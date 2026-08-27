"""ROBUSTNESS CHECK on battery V's 5/5 cell -- run BEFORE believing it.

A single winning cell in a jumpy sweep (5:5/5, 15:3/5, 30:3/5, 60:4/5, 120:4/5, 240:1/5)
is the classic shape of noise, not of an edge. Two questions decide it:

  1. IS IT A PLATEAU? Sweep every neighbour 1..12. A real effect degrades smoothly around
     its optimum. If 5 is a spike between worse neighbours, it is a lucky draw.
  2. IS IT A HANDFUL OF TRADES? ENGUQ.md 1.1 -- top 10 winners are 83% of net. Recompute
     the gain with the single best trade removed from BOTH sides. If the improvement
     evaporates, the cooldown did not improve anything; it happened to keep one monster.
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\enguqfix"
DATA_ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, DATA_ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_eng", os.path.join(REPO, "augur_strategies", "ENGUQ_1M_ETH_1_0.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
run_backtest = _mod.run_backtest

MULT, COST, LB = 20.0, 0.533, "2025-06-30"
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0)

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def series(cb):
    r = run_backtest(o, h, l, c, volumes=v, day_id=day, index=idx,
                     return_trades=True, **{**CERT, "cooldown_bars": cb})
    tr = r["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])
    ent = pd.to_datetime([idx[int(t[0])] for t in tr]).tz_localize(None)
    return d, ent


def summ(d, ent):
    pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
    lb = d[ent >= pd.Timestamp(LB)]
    lbpf = lb[lb > 0].sum() / max(abs(lb[lb < 0].sum()), 1e-9) if len(lb) else float("nan")
    cum = np.cumsum(d)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    return dict(n=len(d), net=d.sum(), pf=pf, dd=dd, lb_net=lb.sum(), lb_pf=lbpf)


d0, e0 = series(0)
s0 = summ(d0, e0)
print("control: n=%d net=$%.0f PF=%.3f LBnet=$%.0f LBPF=%.3f"
      % (s0["n"], s0["net"], s0["pf"], s0["lb_net"], s0["lb_pf"]))

print("\n1. PLATEAU CHECK -- neighbours of the winning cell")
print("%5s %6s %11s %8s %7s %11s %8s" % ("bars", "n", "net", "dnet$", "PF", "LBnet", "LBPF"))
keep = {}
for cb in range(1, 13):
    d, e = series(cb)
    s = summ(d, e)
    keep[cb] = (d, e, s)
    print("%5d %6d %11.0f %+8.0f %7.3f %11.0f %8.3f"
          % (cb, s["n"], s["net"], s["net"] - s0["net"], s["pf"], s["lb_net"], s["lb_pf"]))

print("\n2. SINGLE-TRADE FRAGILITY at cooldown=5")
d5, e5, s5 = keep[5]
for label, cut in (("as measured", 0), ("drop best 1", 1), ("drop best 3", 3)):
    a = np.sort(d0)[::-1][cut:] if cut else d0
    b = np.sort(d5)[::-1][cut:] if cut else d5
    print("  %-12s control $%9.0f   cooldown5 $%9.0f   delta %+9.0f"
          % (label, a.sum(), b.sum(), b.sum() - a.sum()))

lb0 = d0[e0 >= pd.Timestamp(LB)]
lb5 = d5[e5 >= pd.Timestamp(LB)]
print("\n  lockbox only (%s+): control n=%d $%.0f | cooldown5 n=%d $%.0f"
      % (LB, len(lb0), lb0.sum(), len(lb5), lb5.sum()))
for cut in (1, 3):
    print("    drop best %d: control $%.0f | cooldown5 $%.0f  delta %+.0f"
          % (cut, np.sort(lb0)[::-1][cut:].sum(), np.sort(lb5)[::-1][cut:].sum(),
             np.sort(lb5)[::-1][cut:].sum() - np.sort(lb0)[::-1][cut:].sum()))
