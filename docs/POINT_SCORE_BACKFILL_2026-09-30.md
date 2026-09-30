# POINT SCORE backfill - result (2026-09-30)

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
  - The 10-second point is NA on 39 trades: there is no 10-second data before 2026-06-23, one trade sits
    near a roll, and one minute had no 10-second bar.

## Pre-registered answers

- **Primary: score against R, rank correlation +0.03** (95% CI -0.25 to +0.31). Against points per
  contract it is +0.09 (CI -0.19 to +0.35). **No relationship.**
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
- **Trend point (not in the nine):** hit on 23 trades, +0.27 against +0.07.
- **Above yesterday's close:** hit on 34 trades, +0.09 against +0.28 when below. This runs the other way.
- **Time of day:** 09:30-09:59 had mean R +0.27 (21 trades), 10:00-11:59 +0.04 (13), and 12:00-16:00
  +0.12 (19).
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
