"""TWO HORIZONS OF THE SAME EDGE: DOES RUNNING BOTH BEAT RUNNING EITHER?

Everything so far has treated the hold cap as a REPLACEMENT for the uncapped crown - one or
the other. But they are the same entry with two different exit horizons, and the audit says
they fail in different places: the uncapped crown keeps 56% of its profit in ten trades and
correlates +0.51 with the index's own year, while the capped version spreads the profit
(44%) and correlates less (+0.38) but gives up about 8% of the money and some profit factor.

That is the shape of two legs that might pool well rather than compete, so this tests it
directly: one contract of each, side by side, no leg selection and no weighting cleverness
(1:1, the house convention for a book). The interesting question is not whether the pooled
net is bigger - of course two contracts make more than one - but whether the pooled book is
better per unit of RISK and less tail-dependent than either leg alone.

WHAT IS MEASURED, all on the pooled daily series so the two legs' overlapping holds are
handled honestly rather than by adding leg statistics together:
  * annualised MAR on the pooled equity (the drawdown-aware read that decides here)
  * top-10 concentration and the yearly correlation with the index, on the pooled series
  * the two index down years, and positive years out of the window
  * the correlation between the two legs' own DAILY P&L - if it is near 1.0 the second leg
    is buying nothing but leverage, which is the trap this test exists to catch

PRE-REGISTERED, written before running. The book is worth queueing only if:
  1. pooled MAR  >  the better leg's MAR              (it must beat, not merely average)
  2. pooled top-10 share  < 50%                       (between the two legs, nearer the cap's)
  3. pooled yearly correlation with the index  < 0.45 (better than the uncapped leg's +0.51)
  4. both index down years positive on the pooled series
  5. daily leg-to-leg correlation  < 0.90             (or the second leg is just leverage)
If it clears all five it gets an Auto-Validate as a BOOK job. If it does not, it is written
down as measured and nothing is queued.

RESULT, 2026-09-09 - 4 of 5, so NOTHING WAS QUEUED. The one it misses is the one that decides.

    uncapped crown (R2)        net $613,126  DD $39,200  MAR 0.97  top-10 55.6%  corr +0.48
    capped crown (R3, 8280)    net $565,913  DD $40,548  MAR 0.87  top-10 43.8%  corr +0.39
    BOOK 1:1 (both horizons)   net $1,179,039 DD $77,374 MAR 0.95  top-10 36.2%  corr +0.45
    daily leg-to-leg correlation +0.407; 2018 +$24,111, 2022 +$7,966, 17/17 positive years

The diversification is REAL and it is not leverage: the legs share only +0.41 of their daily
P&L, and pooling gives the lowest concentration measured anywhere on this family (36.2%,
against 43.8% capped and 55.6% uncapped) while staying positive in both index down years.
What it does NOT give is risk-adjusted improvement - MAR 0.95 against the better leg's 0.97.
Net doubles, but so does drawdown ($39,200 -> $77,374, a 1.97x on a +0.41 correlation), so
the second contract buys size and a smoother profit distribution, not a better edge per unit
of risk. Bar 1 was written to require BEATING the better leg precisely so a tie could not be
talked into a promotion; 0.95 < 0.97, so nothing is queued. Recorded as a NEAR MISS: if a
future session wants this book, the honest argument is concentration, not MAR, and that is an
owner call about what the book is for.

A BUG WORTH KEEPING (caught by a sanity check, not by the code): the first run of this driver
pooled the legs with `sum(legs.values())`. Adding pandas Series on different day indexes
yields NaN on every day only ONE leg traded, and those days then collapsed to zero - deleting
about two thirds of the book's P&L and inventing a $105,645 drawdown. It reported net $374,374
(less than either leg alone, which is arithmetically impossible for two profitable legs) and a
convincing all-FAIL verdict. Always check the pooled net equals the sum of the legs' nets
before reading anything else off a pooled series.

NOTE ON STAMPING: this driver books a trade on its EXIT day, because that is the only stamping
under which two legs with different hold lengths can be summed day by day. Reads here will
differ slightly from entry-stamped ones elsewhere in the project (R2's index correlation reads
+0.48 here vs +0.51 entry-stamped, 2018 $9,403 vs $12,392) - same trades, different day.
"""
import io
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
LB_FROM = pd.Timestamp("2025-06-30")
MULT, COST = 20.0, 0.533
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"

CROWN = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
             breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
             min_brk=1.6, vol_mult=1.1, er_th=0.0)
LEGS = [("uncapped crown (R2)", 0), ("capped crown (R3, 8280)", 8280)]


def daily_and_trades(cap, arr, idx):
    r = run_backtest(STRAT, arrays=arr, params=dict(CROWN, max_hold_bars=cap),
                     cost_pts=COST, return_trades=True)
    tr = (r or {}).get("trades") or []
    # a trade is booked on its EXIT day: that is when the money is actually realised, and it
    # is the only stamping under which two legs with different hold lengths can be summed.
    ex = pd.DatetimeIndex([idx[int(t[1])] for t in tr]).normalize()
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
    pnl = np.array([t[2] * MULT for t in tr], float)
    daily = pd.Series(pnl, index=ex).groupby(level=0).sum()
    return daily, pnl, ent


def read(daily, bench, years, label):
    eq = daily.cumsum()
    dd = float((eq.cummax() - eq).max())
    d = daily.values
    yr = daily.groupby(daily.index.year).sum()
    common = yr.index.intersection(bench.index)
    gross_w = float(d[d > 0].sum())
    gross_l = float(-d[d < 0].sum())
    return dict(label=label, net=float(d.sum()), dd=dd,
                mar=(float(d.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                pf_daily=gross_w / max(gross_l, 1e-9),
                corr=float(yr[common].corr(bench[common])),
                y2018=float(yr.get(2018, 0.0)), y2022=float(yr.get(2022, 0.0)),
                pos_years=int((yr > 0).sum()), n_years=int(len(yr)))


def main():
    arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(arr["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    years = (idx[-1] - idx[0]).days / 365.25
    last = pd.Series(np.asarray(arr["close"], float), index=idx).resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    legs, trades = {}, {}
    for label, cap in LEGS:
        daily, pnl, ent = daily_and_trades(cap, arr, idx)
        legs[label] = daily
        trades[label] = (pnl, ent)
        print("  built %-26s %d trades, %d trading days" % (label, len(pnl), len(daily)),
              flush=True)

    # NOT sum(legs.values()): adding Series on different day indexes yields NaN on every day
    # only ONE leg traded, and those days then collapse to zero -- which silently deletes most
    # of the book's P&L (measured: $374,374 instead of $1,179,039 the first time this ran).
    pooled = pd.concat(legs.values(), axis=1).fillna(0.0).sum(axis=1).sort_index()

    rows = [read(legs[l], bench, years, l) for l, _ in LEGS]
    rows.append(read(pooled, bench, years, "BOOK 1:1 (both horizons)"))

    # concentration: on trades for the legs, on trading DAYS for the pooled series (a pooled
    # "trade" does not exist - the two legs overlap - so the day is the honest unit here)
    conc = {}
    for l, _ in LEGS:
        p = trades[l][0]
        conc[l] = float(np.sort(p)[::-1][:10].sum() / p.sum())
    pv = pooled.values
    conc["BOOK 1:1 (both horizons)"] = float(np.sort(pv)[::-1][:10].sum() / pv.sum())

    print("\n  %-26s %11s %10s %6s %6s %6s %9s %9s %6s"
          % ("", "net $", "maxDD $", "MAR", "top10", "corr", "2018", "2022", "yrs+"))
    for r in rows:
        print("  %-26s %11s %10s %6.2f %5.1f%% %+6.2f %9s %9s %3d/%d"
              % (r["label"], format(r["net"], ",.0f"), format(r["dd"], ",.0f"), r["mar"],
                 conc[r["label"]] * 100, r["corr"], format(r["y2018"], ",.0f"),
                 format(r["y2022"], ",.0f"), r["pos_years"], r["n_years"]), flush=True)

    a, b = legs[LEGS[0][0]], legs[LEGS[1][0]]
    both = pd.concat([a, b], axis=1).fillna(0.0)
    leg_corr = float(both.iloc[:, 0].corr(both.iloc[:, 1]))
    print("\n  daily leg-to-leg correlation: %+.3f  (near +1.0 = the second leg is only "
          "leverage)" % leg_corr)

    book = rows[-1]
    best_leg_mar = max(rows[0]["mar"], rows[1]["mar"])
    checks = [
        ("pooled MAR beats the better leg (%.2f)" % best_leg_mar, book["mar"] > best_leg_mar,
         "%.2f" % book["mar"]),
        ("pooled top-10 share < 50%", conc[book["label"]] < 0.50,
         "%.1f%%" % (conc[book["label"]] * 100)),
        ("pooled index correlation < 0.45", book["corr"] < 0.45, "%+.2f" % book["corr"]),
        ("both index down years positive", book["y2018"] > 0 and book["y2022"] > 0,
         "%.0f / %.0f" % (book["y2018"], book["y2022"])),
        ("leg-to-leg daily correlation < 0.90", leg_corr < 0.90, "%+.2f" % leg_corr)]
    print("\nPRE-REGISTERED VERDICT:")
    for label, ok, val in checks:
        print("   %-42s %-10s %s" % (label, val, "PASS" if ok else "FAIL"))
    ok_all = all(o for _, o, _ in checks)
    print("\n%s" % ("BOOK CLEARS EVERY BAR -- queue it as a BOOK Auto-Validate."
                    if ok_all else
                    "BOOK DOES NOT CLEAR -- write it down as measured, queue nothing."))
    json.dump(dict(rows=rows, conc=conc, leg_corr=leg_corr, cleared=ok_all),
              io.open(os.path.join(SCR, "_two_horizon.json"), "w"), indent=1, default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
