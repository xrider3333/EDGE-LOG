"""Adversarial re-verification of tools/noise_gate_tilt.py. Independent arithmetic."""
import sys, os, json
import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\noisetilt"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "augur_strategies"))

from augur_engine.data import find_master, load_master_arrays
from augur_engine.ml_gate import gate_trades, entry_features_causal, entry_features
from noise_variant_research import run_variant
import importlib
ngt = importlib.import_module("noise_gate_tilt")

INST, TF, SESS, SOURCE = "NQ", "5m", "rth", "db_noadj_rth"
MULT, FEE = 20.0, 0.533
DFROM, DTO, LB_FROM = "2010-06-07", "2026-08-12", "2025-02-11"
CAP = 3.0
CFG = ngt.CFG
ALL_MODELS = ("logistic", "rf", "xgb", "tree", "et")   # ORB's FIVE, not four

m = find_master(INST, TF, SESS, SOURCE)
arrays = load_master_arrays(m, DFROM, DTO)
idx = arrays["index"]
T = run_variant(arrays["open"], arrays["high"], arrays["low"], arrays["close"],
                arrays.get("volume"), arrays["day_id"], **CFG)
T = sorted(T, key=lambda t: int(t[0]))
pnl = np.array([t[2] for t in T], float)
nb = len(idx)
ts = np.array([idx[min(int(t[0]), nb - 1)] for t in T])
lb_start = pd.Timestamp(LB_FROM)
_tz = getattr(pd.Timestamp(idx[-1]), "tzinfo", None)
if _tz is not None and lb_start.tzinfo is None:
    lb_start = lb_start.tz_localize(_tz)
pre = ts < lb_start; lb = ~pre
risk, nfb = ngt._trade_risk(T, arrays, CFG)

print("### SETUP")
print("master %s  bars %d  trades %d  pre %d  lb %d  risk-fallbacks %d"
      % (m["filename"], nb, len(T), pre.sum(), lb.sum(), nfb))
yrs_pre = (pd.Timestamp(ts[pre][-1]) - pd.Timestamp(ts[0])).days / 365.25
yrs_lb  = (pd.Timestamp(ts[-1]) - pd.Timestamp(ts[lb][0])).days / 365.25
print("PRE span %s -> %s  = %.2f yr   |  LB span %s -> %s = %.2f yr"
      % (str(ts[0])[:10], str(ts[pre][-1])[:10], yrs_pre,
         str(ts[lb][0])[:10], str(ts[-1])[:10], yrs_lb))

# ---------- independent metrics (my own arithmetic, not theirs) ----------
def met(p, s):
    net = s * (p - FEE) * MULT
    cum = np.cumsum(net)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    live = s > 1e-9
    return dict(net=float(net.sum()), dd=dd, mar=float(net.sum())/abs(dd),
                n=int(live.sum()), avg=float(s[live].mean()) if live.any() else 0.0,
                mx=float(s.max()), arr=net)

flat = np.ones(len(T))
B = {"pre": met(pnl[pre], flat[pre]), "lb": met(pnl[lb], flat[lb])}
full = met(pnl, flat)
print("FLAT  PRE net %,.0f MAR %.4f DD %,.0f n %d".replace(",.0f","0.0f") % (0,0,0,0) if False else
      "FLAT  PRE net %s MAR %.4f DD %s n %d" % (f"{B['pre']['net']:,.0f}", B['pre']['mar'], f"{B['pre']['dd']:,.0f}", B['pre']['n']))
print("FLAT  LB  net %s MAR %.4f DD %s n %d" % (f"{B['lb']['net']:,.0f}", B['lb']['mar'], f"{B['lb']['dd']:,.0f}", B['lb']['n']))
print("FLAT FULL net %s MAR %.4f DD %s n %d  <- vs recorded #243 raw 17.2"
      % (f"{full['net']:,.0f}", full['mar'], f"{full['dd']:,.0f}", full['n']))

# ---------- probs (cached) ----------
cache = os.path.join(SCRATCH, "probs.npz")
if os.path.exists(cache):
    probs = {k: v for k, v in np.load(cache).items()}
    print("loaded cached probs:", list(probs))
else:
    feats = entry_features_causal(arrays)[0]
    probs = {}
    for mdl in ALL_MODELS:
        g = gate_trades(arrays, [(int(t[0]), int(t[1]), float(t[2]) - FEE) for t in T],
                        model=mdl, threshold=0.0, min_history=30, refit_every=25, seed=42, feats=feats)
        probs[mdl] = np.asarray(g["prob"], float)
        print("  scored %-9s warmup %d median %.4f" % (mdl, np.isnan(probs[mdl]).sum(), np.nanmedian(probs[mdl])))
    probs["avg5"] = np.nanmean(np.vstack([probs[k] for k in ALL_MODELS]), axis=0)
    np.savez(cache, **probs)
np.save(os.path.join(SCRATCH, "pnl.npy"), pnl)
np.save(os.path.join(SCRATCH, "pre.npy"), pre)
np.save(os.path.join(SCRATCH, "risk.npy"), risk)

SCHEMES = (("cut@50", ngt._w_cut), ("tier", ngt._w_tier), ("linear", ngt._w_linear))
SRC = list(ALL_MODELS) + ["avg5"]

rows = []
print("\n### ALL 18 CELLS (5 models + avg5 consensus) x 3 schemes  -- driver ran only 12")
print("%-9s%-8s %12s %8s %11s %6s %6s %6s | %11s %8s %11s %5s %6s %6s %8s %5s"
      % ("model","scheme","PREnet","PREMAR","PREDD","n","avgSz","maxSz",
         "LBnet","LBMAR","LBDD","n","avgSz","maxSz","k","cap"))
for mdl in SRC:
    p = probs[mdl]
    for nm, fn in SCHEMES:
        w = fn(p)
        denom = float((w[pre]*risk[pre]).sum())
        k = float(risk[pre].sum())/denom
        raw = w*k
        size = np.minimum(raw, CAP)
        caps = int((raw > CAP+1e-12).sum())
        r = dict(model=mdl, scheme=nm, k=k, caps=caps, w=w, size=size,
                 pre=met(pnl[pre], size[pre]), lb=met(pnl[lb], size[lb]))
        rows.append(r)
        print("%-9s%-8s %12s %8.3f %11s %6d %6.2f %6.2f | %11s %8.3f %11s %5d %6.2f %6.2f %8.4f %5d"
              % (mdl, nm, f"{r['pre']['net']:,.0f}", r['pre']['mar'], f"{r['pre']['dd']:,.0f}",
                 r['pre']['n'], r['pre']['avg'], r['pre']['mx'],
                 f"{r['lb']['net']:,.0f}", r['lb']['mar'], f"{r['lb']['dd']:,.0f}",
                 r['lb']['n'], r['lb']['avg'], r['lb']['mx'], k, caps))

# ---------- BAR A: as coded in noise_gate_tilt.py ----------
print("\n### BAR A - as CODED in noise_gate_tilt.py (PREnet> , PREMAR> , LBMAR>=)")
passA = []
for r in rows:
    l1 = r['pre']['net'] > B['pre']['net']; l2 = r['pre']['mar'] > B['pre']['mar']
    l3 = r['lb']['mar'] >= B['lb']['mar']
    ok = l1 and l2 and l3
    if ok: passA.append(r)
    print("  %-9s%-8s L1 %+11s %-3s | L2 %+7.3f %-3s | L3 %+7.3f %-3s -> %s"
          % (r['model'], r['scheme'], f"{r['pre']['net']-B['pre']['net']:,.0f}", "ok" if l1 else "no",
             r['pre']['mar']-B['pre']['mar'], "ok" if l2 else "no",
             r['lb']['mar']-B['lb']['mar'], "ok" if l3 else "no", "PASS" if ok else "FAIL"))
print("  => %d of %d clear BAR A" % (len(passA), len(rows)))

# ---------- BAR B: the REAL 2026-08-10 ORB bar ----------
print("\n### BAR B - the ACTUAL 2026-08-10 ORB bar from tools/orb_gate_tilt.py:")
print("    ok = pre MAR > flat  AND  lb MAR > flat (STRICT)  AND  lb MAR > cut@50's lb MAR")
print("    ...and cut@50 rows are NOT tilt variants; ORB's '12' = 6 sources x (tier,linear)")
cut = {r['model']: r for r in rows if r['scheme'] == 'cut@50'}
passB = []; nB = 0
for r in rows:
    if r['scheme'] == 'cut@50':
        continue
    nB += 1
    c = cut.get(r['model'])
    ok = (r['pre']['mar'] > B['pre']['mar'] and r['lb']['mar'] > B['lb']['mar']
          and c is not None and r['lb']['mar'] > c['lb']['mar'])
    if ok: passB.append(r)
    print("  %-9s%-8s preMAR %7.3f vs %7.3f | lbMAR %7.3f vs flat %7.3f / cut %7.3f -> %s"
          % (r['model'], r['scheme'], r['pre']['mar'], B['pre']['mar'],
             r['lb']['mar'], B['lb']['mar'], c['lb']['mar'], "PASS" if ok else "fail"))
print("  => %d of %d TILT variants clear BAR B (the real ORB bar)" % (len(passB), nB))

# ---------- k-invariance of MAR ----------
print("\n### IS THE CAPITAL MATCH LOAD-BEARING?  MAR is invariant to a uniform scale k.")
r0 = rows[3]  # rf cut@50
for kk in (1.0, r0['k'], 2.5):
    s = np.minimum(r0['w']*kk, 1e9)
    print("   rf cut@50 with k=%.4f -> PRE net %14s  PRE MAR %.6f   LB MAR %.6f"
          % (kk, f"{met(pnl[pre], s[pre])['net']:,.0f}", met(pnl[pre], s[pre])['mar'], met(pnl[lb], s[lb])['mar']))
print("   => legs 2 and 3 (both MAR legs) CANNOT be affected by capital matching when the cap does not bind.")
print("   total cap binds across all cells: %d of %d cell-trades" % (sum(r['caps'] for r in rows), len(rows)*len(T)))

# ---------- CONCENTRATION, re-derived two ways ----------
print("\n### CONCENTRATION (PRE slice)")
fnet = B['pre']['arr']
def ex_own(a, k=10):
    return float(a.sum() - np.sort(a)[::-1][:k].sum())
top10_flat_idx = np.argsort(fnet)[::-1][:10]     # flat's own 10 best, by index
f_own = ex_own(fnet)
f_same = float(fnet.sum() - fnet[top10_flat_idx].sum())
print("  flat  net %s | ex-own-top10 %s | ex-flat's-top10 %s"
      % (f"{fnet.sum():,.0f}", f"{f_own:,.0f}", f"{f_same:,.0f}"))
print("  %-9s%-8s %12s %13s %13s | %13s %13s"
      % ("model","scheme","net","ex-OWN-top10","gain(OWN)","ex-SAME-top10","gain(SAME)"))
for r in rows:
    a = r['pre']['arr']
    v_own = ex_own(a); v_same = float(a.sum() - a[top10_flat_idx].sum())
    print("  %-9s%-8s %12s %13s %13s | %13s %13s  %s"
          % (r['model'], r['scheme'], f"{a.sum():,.0f}", f"{v_own:,.0f}",
             f"{v_own-f_own:+,.0f}", f"{v_same:,.0f}", f"{v_same-f_same:+,.0f}",
             "survives-both" if (v_own-f_own>0 and v_same-f_same>0) else "FRAGILE"))

# ---------- COVERAGE ----------
print("\n### COVERAGE - what cut@50 throws away, at flat size 1")
for mdl in SRC:
    p = probs[mdl]; d = (~np.isnan(p)) & (p < 0.50)
    print("  %-9s drops %4d/%d (PRE %4d / LB %3d)  worth PRE %11s  LB %11s"
          % (mdl, d.sum(), len(T), (d&pre).sum(), (d&lb).sum(),
             f"{float(((pnl[d&pre]-FEE)*MULT).sum()):,.0f}",
             f"{float(((pnl[d&lb]-FEE)*MULT).sum()):,.0f}"))

# ---------- NOISE: spread + bootstrap on the decisive leg ----------
print("\n### NOISE / SPREAD")
pm = np.array([r['pre']['mar'] for r in rows]); lm = np.array([r['lb']['mar'] for r in rows])
print("  PRE MAR across 18 cells: min %.2f max %.2f spread %.2f  (flat %.2f)" % (pm.min(), pm.max(), pm.max()-pm.min(), B['pre']['mar']))
print("  LB  MAR across 18 cells: min %.2f max %.2f spread %.2f  (flat %.2f)" % (lm.min(), lm.max(), lm.max()-lm.min(), B['lb']['mar']))

rng = np.random.default_rng(7)
def boot_mar(net, nb_=2000):
    n = len(net); out = np.empty(nb_)
    for i in range(nb_):
        s = net[rng.integers(0, n, n)]
        cum = np.cumsum(s); dd = (cum-np.maximum.accumulate(cum)).min()
        out[i] = s.sum()/abs(dd) if abs(dd) > 1e-9 else np.nan
    return out
bf_pre = boot_mar(B['pre']['arr']); bf_lb = boot_mar(B['lb']['arr'])
print("  flat PRE MAR %.2f  bootstrap 90%% CI [%.2f, %.2f]" % (B['pre']['mar'], *np.nanpercentile(bf_pre,[5,95])))
print("  flat LB  MAR %.2f  bootstrap 90%% CI [%.2f, %.2f]" % (B['lb']['mar'], *np.nanpercentile(bf_lb,[5,95])))
print("  -- paired bootstrap of (cell LB MAR - flat LB MAR), same resample indices:")
nlb = int(lb.sum())
for r in rows:
    if r['model'] not in ('rf','logistic','xgb') or r['scheme'] != 'cut@50':
        continue
    d = np.empty(2000); rg2 = np.random.default_rng(11)
    for i in range(2000):
        ix = rg2.integers(0, nlb, nlb)
        a = r['lb']['arr'][ix]; b = B['lb']['arr'][ix]
        ca, cb = np.cumsum(a), np.cumsum(b)
        da = (ca-np.maximum.accumulate(ca)).min(); db = (cb-np.maximum.accumulate(cb)).min()
        d[i] = (a.sum()/abs(da)) - (b.sum()/abs(db)) if abs(da)>1e-9 and abs(db)>1e-9 else np.nan
    lo, hi = np.nanpercentile(d, [5,95])
    print("    %-9s%-8s dLBMAR %+.3f  bootstrap 90%% CI [%+.2f, %+.2f]  P(d>0)=%.2f"
          % (r['model'], r['scheme'], r['lb']['mar']-B['lb']['mar'], lo, hi, float(np.nanmean(d>0))))

# ---------- CAUSALITY: randomise the tape AFTER a cutoff ----------
print("\n### CAUSALITY TEST 1 - randomise the tape after a cutoff bar")
CUT = int(nb * 0.60)
rg = np.random.default_rng(123)
a2 = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in arrays.items()}
for key in ("open", "high", "low", "close"):
    v = np.asarray(arrays[key], float).copy()
    tail = v[CUT:].copy(); rg.shuffle(tail)
    v[CUT:] = tail * rg.uniform(0.5, 1.5, size=tail.shape)
    a2[key] = v
F0 = entry_features_causal(arrays)[0]
F1 = entry_features_causal(a2)[0]
same_rows = int(np.all(np.isclose(F0[:CUT], F1[:CUT], atol=1e-9, equal_nan=True), axis=1).sum())
print("  cutoff bar %d of %d.  feature rows 0..%d identical: %d of %d  (%s)"
      % (CUT, nb, CUT-1, same_rows, CUT, "PASS - no future leaks into past rows" if same_rows==CUT else "FAIL"))
first_diff = np.where(~np.all(np.isclose(F0, F1, atol=1e-9, equal_nan=True), axis=1))[0]
print("  first differing feature row: %d (cutoff %d) -> lead/lag = %+d bars %s"
      % (first_diff[0], CUT, first_diff[0]-CUT,
         "(causal: >= cutoff)" if first_diff[0] >= CUT else "(LEAK: before cutoff!)"))
# leak-era comparison: the UNSHIFTED entry_features should differ one bar EARLIER
G0 = entry_features(arrays)[0]; G1 = entry_features(a2)[0]
fd2 = np.where(~np.all(np.isclose(G0, G1, atol=1e-9, equal_nan=True), axis=1))[0]
print("  same test on the LEAK-ERA entry_features(): first differing row %d (%+d vs cutoff)"
      % (fd2[0], fd2[0]-CUT))

print("\n### CAUSALITY TEST 2 - same trade list, tape randomised after cutoff; do EARLY probs move?")
tt = [(int(t[0]), int(t[1]), float(t[2]) - FEE) for t in T]
early = np.array([int(t[0]) < CUT for t in T])
for mdl in ("logistic", "tree"):
    g0 = gate_trades(arrays, tt, model=mdl, threshold=0.0, min_history=30,
                     refit_every=25, seed=42, feats=F0)
    g1 = gate_trades(arrays, tt, model=mdl, threshold=0.0, min_history=30,
                     refit_every=25, seed=42, feats=F1)
    p0 = np.asarray(g0["prob"], float); p1 = np.asarray(g1["prob"], float)
    e = early & ~np.isnan(p0)
    md = float(np.nanmax(np.abs(p0[e]-p1[e]))) if e.any() else 0.0
    lt = early | True
    mdl_all = float(np.nanmax(np.abs(p0[~early & ~np.isnan(p0)]-p1[~early & ~np.isnan(p1)])))
    print("  %-9s trades entering BEFORE cutoff: n=%d  max |dp| = %.2e  %s   (after cutoff max|dp| = %.3f)"
          % (mdl, int(e.sum()), md, "PASS" if md < 1e-9 else "FAIL - future tape moved past scores", mdl_all))

print("\n### CAUSALITY TEST 3 - perturb the OUTCOMES (pnl) of late trades; do EARLY probs move?")
KTR = int(len(T)*0.6)
tt2 = [(tt[i][0], tt[i][1], (tt[i][2] if i < KTR else float(rg.normal(0, 50))))
       for i in range(len(T))]
for mdl in ("logistic", "tree"):
    g0 = gate_trades(arrays, tt,  model=mdl, threshold=0.0, min_history=30, refit_every=25, seed=42, feats=F0)
    g1 = gate_trades(arrays, tt2, model=mdl, threshold=0.0, min_history=30, refit_every=25, seed=42, feats=F0)
    p0 = np.asarray(g0["prob"], float); p1 = np.asarray(g1["prob"], float)
    e = np.arange(len(T)) < KTR
    e &= ~np.isnan(p0)
    md = float(np.nanmax(np.abs(p0[e]-p1[e]))) if e.any() else 0.0
    print("  %-9s first %d trades: max |dp| = %.2e  %s"
          % (mdl, KTR, md, "PASS - later outcomes never train earlier scores" if md < 1e-9 else "FAIL"))
print("\nDONE")
