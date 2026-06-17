# orb_fold_filter.py — does a candidate filter hold ACROSS TIME (not just one split)?
# Builds the NQ ORB population (vol_filter off), cuts it into K chronological folds,
# and per fold compares baseline vs each candidate filter. A real edge beats
# baseline in MOST folds; a lucky one wins a couple and loses the rest.
import os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTERS = {"NQ": ("master_00c66966.csv", 20), "ES": ("master_a85a0438.csv", 50)}
INST = os.environ.get("XC_INST", "NQ").upper()
fname, MULT = MASTERS[INST]
COST = 5.66 / MULT + 0.25
OR_BARS, STOP_FRAC = 3, 0.75
K = 6

df = pd.read_csv(os.path.join(ROOT, "augur_uploads", fname))
dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern"); df.index = dt
O, H, L, C, V = (df[c].values for c in ["open", "high", "low", "close", "volume"])
DAY = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64"); n = len(C)

bounds = []; i = 0
while i < n:
    j = i
    while j < n and DAY[j] == DAY[i]: j += 1
    bounds.append((i, j)); i = j
sess_rng = np.array([H[a:b].max() - L[a:b].min() for a, b in bounds], float)

rows = []
for si, (a, b) in enumerate(bounds):
    m = b - a
    if m <= OR_BARS + 1: continue
    so, sh, sl, sc, sv = O[a:b], H[a:b], L[a:b], C[a:b], V[a:b]
    or_hi, or_lo = sh[:OR_BARS].max(), sl[:OR_BARS].min(); rng = or_hi - or_lo
    if rng <= 0: continue
    med = np.median(sess_rng[max(0, si-20):si]) if si >= 5 else np.nan
    pos = 0; entry = stop = 0.0
    for k in range(OR_BARS, m):
        if pos == 0:
            up, dn = sh[k] >= or_hi, sl[k] <= or_lo
            if not (up or dn): continue
            side = 1 if up else -1
            entry = (max(or_hi, so[k]) if so[k] > or_hi else or_hi) if up else (min(or_lo, so[k]) if so[k] < or_lo else or_lo)
            stop = entry - STOP_FRAC*rng if up else entry + STOP_FRAC*rng
            bvr = (sv[k]/sv[:k].mean()) if k > 0 and sv[:k].mean() > 0 else np.nan
            owr = (rng/med) if med and not np.isnan(med) else np.nan
            pos = side
            f = dict(owr=owr, bvr=bvr)
            continue
        else:
            if pos > 0 and sl[k] <= stop: _p = stop-entry; pos=0; break
            if pos < 0 and sh[k] >= stop: _p = entry-stop; pos=0; break
    if pos != 0: _p = (sc[-1]-entry) if pos > 0 else (entry-sc[-1])
    f["net"] = (_p - COST)*MULT
    rows.append(f)
T = pd.DataFrame(rows).dropna().reset_index(drop=True)

def pf(s):
    g = s[s>0].sum(); l = -s[s<0].sum(); return g/l if l > 0 else 99.0

owr_med = T.owr.median()
filters = {
    "baseline (all)":        lambda d: d,
    f"narrow OR (owr<={owr_med:.2f})": lambda d: d[d.owr <= owr_med],
    "vol>=1.5 (current)":    lambda d: d[d.bvr >= 1.5],
    "vol>=2.0":              lambda d: d[d.bvr >= 2.0],
    "vol>=2.5":              lambda d: d[d.bvr >= 2.5],
    "narrow OR + vol>=1.5":  lambda d: d[(d.owr <= owr_med) & (d.bvr >= 1.5)],
}
folds = np.array_split(T, K)
print(f"{INST} ORB filter test · {len(T)} trades · {K} chronological folds · net of costs")
print(f"{'filter':<26} " + " ".join(f"F{i+1}" for i in range(K)) + "   beats-base  totalPF  total$")
base_pf = [pf(folds[i].net) for i in range(K)]
for name, fn in filters.items():
    pfs, beats = [], 0
    allnet = []
    for i in range(K):
        sub = fn(folds[i]); p = pf(sub.net); pfs.append(p); allnet.append(sub.net)
        if name != "baseline (all)" and p > base_pf[i]: beats += 1
    allnet = pd.concat(allnet)
    cells = " ".join(f"{p:4.2f}" for p in pfs)
    bb = "—" if name == "baseline (all)" else f"{beats}/{K}"
    print(f"{name:<26} {cells}   {bb:>8}  {pf(allnet.net if hasattr(allnet,'net') else allnet):6.2f}  ${allnet.sum():>10,.0f}")
