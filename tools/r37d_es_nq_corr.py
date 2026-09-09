"""
ROUND 37d — is the ENGU-Q ES leg a RETURN diversifier or just an account diversifier? (2026-09-08)
The R2 crown file at its defaults on NQ 1m ETH (0.783/RT, $20/pt) and ES 1m ETH (0.40/RT, $50/pt),
2010-06-07..2025-06-29; PnL aggregated by EXIT day; correlation daily and monthly; 1:1 pool vs each alone.
Result on first run: daily corr 0.20, monthly 0.21, 685 shared entry days of 1148/1262;
NQ alone n/DD 13.2, ES alone 7.5 (daily-aggregated), NQ+ES 1:1 = $720,491 / DD $44,896 / n/DD 16.1.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

fn = "augur_strategies/ENGUQ_1M_ETH_R2_1_0.py"
sp = ilu.spec_from_file_location("m", fn); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
P = {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}
out = {}
for inst, cost, mult in (("NQ", 0.783, 20.0), ("ES", 0.40, 50.0)):
    A = load_master_arrays(find_master(inst, "1m", "eth", "db_noadj_eth"), date_from="2010-06-07", date_to="2025-06-29")
    idx = pd.DatetimeIndex(A["index"])
    r = run_backtest(fn, arrays=A, params=P, cost_pts=cost, return_trades=True)
    df = pd.DataFrame({"d": [idx[t[1]].date() for t in r["trades"]], "pnl": [t[2] * mult for t in r["trades"]],
                       "e": [idx[t[0]].date() for t in r["trades"]]})
    out[inst] = df
    print(f"{inst}: n={len(df)} net=${df.pnl.sum():,.0f}", flush=True)
nq = out["NQ"].groupby("d").pnl.sum(); es = out["ES"].groupby("d").pnl.sum()
# sort_index IS LOAD-BEARING (round 41 lesson): pd.concat on two date-object indexes returns the
# UNION IN UNSORTED ORDER, so a cumsum below would walk the calendar out of order and the
# "drawdown" it reports would be meaningless. Sort, then assert.
al = pd.concat([nq, es], axis=1).sort_index().fillna(0); al.columns = ["nq", "es"]
assert al.index.is_monotonic_increasing, "pooled daily index is not in calendar order"
print(f"exit-day PnL correlation (zeros filled): {al.nq.corr(al.es):.3f}")
mo = al.groupby(pd.to_datetime(al.index).to_period("M")).sum(); print(f"monthly PnL correlation: {mo.nq.corr(mo.es):.3f}")
shared = set(out["NQ"].e) & set(out["ES"].e)
print(f"shared ENTRY days: {len(shared)} of NQ {out['NQ'].e.nunique()} / ES {out['ES'].e.nunique()}")
for lab, s in (("NQ alone", al.nq), ("ES alone", al.es), ("NQ+ES 1:1", al.sum(axis=1))):
    cum = s.cumsum(); dd = float((cum - cum.cummax()).min())
    print(f"  {lab:10} net=${s.sum():>9,.0f} DD=${-dd:>8,.0f} n/DD={s.sum()/-dd:5.2f}")
