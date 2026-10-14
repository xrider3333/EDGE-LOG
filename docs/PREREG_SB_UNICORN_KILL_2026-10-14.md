# UNICORN KILL TEST 10-14 - arXiv 2511.12490 ("13-Sharpe drift-regime factor") replicated on our daily stocks (STRATEGY-BEATING)

**Why this runs (MANAGER #172, owner 10-14):** the owner asked for the paper to be assessed. MANAGER's read
(`C:\EdgeLog\manager\papers\arxiv_2511_12490\ASSESSMENT.md`) says it is not real as stated. This is the cheap kill test: rebuild
the factor as the paper defines it, then remove its advantages one at a time. It is a kill test, not a candidate. Nothing here
can enter the book. Written before any run; harness `tools/rocfrontier/r31_unicorn_kill_1014.py`.

## Survivorship bias, stated first
- We hold no S&P 500 list, and the owner said no new data on 10-12.
- **Universe U (the paper's kind):** the 500 largest US common stocks by mean dollar volume (raw close x volume) over the last
  63 sessions of our data (to 2026-06-30). Only names still trading at that date can qualify. Kept: exchanges NASDAQ / NYSE /
  AMEX / ARCA / BATS. Dropped: names containing "Depositary" or "ADR".
  - This list is chosen with hindsight, exactly as the paper's "current constituents" are. It is biased in the same direction.
  - Each name enters on the day its data begins.
- **Control universe P (report only, the survivorship check):** each day, the 500 largest of ALL the common stocks we hold by
  mean dollar volume over the 63 sessions BEFORE that day. Our Alpaca set keeps names that later stopped trading (1,457 inactive),
  so P has no hindsight in its membership.

## Data
- Alpaca SIP daily bars, `C:\EdgeLog\alpaca_cache\siporb\daily_raw.parquet` and `daily_split.parquet`, 2016-01-04 .. 2026-06-30.
- Returns use split-adjusted prices. Dividends are not in the data; long and short sides both miss them.
- The session calendar is every date on which at least 1,000 of our stocks have a bar.
- A held name with no bar at the end of its holding period earns 0 for that period (no delisting return is held). This
  matters only for P.
- "Mean dollar volume over 63 sessions" needs all 63 sessions present.

## The factor, as the paper defines it (section 2.1)
- **Value:** cross-sectional percentile rank (0..1) of 1 / RAW close on day t. Raw price is the price that day; a split-adjusted
  price would rank on future splits.
- **Reversal:** cross-sectional z-score of minus the 10-day split-adjusted return (close t / close t-10 - 1).
- **BASE** = 0.7 x value + 0.3 x reversal.
- **Regime:** the share of up days (split-adjusted close-to-close return > 0) over days t-1 .. t-63 (paper eq. 2, 63 valid
  returns required) is above 0.60.
- **EDGE** = BASE x regime. Active names = regime on and BASE known.
- **Portfolio:** z-score EDGE across the active names. Long the names above zero, short those below. Weights in proportion to
  |z|, longs summing to 50% and shorts to 50% of a $100,000 account. Rebalanced every session.
- **Left out:** the paper's volatility scaling (one constant; it cannot change Sharpe, ROC @ $30k or Sortino) and its kill
  switch (a path overlay). Both are stated as omitted, not tuned.
- **Cost:** a cost in basis points is charged on every unit traded: the sum over names of |target weight - weight carried in
  from the day before after its own move|.

## Cells
| Cell | Fill | Cost a unit traded | Universe |
|---|---|---|---|
| (a) as published | close t (the signal's own close) | 0.6 bp | U |
| (b) next-open fill | open t+1, held to open t+2 | 0.6 bp | U |
| (c) | close t | 5 bp | U |
| (d) | close t | 10 bp | U |
| (e) | open t+1 | 10 bp | U |
| (f) report only | close t | 0.6 bp | P (no hindsight) |
| (g) report only | close t, but value ranks a SPLIT-ADJUSTED price (as a default Yahoo pull would) | 0.6 bp | U |

## Reported per cell and stretch
- **Stretches:** WF 2016-07-01 .. 2025-06-29 (the house stretch; the first 63 sessions are warm-up), and AFTER
  2025-06-30 .. 2026-06-30 apart. Also each calendar year's Sharpe.
- **Four numbers:** ROC @ $30k, DD5 (one-episode flag), DD % from peak, Sortino. All from `seat_pipeline.figures` and
  `drawdowns.dd_pct_peak` on the daily dollar P&L.
- **Also:** annual Sharpe (daily mean / sd x sqrt 252), net a year, mean daily turnover (units traded / account), active names
  a day, longs / shorts a day.
- **Context:** the equal-weight buy-and-hold of the universe, same stretches.
- **Fragility check on (a) and (b):** the 5 largest single stock-day P&L figures, and the share of net from the top 20 stock-days.
  A bad print would show up here. No return is filtered.

## How it is read (fixed now)
- If (a) gives a large Sharpe and (b) / (c) / (d) / (e) bring it near zero or below, the paper is explained by same-close fills and
  costs, even with the survivorship bias left in its favour.
- If (f) falls well below (a), the survivor list is part of the paper's number.
- If (b) at 10 bp, cell (e), keeps WF ROC @ $30k at 15 or above with a Sortino above 1, it is NOT dead. That would go back to
  MANAGER as a separate, pre-registered question (point-in-time universe, borrow costs). It would not be a book add.
- A Sharpe of 13 is not expected under any cell.
