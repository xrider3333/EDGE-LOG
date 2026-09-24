"""IS C4 A CONCENTRATION DETECTOR, OR A SAMPLE-SIZE DETECTOR? (2026-09-24)

tools/tilt_guard.py fails a candidate when ONE trade is more than 50% of its LOCKBOX bucket
(check C4, a flat threshold). On 2026-09-09 that single check failed the compression tilt
inside v12 on run #243 while every other check was outstanding - a 0.0% shift null and a
297-trade walk-forward bucket whose worst trade was 8% of the gain. BACKTESTING_STACK.md
flagged the threshold as a SEPARATE decision to be settled on its own evidence, deliberately
not changed in the same breath as a result it would have rescued. This is that evidence.

THE SUSPICION. C4's denominator is the bucket's NET, not its gross. A leg at profit factor 1.5
turns roughly three dollars of gross winnings into one dollar of net, so the biggest trade is
measured against a number about three times smaller than the pile it came out of. Do that on a
20-trade bucket drawn from a fat-tailed instrument and a top-1 share above 50% may be the
ORDINARY case rather than the alarming one - in which case C4 is firing on small samples,
which every lockbox bucket is, and not on concentration.

WHAT THIS MEASURES. For each leg and each stretch, draw many random buckets of size n from
that leg's OWN trades in that stretch (without replacement, no tagging involved at all) and
compute C4's exact statistic on each. That is the null C4 never had: how concentrated does a
bucket of this size from this leg look when nothing is going on? Reported per n: the median
top-1 share, and the share of random buckets the current 50% rule would fail.

    python tools/c4_calibration.py                 # the two NOISE runs
    python tools/c4_calibration.py --orb           # add ORB #314
    python tools/c4_calibration.py --draws 40000   # bootstrap draws per cell (default 20000)

READING IT. If the 50% line fails a large share of random same-size buckets, C4 as written
cannot distinguish a real one-trade artifact from an ordinary small sample, and the honest
replacement is a PERCENTILE against this null - the same standard C2 and C3 already hold
their candidates to. If random buckets almost never cross 50%, the threshold is fine and the
#243 case really was concentrated. This tool does not decide which; it prints the numbers.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays     # noqa: E402
from augur_engine.engine import run_backtest                      # noqa: E402

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

SIZES = (5, 10, 15, 20, 30, 50, 100, 200, 400)


def top1_share(p):
    """C4's exact statistic: the biggest single contributor as a percent of the bucket NET."""
    s = p.sum()
    if abs(s) < 1e-9:
        return np.nan
    srt = np.sort(p)[::-1] if s > 0 else np.sort(p)
    return 100.0 * srt[0] / s


def top1_gross(p):
    """The same question against the bucket's GROSS: what share of all the money that moved
    did the single biggest trade move? Bounded in [0, 100], so its percentiles mean something
    even when the net is near zero - which is exactly where the net version goes to infinity."""
    g = np.abs(p).sum()
    if g < 1e-9:
        return np.nan
    return 100.0 * np.abs(p).max() / g


def null_top1(pnl, n, draws, rng, stat=top1_share):
    """Distribution of a concentration statistic over random same-size buckets from this leg."""
    pnl = np.asarray(pnl, float)
    if len(pnl) <= n:
        return None
    out = np.empty(draws)
    for i in range(draws):
        out[i] = stat(rng.choice(pnl, size=n, replace=False))
    return out[np.isfinite(out)]


def load_leg(fname, params, instrument="NQ", tf="5m", sess="rth"):
    arr = load_master_arrays(find_master(instrument, tf, sess, "db_noadj_rth"),
                             date_from="2010-06-07", date_to=END)
    trades = sorted(run_backtest(fname, arrays=arr, params=params, cost_pts=COST,
                                 return_trades=True)["trades"], key=lambda t: t[0])
    idx = pd.DatetimeIndex(arr["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    ts = idx[[int(t[0]) for t in trades]]
    pnl = np.array([float(t[2]) for t in trades]) * NQ_MULT
    return ts, pnl


def stretches(ts):
    a = ts < pd.Timestamp(WF0)
    b = (ts >= pd.Timestamp(WF0)) & (ts < pd.Timestamp(LB0))
    c = ts >= pd.Timestamp(LB0)
    return (("in-sample", a), ("walk-forward", b), ("lockbox", c))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=20000)
    ap.add_argument("--orb", action="store_true", help="also calibrate on ORB #314")
    a = ap.parse_args()
    rng = np.random.default_rng(20260924)

    legs = [("NOISE #243", "NOISE_1_1_SBS_V90.py", P243, "5m", "rth"),
            ("NOISE #304", "NOISE_1_1_NBHD.py", P304, "5m", "rth")]
    if a.orb:
        legs.append(("ORB #314", "ORB_3_6_R6.py", PORB, "5m", "rth"))

    print("C4 CALIBRATION - how concentrated does an UNTAGGED bucket of size n look?")
    print("Random buckets drawn without replacement from the leg's own trades in that stretch.")
    print("'fails 50%' = the share of those random buckets the current C4 rule would reject.\n")

    rows = []
    for tag, fname, params, tf, sess in legs:
        ts, pnl = load_leg(fname, params, tf=tf, sess=sess)
        gw, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        print("=" * 96)
        print(f"{tag}  n={len(pnl)}  net ${pnl.sum():+,.0f}  gross win ${gw:,.0f}  "
              f"gross loss ${gl:,.0f}  PF {gw / gl if gl else 99:.2f}")
        for nm, m in stretches(ts):
            p = pnl[m]
            if len(p) < 20:
                print("  %-13s n=%d - too few trades to calibrate" % (nm, len(p)))
                continue
            print(f"  {nm:13s} n={len(p):4d}  net ${p.sum():+,.0f}")
            print("      %5s | %8s %8s %9s | %8s %8s %8s"
                  % ("n", "med/NET", "p95/NET", "fails 50%", "med/GROSS", "p95", "p99"))
            for n in SIZES:
                d = null_top1(p, n, a.draws, rng)
                dg = null_top1(p, n, a.draws, rng, stat=top1_gross)
                if d is None or not len(d) or dg is None or not len(dg):
                    continue
                fail = float((d > 50).mean())
                print("      %5d | %7.0f%% %7.0f%% %8.1f%% | %7.0f%% %7.0f%% %7.0f%%"
                      % (n, np.median(d), np.percentile(d, 95), 100 * fail,
                         np.median(dg), np.percentile(dg, 95), np.percentile(dg, 99)))
                rows.append((tag, nm, n, float(np.median(d)), fail,
                             float(np.median(dg)), float(np.percentile(dg, 95)),
                             float(np.percentile(dg, 99))))

    print("\n" + "=" * 96)
    print("WHAT THE 50% LINE DOES, ACROSS EVERY LEG AND STRETCH")
    print("  %5s | %14s %13s | %15s %11s %11s"
          % ("n", "median top-1/NET", "fails 50%", "median top-1/GROSS", "p95", "p99"))
    for n in SIZES:
        sel = [r for r in rows if r[2] == n]
        if not sel:
            continue
        print("  %5d | %13.0f%% %12.1f%% | %14.0f%% %10.0f%% %10.0f%%"
              % (n, np.mean([r[3] for r in sel]), 100 * np.mean([r[4] for r in sel]),
                 np.mean([r[5] for r in sel]), np.mean([r[6] for r in sel]),
                 np.mean([r[7] for r in sel])))
    print("")
    print("The NET column is the rule as it stands. The GROSS column is the same question")
    print("asked of a bounded statistic: its percentiles are usable, the NET one's are not.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
