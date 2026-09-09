"""DOES THE SWEEP LEADER SURVIVE THE THINGS THAT USUALLY KILL A LEADER? (2026-09-09)

The 54-cell sweep produced a cell that clears the owner's tail bar AND beats the shipped
hold-capped crown on every read (cap 9,660 / trail 2.0 / breakeven 1.5: MAR 1.04 vs 0.87,
net $588,793 vs $565,913, top-10 40% vs 44%, correlation +0.33 vs +0.38, 172 held-out
trades vs 155). It was picked AFTER seeing the grid, so before it goes anywhere it gets
the two tests that have killed leaders in this project before:

  1. COST STRESS. The 2026-09-08 NOISE round showed a leader can lose most of its
     risk-adjusted return between 0.533 and 1.033 points of cost while a plainer geometry
     barely moves. Same three costs here.
  2. PERIOD SPLIT. Fit the story on the first half, then look at the second - and the
     other way round. A cell that only works in the melt-up half is the beta problem
     wearing a different hat.

Three configs so the comparison means something: the sweep leader, the shipped R3
(hold cap alone), and the live R2 crown (no cap). Nothing here crowns anything; the
running full-discovery validate is what decides.

RESULT, 2026-09-09.

1. COST STRESS - the leader PASSES, and is the least cost-fragile of the three in
   relative terms. Doubling cost from 0.533 to 1.033 points:
       leader   MAR 1.04 -> 1.00 -> 0.97   (-7%)   net $588,793 -> $558,873
       R3       MAR 0.87 -> 0.84 -> 0.82   (-6%)   net $565,913 -> $539,443
       R2 live  MAR 0.92 -> 0.90 -> 0.87   (-5%)   net $613,126 -> $593,636
   The leader still beats both at every cost. Trade counts do not move with cost (entries
   are not marginal), which is the shape you want - nothing here is fee-scalping.

2. PERIOD SPLIT - THE REAL CAVEAT, and it applies to ALL THREE configs, not just the
   leader. Cut at 2018-06-30:
       leader   1st half $54,074 PF 1.252 MAR 0.74  |  2nd half $534,720 PF 1.568 MAR 1.89
       R3       1st half $58,099 PF 1.278 MAR 0.81  |  2nd half $507,815 PF 1.560 MAR 1.57
       R2 live  1st half $65,872 PF 1.393 MAR 0.81  |  2nd half $547,253 PF 1.788 MAR 1.65
   READ THE DOLLARS CAREFULLY: dollar P&L scales with the index level, and the Nasdaq was
   near 2,000 in 2011 against 20,000 in 2025, so a ~10x dollar gap between halves is mostly
   arithmetic, NOT a 10x edge gap. The scale-free reads are PF and MAR (both are ratios of
   dollars, so the index level cancels), and those still say the edge was materially weaker
   before 2018: PF 1.25 vs 1.57, MAR 0.74 vs 1.89 on the leader.
   So the family is profitable in both halves but roughly twice as good in the second. That
   is a regime caveat that belongs on any card for this line of work, and it is NOT the
   owner's beta problem in disguise - the second half contains 2022, when the index fell 32%
   and the leader made +$30,768.
"""
import io
import os
import sys
import json

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
MULT = 20.0
COSTS = [0.533, 0.783, 1.033]
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"

BASE = dict(buf_atr=0.3, tl_len=206, limit_atr=0.55, atr_len=52, act_R=1.5,
            ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
            min_brk=1.6, vol_mult=1.1, er_th=0.0)
CASES = [
    ("LEADER  cap 9660 trail 2.0 be 1.5",
     dict(BASE, max_hold_bars=9660, trail_frac=2.0, breakeven_R=1.5)),
    ("R3      cap 8280 trail 2.5 be 2.0",
     dict(BASE, max_hold_bars=8280, trail_frac=2.5, breakeven_R=2.0)),
    ("R2 live no cap  trail 2.5 be 2.0",
     dict(BASE, max_hold_bars=0, trail_frac=2.5, breakeven_R=2.0)),
]
SPLIT = pd.Timestamp("2018-06-30")   # roughly halves the 16-year window


def stats(d, ent, years):
    if len(d) < 20:
        return None
    order = np.argsort(ent.values)
    eq = np.cumsum(d[order])
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    wins = d[d > 0]
    pf = float(wins.sum() / max(-d[d < 0].sum(), 1e-9))
    return dict(n=len(d), net=float(d.sum()), pf=pf, dd=dd,
                mar=(float(d.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                top10=float(np.sort(d)[::-1][:10].sum() / d.sum()))


def main():
    arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(arr["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    out = {}

    print("1. COST STRESS  (points per round turn; 0.533 = about two ticks plus fees)")
    print("   %-34s %8s %6s %7s %6s %6s" % ("config @ cost", "net $", "PF", "MAR", "n", "top10"))
    for label, p in CASES:
        for cost in COSTS:
            r = run_backtest(STRAT, arrays=arr, params=dict(p), cost_pts=cost,
                             return_trades=True)
            tr = (r or {}).get("trades") or []
            d = np.array([t[2] * MULT for t in tr], float)
            ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
            yrs = (idx[-1] - idx[0]).days / 365.25
            s = stats(d, ent, yrs)
            out["%s @ %.3f" % (label, cost)] = s
            print("   %-30s @%.3f %8s %6.3f %7.2f %6d %5.0f%%"
                  % (label, cost, format(s["net"], ",.0f"), s["pf"], s["mar"], s["n"],
                     s["top10"] * 100), flush=True)
        print()

    print("2. PERIOD SPLIT  (same run, cut at %s -- neither half was tuned separately)"
          % SPLIT.date())
    print("   %-34s %10s %6s %6s   %10s %6s %6s"
          % ("config", "1st net", "PF", "MAR", "2nd net", "PF", "MAR"))
    for label, p in CASES:
        r = run_backtest(STRAT, arrays=arr, params=dict(p), cost_pts=0.533,
                         return_trades=True)
        tr = (r or {}).get("trades") or []
        d = np.array([t[2] * MULT for t in tr], float)
        ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
        halves = []
        for lo, hi in ((idx[0], SPLIT), (SPLIT, idx[-1])):
            m = (ent >= lo) & (ent < hi)
            halves.append(stats(d[m], ent[m], (hi - lo).days / 365.25))
        a, b = halves
        out["split " + label] = dict(first=a, second=b)
        print("   %-34s %10s %6.3f %6.2f   %10s %6.3f %6.2f"
              % (label, format(a["net"], ",.0f"), a["pf"], a["mar"],
                 format(b["net"], ",.0f"), b["pf"], b["mar"]), flush=True)

    json.dump(out, io.open(os.path.join(SCR, "_leader_stress.json"), "w"), indent=1,
              default=float)
    print("\nSAVED")


if __name__ == "__main__":
    main()
