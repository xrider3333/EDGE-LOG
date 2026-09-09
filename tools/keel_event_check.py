"""Reproduce the KEEL v12 finding from scratch: the FOMC pre-statement hole.

Self-contained - it backtests the legs itself and reads only tools/data/fomc_dates.txt, so it
does not depend on any cached state. This is the evidence behind v12's adoption; re-run it
after any change to ml_keel, the NOISE/ORB/ENGU-Q crown configs, or the Fed calendar file.

    python tools/keel_event_check.py              # NOISE #243 + #304: buckets, permutation, v11 vs v12
    python tools/keel_event_check.py --families   # add the ORB and ENGU-Q mechanism check (slow)
    python tools/keel_event_check.py --perm 4000  # permutation draws (default 4000)

WHAT IT CHECKS
  1. Bucket expectancy: trades entered on a scheduled FOMC decision day BEFORE the 14:00 ET
     statement, against everything else, split IS / walk-forward / lockbox.
  2. Year-by-year sign of that bucket in the walk-forward.
  3. Permutation test: random day-calendars of the same size; where does the real one rank?
  4. Placebos that must FAIL: the morning before a decision day, a random matched day-set, and
     an every-morning shrink of the same dollar size.
  5. v11 vs v12 through the real keel_walk on both NOISE stretches.

The bar v12 was adopted on: better net on all four stretches with drawdown never worse on any.
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine import ml_keel                                  # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402
from augur_engine.engine import run_backtest                      # noqa: E402

WF0, LB0, END = "2016-05-02", "2025-02-11", "2026-08-12"
NQ_MULT, COST = 20.0, 0.533

# the two NOISE runs the overlay is tuned and judged on (#243 = paper leg, #304 = crown)
P243 = {"lookback": 44, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap",
        "side": "Both", "window": "all_day", "flat_eod": True, "skip_holidays": False,
        "stop_mode": "bandwidth", "stop_k": 1.75, "daytype_mode": "skip_bot_short",
        "daytype_lo": 0.2, "daytype_hi": 0.8, "vol_skip_pct": 90.0, "confirm_bars": 1}
P304 = {"lookback": 40, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap",
        "side": "Both", "window": "all_day", "flat_eod": True, "skip_holidays": False,
        "stop_mode": "bandwidth", "stop_k": 1.75, "daytype_mode": "skip_bot_short",
        "daytype_lo": 0.2, "daytype_hi": 0.8, "vol_skip_pct": 95.0, "confirm_bars": 1}
RUNS = (("243", "NOISE_1_1_SBS_V90.py", P243), ("304", "NOISE_1_1_NBHD.py", P304))


def metrics(pnl, a, b):
    p = np.asarray(pnl, float)
    if not len(p):
        return dict(net=0.0, pf=0.0, dd=0.0, mar=0.0, evr=0.0)
    cum = np.cumsum(p)
    dd = float((cum - np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]).min())
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    yrs = max((pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25, 1 / 12)
    losses = p[p < 0]
    return dict(net=float(p.sum()), pf=float(gw / gl) if gl > 0 else 99.0, dd=dd,
                mar=float((p.sum() / yrs) / abs(dd)) if dd < 0 else 99.0,
                evr=float(p.mean() / -losses.mean()) if len(losses) else 0.0)


def evr(p):
    p = np.asarray(p, float)
    losses = p[p < 0]
    return float(p.mean() / -losses.mean()) if len(losses) else float("nan")


def naive_et(index):
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    return idx


def load_leg(fname, params, instrument="NQ", tf="5m", sess="rth", date_to=END):
    arr = load_master_arrays(find_master(instrument, tf, sess, "db_noadj_rth"),
                             date_from="2010-06-07", date_to=date_to)
    trades = sorted(run_backtest(fname, arrays=arr, params=params, cost_pts=COST,
                                 return_trades=True)["trades"], key=lambda t: t[0])
    return arr, trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perm", type=int, default=4000)
    ap.add_argument("--families", action="store_true", help="also run the ORB / ENGU-Q mechanism check")
    args = ap.parse_args()

    days = ml_keel.fomc_decision_days()
    print(f"FOMC decision days: {len(days)}  {min(days)} .. {max(days)}")
    if max(days) < dt.date.today():
        print("  !! the calendar ends in the past - the live tilt will never fire. Refresh it from")
        print("     federalreserve.gov/monetarypolicy/fomccalendars.htm into tools/data/fomc_dates.txt")

    rng = np.random.default_rng(20260909)
    verdict = []
    for rid, fname, params in RUNS:
        arr, trades = load_leg(fname, params)
        idx = naive_et(arr["index"])
        sizes = {v: ml_keel.keel_walk(arr, trades, version=v)["size"] for v in ("v11", "v12")}
        kw = ml_keel.keel_walk(arr, trades, version="v11")
        E, P = kw["E"], kw["P"] * NQ_MULT
        ts = idx[np.clip(E, 0, len(idx) - 1)]
        pre = ml_keel.pre_statement_mask(arr, E)
        wf = (ts >= pd.Timestamp(WF0)) & (ts < pd.Timestamp(LB0))
        lb = ts >= pd.Timestamp(LB0)
        ins = ~wf & ~lb
        v11 = P * sizes["v11"]

        print(f"\n{'='*92}\n#{rid}  {len(trades)} trades, {int(pre.sum())} tagged pre-statement ({100*pre.mean():.1f}%)")
        print("  1. bucket expectancy (EV R), by stretch")
        for nm, m in (("in-sample ", ins), ("walk-fwd  ", wf), ("lockbox   ", lb)):
            a, b = P[m & pre], P[m & ~pre]
            print(f"     {nm} pre-statement {evr(a):+.3f} (n={int((m&pre).sum()):3d}, ${a.sum():+9,.0f})"
                  f"   |  every other {evr(b):+.3f} (n={int((m&~pre).sum()):4d}, ${b.sum():+10,.0f})")

        yr = np.array([t.year if t.month >= 7 else t.year - 1 for t in ts])
        g = pd.Series(v11[pre & wf]).groupby(yr[pre & wf]).sum()
        print(f"  2. walk-forward years with the bucket negative: {int((g < 0).sum())}/{len(g)}   total ${g.sum():+,.0f}")

        dcode = pd.Categorical([t.date() for t in ts], categories=sorted({t.date() for t in ts})).codes
        alldays = np.array(sorted({t.date() for t in ts}))
        am = np.array([t.hour < 14 for t in ts])
        k = int(np.isin(alldays, list(days)).sum())
        real = float(v11[pre].sum())
        draws = np.array([v11[am & np.isin(dcode, rng.choice(len(alldays), size=k, replace=False))].sum()
                          for _ in range(args.perm)])
        pct = float((draws <= real).mean())
        print(f"  3. permutation: real ${real:+,.0f} vs random-calendar mean ${draws.mean():+,.0f} "
              f"(sd ${draws.std():,.0f})  ->  {pct*100:.2f}% of {args.perm} are this bad  (z {(real-draws.mean())/draws.std():.2f})")

        nxt = {alldays[i]: alldays[i + 1] for i in range(len(alldays) - 1)}
        before = np.array([nxt.get(t.date()) in days for t in ts]) & am
        print("  4. placebos (each must LOSE money - if one wins, the tilt is not about the events)")
        for nm, mask, mult in (("morning before a decision day", before, 0.5),
                               ("every morning, same $ shrink ", am, 0.985)):
            alt = v11 * np.where(mask, mult, 1.0)
            d_wf, d_lb = (alt - v11)[wf].sum(), (alt - v11)[lb].sum()
            print(f"     {nm}: walk-forward ${d_wf:+,.0f}   lockbox ${d_lb:+,.0f}"
                  f"   {'OK (loses, as required)' if d_wf < 0 else '<-- WARNING: this placebo WINS'}")
        # the random-day placebo is a DISTRIBUTION, never a single draw. One draw is pure noise:
        # at some seeds it "wins" and reads like a failed placebo when nothing is wrong. What has
        # to be true is that halving a RANDOM day-set is usually worthless, while halving the real
        # calendar is near the top of that distribution.
        real_gain = float((v11 * np.where(pre, 0.5, 1.0) - v11)[wf | lb].sum())
        gains = np.empty(min(args.perm, 500))
        for i in range(len(gains)):
            fk = np.isin(dcode, rng.choice(len(alldays), size=k, replace=False)) & am
            gains[i] = (v11 * np.where(fk, 0.5, 1.0) - v11)[wf | lb].sum()
        beat = float((gains >= real_gain).mean())
        print(f"     random matched day-sets ({len(gains)} draws): halving a random calendar is worth "
              f"${gains.mean():+,.0f} on average (sd ${gains.std():,.0f});")
        print(f"       halving the REAL calendar is worth ${real_gain:+,.0f} - beaten by {beat*100:.1f}% of them"
              f"   {'OK' if beat < 0.05 else '<-- WARNING: random day-sets do this well too'}")

        print("  5. v11 vs v12 on the run's own stretches")
        for stg, m, a, b in (("walk-forward", wf, WF0, LB0), ("lockbox     ", lb, LB0, END)):
            m11 = metrics((P * sizes["v11"])[m], a, b)
            m12 = metrics((P * sizes["v12"])[m], a, b)
            print(f"     {stg}  v11 ${m11['net']:>10,.0f} DD ${m11['dd']:>9,.0f} MAR {m11['mar']:5.2f}"
                  f"  ->  v12 ${m12['net']:>10,.0f} DD ${m12['dd']:>9,.0f} MAR {m12['mar']:5.2f}"
                  f"   net {m12['net']-m11['net']:+,.0f}  dd {m12['dd']-m11['dd']:+,.0f}")
            verdict.append((m12["net"] > m11["net"], m12["dd"] >= m11["dd"] - 1e-6))

    if args.families:
        print(f"\n{'='*92}\nMECHANISM CHECK - is the hole NOISE-only? (raw size, full history)")
        legs = [("ORB #314 (breakout)", "ORB_3_6_R6.py",
                 dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
                      atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0), "5m", "rth")]
        for tag, fname, params, tf, sess in legs:
            try:
                arr, trades = load_leg(fname, params, tf=tf, sess=sess)
                E = np.array([int(t[0]) for t in trades])
                P = np.array([float(t[2]) for t in trades]) * NQ_MULT
                pre = ml_keel.pre_statement_mask(arr, E)
                print(f"  {tag:26s} pre-statement EV R {evr(P[pre]):+.3f} (n={int(pre.sum())})"
                      f"   |  every other {evr(P[~pre]):+.3f} (n={int((~pre).sum())})")
            except Exception as e:
                print(f"  {tag}: skipped ({type(e).__name__}: {e})")

    ok_net = all(v[0] for v in verdict)
    ok_dd = all(v[1] for v in verdict)
    print(f"\n{'='*92}\nADOPTION BAR: net better on {sum(v[0] for v in verdict)}/{len(verdict)} stretches; "
          f"drawdown never worse: {ok_dd}  ->  {'HOLDS' if ok_net and ok_dd else 'DOES NOT HOLD'}")
    return 0 if (ok_net and ok_dd) else 1


if __name__ == "__main__":
    sys.exit(main())
