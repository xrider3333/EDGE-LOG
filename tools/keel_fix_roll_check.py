"""KEEL v12: size the gap_atr look-ahead fix and the contract-roll contamination (2026-09-26, MANAGER).

Two questions, one tape (NQ 5m RTH, 2010-06-07 .. 2026-09-16, cost 0.533, the round-60 stretches:
walk-forward 2016-06-30 .. 2025-07-16, lockbox from 2025-07-16), on NOISE #304 (crown, NOISE_1_0.py)
and NOISE #382 (the live Webull base, NOISE_1_8_CT304.py 30-min 2.0x):

 1. LOOK-AHEAD. gap_atr = (day open - prior close) / ATR14, and the ATR it divides by includes the
    bar's OWN high/low/close (found in book round 58, inbox item from the frontier chat). The fix lags
    that ATR one bar. Measured here WITHOUT editing the engine: extra_features is re-built from its own
    source with the one division changed, so the live model is untouched until the Webull lane ships.
 2. ROLLS. KEEL refits on the UNADJUSTED master. NOISE is flat by the close, so no trade P&L crosses a
    between-session switch - but gap_atr reads every roll gap as a huge opening gap, and the 2026-09-14
    11:30 ET splice (about +297.5 points of carry INSIDE a session) is a fake trade in the training set.
    Roll-corrected = features built on a Panama back-adjusted copy (the 64 raw switches from
    tools/data/contract_switches_NQ.csv, plus June 2026 at +298 before the 06-15 open and September 2026
    at +297.5 from the 09-14 11:30 bar - the ROLL_AUDIT.md central estimates), and every trade open
    across a switch dropped from the walk. Its effect is judged against the fix alone on the SAME trades.

    python tools/keel_fix_roll_check.py              (~25 min)
    python tools/keel_fix_roll_check.py --seeds 8    the NOISE FLOOR: the fixed model refit with 8 other
                                                     seeds; a change smaller than this spread is not a change
"""
import importlib.util as ilu
import inspect
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools", "rollaudit"))
import rollaudit_lib as RL                                            # noqa: E402
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
BASES = (("NOISE #304", "NOISE_1_0.py", CROWN),
         ("NOISE #382", "NOISE_1_8_CT304.py", dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0)))
# 2026 switches the raw table does not have (ROLL_AUDIT.md 6.3 central estimates), ET wall clock
EXTRA = (("2026-06-15 03:30", 298.0), ("2026-09-14 11:30", 297.5))

_OLD = "gap = (day_open.to_numpy() - pc_on_bars) / atr14.to_numpy()"
_NEW = "gap = (day_open.to_numpy() - pc_on_bars) / atr14.shift(1).to_numpy()"
_src = inspect.getsource(K.extra_features)
assert _src.count(_OLD) == 1, "extra_features changed - update this check (the fix may already be in)"
_ns = dict(vars(K))
exec(_src.replace(_OLD, _NEW).replace("def extra_features(", "def extra_features_fixed("), _ns)
EXTRA_FIXED = _ns["extra_features_fixed"]
EXTRA_SHIPPED = K.extra_features


def feats(arrays, fixed):
    K.extra_features = EXTRA_FIXED if fixed else EXTRA_SHIPPED
    try:
        return K.keel_features(arrays)
    finally:
        K.extra_features = EXTRA_SHIPPED


def switches():
    sw = RL.load_switches("NQ")
    s = list(zip(sw.switch_sec.to_numpy(np.int64), sw.contract_offset.to_numpy(float)))
    for et, off in EXTRA:
        s.append((int(pd.Timestamp(et).tz_localize("US/Eastern").tz_convert("UTC").value // 10**9), off))
    return sorted(s)


def adjusted(arrays, sw):
    sec = RL._sec(arrays["index"])
    add = np.zeros(len(sec))
    for s, off in sw:
        if np.isfinite(off):
            add[sec < s] += off
    out = dict(arrays)
    for k in ("open", "high", "low", "close"):
        out[k] = np.asarray(arrays[k], float) + add
    return out


def crosses(trades, index, sw):
    sec = RL._sec(index)
    ss = np.array([s for s, _ in sw], np.int64)
    return np.array([bool(((ss > sec[int(t[0])]) & (ss <= sec[int(t[1])])).any()) for t in trades])


def mod(fn):
    sp = ilu.spec_from_file_location(fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def stretch_stats(dates, pnl, a, b, end):
    m = np.ones(len(dates), bool)
    if a is not None:
        m &= dates >= a
    if b is not None:
        m &= dates < b
    q = pnl[m]
    yrs = ((b or end) - a).days / 365.25
    cum = np.cumsum(q)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max()) if len(q) else 0.0
    return dict(net=float(q.sum()), dd=dd, roc=100 * q.sum() / yrs / ACCT,
                sortino=sortino_from_pnls(list(q), yrs) or 0.0)


def seed_floor(n):
    """Refit the look-ahead-fixed model with n other seeds on each base and print the spread of each
    stretch's net, drawdown, ROC and Sortino - the yardstick the two changes above are judged against."""
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    idx = pd.DatetimeIndex(A["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    end = idx[-1]
    F = feats(A, True)
    for name, fn, params in BASES:
        r = run_backtest(mod(fn), arrays=A, params=params, cost_pts=COST, return_trades=True)
        T = sorted(r["trades"], key=lambda z: z[0])
        rows = []
        for sd in range(1, n + 1):
            kw = K.keel_walk(A, T, feats=F, version="v12", seed=K.SEED + 1000 * sd)
            d = pd.DatetimeIndex([idx[max(int(e) - 1, 0)] for e in kw["E"]])
            p = kw["P"] * MULT * np.asarray(kw["size"], float)
            w, lb = stretch_stats(d, p, WF0, LB0, end), stretch_stats(d, p, LB0, None, end)
            rows.append((w["net"], w["dd"], w["roc"], w["sortino"], lb["net"], lb["dd"], lb["roc"], lb["sortino"]))
            print(f"  {name} seed +{1000 * sd}: WF ${w['net']:,.0f} DD ${w['dd']:,.0f} ROC {w['roc']:.1f} "
                  f"Sortino {w['sortino']:.2f} | LB ${lb['net']:,.0f} DD ${lb['dd']:,.0f} ROC {lb['roc']:.1f} "
                  f"Sortino {lb['sortino']:.2f}", flush=True)
        R = np.array(rows)
        lab = ("WF net", "WF DD", "WF ROC", "WF Sortino", "LB net", "LB DD", "LB ROC", "LB Sortino")
        print(f"{name} seed floor over {n} refits (min .. max, and max/min - 1):")
        for j, nm in enumerate(lab):
            lo, hi = R[:, j].min(), R[:, j].max()
            print(f"    {nm:11s} {lo:>12,.2f} .. {hi:>12,.2f}   spread {100 * (hi / lo - 1) if lo > 0 else float('nan'):.1f}%")
    return 0


def main():
    if "--seeds" in sys.argv:
        return seed_floor(int(sys.argv[sys.argv.index("--seeds") + 1]))
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    idx = pd.DatetimeIndex(A["index"])
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    end = idx[-1]
    sw = switches()
    F_ship, F_fix = feats(A, False), feats(A, True)
    F_roll = feats(adjusted(A, sw), True)
    gi = F_ship[1].index("gap_atr")
    moved = np.abs(F_fix[0][:, gi] - F_ship[0][:, gi]) > 1e-12
    same = bool(np.allclose(np.delete(F_fix[0], gi, 1), np.delete(F_ship[0], gi, 1)))
    print(f"tape {idx[0].date()} .. {end.date()}  gap_atr moved by the fix on {100 * moved.mean():.1f}% of bars;"
          f" the other {len(F_ship[1]) - 1} features identical: {same}")
    rg = np.abs(F_roll[0][:, gi] - F_fix[0][:, gi]) > 1e-9
    print(f"roll correction moves gap_atr on {100 * rg.mean():.2f}% of bars (the switch-day openings)", flush=True)

    for name, fn, params in BASES:
        r = run_backtest(mod(fn), arrays=A, params=params, cost_pts=COST, return_trades=True)
        T = sorted(r["trades"], key=lambda z: z[0])
        cx = crosses(T, A["index"], sw)
        Tc = [t for t, c in zip(T, cx) if not c]
        runs = {}
        for lab, tr, F in (("shipped v12", T, F_ship), ("look-ahead fixed", T, F_fix),
                           ("fixed, clean trades", Tc, F_fix), ("fixed + roll-corrected", Tc, F_roll)):
            kw = K.keel_walk(A, tr, feats=F, version="v12")
            d = pd.DatetimeIndex([idx[max(int(e) - 1, 0)] for e in kw["E"]])
            runs[lab] = (d, kw["P"] * MULT, np.asarray(kw["size"], float))
        crossed = ", ".join(str(idx[int(t[0])].date()) for t, c in zip(T, cx) if c) or "none"
        print(f"\n{name}: {len(T)} trades, {int(cx.sum())} open across a switch ({crossed})")
        print(f"  {'':24s} {'WF net':>10s} {'DD':>8s} {'ROC%/yr':>8s} {'Sortino':>7s} | {'LB net':>9s} {'DD':>8s}"
              f" {'ROC%/yr':>8s} {'Sortino':>7s} | mean size")
        for lab, (d, p, s) in runs.items():
            w = stretch_stats(d, p * s, WF0, LB0, end)
            lb = stretch_stats(d, p * s, LB0, None, end)
            print(f"  {lab:24s} {w['net']:>10,.0f} {w['dd']:>8,.0f} {w['roc']:>8.1f} {w['sortino']:>7.2f} | "
                  f"{lb['net']:>9,.0f} {lb['dd']:>8,.0f} {lb['roc']:>8.1f} {lb['sortino']:>7.2f} | {s.mean():.3f}")
        for a, b in (("shipped v12", "look-ahead fixed"), ("fixed, clean trades", "fixed + roll-corrected")):
            (_, pa, sa), (_, pb, sb) = runs[a], runs[b]
            chg = np.abs(sb - sa) / np.maximum(sa, 1e-9)
            sh = np.round(10 * sa) != np.round(10 * sb)
            print(f"  {b} vs {a}: net {100 * ((pb * sb).sum() / (pa * sa).sum() - 1):+.2f}% whole tape; "
                  f"size moved >1% on {100 * (chg > 0.01).mean():.1f}% of trades, max {100 * chg.max():.1f}%; "
                  f"10-share base changes on {100 * sh.mean():.1f}% of trades", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
