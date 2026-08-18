"""t6 — ENGU-Q ETH 'freeze_overnight' probe (round-6 R6d's flagged untested refinement).

PRE-REGISTERED (written before the variant ran):
  Invariant: freeze OFF must reproduce the certified triage run TO THE CENT
             (n=2843, net $434,721.12, PF 1.332, maxDD -$50,420.22).
  B1 full-window: MAR > 8.62 AND net >= $434,721 AND maxDD <= $55,462 (+10% cap).
  B2 LB (entry-sliced 2025-06-30 -> 2026-06-30): net >= $98,488 AND PF >= 1.40.
  B3 frozen 8-fold WF (equal-bar folds, fresh warmup, t3 protocol): >= 7/8 positive.
  B4 robustness (report-only, no re-pick): freeze windows 17:00-09:30 and 18:00-10:00
     should stay within ~+/-15% of the 18:00-09:30 net (plateau, not spike).
One knob (freeze on/off). No other params touched (frozen #149-scaled config).
"""
import sys, pathlib, json
import numpy as np, pandas as pd
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest, find_master, load_master_arrays
import importlib.util
_sp = importlib.util.spec_from_file_location("eth", REPO / "augur_strategies" / "ENGUQ_1M_ETH_1_0.py")
_md = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(_md)
FROZEN = {k: v["default"] for k, v in _md.DEFAULT_PARAMS.items()}   # the certified scaled config

WIN = ("2010-06-07", "2026-06-30")
LB = pd.Timestamp("2025-06-30")
COST, MULT = 0.533, 20.0
S = "ENGUQ_1M_ETH_1_0.py"

arr = load_master_arrays(find_master("NQ", "1m", "eth"), date_from=WIN[0], date_to=WIN[1])
n = len(arr["close"]); idx = arr["index"]
print(f"bars {n}")

def stats(r, tag):
    net = r["total_pnl"]*MULT; dd = r["max_drawdown"]*MULT
    tr = r["trades"]
    lbm = [t for t in tr if pd.Timestamp(idx[int(t[0])]).tz_localize(None) >= LB]
    lb_net = sum(t[2] for t in lbm)*MULT
    gw = sum(t[2] for t in lbm if t[2] > 0); gl = -sum(t[2] for t in lbm if t[2] < 0)
    lb_pf = (gw/gl) if gl > 1e-9 else float("inf")
    print(f"{tag}: n={r['num_trades']} net=${net:,.2f} PF={r['profit_factor']:.3f} "
          f"DD=${dd:,.2f} MAR={net/abs(dd):.2f} | LB n={len(lbm)} net=${lb_net:,.2f} PF={lb_pf:.3f}")
    return dict(n=r["num_trades"], net=net, pf=r["profit_factor"], dd=dd, mar=net/abs(dd),
                lb_n=len(lbm), lb_net=lb_net, lb_pf=lb_pf)

base = run_backtest(S, arrays=arr, params=dict(FROZEN, freeze_overnight=False), cost_pts=COST, return_trades=True)
b = stats(base, "OFF (invariant)")
ok = (b["n"] == 2843 and abs(b["net"] - 434721.12) < 1.0 and abs(b["dd"] + 50420.22) < 1.0)
print("INVARIANT:", "PASS" if ok else "FAIL — ABORT")
if not ok: sys.exit(1)

von = run_backtest(S, arrays=arr, params=dict(FROZEN, freeze_overnight=True), cost_pts=COST, return_trades=True)
v = stats(von, "FREEZE 18:00-09:30")

# B3 frozen 8-fold WF with the flag ON
folds = 8; pos_folds = 0; fold_rows = []
for f in range(folds):
    a, bnd = int(n*f/folds), int(n*(f+1)/folds)
    sl = {k: (arr[k][a:bnd] if k in ("open","high","low","close","volume","day_id","index") else arr[k]) for k in arr}
    fr = run_backtest(S, arrays=sl, params=dict(FROZEN, freeze_overnight=True), cost_pts=COST, return_trades=True)
    fn = (fr["total_pnl"]*MULT) if fr else 0.0
    fold_rows.append(round(fn))
    if fn > 0: pos_folds += 1
print("WF folds $:", fold_rows, f"-> {pos_folds}/8 positive")

print("\nB1 full:", "PASS" if (v["mar"] > 8.62 and v["net"] >= 434721 and abs(v["dd"]) <= 55462) else "FAIL")
print("B2 LB  :", "PASS" if (v["lb_net"] >= 98488 and v["lb_pf"] >= 1.40) else "FAIL")
print("B3 WF  :", "PASS" if pos_folds >= 7 else "FAIL")
