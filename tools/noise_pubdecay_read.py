# -*- coding: utf-8 -*-
"""NOISE PUBLICATION-DECAY READ (python tools/noise_pubdecay_read.py) - computes exactly what docs/PRESTATED_noise_pubdecay_2026-10-15.md fixed (LF sha256
1cd933b5...), checked at start. Unit object = tools/noise_halves_read.trades() (#304 core, band units, cost 0.533);
dollar object = #422's crown via tools/noise_chain_read (per-contract re-costing). Report only."""
import hashlib
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(HERE)
REPO = ROOT
PRE = os.path.join(REPO, "docs", "PRESTATED_noise_pubdecay_2026-10-15.md")
SHA = "1cd933b545a32bf0b3be60c2bd17ebf23988fac774fd6cd10d2288ea42341998"
got = hashlib.sha256(open(PRE, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
if got != SHA:
    raise SystemExit("pre-stated file changed: %s" % got)
print("pre-stated read sha256 OK", SHA[:16])
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
os.environ.pop("AUGUR_TRIAL_CACHE", None)
os.environ.setdefault("NOISE_CHAIN_CACHE", r"C:\EdgeLog\_anatomy_cache\noise_tp_validate")
import noise_halves_read as HV           # noqa: E402
import noise_chain_read as C             # noqa: E402
from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.strategies import load_strategy               # noqa: E402

D = pd.Timestamp
P0, P1, Q0, PD0, S0 = D("2016-07-01"), D("2024-05-31"), D("2024-06-01"), D("2025-07-16"), D("2024-05-01")
B, SEED, MP = 2000, 20261015, 0.42

T, last = HV.trades()
T["d"] = pd.to_datetime(T["date"])
L = D(last)
T["m"] = T["d"].dt.to_period("M")
pre = T[(T.d >= P0) & (T.d <= P1)]
post = T[(T.d >= Q0) & (T.d <= L)]
pdz = T[(T.d >= PD0) & (T.d <= L)]
sens = T[(T.d >= S0) & (T.d <= L)]
pre_s = T[(T.d >= P0) & (T.d < S0)]
print("unit object: #304 core, NQ 5m RTH no-adjust to %s, cost 0.533, band units a trade" % last)


def month_boot(df, rng, n=B):
    g = [x.bu.to_numpy() for _, x in df.groupby("m")]
    k = len(g)
    out = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, k, k)
        v = np.concatenate([g[j] for j in pick])
        out[i] = v.mean()
    return out


def read(lab, a, b):
    rng = np.random.default_rng(SEED)
    ba, bb = month_boot(a, rng), month_boot(b, rng)
    se = np.std(bb - ba, ddof=1)
    drop = (1 - MP) * a.bu.mean()
    print("\n%s" % lab)
    print("  POWER (printed first): SE(POST - PRE) %.4f bu (month blocks); McLean-Pontiff drop 0.58 x PRE = %.4f bu = %.2f SE"
          " -> %s" % (se, drop, drop / se, "detectable (>= 2.5 SE)" if drop >= 2.5 * se else "UNDERPOWERED (< 2.5 SE)"))
    r = b.bu.mean() / a.bu.mean()
    lo, hi = np.percentile(bb / ba, [5, 95])
    print("  PRE  n %4d  months %3d  mean %+.4f bu   |  POST n %4d  months %3d  mean %+.4f bu" % (
        len(a), a.m.nunique(), a.bu.mean(), len(b), b.m.nunique(), b.bu.mean()))
    print("  R = POST/PRE %.2f   90%% CI %.2f .. %.2f   (contains 1.0: %s; contains 0.42: %s)" % (
        r, lo, hi, lo <= 1.0 <= hi, lo <= MP <= hi))
    c1, c42 = lo <= 1.0 <= hi, lo <= MP <= hi
    verdict = ("NO DETECTABLE DECAY" if c1 and not c42 else "DECAY CONSISTENT WITH McLEAN-PONTIFF" if c42 and not c1
               else "CAN'T TELL (underpowered)" if c1 and c42 else "EXCLUDES BOTH - report as printed")
    if drop < 2.5 * se:
        verdict += " [power line: underpowered]"
    print("  READING:", verdict)
    for nm, x in (("PRE", a), ("POST", b)):
        print("    %-4s held to close %4.1f%% (mean %+.2f bu) | VWAP exit %4.1f%% (mean %+.2f bu) | stop %4.1f%%" % (
            nm, 100 * (x.kind == "held to close").mean(), x[x.kind == "held to close"].bu.mean(),
            100 * (x.kind == "VWAP exit").mean(), x[x.kind == "VWAP exit"].bu.mean(), 100 * (x.kind == "stop").mean()))
    return r, lo, hi


read("MAIN: PRE 2016-07-01..2024-05-31 vs POST 2024-06-01..%s" % last, pre, post)
read("POST-DESIGN (report): PRE vs 2025-07-16..%s (lockbox spent + forward)" % last, pre, pdz)
read("SENSITIVITY: PRE 2016-07-01..2024-04-30 vs POST from 2024-05-01", pre_s, sens)
yr = T[T.d >= P0].groupby(T.d.dt.year).bu.agg(["count", "mean"])
print("\ncontext - band units a trade by year: " + ", ".join("%d %+.3f (%d)" % (y, r["mean"], r["count"]) for y, r in yr.iterrows()))

# ── dollars: #422's crown, four numbers per stretch ──
d = C.fetch(422)
champ = dict(d["validate"].get("champion") or d["best_params"])
st = load_strategy(os.path.join(REPO, "augur_strategies", d["strategy"]))
m = find_master("NQ", "5m", "rth", "db_noadj_rth")
A = load_master_arrays(m, date_from=d["date_from"], date_to=last)
bi = pd.DatetimeIndex(A["index"])
bi = bi.tz_convert("America/New_York").tz_localize(None) if bi.tz is not None else bi
TR = C.trades(st, A, champ, 0.533)
print("\nDOLLARS - NOISE #422 crown %s, $ at mult 20, four numbers per stretch (DD%% on $100k)" % champ)
for lab, lo, hi in (("PRE 2016-07-01..2024-05-31", P0, P1), ("POST 2024-06-01..%s" % last, Q0, L),
                    ("POST-DESIGN 2025-07-16..%s" % last, PD0, L)):
    sess = pd.Index(sorted({x.normalize() for x in bi if lo <= x.normalize() <= hi}))
    yrs = (hi - lo).days / 365.25
    tr = [t for t in TR if lo <= bi[int(t[0]) - 1].normalize() <= hi]
    dd = [bi[int(t[0]) - 1].normalize() for t in tr]
    for c in (0.533, 0.7825):
        print(C.line("%s @%.4f" % (lab, c), C.four(dd, [(float(t[2]) - t[-1] * (c - 0.533)) * 20 for t in tr], sess, yrs)))
