# ENGU-Q HOLD CAP r2 — PRE-REGISTRATION: the cap knob opened on a full Auto-Validate

**Written before the job is queued and before any cell of it exists.** Owner order 2026-10-14,
relayed as MANAGER #79: *"keep testing … autovalidate on EL the top 3 results from the last few
weeks that you find promising. let me know their past runs."* This lane's cell is **ENGU-Q #335
with the hold-cap knob opened (off / 2h / 4h / 1 session / 1 week) on top of its normal ranges.**

## My objection, stated once and then set aside

**I advised against a cap sweep** after hold cap r1 (MANAGER #946, 2026-10-12): the cap's effect is
monotone and already mapped from 15 minutes to a week, and the one cell that beat the crown on ROC
failed the house bar on Sortino and on the one-episode test. MANAGER's #79 acknowledges this and
the owner wants the top candidates validated anyway. **That is the owner's call and this round runs
in full.** What r1 could not do and this round can: r1 held every other knob at the crown's values,
so it only ever asked "what does a cap do to THIS cell". A full search asks the different and
fairer question — **whether a differently-tuned cell plus a cap beats the crown** — and it puts a
lockbox under the answer. That is a real question and r1 did not answer it.

## What r1 found, so this round is judged against something

Walk-forward 2016-10-01..2025-06-30, roll-corrected overnight master, cost 0.783, drawdown valued
daily, all other knobs at the crown's values:

| cell | ROC@30k | DD5 | DD% peak | Sortino | win | w/l |
|---|---|---|---|---|---|---|
| crown, no cap | 26.5 | $30,408 | 14.80% | 3.66 | 30.0% | 3.62 |
| cap 1 hour | 12.1 | $15,225 | 27.79% | 1.17 | 47.2% | 1.22 |
| **cap 4 hours** | **29.8** | $20,185 | 19.01% | **2.20** | 41.7% | 1.65 |
| cap 1 session | 25.2 | $31,820 | 14.51% | 3.06 | 33.2% | 2.65 |
| cap 1 week | 20.6 | $31,485 | 17.02% | 2.97 | 30.6% | 3.17 |

The 4-hour cap's worst drawdown is $28,296 against its DD5 of $20,185 — a ratio of 1.40, so **it is
flagged driven by one episode**, as is the crown itself at 1.60.

## The instrument

`augur_strategies/ENGUQ_1M_ETH_HC_1_0.py`, already on main and already parity-gated: with the cap
OFF it reproduces the crown trade for trade, 2,053 against 2,053. Its other thirteen knobs keep the
parent's own fences, and **every one of run #335's champion settings is reachable on them** —
checked, including `tl_len` 238 = 50 + 4×47, `ema_len` 1340 = 100 + 40×31, `atr_len` 28 = 20 + 4×2,
`stop_mult` 1.2 and `regime_len` 5.

### The one change: the cap's fence is re-cut from 0..20000 step 5 to **0..6900 step 60**

r1 needed 5-bar resolution to reach its 15-minute cell. This round does not: the owner's smallest
named cell is 2 hours, and r1 already measured 15, 30 and 60 minutes and found them dead or
marginal. The old fence offers **4,001 lattice points for one knob**, which inside a 900-trial
search over fourteen knobs is resolution nobody asked for, bought with trials the other knobs need.

The new fence is **116 points at one-hour resolution, capped at the owner's largest named cell**,
and it holds all five of them exactly:

| cell | bars | on 0..6900 step 60 |
|---|---|---|
| off | 0 | 0 |
| 2 hours | 120 | 60 × 2 |
| 4 hours | 240 | 60 × 4 |
| 1 session | 1380 | 60 × 23 |
| 1 week | 6900 | 60 × 115 |

**This is a re-cut, not a pinning** — the knob still searches 116 values and 0 = off is in the
space. **The queue driver asserts all five cells land on the declared lattice and refuses to queue
if any does not**, which is this lane's third encounter with an unreachable cell and the reason the
check sits in the path that actually runs rather than in a document.

That assertion lives in the driver rather than in `tests/` on purpose: touching `tests/` puts the
ship on the hook's 45-minute engine tier, and on 2026-10-12 that cost this lane three duplicate
test slots. The gate is not weaker for sitting in the driver — it blocks the queue, not a push.

## The basis, and a judgement call I am flagging rather than burying

MANAGER #79 says to pin the window and master **to the crown's run**. Run #335's stored basis is
`db_noadj_eth`, cost 0.533, 2010-06-07..2026-06-30. **I am pinning the window to that and the
master to `db_adj_eth` at cost 0.783 instead**, for two reasons:

1. **`db_adj_eth` is the registered roll-corrected master.** #335 predates the roll audit; the
   house has moved to the corrected tape and three of BOOK #463's four legs are already restated
   on it.
2. **The numbers that motivated this round were read on it.** "The 4h cap read 29.8 vs crown 26.5"
   is r1's figure on `db_adj_eth` at 0.783. Pinning to the older basis would produce a result that
   cannot be compared with the figure the owner is asking about.

If MANAGER wants the literal #335 basis instead, say so and I re-queue; it is one line in the
driver. **Window pinned 2010-06-07..2026-06-30, master `db_adj_eth`, cost 0.783, multiplier 20,
900 trials (owner rule, never lowered), 12-month lockbox, 8 folds, warm 300 days.**

## The bar — what counts as a pass

The yardstick is unchanged: **ROC %/yr at a $30,000 drawdown valued daily, WF and LB apart, with
DD5 beside it.** A pass needs ALL of:

1. **Walk-forward ROC@30k beats the crown's own 26.5 on the same basis**, re-read on the
   validate's exact walk-forward out-of-sample dates rather than on r1's window.
2. **Sortino at least matches the crown's 3.66.** This is the clause r1's best cell failed, at
   2.20, and it is why a cap that wins on ROC alone is not a candidate.
3. **Not driven by one episode** — worst drawdown no more than 1.3 × DD5. r1's 4-hour cell was
   1.40 and the crown is 1.60, so if this clause is read strictly it disqualifies the incumbent
   too; the honest form is that the winner's ratio must not be **worse** than the crown's 1.60,
   and the ratio is reported either way.
4. **At least 100 walk-forward and 50 lockbox trades**, with the lockbox profitable without its
   single biggest trade.
5. **The engine's own verdict is not WEAK.** ENGU-Q RTH r1 (#489) came back WEAK on 14.8 trades
   per parameter; this file has fourteen knobs on a tape with roughly 2,000 trades, which is a far
   better ratio, but the gate is named in advance either way.
6. **The winning cell is the walk-forward chain, never the full-window champion.** #489 produced a
   39.6 on the champion read backwards over the walk-forward dates against a chain figure of 10.1.
   That gap is what this clause exists to prevent.

**Any failure = dead, written to the ledger and the lane doc. No variants, no second sweep.**

## The honest prior, written before the run

**I expect this to fail clause 2, and I expect the search to find a cap near 4 hours.** r1's shape
says the cap trades Sortino for ROC: every cell that raised the win rate cut the win/loss ratio,
and this family's money is in multi-day survivors — 490 trades held 24 hours or more made $1.03M
while 1,563 shorter ones lost $539k. A cap converts survivors into non-survivors by construction.

**What could make a full search genuinely different from r1, and I would be wrong to dismiss it:**
a cell tuned *with* the cap can widen its trail, lengthen its trendline or loosen its stop to let
the remaining holds run, which r1 forbade by construction. If the search finds that, the Sortino
clause is where it will show, and I would rather be shown wrong by a real search than keep
asserting r1's shape.

**What will not change:** the cap cannot create survivors, only preserve or destroy them, and the
lockbox is a fresh year that r1 never touched.

## How this could fool us

- **900 trials on one instrument is a selection machine** and the cap knob adds a fourteenth
  dimension. PBO goes in the report whatever it says.
- **r1's 4-hour result is in my head and in this document.** That is why clause 1 is pinned to the
  crown's 26.5 rather than to "beats r1", and why the walk-forward chain decides.
- **DD5 and DD% from peak disagreed in r1** — DD5 improved while DD% from peak worsened. Both are
  reported for both stretches and neither is quoted alone.
- **The chain's own DD5 may be unavailable.** On #489 the validate stored the walk-forward chain as
  cumulative points with no trade dates, so no daily curve could be rebuilt and DD5 / DD% from peak
  read '-'. STRATEGY-BEATING (#78) called that a gap worth its own to-do for whoever owns the run
  report. If it recurs here it is reported as '-' again, never substituted with a trade-level
  figure.

## Process

Witness branch `prereg/enguq-holdcap-r2` with LF sha256s posted to MANAGER before the job is
queued, this document and the re-cut fence on main first, then the Auto-Validate, then the job id.
Nothing live or paper changes. Crown #335 stays frozen and stays the incumbent.
