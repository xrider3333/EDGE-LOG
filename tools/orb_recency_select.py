# -*- coding: utf-8 -*-
"""Does selecting on RECENT data have the forward skill that all-history selection lacks?

The meta walk-forward showed picking on ALL history beats leaving the parameters alone in only 3
of 11 forward years. Separately, the ORB edge is measurably stronger in the second half of its
history on configs nobody selected. If the tape genuinely changed, a selector that looks only at
the recent past should do better than one that averages over a regime that no longer exists.
Same protocol as the meta walk-forward: decide on data before the date, trade the winner for the
next year, never overlap, never look past the sealed end."""
import sys, pickle, json, itertools, numpy as np, pandas as pd
sys.path.insert(0,r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P
res=pickle.load(open(sys.argv[1],"rb"))
GRID=dict(or_bars=[1,2,3],stop_frac=[2.0,2.5,3.0],target_R=[4.0,5.0,5.5,6.0],
          be_after_R=[0.5,1.0],atr_filter=[0.7,0.75],vpace_filter=[0.7,0.8])
KEYS=list(GRID); DEFAULT={k:P.BASE[k] for k in KEYS}
dk=json.dumps(DEFAULT,sort_keys=True)
LB=pd.Timestamp(P.LB_END); START=pd.Timestamp("2010-06-07")
def sc(df,lo,hi,minn=30):
    d=df[(df.ts>=lo)&(df.ts<hi)]
    if len(d)<minn: return None
    p=d.net.values; yrs=max((d.ts.iloc[-1]-d.ts.iloc[0]).days/365.25,.1)
    cum=np.cumsum(p); dd=abs(float((cum-np.maximum.accumulate(cum)).min()))
    w=p[p>0].sum(); l=abs(p[p<0].sum())
    return dict(mar=((p.sum()/yrs)/dd if dd else np.nan),net=p.sum(),tpy=len(p)/yrs,
                pf=(w/l if l else np.inf))
LOOKBACKS=[("all history",None),("last 5y",5),("last 3y",3),("last 2y",2)]
RULES=[("MAR","mar"),("PF","pf")]
DATES=[pd.Timestamp("%d-08-13"%y) for y in range(2015,2026)]
out={}
rows=[]
for D in DATES:
    F=min(D+pd.DateOffset(years=1),LB)
    if F<=D: continue
    fwd={k:sc(v,D,F,20) for k,v in res.items()}
    row={"date":D.date()}
    for lname,yb in LOOKBACKS:
        lo=START if yb is None else max(START,D-pd.DateOffset(years=yb))
        s={k:sc(v,lo,D) for k,v in res.items()}
        elig=[k for k,x in s.items() if x and x["tpy"]>=120]
        if not elig: continue
        for rname,key in RULES:
            pick=max(elig,key=lambda k:s[k][key])
            row["%s|%s"%(lname,rname)]=fwd[pick]["net"] if fwd.get(pick) else np.nan
    row["leave alone"]=fwd[dk]["net"] if fwd.get(dk) else np.nan
    fn=np.array([fwd[k]["net"] for k in res if fwd.get(k)])
    row["random config"]=float(np.median(fn))
    rows.append(row)
df=pd.DataFrame(rows); pd.set_option("display.width",250)
print("=== forward-year net $ by SELECTOR ===")
print(df.round(0).to_string(index=False))
print("\n=== TOTALS over %d forward years ==="%len(df))
base=df["leave alone"]
for c in [c for c in df.columns if c!="date"]:
    v=df[c]
    print("  %-22s total $%8.0f | mean/yr $%7.0f | pos %2d/%d | beats leave-alone %2d/%d"
          %(c,v.sum(),v.mean(),(v>0).sum(),len(v),(v>base).sum(),len(v)))
