"""SHELF No. 39 MAP CHECK - Lu, Chen & Hsu 2015 (JBF 61, 172-183), "Trend definition or holding
strategy: what determines the profitability of candlestick charting?" - REPORT ONLY, nothing
pre-registered, nothing optimised, no lockbox read.

THE PAPER. On Dow component stocks the authors cross three ways of defining the prior trend a
candlestick pattern is said to reverse with four holding rules, and find the HOLDING RULE decides
profitability far more than the trend definition. Eight three-day reversal patterns survive 0.5%
costs under one holding rule and fail under another.

WHY IT POINTS AT THIS FAMILY. ENGU-Q is an engulfing-reversal family: the paper is asking our
question, how long to hold the reversal and how to define the trend it reverses.

WHAT THIS CHECKS, BEFORE SPENDING A ROUND (the power-first gate). The paper's four holding rules are
FIXED N-DAY HOLDS - they are caps. This house has already run that dimension hard: ENGU-Q HOLD CAP r2
(run #491, 116 cap values from 0 to 6,900 bars) is DEAD, the eight walk-forward folds disagreed about
the cap (0, 0, 6540, 0, 6420, 6420, 900, 900) and the chain read 8.5 against the crown's 26.5. Q34
found the leg's dollars are in the EXITS, not the entries, and executor r1 (10-18) found 112% of the
overnight-hold arm's net comes from holds through the close. So the prior is poor and the honest
thing is to price the CEILING first.

THE CEILING is the best of the 12 cells with perfect hindsight over which cell to pick. If even the
best cell does not beat the current exit by enough to matter after paying for 12 tries, the shelf item
closes at draft with a ledger line and no prereg - that is a result, not a failure.

GRID, fixed here before the numbers:
  trend definition (an ENTRY FILTER on #335's own entries, never a new entry)
    T1  none - every #335 entry (the leg as it trades, so the grid contains the status quo)
    T2  the prior 10 sessions closed DOWN   (a short-run downtrend to reverse)
    T3  the prior 60 sessions closed DOWN   (a long-run downtrend to reverse)
  holding rule (replaces the leg's trailing exit)
    H0  the leg's own exit (the baseline column)
    H1 / H3 / H5 / H10   exit at the close of the 1st / 3rd / 5th / 10th session after entry

    python tools/enguq_shelf39_map.py
"""
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_shelf39"
WF0, WF1 = "2016-10-12", "2025-06-27"        # #335's own walk-forward folds 1..8
HOLDS = (0, 1, 3, 5, 10)                      # 0 = the leg's own exit
TRENDS = (("T1 none", 0), ("T2 down 10", 10), ("T3 down 60", 60))


def main():
    sys.path.insert(0, REPO)
    os.chdir(REPO)
    import numpy as np
    import pandas as pd
    from api.book_shadow import BOOK463_LEGS
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import four_numbers
    from augur_engine.engine import run_backtest

    os.makedirs(OUT, exist_ok=True)
    leg = [l for l in BOOK463_LEGS if l["strategy"].startswith("ENGUQ")][0]
    cost_rt = float(leg["cost_pts"]) * 20.0
    m = find_master(leg["instrument"], leg["timeframe"], leg["session"], leg["source"])
    arr = load_master_arrays(m, date_from="2010-06-07", date_to="2026-06-30")
    res = run_backtest(leg["strategy"], arrays=arr, params=leg["params"],
                       cost_pts=float(leg["cost_pts"]), return_trades=True)
    tr = sorted((int(t[0]), int(t[1]), float(t[2])) for t in res["trades"])
    ix = arr["index"]
    n = len(ix)
    close = np.asarray(arr["close"], float)
    bd = pd.DatetimeIndex(np.asarray(ix, dtype="datetime64[D]"))
    sess = pd.DatetimeIndex(sorted(set(bd)))
    last_bar = pd.Series(np.arange(n), index=bd).groupby(level=0).max()      # last bar of each session
    sess_no = pd.Series(np.arange(len(sess)), index=sess)
    print("%s on %s: %d bars, %d trades, cost $%.2f a round trip"
          % (leg["strategy"], m["filename"], n, len(tr), cost_rt))

    # session closes, for the trend filters - closes STRICTLY BEFORE the entry session, so a day's
    # own move can never qualify its own entry
    dc = pd.Series(close[last_bar.to_numpy()], index=sess)
    prev = dc.shift(1)

    def daily_of(trades, idx):
        """DAILY mark-to-market: an open position is valued at every session close it is held
        through, which is how the house values drawdown."""
        marks = last_bar.to_numpy()
        eq = np.zeros(len(marks))
        for i0, i1, pts in trades:
            pnl = pts * 20.0
            x0 = float(close[min(i0, n - 1)])
            x1 = float(close[min(i1, n - 1)])
            mv = (x1 - x0) * 20.0
            side = 1.0 if (mv == 0 or (mv > 0) == (pnl > 0)) else -1.0
            om = (marks > i0) & (marks < i1)
            eq[om] += side * (close[marks[om]] - x0) * 20.0
            eq[marks >= i1] += pnl
        s = pd.Series(eq, index=sess).diff()
        s.iloc[0] = eq[0]
        return s.reindex(idx).fillna(0.0)

    wf_idx = sess[(sess >= pd.Timestamp(WF0)) & (sess <= pd.Timestamp(WF1))]
    yrs = (pd.Timestamp(WF1) - pd.Timestamp(WF0)).days / 365.25

    def retime(i0, i1, pnl_pts, hold):
        """Re-exit a trade at the close of the hold-th session after its entry. The side is read from
        the leg's own trade (long-only here) and the P&L is re-priced bar to bar, cost unchanged."""
        if hold == 0:
            return i1, pnl_pts
        k = int(sess_no.get(bd[i0], -1))
        if k < 0:
            return i1, pnl_pts
        j = min(k + hold, len(sess) - 1)
        i2 = int(last_bar.iloc[j])
        if i2 <= i0:
            i2 = min(i0 + 1, n - 1)
        gross = (close[i2] - close[i0])                       # long-only family
        return i2, gross - float(leg["cost_pts"])

    rows = []
    base = None
    for tname, win in TRENDS:
        ok = None
        if win:
            down = (prev - prev.shift(win)) < 0
            ok = set(sess[down.reindex(sess).fillna(False).to_numpy()])
        for hold in HOLDS:
            sel = [(a, b, p) for a, b, p in tr if ok is None or bd[a] in ok]
            out = []
            prev_exit = -1
            for a, b, p in sel:
                if a < prev_exit:                  # a re-timed exit can overlap the next entry; the
                    continue                        # leg never holds two, so the later entry is skipped
                b2, p2 = retime(a, b, p, hold)
                out.append((a, b2, p2))
                prev_exit = b2
            d = daily_of(out, wf_idx)
            f = four_numbers(list(d), years=yrs)
            ntr = sum(1 for a, _b, _p in out if pd.Timestamp(WF0) <= bd[a] <= pd.Timestamp(WF1))
            rows.append({"trend": tname, "hold": ("leg exit" if hold == 0 else "%d sessions" % hold),
                         "trades": ntr, "roc30": f["roc30"], "dd5": f["dd5_usd"],
                         "ddpct": f["dd_pct_peak"], "sortino": f["sortino"],
                         "one_episode": f["one_episode"], "net": f["net"]})
            if tname.startswith("T1") and hold == 0:
                base = rows[-1]
            print("  %-11s %-12s trades %5d | ROC@30k %7.2f | DD5 %9s | DD%% %6.2f | Sortino %6.3f"
                  % (tname, rows[-1]["hold"], ntr, f["roc30"] or 0.0, format(f["dd5_usd"], ",.0f"),
                     f["dd_pct_peak"], f["sortino"] or 0.0))

    print("\nBASELINE (the leg as it trades, T1 + its own exit): ROC@30k %.2f" % base["roc30"])
    ceiling = max(rows, key=lambda r: r["roc30"] or -1e9)
    print("CEILING of the 12-cell grid, chosen with hindsight: %s + %s -> ROC@30k %.2f (%+.2f vs the leg)"
          % (ceiling["trend"], ceiling["hold"], ceiling["roc30"], ceiling["roc30"] - base["roc30"]))
    beat = [r for r in rows if (r["roc30"] or -1e9) > base["roc30"]]
    print("cells beating the leg: %d of %d" % (len(beat), len(rows)))
    print("\nREAD: the gate is the CEILING, not the mean. A ceiling at or below the leg means no "
          "holding rule in the paper's family can lift this leg,\nand the shelf item closes at draft "
          "with no prereg and no trials spent. A ceiling above it is a candidate, and then the 12 "
          "tries have to be paid for.")
    json.dump({"rows": rows, "baseline": base, "ceiling": ceiling, "wf": [WF0, WF1], "years": yrs,
               "master": m["filename"], "cost_pts": leg["cost_pts"]},
              open(os.path.join(OUT, "shelf39_map.json"), "w"), indent=1, default=str)
    print("\nwrote %s" % os.path.join(OUT, "shelf39_map.json"))


if __name__ == "__main__":
    main()
