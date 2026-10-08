# -*- coding: utf-8 -*-
"""VRPES r1 STAGE A - the variance risk premium as monthly ES timing (docs/PREREG_vrpes_r1_2026-10-07.md + ADDENDUM 1;
TTM scope rank 5, opened by MANAGER 2026-10-07; MANAGER review C:/EdgeLog/manager/reviews/REVIEW_VRPES_JUMPSPLIT_2026-10-07.md).

A high variance risk premium (implied minus realized variance) forecasts equity returns over the next months (Bollerslev,
Tauchen & Zhou 2009 RFS; Bekaert & Hoerova 2014 JoE). Rule: VRP(d) = VIX close(d)^2 - RV22(d), RV22 = the last 22 ES
sessions' realized variance, annualised, in VIX points squared. RV per session (ADDENDUM 1, edits 1-2) = the squared
OVERNIGHT return (the ADJ 30m close-to-open point gap / the prior session's no-adjust close; exact across rolls) + the sum
of squared 5m RTH log returns over EVERY bar present (a return across a missing bar counts as one return; the first from
the first bar's open). If the latest VRP dated STRICTLY BEFORE a month's first session is in the top tercile of the 756
VRP days before it: LONG 1 ES at that session's 09:30 open, out at the month's last session close; flat otherwise.
Cost 0.363 pt a round trip + one more for each real ES switch (tools/data/rolls_ES.csv) held through; $50 a point.

Bars on the WORSE of lag 1 (the primary) and lag 2. Binding null = CIRCULAR SHIFT of the 108-month WF state vector (k =
12 .. 96, exhaustive, each lag's own vector), p printed as a rank out of 86. Binding twins: ALWAYS LONG (RISK r1 trio) and
VIX^2 alone (A6). Every ROC @ $30k prints its DD5.

  python tools/vrpes_r1_stageA.py --predata  -> RV coverage, the schedule with every in-month's inputs, counts, twins'
                                                overlap, the power line and its own-$/yr conversion (no real direction)
  python tools/vrpes_r1_stageA.py            -> Stage A (refuses unless the prereg is on origin/main)
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HOME = os.environ.get("EDGELOG_HOME") or "C:/EdgeLog"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
import halfhour_r1_stageA as HH                                         # noqa: E402
import ttm_r1_common as TC                                              # noqa: E402

COST, M = 0.363, 50.0
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
EARLY0, EARLY1 = pd.Timestamp("2013-08-01"), pd.Timestamp("2016-06-30")
RVN, LOOK, NBAR = 22, 756, 78
CUTS = {"tercile": 2.0 / 3.0, "quartile": 3.0 / 4.0}                    # top tercile = PRIMARY, top quartile = neighbour
LAGS = (1, 2)
SHIFTS = range(12, 97)
NULL_DRAWS, SEED = 1000, 20261007
PUB = os.path.join(HOME, "_research_cache", "public_series")
PREREG = "docs/PREREG_vrpes_r1_2026-10-07.md"
DRY = "--dryrun" in sys.argv          # smoke test of the Stage A code on COIN-FLIP sides per month: no real direction
HALT_DAYS = [pd.Timestamp(d) for d in ("2020-03-09", "2020-03-12", "2020-03-16", "2020-03-18")]


def photo(name, col):
    raw = os.path.join(PUB, "cboe", name)
    prov = json.load(open(os.path.join(PUB, "public_series_provenance.json"), encoding="utf-8"))["cboe\\" + name]
    assert hashlib.sha256(open(raw, "rb").read()).hexdigest() == prov["sha256"], name + " is not the photograph - abort"
    v = pd.read_csv(raw)
    v.columns = [c.strip().upper() for c in v.columns]
    v["DATE"] = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    return v[v["DATE"] <= WF1].set_index("DATE")[col].astype(float), prov, raw


def sessions(sym, tf, src):
    A = load_master_arrays(find_master(sym, tf, "rth", src), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"]).tz_localize(None)
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    return A, ts


def realized():
    """Per ES session with any 5m RTH bar: RTH realized variance over every bar present, bar count, no-adjust last close."""
    A, ts = sessions("ES", "5m", "db_noadj_rth")
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    ok = (k >= 0) & (k < NBAR)
    df = pd.DataFrame({"d": ts.normalize()[ok], "k": k[ok], "o": np.asarray(A["open"], float)[ok],
                       "c": np.asarray(A["close"], float)[ok]}).dropna().sort_values(["d", "k"])
    rows = []
    for d, g in df.groupby("d", sort=True):
        px = np.r_[g["o"].iloc[0], g["c"].to_numpy()]
        r = np.diff(np.log(px))
        rows.append((d, float((r ** 2).sum()), len(g), float(g["o"].iloc[0]), float(g["c"].iloc[-1]), int(g["k"].iloc[0]),
                     int(g["k"].iloc[-1])))
    return pd.DataFrame(rows, columns=["d", "rv_rth", "nbars", "o_noadj", "c_noadj", "k0", "k1"]).set_index("d")


def build():
    vix, pv, vraw = photo("VIX_History.csv", "CLOSE")
    R = realized()
    # DROP rule (MANAGER 10-07): the photograph carries VIX rows on CME US-holiday sessions (stock market closed) from
    # 2022 on. A holiday session ends with the 12:55 or 13:00 bar, complete from 09:30 (the CME schedule). Those VIX rows
    # are dropped, so no VRP value is ever dated on a holiday; the holiday session's own returns stay in RV.
    hol = R.index[(R["k0"] == 0) & R["k1"].isin([41, 42]) & (R["nbars"] == R["k1"] + 1)]
    dropped = vix.index[vix.index.isin(hol)]
    vix = vix[~vix.index.isin(hol)]
    A, ts = sessions("ES", "30m", "db_adj_rth")
    df = pd.DataFrame({"d": ts.normalize(), "o": np.asarray(A["open"], float), "c": np.asarray(A["close"], float)})
    g = df.groupby("d", sort=True)
    days = pd.DatetimeIndex(g.o.first().index)
    O, C = g.o.first().to_numpy(), g.c.last().to_numpy()
    # overnight: ADJ point gap (exact across rolls) over the prior session's no-adjust close
    cn = R["c_noadj"].reindex(days).to_numpy()
    on = np.full(len(days), np.nan)
    on[1:] = np.log1p((O[1:] - C[:-1]) / cn[:-1])
    R["r_on2"] = pd.Series(on ** 2, index=days).reindex(R.index)
    rv_full = (R["rv_rth"] + R["r_on2"]).dropna()
    series = {}
    for lab, rvd in (("VRP", rv_full), ("VRP_RTH", R["rv_rth"])):
        rv22 = (rvd.rolling(RVN).sum() * (252.0 / RVN) * 1e4).dropna()
        series[lab] = (vix.reindex(rv22.index) ** 2 - rv22).dropna()
        series[lab + "_rv22"] = rv22
    series["VIX"] = vix.reindex(series["VRP"].index).dropna()            # the VIX-alone twin on the same dates
    ym = days.year * 12 + days.month - 1
    starts = np.r_[0, np.flatnonzero(np.diff(ym)) + 1]
    ends = np.r_[starts[1:] - 1, len(days) - 1]
    sig, used = {}, {}
    for lab in ("VRP", "VRP_RTH", "VIX"):
        s = series[lab]
        vv, vi = s.to_numpy(), s.index
        for lag in LAGS:
            pct = np.full(len(starts), np.nan)
            u = np.full(len(starts), -1)
            for j, st in enumerate(starts):
                k = vi.searchsorted(days[st]) - lag                     # lag 1 = the latest value dated strictly before
                if k < LOOK:
                    continue
                pct[j] = float((vv[k - LOOK:k] < vv[k]).mean())
                u[j] = k
            sig[(lab, lag)], used[(lab, lag)] = pct, u
    rolls = pd.read_csv(os.path.join(ROOT, "tools", "data", "rolls_ES.csv"))
    sw = pd.DatetimeIndex(pd.to_datetime(rolls["switch_et"]).dt.normalize())
    sw = sw[(sw >= pd.Timestamp(D0)) & (sw <= WF1)]
    return dict(days=days, O=O, C=C, starts=starts, ends=ends, sig=sig, used=used, series=series, vix=vix, prov=pv,
                vraw=vraw, R=R, switches=sw, hol=hol, vix_dropped=dropped, o_noadj=R["o_noadj"].reindex(days).to_numpy(),
                rolls_status=rolls.loc[(pd.to_datetime(rolls["switch_et"]) <= WF1), "status"].value_counts().to_dict())


def months_of(D, lab, lag, cut, lo=WF0, hi=WF1):
    first = D["days"][D["starts"]]
    m = np.asarray((first >= lo) & (first <= hi))
    p = D["sig"][(lab, lag)]
    return np.flatnonzero(m & np.isfinite(p) & (p >= cut))


def all_months(D, lo=WF0, hi=WF1):
    first = D["days"][D["starts"]]
    return np.flatnonzero(np.asarray((first >= lo) & (first <= hi)))


def roll_hits(D, m):
    """Real ES switches held through in month m: switch evening X with first session <= X < last session."""
    e, z = D["days"][D["starts"][m]], D["days"][D["ends"][m]]
    return D["switches"][(D["switches"] >= e) & (D["switches"] < z)]


def pnl(D, months, side=None, cost=COST, roll=True):
    """Daily $ per ES session for long-1-ES months (side: per-month +1/-1 for the coin-flip line); trade $ per month."""
    O, C, days = D["O"], D["C"], D["days"]
    x = np.zeros(len(O))
    tr = []
    for j, m in enumerate(months):
        s = 1.0 if side is None else float(side[j])
        if DRY and side is None:
            s = float(np.random.default_rng(1000 + int(m)).integers(0, 2) * 2 - 1)
        e, z = D["starts"][m], D["ends"][m]
        x[e] += s * (C[e] - O[e]) * M - cost * M
        for t in range(e + 1, z + 1):
            x[t] += s * (C[t] - C[t - 1]) * M
        extra = 0.0
        if roll:
            for X in roll_hits(D, m):
                t = int(days.searchsorted(X, side="right"))
                x[t] -= cost * M
                extra += cost * M
        tr.append(s * (C[z] - O[e]) * M - cost * M - extra)
    return x, np.array(tr)


def tob(D, x, bdays):
    return pd.Series(x, index=D["days"]).reindex(bdays, fill_value=0.0).to_numpy()


def month_detail(D, lab, lag, m):
    s = D["series"][lab]
    k = D["used"][(lab, lag)][m]
    vd = s.index[k]
    entry = D["days"][D["starts"][m]]
    vix_dates = D["vix"].index
    gap = int(((vix_dates > vd) & (vix_dates <= entry)).sum())
    rv = D["series"]["VRP_rv22"].get(vd, np.nan) if lab == "VRP" else D["series"]["VRP_RTH_rv22"].get(vd, np.nan)
    return vd, gap, float(D["vix"].get(vd, np.nan)), float(rv), float(D["sig"][(lab, lag)][m])


def predata(D, B, bdays, years):
    R = D["R"]
    short = R[R["nbars"] < NBAR]
    print("RV COVERAGE (edit 1): %d ES sessions in RV, %d of them with < 78 bars (the old rule would drop them); by year %s"
          % (len(R), len(short), {int(k): int(v) for k, v in pd.Series(short.index.year).value_counts().sort_index().items()}))
    print("  2020 short sessions: %s" % ", ".join("%s (%d bars, %02d:%02d-%02d:%02d)" % (
        d.date(), r.nbars, (570 + 5 * r.k0) // 60, (570 + 5 * r.k0) % 60, (570 + 5 * r.k1) // 60, (570 + 5 * r.k1) % 60)
        for d, r in short[short.index.year == 2020].iterrows()))
    for d in HALT_DAYS:
        print("  halt day %s inside RV: %s" % (d.date(), "YES, %d bars" % R.loc[d, "nbars"] if d in R.index else "NO"))
    print("  VIX DROP RULE: %d CME-holiday sessions in the ES data; %d VIX rows dated on them DROPPED: %s" % (
        len(D["hol"]), len(D["vix_dropped"]), ", ".join(str(d.date()) for d in D["vix_dropped"])))
    print("  overnight return available on %d of %d sessions; roll switches 2010-06..2025-06 by status %s" % (
        int(R["r_on2"].notna().sum()), len(R), D["rolls_status"]))
    first = D["days"][D["starts"]]
    for lag in LAGS:
        P = months_of(D, "VRP", lag, CUTS["tercile"])
        print("SCHEDULE lag %d PRIMARY (top tercile): %d WF in-months, 2020: %d" % (lag, len(P), int((first[P].year == 2020).sum())))
        for m in P:
            vd, gap, vx, rv, p = month_detail(D, "VRP", lag, m)
            nh = len(roll_hits(D, m))
            print("    %s  VRP date %s  gap %d%s  VIX %.2f  RV22 %.1f (vol %.1f)  VRP %.1f  rank %.3f%s" % (
                first[m].strftime("%Y-%m"), vd.date(), gap, "  GAP > LAG" if gap > lag else "", vx, rv, np.sqrt(rv),
                vx ** 2 - rv, p, "  roll x%d" % nh if nh else ""))
        for mo in ("2020-02", "2020-03", "2020-04"):
            m = int(np.flatnonzero(np.asarray(first.strftime("%Y-%m") == mo))[0])
            vd, gap, vx, rv, p = month_detail(D, "VRP", lag, m)
            print("    STATE %s lag %d: VRP date %s gap %d, VIX %.2f, RV22 %.1f, rank %.3f -> %s" % (
                mo, lag, vd.date(), gap, vx, rv, p, "IN" if p >= CUTS["tercile"] else "out"))
        for cl, cut in CUTS.items():
            ms = months_of(D, "VRP", lag, cut)
            jy = [int(((first[ms] >= pd.Timestamp(y, 7, 1)) & (first[ms] < pd.Timestamp(y + 1, 7, 1))).sum())
                  for y in TC.WF_YEARS]
            ea = months_of(D, "VRP", lag, cut, EARLY0, EARLY1)
            runs = int(np.sum(np.diff(np.r_[-2, ms]) > 1))
            print("  COUNTS lag %d top %s: %d WF in-months in %d runs; per July-June year %s (years with 0 = not "
                  "positive: %d); EARLY 2013-08..2016-06 %d in-months; halves 2016-21 %d / 2022-25 %d" % (
                      lag, cl, len(ms), runs, jy, sum(v == 0 for v in jy), len(ea),
                      int((first[ms] <= pd.Timestamp("2021-12-31")).sum()), int((first[ms] >= pd.Timestamp("2022-01-01")).sum())))
        for tw in ("VRP_RTH", "VIX"):
            T = months_of(D, tw, lag, CUTS["tercile"])
            print("  TWIN %s lag %d: %d in-months; overlap with the primary %d (primary only %d, twin only %d)" % (
                tw, lag, len(T), len(np.intersect1d(P, T)), len(np.setdiff1d(P, T)), len(np.setdiff1d(T, P))))
    print("  CBOE photograph lines for the 2020-02/03/04 decision dates (hand check):")
    raw = open(D["vraw"], encoding="utf-8").read().splitlines()
    for lag in LAGS:
        for mo in ("2020-02", "2020-03", "2020-04"):
            m = int(np.flatnonzero(np.asarray(first.strftime("%Y-%m") == mo))[0])
            vd = month_detail(D, "VRP", lag, m)[0]
            key = vd.strftime("%m/%d/%Y")
            print("    lag %d %s: %s" % (lag, mo, next((ln for ln in raw if ln.startswith(key)), "NOT FOUND")))
    P = months_of(D, "VRP", 1, CUTS["tercile"])
    rng = np.random.default_rng(SEED)
    x, _ = pnl(D, P, side=rng.choice([-1.0, 1.0], size=len(P)))
    xb = tob(D, x, bdays)
    print("POWER LINES (coin-flip sides on the lag-1 primary's schedule, roll charges in; no real direction is computed)")
    HH.power_lines(xb, B, years)
    mde = TC.mde_line(xb, B, years)
    held = np.zeros(len(D["days"]), bool)
    for m in P:
        held[D["starts"][m]:D["ends"][m] + 1] = True
    hb = np.flatnonzero(pd.Series(held, index=D["days"]).reindex(bdays, fill_value=False).to_numpy())
    r = TC.mde_own(lambda g: tob(D, pnl(D, P, side=g.choice([-1.0, 1.0], size=len(P)))[0], bdays), hb, B, mde)
    print("  MDE IN OWN MONEY (edit 12): the $30k-twin line's minimum detectable lead %.1f needs own ROC@30k %.1f (p25 %.1f "
          "/ p75 %.1f over %d coin-flip draws) = own $%s a year at a $30k drawdown, vs the $15,000 MDL and the prior "
          "median ROC 5 = $5,000 a year" % (mde, r["roc"][1], r["roc"][0], r["roc"][2], r["n"],
                                            format(int(round(r["roc"][1] * 1000)), ",")))


def null_circular(D, lag, bdays, RD):
    """Family max (both cells) of own ROC@30k and R-day sum over all circular shifts of lag's WF state vector."""
    W = all_months(D)
    p = D["sig"][("VRP", lag)][W]
    lab = {c: (np.isfinite(p) & (p >= cut)) for c, cut in CUTS.items()}
    roc, rs = [], []
    for k in SHIFTS:
        r1, r2 = [], []
        for c in CUTS:
            ms = W[np.roll(lab[c], k)]
            xb = tob(D, pnl(D, ms)[0], bdays)
            r1.append(TC.stat(xb, bdays)["roc"])
            r2.append(float(xb[RD].sum()))
        roc.append(np.nanmax(r1))
        rs.append(max(r2))
    return np.array(roc), np.array(rs)


def null_shuffle(D, lag, bdays, rng):
    W = all_months(D)
    p = D["sig"][("VRP", lag)][W]
    yr = D["days"][D["starts"][W]].year
    out = np.empty(NULL_DRAWS)
    for i in range(NULL_DRAWS):
        pp = p.copy()
        for y in np.unique(yr):
            ii = np.flatnonzero(yr == y)
            pp[ii] = pp[rng.permutation(ii)]
        out[i] = np.nanmax([TC.stat(tob(D, pnl(D, W[np.isfinite(pp) & (pp >= cut)])[0], bdays), bdays)["roc"]
                            for cut in CUTS.values()])
    return out


def stage_a(D, B, bdays, years):
    sha = subprocess.run(["git", "log", "-1", "--format=%h", "origin/main", "--", PREREG], capture_output=True, text=True,
                         cwd=ROOT).stdout.strip()
    print("  PREREG on main: %s last changed in %s" % (PREREG, sha or "NOT ON MAIN - STOP"))
    if DRY:
        print("  *** DRY RUN: coin-flip sides per month - every number below is NOISE, not a result ***")
    elif not sha:
        return
    import balance_r1_stageA as BAL
    L = BAL.load_L(B)[0]
    RD = np.asarray(bdays.isin(pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))))
    days = D["days"]
    edays = days[(days >= EARLY0) & (days <= EARLY1)]
    first = days[D["starts"]]
    rng = np.random.default_rng(SEED)
    verdict = {}
    p0, p1 = HH.worst_window(B)
    for lag in LAGS:
        print("=== LAG %d ===" % lag)
        rows = {}
        for lab, ms_wf, ms_e in (
                ("PRIMARY top tercile", months_of(D, "VRP", lag, CUTS["tercile"]), months_of(D, "VRP", lag, CUTS["tercile"], EARLY0, EARLY1)),
                ("neighbour top quartile", months_of(D, "VRP", lag, CUTS["quartile"]), months_of(D, "VRP", lag, CUTS["quartile"], EARLY0, EARLY1)),
                ("twin VIX^2 alone (A6)", months_of(D, "VIX", lag, CUTS["tercile"]), months_of(D, "VIX", lag, CUTS["tercile"], EARLY0, EARLY1)),
                ("twin RTH-only RV", months_of(D, "VRP_RTH", lag, CUTS["tercile"]), months_of(D, "VRP_RTH", lag, CUTS["tercile"], EARLY0, EARLY1)),
                ("twin ALWAYS LONG", all_months(D), all_months(D, EARLY0, EARLY1))):
            x, tr = pnl(D, ms_wf)
            xb = tob(D, x, bdays)
            xe = pd.Series(pnl(D, ms_e)[0], index=days).reindex(edays, fill_value=0.0).to_numpy()
            st = TC.stat(xb, bdays)
            pf = tr[tr > 0].sum() / -tr[tr < 0].sum() if (tr < 0).any() else np.inf
            ys = TC.jy_sums(xb, bdays)
            k20 = np.asarray(bdays.year != 2020)
            s20 = TC.stat(xb[k20], bdays[k20])
            h1 = float(xb[bdays <= pd.Timestamp("2021-12-31")].sum())
            h2 = float(xb[bdays >= pd.Timestamp("2022-01-01")].sum())
            ww = np.sort(xb[(bdays > p0) & (bdays <= p1)])
            rows[lab] = dict(ms=ms_wf, x=x, xb=xb, xe=xe, tr=tr, st=st, pf=pf, ys=ys, s20=s20, h1=h1, h2=h2,
                             rsum=float(xb[RD].sum()), ww=ww)
            print("  %-24s n %3d  %s  PF %.2f  years + %d/9  R-day sum $%s  no-2020 ROC %.2f  halves $%s / $%s  EARLY net "
                  "$%s" % (lab, len(tr), TC.fmt(st), pf, sum(v > 0 for v in ys), format(int(rows[lab]["rsum"]), ","),
                           s20["roc"], format(int(h1), ","), format(int(h2), ","), format(int(xe.sum()), ",")))
        pr = rows["PRIMARY top tercile"]
        nroc, nrs = null_circular(D, lag, bdays, RD)
        T = pr["st"]["roc"]
        ge = int((nroc >= T).sum())
        ge_r = int((nrs >= pr["rsum"]).sum())
        print("  NULL circular shift (k 12..96, %d draws, family max of both cells): ROC p95 %.2f; real %.2f = rank %d of %d "
              "(%d draws >= real); R-day sum p95 $%s, real rank %d of %d" % (
                  len(nroc), np.percentile(nroc, 95), T, ge + 1, len(nroc) + 1, ge, format(int(np.percentile(nrs, 95)), ","),
                  ge_r + 1, len(nrs) + 1))
        ns = null_shuffle(D, lag, bdays, rng)
        print("  REPORTED within-year shuffle null (x%d): family-max ROC p95 %.2f (circular p95 %.2f; gap %+.2f)" % (
            NULL_DRAWS, np.percentile(ns, 95), np.percentile(nroc, 95), np.percentile(nroc, 95) - np.percentile(ns, 95)))
        a2 = ge <= int(0.05 * len(nroc))
        earner = T >= 5 and ge_r <= int(0.05 * len(nrs))
        route = T >= 15 or earner
        s20 = pr["s20"]
        route20 = s20["roc"] >= 15 or (s20["roc"] >= 5 and earner)
        tr = pr["tr"]
        x2 = tob(D, pnl(D, pr["ms"], cost=2 * COST)[0], bdays)
        a4 = (tr.sum() - tr.max() > 0) and (x2.sum() > 0)
        AL = rows["twin ALWAYS LONG"]
        ok_trio, lines = TC.lead_trio(np.r_[pr["xe"], pr["xb"]], np.r_[AL["xe"], AL["xb"]], edays.append(bdays),
                                      np.r_[np.zeros(len(edays), bool), np.ones(len(bdays), bool)],
                                      np.r_[np.ones(len(edays), bool), np.zeros(len(bdays), bool)], "PRIMARY (timed) vs ALWAYS LONG (raw)")
        print("\n".join(lines))
        vx = rows["twin VIX^2 alone (A6)"]
        a6 = T > vx["st"]["roc"]
        print("  A6 regime-matched: primary %.2f vs VIX^2-alone %.2f -> %s; in-month overlap %d of %d / %d" % (
            T, vx["st"]["roc"], "PASS" if a6 else "FAIL - file as 'VIX-level timing, not VRP'",
            len(np.intersect1d(pr["ms"], vx["ms"])), len(pr["ms"]), len(vx["ms"])))
        bars = [("A1 route (>= 15, or >= 5 + R-day sum > circular p95)", route),
                ("A1 count (>= 100 trades and 50 a year)", len(tr) >= 100 and len(tr) / years >= 50),
                ("PF > 1", pr["pf"] > 1), (">= 6 of 9 July-June years", sum(v > 0 for v in pr["ys"]) >= 6),
                ("A1b route without 2020", route20), ("A2 ROC > circular p95 (strict rank)", a2),
                ("A3 neighbour net > 0", rows["neighbour top quartile"]["st"]["net"] > 0),
                ("A4 net > 0 without best trade and at 2x cost", a4),
                ("A5 RISK r1 trio vs always-long (WF / EX / EARLY lead > 0, paired d >= 6/9)", ok_trio),
                ("A5 standalone net > 0 in both WF halves", pr["h1"] > 0 and pr["h2"] > 0),
                ("A6 beats VIX^2 alone", a6)]
        for b, v in bars:
            print("    %-78s %s" % (b, "pass" if v else "FAIL"))
        others = all(v for b, v in bars if not b.startswith("A1 count"))
        verdict[lag] = "PASS" if all(v for _, v in bars) else ("RESEARCH ROW (count only)" if others else "FAIL")
        print("  LAG %d VERDICT: %s" % (lag, verdict[lag]))
        if lag == 1:
            print("  dollars inside #463's worst WF drawdown (%s .. %s): $%s" % (p0.date(), p1.date(), format(int(pr["ww"].sum()), ",")))
            print("\n".join(TC.book_adds(pr["xb"], B, L, years, "VRPES", no2020=True)))
            print("  every in-month: " + "; ".join("%s $%s" % (first[m].strftime("%Y-%m"), format(int(v), ","))
                                                    for m, v in zip(pr["ms"], tr)))
            tr0 = pnl(D, pr["ms"], cost=0.0)[1]
            nrt = np.array([1 + len(roll_hits(D, m)) for m in pr["ms"]])
            px = np.array([D["o_noadj"][D["starts"][m]] for m in pr["ms"]])
            for bps in (0, 5, 10, 20):
                print("  cost curve %2d bps a round trip (no-adjust entry price): net $%s" % (
                    bps, format(int(tr0.sum() - (bps / 1e4 * px * M * nrt).sum()), ",")))
            path = np.zeros(25)
            for m in pr["ms"]:
                e, z = D["starts"][m], D["ends"][m]
                path[:z - e + 1] += pr["x"][e:z + 1]
            print("  event path, mean $ by session of the month: " + " ".join("%.0f" % v for v in path[:23] / max(len(tr), 1)))
    final = "PASS" if all(v == "PASS" for v in verdict.values()) else (
        "RESEARCH ROW (count only)" if all(v != "FAIL" for v in verdict.values()) else "FAIL")
    print("VERDICT (worse of lag 1 and lag 2): %s   [lag 1 %s; lag 2 %s]" % (final, verdict[1], verdict[2]))


def main(argv):
    D = build()
    days = D["days"]
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    pv = D["prov"]
    v = D["series"]["VRP"]
    print("VRPES r1 - ES 30m RTH ADJ %d sessions (%s .. %s); VIX photograph %s sha256 %s.. verified; VRP days %d (%s .. %s)"
          % (len(days), days[0].date(), days[-1].date(), pv["fetched_at"], pv["sha256"][:8], len(v), v.index[0].date(),
             v.index[-1].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    print("  VIX rows on CME-holiday sessions dropped (rule in ADDENDUM 1 edit 13): %d" % len(D["vix_dropped"]))
    if "--predata" in argv:
        predata(D, B, bdays, years)
        return
    stage_a(D, B, bdays, years)


if __name__ == "__main__":
    main(sys.argv[1:])
