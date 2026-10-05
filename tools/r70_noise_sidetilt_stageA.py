# -*- coding: utf-8 -*-
"""NOISE ROUND 70 STAGE A - size NOISE #422's SHORTS up (docs/PREREG_noise_r70_sidetilt_2026-10-05.md). WALK-FORWARD ONLY.

Every short x K (1.5 primary; 1.25 / 2.0 neighbours) on top of #422's own size; longs unchanged. Nothing after the
walk-forward is computed: the NOISE leg reads 2016-06-30 .. 2025-07-16 (NOISE's stretches), the book reads #463's own
walk-forward 2016-07-01 .. 2025-06-29 with the book built only to 2025-06-29.

  A1  NOISE leg beats #422 on WF ROC@30k AND Sortino, >= 100 trades
  A2  both neighbours beat #422's WF ROC@30k
  A3  paired stationary block bootstrap (mean block 20 sessions, 1,000 draws, seed 20261005): 5th pct of the WF
      ROC@30k difference > 0
  A4  >= 6 of 9 WF years, AND still ahead of #422 without 2020-02-01..04-30 AND without calendar 2022
  A5  BOOK: #463 + (tilted NOISE - plain NOISE) beats #463 + (c - 1) x plain NOISE, c = mean tilted size / mean #422
      size over WF trades (sizes only), on WF ROC@30k AND Sortino. Parity first: the book series reproduces #463's
      unified WF 93.81 / 3.816 or the round aborts.

  python tools/r70_noise_sidetilt_stageA.py   -> tools/r37_results/r70_stageA.txt (tee)
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

K_MAIN, K_NB = 1.5, (1.25, 2.0)
SEED, DRAWS, BLOCK = 20261005, 1000, 20
BWF0, BPRE = pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29")
SESS = np.array(sorted(set(R.DATE[(R.DATE >= R.WF0) & (R.DATE < R.LB0)])))
YEARS = (pd.Timestamp(R.LB0) - pd.Timestamp(R.WF0)).days / 365.25


def tilted(tr, k):
    return [(int(t[0]), float(t[2]) * (k if np.sign(t[3]) < 0 else 1.0)) for t in tr]


def wf_line(label, pairs):
    s = R.stats(pairs, R.WF0, R.LB0)
    print("  %-22s WF %4d tr  ROC@30k %5.1f%%  Sortino %4.2f  (%5.1f%%/yr, DD $%s)" % (
        label, s["n"], s["r30"], s["so"], s["roc"], format(int(s["dd"]), ",")))
    return s


def daily(pairs, sess=SESS):
    k = np.array([p[0] for p in pairs], int)
    v = np.array([p[1] for p in pairs], float) * R.M
    d = R.DATE[k - 1]
    m = (d >= sess[0]) & (d <= sess[-1])
    return pd.Series(v[m]).groupby(d[m]).sum().reindex(sess, fill_value=0.0).to_numpy()


def roc30(x, years):
    cum = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    return 30 * (x.sum() / years) / dd if dd > 0 else np.inf


def stationary_index(n, rng):
    idx = np.empty(n, int)
    i = rng.integers(n)
    for t in range(n):
        if t > 0:
            i = rng.integers(n) if rng.random() < 1.0 / BLOCK else (i + 1) % n
        idx[t] = i
    return idx


def book_stats(x, dates):
    sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
    import r11_risk as R11
    return R11.stats(np.asarray(x, float), dates)


if __name__ == "__main__":
    print("NOISE round 70 STAGE A - #422 shorts x %.2f, walk-forward only" % K_MAIN)
    ct = R.load("NOISE_1_8_CT304H.py")
    tr = sorted(run_backtest(ct, arrays=R.A, params=dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75),
                             cost_pts=R.COST, return_trades=True)["trades"], key=lambda t: int(t[0]))
    base = tilted(tr, 1.0)
    twin = wf_line("NOISE #422", base)
    assert twin["n"] == 2805 and round(twin["r30"], 1) == 84.6, "PARITY FAILED (#422) - abort"
    cells = {k: tilted(tr, k) for k in (K_MAIN,) + K_NB}
    s = {k: wf_line("shorts x %.2f%s" % (k, "" if k == K_MAIN else " (neighbour)"), cells[k]) for k in (K_MAIN,) + K_NB}
    a1 = s[K_MAIN]["r30"] > twin["r30"] and s[K_MAIN]["so"] > twin["so"] and s[K_MAIN]["n"] >= 100
    a2 = all(s[k]["r30"] > twin["r30"] for k in K_NB)

    x1, x2 = daily(base), daily(cells[K_MAIN])
    rng = np.random.default_rng(SEED)
    diffs = np.empty(DRAWS)
    for i in range(DRAWS):
        idx = stationary_index(len(SESS), rng)
        diffs[i] = roc30(x2[idx], YEARS) - roc30(x1[idx], YEARS)
    p5 = float(np.percentile(diffs, 5))
    a3 = p5 > 0

    wins = 0
    for y in range(9):
        a = (pd.Timestamp(R.WF0) + pd.DateOffset(years=y)).date()
        b = R.LB0 if y == 8 else (pd.Timestamp(R.WF0) + pd.DateOffset(years=y + 1)).date()
        m = (SESS >= a) & (SESS < b)
        yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
        r1, r2 = roc30(x1[m], yrs), roc30(x2[m], yrs)
        wins += r2 > r1
        print("    year %d (%s .. %s): #422 %6.1f  tilted %6.1f" % (y + 1, a, b, r1, r2))
    outs = {}
    for lab, lo, hi in (("without 2020-02..04", pd.Timestamp("2020-02-01").date(), pd.Timestamp("2020-04-30").date()),
                        ("without 2022", pd.Timestamp("2022-01-01").date(), pd.Timestamp("2022-12-31").date())):
        keep = ~((SESS >= lo) & (SESS <= hi))
        yrs = YEARS - ((pd.Timestamp(hi) - pd.Timestamp(lo)).days + 1) / 365.25
        outs[lab] = (roc30(x1[keep], yrs), roc30(x2[keep], yrs))
        print("    %-20s #422 %6.1f  tilted %6.1f" % (lab, outs[lab][0], outs[lab][1]))
    a4 = wins >= 6 and all(v[1] > v[0] for v in outs.values())

    # ---- A5: the book, walk-forward only, built to 2025-06-29 -------------------------------------------------------
    from api.book_shadow import book463_valued_daily
    B = book463_valued_daily("2010-06-07", BPRE.strftime("%Y-%m-%d"))
    B = B[(B.index >= BWF0) & (B.index <= BPRE)]
    ref = book_stats(B.to_numpy(), B.index)
    print("  BOOK #463 WF (built to 2025-06-29): ROC@30k %.2f  Sortino %.3f" % (ref["roc"], ref["sort"]))
    assert abs(ref["roc"] - 93.81) < 0.05 and abs(ref["sort"] - 3.816) < 0.005, "BOOK PARITY FAILED - abort"
    bdays = pd.DatetimeIndex(B.index)
    kk = np.array([p[0] for p in base])
    d_et = pd.DatetimeIndex([pd.Timestamp(x) for x in R.DATE[kk - 1]])
    noise_day = pd.Series(np.array([p[1] for p in base]) * R.M).groupby(d_et).sum().reindex(bdays, fill_value=0.0)
    tilt_day = pd.Series(np.array([p[1] for p in cells[K_MAIN]]) * R.M).groupby(d_et).sum().reindex(bdays, fill_value=0.0)
    comp =R.SQ._compression(R.H, R.L, R.C, np.asarray(R.A["day_id"]), R.A["index"], 60, 20, 1.15)
    s422 = np.where(comp[kk - 1].astype(bool), 1.75, 1.0)
    side = np.array([np.sign(t[3]) for t in tr])
    wfm = (R.DATE[kk - 1] >= BWF0.date()) & (R.DATE[kk - 1] <= BPRE.date())
    c = float((s422 * np.where(side < 0, K_MAIN, 1.0))[wfm].mean() / s422[wfm].mean())
    tilted_book = B + (tilt_day - noise_day)
    twin_book = B + (c - 1.0) * noise_day
    tb, tw = book_stats(tilted_book.to_numpy(), bdays), book_stats(twin_book.to_numpy(), bdays)
    print("  BOOK + tilted NOISE   ROC@30k %.2f  Sortino %.3f" % (tb["roc"], tb["sort"]))
    print("  BOOK + NOISE x c=%.3f ROC@30k %.2f  Sortino %.3f  (plain extra NOISE at the same mean size)" % (c, tw["roc"], tw["sort"]))
    a5 = tb["roc"] > tw["roc"] and tb["sort"] > tw["sort"]

    print("")
    for lab, ok in (("A1 NOISE leg beats #422 on WF ROC@30k and Sortino", a1), ("A2 both neighbours beat #422", a2),
                    ("A3 paired bootstrap p5 %+.1f > 0" % p5, a3), ("A4 %d of 9 years, 2020-out and 2022-out" % wins, a4),
                    ("A5 book beats plain extra NOISE at the same mean size", a5)):
        print("  %-55s %s" % (lab, "PASS" if ok else "FAIL"))
    print("")
    print("STAGE A: %s" % ("PASS on every bar -> MANAGER decides the one lockbox read" if all((a1, a2, a3, a4, a5))
                         else "FAIL - recorded dead, no variants"))
