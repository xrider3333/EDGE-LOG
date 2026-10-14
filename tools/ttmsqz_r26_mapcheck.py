"""TTM r26 map checks (MANAGER #108 'keep testing'): two new TTM-family leg ideas through the house power-first map,
tools/mapcheck_f.py imported UNCHANGED (its PRIORS list swapped in memory; its OUT pointed here so Custom ML's record is not
overwritten). Synthetic priors only - no real data read, no book look."""
import os
import sys
OUT = "C:/EdgeLog/_anatomy_cache/ttm_r26"          # log copy: tools/data/ttmsqz_r26_mapcheck.txt
sys.path.insert(0, "C:/Users/xride/OneDrive/Desktop/EDGE-LOG/tools")
os.chdir("C:/Users/xride/OneDrive/Desktop/EDGE-LOG")
import mapcheck_f as MC   # noqa: E402
MC.OUT = OUT
MC.PRIORS = [
    dict(name="TTM-ETF-SLEEVE", n=280, s_mid=0.15, s_sd=0.25, rho_dd=0.30, rho_out="same", tails="t3", vol="clustered",
         src="TTM #459's frozen rules on 14 ETFs at 30m (SPY, IWM, DIA, SMH + 10 sector ETFs; data 2016-26 held), pooled as one "
             "leg, ~20 fires a market a year. ES #459 itself: WF yearly Sharpe ~0.7 at real cost (ROC 12.5, Sortino 1.18). Every "
             "transfer so far failed: the whole stack on NQ (TTM.md row 17), the crown on 35 large stocks (r20c, pooled ROC -3.0). "
             "Per-market prior ~0.1, pooled at pairwise correlation ~0.5 -> ~0.15 +- 0.25; breakout legs lose with the book in "
             "crash weeks -> rho_dd +0.3"),
    dict(name="TTM-ES-OVERNIGHT", n=25, s_mid=0.15, s_sd=0.30, rho_dd=0.20, rho_out="same", tails="t3", vol="clustered",
         src="TTM #459's rules on ES 30m bars built from the 5m ETH master (db_adj_eth 2010-26 held), overnight hours only "
             "(18:00-09:30 ET), flat by 09:30. Overnight ES has about half the RTH range and weaker breakout follow-through; the "
             "house's overnight evidence is small (OVERNIGHT-DOWNDAY prior 0.15). ~25 fires a year"),
]
MC.main()
