"""
NT3 SAFEHAVEN - intraday flight to quality on equity-stress days (IEF, GLD). STAGE A, walk-forward only.
Pre-registration: docs/PREREG_orb_newtypes_r1_2026-10-05.md (NT3). Run from the shared checkout:

    python tools/orb_nt3_safehaven.py

Trigger: ES move in POINTS from the prior session's 16:00 price (15:55-bar close) to 10:30 (10:25-bar close) <= -k x its
median |same window| over the previous 60 sessions (house ES 5-minute RTH master; MANAGER edit 2). Trade: long $100,000
of the fund at the 10:35 bar's OPEN - one bar after the 10:25 bar's close is read (MANAGER edit 1) - out at the 15:55
bar's close. k = 2 is the mechanism's test; k = 1 (about half of all sessions) is a dilution check that cannot pass
(MANAGER edit 7). Fund masters: GLD master_90ca117d.csv (sha256 8636706acc25d727...), IEF master_8715eb14.csv
(3d93b57cc83018cb...), Alpaca 5-minute RTH, split-adjusted, 2016-01-04..2026-06-30 (Alpaca 5-minute split-adjusted bars, stamped at the START, Eastern).
Cells: fund {IEF, GLD} x k {1, 2}. Cost 2 bp a side (stress 5 bp). Random-day family null (same count per year of random
non-trigger sessions, same trade). No fund bars before 2016: the 2010-16 check is not available (stated in the prereg).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orb_nt_common as C   # noqa: E402

NOTIONAL, BP, BP_STRESS = 100000.0, 2.0, 5.0


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.data import find_master, load_master_arrays

    book, cal = C.book463(), C.session_calendar()
    ddd = C.drawdown_days(book)
    print("#463 drawdown days: %d (TV counted 460)" % len(ddd))
    A = load_master_arrays(find_master("ES", "5m", "rth", "db_adj_rth"), date_from="2015-06-01", date_to=C.WF[1])
    idx = pd.DatetimeIndex(A["index"]).tz_localize(None)
    es = pd.Series(np.asarray(A["close"], float), index=idx)
    day = es.index.normalize()
    last = es.groupby(day).last()
    at1030 = es[es.index.strftime("%H:%M") == "10:25"]
    at1030.index = at1030.index.normalize()
    r = (at1030 - last.shift(1).reindex(at1030.index)).dropna()          # points
    med = r.abs().rolling(60, min_periods=60).median().shift(1)
    trade = {}
    for f in ("IEF", "GLD"):
        F = load_master_arrays(find_master(f, "5m", "rth", "alpaca_split_rth"), date_from="2016-01-01", date_to=C.WF[1])
        fi = pd.DatetimeIndex(F["index"]).tz_localize(None)
        fo = pd.Series(np.asarray(F["open"], float), index=fi)
        fc = pd.Series(np.asarray(F["close"], float), index=fi)
        en = fo[fo.index.strftime("%H:%M") == "10:35"]
        ex = fc[fc.index.strftime("%H:%M") == "15:55"]
        en.index, ex.index = en.index.normalize(), ex.index.normalize()
        both = en.index.intersection(ex.index)
        g = NOTIONAL * (ex[both] / en[both] - 1.0)
        trade[f] = pd.DataFrame({"date": both, "g": g.values})
        print("%s: %d sessions with both the 10:35 and 15:55 bars" % (f, len(both)))
    cells, pools = {}, {}
    for f in ("IEF", "GLD"):
        T = trade[f]
        for k in (1, 2):
            trig = set(r.index[(r <= -k * med.reindex(r.index)) & med.reindex(r.index).notna()])
            X = T[T.date.isin(trig)].copy()
            X["usd"] = X.g - 2 * BP / 1e4 * NOTIONAL
            X["usd_stress"] = X.g - 2 * BP_STRESS / 1e4 * NOTIONAL
            cells["%s k=%d" % (f, k)] = X.reset_index(drop=True)
            pools["%s k=%d" % (f, k)] = T[~T.date.isin(trig)].reset_index(drop=True)
    for name, X in cells.items():
        print("%s: %d trigger sessions in the fund data, %d in the WF" % (name, len(X),
              int(((X.date >= pd.Timestamp(C.WF[0])) & (X.date <= pd.Timestamp(C.WF[1]))).sum())))
    rng = np.random.default_rng(20261005)
    nulls = []
    for _ in range(C.N_NULL):
        ns = {}
        for name, X in cells.items():
            P = pools[name]
            pick = []
            for y, n in X.groupby(X.date.dt.year).size().items():
                cand = np.flatnonzero(P.date.dt.year.values == y)
                pick.extend(rng.choice(cand, size=min(n, len(cand)), replace=False))
            N = P.iloc[sorted(pick)]
            ns[name] = N.assign(usd=N.g - 2 * BP / 1e4 * NOTIONAL)
        nulls.append(ns)
    passes = C.evaluate(cells, nulls, book, cal, ddd, "NT3 SAFEHAVEN", report_only=("IEF k=1", "GLD k=1"))
    for name, X in cells.items():   # reported: the known enemies, named in the prereg
        for lab, (a, b) in (("2020 dash for cash", ("2020-03-09", "2020-03-18")), ("2022", ("2022-01-01", "2022-12-31"))):
            Y = X[(X.date >= pd.Timestamp(a)) & (X.date <= pd.Timestamp(b))]
            print("(reported) %s in %s: %d trades, $%.0f" % (name, lab, len(Y), Y.usd.sum()))
    print("\nNT3 verdict: %s" % ("PASS: %s" % ", ".join(passes) if passes else "DEAD at Stage A (0 of 4 cells)"))


if __name__ == "__main__":
    main()
