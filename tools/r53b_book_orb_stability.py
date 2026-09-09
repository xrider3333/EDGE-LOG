"""
ROUND 53b - is the book's preference for an opening-range leg STABLE, or is it noise? (2026-09-09)

Round 53 ranks opening-range configurations by what they do for the four-leg book. That ranking means
nothing on its own: this session showed that ranking those same configurations by their OWN
return-over-drawdown has no forward skill, and there is no reason to assume ranking them by their book
contribution behaves differently until somebody measures it.

So: cut the selection stretch in half. Rank every variant on the first half, rank them again on the
second, and ask whether the two agree. If a leg that helps the book through 2010-2017 is a coin flip
for 2017-2025, then "the best book leg" is a fitted number and the incumbent stays. Prints the rank
correlation between halves, what the first half's winner went on to do, and where the incumbent and
the crown sit in each half.

Self-contained on purpose: it re-declares the same legs as round 53 rather than importing it, because
importing that module would re-run its whole sweep.
"""
import os
import sys
import importlib.util as ilu

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
LB0 = pd.Timestamp("2025-06-30")
MID = pd.Timestamp("2017-12-31")
CACHE = {}

NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1, "daytype_mode": "skip_bot_short",
               "band_mult_long": 0.75, "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}
ORB_BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0,
                trail_bars=0, flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.0,
                target_R=5.5, be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)
CROWN = dict(ORB_BASE, atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0, be_after_R=0.5)


def defaults(fn):
    sp = ilu.spec_from_file_location("m", fn)
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def daily(fn, inst, tf, sess, cost, mult, params=None):
    key = (fn, inst, tf, sess, cost, mult, repr(params))
    if key not in CACHE:
        src = "db_noadj_rth" if sess == "rth" else "db_noadj_eth"
        A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
        idx = pd.DatetimeIndex(A["index"])
        r = run_backtest(fn, arrays=A, params=(params if params is not None else defaults(fn)),
                         cost_pts=cost, return_trades=True)
        s = pd.Series([t[2] * mult for t in r["trades"]],
                      index=[idx[t[1]].tz_localize(None).normalize() for t in r["trades"]])
        CACHE[key] = s.groupby(level=0).sum().sort_index()
    return CACHE[key]


def dd_of(s):
    s = s.sort_index()
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


ENGUQ = ("augur_strategies/ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None)
TTM = ("augur_strategies/TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None)
NOISE = ("augur_strategies/NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN)

print("building the three fixed legs", flush=True)
REST = [(daily(*ENGUQ), 1.0), (daily(*TTM), 3.0), (daily(*NOISE), 1.0)]

VARIANTS = [("#234 incumbent", dict(ORB_BASE)), ("#314 crown", dict(CROWN))]
for sf in (2.0, 2.5, 3.0):
    for tr in (4.0, 5.0, 5.5, 6.0):
        for be in (0.5, 1.0):
            for af, vf in ((0.7, 0.7), (0.75, 0.8), (0.0, 0.0)):
                for ob in (1, 2, 3):
                    p = dict(ORB_BASE, stop_frac=sf, target_R=tr, be_after_R=be,
                             atr_filter=af, vpace_filter=vf, or_bars=ob)
                    if any(v[1] == p for v in VARIANTS):
                        continue
                    VARIANTS.append(("s%.1f t%.1f be%.1f f%.2f/%.2f ob%d" % (sf, tr, be, af, vf, ob), p))
print("scoring %d variants on each half of the selection stretch" % len(VARIANTS), flush=True)


def book_mar(orb_s, lo, hi):
    parts = [p * w for p, w in REST] + [orb_s]
    s = pd.concat(parts, axis=1).sort_index().fillna(0).sum(axis=1)
    z = s[(s.index >= lo) & (s.index < hi)]
    dd = -dd_of(z)
    return (float(z.sum()) / dd) if dd > 0 else np.nan


rows = []
for i, (lab, p) in enumerate(VARIANTS):
    o = daily("augur_strategies/ORB_3_6.py", "NQ", "5m", "rth", 0.533, 20.0, p)
    rows.append({"book": lab,
                 "h1": book_mar(o, pd.Timestamp("2010-06-07"), MID),
                 "h2": book_mar(o, MID, LB0)})
    if i % 20 == 0:
        print("   %d/%d" % (i, len(VARIANTS)), flush=True)

df = pd.DataFrame(rows).dropna()
rho = df.h1.corr(df.h2, method="spearman")
df["r1"] = df.h1.rank(ascending=False)
df["r2"] = df.h2.rank(ascending=False)
w1 = df.sort_values("h1", ascending=False).iloc[0]
print("\n=== does the book's favourite opening-range leg stay its favourite? ===")
print("variants scored: %d" % len(df))
print("rank correlation between the two halves: %+.3f" % rho)
print("first half's winner: %s  (rank 1 of %d there, rank %.0f of %d in the second half)"
      % (w1.book, len(df), w1.r2, len(df)))
for nm in ("#234 incumbent", "#314 crown"):
    r = df[df.book == nm]
    if len(r):
        r = r.iloc[0]
        print("  %-16s first half rank %3.0f of %d | second half rank %3.0f of %d"
              % (nm, r.r1, len(df), r.r2, len(df)))
top = int(max(1, round(0.1 * len(df))))
keep = (df.sort_values("h1", ascending=False).head(top).r2 <= top).sum()
print("of the top %d in the first half, %d are still top %d in the second (chance would give ~%.1f)"
      % (top, keep, top, top * top / float(len(df))))
df.sort_values("h1", ascending=False).to_csv("_r53b_book_orb_stability.csv", index=False)
print("wrote _r53b_book_orb_stability.csv")
