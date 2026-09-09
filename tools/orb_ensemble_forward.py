# -*- coding: utf-8 -*-
"""ENSEMBLE test. The meta walk-forward said picking ONE config has no forward skill. If that is
true, the answer is not a better picker - it is to stop picking. Trade the top-K configs together,
one unit each, and judge PER UNIT (divide by K) so this is never a leverage win. The prize we are
looking for is drawdown: near-identical configs whose losing days differ should pool to a smaller
drawdown than any single one of them, at nearly the same money."""
import sys, itertools, json, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P

GRID = dict(or_bars=[1,2,3], stop_frac=[2.0,2.5,3.0], target_R=[4.0,5.0,5.5,6.0],
            be_after_R=[0.5,1.0], atr_filter=[0.7,0.75], vpace_filter=[0.7,0.8])
KEYS=list(GRID); CFGS=[dict(zip(KEYS,v)) for v in itertools.product(*GRID.values())]
DEFAULT={k:P.BASE[k] for k in KEYS}
CROWN=dict(DEFAULT, atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0, be_after_R=0.5, or_bars=2)
print("configs", len(CFGS), flush=True)
res={}
for i,cfg in enumerate(CFGS):
    tr=P.trades_of(cfg)
    res[json.dumps(cfg,sort_keys=True)]=pd.DataFrame(tr,columns=["ts","net"]) if tr else pd.DataFrame(columns=["ts","net"])
    if i%50==0: print(" %d"%i, flush=True)
import pickle; pickle.dump(res, open(sys.argv[1] if len(sys.argv)>1 else "res.pkl","wb"))

def curve_stats(df, lo, hi, units=1):
    d=df[(df.ts>=lo)&(df.ts<hi)].sort_values("ts")
    if len(d)<20: return None
    p=d.net.values/units; yrs=max((d.ts.iloc[-1]-d.ts.iloc[0]).days/365.25,0.1)
    cum=np.cumsum(p); dd=abs(float((cum-np.maximum.accumulate(cum)).min()))
    w=p[p>0].sum(); l=abs(p[p<0].sum())
    return dict(net=p.sum(), dd=dd, mar=((p.sum()/yrs)/dd if dd else np.nan), pf=(w/l if l else np.inf), n=len(p))

def isc(df, lo, hi):
    d=df[(df.ts>=lo)&(df.ts<hi)]
    if len(d)<30: return None
    p=d.net.values; yrs=max((d.ts.iloc[-1]-d.ts.iloc[0]).days/365.25,0.1)
    cum=np.cumsum(p); dd=abs(float((cum-np.maximum.accumulate(cum)).min()))
    return dict(mar=((p.sum()/yrs)/dd if dd else np.nan), tpy=len(p)/yrs, net=p.sum())

START=pd.Timestamp("2010-06-07"); LB=pd.Timestamp(P.LB_END)
DATES=[pd.Timestamp("%d-08-13"%y) for y in range(2015,2026)]
dk=json.dumps(DEFAULT,sort_keys=True); ck=json.dumps(CROWN,sort_keys=True)
KS=[1,3,5,10,20,40]
rows=[]
for D in DATES:
    F=min(D+pd.DateOffset(years=1),LB)
    if F<=D: continue
    sc={k:isc(v,START,D) for k,v in res.items()}
    elig=[k for k,s in sc.items() if s and s["tpy"]>=120]
    if len(elig)<40: continue
    order=sorted(elig,key=lambda k:-sc[k]["mar"])
    row=dict(date=D.date())
    for K in KS:
        sel=order[:K]
        pooled=pd.concat([res[k] for k in sel]) if sel else None
        st=curve_stats(pooled,D,F,units=K) if pooled is not None else None
        row["net_k%d"%K]=st["net"] if st else np.nan
        row["mar_k%d"%K]=st["mar"] if st else np.nan
        row["dd_k%d"%K]=st["dd"] if st else np.nan
    for lab,key in (("def",dk),("crown",ck)):
        st=curve_stats(res[key],D,F)
        row["net_"+lab]=st["net"] if st else np.nan
        row["mar_"+lab]=st["mar"] if st else np.nan
        row["dd_"+lab]=st["dd"] if st else np.nan
    rows.append(row)
df=pd.DataFrame(rows); pd.set_option("display.width",250)
print("\n=== FORWARD YEAR, PER UNIT (net $ / K) ===")
print(df[["date"]+["net_k%d"%k for k in KS]+["net_def","net_crown"]].round(0).to_string(index=False))
print("\n=== FORWARD YEAR drawdown per unit ===")
print(df[["date"]+["dd_k%d"%k for k in KS]+["dd_def","dd_crown"]].round(0).to_string(index=False))
print("\n=== SUMMARY (11 forward years, per unit) ===")
for K in KS:
    v=df["net_k%d"%K]; d=df["dd_k%d"%K]
    print("  top-%-3d ensemble   total $%8.0f | mean/yr $%7.0f | mean DD $%7.0f | pos yrs %2d/%d"
          %(K,v.sum(),v.mean(),d.mean(),(v>0).sum(),len(v)))
for lab,name in (("def","leave alone      "),("crown","today's crown*   ")):
    v=df["net_"+lab]; d=df["dd_"+lab]
    print("  %s total $%8.0f | mean/yr $%7.0f | mean DD $%7.0f | pos yrs %2d/%d"
          %(name,v.sum(),v.mean(),d.mean(),(v>0).sum(),len(v)))
print("  (* crown params were chosen knowing these years - hindsight upper bound, not a competitor)")
for K in KS[1:]:
    a=df["net_k%d"%K]; b=df["net_def"]
    print("  top-%d beats leave-alone in %d of %d years; mean diff $%.0f"%(K,(a>b).sum(),len(a),(a-b).mean()))
