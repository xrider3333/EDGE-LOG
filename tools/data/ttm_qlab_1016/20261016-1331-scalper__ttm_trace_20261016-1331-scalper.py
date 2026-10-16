"""TTM (house verifier) QL_NOISE2M_TREND stage 2 - COMPARE + TRACE. Written AFTER the stage-1 output sha 584c7291... was posted to
MANAGER (#1303); the lab's numbers_pre_wf.json, pre_wf_trades.csv, sandbox_pre_wf_out.json and the plugin code are read here.
1. arm A (house cost, from ttm_verify.json) vs the lab's numbers_pre_wf.json field by field; arm A's engine trades vs the lab's
   pre_wf_trades.csv and sandbox_pre_wf_out.json trade for trade.
2. TTM's OWN rule (stage-1 own_rule, generalised with one knob per reading choice) re-run (a) the literal/blind way - must equal
   stage-1 arm B exactly - and (b) the PLUGIN's way - must equal the engine's plugin trades 100% trade for trade. Each slip is
   then switched one at a time (plugin way -> literal) and cumulatively (plugin -> arm B), scored with the stage-1 booking.
3. look-ahead: perturb every bar from the entry bar on (keeping the entry open) and every bar after the exit bar, re-run the
   plugin per session, and require identical entries / exits.
4. how often the rule fires: qualifying signal bars per session before the one-per-session cap, first-signal session bar.
Writes only ttm_trace.json in this folder."""
import hashlib
import importlib.util
import json
import os
import types

import numpy as np
import pandas as pd

OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261016-1331-scalper"
spec = importlib.util.spec_from_file_location("V", OUT + "/ttm_verify_20261016-1331-scalper.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)          # sets AUGUR_TRIAL_CACHE=0 before importing augur_engine; main() is not run

LAB_NUM = V.IDEA + "/numbers_pre_wf.json"
LAB_CSV = V.IDEA + "/pre_wf_trades.csv"
LAB_SBX = V.IDEA + "/sandbox_pre_wf_out.json"
STAGE1 = OUT + "/ttm_verify.json"
STAGE1_SHA = "584c729146d9a7ed053c90bc9a9f03fc0b88658400a12fcc51b76a00f73eb06d"

LITERAL = dict(N=20, window="prior", reset=False, centre="prev_close", half=1.0, T=6, last_off=1, min_sess=None)
PLUGIN_WAY = dict(N=12, window="incl_k", reset=True, centre="median_close", half=0.5, T=7, last_off=2, min_sess="N+3")


def signals(o, h, l, c, day_id, N, window, reset, centre, half, last_off, min_sess, **_):
    """Vectorised: side[k] in {-1,0,1} for every bar k where TTM's rule (with these reading knobs) would enter at open[k+1]."""
    n = len(c)
    rng = pd.Series(h - l)
    cs = pd.Series(c)
    did = pd.Series(np.asarray(day_id))
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    sess_start = np.repeat(starts, ends - starts)
    sess_end = np.repeat(ends, ends - starts)
    krel = np.arange(n) - sess_start
    if reset:
        w = rng.groupby(did).transform(lambda s: s.rolling(N).median())
        mc = cs.groupby(did).transform(lambda s: s.rolling(N).median())
        if window == "prior":
            w = w.groupby(did).shift(1)
            mc = mc.groupby(did).shift(1)
    else:
        w = rng.rolling(N).median()
        mc = cs.rolling(N).median()
        if window == "prior":
            w, mc = w.shift(1), mc.shift(1)
    w, mc = w.to_numpy(), mc.to_numpy()
    if centre == "prev_close":
        ctr = np.r_[np.nan, c[:-1]]
        if reset:
            ctr = np.where(krel == 0, np.nan, ctr)
    elif centre == "median_close":
        ctr = mc
    elif centre == "day_open":
        ctr = o[sess_start]
    else:
        raise ValueError(centre)
    up, dn = ctr + half * w, ctr - half * w
    dopen = o[sess_start]
    ok = np.isfinite(w) & (w > 0) & np.isfinite(ctr)
    ok &= krel >= (N if reset else 0)                                   # reset: first signal at session bar N (plugin: bar 13)
    ok &= np.arange(n) <= sess_end - 1 - last_off                        # entry bar k+1 (and plugin: k+2) inside the session
    if min_sess is not None:
        ms = N + 3 if min_sess == "N+3" else int(min_sess)
        ok &= (sess_end - sess_start) > ms
    with np.errstate(invalid="ignore"):
        side = np.where(ok & (c > up) & (c > dopen), 1, np.where(ok & (c < dn) & (c < dopen), -1, 0))
    return side, w, starts, ends


def rule(o, h, l, c, day_id, N, window, reset, centre, half, T, last_off, min_sess, stop_mult=1.5):
    """TTM's own rule with reading knobs. T = bars held counting the entry bar (text: 6 = 12 min; plugin max_hold=6 -> 7)."""
    side, w, starts, ends = signals(o, h, l, c, day_id, N, window, reset, centre, half, last_off, min_sess)
    out = []
    nz = np.flatnonzero(side)
    pos = np.searchsorted(nz, starts)
    for s, e, p in zip(starts, ends, pos):
        if p >= len(nz) or nz[p] >= e:
            continue
        k = int(nz[p])
        sd = int(side[k])
        ent = k + 1
        ep = o[ent]
        stop = ep - sd * stop_mult * w[k]
        last = min(ent + T - 1, e - 1)
        xb, xp = last, c[last]
        for j in range(ent, last + 1):
            if j > ent and sd * (o[j] - stop) <= 0:                   # a bar that opens past the stop books its open
                xb, xp = j, o[j]
                break
            if (l[j] <= stop) if sd > 0 else (h[j] >= stop):
                xb, xp = j, stop
                break
        out.append((int(ent), int(xb), sd, float(ep), float(xp), float(sd * (xp - ep))))
    return out


def diff(X, Y):
    """X, Y: lists of (entry, exit, side, entry_px, exit_px, gross). Match by (entry, side)."""
    kx = {(t[0], t[2]): t for t in X}
    ky = {(t[0], t[2]): t for t in Y}
    both = set(kx) & set(ky)
    return {"n_x": len(X), "n_y": len(Y), "same_entry_and_side": len(both), "only_x": len(set(kx) - set(ky)),
            "only_y": len(set(ky) - set(kx)),
            "exact_same_exit_entrypx_pts": sum(1 for k in both if kx[k][1] == ky[k][1] and abs(kx[k][3] - ky[k][3]) < 1e-9
                                              and abs(kx[k][5] - ky[k][5]) < 1e-9)}


def four_str(s):
    return (f"ROC@30k {s['roc30']:.2f} | DD5 ${s['dd5']:,.0f}{' (ONE EPISODE)' if s['one_episode'] else ''} | DD% from peak "
            f"{s['dd_pct_peak']:.1f}% | Sortino {s['sortino']:.2f} | trades {s['trades']:,} ({s['trades_per_yr']:.0f}/yr) | "
            f"$/yr {s['per_yr_usd']:,.0f}")


def scored(T, idxn, days):
    r = V.score_all([t[1] for t in T], [t[5] for t in T], idxn, days)
    keep = ("trades", "trades_per_yr", "net_usd", "per_yr_usd", "roc30", "dd5", "one_episode", "max_dd", "dd_pct_peak",
            "sortino", "win_rate", "gross_per_trade_pts", "net_per_trade_usd")
    return {k: dict({kk: v[kk] for kk in keep}, four=four_str(v)) for k, v in r.items()}


def main():
    assert hashlib.sha256(open(STAGE1, "rb").read()).hexdigest() == STAGE1_SHA, "stage-1 output changed"
    assert V.lf_sha(V.PLUGIN) == V.PIN_FULL_PREREG, "plugin pin"
    S1 = json.load(open(STAGE1))
    row, A, idxn, days, o, h, l, c, day_id = V.load()
    res = {"stage1_json": STAGE1, "stage1_sha256": STAGE1_SHA, "plugin_lf_sha256": V.lf_sha(V.PLUGIN)}

    # ---- arm A: the plugin through the engine (same call as stage 1) ------------------------------------------------------
    m = types.ModuleType("ttm_ql_noise2m_trend_trace")
    m.__file__ = V.PLUGIN
    exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
    r = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    TA = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float("nan"), float(t[2])) for t in r["trades"]]
    sA = scored(TA, idxn, days)
    hA = S1["A_plugin"]["house_cost"]
    assert sA["house_cost"]["trades"] == hA["trades"] and abs(sA["house_cost"]["net_usd"] - hA["net_usd"]) < 1e-6

    # ---- 1. lab numbers vs arm A ------------------------------------------------------------------------------------------
    L = json.load(open(LAB_NUM))["numbers"]
    cmp = []
    for f_lab, f_me, tol, scale in [("trades", "trades", 0, 1), ("net_usd", "net_usd", 1.0, 1), ("roc_30k", "roc30", 0.005, 1),
                                    ("dd5_usd", "dd5", 1.0, 1), ("max_dd_usd", "max_dd", 1.0, 1),
                                    ("dd_pct_peak", "dd_pct_peak", 0.01, 1), ("sortino", "sortino", 0.001, 1),
                                    ("one_episode", "one_episode", None, 1), ("win_rate", "win_rate", 0.05, 100.0),
                                    ("trades_per_year", "trades_per_yr", 0.05, 1), ("years", "years", 0.0005, 1),
                                    ("net_usd_per_trade", "net_per_trade_usd", 0.005, 1)]:
        lab = L[f_lab]
        mine = (hA[f_me] if f_me != "years" else hA["years"]) * (scale if f_me == "win_rate" else 1)
        if tol is None:
            ok = (lab == mine)
        elif tol == 0:
            ok = (lab == mine)
        else:
            ok = abs(float(lab) - float(mine)) <= tol + 1e-12
        cmp.append({"numbers_file": LAB_NUM, "field": f_lab, "lab": lab, "mine": mine, "tol": tol, "match": bool(ok)})
    res["lab_vs_arm_a_house"] = cmp
    res["lab_vs_arm_a_all_match"] = all(x["match"] for x in cmp)
    res["lab_dd5_n"] = L.get("dd5_n")

    lab = pd.read_csv(LAB_CSV)
    sbx = json.load(open(LAB_SBX))["trades"]
    tl = list(zip(lab.entry_bar.astype(int), lab.exit_bar.astype(int), lab.side.astype(int), lab.entry_price.astype(float),
                  lab.pnl_points_net.astype(float)))
    ts = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in sbx]
    def tmatch(Lt):
        n_ok = sum(1 for a, b in zip(TA, Lt) if a[0] == b[0] and a[1] == b[1] and a[2] == b[2] and abs(a[3] - b[3]) < 1e-9
                   and abs((a[5] - V.HOUSE_COST) - b[4]) < 5e-4)
        return {"lab_trades": len(Lt), "arm_a_trades": len(TA), "exact_matches": n_ok}
    res["lab_trades_csv_vs_arm_a"] = tmatch(tl)
    res["lab_sandbox_trades_vs_arm_a"] = tmatch(ts)
    et = pd.to_datetime(lab.entry_time.str.slice(0, 19))
    res["lab_trades_csv_entry_time_check"] = int((et.to_numpy() == idxn[lab.entry_bar.to_numpy()].to_numpy()).sum())

    # ---- 2. own rule: literal (must = stage-1 arm B) and plugin way (must = engine A) --------------------------------------
    B0 = V.own_rule(o, h, l, c, day_id)                      # the stage-1 blind arm B, unchanged code
    BL = rule(o, h, l, c, day_id, **LITERAL)
    BP = rule(o, h, l, c, day_id, **PLUGIN_WAY)
    res["own_literal_vs_stage1_armB"] = diff(BL, B0)
    res["own_plugin_way_vs_engine_armA"] = diff(BP, TA)
    pw = res["own_plugin_way_vs_engine_armA"]
    res["b_plugin_way_matches_100pct"] = bool(pw["n_x"] == pw["n_y"] == pw["same_entry_and_side"] == pw["exact_same_exit_entrypx_pts"]
                                             == len(TA))
    lt = res["own_literal_vs_stage1_armB"]
    res["literal_matches_stage1_armB_100pct"] = bool(lt["n_x"] == lt["n_y"] == lt["same_entry_and_side"]
                                                     == lt["exact_same_exit_entrypx_pts"] == len(B0))
    res["armA_scored"] = sA
    res["armB_literal_scored"] = scored(BL, idxn, days)
    res["plugin_way_scored"] = scored(BP, idxn, days)

    # one slip at a time: plugin way with ONE knob put back to the literal / blind reading
    slips = {"S1_time_stop_T6_12min": {"T": 6},
             "S2_N20": {"N": 20},
             "S3_band_window_excludes_signal_bar": {"window": "prior"},
             "S4_no_session_reset_global_band": {"reset": False},
             "S5_centre_prev_close_edges_1w": {"centre": "prev_close", "half": 1.0},
             "S5b_centre_median_close_edges_1w": {"half": 1.0},
             "S5c_centre_day_open_edges_1w": {"centre": "day_open", "half": 1.0},
             "S6_guards_off_last_off1_no_min_session": {"last_off": 1, "min_sess": None}}
    one = {}
    for nm, kw in slips.items():
        T = rule(o, h, l, c, day_id, **dict(PLUGIN_WAY, **kw))
        d = diff(T, BP)
        one[nm] = {"knobs": kw, "trades_changed_vs_plugin": max(len(T), len(BP)) - d["exact_same_exit_entrypx_pts"],
                   "scored": scored(T, idxn, days)}
    res["slip_one_at_a_time"] = one
    # cumulative path plugin -> literal
    path, cur = {}, dict(PLUGIN_WAY)
    for nm, kw in [("1_T6", {"T": 6}), ("2_N20", {"N": 20}), ("3_prior_window", {"window": "prior"}),
                   ("4_no_reset", {"reset": False}), ("5_prev_close_1w", {"centre": "prev_close", "half": 1.0}),
                   ("6_guards_off", {"last_off": 1, "min_sess": None})]:
        cur.update(kw)
        T = rule(o, h, l, c, day_id, **cur)
        path[nm] = {"knobs": dict(cur), "house": scored(T, idxn, days)["house_cost"]}
        if nm == "6_guards_off":
            path[nm]["equals_stage1_armB"] = diff(T, B0)
    res["cumulative_plugin_to_literal"] = path

    # ---- 3. look-ahead perturbation on the plugin, session by session ----------------------------------------------------
    rg = np.random.default_rng(20261016)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(c)]
    by_entry = {t[0]: t for t in TA}
    bad_entry, bad_exit, checked = [], [], 0

    def pert(oo, hh, ll, cc, cut, keep_open):
        oo, hh, ll, cc = oo.copy(), hh.copy(), ll.copy(), cc.copy()
        nn = len(cc) - cut
        if nn <= 0:
            return oo, hh, ll, cc
        prev = cc[cut - 1]
        steps = np.round(rg.normal(0, 3, nn) * 4) / 4
        cn = prev + np.cumsum(steps)
        on = np.r_[prev, cn[:-1]]
        if keep_open:
            on[0] = oo[cut]
        hn = np.maximum(on, cn) + np.abs(np.round(rg.normal(0, 2, nn) * 4) / 4)
        ln = np.minimum(on, cn) - np.abs(np.round(rg.normal(0, 2, nn) * 4) / 4)
        oo[cut:], hh[cut:], ll[cut:], cc[cut:] = on, hn, ln, cn
        return oo, hh, ll, cc

    prev_start = np.r_[starts[0], starts[:-1]]
    for s, e, ps in zip(starts, ends, prev_start):
        tr = [t for k, t in by_entry.items() if s <= k < e]
        if not tr:
            continue
        t = tr[0]
        # the plugin returns None on < 50 bars, so each session is run with the PREVIOUS session prepended (the plugin's band
        # resets each session, so the prepended session cannot change this session's trade); only this session's bars are perturbed
        sl = slice(ps, e)
        so, sh, sl_, sc, sd = o[sl], h[sl], l[sl], c[sl], np.asarray(day_id)[sl]
        ent, xb, off = t[0] - ps, t[1] - ps, s - ps
        checked += 1

        def pick(rr):
            q = [x for x in (rr["trades"] if rr else []) if x[0] >= off]
            return q[0] if q else None
        po, ph, pl, pc = pert(so, sh, sl_, sc, ent, keep_open=True)          # every bar from the entry bar on, entry open kept
        q = pick(m.run_backtest(po, ph, pl, pc, None, sd, return_trades=True))
        if q is None or q[0] != ent or q[3] != t[2] or abs(q[4] - t[3]) > 1e-9:
            bad_entry.append(str(idxn[t[0]]))
        po, ph, pl, pc = pert(so, sh, sl_, sc, xb + 1, keep_open=False)      # every bar after the exit bar
        q = pick(m.run_backtest(po, ph, pl, pc, None, sd, return_trades=True))
        if q is None or q[0] != ent or q[1] != xb or abs(q[2] - t[5]) > 1e-9:
            bad_exit.append(str(idxn[t[0]]))
    res["lookahead_perturbation"] = {"sessions_checked": checked, "entry_changed_when_bars_from_entry_on_perturbed": len(bad_entry),
                                     "exit_changed_when_bars_after_exit_perturbed": len(bad_exit),
                                     "first_bad_entry": bad_entry[:5], "first_bad_exit": bad_exit[:5]}
    sl_len = ends - starts
    res["session_length_guard"] = {"sessions": int(len(starts)), "sessions_le_15_bars": int((sl_len <= 15).sum()),
                                   "min_bars": int(sl_len.min()), "max_bars": int(sl_len.max()),
                                   "sessions_lt_195_bars": int((sl_len < 195).sum())}

    # ---- 4. how often the rule fires (before the one-per-session cap) ----------------------------------------------------
    fire = {}
    for nm, kw in (("literal_armB", LITERAL), ("plugin_way", PLUGIN_WAY)):
        side, w, st, en = signals(o, h, l, c, day_id, **kw)
        nz = np.flatnonzero(side)
        sess_of = np.searchsorted(st, nz, side="right") - 1
        per = np.bincount(sess_of, minlength=len(st))
        first_rel = []
        for s_i in range(len(st)):
            p = np.searchsorted(nz, st[s_i])
            if p < len(nz) and nz[p] < en[s_i]:
                first_rel.append(int(nz[p] - st[s_i]))
        first_rel = np.array(first_rel)
        earliest = PLUGIN_WAY["N"] if kw["reset"] else (1 if kw["centre"] == "prev_close" else 0)
        fire[nm] = {"qualifying_signal_bars": int(len(nz)), "per_year": float(len(nz) / hA["years"]),
                    "share_of_eligible_bars": float(len(nz) / max(1, int(((np.arange(len(c)) - np.repeat(st, en - st)) >= earliest).sum()))),
                    "sessions_with_signal": int((per > 0).sum()), "sessions": int(len(st)),
                    "signals_per_session_median": float(np.median(per)), "signals_per_session_mean": float(per.mean()),
                    "first_signal_session_bar_median": float(np.median(first_rel)),
                    "first_signal_at_earliest_eligible_bar": int((first_rel == earliest).sum()),
                    "earliest_eligible_session_bar": int(earliest),
                    "first_signal_within_3_bars_of_earliest": int((first_rel <= earliest + 2).sum())}
    res["how_often_rule_fires"] = fire

    s = json.dumps(res, indent=1, default=float) + "\n"
    with open(OUT + "/ttm_trace.json", "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print(s)
    print("trace output", OUT + "/ttm_trace.json", "sha256", hashlib.sha256(open(OUT + "/ttm_trace.json", "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
