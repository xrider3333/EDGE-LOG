# -*- coding: utf-8 -*-
"""Verify the ONE round-10 config that beat the crown on every window at IDENTICAL drawdown:
add a second unit once a bar CLOSES at +2R, shared stop, one add maximum. Round 10 rejected it on
the plateau rule. Before believing it, run the two tests that killed this session's other candidates:
per-stretch concentration, and a year-block bootstrap against the crown."""
import sys, numpy as np, pandas as pd
sys.path.insert(0,r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P
b=P.bars(); LB=pd.Timestamp(P.LB_END,tz=b["index"].tz)
CROWN=dict(P.BASE, atr_filter=0.75,vpace_filter=0.8,stop_frac=2.5,target_R=5.0,be_after_R=0.5)
def run(strategy, over):
    r=P.strat(strategy).run_backtest(b["open"],b["high"],b["low"],b["close"],volumes=b["volume"],
                                     day_id=b["day_id"],return_trades=True,**dict(CROWN,**over))
    idx=b["index"]; out=[]
    for t in r["trades"]:
        d=idx[t[0]]
        if d<=LB: out.append((d.tz_localize(None),(t[2]-P.COST)*P.MULT))
    return pd.DataFrame(out,columns=["ts","net"]).sort_values("ts").reset_index(drop=True)
c=run("ORB_3_6.py",{})
p=run("ORB_3_6_PYR.py",dict(pyr_add_R=2.0,pyr_stop="shared",pyr_max=1))
print("crown trades %d  net $%.0f | pyramid trades %d net $%.0f"%(len(c),c.net.sum(),len(p),p.net.sum()))
def stat(d,lo=None,units=1.0):
    x=d if lo is None else d[d.ts>=pd.Timestamp(lo)]
    q=x.net.values/units; yrs=max((x.ts.iloc[-1]-x.ts.iloc[0]).days/365.25,.1)
    cum=np.cumsum(q); dd=abs(float((cum-np.maximum.accumulate(cum)).min()))
    w=q[q>0].sum(); l=abs(q[q<0].sum())
    return q.sum(),dd,(w/l if l else np.inf),((q.sum()/yrs)/dd if dd else np.nan)
print("\n=== per-stretch concentration: strip the 5 biggest winners from EACH 200-trade block ===")
print("block   crown PF  pyr PF | crown exTop5  pyr exTop5")
cb=[];pb=[]
for i in range(0,min(len(c),len(p))-199,200):
    for nm,d,acc in (("c",c,cb),("p",p,pb)):
        v=np.sort(d.iloc[i:i+200].net.values)[::-1]
        w=v[v>0].sum(); l=abs(v[v<0].sum()); q=v[5:]
        acc.append((w/l if l else np.nan,(q[q>0].sum()/abs(q[q<0].sum()) if abs(q[q<0].sum()) else np.nan)))
    print("%5d   %7.3f  %7.3f | %11.3f  %10.3f"%(i//200+1,cb[-1][0],pb[-1][0],cb[-1][1],pb[-1][1]))
ce=np.array([x[1] for x in cb]); pe=np.array([x[1] for x in pb])
print("mean ex-top-5 PF: crown %.3f  pyramid %.3f  (pyramid better in %d of %d blocks)"
      %(ce.mean(),pe.mean(),int((pe>ce).sum()),len(ce)))
print("\n=== year-block bootstrap, pyramid minus crown (per unit; 5000 draws) ===")
yrs=sorted(set(c.ts.dt.year)|set(p.ts.dt.year))
cg={y:c[c.ts.dt.year==y].net.values for y in yrs}; pg={y:p[p.ts.dt.year==y].net.values for y in yrs}
rng=np.random.default_rng(5); dm=[];dd=[];dn=[]
for _ in range(5000):
    dr=rng.choice(yrs,len(yrs),replace=True)
    cc=np.concatenate([cg[y] for y in dr if len(cg[y])]); pp=np.concatenate([pg[y] for y in dr if len(pg[y])])
    def md(v):
        cum=np.cumsum(v); d=abs(float((cum-np.maximum.accumulate(cum)).min()))
        return ((v.sum()/len(yrs))/d if d else np.nan), d, v.sum()
    a,ad,an=md(pp); bq,bd,bn=md(cc)
    dm.append(a-bq); dd.append(ad-bd); dn.append(an-bn)
for nm,v,better in (("MAR",np.array(dm),lambda z:z>0),("maxDD $",np.array(dd),lambda z:z<0),("net $",np.array(dn),lambda z:z>0)):
    print("  %-8s mean %+10.3f | 95%% CI %+.3f to %+.3f | P(pyramid better) = %.3f"
          %(nm,v.mean(),np.percentile(v,2.5),np.percentile(v,97.5),float(better(v).mean())))
print("\n=== is the plateau neighbour real? avg units per trade by add threshold ===")
for a in (1.5,2.0,3.0):
    d=run("ORB_3_6_PYR.py",dict(pyr_add_R=a,pyr_stop="shared",pyr_max=1))
    n,dq,pf,mar=stat(d); print("  addR %.1f: net $%.0f DD $%.0f PF %.3f MAR %.2f"%(a,n,dq,pf,mar))
n,dq,pf,mar=stat(c); print("  crown   : net $%.0f DD $%.0f PF %.3f MAR %.2f"%(n,dq,pf,mar))
