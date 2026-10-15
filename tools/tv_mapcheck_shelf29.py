# MAPCHECK-F for reading-shelf paper #29 (Kurov, Sancetta, Strasser, Wolfe 2019, JFQA: "Price Drift Before U.S. Macroeconomic
# News") - TV, 2026-10-15. Imports tools/mapcheck_f.py unchanged, adds this paper's priors, runs only them and writes to TV's own
# folder (never CUSTOM-ML's MAPCHECK_F.txt / .csv). A synthetic prior, not a book look.
#   python tools/tv_mapcheck_shelf29.py
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, os.path.join(SHARED, "tools"))
sys.path.insert(0, SHARED)
import mapcheck_f as MC                                                  # noqa: E402

MC.OUT = r"C:\EdgeLog\_research_cache\tv_shelf\paper29_mapcheck"
SRC = ("Kurov et al. 2019 (abstract, RePEc page read 10-15): 30 US releases; 9 of the 20 that move markets show informed "
       "trading - E-mini and Treasury futures drift the 'correct' way from ~30 min before the release, ~40% of the total move. Trade: at 09:55 ET follow the 09:30-09:55 NQ move, exit "
       "10:05, on the 9 drift releases (~108 a year). Per-trade edge guess ~1.5 pt on a ~15 pt move minus 0.706 cost -> ~0.05 per-trade Sharpe x sqrt(108) ~0.52, halved for "
       "post-publication decay and the 2013-14 end of paid early data access that the paper's own leak story rests on.")
MC.PRIORS += [
    dict(name="SHELF29-PREDRIFT", n=108, s_mid=0.26, s_sd=0.25, rho_dd=0.0, rho_out="zero", tails="t3", vol="clustered", src=SRC),
    dict(name="SHELF29-PREDRIFT (as published)", n=108, s_mid=0.52, s_sd=0.25, rho_dd=0.0, rho_out="zero", tails="t3",
         vol="clustered", src="the same, NO decay shrink (upper bound)"),
]

if __name__ == "__main__":
    MC.main(["SHELF29-PREDRIFT", "SHELF29-PREDRIFT (as published)"])
