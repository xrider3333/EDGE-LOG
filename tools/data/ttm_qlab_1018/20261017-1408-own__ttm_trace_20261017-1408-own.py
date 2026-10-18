"""TTM QL_LATEMOM_NQ (20261017-1408-own) - STAGE 2: COMPARE + TRACE.
Written AFTER stage 1's output sha cd4c3f96fc63... was posted to MANAGER (#1479). Opens the lab's numbers_pre_wf.json and
pre_wf_trades.csv and the plugin code for the first time in this stage.

 1. arm A (plugin as run through the engine, TTM booking) vs the lab's numbers_pre_wf.json, field by field, and vs
    pre_wf_trades.csv trade for trade.
 2. TTM's OWN rule (stage-1 arm B, ttm_armb_own_rule.py, pinned LF sha 9b228fc8...) re-implemented here with two switches for the
    plugin's departures from the Mechanism text:
      d1  skip the session when the trailing SIGNED median block move <= 0 (or the median morning range <= 0)
          (plugin: 'if med_block <= 0 or med_morn <= 0: continue' - no such clause in the text)
      d2  trailing set = the last 20 sessions BY COUNT (j in i-20..i-1), short sessions inside it dropped, >= 10 full ones
          needed, and no trade before session index 20 (plugin) - vs arm B's 'last 20 prior FULL sessions'
    With both off the function must equal arm B trade for trade; with both on it must equal the plugin 100%.
    Each slip alone is scored (four numbers, house + real + stress), plus the text's own contradictions (clock labels
    14:30 vs bar 54 = 14:00; hypothesis 'median block RANGE' vs the Mechanism's signed close-open).
 3. Look-ahead: (a) scramble high/low/close of bars 66..77 and open of bars 67..77 in EVERY session -> entries and sides must
    not move; (b) cut the data at the end of a sampled session -> that session's trade must not change (no future session
    read); (c) today's-session-length check 'b - a < 78' - count sessions with 66..77 bars (the only case where it could matter).
 4. Four numbers strings, promotion bar (MANAGER #129, 10-16 15:37) and the old bar.
Writes only ttm_trace.json in this folder."""
import hashlib
import importlib.util
import json
import os
import sys
import types

os.environ["AUGUR_TRIAL_CACHE"] = "0"
import numpy as np    # noqa: E402
import pandas as pd   # noqa: E402

OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1408-own"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1408-own"
spec = importlib.util.spec_from_file_location("ttm_v1408", os.path.join(OUT, "ttm_verify_20261017-1408-own.py"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)          # sets AUGUR_TRIAL_CACHE=0, sys.path, imports the engine; main() not run
assert V.lf_sha(V.PLUGIN) == V.PIN_PREREG_FULL, "plugin pin"
assert V.lf_sha(V.ARMB) == V.ARMB_SHA_AT_BUILD, "arm B pin"
spec_b = importlib.util.spec_from_file_location("ttm_armb", V.ARMB)
ARMB = importlib.util.module_from_spec(spec_b)
spec_b.loader.exec_module(ARMB)


def own_rule(o, h, l, c, day_id, trend_k=0.5, counter_k=1.5, lb=20, d1=False, d2=False,
             blk0=54, morn_end=54, block_stat="signed"):
    """TTM's arm B rule with switches. blk0 = first block bar (54 = Mechanism index, 60 = the text's '14:30' clock label);
    morn_end = first bar AFTER the morning (54 index / 60 clock); block_stat 'signed' (Mechanism) | 'range' (Hypothesis).
    Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    L = ends - starts
    full = L >= 78
    mv = np.full(len(starts), np.nan)
    bs = np.full(len(starts), np.nan)
    mr = np.full(len(starts), np.nan)
    for i, (s, e) in enumerate(zip(starts, ends)):
        if full[i]:
            mv[i] = c[s + 65] - o[s + blk0]
            bs[i] = mv[i] if block_stat == "signed" else (np.max(h[s + blk0:s + 66]) - np.min(l[s + blk0:s + 66]))
            mr[i] = np.max(h[s:s + morn_end]) - np.min(l[s:s + morn_end])
    full_idx = np.flatnonzero(full)
    out = []
    stats = {"skipped_d1_block": 0, "skipped_d1_morn": 0, "windows_lt20_full": 0, "windows_lt10_full": 0}
    for i, (s, e) in enumerate(zip(starts, ends)):
        if not full[i]:
            continue
        if d2:
            if i < lb:
                continue
            win = [j for j in range(i - lb, i) if full[j]]
            if len(win) < lb:
                stats["windows_lt20_full"] += 1
            if len(win) < lb // 2:
                stats["windows_lt10_full"] += 1
                continue
        else:
            win = full_idx[full_idx < i][-lb:]
            if len(win) < lb:
                continue
        med_block = float(np.median(bs[win]))
        med_morn = float(np.median(mr[win]))
        if d1 and (med_block <= 0 or med_morn <= 0):
            stats["skipped_d1_block"] += int(med_block <= 0)
            stats["skipped_d1_morn"] += int(med_morn <= 0)
            continue
        room = mr[i] <= counter_k * med_morn
        side = 1 if (mv[i] >= trend_k * med_block and room) else (-1 if (-mv[i] >= trend_k * med_block and room) else 0)
        if side:
            ent, xb = int(s + 66), int(e - 1)
            out.append((ent, xb, int(side), float(o[ent]), float(c[xb]), float(side * (c[xb] - o[ent]))))
    return out, stats


def cmp(Ta, B):
    """Ta (entry, exit, side, entry_px, gross); B own_rule rows."""
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = set(ka) & set(kb)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][3] - kb[k][3]) < 1e-9 and abs(ka[k][4] - kb[k][5]) < 1e-9)
    return {"plugin": len(Ta), "own": len(B), "same_entry_side": len(both), "exact_entry_exit_px_pts": exact,
            "only_plugin": len(set(ka) - set(kb)), "only_own": len(set(kb) - set(ka)),
            "match_100pct": bool(exact == len(Ta) == len(B))}


def fmt4(f):
    return (f"ROC@30k {f['roc30']:.2f} | DD5 ${f['dd5']:,.0f}{' (one episode)' if f['one_episode'] else ''} | "
            f"DD% from peak {f['dd_pct_peak']:.1f}% | Sortino {f['sortino']:.2f} | trades {f['trades']:,} "
            f"({f['trades_per_yr']:.0f}/yr) | $/yr {f['per_yr_usd']:,.0f} | gross {f['gross_per_trade_pts']:+.3f} pt/trade")


def main():
    row = [x for x in V.list_masters() if x.get("filename") == V.MASTER]
    assert len(row) == 1
    A = V.load_master_arrays(row[0], date_from=V.D0, date_to=V.D1)
    assert A.get("fingerprint") == V.PREREG_FINGERPRINT and len(A["close"]) == V.PREREG_BARS
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res = {"idea": "QL_LATEMOM_NQ", "folder": "20261017-1408-own", "stage": "2 compare + trace",
           "stage1_output_sha256_posted": "cd4c3f96fc63ece343146c19daaf181d8eb1e79337aa92ebad38f1707c13b27d",
           "plugin_lf_sha256": V.lf_sha(V.PLUGIN), "armb_lf_sha256": V.lf_sha(V.ARMB),
           "costs_pts_rt": {"house": V.COST, "real": V.REAL_COST, "stress": V.STRESS_COST,
                            "real_derivation": "2 x 0.25 pt tick + $5.65 / $20 = 0.5 + 0.2825 = 0.7825"}}

    # ---- ARM A: plugin through the engine (stage-1 path)
    m = types.ModuleType("ttm_ql_latemom_s2")
    m.__file__ = V.PLUGIN
    exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
    r = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]
    AH = V.score([t[1] for t in Ta], [t[4] for t in Ta], idxn, days, V.COST)
    AR = V.score([t[1] for t in Ta], [t[4] for t in Ta], idxn, days, V.REAL_COST)
    AS = V.score([t[1] for t in Ta], [t[4] for t in Ta], idxn, days, V.STRESS_COST)
    usd = (np.array([t[4] for t in Ta]) - V.COST) * V.MULT
    daily = pd.Series(usd, index=idxn[[t[1] for t in Ta]].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    d5 = V.dd5(daily)
    pf = float(usd[usd > 0].sum() / -usd[usd < 0].sum())

    # ---- 1. vs the lab's numbers_pre_wf.json
    L = json.load(open(os.path.join(IDEA, "numbers_pre_wf.json"), encoding="utf-8"))
    N = L["numbers"]
    rows = []

    def chk(field, lab, mine, tol, note=""):
        ok = (lab == mine) if tol is None else (abs(float(lab) - float(mine)) <= tol)
        rows.append({"numbers_file": "numbers_pre_wf.json", "field": field, "lab": lab, "mine": mine, "tol": tol,
                     "match": bool(ok), "note": note})

    chk("trades", N["trades"], AH["trades"], None)
    chk("net_usd", N["net_usd"], round(AH["net_usd"], 4), 1.0)
    chk("roc_30k", N["roc_30k"], round(AH["roc30"], 6), 0.005)
    chk("dd5_usd", N["dd5_usd"], AH["dd5"], 1.0)
    chk("max_dd_usd", N["max_dd_usd"], round(AH["max_dd"], 4), 1.0)
    chk("dd_pct_peak", N["dd_pct_peak"], AH["dd_pct_peak"], 0.01)
    chk("sortino", N["sortino"], round(AH["sortino"], 6), 0.001)
    chk("one_episode", N["one_episode"], AH["one_episode"], None)
    chk("win_rate (lab %, mine x100)", N["win_rate"], round(100 * AH["win_rate"], 4), 0.05)
    # the lab's own gross / cost line, field by field
    chk("cost_pts", N["cost_pts"], V.COST, 1e-9, "house RT cost")
    chk("mult", N["mult"], V.MULT, 1e-9)
    chk("gross_pts_per_trade", N["gross_pts_per_trade"], round(AH["gross_per_trade_pts"], 6), 0.0001)
    chk("net_pts_per_trade", N["net_pts_per_trade"], round(AH["net_per_trade_pts"], 6), 0.0001)
    chk("gross_cost_ratio", N["gross_cost_ratio"], round(AH["gross_over_cost"], 6), 0.005)
    chk("net_usd_per_trade", N["net_usd_per_trade"], round(AH["net_per_trade_usd"], 4), 0.01)
    chk("trades_per_year", N["trades_per_year"], round(AH["trades_per_yr"], 4), 0.05)
    chk("years", N["years"], round(AH["years"], 6), 0.0005)
    chk("sessions", N["sessions"], len(days), None)
    chk("dd5_n", N["dd5_n"], d5["n"], None)
    chk("profit_factor", N["profit_factor"], round(pf, 6), 0.0001)
    chk("mtm_marked / unmarked / dropped_before_wf", [N["mtm_marked"], N["mtm_unmarked"], N["dropped_before_wf"]], [0, 0, 0], None)
    chk("fingerprint", L["fingerprint"], A.get("fingerprint"), None)
    chk("bars", L["bars"], len(c), None)
    chk("params", L["params"], V.PARAMS_B, None)
    chk("first_signal_bar_check.n (entries before bar 66)", L["first_signal_bar_check"]["n"], 0, None)
    res["lab_vs_arm_a"] = rows
    res["lab_promotion_text"] = L.get("promotion")
    res["lab_promoted"] = L.get("promoted")

    # ---- 1b. vs pre_wf_trades.csv trade for trade
    T = pd.read_csv(os.path.join(IDEA, "pre_wf_trades.csv"))
    ok_rows = 0
    bad = []
    for (ea, xa, sa, pa, ga), (_, t) in zip(Ta, T.iterrows()):
        good = (int(t.entry_bar) == ea and int(t.exit_bar) == xa and int(t.side) == sa and abs(t.entry_price - pa) < 1e-9
                and abs(t.pnl_points_net - (ga - V.COST)) < 1e-5
                and pd.Timestamp(t.entry_time).tz_localize(None) == idxn[ea]
                and pd.Timestamp(t.exit_time).tz_localize(None) == idxn[xa])
        ok_rows += int(good)
        if not good and len(bad) < 5:
            bad.append([ea, xa, sa, pa, ga, t.to_dict()])
    res["trades_csv_vs_arm_a"] = {"csv_rows": len(T), "arm_a_trades": len(Ta), "rows_identical": ok_rows,
                                  "all_identical": bool(ok_rows == len(T) == len(Ta)), "first_bad": bad,
                                  "csv_net_pts_sum": float(T.pnl_points_net.sum()),
                                  "arm_a_net_pts_sum": float(sum(t[4] for t in Ta) - V.COST * len(Ta))}
    # the lab files are the engine's own trades; also the plugin called DIRECTLY (no engine) gives the same list
    rd = m.run_backtest(o, h, l, c, day_id=day_id, index=A["index"], return_trades=True)
    Td = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in rd["trades"]]
    res["plugin_direct_equals_engine"] = bool(Td == Ta)

    # ---- 2. own rule, plugin's way
    B_ref = ARMB.own_rule(o, h, l, c, day_id, **V.PARAMS_B)
    var = {}
    for nm, kw in (("literal_armB", {}), ("d1_only", {"d1": True}), ("d2_only", {"d2": True}),
                   ("plugin_way_d1_d2", {"d1": True, "d2": True}),
                   ("clock_labels_literal", {"blk0": 60, "morn_end": 60}),
                   ("clock_labels_plugin_way", {"blk0": 60, "morn_end": 60, "d1": True, "d2": True}),
                   ("hyp_block_range_literal", {"block_stat": "range"}),
                   ("hyp_block_range_plugin_way", {"block_stat": "range", "d1": True, "d2": True})):
        B, st = own_rule(o, h, l, c, day_id, **kw)
        ex, gp = [t[1] for t in B], [t[5] for t in B]
        var[nm] = {"switches": kw, "skip_stats": st, "vs_plugin": cmp(Ta, B),
                   "house": V.score(ex, gp, idxn, days, V.COST), "real": V.score(ex, gp, idxn, days, V.REAL_COST),
                   "stress": V.score(ex, gp, idxn, days, V.STRESS_COST)}
        var[nm]["four_house"] = fmt4(var[nm]["house"])
        var[nm]["four_real"] = fmt4(var[nm]["real"])
        var[nm]["promotes_new_bar_house"] = bool(var[nm]["house"]["gross_per_trade_pts"] >= V.COST and var[nm]["house"]["roc30"] > 0
                                                 and not var[nm]["house"]["one_episode"])
        if nm == "literal_armB":
            var[nm]["equals_stage1_armB_trade_for_trade"] = bool(B == B_ref)
    res["variants"] = var
    res["b_plugin_way_matches_100pct"] = var["plugin_way_d1_d2"]["vs_plugin"]["match_100pct"]
    res["literal_reproduces_stage1_armB"] = var["literal_armB"]["equals_stage1_armB_trade_for_trade"]

    # ---- 3. look-ahead checks on the plugin itself
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(c)]
    Ls = ends - starts
    rng = np.random.default_rng(20261018)
    o2, h2, l2, c2 = o.copy(), h.copy(), l.copy(), c.copy()
    for s, e in zip(starts, ends):
        if e - s >= 78:
            seg = slice(s + 66, e)
            base = o[s + 66]
            c2[seg] = base + rng.normal(0, 40, e - s - 66)
            o2[s + 67:e] = base + rng.normal(0, 40, e - s - 67)
            hi = np.maximum(o2[seg], c2[seg]) + rng.uniform(0, 30, e - s - 66)
            lo = np.minimum(o2[seg], c2[seg]) - rng.uniform(0, 30, e - s - 66)
            h2[seg], l2[seg] = hi, lo
    rp = m.run_backtest(o2, h2, l2, c2, day_id=day_id, index=A["index"], return_trades=True)
    Tp = [(int(t[0]), int(t[3])) for t in rp["trades"]]
    la = {"scramble_bars_66_77_every_session": {
        "entries_sides_unchanged": bool(Tp == [(t[0], t[2]) for t in Ta]), "trades_after": len(Tp),
        "entry_px_unchanged": bool([float(t[4]) for t in rp["trades"]] == [t[3] for t in Ta])}}
    samp = sorted(rng.choice(len(Ta), size=25, replace=False).tolist())
    cut_ok = 0
    for k in samp:
        e_bar = Ta[k][0]
        si = int(np.searchsorted(starts, e_bar, side="right") - 1)
        cut = int(ends[si])
        rc = m.run_backtest(o[:cut], h[:cut], l[:cut], c[:cut], day_id=day_id[:cut], index=A["index"][:cut], return_trades=True)
        last = rc["trades"][-1] if rc and rc.get("trades") else None
        cut_ok += int(last is not None and (int(last[0]), int(last[1]), int(last[3]), float(last[4]), float(last[2])) == Ta[k])
    la["cut_data_at_session_end_25_sampled"] = {"checked": len(samp), "identical": cut_ok}
    la["session_lengths"] = {str(k): int(v) for k, v in pd.Series(Ls).value_counts().sort_index().items()}
    la["sessions_with_66_to_77_bars"] = int(((Ls >= 66) & (Ls < 78)).sum())
    la["sessions_over_78_bars"] = int((Ls > 78).sum())
    la["reading"] = ("signal reads close[a+65], open[a+54], high/low[a..a+53] of today and bars 0..65 of PRIOR sessions only; "
                     "fill at open[a+66]; exit close[b-1] = bar 77. 'b - a < 78' reads today's session length, but no session "
                     "has 66..77 bars (short sessions are 24-46 bars, so bar 66 never exists on them) and the half days are "
                     "on the published calendar: no effect. No ATR, stop, target or size.")
    res["lookahead"] = la

    # ---- 4. four numbers + promotion bar
    res["arm_a"] = {"house": AH, "real": AR, "stress": AS, "pf_house": pf, "dd5_n_house": d5["n"],
                    "four_house": fmt4(AH), "four_real": fmt4(AR), "four_stress": fmt4(AS)}
    res["promotion_new_bar_129"] = {
        "gross_pt_per_trade": AH["gross_per_trade_pts"], "house_cost_pts": V.COST, "real_cost_pts": V.REAL_COST,
        "gross_ge_house_cost": bool(AH["gross_per_trade_pts"] >= V.COST),
        "gross_ge_real_cost": bool(AH["gross_per_trade_pts"] >= V.REAL_COST),
        "net_roc30_house_gt_0": bool(AH["roc30"] > 0), "one_episode_house": AH["one_episode"],
        "promotes": bool(AH["gross_per_trade_pts"] >= V.COST and AH["roc30"] > 0 and not AH["one_episode"]),
        "old_bar_roc_ge_15_not_one_episode": bool(AH["roc30"] >= 15 and not AH["one_episode"])}
    lab_ok = all(x["match"] for x in rows)
    res["verdict"] = "VERIFIED EXACT" if lab_ok and res["trades_csv_vs_arm_a"]["all_identical"] else "DIFFERENCE"
    s = json.dumps(res, indent=1, default=float)
    open(os.path.join(OUT, "ttm_trace.json"), "w", encoding="utf-8").write(s + "\n")
    print(s)


if __name__ == "__main__":
    main()
