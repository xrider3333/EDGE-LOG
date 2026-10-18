"""TTM (house verifier): STAGE 2 - COMPARE + TRACE for Qwen Lab idea QL_RANGECOMP_NQ (20261017-1502-own).
Stage 1 output (ttm_verify.json, sha256 82a9f3d1...48d5) was posted to MANAGER before this file opened the lab's numbers.
Does:
 1. arm A (house cost) vs the lab's numbers_pre_wf.json, field by field, with the stated tolerances; plus the lab's own
    gross/trade, cost, net/trade, gross/cost ratio, profit factor, trades/yr re-derived.
 2. trade-for-trade: lab pre_wf_trades.csv vs the plugin re-run through the engine (arm A) vs TTM's own rule (arm B, the
    stage-1 own_rule imported unchanged) vs B run 'the plugin's way' (the plugin's two latent departures switched on:
    sessions with <= warmup+2 bars skipped, no 77-bar time stop) - b_plugin_way_matches_100pct.
 3. look-ahead: for every session the plugin trades, scramble high/low/close of the fill bar and every later bar (and the open
    of every bar after the fill bar) and re-run the plugin; the entry bar / side / entry price must not move. Plus a
    stop-level check (every stop exit books entry -/+ stop_frac * range of bars <= signal bar).
 4. trade-rate note (sessions traded / sessions).
Writes only into C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1502-own/."""
import hashlib
import importlib.util
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1502-own"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1502-own"
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402

spec = importlib.util.spec_from_file_location("ttm_s1", os.path.join(OUT, "ttm_verify_20261017-1502-own.py"))
S1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S1)
PLUGIN, MASTER, D0, D1 = S1.PLUGIN, S1.MASTER, S1.D0, S1.D1
COST, MULT, REAL_COST, STRESS_COST = S1.COST, S1.MULT, S1.REAL_COST, S1.STRESS_COST


def own_rule_plugin_way(o, h, l, c, day_id, warmup_bars, entry_frac, stop_frac):
    """TTM's own rule with the plugin's two latent departures switched on: skip a session with <= warmup+2 bars; no time stop
    (session-end exit only). Otherwise the stage-1 own_rule line for line."""
    n = len(c)
    out = []
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    for s, e in zip(starts, ends):
        if e - s <= warmup_bars + 2:          # plugin: `if b - a <= wb + 2: continue`
            continue
        rh = np.maximum.accumulate(h[s:e])
        rl = np.minimum.accumulate(l[s:e])
        o0 = o[s]
        for kk in range(warmup_bars, e - s - 1):
            rng = rh[kk] - rl[kk]
            if rng <= 0:
                continue
            k = s + kk
            if c[k] >= rh[kk] - entry_frac * rng and c[k] > o0:
                side = 1
            elif c[k] <= rl[kk] + entry_frac * rng and c[k] < o0:
                side = -1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * stop_frac * rng
            last = e - 1                        # plugin: no time stop, session end only
            xb, xp, how = last, c[last], "session_end"
            for j in range(ent, last + 1):
                if j > ent and side * (o[j] - stop) <= 0:
                    xb, xp, how = j, o[j], "stop_gap_open"
                    break
                if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                    xb, xp, how = j, stop, "stop"
                    break
            out.append((ent, xb, side, float(ep), float(xp), float(side * (xp - ep)), how, float(stop), int(k)))
            break
    return out


def cmp_lists(X, Y, name_x, name_y):
    """X, Y: lists of (entry_bar, exit_bar, side, entry_px, gross_pts)."""
    kx = {(t[0], t[2]): t for t in X}
    ky = {(t[0], t[2]): t for t in Y}
    both = sorted(set(kx) & set(ky))
    exact = [k for k in both if kx[k][1] == ky[k][1] and abs(kx[k][3] - ky[k][3]) < 1e-9 and abs(kx[k][4] - ky[k][4]) < 1e-6]
    return {"pair": f"{name_x} vs {name_y}", f"{name_x}_trades": len(X), f"{name_y}_trades": len(Y),
            "same_entry_and_side": len(both), "exact_same_exit_px_pts": len(exact),
            f"only_{name_x}": len(set(kx) - set(ky)), f"only_{name_y}": len(set(ky) - set(kx)),
            "first_diffs": [[k[0], k[1], list(kx[k][1:]), list(ky[k][1:])] for k in both if k not in set(exact)][:5],
            "match_100pct": bool(len(exact) == len(X) == len(Y))}


def main():
    res = {"idea": "QL_RANGECOMP_NQ", "stage": "2 - COMPARE + TRACE (lab numbers opened after the stage-1 sha was posted)"}
    s1_path = os.path.join(OUT, "ttm_verify.json")
    res["stage1_json_sha256"] = hashlib.sha256(open(s1_path, "rb").read()).hexdigest()
    assert res["stage1_json_sha256"] == "82a9f3d1c8c41364764011c4abd8580a096881cd3f676ce8d9c2b18c6be948d5"
    S1J = json.load(open(s1_path))
    AH, AR = S1J["A_plugin"]["house_cost"], S1J["A_plugin"]["real_cost"]
    assert S1.lf_sha(PLUGIN) == S1.PIN_FULL_PREREG

    # ---------------- 1. lab numbers vs arm A (house) ----------------
    LAB = json.load(open(os.path.join(IDEA, "numbers_pre_wf.json")))
    N = LAB["numbers"]
    lab_wr = N["win_rate"] / 100.0 if N["win_rate"] > 1.0 else N["win_rate"]
    rows = [("trades", N["trades"], AH["trades"], 0), ("net_usd", N["net_usd"], AH["net_usd"], 1.0),
            ("roc_30k", N["roc_30k"], AH["roc30"], 0.005), ("dd5_usd", N["dd5_usd"], AH["dd5"], 1.0),
            ("max_dd_usd", N["max_dd_usd"], AH["max_dd"], 1.0), ("dd_pct_peak", N["dd_pct_peak"], AH["dd_pct_peak"], 0.01),
            ("sortino", N["sortino"], AH["sortino"], 0.001), ("one_episode", N["one_episode"], AH["one_episode"], None),
            ("win_rate (lab % -> frac)", lab_wr, AH["win_rate"], 0.0005),
            ("cost_pts", N["cost_pts"], COST, 1e-9), ("gross_pts_per_trade", N["gross_pts_per_trade"], AH["gross_pts_per_trade"], 0.0001),
            ("net_pts_per_trade", N["net_pts_per_trade"], AH["gross_pts_per_trade"] - COST, 0.0001),
            ("net_usd_per_trade", N["net_usd_per_trade"], AH["net_usd_per_trade"], 0.01),
            ("gross_cost_ratio", N["gross_cost_ratio"], AH["gross_pts_per_trade"] / COST, 0.005),
            ("trades_per_year", N["trades_per_year"], AH["trades_per_yr"], 0.1),
            ("years", N["years"], AH["years"], 0.001), ("sessions", N["sessions"], S1J["sessions"], 0),
            ("mult", N["mult"], MULT, 0), ("bars", LAB["bars"], S1J["bars"], 0),
            ("fingerprint", LAB["fingerprint"], S1J["data_fingerprint"], None)]
    cmp_rows = []
    for f, lab, mine, tol in rows:
        ok = (lab == mine) if tol is None else (abs(float(lab) - float(mine)) <= tol + 1e-12)
        cmp_rows.append({"field": f, "lab": lab, "mine": mine, "tol": tol, "match": bool(ok)})
    res["lab_vs_arm_a_house"] = cmp_rows
    res["all_core_fields_match"] = all(r["match"] for r in cmp_rows)

    # ---------------- 2. trade for trade ----------------
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1
    A = load_master_arrays(row[0], date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(c)]
    slen = ends - starts
    kd, _ = S1.knob_defaults(PLUGIN)
    wb, ef, sf = int(kd["warmup_bars"]), float(kd["entry_frac"]), float(kd["stop_frac"])
    res["session_lengths"] = {str(int(k)): int(v) for k, v in pd.Series(slen).value_counts().sort_index().items()}
    res["sessions_le_warmup_plus_2_bars"] = int((slen <= wb + 2).sum())

    m = types.ModuleType("ttm_ql_rangecomp_s2")
    m.__file__ = PLUGIN
    exec(compile(open(PLUGIN, encoding="utf-8").read(), PLUGIN, "exec"), m.__dict__)
    r = run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    TA = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(t[2])) for t in r["trades"]]

    B = S1.own_rule(o, h, l, c, day_id, wb, ef, sf)
    TB = [(t[0], t[1], t[2], t[3], t[5]) for t in B]
    BP = own_rule_plugin_way(o, h, l, c, day_id, wb, ef, sf)
    TBP = [(t[0], t[1], t[2], t[3], t[5]) for t in BP]

    csv = pd.read_csv(os.path.join(IDEA, "pre_wf_trades.csv"))
    TL = [(int(x.entry_bar), int(x.exit_bar), int(x.side), float(x.entry_price), float(x.pnl_points_net) + COST)
          for x in csv.itertuples()]
    # lab timestamps agree with the bar indices
    et = pd.to_datetime(csv["entry_time"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    xt = pd.to_datetime(csv["exit_time"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    res["lab_csv_times_match_bar_index"] = {
        "entry": int((et.values == idxn[csv["entry_bar"].to_numpy()].values).sum()),
        "exit": int((xt.values == idxn[csv["exit_bar"].to_numpy()].values).sum()), "rows": int(len(csv))}

    res["trade_for_trade"] = [cmp_lists(TL, TA, "labcsv", "A_plugin"), cmp_lists(TA, TB, "A_plugin", "B_own"),
                              cmp_lists(TA, TBP, "A_plugin", "B_plugin_way"), cmp_lists(TB, TBP, "B_own", "B_plugin_way")]
    res["b_plugin_way_matches_100pct"] = bool(res["trade_for_trade"][2]["match_100pct"])
    res["lab_csv_matches_plugin_100pct"] = bool(res["trade_for_trade"][0]["match_100pct"])
    # lab CSV scored by TTM's booking (net pts in the file, so cost 0 here)
    res["lab_csv_scored_by_ttm_house"] = S1.score([t[1] for t in TL], [t[4] - COST for t in TL], idxn, days, 0.0)

    # ---------------- 3. look-ahead ----------------
    # 3a stop level: every B stop exit booked entry -/+ sf * range(bars <= signal bar k); A == B on exit px, so the plugin too
    sess_of = np.repeat(np.arange(len(starts)), slen)
    bad_stop = 0
    for t in BP:
        ent, xb, side, ep, xp, pts, how, stop, k = t
        s = starts[sess_of[k]]
        rng_k = h[s:k + 1].max() - l[s:k + 1].min()
        if abs(stop - (ep - side * sf * rng_k)) > 1e-9:
            bad_stop += 1
        if how == "stop" and abs(xp - stop) > 1e-9:
            bad_stop += 1
    res["stop_level_from_bars_le_signal_bar"] = {"checked": len(BP), "bad": bad_stop}
    # 3b scramble the fill bar's h/l/c and every later bar (o too after the fill bar); entry must not move
    rng = np.random.default_rng(20261018)
    moved, checked, created = 0, 0, 0
    traded_sess = {int(sess_of[t[0]]): t for t in TA}
    for si in range(len(starts)):
        lo_s = si - 1 if si > 0 else si          # include a neighbour session so the slice has >= 50 bars
        hi_s = si if si > 0 else si + 1
        a0, b0 = starts[lo_s], ends[hi_s]
        oo, hh, ll, cc = o[a0:b0].copy(), h[a0:b0].copy(), l[a0:b0].copy(), c[a0:b0].copy()
        did = day_id[a0:b0]
        s, e = starts[si] - a0, ends[si] - a0
        if si in traded_sess:
            ent = traded_sess[si][0] - a0
            cut = ent                              # fill bar: its open is known at the fill; h/l/c are not
        else:
            continue
        span = max(1.0, float(hh[s:e].max() - ll[s:e].min()))
        for trial in range(3):
            o2, h2, l2, c2 = oo.copy(), hh.copy(), ll.copy(), cc.copy()
            nn = e - cut
            mid = cc[cut - 1] + rng.normal(0, span, nn)
            o2[cut + 1:e] = mid[1:] + rng.normal(0, span * 0.1, nn - 1)
            c2[cut:e] = mid + rng.normal(0, span * 0.1, nn)
            h2[cut:e] = np.maximum.reduce([o2[cut:e], c2[cut:e]]) + np.abs(rng.normal(0, span * 0.3, nn))
            l2[cut:e] = np.minimum.reduce([o2[cut:e], c2[cut:e]]) - np.abs(rng.normal(0, span * 0.3, nn))
            rr = m.run_backtest(o2, h2, l2, c2, day_id=did, warmup_bars=wb, entry_frac=ef, stop_frac=sf, return_trades=True)
            tt = [t for t in (rr or {}).get("trades", []) if s <= t[0] < e]
            checked += 1
            if len(tt) != 1 or tt[0][0] != ent or tt[0][3] != traded_sess[si][2] or abs(tt[0][4] - traded_sess[si][3]) > 1e-9:
                moved += 1
    res["lookahead_scramble"] = {"sessions_traded": len(traded_sess), "trials": checked, "entry_moved": moved,
                                 "what": "fill bar h/l/c + all later bars (o after the fill bar) scrambled; entry bar, side "
                                         "and entry price re-checked"}
    res["trade_rate"] = {"sessions": int(len(starts)), "sessions_traded": len(traded_sess),
                         "share": len(traded_sess) / len(starts), "stated_prior_per_yr": 120.0,
                         "counted_per_yr": AH["trades_per_yr"]}

    # ---------------- 5. four numbers ----------------
    def fstr(f):
        return (f"ROC@30k {f['roc30']:.2f} | DD5 ${f['dd5']:,.0f} | DD% from peak {f['dd_pct_peak']:.1f}% | Sortino "
                f"{f['sortino']:.2f} | trades {f['trades']:,} ({f['trades_per_yr']:.0f}/yr) | $/yr {f['per_yr_usd']:,.0f} | "
                f"one_episode {f['one_episode']}")
    res["four_numbers"] = {"house": fstr(AH), "real": fstr(AR), "stress": fstr(S1J["A_plugin"]["stress_cost"])}
    res["promotion"] = {"gross_pts_per_trade": AH["gross_pts_per_trade"], "house_cost_pts": COST, "real_cost_pts": REAL_COST,
                        "gross_ge_house_cost": bool(AH["gross_pts_per_trade"] >= COST),
                        "gross_ge_real_cost": bool(AH["gross_pts_per_trade"] >= REAL_COST),
                        "roc_house_gt_0": bool(AH["roc30"] > 0), "not_one_episode": bool(not AH["one_episode"]),
                        "promotes_new_bar": bool(AH["gross_pts_per_trade"] >= COST and AH["roc30"] > 0 and not AH["one_episode"]),
                        "old_bar_roc_ge_15_not_one_episode": bool(AH["roc30"] >= 15 and not AH["one_episode"]),
                        "lab_says": LAB.get("promotion"), "lab_promoted": LAB.get("promoted")}
    s = json.dumps(res, indent=1, default=float)
    b = (s + "\n").encode("utf-8")
    with open(os.path.join(OUT, "ttm_stage2_compare_trace.json"), "wb") as fh:
        fh.write(b)
    print(s)
    print("output sha256", hashlib.sha256(b).hexdigest())


if __name__ == "__main__":
    main()
