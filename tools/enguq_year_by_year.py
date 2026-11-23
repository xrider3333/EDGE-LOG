"""Board 180 + MANAGER #194: is ENGU-Q DECAYING, or was 2025-26 one bad episode?

THE QUESTION. Run #556 (the volatility-sized arm) FAILED its lockbox year 2025-06-30..2026-06-30
with -$14,674. MANAGER asks whether the BASELINE lost the same year too. If the baseline also lost
it, the year is a bad tape for the whole family and #556's FAIL says nothing about its sizing; if
the baseline held up, the loss belongs to the sizing.

WHAT THIS RUNS. The #335 paper cell -- api.paper.ENGUQ_335, which is the R2 file's DEFAULTS
(api/paper_leg_params.py records ENGUQ_335 as how='defaults', cell 0), i.e. exactly what the paper
leg and NinjaTrader trade -- over the WHOLE adjusted master, split by trading year. Nothing is
tuned here and no parameter is chosen by looking at an outcome.

HOW TO READ IT, STATED FIRST. #335's own search ran to 2025-06-29, so every year up to 2025-06 is
IN-SAMPLE for this cell and only 2025-07..2026-06 is unseen. The in-sample years are therefore a
ceiling, not a forecast; the one number that answers MANAGER's question is the last row, and the
honest comparison is "the unseen year against the in-sample spread", not against the mean.

Trades are assigned to the year of their EXIT bar, and a year's P&L is its daily curve summed, so
a multi-day hold that spans a year boundary lands wholly in the year it closed -- the same
convention the stitched book files use. Cost 0.783 pts a round trip, mult 20, one NQ, no sizing.

Output: C:/EdgeLog/_anatomy_cache/bookq/t180/regime_335.txt + .json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
from api.paper import ENGUQ_335                                  # noqa: E402
from augur_engine.data import find_master, load_master_arrays    # noqa: E402
from augur_engine.drawdowns import four_numbers                  # noqa: E402
from augur_engine.strategies import load_strategy                # noqa: E402

COST, MULT = 0.783, 20.0
OUT = r"C:\EdgeLog\_anatomy_cache\bookq\t180"
LB_FROM, LB_TO = "2025-06-30", "2026-06-30"
LINES = []


def P(s=""):
    print(s, flush=True)
    LINES.append(s)


def main():
    mod = load_strategy("ENGUQ_1M_ETH_R2_1_0.py")
    m = find_master("NQ", "1m", "eth", "db_adj_eth")
    arr = load_master_arrays(m)
    idx = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    day_id = np.asarray(arr["day_id"])
    P("ENGU-Q #335 PAPER CELL BY YEAR -- the regime-vs-decay read (board 180, MANAGER #194)")
    P("master %s, %s bars, %s .. %s" % (m.get("filename"), format(len(idx), ","), idx[0], idx[-1]))
    P("cell = api.paper.ENGUQ_335 (the R2 defaults, what the paper leg trades): %s"
      % json.dumps(ENGUQ_335, sort_keys=True))
    P("cost %.3f pts RT, mult %s, 1 NQ, trades dated by EXIT bar, years are TRADING years" % (COST, MULT))
    P("IN-SAMPLE WARNING: #335's search ran to 2025-06-29, so only %s..%s is unseen." % (LB_FROM, LB_TO))
    P("")

    out = mod.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"],
                           volumes=arr["volume"], day_id=day_id, return_trades=True, **ENGUQ_335)
    tr = out["trades"]
    if not tr:
        P("NO TRADES -- refusing to report anything")
        return
    pts = np.array([float(t[2]) for t in tr], float)
    ex = np.array([int(t[1]) for t in tr], int)
    usd = (pts - COST) * MULT
    dates = idx[ex].normalize()
    daily = pd.Series(usd, index=dates).groupby(level=0).sum().sort_index()
    P("whole master: %d trades, net $%s" % (len(tr), format(int(usd.sum()), ",")))
    P("")

    res = {}
    P("%-22s %10s %8s %7s %8s %9s %7s" % ("stretch", "net $", "trades", "days", "worst DD", "DD5", "Sortino"))
    # calendar-ish trading years ending 06-30, so the last row IS run #556's lockbox year
    edges = [("%d-06-30" % y, "%d-06-30" % (y + 1)) for y in range(2010, 2026)]
    for a, b in edges:
        s = daily[(daily.index >= a) & (daily.index < b)]
        if s.empty:
            continue
        n = int(((dates >= a) & (dates < b)).sum())
        fn = four_numbers(list(s.values), dates=[d.strftime("%Y-%m-%d") for d in s.index])
        tag = "%s..%s" % (a[:7], b[:7])
        res[tag] = dict(fn, net=float(s.sum()), trades=n, days=int(s.size))
        P("%-22s %10s %8d %7d %8s %9s %7.2f"
          % (tag, format(int(s.sum()), ","), n, s.size, format(int(fn["max_dd"]), ","),
             format(int(fn["dd5_usd"]), ","), fn["sortino"]))

    P("")
    lb = res.get("2025-06..2026-06")
    if lb:
        others = [v["net"] for k, v in res.items() if k != "2025-06..2026-06"]
        worse = sum(1 for v in others if v < lb["net"])
        P("THE UNSEEN YEAR %s..%s: net $%s on %d trades."
          % (LB_FROM, LB_TO, format(int(lb["net"]), ","), lb["trades"]))
        P("  %d of the %d earlier (in-sample) years were WORSE than it." % (worse, len(others)))
        P("  negative years in the whole span: %d of %d"
          % (sum(1 for v in res.values() if v["net"] < 0), len(res)))
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "regime_335.txt"), "w").write("\n".join(LINES) + "\n")
    json.dump(res, open(os.path.join(OUT, "regime_335.json"), "w"), indent=2, default=str)
    P("")
    P("written: %s" % os.path.join(OUT, "regime_335.txt"))


if __name__ == "__main__":
    main()
