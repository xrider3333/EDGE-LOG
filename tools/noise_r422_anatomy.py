# -*- coding: utf-8 -*-
"""NOISE #422 ANATOMY - which mechanism, not which size (docs/PREREG_noise_r422_anatomy_2026-10-06.md; MANAGER #63 /
#64, scope rank 1). REPORT ONLY: no rule is mined, nothing changes on NQ.

#422 = NOISE_1_8_CT304H (60-minute compression gate 20 / 1.15, 1.75x) on the NQ 5m RTH no-adjust master. Every trade is
tagged at its SIGNAL bar (the bar whose close decided the entry = the fill bar - 1), never the fill bar. Walk-forward
stretch only: signal date 2016-07-01 .. 2025-06-29 (the book's WF). Dollars at 1 NQ: UNIT = the #304 core trade (size
divided out), SIZED = #422 as traded. Halves on every table: H1 2016-07 .. 2021-12, H2 2022-01 .. 2025-06.

  B1 hour        signal bar closing 09:40-10:25 / 10:30-13:55 / 14:00-15:55
  B2 exit path   exit kind (VWAP exit at the next open / stop inside the bar / end of day) - descriptive of outcomes;
                 holding time; the best and worst point in NQ points; ROOM TO PAY (MANAGER #63): the gap between the
                 signal close and the session VWAP at that close, in % of price, by terciles
  B3 day type    open gap size; ex-post day shape (close location; DESCRIPTIVE ONLY, not knowable at entry); FOMC / CPI
                 / NFP days; prior-day range percentile vs 252 sessions (terciles); the 60-minute squeeze on / off
  B4 side        long / short x prior close above / below its 200-session average; 2022 alone
  B5 order       first break of the session / second / third or later

NULLS (the power line of a report): an intraday tag is shuffled among the trades of the SAME session (keeps every day
effect); a day-level tag is shuffled among the sessions of the SAME year (keeps every year effect). 1,000 draws. Each
bucket's null 5-95% band of UNIT $/trade is printed in --power mode BEFORE any real bucket is read, and beside it after.

  python tools/noise_r422_anatomy.py --power     null bands only (no real bucket number)
  python tools/noise_r422_anatomy.py             the tables
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

W0, W1, H2 = pd.Timestamp("2016-07-01").date(), pd.Timestamp("2025-06-29").date(), pd.Timestamp("2022-01-01").date()
DRAWS, SEED = 1000, 20261006
DATA = os.path.join(R.ROOT, "tools", "data")


def dates_from(fn, col="date"):
    p = os.path.join(DATA, fn)
    if fn.endswith(".txt"):
        return {pd.Timestamp(l.strip()).date() for l in open(p) if l.strip() and not l.startswith("#")}
    d = pd.read_csv(p, comment="#")
    return {pd.Timestamp(x).date() for x in d[col]}


def build():
    A = R.A
    O, Hh, Lw, C = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    V = np.asarray(A["volume"], float)
    idx = R.IDX
    day = np.asarray(A["day_id"])
    ct = R.load("NOISE_1_8_CT304H.py")
    tr = sorted(run_backtest(ct, arrays=A, params=dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75),
                             cost_pts=R.COST, return_trades=True)["trades"], key=lambda t: int(t[0]))
    comp = R.SQ._compression(R.H, R.L, R.C, day, A["index"], 60, 20, 1.15).astype(bool)
    # session frame
    starts = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
    ends = np.r_[starts[1:], len(day)]
    sdate = np.array([idx[s].date() for s in starts])
    s_of = np.repeat(np.arange(len(starts)), ends - starts)
    tp = (Hh + Lw + C) / 3.0
    vw = np.empty(len(C))
    for a, b in zip(starts, ends):
        cv = np.cumsum(V[a:b])
        with np.errstate(invalid="ignore", divide="ignore"):
            vw[a:b] = np.cumsum(tp[a:b] * V[a:b]) / cv
    dO, dC = O[starts], C[ends - 1]
    dH = np.array([Hh[a:b].max() for a, b in zip(starts, ends)])
    dL = np.array([Lw[a:b].min() for a, b in zip(starts, ends)])
    prevC = np.r_[np.nan, dC[:-1]]
    rng = (dH - dL) / dC
    prev_rng = np.r_[np.nan, rng[:-1]]
    pct = pd.Series(prev_rng).rolling(253, min_periods=253).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True).to_numpy()
    sma200 = pd.Series(dC).rolling(200).mean().shift(1).to_numpy()
    clv = (dC - dL) / np.where(dH > dL, dH - dL, np.nan)
    fomc, cpi, nfp = dates_from("fomc_dates.txt"), dates_from("cpi_dates.csv"), dates_from("nfp_dates.csv")
    rows = []
    order = {}
    for t in tr:
        k0, k1, pnl, side = int(t[0]), int(t[1]), float(t[2]), float(np.sign(t[3]))
        ks = k0 - 1                                                    # the SIGNAL bar
        d = idx[ks].date()
        if not (W0 <= d <= W1):
            continue
        s = 1.75 if comp[ks] else 1.0
        unit = pnl / s
        epx = float(t[4]) if len(t) > 4 else float(O[k0])
        xpx = epx + side * (unit + R.COST)
        si = s_of[ks]
        last = k1 == ends[si] - 1
        kind = ("eod" if last and abs(xpx - C[k1]) < 1e-6 else
                "vwap_next_open" if abs(xpx - O[k1]) < 1e-6 else "stop_in_bar")
        seg = slice(k0, k1 + 1)
        mfe = float(np.max((Hh[seg] - epx) if side > 0 else (epx - Lw[seg])))
        mae = float(np.max((epx - Lw[seg]) if side > 0 else (Hh[seg] - epx)))
        order[si] = order.get(si, 0) + 1
        hm = idx[ks].hour * 60 + idx[ks].minute + 5                     # the signal bar's CLOSE, minutes after midnight
        rows.append(dict(
            date=d, half="H1" if d < H2 else "H2", year=d.year, session=si, side="long" if side > 0 else "short",
            unit=unit * R.M, sized=pnl * R.M, size=s,
            B1_hour="a 09:40-10:25" if hm < 630 else ("b 10:30-13:55" if hm < 840 else "c 14:00-15:55"),
            B2_exit=kind, B2_hold="a <=3 bars" if k1 - k0 <= 3 else ("b 4-12 bars" if k1 - k0 <= 12 else "c >12 bars"),
            mfe=mfe, mae=mae, room=abs(C[ks] - vw[ks]) / C[ks] * 1e4,
            B3_gap=abs(dO[si] / prevC[si] - 1) * 100 if prevC[si] == prevC[si] else np.nan,
            B3_shape="trend up" if clv[si] >= 0.8 else ("trend down" if clv[si] <= 0.2 else "range"),
            B3_event="FOMC" if d in fomc else ("CPI" if d in cpi else ("NFP" if d in nfp else "none")),
            B3_volpct=pct[si], B3_squeeze="on" if comp[ks] else "off",
            B4_state=("long" if side > 0 else "short") + (" / above 200" if dC[si - 1] > sma200[si] else " / below 200")
            if si > 0 and sma200[si] == sma200[si] else "n/a",
            B5_order=order[si]))
    T = pd.DataFrame(rows)
    T["B2_room"] = pd.qcut(T.room, 3, labels=["a near VWAP", "b middle", "c far from VWAP"]).astype(str)
    T["B3_gap"] = pd.cut(T.B3_gap, [-1, 0.25, 0.75, 100], labels=["a <0.25%", "b 0.25-0.75%", "c >=0.75%"]).astype(str)
    T["B3_volpct"] = pd.cut(T.B3_volpct, [-1, 1 / 3, 2 / 3, 2], labels=["a low", "b mid", "c high"]).astype(str)
    T["B5_order"] = T.B5_order.clip(upper=3).map({1: "a first", 2: "b second", 3: "c third+"})
    T["B4_2022"] = np.where(T.year == 2022, "2022", "other years")
    return T


INTRADAY = ("B1_hour", "B2_room", "B3_squeeze", "B5_order")
DAYLEVEL = ("B3_gap", "B3_shape", "B3_event", "B3_volpct", "B4_state")
NO_NULL = ("B4_2022",)                                               # a year split: no within-year null exists
DESCRIPTIVE = ("B2_exit", "B2_hold")                                  # outcomes, no null


def null_bands(T, col):
    """5-95% band of each bucket's UNIT $/trade with the tag shuffled within session (intraday) or within year (day)."""
    rng = np.random.default_rng(SEED)
    lab = T[col].to_numpy()
    u = T.unit.to_numpy()
    cats = sorted(set(lab))
    out = {c: [] for c in cats}
    if col in INTRADAY:
        grp = T.session.to_numpy()
        for _ in range(DRAWS):
            o = np.lexsort((rng.random(len(T)), grp))                  # a random order inside each session
            perm = np.empty(len(T), int)
            perm[np.argsort(grp, kind="stable")] = o
            pl = lab[perm]
            for c in cats:
                m = pl == c
                out[c].append(u[m].mean() if m.any() else np.nan)
    else:
        days = T.drop_duplicates("session")[["session", "year", col]]
        for _ in range(DRAWS):
            dd = days.assign(r=rng.random(len(days))).sort_values(["year", "r"])
            orig = days.sort_values(["year", "session"])
            mp = dict(zip(orig.session.to_numpy(), dd[col].to_numpy()))
            pl = T.session.map(mp).to_numpy()
            for c in cats:
                m = pl == c
                out[c].append(u[m].mean() if m.any() else np.nan)
    return {c: (np.nanpercentile(v, 5), np.nanpercentile(v, 95)) for c, v in out.items()}


def table(T, col, bands=None):
    tot = T.unit.sum()
    print("\n%s" % col)
    print("  %-22s %5s %10s %8s %6s %7s %10s | %-24s | %-24s | %s" % (
        "bucket", "n", "unit $", "$/trade", "PF", "share", "sized $", "H1 n / $/trade / PF", "H2 n / $/trade / PF",
        "null 5-95% $/trade"))
    for c, g in T.groupby(col):
        pf = g.unit[g.unit > 0].sum() / -g.unit[g.unit < 0].sum() if (g.unit < 0).any() else np.inf
        hs = []
        for h in ("H1", "H2"):
            x = g[g.half == h].unit
            hpf = x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.inf
            hs.append("%4d / %6.0f / %4.2f" % (len(x), x.mean() if len(x) else np.nan, hpf))
        b = bands.get(c) if bands else None
        print("  %-22s %5d %10s %8.0f %6.2f %6.1f%% %10s | %-24s | %-24s | %s" % (
            c, len(g), format(int(g.unit.sum()), ","), g.unit.mean(), pf, 100 * g.unit.sum() / tot,
            format(int(g.sized.sum()), ","), hs[0], hs[1], "" if b is None else "%.0f .. %.0f" % b))


def main(argv):
    T = build()
    print("NOISE #422 anatomy - %d WF trades (signal date %s .. %s), unit $ %s, sized $ %s" % (
        len(T), T.date.min(), T.date.max(), format(int(T.unit.sum()), ","), format(int(T.sized.sum()), ",")))
    assert len(T) > 2500, "trade count far from #422's WF 2,805 - abort"
    bands = {c: null_bands(T, c) for c in INTRADAY + DAYLEVEL}
    if "--power" in argv:
        print("POWER LINE (null bands only - no real bucket number is computed in this mode):")
        for c in INTRADAY + DAYLEVEL:
            print("  %-12s %s" % (c, "; ".join("%s %.0f .. %.0f" % (k, a, b) for k, (a, b) in sorted(bands[c].items()))))
        return
    for c in ("B1_hour", "B2_exit", "B2_hold", "B2_room", "B3_gap", "B3_shape", "B3_event", "B3_volpct", "B3_squeeze",
              "B4_state", "B4_2022", "B5_order"):
        table(T, c, bands.get(c))
    print("\nB2 best / worst point (NQ points, medians): winners MFE %.1f MAE %.1f | losers MFE %.1f MAE %.1f" % (
        T[T.unit > 0].mfe.median(), T[T.unit > 0].mae.median(), T[T.unit <= 0].mfe.median(), T[T.unit <= 0].mae.median()))


if __name__ == "__main__":
    main(sys.argv[1:])
