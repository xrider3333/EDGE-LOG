import sys, json, pathlib
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
import numpy as np
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays
from augur_engine import ml_gate

PARAMS_310 = {
    "buf_atr": 1.0, "breakeven_R": 1.5, "ema_len": 420, "tl_len": 238, "vol_mult": 0.8,
    "stop_mult": 1.7, "trail_frac": 4.0, "regime_len": 5, "min_brk": 0.4,
    "limit_atr": 0.7, "atr_len": 44, "act_R": 3.0,
}
COST, MULT = 0.533, 20.0
WIN = ("2010-06-07", "2026-06-30")

m = find_master("NQ", "1m", "eth", "db_noadj_eth")
print("master:", m)
arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
r = run_backtest("ENGUQ_1M_ETH_LIM_1_0.py", arrays=arr, params=dict(PARAMS_310),
                  cost_pts=COST, return_trades=True)
trades = r.get("trades") or []
print("n_trades (fresh):", len(trades), "total_pnl_pts:", r.get("total_pnl"), "net$:", r.get("total_pnl", 0)*MULT if r.get("total_pnl") is not None else None)

gv = ml_gate.gate_validate(arr, trades, wf_from="2016-10-12", wf_to="2025-06-30",
                            lb_from="2025-06-30", lockbox_months=12)
print("\n--- FRESH gate_validate ---")
print("span:", gv.get("span"))
print("wf_range:", gv.get("wf_range"))
print("lockbox_from:", gv.get("lockbox_from"))
uw = gv.get("ungated_wf")
ul = gv.get("ungated_lockbox")
uf = gv.get("ungated_full")
print("ungated_wf:", uw)
print("ungated_wf net$:", uw.get("total_pnl")*MULT if uw else None)
print("ungated_lockbox:", ul)
print("ungated_full:", uf)
print("ungated_full net$:", uf.get("total_pnl")*MULT if uf else None)
