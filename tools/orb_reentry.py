"""ORB item Q — re-entry / stop-and-reverse bake-off (ORB_3_0_RE.py).

Modes: none (anchor == #154) / rebreak / flip / sar, on the frozen #137+BE base,
optimize window + held-out lockbox, MAR-ranked. Usage: python tools/orb_reentry.py
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
MOD = load_strategy("ORB_3_0_RE.py")
ARR = {w: load_master_arrays(MASTER, date_from=d0, date_to=d1) for w, (d0, d1) in
       (("full", FULL), ("opt", OPT), ("lb", LB))}

def kpi(window, **p):
    r = run_backtest(MOD, arrays=ARR[window], params=dict(BASE, **p), cost_pts=FEE, return_trades=False)
    if not r:
        return dict(net=0, dd=0, pf=0, mar=0, n=0, wr=0)
    net = r["total_pnl"] * MULT; dd = abs(r.get("max_drawdown", 0) or 0) * MULT
    return dict(net=net, dd=dd, pf=r.get("profit_factor", 0) or 0, mar=(net / dd if dd else 0),
                n=int(r.get("num_trades", 0) or 0), wr=r.get("win_rate", 0) or 0)

f = kpi("full", reentry_mode="none")
print(f"\nANCHOR none/full: net ${f['net']:,.0f} DD ${f['dd']:,.0f} n {f['n']}  [expect $574,177 / $26,763 / 3951]")

hdr = (f"{'mode':>9} | {'IS net$':>10} {'IS DD$':>8} {'IS MAR':>6} {'IS n':>5} | "
       f"{'LB net$':>9} {'LB DD$':>7} {'LB MAR':>6} {'LB PF':>5} {'LB n':>4}")
print("\n" + "=" * len(hdr)); print(hdr); print("-" * len(hdr))
for mode in ("none", "rebreak", "flip", "sar"):
    o = kpi("opt", reentry_mode=mode); l = kpi("lb", reentry_mode=mode)
    print(f"{mode:>9} | {o['net']:>10,.0f} {o['dd']:>8,.0f} {o['mar']:>6.1f} {o['n']:>5} | "
          f"{l['net']:>9,.0f} {l['dd']:>7,.0f} {l['mar']:>6.1f} {l['pf']:>5.2f} {l['n']:>4}")
print("-" * len(hdr))
print("A mode wins only if it beats none on MAR in BOTH windows (extra trades add fee + risk).")
