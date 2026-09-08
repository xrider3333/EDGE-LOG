"""
ROUND 32b — third family seed: the WEEKLY opening range (pre-registered 2026-09-08).

Mechanism the library has never traded at this time scale: Monday's opening range sets
the WEEK's levels. Range = Monday's first 60 minutes (or the whole Monday session).
From Tuesday on, the first 5m CLOSE beyond the range -> enter next open, one trade per
direction per week. Stop = the other side of the range x stop_mult. Breakeven at 1R
(armed on close, next bar). Exit at Wednesday's close or Friday's close. Overnight holds
are naked (r18b: resting overnight stops hurt); the morning open is checked gap-honestly.
Roll-seam weeks skipped (house calendar detector). Costs 0.783/RT (overnight holds).
Cells: range {mon60, monfull} x exit {wed, fri} x stop {0.75, 1.0} = 8.
Window 2010-06-07 .. 2025-06-29. Whole grid; one look. Reported with the concentration test.
"""
import os, sys, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
_sp2 = _ilu.spec_from_file_location("r32", os.path.join(ROOT, "tools", "r32_family_seeds.py"))
r32 = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(r32)

m = find_master("NQ", "5m", "rth", "db_noadj_rth")
R = load_master_arrays(m, date_to="2025-06-29")
o, h, l, c, did = R["open"], R["high"], R["low"], R["close"], R["day_id"]
idx = R["index"]; mins = (idx.hour * 60 + idx.minute).values
sess = []; a = 0; n = len(c)
while a < n:
    b = a
    while b < n and did[b] == did[a]: b += 1
    sess.append((a, b)); a = b
do = np.array([o[x] for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
seams = set(_ond.detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
wk = np.array([idx[x].isocalendar()[1] + 100 * idx[x].isocalendar()[0] for x, y in sess])
wd = np.array([idx[x].weekday() for x, y in sess])
cells = {(rg, ex, sm): [] for rg in ("mon60", "monfull") for ex in ("wed", "fri") for sm in (0.75, 1.0)}
d = 0
while d < len(sess):
    days = [k for k in range(d, len(sess)) if wk[k] == wk[d]]
    d = days[-1] + 1
    if len(days) < 3 or wd[days[0]] != 0 or any(k in seams for k in days):
        continue
    mon = days[0]; a0, b0 = sess[mon]
    for rg in ("mon60", "monfull"):
        hi_i = [k for k in range(a0, b0) if mins[k] < 630] if rg == "mon60" else list(range(a0, b0))
        if not hi_i: continue
        rh = h[hi_i].max(); rl = l[hi_i].min(); rng = rh - rl
        if rng <= 0: continue
        for ex in ("wed", "fri"):
            exit_day = next((k for k in days if wd[k] == 2), None) if ex == "wed" else days[-1]
            if exit_day is None: continue
            i_end = sess[exit_day][1]
            for sm in (0.75, 1.0):
                done = {1: False, -1: False}
                for k in range(sess[days[1]][0], i_end - 1):
                    for side, lvl in ((1, rh), (-1, rl)):
                        if done[side]: continue
                        if (c[k] > lvl) if side == 1 else (c[k] < lvl):
                            entry = o[k + 1]; stop0 = entry - side * sm * rng
                            px = r32.ride(o, h, l, c, k + 1, i_end, entry, stop0, side)
                            cells[(rg, ex, sm)].append(side * (px - entry) - 0.783)
                            done[side] = True
r32.RESULTS.clear()
for (rg, ex, sm), pnl in cells.items():
    r32.score(pnl, "C-WEEKLYOR", f"{rg}/{ex}/stop{sm}", floor=300)
print(f"{'fam':12}{'cell':22}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
for r in r32.RESULTS:
    if not r.get("n"): print(f"{r['fam']:12}{r['cell']:22}  no trades"); continue
    g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300 and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
    print(f"{r['fam']:12}{r['cell']:22}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
with open("tools/r16_results/r32b_weekly_or.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(max(r32.RESULTS, key=len).keys())); w.writeheader()
    for r in r32.RESULTS: w.writerow(r)
print("saved tools/r16_results/r32b_weekly_or.csv")
