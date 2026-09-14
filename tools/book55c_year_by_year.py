"""
BOOK ROUND 55c - does #379 beat #366 YEAR BY YEAR, or only in aggregate? And the same for the tilt. (2026-09-14)

Run #379 beats the adopted book #366 on the selection window (44.35 against 38.18) and on the held-back
year. Both are single ratios over long stretches, and a maximum drawdown is ONE bad stretch - so a
book can win the ratio by dodging one drawdown while losing most years. Adoption is pending with the
owner, so this is the evidence that decision should rest on.

For each calendar year 2011-2025 (2010 and 2026 are partial and reported but not counted):
    net profit and the worst peak-to-trough inside that year, for each book;
    DOMINATES = at least as much net AND no deeper drawdown; LOSES = less net AND deeper drawdown.
And the change split by slot, so the two swaps can be judged separately:
    opening-range swap (#314 in place of #234) and squeeze swap (combined leg in place of stop-only).

PRE-REGISTERED: #379 is a robust improvement if it DOMINATES in at least 9 of the 15 full years and
LOSES in no more than 3. The round-55 tilt is judged the same way against #379.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from book55b_tilt_null import trades, to_daily, pool, NOISE_CROWN, S   # same harness, same legs

YEARS = list(range(2011, 2026))


def yearly(s):
    s = s.sort_index()
    rows = {}
    for y in range(2010, 2027):
        z = s[(s.index >= pd.Timestamp(f"{y}-01-01")) & (s.index < pd.Timestamp(f"{y+1}-01-01"))]
        if len(z) == 0:
            continue
        cum = z.cumsum()
        rows[y] = (float(z.sum()), float(-(cum - cum.cummax()).min()))
    return rows


def compare(name_a, a, name_b, b):
    ya, yb = yearly(a), yearly(b)
    dom = lose = 0
    print(f"\n  {name_b}  vs  {name_a}")
    print(f"    {'year':5} {'net A':>10} {'DD A':>8} {'net B':>10} {'DD B':>8}  verdict")
    for y in sorted(set(ya) | set(yb)):
        na, da = ya.get(y, (0.0, 0.0)); nb, db = yb.get(y, (0.0, 0.0))
        if nb >= na and db <= da:
            v = "B dominates"
        elif nb < na and db > da:
            v = "B LOSES"
        else:
            v = "mixed"
        if y in YEARS:
            dom += v == "B dominates"; lose += v == "B LOSES"
        tag = "" if y in YEARS else "  (partial, not counted)"
        print(f"    {y:5} {na:>10,.0f} {da:>8,.0f} {nb:>10,.0f} {db:>8,.0f}  {v}{tag}")
    ok = dom >= 9 and lose <= 3
    print(f"    => dominates {dom} of {len(YEARS)} full years, loses {lose}  ->  "
          f"{'ROBUST by the pre-registered test' if ok else 'NOT robust by the pre-registered test'}")
    return dom, lose


def slot_years(label, old, new):
    yo, yn = yearly(old), yearly(new)
    better = sum(1 for y in YEARS if yn.get(y, (0, 0))[0] > yo.get(y, (0, 0))[0])
    diff = [yn.get(y, (0, 0))[0] - yo.get(y, (0, 0))[0] for y in YEARS]
    print(f"    {label:42} more net in {better:2} of {len(YEARS)} years; "
          f"median yearly change ${np.median(diff):>9,.0f}; worst ${min(diff):>9,.0f}")


if __name__ == "__main__":
    print("building legs")
    orb314 = to_daily(trades(S + "ORB_3_6_R6.py", "NQ", "5m", "rth", 0.533, 20.0, None))
    orb234 = to_daily(trades(S + "ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, None))
    enq = to_daily(trades(S + "ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None))
    ttm_c = to_daily(trades(S + "TTMSQZ_3_0_ES30SSOF2.py", "ES", "30m", "rth", 0.363, 50.0, None)) * 3.0
    ttm_s = to_daily(trades(S + "TTMSQZ_3_0_ES30SS20.py", "ES", "30m", "rth", 0.363, 50.0, None)) * 3.0
    raw_t = trades(S + "NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN)
    hsq_t = trades(S + "NOISE_1_9_HSQ304.py", "NQ", "5m", "rth", 0.533, 20.0, None)
    raw = to_daily(raw_t); hsq = to_daily(hsq_t)

    b366 = pool(orb234, enq, ttm_s, raw)
    b379 = pool(orb314, enq, ttm_c, raw)
    tilt = pool(orb314, enq, ttm_c, raw, hsq)
    compare("#366 adopted", b366, "#379 both crowns", b379)
    print("\n  where the #379 change comes from, slot by slot:")
    slot_years("opening-range swap (#314 for #234)", orb234, orb314)
    slot_years("squeeze swap (combined for stop-only, x3)", ttm_s, ttm_c)
    compare("#379 both crowns", b379, "#379 + hourly-squeeze tilt", tilt)
