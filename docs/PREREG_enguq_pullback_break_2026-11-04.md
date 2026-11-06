# PREREG - ENGU-Q "PULLBACK BREAK" SCAN r1 (owner ask 11-04, MANAGER #273) - lane ENGU-Q

Owner 11-04 ~14:00 MST, via MANAGER #273: deep dive on a shape he traded twice today on ES 5m (14:00
and 15:05 ET). Spec `C:\EdgeLog\manager\scopes\ENGUQ_PULLBACK_BREAK_SPEC_2026-11-04.md`.
**DRAFT - no run until MANAGER GO.** Pre-lockbox only, lockbox veto-only, four numbers, folds counted.

## 0. My read of how this maps onto the crown - A COUSIN, NOT A SUBSET

Asked for one word: **cousin.** The entry trigger is a near-twin of the crown's; the TRADE is a
different animal, and the difference sits exactly where this family's money has been measured to be.

**Where it is a twin.** A run of 10-20 consecutively lower 5-minute closes IS a descending structure,
and a descending trendline fitted through the highs of such a run is close to collinear with the
closes. The crown (`ENGUQ_1M_ETH_R2_1_0.py`, #335) fires when a close clears that fitted line by
`buf_atr` plus `min_brk` x ATR with an EMA trend filter; the owner's shape fires when the first
higher close arrives with a body big against the drift candles, with price above a 200ma and the day
green. **Those are two spellings of "a descending leg broke upward with conviction, in an uptrend."**
I expect the entry sets to overlap substantially once both are read on one tape, and ask 3 below
measures that rather than assuming it.

**Where it is NOT a subset, and why I expect the spec as written to fail.** The crown holds for days
to weeks - up to 143 days - and three independent rounds have found that **the family's money is in
those survivors** (`enguq-money-is-in-the-survivors`). The owner's sketch is a 0-3 bar trade with a
fixed 1R target off the breakout body. This house has now measured four times, independently, that
shortening this family's hold taxes the edge:

| round | what it shortened | result |
|---|---|---|
| shelf No. 39 holding-rule grid | candlestick exit rules | 0 of 15 beat the leg's own exit; the hindsight ceiling IS the leg |
| hold cap r2 | a maximum hold in bars | dead over 116 cap values |
| executor r1 T08 | regular hours, held through close | **112% of its net came from the holds through the close** |
| **Webull arm C, today** | flat at 15:59 every day | ROC 26.09 -> 6.17, DD% from peak 12.75 -> 41.34 |

So my pre-registered expectation is: **the owner's ENTRY is real and probably already half-known to
the crown; his EXIT is the part I expect to cost money.** That is a testable split and the arms below
are built to separate them, because if it is right the useful answer to the owner is not "your shape
does not work" but "your shape is a good entry and the crown's own exit pays you more for it."

**Two honest cautions, written before any number.**

1. **The evidence so far is two trades, both from today, both AFTER the lockbox cut.** That is not a
   criticism of the owner's read - a trader seeing a shape twice in an afternoon is exactly how a
   hypothesis should start - but it means today's two fills can never be part of the test. They are
   the hypothesis, not the data.
2. **"10-20 lower closes" is the single biggest ambiguity and I will not resolve it by picking the
   version that scores better.** Ten CONSECUTIVE lower 5-minute closes is a rare event; "a gentle
   downward drift of 10-20 bars, mostly lower" is common. Those are different strategies with
   different trade counts. Both are pre-declared as separate arms below, read side by side, and the
   count of each is reported in G0 before anything is scored.

## 1. Start from scratch, or build on what we have? MY CALL: SCRATCH SCAN, HOUSE RAILS

The spec doc's own note is right - this is a new family seed, not a knob move - so there is **no
strategy file and no plugin in r1.** It is a scan: find the bars, measure what happened after them.
But it runs on the house rails, not new ones: `augur_engine.drawdowns.four_numbers` for the four
numbers, #335's own fold dates, the house cost ladder, the power-first gate, `tools/run_record.py`
for the records. **Scan, then a strategy file, then a belief** - in that order, per
`edgelog-scan-then-strategy-file`. A plugin only gets written if G0 and the arm grid clear.

## 2. Data, cost and windows, pinned

- **Tape**: `ADJ_ES_5m_ETH.csv` from `augur_uploads/`, pinned by filename AND row count, printed and
  recorded. ES 5m ETH is the owner's own timeframe and instrument; r1 does not translate it.
- **Cost**: **0.533 ES points a round trip x $50 = $26.65** as the headline, with a ladder at
  **0.25 / 0.533 / 0.75 / 1.25 points** reported for every arm. Note in advance: on a 5m ES breakout
  body of roughly 5-15 points (1R = $250-750), the headline cost is 4-10% of 1R, so **this shape will
  not die of cost** - it will live or die on hit rate, and the ladder is reported so that is visible
  rather than assumed.
- **Window**: pre-lockbox only, **entries strictly before 2025-06-30**, split as the house does -
  pre-WF for the draft read, then #335's own 8 folds for the graded read. **Lockbox 2025-07-01
  onwards is VETO-ONLY**: not loaded while anything is selected, read once at the end, and it can
  only kill.
- The ETH session cut applies (`eth_session_18et`): the window ends at 18:00 ET of `date_to`, not
  midnight, so the read cannot take the first lockbox evening. This is the trap that cost 24 ENGU-Q
  runs their parity and it is named here, not discovered.
- **No 200ma is computed across a session gap without saying so**: the 5m 200ma is a 200-bar mean on
  the ETH bar series (about 16.7 hours, so it spans the overnight) and the daily 200ma is a 200
  trade-day mean. Both are reported; neither is silently preferred.

## 3. The arms, all pre-declared

The grid is deliberately small, because every cell is a selection opportunity. **5 entry arms x 4
exit arms = 20 cells, and the multiple-reads correction in clause 2 of section 5 is set for 20.**

### Entry arms - how the drift is defined

| arm | drift definition | body test |
|---|---|---|
| **E1** | **N consecutive lower closes**, N in {5, 8, 12} | breakout body > 1.5x the median body of the drift run |
| **E2** | **a 15-bar window with >= 70% lower closes** and a net lower close, the "gentle drift" reading | same |
| **E3** | E1 with the body test raised: body > 2.5x the drift median | - |
| **E4** | E1 with **no body test at all** - the control | - |
| **E5** | E1 **plus the crown's own EMA trend filter** instead of the 200ma | - |

**E4 is the arm that decides whether the body test earns its place.** If E1 does not beat E4, the
"relatively big body" the owner saw is decoration and the drift count is doing the work. That is
stated now so it cannot be dropped later.

### Context filter, applied to every entry arm and also removed

Day green (close above yesterday's settle) AND above the 200ma. **Reported BOTH with and without the
context filter**, because the owner names it as the thesis - "market is up, buyers in control" - and
a thesis that is load-bearing must be shown to be load-bearing. If the shape scores the same without
it, the context is not the edge and the owner should hear that plainly.

### Exit arms - the part I expect to matter most

| arm | exit |
|---|---|
| **X1** | **1R = the breakout body**, target 1R, stop at the breakout candle's low, as the owner sketched |
| **X2** | same stop, targets **1.5R and 2R** |
| **X3** | stop at the breakout low **minus 0.25 x ATR20** buffer, target 1R - does the bare low get wicked out? |
| **X4** | **the crown's own exit** - swing-low stop, trail from `act_R`, breakeven move, multi-day hold |

Every exit arm also carries a **time stop at 3, 6 and 12 bars** reported separately, since the owner's
two examples reached 1R in 0-3 bars and the question of whether that is the shape or those two trades
is exactly what a scan answers.

**X4 is the arm my prior says wins**, and it is in the grid for that reason: it is the one cell that
tests "good entry, wrong exit" instead of only testing the owner's exit.

## 4. G0 - the power-first gate, which can end this round at draft

Run first, before any arm is scored, and reported whatever it says:

1. **Count per entry arm per N**, pre-lockbox, trades a year. **Floor 50 a year.** An arm under the
   floor is greyed and not scored - no exceptions, and no merging of cells to reach the floor.
2. **Gross against cost per arm**, not pre-WF ROC (MANAGER's rule): mean gross points a trade must
   exceed 2x the 0.533 headline, or the arm is greyed. Screening on ROC rewards any cut that happens
   to shorten the drawdown and is how the ORB paper scout produced 13 dead candidates.
3. **The 80% power line** at a two-sided 5% level for each comparison the arms imply, by the house
   formula (n per group = 15.7 sd²/δ², one-sample 7.85). **Any comparison 2x or more short of its
   line is reported as an UNPOWERED OBSERVATION and nothing else** - it does not become a candidate,
   it does not reach a strategy file, and it is not quoted as a number anywhere.
4. **If every cell is greyed, the round closes at draft**, which costs an hour instead of a runner
   night. Yesterday's w93 G0 closed both directions this way and that was the cheapest result of the
   week.

## 5. The bar for calling this a candidate

Four numbers from `augur_engine.drawdowns.four_numbers` on the DAILY mark-to-market series (every
session, zero days included) - ROC@$30k, DD5, DD% from peak, daily Sortino - per cell, per fold, plus
`one_episode`.

A cell becomes a CANDIDATE for a strategy file only if all of:

1. it clears G0's count and gross/cost screens;
2. it wins **>= 7 of the 8 folds** against the no-trade baseline (p 0.035 - this is a DISCOVERY read
   on a new seed, not a three-way ranking between known arms, so the bar is the 7-of-8 discovery bar,
   not the 6-of-8 ranking bar used for the Webull arms today, and the difference is stated here
   before the data so it cannot be said later that the bar moved);
3. it is **not one episode** (worst DD <= 1.3 x DD5);
4. it survives the cost ladder to 0.75 points with positive net;
5. its edge is **not concentrated in one fold** - no single fold may hold more than 40% of the net
   (arm A today held 35% of its net in fold 5 and that is the single most disqualifying fact about
   it);
6. the lockbox does not veto it.

**If no cell clears, the answer to the owner is "the shape you saw is real to look at but does not
pay on nine years of tape", and that is a result.** A clean nothing-found is the expected outcome
here: this would be the first new ENGU-Q family seed to survive since #335, and the seed hunt
(rounds 32-42) is already on the dead list.

## 6. Ask 3 - the overlap with #335's signals, and the one thing I will not fake

The owner's shape is **ES 5m**; #335 is **NQ 1m**. **A single overlap percentage across those two
tapes would be a fabricated number** and this prereg will not produce one. What is honest is two
separate measurements, reported as two:

- **Overlap, same instrument, same timeframe:** take #335's own NQ signals, resample NQ to 5m, and
  count what fraction of its entry bars satisfy each entry arm's conditions. This answers "does the
  crown already take this shape?" on one tape with no translation.
- **Coincidence, cross-instrument, time only:** count how often an ES 5m pullback-break bar falls in
  the same 5-minute slot as a #335 NQ signal. Reported as a CO-OCCURRENCE IN TIME and labelled as
  such, since ES and NQ are 0.9-correlated and a high number here means the index moved, not that the
  strategies agree.

Both numbers go in the results doc with those words attached. If the same-instrument overlap is high,
the useful finding is that the owner has independently rediscovered his own crown's trigger - which
would be a good sign about the read and a bad sign about the round's novelty, and the owner should
hear it that way round.

## 7. Method pins

- Harness `tools/enguq_pullback_break_r1.py`, frozen with this document, checks this prereg's LF
  sha256 at start and exits on mismatch, prints its own, and carries a `selftest` on hand-made bars
  with no data covering: the consecutive-lower-close counter, the >= 70% window variant, the body
  ratio, the day-green test across a session boundary, both 200ma definitions, the 1R-off-body
  arithmetic, and the bar on which an entry is DROPPED rather than booked.
- **Entries are tagged at the SIGNAL bar and filled at the next bar's open**, never at the signal
  bar's close. Intrabar order between the 1R target and the stop is resolved **pessimistically** -
  if a bar's range contains both, the STOP is taken. A scan that lets the target win ties is how
  look-ahead enters this house quietly.
- The 200ma, ATR20 and yesterday's settle are computed on bars **strictly before** the signal bar.
- Masters pinned by FILENAME AND ROW COUNT, printed and recorded.
- One run-record JSONL line per cell per stage in `C:\EdgeLog\run_records\enguq_202611.jsonl`
  through `tools/run_record.py`, handed the daily series.
- RUN-BEFORE-MAIN on GO: frozen commit pushed as `prereg/enguq-pullback-break-r1`, sha posted to
  MANAGER before the harness is launched.
- **MANAGER is running its own first-pass scan on the same tape in parallel.** Good: that is a second
  pair of eyes, not a race. Where our counts disagree, the disagreement is reported and reconciled
  **before** either set of numbers is quoted to the owner - two scans that differ on the trade count
  mean one of us has the drift definition wrong, and that is worth more than either headline.
- Nothing in this round touches live, paper, the box, or any account.

## 8. Prior, written before the data

- **E1/E2 will produce plenty of signals on E2's loose definition and probably too few on E1 at
  N=12.** I expect the consecutive-close variant to be count-starved at the high N and the ">= 70% of
  15 bars" variant to be the only one above 50 a year.
- **I expect the body test (E1 vs E4) to add little.** "A relatively big body" after a drift is
  largely a restatement of "volatility expanded", which is already in the ATR normalisation.
- **I expect the day-green + 200ma context to help, and to be the most likely part to survive**,
  because it is a trend filter and this family's EMA trend filter has held across every round.
- **I expect X1 (fixed 1R off the body) to lose to X4 (the crown's exit)** by a wide margin, for the
  four measured reasons tabulated in section 0. If that is what the grid shows, the recommendation to
  the owner will be: **keep your entry read, hand the exit to the crown.**
- **Most likely overall outcome: no cell clears clause 2, and the round closes with a nothing-found
  plus one useful sentence about the exit.** I am saying so now so that a nothing-found cannot be
  dressed up later as a surprise, and so that if a cell DOES clear 7 of 8 folds it is read against a
  prior that expected it not to.

---

## 9. CHALLENGE TO MANAGER'S SCAN r1, AND THE r2 DEFINITION (MANAGER #279, 11-04 14:21)

MANAGER's scan `C:\EdgeLog\manager\scopes\ENGUQ_PULLBACK_BREAK_SCAN_R1_2026-11-04.md` (399 cells)
asked to be challenged, not accepted. This section is that challenge. **It is written before r2 runs
and it does not re-run r1**: everything below either re-reads r1's own printed numbers or names a
cell r1 did not evaluate. Sections 0-8 above are unchanged except where this section says so.

### 9.1 What I accept outright, and one of my own arms it kills

- **E1 at N >= 10 is DEAD and r1 killed it.** 33 RTH signals in 15 years at N >= 10, 10 at N >= 12.
  My section 3 pre-declared E1 at N in {5, 8, 12}; **N=12 is struck, and N=8 is on notice** (r1 reports
  n < 100 for strict runs at N >= 8). That is r1 doing exactly what a G0 is for, and it saves my own
  round a wasted cell. No argument.
- **The 0.5-point tolerance finding is the most valuable line in the scan**, and it is worth more than
  the headline. The owner's 14:00 ET bar does not fire the strict rule because **13:55 closed +0.25
  UP**. So the strict lower-close count never described the trade he took - not in his words, and not
  in either of our r1 definitions. **288 of r1's signal-sweep cells and all three of my E1 variants
  were measuring a different shape.** The honest status of the owner's hypothesis after 399 cells is
  therefore NOT "tested and dead" but **"not yet tested"**, and that distinction is the whole reason
  r2 exists.
- **Multiplicity cuts in r1's favour and I grant it.** With 399 looks and nothing above 4 of 8 folds,
  the search was broad enough that a decent edge would have surfaced somewhere. I accept the strong
  reading of r1's conclusion - **conditional on the exit**, which is 9.2.

### 9.2 THE STRUCTURAL HOLE: all 399 cells share arm C's exit, so r1 cannot say "no gross edge"

**Every cell in r1 goes flat at the session close.** The base cell is "flat at the 15:55 bar close";
the 96-cell exit sweep varies target and stop inside that; the ETH variant "uses the same 15:55 flat
rule"; and r1's own caveat says **"no overnight-specific exits tested."** There is no multi-day hold
anywhere in 399 cells.

**That is arm C.** And arm C was measured TODAY, on this family's own crown, on the same lane's four
numbers:

| | ROC@$30k | DD% from peak |
|---|---|---|
| ENGU-Q #335, its own exit | 26.09 | - |
| the same strategy forced flat at the close (arm C) | **6.17** | 41.34 |

**A flat-at-close exit removed 76% of the ROC from a strategy we know has an edge.** So apply the
arithmetic to r1's own null band. If the pullback-break entry carried a true edge of, say, +$30 gross
a trade under a hold-it exit, then under a flat-at-close exit you would expect to see roughly
**+$7 a trade** - and r1's reported band for every strict-run cell with n >= 200 is
**"between -$1 and +$10 per trade (= 0 to 0.2 pts)", which r1 calls "inside spread noise."**

**r1's noise band is the same size as the residual its own exit would leave of a real edge.** That is
not a quibble about a knob; it means the scan cannot distinguish "this entry has no edge" from "this
exit destroys the edge this entry has", because it never ran a cell that could tell them apart.

**So r1's conclusion should be restated, and I propose this wording for the owner:** *no cell clears
$26.65 round trip UNDER A FLAT-AT-CLOSE EXIT.* That is a true, useful and narrower claim than "no
gross edge". Four independent prior rounds (shelf No. 39's 0 of 15, hold cap r2's 116 dead cap
values, executor r1's 112%-from-the-overnight-holds, and arm C today) say the exit is the most likely
place for this family's money to go missing, which is precisely why my section 3 put **X4, the crown's
own exit, in the grid.** **X4 remains the single most important cell in r2 and r1 contains no
equivalent of it.**

### 9.3 THE CONTEXT CONCLUSION IS MEASURED AT FIXED CONTRACT, AND THE HOUSE SIZES ON RISK

r1 concludes "DAYGREEN + MA200 context does NOT add". Two objections, both from r1's own table.

**(a) The $ column is a sizing artefact, and r1 says so itself.** r1's reason for the filtered cells
being worse in dollars is printed in the scan: *"green/above-MA days have bigger bodies, so the fixed-R
trade loses more $ per stop."* But R is DEFINED as the body, so a bigger body is a bigger risk per
trade, and the $ figure at a fixed contract count is then dominated by position size rather than by
edge. **This house sizes on risk, not on contracts.** Under constant-$-per-R sizing - which is how any
of this would actually be traded - the R column is the edge and the $ column is noise about volatility.
r1 even flags the symptom without drawing the conclusion: *"$ and R rankings disagree in places (context
cells have positive avg R and negative $)."*

**(b) In R terms the context adds in three of the four pairs r1 printed, sign-consistent:**

| signal def | avg R unfiltered | avg R with DAYGREEN+MA200 | direction |
|---|---|---|---|
| N6 strict r1.5 RTH (base) | -0.044 | **+0.037** | sign flips POSITIVE |
| N8 L1 r1.5 RTH | +0.154 | **+0.222** | up |
| N6 strict r1.0 ETH | -0.013 | **+0.009** | sign flips POSITIVE |
| N4 L1 r1.0 RTH (biggest n) | -0.026 | -0.031 | flat/down |

None of these is significant (t +0.59, +0.40, +0.29). **That makes the context UNPOWERED, not
REFUTED** - and this lane has a memory on exactly that distinction
(`edgelog-review-refute-can-kill-true-finding`). The statistic r1 leads with, P(1R hit before stop
within 3 bars), is additionally the wrong test: with a target fixed at 1R, a hit-rate comparison is
insensitive to the shape of the R distribution, which is the thing that pays. A z of -0.7 on a hit
rate is not evidence against a thesis about the R distribution.

**r2 therefore reports every cell BOTH at fixed contract AND risk-normalised (constant $ per R), as
two columns, pre-declared now.** This costs no new simulation - it is a re-weighting of the
per-signal table r1 already has - and it is the one change that could flip the sign of the context
conclusion. **I am not predicting that it will.** I am saying the question is open and r1's design
could not close it.

### 9.4 Two smaller challenges

- **The 1R-in-0-3-bars table does not test the owner's claim.** He did not claim a high hit rate; he
  observed that in HIS two examples price reached 1R within three bars. r1 measures ~40% reach 1R
  against 33-45% stopped first in that window and reads it as a coin flip - which it is, **for a
  three-bar scalp.** The value of the trade is in what the remainder does, and a three-bar window
  cannot see it by construction.
- **The lockbox is now partly spent on this shape and that cost should be on the record.** r1 prints
  LB reads per cell, including *"the dgma cells are mildly positive in LB (+0.02..+0.17 R, n 15-308)."*
  Nothing was selected on it, so this is not a look-ahead leak and I am not calling it one - but the
  numbers are now known to both lanes, so **r2 cannot treat the lockbox as a clean veto on the
  day-green/MA context cells specifically.** For those cells the veto is weakened to "already seen";
  for every other cell it stands. Said plainly so it cannot be quietly reused later as if unseen.

### 9.5 The r2 definition - MANAGER's three, plus the two my challenge implies

MANAGER's brief: drift-with-tolerance, body >= 2x, crown overlap. **Accepted, all three**, and they
replace E1/E2/E3 above. Two additions, from 9.2 and 9.3, because without them r2 repeats r1's design:

| r2 arm | definition |
|---|---|
| **D1 drift with tolerance** | run = bars where `close <= prior close + k ticks`, **k in {1, 2, 4, 8} ticks (0.25-2.00 pts), PRE-DECLARED, not chosen to make today's bar fire**; N >= 6 |
| **D2 regression slope** | OLS slope over the trailing 10, 15 and 20 bars below a threshold - a definition with no "count" in it at all, as a cross-check that D1's answer is about drift and not about counting |
| **B1 body** | breakout body >= 2.0x the mean body of the N prior bars, r1's one knob that moved dollars; **B0, no body test, stays as the control** |
| **X4 the crown's exit** | swing-low stop, trail from `act_R`, breakeven move, **multi-day hold** - the cell r1 has none of, and per 9.2 the most important one in the round |
| **ACCOUNTING** | every cell reported at fixed contract AND risk-normalised, per 9.3 |

**The tolerance must not be fitted to today's bar.** k = 2 ticks makes the 14:00 bar fire with a
6-bar run and k = 8 makes it a 14-bar run; choosing k on that basis would be fitting a definition to
**one bar, which is post-lockbox and is also one of the two trades that are the hypothesis rather
than the data.** The grid is declared above and all four k values are reported whatever they say.

**Priors for r2, written now.** I expect D1 to behave like r1's N6-L1 cells - flat after cost - on the
flat-at-close exits, because that is what r1 measured and a tolerance mostly enlarges the same
population. **The open question is X4, and my prior is that X4 beats every flat-at-close cell in r2
by a wide margin while STILL not clearing the 7-of-8 fold bar**, because the crown's exit is doing the
work and the pullback-break entry is then just a worse way of finding the crown's own trades - which
is what the overlap measurement in section 6 is for. **If that is how it lands, the answer to the
owner is: your eye is reading a real pattern, your entry is close to your own crown's trigger, and the
1R-off-the-body exit is the part that costs you.** That is a useful answer and it is reachable from a
nothing-found.

### 9.6 Overlap

Section 6 stands unchanged and is still mine: same-instrument overlap (#335's NQ signals, NQ
resampled to 5m, against each r2 entry arm) reported separately from cross-instrument co-occurrence
in time, with the words attached, and no single ES-versus-NQ overlap percentage produced. Not run -
there is no GO yet, and my section 7 pins RUN-BEFORE-MAIN.
