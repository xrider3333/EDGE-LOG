# DRIFTBURST r1 - fade a volatility-normalised drift burst on NQ / ES 1m: CLOSED AT DRAFT (TV, 2026-10-16)

Prereg `docs/PREREG_tv_driftburst_r1_2026-10-16.md` (LF sha256 03e47387..., witness prereg/tv-driftburst @ 1bcac370, pushed and posted
to MANAGER before the run; two adversarial reviews before the freeze). Harness `tools/tv_driftburst_r1.py` (LF 74bf42ec...; MAPCHECK-F
pinned). Output `C:\EdgeLog\_research_cache\tv_scalp\driftburst_r1\` (result.json, MAPCHECK_F.txt / .csv; log `..\driftburst_r1_run.log`
- the launcher fired the run twice, 17:26 and 17:28; both runs are identical, reported to MANAGER as a detach.py bug).
Source: TV's scalper scout of 10-16 - Christensen, Oomen and Reno (2022), "The drift burst hypothesis" (J. Econometrics).

PRE-WF ROWS ONLY: NQ 1m ETH no-adjust id 34 and ES id 30, 2010-06-07 .. 2016-06-30 (1.94M / 2.10M bars). The walk-forward and the
lockbox were not read. Costs NQ 0.706 / ES 0.582 pt; 24 cells (CROSS / EXHAUST entry x k 5/15/30 x c 4/6 x H 15/60); 2,578 global
burst clusters.

## Verdict: CLOSED AT DRAFT - every cell loses after cost
- All 24 cells have a NEGATIVE pooled event t (CROSS k5 c4 H15 -8.0; EXHAUST k5 c4 H15 -10.7). Net PF 0.51-0.95 in every cell and
  market. The candidate (best pooled t) is EXHAUST k30 c6 H15: t -0.64 vs the family-wise null's 95th percentile 1.32, 25 events a
  year, NQ PF 0.954 (223 trades), ES 0.860 (183).
- Failed conditions: (1) not above the null with a positive net; (2) does not earn in both markets; (3) too thin (25 events a year);
  (4) MAPCHECK-F: GREYED (< 50 a year; halved Sharpe floored at 0 -> own ROC -0.1, P(lift #463) 11%).
- Four numbers, candidate pooled daily P&L (ROC@30k / DD5@30k / DD% from peak / Sortino): -3.9 / $7.9k / 28.8% / -0.36 (1 EPISODE).
  The busiest cell (CROSS k5 c4 H15, ~400 events a year): NQ -4.9 / $15.0k / 29.9% / -3.01, ES -4.9 / $15.0k / 30.0% / -3.00.

## Reading
- At 1-minute resolution, NQ / ES drift bursts do not revert enough to pay a 2-tick round trip: the fade is near zero GROSS (EXHAUST
  k5 c4 H15 fades lose ~0.2 pt a trade before cost) and the cost does the rest. The paper's reversion lives at tick speed, below the
  house's bar size - the same lesson as the order-flow and lead-lag literature (the scout's 'negative evidence' rows).
- The continuation mirror is not an edge either: its best gross t is 2.3 (1 of 24 mirrors, before cost), ~0.2 pt a trade - dead at cost.
- Macro-minute share of trades 3-5%: the bursts are mostly not release-driven.
- Short-horizon NQ / ES remains closed ground at the house's bar size and cost (10-12 scalp hunt, the Super Scalper splits, now this).
