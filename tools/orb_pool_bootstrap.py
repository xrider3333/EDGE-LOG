# -*- coding: utf-8 -*-
"""Year-block bootstrap of POOLED (11 validated ORB configs, per unit) vs the crown alone.
Resample calendar years with replacement, rebuild both equity curves in the drawn order, and
compare MAR and drawdown. maxDD is a noisy statistic, so a 6% MAR gain must be shown to survive."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P
LB=pd.Timestamp(P.LB_END)
legs=[pd.DataFrame(P.trades_of(o),columns=["ts","net"]) for _,_,o,_ in P.CANDIDATES]
K=len(legs)
pool=pd.concat(legs); pool=pool[pool.ts<=LB].sort_values("ts"); pool["net"]/=K
crown=legs[[l for l,(r,_,_,_) in enumerate(P.CANDIDATES) if r==314][0]]
crown=crown[crown.ts<=LB].sort_values("ts")
def mar_dd(p, yrs):
    cum=np.cumsum(p); dd=abs(float((cum-np.maximum.accumulate(cum)).min()))
    return (((p.sum()/yrs)/dd) if dd else np.nan), dd
yrs=sorted(set(pool.ts.dt.year) | set(crown.ts.dt.year))
pg={y:pool[pool.ts.dt.year==y].net.values for y in yrs}
cg={y:crown[crown.ts.dt.year==y].net.values for y in yrs}
rng=np.random.default_rng(7); dm=[]; dd_=[]
for _ in range(5000):
    draw=rng.choice(yrs,len(yrs),replace=True)
    pp=np.concatenate([pg[y] for y in draw if len(pg[y])]); cc=np.concatenate([cg[y] for y in draw if len(cg[y])])
    if len(pp)<50 or len(cc)<50: continue
    a,ad=mar_dd(pp,len(yrs)); b,bd=mar_dd(cc,len(yrs))
    dm.append(a-b); dd_.append(ad-bd)
dm=np.array(dm); dd_=np.array(dd_)
print("POOLED minus CROWN, year-block bootstrap, %d draws" % len(dm))
print("  MAR difference : mean %+.3f | 95%% CI %+.3f to %+.3f | P(pool better) = %.3f"
      %(dm.mean(), np.percentile(dm,2.5), np.percentile(dm,97.5), float((dm>0).mean())))
print("  maxDD difference $: mean %+.0f | 95%% CI %+.0f to %+.0f | P(pool lower DD) = %.3f"
      %(dd_.mean(), np.percentile(dd_,2.5), np.percentile(dd_,97.5), float((dd_<0).mean())))
