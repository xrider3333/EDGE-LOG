"""
BOOK ROUND 55d - the correction round 55c forces: judge the two #379 swaps SEPARATELY, year by year (2026-09-14).

Round 55c showed #379 does NOT robustly beat #366 year by year (dominates 5 of 15 full years, loses 4),
and split the change by slot: the SQUEEZE swap earns more in 13 of 15 years (worst year -4,061 dollars),
while the OPENING-RANGE swap is a coin flip (8 of 15, worst year -27,405). #379's ratio win over #366 is
largely one drawdown - 2020, where #366 sets its whole-window maximum of 36,562 and #379 does not.

So this scores the book with ONLY the squeeze swap - #366 with the combined squeeze leg, the opening-range
control kept - against #366 and against #379, with the same pre-registered year test (dominate at least 9
of 15 full years, lose no more than 3), and adds the hourly-squeeze tilt on top of it for completeness.
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools")); os.chdir(ROOT)
from book55b_tilt_null import trades, to_daily, pool, mar2, NOISE_CROWN, S
from book55c_year_by_year import compare

if __name__ == "__main__":
    orb314 = to_daily(trades(S + "ORB_3_6_R6.py", "NQ", "5m", "rth", 0.533, 20.0, None))
    orb234 = to_daily(trades(S + "ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, None))
    enq = to_daily(trades(S + "ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None))
    ttm_c = to_daily(trades(S + "TTMSQZ_3_0_ES30SSOF2.py", "ES", "30m", "rth", 0.363, 50.0, None)) * 3.0
    ttm_s = to_daily(trades(S + "TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None)) * 3.0
    raw = to_daily(trades(S + "NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN))
    hsq = to_daily(trades(S + "NOISE_1_9_HSQ304.py", "NQ", "5m", "rth", 0.533, 20.0, None))
    b366 = pool(orb234, enq, ttm_s, raw)
    b379 = pool(orb314, enq, ttm_c, raw)
    sq_only = pool(orb234, enq, ttm_c, raw)
    sq_tilt = pool(orb234, enq, ttm_c, raw, hsq)
    for nm, s in (("#366 adopted", b366), ("#379 both swaps", b379), ("SQUEEZE SWAP ONLY", sq_only),
                  ("squeeze swap only + hourly tilt", sq_tilt)):
        m = mar2(s)
        print(f"  {nm:34} selection {m[0]:6.2f}   held-back {m[1]:6.2f}   whole-window net ${s.sum():>10,.0f}")
    compare("#366 adopted", b366, "SQUEEZE SWAP ONLY", sq_only)
    compare("SQUEEZE SWAP ONLY", sq_only, "#379 both swaps", b379)
