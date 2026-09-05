"""
PRE-REGISTERED sweep — EMAPB 1.0 (1m EMA-pullback continuation) on NQ 1m RTH.
Window 2010-06-07..2025-06-29 (lockbox after that never loaded). cost_pts 0.533, $20/pt.
Grid (whole grid): ema_fast {10,20,40} x ema_slow {50,100,200} x stop_mult {0.75,1.0,1.5}
                   x be_R {1.0} x trail_atr {1.0} x max_trades_per_day {6} = 27 cells.
Bar to report against (not tuned to): PF >= 1.25, MAR >= 8, n >= 300; R/YR reference ~50-60
(ENGU-Q family single-strategy leaders). 8 workers via multiprocessing; each worker runs
the engine itself and returns the engine's own attached risk figures.
"""
import os, sys, csv, itertools, time
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from multiprocessing import Pool
import importlib.util as ilu

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
MULT = 20.0


def defaults():
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", "EMAPB_1_0.py")); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


_ARR = None


def _init():
    global _ARR
    from augur_engine.data import find_master, load_master_arrays
    _ARR = load_master_arrays(find_master("NQ", "1m", "rth", "db_noadj_rth"), **WIN)


def one(params):
    from augur_engine.engine import run_backtest
    t0 = time.time()
    r = run_backtest("EMAPB_1_0.py", arrays=_ARR, params=params, cost_pts=0.533, return_trades=True)
    if not r:
        return dict(params=params, n=0)
    p = np.array([t[2] for t in r["trades"]]); k = len(p) // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k > 0 else 0
    yrs = (_ARR["index"][-1] - _ARR["index"][0]).days / 365.25
    n = r["num_trades"]; net = r["total_pnl"] * MULT; dd = -r["max_drawdown"] * MULT
    evr = r.get("expectancy_r"); w = r["win_rate"] / 100
    if evr is None:
        evr = (1 - w) * (r["profit_factor"] - 1)
    tpy = r.get("trades_per_year") or n / yrs
    return dict(params=params, n=n, net=round(net), pf=round(r["profit_factor"], 3), dd=round(dd),
                mar=round(net / dd, 2) if dd > 0 else 99, win=round(r["win_rate"], 1), evr=round(evr, 3),
                ryr=round(evr * tpy, 1), tpy=round(tpy, 1), sh=round(r.get("sharpe") or 0, 2),
                so=round(r.get("sortino") or 0, 2), avl=round((r.get("avg_loss") or 0) * MULT), folds8=folds,
                secs=round(time.time() - t0))


if __name__ == "__main__":
    D = defaults()
    # smoke on 3 months first
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    A = load_master_arrays(find_master("NQ", "1m", "rth", "db_noadj_rth"), date_from="2024-01-01", date_to="2024-03-31")
    r = run_backtest("EMAPB_1_0.py", arrays=A, params=D, cost_pts=0.533, return_trades=True)
    print("smoke 2024Q1:", None if not r else {k: (round(r[k], 3) if isinstance(r[k], float) else r[k]) for k in ("num_trades", "total_pnl", "profit_factor", "win_rate")}, flush=True)
    grid = [dict(D, ema_fast=a, ema_slow=b, stop_mult=s) for a, b, s in itertools.product((10, 20, 40), (50, 100, 200), (0.75, 1.0, 1.5))]
    t0 = time.time()
    with Pool(processes=8, initializer=_init) as pool:
        res = pool.map(one, grid)
    print(f"sweep done in {time.time()-t0:.0f}s\n", flush=True)
    rows = []
    for x in sorted(res, key=lambda z: -z.get("ryr", -9)):
        p = x["params"]; cellname = f"f{p['ema_fast']}/s{p['ema_slow']}/stop{p['stop_mult']}"
        rows.append(dict(cell=cellname, **{k: v for k, v in x.items() if k != "params"}))
        if x.get("n"):
            print(f"{cellname:22} n={x['n']:5} net=${x['net']:>10,} PF={x['pf']:.3f} DD=${x['dd']:>8,} MAR={x['mar']:>6.2f} win={x['win']:5.1f} EVR={x['evr']:.3f} R/YR={x['ryr']:6.1f} tpy={x['tpy']:6.1f} folds+ {x['folds8']}/8  ({x['secs']}s)")
        else:
            print(f"{cellname:22} no trades")
    os.makedirs("tools/r16_results", exist_ok=True)
    with open("tools/r16_results/sweep_emapb.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("saved tools/r16_results/sweep_emapb.csv")
