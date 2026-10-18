"""TTM QL_QUIETBREAK_NQ (folder 20261017-1555-own) - STAGE 2 COMPARE + TRACE.
Written AFTER the stage-1 output (ttm_verify.json, sha256 f3c6c592...) was posted to MANAGER (#1473).
Re-uses the stage-1 harness (own_rule / score / four, unchanged) and adds:
 (1) arm A (plugin through the engine, house cost) vs the lab's numbers_pre_wf.json field by field, and vs pre_wf_trades.csv
     trade by trade;
 (2) own_rule_plugin_way: TTM's own rule with the ONE departure the plugin makes (trailing median over UP TO `lookback`
     prior sessions, NaN dropped, minimum 5) plus the plugin's inert guards (session < 14 bars, median <= 0, MR <= 0) ->
     must equal the plugin trade for trade (entry bar, exit bar, side, entry px, gross pts);
 (3) the literal reading (= stage-1 arm B, full 20 prior sessions) four numbers, house / real / stress;
 (4) look-ahead: every plugin trade re-run with the data TRUNCATED after its fill bar and that fill bar's high/low/close
     overwritten with junk (open kept) - the entry must be reproduced (decision reads bars <= k only, fill at open[k+1]);
 (5) data notes: short (truncated) sessions the ride-to-close exits on; quiet_k 0.8 (plugin_v1's default) for context.
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1555-own/."""
import hashlib
import importlib.util
import json
import os
import types

import numpy as np
import pandas as pd

OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1555-own"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1555-own"
spec = importlib.util.spec_from_file_location("ttm_v1555", os.path.join(OUT, "ttm_verify_20261017-1555-own.py"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)            # sets AUGUR_TRIAL_CACHE=0 before importing augur_engine


def own_rule_plugin_way(o, h, l, c, day_id, quiet_k=1.0, lookback=20, morning_bars=12, min_prior=5):
    """own_rule (stage 1, blind) with the plugin's warm-up: median over the up-to-`lookback` prior sessions with a finite
    morning range, needing >= min_prior of them; plus the plugin's guards (session >= 14 bars, median > 0, MR > 0)."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    mr = np.array([h[s:s + morning_bars].max() - l[s:s + morning_bars].min() if e - s >= morning_bars else np.nan
                   for s, e in zip(starts, ends)])
    out = []
    for i, (s, e) in enumerate(zip(starts, ends)):
        if e - s < 14 or i < 1 or not np.isfinite(mr[i]) or mr[i] <= 0:
            continue
        prior = mr[max(0, i - lookback):i]
        prior = prior[np.isfinite(prior)]
        if prior.size < min_prior:
            continue
        med = float(np.median(prior))
        if not med > 0 or not mr[i] <= quiet_k * med:
            continue
        mh = h[s:s + morning_bars].max()
        ml = l[s:s + morning_bars].min()
        for k in range(s + morning_bars, e):
            side = 1 if c[k] > mh else (-1 if c[k] < ml else 0)
            if side == 0:
                continue
            if k + 1 < e:
                ent, xb = k + 1, e - 1
                ep, xp = float(o[ent]), float(c[xb])
                out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep))))
            break
    return out


def diff(Ta, B):
    """Ta: (entry, exit, side, entry_px, gross); B: own_rule tuples (entry, exit, side, ep, xp, gross)."""
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = set(ka) & set(kb)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][3] - kb[k][3]) < 1e-9 and abs(ka[k][4] - kb[k][5]) < 1e-9)
    return {"plugin_trades": len(Ta), "own_trades": len(B), "same_entry_side": len(both), "only_plugin": len(set(ka) - set(kb)),
            "only_own": len(set(kb) - set(ka)), "exact_entry_exit_side_px_pts": exact,
            "match_100pct": bool(len(Ta) == len(B) == exact)}


def fmt(f):
    return (f"ROC@30k {f['roc30']:.2f} | DD5 ${f['dd5']:,.0f} | DD% from peak {f['dd_pct_peak']:.1f}% | Sortino {f['sortino']:.2f} | "
            f"trades {f['trades']:,} ({f['trades_per_yr']:.0f}/yr) | $/yr {f['per_yr_usd']:,.0f} | gross {f['gross_per_trade_pts']:+.4f} pt/trade "
            f"vs cost {f['cost_pts_rt']:.4f} pt | one_episode {f['one_episode']}")


def main():
    assert hashlib.sha256(open(os.path.join(OUT, "ttm_verify.json"), "rb").read()).hexdigest().startswith("f3c6c592a2d3")
    assert V.lf_sha(V.PLUGIN) == V.PIN_FULL_PREREG
    row = [x for x in V.list_masters() if x.get("filename") == V.MASTER]
    assert len(row) == 1
    A = V.load_master_arrays(row[0], date_from=V.D0, date_to=V.D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    m = types.ModuleType("ttm_ql_quietbreak_trace")
    m.__file__ = V.PLUGIN
    exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
    r = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]
    res = {"fingerprint": A.get("fingerprint"), "bars": len(c), "sessions": len(days)}
    sA = V.arm([t[1] for t in Ta], [t[4] for t in Ta], idxn, days)
    hA = sA["house_cost"]

    # (1a) lab numbers file vs arm A (house cost)
    lab = json.load(open(os.path.join(IDEA, "numbers_pre_wf.json"), encoding="utf-8"))
    N = lab["numbers"]
    usd = (np.array([t[4] for t in Ta]) - V.COST) * V.MULT
    pf = float(usd[usd > 0].sum() / -usd[usd < 0].sum())
    from augur_engine.drawdowns import dd5 as _dd5
    s_daily = pd.Series(usd, index=idxn[np.array([t[1] for t in Ta])].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    dd5n = int(_dd5(s_daily)["n"])
    rows = [("trades", N["trades"], hA["trades"], 0),
            ("net_usd", N["net_usd"], round(hA["net_usd"], 2), 1.0),
            ("roc_30k", N["roc_30k"], round(hA["roc30"], 4), 0.005),
            ("dd5_usd", N["dd5_usd"], hA["dd5"], 1.0),
            ("max_dd_usd", N["max_dd_usd"], round(hA["max_dd"], 2), 1.0),
            ("dd_pct_peak", N["dd_pct_peak"], hA["dd_pct_peak"], 0.01),
            ("sortino", N["sortino"], round(hA["sortino"], 4), 0.001),
            ("one_episode", N["one_episode"], hA["one_episode"], None),
            ("win_rate (lab %, mine x100)", N["win_rate"], round(100 * hA["win_rate"], 4), 0.05),
            ("trades_per_year", N["trades_per_year"], round(hA["trades_per_yr"], 4), 0.05),
            ("years", N["years"], round(hA["years"], 4), 0.001),
            ("sessions", N["sessions"], len(days), 0),
            ("cost_pts", N["cost_pts"], V.COST, 0),
            ("mult", N["mult"], V.MULT, 0),
            ("gross_pts_per_trade", N["gross_pts_per_trade"], round(hA["gross_per_trade_pts"], 4), 0.0001),
            ("net_pts_per_trade", N["net_pts_per_trade"], round(hA["gross_per_trade_pts"] - V.COST, 4), 0.0001),
            ("net_usd_per_trade", N["net_usd_per_trade"], round(hA["net_per_trade_usd"], 4), 0.01),
            ("gross_cost_ratio", N["gross_cost_ratio"], round(hA["gross_over_cost"], 4), 0.001),
            ("profit_factor (net, per trade)", N["profit_factor"], round(pf, 4), 0.0001),
            ("dd5_n", N["dd5_n"], dd5n, 0),
            ("fingerprint", lab["fingerprint"], A.get("fingerprint"), None),
            ("bars", lab["bars"], len(c), 0),
            ("first_signal_bar_check.earliest_session_bar", lab["first_signal_bar_check"]["earliest_session_bar"],
             int(min(t[0] - np.r_[0, np.flatnonzero(np.diff(day_id)) + 1][np.searchsorted(np.r_[0, np.flatnonzero(np.diff(day_id)) + 1], t[0], side="right") - 1] for t in Ta)), 0)]
    cmp = []
    for f, lv, mv, tol in rows:
        ok = (lv == mv) if tol is None else (abs(float(lv) - float(mv)) <= tol + 1e-12)
        cmp.append({"field": f, "lab": lv, "mine": mv, "tol": tol, "match": bool(ok)})
    res["numbers_pre_wf_vs_armA_house"] = cmp
    res["numbers_pre_wf_all_match"] = all(x["match"] for x in cmp)
    res["lab_promotion_text"] = lab.get("promotion")
    res["lab_params"] = lab.get("params")

    # (1b) lab trades csv vs arm A
    T = pd.read_csv(os.path.join(IDEA, "pre_wf_trades.csv"))
    mine = pd.DataFrame(Ta, columns=["entry_bar", "exit_bar", "side", "entry_price", "gross"])
    same_len = len(T) == len(mine)
    tm = {}
    if same_len:
        tm["entry_bar"] = int((T["entry_bar"].to_numpy() == mine["entry_bar"].to_numpy()).sum())
        tm["exit_bar"] = int((T["exit_bar"].to_numpy() == mine["exit_bar"].to_numpy()).sum())
        tm["side"] = int((T["side"].to_numpy() == mine["side"].to_numpy()).sum())
        tm["entry_price"] = int((np.abs(T["entry_price"].to_numpy() - mine["entry_price"].to_numpy()) < 1e-9).sum())
        tm["net_pts (lab) == gross - 0.533 (mine), |d|<1e-6"] = int((np.abs(T["pnl_points_net"].to_numpy() - (mine["gross"].to_numpy() - V.COST)) < 1e-6).sum())
        et = pd.to_datetime(T["entry_time"], utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None).to_numpy()
        xt = pd.to_datetime(T["exit_time"], utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None).to_numpy()
        tm["entry_time == bar index time"] = int((et == idxn[mine["entry_bar"].to_numpy()].to_numpy()).sum())
        tm["exit_time == bar index time"] = int((xt == idxn[mine["exit_bar"].to_numpy()].to_numpy()).sum())
        tm["lab_net_pts_sum"] = float(T["pnl_points_net"].sum())
        tm["mine_net_pts_sum"] = float((mine["gross"] - V.COST).sum())
    res["pre_wf_trades_csv_vs_armA"] = {"lab_rows": len(T), "mine": len(mine), "per_field_equal_rows": tm,
                                        "all_match": bool(same_len and all(v == len(T) for k, v in tm.items() if not k.endswith("_sum")))}

    # (2) own rule the plugin's way vs the plugin
    Bp = own_rule_plugin_way(o, h, l, c, day_id)
    res["own_rule_plugin_way_vs_plugin"] = diff(Ta, Bp)
    # direct call == engine (needed for the truncation test)
    rd = m.run_backtest(o, h, l, c, None, day_id, A["index"], return_trades=True)
    Td = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in rd["trades"]]
    res["direct_plugin_call_equals_engine"] = bool(Td == Ta)

    # (3) literal reading (stage-1 arm B) and the slip's isolated effect
    B = V.own_rule(o, h, l, c, day_id)
    res["own_rule_literal_vs_plugin"] = diff(Ta, B)
    sB = V.arm([t[1] for t in B], [t[5] for t in B], idxn, days)
    res["four_numbers"] = {"A_plugin": {k: fmt(v) for k, v in sA.items()}, "B_literal_full20": {k: fmt(v) for k, v in sB.items()}}
    res["A_plugin_scores"] = sA
    res["B_literal_scores"] = sB

    # (4) look-ahead: truncate after each fill bar, junk that bar's h/l/c, entry must reproduce
    rng = np.random.default_rng(20261018)
    ok = 0
    bad = []
    for t in Ta:
        e = t[0]
        oo, hh, ll, cc = o[:e + 1].copy(), h[:e + 1].copy(), l[:e + 1].copy(), c[:e + 1].copy()
        j = rng.uniform(-200, 200)
        hh[e], ll[e], cc[e] = oo[e] + abs(j) + 50, oo[e] - abs(j) - 50, oo[e] + j
        rt = m.run_backtest(oo, hh, ll, cc, None, day_id[:e + 1], A["index"][:e + 1], return_trades=True)
        last = rt["trades"][-1] if rt and rt.get("trades") else None
        if last is not None and int(last[0]) == e and int(last[3]) == t[2] and abs(float(last[4]) - t[3]) < 1e-9:
            ok += 1
        else:
            bad.append([str(idxn[e]), t[2], None if last is None else [int(last[0]), int(last[3])]])
    res["lookahead_truncate_and_junk_fill_bar"] = {"trades_tested": len(Ta), "entry_reproduced": ok, "failed": bad[:10]}

    # (5) data notes
    st = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    en = np.r_[st[1:], len(c)]
    slen = en - st
    sess_of = np.searchsorted(st, np.arange(len(c)), side="right") - 1
    short = [i for i in range(len(st)) if slen[i] < 78]
    tr_short = [t for t in Ta if slen[sess_of[t[0]]] < 78]
    res["data_short_sessions"] = {
        "sessions_lt_78_bars": len(short),
        "by_length": {int(k): int(v) for k, v in zip(*np.unique(slen[short], return_counts=True))},
        "last_bar_times": sorted({str(idxn[en[i] - 1].time()) for i in short}),
        "plugin_trades_in_short_sessions": len(tr_short),
        "those_trades": [[str(idxn[t[0]]), str(idxn[t[1]]), t[2], t[4]] for t in tr_short],
        "those_gross_pts_sum": float(sum(t[4] for t in tr_short)),
        "min_session_bars": int(slen.min())}
    Ta_full = [t for t in Ta if slen[sess_of[t[0]]] >= 78]
    res["A_plugin_full_sessions_only_house"] = fmt(V.score([t[1] for t in Ta_full], [t[4] for t in Ta_full], idxn, days, V.COST))
    r8 = V.run_backtest(m, instrument="NQ", arrays=A, params={"quiet_k": 0.8, "lookback": 20}, cost_pts=0.0, return_trades=True)
    T8 = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r8["trades"]]
    res["variant_quiet_k_0p8_plugin_v1_default"] = {k: fmt(V.score([t[1] for t in T8], [t[4] for t in T8], idxn, days, cst))
                                                    for k, cst in (("house", V.COST), ("real", V.REAL_COST))}
    res["warmup_trades_only_plugin"] = [[str(idxn[t[0]]), t[2], t[4], int(sess_of[t[0]])] for t in Ta if sess_of[t[0]] < 20]
    s = json.dumps(res, indent=1, default=float)
    print(s)
    p = os.path.join(OUT, "ttm_trace.json")
    open(p, "w", encoding="utf-8", newline="\n").write(s + "\n")
    print("trace sha256", hashlib.sha256(open(p, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
