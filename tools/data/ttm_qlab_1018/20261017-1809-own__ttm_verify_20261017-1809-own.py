"""TTM (house verifier): BLIND stage-1 re-check of the Qwen Lab's QL_REVERSAL_NQ (20261017-1809-own) PRE-WF Stage A.
Built from C:/EdgeLog/qwen_lab/ideas/20261017-1809-own/QL_REVERSAL_NQ_2026-10-17.md and plugin_v2.py.txt only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read
until this output's sha256 is posted to MANAGER.
(A) the plugin AS RUN (plugin_v2.py.txt, LF sha256 e6f1ce54841b... = the prereg's hash) through the engine on the registry master;
(B) TTM's OWN implementation of the prereg's Mechanism text (ttm_armb_20261017-1809-own.py, frozen before the plugin was read);
trade-for-trade diff A vs B. Both scored by TTM's own booking: $ on the exit session, zero days kept; ROC@30k, DD5, DD% from
peak, Sortino; house cost 0.533 pt, real cost 0.7825 pt, stress = house + 0.5 pt.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1809-own/."""
import hashlib
import json
import math
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1809-own"
sys.path.insert(0, REPO)
sys.path.insert(0, OUT)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
import importlib.util                                             # noqa: E402

PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261017-1809-own/plugin_v2.py.txt"
PIN_PREFIX = "e6f1ce54841b"
PIN_PREREG = "e6f1ce54841bbf114455fa1e85f600a8d6031a5576fb9e3865645ef232858cd2"
ARMB = os.path.join(OUT, "ttm_armb_20261017-1809-own.py")
ARMB_FROZEN = "cd271a43eb0dec1887a0edebe4d0e84f3363fbafa2a820fee845bf597298eb5b"
FP_PREREG = "66f906272ba2dba5645708c9956ecf2360515b64"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side on the house cost
STRETCH_K = 1.5                        # the ONE number taken from the file (DEFAULT_PARAMS['stretch_k']['default']); text silent


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def clean(x):
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net_usd": float(x.sum()), "per_yr_usd": float(x.sum()) / yrs, "years": yrs, "max_dd": mdd,
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"), "dd5": float(r["dd5_usd"]),
            "one_episode": r["one_episode"] if isinstance(r["one_episode"], str) else bool(r["one_episode"]),
            "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts_gross = np.asarray(pts_gross, float)
    usd = (pts_gross - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    assert abs(s.sum() - usd.sum()) < 1e-6, "a trade booked off the calendar"
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "gross_pts_per_trade": float(pts_gross.mean()), "net_pts_per_trade": float(pts_gross.mean() - cost),
              "gross_over_cost": float(pts_gross.mean() / cost), "cost_pts": cost,
              "avg_win_loss_usd": [float(usd[usd > 0].mean()), float(-usd[usd <= 0].mean())]})
    return f


def three(exit_bars, pts, idxn, days):
    return {"house_cost": score(exit_bars, pts, idxn, days, COST), "real_cost": score(exit_bars, pts, idxn, days, REAL_COST),
            "stress_cost": score(exit_bars, pts, idxn, days, STRESS_COST)}


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_PREREG
    assert plugin_pin_ok, "plugin pin"
    assert lf_sha(ARMB) == ARMB_FROZEN, "arm B changed after freeze"
    spec = importlib.util.spec_from_file_location("ttm_armb", ARMB)
    armb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(armb)

    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    assert days[-1] < pd.Timestamp("2016-07-01")
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    sess_start = np.repeat(starts, np.diff(np.r_[starts, len(c)]))
    in_sess = np.arange(len(c)) - sess_start
    res = {"idea": "QL_REVERSAL_NQ", "folder": "20261017-1809-own", "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": str(A.get("fingerprint")), "fingerprint_matches_prereg": str(A.get("fingerprint")) == FP_PREREG,
           "bars": len(c), "window": [str(days[0].date()), str(days[-1].date())], "sessions": len(days),
           "plugin_lf_sha256": pin, "plugin_pin_ok": plugin_pin_ok, "armb_lf_sha256": ARMB_FROZEN,
           "costs_pts": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT,
           "stretch_k_used_in_B": STRETCH_K}

    # ARM B (own rule from the prereg text)
    B = armb.own_rule(o, h, l, c, day_id, stretch_k=STRETCH_K)
    Bt = armb.own_rule(o, h, l, c, day_id, stretch_k=STRETCH_K, need_trail=True)
    res["B_own_rule"] = three([t[1] for t in B], [t[5] for t in B], idxn, days)
    res["B_own_rule"]["min_entry_in_session_bar"] = int(min(in_sess[t[0]] for t in B))
    res["B_own_rule"]["stopped"] = int(sum(1 for t in B if t[1] != (np.flatnonzero(day_id == day_id[t[0]])[-1]) or t[4] != c[t[1]]))
    res["B_variant_need_trail20"] = {"trades": len(Bt), "house_cost": score([t[1] for t in Bt], [t[5] for t in Bt], idxn, days, COST)}

    # ARM A (the plugin through the engine, file defaults, cost 0 in the engine)
    m = types.ModuleType("ttm_ql_reversal_nq")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]
    res["A_plugin"] = three([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["sum_gross_pts"] = float(sum(t[4] for t in Ta))
    res["A_plugin"]["min_entry_in_session_bar"] = int(min(in_sess[t[0]] for t in Ta)) if Ta else None
    res["A_plugin"]["trade_tuple_len"] = len(T[0]) if T else None
    res["A_plugin"]["max_trades_one_session"] = int(pd.Series([day_id[t[0]] for t in Ta]).value_counts().max()) if Ta else 0

    # A vs B
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    sa = {day_id[k[0]] for k in ka}
    sb = {day_id[k[0]] for k in kb}
    res["A_vs_B"] = {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both), "only_A": len(set(ka) - set(kb)),
                     "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
                     "sessions_traded_A": len(sa), "sessions_traded_B": len(sb), "sessions_both": len(sa & sb),
                     "first_only_A": [[str(idxn[k[0]]), k[1], ka[k][4]] for k in sorted(set(ka) - set(kb))[:8]],
                     "first_only_B": [[str(idxn[k[0]]), k[1], kb[k][5]] for k in sorted(set(kb) - set(ka))[:8]],
                     "first_exit_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                          for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:8],
                     "sum_abs_pts_diff_matched": float(sum(abs(ka[k][4] - kb[k][5]) for k in both))}
    s = json.dumps(clean(res), indent=1, sort_keys=True, allow_nan=False) + "\n"
    print(s)
    p = os.path.join(OUT, "ttm_verify.json")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print("output sha256", hashlib.sha256(open(p, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
