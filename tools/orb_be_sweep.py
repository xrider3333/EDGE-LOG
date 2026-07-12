"""ORB breakeven sweep — be_after_R 0.9..2.5 by 0.1 (no gaps), on the #137-locked config.

For EACH be level, runs the engine twice via date_from/date_to so the optimize window and
the held-out lockbox are independent backtests (own DD/PF), matching the #153/#154 BE study
windows. Prints in-sample vs lockbox KPIs + flags the risk-adjusted (MAR) champion in EACH.

Usage:  python tools/orb_be_sweep.py           # NQ 5m rth, full table
Anchor: be=0.0 row must reproduce #137 (~$567k net, ~-$40k DD) — sanity check the data path.
"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest

INST = "NQ"; TF = "5m"; SESS = "rth"; MULT = 20.0
FEE  = 0.533                                   # matches #137/#153/#154 cost_pts
# #137-locked lever set (== #153/#154/#155 best_params minus be); only be_after_R varies.
BASE = dict(or_bars=1, trade_mode="Both", stop_frac=1.75, vol_filter=1.25,
            atr_filter=0.1, breakout_buf=0.0, target_R=4.5)
# BE study windows (== #154): optimize = all but last 12mo, lockbox = last 12mo.
FULL = ("2010-06-07", "2026-06-30")
OPT  = ("2010-06-07", "2025-06-29")
LB   = ("2025-06-30", "2026-06-30")

LEVELS = [0.0] + [round(0.9 + 0.1*i, 1) for i in range(17)]   # anchor + 0.9..2.5

def kpi(be, d0, d1):
    r = run_backtest("ORB_3_0_BE.py", instrument=INST, timeframe=TF, session=SESS,
                     params=dict(BASE, be_after_R=be), cost_pts=FEE,
                     date_from=d0, date_to=d1, return_trades=False)
    net = r["total_pnl"] * MULT
    dd  = abs(r.get("max_drawdown", 0) or 0) * MULT
    return dict(net=net, dd=dd, pf=r.get("profit_factor", 0) or 0,
                mar=(net/dd if dd else 0), n=int(r.get("num_trades", 0) or 0),
                wr=r.get("win_rate", 0) or 0)

rows = []
for be in LEVELS:
    o = kpi(be, *OPT); l = kpi(be, *LB)
    rows.append((be, o, l))
    print(f"  ...be={be:<4} in-sample net ${o['net']:>10,.0f} DD ${o['dd']:>8,.0f} MAR {o['mar']:>5.1f}"
          f"  |  lockbox net ${l['net']:>8,.0f} DD ${l['dd']:>7,.0f} MAR {l['mar']:>5.1f} PF {l['pf']:.2f}",
          flush=True)

# best-in-lockbox by MAR and by net (exclude the be=0 anchor from "best BE" picks)
be_rows = [r for r in rows if r[0] > 0]
best_lb_mar = max(be_rows, key=lambda r: r[2]["mar"])[0]
best_lb_net = max(be_rows, key=lambda r: r[2]["net"])[0]
best_is_mar = max(be_rows, key=lambda r: r[1]["mar"])[0]

print("\n" + "=" * 118)
print(f"ORB BREAKEVEN SWEEP — {INST} {TF} {SESS} · #137-locked (or1/stop1.75/tgt4.5R/vol1.25/atr0.1/Both) · cost {FEE}pt")
print(f"  in-sample = {OPT[0]}→{OPT[1]}   ·   lockbox = {LB[0]}→{LB[1]}  (held out, last 12mo)")
print("=" * 118)
hdr = f"{'be_R':>5} | {'IS net$':>10} {'IS DD$':>9} {'IS PF':>5} {'IS MAR':>6} {'IS n':>5} | " \
      f"{'LB net$':>9} {'LB DD$':>8} {'LB PF':>5} {'LB MAR':>6} {'LB win%':>7} {'LB n':>4} | flag"
print(hdr); print("-" * len(hdr))
for be, o, l in rows:
    flags = []
    if be == 0.0: flags.append("#137 baseline (no BE)")
    if be == best_lb_mar: flags.append("<< best LOCKBOX MAR")
    if be == best_lb_net: flags.append("<< best LOCKBOX net")
    if be == 1.0: flags.append("#154 PASS")
    if be == 2.6 == be: pass
    print(f"{be:>5.1f} | {o['net']:>10,.0f} {o['dd']:>9,.0f} {o['pf']:>5.2f} {o['mar']:>6.1f} {o['n']:>5} | "
          f"{l['net']:>9,.0f} {l['dd']:>8,.0f} {l['pf']:>5.2f} {l['mar']:>6.1f} {l['wr']:>6.1f}% {l['n']:>4} | {' '.join(flags)}")
print("-" * len(hdr))
print(f"best LOCKBOX MAR  -> be={best_lb_mar}    best LOCKBOX net -> be={best_lb_net}    best IN-SAMPLE MAR -> be={best_is_mar}")
print("(higher be_after_R barely triggers -> drifts back toward #137: higher net, WORSE DD/MAR. Lower be cuts DD.)")
