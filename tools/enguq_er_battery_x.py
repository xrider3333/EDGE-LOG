"""BATTERY X -- next generation of the ENGU-Q efficiency gate (2026-08-26, owner away:
"do more testing while im away. new / better params / versions of this").

The efficiency floor (run #265) is the only confirmation gate this project has ever had
survive a pre-registered bar, and it TRANSFERS to ES (STUDIES row 345). But today's ORB
attempt (run 278) and the ES lockbox both exposed the same weakness: a FIXED threshold
starves. When the tape gets choppier, a fixed 0.25 floor stops admitting trades entirely --
zero lockbox trades on ORB, zero on ES. That is the thing to fix.

VARIANTS (all strictly causal - every number known at the signal bar's close):
  A  PERCENTILE floor. Instead of "er >= 0.25", take a setup only if its er is in the top
     X% of the er values seen over a TRAILING window (expanding, past-only). Self-adjusting:
     the admitted fraction stays roughly constant as the market changes, so it cannot starve.
  B  SIGNED efficiency. The plain ratio is direction-blind (a clean move DOWN scores as high
     as a clean move up). ENGU-Q is long-only, so require the net move to be UP as well.
  C  DUAL window. Require efficiency on BOTH the last hour and the last four hours - the
     higher-timeframe confirmation idea, expressed through the one mechanism that works.

PRE-REGISTERED BARS (written before running, all three must pass):
  1. full-window PF > control PF
  2. the PF gain holds in >= 3 of 4 eras
  3. >= 40 trades in the held-out year  <-- the anti-starvation bar today's failures earned
A variant that passes all three is worth a validate slot. Nothing is adopted from a bench.
"""
import sys
import json
import importlib.util as ilu

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

spec = ilu.spec_from_file_location(
    "er", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_strategies\ENGUQ_1M_ETH_ER_1_0.py")
m = ilu.module_from_spec(spec); spec.loader.exec_module(m)

COST, MULT, LB = 0.533, 20.0, "2025-06-30"
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0, limit_atr=0.0)
ERAS = (("2010-01-01", "2014-01-01"), ("2014-01-01", "2018-01-01"),
        ("2018-01-01", "2022-01-01"), ("2022-01-01", "2027-01-01"))

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def er_raw(L, signed=False):
    """Kaufman efficiency over L bars, ending at each bar. signed=True keeps the sign of the
    net move (so a clean DOWN move scores negative and is rejected by a positive floor)."""
    prev = np.concatenate([np.full(L, np.nan), c[:-L]])
    net = c - prev
    chg = net if signed else np.abs(net)
    ad = np.abs(np.diff(c, prepend=c[0])); cs = np.cumsum(ad)
    path = cs - np.concatenate([np.zeros(L), cs[:-L]])
    return np.nan_to_num(np.where(path > 0, chg / np.maximum(path, 1e-9), 0.0))


def pct_floor(er, win, keep):
    """Rolling PERCENTILE floor, past-only. At each bar the threshold is the (1-keep)
    quantile of the er values over the previous `win` bars -- the current bar is EXCLUDED,
    so nothing about the present leaks into its own threshold. Sampled every `step` bars and
    held forward (a quantile over millions of bars is not needed exactly, only stably)."""
    step = 5000
    thr = np.zeros(len(er))
    q = 0.0
    for s in range(0, len(er), step):
        lo = max(0, s - win)
        if s > win // 4:
            past = er[lo:s]
            past = past[past > 0]
            if len(past) > 500:
                q = float(np.quantile(past, 1.0 - keep))
        thr[s:s + step] = q
    return thr


def run(mask):
    r = m.run_backtest(o, h, l, c, volumes=v, day_id=day, return_trades=True,
                       **{**CERT, "er_len": 60, "er_th": 0.0})
    tr = r["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])
    ei = np.array([int(t[0]) for t in tr])
    ent = pd.to_datetime([idx[i] for i in ei]).tz_localize(None)
    if mask is not None:
        k = mask[ei]
        d, ent = d[k], ent[k]
    if not len(d):
        return None
    pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
    lbm = ent >= pd.Timestamp(LB)
    eras = []
    for a, b in ERAS:
        mm = (ent >= pd.Timestamp(a)) & (ent < pd.Timestamp(b))
        x = d[mm]
        eras.append(x[x > 0].sum() / max(abs(x[x < 0].sum()), 1e-9) if len(x) else np.nan)
    eq = np.cumsum(d)
    return dict(n=len(d), net=float(d.sum()), pf=float(pf), eras=eras,
                dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                lb_n=int(lbm.sum()), lb_net=float(d[lbm].sum()))


base = run(None)
print(f"CONTROL (#226 raw): n={base['n']} net=${base['net']:,.0f} PF={base['pf']:.3f} "
      f"LB {base['lb_n']} trades\n")
er60 = er_raw(60)
ref = run(er60 >= 0.25)
print(f"run #265 (fixed 0.25): n={ref['n']} net=${ref['net']:,.0f} PF={ref['pf']:.3f} "
      f"LB {ref['lb_n']} trades\n")

rows = {}
def report(tag, s):
    if s is None:
        print(f"  {tag:34s} EMPTY"); return
    holds = sum(1 for g, u in zip(s["eras"], base["eras"]) if np.isfinite(g) and g > u)
    ok = (s["pf"] > base["pf"]) and holds >= 3 and s["lb_n"] >= 40
    rows[tag] = dict(s, holds=holds, passes=bool(ok))
    print(f"  {tag:34s} n={s['n']:5d} net=${s['net']:10,.0f} PF={s['pf']:.3f} "
          f"eras {holds}/4  LB {s['lb_n']:3d} tr  {'*** PASSES ***' if ok else ''}")

print("A - PERCENTILE floor (self-adjusting, cannot starve)")
for L in (60, 120):
    e = er_raw(L)
    for keep in (0.30, 0.40, 0.50, 0.60):
        report(f"A er{L} keep top {int(keep*100)}%", run(e >= pct_floor(e, 400000, keep)))

print("\nB - SIGNED efficiency (long-only: net move must be UP)")
for L in (60, 120):
    e = er_raw(L, signed=True)
    for th in (0.15, 0.25, 0.35):
        report(f"B signed er{L} >= {th}", run(e >= th))

print("\nC - DUAL window (hour AND four hours)")
e60, e240 = er_raw(60), er_raw(240)
for a in (0.20, 0.25):
    for b in (0.15, 0.25):
        report(f"C er60>={a} AND er240>={b}", run((e60 >= a) & (e240 >= b)))

json.dump(rows, open(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\_battery_x.json", "w"),
          indent=1, default=float)
win = [k for k, r_ in rows.items() if r_["passes"]]
print("\nPASSED ALL THREE BARS:", win or "none")
