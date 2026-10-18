"""TTM QL_REVERSAL_NQ (20261017-1809-own) stage 2 - COMPARE + TRACE. Written AFTER the stage-1 output
(ttm_verify.json, sha256 d6741e395732...) was posted to MANAGER (#1472); the lab's numbers_pre_wf.json / pre_wf_trades.csv and
the plugin code are read only now.
 1. arm A (plugin through the engine) vs the lab's numbers_pre_wf.json field by field, and vs pre_wf_trades.csv trade by trade.
 2. TTM's own rule (frozen arm B, cd271a43eb0d...) re-run 'the plugin's way': each place the plugin's code departs from the
    prereg Mechanism text is a toggle (P1 trailing-stats warm-up gate, P2 short-session skip, P3 ATR<=0 skip, P4 ATR fallback
    inside session 0); all on must equal the plugin 100% trade for trade; each toggle alone shows what it costs.
 3. look-ahead: per trade, the entry bar's high/low/close and every later bar of the session are overwritten (open of the fill
    bar kept) so the stop is forced to fill at a touch on the next bar; the entry bar, side, entry price must not move, and the
    forced exit price must equal the stop TTM computes from bars <= the signal bar - 1 only.
 4. diagnostic only (NOT the Mechanism, chosen after results): two readings of the Hypothesis's 'beyond the trailing 20-session
    median burst range' filter and the Hypothesis's '10-bar burst'.
Writes only ttm_trace.json into the same folder."""
import hashlib
import importlib.util
import json
import os
import types

import numpy as np
import pandas as pd

OUT = "C:/EdgeLog/_anatomy_cache/ttm_qlab/20261017-1809-own"
IDEA = "C:/EdgeLog/qwen_lab/ideas/20261017-1809-own"
spec = importlib.util.spec_from_file_location("ttm_v", os.path.join(OUT, "ttm_verify_20261017-1809-own.py"))
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)              # sets AUGUR_TRIAL_CACHE=0 before importing augur_engine
from augur_engine.drawdowns import dd5   # noqa: E402

assert V.lf_sha(V.PLUGIN) == V.PIN_PREREG
assert V.lf_sha(V.ARMB) == V.ARMB_FROZEN
spec = importlib.util.spec_from_file_location("ttm_armb", V.ARMB)
ARMB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ARMB)


def own_rule_pluginway(o, h, l, c, day_id, stretch_k=1.5, warmup_bars=12, atr_bars=20, stop_frac=1.5, trail_sessions=20,
                       p1_trail_gate=True, p2_short_skip=True, p3_atr0_skip=True, p4_atr_fallback=True,
                       hyp=None, need_trail_full=False):
    """TTM's frozen rule (R1..R9) with the plugin's departures as toggles. All toggles off = frozen arm B exactly."""
    n = len(c)
    rng = h - l
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    wb, ab, ts = warmup_bars, atr_bars, trail_sessions
    # per-session stats exactly as the prereg 'stores' them: session high-low range and a session ATR (the plugin's
    # session ATR = mean range of the session's last atr_bars bars; a session with < wb+2 bars stores 0, 0)
    srange, satr = [], []
    for s, e in zip(starts, ends):
        if e - s < wb + 2:
            srange.append(0.0); satr.append(0.0); continue
        srange.append(float(h[s:e].max() - l[s:e].min()))
        satr.append(float(rng[e - ab:e].mean() if e - s >= ab else rng[s:e].mean()))
    out = []
    for si, (s, e) in enumerate(zip(starts, ends)):
        if p2_short_skip and e - s <= wb + 2:
            continue
        med_range = None
        if p1_trail_gate or hyp or need_trail_full:
            lo = max(0, si - ts)
            if p1_trail_gate:
                if si < 1 or si - lo < 2:
                    continue
            if need_trail_full and si - lo < ts:
                continue
            if si - lo >= 1:
                med_range = float(np.median(srange[lo:si])); med_atr = float(np.median(satr[lo:si]))
                if p1_trail_gate and (med_range <= 0 or med_atr <= 0):
                    continue
        o0 = o[s]
        for k in range(s + wb, e - 1):
            if k - ab < 0:
                if not p4_atr_fallback:
                    continue
                atr = rng[s:k].mean()
            else:
                atr = rng[k - ab:k].mean()
            if p3_atr0_skip and atr <= 0:
                continue
            b_hi = h[k - wb:k].max()
            b_lo = l[k - wb:k].min()
            if c[k] < b_lo - stretch_k * atr and c[k] < o0:
                side = 1
            elif c[k] > b_hi + stretch_k * atr and c[k] > o0:
                side = -1
            else:
                continue
            if hyp is not None:
                if med_range is None:
                    continue
                if hyp == "move_gt_medrange":      # the burst move incl. close[k] beyond the median prior-session range
                    mv = (b_hi - c[k]) if side > 0 else (c[k] - b_lo)
                elif hyp == "window_gt_medrange":  # the 12-bar window's own range beyond the median prior-session range
                    mv = b_hi - b_lo
                if not mv > med_range:
                    continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * stop_frac * atr
            xb, xp = e - 1, c[e - 1]
            for j in range(ent, e):
                if j > ent and side * (o[j] - stop) <= 0:
                    xb, xp = j, o[j]; break
                if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                    xb, xp = j, stop; break
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep)), float(stop)))
            break
    return out


def diff(Ta, B):
    ka = {(t[0], t[2]): t for t in Ta}
    kb = {(t[0], t[2]): t for t in B}
    both = set(ka) & set(kb)
    ex = sum(1 for k in both if ka[k][1] == kb[k][1] and abs(ka[k][5] - kb[k][5]) < 1e-6 and abs(ka[k][3] - kb[k][3]) < 1e-9)
    return {"plugin": len(Ta), "own": len(B), "same_entry_side": len(both), "only_plugin": len(set(ka) - set(kb)),
            "only_own": len(set(kb) - set(ka)), "exact": ex, "pct_exact_of_plugin": 100.0 * ex / max(1, len(Ta)),
            "match_100pct": ex == len(Ta) == len(B), "sum_abs_pts_diff": float(sum(abs(ka[k][5] - kb[k][5]) for k in both))}


def fmt4(f):
    oe = f["one_episode"]
    return (f"ROC@30k {f['roc30']:.2f} | DD5 ${f['dd5']:,.0f} (one_episode {oe}) | DD% from peak {f['dd_pct_peak']:.2f}% | "
            f"Sortino {f['sortino']:.2f} | trades {f['trades']:,} ({f['trades_per_yr']:.1f}/yr) | $/yr {f['per_yr_usd']:,.0f} | "
            f"gross {f['gross_pts_per_trade']:.4f} pt/trade vs cost {f['cost_pts']:.4f} pt | win {100 * f['win_rate']:.2f}%")


def main():
    row = [x for x in V.list_masters() if x.get("filename") == V.MASTER]
    assert len(row) == 1
    A = V.load_master_arrays(row[0], date_from=V.D0, date_to=V.D1)
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    days = pd.DatetimeIndex(sorted(set(idxn.normalize())))
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day_id = np.asarray(A["day_id"])
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], len(c)]
    sess_of = np.repeat(np.arange(len(starts)), ends - starts)
    in_sess = np.arange(len(c)) - starts[sess_of]
    res = {"fingerprint": str(A.get("fingerprint")), "bars": len(c), "sessions": len(days),
           "session_len_counts": {str(k): int(v) for k, v in pd.Series(ends - starts).value_counts().sort_index().items()}}

    # plugin through the engine (arm A) and called directly
    m = types.ModuleType("ttm_trace_ql_reversal")
    m.__file__ = V.PLUGIN
    exec(compile(open(V.PLUGIN, encoding="utf-8").read(), V.PLUGIN, "exec"), m.__dict__)
    r = V.run_backtest(m, instrument="NQ", arrays=A, params=None, cost_pts=0.0, return_trades=True)
    Ta = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float("nan"), float(t[2])) for t in r["trades"]]
    rd = m.run_backtest(o, h, l, c, day_id=day_id, index=A["index"], return_trades=True)
    Td = [(int(t[0]), int(t[1]), int(t[3]), float(t[4]), float("nan"), float(t[2])) for t in rd["trades"]]
    res["engine_vs_direct_plugin"] = diff(Ta, Td)
    houseA = V.score([t[1] for t in Ta], [t[5] for t in Ta], idxn, days, V.COST)
    realA = V.score([t[1] for t in Ta], [t[5] for t in Ta], idxn, days, V.REAL_COST)
    stressA = V.score([t[1] for t in Ta], [t[5] for t in Ta], idxn, days, V.STRESS_COST)

    # 1. lab numbers file, field by field
    lab = json.load(open(os.path.join(IDEA, "numbers_pre_wf.json"), encoding="utf-8"))
    L = lab["numbers"]
    usd = (np.array([t[5] for t in Ta]) - V.COST) * V.MULT
    daily = pd.Series(usd, index=idxn[[t[1] for t in Ta]].normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
    d5 = dd5(daily)
    mine = {"trades": houseA["trades"], "net_usd": houseA["net_usd"], "roc_30k": houseA["roc30"], "dd5_usd": houseA["dd5"],
            "max_dd_usd": houseA["max_dd"], "dd_pct_peak": houseA["dd_pct_peak"], "sortino": houseA["sortino"],
            "one_episode": houseA["one_episode"], "win_rate": 100.0 * houseA["win_rate"],
            "trades_per_year": houseA["trades_per_yr"], "years": houseA["years"], "sessions": len(days),
            "net_pts_per_trade": houseA["net_pts_per_trade"], "net_usd_per_trade": float(usd.mean()),
            "gross_pts_per_trade": houseA["gross_pts_per_trade"], "cost_pts": V.COST, "mult": V.MULT,
            "gross_cost_ratio": houseA["gross_over_cost"], "dd5_n": int(d5["n"]),
            "profit_factor": float(usd[usd > 0].sum() / -usd[usd < 0].sum())}
    tol = {"trades": 0, "net_usd": 1.0, "roc_30k": 0.005, "dd5_usd": 1.0, "max_dd_usd": 1.0, "dd_pct_peak": 0.01,
           "sortino": 0.001, "one_episode": None, "win_rate": 0.05, "trades_per_year": 0.05, "years": 0.001, "sessions": 0,
           "net_pts_per_trade": 0.0001, "net_usd_per_trade": 0.01, "gross_pts_per_trade": 0.0001, "cost_pts": 1e-9,
           "mult": 1e-9, "gross_cost_ratio": 0.001, "dd5_n": 0, "profit_factor": 0.0001}
    cmp_rows = []
    for k, t in tol.items():
        lv, mv = L.get(k), mine[k]
        ok = (lv == mv) if t is None else (lv is not None and abs(float(lv) - float(mv)) <= t + 1e-12)
        cmp_rows.append({"field": k, "lab": lv, "mine": mv, "tol": t, "match": bool(ok)})
    extra = {"bars": (lab.get("bars"), len(c)), "fingerprint": (lab.get("fingerprint"), str(A.get("fingerprint"))),
             "window": (lab.get("window"), f"{days[0].date()}..{days[-1].date()}"), "master": (lab.get("master"), V.MASTER),
             "params": (lab.get("params"), {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}),
             "first_signal_bar_check.earliest_session_bar": (lab["first_signal_bar_check"]["earliest_session_bar"],
                                                              int(min(in_sess[t[0]] for t in Ta))),
             "promoted": (lab.get("promoted"), False)}
    for k, (lv, mv) in extra.items():
        cmp_rows.append({"field": k, "lab": lv, "mine": mv, "tol": "equal", "match": lv == mv})
    res["lab_numbers_vs_armA_house"] = cmp_rows
    res["lab_numbers_all_match"] = all(x["match"] for x in cmp_rows)

    # 1b. lab trades csv, trade by trade
    tc = pd.read_csv(os.path.join(IDEA, "pre_wf_trades.csv"))
    nmis = []
    for i, (t, rr) in enumerate(zip(Ta, tc.itertuples(index=False))):
        bad = []
        if int(rr.entry_bar) != t[0]: bad.append("entry_bar")
        if int(rr.exit_bar) != t[1]: bad.append("exit_bar")
        if int(rr.side) != t[2]: bad.append("side")
        if abs(float(rr.entry_price) - t[3]) > 1e-9: bad.append("entry_price")
        if abs(float(rr.pnl_points_net) - (t[5] - V.COST)) > 5e-6: bad.append("pnl_points_net")
        if pd.Timestamp(rr.entry_time) != idx[t[0]]: bad.append("entry_time")
        if pd.Timestamp(rr.exit_time) != idx[t[1]]: bad.append("exit_time")
        if bad:
            nmis.append([i] + bad)
    res["lab_trades_csv_vs_armA"] = {"csv_rows": len(tc), "armA_trades": len(Ta), "rows_mismatched": len(nmis),
                                     "first_mismatches": nmis[:8], "all_match": len(tc) == len(Ta) and not nmis,
                                     "csv_sum_net_pts": float(tc.pnl_points_net.sum()),
                                     "armA_sum_net_pts": float(sum(t[5] for t in Ta) - V.COST * len(Ta))}

    # 2. own rule the plugin's way
    lit = ARMB.own_rule(o, h, l, c, day_id, stretch_k=V.STRETCH_K)
    lit7 = own_rule_pluginway(o, h, l, c, day_id, p1_trail_gate=False, p2_short_skip=False, p3_atr0_skip=False,
                              p4_atr_fallback=False)
    res["frozen_B_vs_toggles_off"] = diff([t[:6] for t in lit7], lit)
    pw = own_rule_pluginway(o, h, l, c, day_id)
    res["B_plugin_way_vs_plugin"] = diff(Ta, pw)
    res["B_literal_vs_plugin"] = diff(Ta, lit)
    toggles = {}
    for nm in ("p1_trail_gate", "p2_short_skip", "p3_atr0_skip", "p4_atr_fallback"):
        kw = {x: (x == nm) for x in ("p1_trail_gate", "p2_short_skip", "p3_atr0_skip", "p4_atr_fallback")}
        Bx = own_rule_pluginway(o, h, l, c, day_id, **kw)
        toggles[nm] = {"vs_literal": diff([t[:6] for t in Bx], lit), "trades": len(Bx)}
    res["each_departure_alone_vs_literal"] = toggles
    rng = h - l
    atr20 = pd.Series(rng).rolling(20).mean().shift(1).to_numpy()   # mean range of bars k-20..k-1
    scan = (in_sess >= 12) & (in_sess <= (ends - starts)[sess_of] - 2)
    res["departure_exposure"] = {
        "sessions_le_14_bars": int(((ends - starts) <= 14).sum()),
        "sessions_skipped_by_trail_gate": 2, "literal_trades_in_first_two_sessions": int(sum(1 for t in lit if sess_of[t[0]] < 2)),
        "scan_bars_with_atr_le_0": int(np.sum(scan & (atr20 <= 0))),
        "scan_bars_with_global_k_lt_20": int(np.sum(scan & (np.arange(len(c)) < 20))),
        "first_session_bars": int(ends[0] - starts[0])}
    # signals the literal rule finds in sessions 0/1 (any bar, not just the first)
    res["stops_check"] = {"plugin_stopped_trades": int(sum(1 for t in pw if not (t[1] == ends[sess_of[t[0]]] - 1 and t[4] == c[t[1]]))),
                          "touch_fills": int(sum(1 for t in pw if t[4] == t[6])),
                          "gap_fills": int(sum(1 for t in pw if t[4] != t[6] and not (t[1] == ends[sess_of[t[0]]] - 1 and t[4] == c[t[1]]))),
                          "stopped_on_entry_bar": int(sum(1 for t in pw if t[1] == t[0] and t[4] == t[6]))}

    # 3. look-ahead perturbation on every plugin trade
    stop_of = {(t[0], t[2]): t[6] for t in pw}
    la = {"trades_tested": 0, "entry_unchanged": 0, "side_unchanged": 0, "entry_px_unchanged": 0, "forced_stop_tests": 0,
          "forced_stop_px_equals_own_stop": 0, "baseline_subwindow_reproduces": 0, "fails": []}
    for t in Ta:
        e, side = t[0], t[2]
        si = sess_of[e]
        w0, w1 = starts[max(0, si - 22)], ends[si]
        oo, hh, ll, cc = (x[w0:w1].copy() for x in (o, h, l, c))
        dd = day_id[w0:w1]
        base = m.run_backtest(oo, hh, ll, cc, day_id=dd, return_trades=True)
        bt = [x for x in (base or {}).get("trades", []) if x[0] + w0 == e]
        la["baseline_subwindow_reproduces"] += int(len(bt) == 1 and bt[0][1] + w0 == t[1] and abs(bt[0][2] - t[5]) < 1e-9)
        ee = e - w0
        ep = oo[ee]
        # entry bar: high/low/close moved far in the trade's favour (no stop touch on it); later bars: open at entry, a
        # 1000-pt range both ways, close at entry -> a stop that reads only bars < the signal bar fills at a touch on bar e+1
        if side > 0:
            hh[ee], ll[ee], cc[ee] = ep + 500.0, ep, ep + 250.0
        else:
            hh[ee], ll[ee], cc[ee] = ep, ep - 500.0, ep - 250.0
        oo[ee + 1:], hh[ee + 1:], ll[ee + 1:], cc[ee + 1:] = ep, ep + 1000.0, ep - 1000.0, ep
        pr = m.run_backtest(oo, hh, ll, cc, day_id=dd, return_trades=True)
        pt = [x for x in (pr or {}).get("trades", []) if dd[x[0]] == day_id[e]]
        la["trades_tested"] += 1
        ok_e = len(pt) == 1 and pt[0][0] + w0 == e
        ok_s = ok_e and pt[0][3] == side
        ok_p = ok_e and pt[0][4] == t[3]
        la["entry_unchanged"] += int(ok_e); la["side_unchanged"] += int(ok_s); la["entry_px_unchanged"] += int(ok_p)
        if ee + 1 < len(oo) and dd[ee + 1] == dd[ee]:
            la["forced_stop_tests"] += 1
            xp = t[3] + side * pt[0][2] if ok_e else None
            ok_x = ok_e and pt[0][1] == ee + 1 and abs(xp - stop_of[(e, side)]) < 1e-9
            la["forced_stop_px_equals_own_stop"] += int(ok_x)
        else:
            ok_x = True
        if not (ok_e and ok_s and ok_p and ok_x):
            la["fails"].append([str(idx[e]), side])
    la["fails"] = la["fails"][:10]
    res["lookahead_perturbation"] = la

    # 4. diagnostics: Hypothesis readings (NOT the Mechanism; chosen after the results were seen)
    diag = {}
    for nm, kw in (("H_move_beyond_med_session_range", {"hyp": "move_gt_medrange"}),
                   ("H_window_range_beyond_med_session_range", {"hyp": "window_gt_medrange"}),
                   ("H_10_bar_burst_warmup10", {"warmup_bars": 10}),
                   ("need_full_20_session_trail", {"need_trail_full": True})):
        Bx = own_rule_pluginway(o, h, l, c, day_id, **kw)
        if Bx:
            diag[nm] = {"house": V.score([t[1] for t in Bx], [t[5] for t in Bx], idxn, days, V.COST),
                        "real": V.score([t[1] for t in Bx], [t[5] for t in Bx], idxn, days, V.REAL_COST),
                        "min_entry_in_session_bar": int(min(in_sess[t[0]] for t in Bx))}
            diag[nm]["four_house"] = fmt4(diag[nm]["house"])
        else:
            diag[nm] = {"trades": 0}
    res["diagnostic_variants"] = diag

    res["four_numbers"] = {"house": fmt4(houseA), "real": fmt4(realA), "stress": fmt4(stressA)}
    res["cost_line"] = {"house_pts": V.COST, "real_pts": V.REAL_COST, "real_def": "0.25 x 2 ticks + $5.65 / $20",
                        "stress_pts": V.STRESS_COST}
    res["promotion_MANAGER_129"] = {"gross_pts_per_trade": houseA["gross_pts_per_trade"],
                                    "gross_ge_house_cost": houseA["gross_pts_per_trade"] >= V.COST,
                                    "gross_ge_real_cost": houseA["gross_pts_per_trade"] >= V.REAL_COST,
                                    "net_roc_gt_0_house": houseA["roc30"] > 0, "not_one_episode": houseA["one_episode"] is False,
                                    "old_bar_roc_ge_15": houseA["roc30"] >= 15}
    res["promotion_MANAGER_129"]["promotes"] = bool(res["promotion_MANAGER_129"]["gross_ge_house_cost"] and
                                                   res["promotion_MANAGER_129"]["net_roc_gt_0_house"] and
                                                   res["promotion_MANAGER_129"]["not_one_episode"])
    s = json.dumps(V.clean(res), indent=1, sort_keys=True, allow_nan=False, default=str) + "\n"
    print(s)
    p = os.path.join(OUT, "ttm_trace.json")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print("trace sha256", hashlib.sha256(open(p, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
