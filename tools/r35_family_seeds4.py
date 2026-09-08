"""
ROUND 35 — family seeds, fourth batch + GAPGO hand-off controls (pre-registered 2026-09-08).
Window 2010-06-07..2025-06-29, lockbox never loaded, concentration test on every cell.

NEW MECHANISMS (NQ 5m RTH, 0.533/RT, $20/pt):
H. STREAK — multi-bar persistence. k consecutive same-direction 5m closes (each bar closing in
   its own top/bottom third) -> enter next open in that direction; stop = the streak's other
   extreme x stop_mult; BE 1R; exit at close; one per direction per day, entries 10:00-15:00.
   Cells: k {3, 4} x stop_mult {1.0, 1.5} = 4.
Y. FAILEDFILL — the gap that would not fill. Gap >= 0.15 ATR20; price then retraces at least
   fill_frac of the gap toward the prior close (a LOW at or below open - fill_frac x gap for a
   gap up); the first bar that then CLOSES back beyond the session OPEN in the gap direction
   -> enter next open; stop = the retrace extreme x stop_mult; BE 1R; exit at close.
   Cells: fill_frac {0.5, 1.0} x stop_mult {1.0, 1.5} = 4.

GAPGO HAND-OFF CONTROLS:
N. PRIORDAY — is the gap direction just yesterday's direction? First-bar break in the PRIOR
   DAY's direction (close vs open; close position in range >0.6/<0.4), stop 0.75. 2 cells.
   If this matches GAPGO, the gap adds nothing over yesterday's candle.
P. GAPGO on ES (5m RTH, $50/pt, 0.30 pts/RT assumed = ~$15 commission + slippage):
   gap {0.15, 0.25} x stop 0.75, 1 bar. Does the mechanism travel off the NQ tape?
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


def load(inst):
    m = find_master(inst, "5m", "rth", "db_noadj_rth")
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
    seams = set(_ond.detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
    nd = len(sess); atr = np.full(nd, np.nan)
    for d in range(20, nd): atr[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
    return dict(o=o, h=h, l=l, c=c, mins=mins, sess=sess, do=do, dh=dh, dl=dl, dc=dc, seams=seams, atr=atr, nd=nd)


NQ = load("NQ")
r32.RESULTS.clear()

# ---------- H: STREAK ----------
def streak(T, k, sm, cost, cell):
    o, h, l, c, mins = T["o"], T["h"], T["l"], T["c"], T["mins"]
    pnl = []
    for d in range(21, T["nd"]):
        if d in T["seams"]: continue
        a, b = T["sess"][d]; done = {1: False, -1: False}
        for i in range(a + k - 1, b - 1):
            if mins[i] < 600 or mins[i] > 900: continue
            for side in (1, -1):
                if done[side]: continue
                ok = True
                for j in range(i - k + 1, i + 1):
                    rng = h[j] - l[j]
                    if rng <= 0: ok = False; break
                    pos = (c[j] - l[j]) / rng
                    if side == 1 and not (c[j] > o[j] and pos >= 2 / 3): ok = False; break
                    if side == -1 and not (c[j] < o[j] and pos <= 1 / 3): ok = False; break
                if not ok: continue
                entry = o[i + 1]
                ext = l[i - k + 1:i + 1].min() if side == 1 else h[i - k + 1:i + 1].max()
                stop0 = entry - side * sm * abs(entry - ext)
                if side * (entry - stop0) <= 0: continue
                px = ride(o, h, l, c, i + 1, b, entry, stop0, side)
                pnl.append(side * (px - entry) - cost); done[side] = True
    score(pnl, "H-STREAK", cell)


for k in (3, 4):
    for sm in (1.0, 1.5):
        streak(NQ, k, sm, 0.533, f"k{k}/stop{sm}")
print("STREAK done", flush=True)


# ---------- Y: FAILEDFILL ----------
def failedfill(T, gm, ff, sm, cost, cell):
    o, h, l, c = T["o"], T["h"], T["l"], T["c"]
    pnl = []
    for d in range(21, T["nd"]):
        if d in T["seams"] or np.isnan(T["atr"][d]): continue
        a, b = T["sess"][d]
        gap = T["do"][d] - T["dc"][d - 1]
        if abs(gap) < gm * T["atr"][d]: continue
        side = 1 if gap > 0 else -1
        level = T["do"][d] - side * ff * abs(gap)          # retrace target
        filled = False; ext = None
        for i in range(a, b - 1):
            if not filled:
                if (l[i] <= level) if side == 1 else (h[i] >= level):
                    filled = True; ext = l[i] if side == 1 else h[i]
                continue
            ext = min(ext, l[i]) if side == 1 else max(ext, h[i])
            if (c[i] > T["do"][d]) if side == 1 else (c[i] < T["do"][d]):
                entry = o[i + 1]
                stop0 = entry - side * sm * abs(entry - ext)
                if side * (entry - stop0) <= 0: break
                px = ride(o, h, l, c, i + 1, b, entry, stop0, side)
                pnl.append(side * (px - entry) - cost); break
    score(pnl, "Y-FAILFILL", cell)


for ff in (0.5, 1.0):
    for sm in (1.0, 1.5):
        failedfill(NQ, 0.15, ff, sm, 0.533, f"fill{ff}/stop{sm}")
print("FAILEDFILL done", flush=True)


# ---------- N: PRIORDAY control ----------
def priorday(T, mode, sm, cost, cell):
    o, h, l, c = T["o"], T["h"], T["l"], T["c"]
    pnl = []
    for d in range(21, T["nd"]):
        if d in T["seams"]: continue
        a, b = T["sess"][d]
        if mode == "closeopen":
            side = 1 if T["dc"][d - 1] > T["do"][d - 1] else (-1 if T["dc"][d - 1] < T["do"][d - 1] else 0)
        else:
            rng = T["dh"][d - 1] - T["dl"][d - 1]
            pos = (T["dc"][d - 1] - T["dl"][d - 1]) / rng if rng > 0 else 0.5
            side = 1 if pos > 0.6 else (-1 if pos < 0.4 else 0)
        if side == 0: continue
        fh, fl = h[a], l[a]
        for k in range(a + 1, b - 1):
            if (c[k] > fh) if side == 1 else (c[k] < fl):
                entry = o[k + 1]; stop0 = entry - side * sm * (fh - fl)
                px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
                pnl.append(side * (px - entry) - cost); break
    score(pnl, "N-PRIORDAY", cell)


priorday(NQ, "closeopen", 0.75, 0.533, "CTRL prior close>open dir")
priorday(NQ, "closepos", 0.75, 0.533, "CTRL prior close-position dir")
print("PRIORDAY done", flush=True)


# ---------- P: GAPGO on ES ----------
def gapgo(T, gm, sm, cost, cell):
    o, h, l, c = T["o"], T["h"], T["l"], T["c"]
    pnl = []
    for d in range(21, T["nd"]):
        if d in T["seams"] or np.isnan(T["atr"][d]): continue
        a, b = T["sess"][d]
        gap = T["do"][d] - T["dc"][d - 1]
        if abs(gap) < gm * T["atr"][d]: continue
        side = 1 if gap > 0 else -1
        fh, fl = h[a], l[a]
        if fh - fl <= 0: continue
        for k in range(a + 1, b - 1):
            if (c[k] > fh) if side == 1 else (c[k] < fl):
                entry = o[k + 1]; stop0 = entry - side * sm * (fh - fl)
                px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
                pnl.append(side * (px - entry) - cost); break
    score(pnl, "P-GAPGO-ES", cell)


ES = load("ES")
r32.MULT = 50.0
for gm in (0.15, 0.25):
    gapgo(ES, gm, 0.75, 0.30, f"ES gap{gm}/stop0.75")
gapgo(ES, 0.0, 0.75, 0.30, "ES any-gap direction")
r32.MULT = 20.0
print("GAPGO-ES done", flush=True)

print(f"\n{'fam':12}{'cell':30}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
for r in r32.RESULTS:
    if not r.get("n"): print(f"{r['fam']:12}{r['cell']:30}  no trades"); continue
    g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300 and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
    print(f"{r['fam']:12}{r['cell']:30}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
with open("tools/r16_results/r35_family_seeds4.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(max(r32.RESULTS, key=len).keys())); w.writeheader()
    for r in r32.RESULTS: w.writerow(r)
print("saved tools/r16_results/r35_family_seeds4.csv")
