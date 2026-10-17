# Should have traded: 10-12 CBD, 10-14 ENGD, 10-16 ENGD (NQ, 1-minute)

Owner, 2026-10-17: "add these to the should-have-traded ledger, add their setups / price action to the
discretionary-to-algo data, deep dive these trades: what contributed to their success, how you would have
managed them, how we keep trading / improve them, parameters to adjust. The NQ trades had lots of bearish
momentum, all were below the previous day's low and many had momentum that agreed on the 5m and 30m."

Everything below is computed from the 1-minute CME bars (`augur_uploads/NOADJ_NQ_1m_ETH.csv`, NT-spliced for
10-12 and 10-14; the 10-16 session carries no source tag yet, see the note at the end) and the three snapshots.
The charts are NQ1!; he trades MNQ, so results are in points and R (R = the signal candle's high minus the
entry). These are three single trades: no backtest numbers, no claim of an edge. They are an answer key for the
algo work (`tools/data/setup_journal.json`, key `missed`; rendered on `setups/CBD.md` and `setups/ENGD.md`).

## The three signals

| | 10-12 CBD | 10-14 ENGD | 10-16 ENGD |
|---|---|---|---|
| Signal candle (ET) | 10:06 | 09:57 (09:52 is the alternative read; no box drawn) | 10:51 |
| Signal O / H / L / C | 30,944.25 / 30,952.25 / 30,920.75 / 30,921.00 | 30,541.50 / 30,542.50 / 30,477.75 / 30,479.25 | 29,936.50 / 29,937.00 / 29,891.00 / 29,893.75 |
| Body, x prior 10 bars | 23 pts, 2.3x | 62 pts, 2.6x | 43 pts, 8.0x |
| Volume, x prior 10 bars | 2,093, 1.7x | 4,759, 1.7x | 1,970, 1.65x |
| Range / 14-bar ATR | 1.7 | 1.8 | 2.4 |
| Structure | broke the floor of a 22-bar base (09:43-10:04, 30,945-31,007), new low of day | engulfed 09:53-09:56 after the 09:48 lower high, new session low | engulfed a 7-bar base (10:44-10:50) after a 55-min pullback that stalled under the 1m 200 SMA; not a new low of day |
| Entry (next open) / stop (signal high) / risk | 30,920.75 / 30,952.25 / 31.5 pts | 30,479.25 / 30,542.50 / 63.25 pts | 29,894.25 / 29,937.00 / 42.75 pts |
| Drawn target | ~30,860 (1.9 R) | none drawn | ~29,825 (1.6 R) |

### Context at the signal close (the "momentum agreed" the owner saw, measured)

| | 10-12 | 10-14 | 10-16 |
|---|---|---|---|
| vs prior day's low | 70 below | 112 below | **271 above** (10-15 low 29,622.50) |
| vs prior day's close | 193 below | 309 below | 248 below |
| vs premarket low | 96 below | 56 below | 129 below |
| 200 SMA 1m / 5m / 30m | below all three | below all three | below all three |
| 5m 20 EMA: price below, slope down | yes, yes | yes, yes | yes, yes |
| 30m 20 EMA: price below, slope down, last 3 bars red | yes, yes, 3 of 3 | yes, yes, 3 of 3 | yes, yes, 3 of 3 |
| Day shape before the signal | gap down 69, 110-pt flush 09:30-09:34, base | 08:30 data candle broke the rising support line by 200 pts in one minute; open bounced to a lower high | gap down 118, 240-pt sell to 29,787 by 09:55, 55-min pullback |
| Point score (ps1.2, SMA) | 7/9, daily trend not down | 9/9, daily trend down | 5/9, daily trend down |

Correction to the owner's note: two of the three were below the previous day's low. The 10-16 trade was 271
points above it; it was below the previous day's close and the premarket low. It was also the best of the three,
and the lowest point score. The alignment that all three share is the 5m / 30m one: below the 200 SMAs, falling
20 EMAs, three red 30m bars, below yesterday's close.

## What happened next (nothing here is counted anywhere)

| | 10-12 CBD | 10-14 ENGD | 10-16 ENGD |
|---|---|---|---|
| Worst excursion first 30 min (pts, % of risk) | 12, 39% | 59, 93% (10:03 high 30,538, 4 pts from the stop) | 5, 12% |
| Best excursion 5 / 15 / 30 / 60 min (pts) | 52 / 54 / 64 / 64 | 14 / 22 / 25 / 62 | 58 / 163 / 218 / 249 |
| 1 R / 1.5 R / 2 R / 3 R first printed | 10:09 / 10:10 / 10:27 / never (stop first) | 11:05 / 11:11 / 11:37 / 12:10 | 10:53 / 11:00 / 11:02 / 11:05 |
| Drawn target printed | 10:26 | - | 11:00 |
| Stop (signal high) printed | 11:48 | never | never |
| Day low (time), max R | 30,844 (14:52), 2.4 R | 30,078 (15:05), 6.3 R | 29,269 (15:08), 14.6 R |
| 16:00 close, R at close | 30,896, +0.8 R | 30,186, +4.6 R | 29,379, +12.0 R |

### The same three trades under different exit rules (R per trade; the total is the sum)

| Exit rule | 10-12 | 10-14 | 10-16 | Total |
|---|---|---|---|---|
| Out after 2 minutes (his live habit on the real trades) | +0.76 | +0.08 | +0.93 | +1.8 |
| Out after 15 minutes | +0.83 | +0.16 | +3.55 | +4.5 |
| Bracket at 2 R | +2.0 | +2.0 | +2.0 | +6.0 |
| Half off at 2 R, rest to breakeven then trailed under the last five 5-minute highs | +1.0 | +2.6 | +2.9 | +6.5 |
| Stop to breakeven after +1 R, else hold to the close | 0.0 (stopped 10:15 by 3 pts) | +4.6 | +12.0 | +16.7 |
| Stop to breakeven after +1.5 R, else hold to the close | 0.0 | +4.6 | +12.0 | +16.7 |
| Trail under the last three 1-minute highs after +1 R | +0.56 | +1.2 | +0.85 | +2.6 |
| Hold to the close, stop at the signal high | -1.0 | +4.6 | +12.0 | +15.7 |

## Assessment

**What contributed to their success.** The candle was the trigger, not the reason. All three fired inside a
day that had already declared itself: an opening or 08:30 impulse of 110-240 points, price under the 200 SMA on
the 1m, 5m and 30m, falling 5m and 30m 20 EMAs, three red 30m bars, and a close below the previous day's close
(twice also below its low). Each signal bar was the largest body of its last ten (2.3x, 2.6x, 8x) on 1.65-1.7x
volume and closed through a structure: the floor of a 22-bar base (CBD), or the lows of a 4-7 bar pullback after
a lower high (ENGD). Two of the three were trend days that closed near their lows; the entries caught the second
leg. His real CBD trades on MES (5, -$303) were taken without this alignment being checked; three trades cannot
prove the alignment is the difference, but it is the testable hypothesis.

**How I would have managed them.**
1. The stop at the signal candle's high was right on all three: it was never hit inside the first hour (39%,
   93%, 12% of the risk used), and on 10-12 it only printed at 11:48, after the drawn target had paid.
2. The 10-14 entry is the one to fix. Entering at the low of a 65-point bar with the stop at its top is a 63-point
   risk and a 93% excursion before it worked. The first engulfing bar after the lower high (09:52) had the same
   stop logic, 56 points of risk, 33 points of heat and paid 1 R in five minutes. If the first bar is missed,
   waiting for the pullback into the big bar (the 10:03 bounce reached 30,538) gives a better price with the same
   stop. Either way, size by the stop: a 63-point stop is one MNQ, not three.
3. Breakeven moves do not fit NQ at one minute: on 10-12 the breakeven stop was hit by 3 points at 10:15 after
   +1.7 R was on the table. A fixed 2 R bracket paid on all three (+6 R total); half off at 2 R with the rest
   trailed under 5-minute highs paid slightly more (+6.5 R) and keeps a runner on days like 10-16.
4. The two-minute exit habit (what the real-trade exit check found) would have made +1.8 R on three trades that
   were worth +15.7 R held with the original stop. The money in these setups is 10 to 60 minutes out, not 2.

**How to keep trading them, and the parameters to test.** For the discretionary side: a one-line checklist
before the entry: below yesterday's close, below the 5m and 30m 200 SMA, 5m and 30m 20 EMAs falling, three red
30m bars; signal body at least 2x the last ten and volume at least 1.5x; CBD closes below a base of 15 bars or
more, ENGD closes below the lows of the last three bars after a lower high; entry next open, stop at the signal
high, first target 2 R, size by the stop. The point score is not the filter: the best trade scored 5/9 because
"below yesterday's low" and the biggest-bar points missed; the 5m / 30m alignment is what the three share.

For the algo side (DISCRETIONARY-TO-ALGO; `setups/ALGO_SCOPE.md` item 2, the box-breakout scan, already
describes the shape): a short-side scan on NQ 1m, 09:45-11:30, with exactly the context filter above, the two
trigger shapes, next-open entry, stop at the signal high, and the three exit rules that paid here (2 R bracket;
half at 2 R plus a 5m trail; hold to close). Frozen first, run as a Stage A on the walk-forward years only, the
owner's three dates and the journal's six real CBD / ENGD trades held out as the answer key, and the usual bar:
gross edge per trade above the round-trip cost, net ROC at $30k above zero, not one episode. Round 1 of the setups
found no edge in the bare candle rules; this adds the context filter those rules did not have.

### Data note

The 10-16 session's 1-minute rows carry no `source` tag in the NQ master (10-12 and 10-14 are `nt_hist_splice`).
The levels used here (open 30,024.25, low 29,268.75, close 29,379.50) match the snapshot's axis; TBIS to confirm
the 10-16 provenance when the weekday NT splice runs.
