# PRE-REGISTRATION DRAFT - the NOISE FADE on TLT r1 (scope A4; MANAGER #57 / #64 / #67)

Drafted 2026-10-07 evening by the NOISE lane, for MANAGER's review, before any TLT trade was run. The harness and the
power line are written after the GO and before any real-direction run.

## Question
NOISE on IEF lost hard (PF 0.61, TRANSFER r2, ledger 2.49): in bonds a break of the day's noise area REVERTS. Is that a
tradable mechanism? The test: on TLT, fade the break and take the move back to VWAP.
- **Fresh test.** IEF's number is SEEN, so IEF is tainted for this question and is reported only. TLT has never had a
  NOISE trade run on it. Disclosed: TLT's price bars were read for the habitat table (ledger 2.82: 45% trend days, cost 2%
  of the day range), and TV's new-types r2 read a different TLT mechanism (the pre-auction short).
- **Map:** bond intraday reversal is not an equity trend shape, so the leg may be uncorrelated with #463's drawdown weeks.
  Expected, if real: own ROC @ $30k 5 - 20.

## The fade, defined as the MIRROR of a NOISE trade (no new strategy code)
- Every NOISE_1_0 trade on TLT is taken in the opposite direction, with the same entry bar, exit bar and exit price.
  - A NOISE long that exits when price falls back through VWAP, or at its bandwidth stop, is a fade short that takes
    that fall as profit.
  - A NOISE long held to the close on a trend day is the fade's loss. The fade's only exit on that side is the close.
- **Fade P&L = -(NOISE gross P&L) - cost.** Cost is charged on the mirror trade as on any trade.
- This is a fade with a VWAP / band-extension target and the close as its stop. Disclosed: the loss side has no intraday
  stop. A trend day is the whole risk.

## Rules (frozen)
- **Data.** TLT 5m RTH, Alpaca split-adjusted, from the NOISE fund pull (gates passed, ledger 2.83). Loaded 2016-01-04 ..
  2025-06-29 with date_to pinned. Trades count by exit date 2016-07-01 .. 2025-06-29. The lockbox is never read.
- **Strategy underneath.** NOISE_1_0.py, VWAP exit, bandwidth stop, flat at the close, both sides, all day, confirm 1.
  - The two NQ filters are OFF. They were tuned for breaks that continue; a fade has no reason to inherit them. (This
    differs from IWM r1, on purpose.)
- **Size and cost.** Unit = floor($100,000 / TLT's 2016-06-30 close). $0.02 a share round trip as traded.
- **Grid (54 cells):** IWM r1's axes (lookback 20 / 40 / 60 x long band 0.5 / 0.75 / 1.0 x short band 0.75 / 1.0 / 1.5 x
  stop 1.25 / 1.75). The band and stop set where the fade enters and where it takes profit. CROWN = the best WF own ROC
  @ $30k of the FADE.
- **Null.** Sign flips of every cell's realised fade trades, 200 draws. Statistic = the family max fade ROC @ $30k.

## Stage A bars (house line #45)
- **A1:** crown own ROC @ $30k >= 15 OR the earner route; PF > 1; >= 100 trades and 50 a year; >= 6 of 9 July-June
  years positive.
- **A1b no-2020:** the same route holds without calendar 2020.
- **A2:** the crown is above the null's p95.
- **A3 plateau:** at least half of the one-step neighbours keep at least half of the crown's ROC.
- **A4 (REPORT):** the book add vs #463's walk-forward, with the volatility-sized primary and the $30k twin.
- **Every ROC is printed with DD5** and the one-episode flag.

## Printed before the bars
1. **IEF reported only** (tainted): the fade on IEF at the TLT crown's cell.
2. **The mechanism check.** The fade's net by NOISE exit kind:
   - VWAP exits = the reversions it is built on;
   - stops = deeper reversions;
   - holds to the close = the trend days it loses on.
   Plus the single-trade-session split (MANAGER #67).
3. **Cost and context:**
   - before-cost net;
   - realised cost in bps;
   - trades a year;
   - per-year trades and notional;
   - H1 / H2;
   - longs / shorts of the fade;
   - the cost curve at 0 / 5 / 10 / 20 bps;
   - the 2022 bond bear market alone;
   - #463's worst-drawdown dollars and without its 3 best days.

## What follows
- **PASS:** a pinned 900-trial Auto-Validate the same day. This needs a fade switch in a strategy file, written and
  parity-checked against the mirror before the validate.
- **FAIL:** recorded dead, no variants.
- **Either way:** a ledger row, a RUNBOARD research row (ROC, drawdown, DD5) and a NOISE.md section.

## AMENDMENT 1 - STRATEGY-BEATING cross-lane review #73 / #76 and MANAGER #74 / #75 (GO WITH EDITS), 2026-10-08, before any real-direction run
All edits are accepted. Where this amendment and the text above differ, this amendment rules.
1. **Null.** One random sign per SESSION per draw, shared by all 54 cells, applied to each cell's realised daily gross
   fade P&L (cost kept). 2,000 draws. The statistic is the family max.
2. **Seeds.** The power line is seeded with the fixed seed 20261006 and reproduces. The `--dry` smoke test is seeded from
   a stable digest (crc32).
3. **Ex-dividend sessions.**
   - NOISE's band uses the prior close, and the master is split-adjusted only. TLT goes ex-dividend monthly, about 12
     sessions a year.
   - REPORT: trades on ex-dividend sessions and their net, from MANAGER's Alpaca cash-dividend pull. The run stops if the
     calendar is missing.
4. **Data.**
   - The master is the SIP feed.
   - "Flat at the close" is priced at the session's last 5-minute bar's close (15:55 - 16:00; 12:55 - 13:00 on early
     closes), not the closing auction. The fade's whole loss side sits on that price.
   - The cost is the same as NOISE's ($0.02 a share). That is conservative for a fader, which supplies liquidity at the
     break.
5. **Freshness (replaces "Fresh test" above in substance).** TLT and IEF share 2016-25 and the rate path, and IEF's loss
   is what motivated this test. So Stage A on TLT is a CORRELATED re-test, not independent confirmation. A Stage A pass
   only opens the Auto-Validate: the decision rests on that validate's lockbox (the first unseen year) and a forward line.
6. **Tail** (REPORT, before the bars):
   - the 10 worst fade days, each with TLT's open-to-close move that session;
   - the fade's dollars over #463's 28 drawdown episodes (house rule >= $14,950; 460 days), and how many episodes it made
     money in. "May be uncorrelated with #463's drawdown weeks" is read from this number.
7. **Twin with the NQ filters ON** (REPORT), for symmetry with IWM r1 and the sector funds.
8. **Map row** (REPORT): the crown's dollars a year at a $30k own drawdown (ROC x $1,000) against the map's >= $15,000.

Harness: `tools/noise_tltfade_r1_stageA.py`.
- **Power line:** `tools/r37_results/noise_tltfade_r1_power.txt`. Coin-flip centre cell, 4,432 WF trades (493 a year).
  Book-add lead 5% line 17.7 at the volatility size, 5.7 at the $30k twin.
- Dividend calendar: MANAGER's pull for NOISE #613, `C:/EdgeLog/_anatomy_cache/noise_funds_r1/etf_dividends.csv` (2026-10-08 11:03, 486 rows, sha256 22776e7d354773a85eb705e34b34e2720aade7abf9da942d2e45ee31d8800621; raw pages `etf_dividends_raw.jsonl` sha256 c8a8346e90874bd3b6afac6a4e3fac0bb7393b98f17bd78e05d7fc2b84d88981). The `--dry` smoke test (coin flips everywhere, no real direction) ran the whole path clean on 2026-10-08. GO: STRATEGY-BEATING confirmed the code folds (#76); MANAGER #74 makes that confirmation plus this committed amendment the GO. Stage A runs after this commit, WF only, lockbox unread.
