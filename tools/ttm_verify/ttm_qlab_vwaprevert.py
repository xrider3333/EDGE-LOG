"""TTM (house verifier, MANAGER 10-15): BLIND re-check of the Qwen Lab's QL_VWAPREVERT_NQ PRE-WF Stage A.
Built from C:/EdgeLog/qwen_lab/preregs/QL_VWAPREVERT_NQ_2026-10-15.md and the plugin file only; the lab's numbers_pre_wf.json /
pre_wf_trades.csv / tools/qwen_lab.py are NOT read until this output's sha256 is posted.
(A) the plugin AS RUN (plugin_v2.py.txt, LF sha256 bb98812d... = the prereg's hash) through the engine on the pinned master;
(B) TTM's OWN implementation of the prereg's rule text, independent of the plugin; trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session, zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261015-1232-own/plugin_v2.py.txt"
PIN_PLUGIN = "bb98812d6ff49b1bbdf38b43a7344552544d141b03751a8b6fe57ba6663af5bd"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def own_rule(o, h, l, c, day_id):
    """The prereg's mechanism, written from its text: session VWAP proxy = mean close from the session's first bar to k; ATR20 =
    mean(high - low) over bars k-19..k (global bars); k >= 25 (global); close > VWAP + 2.5 ATR -> short at k+1's open, < VWAP - 2.5
    ATR -> long; stop 1.0 ATR, target 1.5 ATR (ATR of bar k), intrabar from the entry bar on, a gap through books the open, stop
    checked before target in one bar; flat at the session's last bar close; one trade per session (first signal); the entry bar
    k+1 must be in the same session. Returns (entry_bar, exit_bar, side, entry_px, exit_px, pts gross)."""
    n = len(c)
    rng = h - l
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        cs = np.cumsum(c[s:e])
        k = max(s, 25)
        while k < e - 1:
            if k < 19:
                k += 1
                continue
            vw = cs[k - s] / (k - s + 1)
            atr = rng[k - 19:k + 1].mean()
            side = -1 if c[k] > vw + 2.5 * atr else (1 if c[k] < vw - 2.5 * atr else 0)
            if side == 0:
                k += 1
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * 1.0 * atr
            tgt = ep + side * 1.5 * atr
            xb, xp = e - 1, c[e - 1]
            for j in range(ent, e):
                if j > ent:                       # a later bar opening beyond a level fills at its open
                    if side * (o[j] - stop) <= 0:
                        xb, xp = j, o[j]
                        break
                    if side * (o[j] - tgt) >= 0:
                        xb, xp = j, o[j]
                        break
                lo_hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
                hi_hit = (h[j] >= tgt) if side > 0 else (l[j] <= tgt)
                if lo_hit:
                    xb, xp = j, stop
                    break
                if hi_hit:
                    xb, xp = j, tgt
                    break
            out.append((ent, xb, side, float(ep), float(xp), float(side * (xp - ep))))
            break                                 # one trade per session
    return out


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net": float(x.sum()), "per_yr": float(x.sum()) / yrs, "years": yrs, "max_dd": mdd,
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"), "dd5": float(r["dd5_usd"]),
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(entry_bars, exit_bars, pts_gross, idxn, days, cost):
    usd = (np.asarray(pts_gross, float) - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "avg_win_loss": [float(usd[usd > 0].mean()), float(-usd[usd <= 0].mean())]})
    return f


def main():
    assert lf_sha(PLUGIN) == PIN_PLUGIN, "plugin pin"
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    res = {"master": MASTER, "registry_id": row[0].get("id"), "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "bars": len(c), "window": [str(days[0].date()), str(days[-1].date())], "sessions": len(days)}
    m = types.ModuleType("ttm_ql_vwaprevert")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]
    B = own_rule(o, h, l, c, np.asarray(A["day_id"]))
    res["A_plugin"] = {"house_cost": score([t[0] for t in Ta], [t[1] for t in Ta], [t[4] for t in Ta], idxn, days, COST),
                       "real_cost": score([t[0] for t in Ta], [t[1] for t in Ta], [t[4] for t in Ta], idxn, days, REAL_COST),
                       "engine_total_pnl_pts": float(r.get("total_pnl", float("nan")))}
    res["B_own_rule"] = {"house_cost": score([t[0] for t in B], [t[1] for t in B], [t[5] for t in B], idxn, days, COST),
                         "real_cost": score([t[0] for t in B], [t[1] for t in B], [t[5] for t in B], idxn, days, REAL_COST)}
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both), "only_A": len(set(ka) - set(kb)),
                     "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit, "same_gross_pts": same_pts,
                     "first_only_A": [str(idxn[k[0]]) for k in sorted(set(ka) - set(kb))[:5]],
                     "first_only_B": [str(idxn[k[0]]) for k in sorted(set(kb) - set(ka))[:5]],
                     "first_exit_diffs": [[str(idxn[k[0]]), str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5]}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    open(os.path.join(OUT, "ttm_qlab_vwaprevert.json"), "w", encoding="utf-8", newline="\n").write(s + "\n")
    print("output sha256", hashlib.sha256((s + "\n").encode()).hexdigest())


if __name__ == "__main__":
    main()
