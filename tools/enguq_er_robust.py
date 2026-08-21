"""BATTERY W -- is the efficiency-ratio gate a plateau or a spike?

Battery V found er(60) >= 0.25 PROMISING on both entries (raw: PF 1.332->1.597, LB PF
1.493->2.645; l50: 1.401->1.578, 1.674->2.751) -- but the 0.35 threshold collapsed, which
is exactly the shape a knife-edge has. Before any celebration:
  1. plateau map: ER length x threshold grid (40/60/90 x 0.15/0.20/0.25/0.30)
  2. yearly spread + top-10 concentration for the hit cells
  3. paired block bootstrap of the PF gain for the headline cell (er60_25 on l50)
"""
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
SCR = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15\scratchpad")
sys.path.insert(0, SCR)
import importlib.util as ilu
spec = ilu.spec_from_file_location("htfb", SCR + r"\htf_battery_lib.py")

# reuse the battery-V engine by importing the file with its __main__ sweep stripped:
# simplest robust route -- re-exec htf_battery.py up to the mask section via its functions.
# htf_battery.py runs its sweep at import, so instead re-declare the engine here by exec
# of the source between markers.
src = open(SCR + r"\htf_battery.py", encoding="utf-8").read()
head = src.split("# \u2500\u2500 gate masks")[0]
exec(compile(head, "htf_head", "exec"))

# er masks for the grid
def er_mask(L, th):
    chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
    ad = np.abs(np.diff(c, prepend=c[0]))
    cs = np.cumsum(ad)
    vol_sum = cs - np.concatenate([np.zeros(L), cs[:-L]])
    er = np.where(vol_sum > 0, chg / np.maximum(vol_sum, 1e-9), 0.0)
    return np.nan_to_num(er) >= th


def yearly(trades):
    d = np.array([(t[2] - COST) * MULT for t in trades])
    ent = pd.to_datetime([idx[int(t[0])] for t in trades]).tz_localize(None)
    yr = pd.Series(d).groupby(ent.year.values).sum()
    d18 = d[ent >= pd.Timestamp("2018-01-01")]
    top10 = float(np.sort(d18)[::-1][:10].sum() / d18.sum()) if len(d18) and d18.sum() > 0 else float("nan")
    return int((yr > 0).sum()), int(len(yr)), round(top10, 3)


print("parity ...", flush=True)
ctl_raw = stats(engine(None, 0.0, **CERT))
ctl_l50 = stats(engine(None, 0.5, **CERT))
assert ctl_raw["n"] == 2843 and abs(ctl_raw["net"] - 434721.12) < 1.0
assert ctl_l50["n"] == 2924 and abs(ctl_l50["net"] - 513007.57) < 1.0
print("  PASS", flush=True)

rows = {}
print("\nPLATEAU GRID (l50 entry; PF / LB net / LB PF / n)")
for L in (40, 60, 90):
    for th in (0.15, 0.20, 0.25, 0.30):
        m = er_mask(L, th)
        tr = engine(m, 0.5, **CERT)
        s = stats(tr)
        py, ty, t10 = yearly(tr)
        s.update(yrs_pos=py, yrs_tot=ty, top10_2018=t10)
        rows["L%d_t%s_l50" % (L, th)] = s
        print(f"  L={L:3d} th={th:.2f}: n={s['n']:5d} net=${s['net']:10,.0f} DD=${s['dd']:8,.0f} "
              f"PF={s['pf']:.3f} LB=${s['lb_net']:8,.0f} (n={s['lb_n']:3d}, PF={s['lb_pf']:.3f}) "
              f"yrs+{py}/{ty} top10={t10}", flush=True)

print("\nHEADLINE CELLS, raw entry, with yearly detail")
for L, th in ((60, 0.25), (60, 0.20), (40, 0.25)):
    m = er_mask(L, th)
    tr = engine(m, 0.0, **CERT)
    s = stats(tr)
    py, ty, t10 = yearly(tr)
    s.update(yrs_pos=py, yrs_tot=ty, top10_2018=t10)
    rows["L%d_t%s_raw" % (L, th)] = s
    print(f"  L={L:3d} th={th:.2f}: n={s['n']:5d} net=${s['net']:10,.0f} DD=${s['dd']:8,.0f} "
          f"PF={s['pf']:.3f} LB=${s['lb_net']:8,.0f} (n={s['lb_n']:3d}, PF={s['lb_pf']:.3f}) "
          f"yrs+{py}/{ty} top10={t10}", flush=True)

# ── paired block bootstrap: er60_25 on l50 vs plain l50 ────────────────────────────
print("\nBOOTSTRAP -- PF gain of er60_25 over plain limit-0.50 (paired, block=20d, 5000x)")
from collections import defaultdict

def by_day(trades):
    d = np.array([(t[2] - COST) * MULT for t in trades])
    ext = pd.to_datetime([idx[int(t[1])] for t in trades]).tz_localize(None).normalize()
    mp = defaultdict(list)
    for k, p_ in zip(ext, d):
        mp[k].append(p_)
    return {k: np.array(vv) for k, vv in mp.items()}

A = by_day(engine(er_mask(60, 0.25), 0.5, **CERT))
B = by_day(engine(None, 0.5, **CERT))
days = sorted(set(A) | set(B))
rng = np.random.default_rng(42)
BL = 20
nb = int(np.ceil(len(days) / BL))

def pf_of(mp, ds):
    w = s_ = 0.0
    for dd_ in ds:
        a = mp.get(dd_)
        if a is None:
            continue
        w += a[a > 0].sum(); s_ += -a[a < 0].sum()
    return w / s_ if s_ > 0 else np.nan

diffs = []
for _ in range(5000):
    starts = rng.integers(0, max(len(days) - BL, 1), size=nb)
    order = np.concatenate([np.arange(st, st + BL) for st in starts])[:len(days)]
    order = order[order < len(days)]
    ds = [days[j] for j in order]
    diffs.append(pf_of(A, ds) - pf_of(B, ds))
diffs = np.array([x for x in diffs if np.isfinite(x)])
lo, hi = np.percentile(diffs, [2.5, 97.5])
print(f"  mean {diffs.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  wins {(diffs>0).mean()*100:.1f}%  "
      f"{'STRADDLES ZERO' if lo < 0 < hi else 'DISTINGUISHABLE'}")
rows["bootstrap_pf_er6025_l50"] = dict(mean=float(diffs.mean()), ci=[float(lo), float(hi)],
                                       wins=float((diffs > 0).mean()))

json.dump(rows, open(SCR + r"\er_robust.json", "w"), indent=1, default=float)
print("SAVED")
