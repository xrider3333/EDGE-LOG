"""
ROUND 52 — is there a FIFTH leg? The validated dip book has never been in the book either (2026-09-09).

Round 51 validated the four-leg book (run #366): the opening-range crown, the current ENGU-Q crown,
three lots of the squeeze leg and the NOISE crown, at 38.18 return-over-drawdown on the selection
window against the adopted book's 30.25. The gain came entirely from noticing that a crowned,
paper-traded strategy had simply never been put in the book.

The same question applies to the one other strategy in the library that is crowned and validated and
absent: the NQ dip book (run #307, PASS). It is the only multi-day, long-only mechanism here - it buys
weakness and holds for days, where all four current legs are intraday - so if anything in the library
is uncorrelated with this book, it is that.

Judged exactly as round 51 was: return-over-drawdown on the selection window, the held-back year as a
guard, never net alone. The dip book bills its own dollars inside the plugin, so it enters at cost
zero and multiplier one, the same convention the ETF book used. Daily profits pooled by exit day and
sorted before any running total; every book's drawdown checked against the sum of its parts'.

NOTE ON THE BASELINE, which is the round-51 lesson: the numbers here are all produced by THIS harness,
so they are comparable to EACH OTHER but NOT to the app's run #366. Whatever wins here gets queued and
scored by the app before any claim is made against #366.
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
NQDIP_CROWN = {"rsi_len": 5, "pb_hold": 14, "cap_mult": 1.0, "pb_ema": 5, "cost_pts_rt": 0.783,
               "trend_len": 100, "rsi_exit": 9, "cost_bps": 2.0, "notional": 100000, "use_pb": True,
               "cap_hold": 5, "use_rsi": True, "cap_q": 0.3, "rsi_thr": 30, "dbl_n": 10,
               "use_cap": True, "use_dbl": True}   # run #307's own champion, read from the run doc


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
        print(f"  leg {os.path.basename(fn):26} {inst} {tf:3} days={len(CACHE[key]):5} "
              f"net=${CACHE[key].sum():>10,.0f}", flush=True)
    return CACHE[key]


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


LEGS = {
    "ORB": ("augur_strategies/ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, None),
    "ENGUQ": ("augur_strategies/ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None),
    "TTM": ("augur_strategies/TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None),
    "NOISE": ("augur_strategies/NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN),
    "NQDIP": ("augur_strategies/NQDIP_1_0.py", "NQ", "5m", "rth", 0.0, 1.0, NQDIP_CROWN),
}
print("building legs", flush=True)
ROWS = []


def score(label, members):
    parts = [daily(LEGS[k]) * w for k, w in members]
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
    print(f"  {label:30} " + " | ".join(line) + f"  top10 pre {out['pre_top10']}%")


FOUR = [("ORB", 1.0), ("ENGUQ", 1.0), ("TTM", 3.0), ("NOISE", 1.0)]
print()
score("NQDIP alone", [("NQDIP", 1.0)])
print()
score("FOUR-LEG (validated #366)", FOUR)
for w in (1.0, 2.0, 3.0):
    score(f"FIVE-LEG + NQDIP weight {w:g}", FOUR + [("NQDIP", w)])
print("\ncorrelation of the dip book with each existing leg (daily, zeros filled):")
base = pd.concat([daily(LEGS[k]).rename(k) for k in ("ORB", "ENGUQ", "TTM", "NOISE", "NQDIP")],
                 axis=1).sort_index().fillna(0)
print(base.corr()["NQDIP"].round(3).to_string())
with open("tools/r16_results/r52_book_add_nqdip.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r52_book_add_nqdip.csv")
