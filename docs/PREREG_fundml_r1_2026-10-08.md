# PRE-REGISTRATION (DRAFT for MANAGER) - FUND-ML r1: a learned ranker on point-in-time XBRL fundamentals (2026-10-08)

Custom ML, queue item 1 of docs/SCOPE_CUSTOM-ML_2026-10-07.md (standing order addendum 2; MANAGER #71 / #76 b).
Walk-forward ONLY; nothing filed or traded after 2025-06-29 is loaded. Computed before this draft: nothing on returns -
only the extract's row counts (fundamentals_manifest.json) and, before any number, a coverage-only dry load (names x
months with each input).

## Why this, after XSML r1 died
XSML r1 (ledger 2.97): a learned ranker on daily PRICE / volume characteristics had gross information (12.7 vs the
shuffle's 10.3) that weekly turnover and costs ate, and it lost to the plain reversal + momentum twin. Two lessons go
straight into this design: trade LESS (monthly, beta-neutral) and feed the model NEW information (the balance sheet,
income and cash flow as filed), not re-cut prices. MANAGER's 10-05 assessment: the only things that ever worked in
this house were new information turned into a rule - here the learned model must beat the plain published rule.

## Dead-list / owner cross-check
- No dead family trades fundamentals (ledger section 2). XSML r1 (price-only learned ranker, dead) - this adds the
  filings and trades monthly. RESMOM (residual momentum, dead standalone; the book line L).
- FRONTIER owns the plain sorts (B6 gross profitability / quality, B8 asset growth, B9 value) - the TWIN here is the
  composite of exactly those; its numbers are reported for FRONTIER, never claimed by this lane.
- STRATEGY-BEATING owns NETISS (net issuance) and the event families - issuance enters only as one input here.

## Map placement
A new standalone leg: net WF ROC @ $30k >= 15, or the earner route (DO above its null's 95th AND rho_dd <= -0.15).
Value and profitability long/short books earned in 2022 (a #463 drawdown year), so DO / rho_dd are printed beside
the result; the book-add report is incremental over the RESMOM line L (house line #45 - a report, never a gate).

## Data (all held)
- Prices, universe, dividends, split quarantine, delisting worst case: the XSML r1 harness unchanged (Alpaca SIP
  dailies, top 500 by 20-day median dollar volume, close >= $5, >= 260 sessions; corporate-actions file sha256
  e5bc8487...).
- Fundamentals: C:\EdgeLog\_research_cache\xbrl_companyfacts\fundamentals_asfiled\ (tools/extract_fundamentals.py
  from companyfacts.zip sha256 db35d36b...; 35 us-gaap concepts; one row per fact x filing; facts filed on or after
  2025-06-30 cut). Share counts: shares_asfiled_wide.csv (dei:EntityCommonStockSharesOutstanding first).
- Symbol -> CIK: the reviewed map (4,992 of 5,367 SIPORB-floor symbols). A universe name with no CIK or no usable
  filing is OUT of this cell's universe (the mapped share of the universe is printed by month).

## Point in time (the rule that matters most)
- A fact's value is known from the session AFTER its FIRST filing: take min(filed) per (cik, concept, start, end);
  a fact counts at decision date t only if that first-filed date is <= the session before t (an after-close filing on
  t is not used at t). Amendments and later re-filings never replace what was first filed. The frames API is never
  used.
- FLOWS (revenue, costs, income, cash flow): the latest ANNUAL fact (duration 350-380 days, form 10-K / 10-K/A / 20-F /
  40-F) known at t; stale beyond 15 months = missing. STOCKS (balance sheet): the latest instant fact known at t from
  any form; stale beyond 9 months = missing. Prior-year values for growth inputs: the annual fact whose period ends
  330-400 days before the current one.
- Market value = price at t's close x the latest dei:EntityCommonStockSharesOutstanding known at t (else
  us-gaap:CommonStockSharesOutstanding).
- Concept fallbacks, fixed now: revenue = Revenues, else RevenueFromContractWithCustomerExcludingAssessedTax, else
  SalesRevenueNet; cost of revenue = CostOfRevenue, else CostOfGoodsAndServicesSold; equity = StockholdersEquity, else
  the noncontrolling-inclusive tag; debt = LongTermDebt, else LongTermDebtNoncurrent.

## The cell
- **Inputs (cross-sectional ranks in [-0.5, 0.5], NaN kept; 24):** book-to-market, earnings / price, operating cash
  flow / price, sales / price; ROE, gross profit / assets (Novy-Marx), operating profitability (FF: revenue - COGS -
  SG&A - interest, over equity), ROA; asset growth, capex / assets; accruals ((net income - operating cash flow) /
  assets); 1-year share growth, buybacks / market value, dividends / market value; liabilities / assets, current
  ratio, cash / assets; R&D / market value, SG&A / assets; and from XSML's price set momentum 252..21, return over
  21, volatility 63, 252-day beta, log dollar volume.
- **Model (registered, no search):** sklearn HistGradientBoostingRegressor with XSML's settings (max_iter 300,
  learning_rate 0.05, max_leaf_nodes 31, min_samples_leaf 200, l2 1.0, no early stopping, random_state 20261008);
  target = cross-sectional rank of the 21-session total return from t+1 open; refit every 1 January on decisions whose
  target ended before it (purged). First refit 2018-01-01.
- **Rule:** decisions at each month's last close; long the top 50, short the bottom 50 of the eligible names;
  BETA-NEUTRAL (XSML cell C's scaling); hold to the next month's fill. $1M a side; 5 bps a side + 1%/yr borrow; stress
  10 bps.
- **Plain twin (no model):** the equal-weight average rank of book-to-market, operating profitability and minus asset
  growth (the FF5 / HXZ composite), same rule.
- **Null:** 1,000 random beta-neutral books on the same eligible names, same rule, gross; power line printed and
  committed first, with the twin's and the cell's eligible-name counts by month.

## Stage A bars (house line #45; XSML r1's set)
1. Net WF ROC @ $30k >= 15 (or the earner route) AND net > 0 at the stress cost.
2. NET WF ROC above the shuffle's 95th percentile.
3. Beats the plain twin on net WF ROC AND Sortino.
4. RISK r1 + concentration: net > 0 without Feb-Apr 2020; >= 5 of 7 July-June WF years; both halves (2018-21,
   2022-25); without the best 1% of name-periods; without the best 5 months.
5. >= 100 name-positions and >= 26 decisions; PF of name-periods (net of a round trip) >= 1.0.
6. Neighbours (25 and 100 names a side) both net WF ROC > 0.
Reported regardless (standing order addendum 2 (2)): DD5 beside every ROC (#77); event-time path (P&L by sessions
since the fill); cost curve 0 / 5 / 10 / 20 bps; per-year and per-#463-episode rows; long vs short legs; beta to ES;
the delisting worst case; the 30 largest single-name contributors; the twin's full row; the mapped share of the
universe; the book-add report over L.

## What a result means
- A pass -> hand audit of the 30 names, then MANAGER: RUNBOARD research row the same day, the leg's own sealed-year
  veto on the one stock day, a forward paper shadow; the basket cannot run as an EDGELOG engine job.
- A fail -> dead, ledger + memory, no variants. If the TWIN clears bars 1-2 and the model does not, the twin's row goes
  to FRONTIER as evidence for its B6 / B8 / B9 seats.
- Nothing live or in the adopted book changes.

## Priors to disclose
- 09-27 audit and XSML r1: learned models here have matched or lost to plain rules every time so far.
- McLean & Pontiff (2016): published anomalies lose about half their return after publication; effects are weakest
  in the most liquid names. Value lost 2017-2020 and rallied 2021-22; one regime may dominate (DD5 and halves are there
  for that).
- Expected: 3-10 net at $30k standalone; the learned lift over the composite is the open question.
