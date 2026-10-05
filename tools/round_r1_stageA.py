# -*- coding: utf-8 -*-
"""ROUND r1 STAGE A - stop cascades at round NQ prices (docs/PREREG_round_r1_2026-10-05.md).

Osler (2003, 2005): take-profit orders cluster AT round prices and stop-loss orders just BEYOND them, so a trend that
crosses a round price tends to accelerate (stops fire) and one that touches it without crossing tends to turn (take-
profits fill). Levels are fixed by arithmetic - multiples of G points on the RAW front-month price - never by the tape.

  CROSS    a 5m bar CLOSES across a level (previous close in the same session on the other side): trade 1 NQ in the
           crossing direction from the next bar's open, out H minutes later at a bar close (or the 15:55 bar's close)
  REVERSE  a bar's high reaches the level above the previous close (low reaches the level below) but closes back on
           the same side: trade 1 NQ the other way, same entry and exit
Signal bars 09:35 .. 15:20 (bar starts); one position at a time per cell; cost 0.533 pt a round trip; no stop.
Cells: CROSS G100 H30 PRIMARY, CROSS G100 H60, CROSS G50 H30, REVERSE G100 H30.
Family null: the same four cells on a grid shifted OFF the round numbers (offset f x G, f ~ U(0.1, 0.9), 200 draws,
one f per draw for all four cells) - same volatility, same trend content, same crossing rate, no round numbers.
Walk-forward stretch only (2016-07-01 .. 2025-06-29); the master is loaded with date_to 2025-06-29.

  python tools/round_r1_stageA.py --power   -> the power line from a COIN-FLIP leg on the primary's schedule
  python tools/round_r1_stageA.py           -> Stage A
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import halfhour_r1_stageA as HH                                       # noqa: E402  (book, stats, scaling, loaders)
import power_line as PL                                               # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402

COST, M = HH.COST, HH.M
PRIMARY = ("CROSS", 100, 30)
CELLS = [PRIMARY, ("CROSS", 100, 60), ("CROSS", 50, 30), ("REVERSE", 100, 30)]
K0, K1 = 1, 70                                                        # signal bars 09:35 .. 15:20
NULL_DRAWS, SEED = 200, 20261005


def bars():
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from=HH.D0,
                           date_to=HH.WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= HH.WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    day = pd.Index(ts.date)
    days = pd.Index(sorted(set(day)))
    di = days.get_indexer(day)
    ok = (k >= 0) & (k < 78)
    out = {}
    for f in ("open", "high", "low", "close"):
        X = np.full((len(days), 78), np.nan)
        X[di[ok], k[ok]] = np.asarray(A[f], float)[ok]
        out[f] = X
    keep = ~np.isnan(out["close"][:, 77])
    return pd.DatetimeIndex(days[keep]), {f: X[keep] for f, X in out.items()}


def signals(X, rule, G, u):
    """(D, 78) array of +1 / -1 / 0 at the signal bar."""
    C, Hh, Ll = X["close"], X["high"], X["low"]
    m = np.floor((C - u) / G)
    mp = np.full_like(m, np.nan)
    mp[:, 1:] = m[:, :-1]
    s = np.zeros(C.shape)
    if rule == "CROSS":
        s = np.where(m > mp, 1.0, np.where(m < mp, -1.0, 0.0))
    else:
        up_touch = Hh >= u + G * (mp + 1)
        dn_touch = Ll <= u + G * mp
        same = m == mp
        s = np.where(same & up_touch & ~dn_touch, -1.0, np.where(same & dn_touch & ~up_touch, 1.0, 0.0))
    s[:, :K0] = 0.0
    s[:, K1 + 1:] = 0.0
    s[np.isnan(mp) | np.isnan(m)] = 0.0
    return s


def trades(X, s, H, coin=None):
    """Greedy one-position-at-a-time per cell. Returns (D, 78) $ P&L at the signal bar, and the taken mask."""
    D = s.shape[0]
    O, C = X["open"], X["close"]
    hb = H // 5
    P = np.zeros(s.shape)
    on = np.zeros(s.shape, bool)
    held = np.zeros(s.shape)
    dd_, kk_ = np.nonzero(s)
    free_d, free_k = -1, -1
    for d, k in zip(dd_, kk_):
        if d == free_d and k <= free_k:
            continue
        e = min(k + hb, 77)
        if np.isnan(O[d, k + 1]) or np.isnan(C[d, e]):
            continue
        side = s[d, k] if coin is None else coin[d, k]
        P[d, k] = (side * (C[d, e] - O[d, k + 1]) - COST) * M
        on[d, k] = True
        held[d, k + 1:e + 1] = side
        free_d, free_k = d, e
    assert D == s.shape[0]
    trades.held = held
    return P, on


def run_cell(X, cell, u_frac=0.0, coin=None):
    rule, G, H = cell
    return trades(X, signals(X, rule, G, u_frac * G), H, coin)


def main(argv):
    days, X = bars()
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    wfd = (days >= HH.WF0) & (days <= HH.WF1)
    Xw = {f: np.where(wfd[:, None], v, np.nan) for f, v in X.items()}  # trades only inside the WF stretch
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("ROUND r1 - NQ 5m RTH no-adjust (raw front-month prices), %d full sessions, %d in the WF stretch" % (
        len(days), int(wfd.sum())))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))

    if "--power" in argv:
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=X["close"].shape)
        P, on = run_cell(Xw, PRIMARY, coin=coin)
        print("POWER LINES (coin-flip directions on the primary's schedule: %d trades, %.0f a year; amendment 1)" % (
            int(on.sum()), on.sum() / years))
        HH.power_lines(HH.daily(P, days, bdays).to_numpy(), B, years)
        print("  (no real direction was computed)")
        return

    rows = {}
    for cell in CELLS:
        P, on = run_cell(Xw, cell)
        x = HH.daily(P, days, bdays).to_numpy()
        st = HH.own(x, bdays)
        n = int(on.sum())
        pf = (P[P > 0].sum() / -P[P < 0].sum()) if (P < 0).any() else np.inf
        yrs = [x[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
        rows[cell] = dict(x=x, st=st, n=n, pf=pf, yrs=yrs)
        print("  %-26s n %5d (%4.0f/yr)  net $%9s  PF %.3f  DD $%7s  own ROC@30k %6.2f  Sortino %5.2f  "
              "gross %.2f pt/trade  years + %d/9" % (
                  "%s G%d H%d%s" % (cell + ("  PRIMARY" if cell == PRIMARY else "",)), n, n / years,
                  format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
                  float((P[on] / M + COST).mean()) if n else float("nan"), sum(v > 0 for v in yrs)))

    rng = np.random.default_rng(SEED)
    null_max, null_prim = np.empty(NULL_DRAWS), np.empty(NULL_DRAWS)
    for i in range(NULL_DRAWS):
        f = rng.uniform(0.1, 0.9)
        vals = np.array([HH.own(HH.daily(run_cell(Xw, c, f)[0], days, bdays).to_numpy(), bdays)["roc"] for c in CELLS])
        vals = np.nan_to_num(vals, nan=-1e9)
        null_max[i], null_prim[i] = vals.max(), vals[0]
    q95 = float(np.percentile(null_max, 95))
    print("  family null (200 off-round grids): family-max own ROC@30k p95 %.2f; primary-cell null median %.2f" % (
        q95, float(np.median(null_prim))))

    pr = rows[PRIMARY]
    P, on = run_cell(Xw, PRIMARY)
    print("  REPORT overlap with #463 legs on ROUND's held bars: %s" % HH.overlap(trades.held, HH.book_positions(days)))
    m20 = (bdays >= pd.Timestamp("2022-01-01")) & (bdays <= pd.Timestamp("2022-12-31"))
    print("  REPORT calendar 2022: #463 $%s, ROUND primary at 1 NQ $%s" % (
        format(int(B.to_numpy()[m20].sum()), ","), format(int(pr["x"][m20].sum()), ",")))
    shadow = HH.book_report(pr["x"], B, years, "ROUND")
    a1, no2020, route = HH.standalone(pr["st"], pr["pf"], pr["n"], years, pr["yrs"], pr["x"], bdays, B, "ROUND")
    a2 = pr["st"]["roc"] > q95
    a3 = all(rows[c]["st"]["net"] > 0 for c in CELLS[1:3])
    print("")
    for lab, ok in (("A1 own ROC@30k >= 15 or earner route (%s), PF > 1, >= 100 and 50/yr, >= 6 of 9 years" % route, a1),
                    ("A1b no-2020: the same route holds without calendar 2020", no2020),
                    ("A2 primary above the off-round family null's p95", a2),
                    ("A3 both CROSS neighbours net positive after cost", a3)):
        print("  %-80s %s" % (lab, "PASS" if ok else "FAIL"))
    print("  A4 (REPORT, house line #45) vol-scale book add >= 98.50 / 3.816 with p5 > 0: %s -> %s" % (
        "yes" if shadow else "no", "forward BOOK shadow line too" if shadow else "standalone only"))
    print("")
    print("STAGE A: %s" % ("PASS -> pinned Auto-Validate the same day (ROUND_1_0 plugin, parity first)"
                         if all((a1, no2020, a2, a3)) else "FAIL - recorded dead, no variants"))

if __name__ == "__main__":
    main(sys.argv[1:])
