"""TTM QL_VWAPREVERT_NQ re-check - TRACE (written AFTER output sha 2257f330 was posted, disclosed): TTM's arm B read the prereg's
'k >= 25' and 'ATR over bars k-19..k' on GLOBAL bars (ATR reaching into the prior session); the plugin counts k inside the session
from k = atr_window = 20 (ATR inside the session, last signal 3 bars before the close). Re-run TTM's own rule under
B1 = the prereg read session-relative (k >= 25 inside the session) and B2 = the plugin's reading (k from 20, k <= n_session - 3),
and diff each against the plugin trade for trade."""
import importlib.util
import json
import types

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("v", __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "ttm_qlab_vwaprevert.py"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def rule_rel(o, h, l, c, day_id, k0, last_off):
    n = len(c)
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        cs = np.cumsum(c[s:e])
        rg = h[s:e] - l[s:e]
        for kr in range(k0, (e - s) - last_off):
            k = s + kr
            vw = cs[kr] / (kr + 1)
            atr = rg[kr - 19:kr + 1].mean()
            side = -1 if c[k] > vw + 2.5 * atr else (1 if c[k] < vw - 2.5 * atr else 0)
            if side == 0:
                continue
            ent = k + 1
            ep = o[ent]
            stop, tgt = ep - side * atr, ep + side * 1.5 * atr
            xb, xp = e - 1, c[e - 1]
            for j in range(ent, e):
                if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                    xb, xp = j, (min(o[j], stop) if side > 0 else max(o[j], stop)) if j > ent else stop
                    break
                if (h[j] >= tgt) if side > 0 else (l[j] <= tgt):
                    xb, xp = j, (max(o[j], tgt) if side > 0 else min(o[j], tgt)) if j > ent else tgt
                    break
            out.append((ent, xb, side, float(ep), float(xp), float(side * (xp - ep))))
            break
    return out


row = [x for x in V.list_masters() if x.get("filename") == V.MASTER][0]
A = V.load_master_arrays(row, date_from=V.D0, date_to=V.D1)
idxn = pd.DatetimeIndex(A["index"]).tz_localize(None)
days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
m = types.ModuleType("trace_vw"); m.__file__ = V.PLUGIN
exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
T = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)["trades"]
ka = {(int(t[0]), int(t[3])): (int(t[1]), float(t[2])) for t in T}
out = {}
for nm, k0, off in (("B1_prereg_session_k25", 25, 2), ("B2_plugin_reading_k20", 20, 2)):
    B = rule_rel(o, h, l, c, np.asarray(A["day_id"]), k0, off)
    kb = {(t[0], t[2]): (t[1], t[5]) for t in B}
    both = set(ka) & set(kb)
    out[nm] = {"trades": len(B), "same_entry_side": len(both), "only_plugin": len(set(ka) - set(kb)), "only_own": len(set(kb) - set(ka)),
               "same_exit_and_pts": sum(1 for k in both if ka[k][0] == kb[k][0] and abs(ka[k][1] - kb[k][1]) < 1e-6),
               "house_cost": V.score([t[0] for t in B], [t[1] for t in B], [t[5] for t in B], idxn, days, V.COST),
               "real_cost": V.score([t[0] for t in B], [t[1] for t in B], [t[5] for t in B], idxn, days, V.REAL_COST)}
print(json.dumps(out, indent=1, default=float))
json.dump(out, open("C:/EdgeLog/_anatomy_cache/ttm_qlab/ttm_qlab_vwaprevert_trace.json", "w"), indent=1, default=float)
