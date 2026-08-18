"""t7 — LEGAL BOOK reads (post look-ahead cleanup): rebuild the blend baseline on the
legal ORB crown (#234 = ORB_3_6_C2 pinned) and measure the 3-leg candidate (+ ETH).

Parity gates first (each leg on ITS OWN certified window, must match):
  C2   : 2010-06-07 -> 2026-08-13, NQ 5m rth  -> n=2607, net $389,874, PF 1.307
  ENGUQ: 2010-06-07 -> 2026-06-30, NQ 1m rth  -> n=2048, net $477,520.82
  ETH  : 2010-06-07 -> 2026-06-30, NQ 1m eth  -> n=2843, net $434,721.12
Then all legs on the COMMON window 2010-06-07 -> 2026-08-13 (exit-date daily, union):
  BOOK A (new legal baseline) : C2 + ENGUQ-RTH, 1:1
  BOOK B (candidate)          : C2 + ENGUQ-RTH + ENGUQ-ETH, 1:1:1
  BOOK C (read)               : C2 + ENGUQ-ETH, 1:1
Stats per book: net, pooled PF, maxDD, MAR, 8 equal-day WF slices, LB slice
(2025-08-13 -> 2026-08-13, matching #234's lockbox year), pairwise daily corr.
"""
import sys, pathlib
import numpy as np, pandas as pd
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine.engine import run_backtest, find_master, load_master_arrays
import importlib.util
def defaults(f):
    sp = importlib.util.spec_from_file_location("m", REPO/"augur_strategies"/f)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}

C2P  = defaults("ORB_3_6_C2.py")
ETHP = defaults("ENGUQ_1M_ETH_1_0.py")
_s = importlib.util.spec_from_file_location("e", REPO/"augur_strategies"/"ENGUQ_1M_1_0.py")
_m = importlib.util.module_from_spec(_s); _s.loader.exec_module(_m)
ENGP = _m.NQ_DEPLOY_PARAMS_149
COST, MULT = 0.533, 20.0
END = "2026-08-13"; LBF = pd.Timestamp("2025-08-13")

def leg(strat, inst, tf, sess, params, d_to):
    arr = load_master_arrays(find_master(inst, tf, sess), date_from="2010-06-07", date_to=d_to)
    r = run_backtest(strat, arrays=arr, params=params, cost_pts=COST, return_trades=True)
    idx = arr["index"]; d = {}; pnls = []
    for t in r["trades"]:
        day = pd.Timestamp(idx[int(t[1])]).date()
        d[day] = d.get(day, 0.0) + float(t[2]) * MULT
        pnls.append(float(t[2]))
    return r, pd.Series(d).sort_index(), pnls

# ── parity gates ──────────────────────────────────────────────────────────────
r,_,_ = leg("ORB_3_6_C2.py","NQ","5m","rth",C2P,"2026-08-13")
print(f"C2 parity  : n={r['num_trades']} net=${r['total_pnl']*MULT:,.0f} PF={r['profit_factor']:.3f} (expect 2607/$389,874/1.307)")
c2_ok = abs(r['num_trades']-2607)<=2 and abs(r['total_pnl']*MULT-389874)<800
r,_,_ = leg("ENGUQ_1M_1_0.py","NQ","1m","rth",ENGP,"2026-06-30")
print(f"ENGQ parity: n={r['num_trades']} net=${r['total_pnl']*MULT:,.2f} (expect 2048/$477,520.82)")
eg_ok = r['num_trades']==2048 and abs(r['total_pnl']*MULT-477520.82)<1
r,_,_ = leg("ENGUQ_1M_ETH_1_0.py","NQ","1m","eth",ETHP,"2026-06-30")
print(f"ETH parity : n={r['num_trades']} net=${r['total_pnl']*MULT:,.2f} (expect 2843/$434,721.12)")
et_ok = r['num_trades']==2843 and abs(r['total_pnl']*MULT-434721.12)<1
if not (c2_ok and eg_ok and et_ok):
    print("PARITY FAIL — ABORT"); sys.exit(1)
print("ALL PARITY PASS\n")

# ── common-window legs ────────────────────────────────────────────────────────
_, c2d, c2p = leg("ORB_3_6_C2.py","NQ","5m","rth",C2P,END)
_, egd, egp = leg("ENGUQ_1M_1_0.py","NQ","1m","rth",ENGP,END)
_, etd, etp = leg("ENGUQ_1M_ETH_1_0.py","NQ","1m","eth",ETHP,END)

# durable per-leg daily series -> any future slice stat without engine reruns
out = pd.DataFrame({"c2": c2d, "engq_rth": egd, "engq_eth": etd}).fillna(0.0)
out.index.name = "date"
out.to_csv(REPO / "tools" / "r13_results" / "legal_legs_daily.csv")
print("saved tools/r13_results/legal_legs_daily.csv", out.shape)

def pooled_pf(list_of_pnls):
    allp = [x for l in list_of_pnls for x in l]
    gw = sum(x for x in allp if x>0); gl = -sum(x for x in allp if x<0)
    return gw/gl if gl>1e-9 else float("inf")

def book(name, legs_daily, legs_pnls):
    s = pd.DataFrame({i:d for i,d in enumerate(legs_daily)}).fillna(0).sum(axis=1).sort_index()
    cum = s.cumsum(); dd = float((cum-cum.cummax()).min()); net = float(s.sum())
    lb = s[pd.Index(pd.to_datetime(s.index)) >= LBF]
    lbc = lb.cumsum(); lbdd = float((lbc-lbc.cummax()).min()) if len(lb) else np.nan
    ei = np.array_split(np.arange(len(s)), 8)
    slices = [float(s.iloc[ix].sum()) for ix in ei]; wf = sum(1 for x in slices if x>0)
    pf = pooled_pf(legs_pnls)
    print(f"{name:34} net=${net:>11,.0f} PF={pf:.3f} DD=${abs(dd):>9,.0f} MAR={net/abs(dd):5.2f} "
          f"WF={wf}/8 | LB net=${float(lb.sum()):>9,.0f} LBDD=${abs(lbdd):>8,.0f} LBMAR={float(lb.sum())/abs(lbdd):4.2f}")
    return s

print(f"{'book':34} {'':>15} {'':>8}")
sA = book("A  C2 + ENGUQ-RTH (legal baseline)", [c2d,egd], [c2p,egp])
sB = book("B  C2 + RTH + ETH (3-leg cand.)  ", [c2d,egd,etd], [c2p,egp,etp])
sC = book("C  C2 + ETH (2-leg alt)          ", [c2d,etd], [c2p,etp])
u = pd.DataFrame({"c2":c2d,"eg":egd,"et":etd}).fillna(0)
print("\ncorr daily: C2~RTH %.3f · C2~ETH %.3f · RTH~ETH %.3f" %
      (u.c2.corr(u.eg), u.c2.corr(u.et), u.eg.corr(u.et)))
