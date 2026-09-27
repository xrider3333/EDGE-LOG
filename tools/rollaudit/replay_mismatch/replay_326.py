import sys
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays
from augur_engine import ml_gate

PARAMS = {
    "buf_atr": 0.9, "breakeven_R": 1.5, "ema_len": 1380, "tl_len": 170, "vol_mult": 0.0,
    "stop_mult": 1.0, "trail_frac": 2.5, "regime_len": 5, "min_brk": 1.3,
    "limit_atr": 0.5, "atr_len": 106, "act_R": 2.5,
}
COST, MULT = 0.533, 20.0
WIN = ("2010-06-07", "2026-06-30")
LB_FROM = "2025-06-30"

m = find_master("NQ", "1m", "eth", "db_noadj_eth")
arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])

# CONTINUOUS: one backtest over the whole window (what gate_validate itself does)
r_cont = run_backtest("ENGUQ_1M_ETH_REG5.py", arrays=arr, params=dict(PARAMS),
                       cost_pts=COST, return_trades=True)
trades = r_cont.get("trades") or []
print("CONTINUOUS full-window: n_trades=%d net$=%.2f" % (len(trades), (r_cont.get("total_pnl") or 0)*MULT))

gv = ml_gate.gate_validate(arr, trades, wf_from="2016-10-12", wf_to="2025-06-30",
                            lb_from=LB_FROM, lockbox_months=12)
print("gate_validate ungated_full n=%d $%.2f" % (gv["ungated_full"]["num_trades"], gv["ungated_full"]["total_pnl"]*MULT))
print("gate_validate ungated_wf   n=%d $%.2f" % (gv["ungated_wf"]["num_trades"], gv["ungated_wf"]["total_pnl"]*MULT))
print("gate_validate ungated_lockbox(continuous, by entry-time) n=%d $%.2f" % (gv["ungated_lockbox"]["num_trades"], gv["ungated_lockbox"]["total_pnl"]*MULT))

# RELOAD: fresh backtest starting the array AT the lockbox boundary only (validate.py's lockbox method)
arr_lb = load_master_arrays(m, date_from=LB_FROM, date_to=WIN[1])
r_reload = run_backtest("ENGUQ_1M_ETH_REG5.py", arrays=arr_lb, params=dict(PARAMS),
                         cost_pts=COST, return_trades=True)
trades_lb = r_reload.get("trades") or []
print("\nRELOAD lockbox-only (fresh state from %s): n_trades=%d net$=%.2f" % (LB_FROM, len(trades_lb), (r_reload.get("total_pnl") or 0)*MULT))
