"""api/cloud_signal.py — cloud SIGNAL ENGINE for the three crowned NQ strategies,
running on QQQ share bars, meant to eventually feed a Webull execution adapter.

NO ORDER CODE OF ANY KIND. This module never imports a broker SDK, never places an
order, never touches a live/paper account. It reads bars, runs the same engine the
rest of this repo already uses (augur_engine.engine.run_backtest), diffs the
resulting trade list against what it last saw, and writes SIGNAL events (ENTRY /
EXIT) to a CSV ledger. Nothing downstream of this file exists yet — a future
execution module reads signals.csv (or a Firestore mirror of it) and decides what to
do about them. That is a DIFFERENT module, not a flag flip in this one.

WHY THIS EXISTS. tools/qqq_paper.py already replays the three crowned NQ strategies
on QQQ bars and writes a paper blotter — it is the model/backtest half. This module
is the forward-looking SIGNAL half: it is built to run continuously (or be replayed
bar-by-bar) and emit discrete, idempotent, timestamped events an order-placing layer
can consume one at a time, rather than a blotter you re-read start to finish.

PORTABLE PATHS. EDGELOG_HOME (default C:\\EdgeLog on Windows, ~/edgelog elsewhere)
is the root. Bar cache lives under <home>/ohlc/ (QQQ_1m.csv / QQQ_5m.csv — on the
owner's machine, with EDGELOG_HOME unset, this IS tools/qqq_paper.py's own
C:\\EdgeLog\\ohlc cache, same files, no duplication). Engine state lives under
<home>/cloud_signal/ (signals.csv, state.json, heartbeat.json).

DATA REUSE. The yfinance fetch/chunking (`_fetch_yf`) and the epoch-schema /
RTH-array builder (`_to_epoch_frame`, `build_arrays`) are IMPORTED from
tools/qqq_paper.py, not reimplemented — those functions are pure (no path constants
baked in) so reuse is a straight import. Only the on-disk CACHE READ/WRITE path
differs (this module writes under EDGELOG_HOME, qqq_paper.py always writes under
literal C:\\EdgeLog\\ohlc) — qqq_paper.py's own behaviour is completely unchanged by
this file's existence. The rename-into-place retry (`qp._replace_with_retry`, added
2026-09-14) is reused the same way: ONE helper backs every risky `os.replace` in both
files, because both write the very same shared OHLC cache and Windows refuses that
rename outright while any reader -- including the OTHER writer's own read of the same
file -- still has it open.

THE CROWN (LIVE) LEGS (as of 2026-10-09; NOISE swapped by OWNER DECISION 2026-09-23,
ENGU-Q back on the order-placing book by OWNER DECISION 2026-10-09 -- see ENGUQ_335 below):
  ORB_R6      run #314, ORB_3_6_R6.py, api.paper.ORB_314, 5m RTH, no gate.
  NOISE_382   run #382, NOISE_1_8_CT304.py, params below, 5m RTH, no gate.
              (repointed 2026-09-24 -- run #382 is the #304 crown's own core, written out
              literally inside that file, plus the validated hourly-compression SIZE tilt
              (tilt_mult 2.0, gate_tf_min 30, gate_len 16, gate_ratio 1.15 -- all inside
              that file's own FENCED admissible set). #304 stays in api/qqq_exec.py's
              ENGINE_LEG_MAP (-> the same "NOISE" exec leg) purely so an in-flight trade
              id or an old signals.csv row keeps resolving; it is GONE from CROWN_LEGS
              itself, not kept alongside. api/paper.py's OWN "NOISE_304" leg (the
              NinjaTrader PAPER board, api.paper.NOISE_304_NBHD) is a DIFFERENT book and
              is UNCHANGED and unrelated to this one.)
  ENGUQ_335   run #335, ENGUQ_1M_ETH_R2_1_0.py, api.paper.ENGUQ_335, 1m **ETH**, no gate.
              LIVE AGAIN SINCE 2026-10-09 (OWNER DECISION via MANAGER #102, reversing the
              2026-09-28 move to the shadow legs). It was taken off the book because every
              ENGU-Q Webull order had been closed by qqq_exec's 15:59 end-of-day flatten, never
              by the strategy's own multi-day exit; the owner accepts QQQ's RTH-only tape
              ("idc if its not getting 24hr data"), and since the same day (owner GO
              2026-10-09, MANAGER #106) the book HOLDS ENGU-Q OVERNIGHT: qqq_exec's 15:59
              flat_by flatten sells the other legs but keeps the ENGU-Q lot (qqq_exec
              HOLD_OVERNIGHT_LEGS), which sells on this leg's own EXIT on a later day -- the
              exit of an emitted ENTRY fires on any later day, also when first seen after
              the close (EOD SETTLE). qqq_exec only opens it inside its session window.
              Same cfg it had live before 2026-09-28 (commit
              fb0f32f0's parent: phantom_safe, max_entry_age_sec, no eod_flat) plus
              "live_since" -- it STARTS FLAT (see LIVE SINCE above _apply_live_since: its old
              live state is discarded and it cold-starts, so no catch-up ENTRY and no EXIT
              for a trade the book no longer holds). api/qqq_exec.py maps it to "ENGUQ".

SHADOW LEGS (OWNER DECISION 2026-09-28, via MANAGER) -- SHADOW_LEGS below. Same engine,
same bars, NO orders: they write only to their own store, <home>/cloud_signal/shadow/
(state.json + signals.csv -- see shadow_paths), which api/qqq_exec.py never reads for
orders (its one read, since 2026-10-09, is the display-only "shadow_trades" block of its
status doc -- _build_shadow_trades), so nothing they do can reach Webull, the live legs,
their caps or their state. They exist
so the Custom ML chat can score would-be trades (docs/PREREG_noise_shadow_forward_
2026-09-28.md; tools/shadow_legs_report.py reads the ledger). Run by run_shadow_step()
from cloud_signal_thread, after the live step, on fetch ticks only.
  NOISE_422_PLAIN   run #422, NOISE_1_8_CT304H.py, NOISE_422_PARAMS, 5m RTH, no KEEL.
  NOISE_422_FIXED   the same + KEEL v12's fixed tilts, no model (research arm A3).
  NOISE_422_KEEL    the same + KEEL v12 learned, its own nightly state (NOISE_422_KEEL_v12_*).
  DIP_424K    run #424 ("KEEL DIP"), NQDIP_1_1.py, DIP_424_PARAMS, asset="ETF", + KEEL v12
              learned (its own nightly state, trained on #424's NQ trades -- keel["train"]).
  DIP_424F    the same at a constant size DIP_424_CONST_SIZE = 1.245 (KEEL's average size over
              #424's walk-forward trades; MANAGER #108 GO 2026-10-09).
              Both run through api/dip_live.py (cfg["runner"] = DIP_RUNNER), never through
              run_leg_trades: the file returns 6-field trades with the P&L in dollars, reports
              a trade only once it exits, holds up to seven positions at once (one per dip
              mechanism -> a per-slot trade id) and decides on the DAILY close, filling at the
              next session's 09:30 open -- its daily series is QQQ_1d.csv history plus the 5m
              cache's own sessions. See that module's docstring.
  (ENGUQ_335 was the fourth shadow leg from 2026-09-28 to 2026-10-09, when it went back to
  CROWN_LEGS. Its shadow rows stay in the shadow ledger untouched -- tools/
  shadow_legs_report.py still lists them, as a leg found in the ledger -- and its record in
  the shadow state.json is simply no longer stepped.)

ENGINE LIMITATION, READ BEFORE TRUSTING THE ENGUQ_335 LEG. The ENGU-Q family crown
moved to an ETH (23-hour NQ futures) config on 2026-09-08. yfinance QQQ bars (this
module, exactly like tools/qqq_paper.py, pulls prepost=False) only ever cover the
09:30-16:00 ET regular session — there is no equivalent of NQ's overnight Globex tape
for a cash equity. Running ENGUQ_335's ETH-fit parameters on an RTH-only splice is a
KNOWN mismatch, not a hidden one:
  1. `regime_len` in ENGUQ_1M_ETH_R2_1_0.py's parent file counts regime blocks as
     `regime_len * 390` bars (see that file's own frozen unit-notice comment) — 390
     is the RTH bar count, so on the ETH tape it trained on, regime_len=10 means
     ~3.6 CALENDAR days of history; spliced onto QQQ's RTH-only bars (390 bars really
     IS one session here) the same knob instead reads as 10 SESSIONS. The regime
     filter fires on a different real-world lookback than the one it was validated on.
  2. The strategy file hardcodes an absolute `risk < max(0.25, 0.5): skip trade`
     floor (a flat $0.50 price distance) and an ATR floor of 0.25 inside the breakout
     test — both calibrated against NQ's ~$25,000 price level, where $0.50 is noise.
     Against a ~$700 QQQ share these floors bind far more often, silently gating out
     (or, depending on the local ATR, silently admitting) trades the crown's own
     validate never saw.
  This leg still RUNS (it does not raise) and is included below because the task is
  to signal the current crowns, not to invent a safer substitute unasked — but its
  signals should be read as exploratory, not evidence-backed, until this is fixed
  properly (an ETH-equivalent data source, or a from-scratch RTH re-validation of the
  file). tools/qqq_paper.py made the opposite call for its own ENGUQ leg (it
  deliberately keeps running the older RTH #149 variant rather than the ETH crown,
  for exactly this reason) — see that file's update note, 2026-09-08.

CLI
  python -m api.cloud_signal --replay YYYY-MM-DD   replay one cached session bar-by-
                                                     bar, print the signal ledger +
                                                     the NT-vs-QQQ comparison table.
                                                     ISOLATED: runs in a temp copy of
                                                     the bar cache with a cold state
                                                     and never writes the live ledger
  python -m api.cloud_signal --replay YYYY-MM-DD --live-paths
                                                     explicit opt-in: replay INTO the
                                                     live <home>/cloud_signal ledger +
                                                     state; refused while a live
                                                     writer's heartbeat is fresh
  python -m api.cloud_signal --once                 one live step() and exit. REFUSED
                                                     (exit code 2) while a live writer's
                                                     heartbeat is fresh -- the runner's
                                                     own parallel run, or another
                                                     --loop/--once -- naming the
                                                     heartbeat's age and path, so a
                                                     hand-run step can never become a
                                                     second writer of state.json /
                                                     signals.csv beside it
  python -m api.cloud_signal --loop                 step() every 20s during session
                                                     hours, sleep outside them. Same
                                                     fresh-heartbeat refusal as --once,
                                                     checked ONCE at startup before this
                                                     loop's own first heartbeat write
                                                     (never re-checked inside the loop --
                                                     it would see its own stamp)
"""
import argparse
import datetime as _dt
import inspect
import json
import logging as _logging
import math
import os
import shutil
import sys
import tempfile
import threading
import time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.engine import run_backtest as engine_run_backtest          # noqa: E402
from api import market_calendar                                             # noqa: E402
from api import trade_id as _trade_id                                       # noqa: E402
from api.paper import ORB_314, ENGUQ_335                                    # noqa: E402
import tools.qqq_paper as qp                                                # noqa: E402

TZ = qp.TZ                             # "US/Eastern" — same convention everywhere in this repo
RTH_OPEN = qp.RTH_OPEN
RTH_CLOSE = qp.RTH_CLOSE

# Bar must have fully closed at least this long before `now` before we act on it.
CLOSE_GRACE_SECONDS = 5

# Default rolling-window depth: "last N sessions" per the task spec. Actual depth used
# is always min(this, sessions available in the cache) — the cache today only holds
# ~25 sessions of 1m and ~77 of 5m, so this is a ceiling, not a promise of 60 real
# sessions of history. A LEG WHOSE STRATEGY DECLARES A LONGER LOOK-BACK GETS MORE THAN
# THIS -- see leg_warmup_sessions() below (WEBULL_PAPER_TODO.md item 12): this constant
# is only the floor every leg starts from, not the last word for all of them.
DEFAULT_WARMUP_SESSIONS = 60

TIMEFRAME_SECONDS = {"1m": 60, "5m": 300}


def edgelog_home():
    h = os.environ.get("EDGELOG_HOME")
    if h:
        return h
    if os.name == "nt":
        return r"C:\EdgeLog"
    return os.path.expanduser("~/edgelog")


def _paths(home=None):
    home = home or edgelog_home()
    ohlc_dir = os.path.join(home, "ohlc")
    state_dir = os.path.join(home, "cloud_signal")
    return {
        "home": home,
        "ohlc_dir": ohlc_dir,
        "state_dir": state_dir,
        "signals_path": os.path.join(state_dir, "signals.csv"),
        "state_path": os.path.join(state_dir, "state.json"),
        "heartbeat_path": os.path.join(state_dir, "heartbeat.json"),
    }


# The LIVE store: the runner's parallel run writes here and api/qqq_exec.py consumes
# signals.csv by row cursor. Only live (fetching) callers may default to it -- an offline
# run gets isolated_paths() or an explicit paths dict (see isolated_paths, 2026-09-14).
DEFAULT_PATHS = _paths()


def shadow_paths(live_paths=None):
    """The SHADOW LEGS' store (OWNER DECISION 2026-09-28): the same keys as _paths(), with
    ohlc_dir = the LIVE store's own bar cache (the shadow legs read the very bars the live
    legs do -- QQQ_5m/QQQ_1m/QQQ_1d.csv and any backfill -- and never write them) and every
    state file under <live state_dir>/shadow/. api/qqq_exec.py takes orders only from
    DEFAULT_PATHS["signals_path"], so nothing written here can ever become an order (it
    reads this store's signals.csv for one display-only block of its status doc,
    "shadow_trades" -- see api/qqq_exec.py _build_shadow_trades).
    Built from `live_paths` (default DEFAULT_PATHS, read at call time) so a test that
    repoints DEFAULT_PATHS gets a matching shadow store under it."""
    live_paths = live_paths or DEFAULT_PATHS
    state_dir = os.path.join(live_paths["state_dir"], "shadow")
    return {
        "home": live_paths["home"],
        "ohlc_dir": live_paths["ohlc_dir"],
        "state_dir": state_dir,
        "signals_path": os.path.join(state_dir, "signals.csv"),
        "state_path": os.path.join(state_dir, "state.json"),
        # the shadow run's OWN heartbeat (run_shadow_step) -- never the live one, which
        # api/qqq_exec.py's engine-mode feed check reads
        "heartbeat_path": os.path.join(state_dir, "heartbeat.json"),
    }


# ── Crown legs (current as of 2026-09-24 — see api/paper.py PAPER_LEGS) ─────────────────
# NOISE_382 (OWNER DECISION 2026-09-23): run #382's champion cell, read literally from the
# run's own doc. NOISE_1_8_CT304.py is FENCED (_ADMISSIBLE/_in_neighbourhood) -- it REFUSES
# (returns None) a configuration outside its declared neighbourhood rather than clamp one,
# so this dict must carry the exact cell the run picked, never a rounded/nearby guess.
# gate_tf_min in {30, 60}, gate_len in {16, 20}, gate_ratio in {1.0, 1.15},
# tilt_mult in {1.0, 1.5, 2.0} -- every value below sits on one of those points.
NOISE_382_PARAMS = {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15}

# NOISE #422 (SHADOW LEGS, OWNER DECISION 2026-09-28): run #422's crowned cell, read
# literally from the run's own record (NOISE.md "NOISE #422 (NOISE-55, CT304H)";
# tools/r61_noise_382_live_gaps.py carries the same literal). NOISE_1_8_CT304H.py is FENCED
# exactly like NOISE_1_8_CT304.py -- it REFUSES (returns None) a configuration outside its
# declared neighbourhood rather than clamp one, so this dict must carry the exact cell the
# run picked. gate_len in {16, 20, 24}, gate_ratio in {0.85, 1.0, 1.15}, tilt_mult in
# {1.25, 1.5, 1.75} -- every value below sits on one of those points. There is NO
# gate_tf_min key: the file freezes the verification frame at 60 minutes itself.
NOISE_422_PARAMS = {"tilt_mult": 1.75, "gate_len": 20, "gate_ratio": 1.15}

# DIP #424 (SHADOW LEGS, MANAGER #108 GO 2026-10-09): run #424's validate champion, read
# literally from the run's own doc (validate.champion; NQ 5m RTH no-adjust, cost 0 / mult 1 --
# NQDIP_1_1.py charges its own costs and returns dollars). No "asset" key here: the live legs
# add asset="ETF" (every setting is scale-free; "auto" would pick NQ micro costs and roll
# seams on intraday data), while KEEL's NQ training (keel["train"]) runs it without one.
DIP_424_PARAMS = {"notional": 100000, "cost_pts_rt": 0.783, "cost_bps": 2.0,
                  "trend_len": 400, "rsi_len": 3, "rsi_thr": 45, "rsi_exit": 6,
                  "dbl_n": 5, "pb_ema": 10, "pb_hold": 30,
                  "cap_mult": 0.75, "cap_q": 0.35, "cap_hold": 5,
                  "ibs_thr": 0.25, "ibs_exit": 1.0, "ibs_hold": 10,
                  "streak_n": 0, "streak_hold": 4, "gap_atr": 0.0, "gap_hold": 1,
                  "use_rsi": True, "use_dbl": True, "use_pb": True, "use_cap": True,
                  "use_ibs": True, "use_streak": True, "use_gapdn": True}
# DIP_424F's constant size: KEEL's average size over #424's walk-forward trades (SB/TTM: the
# true-roll list's average; fixed 1.245x beat KEEL on ROC, 23.9 vs 18.5 at $30k DD).
DIP_424_CONST_SIZE = 1.245
# cfg["runner"] of a DIP leg -- leg_decision_trades sends it to api/dip_live.py
DIP_RUNNER = "dip_daily"
# NQDIP_1_1.py's seven mechanisms in the file's own order (NQDIP_1_1.py:286-287): the slot
# name each trade carries in its id, and the use_* flag that runs that mechanism alone.
DIP_MECHS = (("RSI", "use_rsi"), ("DBL", "use_dbl"), ("PB", "use_pb"), ("CAP", "use_cap"),
             ("IBS", "use_ibs"), ("STREAK", "use_streak"), ("GAPDN", "use_gapdn"))
# warmup_sessions of a DIP leg: EVERY cached 5m session (the daily series' sources must never
# flip back as a rolling window moves -- see api/dip_live.py)
DIP_5M_ALL_SESSIONS = 100_000
# The daily series' calibration guard (api/dip_live.py build_daily_series): over at least
# DIP_CAL_MIN_OVERLAP sessions that are complete in the 5m cache AND in QQQ_1d.csv, the median
# |5m close / 1d close - 1| and the same for opens must each be <= DIP_CAL_TOL, else the series
# is refused (a split or an adjusted file). 10 bp is a PROPOSAL, not yet measured on the box.
DIP_CAL_TOL = 0.0010
DIP_CAL_MIN_OVERLAP = 20
# ... AND no single overlap session may differ by more than DIP_CAL_MAX_DAY on its close or its
# open ("cal_split"): the median alone goes back to 0 about 45 sessions after a split one file
# has and the other has not, while the older half still carries the 2:1 cliff. The worst real
# day measured is 14 bp; a 2:1 split is ~5,000 bp.
DIP_CAL_MAX_DAY = 0.02
# ... AND no session of the series may open outside DIP_SPLIT_GAP x the previous session's close
# ("cal_split"): a split inside the RAW 5m cache (or a raw QQQ_1d row) is caught even where the
# two files agree or QQQ_1d.csv has no row to compare. A 2:1 split is 0.5, a 1:2 reverse 2.0.
DIP_SPLIT_GAP = (0.6, 1.6)
# A DIP leg hands _diff_leg only trades still open or closed within this many sessions -- every
# trade ENTERED inside it is among them -- so a cold start does not absorb years of history
# into state.json.
DIP_DIFF_SESSIONS = 60


# ── KEEL v12 overlay (OWNER DECISION 2026-09-23) ─────────────────────────────────────────
# "Put KEEL v12 on top of run #382 on the live Webull NOISE leg, train it on the NQ
# backtest like the validation." See augur_engine/ml_keel.py's keel_build_state /
# keel_score_from_state (the build-once/score-many split this overlay is built on) and
# tools/keel_live_state.py (the nightly job that writes the files keel_paths() below
# names). AN OVERLAY, NEVER A GATE: every failure path in _keel_size_for_entry returns
# keel_size 1.0 (unsized -- exactly today's un-overlaid behaviour), logged, never raised
# -- see that function's own docstring. KEEL_MAX_STALE_SESSIONS caps how many trading
# sessions a state may lag "now" before it is treated as unavailable rather than trusted.
KEEL_MAX_STALE_SESSIONS = 5

# FOUR SHAPES OF A LEG'S "keel" KEY (2026-09-27, docs/PREREG_keel_422_parts_2026-09-27.md
# RESULT; the first three run side by side on the NOISE #422 shadow legs since 2026-09-28; the
# fourth, const, since the DIP #424 shadow legs, 2026-10-09):
#   learned  dict(version="v12", **keel_paths(<leg>, "v12"))  -- the model, trained nightly on
#            the box (tools/keel_live_state.py) and scored from its state file (no "mode"
#            key, or mode="learned"). NOISE_382 (live) and NOISE_422_KEEL (shadow).
#   fixed    dict(version="v12", mode="fixed")  -- v12's a-priori tilts with NO model
#            (augur_engine/ml_keel.py's fixed_tilt_sizes_v12, arm A3 of that pre-registration:
#            compression 1.5x, Friday 1.5x, capped at 3, half size before an FOMC statement).
#            No state file, no nightly build, no staleness check. NOISE_422_FIXED (shadow).
#   const    dict(mode="const", size=<float>)  -- every entry at that one size, no model, no
#            state, no tilts (_keel_const_size: finite, > 0, <= KEEL_CONST_MAX_SIZE, else 1.0
#            with its reason). DIP_424F (shadow, 1.245).
#   none     no "keel" key at all -- the plugin's own size. ORB_R6, NOISE_422_PLAIN, ENGUQ_335.
# A learned block may also carry "train" (DIP_424K: the params / cost_pts / date_from its NQ
# training run uses -- read by tools/keel_live_state.py only; nothing in this module reads it).
# Any other "mode" is a configuration error: every entry sizes 1.0 and the fallback push says
# so (see _keel_size_for_entry / _keel_fallback_reason), same as a broken learned state.
KEEL_MODE_LEARNED = "learned"
KEEL_MODE_FIXED = "fixed"
KEEL_MODE_CONST = "const"
KEEL_CONST_MAX_SIZE = 3.0        # the KEEL v12 rule's own cap -- a constant size above it is refused
KEEL_FIXED_VERSIONS = ("v12",)   # the fixed tilts exist for v12 only (ml_keel.FIXED_V12_*)


def keel_mode(keel_cfg):
    """The mode of a leg's "keel" block (see FOUR SHAPES above): "learned", "fixed" or
    "const", None for no block, or the raw lower-cased "mode" string when it is none of them --
    which every reader treats as a configuration error, never as any mode. Never raises."""
    if not keel_cfg:
        return None
    try:
        mode = str(keel_cfg.get("mode") or KEEL_MODE_LEARNED).strip().lower()
    except Exception:
        return "?"
    return mode


# LIVE SINCE for ENGUQ_335 (OWNER DECISION 2026-10-09, via MANAGER #102) -- see LIVE SINCE
# above _apply_live_since. Changing it re-runs that leg's cold start once, on purpose.
ENGUQ_LIVE_SINCE = "2026-10-09"


def keel_paths(leg_key, version, home=None):
    """Where tools/keel_live_state.py writes -- and this module reads -- a leg's KEEL
    state (joblib, this-host-only, never copied across machines) and its JSON summary
    (plain-safe, freely readable). Same EDGELOG_HOME convention as _paths() above."""
    home = home or edgelog_home()
    d = os.path.join(home, "cloud_signal", "keel")
    return {"dir": d,
           "state_path": os.path.join(d, f"{leg_key}_{version}_state.joblib"),
           "summary_path": os.path.join(d, f"{leg_key}_{version}_summary.json")}


CROWN_LEGS = {
    "ORB_R6": {
        "strategy": "ORB_3_6_R6.py",
        "timeframe": "5m",
        "params": dict(ORB_314),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        # Flat at the session's last bar, like the backtest -- see EOD SETTLE (2026-09-28).
        "eod_flat": True,
        # Report the engine's own stop / target / breakeven levels (stop_px/target_px on
        # the ENTRY row, a LEVELS row when breakeven moves the stop) for the resting Webull
        # stop -- see RESTING LEVELS above run_leg_trades. ONLY this leg.
        "resting_levels": True,
    },
    "NOISE_382": {
        "strategy": "NOISE_1_8_CT304.py",
        "timeframe": "5m",
        "params": dict(NOISE_382_PARAMS),
        # same warm-up as every other crown leg -- the owner's spec calls for no change
        # here, only the strategy file + params under it.
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        # KEEL v12 overlay -- see the block comment above keel_paths(). Any OTHER leg's
        # cfg simply has no "keel" key, and every keel-aware code path below treats a
        # missing key exactly like today's pre-KEEL behaviour (see _diff_leg).
        "keel": dict(version="v12", **keel_paths("NOISE_382", "v12")),
        # Send orders at the backtest's decision (the close of bar D), not a bar later
        # (WEBULL_PAPER_TODO.md item 16, owner GO 2026-09-26) -- see _decide_at_close_probe.
        "decide_at_close": True,
        # Flat at the session's last bar (NOISE_1_0.py's STEP E) -- see EOD SETTLE.
        "eod_flat": True,
    },
    # LIVE AGAIN SINCE 2026-10-09 (OWNER DECISION via MANAGER #102) -- see the module
    # docstring. The cfg it had live before 2026-09-28 (fb0f32f0's parent), key for key,
    # plus "live_since". No "eod_flat": its strategy holds overnight in the backtest, so its
    # engine trade may stay open past the close -- and since 2026-10-09 (owner GO, MANAGER
    # #106) the BOOK holds it too: qqq_exec's flat_by flatten skips ENGUQ
    # (HOLD_OVERNIGHT_LEGS) and sells it on this leg's own EXIT on a later day.
    "ENGUQ_335": {
        "strategy": "ENGUQ_1M_ETH_R2_1_0.py",
        "timeframe": "1m",
        # phantom_safe=True (2026-09-26, WEBULL_GO_LIVE.md 3.7): ONLY this leg opts in.
        # phantom_safe is a run_backtest KEYWORD ARGUMENT, not a DEFAULT_PARAMS entry (kept out
        # of DEFAULT_PARAMS on purpose so no search space ever sweeps it -- see that file's own
        # comment just above DEFAULT_PARAMS' closing brace). The strategy's own default is False
        # (every backtest, validate and paper leg keeps today's behaviour) -- this is the one
        # caller that re-runs the walk on a rolling window that keeps growing bar by bar, which
        # is exactly the shape that used to book a trade a full backtest never takes (see
        # ENGUQ_1M_ETH_R2_1_0.py's comment for what the flag does).
        "params": dict(ENGUQ_335, phantom_safe=True),
        # With phantom_safe a REAL later entry only shows once the earlier setup's 10-bar
        # fill window has run out, up to ~10 one-minute bars after its own fill bar
        # (seen 2026-09-24 12:17). Accept entries up to 11 bars old instead of the
        # default 3, so a late real trade is taken rather than dropped (lead, 2026-09-26).
        "max_entry_age_sec": 11 * 60,
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        # see module docstring "ENGINE LIMITATION" — flagged, not hidden
        "caveat": "ETH-fit crown running on an RTH-only QQQ tape — exploratory, not evidence-backed",
        # START FLAT (owner 2026-10-09): the box's live state.json still holds this leg's
        # pre-2026-09-28 records -- see LIVE SINCE above _apply_live_since.
        "live_since": ENGUQ_LIVE_SINCE,
    },
}

# ── Shadow legs (OWNER DECISION 2026-09-28) -- see the module docstring's SHADOW LEGS ────
# Run by run_shadow_step() on the SAME bars as CROWN_LEGS, into shadow_paths()'s store only.
# "shadow": True is a second, independent guard beside run_shadow_step's fetch=False: every
# ntfy push step()/_diff_leg can reach checks it (see _push_allowed), so a shadow leg can
# never page the owner even if a future caller ran it with fetch=True. Keys must not collide
# with CROWN_LEGS (tests/test_shadow_legs.py) -- a trade id carries the leg key. ORDER MATTERS:
# api/qqq_exec.py's shadow_trades block and the board list the legs in this order, so a new leg
# is APPENDED (the DIP #424 pair last, 2026-10-09).
SHADOW_LEGS = {
    # NOISE #422 plain: the plugin's own size (1.0, or 1.75 while the hourly squeeze is on).
    "NOISE_422_PLAIN": {
        "strategy": "NOISE_1_8_CT304H.py",
        "timeframe": "5m",
        "params": dict(NOISE_422_PARAMS),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        "decide_at_close": True,
        # flat at the session's last bar like the primary -- see EOD SETTLE (2026-09-28)
        "eod_flat": True,
        "shadow": True,
    },
    # + KEEL v12's fixed tilts, no model (research arm A3) -- see THREE SHAPES above keel_paths.
    "NOISE_422_FIXED": {
        "strategy": "NOISE_1_8_CT304H.py",
        "timeframe": "5m",
        "params": dict(NOISE_422_PARAMS),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        "keel": dict(version="v12", mode=KEEL_MODE_FIXED),
        "decide_at_close": True,
        # flat at the session's last bar like the primary -- see EOD SETTLE (2026-09-28)
        "eod_flat": True,
        "shadow": True,
    },
    # + KEEL v12 learned: its OWN nightly state, trained on #422's NQ walk under this key's
    # file names (tools/keel_live_state.py builds every learned leg in both dicts). Until the
    # first build lands every entry scores 1.0 -- silently, see _push_allowed.
    "NOISE_422_KEEL": {
        "strategy": "NOISE_1_8_CT304H.py",
        "timeframe": "5m",
        "params": dict(NOISE_422_PARAMS),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        "keel": dict(version="v12", **keel_paths("NOISE_422_KEEL", "v12")),
        "decide_at_close": True,
        # flat at the session's last bar like the primary -- see EOD SETTLE (2026-09-28)
        "eod_flat": True,
        "shadow": True,
    },
    # ENGUQ_335 was the fourth shadow leg from 2026-09-28 until it went back to CROWN_LEGS on
    # 2026-10-09 (OWNER DECISION) -- see the module docstring. Its shadow rows stay as history.
    # DIP #424 ("KEEL DIP", MANAGER #108 GO 2026-10-09) -- see the module docstring and
    # api/dip_live.py. Decided on the daily close, filled at the next session's 09:30 open, up
    # to seven positions at once (one per mechanism, each its own trade-id slot), multi-day
    # holds -- so no eod_flat / decide_at_close / resting_levels. warmup_sessions: every cached
    # 5m session (the daily series' source per date must never flip back). max_entry_age_sec:
    # the whole session -- no order is ever sent and the fill price (the 09:30 open) does not
    # depend on when the box saw the bar, so a would-be trade is never lost to an outage
    # shorter than the session (the default three bars would drop it after 15 minutes).
    # + KEEL v12 learned, its OWN nightly state (DIP_424K_v12_state.joblib / _summary.json,
    # tools/keel_live_state.py), trained on #424's NQ trades: keel["train"] = the run's own
    # params WITHOUT an asset key (auto -> the NQ model on 5m NQ), cost 0 (the file charges its
    # own), from the run's date_from. Until the first build lands every entry scores 1.0.
    "DIP_424K": {
        "strategy": "NQDIP_1_1.py",
        "timeframe": "5m",
        "runner": DIP_RUNNER,
        "params": dict(DIP_424_PARAMS, asset="ETF"),
        "warmup_sessions": DIP_5M_ALL_SESSIONS,
        "max_entry_age_sec": 390 * 60,
        "keel": dict(version="v12", **keel_paths("DIP_424K", "v12"),
                     train=dict(params=dict(DIP_424_PARAMS), cost_pts=0.0, date_from="2010-06-07")),
        "shadow": True,
    },
    # the same trades at a constant 1.245 (see DIP_424_CONST_SIZE / FOUR SHAPES above)
    "DIP_424F": {
        "strategy": "NQDIP_1_1.py",
        "timeframe": "5m",
        "runner": DIP_RUNNER,
        "params": dict(DIP_424_PARAMS, asset="ETF"),
        "warmup_sessions": DIP_5M_ALL_SESSIONS,
        "max_entry_age_sec": 390 * 60,
        "keel": dict(mode=KEEL_MODE_CONST, size=DIP_424_CONST_SIZE),
        "shadow": True,
    },
}

# Sizing: identical convention to tools/qqq_paper.py (shares = floor($ notional / entry px)).
NOTIONAL_PER_LEG = qp.NOTIONAL_PER_LEG
SLIPPAGE_PER_SHARE = qp.SLIPPAGE_PER_SHARE


# ── Bar cache (portable read/write; reuses qp's fetch + array builder) ──────────────────
def _cache_path(timeframe, paths=None):
    paths = paths or DEFAULT_PATHS
    return os.path.join(paths["ohlc_dir"], f"QQQ_{timeframe}.csv")


def load_cached_bars(timeframe, paths=None):
    """Read the on-disk epoch-schema cache. None if nothing cached yet."""
    path = _cache_path(timeframe, paths)
    if not os.path.exists(path):
        return None
    import pandas as pd
    return pd.read_csv(path)


# -- optional Alpaca backfill splice (tools/backfill_qqq_5m_alpaca.py, WEBULL go-live
# "alpaca" task, 2026-09-26) -- READ-ONLY older history for signal computation, never for
# what gets written back to disk. See that tool's own module docstring "UPLOAD" for why
# this lives here rather than touching QQQ_5m.csv directly: the box's --apply upload
# writes ~/edgelog/ohlc/QQQ_{tf}_backfill.csv, a file this module never writes, so there is
# no write-write race with the live cache-writer thread (fetch_and_merge) to guard
# against -- only a read of a file something else finished writing (atomically) before
# this call started.
_BACKFILL_CACHE = {}     # backfill path -> (mtime, DataFrame)
_BACKFILL_WARNED = set()  # backfill paths already logged as unreadable (log once)


def _backfill_path(timeframe, paths):
    return os.path.join(paths["ohlc_dir"], f"QQQ_{timeframe}_backfill.csv")


def _load_backfill_bars(timeframe, paths):
    """QQQ_{tf}_backfill.csv, if present, cached by the file's own mtime so a live tick
    loop does not reparse it every call. None if the file is absent. Fail-safe: any read
    error is cached (by that same mtime, as None) and logged ONCE, so a broken file is
    neither re-parsed every tick nor re-logged -- only a later mtime change (someone
    fixing or replacing the file) triggers another attempt. A bad backfill file must
    never break live signals."""
    path = _backfill_path(timeframe, paths)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _BACKFILL_CACHE.get(path)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    try:
        import pandas as pd
        df = pd.read_csv(path)
    except Exception as e:
        _BACKFILL_CACHE[path] = (mtime, None)
        if path not in _BACKFILL_WARNED:
            _BACKFILL_WARNED.add(path)
            print(f"[cloud-signal] backfill file unreadable, ignoring it ({path}): "
                  f"{type(e).__name__}: {e}")
        return None
    _BACKFILL_CACHE[path] = (mtime, df)
    return df


def _prepend_backfill(df, timeframe, paths):
    """`df` with any _load_backfill_bars() rows STRICTLY OLDER than `df`'s own first bar
    spliced onto the front -- never overriding a single row `df` already has. Returns
    `df` UNCHANGED (None stays None, empty stays empty) whenever there is no backfill
    file, no usable older rows, or anything goes wrong (fail-safe by design, same
    contract as _load_backfill_bars). A missing/empty live cache is deliberately NOT
    replaced by the backfill alone: signal computation should skip the leg the same way
    it would with no cache at all, not silently run off backfill-only history."""
    try:
        if df is None or not len(df):
            return df
        backfill = _load_backfill_bars(timeframe, paths)
        if backfill is None or not len(backfill):
            return df
        import pandas as pd
        older = backfill[backfill["time"] < df["time"].min()]
        if not len(older):
            return df
        return pd.concat([older, df], ignore_index=True).sort_values("time").reset_index(drop=True)
    except Exception as e:
        print(f"[cloud-signal] backfill splice failed, ignoring it ({type(e).__name__}: {e})")
        return df


def historical_bars(timeframe, paths=None):
    """load_cached_bars() plus any older QQQ_{tf}_backfill.csv history spliced onto the
    front (_prepend_backfill) -- what signal computation and window-sizing should read.
    NEVER what fetch_and_merge writes back to the on-disk cache."""
    paths = paths or DEFAULT_PATHS
    return _prepend_backfill(load_cached_bars(timeframe, paths), timeframe, paths)


WEBULL_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json")
WEBULL_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR", r"C:\EdgeLog\webull_token")
WEBULL_TAIL_BARS = 200          # see _fetch_webull

# UNSETTLED BARS (2026-09-28). A fetched row is merged into the cache only if its bar had
# already CLOSED when the Webull response came back -- or, for the yfinance fallback,
# closed at least YF_SETTLE_SECONDS before the request went out. step() decides a bar from whatever version the cache
# holds at close+CLOSE_GRACE_SECONDS, often on a 1s fetch=False tick reading a fetch made
# up to 30s earlier, and never re-decides it (leg_state["last_bar_epoch"]). Webull returns
# finished bars only (box caches checked live 2026-09-28: the just-closed bar lands ~6s
# after the close and never changes), so this is a no-op there. yfinance returns the
# still-FORMING bar (5m: a growing partial aggregate; 1m: a flat volume-0 placeholder) and
# keeps revising the newest closed one for ~13-38s, so without this a fallback session
# decides every bar off a pre-close snapshot. Cost under the fallback: a bar is decided
# one fetch later (~30-90s), well inside the legs' entry-age grace.
YF_SETTLE_SECONDS = 60
_UNSETTLED_DROP_LOGGED = {}     # timeframe -> True while a run of fetches keeps dropping rows


def _wall_epoch():
    """The fetch moment, as POSIX seconds. Its own function so tests can pin it."""
    return int(_time.time())


def _drop_unsettled(fresh, timeframe, settled_by_epoch, source, log=print):
    """`fresh` minus every row whose bar closes after `settled_by_epoch` (see UNSETTLED
    BARS above). Logs once per run of dropping fetches, not every 30s."""
    if fresh is None or not len(fresh):
        return fresh
    keep = fresh["time"].astype("int64") + TIMEFRAME_SECONDS[timeframe] <= settled_by_epoch
    dropped = int((~keep).sum())
    if not dropped:
        _UNSETTLED_DROP_LOGGED.pop(timeframe, None)
        return fresh
    if not _UNSETTLED_DROP_LOGGED.get(timeframe):
        _UNSETTLED_DROP_LOGGED[timeframe] = True
        log(f"[cloud-signal] {source} {timeframe}: left {dropped} not-yet-settled bar(s) out of "
            f"the cache (newest {int(fresh['time'].max())}); they merge once settled "
            f"(logged once until a fetch drops nothing)")
    return fresh[keep].reset_index(drop=True)


def _fetch_webull(timeframe, count=WEBULL_TAIL_BARS, log=print):
    """Recent QQQ bars from the official Webull OpenAPI, in this module's epoch schema,
    or None if unavailable. PREFERRED over yfinance since 2026-09-09, when the owner
    claimed the free Nasdaq Basic non-display tier: it is the exchange's own consolidated
    Level 1 feed, roughly a second behind the print, against yfinance's ~38s median for
    the newest CLOSED minute (measured, tools/qqq_feed_latency_probe.py).

    Only the TAIL is fetched. The API caps a request at 1200 bars while the rolling
    window wants tens of thousands, so history stays in the on-disk cache and this call
    just tops it up — the same shape the yfinance path always had.

    TOKEN: MarketData(api) does NOT authenticate; only ClientInitializer.initializer()
    attaches the x-access-token, and the SDK runs it inside TradeClient/DataClient but
    never inside MarketData. Omitting it is a silent 401 that reads like "no
    entitlement" — the bug that kept api/qqq_exec.py's quote path dark for the whole
    trial. Do not remove that call.

    RTH ONLY, matching the yfinance path's prepost=False: the crowned configs are
    regular-session configs and a spliced overnight bar would change what a bar means.
    """
    import json as _json
    import pandas as pd
    # FEED HEALTH: every call that returns None leaves its own reason here, so the yfinance
    # push never names an older call's error (e.g. a token PENDING long since fixed)
    _WEBULL_LAST_ERR["text"] = "no reply yet"
    try:
        with open(WEBULL_KEYS, encoding="utf-8") as fh:
            keys = _json.load(fh)
        ak = (keys.get("app_key") or "").strip()
        sk = (keys.get("app_secret") or "").strip()
        if not ak or not sk or ak.startswith("PASTE_"):
            _WEBULL_LAST_ERR["text"] = "no Webull keys set"
            return None
        from webull.core.client import ApiClient
        from webull.core.http.initializer.client_initializer import ClientInitializer
        from webull.data.quotes.market_data import MarketData
        from webull.data.common.category import Category
        from webull.data.common.timespan import Timespan
        span = {"1m": Timespan.M1, "5m": Timespan.M5}.get(timeframe)
        if span is None:
            _WEBULL_LAST_ERR["text"] = f"no Webull bars for {timeframe}"
            return None
        api = ApiClient(ak, sk, (keys.get("region") or "us").strip().lower(),
                        token_check_duration_seconds=15, token_check_interval_seconds=5,
                        connect_timeout=10, timeout=25)
        os.makedirs(WEBULL_TOKEN_DIR, exist_ok=True)
        api.set_token_dir(WEBULL_TOKEN_DIR)
        # the SDK otherwise attaches a rotating file logger on the shared CWD, which the
        # five runner processes fight over every hour (WinError 32)
        api._file_logger_set = True
        _logging.getLogger("webull.core").addHandler(_logging.NullHandler())
        ClientInitializer.initializer(api)
        resp = MarketData(api).get_history_bar("QQQ", Category.US_ETF, span, count=str(count))
        rows = resp.json() if hasattr(resp, "json") else resp
        if not isinstance(rows, list) or not rows:
            _WEBULL_LAST_ERR["text"] = "empty reply from Webull"
            return None
        out = []
        for r in rows:
            if str(r.get("trading_session", "RTH")).upper() != "RTH":
                continue
            try:
                ts = int(pd.Timestamp(r["time"]).timestamp())
                out.append({"time": ts, "open": float(r["open"]), "high": float(r["high"]),
                            "low": float(r["low"]), "close": float(r["close"]),
                            "volume": float(r.get("volume") or 0.0)})
            except Exception:
                continue
        if not out:
            _WEBULL_LAST_ERR["text"] = "Webull reply had no regular-session bars"
            return None
        _WEBULL_LAST_ERR["text"] = None
        return pd.DataFrame(out).sort_values("time").reset_index(drop=True)
    except Exception as e:
        log(f"[cloud-signal] webull bars unavailable ({timeframe}): {type(e).__name__}: {e}")
        _WEBULL_LAST_ERR["text"] = f"{type(e).__name__}: {e}"[:300]
        return None


# The newest Webull REST error this process saw (None after a good fetch) -- the FEED HEALTH
# push names it, and pages URGENT when it is the token waiting for approval (finding 15).
_WEBULL_LAST_ERR = {"text": None}


def fetch_and_merge(timeframe, paths=None, log=print):
    """Pull fresh bars, merge into the cache under EDGELOG_HOME, and return
    (merged_epoch_frame, source, cache_ok) where source is "webull" or "yfinance" --
    whichever one actually produced THIS call's fresh rows -- and cache_ok is False
    only when the on-disk rename could not be completed (see RENAME RETRY below).
    Network call — never invoked from --replay or from tests, only from a live step().

    Webull first, yfinance as the fallback. Both are consolidated US equity prints for
    the same regular session, so they agree to the cent in normal conditions; the cache
    can therefore hold rows from either without a seam. If that ever stops being true it
    shows up as a price jump exactly at a source change, so the fallback logs when it
    fires rather than switching silently.

    The returned `source` is what api/qqq_exec.py's engine-mode pricing (and the web
    tab's status panel) report as WEBULL/YAHOO -- see `read_bar_source` below, which
    persists this into state.json so a DIFFERENT process (the standalone qqq_exec
    adapter) can read it without importing this module's live fetch path.

    RENAME RETRY (2026-09-14). `os.replace(tmp, path)` used to be a single unretried
    call: `C:\\EdgeLog\\ohlc\\QQQ_1m.csv`/`QQQ_5m.csv` are read by several other
    short-lived processes (tools/qqq_paper.py's own independent sync of the SAME files
    when EDGELOG_HOME is unset, a replay, a test snapshot), and Windows refuses the
    rename outright -- not a retry-free race, an outright PermissionError -- while any
    of them merely has the destination open for reading. Seen live: `[cloud-signal]
    step failed: PermissionError [WinError 32] ... 'QQQ_1m.csv.tmp' -> 'QQQ_1m.csv'`,
    which aborted the whole step() call (this leg's bars were already fetched and
    merged in memory, but the exception propagated before any leg's signals were
    evaluated) and made cloud_signal_thread mark the heartbeat ok=false -- which
    api/qqq_exec.py's engine-mode feed check reads as "stale", blocking new entries,
    for what was really a few-millisecond reader lock. `qp._replace_with_retry` rides
    that out (see its docstring for the budget); `merged` is already fully computed by
    the time the rename is attempted, so this function returns it regardless of
    whether the rename succeeded -- the caller (step()) can still evaluate signals off
    it even when cache_ok is False, and only the ON-DISK cache is a step behind until
    the next successful fetch."""
    import pandas as pd
    paths = paths or DEFAULT_PATHS
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    path = _cache_path(timeframe, paths)
    old = load_cached_bars(timeframe, paths)
    if old is None:
        old = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    # Settled-by cutoff per source (see UNSETTLED BARS above _wall_epoch). Webull: the
    # RESPONSE time -- it never serves a forming bar, so a bar that finished while the
    # request was in flight is final and is kept (the fetch phase drifts against the 5m
    # grid, so a request can start a second or two before a close), and a forming row
    # would still close after the response and be dropped. yfinance: the REQUEST-start time
    # minus the settle margin, since it serves forming bars and revises the newest closed one.
    fresh = _fetch_webull(timeframe, log=log)
    settled_by = _wall_epoch()
    source = "webull"
    if fresh is None or not len(fresh):
        log(f"[cloud-signal] falling back to yfinance for {timeframe} bars")
        settled_by = _wall_epoch() - YF_SETTLE_SECONDS
        fresh_df = qp._fetch_yf(timeframe)
        fresh = qp._to_epoch_frame(fresh_df)
        source = "yfinance"
    fresh = _drop_unsettled(fresh, timeframe, settled_by, source, log=log)
    # concat only non-empty frames: an all-dropped fetch is routine under the yfinance
    # fallback, and concatenating an empty frame raises pandas' FutureWarning
    parts = [f for f in (old, fresh) if f is not None and len(f)]
    merged = pd.concat(parts, ignore_index=True) if parts else old
    if len(merged):
        merged = merged.drop_duplicates("time", keep="last").sort_values("time")
    # ATOMIC (2026-09-09): to_csv() TRUNCATES then writes, so a reader that opens the file
    # mid-write gets an empty or half-written cache. That is not hypothetical -- this thread
    # rewrites the cache every 30s and it caught the test suite red-handed, which is exactly
    # what a strategy run or a manual replay would have hit instead. Write beside it and
    # rename: os.replace is atomic on Windows and POSIX, so a reader sees the old file or
    # the new one, never a torn one. RETRIED (2026-09-14, see docstring above) rather than
    # left to raise on the first transient lock.
    tmp = path + ".tmp"
    merged.to_csv(tmp, index=False)
    cache_ok = qp._replace_with_retry(tmp, path, log=log,
                                      what=f"[cloud-signal] {timeframe} bar cache")
    # Splice any older Alpaca-backfill history onto the RETURNED frame only -- `merged` was
    # already written to disk above with none of it, so the on-disk cache never gains
    # backfill rows (see historical_bars / tools/backfill_qqq_5m_alpaca.py "UPLOAD").
    return _prepend_backfill(merged, timeframe, paths), source, cache_ok


def read_bar_source(paths=None):
    """Best-effort read of state.json's `bar_source` block: {timeframe: {"source",
    "newest_epoch", "checked_at"}}, written by step() on every FETCHING call (--once /
    --loop / the runner thread; never --replay, which passes fetch=False and touches no
    network). Returns {} if the state file is absent or this process's step() has never
    fetched live yet -- a caller in a different process (api/qqq_exec.py, engine mode)
    reads this instead of importing the live fetch path itself."""
    paths = paths or DEFAULT_PATHS
    try:
        return _load_state(paths).get("bar_source") or {}
    except Exception:
        return {}


build_arrays = qp.build_arrays   # pure transform, reused as-is


# ── Rolling window + "closed bars only" ──────────────────────────────────────────────────
def _closed_cutoff_epoch(now, timeframe):
    """Bars whose CLOSE (bar-open-time + timeframe) is <= now - grace are usable."""
    now_epoch = int(now.timestamp())
    return now_epoch - CLOSE_GRACE_SECONDS - TIMEFRAME_SECONDS[timeframe]


def closed_arrays(all_epoch_df, now, timeframe, warmup_sessions):
    """epoch_df -> RTH arrays (via qp.build_arrays), filtered to bars CLOSED as of
    `now`, then trimmed to the last `warmup_sessions` distinct sessions ending at or
    before `now`'s own session. Returns None if there is nothing usable yet.

    PERFORMANCE: a cheap raw-epoch prefilter runs BEFORE build_arrays (which does the
    tz-aware pandas datetime conversion + day factorize — the actually expensive
    part). Without it, replay()'s per-closed-bar recompute pays that cost against the
    ENTIRE cache every single call (390+ times for a 1m leg), which is what made an
    early version of this function take 80+ seconds per replayed session. Restricting
    to a calendar-day window first bounds that cost to roughly the window size
    regardless of total cache depth.

    BUFFER SIZE (fixed 2026-09-13 — see tools/orb_qqq_warmup_bug.py). The buffer used
    to be a flat `warmup_sessions + 5` calendar days, on the theory that 5 days was
    "generous" slack for weekends/holidays. It is not: `warmup_sessions` counts TRADING
    days, which run only 5/7 of calendar days, so 60 trading sessions span roughly 84
    calendar days, not 65. The undersized buffer silently truncated the raw prefilter
    to whichever sessions fit inside it (measured: 47 sessions instead of the intended
    60 on the real QQQ cache), which is one bug on its own (every trailing filter gets
    less history than its own code asks for) — but the worse half is that `cutoff`
    (and therefore `lower_bound`) advances continuously with `now` throughout a single
    session, so as wall-clock time passes within ONE trading day the oldest session can
    age out of the too-tight buffer mid-afternoon, shrinking the window by exactly one
    session at that instant. Every session's index into the trailing-N-session
    reference (ORB's atr_filter/vpace_filter, and any other plugin doing the same
    pattern) shifts by one at that moment, which can flip a same-day trading decision
    hours after the fact: reproduced on 2026-09-04 (ORB_3_6_R6.py's atr/vpace filters),
    where an entry at the day's 09:55 bar was ABSENT from the engine's trade list at
    every tick through 14:05 and PRESENT from 14:06 onward, with no new bar of ANY
    session boundary involved — purely the raw calendar buffer dropping 2026-07-01 out
    of the window at that exact wall-clock moment. The entry then aged past
    `max_entry_age_sec` and was recorded as "late" (silently suppressed) — this time.
    A smaller shift, or a filter less sensitive to one session's weight in a median,
    would instead have emitted a spurious ENTRY that only exists because of when the
    engine happened to be asked, which is a live correctness bug, not merely a stale
    diagnostic. Fix: size the buffer off the actual 5-trading-days-per-7-calendar-days
    cadence plus real slack for holidays, so the buffer always covers `warmup_sessions`
    sessions and the raw prefilter is a no-op (keeps every session actually available)
    long before `keep_days` needs to trim anything — making the exact-session-count
    trim below the ONLY thing that ever changes the window, and only once a day (when
    the calendar date itself rolls, not mid-session)."""
    if all_epoch_df is None or not len(all_epoch_df):
        return None
    cutoff = _closed_cutoff_epoch(now, timeframe)
    calendar_buffer_days = math.ceil(int(warmup_sessions) * 7 / 5) + 15
    lower_bound = cutoff - calendar_buffer_days * 86400
    df = all_epoch_df[(all_epoch_df["time"] <= cutoff) & (all_epoch_df["time"] >= lower_bound)]
    arrays = build_arrays(df)
    if arrays is None or not len(arrays["close"]):
        return None
    day_id = arrays["day_id"]
    distinct_days = sorted(set(day_id.tolist()))
    keep_days = set(distinct_days[-int(warmup_sessions):])
    mask = [d in keep_days for d in day_id]
    if not any(mask):
        return None
    import numpy as np
    mask = np.array(mask)
    out = {k: (v[mask] if k != "index" else v[mask]) for k, v in arrays.items()}
    # ENGINE ROLL GUARD (MANAGER #58 A): arrays must say what they are. These feed live / paper /
    # shadow legs only, which the engine reports and never refuses or changes (MANAGER D2).
    if not out.get("meta"):
        out["meta"] = {"roll_mode": "live", "name": "cloud_signal.closed_arrays"}
    return out


# ── Live history window sizing (WEBULL_PAPER_TODO.md item 12, 2026-09-25) ────────────────
# A strategy file MAY declare a module-level REQUIRED_LOOKBACK_SESSIONS: how many
# TRAILING sessions one of its own internal look-backs needs fully available (strictly
# BEFORE the session being judged) before that look-back stops truncating. Only
# NOISE_1_8_CT304.py (via NOISE_1_1_NBHD.py, via NOISE_1_0.py's vol_skip_pct filter)
# declares one today -- see NOISE_1_0.py's own VOL_SKIP_LOOKBACK_SESSIONS /
# REQUIRED_LOOKBACK_SESSIONS. ORB_3_6_R6.py and ENGUQ_1M_ETH_R2_1_0.py declare nothing,
# so leg_warmup_sessions() below is a complete no-op for them -- byte-identical to the
# plain cfg["warmup_sessions"] read step() used before this existed.
#
# THE BUG THIS FIXES. warmup_sessions (DEFAULT_WARMUP_SESSIONS, 60 -- same for every leg)
# hands closed_arrays() exactly 60 sessions TOTAL, so the session being judged ("today")
# sits in the LAST slot of that window -- never more than 59 sessions deep into it.
# NOISE's vol_skip_pct filter needs 60 REFERENCE sessions strictly BEFORE the day it
# ranks (see NOISE_1_0.py's _vol_percentile) before it produces anything but NaN, and
# NaN reads as "not extreme" -- i.e. the skip silently stands down forever, no matter
# how much real history the box has accumulated. Live NOISE_382 therefore traded days
# the backtest -- which always sees its FULL history -- would have skipped, exactly the
# "dishonest to the backtest" gap item 12 names.
#
# WARMUP_MARGIN_SESSIONS is slack ABOVE a strategy's bare declared minimum: the exact
# analytical floor is a session or two tighter than the declared number (NOISE_1_0.py's
# _vol_percentile needs the JUDGED session's own index to clear min_obs by 2, not 1 --
# see that function's index arithmetic), and a "session" in a live rolling window is not
# always a full trading day (a holiday-shortened session can eat one without shrinking
# the DISTINCT-DAY count closed_arrays trims to). Ten sessions of slack clears that
# uncertainty with room to spare instead of shaving it to the exact bar.
#
# FOLLOW-UP (go-live audit item 3.8, 2026-09-26). 307a128 fixed the skip's ability to
# ENGAGE at all by declaring REQUIRED_LOOKBACK_SESSIONS = 60 (NOISE_1_0.py's min_obs
# floor), but a live window sized off the floor still ranked each day against only
# ~60-70 reference sessions once the skip fired, while a backtest run over its full
# history always ranks against the FULL 252-session window (_vol_percentile's ref_n) --
# about half of skip days disagreed as a result. NOISE_1_0.py now declares
# REQUIRED_LOOKBACK_SESSIONS off VOL_SKIP_REF_SESSIONS (252, its ranking depth) instead
# of VOL_SKIP_LOOKBACK_SESSIONS (60, its bare activation floor), so this same margin
# gives NOISE_382 a 262-session window -- no special-casing here, this function is
# unchanged; only what NOISE_1_0.py declares changed.
WARMUP_MARGIN_SESSIONS = 10


def _strategy_module_for_sizing(strategy):
    """Best-effort module lookup for WINDOW SIZING only. `strategy` is whatever a leg's
    cfg["strategy"] holds -- a bare filename (CROWN_LEGS, always) or an already-loaded
    module (a test's stub). Never raises: this runs before the engine call that would
    surface a real load failure loudly (run_leg_trades), so a strategy this can't
    resolve just declares no requirement (falls back to the leg's plain
    warmup_sessions) rather than blocking step()."""
    if hasattr(strategy, "run_backtest"):
        return strategy
    try:
        from augur_engine.strategies import load_strategy
        return load_strategy(strategy)
    except Exception:
        return None


def required_lookback_sessions(strategy):
    """This leg's strategy's own declared REQUIRED_LOOKBACK_SESSIONS (see block comment
    above), or None when it declares nothing -- true today for every CROWN_LEGS
    strategy except NOISE_1_8_CT304.py."""
    mod = _strategy_module_for_sizing(strategy)
    if mod is None:
        return None
    n = getattr(mod, "REQUIRED_LOOKBACK_SESSIONS", None)
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def leg_warmup_sessions(cfg):
    """The number of trailing sessions to hand this leg's engine call: its own
    cfg["warmup_sessions"] (DEFAULT_WARMUP_SESSIONS for every leg today), OR enough for
    its strategy's declared REQUIRED_LOOKBACK_SESSIONS plus WARMUP_MARGIN_SESSIONS of
    slack, WHICHEVER IS LARGER. A leg whose strategy declares nothing gets exactly its
    existing warmup_sessions back -- unaffected by this function's existence.
    closed_arrays() already trims to however many distinct sessions the cache actually
    holds when that is fewer than what this returns (see its own "keep_days" slicing),
    so the CAP is automatic; this only ever asks for more, never less."""
    base = int(cfg.get("warmup_sessions", DEFAULT_WARMUP_SESSIONS))
    need = required_lookback_sessions(cfg.get("strategy"))
    return base if need is None else max(base, need + WARMUP_MARGIN_SESSIONS)


# ── "session still in progress" pass-through (WEBULL_PAPER_TODO.md item 15) ──────────────
# GENERIC BY DESIGN, NOT ORB-SPECIFIC. A strategy's length-based half-day skip (today,
# only ORB_3_6.py -- see its own "LIVE-ENGINE ADDITION" note) can misfire on the live
# engine's own rolling window: the LAST session in that window is today's, still being
# built bar by bar, so it is genuinely short -- for a reason that has nothing to do with
# a holiday -- until the session is nearly over. By the time it counts as full, a morning
# entry has already aged past _diff_leg's freshness window and is dropped as "late" (box
# record: ORB_R6 fired once since 09-09, late_skipped 6). Rather than hard-code that fix
# to ORB, any strategy may opt in by simply declaring a `session_in_progress` keyword on
# its own run_backtest (exactly the reflection convention augur_engine.engine.run_backtest
# already uses for `volumes`/`day_id`/`index`) -- this module then sets it True for that
# call whenever the two conditions below both hold, and leaves every other leg, and every
# leg on every other call, completely untouched.
def _leg_accepts_session_in_progress(strategy):
    """True iff `strategy`'s run_backtest explicitly names a `session_in_progress`
    parameter. Deliberately does NOT treat a bare **kwargs catch-all as support (unlike
    the volumes/day_id convention every plugin is expected to tolerate): skipping a
    strategy's own half-day test is a live-only correctness decision, and a plugin that
    merely swallows extra keywords has not actually reviewed whether that is safe for
    it. Best-effort/never-raises, same contract as _strategy_module_for_sizing."""
    mod = _strategy_module_for_sizing(strategy)
    if mod is None or not hasattr(mod, "run_backtest"):
        return False
    try:
        sp = inspect.signature(mod.run_backtest).parameters
    except (TypeError, ValueError):
        return False
    return "session_in_progress" in sp


def _session_in_progress(arrays, now):
    """True when `arrays`' LAST session shares `now`'s calendar date AND today is not a
    recognised early close (api.market_calendar.session_close_et) -- i.e. the window
    genuinely ends mid-build on today's own session, not on a real half day where a
    length-based skip should still fire untouched. Best-effort/never-raises: any
    surprise here (a naive `now`, an empty index) reads as False, the safe/off default
    that reproduces today's behaviour."""
    try:
        idx = arrays.get("index")
        if idx is None or not len(idx) or now is None:
            return False
        last_date = idx[-1].date()
        today = now.date()
        if last_date != today:
            return False
        return market_calendar.session_close_et(today) != "13:00"
    except Exception:
        return False


def _cache_session_count(tf, paths):
    """How many DISTINCT RTH sessions the bar cache holds for `tf` right now, INCLUDING
    any older Alpaca-backfill history (historical_bars) -- the same day-bucketing
    build_arrays/closed_arrays use, so this number means the same thing as a leg's
    warmup_sessions and log_history_windows' own COMPLETE/TRUNCATED verdict reflects the
    backfill once it lands. 0 when there is no cache yet. Only ever called from
    log_history_windows (STARTUP, never the per-tick path) -- paying build_arrays' full
    tz-aware/factorize cost once here is fine even though closed_arrays deliberately
    avoids it per-tick (see that function's own PERFORMANCE note)."""
    epoch_df = historical_bars(tf, paths)
    if epoch_df is None or not len(epoch_df):
        return 0
    arrays = build_arrays(epoch_df)
    if arrays is None or not len(arrays.get("close", [])):
        return 0
    return len(set(arrays["day_id"].tolist()))


def log_history_windows(legs=None, paths=None, log=print):
    """ONE clear line per leg naming the history window it will use and whether that
    covers its strategy's own declared look-back (item 12, WEBULL_PAPER_TODO.md).
    Called once at STARTUP (cmd_once, cmd_loop, cloud_signal_thread) -- never per-tick,
    the same rule as the cost note on _cache_session_count. Best-effort/diagnostic
    only: a leg whose cache can't be read yet logs that and moves on rather than
    raising -- this never gates step(), which sizes its own window fresh every call via
    leg_warmup_sessions()."""
    legs = legs if legs is not None else CROWN_LEGS
    paths = paths or DEFAULT_PATHS
    cache_counts = {}
    for key, cfg in legs.items():
        tf = cfg["timeframe"]
        if cfg.get("runner") == DIP_RUNNER:
            # a DIP leg's window is its DAILY series (QQQ_1d.csv + the 5m sessions), not a
            # count of 5m sessions -- api/dip_live.py says how long it is and whether it is ready
            try:
                from api import dip_live as _dip
                log(_dip.history_line(key, cfg, paths))
            except Exception as e:
                log(f"[cloud-signal] history window {key}: DIP daily series unknown "
                    f"({type(e).__name__}: {e})")
            continue
        if tf not in cache_counts:
            try:
                cache_counts[tf] = _cache_session_count(tf, paths)
            except Exception as e:
                log(f"[cloud-signal] history window {key}: could not read the {tf} cache "
                    f"({type(e).__name__}: {e}) -- window sizing continues off the default")
                cache_counts[tf] = None
        available = cache_counts[tf]
        if available is None:
            continue   # already logged above
        base = int(cfg.get("warmup_sessions", DEFAULT_WARMUP_SESSIONS))
        need = required_lookback_sessions(cfg.get("strategy"))
        wanted = base if need is None else max(base, need + WARMUP_MARGIN_SESSIONS)
        actual = min(wanted, available)
        if need is None:
            log(f"[cloud-signal] history window {key}: {actual} session(s) "
                f"(default {base}; cache holds {available}) -- no declared look-back "
                f"requirement beyond the default")
        elif actual >= wanted:
            log(f"[cloud-signal] history window {key}: {actual} session(s) "
                f"(strategy needs >= {need}; wanted {wanted} = {need}+{WARMUP_MARGIN_SESSIONS} "
                f"margin; cache holds {available}) -- look-back COMPLETE")
        else:
            short = max(0, need - actual)
            bridge_note = ""
            if short > 0 and _leg_accepts_vol_prior_ranges(cfg.get("strategy")):
                daily_n = _daily_prior_sessions_available(tf, paths, need)
                bridge_note = (
                    f" -- vol_prior_ranges bridge (go-live audit item 3.8) available: up to "
                    f"{min(short, daily_n)} more session(s) from QQQ DAILY bars ({daily_n} "
                    f"cached before the {tf} window's own first session), calibrated onto the "
                    f"{tf} scale at runtime; the exact count used each tick depends on that "
                    f"day's calibration (see api/cloud_signal.py's vol_prior_ranges_for_leg)")
            log(f"[cloud-signal] history window {key}: {actual} session(s) "
                f"(strategy needs >= {need}; wanted {wanted} = {need}+{WARMUP_MARGIN_SESSIONS} "
                f"margin; cache holds only {available}) -- look-back TRUNCATED"
                + (f", {short} session(s) short of the strategy's own minimum" if short > 0
                   else " (below the margin, but at/above the strategy's own minimum)")
                + bridge_note)


# ── vol_prior_ranges bridge (go-live audit item 3.8, 2026-09-26) ─────────────────────────
# See NOISE_1_0.py's own vol_prior_ranges / _vol_percentile docstrings for what this feeds
# and WHY: the box's QQQ 5m cache holds only ~77 sessions -- nowhere near the 252 sessions
# the vol_skip_pct filter ranks against once it engages -- and there is no intraday data key
# on this PC to backfill it (WEBULL_PAPER_TODO.md item 12's other half, which needs an
# owner-provisioned key; see MANAGER inbox item 12, 2026-09-26). The filter only ever reads
# each session's (H-L)/C though, which a DAILY bar already gives for any session older than
# the 5m cache's own reach. This loads QQQ daily bars from yfinance, computes (H-L)/C for the
# sessions strictly BEFORE a leg's own 5m window, calibrates them onto the 5m-derived scale
# (a daily bar's own H/L is not the same number as an RTH-only 5m session's -- see
# _calibrate_daily_ranges), and hands the result to NOISE_1_0.py's vol_prior_ranges kwarg via
# a PER-CALL copy of the leg's params (cfg["params"] itself is never mutated -- same
# convention as the session_in_progress pass-through above).
#
# FAIL-SAFE THROUGHOUT, by design: any error, any missing/thin overlap, or a calibration
# ratio outside a sane band passes NOTHING and logs why -- exactly today's (pre-this-
# feature) behaviour for that call. This is a bridge for a PC that lacks intraday depth, not
# a new hard requirement -- NOISE_382 keeps trading on its 5m-only window whenever the
# bridge is unavailable, same as before REQUIRED_LOOKBACK_SESSIONS existed.
DAILY_MIN_OVERLAP_SESSIONS = 20
DAILY_CALIBRATION_RATIO_MIN = 0.8
DAILY_CALIBRATION_RATIO_MAX = 1.25
DAILY_MARGIN_SESSIONS = WARMUP_MARGIN_SESSIONS   # same slack idea as leg_warmup_sessions

_DAILY_CALIBRATION_LOG = {}   # "date" -> the ET calendar date last logged; "reasons" ->
                              # the set of _log_fail_safe_once reason_keys already logged
                              # that date (reset together whenever "date" rolls forward)


def _leg_accepts_vol_prior_ranges(strategy):
    """True iff `strategy` -- or, walking its `_base` attribute chain the way
    NOISE_1_8_CT304.py wraps NOISE_1_1_NBHD.py wraps NOISE_1_0.py -- resolves to a
    module whose run_backtest explicitly names a `vol_prior_ranges` parameter. Same
    reflection convention as _leg_accepts_session_in_progress: a bare **kwargs
    catch-all does not count ON ITS OWN, but NOISE's two live wrappers each forward
    this specific keyword through their own **kw once it is present in the caller's
    kwargs (see NOISE_1_8_CT304.py's own vol_prior_ranges passthrough and
    NOISE_1_1_NBHD.py's _BASE_ARGS filter, which is computed by inspecting
    NOISE_1_0.py's signature directly) -- so reaching a module at the bottom of the
    chain that DOES name it is sufficient to know the whole chain will carry it
    through. Best-effort/never-raises, same contract as _strategy_module_for_sizing."""
    mod = _strategy_module_for_sizing(strategy)
    seen = set()
    while mod is not None and id(mod) not in seen:
        seen.add(id(mod))
        if hasattr(mod, "run_backtest"):
            try:
                sp = inspect.signature(mod.run_backtest).parameters
            except (TypeError, ValueError):
                sp = {}
            if "vol_prior_ranges" in sp:
                return True
        mod = getattr(mod, "_base", None)
    return False


def _fetch_yf_daily():
    """Fresh QQQ DAILY bars from yfinance, regular session, unadjusted -- same
    auto_adjust=False convention as qp._fetch_yf's intraday pulls. Returns a
    DataFrame indexed by a DatetimeIndex with Open/High/Low/Close/Volume, or an
    empty DataFrame on ANY failure (network, rate limit, genuinely no data) --
    never raises. period="5y" is comfortably more than REQUIRED_LOOKBACK_SESSIONS
    (252) + margin ever needs and small enough to pull in one request, every time
    (no 7-day chunking like the 1m intraday path)."""
    import pandas as pd
    try:
        import yfinance as yf
        tkr = yf.Ticker(qp.TICKER)
        df = tkr.history(period="5y", interval="1d", prepost=False, auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    return df if df is not None else pd.DataFrame()


def _last_completed_session_date(now):
    """The most recent session date that should already be fully closed as of `now`:
    TODAY's own session once `now` is at/after its regular-session close (api.
    market_calendar.session_close_et) -- half-day aware -- else the most recent
    session date strictly BEFORE today. Used to decide whether the on-disk QQQ daily
    cache is stale (go-live audit item 3.8, critical fix 2026-09-26): the cache should
    always hold a finished bar for this date once it exists, whatever the wall-clock
    time is."""
    today = now.date()
    if market_calendar.is_session(today):
        close_et = market_calendar.session_close_et(today)
        hh, mm = (int(x) for x in close_et.split(":"))
        if now.time() >= _dt.time(hh, mm):
            return today
    d = today - _dt.timedelta(days=1)
    while not market_calendar.is_session(d):
        d -= _dt.timedelta(days=1)
    return d


def _drop_unfinished_session_rows(df, now, log=print):
    """Drop any row of an epoch-schema daily-bars DataFrame dated `now`'s own ET
    calendar date OR LATER, unless TODAY's own regular session has already closed as
    of `now` -- i.e. keep only FINISHED daily bars, matching what "after the close"
    means everywhere else in this bridge (critical fix, go-live audit item 3.8,
    2026-09-26: a stray in-progress row from yfinance -- e.g. a mid-session pull that
    returns today's own partial OHLC -- must never be stored or handed to a strategy
    as though it were a finished session). Applied both BEFORE this cache is written
    (fetch_and_merge_daily) and BEFORE it is read for use (vol_prior_ranges_for_leg /
    _daily_prior_sessions_available), so a row written by an older build, or by any
    other writer of this file, is filtered out here too. Never raises: any error
    reading `df` returns it unchanged rather than risk dropping good rows."""
    import pandas as pd
    if df is None or not len(df):
        return df
    try:
        needed = _last_completed_session_date(now)
        dates = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(TZ).dt.date
        kept = df[dates <= needed]
        return kept.reset_index(drop=True)
    except Exception as e:
        log(f"[cloud-signal] could not filter unfinished daily rows ({type(e).__name__}: {e}) "
            f"-- using the cache unfiltered this call")
        return df


def fetch_and_merge_daily(paths=None, now=None, log=print):
    """Refresh <home>/ohlc/QQQ_1d.csv from yfinance and return the merged epoch-schema
    DataFrame (one row per session), or None on any failure -- NEVER raises: a daily-
    cache miss just means vol_prior_ranges_for_leg passes nothing this call (see its
    own fail-safe). Same atomic write-beside-and-rename convention as fetch_and_merge
    (qp._replace_with_retry) -- this file is read by this same process's very next
    call and, in principle, a parallel replay/tool, exactly like QQQ_5m.csv/QQQ_1m.csv.

    Any row dated `now`'s own date or later is dropped before the merge is written
    (see _drop_unfinished_session_rows) unless today's own session has already
    closed -- a mid-session yfinance pull can return today's own partial daily bar,
    and "after the close" (the spec) means a FINISHED bar, never that one."""
    import pandas as pd
    paths = paths or DEFAULT_PATHS
    now = now or _dt.datetime.now(tz=_zi(TZ))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    path = _cache_path("1d", paths)
    old = load_cached_bars("1d", paths)
    if old is None:
        old = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    fresh_df = _fetch_yf_daily()
    fresh = qp._to_epoch_frame(fresh_df)
    fresh = _drop_unfinished_session_rows(fresh, now, log=log)
    if not len(fresh) and not len(old):
        return None
    merged = pd.concat([old, fresh], ignore_index=True)
    if len(merged):
        merged = merged.drop_duplicates("time", keep="last").sort_values("time")
    tmp = path + ".tmp"
    merged.to_csv(tmp, index=False)
    qp._replace_with_retry(tmp, path, log=log, what="[cloud-signal] 1d bar cache")
    return merged


def _daily_cache_refreshed_today(paths, now):
    """True iff <home>/ohlc/QQQ_1d.csv's own mtime already falls on `now`'s ET
    calendar date -- the refresh-at-most-once-a-day ATTEMPT gate for
    _maybe_refresh_daily_cache (kept exactly as before this fix: a failed fetch
    leaves the old file's mtime untouched, so the next tick the same day retries,
    same as always). False (never raises) when the file does not exist yet or its
    mtime can't be read."""
    try:
        import pandas as pd
        mtime = os.path.getmtime(_cache_path("1d", paths))
    except OSError:
        return False
    try:
        mdate = pd.Timestamp(mtime, unit="s", tz="UTC").tz_convert(TZ).date()
    except Exception:
        return False
    return mdate == now.date()


def _daily_cache_newest_date(paths):
    """The most recent session date already on disk in <home>/ohlc/QQQ_1d.csv, or
    None when the cache is missing, empty, or unreadable -- never raises."""
    try:
        df = load_cached_bars("1d", paths)
        if df is None or not len(df):
            return None
        import pandas as pd
        dates = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(TZ).dt.date
        return dates.max()
    except Exception:
        return None


def _daily_cache_refresh_due(now, paths):
    """True iff _maybe_refresh_daily_cache(now, paths) would fetch right now: no attempt
    yet on `now`'s ET date (the mtime gate) AND the cache is missing or older than
    _last_completed_session_date(now). Split out (2026-09-27) so api/cloud_signal_stream.py
    can ask "may a fetching step() still change QQQ_1d.csv today?" with the SAME test,
    without fetching. May raise on an unexpected error -- both callers wrap it."""
    if _daily_cache_refreshed_today(paths, now):
        return False
    newest = _daily_cache_newest_date(paths)
    return newest is None or newest < _last_completed_session_date(now)


def _maybe_refresh_daily_cache(now, paths, log=print):
    """Refresh the QQQ daily cache when it does not yet hold the last COMPLETED
    session (critical fix, go-live audit item 3.8, 2026-09-26): missing entirely, or
    its newest on-disk date is older than _last_completed_session_date(now) -- the
    session before today, or today itself once today's own regular-session close has
    passed. This is tied to what the cache actually HOLDS, not to `now`'s own
    time-of-day, because the live loops (cloud_signal_thread, cmd_loop) only ever
    call step() during RTH_OPEN..RTH_CLOSE -- a pure time-of-day gate at the session
    close overlaps that window at a single instant and the cache was never refreshed
    in practice (see this function's own history for the bug this replaced).

    Still refreshes AT MOST ONCE PER CALENDAR DAY (the mtime/attempt gate above,
    unchanged) even when the cache is stale for a reason this can't fix (e.g.
    yfinance genuinely has nothing new yet) -- this never hammers the network every
    tick. A non-session day (weekend/holiday) still only ever attempts once, since
    the cache is never stale relative to `_last_completed_session_date` past the
    first successful refresh that already covers it. Never raises -- any failure
    here just leaves the existing on-disk cache (or none) in place for
    vol_prior_ranges_for_leg to read, which is already its own fail-safe path."""
    try:
        if not _daily_cache_refresh_due(now, paths):
            return
        fetch_and_merge_daily(paths, now=now, log=log)
    except Exception as e:
        log(f"[cloud-signal] QQQ daily cache refresh failed ({type(e).__name__}: {e}) -- "
            f"vol_prior_ranges continues off whatever is already cached, if anything")


def _session_ranges_from_5m(arrays):
    """{date: (H-L)/C} for every distinct session already in this leg's live intraday
    `arrays` -- the same per-session reduction NOISE_1_0.py's own _vol_percentile
    does internally, read off the live cache instead of a backtest master. Used ONLY
    to calibrate the daily series onto the same scale (see _calibrate_daily_ranges);
    never itself handed to a strategy."""
    import numpy as np
    h, l, c, day_id, idx = (arrays["high"], arrays["low"], arrays["close"],
                            arrays["day_id"], arrays["index"])
    out = {}
    n = len(day_id)
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        out[idx[a].date()] = (float(np.max(h[a:b])) - float(np.min(l[a:b]))) / float(c[b - 1])
        a = b
    return out


def _daily_ranges_by_date(daily_df):
    """{date: (H-L)/C} from an epoch-schema daily bars DataFrame (time/open/high/low/
    close/volume, one row per session -- QQQ_1d.csv's own schema). Skips any row with
    a non-positive close (can't compute a ratio off it)."""
    import pandas as pd
    dates = pd.to_datetime(daily_df["time"], unit="s", utc=True).dt.tz_convert(TZ).dt.date
    out = {}
    for dt, h, l, c in zip(dates, daily_df["high"], daily_df["low"], daily_df["close"]):
        c = float(c)
        if c > 0:
            out[dt] = (float(h) - float(l)) / c
    return out


def _log_fail_safe_once(reason_key, msg, log=print):
    """Logs `msg` at most once per ET calendar date per `reason_key` (minor fix,
    go-live audit item 3.8, 2026-09-26): every vol_prior_ranges fail-safe reason used
    to log on EVERY call -- about 78 times a day for NOISE_382's own 5m cadence --
    because only the calibration line itself had a once-a-day latch. Keyed by
    `reason_key` (a short fixed label, not the formatted message text, which carries
    numbers that legitimately change tick to tick) so each distinct reason still gets
    its own once-a-day line, but the SAME reason on the next bar/tick that same date
    stays silent. Shares its date-rollover bookkeeping with _DAILY_CALIBRATION_LOG so
    a fresh calendar date resets every reason's latch together."""
    today = _dt.datetime.now(tz=_zi(TZ)).date()
    if _DAILY_CALIBRATION_LOG.get("date") != today:
        _DAILY_CALIBRATION_LOG["date"] = today
        _DAILY_CALIBRATION_LOG["reasons"] = set()
    reasons = _DAILY_CALIBRATION_LOG.setdefault("reasons", set())
    if reason_key in reasons:
        return
    reasons.add(reason_key)
    log(msg)


def _calibrate_daily_ranges(daily_df, arrays, now=None, log=print):
    """Median ratio of 5m-derived (H-L)/C to Yahoo-DAILY (H-L)/C over the sessions
    BOTH sources cover (the live intraday `arrays`' own sessions), plus that overlap
    count. Logged ONCE per ET calendar date (not per leg, not per tick).

    JUDGED-DAY LEAK (minor fix, go-live audit item 3.8, 2026-09-26): the live
    intraday `arrays`' own LAST session is dropped from the overlap before
    calibrating whenever `now` is given and that session's date is `now`'s own date
    or later, or _session_in_progress(arrays, now) says the window is mid-build --
    in replay, the daily cache already holds the replayed day's own FINISHED bar
    while `arrays` only holds part of it; live, this only matters if a stray
    in-progress row ever reached this far (see _drop_unfinished_session_rows, which
    should already have kept it out). Either way, letting the session being judged
    leak into its own scale factor is a small bias this avoids. `now=None` (every
    call site that predates this parameter) skips the check entirely -- byte-
    identical to before it existed.

    Returns (ratio, overlap_n): ratio is None -- meaning "pass nothing, fail safe" --
    whenever the overlap is thinner than DAILY_MIN_OVERLAP_SESSIONS or the median
    ratio itself falls outside [DAILY_CALIBRATION_RATIO_MIN, DAILY_CALIBRATION_RATIO_MAX]
    (a daily bar and an RTH-only 5m session's own (H-L)/C should be close -- QQQ barely
    trades outside RTH -- so a ratio far from 1.0 means the two series are not lining up
    the way this bridge assumes, e.g. a date-alignment bug or a corrupted cache, and
    scaling by it would be trusting a broken calibration rather than fixing one)."""
    import numpy as np
    five_min = _session_ranges_from_5m(arrays)
    if now is not None and five_min:
        idx = arrays.get("index")
        last_date = idx[-1].date() if idx is not None and len(idx) else None
        if last_date is not None and (last_date >= now.date()
                                      or _session_in_progress(arrays, now)):
            five_min = dict(five_min)
            five_min.pop(last_date, None)
    daily = _daily_ranges_by_date(daily_df)
    overlap = sorted(set(five_min) & set(daily))
    n = len(overlap)
    ratios = [five_min[d] / daily[d] for d in overlap if daily[d] > 0]
    ratio = float(np.median(ratios)) if ratios else None
    today = _dt.datetime.now(tz=_zi(TZ)).date()
    if _DAILY_CALIBRATION_LOG.get("date") != today:
        _DAILY_CALIBRATION_LOG["date"] = today
        _DAILY_CALIBRATION_LOG["reasons"] = set()
        log(f"[cloud-signal] vol_prior_ranges calibration: {n} overlap session(s) between "
            f"the 5m cache and QQQ daily bars, 5m/daily (H-L)/C median ratio = "
            + (f"{ratio:.4f}" if ratio is not None else "n/a"))
    if ratio is None:
        _log_fail_safe_once(
            "no_valid_overlap",
            "[cloud-signal] vol_prior_ranges: no valid overlap ratios -- passing nothing", log)
        return None, n
    if n < DAILY_MIN_OVERLAP_SESSIONS:
        _log_fail_safe_once(
            "thin_overlap",
            f"[cloud-signal] vol_prior_ranges: only {n} overlap session(s) "
            f"(< {DAILY_MIN_OVERLAP_SESSIONS} required) -- passing nothing", log)
        return None, n
    if not (DAILY_CALIBRATION_RATIO_MIN <= ratio <= DAILY_CALIBRATION_RATIO_MAX):
        _log_fail_safe_once(
            "ratio_out_of_band",
            f"[cloud-signal] vol_prior_ranges: calibration ratio {ratio:.4f} outside "
            f"[{DAILY_CALIBRATION_RATIO_MIN}, {DAILY_CALIBRATION_RATIO_MAX}] -- passing nothing", log)
        return None, n
    return ratio, n


def vol_prior_ranges_for_leg(cfg, arrays, now, paths=None, fetch=False, log=print):
    """The list of calibrated prior-session (H-L)/C values (oldest first) to hand
    this leg's engine call as vol_prior_ranges -- see NOISE_1_0.py's own kwarg -- or
    None when the leg's strategy does not declare it, its strategy declares no
    REQUIRED_LOOKBACK_SESSIONS, the daily cache can't be built/read, or calibration
    fails (see _calibrate_daily_ranges). `fetch` gates the ONE network call this can
    make (refreshing QQQ_1d.csv) -- False (the default) never touches the network,
    same convention as fetch_and_merge/`step`'s own fetch flag; a replay or a test
    passes/leaves this False and reads only whatever is already on disk, if anything.

    FAIL-SAFE: any exception anywhere in this function is caught, logged once, and
    treated as "pass nothing" -- this never raises and never blocks step()."""
    try:
        if not _leg_accepts_vol_prior_ranges(cfg.get("strategy")):
            return None
        need = required_lookback_sessions(cfg.get("strategy"))
        if need is None:
            return None
        first_date = arrays["index"][0].date()
        paths = paths or DEFAULT_PATHS
        if fetch:
            _maybe_refresh_daily_cache(now, paths, log=log)
        daily_df = load_cached_bars("1d", paths)
        if daily_df is None or not len(daily_df):
            _log_fail_safe_once(
                "missing_cache",
                "[cloud-signal] vol_prior_ranges: QQQ_1d.csv is missing or empty -- "
                "passing nothing until it exists", log)
            return None
        # Defense in depth (critical fix, go-live audit item 3.8): filter out any
        # unfinished-session row again at READ time, not only at fetch_and_merge_daily's
        # write time -- a cache written by an older build, or by any other writer of
        # this file, could still hold a stray in-progress row.
        daily_df = _drop_unfinished_session_rows(daily_df, now, log=log)
        if daily_df is None or not len(daily_df):
            _log_fail_safe_once(
                "missing_cache",
                "[cloud-signal] vol_prior_ranges: QQQ_1d.csv has no finished session yet -- "
                "passing nothing until it does", log)
            return None
        ratio, _overlap_n = _calibrate_daily_ranges(daily_df, arrays, now=now, log=log)
        if ratio is None:
            return None
        daily = _daily_ranges_by_date(daily_df)
        prior_dates = sorted(d for d in daily if d < first_date)
        keep = need + DAILY_MARGIN_SESSIONS
        prior_dates = prior_dates[-keep:]
        if not prior_dates:
            return None
        return [ratio * daily[d] for d in prior_dates]
    except Exception as e:
        log(f"[cloud-signal] vol_prior_ranges unavailable ({type(e).__name__}: {e}) -- "
            f"passing nothing this call")
        return None


def _daily_prior_sessions_available(tf, paths, need):
    """Best-effort count of QQQ daily-bar sessions cached STRICTLY BEFORE the `tf`
    intraday cache's own first session -- i.e. an upper bound on what the
    vol_prior_ranges bridge could contribute, ignoring calibration (a STARTUP
    diagnostic only -- see log_history_windows; the real, calibration-gated count is
    computed fresh every tick by vol_prior_ranges_for_leg). 0 on any missing cache or
    read failure -- never raises."""
    try:
        epoch_df = load_cached_bars(tf, paths)
        if epoch_df is None or not len(epoch_df):
            return 0
        arrays = build_arrays(epoch_df)
        if arrays is None or not len(arrays.get("close", [])):
            return 0
        first_date = arrays["index"][0].date()
        daily_df = load_cached_bars("1d", paths)
        if daily_df is None or not len(daily_df):
            return 0
        daily = _daily_ranges_by_date(daily_df)
        n = sum(1 for d in daily if d < first_date)
        return min(n, need + DAILY_MARGIN_SESSIONS)
    except Exception:
        return 0


# ── RESTING LEVELS (2026-09-29, resting ORB stops -- design section 2) ─────────────────────
# ONE source of truth for the levels a resting Webull stop / OCO target is placed at: the
# engine itself. A leg with cfg["resting_levels"] (ORB_R6 only) whose strategy explicitly
# names a `return_levels` keyword (ORB_3_6.py -- a bare **kwargs does not count, same
# reflection rule as session_in_progress) gets return_levels=True on a PER-CALL copy of
# its params; the engine then reports, per trade, the initial stop, the target, the
# breakeven trigger and the bar at whose close breakeven armed. run_leg_trades rounds
# them to cents and hangs them on the trade as t["levels"]; _diff_leg writes stop_px /
# target_px on the ENTRY row and ONE "LEVELS" row (never an ENTRY/EXIT -- api/qqq_exec.py
# ignores every other event type until it learns this one) when breakeven moves the stop.
#
# CENT ROUNDING IN THE BACKTEST'S OWN TRIGGER DIRECTION. The backtest fills a long's stop
# when low <= stop and its target when high >= target (a short: high >= stop, low <=
# target). On a one-cent price grid those tests are EXACTLY "low <= floor(stop)" and
# "high >= ceil(target)", so: sell stop DOWN, buy stop UP, sell target UP, buy target
# DOWN -- the order rests where the engine's own bar test would first fire, never
# earlier. RESTING_CENT_TOL absorbs the float32 noise of the bar cache (732.33 is stored
# as 732.330017), which must not push a level a whole cent away. The one case this cannot
# match is a float TIE: a level that is a whole cent up to float noise (entry + 12.5 x an
# even-cent range) touched exactly by a bar -- the backtest's float compare decides that
# by 1e-13, Webull by the cent (tests/test_orb_resting_levels.py: none in 62 real QQQ
# sessions, 1 in 73 synthetic cent-grid trades). A sub-penny print beyond the level but
# short of the cent is invisible to a cent-priced order too. The breakeven TRIGGER is
# the engine's own bar-close test and is never sent to Webull, so it is shown to the
# nearest cent. 09-28's short (entry 732.33, range 3.375, ORB #314): buy stop 740.77,
# breakeven trigger 728.11, target 690.14.
RESTING_CENT_TOL = 1e-4          # dollars; below any real tick, above float32 noise


def _leg_accepts_return_levels(strategy):
    """True iff `strategy`'s run_backtest explicitly names a `return_levels` parameter --
    the _leg_accepts_session_in_progress convention (a bare **kwargs catch-all does not
    count). Best-effort/never-raises."""
    mod = _strategy_module_for_sizing(strategy)
    if mod is None or not hasattr(mod, "run_backtest"):
        return False
    try:
        sp = inspect.signature(mod.run_backtest).parameters
    except (TypeError, ValueError):
        return False
    return "return_levels" in sp


# ── DECISION BARS (2026-10-05, NOISE lane audit / MANAGER #65) ───────────────────────────
# The Webull box decides NOISE on live 5m QQQ bars that Webull sometimes revises afterwards,
# and the bar cache keeps only the revised bar -- so an audit could only INFER what the
# engine saw (09-25: a close 2.2c higher made an extra long; 09-28: a thinner opening bar
# moved the VWAP and exited a short early). A leg whose strategy chain names a
# `return_decisions` keyword (NOISE_1_0.py, reached through NOISE_1_1_NBHD.py and
# NOISE_1_8_CT304.py / NOISE_1_8_CT304H.py, which forward it) gets return_decisions=True on
# a PER-CALL copy of its params; the plugin then reports, per trade, the bar, VWAP and band
# its own loop compared at the entry decision and at the exit decision (NOISE_1_0.py's
# DECISION RECORD). run_leg_trades hangs them on the trade as t["decision"] and _diff_leg
# writes them into SIGNAL_COLS' dec_* columns on the ENTRY / EXIT row. LOGGING ONLY: no
# trade, size, time or price changes (tests/test_noise_decision_log.py runs the step with
# and without it and compares every decision field). No extra network: the record rides on
# the engine call step() already makes. LOG_DECISION_BARS = False switches it off whole.
LOG_DECISION_BARS = True


def _leg_accepts_return_decisions(strategy):
    """True iff `strategy` -- or a module down its `_base` chain (the
    _leg_accepts_vol_prior_ranges walk: NOISE's wrappers forward this keyword) -- has a
    run_backtest that explicitly names `return_decisions`. A bare **kwargs does not count.
    Best-effort/never-raises."""
    mod = _strategy_module_for_sizing(strategy)
    seen = set()
    while mod is not None and id(mod) not in seen:
        seen.add(id(mod))
        if hasattr(mod, "run_backtest"):
            try:
                sp = inspect.signature(mod.run_backtest).parameters
            except (TypeError, ValueError):
                sp = {}
            if "return_decisions" in sp:
                return True
        mod = getattr(mod, "_base", None)
    return False


def _dec_num(x):
    """A decision-record number for the ledger: the float exactly as the engine held it
    (shortest repr, no rounding -- a 0.1c gap is the whole point of the audit); a volume
    that is a whole number prints as one; None/NaN -> ""."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(x):
        return ""
    return x


def _trade_decision(rec, entry_bar, side, idx, n_bars, tf):
    """{"entry": {dec_* row fields}, "exit": {...}} from one entry of the engine's
    out["decisions"] (see DECISION BARS), or None when the record does not describe THIS
    trade (its entry decision must be the bar right before `entry_bar`, on this trade's
    side). A side whose bar index falls outside `idx` is None. NEVER RAISES: this is
    logging only, so a malformed record (any exception at all) just blanks the dec_*
    columns -- it must never cost the leg its trades for the tick."""
    try:
        return _trade_decision_inner(rec, entry_bar, side, idx, n_bars, tf)
    except Exception:
        return None


def _trade_decision_inner(rec, entry_bar, side, idx, n_bars, tf):
    if not isinstance(rec, dict):
        return None
    try:
        ent = rec.get("entry") or {}
        if int(ent.get("bar")) != int(entry_bar) - 1:
            return None
        if (ent.get("rule") == "close>upper") != (side > 0):
            return None
    except (TypeError, ValueError):
        return None
    step_td = None
    if tf in TIMEFRAME_SECONDS:
        step_td = _dt.timedelta(seconds=TIMEFRAME_SECONDS[tf])

    def one(d):
        if not isinstance(d, dict):
            return None
        try:
            b = int(d.get("bar"))
        except (TypeError, ValueError):
            return None
        if not 0 <= b < n_bars:
            return None
        start = idx[b]
        vol = _dec_num(d.get("volume"))
        if vol != "" and float(vol).is_integer():
            vol = int(vol)
        return {
            "_bar": b,            # index into THIS call's arrays; never written to the ledger
            "dec_bar_start": start.isoformat(),
            "dec_bar_end": (start + step_td).isoformat() if step_td is not None else "",
            "dec_open": _dec_num(d.get("open")), "dec_high": _dec_num(d.get("high")),
            "dec_low": _dec_num(d.get("low")), "dec_close": _dec_num(d.get("close")),
            "dec_volume": vol, "dec_vwap": _dec_num(d.get("vwap")),
            "dec_band_upper": _dec_num(d.get("upper")),
            "dec_band_lower": _dec_num(d.get("lower")),
            "dec_rule": str(d.get("rule") or ""), "dec_level": _dec_num(d.get("level")),
        }
    out = {"entry": one(rec.get("entry")), "exit": one(rec.get("exit"))}
    return out if out["entry"] is not None else None


def _decision_cols(t, which, bar_source):
    """The dec_* fields for one ENTRY ("entry") or EXIT ("exit") row of trade `t`, or {}
    when it carries no record for that side (every non-NOISE leg) -- the row then leaves
    every dec_* column blank, exactly as before they existed."""
    dec = t.get("decision") if isinstance(t, dict) else None
    side = dec.get(which) if isinstance(dec, dict) else None
    if not side:
        return {}
    out = {k: v for k, v in side.items() if k in DECISION_COLS}
    # "cache": an offline step (replay, a test) read the on-disk bars with no feed named
    out["dec_bar_source"] = bar_source or "cache"
    return out


def _cent_level(px, up):
    """`px` rounded to a whole cent, UP (ceil) or DOWN (floor) -- see RESTING LEVELS. None
    for a missing or non-finite price."""
    try:
        px = float(px)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(px):
        return None
    cents = px * 100.0
    near = round(cents)
    if abs(cents - near) <= RESTING_CENT_TOL * 100.0:
        cents = near
    return round((math.ceil(cents) if up else math.floor(cents)) / 100.0, 2)


def _trade_levels(lv, entry_bar, side, entry_px, idx, n_bars):
    """The cent-rounded levels one trade rests at (see RESTING LEVELS), from one entry of
    the engine's out["levels"]; None when the row does not describe THIS trade or cannot
    be rested from (a trailing stop or a partial exit moves the stop in ways it does not
    list) -- the leg then simply has no levels and ORB keeps today's engine exit.
        stop_px        initial protective stop (sell stop DOWN for a long, buy stop UP)
        target_px      target (sell limit UP, buy limit DOWN); None with target_R 0
        be_trigger_px  the bar close that arms breakeven (nearest cent; engine-only)
        be_stop_px     the stop from the bar AFTER that close (= entry, same rounding)
        be_armed_time  start of the bar whose CLOSE armed breakeven, or None
    """
    if not isinstance(lv, dict) or lv.get("trail") or lv.get("partial"):
        return None
    try:
        if int(lv.get("entry_bar")) != int(entry_bar) or int(lv.get("side")) != int(side):
            return None
        if abs(float(lv.get("entry")) - float(entry_px)) > 1e-9 * max(1.0, abs(float(entry_px))):
            return None
    except (TypeError, ValueError):
        return None
    long_ = side > 0
    stop_px = _cent_level(lv.get("stop"), up=not long_)
    if stop_px is None:
        return None
    target_px = _cent_level(lv.get("target"), up=long_)
    be_trigger_px = None
    if lv.get("be_trigger") is not None:
        try:
            be_trigger_px = round(float(lv["be_trigger"]), 2)
        except (TypeError, ValueError):
            be_trigger_px = None
    be_stop_px = _cent_level(lv.get("be_stop"), up=not long_)
    be_armed_time = None
    be_bar = lv.get("be_bar")
    if be_bar is not None and be_stop_px is not None:
        try:
            be_bar = int(be_bar)
            if 0 <= be_bar < n_bars:
                be_armed_time = idx[be_bar].isoformat()
        except (TypeError, ValueError, IndexError):
            be_armed_time = None
    return {"stop_px": stop_px, "target_px": target_px, "be_trigger_px": be_trigger_px,
            "be_stop_px": be_stop_px, "be_armed_time": be_armed_time}


# ── One leg's trades -> canonical records ────────────────────────────────────────────────
class _TradeSizeContractError(Exception):
    """Raised by _resolve_trade_sizes when a plugin DECLARES the additive per-trade
    size contract (trade_sizes/size_cost_pts -- see NOISE_1_8_CT304.py's ADDITIVE
    SIZE CONTRACT comment) but the declaration itself is broken. Always caught by
    run_leg_trades, which fails that leg's WHOLE call closed rather than guess."""


def _leg_label(cfg, leg_key):
    """Best-effort human-readable name for a leg in a log line, for a caller (a
    test, or a standalone tool) that did not pass leg_key -- step() always does."""
    if leg_key:
        return str(leg_key)
    strat = cfg.get("strategy")
    if isinstance(strat, str):
        return strat
    return getattr(strat, "STRATEGY_NAME", None) or getattr(strat, "__name__", None) or repr(strat)


def _resolve_trade_sizes(res, n_trades, label):
    """Validates the additive per-trade size contract a sizing plugin's result dict
    may carry (trade_sizes: list of floats, same length/order as `trades`;
    size_cost_pts: the cost constant it folded in -- see NOISE_1_8_CT304.py's
    ADDITIVE SIZE CONTRACT comment). Returns (sizes, cost) -- a list of validated
    floats and a float -- when the contract is present and sound, or (None, None)
    when the plugin simply does not size at all (no `trade_sizes` key: the ordinary,
    unaffected case). Raises _TradeSizeContractError the instant a DECLARED contract
    looks wrong in any way -- caught by run_leg_trades, which fails that whole call
    closed rather than guess. There is no partial-credit path: a badly-declared size
    is exactly as dangerous as an undeclared one, so a broken declaration is never
    quietly treated as "not sizing".
    """
    sizes = res.get("trade_sizes")
    if sizes is None:
        return None, None
    cost = res.get("size_cost_pts")
    if cost is None:
        raise _TradeSizeContractError(
            f"{label}: trade_sizes present ({len(sizes)} value(s)) but size_cost_pts is missing")
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        raise _TradeSizeContractError(f"{label}: size_cost_pts {cost!r} is not a number")
    if not math.isfinite(cost):
        raise _TradeSizeContractError(f"{label}: size_cost_pts {cost!r} is not finite")
    if len(sizes) != n_trades:
        raise _TradeSizeContractError(
            f"{label}: trade_sizes has {len(sizes)} entries for {n_trades} trade(s)")
    out = []
    for idx, s in enumerate(sizes):
        try:
            sf = float(s)
        except (TypeError, ValueError):
            sf = float("nan")
        if not math.isfinite(sf) or sf <= 0:
            raise _TradeSizeContractError(
                f"{label}: trade_sizes[{idx}] = {s!r} is not a finite positive size")
        out.append(sf)
    return out, cost


def run_leg_trades(cfg, arrays, leg_key=None, log=print, now=None, paths=None, fetch=False):
    """Runs the plugin (or a stub module override) via the shared engine wrapper and
    converts the raw (entry_bar, exit_bar, pnl_pts, side, entry_px) tuples into
    canonical dicts keyed by wall-clock timestamps (not bar indices — those are only
    valid for the exact arrays slice they came from, and the rolling window's start
    shifts every call).

    PER-TRADE SIZE (2026-09-23). A sizing plugin (NOISE_1_8_CT304.py today; the KEEL
    overlay later) can additively declare trade_sizes/size_cost_pts in its result dict
    -- see that file's ADDITIVE SIZE CONTRACT comment and this module's
    _resolve_trade_sizes. When declared and valid, every trade dict below carries the
    real per-trade size in "size" and a real, inverted exit_px. A plugin that never
    sizes gets "size": 1.0 on every trade and the exact exit_px arithmetic this
    function has always used -- byte-for-byte unaffected. A plugin whose declaration
    is broken (see _resolve_trade_sizes) fails the WHOLE call closed: this returns []
    and logs why, rather than guess at a price that would mis-size every order
    downstream.

    SESSION-IN-PROGRESS PASS-THROUGH (item 15, see the block comment above
    _leg_accepts_session_in_progress). `now` is optional and defaults to None -- every
    call site that predates this feature (tests, tools) keeps calling this with no
    `now` and gets exactly today's behaviour, cfg["params"] untouched. Only step()
    passes the real `now`, and only a leg whose strategy opted in AND whose window's
    last session is today's own (still-forming) session gets a PER-CALL copy of its
    params with session_in_progress=True added -- cfg["params"] itself is never
    mutated, so the next call (a different `now`) recomputes this fresh.

    VOL_PRIOR_RANGES PASS-THROUGH (go-live audit item 3.8, see the block comment above
    _leg_accepts_vol_prior_ranges). Same `now`-gated, per-call-copy convention as
    session_in_progress just above -- `paths`/`fetch` are new, optional, and default to
    (None -> DEFAULT_PATHS) / False, so every pre-existing call site is unaffected and
    touches no network. Only step() passes the real `paths`/`fetch`. `paths` must be
    passed EXPLICITLY (not just `now`) for this bridge to run at all (minor fix,
    go-live audit item 3.8, 2026-09-26): a caller that passes `now` alone used to
    still read the live DEFAULT_PATHS QQQ_1d.csv for an opted-in leg -- a read-only,
    fetch=False read, but one an isolated test or tool calling this with `now` (to
    exercise session_in_progress, say) never asked for and had no way to avoid. Give
    such a call its own `paths` (an isolated dict, or DEFAULT_PATHS on purpose) to opt
    into the daily-cache bridge too.

    RESTING LEVELS (2026-09-29, see the block comment above _leg_accepts_return_levels).
    Only for a cfg["resting_levels"] leg whose strategy names `return_levels`: the call
    also gets return_levels=True (per-call copy again) and every trade dict gains a
    "levels" key (_trade_levels, or None when the engine's row cannot be rested from).
    Every other leg's call and trade dicts are exactly as before -- no "levels" key.

    DECISION BARS (2026-10-05, see the block above _leg_accepts_return_decisions). Only for
    a leg whose strategy chain names `return_decisions` (NOISE): the call also gets
    return_decisions=True (per-call copy) and every trade dict gains a "decision" key --
    {"entry": dec_* fields, "exit": dec_* fields or None while the trade is still open},
    or None when the engine's record does not line up with the trade. Read-only: no other
    key of any trade dict changes. Every other leg: no "decision" key.
    """
    params = cfg["params"]
    extra = {}
    want_levels = bool(cfg.get("resting_levels")) and _leg_accepts_return_levels(cfg["strategy"])
    if want_levels:
        extra["return_levels"] = True
    # DECISION BARS (see the block above _leg_accepts_return_decisions): read-only record
    want_decisions = LOG_DECISION_BARS and _leg_accepts_return_decisions(cfg["strategy"])
    if want_decisions:
        extra["return_decisions"] = True
    if now is not None and _leg_accepts_session_in_progress(cfg["strategy"]) \
            and _session_in_progress(arrays, now):
        extra["session_in_progress"] = True
    if now is not None and paths is not None:
        prior_ranges = vol_prior_ranges_for_leg(cfg, arrays, now, paths=paths, fetch=fetch, log=log)
        if prior_ranges:
            extra["vol_prior_ranges"] = prior_ranges
    if extra:
        params = dict(params)
        params.update(extra)
    res = engine_run_backtest(cfg["strategy"], arrays=arrays, params=params,
                              cost_pts=0.0, return_trades=True)
    if not res or not res.get("trades"):
        return []
    idx = arrays["index"]
    n_bars = len(arrays["close"])
    last_close = float(arrays["close"][n_bars - 1])

    trades_raw = res["trades"]
    label = _leg_label(cfg, leg_key)
    levels_raw = None
    if want_levels:
        levels_raw = res.get("levels")
        if not isinstance(levels_raw, (list, tuple)) or len(levels_raw) != len(trades_raw):
            # never guess which level belongs to which trade -- no levels, today's exits
            log(f"[cloud-signal] {label}: engine levels missing or misaligned "
                f"({'none' if levels_raw is None else len(levels_raw)} for "
                f"{len(trades_raw)} trade(s)) -- no resting levels this call")
            levels_raw = None
    decisions_raw = None
    if want_decisions:
        decisions_raw = res.get("decisions")
        if not isinstance(decisions_raw, (list, tuple)) or len(decisions_raw) != len(trades_raw):
            # never guess which record belongs to which trade -- the rows just stay blank,
            # and say so (a blank dec_bar_source otherwise reads like a non-NOISE row)
            log(f"[cloud-signal] {label}: engine decision records missing or misaligned "
                f"({'none' if decisions_raw is None else (len(decisions_raw) if isinstance(decisions_raw, (list, tuple)) else type(decisions_raw).__name__)} for "
                f"{len(trades_raw)} trade(s)) -- dec_* columns blank this call")
            decisions_raw = None
    try:
        leg_sizes, size_cost_pts = _resolve_trade_sizes(res, len(trades_raw), label)
    except _TradeSizeContractError as e:
        log(f"[cloud-signal] {e} -- refusing to emit signals for {label} this call "
           f"(a wrong size inversion would mis-price every order it sends)")
        return []
    sizes_declared = leg_sizes is not None

    # PRICE-BASED "STILL OPEN AT THE BOUNDARY" TEST -- SAFE ONLY WHEN THE LEG PROMISES
    # eod_marks_at_close (default True; see the AMBIGUOUS BOUNDARY comment in the loop
    # below). Two known ways a plugin can break that promise, and what makes each safe
    # (2026-09-22 audit; sizing contract added 2026-09-23):
    #   - ORB_3_6.py:346-350's EOD-flat block does not always mark an unresolved end-of-
    #     data position at a clean last-bar close: whenever a partial exit already fired
    #     (p_done, gated on `partial_exit_R > 0` at ORB_3_6.py:320 and :338), the reported
    #     pnl is a 50/50 blend of the partial fill and the final close (line 348), so the
    #     price test would usually read the still-half-open position as a genuine close.
    #     The live ORB_R6 leg pins partial_exit_R=0.0 (api/paper.py:177-180, ORB_314), so
    #     this is inert today -- but that is a PARAMS fact, not a code fact, and a params
    #     change must not silently arm a mechanism that flattens a live position early.
    #     Checked explicitly below, every call, unrelated to sizing.
    #   - A plugin that folds a per-trade size multiplier into pnl_pts (NOISE_1_8_CT304.py
    #     -- see its ADDITIVE SIZE CONTRACT comment) breaks the exit-price reconstruction
    #     UNLESS it declares trade_sizes/size_cost_pts: `sizes_declared` above is only
    #     True once that declaration has passed _resolve_trade_sizes, at which point the
    #     fold is inverted below and exit_px is real again -- the price test needs no help
    #     from this leg's cfg. The manual escape hatch (cfg["eod_marks_at_close"] = False)
    #     is required ONLY for a plugin that folds size into pnl_pts WITHOUT declaring it:
    #     there is no way to detect that case from the result dict alone, so it stays an
    #     explicit, manual promise on the leg config -- exactly as before this contract
    #     existed.
    # A leg opts out of the price test -- falling back to the OLD, conservative rule that
    # ANY trade still sitting at the boundary reads as open, price notwithstanding -- via
    # an explicit cfg["eod_marks_at_close"] = False (ALWAYS honoured, even when sizes are
    # declared) or automatically the moment its own declared params turn on
    # ORB's partial-exit blend. An explicit True never overrides the partial_exit_R check;
    # only the strategy's own params, or a validated size declaration, can prove the price
    # safe.
    _partial_exit_r = float((cfg.get("params") or {}).get("partial_exit_R") or 0)
    # An explicit eod_marks_at_close=False is ALWAYS honoured, sizes declared or not: the
    # conservative rule can only delay an exit by a bar, never invent one, so a caution a
    # human wrote on a leg must not be overridden by a contract they may not know about.
    # A valid size declaration only removes the NEED for that flag on a size-folding leg.
    _eod_promise = cfg.get("eod_marks_at_close", True)
    eod_marks_at_close = _eod_promise and not (_partial_exit_r > 0)
    # EOD FLAT (2026-09-28, see EOD SETTLE above cloud_signal_thread). A leg flagged
    # cfg["eod_flat"] promises its strategy flattens every position at the close of the
    # session's LAST bar. When this window ends on exactly that bar, the session is
    # complete, so a trade whose exit is that bar really closed there -- the backtest's
    # own end-of-day fill -- and is not "still open because the data ran out". Without
    # this, the day's last exits were only emitted the next morning. Never applied with
    # ORB's partial-exit blend on (its boundary price is not a clean close, see above).
    _tf = cfg.get("timeframe")
    eod_flat_close = False
    if cfg.get("eod_flat") and not (_partial_exit_r > 0) and _tf in TIMEFRAME_SECONDS:
        try:
            eod_flat_close = _is_session_last_bar(idx[n_bars - 1], _tf)
        except Exception:
            eod_flat_close = False

    if sizes_declared:
        paired = list(zip(trades_raw, leg_sizes))
    else:
        paired = [(t, 1.0) for t in trades_raw]
    # the engine's levels ride with their trade through the sort (same order as trades_raw)
    paired = [p + (levels_raw[n] if levels_raw is not None else None,)
              for n, p in enumerate(paired)]
    # ... and so does each trade's decision record (DECISION BARS)
    paired = [p + (decisions_raw[n] if decisions_raw is not None else None,)
              for n, p in enumerate(paired)]
    paired.sort(key=lambda p: p[0][0])

    out = []
    for (entry_bar, exit_bar, pnl_pts, side, entry_px), size, lv, dec in paired:
        entry_bar = int(entry_bar); exit_bar = int(exit_bar)
        entry_px = float(entry_px)
        if sizes_declared:
            # INVERTED EXIT PRICE (2026-09-23): the plugin folded
            # pts = size*raw - (size-1)*size_cost_pts before handing this trade back
            # (see its ADDITIVE SIZE CONTRACT comment); this is the exact algebraic
            # inverse, recovering the real raw price move, so exit_px below is a real
            # price again -- not a synthetic, cost/size-scaled number.
            raw = (pnl_pts + (size - 1.0) * size_cost_pts) / size
            exit_px = entry_px + raw * side
        else:
            # UNCHANGED: reconstructed from entry_px and the reported pnl_pts alone,
            # which is only ever the real fill price when pnl_pts is a raw price
            # difference -- true for every plugin that does not fold a size multiplier
            # into it.
            exit_px = entry_px + pnl_pts * side
        if exit_bar < n_bars - 1:
            still_open = False
        elif eod_flat_close:
            # the session's last bar: an eod_flat strategy is flat here (see EOD FLAT above)
            still_open = False
        elif not eod_marks_at_close:
            # OLD, conservative rule for a leg whose boundary price can't be trusted (see
            # above): any trade still sitting at the boundary reads as open, no matter
            # what its (possibly blended or synthetic) reported price says.
            still_open = True
        else:
            # AMBIGUOUS BOUNDARY (2026-09-22): every plugin reachable here with
            # eod_marks_at_close true force-closes a position that is still open when its
            # data runs out by marking it at the newest bar's own CLOSE (NOISE_1_0.py's
            # "STEP E" EOD backstop, ORB_3_6.py's "EOD flat" block when no partial exit
            # has fired, ENGUQ_1M_ETH_R2_1_0.py's end-of-walk fallback and its compiled
            # twin in augur_engine/fastloop.py's _walk_jit all do this). So exit_bar ==
            # n_bars - 1 is produced BOTH by a position that is genuinely still open (the
            # strategy simply ran out of bars) and by one that closed for real exactly on
            # the newest bar — the two are NOT distinguishable by bar index alone, which
            # is what the old `exit_bar >= n_bars - 1` rule assumed, and why every real
            # exit on the newest bar was emitted a bar late and collided with whatever
            # entered next.
            #
            # They ARE distinguishable by price: a genuine close can land anywhere (an
            # open-fill, a stop or band level, ...), but the data-end fallback is ALWAYS
            # the last bar's own close, exactly. So a reported exit price that differs
            # from that close by more than a hair means the position really closed; one
            # that matches it means the plugin never got a chance to do anything but the
            # boilerplate flatten, i.e. it is still open. Relative tolerance, not exact
            # equality: pnl_pts round-trips through a subtraction (close - entry) and
            # back (entry + pnl), which can lose the last ULP even when both sides mean
            # the same price.
            # The inverted size fold above is exact algebraically, so this reasoning
            # holds for a declared-size leg too.
            still_open = abs(exit_px - last_close) <= 1e-6 * abs(last_close) + 1e-9
        shares = int(math.floor(NOTIONAL_PER_LEG / entry_px)) if entry_px > 0 else 0
        out.append({
            "side": "long" if side > 0 else "short",
            "entry_time": idx[entry_bar].isoformat(),
            "entry_px": round(entry_px, 4),
            "shares": max(shares, 0),
            "exit_time": None if still_open else idx[min(exit_bar, n_bars - 1)].isoformat(),
            "exit_px": None if still_open else round(exit_px, 4),
            "still_open": still_open,
            "size": size,
            # additive (2026-09-23, KEEL overlay): the entry's own bar index into THIS
            # call's `arrays` -- needed to slice a feature row for the KEEL overlay (see
            # _keel_size_for_entry) at the exact bar the trade fired on. Nothing before
            # this reads it, so it changes no existing behaviour.
            "entry_bar": entry_bar,
        })
        if want_levels:
            out[-1]["levels"] = _trade_levels(lv, entry_bar, side, entry_px, idx, n_bars)
        if want_decisions:
            d = _trade_decision(dec, entry_bar, side, idx, n_bars, _tf)
            if d is None and decisions_raw is not None:
                # the list lined up but THIS record did not describe this trade (entry bar
                # or side mismatch, or malformed) -- logging only, the trade is unchanged
                log(f"[cloud-signal] {label}: decision record rejected for the "
                    f"{'long' if side > 0 else 'short'} entry at bar {entry_bar} "
                    f"({idx[entry_bar].isoformat()}) -- dec_* columns blank on its rows")
            if d is not None and still_open:
                d["exit"] = None          # the engine's data-end mark is not an exit decision
            out[-1]["decision"] = d
    return out


# ── KEEL v12 overlay -- see the block comment above keel_paths() near CROWN_LEGS ─────────
_KEEL_STATE_CACHE = {}   # state_path -> (mtime, state, summary-or-None)

# KEEL FALLBACK PUSH (deadman/deadman_keel_guard, 2026-09-26). How many trading sessions
# a KEEL state may lag "now" (by data_through/last_nq_session) before this module NOTES it
# (_keel_fallback_reason) -- DELIBERATELY TIGHTER than KEEL_MAX_STALE_SESSIONS above (which
# governs when the SIZING itself gives up and falls back to 1.0).
# WEBULL PUSH PLAN 10-07 (MANAGER #86, section 2): the phone used to hear "KEEL fell back to
# 1.0" from 2 stale sessions on, while sizing only falls back past KEEL_MAX_STALE_SESSIONS --
# a false title most of the time (box proof: NOISE_382 pushed 10-05 at 4 stale sessions).
# Now a STALE-ONLY reason within KEEL_MAX_STALE_SESSIONS is a fact for the log and
# state["keel_alerts"] only (the box monitor tools/webull_freshness.py owns "KEEL not
# rebuilt"); the phone hears only a REAL fallback (_keel_fallback_is_real).
KEEL_PUSH_STALE_SESSIONS = 1


def _load_keel_state(state_path, summary_path, log=print):
    """Best-effort load of a KEEL state + its JSON summary, cached by the state file's
    OWN mtime so a fresh nightly rebuild is picked up without restarting this process,
    and a repeat call within the same tick never re-reads a multi-MB joblib file twice.
    Returns (state, summary) -- summary may be None even when state loads fine (its
    file missing/unreadable is not fatal, only staleness reporting degrades). NEVER
    raises: every failure returns (None, None), which _keel_size_for_entry turns into
    the safe keel_size 1.0 fallback."""
    try:
        mtime = os.path.getmtime(state_path)
    except OSError:
        return None, None
    cached = _KEEL_STATE_CACHE.get(state_path)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    try:
        import joblib
        state = joblib.load(state_path)
    except Exception as e:
        log(f"[cloud-signal] KEEL state unreadable ({state_path}): {type(e).__name__}: {e}")
        return None, None
    summary = None
    try:
        if os.path.exists(summary_path):
            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)
    except Exception as e:
        log(f"[cloud-signal] KEEL summary unreadable ({summary_path}): {type(e).__name__}: {e}")
    _KEEL_STATE_CACHE[state_path] = (mtime, state, summary)
    return state, summary


def _keel_size_for_entry(keel_cfg, arrays, entry_bar, entry_time, log=print, scratch=None):
    """The KEEL multiplier for ONE new entry about to be emitted (design: "compute the
    KEEL size once" -- see _diff_leg, the only caller). Reads the trade's own feature
    row from `keel_features` on `arrays` (the QQQ arrays the leg already uses) at
    `entry_bar`, and scores it against the nightly-built NQ state -- see
    augur_engine.ml_keel.keel_score_from_state.

    ALWAYS returns a finite float > 0 as its first element -- 1.0 (unsized, i.e.
    "behave exactly like no overlay") on ANY failure: the state file missing or
    unreadable, feature columns that do not match what the state was built on, more
    than KEEL_MAX_STALE_SESSIONS trading sessions between the state's last trained NQ
    session and this entry's own session, or an exception anywhere in the scoring
    call. Every failure is logged with a short reason (the second return value) and
    NEVER raised -- KEEL is an OVERLAY, not a gate, so a broken overlay must never
    block or delay the trade it would have merely resized. The second return value is
    a short human-readable reason string on any fallback, or a diagnostics dict
    (z/trust/rho/t_fast) on a real score -- for logging only.

    A mode="fixed" block (see FOUR SHAPES above keel_paths) never reaches the state
    file: _keel_fixed_size_for_entry scores it, under the same contract. A mode="const"
    block is its one size (_keel_const_size), whatever the entry bar. An unknown mode
    is a configuration error -> 1.0 with its reason, like any other fallback. So is a
    learned block with no "state_path" (dict(version="v12") alone, or a misspelt "mode"
    KEY, both read as learned): _diff_leg and step()'s per-leg loop have no try of their
    own, so a KeyError here would stop every leg's tick, not just this entry's KEEL.

    `scratch` (a dict, optional -- _diff_leg passes one): on a learned leg whose feature
    columns match the state, receives "feats" (the keel_features (F, names) just computed
    on `arrays`) and "rule_cfg" (the state's rule cfg), so the KEEL ENTRY EXTRAS
    (_keel_entry_extras, logging only) never recompute them on the entry path. Writing it
    changes nothing this function returns.
    """
    if keel_cfg and keel_mode(keel_cfg) == KEEL_MODE_CONST:
        return _keel_const_size(keel_cfg)
    if not keel_cfg or entry_bar is None:
        return 1.0, None
    mode = keel_mode(keel_cfg)
    if mode == KEEL_MODE_FIXED:
        return _keel_fixed_size_for_entry(keel_cfg, arrays, entry_bar, log=log)
    if mode != KEEL_MODE_LEARNED:
        return 1.0, f"unknown keel mode {mode!r}"
    state_path = keel_cfg.get("state_path")
    if not state_path:
        return 1.0, "keel config has no state_path"
    state, summary = _load_keel_state(state_path, keel_cfg.get("summary_path", ""), log=log)
    if state is None:
        return 1.0, "keel state unavailable"
    try:
        # ITEM D (2026-09-25): staleness must be counted from the DATA, not the last
        # trade. "last_nq_session" (ml_keel.py's own field) is the date of the last NQ
        # NOISE TRADE the state was fitted on -- on a quiet run of NQ sessions with no
        # trade at all, that date stops advancing even though tools/keel_live_state.py
        # keeps rebuilding on fully current data every night, which would eventually
        # (after KEEL_MAX_STALE_SESSIONS quiet sessions) trip this guard and fall back
        # to size 1.0 for no real reason. "data_through" (the ET date of the last BAR
        # actually used -- see tools/keel_live_state.py's build()) tracks the data
        # itself, so prefer it; fall back to last_nq_session for a summary written
        # before this field existed.
        last_session = (summary or {}).get("data_through") or (summary or {}).get("last_nq_session")
        if last_session:
            entered = entry_time
            if isinstance(entered, str):
                entered = _dt.datetime.fromisoformat(entered)
            sessions = market_calendar.sessions_between(last_session, entered.date().isoformat())
            n_stale = max(0, len(sessions) - 1)
            if n_stale > KEEL_MAX_STALE_SESSIONS:
                return 1.0, (f"keel state stale: {n_stale} session(s) since {last_session}")
        from augur_engine import ml_keel as _keel
        F, names = _keel.keel_features(arrays)
        if list(names) != list(state.get("feature_names") or []):
            return 1.0, "keel feature columns do not match the state"
        if isinstance(scratch, dict):
            scratch["feats"] = (F, names)
            scratch["rule_cfg"] = state.get("cfg") or _keel.CFG.get(state.get("version"))
        row = int(min(max(int(entry_bar), 0), len(F) - 1))
        size, diag = _keel.keel_score_from_state(state, arrays, row, x_row=F[row:row + 1],
                                                 cross_series=True)
        if not math.isfinite(size) or size <= 0:
            return 1.0, f"keel scoring returned a non-finite/non-positive size ({size!r})"
        return float(size), diag
    except Exception as e:
        log(f"[cloud-signal] KEEL scoring failed: {type(e).__name__}: {e}")
        return 1.0, f"keel scoring error: {type(e).__name__}: {e}"


def _keel_const_size(keel_cfg):
    """(size, diag) for a mode="const" block (see FOUR SHAPES above keel_paths): its "size" when
    that is a finite number > 0 and <= KEEL_CONST_MAX_SIZE -> (size, {"mode": "const", "size"}),
    else (1.0, a reason string) -- the same contract as every other KEEL scorer. Never raises."""
    try:
        size = float((keel_cfg or {}).get("size"))
    except (TypeError, ValueError):
        return 1.0, f"keel const size invalid: {(keel_cfg or {}).get('size')!r}"
    if not math.isfinite(size) or size <= 0 or size > KEEL_CONST_MAX_SIZE:
        return 1.0, f"keel const size invalid: {size!r} (needs 0 < size <= {KEEL_CONST_MAX_SIZE})"
    return size, {"mode": KEEL_MODE_CONST, "size": size}


def _keel_fixed_size_for_entry(keel_cfg, arrays, entry_bar, log=print, feats=None):
    """keel_size for ONE new entry on a mode="fixed" leg: v12's fixed tilts, no model
    (augur_engine.ml_keel.fixed_tilt_sizes_v12) at `entry_bar` of `arrays` -- the arrays
    _diff_leg was handed. Same contract as _keel_size_for_entry: a finite float > 0, 1.0
    with a short reason string on ANY failure (logged, never raised), a small diagnostics
    dict on a real score.

    DECIDE-AT-CLOSE. For a probe entry `arrays` are the probe's (bar D plus two flat
    stand-ins) and `entry_bar` is the stand-in S1, which carries the real D+1 bar's own
    start time and session. Every tilt reads only what is known at that bar's open: the
    compression state of the last COMPLETE 60-minute group before it (the stand-ins sit in
    S1's own group or later, never in an earlier one), and the weekday and FOMC
    pre-statement hour of its start time. So the probe's size equals the full-history
    backtest's at the real entry bar (tests/test_noise_422_keel_fixed.py checks it).

    An entry_bar outside `arrays` (should never happen) is a fallback with its reason, not
    clamped onto the nearest bar and scored there silently.

    `feats`: keel_features(arrays)'s (F, names) when the caller already computed it on these
    SAME arrays (the KEEL entry extras pass the score's own) -- ignored unless it has one
    row per bar; the size is identical either way."""
    try:
        version = keel_cfg.get("version")
        if version not in KEEL_FIXED_VERSIONS:
            return 1.0, f"keel fixed tilts: unsupported version {version!r}"
        from augur_engine import ml_keel as _keel
        row, n_bars = int(entry_bar), len(arrays["close"])
        if not 0 <= row < n_bars:
            return 1.0, f"keel fixed tilts: entry_bar {row} out of range (0..{n_bars - 1})"
        kw = {}
        if feats is not None and len(feats[0]) == n_bars:
            kw["feats"] = feats
        size = float(_keel.fixed_tilt_sizes_v12(arrays, [row], **kw)[0])
        if not math.isfinite(size) or size <= 0:
            return 1.0, f"keel fixed tilts returned a non-finite/non-positive size ({size!r})"
        return size, {"mode": KEEL_MODE_FIXED, "version": version}
    except Exception as e:
        log(f"[cloud-signal] KEEL fixed tilts failed: {type(e).__name__}: {e}")
        return 1.0, f"keel fixed tilts error: {type(e).__name__}: {e}"


# ── KEEL ENTRY EXTRAS (2026-10-05, MANAGER #76 -- owner GL 2.6 decision pending) ──────────
# KEEL v12's 10-05 evening states read fast-trust (t_fast) -1.33 / -1.23, below the -0.5
# shade line for the first time, so from 10-06 the SHADE branch (size = clip(1 - 1.0 x z,
# 0.5, 1.5), against the model's own score) replaces the fixed tilts alone on the live
# NOISE leg. To SEE that happen, every ENTRY on a LEARNED KEEL leg also records which branch
# decided (keel_branch), what the fixed rule alone would size the same entry bar
# (keel_fixed_size) and the score's diag (keel_t_fast / keel_trust / keel_score) -- see
# SIGNAL_COLS. LOGGING ONLY, NOTHING LIVE CHANGES: the extras are computed AFTER keel_size,
# from the same arrays and entry bar, and nothing reads them to size or send an order. Any
# failure blanks the extra field(s) it touched, never the trade.
#
# KEEL SIZE DIFF ALERT: when keel_size and keel_fixed_size differ by more than
# KEEL_DIFF_TOL on a LIVE leg's entry (_push_allowed: live tick, the cloud box, not a shadow
# leg), the entry is written ONCE (date + leg + entry time) to
# <state_dir>/keel_size_diffs.jsonl (last KEEL_DIFFS_KEEP lines) -- tools/webull_freshness.py
# puts the last 20 in status.json and tools/webull_freshness_pc.py relays each one once to
# the MANAGER and PAPER-WB inboxes -- and ONE low-priority plain push goes out ("NOISE: KEEL
# size differs", via _engine_note: ntfy_push.plain + dedupe, then _engine_push).
# A shadow leg's difference is logged (cloud_signal.log, its signal row), never pushed.
# AT-MOST-ONCE (review 10-05): the note runs just AFTER the state and the rows are written, so
# a process death in that few-millisecond window loses that entry's diff record / push / inbox
# relay for good (the entry is never emitted again). The row itself is safe and carries
# keel_size + keel_fixed_size, so tools/keel_size_report.py still shows the difference.
KEEL_ENTRY_EXTRAS = True        # tests flip it off to prove the extras change no decision
KEEL_DIFF_TOL = 0.01
KEEL_DIFFS_FILE = "keel_size_diffs.jsonl"
KEEL_DIFFS_KEEP = 200


def _keel_rule_cfg(keel_cfg):
    """The KEEL rule's own cfg for a learned block: the state's "cfg" (what it was built
    with), else ml_keel.CFG[version]. None when neither can be read. Never raises."""
    try:
        from augur_engine import ml_keel as _keel
        state, _summary = _load_keel_state(keel_cfg.get("state_path") or "",
                                           keel_cfg.get("summary_path", ""), log=lambda *_: None)
        if isinstance(state, dict):
            return state.get("cfg") or _keel.CFG.get(state.get("version"))
        return _keel.CFG.get(keel_cfg.get("version"))
    except Exception:
        return None


def _finite_or_blank(v, nd=6):
    try:
        f = float(v)
        return round(f, nd) if math.isfinite(f) else ""
    except (TypeError, ValueError):
        return ""


def _keel_entry_extras(keel_cfg, arrays, entry_bar, diag, log=print, feats=None,
                       rule_cfg=None):
    """The KEEL ENTRY EXTRAS columns (KEEL_EXTRA_COLS) for ONE entry on a LEARNED KEEL leg
    -- see the block above. `diag` is what _keel_size_for_entry returned beside keel_size
    for this same entry (a dict on a real score, a reason string on its 1.0 fallback). The
    fixed-tilt size reuses _keel_fixed_size_for_entry on the SAME `arrays` and `entry_bar`
    (for a decide-at-close probe: the probe arrays and its stand-in S1, exactly what the
    NOISE_422_FIXED shadow leg scores). All blank for any other leg, when the switch is off,
    and per field on a failure. Never raises.

    COST ON THE ENTRY PATH (review 10-05): `feats` / `rule_cfg` are what
    _keel_size_for_entry already computed for this entry (its `scratch`), so the extras add
    no second keel_features pass and no second state load; without them (a fallback score)
    they are recomputed as before."""
    out = {c: "" for c in KEEL_EXTRA_COLS}
    if not KEEL_ENTRY_EXTRAS or not keel_cfg or entry_bar is None \
            or keel_mode(keel_cfg) != KEEL_MODE_LEARNED:
        return out
    try:
        from augur_engine import ml_keel as _keel
        # a fallback score (diag not a dict) is "fallback-1.0" without reading cfg -- skip
        # the state load on the entry path in exactly that degraded case
        if not isinstance(diag, dict):
            out["keel_branch"] = _keel.keel_branch(diag, None)
        else:
            out["keel_branch"] = _keel.keel_branch(
                diag, rule_cfg if rule_cfg is not None else _keel_rule_cfg(keel_cfg))
        if isinstance(diag, dict):
            out["keel_t_fast"] = _finite_or_blank(diag.get("t_fast"))
            out["keel_trust"] = _finite_or_blank(diag.get("trust"))
            out["keel_score"] = _finite_or_blank(diag.get("z"))
    except Exception as e:
        log(f"[cloud-signal] KEEL entry extras (branch/diag) failed, left blank: "
            f"{type(e).__name__}: {e}")
        for c in ("keel_branch", "keel_t_fast", "keel_trust", "keel_score"):
            out[c] = ""
    try:
        fixed, fdiag = _keel_fixed_size_for_entry(
            {"version": keel_cfg.get("version"), "mode": KEEL_MODE_FIXED}, arrays, entry_bar,
            log=log, feats=feats)
        # a fallback (reason string) is NOT the fixed rule's size -- blank, never a fake 1.0
        out["keel_fixed_size"] = float(fixed) if isinstance(fdiag, dict) else ""
    except Exception as e:
        log(f"[cloud-signal] KEEL entry extras (fixed size) failed, left blank: "
            f"{type(e).__name__}: {e}")
        out["keel_fixed_size"] = ""
    return out


def _keel_diffs_path(paths):
    return os.path.join(paths["state_dir"], KEEL_DIFFS_FILE)


def _keel_diff_key(rec):
    return (str(rec.get("date") or ""), str(rec.get("leg") or ""), str(rec.get("entry_time") or ""))


def read_keel_diffs(path, last=None):
    """The KEEL size-diff records in `path` (keel_size_diffs.jsonl), oldest first; the last
    `last` only when given. A missing file is []; a torn/bad line is skipped. Never raises."""
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except OSError:
        return []
    return out[-int(last):] if last else out


def _record_keel_diff(paths, rec, log=print):
    """Append `rec` to keel_size_diffs.jsonl unless the same date + leg + entry time is
    already there. Returns True (new), False (already recorded) or None (could not write).
    Keeps the last KEEL_DIFFS_KEEP lines (an atomic rewrite when it grows past that)."""
    path = _keel_diffs_path(paths)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        have = read_keel_diffs(path)
        if any(_keel_diff_key(r) == _keel_diff_key(rec) for r in have):
            return False
        line = json.dumps(rec, sort_keys=True, default=str)
        if len(have) + 1 > KEEL_DIFFS_KEEP:
            keep = [json.dumps(r, sort_keys=True, default=str)
                    for r in have[-(KEEL_DIFFS_KEEP - 1):]] + [line]
            tmp = f"{path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(keep) + "\n")
            os.replace(tmp, path)
        else:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return True
    except Exception as e:
        log(f"[cloud-signal] KEEL size diff not recorded ({type(e).__name__}: {e})")
        return None


def _fmt_num(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "?"


def _keel_diff_problem(clock, side, ks, fs):
    """The KEEL-size-differs problem line with ONE number: 'KEEL sized the long entry (10:35) 38%
    smaller than the fixed rule would.' (the time is a clock, not a count; hhmm() may make it
    'yesterday 10:35', hence the brackets)."""
    entry = " ".join(x for x in ("the", str(side or "").strip(), "entry") if x)
    entry += f" ({clock})" if clock else ""
    try:
        k, f = float(ks), float(fs)
        pct = round(abs(k / f - 1.0) * 100) if f > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        pct = None
    if not pct:
        return f"KEEL sized {entry} differently from the fixed rule."
    return f"KEEL sized {entry} {pct}% {'larger' if k > f else 'smaller'} than the fixed rule would."


def keel_entry_log_line(e):
    """The one cloud_signal.log line per learned-KEEL ENTRY -- key=value, so
    tools/keel_size_report.py can read it back (KEEL_LOG_RE there)."""
    return ("[cloud-signal] KEEL ENTRY "
            f"leg={e.get('leg')} time={e.get('ref_time')} side={e.get('side')} "
            f"keel_size={e.get('keel_size')} fixed_size={e.get('keel_fixed_size')} "
            f"branch={e.get('keel_branch') or '-'} t_fast={e.get('keel_t_fast')} "
            f"trust={e.get('keel_trust')} score={e.get('keel_score')} "
            f"size={e.get('size')} trade_id={e.get('trade_id')}")


def _engine_push_background(msg, title, priority="high", paths=None, log=print):
    """_engine_push on a daemon thread -- for a caller on the live decision path (the stream
    commit, the engine thread's FEED HEALTH pushes) that must not wait out a push's network
    timeout. Returns "background" (or False when the thread could not start). Never raises."""
    try:
        th = threading.Thread(target=lambda: _engine_push(msg, title, priority=priority,
                                                          paths=paths, log=log),
                              name="engine-push", daemon=True)
        th.start()
        return "background"
    except Exception as e:
        log(f"[cloud-signal] background push could not start ({type(e).__name__}: {e}): {title}")
        return False


def _note_keel_entries(events, legs, paths, fetch, log=print, push=None):
    """After a batch of signal rows is APPENDED (step(), or a stream commit): one log line per
    learned-KEEL ENTRY (keel_entry_log_line) and the KEEL SIZE DIFF ALERT (see KEEL ENTRY
    EXTRAS above) for a live leg whose keel_size and keel_fixed_size differ by more than
    KEEL_DIFF_TOL -- recorded once per entry, one low-priority plain push on a NEW record (or
    when the record could not be written -- the entry itself is emitted only once). Shadow
    legs: the log line only. Runs after the rows are written, so nothing here can delay or
    change an order. Never raises.

    `push`: the sender (default _engine_push, synchronous); the stream commit passes
    _engine_push_background. A "fallback-1.0" difference (KEEL could not score, so it sized
    1.0) is RECORDED for the inbox relay but not pushed: the KEEL fallback alert already
    paged that cause at high priority."""
    for e in events or []:
        try:
            if e.get("event") != "ENTRY" or e.get("keel_size") in ("", None) \
                    or "keel_branch" not in e:
                continue
            cfg = (legs or {}).get(e.get("leg")) or {}
            ks, fs = e.get("keel_size"), e.get("keel_fixed_size")
            try:
                differs = (fs not in ("", None)
                           and abs(float(ks) - float(fs)) > KEEL_DIFF_TOL)
            except (TypeError, ValueError):
                differs = False
            live = _push_allowed(cfg, fetch)
            log(keel_entry_log_line(e) + (" DIFFERS" if differs else "")
                + (" (shadow leg: logged only)" if differs and cfg.get("shadow") else ""))
            if not differs or not live:
                continue
            when = str(e.get("ref_time") or "")
            rec = {"date": when[:10], "leg": e.get("leg"), "entry_time": when,
                   "side": e.get("side"), "keel_size": ks, "keel_fixed_size": fs,
                   "branch": e.get("keel_branch") or "", "t_fast": e.get("keel_t_fast"),
                   "trust": e.get("keel_trust"), "score": e.get("keel_score"),
                   "size": e.get("size"), "trade_id": e.get("trade_id") or "",
                   "recorded_at": _dt.datetime.now(tz=_zi(TZ)).isoformat()}
            new = _record_keel_diff(paths, rec, log=log)
            if new is False:
                continue
            if rec["branch"] == "fallback-1.0":
                log(f"[cloud-signal] KEEL size diff on {rec['leg']} {when} is the 1.0 fallback "
                    f"-- recorded, no second push (the KEEL fallback alert covers it)")
                continue
            from api import ntfy_push
            # PLAIN PHONE FORMAT (api/ntfy_push.plain/dedupe): owner's clock, no codes, ONE
            # number on the problem line (the gap in %); both sizes, the branch / t_fast /
            # score stay in the record, the log line and the inbox relay
            note = ntfy_push.plain(
                str(rec["leg"] or "NOISE").split("_")[0], "KEEL size differs",
                "not affected (the order used KEEL's size, as always)",
                _keel_diff_problem(ntfy_push.hhmm(when), rec["side"], ks, fs),
                "nothing", priority="low")
            _engine_note("keel_diff", f"{rec['leg']} {when}", note, paths, log=log, push=push)
        except Exception as ex:
            log(f"[cloud-signal] KEEL entry note failed: {type(ex).__name__}: {ex}")


def _keel_fallback_reason(keel_cfg, now, arrays=None, log=print):
    """Would KEEL fall back to keel_size 1.0 right now, and if so why -- a STANDALONE
    freshness read, independent of any actual trade entry. _keel_size_for_entry above
    only ever runs at the moment a NEW entry is about to be emitted, which on a quiet
    leg can be hours or days away; a broken/stale KEEL state should not have to wait
    for a trade to be noticed (deadman/deadman_keel_guard, 2026-09-26).

    Checks: the state file itself (missing/unreadable -- see _load_keel_state),
    staleness by data_through/last_nq_session against KEEL_PUSH_STALE_SESSIONS (tighter
    than KEEL_MAX_STALE_SESSIONS -- see that constant's own comment), and -- only when
    `arrays` is given -- the feature-column match _keel_size_for_entry also checks. A
    feature-column mismatch is a REAL fallback to 1.0, so it wins over a stale reason
    (10-08 review: a model 2-5 sessions old with a mismatch used to read as stale-only,
    so this step-time check stayed silent on a real fallback). `arrays` is optional because this is called
    every tick a leg's bars actually advance (see step()), and the two array-free
    checks alone already cover the failure modes that matter most: a dead nightly
    build, or a state file that stops updating.

    Returns a short human-readable reason string on any fallback condition, or None
    when KEEL looks healthy. NEVER raises -- any exception anywhere in this check
    itself is caught and reported back as its own reason, exactly like a real scoring
    exception would be.

    A mode="fixed" block has no state and nothing to go stale: healthy (None) unless its
    version has no fixed tilts. A mode="const" block is healthy unless its size is invalid.
    An unknown mode is always reported."""
    try:
        mode = keel_mode(keel_cfg)
        if mode == KEEL_MODE_CONST:
            _size, diag = _keel_const_size(keel_cfg)
            return diag if isinstance(diag, str) else None
        if mode == KEEL_MODE_FIXED:
            version = keel_cfg.get("version")
            return (None if version in KEEL_FIXED_VERSIONS
                    else f"keel fixed tilts: unsupported version {version!r}")
        if mode != KEEL_MODE_LEARNED:
            return f"unknown keel mode {mode!r}"
        state_path = keel_cfg.get("state_path")
        if not state_path:
            return "keel config has no state_path"
        state, summary = _load_keel_state(state_path, keel_cfg.get("summary_path", ""), log=log)
        if state is None:
            return "keel state unavailable"
        stale = None
        last_session = (summary or {}).get("data_through") or (summary or {}).get("last_nq_session")
        if last_session:
            sessions = market_calendar.sessions_between(last_session, now.date().isoformat())
            n_stale = max(0, len(sessions) - 1)
            if n_stale > KEEL_PUSH_STALE_SESSIONS:
                stale = f"keel state stale: {n_stale} session(s) since {last_session}"
        if arrays is not None:
            from augur_engine import ml_keel as _keel
            F, names = _keel.keel_features(arrays)
            if list(names) != list(state.get("feature_names") or []):
                return "keel feature columns do not match the state"
        return stale
    except Exception as e:
        return f"keel freshness check error: {type(e).__name__}: {e}"


def _is_cloud_host():
    """True only on the box (EDGELOG_HOST_ROLE=cloud, set by deploy/cloud/edgelog.env via
    install.sh / edgelog.env.example) -- the SAME check api/runner.py's
    _cloud_runner_refusal and api/qqq_exec.py's host-role label already use. The PC
    runner also imports and calls this module's step() (api/runner.py's
    cloud_signal_thread), and C:\\EdgeLog\\cloud_signal\\keel never exists there (KEEL
    state is only ever built on the box), so without this gate the PC would page the
    owner's phone with a false "keel state unavailable" every trading day -- see
    _maybe_push_keel_fallback's caller in step()."""
    return str(os.environ.get("EDGELOG_HOST_ROLE") or "").strip().lower() == "cloud"


def _push_allowed(cfg, fetch):
    """May a KEEL fallback push fire for this leg on this tick? Only on a LIVE (fetching)
    tick, on the cloud box (_is_cloud_host), for a leg that is NOT a shadow leg
    (cfg["shadow"], SHADOW_LEGS -- OWNER DECISION 2026-09-28: shadow legs never page the
    owner). The ONE gate both push sites use (step()'s standalone freshness push and
    _diff_leg's scoring-time push); for every CROWN_LEGS leg (no "shadow" key) it is exactly
    the `fetch and _is_cloud_host()` test those two sites carried before it existed.
    run_shadow_step also steps with fetch=False, so a shadow leg is silenced twice over --
    a NOISE_422_KEEL with no state yet on the box scores 1.0 and says nothing."""
    return bool(fetch) and not (cfg or {}).get("shadow") and _is_cloud_host()


def _this_host_id():
    """This host's label for a KEEL fallback push title, so a real box alert can never
    be confused with anything else -- same EDGELOG_HOST_ID-override-else-hostname
    pattern as api/qqq_exec.py's _lease_host_id."""
    override = os.environ.get("EDGELOG_HOST_ID")
    if override and override.strip():
        return override.strip()
    try:
        import socket
        return socket.gethostname() or "unknown-host"
    except Exception:
        return "unknown-host"


def _keel_ntfy_push(msg, title, log=print, priority="high"):
    """ONE KEEL fallback push through api/ntfy_push -- WEBULL PUSH PLAN 10-07, section 2: this
    used to be a raw POST to a hard-coded https://ntfy.sh/<topic> (no NTFY_TOKEN, no
    NTFY_SERVER, no stripped topic, no result), which would have gone silent the day a
    private topic is turned on. Now the token-aware helper, and a high push goes through
    this engine's persisted outbox (_engine_outbox) like its other alerts.
    Returns None when no topic is set (nothing to send to -- counts as done), True / "queued"
    when it went out or the outbox keeps it, False when the send failed (the caller tries
    again on a later tick). Never raises."""
    try:
        from api import ntfy_push
        if not (os.environ.get("NTFY_TOPIC") or "").strip():
            log(f"[cloud-signal] NTFY_TOPIC unset, push skipped: {title}: {msg}")
            return None
        if ntfy_push.is_durable(priority):
            r = _engine_outbox(DEFAULT_PATHS).send(msg, title, priority, log=log)
            if r is not False:
                return r
            log(f"[cloud-signal] ntfy outbox could not take the push -- one plain try: {title}")
        ok, detail = ntfy_push.push_result(msg, title=title, priority=priority, timeout=4)
        if ok is False:
            log(f"[cloud-signal] ntfy push failed ({detail}): {title}")
        return ok
    except Exception as e:
        log(f"[cloud-signal] ntfy push failed: {type(e).__name__}: {e}")
        return False


_KEEL_STALE_PREFIX = "keel state stale: "


def _keel_stale_sessions(reason):
    """The session count in a "keel state stale: N session(s) since D" reason, else None."""
    s = str(reason or "")
    if not s.startswith(_KEEL_STALE_PREFIX):
        return None
    try:
        return int(s[len(_KEEL_STALE_PREFIX):].split()[0])
    except (ValueError, IndexError):
        return None


def _keel_fallback_is_real(reason):
    """True when `reason` means sizing REALLY falls back to 1.0 (WEBULL PUSH PLAN 10-07): the
    state missing or unreadable, a feature mismatch, a scoring or check error, an unknown
    mode -- or a stale state past KEEL_MAX_STALE_SESSIONS, the exact bound
    _keel_size_for_entry uses. A stale state within it still sizes on the model: False."""
    if not reason:
        return False
    n = _keel_stale_sessions(reason)
    return n is None or n > KEEL_MAX_STALE_SESSIONS


def _keel_leg_word(leg_key):
    head = str(leg_key or "NOISE").split("_")[0]
    return {"ENGUQ": "ENGU-Q"}.get(head, head)


def _keel_fallback_note(leg_key, reason):
    """The plain phone note for a REAL KEEL fallback (api/ntfy_push.plain): high -- the
    leg's trades are sized at base size without their model."""
    from api import ntfy_push
    w = _keel_leg_word(leg_key)
    n = _keel_stale_sessions(reason)
    r = str(reason or "")
    if n is not None:
        problem = f"The KEEL sizing model is {n} trading sessions old, too old to use"
    elif "feature columns" in r:
        problem = "The KEEL sizing model does not match the price data it is given"
    elif "fixed tilts error" in r:
        problem = f"The KEEL fixed sizing failed to size {ntfy_push.with_article(w)} trade"
    elif "no state_path" in r or "unknown keel mode" in r or "unsupported version" in r:
        problem = "The KEEL sizing setting on the cloud box is not valid"
    elif "scoring" in r:
        problem = f"The KEEL sizing model failed to size {ntfy_push.with_article(w)} trade"
    elif "check error" in r:
        problem = "The KEEL sizing model check failed on the cloud box"
    else:
        problem = "The KEEL sizing model could not be read on the cloud box"
    return ntfy_push.plain("QQQ book", "CHECK NOW",
                           f"{w} trades at base size without its sizing model", problem,
                           "ask Claude (PAPER-WB chat)", priority="high")


def _monitor_owns_keel_stale(leg_key, paths=None):
    """True when the box monitor (tools/webull_freshness.py) already pushed this leg's
    "KEEL too old" episode (an open, not-quiet keel_fallback:<leg>... alert in
    <home>/freshness/state.json): ONE ALERTER PER PROBLEM -- a stale-only fallback is then
    recorded here, not pushed a second time. Reads one small local file; never raises."""
    try:
        home = (paths or DEFAULT_PATHS).get("home") or edgelog_home()
        with open(os.path.join(home, "freshness", "state.json"), encoding="utf-8") as f:
            alerts = (json.load(f) or {}).get("alerts") or {}
        for key, rec in alerts.items():
            name = str(key)[len("keel_fallback:"):] if str(key).startswith("keel_fallback:") else None
            if (name and (name == leg_key or name.startswith(f"{leg_key}_"))
                    and isinstance(rec, dict) and rec.get("open") and not rec.get("quiet")):
                return True
    except Exception:
        pass
    return False


def _keel_fallback_push_once(leg_key, reason, today, stamps, log=print):
    """Push one REAL KEEL fallback for `leg_key` at most once a day. `stamps` are the dicts
    that remember the day it went out (state["keel_alerts"][leg] and the leg's own
    leg_state["keel_alert"]) -- either one stamped today holds it, so the step-time check
    and the scoring-time fallback never push the same day's problem twice. A send that
    FAILED (False) stamps nothing, so a later tick tries again; None (no topic set) counts
    as done, so a box with no topic never loops. Returns True when it pushed."""
    if any(s.get("last_pushed_date") == today for s in stamps):
        return False
    n = _keel_stale_sessions(reason)
    if n is not None and _monitor_owns_keel_stale(leg_key):
        log(f"[cloud-signal] KEEL fallback on {leg_key} ({reason}) -- the box monitor already "
            f"pushed its old-model episode; recorded, no second push")
        for s in stamps:
            s["last_pushed_date"] = today
            s["last_reason"] = reason
        return False
    note = _keel_fallback_note(leg_key, reason)
    res = _keel_ntfy_push(note["message"], note["title"], log=log)
    if res is False:
        log(f"[cloud-signal] KEEL fallback push for {leg_key} did not go out -- trying again "
            f"on a later tick")
        return False
    for s in stamps:
        s["last_pushed_date"] = today
        s["last_reason"] = reason
    return True


def _maybe_push_keel_fallback(leg_key, keel_cfg, now, state, arrays=None, log=print):
    """Tells the owner, ONCE PER (ET calendar) DAY, when `leg_key`'s KEEL overlay REALLY
    falls back to keel_size 1.0 -- WEBULL PUSH PLAN 10-07: the state missing/unreadable, a
    feature-column mismatch, an exception in the check itself, or a state stale PAST
    KEEL_MAX_STALE_SESSIONS (_keel_fallback_is_real). A stale state within that bound
    (KEEL_PUSH_STALE_SESSIONS < n <= KEEL_MAX_STALE_SESSIONS) still sizes on the model: it
    is logged once a day and kept in state["keel_alerts"][leg_key] (last_reason,
    stale_sessions, last_stale_date) -- no push; the box monitor owns "KEEL not rebuilt".
    Dedupe lives in state["keel_alerts"][leg_key]["last_pushed_date"] (and the leg's own
    leg_state["keel_alert"], shared with the scoring-time push in _diff_leg) -- state.json,
    the SAME ledger step() already loads/persists every tick. A day with NO reason leaves
    the stamps untouched -- the NEXT bad day pages again. Never raises -- a broken alerter
    must never take down step()."""
    try:
        reason = _keel_fallback_reason(keel_cfg, now, arrays=arrays, log=log)
        if not reason:
            return
        alerts = state.setdefault("keel_alerts", {})
        rec = alerts.setdefault(leg_key, {})
        today = now.date().isoformat()
        rec["last_reason"] = reason
        if not _keel_fallback_is_real(reason):
            rec["stale_sessions"] = _keel_stale_sessions(reason)
            if rec.get("last_stale_date") != today:
                rec["last_stale_date"] = today
                log(f"[cloud-signal] KEEL {leg_key}: {reason} -- still sizing on the model "
                    f"(falls back only past {KEEL_MAX_STALE_SESSIONS}); no push, the box "
                    f"monitor owns it")
            return
        leg_alert = ((state.get("legs") or {}).get(leg_key) or {}).get("keel_alert")
        stamps = [rec] + ([leg_alert] if isinstance(leg_alert, dict) else [])
        _keel_fallback_push_once(leg_key, reason, today, stamps, log=log)
    except Exception as e:
        log(f"[cloud-signal] KEEL fallback push failed: {type(e).__name__}: {e}")


def _entry_key(leg, trade):
    """The key a leg's emitted-trade memory (leg_state['trades']) is stored under: the
    trade's stable id from api/trade_id.py -- leg + entry bar time + side, and NOT the entry
    price (2026-09-14). The old key carried the price, so the same trade re-priced by a
    cent (Webull vs yfinance bars for one minute can disagree, and the cache keeps
    whichever source wrote last) looked brand new: within a few bars it re-emitted as a
    second ENTRY, and either way the original key dropped out of the trade list, so its
    EXIT was never emitted. The price-bearing form is only a fallback for a trade whose id
    cannot be formed (never the case for a well-formed engine trade); such a trade's rows
    carry an empty trade_id and api/qqq_exec.py refuses to act on them.

    SLOT (2026-10-09): a trade that names a "slot" (only the DIP #424 shadow legs' -- seven
    mechanisms can fill at one bar) gets the per-slot id "<leg>-<time>-L-<SLOT>"; every other
    trade has no slot and keeps exactly the id it always had."""
    return (_trade_id.make(leg, trade.get("entry_time"), trade.get("side"), slot=trade.get("slot"))
            or _legacy_entry_key(leg, trade))


def _legacy_entry_key(leg, trade):
    return f"{leg}|{trade['entry_time']}|{trade['side']}|{trade['entry_px']:.4f}"


# leg_state["key_format"] once _rekey_recorded_trades has run for that leg.
TRADE_KEY_FORMAT = "trade_id_v1"

# SHADOW SEED CARRY (2026-10-07, MANAGER #87 -- see _diff_leg's COLD START). A SHADOW leg
# (cfg["shadow"]) that is holding a trade when it cold-starts carries that trade as an open
# would-be trade instead of absorbing it: one ENTRY row at the trade's own entry time and
# price whose reason starts with SEEDED_REASON_TAG, and its memory record keeps
# exit_emitted False (plus "seeded_open": True), so the strategy's own EXIT -- and the
# trade's P&L -- land in the shadow ledger when it closes. The live (order-placing) legs
# never take this path: an executor that never entered still cannot exit.
# leg_state["seed_open_format"] = SEED_OPEN_FORMAT once a shadow leg's seed is in this
# shape -- set at the cold start itself, or by _carry_seeded_open's one-time upgrade of a
# leg seeded before this existed (ENGUQ_335 on the box, seeded 2026-09-29 holding the
# 2026-09-28 12:32 long).
SEED_OPEN_FORMAT = 1
SEEDED_REASON_TAG = "seeded=1"

# LIVE SINCE (2026-10-09, OWNER DECISION via MANAGER #102 -- ENGU-Q back on the book). A leg's
# cfg may carry "live_since": "YYYY-MM-DD", the day it (re)joined the order-placing book. When
# the leg's stored state (state.json legs[<key>]) does not carry that same value, the state is
# from an EARLIER stint: it is discarded, once, and the leg COLD STARTS like a leg never seen
# before (_diff_leg's COLD START: one SEED row, every trade in the window absorbed -- including
# one still open, so no catch-up ENTRY for a trade the strategy is already in, and no EXIT for a
# position the book never took). The state is stamped leg_state["live_since"] at the discard, so
# it never repeats; the SEED row's reason names the live_since. A leg whose cfg has no
# "live_since" behaves exactly as before.
# WHY (verified on the box 2026-10-09): ENGUQ_335's live state.json still held its
# pre-2026-09-28 records -- the 09-28 12:32 long (ENGUQ_335-20260928T163200Z-L) with
# exit_emitted False, which the strategy closed 2026-10-08 13:01 @ 746.8612, and two phantom
# ghosts (09-17, 09-23) with exit_emitted False -- so re-adding the leg as-is would have emitted
# an EXIT for that trade on the first tick, for a position the book closed at 15:59 on 09-28.
LIVE_SINCE_KEY = "live_since"


def _apply_live_since(leg_key, cfg, leg_state, now=None, log=print):
    """LIVE SINCE (see the block above): when `cfg` carries "live_since" and `leg_state` does
    not carry the same value, empty `leg_state` IN PLACE (every key -- trades, seeded,
    counters, last_bar_epoch) and stamp it with that live_since plus a small record of what
    was discarded, timed by the caller's `now` (so a replay's state stays deterministic); the
    caller's next _diff_leg then cold-starts the leg. Returns True when it discarded. Never
    raises; a cfg with no live_since, or a state already stamped with it, changes nothing."""
    try:
        want = (cfg or {}).get(LIVE_SINCE_KEY)
        if not want or leg_state.get(LIVE_SINCE_KEY) == want:
            return False
        old_trades = leg_state.get("trades") or {}
        owed = sorted(k for k, rec in old_trades.items()
                      if isinstance(rec, dict) and not rec.get("exit_emitted"))
        had = bool(old_trades) or bool(leg_state.get("seeded"))
        prev = leg_state.get(LIVE_SINCE_KEY)
        leg_state.clear()
        leg_state["trades"] = {}
        leg_state[LIVE_SINCE_KEY] = want
        leg_state["live_since_reset"] = {
            "at": (now or _dt.datetime.now(tz=_zi(TZ))).isoformat(),
            "previous_live_since": prev,
            "discarded_trades": len(old_trades),
            # ids only, capped -- what WOULD have emitted an EXIT had the state been kept
            "discarded_exit_owed": owed[:20],
        }
        if had:
            log(f"[cloud-signal] {leg_key}: live since {want} -- its earlier state "
                f"({len(old_trades)} trade record(s), {len(owed)} with an exit still owed"
                + (f": {', '.join(owed[:5])}" if owed else "")
                + ") discarded; cold start next (SEED only, nothing entered or exited)")
        else:
            log(f"[cloud-signal] {leg_key}: live since {want} -- no earlier state; cold start "
                f"next (SEED only)")
        return True
    except Exception as e:
        log(f"[cloud-signal] {leg_key}: live_since check failed ({type(e).__name__}: {e}) -- "
            f"state left as it was")
        return False


def _entry_from_previous_session(t, now):
    """True when trade `t`'s entry is dated the session right before `now`'s ET date (the
    last session day strictly before it) -- a "stale" entry _diff_leg logs as not taken,
    unlike an older one (the rolling window's left edge re-minting a trade). Never raises."""
    try:
        et = now.astimezone(_zi(TZ)) if now.tzinfo is not None else now.replace(tzinfo=_zi(TZ))
        d = et.date() - _dt.timedelta(days=1)
        for _ in range(15):
            if market_calendar.is_session(d):
                return str(t.get("entry_time"))[:10] == d.isoformat()
            d -= _dt.timedelta(days=1)
        return False
    except Exception:
        return False


def _not_taken_after_close_line(leg_key, t, now):
    """The ONE plain log line for a live leg's NEW entry first seen once its session has
    closed (_diff_leg's "after_close" skip, or a "stale" entry from the previous session --
    see _entry_from_previous_session): which strategy, which side, the signal's own bar time,
    and why nothing was sent. Never raises."""
    when = None
    try:
        when = _dt.datetime.fromisoformat(str(t.get("entry_time")))
        when = when.astimezone(_zi(TZ)) if when.tzinfo else when.replace(tzinfo=_zi(TZ))
        at = f"{when:%H:%M} ET on {when:%Y-%m-%d}"
    except Exception:
        when = None
        at = str(t.get("entry_time"))
    try:
        seen = now.astimezone(_zi(TZ)) if now.tzinfo else now.replace(tzinfo=_zi(TZ))
        if when is not None and when.date() != seen.date():
            # first seen in a later session: name that day, and the signal's own session close
            close = _session_close_dt(when)
            close_txt = (f"that session's {close:%H:%M} close" if close is not None
                         else "that session's close")
            seen_txt = f"{seen:%H:%M:%S} ET on {seen:%Y-%m-%d}"
        else:
            close = _session_close_dt(now)
            close_txt = f"the {close:%H:%M} close" if close is not None else "the session close"
            seen_txt = f"{seen:%H:%M:%S} ET"
    except Exception:
        close_txt, seen_txt = "the session close", str(now)
    return (f"[cloud-signal] {_keel_leg_word(leg_key)} {t.get('side')} signal at {at} "
            f"({leg_key}) not taken: the market is closed -- the strategy's entry was first "
            f"seen at {seen_txt}, after {close_txt}. No order.")


def _merge_rank(rec):
    """Which of two memory records for ONE trade id to keep when re-keying: a record whose
    ENTRY really was emitted beats a skipped/seeded twin (its EXIT may still be owed), and
    among emitted ones a record whose EXIT already went out beats one still waiting (the
    trade is one trade -- a second EXIT would only find no lot)."""
    emitted_entry = not rec.get("skipped") and (not rec.get("seeded") or bool(rec.get("seeded_open")))
    return (emitted_entry, bool(rec.get("exit_emitted")))


def _rekey_recorded_trades(leg_key, leg_state):
    """One-time, idempotent upgrade of a leg's emitted-trade memory from the pre-2026-09-14
    price-bearing keys to trade ids (see _entry_key). Without it, the first step() after
    the upgrade would find none of its own records: every trade still in the window would
    look new, a trade open across the upgrade would be recorded as LATE with its exit
    marked done, and its real EXIT would never be emitted. Price twins of one trade merge
    via _merge_rank. Returns how many records merged away."""
    if leg_state.get("key_format") == TRADE_KEY_FORMAT:
        return 0
    recorded = leg_state.get("trades") or {}
    out = {}
    for key, rec in recorded.items():
        new_key = _trade_id.make(leg_key, (rec or {}).get("entry_time"), (rec or {}).get("side"),
                                 slot=(rec or {}).get("slot")) or key
        cur = out.get(new_key)
        out[new_key] = rec if cur is None else max((cur, rec), key=_merge_rank)
    leg_state["trades"] = out
    leg_state["key_format"] = TRADE_KEY_FORMAT
    return len(recorded) - len(out)


# ── State I/O ───────────────────────────────────────────────────────────────────────────
def _load_state(paths):
    if not os.path.exists(paths["state_path"]):
        return {"legs": {}}
    with open(paths["state_path"], encoding="utf-8") as f:
        return json.load(f)


def _write_state(state, paths):
    """state.json is the idempotency ledger (which trades each leg has already emitted),
    read back by the very next step() call -- unlike the bar cache, losing this write
    silently would let the next tick re-diff against stale memory and re-emit ENTRY/EXIT
    rows _append_signals already wrote for THIS call. So the rename retries the same
    transient-lock budget as every other writer here (qp._replace_with_retry -- a reader
    such as a manual `_load_state` call or a debugging read can have this file open for
    the same few milliseconds the OHLC cache readers do), but on final failure it RAISES
    instead of continuing: the caller (step()) must not reach _append_signals having
    silently failed to persist that those events were already recorded."""
    os.makedirs(paths["state_dir"], exist_ok=True)
    tmp = paths["state_path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    if not qp._replace_with_retry(tmp, paths["state_path"], log=print,
                                  what="[cloud-signal] state.json"):
        raise OSError(f"cloud_signal: could not replace {paths['state_path']} after retries")


SIGNAL_COLS = ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares", "reason",
              # appended, never inserted -- api/qqq_exec.py's engine mode and the web tab's
              # status panel read this to attribute a trade's price to WEBULL or YAHOO.
              "bar_source",
              # appended, never inserted (2026-09-14) -- the trade's stable id
              # (api/trade_id.py: leg + entry bar time + side), IDENTICAL on its ENTRY and
              # its EXIT row. An EXIT's ref_time is the exit bar, so without this column an
              # EXIT row cannot say which trade it closes. "" on SEED rows.
              "trade_id",
              # appended, never inserted (2026-09-23) -- the per-trade size multiplier.
              # For a leg with NO "keel" block in CROWN_LEGS this is the plugin's own
              # declared size (run_leg_trades: 1.0 for a leg that does not size at all)
              # -- UNCHANGED by the KEEL overlay below. For a leg WITH a "keel" block
              # (NOISE_382 today) this is the PRODUCT plugin_size * keel_size (see
              # _diff_leg / _keel_size_for_entry) -- the executor's existing
              # size-to-shares multiply (api/qqq_exec.py's _sized_shares) needs no
              # change to pick up KEEL sizing, because it already multiplies by
              # whatever is in this column. "" on SEED rows and on any row written
              # before this column existed -- a blank here means "1.0, unsized", never
              # "unknown".
              "size",
              # appended, never inserted (2026-09-23, KEEL overlay) -- the KEEL
              # multiplier ALONE (this leg's "size" column above is plugin_size x this
              # value), for the trade drawer's breakdown display and for telling apart
              # "no keel overlay on this leg" (blank) from "keel ran and stood down at
              # 1.0" or "keel failed safe to 1.0" (a real 1.0, logged -- see
              # _keel_size_for_entry) -- both real numbers, never blank. Blank on SEED
              # rows, on every non-KEEL leg's rows, and on any row written before this
              # column existed.
              "keel_size",
              # appended, never inserted (2026-09-29, resting ORB stops) -- the engine's own
              # cent-rounded levels (see RESTING LEVELS above _leg_accepts_return_levels),
              # only for a cfg["resting_levels"] leg (ORB_R6): the initial stop and the
              # target on its ENTRY row, the moved stop and the same target on a LEVELS row.
              # Blank on every other row and leg, and on rows written before these existed.
              "stop_px", "target_px",
              # appended, never inserted (2026-10-05, NOISE lane audit / MANAGER #65) -- the
              # DECISION BAR exactly as the engine saw it when it decided, read from the
              # plugin's own DECISION RECORD (NOISE_1_0.py's return_decisions; see DECISION
              # BARS above run_leg_trades), never re-derived from the bar cache later (the
              # feed revises bars after the fact and the cache keeps only the revision).
              # On a NOISE leg's ENTRY row: the bar at whose close the entry was decided
              # (the bar before the fill). On its EXIT row: the bar the exit was decided on
              # (the bar before the fill for a mid-session VWAP / band close; the fill bar
              # itself for a stop, a boundary touch, a VWAP / band close on the session's
              # last bar -- it fills at that same bar's close -- or the flatten). dec_bar_start/dec_bar_end = that bar's
              # start and close (ET, ISO); dec_open..dec_volume = its OHLCV; dec_vwap = the
              # session VWAP at its close; dec_band_upper/dec_band_lower = the noise band at
              # that bar; dec_rule = the comparison the rule made ("close>upper",
              # "close<lower", "close<vwap", "close>vwap", "low<=stop", "high>=stop",
              # "open<stop", "open>stop", "session_last_bar", ...); dec_level = the exact
              # value on the other side of it (the band, the VWAP or the stop; blank for
              # session_last_bar); dec_bar_source = the feed that served this tick's bars
              # (bar_source's value -- "webull"/"yfinance"/"stream" -- or "cache" for an
              # offline step that named none; never blank, so a non-blank dec_bar_source
              # marks a row that HAS a decision record). LOGGING ONLY: nothing reads these to
              # decide anything (api/cloud_signal_stream.py's _DECISION_FIELDS leaves them
              # out). Blank on SEED/LEVELS rows, on every non-NOISE leg (ORB, ENGU-Q), on a
              # NOISE row whose record did not line up with its trade (run_leg_trades logs
              # that), and on rows written before these existed.
              # NOT LOGGED HERE (2026-10-05 review): (a) the CT304/CT304H compression size
              # tilt -- its gate (BB/KC width on the 30m/60m frame vs gate_ratio) is built
              # from intraday bars that include the decision bar, so a revision CAN flip it,
              # but only its outcome is recorded, in the "size" column (1.0 vs tilt_mult);
              # (b) the bandwidth stop level set at entry -- it appears as dec_level only on
              # the stop-exit row that hits it; (c) the vol_skip / daytype session gates,
              # which read prior sessions only and so cannot move on a same-day revision.
              # dec_rule names the last bar's comparison ("close>upper"); with
              # confirm_bars > 1 the rule is a streak of such closes (live legs use 1).
              "dec_bar_start", "dec_bar_end", "dec_open", "dec_high", "dec_low", "dec_close",
              "dec_volume", "dec_vwap", "dec_band_upper", "dec_band_lower", "dec_rule",
              "dec_level", "dec_bar_source",
              # appended, never inserted (2026-10-05, MANAGER #76 -- KEEL vs FIXED) -- on the
              # ENTRY row of a LEARNED KEEL leg only (NOISE_382 live, NOISE_422_KEEL shadow):
              # keel_branch = which branch of the KEEL rule set the model part
              # (augur_engine.ml_keel.keel_branch: trust / shade / fixed-only /
              # fallback-1.0); keel_fixed_size = what v12's fixed tilts ALONE would size
              # the same entry bar (_keel_fixed_size_for_entry, the NOISE_422_FIXED rule);
              # keel_t_fast / keel_trust / keel_score = the score's own diag (fast ledger,
              # trust after the fast cut, z). LOGGING ONLY: computed after keel_size, never
              # read to size or send anything (see KEEL ENTRY EXTRAS). Blank on every other
              # row and leg, on rows written before these existed, and wherever computing
              # one failed (the trade itself is never touched).
              "keel_branch", "keel_fixed_size", "keel_t_fast", "keel_trust", "keel_score"]

# The decision-bar columns above, in order -- the only columns _decision_cols fills.
DECISION_COLS = SIGNAL_COLS[SIGNAL_COLS.index("dec_bar_start"):SIGNAL_COLS.index("dec_bar_source") + 1]

# The KEEL ENTRY EXTRAS columns above, in order -- the only columns _keel_entry_extras fills.
KEEL_EXTRA_COLS = SIGNAL_COLS[SIGNAL_COLS.index("keel_branch"):SIGNAL_COLS.index("keel_score") + 1]


def _read_signals_header(path):
    """signals.csv's on-disk header as a list of names; None if missing, empty or unreadable."""
    import csv
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return next(csv.reader(f), None) or None
    except Exception:
        return None


def _migrate_signals_header(path, cols, _retries=20, _sleep=0.05):
    """If `path` already exists under an OLDER header -- a strict prefix of `cols` (e.g.
    before `bar_source` or `trade_id` was added) -- rewrite it under the new header, padding
    every old row's missing fields with "" -- same rationale and pattern as api/qqq_exec.py's
    `_migrate_csv_header`: a code upgrade that appends a column must never desync the
    on-disk header from what DictWriter is about to write next. A no-op when the header
    already matches. Never raises.

    PREFIX ONLY (2026-09-14). Any other header -- longer, because a newer writer appended a
    column this version has never heard of, or different -- is left exactly as it is.
    Rewriting it under `cols` would delete those columns from every row, which is what the
    pre-2026-09-14 copy of this function does to trade_id whenever an old checkout appends
    to the live ledger. _append_signals writes aligned to whatever header is on disk.

    ATOMIC (2026-09-14). This used to truncate signals.csv and rewrite it in place, while
    api/qqq_exec.py reads the same file every 5 s and consumes it by ROW COUNT -- a read
    landing inside the rewrite saw a short or empty ledger. The new file is written beside
    it and renamed over it, so a reader sees the old file or the new one. Windows refuses
    that rename while any reader has the file open, so it is retried (via the shared
    qp._replace_with_retry -- this was the first of this module's writers to retry at
    all, before the OHLC cache write and state.json write gained the same helper); if it
    still fails the file is left untouched (and the next append tries again) -- never
    rewritten in place."""
    import csv
    tmp = None
    try:
        header = _read_signals_header(path)
        cols = list(cols)
        if not header or header == cols:
            return
        if not (len(header) < len(cols) and cols[:len(header)] == header):
            return
        with open(path, encoding="utf-8", newline="") as f:
            old_rows = list(csv.DictReader(f))
        tmp = "%s.%d.migrate.tmp" % (path, os.getpid())
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in old_rows:
                w.writerow({c: r.get(c, "") for c in cols})
        # log=None: this call has always failed silently (the boot-time caller logs its
        # OWN "ledger header check failed" only for a raised exception, never for this
        # already-quiet retry-exhausted path) -- keep that, don't add a new log line here.
        qp._replace_with_retry(tmp, path, log=None,
                               what="[cloud-signal] signals.csv header upgrade",
                               retries=_retries, sleep=_sleep)
        tmp = None   # renamed away on success, or already cleaned up on failure
    except Exception:
        pass
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def _append_signals(events, paths):
    if not events:
        return
    os.makedirs(paths["state_dir"], exist_ok=True)
    path = paths["signals_path"]
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    import csv
    fieldnames = SIGNAL_COLS
    if not new_file:
        _migrate_signals_header(path, SIGNAL_COLS)
        # Rows follow the header that is actually on disk: normally SIGNAL_COLS, but a newer
        # writer's longer header is never rewritten (see _migrate_signals_header), and an old
        # header stays if its upgrade could not swap in this time. Unknown columns stay "".
        fieldnames = _read_signals_header(path) or SIGNAL_COLS
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
        for e in events:
            w.writerow({k: e.get(k, "") for k in fieldnames})


# ── Decide at close (WEBULL_PAPER_TODO.md item 16, owner GO 2026-09-26) ─────────────────
# A decide-at-close plugin (NOISE_1_0.py and its wrappers) decides at the CLOSE of bar D
# (entry_pending / exit_pending) and fills at the OPEN of bar D+1, and the trade records
# D+1 as its entry/exit bar. step() only hands it CLOSED bars, so it cannot report that
# fill until D+1 has closed too: every live NOISE order went out one bar after the
# backtest's own fill (09-22..09-25). A leg with cfg["decide_at_close"] also runs the
# plugin on the same arrays plus stand-in bars, and anything the plugin fills at the
# first stand-in's OPEN was already decided at D's close -- that decision is emitted now,
# under the trade id the real D+1 bar will later produce, so it is never emitted twice.
#
# TWO flat stand-ins, not one: S1 for D+1 and S2 after it, all four prices = D's close,
# volume 0 (VWAP unchanged), D's day id. With only S1, an exit filled at S1's open and
# the plugin's end-of-data force-close at S1's close carry the SAME price, and the
# 6249926 price rule would read every queued exit as still open. With S2 the force-close
# lands on S2, so a trade closed ON S1 is a real fill -- the same rule, one bar further on.
#
# What the probe may emit, and nothing else:
#   ENTRY  a trade whose entry bar is S1 (queued at D's close).
#   EXIT   a trade the normal run reports still open, closed ON S1. Such an exit is either
#          queued at D's close or a stop hit on S1. Entered BEFORE D: a flat S1 sits inside
#          D's own range, so a fixed stop that D itself did not touch cannot be hit on S1.
#          Entered ON D (plugins skip the stop on the entry bar, so D may already sit past
#          it): only if a CONFIRM run, with the stand-ins far on the position's winning
#          side where no stop can fill, still closes it on S1 at S1's own open.
#   That is the promise a leg makes by setting the flag: it DECIDES at a bar's close and
#   FILLS at the next bar's open (never at the fill bar's own close), and its stops are
#   levels fixed at entry, checked on every later bar's open/high/low (true of
#   NOISE_1_0.py; NOT of ORB_3_6.py, which enters at the signal bar's own close -- run
#   there, the probe would invent entries from the stand-in's close; nor of a trailing
#   stop or a target that fills at a gap open).
#   Anything else -- every fill on S2, the S1 exit of a trade that entered on S1 -- rests
#   on stand-in data and is ignored.
# No probe when D is not from `now`'s own session, or D is its session's last bar (no
# D+1 exists: the plugin flattens at D's close).
DECIDE_AT_CLOSE_TAG = "decide_at_close"


def _is_session_last_bar(bar_start, tf):
    """True when a bar starting at `bar_start` (ET) closes at or after its session's
    close (16:00, or 13:00 on a recognised half day)."""
    hh, mm = (int(x) for x in market_calendar.session_close_et(bar_start.date()).split(":"))
    end_min = bar_start.hour * 60 + bar_start.minute + TIMEFRAME_SECONDS[tf] // 60
    return end_min >= hh * 60 + mm


def _session_close_dt(now):
    """Today's session close (16:00, or 13:00 on a recognised half day) as an ET datetime,
    or None when `now`'s date is not a session. A naive `now` is read as ET. Never raises."""
    try:
        if now is None:
            return None
        et = now.astimezone(_zi(TZ)) if now.tzinfo is not None else now.replace(tzinfo=_zi(TZ))
        if not market_calendar.is_session(et.date()):
            return None
        hh, mm = (int(x) for x in market_calendar.session_close_et(et.date()).split(":"))
        return et.replace(hour=hh, minute=mm, second=0, microsecond=0)
    except Exception:
        return None


def _at_or_after_session_close(now):
    """True from today's session close onward (same session day only). Never raises."""
    close_dt = _session_close_dt(now)
    if close_dt is None:
        return False
    et = now.astimezone(_zi(TZ)) if now.tzinfo is not None else now.replace(tzinfo=_zi(TZ))
    return et >= close_dt


def _stand_in_arrays(arrays, tf, pads=2, price=None):
    """`arrays` plus `pads` flat stand-in bars after its last bar, at `price` (default: the
    last close -- see the block above)."""
    import numpy as np
    import pandas as pd
    last_px = float(arrays["close"][-1]) if price is None else float(price)
    step_td = pd.Timedelta(seconds=TIMEFRAME_SECONDS[tf])
    idx = arrays["index"]
    out = dict(arrays)
    for k in ("open", "high", "low", "close"):
        out[k] = np.concatenate([np.asarray(arrays[k], dtype=float), np.full(pads, last_px)])
    out["volume"] = np.concatenate([np.asarray(arrays["volume"], dtype=float), np.zeros(pads)])
    out["day_id"] = np.concatenate([arrays["day_id"],
                                    np.full(pads, arrays["day_id"][-1], dtype=arrays["day_id"].dtype)])
    out["index"] = idx.append(pd.DatetimeIndex([idx[-1] + step_td * (i + 1) for i in range(pads)]))
    return out


def _decide_at_close_probe(arrays, trades, tf, now, run, log=print):
    """(trades, arrays_for_diff): `trades` (the normal run over `arrays`, ending at bar D)
    plus what the plugin already decided at D's close -- new ENTRY trades filled at S1,
    and still-open trades it closes at S1 -- tagged "probe_entry"/"probe_exit" for the
    signal row's reason. `run(arrays)` runs the leg exactly as step() just did. Returns
    the inputs unchanged when there is no probe or it finds nothing; never raises."""
    try:
        idx = arrays["index"]
        n = len(arrays["close"])
        d_start = idx[-1]
        if n < 2 or d_start.date() != now.astimezone(d_start.tzinfo).date() \
                or _is_session_last_bar(d_start, tf):
            return trades, arrays
        probe_arrays = _stand_in_arrays(arrays, tf)
        s1_time = probe_arrays["index"][n].isoformat()
        d_close = round(float(arrays["close"][-1]), 4)
        tag = (f"{DECIDE_AT_CLOSE_TAG}: decided at the close of the {d_start.strftime('%H:%M')} "
               f"bar, priced at that close")
        new_entries, early_exits, entered_on_d = [], set(), {}
        # DECISION BARS: the probe run's own exit record for each early exit -- decided at D's
        # close, a REAL bar (index n - 1); a record on a stand-in (index >= n) is dropped.
        exit_decisions = {}

        def _real_exit_decision(t):
            dx = (t.get("decision") or {}).get("exit")
            if dx and isinstance(dx.get("_bar"), int) and dx["_bar"] <= n - 1:
                return dx
            return None
        for t in run(probe_arrays):
            key = (t["entry_time"], t["side"])
            if t["entry_bar"] == n:
                dec = t.get("decision")
                new_entries.append(dict(t, still_open=True, exit_time=None, exit_px=None,
                                        probe_entry=tag,
                                        decision=(dict(dec, exit=None) if dec else dec)))
            elif t["exit_time"] == s1_time:
                if t["entry_bar"] < n - 1:
                    early_exits.add(key)
                    exit_decisions[key] = _real_exit_decision(t)
                elif t["entry_bar"] == n - 1:
                    entered_on_d[key] = t["side"]
        # CONFIRM RUN (entered on D): same bars, the stand-ins moved far onto the winning side
        # of that position, where no stop can fill. Still closed on S1, at S1's own open ->
        # the exit was queued at D's close, not a stop guessed from stand-in data.
        for side in sorted(set(entered_on_d.values())):
            far = float(arrays["close"][-1]) * (2.0 if side == "long" else 0.5)
            for t in run(_stand_in_arrays(arrays, tf, price=far)):
                key = (t["entry_time"], t["side"])
                if (entered_on_d.get(key) == side and t["exit_time"] == s1_time
                        and abs(float(t["exit_px"]) - far) <= 1e-6 * far):
                    early_exits.add(key)
                    exit_decisions[key] = _real_exit_decision(t)
        if not new_entries and not early_exits:
            return trades, arrays
        out = []
        for t in trades:
            if t["still_open"] and (t["entry_time"], t["side"]) in early_exits:
                t = dict(t, still_open=False, exit_time=s1_time, exit_px=d_close, probe_exit=tag)
                if t.get("decision"):
                    t["decision"] = dict(t["decision"],
                                         exit=exit_decisions.get((t["entry_time"], t["side"])))
            out.append(t)
        return out + new_entries, probe_arrays
    except Exception as e:
        log(f"[cloud-signal] decide_at_close probe failed ({type(e).__name__}: {e}) -- "
            f"falling back to the closed-bar signals for this bar")
        return trades, arrays


def leg_decision_trades(cfg, arrays, leg_key, tf, now, paths, fetch, log=print):
    """(trades, diff_arrays): everything step() does to one leg between closed_arrays and
    _diff_leg -- run_leg_trades with `now`/`paths`/`fetch` (the session_in_progress and
    vol_prior_ranges pass-throughs), then, for a cfg["decide_at_close"] leg, the
    decide_at_close probe; `diff_arrays` is what _diff_leg must be handed. ONE function so
    step() and api/cloud_signal_stream.py's stream decision cannot drift apart again (the
    stream path once skipped all three extras -- WEBULL_PAPER_TODO.md item 10). The stream
    calls this with fetch=False: it must never touch the network, and step() runs right
    after it on the same tick and does the daily-cache refresh.

    A DIP leg (cfg["runner"] == DIP_RUNNER) goes to api/dip_live.py instead and NEVER reaches
    run_leg_trades (whose 5-field unpack raises on the file's 6-field trades and would read
    its dollar P&L as a price move): (trades, arrays), where trades is None while its daily
    series is not ready -- step() then skips the leg's diff (no SEED) and retries next bar."""
    if cfg.get("runner") == DIP_RUNNER:
        return run_dip_leg_trades(cfg, arrays, leg_key, now, paths, log), arrays
    trades = run_leg_trades(cfg, arrays, leg_key=leg_key, log=log, now=now, paths=paths,
                            fetch=fetch)
    diff_arrays = arrays
    if cfg.get("decide_at_close"):
        # The probe must run the leg exactly like the call above -- keep the two in step.
        # fetch=False: the call above already refreshed the daily cache this tick, so the
        # probe reads the same file without a second network call.
        trades, diff_arrays = _decide_at_close_probe(
            arrays, trades, tf, now,
            lambda a: run_leg_trades(cfg, a, leg_key=leg_key, log=log, now=now, paths=paths,
                                     fetch=False),
            log=log)
    return trades, diff_arrays


def run_dip_leg_trades(cfg, arrays, leg_key=None, now=None, paths=None, log=print):
    """A DIP #424 leg's trade dicts for this tick, or None while its daily series is not ready
    (see api/dip_live.py run_dip_leg_trades -- this is the module's one entry point here)."""
    from api import dip_live as _dip
    return _dip.run_dip_leg_trades(cfg, arrays, leg_key=leg_key, now=now, paths=paths, log=log)


def _dip_daily_series(arrays, now, paths, params=None, log=print):
    """(series, None) or (None, (reason_key, text)) -- api/dip_live.py build_daily_series on
    the DIP legs' params (default DIP_424_PARAMS)."""
    from api import dip_live as _dip
    return _dip.build_daily_series(arrays, now, paths, dict(params or DIP_424_PARAMS), log=log)


# ── The core entry point ───────────────────────────────────────────────────────────────
def step(now=None, legs=None, paths=None, fetch=True, warnings=None, bar_sources=None,
         post_close=False):
    """One signal-engine tick. For each leg: load cached bars (optionally refreshed
    from yfinance first), restrict to bars CLOSED as of `now`, run the engine over the
    rolling warm-up window, and diff the resulting trade list against what was last
    persisted for that leg. Returns the list of NEW events emitted THIS call (empty on
    a rerun at the same `now` — idempotent by construction: every event is keyed by
    the trade id (leg, entry bar time, side -- see _entry_key) and a key already recorded
    in state.json is never re-emitted).

    `legs`: defaults to CROWN_LEGS; pass a different dict (e.g. with a stub strategy
    module as cfg["strategy"]) to test the diff/idempotency machinery in isolation.
    `fetch`: pull fresh bars over the network first. --replay always passes False (it
    must stay fully offline and deterministic); --once/--loop pass True.
    `paths`: the state store. Defaults to the live DEFAULT_PATHS ONLY for a fetching
    (live) call. An offline call (fetch=False) must name its store: it used to fall
    through to the live ledger too, which is how a replay contaminated it twice (see
    isolated_paths), and a lone offline step into a fresh scratch store could only ever
    cold-start, so there is no useful default to give it instead.
    `warnings`: optional dict this call may POPULATE (never reads) with non-fatal
    problems the caller should surface without treating the whole tick as failed.
    Currently only `cache_write_failed` (bool, 2026-09-14): at least one timeframe's
    on-disk bar cache could not be replaced this call even after fetch_and_merge's own
    retries, though the freshly fetched bars were still used from memory for every
    leg's signal evaluation below (they are already in `tf_cache` by the time the
    rename is attempted -- see fetch_and_merge). A caller that writes a heartbeat
    (cloud_signal_thread, cmd_once, cmd_loop) uses this to still report ok=True with a
    note instead of raising, so a transient disk/lock hiccup does not make
    api/qqq_exec.py's engine-mode feed check see a stale heartbeat and block entries
    over something that never affected the signals it will act on.
    `bar_sources`: optional {timeframe: "webull"/"yfinance"} for a fetch=False call whose
    bars a fetching caller has JUST refreshed on disk (run_shadow_step, 2026-09-28): it is
    recorded and stamped exactly as a fetch's own source would be. Ignored for a timeframe
    this call fetched itself; None (every other caller) changes nothing.
    `post_close` (2026-09-28): the EOD SETTLE step (see _eod_settle_tick) -- passed to
    _diff_leg, which then never emits an ENTRY. Also reports, via `warnings`
    ("eod_settled", "eod_bars"), whether every cfg["eod_flat"] leg's newest usable bar
    is today's last session bar, and stamps state["eod_settled"][date] when it is.
    """
    legs = legs if legs is not None else CROWN_LEGS
    if paths is None:
        if not fetch:
            raise ValueError("step(fetch=False) needs an explicit `paths`: an offline step must "
                             "not default to the live ledger -- use replay() or "
                             "isolated_paths(), or pass DEFAULT_PATHS on purpose")
        paths = DEFAULT_PATHS
    now = now or _dt.datetime.now(tz=_zi(TZ))
    if now.tzinfo is None:
        now = now.replace(tzinfo=_zi(TZ))

    state = _load_state(paths)
    state.setdefault("legs", {})
    all_events = []

    tf_cache = {}
    # PRICE-SOURCE ATTRIBUTION (feature: engine-mode status panel / api/qqq_exec.py):
    # persisted to state.json below as state["bar_source"][tf], not kept only in this
    # in-process dict -- the standalone qqq_exec adapter is a DIFFERENT process and can
    # only see this via the file (see read_bar_source).
    tf_source = {}
    # EOD SETTLE (2026-09-28): per cfg["eod_flat"] leg, the newest usable bar's start and
    # whether it is today's last session bar -- read before the "no new bar" short-circuit
    # below, so a repeat settle step still knows the day is complete.
    eod_bars = {}
    for key, cfg in legs.items():
        tf = cfg["timeframe"]
        if cfg.get("eod_flat"):
            eod_bars[key] = None
        if fetch and tf not in tf_cache:
            tf_cache[tf], tf_source[tf], cache_ok = fetch_and_merge(tf, paths)
            if not cache_ok and warnings is not None:
                warnings["cache_write_failed"] = True
        elif tf not in tf_cache:
            tf_cache[tf] = historical_bars(tf, paths)
            if bar_sources and bar_sources.get(tf):
                tf_source[tf] = bar_sources[tf]
        epoch_df = tf_cache[tf]
        leg_state = state["legs"].setdefault(key, {"trades": {}})
        # LIVE SINCE (2026-10-09): an earlier stint's state is discarded before anything reads
        # it -- including the "no new bar" short-circuit below -- and persisted as discarded
        # by this call's own state write even when no bar is usable yet.
        _apply_live_since(key, cfg, leg_state, now=now)
        if epoch_df is None or not len(epoch_df):
            continue

        # Skip the (expensive) engine recompute unless a NEW bar of THIS leg's own
        # timeframe has closed since the last time we checked. A 5m leg ticked every
        # minute (replay()) or every 20s (--loop) only has real work to do once every
        # 5 real minutes — its trade list literally cannot have changed without a new
        # bar — and recomputing anyway is exactly what made an early version of this
        # function cost O(ticks) instead of O(bars) per replayed session.
        cutoff = _closed_cutoff_epoch(now, tf)
        usable = epoch_df[epoch_df["time"] <= cutoff]
        if not len(usable):
            continue
        latest_bar_epoch = int(usable["time"].max())
        if cfg.get("eod_flat"):
            try:
                bar_start = _dt.datetime.fromtimestamp(latest_bar_epoch, tz=_zi(TZ))
                if bar_start.date() == now.astimezone(_zi(TZ)).date() \
                        and _is_session_last_bar(bar_start, tf):
                    eod_bars[key] = bar_start.isoformat()
            except Exception:
                pass
        if tf in tf_source:
            state.setdefault("bar_source", {})[tf] = {
                "source": tf_source[tf], "newest_epoch": latest_bar_epoch,
                "checked_at": now.isoformat()}
        if leg_state.get("last_bar_epoch") == latest_bar_epoch:
            continue
        leg_state["last_bar_epoch"] = latest_bar_epoch

        arrays = closed_arrays(epoch_df, now, tf, leg_warmup_sessions(cfg))
        if arrays is None:
            continue

        # KEEL FALLBACK PUSH (deadman/deadman_keel_guard, 2026-09-26): a standalone
        # freshness read, independent of whether this tick's diff below finds a new
        # entry to score -- see _maybe_push_keel_fallback / _keel_fallback_reason.
        # Runs here (once per leg per NEW bar, same cadence as the recompute above)
        # rather than every tick: cheap and frequent enough (every 5 real minutes for
        # NOISE_382) for a once-per-day push, without re-adding the O(ticks) cost the
        # comment above this block exists to avoid.
        #
        # ONLY on a LIVE tick on the CLOUD BOX (fetch=True AND EDGELOG_HOST_ROLE=cloud,
        # see _is_cloud_host) -- 2026-09-26 fix. api/runner.py's cloud_signal_thread
        # calls this same step() from the PC runner too, and the PC never has a KEEL
        # state directory (it is only ever built on the box), so without this gate the
        # PC would push a false "keel state unavailable" every trading day, using the
        # SAME title as a real box alert -- the owner could never tell them apart. A
        # replay (--replay always passes fetch=False) hits the same gate: replaying N
        # historical days with a live NTFY_TOPIC set must never send N false pushes for
        # a "staleness" that is just how far in the past the replay's own `now` is.
        # Never for a shadow leg (cfg["shadow"] -- see _push_allowed).
        keel_cfg = (cfg or {}).get("keel")
        if keel_cfg and _push_allowed(cfg, fetch):
            _maybe_push_keel_fallback(key, keel_cfg, now, state, arrays=arrays)

        # run_leg_trades (+ the decide_at_close probe for a flagged leg) -- shared with the
        # stream path (api/cloud_signal_stream.py) so the two can never decide differently
        # off the same bars; see leg_decision_trades.
        trades, diff_arrays = leg_decision_trades(cfg, arrays, key, tf, now, paths, fetch)
        if trades is None:
            # only a DIP leg's runner ever says "not ready" (its daily series -- see
            # api/dip_live.py): no diff and no SEED; last_bar_epoch already moved, so the next
            # new bar retries
            continue
        # Three bars of grace by default: a signal may legitimately be discovered a bar or
        # so late, but never hours late (see _diff_leg's LATE ENTRIES note). A leg may set
        # its own `max_entry_age_sec` when its bar size makes three bars the wrong measure.
        events = _diff_leg(key, trades, leg_state, now,
                           max_entry_age_sec=cfg.get("max_entry_age_sec",
                                                     3 * TIMEFRAME_SECONDS[tf]),
                           bar_source=(state.get("bar_source", {}).get(tf, {}).get("source")),
                           cfg=cfg, arrays=diff_arrays, fetch=fetch, post_close=post_close)
        all_events.extend(events)
        leg_state["asof"] = arrays["index"][-1].isoformat()

    # FEED HEALTH (2026-10-05, sweep findings 6 + 15): how fresh each timeframe's closed bars
    # are, for the caller's heartbeat -- see bar_health / _feed_health.
    if warnings is not None:
        health = warnings.setdefault("bar_health", {})
        for tf, frame in tf_cache.items():
            try:
                h = bar_health(frame, now, tf)
            except Exception as e:
                h = {"timeframe": tf, "error": f"{type(e).__name__}: {e}"}
            h["source"] = tf_source.get(tf)
            h["fetched"] = bool(fetch and tf in tf_source)
            health[tf] = h

    if post_close:
        settled = all(v is not None for v in eod_bars.values())
        if settled:
            day = now.astimezone(_zi(TZ)).date().isoformat()
            stamps = state.setdefault("eod_settled", {})
            stamps[day] = {"at": now.isoformat(), "bars": dict(eod_bars)}
            for old in sorted(stamps)[:-10]:          # a short history is plenty
                stamps.pop(old, None)
        if warnings is not None:
            warnings["eod_settled"] = settled
            warnings["eod_bars"] = dict(eod_bars)

    state["generated_at"] = now.isoformat()
    _write_state(state, paths)
    _append_signals(all_events, paths)
    # KEEL ENTRY EXTRAS (MANAGER #76): the log line per learned-KEEL entry + the size-diff
    # alert, AFTER the rows are written -- never raises, never touches an event. The push goes
    # on a daemon thread (as the stream commit's does): a "default" push is a single plain try
    # with a network timeout, and the engine thread / heartbeat must not wait it out.
    _note_keel_entries(all_events, legs, paths, fetch, push=_engine_push_background)
    return all_events


def _levels_reason(lv, tf):
    """'breakeven armed at the close of 11:05 (the 11:00 bar)' -- the LEVELS row's reason.
    The bar CLOSES `tf` after the start time the ledger stamps (ref_time)."""
    try:
        start = _dt.datetime.fromisoformat(str(lv["be_armed_time"]))
        start = start.astimezone(_zi(TZ)) if start.tzinfo else start
        if tf in TIMEFRAME_SECONDS:
            close = start + _dt.timedelta(seconds=TIMEFRAME_SECONDS[tf])
            return (f"breakeven armed at the close of {close:%H:%M} (the {start:%H:%M} bar); "
                    f"stop {lv['be_stop_px']} from the next bar")
        return (f"breakeven armed at the close of the {start:%H:%M} bar; "
                f"stop {lv['be_stop_px']} from the next bar")
    except Exception:
        return f"breakeven armed; stop {lv.get('be_stop_px')} from the next bar"


def _zi(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        import pytz
        return pytz.timezone(name)


def _seed_carry_sizes(cfg, t):
    """(size, keel_size) for a seeded carry: the plugin's own size with keel_size blank (KEEL is
    never scored for a seeded trade) -- except on a mode="const" leg (DIP_424F), whose one size
    is a rule, not a score, and applies to every trade it holds: plugin x const, const."""
    size = t.get("size", 1.0)
    keel_cfg = (cfg or {}).get("keel")
    if keel_cfg and keel_mode(keel_cfg) == KEEL_MODE_CONST:
        k, diag = _keel_const_size(keel_cfg)
        if isinstance(diag, dict):
            return size * k, k
    return size, ""


def _seeded_entry_event(leg_key, key, t, rec, bar_source, why, cfg=None):
    """The ONE ENTRY row a shadow leg writes for a trade it was already holding at its seed
    (see SEED_OPEN_FORMAT): the trade's own entry time and price, its id, the plugin's own
    size (KEEL is never scored for a seeded trade -- keel_size stays blank, as on SEED; a
    mode="const" leg's constant size does apply, see _seed_carry_sizes), and a reason that
    starts with SEEDED_REASON_TAG. Also marks `rec` as carried (exit owed)."""
    size, keel_size = _seed_carry_sizes(cfg, t)
    if t.get("slot"):
        why = f"{why} (slot={t['slot']})"
    rec.update({"exit_emitted": False, "seeded_open": True, "size": size, "keel_size": keel_size})
    return {
        "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
        "leg": leg_key, "event": "ENTRY", "side": t["side"],
        "ref_time": t["entry_time"], "ref_price": t["entry_px"],
        "shares": t["shares"],
        "reason": f"{SEEDED_REASON_TAG}; {why} -- a would-be trade entered before the seed, "
                  "no order",
        "bar_source": bar_source or "",
        "trade_id": key if _trade_id.is_valid(key) else "",
        "size": size, "keel_size": keel_size,
    }


def _carry_seeded_open(leg_key, trades, leg_state, bar_source, now, cfg=None):
    """ONE-TIME upgrade of a shadow leg seeded before SEED_OPEN_FORMAT existed (ENGUQ_335 on
    the box: seeded 2026-09-29 09:30 holding the 2026-09-28 12:32 long, recorded as
    exit_emitted with no exit). A seed record with no exit_time was open at the seed; if the
    engine's trade list still holds that trade (open, or closed since -- the caller's diff
    then emits its EXIT on this same call), it gets its seeded ENTRY now and its exit is owed
    again. A record the window no longer holds stays absorbed and is counted in
    leg_state["seed_open_lost"]. Stamps leg_state["seed_open_format"], so it runs once."""
    events = []
    recorded = leg_state.setdefault("trades", {})
    by_key = {_entry_key(leg_key, t): t for t in trades}
    for key, rec in recorded.items():
        if not (rec.get("seeded") and rec.get("exit_emitted") and not rec.get("seeded_open")
                and rec.get("exit_time") is None):
            continue
        t = by_key.get(key)
        if t is None:
            leg_state["seed_open_lost"] = int(leg_state.get("seed_open_lost", 0)) + 1
            continue
        events.append(_seeded_entry_event(
            leg_key, key, t, rec, bar_source,
            f"open at this shadow leg's cold start, carried on {now.date().isoformat()}", cfg=cfg))
    leg_state["seed_open_format"] = SEED_OPEN_FORMAT
    return events


def _diff_leg(leg_key, trades, leg_state, now, max_entry_age_sec=None, bar_source=None,
             cfg=None, arrays=None, fetch=True, log=print, post_close=False,
             not_taken_log=None):
    """Mutates leg_state['trades'] (entry_key -> record) in place; returns the list of
    NEW ENTRY/EXIT event dicts this call discovered.

    `post_close` (2026-09-28, EOD SETTLE -- see the block above cloud_signal_thread): the
    step runs after the session's close. A trade FIRST seen then is recorded silently
    (skip "after_close", counted in leg_state['after_close_skipped']) with its EXIT
    suppressed -- nothing can be bought after the bell, so no actionable ENTRY is ever
    emitted then. EXITs of trades whose ENTRY was already emitted still emit, tagged
    "eod_settle" in the reason. Also switched on automatically whenever `now` is at or
    past today's session close (a stream or regular step that lands on the bell).

    `cfg`/`arrays` (2026-09-23, KEEL overlay): `cfg` is this leg's own CROWN_LEGS entry
    (step() always passes it; a caller that omits it -- every test written before this
    feature, and any leg with no "keel" block -- gets EXACTLY today's pre-KEEL
    behaviour, see the ENTRY branch below) and `arrays` are the QQQ arrays `trades` was
    computed from, needed to slice the new entry's own feature row. KEEL is scored
    ONCE, only for a leg whose cfg carries a "keel" block, only at the moment an ENTRY
    is about to be emitted (never during SEED -- see the COLD START note below -- and
    never recomputed for that trade's later EXIT, which reuses the value this call
    stores on `rec`).

    `bar_source` ("webull"/"yfinance"/None) is stamped onto every event this call emits
    (including SEED) so a downstream consumer -- api/qqq_exec.py's engine mode, or the
    web tab's status panel -- can show which QQQ feed priced this specific trade, without
    re-deriving it later from a rolling bar_source history that may have moved on.

    STALE ENTRIES ARE NEVER ACTIONABLE. The engine recomputes each leg's trade list
    over a ROLLING warm-up window, and a trade sitting at that window's left edge is
    not identity-stable: strategies warm their indicators from the first bar of the
    array they are handed (ORB_3_6.py's volume-pace reference is a 20-bar nanmean that
    is literally an empty slice at index 0), so as the window slides forward the oldest
    trades can shift entry bar or entry price by a hair -- which changes their
    _entry_key and makes them look brand new. Measured on the real QQQ cache: a
    2026-09-04 replay emitted ENTRY events dated 2026-07-01 for exactly this reason.
    An entry that is not in TODAY's session cannot be acted on at today's price under
    any circumstances, so it is recorded silently (and counted in
    leg_state['stale_skipped']) instead of being emitted. Its exit is suppressed with
    it -- an executor that never entered cannot exit. Exits of trades whose ENTRY *was*
    emitted still fire normally on a later day (an overnight ENGU-Q hold closing the
    next morning is a real, wanted EXIT).

    COLD START (leg never seen before). The engine re-derives each leg's WHOLE trade
    list over the rolling warm-up window on every call, so the very first call for a
    leg legitimately "discovers" every trade the strategy took over the last N
    sessions. Emitting those as ENTRY/EXIT would hand a downstream execution layer
    dozens of actionable orders for trades that closed weeks ago -- the same defect
    api/qqq_exec.py had to fix for NinjaTrader fills on first boot (v73.459, "never
    replay pre-today fills"). So the first call for a leg ABSORBS the history
    silently: every trade is recorded as already-emitted (including one that is still
    open -- an executor that never entered cannot exit) and a single non-actionable
    SEED event is written to the ledger naming what was absorbed. Only trades the
    engine opens AFTER the seed produce ENTRY/EXIT. Consumers must act on ENTRY/EXIT
    only and ignore any other event type.

    SHADOW LEGS ARE THE ONE EXCEPTION (2026-10-07, MANAGER #87 -- see SEED_OPEN_FORMAT). A
    shadow leg (cfg["shadow"]) places no orders, so "an executor that never entered cannot
    exit" does not apply to it, and absorbing its open trade only loses a would-be trade
    (ENGUQ_335 seeded 2026-09-29 09:30 holding the 09-28 12:32 long, and logged nothing
    for it). Its trade still OPEN at the seed is carried: the SEED row is followed by ONE
    ENTRY at that trade's own entry time and price, reason "seeded=1; ...", and its EXIT
    follows when the strategy closes it. Closed history is still absorbed silently. Written
    once: state.json's leg_state["seeded"] stops a second cold start, so a restart never
    repeats it. A shadow leg seeded before this existed is upgraded once by
    _carry_seeded_open (below).

    LIVE SINCE (2026-10-09 -- see the block above _apply_live_since). A cfg carrying
    "live_since" whose value `leg_state` does not carry yet gets its state discarded first
    (step() already did that on its own call; this covers every other caller, e.g. the
    stream path), so the leg cold-starts here: SEED only, the SEED reason naming it.

    AFTER-CLOSE ENTRIES GET ONE LOG LINE (2026-10-09). A live leg's NEW entry first seen once
    its session has closed is still never emitted, but it is no longer silent: one plain line
    names the strategy, side, the signal's bar time and why (_not_taken_after_close_line).
    Two shapes: the "after_close" skip below (first seen after today's bell), and a "stale"
    entry dated the session right before `now`'s (first seen the next session -- ENGU-Q's
    phantom_safe walk only finishing a 15:5x setup's fill window on the next morning's bars,
    or an EOD settle that gave up; see _entry_from_previous_session). Older stale entries
    (the rolling window's left edge re-minting a trade) stay silent. Once per trade -- its
    record stops a repeat. Not for a shadow leg (it sends no order either way).
    `not_taken_log` receives that line (default: `log`); False drops it. The stream path's
    dry runs on throwaway state copies (api/cloud_signal_stream._dry_run_decision) collect it
    and log it only for a decision they commit, so a tick through the stream path still logs
    it once -- not once per dry run plus once more from step().

    TRADE ID (2026-09-14). Every ENTRY and EXIT event carries `trade_id` (api/trade_id.py),
    the same value on both rows of one trade, and it is also the key of this leg's memory
    (see _entry_key; _rekey_recorded_trades upgrades a pre-2026-09-14 memory once). An
    executor closes a position only with the EXIT whose trade_id matches the one it opened.

    `fetch` (2026-09-26, deadman/deadman_keel_guard): step()'s own `fetch` passed straight
    through, gating ONLY the scoring-time KEEL fallback push below (same live+cloud-box
    gate as step()'s standalone _maybe_push_keel_fallback) -- never anything else here.
    Defaults True so every pre-existing direct caller (every test written before this
    feature) keeps behaving exactly as before; the push itself additionally requires
    EDGELOG_HOST_ROLE=cloud, so it stays a no-op off the box regardless.

    RESTING LEVELS (2026-09-29). Only for a cfg["resting_levels"] leg whose trades carry
    "levels" (run_leg_trades): the ENTRY row gains stop_px/target_px, and when breakeven
    has armed on an open trade whose ENTRY was emitted, ONE "LEVELS" row names the moved
    stop (ref_time = the arming bar, ref_price = stop_px = the new stop). It is keyed on
    the trade's memory record like every other event (rec["be_emitted"]), so a re-run
    tick never repeats it; it is never written for a skipped/seeded trade, a trade that
    closed in the same diff (its EXIT says it all), or after the close.
    """
    events = []
    levels_on = bool((cfg or {}).get("resting_levels"))
    _apply_live_since(leg_key, cfg, leg_state, now=now, log=log)   # LIVE SINCE -- see the docstring
    _rekey_recorded_trades(leg_key, leg_state)
    recorded = leg_state.setdefault("trades", {})
    carry_open = bool((cfg or {}).get("shadow"))      # SHADOW legs only -- see SEED_OPEN_FORMAT
    if not leg_state.get("seeded"):
        open_at_seed = "none"
        carried = []
        for t in trades:
            key = _entry_key(leg_key, t)
            carry = carry_open and bool(t["still_open"])
            recorded[key] = {
                "entry_time": t["entry_time"], "side": t["side"],
                "entry_px": t["entry_px"], "shares": t["shares"],
                "exit_emitted": not carry, "exit_time": t.get("exit_time"),
                "exit_px": t.get("exit_px"), "seeded": True,
            }
            if t.get("slot"):
                recorded[key]["slot"] = t["slot"]      # DIP legs only (see _entry_key)
            if t["still_open"]:
                open_at_seed = f"{t['side']} @ {t['entry_px']} ({t['entry_time']})"
            if carry:
                carried.append((key, t))
        leg_state["seeded"] = True
        if carry_open:
            leg_state["seed_open_format"] = SEED_OPEN_FORMAT
        events.append({
            "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
            "leg": leg_key, "event": "SEED", "side": "", "ref_time": "",
            "ref_price": "", "shares": "", "bar_source": bar_source or "", "trade_id": "", "size": "",
            # KEEL is never scored during a cold-start SEED (design: "the cold-start
            # SEED path must not score or emit anything") -- a batch of dozens of
            # absorbed historical trades is not one live entry, and none of them are
            # ever acted on, so there is nothing meaningful to size.
            "keel_size": "",
            "reason": (f"cold start: absorbed {len(trades)} historical trade(s) without "
                       f"emitting; open_at_seed={open_at_seed}"
                       + ("; shadow leg: carried as an open would-be trade" if carried else "")
                       + (f"; live_since={leg_state[LIVE_SINCE_KEY]} (earlier state discarded, "
                          "starts flat)" if leg_state.get(LIVE_SINCE_KEY) else "")),
        })
        for key, t in carried:
            events.append(_seeded_entry_event(leg_key, key, t, recorded[key], bar_source,
                                              "open at this shadow leg's cold start", cfg=cfg))
        return events
    if carry_open and leg_state.get("seed_open_format") != SEED_OPEN_FORMAT:
        # a shadow leg seeded before SEED_OPEN_FORMAT existed: carry its open-at-seed trade
        # now (once), then fall through -- the diff below emits its EXIT if it has closed
        events.extend(_carry_seeded_open(leg_key, trades, leg_state, bar_source, now, cfg=cfg))
    # LATE ENTRIES ARE NOT ACTIONABLE EITHER (2026-09-09, seen live). "Entry is from today"
    # was too weak a test. After the 12:44 runner restart this engine re-derived the day and
    # emitted an ENGU-Q ENTRY stamped 10:07 -- two and a half hours old -- because it was
    # still technically today. An executor cannot take a 10:07 price at 12:44; it would open
    # at a different price than the one the signal was justified at, which is precisely the
    # divergence the whole parallel run exists to measure. Being one bar late is normal and
    # fine; being hours late means a gap (restart, data outage) and the trade is gone. So an
    # entry must be within a few bars of `now` to emit, and anything older is recorded
    # silently and counted in `late_skipped` -- visible, but never handed downstream.
    today = now.date().isoformat()
    post_close = bool(post_close) or _at_or_after_session_close(now)
    for t in trades:
        key = _entry_key(leg_key, t)
        tid = key if _trade_id.is_valid(key) else ""
        rec = recorded.get(key)
        if rec is None:
            # One trade, ONE reason. STALE = the entry is not even from today (the rolling
            # window's left edge re-minting an old trade). LATE = today, but discovered too
            # many bars after the fact to act on. AFTER_CLOSE = first seen once the session
            # has closed (see `post_close`). They are different failures and counting a
            # trade under two makes each counter a lie.
            skip = None
            if str(t["entry_time"])[:10] != today:
                skip = "stale"
            elif post_close:
                skip = "after_close"
            elif max_entry_age_sec:
                try:
                    entered = _dt.datetime.fromisoformat(str(t["entry_time"]))
                    if entered.tzinfo is None:
                        entered = entered.replace(tzinfo=_zi(TZ))
                    if (now - entered).total_seconds() > max_entry_age_sec:
                        skip = "late"
                except Exception:
                    pass
            recorded[key] = {"entry_time": t["entry_time"], "side": t["side"],
                             "entry_px": t["entry_px"], "shares": t["shares"],
                             "exit_emitted": bool(skip), "exit_time": None,
                             "exit_px": None, "skipped": skip}
            if t.get("slot"):
                recorded[key]["slot"] = t["slot"]      # DIP legs only (see _entry_key)
            if skip:
                counter = f"{skip}_skipped"
                leg_state[counter] = int(leg_state.get(counter, 0)) + 1
                note = log if not_taken_log is None else not_taken_log
                if note and not (cfg or {}).get("shadow") and (
                        skip == "after_close"
                        or (skip == "stale" and _entry_from_previous_session(t, now))):
                    # the market is closed: never emitted, never silent (see the docstring)
                    note(_not_taken_after_close_line(leg_key, t, now))
                continue
            # real per-trade size when the leg declares one, else 1.0 -- see
            # run_leg_trades's PER-TRADE SIZE contract and SIGNAL_COLS's "size" column.
            # This is the PLUGIN's own size -- KEEL (below) multiplies IT, never the
            # other way around, and the P&L un-fold inside run_leg_trades already used
            # this same plugin size alone (KEEL is computed after that un-fold, so it
            # cannot touch it).
            plugin_size = t.get("size", 1.0)
            keel_size = ""
            final_size = plugin_size
            keel_extras = None
            keel_cfg = (cfg or {}).get("keel")
            if keel_cfg:
                # KEEL SCORED ONCE, HERE -- exactly when this new entry is about to be
                # emitted (design: "compute the KEEL size once and emit size = plugin
                # size x keel size"). Never recomputed for this trade again -- the
                # EXIT branch below reuses `rec`'s stored values -- and never called
                # during SEED (see that branch, above).
                _ks_scratch = {}       # the score's own features / rule cfg, for the extras
                ks, _diag = _keel_size_for_entry(keel_cfg, arrays, t.get("entry_bar"),
                                                 t["entry_time"], log=log, scratch=_ks_scratch)
                keel_size = ks
                final_size = plugin_size * ks
                # SCORING-TIME FALLBACK PUSH (minor fix, deadman/deadman_keel_guard,
                # 2026-09-26). _keel_fallback_reason (step()'s standalone freshness
                # read) never calls keel_score_from_state, so it cannot see a fallback
                # that only happens AT SCORING TIME -- keel_score_from_state raising,
                # or returning a non-finite/non-positive size (_keel_size_for_entry's
                # own two `except`/guard branches, above). Those ARE real "this trade
                # got sized at 1.0 because scoring blew up" events, and they are the
                # ones the owner most wants to hear about -- so page for them here too.
                # `_diag` is a short reason STRING on any fallback (see
                # _keel_size_for_entry's own docstring) or a diagnostics DICT on a real
                # score -- isinstance(_diag, str) is exactly "this was a fallback".
                # Dedupe lives on `leg_state` itself (once per ET calendar day, same
                # convention as _maybe_push_keel_fallback's state["keel_alerts"]) since
                # this function -- unlike step() -- has no access to the top-level
                # state dict. Same live+cloud-box gate as step()'s own push: the PC
                # runner scores KEEL too (import-only, no state directory), so without
                # this gate it would page a false "keel state unavailable" on its own.
                # Never for a shadow leg (cfg["shadow"] -- see _push_allowed).
                # WEBULL PUSH PLAN 10-07: the plain note through api/ntfy_push, at most once a
                # day per leg across this push and step()'s (_keel_fallback_push_once) -- every
                # reason here is a REAL fallback (this trade was just sized at 1.0).
                if isinstance(_diag, str) and _push_allowed(cfg, fetch):
                    alert = leg_state.setdefault("keel_alert", {})
                    _keel_fallback_push_once(leg_key, _diag, today, [alert], log=log)
                # KEEL ENTRY EXTRAS (logging only, MANAGER #76): computed AFTER keel_size and
                # final_size are fixed above, from the same arrays and entry bar; they ride
                # on the row only -- see _keel_entry_extras. Learned legs only.
                if keel_mode(keel_cfg) == KEEL_MODE_LEARNED:
                    keel_extras = _keel_entry_extras(keel_cfg, arrays, t.get("entry_bar"),
                                                     _diag, log=log,
                                                     feats=_ks_scratch.get("feats"),
                                                     rule_cfg=_ks_scratch.get("rule_cfg"))
            rec = recorded[key]
            rec["size"] = final_size
            rec["keel_size"] = keel_size
            events.append({
                "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
                "leg": leg_key, "event": "ENTRY", "side": t["side"],
                "ref_time": t["entry_time"], "ref_price": t["entry_px"],
                "shares": t["shares"],
                # a decide-at-close probe's tag, or a DIP leg's own note (decided at the prior
                # close, filled at the 09:30 open, when the engine first saw it); else blank
                "reason": t.get("probe_entry") or t.get("entry_note") or "",
                "bar_source": bar_source or "",
                "trade_id": tid,
                "size": final_size,
                "keel_size": keel_size,
                # DECISION BARS: the bar this entry was decided on (blank off NOISE)
                **_decision_cols(t, "entry", bar_source),
                # KEEL ENTRY EXTRAS: learned KEEL legs only (no keys at all elsewhere)
                **(keel_extras or {}),
            })
            lv = t.get("levels") if levels_on else None
            if lv:
                # the engine's initial stop and target -- see RESTING LEVELS / SIGNAL_COLS
                rec["stop_px"] = lv["stop_px"]
                rec["target_px"] = lv["target_px"]
                events[-1]["stop_px"] = lv["stop_px"]
                events[-1]["target_px"] = "" if lv["target_px"] is None else lv["target_px"]
        lv = t.get("levels") if levels_on else None
        if (lv and lv.get("be_armed_time") and t["still_open"] and not post_close
                and not rec.get("skipped") and not rec.get("seeded")
                and not rec.get("exit_emitted") and not rec.get("be_emitted")):
            # BREAKEVEN MOVED THE STOP (see RESTING LEVELS): armed at the close of the bar
            # starting be_armed_time, in force from the next bar. Once per trade.
            rec["be_emitted"] = lv["be_armed_time"]
            rec["stop_px"] = lv["be_stop_px"]
            target_px = rec.get("target_px", lv["target_px"])
            events.append({
                "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
                "leg": leg_key, "event": "LEVELS", "side": t["side"],
                "ref_time": lv["be_armed_time"], "ref_price": lv["be_stop_px"],
                "shares": t["shares"],
                "reason": _levels_reason(lv, (cfg or {}).get("timeframe")),
                "bar_source": bar_source or "",
                "trade_id": tid,
                "size": "", "keel_size": "",
                "stop_px": lv["be_stop_px"],
                "target_px": "" if target_px is None else target_px,
            })
        if (not t["still_open"]) and (not rec["exit_emitted"]):
            rec["exit_emitted"] = True
            rec["exit_time"] = t["exit_time"]
            rec["exit_px"] = t["exit_px"]
            # SIZE NEVER CHANGES AFTER ENTRY (design). A keel-scored leg reuses exactly
            # the size/keel_size this SAME trade's ENTRY stored on `rec` above -- never
            # a fresh KEEL score (the ledger/state may have moved on by exit time, and
            # re-scoring would let one trade's order size drift after the fact). A leg
            # with no "keel" block is completely unaffected: same t.get("size", 1.0)
            # this line has always read.
            if (cfg or {}).get("keel"):
                exit_size = rec.get("size", t.get("size", 1.0))
                exit_keel_size = rec.get("keel_size", "")
            else:
                exit_size = t.get("size", 1.0)
                exit_keel_size = ""
            events.append({
                "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
                "leg": leg_key, "event": "EXIT", "side": t["side"],
                "ref_time": t["exit_time"], "ref_price": t["exit_px"],
                "shares": t["shares"],
                "reason": ("strategy_exit" + (f"; {t['probe_exit']}" if t.get("probe_exit") else "")
                           + (f"; {t['exit_note']}" if t.get("exit_note") else "")
                           # a DIP exit fills at a 09:30 open, never at the close -- no
                           # eod_settle tag even when it is first seen after the bell
                           + ("; eod_settle" if post_close and not t.get("exit_note") else "")),
                "bar_source": bar_source or "",
                # the ENTRY's id, not one built from the exit bar -- see SIGNAL_COLS
                "trade_id": tid,
                # the same per-trade size as the ENTRY event -- see SIGNAL_COLS
                "size": exit_size,
                "keel_size": exit_keel_size,
                # DECISION BARS: the bar this exit was decided on (blank off NOISE)
                **_decision_cols(t, "exit", bar_source),
            })
    return events


# ── Replay ──────────────────────────────────────────────────────────────────────────────
def _session_minute_closes(day, tz_name=TZ, max_ticks=None):
    """Every 1-minute bar-close timestamp inside RTH for `day` (a session day) — the
    finest granularity any leg needs (ENGUQ_335 is 1m). `step()` itself skips the
    actual engine recompute for a 5m leg on the 4 out of 5 ticks where its own latest
    closed bar hasn't advanced, so ticking every minute here costs 5m legs nothing
    extra. `max_ticks` caps how many closes are returned (from the start of the
    session) — see replay()'s docstring."""
    tz = _zi(tz_name)
    d = market_calendar._coerce_date(day)
    start = _dt.datetime.combine(d, RTH_OPEN, tzinfo=tz)
    end = _dt.datetime.combine(d, RTH_CLOSE, tzinfo=tz)
    out = []
    t = start + _dt.timedelta(minutes=1)   # first CLOSE is one minute after open
    while t <= end:
        out.append(t)
        if max_ticks is not None and len(out) >= max_ticks:
            break
        t += _dt.timedelta(minutes=1)
    return out


def isolated_paths(legs=None, source_paths=None, root=None):
    """A throwaway paths dict for an OFFLINE run: a fresh temp home holding a COPY of the
    bar cache for every timeframe `legs` uses (copied from `source_paths`, default the
    live DEFAULT_PATHS) and an empty cloud_signal/ dir, so the run starts cold and every
    file it writes lands in the copy. The caller owns the folder (paths["home"]) --
    replay() removes the one it makes for itself; the CLI keeps its copy for inspection.

    WHY (2026-09-14, the second time). `python -m api.cloud_signal --replay 2026-09-03`
    ran replay(day) -> step(paths=None) -> DEFAULT_PATHS, straight into the live ledger
    the runner's parallel run appends to and api/qqq_exec.py consumes by row cursor. At
    00:55 ET it wrote a NOISE_304 SEED plus 2026-09-03 ENTRY/EXIT rows and left that
    day's 11:00 trade recorded as entered-but-still-open, so at 09:31 ET the LIVE engine
    emitted the EXIT of a trade from eleven days earlier and the shadow adapter consumed
    it (no lot happened to be open). 2026-09-09 was the same mistake by hand. A replay
    row's emitted_at is the real clock, so the adapter cannot tell it from a live
    signal: the only safe replay is one that cannot reach the live files unless someone
    asks for exactly that (--live-paths)."""
    legs = legs if legs is not None else CROWN_LEGS
    source_paths = source_paths or DEFAULT_PATHS
    paths = _paths(home=tempfile.mkdtemp(prefix="cloud_signal_replay_", dir=root))
    try:
        os.makedirs(paths["ohlc_dir"], exist_ok=True)
        for tf in sorted({cfg["timeframe"] for cfg in legs.values()}):
            src = _cache_path(tf, source_paths)
            if os.path.exists(src):
                # one read of a file the live writer only ever os.replace()s -- never torn
                shutil.copyfile(src, _cache_path(tf, paths))
    except BaseException:
        shutil.rmtree(paths["home"], ignore_errors=True)
        raise
    return paths


def replay(day, legs=None, paths=None, warmup_sessions=None, max_ticks=None):
    """Replay one cached session bar-by-bar (1-minute granularity), calling step() at
    each closed-bar boundary with fetch=False (fully offline — only ever reads the
    on-disk cache). Returns the events THIS call emitted. Replay the same day twice
    against one persistent store to see the idempotency guarantee: the second call's
    return is empty.

    `paths`: the store to replay INTO. The default (None) is a throwaway
    isolated_paths() copy, removed when the replay returns, so every default call starts
    cold -- and never the live DEFAULT_PATHS (see isolated_paths for the incident). Pass
    a paths dict you own to keep the ledger/state or rerun against it; pass DEFAULT_PATHS
    only when writing into the live ledger is genuinely the point.

    `warmup_sessions`: overrides every leg's warm-up window for this call only (does
    not mutate CROWN_LEGS/legs). `max_ticks`: replay only the first N 1-minute closes
    of the session instead of the full ~390. Both exist for
    tests/test_cloud_signal.py's speed budget — the rolling-window recompute-on-new-
    bar design costs real wall-clock time per bar (pandas datetime/tz parsing on the
    slice, then the engine call), and the production defaults (60 sessions, the full
    session) are unnecessarily slow for a unit test that is only checking the
    diff/idempotency mechanics, not strategy fidelity or full-day coverage. The CLI
    (`--replay`, used for the real report) always uses the production defaults.
    """
    legs = legs if legs is not None else CROWN_LEGS
    if warmup_sessions is not None:
        legs = {k: dict(v, warmup_sessions=warmup_sessions) for k, v in legs.items()}
    if not market_calendar.is_session(day):
        raise ValueError(f"{day} is not a session day (holiday or weekend)")
    own_scratch = paths is None
    if own_scratch:
        paths = isolated_paths(legs)
    try:
        ledger = []
        for now in _session_minute_closes(day, max_ticks=max_ticks):
            ledger.extend(step(now=now, legs=legs, paths=paths, fetch=False))
        return ledger
    finally:
        if own_scratch:
            shutil.rmtree(paths["home"], ignore_errors=True)


# ── NT-vs-QQQ comparison (diagnostic only — no assertion) ────────────────────────────────
def nt_comparison(day, fills_path=None):
    """Side-by-side NinjaTrader fills vs this session's cloud_signal ledger for `day`.
    Diagnostic only: prints how far QQQ-bar signals diverge from the NQ-bar signals
    NinjaTrader actually took. Returns the row list (also used by --replay's table)."""
    from api import nt_sync
    fills_path = fills_path or nt_sync.DEFAULT_FILLS
    d = market_calendar._coerce_date(day)
    day_str = str(d)
    fills = nt_sync.parse_fills(fills_path)
    trades = nt_sync.build_trades(fills)
    nt_rows = [t for t in trades if t["date"] == day_str]
    return nt_rows


def _fmt_ledger_table(events):
    lines = []
    header = f"{'leg':<14}{'event':<7}{'side':<7}{'ref_time':<30}{'ref_price':>10}{'shares':>8}"
    lines.append(header)
    lines.append("-" * len(header))
    for e in events:
        lines.append(f"{e['leg']:<14}{e['event']:<7}{e['side']:<7}{str(e['ref_time']):<30}"
                     f"{e['ref_price']:>10}{e['shares']:>8}")
    return "\n".join(lines)


def _fmt_nt_comparison_table(events, nt_rows):
    lines = []
    header = (f"{'leg/tag':<16}{'source':<8}{'event':<7}{'time (ET)':<20}{'price':>10}")
    lines.append(header)
    lines.append("-" * len(header))
    for e in events:
        lines.append(f"{e['leg']:<16}{'QQQ':<8}{e['event']:<7}{str(e['ref_time']):<20}{e['ref_price']:>10}")
    for t in nt_rows:
        lines.append(f"{t.get('signal') or '(untagged)':<16}{'NT':<8}{'ENTRY':<7}"
                     f"{t['date']+' '+t['entryTime']:<20}{t['entry']:>10}")
        if t.get("exitTime"):
            lines.append(f"{t.get('signal') or '(untagged)':<16}{'NT':<8}{'EXIT':<7}"
                         f"{t['date']+' '+t['exitTime']:<20}{t['exit']:>10}")
    if not nt_rows:
        lines.append("(no NinjaTrader fills tagged for this session)")
    return "\n".join(lines)


# ── Heartbeat ───────────────────────────────────────────────────────────────────────────
def _write_heartbeat(paths, ok=True, note="", cache_write_failed=False, health=None):
    """`cache_write_failed` (2026-09-14): set by a caller that saw step()'s `warnings`
    dict carry it -- the on-disk bar cache rename failed even after retries, but the
    step still ran off the freshly fetched bars in memory (see step()'s docstring). It
    is recorded here (only when True, keeping the common heartbeat's shape unchanged)
    as a visible warning alongside ok=True -- never as a reason to flip ok to False,
    which is exactly the behaviour that used to make api/qqq_exec.py's engine-mode
    feed check block new entries over a transient disk/lock hiccup instead of a real
    outage.

    The rename retries the same transient-lock budget as every other writer here
    (qp._replace_with_retry): api/qqq_exec.py's `_check_feed_engine` opens this exact
    file every tick, so a reader can hold it for the same few milliseconds the OHLC
    cache readers do. On final failure this raises (see _write_state for why a writer
    in this module treats an exhausted retry as fatal rather than silently moving on)
    -- callers already wrap their heartbeat writes in a try/except for exactly this.

    `health` (2026-10-05, FEED HEALTH): the in-session live step's bar freshness, merged in
    as extra keys -- newest_closed_bar_et, newest_closed_bar_epoch, bar_age_s, bars_due,
    bars_missing, stalled, verdict, bar_source, yf_fallback_streak (see _feed_health) -- the
    5m's figures -- plus stalled_timeframes and feed_by_timeframe for every live timeframe
    (2026-10-09, ENGU-Q's 1m: EVERY LIVE TIMEFRAME in the FEED HEALTH block).
    `ok` keeps its old meaning (the step RAN): read `verdict` / `stalled` for "bars are
    arriving"."""
    os.makedirs(paths["state_dir"], exist_ok=True)
    hb = {"ts": _dt.datetime.now(tz=_zi(TZ)).isoformat(), "ok": ok, "note": note}
    if cache_write_failed:
        hb["cache_write_failed"] = True
    if health:
        for k, v in health.items():
            if k not in hb:
                hb[k] = v
    tmp = paths["heartbeat_path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hb, f, indent=2)
    if not qp._replace_with_retry(tmp, paths["heartbeat_path"], log=print,
                                  what="[cloud-signal] heartbeat.json"):
        raise OSError(f"cloud_signal: could not replace {paths['heartbeat_path']} after retries")


# ── CLI ─────────────────────────────────────────────────────────────────────────────────
# The runner thread stamps its heartbeat every 30s in session and every 60s outside it, so
# three of the slow beats without one is the least that can mean "no live writer".
LIVE_WRITER_FRESH_SEC = 180.0


def _live_writer_age_sec(paths):
    """Seconds since a live writer (the runner thread, --loop, --once) last stamped the
    heartbeat under `paths`; None when there is no heartbeat file at all. A heartbeat that
    exists but cannot be read reads as 0.0 -- "can't tell" must refuse a live write, not
    wave it through."""
    hb = paths["heartbeat_path"]
    if not os.path.exists(hb):
        return None
    try:
        with open(hb, encoding="utf-8") as f:
            ts = _dt.datetime.fromisoformat(str(json.load(f).get("ts")))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_zi(TZ))
        return (_dt.datetime.now(tz=_zi(TZ)) - ts).total_seconds()
    except Exception:
        return 0.0


def _refuse_beside_live_writer(paths, label):
    """Shared refusal check for cmd_once/cmd_loop (WEBULL_PAPER_TODO.md item 2): a
    hand-run step beside a fresh live writer (the runner's cloud_signal_thread, or
    another --loop/--once) becomes a SECOND writer of state.json/signals.csv, which can
    double-emit an ENTRY or drop a trade's bookkeeping so its ENTRY re-fires after its
    EXIT (see WEBULL_PAPER_TODO.md item 2's "What can go wrong" section). Reuses the
    exact same heartbeat freshness test --live-paths already uses (_live_writer_age_sec /
    LIVE_WRITER_FRESH_SEC), so "fresh" means the same thing everywhere in this file.

    Returns 2 (the process exit code to use) and prints a message naming the
    heartbeat's age and path when a writer stamped it within LIVE_WRITER_FRESH_SEC;
    returns None (proceed as before) when the heartbeat is stale or absent.

    NEVER call this from cloud_signal_thread: a stale heartbeat left by an old --loop
    (or a runner restart) must never stop the runner's own live parallel run -- see
    that function's own docstring."""
    age = _live_writer_age_sec(paths)
    if age is None or age >= LIVE_WRITER_FRESH_SEC:
        return None
    print(f"cloud_signal {label}: REFUSED -- a live writer stamped {paths['heartbeat_path']} "
          f"{age:.0f}s ago (fresh threshold {LIVE_WRITER_FRESH_SEC:.0f}s). Running {label} "
          f"beside it would give the live signal record a second writer -- stop the runner's "
          f"cloud_signal thread (or the other --loop/--once) first, or wait for the heartbeat "
          f"to go stale.")
    return 2


def cmd_replay(day, live_paths=False):
    """--replay. Isolated by default: the session replays in an isolated_paths() copy that
    is kept and named on screen, so its state.json/signals.csv can be read afterwards,
    and the live ledger is never opened for writing.

    --live-paths is the explicit opt-in to replay INTO DEFAULT_PATHS, and it is refused
    while a live writer's heartbeat is fresh: the runner thread rewrites state.json every
    30s (two writers lose each other's records and re-emit), and api/qqq_exec.py acts on
    any new ENTRY/EXIT row whose emitted_at looks recent -- which every replay row's does.
    Stop the thread first, and mind the adapter. Returns a process exit code."""
    if live_paths:
        paths = DEFAULT_PATHS
        age = _live_writer_age_sec(paths)
        if age is not None and age < LIVE_WRITER_FRESH_SEC:
            print(f"cloud_signal replay {day}: REFUSED --live-paths -- a live writer stamped "
                  f"{paths['heartbeat_path']} {age:.0f}s ago. Stop the runner's cloud_signal "
                  f"thread (or --loop) first, or drop --live-paths to replay in isolation.")
            return 2
        print(f"cloud_signal replay {day}: --live-paths -- writing into the LIVE ledger and "
              f"state in {paths['state_dir']}")
    else:
        paths = isolated_paths()
        print(f"cloud_signal replay {day}: isolated copy in {paths['home']} "
              f"(live ledger untouched; delete the folder when done)")
    events = replay(day, paths=paths)
    print(f"cloud_signal replay {day} — {len(events)} new event(s) this call")
    print(_fmt_ledger_table(events))
    nt_rows = nt_comparison(day)
    print(f"\nNT (NinjaTrader NQ) vs QQQ cloud_signal — session {day}")
    print(_fmt_nt_comparison_table(events, nt_rows))
    return 0


def cmd_once():
    """One live step() and exit. Refused (returns 2) while a live writer's heartbeat is
    fresh -- see _refuse_beside_live_writer -- so this can never become a second writer
    of the live signal record beside the runner's own cloud_signal_thread or another
    --loop/--once. Also refused (returns 2) when this host is excluded by config.json's
    serving_hosts -- see _serving_hosts_ok's docstring: that gate protects
    cloud_signal_thread, but a hand-run `--once` on an excluded host bypassed it (MINOR
    review fix, 2026-09-26). Returns the process exit code; main() passes it to
    sys.exit()."""
    paths = DEFAULT_PATHS
    hosts_ok, hosts_reason = _serving_hosts_ok()
    if not hosts_ok:
        print(f"cloud_signal --once: REFUSED -- {hosts_reason}")
        return 2
    rc = _refuse_beside_live_writer(paths, "--once")
    if rc:
        return rc
    log_history_windows(paths=paths)
    warnings = {}
    events = step(fetch=True, paths=paths, warnings=warnings)
    cache_failed = bool(warnings.get("cache_write_failed"))
    note = f"{len(events)} event(s)" + (" (cache_write_failed)" if cache_failed else "")
    _write_heartbeat(paths, ok=True, note=note, cache_write_failed=cache_failed)
    print(f"cloud_signal --once: {len(events)} new event(s)")
    print(_fmt_ledger_table(events))
    return 0


THREAD_STEP_SEC = 30.0   # see cloud_signal_thread


def _host_id():
    """This host's identity -- the SAME rule as api.qqq_exec._lease_host_id, duplicated
    (not imported) because that module already imports THIS one (_build_keel_status), so
    the reverse import would be circular. EDGELOG_HOST_ID overrides; else the OS
    hostname."""
    override = os.environ.get("EDGELOG_HOST_ID")
    if override and override.strip():
        return override.strip()
    try:
        import platform as _platform
        return _platform.node() or "unknown-host"
    except Exception:
        return "unknown-host"


def _qqq_exec_config_path():
    """Path to api/qqq_exec.py's config.json -- the book's own config file. Built the
    SAME way that module builds its own CONFIG_PATH (EDGELOG_QQQ_EXEC_DIR, else
    <EDGELOG_HOME>/qqq_exec), duplicated rather than imported for the same circular-
    import reason as _host_id above."""
    out_dir = os.environ.get("EDGELOG_QQQ_EXEC_DIR", os.path.join(edgelog_home(), "qqq_exec"))
    return os.path.join(out_dir, "config.json")


def _serving_hosts_ok(log=print):
    """(ok, reason) -- SERVING_HOSTS GATE (2026-09-26, "the PC does not run the signal
    engine either"): reads the SAME "serving_hosts" list from the SAME config.json as
    api.qqq_exec._serving_hosts_ok (see that function's docstring for the full why this
    is a static allow-list, never a Firestore lease). One list in one file governs both
    halves of the book, so there is only ever one place to edit.

    Missing config.json, missing key, or a value that is not a non-empty list --
    today's behaviour, this host may run the engine exactly as before. A read/parse
    error is treated the same way (fail-open) -- never raises, never blocks the engine
    over a transient file glitch. MINOR review fix (2026-09-26): a missing file is the
    common, silent case (nobody has added the key yet), but a file that EXISTS and
    fails to parse is a real config problem masquerading as "every host may serve" --
    logged as a WARNING, distinct from the missing-file case, so it does not read like
    routine startup noise."""
    path = _qqq_exec_config_path()
    if not os.path.exists(path):
        return True, None
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        log(f"[cloud-signal] WARNING: {path} exists but could not be read/parsed "
            f"({type(e).__name__}: {e}) -- serving_hosts gate fails OPEN (proceeding, "
            "today's behaviour); fix the file to restore the gate")
        return True, None
    hosts = (cfg or {}).get("serving_hosts")
    if hosts is None:
        return True, None
    if not isinstance(hosts, list) or not hosts:
        log(f"[cloud-signal] {path}'s serving_hosts={hosts!r} is not a non-empty list -- "
            "ignoring (every host may still run the engine, today's behaviour)")
        return True, None
    allowed = {str(h).strip() for h in hosts if str(h).strip()}
    me = _host_id()
    if me in allowed:
        return True, None
    return False, (f"this host {me!r} is not in {path}'s serving_hosts {sorted(allowed)} "
                   "-- refusing to run the signal engine")


# ── Shadow run (OWNER DECISION 2026-09-28) -- see the module docstring's SHADOW LEGS ─────
# One shadow failure log line per this many seconds at most (the rest are counted and
# reported with the next line) -- a broken shadow leg must not flood the runner log either.
SHADOW_ERROR_LOG_EVERY_SEC = 600.0
_SHADOW_ERR = {"last_logged": 0.0, "suppressed": 0}
# NOISE FORWARD LOG (2026-09-28, Custom ML's pre-registered forward test,
# docs/PREREG_noise_shadow_forward_2026-09-28.md): run_shadow_step writes one decision-time
# row per NOISE signal into <shadow store>/noise_forward_log.csv -- see api/noise_forward.py.
# False turns it off; the live and shadow legs are identical either way.
NOISE_FORWARD_LOG = True


def shadow_only_timeframes(live_legs=None, shadow_legs=None):
    """The timeframes a shadow leg reads that NO live leg does, sorted -- today [] (every
    shadow leg is 5m; it was ["1m"] while ENGUQ_335 was a shadow leg, 2026-09-28..10-09 --
    the live step fetches 1m again now that ENGU-Q is live). The live step already fetches
    every live timeframe once per fetch tick; run_shadow_step fetches only these, so each
    timeframe is fetched exactly once per tick (Webull rate-limits with 429)."""
    live_legs = CROWN_LEGS if live_legs is None else live_legs
    shadow_legs = SHADOW_LEGS if shadow_legs is None else shadow_legs
    live_tfs = {cfg["timeframe"] for cfg in live_legs.values()}
    return sorted({cfg["timeframe"] for cfg in shadow_legs.values()} - live_tfs)


def run_shadow_step(now=None, fetch=True, live_legs=None, shadow_legs=None, live_paths=None,
                    log=print, post_close=False):
    """One tick of the SHADOW LEGS, run AFTER the live step on the same tick. Returns the
    shadow events this call emitted (written to shadow_paths()' ledger only).

      1. On a fetch tick, fetch_and_merge each shadow_only_timeframes() timeframe into the
         LIVE bar cache -- the only network this ever does. A timeframe a live leg uses is
         never fetched here: the live step fetched it moments ago on this same tick.
      2. step() over `shadow_legs` with fetch=False into the shadow store: the same engine,
         the same on-disk bars the live step just refreshed, the same QQQ_1d.csv. fetch=False
         means no network, no daily-cache refresh and no ntfy push (and every shadow cfg
         carries "shadow": True, the second guard -- see _push_allowed).
      3. NOISE FORWARD LOG (NOISE_FORWARD_LOG): api/noise_forward.forward_log_tick writes
         any NOISE signal row now due into the shadow store. Never raises.
      4. Stamp the shadow store's OWN heartbeat -- never the live heartbeat.

    `post_close`: the EOD SETTLE step (_eod_settle_shadow) -- passed to step(), so no shadow
    ENTRY is emitted after the bell.

    The live store is only ever READ here (its state.json's bar_source, to label the
    shadow rows with the feed that priced them) -- never written. May raise: the thread
    calls it through _shadow_tick, which never does."""
    shadow_legs = SHADOW_LEGS if shadow_legs is None else shadow_legs
    if not shadow_legs:
        return []
    live_legs = CROWN_LEGS if live_legs is None else live_legs
    live_paths = live_paths or DEFAULT_PATHS
    spaths = shadow_paths(live_paths)
    sources = {tf: info.get("source") for tf, info in (read_bar_source(live_paths) or {}).items()
               if isinstance(info, dict) and info.get("source")}
    notes = []
    if fetch:
        for tf in shadow_only_timeframes(live_legs, shadow_legs):
            try:
                _df, src, cache_ok = fetch_and_merge(tf, live_paths, log=log)
                sources[tf] = src
                if not cache_ok:
                    notes.append(f"{tf} cache_write_failed")
            except Exception as e:     # the shadow step still runs off the cache on disk
                notes.append(f"{tf} fetch failed: {type(e).__name__}: {e}")
    events = step(now=now, legs=shadow_legs, paths=spaths, fetch=False, bar_sources=sources,
                  post_close=post_close)
    if NOISE_FORWARD_LOG:
        try:
            from api import noise_forward as _nf
            n_fwd = _nf.forward_log_tick(now, live_paths, spaths, live_legs, shadow_legs, log=log)
        except Exception as e:           # an import failure; forward_log_tick itself never raises
            n_fwd = 0
            notes.append(f"NOISE forward log unavailable: {type(e).__name__}: {e}")
        if n_fwd:
            notes.append(f"{n_fwd} NOISE forward-log row(s)")
    _write_heartbeat(spaths, ok=True,
                     note=f"{len(events)} shadow event(s)" + ("; " + "; ".join(notes) if notes else ""))
    return events


def _shadow_tick(now, fetch, log=print):
    """cloud_signal_thread's ONE call into the shadow legs: run_shadow_step, NEVER raising
    into the live loop. A failure stamps the shadow heartbeat ok=false (best-effort) and
    logs at most once per SHADOW_ERROR_LOG_EVERY_SEC, with how many were held back."""
    try:
        events = run_shadow_step(now=now, fetch=fetch, log=log)
        for e in events:
            log(f"[cloud-signal] SHADOW {e['event']} {e['leg']} {e.get('side','')} "
                f"@ {e.get('ref_price','')} ({e.get('ref_time','')}) size={e.get('size','')}")
        return events
    except Exception as e:
        try:
            _write_heartbeat(shadow_paths(), ok=False, note=f"{type(e).__name__}: {e}")
        except Exception:
            pass
        now_wall = _time.time()
        if now_wall - _SHADOW_ERR["last_logged"] >= SHADOW_ERROR_LOG_EVERY_SEC:
            held = _SHADOW_ERR["suppressed"]
            _SHADOW_ERR["last_logged"], _SHADOW_ERR["suppressed"] = now_wall, 0
            log(f"[cloud-signal] shadow step failed (live legs unaffected): "
                f"{type(e).__name__}: {e}" + (f" [+{held} more since the last line]" if held else ""))
        else:
            _SHADOW_ERR["suppressed"] += 1
        return []


# ── EOD SETTLE (2026-09-28) ─────────────────────────────────────────────────────────────
# The thread below steps only while RTH_OPEN <= now <= RTH_CLOSE, and a bar is usable only
# CLOSE_GRACE_SECONDS after it closes -- so the session's LAST bar (5m 15:55, 1m 15:59)
# first became usable at 16:00:05, when the thread had already stopped stepping. The
# day's end-of-day exits were then emitted around 09:35 the NEXT session with an old
# ref_time (box cloud_signal.log, 09-25: "EXIT NOISE_382 long @ 744.5 (15:55)" at the
# next open), which api/qqq_exec.py logged as exit_no_lot.
#
# Now, on a session day, the thread runs ONE more kind of step after the close: from
# close + EOD_SETTLE_FIRST_TRY_SEC, every EOD_SETTLE_RETRY_SEC, until close +
# EOD_SETTLE_WINDOW_SEC, a plain step(post_close=True) with fetch -- never the stream
# wrapper. It stops once every cfg["eod_flat"] leg's newest usable bar is the session's
# last bar (state["eod_settled"][date]); past the window it gives up with one log line
# and the next morning emits as before. With post_close set no ENTRY is ever emitted
# (_diff_leg), and run_leg_trades' EOD FLAT rule closes the eod_flat legs' trades at that
# last bar -- the backtest's own end-of-day fill. SIGNALS ONLY for every leg that is flat
# at the close: api/qqq_exec.py never sends a broker order for these rows (its after-close
# guard; no lot -> nothing to close). The one exception is a lot qqq_exec HOLDS OVERNIGHT
# (ENGU-Q since 2026-10-09, owner GO, MANAGER #106 -- qqq_exec HOLD_OVERNIGHT_LEGS): a settle
# EXIT for its trade (the exit of an emitted ENTRY, tagged eod_settle) keeps the lot and is
# sold at market at the next open (qqq_exec _defer_held_close), never at the row's price.
# Only the eod_flat legs' last bars are waited for: an ENGU-Q exit on its 1m 15:59 bar that
# misses the settle comes with the next session's first step instead and is sold the same
# way, at market at a price from that day.
#
# KNOWN LIMIT (accepted, 2026-09-28 review): a settle EXIT's price is fixed by the FIRST
# fetch that holds the last bar, and _diff_leg never re-emits an exit once emitted -- so
# if that REST bar is later revised (09-28: stream-vs-REST close differences up to 0.005
# on just-closed bars), backtest_exit_px keeps the provisional value. It feeds signals and
# parity only; no order depends on it (a held lot's settle EXIT is sold at market at the
# next open, never at this price -- see SIGNALS ONLY above).
#
# A step() that RAISES inside the window is caught here, never by the thread's own
# except-branch: the heartbeat stays ok=True with an "eod settle failed" note (nothing
# signal-driven can happen after the bell, and an ok=False heartbeat would make
# api/qqq_exec.py's feed check call the engine stalled and page while a lot is open), and
# the last try inside the window still writes the GAVE UP line.
EOD_SETTLE_FIRST_TRY_SEC = 30.0
EOD_SETTLE_RETRY_SEC = 30.0
EOD_SETTLE_WINDOW_SEC = 300.0
EOD_SETTLE_POLL_SEC = 5.0


def _eod_settle_close(now):
    """Today's session close when `now` is inside its settle window (close, close +
    EOD_SETTLE_WINDOW_SEC], else None. Never raises."""
    close_dt = _session_close_dt(now)
    if close_dt is None:
        return None
    et = now.astimezone(_zi(TZ)) if now.tzinfo is not None else now.replace(tzinfo=_zi(TZ))
    if close_dt < et <= close_dt + _dt.timedelta(seconds=EOD_SETTLE_WINDOW_SEC):
        return close_dt
    return None


def _eod_settle_shadow(now, log=print):
    """The shadow legs' settle step, when this build has them (run_shadow_step, the
    wb-shadow work) AND that function takes `post_close` -- without it, stepping the
    shadow legs after the bell could emit an ENTRY, so they are left alone and settle the
    next morning as before. Never raises; returns the shadow events."""
    fn = globals().get("run_shadow_step")
    if not callable(fn):
        return []
    try:
        accepts = "post_close" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        accepts = False
    if not accepts:
        return []
    try:
        return fn(now=now, fetch=True, post_close=True, log=log) or []
    except Exception as e:
        log(f"[cloud-signal] eod settle: shadow step failed (live legs unaffected): "
            f"{type(e).__name__}: {e}")
        return []


def _eod_settle_tick(now, close_dt, mem, paths=None, log=print):
    """One pass of the EOD SETTLE window (see the block above). `mem` is the thread's own
    {date: {"last_try", "done", "gave_up"}}. Writes the heartbeat on every pass (the
    engine stays fresh for api/qqq_exec.py through the window). Returns the live events
    emitted. A step() that raises is logged and noted in an ok=True heartbeat, not
    re-raised (see the EOD SETTLE block above)."""
    paths = paths or DEFAULT_PATHS
    day = close_dt.date().isoformat()
    m = mem.setdefault(day, {"last_try": None, "done": False, "gave_up": False})
    if m["done"] or m["gave_up"]:
        _write_heartbeat(paths, ok=True, note="eod settle: " + ("settled" if m["done"] else "gave up"))
        return []
    if now < close_dt + _dt.timedelta(seconds=EOD_SETTLE_FIRST_TRY_SEC):
        _write_heartbeat(paths, ok=True, note="eod settle: waiting for the last bar")
        return []
    if m["last_try"] is not None and \
            (now - m["last_try"]).total_seconds() < EOD_SETTLE_RETRY_SEC:
        _write_heartbeat(paths, ok=True, note="eod settle: waiting")
        return []
    if (_load_state(paths).get("eod_settled") or {}).get(day):
        m["done"] = True                  # a restart inside the window: already settled
        _write_heartbeat(paths, ok=True, note="eod settle: settled")
        return []
    m["last_try"] = now
    warnings = {}
    last_try_in_window = (now + _dt.timedelta(seconds=EOD_SETTLE_RETRY_SEC)
                          > close_dt + _dt.timedelta(seconds=EOD_SETTLE_WINDOW_SEC))
    try:
        events = step(now=now, fetch=True, paths=paths, warnings=warnings, post_close=True)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log(f"[cloud-signal] eod settle step failed: {err}")
        if last_try_in_window:
            m["gave_up"] = True
            log(f"[cloud-signal] eod settle {day}: GAVE UP -- the last try inside the window "
                f"failed ({err}); the next session's first step emits these exits")
            _note_eod_gave_up(paths, day, close_dt, now, f"the last try failed ({err})", log=log)
        try:
            _write_heartbeat(paths, ok=True, note=f"eod settle failed: {err}"[:300])
        except Exception:
            pass
        return []
    shadow = _eod_settle_shadow(now, log=log)
    settled = bool(warnings.get("eod_settled"))
    cache_failed = bool(warnings.get("cache_write_failed"))
    note = (f"eod settle: {len(events)} event(s)" + (" (settled)" if settled else "")
            + (f", {len(shadow)} shadow" if shadow else "")
            + (" (cache_write_failed)" if cache_failed else ""))
    _write_heartbeat(paths, ok=True, note=note, cache_write_failed=cache_failed)
    for e in events:
        log(f"[cloud-signal] {e['event']} {e['leg']} {e.get('side','')} "
            f"@ {e.get('ref_price','')} ({e.get('ref_time','')}) {e.get('reason','')}")
    if settled:
        m["done"] = True
        log(f"[cloud-signal] eod settle {day}: every flat-at-close leg has its last bar "
            f"({warnings.get('eod_bars')}) -- {len(events)} event(s)")
    elif last_try_in_window:
        m["gave_up"] = True
        log(f"[cloud-signal] eod settle {day}: GAVE UP -- the last bar never arrived "
            f"({warnings.get('eod_bars')}); the next session's first step emits these exits")
        _note_eod_gave_up(paths, day, close_dt, now, "the last bar never arrived", log=log)
    return events


def _note_eod_gave_up(paths, day, close_dt, now, why, log=print):
    """EOD SETTLE GAVE UP (sweep 2026-10-05, finding 30): it used to be one log line, while
    the day's end-of-day exits silently moved to the next morning with an old ref_time.
    Now, once per day (state["eod_gave_up"][day], so a restart inside the window cannot
    record twice): a record in state.json -- api/qqq_exec.py turns it into a board event --
    and one log line. NO PUSH from here: ONE ALERTER PER PROBLEM (api/ntfy_push) -- "today's
    close was not settled" is pushed only by tools/webull_freshness.py's eod_settled check
    (box timer, from 16:10 ET), which names this record's `why`; it also covers an engine
    that was down through the window and so could not record anything. Never raises."""
    first = True
    try:
        state = _load_state(paths)
        rec = state.setdefault("eod_gave_up", {})
        first = day not in rec
        if first:
            rec[day] = {"at": now.isoformat(), "why": why}
            for old in sorted(rec)[:-10]:               # a short history is plenty
                rec.pop(old, None)
            _write_state(state, paths)
    except Exception as e:
        log(f"[cloud-signal] eod settle: could not record the give-up ({type(e).__name__}: {e})")
    if not first:
        return
    try:
        last_bar = close_dt - _dt.timedelta(seconds=TIMEFRAME_SECONDS["5m"])
        log(f"[cloud-signal] eod settle {day}: last bar {last_bar.strftime('%H:%M')} ET did "
            f"not arrive by {now.strftime('%H:%M')} ET ({why}) on {_this_host_id()} -- the "
            f"exits are written at the next session's first step, stamped {day} (recorded "
            f"for the board; tools/webull_freshness.py pushes it)")
    except Exception as e:
        log(f"[cloud-signal] eod settle: give-up log line failed ({type(e).__name__}: {e})")


# ── FEED HEALTH (2026-10-05, sweep findings 6 + 15) ──────────────────────────────────────
# The heartbeat used to say ok=True every tick whether or not a new bar had arrived, so a
# frozen Webull tail (or Webull and yfinance both empty) produced no ENTRY and no EXIT while
# everything looked healthy, and a fall-back to yfinance was a log line only. Now every
# in-session live step reports, per timeframe (bar_health), the newest CLOSED bar, its age,
# how many of today's bars should have closed (bars_due) and how many of those are missing
# (bars_missing), and a STALLED verdict when no new bar has closed for two bars + 60 s
# (5m: 660 s) after one was due. The heartbeat carries the live 5m figures (_feed_health).
#
# `ok` KEEPS ITS MEANING ("the step ran without an error"). api/qqq_exec.py's
# _check_feed_engine reads ok=false as a stalled ENGINE: it blocks every new entry, counts
# the minute as feed downtime for readiness and, with a lot open, pages SIGNAL STALL. A
# frozen bar tail already produces no entry by itself, and a misjudged stall (a calendar or
# half-day edge) must not block real entries -- so the verdict is reported in `verdict` /
# `stalled` beside `ok`, and the engine pushes it itself:
#   * one HIGH push per stall episode ("QQQ book: prices stopped"), and one low "QQQ book: OK"
#     back-to-normal when bars arrive again;
#   * one HIGH push when the live 5m bars came from yfinance for 3+ fetches in a row ("QQQ
#     book: backup prices"; HIGH "QQQ book: approve Webull login" when Webull's last error
#     is the token waiting for approval), and one low "QQQ book: OK" when Webull bars are back.
#   All in the plain format through _engine_note / _engine_note_clear (ntfy_push.plain +
#   dedupe); the developer detail (bars missing, source, Webull error) goes to the log.
# Episodes live in <state_dir>/feed_alerts.json (survives a restart, no repeat page). Only
# the cloud box pushes (_engine_push), like the KEEL push. A yfinance streak, like a stall
# episode, ends quietly at the day change (no carry-over page, no next-morning "back" push).
#
# ONE PAGER PER EPISODE: tools/webull_freshness.py (box timer, every 2 min) checks the same
# two problems (its bar_age and bar_source checks). It reads these heartbeat fields: while
# a fresh heartbeat carries `stalled` (bar_age) or yf_fallback_streak (bar_source), its
# episode opens QUIET (tracked on its status, not pushed) -- this engine is the pager. With
# a stale heartbeat, or an engine older than these fields, it pages them itself.
#
# EVERY LIVE TIMEFRAME (2026-10-09, review of ENGU-Q's return to the book). Both alerts used
# to read the 5m figures only -- fine while every live leg was 5m (2026-09-28..10-09), but
# ENGU-Q trades on 1m bars, fetched second on each tick, so a 1m fetch that came back empty
# (a 429) or a frozen 1m tail left it on late or no bars with nothing paged. Now:
#   * a stall pages for ANY live timeframe: the 5m on its own verdict, as before; another one
#     (1m) once it has been silent for the 5m's own limit (660 s, `silent_s`), so a 1m tail
#     running 2-3 bars behind -- yfinance's 30-90 s lag -- never flaps a page;
#   * the yfinance streak counts a fetch tick on which ANY live timeframe came from yfinance;
#   * the heartbeat keeps its top-level 5m figures (tools/webull_freshness.py's bar_age reads
#     them as 5m) and adds stalled_timeframes and feed_by_timeframe {tf: figures + source}.
FEED_STALL_GRACE_BARS = 2
FEED_STALL_EXTRA_SEC = 60.0
FEED_YF_PUSH_FETCHES = 3
FEED_PRIMARY_TF = "5m"
FEED_ALERTS_FILE = "feed_alerts.json"


def _feed_stall_limit_sec(tf):
    return FEED_STALL_GRACE_BARS * TIMEFRAME_SECONDS[tf] + FEED_STALL_EXTRA_SEC


def bar_health(epoch_df, now, tf):
    """Freshness of one timeframe's CLOSED bars at `now` (pure, no I/O):
      newest_closed_bar_et     the newest closed bar's START, ET ISO (the ledger's ref_time)
      newest_closed_bar_epoch  the same as an epoch
      bar_age_s                seconds since that bar CLOSED
      bars_due                 today's session bars that have closed by now (none off-session)
      bars_missing             how many of those are not in the frame
      stalled                  in session, at least one bar due, and nothing new closed for
                               two bars + 60 s (5m: 660 s; before the first bar of the day the
                               clock starts at the open, so 09:41 at the earliest)
      silent_s                 the seconds that stall clock has run (None until a bar is due)
                               -- _feed_stall_pages reads it for a non-5m timeframe"""
    sec = TIMEFRAME_SECONDS[tf]
    et = now.astimezone(_zi(TZ)) if now.tzinfo is not None else now.replace(tzinfo=_zi(TZ))
    now_e = et.timestamp()
    out = {"timeframe": tf, "newest_closed_bar_et": None, "newest_closed_bar_epoch": None,
           "bar_age_s": None, "bars_due": 0, "bars_missing": 0, "stalled": False,
           "silent_s": None}
    cutoff = _closed_cutoff_epoch(et, tf)
    usable = None
    newest = None
    if epoch_df is not None and len(epoch_df):
        t = epoch_df["time"]
        usable = t[t <= cutoff]
        if len(usable):
            newest = int(usable.max())
    if newest is not None:
        out["newest_closed_bar_epoch"] = newest
        out["newest_closed_bar_et"] = _dt.datetime.fromtimestamp(newest, tz=_zi(TZ)).isoformat()
        out["bar_age_s"] = round(now_e - (newest + sec), 1)
    close_dt = _session_close_dt(et)
    if close_dt is None:
        return out
    open_dt = et.replace(hour=RTH_OPEN.hour, minute=RTH_OPEN.minute, second=0, microsecond=0)
    open_e = int(open_dt.timestamp())
    hi = min(cutoff, int(close_dt.timestamp()) - sec)
    if hi >= open_e:
        due = (hi - open_e) // sec + 1
        present = 0
        if usable is not None and len(usable):
            vals = usable[(usable >= open_e) & (usable <= hi)].unique()
            present = int(sum(1 for v in vals if (int(v) - open_e) % sec == 0))
        out["bars_due"] = int(due)
        out["bars_missing"] = int(max(0, due - present))
    if open_dt <= et <= close_dt and out["bars_due"] >= 1:
        ref = max((newest + sec) if newest is not None else 0, open_e)
        out["silent_s"] = round(now_e - ref, 1)
        out["stalled"] = (now_e - ref) > _feed_stall_limit_sec(tf)
    return out


def _feed_alerts_path(paths):
    return os.path.join(paths["state_dir"], FEED_ALERTS_FILE)


def _load_feed_alerts(paths):
    try:
        with open(_feed_alerts_path(paths), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_feed_alerts(paths, mem, log=print):
    try:
        os.makedirs(paths["state_dir"], exist_ok=True)
        p = _feed_alerts_path(paths)
        tmp = f"{p}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=1)
        if not qp._replace_with_retry(tmp, p, log=log, what="[cloud-signal] feed_alerts.json"):
            log("[cloud-signal] feed_alerts.json not saved (a repeat push is possible)")
    except Exception as e:
        log(f"[cloud-signal] feed_alerts.json not saved ({type(e).__name__}: {e})")


def _hhmm_of(iso):
    try:
        return _dt.datetime.fromisoformat(str(iso)).astimezone(_zi(TZ)).strftime("%H:%M")
    except Exception:
        return "none"


def _feed_stall_pages(x, primary):
    """Whether timeframe health `x` is in a stall that pages (EVERY LIVE TIMEFRAME in the FEED
    HEALTH block): the primary (5m) timeframe on its own verdict, as before; any other live
    timeframe on its verdict AND only once it has been silent for the primary's own limit
    (660 s), so a 1m tail a few bars behind never flaps a page. Never raises."""
    try:
        if not x.get("stalled"):
            return False
        if x is primary:
            return True
        return float(x.get("silent_s")) > _feed_stall_limit_sec(
            primary.get("timeframe") or FEED_PRIMARY_TF)
    except Exception:
        return False


def _feed_health(now, warnings, paths, log=print):
    """The in-session heartbeat's FEED HEALTH fields from step()'s warnings["bar_health"],
    plus the one-push-per-episode alerts (see the FEED HEALTH block). Never raises: a
    broken check returns {} and the heartbeat is written as before.

    Runs on the engine thread before the heartbeat write and the next step: the repeat rule
    and feed_alerts.json stay synchronous, but the network send goes to a daemon thread
    (_engine_push_background, FEED_PUSH_BACKGROUND) so a slow ntfy never delays either."""
    push = _engine_push_background if FEED_PUSH_BACKGROUND else None
    try:
        bh = (warnings or {}).get("bar_health") or {}
        h = bh.get(FEED_PRIMARY_TF) or (bh[sorted(bh)[0]] if bh else None)
        if not h or h.get("error"):
            return {"verdict": "unknown"} if h else {}
        tf = h.get("timeframe") or FEED_PRIMARY_TF
        fields = {k: h.get(k) for k in ("newest_closed_bar_et", "newest_closed_bar_epoch",
                                         "bar_age_s", "bars_due", "bars_missing", "stalled")}
        fields["bar_timeframe"] = tf
        # EVERY LIVE TIMEFRAME (2026-10-09 -- see the FEED HEALTH block): the 5m first, then
        # every other timeframe a live leg reads (1m for ENGU-Q); the top-level figures above
        # stay the 5m's
        watched = [h] + [bh[k] for k in sorted(bh) if bh[k] is not h
                         and isinstance(bh[k], dict) and not bh[k].get("error")]
        paging = [x for x in watched if _feed_stall_pages(x, h)]
        fields["stalled_timeframes"] = [x.get("timeframe") for x in paging]
        fields["feed_by_timeframe"] = {
            str(x.get("timeframe")): {k: x.get(k) for k in (
                "newest_closed_bar_epoch", "bar_age_s", "bars_due", "bars_missing", "stalled",
                "source")} for x in watched}
        fields["verdict"] = "stalled" if (h.get("stalled") or paging) else "ok"
        et = now.astimezone(_zi(TZ)) if now.tzinfo is not None else now.replace(tzinfo=_zi(TZ))
        day = et.date().isoformat()
        from api import ntfy_push
        mem = _load_feed_alerts(paths)
        changed = False
        host = _this_host_id()
        sh = paging[0] if paging else h            # the stall this episode reports
        stf = sh.get("timeframe") or tf
        newest = _hhmm_of(sh.get("newest_closed_bar_et"))

        # 1. bars stopped (finding 6) -- one episode per stall, per session day
        st = mem.get("stall") if isinstance(mem.get("stall"), dict) else {}
        if st.get("active") and st.get("day") != day:
            log(f"[cloud-signal] FEED: yesterday's stall episode closed at the day change")
            st, changed = {}, True
            _engine_note_forget("feed_stall", paths, log=log)
        if paging:
            if not st.get("active"):
                st = {"day": day, "active": True, "since": et.isoformat(), "pushed": False,
                      "timeframe": stf}
                changed = True
                log(f"[cloud-signal] FEED STALLED: no new {stf} bar closed for "
                    f"{(sh.get('bar_age_s') or 0) / 60:.0f} min (newest {newest} ET, "
                    f"{sh.get('bars_missing')} of {sh.get('bars_due')} bar(s) missing today)")
            if not st.get("pushed"):
                age_min = (sh.get("bar_age_s") or 0) / 60.0
                log(f"[cloud-signal] FEED STALLED page ({host}): no new {stf} bar for "
                    f"{age_min:.0f} min, newest {newest} ET, {sh.get('bars_missing')} of "
                    f"{sh.get('bars_due')} missing, source {sh.get('source') or 'cache'}")
                newest_epoch = sh.get("newest_closed_bar_epoch")
                closed_at = (float(newest_epoch) + TIMEFRAME_SECONDS.get(stf, 300)
                             if newest_epoch else None)
                note = ntfy_push.plain(
                    "QQQ book", "prices stopped", "the QQQ book cannot enter or exit trades",
                    (f"No new QQQ price bar since {ntfy_push.hhmm(closed_at, now=et)}."
                     if closed_at else f"No new QQQ price bar for {age_min:.0f} min."),
                    "nothing - the signal program keeps trying; ask Claude (PAPER-WB chat) "
                    "if it lasts")
                _engine_note("feed_stall", "feed_stall", note, paths, log=log, push=push)
                st["pushed"] = True
                changed = True
        elif st.get("active"):
            try:
                since = _dt.datetime.fromisoformat(st.get("since"))
                mins = max(0.0, (et - since).total_seconds() / 60.0)
            except Exception:
                mins = 0.0
            rtf = st.get("timeframe") or tf
            rh = next((x for x in watched if x.get("timeframe") == rtf), h)
            log(f"[cloud-signal] FEED recovered: {rtf} bars arriving again (newest "
                f"{_hhmm_of(rh.get('newest_closed_bar_et'))} ET)")
            if st.get("pushed"):
                _engine_note_clear("feed_stall", "QQQ book",
                                   f"prices stopped for about {mins:.0f} min", paths, log=log,
                                   push=push)
            st, changed = {"day": day, "active": False}, True
        mem["stall"] = st

        # 2. live bars on yfinance instead of Webull (finding 15) -- counted per real fetch
        yf = mem.get("yf") if isinstance(mem.get("yf"), dict) else {}
        if yf and yf.get("day") != day:
            # like the stall episode: yesterday's streak (and its page) ends quietly at the
            # day change, so a fresh morning fallback counts from 1 and pages on its own
            log(f"[cloud-signal] FEED: yesterday's yfinance streak closed at the day change")
            _engine_note_forget("feed_yf", paths, log=log)
            yf = {}
            mem["yf"] = yf
            changed = True
        # every live timeframe fetched on this tick (EVERY LIVE TIMEFRAME): one count per
        # fetch tick on which ANY of them came from yfinance
        fetched = [(x.get("timeframe"), x.get("source")) for x in watched
                   if x.get("fetched") and x.get("source")]
        yf_tfs = "/".join(str(t) for t, s in fetched if s == "yfinance")
        if fetched:
            if yf_tfs:
                yf = dict(yf, streak=int(yf.get("streak") or 0) + 1, day=day)
                if not yf.get("since"):
                    yf["since"] = et.isoformat()
                changed = True
                if yf["streak"] >= FEED_YF_PUSH_FETCHES and not yf.get("pushed"):
                    err = _WEBULL_LAST_ERR.get("text") or "no error text (empty reply)"
                    token = any(s in err.upper() for s in ("PENDING", "ERROR_INIT_TOKEN"))
                    log(f"[cloud-signal] FEED ON YFINANCE page ({host}): live {yf_tfs} bars "
                        f"from yfinance for {yf['streak']} fetches in a row; last Webull error: "
                        f"{err}")
                    if token:
                        note = ntfy_push.plain(
                            "QQQ book", "approve Webull login",
                            "the QQQ book trades on late prices",
                            "QQQ prices come from the slower backup source: the Webull login "
                            "is waiting for approval.",
                            "approve the login in the Webull app", priority="high")
                    else:
                        note = ntfy_push.plain(
                            "QQQ book", "backup prices", "the QQQ book trades on late prices",
                            "QQQ prices are coming from the slower backup source, not Webull.",
                            "nothing - it switches back by itself; ask Claude (PAPER-WB chat) "
                            "if it lasts")
                    _engine_note("feed_yf", "feed_yf", note, paths, log=log, push=push)
                    yf["pushed"] = True
            else:
                if yf.get("pushed"):
                    log(f"[cloud-signal] FEED: live "
                        f"{'/'.join(str(t) for t, _ in fetched)} bars from Webull again "
                        f"(after {int(yf.get('streak') or 0)} yfinance fetches)")
                    _engine_note_clear("feed_yf", "QQQ book", "prices from the backup source",
                                       paths, log=log, push=push)
                if yf:
                    changed = True
                yf = {}
            mem["yf"] = yf
        fields["bar_source"] = h.get("source") or None
        fields["yf_fallback_streak"] = int(yf.get("streak") or 0)
        if changed:
            _save_feed_alerts(paths, mem, log=log)
        return fields
    except Exception as e:
        log(f"[cloud-signal] feed health check failed (heartbeat written without it): "
            f"{type(e).__name__}: {e}")
        return {}


# ── engine pushes (EOD settle give-up, FEED HEALTH) ──────────────────────────────────────
# HIGH/URGENT go through api/ntfy_push.Outbox (<state_dir>/ntfy_outbox.json): one try now,
# then spaced retries on a background thread if ntfy is unreachable (finding 16). Only on
# the cloud box (EDGELOG_HOST_ROLE=cloud, _is_cloud_host): the PC's runner thread steps the
# same engine and must never page with the same titles.
ENGINE_OUTBOX_BACKGROUND = True
# FEED HEALTH pushes leave the engine thread (see _feed_health); tests set False to record
# them synchronously
FEED_PUSH_BACKGROUND = True
_ENGINE_OUTBOXES = {}
# the engine thread and a background push thread can both ask first: ONE Outbox per file, or
# two in-memory queues would rewrite the same ntfy_outbox.json and lose a push
_ENGINE_OUTBOX_LOCK = threading.Lock()


def _engine_outbox(paths):
    from api import ntfy_push
    path = os.path.join(paths["state_dir"], "ntfy_outbox.json")
    with _ENGINE_OUTBOX_LOCK:
        box = _ENGINE_OUTBOXES.get(path)
        if box is None or box.background != bool(ENGINE_OUTBOX_BACKGROUND):
            box = ntfy_push.Outbox(
                path,
                sender=lambda m, t, p: ntfy_push.push_result(m, title=t, priority=p, timeout=4),
                tag="cloud-signal", background=ENGINE_OUTBOX_BACKGROUND)
            _ENGINE_OUTBOXES[path] = box
        return box


# THE PLAIN PHONE FORMAT for the engine's own NEW pushes (KEEL size differs, prices stopped /
# on the backup source -- api/ntfy_push PLAIN FORMAT, v73.1120/1121):
# each builds its text with ntfy_push.plain() and goes through _engine_note(), which applies
# the shared repeat rule (ntfy_push.dedupe) per problem key, persisted in
# <state_dir>/phone_dedupe.json, logs any lint() problem, and hands the note to _engine_push.
# _engine_note_clear() sends the one low "back to normal" (only after a high push in the
# episode); _engine_note_forget() ends an episode quietly (the day change).
PHONE_DEDUPE_FILE = "phone_dedupe.json"
_PHONE_LOCK = threading.Lock()


def _phone_store_path(paths):
    return os.path.join((paths or DEFAULT_PATHS)["state_dir"], PHONE_DEDUPE_FILE)


def _phone_update(paths, fn, log=print):
    """Load the dedupe store, apply fn(store) -> result, save it. Never raises (returns None)."""
    try:
        with _PHONE_LOCK:
            p = _phone_store_path(paths)
            try:
                with open(p, encoding="utf-8") as f:
                    store = json.load(f)
                store = store if isinstance(store, dict) else {}
            except Exception:
                store = {}
            res = fn(store)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(store, f, indent=1)
            if not qp._replace_with_retry(tmp, p, log=log,
                                          what="[cloud-signal] phone_dedupe.json"):
                log("[cloud-signal] phone_dedupe.json not saved (a repeat push is possible)")
            return res
    except Exception as e:
        log(f"[cloud-signal] phone dedupe failed ({type(e).__name__}: {e})")
        return None


def _engine_note(key, problem_id, note, paths=None, log=print, push=None, now_ts=None):
    """Send one plain() note through the repeat rule: pushes only when dedupe says so (a NEW or
    WORSE problem, or the same one a day later). `push` as for _engine_push (the stream commit
    passes _engine_push_background). Returns the dedupe action. Never raises."""
    try:
        from api import ntfy_push
        for p in ntfy_push.lint(note):
            log(f"[cloud-signal] phone note lint: {p}: {note.get('title')}")
        now_ts = _time.time() if now_ts is None else now_ts
        rank = ntfy_push.RANK.get(note.get("priority"), 0)
        action = _phone_update(paths, lambda st: ntfy_push.dedupe_in(
            st, key, {str(problem_id): rank}, now_ts), log=log)
        if action == "push":
            (push or _engine_push)(note["message"], note["title"], priority=note["priority"],
                                   paths=paths, log=log)
        else:
            log(f"[cloud-signal] phone note held by the repeat rule: {note.get('title')}")
        return action
    except Exception as e:
        log(f"[cloud-signal] phone note failed ({type(e).__name__}: {e})")
        return None


def _engine_note_clear(key, area, what, paths=None, log=print, push=None, now_ts=None):
    """The problem `key` cleared: ONE low "back to normal" when its episode had a high push."""
    try:
        from api import ntfy_push
        now_ts = _time.time() if now_ts is None else now_ts
        action = _phone_update(paths, lambda st: ntfy_push.dedupe_in(st, key, {}, now_ts),
                               log=log)
        if action == "clear":
            note = ntfy_push.back_to_normal(area, what)
            (push or _engine_push)(note["message"], note["title"], priority=note["priority"],
                                   paths=paths, log=log)
        return action
    except Exception as e:
        log(f"[cloud-signal] phone clear failed ({type(e).__name__}: {e})")
        return None


def _engine_note_forget(key, paths=None, log=print):
    """End the problem `key`'s episode quietly (no push) -- e.g. at the day change."""
    _phone_update(paths, lambda st: st.pop(key, None), log=log)


def _engine_push(msg, title, priority="high", paths=None, log=print):
    """One engine alert. Returns what the sender returned (True / "queued" / None / False),
    or None when this host does not push. Never raises."""
    try:
        if not _is_cloud_host():
            log(f"[cloud-signal] (not the cloud box, no push) {title}: {msg}")
            return None
        from api import ntfy_push
        paths = paths or DEFAULT_PATHS
        if ntfy_push.is_durable(priority):
            r = _engine_outbox(paths).send(msg, title, priority, log=log)
            if r is not False:
                return r
            # False: the outbox itself broke before any network try -- one plain try below
            log(f"[cloud-signal] ntfy outbox could not take the push -- one plain try: {title}")
        ok, detail = ntfy_push.push_result(msg, title=title, priority=priority, timeout=4)
        if ok is False:
            log(f"[cloud-signal] ntfy push failed ({detail}): {title}")
        return ok
    except Exception as e:
        log(f"[cloud-signal] push failed ({type(e).__name__}: {e}): {title}")
        return False


def cloud_signal_thread(stop=None, log=print):
    """Runner-hosted PARALLEL RUN. Steps the signal engine through every session so the
    QQQ-bar signals accumulate beside the NinjaTrader-mirrored shadow book, which is the
    evidence the "drop NinjaTrader" decision needs: two ledgers over the same sessions,
    one derived from NQ futures fills and one from QQQ bars alone.

    Signals only -- this thread cannot place an order, and nothing downstream of
    signals.csv exists. It never raises into the runner and never blocks its main loop.

    30s rather than cmd_loop's 20s: every step may hit yfinance once per timeframe before
    the cheap "no new bar closed" short-circuit in step() can skip the engine, and a 1m leg
    cannot gain a bar faster than once a minute anyway. Two fetches a minute per timeframe
    is enough to see a bar the moment it closes without leaning on a free endpoint.

    ITEM 10 (2026-09-25, "fire orders at the bar close from the live price feed"): the
    per-tick call below goes through api.cloud_signal_stream.run_stream_aware_step
    instead of a bare step() -- see that module's docstring. It always ends by calling
    THIS module's real step() and returning exactly what it returns, so with its owner
    switch off (the default) this thread's behaviour is unchanged. The import is
    best-effort: a failure there (or inside the wrapper itself) falls straight back to
    calling step() directly, so a bug in the new module can never stop a real signal
    from being evaluated. The sleep at the bottom is the only other change: it fast-polls
    (api.cloud_signal_stream.HANDOFF_POLL_SECONDS, ~1s -- not the producer's own ~250ms
    internal thread, see that constant's own docstring for why) only in the ~minute after
    each 5m boundary (api.cloud_signal_stream.in_handoff_window) so that module's own
    local hand-off-file check can catch a stream bar within a second or two of its close
    instead of the classic ~30s;
    api.cloud_signal_stream.run_stream_aware_step throttles the actual network fetch back
    to this thread's normal THREAD_STEP_SEC cadence regardless of how often it is called,
    so the fast poll never turns into a fast REST-fetch loop.

    NEVER refuses beside a fresh heartbeat (unlike cmd_once/cmd_loop, see
    _refuse_beside_live_writer's own docstring) -- this IS the live writer, and a stale
    heartbeat left by an old --loop or a runner restart must not stop it from starting.

    SHADOW LEGS (OWNER DECISION 2026-09-28): after each successful FETCH tick's live step
    and heartbeat, _shadow_tick runs the SHADOW_LEGS into their own store (see
    run_shadow_step). It never raises into this loop and never writes the live heartbeat,
    state.json or signals.csv.

    SERVING_HOSTS GATE (2026-09-26): checked FIRST, before anything else here -- see
    _serving_hosts_ok. This is both the runner's in-process thread (PC) and the box's
    own systemd ExecStart, so one check here covers both call sites; an excluded host
    returns at once, never touching signals.csv, state.json or the heartbeat file.

    EOD SETTLE (2026-09-28): for five minutes after each session's close this thread runs
    the settle step instead of idling -- see the EOD SETTLE block above _eod_settle_tick."""
    hosts_ok, hosts_reason = _serving_hosts_ok(log=log)
    if not hosts_ok:
        log(f"[cloud-signal] REFUSING to run the signal engine: {hosts_reason} -- never "
            "stepping, never writing signals.csv/state.json/heartbeat.json")
        return
    log("[cloud-signal] parallel run: ON (signals only, no order path)")
    # engine pushes the last process could not deliver (finding 16) -- retried off this loop
    if _is_cloud_host():
        try:
            _engine_outbox(DEFAULT_PATHS).resume(log=log)
        except Exception as e:
            log(f"[cloud-signal] ntfy outbox resume failed (non-fatal): {type(e).__name__}: {e}")
    try:
        log_history_windows(log=log)
    except Exception as e:                     # diagnostic only -- must never block startup
        log(f"[cloud-signal] history window logging failed ({type(e).__name__}: {e}) -- continuing")
    if SHADOW_LEGS:
        log(f"[cloud-signal] shadow legs: {', '.join(SHADOW_LEGS)} (no orders; ledger "
            f"{shadow_paths()['signals_path']})")
        try:
            log_history_windows(legs=SHADOW_LEGS, log=log)
        except Exception as e:                 # same: diagnostic only
            log(f"[cloud-signal] shadow history window logging failed ({type(e).__name__}: {e})")
        if NOISE_FORWARD_LOG:
            # resolve the engine commit NOW, not on the first NOISE row mid-session (it is
            # read from .git, no subprocess -- see noise_forward.engine_commit)
            try:
                from api import noise_forward as _nf
                _nf.engine_commit()
            except Exception as e:             # the forward log then reads it on first use
                log(f"[cloud-signal] NOISE forward log commit read failed ({type(e).__name__}: {e})")
    try:
        from api import cloud_signal_stream as _stream_mod
    except Exception as e:
        log(f"[cloud-signal] cloud_signal_stream unavailable, item 10 stream path disabled "
           f"({type(e).__name__}: {e}); stepping classically")
        _stream_mod = None
    # Bring the live ledger's header up to SIGNAL_COLS at boot rather than at the first
    # emitted event, which is always mid-session with api/qqq_exec.py reading the file (a
    # runner restart after the close then upgrades it while nobody is consuming). Atomic
    # either way -- see _migrate_signals_header.
    try:
        # ... and the shadow ledger's (same SIGNAL_COLS; its own first append would do it too)
        for _ledger in (DEFAULT_PATHS["signals_path"], shadow_paths()["signals_path"]):
            if os.path.exists(_ledger):
                _migrate_signals_header(_ledger, SIGNAL_COLS)
    except Exception as e:
        log(f"[cloud-signal] ledger header check failed (next append retries): {type(e).__name__}: {e}")
    last_fetch_wall = 0.0
    settle_mem = {}                  # EOD SETTLE: {date: {"last_try", "done", "gave_up"}}
    while stop is None or not stop.is_set():
        in_session = False           # set before the try so a throw still picks a sleep
        settling = False
        try:
            now_et = _dt.datetime.now(tz=_zi(TZ))
            in_session = (market_calendar.is_session(now_et.date())
                         and RTH_OPEN <= now_et.time() <= RTH_CLOSE)
            # A recognised half day ends at ITS close (13:00), not RTH_CLOSE: past it the
            # EOD SETTLE window below takes over, exactly as after 16:00 on a full day.
            if in_session and market_calendar.session_close_et(now_et.date()) != "16:00":
                half_close = _session_close_dt(now_et)
                if half_close is not None and now_et > half_close:
                    in_session = False
            settle_close = None if in_session else _eod_settle_close(now_et)
            settling = settle_close is not None
            if settling:
                _eod_settle_tick(now_et, settle_close, settle_mem, log=log)
            elif in_session:
                # THROTTLE (item 10): only the REST/network half of a step runs on the
                # classic 30s cadence -- a fast tick in between (see the sleep below)
                # still calls in, but with fetch=False, so it only ever costs a cheap
                # on-disk short-circuit check, never an extra network round trip.
                now_wall = _time.time()
                do_fetch = (now_wall - last_fetch_wall) >= THREAD_STEP_SEC
                if do_fetch:
                    last_fetch_wall = now_wall
                warnings = {}
                if _stream_mod is not None:
                    events = _stream_mod.run_stream_aware_step(
                        now=now_et, fetch=do_fetch, paths=DEFAULT_PATHS, warnings=warnings, log=log)
                else:
                    events = step(now=now_et, fetch=do_fetch, paths=DEFAULT_PATHS, warnings=warnings)
                cache_failed = bool(warnings.get("cache_write_failed"))
                note = f"{len(events)} event(s)" + (" (cache_write_failed)" if cache_failed else "")
                # FEED HEALTH (2026-10-05): newest closed bar, its age, bars due/missing and
                # the stalled verdict ride on the heartbeat; ok keeps its meaning
                health = _feed_health(now_et, warnings, DEFAULT_PATHS, log=log)
                if health.get("stalled") or health.get("stalled_timeframes"):
                    s_tf = (health.get("stalled_timeframes") or [health.get("bar_timeframe")])[0]
                    s_age = ((health.get("feed_by_timeframe") or {}).get(str(s_tf)) or {}).get(
                        "bar_age_s", health.get("bar_age_s"))
                    note += f" -- STALLED: no new {s_tf} bar for {(s_age or 0) / 60:.0f} min"
                _write_heartbeat(DEFAULT_PATHS, ok=True, note=note, cache_write_failed=cache_failed,
                                 health=health)
                for e in events:
                    log(f"[cloud-signal] {e['event']} {e['leg']} {e.get('side','')} "
                        f"@ {e.get('ref_price','')} ({e.get('ref_time','')}) {e.get('reason','')}")
                # SHADOW LEGS (OWNER DECISION 2026-09-28): only AFTER the live step and its
                # heartbeat, and only on a fetch tick -- the bars on disk only move when a
                # fetch lands, so the ~1s hand-off-window fast ticks between (fetch=False)
                # have nothing new for a shadow leg and are left to the live legs alone.
                # _shadow_tick never raises; its store is <state_dir>/shadow/.
                if do_fetch:
                    _shadow_tick(now_et, fetch=True, log=log)
            else:
                _write_heartbeat(DEFAULT_PATHS, ok=True, note="outside session hours")
        except Exception as e:                            # a bad step must never kill the run
            try:
                # EOD SETTLE: after the bell a failure stays ok=True (see the block above
                # _eod_settle_tick) -- no signal-driven action can happen then
                _write_heartbeat(DEFAULT_PATHS, ok=bool(settling),
                                 note=(("eod settle failed: " if settling else "")
                                       + f"{type(e).__name__}: {e}"))
            except Exception:
                pass
            log(f"[cloud-signal] step failed: {type(e).__name__}: {e}")
        sleep_s = THREAD_STEP_SEC if in_session else 60.0
        if settling:
            sleep_s = EOD_SETTLE_POLL_SEC   # cheap passes; _eod_settle_tick paces the steps
        if in_session and _stream_mod is not None:
            try:
                if _stream_mod.in_handoff_window(now_et):
                    sleep_s = _stream_mod.HANDOFF_POLL_SECONDS
            except Exception:
                sleep_s = THREAD_STEP_SEC
        _time.sleep(sleep_s)


def cmd_loop():
    """step() every 20s during session hours, sleep outside them, until Ctrl+C. Refused
    (returns 2) while a live writer's heartbeat is fresh -- see
    _refuse_beside_live_writer -- so this can never become a second writer beside the
    runner's own cloud_signal_thread or another --loop/--once. Also refused (returns 2)
    when this host is excluded by config.json's serving_hosts -- see
    _serving_hosts_ok's docstring: that gate protects cloud_signal_thread, but a
    hand-run `--loop` on an excluded host bypassed it (MINOR review fix, 2026-09-26).

    Both checks run EXACTLY ONCE, here, before this loop's own first heartbeat write --
    never inside the loop below. This loop writes the heartbeat itself every iteration
    (ok=True, "outside session hours" or an event count), so checking freshness again
    inside the loop would see the stamp IT JUST WROTE a moment before and refuse itself
    on the very next pass."""
    paths = DEFAULT_PATHS
    hosts_ok, hosts_reason = _serving_hosts_ok()
    if not hosts_ok:
        print(f"cloud_signal --loop: REFUSED -- {hosts_reason}")
        return 2
    rc = _refuse_beside_live_writer(paths, "--loop")
    if rc:
        return rc
    log_history_windows(paths=paths)
    print("cloud_signal --loop: stepping every 20s during session hours (Ctrl+C to stop)")
    while True:
        now_et = _dt.datetime.now(tz=_zi(TZ))
        in_session = (market_calendar.is_session(now_et.date())
                     and RTH_OPEN <= now_et.time() <= RTH_CLOSE)
        if in_session:
            try:
                warnings = {}
                events = step(now=now_et, fetch=True, paths=paths, warnings=warnings)
                cache_failed = bool(warnings.get("cache_write_failed"))
                note = f"{len(events)} event(s)" + (" (cache_write_failed)" if cache_failed else "")
                _write_heartbeat(paths, ok=True, note=note, cache_write_failed=cache_failed)
                if events:
                    print(_fmt_ledger_table(events))
            except Exception as e:                       # never let the loop die silently
                _write_heartbeat(paths, ok=False, note=str(e))
                print(f"  [warn] step() failed: {e}", file=sys.stderr)
            _time.sleep(20)
        else:
            _write_heartbeat(paths, ok=True, note="outside session hours")
            _time.sleep(60)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", metavar="YYYY-MM-DD",
                    help="replay one cached session in an isolated copy")
    ap.add_argument("--live-paths", action="store_true",
                    help="with --replay: write INTO the live ledger/state instead of a copy "
                         "(refused while a live writer's heartbeat is fresh)")
    ap.add_argument("--once", action="store_true", help="one live step() and exit")
    ap.add_argument("--loop", action="store_true", help="step() every 20s during session hours")
    args = ap.parse_args(argv)
    if args.live_paths and not args.replay:
        ap.error("--live-paths only applies to --replay")
    if args.replay:
        rc = cmd_replay(args.replay, live_paths=args.live_paths)
        if rc:
            sys.exit(rc)
    elif args.once:
        rc = cmd_once()
        if rc:
            sys.exit(rc)
    elif args.loop:
        rc = cmd_loop()
        if rc:
            sys.exit(rc)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
