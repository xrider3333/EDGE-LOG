# -*- coding: utf-8 -*-
"""NOISE ROUND 69 - power of the paired test, computed BEFORE the round from NOISE #422's own walk-forward series.

The 2.25x-minus-1.75x difference on the same trades is 0.5 x the net of each compressed-decision trade (0 otherwise),
valued by day. This prints ONLY its spread - the stationary block-bootstrap (20 trading days, 1,000 draws) standard
error of its annualised mean - and the minimum detectable walk-forward ROC-at-$30k difference (one-sided 5%, 80% power,
#422's walk-forward drawdown held fixed). It never prints the difference's mean or any 2.25x result.

  python tools/r69_noise_power.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402

BLOCK, DRAWS, SEED = 20, 1000, 20261004


def stationary_bootstrap_means(x, rng):
    n = len(x)
    out = np.empty(DRAWS)
    p = 1.0 / BLOCK
    for d in range(DRAWS):
        idx = np.empty(n, int)
        i = rng.integers(n)
        for t in range(n):
            if t > 0 and rng.random() < p:
                i = rng.integers(n)
            else:
                i = (i + 1) % n if t > 0 else i
            idx[t] = i
        out[d] = x[idx].mean()
    return out


if __name__ == "__main__":
    tr = R.trades(R.build())
    tf, ln, ratio, _ = R.LEGS[1][3]
    comp = R.SQ._compression(R.H, R.L, R.C, np.asarray(R.A["day_id"]), R.A["index"], tf, ln, ratio)
    k = np.array([int(x[0]) for x in tr])
    net = np.array([float(x[2]) for x in tr]) * R.M
    on = comp[k - 1].astype(bool)
    day = R.DATE[k - 1]
    wf = (day >= R.WF0) & (day < R.LB0)
    sessions = pd.Index(sorted(set(R.DATE[(R.DATE >= R.WF0) & (R.DATE < R.LB0)])))
    d = pd.Series(np.where(on, 0.5 * net, 0.0)[wf]).groupby(day[wf]).sum().reindex(sessions, fill_value=0.0).to_numpy()
    twin = R.stats(R.sized(tr, R.LEGS[1][3]), R.WF0, R.LB0)
    years = (pd.Timestamp(R.LB0) - pd.Timestamp(R.WF0)).days / 365.25
    se_daily = stationary_bootstrap_means(d - d.mean(), np.random.default_rng(SEED)).std()
    se_annual = se_daily * len(sessions) / years
    mdd = (1.645 + 0.842) * 30 * se_annual / twin["dd"]
    print("NOISE #422 walk-forward: %d sessions, %d trades, drawdown $%s (daily), ROC@30k %.1f" % (
        len(sessions), twin["n"], format(int(twin["dd"]), ","), twin["r30"]))
    print("paired difference (0.5 x compressed-trade net, by day): block-bootstrap SE of the annual mean $%s/yr"
          % format(int(se_annual), ","))
    print("MINIMUM DETECTABLE walk-forward ROC@30k difference (one-sided 5%%, 80%% power, drawdown fixed): %.1f points"
          % mdd)
