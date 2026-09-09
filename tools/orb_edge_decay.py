# -*- coding: utf-8 -*-
"""Is the crown's edge DECAYING? Rolling profit factor and EV per unit of risk on the #314 crown,
in trade-count blocks (not calendar, so each point rests on the same amount of evidence).
Money grew ~7x with the index, so dollars per year say nothing about edge - PF and EV R do."""
import sys, numpy as np, pandas as pd
sys.path.insert(0,r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P
CROWN=dict(atr_filter=0.75,vpace_filter=0.8,stop_frac=2.5,target_R=5.0,be_after_R=0.5)
d=pd.DataFrame(P.trades_of(CROWN),columns=["ts","net"]).sort_values("ts").reset_index(drop=True)
print("crown trades to LB_END:",len(d))
B=200
print("\nblock  period                 n    net$    PF    win%   avg$")
pf=[]
for i in range(0,len(d)-B+1,B):
    g=d.iloc[i:i+B]; p=g.net.values
    w=p[p>0].sum(); l=abs(p[p<0].sum()); f=w/l if l else np.inf
    pf.append(f)
    print("%5d  %s..%s %4d %8.0f %6.3f %5.0f%% %7.0f"%(i//B+1,g.ts.iloc[0].date(),g.ts.iloc[-1].date(),
          len(g),p.sum(),f,100*(p>0).mean(),p.mean()))
pf=np.array(pf); n=len(pf); x=np.arange(n)
sl=np.polyfit(x,pf,1)[0]
rng=np.random.default_rng(3)
null=[np.polyfit(x,rng.permutation(pf),1)[0] for _ in range(20000)]
p_dec=float(np.mean(np.array(null)<=sl))
print("\nPF trend across %d blocks: slope %+.4f per block (%.3f over the whole history)"%(n,sl,sl*(n-1)))
print("first half mean PF %.3f | second half %.3f"%(pf[:n//2].mean(),pf[n//2:].mean()))
print("permutation p for a DECLINING trend = %.3f  (small = real decay)"%p_dec)

# ---- ROBUSTNESS: is the rising PF just a few fat winners in the recent blocks? ----
print("\n=== same blocks, TOP-5 WINNERS REMOVED from each (the per-stretch concentration test) ===")
print("block  n    PF_all  PF_ex5  top5 share of block net")
pf2=[]
for i in range(0,len(d)-B+1,B):
    p=np.sort(d.iloc[i:i+B].net.values)[::-1]
    w=p[p>0].sum(); l=abs(p[p<0].sum()); f=w/l if l else np.inf
    q=p[5:]; w2=q[q>0].sum(); l2=abs(q[q<0].sum()); f2=w2/l2 if l2 else np.inf
    share=100*p[:5].sum()/p.sum() if p.sum()>0 else np.nan
    pf2.append(f2)
    print("%5d %4d  %6.3f  %6.3f   %5.0f%%"%(i//B+1,len(p),f,f2,share))
pf2=np.array(pf2); x2=np.arange(len(pf2)); s2=np.polyfit(x2,pf2,1)[0]
null2=[np.polyfit(x2,rng.permutation(pf2),1)[0] for _ in range(20000)]
print("\nex-top-5 PF trend slope %+.4f/block | first half %.3f -> second half %.3f | p(rising) = %.3f"
      %(s2,pf2[:len(pf2)//2].mean(),pf2[len(pf2)//2:].mean(),float(np.mean(np.array(null2)>=s2))))
# same test on WIN RATE and on EV in R units (dollar-free)
wr=[]; 
for i in range(0,len(d)-B+1,B):
    p=d.iloc[i:i+B].net.values; wr.append(100*(p>0).mean())
wr=np.array(wr); s3=np.polyfit(np.arange(len(wr)),wr,1)[0]
n3=[np.polyfit(np.arange(len(wr)),rng.permutation(wr),1)[0] for _ in range(20000)]
print("win-rate trend %+.3f pts/block | %.1f%% -> %.1f%% | p(rising) = %.3f"
      %(s3,wr[:len(wr)//2].mean(),wr[len(wr)//2:].mean(),float(np.mean(np.array(n3)>=s3))))
