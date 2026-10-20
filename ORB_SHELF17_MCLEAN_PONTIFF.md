# READING SHELF No. 17: McLean & Pontiff 2016, "Does Academic Research Destroy Stock Return Predictability?", applied to ORB #314 (ORB lane, 2026-10-20)

**Verdict: CLOSED AT DRAFT** by the power-first gate. No mean after the publication cut was computed or printed.

**The question.** The paper finds that published anomalies earn about 58% less after publication. Did #314's net edge a trade fall
after its own source paper went public? The source is shelf No. 4 (Zarattini & Aziz, SSRN 4416622, posted April 2023), so the cut is 2023-05-01.
The pick was posted before any number (MANAGER #1546).

**Power line** (`C:\EdgeLog\_anatomy_cache\shelf17\power_shelf17.py`, stdout beside it):
- #314 on NQ 5m RTH at 0.533 pt. The unit is net % of the raw close, a trade.
- PRE = WF 2016-07-01 .. 2023-04-30: 965 trades, +0.096% a trade. POST = 2023-05-01 .. 2025-06-27: 316 trades (count only).
- On the calibrated two-sample test (null SE, as Welch), a 58% drop is 1.21 SE on the pre-WF dispersion (0.71% a trade) and 0.98 SE
  on PRE's own (0.88%). The gate needs 2.0.
  - The script's first print (1.35 / 1.10) used the delta-method SE at ratio 0.42. That test is oversized: from PRE trades, it
    rejects 8% at a nominal 5% under no change.
- A block SE does not help. On PRE it is 0.84-0.87 x iid, and even at that size the drop stays at or below 1.59 SE.
- Adding the lockbox and forward (~190 trades) gives 1.43 SE. Reaching 2.0 needs about 2,000 post trades (around 2037) on the
  pre-WF dispersion. On PRE's own dispersion it is never reached: PRE's 965 trades cap the z at 1.98.

**Blind check** (ORB-lane workflow, `C:\EdgeLog\_anatomy_cache\wf_orb1020\`). An adversarial verifier re-derived every input
(965 / 0.0962% / 0.875% / 0.713% / 316) and the trade fields: exit bar, same-session dating, raw-close alignment, one cost a round trip.
It then simulated a pseudo-POST of 316 trades from PRE trades only, with 58% of the edge removed. No pre-specifiable metric
gets near 80% power:
- mean: 25-33% one-sided;
- trimmed mean and rank test: 22-35%;
- profit factor: 25-28%;
- win rate: 17-23%;
- 200-trade-block permutation: cannot reject two-sided.

**What already stands** (cited, not redone):
- ORB EDGE IMPROVING (09-09): PF 1.09 -> 1.41 across 200-trade blocks, also with the top 5 winners removed.
- DECAY r1 (ledger 2.177): ORB lockbox / WF Sharpe 1.00.
- The NOISE twin of this read is ledger 2.181.

Nothing is queued. No run record (no P&L curve).
