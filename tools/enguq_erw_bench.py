"""
ENGU-Q ETH efficiency-floor x wide-exit stack -- bench driver (worktree enguq-erw).

QUESTION: does stacking the efficiency floor (run #265: er_len 60, er_th 0.25 on the
#226 config -> PF 1.33 -> 1.60) with the #310 limit-full-discovery "let it run" exit
structure (trail_frac 4.0, act_R 3.0, stop_mult 1.7, limit_atr 0.7, regime_len 5 ->
PF 2.22 but only 538 trades, weak lockbox PF 1.24/91) COMPOUND, or does the floor's
edge already live inside the trades the wide exit catches (i.e. no incremental gain
from stacking)?

PRE-REGISTERED BARS (all four must pass for PROMISING; parent = #265: PF 1.597,
n=1336, EV R 0.44, R/YR 36.6, held-out(LB, entries>=2025-06-30) 67 trades):
  1. full-window PF > 1.597 (parent PF, same window/costs)
  2. the PF gain holds in >= 3 of 4 eras (2010-14, 14-18, 18-22, 22+)
  3. >= 40 trades in the held-out year (2025-06-30..2026-06-30)
  4. EV R AND R/YR both above the parent's (EV R 0.44 / R/YR 36.6)
PRIMARY cell (declared before running): trail_frac=4.0, act_R=3.0, er_th=0.25,
limit_atr=0.0, stop_mult=1.0 (all-else #265 default) -- the cleanest single-knob
read of "does widening the trail alone, on top of the floor, help".

PARITY ANCHORS (printed before the grid; must pass before any bench cell is trusted):
  - ALL DEFAULTS (er_th=0.25, exits at #265 values) on window 2010-06-07..2026-06-30,
    NQ 1m ETH db_noadj_eth, cost 0.533 x $20 -> n=1336, net $486,413.24, PF 1.597,
    held-out (entries>=2025-06-30) n=67, $146,230.78.
  - er_th=0.0 (gate off) -> n=2843, net $434,721.12 (#226 parity).

Bench grid (<=16 in-engine runs, all on the #265 base unless noted):
  A) trail_frac in {2.5, 4.0, 5.0} x act_R in {2.5, 3.0}, er_th=0.25          (6 cells)
  B) #310-style cell (stop_mult 1.7, trail_frac 4.0, act_R 3.0, breakeven 1.5,
     limit_atr in {0.0, 0.7}) x er_th in {0.25, 0.0}                          (4 cells)
Total 10 engine runs + 2 parity runs = 12.
"""
import sys
import json
import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\enguq-erw"
sys.path.insert(0, REPO)
SCR = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15\scratchpad")

import augur_engine.paths as _paths
import augur_engine.data as _data
_SHARED_ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
_SHARED_DB = _SHARED_ROOT + r"\optimizer_history.db"
_SHARED_UPLOADS = _SHARED_ROOT + r"\augur_uploads"
_paths.DB_PATH = _SHARED_DB
_paths.UPLOADS = _SHARED_UPLOADS
_data.DB_PATH = _SHARED_DB
_data.UPLOADS = _SHARED_UPLOADS
from augur_engine.data import find_master, load_master_arrays
import importlib.util
spec = importlib.util.spec_from_file_location(
    "erw", REPO + r"\augur_strategies\ENGUQ_1M_ETH_ERW_1_0.py")
erw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(erw)

DATE_FROM, DATE_TO = "2010-06-07", "2026-06-30"
COST, MULT = 0.533, 20
LB_START = "2025-06-30"

master = find_master("NQ", "1m", session="eth", source="db_noadj_eth")
arr = load_master_arrays(master, date_from=DATE_FROM, date_to=DATE_TO)
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v = arr.get("volume")
idx = pd.to_datetime(arr["index"])


def run(**params):
    out = erw.run_backtest(o, h, l, c, volumes=v, return_trades=True, **params)
    if out is None or not out.get("trades"):
        return None
    trades = out["trades"]  # (entry_idx, exit_idx, pnl_pts, side, entry_px)
    pnl = np.array([(t[2] - COST) * MULT for t in trades])
    ent = idx[[int(t[0]) for t in trades]]
    n = len(pnl)
    wins = pnl[pnl > 0]; losses = pnl[pnl < 0]
    wr = len(wins) / n
    pf = wins.sum() / max(abs(losses.sum()), 1e-9)
    ev_r = (1 - wr) * (pf - 1)
    years = (idx[-1] - idx[0]).days / 365.25
    tpy = n / years
    r_yr = ev_r * tpy
    lb_ts = pd.Timestamp(LB_START)
    if ent.tz is not None and lb_ts.tzinfo is None:
        lb_ts = lb_ts.tz_localize(ent.tz)
    lb_mask = ent >= lb_ts
    lb_n = int(lb_mask.sum()); lb_net = float(pnl[lb_mask].sum())
    lb_pf = (pnl[lb_mask][pnl[lb_mask] > 0].sum() /
             max(abs(pnl[lb_mask][pnl[lb_mask] < 0].sum()), 1e-9)) if lb_n else float("nan")
    eras = []
    for a, b in (("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
                 ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01")):
        ta, tb = pd.Timestamp(a), pd.Timestamp(b)
        if ent.tz is not None:
            ta = ta.tz_localize(ent.tz); tb = tb.tz_localize(ent.tz)
        m = (ent >= ta) & (ent < tb)
        dd = pnl[m]
        if len(dd) == 0:
            eras.append((a[:4], np.nan, 0))
            continue
        epf = dd[dd > 0].sum() / max(abs(dd[dd < 0].sum()), 1e-9)
        eras.append((a[:4], epf, int(len(dd))))
    return dict(n=n, net=round(float(pnl.sum()), 2), pf=round(float(pf), 3), wr=round(wr * 100, 1),
                ev_r=round(float(ev_r), 3), r_yr=round(float(r_yr), 1),
                lb_n=lb_n, lb_net=round(lb_net, 2), lb_pf=round(float(lb_pf), 3) if lb_n else None,
                eras=eras)


BASE = dict(er_len=60, er_th=0.25, limit_atr=0.0, tl_len=170, vol_mult=0.8, stop_mult=1.0,
            act_R=2.5, trail_frac=2.5, buf_atr=0.9, min_brk=1.3, ema_len=1380, atr_len=106,
            regime_len=0, breakeven_R=1.5)

print("=" * 70)
print("PARITY CHECK 1: all defaults (#265) -- expect n=1336, net $486,413.24, PF 1.597, LB n=67, $146,230.78")
p1 = run(**BASE)
print(p1)
ok1 = (p1 and p1["n"] == 1336 and abs(p1["net"] - 486413.24) < 1.0 and abs(p1["pf"] - 1.597) < 0.005
       and p1["lb_n"] == 67 and abs(p1["lb_net"] - 146230.78) < 1.0)
print("PARITY 1:", "PASS" if ok1 else "FAIL")

print("\nPARITY CHECK 2: er_th=0.0 (gate off) -- expect n=2843, net $434,721.12 (#226 parity)")
p2 = run(**{**BASE, "er_th": 0.0})
print(p2)
ok2 = (p2 and p2["n"] == 2843 and abs(p2["net"] - 434721.12) < 1.0)
print("PARITY 2:", "PASS" if ok2 else "FAIL")

PARENT_PF, PARENT_EVR, PARENT_RYR, PARENT_LB = 1.597, 0.44, 36.6, 67
PARENT_ERAS = {e[0]: e[1] for e in p1["eras"]} if p1 else {}

print("\n" + "=" * 70)
print("BENCH GRID (PRIMARY = trail_frac 4.0 / act_R 3.0 / er_th 0.25 / limit_atr 0.0)")
grid = []
for tf in (2.5, 4.0, 5.0):
    for ar in (2.5, 3.0):
        grid.append(dict(label=f"A trail{tf}_act{ar}_erth.25", primary=(tf == 4.0 and ar == 3.0),
                          params=dict(trail_frac=tf, act_R=ar, er_th=0.25)))
for lim in (0.0, 0.7):
    for erth in (0.25, 0.0):
        grid.append(dict(label=f"B #310cell_lim{lim}_erth{erth}",
                          params=dict(stop_mult=1.7, trail_frac=4.0, act_R=3.0, breakeven_R=1.5,
                                      limit_atr=lim, er_th=erth)))

results = []
for cell in grid:
    params = {**BASE, **cell["params"]}
    res = run(**params)
    results.append((cell["label"], cell.get("primary", False), params, res))
    if res is None:
        print(f"{cell['label']:34s} -> None (no trades)")
        continue
    era_str = " ".join(f"{e[0]}:{e[1]:.2f}" if not np.isnan(e[1]) else f"{e[0]}:n/a" for e in res["eras"])
    print(f"{cell['label']:34s} n={res['n']:5d} net=${res['net']:>12,.0f} PF={res['pf']:.3f} "
          f"WR={res['wr']:.1f}% EV_R={res['ev_r']:.3f} R/YR={res['r_yr']:.1f} "
          f"LB(n={res['lb_n']},PF={res['lb_pf']})  eras[{era_str}]")

print("\n" + "=" * 70)
print("BAR CHECK (parent #265: PF 1.597, EV R 0.44, R/YR 36.6, LB 67 trades)")
verdicts = {}
for label, is_primary, params, res in results:
    if res is None:
        verdicts[label] = "DEAD (no trades)"
        continue
    bar1 = res["pf"] > PARENT_PF
    holds = sum(1 for e in res["eras"]
                if not np.isnan(e[1]) and e[0] in PARENT_ERAS
                and not np.isnan(PARENT_ERAS[e[0]]) and e[1] > PARENT_ERAS[e[0]])
    bar2 = holds >= 3
    bar3 = res["lb_n"] >= 40
    bar4 = (res["ev_r"] > PARENT_EVR) and (res["r_yr"] > PARENT_RYR)
    passed = bar1 and bar2 and bar3 and bar4
    verdicts[label] = ("PROMISING" if passed else "DEAD") + \
        f" (bar1 PF>{PARENT_PF}:{bar1}, bar2 eras_pos>=3:{bar2}({holds}/4), " \
        f"bar3 LB>=40:{bar3}({res['lb_n']}), bar4 EVR&RYR>parent:{bar4})"
    marker = " <== PRIMARY" if is_primary else ""
    print(f"{label:34s} -> {verdicts[label]}{marker}")

json.dump({
    "parity1": p1, "parity1_pass": ok1, "parity2": p2, "parity2_pass": ok2,
    "grid": [{"label": lbl, "primary": pr, "params": {k: v for k, v in par.items()},
              "result": res} for lbl, pr, par, res in results],
    "verdicts": verdicts,
}, open(SCR + r"\_enguq_erw_bench.json", "w"), indent=1, default=str)
print("\nSAVED", SCR + r"\_enguq_erw_bench.json")
