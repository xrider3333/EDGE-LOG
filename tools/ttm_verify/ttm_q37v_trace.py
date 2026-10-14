"""TTM verify Q37 - TRACE of the two DIFFERENCES (written AFTER opening q37_dip_qqq.json, disclosed):
(1) trade selection: Q37 keeps trades by ENTRY <= 2025-08-24 (1,782 QQQ) - mine by EXIT (1,777 + 5 exiting after);
(2) NQ calendar: my NQ arm reindexed onto QQQ's sessions, DROPPING the P&L of 42 NQ exit days QQQ has no session for (my bug).
Re-reads both arms with entry-selection and each arm's calendar = its window sessions UNION its own exit days."""
import importlib.util
import json
import os

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("v", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ttm_q37v.py"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
import types                                                      # noqa: E402
import os                                                         # noqa: E402

row = [x for x in list_masters() if x.get("filename") == V.MASTER][0]
A = load_master_arrays(row)
idx = pd.DatetimeIndex(A["index"])
sessions = pd.DatetimeIndex(sorted(set(idx.tz_localize(None).normalize())))
fp = os.path.join(V.REPO, "augur_strategies", "NQDIP_1_1.py")
m = types.ModuleType("ttm_q37v_dip2"); m.__file__ = fp
exec(compile(open(fp, encoding="utf-8").read(), fp, "exec"), m.__dict__)
P = dict(V.CS.DIP_424_PARAMS); P["asset"] = "ETF"
T = run_backtest(m, instrument="QQQ", arrays=A, params=P, cost_pts=0.0, return_trades=True)["trades"]
ent = idx[[t[0] for t in T]].tz_localize(None).normalize(); ext = idx[[t[1] for t in T]].tz_localize(None).normalize()
pnl = np.array([t[2] for t in T], float); epx = np.array([t[4] for t in T], float)
first = ent.min()
out = {}
k = np.asarray(ent <= V.END)
xd = ext[k]
days = sessions[(sessions >= first) & (sessions <= xd.max())]
real = pnl + P["notional"] * P["cost_bps"] / 1e4 - V.REAL_PER_SHARE_RT * P["notional"] / epx
out["qqq_n_by_entry"] = int(k.sum()); out["qqq_days"] = len(days)
for nm, v, sz in (("QQQ RAW house", pnl, 1.0), ("QQQ F house", pnl, V.F_SIZE), ("QQQ RAW real", real, 1.0), ("QQQ F real", real, V.F_SIZE)):
    out[nm] = V.stats(V.daily(xd, v[k] * sz, days), days)
N = pd.read_csv(V.PURE, parse_dates=["entry", "exit"])
nk = (N.entry.dt.normalize() >= first) & (N.entry.dt.normalize() <= V.END)
nd = N.exit.dt.normalize()[nk]
ndays = days.union(pd.DatetimeIndex(nd.unique()))
ndays = ndays[(ndays >= first) & (ndays <= max(nd.max(), days.max()))]
out["nq_n_by_entry"] = int(nk.sum()); out["nq_days"] = len(ndays)
out["NQ RAW"] = V.stats(V.daily(nd, N.pnl[nk], ndays), ndays)
out["QQQ $ / NQ $ a year"] = out["QQQ RAW house"]["per_yr"] / out["NQ RAW"]["per_yr"]
s = json.dumps(out, indent=1, sort_keys=True)
print(s)
open("C:/EdgeLog/_anatomy_cache/ttm_q37v/ttm_q37v_trace.json", "w", encoding="utf-8", newline="\n").write(s + "\n")
