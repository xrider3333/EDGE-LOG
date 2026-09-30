"""Paired sequential stop for the forward SHADOW tests (owner YES via MANAGER inbox #27, 2026-09-29).
Rule: docs/PREREG_paired_sequential_stop_2026-09-29.md. Written before any forward trade was read.

Every shadow arm trades the SAME fills as its twin; only the size differs. So judge the per-trade DIFFERENCE
    d_i = (r_i - rbar_n) * b_i        r = arm size / twin size, b = the twin's P&L on the trade,
                                      rbar_n = the mean of r over the n forward trades read so far
Subtracting the arm's OWN running mean size makes it a test of AIM (are the big sizes on the good trades?), not
of leverage (an arm that is simply bigger earns more whenever the edge is positive).
AMENDED 2026-09-30 before any forward trade was read (MANAGER #34 re-check): the first version subtracted a
FROZEN walk-forward mean c; if an arm's forward mean size drifts from c (KEEL's does), plain leverage leaks into
d. The running mean removes it by construction. Passing a number as `c` still gives the old fixed-c form.

    python tools/paired_seq_stop.py              print the frozen constants and each pair's false-stop rate
    from tools.paired_seq_stop import read_pair  score a forward log
"""
import os
import sys

import numpy as np
import pandas as pd

LEGS = r"C:\EdgeLog\book_legs"
FIRST, EVERY, BOUND, BOUND_EX = 20, 10, 3.0, 2.0
# (test, arm, twin, arm file, twin file, maximum forward trades in its written rule)
PAIRS = (("NOISE", "P primary (#382 + KEEL)", "A1 #382 plain", "NOISE382_keel_s42", "NOISE382_raw", 150),
         ("NOISE", "A3 #422 + fixed tilts", "A2 #422 plain", "NOISE422_fixed", "NOISE422_raw", 150),
         ("NOISE", "A4 #422 + KEEL", "A2 #422 plain", "NOISE422_keel_s42", "NOISE422_raw", 150),
         ("ORB tree", "tree HYBRID DD", "ORB #314 raw", "ORB314_hybdd_tree", "ORB314_raw", 120),
         ("TTM KEEL", "K #458 + KEEL", "R #458 raw", "TTM458_keel", "TTM458_raw", 50))
# Superseded 2026-09-30 (fixed-c form, kept for the record): c 1.2447 / 1.1394 / 1.2290 / 1.0463 / 1.8145,
# bounds 3.00 / 3.75 / 3.00 / 3.00 / 3.50. Running-mean bounds below, frozen by the 2026-09-30 run of main().
BOUNDS = {"NOISE382_keel_s42": 3.00, "NOISE422_fixed": 3.00, "NOISE422_keel_s42": 3.00, "ORB314_hybdd_tree": 3.00,
          "TTM458_keel": 3.25}


def tstat(d):
    d = np.asarray(d, float)
    if len(d) < 2 or d.std(ddof=1) <= 0:
        return 0.0
    return float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d))))


def diffs(u, m_arm, m_twin, c, n):
    """The first n paired differences. c=None: running-mean form (the rule); a number: the old fixed-c form."""
    u, ma, mt = (np.asarray(x, float)[:n] for x in (u, m_arm, m_twin))
    if c is not None:
        return (ma - c * mt) * u
    r = ma / np.where(mt == 0, np.nan, mt)
    return (r - np.nanmean(r)) * (mt * u)


def read_pair(u, m_arm, m_twin, c=None, bound=BOUND):
    """Walk the forward trades in order; return (status, n, t) at the first look that stops, else the last look.
    status: 'EARLY FAIL', 'EARLY PASS - read the final rule now', or 'continue'. u = P&L on one base unit;
    m_arm / m_twin = sizes (twin > 0 in the running-mean form)."""
    N = len(np.asarray(u))
    last = ("continue", N, tstat(diffs(u, m_arm, m_twin, c, N)))
    for n in range(FIRST, N + 1, EVERY):
        x = diffs(u, m_arm, m_twin, c, n)
        t = tstat(x)
        if t >= bound and tstat(np.delete(x, int(np.argmax(x)))) >= BOUND_EX:
            return "EARLY PASS - read the final rule now", n, t
        if t <= -bound and tstat(np.delete(x, int(np.argmin(x)))) <= -BOUND_EX:
            return "EARLY FAIL", n, t
        last = ("continue", n, t)
    return last


def load_pair(arm, twin):
    a = pd.read_csv(os.path.join(LEGS, arm + "_trades.csv"))
    b = pd.read_csv(os.path.join(LEGS, twin + "_trades.csv"))
    a = b[["entry_time"]].merge(a[["entry_time", "size"]], on="entry_time", how="left").fillna({"size": 0.0})
    ms_t = b["size"].to_numpy(float)
    u = b.pnl_usd.to_numpy(float) / np.where(ms_t == 0, 1.0, ms_t)       # P&L on one base unit
    return u, a["size"].to_numpy(float), ms_t, b.stage.to_numpy()


def false_stop(r, b, nmax, bound, reps, seed):
    """Worse of two no-aim nulls. (1) sizes r and twin P&L b drawn INDEPENDENTLY from their walk-forward pools;
    (2) walk-forward (r, b) PAIRS drawn together after removing b's linear dependence on r - keeps the real
    link between size and trade SIZE (big sizes on quiet trades, say) while taking out any aim."""
    rng = np.random.default_rng(seed)
    one = np.ones(nmax)
    rc = r - r.mean()
    beta = float((rc * b).sum() / (rc * rc).sum()) if (rc * rc).sum() > 0 else 0.0
    bres = b - beta * rc
    s1 = s2 = 0
    for _ in range(reps):
        s1 += read_pair(rng.choice(b, nmax), rng.choice(r, nmax), one, None, bound)[0] != "continue"
        k = rng.integers(0, len(r), nmax)
        s2 += read_pair(bres[k], r[k], one, None, bound)[0] != "continue"
    return max(s1, s2) / reps


def calibrate(r, b, nmax, reps=4000, seed=20260930):
    for bound in np.arange(3.0, 8.01, 0.25):
        fs = false_stop(r, b, nmax, bound, reps, seed)
        if fs <= 0.05:
            return float(bound), fs
    return float("nan"), fs


def main():
    """Freeze each pair's boundary: the smallest of 3.0, 3.25, ... whose false-stop rate is <= 5% under the
    no-aim null (walk-forward sizes and walk-forward twin P&L drawn independently)."""
    for test, arm_lab, twin_lab, arm, twin, nmax in PAIRS:
        u, ma, mt, st = load_pair(arm, twin)
        wf = st == "WF"
        r, b = ma[wf] / mt[wf], (mt * u)[wf]
        if BOUNDS[arm] is None:
            bound, fs = calibrate(r, b, nmax)
        else:
            bound, fs = BOUNDS[arm], false_stop(r, b, nmax, BOUNDS[arm], 4000, 20260930)
        print(f"{test:9s} {arm_lab:26s} vs {twin_lab:15s} boundary |t| >= {bound:.2f}  false-stop {100 * fs:4.1f}% "
              f"over {nmax} trades  (WF running-mean paired t {tstat(diffs(u[wf], ma[wf], mt[wf], None, int(wf.sum()))):+.2f}, "
              f"mean size {r.mean():.3f})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
