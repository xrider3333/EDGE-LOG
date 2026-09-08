"""
ROUND 33 — family seeds, second batch (pre-registered 2026-09-08). NQ 5m RTH, 2010-06-07..2025-06-29.

Everything that has ever validated here is intraday CONTINUATION on NQ with tight initial
risk, fired by a specific structural trigger (the open, a trendline break, a band break).
Two triggers the library has never used, each cheap and legal (finished-bar information only):

D. VOLBAR - relative-volume momentum bar continuation. A 5m bar whose volume is >= vmult x
   its trailing 20-bar average AND which closes in the top (bottom) q of its own range and
   is an up (down) bar = a participation bar. Enter NEXT bar open in its direction; stop =
   the bar's other extreme x stop_mult; breakeven at 1R (armed on close, next bar); exit at
   the session close. One trade per direction per day, entries 10:00-15:00 ET only.
   Cells: vmult {1.5, 2.0, 3.0} x q {0.2, 0.3} x stop_mult {1.0} = 6.
E. OVNGO - overnight-move continuation. If the RTH open gaps >= gmult x ATR20 (of daily
   ranges) from the prior close, wait for the first 5m CLOSE beyond the FIRST bar's high
   (gap up) / low (gap down) -> enter next open in the gap direction; stop = first bar's
   other side x stop_mult; breakeven at 1R; exit at the close. Cells: gmult {0.25, 0.5,
   0.75} x stop_mult {0.75, 1.0} = 6. Roll-seam days skipped.
Both families reported with the full house read incl. the concentration test.
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
o, h, l, c, v, did = R["open"], R["high"], R["low"], R["close"], R["volume"], R["day_id"]
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
vavg = np.full(n, np.nan)
cs = np.concatenate([[0.0], np.cumsum(v)])
for i in range(20, n):
    vavg[i] = (cs[i] - cs[i - 20]) / 20.0          # trailing 20 bars, EXCLUDING bar i
r32.RESULTS.clear()

# ---------- D: VOLBAR ----------
for vm in (1.5, 2.0, 3.0):
    for q in (0.2, 0.3):
        pnl = []
        for d in range(21, nd):
            if d in seams: continue
            a, b = sess[d]; done = {1: False, -1: False}
            for k in range(a + 1, b - 1):
                if mins[k] < 600 or mins[k] > 900: continue
                if np.isnan(vavg[k]) or v[k] < vm * vavg[k]: continue
                rng = h[k] - l[k]
                if rng <= 0: continue
                pos = (c[k] - l[k]) / rng
                side = 1 if (c[k] > o[k] and pos >= 1 - q) else (-1 if (c[k] < o[k] and pos <= q) else 0)
                if side == 0 or done[side]: continue
                entry = o[k + 1]; stop0 = (l[k] if side == 1 else h[k])
                if side * (entry - stop0) <= 0: continue
                px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
                pnl.append(side * (px - entry) - 0.533); done[side] = True
        score(pnl, "D-VOLBAR", f"vol{vm}x/q{q}")
print("VOLBAR done", flush=True)

# ---------- E: OVNGO ----------
atr20 = np.full(nd, np.nan)
for d in range(20, nd): atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
for gm in (0.25, 0.5, 0.75):
    for sm in (0.75, 1.0):
        pnl = []
        for d in range(21, nd):
            if d in seams or np.isnan(atr20[d]): continue
            gap = do[d] - dc[d - 1]
            if abs(gap) < gm * atr20[d]: continue
            side = 1 if gap > 0 else -1
            a, b = sess[d]
            fh, fl = h[a], l[a]
            for k in range(a + 1, b - 1):
                if (c[k] > fh) if side == 1 else (c[k] < fl):
                    entry = o[k + 1]; stop0 = entry - side * sm * (fh - fl)
                    px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
                    pnl.append(side * (px - entry) - 0.533); break
        score(pnl, "E-OVNGO", f"gap{gm}atr/stop{sm}")
print("OVNGO done", flush=True)

print(f"\n{'fam':10}{'cell':22}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
for r in r32.RESULTS:
    if not r.get("n"): print(f"{r['fam']:10}{r['cell']:22}  no trades"); continue
    g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300 and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
    print(f"{r['fam']:10}{r['cell']:22}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
with open("tools/r16_results/r33_family_seeds2.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(max(r32.RESULTS, key=len).keys())); w.writeheader()
    for r in r32.RESULTS: w.writerow(r)
print("saved tools/r16_results/r33_family_seeds2.csv")
