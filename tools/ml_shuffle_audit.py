"""Shuffle audit of every ML / tilt-sized book leg (2026-09-30, Custom ML queue after MANAGER #29).

Question: does each sized leg's edge over its raw twin come from WHERE it puts size (aim), or only from the
SHAPE of its sizes (how big and how spread)? For each leg in C:\\EdgeLog\\book_legs, m = arm size / twin size per
trade. The null keeps those exact m values and shuffles them across the same trades 1,000 times. Aim is shown
only if the arm's ROC %/yr at a $30k drawdown is above the 95th percentile of its shuffles. WF and LB apart.
Bar written before running: docs/ML_SHUFFLE_AUDIT_2026-09-30.md (top section).

Days: P&L lands on the ENTRY day (the exports' trade files). That is exact for the intraday legs (NOISE, ORB,
TTM) and understates the drawdown of ENGU-Q, which holds for weeks - its rows are marked as such.

    python tools/ml_shuffle_audit.py
"""
import os
import sys

import numpy as np
import pandas as pd

LEGS = r"C:\EdgeLog\book_legs"
PAIRS = (("NOISE422_fixed", "NOISE422_raw"), ("NOISE422_keel_s42", "NOISE422_raw"), ("NOISE422_keel_bag7", "NOISE422_raw"),
         ("NOISE382_keel_s42", "NOISE382_raw"), ("NOISE382_fixed", "NOISE382_raw"), ("ORB314_hybdd_tree", "ORB314_raw"),
         ("ENGUQ335_hybdd_rf", "ENGUQ335_raw"), ("ENGUQ335paper_hybdd_rf", "ENGUQ335paper_raw"),
         ("TTM368_keel", "TTM368_raw"), ("TTM458_keel", "TTM458_raw"))
NSHUF, SEED = 1000, 20260930


def roc30(days, pnl):
    daily = pd.Series(pnl).groupby(days).sum()
    yrs = max((daily.index.max() - daily.index.min()).days, 1) / 365.25
    cum = daily.cumsum().to_numpy()
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    return 30.0 * (pnl.sum() / yrs) / dd if dd > 0 else float("nan")


def main():
    rng = np.random.default_rng(SEED)
    for arm, twin in PAIRS:
        a = pd.read_csv(os.path.join(LEGS, arm + "_trades.csv"))
        b = pd.read_csv(os.path.join(LEGS, twin + "_trades.csv"))
        a = b[["entry_time"]].merge(a[["entry_time", "size"]], on="entry_time", how="left").fillna({"size": 0.0})
        tw = b["size"].to_numpy(float)
        u = b.pnl_usd.to_numpy(float) / np.where(tw == 0, 1.0, tw)
        m = a["size"].to_numpy(float) / np.where(tw == 0, 1.0, tw)
        days = pd.to_datetime(b.entry_time.str[:10])
        out = []
        for st in ("WF", "LB"):
            k = (b.stage == st).to_numpy()
            base = u[k] * tw[k]
            arm_p = u[k] * tw[k] * m[k]
            r_raw, r_arm = roc30(days[k].to_numpy(), base), roc30(days[k].to_numpy(), arm_p)
            null = [roc30(days[k].to_numpy(), base * rng.permutation(m[k])) for _ in range(NSHUF)]
            out.append(f"{st} n {int(k.sum()):4d} raw {r_raw:6.1f} arm {r_arm:6.1f} shuffle pct {100 * np.mean(np.array(null) < r_arm):5.1f}")
        tag = "  (multi-week holds: entry-day drawdown understated)" if arm.startswith("ENGUQ") else ""
        print(f"{arm:24s} | " + " | ".join(out) + tag, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
