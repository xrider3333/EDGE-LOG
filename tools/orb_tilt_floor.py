"""ORB — the HYBRID: tilt most trades, but SKIP the truly hopeless ones (owner idea, item 197).

Today there are two ways to spend a model score:
    FILTER  below the cut-off the trade is deleted.        (loses big winners it was wrong about)
    TILT    every trade is taken, only re-sized.           (still pays for hopeless trades)

The owner's idea is the obvious middle: tilt normally, but below some LOW floor stop paying
entirely. The risk is equally obvious - the floor is a free parameter, and picking it by looking
at the held-out year would be exactly the curve-fitting the whole validation stack exists to stop.

So the floor is chosen on PRE-LOCKBOX data ONLY, by a rule fixed before the run:
    choose the floor with the best PRE-LOCKBOX MAR; ties -> the LOWEST floor (skip less).
The lockbox is then reported ONCE for that choice, as a check, never as the chooser. Every other
floor's lockbox number is printed too - clearly marked HINDSIGHT - so the owner can see whether
the pre-lockbox pick was lucky or sound, which is the only honest way to read a new free knob.

Floors swept: 0 (pure tilt) .30 .35 .40 .45 .50 (=filter-like). Tilt shape and capital-matching
are unchanged from SS4.25 so the only moving part is the floor.

Usage:  python tools/orb_tilt_floor.py [NQ|ES]
"""
import sys, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.ml_gate import gate_trades
from augur_engine.sizing import trade_features, mar

INST = (sys.argv[1] if len(sys.argv) > 1 else "NQ").upper()
MULT = {"NQ": 20.0, "ES": 50.0}.get(INST, 20.0)
FEE = 5.66 / MULT + 0.25
STRAT = "ORB_3_0_ENS.py"
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
           breakout_buf=0.0, be_after_R=1.0, target_R=4.0, trail_bars=12, flat_eod=True)
DFROM, DTO, LB_FROM = "2010-06-07", "2026-06-30", "2025-06-30"
MODELS = ("rf", "tree", "et")
FLOORS = (0.0, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65)
CAP = 3.0


def _metrics(pnl, size):
    net = size * (pnl - FEE) * MULT
    live = size > 1e-9
    if not len(net):
        return None
    cum = np.cumsum(net)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    return {"net": float(net.sum()), "dd": dd, "mar": mar(net.sum(), dd),
            "n": int(live.sum())}


def main():
    m = find_master(INST, "5m", "rth")
    arrays = load_master_arrays(m, DFROM, DTO)
    res = run_backtest(STRAT, instrument=INST, timeframe="5m", session="rth", params=CFG,
                       cost_pts=0.0, date_from=DFROM, date_to=DTO, return_trades=True)
    T = sorted(res["trades"], key=lambda t: int(t[0]))
    idx = np.asarray(arrays["index"]); nb = len(idx)
    ts = np.array([idx[min(int(t[0]), nb - 1)] for t in T])
    pnl, risk, _e, _s = trade_features(T, arrays, CFG["stop_frac"], CFG["or_bars"])
    _tz = getattr(pd.Timestamp(idx[-1]), "tzinfo", None)
    lb0 = pd.Timestamp(LB_FROM)
    if _tz is not None and lb0.tzinfo is None:
        lb0 = lb0.tz_localize(_tz)
    pre, lb = ts < lb0, ts >= lb0

    print(f"=== ORB item 197 — HYBRID: tilt with a SKIP FLOOR ({INST} 5m RTH) ===")
    print(f"window {DFROM} -> {DTO} · {len(T)} trades · pre {int(pre.sum())} · LB {int(lb.sum())}")
    base = _metrics(pnl[pre], np.ones(int(pre.sum()))), _metrics(pnl[lb], np.ones(int(lb.sum())))
    print(f"no filter, flat: pre ${base[0]['net']:,.0f} (MAR {base[0]['mar']:.1f}) · "
          f"LB ${base[1]['net']:,.0f} (MAR {base[1]['mar']:.1f})")

    for mdl in MODELS:
        g = gate_trades(arrays, [(int(t[0]), int(t[1]), float(t[2]) - FEE) for t in T],
                        model=mdl, threshold=0.0, min_history=30, refit_every=25, seed=42)
        p = np.asarray(g.get("prob"), float) if g and g.get("prob") is not None else None
        if p is None or len(p) != len(T):
            print(f"  ! {mdl}: no scores"); continue
        pf = np.where(np.isnan(p), 0.5, p)
        base_w = np.clip(1.0 + 4.0 * (pf - 0.50), 0.25, 3.0)
        base_w = np.where(np.isnan(p), 1.0, base_w)

        print(f"\n  {mdl}")
        print(f"    {'floor':>6}{'kept pre':>10}{'PRE $':>12}{'PRE MAR':>9}"
              f"{'| LB $':>12}{'LB MAR':>8}{'LB DD':>10}  {'(LB = hindsight)':>0}")
        rows = []
        for fl in FLOORS:
            w = np.where(pf < fl, 0.0, base_w) if fl > 0 else base_w.copy()
            if not (w[pre] > 0).any():
                continue
            denom = float((w[pre] * risk[pre]).sum())
            if denom <= 1e-12:
                continue
            k = float(risk[pre].sum()) / denom
            size = np.minimum(w * k, CAP)
            a, c = _metrics(pnl[pre], size[pre]), _metrics(pnl[lb], size[lb])
            rows.append((fl, a, c))
            print(f"    {fl:>6.2f}{a['n']:>10}{a['net']:>12,.0f}{a['mar']:>9.1f}"
                  f"{c['net']:>12,.0f}{c['mar']:>8.1f}{c['dd']:>10,.0f}")
        if rows:
            best = max(rows, key=lambda r: (r[1]["mar"], -r[0]))
            fl, a, c = best
            print(f"    -> PRE-LOCKBOX pick: floor {fl:.2f}  (pre MAR {a['mar']:.1f})   "
                  f"its LB: ${c['net']:,.0f}, MAR {c['mar']:.1f}")
            bestlb = max(rows, key=lambda r: r[2]["mar"])
            if abs(bestlb[0] - fl) > 1e-9:
                print(f"       (hindsight-best floor would have been {bestlb[0]:.2f} at LB MAR "
                      f"{bestlb[2]['mar']:.1f} — the gap is the cost of choosing honestly)")


if __name__ == "__main__":
    main()
