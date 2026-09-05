"""
PRE-REGISTERED sweep of NQDIP 1.1 (the frequency lever): NQ 5m RTH, 2010-06-07..2025-06-29
(the lockbox after that is never loaded), cost_pts 0 / mult 1 (sizing+costs live in the plugin).
Cells, fixed before any result:
  P0  NQDIP 1.0 defaults (the 4-leg reference; must equal run-#307-file parity n=629/$333,424)
  P1  1.1 defaults, all 7 legs
  IBS alone     : ibs_thr {0.15,0.2,0.25} x ibs_exit {0.6,0.7,0.8} x ibs_hold {3,5,7}  = 27
  STREAK alone  : streak_n {2,3,4,5} x streak_hold {3,5,8}                             = 12
  GAPDN alone   : gap_atr {0.25,0.5,0.75,1.0} x gap_hold {1,2,3,5}                     = 16
  P2  7 legs with each new leg at its best-R/YR single-leg setting (one look, reported as such)
Figures per cell come from the engine result (run_backtest attaches win_rate, expectancy_r,
sharpe, sortino, avg_loss, trades_per_year when return_trades is on). R/YR = expectancy_r x
trades_per_year. Also an 8-slice chronological consistency count (positive slices) for the
reference books and the best single-leg cell of each new leg.
"""
import os, sys, csv, itertools
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")


def defaults(fn):
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", fn)); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


ARR = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
YEARS = (ARR["index"][-1] - ARR["index"][0]).days / 365.25


def cell(fn, params):
    r = run_backtest(fn, arrays=ARR, params=params, cost_pts=0.0, return_trades=True)
    if not r:
        return None
    n = r["num_trades"]; net = r["total_pnl"]; dd = -r["max_drawdown"]
    tpy = r.get("trades_per_year") or (n / YEARS)
    evr = r.get("expectancy_r")
    if evr is None:
        w = r["win_rate"] / 100.0; evr = (1 - w) * (r["profit_factor"] - 1)
    return dict(n=n, net=round(net), pf=round(r["profit_factor"], 3), dd=round(dd), mar=round(net / dd, 2) if dd > 0 else 99,
                win=round(r["win_rate"], 1), evr=round(evr, 3), ryr=round(evr * tpy, 1), tpy=round(tpy, 1),
                sh=round(r.get("sharpe") or 0, 2), so=round(r.get("sortino") or 0, 2), avl=round(r.get("avg_loss") or 0),
                trades=r.get("trades"))


def slices8(trades):
    t = sorted(trades, key=lambda z: z[0]); p = np.array([z[2] for z in t]); k = len(p) // 8
    return sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0)


P10 = defaults("NQDIP_1_0.py"); P11 = defaults("NQDIP_1_1.py")
OFFNEW = dict(P11, use_ibs=False, use_streak=False, use_gapdn=False)
rows = []


def add(name, fn, params, folds=False):
    c = cell(fn, params)
    if c is None:
        print(name, "-> no trades"); return None
    f8 = slices8(c["trades"]) if folds else ""
    rec = dict(cell=name, **{k: v for k, v in c.items() if k != "trades"}, folds8=f8)
    rows.append(rec)
    print(f"{name:32} n={c['n']:4} net=${c['net']:>9,} PF={c['pf']:.3f} DD=${c['dd']:>7,} MAR={c['mar']:>6.2f} win={c['win']:5.1f} EVR={c['evr']:.3f} R/YR={c['ryr']:6.1f} tpy={c['tpy']:5.1f} folds+ {f8}", flush=True)
    return rec


ref10 = add("P0 NQDIP_1_0 defaults", "NQDIP_1_0.py", P10, folds=True)
par = add("P0b NQDIP_1_1 new legs OFF (parity)", "NQDIP_1_1.py", OFFNEW, folds=True)
assert ref10 and par and ref10["n"] == par["n"] and ref10["net"] == par["net"], "PARITY FAIL: 1.1 with new legs off != 1.0"
print("PARITY OK\n")
add("P1 NQDIP_1_1 defaults, 7 legs", "NQDIP_1_1.py", P11, folds=True)
solo = dict(P11, use_rsi=False, use_dbl=False, use_pb=False, use_cap=False)
best = {}
for thr, ex, hold in itertools.product((0.15, 0.2, 0.25), (0.6, 0.7, 0.8), (3, 5, 7)):
    r = add(f"IBS thr{thr}/exit{ex}/hold{hold}", "NQDIP_1_1.py", dict(solo, use_ibs=True, use_streak=False, use_gapdn=False, ibs_thr=thr, ibs_exit=ex, ibs_hold=hold))
    if r and (("IBS" not in best) or r["ryr"] > best["IBS"][0]["ryr"]): best["IBS"] = (r, dict(ibs_thr=thr, ibs_exit=ex, ibs_hold=hold))
for sn, sh in itertools.product((2, 3, 4, 5), (3, 5, 8)):
    r = add(f"STREAK n{sn}/hold{sh}", "NQDIP_1_1.py", dict(solo, use_ibs=False, use_streak=True, use_gapdn=False, streak_n=sn, streak_hold=sh))
    if r and (("STREAK" not in best) or r["ryr"] > best["STREAK"][0]["ryr"]): best["STREAK"] = (r, dict(streak_n=sn, streak_hold=sh))
for ga, gh in itertools.product((0.25, 0.5, 0.75, 1.0), (1, 2, 3, 5)):
    r = add(f"GAPDN atr{ga}/hold{gh}", "NQDIP_1_1.py", dict(solo, use_ibs=False, use_streak=False, use_gapdn=True, gap_atr=ga, gap_hold=gh))
    if r and (("GAPDN" not in best) or r["ryr"] > best["GAPDN"][0]["ryr"]): best["GAPDN"] = (r, dict(gap_atr=ga, gap_hold=gh))
print("\nbest single-leg settings by R/YR:", {k: v[1] for k, v in best.items()})
p2 = dict(P11)
for k, v in best.items():
    p2.update(v[1])
add("P2 7 legs, new legs at best single-leg settings (one look)", "NQDIP_1_1.py", p2, folds=True)
for k, v in best.items():
    add(f"P3 best {k} alone (folds)", "NQDIP_1_1.py", dict(solo, **{"use_ibs": k == "IBS", "use_streak": k == "STREAK", "use_gapdn": k == "GAPDN"}, **v[1]), folds=True)
os.makedirs("tools/r16_results", exist_ok=True)
with open("tools/r16_results/sweep_nqdip11.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("\nsaved tools/r16_results/sweep_nqdip11.csv")
print("\nTOP 12 by R/YR:")
for r in sorted(rows, key=lambda z: -z["ryr"])[:12]:
    print(f"  {r['cell']:32} R/YR {r['ryr']:6.1f} EVR {r['evr']:.3f} PF {r['pf']:.2f} n {r['n']} MAR {r['mar']}")
