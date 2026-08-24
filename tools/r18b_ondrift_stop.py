"""
ROUND 18b — overnight drift / uptrend, now with a REAL overnight stop.

Owner point (2026-08-24): "its futures. im sure we can manage a SL on ETH."
Correct — the stop is monitored bar-by-bar on the NQ 1m ETH tape (the 24h data).

Pre-registered before results:
- Base cell is frozen from round 18: buy the RTH close when close > 200-day SMA,
  sell the next RTH open. Same window 2010-06-07 -> 2025-06-29, roll nights skipped.
- Stop grid (whole grid): none, and {0.5, 1.0, 1.5} x ATR20 (20-day average daily
  range) below the entry price. Monitored on every 1m ETH bar between the RTH close
  and the next RTH open. Gap-honest fills: if a bar OPENS below the stop, the fill
  is that bar's open (you get the worse price); otherwise the stop price.
  Stop-outs stay flat until morning (no re-entry).
- Cost 0.783 pts/RT everywhere (overnight Globex slip already priced).
- Parity gate: the "none" cell must reproduce round 18's $282,478 to the dollar.
"""
import os, sys, csv
import numpy as np

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)
from augur_engine.data import find_master, load_master_arrays

DATE_TO="2025-06-29"; MULT=20.0; RT_ON=0.783

def main():
    mr=find_master("NQ","5m","rth","db_noadj_rth")
    R=load_master_arrays(mr,date_to=DATE_TO)
    o,h,l,c,did=R["open"],R["high"],R["low"],R["close"],R["day_id"]; idx=R["index"]
    sess=[]; a=0; n=len(c)
    while a<n:
        b=a
        while b<n and did[b]==did[a]: b+=1
        sess.append((a,b)); a=b
    do=np.array([o[x] for x,y in sess]); dh=np.array([h[x:y].max() for x,y in sess])
    dl=np.array([l[x:y].min() for x,y in sess]); dc=np.array([c[y-1] for x,y in sess])
    nd=len(sess)
    gaps=np.abs(np.concatenate([[0.0],do[1:]-dc[:-1]])); seams=set()
    for d in range(1,nd):
        lo=max(0,d-60)
        if d-lo>=20:
            med=np.median(gaps[lo:d])
            if gaps[d]>=15.0 and gaps[d]>=2.5*med: seams.add(d)
    sma=np.full(nd,np.nan)
    for d in range(199,nd): sma[d]=dc[d-199:d+1].mean()
    atr20=np.full(nd,np.nan)
    for d in range(20,nd): atr20[d]=(dh[d-20:d]-dl[d-20:d]).mean()
    day_end_ts=np.array([idx[y-1].value for x,y in sess])   # ns epoch of RTH close bar
    day_open_ts=np.array([idx[x].value for x,y in sess])

    me=find_master("NQ","1m","eth","db_noadj_eth")
    E=load_master_arrays(me,date_to=DATE_TO)
    eo,el=E["open"],E["low"]; ets=E["index"].values.astype("int64")
    print(f"rth days={nd}  eth bars={len(eo)}")

    nights=[]   # (d, entry_px, exit_px_morning, atr)
    for d in range(210,nd-1):
        if (d+1) in seams or not dc[d]>sma[d]: continue
        nights.append((d,dc[d],do[d+1],atr20[d]))
    print(f"nights={len(nights)}")

    grid=[None,0.5,1.0,1.5]
    rows=[]
    for sm in grid:
        pnl=[]; stops=0
        for d,ent,ex_am,atr in nights:
            if sm is None:
                pnl.append(((ex_am-ent)-RT_ON)*MULT); continue
            stop=ent-sm*atr
            i0=np.searchsorted(ets,day_end_ts[d]+1)      # first ETH bar after RTH close
            i1=np.searchsorted(ets,day_open_ts[d+1])     # first ETH bar at/after next RTH open
            fill=None
            for i in range(i0,i1):
                if eo[i]<=stop: fill=eo[i]; break
                if el[i]<=stop: fill=stop; break
            if fill is not None:
                stops+=1; pnl.append(((fill-ent)-RT_ON)*MULT)
            else:
                pnl.append(((ex_am-ent)-RT_ON)*MULT)
        p=np.array(pnl); net=p.sum(); gw=p[p>0].sum(); gl=-p[p<0].sum()
        cum=np.cumsum(p); dd=(cum-np.maximum.accumulate(cum)).min()
        rows.append(dict(stop=("none" if sm is None else f"{sm}xATR"),n=len(p),stopped=stops,
                         net=round(float(net)),pf=round(float(gw/gl),3),dd=round(float(-dd)),
                         mar=round(float(net/-dd),2),worst=round(float(p.min()))))
        r=rows[-1]
        print(f"stop {r['stop']:8} stopped {stops:5}  net ${r['net']:>9,} PF {r['pf']:.3f} DD ${r['dd']:>7,} MAR {r['mar']:>6.2f} worst ${r['worst']:,}")
    with open(os.path.join(ROOT,"tools","r16_results","r18b_stops.csv"),"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("saved tools/r16_results/r18b_stops.csv")

if __name__=="__main__": main()
