"""
TV NEW-TYPE round 1 (docs/TV_NEWTYPES_R1.md, pre-registered before this file ran): Stage A + A2 on the WALK-FORWARD ONLY for
PAIRS (fund-pair mean reversion), BAB (betting against beta, weekly) and ONMOM (overnight-component persistence). Every array is
cut before 2025-06-30 before any signal; the lockbox is never loaded.

P&L convention (stated, applied identically to every cell, control and null draw): a position's dollar notional is fixed when it
opens and its P&L per period = notional x the fund's return over that period (entry day open -> close, then close -> close, exit
day close -> open); costs = bps x notional at each fill; borrow 0.25 %/yr on short notional per calendar day held.

    python tools/tvnt1_triage.py --selftest          # synthetic prices only
    python tools/tvnt1_triage.py [PAIRS|BAB|ONMOM]    # the pre-registered run (all three by default)
"""
import hashlib, json, os, sys
import numpy as np, pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
CACHE = r"C:\EdgeLog\_research_cache"
OUT = r"C:\EdgeLog\_anatomy_cache\tv_newtypes_r1"
BOOK = r"C:\EdgeLog\_anatomy_cache\rocfrontier\r4\book463_daily.csv"
CUT = pd.Timestamp("2025-06-30")
EARLY = (pd.Timestamp("2007-03-01"), pd.Timestamp("2016-06-30"))
WF = (pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"))
EQUITY = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "QQQ", "IWM"]
OTHER = ["TLT", "IEF", "GLD", "SLV", "TIP", "DBC", "USO", "UUP", "FXA", "FXE", "FXY"]
CHEAP = set(["SPY", "QQQ", "IWM", "TLT", "IEF", "GLD"] + EQUITY[:9])
PAIRS = [("IEF", "TLT"), ("TIP", "IEF"), ("GLD", "SLV"), ("XLK", "QQQ"), ("XLE", "USO"), ("XLP", "XLU"), ("XLB", "XLI"),
         ("SPY", "IWM")]
BORROW = 0.0025 / 365.0
REPS, SEED, DD_EPISODE = 500, 20261005, 14950.0
BOOK_ROC, BOOK_SORT = 98.50, 3.816


def bps(t, stress):
    return (2.0 if t in CHEAP else 5.0) * (2.0 if stress else 1.0) / 1e4


# ------------------------------------------------------------------------------------------------ yardstick
def yard(daily):
    d = daily.sort_index(); eq = np.concatenate([[0.0], d.values.cumsum()])
    dd = float((np.maximum.accumulate(eq) - eq).max()); yrs = max((d.index[-1] - d.index[0]).days / 365.25, 1e-9)
    net = float(d.sum()); neg = np.minimum(d.values, 0.0); rms = float(np.sqrt(np.mean(neg ** 2)))
    return dict(net=net, dd=dd, roc30=30.0 * (net / yrs) / dd if dd > 0 else float("nan"),
                sortino=float(d.values.mean() / rms * np.sqrt(252)) if rms > 0 else float("nan"))


def dd_episodes(book_daily):
    """#463's drawdown episodes: each peak-to-trough run >= $14,950 deep, as its own DatetimeIndex."""
    d = book_daily.sort_index(); eq = d.values.cumsum(); out = []; peak, pi, j, n = 0.0, -1, 0, len(eq)
    while j < n:
        if eq[j] >= peak:
            peak, pi = eq[j], j; j += 1; continue
        k = j
        while k < n and eq[k] < peak:
            k += 1
        t = j + int(np.argmin(eq[j:k]))
        if peak - eq[t] >= DD_EPISODE:
            out.append(d.index[pi + 1: t + 1])
        j = k
    return out


def dd_days(book_daily):
    eps = dd_episodes(book_daily)
    return pd.DatetimeIndex(np.concatenate([e.values for e in eps])) if eps else pd.DatetimeIndex([])


def july_years(a):
    return [(a + pd.DateOffset(years=i), a + pd.DateOffset(years=i + 1)) for i in range(9)]


def vol_c(bwf, daily):
    """Addendum 2: c = 0.25 x #463's daily std over the first two WF years / the leg's daily std over the same two years."""
    a, b = WF[0], WF[0] + pd.DateOffset(years=2) - pd.Timedelta(days=1)
    bs = window(bwf["mtm"], a, b).std(); ls = window(daily, a, b).reindex(window(bwf["mtm"], a, b).index, fill_value=0.0).std()
    return float(0.25 * bs / ls) if ls > 0 else float("nan")


def seat(bwf, daily, c):
    """Addendum 2 seat report: drawdown-day dollars without the leg's best episode, per-year rows, vol share at c."""
    leg = window(daily, *WF); eps = dd_episodes(bwf["mtm"])
    per_ep = [float(leg.reindex(e).fillna(0.0).sum()) for e in eps]
    allsum = float(sum(per_ep))
    x = leg.reindex(bwf.index, fill_value=0.0); bk = bwf["mtm"]; comb = bk + c * x
    share = float(c * np.cov(x, comb)[0, 1] / np.var(comb, ddof=1)) if np.var(comb) > 0 else float("nan")
    years = {"%d-%02d" % (y0.year, y1.year % 100): round(float(leg[(leg.index >= y0) & (leg.index < y1)].sum())) for y0, y1 in july_years(WF[0])}
    return dict(dd_sum=allsum, dd_ex_best_episode=allsum - (max(per_ep) if per_ep else 0.0), episodes=len(eps),
                per_episode=[round(p) for p in per_ep], years=years, vol_share=share, c=c)


def window(s, a, b):
    return s[(s.index >= a) & (s.index <= b)]


def judge(daily, trades, a, b, bdd=None):
    """Stats for one stretch. trades: list of (exit_date, pnl, group) for the trade-level vetoes."""
    d = window(daily, a, b)
    if len(d) < 20:
        return dict(n=0)
    y = yard(d)
    tp = np.array([p for (x, p, g) in trades if a <= x <= b]); gl = -tp[tp < 0].sum()
    out = dict(y, n=len(tp), pf=float(tp[tp > 0].sum() / gl) if gl > 0 else float("inf"),
               t=float(tp.mean() / tp.std(ddof=1) * np.sqrt(len(tp))) if len(tp) > 1 and tp.std(ddof=1) > 0 else 0.0,
               ex_top=float(tp.sum() - tp.max()) if len(tp) else 0.0, ex_best5d=float(d.sum() - np.sort(d.values)[::-1][:5].sum()),
               ex_2020=float(d[(d.index < "2020-02-15") | (d.index > "2020-04-30")].sum()))
    yrs = july_years(a)
    out["years_pos"] = int(sum(d[(d.index >= y0) & (d.index < y1)].sum() > 0 for y0, y1 in yrs))
    groups = {}
    for (x, p, g) in trades:
        if a <= x <= b:
            groups[g] = groups.get(g, 0.0) + p
    out["ex_best_group"] = float(sum(groups.values()) - max(groups.values())) if groups else 0.0
    if bdd is not None:
        x = d.reindex(bdd).fillna(0.0)
        out["dd_sum"] = float(x.sum()); out["dd_ex3"] = float(x.sum() - np.sort(x.values)[::-1][:3].clip(min=0).sum())
    return out


# ------------------------------------------------------------------------------------------------ data
def load():
    so = pd.read_csv(os.path.join(CACHE, "sector_open.csv"), index_col=0, parse_dates=True)
    sc = pd.read_csv(os.path.join(CACHE, "sector_close.csv"), index_col=0, parse_dates=True)
    no = pd.read_csv(os.path.join(CACHE, "nonequity_open.csv"), index_col=0, parse_dates=True)
    nc = pd.read_csv(os.path.join(CACHE, "nonequity_close.csv"), index_col=0, parse_dates=True)
    O = pd.concat([so, no], axis=1); C = pd.concat([sc, nc], axis=1)
    os.chdir(SHARED); sys.path.insert(0, SHARED)
    from augur_engine.data import find_master, load_master_arrays
    for t in ("QQQ", "IWM", "GLD", "TLT"):
        A = load_master_arrays(find_master(t, "1d", "rth", "yahoo_adj"), date_to="2025-06-29")
        ix = pd.DatetimeIndex(A["index"]).tz_localize(None).normalize()
        O[t] = pd.Series(np.asarray(A["open"], float), index=ix); C[t] = pd.Series(np.asarray(A["close"], float), index=ix)
    O = O[O.index < CUT].sort_index(); C = C[C.index < CUT].sort_index().reindex(O.index)
    shas = {f: hashlib.sha256(open(os.path.join(CACHE, f + ".csv"), "rb").read()).hexdigest()[:16]
            for f in ("sector_open", "sector_close", "nonequity_open", "nonequity_close")}
    return O, C, shas


# ------------------------------------------------------------------------------------------------ engines
def run_positions(O, C, legs, stress=False):
    """legs: list of (open_idx, close_idx, ticker, notional_signed, group). A leg opens at O[open_idx], is marked at the
    closes in between and closes at O[close_idx]. Returns (daily P&L Series, trades list (exit_date, pnl, group))."""
    n = len(O); dates = O.index; daily = np.zeros(n); pertrade = {}
    Ov, Cv = {t: O[t].values for t in O.columns}, {t: C[t].values for t in C.columns}
    for (i, j, t, notl, g) in legs:
        if j <= i or j >= n:
            continue
        o, c = Ov[t], Cv[t]
        if not (np.isfinite(o[i]) and np.isfinite(o[j]) and np.all(np.isfinite(c[i:j]))):
            continue
        cost = bps(t, stress) * abs(notl) * 2
        pnl = np.zeros(j - i + 1)
        pnl[0] = notl * (c[i] / o[i] - 1.0)
        if j - i > 1:
            pnl[1:j - i] = notl * (c[i + 1:j] / c[i:j - 1] - 1.0)
        pnl[j - i] = notl * (o[j] / c[j - 1] - 1.0)
        pnl[0] -= cost / 2; pnl[-1] -= cost / 2
        if notl < 0:
            pnl[-1] -= abs(notl) * BORROW * max(1, (dates[j] - dates[i]).days)
        daily[i:j + 1] += pnl
        key = (j, g)
        pertrade[key] = pertrade.get(key, 0.0) + float(pnl.sum())
    trades = [(dates[j], p, g) for (j, g), p in pertrade.items()]
    return pd.Series(daily, index=dates), trades


def pairs_signals(O, C, z_entry, pairs=None):
    legs = []
    for (a, b) in (pairs or PAIRS):
        la, lb = np.log(C[a]), np.log(C[b])
        ok = la.notna() & lb.notna()
        cov = la.rolling(120).cov(lb); var = lb.rolling(120).var()
        beta = (cov / var)
        sp = la - beta * lb
        z = (sp - sp.rolling(60).mean()) / sp.rolling(60).std()
        zv, bv = z.values, beta.values
        i, n = 0, len(O)
        while i < n - 1:
            if np.isfinite(zv[i]) and abs(zv[i]) >= z_entry and np.isfinite(bv[i]) and ok.iloc[i]:
                side = -1.0 if zv[i] > 0 else 1.0           # z > 0: A rich -> short A, long B
                e = i + 1; x = None
                for k in range(e, min(e + 20, n - 1)):
                    if np.isfinite(zv[k]) and np.sign(zv[k]) != np.sign(zv[i]):
                        x = k + 1; break
                x = x if x is not None else min(e + 20, n - 1)
                g = a + "/" + b
                legs.append((e, x, a, side * 50000.0, g)); legs.append((e, x, b, -side * 50000.0 * bv[i], g))
                i = x
            else:
                i += 1
    return legs


def bab_betas(O, C):
    """Per week (first session i, next week's first session j): shrunk 252-session betas to SPY from closes through i-1.
    Computed once and shared by the cells and every null draw (addendum 2 item 6)."""
    rets = C[EQUITY + ["SPY"]].pct_change()
    n = len(O); dates = O.index; out = []
    mondays = [i for i in range(1, n) if dates[i].weekday() < dates[i - 1].weekday() or (dates[i] - dates[i - 1]).days > 3]
    for wi, i in enumerate(mondays):
        j = mondays[wi + 1] if wi + 1 < len(mondays) else n - 1
        win = rets.iloc[max(0, i - 252):i]
        if len(win) < 252:
            continue
        b = {}
        for t in EQUITY:
            x = win[[t, "SPY"]].dropna()
            if len(x) >= 200:
                bt = np.cov(x[t], x["SPY"])[0, 1] / np.var(x["SPY"], ddof=1)
                b[t] = 0.6 * bt + 0.4
        out.append((i, j, b))
    return out


def bab_signals(weeks, K, rng=None):
    legs = []
    for (i, j, b) in weeks:
        if len(b) < 2 * K:
            continue
        names = sorted(b, key=lambda t: b[t])
        if rng is not None:
            names = list(rng.permutation(names))
        lo, hi = names[:K], names[-K:]
        bl, bh = np.mean([b[t] for t in lo]), np.mean([b[t] for t in hi])
        for t in lo:
            legs.append((i, j, t, 50000.0 / bl / K, "L"))
        for t in hi:
            legs.append((i, j, t, -50000.0 / bh / K, "S"))
    return legs


def onmom_daily(O, C, L, stress=False, rng=None, mirror=False, sides=None):
    """sides: a dict that, when given, receives the long-five and short-five daily P&L apart (each with its own costs,
    borrow on the short five) - addendum 2 item 5."""
    names = EQUITY + OTHER
    on = (O[names] / C[names].shift(1) - 1.0)                      # overnight return into day t
    sig = on.rolling(L, min_periods=L).sum()                         # sessions t-L+1..t, the last = t's own overnight
    nxt = (O[names].shift(-1) / C[names] - 1.0)                      # tonight: official close t -> official open t+1
    daily = pd.Series(0.0, index=O.index); trades = []
    S, N = sig.values, nxt.values
    lg, sh = np.zeros(len(O)), np.zeros(len(O))
    for i in range(len(O) - 1):
        ok = np.isfinite(S[i]) & np.isfinite(N[i])
        if ok.sum() < 10:
            continue
        idx = np.where(ok)[0]
        order = idx[np.argsort(S[i][idx])] if rng is None else rng.permutation(idx)
        lo, hi = order[:5], order[-5:]
        if mirror:
            lo, hi = hi, lo
        brw = 5 * 10000.0 * BORROW * max(1, (O.index[i + 1] - O.index[i]).days)
        pl = 10000.0 * N[i][hi].sum() - sum(bps(names[k], stress) * 10000.0 * 2 for k in hi)
        ps = -10000.0 * N[i][lo].sum() - sum(bps(names[k], stress) * 10000.0 * 2 for k in lo) - brw
        p = pl + ps
        lg[i + 1] += pl; sh[i + 1] += ps
        daily.iloc[i + 1] += p; trades.append((O.index[i + 1], p, "night"))
    if sides is not None:
        sides["long"] = pd.Series(lg, index=O.index); sides["short"] = pd.Series(sh, index=O.index)
    return daily, trades


# ------------------------------------------------------------------------------------------------ run
def stage(name, cells, bwf, bdd, null_max, extra=None):
    res = {}
    for key, (daily, trades, daily_s) in cells.items():
        w = judge(daily, trades, *WF, bdd=bdd); e = judge(daily, trades, *EARLY); ws = judge(daily_s, [], *WF)
        corr = float(np.corrcoef(window(daily, *WF).reindex(bwf.index, fill_value=0.0), bwf["mtm"])[0, 1]) if w.get("n") else float("nan")
        res[key] = dict(wf=w, early=e, wf_stress_net=ws.get("net"), corr_book=corr)
    n95 = float(np.percentile(null_max, 95))
    return res, n95


def book_add(bwf, daily, c):
    leg = window(daily, *WF)
    return yard(pd.concat([bwf["mtm"] + c * leg.reindex(bwf.index, fill_value=0.0), c * leg[~leg.index.isin(bwf.index)]]).sort_index())


def main(which, O, C, shas, bwf):
    bdd = dd_days(bwf["mtm"])
    rng = np.random.default_rng(SEED); out = {"shas": shas, "dd_days": len(bdd)}
    if "PAIRS" in which:
        cells = {}
        for z in (2.0, 2.5):
            legs = pairs_signals(O, C, z)
            d, tr = run_positions(O, C, legs); ds, _ = run_positions(O, C, legs, stress=True)
            cells["PAIRS-z%.1f" % z] = (d, tr, ds)
        tr_by = {k: v[1] for k, v in cells.items()}
        nullmax = []
        real = {k: pairs_signals(O, C, float(k.split("z")[1])) for k in cells}
        for _ in range(REPS):
            best = -np.inf
            for k, legs in real.items():
                fake = []
                for g in sorted(set(l[4] for l in legs)):
                    gl = [l for l in legs if l[4] == g]
                    for a_leg, b_leg in zip(gl[0::2], gl[1::2]):
                        h = a_leg[1] - a_leg[0]; e = int(rng.integers(130, len(O) - h - 1)); s = rng.choice([-1.0, 1.0])
                        fake.append((e, e + h, a_leg[2], s * abs(a_leg[3]), g)); fake.append((e, e + h, b_leg[2], -s * abs(b_leg[3]), g))
                d, _ = run_positions(O, C, fake)
                y = yard(window(d, *WF)); best = max(best, y["roc30"] if np.isfinite(y["roc30"]) else -np.inf)
            nullmax.append(best)
        res, n95 = stage("PAIRS", cells, bwf, bdd, nullmax)
        for k, v in res.items():
            w, e = v["wf"], v["early"]
            v["checks"] = {"n>=100": w.get("n", 0) >= 100, "ROC>=15": w.get("roc30", -1) >= 15, "PF>=1.10": w.get("pf", 0) >= 1.10,
                           "t>=2 & >null95": w.get("t", 0) >= 2 and w.get("roc30", -1) > n95, "stress>0": (v["wf_stress_net"] or -1) > 0,
                           "ex-top>0": w.get("ex_top", -1) > 0, "ex-best-pair>0": w.get("ex_best_group", -1) > 0,
                           "6/9 yrs": w.get("years_pos", 0) >= 6, "ex 2020 crash>0": w.get("ex_2020", -1) > 0, "EARLY>0": e.get("net", -1) > 0}
            # addendum 2 item 3: the same cell on the six pairs left after XLK/QQQ and SPY/IWM are removed
            six = [p for p in PAIRS if p not in (("XLK", "QQQ"), ("SPY", "IWM"))]
            l6 = pairs_signals(O, C, float(k.split("z")[1]), pairs=six)
            d6, t6 = run_positions(O, C, l6); s6, _ = run_positions(O, C, l6, stress=True)
            w6, e6, ws6 = judge(d6, t6, *WF), judge(d6, t6, *EARLY), judge(s6, [], *WF)
            c6 = {"n>=100": w6.get("n", 0) >= 100, "ROC>=15": w6.get("roc30", -1) >= 15, "PF>=1.10": w6.get("pf", 0) >= 1.10,
                  "t>=2": w6.get("t", 0) >= 2, "stress>0": (ws6.get("net") or -1) > 0, "ex-top>0": w6.get("ex_top", -1) > 0,
                  "6/9 yrs": w6.get("years_pos", 0) >= 6, "ex 2020 crash>0": w6.get("ex_2020", -1) > 0, "EARLY>0": e6.get("net", -1) > 0}
            v["six_pairs"] = dict(wf=w6, early_net=e6.get("net"), checks=c6)
            v["checks"]["holds without XLK/QQQ + SPY/IWM"] = all(c6.values())
            v["per_pair_wf"] = {}
            for (x, p, g) in tr_by[k]:
                if WF[0] <= x <= WF[1]:
                    v["per_pair_wf"][g] = round(v["per_pair_wf"].get(g, 0.0) + p)
        out["PAIRS"] = dict(cells=res, null95=n95, null50=float(np.percentile(nullmax, 50)), daily={k: v[0] for k, v in cells.items()})
    if "BAB" in which:
        cells = {}; ctrl = {}; lev = {}
        weeks = bab_betas(O, C)
        for K in (5, 3):
            legs = bab_signals(weeks, K)
            d, tr = run_positions(O, C, legs); ds, _ = run_positions(O, C, legs, stress=True)
            wk = {}
            for (x, p, g) in tr:                                    # addendum 2 item 6a: one trade per WEEK, both sides summed
                wk[x] = wk.get(x, 0.0) + p
            cells["BAB-K%d" % K] = (d, [(x, p, "week") for x, p in sorted(wk.items())], ds)
            eq = [(i, j, t, 50000.0 / K * np.sign(nt), g) for (i, j, t, nt, g) in legs]
            ctrl["BAB-K%d-equal-dollar" % K] = yard(window(run_positions(O, C, eq)[0], *WF))
            # addendum 2 item 4: long-side leverage per week (1 / mean shrunk beta of the long set) and the week's gross
            lw, gw = {}, {}
            for (i, j, t, nt, g) in legs:
                if WF[0] <= O.index[i] <= WF[1]:
                    gw[i] = gw.get(i, 0.0) + abs(nt)
                    if g == "L":
                        lw[i] = lw.get(i, 0.0) + nt / 50000.0
            lv, gv = np.array(list(lw.values())), np.array(list(gw.values()))
            lev["BAB-K%d" % K] = dict(long_lev_min=float(lv.min()), long_lev_median=float(np.median(lv)), long_lev_max=float(lv.max()),
                                      gross_median=float(np.median(gv)), gross_max=float(gv.max()), weeks=int(len(lv)),
                                      long_set_changes=int(sum(1 for a_, b_ in zip(sorted(lw), sorted(lw)[1:]) if
                                                               set(l[2] for l in legs if l[0] == a_ and l[4] == "L") !=
                                                               set(l[2] for l in legs if l[0] == b_ and l[4] == "L"))))
        nmax, nmaxdd = [], []
        for _ in range(REPS):
            best, bestdd = -np.inf, -np.inf
            for K in (5, 3):
                d, _ = run_positions(O, C, bab_signals(weeks, K, rng=rng))
                y = yard(window(d, *WF)); best = max(best, y["roc30"]); bestdd = max(bestdd, float(window(d, *WF).reindex(bdd).fillna(0).sum()))
            nmax.append(best); nmaxdd.append(bestdd)
        res, n95 = stage("BAB", cells, bwf, bdd, nmax); ndd95 = float(np.percentile(nmaxdd, 95))
        spy = C["SPY"].pct_change()

        def dbeta(dd_, notional):
            r = spy.reindex(dd_.index) * notional; ok = r.notna()
            return float(np.cov(dd_[ok], r[ok])[0, 1] / np.var(r[ok], ddof=1)) if ok.sum() > 50 else float("nan")
        for k, v in res.items():
            w, e = v["wf"], v["early"]; d = window(cells[k][0], *WF)
            beta = dbeta(d, 50000.0)                                  # addendum 2 item 6b: per $50,000 of side notional
            v["realised_beta"] = beta; v["realised_beta_per_100k"] = dbeta(d, 100000.0)
            v["beta_by_year"] = {"%d-%02d" % (y0.year, y1.year % 100): round(dbeta(d[(d.index >= y0) & (d.index < y1)], 50000.0), 3)
                                 for y0, y1 in july_years(WF[0])}
            v["beta_dd_days"] = dbeta(d.reindex(bdd).dropna(), 50000.0)
            v["leverage"] = lev[k]
            v["seat"] = seat(bwf, cells[k][0], vol_c(bwf, cells[k][0]))
            common = {"rebalances>=400": w.get("n", 0) >= 400, "|beta|<=0.20": abs(beta) <= 0.20, "stress>0": (v["wf_stress_net"] or -1) > 0,
                      "ex-best-week>0": w.get("ex_top", -1) > 0, "6/9 yrs": w.get("years_pos", 0) >= 6,
                      "ex 2020 crash>0": w.get("ex_2020", -1) > 0, "EARLY>0": e.get("net", -1) > 0}
            r1 = w.get("roc30", -1) >= 15 and w.get("pf", 0) >= 1.10 and w.get("roc30", -1) > n95
            r2 = w.get("roc30", -1) >= 5 and w.get("dd_sum", -1) > 0 and w.get("dd_ex3", -1) > 0 and w.get("dd_sum", -1) > ndd95
            v["checks"] = dict(common, **{"route1 or route2": bool(r1 or r2)}); v["route1"], v["route2"] = bool(r1), bool(r2)
        out["BAB"] = dict(cells=res, null95=n95, null50=float(np.percentile(nmax, 50)), null_dd95=ndd95, controls=ctrl, daily={k: v[0] for k, v in cells.items()})
    if "ONMOM" in which:
        cells = {}; mir = {}; sides = {}
        for L in (20, 60):
            sd = {}
            d, tr = onmom_daily(O, C, L, sides=sd); ds, _ = onmom_daily(O, C, L, stress=True)
            cells["ONMOM-L%d" % L] = (d, tr, ds); mir[L] = yard(window(onmom_daily(O, C, L, mirror=True)[0], *WF))
            sides["ONMOM-L%d" % L] = {s: dict(wf_net=float(window(x, *WF).sum()), early_net=float(window(x, *EARLY).sum()))
                                      for s, x in sd.items()}
        names = EQUITY + OTHER
        on = window(O[names] / C[names].shift(1) - 1.0, *WF)
        zero_on = {t: int((on[t] == 0).sum()) for t in names}
        nmax = []
        for _ in range(REPS):
            nmax.append(max(yard(window(onmom_daily(O, C, L, rng=rng)[0], *WF))["roc30"] for L in (20, 60)))
        res, n95 = stage("ONMOM", cells, bwf, bdd, nmax)
        for k, v in res.items():
            w, e = v["wf"], v["early"]; L = int(k.split("L")[1])
            v["checks"] = {"nights>=1800": w.get("n", 0) >= 1800, "ROC>=15": w.get("roc30", -1) >= 15, "PF>=1.10": w.get("pf", 0) >= 1.10,
                           "t>=2 & >null95": w.get("t", 0) >= 2 and w.get("roc30", -1) > n95, "beats mirror": w.get("roc30", -1) > mir[L]["roc30"],
                           "stress>0": (v["wf_stress_net"] or -1) > 0, "ex-best5n>0": w.get("ex_best5d", -1) > 0,
                           "6/9 yrs": w.get("years_pos", 0) >= 6, "ex 2020 crash>0": w.get("ex_2020", -1) > 0, "EARLY>0": e.get("net", -1) > 0}
            v["sides"] = sides[k]
        out["ONMOM"] = dict(cells=res, null95=n95, null50=float(np.percentile(nmax, 50)), mirrors=mir, zero_overnight_days_wf=zero_on,
                            daily={k: v[0] for k, v in cells.items()})
    # Stage A2 per family - a REPORT at the volatility c (house line #45 / addendum 2 item 1); it gates nothing
    for fam in which:
        F = out[fam]; passes = [k for k, v in F["cells"].items() if all(v["checks"].values())]
        F["passes"] = passes
        F["a2"] = {}
        for k in F["cells"]:
            c = vol_c(bwf, F["daily"][k]); y = book_add(bwf, F["daily"][k], c)
            F["a2"][k] = dict(c=c, roc30=y["roc30"], sortino=y["sortino"], dd=y["dd"],
                              above_463=bool(y["roc30"] >= BOOK_ROC and y["sortino"] >= BOOK_SORT))
    return out


def report(out):
    for fam in ("PAIRS", "BAB", "ONMOM"):
        if fam not in out:
            continue
        F = out[fam]
        print("\n%s  null 95th pct ROC@30k %.1f (50th %.1f; power line ~ %.1f ROC points)%s" % (fam, F["null95"], F["null50"],
              F["null95"] - F["null50"], ("  | drawdown-day null %.0f" % F["null_dd95"]) if "null_dd95" in F else ""))
        for k, v in F["cells"].items():
            w = v["wf"]
            print("  %-22s n %5s ROC@30k %6.1f Sort %5.2f PF %4.2f t %5.2f yrs+ %s DDdays $%s (ex3 $%s) EARLY $%s corr %.2f%s %s" % (
                k, w.get("n"), w.get("roc30", float("nan")), w.get("sortino", float("nan")), w.get("pf", 0), w.get("t", 0),
                w.get("years_pos"), f"{w.get('dd_sum', 0):,.0f}", f"{w.get('dd_ex3', 0):,.0f}", f"{v['early'].get('net', 0):,.0f}",
                v["corr_book"], ("  beta %.2f" % v["realised_beta"]) if "realised_beta" in v else "",
                "PASS" if all(v["checks"].values()) else "fails " + ", ".join(c for c, ok in v["checks"].items() if not ok)))
            if "six_pairs" in v:
                s6 = v["six_pairs"]; w6 = s6["wf"]
                print("    six pairs (no XLK/QQQ, SPY/IWM): n %s ROC@30k %.1f PF %.2f t %.2f EARLY $%s %s" % (
                    w6.get("n"), w6.get("roc30", float("nan")), w6.get("pf", 0), w6.get("t", 0), f"{s6['early_net'] or 0:,.0f}",
                    "holds" if all(s6["checks"].values()) else "fails " + ", ".join(c for c, ok in s6["checks"].items() if not ok)))
                print("    per pair WF $:", v["per_pair_wf"])
            if "beta_by_year" in v:
                print("    beta per $50k side %.3f (per $100k %.3f; in #463 DD days %.3f) by year %s" % (
                    v["realised_beta"], v["realised_beta_per_100k"], v["beta_dd_days"], v["beta_by_year"]))
                print("    leverage", {a: round(b, 2) for a, b in v["leverage"].items()})
                s = v["seat"]
                print("    SEAT: DD-day $%s over %d episodes %s; without the best episode $%s; vol share %.3f at c %.2f; years %s" % (
                    f"{s['dd_sum']:,.0f}", s["episodes"], s["per_episode"], f"{s['dd_ex_best_episode']:,.0f}", s["vol_share"], s["c"], s["years"]))
            if "sides" in v:
                print("    long five / short five:", {a: {kk: round(vv) for kk, vv in b.items()} for a, b in v["sides"].items()})
        for extra in ("controls", "mirrors"):
            if extra in F:
                print("  %s: %s" % (extra, {str(k): round(v["roc30"], 1) for k, v in F[extra].items()}))
        if "zero_overnight_days_wf" in F:
            print("  zero-overnight days (WF):", {t: n for t, n in F["zero_overnight_days_wf"].items() if n})
        print("  passes:", F["passes"] or "none")
        for k, a2 in F["a2"].items():
            print("  A2 report %s: c %.2f -> book ROC@30k %.2f Sort %.3f DD $%s%s" % (k, a2["c"], a2["roc30"], a2["sortino"],
                  f"{a2['dd']:,.0f}", "  (above #463)" if a2["above_463"] else ""))


def selftest():
    global CACHE, BOOK, REPS, WF, EARLY
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2012-01-02", "2019-12-31"); n = len(dates)
    names = ["SPY"] + EQUITY + OTHER
    O = pd.DataFrame(index=dates); C = pd.DataFrame(index=dates)
    mkt = np.cumsum(rng.normal(0, 0.01, n))
    for t in names:
        b = rng.uniform(0.5, 1.5) if t in EQUITY or t == "SPY" else 0.0
        lp = 4 + b * mkt + np.cumsum(rng.normal(0, 0.008, n))
        C[t] = np.exp(lp); O[t] = C[t].shift(1).fillna(C[t].iloc[0]) * np.exp(rng.normal(0, 0.003, n))
    C["SLV"] = C["GLD"] * np.exp(0.05 * np.sin(np.arange(n) / 15.0))          # a mean-reverting pair to exercise PAIRS
    O["SLV"] = C["SLV"].shift(1).fillna(C["SLV"].iloc[0]) * np.exp(rng.normal(0, 0.003, n))   # its opens follow its closes
    bk = pd.DataFrame({"date": dates, "mtm": rng.normal(60, 600, n)})
    d = os.path.join(os.environ.get("TEMP", "."), "tvnt1_selftest"); os.makedirs(d, exist_ok=True)
    BOOK = os.path.join(d, "book.csv"); bk.to_csv(BOOK, index=False)
    WF = (pd.Timestamp("2016-01-01"), pd.Timestamp("2019-12-31")); EARLY = (pd.Timestamp("2013-01-01"), pd.Timestamp("2015-12-31")); REPS = 3
    bwf = window(pd.read_csv(BOOK, parse_dates=["date"]).set_index("date"), *WF)
    out = main(["PAIRS", "BAB", "ONMOM"], O, C, {"synthetic": "-"}, bwf)
    report(out)
    gs = out["PAIRS"]["cells"]["PAIRS-z2.0"]["wf"]
    assert gs.get("n", 0) > 0, "PAIRS must trade on synthetic prices"
    assert abs(out["BAB"]["cells"]["BAB-K5"]["realised_beta"]) < 0.5, "BAB must be close to beta-neutral by construction"
    om = out["ONMOM"]["cells"]["ONMOM-L20"]["wf"]
    assert om.get("pf", 9) < 1.5 and om.get("dd", 0) > 0, "ONMOM on random prices must not look like an edge"
    print("SELFTEST OK - synthetic only, no real data read")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(); sys.exit(0)
    which = [a for a in sys.argv[1:] if a in ("PAIRS", "BAB", "ONMOM")] or ["PAIRS", "BAB", "ONMOM"]
    O, C, shas = load()
    bk = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date"); bwf = window(bk, *WF)
    base = yard(bwf["mtm"])
    print("#463 WF: %.2f / %.3f / $%s (must be 93.81 / 3.816 / $44,849)" % (base["roc30"], base["sortino"], f"{base['dd']:,.0f}"))
    if not (abs(base["roc30"] - 93.81) < 0.01 and abs(base["sortino"] - 3.816) < 0.001 and abs(base["dd"] - 44849) < 1):
        sys.exit("STOP: #463 does not reproduce")
    print("data:", shas, "| funds:", len(O.columns), "| last bar", O.index[-1].date())
    out = main(which, O, C, shas, bwf)
    report(out)
    os.makedirs(OUT, exist_ok=True)
    slim = {k: ({kk: vv for kk, vv in v.items() if kk != "daily"} if isinstance(v, dict) else v) for k, v in out.items()}
    with open(os.path.join(OUT, "stage_a_%s.json" % "_".join(which)), "w") as f:
        json.dump(slim, f, default=float, indent=1)
    print("written", OUT)
