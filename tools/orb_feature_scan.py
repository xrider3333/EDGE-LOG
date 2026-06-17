# orb_feature_scan.py — mine ORB trades for a feature that separates winners from
# losers, WITH train/test discipline so we don't fool ourselves.
#
# Re-implements the ORB entry logic (vol_filter OFF = the full breakout population),
# records per-trade features at entry, then for each feature: tercile/bucket the
# FIRST 70% of trades (chronological), and check whether the same split still
# separates outcomes on the last 30% (out-of-sample). A pattern that only works
# in-sample is curve-fit noise.
import os, sys
import numpy as np, pandas as pd

def _pf(s):
    g = s[s > 0].sum(); ll = -s[s < 0].sum()
    return g/ll if ll > 0 else 99.0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTERS = {"NQ": ("master_00c66966.csv", 20), "ES": ("master_a85a0438.csv", 50)}
INST = os.environ.get("XC_INST", "NQ").upper()
fname, MULT = MASTERS[INST]
COST = 5.66 / MULT + 0.25
OR_BARS, STOP_FRAC = 3, 0.75            # validated structural config (vol_filter OFF)

df = pd.read_csv(os.path.join(ROOT, "augur_uploads", fname))
dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
df.index = dt
O, H, L, C, V = (df[c].values for c in ["open", "high", "low", "close", "volume"])
DAY = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
MIN = (df.index.hour * 60 + df.index.minute).values
n = len(C)

# session bounds + per-session range for trailing-vol features
bounds = []
i = 0
while i < n:
    j = i
    while j < n and DAY[j] == DAY[i]:
        j += 1
    bounds.append((i, j)); i = j
sess_rng = np.array([H[a:b].max() - L[a:b].min() for a, b in bounds], float)
prev_close = {si: (C[bounds[si-1][1]-1] if si > 0 else np.nan) for si in range(len(bounds))}

rows = []
for si, (a, b) in enumerate(bounds):
    m = b - a
    if m <= OR_BARS + 1:
        continue
    so, sh, sl, sc, sv = O[a:b], H[a:b], L[a:b], C[a:b], V[a:b]
    or_hi, or_lo = sh[:OR_BARS].max(), sl[:OR_BARS].min()
    rng = or_hi - or_lo
    if rng <= 0:
        continue
    or_dir = 1 if sc[OR_BARS-1] >= so[0] else -1
    med_rng = np.median(sess_rng[max(0, si-20):si]) if si >= 5 else np.nan
    pc = prev_close[si]
    gap = (so[0] - pc) if not np.isnan(pc) else 0.0
    pos = 0; entry = stop = 0.0; ek = -1
    for k in range(OR_BARS, m):
        if pos == 0:
            up, dn = sh[k] >= or_hi, sl[k] <= or_lo
            if not (up or dn):
                continue
            side = 1 if up else -1
            entry = (max(or_hi, so[k]) if so[k] > or_hi else or_hi) if up else \
                    (min(or_lo, so[k]) if so[k] < or_lo else or_lo)
            stop = entry - STOP_FRAC*rng if up else entry + STOP_FRAC*rng
            bo_vol_rel = (sv[k] / sv[:k].mean()) if k > 0 and sv[:k].mean() > 0 else np.nan
            pos = side; ek = k
            feat = dict(t=a+k, dir=side, or_w=rng,
                        or_w_rel=(rng/med_rng if med_rng and not np.isnan(med_rng) else np.nan),
                        gap_rel=gap/rng, bo_vol_rel=bo_vol_rel, bo_bar=k,
                        agree=int(side == or_dir),
                        entry_min=int(MIN[a+k] - MIN[a]),
                        dow=df.index[a+k].strftime("%a"))
            continue
        else:
            if pos > 0 and sl[k] <= stop:
                _pnl = stop - entry; pos = 0; break
            if pos < 0 and sh[k] >= stop:
                _pnl = entry - stop; pos = 0; break
    if pos != 0:
        _pnl = (sc[-1]-entry) if pos > 0 else (entry-sc[-1])
    feat["net"] = (_pnl - COST) * MULT
    rows.append(feat)

T = pd.DataFrame(rows).dropna(subset=["or_w_rel", "bo_vol_rel"]).reset_index(drop=True)
split = int(len(T)*0.70)
tr, te = T.iloc[:split], T.iloc[split:]
print(f"{INST} ORB feature scan · {len(T)} trades (vol_filter OFF) · "
      f"train {len(tr)} / test {len(te)} (chrono 70/30) · net of costs")
print(f"  baseline:  train PF {_pf(tr.net):.2f} WR {100*(tr.net>0).mean():.0f}% "
      f"${tr.net.sum():,.0f}  |  test PF {_pf(te.net):.2f} WR {100*(te.net>0).mean():.0f}% "
      f"${te.net.sum():,.0f}")


def cont_feature(name):
    qs = tr[name].quantile([1/3, 2/3]).values
    def buck(v): return 0 if v <= qs[0] else (2 if v > qs[1] else 1)
    print(f"\n  {name}  (train terciles @ {qs[0]:.2f}, {qs[1]:.2f}):")
    for lbl, idx in (("low", 0), ("mid", 1), ("high", 2)):
        a = tr[tr[name].apply(buck) == idx].net
        b = te[te[name].apply(buck) == idx].net
        print(f"    {lbl:<4} train n{len(a):>4} PF {_pf(a):>5.2f} WR {100*(a>0).mean():>3.0f}% "
              f"avg ${a.mean():>6.0f}  |  test n{len(b):>4} PF {_pf(b):>5.2f} "
              f"WR {100*(b>0).mean():>3.0f}% avg ${b.mean():>6.0f}")


def cat_feature(name, order=None):
    cats = order or sorted(T[name].unique())
    print(f"\n  {name}:")
    for cval in cats:
        a = tr[tr[name] == cval].net; b = te[te[name] == cval].net
        if len(a) == 0:
            continue
        print(f"    {str(cval):<6} train n{len(a):>4} PF {_pf(a):>5.2f} WR {100*(a>0).mean():>3.0f}% "
              f"avg ${a.mean():>6.0f}  |  test n{len(b):>4} PF {_pf(b):>5.2f} "
              f"WR {100*(b>0).mean():>3.0f}% avg ${b.mean():>6.0f}")


for f in ["or_w_rel", "bo_vol_rel", "gap_rel", "or_w", "bo_bar", "entry_min"]:
    cont_feature(f)
cat_feature("dir", [1, -1])
cat_feature("agree", [1, 0])
cat_feature("dow", ["Mon", "Tue", "Wed", "Thu", "Fri"])
