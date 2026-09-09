"""
ROUND 47 — is the ENGU-Q ES leg's RECENT strength real, or a handful of trades? (2026-09-09)

Round 46 reported that this leg earns profit factor 1.59 and 357 dollars a trade over 2024-2026
against 1.24 and 66 dollars over 2010-2023, and called that a pass on the recency test. That claim
has an obvious failure mode this house has been burned by before: the EV R record that turned out to
be ten trades, and the GAPGO family that passed six gates and lost its sealed year. A stretch with
only 236 trades and a much larger average trade is exactly where a few tails hide.

So this file applies the concentration test to the RECENT STRETCH SPECIFICALLY, not just the whole
window: the top-10 share of that stretch's net, what is left after removing those ten, and how few
trades make up half the profit. Same read for the older stretch and for the crowned NQ leg, so the
recent numbers have something to be judged against.

Costs: NQ 0.783 a round trip at 20 dollars a point; ES 0.60 (honest fills) at 50. Window is the
ENGU-Q crown window 2010-06-07..2026-06-30; the last twelve months are the sealed year the two
running ES validates are grading, so they are already-read rather than fresh evidence.
"""
import os, sys, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

FN = "augur_strategies/ENGUQ_1M_ETH_R2_1_0.py"
sp = ilu.spec_from_file_location("m", FN); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
P = {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}
ROWS = []


def report(label, p):
    p = np.asarray(p, float)
    if len(p) == 0:
        print(f"{label:26} no trades"); return
    net = float(p.sum()); gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gw / gl if gl else 99
    srt = np.array(sorted(p, reverse=True))
    top10 = float(srt[:10].sum()); ex = srt[10:]
    exnet = float(ex.sum()); exgw = ex[ex > 0].sum(); exgl = -ex[ex < 0].sum()
    expf = exgw / exgl if exgl else 99
    # how few winners make up half the net
    wins = srt[srt > 0]; c = np.cumsum(wins)
    half = int(np.searchsorted(c, net / 2.0) + 1) if net > 0 else 0
    share = 100 * top10 / net if net else float("inf")
    ROWS.append(dict(stretch=label, n=len(p), net=round(net), pf=round(pf, 3),
                     top10_pct=round(share), exnet=round(exnet), expf=round(expf, 3),
                     n_for_half=half, pct_for_half=round(100 * half / len(p), 1)))
    print(f"{label:26} n={len(p):5} net=${net:>9,.0f} PF={pf:5.3f} | top-10 = {share:5.1f}% of net | "
          f"ex-top-10 ${exnet:>9,.0f} PF {expf:5.3f} | half the profit from {half:3} trades ({100*half/len(p):4.1f}%)")


for inst, cost, mult in (("NQ", 0.783, 20.0), ("ES", 0.60, 50.0)):
    A = load_master_arrays(find_master(inst, "1m", "eth", "db_noadj_eth"),
                           date_from="2010-06-07", date_to="2026-06-30")
    idx = pd.DatetimeIndex(A["index"])
    r = run_backtest(FN, arrays=A, params=P, cost_pts=cost, return_trades=True)
    df = pd.DataFrame({"t": [idx[t[0]] for t in r["trades"]], "pnl": [t[2] * mult for t in r["trades"]]})
    print(f"\n=== {inst} at {cost} a round trip (${cost*mult:.0f}) ===")
    report(f"{inst} whole window", df.pnl.values)
    report(f"{inst} 2010-2023", df[df.t.dt.year <= 2023].pnl.values)
    report(f"{inst} 2024-2026 (recent)", df[df.t.dt.year >= 2024].pnl.values)
    rec = df[df.t.dt.year >= 2024].sort_values("pnl", ascending=False)
    print(f"  {inst} recent stretch, ten biggest trades:")
    for _, row in rec.head(10).iterrows():
        print(f"      {row.t.date()}  ${row.pnl:>10,.0f}")
with open("tools/r16_results/r47_enguq_es_recent_concentration.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r47_enguq_es_recent_concentration.csv")
