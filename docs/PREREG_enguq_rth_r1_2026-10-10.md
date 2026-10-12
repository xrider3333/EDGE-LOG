# ENGU-Q RTH r1 - PRE-REGISTRATION DRAFT: a market-hours ENGU-Q fit for the Webull QQQ book

**DRAFT to MANAGER, written before any number exists** (owner decision 10-09 ~20:20 MST, relayed as
MANAGER #64: "DIP + search a market-hours ENGU-Q"). Not a port of #335 - a NEW fit on a
regular-hours tape. ENGU-Q #335 itself stays live on NinjaTrader and becomes a no-order tracker on
Webull; nothing here goes near the paper book without the owner.

## Map placement, and the thing this has to beat

`docs/MDL_MAP_R1.md` prices a new leg at about $15,000 a year at a $30,000 drawdown of its own if it
is uncorrelated with BOOK #463 in the weeks #463 falls. **But that is not the relevant bar here**,
because a reference already exists and already works:

**FRONTIER's Q36 measured NQ #335's own signals filled on QQQ prints under the Webull executor, and
it keeps 98% of the leg's dollars a year at the same notional - ROC @ $30k 28.42 against the leg's
26.09, and 114.08 as a seat on the S1 line against 121.06.** So the honest bar is not "does a
market-hours ENGU-Q make money"; it is:

> **Does a fresh regular-hours fit beat simply executing NQ's signals on QQQ?**

If it does not, the owner's choice is between an NQ-signal leg that keeps 98% and a QQQ-native leg
that keeps less - and the only reason to prefer the second is operational, not financial. That
reason is real and worth stating: an NQ-signal leg makes a QQQ-only Webull account depend on a
live NQ feed and on this PC's signal path, which is a coupling the box does not have today.

## (a) The signal tape - QQQ's own prints, and why

**PRIMARY: signals AND fills on the QQQ 1-minute regular-hours master** (FRONTIER's Alpaca SIP pull,
`master_dd092f50.csv`, sha256 `bdca2595...`, 2016-01-04..2026-06-30, 1,023,757 rows).

Why that and not NQ signals with QQQ fills:

1. **The owner asked for a market-hours ENGU-Q for the QQQ book.** A fit must be fitted on the tape
   it will trade, or it is the same category of thing that already failed: #335's settings run
   unchanged on the QQQ tape made **308 walk-forward trades against the leg's 1,194** (Q36 row A),
   because thresholds calibrated to NQ's point scale and a 1,380-bar session select far fewer QQQ
   bars. Re-fitting is precisely the remedy, and it has to happen on QQQ's own prints.
2. **It removes the NQ-feed coupling** described above, which is the operational reason the owner's
   question arose at all.
3. **Q36's NQ-signal result is kept as the REFERENCE ROW, not discarded** - it is the benchmark in
   the bar below. Both are reported side by side so the owner sees the real choice.

Costs and fills, pinned now: **$0.01 a share a side** (Q36's convention), one NQ contract's notional
in QQQ shares (about 820-822), **fills 09:31-15:59 ET only, overnight hold allowed**, a signal
outside those minutes fills at the next 09:30 open (the Q34/Q36 executor rule).

## (b) The ranged file - lookbacks sized for a 390-bar session, ranges FULL

A new research file `ENGUQ_RTH_1_0.py`, the crown's mechanism with every lookback re-ranged for a
390-bar session rather than a 1,380-bar one. **The 900-trial budget is the owner's rule and is not
lowered; the ranges are NOT pinned** (MANAGER #64), so the search decides, not me.

Proposed ranges, each stated with its session meaning so the fence is auditable:

| knob | range | step | reaches |
|---|---|---|---|
| `ema_len` | 20 .. 1560 | 20 | 0.05 to 4 sessions |
| `tl_len` | 10 .. 780 | 10 | the swing-low lookback, up to 2 sessions |
| `atr_len` | 10 .. 390 | 10 | up to one full session |
| `er_len` | 10 .. 390 | 10 | up to one full session |
| `regime_len` | 1 .. 20 | 1 | days, unchanged in meaning |
| `limit_atr` | 0.0 .. 1.5 | 0.05 | unitless, the crown's 0.55 inside it |
| `buf_atr` | 0.0 .. 1.0 | 0.05 | unitless |
| `min_brk` | 0.5 .. 3.0 | 0.1 | unitless |
| `trail_frac` | 1.0 .. 4.0 | 0.25 | unitless, the crown's 2.5 inside it |
| `stop_mult` | 0.5 .. 2.0 | 0.25 | unitless |
| `act_R` | 0.5 .. 3.0 | 0.25 | unitless |
| `breakeven_R` | 0.0 .. 4.0 | 0.5 | 0 = off |
| `vol_mult` | 0.0 .. 2.0 | 0.1 | 0 = off |

**Harness gate, and it is here because this lane has already shipped this defect once:** a test
asserts every value above lands on the declared lattice (`min + step*k`), and asserts that with the
ranged file set to the crown's own settings it reproduces the crown's trade list on the NQ ETH
master trade for trade. A search space that cannot express the cell it is compared against is a
void round - that is what nearly happened to round 62.

## (c) How it is judged

One pinned Auto-Validate on the house runner: **900 trials, `date_from` / `date_to` PINNED to
2016-01-04..2026-06-30** (the pinned-validate rule; the ranges stay open), the house walk-forward /
lockbox split with the 12-month lockbox, **ROC @ $30k with DD5 beside it and the one-episode flag**
(rule 10-07), Sortino, and the house minimums of 100 walk-forward / 50 lockbox trades.

**A pass needs ALL of:**

1. **ROC @ $30k beats the Q36 reference (28.42) by more than the round's own power line**, computed
   and posted BEFORE any cell P&L. Not "beats 28.42" - beats it detectably.
2. **Sortino at least matches the reference**, and DD5 does not reveal a one-episode win (worst
   drawdown over 1.3 x DD5 = the ROC is driven by one episode and the row is reported as such, not
   passed).
3. **At least 100 walk-forward and 50 lockbox trades**, and the lockbox profitable without its
   single biggest trade.
4. **The validate's own verdict is not WEAK.** This matters more than usual - see the prior.
5. **The Webull executor read (Q34 / Q36 method) on the winning cell**, reported before any
   adoption conversation: what share of the dollars survives 09:31-15:59 fills with the overnight
   hold, and the seat read on the S1 line.
6. **A plain-exposure twin**, since this family is a long trend hold: the winning cell against a
   buy-and-hold QQQ position at the same average exposure, in-position and always-on, which is the
   comparison CALMTAPE r1 failed and the one FRONTIER's Q31 had to add after review.

**Any failure = dead, written to the ledger and the lane doc, no variants, no second search.** One
search, one budget.

## (d) The honest prior, and it is NOT encouraging

Stated before any number, with the ledger rows rather than from memory:

- **Both QQQ Auto-Validates this house has ever run came back WEAK.** Row 2.96: ORB's run **#486
  WEAK, PBO 0.976**, folds 6 of 8, and its winner differed from the live crown on 11 of 13 settings.
  Row 2.97: NOISE's run **#485 WEAK, PBO 0.687 the only fail**, folds 8 of 8, plateau 9 of 9, and
  its winner was the live core with one lookback changed. **Two for two.** A third QQQ Auto-Validate
  should be expected to come back weak, and clause 4 above takes that seriously rather than treating
  PBO as a footnote.
- **Re-searching a crown has not paid in this house before**: ORB's meta-walk-forward returned
  $166k against the defaults' $377k, which is why crowns are frozen.
- **QQQ degrades this house's NQ edges unevenly** - NOISE keeps 0.94 of its NQ edge, ORB only 0.78,
  and ORB's QQQ ROC fell to 23.4 from 35.8. There is no measurement of what ENGU-Q's mechanism keeps
  under a fresh fit, which is the gap this round fills.
- **What could make a fresh fit genuinely different from the 308-trade port:** the crown's
  thresholds are ATR multiples and break sizes calibrated on NQ's point scale over a 23-hour
  session. On QQQ's 390-bar session at roughly a fortieth of the point value, the same multiples
  select far fewer bars. A re-fit can recover the trade count, and trade count is this family's
  binding constraint (the lockbox minimum of 50 is what #335 only barely clears).
- **And what probably will not change:** this family's money is in multi-day survivors, and Q34
  already showed the overnight-hold executor keeps 100% of the exit timing's dollars while the entry
  timing's contribution is not resolvable. If the survivors are the edge and the executor already
  preserves them, a fresh entry fit has little left to win - which is the same wall seven
  pre-registered ENGU-Q entry filters hit.

**So my prior is that this search does not produce something distinguishably better than Q36's
reference, and I am saying so in advance rather than after.** The round is still worth running,
because the owner has asked, because the operational case for a QQQ-native leg is real, and because
a clean falsification closes the question instead of leaving it open.

## How this could fool us

- **900 trials on one instrument is a selection machine.** The two WEAK verdicts above are what that
  looks like. Clause 4 is the guard and the PBO number goes in the report whatever it says.
- **Overlapping sessions**: QQQ and NQ are the same underlying, so the new fit will correlate with
  #463's existing ENGU-Q leg. If it is adopted alongside, that is concentration, not
  diversification - the seat read must be incremental, never standalone.
- **The lockbox is one year and this family's lockbox is one trade.** A lockbox pass here means very
  little on its own; clause 3's without-the-biggest-trade test is the real check.
- **Cost at a cent a share is an assumption.** NOISE's QQQ work found the 6% gap was mostly cost at
  2 cents and a breakeven of $0.17 a share; a cost curve at 0.5, 1 and 2 cents is reported, not one
  number.

## What I need from MANAGER before anything runs

1. **GO or edits on the tape choice in (a)** - this is the one decision that changes the whole round.
2. **Confirmation that the Q36 reference (28.42) is the right thing to beat**, rather than the map's
   $15k-a-year row. I believe it is, because the owner's real question is which leg to put on the
   QQQ book, not whether a new leg exists.
3. Whether clause 6's buy-and-hold twin should use QQQ or the NQ proxy.

On GO this goes out as a witness branch `prereg/enguq-rth-r1` with the note and harness sha256s
posted before the run, per the run-before-main rule.

## Addendum 1 (2026-10-10, MANAGER #65 - GO, before any number exists)

MANAGER answered all three questions and this records the rulings; the draft above is otherwise
unchanged, and nothing in it is edited.

1. **TAPE: the QQQ 1-minute regular-hours master for signals AND fills.** Agreed as proposed.
2. **BAR: Q36's 28.42 is the right thing to beat** - a fresh fit must beat simply executing NQ
   #335's signals on QQQ, with **the power line posted BEFORE any cell P&L**. If it cannot beat it
   detectably, this lane says so plainly and MANAGER puts the operational choice (a QQQ-native leg
   versus the NQ-feed dependency) to the owner. The map's $15k-a-year row is NOT the bar here.
3. **EXPOSURE TWIN: QQQ**, the tape the leg trades, not the NQ proxy.

MANAGER also confirmed the running arrangements: witness branch and hashes first, then the
900-trial Auto-Validate on the house runner with the trial cache on and five workers available, and
**the #326 tree/tier re-read comes AFTER this search lands** (that re-read has since been done and
reported separately - it added 0.7 ROC points, not the 13.7 the stored block implied).

**Nothing else moves.** The ranges stay unpinned, the window stays pinned, the six pass clauses
stand as written, and the stated prior - that this search probably does not beat 28.42 detectably,
given two WEAK QQQ Auto-Validates and seven dead ENGU-Q entry filters - stands as written rather
than being softened now that the round is authorised.

## Addendum 2 (2026-10-10, STRATEGY-BEATING's review folded IN FULL, before any data)

MANAGER #68 asked for these as "addendum 1"; addendum 1 above already recorded the GO, so this is
**addendum 2** and nothing above is edited. Every edit from the review (#67, full text at
`C:\EdgeLog\manager\reviews\enguq_rth_r1_review_STRATEGY-BEATING_2026-10-10.md`) is folded, and
**each blocking finding was verified against the strategy file before folding rather than taken on
trust**. All three were correct; the verification notes are recorded here because two of them are
more precise than the review states.

### L1 - the lattices could not reach the crown, so the reproduction gate failed by construction

**Confirmed.** `tl_len` 10..780 step 10 cannot reach the crown's **206**; `atr_len` 10..390 step 10
cannot reach **52**. This is the round-62 defect in a new place: the draft asserted a reachability
test and then specified a fence that fails it. Replaced with the review's anchored lattices:

| knob | was | **now** | reaches the crown |
|---|---|---|---|
| `tl_len` | 10..780 step 10 | **10..782 step 4** | 206 = 10 + 4x49 |
| `atr_len` | 10..390 step 10 | **12..392 step 4** | 52 = 12 + 4x10 |

### L2 - the efficiency-gate threshold was missing from the table

**Confirmed.** The file carries `er_th` (default 0.0, 0.0..0.5 step 0.05) and the gate is written
`if float(er_th) > 0`, so **at the crown's 0.0 the gate is off and `er_len` does nothing at all**.
Added: **`er_th` 0.00..0.50 step 0.05**. `er_len` stays in the table and is only meaningful when
`er_th` is above zero, which is now searchable rather than silently dead.

### L3 - two hard-coded NQ price floors, and they are the mechanical reason for 308 trades

**Confirmed, and located exactly:** an **ATR floor of 0.25** in the break test
(`(c[i] - tl_now) / max(a, 0.25) < min_brk`) and a **risk floor of 0.50** in both entry paths
(`if risk < max(0.25, 0.5)`, twice). Both are absolute NQ POINTS. On QQQ, where a share trades in
cents, a 0.50-point risk floor and a 0.25 ATR floor reject nearly every candidate bar - which is the
mechanism behind Q36's **308 walk-forward trades against the leg's 1,194**, and the single most
important thing the search must be able to move. Added as searchable knobs, both reaching the NQ
values and QQQ-scale values:

| knob | range | step | note |
|---|---|---|---|
| `risk_floor` | 0.00 .. 0.50 | 0.01 | 0.50 = today's hard-coded NQ value; 0.00 = off |
| `atr_floor` | 0.00 .. 0.25 | 0.01 | 0.25 = today's hard-coded NQ value; 0.00 = off |

### P1 - the power line, by Q36's own method, and what it implies

The line is computed by **Q36's method from the reference series alone** - no cell of the new search
touches it - and is **posted with the witness branch before any cell P&L**. Q36's published line is
**12.70 ROC points**. **So clause 1 requires a walk-forward ROC of about 41 to beat the reference's
28.42 detectably.** That is stated here, in advance, with its consequence: 41 is far above the
crown's own 26.5 and above the ungated #326 cell's 21.5, so **on this bar the round is very likely
to fail, and the prior in the draft is strengthened rather than softened by the review.** If the
search lands between 28.42 and 41 the honest report is "better on the point estimate, not
distinguishable", and MANAGER puts the operational choice to the owner.

### C2 and C3 - clauses 5 and 6 get real bars instead of being reports

- **Clause 5, the executor read, now has a bar:** the winning cell's ROC under the Webull executor
  must also beat the reference by the power line, and its seat on the S1 line must be **at least
  114.08** (Q36's reference seat). A report with no threshold cannot fail, and a clause that cannot
  fail is not a clause.
- **Clause 6, the QQQ buy-and-hold twin, now has a bar:** the winning cell must beat the
  same-exposure QQQ twin by **more than the twin null's 95th percentile** - the CALMTAPE pattern,
  where a calm-uptrend long lost to its own same-exposure hold. Both the in-position and always-on
  twins are reported; the in-position one carries the bar.

### Everything else from the review, folded as stated

- **The reference is re-read on the validate's exact walk-forward out-of-sample dates**, not on
  Q36's window, so the comparison is date-for-date.
- **The walk-forward stretch decides; the lockbox is veto-only** and is not treated as blind here.
- **"The winning cell" means the walk-forward chain's cell, never the full-window champion.**
- **A walk-forward concentration check** is added: the result must survive without its top three
  trades, and be positive in at least 6 of 9 walk-forward years.
- **`regime_len` counts 390-bar blocks** - verified in the file (`rb = int(regime_len) * 390`), so
  on an RTH tape one block is one session while on NQ's overnight tape the crown's 10 is about 2.8
  sessions. Its existing fence (0..100 step 5) already reaches 10 and already includes **0 = off**,
  so no change is needed, but the **unit shift is recorded** because it changes what the knob means.
- **The lattice test compares floats with a tolerance**, not for equality.
- **Parity is checked two ways before any search:** a code diff against `ENGUQ_1M_ETH_R2_1_0.py`
  showing only the intended additions, and a trade-for-trade match against the **SAVED #335 trade
  list** on `db_noadj_eth`, 2010-06-07..2026-06-30.
- **One trial is timed before 900 are queued** - the file is uncompiled and `tl_len` now reaches
  782, so the per-trial cost must be measured, not assumed.
- **The budget stays at 900** (owner rule, never lowered).

**Process, as MANAGER set it:** witness branch and hashes to STRATEGY-BEATING and MANAGER, then
**STRATEGY-BEATING confirms the folds**, and only then does anything run.

## Addendum 3 (2026-10-10, STRATEGY-BEATING's four pins, before any data)

STRATEGY-BEATING confirmed the addendum-2 folds and its own hash of this note (#69), and set four
one-line pins; MANAGER's #70 is GO with no further review once they are in. All four are below, plus
the recomputed power line the pins require. Nothing above is edited.

### Pin 1 - ONE fence for the regime filter

The draft's section (b) said `regime_len` 1..20 step 1 while addendum 2 cited the file's existing
0..100 step 5 - **two fences for one knob, which the reviewer caught in my document**. Pinned to a
single range: **`regime_len` 0..20 step 1**. It holds **0 = off** and the crown's 10, at session
resolution on a 390-bar tape.

### Pin 2 - the concentration check, in the reviewer's exact words

The draft's wording was looser than the review. Replaced with both halves, each a real threshold:

1. **The walk-forward ROC with its top three trades removed is still above the reference's 28.42**,
   the reference re-read on the same dates.
2. **The cell is ahead of the reference in at least two-thirds of the validate's walk-forward
   calendar years** - the count comes from the validate's own fold schedule, not an assumed nine
   years. "Positive in 6 of 9 years" is dropped, because the reference clears that too and a bar the
   reference also clears tests nothing.

### Pin 3 - the power line, recomputed on the validate's own dates

**Recomputed with the house tool by Q36's method** - paired stationary block bootstrap on the two
daily series, mean block 20 sessions, 1,000 draws, seed 20261005, ROC at $30k with the drawdown
valued daily:

| | value |
|---|---|
| SD of the bootstrapped lead | 7.7197 |
| **5% line (50% power)** | **12.6989** |
| 80% line (four times in five) | 19.1989 |
| days / years | 2,626 / 8.994 |

**It equals Q36's 12.70, and for a reason rather than by coincidence: the reference's own daily
series spans only 2016-07-01..2025-06-29, so clipping it to the validate's window removes nothing.
The reference series, not the window, is the binding constraint.** If the job's fold schedule trims
the out-of-sample span materially the line is re-posted; a trim can only shorten it.

**So clause 1 needs a walk-forward ROC of at least 41.1 to beat 28.42 at 50% power, or 47.6 to clear
it four times in five** - against the crown's own 26.5 and the ungated #326 cell's 21.5.

**And the limit of any line posted before a search exists, stated rather than discovered later:**
this is the spread of **leg versus reference**, the only two series that exist today. The real bar is
**candidate versus reference**, whose spread needs the candidate's daily series. So the pre-posted
number is a **proxy** resting on the candidate's daily volatility resembling the leg's. The true
paired line is recomputed on the winning cell and **both are reported** - the pass judged on the
true line, this proxy standing as the record that the bar was not moved after the result was seen.
If they differ materially that is said loudly.

### Pin 4 - zero guards for the newly exposed floors

Exposing the two hard-coded floors as knobs introduces two numerical holes at 0.00, both guarded in
the harness:

- **`atr_floor` 0** would let the break test divide by a zero ATR on a flat bar, and infinity passes
  any `min_brk`. Guard: **`max(a, atr_floor, 1e-9)`**.
- **`risk_floor` 0** would admit zero-risk entries - the stop sits at the entry and R is undefined.
  Guard: **skip any trade with `risk <= 0`**.

Both leave NQ parity at the crown's 0.50 / 0.25 untouched, and **the timed trial asserts no infinity
or not-a-number anywhere in its output**.

### Order of operations from here

Witness branch moved to this commit, addendum hash posted to STRATEGY-BEATING and MANAGER, then the
ranged file and harness built and hashed, then the 900-trial Auto-Validate queued and its job id
sent. **Nothing runs before the hash is out.** Budget stays 900.

## Addendum 4 (2026-10-12, the built harness and what its gates caught - still before any P&L)

The ranged file and the harness now exist and every gate passes. Three things below were NOT known
when addenda 2 and 3 were written, and one of them is a defect in my own fences that the review did
not catch either. Nothing above is edited.

Files: `augur_strategies/ENGUQ_RTH_1_0.py` (built by patching the crown, not retyped) and
`tests/test_enguq_rth_lattice.py`.

### 4.1 - A THIRD lattice break, in `stop_mult`, and why both earlier checks missed it

The lattice gate failed on first run: **`stop_mult` = 1.2 is not reachable on 0.50..2.00 step
0.25.** Fixed to **step 0.1**, which is also the file's own native step, and the gate now passes.

**Why this matters more than the fix.** STRATEGY-BEATING's L1 found exactly this class of defect in
`tl_len` and `atr_len`, I folded it, and I then asserted a reachability test - and the space was
*still* unable to express the crown. The reason is a distinction neither the draft nor the review
drew:

> **The crown FILE's defaults and RUN #335's champion settings are different numbers.**

`ENGUQ_1M_ETH_R2_1_0.py` carries `tl_len` 206, `atr_len` 52, `ema_len` 220, `stop_mult` 1.0. Run
#335's stored champion is `tl_len` 238, `atr_len` 28, `ema_len` 1340, **`stop_mult` 1.2**. Both the
draft and the review checked the FILE, where 1.0 sits on a 0.25 lattice; the RUN, which is what the
house means by "the crown", does not. **Checking the file's defaults is not checking the run.** The
test now pins BOTH cells by name and would fail if either became unreachable.

### 4.2 - Parity, two ways, both run

**A. Code equivalence - PASS, trade for trade.** The new file at run #335's champion settings with
both floors at their NQ values reproduces the crown file's trade list exactly on `db_noadj_eth`
2010-06-07..2026-06-30: **1,387 trades against 1,387, every entry bar, exit bar and P&L identical.**
This is also a free re-proof that the compiled and interpreted walks agree at these settings, since
the crown dispatches to the compiler here and the new file cannot.

**B. Against the saved #335 export - 98.36%, and the residual is explained rather than waved at.**
The stored export (`C:\EdgeLog\book_legs\ENGUQ335_raw_trades.csv`, 1,344 trades) shares **1,322
entry bars** with this run's 1,387. The 22 misses and 65 extras are scattered across ten years, not
at the window edges, and cluster in the most recent years (17 extras in 2024, 20 in 2026).
**The cause is the tape, not the code:** the export was written **2026-09-27**, and the
`db_noadj_eth` master was last rewritten **2026-10-12 12:28** and now runs to 2026-10-12. Feeds
restate recent bars, which is exactly where the residual sits. Gate A - both files on today's tape -
is the gate that tests this patch, and it is exact.

### 4.3 - The floors DO move the walk, and by much less than the prereg implied

A knob a search can move that moves nothing is the defect this round exists to fix, so the harness
asserts the new floors bite. They do - but the measured size changes the story:

| tape | floors | trades |
|---|---|---|
| NQ overnight, #335 settings | NQ values (0.50 / 0.25) | 1,387 |
| NQ overnight, #335 settings | both 0 | 1,389 |
| **QQQ regular hours, crown lookbacks** | **NQ values (Q36's published row)** | **308** |
| **QQQ regular hours, crown lookbacks** | **both 0** | **398** |

**On NQ the floors are nearly inert** - two trades in 1,387 - which is precisely why they survived
as hard-coded constants for so long without anyone noticing. **On QQQ they bite, but they recover
only about a third of the gap:** 308 to 398, not 308 to the leg's 1,194.

**This corrects a claim in addendum 2.** That note called the two floors "the single most important
thing the search must be able to move", and the review named them as the mechanism behind
308-against-1,194. **Measured, they explain roughly 90 of the 886 missing trades.** The larger part
of the gap has to be the tape itself: the regular-hours master holds **1,023,757 bars against the
overnight master's 5,503,474** - a fifth as many bars to find signals in. No re-fit can conjure
that back. **So the prior gets weaker again, not stronger:** the lever we identified as the main one
is real but small, and the dominant constraint is one the search cannot touch.

These are **trade COUNTS at cells fixed in advance** - the crown's own settings and the fence
corners. **No P&L on the QQQ tape has been computed or looked at.**

### 4.4 - The timed trial (addendum 2's requirement)

On the QQQ 1-minute regular-hours master (`master_dd092f50.csv`, id 144, 1,023,757 rows,
2016-01-04..2026-06-30), uncompiled, single-threaded:

- **worst corner** (`tl_len` 782, `ema_len` 1560, `atr_len` 392, floors 0): **7.5 s**, 126 trades.
- **mid space** (the crown's own lookbacks, floors 0): **7.4 s**, 398 trades.
- **Pin 4 holds:** no infinity and no not-a-number in either output with both floors at 0.00.
- 900 single trials is about **1.9 hours** single-threaded, **0.6 hours** at three workers. The
  validate multiplies this by its fold schedule, so the queued job is hours, not minutes - but it is
  affordable and the budget stays **900**.

**One operational note found while timing:** `find_master("QQQ", "1m", "rth")` returned the QQQ
**daily** total-return master, a 2,637-bar tape that would have run silently and produced a
meaningless search. The harness selects FRONTIER's pull by filename instead, and the master's name,
rows, window, source and session are printed before anything runs.

### 4.5 - What runs next

Witness branch and these hashes to STRATEGY-BEATING and MANAGER, then the Auto-Validate: **900
trials, window pinned 2016-01-04..2026-06-30, master `master_dd092f50.csv`, full ranges**. The six
pass clauses, the 41.1 bar and the veto-only lockbox are unchanged.
