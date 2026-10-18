"""TTM (house verifier) STAGE 2 - COMPARE + TRACE for Qwen Lab QL_TOMRUSH_NQ (idea folder 20261016-2218-shelf34).
Run after stage 1 (ttm_verify.json sha256 c168cf4d... posted to MANAGER). Opens the lab's numbers_pre_wf.json and
pre_wf_trades.csv only now.
  1. arm A (plugin_v2 through the engine) vs the lab's numbers file, field by field, and vs the lab's trade CSV trade by trade
  2. 'plugin way' = TTM's own rule re-written with every plugin detail (session < 2 bars skipped, ATR fallback when fewer
     than atr_bars prior bars, stop live on the entry bar, gap-through on o < stop) -> must match the plugin 100%
  3. literal-reading variants of the one ambiguous prereg word ('ATR'): house Wilder ATR (ml_gate._atr: EWM alpha 1/14 of
     TR) and plain high-low ATR; plus the no-stop reading for context -> four numbers each
  4. look-ahead: per trade, (a) truncate the arrays after the exit bar, (b) truncate after the entry bar with that bar's
     h/l/c set to its open, (c) truncate after the entry bar with its low pushed far down -> booked stop must equal the
     stop TTM computes from bars < entry only
Writes only C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-2218-shelf34/ttm_trace.json. Nothing in the EDGE-LOG repo."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-2218-shelf34"
sys.path.insert(0, REPO)
sys.path.insert(0, OUT)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
from augur_engine.session_calendar import is_last_n_sessions_of_month   # noqa: E402
import ttm_armb_own_rule                                          # noqa: E402

IDEA = "C:/EdgeLog/qwen_lab/ideas/20261016-2218-shelf34"
PLUGIN = IDEA + "/plugin_v2.py.txt"
PIN_PLUGIN = "b57fa81a4bdfe01cc29fcd6648d46f24cc701c69545a3e824b423a341139194f"
ARMB_SHA = "0fc651007b3a800994512dfffda89d886a58727b8ac76294aa24634b13349e3d"
STAGE1_SHA = "c168cf4db6c6734e06b2a07b7bb2d97b8549b000383de3d98d96b6a1fc0e91c4"
MASTER, D0, D1 = "NOADJ_NQ_5m_RTH.csv", "2010-06-07", "2016-06-30"
COST, MULT = 0.533, 20.0
REAL_COST = 0.25 * 2 + 5.65 / MULT     # 0.7825 pt RT
STRESS_COST = COST + 0.5               # 1.033 pt RT
TOL = {"trades": 0, "net_usd": 1.0, "roc_30k": 0.005, "dd5_usd": 1.0, "max_dd_usd": 1.0, "dd_pct_peak": 0.01,
       "sortino": 0.001, "win_rate": 0.05}


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
            "dd5_n": int(r["n"]), "new_high_ever": bool(np.max(eq) > 1e-9),
            "one_episode_reading": ("NOT TESTABLE" if (int(r["n"]) <= 1 or not np.max(eq) > 1e-9)
                                    else ("True" if r["one_episode"] else "False")),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def score(exit_bars, pts_gross, idxn, days, cost):
    pts = np.asarray(pts_gross, float)
    usd = (pts - cost) * MULT
    s = pd.Series(usd, index=idxn[np.asarray(exit_bars, int)].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    f = four(s.to_numpy(), days)
    w, lo = usd[usd > 0].sum(), -usd[usd < 0].sum()
    f.update({"cost_pts_rt": cost, "trades": int(len(usd)), "trades_per_yr": len(usd) / f["years"],
              "win_rate": float((usd > 0).mean()) if len(usd) else float("nan"),
              "gross_pts_per_trade": float(pts.mean()) if len(pts) else float("nan"),
              "net_pts_per_trade": float(pts.mean() - cost) if len(pts) else float("nan"),
              "net_usd_per_trade": float(usd.mean()) if len(usd) else float("nan"),
              "profit_factor_net": float(w / lo) if lo > 0 else float("inf"),
              "gross_cost_ratio": float(pts.mean() / cost)})
    return f


def line(f):
    return ("ROC@30k %.2f | DD5 $%s | DD%% from peak %.2f%% | Sortino %.2f | trades %d (%.1f/yr) | $/yr %s | "
            "gross %.4f pt/trade vs cost %.4f pt RT | one-episode %s"
            % (f["roc30"], format(round(f["dd5"]), ","), f["dd_pct_peak"], f["sortino"], f["trades"], f["trades_per_yr"],
               format(round(f["per_yr_usd"]), ","), f["gross_pts_per_trade"], f["cost_pts_rt"], f["one_episode_reading"]))


def load():
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1, "registry row"
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    return row[0], A, idx, idxn, days


def plugin_way(o, h, l, c, day_id, index, last_n=3, stop_frac=2.0, atr_bars=14, atr_kind="tr_mean"):
    """TTM's own rule written the plugin's way (every plugin detail mirrored; TTM's own code).
    atr_kind: 'tr_mean' (plugin / arm B), 'wilder' (house ml_gate._atr, EWM alpha 1/n of TR, value at bar s-1),
    'hl_mean' (mean of high-low over the n bars before bar 0), 'none' (no stop)."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    did = np.asarray(day_id)
    n = len(c)
    flag = np.asarray(is_last_n_sessions_of_month(index, int(last_n), did), bool)
    starts = np.r_[0, np.flatnonzero(did[1:] != did[:-1]) + 1]
    ends = np.r_[starts[1:], n]
    prev_c = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr0 = tr.copy()
    tr0[0] = h[0] - l[0]                                  # pandas max(axis=1) skips the NaN on bar 0
    wil = pd.Series(tr0).ewm(alpha=1.0 / max(1, atr_bars), adjust=False).mean().to_numpy()
    out = []
    for s, e in zip(starts, ends):
        if e - s < 2:                                     # plugin: a session of < 2 bars is skipped
            continue
        if not flag[s]:
            continue
        if atr_kind == "tr_mean":
            if s >= atr_bars:
                atr = float(tr[s - atr_bars:s].mean())
            else:                                         # plugin fallback (never fires in this window)
                atr = float((h[:s].max() - l[:s].min()) / max(s, 1))
        elif atr_kind == "wilder":
            atr = float(wil[s - 1])
        elif atr_kind == "hl_mean":
            atr = float((h[s - atr_bars:s] - l[s - atr_bars:s]).mean())
        else:
            atr = None
        if atr is not None and atr <= 0:
            continue
        ep = o[s]
        xb, xp = e - 1, c[e - 1]
        if atr is not None:
            stop = ep - float(stop_frac) * atr
            for j in range(s, e):                         # live from the entry bar, intrabar on the low
                if l[j] <= stop:
                    xb, xp = j, (o[j] if o[j] < stop else stop)
                    break
        out.append((int(s), int(xb), 1, float(ep), float(xp), float(xp - ep)))
    return out


def load_plugin():
    m = types.ModuleType("ttm_ql_tomrush_trace")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    return m


def cmp_num(lab, mine, tol):
    if isinstance(lab, str) or isinstance(mine, str):
        return str(lab) == str(mine)
    return abs(float(lab) - float(mine)) <= tol + 1e-12


def main():
    assert lf_sha(PLUGIN) == PIN_PLUGIN, "plugin pin"
    assert lf_sha(OUT + "/ttm_armb_own_rule.py") == ARMB_SHA, "arm B changed"
    assert hashlib.sha256(open(OUT + "/ttm_verify.json", "rb").read()).hexdigest() == STAGE1_SHA, "stage-1 output changed"
    row, A, idx, idxn, days = load()
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    did = np.asarray(A["day_id"])
    res = {"idea": "QL_TOMRUSH_NQ", "stage": "2 COMPARE + TRACE", "stage1_output_sha256": STAGE1_SHA,
           "plugin_lf_sha256": PIN_PLUGIN, "fingerprint": A.get("fingerprint"), "bars": int(len(idx)), "sessions": len(days),
           "window": [str(days[0].date()), str(days[-1].date())]}
    m = load_plugin()
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]   # entry, exit, side, px, gross
    xa, ga = [t[1] for t in Ta], [t[4] for t in Ta]
    house, real, stress = (score(xa, ga, idxn, days, k) for k in (COST, REAL_COST, STRESS_COST))
    res["arm_a"] = {"house": house, "real": real, "stress": stress,
                    "four_numbers": {"house": line(house), "real": line(real), "stress": line(stress)}}

    # ---- 1. lab numbers file, field by field
    labf = json.load(open(IDEA + "/numbers_pre_wf.json", encoding="utf-8"))
    L = labf["numbers"]
    rows = []

    def add(field, lab, mine, tol, numbers_file="numbers_pre_wf.json"):
        rows.append({"numbers_file": numbers_file, "field": field, "lab": lab, "mine": mine, "tol": tol,
                     "match": bool(cmp_num(lab, mine, tol))})
    add("trades", L["trades"], house["trades"], 0)
    add("net_usd", L["net_usd"], round(house["net_usd"], 4), 1.0)
    add("roc_30k", L["roc_30k"], round(house["roc30"], 6), 0.005)
    add("dd5_usd", L["dd5_usd"], house["dd5"], 1.0)
    add("max_dd_usd", L["max_dd_usd"], round(house["max_dd"], 4), 1.0)
    add("dd_pct_peak", L["dd_pct_peak"], house["dd_pct_peak"], 0.01)
    add("sortino", L["sortino"], round(house["sortino"], 6), 0.001)
    add("one_episode", L["one_episode"], house["one_episode_reading"], 0)
    add("win_rate (lab %, mine x100)", L["win_rate"], round(100 * house["win_rate"], 4), 0.05)
    add("dd5_n", L["dd5_n"], house["dd5_n"], 0)
    add("trades_per_year", L["trades_per_year"], round(house["trades_per_yr"], 4), 0.05)
    add("years", L["years"], round(house["years"], 4), 0.001)
    add("sessions", L["sessions"], len(days), 0)
    add("cost_pts", L["cost_pts"], COST, 1e-9)
    add("gross_pts_per_trade", L["gross_pts_per_trade"], round(house["gross_pts_per_trade"], 6), 0.0001)
    add("net_pts_per_trade", L["net_pts_per_trade"], round(house["net_pts_per_trade"], 6), 0.0001)
    add("net_usd_per_trade", L["net_usd_per_trade"], round(house["net_usd_per_trade"], 4), 0.01)
    add("gross_cost_ratio", L["gross_cost_ratio"], round(house["gross_cost_ratio"], 6), 0.001)
    add("profit_factor (net)", L["profit_factor"], round(house["profit_factor_net"], 6), 0.0001)
    add("mult", L["mult"], MULT, 0)
    add("fingerprint", labf["fingerprint"], A.get("fingerprint"), 0)
    add("bars", labf["bars"], int(len(idx)), 0)
    add("params", json.dumps(labf["params"], sort_keys=True), json.dumps({"atr_bars": 14, "last_n": 3, "stop_frac": 2.0},
                                                                         sort_keys=True), 0)
    add("promoted", labf["promoted"], False, 0)
    res["lab_vs_arm_a"] = rows
    res["lab_vs_arm_a_all_match"] = all(x["match"] for x in rows)
    res["lab_vs_arm_a_tolerance_fields_match"] = all(x["match"] for x in rows if x["field"].split(" ")[0] in
                                                     ("trades", "net_usd", "roc_30k", "dd5_usd", "max_dd_usd", "dd_pct_peak",
                                                      "sortino", "one_episode", "win_rate"))
    # exactness on the tolerance fields (the lab rounds; exact = equal after the lab's rounding)
    res["lab_vs_arm_a_max_abs_diff"] = {x["field"]: (abs(float(x["lab"]) - float(x["mine"]))
                                                     if not isinstance(x["lab"], str) and not isinstance(x["lab"], bool) else None)
                                        for x in rows}

    # ---- 1b. lab trade CSV, trade by trade
    t = pd.read_csv(IDEA + "/pre_wf_trades.csv")
    n_match = 0
    worst = 0.0
    bad = []
    for i, (a, rr) in enumerate(zip(Ta, t.itertuples(index=False))):
        ok = (a[0] == rr.entry_bar and a[1] == rr.exit_bar and a[2] == rr.side and abs(a[3] - rr.entry_price) < 1e-9
              and abs((a[4] - COST) - rr.pnl_points_net) < 1e-5
              and str(idxn[a[0]]) == str(pd.Timestamp(rr.entry_time).tz_localize(None))
              and str(idxn[a[1]]) == str(pd.Timestamp(rr.exit_time).tz_localize(None)))
        worst = max(worst, abs((a[4] - COST) - rr.pnl_points_net))
        n_match += ok
        if not ok and len(bad) < 5:
            bad.append([i, list(a), list(rr)])
    res["lab_csv_vs_arm_a"] = {"lab_rows": int(len(t)), "arm_a_trades": len(Ta), "exact_rows": int(n_match),
                               "max_abs_net_pts_diff": worst, "first_mismatches": bad,
                               "lab_csv_net_sum_usd": float(t.pnl_points_net.sum() * MULT),
                               "lab_csv_gross_pts_per_trade": float((t.pnl_points_net + COST).mean())}

    # ---- 2. plugin way vs the plugin, and vs the frozen arm B
    P = plugin_way(o, h, l, c, did, A["index"])
    B = ttm_armb_own_rule.own_rule(o, h, l, c, did, A["index"], stop_frac=2.0)
    kp, ka, kb = ({(x[0], x[2]): x for x in P}, {(x[0], x[2]): x for x in Ta}, {(x[0], x[2]): x for x in B})
    exact_pa = sum(1 for k in set(kp) & set(ka) if kp[k][1] == ka[k][1] and abs(kp[k][5] - ka[k][4]) < 1e-9
                   and abs(kp[k][3] - ka[k][3]) < 1e-12)
    exact_pb = sum(1 for k in set(kp) & set(kb) if kp[k][1] == kb[k][1] and abs(kp[k][5] - kb[k][5]) < 1e-9)
    direct = m.run_backtest(o, h, l, c, A.get("volume"), day_id=did, index=A["index"], return_trades=True)["trades"]
    res["plugin_way"] = {"P_trades": len(P), "A_trades": len(Ta), "exact_vs_plugin_engine": exact_pa,
                         "matches_100pct": bool(exact_pa == len(P) == len(Ta)),
                         "exact_vs_frozen_arm_b": exact_pb, "direct_plugin_call_equals_engine": [tuple(x[:2]) for x in direct] ==
                         [tuple(x[:2]) for x in Ta]}
    # plugin-only code paths and whether any fires in the window
    starts = np.r_[0, np.flatnonzero(did[1:] != did[:-1]) + 1]
    ends = np.r_[starts[1:], len(did)]
    flag = np.asarray(is_last_n_sessions_of_month(A["index"], 3, did), bool)
    res["plugin_only_paths"] = {
        "flagged_sessions_with_lt_2_bars": int(sum(1 for s, e in zip(starts, ends) if flag[s] and e - s < 2)),
        "flagged_sessions_with_lt_atr_bars_prior": int(sum(1 for s in starts if flag[s] and s < 14)),
        "flagged_session_starting_at_bar_14_exactly (plugin slice c[a-15:a-1] would wrap and raise)":
            int(sum(1 for s in starts if flag[s] and s == 14)),
        "gap_through_fills": int(sum(1 for x in Ta if x[1] != ends[np.searchsorted(starts, x[0], side='right') - 1] - 1
                                      and abs(o[x[1]] - (x[3] + x[4])) < 1e-9 and x[1] > x[0])),
        "stops_on_entry_bar": int(sum(1 for x in Ta if x[1] == x[0])),
        "stopped": int(sum(1 for x in Ta if x[1] != ends[np.searchsorted(starts, x[0], side='right') - 1] - 1)),
        "first_session_start_bar0_flagged (fallback would call max() on an empty slice)": bool(flag[0])}

    # ---- 3. literal-reading variants of 'ATR' (+ no stop for context)
    var = {}
    for kind in ("tr_mean", "wilder", "hl_mean", "none"):
        V = plugin_way(o, h, l, c, did, A["index"], atr_kind=kind)
        xv, gv = [x[1] for x in V], [x[5] for x in V]
        fh, fr = score(xv, gv, idxn, days, COST), score(xv, gv, idxn, days, REAL_COST)
        same = sum(1 for x in V if (x[0], 1) in ka and ka[(x[0], 1)][1] == x[1] and abs(ka[(x[0], 1)][4] - x[5]) < 1e-9)
        var[kind] = {"trades": len(V), "same_as_plugin": same, "house": line(fh), "real": line(fr),
                     "house_roc30": fh["roc30"], "gross_pts_per_trade": fh["gross_pts_per_trade"],
                     "one_episode_reading": fh["one_episode_reading"],
                     "promotes_at_house": bool(fh["gross_pts_per_trade"] >= COST and fh["roc30"] > 0
                                               and fh["one_episode_reading"] == "False")}
    res["atr_reading_variants"] = var

    # ---- 4. look-ahead: truncation and entry-bar neutralisation, every trade
    vol = A.get("volume")
    idx_arr = A["index"]
    ok_trunc_exit = ok_neutral = ok_stop = 0
    la_bad = []
    for (e, x, side, ep, g) in Ta:
        # the plugin skips a session of < 2 bars, so every truncation keeps >= 2 bars of the entry session; when the
        # trade stops on its entry bar (exit == entry) the one extra bar e+1 is overwritten flat at c[e] so its
        # contents cannot matter
        k = max(x + 1, e + 2)
        o1, h1, l1, c1 = o[:k].copy(), h[:k].copy(), l[:k].copy(), c[:k].copy()
        if x == e:
            o1[e + 1] = h1[e + 1] = l1[e + 1] = c1[e + 1] = c[e]
        rr = m.run_backtest(o1, h1, l1, c1, None, day_id=did[:k], index=idx_arr[:k], return_trades=True)
        lt = rr["trades"][-1] if rr else None
        if lt is not None and lt[0] == e and lt[1] == x and abs(lt[2] - g) < 1e-9:
            ok_trunc_exit += 1
        elif len(la_bad) < 5:
            la_bad.append(["trunc_exit", e, x, g, lt])
        k = e + 2                                         # entry bar + one bar, both flat at o[e]
        o2, h2, l2, c2 = o[:k].copy(), h[:k].copy(), l[:k].copy(), c[:k].copy()
        h2[e] = l2[e] = c2[e] = o[e]
        o2[e + 1] = h2[e + 1] = l2[e + 1] = c2[e + 1] = o[e]
        rr = m.run_backtest(o2, h2, l2, c2, None, day_id=did[:k], index=idx_arr[:k], return_trades=True)
        lt = rr["trades"][-1] if rr else None
        if lt is not None and lt[0] == e and lt[1] == e + 1 and abs(lt[2]) < 1e-12 and abs(lt[4] - ep) < 1e-12:
            ok_neutral += 1
        elif len(la_bad) < 5:
            la_bad.append(["neutral_entry_bar", e, lt])
        o3, l3, h3, c3 = o[:k].copy(), l[:k].copy(), h[:k].copy(), c[:k].copy()
        l3[e] = o[e] - 5000.0                             # entry bar's own h/l/c moved far: the stop must not move
        h3[e] = o[e] + 5000.0
        c3[e] = o[e] - 4000.0
        rr = m.run_backtest(o3, h3, l3, c3, None, day_id=did[:k], index=idx_arr[:k], return_trades=True)
        lt = rr["trades"][-1] if rr else None
        atr_own = float(np.mean(np.maximum(h[e - 14:e] - l[e - 14:e], np.maximum(np.abs(h[e - 14:e] - c[e - 15:e - 1]),
                                                                              np.abs(l[e - 14:e] - c[e - 15:e - 1])))))
        stop_own = o[e] - 2.0 * atr_own
        if lt is not None and lt[0] == e and lt[1] == e and abs((lt[4] + lt[2]) - stop_own) < 1e-9:
            ok_stop += 1
        elif len(la_bad) < 5:
            la_bad.append(["stop_from_prior_bars", e, stop_own, lt])
    res["lookahead"] = {"trades": len(Ta), "truncated_after_exit_identical": ok_trunc_exit,
                        "entry_bar_hlc_neutralised_entry_unchanged": ok_neutral,
                        "stop_level_from_bars_before_entry_only": ok_stop, "problems": la_bad,
                        "clean": bool(ok_trunc_exit == ok_neutral == ok_stop == len(Ta) and not la_bad)}

    # ---- 5. promotion bar (MANAGER #129, 10-16 15:37) and the old bar
    res["promotion"] = {
        "gross_pts_per_trade": house["gross_pts_per_trade"], "cost_house_pts": COST, "cost_real_pts": REAL_COST,
        "gross_ge_cost_house": bool(house["gross_pts_per_trade"] >= COST),
        "gross_ge_cost_real": bool(house["gross_pts_per_trade"] >= REAL_COST),
        "net_roc30_house": house["roc30"], "roc_gt_0": bool(house["roc30"] > 0),
        "one_episode_reading": house["one_episode_reading"],
        "promotes_new_bar": bool(house["gross_pts_per_trade"] >= COST and house["roc30"] > 0
                                 and house["one_episode_reading"] == "False"),
        "promotes_old_bar_roc_ge_15": bool(house["roc30"] >= 15 and house["one_episode_reading"] == "False"),
        "lab_promotion_line": labf.get("promotion"), "lab_promoted": labf.get("promoted")}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    path = os.path.join(OUT, "ttm_trace.json")
    open(path, "w", encoding="utf-8", newline="\n").write(s + "\n")
    print(s)
    print("trace output sha256", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
