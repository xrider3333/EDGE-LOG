"""Local sized-backtest via the engine hook — `engine.run_backtest(sizing=...)`.

NOT the live web: a local command to see the deployable ORB with the execution-layer
size overlay (risk-parity × time-tilt × short-tilt) applied, capital-matched. The engine
attaches a `res["sizing"]` block (baseline vs sized) WITHOUT changing the headline
1-contract metrics. Usage:  python tools/orb_sized_backtest.py [NQ|ES]
"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest

INST = (sys.argv[1] if len(sys.argv) > 1 else "NQ").upper()
MULT = {"NQ": 20.0, "ES": 50.0}.get(INST, 20.0)
FEE  = 5.66 / MULT + 0.25
DEPLOY = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, vol_filter=1.25, breakout_buf=0.0,
              partial_exit_R=0.0, trail_bars=5, target_R=0.0, flat_eod=True)
# The deploy-stack overlay: risk-parity × time-tilt × short-tilt (ORB.md §4.7/4.10/4.11).
SIZING = dict(risk_parity=True, time_tilt=True, long_w=0.5, short_w=1.5,
              stop_frac=0.75, or_bars=1, mult=MULT, fee_pts=FEE)

res = run_backtest("ORB_3_1.py", instrument=INST, timeframe="5m", session="rth",
                   params=DEPLOY, cost_pts=FEE, sizing=SIZING)

print(f"=== ORB sized backtest — {INST} 5m RTH (via engine hook, full history) ===")
print(f"headline (unchanged, 1-contract net): ${res['total_pnl']*MULT:,.0f}  "
      f"PF {res['profit_factor']:.2f}  maxDD ${res['max_drawdown']*MULT:,.0f}  "
      f"MAR {res['total_pnl']/abs(res['max_drawdown']):.1f}")
sz = res.get("sizing")
if not sz:
    print("  (no res['sizing'] — check stop_frac/or_bars)"); sys.exit(0)
b, o = sz["baseline"], sz["sized"]
def line(lab, m):
    print(f"  {lab:<20}net ${m['net']:>12,.0f}  PF {m['profit_factor']:>5.2f}  "
          f"maxDD ${m['max_drawdown']:>11,.0f}  MAR {m['mar']:>6.1f}  maxSz {m['max_size']:>4.1f}")
print(f"sizing overlay (capital-matched to same total $risk) — rule {sz['rule']}:")
line("baseline size-1", b)
line("deploy stack", o)
print(f"  -> MAR {b['mar']:.1f} -> {o['mar']:.1f}  ({(o['mar']/b['mar']-1)*100:+.0f}%),  "
      f"PF {b['profit_factor']:.2f} -> {o['profit_factor']:.2f}")
print("\nHeadline is the honest 1-contract number; the overlay is an execution-layer choice.")
print("Not deployed to the web — the live sizing toggle is the separate 'take it live' step.")
