"""Durable ORB edge-stack report — reproduces the sizing-overlay findings from ORB.md
(§4.7 risk-parity · §4.9-4.10 time-tilt · §4.11 short-tilt) on the deployable config.

Runs the deployable ORB 3.1 (single-lot ride + 5-bar trail), then applies the execution-layer
sizing overlays from augur_engine.sizing and prints a capital-matched comparison over the full
history and the reserved last-12-month lockbox. This replaces the throwaway session scratchpad
scripts — rerun any time with:  python tools/orb_edge_report.py [NQ|ES]

MAR = net / |max drawdown|.  Overlays are compared at the SAME total dollar-risk budget.
"""
import sys, os, datetime as dt
import numpy as np, pandas as pd, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
from augur_engine import sizing as SZ

def _load_strategy(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "augur_strategies", name + ".py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

INST = (sys.argv[1] if len(sys.argv) > 1 else "NQ").upper()
MULT = {"NQ": 20.0, "ES": 50.0}.get(INST, 20.0)
FEE  = 5.66 / MULT + 0.25
STOP_FRAC, OR_BARS = 0.75, 1
DEPLOY = dict(or_bars=OR_BARS, trade_mode="Both", stop_frac=STOP_FRAC, vol_filter=1.25,
              breakout_buf=0.0, partial_exit_R=0.0, trail_bars=5, target_R=0.0, flat_eod=True)

arrays = load_master_arrays(find_master(INST, "5m", "rth"))
idx = pd.to_datetime(arrays["index"])
orb31 = _load_strategy("ORB_3_1")
res = orb31.run_backtest(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                         volumes=arrays["volume"], day_id=arrays["day_id"], return_trades=True, **DEPLOY)
trades = res["trades"]
pnl, risk, ebar, side = SZ.trade_features(trades, arrays, STOP_FRAC, OR_BARS)
tdate = np.array([idx[t[0]].date() for t in trades])
lb_start = idx.max().date() - dt.timedelta(days=365)

# (label, sizing kwargs)
SCHEMES = [
    ("baseline (size 1)",              dict(risk_parity=False)),
    ("+ risk-parity (§4.7)",           dict(risk_parity=True)),
    ("+ time-tilt (§4.10)",            dict(risk_parity=True, time_tilt=True)),
    ("+ short-tilt L0.5/S1.5 (§4.11)", dict(risk_parity=True, time_tilt=True, long_w=0.5, short_w=1.5)),
    ("full stack, short-only",         dict(risk_parity=True, time_tilt=True, long_w=0.0, short_w=1.0)),
]

def report(mask, title):
    print(f"\n{title}   ({int(mask.sum())} trades)")
    print(f"  {'scheme':<34}{'net $':>13}{'PF':>6}{'maxDD $':>12}{'MAR':>8}{'maxSz':>7}")
    for lab, kw in SCHEMES:
        w = SZ.sizing_weights(risk[mask], ebar[mask], side[mask], **kw)
        m = SZ.sized_metrics(pnl[mask], risk[mask], w, mult=MULT, fee_pts=FEE)
        if not m:
            print(f"  {lab:<34}  (no trades)"); continue
        print(f"  {lab:<34}{m['net']:>13,.0f}{m['profit_factor']:>6.2f}"
              f"{m['max_drawdown']:>12,.0f}{m['mar']:>8.1f}{m['max_size']:>7.1f}")

print(f"=== ORB edge-stack report — {INST} 5m RTH (net of ${5.66:.2f}+0.25pt = {FEE:.3f}pt/contract) ===")
print("Capital-matched: each scheme deploys the SAME total dollar-risk as the size-1 baseline.")
report(np.ones(len(trades), bool), "FULL HISTORY")
report(tdate >= lb_start, f"LOCKBOX (unseen, since {lb_start})")
print("\nRead MAR (net/|maxDD|). Overlays are an EXECUTION-LAYER choice — entries/exits unchanged.")
print("Deploy rule: contracts = round( T·RISK$ / (0.75·OR_width·$per_pt) ), clamp [1, 3× base];")
print("  T = time×side tilt (~2× morning, ~1.5× short). See ORB.md §5.6.")
