# -*- coding: utf-8 -*-
"""NOISE round 69c - NOISE #422 on the roll-corrected ADJ_ master vs the no-adjust master, WALK-FORWARD ONLY.

MANAGER #30 (reported, not judged): #422 is the only BOOK #463 leg still on NOADJ_NQ_5m_RTH; the other three run on
ADJ_ (back-adjusted). Same strategy file and settings on both tapes (to 2026-09-16, cost 0.533, $20/pt); compare the
walk-forward trades by fill time: count, net, and whether the differences sit at contract switches (rolls_NQ.csv).
Rule from MANAGER: both differences under 1% -> 'book reference unaffected'; more -> post the figures.

  python tools/r69c_noise_422_adj_vs_noadj.py  -> tools/r37_results/r69c_adj_vs_noadj.txt
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

P422 = dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75)


def run(src):
    A = load_master_arrays(find_master("NQ", "5m", "rth", src), date_from="2010-06-07", date_to=R.LAST)
    idx = pd.DatetimeIndex(A["index"]).tz_convert("America/New_York")
    tr = run_backtest(R.load("NOISE_1_8_CT304H.py"), arrays=A, params=P422, cost_pts=R.COST, return_trades=True)["trades"]
    rows = []
    for t in tr:
        sig_day = idx[int(t[0]) - 1].date()
        if R.WF0 <= sig_day < R.LB0:
            rows.append(dict(fill=idx[int(t[0])], exit=idx[int(t[1])], side=int(np.sign(t[3])), usd=float(t[2]) * R.M,
                             day=sig_day))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    a, b = run("db_noadj_rth"), run("db_adj_rth")
    na, nb = len(a), len(b)
    print("NOISE #422 walk-forward %s .. %s, NO-ADJUST vs ADJ_ (back-adjusted) master" % (R.WF0, R.LB0))
    print("  no-adjust : %d trades, net $%s" % (na, format(int(a.usd.sum()), ",")))
    print("  ADJ_      : %d trades, net $%s" % (nb, format(int(b.usd.sum()), ",")))
    print("  difference: %+d trades (%+.2f%%), net %+.2f%%" % (nb - na, 100.0 * (nb - na) / na,
                                                          100.0 * (b.usd.sum() - a.usd.sum()) / a.usd.sum()))
    m = a.merge(b, on=["fill", "side"], how="outer", suffixes=("_n", "_a"), indicator=True)
    both = m[m._merge == "both"]
    same_exit = (both.exit_n == both.exit_a)
    print("  matched by fill time and side: %d; same exit %d; only no-adjust %d; only ADJ_ %d" % (
        len(both), int(same_exit.sum()), int((m._merge == "left_only").sum()), int((m._merge == "right_only").sum())))
    print("  matched trades: $ difference total %+.0f (same-exit trades %+.0f)" % (
        (both.usd_a - both.usd_n).sum(), (both.usd_a - both.usd_n)[same_exit].sum()))
    rolls = pd.read_csv(os.path.join(R.ROOT, "tools", "data", "rolls_NQ.csv"))
    rd = pd.to_datetime(rolls.switch_et).dt.date
    roll_days = set()
    for d in rd:
        for k in range(-3, 4):
            roll_days.add(d + pd.Timedelta(days=k))
    diff = m[(m._merge != "both") | ((m._merge == "both") & ((m.exit_n != m.exit_a) | ((m.usd_a - m.usd_n).abs() > 0.5)))]
    dday = diff.day_n.fillna(diff.day_a)
    near = dday.map(lambda d: d in roll_days)
    print("  differing trades: %d, of which within 3 days of a contract switch: %d" % (len(diff), int(near.sum())))
    s1 = R.stats([(0, 0)], R.WF0, R.LB0) if False else None
    print("  verdict rule: both differences under 1%% -> book reference unaffected: %s" % (
        "UNAFFECTED" if abs(nb - na) / na < 0.01 and abs(b.usd.sum() - a.usd.sum()) / abs(a.usd.sum()) < 0.01
        else "OVER 1% - figures to MANAGER"))
