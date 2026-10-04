# PRE-REGISTRATION (DRAFT for MANAGER review) — NOISE round 69: is NOISE #422's compression size-up too small? (2026-10-04)

Owner ask via MANAGER (10-04): push the frontier (BOOK #463, WF 93.8 / LB 155.5 %/yr ROC at a $30k drawdown) with one
best remaining shot for NOISE, pre-registered, draft reviewed before anything runs. Nothing below has been computed.

## Why this is the one shot
Twelve rounds since 09-24 closed every other NOISE lever (filters, entry timing, exits incl. three breakeven tests,
pyramids, order flow, ES and overnight information). The corpus lesson (book lane, 10-03): survivors keep every trade and
RE-SIZE it from state; NOISE #422's hourly-compression size-up is the one NOISE change that has held everywhere. Two
independent hints, both already on record, say its size is too small:
1. #422's own validate (run #422, NOISE-55) crowned tilt 1.75 - the TOP edge of its 1.25 / 1.5 / 1.75 grid.
2. Round 62: KEEL v12's squeeze multiplier lands on the same compressed trades (615 of 615), lifting their weight from
   1.75x to ~2.6x, and removing it made money AND return per drawdown worse at every seed.
ROC at a $30k drawdown is leverage-free, so only the RELATIVE weight of compressed vs other trades can move it: if
compressed-hour breaks earn more per unit of risk, more weight raises it until concentration bites.

## Rule, fixed now
NOISE #422 unchanged (crown core, 60-minute compression gate 20 bars, ratio 1.15) except the size on a compressed
decision bar: PRIMARY 2.25x (others 1x). Neighbours reported, never picked from: 2.0x and 2.75x. Twin = #422 (1.75x).
Same per-trade size arithmetic as the strategy file (s x net), rebuilt legs reproducing NOISE_1_8_CT304H trade for trade
first (round 68's harness).

## Bar (all must hold)
1. Owner yardstick vs #422: ROC %/yr at a $30k drawdown (valued daily) AND Sortino higher in BOTH walk-forward
   (2016-06-30 .. 2025-07-16) and lockbox (.. 2026-07-16); >= 100 WF / 50 LB trades; LB profitable without its top trade.
2. Plateau: both neighbours beat #422's walk-forward ROC at $30k.
3. Aim, not leverage: the 2.25x cell's ROC at $30k beats the 95th percentile of 1,000 shuffles of its OWN sizes across
   trades (within each stretch), in BOTH stretches (Custom ML's shuffle-of-own-sizes null).
4. Concentration: the lockbox share of net from its top 5 trades rises by no more than 10 points over #422's.
Data: NQ 5-minute RTH no-adjust master to 2026-09-16, cost 0.533/contract, $20/pt, $100k.

## Book readout (descriptive, owned by the book lane)
BOOK #463 with its NOISE leg at 2.25x instead of 1.75x, same book convention, against WF 93.8 / LB 155.5 - handed to
the book lane to judge; this round claims nothing about the book.

## If it passes
Fenced house Auto-Validate: a CT304H sibling with tilt_mult in {1.75, 2.0, 2.25, 2.5, 2.75}, gate fixed, pinned
date_from 2010-06-07 / date_to 2026-07-16, 900 trials; then the RUNBOARD watch list and the book lane. A failure is
recorded dead and #422 stays at 1.75x.
