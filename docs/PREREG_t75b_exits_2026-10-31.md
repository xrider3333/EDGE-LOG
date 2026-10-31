# PREREG - TEST 75 PHASE B: trailing / breakeven exits on NOISE #382 and ORB #314 (2026-10-31)

Owner ask (MANAGER #146, 10-31): "such an MFE coming back to clap us is unacceptable". Phase A
(`tools/t75_phaseA_exits.py`, v73.1449 44adbea1) built 10 exit variants on the two live trades that gave
back. That was in-sample idea generation on two trades chosen BECAUSE they gave back. This file is the test.
NOISE runs its half; ORB runs the ORB #314 half on this same file, with the same rules and reading rule.

## What is already settled (not re-tested here)
- **Giveback stop** (exit after giving back X% of MFE once MFE >= Y R): test 74, 0 of 9 cells lift NOISE.
- **Scale-out** (bank F at T, hold the rest): test 75 first scope, 0 of 30 cells lift NOISE.
- **VWAP-cross exit:** NOISE #382 already exits on a close across VWAP. For ORB it is a new rule, but Phase A
  lost money on the ORB trade. Left out.

## The 5 variants (chosen by mechanism family, NOT by Phase A rank)
Phase A ranked the time-decay trail first and the 6-bar trail last. The 6-bar trail is kept anyway because
it is the one structure-based trail (swing lows/highs, no volatility input). Two trades cannot rank anything.
Parameters are the Phase A ones, unchanged. ATR is on the leg's own bars: NQ 5m for NOISE, the ORB leg's own
master for ORB.

| # | Variant | Family | Rule (long; a short mirrors it) |
|---|---|---|---|
| E1 | ATR trail 3 x 14 | volatility trail from the close | stop = best close since entry - 3 x ATR(14) |
| E2 | Chandelier 3 x 22 | volatility trail from the extreme | stop = highest high since entry - 3 x ATR(22) |
| E3 | 6-bar trail | structure trail | stop = lowest low of the last 6 closed bars |
| E4 | Time-decay ATR trail | trail that tightens into the close | stop = best close - k x ATR(14), k = max(1, 3 x minutes to 16:00 / 390) |
| E5 | Breakeven at 1R + 2 x ATR trail | breakeven then trail | nothing until MFE >= 1R; then stop = max(entry, best close - 2 x ATR(14)) |

R = the entry's own protective-stop distance (the engine's `levels.risk`).

## Execution rules (no look-ahead)
- **Updates:** every level is computed on a bar's CLOSE and acts from the NEXT bar.
  - If the next bar opens through the level, the fill is that bar's open.
  - Otherwise, if the bar touches the level, the fill is the level.
- **First bar:** the overlay never acts on the entry bar.
- **Leg's own exit:** it always applies, whichever comes first. On the leg's exit bar the overlay acts only
  when the leg's exit is not at that bar's open.
- **Stop and trail on the same bar:** if a bar touches both the leg's stop and the overlay level, take the
  worse fill for the trade.
- **Size and cost:** the leg's size tilt and per-trade cost are kept. Pts = size x (raw - cost), the same as
  hold. The overlay adds no extra commission: one exit either way.

## Data and stretches
- **Trades:** the crowned config, with the run's own champion parameters for NOISE #382, run ONCE over
  2010-06-07 .. 2025-07-15 (the optimize end).
- **Lockbox:** 2025-07-16 .. 2026-07-16. It is NEVER loaded; the master is cut at the optimize end. Nothing
  after the lockbox is used.
- **IS:** trades whose decision day is 2010-06-07 .. 2021-12-31.
- **OOS:** 2022-01-01 .. 2025-07-15.
- The entry parameters were tuned on part of this window. That affects hold and every variant alike, and the
  comparison is overlay vs hold on the same trades.
- **Second line, for continuity with test 74 and the first t75 scope:** the same overlay on the #382 WF chain
  (2016-10..2025-07), the same trade rebuild, the same caveat (about 0.5% off the stored chain).
- **Folds:** the calendar years of each stretch. A fold is won when the variant nets more than hold.

## Numbers per variant per stretch
ROC@$30k, DD5, DD% from peak, Sortino (`augur_engine.drawdowns.four_numbers` on daily $), net, worst DD,
folds won. Also per stretch:
- **MFE captured:** sum of raw over trades with MFE > 0, divided by sum of their MFE.
- **Median giveback:** MFE minus final, in R.
- **Trades changed:** how many trades the overlay closes differently from hold.

## Reading rule (fixed now)
A variant LIFTS a leg only if, on the OOS stretch, ALL of these hold:
1. **ROC and Sortino:** it beats hold on ROC@30k AND on Sortino.
2. **Folds:** it wins at least 60% of the OOS years (3 of 4 with 2022, 2023, 2024 and part of 2025).
3. **Not one episode:** worst DD <= 1.3 x DD5, or the same flag as hold.
4. **Same direction in IS:** it also beats hold on IS ROC@30k.

The OOS stretch carries the verdict. IS only confirms direction. Five variants are tried, so one passing
needs care: a pass with the other four failing is reported as "1 of 5, check for chance". The prior is
about 15%, given tests 74 and 75 (scale-out) found nothing.

## Not done
No re-tuning of any parameter. No variant added after the numbers. Nothing live changes on a pass. A pass
goes to the owner as a proposal for a forward shadow, not a switch.
