"""
ROUND 48 — the adopted book still carries the EX-CROWN ENGU-Q leg (2026-09-09).

Run #361 is the book that was adopted yesterday: the opening-range crown, an ENGU-Q leg, and three
lots of the TTM structural-stop leg. Its ENGU-Q leg is the #309 efficiency file. But the ENGU-Q crown
MOVED to run #335 on 2026-09-08 - the R2 file, same mechanism with a 2.0 R breakeven and a 1.0 stop -
and the paper leg was swapped that night. The book was not. So the book is trading yesterday's crown.

This measures the swap, and one honesty check alongside it: the book costs its ENGU-Q leg at 0.533 a
round trip, which is the DAY-SESSION convention, while this leg trades the 24-hour tape where the
house convention is 0.783. Both are tested so the swap is not confounded with a cost change.

Four books, same window (2010-06-07..2026-06-30) and same lockbox split (last 12 months) as run #361:
  A  current #361 legs, ENGU-Q = #309 file at 0.533   (the adopted book, reproduced)
  B  ENGU-Q = #335 R2 crown at 0.533                  (the swap alone)
  C  ENGU-Q = #309 file at 0.783                      (the cost correction alone)
  D  ENGU-Q = #335 R2 crown at 0.783                  (both)
Daily PnL is pooled by EXIT day, SORTED before any running total (round-41 lesson), and every book's
drawdown is checked against the bound that a sum's drawdown cannot exceed the sum of its parts'.
Concentration is reported PER STRETCH, not just whole-window (round-47 lesson).
"""
import os, sys, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
LB0 = pd.Timestamp("2025-06-30")


def defaults(fn):
    sp = ilu.spec_from_file_location("m", fn); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


CACHE = {}


def leg(fn, inst, tf, sess, cost, mult, weight):
    key = (fn, inst, tf, sess, cost, mult)
    if key not in CACHE:
        src = "db_noadj_rth" if sess == "rth" else "db_noadj_eth"
        A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
        idx = pd.DatetimeIndex(A["index"])
        r = run_backtest(fn, arrays=A, params=defaults(fn), cost_pts=cost, return_trades=True)
        s = pd.Series([t[2] * mult for t in r["trades"]],
                      index=[idx[t[1]].tz_localize(None).normalize() for t in r["trades"]])
        CACHE[key] = s.groupby(level=0).sum().sort_index()
        p = CACHE[key].values
        print(f"  leg {os.path.basename(fn):28} {inst} {tf:3} @{cost:.3f}  days={len(p):5} net=${p.sum():>10,.0f}", flush=True)
    return CACHE[key] * weight


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing, "daily index not in calendar order"
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


ROWS = []


def book(label, legs):
    parts = [leg(*a) for a in legs]
    s = pd.concat(parts, axis=1).sort_index().fillna(0).sum(axis=1)
    assert s.index.is_monotonic_increasing
    bound = sum(-dd_of(p) for p in parts)
    out = {"book": label}
    for stage, sel in (("pre", s.index < LB0), ("lockbox", s.index >= LB0), ("whole", s.index == s.index)):
        z = s[sel]
        net = float(z.sum()); dd = -dd_of(z)
        pos = z[z > 0].sum(); neg = -z[z < 0].sum()
        pf = pos / neg if neg else 99
        srt = np.array(sorted(z.values, reverse=True))
        top10 = float(srt[:10].sum()); ex = float(srt[10:].sum())
        out[stage + "_net"] = round(net); out[stage + "_dd"] = round(dd)
        out[stage + "_mar"] = round(net / dd, 2) if dd > 0 else 99
        out[stage + "_pf"] = round(pf, 3)
        out[stage + "_top10"] = round(100 * top10 / net) if net > 0 else 999
        out[stage + "_ex"] = round(ex)
        print(f"  {label:34} {stage:8} net=${net:>10,.0f} DD=${dd:>9,.0f} n/DD={net/dd if dd else 99:6.2f} "
              f"PF={pf:5.3f} top10={round(100*top10/net) if net>0 else 999:>4}% ex=${ex:>10,.0f}")
    assert out["whole_dd"] <= round(bound) + 1, f"drawdown {out['whole_dd']} exceeds bound {bound}"
    print(f"  {'':34} (drawdown bound from the parts: ${bound:,.0f})")
    ROWS.append(out)


ORB = ("augur_strategies/ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, 1.0)
TTM = ("augur_strategies/TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, 3.0)
E309 = "augur_strategies/ENGUQ_1M_ETH_ER_1_0.py"
E335 = "augur_strategies/ENGUQ_1M_ETH_R2_1_0.py"
print("building legs\n")
for lab, fn, cost in (("A #361 as adopted (ENGU-Q #309 @0.533)", E309, 0.533),
                      ("B crown swap (ENGU-Q #335 @0.533)", E335, 0.533),
                      ("C cost fix only (ENGU-Q #309 @0.783)", E309, 0.783),
                      ("D swap + cost fix (ENGU-Q #335 @0.783)", E335, 0.783)):
    print()
    book(lab, [ORB, (fn, "NQ", "1m", "eth", cost, 20.0, 1.0), TTM])
with open("tools/r16_results/r48_book_crown_swap.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r48_book_crown_swap.csv")
