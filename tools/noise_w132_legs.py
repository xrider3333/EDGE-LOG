"""w132 alpha re-scan (NOISE lane): one-unit daily $ leg CSVs, cut at 2025-06-30, for owner_screen.py.
Legs: NOISE #382 crown frozen on ES 5m (cost 0.613, $50), on NQ 2m (0.783, $20), and on ES 2m;
TRAPFADE (w121, both arms) and NOISE-BRK-R (w118) at 0.783 over 2010-06-07..2025-06-30.
PYTHONPATH=. python tools/noise_w132_legs.py
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.strategies import load_strategy

OUT = r"C:\EdgeLog\manager\reports\w132_noise"
os.makedirs(OUT, exist_ok=True)
END = "2025-06-30"
crown = dict(json.load(open(r"C:\EdgeLog\_anatomy_cache\t74_giveback\run382.json"))["validate"]["champion"])
s = load_strategy(os.path.join(os.getcwd(), "augur_strategies", "NOISE_1_8_CT304.py"))


def arrays(inst, tf):
    if tf == "2m" and inst == "ES":
        A = load_master_arrays(find_master("ES", "1m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=END)
        ix = pd.DatetimeIndex(A["index"])
        df = pd.DataFrame({k: A[k] for k in ("open", "high", "low", "close", "volume")}, index=ix)
        r = df.resample("2min", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        B = {k: r[k].to_numpy(float) for k in r.columns}
        B["index"] = r.index
        nd = r.index.tz_convert("America/New_York").normalize() if r.index.tz is not None else r.index.normalize()
        B["day_id"] = pd.factorize(nd)[0]
        B["meta"] = A.get("meta", {})
        return B
    return load_master_arrays(find_master(inst, tf, "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=END)


def noise_leg(name, inst, tf, cost, mult):
    A = arrays(inst, tf)
    ix = pd.DatetimeIndex(A["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    r = run_backtest(s, arrays=A, params=crown, cost_pts=0.533, return_trades=True)
    T = r["trades"]; S = r.get("trade_sizes") or [1.0] * len(T)
    d = pd.DataFrame({"date": [ix[min(int(t[1]), len(ix) - 1)].normalize() for t in T],
                      "pnl": [(float(t[2]) - float(z) * (cost - 0.533)) * mult for t, z in zip(T, S)], "trades": 1})
    d.groupby("date").sum().to_csv(os.path.join(OUT, name + ".csv"))
    print(name, len(T), "trades, net $%.0f" % d.pnl.sum(), flush=True)


noise_leg("noise382_ES_5m", "ES", "5m", 0.613, 50.0)
noise_leg("noise382_NQ_2m", "NQ", "2m", 0.783, 20.0)
noise_leg("noise382_ES_2m", "ES", "2m", 0.613, 50.0)
