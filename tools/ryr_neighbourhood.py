"""
Neighbourhood check around an R / YR search leader: is it a PLATEAU or a SPIKE?

A random search reports its best cell; that cell is flattered by the search itself.
This walks each ranged knob one step either side of the leader (all other knobs held),
so a leader whose neighbours collapse is a spike and must not be validated.

usage: python tools/ryr_neighbourhood.py <tag> <strategy.py> <inst> <tf> <sess> <src> <cost> <mult> <workers>
       reads the leader from tools/r16_results/ryr_search_<tag>.csv (rank 1 by R / YR
       among rows passing that file's gates), writes ryr_nb_<tag>.csv.
"""
import os, sys, csv, ast, time
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from multiprocessing import Pool
import importlib.util as ilu

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
_ARR = None; _CFG = {}


def _init(cfg):
    global _ARR, _CFG
    _CFG = cfg
    from augur_engine.data import find_master, load_master_arrays
    _ARR = load_master_arrays(find_master(cfg["inst"], cfg["tf"], cfg["session"], cfg["source"]), **WIN)


def one(item):
    label, params = item
    from augur_engine.engine import run_backtest
    try:
        r = run_backtest(_CFG["fn"], arrays=_ARR, params=params, cost_pts=_CFG["cost"], return_trades=True)
    except Exception as e:
        return dict(label=label, n=0, err=str(e)[:60])
    if not r or not r.get("trades"):
        return dict(label=label, n=0)
    tr = sorted(r["trades"], key=lambda z: z[0]); p = np.array([t[2] for t in tr]); k = len(p) // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k else 0
    yrs = (_ARR["index"][-1] - _ARR["index"][0]).days / 365.25
    M = _CFG["mult"]; n = r["num_trades"]; net = r["total_pnl"] * M; dd = -r["max_drawdown"] * M
    w = r["win_rate"] / 100.0
    evr = r.get("expectancy_r") if r.get("expectancy_r") is not None else (1 - w) * (r["profit_factor"] - 1)
    tpy = r.get("trades_per_year") or n / yrs
    return dict(label=label, n=n, net=round(net), pf=round(r["profit_factor"], 3), dd=round(dd),
                mar=round(net / dd, 2) if dd > 0 else 99, win=round(r["win_rate"], 1), evr=round(evr, 3),
                ryr=round(evr * tpy, 1), tpy=round(tpy, 1), folds8=folds,
                sh=round(r.get("sharpe") or 0, 2), so=round(r.get("sortino") or 0, 2),
                avl=round((r.get("avg_loss") or 0) * M))


if __name__ == "__main__":
    tag, fn, inst, tf, sess, src, cost, mult, workers = sys.argv[1:10]
    cfg = dict(fn=fn, inst=inst, tf=tf, session=sess, source=src, cost=float(cost), mult=float(mult))
    rows = [r for r in csv.DictReader(open(f"tools/r16_results/ryr_search_{tag}.csv")) if int(r["n"] or 0) > 0]
    lead = max(rows, key=lambda r: float(r["ryr"]))
    base = ast.literal_eval(lead["params"])
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", fn)); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    dp = m.DEFAULT_PARAMS
    print(f"leader R/YR {lead['ryr']} EVR {lead['evr']} PF {lead['pf']} n {lead['n']} folds {lead['folds8']}")
    print("params:", base, flush=True)
    jobs = [("LEADER", dict(base))]
    for k, v in dp.items():
        t = v.get("type")
        if t == "str":
            for o in (v.get("options") or []):
                if o != base.get(k):
                    jobs.append((f"{k}={o}", dict(base, **{k: o})))
        elif t == "bool":
            jobs.append((f"{k}={not base.get(k)}", dict(base, **{k: (not base.get(k))})))
        else:
            lo, hi, st = v.get("min"), v.get("max"), v.get("step") or 1
            if lo is None or lo == hi:
                continue
            cur = base.get(k, v["default"])
            for d in (-1, 1):
                x = cur + d * st
                if lo <= x <= hi:
                    x = int(round(x)) if t == "int" else round(float(x), 6)
                    jobs.append((f"{k}={x}", dict(base, **{k: x})))
    print(f"{len(jobs)} neighbour cells", flush=True)
    t0 = time.time()
    with Pool(processes=int(workers), initializer=_init, initargs=(cfg,)) as pool:
        res = pool.map(one, jobs, chunksize=1)
    print(f"done in {(time.time()-t0)/60:.1f} min\n", flush=True)
    with open(f"tools/r16_results/ryr_nb_{tag}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    good = [x for x in res if x.get("n")]
    lead_row = next(x for x in res if x["label"] == "LEADER")
    nb = [x for x in good if x["label"] != "LEADER"]
    ryrs = sorted(x["ryr"] for x in nb)
    print(f"LEADER    R/YR {lead_row['ryr']:6.1f} EVR {lead_row['evr']:.2f} PF {lead_row['pf']:.2f} n {lead_row['n']} MAR {lead_row['mar']} folds {lead_row['folds8']}/8")
    print(f"neighbours: {len(nb)} | median R/YR {np.median(ryrs):.1f} | 25th {np.percentile(ryrs,25):.1f} | min {min(ryrs):.1f} | max {max(ryrs):.1f}")
    print(f"  neighbours holding R/YR >= 50% of leader: {sum(1 for x in nb if x['ryr'] >= 0.5*lead_row['ryr'])}/{len(nb)}")
    print(f"  neighbours with PF >= 1.25: {sum(1 for x in nb if x['pf'] >= 1.25)}/{len(nb)}  | folds >= 6: {sum(1 for x in nb if x['folds8'] >= 6)}/{len(nb)}")
    print(f"\nworst 8 neighbours:")
    for x in sorted(nb, key=lambda z: z["ryr"])[:8]:
        print(f"  {x['label']:26} R/YR {x['ryr']:6.1f} PF {x['pf']:5.2f} n {x['n']:5} MAR {x['mar']:6.1f} folds {x['folds8']}")
    print(f"\nbest 8 neighbours:")
    for x in sorted(nb, key=lambda z: -z["ryr"])[:8]:
        print(f"  {x['label']:26} R/YR {x['ryr']:6.1f} PF {x['pf']:5.2f} n {x['n']:5} MAR {x['mar']:6.1f} folds {x['folds8']}")
    print("\nsaved tools/r16_results/ryr_nb_%s.csv" % tag)
