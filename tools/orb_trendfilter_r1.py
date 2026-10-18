"""ORB TRENDFILTER r1 (T05; ORB lane, 2026-10-18) - the trend-day catcher (move so far at the fill) as a filter on #314's entries, vs #314
bare. Frozen in docs/PREREG_orb_trendfilter_r1_2026-10-18.md; this harness checks that note's and the paired test's LF sha256 first and stops on
a mismatch. WF entries only (2016-07-01..2025-06-27), lockbox unread, read-only (stdout and --out only).

    python tools/orb_trendfilter_r1.py [--repo <checkout with the masters>] [--out result.json]
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = os.path.join(HERE, "docs", "PREREG_orb_trendfilter_r1_2026-10-18.md")
SDMOD = os.path.join(HERE, "augur_engine", "sharpe_diff.py")
NOTE_SHA = "47dfcd13e4b3cda714da86882e990356c8e6557949df8e23b78731dce506b437"
SD_SHA = "704559490f7b3dd1c393c9b8ccdd5333321ddd4ff5269ea55246570a5e3af894"
RUN0, PRE0, PRE1, WF0, WF1 = "2010-05-01", "2010-06-07", "2016-06-30", "2016-07-01", "2025-06-27"
MASTER, MASTER_RAW = "ADJ_NQ_5m_RTH.csv", "NOADJ_NQ_5m_RTH.csv"
MULT, COST, THETA = 20.0, 0.533, 0.00584          # theta = pre-WF q75 of m on the RAW first open (0.5838%), set in the note
LEG_STRATEGY = "ORB_3_6_R6.py"
LEG_PARAMS = dict(or_bars=2, trade_mode="First-candle dir", stop_frac=2.5, atr_filter=0.75, vpace_filter=0.8, close_confirm=True, breakout_buf=0.25,
                  trail_bars=0, target_R=5.0, partial_exit_R=0.0, be_after_R=0.5, flat_eod=True, skip_holidays=True)
B_SR, M_SR, SEED, ALPHA = 20, 4999, 7, 0.05
DRAWS, BLOCK = 2000, 20


def lf_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def four30(daily, yrs):
    """the house four numbers (augur_engine.drawdowns.four_numbers) on the series scaled to a $30k worst drawdown; roc30_raw unrounded for decisions"""
    from augur_engine.drawdowns import four_numbers
    f0 = four_numbers(daily, years=yrs)
    k = 30000.0 / f0["max_dd"] if f0["max_dd"] else 1.0
    f = four_numbers(daily * k, years=yrs)
    return {"roc30": None if f["roc30"] is None else round(f["roc30"], 2), "roc30_raw": f["roc30"], "dd5_at_30k": round(float(f["dd5_usd"]), 0),
            "dd_pct_peak_at_30k": round(float(f["dd_pct_peak"]), 2), "sortino": None if f["sortino"] is None else round(f["sortino"], 3),
            "one_episode": bool(f["one_episode"]), "net_per_year": round(float(f0["net_per_year"]), 0), "max_dd": round(float(f0["max_dd"]), 0),
            "worst_over_dd5": round(float(f["max_dd"]) / float(f["dd5_usd"]), 3) if f["dd5_usd"] else None}


def roc30(v, yrs, np):
    q = np.cumsum(v)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max())
    return 30.0 * (float(v.sum()) / yrs) / dd if dd > 0 else float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    got, gsd = lf_sha(NOTE), lf_sha(SDMOD)
    print("PIN note LF sha256 %s (frozen %s); test module %s (frozen %s); harness %s" % (got, NOTE_SHA, gsd, SD_SHA, lf_sha(os.path.abspath(__file__))),
          flush=True)
    if got != NOTE_SHA or gsd != SD_SHA:
        raise SystemExit("refused: the prereg note or the test module is not the frozen one (nothing computed)")
    sys.path.insert(0, a.repo)                                  # the engine, masters and registry live in the shared checkout
    os.chdir(a.repo)
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "0")
    import numpy as np
    import pandas as pd
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    import importlib.util
    _sp = importlib.util.spec_from_file_location("lw_sharpe_diff", SDMOD)       # the pinned test module, loaded from its own file
    _sd = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(_sd)
    sharpe_diff_test = _sd.sharpe_diff_test
    from scipy import stats
    leg = cs.CROWN_LEGS["ORB_R6"]
    if leg["strategy"] != LEG_STRATEGY or dict(leg["params"]) != LEG_PARAMS:
        raise SystemExit("refused: CROWN_LEGS['ORB_R6'] is not the frozen leg: %s %s" % (leg["strategy"], leg["params"]))
    for fn in ("ORB_3_6.py", LEG_STRATEGY):
        print("PIN strategy %s LF sha256 %s" % (fn, lf_sha(os.path.join(a.repo, "augur_strategies", fn))), flush=True)
    m = find_master("NQ", "5m", "rth", "db_adj_rth")
    mr = find_master("NQ", "5m", "rth", "db_noadj_rth")
    if m is None or m.get("filename") != MASTER or mr is None or mr.get("filename") != MASTER_RAW:
        raise SystemExit("refused: the NQ 5m masters are %r / %r, not the frozen %s / %s" % (m and m.get("filename"), mr and mr.get("filename"),
                         MASTER, MASTER_RAW))
    arr = load_master_arrays(m, date_from=RUN0, date_to=WF1)
    raw = load_master_arrays(mr, date_from=RUN0, date_to=WF1)
    ix = pd.DatetimeIndex(arr["index"])
    if len(ix) != len(raw["index"]) or not (ix == pd.DatetimeIndex(raw["index"])).all():
        raise SystemExit("refused: the adjusted and raw NQ 5m windows do not share one bar index")
    print("DATA %s + %s: %d bars, %s .. %s; fingerprints %s / %s" % (MASTER, MASTER_RAW, len(ix), ix[0], ix[-1], arr.get("fingerprint"),
          raw.get("fingerprint")), flush=True)
    r = run_backtest(leg["strategy"], arrays=arr, params=dict(leg["params"]), cost_pts=COST, return_trades=True)
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    day = ix.normalize()
    first_open = pd.Series(np.asarray(arr["open"], float), index=ix).groupby(day).first()
    first_raw = pd.Series(np.asarray(raw["open"], float), index=ix).groupby(day).first()        # the % denominator: no future roll offsets
    first_pos = pd.Series(np.arange(len(ix)), index=ix).groupby(day).first()
    hi, lo = np.asarray(arr["high"], float), np.asarray(arr["low"], float)
    T0, T1 = pd.Timestamp(WF0), pd.Timestamp(WF1)
    rows, pre = [], []
    for t in r["trades"]:
        ei, xi, pts, d, e = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        dd = day[ei]
        O, R, p0 = float(first_open[dd]), float(first_raw[dd]), int(first_pos[dd])
        sd = 1 if d > 0 else -1
        rec = {"entry_day": dd, "exit_day": day[min(xi, len(day) - 1)], "usd": pts * MULT, "net_pts": pts, "ret": pts / (e - O + R),
               "m": sd * (e - O) / R, "orw": (hi[p0:p0 + 2].max() - lo[p0:p0 + 2].min()) / R, "after_or": ei >= p0 + 1}
        if T0 <= dd <= T1:
            rows.append(rec)
        elif pd.Timestamp(PRE0) <= dd <= pd.Timestamp(PRE1):
            pre.append(rec)
    T, PW = pd.DataFrame(rows), pd.DataFrame(pre)
    if not T.after_or.all() or not PW.after_or.all():
        raise SystemExit("refused: an entry inside the 2-bar opening range (OR width would not be known at the fill)")
    q75_pre = float(PW.m.quantile(0.75))
    W_TH = float(PW.orw.quantile(0.75))                         # report-only OR-width control: skip OR width >= its pre-WF q75
    print("CHECK pre-WF: %d trades; q75 of m %.6f (note's theta %.6f); OR-width q75 %.6f; corr(m, OR width) %.2f" % (len(PW), q75_pre, THETA,
          W_TH, PW.m.corr(PW.orw)), flush=True)
    if abs(q75_pre - THETA) > 5e-5:
        raise SystemExit("refused: the pre-WF q75 of m (%.6f) is not the note's theta (%.6f) - the data or the leg moved" % (q75_pre, THETA))
    yrs = (T1 - T0).days / 365.25
    cal = pd.DatetimeIndex(sorted(set(day)))
    cal = cal[(cal >= T0) & (cal <= T1)]
    print("leg %s %s on %s; WF trades %d; m >= %.3f%% on %d (%.0f%%); WF corr(m, OR width) %.2f" % (leg["strategy"], leg["params"], m["filename"],
          len(T), 100 * THETA, int((T.m >= THETA).sum()), 100 * (T.m >= THETA).mean(), T.m.corr(T.orw)), flush=True)
    keep = {"A": np.ones(len(T), bool), "F+": (T.m >= THETA).to_numpy(), "F-": (T.m < THETA).to_numpy(), "W-": (T.orw < W_TH).to_numpy()}
    label = {"A": "#314 bare", "F+": "CATCHER", "F-": "NARROW OPEN", "W-": "OR-WIDTH CONTROL (report-only)"}
    daily = {}
    res = {"note_sha": NOTE_SHA, "sd_sha": SD_SHA, "harness_sha": lf_sha(os.path.abspath(__file__)), "masters": [MASTER, MASTER_RAW],
           "window": [WF0, WF1], "trades": int(len(T)), "theta": THETA, "orw_theta": W_TH, "arms": {}}
    for k, kp in keep.items():
        s = pd.Series(T["usd"].to_numpy() * kp, index=pd.DatetimeIndex(T["exit_day"])).groupby(level=0).sum()
        daily[k] = s.reindex(cal).fillna(0.0)
        if abs(float(daily[k].sum()) - float(T.usd[kp].sum())) > 1e-6:
            raise SystemExit("refused: arm %s lost exit-day P&L off the RTH calendar" % k)
        f = four30(daily[k], yrs)
        n_k = int(kp.sum())
        f["label"] = label[k]
        f["trades"] = n_k
        f["trades_per_year"] = round(n_k / yrs, 1)
        f["gross_pt_per_trade_raw"] = float((T.net_pts[kp] + COST).mean()) if n_k else None
        f["gross_pt_per_trade"] = None if f["gross_pt_per_trade_raw"] is None else round(f["gross_pt_per_trade_raw"], 3)
        f["cost_pt_per_trade"] = COST
        f["mdl_ok"] = bool(f["roc30_raw"] is not None and f["roc30_raw"] >= 15)
        res["arms"][k] = f
        print("ARM %-2s %s: ROC@30k %s | DD5 $%s | DD%% %s | Sortino %s%s | worst/DD5 %s | net/yr $%s | %s trades/yr | gross %s pt vs cost %s" % (
              k, label[k], f["roc30"], f["dd5_at_30k"], f["dd_pct_peak_at_30k"], f["sortino"], " (one episode)" if f["one_episode"] else "",
              f["worst_over_dd5"], f["net_per_year"], f["trades_per_year"], f["gross_pt_per_trade"], COST), flush=True)
    # kept vs skipped per trade (% of price)
    x, y = T.ret[T.m >= THETA], T.ret[T.m < THETA]
    w = stats.ttest_ind(x, y, equal_var=False)
    se = math.sqrt(x.var(ddof=1) / len(x) + y.var(ddof=1) / len(y))
    dfree = se ** 4 / ((x.var(ddof=1) / len(x)) ** 2 / (len(x) - 1) + (y.var(ddof=1) / len(y)) ** 2 / (len(y) - 1))
    hw = float(stats.t.ppf(0.975, dfree)) * se
    dlt = float(x.mean() - y.mean())
    res["split"] = {"n_high": int(len(x)), "n_low": int(len(y)), "mean_high_pct": round(100 * x.mean(), 4), "mean_low_pct": round(100 * y.mean(), 4),
                    "diff_pct": round(100 * dlt, 4), "ci95_pct": [round(100 * (dlt - hw), 4), round(100 * (dlt + hw), 4)], "p": round(float(w.pvalue), 4)}
    print("SPLIT per trade: m >= theta n %d mean %.4f%% | m < theta n %d mean %.4f%% | high - low %.4f%% (95%% %s) p %.4f" % (len(x), 100 * x.mean(),
          len(y), 100 * y.mean(), 100 * dlt, res["split"]["ci95_pct"], w.pvalue), flush=True)
    # arm vs A: paired Sharpe and ROC lead
    rng = np.random.default_rng(SEED)
    VA = daily["A"].to_numpy(float)
    N = len(VA)
    nb = int(math.ceil(N / BLOCK))
    leads = {"F+": [], "F-": [], "W-": []}
    for _ in range(DRAWS):                                      # report-only interval (resampled-path max DD is not centred on the observed one)
        st = rng.integers(0, N - BLOCK + 1, size=nb)
        idx = (st[:, None] + np.arange(BLOCK)[None, :]).ravel()[:N]
        ra = roc30(VA[idx], yrs, np)
        for k in leads:
            leads[k].append(roc30(daily[k].to_numpy(float)[idx], yrs, np) - ra)
    ps = {}
    raw_t = {}
    for k in ("F+", "F-", "W-"):
        t = sharpe_diff_test(daily[k].to_numpy(float), VA, b=B_SR, M=M_SR, alpha=ALPHA, seed=SEED)
        raw_t[k] = t
        lo, hi = np.nanpercentile(leads[k], [5, 95])
        lead_raw = (res["arms"][k]["roc30_raw"] or 0.0) - (res["arms"]["A"]["roc30_raw"] or 0.0)
        rec = {"sr_arm": round(t["sr_x"], 3), "sr_A": round(t["sr_y"], 3), "sr_diff": round(t["diff"], 4), "sr_ci95": [round(u, 4) for u in t["ci_boot"]],
               "sr_p": round(t["p_boot"], 4), "sr_p_raw": float(t["p_boot"]), "mde80": round(2.8 * t["se_hac"], 4),
               "roc_lead": round(lead_raw, 2), "roc_lead_ci90_report_only": [round(float(lo), 2), round(float(hi), 2)]}
        res["vs_A_" + k] = rec
        if k != "W-":
            ps[k] = float(t["p_boot"])
        print("%s vs A: Sharpe %.3f vs %.3f diff %+.4f (95%% %s) p %.4f (two-sided) MDE80 %.3f | ROC lead %+.2f (90%% %s, report-only)%s" % (k,
              rec["sr_arm"], rec["sr_A"], rec["sr_diff"], rec["sr_ci95"], rec["sr_p"], rec["mde80"], rec["roc_lead"], rec["roc_lead_ci90_report_only"],
              "  [OR-width control, not in the verdict]" if k == "W-" else ""), flush=True)
    # Holm over the two verdict arms (strict <), then the verdicts on unrounded values
    order = sorted(ps, key=lambda k: ps[k])
    holm = set()
    for i, k in enumerate(order):
        if ps[k] < ALPHA / (2 - i):
            holm.add(k)
        else:
            break
    for k in ("F+", "F-"):
        f, v, t = res["arms"][k], res["vs_A_" + k], raw_t[k]
        clauses = {"gross>=cost": bool(f["gross_pt_per_trade_raw"] is not None and f["gross_pt_per_trade_raw"] >= COST),
                   "roc>0": bool((f["roc30_raw"] or 0.0) > 0), "roc>=15 (MDL path)": f["mdl_ok"]}
        bar = all(clauses.values())
        cond = {"sharpe diff>0 & Holm": bool(t["diff"] > 0 and k in holm),
                "ROC above A": bool((f["roc30_raw"] or 0.0) > (res["arms"]["A"]["roc30_raw"] or 0.0)),
                "not one episode": not f["one_episode"], "MANAGER bar": bar}
        lifts = all(cond.values())
        reading = "LIFTS" if lifts else ("REVERSED" if t["ci_boot"][1] < 0 else "NOT SHOWN")
        v["bar_clauses"], v["conditions"], v["manager_bar"], v["lifts"], v["reading"] = clauses, cond, bar, lifts, reading
        print("ARM %s %s: MANAGER bar %s %s; conditions %s; reading %s" % (k, label[k], "pass" if bar else "fail", clauses, cond, reading), flush=True)
    verdict = ("THE CATCHER FILTER LIFTS #314" if res["vs_A_F+"]["lifts"] else "A NARROW-OPEN FILTER LIFTS #314" if res["vs_A_F-"]["lifts"]
               else "NO FILTER LIFT")
    res["verdict"] = verdict
    # report-only map on the WF money days (after the verdict)
    dayp = T.groupby("exit_day")["usd"].sum().sort_values(ascending=False)
    top = T[T["exit_day"].isin(set(dayp.index[:26]))]
    res["top26_kept_by_catcher"] = [int((top.m >= THETA).sum()), int(len(top))]
    print("MAP (report): WF top-26 money days: %d of %d trades had m >= theta" % tuple(res["top26_kept_by_catcher"]), flush=True)
    print("VERDICT: %s" % verdict, flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, default=str)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
