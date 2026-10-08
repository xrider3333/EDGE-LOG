"""DISTRESS-ML r1 - a learned distress (crash) classifier on point-in-time XBRL + prices, short the likely crashers, long
the safest, beta-neutral, monthly (walk-forward only; nothing after 2025-06-29). Pre-registration:
docs/PREREG_distressml_r1_2026-10-08.md. Reuses FUND-ML r1's point-in-time loaders (tools/fundml_r1.py, addenda 1-2:
share-count staleness, raw-price $5 floor, as-traded market value) and the XSML r1 harness (tools/xsml_r1.py).

    python tools/distressml_r1.py dryload   coverage only - names x months with each input; never a return
    python tools/distressml_r1.py power     the null (random beta-neutral books on the eligible names): ROC + earner route
    python tools/distressml_r1.py run       cell + CHS twin + bars + diagnostics, after POWER.txt is committed
    (cwd = the shared checkout; EDGELOG_ROOT = it; XSML_CA = the wide corporate-actions file)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsml_r1 as X                                                   # noqa: E402
import fundml_r1 as F                                                 # noqa: E402

OUT = r"C:\EdgeLog\custom_ml\distressml_r1"
SEED = 20261008
H = 63                                                                # label horizon (sessions)
HGB = F.HGB
CHS_IN = ["nimta", "tlmta", "exret", "sigma", "rsize", "cashmta", "mb", "price"]
INPUTS = CHS_IN + ["wcta", "reta", "ebitta", "metl", "sta",          # Altman
                   "lta", "clca", "loss2", "dni", "cfotl", "icov",   # Ohlson + coverage
                   "ivol63", "max21", "dhi", "mom12", "beta", "ldv"]  # XSML cell C's price set
# CHS (2008) Table IV column 3, as restated in the Management Science online appendix of "Distressed Stocks in
# Distressed Times" (intercept -9.164 dropped: it does not change a ranking)
CHS = dict(nimta=-20.264, tlmta=1.416, exret=-7.129, sigma=1.411, rsize=-0.045, cashmta=-2.132, mb=0.075, price=-0.058)
PHI = 2.0 ** (-1.0 / 3.0)


# ------------------------------------------------------------------------------------------------ inputs
def distress_at(facts, shares, t):
    g = lambda names, flow: F.pick(facts, names, t, flow)
    d = pd.DataFrame({
        "ni": g(["NetIncomeLoss"], True),
        "ni_1y": F.latest(facts.get("NetIncomeLoss"), t, True, back=(330, 400)),
        "rev": g(["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"], True),
        "opi": g(["OperatingIncomeLoss"], True), "intx": g(["InterestExpense"], True),
        "cfo": g(["NetCashProvidedByUsedInOperatingActivities"], True),
        "assets": g(["Assets"], False), "liab": g(["Liabilities"], False),
        "eq_all": g(["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"], False),
        "be": g(["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], False),
        "ca": g(["AssetsCurrent"], False), "cl": g(["LiabilitiesCurrent"], False),
        "cash": g(["CashAndCashEquivalentsAtCarryingValue"], False),
        "re": g(["RetainedEarningsAccumulatedDeficit"], False),
        "sh": F.pick(shares, ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"], t, False,
                     max_age=F.FLOW_MAX),
    })
    # total liabilities: the Liabilities tag, else assets minus total equity (many filers never tag Liabilities)
    d["liab"] = d.liab.combine_first(d.assets - d.eq_all)
    return d


def exret_avg(D, mo):
    """CHS EXRETAVG at each month end: geometrically weighted (2^(-1/3) per month) average of the last 12 monthly log
    excess returns over the equal-weight universe; at least 9 of 12 months, weights renormalised over those present."""
    M = D.C.reindex(pd.DatetimeIndex(mo))
    rm = M / M.shift(1) - 1.0
    cm = (1.0 + D.mkt).cumprod().reindex(pd.DatetimeIndex(mo))
    mm = cm / cm.shift(1) - 1.0
    ex = np.log1p(rm).sub(np.log1p(mm), axis=0).to_numpy(float)
    out = np.full(ex.shape, np.nan)
    w = PHI ** np.arange(12)
    for i in range(12, len(mo)):
        blk = ex[i - 11: i + 1][::-1]                                 # row 0 = the month ending at mo[i]
        ok = np.isfinite(blk)
        ww = (w[:, None] * ok)
        n = ok.sum(axis=0)
        s = np.nansum(np.where(ok, blk, 0.0) * w[:, None], axis=0) / np.where(ww.sum(axis=0) > 0, ww.sum(axis=0), np.nan)
        out[i] = np.where(n >= 9, s, np.nan)
    return pd.DataFrame(out, index=pd.DatetimeIndex(mo), columns=D.syms)


def wins(v, lo=5, hi=95):
    ok = np.isfinite(v)
    if ok.sum() < 10:
        return v
    a, b = np.percentile(v[ok], [lo, hi])
    return np.clip(v, a, b)


def build_inputs(D, FC, dates, mo):
    facts, shares = F.load_facts(), F.load_shares()
    cmap = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False)[["symbol", "cik"]] for p in F.CIKMAP])
    cmap = cmap[cmap.cik != ""].drop_duplicates("symbol", keep="last")
    cmap["cik"] = cmap.cik.str.lstrip("0")
    sym2cik = dict(zip(cmap.symbol, cmap.cik))
    col_cik = pd.Series([sym2cik.get(s) for s in D.syms], index=D.syms)
    EX = exret_avg(D, mo)
    sig = D.r_cc.rolling(63, min_periods=50).std() * np.sqrt(252.0)
    frames = {k: pd.DataFrame(np.nan, index=pd.DatetimeIndex(dates), columns=D.syms) for k in INPUTS}
    twin, elig = {}, {}
    for t in dates:
        p = D.pos(t)
        names = np.flatnonzero(D.Un[p])
        f = distress_at(facts, shares, t)
        ck = col_cik.iloc[names]
        R = f.reindex(ck.values)
        R.index = D.syms[names]
        px = D.Craw.iloc[p, names].to_numpy(float)                    # as-traded close (FUND-ML addendum 2)
        mv = R.sh.to_numpy(float) * px
        mv = np.where(mv > 0, mv, np.nan)
        tl = R.liab.where(R.liab > 0).to_numpy(float)
        a = R.assets.where(R.assets > 0).to_numpy(float)
        mta = mv + tl
        be = R.be.to_numpy(float)
        adj = be + 0.1 * (mv - be)
        adj = np.where(np.isfinite(adj) & (adj <= 0), 1.0, adj)       # CHS: non-positive adjusted book -> $1
        ni, ni1 = R.ni.to_numpy(float), R.ni_1y.to_numpy(float)
        intx = R.intx.where(R.intx > 0).to_numpy(float)
        vals = {
            "nimta": ni / mta, "tlmta": tl / mta, "exret": EX.loc[t, D.syms[names]].to_numpy(float),
            "sigma": sig.iloc[p, names].to_numpy(float), "rsize": np.log(mv / np.nansum(mv)),
            "cashmta": R.cash.to_numpy(float) / mta, "mb": mv / adj, "price": np.log(np.minimum(px, 15.0)),
            "wcta": (R.ca - R.cl).to_numpy(float) / a, "reta": R.re.to_numpy(float) / a,
            "ebitta": R.opi.to_numpy(float) / a, "metl": mv / tl, "sta": R.rev.to_numpy(float) / a,
            "lta": np.log(a), "clca": R.cl.to_numpy(float) / R.ca.where(R.ca > 0).to_numpy(float),
            "loss2": np.where(np.isfinite(ni) & np.isfinite(ni1), ((ni < 0) & (ni1 < 0)).astype(float), np.nan),
            "dni": (ni - ni1) / (np.abs(ni) + np.abs(ni1)), "cfotl": R.cfo.to_numpy(float) / tl,
            "icov": R.opi.to_numpy(float) / intx,
            "ivol63": FC["ivol63"].iloc[p, names].to_numpy(float), "max21": FC["max21"].iloc[p, names].to_numpy(float),
            "dhi": FC["dhi"].iloc[p, names].to_numpy(float), "mom12": FC["mom12"].iloc[p, names].to_numpy(float),
            "beta": FC["beta"].iloc[p, names].to_numpy(float), "ldv": FC["ldv"].iloc[p, names].to_numpy(float),
        }
        for k, v in vals.items():
            v = np.where(np.isfinite(v), v, np.nan)
            vals[k] = v
            frames[k].loc[t, D.syms[names]] = v
        ok = np.all([np.isfinite(vals[k]) for k in CHS_IN], axis=0)
        elig[t] = names[ok]
        # the CHS twin: published coefficients on the raw inputs, winsorised 5 / 95 across the eligible names
        twin[t] = (names[ok], sum(c * wins(vals[k][ok]) for k, c in CHS.items()))
        F.COUNTS[t] = dict(universe=len(names), mapped=int(ck.notna().sum()), shares_ok=int(np.isfinite(mv).sum()),
                           eligible=int(ok.sum()))
        X.log(f"  {t.date()}: universe {len(names)}, mapped {int(ck.notna().sum())}, eligible {int(ok.sum())}")
    return frames, elig, twin


# ------------------------------------------------------------------------------------------------ model
def model_scores(D, frames, elig, dates):
    from sklearn.ensemble import HistGradientBoostingClassifier
    target = X.fwd_crash(D, H)
    rows = {t: (elig[t], X.xs_rank(frames, t, D.syms[elig[t]])) for t in dates}
    preds, fits, labels = {}, {}, {}
    for t in dates:
        fill = D.dates[D.pos(t) + 1]
        if fill < X.WF0:
            continue
        Y = fill.year
        if Y not in fits:
            cut = pd.Timestamp(f"{Y}-01-01")
            Xs, ys = [], []
            for u in dates:
                pu = D.pos(u)
                ex = pu + 1 + H
                if ex >= len(D.dates) or D.dates[ex] >= cut:
                    continue
                names, Xu = rows[u]
                y = target(pu, names)
                ok = np.isfinite(y)
                if ok.sum() > 50:
                    Xs.append(Xu[ok]); ys.append(y[ok])
            yt = np.concatenate(ys)
            fits[Y] = HistGradientBoostingClassifier(**HGB).fit(np.vstack(Xs), yt.astype(int))
            X.log(f"  refit {Y}: {len(yt):,} rows from {len(Xs)} decisions, {int(yt.sum()):,} positives")
        names, Xt = rows[t]
        preds[t] = (names, fits[Y].predict_proba(Xt)[:, 1])
        p = D.pos(t)
        labels[t] = target(p, names) if p + 1 + H < len(D.dates) else np.full(len(names), np.nan)
    return preds, labels


def auc_by_year(preds, labels):
    from sklearn.metrics import roc_auc_score
    rows = {}
    for t, (names, pr) in preds.items():
        y = labels[t]
        ok = np.isfinite(y)
        if ok.sum() > 20 and 0 < y[ok].sum() < ok.sum():
            rows.setdefault(t.year, []).append((roc_auc_score(y[ok], pr[ok]), float(y[ok].mean())))
    return {yr: (float(np.mean([a for a, _ in v])), float(np.mean([b for _, b in v]))) for yr, v in sorted(rows.items())}


# ------------------------------------------------------------------------------------------------ steps
def setup():
    ca = X.ca_path_required()
    D = X.Data(ca, floor_raw=True)
    FA, FC, beta, wk, mo = X.build(D)
    w = X.wf_decisions(D, mo)
    pre = [t for t in mo if D.dates[D.pos(t) + 1] < X.WF0 and t.year >= 2017]
    dates = sorted(set(pre) | set(w))
    frames, elig, twin = build_inputs(D, FC, dates, mo)
    return D, beta, frames, elig, twin, dates, w


def dryload():
    os.makedirs(OUT, exist_ok=True)
    D, beta, frames, elig, twin, dates, w = setup()
    cov = pd.DataFrame({k: [int(frames[k].loc[t].notna().sum()) for t in dates] for k in INPUTS}, index=dates)
    cov["universe"] = [int(D.Un[D.pos(t)].sum()) for t in dates]
    cov["eligible"] = [len(elig[t]) for t in dates]
    cov.to_csv(os.path.join(OUT, "coverage.csv"))
    print(cov.describe().loc[["min", "50%", "max"]].round(0).to_string())
    print("\n".join(F.coverage_lines([t for t in dates if t in w])))


def books_of(D, scores, dates, beta, n=X.N_SIDE):
    """scores = predicted badness: side_books longs the LOWEST, shorts the HIGHEST."""
    return [(t, X.side_books(D, t, scores[t][0], scores[t][1], n=n, beta=beta[D.pos(t)])) for t in dates]


def power():
    os.makedirs(OUT, exist_ok=True)
    D, beta, frames, elig, twin, dates, w = setup()
    w463, days, weeks, _, _ = X.book463_ddweeks()
    rng = np.random.default_rng(SEED)
    roc, roc_net, do, rho = [], [], [], []
    for _ in range(X.N_SHUF):
        books = [(t, X.side_books(D, t, elig[t], rng.random(len(elig[t])), beta=beta[D.pos(t)])) for t in w]
        x = X.periodic_book(D, books)
        roc.append(X.roc_sortino(x)[0])
        roc_net.append(X.roc_sortino(X.periodic_book(D, books, X.COST, X.BORROW))[0])
        r_, d_ = X.dd_stats(x, w463, days, weeks)
        do.append(d_); rho.append(r_)
    roc, roc_net, do, rho = map(np.array, (roc, roc_net, do, rho))
    p50, p95 = float(np.median(roc)), float(np.percentile(roc, 95))
    lines = [f"DISTRESS-ML r1 POWER LINE (no cell or twin P&L read): {len(w)} monthly WF decisions; 1,000 random "
             f"beta-neutral books on the eligible names (seed {SEED}).",
             f"  null (GROSS - the cell is judged NET against it, deliberately conservative): WF ROC @ $30k 50th {p50:+.1f}, "
             f"95th {p95:+.1f}; for the record, the NET null's 95th {np.percentile(roc_net, 95):+.1f}",
             f"  earner-route null: DO 50th {np.median(do):+.3f}, 95th {np.percentile(do, 95):+.3f}; rho_dd 5th "
             f"{np.percentile(rho, 5):+.3f}, 50th {np.median(rho):+.3f}",
             f"  MDE in own money: the smallest lead over a random book this test can see is about "
             f"${(p95 - p50) * 1000:,.0f} a year at a $30k drawdown (95th minus 50th, $1,000 a year per ROC point); the "
             f"map bar (ROC 15) is $15,000 a year."] + ["  " + l for l in F.coverage_lines(w)]
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "POWER.txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame({"roc": roc, "roc_net": roc_net, "do": do, "rho": rho}).to_csv(os.path.join(OUT, "nulls.csv"), index=False)


def bars(D, net, net_s, twin_net, null95, do95, do50, w463, days, weeks, info, pf, nbrs_roc, nbrs_do, acc):
    """The prereg's six bars (the earner route as registered for this cell)."""
    r, s = X.roc_sortino(net)
    rt, st = X.roc_sortino(twin_net)
    rho, do = X.dd_stats(net, w463, days, weeks)
    _, do_t = X.dd_stats(twin_net, w463, days, weeks)
    wf = net[(net.index >= X.WF0) & (net.index <= X.WF1)]
    tot = float(wf.sum())
    earner = do > do95 and rho <= -0.15 and tot > 0
    route = "ROC" if r >= 15 else ("EARNER" if earner else "none")
    no20 = float(wf[~((wf.index >= "2020-02-01") & (wf.index <= "2020-04-30"))].sum())
    ys = X.years_ok(net)
    h1 = float(wf[wf.index <= "2021-12-31"].sum())
    h2 = float(wf[wf.index >= "2022-01-01"].sum())
    npd = np.sort(np.asarray(acc.name_periods, float))[::-1]
    k1 = max(1, int(round(0.01 * len(npd))))
    no_top1 = tot - float(npd[:k1].sum())
    no_top5 = tot - float(np.sort(np.asarray(acc.dec_periods, float))[::-1][:5].sum())
    b = {
        "1 net WF ROC >= 15 OR the earner route (DO > null 95th AND rho_dd <= -0.15 AND net WF > 0); net > 0 at stress":
            bool((r >= 15 or earner) and tot > 0 and net_s[(net_s.index >= X.WF0)].sum() > 0),
        "2 NET WF ROC above the null's 95th (or, on the earner route, DO above its 95th)": bool(r > null95 or earner),
        "3 beats the CHS twin on net WF ROC AND Sortino (earner route: on DO as well)":
            bool(r > rt and s > st and (route != "EARNER" or do > do_t)),
        "4 RISK r1: no Feb-Apr 2020 > 0, >= 5 of 7 years > 0, halves 2018-21 / 2022-25 > 0, > 0 without the best 1% of "
        "name-periods and without the best 5 months":
            bool(no20 > 0 and sum(v > 0 for v in ys) >= 5 and h1 > 0 and h2 > 0 and no_top1 > 0 and no_top5 > 0),
        "5 >= 100 name-positions, >= 26 decisions, PF of name-periods >= 1.0":
            bool(info["positions"] >= 100 and info["decisions"] >= 26 and pf >= 1.0),
        "6 neighbours (25 / 100) net WF ROC > 0 (earner route: both DO > the null's 50th)":
            bool(all(v > do50 for v in nbrs_do.values()) if route == "EARNER" else all(v > 0 for v in nbrs_roc.values())),
    }
    lines = [f"  route: {route} | rho_dd {rho:+.3f}, DO {do:+.3f} (null 95th {do95:+.3f}); twin DO {do_t:+.3f} | halves "
             f"2018-21 ${h1:,.0f} / 2022-25 ${h2:,.0f}"]
    lines += [f"  [{'PASS' if v else 'fail'}] {k}" for k, v in b.items()]
    return lines, all(b.values())


def run():
    assert os.path.exists(os.path.join(OUT, "POWER.txt")), "run `power` first and commit POWER.txt"
    nl = pd.read_csv(os.path.join(OUT, "nulls.csv"))
    null95 = float(np.percentile(nl.roc, 95))
    do95, do50 = float(np.percentile(nl["do"], 95)), float(np.median(nl["do"]))
    D, beta, frames, elig, twin, dates, w = setup()
    w463, days, weeks, _, _ = X.book463_ddweeks()
    T = len(D.dates)
    P, LAB = model_scores(D, frames, elig, dates)
    wd = [t for t in w if t in P]
    books = books_of(D, P, wd, beta)
    tbooks = books_of(D, twin, wd, beta)
    acc, acc0 = X.Acc(T), X.Acc(T)
    net = X.periodic_book(D, books, X.COST, X.BORROW, acc=acc)
    X.periodic_book(D, books, X.COST, X.BORROW, acc=acc0, delist="short0")
    tw = X.periodic_book(D, tbooks, X.COST, X.BORROW)
    nb = {n: X.periodic_book(D, books_of(D, P, wd, beta, n=n), X.COST, X.BORROW) for n in (25, 100)}
    nbrs_roc = {f"n={n}": X.roc_sortino(x)[0] for n, x in nb.items()}
    nbrs_do = {f"n={n}": X.dd_stats(x, w463, days, weeks)[1] for n, x in nb.items()}
    pfv = np.asarray(acc.name_periods, float)
    pf = float(pfv[pfv > 0].sum() / -pfv[pfv < 0].sum())
    info = dict(decisions=len(books), positions=sum(len(b) for _, b in books))
    net_s = X.periodic_book(D, books, X.COST_STRESS, X.BORROW)
    # the harness's standard block (its own bar lines are replaced by this prereg's six)
    lines, _ = X.judge("C DISTRESS-ML", D, net, net_s, X.periodic_book(D, books), tw, null95, w463, days, weeks, info,
                       pf, nbrs_roc, acc, X.periodic_book(D, books, X.COST, X.BORROW, delist="long0"),
                       pd.Series(acc0.short, index=D.dates), do95)
    lines = [l for l in lines if not l.startswith("  [") and not l.startswith("  -> ")]
    bl, ok = bars(D, net, net_s, tw, null95, do95, do50, w463, days, weeks, info, pf, nbrs_roc, nbrs_do, acc)
    lines += bl
    # diagnostics (standing order addendum 2 (2))
    from augur_engine.drawdowns import dd5
    rt, st = X.roc_sortino(tw)
    d5t = dd5(tw[(tw.index >= X.WF0) & (tw.index <= X.WF1)])
    curve = {c: X.roc_sortino(X.periodic_book(D, books, c / 1e4, X.BORROW))[0] for c in (0, 5, 10, 20)}
    fills = [D.pos(t) + 1 for t, _ in books]
    ev, cnt = np.zeros(25), np.zeros(25)
    for k, f in enumerate(fills):
        e = fills[k + 1] if k + 1 < len(fills) else T
        seg = net.iloc[f:e].to_numpy()[:25]
        ev[:len(seg)] += seg; cnt[:len(seg)] += 1
    path = np.cumsum(ev / np.maximum(cnt, 1))
    wf = net[(net.index >= X.WF0) & (net.index <= X.WF1)]
    m = D.mkt.reindex(wf.index).fillna(0.0)
    beta_mkt = float(np.cov(wf, m)[0, 1] / m.var()) / (2 * X.GROSS) if m.var() > 0 else float("nan")
    top_eps = dd5(w463)["episodes"]
    ep_rows = [f"{pd.Timestamp(e['peak']).date()}..{pd.Timestamp(e['trough']).date()} (#463 -${e['depth']:,.0f}): "
               f"cell ${float(net[(net.index > pd.Timestamp(e['peak'])) & (net.index <= pd.Timestamp(e['trough']))].sum()):,.0f}"
               f", twin ${float(tw[(tw.index > pd.Timestamp(e['peak'])) & (tw.index <= pd.Timestamp(e['trough']))].sum()):,.0f}"
               for e in top_eps]
    au = auc_by_year(P, LAB)
    lines += [f"  TWIN (CHS 2008 published logit, for FRONTIER): net WF ROC {rt:.1f} / {st:.2f}; worst DD "
              f"${d5t['max_dd']:,.0f} DD5 ${d5t['dd5_usd']:,.0f}",
              "  cost curve (net WF ROC @ $30k at 0 / 5 / 10 / 20 bps a side): " + " / ".join(f"{v:.1f}" for v in curve.values()),
              "  event-time path (mean cumulative $ by session since the fill, sessions 1, 5, 10, 15, 20): "
              + ", ".join(f"{path[i]:,.0f}" for i in (0, 4, 9, 14, 19)),
              "  #463's five deepest WF drawdowns, cell and twin P&L inside each: " + "; ".join(ep_rows),
              f"  beta to the equal-weight universe (per $ gross): {beta_mkt:+.3f}",
              "  out-of-sample AUC by year (label base rate): "
              + ", ".join(f"{y} {a:.3f} ({b:.1%})" for y, (a, b) in au.items()),
              f"  neighbours DO: " + ", ".join(f"{k} {v:+.3f}" for k, v in nbrs_do.items())]
    lines += ["  " + l for l in F.coverage_lines(wd)]
    lines.append("\nSTAGE A: " + ("DISTRESS-ML PASSES -> hand audit of the 30 names, then MANAGER" if ok else
                                   "DISTRESS-ML dead (no variants)") + " - walk-forward only; nothing after 2025-06-29 loaded")
    txt = open(os.path.join(OUT, "POWER.txt"), encoding="utf-8").read().rstrip() + "\n" + "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "STAGE_A.txt"), "w", encoding="utf-8").write(txt + "\n")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"dryload": dryload, "power": power, "run": run}.get(mode, lambda: sys.exit("usage: distressml_r1.py dryload | power | run"))()
