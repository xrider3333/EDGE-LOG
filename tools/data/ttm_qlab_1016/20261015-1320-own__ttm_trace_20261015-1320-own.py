"""TTM (house verifier): STAGE 2 - COMPARE + TRACE for Qwen Lab idea QL_VWAPREVERT_NQ, second run (plugin v2, LF sha256 dbcf3008...),
idea folder C:/EdgeLog/qwen_lab/ideas/20261015-1320-own/. Written AFTER the stage-1 output (ttm_verify.json, sha256 9c5084e4...) was
posted to MANAGER; the lab's numbers_pre_wf.json, pre_wf_trades.csv and the plugin code are opened here for the first time.

1. COMPARE: the lab's numbers_pre_wf.json field by field against TTM arm A (plugin through the engine, house cost 0.533), and the lab's
   pre_wf_trades.csv trade for trade against arm A's engine trades (and re-scored through TTM's yardstick).
2. TRACE: TTM's own rule (stage-1 arm B, reused verbatim from ttm_verify_20261015-1320-own.py) is generalised with one switch per
   departure the plugin makes from the prereg text:
     warm      global warm-up bar index: prereg 'k >= 25'  vs plugin 'k >= atr_window' (= 20)
     skip      skip sessions with fewer than N bars: prereg none vs plugin 'b - a < atr_window + 5' (= 25)
     gaps      later-bar order: prereg reading (stop gap, target gap, then intrabar stop-first) vs plugin (intrabar stop incl. a
               stop gap, THEN target incl. a target gap) - differs only on a bar that opens beyond the target and trades to the stop
     atr0      plugin skips a bar whose ATR <= 0; prereg says nothing
   PLUGIN WAY = (warm 20, skip 25, gaps plugin, atr0 on) must equal the plugin 100% trade for trade (entry, side, entry px, exit, pts).
   LITERAL = (warm 25, skip none, gaps prereg, atr0 off) must equal stage-1 arm B. Each single slip is reverted one at a time and scored
   with the four numbers.
3. LOOK-AHEAD: per-trade perturbation on a one-session slice (future bars randomised -> entry unchanged; a designed shock on the entry
   bar -> the implied stop / target distance equals the ATR of bars k-19..k only); truncation test (session cut right after the entry
   bar -> does the plugin still take the trade? the session-length skip reads the session's future bar count).
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1320-own/."""
import hashlib
import importlib.util
import json
import os
import types

import numpy as np
import pandas as pd

OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261015-1320-own"
spec = importlib.util.spec_from_file_location("ttm_v", OUT + "/ttm_verify_20261015-1320-own.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)            # sets AUGUR_TRIAL_CACHE=0, sys.path, chdir; main() not run
assert os.environ.get("AUGUR_TRIAL_CACHE") == "0"

LAB_NUMBERS = V.IDEA + "/numbers_pre_wf.json"
LAB_TRADES = V.IDEA + "/pre_wf_trades.csv"


def rule(o, h, l, c, day_id, warm=25, skip=None, gaps="prereg", atr0=False, warm_in_session=False):
    """TTM's stage-1 own_rule with one switch per plugin departure. Returns [(entry, exit, side, entry_px, exit_px, gross_pts)]."""
    n = len(c)
    rng = h - l
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    out = []
    for s, e in zip(starts, ends):
        if skip is not None and e - s < skip:
            continue
        csum = 0.0
        for k in range(s, e):
            csum += c[k]
            if warm_in_session:
                if k - s < warm:
                    continue
            elif k < warm:
                continue
            if k + 1 >= e:
                break
            vw = csum / (k - s + 1)
            atr = rng[k - 19:k + 1].mean()
            if atr0 and atr <= 0:
                continue
            if c[k] > vw + 2.5 * atr:
                side = -1
            elif c[k] < vw - 2.5 * atr:
                side = 1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * 1.0 * atr
            tgt = ep + side * 1.5 * atr
            xb, xp = e - 1, c[e - 1]
            for j in range(ent, e):
                stop_hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
                tgt_hit = (h[j] >= tgt) if side > 0 else (l[j] <= tgt)
                if gaps == "prereg":
                    if j > ent:
                        if side * (o[j] - stop) <= 0:
                            xb, xp = j, o[j]
                            break
                        if side * (o[j] - tgt) >= 0:
                            xb, xp = j, o[j]
                            break
                    if stop_hit:
                        xb, xp = j, stop
                        break
                    if tgt_hit:
                        xb, xp = j, tgt
                        break
                else:                                         # plugin order: stop (with its gap) first, then target (with its gap)
                    if stop_hit:
                        xb, xp = j, (o[j] if side * (o[j] - stop) < 0 else stop)
                        break
                    if tgt_hit:
                        xb, xp = j, (o[j] if side * (o[j] - tgt) > 0 else tgt)
                        break
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
            break
    return out


def diff(P, B):
    """P = plugin trades [(entry, exit, side, entry_px, gross)], B = rule trades [(entry, exit, side, entry_px, exit_px, gross)]."""
    ka = {(t[0], t[2]): t for t in P}
    kb = {(t[0], t[2]): t for t in B}
    both = set(ka) & set(kb)
    exact = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][3] - kb[k][3]) < 1e-9 and abs(ka[k][4] - kb[k][5]) < 1e-9)
    return {"plugin_trades": len(P), "rule_trades": len(B), "same_entry_side": len(both), "exact_entry_exit_px_pts": exact,
            "only_plugin": len(set(ka) - set(kb)), "only_rule": len(set(kb) - set(ka)),
            "match_100pct": bool(len(P) == len(B) == exact)}


def short(f):
    keys = ("trades", "trades_per_yr", "net_usd", "per_yr_usd", "roc30", "dd5", "dd5_n", "one_episode", "max_dd", "dd_pct_peak",
            "sortino", "win_rate", "gross_win_rate", "gross_pts_total", "net_per_trade_pts")
    return {k: f[k] for k in keys}


def four_str(f):
    return ("ROC@30k %.2f | DD5 $%s | DD%% from peak %.1f%% | Sortino %.2f | trades %s (%.0f/yr) | $/yr %s%s"
            % (f["roc30"], format(round(f["dd5"]), ","), f["dd_pct_peak"], f["sortino"], format(f["trades"], ","),
               f["trades_per_yr"], format(round(f["per_yr_usd"]), ","), " | ONE EPISODE" if f["one_episode"] else ""))


def scored(B, idxn, days):
    ex, pts = [t[1] for t in B], [t[5] for t in B]
    return {nm: short(V.score(ex, pts, idxn, days, cst)) for nm, cst in
            (("house_0.533", V.COST), ("real_0.7825", V.REAL_COST), ("stress_1.033", V.STRESS_COST))}


def main():
    res = {"idea": "QL_VWAPREVERT_NQ", "run": "second run, plugin v2", "stage": "2 - compare + trace"}
    pin = V.lf_sha(V.PLUGIN)
    assert pin == V.PIN_FULL, pin
    res["plugin_lf_sha256"] = pin
    res["stage1_output_sha256"] = hashlib.sha256(open(OUT + "/ttm_verify.json", "rb").read()).hexdigest()
    assert res["stage1_output_sha256"] == "9c5084e4cf46d037243681431192239b70c14277191d00e01f72178a8bebe116"
    row = [x for x in V.list_masters() if x.get("filename") == V.MASTER]
    assert len(row) == 1
    A = V.load_master_arrays(row[0], date_from=V.D0, date_to=V.D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    res["master"] = {"file": V.MASTER, "registry_id": row[0].get("id"), "bars": int(len(c)), "fingerprint": A.get("fingerprint"),
                     "sessions": int(len(days))}

    # ---- arm A: plugin through the engine (as stage 1)
    m = types.ModuleType("ttm_ql_vwaprevert_v2_trace")
    m.__file__ = V.PLUGIN
    exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
    r = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    P = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]
    armA = scored([(t[0], t[1], t[2], t[3], None, t[4]) for t in P], idxn, days)
    res["arm_A"] = armA
    res["arm_A_four_numbers"] = {k: four_str(v) for k, v in armA.items()}

    # ---- 1. COMPARE: lab numbers file vs arm A house
    lab = json.load(open(LAB_NUMBERS, encoding="utf-8"))
    L = lab["numbers"]
    a = armA["house_0.533"]
    tol = [("trades", "trades", L["trades"], a["trades"], 0),
           ("net_usd", "net_usd", L["net_usd"], a["net_usd"], 1.0),
           ("roc_30k", "roc30", L["roc_30k"], a["roc30"], 0.005),
           ("dd5_usd", "dd5", L["dd5_usd"], a["dd5"], 1.0),
           ("max_dd_usd", "max_dd", L["max_dd_usd"], a["max_dd"], 1.0),
           ("dd_pct_peak", "dd_pct_peak", L["dd_pct_peak"], a["dd_pct_peak"], 0.01),
           ("sortino", "sortino", L["sortino"], a["sortino"], 0.001),
           ("win_rate", "win_rate", L["win_rate"], a["win_rate"] * (100.0 if L["win_rate"] > 1.0 else 1.0),
            0.05 if L["win_rate"] > 1.0 else 0.0005)]
    cmp_rows = []
    for lf, mf, lv, mv, t in tol:
        cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": lf, "lab": lv, "mine": mv,
                         "abs_diff": abs(float(lv) - float(mv)), "tol": t, "match": bool(abs(float(lv) - float(mv)) <= t)})
    cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": "one_episode", "lab": L["one_episode"], "mine": a["one_episode"],
                     "match": bool(L["one_episode"] == a["one_episode"])})
    cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": "dd5_n", "lab": L["dd5_n"], "mine": a["dd5_n"],
                     "match": bool(L["dd5_n"] == a["dd5_n"])})
    cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": "trades_per_year", "lab": L["trades_per_year"],
                     "mine": a["trades_per_yr"], "match": bool(abs(L["trades_per_year"] - a["trades_per_yr"]) <= 0.05)})
    cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": "net_pts_per_trade", "lab": L["net_pts_per_trade"],
                     "mine": a["net_per_trade_pts"], "match": bool(abs(L["net_pts_per_trade"] - a["net_per_trade_pts"]) <= 5e-5)})
    cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": "years", "lab": L["years"],
                     "mine": round((days[-1] - days[0]).days / 365.25, 4),
                     "match": bool(abs(L["years"] - (days[-1] - days[0]).days / 365.25) <= 0.0005)})
    cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": "sessions", "lab": L["sessions"], "mine": int(len(days)),
                     "match": bool(L["sessions"] == len(days))})
    for lf, mv in (("bars", int(len(c))), ("fingerprint", A.get("fingerprint")), ("master", V.MASTER), ("cost_pts", V.COST)):
        cmp_rows.append({"numbers_file": "numbers_pre_wf.json", "field": lf, "lab": lab[lf], "mine": mv,
                         "match": bool(lab[lf] == mv)})

    # the lab's trade list vs arm A trade for trade, then re-scored through TTM's yardstick
    T = pd.read_csv(LAB_TRADES)
    n_ok = 0
    worst_pts = 0.0
    if len(T) == len(P):
        for (_, rw), p in zip(T.iterrows(), P):
            g = rw["pnl_points_net"] + V.COST
            worst_pts = max(worst_pts, abs(g - p[4]))
            if (int(rw["entry_bar"]) == p[0] and int(rw["exit_bar"]) == p[1] and int(rw["side"]) == p[2]
                    and abs(rw["entry_price"] - p[3]) < 1e-9 and abs(g - p[4]) < 1e-5
                    and pd.Timestamp(rw["entry_time"]) == idx[p[0]] and pd.Timestamp(rw["exit_time"]) == idx[p[1]]):
                n_ok += 1
    labT = V.score(T["exit_bar"].to_numpy(int), (T["pnl_points_net"] + V.COST).to_numpy(float), idxn, days, V.COST)
    res["lab_trades_csv_vs_arm_A"] = {"lab_rows": int(len(T)), "arm_A_trades": len(P), "rows_identical": n_ok,
                                      "max_abs_gross_pts_diff": worst_pts, "identical_100pct": bool(n_ok == len(P) == len(T)),
                                      "lab_csv_rescored_house": short(labT)}
    for lf, mf, t in (("trades", "trades", 0), ("net_usd", "net_usd", 1.0), ("roc_30k", "roc30", 0.005), ("dd5_usd", "dd5", 1.0),
                      ("max_dd_usd", "max_dd", 1.0), ("dd_pct_peak", "dd_pct_peak", 0.01), ("sortino", "sortino", 0.001)):
        cmp_rows.append({"numbers_file": "pre_wf_trades.csv (re-scored by TTM)", "field": lf, "lab": labT[mf], "mine": a[mf],
                         "abs_diff": abs(labT[mf] - a[mf]), "tol": t, "match": bool(abs(labT[mf] - a[mf]) <= t)})
    cmp_rows.append({"numbers_file": "pre_wf_trades.csv", "field": "trade_for_trade (entry, exit, side, entry_px, pts, times)",
                     "lab": n_ok, "mine": len(P), "match": bool(n_ok == len(P) == len(T))})
    res["lab_vs_arm_A"] = cmp_rows
    res["lab_vs_arm_A_all_match"] = bool(all(x["match"] for x in cmp_rows))
    res["lab_promotion_line"] = lab.get("promotion")

    # ---- 2. TRACE: plugin way and literal reading
    pw = dict(warm=20, skip=25, gaps="plugin", atr0=True)
    lit = dict(warm=25, skip=None, gaps="prereg", atr0=False)
    PW = rule(o, h, l, c, day_id, **pw)
    LIT = rule(o, h, l, c, day_id, **lit)
    B1 = V.own_rule(o, h, l, c, day_id)                       # stage-1 arm B, verbatim
    res["plugin_way"] = {"switches": pw, "vs_plugin": diff(P, PW)}
    res["literal_equals_stage1_arm_B"] = bool(LIT == B1)
    res["literal"] = {"switches": lit, "vs_plugin": diff(P, LIT), "scored": scored(LIT, idxn, days)}
    variants = {
        "S1_warmup_k25_not_k20": dict(pw, warm=25),
        "S2_no_short_session_skip": dict(pw, skip=None),
        "S3_prereg_gap_order": dict(pw, gaps="prereg"),
        "S4_no_atr_le_0_skip": dict(pw, atr0=False),
    }
    res["slip_variants"] = {}
    for nm, sw in variants.items():
        Bv = rule(o, h, l, c, day_id, **sw)
        sc = scored(Bv, idxn, days)
        ka = {(t[0], t[2]) for t in P}
        kb = {(t[0], t[2]) for t in Bv}
        res["slip_variants"][nm] = {"switches": sw, "vs_plugin": diff(P, Bv), "scored": sc,
                                    "four_numbers": {k: four_str(v) for k, v in sc.items()},
                                    "gross_pts_only_plugin": float(sum(t[4] for t in P if (t[0], t[2]) in ka - kb)),
                                    "gross_pts_only_variant": float(sum(t[5] for t in Bv if (t[0], t[2]) in kb - ka))}
    # sensitivity, not a slip: the other reading of 'k >= 25' (counted inside the session)
    ALT = rule(o, h, l, c, day_id, warm=25, skip=None, gaps="prereg", atr0=False, warm_in_session=True)
    sc = scored(ALT, idxn, days)
    res["sensitivity_warmup_in_session_k25"] = {"vs_plugin": diff(P, ALT), "scored": sc,
                                                "four_numbers": {k: four_str(v) for k, v in sc.items()}}
    res["literal"]["four_numbers"] = {k: four_str(v) for k, v in res["literal"]["scored"].items()}

    # where the gap-order and ATR<=0 switches COULD act (on the plugin's own trades and on every evaluated bar)
    gap_bars = 0
    for (ent, xb, sd, ep, g) in P:
        k = ent - 1
        atr = (h[k - 19:k + 1] - l[k - 19:k + 1]).mean()
        stop, tgt = ep - sd * atr, ep + sd * 1.5 * atr
        for j in range(ent + 1, xb + 1):
            stop_hit = (l[j] <= stop) if sd > 0 else (h[j] >= stop)
            if sd * (o[j] - tgt) >= 0 and stop_hit:
                gap_bars += 1
    rng = h - l
    atr_all = pd.Series(rng).rolling(20).mean().to_numpy()
    res["switch_reach"] = {"bars_open_beyond_target_and_touching_stop_inside_plugin_trades": int(gap_bars),
                           "bars_with_atr20_le_0_in_window": int(np.nansum(atr_all[20:] <= 0))}

    # short sessions in the window (what the skip removes)
    sess_len = np.bincount(day_id)
    sess_start = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    shortd = [{"date": str(idxn[sess_start[d]].date()), "bars": int(sess_len[d]), "first": str(idxn[sess_start[d]].time()),
               "last": str(idxn[sess_start[d] + sess_len[d] - 1].time())} for d in range(len(sess_len)) if sess_len[d] < 25]
    res["sessions_under_25_bars"] = {"count": len(shortd), "list": shortd}
    res["session_length_counts"] = {str(k): int(v) for k, v in zip(*np.unique(sess_len, return_counts=True))}

    # ---- 3. LOOK-AHEAD: one-session slices [a-PAD, b): the plugin sees the same ATR history; the PAD-bar stub before the session is
    # its own fake session (it may trade; ignored - each trade is looked up by its entry bar). PAD = 60 so a slice cut right after the
    # entry bar still clears the plugin's n >= 50 guard.
    PAD = 60
    rs = np.random.default_rng(20261016)
    did = day_id
    la = {"slices": 0, "slice_reproduces": 0, "future_randomised_entry_same": 0, "stop_shock_level_eq_atr_k": 0,
          "target_shock_level_eq_atr_k": 0, "truncated_after_entry_still_trades": 0, "truncated_cases": 0,
          "signal_bar_in_session_lt_23": 0, "first_failures": []}
    for (ent, xb, sd, ep, g) in P:
        k = ent - 1
        d = int(did[ent])
        a0, b0 = int(sess_start[d]), int(sess_start[d] + sess_len[d])
        if a0 < PAD:
            continue                                       # first session of the window (global warm-up) - not sliced
        s0 = a0 - PAD
        sl = slice(s0, b0)
        oo, hh, ll, cc = o[sl].copy(), h[sl].copy(), l[sl].copy(), c[sl].copy()
        dd = np.r_[np.zeros(PAD, int), np.ones(b0 - a0, int)]
        kk, ee = k - s0, ent - s0
        la["slices"] += 1

        def run(o_, h_, l_, c_, d_):
            rr = m.run_backtest(o_, h_, l_, c_, None, d_, return_trades=True)
            return [t for t in (rr["trades"] if rr else []) if t[0] >= PAD]   # the target session's trade only
        t0 = run(oo, hh, ll, cc, dd)
        if t0 and t0[0][0] == ee and t0[0][1] == xb - s0 and t0[0][3] == sd and abs(t0[0][2] - g) < 1e-9:
            la["slice_reproduces"] += 1
        # (a) randomise every bar after k (keep o[k+1], the fill price); entry must not move
        o2, h2, l2, c2 = oo.copy(), hh.copy(), ll.copy(), cc.copy()
        nf = len(oo) - (kk + 1)
        base = rs.normal(ep, 50.0, nf)
        o2[kk + 1:] = base
        o2[ee] = ep
        hi = np.maximum(o2[kk + 1:], base) + rs.uniform(0, 40, nf)
        lo = np.minimum(o2[kk + 1:], base) - rs.uniform(0, 40, nf)
        h2[kk + 1:], l2[kk + 1:], c2[kk + 1:] = hi, lo, base
        t1 = run(o2, h2, l2, c2, dd)
        if t1 and t1[0][0] == ee and t1[0][3] == sd and t1[0][4] == ep:
            la["future_randomised_entry_same"] += 1
        elif len(la["first_failures"]) < 5:
            la["first_failures"].append(["random", str(idxn[ent])])
        atr_k = float((h[k - 19:k + 1] - l[k - 19:k + 1]).mean())
        # (b) stop shock on the entry bar: a 5000-pt adverse range; the implied stop distance must be ATR(k-19..k) x 1.0
        o3, h3, l3, c3 = oo.copy(), hh.copy(), ll.copy(), cc.copy()
        if sd > 0:
            h3[ee], l3[ee], c3[ee] = ep, ep - 5000.0, ep
        else:
            h3[ee], l3[ee], c3[ee] = ep + 5000.0, ep, ep
        t2 = run(o3, h3, l3, c3, dd)
        if t2 and t2[0][0] == ee and t2[0][1] == ee and abs(-t2[0][2] - atr_k) < 1e-9:
            la["stop_shock_level_eq_atr_k"] += 1
        elif len(la["first_failures"]) < 5:
            la["first_failures"].append(["stop", str(idxn[ent]), t2[0] if t2 else None, atr_k])
        # (c) target shock on the entry bar: a 5000-pt favourable range; implied target distance must be ATR(k-19..k) x 1.5
        o4, h4, l4, c4 = oo.copy(), hh.copy(), ll.copy(), cc.copy()
        if sd > 0:
            h4[ee], l4[ee], c4[ee] = ep + 5000.0, ep, ep
        else:
            h4[ee], l4[ee], c4[ee] = ep, ep - 5000.0, ep
        t3 = run(o4, h4, l4, c4, dd)
        if t3 and t3[0][0] == ee and t3[0][1] == ee and abs(t3[0][2] - 1.5 * atr_k) < 1e-9:
            la["target_shock_level_eq_atr_k"] += 1
        elif len(la["first_failures"]) < 5:
            la["first_failures"].append(["target", str(idxn[ent]), t3[0] if t3 else None, atr_k])
        # (d) truncation: the session ends right after the entry bar (only bars <= k+1 exist); does the plugin still enter?
        if k - a0 < 23:
            la["signal_bar_in_session_lt_23"] += 1
        tl = ee + 1
        if tl >= 50:                                       # always true with PAD = 60
            la["truncated_cases"] += 1
            t5 = run(oo[:tl], hh[:tl], ll[:tl], cc[:tl], dd[:tl])
            if t5 and t5[0][0] == ee and t5[0][3] == sd:
                la["truncated_after_entry_still_trades"] += 1
    res["look_ahead"] = la

    s = json.dumps(res, indent=1, default=float)
    data = (s + "\n").encode("utf-8")
    with open(os.path.join(OUT, "ttm_trace.json"), "wb") as fh:
        fh.write(data)
    print(s)
    print("output sha256", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
