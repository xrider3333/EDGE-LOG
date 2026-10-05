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


# ---- amendment 1 (MANAGER #44 / #45, 2026-10-05, before any real-direction run) ----------------------------------------
# Shared by HALFHOUR, ROUND and BONDLEAD r1: the book add is a REPORT (it opens a forward BOOK shadow line or not), sized
# by volatility (leg daily SD over the first two WF years = 25% of #463's daily SD on the same days); the $30k-own-
# drawdown sizing is reported beside it as the twin. The standalone bars decide the Auto-Validate.
VOL_END, VOL_SHARE = pd.Timestamp("2018-07-01"), 0.25
LEGCACHE = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "_anatomy_cache", "newtype_r1",
                        "book463_nq_positions.npz")


def vol_scaled(x, B, bdays):
    m = np.asarray((bdays >= WF0) & (bdays < VOL_END))
    sx = float(np.std(x[m], ddof=1))
    s = VOL_SHARE * float(np.std(B.to_numpy()[m], ddof=1)) / sx if sx > 0 else 0.0
    return x * s, s


def worst_window(B):
    """#463's worst walk-forward drawdown: (peak day, trough day) on its daily series."""
    cum = np.cumsum(B.to_numpy())
    peak = np.maximum.accumulate(cum)
    t1 = int(np.argmax(peak - cum))
    t0 = int(np.argmax(cum[:t1 + 1]))
    return B.index[t0], B.index[t1]


def power_lines(x, B, years):
    """Two power lines for a (coin-flip) leg: vol scale (the primary) and $30k own drawdown (the twin)."""
    bdays = pd.DatetimeIndex(B.index)
    xv, s = vol_scaled(x, B, bdays)
    xd, dd = scaled(x)
    for lab, xx, size in (("VOL scale (primary)", xv, s), ("$30k own drawdown (twin)", xd, 30000.0 / dd)):
        r = PL.power_line(B.to_numpy() + xx, B.to_numpy(), years)
        print("  %-26s x%.3f NQ: SD of the book-add lead %.1f points; 5%% line %.1f; 80%% line %.1f" % (
            lab, size, r["sd"], r["line_5pct"], r["line_80pct"]))


def book_report(x, B, years, name):
    """REPORT (house line #45): book + leg at both sizes, paired bootstrap p5; returns True when the VOL-scale add
    clears 98.50 / 3.816 with p5 > 0 (-> a forward BOOK shadow line is also opened)."""
    bdays = pd.DatetimeIndex(B.index)
    out = None
    for lab, (xx, s) in (("VOL scale", vol_scaled(x, B, bdays)), ("$30k own DD (twin)", (lambda t: (t[0], 30000.0 / t[1]))(scaled(x)))):
        bb = own(B.to_numpy() + xx, bdays)
        idx = PL.stationary_indices(len(xx), 1000, 20, np.random.default_rng(SEED))
        lead = PL.roc30((B.to_numpy() + xx)[idx], years) - PL.roc30(B.to_numpy()[idx], years)
        lead = lead[np.isfinite(lead)]
        p5 = float(np.percentile(lead, 5))
        print("  REPORT book #463 + %s at %-18s (x%.3f NQ): ROC@30k %.2f  Sortino %.3f  bootstrap p5 %+.1f (SD %.1f)" % (
            name, lab, s, bb["roc"], bb["sort"], p5, float(lead.std(ddof=1))))
        if out is None:
            out = bb["roc"] >= BAR_BOOK_ROC and bb["sort"] >= BAR_BOOK_SORT and p5 > 0
    return out


def standalone(st, pf, n, years, yrs, x, bdays, B, name):
    """House line #45 standalone bars: own ROC@30k >= 15 OR the earner route (>= 5 and positive in #463's worst WF
    drawdown, also without its 3 best days there); PF > 1; >= 100 trades and 50 a year; >= 6 of 9 years; no-2020 =
    the same ROC route still holds with calendar 2020 removed. Returns (a1, no2020)."""
    p0, p1 = worst_window(B)
    w = np.asarray((bdays > p0) & (bdays <= p1))
    ww = np.sort(x[w])
    dd_sum, dd_ex3 = float(ww.sum()), float(ww[:-3].sum()) if len(ww) > 3 else float("nan")
    earner = st["roc"] >= 5 and dd_sum > 0 and dd_ex3 > 0
    route = st["roc"] >= BAR_OWN
    k = np.asarray(bdays.year != 2020)
    s20 = own(x[k], bdays[k])
    no2020 = s20["net"] > 0 and s20["roc"] >= (BAR_OWN if route else 5.0)
    print("  %s in #463's worst WF drawdown (%s .. %s): $%s at 1 NQ, $%s without its 3 best days; without 2020: own "
          "ROC@30k %.2f, net $%s" % (name, p0.date(), p1.date(), format(int(dd_sum), ","), format(int(dd_ex3), ","),
                                     s20["roc"], format(int(s20["net"]), ",")))
    a1 = (route or earner) and pf > 1 and n >= 100 and n / years >= 50 and sum(v > 0 for v in yrs) >= 6
    return a1, no2020, ("ROC route" if route else ("earner route" if earner else "neither route"))


def book_positions(days):
    """(D, 78) side held at each RTH 5m bar by #463's NQ 5m legs (ORB #314 = ORB_3_6_C2 on the adjusted master, NOISE
    #422 = NOISE_1_8_CT304H on the no-adjust master), from their engine trades (entry bar .. exit bar). ENGU-Q (1m ETH)
    and TTM (ES) are not included. Cached."""
    import json
    import importlib.util as ilu
    from augur_engine.engine import run_backtest
    if os.path.exists(LEGCACHE):
        z = np.load(LEGCACHE, allow_pickle=True)
        cd = pd.DatetimeIndex(z["days"])
        out = {}
        for k in ("ORB", "NOISE"):
            X = np.zeros((len(days), 78))
            ii = cd.get_indexer(days)
            X[ii >= 0] = z[k][ii[ii >= 0]]
            out[k] = X
        return out
    legs = json.load(open(os.path.join(os.path.dirname(LEGCACHE), "..", "rocfrontier", "r4", "book463_legs.json")))
    res, alld = {}, None
    for key, pre in (("ORB", "ORB"), ("NOISE", "NOISE")):
        lg = [l for l in legs if l["strategy"].startswith(pre)][0]
        A = load_master_arrays(find_master("NQ", "5m", "rth", lg["source"]), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
        sp = ilu.spec_from_file_location("leg_" + key, os.path.join(ROOT, "augur_strategies", lg["strategy"]))
        m = ilu.module_from_spec(sp)
        sp.loader.exec_module(m)
        tr = run_backtest(m, arrays=A, params=lg["params"], cost_pts=lg["cost_pts"], return_trades=True)["trades"]
        ts = pd.DatetimeIndex(A["index"])
        kk = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
        dd = pd.DatetimeIndex(pd.Index(ts.date))
        alld = dd.unique() if alld is None else alld.union(dd.unique())
        res[key] = (tr, dd, kk)
    alld = pd.DatetimeIndex(sorted(alld))
    store = {"days": np.array(alld.astype("datetime64[ns]"))}
    for key, (tr, dd, kk) in res.items():
        X = np.zeros((len(alld), 78))
        di = alld.get_indexer(dd)
        for t in tr:
            e0, e1, side = int(t[0]), int(t[1]), float(np.sign(t[3]))
            if di[e0] != di[e1]:
                continue
            X[di[e0], max(kk[e0], 0):min(kk[e1], 77) + 1] = side
        store[key] = X
    os.makedirs(os.path.dirname(LEGCACHE), exist_ok=True)
    np.savez(LEGCACHE, **store)
    return book_positions(days)


def overlap(cand, legs):
    """Share of the candidate's held bars on which a #463 leg holds the SAME side (and the opposite side)."""
    held = cand != 0
    n = max(int(held.sum()), 1)
    parts = []
    either = np.zeros(cand.shape, bool)
    for k, X in legs.items():
        same = held & (np.sign(X) == np.sign(cand)) & (X != 0)
        opp = held & (np.sign(X) == -np.sign(cand)) & (X != 0)
        either |= same
        parts.append("%s same %.0f%% / opposite %.0f%%" % (k, 100 * same.sum() / n, 100 * opp.sum() / n))
    return "; ".join(parts) + "; same-side with either %.0f%% of its held bars" % (100 * either.sum() / n)


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
        print("POWER LINES (coin-flip directions on the primary's schedule: %d trades, %.0f a year; amendment 1)" % (
            int(on.sum()), on.sum() / years))
        power_lines(daily(P, days, bdays).to_numpy(), B, years)
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
        rows[(L, z)] = dict(x=x, st=st, n=n, pf=pf, yrs=yrs, P=P, on=on, S=S)
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
    # amendment 1 (3): mechanism check - the primary on the mid-day slots only (10:00 .. 15:30), and per slot
    mid = np.zeros(NSLOT, bool)
    mid[1:12] = True
    Pm = np.where(mid[None, :], pr["P"], 0.0)
    sm = own(daily(Pm, days, bdays).to_numpy(), bdays)
    print("  REPORT mid-day slots only (10:00-15:30): n %d  net $%s  own ROC@30k %.2f  (full 13: %.2f)" % (
        int(pr["on"][:, mid].sum()), format(int(sm["net"]), ","), sm["roc"], pr["st"]["roc"]))
    print("  REPORT per slot $ (09:30 .. 15:30 starts): %s" % ", ".join(
        "%s" % format(int(pr["P"][:, h].sum()), ",") for h in range(NSLOT)))
    # amendment 1 (2): overlap with #463's NQ 5m legs, on held bars
    side = np.where(pr["on"], np.sign(pr["S"]), 0.0)
    cand = np.zeros((len(days), 78))
    for h in range(NSLOT):
        cand[:, h * BARS:(h + 1) * BARS] = side[:, h:h + 1]
    print("  REPORT overlap with #463 legs on HALFHOUR's held bars: %s" % overlap(cand, book_positions(days)))

    shadow = book_report(pr["x"], B, years, "HALFHOUR")
    a1, no2020, route = standalone(pr["st"], pr["pf"], pr["n"], years, pr["yrs"], pr["x"], bdays, B, "HALFHOUR")
    a2 = pr["st"]["roc"] > q95
    a3 = all(rows[c]["st"]["net"] > 0 for c in CELLS[1:])
    print("")
    for lab, ok in (("A1 own ROC@30k >= 15 or earner route (%s), PF > 1, >= 100 and 50/yr, >= 6 of 9 years" % route, a1),
                    ("A1b no-2020: the same route holds without calendar 2020", no2020),
                    ("A2 primary above the wrong-slot family null's p95", a2),
                    ("A3 all three neighbours net positive after cost", a3)):
        print("  %-80s %s" % (lab, "PASS" if ok else "FAIL"))
    print("  A4 (REPORT, house line #45) vol-scale book add >= 98.50 / 3.816 with p5 > 0: %s -> %s" % (
        "yes" if shadow else "no", "forward BOOK shadow line too" if shadow else "standalone only"))
    print("")
    print("STAGE A: %s" % ("PASS -> pinned Auto-Validate the same day (HALFHOUR_1_0 plugin, parity first)"
                         if all((a1, no2020, a2, a3)) else "FAIL - recorded dead, no variants"))

if __name__ == "__main__":
    main(sys.argv[1:])
