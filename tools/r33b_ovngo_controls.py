"""
ROUND 33b — is OVNGO its own mechanism, or a 5-minute ORB in disguise? (pre-registered 2026-09-08)

Round 33's best cell (gap >= 0.25 x ATR20, first 5m close beyond the FIRST bar in the gap
direction, stop 0.75 x first-bar range, BE at 1R, exit at close) scored n=1528 / $107,044 /
PF 1.311 / DD $23,410 / 8-of-8 slices / top-10 share 61% / ex-top-10 +$41,561. It fails only
the n/DD bar (4.57 vs 8). Before calling it a family seed, three CONTROLS and six one-step
NEIGHBOURS, all on NQ 5m RTH 2010-06-07..2025-06-29, no lockbox:
  CONTROLS  any-gap (threshold 0)  |  plain 5m ORB both sides, no gap reference  |  AGAINST the gap
  NEIGHBOURS gap 0.15 / 0.35  |  stop 0.5  |  exit 60m / 120m  |  15-minute range (3 bars)
If the plain ORB matches it, the gap filter is doing nothing and this is the ORB family.
"""
import os, sys, csv
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
_sp2 = _ilu.spec_from_file_location("r32", os.path.join(ROOT, "tools", "r32_family_seeds.py"))
r32 = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(r32)
score, ride = r32.score, r32.ride

m = find_master("NQ", "5m", "rth", "db_noadj_rth")
R = load_master_arrays(m, date_to="2025-06-29")
o, h, l, c, did = R["open"], R["high"], R["low"], R["close"], R["day_id"]
idx = R["index"]; mins = (idx.hour * 60 + idx.minute).values
sess = []; a = 0; n = len(c)
while a < n:
    b = a
    while b < n and did[b] == did[a]: b += 1
    sess.append((a, b)); a = b
do = np.array([o[x] for x, y in sess]); dh = np.array([h[x:y].max() for x, y in sess])
dl = np.array([l[x:y].min() for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
nd = len(sess)
seams = set(_ond.detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
atr20 = np.full(nd, np.nan)
for d in range(20, nd): atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
r32.RESULTS.clear()


def ovngo(gm, sm, mode="with", orbars=1, exit_min=None, cell=""):
    pnl = []
    for d in range(21, nd):
        if d in seams or np.isnan(atr20[d]): continue
        a, b = sess[d]
        if b - a < orbars + 2: continue
        gap = do[d] - dc[d - 1]
        if mode != "orb" and abs(gap) < gm * atr20[d]: continue
        i_end = b
        if exit_min is not None:
            ends = [k for k in range(a, b) if mins[k] >= exit_min]
            if not ends: continue
            i_end = ends[0]
        fh, fl = h[a:a + orbars].max(), l[a:a + orbars].min()
        if mode == "orb": sides = (1, -1)
        elif mode == "with": sides = (1,) if gap > 0 else (-1,)
        else: sides = (-1,) if gap > 0 else (1,)          # against
        done = {1: False, -1: False}
        for k in range(a + orbars, i_end - 1):
            for side in sides:
                if done[side]: continue
                if (c[k] > fh) if side == 1 else (c[k] < fl):
                    entry = o[k + 1]; stop0 = entry - side * sm * (fh - fl)
                    px = ride(o, h, l, c, k + 1, i_end, entry, stop0, side)
                    pnl.append(side * (px - entry) - 0.533); done[side] = True
    score(pnl, "E-OVNGO", cell)


ovngo(0.25, 0.75, cell="REF gap0.25/stop0.75/close")
ovngo(0.0, 0.75, cell="CTRL any-gap direction")
ovngo(0.0, 0.75, mode="orb", cell="CTRL plain 5m ORB both")
ovngo(0.25, 0.75, mode="against", cell="CTRL against gap")
ovngo(0.15, 0.75, cell="NB gap0.15")
ovngo(0.35, 0.75, cell="NB gap0.35")
ovngo(0.25, 0.5, cell="NB stop0.5")
ovngo(0.25, 0.75, exit_min=630, cell="NB exit 60m")
ovngo(0.25, 0.75, exit_min=690, cell="NB exit 120m")
ovngo(0.25, 0.75, orbars=3, cell="NB 15m range")

print(f"{'fam':10}{'cell':28}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
for r in r32.RESULTS:
    if not r.get("n"): print(f"{r['fam']:10}{r['cell']:28}  no trades"); continue
    g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300 and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
    print(f"{r['fam']:10}{r['cell']:28}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
with open("tools/r16_results/r33b_ovngo_controls.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(max(r32.RESULTS, key=len).keys())); w.writeheader()
    for r in r32.RESULTS: w.writerow(r)
print("saved tools/r16_results/r33b_ovngo_controls.csv")
