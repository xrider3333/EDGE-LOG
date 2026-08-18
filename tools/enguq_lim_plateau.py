"""ROBUSTNESS: is limit_atr=0.50 a plateau or a lone spike?

The battery-O sweep tested 0.10/0.20/0.35/0.50 and was NON-MONOTONIC: 0.35 dipped
(net/DD 7.49, LB $104k) and 0.50 spiked (net $513k, LB $126k). A parameter you adopt
should sit on a plateau -- neighbours within a step or two should look similar. If 0.50
is a lone spike between two valleys, it is a curve-fit and the adoption is unsafe.
"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays
from augur_strategies.ENGUQ_1M_ETH_LIM_1_0 import run_backtest

MULT, COST, LB_START = 20.0, 0.533, "2025-06-30"
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0)

arr = load_master_arrays(find_master("NQ","1m","eth","db_noadj_eth"), date_from=None,
                         date_to="2026-06-30")
o,h,l,c = arr["open"],arr["high"],arr["low"],arr["close"]
v,day,idx = arr["volume"],arr["day_id"],arr["index"]

def stats(trades):
    d = np.array([(t[2]-COST)*MULT for t in trades])
    ent = pd.to_datetime([idx[int(t[0])] for t in trades]).tz_localize(None)
    cum = np.cumsum(d); dd = abs(float((cum-np.maximum.accumulate(cum)).min()))
    pf = d[d>0].sum()/max(abs(d[d<0].sum()),1e-9)
    lb = d[ent>=pd.Timestamp(LB_START)]
    lbpf = lb[lb>0].sum()/max(abs(lb[lb<0].sum()),1e-9) if len(lb) else float('nan')
    # yearly consistency
    yrs = pd.Series(d).groupby(ent.year.values).sum()
    return dict(n=len(d), net=float(d.sum()), dd=dd, net_dd=float(d.sum())/dd,
                pf=float(pf), lb_n=int(len(lb)), lb_net=float(lb.sum()), lb_pf=float(lbpf),
                pos_years=int((yrs>0).sum()), tot_years=int(len(yrs)))

GRID = [0.00,0.15,0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.80,0.90,1.00]
rows=[]
for L in GRID:
    r = run_backtest(o,h,l,c, volumes=v, day_id=day, index=idx, return_trades=True,
                     limit_atr=L, **CERT)
    s = stats(r["trades"]); s["limit_atr"]=L; rows.append(s)
    print(f"{L:.2f} | n={s['n']:5d} | net=${s['net']:10,.0f} | DD=${s['dd']:9,.0f} | "
          f"net/DD={s['net_dd']:5.2f} | PF={s['pf']:.3f} | LB=${s['lb_net']:9,.0f} "
          f"(n={s['lb_n']:3d}, PF={s['lb_pf']:.3f}) | yrs+{s['pos_years']}/{s['tot_years']}",
          flush=True)

json.dump(rows, open(r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15\scratchpad\lim_plateau.json","w"), indent=1)
print("\nSAVED")
