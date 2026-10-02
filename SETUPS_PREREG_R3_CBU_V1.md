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

## 4a. Outcome cells fixed (2026-10-01, committed before any outcome run)

- **Owner answers:** none yet.
  - MANAGER (2026-10-01, inbox #15): use the bracketed defaults if no answer arrives before the profit test
    is ready.
  - The defaults are: both bases (Q1), both windows (Q2), the 09:30 candle counts (Q3), ride and be2r (Q4),
    volume 1.5x (Q5).
  - So **all 16 cells run as written**. Answers arriving later can only pick among them.
- **Code:**
  - `augur_strategies/CBUQ_2_0.py` (family CBU-Q; DEFAULT_PARAMS ranged for Auto-Validate);
  - driver `tools/setups_r3_triage.py`;
  - tests `tests/test_cbuq_2_0.py`.
- **Data:** `FADJ_{NQ,ES}_1m_ETH`, sliced to 2010-06-07..2025-07-06 at read (round 2's loader and window
  assert).
- **History readings:**
  - **Yesterday** = the latest earlier session that has regular bars, is not a listed holiday, and whose
    last regular bar starts at 13:14 or later. The point score's strict "complete" needs an early-close list
    that does not exist before 2025. On 2026 data this differs from Test 1 on one ES bar (07-27 09:35, after
    an incomplete capture day).
  - **Holidays** = US equity-market full closures 2010-27 by rule, plus Sandy and two days of mourning. The
    list equals the point score's for 2025-27 (tested). No decision is made on a listed holiday.
  - **EMA warm-up:** 600 buckets.
  - **Cross-check:** on 2026-04-07..09-30 the file's signals equal Test 1's alerts on 750 of 751 bars.
- **Neighbours (7):** base flipped, window flipped, exit flipped, vol 1.25 and 2.0, range 1.0 and 1.4.
  A cell advances on: the house bar at house cost + stress PF ≥ 1.10 + at least 2 of 7 neighbours with
  PF ≥ 1.15.
- **Validate grid** (only if a cell advances): base × window × exit × vol {1.25, 1.5, 2.0} ×
  range {1.0, 1.2, 1.4} × body {0.5, 0.7, 0.9}.
- **NOISE #382 overlap:** reported for every cell that passes the house bar.

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

- **2026-10-01, Test 1 implementation readings** (written into `tools/cbu_v1_alerts.py` before its first run;
  none changes a rule):
  - Bars, the 5m/30m EMAs and yesterday's high come from the point-score loader: the NOADJ 1m master plus the NT
    capture in the summer hole and after the master's end, back-adjusted at the real contract switches.
  - Listed CME full holidays are not sessions.
  - A combined session needs both NQ and ES to have closed it.
  - Held base: the 30-bar high is dated at its EARLIEST bar, so an equal touch later does not reset the hold.
    The latest-bar reading was run as a check and changes nothing material: held+day 0.58 vs 0.66 a day, same
    recall.
  - Recall counts an alert at the signal minute or the minute after, as section 3 says.
- **2026-10-01, validate ranges** (after Test 2's triage and before the validate is queued): the runner's
  Auto-Validate searches the file's DEFAULT_PARAMS ranges, not a preset. Those ranges now hold the section 4a
  grid: base × window × exit × vol 1.25-2.0 × range 1.0-1.4 × body 0.5-0.9. Uniform steps add one value, vol
  1.75, to the declared {1.25, 1.5, 2.0}. That gives 288 configs.

## 8. Test 1 result (2026-10-01): the alert check

`python tools/cbu_v1_alerts.py` covered 122 regular sessions, 2026-04-07..2026-09-30, on NQ and ES.
No outcome was read. The report and the alert list are local, in `C:\EdgeLog\_anatomy_cache\cbu_v1_alerts\`.

| Variant | Alerts a day, NQ + ES (median / p90 / max) | Days with any | In-sample recall (same minute) | Useful? |
|---|---|---|---|---|
| `any` + `am` | 0.96 (0 / 3.9 / 7) | 38% | 6 of 13 (5) | **yes** |
| `any` + `day` | 2.80 (1 / 9 / 20) | 52% | 9 of 13 (8) | **yes** |
| `held` + `am` | 0.19 (0 / 1 / 3) | 16% | 2 of 13 (2) | no |
| `held` + `day` | 0.66 (0 / 3 / 6) | 29% | 3 of 13 (3) | no |

- **The same-minute recall reproduces the section 2 fit table exactly** (5 / 8 / 2 / 3).
  - The extra catch on the `any` variants is 06-30. Its 09:30 candle closed below the premarket high, but
    the 09:31 bar fired.
- **Misses:**
  - volume: 04-14 09:42 at 0.94x and 04-21 09:52 at 1.13x;
  - not a new high of the day: 04-07 13:34, which also failed the yesterday's-high context, and 04-27 15:45.
- **Held base** catches only the 5 base breakouts it was written for, and the volume rule drops 2 of those
  (04-21, 04-27).
- **Alerts bunch:** `any` + `day` has a median of 1 a day but 9 or more on the busiest tenth of days. Those are
  the up-trend days.
- **Out of sample:** no SHOULD HAVE TRADED CBU entry is dated after the prereg yet (0 of 0). Each new one gets
  scored with this tool as it comes in.
- **Verdict:** two variants meet the useful bar: momentum new highs, either morning-only or all-day.
  - These feed the alerts-first track.
  - The outcome test (section 4) still waits for the owner's answers.

## 9. Test 2 result (2026-10-01): the outcome triage

`python tools/setups_r3_triage.py`: 16 cells, 2010-06-07..2025-07-06, FADJ 1m, micro costs, runtime 39 s.
Cells were fixed in eb6bf3e8 before the run. Results are local, in
`C:\EdgeLog\_anatomy_cache\setups_r3_results\`. Money is for one micro contract.

**1 of 16 cells passes, and it advances: NQ, `any` base, `am` window, `ride`.**

| Measure | Value |
|---|---|
| Trades / days | 1,320 trades on 1,079 days |
| PF / net | PF 1.59, net $9,786 |
| net/DD | 10.6 |
| Slices positive | 6 of 8 |
| Top-10 share / net without them | 54%, +$4,496 |
| $/trade | $7.41 (bar $4.80) |
| Stress PF | 1.53 |
| Neighbours with PF ≥ 1.15 | 6 of 7; only `be2r` fails, at 1.08 |

**Near misses, all NQ `ride`:**

- `held` + `am`: PF 1.96, but slices 5 of 8;
- `held` + `day`: PF 1.63, but net/DD 7.6 and slices 5 of 8;
- `any` + `day`: PF 1.41, but net/DD 6.0, slices 5 of 8 and $/trade 4.63.

**Everything else:**

- **ES:** no cell is close. The best is `held` + `am` + `ride` at PF 1.16; every `any`-base ES cell loses.
- **Exit:** `ride` beats `be2r` in all 8 pairs. The 2 R target (his 04-07 note) turns every NQ ride cell
  into PF 1.07-1.25.

**NOISE #382 overlap (round 1's test), for the advancing cell:**

- 84% of its trades are on days NOISE #382 trades, and 97% of those are in the same direction.
- On NOISE-flat days it took 215 trades and lost $2,663 gross.
- This is the same shape as round 1 (#427: 74%, lost on NOISE-flat days). The edge is NOISE #382's trend
  days.

**Holiday audit:** 86 listed holidays had no decisions. Two short sessions that are not holidays stay in;
they are data cut-offs (2020-02-28, 2020-06-30).

**Next, per section 4:** one Auto-Validate of `CBUQ_2_0.py` on NQ, as section 4 specifies, judged on the
owner yardstick. The NOISE overlap is part of the verdict.

## 10. Auto-Validate verdict (run #481, 2026-10-02): FAIL

**The job:** `tools/queue_setups_r3_validate.py`, job 6MagctwCz68pmGh7Hu5t, CBU-Q-3.

- 288 configs, 900 trials, 8 walk-forward folds, FADJ NQ 1m, 2010-06-07..2026-04-06.
- 9-month lockbox: 2025-07-07..2026-04-06.
- Micro cost: 1.20 points at $2.

**Champion:** the triage cell itself (`any` / `am` / `ride`, vol 1.5, range 1.2, body 0.7).

**Verdict: FAIL, 5 of 7 gates.**

- Passed: walk-forward efficiency, sample, plateau, luck (DSR 0.998) and consistency.
- Failed: ES transfer (1,252 trades, PF 0.73).
- Failed: overfit, PBO 0.63 ("likely overfit selection").

**Owner yardstick** (ROC %/yr at a $30k worst drawdown valued daily; the champion's continuous trades sliced
by stretch):

| Stretch | Trades | PF | Net per MNQ | ROC @ $30k DD | Sortino (run) |
|---|---|---|---|---|---|
| IS 2010-06-07..2016-10-13 | 559 | 1.00 | +$9 | 0%/yr | - |
| WF 2016-10-14..2025-07-06 | 761 (fold-by-fold run: 694) | 1.73 | +$9,777 | **+37.8%/yr** | 3.22 |
| LB 2025-07-07..2026-04-06 | 61 | 0.50 | -$1,286 | **-40.1%/yr** | -2.70 |

**Checks against the yardstick:**

- The minimum trade counts are met: 100 walk-forward, 50 lockbox.
- The lockbox is not profitable without its biggest trade (-$1,630).
- Walk-forward folds: all 8 are positive, but fold 8 (2024-06..2025-07) made only +$96.

**NOISE #382 overlap** (section 9): 84% of the selection trades are on #382 days, 97% of them the same
direction, and they lose on #382-flat days.

**Reading:**

- CBU rules v1 found NOISE #382's trend days a third time, after rounds 1 and 2.
- As a stand-alone strategy it is dead.
- The alert check (section 8) stands. The owner's 5 answers can only choose which alert variant to keep.
