"""
ENGU-Q ETH #309 crown x PARTIAL EXIT / SCALE-OUT -- bench driver (worktree enguq-partial).

QUESTION: run #309 (the crowned ENGU-Q ETH leg) has the best PF/EV R in the library but
weak risk-adjusted return: MAR 0.75 ($36.8k/yr against a $48.9k drawdown), 58% of net in
its top ten trades, 282-day longest hold. It rides winners the full round trip and gives
back the whole open-profit swing when a long hold turns. Does banking part of the
position early (a partial exit at partial_R x initial risk) buy risk-adjusted return
(higher MAR, lower tail concentration) without breaking profit factor or starving the
held-out year?

PRE-REGISTERED BARS (written before running; ALL must pass for a cell to be an honest
"improvement" -- trading one number for another in an arguably-better direction, not a
straight win):
  1. MAR up >= 15% vs 0.75          -> MAR >= 0.8625
  2. R/YR down <= 5% vs 43.4        -> R/YR >= 41.23
  3. top-10 share <= 58% AND net excluding the top ten is still positive
  4. >= 90 held-out trades (entries >= 2025-06-30)
  5. PF >= 1.50 (may fall from 1.655 -- banking early costs PF -- but not through the floor)
PRIMARY (declared before running) = partial_R 2.0, partial_frac 0.5.

PARITY ANCHORS (printed before the grid; must PASS before any bench cell is trusted):
  - partial_R=0.0 (OFF) on #309's params, window 2010-06-07..2026-06-30, NQ 1m ETH
    db_noadj_eth, cost 0.533 x $20 -> n=1604, net $591,267, PF 1.655 (run #309 exactly).
  - DEFAULT_PARAMS (ER_1_0 defaults, er_th=0.0, limit_atr=0.0) -> n=2843, net $434,721.12
    (the #226 anchor).

BENCH GRID (<=16 in-engine runs total; 2 parity + 10 base grid + up to 2 breakeven-repeat
cells for the two most promising base cells = 14 runs):
  partial_R in {1.0, 1.5, 2.0, 3.0, 4.0} x partial_frac in {0.25, 0.5}     (10 cells)
  + the 2 cells closest to clearing the bars, repeated with breakeven_R 1.5 (2 cells)
"""
import sys
import json
import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\enguq-partial"
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
    "px", REPO + r"\augur_strategies\ENGUQ_1M_ETH_PX_1_0.py")
px = importlib.util.module_from_spec(spec)
spec.loader.exec_module(px)

DATE_FROM, DATE_TO = "2010-06-07", "2026-06-30"
COST, MULT = 0.533, 20
LB_START = "2025-06-30"

master = find_master("NQ", "1m", session="eth", source="db_noadj_eth")
arr = load_master_arrays(master, date_from=DATE_FROM, date_to=DATE_TO)
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v = arr.get("volume")
idx = pd.to_datetime(arr["index"])


def run(**params):
    out = px.run_backtest(o, h, l, c, volumes=v, return_trades=True, **params)
    if out is None or not out.get("trades"):
        return None
    trades = out["trades"]  # (entry_idx, exit_idx, pnl_pts, side, entry_px)
    pnl = np.array([(t[2] - COST) * MULT for t in trades])
    ent_i = np.array([int(t[0]) for t in trades])
    ext_i = np.array([int(t[1]) for t in trades])
    ent = idx[ent_i]
    ext = idx[ext_i]
    n = len(pnl)
    wins = pnl[pnl > 0]; losses = pnl[pnl < 0]
    wr = len(wins) / n
    pf = wins.sum() / max(abs(losses.sum()), 1e-9)
    ev_r = (1 - wr) * (pf - 1)
    years = (idx[-1] - idx[0]).days / 365.25
    tpy = n / years
    r_yr = ev_r * tpy
    net = float(pnl.sum())
    cum = np.cumsum(pnl)
    dd = float((cum - np.maximum.accumulate(cum)).min())  # negative
    mar = (net / years) / abs(dd) if dd != 0 else float("nan")

    lb_ts = pd.Timestamp(LB_START)
    if ent.tz is not None and lb_ts.tzinfo is None:
        lb_ts = lb_ts.tz_localize(ent.tz)
    lb_mask = ent >= lb_ts
    lb_n = int(lb_mask.sum()); lb_net = float(pnl[lb_mask].sum())
    lb_pf = (pnl[lb_mask][pnl[lb_mask] > 0].sum() /
             max(abs(pnl[lb_mask][pnl[lb_mask] < 0].sum()), 1e-9)) if lb_n else float("nan")

    order = np.argsort(pnl)[::-1]
    top10_idx = order[:10]
    top10_sum = float(pnl[top10_idx].sum())
    top10_share = (top10_sum / net * 100.0) if net != 0 else float("nan")
    net_ex_top10 = net - top10_sum

    hold_days = (ext - ent).days
    longest_hold = int(hold_days.max()) if n else 0

    eras = []
    for a, b in (("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
                 ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01")):
        ta, tb = pd.Timestamp(a), pd.Timestamp(b)
        if ent.tz is not None:
            ta = ta.tz_localize(ent.tz); tb = tb.tz_localize(ent.tz)
        m = (ent >= ta) & (ent < tb)
        ddv = pnl[m]
        if len(ddv) == 0:
            eras.append((a[:4], np.nan, 0))
            continue
        epf = ddv[ddv > 0].sum() / max(abs(ddv[ddv < 0].sum()), 1e-9)
        eras.append((a[:4], epf, int(len(ddv))))

    return dict(n=n, net=round(net, 2), pf=round(float(pf), 3), wr=round(wr * 100, 1),
                ev_r=round(float(ev_r), 3), r_yr=round(float(r_yr), 1),
                max_dd=round(abs(dd), 2), mar=round(float(mar), 4),
                lb_n=lb_n, lb_net=round(lb_net, 2), lb_pf=round(float(lb_pf), 3) if lb_n else None,
                top10_share=round(top10_share, 1), net_ex_top10=round(net_ex_top10, 2),
                longest_hold_days=longest_hold, eras=eras)


BASE_309 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52,
                act_R=1.5, breakeven_R=3.0, ema_len=220, er_len=100, stop_mult=1.3,
                regime_len=10, min_brk=1.6, vol_mult=1.1, er_th=0.0,
                partial_R=0.0, partial_frac=0.5)

print("=" * 78)
print("PARITY CHECK 1: #309 params, partial_R=0.0 (OFF) -- expect n=1604, net $591,267, PF 1.655")
p1 = run(**BASE_309)
print(p1)
ok1 = (p1 and p1["n"] == 1604 and abs(p1["net"] - 591267) < 5.0 and abs(p1["pf"] - 1.655) < 0.005)
print("PARITY 1:", "PASS" if ok1 else "FAIL")

print("\nPARITY CHECK 2: DEFAULT_PARAMS (er_th=0, limit_atr=0) -- expect n=2843, net $434,721.12 (#226)")
default_kwargs = {k: v["default"] for k, v in px.DEFAULT_PARAMS.items()}
p2 = run(**default_kwargs)
print(p2)
ok2 = (p2 and p2["n"] == 2843 and abs(p2["net"] - 434721.12) < 1.0)
print("PARITY 2:", "PASS" if ok2 else "FAIL")

PARENT = dict(mar=0.75, r_yr=43.4, top10_share=58.0, lb_n=99, pf=1.655)
BAR = dict(mar_min=PARENT["mar"] * 1.15, r_yr_min=PARENT["r_yr"] * 0.95,
           top10_max=PARENT["top10_share"], lb_min=90, pf_min=1.50)

print("\n" + "=" * 78)
print(f"BARS: MAR>={BAR['mar_min']:.4f}  R/YR>={BAR['r_yr_min']:.2f}  top10<={BAR['top10_max']}  "
      f"net_ex_top10>0  LB_n>={BAR['lb_min']}  PF>={BAR['pf_min']}")
print("PRIMARY = partial_R 2.0 / partial_frac 0.5")
print("=" * 78)


def verdict(res):
    if res is None:
        return False, "DEAD (no trades)"
    b1 = res["mar"] >= BAR["mar_min"]
    b2 = res["r_yr"] >= BAR["r_yr_min"]
    b3 = (res["top10_share"] <= BAR["top10_max"]) and (res["net_ex_top10"] > 0)
    b4 = res["lb_n"] >= BAR["lb_min"]
    b5 = res["pf"] >= BAR["pf_min"]
    passed = b1 and b2 and b3 and b4 and b5
    return passed, (f"MAR{'OK' if b1 else 'X'}({res['mar']}) R/YR{'OK' if b2 else 'X'}({res['r_yr']}) "
                     f"top10{'OK' if b3 else 'X'}({res['top10_share']}%,exT10=${res['net_ex_top10']:,.0f}) "
                     f"LB{'OK' if b4 else 'X'}({res['lb_n']}) PF{'OK' if b5 else 'X'}({res['pf']})")


grid_cells = []
for pr in (1.0, 1.5, 2.0, 3.0, 4.0):
    for pf_frac in (0.25, 0.5):
        grid_cells.append(dict(label=f"pR{pr}_pf{pf_frac}", primary=(pr == 2.0 and pf_frac == 0.5),
                                params=dict(partial_R=pr, partial_frac=pf_frac)))

results = []
for cell in grid_cells:
    params = {**BASE_309, **cell["params"]}
    res = run(**params)
    passed, why = verdict(res)
    results.append((cell["label"], cell.get("primary", False), params, res, passed, why))
    marker = " <== PRIMARY" if cell.get("primary") else ""
    if res is None:
        print(f"{cell['label']:16s} -> None (no trades){marker}")
        continue
    print(f"{cell['label']:16s} n={res['n']:5d} net=${res['net']:>11,.0f} PF={res['pf']:.3f} "
          f"WR={res['wr']:.1f}% EV_R={res['ev_r']:.3f} R/YR={res['r_yr']:.1f} "
          f"DD=${res['max_dd']:>9,.0f} MAR={res['mar']:.4f} LB_n={res['lb_n']:3d} "
          f"top10={res['top10_share']:.1f}% exT10=${res['net_ex_top10']:>10,.0f} "
          f"hold={res['longest_hold_days']:4d}d -> {'PASS' if passed else 'DEAD'}{marker}")
    print(f"{'':16s}    {why}")

# pick the 2 base cells closest to clearing the bars (most bars satisfied, tie-break on MAR)
def score(entry):
    label, primary, params, res, passed, why = entry
    if res is None:
        return (-1, -999)
    nbars = why.count("OK")
    return (nbars, res["mar"])

ranked = sorted(results, key=score, reverse=True)
top2 = ranked[:2]
print("\n" + "=" * 78)
print("Repeating the 2 most-promising base cells with breakeven_R=1.5 "
      "(banking early may make an earlier breakeven affordable):")
for label, primary, params, res, passed, why in top2:
    be_label = label + "_be1.5"
    be_params = {**params, "breakeven_R": 1.5}
    be_res = run(**be_params)
    be_passed, be_why = verdict(be_res)
    results.append((be_label, False, be_params, be_res, be_passed, be_why))
    if be_res is None:
        print(f"{be_label:20s} -> None (no trades)")
        continue
    print(f"{be_label:20s} n={be_res['n']:5d} net=${be_res['net']:>11,.0f} PF={be_res['pf']:.3f} "
          f"WR={be_res['wr']:.1f}% EV_R={be_res['ev_r']:.3f} R/YR={be_res['r_yr']:.1f} "
          f"DD=${be_res['max_dd']:>9,.0f} MAR={be_res['mar']:.4f} LB_n={be_res['lb_n']:3d} "
          f"top10={be_res['top10_share']:.1f}% exT10=${be_res['net_ex_top10']:>10,.0f} "
          f"hold={be_res['longest_hold_days']:4d}d -> {'PASS' if be_passed else 'DEAD'}")
    print(f"{'':20s}    {be_why}")

print("\n" + "=" * 78)
any_pass = any(passed for _, _, _, _, passed, _ in results)
print("ANY CELL PASSED ALL 5 BARS:", any_pass)
if any_pass:
    for label, primary, params, res, passed, why in results:
        if passed:
            print("  PASSING CELL:", label, params)

json.dump({
    "parity1": p1, "parity1_pass": ok1, "parity2": p2, "parity2_pass": ok2,
    "bars": BAR,
    "grid": [{"label": lbl, "primary": pr, "params": par, "result": res, "passed": pas, "why": why}
             for lbl, pr, par, res, pas, why in results],
    "any_pass": any_pass,
}, open(SCR + r"\_enguq_px_bench.json", "w"), indent=1, default=str)
print("\nSAVED", SCR + r"\_enguq_px_bench.json")
