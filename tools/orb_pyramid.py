"""ORB item U — pyramid-at-+R vs the at-entry ensemble vs single-lot.

All on the frozen #137+BE base, 2-contract-capital accounting (50/50 blend; lot B = $0 when
unfilled), optimize window + lockbox, MAR-ranked. Usage: python tools/orb_pyramid.py
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from augur_engine.engine import run_backtest, find_master, load_master_arrays, load_strategy

MULT, FEE = 20.0, 0.533
FULL = ("2010-06-07", "2026-06-30")
OPT  = ("2010-06-07", "2025-06-29")
LB   = ("2025-06-30", "2026-06-30")
BASE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
            atr_filter=0.1, breakout_buf=0.0, target_R=4.5, be_after_R=1.0)

print("loading master + windows ...", flush=True)
MASTER = find_master("NQ", "5m", "rth")
ARR = {w: load_master_arrays(MASTER, date_from=d0, date_to=d1) for w, (d0, d1) in
       (("full", FULL), ("opt", OPT), ("lb", LB))}
PYR = load_strategy("ORB_3_0_PYR.py")
ENS = load_strategy("ORB_3_0_ENS.py")
BE  = load_strategy("ORB_3_0_BE.py")

def kpi(mod, window, **p):
    r = run_backtest(mod, arrays=ARR[window], params=dict(BASE, **p), cost_pts=FEE, return_trades=False)
    if not r:
        return dict(net=0, dd=0, pf=0, mar=0, n=0)
    net = r["total_pnl"] * MULT; dd = abs(r.get("max_drawdown", 0) or 0) * MULT
    return dict(net=net, dd=dd, pf=r.get("profit_factor", 0) or 0,
                mar=(net / dd if dd else 0), n=int(r.get("num_trades", 0) or 0))

hdr = (f"{'book':>26} | {'IS net$':>10} {'IS DD$':>8} {'IS MAR':>6} | "
       f"{'LB net$':>9} {'LB DD$':>7} {'LB MAR':>6} {'LB PF':>5}")
print("\n" + "=" * len(hdr)); print(hdr); print("-" * len(hdr))
def row(label, mod, **p):
    o = kpi(mod, "opt", **p); l = kpi(mod, "lb", **p)
    print(f"{label:>26} | {o['net']:>10,.0f} {o['dd']:>8,.0f} {o['mar']:>6.1f} | "
          f"{l['net']:>9,.0f} {l['dd']:>7,.0f} {l['mar']:>6.1f} {l['pf']:>5.2f}")

row("single-lot (deploy)", BE)
row("ensemble tgt4.5/tr5", ENS, trail_bars=5)
for pat in (0.5, 1.0, 1.5, 2.0):
    row(f"pyramid @{pat}R / tr5", PYR, pyramid_at_R=pat, trail_bars=5)
for tb in (3, 8):
    row(f"pyramid @1.0R / tr{tb}", PYR, pyramid_at_R=1.0, trail_bars=tb)
print("-" * len(hdr))
print("All rows 2-contract-capital blend except single-lot (1 contract; MAR is scale-free).")
print("Pyramid wins only if it beats the ENSEMBLE on MAR in BOTH windows.")
