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

## AMENDMENT 1 - STRATEGY-BEATING cross-lane review #73 / #76 and MANAGER #74 / #75 (GO WITH EDITS), 2026-10-08, before any real-direction run
All edits are accepted. Where this amendment and the text above differ, this amendment rules.
1. **Null.** One random sign per SESSION per draw, shared by every cell and every fund, applied to each cell's realised
   daily gross P&L (cost kept). 2,000 draws. The statistic is the MAX own ROC @ $30k over all 378 cells.
   - This replaces "the same flips across a fund's cells" above. The first harness draft flipped each trade
     independently, which is what IWM r1 did; it is not the rule here.
   - One sign per session keeps the within-day dependence between re-entries and the correlation across cells and funds,
     so the max is calibrated.
2. **Seeds.**
   - The power lines are seeded with the fixed seed 20261006 and reproduce.
   - The `--dry` smoke test, which uses coin flips everywhere and computes no real direction, is seeded from a stable
     digest (crc32) of the cell.
3. **Ex-dividend sessions.**
   - NOISE_1_0's band uses the prior close (high bound = max(open, prior close), low bound = min(open, prior close)). The
     masters are split-adjusted only, so an ex-date moves one bound by the dividend: about 0.5 - 0.9% a quarter on XLU,
     XLP, XLF and XLV.
   - REPORT: the trades on ex-dividend sessions and their net, per fund crown. The calendar is an Alpaca cash-dividend
     pull run by MANAGER (`etf_dividends.csv`). The run stops if the calendar is missing.
   - The bound is not adjusted, because that would change the frozen strategy.
4. **Data.**
   - The masters are the SIP feed (`--feed sip`), not IEX-only.
   - "Flat at the close" exits at each session's last 5-minute bar's close: 15:55 - 16:00, and 12:55 - 13:00 on early
     closes.
5. **Disclosed.** Ledger 2.82's habitat table read these funds' price bars (trend-day share, cost against the day range).
   That read used no NOISE trade.
6. **Overlap and make-up.**
   - REPORT, beside A4: each fund crown's daily P&L correlation with NOISE #422 and with BOOK #463. XLK sits close to QQQ,
     so its crown may re-find the book's own NOISE leg.
   - Disclosed: the 2018-09 GICS change created XLC. XLK and XLY lost their internet names then, so their make-up breaks
     in the walk-forward.
7. **Constant notional.** REPORT: the crown at a constant $100k a trade, beside the fixed-share crown. XLK's notional is
   about 5x higher by 2025, so its fixed-share ROC leans on the late years.
8. **The power line is read against A2's hurdle**, the 378-cell max null's p95, not against a single fund's null.

Harness: `tools/noise_sectors_r1_stageA.py` (shared code `tools/noise_fund_r1_common.py`, which imports the IWM r1
harness unchanged).
- **Power lines:** `tools/r37_results/noise_sectors_r1_power.txt`. Coin-flip centre cell, book-add lead, 5% line at the
  volatility size / the $30k twin:

  | Fund | Vol size | $30k twin |
  |---|---|---|
  | XLK | 25.2 | 15.0 |
  | XLY | 19.1 | 4.3 |
  | XLI | 16.7 | 4.1 |
  | XLV | 17.2 | 3.1 |
  | XLP | 17.9 | 2.3 |
  | XLU | 15.8 | 3.0 |
  | XLF | 19.7 | 2.3 |

- Dividend calendar: MANAGER's pull for NOISE #613, `C:/EdgeLog/_anatomy_cache/noise_funds_r1/etf_dividends.csv` (2026-10-08 11:03, 486 rows, sha256 22776e7d354773a85eb705e34b34e2720aade7abf9da942d2e45ee31d8800621; raw pages `etf_dividends_raw.jsonl` sha256 c8a8346e90874bd3b6afac6a4e3fac0bb7393b98f17bd78e05d7fc2b84d88981). The `--dry` smoke test (coin flips everywhere, no real direction) ran the whole path clean on 2026-10-08. GO: STRATEGY-BEATING confirmed the code folds (#76); MANAGER #74 makes that confirmation plus this committed amendment the GO. Stage A runs after this commit, WF only, lockbox unread.
