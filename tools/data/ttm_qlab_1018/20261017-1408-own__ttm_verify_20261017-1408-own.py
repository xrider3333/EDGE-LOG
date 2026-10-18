"""TTM (house verifier): BLIND re-check of the Qwen Lab's QL_LATEMOM_NQ (20261017-1408-own) PRE-WF Stage A.
Built from C:/EdgeLog/qwen_lab/ideas/20261017-1408-own/QL_LATEMOM_NQ_2026-10-17.md and plugin_v1.py.txt only; the lab's
numbers_pre_wf.json / pre_wf_trades.csv / sandbox_*_out.json / gates_*.json / transcript.json / idea.json / tools/qwen_lab.py are
NOT read until this output's sha256 is posted.
(A) the plugin AS RUN (plugin_v1.py.txt, LF sha256 ee95b989089d... = the prereg's hash) through the engine on the pinned master;
(B) TTM's OWN implementation of the prereg's Mechanism text (ttm_armb_own_rule.py, written and hashed before the plugin code was
    read; only the DEFAULT_PARAMS values trend_k / counter_k were taken from the plugin, by AST); trade-for-trade diff A vs B.
Both scored by TTM's own booking: $ on the exit session (ET), zero days kept; ROC@30k, DD5, DD% from peak, Sortino.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1408-own/."""
import hashlib
import importlib.util
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1408-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402

PLUGIN = "C:/EdgeLog/qwen_lab/ideas/20261017-1408-own/plugin_v1.py.txt"
PIN_PREFIX = "ee95b989089d"
PIN_PREREG_FULL = "ee95b989089db7b6ba57b68c6c12c77da8eac46d8ea7b465b5232cbc9cab2efc"
ARMB = os.path.join(OUT, "ttm_armb_own_rule.py")
ARMB_SHA_AT_BUILD = "9b228fc83afbb484308c7d01565b4805cb17481d26caf2ed82f4cca926477b6c"   # recorded before the plugin code was read
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
PREREG_FINGERPRINT, PREREG_BARS = "66f906272ba2dba5645708c9956ecf2360515b64", 119248
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # owner rule: $5.65 commission + 1 tick each side = 0.7825 pt
STRESS_COST = COST + 0.5               # +1 tick each side on top of house cost
PARAMS_B = {"trend_k": 0.5, "counter_k": 1.5, "lookback": 20}   # plugin DEFAULT_PARAMS defaults (AST); lookback 20 = the text


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
    ea = {t[0] for t in Ta}
    eb = {t[0] for t in B}
    return {"A_trades": len(Ta), "B_trades": len(B), "same_entry_and_side": len(both), "only_A": len(set(ka) - set(kb)),
            "only_B": len(set(kb) - set(ka)), "same_exit_bar": same_exit, "same_gross_pts": same_pts, "exact": exact,
            "same_entry_bar_opposite_side": len(ea & eb) - len(both),
            "same_entry_px": sum(1 for k in both if abs(ka[k][3] - kb[k][3]) < 1e-9),
            "first_only_A": [[str(idxn[k[0]]), k[1]] for k in sorted(set(ka) - set(kb))[:5]],
            "first_only_B": [[str(idxn[k[0]]), k[1]] for k in sorted(set(kb) - set(ka))[:5]],
            "first_exit_diffs": [[str(idxn[k[0]]), k[1], str(idxn[ka[k][1]]), str(idxn[kb[k][1]]), ka[k][4], kb[k][5]]
                                 for k in both if ka[k][1] != kb[k][1] or abs(ka[k][4] - kb[k][5]) > 1e-6][:5]}


def clocks(T, idxn, ei, xi):
    ent = pd.Series([idxn[t[ei]].strftime("%H:%M") for t in T]).value_counts().to_dict() if T else {}
    ext = pd.Series([idxn[t[xi]].strftime("%H:%M") for t in T]).value_counts().to_dict() if T else {}
    held = pd.Series([int(t[xi] - t[ei]) for t in T]).value_counts().to_dict() if T else {}
    return {"entry_clock": {str(k): int(v) for k, v in ent.items()}, "exit_bar_open_clock": {str(k): int(v) for k, v in ext.items()},
            "bars_held": {str(k): int(v) for k, v in held.items()}}


def posthoc(o, h, l, c, day_id, Ta, B, idxn, days, trend_k=0.5, counter_k=1.5, lb=20):
    """Per full session: TTM's trailing stats (last 20 FULL sessions) and the plugin-style ones (last 20 sessions by count, full
    ones only, >= 10 needed). Rebuild A from the text + the two departures and attribute every A/B difference."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    full = (ends - starts) >= 78
    mv = np.array([c[s + 65] - o[s + 54] if f else np.nan for s, f in zip(starts, ends - starts >= 78)])
    mr = np.array([np.max(h[s:s + 54]) - np.min(l[s:s + 54]) if f else np.nan for s, f in zip(starts, full)])
    rows = {}
    rebuilt = []
    for i, (s, e) in enumerate(zip(starts, ends)):
        if not full[i]:
            continue
        prior_full = [j for j in range(i) if full[j]][-lb:]
        mb_ttm = float(np.median(mv[prior_full])) if len(prior_full) == lb else None
        win = [j for j in range(max(0, i - lb), i) if full[j]] if i >= lb else []
        ok_p = i >= lb and len(win) >= lb // 2
        mb_p = float(np.median(mv[win])) if ok_p else None
        mm_p = float(np.median(mr[win])) if ok_p else None
        rows[s + 66] = {"mb_ttm": mb_ttm, "mb_plugin_style": mb_p}
        if ok_p and mb_p > 0 and mm_p > 0:
            room = mr[i] <= counter_k * mm_p
            side = 1 if (mv[i] >= trend_k * mb_p and room) else (-1 if (-mv[i] >= trend_k * mb_p and room) else 0)
            if side:
                rebuilt.append((int(s + 66), int(e - 1), side, float(o[s + 66]), float(c[e - 1]), float(side * (c[e - 1] - o[s + 66]))))
    d = diff(Ta, rebuilt, idxn)
    ka = {(t[0], t[2]) for t in Ta}
    kb = {(t[0], t[2]) for t in B}
    only_b = sorted(kb - ka)
    only_a = sorted(ka - kb)
    nb_neg = sum(1 for k in only_b if rows[k[0]]["mb_ttm"] is not None and rows[k[0]]["mb_ttm"] <= 0)
    nb_negp = sum(1 for k in only_b if rows[k[0]]["mb_plugin_style"] is not None and rows[k[0]]["mb_plugin_style"] <= 0)
    bmap = {(t[0], t[2]): t for t in B}
    neg_b = [bmap[k] for k in only_b if rows[k[0]]["mb_ttm"] is not None and rows[k[0]]["mb_ttm"] <= 0]
    sess_neg = sum(1 for v in rows.values() if v["mb_ttm"] is not None and v["mb_ttm"] <= 0)
    return {"rebuilt_text_plus_d1_d2_vs_A": {"trades": len(rebuilt), "exact_vs_A": d["exact"], "only_A": d["only_A"],
                                             "only_B": d["only_B"], "equals_A": bool(d["exact"] == len(Ta) == len(rebuilt))},
            "only_B_with_ttm_signed_median_le_0": nb_neg, "only_B_with_plugin_style_median_le_0": nb_negp,
            "only_B_total": len(only_b), "only_A_total": len(only_a),
            "full_sessions_with_ttm_signed_median_le_0": sess_neg,
            "only_A_entries": [[str(idxn[k[0]]), k[1], rows[k[0]]] for k in only_a],
            "B_trades_skipped_by_d1": {"trades": len(neg_b), "long": sum(1 for t in neg_b if t[2] > 0),
                                       "short": sum(1 for t in neg_b if t[2] < 0),
                                       "gross_pts_sum": float(sum(t[5] for t in neg_b)),
                                       "gross_per_trade_pts": float(np.mean([t[5] for t in neg_b])) if neg_b else float("nan")},
            "note": ("plugin departs from the Mechanism text in two ways: d1 'if med_block <= 0 or med_morn <= 0: continue' (not in the "
                     "text; with a signed median <= 0 the text's LONG test fires on flat/down blocks); d2 trailing = the last 20 "
                     "sessions BY COUNT with short sessions dropped (>= 10 full needed) vs TTM's last 20 FULL sessions. Both use bars "
                     "54-65 / 0-53 by index (the 14:00-15:00 block; the '14:30' clock label is wrong in both). No look-ahead: signal "
                     "uses bars <= 65, fill at bar 66's open, exit at bar 77's close.")}


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
    res = {"idea": "QL_LATEMOM_NQ", "folder": "20261017-1408-own", "master": MASTER, "registry_id": row[0].get("id"),
           "master_sha256": hashlib.sha256(open(os.path.join(REPO, "augur_uploads", MASTER), "rb").read()).hexdigest(),
           "fingerprint": A.get("fingerprint"), "fingerprint_matches_prereg": A.get("fingerprint") == PREREG_FINGERPRINT,
           "bars": len(c), "bars_match_prereg": len(c) == PREREG_BARS, "tz": str(idx.tz),
           "window": [str(days[0].date()), str(days[-1].date())], "sessions": len(days),
           "plugin": PLUGIN, "plugin_lf_sha256": pin, "plugin_pin_ok": plugin_pin_ok,
           "armb_file": ARMB, "armb_lf_sha256": armb_sha, "armb_reading": armb.READING, "params_used_B": PARAMS_B,
           "costs_pts_rt": {"house": COST, "real": REAL_COST, "stress": STRESS_COST}, "usd_per_pt": MULT}

    # ARM A: plugin as run, through the engine, file defaults
    m = types.ModuleType("ttm_ql_latemom")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in T]
    res["A_plugin"] = three([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    res["A_plugin"]["engine_total_pnl_pts"] = float(r.get("total_pnl", float("nan")))
    res["A_plugin"]["gross_pts_sum"] = float(sum(t[4] for t in Ta))
    res["A_plugin"]["timing"] = clocks(Ta, idxn, 0, 1)
    res["A_plugin"]["sides"] = {"long": sum(1 for t in Ta if t[2] > 0), "short": sum(1 for t in Ta if t[2] < 0)}
    res["A_plugin"]["entry_px_is_bar_open"] = sum(1 for t in Ta if abs(t[3] - o[t[0]]) < 1e-9)

    # ARM B: own rule from the prereg text
    B = armb.own_rule(o, h, l, c, day_id, **PARAMS_B)
    res["B_own_rule"] = three([t[1] for t in B], [t[5] for t in B], idxn, days)
    res["B_own_rule"]["gross_pts_sum"] = float(sum(t[5] for t in B))
    res["B_own_rule"]["timing"] = clocks(B, idxn, 0, 1)
    res["B_own_rule"]["sides"] = {"long": sum(1 for t in B if t[2] > 0), "short": sum(1 for t in B if t[2] < 0)}
    res["A_vs_B"] = diff(Ta, B, idxn)

    # diagnostics only (NOT arm B): the readings the text leaves most open
    diag = {}
    for name, kw in (("block_abs_median", {"block_stat": "abs"}), ("block_range_median", {"block_stat": "range"}),
                     ("trailing_any_20_sessions", {"skip_short_sessions": False}),
                     ("block_abs_and_trailing_any", {"block_stat": "abs", "skip_short_sessions": False})):
        Bv = armb.own_rule(o, h, l, c, day_id, **PARAMS_B, **kw)
        d = diff(Ta, Bv, idxn)
        sc = score([t[1] for t in Bv], [t[5] for t in Bv], idxn, days, COST)
        diag[name] = {"trades": len(Bv), "same_entry_and_side_vs_A": d["same_entry_and_side"], "exact_vs_A": d["exact"],
                      "only_A": d["only_A"], "only_B": d["only_B"], "house_roc30": sc["roc30"], "house_net_usd": sc["net_usd"],
                      "house_trades_per_yr": sc["trades_per_yr"], "house_one_episode": sc["one_episode"],
                      "gross_per_trade_pts": sc["gross_per_trade_pts"]}
    res["diag_variants_not_armB"] = diag

    # POST-HOC (written AFTER the plugin code was read, after ARM B was frozen; NOT arm B): the plugin's two departures from the
    # Mechanism text, added to TTM's own loop - (d1) skip the session when the trailing SIGNED median block move <= 0 (or the
    # median morning range <= 0); (d2) trailing set = the last 20 SESSIONS by count, short ones dropped, >= 10 full ones needed.
    res["posthoc_after_plugin_read"] = posthoc(o, h, l, c, day_id, Ta, B, idxn, days)

    ah = res["A_plugin"]["house_cost"]
    bh = res["B_own_rule"]["house_cost"]
    res["checks"] = {
        "promotion_rule_A (gross/trade >= 0.533 AND roc30 > 0 AND one_episode False)":
            bool(ah["gross_per_trade_pts"] >= COST and ah["roc30"] > 0 and not ah["one_episode"]),
        "promotion_rule_B (same)": bool(bh["gross_per_trade_pts"] >= COST and bh["roc30"] > 0 and not bh["one_episode"]),
        "broken_plugin_check_A_ok (>= 120/3 and >= 20 per yr)": bool(ah["trades_per_yr"] >= 40.0 and ah["trades_per_yr"] >= 20.0),
        "A_equals_B_exactly": bool(res["A_vs_B"]["exact"] == len(Ta) == len(B)),
        "A_equals_text_plus_d1_d2_exactly": res["posthoc_after_plugin_read"]["rebuilt_text_plus_d1_d2_vs_A"]["equals_A"],
        "finding": ("every A trade fills at 15:00 (bar 66 open) and exits at the 15:55 bar's close (11 bars held): timing contract "
                    "holds, no look-ahead. A (654) is NOT the literal Mechanism text (B, 1151): 649 trades identical, 502 only in B, "
                    "5 only in A. The gap is fully explained by two plugin choices not in the text - d1 skip when the trailing SIGNED "
                    "median block move <= 0, d2 trailing window = last 20 sessions by count with short sessions dropped; text + d1 + "
                    "d2 rebuilds A trade for trade. Both arms lose after house cost (gross/trade A 0.12, B 0.19 pt < 0.533): no "
                    "promotion under either reading."),
    }

    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    b = (s + "\n").encode("utf-8")
    open(os.path.join(OUT, "ttm_verify.json"), "wb").write(b)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
