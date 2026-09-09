"""DOES THE SWEEP LEADER TRAVEL TO ES, OR WAS IT FITTED TO THE NASDAQ TAPE?

The strongest test available without buying new data: take the configuration UNCHANGED to a
different market. The ENGU-Q crown is already known to travel - the R2 crown clears the house
bar on ES 1m 24h with no re-fitting - so ES is the established travel destination for this
family and the comparison is like for like.

The question that matters here: the sweep leader (hold cap 9,660 / trail 2.0 / breakeven 1.5)
was selected on the NQ tape AFTER seeing a grid. If its advantage over the shipped R3 is real
structure, it should show up on ES too, where nothing was fitted. If it evaporates - or
reverses - then the advantage was NQ-specific curve fitting and the leader should be dropped
however good its NQ numbers look.

ES leg convention taken from the existing NQ+ES book queue script, not invented here:
cost 0.40 points per round turn, multiplier $50. NQ shown beside it at its own 0.533/$20.

Reported for both tapes and all three configs: trades, net, profit factor, annualised MAR,
top-10 concentration, correlation of yearly net with that instrument's own yearly return, and
the two index down years. No new pass/fail bar - the pre-registered bar is unchanged from
tools/r3_buyback_sweep.py, and what is being judged is whether the RANKING survives the move.

RESULT, 2026-09-09: THE LEADER FAILS THIS TEST AND IS DROPPED AS A CANDIDATE.

    ES 1m 24h, cost 0.40 / $50, nothing re-fitted:
      LEADER   n 3,240  net $159,297  PF 1.183  MAR 0.33  top-10 72%  corr +0.34  2022 -$4,869
      R3       n 2,809  net $175,599  PF 1.215  MAR 0.34  top-10 65%  corr +0.46  2022 -$12,428
      R2 live  n 2,107  net $228,575  PF 1.360  MAR 0.43  top-10 65%  corr +0.45  2022 +$12,598

The leader is WORSE than the shipped R3 on three of the four reads that matter (MAR, profit
factor, concentration) and better only on correlation - so on the one tape where nothing was
fitted, the advantage that made it the leader on NQ does not merely shrink, it reverses. Per
the rule written into this file's header BEFORE the test ran, that makes its NQ advantage
NQ-specific curve fitting and it is dropped, whatever its NQ numbers look like.

TWO THINGS WORTH KEEPING FROM THE WRECKAGE:
  * The hold cap itself does not travel either. On ES the UNCAPPED R2 beats both capped
    variants on every read (PF 1.360 vs 1.215/1.183, MAR 0.43 vs 0.34/0.33) and is the only
    one of the three that makes money in 2022. Whatever the cap is fixing, it is specific to
    the Nasdaq tape - so an ES leg should not inherit it without its own evidence.
  * The tail bar FAILS on ES for all three: top-10 65-72% (bar is <60%) and the two capped
    configs lose money in 2022. The ENGU-Q family is materially more tail-dependent on ES
    than on NQ, which is a caution for the NQ+ES book line of work, not just for this cell.
"""
import io
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
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"
TAPES = [("NQ", 0.533, 20.0), ("ES", 0.40, 50.0)]

BASE = dict(buf_atr=0.3, tl_len=206, limit_atr=0.55, atr_len=52, act_R=1.5,
            ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
            min_brk=1.6, vol_mult=1.1, er_th=0.0)
CASES = [
    ("LEADER cap 9660 trail 2.0 be 1.5",
     dict(BASE, max_hold_bars=9660, trail_frac=2.0, breakeven_R=1.5)),
    ("R3     cap 8280 trail 2.5 be 2.0",
     dict(BASE, max_hold_bars=8280, trail_frac=2.5, breakeven_R=2.0)),
    ("R2live no cap  trail 2.5 be 2.0",
     dict(BASE, max_hold_bars=0, trail_frac=2.5, breakeven_R=2.0)),
]


def main():
    out = {}
    for inst, cost, mult in TAPES:
        master = find_master(inst, "1m", "eth", "db_noadj_eth")
        if not master:
            print("no master for %s -- skipped" % inst, flush=True)
            continue
        arr = load_master_arrays(master, **WIN)
        idx = pd.DatetimeIndex(pd.to_datetime(arr["index"]))
        try:
            idx = idx.tz_localize(None)
        except (TypeError, AttributeError):
            pass
        years = (idx[-1] - idx[0]).days / 365.25
        last = pd.Series(np.asarray(arr["close"], float), index=idx).resample("YE").last()
        bench = ((last / last.shift(1) - 1.0) * 100).dropna()
        bench.index = bench.index.year

        print("=" * 112)
        print("%s 1m 24h   %s..%s   cost %.3f pts   multiplier $%.0f"
              % (inst, idx[0].date(), idx[-1].date(), cost, mult), flush=True)
        print("  %-34s %5s %11s %6s %6s %6s %6s %9s %9s %5s"
              % ("config", "n", "net $", "PF", "MAR", "top10", "corr", "2018", "2022", "LB"))
        for label, p in CASES:
            r = run_backtest(STRAT, arrays=arr, params=dict(p), cost_pts=cost,
                             return_trades=True)
            tr = (r or {}).get("trades") or []
            if len(tr) < 30:
                print("  %-34s only %d trades" % (label, len(tr)), flush=True)
                continue
            d = np.array([t[2] * mult for t in tr], float)
            ent = pd.DatetimeIndex([idx[int(t[0])] for t in tr])
            eq = np.cumsum(d[np.argsort(ent.values)])
            dd = float(np.max(np.maximum.accumulate(eq) - eq))
            pf = float(d[d > 0].sum() / max(-d[d < 0].sum(), 1e-9))
            yr = pd.Series(d, index=ent).groupby(lambda x: x.year).sum()
            common = yr.index.intersection(bench.index)
            s = dict(n=len(d), net=float(d.sum()), pf=pf,
                     mar=(float(d.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                     dd=dd, top10=float(np.sort(d)[::-1][:10].sum() / d.sum()),
                     corr=float(yr[common].corr(bench[common])),
                     y2018=float(yr.get(2018, 0.0)), y2022=float(yr.get(2022, 0.0)),
                     lb_n=int((ent >= LB_FROM).sum()),
                     pos_years=int((yr > 0).sum()), n_years=int(len(yr)))
            out["%s %s" % (inst, label)] = s
            print("  %-34s %5d %11s %6.3f %6.2f %5.0f%% %+6.2f %9s %9s %5d"
                  % (label, s["n"], format(s["net"], ",.0f"), s["pf"], s["mar"],
                     s["top10"] * 100, s["corr"], format(s["y2018"], ",.0f"),
                     format(s["y2022"], ",.0f"), s["lb_n"]), flush=True)

    if all(("ES " + c[0]) in out for c in CASES):
        print("\nRANKING CHECK -- does the leader still beat R3 where nothing was fitted?")
        for key in ("mar", "pf", "top10", "corr"):
            l = out["ES LEADER cap 9660 trail 2.0 be 1.5"][key]
            r3 = out["ES R3     cap 8280 trail 2.5 be 2.0"][key]
            better = (l < r3) if key in ("top10", "corr") else (l > r3)
            print("  ES %-6s leader %8.3f  vs R3 %8.3f   -> leader %s"
                  % (key, l, r3, "BETTER" if better else "worse"))
    json.dump(out, io.open(os.path.join(SCR, "_es_travel.json"), "w"), indent=1, default=float)
    print("\nSAVED")


if __name__ == "__main__":
    main()
