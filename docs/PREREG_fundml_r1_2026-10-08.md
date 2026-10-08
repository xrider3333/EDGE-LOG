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

## Addendum 1 (2026-10-08 11:10 MST, MANAGER review #81, folded in BEFORE any power or return number)
Computed before this addendum: the coverage-only dry load (names x months with each input; no returns, no P&L).
1. SHARE COUNTS get the BUYBACK staleness rule: the share count S comes from a fact first filed on or before the
   session before t whose period end is within 15 months of t; otherwise market value is missing, and with it every
   input over price or market value (book-to-market, earnings / price, cash flow / price, sales / price, buybacks /
   MV, dividends / MV, R&D / MV) and 1-year share growth. The year-ago share count obeys the same 15 months. The
   count of names with a usable share count is printed (dry load, power line, result).
2. NULL BASIS: the 1,000-book null is GROSS and the cell is judged NET against it - deliberately conservative (the
   cell must clear the null's gross 95th after paying its own costs). The NET null's 95th is printed beside it, for
   the record only; it is not a bar.
3. SURVIVOR TILT: the symbol -> CIK map is today's, so names that died before the map was built are more often
   unmapped. The mapped share of the universe is printed by July-June WF year; if any year is under 85%, the result
   line says "universe survivor-tilted in <years>". Bar 3 (vs the twin) stays as is - both carry the same tilt.
4. MDE in own money in the power line: the null's 95th minus its 50th, in dollars a year at a $30k drawdown ($1,000
   a year per ROC point), beside the map bar ($15,000 a year), so a dead result can be told from an undecidable one.

## Addendum 2 (2026-10-08 11:35 MST, own finding while drafting DISTRESS-ML, BEFORE any power or return number)
The power run started after addendum 1 was stopped unread and discarded. Found: the harness's prices are
SPLIT-ADJUSTED to the pull date, which carries FUTURE splits back in time (1,412 symbols' closes differ from the
as-traded close by more than 0.5%).
1. MARKET VALUE: the share count is as filed (raw), so as-filed shares x a split-adjusted close understates the market
   value of every name that later split forward - future winners would have looked cheap (high book-to-market,
   earnings / price ...): look-ahead. Fixed: market value = as-filed shares x the AS-TRADED (raw) close at t
   (daily_raw.parquet, same rows as daily_split).
2. UNIVERSE FLOOR: the $5 floor on the split-adjusted close drops future forward-splitters (a later 10:1 split puts
   the past adjusted price under $5) and admits future reverse-splitters (distressed names whose as-traded price was
   under $5). Fixed for this cell: the floor is applied to the as-traded close (tools/xsml_r1.py Data(floor_raw=True);
   the default stays off, so XSML r1 reproduces unchanged). Everything else in the harness is unchanged: returns,
   dividends, features are split-invariant. The name-days that move between the two universes are printed with the
   dry load; the cell, twin and null all use the new universe. Dry load: 1,494 of 1,004,000 universe name-days
   (0.15%) move each way from July 2017 - out: future reverse-splitters (EXE / ECA, LCID, SNDL, AMC, SIRI ...); in:
   future forward-splitters (NVDA 346 days, CVNA 133 ...). Coverage unchanged (eligible median 320, mapped share
   96.5-100% by WF year, no survivor-tilt flag).
3. Reported to MANAGER as a harness finding: XSML r1 (dead) ran on the split-adjusted floor; its verdicts are not
   re-opened (the leak is in the universe both the cells and the nulls shared), and any other lane using the XSML
   universe should take floor_raw=True.

## Power line (2026-10-08, committed before `run`; fixed data per addenda 1-2; no cell or twin P&L read)
```
FUND-ML r1 POWER LINE (no cell or twin P&L read): 90 monthly WF decisions; 1,000 random beta-neutral books on the eligible names (seed 20261008).
  null (GROSS - the cell is judged NET against it, deliberately conservative): WF ROC @ $30k 50th +0.1, 95th +10.5; for the record, the NET null's 95th +1.6; DO 95th +0.207
  MDE in own money: the smallest lead over a random book this test can see is about $10,454 a year at a $30k drawdown (95th minus 50th, $1,000 a year per ROC point); the map bar (ROC 15) is $15,000 a year.
  mapped share of the universe by July-June year: 2017/18 96.5%, 2018/19 96.5%, 2019/20 98.7%, 2020/21 99.4%, 2021/22 99.7%, 2022/23 100.0%, 2023/24 100.0%, 2024/25 100.0%
  names with a usable share count (first filed before t, period end within 15 months): median 433 of 498 mapped; eligible median 320
```

## RESULT (2026-10-08 11:45 MST, Stage A, walk-forward only; lockbox never read; run-before-main #82: frozen commit
## 3226b1cf on origin prereg/custom-ml-fundml-r1, hashes matched at start) - DEAD
Full output: C:\EdgeLog\custom_ml\fundml_r1\STAGE_A.txt.
- Cell: net WF ROC @ $30k -0.2 (Sortino -0.02), gross 2.6, stress -1.4; null 95th 10.5 (net lead -10.7). WF net
  -$11,498 over 7 years on $1M a side. Worst DD $280,705, DD5 $121,695 - one episode. PF 0.998; neighbours -0.7 / -1.0.
- Years: +38k, +24k, -33k, -82k, -42k, +96k, -36k (3 of 7); halves +$70,674 / -$82,173; without the best 1% of
  name-periods -$829k. Cost curve 1.4 / -0.2 / -1.4 / -2.7 (0 / 5 / 10 / 20 bps): nothing even before costs.
- Twin (B/M + operating profitability - asset growth, for FRONTIER): net -2.0 / -0.50, worst DD $1,021,390 = DD5
  (one long drawdown). The model "beat" the twin (bar 3) only by losing less.
- Earner report: rho_dd -0.13, DO -0.097 (null 95th +0.207) - lost inside #463's drawdowns, mostly 2025.
- Mapped share 96.5-100% by WF year: no survivor-tilt flag. MDE ~$10,454/yr, so this is DEAD, not undecidable.
Bars: 1 fail, 2 fail, 3 pass, 4 (RISK) fail, 5 pass / PF fail, 6 fail. FUND-ML r1 dead, no variants. Lesson: on the
500 most liquid US names 2018-2025, filed fundamentals - learned or as the published composite - carried no monthly
cross-sectional edge; value / quality / investment lost money in this window.
