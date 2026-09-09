# -*- coding: utf-8 -*-
"""CONTROL for the rising-edge finding. The crown was chosen partly on recent data, so its recent
blocks are flattered by selection. Repeat the identical test on configs that were NOT selected on
recent data: the untouched parent default, and deliberately mediocre corners of the grid."""
import sys, numpy as np, pandas as pd
sys.path.insert(0,r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P
rng=np.random.default_rng(11); B=200
TESTS=[("crown #314", dict(atr_filter=0.75,vpace_filter=0.8,stop_frac=2.5,target_R=5.0,be_after_R=0.5)),
       ("parent default", {}),
       ("no filters at all", dict(atr_filter=0.0,vpace_filter=0.0)),
       ("wide stop 3.0 / tgt 4", dict(stop_frac=3.0,target_R=4.0)),
       ("or_bars 1", dict(or_bars=1)),
       ("or_bars 3, be 0.5", dict(or_bars=3,be_after_R=0.5))]
print("%-24s %5s  %-13s %-13s %-13s"%("config","n","PF 1st->2nd","exTop5 1st->2nd","winrate 1st->2nd"))
for lab,over in TESTS:
    d=pd.DataFrame(P.trades_of(over),columns=["ts","net"]).sort_values("ts").reset_index(drop=True)
    pf=[];pe=[];wr=[]
    for i in range(0,len(d)-B+1,B):
        p=np.sort(d.iloc[i:i+B].net.values)[::-1]
        w=p[p>0].sum(); l=abs(p[p<0].sum()); pf.append(w/l if l else np.nan)
        q=p[5:]; w2=q[q>0].sum(); l2=abs(q[q<0].sum()); pe.append(w2/l2 if l2 else np.nan)
        wr.append(100*(p>0).mean())
    def half(a):
        a=np.array(a); h=len(a)//2; return a[:h].mean(), a[h:].mean()
    def pval(a):
        a=np.array(a); x=np.arange(len(a)); s=np.polyfit(x,a,1)[0]
        return float(np.mean([np.polyfit(x,rng.permutation(a),1)[0] for _ in range(5000)]>=s))
    a1,a2=half(pf); b1,b2=half(pe); c1,c2=half(wr)
    print("%-24s %5d  %5.2f->%5.2f p%.2f  %5.2f->%5.2f p%.2f  %4.1f->%4.1f p%.2f"
          %(lab,len(d),a1,a2,pval(pf),b1,b2,pval(pe),c1,c2,pval(wr)))
