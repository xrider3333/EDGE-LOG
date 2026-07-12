"""ORB item E — the 1-lot-ride + 1-lot-trail ENSEMBLE (ORB.md §6).

Same #137 entries, two exit plans run as one 2-contract book, blended 50/50 per trade:
  • Leg A (ride) : ORB_3_0_BE  — ride to 4.5R / EOD with the validated 1.0R breakeven (the deploy).
  • Leg B (trail): ORB_3_1     — same entry/stop (1.75), trail the runner on an N-bar low/high.
The two legs share identical entries (same breakout + vol filter + holiday skip), so they align
1:1 by entry bar. Ensemble per-trade PnL = 0.5*(legA_net + legB_net) — the "1-contract-equivalent"
blend, so MAR/DD/PF compare on the same risk basis as each single-lot leg.

Question (ORB.md §6 E): does the blend smooth the curve — MAR/DD between the ride and the trail,
and ideally a better risk-adjusted number than either alone? in-sample + held-out lockbox.
"""
import sys, os
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest, find_master, load_master_arrays, load_strategy

INST, TF, SESS, MULT, FEE = "NQ", "5m", "rth", 20.0, 0.533
FULL = ("2010-06-07", "2026-06-30"); OPT = ("2010-06-07", "2025-06-29"); LB = ("2025-06-30", "2026-06-30")
RIDE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
            breakout_buf=0.0, target_R=4.5, be_after_R=1.0)
TRAIL_BASE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25, atr_filter=0.1,
                  breakout_buf=0.0, partial_exit_R=0.0, target_R=0.0, skip_holidays=True)

MASTER = find_master(INST, TF, SESS)
MOD_A = load_strategy("ORB_3_0_BE.py")   # ride + BE
MOD_B = load_strategy("ORB_3_1.py")      # trail
ARR = {w: load_master_arrays(MASTER, date_from=d0, date_to=d1) for w, (d0, d1) in
       (("full", FULL), ("opt", OPT), ("lb", LB))}


def trades_pt(mod, window, **params):
    """Per-trade net PnL in POINTS (fee applied), keyed by entry bar index."""
    r = run_backtest(mod, arrays=ARR[window], params=params, return_trades=True)
    out = {}
    for t in (r or {}).get("trades", []) or []:
        out[t[0]] = t[2] - FEE
    return out


def metrics(pts_by_key):
    keys = sorted(pts_by_key)
    a = np.array([pts_by_key[k] for k in keys], float)
    if not len(a):
        return dict(net=0, dd=0, mar=0, pf=0, wr=0, n=0)
    net = a.sum() * MULT
    wins = a[a > 0]; losses = a[a < 0]
    gl = -losses.sum()
    pf = (wins.sum() / gl) if gl > 1e-9 else float("inf")
    cum = np.cumsum(a); dd = abs((cum - np.maximum.accumulate(cum)).min()) * MULT
    return dict(net=net, dd=dd, mar=(net / dd if dd else 0), pf=pf,
                wr=100 * len(wins) / len(a), n=len(a))


def blend(A, B):
    keys = set(A) | set(B)
    return {k: 0.5 * (A.get(k, 0.0) + B.get(k, 0.0)) for k in keys}


def show(tag, m):
    print(f"  {tag:26} net ${m['net']:>10,.0f}  DD ${m['dd']:>8,.0f}  MAR {m['mar']:>5.1f}  "
          f"PF {m['pf']:.2f}  WR {m['wr']:.0f}%  n{m['n']:>5}")


print("=== ORB item E — ride + trail ENSEMBLE (NQ 5m rth, #137 base) ===\n")
for w, label in (("full", "FULL 2010-2026"), ("opt", "IN-SAMPLE (opt)"), ("lb", "LOCKBOX (held-out 12mo)")):
    A = trades_pt(MOD_A, w, **RIDE)
    print(f"[{label}]   (ride leg trades: {len(A)})")
    show("Leg A  ride+BE (deploy)", metrics(A))
    for tb in (3, 5, 8):
        B = trades_pt(MOD_B, w, **dict(TRAIL_BASE, trail_bars=tb))
        show(f"Leg B  trail-{tb}", metrics(B))
        show(f"ENSEMBLE ride + trail-{tb}", metrics(blend(A, B)))
    print()
print("Read: does the ensemble land between the ride and the trail on MAR/DD (smoother),")
print("and does any trail-N give a better risk-adjusted blend than the ride-only deploy?")
