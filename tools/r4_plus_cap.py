"""DO THE TWO INDEPENDENT IMPROVEMENTS STACK?

Two things measured today improve the ENGU-Q crown in DIFFERENT places:

    the HOLD CAP (R3, 8,280 bars)  fixes the tail - concentration 55.6% -> 43.8%, index
                                   correlation +0.51 -> +0.38, held-out trades 118 -> 155 -
                                   and costs about 8% of net and 0.05 of MAR.
    the DEEPER LIMIT (R4, 0.85)    improves the money side - MAR 0.92 -> 1.08, net +0.7%,
                                   2022 $7,340 -> $17,489 - and does NOTHING for the tail
                                   (concentration 56.3%, correlation +0.44).

They touch different parts of the trade: one is where the entry rests, the other is when the
position is forced out. So the obvious question is whether running both gives the cap's tail
fix at the deeper limit's risk-adjusted return, or whether they interfere.

The grid is small on purpose: three limit depths across the measured plateau x four caps
(off, and the three that looked good in the cap sweep). 12 cells, one at a time, no cleverness.

PRE-REGISTERED, written before running. A combined cell is a CANDIDATE only if it clears all:
  1. annualised MAR        > 1.08     (beat the deeper limit alone - stacking must ADD)
  2. top-10 share of net   < 46%      (keep the cap's tail fix; the cap alone gives 43.8%)
  3. index correlation     < 0.40     (the enforced tail bar neither change passes alone -
                                       the cap gets to +0.38 only without the deeper limit)
  4. both index down years positive
  5. >= 150 continuous held-out trades (the cap alone gives 155; do not lose that sample)
If nothing clears, the honest answer is that the two changes do not stack and the choice
between them is a choice - money or tail - not a free combination.

RESULT, 2026-09-09 - THEY STACK, and the winner is the first ENGU-Q config to pass the tail bar.

    limit  cap      trades      net       PF     MAR   top-10  corr    2018      2022     held-out
     0.55  off       1,949   $613,126   1.711   0.92   55.6%  +0.51  $12,392   $ 7,340     118
     0.55  8,280     2,647   $565,913   1.507   0.87   43.8%  +0.38  $17,697   $ 2,794     155
     0.85  off       1,995   $617,284   1.717   1.08   56.3%  +0.44  $10,574   $17,489     118
     0.85  9,660 *   2,585   $566,907   1.538   1.16   43.0%  +0.27  $13,022   $24,796     151
     1.00  9,660     2,613   $550,660   1.526   1.12   42.3%  +0.29  $10,611   $21,742     161

Two of sixteen cells cleared, and they are neighbours - a plateau, not a spike. The winner was
shipped as ENGUQ_1M_ETH_R5_1_0.py and queued (job CtGFgEBu). queue_guard --tail-enforce agrees
independently: VERDICT PASS, TAIL/BETA BAR PASS, top-10 45%, correlation +0.273, both down
years positive, 17/17 positive years, longest hold 15 days, reload 152 vs continuous 151.

Held-out year, which nobody tuned on: 151 trades / PF 1.648 / +$99,997 / R per year 66.8,
against the crown's 118 / 1.675 / $88,380 / 57.5. Cost: 7.5% of net and PF 1.711 -> 1.538.
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
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"       # the file that carries max_hold_bars
CROWN = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
             breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
             min_brk=1.6, vol_mult=1.1, er_th=0.0)
LIMITS = [0.55, 0.70, 0.85, 1.00]
CAPS = [0, 6900, 8280, 9660]


def score(tr, idx, bench, years):
    pnl = np.array([t[2] * MULT for t in tr], float)
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
    eq = np.cumsum(pnl[np.argsort(ent.values)])
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    order = np.argsort(pnl)[::-1]
    k = max(1, int(round(len(pnl) * 0.005)))
    keep = np.ones(len(pnl), bool)
    keep[order[:k]] = False
    q = pnl[keep]
    w = q[q > 0]
    pf_q = float(w.sum() / max(-q[q < 0].sum(), 1e-9))
    wr_q = len(w) / len(q)
    wf = pnl[pnl > 0]
    yr = pd.Series(pnl, index=ent).groupby(lambda x: x.year).sum()
    common = yr.index.intersection(bench.index)
    return dict(n=len(pnl), net=float(pnl.sum()),
                pf=float(wf.sum() / max(-pnl[pnl < 0].sum(), 1e-9)), dd=dd,
                mar=(float(pnl.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                top10=float(np.sort(pnl)[::-1][:10].sum() / pnl.sum()),
                prop_ev_r=(1 - wr_q) * (pf_q - 1),
                corr=float(yr[common].corr(bench[common])),
                y2018=float(yr.get(2018, 0.0)), y2022=float(yr.get(2022, 0.0)),
                lb_n=int((ent >= LB_FROM).sum()),
                pos_years=int((yr > 0).sum()), n_years=int(len(yr)))


def main():
    a = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(a["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    years = (idx[-1] - idx[0]).days / 365.25
    last = pd.Series(np.asarray(a["close"], float), index=idx).resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    print("  %-6s %-6s %5s %11s %6s %6s %6s %7s %6s %9s %9s %5s"
          % ("limit", "cap", "n", "net $", "PF", "MAR", "top10", "propEVR", "corr",
             "2018", "2022", "LB"), flush=True)
    rows, winners = [], []
    for lim, cap in itertools.product(LIMITS, CAPS):
        r = run_backtest(STRAT, arrays=a,
                         params=dict(CROWN, limit_atr=lim, max_hold_bars=cap),
                         cost_pts=COST, return_trades=True)
        tr = (r or {}).get("trades") or []
        if len(tr) < 50:
            continue
        s = score(tr, idx, bench, years)
        s.update(limit=lim, cap=cap)
        rows.append(s)
        ok = [("MAR>1.08", s["mar"] > 1.08), ("top10<46%", s["top10"] < 0.46),
              ("corr<0.40", s["corr"] < 0.40), ("2018>0", s["y2018"] > 0),
              ("2022>0", s["y2022"] > 0), ("LB>=150", s["lb_n"] >= 150)]
        s["clears_all"] = all(x for _, x in ok)
        if s["clears_all"]:
            winners.append(s)
        tag = ""
        if lim == 0.55 and cap == 0:
            tag = "  <- live crown"
        elif lim == 0.55 and cap == 8280:
            tag = "  <- R3 hold cap"
        elif lim == 0.85 and cap == 0:
            tag = "  <- R4 deeper limit"
        if s["clears_all"]:
            tag += "   <<< CLEARS ALL"
        print("  %-6.2f %-6d %5d %11s %6.3f %6.2f %5.1f%% %7.3f %+6.2f %9s %9s %5d%s"
              % (lim, cap, s["n"], format(s["net"], ",.0f"), s["pf"], s["mar"],
                 s["top10"] * 100, s["prop_ev_r"], s["corr"], format(s["y2018"], ",.0f"),
                 format(s["y2022"], ",.0f"), s["lb_n"], tag), flush=True)

    print("\nCLEARS EVERY BAR: %d of %d" % (len(winners), len(rows)))
    for w in sorted(winners, key=lambda x: -x["mar"]):
        print("   limit %.2f cap %d -> MAR %.2f  net $%s  top10 %.1f%%  corr %+.2f  LB %d"
              % (w["limit"], w["cap"], w["mar"], format(w["net"], ",.0f"),
                 w["top10"] * 100, w["corr"], w["lb_n"]))
    if not winners:
        print("   NONE -- the two changes do not stack. The choice between the tail fix and "
              "the risk-adjusted return is a real choice, not a free combination.")
    json.dump(rows, io.open(os.path.join(SCR, "_r4_plus_cap.json"), "w"), indent=1,
              default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
