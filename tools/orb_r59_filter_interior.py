"""
ROUND 59 - where does the volatility filter turn over, between LOOSE and OFF? (2026-09-24)

THE QUESTION. The opening-range family's money moves in lockstep with how hard the volatility
filter gates: walk-forward money is $339,110 at run #257 (filter 0.50), $334,080 at run #266
(filter off), $310,678 at the control (0.70), $290,411 at #294 (0.75), $276,201 at #297 (0.80)
and $261,668 at #298 (0.80 on both gates). Looser earns more and tighter is a drawdown dial -
but the direction does not run to the end: turning the filter OFF earns $6,470 LESS than merely
loosening it. Three coarse samples (0.0, 0.5, 0.7) cannot say whether that is a real interior
peak, a broad flat shelf we happen to have sampled at two points, or noise between neighbours.
The E1-region validate queued today fences the filter at 0.4-0.6, so it cannot answer this
either. This maps the whole span at #257's geometry, and crosses it with stop width because
stop and filter are the two knobs #257 moves.

WHAT IS SCORED, AND WHY IT IS NOT NET. This stack's house rule since 2026-09-14 is to judge by
MONEY BY CALENDAR YEAR against the control, not by a return-over-drawdown ratio - a ratio lead
turned out to be pure drawdown twice (runs #297 and #397). So every cell reports: full-window
net, drawdown, the number of calendar years it beats the control, total money against the
control, money against the control in the four biggest years (2021, 2022, 2023, 2025), its
worst single year, and its top-ten-trade concentration share, which has retracted three claims
in this stack on its own.

DISCIPLINE, WRITTEN BEFORE THE RUN. This is read for SHAPE ONLY - is there an interior peak in
the filter, and is the ridge around #257 broad or narrow. It is NOT a hunt for a new crown, and
nothing here gets queued on the strength of a maximum. The reason is measured, not assumed:
this session's meta walk-forward over eleven non-overlapping forward years found that re-picking
opening-range parameters has NO forward skill - re-picking earned $166k, leaving the parent
defaults alone earned $377k, and a configuration drawn at random earned $312k. So a cell that
beats #257 by a few thousand dollars is a coordinate on a surface, not a recommendation. The
useful outputs are the SHAPE of the filter curve and the WIDTH of the plateau.

Full window on one contract to the certified end 2026-08-13, NQ 5m RTH no-adjust, 0.533 pts per
round turn. Writes its results after every cell so a formatting slip cannot discard the sweep.
"""
import os
import sys
import time

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

OUT = os.path.join(ROOT, "_r59_filter_interior.csv")
FN = "augur_strategies/ORB_3_6.py"
MULT = 20.0
COST = 0.533
WIN = dict(date_from="2010-06-07", date_to="2026-08-13")
BIG_YEARS = (2021, 2022, 2023, 2025)

CONTROL = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0,
               trail_bars=0, flat_eod=True, skip_holidays=True, breakout_buf=0.25,
               stop_frac=2.0, target_R=5.5, be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)
# run #257: the control with a wider stop, a bigger buffer and a looser vol-regime filter
E1 = dict(CONTROL, stop_frac=2.5, breakout_buf=0.30, atr_filter=0.5)


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays
    from research_beacon import beacon

    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
    idx = pd.DatetimeIndex(A["index"])

    def replay(params):
        r = run_backtest(FN, arrays=A, params=params, cost_pts=COST, return_trades=True)
        pnl = pd.Series([t[2] * MULT for t in r["trades"]],
                        index=[idx[t[1]].tz_localize(None) for t in r["trades"]]).sort_index()
        cum = pnl.cumsum()
        dd = float((cum - cum.cummax()).min())
        by_year = pnl.groupby(pnl.index.year).sum()
        top10 = pnl.nlargest(10).sum()
        return dict(net=float(pnl.sum()), dd=abs(dd), trades=int(len(pnl)),
                    pf=float(r["profit_factor"]), by_year=by_year,
                    top10_share=(float(top10) / float(pnl.sum()) if pnl.sum() > 0 else float("nan")))

    print("replaying the control for the year-by-year baseline", flush=True)
    base = replay(dict(CONTROL))
    print("  control: net $%.0f  dd $%.0f  %d trades  pf %.3f"
          % (base["net"], base["dd"], base["trades"], base["pf"]), flush=True)

    cells = [(a, s) for a in (0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80)
             for s in (2.0, 2.25, 2.5, 2.75, 3.0)]
    rows = []
    t0 = time.time()
    with beacon("round 59 vol-filter interior x stop width", total=len(cells)) as bc:
        for i, (a, s) in enumerate(cells, 1):
            r = replay(dict(E1, atr_filter=a, stop_frac=s))
            diff = (r["by_year"] - base["by_year"]).fillna(0.0)
            row = dict(atr=a, stop=s, net=r["net"], dd=r["dd"], pf=r["pf"], trades=r["trades"],
                       top10_share=r["top10_share"],
                       years_better=int((diff > 0).sum()), vs_control=float(diff.sum()),
                       big4=float(diff.reindex(list(BIG_YEARS)).fillna(0.0).sum()),
                       worst_year=float(r["by_year"].min()))
            rows.append(row)
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print("[%4.0fs] %3d/%d filter %.2f stop %.2f | net $%8.0f dd $%7.0f pf %.3f | "
                  "vs control $%+8.0f (big4 $%+8.0f, %2d yrs) worst $%+8.0f top10 %.0f%%"
                  % (time.time() - t0, i, len(cells), a, s, row["net"], row["dd"], row["pf"],
                     row["vs_control"], row["big4"], row["years_better"], row["worst_year"],
                     100 * row["top10_share"]), flush=True)
            bc.step(i)

    df = pd.DataFrame(rows)
    for col, title in (("vs_control", "MONEY vs THE CONTROL, whole window"),
                       ("big4", "MONEY vs THE CONTROL in the four biggest years"),
                       ("net", "FULL-WINDOW NET")):
        print("\n%s (rows = vol-regime filter, columns = stop x range width)" % title)
        print(df.pivot_table(index="atr", columns="stop", values=col).round(0).to_string())
    e1 = df[(df.atr == 0.5) & (df.stop == 2.5)].iloc[0]
    print("\nrun #257's own cell: net $%.0f, $%+.0f vs the control, %d years better, top-ten %.0f%%"
          % (e1.net, e1.vs_control, e1.years_better, 100 * e1.top10_share))
    print("cells beating #257 on money vs the control: %d of %d"
          % (int((df.vs_control > e1.vs_control).sum()), len(df)))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
