"""NOISE #422 + KEEL v12 - the combination the owner wants live, never measured before (2026-09-27, MANAGER).

Same round-60 tape and stretches as tools/keel_bag_check.py (NQ 5m RTH no-adj, 2010-06-07 .. 2026-09-16,
cost 0.533, walk-forward 2016-06-30 .. 2025-07-16, lockbox from 2025-07-16), leak-fixed KEEL v12 (engine
at 85be1b8 or later). Rows, side by side:
    #382 alone | #382 + KEEL seed 42 (the live stack) | #382 + KEEL 7-seed bag
    #422 alone | #422 + KEEL seed 42                  | #422 + KEEL 7-seed bag
#422 = NOISE_1_8_CT304H.py gate_len 20, gate_ratio 1.15, tilt_mult 1.75 (run #422's best_params).
Per stretch: net $, ROC %/yr on $100k, Sortino (engine), max drawdown, return per drawdown; plus the
largest contract multiple reached (plugin size x KEEL size) and the share of trades at 3x or more -
KEEL's own hourly-squeeze 1.5x lands on top of #422's hourly-squeeze 1.75x.

    python tools/keel_422_stack_check.py --walk     # #422 KEEL walks, cached (~20 min)
    python tools/keel_422_stack_check.py            # the table (reads the #382 cache from keel_bag_check)
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import keel_bag_check as B                                            # noqa: E402
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

P422 = dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75)
BAG = B.BAGS[0]


def tape():
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=B.LAST)
    idx = pd.DatetimeIndex(A["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    return A, idx


def plugin_sizes(r, n):
    s = r.get("trade_sizes")
    return np.asarray(s, float) if s is not None and len(s) == n else np.ones(n)


def walk():
    A, idx = tape()
    r = run_backtest(B.mod("NOISE_1_8_CT304H.py"), arrays=A, params=P422, cost_pts=B.COST, return_trades=True)
    T = sorted(r["trades"], key=lambda z: z[0])
    F = K.keel_features(A)
    out = {}
    for s in (42,) + BAG:
        kw = K.keel_walk(A, T, feats=F, version="v12", seed=s)
        out["s%d" % s] = np.asarray(kw["size"], float)
        print(f"#422 seed {s}: mean KEEL size {out['s%d' % s].mean():.4f}", flush=True)
    out["P"] = kw["P"] * B.MULT
    out["d"] = np.array([idx[max(int(e) - 1, 0)].value for e in kw["E"]], np.int64)
    out["end"] = np.array([idx[-1].value], np.int64)
    out["plug"] = plugin_sizes(r, len(T))[np.argsort([t[0] for t in r["trades"]], kind="stable")]
    os.makedirs(B.CACHE, exist_ok=True)
    np.savez(os.path.join(B.CACHE, "leg422.npz"), **out)
    print("cached leg422")


def main():
    A, idx = tape()
    r382 = run_backtest(B.mod("NOISE_1_8_CT304.py"), arrays=A, params=B.LEGS["382"][2], cost_pts=B.COST,
                        return_trades=True)
    plug382 = plugin_sizes(r382, len(r382["trades"]))[np.argsort([t[0] for t in r382["trades"]], kind="stable")]
    rows = []
    for leg, plug in (("382", plug382), ("422", None)):
        z = np.load(os.path.join(B.CACHE, "leg%s.npz" % leg))
        d, P, end = pd.DatetimeIndex(z["d"]), z["P"], pd.Timestamp(int(z["end"][0]))
        plug = z["plug"] if plug is None else plug
        assert len(plug) == len(P), "plugin sizes do not line up with the cached trades"
        bag = np.mean([z["s%d" % s] for s in BAG], axis=0)
        for lab, k in (("alone", np.ones(len(P))), ("+ KEEL seed 42", z["s42"]), ("+ KEEL 7-seed bag", bag)):
            w, lb = B.both(d, P * k, end)
            mult = plug * k
            rows.append((f"NOISE #{leg} {lab}", w, lb, float(mult.max()), float((mult >= 3.0 - 1e-9).mean())))
    print("Round-60 tape; WF 2016-06-30..2025-07-16, LB 2025-07-16..2026-09-16; ROC on $100k; leak-fixed KEEL v12")
    print(f"{'':28s} {'WF net':>9s} {'ROC':>6s} {'Sort':>5s} {'DD':>7s} {'r/DD':>5s} | {'LB net':>8s} {'ROC':>6s}"
          f" {'Sort':>5s} {'DD':>7s} {'r/DD':>5s} | {'max x':>5s} {'>=3x':>6s}")
    for lab, w, lb, mx, s3 in rows:
        print(f"{lab:28s} {w['net']:>9,.0f} {w['roc']:>6.1f} {w['sortino']:>5.2f} {w['dd']:>7,.0f} {w['mar']:>5.2f} | "
              f"{lb['net']:>8,.0f} {lb['roc']:>6.1f} {lb['sortino']:>5.2f} {lb['dd']:>7,.0f} {lb['mar']:>5.2f} | "
              f"{mx:>5.2f} {100 * s3:>5.1f}%")
    bw = max(rows, key=lambda x: x[1]["net"]); bl = max(rows, key=lambda x: x[2]["net"])
    print(f"\nHighest WF net: {bw[0]} (${bw[1]['net']:,.0f}).  Highest LB net: {bl[0]} (${bl[2]['net']:,.0f}).")
    return 0


if __name__ == "__main__":
    sys.exit(walk() if "--walk" in sys.argv else main())
