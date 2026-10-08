# -*- coding: utf-8 -*-
"""NOISE on IWM r1 - POST-VERDICT REPORT (the Stage A verdict, FAIL, was printed first and is not touched).

MANAGER #67 (2026-10-06 06:15) asked for the #422 anatomy's day-structure check in the IWM read: the share of trades and
of dollars in single-trade sessions (NQ: 28.6% / 97.4%). The frozen harness did not print it, and the lane missed the ask
before the 2026-10-07 18:01 launch. This prints it on the registered crown cell, plus the crown's trade count inside
#463's worst WF drawdown (the harness printed $0 there), and the crown's DD5 (MANAGER #70, 2026-10-07: every ROC
@ $30k is reported with DD5 beside it).

  python tools/noise_iwm_r1_daystructure.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import noise_iwm_r1_stageA as M                                       # noqa: E402
from augur_engine.drawdowns import dd5                                # noqa: E402

CROWN = (20, 1.0, 1.0, 1.75)                                          # printed by Stage A: lookback 20 / long 1.00 / short 1.00 / stop 1.75


def split(df, label):
    sess = pd.DatetimeIndex(df["entry"]).normalize()
    k = pd.Series(sess).map(pd.Series(sess).value_counts()).to_numpy()
    one = k == 1
    pnl = df.pnl.to_numpy()
    print("  %s: %d trades in %d sessions; single-trade sessions %d (%.1f%% of trades) net $%s; multi-break sessions %d "
          "trades net $%s (first breaks $%s, later breaks $%s)" % (
              label, len(df), len(set(sess)), int(one.sum()), 100 * one.mean(), format(int(pnl[one].sum()), ","),
              int((~one).sum()), format(int(pnl[~one].sum()), ","),
              format(int(pnl[~one & ~pd.Series(sess).duplicated().to_numpy()].sum()), ","),
              format(int(pnl[pd.Series(sess).duplicated().to_numpy()].sum()), ",")))


def main():
    a5, unit, q = M.load()
    df = M.cell(CROWN, a5, unit, q).sort_values("entry").reset_index(drop=True)
    print("NOISE on IWM r1 crown %s - post-verdict day-structure report (MANAGER #67), WF exit dates %s .. %s" % (
        "/".join(str(x) for x in CROWN), df.date.min().date(), df.date.max().date()))
    split(df, "net of cost")
    g = df.assign(pnl=df.pnl.to_numpy() + M.R8.COST * unit * df.ratio.to_numpy())
    split(g, "before cost")
    ent = pd.DatetimeIndex(df["entry"])
    if ent.tz is not None:
        ent = ent.tz_localize(None)
    w = (ent >= pd.Timestamp("2020-03-02")) & (ent < pd.Timestamp("2020-03-28"))
    print("  crown trades entered 2020-03-02 .. 2020-03-27 (#463's worst WF drawdown): %d, net $%s" % (
        int(w.sum()), format(int(df.pnl[w].sum()), ",")))
    B, _ = M.HH.book()
    bdays = pd.DatetimeIndex(B.index)
    d = dd5(pd.Series(M.daily(df, bdays), index=bdays))
    print("  crown DD5 (5 deepest daily drawdown episodes, 869 shares): $%s; worst $%s (worst / DD5 %.2f%s)" % (
        format(int(d["dd5_usd"]), ","), format(int(d["max_dd"]), ","), d["max_dd"] / d["dd5_usd"],
        ", driven by one episode" if d["one_episode"] else ""))


if __name__ == "__main__":
    main()
