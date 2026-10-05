# -*- coding: utf-8 -*-
"""HALFHOUR r1 STAGE A - same-half-hour seasonality on NQ (docs/PREREG_halfhour_r1_2026-10-05.md).

Heston, Korajczyk & Sadka (2010): a half-hour's return repeats at the SAME half-hour on later days (for 40+ sessions),
while other half-hours do not - the footprint of institutions that trade on a fixed clock (Bogousslavsky 2016:
infrequent rebalancing). Rule: at the start of each of the 13 RTH half-hours, take the mean of that same slot's return
over the previous L valid sessions; scale by the slot's own trailing-250-session SD / sqrt(L); if |t| >= z, trade NQ in
the sign of the mean from the slot's first 5m open to its last 5m close. 1 NQ, cost 0.533 pt a round trip, no stop.

Cells L x z = (40, 1.0) PRIMARY, (20, 1.0), (40, 2.0), (20, 2.0). Family null: the same four cells with the signal of
slot h taken from a different slot (200 random derangements of the 13 slots) - keeps recent-drift and trade density,
removes only the same-slot alignment the mechanism claims. Walk-forward stretch only (2016-07-01 .. 2025-06-29); the
master is loaded with date_to 2025-06-29, so nothing later exists in memory.

  python tools/halfhour_r1_stageA.py --power   -> the power line from a COIN-FLIP leg on the primary's schedule
                                                  (no real direction is computed)
  python tools/halfhour_r1_stageA.py           -> Stage A
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
import power_line as PL                                                 # noqa: E402

COST, M = 0.533, 20.0
D0, WF0, WF1 = "2010-06-07", pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")
NSLOT, BARS, HIST = 13, 6, 250
PRIMARY = (40, 1.0)
CELLS = [PRIMARY, (20, 1.0), (40, 2.0), (20, 2.0)]
NULL_DRAWS, SEED = 200, 20261005
BAR_OWN, BAR_BOOK_ROC, BAR_BOOK_SORT = 15.0, 98.50, 3.816


def slot_returns():
    """R[d, h] = close of the slot's last 5m bar - open of its first (points); NaN when any of the six bars is missing.
    Sessions without a 15:55 bar (half days, broken sessions) are dropped whole."""
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    o, c = np.asarray(A["open"], float), np.asarray(A["close"], float)
    mins = ts.hour * 60 + ts.minute - 570                                  # minutes after 09:30
    k = np.asarray(mins // 5)
    day = pd.Index(ts.date)
    days = pd.Index(sorted(set(day)))
    di = days.get_indexer(day)
    O = np.full((len(days), 78), np.nan)
    Cl = np.full((len(days), 78), np.nan)
    ok = (k >= 0) & (k < 78)
    O[di[ok], k[ok]] = o[ok]
    Cl[di[ok], k[ok]] = c[ok]
    full = ~np.isnan(Cl[:, 77])
    R = np.full((len(days), NSLOT), np.nan)
    for h in range(NSLOT):
        a, b = h * BARS, h * BARS + BARS - 1
        have = ~np.isnan(O[:, a:b + 1]).any(axis=1) & ~np.isnan(Cl[:, a:b + 1]).any(axis=1)
        R[:, h] = np.where(have, Cl[:, b] - O[:, a], np.nan)
    keep = full
    return pd.DatetimeIndex(days[keep]), R[keep]


def signals(R, L):
    """S[d, h] = mean of the slot's previous L valid returns; T = S / (sd of previous HIST valid / sqrt(L)).
    Only sessions BEFORE d enter; NaN until HIST valid observations exist."""
    D = R.shape[0]
    S = np.full(R.shape, np.nan)
    T = np.full(R.shape, np.nan)
    for h in range(NSLOT):
        v = np.flatnonzero(~np.isnan(R[:, h]))
        x = R[v, h]
        cs = np.r_[0.0, np.cumsum(x)]
        cs2 = np.r_[0.0, np.cumsum(x * x)]
        for j in range(HIST, len(v)):                                      # signal for observation j uses x[:j]
            m = (cs[j] - cs[j - L]) / L
            s1, s2 = cs[j] - cs[j - HIST], cs2[j] - cs2[j - HIST]
            var = (s2 - s1 * s1 / HIST) / (HIST - 1)
            if var > 0:
                S[v[j], h] = m
                T[v[j], h] = m / (np.sqrt(var) / np.sqrt(L))
        assert D == R.shape[0]
    return S, T


def leg_pnl(R, S, T, z, perm=None, coin=None):
    """Per-(day, slot) $ P&L of one NQ: trade slot h with the signal of slot perm[h] (identity = the real rule)."""
    p = np.arange(NSLOT) if perm is None else perm
    Sp, Tp = S[:, p], T[:, p]
    on = (np.abs(Tp) >= z) & ~np.isnan(R) & ~np.isnan(Tp)
    side = np.sign(Sp) if coin is None else coin
    return np.where(on, (side * R - COST) * M, 0.0), on


def daily(P, days, bdays):
    return pd.Series(P.sum(axis=1), index=days).reindex(bdays, fill_value=0.0)


def own(x, bdays):
    import r11_risk as R11
    return R11.stats(np.asarray(x, float), bdays)


def derangement(rng):
    while True:
        p = rng.permutation(NSLOT)
        if not (p == np.arange(NSLOT)).any():
            return p


def book():
    from api.book_shadow import book463_valued_daily
    B = book463_valued_daily(D0, WF1.strftime("%Y-%m-%d"))
    B = B[(B.index >= WF0) & (B.index <= WF1)]
    ref = own(B.to_numpy(), B.index)
    assert abs(ref["roc"] - 93.81) < 0.05 and abs(ref["sort"] - 3.816) < 0.005, "BOOK PARITY FAILED - abort"
    return B, ref


def scaled(x):
    cum = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum).max())
    return x * (30000.0 / dd) if dd > 0 else x, dd


def main(argv):
    days, R = slot_returns()
    B, ref = book()
    bdays = pd.DatetimeIndex(B.index)
    wfd = (days >= WF0) & (days <= WF1)
    lost = int((~days[wfd].isin(bdays)).sum())
    print("HALFHOUR r1 - NQ 5m RTH no-adjust, %d full sessions loaded (%s .. %s), %d in the WF stretch; %d WF sessions "
          "not on the book's day index" % (len(days), days[0].date(), days[-1].date(), int(wfd.sum()), lost))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    sig = {L: signals(R, L) for L in sorted({c[0] for c in CELLS})}
    Rw = np.where(wfd[:, None], R, np.nan)                                 # trades only inside the WF stretch
    years = (bdays[-1] - bdays[0]).days / 365.25

    if "--power" in argv:
        S, T = sig[PRIMARY[0]]
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=R.shape)
        P, on = leg_pnl(Rw, S, T, PRIMARY[1], coin=coin)
        x, dd = scaled(daily(P, days, bdays).to_numpy())
        r = PL.power_line(B.to_numpy() + x, B.to_numpy(), years)
        print("POWER LINE (coin-flip directions on the primary's schedule: %d trades, %.0f a year; scaled to a $30k "
              "own drawdown, x%.3f NQ)" % (int(on.sum()), on.sum() / years, 30000.0 / dd))
        print("  SD of the bootstrapped book-add ROC@$30k lead %.1f points; 5%% line %.1f; 80%% line %.1f" % (
            r["sd"], r["line_5pct"], r["line_80pct"]))
        print("  (no real direction was computed)")
        return

    rows = {}
    for L, z in CELLS:
        S, T = sig[L]
        P, on = leg_pnl(Rw, S, T, z)
        x = daily(P, days, bdays).to_numpy()
        st = own(x, bdays)
        n = int(on.sum())
        g = P[on] / M + COST
        pf = (P[P > 0].sum() / -P[P < 0].sum()) if (P < 0).any() else np.inf
        yrs = [x[(bdays >= pd.Timestamp(y, 7, 1)) & (bdays < pd.Timestamp(y + 1, 7, 1))].sum() for y in range(2016, 2025)]
        rows[(L, z)] = dict(x=x, st=st, n=n, pf=pf, yrs=yrs, P=P, on=on)
        print("  %-22s n %5d (%4.0f/yr)  net $%9s  PF %.3f  DD $%7s  own ROC@30k %6.2f  Sortino %5.2f  "
              "gross %.2f pt/trade  years + %d/9" % (
                  "L %d z %.1f%s" % (L, z, "  PRIMARY" if (L, z) == PRIMARY else ""), n, n / years,
                  format(int(st["net"]), ","), pf, format(int(st["max_dd"]), ","), st["roc"], st["sort"],
                  float(g.mean()) if n else float("nan"), sum(v > 0 for v in yrs)))

    rng = np.random.default_rng(SEED)
    null_max, null_prim = np.empty(NULL_DRAWS), np.empty(NULL_DRAWS)
    for i in range(NULL_DRAWS):
        p = derangement(rng)
        vals = []
        for L, z in CELLS:
            S, T = sig[L]
            P, _ = leg_pnl(Rw, S, T, z, perm=p)
            vals.append(own(daily(P, days, bdays).to_numpy(), bdays)["roc"])
        vals = np.nan_to_num(np.array(vals), nan=-1e9)
        null_max[i], null_prim[i] = vals.max(), vals[0]
    q95 = float(np.percentile(null_max, 95))
    print("  family null (200 wrong-slot derangements): family-max own ROC@30k p95 %.2f; primary-cell null median %.2f"
          % (q95, float(np.median(null_prim))))

    pr = rows[PRIMARY]
    x, dd1 = scaled(pr["x"])
    bb = own(B.to_numpy() + x, bdays)
    print("  BOOK #463 + HALFHOUR primary at a $30k own drawdown (x%.3f NQ): ROC@30k %.2f  Sortino %.3f" % (
        30000.0 / dd1, bb["roc"], bb["sort"]))
    r = PL.power_line(B.to_numpy() + x, B.to_numpy(), years)              # spread only - same draws as the bar below
    idx = PL.stationary_indices(len(x), 1000, 20, np.random.default_rng(SEED))
    lead = PL.roc30((B.to_numpy() + x)[idx], years) - PL.roc30(B.to_numpy()[idx], years)
    p5 = float(np.percentile(lead[np.isfinite(lead)], 5))
    print("  paired bootstrap (mean block 20, 1,000 draws) book-add lead: 5th percentile %+.1f (SD %.1f)" % (p5, r["sd"]))
    m20 = (bdays >= pd.Timestamp("2020-03-02")) & (bdays <= pd.Timestamp("2020-03-27"))
    print("  #463's worst WF drawdown weeks (2020-03-02 .. 03-27): HALFHOUR primary at that size $%s" % format(
        int(x[m20].sum()), ","))

    st = pr["st"]
    a1 = st["roc"] >= BAR_OWN and pr["pf"] > 1 and pr["n"] >= 100 and pr["n"] / years >= 50 and sum(
        v > 0 for v in pr["yrs"]) >= 6
    a2 = st["roc"] > q95
    a3 = all(rows[c]["st"]["net"] > 0 for c in CELLS[1:])
    a4 = bb["roc"] >= BAR_BOOK_ROC and bb["sort"] >= BAR_BOOK_SORT and p5 > 0
    print("")
    for lab, ok in (("A1 own ROC@30k >= 15, PF > 1, >= 100 trades and 50 a year, >= 6 of 9 years", a1),
                    ("A2 primary above the wrong-slot family null's p95", a2),
                    ("A3 all three neighbours net positive after cost", a3),
                    ("A4 book add >= 98.50 / Sortino 3.816 and bootstrap p5 > 0", a4)):
        print("  %-75s %s" % (lab, "PASS" if ok else "FAIL"))
    print("")
    print("STAGE A: %s" % ("PASS -> pinned Auto-Validate the same day (HALFHOUR_1_0 plugin, parity first)"
                         if all((a1, a2, a3, a4)) else "FAIL - recorded dead, no variants"))


if __name__ == "__main__":
    main(sys.argv[1:])
