"""
ROUND 49 — the book has no NOISE leg. Should it? (2026-09-09)

The adopted book is the opening-range crown, an ENGU-Q leg and three lots of the TTM structural-stop
leg. Round 48 showed swapping in the current ENGU-Q crown nearly triples its return-to-drawdown. The
NOISE family is crowned (run #304), paper-traded, and has never been in the book at all - and it is
the one family whose daily profits have historically shown little relation to the others.

Tested against round 48's winner as the new baseline, all on the same window and lockbox split:
  BASE   opening-range crown + ENGU-Q #335 crown + TTM structural-stop x3
  +N1    the same, plus the NOISE crown at weight 1
  +N2    plus NOISE at weight 2
  TTMx1  the base with TTM at weight 1 instead of 3 - a check that the weight-3 is not doing the work
  NOISE only, and each leg alone, are printed so the book can be judged against its parts

JUDGED ON RETURN-OVER-DRAWDOWN, NOT NET. Adding any positive leg raises net; the question is whether
it raises net faster than drawdown. Daily profits are pooled by EXIT day and SORTED before any running
total, every book's drawdown is checked against the bound that a sum's drawdown cannot exceed the sum
of its parts', and concentration is reported per stretch.
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
NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1, "daytype_mode": "skip_bot_short",
               "band_mult_long": 0.75, "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}   # run #304's own champion


def defaults(fn):
    sp = ilu.spec_from_file_location("m", fn); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


CACHE = {}


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
        print(f"  leg {os.path.basename(fn):26} {inst} {tf:3} @{cost:.3f}  days={len(CACHE[key]):5} "
              f"net=${CACHE[key].sum():>10,.0f}", flush=True)
    return CACHE[key]


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing, "daily index not in calendar order"
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


ORB = ("augur_strategies/ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, None)
E335 = ("augur_strategies/ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None)
TTM = ("augur_strategies/TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None)
NOISE = ("augur_strategies/NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN)
ROWS = []


def book(label, legs):
    parts = [daily(*spec) * w for spec, w in legs]
    s = pd.concat(parts, axis=1).sort_index().fillna(0).sum(axis=1)
    bound = sum(-dd_of(p) for p in parts)
    out = {"book": label}
    line = []
    for stage, sel in (("pre", s.index < LB0), ("lockbox", s.index >= LB0), ("whole", s.index == s.index)):
        z = s[sel]; net = float(z.sum()); dd = -dd_of(z)
        pos = z[z > 0].sum(); neg = -z[z < 0].sum(); pf = pos / neg if neg else 99
        srt = np.array(sorted(z.values, reverse=True)); top10 = float(srt[:10].sum())
        out[stage + "_net"] = round(net); out[stage + "_dd"] = round(dd)
        out[stage + "_mar"] = round(net / dd, 2) if dd > 0 else 99
        out[stage + "_pf"] = round(pf, 3)
        out[stage + "_top10"] = round(100 * top10 / net) if net > 0 else 999
        line.append(f"{stage} ${net:>9,.0f}/DD ${dd:>8,.0f} = {net/dd if dd else 99:6.2f}")
    assert out["whole_dd"] <= round(bound) + 1, f"drawdown exceeds bound {bound}"
    ROWS.append(out)
    print(f"  {label:26} " + " | ".join(line) + f"   PF {out['whole_pf']:.3f}  top10 pre {out['pre_top10']}%")


print("building legs\n")
BASE = [(ORB, 1.0), (E335, 1.0), (TTM, 3.0)]
print()
book("each leg alone: ORB", [(ORB, 1.0)])
book("each leg alone: ENGU-Q 335", [(E335, 1.0)])
book("each leg alone: TTM x3", [(TTM, 3.0)])
book("each leg alone: NOISE 304", [(NOISE, 1.0)])
print()
book("BASE (round 48 winner)", BASE)
book("+ NOISE weight 1", BASE + [(NOISE, 1.0)])
book("+ NOISE weight 2", BASE + [(NOISE, 2.0)])
book("BASE but TTM weight 1", [(ORB, 1.0), (E335, 1.0), (TTM, 1.0)])
print("\nleg-to-leg daily correlation (whole window, zeros filled):")
names = {"ORB": ORB, "ENGU-Q 335": E335, "TTM": TTM, "NOISE 304": NOISE}
al = pd.concat([daily(*s).rename(k) for k, s in names.items()], axis=1).sort_index().fillna(0)
print(al.corr().round(3).to_string())
with open("tools/r16_results/r49_book_add_noise.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r49_book_add_noise.csv")
