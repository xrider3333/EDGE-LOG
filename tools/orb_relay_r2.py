"""ORB RELAY r2 (T34; ORB lane, 2026-10-18) - the live QQQ ORB leg on NQ #314's signals, at the Webull leg's cost, +2 slippage ticks a side,
one-bar-late fills and fold by fold. Frozen in docs/PREREG_orb_relay_r2_2026-10-18.md; this harness checks that note's and the paired test's
LF sha256 first and stops on a mismatch, then pins the leg and the four masters and reproduces RELAY r1 before any pair is read.
WF only (2016-07-01..2025-06-27), lockbox unread, read-only (stdout and --out only).

    python tools/orb_relay_r2.py [--repo <checkout with the masters>] [--out result.json]
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = os.path.join(HERE, "docs", "PREREG_orb_relay_r2_2026-10-18.md")
SDMOD = os.path.join(HERE, "augur_engine", "sharpe_diff.py")
NOTE_SHA = "072b1df69c9a2d6364e4445ba7ec6c34d4af8f2f223e53623071d6581472530d"
SD_SHA = "704559490f7b3dd1c393c9b8ccdd5333321ddd4ff5269ea55246570a5e3af894"
WF0, WF1 = "2016-07-01", "2025-06-27"
MASTERS = {"q5": ("QQQ", "5m", "rth", "alpaca_split_rth", "master_ac263357.csv"), "n5": ("NQ", "5m", "rth", "db_adj_rth", "ADJ_NQ_5m_RTH.csv"),
           "q1": ("QQQ", "1m", "rth", "alpaca_split_rth", "master_dd092f50.csv"), "n1": ("NQ", "1m", "rth", "db_adj_rth", "ADJ_NQ_1m_RTH.csv")}
LEG_STRATEGY = "ORB_3_6_R6.py"
LEG_PARAMS = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.5, atr_filter=0.75, vpace_filter=0.8, close_confirm=True, breakout_buf=0.25,
                  trail_bars=0, target_R=5.0, partial_exit_R=0.0, be_after_R=0.5, flat_eod=True, skip_holidays=True)
UNIT = 10
C_HOUSE, C_HOUSE2, C_WB, C_WB2, C_LIVE = 0.02, 0.06, 0.097, 0.137, 0.19     # $ a share a round trip; +2 ticks a side = +$0.04
REPRO = {"A_trades": 1161, "A_roc": 23.47, "A_tol": 0.05, "C_roc": 34.36, "C_tol": 0.10}  # RELAY r1 / COSTSTRESS r1 at $0.02
DRAWS, BLOCK, SEED = 2000, 20, 20261018
B_SR, M_SR, SR_SEED, ALPHA, FOLDS, FOLD_BAR = 20, 4999, 7, 0.05, 8, 6


def lf_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def four30(daily, yrs):
    """the house four numbers on the series scaled to a $30k worst drawdown; roc30_raw unrounded for decisions"""
    from augur_engine.drawdowns import four_numbers
    f0 = four_numbers(daily, years=yrs)
    k = 30000.0 / f0["max_dd"] if f0["max_dd"] else 1.0
    f = four_numbers(daily * k, years=yrs)
    return {"roc30": None if f["roc30"] is None else round(f["roc30"], 2), "roc30_raw": f["roc30"], "dd5_at_30k": round(float(f["dd5_usd"]), 0),
            "dd_pct_peak_at_30k": round(float(f["dd_pct_peak"]), 2), "sortino": None if f["sortino"] is None else round(f["sortino"], 3),
            "one_episode": bool(f["one_episode"]), "worst_over_dd5": round(float(f["max_dd"]) / float(f["dd5_usd"]), 3) if f["dd5_usd"] else None,
            "net_per_year": round(float(f0["net_per_year"]), 2), "max_dd": round(float(f0["max_dd"]), 2), "scale_to_30k": k}


def roc30(v, yrs, np):
    q = np.cumsum(v)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max())
    return 30.0 * (float(v.sum()) / yrs) / dd if dd > 0 else float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if not os.path.exists(NOTE) or not os.path.exists(SDMOD):
        raise SystemExit("refused: the prereg note or augur_engine/sharpe_diff.py is missing next to this harness (nothing computed)")
    got, gsd = lf_sha(NOTE), lf_sha(SDMOD)
    print("PIN note LF sha256 %s (frozen %s); sharpe_diff.py %s (frozen %s); harness %s" % (got, NOTE_SHA, gsd, SD_SHA,
          lf_sha(os.path.abspath(__file__))), flush=True)
    if got != NOTE_SHA or gsd != SD_SHA:
        raise SystemExit("refused: the prereg note or the test module is not the frozen one (nothing computed)")
    sys.path.insert(0, a.repo)                                  # the engine, masters and registry live in the shared checkout
    os.chdir(a.repo)
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "0")
    import numpy as np
    import pandas as pd
    from scipy import stats
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    import importlib.util
    _sp = importlib.util.spec_from_file_location("lw_sharpe_diff", SDMOD)       # the pinned test module, loaded from its own file
    _sd = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(_sd)
    sharpe_diff_test = _sd.sharpe_diff_test
    leg = cs.CROWN_LEGS["ORB_R6"]
    if leg["strategy"] != LEG_STRATEGY or dict(leg["params"]) != LEG_PARAMS:
        raise SystemExit("refused: CROWN_LEGS['ORB_R6'] is not the frozen leg: %s %s" % (leg["strategy"], leg["params"]))
    P = dict(leg["params"])
    assert P["trail_bars"] == 0 and P["partial_exit_R"] == 0     # the exit-level reconstruction below needs no trail and no partials
    for fn in ("ORB_3_6.py", LEG_STRATEGY):
        print("PIN strategy %s LF sha256 %s" % (fn, lf_sha(os.path.join(a.repo, "augur_strategies", fn))), flush=True)
    T0, T1 = pd.Timestamp(WF0), pd.Timestamp(WF1)

    def et(ix):
        ix = pd.DatetimeIndex(ix)
        return ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix

    def master(key):
        sym, tf, sess, src, fn = MASTERS[key]
        m = find_master(sym, tf, sess, src)
        if m is None or m.get("filename") != fn:
            raise SystemExit("refused: master %s/%s/%s/%s is %r, not the frozen %s" % (sym, tf, sess, src, m and m.get("filename"), fn))
        return m

    fps = {}

    def trades_of(key):
        m = master(key)
        arr = load_master_arrays(m, date_to=WF1)
        fps[key] = arr.get("fingerprint")
        r = run_backtest(leg["strategy"], arrays=arr, params=dict(P), cost_pts=0.0, return_trades=True)
        ix = et(arr["index"])
        out, phantom = [], 0
        for t in r["trades"]:
            ei, xi, pts, d, e = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
            if ix[ei].normalize() < T0 or ix[min(xi, len(ix) - 1)].normalize() > T1:
                continue
            out.append((ei, xi, pts, d, e, xi == ei))         # last flag: a phantom last-bar entry (enter and go flat on the session's last bar)
            phantom += int(xi == ei)
        print("DATA %s %s: %d bars %s .. %s; fingerprint %s; WF trades %d (phantom last-bar entries %d)" % (key, m["filename"], len(ix), ix[0],
              ix[-1], fps[key], len(out), phantom), flush=True)
        return m, arr, ix, out, phantom

    qm5, q5, qix5, A_all, ph_A = trades_of("q5")
    nm5, n5, nix5, N_all, ph_N = trades_of("n5")
    cal = pd.DatetimeIndex(sorted(set(qix5.normalize())))
    cal = cal[(cal >= T0) & (cal <= T1)]
    calset = set(cal)
    yrs = (cal[-1] - cal[0]).days / 365.25
    m1n, m1q = master("n1"), master("q1")
    a1n = load_master_arrays(m1n, date_from="2016-06-01", date_to=WF1)
    a1q = load_master_arrays(m1q, date_from="2016-06-01", date_to=WF1)
    fps["n1"], fps["q1"] = a1n.get("fingerprint"), a1q.get("fingerprint")
    n1 = pd.DataFrame({"h": np.asarray(a1n["high"], float), "l": np.asarray(a1n["low"], float)}, index=et(a1n["index"]))
    q1 = pd.DataFrame({"o": np.asarray(a1q["open"], float), "c": np.asarray(a1q["close"], float)}, index=et(a1q["index"]))
    qlast = pd.Series(q1.index, index=q1.index).groupby(q1.index.normalize()).max()
    print("DATA 1m: NQ %s (%d rows, fingerprint %s), QQQ %s (%d rows, fingerprint %s)" % (m1n["filename"], len(n1), fps["n1"], m1q["filename"],
          len(q1), fps["q1"]), flush=True)
    nclose = np.asarray(n5["close"], float)
    last_of_day = pd.Series(np.arange(len(nix5)), index=nix5).groupby(nix5.normalize()).max()
    one = pd.Timedelta(minutes=1)

    def px(col, ts):
        if ts is None:
            return None
        v = q1[col].get(ts)
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)

    # relay fills: C next-print, CL one NQ 5m bar late (blind 5 min), CY the box's Yahoo delay (bar te seen at te+20; exits 15 min late)
    rel = {"C": [], "CL": [], "CY": []}
    miss = {k: {"entry": 0, "exit": 0} for k in rel}
    cnt = {"nq_trades": len(N_all), "phantom_nq": ph_N, "phantom_qqq": ph_A, "eod": 0, "fallback": 0, "cl_exit_before_entry": 0,
           "cy_exit_before_entry": 0}
    for ei, xi, pts, d, e, ph in N_all:
        if ph:
            continue
        te, tx = nix5[ei], nix5[xi]
        day = tx.normalize()
        lvl = e + pts * d
        lm = qlast.get(day)
        is_eod = xi == int(last_of_day[day]) and abs(lvl - nclose[xi]) < 1e-6
        if is_eod:
            cnt["eod"] += 1
            x = {"C": px("c", lm), "CL": px("c", lm), "CY": px("c", lm)}
        else:
            mins = n1.loc[tx:tx + 4 * one]
            if d > 0:
                hit = mins.index[(mins["l"] <= lvl).to_numpy()] if lvl <= e else mins.index[(mins["h"] >= lvl).to_numpy()]
            else:
                hit = mins.index[(mins["h"] >= lvl).to_numpy()] if lvl >= e else mins.index[(mins["l"] <= lvl).to_numpy()]
            if len(hit):
                hm = hit[0]
            else:
                hm = tx + 4 * one
                cnt["fallback"] += 1
            cnt["cl_exit_before_entry"] += int(hm < te + 10 * one)
            cnt["cy_exit_before_entry"] += int(hm < te + 20 * one)
            x = {"C": px("c", hm), "CL": px("c", None if lm is None else min(hm + 5 * one, lm)),
                 "CY": px("c", None if lm is None else min(hm + 15 * one, lm))}
        en = {"C": px("o", te + 5 * one), "CL": px("o", te + 10 * one), "CY": px("o", te + 20 * one)}
        for k in rel:
            if en[k] is None or (k != "C" and lm is not None and te + {"CL": 10, "CY": 20}[k] * one > lm):
                miss[k]["entry"] += 1
                continue
            if x[k] is None:
                miss[k]["exit"] += 1
                continue
            rel[k].append((day, d * (x[k] - en[k])))                    # gross $ a share
    A_rows_r1 = [(qix5[min(xi, len(qix5) - 1)].normalize(), pts) for _ei, xi, pts, _d, _e, _ph in A_all]          # r1's A (phantoms kept)
    A_rows = [(qix5[min(xi, len(qix5) - 1)].normalize(), pts) for _ei, xi, pts, _d, _e, ph in A_all if not ph]   # gross $ a share (cost 0)
    print("relay fills: %d NQ trades (%d phantom last-bar entries skipped; QQQ A phantoms skipped %d); EOD %d; stop/target with no NQ minute at "
          "the level %d (bar's last minute used); dropped C %s, CL %s, CY %s; CL exits that fired before its late entry %d, CY %d" % (len(N_all),
          ph_N, ph_A, cnt["eod"], cnt["fallback"], miss["C"], miss["CL"], miss["CY"], cnt["cl_exit_before_entry"], cnt["cy_exit_before_entry"]),
          flush=True)
    for k, rows in list(rel.items()) + [("A", A_rows), ("A_r1", A_rows_r1)]:
        off = [d for d, _g in rows if d not in calset]
        if off:
            raise SystemExit("refused: %s rows off the QQQ WF calendar: %d" % (k, len(off)))

    def daily(rows, cost):
        if not rows:
            return pd.Series(0.0, index=cal)
        s = pd.Series([UNIT * (g - cost) for _d, g in rows], index=pd.DatetimeIndex([d for d, _g in rows])).groupby(level=0).sum()
        return s.reindex(cal).fillna(0.0)

    # repro gate: RELAY r1's A (phantoms kept) and C at $0.02, before any new arm or pair is read
    fa, fc = four30(daily(A_rows_r1, C_HOUSE), yrs), four30(daily(rel["C"], C_HOUSE), yrs)
    rep = {"A_trades": len(A_rows_r1), "A_roc": fa["roc30_raw"], "C_trades": len(rel["C"]), "C_roc": fc["roc30_raw"]}
    ok = (rep["A_trades"] == REPRO["A_trades"] and fa["roc30_raw"] is not None and abs(fa["roc30_raw"] - REPRO["A_roc"]) <= REPRO["A_tol"]
          and fc["roc30_raw"] is not None and abs(fc["roc30_raw"] - REPRO["C_roc"]) <= REPRO["C_tol"])
    print("REPRO r1 at $0.02: A %d trades ROC %.3f (r1 %d / %.2f); C %d trades ROC %.3f (r1 %.2f) -> %s" % (rep["A_trades"], fa["roc30_raw"] or float("nan"),
          REPRO["A_trades"], REPRO["A_roc"], rep["C_trades"], fc["roc30_raw"] or float("nan"), REPRO["C_roc"], "OK" if ok else "REPRO MISMATCH"),
          flush=True)
    if not ok:
        raise SystemExit("REPRO MISMATCH: the data or the leg moved since RELAY r1 - stopped before any pair is read")

    fills = {"A": A_rows, "C": rel["C"], "CL": rel["CL"], "CY": rel["CY"]}
    arms = {"A": ("A", C_HOUSE), "C": ("C", C_HOUSE),
            "A2": ("A", C_HOUSE2), "C2": ("C", C_HOUSE2),
            "AW": ("A", C_WB), "CW": ("C", C_WB), "CLW": ("CL", C_WB),
            "AW2": ("A", C_WB2), "CW2": ("C", C_WB2), "CLW2": ("CL", C_WB2), "CYW2": ("CY", C_WB2),
            "A4": ("A", C_LIVE), "C4": ("C", C_LIVE), "CL4": ("CL", C_LIVE)}
    D = {}
    res = {"note_sha": NOTE_SHA, "sd_sha": SD_SHA, "harness_sha": lf_sha(os.path.abspath(__file__)), "window": [WF0, WF1],
           "masters": {k: v[4] for k, v in MASTERS.items()}, "fingerprints": fps, "params": P, "repro_r1": rep, "counts": cnt, "dropped": miss,
           "arms": {}, "pairs": {}}
    for k, (src, c) in arms.items():
        D[k] = daily(fills[src], c)
        f = four30(D[k], yrs)
        g = [x for _d, x in fills[src]]
        gps = float(np.mean(g)) if g else float("nan")
        f.update({"fill": src, "trades": len(g), "trades_per_year": round(len(g) / yrs, 1), "gross_per_share": round(gps, 4), "cost_per_share": c,
                  "gross_cost_ratio": round(gps / c, 3)})
        f["bar_clauses"] = {"gross>=cost": bool(gps >= c), "roc>0": bool((f["roc30_raw"] or 0.0) > 0), "not one episode": not f["one_episode"],
                            "roc>=15 (MDL path)": bool((f["roc30_raw"] or 0.0) >= 15)}
        f["bar"] = all(f["bar_clauses"].values())
        res["arms"][k] = f
        print("ARM %-4s (%s fills, $%.3f): ROC@30k %s | DD5 $%s | DD%% %s | Sortino %s%s | worst/DD5 %s | net/yr $%s | %s trades/yr | gross $%.4f/sh"
              " = %.2f x cost | bar %s%s" % (k, src, c, f["roc30"], f["dd5_at_30k"], f["dd_pct_peak_at_30k"], f["sortino"],
              " (one episode)" if f["one_episode"] else "", f["worst_over_dd5"], f["net_per_year"], f["trades_per_year"], gps, f["gross_cost_ratio"],
              "PASS" if f["bar"] else "fail", "" if f["bar"] else " (" + ", ".join(x for x, v in f["bar_clauses"].items() if not v) + ")"), flush=True)
    n = len(cal)
    edges = np.linspace(0, n, FOLDS + 1).astype(int)
    rng = np.random.default_rng(SEED)
    nb = int(math.ceil(n / BLOCK))
    idxs = []
    for _ in range(DRAWS):
        st = rng.integers(0, n - BLOCK + 1, size=nb)
        idxs.append((st[:, None] + np.arange(BLOCK)[None, :]).ravel()[:n])
    pairs = (("CW", "AW"), ("CLW2", "AW2"),                                       # the verdict pairs
             ("C", "A"), ("C2", "A2"), ("CLW", "AW"), ("CW2", "AW2"), ("CYW2", "AW2"), ("C4", "A4"), ("CL4", "A4"))   # report-only
    for rk, lk in pairs:
        vr, vl = D[rk].to_numpy(float), D[lk].to_numpy(float)
        lead = (res["arms"][rk]["roc30_raw"] or 0.0) - (res["arms"][lk]["roc30_raw"] or 0.0)
        bs = [roc30(vr[i], yrs, np) - roc30(vl[i], yrs, np) for i in idxs]
        lo, hi = np.nanpercentile(bs, [5, 95])
        t = sharpe_diff_test(vr, vl, b=B_SR, M=M_SR, alpha=ALPHA, seed=SR_SEED)
        holds = [bool(vr[edges[j]:edges[j + 1]].sum() > vl[edges[j]:edges[j + 1]].sum()) for j in range(FOLDS)]
        kr, kl = res["arms"][rk]["scale_to_30k"], res["arms"][lk]["scale_to_30k"]
        holds30 = [bool(kr * vr[edges[j]:edges[j + 1]].sum() > kl * vl[edges[j]:edges[j + 1]].sum()) for j in range(FOLDS)]
        k_hold = int(sum(holds))
        sign_p = float(stats.binomtest(k_hold, FOLDS, 0.5, alternative="greater").pvalue)
        rec = {"roc_lead": round(lead, 2), "roc_lead_raw": lead, "roc_lead_ci90": [round(float(lo), 2), round(float(hi), 2)],
               "sr_relay": round(t["sr_x"], 3), "sr_live": round(t["sr_y"], 3), "sr_diff": round(t["diff"], 4), "sr_ci95": [round(u, 4) for u in t["ci_boot"]],
               "sr_p_two_sided": round(t["p_boot"], 4), "sr_p_raw": float(t["p_boot"]), "sr_mde80": round(2.8 * t["se_hac"], 4),
               "folds_hold": k_hold, "fold_flags": holds, "sign_p": round(sign_p, 4), "folds_hold_at_30k_report": int(sum(holds30)),
               "fold_net_diff": [round(float(vr[edges[j]:edges[j + 1]].sum() - vl[edges[j]:edges[j + 1]].sum()), 0) for j in range(FOLDS)],
               "fold_dates": [[str(cal[edges[j]].date()), str(cal[edges[j + 1] - 1].date())] for j in range(FOLDS)]}
        res["pairs"]["%s_vs_%s" % (rk, lk)] = rec
        print("%-4s vs %-3s: ROC lead %+.2f (90%% %s) | folds %d/8 (sign p %.3f; at $30k %d/8) %s | Sharpe %.3f vs %.3f diff %+.4f (95%% %s) p %.4f "
              "two-sided, MDE80 %.3f (report-only)" % (rk, lk, rec["roc_lead"], rec["roc_lead_ci90"], k_hold, sign_p, rec["folds_hold_at_30k_report"],
              rec["fold_net_diff"], rec["sr_relay"], rec["sr_live"], rec["sr_diff"], rec["sr_ci95"], rec["sr_p_two_sided"], rec["sr_mde80"]), flush=True)
    A_, C_, S_, SA = res["arms"]["AW"], res["arms"]["CW"], res["arms"]["CLW2"], res["arms"]["AW2"]
    pw, ps_ = res["pairs"]["CW_vs_AW"], res["pairs"]["CLW2_vs_AW2"]
    conds = {}
    for x, v in C_["bar_clauses"].items():
        conds["CW " + x] = v
    conds["CW vs AW holds in >= 6 of 8 folds"] = pw["folds_hold"] >= FOLD_BAR
    conds["CLW2 ROC above AW2's"] = bool((S_["roc30_raw"] or 0.0) > (SA["roc30_raw"] or 0.0))
    for x, v in S_["bar_clauses"].items():
        conds["CLW2 " + x] = v
    conds["CLW2 vs AW2 holds in >= 6 of 8 folds"] = ps_["folds_hold"] >= FOLD_BAR
    fails = [k for k, v in conds.items() if not v]
    if (C_["roc30_raw"] or 0.0) <= (A_["roc30_raw"] or 0.0):                    # decided first
        verdict = "NO CASE FOR THE RELAY"
    elif not fails:
        verdict = "RELAY HOLDS UNDER STRESS"
    elif all(k.endswith("not one episode") for k in fails):
        verdict = "RELAY LEAD STABLE, ONE-EPISODE (fails only: %s; worst/DD5 CW %s, CLW2 %s)" % ("; ".join(fails), C_["worst_over_dd5"],
                                                                                              S_["worst_over_dd5"])
    else:
        verdict = "RELAY LEADS, NOT ROBUST (fails: %s)" % "; ".join(fails)
    res["conditions"], res["verdict"] = conds, verdict
    print("CONDITIONS: %s" % conds, flush=True)
    print("VERDICT: %s" % verdict, flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, default=str)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
