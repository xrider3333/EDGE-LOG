# RESULTS - GROK-ENGUQ SCORE FILTER r1 (job 1 of MANAGER #123)

Run 2026-10-28, reported 2026-10-30. Prereg `docs/PREREG_grokenguq_score_r1_2026-10-28.md`, frozen
commit `d46a77d6516244f329d443c12893670065716030` on `prereg/grokenguq-score-r1`, hashes posted to
MANAGER (#1730) before the run and matched at start. Harness `tools/grokenguq_score_r1.py`. Log
`C:\EdgeLog\grokenguq_score_r1.log`, record `C:\EdgeLog\_anatomy_cache\grokenguq_score_r1\`.
Master pinned: `ADJ_NQ_1m_ETH.csv`, registry rows 5,555,154, bars loaded 5,440,704.

**The answer in one line: GROK and ENGU-Q never fire on the same bar - 0 of 2,053 - so GROK-ENGUQ is a
genuinely new family, and the score used as a filter on #335 is strongly NEGATIVE, not null.**

## 1. The overlap: zero, and it is not because GROK is quiet

| reading | count |
|---|---|
| GROK bull breakouts in the whole tape | **8,306** of 5,440,704 bars (0.153%, one every 655 bars) |
| ... on the walk-forward stretch | 4,666 |
| **ENGU-Q entry bars that ARE a GROK bull breakout** | **0 of 2,053** |
| ENGU-Q entries within +/-1 bar of one | 112 (5.5%) |
| ... within +/-5 bars | 193 (9.4%) |
| ... within +/-20 bars | 274 (13.3%) |
| ... within +/-60 bars | 418 (20.4%) |

The gate ladder, each filter alone and then cumulative, shows what makes a GROK breakout rare:

| gate | alone | cumulative |
|---|---|---|
| bullish | 2,314,043 (42.5%) | 2,314,043 |
| close > 20-bar high | 287,708 (5.3%) | 278,194 |
| **body > 0.7x the prior 20-bar range** | **22,707 (0.42%)** | **9,561** |
| opposite-momentum pass | 5,437,684 (99.9%) | 8,624 |
| body > 1.7x ATR20 | 138,724 (2.6%) | 8,417 |
| volume > 1.3x avg20 | 1,262,547 (23.2%) | 8,306 |
| close > EMA20 | 2,828,513 (52.0%) | 8,306 |

- The binding gate is the body-versus-range test; the opposite-momentum filter is almost free (it
  passes 99.9% of bars, because the Pine only runs its scan on an already-valid breakout body).
- **Zero overlap, but not independence.** At a 0.153% base rate, chance would put about 0.46% of
  entries within +/-1 bar of a breakout. The observed 5.5% is about TWELVE TIMES that. The two systems
  watch the same events and take opposite moments of them: GROK buys the thrust bar that closes beyond
  a 20-bar high, ENGU-Q buys the reversal around it.
- **The consequence for job 2, which this round was partly run to settle:** GROK-ENGUQ cannot be
  scored as a variant of #335, cannot borrow its trade set, and needs its own exit rule. It is a new
  family, and its prereg has to say so before an exit is chosen.

## 2. The score on #335's own trades

Mean 2.74 of a maximum 15, over all 2,053 trades. Distribution:

| score | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| trades | 36 | 1,114 | 605 | 141 | 66 | 46 | 16 | 12 | 13 | 2 | 2 |

ENGU-Q's entry bars are low-quality by GROK's measure almost always, which is what the zero overlap
already implied.

## 3. The arms, WF 2016-10-12 .. 2025-06-27

| arm | trades | tr/yr | ROC@30k | DD5 | DD% | Sortino | one episode | vs leg |
|---|---|---|---|---|---|---|---|---|
| LEG | 1,167 | 134 | **26.41** | $31,272 | 14.81% | 1.615 | yes | - |
| S4 (score >= 4) | 157 | 18 | **-1.36** | $9,721 | 30.99% | -0.149 | yes | -27.77 |
| S6 | 42 | 5 | -1.26 | $15,146 | 23.64% | -0.140 | yes | -27.67 |
| S8 | 13 | 1 | 2.09 | $2,085 | 6.49% | 0.360 | yes | -24.33 |
| S10 | **0** | 0 | - | - | - | - | - | EMPTY |
| GB (GROK breakout) | **0** | 0 | - | - | - | - | - | EMPTY |
| GB+S | **0** | 0 | - | - | - | - | - | EMPTY |

**S10, GB and GB+S keep ZERO trades on the walk-forward stretch.** The harness printed 0.00 in their
figure columns; those are "no trades", NOT results, and must never be quoted as figures. Only 4 trades
in the whole 2010-2026 set score 10 or more and none of them falls inside the walk-forward years.

Fold by fold, wins against the bare leg (bar: >= 7 of 8):

| arm | f1 | f2 | f3 | f4 | f5 | f6 | f7 | f8 | wins | mean | sd |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S4 | -133.7 | -48.8 | +7.8 | -101.9 | -115.6 | -9.2 | -35.2 | -93.1 | 1 of 8 | -66.21 | 52.06 |
| S6 | -125.1 | -59.6 | +21.9 | -101.9 | -122.3 | +1.8 | -55.6 | -140.5 | 2 of 8 | -72.66 | 60.48 |
| S8 | -135.1 | -59.6 | +37.6 | -101.9 | -137.5 | +8.0 | -55.4 | +254.1 | 3 of 8 | -23.74 | 128.55 |

**Every arm fails the bar on all four conditions.** S8's +254 in fold 8 on 13 trades across nine years
is a single-trade artefact, not an edge, and its mean of -23.74 with an sd of 128.55 says so.

## 4. What this changes

1. **The score is informative with the WRONG SIGN.** Keeping only the bars GROK rates highly turns
   +26.41 into about zero. The high-score bars are the ones ENGU-Q loses on, which is mechanically
   sensible - the score rewards the most extended bar of the session, and entering a reversal there is
   the worst case for this leg.
2. **GROK-ENGUQ is a new family.** Job 2's prereg must treat it as one: its own exit rule, its own
   lattice, its own lockbox discipline, and no reuse of #335's trades or crown.
3. **NOT TESTED, deliberately:** the inverse filter (keep only the LOW-score bars). That threshold is
   not in the frozen prereg, and adding it after seeing these numbers is exactly the selection this
   lane pre-registers to avoid. It is a one-line question and it needs its own prereg; my own view is
   that it is the complement of the same read, and this family already carries 24 dead entry gates.
4. **An operational note for anyone porting Pine:** the opposite-momentum filter passes 99.9% of bars
   because the Pine only runs its scan when the body is already a valid breakout body, so a
   small-bodied bar is GIVEN that point. The port reproduces the quirk rather than fixing it; a
   "corrected" port would be a different indicator from the owner's.
