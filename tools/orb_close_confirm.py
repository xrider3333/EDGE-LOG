"""ORB item J — entry-confirmation bake-off (touch vs close-confirmed variants).

Runs the 4 entry modes of ORB_3_0_CC.py on the frozen #137 base, each with be=0 and the
deploy be=1.0, on the optimize window AND the held-out lockbox (independent backtests),
ranked by MAR. Anchors must reproduce:
    touch / be=0   -> #137            ($567,297 full, DD -$40,233)
    touch / be=1.0 -> #154/#156       ($574,177 full, DD -$26,763)
    close / be=0   -> the -$392k trap (~$175k full net, ORB.md item J)

Usage: python tools/orb_close_confirm.py
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from augur_engine.engine import run_backtest, find_master, load_master_arrays, load_strategy

INST, TF, SESS, MULT, FEE = "NQ", "5m", "rth", 20.0, 0.533
FULL = ("2010-06-07", "2026-06-30")
OPT  = ("2010-06-07", "2025-06-29")
LB   = ("2025-06-30", "2026-06-30")
BASE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
            atr_filter=0.1, breakout_buf=0.0, target_R=4.5)

print("loading master + windows ...", flush=True)
MASTER = find_master(INST, TF, SESS)
MOD = load_strategy("ORB_3_0_CC.py")
ARR = {w: load_master_arrays(MASTER, date_from=d0, date_to=d1) for w, (d0, d1) in
       (("full", FULL), ("opt", OPT), ("lb", LB))}

def kpi(window, **p):
    r = run_backtest(MOD, arrays=ARR[window], params=dict(BASE, **p),
                     cost_pts=FEE, return_trades=False)
    if not r:
        return dict(net=0.0, dd=0.0, pf=0.0, mar=0.0, n=0, wr=0.0)
    net = r["total_pnl"] * MULT
    dd  = abs(r.get("max_drawdown", 0) or 0) * MULT
    return dict(net=net, dd=dd, pf=(r.get("profit_factor", 0) or 0),
                mar=(net / dd if dd else 0.0), n=int(r.get("num_trades", 0) or 0),
                wr=(r.get("win_rate", 0) or 0))

print("\n=== ANCHORS (full window) ===")
for lbl, p, exp in (("touch be=0", dict(entry_mode="touch", be_after_R=0.0), "$567,297 / DD $40,233"),
                    ("touch be=1", dict(entry_mode="touch", be_after_R=1.0), "$574,177 / DD $26,763"),
                    ("close be=0", dict(entry_mode="close", be_after_R=0.0), "~$175k (the -$392k trap)")):
    f = kpi("full", **p)
    print(f"  {lbl:11} net ${f['net']:>10,.0f}  DD ${f['dd']:>8,.0f}  n {f['n']}   [expect {exp}]")

hdr = (f"{'entry mode':>12} {'be':>4} | {'IS net$':>10} {'IS DD$':>8} {'IS MAR':>6} {'IS n':>5} | "
       f"{'LB net$':>9} {'LB DD$':>7} {'LB MAR':>6} {'LB PF':>5} {'LB WR%':>6} {'LB n':>4}")
print("\n" + "=" * len(hdr)); print(hdr); print("-" * len(hdr))
rows = []
for mode in ("touch", "close", "close_open", "close_level"):
    for be in (0.0, 1.0):
        o = kpi("opt", entry_mode=mode, be_after_R=be)
        l = kpi("lb",  entry_mode=mode, be_after_R=be)
        rows.append((mode, be, o, l))
        print(f"{mode:>12} {be:>4} | {o['net']:>10,.0f} {o['dd']:>8,.0f} {o['mar']:>6.1f} {o['n']:>5} | "
              f"{l['net']:>9,.0f} {l['dd']:>7,.0f} {l['mar']:>6.1f} {l['pf']:>5.2f} {l['wr']:>5.1f}% {l['n']:>4}")
print("-" * len(hdr))
ctl = next(r for r in rows if r[0] == "touch" and r[1] == 1.0)
print(f"Control = touch/be1.0 (the deploy): IS MAR {ctl[2]['mar']:.1f} / LB MAR {ctl[3]['mar']:.1f}.")
print("A confirmation mode WINS only if it beats the control on MAR in BOTH windows.")
print("close_level trades fewer sessions (runaways never retrace) — n tells that story.")
