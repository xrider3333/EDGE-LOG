"""What KEEL v12 adds on NOISE #422 - read against docs/PREREG_keel_422_parts_2026-09-27.md (bar 10dedef5).

Arms on the round-60 tape (tools/keel_bag_check.py stretches, leak-fixed engine):
  A0 #422 alone | A1 + KEEL v12 7-seed bag | A2 + KEEL v12 without its compression 1.5x, 7-seed bag
  A3 + fixed v12 tilts only (compression 1.5x, Friday 1.5x, cap 3, FOMC pre-statement 0.5x), no model
  A4 + fixed tilts without compression (Friday 1.5x, FOMC 0.5x)

    python tools/keel_422_parts_check.py --walk    # A2's seven walks, cached (~20 min)
    python tools/keel_422_parts_check.py           # the table and the pre-registered H1 / H2 / veto
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import keel_bag_check as B                                            # noqa: E402
import keel_422_stack_check as S                                      # noqa: E402
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

K.CFG["_v12_nocomp"] = {k: v for k, v in K.CFG["v12"].items() if k != "comp"}
EVENT = dict(K.CFG["v12"]["event"])
DOW = {k: v for k, v in K.CFG["v12"]["dow"].items() if k != "cap"}


def trades():
    A, idx = S.tape()
    r = run_backtest(B.mod("NOISE_1_8_CT304H.py"), arrays=A, params=S.P422, cost_pts=B.COST, return_trades=True)
    return A, idx, sorted(r["trades"], key=lambda z: z[0])


def walk():
    A, idx, T = trades()
    F = K.keel_features(A)
    out = {}
    for s in S.BAG:
        out["s%d" % s] = np.asarray(K.keel_walk(A, T, feats=F, version="_v12_nocomp", seed=s)["size"], float)
        print(f"A2 seed {s}: mean size {out['s%d' % s].mean():.4f}", flush=True)
    np.savez(os.path.join(B.CACHE, "leg422_nocomp.npz"), **out)
    print("cached leg422_nocomp")


def main():
    A, idx, T = trades()
    z = np.load(os.path.join(B.CACHE, "leg422.npz"))
    zn = np.load(os.path.join(B.CACHE, "leg422_nocomp.npz"))
    d, P, end, plug = pd.DatetimeIndex(z["d"]), z["P"], pd.Timestamp(int(z["end"][0])), z["plug"]
    assert len(T) == len(P), "trade list moved since the #422 cache was built"
    cap = float(K.CFG["v12"]["comp"]["cap"])
    arms = {
        "A0 #422 alone": np.ones(len(P)),
        "A1 + KEEL v12 (7-seed)": np.mean([z["s%d" % s] for s in S.BAG], axis=0),
        "A2 + KEEL v12 no squeeze (7-seed)": np.mean([zn["s%d" % s] for s in S.BAG], axis=0),
        "A3 + fixed tilts only": K.compression_sizes(A, T, mult=1.5, dow=DOW, cap=cap, event=EVENT),
        "A4 + fixed tilts, no squeeze": K.compression_sizes(A, T, mult=1.0, dow=DOW, cap=cap, event=EVENT),
    }
    res = {}
    print("NOISE #422 on the round-60 tape; WF 2016-06-30..2025-07-16, LB 2025-07-16..2026-09-16; ROC on $100k")
    print(f"{'':34s} {'WF net':>9s} {'ROC':>6s} {'Sort':>5s} {'DD':>7s} {'r/DD':>5s} | {'LB net':>8s} {'ROC':>6s}"
          f" {'Sort':>5s} {'DD':>7s} {'r/DD':>5s} | max x")
    for lab, k in arms.items():
        w, lb = B.both(d, P * k, end)
        res[lab] = (w, lb)
        print(f"{lab:34s} {w['net']:>9,.0f} {w['roc']:>6.1f} {w['sortino']:>5.2f} {w['dd']:>7,.0f} {w['mar']:>5.2f} | "
              f"{lb['net']:>8,.0f} {lb['roc']:>6.1f} {lb['sortino']:>5.2f} {lb['dd']:>7,.0f} {lb['mar']:>5.2f} | "
              f"{float((plug * k).max()):.2f}")
    a0, a1, a2, a3, a4 = (res[k] for k in arms)
    h1 = a2[0]["mar"] >= 1.03 * a1[0]["mar"] and a2[0]["sortino"] >= a1[0]["sortino"]
    ref, fixed = (a2, a4) if h1 else (a1, a3)
    h2 = fixed[0]["mar"] >= ref[0]["mar"] and fixed[0]["sortino"] >= 0.97 * ref[0]["sortino"]
    print(f"\nH1 drop KEEL's squeeze on #422 ...... {'HOLDS' if h1 else 'does not hold'}")
    print(f"H2 learned part adds nothing ........ {'HOLDS' if h2 else 'does not hold'} "
          f"({'A4 vs A2' if h1 else 'A3 vs A1'})")
    ok = {lab: r for lab, r in res.items() if not lab.startswith("A0") and r[1]["mar"] >= a0[1]["mar"]}
    print("Lockbox veto clears: " + (", ".join(ok) if ok else "none"))
    if ok:
        best = max(ok, key=lambda x: ok[x][0]["mar"])
        print(f"RECOMMENDATION (pre-registered rule): {best}")
    else:
        print("RECOMMENDATION (pre-registered rule): none clears the lockbox veto")
    return 0


if __name__ == "__main__":
    sys.exit(walk() if "--walk" in sys.argv else main())
