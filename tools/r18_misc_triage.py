"""
ROUND 18 — MISC hunt part 3: the overnight session + two intraday leftovers.

Pre-registered 2026-08-24 before any results. Window 2010-06-07 -> 2025-06-29,
lockbox never loaded. NQ 5m RTH master, $20/pt.

Concepts (whole grid, nothing added after):
  ONDRIFT - overnight drift: buy the RTH close, sell the next RTH open. The famous
            "all the index return happens overnight" effect. Cost 0.783 pts/RT
            (overnight Globex slip). Seam nights skipped. Cells: always / uptrend
            only (close>200d) / after a down RTH day / after an up RTH day /
            short in downtrend.
  VWTREND - VWAP pullback WITH the trend (the fade version died long ago): after
            10:30, if price is above session VWAP and a bar's low touches VWAP,
            buy the next bar open, ride to the close. Mirror short. Cells:
            long-only / both.  RT 0.533.
  AMBRK   - afternoon breakout: after 12:00, first close above the morning
            (9:30-12:00) high -> buy next bar open to the close. Mirror at the low.
            Buffer 0 or 0.25*ATR20. RT 0.533.

Gates: PF>=1.25, MAR>=8, n>=300 (ONDRIFT conditional cells and all others easily
clear 300 candidates; no floor substitution needed this round).
"""
import os, sys, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays

DATE_TO="2025-06-29"; MULT=20.0; RT=0.533; RT_ON=0.783
RESULTS=[]

def score(pnl,concept,cell):
    p=np.asarray(pnl,float)
    if len(p)==0: RESULTS.append(dict(concept=concept,cell=cell,n=0,net=0,pf=0,dd=0,mar=0)); return
    gw=p[p>0].sum(); gl=-p[p<0].sum(); pf=gw/gl if gl>1e-9 else float('inf')
    cum=np.cumsum(p); dd=float((cum-np.maximum.accumulate(cum)).min())
    net=float(p.sum()); mar=net/-dd if dd<-1e-9 else float('inf')
    RESULTS.append(dict(concept=concept,cell=cell,n=int(len(p)),net=net,pf=float(pf),dd=float(-dd),mar=float(mar)))

def main():
    m=find_master("NQ","5m","rth","db_noadj_rth")
    A=load_master_arrays(m,date_to=DATE_TO)
    o,h,l,c,v,did=A["open"],A["high"],A["low"],A["close"],A["volume"],A["day_id"]
    idx=A["index"]; mins=(idx.hour*60+idx.minute).values
    sess=[]; a=0; n=len(c)
    while a<n:
        b=a
        while b<n and did[b]==did[a]: b+=1
        sess.append((a,b)); a=b
    do=np.array([o[a] for a,b in sess]); dh=np.array([h[a:b].max() for a,b in sess])
    dl=np.array([l[a:b].min() for a,b in sess]); dc=np.array([c[b-1] for a,b in sess])
    nd=len(sess)
    gaps=np.abs(np.concatenate([[0.0],do[1:]-dc[:-1]])); seams=set()
    for d in range(1,nd):
        lo=max(0,d-60)
        if d-lo>=20:
            med=np.median(gaps[lo:d])
            if gaps[d]>=15.0 and gaps[d]>=2.5*med: seams.add(d)
    sma200=np.full(nd,np.nan)
    for d in range(199,nd): sma200[d]=dc[d-199:d+1].mean()
    print(f"days={nd} seams={len(seams)}")

    # ── ONDRIFT ──
    cells={"always":lambda d:True,
           "uptrend":lambda d:dc[d]>sma200[d],
           "after-down":lambda d:dc[d]<do[d],
           "after-up":lambda d:dc[d]>do[d],
           "short-downtrend":lambda d:dc[d]<sma200[d]}
    for name,cond in cells.items():
        side=-1 if name.startswith("short") else 1
        pnl=[]
        for d in range(210,nd-1):
            if (d+1) in seams or not cond(d): continue
            pnl.append((side*(do[d+1]-dc[d])-RT_ON)*MULT)
        score(pnl,"ONDRIFT",name)

    # ── VWTREND ──
    for both in (False,True):
        pnl=[]
        for d in range(21,nd):
            a,b=sess[d]
            cv=np.cumsum(v[a:b]); tp=(h[a:b]+l[a:b]+c[a:b])/3.0
            cpv=np.cumsum(tp*v[a:b])
            vwap=np.divide(cpv,cv,out=tp.copy(),where=cv>0)
            done=False
            for k in range(a,b-1):
                if mins[k]<630: continue
                j=k-a
                if not done and c[k]>vwap[j] and l[k]<=vwap[j]:
                    pnl.append(((c[b-1]-o[k+1])-RT)*MULT); done=True; break
                if not done and both and c[k]<vwap[j] and h[k]>=vwap[j]:
                    pnl.append((-(c[b-1]-o[k+1])-RT)*MULT); done=True; break
        score(pnl,"VWTREND","long" if not both else "both")

    # ── AMBRK ──
    for buf_atr in (0.0,0.25):
        pnl=[]
        for d in range(21,nd):
            a,b=sess[d]
            atr=(dh[d-20:d]-dl[d-20:d]).mean()
            hi=None; lo_=None; kk=None
            for k in range(a,b):
                if mins[k]<720:
                    hi=h[k] if hi is None else max(hi,h[k]); lo_=l[k] if lo_ is None else min(lo_,l[k])
                else:
                    kk=k; break
            if kk is None or hi is None: continue
            buf=buf_atr*atr
            for k in range(kk,b-1):
                if c[k]>hi+buf:
                    pnl.append(((c[b-1]-o[k+1])-RT)*MULT); break
                if c[k]<lo_-buf:
                    pnl.append((-(c[b-1]-o[k+1])-RT)*MULT); break
        score(pnl,"AMBRK",f"buf{buf_atr}")

    print(f"\n{'concept':8}{'cell':18}{'n':>6}{'net$':>12}{'PF':>7}{'DD$':>11}{'MAR':>7}  gate")
    for r in RESULTS:
        g="PASS" if (r['pf']>=1.25 and r['mar']>=8 and r['n']>=300) else "fail"
        print(f"{r['concept']:8}{r['cell']:18}{r['n']:>6}{r['net']:>12,.0f}{r['pf']:>7.3f}{r['dd']:>11,.0f}{r['mar']:>7.2f}  {g}")
    outdir=os.path.join(ROOT,"tools","r16_results"); os.makedirs(outdir,exist_ok=True)
    with open(os.path.join(outdir,"r18_triage.csv"),"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(RESULTS[0].keys())); w.writeheader(); w.writerows(RESULTS)
    print("saved tools/r16_results/r18_triage.csv")

if __name__=="__main__": main()
