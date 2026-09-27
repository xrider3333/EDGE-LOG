"""Seed-averaged KEEL v12 on NOISE #304 and NOISE #382 - read against docs/PREREG_keel_bag_2026-09-26.md.

The bar was committed (696c00f) before this file computed a single bagged size. Build: per trade, the
MEAN of seven per-seed v12 sizes (primary bag seeds 90001-90007); two more bags (90011-17, 90021-27)
measure how much a bag still depends on its seeds; the seven already-seen single seeds (42, 1042 ..
6042) give the single-seed median. Round-60 tape and stretches; engine as on main (gap_atr fixed).

    python tools/keel_bag_check.py --leg 304     # walks + caches per-seed sizes (~60 min per leg)
    python tools/keel_bag_check.py --leg 382
    python tools/keel_bag_check.py --report      # reads both caches, applies P1-P4, prints the verdict
"""
import argparse
import importlib.util as ilu
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine import ml_keel as K                                 # noqa: E402
from augur_engine.analytics import sortino_from_pnls                  # noqa: E402
from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

LAST = "2026-09-16"
WF0, LB0 = pd.Timestamp("2016-06-30"), pd.Timestamp("2025-07-16")
MULT, ACCT, COST = 20.0, 100000.0, 0.533
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
LEGS = {"304": ("NOISE #304", "NOISE_1_0.py", CROWN),
        "382": ("NOISE #382", "NOISE_1_8_CT304.py", dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0))}
SINGLE = (42, 1042, 2042, 3042, 4042, 5042, 6042)
BAGS = (tuple(range(90001, 90008)), tuple(range(90011, 90018)), tuple(range(90021, 90028)))
CACHE = os.path.join(os.environ.get("KEEL_BAG_CACHE", r"C:\EdgeLog\_anatomy_cache\keel_bag"))


def mod(fn):
    sp = ilu.spec_from_file_location(fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def walk(leg):
    name, fn, params = LEGS[leg]
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    idx = pd.DatetimeIndex(A["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    assert "atr14_prior" in open(os.path.join(ROOT, "augur_engine", "ml_keel.py"), encoding="utf-8").read(), \
        "engine predates the gap_atr fix (85be1b8) - pull main first"
    r = run_backtest(mod(fn), arrays=A, params=params, cost_pts=COST, return_trades=True)
    T = sorted(r["trades"], key=lambda z: z[0])
    F = K.keel_features(A)
    out = {}
    for s in SINGLE + sum(BAGS, ()):
        kw = K.keel_walk(A, T, feats=F, version="v12", seed=s)
        out["s%d" % s] = np.asarray(kw["size"], float)
        print(f"{name} seed {s}: mean size {out['s%d' % s].mean():.4f}", flush=True)
    out["P"] = kw["P"] * MULT
    out["d"] = np.array([idx[max(int(e) - 1, 0)].value for e in kw["E"]], np.int64)
    out["end"] = np.array([idx[-1].value], np.int64)
    os.makedirs(CACHE, exist_ok=True)
    np.savez(os.path.join(CACHE, "leg%s.npz" % leg), **out)
    print("cached", os.path.join(CACHE, "leg%s.npz" % leg))


def stats(d, p, a, b, end):
    m = (d >= a) & ((d < b) if b is not None else True)
    q = p[m]
    yrs = ((b if b is not None else end) - a).days / 365.25
    cum = np.cumsum(q)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    return dict(net=float(q.sum()), dd=dd, mar=(q.sum() / yrs) / dd if dd > 0 else 0.0,
                roc=100 * q.sum() / yrs / ACCT, sortino=sortino_from_pnls(list(q), yrs) or 0.0)


def both(d, p, end):
    return stats(d, p, WF0, LB0, end), stats(d, p, LB0, None, end)


def spread(xs):
    xs = np.asarray(xs, float)
    return xs.max() / xs.min() - 1 if xs.min() > 0 else float("inf")


def report():
    verdict = {}
    for leg, (name, _, _) in LEGS.items():
        z = np.load(os.path.join(CACHE, "leg%s.npz" % leg))
        d, P, end = pd.DatetimeIndex(z["d"]), z["P"], pd.Timestamp(int(z["end"][0]))
        raw = both(d, P, end)
        single = {s: both(d, P * z["s%d" % s], end) for s in SINGLE}
        bags = [both(d, P * np.mean([z["s%d" % s] for s in bag], axis=0), end) for bag in BAGS]
        med = {st: {k: float(np.median([single[s][i][k] for s in SINGLE])) for k in ("net", "dd", "mar", "roc", "sortino")}
               for i, st in enumerate(("wf", "lb"))}
        print(f"\n{name}   (WF 2016-06-30..2025-07-16 | LB 2025-07-16..{end.date()})")
        print(f"  {'':22s} {'WF ROC':>7s} {'WF MAR':>7s} {'WF Sort':>7s} {'WF DD':>8s} | {'LB ROC':>7s} {'LB MAR':>7s}"
              f" {'LB Sort':>7s} {'LB DD':>8s}")
        rows = [("raw", raw), ("single seed 42", single[42]),
                ("single-seed median", ({**med["wf"]}, {**med["lb"]}))] + \
               [("bag %d (seeds %d-%d)" % (i + 1, b[0], b[-1]), bags[i]) for i, b in enumerate(BAGS)]
        for lab, (w, lb) in rows:
            print(f"  {lab:22s} {w['roc']:>7.1f} {w['mar']:>7.2f} {w['sortino']:>7.2f} {w['dd']:>8,.0f} | "
                  f"{lb['roc']:>7.1f} {lb['mar']:>7.2f} {lb['sortino']:>7.2f} {lb['dd']:>8,.0f}")
        w, lb = bags[0]
        p1 = w["mar"] >= raw[0]["mar"] and w["sortino"] >= raw[0]["sortino"]
        p2 = w["mar"] >= 0.97 * med["wf"]["mar"] and w["sortino"] >= 0.97 * med["wf"]["sortino"]
        p3 = lb["mar"] >= raw[1]["mar"]
        s_lb, b_lb = spread([single[s][1]["net"] for s in SINGLE]), spread([b[1]["net"] for b in bags])
        s_wf, b_wf = spread([single[s][0]["net"] for s in SINGLE]), spread([b[0]["net"] for b in bags])
        p4 = b_lb <= 0.5 * s_lb and b_wf <= 0.5 * s_wf
        print(f"  P1 beats raw on WF MAR + Sortino ........ {'PASS' if p1 else 'FAIL'}")
        print(f"  P2 >= 97% of single-seed median on WF ... {'PASS' if p2 else 'FAIL'}")
        print(f"  P3 LB MAR >= raw ........................ {'PASS' if p3 else 'FAIL'}")
        print(f"  P4 steadier: LB net spread {100 * b_lb:.1f}% vs single {100 * s_lb:.1f}%, WF {100 * b_wf:.1f}% vs "
              f"{100 * s_wf:.1f}% ... {'PASS' if p4 else 'FAIL'}")
        verdict[leg] = (p1, p2, p3, p4)
    ok = all(all(v) for v in verdict.values())
    print(f"\nPRE-REGISTERED VERDICT: {'PASS' if ok else 'FAIL'}  "
          + "  ".join(f"#{k} P1-P4 {''.join('Y' if x else 'n' for x in v)}" for k, v in verdict.items()))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", choices=sorted(LEGS))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.report:
        sys.exit(report())
    walk(a.leg)
