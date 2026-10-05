"""
NT1 MACRO830 - the 08:30 CPI / payroll futures reaction carried into the cash open (NQ, ES). STAGE A, walk-forward only.
Pre-registration: docs/PREREG_orb_newtypes_r1_2026-10-05.md (NT1). Run from the shared checkout:

    python tools/orb_nt1_macro830.py

m = close of the 08:34 bar - close of the 08:29 bar, in POINTS (MANAGER edit 2: shift-invariant on the roll-corrected
masters). CLOCK (edit 1): the 1-minute ETH masters are stamped at the bar START (loader doc: NOADJ/ADJ 1m ETH = epoch
seconds, bar START; checked on 2022-09-13, the CPI jump sits in the bar labelled 08:30, the 08:29 bar closes pre-release).
So the 08:34 bar is complete at 08:35:00, and entry at the 08:35 bar's open is strictly after the signal. Exit at the
close of the 09:59 bar. Cells: market x {every
release day; |m| >= median |m| of the previous 24 release days}. Coin-flip side null; the fade mirror is reported.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orb_nt_common as C   # noqa: E402  (sets ROOT, cwd, env)

MKT = {"NQ": (20.0, 0.533), "ES": (50.0, 0.363)}
STRESS = 0.25


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.data import find_master, load_master_arrays

    days = sorted(set(pd.read_csv("tools/data/cpi_dates.csv", comment="#").date)
                  | set(pd.read_csv("tools/data/nfp_dates.csv", comment="#").date))
    days = [pd.Timestamp(d) for d in days if "2010-06-07" <= d <= C.WF[1]]
    book, cal = C.book463(), C.session_calendar()
    ddd = C.drawdown_days(book)
    print("#463 drawdown days (>= $%.0f episodes): %d (TV counted 460)" % (C.DD_DEPTH, len(ddd)))
    rows = {}
    for mk, (mult, cost) in MKT.items():
        A = load_master_arrays(find_master(mk, "1m", "eth", "db_adj_eth"), date_from="2010-06-01", date_to=C.WF[1])
        idx = pd.DatetimeIndex(A["index"])
        o = pd.Series(np.asarray(A["open"], float), index=idx)
        c = pd.Series(np.asarray(A["close"], float), index=idx)
        out, skipped = [], 0
        for d in days:
            ts = lambda hm: pd.Timestamp("%s %s" % (d.date(), hm), tz=idx.tz)
            try:
                c0, c1, en, ex = c[ts("08:29")], c[ts("08:34")], o[ts("08:35")], c[ts("09:59")]
            except KeyError:
                skipped += 1
                continue
            m = c1 - c0                                  # points
            if m == 0:
                skipped += 1
                continue
            g = (ex - en) * mult
            side = 1.0 if m > 0 else -1.0
            out.append(dict(date=d, m=m, g=g, side=side, usd=side * g - cost * mult,
                            usd_stress=side * g - (cost + STRESS) * mult, cost=cost * mult))
        T = pd.DataFrame(out).sort_values("date").reset_index(drop=True)
        med = T.m.abs().rolling(24, min_periods=24).median().shift(1)
        T["big"] = T.m.abs() >= med
        print("%s: %d release days traded, %d skipped (missing bars or zero move)" % (mk, len(T), skipped))
        rows[mk] = T
    cells = {"%s every day" % mk: rows[mk] for mk in MKT}
    cells.update({"%s big move" % mk: rows[mk][rows[mk].big] for mk in MKT})
    rng = np.random.default_rng(20261005)
    nulls = []
    for _ in range(C.N_NULL):
        ns = {}
        for mk in MKT:
            T = rows[mk]
            s = rng.choice([-1.0, 1.0], size=len(T))
            N = T.assign(usd=s * T.g - T.cost)
            ns["%s every day" % mk] = N
            ns["%s big move" % mk] = N[T.big.values]
        nulls.append(ns)
    passes = C.evaluate(cells, nulls, book, cal, ddd, "NT1 MACRO830")
    for mk in MKT:   # reported: the fade mirror (control)
        T = rows[mk]
        W = T[(T.date >= pd.Timestamp(C.WF[0])) & (T.date <= pd.Timestamp(C.WF[1]))]
        f = -W.side * W.g - W.cost
        print("(reported) %s FADE mirror: WF net $%.0f, mean $%.0f, t %.2f" % (mk, f.sum(), f.mean(), C.tstat(f)))
    print("\nNT1 verdict: %s" % ("PASS: %s" % ", ".join(passes) if passes else "DEAD at Stage A (0 of 4 cells)"))


if __name__ == "__main__":
    main()
