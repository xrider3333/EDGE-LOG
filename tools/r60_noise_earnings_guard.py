# -*- coding: utf-8 -*-
"""NOISE ROUND 60 - mega-cap earnings reaction sessions, judged by the tilt battery.

Pre-registration: docs/PREREG_earnings_2026-09-24.md (committed 7ca2af2 BEFORE this file existed and before any
trade was tagged). Calendar: tools/data/megacap_earnings.csv (SEC 8-K Item 2.02, seven companies, 461 releases).

  python tools/r60_noise_earnings_guard.py     -> tools/r37_results/r60_earnings_guard.txt (tee it)
Run from the shared checkout (master registry lives there). Two engine backtests; a couple of minutes.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)          # engine + master registry + tilt_guard from the shared checkout
os.chdir(ROOT)
import importlib.util as ilu                                          # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402
from tools.tilt_guard import guard                                    # noqa: E402

MULT, COST = 20.0, 0.533
START, LAST = "2010-06-07", pd.Timestamp("2026-09-16").date()       # last Databento bar; Yahoo rows excluded
WF0, LB0 = pd.Timestamp("2016-05-02").date(), pd.Timestamp("2025-02-11").date()   # run #304's windows
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
BASES = [("PRIMARY - live crown #304", CROWN),
         ("REPLICATION - retired crown #243", dict(CROWN, lookback=44, vol_skip_pct=90.0))]

sp = ilu.spec_from_file_location("N10", os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py"))
N10 = ilu.module_from_spec(sp)
sp.loader.exec_module(N10)
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from=START)
IDX = pd.DatetimeIndex(A["index"])
SESS = np.array(sorted(set(d for d in IDX.date if d <= LAST)))

# ---- reaction sessions, exactly as pre-registered ----------------------------------------
cal = pd.read_csv(os.path.join(HERE, "tools", "data", "megacap_earnings.csv"))
react, by_tk = {}, {}
for tk, acc in zip(cal["ticker"], cal["accepted_et"]):
    t = pd.Timestamp(acc)
    day, hm = t.date(), t.hour * 60 + t.minute
    k = np.searchsorted(SESS, day, side="right" if hm >= 16 * 60 else "left")
    if k >= len(SESS):
        continue
    s = SESS[k]
    react.setdefault(s, set()).add(tk)
REACT = set(react)
pos = {d: i for i, d in enumerate(SESS)}
BEFORE = {SESS[pos[d] - 1] for d in REACT if pos[d] > 0}
WEEKS = {(d.isocalendar()[0], d.isocalendar()[1]) for d in REACT}
print("reaction sessions %d of %d (%.1f%%), placebo sessions %d, earnings-season weeks %d"
      % (len(REACT), len(SESS), 100 * len(REACT) / len(SESS), len(BEFORE), len(WEEKS)))
print("sessions with 2+ releases: %d" % sum(1 for v in react.values() if len(v) > 1))


def evr(p):
    p = np.asarray(p, float)
    if len(p) < 2:
        return float("nan")
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    return (1 - (p > 0).mean()) * ((gw / gl if gl > 0 else 99.0) - 1)


out = {}
for name, params in BASES:
    r = run_backtest(N10, arrays=A, params=params, cost_pts=COST, return_trades=True)
    t = sorted(r["trades"], key=lambda z: z[0])
    sig = np.array([IDX[max(int(x[0]) - 1, 0)].date() for x in t])
    keep = sig <= LAST
    t = [x for x, k in zip(t, keep) if k]
    sig = sig[keep]
    pnl = np.array([x[2] * MULT for x in t], float)
    ts = pd.DatetimeIndex([IDX[int(x[0])] for x in t])
    mask = np.array([d in REACT for d in sig])
    plac = np.array([d in BEFORE and d not in REACT for d in sig])
    sub = np.array([(d.isocalendar()[0], d.isocalendar()[1]) in WEEKS for d in sig])
    wf = (sig >= WF0) & (sig < LB0)
    lb = sig >= LB0
    is_ = sig < WF0
    print("\n" + "#" * 110 + "\n" + name + ": %d trades, %d tagged (%.1f%%), %d placebo, %d in earnings-season weeks"
          % (len(pnl), mask.sum(), 100 * mask.mean(), plac.sum(), sub.sum()))
    print("%-14s %8s %8s %8s %8s | %8s %8s %8s" % ("stretch", "n tag", "EV R tag", "EV R rest", "$/trade",
                                                   "n plac", "EVR plac", "EVR seas"))
    signs = []
    for nm, m in (("IS", is_), ("WF", wf), ("LB", lb)):
        a, b, c = pnl[mask & m], pnl[~mask & m], pnl[plac & m]
        s_ = pnl[sub & ~mask & m]
        signs.append(evr(a) - evr(b))
        print("%-14s %8d %8.3f %8.3f %8.0f | %8d %8.3f %8.3f" % (nm, len(a), evr(a), evr(b),
              a.mean() if len(a) else float("nan"), len(c), evr(c), evr(s_)))
    res = guard(pnl, ts, np.ones(len(pnl)), mask, 1.5, wf, lb, subgroup=sub, placebo_mask=plac,
                permute="days", label="earnings reaction sessions 1.5x - " + name, perm=2000)
    print(res["report"])
    print("  VERDICT (H1, pre-registered):", "PASSES THE BATTERY" if res["passed"] else "FAILS")
    out[name] = dict(passed=res["passed"], signs=signs, pnl=pnl, ts=ts, mask=mask, plac=plac, sub=sub,
                     wf=wf, lb=lb, sig=sig)

    # descriptive only - never adoptable (pre-registration, 'What happens to a NO')
    tick = np.array([",".join(sorted(react.get(d, ()))) for d in sig])
    print("  per company (descriptive, WF+LB only):")
    for tk in ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"):
        m = np.array([tk in s.split(",") for s in tick]) & (wf | lb)
        print("    %-5s n %4d  EV R %6.3f  net $%9s" % (tk, m.sum(), evr(pnl[m]), format(int(pnl[m].sum()), ",")))
    multi = np.array([len(react.get(d, ())) > 1 for d in sig]) & (wf | lb)
    print("    2+ releases same session  n %4d  EV R %6.3f" % (multi.sum(), evr(pnl[multi])))

print("\n" + "=" * 110)
both = all(v["passed"] for v in out.values())
print("H1 (1.5x on reaction sessions), BOTH bases:", "PASS" if both else "FAIL")
neg_all = all(all(s < 0 for s in v["signs"]) for v in out.values())
if not both and neg_all:
    print("\nPOST-HOC (not pre-registered direction): bucket negative in all stretches on both bases -> 0.5x shrink")
    for name, v in out.items():
        res = guard(v["pnl"], v["ts"], np.ones(len(v["pnl"])), v["mask"], 0.5, v["wf"], v["lb"], subgroup=v["sub"],
                    placebo_mask=v["plac"], permute="days", label="POST-HOC earnings shrink 0.5x - " + name, perm=2000)
        print(res["report"])
        print("  POST-HOC VERDICT:", "passes (forward idea only)" if res["passed"] else "FAILS")
elif not both:
    print("bucket not negative in every stretch on both bases -> no post-hoc shrink test (pre-registered rule)")
