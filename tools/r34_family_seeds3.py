"""
ROUND 34 — family seeds, third batch (pre-registered 2026-09-08). NQ 5m RTH, 2010-06-07..2025-06-29.

F. LEADLAG — ES leads, NQ follows. At the close of a 5m bar, ES has just printed a NEW
   session high (low) — its close is above every prior close of the day — while NQ's close
   is NOT at a new session high (low). Buy (sell) NQ next bar open expecting the catch-up.
   Stop = the NQ bar's low (high) x stop_mult; BE at 1R; exit at the close. One trade per
   direction per day, entries 10:00-15:00 ET. ES and NQ 5m RTH masters aligned on timestamp.
   Cells: stop_mult {1.0, 1.5} x lead window {session, 12 bars} = 4, plus the MIRROR control
   (NQ leads, ES lags -> trade NQ in its own direction = plain NQ momentum) = 2 more.
G. RETEST — break-and-retest entry. First 5m close above (below) the opening-range high
   (low), then a later bar whose LOW (HIGH) touches the level and which CLOSES back above
   (below) it = the retest. Enter next open; stop = the retest bar's other extreme x
   stop_mult; BE at 1R; exit at the close. One trade per direction per day. Cells: range
   {15m, 30m} x stop_mult {1.0, 1.5} = 4.
Both reported with the full house read incl. the concentration test.
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
do = np.array([o[x] for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
nd = len(sess)
seams = set(_ond.detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
r32.RESULTS.clear()

# ---------- F: LEADLAG ----------
mE = find_master("ES", "5m", "rth", "db_noadj_rth")
E = load_master_arrays(mE, date_to="2025-06-29")
es_close = pd.Series(E["close"], index=E["index"])
ec = es_close.reindex(idx).values                     # ES close aligned on NQ timestamps (NaN if missing)
print("ES aligned bars:", int(np.isfinite(ec).sum()), "of", n, flush=True)


def leadlag(sm, win, mirror=False, cell=""):
    pnl = []
    for d in range(1, nd):
        if d in seams: continue
        a, b = sess[d]
        if np.isnan(ec[a:b]).any(): continue
        done = {1: False, -1: False}
        for k in range(a + 3, b - 1):
            if mins[k] < 600 or mins[k] > 900: continue
            s0 = a if win == "session" else max(a, k - 12)
            lead, lag = (ec, c) if not mirror else (c, ec)
            lead_hi = lead[k] > lead[s0:k].max(); lead_lo = lead[k] < lead[s0:k].min()
            lag_hi = lag[k] > lag[s0:k].max(); lag_lo = lag[k] < lag[s0:k].min()
            side = 1 if (lead_hi and not lag_hi) else (-1 if (lead_lo and not lag_lo) else 0)
            if side == 0 or done[side]: continue
            entry = o[k + 1]; rng = h[k] - l[k]
            if rng <= 0: continue
            stop0 = entry - side * sm * rng
            px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
            pnl.append(side * (px - entry) - 0.533); done[side] = True
    score(pnl, "F-LEADLAG", cell)


for sm in (1.0, 1.5):
    for win in ("session", "12bar"):
        leadlag(sm, win, cell=f"ES->NQ/{win}/stop{sm}")
for win in ("session", "12bar"):
    leadlag(1.0, win, mirror=True, cell=f"CTRL NQ->ES/{win}/stop1.0")
print("LEADLAG done", flush=True)


# ---------- G: RETEST ----------
def retest(orbars, sm, cell=""):
    pnl = []
    for d in range(1, nd):
        if d in seams: continue
        a, b = sess[d]
        if b - a < orbars + 3: continue
        rh, rl = h[a:a + orbars].max(), l[a:a + orbars].min()
        broke = {1: False, -1: False}; done = {1: False, -1: False}
        for k in range(a + orbars, b - 1):
            for side, lvl in ((1, rh), (-1, rl)):
                if done[side]: continue
                beyond = (c[k] > lvl) if side == 1 else (c[k] < lvl)
                if not broke[side]:
                    if beyond: broke[side] = True
                    continue
                touched = (l[k] <= lvl) if side == 1 else (h[k] >= lvl)
                if touched and beyond:
                    entry = o[k + 1]; rng = h[k] - l[k]
                    if rng <= 0: continue
                    stop0 = entry - side * sm * rng
                    px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
                    pnl.append(side * (px - entry) - 0.533); done[side] = True
    score(pnl, "G-RETEST", cell)


for orbars in (3, 6):
    for sm in (1.0, 1.5):
        retest(orbars, sm, cell=f"or{orbars*5}m/stop{sm}")
print("RETEST done", flush=True)

print(f"\n{'fam':10}{'cell':28}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
for r in r32.RESULTS:
    if not r.get("n"): print(f"{r['fam']:10}{r['cell']:28}  no trades"); continue
    g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300 and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
    print(f"{r['fam']:10}{r['cell']:28}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
with open("tools/r16_results/r34_family_seeds3.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(max(r32.RESULTS, key=len).keys())); w.writeheader()
    for r in r32.RESULTS: w.writerow(r)
print("saved tools/r16_results/r34_family_seeds3.csv")
