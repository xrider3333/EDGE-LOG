# -*- coding: utf-8 -*-
"""The NOISE FADE on TLT r1 - Stage A (docs/PREREG_noise_tltfade_r1_2026-10-08.md; scope A4).

The fade = the MIRROR of every NOISE_1_0 trade on TLT: same entry bar, exit bar and exit price, opposite direction;
fade P&L = -(NOISE gross P&L) - cost. NOISE_1_0 underneath with VWAP exit, bandwidth stop, flat at the close, both
sides, all day, confirm 1 and the two NQ filters OFF. IWM r1's 54-cell grid and unit / cost / walk-forward rules
(tools/noise_fund_r1_common.py); CROWN = the best WF own ROC@$30k of the FADE; null (review #73 item 1) = ONE random sign
per SESSION per draw shared by all 54 cells, 2,000 draws, statistic = the family max. IEF (tainted - its NOISE number was
seen in TRANSFER r2) is reported only. Review #73 reports: ex-dividend sessions (3), the 10 worst fade days with TLT's
open-to-close move and the fade on #463's drawdown days / episodes (10), the filters-ON twin (12), the map row (13).

  python tools/noise_tltfade_r1_stageA.py --power   power lines from a coin-flip CENTRE cell; no real direction
  python tools/noise_tltfade_r1_stageA.py           Stage A
  python tools/noise_tltfade_r1_stageA.py --dry     the whole Stage A path on coin-flip directions (smoke test)
"""
import sys

import numpy as np
import pandas as pd

import noise_fund_r1_common as C

FUND, TAINTED = "TLT", "IEF"


def fade(fund, c, a5, unit, q):
    return C.cell(fund, c, a5, unit, q, base=C.FILTERS_OFF, fade=True)


def main(argv):
    if "--dry" in argv:
        C.DRY = True
        print("DRY RUN - every cell's directions are a coin flip; no real direction is computed; nothing here is a result")
    B, ref = C.HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    a5, unit, q = C.load(FUND)
    print("NOISE FADE on TLT r1 - unit %d shares (2016-06-30 close), cost $%.2f a share as traded; WF exit dates %s .. %s"
          % (unit, C.R8.COST, bdays[0].date(), bdays[-1].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))

    if "--power" in argv:
        df = fade(FUND, C.CENTRE, a5, unit, q)
        coin = np.random.default_rng(C.SEED).choice([-1.0, 1.0], size=len(df))
        cst = C.R8.COST * unit * df.ratio.to_numpy()
        df = df.assign(pnl=coin * (df.pnl.to_numpy() + cst) - cst)
        print("POWER LINES (coin-flip directions on the CENTRE cell's %d WF trades, %.0f a year)" % (len(df), len(df) / years))
        C.HH.power_lines(C.daily(df, bdays), B, years)
        print("  (no real direction was computed; coin seed %d, fixed - re-running reproduces these lines)" % C.SEED)
        return

    res = {c: None for c in C.GRID}
    for c in C.GRID:
        df = fade(FUND, c, a5, unit, q)
        res[c] = (df, C.own(df, bdays))
    rocs = np.array([res[c][1]["roc"] for c in C.GRID], float)
    best = max(C.GRID, key=lambda c: np.nan_to_num(res[c][1]["roc"], nan=-1e9))
    S = C.session_signs(bdays)
    nmax = np.nanmax(np.vstack([C.roc_draws(res[c][0], unit, bdays, S) for c in C.GRID]), axis=0)
    q95 = float(np.percentile(nmax, 95))
    df, st = res[best]
    x = C.daily(df, bdays)
    pf = df.pnl[df.pnl > 0].sum() / -df.pnl[df.pnl < 0].sum() if (df.pnl < 0).any() else np.inf
    n = len(df)
    print("  grid: 54 cells, fade own ROC@30k median %.2f, best %.2f at lookback %d / long %.2f / short %.2f / stop %.2f; "
          "cells > 0: %d" % (np.nanmedian(rocs), st["roc"], *best, int((rocs > 0).sum())))
    print("  family null (one sign per session shared by all cells, %d draws): family-max own ROC@30k p95 %.2f" % (
        len(S), q95))

    # printed before the bars: IEF (tainted, report only), the mechanism check, day structure
    a5i, uniti, qi = C.load(TAINTED)
    dfi = fade(TAINTED, best, a5i, uniti, qi)
    si = C.own(dfi, bdays)
    print("  REPORT IEF (TAINTED - seen in TRANSFER r2; never a bar) fade at the TLT crown's cell: n %d  net $%s  own ROC@30k "
          "%.2f" % (len(dfi), format(int(si["net"]), ","), si["roc"]))
    hc = C.held_to_close(df, a5)
    for lab, m in (("held to the close (the trend days the fade loses on)", hc),
                   ("exited earlier (VWAP or stop - the reversions it is built on)", ~hc)):
        h = df[m]
        print("  MECHANISM %-62s n %5d  net $%10s" % (lab, len(h), format(int(h.pnl.sum()), ",")))
    C.day_structure(df, FUND)

    print("  CROWN n %d (%.0f/yr)  net $%s  PF %.3f  DD $%s  own ROC@30k %.2f  Sortino %.2f  %s" % (
        n, n / years, format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
        C.dd5_line(df, bdays)))
    nbr = [res[c][1]["roc"] for c in C.neighbours(best)]
    print("  neighbours (one step on one axis): %s" % ", ".join("%.1f" % v for v in nbr))
    yrs = C.reports(df, unit, bdays, years, x)
    y22 = df[(df.date >= pd.Timestamp("2022-01-01")) & (df.date < pd.Timestamp("2023-01-01"))]
    print("  REPORT 2022 alone (the bond bear market): n %d  net $%s" % (len(y22), format(int(y22.pnl.sum()), ",")))
    print("  REPORT %s" % C.ex_dividend_line(df, FUND))
    dfon = C.cell(FUND, best, a5, unit, q, base=C.INHERITED, fade=True)
    son = C.own(dfon, bdays)
    print("  TWIN crown with both NQ filters ON (report): n %d  net $%s  own ROC@30k %.2f" % (
        len(dfon), format(int(son["net"]), ","), son["roc"]))
    print("  MAP ROW: crown $ a year at a $30k own drawdown $%s vs the map's >= $15,000 (reported, not a bar)" % (
        format(int(1000 * st["roc"]), ",")))
    # the 10 worst fade days with TLT's open-to-close move that session
    idx = pd.DatetimeIndex(a5["index"])
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    bars_ = pd.DataFrame({"o": np.asarray(a5["open"], float), "c": np.asarray(a5["close"], float)}, index=idx)
    day = bars_.groupby(bars_.index.normalize()).agg(o=("o", "first"), c=("c", "last"))
    oc = 100 * (day.c / day.o - 1)
    xs = pd.Series(x, index=bdays)
    print("  REPORT 10 worst fade days: %s" % "; ".join(
        "%s $%s (TLT open-to-close %+.2f%%)" % (d.date(), format(int(v), ","), oc.get(d, np.nan))
        for d, v in xs.nsmallest(10).items()))
    eps = C.dd_episodes(B)
    on = [xs[(xs.index >= a) & (xs.index <= b)].sum() for a, b in eps]
    days = sum(int(((bdays >= a) & (bdays <= b)).sum()) for a, b in eps)
    print("  REPORT on #463's %d drawdown episodes (%d days, house rule >= $14,950): fade $%s; episodes the fade made money "
          "in: %d of %d" % (len(eps), days, format(int(sum(on)), ","), sum(v > 0 for v in on), len(eps)))
    shadow = C.HH.book_report(x, B, years, "NOISE-FADE-TLT")
    print("")
    ok = C.bars(st, pf, n, years, yrs, x, bdays, B, "NOISE-FADE-TLT", q95, nbr)
    print("  A4 (REPORT) vol-scale book add >= 98.50 / 3.816 with p5 > 0: %s" % ("yes" if shadow else "no"))
    print("")
    print("STAGE A: %s" % ("PASS -> a fade switch in a strategy file, parity-checked against the mirror, then a pinned "
                         "900-trial Auto-Validate" if ok else "FAIL - recorded dead, no variants"))


if __name__ == "__main__":
    main(sys.argv[1:])
