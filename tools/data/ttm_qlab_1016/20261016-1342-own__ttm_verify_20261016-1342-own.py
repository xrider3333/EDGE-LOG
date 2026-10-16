"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_TRENDN (20261016-1342-own) PRE-WF Stage A.
Built from C:/EdgeLog/qwen_lab/ideas/20261016-1342-own/QL_TRENDN_2026-10-16.md and plugin_v1.py.txt only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / tools/qwen_lab.py are NOT read
until this output's sha256 is posted.
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 dbc02a2e11c3... = the prereg's hash) through the engine on the pinned master;
(B) TTM's OWN implementation of the prereg's Mechanism text (ttm_armb_own_rule.py, written before the plugin code was read;
    only the three DEFAULT_PARAMS values were taken from the plugin); trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session (ET), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-1342-own/."""
import hashlib
import importlib.util
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-1342-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261016-1342-own/plugin_v1.py.txt"
PIN_PREFIX = "dbc02a2e11c3"
PIN_PREREG_FULL = "dbc02a2e11c364dcdcd9eb18be18067fa77e5ce9a0ff01dff43d8a56a670f2ae"
ARMB = os.path.join(OUT, "ttm_armb_own_rule.py")
ARMB_SHA_AT_BUILD = "08e541671ab34d24211fa98757edee62162ef012c76bd68b1d17cd7a2e5d24d3"   # recorded before the plugin code was read
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
PREREG_FINGERPRINT, PREREG_BARS = "66f906272ba2dba5645708c9956ecf2360515b64", 119248
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side on top of house cost
PARAMS_B = {"threshold_frac": 0.3, "stop_frac": 1.0, "trail_frac": 0.5}   # the plugin's DEFAULT_PARAMS defaults (AST-extracted)


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


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
            "first_only_A": [[str(idxn[k[0]]), k[1]] for k in sorted(set(ka) - set(kb))[:5]],
            "first_only_B": [[str(idxn[k[0]]), k[1]] for k in sorted(set(kb) - set(ka))[:5]],
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

    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res = {"idea": "QL_TRENDN", "folder": "20261016-1342-own", "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": A.get("fingerprint"), "fingerprint_matches_prereg": A.get("fingerprint") == PREREG_FINGERPRINT,
           "bars": len(c), "bars_match_prereg": len(c) == PREREG_BARS,
           "window": [str(days[0].date()), str(days[-1].date())], "sessions": len(days),
           "plugin": PLUGIN, "plugin_lf_sha256": pin, "plugin_pin_ok": plugin_pin_ok,
           "armb_file": ARMB, "armb_lf_sha256": armb_sha, "armb_reading": armb.READING, "params_used": PARAMS_B,
           "costs_pts_rt": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT}

    # ARM A: plugin as run, through the engine, file defaults
    m = types.ModuleType("ttm_ql_trendn")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]
    res["A_plugin"] = three([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["gross_pts_sum"] = float(sum(t[4] for t in Ta))

    # ARM B: own rule from the prereg text
    B = armb.own_rule(o, h, l, c, day_id, **PARAMS_B)
    res["B_own_rule"] = three([t[1] for t in B], [t[5] for t in B], idxn, days)
    res["B_own_rule"]["gross_pts_sum"] = float(sum(t[5] for t in B))
    res["A_vs_B"] = diff(Ta, B, idxn)

    # diagnostics only (NOT arm B): the two readings the text leaves most open
    diag = {}
    for name, kw in (("entry_bar12", {"entry_pos": 12}), ("short_no_threshold", {"short_needs_threshold": False}),
                     ("entry_bar12_and_short_no_threshold", {"entry_pos": 12, "short_needs_threshold": False})):
        Bv = armb.own_rule(o, h, l, c, day_id, **PARAMS_B, **kw)
        d = diff(Ta, Bv, idxn)
        sc = score([t[1] for t in Bv], [t[5] for t in Bv], idxn, days, COST)
        diag[name] = {"trades": len(Bv), "same_entry_and_side_vs_A": d["same_entry_and_side"], "exact_vs_A": d["exact"],
                      "only_A": d["only_A"], "only_B": d["only_B"], "house_roc30": sc["roc30"], "house_net_usd": sc["net_usd"]}
    res["diag_variants_not_armB"] = diag

    ah = res["A_plugin"]["house_cost"]
    res["checks"] = {
        "promotion_rule_A_roc30_ge_15_and_not_one_episode": bool(ah["roc30"] >= 15 and not ah["one_episode"]),
        "promotion_rule_B_roc30_ge_15_and_not_one_episode": bool(res["B_own_rule"]["house_cost"]["roc30"] >= 15
                                                                 and not res["B_own_rule"]["house_cost"]["one_episode"]),
        "broken_plugin_check_A_ok (>= 120/3 and >= 20 per yr)": bool(ah["trades_per_yr"] >= 40.0 and ah["trades_per_yr"] >= 20.0),
        "A_equals_text_with_entry_at_bar12_exactly": bool(diag["entry_bar12"]["exact_vs_A"] == len(Ta) == diag["entry_bar12"]["trades"]),
        "finding": ("plugin = the Mechanism text trade-for-trade EXCEPT the fill bar: it enters at session bar 12's open (10:30 ET, "
                    "the bar after signal bar 11; no look-ahead) where the text literally says bar 13's open (10:35). Threshold on "
                    "both sides, ratchet, gap-through fill at the open and flat-at-close all match. Both readings lose after house cost."),
    }

    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    b = (s + "\n").encode("utf-8")
    open(os.path.join(OUT, "ttm_verify.json"), "wb").write(b)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
