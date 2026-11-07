# RESULTS - ENGU-Q PULLBACK BREAK r2, ES 5m (owner ask 11-04, MANAGER #273/#279/#141)

Run 2026-11-06. Prereg `docs/PREREG_enguq_pullback_break_2026-11-04.md`, frozen LF sha256
`2786c829ff1a4f840217640b3aa5683634cb4b1bd00a97c2ddcf15c5efbc5ba6` (section 9 is my challenge to
MANAGER's scan r1; addendum 2 records my own broken drift definition), pushed as
`prereg/enguq-pullback-break-r2` before the run. Harness `tools/enguq_pullback_break_r2.py`,
selftest PASS 21 checks, checks the prereg sha at start. Logs `C:\EdgeLog\enguq_pb_*.log`, records
`C:\EdgeLog\_anatomy_cache\enguq_pullback_break_r2\{g0,stage1}.json`.

Master pinned: `ADJ_ES_5m_ETH.csv` 1,154,741 rows, 2010-06-06 .. 2026-11-06; **pre-lockbox
1,058,658 bars, 2010-06-06 .. 2025-06-30, 15.07 years**, ETH session cut 18:00 ET of `date_to`.
Lockbox 2025-07-01 onwards **NEVER OPENED**.

**The answer in one line: the round CLOSES. No cell reaches the pre-registered 7-of-8 fold bar at
ANY cost rung, including a commission-only one - the best on a 106-row grid is 5 of 8, and that cell
holds 92% of its net in a single fold.**

**But two findings survive, and one of them vindicates the challenge in section 9.**

## 1. The headline: the fold bar, at every cost

| cost, ES pts RT | cells with positive net $ | cells reaching >= 7 of 8 folds |
|---|---|---|
| **0.08** (BELOW ANY REAL COST - see 4a) | 27 of 106 | **0** |
| **0.10** (BELOW ANY REAL COST - see 4a) | 25 of 106 | **0** |
| **0.25** (still below the real figure) | 14 of 106 | **0** |
| *0.45 - the REAL house commission+exchange RT, NOT MEASURED* | *between 1 and 14, by the rungs either side* | *0* |
| **0.533 (house, headline)** | 1 of 106 | **0** |
| *0.95 - the real figure WITH slippage, NOT MEASURED* | *at most 1* | *0* |

**This closes the round without needing the cost argument at all** - and that is just as well,
because my cost estimate turned out to be the wrong way round (4a). At no rung on this ladder,
real or unreal, does a single cell reach the fold bar. The
best fold count anywhere is 5 of 8, which is not suggestive - the house bar for a discovery read is
7 of 8 (p 0.035) and 6 of 8 is already only suggestive.

**And the leader fails the concentration clause outright.** `D2' w=10 d=0.5 b2 X4` looks the best
thing on the grid at commission-only - net $144,181, ROC@30k 5.89, DD5 $28,047, DD% 36.21, Sortino
1.118 - and **92.3% of that net sits in ONE of the eight folds** (clause 5 caps it at 40%). It is
also flagged `one_episode`. That is the single most disqualifying fact in this round and it is the
same shape that disqualified Webull arm A two days ago at 35%.

## 2. FINDING THAT SURVIVES #1 - the exit was eating the result, as section 9 argued

| exit | mean gross R | mean net R @ 0.533 | mean folds won |
|---|---|---|---|
| **X4 - an X4-style multi-day trailing exit** (swing-low stop, trail from `act_R`, breakeven, MULTI-DAY HOLD) | **+0.0095** | **-0.2329** | **2.17 / 8** |
| X1 - the owner's sketch (1R off the body, stop at the breakout low, flat at the close) | -0.0280 | -0.4277 | 0.66 / 8 |

> **CORRECTION, 2026-11-06, found while pinning #335 for the crown-overlap check: X4 IS NOT THE
> CROWN'S OWN EXIT, and every description of it as such is WITHDRAWN.** The harness pins stop_mult
> 1.0, act_R 2.5, trail_frac 2.5, breakeven_R 1.5. The file's defaults are 1.0 / 1.5 / 2.5 / 2.0 and
> run #335's champion is 1.2 / 2.5 / 4.0 / 1.0 - so two of the four are the file's, one is the run's,
> and breakeven_R 1.5 is from neither. That is the FILE DEFAULTS != RUN rule, broken by me. What X4
> actually is: an X4-STYLE multi-day trailing exit, soundly measured, simply not the crown's.
> **The verdict is untouched** - a 0-of-106 fold count moves for no exit parameter - and so is
> **"a multi-day hold beats flat-at-close"**, because both arms were measured against each other on
> the same bars. Full treatment in section 4 of
> `docs/RESULTS_enguq_crown_overlap_r1_2026-11-06.md`.

**X4 beats X1 on every statistic, across all 53 cells.** Gross R flips sign; net R halves its loss;
the fold count more than triples. **This is the comparison MANAGER's scan r1 could not make, because
all 399 of its cells go flat at the session close** (its own caveat: "no overnight-specific exits
tested").

So section 9.2's objection was substantively right, and the restatement it proposed is the correct
reading of r1: *no cell clears cost UNDER A FLAT-AT-CLOSE EXIT.* The flat-at-close exit was not
merely failing to find an edge, it was removing one - consistent with arm C stripping 76% of the ROC
off this family's own crown (26.09 -> 6.17) in the Webull round, and with the four prior rounds that
found shortening this family's hold taxes the edge. **This is now the fifth.**

**It does not rescue the shape.** X4 is better and still loses at the house cost, and still never
reaches 7 of 8 folds.

## 3. FINDING THAT SURVIVES #2 - the owner's body test is real, small, and never enough

Gross R by whether the body test is applied, on the X4 exit:

- **B0, no body test: gross R negative in essentially every cell** (around -0.07 at G0, -0.02 to
  -0.06 on X4).
- **b2, body >= 2.0x the mean body of the prior N bars: gross R positive in most cells**, up to
  **+0.1005** (`D1' k=1t N>=8 d=1.0 b2 X4`).
- **Every single positive-net cell on the grid is X4 AND b2.** 14 of 106 rows at the 0.25 rung, and
  all 14 carry both.

**The owner's "relatively big body" is doing real work, and my own prior said it would not.** Section
9.5 predicted the body test would "add little" on the grounds it restates volatility expansion. That
prediction is wrong and the record should say so. The body filter helps twice over: it raises gross R
*and* it widens the stop (mean risk 2.0 -> 5.3 points), which cuts cost as a fraction of R from 0.45
to 0.19.

It is still not enough to clear a fold bar at any cost.

## 4. The number my own prereg got worst: cost against R

My prereg wrote "this shape will NOT die of cost: on a 5-15 pt breakout body the headline is 4-10% of
1R." **Measured mean risk is 1.5-5.3 ES points, so the 0.533 house round trip is 11-36% of 1R - three
to four times what I assumed.** On a 5-minute tape the trade is simply too small to carry a futures
round trip comfortably.

### 4a. CORRECTION, after MANAGER #144: my commission-only rungs were below any real cost

**I was wrong about ES cost in the direction that flattered this round, and the correction is
recorded here rather than left in a chat.** My prereg and section 1 carried 0.08 and 0.10 ES points
as an estimated commission-only round trip, labelled as my estimate. MANAGER #144 settled it: there
is no owner-specific ES figure, and the **house ES round trip is $5.66 both sides at the same broker
as NQ = 0.45 ES points** at $12.50 a point, or **0.95 points with the $5 slippage a side**. So:

- **My 0.08 and 0.10 rungs are not commission-only, they are below any cost that exists.** Every
  figure quoted against them - including the 27-of-106 positive count - describes a tape nobody
  trades, and is relabelled accordingly above.
- **The real commission-only rung, 0.45, was never measured.** I will not interpolate a count onto
  it. What the measured rungs either side do say, because positive-cell count falls monotonically in
  cost, is that 0.45 sits **between 1 and 14 of 106** - and the fold column is **0 on both sides of
  it**, which is the column the verdict rests on.
- **The claim I previously made that a better cost assumption multiplies the positive count 27x is
  WITHDRAWN.** It was true only of rungs below reality. The honest version is narrower: moving from
  the house headline 0.533 to the real commission-only 0.45 cannot move the count past 14, and moves
  the fold verdict not at all.
- **The verdict is unchanged, and for the stronger reason.** It never rested on cost; cost is now
  worse than I assumed, not better.

**ROC@30k and DD% are NOT interpretable on the losing cells here** and are not quoted as if they
were: `four_numbers` correctly returns `roc30 = None` when a stretch does not make money, and the
-1.99 ROC floor and the DD% figures of 188% to 793% on X1 cells are artefacts of a negative net, not
drawdowns anyone should read.

## 5. What was wrong with my own work, on the record

Three defects, all mine, all found and fixed before any number was reported as a result. They are
listed because the measurements they voided were quoted to MANAGER in flight:

1. **The drift definition was broken** (addendum 2). `close <= prior close + k ticks` is "not
   meaningfully HIGHER", not "drifting DOWN": **56.6% of all ES 5m bars pass at k=0 and 93.0% at
   k=8**, so a six-bar run was near-certain and the condition selected nothing. MANAGER's #279 said
   *net* drift; I implemented the tolerance and omitted the net decline, which is the half that does
   the work. Fixed with a net fall >= `d` x ATR20, d in {0.5, 1.0, 1.5}; k=8 struck as
   uninterpretable.
2. **The first screen was on gross POINTS**, which compares position sizes rather than edges whenever
   R varies - *the exact objection section 9.3 raises against MANAGER's scan r1*. Repeating it would
   have been indefensible. Now screened on net R with cost expressed in R per trade. This fix is what
   exposed defect 3.
3. **A fill bug made gross R exactly -1.0000 in all 54 cells.** The caller passed the SIGNAL bar as
   the entry bar with that bar's own low as the stop, so `low[entry_bar] <= stop` was true by
   construction and every trade booked a full stop-out. Prereg section 7 pins a next-bar-OPEN fill
   and the harness never implemented its own pin. **A constant repeated across 54 heterogeneous cells
   is a bug signature, never a result.** The selftest now guards it in both directions.

**Withdrawn:** my in-flight claim that gross was "uniformly negative, -1.3 to -2.6 points, so the
entry definition is load-bearing". That was defect 3; the points column was mean risk with a minus
sign, which is why `gross pt` equalled `risk pt` in every row.

## 6. Owner standing order 11-06 (#142): what I did and did not do

- **Cost rows.** #142 gives a commission-only figure for **NQ** (0.283 pt). This is an **ES** tape and
  **I did not transplant it or invent an ES equivalent.** The ladder now carries 0.08 and 0.10 ES
  points, **explicitly labelled as MY ESTIMATE** of an ES commission-only round trip ($4-5 RT at $50
  a point), with the real figure requested from MANAGER. The house 0.533 remains the headline.
- **The limit-fill rule is NOT implemented.** #142 says to count a limit fill only when price trades
  THROUGH the level by one tick. Every fill here is a next-bar-OPEN market fill. Given that cost is
  11-36% of R on this shape, a limit arm is the single change most likely to matter, so it is
  pre-declared as its own arm rather than bolted on mid-run.
- Catalogue `tested_catalogue.json` and this week's scopes are checked before any idea is carried
  forward from these failures.

## 7. Verdict and what it means for the owner

**The pullback-break shape as drawn does not pay on 15 years of ES 5m, at any cost rung, under either
exit.** The round closes on the fold bar, not on cost, so a better cost assumption does not reopen it.

**What to tell the owner, in his own terms:** his eye is picking up two real things - **the big
breakout body matters** (it flips gross R positive and my prior said it would not) and **holding the
trade matters far more than the 1R target he sketched** (the crown's exit beats his on every
statistic). What does not survive is the trade as a standalone 5-minute scalp: at 1.5-5.3 points of
risk it cannot carry a futures round trip, and nothing on a 106-row grid is steady across the eight
folds.

**This is the thirteenth-plus round on the trendline/pullback entry family and the fifth independent
confirmation that shortening this family's hold costs money.** Nothing here is queued, no strategy
file is written, and the lockbox is untouched.

## 8. Run records - every reported cell is now on the COMPARE chart (MANAGER #145)

The owner could not see this round on the COMPARE scatter, because a lane harness writes nothing to
`users/{uid}/runs` - only the web runner does. Fixed for this round under the W47 standing rule:

- **209 run records written** to `C:\EdgeLog\run_records\enguq_202611.jsonl` and synced, one per
  reported cell at **two cost rungs** - 0.533 (the house headline the verdict rests on) and 0.25 (my
  ladder's lowest, now labelled below any real cost). Stage `preLB`, family `ENGU-Q`, ES 5m, ledger
  row 2.218.
- **The figures are stored as measured, never re-derived.** Each was produced by
  `augur_engine.drawdowns.four_numbers` off that cell's own DAILY dollar series with zero days
  included, and handed to `run_record.write_record` through `numbers=`, which stores a lane's dict
  exactly as given. Nothing I did not measure was written.
- **The 0.08 and 0.10 rungs were deliberately NOT written.** Per 4a they are below any real cost, and
  a row on the owner's chart is a claim about a tradeable result.
- **Three rows were refused and stay refused, correctly.** `D2' w=10/15/20 d=0.5 B0 X1` at house cost
  lose over $1,000,000 on a $100,000 account, so their DD % from peak reads 1,068-1,138%, and the
  writer refuses a percentage that large without the dollar drawdown beside it. I did not store a
  max drawdown for those cells and will not derive one from the net, which is the house rule the
  writer is enforcing. Their DD % was never interpretable anyway, for the reason in section 4.
