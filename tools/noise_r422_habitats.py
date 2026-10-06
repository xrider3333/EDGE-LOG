# -*- coding: utf-8 -*-
"""NOISE #422 anatomy (docs/PREREG_noise_r422_anatomy_2026-10-06.md) - the habitat list, written AFTER the tables.

The anatomy names the mechanism: one break a day held to the close on a trend day. This prints, for NQ and every
gated habitat in the scope queue, how often the day has that shape and what the cost is against the day's range.
It reads PRICE BARS ONLY: no NOISE trade is run on any fund, so it is not a result for any habitat prereg.

Per symbol, 5m RTH sessions 2016-07-01 .. 2025-06-29 (the book's walk-forward; nothing from the lockbox):
  trend-day share   close location (C - L) / (H - L) >= 0.8 or <= 0.2 (the anatomy's B3 shape, same cut)
  median range      (H - L) / C in bps
  cost              NQ: the engine's round-trip cost in points over the median close; funds: $0.02 a share round trip
                    over the median split-adjusted close (TRANSFER r2's cost), in bps
  cost / range      the cost as a share of the median day range

  python tools/noise_r422_habitats.py
"""
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("EDGELOG_ROCFRONTIER_R8", r"C:\EdgeLog\_anatomy_cache\noise_funds_r1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
import r8_transfer_etf as R8                                           # noqa: E402

W0, W1 = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")
FUNDS = ("IWM", "QQQ", "SPY", "DIA", "XLF", "XLU", "XLV", "XLP", "XLI", "XLY", "XLK", "TLT", "GLD")


def days(a):
    idx = pd.DatetimeIndex(a["index"])
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    f = pd.DataFrame({"h": np.asarray(a["high"], float), "l": np.asarray(a["low"], float),
                      "c": np.asarray(a["close"], float)}, index=idx)
    d = f.groupby(f.index.normalize()).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    return d[(d.index >= W0) & (d.index <= W1)]


def row(sym, d, cost_bps):
    clv = (d.c - d.l) / (d.h - d.l).where(d.h > d.l)
    trend = ((clv >= 0.8) | (clv <= 0.2)).mean()
    rng = float(np.median(1e4 * (d.h - d.l) / d.c))
    print("  %-4s sessions %4d  trend days %5.1f%% (up %4.1f%% / down %4.1f%%)  median range %5.1f bps  cost %4.2f bps"
          "  cost / range %5.2f%%" % (sym, len(d), 100 * trend, 100 * (clv >= 0.8).mean(), 100 * (clv <= 0.2).mean(),
                                      rng, cost_bps, 100 * cost_bps / rng))


def main():
    print("NOISE #422 habitats - day shape and cost vs range, 5m RTH, sessions 2016-07-01 .. 2025-06-29 (price bars only)")
    d = days(R.A)
    row("NQ", d, 1e4 * R.COST / float(np.median(d.c)))
    for f in FUNDS:
        try:
            d = days(R8.load(f, "5m", R8.PRE))
        except SystemExit as e:
            print("  %-4s not loaded: %s" % (f, e))
            continue
        row(f, d, 1e4 * R8.COST / float(np.median(d.c)))


if __name__ == "__main__":
    main()
