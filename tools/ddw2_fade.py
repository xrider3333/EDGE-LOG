"""
DD-WEEK r2 (TV) = DAILYFADE - pre-registered in docs/DDWEEK_FADE_R1.md (+ pre-data addendum 1) before this file ran: fade
the NQ / ES cash-session move both ways (enter 16:00, hold one session), flat or ES-volatility-leaned size, judged on BOOK
#463's drawdown days. Stage A + A2 on the walk-forward ONLY; arrays are cut before 2025-06-30 00:00 ET before any signal.

Addendum 1: every signal quantity is in POINTS on the roll-corrected master (db_adj_rth) - points are shift-invariant, a
back-adjusted LEVEL is not a price (June 2010 NQ ~5,553 adjusted vs ~1,820 raw). The RAW master (db_noadj_rth) only sets
the whole-micro count: n = max(1, round($100k x k / (raw x $2 MNQ | $5 MES))).

    python tools/ddw2_fade.py --selftest      # synthetic bars only
    python tools/ddw2_fade.py                 # the pre-registered run
"""
import csv, json, os, sys
import numpy as np, pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
OUT = r"C:\EdgeLog\_anatomy_cache\ddweek\r2"
BOOK = r"C:\EdgeLog\_anatomy_cache\rocfrontier\r4\book463_daily.csv"
CUT = pd.Timestamp("2025-06-30 00:00", tz="US/Eastern")
EARLY_END = pd.Timestamp("2016-06-30")
WF = (pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"))
MULT = {"NQ": 20.0, "ES": 50.0}
COST = {"NQ": 0.533, "ES": 0.363}
MICRO_COMM_RT = 1.00                      # $0.50 a side per micro
STRESS, ROLL_PT, NOTIONAL = 0.25, 0.25, 100000.0
CELLS = [(m, f, l) for m in ("NQ", "ES") for f in ("m0", "m1") for l in ("F", "S")]
DD_EPISODE, NULL_REPS, SEED = 14950.0, 500, 20261004
BOOK_BAR_ROC, BOOK_BAR_SORT = 98.50, 3.816


def yard(daily):
    d = daily.sort_index()
    eq = np.concatenate([[0.0], d.values.cumsum()])
    dd = float((np.maximum.accumulate(eq) - eq).max())
    yrs = max((d.index[-1] - d.index[0]).days / 365.25, 1e-9)
    net = float(d.sum()); neg = np.minimum(d.values, 0.0); rms = float(np.sqrt(np.mean(neg ** 2)))
    return dict(net=net, dd=dd, years=yrs, roc30=30.0 * (net / yrs) / dd if dd > 0 else float("nan"),
                sortino=float(d.values.mean() / rms * np.sqrt(252)) if rms > 0 else float("nan"))


def dd_days(book_daily):
    d = book_daily.sort_index(); eq = d.values.cumsum(); days = []; peak, peak_i, j, n = 0.0, -1, 0, len(eq)
    while j < n:
        if eq[j] >= peak:
            peak, peak_i = eq[j], j; j += 1; continue
        k = j
        while k < n and eq[k] < peak:
            k += 1
        t = j + int(np.argmin(eq[j:k]))
        if peak - eq[t] >= DD_EPISODE:
            days.extend(d.index[peak_i + 1: t + 1])
        j = k
    return pd.DatetimeIndex(days)


def switches(root):
    out = []
    with open(os.path.join(SHARED, "tools", "data", "rolls_%s.csv" % root), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kind") == "not_a_roll" or not (r.get("old") and r.get("new")):
                continue
            out.append(int(r["switch_sec"]))
    return np.array(sorted(out), dtype=np.int64)


def sessions(adj_c, raw_c, idx):
    """Eligible sessions (all 78 RTH bars): adjusted + raw close of the 15:50 and 15:55 bars, 16:00 epoch seconds."""
    et = idx.tz_convert("US/Eastern"); keep = et < CUT
    et, a, r = et[keep], adj_c[keep], raw_c[keep]
    mins = et.hour * 60 + et.minute; rth = (mins >= 570) & (mins <= 955)
    df = pd.DataFrame({"date": et[rth].normalize().tz_localize(None), "m": mins[rth], "a": a[rth], "r": r[rth]})
    rows = []
    for D, s in df.groupby("date"):
        if not (len(s) == 78 and s["m"].nunique() == 78):
            continue
        s = s.set_index("m")
        rows.append(dict(date=D, a1550=s.at[950, "a"], a1555=s.at[955, "a"], r1555=s.at[955, "r"],
                         t16=int(pd.Timestamp(D).tz_localize("US/Eastern").value // 10**9) + 16 * 3600))
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def build(S, sw):
    """Per session t: R (cash close t-1 -> 15:55 t), the next-session exit, switches crossed; NaN where not tradeable."""
    S = S.copy()
    gap_prev = (S["date"] - S["date"].shift(1)).dt.days
    gap_next = (S["date"].shift(-1) - S["date"]).dt.days
    S["R"] = np.where(gap_prev <= 4, S["a1550"] - S["a1555"].shift(1), np.nan)          # points (addendum 1)
    S["ret"] = np.where(gap_prev <= 4, S["a1555"] - S["a1555"].shift(1), np.nan)        # daily point change, 16:00 to 16:00
    S["scale"] = S["R"].abs().rolling(60, min_periods=40).median().shift(1)
    S["exit_a"] = np.where(gap_next <= 4, S["a1555"].shift(-1), np.nan)
    S["exit_date"] = S["date"].shift(-1)
    t_next = S["t16"].shift(-1).fillna(0).astype(np.int64).values
    S["rolls"] = [int(((sw > a) & (sw <= b)).sum()) for a, b in zip(S["t16"].values, t_next)]
    return S


def lean_series(S_es):
    """k_t from ES: 20-session std of daily POINT changes of the 16:00 closes / its median over the previous 252, clipped."""
    v20 = S_es["ret"].rolling(20, min_periods=20).std()
    med = v20.rolling(252, min_periods=126).median().shift(1)
    k = (v20 / med).clip(0.5, 2.0)                          # v20 at t uses returns through t's close = prior close for t+1
    return pd.Series(k.shift(1).values, index=S_es["date"].values)   # known at the PRIOR close


def cell(S, mkt, filt, lean, k_es, side=None, stress=False):
    R = S["R"].values; sc = S["scale"].values
    ok = np.isfinite(R) & np.isfinite(sc) & np.isfinite(S["exit_a"].values) & (R != 0)
    if filt == "m1":
        ok &= np.abs(R) >= sc
    k = np.ones(len(S)) if lean == "F" else k_es.reindex(S["date"].values).values
    ok &= np.isfinite(k)
    sd = -np.sign(R) if side is None else side
    mpp = MULT[mkt] / 10.0                                                   # MNQ $2 / MES $5 a point
    n = np.maximum(1.0, np.floor(NOTIONAL * np.nan_to_num(k) / (S["r1555"].values * mpp) + 0.5))   # whole micros, nearest
    pts = sd * (S["exit_a"].values - S["a1555"].values)
    cost = n * ((COST[mkt] + (STRESS if stress else 0.0) + ROLL_PT * S["rolls"].values) * mpp + MICRO_COMM_RT)
    pnl = pts * mpp * n - cost
    return ok, np.nan_to_num(pnl)


def stats(S, ok, pnl, tdays, a, b, bdd=None):
    d = pd.DatetimeIndex(S["exit_date"].values); w = ok & (d >= a) & (d <= b)
    p = pnl[w]; out = dict(n=int(w.sum()))
    if out["n"] < 2:
        return out, pd.Series(dtype=float)
    daily = pd.Series(p, index=d[w]).groupby(level=0).sum().reindex(tdays[(tdays >= a) & (tdays <= b)], fill_value=0.0)
    out.update(yard(daily))
    gl = -p[p < 0].sum(); out["pf"] = float(p[p > 0].sum() / gl) if gl > 0 else float("inf")
    out["t"] = float(p.mean() / p.std(ddof=1) * np.sqrt(len(p))) if p.std(ddof=1) > 0 else 0.0
    out["ex_top_day"] = float(daily.sum() - daily.max())
    out["per_trade"] = float(p.mean())
    yrs = [(a + pd.DateOffset(years=i), a + pd.DateOffset(years=i + 1)) for i in range(9)]
    out["years_pos"] = int(sum(daily[(daily.index >= y0) & (daily.index < y1)].sum() > 0 for y0, y1 in yrs))
    out["net_ex_2020"] = float(daily[(daily.index < "2020-02-15") | (daily.index > "2020-04-30")].sum())
    if bdd is not None:
        x = daily.reindex(bdd).fillna(0.0)
        out["dd_sum"] = float(x.sum()); out["dd_ex3"] = float(x.sum() - np.sort(x.values)[::-1][:3].clip(min=0).sum())
    return out, daily


def run(M):
    """M: {mkt: (S, tdays)}; M['ES'] supplies the lean."""
    bk = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    bwf = bk[(bk.index >= WF[0]) & (bk.index <= WF[1])]
    base = yard(bwf["mtm"])
    print("#463 WF: ROC@30k %.2f  Sortino %.3f  DD $%s  (must be 93.81 / 3.816 / $44,849)"
          % (base["roc30"], base["sortino"], f"{base['dd']:,.0f}"))
    if not (abs(base["roc30"] - 93.81) < 0.01 and abs(base["sortino"] - 3.816) < 0.001 and abs(base["dd"] - 44849) < 1):
        sys.exit("STOP: #463 does not reproduce - nothing runs")
    bdd = dd_days(bwf["mtm"]); print("#463 WF drawdown days: %d" % len(bdd))
    k_es = lean_series(M["ES"][0])
    res, dly = {}, {}
    for mkt, f, l in CELLS:
        S, td = M[mkt]; key = "%s-%s-%s" % (mkt, f, l)
        ok, pnl = cell(S, mkt, f, l, k_es)
        w, dw = stats(S, ok, pnl, td, *WF, bdd=bdd)
        e, _ = stats(S, ok, pnl, td, pd.Timestamp("2000-01-01"), EARLY_END)
        oks, pnls = cell(S, mkt, f, l, k_es, stress=True); ws, _ = stats(S, oks, pnls, td, *WF)
        sides = {}
        for nm, sel in (("long", S["R"].values < 0), ("short", S["R"].values > 0)):
            sides[nm] = stats(S, ok & sel, pnl, td, *WF)[0].get("net", 0.0)
        corr = {c: float(np.corrcoef(dw.reindex(bwf.index, fill_value=0.0), bwf[c])[0, 1])
                for c in ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm", "mtm")} if len(dw) else {}
        res[key] = dict(wf=w, early=e, wf_stress=ws, sides=sides, corr=corr); dly[key] = dw
    rng = np.random.default_rng(SEED); mt, md = [], []
    for _ in range(NULL_REPS):
        bt, bd = -np.inf, -np.inf
        for mkt in ("NQ", "ES"):
            S, td = M[mkt]; coin = rng.choice([-1.0, 1.0], size=len(S))
            for f in ("m0", "m1"):
                for l in ("F", "S"):
                    ok, pnl = cell(S, mkt, f, l, k_es, side=coin)
                    w, _ = stats(S, ok, pnl, td, *WF, bdd=bdd)
                    bt = max(bt, w.get("t", -np.inf)); bd = max(bd, w.get("dd_sum", -np.inf))
        mt.append(bt); md.append(bd)
    nt95, nd95 = float(np.percentile(mt, 95)), float(np.percentile(md, 95))
    passes = []
    for key, v in res.items():
        w, e, ws = v["wf"], v["early"], v["wf_stress"]
        mkt, f, l = key.split("-")
        twin = res["%s-%s-F" % (mkt, f)]["wf"]
        chk = {"a n>=100": w.get("n", 0) >= 100, "b ROC>=5": w.get("roc30", -1) >= 5, "c PF>=1.05": w.get("pf", 0) >= 1.05,
               "d t>=2 & >null": w.get("t", 0) >= 2 and w.get("t", 0) > nt95, "e stress>0": ws.get("net", -1) > 0,
               "f ex-top-day>0": w.get("ex_top_day", -1) > 0, "g 6/9 yrs": w.get("years_pos", 0) >= 6,
               "h DD-days>0, ex3>0, >null": w.get("dd_sum", -1) > 0 and w.get("dd_ex3", -1) > 0 and w.get("dd_sum", -1) > nd95,
               "i ex 2020 crash>0": w.get("net_ex_2020", -1) > 0, "j EARLY>0": e.get("net", -1) > 0,
               "k S beats F twin": l == "F" or (w.get("roc30", -1) > twin.get("roc30", 0) and w.get("sortino", -1) > twin.get("sortino", 0))}
        v["checks"] = chk; v["pass"] = all(chk.values())
        if v["pass"]:
            passes.append(key)

    def add(key, c):
        leg = dly[key]; return yard(pd.concat([bwf["mtm"] + c * leg.reindex(bwf.index, fill_value=0.0),
                                               c * leg[~leg.index.isin(bwf.index)]]).sort_index())
    if passes:
        top = max(passes, key=lambda k: res[k]["wf"]["roc30"]); tries = {c: add(top, c) for c in (0.5, 1, 2)}
        c = max(tries, key=lambda k: tries[k]["roc30"])
        a2 = dict(cell=top, c=c, tries=tries, passed=tries[c]["roc30"] >= BOOK_BAR_ROC and tries[c]["sortino"] >= BOOK_BAR_SORT)
    else:
        a2 = dict(report_only={k: add(k, 1) for k in ("NQ-m0-F", "ES-m0-F")})
    return dict(base=base, dd_days=len(bdd), null_t95=nt95, null_dd95=nd95, cells=res, passes=passes, a2=a2)


def report(R):
    print("null 95th pct: max t %.2f | max drawdown-day sum $%s" % (R["null_t95"], f"{R['null_dd95']:,.0f}"))
    for key, v in R["cells"].items():
        w = v["wf"]
        if w.get("n", 0) < 2:
            print("  %-9s too few trades" % key); continue
        print("  %-9s n %4d $/tr %6.1f ROC@30k %6.1f Sort %5.2f PF %4.2f t %5.2f yrs+ %d DDdays $%9s (ex3 $%9s) long $%9s"
              " short $%9s EARLY $%9s %s" % (key, w["n"], w["per_trade"], w["roc30"], w["sortino"], w["pf"], w["t"],
              w["years_pos"], f"{w['dd_sum']:,.0f}", f"{w['dd_ex3']:,.0f}", f"{v['sides']['long']:,.0f}",
              f"{v['sides']['short']:,.0f}", f"{v['early'].get('net', 0):,.0f}", "PASS" if v["pass"] else
              "fails " + ",".join(k.split()[0] for k, ok in v["checks"].items() if not ok)))
    print("Stage A passes:", R["passes"] or "none"); print("Stage A2:", json.dumps(R["a2"], default=float)[:900])


def selftest():
    global BOOK, WF, EARLY_END, NULL_REPS
    rng = np.random.default_rng(2)
    b = pd.Series([10000, -20000, 5000, 30000, -16000, 1000], index=pd.date_range("2020-01-01", periods=6), dtype=float)
    assert list(dd_days(b).strftime("%m-%d")) == ["01-02", "01-05"]
    idx = pd.date_range("2013-01-01", "2016-12-31 23:55", freq="5min", tz="US/Eastern"); idx = idx[idx.dayofweek < 5]
    M = {}
    for mkt, lvl in (("NQ", 4000.0), ("ES", 2000.0)):
        raw = lvl + np.cumsum(rng.normal(0, 0.4, len(idx))); adj = raw + 3000.0     # back-adjust shift: a level is not a price
        S = build(sessions(adj, raw, idx), np.array([], dtype=np.int64))
        S0 = build(sessions(raw, raw, idx), np.array([], dtype=np.int64))
        assert len(S) > 900 and np.allclose(S["R"], S0["R"], equal_nan=True), "R must be shift-invariant (points)"
        assert np.allclose(lean_series(S).values, lean_series(S0).values, equal_nan=True), "k must be shift-invariant"
        M[mkt] = (S, pd.DatetimeIndex(S["date"]))
    bk = pd.DataFrame({"date": pd.date_range("2013-01-01", "2016-12-31", freq="B")})
    for c in ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm"):
        bk[c] = rng.normal(40, 500, len(bk))
    bk["mtm"] = bk[["L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm"]].sum(axis=1)
    d = os.path.join(os.environ.get("TEMP", "."), "ddw2_selftest"); os.makedirs(d, exist_ok=True)
    BOOK = os.path.join(d, "book.csv"); bk.to_csv(BOOK, index=False)
    WF = (pd.Timestamp("2015-01-01"), pd.Timestamp("2016-12-30")); EARLY_END = pd.Timestamp("2014-12-31"); NULL_REPS = 5
    real = sys.exit; sys.exit = lambda msg=None: print("  (selftest: reproduction gate skipped)")
    try:
        R = run(M)
    finally:
        sys.exit = real
    report(R); print("SELFTEST OK - synthetic only, no real data read")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(); sys.exit(0)
    os.chdir(SHARED); sys.path.insert(0, SHARED)
    from augur_engine.data import find_master, load_master_arrays
    M = {}
    for mkt in ("NQ", "ES"):
        A = load_master_arrays(find_master(mkt, "5m", "rth", "db_adj_rth"), date_to="2025-06-29")
        B = load_master_arrays(find_master(mkt, "5m", "rth", "db_noadj_rth"), date_to="2025-06-29")
        ia, ib = pd.DatetimeIndex(A["index"]), pd.DatetimeIndex(B["index"])
        raw = pd.Series(np.asarray(B["close"], float), index=ib).reindex(ia).values
        S = build(sessions(np.asarray(A["close"], float), raw, ia), switches(mkt))
        S = S[np.isfinite(S["r1555"])].reset_index(drop=True)
        print("%s: %d eligible sessions" % (mkt, len(S))); M[mkt] = (S, pd.DatetimeIndex(S["date"]))
    R = run(M); report(R)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "stage_a.json"), "w") as f:
        json.dump(R, f, default=float, indent=1)
    print("written", OUT)
