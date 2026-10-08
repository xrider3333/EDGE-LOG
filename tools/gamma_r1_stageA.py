# -*- coding: utf-8 -*-
"""GAMMA r1 - dealer gamma as the ES day-type switch, ONE shared prereg for two arms (docs/PREREG_gamma_r1_2026-10-07.md;
MANAGER #67: TTM's GEXEXP expansion arm + DISC's GEXREV reversion arm, one family null). THIS FILE = the shared frame and
the GEXEXP arm; the GEXREV arm's fade is DISC's BALANCE r1 rule and is wired in after DISC's review.

GEX = SqueezeMetrics' public daily dealer-gamma estimate (S&P 500 options), the 2026-10-07 photograph
C:/EdgeLog/_research_cache/squeezemetrics/DIX.csv, re-hashed against squeezemetrics_provenance.json; rows after 2025-06-29
dropped on read; only the value dated strictly BEFORE a session is read (end-of-day value, publication time unstated).
State per session: the prior GEX's percentile among the 252 GEX days before it. Bottom tercile = SHORT-GAMMA day (GEXEXP),
top tercile = LONG-GAMMA day (GEXREV).

GEXEXP (short-gamma days): ES 30m RTH; range = high / low of the 10:00 and 10:30 bars; the first 30m close beyond it from
the 11:00 bar to the 15:00 bar -> 1 ES in that direction at the next bar's open, out at the 15:30 bar's close; one trade a
session; no stop. Cost 0.363 pt, $50 a point. Intra-session only, so the no-adjust master is exact.

  python tools/gamma_r1_stageA.py --counts   -> state days and GEXEXP trades per year (no returns)
  python tools/gamma_r1_stageA.py --power    -> the power line from a COIN-FLIP side on GEXEXP's schedule
"""
import hashlib
import json
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

COST, M = 0.363, 50.0
D0, WF0, WF1 = "2010-06-07", HH.WF0, HH.WF1
SEED = 20261007
GEXDIR = os.path.join(HOME, "_research_cache", "squeezemetrics")


def gex():
    raw = os.path.join(GEXDIR, "DIX.csv")
    prov = json.load(open(os.path.join(GEXDIR, "squeezemetrics_provenance.json"), encoding="utf-8"))["DIX.csv"]
    assert hashlib.sha256(open(raw, "rb").read()).hexdigest() == prov["sha256"], "DIX.csv is not the photograph - abort"
    g = pd.read_csv(raw, parse_dates=["date"])
    g = g[g["date"] <= WF1].set_index("date")["gex"].astype(float).dropna()
    return g, prov


def state(days, g):
    """Per session: -1 short-gamma (bottom tercile), +1 long-gamma (top tercile), 0 middle / unknown."""
    gv, gi = g.to_numpy(), g.index
    out = np.zeros(len(days), int)
    pct = np.full(len(days), np.nan)
    for i, d in enumerate(days):
        k = gi.searchsorted(d) - 1                                      # the latest GEX dated strictly before session d
        if k < 252:
            continue
        p = float((gv[k - 252:k] < gv[k]).mean())
        pct[i] = p
        out[i] = -1 if p <= 1.0 / 3.0 else (1 if p >= 2.0 / 3.0 else 0)
    return out, pct


def es30():
    A = load_master_arrays(find_master("ES", "30m", "rth", "db_noadj_rth"), date_from=D0, date_to=WF1.strftime("%Y-%m-%d"))
    ts = pd.DatetimeIndex(A["index"])
    assert ts[-1].date() <= WF1.date(), "a bar after 2025-06-29 is in memory - abort"
    k = np.asarray((ts.hour * 60 + ts.minute - 570) // 30)
    day = pd.DatetimeIndex(pd.Index(ts.date))
    days = pd.DatetimeIndex(sorted(set(day)))
    di = days.get_indexer(day)
    G = {}
    ok = (k >= 0) & (k < 13)
    for f in ("open", "high", "low", "close"):
        X = np.full((len(days), 13), np.nan)
        X[di[ok], k[ok]] = np.asarray(A[f], float)[ok]
        G[f] = X
    full = np.isfinite(G["close"]).all(axis=1) & np.isfinite(G["open"]).all(axis=1)
    return days[full], {f: X[full] for f, X in G.items()}


def gexexp_schedule(G, on):
    """(side, entry bar) per session: the first close of bars 3..11 (11:00 .. 15:00) beyond the 10:00-11:00 range."""
    hi = np.maximum(G["high"][:, 1], G["high"][:, 2])
    lo = np.minimum(G["low"][:, 1], G["low"][:, 2])
    side = np.zeros(len(hi))
    ent = np.full(len(hi), -1)
    for i in np.flatnonzero(on):
        for b in range(3, 12):
            c = G["close"][i, b]
            if c > hi[i] or c < lo[i]:
                side[i], ent[i] = (1.0 if c > hi[i] else -1.0), b + 1
                break
    return side, ent


def gexexp_pnl(G, side, ent):
    x = np.zeros(len(side))
    m = side != 0
    x[m] = side[m] * (G["close"][m, 12] - G["open"][m, ent[m]]) * M - COST * M
    return x


def main(argv):
    g, prov = gex()
    days, G = es30()
    st, pct = state(days, g)
    wf = np.asarray((days >= WF0) & (days <= WF1))
    B, ref = HH.book()
    bdays = pd.DatetimeIndex(B.index)
    years = (bdays[-1] - bdays[0]).days / 365.25
    print("GAMMA r1 - GEX photograph %s fetched %s sha256 %s.. verified, %d GEX days to %s; ES 30m RTH no-adjust %d full "
          "sessions (%s .. %s)" % (prov["url"], prov["fetched_at_utc"], prov["sha256"][:8], len(g), g.index[-1].date(),
                                   len(days), days[0].date(), days[-1].date()))
    print("  BOOK #463 WF parity: ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    neg = int((g[g.index >= WF0] < 0).sum())
    print("  WF sessions with a state: %d; short-gamma (bottom tercile) %d (%.0f a year), long-gamma (top tercile) %d (%.0f a "
          "year); raw GEX < 0 on %d WF GEX days" % (int((wf & np.isfinite(pct)).sum()), int((wf & (st == -1)).sum()),
                                                  (wf & (st == -1)).sum() / years, int((wf & (st == 1)).sum()),
                                                  (wf & (st == 1)).sum() / years, neg))
    side, ent = gexexp_schedule(G, wf & (st == -1))
    yb = pd.Series(days.year[side != 0]).value_counts().sort_index()
    print("  COUNTS GEXEXP: %d WF trades (%.0f a year), long %d / short %d; per calendar year %s" % (
        int((side != 0).sum()), (side != 0).sum() / years, int((side > 0).sum()), int((side < 0).sum()),
        {int(k): int(v) for k, v in yb.items()}))
    for lab, a, b in (("2016-21", WF0, pd.Timestamp("2021-12-31")), ("2022-25", pd.Timestamp("2022-01-01"), WF1)):
        m = np.asarray((days >= a) & (days <= b))
        print("    %s: short-gamma days %d, long-gamma days %d, GEXEXP trades %d" % (
            lab, int((m & (st == -1)).sum()), int((m & (st == 1)).sum()), int((m & (side != 0)).sum())))
    RD = np.asarray(days.isin(pd.DatetimeIndex(pd.to_datetime(
        pd.read_csv(os.path.join(HOME, "_anatomy_cache", "q19", "residual_days.csv")).query("in_R").date))))
    print("  R days among GEXEXP trade days %d; among long-gamma days %d" % (int((RD & (side != 0)).sum()),
                                                                            int((RD & wf & (st == 1)).sum())))
    if "--power" in argv:
        coin = np.random.default_rng(SEED).choice([-1.0, 1.0], size=len(side))
        x = gexexp_pnl(G, np.where(side != 0, coin, 0.0), ent)
        print("POWER LINES (coin-flip sides on GEXEXP's schedule; no real direction is computed)")
        HH.power_lines(pd.Series(x, index=days).reindex(bdays, fill_value=0.0).to_numpy(), B, years)


if __name__ == "__main__":
    main(sys.argv[1:])
