# -*- coding: utf-8 -*-
"""NOISE_422_FIXED forward shadow - the three pre-stated sub-arm reads (NOISE.md, MANAGER #32, 2026-10-04).

The shadow NOISE_422_FIXED trades the same signals as NOISE #422 plain; only the size differs. Three difference series
against #422 plain, each scored with the house paired sequential stop (tools/paired_seq_stop.read_pair, running-mean
form: it tests AIM - are the bigger sizes on the better trades - not leverage):
  FULL     arm = the package's size (m_422fixed)                    relevant = every trade
  FRIDAY   arm = #422 plain x 1.5 on Friday entries, else x 1        relevant = Friday trades
  FOMC     arm = #422 plain x 0.5 before a 14:00 ET FOMC statement   relevant = FOMC-morning trades
  SHORTS   arm = #422 plain x 1.5 on short trades (REPORT-ONLY, MANAGER #37 after round 70 died at Stage A on the paired
           bootstrap alone)                                       relevant = short trades
A tilt's aim needs the untilted trades as its contrast, so every series runs over ALL closed trades; "relevant" counts
the trades the tilt actually re-sizes, and a series is judged once it has 50 relevant closed trades (the FOMC series
will take years - a report, not a bar). Unit P&L = the primary's real Webull fill P&L per share (pnl_per_share).
A forward pass is the only thing that could change #422's sizing, and that goes to the owner.

  python tools/noise_fixed_subarm_read.py [--home DIR]   (default: the newest C:\\EdgeLog\\box_backup\\<stamp>)
"""
import argparse
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paired_seq_stop as P                                           # noqa: E402

RELEVANT_AT = 50


def joined(home):
    out = os.path.join(tempfile.mkdtemp(), "noise_forward_joined.csv")
    subprocess.run([sys.executable, os.path.join(HERE, "noise_forward_log.py"), "--home", home, "--out", out],
                   check=True, capture_output=True)
    return pd.read_csv(out)


def series(d):
    plain = d.m_422plain.to_numpy(float)
    fri = d.friday.astype(int).to_numpy() == 1
    fomc = d.fomc_pre14.astype(int).to_numpy() == 1
    short = d.side.astype(str).str.lower().str.startswith("s").to_numpy() | (pd.to_numeric(d.side, errors="coerce").to_numpy() < 0)
    return (("FULL package", d.m_422fixed.to_numpy(float), np.ones(len(d), bool)),
            ("FRIDAY 1.5x", plain * np.where(fri, 1.5, 1.0), fri),
            ("FOMC 0.5x", plain * np.where(fomc, 0.5, 1.0), fomc),
            ("SHORTS 1.5x", plain * np.where(short, 1.5, 1.0), short))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=None)
    a = ap.parse_args(argv)
    home = a.home or sorted(glob.glob(r"C:\EdgeLog\box_backup\*\cloud_signal\shadow\noise_forward_log.csv"))[-1] \
        .split(r"\cloud_signal")[0]
    full = joined(home)
    for unit, label in (("pnl_per_share", "REAL Webull fills (the pre-stated read)"),
                        ("pnl_per_share_book", "BOOK would-be fills incl. broker-blocked rows (flagged: Webull netting "
                                               "refuses a NOISE short while the account is long)")):
        if unit not in full.columns:
            print("  (%s: column %s missing in the joined log)" % (label, unit))
            continue
        d = full[np.isfinite(pd.to_numeric(full[unit], errors="coerce"))].copy()
        d = d.sort_values("entry_bar_time").reset_index(drop=True)
        print("NOISE_422_FIXED sub-arm reads on %s - forward log %s, %d closed trades (%s .. %s)" % (
            label, home, len(d), str(d.entry_bar_time.iloc[0])[:10] if len(d) else "-",
            str(d.entry_bar_time.iloc[-1])[:10] if len(d) else "-"))
        read(d, d[unit].astype(float).to_numpy())


def read(d, u):
    for name, m_arm, rel in series(d):
        nrel = int(rel.sum())
        if len(d) >= P.FIRST:
            status, n, t = P.read_pair(u, m_arm, d.m_422plain.to_numpy(float), bound=P.BOUNDS["NOISE422_fixed"])
        else:
            status, n, t = "too early (paired stop looks from %d trades)" % P.FIRST, len(d), float("nan")
        due = "JUDGE NOW" if nrel >= RELEVANT_AT else "%d of %d relevant" % (nrel, RELEVANT_AT)
        print("  %-13s relevant trades %3d  paired t %6s  stop: %-40s  final read: %s" % (
            name, nrel, "n/a" if not np.isfinite(t) else "%+.2f" % t, status, due))


if __name__ == "__main__":
    main()
