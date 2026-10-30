# PREREG - GROK-ENGUQ SCORE FILTER r1 (job 1 of MANAGER #123)

2026-10-28, lane ENGU-Q. Owner GO 10-28 for a new family GROK-ENGUQ, from his TradingView indicator
"GROK ENGU (II)" (`C:\EdgeLog\_research_cache\tv_scalp\grok_engu\grok_engu_ii.pine.txt`).

FROZEN BEFORE ANY NUMBER IS COMPUTED. This document covers **job 1 only** - tagging ENGU-Q #335's own
trades with the GROK quality score and asking whether a score floor lifts the four numbers. Job 2 (the
port as a strategy plugin plus a 900-trial Auto-Validate) gets its own prereg and is not started until
job 1 is reported.

## 0. What is being tested

The GROK indicator carries a 0-15 quality score. The cheap question is whether that score, read on
**ENGU-Q #335's own entry signal bars**, separates its good trades from its bad ones. Nothing is
optimised, no parameter is searched, and **no new strategy is run** - this is a filter applied after
the fact to one fixed, existing trade list.

- The leg: `ENGUQ_1M_ETH_R2_1_0.py` on NQ 1m ETH `db_adj_eth`, cost 0.783 pts a round trip, $20 a
  point, params as `api/book_shadow.BOOK463_LEGS` holds them. Long only.
- The stretch: **walk-forward years only, 2016-10-12 .. 2025-06-27**, #335's own 8 folds, the same
  windows frozen in `docs/PREREG_enguq_executor_r1_2026-10-18.md`:

| fold | from | to | | fold | from | to |
|---|---|---|---|---|---|---|
| 1 | 2016-10-12 | 2017-11-23 | | 5 | 2021-03-08 | 2022-04-04 |
| 2 | 2017-11-23 | 2018-12-30 | | 6 | 2022-04-04 | 2023-05-02 |
| 3 | 2018-12-30 | 2020-02-03 | | 7 | 2023-05-02 | 2024-05-29 |
| 4 | 2020-02-03 | 2021-03-08 | | 8 | 2024-05-29 | 2025-06-27 |

- **The lockbox (2025-07-01 .. 2026-06-30) is not read in this round, at all.**
- A trade is tagged at its **ENTRY SIGNAL BAR** - the entry bar index the engine returns in the trade
  tuple - per the house rule. Never at the exit, never at a later bar.

## 1. The port of the score, and the one judgement call it forces

The score is ported from the Pine verbatim at the indicator's own defaults, which give **maxScore 15**:
opposite-momentum 1 + ATR expansion 1 + volume 1 + trend 1 + six body/volume extremity points + up to
five S/D points. Defaults: lookback 20, body 0.7x the prior 20-bar range, ATR 20 at 1.7x, volume SMA 20
at 1.3x, EMA 20, opposite-momentum scan 20 at 0.6x, S/D pivot length 20.

**THE JUDGEMENT CALL, DECLARED BEFORE ANY NUMBER.** In the Pine the score is direction-gated: four of
its components read `isBull ? ... : ...`, and `isBull` / `isBear` are only true on a bar where GROK's
OWN breakout fires. On any other bar the score silently collapses to the bear-side reading and the S/D
points are zero, so the raw Pine score is not defined on an arbitrary bar. ENGU-Q is long only
(asserted in the harness), so this round scores **every signal bar on the BULL side**, i.e. with
`isBull` forced true, and reports the GROK-breakout coincidence separately as its own arm. Writing it
the other way round - scoring only the bars where GROK also fired - would confound "the score is
informative" with "GROK and ENGU-Q agree", which are two different claims and are arms A and B below.

Look-ahead: the S/D pivots use `ta.pivothigh(high, 20, 20)`, which is confirmed 20 bars late, so a
level only enters the array 20 bars after the pivot - the harness reproduces that lag exactly and
asserts it. Body and volume extremity points include the current bar and nothing after it. The
"largest of the last 20" and "largest of the session so far" readings use only closed bars up to and
including the signal bar.

## 2. The arms, fixed here

| arm | definition |
|---|---|
| LEG | all of #335's WF trades, unfiltered - the baseline |
| S4 | score >= 4 |
| S6 | score >= 6 |
| S8 | score >= 8 |
| S10 | score >= 10 |
| GB | the signal bar is ALSO a GROK bull breakout (all six gates pass), score ignored |
| GB+S | a GROK bull breakout AND score >= 8 |

Seven arms, chosen now. **No threshold is added, moved or dropped after a number is seen.** Dropping a
trade means the leg simply does not take it; the remaining trades keep their own entry and exit bars
and their own P&L, and no trade is re-timed or re-priced.

## 3. The four numbers, and the bar

Every arm, every stretch: `augur_engine.drawdowns.four_numbers` on the DAILY mark-to-market series
(every session present, zero days included) -> ROC@30k, DD5, DD% from peak, Sortino, plus
`one_episode` (worst DD > 1.3 x DD5).

**An arm LIFTS only if all four hold:**

1. its whole-stretch ROC@30k beats the LEG's;
2. it beats the LEG in **>= 7 of the 8 folds** (binomial one-sided, P(X>=7 | p=0.5) = 0.035; 6 of 8 is
   SUGGESTIVE and is not a pass; <= 5 is no fold-level evidence);
3. it is **not one episode**;
4. it keeps **>= 50 trades a year**, the house floor for a readable leg.

Condition 2 is in because of the lesson this lane learned on 2026-10-18: an arm beat the leg on the
whole stretch by +2.33 ROC points while winning only 3 of 8 folds, because ROC@30k divides by the
WORST drawdown and a filter that removes one bad episode flatters it. DD5 is reported beside ROC for
the same reason - **a better ROC@30k with a WORSE DD5 means one episode moved, not an edge.**

Also reported, not gating: trades kept and dropped per arm, the dropped trades' own net, the score
distribution over all WF trades, and the per-fold difference mean and sd.

## 4. Prior, written before the data

- **I expect no arm to reach 7 of 8 folds.** Twenty-four entry gates on this family are dead, round 57
  killed entry rules outright, and the three most recent rounds (hold cap r2, shelf No. 39, executor
  r1) all found that filtering or re-timing this leg taxes it.
- I expect S4 to be nearly the whole book (so ~0 effect) and S10 to cut below the 50-trade floor.
- **I expect the GROK coincidence (GB) to be rare, and that is the interesting number even if it is
  useless as a filter.** GROK needs a close beyond a 20-bar extreme with a body over 0.7x that range
  and over 1.7x ATR; ENGU-Q is an engulfing reversal that often enters against the immediately prior
  move. If GB keeps under about 10% of the trades, the two systems are looking at different bars and
  job 2 is a genuinely NEW family rather than a re-skin of #335 - which is worth knowing before the
  port is written.
- If the score is informative at all, I expect it in the SIZE of the win rather than the direction:
  the body/volume extremity points are a volatility reading, and this family's money is in long
  survivors that begin on decisive bars.

## 5. Method pins

- Harness `tools/grokenguq_score_r1.py`, frozen with this document; it checks this file's LF sha256 at
  start, stops on a mismatch, prints its own, and has a `selftest` that reproduces the Pine's score on
  hand-made bars with no data.
- The master is pinned by FILENAME AND ROW COUNT, not by name - `find_master` silently returns today's
  tape, and a refill inside the window moves every bar index (this lane's own 10-18 finding, TTM #108).
  The harness prints both and records them.
- RUN-BEFORE-MAIN: the frozen commit is pushed to `origin` as `prereg/grokenguq-score-r1` and its
  sha256s go to MANAGER before the harness is launched.
- Addenda are appended with a time and a reason, never a replacement.
- One JSONL run record per arm per stage through `tools/run_record.py`, handed the daily series.
