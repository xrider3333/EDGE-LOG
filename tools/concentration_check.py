"""
CONCENTRATION CHECK — run this BEFORE queueing anything, not after it passes.

Why it exists (2026-09-08): an ENGU-Q 24h configuration found by an R / YR-objective
search scored the library-record EV R 1.40, held 26 of 26 one-step neighbours in a
plateau check, and then PASSED its Auto-Validate on all six gates (run #320). It makes
101% of its net from TEN trades in fifteen years; strip them and the other 823 trades
lose money at PF 0.98. Neither a plateau check nor a walk-forward nor a lockbox detects
that - they answer different questions:
    plateau      -> do NEIGHBOURING settings agree?
    walk-forward -> does it hold on data it was not tuned on?
    concentration-> is the profit spread across trades, or is it a handful of tails?
EV R is especially prone to it: dividing by the average LOSING trade rewards exactly the
few-enormous-winners shape, so a wide trail on a 24-hour tape can score 1.4 while being
untradeable.

Usage:
    python tools/concentration_check.py <strategy.py> <inst> <tf> <sess> <src> <cost> <mult> [params_json]
    (params_json omitted or {} = the file's own defaults, which for a fenced neighbourhood
     file reproduces its plateau centre)

Reports, on the pre-lockbox window: full stats, the top-10 share of net, and the stats
with the ten biggest winners removed. Net / PF / win% / EV R are order-independent so they
stay meaningful after the removal; DRAWDOWN IS NOT and is deliberately not printed for the
ex-top-10 series.

Bar used by this project: top-10 share >= 90% = ARTIFACT, do not queue. 50-90% = state it
loudly on the card. Below 50% with a positive ex-top-10 net = a normally-distributed edge.
Reference points measured: deployed ENGU-Q leg 80%, NOISE crowns 22-42%.
"""
import os, sys, json
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")


def stats(pnls):
    p = np.asarray(pnls, float)
    if len(p) == 0:
        return None
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gw / gl if gl > 0 else float("inf")
    w = float((p > 0).mean())
    return dict(n=len(p), net=float(p.sum()), pf=float(pf), win=100 * w, evr=(1 - w) * (pf - 1))


def main():
    fn, inst, tf, sess, src, cost, mult = sys.argv[1:8]
    params = json.loads(sys.argv[8]) if len(sys.argv) > 8 else {}
    A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
    r = run_backtest(fn, arrays=A, params=params, cost_pts=float(cost), return_trades=True)
    if not r or not r.get("trades"):
        print("no trades"); sys.exit(2)
    M = float(mult)
    pnls = [t[2] * M for t in r["trades"]]
    cum = np.cumsum([p for p in pnls]); dd = float((cum - np.maximum.accumulate(cum)).min())
    full = stats(pnls)
    srt = sorted(pnls, reverse=True)
    top10 = sum(srt[:10])
    ex = stats(srt[10:])
    share = 100 * top10 / full["net"] if full["net"] else float("inf")
    print(f"\n{fn}  {inst} {tf} {sess}  window {WIN['date_from']}..{WIN['date_to']}")
    print(f"  FULL         n={full['n']:5} net=${full['net']:>11,.0f} PF={full['pf']:6.3f} win={full['win']:5.1f}% "
          f"EV R={full['evr']:6.3f} DD=${-dd:>10,.0f}")
    print(f"  top-10 winners = ${top10:,.0f}  =  {share:.0f}% of net")
    print(f"  EX-TOP-10    n={ex['n']:5} net=${ex['net']:>11,.0f} PF={ex['pf']:6.3f} win={ex['win']:5.1f}% "
          f"EV R={ex['evr']:6.3f}   (drawdown not meaningful once trades are reordered)")
    if share >= 90 or ex["net"] <= 0:
        print("\n  VERDICT: ARTIFACT — do NOT queue. The profit is the tail, not the strategy.")
        sys.exit(1)
    if share >= 50:
        print("\n  VERDICT: CONCENTRATED — queueable, but say the top-10 share out loud on the card.")
    else:
        print("\n  VERDICT: SPREAD — profit is distributed across the trade list.")


if __name__ == "__main__":
    main()
