"""
ROUND 19b — NEW INSTRUMENTS, zero-cost data path: the multi-day classics on four
uncorrelated ETFs (gold GLD, long bonds TLT, small caps IWM, oil USO) + QQQ control.

Owner direction 2026-08-24: "both" (filters on champions + new instruments). The
futures data buy needs owner action (Alpaca keys / Databento); daily ETF history is
free via the same Yahoo path the app already uses, and the round-17 hold-for-days
playbook only needs daily bars — so the classics get their out-of-family test NOW.

Pre-registered before results:
- Data: Yahoo daily OHLC, auto_adjust=True (split+dividend adjusted = total-return
  prices — fair for multi-day holds, holders receive distributions; also removes
  USO's 2020 1:8 reverse split). Window 2006-01-01 -> 2025-06-29. Later data = sealed.
- Execution: signal on close of day d -> enter at day d+1 OPEN; exit signal on close
  -> exit next OPEN. No stop (r17 convention). No roll seams (ETFs are continuous).
- Sizing/costs: $100,000 notional per trade (shares = 100000/entry). Cost per round
  trip = 2 basis points of notional ($20) + $0 commission — generous for these ETFs.
- Cells per instrument (frozen r17 shapes, no re-tuning): RSI2 thr10 long / both,
  DBL7 long, DONCH 20/10, PB20 long / both. 6 cells x 5 tickers = 30. One look.
- Gates: PF >= 1.25, MAR >= 8, n >= 150 (r17 multi-day floor).
"""
import os, sys, csv
import numpy as np
import pandas as pd

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIONAL=100_000.0; COST_RT=20.0
RESULTS=[]

def wilder_rsi(x,per):
    d=np.diff(x,prepend=x[0]); up=np.where(d>0,d,0.0); dn=np.where(d<0,-d,0.0)
    au=np.zeros_like(x); ad=np.zeros_like(x)
    au[per]=up[1:per+1].mean(); ad[per]=dn[1:per+1].mean()
    for i in range(per+1,len(x)):
        au[i]=(au[i-1]*(per-1)+up[i])/per; ad[i]=(ad[i-1]*(per-1)+dn[i])/per
    rs=np.divide(au,ad,out=np.full_like(x,np.inf),where=ad>1e-12)
    return 100-100/(1+rs)

def score(pnl,tick,cell):
    p=np.asarray(pnl,float)
    if len(p)==0:
        RESULTS.append(dict(ticker=tick,cell=cell,n=0,net=0,pf=0,dd=0,mar=0)); return
    gw=p[p>0].sum(); gl=-p[p<0].sum(); pf=gw/gl if gl>1e-9 else float('inf')
    cum=np.cumsum(p); dd=float((cum-np.maximum.accumulate(cum)).min())
    net=float(p.sum()); mar=net/-dd if dd<-1e-9 else float('inf')
    RESULTS.append(dict(ticker=tick,cell=cell,n=int(len(p)),net=round(net),
                        pf=round(float(pf),3),dd=round(float(-dd)),mar=round(float(mar),2)))

def run(do,dh,dl,dc,ent,ex,max_hold=None,start=210):
    nd=len(dc); pnl=[]; pos=0; de=0; d=start
    while d<nd-1:
        if pos==0:
            s=ent(d)
            if s!=0: pos,de=s,d+1; d+=1; continue
        else:
            if d>=de and (ex(d,pos,de) or (max_hold and d-de>=max_hold)):
                sh=NOTIONAL/do[de]
                raw=(do[d+1]-do[de])*sh
                pnl.append(pos*raw-COST_RT); pos=0
        d+=1
    return pnl

def main():
    try:
        import yfinance as yf
        dfs={s:yf.download(s,start="2006-01-01",end="2025-06-30",interval="1d",
                           auto_adjust=True,progress=False) for s in ["GLD","TLT","IWM","USO","QQQ"]}
    except Exception as e:
        print("yfinance failed:",e); sys.exit(1)
    for tick,df in dfs.items():
        if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        df=df[["Open","High","Low","Close"]].dropna()
        do,dh,dl,dc=(df[c].values.astype(float) for c in ["Open","High","Low","Close"])
        nd=len(dc)
        sma200=np.full(nd,np.nan); sma5=np.full(nd,np.nan)
        for d in range(199,nd): sma200[d]=dc[d-199:d+1].mean()
        for d in range(4,nd): sma5[d]=dc[d-4:d+1].mean()
        k=2/21; ema20=np.full(nd,np.nan); ema20[19]=dc[:20].mean()
        for d in range(20,nd): ema20[d]=ema20[d-1]+k*(dc[d]-ema20[d-1])
        rsi2=wilder_rsi(dc,2)
        for both in (False,True):
            def ent(d,both=both):
                if dc[d]>sma200[d] and rsi2[d]<10: return 1
                if both and dc[d]<sma200[d] and rsi2[d]>90: return -1
                return 0
            def ex(d,pos,de): return (dc[d]>sma5[d]) if pos>0 else (dc[d]<sma5[d])
            score(run(do,dh,dl,dc,ent,ex),tick,f"RSI2/{'both' if both else 'long'}")
        def ent7(d):
            if d<7: return 0
            return 1 if (dc[d]>sma200[d] and dc[d]==dc[d-6:d+1].min()) else 0
        def ex7(d,pos,de): return dc[d]==dc[d-6:d+1].max()
        score(run(do,dh,dl,dc,ent7,ex7),tick,"DBL7/long")
        def entD(d):
            if d<20: return 0
            if dc[d]>=dh[d-20:d].max(): return 1
            if dc[d]<=dl[d-20:d].min(): return -1
            return 0
        def exD(d,pos,de):
            if d<10: return False
            return (dc[d]<=dl[d-10:d].min()) if pos>0 else (dc[d]>=dh[d-10:d].max())
        score(run(do,dh,dl,dc,entD,exD),tick,"DONCH/20-10")
        for both in (False,True):
            def entP(d,both=both):
                if dc[d]>sma200[d] and dl[d]<=ema20[d] and dc[d-1]>ema20[d-1]: return 1
                if both and dc[d]<sma200[d] and dh[d]>=ema20[d] and dc[d-1]<ema20[d-1]: return -1
                return 0
            def exP(d,pos,de): return (dc[d]>dh[de-1]) if pos>0 else (dc[d]<dl[de-1])
            score(run(do,dh,dl,dc,entP,exP,10),tick,f"PB20/{'both' if both else 'long'}")
    print(f"{'ticker':7}{'cell':14}{'n':>5}{'net$':>10}{'PF':>7}{'DD$':>9}{'MAR':>7}  gate")
    for r in RESULTS:
        g="PASS" if (r['pf']>=1.25 and r['mar']>=8 and r['n']>=150) else "fail"
        print(f"{r['ticker']:7}{r['cell']:14}{r['n']:>5}{r['net']:>10,}{r['pf']:>7.3f}{r['dd']:>9,}{r['mar']:>7.2f}  {g}")
    with open(os.path.join(ROOT,"tools","r16_results","r19_etf.csv"),"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(RESULTS[0].keys())); w.writeheader(); w.writerows(RESULTS)
    print("saved tools/r16_results/r19_etf.csv")

if __name__=="__main__": main()
