"""CAN WE BUY BACK WHAT THE HOLD CAP COST, WITHOUT BREAKING THE TAIL BAR? (2026-09-09)

The hold cap fixed the owner's problem - concentration 56% -> 44%, index correlation
+0.51 -> +0.38, positive in both down years - and it cost about 8% of headline profit
(net $613k -> $566k, PF 1.711 -> 1.507, MAR 0.92 -> 0.87). This sweep asks whether any
neighbouring setting pays that back while STILL clearing the bar the owner asked for.

It moves the three knobs that trade the same thing the cap does - how long a winner is
allowed to run (trail_frac), when the stop goes to breakeven (breakeven_R), and where the
trail switches on (act_R) - around the shipped R3 configuration, at three caps.

PRE-REGISTERED, written before running. A cell REPLACES R3 only if it clears ALL of:
  1. top-10 share of net       < 60%          (the owner's concentration rule)
  2. positive in BOTH down years (2018, 2022) separately, not netted
  3. correlation of yearly net with the instrument's yearly return  < 0.40
  4. annualised MAR            > 0.87         (strictly better than R3)
  5. continuous lockbox trades >= 150         (R3 has 155; do not thin the held-out sample)
Net profit is deliberately NOT a bar - the whole point is an edge that does not need the
index to rise. Every cell is printed whatever it shows, and the count that clears is
reported honestly even when it is zero.

RESULT, 2026-09-09: 20 of 54 cells clear every bar - a broad plateau, not a lucky corner.
The grid reproduces the shipped R3 to the dollar at its own coordinates (2,647 trades /
$565,913 / MAR 0.87), which is the harness's own parity check.

  LEADER  cap 9,660 / trail 2.0 / breakeven 1.5:
      n 2,992   net $588,793   PF 1.509   MAR 1.04   top-10 39.9%   corr +0.33
      2018 +$19,275   2022 +$30,768   held-out 172 trades   longest hold 15 days
  beats shipped R3 (MAR 0.87, top-10 43.8%, corr +0.38, 155 held-out) on every read, and
  the queue guard confirms it independently: PASS, tail bar PASS, and the held-out year
  reconstructs to 172 trades both continuously and on an independent reload (no artifact).

KNOB DEGENERACY worth knowing before reading the table: act_R does nothing when
breakeven_R is 1.5, because the breakeven lift fires at or before the trail activates and
the stop only ever ratchets up; and breakeven_R 2.0 vs 2.5 is invisible whenever the trail
has already lifted the stop above entry by then. Identical rows in the output are that,
not a bug - confirmed against the strategy's exit block.

SELECTION CAVEAT: the leader was chosen after seeing this grid. See tools/r3_leader_stress.py
for the cost-stress and period-split tests it was then put through.
"""
import io
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
LB_FROM = pd.Timestamp("2025-06-30")
MULT, COST = 20.0, 0.533
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"

R3 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
          breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
          min_brk=1.6, vol_mult=1.1, er_th=0.0, max_hold_bars=8280)

CAPS = [6900, 8280, 9660]
TRAIL = [2.0, 2.5, 3.0]
BE = [1.5, 2.0, 2.5]
ACT = [1.5, 2.0]


def assess(trades, idx, bench, years):
    d = np.array([t[2] * MULT for t in trades], float)
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in trades])
    ext = pd.DatetimeIndex([idx[int(t[1])] for t in trades])
    order = np.argsort(ent.values)
    eq = np.cumsum(d[order])
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    wins = d[d > 0]
    pf = float(wins.sum() / max(-d[d < 0].sum(), 1e-9))
    wr = len(wins) / len(d)
    yr = pd.Series(d, index=ent).groupby(lambda x: x.year).sum()
    common = yr.index.intersection(bench.index)
    return dict(
        n=len(d), net=float(d.sum()), pf=pf, ev_r=(1 - wr) * (pf - 1), dd=dd,
        mar=(float(d.sum()) / years) / dd if dd > 1e-9 else float("nan"),
        top10=float(np.sort(d)[::-1][:10].sum() / d.sum()),
        corr=float(yr[common].corr(bench[common])),
        y2018=float(yr.get(2018, 0.0)), y2022=float(yr.get(2022, 0.0)),
        lb_n=int((ent >= LB_FROM).sum()), hold=int(max((ext - ent).days)),
        pos_years=int((yr > 0).sum()), n_years=int(len(yr)))


def clears(s):
    return [("top10<60%", s["top10"] < 0.60), ("2018>0", s["y2018"] > 0),
            ("2022>0", s["y2022"] > 0), ("corr<0.40", s["corr"] < 0.40),
            ("MAR>0.87", s["mar"] > 0.87), ("LB>=150", s["lb_n"] >= 150)]


def main():
    arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(arr["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    years = (idx[-1] - idx[0]).days / 365.25
    last = pd.Series(np.asarray(arr["close"], float), index=idx).resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    cells = [dict(R3, max_hold_bars=c, trail_frac=t, breakeven_R=b, act_R=a)
             for c, t, b, a in itertools.product(CAPS, TRAIL, BE, ACT)]
    print("%d cells; R3 itself is one of them (cap 8280 / trail 2.5 / be 2.0 / act 1.5)"
          % len(cells), flush=True)

    rows, winners = [], []
    for i, p in enumerate(cells, 1):
        r = run_backtest(STRAT, arrays=arr, params=dict(p), cost_pts=COST,
                         return_trades=True)
        tr = (r or {}).get("trades") or []
        if len(tr) < 50:
            print("  [%2d/%d] cap %5d trail %.1f be %.1f act %.1f  -- only %d trades, skipped"
                  % (i, len(cells), p["max_hold_bars"], p["trail_frac"], p["breakeven_R"],
                     p["act_R"], len(tr)), flush=True)
            continue
        s = assess(tr, idx, bench, years)
        s.update(cap=p["max_hold_bars"], trail=p["trail_frac"], be=p["breakeven_R"],
                 act=p["act_R"])
        rows.append(s)
        ok = clears(s)
        s["clears_all"] = all(v for _, v in ok)
        if s["clears_all"]:
            winners.append(s)
        print("  [%2d/%d] cap %5d trail %.1f be %.1f act %.1f  n=%4d net=$%9s PF=%.3f "
              "MAR=%.2f top10=%4.1f%% corr=%+.2f 2018=$%7s 2022=$%8s LB=%3d hold=%3dd%s"
              % (i, len(cells), s["cap"], s["trail"], s["be"], s["act"], s["n"],
                 format(s["net"], ",.0f"), s["pf"], s["mar"], s["top10"] * 100, s["corr"],
                 format(s["y2018"], ",.0f"), format(s["y2022"], ",.0f"), s["lb_n"],
                 s["hold"], "   <<< CLEARS ALL" if s["clears_all"] else ""), flush=True)

    print("\nCLEARS EVERY BAR: %d of %d" % (len(winners), len(rows)), flush=True)
    for w in sorted(winners, key=lambda x: -x["mar"]):
        print("   cap %5d trail %.1f be %.1f act %.1f -> MAR %.2f net $%s top10 %.0f%% "
              "corr %+.2f LB %d"
              % (w["cap"], w["trail"], w["be"], w["act"], w["mar"], format(w["net"], ",.0f"),
                 w["top10"] * 100, w["corr"], w["lb_n"]), flush=True)
    json.dump(rows, io.open(os.path.join(SCR, "_r3_buyback.json"), "w"), indent=1,
              default=float)
    print("SAVED", flush=True)


if __name__ == "__main__":
    main()
