# DRAFT PRE-REGISTRATION — NOISE hedge tilt inside BOOK #463 (Custom ML, 2026-10-04) — FOR MANAGER REVIEW

Status: DRAFT sent to MANAGER before any number exists (standing order 10-04, item 2: if no answer in 60 minutes,
Stage A — walk-forward only, lockbox untouched — runs anyway and the review is folded in as a dated addendum).

## Map placement first (docs/MDL_MAP_R1.md)
A re-sizing of NOISE must beat **plain extra NOISE** (a quarter more NOISE already lifts both stretches: 99.8 / 156.3).
This idea keeps every NOISE trade and re-sizes it from BOOK STATE, aimed at the map's one direction that matters at
almost any size: the book's drawdown weeks. #463's worst stretches are ENGU-Q give-backs on falling NQ (sealed-year
worst: 2026-06-18..26; 2022) and March 2020. It is judged against plain extra NOISE at the SAME average size, so
leverage alone cannot pass.

## Mechanism (written before looking)
ENGU-Q is long-only and holds for days to weeks; while it holds, the book is net long NQ. A NOISE trade taken in
the SAME direction adds to that exposure; one taken AGAINST it is a partial hedge that earns on exactly the days
the ENGU-Q leg gives back. Sizing NOISE up when it opposes the book's open ENGU-Q exposure and down when it
stacks on it should lower the book's drawdown more than it lowers its return. Not fitted to any episode; the
multipliers are fixed below.
Honest prior: weak-to-moderate. Related evidence already read: the corrected AG test (ORB/NOISE agreement, fill
times) found same-direction stacked trades no better, if anything worse, per dollar (walk-forward paired t -1.96)
- a different pair (ORB, not ENGU-Q), so it motivates but does not establish this.

## Rule
- State at each NOISE #422 trade's FILL time (NOISE fills at its entry bar's open): ENGU-Q #463 leg
  (ENGUQ_1M_ETH_R2_1_0.py, #463's params, db_adj_eth) holds an open long that FILLED strictly before it and has not
  yet exited (exit = exit bar label + 1 minute, its bar's close).
- Multipliers (fixed): NOISE short while ENGU-Q long = **1.5x** (hedge); NOISE long while ENGU-Q long = **0.5x**
  (stacked); ENGU-Q flat = **1.0x**. No other leg changes.

## Stage A (walk-forward only; lockbox untouched)
Book = #463's four legs exactly as api/book_shadow.BOOK463_LEGS, valued daily, the unified ROC convention
(#463 = WF 93.8 %/yr at a $30k drawdown, Sortino 3.82). WF = 2016-07-01 .. 2025-06-29.
- **Twin (plain extra NOISE):** #463 with NOISE scaled by c = the mean multiplier the rule assigns over WF NOISE
  trades (counts of states only, no outcomes).
- **PASS needs all:**
  1. tilted book beats the twin AND #463 on WF ROC at a $30k drawdown AND on WF Sortino;
  2. still beats the twin on ROC with 2020-02-01..04-30 removed;
  3. beats the twin on ROC in at least 6 of the 9 WF years (July-June);
  4. untuned check: beats the twin on ROC in the 2011-01-01 .. 2016-06-30 block;
  5. family-aware null: the tilted book's WF ROC lead over the twin exceeds the 95th percentile of 200 placebo
     books in which ENGU-Q's position calendar is circularly shifted by a random 20..250 trading days (keeps its
     clustering and duty cycle, breaks its timing), seed 20261004;
  6. at least 100 tilted NOISE trades in WF.
- FAIL on any = dead, ledger + lane doc, no variants (no other multipliers, no ORB/TTM version).
- PASS -> to MANAGER for ONE lockbox read (a BOOK run if the book engine can express a per-trade state size,
  otherwise a forward no-order shadow book line with the paired early stop); the RUNBOARD gets the run either way.

Driver (to be written after review): tools/noise_hedge_tilt.py.
