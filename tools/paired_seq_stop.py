"""Paired sequential stop for the forward SHADOW tests (owner YES via MANAGER inbox #27, 2026-09-29).
Rule: docs/PREREG_paired_sequential_stop_2026-09-29.md. Written before any forward trade was read.

Every shadow arm trades the SAME fills as its twin; only the size differs. So judge the per-trade DIFFERENCE
    d_i = (m_arm_i - c * m_twin_i) * u_i
u_i = the trade's P&L on one base unit, m = each side's size multiplier, c = the arm's frozen walk-forward mean
size relative to its twin. Subtracting c makes it a test of AIM (are the big sizes on the good trades?), not of
leverage (an arm that is simply bigger earns more whenever the edge is positive).

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
# Frozen by the first run of this file (2026-09-29) from the WF stage of the book-leg exports; never re-derived.
C = {"NOISE382_keel_s42": 1.2447, "NOISE422_fixed": 1.1394, "NOISE422_keel_s42": 1.2290,
     "ORB314_hybdd_tree": 1.0463, "TTM458_keel": 1.8145}
BOUNDS = {"NOISE382_keel_s42": 3.00, "NOISE422_fixed": 3.75, "NOISE422_keel_s42": 3.00,
          "ORB314_hybdd_tree": 3.00, "TTM458_keel": 3.50}


def tstat(d):
    d = np.asarray(d, float)
    if len(d) < 2 or d.std(ddof=1) <= 0:
        return 0.0
    return float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d))))


def read_pair(u, m_arm, m_twin, c, bound=BOUND):
    """Walk the forward trades in order; return (status, n, t) at the first look that stops, else the last look.
    status: 'EARLY FAIL', 'EARLY PASS - read the final rule now', or 'continue'."""
    d = (np.asarray(m_arm, float) - c * np.asarray(m_twin, float)) * np.asarray(u, float)
    last = ("continue", len(d), tstat(d))
    for n in range(FIRST, len(d) + 1, EVERY):
        x = d[:n]
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


def false_stop(dnull, nmax, bound, reps, seed):
    rng = np.random.default_rng(seed)
    one, zero = np.ones(nmax), np.zeros(nmax)
    return float(np.mean([read_pair(rng.choice(dnull, nmax), one, zero, 0.0, bound)[0] != "continue"
                          for _ in range(reps)]))


def main(reps=4000, seed=20260929):
    """Freeze c and the per-pair boundary: the smallest of 3.0, 3.25, ... whose false-stop rate is <= 5%
    when the same walk-forward differences are re-drawn with their mean removed (the null)."""
    for test, arm_lab, twin_lab, arm, twin, nmax in PAIRS:
        u, ma, mt, st = load_pair(arm, twin)
        wf = st == "WF"
        c = float(np.mean(ma[wf] / mt[wf])) if C[arm] is None else C[arm]
        d = (ma - c * mt) * u
        dnull = d[wf] - d[wf].mean()
        if BOUNDS[arm] is None:
            for b in np.arange(3.0, 8.01, 0.25):
                fs = false_stop(dnull, nmax, b, reps, seed)
                if fs <= 0.05:
                    break
        else:
            b = BOUNDS[arm]
            fs = false_stop(dnull, nmax, b, reps, seed)
        print(f"{test:9s} {arm_lab:26s} vs {twin_lab:15s} c = {c:.4f}  boundary |t| >= {b:.2f}  false-stop "
              f"{100 * fs:4.1f}% over {nmax} trades  (WF paired t {tstat(d[wf]):+.2f}, {int(wf.sum())} trades)",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
