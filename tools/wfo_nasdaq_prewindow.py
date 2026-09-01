"""Does the WALK-FORWARD PROCESS itself (fine grid, per-fold re-selection) hold up in the
1999-2010 regime (dot-com crash + 2008), where the FIXED params were weak? QQQ and SPY
(control), $100k notional, 2 bps. OOS-only, 8 folds after a 2-year warm-up."""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import importlib.util as _ilu
def load(name, fn):
    sp = _ilu.spec_from_file_location(name, os.path.join(ROOT, "tools", fn)); m = _ilu.module_from_spec(sp); sp.loader.exec_module(m); return m
wfd = load("wfd", "wfo_daily_dips.py"); wfb = load("wfb", "wfo_daily_dips_books.py"); wnf = load("wnf", "wfo_nasdaq_fine.py")
wnf.FOLDS = 8
import yfinance as yf
def tape(tk):
    df = yf.download(tk, start="1998-01-01", end="2010-06-07", interval="1d", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df[["Open","High","Low","Close"]].dropna()
    do,dh,dl,dc = (df[c].values.astype(float) for c in ["Open","High","Low","Close"])
    return wnf.FineTape(wfd.Tape(tk, do, dh, dl, dc, [d.date() for d in df.index], set(), 1.0, 0.0, 0.0, etf=True))
for tk in ("QQQ", "SPY"):
    tp = tape(tk); legs = {}; joint = {}
    for mech, grid in wnf.GRIDS.items():
        all_tr = {ci: tp.trades(mech, p) for ci, p in enumerate(grid)}
        oos, chosen, fold_nets, is_avg = wnf.wfo12(all_tr, tp.dates)
        st = wfd.stats([z[1] for z in oos]); pos = sum(1 for f in fold_nets if f > 0)
        legs[f"{tk}/{mech}"] = oos
        print(f"PRE-WINDOW WFO {tk} {mech:4} OOS n={st['n']:4} net=${st['net']:>9,.0f} PF={st['pf']:.3f} DD=${st['dd']:>8,.0f} MAR={st['mar']:>6.2f} folds+ {pos}/8", flush=True)
    ser = wfb.causal_scaled(legs); st = wfd.stats([z[1] for z in ser])
    y = wfb.yearly(ser); pos = sum(1 for v in y.values() if v > 0)
    print(f"PRE-WINDOW WFO {tk} BOOK(4) n={st['n']:4} net=${st['net']:>9,.0f} PF={st['pf']:.3f} DD=${st['dd']:>8,.0f} MAR={st['mar']:>6.2f} yrs+ {pos}/{len(y)}\n", flush=True)
