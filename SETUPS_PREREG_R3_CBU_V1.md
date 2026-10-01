# CBU rules v1 (CBU-Q 2.0): pre-registration

**Written and committed 2026-10-01, before any backtest of these rules.**

- **Owner ask, via MANAGER:** "for the CBU rules, those are for you to write based off the CBU history
  overall". The rules below are written from his history, not by him. At most 5 owner questions are left
  open (section 6).
- **MANAGER defaults for the other ALGO_SCOPE calls:**
  - track = alerts first;
  - name CBU-Q;
  - test window pinned as written (round 1);
  - micro (MNQ/MES) costs;
  - EBU = the data's reading (a local breakout above the 10-candle high but below the day's high);
    recorded here and not tested.

## 1. Evidence the rules are written from

**A. 2026 CBU journal** (`setups/CBU.md`): 12 real futures trades, plus the first SHOULD HAVE TRADED entry
(2026-09-30 09:59 MNQ). All 13 were measured on 1-minute bars at the candle he keyed on, with ATR14 = the
1-minute average true range of the 14 bars before it.

| Measure (13 examples) | Values | Reading |
|---|---|---|
| Signal candle range | 1.24-6.22 ATR, median 1.84 | a big candle; 13 of 13 are 1.2 ATR or more |
| Signal candle body | 0.74-5.76 ATR (all green) | 13 of 13 are 0.7 ATR or more |
| Volume vs the 10 bars before | 0.94-15.2x, median 2.5x | 11 of 13 are 1.5x or more |
| New high of the day | 7 of 9 non-09:30 signals | the two misses: 04-07 13:34 and 04-27 15:45 |
| 09:30-candle signals | 3 of 13 | 2 of 3 close above the premarket high |
| How long the broken high had held (30-bar lookback) | 1-2 bars on 8 of 13; 13-27 bars on 5 of 13 | two kinds; see below |
| Base height under a held high | 3.0-4.7 ATR on those 5 | a real base is a few ATR tall |
| Close past the broken high | 0.0-4.7 ATR, median 1.15 | never far past, except on the 09:30 bursts |
| Context (point score at the signal bar) | above the 5m and 30m 200 EMA 12 of 12; above yesterday's high 11 of 12 | always in an up day above yesterday's high |
| Time | 7 of 13 at 09:30-09:59; 8 of 13 before 11:00; the rest 11:12-15:45 | |
| Stop he drew | the signal candle's low (stop ≈ candle range, median 1.7 ATR) | |
| Target he drew | R:R median 1.0 (0.1-9.0); 09-30 box 1.5 | |
| Result | exits in 1-3 minutes, actual R median +0.22 before fees | his note on 04-07: "should have moved SL at 1:1 for 2:1 RR" |

**Two kinds of CBU on a 1-minute chart:**

- **Base breakout (5 of 13):** the high had held for 13-27 minutes and the base under it is 3-5 ATR tall.
  - Examples: 04-14 10:35, 04-15 11:12, 04-21 09:52, 04-27 15:45, 09-30 09:59.
- **Momentum new high (8 of 13):** the high was made 1-2 minutes earlier.
  - On his 5-10 second chart there is a base inside the minute; a 1-minute rule cannot see it.

**B. 2024-25 tracker** (`TRADETRACKER_2025.xlsx`, 'F old'): 10 CBU trades, 9 on 5-minute charts.

- Breakout candle scored the maximum 3 "candle points" (largest of the day, of the swing, of the
  structure) on 8 of 10.
- Breakout volume scored the maximum 3 volume points on 7 of 10.
- Above the 200 EMA 9 of 10; above VWAP 9 of 10.
- Drawn R:R max median 1.85.
- Structures were wide: 84-1,529 five-minute bars, 26-132 ES points tall.
- That older style supports the context rules (200 EMA, biggest candle and volume). It does not support
  the base size, because it was a different chart speed.

**C. ALGO_SCOPE and round 1:**

- CBU closes at a new high of the day, usually far above the morning levels.
- Its profit as a plain rule (#427) was NOISE #382's trend days.
- Prior art (rounds 37-38): "do not re-test 1m fixed-target scalps". Fixed 1R targets on 1-minute bars
  lose at micro costs.

## 2. The rules, CBU-Q 2.0 (long; one-minute bars, decision at the close of bar i)

1. **Context:** close above the 200 EMA of the 5-minute AND the 30-minute bars (24-hour, roll-corrected,
   point-score definition), and above yesterday's regular-session high (point-score definition with
   holidays and completeness).
2. **Level:**
   - Close above the highest high of today's regular-session bars before i (a new high of the day).
   - On the 09:30 candle there is no earlier regular-session bar, so the close must instead be above the
     premarket high (04:00-09:29).
3. **Candle:** green, range ≥ 1.2 ATR14, body ≥ 0.7 ATR14.
4. **Volume:** ≥ 1.5 × the mean volume of the 10 bars before i.
5. **Base** (`base`, two pre-declared variants; owner question 1):
   - `any`: no base requirement.
   - `held`: the highest high of the 30 bars before i was set at least 10 bars before i, and the base
     (that high minus the lowest low after it, up to i−1) is ≤ 5 ATR14 tall.
6. **Time** (`window`, two variants; owner question 2): signal bar 09:30-10:59 (`am`) or 09:30-15:44
   (`day`).
7. **Entry and stop:** entry at the open of bar i+1; stop = low(i) − 1 tick. Never more than one position
   at a time, and at most 2 trades per session.
8. **Exit** (`exit`, two variants; owner question 4):
   - `ride`: stop to breakeven when a bar closes at +1 R, flat at the 15:59 close.
   - `be2r`: the same breakeven, plus a 2 R target. This is his own note.
   - A plain 1 R target is NOT tested: prior art killed it at these costs.
9. **Costs (micros, round trip):**
   - MNQ: 1.20 points ($1.90 fees = 0.95 point, plus 1 tick); stress 1.45.
   - MES: 0.63 points (0.38 + 1 tick); stress 0.88.
   - In dollars at $2 and $5 a point.

**Fit to the 13 examples (in-sample: the rules were written from these, so this is a fit check, not
evidence):**

| Variant | Examples caught | Which |
|---|---|---|
| `any` + `am` | 5 of 13 | 04-14 10:35, 06-15 09:30, 07-10 09:30, 08-04 09:50, 09-30 09:59 |
| `any` + `day` | 8 of 13 | the five above, plus 04-15 11:12, 05-08 11:36, 06-11 15:30 |
| `held` + `am` | 2 of 13 | 04-14 10:35, 09-30 09:59 |
| `held` + `day` | 3 of 13 | 04-14 10:35, 09-30 09:59, 04-15 11:12 |

**Misses:**

- volume under 1.5x: 04-14 09:42, 04-21 09:52;
- not a new high of the day: 04-07 13:34, 04-27 15:45;
- 09:30 candle below the premarket high: 06-30.

## 3. Test 1: the alert check (runs first, no outcomes)

- **Data:** every 1-minute bar on NQ and ES (roll-corrected masters plus the 10-second-capture fill),
  2026-04-07 to the latest closed session.
- **For each of the four base × window variants, report:**
  - alert episodes per session per market and combined (a run of consecutive signal bars counts once);
  - % of sessions with at least one;
  - recall on the 13 examples: same minute or the minute after, matching the catch-rate check of
    2026-09-28 (in-sample, flagged);
  - recall on every SHOULD HAVE TRADED CBU entry dated after this commit (out of sample).
- **Useful** = in-sample recall ≥ 5 of 13 at ≤ 3 alerts a day combined.
- This feeds the alerts-first track. No outcome is read.

## 4. Test 2: outcome triage (only after the owner answers section 6; a new commit fixes the cells first)

- **Window, as written:** selection 2010-06-07..2025-07-06; held-out 2025-07-07..2026-04-06 (never
  touched at triage).
- **Cells:** base {`any`, `held`} × window {`am`, `day`} × exit {`ride`, `be2r`} × root {NQ, ES} = 16.
  The owner's answers may narrow this; they cannot add cells.
- **House bar,** as in rounds 1-2, in micro dollars:
  - PF ≥ 1.25;
  - net/DD ≥ 8;
  - at least 300 trades;
  - at least 6 of 8 slices positive;
  - top-10 share < 90% with positive net without them;
  - $/trade ≥ 2× cost.
- **Advance rule:** stress PF ≥ 1.10, and at least 2 one-step neighbours with PF ≥ 1.15.
- **Also reported:** the NOISE #382 overlap test (round 1). A pass that lives on NOISE trend days is that
  crown's factor.
- **An advancing cell goes to one Auto-Validate:**
  - 900 trials, `wf_folds` 8, `date_from` 2010-06-07, `date_to` 2026-04-06, `lockbox_months` 9, pinned;
  - grid = the file's validate preset;
  - judged on the owner yardstick: ROC %/yr at a $30k daily-valued worst drawdown, walk-forward and
    lockbox apart, Sortino, 100 walk-forward / 50 lockbox trades, lockbox profitable without its top trade.
- Then it goes on the RUNBOARD watch list.

**The labelled set:**

- The journal trades and SHOULD HAVE TRADED entries are a labelled set used only for recall.
- They are never lockbox data, and never outcome evidence for a backtest.
- No trade date from 2026-04-07 on enters any backtest window above.

## 5. Look-ahead alarms

- Every condition reads only bars closed by the close of bar i.
- The 5m and 30m EMAs use the bar before the one that holds i.
- Yesterday's high comes from a strictly earlier, complete, non-holiday regular session.
- The base reads bars i−30..i−1.
- Unit tests mutate bars ≥ i+1 and assert the decision at i is unchanged, for every variant.

## 6. The questions only the owner can settle

At most 5; defaults apply if unanswered.

1. **Must a CBU break a high that has held for a while (10+ minutes), or does a new high made a minute
   or two earlier count?**
   - Data: 8 of your 13 look like the second kind on 1-minute bars; their base is only visible on your
     5-10 second chart.
   - Default: test both.
2. **Do you skip CBUs after 11:00?**
   - Data: 8 of 13 were before 11:00. The five later ones ranged from -1.05 to +0.60 R. In your journal,
     CBU at the open averaged +0.33 R against +0.03 R later.
   - Default: test both windows.
3. **Does a breakout on the 09:30 candle itself count as a CBU, provided it closes above the premarket
   high?**
   - Data: 3 of 13 were 09:30 candles; 2 closed above the premarket high.
   - Default: yes.
4. **Management: after +1 R, do you move the stop to breakeven and hold for 2 R (your 04-07 note), or
   take profit at about 1 R as you draw it?**
   - Data: drawn boxes are about 1:1, and actual exits average +0.2 R inside 3 minutes.
   - On 09-30 the drawn box would have lost 1 R; breakeven at +1 R would have scratched it.
   - Plain 1 R targets are not testable here (dead at micro costs in earlier rounds).
   - Default: test breakeven-then-ride and breakeven-then-2 R.
5. **Is the 1.5x volume minimum right, or is the candle size enough on its own?**
   - Data: 11 of 13 had 1.5x or more. The two that didn't were 04-14 09:42 (0.94x, +0.08 R) and
     04-21 09:52 (1.13x, +0.46 R).
   - Default: keep 1.5x.

The dashed line at about 30,807 on the 09-30 chart is answered by the data: it is the top of the
09:34-09:58 base (30,806.75 exactly).

## 7. Deviations log (append only)

(none yet)
