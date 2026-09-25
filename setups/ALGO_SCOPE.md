# Algo scope for the discretionary setups (CBU, ENGU, EBU, CBD, ENGD)

> Written 2026-09-25 from the setup journals in this folder, a fresh read of what the shop has already
> tested, and four measurements on the 1-minute ES/NQ history. Each measurement was re-checked by an
> independent script; where the first pass was wrong, the corrected figure is used. The draft was then
> reviewed three ways (prior art, test design, numbers) and rewritten. Hand-written, not generated.
> It extends the discretionary-to-quant brief (`DISCRETIONARY_QUANT.md`, Path A: a rule, with your real
> trades as the answer key, not training data).

## Round 1 result (2026-09-25)

Tested as pre-registered in `SETUPS_PREREG.md`: five strategy files (CBU-Q, CBD-Q, EBU-Q, ENGU 2.0 and its short
mirror) over 516 pre-declared cells on NQ and ES 1-minute 24-hour bars, 2010-06-07 to 2025-07-06. An independent
re-implementation matched every CBU-Q and ENGU 2.0 trade before any result was read. **One cell passes the house bar:
CBU on NQ** (new day high above the prior-day high, first 30 minutes, 2x volume, breakeven at 1R then ride): 617
trades, $52,868, PF 1.81, net/DD 8.8, 8 of 8 slices - but concentrated (top ten trades 85% of net) and the pre-queue
guard shows that cell losing on 27 trades in the sealed stretch. **Its Auto-Validate FAILS (run #427, 5 of 7
gates):** the sealed nine months lose (80 trades, PF 0.85), ES loses at the same settings (PF 0.87), the luck test
fails, and the last walk-forward fold loses. On the overlap test (`tools/setups_r1_overlap.py`) 74% of its trades fall
on NOISE #382 days, same direction, and it loses $61,806 on days NOISE is flat: a morning new high of the day is the
trend day NOISE already trades. ENGU, CBD, EBU and ENGD have no edge as written rules. **Round 1 is closed; nothing goes
forward.** STUDIES rows 1752-1766.

## The short version

1. **The mechanical versions of these setups are already dead or closed here.** The shop tested almost
   every piece on 1-minute NQ in rounds 37-38 (micro opening-range break, open drive, prior-day-high
   break, range burst, volume ignition, 5-bar box break): 0 of 59 short-hold cells paid at house costs,
   and the standing rule is *do not re-test 1-minute fixed-target scalps*. The older ENGU files (the
   range-consolidation breakout and the engulfing breakout of a consolidation) died under honest fills,
   a big-candle-plus-volume rule had no edge over about 10,000 fires in July, and GAPGO (the gap-and-go
   break) failed validate on its sealed year. This session's box-breakout scan found the same thing
   again: near break-even before costs, nothing that survives your micro costs.
2. **What the journals add is what you select.** CBU closes at a new high of the day (7 of the 9 CBU
   signals that had an earlier regular-session candle), usually on a day already trading above its
   premarket and prior-day highs. ENGU does not: it fires inside the day's range (2 of 16 at a new
   high, 5 of 17 above the high of the 10 candles before). That split is the clearest thing in the data.
3. **Recommendation.** First, **measure and build a live setup alert** (Track B): it flags CBU and ENGU
   candidates on your chart and you still decide; it needs no proof of edge. Second, spend at most
   **one** pre-registered validate on the single combination the shop has not run (a new day high AND
   above a morning level, with a ride-to-the-close exit), knowing the likely result is that it
   duplicates ORB #314 / NOISE #382 or fails (Track A). No new ENGU algo and no stock algo yet (Track C).

## What the data says, setup by setup

Your real futures trades (details, charts and the full signal-bar features table on each setup page):

| Setup | Trades | Wins | Net $ | Avg R | Where the signal candle closes (known at its close) |
|---|---|---|---|---|---|
| CBU | 12 | 7 | +53.49 | +0.18 | new high of the day 7 of 9 (three 09:30 signals have no earlier candle), above the premarket high 9 of 12, above the prior-day high 10 of 11, above the 10-candle high 12 of 12 |
| ENGU | 17 | 12 | +107.25 | +0.10 | new high of the day 2 of 16, above the premarket high 2 of 17, above the prior-day high 2 of 17, above the 10-candle high only 5 of 17 |
| EBU | 9 | 4 | +29.15 | -0.01 | above the 10-candle high 7 of 9 (2 exactly at it), new high of the day only 2 of 9, above the premarket high 2 of 9, above the prior-day high 4 of 9 |
| CBD | 4 (3 signals) | 3 | +21.15 | +0.15 | new low of the day 3 of 3 signals, below the premarket low 2 of 3, below the prior-day low 2 of 3 |
| ENGD | 2 | 1 | -7.55 | -0.09 | too few |

Read with care: 44 trades, April-September 2026. Half of the CBU signals (6 of 12) are 09:30-10:00;
the other half are spread through the day. On 6 of the 12 CBU trades you bought inside the signal
minute off a 5- or 10-second chart, so that 1-minute candle closed after your fill; the features
describe the 1-minute candle that holds your trigger, which is what a 1-minute rule would see.

- **CBU = a new high of the day.** Nearly every CBU closes at a new high of the day and above the
  morning levels, and usually far above them (when above, a median of about 7 ATR past the premarket and
  prior-day highs): a new high on a day that is already strong, not the first cross of a morning level. The
  base under the break is short (median 2 candles, 1-6), and base length does not separate CBU from
  ENGU or EBU.
- **ENGU = a candle inside the range.** Volume spikes and candle size overlap heavily between the
  setups (a 09:30 candle always looks like a spike against pre-market volume). The July ENGU-Q work
  found structure height (how tall the base being broken is) was the only attribute with any link to
  your wins (r about +0.29 on the small 2025 tracker sample, "signals, not proof"), and the shop has
  since found that height mostly measures volatility; if it is ever used, measure it in ATR units.
  Your own ENGU entries showed a short edge in July (about +2 points in the first 1-2 minutes, fading
  by 5) on 13-18 trades.
- **EBU** is below the day's high like ENGU but above the 10-candle high like a small breakout; on 4
  of 9 it is well above the prior-day high. It needs its own written rule (owner call).
- **CBD / ENGD** (shorts): too few. The short-side evidence elsewhere is mixed and not comparable
  (ENGU-Q's short mirror of a long-hold trendline break was 0 of 61; ORB's short side was the stronger
  one on a lineage that was later voided).

## The four measurements behind this

Scripts and outputs are in the session scratchpad (`scratchpad/algo/`).

1. **Signal-bar features of all 44 futures trades** (now on each setup page): minutes after 9:30,
   candle range vs ATR, volume vs the 10 candles before, base length, distance past the 10-candle high,
   the day's high so far, the premarket high and the prior-day high. Each uses only bars that had
   closed when the signal candle closed; the prior day skips weekends and exchange holidays and is
   left blank across a contract roll.
2. **Box-breakout scan (the CBU / EBU / CBD shape; it re-derives rounds 37-38 rather than adding to
   them).** At the close of a 1-minute regular-session candle: the N candles before it span at most
   K x ATR14, it closes beyond their high (low), its volume is at least V x their average. N in {5, 10,
   15}, K in {1, 1.5, 2}, V in {1, 2, 3}; fill at the next open, stop at the signal candle's low (high),
   gap-through fills; exits 1R or 15 minutes, flat at 5 minutes, or stop or 15 minutes. Outcomes only
   2018-01-01 to 2025-06-29. Before costs, most cells sit near break-even (N=5, K=2: ES PF 0.92-1.09, NQ
   0.95-1.15 across the three exits) and a few reach PF 1.2-1.3. At your micro cost ($1.90 a round trip
   plus 0.25 point of slippage per side) 0-2 of 59 cells per exit (3 in all) reach PF 1.01-1.05 and
   every cell's average R is -0.15 or worse; at the shop's full-size cost 5 of 118 cells are above PF 1
   (best PF 1.22 on 57 trades). Noise, given how many cells were tried. Recall against your 23
   CBU/EBU/CBD trades with data: 11 at about 15-17 fires a session per side, 6 at about one extra fire
   a session. It could not fire before 09:44, which hides 3 of the 10 CBU trades with data, and even
   with pre-market bars in its windows it still misses those three. It never tested the new-day-high
   condition.
3. **ENGU pattern and ENGU-Q vs your ENGU trades.** A strict engulfing rule (big body, closes above the
   prior candle's high, 2x volume) fires within 5 minutes of 4 of your 19 ENGU/ENGD trades (6 of 19
   when pre-market bars count in its baseline), about 3x chance, at about 6 fires a session; it was not
   outcome-tested (the July "no edge, about 10,000 fires" result was a looser rule without the engulf).
   ENGU-Q's raw signals land within 5 minutes of 4 of your 17 ENGU trades (about 3.5x chance), including
   09:30 on 2026-09-22 (judged on Yahoo bars, the only source for that week); but ENGU-Q was already in
   a position at 13-14 of your 19 signals and entered at only 1. It is a descending-trendline break with
   a resting limit entry that holds for hours (median about 5-12 hours, longest about five months): a
   similar trigger rate, a different trade.
4. **Where tests must not look.** A validate run today holds out the last 12 months (rolling, about
   2025-09-24 onward), which contains every journal trade, the design choices taken from them (the open
   window, the 3x volume split) and the 2026-07-01..08-05 data hole. Track A therefore pins its window
   so that none of that is in the held-out year (below).

## Prior art (why most of this is closed)

| Tested | What it was | Verdict |
|---|---|---|
| Rounds 37-38, NQ 1m (NOISE.md, BOOKMARKS round 37/38) | micro opening-range break, open drive (stop at the 09:30 candle), first close beyond the prior-day high, range burst, volume ignition (close above the 60-bar high on 2x volume, candle stop), 5-bar box break | 0 of 59 short-hold cells; fixed targets lose at house costs. In round 37 only ride-to-the-close exits earned (prior-day-high break with a ride exit PF 1.19, holds of 100+ minutes); in round 38 ignition and box break lost with ride exits too. "Do not re-test 1m fixed-target scalps." |
| Legacy ENGU files (ENGU 1.1.x, 1.3.x) | engulfing breakout of a consolidation; range-consolidation breakout with body and volume filters | dead under honest fills (1.3.x PF 1.05 to 0.89; 1.1.20/21 PF 0.82) |
| July ENGU-Q research | big candle + volume, next-candle entry, ES 1m | no edge over about 10,000 fires; 0 of 312 grid cells positive in and out of sample |
| ONRANGE (round 36) | open at the edge of the overnight range, then a first-bar close break | PF 1.31 on 1,201 trades but 88% of net in the top 10; not adopted |
| GAPGO (B21/B22) | gap direction confirmed by a 5-minute close beyond the first bar(s) | passed triage and 6/6 gates, then failed validate on its sealed year; closed |
| DRIVE, PDX / NDAY | first-hour momentum; prior-day and N-day high/low breaks | closed / dead |
| MISC round 16 | daily-bar narrowing (NR7/NR4/inside day) and session-range breaks | dead |
| TTM | squeeze breakout | survives only on ES 30m, as a book leg |
| Live crowns nearest to a CBU at the open | ORB #314 (2-bar opening range, close-confirmed break), NOISE #382 (band break anchored to the open) | live; any new opening break must prove it is not one of these |

## Track B: live setup alerts (recommended first)

Automating the chart-watching, not the decision.

1. **Measure before building.** For a CBU rule ("a 1-minute candle closes at a new high of the day and
   above the premarket or prior-day high") and an ENGU rule (big-body engulfing candle on a volume
   spike, inside the day's range), count alerts per session on 2024-2025 history and recall on your
   journal trades. This is signal-only (no outcomes), so it cannot overfit a later test. The target of
   "most of your setups at 2-3 alerts a session per market" is unmeasured until then; the box rule
   managed 6 of 23 at one extra fire a session.
2. **Build** the alert as a TradingView indicator with alerts, or a NinjaTrader indicator. Volume
   thresholds must be calibrated on the feed it runs on (the ENGU-Q Pine port switched its volume
   filter off because TradingView's volume differs from the shop's data). `pine/ENGU_1_3_5.pine`
   (range-consolidation breakout) and `pine/NOISE_1_0.pine` are the nearest existing Pine code; none of
   the repo's Pine files raise alerts yet.
3. **Log every alert with its outcome and whether you took it.** At 2-3 alerts a session per market on
   two markets that is roughly 1,000-1,500 candidates a year: the dataset the automated path is missing.
4. **Judge it on your next 20 trades:** how many had an alert first, and how many alerts you ignored.

## Track A: one pre-registered test (proposed name CBU-Q)

**What is untested:** only the combination. Each leg has been run on 1-minute NQ (prior-day-high break,
day-high break at the open, candle-low stop), but not "new high of the day AND above a morning level".
**Honest prior: low**, and the likeliest outcome if it earns is that it is ORB #314 or NOISE #382 on a
1-minute chart. A full pre-registration (in the style of `ENGUQ_R57_PREREG.md`) must be written, dated
and committed before the strategy file exists. It must contain at least:

- **Rule, with information times.** Decision at a 1-minute candle's close, fill at the next open. Long
  when the close is above every earlier regular-session high of the day and above `level` (premarket
  04:00-09:29 high / prior regular-session high / both). The prior day skips holidays and is not used
  across a contract roll (skip those days). ATR and volume baselines come from the 24-hour tape. The
  **09:30 candle is its own pre-declared cell** (its volume always clears a 3x bar against pre-market
  volume, so there the rule is a gap-and-go, whose controls are open drive and GAPGO), with results
  reported split 09:30 vs 09:31-end. One trade per day per side. Stop at the signal candle's low; risk
  measured from the fill; if the next open is at or beyond the stop, no trade; if one candle touches
  both stop and target, the stop counts first.
- **Exits: tail-keeping, not fixed targets** (rounds 37-38 closed fixed targets on 1-minute bars):
  breakeven after `B` x risk, then ride to 15:55 or a trailing stop; a fixed-target cell only as a
  pre-declared control that is expected to fail.
- **Minimum stop size** or a slippage stress, because one-candle stops on 1-minute bars fall under the
  shop's fill-realism floor (about 8 NQ points; your CBU stops median about 4 ES points).
- **Window pinned** so the held-out year holds no journal trade, no design sample and no data hole: for
  example 2010-06-07 to 2026-04-06 with a 9-month held-out stretch (2025-07-07 to 2026-04-06), on the
  24-hour 1-minute master. April-September 2026 is used only for recall on your trades. This overrides
  the "date_to = today for new research" default, so it is an owner call.
- **Validate settings:** the shop's 900 trials, 8 folds, `auto_expand` off (it would push 2- and 3-value
  knobs past the frozen grid), no held-out numbers for any config other than the crowned one
  (`oos_sample_k` 0), knob sets that are not numeric steps declared as options.
- **Cost:** stated in points per instrument (full-size or micro: owner call), plus a stress cost the
  rule must also pass.
- **Kill rules, set now:** a triage bar on the selection window before any validate is queued (the
  house bar: PF 1.25, MAR 8, 300 trades, 6 of 8 slices, top 10 under 90% with positive net without
  them); FAIL or WEAK; fewer than 90 trades in the held-out stretch; held-out PF below 1.1 at the stress
  cost; concentration judged per stretch with a rate-matched top-k; and the **house overlap test**
  against both ORB #314 and NOISE #382 (shared days, same-direction share, and CBU-Q's net on days the
  crown is flat, with the pass level set in the pre-registration). A daily-P&L correlation cut-off is
  not enough: GAPGO was judged a copy of the ORB factor at a correlation of 0.19.
- **Multiple testing:** the count includes this session's 324-combination scan.

## Track C: what to leave alone for now

- **A new ENGU algo.** The reasons are the July grid (0 of 312), the rounds 37-38 closure of 1-minute
  scalps, and the data: the part of ENGU that might be yours is a one-to-two-minute effect, and the
  10-second capture only starts 2026-06-23 (about three months). Revisit with twelve months of 10-second
  history (mid-2027). ENGU-Q stays what it is: a trendline-break trend trade that shares your trigger
  about as often as a plain candle rule does.
- **Stock CBU.** The shop has no small-cap intraday data (no Alpaca keys; Yahoo serves only recent
  1-minute bars, about 7 days per request), so stock setups cannot be backtested. The older sheet rows
  keep float, relative volume and breakout size, which would be the scanner fields later.
- **An ML gate or overlay on your trades.** Cut gates and size tilts failed under honest fills; KEEL
  and the hybrids have a mixed record on the crowns; none of them can learn from 44 trades.

## Small infrastructure

- **Overlap report** (listed as not built in the discretionary brief): any rule's fires against your
  trade times, with recall and extra fires a session. The scans here already compute it; it should
  become a tool, because Track B's first step is exactly this.
- **REPLAY of your journal trades**, only where it is honest: trades from 2026-06-23 on (10-second bars),
  second-level fill stamps or the next open, the edge statistic called directly on the trade list, and
  at most one pre-declared mechanical exit. The July attempt found 1-minute replay of these scalps
  misleading, and 36 of the 44 trades are older than the 10-second history.

## Owner calls

1. Which track: alerts first (recommended), the CBU-Q test, both, or neither.
2. The name: CBU-Q for an automated family (it would join the family list, like ENGU-Q).
3. For CBU-Q only: pin the test window as above (overrides "date_to = today"), and full-size or micro
   costs.
4. EBU: write its rule, or accept the data's reading (a local breakout below the day's high).
5. Stocks: add Alpaca keys if stock CBU should become testable.
