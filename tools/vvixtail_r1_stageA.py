# -*- coding: utf-8 -*-
"""VVIXTAIL r1 STAGE A - vol-of-vol as a short-ES trigger (docs/PREREG_vvixtail_r1_2026-10-06.md; MANAGER #72).

The volatility of VIX carries tail information beyond VIX itself (Park 2015 JFM; Huang, Schlag, Shaliastovich & Thimsen
2019 Management Science: vol-of-vol risk is priced and high VVIX forecasts weak returns). Rule: when the prior-day close of
VVIX / VIX sits in its top 2% of the trailing year (the 252 VIX days before it), SHORT 1 ES at the next RTH open and hold
5 sessions (out at the 5th session's close); no new entry while short. Cost 0.363 pt, $50 a point. Positions span
sessions, so the ES 30m RTH roll-corrected (ADJ) master is used: its additive shift leaves every point difference exact.
VIX and VVIX = the 2026-10-05 CBOE photographs, re-hashed against public_series_provenance.json, rows after 2025-06-29
dropped on read; only values dated strictly before the entry session are read.

Cells: top 2% = PRIMARY, top 5% = neighbour. Earner route (MANAGER #72): own ROC@$30k >= 5 AND the R-day sum above the
family null's 95th percentile; null = the same count of entries per calendar year on shuffled sessions of that year
(non-overlapping), x1,000. Walk-forward 2016-07-01 .. 2025-06-29; EARLY 2010-06-07 .. 2016-06-30 reported as a bar.

  python tools/vvixtail_r1_stageA.py --counts   -> entries per cell per year (no returns)
  python tools/vvixtail_r1_stageA.py --power    -> the power line from a COIN-FLIP side on the primary's schedule
  python tools/vvixtail_r1_stageA.py            -> Stage A
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

COST, M, HOLD = 0.363, 50.0, 5
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
EARLY1 = pd.Timestamp("2016-06-30")
CELLS = [0.98, 0.95]
PRIMARY = CELLS[0]
NULL_DRAWS, SEED = 1000, 20261006
PUB = os.path.join(HOME, "_research_cache", "public_series")
PREREG = "docs/PREREG_vvixtail_r1_2026-10-06.md"
HALVES = [(WF0, pd.Timestamp("2021-12-31")), (pd.Timestamp("2022-01-01"), WF1)]


def photo(name, col):
    raw = os.path.join(PUB, "cboe", name)
    prov = json.load(open(os.path.join(PUB, "public_series_provenance.json"), encoding="utf-8"))["cboe\\" + name]
    assert hashlib.sha256(open(raw, "rb").read()).hexdigest() == prov["sha256"], name + " is not the photograph - abort"
    v = pd.read_csv(raw)
    v.columns = [c.strip().upper() for c in v.columns]
    v["DATE"] = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    return v[v["DATE"] <= WF1].set_index("DATE")[col].astype(float), prov


def build():
    vix, pv = photo("VIX_History.csv", "CLOSE")
    vvix, pw = photo("VVIX_History.csv", "VVIX")
    r = (vvix / vix).dropna()
    r = r[(r.index >= pd.Timestamp("2007-01-01"))]
    # percentile threshold of the ratio on day t against the 252 ratio days strictly before t
    A = load_master_arrays(find_master("ES", "30m", "rth", "db_adj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    day = pd.DatetimeIndex(pd.Index(ts.date))
    df = pd.DataFrame({"d": day, "o": np.asarray(A["open"], float), "c": np.asarray(A["close"], float)})
    g = df.groupby("d", sort=True)
    days = pd.DatetimeIndex(g.o.first().index)
    O, C = g.o.first().to_numpy(), g.c.last().to_numpy()
    rv = r.to_numpy()
    ridx = r.index
    sig = {}
    for q in CELLS:
        on = np.zeros(len(days), bool)
        for i, d in enumerate(days):
            k = ridx.searchsorted(d) - 1                                # the latest ratio day strictly before session d
            if k < 252:
                continue
            on[i] = rv[k] >= np.quantile(rv[k - 252:k], q)
        sig[q] = on
    return dict(days=days, O=O, C=C, sig=sig, prov=(pv, pw), ratio=r)


def schedule(on):
    """Entry session indices: a signal session while flat; the position covers entry .. entry + HOLD - 1."""
    ent, nxt = [], 0
    for i in np.flatnonzero(on):
        if i >= nxt and i + HOLD - 1 < len(on):
            ent.append(int(i))
            nxt = i + HOLD
    return np.array(ent, int)


def pnl(D, ent, side=None, cost=COST):
    """Daily $ per session for short-1-ES trades at `ent` (side: per-trade +1/-1 override for the coin-flip line)."""
    O, C = D["O"], D["C"]
    x = np.zeros(len(O))
    tr = []
    for j, e in enumerate(ent):
        s = -1.0 if side is None else float(side[j])
        x[e] += s * (C[e] - O[e]) * M - cost * M
        for t in range(e + 1, e + HOLD):
            x[t] += s * (C[t] - C[t - 1]) * M
        tr.append(s * (C[e + HOLD - 1] - O[e]) * M - cost * M)
    return x, np.array(tr)


def in_wf(D, ent):
    d = D["days"][ent] if len(ent) else pd.DatetimeIndex([])
    return ent[(d >= WF0) & (d <= WF1)] if len(ent) else ent


def main(argv):
    D = build()
    days = D["days"]
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    pv, pw = D["prov"]
    print("VVIXTAIL r1 - ES 30m RTH ADJ, %d sessions (%s .. %s); VIX / VVIX photographs %s / %s (sha256 %s.. / %s.. "
          "verified); ratio days from %s" % (len(days), days[0].date(), days[-1].date(), pv["fetched_at"], pw["fetched_at"],
                                            pv["sha256"][:8], pw["sha256"][:8], D["ratio"].index[0].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    ENT = {q: in_wf(D, schedule(D["sig"][q])) for q in CELLS}
    RD = np.asarray(bdays.isin(pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))))
    yb = days.year
    if "--counts" in argv or "--power" in argv:
        for q in CELLS:
            e = ENT[q]
            per = pd.Series(yb[e]).value_counts().sort_index()
            held = np.zeros(len(days), bool)
            for i in e:
                held[i:i + HOLD] = True
            hb = pd.Series(held, index=days).reindex(bdays, fill_value=False).to_numpy()
            print("  COUNTS top %.0f%%: %d WF entries (%.1f a year); per calendar year %s; held sessions %d, of them R days %d"
                  % (100 * (1 - q), len(e), len(e) / years, {int(k): int(v) for k, v in per.items()}, int(held.sum()),
                     int((hb & RD).sum())))
    if "--counts" in argv:
        return
    rng = np.random.default_rng(SEED)
    if "--power" in argv:
        e = ENT[PRIMARY]
        x, _ = pnl(D, e, side=rng.choice([-1.0, 1.0], size=len(e)))
        print("POWER LINES (coin-flip sides on the primary's schedule; no real direction is computed)")
        HH.power_lines(pd.Series(x, index=days).reindex(bdays, fill_value=0.0).to_numpy(), B, years)
        return

    sha = subprocess.run(["git", "log", "-1", "--format=%h", "origin/main", "--", PREREG], capture_output=True, text=True,
                         cwd=ROOT).stdout.strip()
    print("  PREREG on main: %s last changed in %s" % (PREREG, sha or "NOT ON MAIN - STOP"))
    if not sha:
        return
    tob = lambda x: pd.Series(x, index=days).reindex(bdays, fill_value=0.0).to_numpy()        # noqa: E731
    rows = {}
    for q in CELLS:
        x, tr = pnl(D, ENT[q])
        xb = tob(x)
        st = HH.own(xb, bdays)
        rsum = float(xb[RD].sum())
        pf = tr[tr > 0].sum() / -tr[tr < 0].sum() if (tr < 0).any() else np.inf
        yrs = [xb[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
        rows[q] = dict(x=x, xb=xb, st=st, tr=tr, pf=pf, yrs=yrs, rsum=rsum)
        if q == PRIMARY:
            rr = np.sort(xb[RD])
            print("  R-DAY SUM (printed first): primary $%s over R's %d days, $%s without its 3 best" % (
                format(int(rsum), ","), int(RD.sum()), format(int(rr[:-3].sum()), ",")))
        print("  top %.0f%%%s  n %3d (%4.1f/yr)  net $%9s  PF %.2f  DD $%7s  own ROC@30k %6.2f  Sortino %5.2f  years + %d/9  "
              "R-day sum $%s" % (100 * (1 - q), "  PRIMARY" if q == PRIMARY else "          ", len(tr), len(tr) / years,
                                 format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
                                 sum(v > 0 for v in yrs), format(int(rsum), ",")))
    # family null: same count of entries per calendar year, shuffled to random sessions of that year (non-overlapping)
    wfi = np.flatnonzero((days >= WF0) & (days <= WF1))
    by_year = {y: wfi[yb[wfi] == y] for y in np.unique(yb[wfi])}
    nr, nroc = np.empty(NULL_DRAWS), np.empty(NULL_DRAWS)
    for i in range(NULL_DRAWS):
        rs, rc = [], []
        for q in CELLS:
            cnt = pd.Series(yb[ENT[q]]).value_counts()
            ent = []
            for y, n in cnt.items():
                pool = by_year[y][by_year[y] + HOLD - 1 < len(days)]
                for _ in range(200):
                    pick = np.sort(rng.choice(pool, size=n, replace=False))
                    if n < 2 or np.all(np.diff(pick) >= HOLD):
                        break
                ent.extend(pick.tolist())
            xb = tob(pnl(D, np.array(sorted(ent), int))[0])
            rs.append(float(xb[RD].sum()))
            rc.append(HH.own(xb, bdays)["roc"])
        nr[i], nroc[i] = max(rs), np.nanmax(rc)
    q95r, q95c = float(np.percentile(nr, 95)), float(np.percentile(nroc, 95))
    print("  family null (%d same-year date shuffles): family-max R-day sum p95 $%s; family-max own ROC@30k p95 %.2f" % (
        NULL_DRAWS, format(int(q95r), ","), q95c))
    pr = rows[PRIMARY]
    st = pr["st"]
    route15 = st["roc"] >= 15
    earner = st["roc"] >= 5 and pr["rsum"] > q95r
    k = np.asarray(bdays.year != 2020)
    s20 = HH.own(pr["xb"][k], bdays[k])
    no2020 = s20["net"] > 0 and s20["roc"] >= (15 if route15 else 5)
    count_ok = len(pr["tr"]) >= 100 and len(pr["tr"]) / years >= 50
    ex_best = float(pr["tr"].sum() - pr["tr"].max())
    stress = float(pnl(D, ENT[PRIMARY], cost=2 * COST)[1].sum())
    ee = schedule(D["sig"][PRIMARY])
    ee = ee[(days[ee] >= pd.Timestamp(D0)) & (days[ee] <= EARLY1)]
    early = float(pnl(D, ee)[1].sum())
    print("  checks: without 2020 own ROC@30k %.2f net $%s; net without the best trade $%s; at 2x cost $%s; EARLY "
          "2010-06..2016-06 n %d net $%s" % (s20["roc"], format(int(s20["net"]), ","), format(int(ex_best), ","),
                                             format(int(stress), ","), len(ee), format(int(early), ",")))
    bars = [("A1 route (ROC >= 15, or ROC >= 5 + R-day sum > null p95 $%s)" % format(int(q95r), ","), route15 or earner),
            ("A1 count (>= 100 and >= 50 a year)", count_ok), ("PF > 1", pr["pf"] > 1),
            (">= 6 of 9 years", sum(v > 0 for v in pr["yrs"]) >= 6), ("A1b without 2020", no2020),
            ("A3 top 5% net > 0", rows[CELLS[1]]["st"]["net"] > 0), ("net ex-best > 0", ex_best > 0),
            ("2x cost net > 0", stress > 0), ("EARLY net > 0", early > 0)]
    ok = all(v for _, v in bars)
    count_only = (not count_ok) and all(v for k_, v in bars if not k_.startswith("A1 count"))
    print("  VERDICT: %s -> %s" % ("; ".join("%s %s" % (k_, "yes" if v else "NO") for k_, v in bars),
                                   "PASS -> plugin + window-pinned Auto-Validate on a ranged file" if ok else
                                   "RESEARCH ROW (fails on count alone)" if count_only else "FAIL (dead, no variants)"))
    HH.book_report(pr["xb"], B, years, "VVIXTAIL")

    print("DIAGNOSTICS (no verdict)")
    e = ENT[PRIMARY]
    print("  primary trades (entry date, $): %s" % ", ".join("%s %s" % (days[i].date(), format(int(v), ","))
                                                          for i, v in zip(e, pr["tr"])))
    for a, b in HALVES:
        m = (bdays >= a) & (bdays <= b)
        print("  half %s .. %s: net $%s" % (a.date(), b.date(), format(int(pr["xb"][m].sum()), ",")))
    print("  per WF year: %s" % ", ".join("%d $%s" % (2016 + i, format(int(v), ",")) for i, v in enumerate(pr["yrs"])))
    path = np.zeros(HOLD)
    for i in e:
        path += np.r_[-(D["C"][i] - D["O"][i]), -(D["C"][i + 1:i + HOLD] - D["C"][i:i + HOLD - 1])] * M
    print("  event path, mean $ by session of the hold 1..5: %s" % " ".join("%+.0f" % v for v in path / max(len(e), 1)))
    print("  cost curve, net at 0 / 5 / 10 / 20 bps of the entry price: %s" % " / ".join(
        "$" + format(int(sum(-(D["C"][i + HOLD - 1] - D["O"][i]) * M - bp / 1e4 * D["O"][i] * M for i in e)), ",")
        for bp in (0, 5, 10, 20)))
    p0, p1 = HH.worst_window(B)
    w = (bdays > p0) & (bdays <= p1)
    print("  inside #463's worst WF drawdown (%s .. %s): $%s" % (p0.date(), p1.date(), format(int(pr["xb"][w].sum()), ",")))


if __name__ == "__main__":
    main(sys.argv[1:])
