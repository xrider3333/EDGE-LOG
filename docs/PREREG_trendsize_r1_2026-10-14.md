# PREREG - TRENDSIZE r1: size ORB inside #463 by a pre-open trend-day score (Custom ML, 2026-10-14)

Owner 10-14 via MANAGER #114: "keep testing". Family name: **ORB** (a size tilt on ORB #234 inside BOOK #463).
This is not a re-tune of #234: entries, exits and params are untouched; only the size of each ORB trade changes, by
a rule written below before any walk-forward read.

## Why (the mechanism, and what is different)
- **ORB earns on trend days.** ORB #234 makes 119% of its walk-forward net on NQ's top-5% |close - open| days and loses on the rest (2026-10-10 power check, memory "ORB = trend-day catcher").
- **Trend days cluster with recent range.** That is volatility clustering: a run of wide sessions makes the next session more likely to be wide.
- **The open already knows the run.** ORB's own vol filter reads the same quantity, the mean range of the last 5 sessions over the median of the last 60 (`atr_filter` in ORB_3_6, stand-down at 0.7).
- **Different from the dead rows:**
  - The quiet-tape filter (memory) is a stand-down at the LOW end, measured as insurance.
  - The release-day ORB size-up (2026-09-09) was a calendar; this is a rolling state.
  - KEEL on ORB was a learned trade score, which worsened DD in every cell.
  - Here: one a-priori state, exposure-neutral by design, judged inside the book.

## Power-first (done before this file, scratch `trendday_map.py`)
- **Achievable AUC** (IS 2010-08..2016-06 ONLY; the walk-forward was not read for this) for "top-5% day":
  - 5/60 range ratio 0.726, prior-day |c - o| 0.677, |gap| / ATR20 0.579, event day 0.513.
  - A logistic fit on the first IS half scores 0.702 on the second.
- **Required skill** (walk-forward, synthetic scores only, nothing real read): a synthetic score at AUC 0.70 lifts #463 by >= 5% with Sortino held in 43% of draws. Random sizing does it in 21%, and the house map line is 30%.
- **Caveat:** a real score's misses are wide LOSING days, which a synthetic score cannot copy. So 43% is an upper bound.

## The rule (frozen)
- **Score, day t:** r_t = mean(high - low, sessions t-5..t-1) / median(high - low, sessions t-60..t-1), from the NQ RTH daily file `C:\EdgeLog\_anatomy_cache\rocfrontier\NQ_daily_rth.csv`. Prior sessions only.
- **Tilt day:** r_t >= the 80th percentile of r over sessions t-250..t-1 (prior values only; needs 250 prior values).
- **Size of an ORB #234 trade, by its ENTRY day's row in the #463 book:** 2.0 on a tilt day, 0.75 otherwise. A row with no score (holiday, warm-up) is 1.0. ENGU-Q, TTM and NOISE stay 1.0.
- **Book:** #463 from r11's cache (`R11.load_book("U", build.json legs)`), refused unless WF 93.81 / Sortino 3.816 reproduce. The tilt multiplies the ORB leg's own entry-row matrix (Book.Am_leg[0]), so every day's mark follows its trade's entry size.

## The bar - WALK-FORWARD ONLY (2016-07-01..2025-06-29); the lockbox is never read for the tilted book
PASS needs all of:
1. **Book lift:** #463 WF ROC @ $30k >= 1.05 x the plain book's, AND Sortino >= the plain book's.
2. **Beats chance:** the real lift (ROC) is above the 95th percentile of 1,000 within-year shuffles of the tilt-day flags (same count per year; seed 20261014).
3. **Beats flat leverage:** the tilted book's ROC beats the plain book with ORB scaled uniformly to the tilt's realised mean ORB size.
4. **Years:** the ORB leg's tilted-minus-plain dollars are positive in >= 6 of the 9 July-to-June WF years (2016-17 .. 2024-25).
5. **Not one episode:** the lift holds (tilted ROC >= plain ROC) with 2020-02-01..2020-04-30 removed, and no single day is more than 50% of the tilted-minus-plain dollars.

**Reported (never a pass route):**
- **Four house numbers** for plain and tilted: ROC @ $30k, DD5, DD % from peak (`augur_engine.drawdowns.dd_pct_peak`, $100k start) and Sortino.
- **Tilt days:** share, and the tilt days' share of trend days.
- **The ORB leg on its own:** plain vs tilted ROC.

## What happens next
- **PASS:** a vol-sized book-add REPORT, then a forward shadow (BOOK LOOKS r1: the lockbox is spent for book candidates). MANAGER and the owner decide; nothing live changes from Stage A.
- **FAIL:** the row is closed in the ledger. No re-tune of the 80th percentile, the 2.0 / 0.75 sizes or the windows.
- **Book look:** this Stage A is ONE book look (a real daily series added to #463). It is posted to MANAGER for the tally.
- **Run-before-main (MANAGER #82):** this file and the harness `tools/trendsize_r1_stageA.py` are pushed as `prereg/custom-ml-trendsize`. Their LF sha256s go to MANAGER, and the harness refuses to run unless they match.
