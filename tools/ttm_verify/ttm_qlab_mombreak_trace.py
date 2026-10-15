"""TTM QL_ES_MOMBREAK re-check - TRACE (written AFTER output sha d96d720f was posted, disclosed). TTM's arm B entered at session
index 13 (10:35, reading 'bar 13' 0-indexed like 'bar 12 (10:30)' and close[11]); the plugin enters at index 12 (10:30, 'bar 13'
1-indexed) and takes ATR(14) over bars entry-13..entry, i.e. INCLUDING the entry bar (Custom ML's disclosed leak).
Re-run TTM's own rule with entry at index 12 and (L) the plugin's leaky ATR / (C) the causal ATR (14 bars before entry)."""
import importlib.util
import json
import types

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("v", __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "ttm_qlab_mombreak.py"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def rule(o, h, l, c, day_id, leak, thr=0.3, stop_frac=2.0):
    n = len(c)
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        if e - s < 15:
            continue
        rngm = h[s:s + 12].max() - l[s:s + 12].min()
        move = c[s + 11] - o[s]
        if rngm <= 0 or abs(move) < thr * rngm:
            continue
        side = 1 if move > 0 else -1
        ent = s + 12
        w = (h[ent - 13:ent + 1] - l[ent - 13:ent + 1]) if leak else (h[ent - 14:ent] - l[ent - 14:ent])
        atr = float(w.mean()) if ent >= 14 else 0.0
        if atr <= 0:
            atr = rngm / 14.0
        ep, ext = o[ent], o[ent]
        xb, xp = e - 1, c[e - 1]
        for j in range(ent, e):
            stop = ext - side * stop_frac * atr
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, ((o[j] if o[j] < stop else stop) if side > 0 else (o[j] if o[j] > stop else stop))
                break
            ext = max(ext, h[j]) if side > 0 else min(ext, l[j])
        out.append((ent, xb, side, float(ep), float(xp), float(side * (xp - ep))))
    return out


row = [x for x in V.list_masters() if x.get("filename") == V.MASTER][0]
A = V.load_master_arrays(row, date_from=V.D0, date_to=V.D1)
idxn = pd.DatetimeIndex(A["index"]).tz_localize(None)
days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
m = types.ModuleType("trace_mb"); m.__file__ = V.PLUGIN
exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
T = V.run_backtest(m, instrument="ES", arrays=A, params=None, cost_pts=0.0, return_trades=True)["trades"]
ka = {(int(t[0]), int(t[3])): (int(t[1]), float(t[2])) for t in T}
out = {}
for nm, leak in (("L_plugin_timing_leaky_atr", True), ("C_plugin_timing_causal_atr", False)):
    B = rule(o, h, l, c, np.asarray(A["day_id"]), leak)
    kb = {(t[0], t[2]): (t[1], t[5]) for t in B}
    both = set(ka) & set(kb)
    out[nm] = {"trades": len(B), "same_entry_side": len(both),
               "same_exit_and_pts": sum(1 for k in both if ka[k][0] == kb[k][0] and abs(ka[k][1] - kb[k][1]) < 1e-6),
               "house_cost": V.score([t[0] for t in B], [t[1] for t in B], [t[5] for t in B], idxn, days, V.COST),
               "real_cost": V.score([t[0] for t in B], [t[1] for t in B], [t[5] for t in B], idxn, days, V.REAL_COST)}
print(json.dumps(out, indent=1, default=float))
json.dump(out, open("C:/EdgeLog/_anatomy_cache/ttm_qlab/ttm_qlab_mombreak_trace.json", "w"), indent=1, default=float)
