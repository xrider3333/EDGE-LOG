# -*- coding: utf-8 -*-
"""POWER LINE - the minimum detectable walk-forward lead, printed BEFORE any bootstrap bar is read (house rule,
MANAGER #37 / #39, 2026-10-05).

The house paired bar: resample the candidate's and its twin's DAILY P&L together with a stationary block bootstrap
(mean block 20 sessions, 1,000 draws) and require the 5th percentile of the ROC-at-$30k lead (candidate minus twin) to
be above zero. Whether a lead of a given size CAN clear that bar depends only on the spread of the bootstrapped lead,
not on the lead itself. This tool prints that spread and the two lines that follow from it, and NEVER prints the lead,
either ROC, or anything else that tells you which way the result went:

  5%% line      1.645 x SD   - a lead must be at least this big for its 5th percentile to clear zero (50% power)
  80%% line     2.487 x SD   - the lead it takes to clear the bar four times in five (one-sided 5%%, 80%% power)

ROC at $30k = 30 x (net / years) / worst drawdown, drawdown valued on the daily series (the house yardstick).

  python tools/power_line.py --cand CAND.csv --twin TWIN.csv [--from 2016-06-30 --to 2025-07-16]
         [--date-col date --pnl-col pnl_usd] [--block 20 --draws 1000 --seed 20261005]
  (CSV: one row per day, a date column and a P&L-in-dollars column; missing days count as $0)

  from power_line import power_line          # power_line(cand_daily, twin_daily, years, ...) -> dict
"""
import argparse
import sys

import numpy as np
import pandas as pd

Z5, Z80 = 1.645, 0.842


def stationary_indices(n, draws, block, rng):
    """(draws, n) resampling indices: each day starts a new block with probability 1/block, else continues the
    previous block (wrapping around the end). Politis-Romano stationary bootstrap."""
    if n < 1:
        raise ValueError("empty series")
    start = rng.random((draws, n)) < 1.0 / block
    start[:, 0] = True
    pos = rng.integers(0, n, size=(draws, n))
    ar = np.broadcast_to(np.arange(n), (draws, n))
    last = np.maximum.accumulate(np.where(start, ar, 0), axis=1)
    base = np.take_along_axis(pos, last, axis=1)
    return (base + (ar - last)) % n


def roc30(paths, years):
    """ROC at a $30k drawdown for each row of a (draws, n) array of daily P&L."""
    cum = np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.zeros((paths.shape[0], 1)), cum], axis=1), axis=1)[:, 1:]
    dd = (peak - cum).max(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dd > 0, 30.0 * (paths.sum(axis=1) / years) / dd, np.nan)


def power_line(cand, twin, years, block=20, draws=1000, seed=20261005):
    """Spread of the bootstrapped ROC@30k lead and the lines that follow. Never returns the lead itself."""
    cand = np.asarray(cand, float)
    twin = np.asarray(twin, float)
    if cand.shape != twin.shape:
        raise ValueError("candidate and twin must be aligned day by day")
    idx = stationary_indices(len(cand), draws, block, np.random.default_rng(seed))
    lead = roc30(cand[idx], years) - roc30(twin[idx], years)
    lead = lead[np.isfinite(lead)]
    sd = float(lead.std(ddof=1)) if len(lead) > 1 else 0.0
    return {"sd": sd, "line_5pct": Z5 * sd, "line_80pct": (Z5 + Z80) * sd, "draws": int(len(lead)),
            "days": int(len(cand)), "years": float(years), "block": block, "seed": seed}


def _load(path, date_col, pnl_col):
    d = pd.read_csv(path)
    return pd.Series(d[pnl_col].astype(float).to_numpy(), index=pd.to_datetime(d[date_col]).dt.normalize()) \
        .groupby(level=0).sum()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Minimum detectable WF ROC@$30k lead - printed before any bar is read")
    ap.add_argument("--cand", required=True)
    ap.add_argument("--twin", required=True)
    ap.add_argument("--from", dest="date_from", default=None)
    ap.add_argument("--to", dest="date_to", default=None)
    ap.add_argument("--date-col", default="date")
    ap.add_argument("--pnl-col", default="pnl_usd")
    ap.add_argument("--block", type=int, default=20)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261005)
    a = ap.parse_args(argv)
    c, t = _load(a.cand, a.date_col, a.pnl_col), _load(a.twin, a.date_col, a.pnl_col)
    days = c.index.union(t.index)
    if a.date_from:
        days = days[days >= pd.Timestamp(a.date_from)]
    if a.date_to:
        days = days[days <= pd.Timestamp(a.date_to)]
    if len(days) < 2:
        raise SystemExit("fewer than two days in the window")
    years = (days[-1] - days[0]).days / 365.25
    r = power_line(c.reindex(days, fill_value=0.0).to_numpy(), t.reindex(days, fill_value=0.0).to_numpy(), years,
                   a.block, a.draws, a.seed)
    print("POWER LINE (paired stationary block bootstrap, mean block %d, %d draws, seed %d; %d days, %.2f years)"
          % (r["block"], r["draws"], r["seed"], r["days"], r["years"]))
    print("  SD of the bootstrapped ROC@$30k lead: %.1f points" % r["sd"])
    print("  MINIMUM DETECTABLE lead for a 5th percentile above zero: %.1f points (50%% power)" % r["line_5pct"])
    print("  lead needed to clear the bar four times in five: %.1f points (80%% power)" % r["line_80pct"])
    print("  (the lead itself is not computed for display - write these lines into the pre-registration first)")
    return r


if __name__ == "__main__":
    main(sys.argv[1:])
