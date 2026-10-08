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
