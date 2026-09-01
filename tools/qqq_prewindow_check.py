"""QQQ dip family, FIXED round-25 parameters (no search at all), on two windows that the
whole hunt never touched: 1999-03-10 -> 2010-06-06 (dot-com crash + 2008) as a TRUE
out-of-sample holdout for the post-hoc QQQ choice, and the in-window 2010-2025 for
reference. Also SPY on the same pre-window as a control. $100k notional, 2 bps."""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("wfd", os.path.join(ROOT, "tools", "wfo_daily_dips.py"))
wfd = _ilu.module_from_spec(_sp); _sp.loader.exec_module(wfd)
_sp2 = _ilu.spec_from_file_location("wfb", os.path.join(ROOT, "tools", "wfo_daily_dips_books.py"))
wfb = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(wfb)
import yfinance as yf
FIXED = {"RSI": dict(rsi_len=2, thr=10, sma=200, exit=5), "DBL": dict(n=7, sma=200),
         "PB": dict(ema=20, sma=200, hold=10), "CAP": dict(rng_mult=1.5, close_q=0.25, hold=5)}
def tape(tk, start, end):
    df = yf.download(tk, start=start, end=end, interval="1d", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df[["Open","High","Low","Close"]].dropna()
    do,dh,dl,dc = (df[c].values.astype(float) for c in ["Open","High","Low","Close"])
    return wfd.Tape(tk, do, dh, dl, dc, [d.date() for d in df.index], set(), 1.0, 0.0, 0.0, etf=True)
for tk in ("QQQ", "SPY"):
    for (label, s, e, cut) in (("PRE-WINDOW 1999-2010", "1998-01-01", "2010-06-07", "1999-03-10"),
                               ("IN-WINDOW 2010-2025", "2009-01-01", "2025-06-30", "2010-06-07")):
        tp = tape(tk, s, e); cutd = pd.Timestamp(cut).date()
        legs = {}
        for mech, p in FIXED.items():
            legs[f"{tk}/{mech}"] = [(t[0], t[2]) for t in tp.trades(mech, p) if t[1] >= cutd]
        for mech, ser in legs.items():
            st = wfd.stats([z[1] for z in ser])
            print(f"{label:22} {mech:9} n={st['n']:4} net=${st['net']:>9,.0f} PF={st['pf']:.3f} DD=${st['dd']:>8,.0f} MAR={st['mar']:>6.2f}")
        ser = wfb.causal_scaled(legs); st = wfd.stats([z[1] for z in ser])
        y = wfb.yearly(ser); pos = sum(1 for v in y.values() if v > 0)
        print(f"{label:22} {tk} BOOK(4) n={st['n']:4} net=${st['net']:>9,.0f} PF={st['pf']:.3f} DD=${st['dd']:>8,.0f} MAR={st['mar']:>6.2f} yrs+ {pos}/{len(y)}\n", flush=True)
