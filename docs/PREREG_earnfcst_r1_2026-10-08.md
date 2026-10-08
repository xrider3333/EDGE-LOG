# PRE-REGISTRATION (DRAFT for MANAGER) - EARN-FCST r1: a learned earnings forecaster on detailed XBRL line items (2026-10-08)

Custom ML, queue item 3 of docs/SCOPE_CUSTOM-ML_2026-10-07.md. Walk-forward ONLY; nothing filed or traded after
2025-06-29 is loaded. Computed before this draft: FUND-ML r1's and DISTRESS-ML r1's coverage-only dry loads and power
lines (no cell return of this design). FUND-ML r1's RESULT (dead, 10-08) is known and disclosed below.

## Why this, after FUND-ML r1 died
FUND-ML r1 ranked expected RETURN on 19 summary ratios and lost (net -0.2; the published composite -2.0). This cell
asks a different, narrower question with different information: from the FULL set of line items a firm files (a few
hundred us-gaap tags, not 35), will next year's earnings go UP? Chen, Cho, Dou & Lev (2022, JAR, "Fundamental analysis
of detailed financial data: a machine learning approach") train a tree ensemble on detailed XBRL items to predict the
direction of the next annual earnings change and report a long-short return the summary ratios and known factors do
not span. The model is trained on ACCOUNTING labels only (no prices), so its training set is every mapped firm-year
since XBRL began (2009-2011), not just the traded window - the house's first learned model whose training data does
not overlap the returns it is judged on.

## Boundary (STRATEGY-BEATING, inbox #83, agreed 10-08)
1. Entry and exit at calendar month-ends only; never keyed to a filing or an announcement.
2. Inputs ignore any fact first filed in the 10 sessions before the decision (EDRIFT's drift window; EDRIFT r1 is
   dead, ledger 2.85, so it is a boundary, not a live leg).
3. Twin = trailing annual earnings change (SUE-style), reported for STRATEGY-BEATING if it clears.
4. (SB's addition A) P&L split into announcement months vs other months on TV's pinned EDGAR item-2.02 calendar
   (sha256 8f4f9f4b...), and the daily P&L correlation with EAP r1's judged cell once EAP has a verdict.
5. (SB's addition B) The 14 payout / issuance concepts in tools/extract_companyfacts.py's BUYBACK maps are DROPPED from
   the inputs (so BUYBACK's P and R cells never overlap through inputs).

## Map placement (docs/MDL_MAP_R1.md)
A standalone leg: net WF ROC @ $30k >= 15 (MDE of this harness ~$10k a year). No earner-route claim (an earnings
forecast has no mechanism for #463's drawdown weeks); DO / rho_dd reported. Expected 0-6 after FUND-ML r1 - drafted
because it is the one remaining scope item that brings information FUND-ML did not have (hundreds of line items and a
non-return label), and because its training set is out-of-window by construction.

## Data (all held; one new extract, no download)
- Prices, universe, dividends, delisting: the XSML r1 harness with FUND-ML addendum 2 (raw $5 floor, as-traded market
  value), unchanged.
- NEW extract from the held companyfacts.zip (sha256 db35d36b..., never refetched; facts filed on or after 2025-06-30
  cut): every us-gaap concept in USD with an ANNUAL fact (10-K family; duration 350-380 days, or an instant at the
  fiscal year end) for the mapped CIKs. Kept: concepts present in >= 5% of mapped firm-years 2010-2017 (the list is
  fixed on 2010-2017 filings only and printed with the dry load before any number), minus the 14 BUYBACK concepts.
  tools/extract_fundamentals.py gains a --detailed mode; the 35-concept extract is untouched.
- Point in time exactly as FUND-ML: a fact counts from the session after its FIRST filing (here: first filed at least
  10 sessions before the decision); amendments never replace history; no frames API.

## The cell
- **Firm-year rows:** one per (cik, fiscal year) from its 10-K: each kept concept scaled by total assets, plus its
  change from the prior fiscal year scaled by total assets (NaN kept), plus log assets.
- **Label:** 1 if the next fiscal year's net income (NetIncomeLoss, first filed) exceeds this year's, else 0; known
  only when the next 10-K is first filed.
- **Model (registered, no search):** sklearn HistGradientBoostingClassifier, the house settings (max_iter 300,
  learning_rate 0.05, max_leaf_nodes 31, min_samples_leaf 200, l2 1.0, no early stopping, random_state 20261008).
  Refit every 1 January on every firm-year whose LABEL was first filed before that date (purged by construction);
  first refit 2018-01-01 on fiscal years 2009-2016.
- **Signal at month-end t:** for each eligible name, the model's P(increase) on its latest 10-K known at t (first filed
  >= 10 sessions before t, period end within 15 months). Eligible = universe names with a scored 10-K.
- **Rule:** long the top 50 by P(increase), short the bottom 50; BETA-NEUTRAL; hold to the next month's fill. $1M a
  side; 5 bps a side + 1%/yr borrow; stress 10 bps.
- **Plain twin (no model):** (NI this year - NI last year) / market value at t, same 10-K, same rule.
- **Null:** 1,000 random beta-neutral books on the eligible names, GROSS (cell judged NET - conservative; net null p95
  printed); power line with the MDE in dollars, eligible names by month, mapped share by WF year (FUND-ML addendum 1).

## Stage A bars (house line #45; FUND-ML r1's set)
1. Net WF ROC @ $30k >= 15 AND net > 0 at the stress cost.
2. NET WF ROC above the null's 95th percentile.
3. Beats the plain twin on net WF ROC AND Sortino.
4. RISK r1 + concentration: net > 0 without Feb-Apr 2020; >= 5 of 7 July-June WF years; both halves (2018-21,
   2022-25); without the best 1% of name-periods; without the best 5 months.
5. >= 100 name-positions and >= 26 decisions; PF of name-periods (net of a round trip) >= 1.0.
6. Neighbours (25 and 100 names a side) both net WF ROC > 0.
Reported regardless: DD5 beside every ROC (#77); the classifier's out-of-sample accuracy / AUC on the label by fiscal
year (a model that cannot forecast earnings cannot be the reason a book made money); event-time path; cost curve
0 / 5 / 10 / 20 bps; per-year and per-#463-episode rows; long vs short; beta; delisting worst cases; the 30 largest
names; the twin's row; the announcement-month split and the EAP correlation (boundary 4).

## What a result means
- A pass -> hand audit, then MANAGER: RUNBOARD research row the same day, the leg's own sealed-year veto on the one
  stock day, a forward paper shadow; book-add report over the RESMOM line L (a report, never a gate).
- A fail -> dead, ledger + memory, no variants; with FUND-ML r1 and XSML r1 dead it closes learned models on the
  liquid stock cross-section in this lane (DISTRESS-ML's earner question aside) until a new information source
  (10-K text, LAZY-PRICES, needs MANAGER's pull).
- Nothing live or in the adopted book changes.

## Priors to disclose
- FUND-ML r1 (dead 10-08): summary fundamentals, learned or plain, earned nothing on these 500 names 2018-2025.
- Chen et al. (2022) samples are all-CRSP; the edge is likely smaller in the 500 most liquid names (McLean & Pontiff
  2016: anomalies weakest there and decay after publication).
- 09-27 audit, XSML r1, FUND-ML r1: learned models here have matched or lost to plain rules every time.
- Expected: 0-6 net at $30k; most likely dead.

## Dry load (2026-10-08 12:05 MST, before any power or return number)
- Detailed extract: 17,030,068 annual-report facts, 9,011 concepts, 4,908 of 4,947 mapped CIKs (1,691,979 facts filed on
  or after 2025-06-30 cut); fundamentals_detailed_manifest.json.
- Concept list FIXED: 7,203 concepts seen in firm-year rows; 546 kept (>= 5% of the 18,194 firm-years first filed
  2010-2017) -> 1,093 features. C:\EdgeLog\custom_ml\earnfcst_r1\CONCEPTS.txt sha256 fa1dad35e3ffacf742c53d938b9284eda8674688dba240d635e4eb1cb3b30bef.
- Firm-years 42,183 (4,157 CIKs); 37,593 with a label; base rate (next year's net income higher) 0.545.
- Eligible names by month: median 411 (min 375); the twin's input finite for a median 365. Mapped share 96.5-100% by
  WF year (no survivor-tilt flag).
- Registered detail: SB boundary 4's announcement month = the month of an item-2.02 8-K on TV's calendar
  (earnings_calendar_ndx.csv, NDX names only) else of a 10-Q / 10-K first filing of NetIncomeLoss (a proxy); the split
  is of GROSS name-period P&L.

## Power line (2026-10-08, null only; no cell or twin P&L read)
```
EARN-FCST r1 POWER LINE (no cell or twin P&L read): 90 monthly WF decisions; 1,000 random beta-neutral books on the eligible names (seed 20261008); 546 concepts kept.
  null (GROSS - the cell is judged NET against it, deliberately conservative): WF ROC @ $30k 50th +0.1, 95th +9.9; for the record, the NET null's 95th +1.5; DO 95th +0.226
  MDE in own money: about $9,792 a year at a $30k drawdown (95th minus 50th); the map bar (ROC 15) is $15,000 a year.
  mapped share of the universe by July-June year: 2017/18 96.5%, 2018/19 96.5%, 2019/20 98.7%, 2020/21 99.4%, 2021/22 99.7%, 2022/23 100.0%, 2023/24 100.0%, 2024/25 100.0%
  names with a usable share count (first filed before t, period end within 15 months): median 367 of 498 mapped; eligible median 411
```

## MAP CHECK (MANAGER #84, 2026-10-08 12:30 MST) - CLOSED WITHOUT A STAGE A
tools/earnfcst_mapcheck.py: noise = 300 of the harness's random beta-neutral books on the eligible names (annualised
P&L std $72,402 on $1M a side); signal = Chen-Cho-Dou-Lev's published hedge return (5.02 / 7.38 / 9.74% a year, all
CRSP stocks) x McLean-Pontiff decay (x1 / x0.55) x a liquid-names haircut (x1 / x0.5) minus the cost row (5 bps a side
at 30% or 100% monthly turnover + 1%/yr borrow: $17,200 / $34,000 a year). Full grid: C:\EdgeLog\custom_ml\earnfcst_r1\
MAPCHECK.csv / MAPCHECK.txt.
- CENTRAL (7.38% x0.55 x0.5, 30%/mo): gross $20,295/yr vs cost $17,200/yr -> median WF ROC @ $30k +0.2, P(>= 15) 1.7%.
- ROC 15 is reached only with NO decay AND the all-stocks effect (9.74%: median 20.8; 7.38%: 12.9) - neither applies to
  liquid names in 2018-2025. Every top-500 cell of the grid has median <= 5.4 and P(>= 15) <= 13%.
MANAGER's rule (median under ~8 AND P(>= 15) under ~10%): met by the central case -> EARN-FCST r1 CLOSED, no Stage A, no
cell return ever computed. The extract (fundamentals_detailed) and the harness stay for any later use.
