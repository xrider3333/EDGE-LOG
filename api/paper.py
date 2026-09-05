"""Shadow paper trading — the always-on runner re-runs the two crowned strategies on
each day's fresh intraday data and logs the trades the engine WOULD have taken.

Nothing here ever touches real money or a broker; this is a pure "would-have-traded"
shadow log written to Firestore (users/{uid}/paper_trades + users/{uid}/paper_reports)
plus a per-uid state doc (users/{uid}/meta/paper_state) that gates the once-a-day run.

Data flow per leg:
  1. Load the leg's master CSV (augur_uploads/*.csv) via find_master/load_master_arrays,
     sliced from ~150 calendar days before "today" (warm-up headroom for ema_len=390 on
     1m ENGU-Q) up to whatever the master already has.
  2. Read the NinjaTrader AddOn's live 10s CSV (C:\\EdgeLog\\ohlc_addon\\NQ_10s.csv,
     fallback C:\\EdgeLog\\ohlc\\NQ_10s.csv), resample to the leg's timeframe, filter to
     RTH (09:30-16:00 America/New_York), and keep only bars strictly AFTER the master's
     last bar — i.e. only the fresh tail the master doesn't have yet.
  3. Append that tail to the loaded arrays IN MEMORY (the master file on disk is never
     touched) and hand the combined arrays to run_backtest(..., return_trades=True).
  4. Trades with an entry date on/after PAPER_START are the "paper" trades; anything
     from the warm-up history before that is discarded.

Everything here is exception-proof by design (try/except around every stage) — a data
hiccup must never take down the runner's watch loop.
"""
import os
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from .util import json_safe

# ── crowned legs ─────────────────────────────────────────────────────────────────
# First trading day shadow trades are logged for. Anything with an entry before this
# (e.g. the warm-up history the engine needs to even start emitting signals) is dropped.
PAPER_START = "2026-08-11"

# ── BACKFILL vs FORWARD (owner 2026-08-16: "are you just assuming they were live
#    from the get go?") ────────────────────────────────────────────────────────────
# No, and the board must not imply it. run_shadow re-runs the WHOLE window since
# PAPER_START against master data every night, so the day a leg is added it instantly
# produces trades going back to PAPER_START. Those trades are a BACKTEST -- nothing
# watched them happen -- and showing them beside a leg that has genuinely been running
# since 2026-08-11 makes a config added this morning look like a fortnight of evidence.
#
# So every leg carries the date its CURRENT config went on the board, and any trade
# before it is stamped backfill=True. This is not bookkeeping pedantry: a gated leg is
# judged against a pre-registered claim with a date on it, and a claim you can test on
# data that already existed when you wrote it is not a forward test.
#
# ORB is in here at 08-16 too. Its trades predate that, but its CONFIG does not -- the
# leg was swapped off the retired look-ahead #125 cut on 2026-08-16, so its Aug-11 and
# Aug-12 trades were produced by a config that was not on the board when they happened.
LEG_LIVE_FROM = {
    "ENGUQ":     "2026-08-17",   # config swapped RTH #149 -> ETH #226
    "ENGUQ_L50": "2026-08-18",   # leg added: #226 config + shallow limit 0.50 ATR (#249)
    "ENGUQ_ER":  "2026-08-21",   # #265 efficiency-gated config REPLACES the #226 raw leg
    "ENGUQ_ER_H": "2026-08-21",  # its crowned hybrid (logistic@0.55), gated overlay
    "NOISE":     "2026-08-11",   # genuinely forward since PAPER_START
    # ORB legs were swapped #230 -> #234 on the EVENING of 2026-08-21, after that session had
    # closed and after its nightly shadow run. A 2026-08-21 trade therefore was not watched
    # under this config, so the first FORWARD session is the next trading day, 2026-08-24.
    "ORB":       "2026-08-24",   # config swapped #230 -> #234 (crown followed into paper)
    "ORB_H":     "2026-08-24",   # gate re-based on #234 (its own crowned rf@0.45, re-calibrated)
    "NOISE_225": "2026-08-16",   # leg added
    "NOISE_H":   "2026-08-16",   # gate added; the pre-registered claim starts here
    "NOISE_H_RF": "2026-08-16",  # owner's pick, added the same day
    "NOISE_SBS": "2026-08-21",   # leg added the day the owner crowned run #241; retired 08-23
    "NOISE_SBS_V90": "2026-08-23",  # leg added the day the owner crowned run #243
    "NOISE_SBS_V90_H": "2026-08-24",  # its run-#243 gate overlay (et@0.50), forward test only
    "NOISE_SBS_V90_T": "2026-08-24",  # its run-#243 size TILT (xgb/tier), forward test only
    "ENGUQ_309": "2026-09-05",  # NEW FAMILY CROWN (owner: "crown #309 and swap the paper
    # leg to it"); ENGUQ_ER / ENGUQ_ER_H / ENGUQ_L50 keep their own dates unchanged --
    # this is an addition, not a swap-in-place.
}

# NQ contract multiplier ($/point) — same value augur_engine/book.py's _MULT table and
# tools/t5_runboard.py / tools/book_smoke.py use for NQ.
_NQ_MULT = 20.0
# NQ round-trip cost in POINTS — same value tools/t5_runboard.py's leg_trades() and
# tools/book_smoke.py use for both the ORB and ENGU-Q NQ legs (commission+slippage,
# see ORB.md: "cost_pts = 0.533 (NQ, mult 20)").
_NQ_COST_PTS = 0.533

# ORB leg params: ORB_125 is defined inline in tools/t5_runboard.py (line ~26), a
# top-level research SCRIPT that runs full 16yr backtests as a side effect of being
# imported — not safe to import from. Copied here verbatim instead (source: tools/
# t5_runboard.py ORB_125) MINUS partial_exit_R/trail_bars: t5_runboard.py actually
# runs this dict against ORB_3_1.py (the richer partial/trailing-stop version), but
# this leg is pinned to ORB_3_0.py — the deliberately-stripped "5 knob" deployable
# (see that file's own docstring) whose run_backtest() has no partial_exit_R or
# trail_bars parameter at all (TypeError if passed); the other knobs are identical.
# RETIRED 2026-08-16: this was run #125's no-trail cut, whose volume filter is the
# LOOK-AHEAD one (2026-08-11 audit) -- the shadow numbers it produced were never
# live-achievable, so forward-testing it measured nothing you could ever trade. Kept only
# as a named reference for old reports that cite it.
ORB_125_RETIRED = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25,
                       breakout_buf=0.0, target_R=0.0, flat_eod=True)

# RETIRED 2026-08-21: run #230 (ORB-40) was the crown from 2026-08-13 to 2026-08-21 and the
# paper ORB config from 2026-08-16 to 2026-08-21. Kept only so old daily reports resolve.
ORB_230 = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, atr_filter=0.7,
               vpace_filter=0.7, close_confirm=True, breakout_buf=0.25, trail_bars=3,
               target_R=5.5, partial_exit_R=3.0, flat_eod=True, skip_holidays=True)

# The current ORB crown: run #234 (ORB-42), ORB_3_6_C2.py. Same entry machinery as #230
# (OR 2, first-candle direction, CLOSE-CONFIRMED, buf 0.25, stop 2.0, v-pace 0.7, ATR 0.7)
# with the SIMPLER exit: ride to 5.5R with breakeven at 1.0R, partial and trail OFF. Two
# fewer knobs than #230 and better on every axis ($389,874 vs $348,129; DD $29,142 vs
# $35,474; lockbox $88,943 PF 1.45 vs $64,575 PF 1.31; WF 7/8 both). PASS 6/6, ES transfer
# PASS. The open Auto-Validate of the same space (run #264, 353 configs) could not find it
# and its own pick FAILED the lockbox, which is the point of pinning. Owner crowned it as
# the baseline 2026-08-21 and asked for paper to follow. Params copied from run #234.
ORB_234 = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.0, atr_filter=0.7,
               vpace_filter=0.7, close_confirm=True, breakout_buf=0.25, trail_bars=0,
               target_R=5.5, partial_exit_R=0.0, be_after_R=1.0, flat_eod=True,
               skip_holidays=True)

# ENGU-Q leg params: NQ_DEPLOY_PARAMS_149 is a clean module-level constant in
# augur_strategies/ENGUQ_1M_1_0.py — import it directly.
from augur_strategies import ENGUQ_1M_1_0 as _enguq  # noqa: E402
ENGUQ_149 = dict(_enguq.NQ_DEPLOY_PARAMS_149)

# ENGU-Q ETH -- the config run #226 certified, and the one this leg should have been
# testing all along (owner 2026-08-17: "ENGUQ is suppose to be ETH right?").
#
# BACKTESTING_STACK.md, 2026-08-13, in its own words: #226 is "formally certified as the
# PRIMARY DEPLOYMENT CANDIDATE" and "the only ENGU-Q variant whose backtest matches live
# behaviour", because the RTH champion "loses $178,340 to a real 24h stop; ETH manages the
# night". The RTH leg's numbers assume a position can sit through the overnight session
# with no stop -- which is not a thing you can actually trade. The same entry names the
# remaining gate before adoption as "paper-forward leg", i.e. exactly this.
#
# The params are the frozen clock-scaled #149 transfer (time lookbacks x3.54 for the 24h
# tape: ema 390->1380, tl 48->170, atr 30->106), copied from run #226's best_params.
ENGUQ_226_ETH = dict(ema_len=1380, tl_len=170, atr_len=106, buf_atr=0.9, vol_mult=0.8,
                     stop_mult=1.0, trail_frac=2.5, regime_len=0, min_brk=1.3,
                     breakeven_R=1.5, act_R=2.5)

# ENGU-Q ETH + SHALLOW LIMIT 0.50 ATR -- run #249 (ENGU-Q-27), owner-adopted 2026-08-18.
#
# Identical to ENGUQ_226_ETH in every knob; the ONLY difference is limit_atr=0.5, which
# replaces the signal-bar-close fill with a resting limit 0.5 x ATR below that close,
# scanned up to 10 bars, gap-honest (a bar that opens through the limit fills at the open,
# never at an untouchable price), and NO TRADE if it never fills.
#
# Why this leg exists: auto-validate #249 returned checks 5/5 with the lockbox HELD and the
# ML gate agreeing (LOCKBOX HELD). Full window 2,924 trades / $513,008 / PF 1.401 vs the
# #226 control's 2,843 / $434,721 / PF 1.332. Profit factor is scale-invariant, so a PF that
# rises with limit depth (1.332 -> 1.358 at 0.20 -> 1.401 at 0.50) is a genuine trade-quality
# improvement, not leverage. Lockbox PF 1.674 vs 1.493.
#
# HONEST CAVEATS, both recorded so the forward test is read correctly:
#   (a) Entering lower against the SAME swing-low stop widens per-trade risk, so drawdown
#       scales with profit: net/DD 8.32 vs the control's 8.62. This buys quality, not a
#       better risk-adjusted ratio, and it FAILS the pre-registered net/DD >= 9.50 bar.
#   (b) The validate report's lockbox is graded by a warm-start reload that carries no open
#       position or pending limit across the boundary, so it takes trades the continuous run
#       had blocked (222 vs 198). Continuous, entry-sliced lockbox is $126,069 / PF 1.674;
#       the report's more conservative $112,088 / PF 1.554 also passes.
#
# A resting limit is also the most executable entry this project has tested -- you place the
# order and wait, rather than needing a fill at a bar's closing print.
ENGUQ_LIM50 = dict(ENGUQ_226_ETH, limit_atr=0.5)

# ENGU-Q ETH + EFFICIENCY GATE -- run #265 (ENGU-Q-28), owner-adopted to paper 2026-08-21
# ("replace the old enguq"). Identical to ENGUQ_226_ETH in every knob; the ONLY addition is
# a momentum-quality floor: the Kaufman efficiency ratio of the last 60 one-minute closes
# (net move divided by path length) must be at least 0.25 on the signal bar. Signals that
# fire out of churn are skipped; nothing about stop, trail or exit changes.
#
# Why it replaced #226 rather than running beside it: #265 is the first confirmation gate
# in this project's history to survive a pre-registered bar. Validate #265: checks 5/5,
# walk-forward 8/8 (the first ENGU-Q variant ever to hold every fold), lockbox HELD at
# $135,983 / PF 2.29 on the report basis ($146,231 / PF 2.65 continuous, entry-sliced).
# Full window vs the #226 control: trades 2,843 -> 1,336, net $434,721 -> $486,413,
# PF 1.332 -> 1.597, and the top-10 concentration FALLS 0.78 -> 0.70. The PF gain holds
# in all four eras and wins 96.4% of 5,000 paired block bootstraps.
#
# Caveats, so the forward test is read correctly: only ~67-83 lockbox trades; the plateau
# is ONE-SIDED (er_th 0.30 collapses the lockbox -- never raise the floor); and it pairs
# better with the raw entry than with the limit-0.50 entry, so this leg is the RAW entry.
ENGUQ_ER25 = dict(ENGUQ_226_ETH, er_len=60, er_th=0.25, limit_atr=0.0)

# Its crowned hybrid gate. Run #265 crowned logistic@0.55 by the standing pre-registered
# rule (net dollars within 80%-of-best MAR, pre-lockbox only). HONEST READ of the card:
# the ML overlay did NOT beat ungated on the held-out year (gated recovery 5.69 vs ungated
# 5.86; gated 48 trades / PF 2.69 vs ungated 67 / PF 2.65) -- the card says "LOCKBOX
# FAILED" for that reason. So this leg is a pre-registered forward TEST of the crowned
# hybrid, not a crown: the claim is that from 2026-08-21 ENGUQ_ER_H beats its exact
# control ENGUQ_ER on recovery factor. If it does not, the overlay adds nothing to an
# already-gated signal and should be dropped. The rf hybrid on the same card (LB PF 5.80
# on 22 trades) was NOT chosen: its PRE-lockbox row is worse than ungated (PF 1.27 vs
# 1.56), so picking it would be hindsight, exactly the NOISE_H mistake documented above.
# size_norm / recycle_factor calibrated by tools/paper_gate_calibrate.py on 2026-08-21.
ENGUQ_ER_GATE = {"mode": "hybrid", "model": "logistic", "threshold": 0.55,
                 "size_norm": 1.697185, "recycle_factor": 1.877809, "source_run": 265}

# ENGU-Q ETH -- run #309, the NEW FAMILY CROWN (owner, 2026-09-05: "crown #309 and swap
# the paper leg to it"). Same strategy file as the efficiency-gated leg above
# (ENGUQ_1M_ETH_ER_1_0.py) but a DIFFERENT cell in that file's search space -- er_th=0.0,
# i.e. the efficiency gate is OFF here. This is not the #265 config with one knob
# changed; it is a distinct champion out of the same file's parameter space, picked by
# the family's EV R / R-YR yardstick (memory `edgelog-round6-evr-ryr`).
#
# Params are run #309's own best_params, read straight from its Firestore run doc
# (users/{uid}/runs/309) and independently re-derived, not copied on faith: run through
# augur_engine.engine.run_backtest over 2010-06-07..2026-06-30 (NQ 1m ETH,
# db_noadj_eth, cost 0.533, mult 20) this exact dict returns n=1,604 / PF 1.655 /
# net $591,267 -- matching the run doc's own validate.total_trades=1604. The run doc's
# validate.verdict is PASS: checks 6/6 (plateau, wfe, sample, consistency, pbo, luck),
# WF folds_held 6 of 8, lockbox pass=true (reload 112 trades, PF 1.541). flags.gate says
# "UNGATED WINS PRE-LOCKBOX -- no gate earns its keep" -- consistent with running this
# leg with no ML gate.
#
# THE EVIDENCE the crown decision was made on (tools/continuous_lb_check.py, ONE
# continuous backtest over the same window/costs, trades sliced by ENTRY time --
# reproduced here 2026-09-05, do not substitute other numbers):
#   selection (->2025-06-30): n=1,505 / PF 1.661 / net $505,756 / DD $44,403 /
#     EV R 0.439 / R per YR 43.9
#   held-out year (2025-06-30->2026-06-30): n=99 / PF 1.620 / net $85,511 /
#     EV R 0.407 / R per YR 40.4
#   top-10 share of selection net: 53% (ex-top-10 it still nets $235,741); longest
#     hold 282 days; reload-vs-continuous lockbox trade count 112 vs 99 (a real but
#     modest divergence -- every ENGU-Q config on this engine shows some of this, see
#     ENGUQ.md section 1.0).
# Against the outgoing crown, run #226 (frozen ETH, identical window/costs): selection
# n=2,655 / PF 1.303 / EV R 0.227 / R per YR 40.0; held-out n=188 / PF 1.493 /
# EV R 0.364 / R per YR 68.5; top-10 share 80%; ex-top-10 nets only $67,297.
#
# WHY THE OWNER CROWNED IT: #309 wins selection EV R, selection R/YR and held-out EV R,
# and it is far less tail-dependent than #226 (53% vs 80% of net sitting in its best ten
# trades).
#
# THE HONEST MARK AGAINST IT -- stated plainly, not buried: #309 LOSES on held-out
# R/YR (40.4 vs #226's 68.5) because it trades about half as often (99 lockbox entries
# vs 188). That is the one number in this comparison that argues against the swap.
# #226 is not deleted or reinstated as a running leg over this -- it stays the
# documented control everywhere it is cited (its own run doc, LEG_SOURCE["ENGUQ"]
# below) even though it has not been an active nightly paper leg since 2026-08-21 (see
# that entry's caveat). See ENGUQ.md's CROWN CHANGE 2026-09-05 section for the full
# writeup.
ENGUQ_309 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, ema_len=220, atr_len=52,
                 act_R=1.5, breakeven_R=3.0, limit_atr=0.55, er_len=100, stop_mult=1.3,
                 regime_len=10, min_brk=1.6, vol_mult=1.1, er_th=0.0)

# NOISE leg params: the validated config (see NOISE_1_0.py docstring) + the
# researched bandwidth stop. NOISE is execution-CLEAN (close signal -> next-open
# fill), so unlike ORB its shadow numbers are live-achievable.
NOISE_FROZEN = dict(lookback=14, band_mult_long=1.5, band_mult_short=1.5,
                    exit_mode="vwap", side="Both", window="all_day",
                    flat_eod=True, skip_holidays=False,
                    stop_mode="bandwidth", stop_k=1.0)

# The NOISE config two consecutive auto-validates actually crowned (#202 NOISE-1 and
# #225 NOISE-6 landed on the identical dict). NOISE_FROZEN above is NOT this config --
# it was assembled by hand from round-12 research and never crowned. Both are on the
# board on purpose; see LEG_SOURCE and NOISE.md.
NOISE_225 = dict(lookback=44, band_mult_long=0.75, band_mult_short=1.5,
                 exit_mode="vwap", side="Both", window="all_day",
                 flat_eod=True, skip_holidays=False,
                 stop_mode="bandwidth", stop_k=1.75)

# The CROWNED NOISE config since 2026-08-21: run #241 (NOISE_1_1_SBS.py, "Short Veto",
# PASS 6/6; #253 is its archived identical repeat). It is the NOISE_225 champion core
# plus ONE causal filter -- no short entries on any day whose PRIOR session closed in
# the bottom 20% of that session's own high-to-low range (daytype_lo 0.20, the strategy
# file's pinned default). Crowned by the owner on the 2026-08-21 combination-study
# recommendation: the filter is the best SINGLE change and no stacked combination
# clears the pre-registered bar. Params are run #241's pinned dict, expressed against
# NOISE_1_0.py (the same base file every other NOISE leg runs, which keeps the
# reconcile tooling's one-vocabulary mapping intact). NOISE_225 above stays on the
# board untouched as the matched RAW control -- the filter is the only difference.
NOISE_241_SBS = dict(NOISE_225, daytype_mode="skip_bot_short",
                     daytype_lo=0.20, daytype_hi=0.80)

# The CROWNED NOISE config since 2026-08-23: run #243 (NOISE_1_1_SBS_V90.py, "Short
# Veto + Wild10", PASS 6/6; #252 is its archived identical repeat). It is run #241's
# config plus ONE more causal filter -- no entries at all on any day whose PRIOR
# session's (high-low)/close percentile, ranked against the trailing 252 sessions,
# is 90 or higher (vol_skip_pct=90; needs 60 reference sessions before it activates).
# Crowned by the owner on 2026-08-23 for the RISK profile, not the money: ~2% less
# total profit than #241 buys ~41% less drawdown ($22,096 vs $31,191), a better PF
# (1.39 vs 1.29), an equal-or-better lockbox, and the family's best ES transfer
# (1.116). Recorded caveat, accepted as a bounded risk: the volatility filter's
# standalone gains concentrate in its ten best avoided trades, so if that benefit
# decays this config degrades toward #241's profile. Params expressed against
# NOISE_1_0.py like every other NOISE leg; NOISE_225 stays the matched RAW control.
NOISE_243_SBS_V90 = dict(NOISE_241_SBS, vol_skip_pct=90.0)

# ── ML gate configs (api/paper_gate.py) ──────────────────────────────────────────
# The gate is an OVERLAY: the strategy picks its trades exactly as it always has, and a
# second model trained only on trades that had already finished decides which to keep
# ("cut") and, in "hybrid" mode, how big to trade the survivors. Read paper_gate.py's
# docstring for the leak rules -- they are the whole reason this is safe to forward-test.
#
# `size_norm` is the FROZEN size divisor. It is not a guess: tools/paper_gate_calibrate.py
# recomputed each gate against its source run's own window and lockbox boundary and
# reproduced that run's stored hybrid row exactly (ORB_H 1946 survivors / max size 1.78 vs
# run #230's kept_pre 1946 / max_size 1.78; NOISE_H 2206 / 1.80 vs run #225's 2206 / 1.8).
# Re-run that tool if a leg's base params, model, or cut-off ever change.
#
# `history_from` makes these legs load their FULL master history rather than the 150-day
# warm-up the raw legs use. That is deliberate and it costs ~90s a day: a gate trained on
# 150 days is a different model from the one the validate crowned, and forward-testing a
# different model than the one under test would answer a question nobody asked.

# ORB — the evidence-backed one. Run #234 (the crown since 2026-08-21) crowned rf@0.45 by
# the same pre-registered net-dollars/80%-MAR-floor rule on PRE-lockbox data only, exactly
# as #230 had, and it HELD its one look at the lockbox: the rf HYBRID row posts held-out
# PF 1.569 vs ungated 1.453, 5,393 vs 4,447 pts, drawdown -1,169 vs -1,286 pts. That is
# best on both halves of the boundary again, the pattern the #230 gate had, reproduced on
# the new base. size_norm / recycle_factor were RE-CALIBRATED for #234 by
# tools/paper_gate_calibrate.py on 2026-08-21 (the divisor is specific to base params +
# model + cut-off, so the #230 numbers could not be carried over).
ORB_GATE = {"mode": "hybrid", "model": "rf", "threshold": 0.45,
            "size_norm": 1.172525, "recycle_factor": 1.213687, "source_run": 234}

# NOISE — the HONEST-TEST one. Read this before trusting the leg.
#
# Run #225's crowned gate was logistic@0.55 and it FAILED its lockbox outright (gated
# recovery 0.44 vs ungated 1.50). Among the hybrid rows, `tree` at the same floor posted by
# far the best held-out year -- PF 1.240 vs ungated 1.128, $3,117 vs $2,286, drawdown -1,079
# vs -1,521 -- but its PRE-lockbox recovery (5.96) was the WORST of the five. The selection
# rule only ever sees pre-lockbox data, so tree would never have been crowned; its lockbox
# win is visible only in hindsight.
#
# So this leg is NOT a crown and must never be described as one. It is a pre-registered
# forward test of a hindsight-generated hypothesis, which is the one legitimate way to
# settle a result like this: the claim is written down BEFORE the data exists, and paper
# trading costs nothing but compute. THE CLAIM, stated so it can fail: from 2026-08-16
# forward, NOISE_H should beat its matched raw control NOISE_225 on recovery factor. If it
# does not, the pre-lockbox ranking was right and the lockbox row was noise.
NOISE_GATE = {"mode": "hybrid", "model": "tree", "threshold": 0.55,
              "size_norm": 1.468647, "recycle_factor": 2.098733, "source_run": 225}

# NOISE, rf — the OWNER's pick (2026-08-16), and on the evidence it is the better-grounded
# of the two. Worth spelling out because it reverses the reasoning above.
#
# Judge the five hybrids ONLY on the years the selection rule is allowed to see (run #231,
# pre-lockbox recovery; ungated scores 14.23):
#     logistic 24.08 ✓   rf 19.72 ✓   xgb 12.47 ✗   et 11.94 ✗   tree 5.96 ✗
# Only logistic and rf beat "just take every trade". TREE DOES NOT EVEN CLEAR THAT BAR --
# it is the worst of the five on the legitimate criterion, which is the other half of why
# NOISE_H is a test rather than a crown.
#
# Now the held-out year (hindsight, never a basis for choosing; ungated recovery 1.79):
#     tree 3.05   rf 1.69   xgb 1.43   logistic 0.51   et negative
# logistic wins before the boundary and collapses after it. tree does the reverse. rf is
# 2nd on BOTH sides -- the only variant that is neither a pre-lockbox darling that died nor
# a hindsight favourite that never earned its place.
#
# Being honest about rf's weakness: out of sample it does NOT beat ungated. Recovery 1.69 vs
# 1.79, on less than half the money (1,405 vs 2,943 pts). What it does do is halve the
# drawdown (831 vs 1,640) for roughly the same risk-adjusted return -- a RISK REDUCER, not a
# money maker, and the same shape the ENGU-Q gate showed. That makes it a sizing-up lever
# rather than an edge, and the forward test should be read that way.
NOISE_GATE_RF = {"mode": "hybrid", "model": "rf", "threshold": 0.55,
                 "size_norm": 1.338251, "recycle_factor": 3.850308, "source_run": 231}

# NOISE crown (#243) + its own gate — FORWARD EVIDENCE ONLY. Read this before citing it.
#
# The owner asked (2026-08-24) for the run-#243 HYBRID added to paper: on the report its
# risk/reward beats RAW (the xgb tab he read: MAR 22.6 vs 15.03, Sharpe 1.42 vs 1.34,
# PF 1.44 vs 1.37, REDEPLOY WF+LB $488k vs $349k). Two honesty notes on that:
#
#   1. THE MODEL IS et, NOT xgb. Run #243's own gate_validate.chosen — the model the
#      standing pre-registered net-dollars/80%-MAR-floor rule picked on PRE-lockbox data
#      only — is `et` (extra-trees) at the 0.50 floor. The xgb tab the owner read is a
#      different hybrid on the same card, and on the years the rule is allowed to see
#      xgb does not even clear ungated (recovery 12.16 vs 17.38); its lockbox slice is
#      the worst of the five (PF 1.016, $130). Cherry-picking it by eye would be exactly
#      the hindsight selection this project bans, so this leg runs the doc's choice: et.
#
#   2. THE GATE FAMILY IS CLOSED FOR BACKTEST ADOPTION. Run #243's card itself says
#      "LOCKBOX FAILED — gate lost to ungated out-of-sample (pre-lockbox win was likely
#      fit)", the same verdict as #225/#231, and the pre-registered #219 test before
#      them. In-sample hybrid outperformance is precisely the pattern that has already
#      failed its lockbox twice. Forward paper testing is the ONE legitimate new-evidence
#      path left for a gated NOISE, so this leg exists to gather that evidence — it must
#      never be adopted, crowned, or reported as validated off backtest numbers.
#
# THE CLAIM, stated so it can fail: from 2026-08-24 forward, NOISE_SBS_V90_H should beat
# its matched raw control NOISE_SBS_V90 on recovery factor. If it does not, the lockbox
# verdict was right and the in-sample hybrid shine was fit.
#
# size_norm / recycle_factor frozen by tools/paper_gate_calibrate.py on 2026-08-24
# against run #243's own window (2010-06-07..2026-08-12, lockbox from 2025-02-11).
# The calibration reproduced the run's stored et hybrid row exactly: 2,613 pre-lockbox
# survivors vs chosen.pre num_trades 2613; 2,983 kept over the full window vs the et
# hybrid row's n_trades 2983; max size after norm 1.38 vs the row's max_size 1.38.
NOISE_243_GATE = {"mode": "hybrid", "model": "et", "threshold": 0.50,
                  "size_norm": 1.232698, "recycle_factor": 1.484747, "source_run": 243}

# NOISE crown (#243) + size TILT — FORWARD EVIDENCE ONLY, same discipline as the hybrid.
#
# A TILT skips nothing: every trade the crown takes is taken, and only the SIZE moves
# with the model's score (tier rule: 0.5x under a 45% score, 1x from 45 to 55%, 2x over
# 55%; normalised to mean 1 over the source run's pre-lockbox trades, capped 3x — the
# report's mean_weight_matched_pre_lockbox_cap3 rule, reimplemented in api/paper_gate.py's
# TILT mode 2026-08-24).
#
# MODEL/SCHEME CHOICE, stated so nobody re-litigates it: picked by the family's STANDING
# pre-registered selection metric for tilts — PRE-lockbox recovery — on which run #243's
# ten tilt rows rank xgb/tier first (18.82). NOT et/tier: that row is first only on raw
# pre-lockbox PnL, and it also happens to be the lockbox winner, so choosing it would
# read as lockbox-informed selection.
#
# THE MECHANISM IS PRE-REGISTERED DEAD FOR BACKTEST ADOPTION: the 2026-08-10 gate-as-
# size-tilt test ran 0/12 clear of the pre-registered bar on causal scores, and the
# earlier "beats the cut" result was leak-driven. This leg exists to gather FORWARD
# evidence only, and must never be crowned or adopted off backtest numbers.
#
# THE CLAIM, stated so it can fail: from 2026-08-24 forward, NOISE_SBS_V90_T should beat
# its matched raw control NOISE_SBS_V90 on recovery factor. If it does not, the 0/12
# verdict stands and the tilt stays dead.
#
# size_norm frozen by tools/paper_gate_calibrate.py on 2026-08-24 against run #243's own
# window. A tilt has no recycle factor: nothing is skipped, so nothing is respent.
# The calibration reproduced the run's stored xgb/tier tilt row: 4,054 pre-lockbox
# trades vs the row's kept_pre 4054, max size after norm 1.885 vs the row's 1.89.
NOISE_243_TILT = {"mode": "tilt", "model": "xgb", "scheme": "tier",
                  "size_norm": 1.060804, "source_run": 243}

# Full-history load date for the gated legs (the masters begin here).
_GATE_HISTORY_FROM = "2010-06-07"

# PROVENANCE — where each leg's config actually came from (owner 2026-08-15: "i dont
# know which config or past run it got it from"). This is the AUTHORITATIVE record; it
# is written into every daily report's legs block so the board can show it, and it is
# what tools/nt_config_reconcile.py's mapping is checked against.
#
# Keep it honest: `run` is the Past-Runs number the params came from, or None when the
# config was never crowned by a run (NOISE's stop came out of a hand-run sweep, not an
# auto-validate). `caveat` is the one thing you would want to know before trusting the
# leg's numbers -- leave it None rather than inventing reassurance.
LEG_SOURCE = {
    "ORB": {
        "run": 234, "run_label": "#234 (ORB-42)", "strategy_file": "ORB_3_6_C2.py",
        "picked": "2026-08-21",
        "note": "The standing ORB crown, crowned as the baseline by the owner on 2026-08-21: "
                "the #230 CLOSE-CONFIRMED entry (OR 2 bars, first-candle direction) with the "
                "simpler ride-to-5.5R exit protected by breakeven at 1R. PASS on all six "
                "checks, lockbox HELD (PF 1.45 over 178 trades, 2025-08-13..2026-08-13), "
                "ES transfer PASS, and its six one-knob neighbours all PASS too.",
        "caveat": "Replaced the #230 leg on 2026-08-21. ORB paper numbers from 2026-08-16 "
                  "to 2026-08-21 measured #230 (same entries, partial+trail exit); before "
                  "2026-08-16 they measured the look-ahead #125. Compare across the "
                  "switches with that in mind.",
    },
    "ENGUQ": {
        "run": 226, "run_label": "#226 (ENGU-Q ETH FROZEN)",
        "strategy_file": "ENGUQ_1M_ETH_FROZEN_1_0.py",
        "picked": "2026-08-17",
        "note": "The 24-hour (ETH) config, certified 2026-08-13 as the PRIMARY DEPLOYMENT "
                "CANDIDATE and the only ENGU-Q variant whose backtest matches live "
                "behaviour. Frozen clock-scaled #149 transfer (time lookbacks x3.54 for the "
                "24h tape). PASS 5/5, walk-forward 7/8, full window 2,843 trades / $434,721 "
                "/ PF 1.33.",
        "caveat": "RETIRED FROM PAPER 2026-08-21 -- replaced by the #265 efficiency-gated "
                  "config (ENGUQ_ER). Still the certified standalone crown; kept here so "
                  "older daily reports resolve. Replaced the RTH #149 leg on 2026-08-17. That leg's numbers assumed a "
                  "position could sit through the overnight session with no stop -- the RTH "
                  "champion gives back $178,340 once a real 24h stop is priced in. Every "
                  "ENGU-Q paper number before this date was measuring that.",
    },
    "ENGUQ_ER": {
        "run": 265, "run_label": "#265 (ENGU-Q ETH EFFICIENCY 0.25)",
        "strategy_file": "ENGUQ_1M_ETH_ER25_1_0.py",
        "picked": "2026-08-21",
        "note": "The #226 ETH config plus a momentum-quality floor: the last hour's Kaufman "
                "efficiency ratio must reach 0.25 at the signal. Validate #265: checks 5/5, "
                "walk-forward 8/8, lockbox HELD $135,983 / PF 2.29. Full window 1,336 trades "
                "/ $486,413 / PF 1.60 vs the #226 control's 2,843 / $434,721 / PF 1.33.",
        "caveat": "REPLACED the #226 raw leg on 2026-08-21 (owner). Few lockbox trades (67-83); "
                  "one-sided plateau -- a 0.30 floor collapses the lockbox, so never raise it; "
                  "pairs better with the raw entry than with the limit entry. The ENGUQ_L50 "
                  "leg lost its matched control when #226 left the board; read it against "
                  "this row knowing the two differ in BOTH entry and gate.",
    },
    "ENGUQ_ER_H": {
        "run": 265, "run_label": "#265 hybrid (logistic@0.55)",
        "strategy_file": "ENGUQ_1M_ETH_ER25_1_0.py",
        "picked": "2026-08-21",
        "note": "The same #265 config with its crowned ML hybrid overlay: logistic model, "
                "0.55 cut-off, survivors sized by score. Pre-lockbox the hybrid beat ungated "
                "(PF 1.65 vs 1.56).",
        "caveat": "A forward TEST, not a crown. On the held-out year the overlay did NOT beat "
                  "ungated (recovery 5.69 vs 5.86) and the card says LOCKBOX FAILED for that "
                  "reason. The claim to falsify: from 2026-08-21 this row beats ENGUQ_ER on "
                  "recovery factor. ENGUQ_ER is its exact control -- one backtest, two rows.",
    },
    "ENGUQ_L50": {
        "run": 249, "run_label": "#249 (ENGU-Q ETH LIMIT 0.50)",
        "strategy_file": "ENGUQ_1M_ETH_LIM50_1_0.py",
        "picked": "2026-08-18",
        "note": "The #226 ETH config with a resting limit entry 0.5 x ATR below the signal "
                "close (10-bar gap-honest fill window, no fill = no trade). Auto-validate "
                "#249: checks 5/5, lockbox HELD, ML gate LOCKBOX HELD, adversarial mild "
                "drift PASS. Full window 2,924 trades / $513,008 / PF 1.401; lockbox "
                "$112,088 / PF 1.554 on the report basis, $126,069 / PF 1.674 continuous.",
        "caveat": "ADDED alongside the #226 leg, which is deliberately kept as the matched "
                  "control -- same config, same tape, only the entry differs, so the forward "
                  "test isolates the limit entry. Two caveats on the numbers: entering lower "
                  "against the same stop widens risk, so net/DD is 8.32 vs the control's 8.62 "
                  "and this FAILS the pre-registered net/DD >= 9.50 bar; and the validate's "
                  "lockbox comes from a warm-start reload that takes trades continuous "
                  "operation had blocked (222 vs 198), so the report understates it.",
    },
    # Kept so older daily reports that cite the RTH leg still resolve.
    "ENGUQ_RTH_RETIRED": {
        "run": 149, "run_label": "#149 (ENGU-Q RTH)", "strategy_file": "ENGUQ_1M_1_0.py",
        "picked": "2026-07-14",
        "note": "NQ_DEPLOY_PARAMS_149 imported directly from the strategy file, plus the "
                "later breakeven_R=1.5 addition. Pine port reconciled against TradingView "
                "2026-07-14 (84.5% of matched trades exact).",
        "caveat": "RETIRED 2026-08-17 -- assumes no overnight stop; superseded by #226 ETH.",
    },
    "NOISE": {
        "run": None, "run_label": "no crowned run", "strategy_file": "NOISE_1_0.py",
        "picked": "2026-08-08",
        "note": "Round-12 frozen defaults (lookback 14, symmetric 1.5 bands, vwap exit) plus "
                "the bandwidth stop k=1.0 that won the 25-variant exit sweep. Assembled by "
                "hand from research, never crowned by an auto-validate run.",
        "caveat": "Auto-validate #225 (NOISE-6) later crowned a DIFFERENT config -- lookback 44, "
                  "asymmetric 0.75/1.5 bands, stop_k 1.75 -- on a fresh 18-month lockbox. This "
                  "leg is not that config. It is now on the board as its own leg, NOISE_225.",
    },
    "NOISE_225": {
        "run": 225, "run_label": "#225 (NOISE-6)", "strategy_file": "NOISE_1_0.py",
        "picked": "2026-08-16",
        "note": "The config two consecutive auto-validates crowned (#202 NOISE-1 and #225 "
                "NOISE-6 landed on the identical dict): lookback 44, asymmetric 0.75/1.5 "
                "bands, bandwidth stop k=1.75. Lockbox PASS, PF 1.08 over 424 trades.",
        "caveat": "Added as the matched RAW control for NOISE_H -- same params, same backtest, "
                  "gate off. Comparing NOISE_H against the older NOISE leg instead would "
                  "confound the gate with a params change.",
    },
    "NOISE_SBS": {
        "run": 241, "run_label": "#241 (Short Veto)", "strategy_file": "NOISE_1_0.py",
        "picked": "2026-08-21",
        "note": "Held the NOISE crown 2026-08-21 to 2026-08-23. The champion core (lookback 44, "
                "asymmetric 0.75/1.5 bands, vwap exit, bandwidth stop k=1.75) plus one causal "
                "filter: no short entries the day after the prior session closed in the bottom "
                "20% of its own range. Run #241 (pinned file NOISE_1_1_SBS.py) validated it "
                "PASS 6/6; the 2026-08-21 combination study then found no filter stack beats "
                "it, which is what that crown decision cited.",
        "caveat": "RETIRED FROM PAPER 2026-08-23 -- the owner moved the crown to run #243 "
                  "(this filter plus the wildest-days skip) and the NOISE_SBS_V90 leg "
                  "replaced this one. Provenance stays here so its two days of nightly "
                  "history still resolve. Historical caveats carried: NOISE_225 was its "
                  "matched RAW control, and the "
                  "NOISE lockbox is SPENT (read many times), so lockbox numbers are "
                  "confirmatory only.",
    },
    "NOISE_SBS_V90": {
        "run": 243, "run_label": "#243 (Short Veto + Wild10)", "strategy_file": "NOISE_1_0.py",
        "picked": "2026-08-23",
        "note": "THE CROWNED NOISE CONFIG since 2026-08-23. Run #241's config plus one more "
                "causal filter: no entries at all on a day whose prior session's range "
                "percentile (vs the trailing 252 sessions) is 90 or higher. Run #243 (pinned "
                "file NOISE_1_1_SBS_V90.py) validated it PASS 6/6. The owner crowned it for "
                "the risk profile: ~2% less total profit than #241 buys ~41% less drawdown "
                "($22,096 vs $31,191), a better PF (1.39 vs 1.29), an equal-or-better "
                "lockbox, and the family's best ES transfer (1.116).",
        "caveat": "NOISE_225 is its matched RAW control -- identical settings, filters off, so "
                  "any difference between the two rows is the filters and nothing else. "
                  "Recorded caveat, accepted as a bounded risk: the volatility filter's "
                  "standalone gains concentrate in its ten best avoided trades, so if that "
                  "benefit decays this config degrades toward run #241's profile. The NOISE "
                  "lockbox is SPENT (read many times), so lockbox numbers are confirmatory "
                  "only -- this forward test and the walk-forward folds are the real judges. "
                  "NinjaTrader does NOT carry either filter yet: EdgeLogNOISE has both knobs "
                  "(default OFF) and keeps running the baseline-plus-gate config until they "
                  "are flipped on after an NT restart.",
    },
    "NOISE_SBS_V90_H": {
        "run": 243, "run_label": "#243 (Short Veto + Wild10) + et hybrid gate",
        "strategy_file": "NOISE_1_0.py", "picked": "2026-08-24",
        "note": "The crowned #243 config (champion core + short veto + wildest-10% skip) "
                "with run #243's OWN chosen gate in HYBRID mode: an extra-trees model at "
                "the 0.50 floor, trades under it skipped, survivors sized by score. The "
                "model is the one run #243's gate_validate.chosen records — picked by the "
                "pre-registered net-dollars/80%-MAR-floor rule on pre-lockbox data — NOT "
                "the xgb tab the owner read on the report; on the years the rule may see, "
                "xgb does not clear ungated and its lockbox slice is the worst of five. "
                "Added at owner ask 2026-08-24.",
        "caveat": "THE GATE FAMILY IS CLOSED FOR BACKTEST ADOPTION — two lockbox failures "
                  "(#219, and the #225/#231 verdict), and run #243's own card says "
                  "LOCKBOX FAILED (gate lost to ungated out-of-sample). This leg exists "
                  "to gather FORWARD evidence only and must never be crowned or adopted "
                  "off backtest numbers. The claim to falsify: from 2026-08-24 it beats "
                  "its matched raw control NOISE_SBS_V90 on recovery factor. NOISE_SBS_V90 "
                  "is its exact control — identical file and params, gate off.",
    },
    "NOISE_SBS_V90_T": {
        "run": 243, "run_label": "#243 (Short Veto + Wild10) + xgb/tier size tilt",
        "strategy_file": "NOISE_1_0.py", "picked": "2026-08-24",
        "note": "The crowned #243 config with run #243's size-TILT construct: every trade "
                "is taken, and an xgb model's score only sets the SIZE (0.5x under 45%, 1x "
                "45-55%, 2x over 55%, mean-1 normalised, capped 3x). xgb/tier was picked by "
                "the standing pre-registered tilt selection metric — pre-lockbox recovery, "
                "where it ranks first of the ten tilt rows (18.82) — NOT et/tier, which "
                "leads only on raw pre-lockbox PnL and also wins the lockbox, so choosing "
                "it would read as lockbox-informed selection. Added at owner ask 2026-08-24 "
                "beside the hybrid leg.",
        "caveat": "THE TILT MECHANISM IS PRE-REGISTERED DEAD FOR BACKTEST ADOPTION — the "
                  "2026-08-10 test ran 0/12 clear of the bar on causal scores. This leg "
                  "exists to gather FORWARD evidence only and must never be crowned or "
                  "adopted off backtest numbers. The claim to falsify: from 2026-08-24 it "
                  "beats its matched raw control NOISE_SBS_V90 on recovery factor. "
                  "NOISE_SBS_V90 is its exact control — identical file and params, tilt "
                  "off; the tilt takes the identical trade list at different sizes.",
    },
    "ORB_H": {
        "run": 234, "run_label": "#234 (ORB-42) + rf hybrid gate", "strategy_file": "ORB_3_6_C2.py",
        "picked": "2026-08-21",
        "note": "The ORB leg with the run #234 ML gate switched on in HYBRID mode: trades "
                "scoring under 45% are skipped and the survivors are sized by score. Crowned "
                "on pre-lockbox data by the pre-registered rule and then HELD its one look at "
                "the lockbox (held-out PF 1.569 vs 1.453 ungated, drawdown -1,169 vs -1,286 "
                "pts). Size divisor re-calibrated for this base on 2026-08-21.",
        "caveat": "Its matched RAW control is the ORB leg -- identical strategy file and params, "
                  "gate off -- so any difference between the two rows is the gate and nothing else. "
                  "Re-based from #230 on 2026-08-21; earlier ORB_H rows measured the #230 gate.",
    },
    "NOISE_H_RF": {
        "run": 231, "run_label": "#231 (NOISE-7) + rf hybrid gate", "strategy_file": "NOISE_1_0.py",
        "picked": "2026-08-16",
        "note": "The owner's pick, and the better-grounded of the two NOISE gates. On the years "
                "the selection rule is ALLOWED to see, rf recovery 19.72 beats ungated 14.23 -- "
                "one of only two hybrids that clear that bar, and tree is not one of them. It is "
                "also 2nd of five on BOTH sides of the lockbox boundary: the only variant that is "
                "neither a pre-lockbox darling that collapsed nor a hindsight favourite.",
        "caveat": "It does NOT beat ungated out of sample -- recovery 1.69 vs 1.79, on less than "
                  "half the money (1,405 vs 2,943 pts). What it does is HALVE the drawdown (831 "
                  "vs 1,640) at about the same risk-adjusted return. Read it as a risk reducer "
                  "and a sizing-up lever, not as an edge.",
    },
    "NOISE_H": {
        "run": 225, "run_label": "#225 (NOISE-6) + tree hybrid gate", "strategy_file": "NOISE_1_0.py",
        "picked": "2026-08-16",
        "note": "Run #225's crowned config with a tree hybrid gate at the crowned 0.55 floor. In "
                "that run's held-out year this row was the standout: PF 1.240 vs 1.128 ungated, "
                "$3,117 vs $2,286, drawdown -1,079 vs -1,521.",
        "caveat": "NOT A CROWN, and it must not be reported as one. Its PRE-lockbox recovery "
                  "(5.96) was the WORST of the five hybrids, so the selection rule -- which only "
                  "sees pre-lockbox data -- would never have picked it; the lockbox win is "
                  "hindsight. #225's actual crowned gate (logistic@0.55) FAILED its lockbox. This "
                  "leg is a pre-registered forward test: it should beat NOISE_225 on recovery "
                  "from 2026-08-16 on, and if it does not, the lockbox row was noise.",
    },
    "ENGUQ_309": {
        "run": 309, "run_label": "#309 (ENGU-Q ETH, EV R / R-YR crown)",
        "strategy_file": "ENGUQ_1M_ETH_ER_1_0.py",
        "picked": "2026-09-05",
        "note": "THE NEW FAMILY CROWN, replacing #226 (owner, 2026-09-05: \"crown #309 and "
                "swap the paper leg to it\"). Same strategy file as ENGUQ_ER but a different "
                "cell of its search space (er_th=0.0, gate off). Measured continuously over "
                "2010-06-07..2026-06-30, NQ 1m ETH, cost 0.533, mult 20 (tools/"
                "continuous_lb_check.py): selection n=1,505 / PF 1.661 / net $505,756 / "
                "DD $44,403 / EV R 0.439 / R per YR 43.9; held-out year n=99 / PF 1.620 / "
                "net $85,511 / EV R 0.407 / R per YR 40.4; top-10 share of selection net "
                "53% (ex-top-10 still nets $235,741); longest hold 282 days. Whole-window "
                "parity: n=1,604 / PF 1.655 / net $591,267, matching the run doc's own "
                "validate.total_trades=1604. Run doc verdict PASS (checks 6/6: plateau, "
                "wfe, sample, consistency, pbo, luck; WF folds_held 6 of 8; lockbox "
                "pass=true, reload 112 trades / PF 1.541). flags.gate: \"UNGATED WINS "
                "PRE-LOCKBOX -- no gate earns its keep\", so this leg runs with no ML gate.",
        "caveat": "THE HONEST MARK AGAINST IT: #309 loses to #226 on held-out R per YR "
                  "(40.4 vs 68.5) because it trades about half as often (99 lockbox "
                  "entries vs 188) -- say this plainly whenever the swap is cited. #226 "
                  "is the outgoing family crown, not deleted or reinstated as a running "
                  "leg -- see LEG_SOURCE[\"ENGUQ\"]. The #265 pair (ENGUQ_ER/ENGUQ_ER_H) "
                  "and ENGUQ_L50 are UNTOUCHED by this crown move: ENGUQ_ER/ENGUQ_ER_H is "
                  "the outgoing paper control and ENGUQ_L50 is its own active "
                  "pre-registered hybrid test, deliberately left running; the owner can "
                  "retire either on request. See ENGUQ.md's CROWN CHANGE 2026-09-05 "
                  "section for the full writeup.",
    },
}

PAPER_LEGS = [
    # ORB: the engine's touch-entry volume filter is LOOK-AHEAD (2026-08-11 audit,
    # see PAPER_TRADING.md) — these shadow numbers are NOT live-achievable. Kept as
    # a flagged reference line; the live candidate is the NT-side ORB V2 chase.
    # history_from matches ORB_H's window so the two legs are the SAME backtest with the
    # gate off/on. Verified 2026-08-16: the 150-day window and the full history produce a
    # bit-identical trade set here, so this changes no number today -- it just stops a
    # future warm-up difference from quietly turning the control into a different
    # experiment. Costs about a second.
    {"key": "ORB", "strategy": "ORB_3_6_C2.py", "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "params": ORB_234, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "history_from": _GATE_HISTORY_FROM, "source": LEG_SOURCE["ORB"]},
    # ADDED 2026-09-05 (owner: "crown #309 and swap the paper leg to it"). The NEW
    # ENGU-Q family crown -- see ENGUQ_309's own comment block above for the full
    # evidence and ENGUQ.md's CROWN CHANGE 2026-09-05 section for the writeup. This is
    # an ADDITION, not a swap-in-place: the #265 efficiency-gated pair immediately below
    # (ENGUQ_ER_H, which emits its own control as ENGUQ_ER) and the ENGUQ_L50 leg further
    # down are DELIBERATELY left untouched -- ENGUQ_ER/ENGUQ_ER_H is the outgoing paper
    # control (the config #309 is replacing as the crown) and ENGUQ_L50 is its own,
    # unrelated, active pre-registered hybrid test. The owner can retire either on
    # request; nothing here does it automatically. No ML gate on this leg.
    {"key": "ENGUQ_309", "strategy": "ENGUQ_1M_ETH_ER_1_0.py", "instrument": "NQ",
     "timeframe": "1m", "session": "eth", "params": ENGUQ_309,
     "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT, "source": LEG_SOURCE["ENGUQ_309"]},
    # ETH since 2026-08-17: the RTH leg was forward-testing the variant this project's own
    # docs had already deprecated as not live-realistic. See ENGUQ_226_ETH above.
    # RETIRED FROM PAPER 2026-08-21 (owner: "replace the old enguq"): the #226 raw leg is
    # superseded by the #265 efficiency-gated pair below. Provenance stays in LEG_SOURCE.
    # #265 raw + its crowned hybrid: ONE backtest, two rows. ENGUQ_ER_H applies the logistic
    # overlay; emit_ungated_as publishes the same backtest's pre-gate trades as ENGUQ_ER, so
    # the raw row is the gated row's exact control and nothing is confounded.
    {"key": "ENGUQ_ER_H", "strategy": "ENGUQ_1M_ETH_ER25_1_0.py", "instrument": "NQ",
     "timeframe": "1m", "session": "eth", "params": ENGUQ_ER25,
     "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "gate": ENGUQ_ER_GATE, "history_from": _GATE_HISTORY_FROM,
     "emit_ungated_as": "ENGUQ_ER", "source": LEG_SOURCE["ENGUQ_ER_H"]},
    # ADOPTED 2026-08-18 (owner: "lets go with the .50"). Runs ALONGSIDE the #226 leg above,
    # not instead of it: that leg is the matched control -- identical config, identical tape,
    # the entry is the only difference -- so this pair forward-tests the shallow limit itself
    # rather than just tracking a new number. See LEG_SOURCE["ENGUQ_L50"] for the caveats.
    {"key": "ENGUQ_L50", "strategy": "ENGUQ_1M_ETH_LIM50_1_0.py", "instrument": "NQ",
     "timeframe": "1m", "session": "eth", "params": ENGUQ_LIM50,
     "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT, "source": LEG_SOURCE["ENGUQ_L50"]},
    # RETIRED 2026-08-16 (owner: "remove the old noise raw"). This was NOISE_FROZEN -- the
    # hand-assembled round-12 config that was never crowned by any auto-validate. Three
    # consecutive validates (#202, #225, #231) all landed on the NOISE_225 dict instead, and
    # as of tonight NinjaTrader runs that config too, so this leg was measuring a variant
    # nothing else in the system uses. Its provenance block stays in LEG_SOURCE so old daily
    # reports that reference it still resolve.

    # RETIRED 2026-08-23: the NOISE_SBS leg (run #241, added 2026-08-21) came off the
    # board when the owner moved the crown to run #243 -- the crown leg tracks the
    # crown, exactly as the ENGU-Q raw leg was replaced on 2026-08-21. Its provenance
    # block stays in LEG_SOURCE so its two days of nightly history still resolve.
    #
    # ADDED 2026-08-23, the day the owner crowned run #243 ("Short Veto + Wild10").
    # The crowned NOISE config: champion core + skip short entries the day after a
    # weak close + skip ALL entries the day after a top-decile volatility session.
    # Runs the same base file as every other NOISE leg; NOISE_225 below (emitted by
    # NOISE_H) is its matched RAW control -- the two filters are the only difference.
    # No gate: the crown is the RAW config. history_from matches the gated legs so
    # all four NOISE rows are computed over the identical window.
    {"key": "NOISE_SBS_V90", "strategy": "NOISE_1_0.py", "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "params": NOISE_243_SBS_V90, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "history_from": _GATE_HISTORY_FROM, "source": LEG_SOURCE["NOISE_SBS_V90"]},

    # ADDED 2026-08-24 (owner: add the run-243 hybrid to paper). The crown config above
    # with run #243's own chosen gate (et@0.50, hybrid) as an overlay. The raw
    # NOISE_SBS_V90 leg above is its matched control -- identical file and params, gate
    # off, same full-history window -- so any difference between the two rows is the
    # gate and nothing else. FORWARD EVIDENCE ONLY: the gate family is closed for
    # backtest adoption (see NOISE_243_GATE's block).
    {"key": "NOISE_SBS_V90_H", "strategy": "NOISE_1_0.py", "instrument": "NQ",
     "timeframe": "5m", "session": "rth", "params": NOISE_243_SBS_V90,
     "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "gate": NOISE_243_GATE, "history_from": _GATE_HISTORY_FROM,
     "source": LEG_SOURCE["NOISE_SBS_V90_H"]},
    # ADDED 2026-08-24 beside the hybrid: the same crown with run #243's size TILT
    # (xgb/tier -- picked by the standing pre-registered tilt metric, pre-lockbox
    # recovery). A tilt takes EVERY trade the raw crown takes and only resizes it, so
    # NOISE_SBS_V90 is again the exact control. FORWARD EVIDENCE ONLY: the tilt
    # mechanism was pre-registered dead for backtest adoption on 2026-08-10 (0/12).
    {"key": "NOISE_SBS_V90_T", "strategy": "NOISE_1_0.py", "instrument": "NQ",
     "timeframe": "5m", "session": "rth", "params": NOISE_243_SBS_V90,
     "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "gate": NOISE_243_TILT, "history_from": _GATE_HISTORY_FROM,
     "source": LEG_SOURCE["NOISE_SBS_V90_T"]},

    # ── gated legs (api/paper_gate.py) ──────────────────────────────────────────
    # ORB_H needs no companion: the raw ORB leg above already runs the identical
    # strategy file and params with the gate off, so it IS the matched control.
    {"key": "ORB_H", "strategy": "ORB_3_6_C2.py", "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "params": ORB_234, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "gate": ORB_GATE, "history_from": _GATE_HISTORY_FROM,
     "source": LEG_SOURCE["ORB_H"]},
    # NOISE_H runs DIFFERENT params from the raw NOISE leg, so it carries its own control:
    # emit_ungated_as publishes the same backtest's pre-gate trades as leg NOISE_225 at no
    # extra cost. One backtest, two rows, nothing confounded.
    {"key": "NOISE_H", "strategy": "NOISE_1_0.py", "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "params": NOISE_225, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "gate": NOISE_GATE, "history_from": _GATE_HISTORY_FROM,
     "emit_ungated_as": "NOISE_225", "source": LEG_SOURCE["NOISE_H"]},
    # Owner's pick. Shares NOISE_225 as its control (already emitted by NOISE_H above), so both
    # NOISE gates are scored against the SAME raw baseline and therefore against each other.
    # Costs ~178s/day -- an rf walk over 5,633 trades is the most expensive leg on the board.
    {"key": "NOISE_H_RF", "strategy": "NOISE_1_0.py", "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "params": NOISE_225, "cost_pts": _NQ_COST_PTS, "mult": _NQ_MULT,
     "gate": NOISE_GATE_RF, "history_from": _GATE_HISTORY_FROM,
     "source": LEG_SOURCE["NOISE_H_RF"]},
]

# ── Layer 1: the NT demo account whose fills we mirror into the daily report ────
PAPER_LIVE_ACCOUNT = "DEMO7240108"

# Are the NinjaScript strategies actually enabled on charts? While this is False the
# Layer 3 reconcile does not treat "the engine signalled and the demo did not trade" as
# a divergence, because that is exactly what is expected.
#
# TRUE since 2026-08-13. PAPER_TRADING.md said the strategies were not enabled; the fills
# say otherwise. DEMO7240108 has been trading NQ on exact 5-minute boundaries with zero
# commission and sequential order ids since 2026-08-11 - machine-generated, on the 5m
# chart, which is NOISE. Nobody updated the doc when the chart was enabled, which is
# precisely the kind of drift this reconcile exists to catch.
NT_STRATEGIES_ENABLED = True
_FILLS_CSV = r"C:\EdgeLog\fills.csv"
_INST_MULT = {"NQ": 20.0, "MNQ": 2.0, "ES": 50.0, "MES": 5.0}

# ── fresh 10s tick source ────────────────────────────────────────────────────────
_ADDON_10S = r"C:\EdgeLog\ohlc_addon\NQ_10s.csv"
_FALLBACK_10S = r"C:\EdgeLog\ohlc\NQ_10s.csv"

_WARMUP_DAYS = 150          # calendar days before "today" (ema_len=390 on 1m headroom)
_STALE_MINUTES = 30         # 10s file is "stale" if its last bar is this far before close
_CHECK_INTERVAL_S = 60.0    # internal throttle for maybe_run_eod


def _log(msg):
    print(f"[paper] {msg}")


# ── fresh-tail builder ───────────────────────────────────────────────────────────
def _ticks_path():
    """Pick the FRESHEST 10s file, not merely the first one that exists.

    This preferred _ADDON_10S purely on existence, which is how a stale file won:
    the NinjaScript OHLC export stopped writing on 2026-08-13 (it only runs while its
    chart is open, and NinjaTrader was restarted repeatedly), so the addon file froze a
    day behind while the watch-folder copy at _FALLBACK_10S kept up to 2026-08-14. The
    runner went on reading the frozen file and every leg reported "10s data looks stale"
    -- with a fresher file sitting right next to it. Compare last-modified and take the
    newer; if only one exists that one wins by default.
    """
    have = [p for p in (_ADDON_10S, _FALLBACK_10S) if os.path.exists(p)]
    if not have:
        return _ADDON_10S          # canonical path for the "missing" warning
    if len(have) == 1:
        return have[0]
    try:
        return max(have, key=os.path.getmtime)
    except OSError:
        return have[0]


def _load_fresh_ticks():
    """Read the live 10s OHLC+delta CSV. Returns (DataFrame|None, path)."""
    path = _ticks_path()
    if not os.path.exists(path):
        return None, path
    try:
        df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close", "volume"])
    except Exception as e:
        _log(f"failed reading {path}: {type(e).__name__}: {e}")
        return None, path
    if df.empty:
        return None, path
    df["time"] = df["time"].astype("int64")
    return df, path


def _resample(df, tf_minutes):
    """10s rows -> OHLCV bars of tf_minutes, bar time = bar-start unix. Bars with no
    rows are simply absent (groupby only emits buckets that have data)."""
    sec = int(tf_minutes) * 60
    key = (df["time"] // sec) * sec
    g = df.groupby(key, sort=True)
    out = pd.DataFrame({
        "time": g["open"].first().index.values,
        "open": g["open"].first().values,
        "high": g["high"].max().values,
        "low": g["low"].min().values,
        "close": g["close"].last().values,
        "volume": g["volume"].sum().values,
    })
    return out


def _filter_rth(bars, session="rth"):
    """Trim the fresh tail to a leg's own session.

    RTH keeps 09:30-16:00 New York; ETH keeps everything. That distinction is the whole
    point of an ETH leg: it exists to trade the overnight tape, so applying the day window
    to it would silently delete the very bars it was validated on and leave a leg claiming
    to be 24-hour while only ever seeing the day session.

    Signature keeps the default so the other callers (api/bars.py, api/gate_live.py) are
    unaffected -- they are RTH by construction.

    Returns (filtered bars DataFrame, tz-aware US/Eastern Timestamp Series aligned to it)."""
    et = pd.to_datetime(bars["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    if str(session).lower() != "rth":
        return bars.reset_index(drop=True), et.reset_index(drop=True)
    tod = et.dt.hour * 60 + et.dt.minute
    mask = (tod >= 9 * 60 + 30) & (tod < 16 * 60)
    return bars[mask].reset_index(drop=True), et[mask].reset_index(drop=True)


def _append_fresh(arrays, bars):
    """Append fresh bars (DataFrame: time/open/high/low/close/volume) to a loaded
    master `arrays` dict, IN MEMORY ONLY. Returns (new arrays dict, n bars appended)."""
    if bars is None or bars.empty:
        return arrays, 0
    new_index = pd.DatetimeIndex(
        pd.to_datetime(bars["time"], unit="s", utc=True).dt.tz_convert("US/Eastern"))
    combined_index = arrays["index"].append(new_index)
    o = np.concatenate([np.asarray(arrays["open"], float), bars["open"].values.astype(float)])
    h = np.concatenate([np.asarray(arrays["high"], float), bars["high"].values.astype(float)])
    l = np.concatenate([np.asarray(arrays["low"], float), bars["low"].values.astype(float)])
    c = np.concatenate([np.asarray(arrays["close"], float), bars["close"].values.astype(float)])
    v_old = arrays.get("volume")
    if v_old is not None:
        v = np.concatenate([np.asarray(v_old, float), bars["volume"].values.astype(float)])
    else:
        v = None
    day_id = pd.factorize(pd.Series(combined_index).dt.date)[0].astype("int64")
    out = dict(arrays)
    out.update(open=o, high=h, low=l, close=c, volume=v, day_id=day_id, index=combined_index)
    return out, len(bars)


# ── trade conversion (mirrors augur_engine/reconcile.py edgelog_blotter) ─────────
def _extract_trades(leg, arrays, sized, key=None):
    """(trade tuple, size multiplier) pairs -> plain dicts.

    `sized` is a list of ((entry_bar, exit_bar, pnl_pts, side, entry_px), size). Size is
    1.0 for every raw leg and for a gate running in "cut" mode; only a HYBRID gate ever
    hands back anything else. It scales the money, never the prices: `pnl_usd` is the
    sized result (what the leg actually earns) while `pnl_pts` stays the one-lot move, so
    a sized row can still be reconciled against a chart tick for tick.
    """
    mult = float(leg.get("mult") or 20.0)
    idx = arrays["index"]
    O = arrays["open"]
    out = []
    for t, size in sized:
        eb, xb, pnl_pts = int(t[0]), int(t[1]), float(t[2])
        side = int(t[3]) if len(t) >= 4 else 0
        entry_px = float(t[4]) if len(t) >= 5 else float(O[eb])
        exit_px = (entry_px + side * pnl_pts) if side else None
        entry_dt = pd.Timestamp(idx[eb])
        exit_dt = pd.Timestamp(idx[xb])
        out.append({
            "leg": key or leg["key"], "strategy": leg["strategy"], "side": side,
            "entry_dt": entry_dt, "exit_dt": exit_dt,
            "entry_px": entry_px, "exit_px": exit_px,
            "size": float(size),
            "pnl_pts": pnl_pts, "pnl_usd": pnl_pts * mult * float(size),
        })
    return out


# ── per-leg shadow run ────────────────────────────────────────────────────────────
def run_shadow(leg, today):
    """Re-run one crowned leg on master + fresh-tail data. Never raises.

    today: a date (or anything pandas.Timestamp can parse) — the trading day this
    shadow run is being produced for; only used to size the warm-up window and the
    staleness check (today's 16:00 ET close).

    Returns {trades, ungated_trades, gate, bars_appended, data_fresh_thru, warnings}.
    `trades` only includes trades whose entry date is >= PAPER_START. `ungated_trades` is
    populated only for a gated leg that declares `emit_ungated_as` (its matched control),
    and `gate` is the gate summary or None.
    """
    warnings = []
    trades_out = []
    ungated_out = []
    gate_info = None
    bars_appended = 0
    data_fresh_thru = None
    ran_ok = False
    try:
        today_d = pd.Timestamp(today).date()

        master = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"))
        if master is None:
            warnings.append(
                f"no master for {leg['instrument']} {leg['timeframe']} {leg.get('session')}")
            return {"trades": [], "ungated_trades": [], "gate": None, "bars_appended": 0,
                   "data_fresh_thru": None, "warnings": warnings, "ran_ok": False}

        # A gated leg loads its FULL history (history_from) instead of the 150-day warm-up:
        # the gate model must be the one the validate crowned, and a model trained on 150
        # days is a different model. Raw legs are unaffected.
        date_from = (leg.get("history_from")
                     or (pd.Timestamp(today_d) - pd.Timedelta(days=_WARMUP_DAYS)).strftime("%Y-%m-%d"))
        arrays = load_master_arrays(master, date_from=date_from, date_to=None)

        ticks_df, ticks_path = _load_fresh_ticks()
        if ticks_df is None:
            warnings.append(f"10s data file missing/empty: {ticks_path}")
        else:
            last_tick_unix = int(ticks_df["time"].iloc[-1])
            data_fresh_thru = last_tick_unix
            close_et = pd.Timestamp(f"{today_d} 16:00:00", tz="US/Eastern")
            last_tick_et = pd.Timestamp(last_tick_unix, unit="s", tz="UTC").tz_convert("US/Eastern")
            if last_tick_et < close_et - pd.Timedelta(minutes=_STALE_MINUTES):
                warnings.append(
                    f"10s data looks stale: last bar {last_tick_et} "
                    f"(more than {_STALE_MINUTES}m before {close_et} close)")

            tf_min = 5 if str(leg["timeframe"]).lower().startswith("5") else 1
            bars = _resample(ticks_df, tf_min)
            bars, bars_et = _filter_rth(bars, leg.get("session", "rth"))
            last_master_time = arrays["index"][-1] if len(arrays["index"]) else None
            if last_master_time is not None and len(bars):
                keep = (bars_et > last_master_time).values
                bars = bars[keep].reset_index(drop=True)
            if len(bars):
                arrays, bars_appended = _append_fresh(arrays, bars)

        if bars_appended == 0:
            warnings.append("zero fresh bars appended")

        res = run_backtest(leg["strategy"], arrays=arrays, params=leg["params"],
                           cost_pts=leg.get("cost_pts", 0.0), return_trades=True)
        raw = list((res or {}).get("trades") or [])
        paper_start = pd.Timestamp(PAPER_START).date()

        if leg.get("gate"):
            from . import paper_gate
            t_gate = time.time()
            sized, gate_info = paper_gate.apply_gate(arrays, raw, leg["gate"])
            gate_info["seconds"] = round(time.time() - t_gate, 1)
            for w in (gate_info.get("warnings") or []):
                warnings.append(f"gate: {w}")
            # The matched RAW control, free: same backtest, same bars, gate off. Only
            # emitted when the leg asks for it (ORB_H's control is the standalone ORB leg).
            if leg.get("emit_ungated_as"):
                ung = _extract_trades(leg, arrays, [(t, 1.0) for t in raw],
                                      key=leg["emit_ungated_as"])
                ungated_out = [t for t in ung if t["entry_dt"].date() >= paper_start]
        else:
            sized = [(t, 1.0) for t in raw]

        trades = _extract_trades(leg, arrays, sized)
        trades_out = [t for t in trades if t["entry_dt"].date() >= paper_start]
        ran_ok = True          # the backtest completed; its trade list is authoritative
    except Exception as e:
        msg = f"exception in run_shadow({leg.get('key')}): {type(e).__name__}: {e}"
        warnings.append(msg)
        _log(msg)

    return {"trades": trades_out, "ungated_trades": ungated_out, "gate": gate_info,
           "bars_appended": bars_appended, "data_fresh_thru": data_fresh_thru,
           "warnings": warnings, "ran_ok": ran_ok}


# ── Layer 1: today's demo-account fills, mirrored into the daily report ──────────
def collect_live_fills(target_date):
    """Read C:\\EdgeLog\\fills.csv and return the PAPER demo account's fills for
    target_date, plus a best-effort day-net. Attribution to individual strategies
    is deliberately NOT attempted here (fills carry no strategy name — that's the
    reconcile layer's job, by time+price). Never raises."""
    out = {"account": PAPER_LIVE_ACCOUNT, "n_fills": 0, "fills": [],
           "day_net_usd": None, "flat_eod": True, "warnings": []}
    try:
        if not os.path.exists(_FILLS_CSV):
            out["warnings"].append("fills.csv missing")
            return out
        date_s = target_date.isoformat()
        pos = {}      # instrument root -> signed qty
        cash = {}     # instrument root -> signed cash flow in points*qty*mult
        with open(_FILLS_CSV, encoding="utf-8-sig") as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 9 or parts[2] != PAPER_LIVE_ACCOUNT:
                    continue
                if not parts[1].startswith(date_s):
                    continue
                inst = parts[3]
                root = inst.split(" ")[0].upper()
                action = parts[4].upper()
                try:
                    qty = float(parts[5]); px = float(parts[6])
                except ValueError:
                    continue
                side = 1 if action.startswith("BUY") else -1
                mult = _INST_MULT.get(root, 1.0)
                pos[root] = pos.get(root, 0.0) + side * qty
                cash[root] = cash.get(root, 0.0) - side * qty * px * mult
                out["fills"].append({"time": parts[1], "instrument": inst,
                                     "action": action, "qty": qty, "price": px})
        out["n_fills"] = len(out["fills"])
        open_roots = [r for r, q in pos.items() if abs(q) > 1e-9]
        out["flat_eod"] = not open_roots
        if out["n_fills"]:
            if open_roots:
                out["warnings"].append(
                    "position still open in " + ",".join(open_roots)
                    + " - day net excludes it")
                out["day_net_usd"] = sum(v for r, v in cash.items() if r not in open_roots)
            else:
                out["day_net_usd"] = sum(cash.values())
    except Exception as e:
        out["warnings"].append(f"live-fills read failed: {type(e).__name__}: {e}")
    return out


# ── once-a-day EOD driver ─────────────────────────────────────────────────────────
_last_check_ts = 0.0


def _last_completed_trading_day(et_now, force=False):
    """The most recent trading day whose EOD (16:10 ET) has passed. With force=True,
    returns today's date regardless of time-of-day (manual/smoke-test trigger)."""
    d = et_now.date()
    if force:
        return d
    if et_now.weekday() < 5 and (et_now.hour, et_now.minute) >= (16, 10):
        candidate = d
    else:
        candidate = d - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _et_now():
    try:
        from zoneinfo import ZoneInfo
        return pd.Timestamp.now(tz=ZoneInfo("America/New_York"))
    except Exception:
        return pd.Timestamp.now(tz="US/Eastern")


def maybe_run_eod(q, *, force=False, dry_run=False):
    """Cheap, throttled, exception-proof hook for the runner's watch loop. Actually
    runs the shadow legs at most once per trading day, after 16:10 ET, skipping
    weekends — plus a startup catch-up if the last run is older than the most recent
    completed trading day. No-ops in well under 1ms outside its 60s check window."""
    global _last_check_ts
    now_wall = time.time()
    if not force and (now_wall - _last_check_ts) < _CHECK_INTERVAL_S:
        return None
    _last_check_ts = now_wall
    try:
        return _run_eod_check(q, force=force, dry_run=dry_run)
    except Exception as e:
        _log(f"maybe_run_eod error: {type(e).__name__}: {e}")
        return None


def _run_eod_check(q, *, force=False, dry_run=False):
    et_now = _et_now()
    # No weekday/time-of-day early return here: _last_completed_trading_day already
    # excludes today until 16:10 ET has passed, and the per-uid last_run_date guard
    # below makes the call a no-op when that day was run. This is what lets a Monday-
    # morning restart still catch up a Friday the PC was off for at Friday's close.
    target_date = _last_completed_trading_day(et_now, force=force)
    target_date_s = target_date.isoformat()

    reports = {}
    for uid in list(getattr(q, "allow", None) or []):
        try:
            already_ran = False
            if not force and not dry_run:
                state = _get_state(q.db, uid)
                last_run = (state or {}).get("last_run_date")
                if last_run and str(last_run) >= target_date_s:
                    already_ran = True
            if already_ran:
                continue

            report = _run_one_uid(q, uid, target_date, dry_run=dry_run)
            reports[uid] = report

            if not dry_run:
                _set_state(q.db, uid, {"last_run_date": target_date_s,
                                       "paper_start": PAPER_START})
        except Exception as e:
            _log(f"uid {uid} skipped: {type(e).__name__}: {e}")
    return {"date": target_date_s, "reports": reports}


def _get_state(db, uid):
    try:
        doc = db.collection("users").document(uid).collection("meta").document("paper_state").get()
        return doc.to_dict() if doc.exists else None
    except Exception:
        return None


def _set_state(db, uid, patch):
    try:
        db.collection("users").document(uid).collection("meta").document("paper_state").set(
            patch, merge=True)
    except Exception as e:
        _log(f"state write failed for uid: {type(e).__name__}: {e}")


def _run_one_uid(q, uid, target_date, *, dry_run=False):
    """Run both legs for one uid, upsert trades + write the daily report doc.
    Returns the report dict (also written to Firestore unless dry_run)."""
    leg_reports = {}
    total_pnl = 0.0
    batch = None
    pending = 0
    firestore = None
    if not dry_run:
        from firebase_admin import firestore as _fs
        firestore = _fs
        batch = q.db.batch()

    def _emit(leg, key, trades):
        """Upsert one leg's trade docs and return (trade_ids, todays_trades, pnl).

        Shared by a leg and its companion control row (a gated leg's `emit_ungated_as`),
        so both are written by identical code -- the point of a matched control is that
        nothing differs except the one thing under test.
        """
        nonlocal batch, pending
        trade_ids = []
        todays_trades = []      # the trade dicts behind trade_ids, for Layer 3
        leg_pnl = 0.0
        for t in trades:
            entry_unix = int(t["entry_dt"].timestamp())
            exit_unix = int(t["exit_dt"].timestamp())
            doc_id = f"pt_{key}_{entry_unix}"
            # run_shadow re-scans the WHOLE window since PAPER_START every day, so this
            # loop sees every trade ever, not just today's. Two consequences, both handled
            # here (bug found 2026-08-12: ORB's single Aug-11 trade was being re-reported
            # as a fresh signal each day, and every trade carried the RUN's date, which
            # collapsed the cumulative curve onto one x-point):
            #   • the trade doc is stamped with the TRADE's own date (upsert is idempotent
            #     on doc_id, so re-scanning simply refreshes it), and
            #   • the daily report counts only trades that actually happened THAT day.
            t_date = t["entry_dt"].date()
            is_today = (t_date == target_date)
            # Did this trade happen while this config was actually on the board?
            _lf = LEG_LIVE_FROM.get(key)
            is_backfill = bool(_lf and t_date < pd.Timestamp(_lf).date())
            if is_today:
                trade_ids.append(doc_id)
                todays_trades.append({
                    "side": t["side"], "entryIso": t["entry_dt"].isoformat(),
                    "entry_px": t["entry_px"], "exit_px": t["exit_px"],
                    "pnl_usd": t["pnl_usd"],
                    # SIZE RIDES ALONG (2026-08-26). It was being dropped here, so the
                    # reconcile could never answer "did the contracts that reached the
                    # broker match the size the strategy intended" -- the one question
                    # that catches a gate whose sizing dies somewhere in the handoff.
                    # _extract_trades already carries it; only this projection lost it.
                    "size": t.get("size"),
                })
                leg_pnl += t["pnl_usd"]
            if not dry_run:
                doc = json_safe({
                    "leg": key, "strategy": leg["strategy"],
                    "side": t["side"], "entryTime": entry_unix, "exitTime": exit_unix,
                    "entryIso": t["entry_dt"].isoformat(), "exitIso": t["exit_dt"].isoformat(),
                    "entry_px": t["entry_px"], "exit_px": t["exit_px"],
                    "size": t.get("size", 1.0),
                    "pnl_pts": t["pnl_pts"], "pnl_usd": t["pnl_usd"],
                    # backfill = this config was not on the board when the trade happened,
                    # so the row is a backtest result, not something forward-observed.
                    "backfill": is_backfill, "live_from": _lf,
                    "layer": "shadow", "run_date": t_date.isoformat(),
                    "flags": leg.get("flags") or [],
                })
                doc["createdAt"] = firestore.SERVER_TIMESTAMP
                batch.set(q.db.collection("users").document(uid)
                         .collection("paper_trades").document(doc_id), doc, merge=True)
                pending += 1
                if pending >= 400:
                    batch.commit(); batch = q.db.batch(); pending = 0
        return trade_ids, todays_trades, leg_pnl

    def _prune(key, trades, ran_ok):
        """Delete trade docs this leg no longer produces. Returns the number removed.

        WHY (found 2026-08-16). Trade docs are upserted by doc_id, which refreshes a trade
        that still exists but can never remove one that stopped existing. So when the ORB
        leg was swapped off the retired look-ahead #125 config on 2026-08-16, its four
        ORB_3_0.py trades stayed in the collection and kept being drawn: the leg read
        "6 trades, -$566" when its actual config produced two. The curve was a blend of two
        different strategies, and every comparison against it was meaningless -- which
        matters far more now that gated legs are scored AGAINST their raw control.

        Bounded and guarded on purpose:
          * only runs when the backtest actually COMPLETED (ran_ok) -- a leg that failed to
            load its master returns no trades, and pruning on that would delete real history;
          * only touches docs at/after PAPER_START, which is the only span run_shadow
            rebuilds, so nothing outside the forward test is reachable;
          * keys on ENTRY time, which is stable -- only an in-progress trade's EXIT moves as
            new bars arrive.
        """
        nonlocal batch, pending
        if dry_run or not ran_ok:
            return 0
        keep = {int(t["entry_dt"].timestamp()) for t in trades}
        start_unix = int(pd.Timestamp(PAPER_START).timestamp())
        removed = 0
        try:
            docs = (q.db.collection("users").document(uid).collection("paper_trades")
                    .where("leg", "==", key).stream())
            for d in docs:
                t = d.to_dict() or {}
                et = t.get("entryTime")
                if et is None or int(et) < start_unix or int(et) in keep:
                    continue
                batch.delete(d.reference)
                removed += 1
                pending += 1
                if pending >= 400:
                    batch.commit(); batch = q.db.batch(); pending = 0
                _log(f"uid={uid} leg={key} PRUNED stale trade {d.id} "
                     f"({t.get('entryIso')}, strategy={t.get('strategy')}) - the current "
                     f"config no longer produces it")
        except Exception as e:
            _log(f"uid={uid} leg={key} prune skipped: {type(e).__name__}: {e}")
        return removed

    for leg in PAPER_LEGS:
        r = run_shadow(leg, target_date)

        # A gated leg's matched control is written FIRST so the board reads control-then-
        # test, and so a failure writing the test never leaves the control missing.
        _companion = leg.get("emit_ungated_as")
        if _companion and r.get("ungated_trades"):
            c_ids, c_today, c_pnl = _emit(leg, _companion, r["ungated_trades"])
            c_pruned = _prune(_companion, r["ungated_trades"], r.get("ran_ok"))
            leg_reports[_companion] = {
                "pruned": c_pruned,
                "n_signals": len(c_ids), "n_since_start": len(r["ungated_trades"]),
                "trade_ids": c_ids, "pnl_usd": c_pnl, "_trades": c_today,
                "bars_appended": r["bars_appended"], "data_fresh_thru": r["data_fresh_thru"],
                "warnings": [], "flags": leg.get("flags") or [],
                "source": LEG_SOURCE.get(_companion) or {},
                "params": dict(leg.get("params") or {}),
                "strategy_file": leg["strategy"], "timeframe": leg.get("timeframe"),
                "gate": None, "control_for": leg["key"],
            }
            total_pnl += c_pnl

        trade_ids, todays_trades, leg_pnl = _emit(leg, leg["key"], r["trades"])
        n_pruned = _prune(leg["key"], r["trades"], r.get("ran_ok"))
        leg_reports[leg["key"]] = {
            "pruned": n_pruned,
            # n_signals / pnl_usd are THIS DAY only; n_since_start is the running total
            # so the cumulative view is still available without conflating the two.
            "n_signals": len(trade_ids), "n_since_start": len(r["trades"]),
            "trade_ids": trade_ids, "pnl_usd": leg_pnl,
            # Layer 3 reads this and strips it before the doc is written - it is the
            # same data as trade_ids, just resolved, and Firestore does not need both.
            "_trades": todays_trades,
            "bars_appended": r["bars_appended"], "data_fresh_thru": r["data_fresh_thru"],
            "warnings": r["warnings"], "flags": leg.get("flags") or [],
            # Provenance travels WITH the numbers (owner 2026-08-15: "i dont know which
            # config or past run it got it from"). Writing both the source block and the
            # exact params means a report is self-describing forever -- you can read an
            # old report and know precisely which config produced it, even after this
            # file has moved on to a different one.
            "source": leg.get("source") or {},
            "params": dict(leg.get("params") or {}),
            "strategy_file": leg["strategy"], "timeframe": leg.get("timeframe"),
            # The gate's own summary (model, cut-off, how many it refused, average size
            # it traded) rides with the leg for the same reason the params do: so a row
            # on the board can always answer "what exactly produced this number".
            "gate": r.get("gate"),
            "control_leg": _companion or ("ORB" if leg["key"] == "ORB_H" else None),
        }
        total_pnl += leg_pnl
        if r["warnings"]:
            for w in r["warnings"]:
                _log(f"uid={uid} leg={leg['key']} {w}")

    if not dry_run and pending:
        batch.commit()

    # blend stays the owner's 1:1 ORB+ENGU-Q baseline — NOISE is reported as its own
    # leg but does NOT join the blend until the owner adds it to the book.
    blend_pnl = sum(leg_reports[k]["pnl_usd"] for k in ("ORB", "ENGUQ") if k in leg_reports)
    report = {
        "legs": leg_reports,
        "blend": {"pnl_usd": blend_pnl},
        "live": collect_live_fills(target_date),   # Layer 1: NT demo fills, unattributed
        "status": "runner_done",
        "run_date": target_date.isoformat(),
    }
    # Layer 3: three-way reconcile (api/paper_reconcile.py). live_expected reflects
    # whether the NinjaScript strategies are actually enabled on charts - while they are
    # not, "shadow signal with no live fill" is the designed state, and reporting it as a
    # divergence every single day is how a status field becomes wallpaper.
    try:
        from . import paper_reconcile
        report["reconcile"] = paper_reconcile.run(
            target_date, report, live_expected=NT_STRATEGIES_ENABLED)
        _v = report["reconcile"].get("verdict") or {}
        for _p in (_v.get("problems") or []):
            _log(f"uid={uid} RECONCILE {target_date.isoformat()}: {_p}")
    except Exception as e:
        report["reconcile"] = {"ok": None, "error": f"{type(e).__name__}: {e}"}

    # Layer 4: did the LIVE ML gate do its job today? (api/gate_audit.py). The reconcile
    # above asks whether the DEMO took the trades the engine expected; this asks the
    # question nobody could answer on 2026-08-24 - was the gate even consulted, and did
    # its answer survive the trip into the order. Same containment as the reconcile: a
    # reader that breaks must cost the report nothing. `report` is passed only so the
    # audit can set the live gate beside the shadow gate's own numbers for the day.
    try:
        from . import gate_audit
        report["gate_live"] = gate_audit.audit(target_date.isoformat(), report=report)
        for _p in (report["gate_live"].get("complaints") or []):
            _log(f"uid={uid} GATE {target_date.isoformat()}: {_p}")
    except Exception as e:
        report["gate_live"] = {"ok": None, "error": f"{type(e).__name__}: {e}"}

    # _trades was only ever a hand-off to the reconcile; it is redundant with trade_ids
    # and would bloat every report doc against the 1 MiB cap.
    for _blk in report["legs"].values():
        _blk.pop("_trades", None)

    if not dry_run:
        report_doc = json_safe(dict(report))
        report_doc["generatedAt"] = firestore.SERVER_TIMESTAMP
        q.db.collection("users").document(uid).collection("paper_reports").document(
            target_date.isoformat()).set(report_doc, merge=True)
        _leg_summary = ", ".join(f"{k}:{v['n_signals']}" for k, v in leg_reports.items())
        _log(f"uid={uid} {target_date.isoformat()}: blend ${total_pnl:,.0f} ({_leg_summary})")

    return report
