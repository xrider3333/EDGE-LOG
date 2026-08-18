"""t7c — dump per-trade (exit_date, pnl_pts) for the 3 legal legs + emit RUNBOARD
BOOKS JSON (full / IS / LB per book, trade-pooled PF). IS = before 2025-08-13,
LB = 2025-08-13 -> 2026-08-13 (#234's lockbox year). Window 2010-06-07 -> 2026-08-13."""
import sys, pathlib, json
import numpy as np, pandas as pd
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest, find_master, load_master_arrays
import importlib.util
def defaults(f):
    sp = importlib.util.spec_from_file_location("m", REPO/"augur_strategies"/f)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}
C2P = defaults("ORB_3_6_C2.py"); ETHP = defaults("ENGUQ_1M_ETH_1_0.py")
_s = importlib.util.spec_from_file_location("e", REPO/"augur_strategies"/"ENGUQ_1M_1_0.py")
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
ENGP = _m.NQ_DEPLOY_PARAMS_149
COST, MULT = 0.533, 20.0
LBF = pd.Timestamp("2025-08-13")

def trades(strat, tf, sess, params):
    arr = load_master_arrays(find_master("NQ", tf, sess), date_from="2010-06-07", date_to="2026-08-13")
    r = run_backtest(strat, arrays=arr, params=params, cost_pts=COST, return_trades=True)
    idx = arr["index"]
    return [(pd.Timestamp(idx[int(t[1])]).tz_localize(None), float(t[2])) for t in r["trades"]]

legs = {"c2": trades("ORB_3_6_C2.py","5m","rth",C2P),
        "engq_rth": trades("ENGUQ_1M_1_0.py","1m","rth",ENGP),
        "engq_eth": trades("ENGUQ_1M_ETH_1_0.py","1m","eth",ETHP)}
rows = [(k, d.isoformat(), p) for k, l in legs.items() for d, p in l]
pd.DataFrame(rows, columns=["leg","exit_dt","pnl_pts"]).to_csv(REPO/"tools"/"r13_results"/"legal_legs_trades.csv", index=False)
print("trades saved:", {k: len(v) for k, v in legs.items()})

def book_stats(leglist):
    tr = sorted([t for k in leglist for t in legs[k]])
    def sl(pred):
        pp = [p for d, p in tr if pred(d)]
        if not pp: return None
        net = sum(pp)*MULT
        gw = sum(x for x in pp if x>0); gl = -sum(x for x in pp if x<0)
        # daily DD
        df = pd.DataFrame([(d.date(), p*MULT) for d, p in tr if pred(d)], columns=["d","p"]).groupby("d")["p"].sum()
        cum = df.cumsum(); dd = float((cum-cum.cummax()).min())
        return dict(net=round(net), pf=round(gw/gl,3) if gl>1e-9 else None, dd=round(abs(dd)),
                    mar=round(net/abs(dd),2) if dd<-1e-9 else None, n=len(pp))
    return {"full": sl(lambda d: True), "is_": sl(lambda d: d < LBF), "lb": sl(lambda d: d >= LBF)}

out = {"A_c2_rth": book_stats(["c2","engq_rth"]),
       "B_3leg":  book_stats(["c2","engq_rth","engq_eth"]),
       "C_c2_eth": book_stats(["c2","engq_eth"]),
       "ETH_alone": book_stats(["engq_eth"])}
print(json.dumps(out, indent=1))
(REPO/"tools"/"r13_results"/"legal_books.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
