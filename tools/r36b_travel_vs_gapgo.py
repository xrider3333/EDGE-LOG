"""
ROUND 36b — is TRAVEL (round 36 triage pass) a second family, or GAPGO's twin? (2026-09-08)
Both harness cells rebuilt to per-DAY PnL on NQ 5m RTH 2010-06-07..2025-06-29: shared trade days,
same-direction share, daily-PnL correlation, and the 1:1 pool vs each alone.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
_sp2 = _ilu.spec_from_file_location("r32", os.path.join(ROOT, "tools", "r32_family_seeds.py"))
r32 = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(r32)
ride = r32.ride

R = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_to="2025-06-29")
o, h, l, c, did = R["open"], R["high"], R["low"], R["close"], R["day_id"]
idx = R["index"]; mins = (idx.hour * 60 + idx.minute).values
sess = []; a = 0; n = len(c)
while a < n:
    b = a
    while b < n and did[b] == did[a]: b += 1
    sess.append((a, b)); a = b
do = np.array([o[x] for x, y in sess]); dh = np.array([h[x:y].max() for x, y in sess])
dl = np.array([l[x:y].min() for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
nd = len(sess); seams = set(_ond.detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
atr = np.full(nd, np.nan)
for d in range(20, nd): atr[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
days = [idx[x].date() for x, y in sess]

gap_d, gap_s, tr_d, tr_s = {}, {}, {}, {}
for d in range(21, nd):
    if d in seams or np.isnan(atr[d]): continue
    a, b = sess[d]
    gap = do[d] - dc[d - 1]
    if abs(gap) >= 0.15 * atr[d]:
        side = 1 if gap > 0 else -1; fh, fl = h[a], l[a]
        if fh - fl > 0:
            for k in range(a + 1, b - 1):
                if (c[k] > fh) if side == 1 else (c[k] < fl):
                    entry = o[k + 1]; px = ride(o, h, l, c, k + 1, b, entry, entry - side * 0.75 * (fh - fl), side)
                    gap_d[days[d]] = 20 * (side * (px - entry) - 0.533); gap_s[days[d]] = side; break
    ks = [i for i in range(a, b - 1) if mins[i] >= 600]
    if ks:
        i = ks[0] - 1 if ks[0] > a else a
        trav = c[i] - do[d]
        if abs(trav) >= 0.3 * atr[d]:
            side = 1 if trav > 0 else -1; entry = o[i + 1]
            if side * (entry - do[d]) > 0:
                px = ride(o, h, l, c, i + 1, b, entry, do[d], side)
                tr_d[days[d]] = 20 * (side * (px - entry) - 0.533); tr_s[days[d]] = side

g = pd.Series(gap_d); t = pd.Series(tr_d)
both = g.index.intersection(t.index)
print(f"GAPGO n={len(g)} net=${g.sum():,.0f}   TRAVEL n={len(t)} net=${t.sum():,.0f}")
print(f"shared days {len(both)} = {100*len(both)/len(t):.0f}% of TRAVEL days, {100*len(both)/len(g):.0f}% of GAPGO days")
same = np.mean([gap_s[x] == tr_s[x] for x in both])
print(f"same direction on shared days: {100*same:.0f}%")
al = pd.concat([g, t], axis=1).sort_index().fillna(0); al.columns = ["gapgo", "travel"]
assert al.index.is_monotonic_increasing, "pooled daily index is not in calendar order"  # round 41 lesson
print(f"daily-PnL correlation (zeros filled): {al.gapgo.corr(al.travel):.3f}; shared days only: {g[both].corr(t[both]):.3f}")
print(f"TRAVEL net on GAPGO days ${t[both].sum():,.0f}; on non-GAPGO days ${t.drop(both).sum():,.0f}")
for lab, s in (("GAPGO alone", g), ("TRAVEL alone", t), ("GAPGO+TRAVEL 1:1", al.sum(axis=1))):
    cum = s.sort_index().cumsum(); dd = float((cum - cum.cummax()).min())
    print(f"  {lab:18} net=${s.sum():>9,.0f} DD=${-dd:>8,.0f} n/DD={s.sum()/-dd:5.2f}")
