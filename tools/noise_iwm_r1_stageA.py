# -*- coding: utf-8 -*-
"""NOISE on IWM, own crown - Stage A (docs/PREREG_noise_iwm_r1_2026-10-06.md; scope rank 2, MANAGER #57 / #63 / #64).

The NOISE mechanism (NOISE_1_0.py: noise-area break, VWAP exit, bandwidth stop, flat at the close, both sides, decisions
on bar closes; the crown's two banked filters ON - skip shorts after a weak prior close, skip the day after a top-5% prior
range) on IWM 5m RTH (Alpaca split-adjusted, the TRANSFER r2 master), with IWM's OWN settings from a frozen 54-cell grid:
  lookback 20 / 40 / 60  x  band_mult_long 0.5 / 0.75 / 1.0  x  band_mult_short 0.75 / 1.0 / 1.5  x  stop_k 1.25 / 1.75
Unit = floor($100,000 / IWM's 2016-06-30 close) shares; cost $0.02 a share round trip charged per share AS TRADED
(TRANSFER r2 addendum 2). Walk-forward stretch only: exit dates 2016-07-01 .. 2025-06-29; nothing after 2025-06-29 loads.

Family null: every cell's realised trades with their DIRECTION P&L sign flipped at random (200 draws, same entries, exits,
costs) - removes "trade with the break" and keeps timing, holding and cost; statistic = the family MAX own ROC@$30k.
CROWN = the cell with the best WF own ROC@$30k (selection disclosed; the null's family max prices it).

  python tools/noise_iwm_r1_stageA.py --power   power lines from a coin-flip version of the CENTRE cell (40 / 0.75 /
                                                1.0 / 1.75); no real direction is used
  python tools/noise_iwm_r1_stageA.py           Stage A
"""
import itertools
import math
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("EDGELOG_ROCFRONTIER_R8", r"C:\EdgeLog\_anatomy_cache\noise_iwm_r1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
import r8_transfer_etf as R8                                           # noqa: E402
import halfhour_r1_stageA as HH                                       # noqa: E402  (book, own stats, book report, standalone bars)

FUND = "IWM"
BASE = dict(exit_mode="vwap", side="Both", window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth",
            confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
GRID = list(itertools.product((20, 40, 60), (0.5, 0.75, 1.0), (0.75, 1.0, 1.5), (1.25, 1.75)))
CENTRE = (40, 0.75, 1.0, 1.75)
NULL_DRAWS, SEED = 200, 20261006
COST_BPS = (0, 5, 10, 20)                                             # round-trip cost curve, basis points of the entry price


def params(c):
    lb, bl, bs, k = c
    return dict(BASE, lookback=lb, band_mult_long=bl, band_mult_short=bs, stop_k=k)


def leg(c, unit, cost):
    return {"strategy": "NOISE_1_0.py", "params": params(c), "instrument": FUND, "timeframe": "5m", "session": "rth",
            "source": "alpaca_split_rth", "cost_pts": cost, "mult": unit, "weight": 1}


def load():
    a5 = R8.load(FUND, "5m", R8.PRE)
    R8.assert_volume(a5, FUND)
    close0 = R8.close_on(a5, "2016-06-30")
    q = R8.share_ratio(FUND, R8.LB0)[0]
    if close0 is None or q is None:
        raise SystemExit("IWM: no 2016-06-30 bar or no split/raw daily files")
    return a5, int(math.floor(R8.USD / close0)), q


def cell(c, a5, unit, q, cost=None):
    df = R8.run_leg(leg(c, unit, R8.COST if cost is None else cost), R8.D0, R8.PRE, a5)
    if cost is None:
        df = R8.as_traded(df, q, unit)
    return df[(df.date >= R8.WF0) & (df.date < R8.LB0)].reset_index(drop=True)


def daily(df, bdays):
    return df.groupby("date").pnl.sum().reindex(bdays, fill_value=0.0).to_numpy()


def main(argv):
    a5, unit, q = load()
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("NOISE on IWM r1 - unit %d shares (2016-06-30 close), cost $%.2f a share as traded; WF exit dates %s .. %s" % (
        unit, R8.COST, bdays[0].date(), bdays[-1].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))

    if "--power" in argv:
        df = cell(CENTRE, a5, unit, q)
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(df))
        gross = df.pnl.to_numpy() + R8.COST * unit * df.ratio.to_numpy()          # cost back in, sign flipped, cost out again
        df = df.assign(pnl=coin * gross - R8.COST * unit * df.ratio.to_numpy())
        print("POWER LINES (coin-flip directions on the CENTRE cell's %d WF trades, %.0f a year)" % (len(df), len(df) / years))
        HH.power_lines(daily(df, bdays), B, years)
        print("  (no real direction was computed)")
        return

    res = {}
    for c in GRID:
        df = cell(c, a5, unit, q)
        st = HH.own(daily(df, bdays), bdays)
        res[c] = (df, st)
    best = max(GRID, key=lambda c: np.nan_to_num(res[c][1]["roc"], nan=-1e9))
    rocs = np.array([res[c][1]["roc"] for c in GRID], float)
    print("  grid: 54 cells, own ROC@30k median %.2f, best %.2f at lookback %d / long %.2f / short %.2f / stop %.2f; "
          "cells > 0: %d" % (np.nanmedian(rocs), res[best][1]["roc"], *best, int((rocs > 0).sum())))

    rng = np.random.default_rng(SEED)
    nmax = np.empty(NULL_DRAWS)
    for i in range(NULL_DRAWS):
        vals = []
        for c in GRID:
            df = res[c][0]
            cst = R8.COST * unit * df.ratio.to_numpy()
            g = (df.pnl.to_numpy() + cst) * rng.choice([-1.0, 1.0], size=len(df)) - cst
            vals.append(HH.own(pd.Series(g, index=df.date).groupby(level=0).sum().reindex(bdays, fill_value=0.0)
                               .to_numpy(), bdays)["roc"])
        nmax[i] = np.nanmax(vals)
    q95 = float(np.percentile(nmax, 95))
    print("  family null (sign flips, 200 draws): family-max own ROC@30k p95 %.2f" % q95)

    df, st = res[best]
    x = daily(df, bdays)
    pf = df.pnl[df.pnl > 0].sum() / -df.pnl[df.pnl < 0].sum() if (df.pnl < 0).any() else np.inf
    yrs = [x[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
    n = len(df)
    print("  CROWN n %d (%.0f/yr)  net $%s  PF %.3f  DD $%s  own ROC@30k %.2f  Sortino %.2f  years + %d/9" % (
        n, n / years, format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
        sum(v > 0 for v in yrs)))
    # neighbours: one step on one axis
    axes = ((20, 40, 60), (0.5, 0.75, 1.0), (0.75, 1.0, 1.5), (1.25, 1.75))
    nb = []
    for i, ax in enumerate(axes):
        j = ax.index(best[i])
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(ax):
                c = list(best)
                c[i] = ax[jj]
                nb.append(tuple(c))
    nbr = [res[c][1]["roc"] for c in nb]
    print("  neighbours (one step on one axis): %s" % ", ".join("%.1f" % v for v in nbr))
    # addendum 2 diagnostics
    h1 = df[df.date < pd.Timestamp("2022-01-01")]
    h2 = df[df.date >= pd.Timestamp("2022-01-01")]
    for lab, h in (("H1 2016-21", h1), ("H2 2022-25", h2), ("longs", df[df.side > 0]), ("shorts", df[df.side < 0])):
        hp = h.pnl[h.pnl > 0].sum() / -h.pnl[h.pnl < 0].sum() if (h.pnl < 0).any() else np.inf
        print("  REPORT %-11s n %5d  net $%10s  PF %.3f" % (lab, len(h), format(int(h.pnl.sum()), ","), hp))
    print("  REPORT per July-June year $: %s" % ", ".join(format(int(v), ",") for v in yrs))
    for bps in COST_BPS:
        g = df.pnl.to_numpy() + R8.COST * unit * df.ratio.to_numpy()
        cst = bps / 1e4 * df.px.to_numpy() * unit
        s2 = HH.own(pd.Series(g - cst, index=df.date).groupby(level=0).sum().reindex(bdays, fill_value=0.0).to_numpy(),
                    bdays)
        print("  REPORT cost %2d bps round trip: net $%s  own ROC@30k %.2f" % (bps, format(int(s2["net"]), ","), s2["roc"]))
    shadow = HH.book_report(x, B, years, "NOISE-IWM")
    a1, no2020, route = HH.standalone(st, pf, n, years, yrs, x, bdays, B, "NOISE-IWM")
    a2 = st["roc"] > q95
    a3 = sum(v >= 0.5 * st["roc"] for v in nbr) >= math.ceil(len(nbr) / 2)
    print("")
    for lab, ok in (("A1 own ROC@30k >= 15 or earner route (%s), PF > 1, >= 100 and 50/yr, >= 6 of 9 years" % route, a1),
                    ("A1b no-2020: the same route holds without calendar 2020", no2020),
                    ("A2 crown above the sign-flip family null's p95 (prices the selection)", a2),
                    ("A3 plateau: at least half the one-step neighbours keep half the crown's ROC", a3)):
        print("  %-80s %s" % (lab, "PASS" if ok else "FAIL"))
    print("  A4 (REPORT, house line #45) vol-scale book add >= 98.50 / 3.816 with p5 > 0: %s; map row for an equity-index "
          "family: about $40k a year at a $30k own drawdown (reported, not a bar)" % ("yes" if shadow else "no"))
    print("")
    print("STAGE A: %s" % ("PASS -> pinned 900-trial Auto-Validate the same day (NOISE_1_0 on IWM, the grid's axes)"
                         if all((a1, no2020, a2, a3)) else "FAIL - recorded dead, no variants"))


if __name__ == "__main__":
    main(sys.argv[1:])
