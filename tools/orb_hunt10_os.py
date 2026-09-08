# -*- coding: utf-8 -*-
"""
ORB round 10 / OS: does DELAYING the opening range help the #314 crown?
(2026-09-08). Every earlier sweep varied or_bars (the range LENGTH) but never where the
range STARTS. ORB_3_6_OS adds or_start_bar. Sweep 0 (crown), 3 (9:45), 6 (10:00, covers
the 10:00 data releases), 9 (10:15), 12 (10:30), and or_bars 2/3 at each start.

Pre-registered gates (ROUND10_SPEC): G1 5y MAR > 2.79 and full MAR > 0.85; G2 full net
>= 95% of $397,150; G3 OOS net and PF >= crown's; G4 plateau (neighbours keep 70% of the
5y MAR gain); G5 trades/yr >= 120. Trades after LB_END are never loaded.

RESULT (2026-09-08): DEAD, decisively. Full-window MAR crown 0.85 -> 9:45 start 0.21 ->
10:00 start 0.01 -> 10:15 0.15 -> 10:30 0.03; the 5-year window the same (2.79 -> 0.63 /
0.22 / 0.50 / 0.06). Changing or_bars at a delayed start does not rescue it. ORB's edge is
the 9:30 open itself - the first ten minutes' direction and range; a range formed any
later carries almost none of it. Do not re-propose a delayed or "second" opening range.

    python tools/orb_hunt10_os.py
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.orb_pick import bars, stats, sessions, BASE, COST, MULT          # noqa: E402
from tools.orb_hunt import strat, IS_END, LB_END                            # noqa: E402

CROWN = dict(BASE, atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0, be_after_R=0.5)
FIVE_Y = "2021-08-13"


def trades(over):
    b = bars()
    r = strat("ORB_3_6_OS.py").run_backtest(b["open"], b["high"], b["low"], b["close"],
                                            volumes=b["volume"], day_id=b["day_id"],
                                            return_trades=True, **dict(CROWN, **over))
    idx = b["index"]; le = pd.Timestamp(LB_END, tz=idx.tz)
    return [(idx[t[0]].tz_localize(None), (t[2] - COST) * MULT) for t in (r or {}).get("trades") or []
            if idx[t[0]] <= le]


def row(label, tr, lo, hi, days):
    w = [(d, p) for d, p in tr if d >= pd.Timestamp(lo) and d <= pd.Timestamp(hi)]
    s = stats(w, lo, days)
    if s is None:
        return "%-22s  (fewer than 20 trades)" % label
    return "%-22s n %4d  net $%9.0f  DD $%7.0f  PF %.3f  MAR %5.2f  EVR %.3f  R/YR %5.1f  w12 %3.0f%%" % (
        label, s["n"], s["net"], s["dd"], s["pf"], s["mar"], s["evr"], s["ryr"], s["win12"])


def main():
    days = sessions()
    grid = [("crown s0", {}), ("s3 9:45", dict(or_start_bar=3)), ("s6 10:00", dict(or_start_bar=6)),
            ("s9 10:15", dict(or_start_bar=9)), ("s12 10:30", dict(or_start_bar=12)),
            ("s6 ob3", dict(or_start_bar=6, or_bars=3)), ("s3 ob3", dict(or_start_bar=3, or_bars=3)),
            ("s6 ob1", dict(or_start_bar=6, or_bars=1)), ("s12 ob3", dict(or_start_bar=12, or_bars=3))]
    res = {k: trades(o) for k, o in grid}
    for wname, lo, hi in [("FULL (<= lockbox start)", "2010-01-01", LB_END), ("IS", "2010-01-01", IS_END),
                          ("OOS 2025-08-13..2026-08-13", IS_END, LB_END), ("5-YEAR", FIVE_Y, LB_END)]:
        print("\n== %s ==" % wname)
        for k, _ in grid:
            print(row(k, res[k], lo, hi, days))


if __name__ == "__main__":
    main()
