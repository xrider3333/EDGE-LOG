# -*- coding: utf-8 -*-
"""NOISE ROUND 55c -- is the hourly squeeze's edge a boundary leak?

A longer verification bar beating a shorter one is exactly what a higher-timeframe look-ahead
produces (round 51 caught one in my own code). The code reads correctly -- a verification bar is
used only from its last base bar onward, and the tilt reads the decision bar -- but reading is not
proof. So the state is deliberately made OLDER:

  lag 0 bars   : as validated
  lag 1 bar    : the reading from one 5-minute bar earlier than the decision bar
  lag 1 hour   : the previous COMPLETE verification bar instead of the latest one

A squeeze is a slow state that persists for hours, so a genuine effect survives an hour of delay
with most of its value. A leak at the group boundary collapses the moment the boundary moves.

PRE-REGISTERED: the effect is a LEAK if, at the stressed cost, the one-hour-lagged tilt keeps less
than half of the as-validated tilt's walk-forward gain over the raw crown, or its shift null rises
above 5%.
"""
import os, sys, importlib.util as ilu
import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from tilt_guard import guard                                           # noqa: E402

sp = ilu.spec_from_file_location("N10", os.path.join(ROOT, "augur_strategies", "NOISE_1_0.py"))
N10 = ilu.module_from_spec(sp); sp.loader.exec_module(N10)

A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-07-16")
IDX = pd.DatetimeIndex(A["index"])
H, L, C = (np.asarray(A[k], float) for k in ("high", "low", "close"))
LB0 = pd.Timestamp("2025-07-16").date()
B0 = pd.Timestamp("2024-01-01").date()
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
             daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)


def compression(tf_min, glen, gratio, group_lag=0):
    """A line-for-line copy of the validated _compression, plus group_lag (0 = as validated)."""
    n = len(C)
    idx = pd.DatetimeIndex(A["index"])
    day = np.asarray(A["day_id"])
    first = pd.Series(idx).groupby(day).transform("first")
    off = ((pd.Series(idx) - first).dt.total_seconds() // 60).astype("int64").values
    bucket = off // int(tf_min)
    key = day.astype(np.int64) * 100000 + bucket.astype(np.int64)
    change = np.empty(n, bool); change[0] = True; change[1:] = key[1:] != key[:-1]
    gs = np.flatnonzero(change)
    ge = np.append(gs[1:], n) - 1
    hh = np.maximum.reduceat(H, gs)
    ll = np.minimum.reduceat(L, gs)
    cc = C[ge]
    s = pd.Series(cc)
    dev = s.rolling(glen).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(glen).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((2.0 * dev) / (1.5 * atr)).to_numpy()
    warm = glen * 2 + 5
    j = np.searchsorted(ge, np.arange(n), side="left")
    j = np.where(ge[np.clip(j, 0, len(ge) - 1)] <= np.arange(n), j, j - 1)
    j = j - int(group_lag)
    ok = j >= warm
    jj = np.clip(j, 0, len(ratio) - 1)
    out = np.zeros(n, bool)
    with np.errstate(invalid="ignore"):
        out[ok] = ratio[jj][ok] <= float(gratio)
    return out


# the copy must equal the validated function before any lag means anything
sq = ilu.spec_from_file_location("SQ", os.path.join(ROOT, "augur_strategies", "NOISE_1_1_SBS_V90_SQ.py"))
SQ = ilu.module_from_spec(sq); sq.loader.exec_module(SQ)
ref = SQ._compression(H, L, C, A["day_id"], A["index"], 60, 20, 1.0)
mine = compression(60, 20, 1.0, 0)
print("copy parity vs the validated function: %d of %d bars differ -> %s"
      % (int((ref != mine).sum()), len(ref), "PASS" if (ref == mine).all() else "FAIL"))
if not (ref == mine).all():
    sys.exit(1)

for cost in (0.783,):
    r = run_backtest(N10, arrays=A, params=CROWN, cost_pts=cost, return_trades=True)
    t = sorted(r["trades"], key=lambda z: z[0])
    bars = np.array([int(x[0]) for x in t])
    p = np.array([x[2] * 20.0 for x in t])
    d = np.array([IDX[b].date() for b in bars])
    ts = pd.DatetimeIndex([IDX[b] for b in bars])
    wf, lb = d < LB0, d >= LB0

    def pf(q):
        return q[q > 0].sum() / -q[q < 0].sum()

    print("\ncost %.3f   raw crown: walk-forward $%s, 2024+ PF %.3f" % (cost, format(int(p[wf].sum()), ","), pf(p[d >= B0])))
    print("%-34s %6s | %12s %8s %9s %8s | %s" % ("reading", "fires", "WF gain $", "kept", "LB gain $", "PF24+", "shift null / battery"))
    base_gain = None
    for gate in ((60, 20, 1.0), (30, 16, 1.15)):
        for lab, glag, blag in (("as validated", 0, 0), ("one 5-minute bar older", 0, 1), ("one full verification bar older", 1, 0),
                                ("two verification bars older", 2, 0)):
            comp = compression(*gate, group_lag=glag)
            m = np.array([bool(comp[b - 1 - blag]) for b in bars])
            q = p * np.where(m, 1.5, 1.0)
            g_wf = q[wf].sum() - p[wf].sum()
            if glag == 0 and blag == 0:
                base_gain = g_wf
            res = guard(p, ts, np.ones(len(p)), m, 1.5, wf, lb, permute="shift", perm=1000,
                        label="lag test")
            line = [x for x in res["report"].splitlines() if "SHIFT" in x]
            pct = line[0].split("->")[-1].strip() if line else "?"
            print("%-34s %5.0f%% | %12s %7.0f%% %9s %8.3f | %s ; %s"
                  % ("%d/%d/%.2f %s" % (gate[0], gate[1], gate[2], lab), 100 * m.mean(), format(int(g_wf), ","),
                     100 * g_wf / base_gain, format(int(q[lb].sum() - p[lb].sum()), ","), pf(q[d >= B0]), pct,
                     "PASS" if res["passed"] else "FAIL"))
        print()
