# -*- coding: utf-8 -*-
"""NOISE on the sector funds, own crowns - Stage A (docs/PREREG_noise_sectors_r1_2026-10-08.md; scope A2).

IWM r1's design fund by fund (tools/noise_iwm_r1_stageA.py imported unchanged through tools/noise_fund_r1_common.py):
the frozen 54-cell NOISE_1_0 grid, the two NQ filters INHERITED and ON (a twin row prints each crown with both OFF),
unit = floor($100k / the fund's 2016-06-30 close), $0.02 a share as traded, walk-forward exit dates 2016-07-01 ..
2025-06-29 (nothing later loads). Funds in MANAGER #67's order: XLK, XLY, XLI, XLV, XLP, XLU, XLF.

Null (review #73 item 1): ONE random sign per SESSION per draw, shared by every cell and every fund, applied to each
cell's realised daily gross (cost kept); 2,000 draws; statistic = the MAX own ROC@$30k over all 378 cells (prices the fund
choice and the cell); each fund's own 54-cell p95 is printed beside it as a report. (IWM r1 flipped each trade
independently, 200 draws - this rule is the reviewed one.)
Reports added by review #73: ex-dividend sessions (item 3), each crown's daily correlation with NOISE #422 and #463
(item 6), the crown at a constant $100k a trade (item 7).

  python tools/noise_sectors_r1_stageA.py --power   power lines per fund from a coin-flip CENTRE cell; no real direction
  python tools/noise_sectors_r1_stageA.py           Stage A (all seven funds)
  python tools/noise_sectors_r1_stageA.py --dry     the whole Stage A path on coin-flip directions (smoke test)
"""
import sys

import numpy as np
import pandas as pd

import noise_fund_r1_common as C

FUNDS = ("XLK", "XLY", "XLI", "XLV", "XLP", "XLU", "XLF")


def main(argv):
    if "--dry" in argv:
        C.DRY = True
        print("DRY RUN - every cell's directions are a coin flip; no real direction is computed; nothing here is a result")
    B, ref = C.HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("NOISE on the sector funds r1 - cost $%.2f a share as traded; WF exit dates %s .. %s" % (
        C.R8.COST, bdays[0].date(), bdays[-1].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    data = {}
    for f in FUNDS:
        data[f] = C.load(f)
        print("  %s unit %d shares (2016-06-30 close)" % (f, data[f][1]))

    if "--power" in argv:
        for f in FUNDS:
            a5, unit, q = data[f]
            df = C.cell(f, C.CENTRE, a5, unit, q)
            coin = np.random.default_rng(C.SEED).choice([-1.0, 1.0], size=len(df))
            cst = C.R8.COST * unit * df.ratio.to_numpy()
            df = df.assign(pnl=coin * (df.pnl.to_numpy() + cst) - cst)
            print("POWER LINES %s (coin-flip directions on the CENTRE cell's %d WF trades, %.0f a year)" % (
                f, len(df), len(df) / years))
            C.HH.power_lines(C.daily(df, bdays), B, years)
        print("  (no real direction was computed; coin seed %d, fixed - re-running reproduces these lines)" % C.SEED)
        return

    res = {f: {} for f in FUNDS}
    for f in FUNDS:
        a5, unit, q = data[f]
        for c in C.GRID:
            df = C.cell(f, c, a5, unit, q)
            res[f][c] = (df, C.own(df, bdays))
    S = C.session_signs(bdays)
    per_fund = {}
    for f in FUNDS:
        per_fund[f] = np.nanmax(np.vstack([C.roc_draws(res[f][c][0], data[f][1], bdays, S) for c in C.GRID]), axis=0)
    pooled = np.nanmax(np.vstack([per_fund[f] for f in FUNDS]), axis=0)
    q95 = float(np.percentile(pooled, 95))
    print("  POOLED null (378 cells, one sign per session shared by all cells and funds, %d draws): max own ROC@30k p95 "
          "%.2f" % (len(S), q95))
    n422 = C.book_series(bdays)

    passed = []
    for f in FUNDS:
        a5, unit, q = data[f]
        rocs = np.array([res[f][c][1]["roc"] for c in C.GRID], float)
        best = max(C.GRID, key=lambda c: np.nan_to_num(res[f][c][1]["roc"], nan=-1e9))
        df, st = res[f][best]
        x = C.daily(df, bdays)
        pf = df.pnl[df.pnl > 0].sum() / -df.pnl[df.pnl < 0].sum() if (df.pnl < 0).any() else np.inf
        print("")
        print("=" * 110)
        print("%s - grid median %.2f, best %.2f at lookback %d / long %.2f / short %.2f / stop %.2f; cells > 0: %d; "
              "own 54-cell null p95 %.2f (report)" % (f, np.nanmedian(rocs), st["roc"], *best, int((rocs > 0).sum()),
                                                    float(np.percentile(per_fund[f], 95))))
        C.day_structure(df, f)
        n = len(df)
        print("  CROWN n %d (%.0f/yr)  net $%s  PF %.3f  DD $%s  own ROC@30k %.2f  Sortino %.2f  %s" % (
            n, n / years, format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
            C.dd5_line(df, bdays)))
        nbr = [res[f][c][1]["roc"] for c in C.neighbours(best)]
        print("  neighbours (one step on one axis): %s" % ", ".join("%.1f" % v for v in nbr))
        yrs = C.reports(df, unit, bdays, years, x)
        dfo = C.cell(f, best, a5, unit, q, base=C.FILTERS_OFF)
        so = C.own(dfo, bdays)
        print("  TWIN crown with both INHERITED NQ filters OFF: n %d  net $%s  own ROC@30k %.2f  %s" % (
            len(dfo), format(int(so["net"]), ","), so["roc"], C.dd5_line(dfo, bdays)))
        k, m = C.history_share(a5)
        print("  REPORT WF sessions whose range filter had < 252 prior sessions: %d of %d (%.1f%%)" % (k, m, 100 * k / m))
        print("  REPORT %s" % C.ex_dividend_line(df, f))
        k100 = 100000.0 / (df.px.to_numpy() * unit)
        s100 = C.own(df.assign(pnl=df.pnl.to_numpy() * k100), bdays)
        print("  REPORT crown at a constant $100k a trade: net $%s  own ROC@30k %.2f" % (format(int(s100["net"]), ","),
                                                                                     s100["roc"]))
        print("  REPORT daily P&L correlation: with NOISE #422 %.2f, with BOOK #463 %.2f" % (
            np.corrcoef(x, n422.to_numpy())[0, 1], np.corrcoef(x, B.to_numpy())[0, 1]))
        shadow = C.HH.book_report(x, B, years, "NOISE-" + f)
        ok = C.bars(st, pf, n, years, yrs, x, bdays, B, "NOISE-" + f, q95, nbr)
        print("  A4 (REPORT) vol-scale book add >= 98.50 / 3.816 with p5 > 0: %s" % ("yes" if shadow else "no"))
        print("  %s STAGE A: %s" % (f, "PASS" if ok else "FAIL"))
        if ok:
            passed.append(f)
    print("")
    print("STAGE A: %s" % ("PASS for %s -> a pinned 900-trial Auto-Validate the same day for each" % ", ".join(passed)
                         if passed else "FAIL on all seven - recorded dead, no variants"))


if __name__ == "__main__":
    main(sys.argv[1:])
