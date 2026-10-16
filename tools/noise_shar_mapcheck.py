# -*- coding: utf-8 -*-
"""python tools/noise_shar_mapcheck.py -> tools/r37_results/noise_shar_mapcheck_1015.txt
NOISE x shelf No. 42 (Patton & Sheppard 2015) - outcome-free map check, exactly as PRESTATED_noise_shar_mapcheck_2026-10-15.md
(LF sha256 52855576..., checked at start). No NOISE P&L is read: NQ 5m RTH returns only."""
import hashlib
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(HERE)
PRE = os.environ.get("NOISE_SHAR_PRESTATED") or os.path.join(os.path.dirname(HERE), "docs", "PRESTATED_noise_shar_mapcheck_2026-10-15.md")
SHA = "52855576230ba5a61a8d5217f951de0c9567a083aadb96007f86f4407acb001b"
got = hashlib.sha256(open(PRE, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
if got != SHA:
    raise SystemExit("pre-stated file changed: %s" % got)
print("pre-stated sha256 OK", SHA[:16])
sys.path.insert(0, REPO)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402

m = find_master("NQ", "5m", "rth", "db_noadj_rth")
A = load_master_arrays(m, date_from="2010-06-07", date_to="2025-07-15")
c = np.asarray(A["close"], float)
day = np.asarray(A["day_id"])
idx = pd.DatetimeIndex(A["index"])
idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
r = np.diff(np.log(c))
same = day[1:] == day[:-1]                        # intraday returns only: the overnight step is excluded
r, d_of = r[same], day[1:][same]
df = pd.DataFrame({"d": d_of, "r2": r * r, "pos": (r > 0) * r * r, "neg": (r < 0) * r * r})
g = df.groupby("d").sum()
dates = pd.Series(idx[np.r_[0, np.flatnonzero(np.diff(day)) + 1]].normalize(), index=np.unique(day))
D = pd.DataFrame({"date": dates.reindex(g.index).values, "RV": g.r2.values, "RSp": g.pos.values, "RSn": g.neg.values})
D["RVw"] = D.RV.rolling(5).mean()
D["RVm"] = D.RV.rolling(22).mean()
D["TRAIL"] = D.RV.rolling(20).mean()              # V2's input: the mean RV of the last 20 sessions, known at day t's close
D["y"] = D.RV.shift(-1)                           # next-day RV (the target)
print("sessions %d (%s .. %s)" % (len(D), D.date.iloc[0].date(), D.date.iloc[-1].date()))


def fit_predict(cols):
    """expanding OLS refit at each month start on rows with a known target strictly before that month; predicts the
    month's next-day RV from day t's regressors."""
    out = np.full(len(D), np.nan)
    month = D.date.dt.to_period("M")
    X = np.column_stack([np.ones(len(D))] + [D[c].to_numpy() for c in cols])
    y = D.y.to_numpy()
    for mo in month.unique():
        rows = np.flatnonzero(month.to_numpy() == mo)
        first = rows[0]
        train = np.arange(first - 1)              # targets known: y[i] = RV[i+1] needs i+1 <= first-1
        ok = train[np.isfinite(X[train]).all(1) & np.isfinite(y[train])]
        if len(ok) < 500:
            continue
        b, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
        out[rows] = X[rows] @ b
    return out


D["HAR"] = fit_predict(["RV", "RVw", "RVm"])
D["SHAR"] = fit_predict(["RSp", "RSn", "RVw", "RVm"])
W = D[(D.date >= pd.Timestamp("2016-07-01")) & (D.date <= pd.Timestamp("2025-07-15"))].dropna(subset=["HAR", "SHAR", "TRAIL", "y"]).copy()
floor = W.RV.quantile(0.01)                       # a forecast at or below zero is floored (OLS can undershoot)
for k in ("TRAIL", "HAR", "SHAR"):
    W[k] = W[k].clip(lower=floor)
print("scored stretch %s .. %s, %d sessions; forecasts floored at the 1st pct of RV in %d / %d / %d rows (TRAIL/HAR/SHAR)" % (
    W.date.iloc[0].date(), W.date.iloc[-1].date(), len(W), (D.loc[W.index, "TRAIL"] < floor).sum(),
    (D.loc[W.index, "HAR"] < floor).sum(), (D.loc[W.index, "SHAR"] < floor).sum()))


def qlike(f, y):
    return float(np.mean(y / f - np.log(y / f) - 1))


for k in ("TRAIL", "HAR", "SHAR"):
    print("  QLIKE %-5s %.4f" % (k, qlike(W[k].to_numpy(), W.y.to_numpy())))
S = {k: 1 / np.sqrt(W[k]) for k in ("TRAIL", "HAR", "SHAR")}
S = {k: v / v.mean() for k, v in S.items()}
for k, v in S.items():
    print("  size 1/sqrt(forecast), mean 1: CV %.3f, p5 %.2f, p95 %.2f" % (v.std() / v.mean(), v.quantile(.05), v.quantile(.95))
          if False else "  size %-5s CV %.3f  p5 %.2f  p95 %.2f" % (k, v.std() / v.mean(), v.quantile(.05), v.quantile(.95)))
c_sh, c_st = np.corrcoef(S["SHAR"], S["HAR"])[0, 1], np.corrcoef(S["SHAR"], S["TRAIL"])[0, 1]
print("  corr(SHAR size, HAR size) %.4f | corr(SHAR size, TRAIL size) %.4f | corr(HAR, TRAIL) %.4f" % (
    c_sh, c_st, np.corrcoef(S["HAR"], S["TRAIL"])[0, 1]))
gap = (S["SHAR"] - S["HAR"]).abs()
print("  sessions with |SHAR size - HAR size| > 0.25: %d of %d (%.1f%%); by year: %s" % (
    (gap > 0.25).sum(), len(gap), 100 * (gap > 0.25).mean(),
    ", ".join("%d %d" % (y, n) for y, n in (gap > 0.25).groupby(W.date.dt.year).sum().items() if n)))
close = c_sh >= 0.95 and c_st >= 0.90
print("READING: %s" % ("CLOSED AT THE MAP CHECK - SHAR sizing is HAR / V2 sizing in all but name; inherits RISK r1"
                       if close else "SIZES DIFFER - draft a pinned WF-only Stage A for MANAGER's GO"))
