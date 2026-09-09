"""
ROUND 42 — the cost ladder on the ES-picked NOISE configuration (2026-09-09).

Round 40 showed one configuration - chosen by searches that only ever read ES bars - clears the house
bar on ES at 5/15/30-minute bars and on NQ at all four, tying the NQ crown. The dimension it has NOT
been stressed on is COST, and a sibling's round-41 bar ladder showed cost is exactly where NOISE
configurations die (R/YR flatters short bars because it rises mechanically with trade count).

So: the same configuration, unchanged, at three round-trip costs per instrument.
  NQ ($20/pt): 0.533 house · 0.783 stressed ($15.66) · 1.033 punitive ($20.66) - the sibling's ladder costs
  ES ($50/pt): 0.30 house ($15) · 0.50 ($25) · 0.70 ($35)
House bar on every cell: PF >= 1.25, net/DD >= 8, n >= 300, >= 6 of 8 slices, top-10 share < 90%
with a positive ex-top-10 net. Window 2010-06-07..2025-06-29, lockbox never loaded.

The configuration is read VERBATIM from the search file, never retyped from a console line (round-40
lesson), and any pooled drawdown here would be sorted first (round-41 lesson) - there is no pooling.
"""
import os, sys, csv, ast
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

CSV = "tools/r16_results/ryr_search_noise_es5m.csv"
rows = [r for r in csv.DictReader(open(CSV)) if int(r["n"] or 0) > 0]
LEADER = ast.literal_eval(max([r for r in rows if float(r["pf"]) >= 1.25 and int(r["folds8"]) >= 6],
                              key=lambda r: float(r["ryr"]))["params"])
print("leader (verbatim from %s):\n  %s\n" % (CSV, LEADER), flush=True)
WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
OUT = []


def read(inst, tf, cost, mult):
    A = load_master_arrays(find_master(inst, tf, "rth", "db_noadj_rth"), **WIN)
    r = run_backtest("augur_strategies/NOISE_1_0.py", arrays=A, params=dict(LEADER), cost_pts=cost, return_trades=True)
    if not r or not r.get("trades"):
        print(f"{inst} {tf:4} cost {cost:.3f}  no trades"); return
    p = np.array([t[2] * mult for t in r["trades"]]); n = len(p)
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl else 99
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min()); net = float(p.sum())
    w = float((p > 0).mean()); k = n // 8
    f8 = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else n].sum() > 0) if k else 0
    srt = sorted(p, reverse=True); top = sum(srt[:10]); ex = np.array(srt[10:])
    exnet = float(ex.sum())
    mar = net / -dd if dd < 0 else 99
    top10 = round(100 * top / net) if net > 0 else 999
    ok = pf >= 1.25 and mar >= 8 and n >= 300 and top10 < 90 and exnet > 0
    OUT.append(dict(inst=inst, tf=tf, cost=cost, dollars=round(cost * mult, 2), n=n, net=round(net),
                    pf=round(pf, 3), dd=round(-dd), mar=round(mar, 2), win=round(100 * w, 1),
                    f8=f8, top10=top10, exnet=round(exnet), per_trade=round(net / n, 2), passes=ok))
    print(f"{inst} {tf:4} cost {cost:.3f} (${cost*mult:5.2f}/RT)  n={n:5} net=${net:>9,.0f} PF={pf:.3f} "
          f"DD=${-dd:>8,.0f} n/DD={mar:6.2f} f8={f8} top10={top10:>3}% ex=${exnet:>9,.0f} "
          f"${net/n:6.2f}/trade  {'PASS' if ok else 'fail'}", flush=True)


for tf in ("5m", "15m", "30m"):
    for cost in (0.30, 0.50, 0.70):
        read("ES", tf, cost, 50.0)
    print()
for tf in ("5m", "15m", "30m"):
    for cost in (0.533, 0.783, 1.033):
        read("NQ", tf, cost, 20.0)
    print()
with open("tools/r16_results/r42_es_config_cost_ladder.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(OUT[0].keys())); w.writeheader()
    for r in OUT: w.writerow(r)
p_es = sum(1 for r in OUT if r["inst"] == "ES" and r["passes"]); n_es = sum(1 for r in OUT if r["inst"] == "ES")
p_nq = sum(1 for r in OUT if r["inst"] == "NQ" and r["passes"]); n_nq = sum(1 for r in OUT if r["inst"] == "NQ")
print(f"ES {p_es}/{n_es} cells clear the full house bar · NQ {p_nq}/{n_nq}")
print("saved tools/r16_results/r42_es_config_cost_ladder.csv")
