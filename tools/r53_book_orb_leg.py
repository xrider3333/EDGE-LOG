"""
ROUND 53 - the book's opening-range leg has never been varied. (2026-09-09)

Rounds 48-52 swapped the ENGU-Q leg, added the NOISE crown, tried a fifth leg and a weight ladder,
and every one of them held the opening-range leg fixed at the old #234 configuration. Meanwhile the
whole ORB programme has been asking which configuration is best ON ITS OWN - and this session showed
that question has no forward skill. The book asks a different question: which opening-range
configuration makes the BOOK best? A variant that earns a little less by itself but loses money on
different days from ENGU-Q, the squeeze and NOISE can lift the book while losing the solo contest.

Baseline is run #366's four legs: opening range x1, ENGU-Q #335 x1, squeeze structural-stop x3,
NOISE crown x1, judged on return-over-drawdown on the selection stretch with the lockbox reported.
CONTROLS THAT NOBODY HAS RUN: the book with NO opening-range leg at all, and with it at weight 2.
Daily profits pooled by exit day, sorted before any running total, drawdown checked against the
sum-of-parts bound, and the correlation of each variant with the rest of the book printed.
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


def daily(fn, inst, tf, sess, cost, mult, params=None, quiet=False):
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
        if not quiet:
            print("  leg %-30s net=$%10.0f" % (os.path.basename(fn), CACHE[key].sum()), flush=True)
    return CACHE[key]


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing, "daily index not in calendar order"
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


ENGUQ = ("augur_strategies/ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None)
TTM = ("augur_strategies/TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None)
NOISE = ("augur_strategies/NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN)


def orb_leg(params):
    return ("augur_strategies/ORB_3_6.py", "NQ", "5m", "rth", 0.533, 20.0, params)


print("building the three fixed legs", flush=True)
REST = [(daily(*ENGUQ), 1.0), (daily(*TTM), 3.0), (daily(*NOISE), 1.0)]
rest_s = pd.concat([p * w for p, w in REST], axis=1).sort_index().fillna(0).sum(axis=1)
rest_bound = sum(-dd_of(p * w) for p, w in REST)

ROWS = []


def score(label, orb_series, w_orb):
    parts = [p * wt for p, wt in REST] + ([orb_series * w_orb] if w_orb else [])
    s = pd.concat(parts, axis=1).sort_index().fillna(0).sum(axis=1)
    bound = rest_bound + ((-dd_of(orb_series * w_orb)) if w_orb else 0.0)
    row = {"book": label}
    for stage, sel in (("pre", s.index < LB0), ("lockbox", s.index >= LB0)):
        z = s[sel]
        net = float(z.sum())
        dd = -dd_of(z)
        row[stage + "_net"] = net
        row[stage + "_dd"] = dd
        row[stage + "_mar"] = (net / dd) if dd > 0 else 99.0
    assert -dd_of(s) <= bound + 1, "drawdown exceeds the sum-of-parts bound"
    if w_orb:
        j = pd.concat([orb_series.rename("o"), rest_s.rename("r")], axis=1).fillna(0)
        row["corr"] = float(j.o.corr(j.r))
        row["orb_net"] = float(orb_series.sum())
    else:
        row["corr"] = np.nan
        row["orb_net"] = 0.0
    ROWS.append(row)
    return row


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

print("scoring %d opening-range variants inside the book" % len(VARIANTS), flush=True)
score("NO opening-range leg", pd.Series(dtype=float), 0)
for i, (lab, p) in enumerate(VARIANTS):
    score(lab, daily(*orb_leg(p), quiet=True), 1.0)
    if i % 20 == 0:
        pd.DataFrame(ROWS).to_csv("_r53_book_orb_leg.csv", index=False)   # incremental: never lose a sweep
        print("   %d/%d" % (i, len(VARIANTS)), flush=True)
score("#234 at WEIGHT 2", daily(*orb_leg(dict(ORB_BASE)), quiet=True), 2.0)
score("#314 at WEIGHT 2", daily(*orb_leg(dict(CROWN)), quiet=True), 2.0)

df = pd.DataFrame(ROWS).sort_values("pre_mar", ascending=False)
df.to_csv("_r53_book_orb_leg.csv", index=False)   # written FIRST: a formatting slip must not cost the sweep
pd.set_option("display.width", 220)
base = df[df["book"] == "#234 incumbent"].iloc[0]
print("\n=== BOOK return-over-drawdown, selection stretch (to 2025-06-30), best first ===")
print("%-34s %10s %10s %8s %8s %7s %11s" % ("opening-range leg", "pre net", "pre DD", "pre MAR",
                                            "LB MAR", "corr", "leg net"))
for _, r in df.head(18).iterrows():
    c = r["corr"]
    print("%-34s %10.0f %10.0f %8.2f %8.2f %7s %11.0f"
          % (r["book"], r["pre_net"], r["pre_dd"], r["pre_mar"], r["lockbox_mar"],
             ("%.2f" % c) if c == c else "-", r["orb_net"]))
print("\nincumbent #234: pre MAR %.2f, lockbox MAR %.2f" % (base.pre_mar, base.lockbox_mar))
for nm in ("NO opening-range leg", "#314 crown", "#234 at WEIGHT 2", "#314 at WEIGHT 2"):
    r = df[df["book"] == nm].iloc[0]
    print("  %-24s pre MAR %6.2f (%+.2f vs incumbent) | lockbox MAR %6.2f"
          % (nm, r["pre_mar"], r["pre_mar"] - base["pre_mar"], r["lockbox_mar"]))
n_better = int((df["pre_mar"] > base["pre_mar"]).sum())
print("\n%d of %d variants beat the incumbent on the selection stretch" % (n_better, len(df)))
best = df.iloc[0]
print("best: %s | pre MAR %.2f vs %.2f | lockbox MAR %.2f vs %.2f | correlation with the rest %.2f vs %.2f"
      % (best["book"], best["pre_mar"], base["pre_mar"], best["lockbox_mar"], base["lockbox_mar"],
         best["corr"], base["corr"]))
print("wrote _r53_book_orb_leg.csv")
