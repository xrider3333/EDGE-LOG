"""FUND-ML r1 - a learned ranker on point-in-time XBRL fundamentals (walk-forward only; nothing after 2025-06-29).
Pre-registration: docs/PREREG_fundml_r1_2026-10-08.md. Reuses the XSML r1 harness (tools/xsml_r1.py): prices, universe,
dividends, split quarantine, delisting worst case, book P&L, #463 drawdown weeks, DD5.

    python tools/fundml_r1.py dryload   coverage only - names x months with each input; never a return
    python tools/fundml_r1.py power     the matched-risk null (random beta-neutral books on the eligible names) + DO null
    python tools/fundml_r1.py run       cell + twin + bars + diagnostics, after POWER.txt is committed
    (cwd = the shared checkout; EDGELOG_ROOT = it; XSML_CA = the wide corporate-actions file)
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsml_r1 as X                                                   # noqa: E402

FUND = r"C:\EdgeLog\_research_cache\xbrl_companyfacts\fundamentals_asfiled"
SHARES = r"C:\EdgeLog\_research_cache\xbrl_companyfacts\shares_asfiled_wide.csv"
CIKMAP = [r"C:\EdgeLog\_research_cache\edgar\symbol_cik_map_wide_symbols_siporb_floor_2016_2025.csv",
          r"C:\EdgeLog\_research_cache\edgar\symbol_cik_map_wide_additions_reviewed.csv"]
OUT = r"C:\EdgeLog\custom_ml\fundml_r1"
SEED = 20261008
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "10-KT", "10-KT/A"}
FLOW_MAX, STOCK_MAX = pd.Timedelta(days=456), pd.Timedelta(days=274)     # 15 and 9 months
HGB = dict(X.HGB, random_state=SEED)
COUNTS = {}                                                          # per decision: universe / mapped / shares / eligible
INPUTS = ["bm", "ep", "cfp", "sp", "roe", "gpa", "op", "roa", "ag", "capex", "accr", "shg", "buyb", "divy", "lev",
          "curr", "cash", "rdm", "sga", "mom12", "r21", "vol63", "beta", "ldv"]


# ------------------------------------------------------------------------------------------------ point in time
def load_facts():
    """First-filed value per (cik, concept, start, end); dates parsed; one frame per concept."""
    parts = sorted(glob.glob(os.path.join(FUND, "part-*.parquet")))
    cols = ["cik", "concept", "unit", "val", "start", "end", "form", "filed"]
    F = pd.concat([pd.read_parquet(p, columns=cols) for p in parts], ignore_index=True)
    for c in ("cik", "concept", "unit", "form"):
        F[c] = F[c].astype(str)
    F["cik"] = F.cik.str.lstrip("0")
    F = F[F.unit.isin(["USD", "USD/shares"]) & F.val.notna()]
    F["filed"] = pd.to_datetime(F.filed, errors="coerce")
    F["end"] = pd.to_datetime(F.end, errors="coerce")
    F["start"] = pd.to_datetime(F.start, errors="coerce")
    F = F[F.filed.notna() & F.end.notna() & (F.filed < X.END)]
    F = F.sort_values("filed", kind="stable").drop_duplicates(["cik", "concept", "start", "end"], keep="first")
    F["dur"] = (F.end - F.start).dt.days
    F["annual"] = F.dur.between(350, 380) & F.form.isin(ANNUAL_FORMS)
    return {c: g.drop(columns=["concept"]) for c, g in F.groupby("concept")}


def load_shares():
    S = pd.read_csv(SHARES, usecols=["cik", "concept", "val", "end", "filed"], dtype={"cik": str})
    S["filed"] = pd.to_datetime(S.filed, errors="coerce")
    S["end"] = pd.to_datetime(S.end, errors="coerce")
    S = S[S.filed.notna() & S.end.notna() & (S.filed < X.END) & S.val.notna()]
    S["cik"] = S.cik.str.lstrip("0")
    S = S.sort_values("filed", kind="stable").drop_duplicates(["cik", "concept", "end"], keep="first")
    S["start"] = pd.NaT
    S["annual"] = False
    return {c.split(":")[1]: g.drop(columns=["concept"]) for c, g in S.groupby("concept")}


def latest(tab, t, flow, back=None, max_age=None):
    """Per cik: the latest value known at t (first filed before t); flows = annual facts within 15 months of t,
    stocks = instant facts within 9 months. back=(lo, hi) days: the known fact ending lo..hi days before the CURRENT
    (staleness-checked) one - the year-ago value for growth inputs."""
    if tab is None:
        return pd.Series(dtype=float)
    k = tab[tab.filed < t]
    k = k[k.annual] if flow else k[k.start.isna()]
    fresh = k[k.end >= t - (max_age if max_age is not None else (FLOW_MAX if flow else STOCK_MAX))]
    cur = fresh.sort_values(["end", "filed"]).groupby("cik")[["end", "val"]].last()
    if back is None:
        return cur.val
    kk = k.merge(cur.end.rename("cur_end").reset_index(), on="cik")
    gap = (kk.cur_end - kk.end).dt.days
    kk = kk[(gap >= back[0]) & (gap <= back[1])]
    return kk.sort_values(["end", "filed"]).groupby("cik").val.last()


def pick(facts, names, t, flow, max_age=None):
    out = None
    for n in names:
        s = latest(facts.get(n), t, flow, max_age=max_age)
        out = s if out is None else out.combine_first(s)
    return out if out is not None else pd.Series(dtype=float)


def fundamentals_at(facts, shares, t):
    """Raw (unranked) fundamentals per cik known at decision date t."""
    g = lambda names, flow: pick(facts, names, t, flow)
    d = pd.DataFrame({
        "rev": g(["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"], True),
        "cogs": g(["CostOfRevenue", "CostOfGoodsAndServicesSold"], True),
        "gp": g(["GrossProfit"], True), "sga": g(["SellingGeneralAndAdministrativeExpense"], True),
        "intx": g(["InterestExpense"], True), "ni": g(["NetIncomeLoss"], True),
        "cfo": g(["NetCashProvidedByUsedInOperatingActivities"], True),
        "capex": g(["PaymentsToAcquirePropertyPlantAndEquipment"], True),
        "buyb": g(["PaymentsForRepurchaseOfCommonStock"], True), "divs": g(["PaymentsOfDividends"], True),
        "rd": g(["ResearchAndDevelopmentExpense"], True),
        "assets": g(["Assets"], False), "liab": g(["Liabilities"], False),
        "be": g(["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], False),
        "ca": g(["AssetsCurrent"], False), "cl": g(["LiabilitiesCurrent"], False),
        "cash": g(["CashAndCashEquivalentsAtCarryingValue"], False),
        "assets_1y": latest(facts.get("Assets"), t, False, back=(330, 400)),
        "sh": pick(shares, ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"], t, False,
                   max_age=FLOW_MAX),                                   # MANAGER #81 (1): 15 months, as BUYBACK
        "sh_1y": latest(shares.get("EntityCommonStockSharesOutstanding"), t, False, back=(330, 400),
                        max_age=FLOW_MAX),
    })
    return d


# ------------------------------------------------------------------------------------------------ inputs
def build_inputs(D, FA, FC, dates):
    facts, shares = load_facts(), load_shares()
    cmap = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False)[["symbol", "cik"]] for p in CIKMAP])
    cmap = cmap[cmap.cik != ""].drop_duplicates("symbol", keep="last")
    cmap["cik"] = cmap.cik.str.lstrip("0")
    sym2cik = dict(zip(cmap.symbol, cmap.cik))
    col_cik = pd.Series([sym2cik.get(s) for s in D.syms], index=D.syms)
    frames = {k: pd.DataFrame(np.nan, index=pd.DatetimeIndex(dates), columns=D.syms) for k in INPUTS}
    elig = {}
    for t in dates:
        p = D.pos(t)
        names = np.flatnonzero(D.Un[p])
        f = fundamentals_at(facts, shares, t)
        ck = col_cik.iloc[names]
        R = f.reindex(ck.values)
        R.index = D.syms[names]
        px = D.C.iloc[p, names].to_numpy(float)
        mv = R.sh.to_numpy(float) * px
        mv = np.where(mv > 0, mv, np.nan)
        be = R.be.where(R.be > 0).to_numpy(float)
        a = R.assets.where(R.assets > 0).to_numpy(float)
        exp = R[["cogs", "sga", "intx"]]
        opn = R.rev - exp.fillna(0.0).sum(axis=1)
        opn = opn.where(exp.notna().any(axis=1) & R.rev.notna())
        gp = R.gp.combine_first(R.rev - R.cogs)
        vals = {
            "bm": be / mv, "ep": R.ni.to_numpy(float) / mv, "cfp": R.cfo.to_numpy(float) / mv,
            "sp": R.rev.to_numpy(float) / mv, "roe": R.ni.to_numpy(float) / be, "gpa": gp.to_numpy(float) / a,
            "op": opn.to_numpy(float) / be, "roa": R.ni.to_numpy(float) / a,
            "ag": R.assets.to_numpy(float) / R.assets_1y.where(R.assets_1y > 0).to_numpy(float) - 1.0,
            "capex": R.capex.to_numpy(float) / a, "accr": (R.ni - R.cfo).to_numpy(float) / a,
            "shg": R.sh.to_numpy(float) / R.sh_1y.where(R.sh_1y > 0).to_numpy(float) - 1.0,
            "buyb": R.buyb.to_numpy(float) / mv, "divy": R.divs.to_numpy(float) / mv,
            "lev": R.liab.to_numpy(float) / a, "curr": R.ca.to_numpy(float) / R.cl.where(R.cl > 0).to_numpy(float),
            "cash": R.cash.to_numpy(float) / a, "rdm": R.rd.to_numpy(float) / mv,
            "sga": R.sga.to_numpy(float) / a,
            "mom12": FA["mom12"].iloc[p, names].to_numpy(float), "r21": FA["r21"].iloc[p, names].to_numpy(float),
            "vol63": FA["vol63"].iloc[p, names].to_numpy(float), "beta": FC["beta"].iloc[p, names].to_numpy(float),
            "ldv": FA["ldv"].iloc[p, names].to_numpy(float),
        }
        for k, v in vals.items():
            frames[k].loc[t, D.syms[names]] = np.where(np.isfinite(v), v, np.nan)
        ok = np.isfinite(vals["bm"]) & np.isfinite(vals["op"]) & np.isfinite(vals["ag"])
        elig[t] = names[ok]
        COUNTS[t] = dict(universe=len(names), mapped=int(ck.notna().sum()), shares_ok=int(np.isfinite(mv).sum()),
                         eligible=int(ok.sum()))
        X.log(f"  {t.date()}: universe {len(names)}, mapped {int(ck.notna().sum())}, eligible {int(ok.sum())}")
    return frames, elig


def coverage_lines(dates):
    """MANAGER #81 (1) + (3): share-count misses and the mapped share of the universe by WF (July-June) year."""
    c = pd.DataFrame(COUNTS).T.reindex(dates)
    c["mapped_share"] = c.mapped / c.universe
    yrs, flag = [], []
    for y in range(2017, 2025):
        k = c[(c.index >= f"{y}-07-01") & (c.index <= f"{y + 1}-06-30")]
        if len(k):
            v = float(k.mapped_share.mean())
            yrs.append(f"{y}/{(y + 1) % 100:02d} {v:.1%}")
            if v < 0.85 and y >= 2017:
                flag.append(f"{y}/{(y + 1) % 100:02d}")
    lines = [f"mapped share of the universe by July-June year: {', '.join(yrs)}",
             f"names with a usable share count (first filed before t, period end within 15 months): median "
             f"{int(c.shares_ok.median())} of {int(c.mapped.median())} mapped; eligible median {int(c.eligible.median())}"]
    if flag:
        lines.append("UNIVERSE SURVIVOR-TILTED IN " + ", ".join(flag) + " (mapped share under 85%; the twin carries the same tilt)")
    return lines


def rank_rows(frames, t, names_sym):
    return X.xs_rank(frames, t, names_sym)


# ------------------------------------------------------------------------------------------------ model
def model_scores(D, frames, elig, dates, horizon=21):
    from sklearn.ensemble import HistGradientBoostingRegressor
    target = X.fwd_rank(D, horizon)
    rows = {t: (elig[t], rank_rows(frames, t, D.syms[elig[t]])) for t in dates}
    preds, fits = {}, {}
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
                ex = pu + 1 + horizon
                if ex >= len(D.dates) or D.dates[ex] >= cut:
                    continue
                names, Xu = rows[u]
                y = target(pu, names)
                ok = np.isfinite(y)
                if ok.sum() > 50:
                    Xs.append(Xu[ok]); ys.append(y[ok])
            fits[Y] = HistGradientBoostingRegressor(**HGB).fit(np.vstack(Xs), np.concatenate(ys))
            X.log(f"  refit {Y}: {sum(len(y) for y in ys):,} rows from {len(Xs)} decisions")
        names, Xt = rows[t]
        preds[t] = (names, fits[Y].predict(Xt))
    return preds


def twin_scores(D, frames, elig, dates):
    out = {}
    for t in dates:
        names = elig[t]
        r = X.xs_rank({"bm": frames["bm"], "op": frames["op"], "ag": -frames["ag"]}, t, D.syms[names])
        out[t] = (names, np.nanmean(r, axis=1))
    return out


# ------------------------------------------------------------------------------------------------ steps
def setup():
    ca = X.ca_path_required()
    D = X.Data(ca)
    FA, FC, beta, wk, mo = X.build(D)
    w = X.wf_decisions(D, mo)
    pre = [t for t in mo if D.dates[D.pos(t) + 1] < X.WF0 and t.year >= 2017]
    dates = sorted(set(pre) | set(w))
    frames, elig = build_inputs(D, FA, FC, dates)
    return D, beta, frames, elig, dates, w


def dryload():
    os.makedirs(OUT, exist_ok=True)
    D, beta, frames, elig, dates, w = setup()
    cov = pd.DataFrame({k: [int(frames[k].loc[t].notna().sum()) for t in dates] for k in INPUTS}, index=dates)
    cov["universe"] = [int(D.Un[D.pos(t)].sum()) for t in dates]
    cov["eligible"] = [len(elig[t]) for t in dates]
    cov.to_csv(os.path.join(OUT, "coverage.csv"))
    print(cov.describe().loc[["min", "50%", "max"]].round(0).to_string())
    print("\n".join(coverage_lines([t for t in dates if t in w])))


def books_of(D, scores, dates, beta, n=X.N_SIDE, sign=-1.0):
    """scores: higher = better -> long the top n (side_books longs the LOWEST of `score`, so pass -score)."""
    return [(t, X.side_books(D, t, scores[t][0], sign * scores[t][1], n=n, beta=beta[D.pos(t)])) for t in dates]


def power():
    os.makedirs(OUT, exist_ok=True)
    D, beta, frames, elig, dates, w = setup()
    w463, days, weeks, _, _ = X.book463_ddweeks()
    rng = np.random.default_rng(SEED)
    roc, roc_net, do = [], [], []
    for _ in range(X.N_SHUF):
        books = [(t, X.side_books(D, t, elig[t], rng.random(len(elig[t])), beta=beta[D.pos(t)])) for t in w]
        x = X.periodic_book(D, books)
        roc.append(X.roc_sortino(x)[0])
        roc_net.append(X.roc_sortino(X.periodic_book(D, books, X.COST, X.BORROW))[0])
        do.append(X.dd_stats(x, w463, days, weeks)[1])
    roc, roc_net, do = np.array(roc), np.array(roc_net), np.array(do)
    p50, p95 = float(np.median(roc)), float(np.percentile(roc, 95))
    lines = [f"FUND-ML r1 POWER LINE (no cell or twin P&L read): {len(w)} monthly WF decisions; 1,000 random beta-neutral "
             f"books on the eligible names (seed {SEED}).",
             f"  null (GROSS - the cell is judged NET against it, deliberately conservative): WF ROC @ $30k 50th {p50:+.1f}, "
             f"95th {p95:+.1f}; for the record, the NET null's 95th {np.percentile(roc_net, 95):+.1f}; DO 95th "
             f"{np.percentile(do, 95):+.3f}",
             f"  MDE in own money: the smallest lead over a random book this test can see is about "
             f"${(p95 - p50) * 1000:,.0f} a year at a $30k drawdown (95th minus 50th, $1,000 a year per ROC point); the "
             f"map bar (ROC 15) is $15,000 a year."] + ["  " + l for l in coverage_lines(w)]
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "POWER.txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame({"roc": roc, "roc_net": roc_net, "do": do}).to_csv(os.path.join(OUT, "nulls.csv"), index=False)


def run():
    assert os.path.exists(os.path.join(OUT, "POWER.txt")), "run `power` first and commit POWER.txt"
    nl = pd.read_csv(os.path.join(OUT, "nulls.csv"))
    null95, do95 = float(np.percentile(nl.roc, 95)), float(np.percentile(nl["do"], 95))
    D, beta, frames, elig, dates, w = setup()
    w463, days, weeks, _, _ = X.book463_ddweeks()
    T = len(D.dates)
    P = model_scores(D, frames, elig, dates)
    TW = twin_scores(D, frames, elig, w)
    wd = [t for t in w if t in P]
    books = books_of(D, P, wd, beta)
    twin = books_of(D, TW, wd, beta)
    acc, acc0 = X.Acc(T), X.Acc(T)
    net = X.periodic_book(D, books, X.COST, X.BORROW, acc=acc)
    X.periodic_book(D, books, X.COST, X.BORROW, acc=acc0, delist="short0")
    nbrs = {f"n={n}": X.roc_sortino(X.periodic_book(D, books_of(D, P, wd, beta, n=n), X.COST, X.BORROW))[0]
            for n in (25, 100)}
    pfv = np.asarray(acc.name_periods, float)
    pf = float(pfv[pfv > 0].sum() / -pfv[pfv < 0].sum())
    info = dict(decisions=len(books), positions=sum(len(b) for _, b in books))
    # FUND-ML's earner route is open (prereg): judge() grants it to names starting with "C"
    lines, ok = X.judge("C FUND-ML", D, net, X.periodic_book(D, books, X.COST_STRESS, X.BORROW),
                        X.periodic_book(D, books), X.periodic_book(D, twin, X.COST, X.BORROW), null95, w463, days, weeks,
                        info, pf, nbrs, acc, X.periodic_book(D, books, X.COST, X.BORROW, delist="long0"),
                        pd.Series(acc0.short, index=D.dates), do95)
    # diagnostics (standing order addendum 2 (2))
    tw = X.periodic_book(D, twin, X.COST, X.BORROW)
    rt, st = X.roc_sortino(tw)
    from augur_engine.drawdowns import dd5
    d5t = dd5(tw[(tw.index >= X.WF0) & (tw.index <= X.WF1)])
    curve = {c: X.roc_sortino(X.periodic_book(D, books, c / 1e4, X.BORROW))[0] for c in (0, 5, 10, 20)}
    fills = [D.pos(t) + 1 for t, _ in books]
    ev = np.zeros(25)
    cnt = np.zeros(25)
    for k, f in enumerate(fills):
        e = fills[k + 1] if k + 1 < len(fills) else T
        seg = net.iloc[f:e].to_numpy()[:25]
        ev[:len(seg)] += seg; cnt[:len(seg)] += 1
    path = np.cumsum(ev / np.maximum(cnt, 1))
    wf = net[(net.index >= X.WF0) & (net.index <= X.WF1)]
    halves = (float(wf[wf.index <= "2021-12-31"].sum()), float(wf[wf.index >= "2022-01-01"].sum()))
    m = D.mkt.reindex(wf.index).fillna(0.0)
    beta_mkt = float(np.cov(wf, m)[0, 1] / m.var()) / (2 * X.GROSS) if m.var() > 0 else float("nan")
    top_eps = dd5(w463)["episodes"]                                   # #463's five deepest WF drawdowns
    ep_rows = [f"{pd.Timestamp(e['peak']).date()}..{pd.Timestamp(e['trough']).date()} (#463 -${e['depth']:,.0f}): "
               f"cell ${float(net[(net.index > pd.Timestamp(e['peak'])) & (net.index <= pd.Timestamp(e['trough']))].sum()):,.0f}"
               for e in top_eps]
    lines += [f"  TWIN (B/M + operating profitability - asset growth composite, for FRONTIER): net WF ROC {rt:.1f} / "
              f"{st:.2f}; worst DD ${d5t['max_dd']:,.0f} DD5 ${d5t['dd5_usd']:,.0f}",
              "  cost curve (net WF ROC @ $30k at 0 / 5 / 10 / 20 bps a side): "
              + " / ".join(f"{v:.1f}" for v in curve.values()),
              "  event-time path (mean cumulative $ by session since the fill, sessions 1, 5, 10, 15, 20): "
              + ", ".join(f"{path[i]:,.0f}" for i in (0, 4, 9, 14, 19)),
              "  #463's five deepest WF drawdowns, cell P&L inside each: " + "; ".join(ep_rows),
              f"  regime halves (2018-21 / 2022-25): ${halves[0]:,.0f} / ${halves[1]:,.0f}; beta to the equal-weight "
              f"universe (per $ gross): {beta_mkt:+.3f}",
              f"  mapped / eligible names by month (median): universe {int(np.median([D.Un[D.pos(t)].sum() for t in wd]))}"
              f", eligible {int(np.median([len(elig[t]) for t in wd]))}"]
    lines += ["  " + l for l in coverage_lines(wd)]
    lines.append("\nSTAGE A: " + ("FUND-ML PASSES -> hand audit of the 30 names, then MANAGER" if ok else
                                   "FUND-ML dead (no variants)") + " - walk-forward only; nothing after 2025-06-29 loaded")
    txt = open(os.path.join(OUT, "POWER.txt"), encoding="utf-8").read().rstrip() + "\n" + "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "STAGE_A.txt"), "w", encoding="utf-8").write(txt + "\n")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"dryload": dryload, "power": power, "run": run}.get(mode, lambda: sys.exit("usage: fundml_r1.py dryload | power | run"))()
