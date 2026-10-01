# POINT SCORE backfill - result (2026-09-30)

## Correction 2026-10-01 (spec v1.1)

A review on 2026-09-30 found rules the first spec did not cover, and the scorer now follows spec v1.1
(`ps1.1`, `docs/POINT_SCORE_SPEC.md`). The pre-registered test, its rules and its trades are unchanged. The
backfill and `point_score_rtest.py` were re-run, and the numbers below are the new run. **The conclusion does
not change: no relationship.**

- **What changed in the scorer:**
  - "Yesterday" must be a complete regular session (last bar 15:59, or 13:14 on a listed early close). If it is
    not, the three "above yesterday's" points and the trend point are NA ("prior session incomplete"). The day
    is not skipped.
  - CME holidays on the spec's list are never "yesterday", even when Globex printed a short stub that day.
  - The 10-second point is NA ("10-second data gap") when the capture lost 3 or more minutes the master traded,
    inside the EMA's 600-bar memory.
- **Scores that moved (two trades of 53):**
  - 2026-07-27 MES long (nt_14595752270): **3/9 became 1/6**. The 07-24 capture stops at 10:46, so the three
    "above yesterday's" points (old: low hit, close hit, high miss) and the trend point (old: miss) are now
    NA instead of reading the 10:46 close as the session close.
  - 2026-09-30 MNQ long, signal 11:51 (nt_198843932160): **6/8 became 7/9**. This is new data, not the code: the
    10-second capture file now holds that minute, which had not been imported at the first run, so the
    10-second point is a hit (old: NA, "no 10-second bar in the signal minute"). The old scorer gives the same
    7/9 on today's data.
  - The holiday rule and the capture-gap rule moved no backfill score: no trade sits on a day after a holiday
    stub, and none has a 10-second capture gap in its window.
- **Numbers that moved (old to new):**
  - Primary rank correlation: +0.033 (CI -0.247 to +0.310) to **+0.029 (CI -0.248 to +0.306)**.
  - Against points per contract: +0.087 (CI -0.192 to +0.354) to +0.083 (CI -0.193 to +0.347).
  - Top against bottom half: unchanged (23 and 30 trades, +0.147 against +0.164 R, median 62.5%).
  - 10-second point NA: 39 trades to 38.
  - Above yesterday's low: 43 hits to 42, with 1 NA. Close: 34 hits to 33, with 1 NA. High: 24 hits, 29 misses
    to 28 misses, with 1 NA.
  - Trend point: 23 hits (mean R +0.27, unchanged), 30 misses (+0.072) to 29 misses (+0.074), 0 NA to 1 NA.
  - Time of day (review finding 5): the old "09:30-09:59" group also held two trades whose signal bar is outside
    09:30-16:00 (08:29 pre-market and 09:29). They now form their own group. 09:30-09:59 went from 21 trades
    (+0.27) to 19 trades (+0.26); the outside group is 2 trades (+0.31).

This is the pre-registered test in `docs/POINT_SCORE_SPEC.md` section 5, committed on main (9b7c89b9)
before any score was compared with any result. It was run exactly as written:

1. `python tools/point_score.py backfill` wrote `C:\EdgeLog\point_score\backfill_scores.csv`. That file
   holds scores only, and no outcomes were read while writing it.
2. `python tools/point_score_rtest.py` then computed the outcomes.

## Trades

- **53 real futures trades** from EDGE LOG, 2026-04-07 to 2026-09-30. All 53 were used; none had
  zero risk.
- **Entry fill source:**
  - 16 from the NinjaTrader fill log (exact seconds);
  - 37 from the setup journal's checked entry minute.
- **Stop source:**
  - 31 are the owner's drawn stop;
  - 15 are the journal's stop;
  - 7 are the signal bar's low or high.
- **R before fees:** mean +0.156, median +0.125, spread (sd) 0.49.
- **Scores:**
  - median 62.5% of the available points;
  - nine of nine on two trades.
  - The 10-second point is NA on 38 trades: there is no 10-second data before 2026-06-23 (37 trades), and one
    trade sits near a roll.
  - The "above yesterday's" points and the trend point are NA on one trade (2026-07-27: the prior session is
    incomplete).

## Pre-registered answers

- **Primary: score against R, rank correlation +0.03** (95% CI -0.25 to +0.31). Against points per
  contract it is +0.08 (CI -0.19 to +0.35). **No relationship.**
- **Secondary: top half against bottom half** (median split at 62.5%):

  | Half | Trades | Mean R | Win rate | Points per contract |
  |---|---|---|---|---|
  | Top | 23 | +0.147 | 78% | +1.45 |
  | Bottom | 30 | +0.164 | 77% | +2.18 |

  - The gap is -0.02 R, give or take 0.26 R at 95%.
  - **No difference:** any real gap is smaller than about 0.26 R either way.

## Exploratory only

These are nine comparisons with small groups, so about one "difference" appears by luck.

- **Largest body:** hit on 13 trades, mean R +0.24 against +0.12 when missed.
- **Largest volume:** hit on 13 trades, +0.28 against +0.11.
- **Trend point (not in the nine):** hit on 23 trades, +0.27 against +0.07 when missed (one trade NA).
- **Above yesterday's close:** hit on 33 trades, +0.09 against +0.28 when below (one trade NA). This runs the
  other way.
- **Time of day:** 09:30-09:59 had mean R +0.26 (19 trades), 10:00-11:59 +0.04 (13), and 12:00-16:00
  +0.12 (19). Two trades with a signal bar outside 09:30-16:00 are their own group (+0.31).
- None of these is evidence; they are leads to watch as trades accumulate.

## Check: the signal candle

- On 25 of 46 journal trades, the automatic signal bar is the candle the owner marked.
- On 19 he marked the minute he entered in, the one still forming when he bought (he fills on 5-10
  second charts).
- Scoring that forming candle would read its close, body and volume after his fill. That is part of the
  trade's own result, so the pre-registered rule (last CLOSED bar) is the honest one.

## Reading

On the owner's 53 real trades, a higher point score did not go with better results. With R this
tightly spread, a gap bigger than about a quarter of an R would have shown.

The score still does its other jobs:

- ranking trades by how the context looked;
- the live TradingView label;
- annotating algo signals.

It should not be read as a trade filter yet. The record grows every week, and the test can be re-run on
the same pre-registered rules whenever the owner wants.
