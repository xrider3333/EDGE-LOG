# PRE-REGISTRATION - NOISE on IWM, own crown, r1 (scope rank 2; MANAGER #57 / #63 / #64)

Drafted 2026-10-05 evening by the NOISE lane, before any real-direction IWM number. The only number so far is the power
line (a coin-flip version of the centre cell). Harness: `tools/noise_iwm_r1_stageA.py`, ready to launch 07:00 on
2026-10-06.

## Question
Does the NOISE mechanism (trade a break of the day's noise area, exit at VWAP) earn on the Russell 2000 cash session with
IWM's OWN settings?
- Small caps have a different holder base: more retail, less index hedging. So their trend days are not NQ's.
- This is a new family, not a transfer. TRANSFER r2 never ran NOISE on IWM; it ran ORB there, flat, ledger 2.49. ES (the
  same mechanism, re-tuned) failed its holdout (NOISE.md 2026-08-22).

## Rules (frozen)
- **Data.** IWM 5m RTH, Alpaca split-adjusted (the TRANSFER r2 master, which passed its data gates). Loaded 2016-01-04 ..
  2025-06-29 with date_to pinned. Trades counted by exit date 2016-07-01 .. 2025-06-29.
  - **Disclosed:** the day-after-a-top-5%-range filter ranks against the history available, which is short in the first
    WF months (data start 2016-01-04).
- **Strategy.**
  - NOISE_1_0.py (the full family file, not the NQ-fenced NBHD file).
  - VWAP exit, bandwidth stop, flat at the close, both sides, all day, confirm 1.
  - The crown's two banked filters stay ON: skip shorts after a weak prior close (0.2), and skip the day after a top-5%
    prior range.
- **Size and cost.** Unit = floor($100,000 / the 2016-06-30 close) = 869 shares. Cost $0.02 a share round trip, charged
  per share as traded (TRANSFER r2 addendum 2).
- **Grid (54 cells):** lookback 20 / 40 / 60 x long band 0.5 / 0.75 / 1.0 x short band 0.75 / 1.0 / 1.5 x stop 1.25 / 1.75.
  - CROWN = the best WF own ROC@$30k. The selection is disclosed and priced by the family-max null.
- **Family null.** Every cell's realised trades with the P&L sign flipped at random, 200 draws. This keeps entries, exits,
  holding and cost, and removes "trade with the break". Statistic = the family MAX own ROC@$30k.

## Stage A bars (house line #45: the standalone bars decide)
- **A1:** crown own ROC@$30k >= 15 OR the earner route; PF > 1; >= 100 trades and 50 a year; >= 6 of 9 July-June years
  positive.
- **A1b no-2020:** the same route holds without calendar 2020.
- **A2:** crown above the sign-flip family null's 95th percentile.
- **A3 plateau:** at least half of the one-step neighbours keep at least half of the crown's ROC.
- **A4 (REPORT):** book add vs #463's walk-forward. Volatility sizing is the primary, the $30k-own-drawdown sizing the
  twin, with the paired bootstrap. It decides only a forward BOOK shadow line.
- **Map row (reported):** an equity-index family needs about $40k a year at a $30k own drawdown to lift the book.

**Addendum 2 diagnostics printed on the crown:**
- H1 2016-21 vs H2 2022-25;
- longs vs shorts;
- per July-June year;
- cost curve at 0 / 5 / 10 / 20 bps round trip;
- #463's worst-drawdown dollars and without its 3 best days;
- without 2020.

## POWER LINE (written before any real-direction run)
- **Method:** coin-flip directions on the CENTRE cell (40 / 0.75 / 1.0 / 1.75): 4,264 WF trades, 474 a year. Paired
  bootstrap, block 20, 1,000 draws.
- **Volatility sizing (x0.802 units of 869 shares):** SD 8.5; minimum detectable book-add lead 14.1; four in five 21.2.
- **$30k own drawdown (x0.493 units):** SD 5.4; minimum detectable 8.9; four in five 13.5.
- (The harness prints these sizes with an "NQ" label; read them as units of 869 IWM shares.)

## What follows
- **PASS:** a pinned 900-trial Auto-Validate the same day (NOISE_1_0 on IWM 5m, alpaca_split_rth, date_from 2016-01-04,
  date_to 2026-06-30, the grid's axes as the search space). Its lockbox is the new strategy's own first look.
- **FAIL:** recorded dead, with no variants.
- **Either way:** a RUNBOARD research row (ROC@$30k and drawdown) and a ledger row.
- **Next:** the QQQ calibration (scope rank 2 after IWM, MANAGER #63).

## AMENDMENT 1 - MANAGER review (GO WITH EDITS for 07:00), 2026-10-05 ~20:40 MST, before any real-direction run
- **The two filters are INHERITED from NQ:** skip shorts after a weak prior close, and skip the day after a top-5% prior
  range. They were tuned on NQ, not IWM. A TWIN ROW prints the crown cell with both OFF. It is a report, not a bar.
- **Reported:** the share of WF sessions whose range filter had under 252 prior sessions of history (data start
  2016-01-04).
- **Per July-June year:** the trade count and the mean notional a trade, beside the per-year dollars.
- **At the crown:** trades a year, and the realised cost in bps of notional a round trip (total and median).
- Unchanged: grid, null, bars, power line.

## RESULT (run once, 2026-10-07 18:01 MST, after reading the inbox)
- **Stage A: FAIL - recorded dead, no variants.**
  - All 54 cells are negative. Crown -2.07 (20 / 1.0 / 1.0 / 1.75), 3,490 trades, PF 0.93, 3 of 9 years.
  - Family null p95 7.62.
  - Gross before cost +$7,352 (ROC 0.46).
  - Twin with both inherited filters off -3.09.
  - Book add 90.3 / 92.4 vs 93.8.
- **Timing (disclosed):** the 07:00 2026-10-06 launch was lost to the PC sleeping (22:40 - 06:12). The run happened
  when the lane reopened, per MANAGER #67, with nothing changed.
- **Post-verdict report** (MANAGER #67's day-structure check, missed before the launch):
  - single-trade sessions are 20.5% of trades and made +$83k;
  - multi-break sessions lost $136k, and the re-entries do not win back the first breaks;
  - DD5 $22,848 vs worst $85,923.
- **Records:** `tools/r37_results/noise_iwm_r1_stageA.txt`, `tools/r37_results/noise_iwm_r1_daystructure.txt`; NOISE.md
  "NOISE on IWM r1"; ledger 2.98.
