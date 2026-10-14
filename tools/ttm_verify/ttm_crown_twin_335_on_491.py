"""TTM crown re-check #491 - TWIN (context, disclosed; written after #491's output sha was posted): crown #335's champion with the cap OFF
(max_hold_bars 0) in #491's own file / master / window / cost / cut, booked by the same functions - the like-for-like twin
(#335's own run doc reads a different master, NOADJ, rewritten 10-14 15:26, and cost 0.533)."""
import importlib.util
import json
import os
import types

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("cw", __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "ttm_crown_wf.py"))
CW = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CW)
_, d = CW.run_doc("491")
_, d335 = CW.run_doc("335")
w = d["validate"]["windows"]
M = CW.find_master(d["instrument"], d["timeframe"], "eth", d["data_source"])
A = CW.load_master_arrays(M, date_from=d["date_from"], date_to=w["optimize"][1])
idx = pd.DatetimeIndex(A["index"]); idxn = idx.tz_localize(None)
fp = os.path.join(CW.REPO, "augur_strategies", d["strategy"])
m = types.ModuleType("twin335"); m.__file__ = fp
exec(compile(open(fp, encoding="utf-8").read(), fp, "exec"), m.__dict__)
P = dict(d335["validate"]["champion"], max_hold_bars=0)
r = CW.run_backtest(m, instrument=d["instrument"], arrays=A, params=P, cost_pts=0.0, return_trades=True)
mult = float(d["multiplier"])
b0 = 2034525
out = {"params": P, "master": M["filename"], "n_trades_all": len(r["trades"])}
for lab, c in (("house_cost", float(d["cost_pts"])), ("real_cost", CW.REAL_COST_PTS["NQ"])):
    H = CW.leg_rows(r, idx, c, mult)
    K = H[H["eb"] >= b0]
    opt1 = pd.Timestamp(w["optimize"][1])
    cal = pd.DatetimeIndex(sorted(set(idxn.normalize()[(idxn >= idxn[b0].normalize()) & (idxn < opt1 + pd.Timedelta(days=1))]) | set(K["exit"].dt.normalize())))
    out[lab] = {"wf_trades": int(len(K)), "wf_pts": float(K["usd"].sum() / mult), "is_trades": int((H["eb"] < b0).sum()),
                "closed": CW.four(CW.daily_closed(K, cal), cal),
                "valued_daily": CW.four(CW.daily_mtm(K, cal, np.asarray(A["close"], float), idxn, mult), cal)}
print(json.dumps(out, indent=1, default=float))
json.dump(out, open("C:/EdgeLog/_anatomy_cache/ttm_crownwf/twin_335_on_491.json", "w"), indent=1, default=float)
