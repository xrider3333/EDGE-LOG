"""TTM r27 map check (shelf No. 8, Goulding, Harvey & Mazzoleni 2023 'Momentum turning points'): the paper's LEG use - a dynamic
slow / fast blended time-series-momentum leg on ES + NQ futures, monthly - through tools/mapcheck_f.py imported UNCHANGED (PRIORS
swapped in memory, OUT pointed here). Synthetic priors only - no data read, no book look."""
import os
import sys
OUT = "C:/EdgeLog/_anatomy_cache/ttm_r27"
sys.path.insert(0, "C:/Users/xride/OneDrive/Desktop/EDGE-LOG/tools")
os.chdir("C:/Users/xride/OneDrive/Desktop/EDGE-LOG")
import mapcheck_f as MC   # noqa: E402
MC.OUT = OUT
MC.PRIORS = [
    dict(name="TURNING-POINTS-LEG", n=24, s_mid=0.25, s_sd=0.30, rho_dd=-0.15, rho_out="zero", tails="t3", vol="clustered",
         src="Dynamic slow (12m) / fast (1m) TSMOM blend on ES + NQ, monthly re-sizing, long or short (~12 position changes a market "
             "a year). The paper's US-market timing is a century of monthly data; published-to-live decay ~half (shelf No. 17 / 19). "
             "The house's own read of the static version - Q9 TREND seat, 1/3/12-month blend on 11 futures funds (ledger 2.58) - "
             "FAILED: it earned in #463's drawdown days but bled ~$1.7k a year between crises (7 of 9 WF years down). Prior "
             "0.25 +- 0.30 a year (paper ~0.5 halved); crisis hedge -> rho_dd -0.15, flat with the book otherwise"),
]
MC.main()
