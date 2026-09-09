"""
Is GAPGO a new family or the ORB crown wearing a gap filter? (2026-09-08)

Runs GAPGO_1_0 (defaults) and the ORB crown #234 (ORB_3_6_C2 with its DEFAULT_PARAMS passed
explicitly - the engine does not merge them) on the same NQ 5m RTH window through the real
engine, then measures: shared trade DAYS, same-direction share on shared days, daily-PnL
correlation, and what each adds to the other as a 1:1 pooled book (DD and n/DD).
Also the NOISE crown for a third reference if its file is present.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as _ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
dates = pd.DatetimeIndex(A["index"]).date


def defaults(fn):
    sp = _ilu.spec_from_file_location("m", fn); m = _ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def daily(fn, mult=20.0):
    r = run_backtest(fn, arrays=A, params=defaults(fn), cost_pts=0.533, return_trades=True)
    tr = r["trades"]
    df = pd.DataFrame({"day": [dates[t[0]] for t in tr], "pnl": [t[2] * mult for t in tr],
                       "side": [t[3] for t in tr]})
    print(f"{os.path.basename(fn):22} n={len(df):5} net=${df.pnl.sum():>10,.0f} PF={r['profit_factor']:.3f} "
          f"DD=${-r['max_drawdown']*mult:,.0f}")
    return df


def book(dfs, label):
    # SORT_INDEX IS LOAD-BEARING (added 2026-09-09, round 41): pd.concat on two `datetime.date`
    # indexes returns their UNION IN UNSORTED ORDER, so the cumsum below walks the calendar out
    # of order and the "drawdown" it reports is meaningless. The bug is invisible without a
    # bound to check it against -- use this one: a sum's max drawdown can never exceed the sum
    # of its parts' max drawdowns. On THIS file's own pair the error is small (GAPGO+ORB reads
    # n/DD 10.82 unsorted vs 10.63 sorted) because these date sets nearly sort themselves, but
    # it is unbounded in general: tools/r41_bar_ladder_overlap.py hit a pair that read
    # DD $222,772 unsorted against parts of $13,092 and $18,425 (bound $31,517) -- n/DD 2.62
    # where the truth was 24.40. Never cumsum a concatenated daily series without sorting first.
    s = pd.concat([d.groupby("day").pnl.sum() for d in dfs], axis=1).sort_index().fillna(0).sum(axis=1)
    assert s.index.is_monotonic_increasing, "pooled daily index is not in calendar order"
    cum = s.cumsum(); dd = float((cum - cum.cummax()).min()); net = float(s.sum())
    print(f"  BOOK {label:28} net=${net:>10,.0f} DD=${-dd:>9,.0f} n/DD={net/-dd if dd < 0 else 99:5.2f}")
    return s


g = daily("augur_strategies/GAPGO_1_0.py")
o = daily("augur_strategies/ORB_3_6_C2.py")
gd = g.groupby("day").pnl.sum(); od = o.groupby("day").pnl.sum()
both = gd.index.intersection(od.index)
print(f"\nshared trade days: {len(both)} of GAPGO {len(gd)} / ORB {len(od)}")
gs = g.groupby("day").side.first().reindex(both); os_ = o.groupby("day").side.first().reindex(both)
print(f"same direction on shared days: {100*float((gs == os_).mean()):.0f}%")
al = pd.concat([gd, od], axis=1).fillna(0); al.columns = ["gapgo", "orb"]
print(f"daily-PnL correlation (all days, zeros filled): {al.gapgo.corr(al.orb):.3f}")
al2 = al.loc[both]
print(f"daily-PnL correlation (shared days only):       {al2.gapgo.corr(al2.orb):.3f}")
print()
book([o], "ORB crown alone")
book([g], "GAPGO alone")
book([o, g], "ORB + GAPGO 1:1")
# what GAPGO earns on days ORB did NOT trade
solo = gd.drop(both, errors="ignore")
print(f"\nGAPGO on ORB-free days: n_days={len(solo)} net=${solo.sum():,.0f}; on shared days net=${gd.loc[both].sum():,.0f}")
nf = "augur_strategies/NOISE_1_2_RYR.py"
if os.path.exists(nf):
    try:
        nz = daily(nf)
        nd_ = nz.groupby("day").pnl.sum()
        al3 = pd.concat([gd, nd_], axis=1).fillna(0); al3.columns = ["gapgo", "noise"]
        print(f"daily-PnL correlation GAPGO vs NOISE_1_2_RYR: {al3.gapgo.corr(al3.noise):.3f}")
        book([o, nz, g], "ORB + NOISE + GAPGO")
        book([o, nz], "ORB + NOISE")
    except Exception as e:
        print("NOISE reference skipped:", e)
