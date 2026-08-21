"""BATTERY W part 2 -- final checks on the ER gate before any claim.

1. Paired bootstrap of the PF gain for er60_25 on the RAW entry (part 1 only did l50).
2. Era split (4 x ~4y): does the PF gain hold in every era or is it one stretch?
3. Slot-path diagnosis: WHY did neighboring cells' lockbox trade counts jump around
   (26 vs 66)? Count lockbox-days blocked by a position entered before the lockbox.
"""
import sys
import json

import numpy as np
import pandas as pd
from collections import defaultdict

SCR = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\6ad46cde-0afb-4d6a-b442-018c45567f15\scratchpad")
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
src = open(SCR + r"\htf_battery.py", encoding="utf-8").read()
exec(compile(src.split("# \u2500\u2500 gate masks")[0], "htf_head", "exec"))


def er_mask(L, th):
    chg = np.abs(c - np.concatenate([np.full(L, np.nan), c[:-L]]))
    ad = np.abs(np.diff(c, prepend=c[0]))
    cs = np.cumsum(ad)
    vol_sum = cs - np.concatenate([np.zeros(L), cs[:-L]])
    er = np.where(vol_sum > 0, chg / np.maximum(vol_sum, 1e-9), 0.0)
    return np.nan_to_num(er) >= th


ctl = engine(None, 0.0, **CERT)
gat = engine(er_mask(60, 0.25), 0.0, **CERT)
sc, sg = stats(ctl), stats(gat)
assert sc["n"] == 2843 and abs(sc["net"] - 434721.12) < 1.0
print("control:", {k: round(v_, 3) if isinstance(v_, float) else v_ for k, v_ in sc.items()})
print("er60_25:", {k: round(v_, 3) if isinstance(v_, float) else v_ for k, v_ in sg.items()})


def by_day(trades):
    d = np.array([(t[2] - COST) * MULT for t in trades])
    ext = pd.to_datetime([idx[int(t[1])] for t in trades]).tz_localize(None).normalize()
    mp = defaultdict(list)
    for k, p_ in zip(ext, d):
        mp[k].append(p_)
    return {k: np.array(vv) for k, vv in mp.items()}


def pf_of(mp, ds):
    w = s_ = 0.0
    for dd_ in ds:
        a = mp.get(dd_)
        if a is None:
            continue
        w += a[a > 0].sum(); s_ += -a[a < 0].sum()
    return w / s_ if s_ > 0 else np.nan


A, B = by_day(gat), by_day(ctl)
days = sorted(set(A) | set(B))
rng = np.random.default_rng(42)
BL = 20
nb = int(np.ceil(len(days) / BL))
diffs = []
for _ in range(5000):
    starts = rng.integers(0, max(len(days) - BL, 1), size=nb)
    order = np.concatenate([np.arange(st, st + BL) for st in starts])[:len(days)]
    order = order[order < len(days)]
    ds = [days[j] for j in order]
    diffs.append(pf_of(A, ds) - pf_of(B, ds))
diffs = np.array([x for x in diffs if np.isfinite(x)])
lo, hi = np.percentile(diffs, [2.5, 97.5])
print(f"\nBOOTSTRAP raw entry: PF gain mean {diffs.mean():+.4f}  CI [{lo:+.4f}, {hi:+.4f}]  "
      f"wins {(diffs > 0).mean() * 100:.1f}%")

print("\nERA SPLIT (PF gated vs control, trade-entry eras)")
def era_pf(trades, a, b):
    d = np.array([(t[2] - COST) * MULT for t in trades])
    ent = pd.to_datetime([idx[int(t[0])] for t in trades]).tz_localize(None)
    m = (ent >= pd.Timestamp(a)) & (ent < pd.Timestamp(b))
    dd_ = d[m]
    if not len(dd_):
        return np.nan, 0, 0.0
    pf = dd_[dd_ > 0].sum() / max(abs(dd_[dd_ < 0].sum()), 1e-9)
    return pf, int(len(dd_)), float(dd_.sum())

for a, b in (("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
             ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01")):
    pg, ng, netg = era_pf(gat, a, b)
    pc, nc, netc = era_pf(ctl, a, b)
    print(f"  {a[:4]}-{b[:4]}: gated PF {pg:.3f} (n={ng:4d}, ${netg:9,.0f})  vs  "
          f"control PF {pc:.3f} (n={nc:4d}, ${netc:9,.0f})  ->  {'holds' if pg > pc else 'LOSES'}")

# slot-path: how much of the lockbox was blockaded by a pre-lockbox entry?
LBTS = pd.Timestamp(LB_START)
for nm, tr in (("control", ctl), ("er60_25", gat)):
    ent = pd.to_datetime([idx[int(t[0])] for t in tr]).tz_localize(None)
    ext = pd.to_datetime([idx[int(t[1])] for t in tr]).tz_localize(None)
    blk = [(en, ex) for en, ex in zip(ent, ext) if en < LBTS and ex > LBTS]
    tot = sum((min(ex, pd.Timestamp("2026-06-30")) - LBTS).days for en, ex in blk)
    print(f"  {nm}: {len(blk)} position(s) straddle the lockbox boundary, blocking ~{tot} days of it")
json.dump(dict(boot=dict(mean=float(diffs.mean()), ci=[float(lo), float(hi)],
                          wins=float((diffs > 0).mean()))),
          open(SCR + r"\er_final.json", "w"), indent=1)
print("SAVED")
