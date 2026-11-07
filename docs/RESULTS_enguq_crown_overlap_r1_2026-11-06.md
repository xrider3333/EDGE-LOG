# ENGU-Q crown overlap r1 — does crown #335 already take the owner's pullback-break shape?

**Verdict: no. The owner has NOT rediscovered his own crown's trigger.** The association is real but
modest, it lives entirely in the loose slope arms with a big body, and the strict drift arms are
unrelated to the crown's entries altogether. The pullback-break round's novelty survives this check.
What the round already failed on is its own fold bar
(`docs/RESULTS_enguq_pullback_break_r2_2026-11-06.md`), and nothing here changes that.

Harness `tools/enguq_crown_overlap_r1.py`, selftest PASS 14 checks. Output
`C:\EdgeLog\_anatomy_cache\enguq_crown_overlap_r1\overlap.json`. Pre-lockbox only, 2010-06-07 ..
2025-06-30 — the same cut r2 used, so **no lockbox was read**.

## 0. The number this check refuses to produce, and why

The owner's shape is **ES 5m**; the crown is **NQ 1m**. Prereg section 6 pre-committed that **a
single ES-versus-NQ overlap percentage would be a fabricated number** and that this round would not
produce one. It does not. Two separate measurements are reported, with the words attached:

- **A — same instrument, same timeframe.** The crown's own NQ entries against each r2 entry arm, both
  computed on NQ resampled to 5m **from the very master the crown ran on**. No translation.
- **B — cross instrument, time only.** How often an ES 5m pullback-break signal lands in the same
  5-minute slot as a crown entry. This is **co-occurrence in time, not agreement**: ES and NQ are
  ~0.9 correlated, so a large number here means the index moved.

**Every overlap carries a base rate and a lift**, because an arm that fires on 20% of all bars will
"cover" about 20% of anybody's entries by chance. **A lift near 1.00 is coincidence however large the
coverage looks**, and three of these arms fire on roughly a fifth of all RTH bars.

## 1. The crown, pinned from the run and not from the file

`ENGUQ_1M_ETH_R2_1_0.py`, run **#335**, basis `db_noadj_eth` (the run's own), cost 0.533, multiplier
20. Champion read from the stored run doc, because **the file's defaults and the run's champion are
different numbers** (house rule FILE DEFAULTS != RUN):

```
act_R 2.5  atr_len 28  breakeven_R 1.0  buf_atr 0.4  ema_len 1340  er_len 100  er_th 0.0
limit_atr 0.1  min_brk 1.4  regime_len 5  stop_mult 1.2  tl_len 238  trail_frac 4.0  vol_mult 0.0
```

**1,237 crown entries** on the pre-lockbox stretch, in 1,237 distinct 5-minute slots, of which
**514 fall in RTH** — and RTH is the only window any r2 arm fires in, because the crown trades 24
hours and the owner's shape is a cash-session trade. The 514 is the denominator for section A; the
crown's out-of-hours entries are reported and then excluded rather than counted as misses.

**Why 1,237 and not the run's stored 870.** The run doc's `best_trades` is 870 and that is the same
figure as `validate.is_trades` — **it is the IN-SAMPLE tuning count, not the whole window's**. 870 of
1,237 is 70%, which is the shape of this house's 75/25 split. There is no parity break here, but the
check was worth doing: a crown entry count that silently disagreed with the stored run would have
invalidated every number below.

## 2. A — same instrument, same timeframe. The answer is no.

| arm family | arm | fires | base % of RTH bars | covers % of the crown's 514 | lift |
|---|---|---|---|---|---|
| strict drift run | best of the 36 `D1'` arms | 897–9,107 | 0.06–3.27 | **0.00–0.58** | **≤ 1.21** |
| slope drift, no body test | `D2' w=20 d=0.5 B0` | 55,324 | 19.85 | 39.30 | **1.98** |
| slope drift + body ≥ 2x | `D2' w=20 d=0.5 b2` | 8,302 | 2.98 | **13.62** | **4.57** |
| slope drift + body ≥ 2x | `D2' w=10 d=0.5 b2` (r2's grid leader) | 7,671 | 2.75 | 6.23 | 2.26 |

- **The strict drift arms are simply not the crown's trade.** All 36 `D1'` cells sit at a lift of
  1.21 or below and cover at most **3 of the crown's 514 RTH entries**. Whatever the crown is
  triggering on, a run of six-to-eight non-rising closes is not it.
- **The `D2' B0` arms look impressive and are not.** `D2' w=20 d=0.5 B0` covers 39.3% of the crown's
  RTH entries — but it fires on **19.85% of every RTH bar on the tape**, so its lift is 1.98. A
  condition that is true on a fifth of all bars is close to no condition at all.
- **The one real association is the body test, and it is modest.** The three `D2' w=20 b2` arms carry
  lifts of **4.15 to 4.57**, the highest anywhere. That is a genuine signal: a big-bodied break after
  a measured slope decline does find the crown's entries about four and a half times more often than
  chance.
- **But it is not a rediscovery, and the direction matters.** At the very best arm, **86.4% of the
  crown's RTH entries are NOT this shape**, and **99.2% of that arm's 8,302 signals are NOT crown
  entries**. The owner's shape and the crown's trigger are two different trades that agree
  occasionally, not one trade found twice.
- **The body test is where the agreement lives, which is consistent with r2.** Every positive-net
  cell in r2 was a `b2` cell, and here the `b2` cells are the only ones with a lift worth the word.
  Two independent reads now say the big body is the part of the owner's observation that is real.

**Power, stated rather than buried.** 514 slots is a small denominator: coverage moves in steps of
0.19 percentage points, so the lifts are noisy and should be read as "about 4 to 5", never as 4.57.
The qualitative split — strict arms unrelated, loose arms coincidental, body arms modestly
associated — is robust to that noise; the exact figures are not.

## 3. B — cross instrument, time only. CO-OCCURRENCE, NOT AGREEMENT.

| arm | ES signals | same 5-minute slot as a crown entry | of the ES signals | of the crown's 514 RTH slots |
|---|---|---|---|---|
| `D2' w=20 d=0.5 B0` | 51,929 | 175 | 0.34% | 34.05% |
| `D2' w=20 d=1.0 B0` | 44,265 | 144 | 0.33% | 28.02% |
| `D2' w=15 d=0.5 B0` | 50,969 | 119 | 0.23% | 23.15% |
| the 36 `D1'` arms | 641–25,270 | 0–25 | ≤ 0.11% | ≤ 4.86% |

- **This table is a statement about the index, not about the strategies.** ES and NQ move together,
  so an ES condition that is true on a fifth of all bars will land in the same five minutes as a
  third of anybody's NQ entries. The right reading of the 34% is "the two index futures were doing
  the same thing", and it would be dishonest to present it as the strategies agreeing.
- **It is reported anyway, and labelled**, because prereg section 6 promised both numbers and because
  the small side of it is informative: even in pure time co-occurrence the strict `D1'` arms barely
  touch the crown.
- **Note the denominator.** The harness printed "of #335 %" against all 1,237 crown slots, including
  the out-of-hours entries no RTH arm can ever match; the table above re-states it against the 514
  RTH slots, which is the comparable figure. Both are in the JSON.

## 4. CORRECTION I OWE ON r2 — X4 was NOT the crown's own exit

**Found while pinning the champion for this check, and reported before it could be read anywhere as
settled.** The r2 harness pins its X4 exit with a comment claiming it is "the crown's own exit,
`ENGUQ_1M_ETH_R2_1_0.py` DEFAULT_PARAMS defaults". **That comment is false, and the four values match
neither source:**

| | stop_mult | act_R | trail_frac | breakeven_R |
|---|---|---|---|---|
| **what r2 actually ran as X4** | 1.0 | 2.5 | 2.5 | **1.5** |
| the file's DEFAULT_PARAMS defaults | 1.0 | **1.5** | 2.5 | **2.0** |
| **run #335's champion** | **1.2** | 2.5 | **4.0** | **1.0** |

Two of the four are the file's defaults, one is the run's, and `breakeven_R = 1.5` is from neither —
`act_R` and `breakeven_R` appear to have been transposed against the file and then never checked
against the run at all. This is the FILE DEFAULTS != RUN rule, broken by me in the direction of
inventing a fourth exit.

- **WITHDRAWN:** the claim that X4 is "THE CROWN'S OWN multi-day exit", wherever it appears — ledger
  2.218, the r2 results doc, and my report to MANAGER.
- **What X4 actually is:** an **X4-style multi-day trailing exit** — stop at 1.0x the entry-to-swing-
  low, trail 2.5R below the running high once 2.5R is reached, stop to entry at 1.5R, held across
  days. A legitimate exit, soundly measured; simply not the crown's.
- **NOT affected — the r2 verdict.** 0 of 106 rows reached 7 of 8 folds at any cost rung. That is a
  fold-count close and no exit parameter moves it.
- **NOT affected — "a multi-day hold beats flat-at-close".** Both arms were measured against each
  other on the same bars: X4 beat X1 on every statistic (gross R +0.0095 vs −0.0280, net R −0.2329 vs
  −0.4277, folds won 2.17 vs 0.66). It remains the fifth confirmation that shortening this family's
  hold taxes the edge, and the reason MANAGER's scan r1 should read "no cell clears cost **under a
  flat-at-close exit**".
- **NOT affected — the body-test finding**, which is an entry result and was measured under both exits
  (and is independently supported by section 2 above).
- **Not re-running 106 cells over it.** The exit that genuinely needs testing is the crown's real one,
  which is the queued "hold until opposite signal" item, and it will be run with #335's champion read
  from the run doc. Re-running r2 under a corrected X4 would answer a question nobody asked and could
  not move a 0-of-106 fold count.

## 5. No run records from this round, deliberately

This check measures **where signals fire**, not what they earn: there is no daily dollar series and no
four numbers, so under the W47 standing rule **nothing here is written as a run record**. Numbers not
measured with a daily series are not written. The r2 cells those records cover are already on the
chart — 209 of them, at the 0.533 and 0.25 rungs.
