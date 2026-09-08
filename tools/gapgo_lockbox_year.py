"""
Why did the GAPGO family lose its lockbox year (2025-08-13..2026-08-13)? (2026-09-08)
Runs GAPGO_1_0 (#330 params), GAPGO_TRAVEL_1_0 (#329 params) and the ORB crown (ORB_3_6_C2, its own
defaults) on the SAME lockbox year through the engine and prints month-by-month PnL, so the read is
"a bad year for the opening-momentum factor" vs "a bad year for these two files only".
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as _ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-08-13")
idx = pd.DatetimeIndex(A["index"])
LB0 = pd.Timestamp("2025-08-13", tz=idx.tz)


def defaults(fn):
    sp = _ilu.spec_from_file_location("m", fn); m = _ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


legs = [("GAPGO #330", "augur_strategies/GAPGO_1_0.py", dict(be_after_R=1.0, gap_mult=0.15, stop_mult=1.0, or_bars=2)),
        ("TRAVEL #329", "augur_strategies/GAPGO_TRAVEL_1_0.py", dict(be_after_R=1.0, clock_min=600, k_atr=0.2, stop_frac=1.0)),
        ("ORB crown C2", "augur_strategies/ORB_3_6_C2.py", defaults("augur_strategies/ORB_3_6_C2.py"))]
tab = {}
for lab, fn, p in legs:
    r = run_backtest(fn, arrays=A, params=p, cost_pts=0.533, return_trades=True)
    df = pd.DataFrame({"t": [idx[t[0]] for t in r["trades"]], "pnl": [t[2] * 20 for t in r["trades"]]})
    lb = df[df.t >= LB0]; pre = df[df.t < LB0]
    gw = lb.pnl[lb.pnl > 0].sum(); gl = -lb.pnl[lb.pnl < 0].sum()
    print(f"{lab:14} PRE n={len(pre):5} net=${pre.pnl.sum():>9,.0f} PF={pre.pnl[pre.pnl>0].sum()/-pre.pnl[pre.pnl<0].sum():.3f} | "
          f"LOCKBOX n={len(lb):4} net=${lb.pnl.sum():>8,.0f} PF={gw/gl if gl else 99:.3f} win={100*(lb.pnl>0).mean():.0f}%")
    tab[lab] = lb.groupby(lb.t.dt.to_period("M")).pnl.sum().round(0)
    # the same year's earlier analogues: each of the last 5 Aug-Aug years
    for y in range(2020, 2025):
        a0 = pd.Timestamp(f"{y}-08-13", tz=idx.tz); a1 = pd.Timestamp(f"{y+1}-08-13", tz=idx.tz)
        s = df[(df.t >= a0) & (df.t < a1)]
        print(f"      {y}-{y+1} Aug-Aug: n={len(s):4} net=${s.pnl.sum():>8,.0f}", end="")
    print()
print("\nmonth-by-month in the lockbox year ($):")
print(pd.DataFrame(tab).fillna(0).astype(int).to_string())
