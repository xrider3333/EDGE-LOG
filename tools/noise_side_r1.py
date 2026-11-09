"""#174 line 3: NOISE #382 crown, long-only vs short-only split, PREREG_noise_side_r1_2026-11-09 (sha bef1416bcb97).
PYTHONPATH=. python tools/noise_side_r1.py [--write]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.drawdowns import four_numbers                 # noqa: E402
from augur_engine.engine import run_backtest                    # noqa: E402
from augur_engine.strategies import load_strategy               # noqa: E402
import run_record                                               # noqa: E402

RUN = r"C:\EdgeLog\_anatomy_cache\t74_giveback\run382.json"
C0, MULT = 0.533, 20.0
ST = {"preWF": ("2010-06-07", "2016-06-29"), "WF": ("2016-06-30", "2025-07-15"), "LB": ("2025-07-16", "2026-07-16")}
WRITE = "--write" in sys.argv
crown = dict(json.load(open(RUN))["validate"]["champion"])
s = load_strategy(os.path.join(os.getcwd(), "augur_strategies", "NOISE_1_8_CT304.py"))
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-07-16")
ix = pd.DatetimeIndex(A["index"]); ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
r = run_backtest(s, arrays=A, params=crown, cost_pts=C0, return_trades=True)
T = r["trades"]; S = r.get("trade_sizes") or [1.0] * len(T)
tr = pd.DataFrame({"d": [ix[max(int(t[0]) - 1, 0)].normalize() for t in T], "p": [float(t[2]) for t in T],
                   "sd": [int(t[3]) for t in T], "z": [float(z) for z in S]})
sess = pd.Index(sorted(set(ix.normalize())))
for c in (0.783, 0.283):
    for stg, (a, b) in ST.items():
        yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
        tot = None
        for side, nm in ((0, "BOTH"), (1, "LONG"), (-1, "SHORT")):
            m = tr[(tr.d >= a) & (tr.d <= b) & ((tr.sd == side) if side else True)]
            dly = ((m.p - m.z * (c - C0)) * MULT).groupby(m.d).sum().reindex(sess, fill_value=0.0)
            dly = dly[(dly.index >= a) & (dly.index <= b)]
            f = four_numbers(dly, years=yrs)
            tot = dly.sum() if side == 0 else tot
            sl = sum(z.sum() > 0 for z in np.array_split(dly.values, 8))
            print("%-5s %-5s cost %.3f tr/yr %4.0f net/yr %8.0f share %5.2f ROC %7.2f DD5 %7.0f DD%% %6.2f Sort %5.2f slices+ %d/8" % (
                stg, nm, c, len(m) / yrs, dly.sum() / yrs, dly.sum() / tot if tot else 0, f.get("roc30") or 0, f.get("dd5_usd") or 0,
                f.get("dd_pct_peak") or 0, f.get("sortino") or 0, sl), flush=True)
            if WRITE and side:
                run_record.append_record(run_record.build_record("NOISE", "lane", stg, strategy="NOISE #382 %s only (split)" % nm.lower(),
                                         family="NOISE", instrument="NQ", timeframe="5m", daily=dly, trades=len(m), cost_pt=c,
                                         note="PREREG_noise_side_r1_2026-11-09, crown trades split by side, re-costed per contract"))
