"""
ROUND 38b (2026-09-08) - cost-stress re-score of every gate-passing NOISE 2m search cell.

Owner: "$10 seems high round trip but idk." The house cost is 0.533 NQ points a round trip
($10.66 at $20/pt: roughly two ticks plus commissions). A 2-minute scalp earns ~$40 a trade, so
the question is not whether $10.66 is right but how fast the edge dies if the real cost is
higher. This re-runs the 74 configs that passed the round-37 gates (PF >= 1.25, n >= 300,
6-of-8 slices at 0.533) at 0.533 / 0.783 / 1.033 pts and ranks them by net-over-drawdown at
0.783 - the cost-robust corner of the 2m space, not the cost-flattered one.

    python tools/r38_noise2m_cost_stress.py   -> tools/r37_results/noise2m_cost_stress.csv
"""
import os, sys, csv, ast, time
import numpy as np
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
DATA_REPO = ROOT if os.path.exists(os.path.join(ROOT, "optimizer_history.db")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, DATA_REPO)
SRC = os.path.join(HERE, "r37_results", "ryr_search_noise2m.csv")
OUT = os.path.join(HERE, "r37_results", "noise2m_cost_stress.csv")
COSTS = (0.533, 0.783, 1.033)
_A = None


def _init():
    global _A
    from augur_engine.data import find_master, load_master_arrays
    _A = load_master_arrays(find_master("NQ", "2m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2025-06-29")


def one(item):
    rank, params = item
    from augur_engine.engine import run_backtest
    out = {"rank": rank}
    for cost in COSTS:
        r = run_backtest("NOISE_1_0.py", arrays=_A, params=params, cost_pts=cost, return_trades=True)
        tr = sorted(r["trades"], key=lambda z: z[0]); p = np.array([t[2] for t in tr]) * 20; k = len(p) // 8
        f = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0)
        cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min()); net = p.sum(); w = (p > 0).mean(); pf = r["profit_factor"]
        srt = sorted(p, reverse=True); top = 100 * sum(srt[:10]) / net if net > 0 else 999
        tag = str(cost).replace('.', '')
        out.update({f"net_{tag}": round(net), f"pf_{tag}": round(float(pf), 3), f"dd_{tag}": round(-dd),
                    f"mar_{tag}": round(net / -dd, 2) if dd < 0 else 99, f"ryr_{tag}": round((1 - w) * (pf - 1) * len(p) / 15.06, 1),
                    f"f8_{tag}": f, f"top10_{tag}": round(top), f"per_{tag}": round(net / len(p), 1)})
    out["n"] = len(p); out["params"] = str(params)
    return out


if __name__ == "__main__":
    t0 = time.time()
    rows = [r for r in csv.DictReader(open(SRC)) if int(r['n']) >= 300 and float(r['pf']) >= 1.25 and int(r['folds8']) >= 6]
    items = [(int(r['rank']), ast.literal_eval(r['params'])) for r in rows]
    print("%d gate-passing configs, costs %s" % (len(items), COSTS), flush=True)
    with Pool(6, initializer=_init) as pool:
        res = pool.map(one, items, chunksize=1)
    res.sort(key=lambda z: -z["mar_0783"])
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    print("rank  n    | 0.533: MAR  R/YR f8 top | 0.783: MAR  R/YR f8 $/tr | 1.033: MAR  R/YR f8 | geometry")
    for x in res[:14]:
        P = ast.literal_eval(x["params"])
        print(f"{x['rank']:>4} {x['n']:>5} | {x['mar_0533']:5.1f} {x['ryr_0533']:6.1f} {x['f8_0533']} {x['top10_0533']:3d}% | "
              f"{x['mar_0783']:5.1f} {x['ryr_0783']:6.1f} {x['f8_0783']} {x['per_0783']:5.1f} | {x['mar_1033']:5.1f} {x['ryr_1033']:6.1f} {x['f8_1033']} | "
              f"{P['exit_mode']}/{P['stop_mode']}{P['stop_k']}/{P['side']}/{P['window']}/conf{P['confirm_bars']}/lb{P['lookback']}/b{P['band_mult_long']}-{P['band_mult_short']}/dt{P['daytype_mode']}/vs{P['vol_skip_pct']}")
    print("survivors at 0.783 (PF>=1.25, MAR>=8, 6/8):", sum(1 for x in res if x['pf_0783'] >= 1.25 and x['mar_0783'] >= 8 and x['f8_0783'] >= 6),
          "| at 1.033:", sum(1 for x in res if x['pf_1033'] >= 1.25 and x['mar_1033'] >= 8 and x['f8_1033'] >= 6))
    print("saved", OUT, "%.1f min" % ((time.time() - t0) / 60), flush=True)
