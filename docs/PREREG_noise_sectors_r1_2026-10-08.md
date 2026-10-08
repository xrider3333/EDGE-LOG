# PRE-REGISTRATION DRAFT - NOISE on the sector funds r1, own crowns (scope A2; MANAGER #57 / #64 / #67)

Drafted 2026-10-07 evening by the NOISE lane, for MANAGER's review, before any sector-fund trade was run. The harness
(a copy of the IWM r1 harness with the fund as an argument) and the power lines are written after the GO and before any
real-direction run.

## Question
Does the NOISE mechanism earn on any of the seven gated SPDR sector funds with its OWN settings? The mechanism is one
break of a trend day held to the close (ledger 2.82).
- Sector moves are driven by sector news (rates for XLF and XLU, defensives for XLP and XLV), so their trend days need
  not be NQ's.
- **Prior: low.**
  - IWM r1 died (ledger 2.94): it had the trend-day break but chopped more, and it was flat before cost.
  - On QQQ the NQ settings gross about 8 bps a trade. At 2 cents a share the sector funds pay 1.8 - 6.5 bps a round trip
    (2 - 5% of their day range, ledger 2.82).
  - This round exists because the scope ranks it and its value would be a basket seat (A9). It is not expected to pass.

## Rules (frozen; IWM r1's rules, fund by fund)
- **Funds, in MANAGER #67's approved order:** XLK, XLY, XLI, XLV, XLP, XLU, XLF.
- **Data.** Each fund's 5m RTH Alpaca split-adjusted master from the NOISE fund pull (gates passed, ledger 2.83). Loaded
  2016-01-04 .. 2025-06-29 with date_to pinned. Trades count by exit date 2016-07-01 .. 2025-06-29. The lockbox is never
  read.
- **Strategy.** NOISE_1_0.py: VWAP exit, bandwidth stop, flat at the close, both sides, all day, confirm 1.
  - The two filters are INHERITED from NQ and stay ON: skip shorts after a weak prior close (0.2), and skip the day after
    a top-5% prior range.
- **Size and cost.** Unit = floor($100,000 / the fund's 2016-06-30 close). $0.02 a share round trip, charged per share
  as traded.
- **Grid per fund:** the same 54 cells as IWM. Lookback 20 / 40 / 60 x long band 0.5 / 0.75 / 1.0 x short band 0.75 /
  1.0 / 1.5 x stop 1.25 / 1.75. CROWN = the fund's best WF own ROC @ $30k.
- **Null.** Every cell's realised trades with the P&L sign flipped at random, 200 draws, the same flips across a fund's
  cells.
  - Statistic = the MAX own ROC @ $30k over ALL 378 cells (7 funds x 54).
  - This prices the choice of fund as well as the cell. Each fund's own 54-cell null p95 is printed beside it as a report.

## Stage A bars per fund (house line #45: the standalone bars decide)
- **A1:** crown own ROC @ $30k >= 15 OR the earner route; PF > 1; >= 100 trades and 50 a year; >= 6 of 9 July-June
  years positive.
- **A1b no-2020:** the same route holds without calendar 2020.
- **A2:** the crown is above the 378-cell sign-flip null's p95.
- **A3 plateau:** at least half of the one-step neighbours keep at least half of the crown's ROC.
- **A4 (REPORT):** the book add vs #463's walk-forward, volatility sizing primary and the $30k-own-drawdown twin, with
  the paired bootstrap. It decides only a forward BOOK shadow line.
- **Every ROC is printed with its DD5** and the one-episode flag (MANAGER #70).

## Printed per fund, before its bars (MANAGER #67's day-structure check first)
1. **Day structure on the crown:** the single-trade-session share of trades and its net; the multi-break sessions' net,
   split into first breaks and later breaks; NQ's 28.6% / 97.4% beside it.
2. **The IWM r1 report rows:**
   - before-cost net;
   - realised cost in bps;
   - trades a year;
   - the twin with both inherited filters off;
   - the share of WF sessions whose range filter had < 252 sessions;
   - per-year trades and notional;
   - H1 / H2, longs / shorts;
   - the cost curve at 0 / 5 / 10 / 20 bps;
   - #463's worst-drawdown dollars and without its 3 best days;
   - without 2020.

## What follows
- **PASS (any fund):** a pinned 900-trial Auto-Validate the same day for that fund (NOISE_1_0 on its 5m master,
  alpaca_split_rth, 2016-01-04 .. 2026-06-30, the grid's axes as the search space). Two passing funds open the A9 basket
  prereg.
- **FAIL:** recorded dead per fund, no variants.
- **Either way:** one ledger row, one RUNBOARD research row per fund (ROC @ $30k, drawdown, DD5) and a NOISE.md section.
- Then A4, the TLT fade.
