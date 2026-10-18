"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_GAPFILL_NQ (20261017-1126-own) PRE-WF Stage A.
Built from C:/EdgeLog/qwen_lab/ideas/20261017-1126-own/QL_GAPFILL_NQ_2026-10-17.md and plugin_v1.py.txt only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / idea.json / tools/qwen_lab.py
are NOT read until this output's sha256 is posted.
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 8b1ea950f9df... = the prereg's hash) through the engine on the pinned master;
(B) TTM's OWN implementation of the prereg's Mechanism text (ttm_armb_own_rule.py, written and hashed before the plugin code was
    read; only the three DEFAULT_PARAMS values were taken from the plugin, AST-extracted); trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session (ET), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1126-own/."""
import ast
import hashlib
import importlib.util
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1126-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

IDEA, FOLDER = "QL_GAPFILL_NQ", "20261017-1126-own"
PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261017-1126-own/plugin_v1.py.txt"
PIN_PREFIX = "8b1ea950f9df"
PIN_PREREG_FULL = "8b1ea950f9df6f38e6af740986294b82efa74e9a4f202ec2e32e29ba9b3969c4"
ARMB = os.path.join(OUT, "ttm_armb_own_rule.py")
ARMB_SHA_AT_BUILD = "a01cf8ac80875c37bd9bb4376a6ac401773446f22fce0b39da681e0448217f7c"   # recorded before the plugin code was read
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
PREREG_FINGERPRINT, PREREG_BARS = "66f906272ba2dba5645708c9956ecf2360515b64", 119248
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side on top of house cost


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def plugin_defaults(path):
    """Only the DEFAULT_PARAMS literal of the plugin (AST), nothing else."""
    for n in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "DEFAULT_PARAMS" for t in n.targets):
            d = ast.literal_eval(n.value)
            return {k: (v["default"] if isinstance(v, dict) else v) for k, v in d.items()}
    raise RuntimeError("no DEFAULT_PARAMS")


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
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts = np.asarray(pts_gross, float)
    usd = (pts - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    f.update({"trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"], "win_rate": float((usd > 0).mean()),
              "gross_per_trade_pts": float(pts.mean()), "gross_over_cost": float(pts.mean() / cost),
              "net_per_trade_pts": float(pts.mean() - cost), "net_per_trade_usd": float(usd.mean()),
              "avg_win_loss_usd": [float(usd[usd > 0].mean()), float(-usd[usd <= 0].mean())]})
    return f


def three(exit_bars, pts, idxn, days):
    return {"house_cost": score(exit_bars, pts, idxn, days, COST), "real_cost": score(exit_bars, pts, idxn, days, REAL_COST),
            "stress_cost": score(exit_bars, pts, idxn, days, STRESS_COST)}


def diff(Ta, B, idxn):
    """Ta rows (entry, exit, side, entry_px, pts); B rows (entry, exit, side, entry_px, exit_px, pts)."""
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = sorted(set(ka) & set(kb))
    same_exit = sum(1 for k in both if ka[k][1] == kb[k][1])
    same_pts = sum(1 for k in both if abs(ka[k][4] - kb[k][5]) < 1e-6)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][4] - kb[k][5]) < 1e-6)
    return {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both), "only_A": len(set(ka) - set(kb)),
            "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
            "same_entry_px": sum(1 for k in both if abs(ka[k][3] - kb[k][3]) < 1e-9),
            "first_only_A": [[str(idxn[k[0]]), k[1], round(ka[k][4], 4)] for k in sorted(set(ka) - set(kb))[:5]],
            "first_only_B": [[str(idxn[k[0]]), k[1], round(kb[k][5], 4)] for k in sorted(set(kb) - set(ka))[:5]],
            "first_exit_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                 for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5]}


def main():
    pin = lf_sha(PLUGIN)
    plugin_pin_ok = pin.startswith(PIN_PREFIX) and pin == PIN_PREREG_FULL
    assert plugin_pin_ok, "plugin pin"
    armb_sha = lf_sha(ARMB)
    assert armb_sha == ARMB_SHA_AT_BUILD, "arm B file changed after it was built"
    spec = importlib.util.spec_from_file_location("ttm_armb_own_rule", ARMB)
    armb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(armb)
    params_b = plugin_defaults(PLUGIN)

    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    assert idxn[-1] < pd.Timestamp("2016-07-01"), "window end must be before the WF start"
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    first_not_0930 = int(sum(1 for s in starts if idxn[s].strftime("%H:%M") != "09:30"))
    res = {"idea": IDEA, "folder": FOLDER, "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": A.get("fingerprint"), "fingerprint_matches_prereg": A.get("fingerprint") == PREREG_FINGERPRINT,
           "bars": len(c), "bars_match_prereg": len(c) == PREREG_BARS,
           "window": [str(days[0].date()), str(days[-1].date())], "sessions": len(days),
           "sessions_first_bar_not_0930": first_not_0930,
           "plugin": PLUGIN, "plugin_lf_sha256": pin, "plugin_pin_ok": plugin_pin_ok,
           "armb_file": ARMB, "armb_lf_sha256": armb_sha, "armb_reading": armb.READING, "params_used": params_b,
           "costs_pts_rt": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT}

    # ARM A: plugin as run, through the engine, file defaults
    m = types.ModuleType("ttm_ql_gapfill_nq")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]
    res["A_plugin"] = three([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["gross_pts_sum"] = float(sum(t[4] for t in Ta))
    res["A_plugin"]["entries_not_at_session_bar0"] = int(sum(1 for t in Ta if t[0] not in set(starts.tolist())))
    res["A_plugin"]["entry_px_not_bar0_open"] = int(sum(1 for t in Ta if abs(o[t[0]] - t[3]) > 1e-9))
    res["A_plugin"]["longs_shorts"] = [int(sum(1 for t in Ta if t[2] > 0)), int(sum(1 for t in Ta if t[2] < 0))]

    # ARM B: own rule from the prereg text
    B = armb.own_rule(o, h, l, c, day_id, **params_b)
    res["B_own_rule"] = three([t[1] for t in B], [t[5] for t in B], idxn, days)
    res["B_own_rule"]["gross_pts_sum"] = float(sum(t[5] for t in B))
    res["B_own_rule"]["longs_shorts"] = [int(sum(1 for t in B if t[2] > 0)), int(sum(1 for t in B if t[2] < 0))]
    res["B_own_rule"]["stopped_out"] = int(sum(1 for t in B if t[1] != np.flatnonzero(day_id == day_id[t[0]])[-1]))
    res["A_vs_B"] = diff(Ta, B, idxn)

    # diagnostics only (NOT arm B): ATR read as mean(high - low) instead of true range
    diag = {}
    for name, kw in (("atr_high_low", {"atr_mode": "hl"}),):
        Bv = armb.own_rule(o, h, l, c, day_id, **params_b, **kw)
        d = diff(Ta, Bv, idxn)
        sc = score([t[1] for t in Bv], [t[5] for t in Bv], idxn, days, COST)
        diag[name] = {"trades": len(Bv), "same_entry_and_side_vs_A": d["same_entry_and_side"], "exact_vs_A": d["exact"],
                      "only_A": d["only_A"], "only_B": d["only_B"], "house_roc30": sc["roc30"], "house_net_usd": sc["net_usd"]}
    # diagnostic (NOT arm B; added AFTER the plugin and the engine's roll notes were read): the plugin declares
    # ROLL_SIGNAL = "difference", so the engine feeds it Panama back-adjusted signals (fills re-priced to raw). Arm B on the
    # same back-adjusted arrays, and whether arm B's only-B entries are the first session after a contract switch.
    from augur_engine import rolls
    oa, ha, la, ca, info = rolls.back_adjust(rolls.epoch_seconds(idx), o, h, l, c, "NQ", 300)
    Bd = armb.own_rule(oa, ha, la, ca, day_id, **params_b)
    d = diff(Ta, Bd, idxn)
    sb = np.asarray(info["switch_bars"])[np.asarray(info["in_series"], bool)]
    switch_sessions = sorted({int(day_id[min(int(x) + 1, len(c) - 1)]) for x in sb if 0 <= int(x) < len(c)})
    only_b = sorted(set((t[0], t[2]) for t in B) - set((t[0], t[2]) for t in Ta))
    diag["armB_on_difference_adjusted_signals"] = {
        "trades": len(Bd), "same_entry_and_side_vs_A": d["same_entry_and_side"], "exact_vs_A": d["exact"],
        "only_A": d["only_A"], "only_B": d["only_B"], "mixed_bars_in_window": int(np.asarray(info["synthetic"]).sum()),
        "switches_in_window": int(len(sb)),
        "armB_only_B_entries_on_first_session_after_switch": int(sum(1 for k in only_b if int(day_id[k[0]]) in switch_sessions)),
        "switch_sessions_first_day": [str(idxn[np.flatnonzero(day_id == s)[0]].date()) for s in switch_sessions][:40],
        "armB_only_B_entry_sessions": [str(idxn[k[0]].date()) for k in only_b]}
    res["diag_variants_not_armB"] = diag

    ah, bh = res["A_plugin"]["house_cost"], res["B_own_rule"]["house_cost"]
    res["checks"] = {
        "promotion_rule_A (gross/trade >= 0.533 and roc30 > 0 and one_episode False)":
            bool(ah["gross_per_trade_pts"] >= COST and ah["roc30"] > 0 and not ah["one_episode"]),
        "promotion_rule_B (gross/trade >= 0.533 and roc30 > 0 and one_episode False)":
            bool(bh["gross_per_trade_pts"] >= COST and bh["roc30"] > 0 and not bh["one_episode"]),
        "broken_plugin_check_A_ok (>= 120/3 and >= 20 per yr)": bool(ah["trades_per_yr"] >= 40.0 and ah["trades_per_yr"] >= 20.0),
    }

    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    b = (s + "\n").encode("utf-8")
    open(os.path.join(OUT, "ttm_verify.json"), "wb").write(b)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
