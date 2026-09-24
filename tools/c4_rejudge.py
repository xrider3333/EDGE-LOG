"""RE-JUDGE EVERY DECIDED TILT UNDER THE REBUILT C4 (2026-09-24).

tools/c4_calibration.py showed C4's old test - one trade over 50% of the lockbox bucket's NET -
fails 73% of RANDOM untagged buckets at n=20. It was a sample-size detector. C4 now asks the same
question of the bucket's GROSS and judges it against the leg's own same-size null at the usual 5%
line. Changing a control is only safe if you then re-run everything the control has already
decided, which is what this does. It is also the regression harness those decisions never had:
before today they lived only in BACKTESTING_STACK.md prose.

    python tools/c4_rejudge.py            # the 5-minute cases (NOISE #243/#304, ORB #314)
    python tools/c4_rejudge.py --enguq    # add ENGU-Q #309 (1m ETH master, slow)

Every case prints its verdict, its reasons, and whether C4 is among them, beside the verdict
recorded on 2026-09-09. A line marked FLIPPED is a decision this change moves and must be argued
for on its own evidence - it is not automatically an improvement.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine import ml_keel                                  # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402
from augur_engine.engine import run_backtest                      # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tools"))
from tilt_guard import guard                                      # noqa: E402

WF0, LB0, END = "2016-05-02", "2025-02-11", "2026-08-12"
NQ_MULT, COST = 20.0, 0.533

P243 = {"lookback": 44, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap",
        "side": "Both", "window": "all_day", "flat_eod": True, "skip_holidays": False,
        "stop_mode": "bandwidth", "stop_k": 1.75, "daytype_mode": "skip_bot_short",
        "daytype_lo": 0.2, "daytype_hi": 0.8, "vol_skip_pct": 90.0, "confirm_bars": 1}
P304 = {"lookback": 40, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap",
        "side": "Both", "window": "all_day", "flat_eod": True, "skip_holidays": False,
        "stop_mode": "bandwidth", "stop_k": 1.75, "daytype_mode": "skip_bot_short",
        "daytype_lo": 0.2, "daytype_hi": 0.8, "vol_skip_pct": 95.0, "confirm_bars": 1}
PORB = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
            atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)


def load_leg(fname, params, instrument="NQ", tf="5m", sess="rth", source="db_noadj_rth"):
    arr = load_master_arrays(find_master(instrument, tf, sess, source),
                             date_from="2010-06-07", date_to=END)
    trades = sorted(run_backtest(fname, arrays=arr, params=params, cost_pts=COST,
                                 return_trades=True)["trades"], key=lambda t: t[0])
    idx = pd.DatetimeIndex(arr["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    E = np.array([int(t[0]) for t in trades])
    return arr, trades, E, idx[E], np.array([float(t[2]) for t in trades]) * NQ_MULT


def squeeze_mask(arr, E):
    """The compression condition exactly as KEEL reads it (its own feature matrix, same bar), so
    these cases are the ones the 2026-09-09 decisions were made on. _squeeze60 already reads the
    last COMPLETE hour before the bar; tools/keel_signal_bar_audit.py measured the signal-bar
    re-tag moving 0.25% of tags and no verdict."""
    F, names = ml_keel.keel_features(arr)
    return F[np.clip(E, 0, len(F) - 1), names.index("sq60_on")] > 0


# v12 with its compression multiplier removed: the base the "compression inside v12" case tilts
ml_keel.CFG["_v12_nocomp"] = {k: v for k, v in ml_keel.CFG["v12"].items() if k != "comp"}


def run(cases, perm):
    print(f"{'case':46s} {'was':6s} {'now':6s}  C4?  reasons")
    print("-" * 118)
    flips = []
    for tag, was, kw in cases:
        r = guard(perm=perm, **kw)
        now = "PASS" if r["passed"] else "FAIL"
        c4 = any("C4" in x for x in r["reasons"])
        flag = "" if now == was else "   <<< FLIPPED"
        print(f"{tag:46s} {was:6s} {now:6s}  {'yes' if c4 else ' - ':4s} "
              f"{'; '.join(r['reasons'])[:60]}{flag}")
        for line in r["report"].splitlines():
            if "MONEY" in line or "C4 concentration" in line:
                print("      " + line.strip())
        if now != was:
            flips.append((tag, was, now, r))
    return flips


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perm", type=int, default=2000)
    ap.add_argument("--enguq", action="store_true")
    a = ap.parse_args()

    cases = []
    for rid, fname, params in (("243", "NOISE_1_1_SBS_V90.py", P243),
                               ("304", "NOISE_1_1_NBHD.py", P304)):
        arr, trades, E, ts, pnl = load_leg(fname, params)
        wf = (ts >= pd.Timestamp(WF0)) & (ts < pd.Timestamp(LB0))
        lb = ts >= pd.Timestamp(LB0)
        one = np.ones(len(pnl))
        # exactly the call tools/keel_event_check.py made when v12 was adopted: base = v11 sizes,
        # permutations inside the pre-14:00 window, the Wednesday-morning subgroup, next-day placebo
        pre = ml_keel.pre_statement_mask(arr, E)
        am = np.array([t.hour < 14 for t in ts])
        wed = ts.dayofweek.values == 2
        days = ml_keel.fomc_decision_days()
        alldays = np.array(sorted({t.date() for t in ts}))
        nxt = {alldays[i]: alldays[i + 1] for i in range(len(alldays) - 1)}
        placebo = np.array([nxt.get(t.date()) in days for t in ts]) & am
        k11 = np.asarray(ml_keel.keel_walk(arr, trades, version="v11")["size"], float)
        cases.append((f"NOISE #{rid} - FOMC pre-statement cut (v12)", "PASS",
                      dict(pnl=pnl, ts=ts, base=k11, mask=pre, mult=0.5, wf=wf, lb=lb,
                           window=am, subgroup=wed, placebo_mask=placebo, permute="days",
                           label=f"NOISE #{rid} FOMC cut")))
        sq = squeeze_mask(arr, E)
        cases.append((f"NOISE #{rid} - compression 1.5x, standalone", "PASS",
                      dict(pnl=pnl, ts=ts, base=one, mask=sq, mult=1.5, wf=wf, lb=lb,
                           permute="shift", label=f"NOISE #{rid} compression")))
        was = "PASS" if rid == "304" else "FAIL"     # #243 failed on C4 alone on 2026-09-09
        k12n = np.asarray(ml_keel.keel_walk(arr, trades, version="_v12_nocomp")["size"], float)
        cases.append((f"NOISE #{rid} - compression inside v12", was,
                      dict(pnl=pnl, ts=ts, base=k12n, mask=sq, mult=1.5,
                           wf=wf, lb=lb, permute="shift",
                           label=f"NOISE #{rid} compression in v12")))
        for dow, nmd in ((4, "Friday"),):
            cases.append((f"NOISE #{rid} - {nmd} 1.5x", "FAIL",
                          dict(pnl=pnl, ts=ts, base=one, mask=ts.dayofweek.values == dow,
                               mult=1.5, wf=wf, lb=lb, permute="days",
                               label=f"NOISE #{rid} {nmd}")))

    arr, trades, E, ts, pnl = load_leg("ORB_3_6_R6.py", PORB)
    wf = (ts >= pd.Timestamp(WF0)) & (ts < pd.Timestamp(LB0))
    lb = ts >= pd.Timestamp(LB0)
    one = np.ones(len(pnl))
    cases.append(("ORB #314 - FOMC pre-statement cut", "FAIL",
                  dict(pnl=pnl, ts=ts, base=one, mask=ml_keel.pre_statement_mask(arr, E),
                       mult=0.5, wf=wf, lb=lb, permute="days", label="ORB FOMC cut")))
    cases.append(("ORB #314 - compression 1.5x", "FAIL",
                  dict(pnl=pnl, ts=ts, base=one, mask=squeeze_mask(arr, E), mult=1.5,
                       wf=wf, lb=lb, permute="shift", label="ORB compression")))

    flips = run(cases, a.perm)
    print("-" * 118)
    if not flips:
        print("NO VERDICT MOVES. The rebuilt C4 reproduces every decision the old one made.")
        return 0
    print(f"{len(flips)} VERDICT(S) MOVE - each one needs its own argument:")
    for tag, was, now, r in flips:
        print(f"\n### {tag}: {was} -> {now}")
        for line in r["report"].splitlines():
            if any(k in line for k in ("MONEY", "C4", "C1", "VERDICT")):
                print("   " + line.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
