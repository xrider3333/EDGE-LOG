"""
ROUND 36 — family seeds, fifth batch (pre-registered 2026-09-08). NQ 5m, 2010-06-07..2025-06-29,
0.533/RT, $20/pt, BE 1R, flat at the close, calendar roll-seam skip, concentration test on every cell.

T. TRAVEL — distance-from-open continuation (a threshold, not a range break). At a fixed clock time
   (10:00 / 10:30 / 11:00 ET) if price has travelled at least k x ATR20 from the session open, enter
   at the next bar's open in that direction; stop = the session OPEN (the whole travel is the risk),
   or half-way (stop_frac 0.5). Cells: time {1000, 1030, 1100} x k {0.3, 0.5} x stop_frac {1.0} = 6.
O. ONRANGE — the open relative to the OVERNIGHT range (18:00 prior evening to 09:25 ET, from the
   5m ETH master). If the RTH open is ABOVE the overnight high (below the low) -> the first-bar break
   in that direction (GAPGO logic with the overnight range as the gauge instead of ATR). Control:
   open INSIDE the overnight range but in its top/bottom 20% -> same trade. Stop 0.75 x first bar.
   Cells: {beyond, edge20, inside-middle control} = 3.
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
atr = np.full(nd, np.nan)
for d in range(20, nd): atr[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
r32.RESULTS.clear()

# ---------- T: TRAVEL ----------
for tmin in (600, 630, 660):
    for k in (0.3, 0.5):
        pnl = []
        for d in range(21, nd):
            if d in seams or np.isnan(atr[d]): continue
            a, b = sess[d]
            ks = [i for i in range(a, b - 1) if mins[i] >= tmin]
            if not ks: continue
            i = ks[0] - 1 if ks[0] > a else a          # last FINISHED bar before the clock time
            trav = c[i] - do[d]
            if abs(trav) < k * atr[d]: continue
            side = 1 if trav > 0 else -1
            entry = o[i + 1]; stop0 = do[d]
            if side * (entry - stop0) <= 0: continue
            px = ride(o, h, l, c, i + 1, b, entry, stop0, side)
            pnl.append(side * (px - entry) - 0.533)
        score(pnl, "T-TRAVEL", f"{tmin//60:02d}{tmin%60:02d}/k{k}/stop=open")
print("TRAVEL done", flush=True)

# ---------- O: ONRANGE ----------
mE = find_master("NQ", "5m", "eth", "db_noadj_eth")
E = load_master_arrays(mE, date_to="2025-06-29")
eidx = pd.DatetimeIndex(E["index"]); eh, el = E["high"], E["low"]
print("ETH index sample:", eidx[:2].tolist(), "RTH:", idx[:2].tolist(), flush=True)
on_hi = np.full(nd, np.nan); on_lo = np.full(nd, np.nan)
for d in range(nd):
    t0 = idx[sess[d][0]]
    j1 = eidx.searchsorted(t0)                       # first ETH bar at/after the RTH open
    j0 = eidx.searchsorted(t0 - pd.Timedelta(hours=15, minutes=45))
    if j1 - j0 >= 100:                               # a real overnight session, not a hole
        on_hi[d] = eh[j0:j1].max(); on_lo[d] = el[j0:j1].min()


def onrange(mode, cell):
    pnl = []
    for d in range(21, nd):
        if d in seams or np.isnan(on_hi[d]): continue
        a, b = sess[d]
        rng = on_hi[d] - on_lo[d]
        if rng <= 0: continue
        pos = (do[d] - on_lo[d]) / rng
        if mode == "beyond":
            side = 1 if pos > 1 else (-1 if pos < 0 else 0)
        elif mode == "edge20":
            side = 1 if 0.8 <= pos <= 1 else (-1 if 0 <= pos <= 0.2 else 0)
        else:                                       # middle control: 0.4-0.6, direction = first-bar close
            side = (1 if c[a] > o[a] else -1) if 0.4 <= pos <= 0.6 else 0
        if side == 0: continue
        fh, fl = h[a], l[a]
        if fh - fl <= 0: continue
        for k in range(a + 1, b - 1):
            if (c[k] > fh) if side == 1 else (c[k] < fl):
                entry = o[k + 1]; stop0 = entry - side * 0.75 * (fh - fl)
                px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
                pnl.append(side * (px - entry) - 0.533); break
    score(pnl, "O-ONRANGE", cell)


onrange("beyond", "open BEYOND overnight range")
onrange("edge20", "open in outer 20% of ON range")
onrange("middle", "CTRL open mid-range, 1st-candle dir")
print("ONRANGE done", flush=True)

print(f"\n{'fam':12}{'cell':34}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
for r in r32.RESULTS:
    if not r.get("n"): print(f"{r['fam']:12}{r['cell']:34}  no trades"); continue
    g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300 and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
    print(f"{r['fam']:12}{r['cell']:34}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
with open("tools/r16_results/r36_family_seeds5.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(max(r32.RESULTS, key=len).keys())); w.writeheader()
    for r in r32.RESULTS: w.writerow(r)
print("saved tools/r16_results/r36_family_seeds5.csv")
