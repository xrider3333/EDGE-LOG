# POINT SCORE - spec v1.1 (`ps1.1`)

The owner's point score for his discretionary trades. The rules are his (2026-09-30), and the defaults were
approved with "go with defaults". Scope: `C:\EdgeLog\manager\point_score_scope_2026-09-30.md`.

This file is the ONE definition. `tools/point_score.py` is the reference implementation, and
`pine/POINT_SCORE_1_0.pine` is a line-by-line port of it. If either one disagrees with this file, the code
is wrong.

## 1. The signal bar

- **Timeframe:** 1 minute (the owner's default for his futures trades). `tf` is a parameter, but only `1m`
  is supported in v1.
- **Signal bar S:** the last CLOSED 1-minute bar before the entry fill.
  - S.start = floor(fill, 1 min) − 1 min.
  - A fill at 09:32:21 gives S = the 09:31 bar, which closes at 09:32:00.
  - A fill at exactly 09:32:00 also gives the 09:31 bar.
  - A fill known only to the minute ("09:32") gives the same result, so minute precision is enough.
- **C / O / V:** close, open and volume of S. **t_close** = S.start + 1 min.
- **No look-ahead:** nothing that starts at or after t_close is ever read.
- **Timestamps:** all times are America/New_York, and bars are stamped at their START.

## 2. The nine points (LONG; SHORT mirrors each one)

**1-4. `ma200_10s`, `ma200_1m`, `ma200_5m`, `ma200_30m` - close above the 200 EMA of that timeframe.**

- **EMA:** alpha = 2/201, seeded with the first close of the loaded history (pandas
  `ewm(span=200, adjust=False)`, which is Pine's `ta.ema`).
- **Futures bars:** 24-hour bars. The EMA must have at least **600** bars of its own timeframe up to and
  including the reference bar, else the point is NA ("EMA warming up").
- **Reference bar** for each timeframe:
  - **1m:** S itself, so the EMA includes C. (Pine: `ta.ema(close,200)` on the 1-minute chart.)
  - **10s:** the last 10-second bar ending at t_close; its close is C. (Pine: the last element of
    `request.security_lower_tf(..., "10S", ta.ema(close,200))`.)
  - **5m / 30m:** the bar BEFORE the one containing S.start. For S = 09:31, that is the 5m bar starting
    09:25 and the 30m bar starting 09:00. (Pine: `request.security(..., "5",
    ta.ema(close,200)[1], lookahead=barmerge.lookahead_on)`.)
  - Above/below does not depend on this choice. The "live" EMA of the forming bar lies between the previous
    EMA and C, so it is on the same side of C. Only the displayed reference value depends on it.
- **Hit:** long when C > EMA; short when C < EMA. A tie is not a hit.

**5-7. `y_low`, `y_close`, `y_high` - close above yesterday's regular-session low, close and high.**

- "Yesterday" is the most recent date BEFORE S's date that has regular-session 1-minute bars, with bar
  start in [09:30, 16:00) ET, **and is not a CME equity holiday** (v1.1). Its high = max high, its low = min
  low, and its close = the close of its last bar in that window.
- **Holidays (v1.1):** the CME holiday list in section 7 is skipped entirely, even when Globex printed a
  short 09:30-13:00 stub that day. The stub is not a regular session, so the session before it is
  yesterday. Genuine early-close days (the day after Thanksgiving, Christmas Eve) ARE regular sessions;
  their close is the 13:14 bar.
- **Completeness (v1.1):** yesterday must have its last regular-session bar at 15:59, or at 13:14 on a listed
  early-close day. Otherwise all three points (and the trend point) are NA, "prior session incomplete".
  The day is NOT skipped: it was a real session we lack data for. Example: 2026-07-24, where the 10-second
  capture stops at 10:46 inside the summer hole.
- The prior session must lie within 7 calendar days, else all three points are NA.
- **Long:** C > level. **Short:** C < level ("below yesterday's high / close / low").

**8. `big_body` - the largest body since today's low.**

- **Today window W:** 1-minute bars on S's calendar date, with start ≥ 09:30 (futures) or ≥ 04:00
  (stocks), and start ≤ S.start. If S.start is before the window start, the point is NA ("signal before
  today's window").
- **Long:** the since-low window is W from the LATEST bar whose low equals min(low over W) through S. A tie
  on the low restarts the window at the later bar. Hit = C > O AND |C − O| ≥ max(|close − open|) over that
  window, which includes S.
- **Short:** mirror it. The window starts at the latest bar whose high equals max(high over W); the candle
  must be red (C < O), with the same body test.
- The since-low window sits inside the day, so the largest body of the whole day always scores too.

**9. `big_vol` - the largest volume since today's low.**

- Same window as point 8. Hit = V ≥ max(volume) over the window, which includes S.
- No colour test.
- NA if every volume in the window is 0 or missing.

**Total and max.**

- total = number of hits among points 1-9.
- max = number of points among 1-9 that are not NA.
- na_count = 9 − max.
- **NA is never 0.** Display "8/9", or "7/8 (1 NA)".

**10 (optional, shown separately, NOT in /9). `d_trend` - daily trend up.**

- y = yesterday's regular session, and yy = the regular session before it. Both follow the holiday and
  completeness rules of points 5-7; if either is incomplete, the trend point is NA.
- **Long hit:** yH > yyH AND yL > yyL. **Short hit:** yH < yyH AND yL < yyL.

VWAP is not scored in v1.

## 3. Data (EL side)

**Root:** MNQ/NQ read NQ bars; MES/ES read ES bars.

**1-minute bars:**

- Base series: `augur_uploads/NOADJ_<ROOT>_1m_ETH.csv` (epoch seconds, bar START; columns time, open,
  high, low, close, volume, source). If the file's final row has volume 0, it is a partial bar: drop it.
- Fill from the 10-second capture, resampled to 1 minute:
  - wherever the master has no bars for ≥ 30 minutes inside 2026-06-30..2026-08-06 (the summer hole);
  - after the master's last bar.
- **Capture masters:** `augur_uploads/master_c279374a.csv` (ES) and `master_b1335b7e.csv` (NQ). They are
  stamped at bar END, so subtract 10 s. They start 2026-06-23.
- The master and the capture agree to about a tick, with equal volume, outside roll windows (checked
  2026-09-30).

**Roll handling (1m / 5m / 30m):**

- Back-adjust relative to the trade with the roll table (`augur_engine/rolls.py`, real switches):
  adjusted(t) = raw(t) + Σ offsets of switches after t − Σ offsets of switches after t_close.
- Prices at the trade stay real, and every comparison is shift-invariant.
- If a switch with status other than exact/measured lies within 3 sessions before S, add a note.

**5m / 30m bars:** resampled from the adjusted 1-minute series (label left, closed left, 24-hour).

**10-second bars:**

- From the capture, raw.
- NA before 2026-06-23 ("no 10-second data").
- NA if any real switch in the roll table lies within 48 h before t_close. The capture rolls about a day
  after the master ("near a contract roll").
- **Capture gaps (v1.1):** NA, "10-second data gap", if the capture is missing data inside the EMA's
  memory. The memory is the span from the 600th-latest 10-second bar before t_close to t_close.
  - Missing data means 3 or more 1-minute master bars with volume > 0 that have no capture bar at all.
  - Quiet minutes with no trades on either feed are not gaps; TradingView has no bars there either.
  - The scheduled 17:00-18:00 ET break and weekends are never gaps.

**Stocks:**

- 1-minute bars from the staged Alpaca loader when its keys exist, else NA with reason "no stock bars".
- The 10-second point is always NA ("no 10-second bars for stocks").

## 4. Output record (agreed with TRADING-LOG)

```
pointScore = {v: 'ps1.1', side: 'LONG'|'SHORT', signal_bar: 'YYYY-MM-DD HH:MM' (ET start), tf: '1m',
  tf_note: '1-minute default', total, max, na_count,
  points: [{k, label, hit: true|false|null, val, ref, na_reason}],   # 9 points, fixed order
  trend: {k:'d_trend', label, hit, val, ref, na_reason},              # separate, not in total
  src: 'master1m+capture10s' ...}
```

**Point keys, in order:** ma200_10s, ma200_1m, ma200_5m, ma200_30m, y_low, y_close, y_high, big_body,
big_vol.

**Labels:** "Above 200 EMA (10s)" and so on; shorts read "Below ...". Big body is "Largest body since
today's low" (short: "since today's high"), and big volume follows the same pattern.

- `val` is the compared value: C for points 1-7; the body or volume for 8-9.
- `ref` is the threshold: the EMA, the level, or the window maximum.

The writer updates only the `pointScore` field on a trade, never setup / grade / notes.

## 5. Backfill test - PRE-REGISTERED (written before any score was compared with any result)

- **Universe:** every real futures trade in EDGE LOG (read-only), through 2026-09-30.
- **Entry time:** the NinjaTrader fill log (`C:/EdgeLog/fills.csv`, UTC to ET) when it matches, else the
  setup journal's entry_time, else EL's entryTime.
- **R:** side × (exit − entry) / risk.
  - risk = |entry − stop|.
  - stop = the owner's drawn stop from `tools/data/setup_journal.json` (`drawn.stop`) when present, else
    the journal's `stop`, else the signal bar's low (long) or high (short).
  - Trades with risk ≤ 0 are excluded and listed.
  - Secondary measure: points per contract, side × (exit − entry), which needs no stop.
- **Score measure:** pct = total / max (points 1-9; the trend point is reported separately).
- **Primary:** Spearman rank correlation of pct against R, with a bootstrap 95% CI (10,000 resamples,
  seed 0).
- **Secondary:**
  - mean R and win rate (R > 0) for the top half against the bottom half by pct (median split; ties at the
    median go to the bottom half);
  - the same split for points per contract.
- **Exploratory only, flagged as nine comparisons:** per-point hit rate, and mean R when hit against when
  missed; points by time of day (09:30-09:59, 10:00-11:59, 12:00-16:00); the trend point against R.
- **Honesty:** with about 53 trades and R varying by about 1 R per trade, only a top-versus-bottom gap
  larger than about 0.55 R is distinguishable from luck. The result is a first look, not proof.
- **Check:** how often the automatic signal bar equals the journal's hand-read signal candle.

## 6. Parity test (Pine against EL) - before the owner relies on the TradingView numbers

- The owner exports chart data from a 1-minute NQ1! or ES1! chart with the indicator on it, for about 5-10
  regular sessions, and saves the CSV in `C:\EdgeLog\point_score\tv_exports\`.
- `python tools/point_score.py parity <csv> --root NQ` compares every point on every bar in the regular
  session.
- **Roll skip (v1.1):** it skips the switch day and the **15** regular sessions after each real switch. On
  an unadjusted TradingView chart the 30-minute EMA carries the roll gap for about two weeks, and
  TradingView's continuous contract also rolls a few days after ours.
- The install note tells the owner to turn on TradingView's back-adjustment for continuous futures. With
  it on, the live label matches EL straight after a roll; parity still skips those sessions, to stay safe.
- **Pass:** at least 98% of bar-points agree where both sides are non-NA, and every disagreement is within
  1 tick of its threshold or is a volume tie.
- Warm-up NA counts are reported separately.

## 7. CME equity-index holiday list (v1.1)

**Full holidays: skipped, never "yesterday".**

| Year | Dates |
|---|---|
| 2025 | 01-01, 01-09, 01-20, 02-17, 04-18, 05-26, 06-19, 07-04, 09-01, 11-27, 12-25 |
| 2026 | 01-01, 01-19, 02-16, 04-03, 05-25, 06-19, 07-03, 09-07, 11-26, 12-25 |
| 2027 | 01-01, 01-18, 02-15, 03-26, 05-31, 06-18, 07-05, 09-06, 11-25, 12-24 |

**Early close: a regular session that ends with the 13:14 bar.**

| Year | Dates |
|---|---|
| 2025 | 07-03, 11-28, 12-24 |
| 2026 | 11-27, 12-24 |
| 2027 | 11-26 |

**Rules:**

- Both implementations carry this same list.
- Extend it each December from the CME holiday calendar.
- A day missing from the list cannot produce a wrong level. Its stub fails the completeness rule, so it
  reads NA instead.
