"""TTM crown re-check - TRACE (written AFTER the output sha was posted, disclosed): the validate's IS/WF cut is
_wfB0 = the first anchored fold's train_bars (augur_engine/validate.py:450), a BAR INDEX that can sit inside a day; the harness
cut at the first bar of the wf_split DATE. Re-slice the same trades at the stored bar and re-compare with cal.is / cal.wf."""
import importlib.util
import json
import sys

import numpy as np
import pandas as pd

run = sys.argv[1]
spec = importlib.util.spec_from_file_location("cw", "C:/EdgeLog/_anatomy_cache/ttm_crownwf/ttm_crown_wf.py")
CW = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CW)
import types, os                                                    # noqa: E402,E401
_, d = CW.run_doc(run)
db = CW.RW.real_client()
t10 = CW.RW.run_ref(db, int(run)).get(field_paths=["top10_results"]).to_dict().get("top10_results") or []
tb = sorted({int(r["train_bars"]) for r in t10 if r.get("fold") == 1 and r.get("train_bars")})
v, w = d["validate"], d["validate"]["windows"]
sess = "rth" if str(d["data_source"]).endswith("rth") else "eth"
M = CW.find_master(d["instrument"], d["timeframe"], sess, d["data_source"])
A = CW.load_master_arrays(M, date_from=d["date_from"], date_to=w["optimize"][1])
idx = pd.DatetimeIndex(A["index"])
fp = os.path.join(CW.REPO, "augur_strategies", d["strategy"])
m = types.ModuleType("trace_%s" % run); m.__file__ = fp
exec(compile(open(fp, encoding="utf-8").read(), fp, "exec"), m.__dict__)
P = dict(v["champion"])
r = CW.run_backtest(m, instrument=d["instrument"], arrays=A, params=P, cost_pts=0.0, return_trades=True)
H = CW.leg_rows(r, idx, float(d["cost_pts"]), float(d["multiplier"]))
st = [c for c in d["selection"]["candidates"] if c.get("params") == P][0]["cal"]
out = {"fold1_train_bars": tb, "date_cut_bar": int(np.searchsorted(idx.tz_localize(None), pd.Timestamp(w["wf_split"])))}
for b0 in tb:
    out["at_bar_%d" % b0] = {"bar_time": str(idx[b0]),
                             "is": [int((H.eb < b0).sum()), round(float(H.usd[H.eb < b0].sum() / float(d["multiplier"])), 4), st["is"]["num_trades"], st["is"]["total_pnl"]],
                             "wf": [int((H.eb >= b0).sum()), round(float(H.usd[H.eb >= b0].sum() / float(d["multiplier"])), 4), st["wf"]["num_trades"], st["wf"]["total_pnl"]]}
print(json.dumps(out, indent=1))
