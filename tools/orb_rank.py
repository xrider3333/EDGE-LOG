# -*- coding: utf-8 -*-
"""Rank the VALIDATED ORB configurations for forward testing.
Every one of these already passed an Auto-Validate at 7 of 8 walk-forward folds, so the validate
verdict does not separate them. What separates them: the sealed year, whether the money is spread
or sits in ten trades, and how they behave in the regime we actually trade now."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P
LB=pd.Timestamp(P.LB_END)
rows=[]
for run,lab,over,ev in P.CANDIDATES:
    tr=P.trades_of(over)
    d=pd.DataFrame(tr,columns=["ts","net"]).sort_values("ts").reset_index(drop=True)
    def st(lo):
        x=d[d.ts>=pd.Timestamp(lo)]
        p=x.net.values; yrs=max((x.ts.iloc[-1]-x.ts.iloc[0]).days/365.25,.1)
        cum=np.cumsum(p); dd=abs(float((cum-np.maximum.accumulate(cum)).min()))
        w=p[p>0].sum(); l=abs(p[p<0].sum())
        return dict(n=len(p),net=p.sum(),dd=dd,pf=(w/l if l else np.inf),mar=((p.sum()/yrs)/dd if dd else np.nan))
    full=st("2010-06-07"); y5=st("2021-08-13"); oos=st("2025-08-13")
    p=np.sort(d.net.values)[::-1]
    top10=100*p[:10].sum()/p.sum()
    q=p[10:]; ex=q[q>0].sum()/abs(q[q<0].sum())
    # recent-regime read: profit factor of the second half of this config's own trades
    h=len(d)//2
    a=d.net.values[:h]; b=d.net.values[h:]
    pf1=a[a>0].sum()/abs(a[a<0].sum()); pf2=b[b>0].sum()/abs(b[b<0].sum())
    rows.append(dict(run=run,lab=lab,n=full["n"],full_net=full["net"],full_dd=full["dd"],full_mar=full["mar"],
                     y5_mar=y5["mar"],y5_pf=y5["pf"],oos_net=oos["net"],oos_pf=oos["pf"],oos_mar=oos["mar"],
                     top10=top10,ex10_pf=ex,pf_first=pf1,pf_second=pf2))
df=pd.DataFrame(rows)
pd.set_option("display.width",250)
print("%-4s %-14s %5s %9s %7s %6s %6s %9s %6s %6s %6s %6s %11s"%(
    "run","config","n","full net","fullMAR","5y MAR","5y PF","OOS net","OOSPF","OOSMAR","top10%","exT10","PF 1st->2nd"))
for _,r in df.sort_values("oos_net",ascending=False).iterrows():
    print("%-4d %-14s %5d %9.0f %7.2f %6.2f %6.3f %9.0f %6.3f %6.2f %6.0f %6.3f  %.2f->%.2f"%(
        r["run"],r["lab"][:14],r["n"],r["full_net"],r["full_mar"],r["y5_mar"],r["y5_pf"],
        r["oos_net"],r["oos_pf"],r["oos_mar"],r["top10"],r["ex10_pf"],r["pf_first"],r["pf_second"]))
df.to_csv(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\_orb_rank.csv",index=False)
