"""
ROUND 38 — SCALPERS, part C (pre-registered 2026-09-08; owner: "keep testing scalpers / intraday").
Builds on round 37's scalp hunt (tools/r37_scalp_triage.py, 0/39: micro-ORB, open-drive, PDH/PDL,
range-burst, VWAP-cross all die on NQ 1m; a FIXED target cannot make a scalp at house costs; only
tail-keeping exits earn). So every mechanism here gets BOTH exit families: FIXED (target k x risk, time
stop) and RIDE (breakeven at 1R armed on a close, ride to the session close) - if a mechanism only pays
with RIDE it is not a scalp, and that is written down. Four mechanisms round 37 did NOT test:

C. SWEEP-RECLAIM   a 1m bar takes out the prior 15-bar low (high) and CLOSES back above (below) it ->
                   enter next open; stop = the sweep extreme. Exits FIXED 1.5R/20 bars, RIDE.
D. CHOP-FADE       trailing 30-bar range under half its own 390-bar median (chop) -> fade a close in
                   the outer 10% of that range; stop 0.25 x width beyond the edge; targets = mid / far
                   edge, 30-bar time stop. (Reversion: the house pattern says dead; pre-registered anyway.)
H. IGNITION        a 1m close above (below) the prior 60-bar high (low) with volume >= vmult x the
                   trailing 60-bar mean (vmult 1.0 = no filter, 2.0); stop = the bar's other extreme.
                   Exits FIXED 2R/30 bars, RIDE. Entries 09:45-15:30, one position at a time.
I. BOX-BREAK       the last 5 bars' range < 0.5 x the median 30-bar range (a 1-minute compression) and a
                   close beyond that 5-bar box -> enter next open; stop = other side of the box.
                   Exits FIXED 2R/30 bars, RIDE. Entries 09:45-15:30.
NQ 1m RTH, 2010-06-07..2025-06-29, lockbox never loaded, $20/pt, scored at 0.533 AND 0.783 per RT,
pessimistic fills (stop first), flat at the close, roll-seam days skipped, concentration on every cell.
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

m = find_master("NQ", "1m", "rth", "db_noadj_rth")
R = load_master_arrays(m, date_to="2025-06-29")
o, h, l, c, v, did = R["open"], R["high"], R["low"], R["close"], R["volume"], R["day_id"]
idx = R["index"]; mins = (idx.hour * 60 + idx.minute).values
n = len(c)
sess = []; a = 0
while a < n:
    b = a
    while b < n and did[b] == did[a]: b += 1
    sess.append((a, b)); a = b
do = np.array([o[x] for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
seams = set(_ond.detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
rng = h - l
print(f"bars {n} sessions {len(sess)} seams {len(seams)}", flush=True)
S = pd.Series
med30 = S(rng).rolling(30).median().shift(1).values
hi60 = S(h).rolling(60).max().shift(1).values; lo60 = S(l).rolling(60).min().shift(1).values
vmean60 = S(v).rolling(60).mean().shift(1).values
hi5 = S(h).rolling(5).max().shift(1).values; lo5 = S(l).rolling(5).min().shift(1).values
hi15 = S(h).rolling(15).max().shift(1).values; lo15 = S(l).rolling(15).min().shift(1).values
w30 = (S(h).rolling(30).max() - S(l).rolling(30).min()).shift(1).values
w30med = S(w30).rolling(390).median().values
r32.RESULTS.clear()


def fixed_exit(i_open, i_end, entry, stop, target, side, tmax):
    last = min(i_end, i_open + tmax)
    for i in range(i_open, last):
        if side == 1:
            if o[i] <= stop: return o[i]
            if l[i] <= stop: return stop
            if h[i] >= target: return target if o[i] < target else o[i]
        else:
            if o[i] >= stop: return o[i]
            if h[i] >= stop: return stop
            if l[i] <= target: return target if o[i] > target else o[i]
    return c[last - 1]


def run(name, gen, exits):
    """gen(a, b) -> list of (k, side, stop0); exits = list of (label, kind, kt, tmax)."""
    for lab, kind, kt, tmax in exits:
        gross = []
        for d in range(1, len(sess)):
            if d in seams: continue
            a, b = sess[d]; busy = a
            for k, side, stop0 in gen(a, b):
                if k < busy or k + 1 >= b - 1: continue
                entry = o[k + 1]; risk = side * (entry - stop0)
                if risk <= 0: continue
                if kind == "ride":
                    px = ride(o, h, l, c, k + 1, b, entry, stop0, side); busy = b
                else:
                    px = fixed_exit(k + 1, b, entry, stop0, entry + side * kt * risk, side, tmax); busy = k + 1 + tmax
                gross.append(side * (px - entry))
        for cost in (0.533, 0.783):
            score([g - cost for g in gross], name, f"{lab}/c{cost}")
        print(name, lab, "done", flush=True)


def in_window(k, lo=585, hi=930): return lo <= mins[k] <= hi


def gen_sweep(a, b):
    out = []
    for k in range(a + 16, b - 2):
        if not in_window(k, 571): continue
        if l[k] < lo15[k] and c[k] > lo15[k]: out.append((k, 1, l[k] - 0.25))
        elif h[k] > hi15[k] and c[k] < hi15[k]: out.append((k, -1, h[k] + 0.25))
    return out
run("C-SWEEP", gen_sweep, [("fixed1.5R", "fixed", 1.5, 20), ("ride", "ride", 0, 0)])


def gen_chop_factory(mode):
    def gen(a, b):
        out = []
        for k in range(a + 31, b - 2):
            if not in_window(k, 571) or np.isnan(w30med[k]) or np.isnan(w30[k]): continue
            hi = h[k - 30:k].max(); lo = l[k - 30:k].min(); w = hi - lo
            if w <= 0 or w >= 0.5 * w30med[k]: continue
            if c[k] <= lo + 0.1 * w: out.append((k, 1, lo - 0.25 * w, (lo + w / 2) if mode == "mid" else hi))
            elif c[k] >= hi - 0.1 * w: out.append((k, -1, hi + 0.25 * w, (lo + w / 2) if mode == "mid" else lo))
        return out
    return gen


for mode in ("mid", "far"):
    gross = []
    gen = gen_chop_factory(mode)
    for d in range(1, len(sess)):
        if d in seams: continue
        a, b = sess[d]; busy = a
        for k, side, stop0, tgt in gen(a, b):
            if k < busy or k + 1 >= b - 1: continue
            entry = o[k + 1]
            if side * (entry - stop0) <= 0 or side * (tgt - entry) <= 0: continue
            px = fixed_exit(k + 1, b, entry, stop0, tgt, side, 30); busy = k + 31
            gross.append(side * (px - entry))
    for cost in (0.533, 0.783):
        score([g - cost for g in gross], "D-CHOPFADE", f"target {mode}/c{cost}")
    print("D-CHOPFADE", mode, "done", flush=True)


def gen_ign_factory(vm):
    def gen(a, b):
        out = []
        for k in range(a + 61, b - 2):
            if not in_window(k) or np.isnan(vmean60[k]) or v[k] < vm * vmean60[k]: continue
            if c[k] > hi60[k]: out.append((k, 1, l[k]))
            elif c[k] < lo60[k]: out.append((k, -1, h[k]))
        return out
    return gen


for vm in (1.0, 2.0):
    run(f"H-IGNITION vol{vm}x", gen_ign_factory(vm), [("fixed2R", "fixed", 2.0, 30), ("ride", "ride", 0, 0)])


def gen_box(a, b):
    out = []
    for k in range(a + 31, b - 2):
        if not in_window(k) or np.isnan(med30[k]): continue
        bw = hi5[k] - lo5[k]
        if bw <= 0 or bw >= 0.5 * med30[k] * 5: continue     # 5-bar box narrower than half of 5 typical bars
        if c[k] > hi5[k]: out.append((k, 1, lo5[k]))
        elif c[k] < lo5[k]: out.append((k, -1, hi5[k]))
    return out
run("I-BOXBREAK", gen_box, [("fixed2R", "fixed", 2.0, 30), ("ride", "ride", 0, 0)])

print(f"\n{'fam':18}{'cell':22}{'n':>7}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
for r in r32.RESULTS:
    if not r.get("n"): print(f"{r['fam']:18}{r['cell']:22}  no trades"); continue
    g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300 and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
    print(f"{r['fam']:18}{r['cell']:22}{r['n']:>7}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
with open("tools/r16_results/r38_scalpers.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(max(r32.RESULTS, key=len).keys())); w.writeheader()
    for r in r32.RESULTS: w.writerow(r)
print("saved tools/r16_results/r38_scalpers.csv")
