"""
R / YR-objective random search over a strategy file's OWN declared ranges (owner 2026-09-04:
beat everything on EV R and R / YR). The app's Auto-Validate crowns on its MAR-floor rule,
so the R / YR frontier of a family sits uncrowned inside its populations; this samples the
declared space directly and scores every config on the owner metric, walk-forward-checked.

Pre-registered protocol (same for every family this is run on):
  window   2010-06-07 .. 2025-06-29 (the lockbox after that is never loaded)
  sampling uniform over each knob's declared [min, max] on its step (str: its options,
           bool: both), fixed knobs (min == max) kept; seed fixed
  figures  from the engine (run_backtest attaches win_rate / expectancy_r / sharpe /
           sortino / avg_loss / trades_per_year when return_trades is on)
  score    R / YR = expectancy_r x trades_per_year; also EV R
  gates    PF >= 1.25, n >= n_floor, 8-slice chronological consistency >= 6/8
  output   tools/r16_results/ryr_search_<tag>.csv + the top table

usage: python tools/ryr_search.py <strategy.py> <inst> <tf> <session> <source> <cost_pts> <mult> <n_configs> <workers> <tag> [n_floor]
"""
import os, sys, csv, time, random
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from multiprocessing import Pool
import importlib.util as ilu

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
_ARR = None
_CFG = {}


def load_params(fn):
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", fn)); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return m.DEFAULT_PARAMS


def sample(dp, rng):
    p = {}
    for k, v in dp.items():
        t = v.get("type")
        if t == "bool":
            p[k] = bool(rng.random() < 0.5) if v.get("min") is None else bool(v["default"])
        elif t == "str":
            opts = v.get("options") or [v["default"]]
            p[k] = rng.choice(opts)
        else:
            lo, hi, st = v.get("min", v["default"]), v.get("max", v["default"]), v.get("step") or 1
            if lo == hi:
                p[k] = v["default"]; continue
            k_steps = int(round((hi - lo) / st))
            x = lo + st * rng.randint(0, max(k_steps, 0))
            p[k] = int(round(x)) if t == "int" else round(float(x), 6)
    return p


def _init(cfg):
    global _ARR, _CFG
    _CFG = cfg
    from augur_engine.data import find_master, load_master_arrays
    _ARR = load_master_arrays(find_master(cfg["inst"], cfg["tf"], cfg["session"], cfg["source"]), **WIN)


def one(params):
    from augur_engine.engine import run_backtest
    t0 = time.time()
    try:
        r = run_backtest(_CFG["fn"], arrays=_ARR, params=params, cost_pts=_CFG["cost"], return_trades=True)
    except Exception as e:
        return dict(params=params, n=0, err=str(e)[:80])
    if not r or not r.get("trades"):
        return dict(params=params, n=0)
    tr = sorted(r["trades"], key=lambda z: z[0]); p = np.array([t[2] for t in tr]); k = len(p) // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k > 0 else 0
    yrs = (_ARR["index"][-1] - _ARR["index"][0]).days / 365.25
    n = r["num_trades"]; M = _CFG["mult"]; net = r["total_pnl"] * M; dd = -r["max_drawdown"] * M
    w = r["win_rate"] / 100.0; evr = r.get("expectancy_r")
    if evr is None:
        evr = (1 - w) * (r["profit_factor"] - 1)
    tpy = r.get("trades_per_year") or n / yrs
    return dict(params=params, n=n, net=round(net), pf=round(r["profit_factor"], 3), dd=round(dd),
                mar=round(net / dd, 2) if dd > 0 else 99, win=round(r["win_rate"], 1), evr=round(evr, 3),
                ryr=round(evr * tpy, 1), tpy=round(tpy, 1), sh=round(r.get("sharpe") or 0, 2),
                so=round(r.get("sortino") or 0, 2), avl=round((r.get("avg_loss") or 0) * M), folds8=folds,
                secs=round(time.time() - t0))


if __name__ == "__main__":
    fn, inst, tf, sess, src, cost, mult, ncfg, workers, tag = sys.argv[1:11]
    n_floor = int(sys.argv[11]) if len(sys.argv) > 11 else 300
    cfg = dict(fn=fn, inst=inst, tf=tf, session=sess, source=src, cost=float(cost), mult=float(mult))
    dp = load_params(fn); rng = random.Random(27)
    grid = [{k: v["default"] for k, v in dp.items()}] + [sample(dp, rng) for _ in range(int(ncfg) - 1)]
    print(f"{fn} on {inst} {tf} {sess} {src}: {len(grid)} configs, {workers} workers, cost {cost}, mult {mult}", flush=True)
    t0 = time.time()
    with Pool(processes=int(workers), initializer=_init, initargs=(cfg,)) as pool:
        res = pool.map(one, grid, chunksize=1)
    print(f"done in {(time.time()-t0)/60:.1f} min", flush=True)
    rows = [dict(rank=0, **{k: v for k, v in x.items() if k != "params"}, params=str(x["params"])) for x in res]
    for i, x in enumerate(sorted(rows, key=lambda z: -(z.get("ryr") or -99))):
        x["rank"] = i + 1
    rows.sort(key=lambda z: z["rank"])
    os.makedirs("tools/r16_results", exist_ok=True)
    out = f"tools/r16_results/ryr_search_{tag}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    ok = [x for x in rows if x.get("n", 0) >= n_floor and (x.get("pf") or 0) >= 1.25 and (x.get("folds8") or 0) >= 6]
    print(f"\nconfigs evaluated: {len(rows)} | pass gates (PF>=1.25, n>={n_floor}, folds>=6/8): {len(ok)}")
    print(f"{'rk':>3} {'R/YR':>6} {'EVR':>5} {'n':>5} {'tpy':>6} {'PF':>5} {'win%':>5} {'net$':>10} {'DD$':>8} {'MAR':>5} f8  params")
    for x in ok[:15]:
        print(f"{x['rank']:>3} {x['ryr']:6.1f} {x['evr']:5.2f} {x['n']:5} {x['tpy']:6.1f} {x['pf']:5.2f} {x['win']:5.1f} {x['net']:>10,} {x['dd']:>8,} {x['mar']:5.1f} {x['folds8']}  {x['params']}")
    print("\ndefault config:", next((x for x in rows if x['params'] == str(grid[0])), None) and {k: v for k, v in next(x for x in rows if x['params'] == str(grid[0])).items() if k in ('ryr', 'evr', 'n', 'pf', 'mar', 'folds8')})
    print("saved", out)
