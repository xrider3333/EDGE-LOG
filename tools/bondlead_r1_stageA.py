# -*- coding: utf-8 -*-
"""BONDLEAD r1 STAGE A - does the bond market's morning tell NQ's afternoon? (docs/PREREG_bondlead_r1_2026-10-05.md)

Gradual information diffusion across asset classes (Hong, Torous & Valkanov 2007; Pitkajarvi, Suominen & Vaittinen 2020
cross-asset momentum: bond returns lead equity returns): macro news shows first and fully in the Treasury market, and
equity investors with limited attention fold it in over hours. Rule, each day:
  morning   r = (last close at or before the window end) / (first open at or after 09:30) - 1, for NQ and the fund(s)
  beta      OLS slope(s) of NQ's morning return on the fund morning return(s) over the previous 60 sessions (sign free:
            the stock-bond correlation flips, 2022)
  signal    z = fitted NQ move (beta . fund morning) / SD of NQ's morning return over the previous 60 sessions
  trade     |z| >= z0: 1 NQ in the sign of the fitted move, from the window-end bar's open to the 15:55 bar's close
Cells: IEF 09:30-12:00 z0 0.1 PRIMARY, IEF 12:00 z0 0.2, IEF 09:30-11:00 z0 0.1, IEF+GLD 12:00 z0 0.1
(z0 is on NQ's own scale: trade when the bond-implied move is at least a tenth of NQ's typical morning; set from
trade COUNTS only - 0.5 gave 22 trades a year, under the map's 50 - before any direction was computed).
Twin (A5): NQ's OWN morning move in the same seat (sign of r_NQ, |r_NQ / sd| >= z0) - the cross-asset part must add to
plain intraday continuation. Family null: the fund morning returns PERMUTED across days (200 draws; beta re-estimated
on the permuted series) - keeps NQ's afternoons, removes only the same-day cross-asset link.
Walk-forward stretch only (2016-07-01 .. 2025-06-29); fund bars exist from 2016-01-04, so the 60-session warm-up ends
before the stretch; every master is loaded with date_to 2025-06-29.

  python tools/bondlead_r1_stageA.py --power   -> the power line from a COIN-FLIP leg on the primary's schedule
  python tools/bondlead_r1_stageA.py           -> Stage A
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import halfhour_r1_stageA as HH                                       # noqa: E402  (book, stats, scaling)
import power_line as PL                                               # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402

COST, M = HH.COST, HH.M
LOOK = 60
PRIMARY = (("IEF",), 30, 0.1)                                         # (funds, window-end bar index, z0); bar 30 = 12:00
CELLS = [PRIMARY, (("IEF",), 30, 0.2), (("IEF",), 18, 0.1), (("IEF", "GLD"), 30, 0.1)]
NULL_DRAWS, SEED = 200, 20261005
F0 = "2016-01-04"


def grid(inst, source):
    A = load_master_arrays(find_master(inst, "5m", "rth", source), date_from=F0, date_to=HH.WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= HH.WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    day = pd.Index(ts.date)
    days = pd.Index(sorted(set(day)))
    di = days.get_indexer(day)
    ok = (k >= 0) & (k < 78)
    O = np.full((len(days), 78), np.nan)
    C = np.full((len(days), 78), np.nan)
    O[di[ok], k[ok]] = np.asarray(A["open"], float)[ok]
    C[di[ok], k[ok]] = np.asarray(A["close"], float)[ok]
    return pd.DatetimeIndex(days), O, C


def morning(O, C, kend):
    """% return from the first open at/after 09:30 to the last close at/before the bar ending at the window end."""
    first = np.where(np.isnan(O[:, :3]).all(axis=1), np.nan, O[:, :3][np.arange(len(O)), np.argmax(~np.isnan(O[:, :3]), axis=1)])
    seg = C[:, kend - 3:kend][:, ::-1]                                # last three bars before the window end, newest first
    last = np.where(np.isnan(seg).all(axis=1), np.nan, seg[np.arange(len(seg)), np.argmax(~np.isnan(seg), axis=1)])
    return last / first - 1.0


def load():
    days, O, C = grid("NQ", "db_noadj_rth")
    keep = ~np.isnan(C[:, 77])
    days, O, C = days[keep], O[keep], C[keep]
    funds = {}
    for f in ("IEF", "GLD"):
        fd, fo, fc = grid(f, "alpaca_split_rth")
        idx = fd.get_indexer(days)
        FO = np.full((len(days), 78), np.nan)
        FC = np.full((len(days), 78), np.nan)
        have = idx >= 0
        FO[have], FC[have] = fo[idx[have]], fc[idx[have]]
        funds[f] = (FO, FC)
    return days, O, C, funds


def fitted(y, X):
    """z[d] = (b_d . X[d]) / sd(y over the previous LOOK valid days), b_d = OLS on the previous LOOK valid days."""
    D = len(y)
    z = np.full(D, np.nan)
    v = np.flatnonzero(~np.isnan(y) & ~np.isnan(X).any(axis=1))
    for j in range(LOOK, len(v)):
        w = v[j - LOOK:j]
        d = v[j]
        Xw = np.c_[np.ones(LOOK), X[w]]
        b = np.linalg.lstsq(Xw, y[w], rcond=None)[0]
        sd = y[w].std(ddof=1)
        if sd > 0:
            z[d] = float(X[d] @ b[1:]) / sd
    return z


def own_z(y):
    D = len(y)
    z = np.full(D, np.nan)
    v = np.flatnonzero(~np.isnan(y))
    for j in range(LOOK, len(v)):
        sd = y[v[j - LOOK:j]].std(ddof=1)
        if sd > 0:
            z[v[j]] = y[v[j]] / sd
    return z


def leg(O, C, z, kend, z0, wf, coin=None):
    on = wf & ~np.isnan(z) & (np.abs(z) >= z0) & ~np.isnan(O[:, kend]) & ~np.isnan(C[:, 77])
    side = np.sign(z) if coin is None else coin
    P = np.where(on, (side * (C[:, 77] - O[:, kend]) - COST) * M, 0.0)
    return np.nan_to_num(P), on


def cell_z(cell, O, C, funds, perm=None):
    names, kend, _ = cell
    y = morning(O, C, kend)
    X = np.column_stack([morning(*funds[f], kend) for f in names])
    if perm is not None:
        X = X[perm]
    return fitted(y, X)


def main(argv):
    days, O, C, funds = load()
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    wf = np.asarray((days >= HH.WF0) & (days <= HH.WF1))
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("BONDLEAD r1 - NQ 5m RTH no-adjust + IEF/GLD 5m RTH (Alpaca), %d full NQ sessions from %s, %d in the WF "
          "stretch; IEF missing on %d of them" % (len(days), days[0].date(), int(wf.sum()),
                                                  int(np.isnan(funds["IEF"][1][wf, 29]).sum())))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))

    if "--power" in argv:
        z = cell_z(PRIMARY, O, C, funds)
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(days))
        P, on = leg(O, C, z, PRIMARY[1], PRIMARY[2], wf, coin=coin)
        x, dd = HH.scaled(pd.Series(P, index=days).reindex(bdays, fill_value=0.0).to_numpy())
        r = PL.power_line(B.to_numpy() + x, B.to_numpy(), years)
        print("POWER LINE (coin-flip directions on the primary's schedule: %d trades, %.0f a year; scaled to a $30k "
              "own drawdown, x%.3f NQ)" % (int(on.sum()), on.sum() / years, 30000.0 / dd))
        print("  SD of the bootstrapped book-add ROC@$30k lead %.1f points; 5%% line %.1f; 80%% line %.1f" % (
            r["sd"], r["line_5pct"], r["line_80pct"]))
        print("  (no real direction was computed)")
        return

    def line(lab, P, on):
        x = pd.Series(P, index=days).reindex(bdays, fill_value=0.0).to_numpy()
        st = HH.own(x, bdays)
        n = int(on.sum())
        pf = (P[P > 0].sum() / -P[P < 0].sum()) if (P < 0).any() else np.inf
        yrs = [x[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
        print("  %-34s n %5d (%4.0f/yr)  net $%9s  PF %.3f  DD $%7s  own ROC@30k %6.2f  Sortino %5.2f  years + %d/9" % (
            lab, n, n / years, format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
            sum(v > 0 for v in yrs)))
        return dict(x=x, st=st, n=n, pf=pf, yrs=yrs)

    rows = {}
    for cell in CELLS:
        z = cell_z(cell, O, C, funds)
        P, on = leg(O, C, z, cell[1], cell[2], wf)
        rows[cell] = line("%s to bar %d z0 %.1f%s" % ("+".join(cell[0]), cell[1], cell[2],
                                                     "  PRIMARY" if cell == PRIMARY else ""), P, on)
    zt = own_z(morning(O, C, PRIMARY[1]))
    Pt, ont = leg(O, C, zt, PRIMARY[1], PRIMARY[2], wf)
    twin = line("TWIN: NQ's own morning move", Pt, ont)

    rng = np.random.default_rng(SEED)
    null_max = np.empty(NULL_DRAWS)
    null_prim = np.empty(NULL_DRAWS)
    for i in range(NULL_DRAWS):
        perm = rng.permutation(len(days))
        vals = []
        for cell in CELLS:
            z = cell_z(cell, O, C, funds, perm=perm)
            P, _ = leg(O, C, z, cell[1], cell[2], wf)
            vals.append(HH.own(pd.Series(P, index=days).reindex(bdays, fill_value=0.0).to_numpy(), bdays)["roc"])
        vals = np.nan_to_num(np.array(vals), nan=-1e9)
        null_max[i], null_prim[i] = vals.max(), vals[0]
    q95 = float(np.percentile(null_max, 95))
    print("  family null (200 day-permuted fund mornings): family-max own ROC@30k p95 %.2f; primary-cell null median "
          "%.2f" % (q95, float(np.median(null_prim))))

    pr = rows[PRIMARY]
    x, dd1 = HH.scaled(pr["x"])
    bb = HH.own(B.to_numpy() + x, bdays)
    print("  BOOK #463 + BONDLEAD primary at a $30k own drawdown (x%.3f NQ): ROC@30k %.2f  Sortino %.3f" % (
        30000.0 / dd1, bb["roc"], bb["sort"]))
    idx = PL.stationary_indices(len(x), 1000, 20, np.random.default_rng(SEED))
    lead = PL.roc30((B.to_numpy() + x)[idx], years) - PL.roc30(B.to_numpy()[idx], years)
    lead = lead[np.isfinite(lead)]
    p5 = float(np.percentile(lead, 5))
    print("  paired bootstrap (mean block 20, 1,000 draws) book-add lead: 5th percentile %+.1f (SD %.1f)" % (
        p5, float(lead.std(ddof=1))))
    for a, b in (("2020-03-02", "2020-03-27"), ("2022-01-03", "2022-12-30"), ("2025-02-19", "2025-04-30")):
        m = (bdays >= pd.Timestamp(a)) & (bdays <= pd.Timestamp(b))
        print("  %s .. %s: #463 $%s, BONDLEAD primary at that size $%s" % (
            a, b, format(int(B.to_numpy()[m].sum()), ","), format(int(x[m].sum()), ",")))

    st = pr["st"]
    a1 = st["roc"] >= HH.BAR_OWN and pr["pf"] > 1 and pr["n"] >= 100 and pr["n"] / years >= 50 and sum(
        v > 0 for v in pr["yrs"]) >= 6
    a2 = st["roc"] > q95
    a3 = all(rows[c]["st"]["net"] > 0 for c in CELLS[1:])
    a4 = bb["roc"] >= HH.BAR_BOOK_ROC and bb["sort"] >= HH.BAR_BOOK_SORT and p5 > 0
    a5 = st["roc"] > twin["st"]["roc"]
    print("")
    for lab, ok in (("A1 own ROC@30k >= 15, PF > 1, >= 100 trades and 50 a year, >= 6 of 9 years", a1),
                    ("A2 primary above the day-permuted family null's p95", a2),
                    ("A3 all three neighbours net positive after cost", a3),
                    ("A4 book add >= 98.50 / Sortino 3.816 and bootstrap p5 > 0", a4),
                    ("A5 primary beats NQ's own-morning twin on own ROC@30k", a5)):
        print("  %-75s %s" % (lab, "PASS" if ok else "FAIL"))
    print("")
    print("STAGE A: %s" % ("PASS -> pinned Auto-Validate the same day (BONDLEAD_1_0 plugin, parity first)"
                         if all((a1, a2, a3, a4, a5)) else "FAIL - recorded dead, no variants"))


if __name__ == "__main__":
    main(sys.argv[1:])
