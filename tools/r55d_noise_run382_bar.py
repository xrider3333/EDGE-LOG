# -*- coding: utf-8 -*-
"""Judge run #382 against the bar pre-registered in NOISE_1_8_CT304.py -- like for like.

The bar's dollar figure ($84,580) was lifted from run #304's OWN lockbox, which ran 2025-02-11 to
2026-08-12 (18 months, 389 trades). Run #382's lockbox ran 2025-07-16 to 2026-07-16 (12 months).
Comparing those would be comparing different calendars, so every clause is re-measured here with
the crown and the tilt on #382's exact lockbox window, and the drawdown clause against a resampled
95th percentile as the file promised."""
import os, sys, importlib.util as ilu
import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402


def load(fn, alias):
    sp = ilu.spec_from_file_location(alias, os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


CT = load("NOISE_1_8_CT304.py", "CT")
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-07-16")
idx = pd.DatetimeIndex(A["index"])
L0, L1 = pd.Timestamp("2025-07-16").date(), pd.Timestamp("2026-07-16").date()


def tr(params):
    r = run_backtest(CT, arrays=A, params=params, cost_pts=0.533, return_trades=True)
    t = sorted(r["trades"], key=lambda z: z[0])
    d = np.array([idx[x[0]].date() for x in t])
    return np.array([x[2] * 20.0 for x in t]), d


def dd(p):
    e = np.cumsum(p)
    return float(np.max(np.maximum.accumulate(e) - e))


def boot_p95(p, n=4000, seed=7):
    rng = np.random.default_rng(seed)
    return float(np.percentile([dd(rng.permutation(p)) for _ in range(n)], 95))


rows = {}
for lab, s in (("crown (tilt off)", 1.0), ("tilt 1.5x", 1.5), ("tilt 2.0x  <- run 382 pick", 2.0)):
    p, d = tr(dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=s))
    m = (d >= L0) & (d < L1)
    q = p[m]
    w, l_ = q[q > 0].sum(), -q[q < 0].sum()
    rows[lab] = dict(n=len(q), net=q.sum(), pf=w / l_, dd=dd(q), p95=boot_p95(q), mar=q.sum() / dd(q))
    print("%-28s sealed n %3d net $%8s PF %.3f DD $%7s resampled-p95 DD $%7s net/DD %.2f"
          % (lab, len(q), format(int(q.sum()), ","), w / l_, format(int(dd(q)), ","),
             format(int(rows[lab]["p95"]), ","), q.sum() / dd(q)))

c = rows["crown (tilt off)"]
print()
for lab in ("tilt 1.5x", "tilt 2.0x  <- run 382 pick"):
    t = rows[lab]
    print("%s" % lab)
    print("   clause 1 verdict PASS ............................ yes (run 382: 6 of 6, PBO 0.111)")
    print("   clause 2 sealed net >= crown on the SAME window ... %s ($%s vs $%s)"
          % ("yes" if t["net"] >= c["net"] else "NO", format(int(t["net"]), ","), format(int(c["net"]), ",")))
    print("   clause 3 sealed DD <= 1.25x crown (realised) ...... %s (%.2fx)"
          % ("yes" if t["dd"] <= 1.25 * c["dd"] else "NO", t["dd"] / c["dd"]))
    print("   clause 3 sealed DD <= 1.25x crown (resampled p95) . %s (%.2fx)"
          % ("yes" if t["p95"] <= 1.25 * c["p95"] else "NO", t["p95"] / c["p95"]))
    print("   clause 4 MAR >= crown ............................. %s (%.2f vs %.2f)"
          % ("yes" if t["mar"] >= c["mar"] else "NO", t["mar"], c["mar"]))
