"""
ROUND 54 - the staleness audit reaches the SQUEEZE leg, and this one looks like a real upgrade (2026-09-10).

Rounds 51 and 53 established the pattern: when a strategy earns a new crown, the paper account gets
swapped and the book does not. Round 51 caught it on the engulfing leg (+26 percent). Round 53 caught it
on the opening-range leg (+9 percent, confirmed by the app as run #373).

The squeeze leg is the third instance and the most lopsided one. The adopted book carries the
STRUCTURAL-STOP-ONLY squeeze file, which validated as run #353. But the crowned squeeze leg is run #369
- the combined leg, structural stop plus deep tilt plus open-bar tilt plus the one-bar fade exit. Their
own validates:

    run #353 (in the book)   net $55,912  drawdown $4,338  profit factor 2.967  274 trades
    run #369 (the crown)     net $77,105  drawdown $3,350  profit factor 3.210  273 trades

That is 38 percent more money on 23 percent LESS drawdown from the same number of trades - unlike the
opening-range swap, where the newer leg was weaker standalone. And the squeeze leg carries triple weight
in the book, so whatever it does gets multiplied.

A book with the combined leg does exist - run #371 - but it is the OLD THREE-LEG book (the superseded
engulfing file, no noise leg, the control opening range). Nobody has put the combined squeeze leg into
the current four-leg book.

Judged as rounds 48-53 were: return-over-drawdown on the selection window, the held-back year as the
guard, never net alone. Daily profits pooled by exit day and SORTED before any running total, with each
book's drawdown checked against the sum of its parts'. These numbers come from THIS harness so they
compare to each other; the winner gets queued and scored by the app before any claim is made.
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
        print(f"  leg {os.path.basename(fn):28} days={len(CACHE[key]):5} net=${CACHE[key].sum():>10,.0f}", flush=True)
    return CACHE[key]


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing, "pooled daily index is not in calendar order"
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


ORB234 = ("augur_strategies/ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, None)
ORB314 = ("augur_strategies/ORB_3_6_R6.py", "NQ", "5m", "rth", 0.533, 20.0, None)
ENGUQ = ("augur_strategies/ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None)
SS20 = ("augur_strategies/TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None)
COMB = ("augur_strategies/TTMSQZ_3_0_ES30SSOF2.py", "ES", "30m", "rth", 0.363, 50.0, None)
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
    print(f"  {label:40} " + " | ".join(line) + f"  PF {out['whole_pf']:.3f}")


print("building legs\n")
print("  the two squeeze legs alone, at the single weight:")
score("squeeze structural-stop only (in the book)", [(SS20, 1.0)])
score("squeeze COMBINED leg (the crown, #369)", [(COMB, 1.0)])
print("\n  the four-leg book, both opening-range files x both squeeze files:")
score("ADOPTED #366  ORB 234 + squeeze SS", [(ORB234, 1.0), (ENGUQ, 1.0), (SS20, 3.0), (NOISE, 1.0)])
score("RUN #373      ORB 314 + squeeze SS", [(ORB314, 1.0), (ENGUQ, 1.0), (SS20, 3.0), (NOISE, 1.0)])
score("candidate A   ORB 234 + squeeze COMBINED", [(ORB234, 1.0), (ENGUQ, 1.0), (COMB, 3.0), (NOISE, 1.0)])
score("candidate B   ORB 314 + squeeze COMBINED", [(ORB314, 1.0), (ENGUQ, 1.0), (COMB, 3.0), (NOISE, 1.0)])
print("\n  and the weight question re-asked on the better squeeze leg:")
for w in (2.0, 4.0, 5.0):
    score(f"candidate B with squeeze weight {w:g}", [(ORB314, 1.0), (ENGUQ, 1.0), (COMB, w), (NOISE, 1.0)])
c = pd.concat([daily(SS20).rename("ss"), daily(COMB).rename("comb")], axis=1).sort_index().fillna(0)
print(f"\n  the two squeeze legs correlate {c.ss.corr(c.comb):.3f} day to day")
os.makedirs("tools/r16_results", exist_ok=True)
with open("tools/r16_results/r54_book_squeeze_leg_audit.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r54_book_squeeze_leg_audit.csv")
