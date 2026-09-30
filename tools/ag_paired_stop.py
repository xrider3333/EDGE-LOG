"""Paired early stop for Frontier's AG shadow line on BOOK #463 (Frontier inbox #28, 2026-09-30).
Rule: docs/PREREG_paired_sequential_stop_2026-09-29.md, section "Frontier's AG line"; the Frontier read in
C:\\EdgeLog\\_anatomy_cache\\adopt449\\PREREG_SHADOWS_0929.txt stays the verdict.

AG = 1.5x on an ORB (#234) or NOISE (#422) trade entering while the OTHER leg holds a trade the same way (on a
same-bar same-direction entry the NOISE trade takes it) - exactly api/book_shadow.agreement_tilted. Every ORB and
NOISE trade enters the paired series as d = (m - c) x trade $, c = the walk-forward mean of m, so the test asks
whether the 1.5x lands on better trades, not whether more size made more money.

    python tools/ag_paired_stop.py        prints c, the tilted share, and the calibrated boundary
Run from the shared checkout (needs the master registry) or set EDGELOG_ROOT to it.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
WF0, LB0 = pd.Timestamp("2016-06-30"), pd.Timestamp("2025-07-16")
TILTED_READ = 100


def leg(L):
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    A = load_master_arrays(find_master(L["instrument"], L["timeframe"], L["session"], L["source"]), date_from="2010-06-07")
    r = run_backtest(L["strategy"], arrays=A, params=L["params"], cost_pts=L["cost_pts"], return_trades=True)
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    T = sorted(r["trades"], key=lambda t: t[0])
    return pd.DataFrame({"e": idx[[int(t[0]) for t in T]], "x": idx[[min(int(t[1]), len(idx) - 1) for t in T]],
                         "side": [1 if float(t[3]) > 0 else -1 for t in T],
                         "usd": [float(t[2]) * L["mult"] * L["weight"] for t in T]})


def tilt(mine, other, is_noise):
    oe, ox, os_ = other.e.to_numpy(), other.x.to_numpy(), other.side.to_numpy()
    m = np.ones(len(mine))
    for i, (e, s) in enumerate(zip(mine.e.to_numpy(), mine.side.to_numpy())):
        hit = (os_ == s) & (((oe < e) & (e < ox)) | ((oe == e) & is_noise))
        if hit.any():
            m[i] = 1.5
    return m


def main(reps=4000, seed=20260930):
    from api.book_shadow import BOOK463_LEGS
    import paired_seq_stop as Q
    orb = leg([L for L in BOOK463_LEGS if L["strategy"].startswith("ORB")][0])
    noi = leg([L for L in BOOK463_LEGS if L["strategy"].startswith("NOISE")][0])
    allt = pd.concat([orb.assign(m=tilt(orb, noi, False)), noi.assign(m=tilt(noi, orb, True))]).sort_values("e")
    wf = allt[(allt.e >= WF0) & (allt.e < LB0)]
    c = float(wf.m.mean())
    share = float((wf.m > 1).mean())
    nmax = int(np.ceil(TILTED_READ / share))
    yrs = (LB0 - WF0).days / 365.25
    d = (wf.m - c) * wf.usd
    m, u = wf.m.to_numpy(), wf.usd.to_numpy()
    rng = np.random.default_rng(seed)
    for b in np.arange(3.0, 8.01, 0.25):
        stops = sum(Q.read_pair((rng.choice(m, nmax) - c) * rng.choice(u, nmax), np.ones(nmax), np.zeros(nmax), 0.0, b)[0]
                    != "continue" for _ in range(reps))
        if stops / reps <= 0.05:
            break
    print(f"AG: WF ORB+NOISE trades {len(wf)} ({len(wf) / yrs:.0f}/yr), tilted {100 * share:.1f}% "
          f"({share * len(wf) / yrs:.0f}/yr); c = {c:.4f}; series length to {TILTED_READ} tilted = {nmax}; "
          f"boundary |t| >= {b:.2f} (false stops {100 * stops / reps:.1f}%); WF paired t {Q.tstat(d):+.2f} (context only)")


if __name__ == "__main__":
    sys.exit(main())
