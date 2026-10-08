"""EARN-FCST r1 - a learned forecaster of the direction of next fiscal-year earnings from detailed XBRL line items
(Chen, Cho, Dou & Lev 2022), traded monthly as a beta-neutral long-short book on the top-500 stock universe (walk-forward
only; nothing after 2025-06-29). Pre-registration: docs/PREREG_earnfcst_r1_2026-10-08.md. Reuses FUND-ML r1's loaders
and point-in-time rules (tools/fundml_r1.py, addenda 1-2) and the XSML r1 harness (tools/xsml_r1.py).

    python tools/earnfcst_r1.py dryload   concept list (fixed on 2010-2017 filings), firm-year and coverage counts, the
                                          label's base rate (accounting only) - never a return
    python tools/earnfcst_r1.py power     the null (random beta-neutral books on the eligible names)
    python tools/earnfcst_r1.py run <sha prereg>,<sha earnfcst_r1.py>,<sha fundml_r1.py>,<sha xsml_r1.py>
    (cwd = the shared checkout; EDGELOG_ROOT = it; XSML_CA = the wide corporate-actions file)
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsml_r1 as X                                                   # noqa: E402
import fundml_r1 as F                                                 # noqa: E402

DET = r"C:\EdgeLog\_research_cache\xbrl_companyfacts\fundamentals_detailed"
CAL = r"C:\EdgeLog\_research_cache\edgar\earnings_calendar_ndx.csv"
OUT = r"C:\EdgeLog\custom_ml\earnfcst_r1"
PREREG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "PREREG_earnfcst_r1_2026-10-08.md")
SEED = 20261008
LAG = 10                                   # a firm-year is used only if its 10-K was first filed >= 10 sessions before t
COVER = 0.05                               # concepts present in >= 5% of the 2010-2017 firm-years
GAP = (330, 400)                           # prior / next fiscal year: period end 330-400 days away
HGB = F.HGB
COLS = ["cik", "concept", "val", "start", "end", "filed"]


# ------------------------------------------------------------------------------------------------ firm-years
def _part(p, keep=None):
    d = pd.read_parquet(p, columns=COLS)
    if keep is not None:
        d = d[d.concept.isin(keep)]
    d = d.assign(cik=d.cik.astype(str).str.lstrip("0"), concept=d.concept.astype(str))
    for c in ("start", "end", "filed"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    d = d[d.filed.notna() & d.end.notna() & d.val.notna() & (d.filed < X.END)]
    d = d.sort_values("filed", kind="stable").drop_duplicates(["cik", "concept", "start", "end"], keep="first")
    dur = (d.end - d.start).dt.days
    return d[d.start.isna() | dur.between(350, 380)]                  # balance-sheet instants or ANNUAL flows only


def _years(d):
    """Firm-years: one per (cik, fiscal year end) of an annual NetIncomeLoss fact, dated by its FIRST filing."""
    ni = d[(d.concept == "NetIncomeLoss") & d.start.notna()]
    return ni.sort_values("filed", kind="stable").drop_duplicates(["cik", "end"])[["cik", "end", "filed"]] \
        .rename(columns={"end": "fye", "filed": "row_filed"})


def select_concepts():
    """Concepts present in >= COVER of the firm-years whose 10-K was first filed in 2010-2017 (fixed before any number)."""
    n_fy, cnt = 0, {}
    for p in sorted(glob.glob(os.path.join(DET, "part-*.parquet"))):
        d = _part(p)
        fy = _years(d)
        fy = fy[(fy.row_filed >= "2010-01-01") & (fy.row_filed < "2018-01-01")]
        n_fy += len(fy)
        m = d.merge(fy, left_on=["cik", "end"], right_on=["cik", "fye"])
        m = m[m.filed <= m.row_filed]
        for c, n in m.drop_duplicates(["cik", "fye", "concept"]).groupby("concept").size().items():
            cnt[c] = cnt.get(c, 0) + int(n)
    keep = sorted(c for c, n in cnt.items() if n >= COVER * n_fy)
    return keep, n_fy, len(cnt)


def firm_years(keep):
    """Wide table: (cik, fye) x kept concepts, each fact first filed no later than the row's 10-K; + row_filed."""
    ks = set(keep) | {"NetIncomeLoss", "Assets"}
    out = []
    for p in sorted(glob.glob(os.path.join(DET, "part-*.parquet"))):
        d = _part(p, ks)
        fy = _years(d)
        m = d.merge(fy, left_on=["cik", "end"], right_on=["cik", "fye"])
        m = m[m.filed <= m.row_filed].drop_duplicates(["cik", "fye", "concept"])
        W = m.pivot_table(index=["cik", "fye"], columns="concept", values="val", aggfunc="first")
        out.append(W.join(fy.set_index(["cik", "fye"]).row_filed, how="inner"))
    W = pd.concat(out).sort_index()
    W = W[W.Assets > 0] if "Assets" in W else W
    return W


def design(W, keep):
    """Features (level / assets, change / assets, log assets), the label (next fiscal year's net income higher) and the
    date the label became known (the next 10-K's first filing)."""
    W = W.reset_index().sort_values(["cik", "fye"])
    a = W.Assets.to_numpy(float)
    lev = W[keep].to_numpy(float) / a[:, None]
    prev_i = np.full(len(W), -1)
    next_i = np.full(len(W), -1)
    ck, fe = W.cik.to_numpy(), W.fye.to_numpy()
    for i in range(1, len(W)):
        if ck[i] == ck[i - 1]:
            g = (fe[i] - fe[i - 1]) / np.timedelta64(1, "D")
            if GAP[0] <= g <= GAP[1]:
                prev_i[i] = i - 1
                next_i[i - 1] = i
    raw = W[keep].to_numpy(float)
    chg = np.full_like(raw, np.nan)
    hp = prev_i >= 0
    chg[hp] = (raw[hp] - raw[prev_i[hp]]) / a[hp, None]
    Xf = np.hstack([lev, chg, np.log(a)[:, None]])
    ni = W.NetIncomeLoss.to_numpy(float)
    hn = next_i >= 0
    y = np.full(len(W), np.nan)
    y[hn] = (ni[next_i[hn]] > ni[hn]).astype(float)
    lab_filed = pd.Series(pd.NaT, index=W.index)
    lab_filed[hn] = W.row_filed.to_numpy()[next_i[hn]]
    ni_prev = np.full(len(W), np.nan)
    ni_prev[hp] = ni[prev_i[hp]]
    meta = W[["cik", "fye", "row_filed"]].assign(label_filed=lab_filed.to_numpy(), ni=ni, ni_prev=ni_prev)
    return Xf, y, meta.reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ model
def refit_models(Xf, y, meta, years):
    """One classifier per WF year Y: trained on every firm-year whose LABEL was first filed before 1 January Y."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    fits = {}
    for Y in years:
        cut = pd.Timestamp(f"{Y}-01-01")
        tr = (meta.label_filed < cut).to_numpy() & np.isfinite(y)
        fits[Y] = HistGradientBoostingClassifier(**HGB).fit(Xf[tr], y[tr].astype(int))
        X.log(f"  refit {Y}: {int(tr.sum()):,} firm-years, base rate {y[tr].mean():.3f}")
    return fits


def oos_auc(fits, Xf, y, meta):
    """Each year's model on the firm-years first filed during that year (none of them in its training set)."""
    from sklearn.metrics import roc_auc_score, accuracy_score
    out = {}
    for Y, m in fits.items():
        k = ((meta.row_filed >= f"{Y}-01-01") & (meta.row_filed < f"{Y + 1}-01-01")).to_numpy() & np.isfinite(y)
        if k.sum() > 50 and 0 < y[k].sum() < k.sum():
            p = m.predict_proba(Xf[k])[:, 1]
            out[Y] = (float(roc_auc_score(y[k], p)), float(accuracy_score(y[k], p > 0.5)), int(k.sum()))
    return out


# ------------------------------------------------------------------------------------------------ signal
def setup(with_model=False):
    ca = X.ca_path_required()
    D = X.Data(ca, floor_raw=True)
    FA, FC, beta, wk, mo = X.build(D)
    w = X.wf_decisions(D, mo)
    keep, n_fy, n_seen = select_concepts()
    W = firm_years(keep)
    Xf, y, meta = design(W, keep)
    cmap = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False)[["symbol", "cik"]] for p in F.CIKMAP])
    cmap = cmap[cmap.cik != ""].drop_duplicates("symbol", keep="last")
    sym2cik = dict(zip(cmap.symbol, cmap.cik.str.lstrip("0")))
    col_cik = pd.Series([sym2cik.get(s) for s in D.syms], index=D.syms)
    shares = F.load_shares()
    fits = refit_models(Xf, y, meta, sorted({D.dates[D.pos(t) + 1].year for t in w})) if with_model else None
    rf = meta.row_filed.to_numpy()
    fye = meta.fye.to_numpy()
    by_cik = meta.groupby("cik").indices
    cell, twin, elig = {}, {}, {}
    for t in w:
        p = D.pos(t)
        cut = D.dates[p - LAG]
        names = np.flatnonzero(D.Un[p])
        ck = col_cik.iloc[names].to_numpy()
        rows = np.full(len(names), -1)
        for j, c in enumerate(ck):
            ix = by_cik.get(c) if c is not None else None
            if ix is None:
                continue
            ok = ix[(rf[ix] < cut) & (fye[ix] >= np.datetime64(t - F.FLOW_MAX))]
            if len(ok):
                rows[j] = ok[np.argmax(fye[ok])]
        have = rows >= 0
        elig[t] = names[have]
        sh = F.pick(shares, ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"], t, False,
                    max_age=F.FLOW_MAX)
        mv = sh.reindex(ck[have]).to_numpy(float) * D.Craw.iloc[p, names[have]].to_numpy(float)
        r = rows[have]
        twin[t] = (names[have], (meta.ni.to_numpy()[r] - meta.ni_prev.to_numpy()[r]) / np.where(mv > 0, mv, np.nan))
        if fits is not None:
            Y = D.dates[p + 1].year
            cell[t] = (names[have], fits[Y].predict_proba(Xf[r])[:, 1])
        F.COUNTS[t] = dict(universe=len(names), mapped=int(pd.notna(ck).sum()), shares_ok=int(np.isfinite(mv).sum()),
                           eligible=int(have.sum()))
    info = dict(keep=keep, n_fy=n_fy, n_seen=n_seen, Xf=Xf, y=y, meta=meta, fits=fits)
    return D, beta, w, elig, cell, twin, info


def books_of(D, scores, dates, beta, n=X.N_SIDE):
    """scores = goodness (P(earnings up), or the twin's change / MV): long the top n -> pass -score to side_books."""
    return [(t, X.side_books(D, t, scores[t][0], -scores[t][1], n=n, beta=beta[D.pos(t)])) for t in dates]


def announce_months(D):
    """(cik, period) of an earnings release: TV's item-2.02 calendar for its names, else the month of a 10-Q / 10-K
    first filing (XBRL `filed`) - a proxy (the 10-Q usually lands within weeks of the release)."""
    s = set()
    cal = pd.read_csv(CAL, dtype=str)
    dc = next(c for c in cal.columns if "accept" in c.lower())
    for c, a in zip(cal.cik.str.lstrip("0"), pd.to_datetime(cal[dc], errors="coerce", utc=True)):
        if pd.notna(a):
            s.add((c, a.tz_convert(None).to_period("M")))
    cal_ciks = set(cal.cik.str.lstrip("0"))
    fa = F.load_facts().get("NetIncomeLoss")
    fa = fa[~fa.cik.isin(cal_ciks)]
    for c, f in zip(fa.cik, fa.filed):
        s.add((c, f.to_period("M")))
    return s


# ------------------------------------------------------------------------------------------------ steps
def dryload():
    os.makedirs(OUT, exist_ok=True)
    D, beta, w, elig, cell, twin, info = setup()
    y, meta = info["y"], info["meta"]
    print(f"concepts seen {info['n_seen']:,}; kept (>= {COVER:.0%} of {info['n_fy']:,} firm-years first filed 2010-2017) "
          f"{len(info['keep'])}; features {info['Xf'].shape[1]}")
    print(f"firm-years {len(meta):,} ({meta.cik.nunique():,} CIKs); with a label {int(np.isfinite(y).sum()):,}, base rate "
          f"(next year's NI higher) {np.nanmean(y):.3f}")
    print("eligible names by month: median " + str(int(np.median([len(elig[t]) for t in w]))) + ", min "
          + str(min(len(elig[t]) for t in w)) + "; twin finite median "
          + str(int(np.median([np.isfinite(twin[t][1]).sum() for t in w]))))
    print("\n".join(F.coverage_lines(w)))
    open(os.path.join(OUT, "CONCEPTS.txt"), "w", encoding="utf-8").write("\n".join(info["keep"]) + "\n")


def power():
    os.makedirs(OUT, exist_ok=True)
    D, beta, w, elig, cell, twin, info = setup()
    w463, days, weeks, _, _ = X.book463_ddweeks()
    rng = np.random.default_rng(SEED)
    roc, roc_net, do = [], [], []
    for _ in range(X.N_SHUF):
        books = [(t, X.side_books(D, t, elig[t], rng.random(len(elig[t])), beta=beta[D.pos(t)])) for t in w]
        x = X.periodic_book(D, books)
        roc.append(X.roc_sortino(x)[0])
        roc_net.append(X.roc_sortino(X.periodic_book(D, books, X.COST, X.BORROW))[0])
        do.append(X.dd_stats(x, w463, days, weeks)[1])
    roc, roc_net, do = map(np.array, (roc, roc_net, do))
    p50, p95 = float(np.median(roc)), float(np.percentile(roc, 95))
    lines = [f"EARN-FCST r1 POWER LINE (no cell or twin P&L read): {len(w)} monthly WF decisions; 1,000 random beta-neutral "
             f"books on the eligible names (seed {SEED}); {len(info['keep'])} concepts kept.",
             f"  null (GROSS - the cell is judged NET against it, deliberately conservative): WF ROC @ $30k 50th {p50:+.1f}, "
             f"95th {p95:+.1f}; for the record, the NET null's 95th {np.percentile(roc_net, 95):+.1f}; DO 95th "
             f"{np.percentile(do, 95):+.3f}",
             f"  MDE in own money: about ${(p95 - p50) * 1000:,.0f} a year at a $30k drawdown (95th minus 50th); the map "
             f"bar (ROC 15) is $15,000 a year."] + ["  " + l for l in F.coverage_lines(w)]
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "POWER.txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame({"roc": roc, "roc_net": roc_net, "do": do}).to_csv(os.path.join(OUT, "nulls.csv"), index=False)


def run(expect=None):
    here = os.path.dirname(os.path.abspath(__file__))
    F.frozen_check(PREREG, [os.path.join(here, f) for f in ("earnfcst_r1.py", "fundml_r1.py", "xsml_r1.py")], expect)
    assert os.path.exists(os.path.join(OUT, "POWER.txt")), "run `power` first and commit POWER.txt"
    nl = pd.read_csv(os.path.join(OUT, "nulls.csv"))
    null95, do95 = float(np.percentile(nl.roc, 95)), float(np.percentile(nl["do"], 95))
    D, beta, w, elig, cell, twin, info = setup(with_model=True)
    w463, days, weeks, _, _ = X.book463_ddweeks()
    T = len(D.dates)
    books = books_of(D, cell, w, beta)
    tbooks = books_of(D, twin, w, beta)
    acc, acc0 = X.Acc(T), X.Acc(T)
    net = X.periodic_book(D, books, X.COST, X.BORROW, acc=acc)
    X.periodic_book(D, books, X.COST, X.BORROW, acc=acc0, delist="short0")
    tw = X.periodic_book(D, tbooks, X.COST, X.BORROW)
    nbrs = {f"n={n}": X.roc_sortino(X.periodic_book(D, books_of(D, cell, w, beta, n=n), X.COST, X.BORROW))[0]
            for n in (25, 100)}
    pfv = np.asarray(acc.name_periods, float)
    pf = float(pfv[pfv > 0].sum() / -pfv[pfv < 0].sum())
    inf = dict(decisions=len(books), positions=sum(len(b) for _, b in books))
    lines, ok = X.judge("A EARN-FCST", D, net, X.periodic_book(D, books, X.COST_STRESS, X.BORROW),
                        X.periodic_book(D, books), tw, null95, w463, days, weeks, inf, pf, nbrs, acc,
                        X.periodic_book(D, books, X.COST, X.BORROW, delist="long0"), pd.Series(acc0.short, index=D.dates),
                        do95)
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
               for e in top_eps]
    # boundary 4 (STRATEGY-BEATING #83): gross name-period P&L split by whether the hold contains an announcement month
    ann = announce_months(D)
    cmap = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False)[["symbol", "cik"]] for p in F.CIKMAP])
    cmap = cmap[cmap.cik != ""].drop_duplicates("symbol", keep="last")
    s2c = dict(zip(cmap.symbol, cmap.cik.str.lstrip("0")))
    col_cik = {j: s2c.get(s) for j, s in enumerate(D.syms)}
    split = {True: 0.0, False: 0.0}
    nsplit = {True: 0, False: 0}
    for k, (t, b) in enumerate(books):
        f = D.pos(t) + 1
        e = fills[k + 1] if k + 1 < len(fills) else T - 1
        mon = {D.dates[i].to_period("M") for i in range(f, e + 1)}
        for j, dol in b.items():
            r = X.fwd_total(D, f - 1, np.array([j]), e - f)[0]
            if not np.isfinite(r):
                continue
            a_ = any((col_cik.get(j), mm) in ann for mm in mon)
            split[a_] += dol * r; nsplit[a_] += 1
    au = oos_auc(info["fits"], info["Xf"], info["y"], info["meta"])
    lines += [f"  TWIN (annual earnings change / market value, SUE-style, for STRATEGY-BEATING): net WF ROC {rt:.1f} / "
              f"{st:.2f}; worst DD ${d5t['max_dd']:,.0f} DD5 ${d5t['dd5_usd']:,.0f}",
              "  classifier out of sample (firm-years first filed in year Y, Y's model): "
              + ", ".join(f"{Y} AUC {a:.3f} acc {c:.3f} (n {n:,})" for Y, (a, c, n) in au.items()),
              "  cost curve (net WF ROC @ $30k at 0 / 5 / 10 / 20 bps a side): " + " / ".join(f"{v:.1f}" for v in curve.values()),
              "  event-time path (mean cumulative $ by session since the fill, sessions 1, 5, 10, 15, 20): "
              + ", ".join(f"{path[i]:,.0f}" for i in (0, 4, 9, 14, 19)),
              "  #463's five deepest WF drawdowns, cell P&L inside each: " + "; ".join(ep_rows),
              f"  beta to the equal-weight universe (per $ gross): {beta_mkt:+.3f}",
              f"  ANNOUNCEMENT SPLIT (SB boundary 4, gross name-periods): holds containing a release month "
              f"${split[True]:,.0f} ({nsplit[True]:,}), others ${split[False]:,.0f} ({nsplit[False]:,}); EAP correlation "
              f"reported when EAP r1 has a verdict"]
    lines += ["  " + l for l in F.coverage_lines(w)]
    lines.append("\nSTAGE A: " + ("EARN-FCST PASSES -> hand audit of the 30 names, then MANAGER" if ok else
                                   "EARN-FCST dead (no variants)") + " - walk-forward only; nothing after 2025-06-29 loaded")
    txt = open(os.path.join(OUT, "POWER.txt"), encoding="utf-8").read().rstrip() + "\n" + "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "STAGE_A.txt"), "w", encoding="utf-8").write(txt + "\n")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "run":
        run(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        {"dryload": dryload, "power": power}.get(mode, lambda: sys.exit(__doc__))()
