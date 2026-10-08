# -*- coding: utf-8 -*-
"""VRPES r1 STAGE A - the variance risk premium as monthly ES timing (docs/PREREG_vrpes_r1_2026-10-07.md; TTM scope rank 5,
opened by MANAGER 2026-10-07 evening).

A high variance risk premium (implied variance minus realized variance) forecasts equity returns over the next months
(Bollerslev, Tauchen & Zhou 2009 RFS; Bekaert & Hoerova 2014 JoE). Rule: at each month end, VRP = VIX^2 minus the trailing
22-session ES realized variance (RTH 5m log returns, annualised, %^2). If the latest VRP dated STRICTLY BEFORE the month's
first session sits in the top tercile of the 756 VRP days before it, LONG 1 ES at that first session's 09:30 open and out
at the month's last session close; flat otherwise. Cost 0.363 pt, $50 a point.

Data: VIX = the 2026-10-05 CBOE photograph (re-hashed against public_series_provenance.json; rows after 2025-06-29 dropped
on read). Realized variance from the ES 5m RTH NO-ADJUST master (intra-session returns only, so the no-adjust prices are
exact); the month-long position is marked on the ES 30m RTH roll-corrected (ADJ) master, whose additive shift leaves every
point difference exact. Arrays cut at 2025-06-29.

LOOK-AHEAD CHARGE (MANAGER 10-07): VIX closes 16:15 ET, after ES's 16:00 RTH close, so the signal acts no earlier than the
NEXT session's open (lag 1 = the primary). The bars are judged on the WORSE of lag 1 and lag 2 (VRP dated two sessions
before the entry), so nothing earned from the last decision day's information is credited.

  python tools/vrpes_r1_stageA.py --counts   -> in-months per cell per year, held sessions, R days (no returns)
  python tools/vrpes_r1_stageA.py --power    -> the power line from a COIN-FLIP side on the primary's schedule
"""
import hashlib
import json
import os
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

COST, M = 0.363, 50.0
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
RVN, LOOK, NBAR = 22, 756, 78
CELLS = [2.0 / 3.0, 3.0 / 4.0]                                          # top tercile = PRIMARY, top quartile = neighbour
PRIMARY = CELLS[0]
LAGS = (1, 2)
SEED = 20261007
PUB = os.path.join(HOME, "_research_cache", "public_series")
PREREG = "docs/PREREG_vrpes_r1_2026-10-07.md"


def photo(name, col):
    raw = os.path.join(PUB, "cboe", name)
    prov = json.load(open(os.path.join(PUB, "public_series_provenance.json"), encoding="utf-8"))["cboe\\" + name]
    assert hashlib.sha256(open(raw, "rb").read()).hexdigest() == prov["sha256"], name + " is not the photograph - abort"
    v = pd.read_csv(raw)
    v.columns = [c.strip().upper() for c in v.columns]
    v["DATE"] = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    return v[v["DATE"] <= WF1].set_index("DATE")[col].astype(float), prov


def sessions(sym, tf, src):
    A = load_master_arrays(find_master(sym, tf, "rth", src), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"]).tz_localize(None)
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    return A, ts


def realized():
    """Per full ES session (78 5m RTH bars): the sum of squared 5m log returns, the first from the 09:30 open."""
    A, ts = sessions("ES", "5m", "db_noadj_rth")
    day = pd.DatetimeIndex(ts.normalize())
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    days = pd.DatetimeIndex(sorted(set(day)))
    di = days.get_indexer(day)
    ok = (k >= 0) & (k < NBAR)
    C = np.full((len(days), NBAR), np.nan)
    C[di[ok], k[ok]] = np.asarray(A["close"], float)[ok]
    O0 = np.full(len(days), np.nan)
    first = ok & (k == 0)
    O0[di[first]] = np.asarray(A["open"], float)[first]
    full = np.isfinite(C).all(axis=1) & np.isfinite(O0)
    r = np.diff(np.log(np.c_[O0, C]), axis=1)
    rv = pd.Series(np.where(full, (r ** 2).sum(axis=1), np.nan), index=days).dropna()
    return rv


def build():
    vix, pv = photo("VIX_History.csv", "CLOSE")
    rv = realized()
    rv22 = (rv.rolling(RVN).sum() * (252.0 / RVN) * 1e4).dropna()      # annualised, in VIX points squared
    vrp = (vix.reindex(rv22.index) ** 2 - rv22).dropna()               # VIX and RV dated the same ES session
    A, ts = sessions("ES", "30m", "db_adj_rth")
    day = pd.DatetimeIndex(ts.normalize())
    df = pd.DataFrame({"d": day, "o": np.asarray(A["open"], float), "c": np.asarray(A["close"], float)})
    g = df.groupby("d", sort=True)
    days = pd.DatetimeIndex(g.o.first().index)
    O, C = g.o.first().to_numpy(), g.c.last().to_numpy()
    ym = days.year * 12 + days.month - 1
    starts = np.r_[0, np.flatnonzero(np.diff(ym)) + 1]
    ends = np.r_[starts[1:] - 1, len(days) - 1]
    vv, vi = vrp.to_numpy(), vrp.index
    sig = {}
    for lag in LAGS:
        pct = np.full(len(starts), np.nan)
        for j, s in enumerate(starts):
            k = vi.searchsorted(days[s]) - lag                         # lag 1 = the latest VRP dated strictly before
            if k < LOOK:
                continue
            pct[j] = float((vv[k - LOOK:k] < vv[k]).mean())
        sig[lag] = pct
    return dict(days=days, O=O, C=C, starts=starts, ends=ends, sig=sig, vrp=vrp, prov=pv)


def pnl(D, months, side=None, cost=COST):
    """Daily $ per session for long-1-ES months (side: per-month +1/-1 override for the coin-flip line)."""
    O, C = D["O"], D["C"]
    x = np.zeros(len(O))
    tr = []
    for j, m in enumerate(months):
        s = 1.0 if side is None else float(side[j])
        e, z = D["starts"][m], D["ends"][m]
        x[e] += s * (C[e] - O[e]) * M - cost * M
        for t in range(e + 1, z + 1):
            x[t] += s * (C[t] - C[t - 1]) * M
        tr.append(s * (C[z] - O[e]) * M - cost * M)
    return x, np.array(tr)


def in_months(D, lag, cut):
    first = D["days"][D["starts"]]
    wf = np.asarray((first >= WF0) & (first <= WF1))
    p = D["sig"][lag]
    return np.flatnonzero(wf & np.isfinite(p) & (p >= cut))


def main(argv):
    D = build()
    days = D["days"]
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    pv = D["prov"]
    vrp = D["vrp"]
    print("VRPES r1 - ES 30m RTH ADJ %d sessions (%s .. %s); VIX photograph %s sha256 %s.. verified; VRP days %d (%s .. %s)"
          % (len(days), days[0].date(), days[-1].date(), pv["fetched_at"], pv["sha256"][:8], len(vrp),
             vrp.index[0].date(), vrp.index[-1].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    first = days[D["starts"]]
    nwf = int(((first >= WF0) & (first <= WF1)).sum())
    print("  WF months %d; VRP < 0 on %d of %d WF VRP days" % (
        nwf, int((vrp[vrp.index >= WF0] < 0).sum()), int((vrp.index >= WF0).sum())))
    RD = np.asarray(bdays.isin(pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))))
    for lag in LAGS:
        for cut in CELLS:
            ms = in_months(D, lag, cut)
            held = np.zeros(len(days), bool)
            for m in ms:
                held[D["starts"][m]:D["ends"][m] + 1] = True
            hb = pd.Series(held, index=days).reindex(bdays, fill_value=False).to_numpy()
            per = pd.Series(first[ms].year).value_counts().sort_index()
            runs = int(np.sum(np.diff(np.r_[-2, ms]) > 1))
            print("  COUNTS lag %d top %s: %d in-months (%.1f a year) in %d runs; per calendar year %s; held sessions %d, "
                  "R days %d" % (lag, "tercile" if cut == CELLS[0] else "quartile", len(ms), len(ms) / years, runs,
                                 {int(k): int(v) for k, v in per.items()}, int(held.sum()), int((hb & RD).sum())))
    p1 = in_months(D, 1, PRIMARY)
    p2 = in_months(D, 2, PRIMARY)
    print("  lag 1 vs lag 2 primary: %d months in both, %d only lag 1, %d only lag 2" % (
        len(np.intersect1d(p1, p2)), len(np.setdiff1d(p1, p2)), len(np.setdiff1d(p2, p1))))
    for lab, a, b in (("2016-21", WF0, pd.Timestamp("2021-12-31")), ("2022-25", pd.Timestamp("2022-01-01"), WF1)):
        f = first[p1]
        print("    %s: primary in-months %d" % (lab, int(((f >= a) & (f <= b)).sum())))
    if "--power" in argv:
        rng = np.random.default_rng(SEED)
        x, _ = pnl(D, p1, side=rng.choice([-1.0, 1.0], size=len(p1)))
        print("POWER LINES (coin-flip sides on the primary's schedule; no real direction is computed)")
        HH.power_lines(pd.Series(x, index=days).reindex(bdays, fill_value=0.0).to_numpy(), B, years)


if __name__ == "__main__":
    main(sys.argv[1:])
