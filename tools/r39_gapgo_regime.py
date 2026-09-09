"""
ROUND 39c — GAPGO: is there a BEFORE-THE-OPEN regime read that would have kept it out of June-July 2026?
Pre-registered 2026-09-08 (after the lockbox was opened by run #330 - so the 2025-08..2026-08 numbers are
INFORMATIONAL ONLY; the honest test is the pre-window 2010-06-07..2025-08-13, and any gate that helps
there would need a FRESH lockbox before it means anything).

Gates (all knowable before today's open; all computed on the previous 20 sessions only):
  G1 median |gap| / ATR20 of the trailing 20 sessions  -> skip the day when it is above X, X in {0.35, 0.45}
  G2 ATR20 / its own 250-session median (a vol-level read) -> skip when above Y, Y in {1.5, 2.0}
  G3 the inverse of G1: TRADE ONLY when the trailing median gap is above X (does the edge live in gappy tapes?)
Strategy = GAPGO_1_0 at run #330's params (gap 0.15 / stop 1.0 / 2 bars), NQ 5m RTH, $20/pt, 0.533/RT.
Reported: pre-window and spent-lockbox PnL with and without each gate, trades removed, PF, n/DD.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-08-13")
idx = pd.DatetimeIndex(A["index"]); o, h, l, c, did = A["open"], A["high"], A["low"], A["close"], A["day_id"]
d = pd.DataFrame({"did": did, "o": o, "h": h, "l": l, "c": c}); g = d.groupby("did")
day = pd.DataFrame({"o": g.o.first(), "c": g.c.last(), "h": g.h.max(), "l": g.l.min()})
day["rng"] = day.h - day.l
day["atr"] = day.rng.rolling(20).mean().shift(1)
day["gapr"] = (day.o - day.c.shift(1)).abs() / day.atr
day["medgap20"] = day.gapr.rolling(20).median().shift(1)            # previous 20 sessions' median gap/ATR
day["atr_rel"] = day.atr / day.atr.rolling(250).median()
r = run_backtest("augur_strategies/GAPGO_1_0.py", arrays=A, params=dict(be_after_R=1.0, gap_mult=0.15, stop_mult=1.0, or_bars=2),
                 cost_pts=0.533, return_trades=True)
tr = pd.DataFrame({"t": [idx[t[0]] for t in r["trades"]], "pnl": [t[2] * 20 for t in r["trades"]], "did": [did[t[0]] for t in r["trades"]]})
tr["medgap20"] = day.medgap20.reindex(tr.did).values; tr["atr_rel"] = day.atr_rel.reindex(tr.did).values
LB0 = pd.Timestamp("2025-08-13", tz=idx.tz)


def stats(s):
    p = s.pnl.values
    if len(p) == 0: return "n=0"
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); cum = np.cumsum(p); dd = (cum - np.maximum.accumulate(cum)).min()
    return f"n={len(p):5} net=${p.sum():>9,.0f} PF={gw/gl if gl else 99:.3f} DD=${-dd:>8,.0f} n/DD={p.sum()/-dd if dd < 0 else 99:5.2f}"


gates = [("no gate", lambda t: np.ones(len(t), bool))]
for X in (0.35, 0.45):
    gates.append((f"G1 skip when trailing median gap > {X} ATR", lambda t, X=X: ~(t.medgap20 > X).values))
for Y in (1.5, 2.0):
    gates.append((f"G2 skip when ATR20 > {Y}x its 250d median", lambda t, Y=Y: ~(t.atr_rel > Y).values))
for X in (0.25, 0.35):
    gates.append((f"G3 trade ONLY when trailing median gap > {X} ATR", lambda t, X=X: (t.medgap20 > X).values))
for lab, f in gates:
    keep = f(tr)
    pre = tr[(tr.t < LB0) & keep]; lb = tr[(tr.t >= LB0) & keep]
    print(f"{lab:48} PRE  {stats(pre)}   |   LOCKBOX(spent) {stats(lb)}")
print("\ntrailing-median-gap regime, pre-window trades bucketed (does GAPGO earn in gappy tapes?):")
pre = tr[tr.t < LB0]
b = pd.cut(pre.medgap20, [0, 0.2, 0.3, 0.4, 0.5, 9], labels=["<0.2", "0.2-0.3", "0.3-0.4", "0.4-0.5", ">0.5"])
for k, s in pre.groupby(b, observed=False): print(f"  medgap20 {k:8} {stats(s)}")
print("lockbox-year trades by the same buckets (informational):")
lb = tr[tr.t >= LB0]
b2 = pd.cut(lb.medgap20, [0, 0.2, 0.3, 0.4, 0.5, 9], labels=["<0.2", "0.2-0.3", "0.3-0.4", "0.4-0.5", ">0.5"])
for k, s in lb.groupby(b2, observed=False): print(f"  medgap20 {k:8} {stats(s)}")
