# NOISE bar-size ladder (LANE A) -- EV R / R-per-year hunt, 2026-09-05

Driver: `tools/noise_ladder_hunt.py`. Pre-registration committed 2026-09-04 (`2ba5c4a`,
already on `main`). This session corrected a stale incumbent constant found at the top of
that pre-registration (see CORRECTIONS below) BEFORE the final ladder run, then ran it.

Regenerate: `EDGELOG_DATA_ROOT=<repo root> python tools/noise_ladder_hunt.py --gate` (gates
only) or `... ladder` (the full 18-cell run below).

## Parity gates -- 4/4 PASS, plus one new cross-check

| gate | result |
|---|---|
| P1 #243 card @5m selection | n 4,054 / net $320,130.25 / PF 1.4201 / DD $18,424.69 -- PASS, matches NOISE.md round 5's BASE cell to the cent |
| P1b causality (continuous run sliced == run stopped at window end) | PASS |
| P1c EV R cross-check | closed-form (mean/avg_loss) = engine's own `expectancy_r` = identity `(1-win_rate)(PF-1)` = 0.267133 on all three -- they agree exactly |
| P2 #305 best_params reproduces the saved run's IS split (75% by bars) | n 2,591 / PF 1.4240226178072 -- PASS |
| P3 #243 card @1m selection (cross-harness vs round 5's `run_variant` path) | n 9,390 / net $271,362 / PF 1.263 -- PASS |
| P4 resampler parity, 1m master -> 5m vs the registered 5m master | 317,006 / 317,044 bars identical = 99.988% -- PASS |

`#305 champion @5m` also independently reproduces the brief's stated parity target: n 3,407 /
PF 1.5403 / net 17,309.9 points ($346,198.74 at $20/pt) -- exact.

## CORRECTIONS made this session, before the final run

1. Stale incumbent bar. The committed pre-registration (`2ba5c4a`) used a cross-family
   incumbent of EV R 1.03 / R-YR 60 (an older cut of the hunt brief). This session's brief
   fixes EV R 1.070 / R-YR 92.6 (ENGU-Q #198's config) for BEATS EVERYTHING, and EV R 0.330 /
   R-YR 76.7 (run #305's own config) for PROMISING. Fixed in the driver's constants
   (`T1_EVR/T1_RYR`, `EVR_INC/RYR_INC`) before the ladder was run -- no cell's result was
   seen under the old numbers first.
2. Margin-test bug. The driver's `tier2()` had a `STRONG` branch that returned
   Auto-Validate-eligible for ANY cell positive on both axes, with no 15% margin check --
   it flagged a +12.4%/+2.2% cell as eligible. Fixed so `STRONG`/`PROMISING` both require the
   pre-registered >=15%-gain / <=15%-loss test on the correct axis pair. This changed the
   eligibility outcome (see VERDICTS).
3. Added the `1m` timeframe to the Auto-Validate queue's allow-list (`TF_END`) since 1m has
   a registered master and the brief lists it as queueable if it clears the bar (it didn't).

## THE 18 CELLS -- selection window 2010-06-07 -> 2025-02-10 (14.68 years), cost 0.533 pts x $20,
2x-cost floor $21.32/trade, source `db_noadj_rth`. MAR = (net/years)/maxDD. Nothing re-fitted.

| config | bar | n | net $ | PF | win % | maxDD $ | MAR | EV R | R/YR | +yrs | net ex10-best | EVR ex10 | R/YR ex10 | 2010-17 $ | $/trade | verdict (within-family) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| C1 #305 best | 1m | 9,142 | 283,399 | 1.264 | 31.2 | 17,573 | 1.10 | 0.181 | 113.0 | 10/16 | 205,450 | 0.132 | 81.9 | -2,190 | 31.0 | NEAR-MISS |
| C1 #305 best | 2m | 5,792 | 322,187 | 1.372 | 34.3 | 15,188 | 1.45 | 0.245 | 96.5 | 14/16 | 247,524 | 0.188 | 74.2 | 15,472 | 55.6 | NEAR-MISS |
| C1 #305 best | 3m (resamp) | 4,537 | 334,388 | 1.436 | 36.4 | 17,720 | 1.29 | 0.278 | 85.8 | 14/16 | 259,460 | 0.216 | 66.5 | 15,021 | 73.7 | NEAR-MISS |
| C1 #305 best | 5m (incumbent) | 3,407 | 346,199 | 1.540 | 38.9 | 11,615 | 2.03 | 0.330 | 76.7 | 14/16 | 276,380 | 0.264 | 61.2 | 20,669 | 101.6 | -- |
| C1 #305 best | 10m (resamp) | 2,368 | 253,258 | 1.488 | 41.8 | 14,273 | 1.21 | 0.284 | 45.8 | 13/16 | 190,564 | 0.215 | 34.5 | 21,307 | 107.0 | DEAD |
| C1 #305 best | 15m | 1,902 | 214,070 | 1.486 | 43.9 | 12,303 | 1.19 | 0.273 | 35.3 | 14/16 | 161,806 | 0.207 | 26.7 | 20,476 | 112.6 | DEAD |
| C2 #305 plateau | 1m | 3,103 | 291,797 | 1.590 | 37.1 | 10,722 | 1.85 | 0.371 | 78.4 | 13/16 | 215,584 | 0.275 | 57.9 | 22,776 | 94.0 | NEAR-MISS (+12%EVR/+2%RYR, neither >=15%) |
| C2 #305 plateau | 2m | 2,105 | 273,216 | 1.689 | 40.0 | 9,904 | 1.88 | 0.413 | 59.2 | 13/16 | 200,362 | 0.304 | 43.4 | 22,561 | 129.8 | NEAR-MISS (+25%EVR but -23%RYR, exceeds loss cap) |
| C2 #305 plateau | 3m (resamp) | 1,707 | 227,438 | 1.628 | 40.2 | 13,245 | 1.17 | 0.375 | 43.7 | 14/16 | 162,350 | 0.270 | 31.2 | 20,262 | 133.2 | NEAR-MISS (+14%EVR but -43%RYR) |
| C2 #305 plateau | 5m (incumbent) | 1,257 | 191,330 | 1.633 | 43.1 | 12,503 | 1.04 | 0.360 | 30.9 | 14/16 | 133,427 | 0.253 | 21.5 | 20,934 | 152.2 | -- |
| C2 #305 plateau | 10m (resamp) | 656 | 67,577 | 1.350 | 42.1 | 13,386 | 0.34 | 0.203 | 9.1 | 10/16 | 16,859 | 0.051 | 2.3 | 11,155 | 103.0 | DEAD |
| C2 #305 plateau | 15m | 0 trades | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | NOT MEASURABLE -- structural (see below) |
| C3 #243 card | 1m | 9,390 | 271,362 | 1.263 | 29.7 | 15,408 | 1.20 | 0.185 | 118.1 | 11/16 | 190,794 | 0.130 | 83.0 | -5,275 | 28.9 | NEAR-MISS |
| C3 #243 card | 2m | 6,329 | 316,571 | 1.354 | 32.8 | 11,569 | 1.86 | 0.237 | 102.4 | 13/16 | 236,797 | 0.178 | 76.6 | 12,105 | 50.0 | NEAR-MISS |
| C3 #243 card | 3m (resamp) | 5,149 | 325,271 | 1.390 | 33.9 | 12,323 | 1.80 | 0.257 | 90.3 | 12/16 | 246,977 | 0.196 | 68.6 | 13,776 | 63.2 | NEAR-MISS |
| C3 #243 card | 5m (incumbent, = crown #243) | 4,054 | 320,130 | 1.420 | 36.4 | 18,425 | 1.18 | 0.267 | 73.8 | 14/16 | 246,092 | 0.206 | 56.7 | 19,303 | 79.0 | -- |
| C3 #243 card | 10m (resamp) | 3,050 | 305,805 | 1.471 | 39.7 | 12,211 | 1.71 | 0.284 | 59.1 | 13/16 | 231,927 | 0.216 | 44.8 | 16,776 | 100.3 | DEAD |
| C3 #243 card | 15m | 2,536 | 306,987 | 1.533 | 41.2 | 10,524 | 1.99 | 0.314 | 54.2 | 13/16 | 236,658 | 0.243 | 41.8 | 24,033 | 121.1 | DEAD |

All 18 cells clear the $/trade >= 2x cost ($21.32) floor. Guards (n>=300, PF>=1.25, >=9 positive
years) pass everywhere except C2@10m/15m (drops below on years/trades).

## THE BAR, applied exactly as pre-registered (corrected numbers)

BEATS EVERYTHING (EV R > 1.070 AND R/YR > 92.6, both survive ex-10-best, n>=300, PF>=1.25,
>=9 positive years): zero cells. Declared unreachable in advance -- NOISE wins ~30-40% of
trades on a wide band, so EV R is structurally 0.18-0.41 across all 18 cells; no cell gets
within 3x of 1.070. This is a fact about the mechanism, not a near-miss.

PROMISING (beats the fixed NOISE incumbent, EV R 0.330 / R-YR 76.7, on ONE axis by >=15%
while losing <=15% on the other): zero cells. Every finer-than-5m cell buys R/YR by
losing MORE than 15% of EV R (1m: -45%/-44% EV R for +47%/+54% R/YR; 2m: -26%/-28% EV R for
+26%/+34% R/YR) -- the loss always exceeds the cap before the gain qualifies. Every
coarser-than-5m cell (10m, 15m) loses on both axes outright. C2's plateau pick at 1m comes
closest with +12.4% EV R / +2.2% R/YR, but neither margin reaches 15%, so it's a NEAR-MISS,
not PROMISING (a prior version of this driver's code had a bug that mislabeled this cell
"STRONG"/eligible -- fixed this session, see CORRECTIONS #2).

Net finding: EV R and R/YR trade off directly against bar size in this family, and the
trade is never cheap enough to call either direction an improvement. Finer bars buy R/YR
(more trades/year) at an EV R cost that always exceeds 15%; coarser bars buy nothing (both
axes fall). 5m remains the best-balanced point on the ladder for both configs tested.

## Confirms round 5's 1m finding independently, on a different config

C1@1m and C3@1m are both net-NEGATIVE across 2010-2017 (-$2,190 and -$5,275) and both lose
most of their edge removing the 10 best trades (EV R falls to 0.132/0.130, i.e. 40-70% of
their gross EV R came from 10 trades out of 9,100-9,400). This matches NOISE.md round 5's
"1m dies on its best 10 trades, negative pre-2018" finding -- now confirmed on #305's config
too, not just #243's.

## The 0-trade cell, explained (not a bug, not a zero)

C2 (#305 plateau) uses `window='afternoon_block'` (blocks new entries in the last 26 bars of
a session) and 15m RTH sessions are exactly 26 bars long -- so every bar is blocked and the
strategy never enters. `augur_engine.engine.run_backtest` returns `None` for this config
(no dict at all), which the driver now catches and reports as NOT MEASURABLE with the
structural reason, never a silent zero or a FAIL.

## Lockbox -- CONFIRMATORY ONLY, read once after every verdict above, never used to rank

This family's lockbox (2025-02-11 onward) has been read many times before (runs 202/203,
the 2026-08-11 gate test, #225/#231, the 2026-08-17 campaign, round 5). Ends pinned per
cell (1m/3m -> 2026-06-30 for the NQ 1m data hole; 2m -> 2026-07-16; 5m/10m -> 2026-08-12;
15m -> 2026-06-30, no cell floated). Every cell stays profitable (PF 0.94-1.44) except
C2@10m, which is barely negative (PF 0.938, -$3,354 on 59 trades) -- consistent with C2@10m
already reading DEAD on the selection window. Nothing here changes any verdict above.

## Auto-Validate

None queued. The only trigger in this lane is a non-5m cell reaching PROMISING or
better, and none did (see THE BAR). 3m and 10m have no registered master regardless
(harness-resampled only) and would not have been queueable even if they had cleared the bar.

## What was not run / caveats

- ETH (24-hour) session: out of scope for this lane (brief specifies RTH only; round 5
  already found ETH fails for #243).
- 30m/60m bar sizes: out of scope (brief's grid is 1m-15m only).
- C2's `stop_mode='atr'` and `window='afternoon_block'` are flagged by
  `augur_strategies/NOISE_1_0.py`'s own docstring as "RESEARCH-ONLY, not separately
  validated" -- this is disclosed, not a defect in this study.
- Every cell reported, including the 0-trade one -- no cell dropped or hidden after the fact.
- The "positive years" denominator is 16, not 15 (the window spans partial-2010 through
  partial-2025 = 16 calendar-year buckets), matching round 5's own convention on the
  identical window. Reported honestly rather than forced to match the brief's "15".
