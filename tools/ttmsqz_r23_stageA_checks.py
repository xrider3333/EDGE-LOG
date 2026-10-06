"""TTM round 23 Stage A - the reported RISK r1 checks (prereg tools/TTM_R23_PREREG.txt, a4260281 + 8f574275).

Reads FRONTIER's Stage A export (C:/EdgeLog/_anatomy_cache/ttm23/daily.csv: valued-daily book P&L per book, days
before 2025-06-30, book UTC day stamps). Walk-forward = 2016-06-30 .. 2025-06-29 as FRONTIER scored it.
R1: COIL minus TWIN WF ROC@$30k without 2020-02-01 .. 2020-04-30 (days dropped, drawdown re-walked).
R3: per WF year (one-year blocks from 06-30), d = m_coil - c x m_twin, c = COIL's average size (stageA.json).
The shuffle (A3) is not run: A1 already fails on every book, so no clause set can pass.
Log: tools/data/ttmsqz_r23_stageA_checks.txt
"""
import json
import os

import numpy as np
import pandas as pd

SRC = r"C:\EdgeLog\_anatomy_cache\ttm23"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "data",
                   "ttmsqz_r23_stageA_checks.txt")
WF0, WF1 = pd.Timestamp("2016-06-30"), pd.Timestamp("2025-06-29")


def roc30(s):
    cum = np.concatenate([[0.0], s.cumsum().to_numpy()])
    dd = float((np.maximum.accumulate(cum) - cum).max())
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return 30.0 * (s.sum() / yrs) / dd if dd > 0 else float("inf")


def main():
    d = pd.read_csv(os.path.join(SRC, "daily.csv"), parse_dates=["day"]).set_index("day")
    st = json.load(open(os.path.join(SRC, "stageA.json"), encoding="utf-8"))
    c = float(st["COIL"]["avg_size_wf"])
    wf = d[(d.index >= WF0) & (d.index <= WF1)]
    L = ["TTM round 23 Stage A - reported checks (FRONTIER export %s; WF %s .. %s, %d days)" % (
        SRC, wf.index[0].date(), wf.index[-1].date(), len(wf))]
    L.append("  WF ROC@$30k here: TWIN %.2f  COIL %.2f  ORB-ONLY %.2f  ENGU-ONLY %.2f  (FRONTIER: 93.81 / 90.22 / 90.43 / 93.40)" % (
        roc30(wf.TWIN), roc30(wf.COIL), roc30(wf["ORB-ONLY"]), roc30(wf["ENGU-ONLY"])))
    ex = wf[~((wf.index >= "2020-02-01") & (wf.index <= "2020-04-30"))]
    L.append("  R1 without Feb-Apr 2020: TWIN %.2f  COIL %.2f  -> COIL minus TWIN %+.2f (full WF %+.2f)" % (
        roc30(ex.TWIN), roc30(ex.COIL), roc30(ex.COIL) - roc30(ex.TWIN), roc30(wf.COIL) - roc30(wf.TWIN)))
    L.append("  R2 tuning block 2010-06-07 .. 2016-06-29 (FRONTIER): TWIN %.2f  COIL %.2f -> %+.2f" % (
        st["TWIN"]["is"]["roc30"], st["COIL"]["is"]["roc30"], st["COIL"]["is"]["roc30"] - st["TWIN"]["is"]["roc30"]))
    pos = 0
    rows = []
    for k in range(9):
        a = WF0 + pd.DateOffset(years=k)
        b = a + pd.DateOffset(years=1) - pd.Timedelta(days=1)
        y = wf[(wf.index >= a) & (wf.index <= b)]
        dd = y.COIL.mean() - c * y.TWIN.mean()
        pos += dd > 0
        rows.append("%s: d %+.1f" % (a.year, dd))
    L.append("  R3 breadth, c = %.4f: %s -> d > 0 in %d of 9 years (needs 6)" % (c, "; ".join(rows), pos))
    L.append("  Tilted share of WF trades: ORB %.1f%%, ENGU-Q %.1f%% (both under the 20%% near-uniform line)" % (
        100 * st["COIL"]["tilted_share_wf"]["ORB_3_6_C2.py"], 100 * st["COIL"]["tilted_share_wf"]["ENGUQ_1M_ETH_R2_1_0.py"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
