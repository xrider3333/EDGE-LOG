"""Round-14 candidate check: the published OVERNIGHT DRIFT (Boyarchenko/Larsen/Whelan,
NY Fed SR 917 / J. Finance) measured directly on OUR ETH masters.

Claim: ~all of the US equity premium accrues 02:00-03:00 ET (European open), ~3.7%/yr
pre-2021; the authors' own 2026 follow-up ("The Disappearing Overnight Drift") reports
~zero since 2021. This script measures the per-night 02:00->03:00 move (and the full
prior-RTH-close->09:30 overnight move for reference) by year, in points and in $ net
of the pre-registered overnight round-trip cost (NQ 0.783 pts = $5.66 comm + 0.5-pt
Globex slippage per the round-6 GLOBEX precedent; ES 0.613).

Diagnostic, not a strategy build: if the measured drift can't clear the cost line even
in its best era, a DAWN strategy build is pointless and the candidate closes without
spending anything. Window 2010-06-07 -> 2025-06-30 (consistent with the sealed year,
which stays unloaded).
"""
import sys, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
UP = REPO / "augur_uploads"
COST = {"NQ": 0.783, "ES": 0.613}   # overnight RT pts (comm + 0.5-pt Globex slippage)
MULT = {"NQ": 20.0, "ES": 50.0}

for inst in ["NQ", "ES"]:
    f = UP / f"NOADJ_{inst}_5m_ETH.csv"
    df = pd.read_csv(f)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    df = df[(df.index >= pd.Timestamp("2010-06-07", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2025-07-01", tz="US/Eastern"))].sort_index()
    o = df["open"]

    # per calendar date: open of first bar >= 02:00 and open of first bar >= 03:00
    hhmm = df.index.hour * 60 + df.index.minute
    d2 = df[(hhmm >= 120) & (hhmm < 150)].groupby(df[(hhmm >= 120) & (hhmm < 150)].index.date)["open"].first()
    d3 = df[(hhmm >= 180) & (hhmm < 210)].groupby(df[(hhmm >= 180) & (hhmm < 210)].index.date)["open"].first()
    both = pd.concat([d2.rename("p2"), d3.rename("p3")], axis=1).dropna()
    both["mv"] = both["p3"] - both["p2"]
    both.index = pd.to_datetime(both.index)

    cost, mult = COST[inst], MULT[inst]
    yr = both.groupby(both.index.year)["mv"]
    print(f"\n=== {inst}: 02:00->03:00 ET drift (pts/night), n={len(both)} nights, cost line = {cost} pts ===")
    print(f"{'year':>5} {'nights':>7} {'mean pts':>9} {'net $/yr @1lot':>15}")
    tot_net = 0.0
    for y, g in yr:
        net = (g.sum() - cost * len(g)) * mult
        tot_net += net
        print(f"{y:>5} {len(g):>7} {g.mean():>9.3f} {net:>15,.0f}")
    pre21 = both[both.index.year <= 2020]["mv"]
    post21 = both[both.index.year >= 2021]["mv"]
    print(f"  pre-2021 mean {pre21.mean():+.3f} pts/night (paper: positive)  "
          f"post-2021 mean {post21.mean():+.3f} (paper follow-up: ~zero)")
    print(f"  ALL-IN net @1 contract, 15yr: ${tot_net:,.0f}   "
          f"(gross pts/night {both['mv'].mean():+.3f} vs cost {cost})")
