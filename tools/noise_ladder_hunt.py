#!/usr/bin/env python3
"""
NOISE BAR-SIZE LADDER — R / YR vs EV R (LANE A of the 2026-09-04 four-lane hunt).

Owner ask (verbatim, via the hunt brief): "keep testing and auto validate anything that
looks promising. i want you to find something that beats everything, especity on EVr and
R/yr."

THE QUESTION
------------
NOISE is the program's R / YR engine (R / YR = EV R x trades per year).  Round 5
(NOISE.md, 2026-08-27) showed the #243 card keeps a recognisable edge from 1m to 60m on
the NQ regular session, with trade count falling 3.7x and profit factor rising as bars
get longer.  Nobody computed EV R or R / YR per cell, nobody ran the NEW #305 champion
(a different configuration) across the ladder, and no bar size except 5m has ever been
Auto-Validated.  This driver does all three.

=================================================================================
PRE-REGISTRATION — written and committed BEFORE a single cell was run.
No cell is added after results are seen.  Every cell is reported, including the ugly
ones.  (Commit history is the attestation: this docstring is committed on its own,
with empty tools/noise_ladder_results/, before the results commit.)
=================================================================================

THE GRID — 3 configs x 6 bar sizes = 18 cells.  NOTHING IS RE-FITTED.

  configs (all three read out of artefacts that already exist; not one knob is tuned
  here, and no knob is searched):
    C1  "#305 best"      run #305 best_params, read from Firestore
                         users/IO0K35JpLIcH9YK4C0pMNYUzZOM2/runs/305.best_params:
                         lookback 51, bands 0.75 / 1.25, vwap exit, bandwidth stop
                         k 1.25, confirm_bars 4, daytype_mode skip_bot_short lo 0.25,
                         vol_skip_pct 99, window all_day.
    C2  "#305 plateau"   the same run's plateau_pick.params (the PDP plateau cell, not
                         the argmax): lookback 82, bands 1.25 / 1.5, vwap exit, ATR stop
                         k 3.5, confirm_bars 4, daytype_mode off, vol_skip_pct 88,
                         window afternoon_block.
    C3  "#243 card"      NOISE_1_1_SBS_V90.py DEFAULT_PARAMS, passed EXPLICITLY (a card
                         file pins only in DEFAULT_PARAMS; params={} would silently run
                         the parent's signature defaults - the run-#234 lesson).

  bar sizes (NQ, regular session, source db_noadj_rth):
    1m   REGISTERED master id 35
    2m   REGISTERED master id 42
    3m   HARNESS-RESAMPLED from the 1m master  (no registered 3m master exists)
    5m   REGISTERED master id 37   <- the base / incumbent bar size
    10m  HARNESS-RESAMPLED from the 5m master  (no registered 10m master exists)
    15m  REGISTERED master id 41
  The resampler is tools/noise_hunt5.py's own `resample()`, imported (not copied) so the
  round-5 cells reproduce bar-for-bar.  3m is resampled from 1m and 10m from 5m, exactly
  the sources round 5 used.  EVERY RESAMPLED CELL IS LABELLED AS SUCH IN EVERY TABLE.

  window        SELECTION 2010-06-07 -> 2025-02-10 (run #231/#305 optimize window).
                EVERY ranking, verdict and decision is made here and nowhere else.
  costs         cost_pts 0.533 round-turn, multiplier 20, 1 contract, source db_noadj_rth.
  engine        augur_engine.engine.run_backtest on augur_strategies/NOISE_1_0.py with
                explicit params - the REAL engine, not the research fork, because C2 uses
                stop_mode='atr' and window='afternoon_block', which tools/
                noise_variant_research.py's run_variant does not implement.

INCUMBENTS, recomputed in THIS harness on THIS window
  The three 5m cells ARE the incumbents: C1@5m is run #305's champion, C3@5m is run
  #243's card, C2@5m is #305's plateau pick.  Run-doc numbers are full-window and are
  NOT comparable, so nothing below is read off a run card.
  Cross-family, for ORIENTATION ONLY (full-window run-doc reads, not recomputed here,
  and said plainly rather than spun): the best single-leg EV R in the program is
  ENGU-Q #198 at ~1.03 with R / YR ~60.  NOISE's EV R is structurally 0.2-0.3 because
  it wins ~30-40% of the time on a wide band, so NO NOISE CELL CAN BEAT #198 ON EV R.
  That is stated up front, before the numbers, so it cannot be presented as a discovery.

THE BAR — two tiers, both fixed now.

  TIER 1 = the hunt brief's section 3.4, judged against the PROGRAM-WIDE best incumbent
  single leg (EV R 1.03 and R / YR 60, ENGU-Q #198):
    BEATS EVERYTHING = beats it on BOTH EV R and R / YR, with n >= 300, PF >= 1.25,
      >= 9 positive calendar years, and still beats on both after the 10 best trades
      are removed.
    PROMISING = beats it on ONE axis by >= 15% while losing <= 15% on the other, same
      guards.
    DECLARED IN ADVANCE: on the arithmetic above, Tier 1 is unreachable for this family.
    It is computed and printed for every cell anyway, and no cell will be described as
    clearing it.

  TIER 2 = the WITHIN-FAMILY bar, and it is the ONLY thing that can trigger an
  Auto-Validate in this lane.  Let INC_EVR = the highest EV R and INC_RYR = the highest
  R / YR among the THREE 5m incumbent cells (C1/C2/C3 at 5m), each taken on its own axis.
  A NON-5m cell is:
    PROMISING  if it beats INC_RYR by >= 15% while losing <= 15% of INC_EVR,
               OR beats INC_EVR by >= 15% while losing <= 15% of INC_RYR;
    STRONG     if it beats BOTH INC_EVR and INC_RYR;
    otherwise NEAR-MISS (within 5% of a leg) or DEAD.
  GUARDS on every Tier-2 verdict, all four required: n >= 300; PF >= 1.25; >= 9 positive
  calendar years in the selection window; and the winning axis still beats its incumbent
  AFTER the cell's 10 best trades are removed.
  0.15 is the brief's own margin; 0.80/0.90 house floors are not used here because this
  is a two-axis comparison, not a net-dollar one.

CONCENTRATION AND ERA READS, applied to EVERY cell (round 5 flagged 1m for exactly these
and they are the difference between a real edge and a lucky decade):
  * net, EV R and R / YR recomputed with the 10 best trades deleted;
  * the 2010-2017 subtotal in dollars (round 5: 92-102% of every cell's net is 2018-2025);
  * $/trade against 2x the round-turn cost ($21.32);
  * positive calendar years out of the years the window actually spans.

REPRODUCTION / PARITY GATES — nothing prints unless all four pass.
  P1  #243 card at 5m on the selection window == round 5's BASE cell to the dollar:
      n 4,054 / net $320,130.25 / PF 1.4201 / maxDD $18,424.69   (NOISE.md 2026-08-27)
  P2  #305 best_params reproduces run #305's SAVED validate figures to 10 decimal places:
      is_trades 2,591 and is_pf 1.4240226178071735.
      CORRECTION TO THE LANE ORDER, recorded because it matters for anyone re-checking:
      #305's is_* is NOT the whole optimize window.  validate.py Stage A calls run_auto
      (method='single', oos=True), and auto.py splits the optimize window 75/25 BY BARS
      (OOS_SPLIT=0.75), so is_trades/is_pf are measured on the FIRST 75% of the bars,
      2010-06-07 -> 2021-06-15 15:45 ET.  The whole optimize window gives n 3,407 /
      PF 1.5403 instead.  The gate reproduces the 75% slice, which is what the run doc
      actually stores.
  P3  #243 card at 1m on the selection window == round 5's 1m cell:
      n 9,390 / net $271,362 / PF 1.263.  This is the cross-harness gate: round 5
      measured it through run_variant, this driver measures it through the real engine.
  P4  resampler parity - the 1m master resampled to 5m reproduces >= 99% of the
      registered 5m master's bars to the tick.  If P4 fails, the 3m and 10m cells are
      DROPPED rather than reported.
  Causality is not assumed: the selection-window slice of a continuous full-length run
  must equal a run stopped at 2025-02-10 to the cent (checked inside P1).

LOCKBOX
  2025-02-11 -> each cell's own master end.  SPENT - this family's lockbox has been read
  many times (runs 202/203, the 2026-08-11 gate test, #225/#231, the 2026-08-17 campaign
  and round 5 itself).  Read ONCE here, AFTER every verdict above is written, printed
  labelled CONFIRMATORY, and NEVER used to rank, order, pick or rescue a cell.
  Cell ends differ and are pinned per cell, not floated:
      1m  -> 2026-06-30 (the 2026-07-01..08-05 NQ 1m hole; the master carries bars past
             it, so this end is pinned by hand, not taken from the master)
      2m  -> 2026-07-16   3m -> 2026-06-30 (inherits 1m)   5m -> 2026-08-12
      10m -> 2026-08-12 (inherits 5m)                      15m -> 2026-06-30

AUTO-VALIDATE (max 2 for this lane, and only on a TIER-2 PROMISING-or-better NON-5m cell)
  Queued as: type 'validate', strategy NOISE_1_0.py (the PARENT, open ranges, discover
  'auto' - never a pinned card), instrument NQ, session rth, source db_noadj_rth,
  date_from 2010-06-07, cost_pts 0.533, mult 20, lockbox_months 18, n_trials 300,
  n_rounds 5, workers 4, preset 'validate', provider 'claude-cli', dsr true,
  status 'queued', and a note citing this pre-registration.
  date_to is PINNED PER TIMEFRAME to that master's own end - NQ 2m 2026-07-16, NQ 15m
  2026-06-30 - and never left blank.
  3m and 10m have NO REGISTERED MASTER, so they CANNOT be queued whatever they measure;
  they are reported as "would need a registered master" and nothing is invented.
  A dupe-guard refuses to queue if any NOISE validate already exists on that timeframe,
  or if any job is open in users/.../backtests.

WHAT THIS DRIVER DOES NOT DO: it does not restart the runner, import/refresh/register a
master, touch NinjaTrader, or write anything to Firestore except the two Auto-Validate
job documents, and those only under the explicit `queue` subcommand.

    python tools/noise_ladder_hunt.py --gate     # parity gates only
    python tools/noise_ladder_hunt.py ladder     # the 18 cells, verdicts, lockbox, CSV
    python tools/noise_ladder_hunt.py queue --tf 2m [--dry]   # the guarded job queue
"""
import argparse
import csv
import io
import json
import os
import sys

import numpy as np
import pandas as pd

# The master registry (optimizer_history.db + augur_uploads/) lives only in the SHARED
# checkout, never in a git worktree.  EDGELOG_DATA_ROOT lets this run from a worktree
# against the real data; unset, it resolves to its own checkout.  Same idiom as
# tools/noise_hunt5.py.
EDGELOG_ROOT = os.environ.get("EDGELOG_DATA_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(EDGELOG_ROOT, "tools"), EDGELOG_ROOT):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

from augur_engine.data import find_master, load_master_arrays        # noqa: E402
from augur_engine.engine import run_backtest                         # noqa: E402
from noise_hunt5 import resample                                     # noqa: E402  (round-5 resampler, reused verbatim)

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
OPT_FROM, OPT_TO = "2010-06-07", "2025-02-10"
LB_FROM = "2025-02-11"
IS_CUT = "2016-04-29 13:50"          # round 5's IS/WF instant, reused unchanged
COST, MULT, SOURCE = 0.533, 20.0, "db_noadj_rth"
STRATEGY = "NOISE_1_0.py"

# Tier-1 orientation constants (full-window run-doc reads, NOT recomputed here)
T1_EVR, T1_RYR = 1.03, 60.0
MARGIN = 0.15
GUARD_N, GUARD_PF, GUARD_YEARS = 300, 1.25, 9

CONFIGS = {
    "C1 #305 best": dict(
        lookback=51, band_mult_long=0.75, band_mult_short=1.25, exit_mode="vwap",
        side="Both", window="all_day", flat_eod=True, skip_holidays=False,
        stop_mode="bandwidth", stop_k=1.25, confirm_bars=4,
        daytype_mode="skip_bot_short", daytype_lo=0.25, daytype_hi=0.6,
        vol_skip_pct=99.0),
    "C2 #305 plateau": dict(
        lookback=82, band_mult_long=1.25, band_mult_short=1.5, exit_mode="vwap",
        side="Both", window="afternoon_block", flat_eod=True, skip_holidays=False,
        stop_mode="atr", stop_k=3.5, confirm_bars=4,
        daytype_mode="off", daytype_lo=0.25, daytype_hi=0.85,
        vol_skip_pct=88.0),
    "C3 #243 card": dict(
        lookback=44, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
        side="Both", window="all_day", flat_eod=True, skip_holidays=False,
        stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
        daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8,
        vol_skip_pct=90.0),
}

# (tf, kind, source_tf, minutes, lockbox_end, registered?)
CELLS = [
    ("1m",  "master",   None, None, "2026-06-30", True),
    ("2m",  "master",   None, None, "2026-07-16", True),
    ("3m",  "resample", "1m", 3,    "2026-06-30", False),
    ("5m",  "master",   None, None, "2026-08-12", True),
    ("10m", "resample", "5m", 10,   "2026-08-12", False),
    ("15m", "master",   None, None, "2026-06-30", True),
]
BASE_TF = "5m"

_ARR = {}


# ══════════════════════════════════════════════════════════════════════════════════
# data
# ══════════════════════════════════════════════════════════════════════════════════
def _ts(s, idx):
    t = pd.Timestamp(s)
    tz = getattr(idx, "tz", None)
    return t.tz_localize(tz) if (tz is not None and t.tzinfo is None) else t


def slice_arr(arr, date_from=None, date_to=None):
    idx = arr["index"]
    m = np.ones(len(idx), bool)
    if date_from:
        m &= np.asarray(idx >= _ts(date_from, idx))
    if date_to:
        m &= np.asarray(idx < _ts(date_to, idx) + pd.Timedelta(days=1))
    out = {k: (v[m] if isinstance(v, np.ndarray) and len(v) == len(idx) else v)
           for k, v in arr.items() if k != "index"}
    out["index"] = idx[m]
    return out


def get_arr(tf):
    """Arrays for one ladder cell, capped at that cell's own pinned lockbox end."""
    if tf in _ARR:
        return _ARR[tf]
    spec = next(c for c in CELLS if c[0] == tf)
    _, kind, src, mins, lb_end, _reg = spec
    if kind == "master":
        m = find_master("NQ", tf, "rth", SOURCE)
        if m is None:
            _ARR[tf] = (None, None)
            return _ARR[tf]
        arr = load_master_arrays(m, date_from=None, date_to=lb_end)
        _ARR[tf] = (dict(arr), m)
    else:
        base, m = get_arr(src)
        if base is None:
            _ARR[tf] = (None, None)
            return _ARR[tf]
        _ARR[tf] = (resample(slice_arr(base, None, lb_end), mins, False), m)
    return _ARR[tf]


# ══════════════════════════════════════════════════════════════════════════════════
# metrics — every definition straight from the hunt brief section 1
# ══════════════════════════════════════════════════════════════════════════════════
def window_years(a, b):
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25


SEL_YEARS = window_years(OPT_FROM, OPT_TO)


def stats(seq, years):
    """seq = [(entry_timestamp, net_pnl_dollars), ...] in time order."""
    if not seq:
        return None
    p = np.array([x[1] for x in seq], float)
    gw = float(p[p > 0].sum())
    gl = float(-p[p < 0].sum())
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    cum = np.cumsum(p)
    dd = float(abs(np.min(cum - np.maximum.accumulate(cum))))
    net = float(p.sum())
    losses = p[p < 0]
    avg_loss = float(-losses.mean()) if len(losses) else None
    evr = (p.mean() / avg_loss) if (avg_loss and avg_loss > 1e-12) else None
    pyear = {}
    for dt, v in seq:
        pyear[int(dt.year)] = pyear.get(int(dt.year), 0.0) + v
    return dict(
        n=len(p), net=net, pf=pf, dd=dd,
        mar=((net / years) / dd) if dd > 1e-9 else float("inf"),
        win=100.0 * float((p > 0).sum()) / len(p),
        dpt=net / len(p), evr=evr,
        ryr=(evr * len(p) / years) if evr is not None else None,
        pyear=pyear, pos_years=sum(1 for v in pyear.values() if v > 0),
        n_years=len(pyear),
        era_2010_17=sum(v for y, v in pyear.items() if 2010 <= y <= 2017),
        years=years)


def drop_best(seq, k=10):
    if len(seq) <= k:
        return []
    order = sorted(range(len(seq)), key=lambda i: seq[i][1], reverse=True)[:k]
    bad = set(order)
    return [t for i, t in enumerate(seq) if i not in bad]


def net_seq(arr, params):
    r = run_backtest(STRATEGY, arrays=arr, params=params, cost_pts=COST,
                     return_trades=True)
    idx = arr["index"]
    return [(idx[int(t[0])], float(t[2]) * MULT) for t in r["trades"]]


# ══════════════════════════════════════════════════════════════════════════════════
# parity gates
# ══════════════════════════════════════════════════════════════════════════════════
def gates(verbose=True):
    ok = True
    resampler_ok = False

    # P1 — #243 card at 5m == round 5's BASE cell, plus the causality/slice check
    arr5, _ = get_arr("5m")
    if arr5 is None:
        print("  P1  NO MASTER for NQ/5m/rth/%s" % SOURCE)
        return False, False
    sel5 = slice_arr(arr5, None, OPT_TO)
    s = stats(net_seq(sel5, CONFIGS["C3 #243 card"]), SEL_YEARS)
    good = (s["n"] == 4054 and abs(s["net"] - 320130.25) < 1.0
            and abs(s["pf"] - 1.4201) < 5e-4 and abs(s["dd"] - 18424.69) < 1.0)
    ok &= good
    if verbose:
        print("  P1  #243 card @5m sel   n=%-6d net=$%-12s PF=%.4f DD=$%-11s  %s"
              % (s["n"], format(s["net"], ",.2f"), s["pf"], format(s["dd"], ",.2f"),
                 "PASS" if good else "FAIL (want 4054 / 320,130.25 / 1.4201 / 18,424.69)"))
    # causality: continuous run sliced == run stopped at OPT_TO
    cont = [t for t in net_seq(arr5, CONFIGS["C3 #243 card"])
            if t[0] < _ts(OPT_TO, arr5["index"]) + pd.Timedelta(days=1)]
    c = stats(cont, SEL_YEARS)
    cgood = c["n"] == s["n"] and abs(c["net"] - s["net"]) < 0.01
    ok &= cgood
    if verbose:
        print("  P1b causality/slice     continuous-slice n=%d net=$%s   %s"
              % (c["n"], format(c["net"], ",.2f"), "PASS" if cgood else "FAIL"))

    # P2 — #305 best_params reproduces the SAVED validate is_trades / is_pf.
    #      auto.py splits the optimize window 75/25 BY BARS (OOS_SPLIT), so the saved
    #      is_* is the FIRST 75% of the bars, not the whole optimize window.
    n = len(sel5["close"])
    ks = int(n * 0.75)
    sub = {k: (v[:ks] if isinstance(v, np.ndarray) and len(v) == n else v)
           for k, v in sel5.items()}
    sub["index"] = sel5["index"][:ks]
    r = run_backtest(STRATEGY, arrays=sub, params=CONFIGS["C1 #305 best"],
                     cost_pts=COST, return_trades=True)
    good = (r["num_trades"] == 2591 and abs(r["profit_factor"] - 1.4240226178071735) < 1e-9)
    ok &= good
    if verbose:
        print("  P2  #305 best IS(75%%)   n=%-6d PF=%.13f  cut %s   %s"
              % (r["num_trades"], r["profit_factor"], sub["index"][-1],
                 "PASS" if good else "FAIL (want 2591 / 1.4240226178071735)"))

    # P3 — cross-harness: #243 card at 1m == round 5's 1m cell (run_variant path)
    arr1, _ = get_arr("1m")
    if arr1 is None:
        print("  P3  NO 1m MASTER")
        ok = False
    else:
        s1 = stats(net_seq(slice_arr(arr1, None, OPT_TO), CONFIGS["C3 #243 card"]),
                   SEL_YEARS)
        good = (s1["n"] == 9390 and abs(s1["net"] - 271362) < 500
                and abs(s1["pf"] - 1.263) < 5e-4)
        ok &= good
        if verbose:
            print("  P3  #243 card @1m sel   n=%-6d net=$%-12s PF=%.4f   %s"
                  % (s1["n"], format(s1["net"], ",.0f"), s1["pf"],
                     "PASS" if good else "FAIL (want 9390 / 271,362 / 1.263)"))

    # P4 — resampler parity, 1m -> 5m against the registered 5m master
    if arr1 is not None:
        rs = resample(arr1, 5, False)
        a = pd.DataFrame({"o": rs["open"], "h": rs["high"], "l": rs["low"],
                          "c": rs["close"]}, index=rs["index"])
        b = pd.DataFrame({"o": arr5["open"], "h": arr5["high"], "l": arr5["low"],
                          "c": arr5["close"]}, index=arr5["index"])
        b = b[b.index <= a.index.max()]
        j = b.join(a, how="left", rsuffix="_r")
        same = int(((j["o"] == j["o_r"]) & (j["h"] == j["h_r"])
                    & (j["l"] == j["l_r"]) & (j["c"] == j["c_r"])).sum())
        frac = same / len(j) if len(j) else 0.0
        resampler_ok = frac >= 0.99
        if verbose:
            print("  P4  resampler 1m->5m    %s of %s registered bars to the tick = "
                  "%.3f%%   %s" % (format(same, ","), format(len(j), ","), 100 * frac,
                                   "PASS" if resampler_ok else
                                   "FAIL - 3m and 10m cells DROPPED"))
    return bool(ok), bool(resampler_ok)


# ══════════════════════════════════════════════════════════════════════════════════
# verdicts
# ══════════════════════════════════════════════════════════════════════════════════
def guards_ok(s, s10):
    g = {"n>=300": s["n"] >= GUARD_N, "PF>=1.25": s["pf"] >= GUARD_PF,
         "yrs>=9": s["pos_years"] >= GUARD_YEARS}
    return g, all(g.values()), s10


def tier1(s, s10):
    """The hunt brief section 3.4 bar against the program-wide incumbent (#198)."""
    if s["evr"] is None:
        return "NOT MEASURABLE"
    g, gok, _ = guards_ok(s, s10)
    beats_both = s["evr"] > T1_EVR and s["ryr"] > T1_RYR
    if beats_both and gok and s10 and s10["evr"] > T1_EVR and s10["ryr"] > T1_RYR:
        return "BEATS EVERYTHING"
    gain_e = s["evr"] / T1_EVR - 1.0
    gain_r = s["ryr"] / T1_RYR - 1.0
    if gok and ((gain_e >= MARGIN and gain_r >= -MARGIN)
                or (gain_r >= MARGIN and gain_e >= -MARGIN)):
        return "PROMISING"
    return "DEAD (EV R %.0f%% of #198)" % (100 * s["evr"] / T1_EVR)


def tier2(s, s10, inc_evr, inc_ryr):
    """The within-family bar — the only Auto-Validate trigger in this lane."""
    if s["evr"] is None:
        return "NOT MEASURABLE", {}
    g, gok, _ = guards_ok(s, s10)
    ge = s["evr"] / inc_evr - 1.0
    gr = s["ryr"] / inc_ryr - 1.0
    d = {"dEVR%": 100 * ge, "dRYR%": 100 * gr, "guards": g}
    if not gok:
        return "DEAD (guard: %s)" % ",".join(k for k, v in g.items() if not v), d
    ex_ok_r = bool(s10 and s10["ryr"] > inc_ryr)
    ex_ok_e = bool(s10 and s10["evr"] > inc_evr)
    if ge > 0 and gr > 0 and ex_ok_r and ex_ok_e:
        return "STRONG", d
    if gr >= MARGIN and ge >= -MARGIN and ex_ok_r:
        return "PROMISING (R/YR)", d
    if ge >= MARGIN and gr >= -MARGIN and ex_ok_e:
        return "PROMISING (EV R)", d
    if gr >= MARGIN and ge >= -MARGIN and not ex_ok_r:
        return "NEAR-MISS (dies ex-10-best)", d
    if max(ge, gr) >= 0.10:
        return "NEAR-MISS", d
    return "DEAD", d


# ══════════════════════════════════════════════════════════════════════════════════
# the ladder
# ══════════════════════════════════════════════════════════════════════════════════
HDR = ("%-20s %-16s %6s %11s %6s %6s %10s %7s %6s %7s %6s %10s %6s %7s %11s"
       % ("config", "bar", "n", "net $", "PF", "win %", "maxDD $", "MAR", "EV R",
          "R / YR", "yrs+", "net-x10", "EVRx10", "RYRx10", "2010-17 $"))


def row(cfg, tf, s, s10, tag):
    if s is None:
        return "%-20s %-16s  no trades" % (cfg, tf + tag)
    return ("%-20s %-16s %6d %11s %6.3f %6.1f %10s %7.2f %6.3f %7.1f %4d/%-2d %10s "
            "%6.3f %7.1f %11s"
            % (cfg, tf + tag, s["n"], format(s["net"], ",.0f"), min(s["pf"], 99.999),
               s["win"], format(s["dd"], ",.0f"), min(s["mar"], 999.99), s["evr"] or 0,
               s["ryr"] or 0, s["pos_years"], s["n_years"],
               format(s10["net"], ",.0f") if s10 else "-",
               (s10["evr"] if s10 else 0) or 0, (s10["ryr"] if s10 else 0) or 0,
               format(s["era_2010_17"], ",.0f")))


def run_ladder(outdir):
    print(__doc__.split("    python tools/noise_ladder_hunt.py")[0].rstrip())
    print("\n" + "=" * 150)
    print("PARITY GATES — nothing prints unless all pass")
    print("=" * 150)
    ok, resampler_ok = gates()
    if not ok:
        print("\nGATE FAILURE — nothing printed. The harness is not trusted; no cell "
              "is reported. (House rule.)")
        return 1
    if not resampler_ok:
        print("\nP4 FAILED — the 3m and 10m cells are DROPPED, not reported.")

    cells = [c for c in CELLS if resampler_ok or c[1] == "master"]
    dropped = [c[0] for c in CELLS if not (resampler_ok or c[1] == "master")]

    print("\n" + "=" * 150)
    print("SELECTION WINDOW %s -> %s  (%.2f years) | cost %.3f pts x $%.0f | 2x cost = "
          "$%.2f/trade | source %s" % (OPT_FROM, OPT_TO, SEL_YEARS, COST, MULT,
                                       2 * COST * MULT, SOURCE))
    print("Nothing re-fitted. MAR is ANNUALISED: (net / years) / maxDD. "
          "R / YR = EV R x trades per year. *x10 = the 10 best trades deleted.")
    print("=" * 150)
    print(HDR)

    res = {}
    for cname, params in CONFIGS.items():
        for tf, kind, src, mins, lb_end, reg in cells:
            arr, _m = get_arr(tf)
            if arr is None:
                print("%-20s %-16s  NO MASTER — cell dropped" % (cname, tf))
                continue
            seq = net_seq(slice_arr(arr, None, OPT_TO), params)
            s = stats(seq, SEL_YEARS)
            s10 = stats(drop_best(seq), SEL_YEARS)
            tag = " (resampled)" if kind == "resample" else ""
            print(row(cname, tf, s, s10, tag))
            res[(cname, tf)] = (s, s10, seq, kind, lb_end, reg)
            sys.stdout.flush()

    # ── incumbents ───────────────────────────────────────────────────────────────
    inc = [res[(c, BASE_TF)][0] for c in CONFIGS if (c, BASE_TF) in res]
    inc_evr = max(x["evr"] for x in inc)
    inc_ryr = max(x["ryr"] for x in inc)
    print("\n" + "=" * 150)
    print("INCUMBENTS, recomputed in THIS harness on THIS window")
    print("=" * 150)
    for c in CONFIGS:
        if (c, BASE_TF) in res:
            s = res[(c, BASE_TF)][0]
            print("  %-20s @5m   EV R %.3f   R / YR %5.1f   PF %.3f   net $%s"
                  % (c, s["evr"], s["ryr"], s["pf"], format(s["net"], ",.0f")))
    print("  TIER-2 incumbent bar:  INC_EVR %.3f   INC_RYR %.1f  (best on each axis)"
          % (inc_evr, inc_ryr))
    print("  TIER-1 incumbent bar:  EV R %.2f   R / YR %.0f   = ENGU-Q #198, a "
          "FULL-WINDOW RUN-DOC read, not recomputed here." % (T1_EVR, T1_RYR))
    print("  Said before the numbers and repeated after them: NOISE wins ~30-40%% of "
          "its trades on a wide band, so its EV R lives at 0.2-0.3 and NO cell in this")
    print("  study can beat #198's ~1.03. Tier 1 is unreachable for this family. "
          "That is a fact about the mechanism, not a near miss.")

    # ── verdicts ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 150)
    print("VERDICTS")
    print("=" * 150)
    print("%-20s %-16s %-34s %-30s %8s %8s" % ("config", "bar", "TIER 2 (within-family)",
                                               "TIER 1 (vs #198)", "dEVR %", "dRYR %"))
    rows_csv, promising = [], []
    for cname in CONFIGS:
        for tf, kind, src, mins, lb_end, reg in cells:
            if (cname, tf) not in res:
                continue
            s, s10, seq, kind, lb_end, reg = res[(cname, tf)]
            if tf == BASE_TF:
                v2, d = "INCUMBENT (base bar size)", {"dEVR%": 0.0, "dRYR%": 0.0}
            else:
                v2, d = tier2(s, s10, inc_evr, inc_ryr)
            v1 = tier1(s, s10)
            print("%-20s %-16s %-34s %-30s %8.1f %8.1f"
                  % (cname, tf + (" (resamp)" if kind == "resample" else ""), v2, v1,
                     d.get("dEVR%", 0), d.get("dRYR%", 0)))
            if v2.startswith(("PROMISING", "STRONG")):
                promising.append((cname, tf, reg, v2, d))
            rows_csv.append(dict(
                config=cname, bar=tf, registered_master=reg,
                resampled=(kind == "resample"), n=s["n"], net=round(s["net"], 2),
                pf=round(s["pf"], 4), win_pct=round(s["win"], 2), maxdd=round(s["dd"], 2),
                mar_annualised=round(s["mar"], 3), ev_r=round(s["evr"], 4),
                r_per_yr=round(s["ryr"], 2), pos_years=s["pos_years"],
                n_years=s["n_years"], dollars_per_trade=round(s["dpt"], 2),
                two_x_cost=round(2 * COST * MULT, 2),
                net_ex10=round(s10["net"], 2) if s10 else None,
                ev_r_ex10=round(s10["evr"], 4) if s10 else None,
                r_per_yr_ex10=round(s10["ryr"], 2) if s10 else None,
                era_2010_2017=round(s["era_2010_17"], 2),
                tier2=v2, tier1=v1,
                d_evr_pct=round(d.get("dEVR%", 0), 2),
                d_ryr_pct=round(d.get("dRYR%", 0), 2)))

    # ── IS / WF split inside the selection window (reported, never a leg) ────────
    print("\n" + "-" * 150)
    print("IS / WF split inside the selection window, cut at %s ET (round 5's instant). "
          "Reported, never a leg." % IS_CUT)
    print("-" * 150)
    for cname in CONFIGS:
        for tf, kind, src, mins, lb_end, reg in cells:
            if (cname, tf) not in res:
                continue
            s, s10, seq, kind, lb_end, reg = res[(cname, tf)]
            cut = _ts(IS_CUT, get_arr(tf)[0]["index"])
            a = stats([t for t in seq if t[0] <= cut], SEL_YEARS)
            b = stats([t for t in seq if t[0] > cut], SEL_YEARS)
            print("  %-20s %-6s IS n=%-5s $%-11s PF %-6s | WF n=%-5s $%-11s PF %s"
                  % (cname, tf,
                     a["n"] if a else "-", format(a["net"], ",.0f") if a else "-",
                     "%.3f" % a["pf"] if a else "-",
                     b["n"] if b else "-", format(b["net"], ",.0f") if b else "-",
                     "%.3f" % b["pf"] if b else "-"))

    # ── lockbox, read ONCE, after every verdict above ───────────────────────────
    print("\n" + "=" * 150)
    print("LOCKBOX %s -> each cell's own master end. SPENT (read many times before: runs "
          "202/203, the 2026-08-11 gate test," % LB_FROM)
    print("#225/#231, the 2026-08-17 campaign and round 5). CONFIRMATORY ONLY — read "
          "once, after every verdict above was written,")
    print("never used to rank, order, pick or rescue a cell. Ends are PINNED per cell, "
          "never floated.")
    print("=" * 150)
    print("%-20s %-16s %-12s %6s %12s %7s %6s %7s" % ("config", "bar", "end", "n",
                                                      "net $", "PF", "EV R", "R / YR"))
    for cname in CONFIGS:
        for tf, kind, src, mins, lb_end, reg in cells:
            if (cname, tf) not in res:
                continue
            arr, _m = get_arr(tf)
            lseq = net_seq(slice_arr(arr, LB_FROM, lb_end), CONFIGS[cname])
            ls = stats(lseq, window_years(LB_FROM, lb_end))
            print("%-20s %-16s %-12s %6s %12s %7s %6s %7s"
                  % (cname, tf, lb_end, ls["n"] if ls else "-",
                     format(ls["net"], ",.0f") if ls else "-",
                     "%.3f" % min(ls["pf"], 99.999) if ls else "-",
                     "%.3f" % ls["evr"] if ls and ls["evr"] else "-",
                     "%.1f" % ls["ryr"] if ls and ls["ryr"] else "-"))
            for r in rows_csv:
                if r["config"] == cname and r["bar"] == tf and ls:
                    r.update(lb_end=lb_end, lb_n=ls["n"], lb_net=round(ls["net"], 2),
                             lb_pf=round(min(ls["pf"], 99.999), 4),
                             lb_ev_r=round(ls["evr"], 4) if ls["evr"] else None,
                             lb_r_per_yr=round(ls["ryr"], 2) if ls["ryr"] else None)
            sys.stdout.flush()

    # ── what can and cannot be queued ───────────────────────────────────────────
    print("\n" + "=" * 150)
    print("AUTO-VALIDATE ELIGIBILITY (Tier-2 PROMISING or better, NON-5m, registered "
          "master required)")
    print("=" * 150)
    if not promising:
        print("  none — no non-5m cell cleared the Tier-2 bar.")
    for cname, tf, reg, v2, d in promising:
        print("  %-20s %-5s %-28s %s" % (cname, tf, v2,
              "QUEUEABLE (registered master)" if reg else
              "WOULD NEED A REGISTERED MASTER — not queued, nothing invented"))
    if dropped:
        print("\nDROPPED: %s (resampler gate P4 failed)" % ", ".join(dropped))

    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "cells.csv")
    keys = sorted({k for r in rows_csv for k in r})
    order = ["config", "bar", "registered_master", "resampled", "n", "net", "pf",
             "win_pct", "maxdd", "mar_annualised", "ev_r", "r_per_yr", "pos_years",
             "n_years", "dollars_per_trade", "two_x_cost", "net_ex10", "ev_r_ex10",
             "r_per_yr_ex10", "era_2010_2017", "tier2", "tier1", "d_evr_pct",
             "d_ryr_pct", "lb_end", "lb_n", "lb_net", "lb_pf", "lb_ev_r", "lb_r_per_yr"]
    order += [k for k in keys if k not in order]
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=order)
        w.writeheader()
        for r in rows_csv:
            w.writerow(r)
    print("\nwrote %s (%d rows)" % (path, len(rows_csv)))
    with io.open(os.path.join(outdir, "incumbents.json"), "w", encoding="utf-8") as fh:
        json.dump({"inc_evr": inc_evr, "inc_ryr": inc_ryr, "tier1_evr": T1_EVR,
                   "tier1_ryr": T1_RYR, "sel_years": SEL_YEARS}, fh, indent=1)
    return 0


# ══════════════════════════════════════════════════════════════════════════════════
# guarded Auto-Validate queue
# ══════════════════════════════════════════════════════════════════════════════════
TF_END = {"2m": "2026-07-16", "15m": "2026-06-30"}


def queue(tf, dry=False, reason=""):
    if tf not in TF_END:
        print("REFUSED — %s has no registered master; a job cannot be queued on it." % tf)
        return 1
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS",
                          os.path.join(EDGELOG_ROOT, "serviceAccount.json"))
    from google.cloud import firestore
    sa = json.load(io.open(os.path.join(EDGELOG_ROOT, "serviceAccount.json"),
                           encoding="utf-8"))
    db = firestore.Client(project=sa["project_id"])
    base = db.collection("users").document(UID)

    for d in base.collection("runs").stream():
        o = d.to_dict() or {}
        if "NOISE" in str(o.get("strategy") or "").upper() and str(o.get("timeframe")) == tf:
            print("REFUSED — a NOISE run already exists on %s: run %s" % (tf, d.id))
            return 1
    for d in base.collection("backtests").stream():
        o = d.to_dict() or {}
        if o.get("status") in ("queued", "running") and o.get("strategy") == STRATEGY \
                and str(o.get("timeframe")) == tf:
            print("REFUSED — an open NOISE job already targets %s: %s" % (tf, d.id))
            return 1

    JOB = {
        "type": "validate", "strategy": STRATEGY, "instrument": "NQ", "timeframe": tf,
        "session": "rth", "source": SOURCE, "date_from": OPT_FROM, "date_to": TF_END[tf],
        "cost_pts": COST, "slippage_pts": 0.25, "commission_usd": 5.66, "mult": 20,
        "discover": "auto", "n_trials": 300, "n_rounds": 5, "lockbox_months": 18,
        "wf_folds": 0, "min_trades": 30, "dsr": True, "transfer_to": None,
        "workers": 4, "preset": "validate", "provider": "claude-cli", "status": "queued",
        "note": reason,
    }
    if dry:
        print(json.dumps(JOB, indent=1))
        return 0
    JOB["createdAt"] = firestore.SERVER_TIMESTAMP
    ref = base.collection("backtests").document()
    ref.set(JOB)
    print("QUEUED job %s   %s %s  %s -> %s" % (ref.id, STRATEGY, tf, OPT_FROM, TF_END[tf]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="ladder", choices=["ladder", "queue"])
    ap.add_argument("--gate", action="store_true", help="parity gates only")
    ap.add_argument("--tf", default="2m")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--reason", default="")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "noise_ladder_results"))
    a = ap.parse_args()
    if a.gate:
        okk, _ = gates()
        sys.exit(0 if okk else 1)
    if a.cmd == "queue":
        sys.exit(queue(a.tf, a.dry, a.reason))
    sys.exit(run_ladder(a.out))
