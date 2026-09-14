# -*- coding: utf-8 -*-
"""NOISE ROUND 56b -- the squeeze FILTER on both bases, same scorecard basis as round 56.

Run #321 (squeeze filter, 30-min gate, on the retired #243 base) has the best profit factor of any
NOISE config in every period. It has never been measured on the live crown, nor with the textbook
hourly gate. The filter keeps a trade only if the squeeze was compressed at its decision bar and
changes nothing else (it is a post-hoc subset in the strategy file), so each row is an exact subset
of its base's trades. Also reports the sealed-year drawdown and a resampled 95th-percentile
drawdown for every row, because a filter trades a third as often and full-window net-over-drawdown
is the least reliable number in the house."""
import os, sys, importlib.util as ilu
import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402

END = pd.Timestamp("2026-07-16").date()
B0 = pd.Timestamp("2024-01-01").date()
S0 = pd.Timestamp("2025-07-16").date()


def load(fn):
    sp = ilu.spec_from_file_location(fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


N10, SQ = load("NOISE_1_0.py"), load("NOISE_1_1_SBS_V90_SQ.py")
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07")
IDX = pd.DatetimeIndex(A["index"])
H, L, C = (np.asarray(A[k], float) for k in ("high", "low", "close"))
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
V243 = dict(CROWN, lookback=44, vol_skip_pct=90.0)
GATES = {"30-min gate": (30, 16, 1.15), "hourly gate": (60, 20, 1.0)}
COMP = {k: SQ._compression(H, L, C, A["day_id"], A["index"], *g) for k, g in GATES.items()}


def trades(params, cost):
    r = run_backtest(N10, arrays=A, params=params, cost_pts=cost, return_trades=True)
    t = sorted(r["trades"], key=lambda z: z[0])
    b = np.array([int(x[0]) for x in t])
    d = np.array([IDX[i].date() for i in b])
    k = d < END
    return b[k], d[k], np.array([x[2] * 20.0 for x in t])[k]


def pf(q):
    return q[q > 0].sum() / -q[q < 0].sum()


def dd(q):
    e = np.cumsum(q)
    return float(np.max(np.maximum.accumulate(e) - e)) if len(q) else 0.0


def p95(q, n=2000):
    rng = np.random.default_rng(3)
    return float(np.percentile([dd(rng.permutation(q)) for _ in range(n)], 95))


print("%-30s | %5s %5s %9s %6s %6s %8s %9s | %6s %6s %6s %8s %8s | %5s %6s"
      % ("config", "n", "win%", "net $", "$/trd", "PF", "DD $", "p95 DD $", "PF<24", "PF24+", "sealPF", "seal $",
         "sealDD", "top10", "PFstr"))
for blab, base in (("#304 live crown", CROWN), ("#243 retired", V243)):
    b, d, p = trades(base, 0.533)
    bs, ds, ps = trades(base, 0.783)
    rows = [("%s (no filter)" % blab, np.ones(len(p), bool), np.ones(len(ps), bool))]
    for g in GATES:
        rows.append(("%s + %s filter" % (blab, g), np.array([bool(COMP[g][i - 1]) for i in b]),
                     np.array([bool(COMP[g][i - 1]) for i in bs])))
    for lab, m, ms in rows:
        q, qd = p[m], d[m]
        s = qd >= S0
        print("%-30s | %5d %5.1f %9s %6.0f %6.3f %8s %9s | %6.3f %6.3f %6.3f %8s %8s | %4.0f%% %6.3f"
              % (lab, len(q), 100 * (q > 0).mean(), format(int(q.sum()), ","), q.mean(), pf(q),
                 format(int(dd(q)), ","), format(int(p95(q)), ","), pf(q[qd < B0]), pf(q[qd >= B0]), pf(q[s]),
                 format(int(q[s].sum()), ","), format(int(dd(q[s])), ","), 100 * np.sort(q)[-10:].sum() / q.sum(),
                 pf(ps[ms])))
    print()
