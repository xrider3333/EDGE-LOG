"""
ROUND 50 — does every leg in the book earn its slot? (2026-09-09)

Rounds 48 and 49 improved the adopted book twice by changing WHAT is in it rather than by tuning any
strategy: swapping the ex-crown ENGU-Q leg for the current crown, then adding the NOISE crown. This
round asks the other half of that question - whether any leg should come OUT - by scoring every
combination of the four legs on the same window and lockbox split.

The suspicion worth testing: the opening-range leg is the weakest of the four on its own (10.32
return-over-drawdown in the selection window against 12.75, 19.37 and 20.89 for the others), it is the
only pair with a meaningful correlation to another leg (0.42 with NOISE, since both trade the NQ day
session), and its own family was closed after roughly 180 tested variants. If it is carried by the
others, the book is better without it.

Every combination is judged on SELECTION-window return-over-drawdown with the lockbox reported beside
it, never on net - adding legs always raises net. Daily profits are pooled by exit day and sorted
before any running total; each book's drawdown is checked against the sum of its parts'; concentration
is reported per stretch. A combination only counts as better if it beats the incumbent on the
selection window AND does not give back more than a tenth of the lockbox.
"""
import os, sys, csv, itertools
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
}
print("building legs", flush=True)
for k, v in LEGS.items():
    print(f"  {k:6} days={len(daily(v)):5} net=${daily(v).sum():>10,.0f}", flush=True)
ROWS = []


def score(label, members):
    parts = [daily(LEGS[k]) * w for k, w in members]
    s = pd.concat(parts, axis=1).sort_index().fillna(0).sum(axis=1)
    bound = sum(-dd_of(p) for p in parts)
    out = {"book": label, "legs": " ".join(f"{k}x{w:g}" for k, w in members)}
    for stage, sel in (("pre", s.index < LB0), ("lb", s.index >= LB0)):
        z = s[sel]; net = float(z.sum()); dd = -dd_of(z)
        srt = np.array(sorted(z.values, reverse=True))
        out[stage + "_net"] = round(net); out[stage + "_dd"] = round(dd)
        out[stage + "_mar"] = round(net / dd, 2) if dd > 0 else 99
        out[stage + "_top10"] = round(100 * float(srt[:10].sum()) / net) if net > 0 else 999
    assert -dd_of(s) <= bound + 1
    ROWS.append(out)


for r in range(2, 5):
    for combo in itertools.combinations(LEGS, r):
        for ttm_w in ((1.0, 3.0) if "TTM" in combo else (1.0,)):
            members = [(k, ttm_w if k == "TTM" else 1.0) for k in combo]
            score("+".join(k + ("x3" if k == "TTM" and ttm_w == 3 else "") for k in combo), members)
ROWS.sort(key=lambda r: -r["pre_mar"])
print(f"\n{'book':34}{'sel net':>12}{'sel DD':>10}{'sel n/DD':>10}{'top10':>7}{'LB net':>11}{'LB DD':>10}{'LB n/DD':>9}")
for r in ROWS:
    star = "  <- incumbent (round 49)" if r["legs"] == "ORB x1 ENGUQ x1 TTM x3 NOISE x1".replace(" x", "x") else ""
    print(f"{r['book']:34}{r['pre_net']:>12,}{r['pre_dd']:>10,}{r['pre_mar']:>10.2f}{r['pre_top10']:>6}%"
          f"{r['lb_net']:>11,}{r['lb_dd']:>10,}{r['lb_mar']:>9.2f}{star}")
with open("tools/r16_results/r50_book_composition_sweep.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r50_book_composition_sweep.csv")
