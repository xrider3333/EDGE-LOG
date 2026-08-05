"""ORB — does the ML size-tilt STACK with the three validated size levers? (item 186)

ORB's biggest wins came from stacking size rules, not from finding new entries: risk-parity alone
lifted lockbox MAR 6.9 -> 8.9 (SS4.7), x time-tilt -> 12.7 (SS4.10), x short-tilt -> 15.0 (SS4.11).
The gate tilt (SS4.25) is a FOURTH size rule built from a completely different signal - a model's
per-trade win probability rather than a structural fact about the trade. If it is genuinely
independent it should multiply through like the others did; if it is just re-discovering
"morning trades and shorts are better" it will add nothing on top.

That is the whole question here, and it is the cheapest big-PnL question left on ORB.

PRE-REGISTERED, nothing tuned after the fact:
  levers      risk-parity (size ~ 1/stop, 3x cap) x time-tilt (morning x2) x side-tilt
              (long x0.5 / short x1.5) - the exact SS5.6 deploy stack, weights unchanged
  gate tilt   linear clip(1 + 4(p - .5), .25, 3) on the gate's own causal walk - the SS4.25
              shape, unchanged
  match       every row capital-matched to the flat size-1 total dollar risk, matched on the
              PRE-LOCKBOX slice only, then that same constant applied to the lockbox
  cap         3 contracts final, the rp-cap3 doctrine
  BAR         the stack x tilt row must beat BOTH parents on lockbox MAR to count as stacking;
              beating only one is a substitution, not a stack.

Usage:  python tools/orb_tilt_stack.py [NQ|ES]
"""
import sys, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.ml_gate import gate_trades
from augur_engine.sizing import trade_features, sizing_weights, mar

INST = (sys.argv[1] if len(sys.argv) > 1 else "NQ").upper()
MULT = {"NQ": 20.0, "ES": 50.0}.get(INST, 20.0)
FEE = 5.66 / MULT + 0.25
STRAT = "ORB_3_0_ENS.py"
CFG = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
           breakout_buf=0.0, be_after_R=1.0, target_R=4.0, trail_bars=12, flat_eod=True)
DFROM, DTO, LB_FROM = "2010-06-07", "2026-06-30", "2025-06-30"
WF_FROM = "2016-06-24"                       # the fold boundary run #195 reports
MODELS = ("rf", "tree")                      # the two best tilt families from SS4.25
CAP = 3.0


def _tilt(p):
    return np.where(np.isnan(p), 1.0, np.clip(1.0 + 4.0 * (p - 0.50), 0.25, 3.0))


def _metrics(pnl, size):
    net = size * (pnl - FEE) * MULT
    if not len(net):
        return None
    cum = np.cumsum(net)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(net[net > 0].sum()); gl = float(-net[net < 0].sum())
    return {"net": float(net.sum()), "n": int(len(net)), "dd": dd,
            "mar": mar(net.sum(), dd),
            "pf": (gw / gl) if gl > 1e-9 else float("inf"),
            "max_sz": float(size.max())}


def main():
    m = find_master(INST, "5m", "rth")
    arrays = load_master_arrays(m, DFROM, DTO)
    res = run_backtest(STRAT, instrument=INST, timeframe="5m", session="rth", params=CFG,
                       cost_pts=0.0, date_from=DFROM, date_to=DTO, return_trades=True)
    T = sorted(res["trades"], key=lambda t: int(t[0]))
    idx = np.asarray(arrays["index"]); nb = len(idx)
    ts = np.array([idx[min(int(t[0]), nb - 1)] for t in T])
    pnl, risk, ebar, side = trade_features(T, arrays, CFG["stop_frac"], CFG["or_bars"])

    _tz = getattr(pd.Timestamp(idx[-1]), "tzinfo", None)
    def _T(s):
        x = pd.Timestamp(s)
        return x.tz_localize(_tz) if (_tz is not None and x.tzinfo is None) else x
    lb0, wf0 = _T(LB_FROM), _T(WF_FROM)
    m_is, m_wf, m_lb = (ts < wf0), (ts >= wf0) & (ts < lb0), (ts >= lb0)
    pre = ~m_lb

    print(f"=== ORB item 186 — does the ML tilt STACK with the deploy size levers? ===")
    print(f"{INST} 5m RTH · {DFROM} -> {DTO} · master {m['filename']}")
    print(f"{len(T)} trades · IS {int(m_is.sum())} · WF {int(m_wf.sum())} · LB {int(m_lb.sum())}")

    # the SS5.6 deploy stack (structural levers only)
    w_stack = sizing_weights(risk, ebar, side, risk_parity=True, rp_cap=3.0,
                             time_tilt=True, long_w=0.5, short_w=1.5)

    rows = [("flat 1 lot", np.ones(len(T))),
            ("deploy stack (rp x time x side)", w_stack)]
    for mdl in MODELS:
        g = gate_trades(arrays, [(int(t[0]), int(t[1]), float(t[2]) - FEE) for t in T],
                        model=mdl, threshold=0.0, min_history=30, refit_every=25, seed=42)
        p = np.asarray(g.get("prob"), float) if g and g.get("prob") is not None else None
        if p is None or len(p) != len(T):
            print(f"  ! {mdl} produced no usable scores, skipped")
            continue
        wt = _tilt(p)
        rows.append((f"gate tilt only ({mdl})", wt))
        rows.append((f"STACK x gate tilt ({mdl})", w_stack * wt))

    hdr = (f"\n{'row':<32}{'IS $':>11}{'WF $':>12}{'LB $':>11}{'LB MAR':>8}"
           f"{'LB DD':>10}{'LB PF':>7}{'maxSz':>7}")
    print(hdr); print("-" * len(hdr))
    out = {}
    for name, w in rows:
        denom = float((w[pre] * risk[pre]).sum())
        if denom <= 1e-12:
            continue
        k = float(risk[pre].sum()) / denom          # capital-match on PRE-LOCKBOX only
        size = np.minimum(w * k, CAP)
        a, b, c = _metrics(pnl[m_is], size[m_is]), _metrics(pnl[m_wf], size[m_wf]), \
                  _metrics(pnl[m_lb], size[m_lb])
        out[name] = c
        print(f"{name:<32}{a['net']:>11,.0f}{b['net']:>12,.0f}{c['net']:>11,.0f}"
              f"{c['mar']:>8.1f}{c['dd']:>10,.0f}{min(c['pf'],99):>7.2f}{c['max_sz']:>7.2f}")

    print("\n--- pre-registered bar: STACK x TILT must beat BOTH parents on lockbox MAR ---")
    st = out.get("deploy stack (rp x time x side)")
    for mdl in MODELS:
        both = out.get(f"STACK x gate tilt ({mdl})")
        only = out.get(f"gate tilt only ({mdl})")
        if not (both and only and st):
            continue
        ok = both["mar"] > st["mar"] and both["mar"] > only["mar"]
        print(f"  {mdl:<6} combined {both['mar']:>6.1f}  vs stack {st['mar']:>6.1f} / "
              f"tilt {only['mar']:>6.1f}   -> {'STACKS' if ok else 'does NOT stack'}")


if __name__ == "__main__":
    main()
