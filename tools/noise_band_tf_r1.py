"""#174 line 2: NOISE #382 crown on NQ 1m / 2m / 5m, PREREG_noise_band_tf_r1_2026-11-09 (sha 7f396618ebda).
PYTHONPATH=. python tools/noise_band_tf_r1.py [--write]
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


def block_t(x, seed=5):
    x = np.asarray(x, float); n = len(x); rng = np.random.default_rng(seed); k = int(np.ceil(n / 20))
    st = rng.integers(0, n - 20, size=(2000, k))
    mu = np.array([np.concatenate([x[a:a + 20] for a in r])[:n].mean() for r in st])
    return x.mean() / mu.std()


D = {}
for tf in ("1m", "2m", "5m"):
    A = load_master_arrays(find_master("NQ", tf, "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-07-16")
    ix = pd.DatetimeIndex(A["index"]); ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    r = run_backtest(s, arrays=A, params=crown, cost_pts=C0, return_trades=True)
    T = r["trades"]; S = r.get("trade_sizes") or [1.0] * len(T)
    tr = pd.DataFrame({"d": [ix[max(int(t[0]) - 1, 0)].normalize() for t in T], "p": [float(t[2]) for t in T], "z": [float(z) for z in S]})
    sess = pd.Index(sorted(set(ix.normalize())))
    for c in (0.783, 0.283):
        dly = ((tr.p - tr.z * (c - C0)) * MULT).groupby(tr.d).sum().reindex(sess, fill_value=0.0)
        D[(tf, c)] = dly
        for stg, (a, b) in ST.items():
            sub = dly[(dly.index >= a) & (dly.index <= b)]; m = tr[(tr.d >= a) & (tr.d <= b)]
            yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
            f = four_numbers(sub, years=yrs)
            g = (m.p + m.z * C0).sum() / max(m.z.sum(), 1)
            print("%s %-5s cost %.3f tr/yr %5.0f gross/ct %.2f ROC %7.2f DD5 %7.0f DD%% %6.2f Sort %5.2f" % (
                tf, stg, c, len(m) / yrs, g, f.get("roc30") or 0, f.get("dd5_usd") or 0, f.get("dd_pct_peak") or 0, f.get("sortino") or 0), flush=True)
            if WRITE:
                run_record.append_record(run_record.build_record("NOISE", "lane", stg, strategy="NOISE #382 band tf %s" % tf, family="NOISE",
                                         instrument="NQ", timeframe=tf, daily=sub, trades=len(m), cost_pt=c,
                                         note="PREREG_noise_band_tf_r1_2026-11-09, crown re-costed per contract"))
w0, w1 = ST["WF"]
for tf in ("1m", "2m"):
    b, x = D[("5m", 0.783)], D[(tf, 0.783)]
    idx = b.index.intersection(x.index); idx = idx[(idx >= w0) & (idx <= w1)]
    diff = (x.reindex(idx, fill_value=0) - b.reindex(idx, fill_value=0))
    sl = np.array_split(diff.values, 8)
    top5 = np.sort(diff.values)[::-1][:5].sum() if diff.sum() > 0 else np.nan
    print("WF %s - 5m @0.783: lift $%.0f/yr, t %.2f, slices up %d/8, top5 share %.2f" % (
        tf, diff.sum() / ((pd.Timestamp(w1) - pd.Timestamp(w0)).days / 365.25), block_t(diff.values), sum(z.sum() > 0 for z in sl),
        top5 / diff.sum() if diff.sum() > 0 else float("nan")))
