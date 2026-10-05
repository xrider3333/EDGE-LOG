"""
DD-WEEK r1 (pre-registered in docs/DDWEEK_OVERNIGHT_R1.md before this file was written): long NQ / ES at the 16:00 ET
close after a DOWN cash session, out at 03:30 ET (E1) or the 09:30 open (E2) of the next trading day, as a leg that
earns while BOOK #463 falls. Stage A (screen) + Stage A2 (book add) on the walk-forward ONLY; nothing here reads the
lockbox - every master array is cut before 2025-06-30 00:00 ET before a signal exists.

    python tools/ddw1_overnight.py --selftest     # synthetic bars only: exercises every code path, no real data
    python tools/ddw1_overnight.py                # the pre-registered run (writes C:\\EdgeLog\\_anatomy_cache\\ddweek\\r1)

Written by TV (2026-10-04), handed to STRATEGY-BEATING (MANAGER #43) and run under its name. Pre-data addendum 2 of the prereg (2026-10-05) changes
these things here, before any number (items 1-5 of the addendum): the run refuses unless docs/DDWEEK_OVERNIGHT_R1.md is the registered text (PREREG_SHA, stamped into
stage_a.json with this file's own sha); #463's drawdown days must be MDL r1's 460 (the house count; a different episode rule stops the run); and
A2's c is set by VOLATILITY, never picked on returns - c = 25% x std(#463's daily P&L, 2016-07-01 .. 2018-06-29) / std(the cell's daily P&L at
one contract on the same days), rounded to whole micros (0.1 contract, at least one micro); the book at 0.5c and 2c is reported, never judged;
r is read in POINTS (close of the 15:50 bar - open of the 09:30 bar; the scale is the median |r| in points), shift-invariant on the back-adjusted
master; and no night is skipped for what comes after its entry - the exit is the first bar at or after the target on or after the next date with
RTH bars, however late (late fills and nights across a weekday without RTH bars are counted and reported).
"""
import csv, hashlib, json, os, sys
import numpy as np, pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
OUT = r"C:\EdgeLog\_anatomy_cache\ddweek\r1"
BOOK = r"C:\EdgeLog\_anatomy_cache\rocfrontier\r4\book463_daily.csv"
CUT = pd.Timestamp("2025-06-30 00:00", tz="US/Eastern")          # nothing at or after this exists for the harness
EARLY_END = pd.Timestamp("2016-06-30")
WF = (pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"))
MULT = {"NQ": 20.0, "ES": 50.0}
COST = {"NQ": 0.533, "ES": 0.363}
STRESS, ROLL_PT = 0.25, 0.25
KS = {"S0": None, "S1": 1.0, "S2": 2.0}
EXITS = {"E1": (3, 30), "E2": (9, 30)}
DD_EPISODE = 14950.0
NULL_REPS, SEED = 500, 20261004
BOOK_BAR_ROC, BOOK_BAR_SORT = 98.50, 3.816
PREREG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "DDWEEK_OVERNIGHT_R1.md")
PREREG_SHA = "645d46b7a14d890909450164931662961036e83974598fae58826be5f504b825"   # LF sha256 of the prereg with pre-data addendum 2 (2026-10-05)
DD_DAYS_REF = 460                                              # MDL r1: #463's WF qualifying drawdown days (28 episodes) - addendum 2's gate
A2_WIN, A2_TARGET, A2_REPORT, MICRO = (pd.Timestamp("2016-07-01"), pd.Timestamp("2018-06-29")), 0.25, (0.5, 2.0), 0.1


def sha_lf(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def prereg_ok():
    """the frozen spec must be the registered one: a missing or changed docs/DDWEEK_OVERNIGHT_R1.md stops the run (nothing computed)"""
    if not os.path.exists(PREREG):
        sys.exit("STOP: docs/DDWEEK_OVERNIGHT_R1.md is not in this checkout - the spec cannot be verified (nothing computed)")
    if sha_lf(PREREG) != PREREG_SHA:
        sys.exit("STOP: docs/DDWEEK_OVERNIGHT_R1.md DIFFERS from the registered text (addendum 2) - nothing computed")
    print("prereg check: docs/DDWEEK_OVERNIGHT_R1.md sha256 matches the registered one")
    return True


# ----------------------------------------------------------------------------------------------------- yardstick
def yard(daily):
    """daily: pd.Series of $ indexed by date (zeros included). ROC %/yr at a $30k worst drawdown + Sortino."""
    d = daily.sort_index()
    eq = np.concatenate([[0.0], d.values.cumsum()])
    dd = float((np.maximum.accumulate(eq) - eq).max())
    yrs = max((d.index[-1] - d.index[0]).days / 365.25, 1e-9)
    net = float(d.sum())
    neg = np.minimum(d.values, 0.0)
    rms = float(np.sqrt(np.mean(neg ** 2)))
    return dict(net=net, dd=dd, years=yrs, roc30=30.0 * (net / yrs) / dd if dd > 0 else float("nan"),
                sortino=float(d.values.mean() / rms * np.sqrt(252)) if rms > 0 else float("nan"))


def dd_days(book_daily):
    """#463 drawdown days: the days after each running peak through the trough of every episode >= $14,950 deep."""
    d = book_daily.sort_index()
    eq = d.values.cumsum()
    days, i, n = [], 0, len(eq)
    peak_i = -1; peak = 0.0                                   # equity starts at 0 before the first day
    j = 0
    while j < n:
        if eq[j] >= peak:
            peak, peak_i = eq[j], j; j += 1; continue
        k = j                                                 # inside an episode: run to the next new high
        while k < n and eq[k] < peak:
            k += 1
        seg = eq[j:k]; t = j + int(np.argmin(seg))
        if peak - eq[t] >= DD_EPISODE:
            days.extend(d.index[peak_i + 1: t + 1])
        j = k
    return pd.DatetimeIndex(days)


# ----------------------------------------------------------------------------------------------------- data
def switches(root):
    out = []
    with open(os.path.join(SHARED, "tools", "data", "rolls_%s.csv" % root), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kind") == "not_a_roll" or not (r.get("old") and r.get("new")):
                continue
            out.append(int(r["switch_sec"]))
    return np.array(sorted(out), dtype=np.int64)


def nights(o, c, idx, sw):
    """One row per eligible RTH session D: r, entry px (close of the 15:55 bar), exit px + date for E1 / E2."""
    et = idx.tz_convert("US/Eastern")
    keep = et < CUT
    o, c, et = o[keep], c[keep], et[keep]
    date = et.normalize().tz_localize(None)
    mins = et.hour * 60 + et.minute
    rth = (mins >= 570) & (mins <= 955)
    sess = pd.DataFrame({"date": date[rth], "m": mins[rth], "o": o[rth], "c": c[rth]})
    tdays = np.array(sorted(sess["date"].unique()))           # every date with RTH bars = trading days
    secs = (et.tz_convert("UTC").asi8 // 10**9).astype(np.int64)
    rows = []
    for D, s in sess.groupby("date"):
        if not (len(s) == 78 and s["m"].nunique() == 78 and s["m"].min() == 570 and s["m"].max() == 955):
            continue                                          # early close / gappy session
        s = s.set_index("m")
        r = s.at[950, "c"] - s.at[570, "o"]                   # addendum 2: POINTS - close of the 15:50 bar - open of the 09:30 bar
        ent = s.at[955, "c"]
        nxt = tdays[np.searchsorted(tdays, D, side="right")] if np.searchsorted(tdays, D, side="right") < len(tdays) else None
        row = dict(date=D, r=r, ent=ent)
        ent_sec = int(pd.Timestamp(D).tz_localize("US/Eastern").value // 10**9) + 16 * 3600
        for ek, (hh, mm) in EXITS.items():
            row[ek + "_px"] = np.nan; row[ek + "_date"] = pd.NaT; row[ek + "_roll"] = 0; row[ek + "_late"] = 0; row[ek + "_gap"] = 0
            if nxt is None:
                continue                                      # no later session inside the cut: nothing to book
            tgt = pd.Timestamp(nxt).tz_localize("US/Eastern") + pd.Timedelta(hours=hh, minutes=mm)
            p = et.searchsorted(tgt)
            if p >= len(et):
                continue                                      # the exit lies beyond the cut
            # addendum 2: never skipped for what comes after the entry - the first bar at or after the target, however late
            xd = et[p].normalize().tz_localize(None)
            row[ek + "_px"] = o[p]; row[ek + "_date"] = xd
            row[ek + "_late"] = int(xd != pd.Timestamp(nxt) or (et[p] - tgt) > pd.Timedelta(minutes=30))
            row[ek + "_gap"] = int(np.busday_count(pd.Timestamp(D).date(), pd.Timestamp(nxt).date()) > 1)   # a weekday without RTH bars
            row[ek + "_roll"] = int(((sw > ent_sec) & (sw <= secs[p])).sum())
        rows.append(row)
    N = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    N["scale"] = N["r"].abs().rolling(60, min_periods=40).median().shift(1)   # previous 60 eligible sessions
    return N, pd.DatetimeIndex(tdays)


def cell_trades(N, mkt, sk, ek, r=None, scale=None, stress=False):
    r = N["r"].values if r is None else r
    scale = N["scale"].values if scale is None else scale
    k = KS[sk]
    sel = (r < 0) if k is None else (np.isfinite(scale) & (r <= -k * scale))
    if k is None:
        sel &= np.isfinite(scale)                              # same warm-up rule for every cell
    sel &= np.isfinite(N[ek + "_px"].values)
    cost = COST[mkt] + (STRESS if stress else 0.0)
    pnl = ((N[ek + "_px"].values - N["ent"].values) - cost - ROLL_PT * N[ek + "_roll"].values) * MULT[mkt]
    return sel, pnl


def daily_of(dates, pnl, tdays, a, b):
    s = pd.Series(pnl, index=pd.DatetimeIndex(dates)).groupby(level=0).sum()
    ix = tdays[(tdays >= a) & (tdays <= b)]
    return s.reindex(ix, fill_value=0.0).astype(float)


def stats(N, sel, pnl, ek, tdays, a, b, book_dd=None):
    dts = pd.DatetimeIndex(N[ek + "_date"].values)
    inwin = sel & (dts >= a) & (dts <= b)
    p = pnl[inwin]; d = dts[inwin]
    out = dict(n=int(inwin.sum()))
    if out["n"] == 0:
        return out, pd.Series(dtype=float)
    daily = daily_of(d, p, tdays, a, b)
    out.update(yard(daily))
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    out["pf"] = float(gw / gl) if gl > 0 else float("inf")
    out["t"] = float(p.mean() / p.std(ddof=1) * np.sqrt(len(p))) if len(p) > 1 and p.std(ddof=1) > 0 else 0.0
    out["ex_top"] = float(p.sum() - p.max())
    out["per_trade"] = float(p.mean())
    yrs = [(a + pd.DateOffset(years=i), a + pd.DateOffset(years=i + 1)) for i in range(9)]
    out["years_pos"] = int(sum(daily[(daily.index >= y0) & (daily.index < y1)].sum() > 0 for y0, y1 in yrs))
    ex20 = daily[(daily.index < "2020-02-01") | (daily.index > "2020-04-30")]
    out["net_ex_2020q1"] = float(ex20.sum())
    if book_dd is not None:
        in_dd = daily.reindex(book_dd).fillna(0.0)
        out["dd_week_net"] = float(in_dd.sum())
        out["dd_week_ex3"] = float(in_dd.sum() - np.sort(in_dd.values)[::-1][:3].clip(min=0).sum())
        mar20 = daily[(daily.index >= "2020-03-02") & (daily.index <= "2020-03-27")]
        out["mar2020"] = float(mar20.sum())
    return out, daily


# ----------------------------------------------------------------------------------------------------- run
def run(markets):
    """markets: {mkt: (N, tdays)}. Returns the Stage A table, the null and Stage A2."""
    bk = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    bwf = bk[(bk.index >= WF[0]) & (bk.index <= WF[1])]
    base = yard(bwf["mtm"])
    print("#463 WF on this convention: ROC@30k %.2f  Sortino %.3f  DD $%s  (must be 93.81 / 3.816 / $44,849)"
          % (base["roc30"], base["sortino"], f"{base['dd']:,.0f}"))
    if not (abs(base["roc30"] - 93.81) < 0.01 and abs(base["sortino"] - 3.816) < 0.001 and abs(base["dd"] - 44849) < 1):
        sys.exit("STOP: #463 does not reproduce - nothing runs")
    bdd = dd_days(bwf["mtm"])
    print("#463 WF drawdown days (episodes >= $%s): %d days (MDL r1: %d)" % (f"{DD_EPISODE:,.0f}", len(bdd), DD_DAYS_REF))
    if len(bdd) != DD_DAYS_REF:
        sys.exit("STOP: #463's drawdown days are not MDL r1's %d - the episode rule differs; nothing runs (addendum 2)" % DD_DAYS_REF)
    res, dailies = {}, {}
    for mkt, (N, tdays) in markets.items():
        for ek in EXITS:
            for sk in KS:
                sel, pnl = cell_trades(N, mkt, sk, ek)
                w, dw = stats(N, sel, pnl, ek, tdays, *WF, book_dd=bdd)
                e, _ = stats(N, sel, pnl, ek, tdays, pd.Timestamp("2000-01-01"), EARLY_END)
                sel_s, pnl_s = cell_trades(N, mkt, sk, ek, stress=True)
                ws, _ = stats(N, sel_s, pnl_s, ek, tdays, *WF)
                key = "%s-%s-%s" % (mkt, ek, sk)
                corr = {c: float(np.corrcoef(dw.reindex(bwf.index, fill_value=0.0), bwf[c])[0, 1])
                        for c in ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm", "mtm")} if len(dw) else {}
                dts_ = pd.DatetimeIndex(N[ek + "_date"].values)
                inw_ = sel & (dts_ >= WF[0]) & (dts_ <= WF[1])
                late_, gap_ = inw_ & (N[ek + "_late"].values == 1), inw_ & (N[ek + "_gap"].values == 1)
                odd = dict(late_n=int(late_.sum()), late_pnl=float(pnl[late_].sum()), gap_n=int(gap_.sum()), gap_pnl=float(pnl[gap_].sum()))
                res[key] = dict(wf=w, early=e, wf_stress=ws, corr=corr, odd_exits=odd)
                dailies[key] = dw
    # family-wide null: shuffle r within market across eligible WF sessions, max |t| over all 12 cells
    rng = np.random.default_rng(SEED); mx = []
    for _ in range(NULL_REPS):
        best = -np.inf
        for mkt, (N, tdays) in markets.items():
            r = N["r"].values.copy()
            wfm = ((N["date"] >= WF[0]) & (N["date"] <= WF[1])).values
            r[wfm] = rng.permutation(r[wfm])
            sc = pd.Series(np.abs(r)).rolling(60, min_periods=40).median().shift(1).values
            for ek in EXITS:
                for sk in KS:
                    sel, pnl = cell_trades(N, mkt, sk, ek, r=r, scale=sc)
                    w, _ = stats(N, sel, pnl, ek, tdays, *WF)
                    best = max(best, w.get("t", 0.0))
        mx.append(best)
    null95 = float(np.percentile(mx, 95))
    passes = []
    for key, v in res.items():
        w, e, ws = v["wf"], v["early"], v["wf_stress"]
        chk = {"a n>=100": w.get("n", 0) >= 100, "b ROC>=5": w.get("roc30", -1) >= 5.0, "c PF>=1.10": w.get("pf", 0) >= 1.10,
               "d t>=2 & >null95": w.get("t", 0) >= 2.0 and w.get("t", 0) > null95, "e stress>0": ws.get("net", -1) > 0,
               "f ex-top>0": w.get("ex_top", -1) > 0, "g 6/9 yrs": w.get("years_pos", 0) >= 6,
               "h DD-week>0 (and ex-3)": w.get("dd_week_net", -1) > 0 and w.get("dd_week_ex3", -1) > 0,
               "i ex Feb-Apr 2020>0": w.get("net_ex_2020q1", -1) > 0, "j EARLY>0": e.get("net", -1) > 0}
        v["checks"] = chk; v["pass"] = all(chk.values())
        if v["pass"]:
            passes.append(key)
    # Stage A2
    def book_add(key, c):
        leg = dailies[key].reindex(bwf.index, fill_value=0.0)
        extra = dailies[key][~dailies[key].index.isin(bwf.index)]
        tot = pd.concat([bwf["mtm"] + c * leg, c * extra]).sort_index()
        return yard(tot)
    def vol_c(key):
        """addendum 2: c from volatility - 25% of #463's daily std over the first two WF years / the cell's (one contract) on the same days, in whole micros"""
        leg = dailies[key].reindex(bwf.index, fill_value=0.0) if len(dailies[key]) else pd.Series(0.0, index=bwf.index)
        w = (bwf.index >= A2_WIN[0]) & (bwf.index <= A2_WIN[1])
        sb, sc = float(np.std(bwf["mtm"].values[w], ddof=1)), float(np.std(leg.values[w], ddof=1))
        if not (sb > 0 and sc > 0):
            return dict(c=float("nan"), c_exact=float("nan"), std_book=sb, std_cell=sc, error="no spread over the window")
        ce = A2_TARGET * sb / sc
        return dict(c=max(MICRO, round(ce / MICRO) * MICRO), c_exact=ce, std_book=sb, std_cell=sc)

    def book_at(key, v):
        out = dict(v)
        if np.isfinite(v["c"]):
            out.update(book=book_add(key, v["c"]), at_half_c=book_add(key, max(MICRO, round(A2_REPORT[0] * v["c"] / MICRO) * MICRO)),
                       at_double_c=book_add(key, round(A2_REPORT[1] * v["c"] / MICRO) * MICRO))
        return out
    a2 = {}
    if passes:
        top = max(passes, key=lambda k: res[k]["wf"]["roc30"])
        a2 = dict(cell=top, **book_at(top, vol_c(top)))
        a2["pass_"] = bool("book" in a2 and a2["book"]["roc30"] >= BOOK_BAR_ROC and a2["book"]["sortino"] >= BOOK_BAR_SORT)
    else:
        a2 = dict(report_only={"%s-E1-S0" % m: book_at("%s-E1-S0" % m, vol_c("%s-E1-S0" % m)) for m in markets})
    return dict(base=base, dd_days=len(bdd), null95=null95, null_max=mx, cells=res, passes=passes, a2=a2)


def report(R):
    print("null: max WF t over 12 cells, 95th pct = %.2f" % R["null95"])
    for key, v in R["cells"].items():
        w = v["wf"]
        if not w.get("n"):
            print("  %-10s no trades" % key); continue
        print("  %-10s n %4d  $/tr %6.1f  ROC@30k %6.1f  Sort %5.2f  PF %4.2f  t %5.2f  yrs+ %d  DDwk $%9s (ex3 $%9s)"
              "  Mar20 $%8s  EARLY $%9s  %s"
              % (key, w["n"], w["per_trade"], w["roc30"], w["sortino"], w["pf"], w["t"], w["years_pos"],
                 f"{w['dd_week_net']:,.0f}", f"{w['dd_week_ex3']:,.0f}", f"{w['mar2020']:,.0f}",
                 f"{v['early'].get('net', 0):,.0f}", "PASS" if v["pass"] else
                 "fails " + ", ".join(k.split()[0] for k, ok in v["checks"].items() if not ok)))
    for k, v in R["cells"].items():
        o_ = v.get("odd_exits") or {}
        if o_.get("late_n") or o_.get("gap_n"):
            print("  %-10s odd exits (addendum 2): late %d ($%s); across a weekday without RTH bars %d ($%s)"
                  % (k, o_["late_n"], f"{o_['late_pnl']:,.0f}", o_["gap_n"], f"{o_['gap_pnl']:,.0f}"))
    print("Stage A passes:", R["passes"] or "none")
    print("Stage A2:", json.dumps(R["a2"], default=float)[:900])


def selftest():
    """Synthetic 5m ETH bars for two markets, three years; checks the yardstick, episodes, nights and the run."""
    global BOOK, WF, EARLY_END, CUT, NULL_REPS, A2_WIN
    rng = np.random.default_rng(1)
    d = pd.Series([1.0, -2.0, 0.0, 3.0], index=pd.date_range("2020-01-01", periods=4))
    y = yard(d); assert abs(y["net"] - 2.0) < 1e-9 and abs(y["dd"] - 2.0) < 1e-9, y
    b = pd.Series([10000, -20000, 5000, 30000, -16000, 1000], index=pd.date_range("2020-01-01", periods=6), dtype=float)
    days = dd_days(b); assert list(days.strftime("%m-%d")) == ["01-02", "01-05"], days   # episode1 20k (days 2), ep2 16k (5)
    idx = pd.date_range("2014-01-01", "2016-12-31 23:55", freq="5min", tz="US/Eastern")
    idx = idx[idx.dayofweek < 5]
    px = 2000 + np.cumsum(rng.normal(0, 0.5, len(idx)))
    markets = {}
    for mkt in ("NQ", "ES"):
        N, td = nights(px.copy(), px.copy(), idx, np.array([], dtype=np.int64))
        assert len(N) > 500 and N["E1_px"].notna().mean() > 0.95, (len(N), N["E1_px"].notna().mean())
        markets[mkt] = (N, td)
    # addendum 2: r is in points; a hole (4 weekdays) and a missing 03:00-04:55 stretch never skip the night before them
    N0 = markets["NQ"][0]
    one = N0.iloc[100]
    m_ = idx.normalize().tz_localize(None) == one["date"]
    o930 = px[m_ & (idx.hour == 9) & (idx.minute == 30)][0]
    c1550 = px[m_ & (idx.hour == 15) & (idx.minute == 50)][0]
    assert abs(one["r"] - (c1550 - o930)) < 1e-9, (one["r"], c1550 - o930)
    dn = idx.normalize().tz_localize(None)
    holes = dn.isin(pd.to_datetime(["2015-03-11", "2015-03-12", "2015-03-13", "2015-03-16"]))
    late_bars = (dn == pd.Timestamp("2015-03-17")) & (idx.hour >= 3) & (idx.hour < 5)
    keep_ = ~(holes | late_bars)
    Nh, _ = nights(px[keep_].copy(), px[keep_].copy(), idx[keep_], np.array([], dtype=np.int64))
    nb = Nh[Nh["date"] == pd.Timestamp("2015-03-10")].iloc[0]
    want = px[(dn == pd.Timestamp("2015-03-17")) & (idx.hour == 5) & (idx.minute == 0)][0]
    assert nb["E1_date"] == pd.Timestamp("2015-03-17") and nb["E1_late"] == 1 and nb["E1_gap"] == 1 and abs(nb["E1_px"] - want) < 1e-12, nb
    assert nb["E2_date"] == pd.Timestamp("2015-03-17") and nb["E2_late"] == 0 and nb["E2_gap"] == 1, nb
    plain = Nh[Nh["date"] == pd.Timestamp("2015-03-03")].iloc[0]
    assert plain["E1_late"] == 0 and plain["E1_gap"] == 0 and plain["E1_date"] == pd.Timestamp("2015-03-04"), plain
    print("addendum 2 proofs: r in points; the night before a 4-weekday hole exits on 2015-03-17 05:00 (late 1, gap 1), not skipped")
    bk = pd.DataFrame({"date": pd.date_range("2014-01-01", "2016-12-31", freq="B")})
    for c in ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm"):
        bk[c] = rng.normal(30, 400, len(bk))
    bk["mtm"] = bk[["L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm"]].sum(axis=1)
    os.makedirs(os.path.join(os.environ.get("TEMP", "."), "ddw1_selftest"), exist_ok=True)
    BOOK = os.path.join(os.environ.get("TEMP", "."), "ddw1_selftest", "book.csv"); bk.to_csv(BOOK, index=False)
    WF = (pd.Timestamp("2015-07-01"), pd.Timestamp("2016-12-30")); EARLY_END = pd.Timestamp("2015-06-30"); NULL_REPS = 5
    A2_WIN = (pd.Timestamp("2015-07-01"), pd.Timestamp("2016-06-30"))
    real_exit = sys.exit
    sys.exit = lambda msg=None: print("  (selftest: reproduction gate skipped)")
    try:
        R = run(markets)
    finally:
        sys.exit = real_exit
    report(R)
    # addendum 2: the volatility-set c makes the cell's std over the window exactly 25% of the book's (before rounding to micros)
    bk2 = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    key0 = next(iter(R["cells"]))
    v = (R["a2"].get("report_only") or {}).get("NQ-E1-S0") or R["a2"]
    assert v.get("std_cell", 0) > 0 and abs(v["c_exact"] * v["std_cell"] / v["std_book"] - 0.25) < 1e-12 and abs(v["c"] * 10 - round(v["c"] * 10)) < 1e-9, v
    print("A2 proof: c_exact x the cell's std = %.12f of the book's; c in whole micros = %.1f" % (v["c_exact"] * v["std_cell"] / v["std_book"], v["c"]))
    print("SELFTEST OK - synthetic only, no real data read")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(); sys.exit(0)
    prereg_ok()
    here_sha = sha_lf(os.path.abspath(__file__))
    os.chdir(SHARED); sys.path.insert(0, SHARED)
    from augur_engine.data import find_master, load_master_arrays
    markets = {}
    for mkt in ("NQ", "ES"):
        A = load_master_arrays(find_master(mkt, "5m", "eth", "db_adj_eth"), date_to="2025-06-29")
        idx = pd.DatetimeIndex(A["index"])
        N, td = nights(np.asarray(A["open"], float), np.asarray(A["close"], float), idx, switches(mkt))
        print("%s: %d eligible sessions, E1 exits %d, E2 exits %d" % (mkt, len(N), N["E1_px"].notna().sum(), N["E2_px"].notna().sum()))
        markets[mkt] = (N, td)
    R = run(markets)
    report(R)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "stage_a.json"), "w") as f:
        json.dump({"prereg_sha256_lf": PREREG_SHA, "harness_sha256": here_sha, **{k: v for k, v in R.items() if k != "null_max"}}, f, default=float, indent=1)
    print("written", OUT)
