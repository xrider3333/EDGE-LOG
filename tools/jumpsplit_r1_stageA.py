# -*- coding: utf-8 -*-
"""JUMPSPLIT r1 STAGE A - a diffusive morning continues, a jump morning does not (docs/PREREG_jumpsplit_r1_2026-10-07.md;
TTM scope rank 8, opened by MANAGER 2026-10-07 evening). NQ and ES are separate arms, judged apart.

Bipower variation separates the continuous part of a morning's variance from its jumps (Barndorff-Nielsen & Shephard 2004,
2006; Huang & Tauchen 2005; Lee & Mykland 2008 RFS). Rule per instrument: from the 30 5m RTH log returns of 09:30-12:00
(the first from the 09:30 open), RV = sum r^2, BV = (pi/2)(n/(n-1)) sum |r_i||r_i-1|, relative jump RJ = (RV - BV) / RV
(not truncated, so there are no ties at zero). p = the share of the 252 prior full sessions' RJ below today's. If p <= 1/3
(a DIFFUSIVE morning) and the morning moved (11:55 bar close != 09:30 open): 1 contract in the morning's direction at the
12:00 bar's open, out at the 15:55 bar's close; no stop; one trade a session. NO-ADJUST 5m RTH masters (intra-session
only, so exact). NQ 0.533 pt x $20, ES 0.363 pt x $50. Full 78-bar sessions only (half-days skipped). Arrays cut at
2025-06-29.

  python tools/jumpsplit_r1_stageA.py --counts   -> state days and trades per arm per year (no returns)
  python tools/jumpsplit_r1_stageA.py --power    -> the power line from a COIN-FLIP side on each arm's primary schedule
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HOME = os.environ.get("EDGELOG_HOME") or "C:/EdgeLog"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
import halfhour_r1_stageA as HH                                         # noqa: E402

ARMS = {"NQ": (0.533, 20.0), "ES": (0.363, 50.0)}
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
EARLY0, EARLY1 = pd.Timestamp("2011-07-01"), pd.Timestamp("2016-06-30")
NBAR, NOON, HIST = 78, 30, 252
CELLS = [1.0 / 3.0, 1.0 / 4.0]                                          # bottom tercile = PRIMARY, bottom quartile = neighbour
PRIMARY = CELLS[0]
SEED = 20261007
PREREG = "docs/PREREG_jumpsplit_r1_2026-10-07.md"
STRETCHES = [("EARLY", EARLY0, EARLY1), ("WF", WF0, WF1), ("WF 2016-21", WF0, pd.Timestamp("2021-12-31")),
             ("WF 2022-25", pd.Timestamp("2022-01-01"), WF1)]


def grid(sym):
    A = load_master_arrays(find_master(sym, "5m", "rth", "db_noadj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"]).tz_localize(None)
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 5)
    day = pd.DatetimeIndex(ts.normalize())
    days = pd.DatetimeIndex(sorted(set(day)))
    di = days.get_indexer(day)
    ok = (k >= 0) & (k < NBAR)
    G = {}
    for f in ("open", "close"):
        X = np.full((len(days), NBAR), np.nan)
        X[di[ok], k[ok]] = np.asarray(A[f], float)[ok]
        G[f] = X
    full = np.isfinite(G["open"]).all(axis=1) & np.isfinite(G["close"]).all(axis=1)
    return days[full], {f: X[full] for f, X in G.items()}


def morning(G):
    """(RJ, direction) per session from the 30 5m returns of 09:30-12:00."""
    r = np.diff(np.log(np.c_[G["open"][:, 0], G["close"][:, :NOON]]), axis=1)
    n = r.shape[1]
    rv = (r ** 2).sum(axis=1)
    bv = (np.pi / 2.0) * (n / (n - 1.0)) * (np.abs(r[:, 1:]) * np.abs(r[:, :-1])).sum(axis=1)
    rj = np.where(rv > 0, (rv - bv) / np.where(rv > 0, rv, 1.0), np.nan)
    move = G["close"][:, NOON - 1] - G["open"][:, 0]
    return rj, np.sign(move)


def pctile(rj):
    p = np.full(len(rj), np.nan)
    for i in range(HIST, len(rj)):
        h = rj[i - HIST:i]
        h = h[np.isfinite(h)]
        if np.isfinite(rj[i]) and len(h) == HIST:
            p[i] = float((h < rj[i]).mean())
    return p


def build(sym):
    days, G = grid(sym)
    rj, d = morning(G)
    return dict(sym=sym, days=days, G=G, rj=rj, dirn=d, p=pctile(rj))


def schedule(D, cut, lo=True):
    p = D["p"]
    on = np.isfinite(p) & ((p <= cut) if lo else (p >= 1.0 - cut)) & (D["dirn"] != 0)
    return np.where(on, D["dirn"], 0.0)


def pnl(D, side):
    cost, m = ARMS[D["sym"]]
    G = D["G"]
    x = np.zeros(len(side))
    t = side != 0
    x[t] = side[t] * (G["close"][t, NBAR - 1] - G["open"][t, NOON]) * m - cost * m
    return x


def main(argv):
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("JUMPSPLIT r1 - NQ / ES 5m RTH no-adjust, full sessions only; arms judged apart")
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    RDd = pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))
    rng = np.random.default_rng(SEED)
    for sym in ARMS:
        D = build(sym)
        days = D["days"]
        wf = np.asarray((days >= WF0) & (days <= WF1))
        print("ARM %s: %d full sessions (%s .. %s); RJ < 0 on %.0f%% of WF sessions; median RJ %.3f" % (
            sym, len(days), days[0].date(), days[-1].date(), 100 * np.nanmean(D["rj"][wf] < 0),
            float(np.nanmedian(D["rj"][wf]))))
        for cut in CELLS:
            s = schedule(D, cut)
            per = pd.Series(days.year[wf & (s != 0)]).value_counts().sort_index()
            print("  COUNTS bottom %s: %d WF trades (%.0f a year), long %d / short %d; per calendar year %s; R days %d" % (
                "tercile" if cut == CELLS[0] else "quartile", int((wf & (s != 0)).sum()), (wf & (s != 0)).sum() / years,
                int((wf & (s > 0)).sum()), int((wf & (s < 0)).sum()), {int(k): int(v) for k, v in per.items()},
                int((wf & (s != 0) & days.isin(RDd)).sum())))
        sp = schedule(D, PRIMARY)
        for lab, a, b in STRETCHES:
            m = np.asarray((days >= a) & (days <= b))
            print("    %-10s primary trades %4d; twins: all sessions %4d, top-tercile (jump) mornings %4d" % (
                lab, int((m & (sp != 0)).sum()), int((m & (D["dirn"] != 0) & np.isfinite(D["p"])).sum()),
                int((m & (schedule(D, PRIMARY, lo=False) != 0)).sum())))
        if "--power" in argv:
            on = wf & (sp != 0)
            x = pnl(D, np.where(on, rng.choice([-1.0, 1.0], size=len(sp)), 0.0))
            print("  POWER LINES %s (coin-flip sides on the primary's schedule; no real direction is computed)" % sym)
            HH.power_lines(pd.Series(x, index=days).reindex(bdays, fill_value=0.0).to_numpy(), B, years)


if __name__ == "__main__":
    main(sys.argv[1:])
