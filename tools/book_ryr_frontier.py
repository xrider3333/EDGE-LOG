"""
Does swapping the ROUND-28 FRONTIER LEGS into the leading pooled book beat it?

A parallel session's round-6 book study reports the current leaders on the owner metric:
  2-leg  NOISE_1_0 crown + ENGUQ_1M_ETH_LIM champion : EV R 0.46 · R / YR 148
  3-leg  + ORB_3_6                                    : EV R 0.334 · R / YR 152
Both use each family's CROWNED configuration. Round 28 found better legs on the owner's
own metric inside those same families (tools/ryr_search.py + ryr_neighbourhood.py):
  NOISE R / YR leader        R / YR 102.6 standalone (crown 74-77)
  ENGU-Q ER EV R leader      EV R 1.40 standalone (the library record)
This asks the only question that matters: pooled and scored as ONE strategy, do the
frontier legs beat the crowned legs?

Protocol (pre-registered): common window 2010-06-07..2025-06-29 (the lockbox is never
loaded), each leg run through the real engine with its own master, cost and multiplier,
trades converted to dollars per leg, pooled chronologically by EXIT time and scored as
one strategy the way the runner's BOOK job does. Reported per book: n, net, PF, win%,
max drawdown on the pooled curve, MAR, EV R, trades/yr, R / YR, 8-slice consistency, and
the daily-PnL correlation between legs.
"""
import os, sys, csv, itertools
from collections import defaultdict
import numpy as np
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")


def defaults(fn):
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", fn)); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


_ARR = {}


def arrays(inst, tf, sess, src):
    k = (inst, tf, sess, src)
    if k not in _ARR:
        _ARR[k] = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
    return _ARR[k]


def leg_trades(name, fn, inst, tf, sess, src, cost, mult, params=None):
    A = arrays(inst, tf, sess, src)
    p = params if params is not None else defaults(fn)
    r = run_backtest(fn, arrays=A, params=p, cost_pts=cost, return_trades=True)
    if not r:
        raise SystemExit(f"{name}: no result")
    idx = A["index"]
    out = [(idx[t[1]], t[2] * mult) for t in r["trades"]]      # (exit timestamp, dollars)
    ev = r.get("expectancy_r"); w = r["win_rate"] / 100.0
    if ev is None:
        ev = (1 - w) * (r["profit_factor"] - 1)
    yrs = (idx[-1] - idx[0]).days / 365.25
    print(f"  leg {name:34} n={r['num_trades']:5} net=${r['total_pnl']*mult:>10,.0f} PF={r['profit_factor']:.3f} "
          f"win={r['win_rate']:5.1f} EV R={ev:.3f} R/YR={ev*r['num_trades']/yrs:6.1f}", flush=True)
    return out


def score(pooled, label, yrs):
    s = sorted(pooled, key=lambda z: z[0])
    p = np.array([z[1] for z in s], float)
    if len(p) == 0:
        return None
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gw / gl if gl > 0 else 99.0
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); w = float((p > 0).mean())
    evr = (1 - w) * (pf - 1)
    tpy = len(p) / yrs
    k = len(p) // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k else 0
    return dict(book=label, n=len(p), net=round(net), pf=round(pf, 3), dd=round(-dd),
                mar=round(net / -dd, 2) if dd < 0 else 99, win=round(100 * w, 1),
                evr=round(evr, 3), tpy=round(tpy, 1), ryr=round(evr * tpy, 1), folds8=folds)


def corr(a, b):
    da, dbb = defaultdict(float), defaultdict(float)
    for t, v in a:
        da[pd.Timestamp(t).date()] += v
    for t, v in b:
        dbb[pd.Timestamp(t).date()] += v
    days = sorted(set(da) | set(dbb))
    x = np.array([da.get(d, 0.0) for d in days]); y = np.array([dbb.get(d, 0.0) for d in days])
    return float(np.corrcoef(x, y)[0, 1])


if __name__ == "__main__":
    print("building legs (common window 2010-06-07..2025-06-29)\n", flush=True)
    # --- crowned legs (what the leading book uses) ---
    NOISE_CROWN = {"daytype_lo": 0.25, "window": "all_day", "confirm_bars": 4, "daytype_mode": "skip_bot_short",
                   "band_mult_long": 0.75, "vol_skip_pct": 99.0, "band_mult_short": 1.25, "skip_holidays": False,
                   "stop_mode": "bandwidth", "flat_eod": True, "lookback": 51, "side": "Both", "daytype_hi": 0.6,
                   "stop_k": 1.25, "exit_mode": "vwap"}
    legs = {}
    legs["NOISE crown (#305)"] = leg_trades("NOISE crown (#305)", "NOISE_1_0.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0, NOISE_CROWN)
    legs["ENGU-Q LIM champ (#310)"] = leg_trades("ENGU-Q LIM champ (#310)", "ENGUQ_1M_ETH_LIM_1_0.py", "NQ", "1m", "eth", "db_noadj_eth", 0.783, 20.0)
    # --- round-28 frontier legs (no params = the fenced files reproduce their search leader) ---
    legs["NOISE R/YR frontier"] = leg_trades("NOISE R/YR frontier", "NOISE_1_2_RYR.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0, {})
    legs["ENGU-Q ER EV R 1.40"] = leg_trades("ENGU-Q ER EV R 1.40", "ENGUQ_1M_ETH_ER_RYR.py", "NQ", "1m", "eth", "db_noadj_eth", 0.783, 20.0, {})
    # --- the third leg both books can share ---
    legs["ORB crown (#234)"] = leg_trades("ORB crown (#234)", "ORB_3_6_C2.py", "NQ", "5m", "rth", "db_noadj_rth", 0.533, 20.0)

    A = arrays("NQ", "5m", "rth", "db_noadj_rth")
    yrs = (A["index"][-1] - A["index"][0]).days / 365.25
    BOOKS = [
        ("CROWNED 2-leg  (NOISE crown + ENGU-Q LIM)", ["NOISE crown (#305)", "ENGU-Q LIM champ (#310)"]),
        ("FRONTIER 2-leg (NOISE R/YR + ENGU-Q EV R)", ["NOISE R/YR frontier", "ENGU-Q ER EV R 1.40"]),
        ("MIXED 2-leg    (NOISE R/YR + ENGU-Q LIM)", ["NOISE R/YR frontier", "ENGU-Q LIM champ (#310)"]),
        ("MIXED 2-leg    (NOISE crown + ENGU-Q EV R)", ["NOISE crown (#305)", "ENGU-Q ER EV R 1.40"]),
        ("CROWNED 3-leg  (+ ORB crown)", ["NOISE crown (#305)", "ENGU-Q LIM champ (#310)", "ORB crown (#234)"]),
        ("FRONTIER 3-leg (+ ORB crown)", ["NOISE R/YR frontier", "ENGU-Q ER EV R 1.40", "ORB crown (#234)"]),
        ("ALL FIVE LEGS", list(legs)),
    ]
    rows = []
    print(f"\n{'book':44}{'n':>6}{'net$':>12}{'PF':>7}{'win%':>6}{'DD$':>10}{'MAR':>6}{'EVR':>6}{'tpy':>7}{'R/YR':>7} f8")
    for label, ks in BOOKS:
        pooled = [t for k in ks for t in legs[k]]
        s = score(pooled, label, yrs)
        rows.append(s)
        print(f"{label:44}{s['n']:>6}{s['net']:>12,}{s['pf']:>7.3f}{s['win']:>6.1f}{s['dd']:>10,}{s['mar']:>6.2f}"
              f"{s['evr']:>6.3f}{s['tpy']:>7.1f}{s['ryr']:>7.1f} {s['folds8']}/8")
    print("\nleg-to-leg daily correlation:")
    for a, b in itertools.combinations(legs, 2):
        print(f"  {a:28} ~ {b:28} {corr(legs[a], legs[b]):+.3f}")
    with open("tools/r16_results/book_ryr_frontier.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("\nsaved tools/r16_results/book_ryr_frontier.csv")
