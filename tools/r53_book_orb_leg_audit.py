"""
ROUND 53 — the same staleness question, asked of the book's OPENING-RANGE leg (2026-09-09).

The book adopted today gained 26 percent of return-over-drawdown from one observation: it was carrying
the ENGU-Q leg that had stopped being the crown the day before. That is a class of defect, not a
one-off, so every other leg deserves the same question.

The opening-range leg is the obvious next candidate. The book uses run #234's configuration. But the
opening-range CROWN moved to run #314 on 2026-09-05 - #234 was explicitly kept as the CONTROL, and the
paper leg trades #314. So the book may be carrying a control rather than a crown, exactly as it was
with ENGU-Q.

The two differ in four settings: the volume-pace gate (0.7 against 0.8), the breakeven trigger (1.0 R
against 0.5 R), the stop width (2.0 against 2.5 range widths) and the target (5.5 R against 5.0), plus
a slightly stricter volatility filter.

Tested exactly as rounds 48 to 52 were: the adopted four-leg book with the opening-range slot filled
by each of the two, judged on return-over-drawdown in the selection window with the held-back year as
the guard, never on net. Daily profits pooled by exit day and sorted before any running total. These
numbers come from THIS harness so they compare to each other; anything that wins gets queued and
scored by the app before a claim is made, which is the round-51 lesson.
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
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}


def defaults(fn):
    sp = ilu.spec_from_file_location("m", fn); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


CACHE = {}


def daily(spec):
    fn, inst, tf, sess, cost, mult, params = spec
    key = (fn, cost, repr(params))
    if key not in CACHE:
        src = "db_noadj_rth" if sess == "rth" else "db_noadj_eth"
        A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
        idx = pd.DatetimeIndex(A["index"])
        r = run_backtest(fn, arrays=A, params=(params if params is not None else defaults(fn)),
                         cost_pts=cost, return_trades=True)
        s = pd.Series([t[2] * mult for t in r["trades"]],
                      index=[idx[t[1]].tz_localize(None).normalize() for t in r["trades"]])
        CACHE[key] = s.groupby(level=0).sum().sort_index()
        print(f"  leg {os.path.basename(fn):26} days={len(CACHE[key]):5} net=${CACHE[key].sum():>10,.0f}", flush=True)
    return CACHE[key]


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


ORB234 = ("augur_strategies/ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, None)
ORB314 = ("augur_strategies/ORB_3_6_R6.py", "NQ", "5m", "rth", 0.533, 20.0, None)
ENGUQ = ("augur_strategies/ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None)
TTM = ("augur_strategies/TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None)
NOISE = ("augur_strategies/NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN)
ROWS = []


def score(label, legs):
    parts = [daily(spec) * w for spec, w in legs]
    s = pd.concat(parts, axis=1).sort_index().fillna(0).sum(axis=1)
    bound = sum(-dd_of(p) for p in parts)
    out = {"book": label}
    line = []
    for stage, sel in (("pre", s.index < LB0), ("lb", s.index >= LB0), ("whole", s.index == s.index)):
        z = s[sel]; net = float(z.sum()); dd = -dd_of(z)
        pos = z[z > 0].sum(); neg = -z[z < 0].sum()
        srt = np.array(sorted(z.values, reverse=True))
        out[stage + "_net"] = round(net); out[stage + "_dd"] = round(dd)
        out[stage + "_mar"] = round(net / dd, 2) if dd > 0 else 99
        out[stage + "_pf"] = round(pos / neg, 3) if neg else 99
        out[stage + "_top10"] = round(100 * float(srt[:10].sum()) / net) if net > 0 else 999
        line.append(f"{stage} ${net:>10,.0f}/DD${dd:>8,.0f}={net/dd if dd else 99:6.2f}")
    assert -dd_of(s) <= bound + 1
    ROWS.append(out)
    print(f"  {label:38} " + " | ".join(line) + f"  PF {out['whole_pf']:.3f}")


print("building legs\n")
print("  the two opening-range legs alone:")
score("ORB #234 alone (what the book uses)", [(ORB234, 1.0)])
score("ORB #314 alone (the current crown)", [(ORB314, 1.0)])
print("\n  the adopted book with each in the opening-range slot:")
score("ADOPTED BOOK #366 (ORB #234)", [(ORB234, 1.0), (ENGUQ, 1.0), (TTM, 3.0), (NOISE, 1.0)])
score("same book with ORB #314 (crown)", [(ORB314, 1.0), (ENGUQ, 1.0), (TTM, 3.0), (NOISE, 1.0)])
score("both opening-range legs together", [(ORB234, 1.0), (ORB314, 1.0), (ENGUQ, 1.0), (TTM, 3.0), (NOISE, 1.0)])
c = pd.concat([daily(ORB234).rename("ORB234"), daily(ORB314).rename("ORB314")], axis=1).sort_index().fillna(0)
print(f"\n  the two opening-range legs correlate {c.ORB234.corr(c.ORB314):.3f} day to day")
with open("tools/r16_results/r53_book_orb_leg_audit.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r53_book_orb_leg_audit.csv")
