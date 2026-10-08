# SCOPE - CUSTOM ML, 2026-10-07 (standing order addendum 2, MANAGER #71; assessment #76 b; lane split #72 / #84)

Late: due 10-06 (this chat sat idle 10-05 evening to 10-07). Draft for MANAGER review; nothing below is computed.

## The domain, and what is already known about it
Custom ML owns LEARNED models on the US stock cross-section, including fundamentals from SEC XBRL company facts
(#72; STRATEGY-BEATING's scope doc says the same). FRONTIER owns the plain single-signal basket seats (BAB / low vol,
gross profitability / quality, seasonality, 52-week high, MAX, reversal, asset growth, value) and STRATEGY-BEATING the
stock EVENT families (EDRIFT / PEAD, NETISS, SHORTINT, INSIDER via TV, BUYBACK, spin-offs, index adds). So every cell here
is a learned model whose TWIN is the plain sort the literature (and usually FRONTIER's table) would trade; if the twin
wins and the model does not, the twin goes to FRONTIER as evidence, not to this lane.

What the house already knows:
- 09-27 ML edge audit and MANAGER's 10-05 assessment: learned models on NQ / ES bar features are a coin flip at matched
  risk (26 of 52; no sized arm aims in both stretches). The two things that worked were NEW INFORMATION turned into a
  FIXED rule (the Fed calendar; the hourly squeeze, +5.2 inside the book). Fundamentals are new information for this
  house; the question is whether a learned combination beats the fixed published one.
- XSML r1 (this lane, running 10-07) is the price-only learned-signal test on the same universe and harness; its
  verdict sets the prior for "learned beats plain" on stocks here.
- RESMOM (STRATEGY-BEATING): residual momentum is dead standalone (ROC 7.1 vs 15) but #463 + 0.264 x RES reads WF 120.8
  - the book-add bar for any new stock cell is now INCREMENTAL over that line (L: WF 120.82, Sortino 3.916, worst DD
  $36,526).
- Published fundamental anomalies lose about half their return after publication (McLean & Pontiff 2016) and are
  weakest in the largest, most liquid names - this universe. Expectation is modest everywhere below.

## Data (held unless marked)
- **Prices:** Alpaca SIP dailies 2016-01..2026-06 (siporb daily_split, inactive names kept), the XSML harness (top-500
  by 20-day dollar volume, split-flag quarantine, dividends from the wide corporate-actions file, delisting worst case).
- **Fundamentals:** companyfacts.zip, one curl 2026-10-05, 1,410,049,978 bytes, sha256 db35d36b...765c (every us-gaap
  and dei tag for every filer; XBRL from 2009, all filers by 2011). The house extractor (tools/extract_companyfacts.py)
  pulls only three share-count concepts today; this lane EXTENDS it (new CONCEPTS list, same as-filed rows) - no new
  download.
- **Point in time:** one row per fact per filing (cik, concept, start, end, val, accn, form, filed). A value is known
  from the session AFTER its first `filed` date: take min(filed) per (cik, concept, start, end); amended forms
  (10-K/A, 10-Q/A) and later re-filings never overwrite history. Frames (last-filed only) are NOT used. Facts filed on or
  after 2025-06-30 are cut.
- **Mapping:** symbol -> CIK for 4,992 of 5,367 SIPORB-floor symbols (93%; reviewed additions included); an unmapped
  name has no fundamentals and is out of these cells' universe (bias reported: mapped vs unmapped returns).
- **Needs a MANAGER pull (public, no key):** SEC submissions JSON for the ~4,950 mapped CIKs (SIC industry code,
  fiscal-year end, former names) - industry-relative inputs and the fiscal-calendar join. Later only: 10-K / 10-Q
  full text for cell 7.

## Rules every cell keeps
Walk-forward only (positions exited 2018-01..2025-06-29; refit every January on data filed before it, purged); one
registered model config (sklearn HistGradientBoosting, XSML's settings) - no search; power line first (matched-risk
shuffle of random books with the cell's own rule, committed before any number); the plain-sort twin; house line #45
(standalone bars decide: net WF ROC @ $30k >= 15 or the earner route, net above the shuffle's 95th, beat the twin, PF,
counts, breadth, no-2020, best-1% / best-5, neighbours); DD5 beside every ROC (#77); the incremental book-add REPORT
over L. Diagnostics every Stage A prints (addendum 2 (2)): event-time path (returns by month since rebalance), regime
halves 2016-21 / 2022-25, cost curve 0 / 5 / 10 / 20 bps, per-year and per-#463-episode rows, long vs short leg, beta to
ES, top-30 name audit list.

## Mechanism space (ranked)

| # | Mechanism (literature) | Data | Dead-list / owner cross-check | Map placement | Expected (own WF ROC @ $30k) |
|---|---|---|---|---|---|
| 1 | **FUND-ML** - a learned ranker on ~25 point-in-time characteristics: value (B/M, E/P, CF/P), profitability (ROE, gross profits / assets, operating profitability), investment (asset growth, capex growth), accruals, net issuance, leverage, plus the XSML price set; monthly, long top 50 / short bottom 50, beta-neutral. Gu, Kelly & Xiu 2020; Freyberger, Neuhierl & Weber 2020; Hou, Xue & Zhang 2015 (q-factors); Fama & French 2015 | H (extract extension) | No dead family trades fundamentals. Twin = the equal-weight rank composite of value + profitability + investment (the FF5 / HXZ plain sort) - FRONTIER's B6 / B8 / B9 territory, so the twin's numbers go to FRONTIER | Standalone >= 15 needed; value / profitability L/S earned in 2022 (a #463 drawdown year) - DO and rho_dd printed | 3-10; the learned gain over the composite is the question |
| 2 | **DISTRESS-ML** - learned probability of a fundamental failure (next-12-month bottom-2% return or delisting) from leverage, profitability, cash, size, volatility, price level; short the likely failures, long the safest, beta-neutral, monthly. Campbell, Hilscher & Szilagyi 2008; Ohlson 1980; Asness, Frazzini & Pedersen 2019 (quality minus junk) | H | XSML cell C is the PRICE-only crash model (no fundamentals); this adds the balance sheet. Twin = CHS's published logit coefficients, no learning (or Altman Z if a CHS input is missing) | The EARNER route: junk falls hardest in sell-offs; aimed at #463's drawdown weeks (DO above its null's 95th, rho_dd <= -0.15) | 0-8 standalone; the earner route is the point |
| 3 | **EARN-FCST** - learned forecast of next fiscal-year earnings change from detailed XBRL line items (hundreds of tags, scaled), long predicted increases / short decreases, rebalanced monthly from the latest filing. Chen, Cho, Dou & Lev 2022 (ML on detailed financial data); Novy-Marx 2015 (fundamental momentum) | H | STRATEGY-BEATING's EDRIFT is the POST-announcement drift event; this is a forecast ranking held through the cycle, entry never keyed to an announcement. Boundary agreed with SB before drafting. Twin = trailing earnings-change (SUE-style) sort | Standalone | 2-8 |
| 4 | INTANGIBLE-VALUE - learned value with R&D and SG&A capitalised. Eisfeldt, Kim & Papanikolaou 2022; Peters & Taylor 2017 | H | Value (FRONTIER B9, unowned) plain twin | Standalone; value earned in 2022 | 0-6 |
| 5 | ACCRUAL-QUALITY - learned earnings-quality score (accruals, Dechow-Dichev residual, cash conversion). Sloan 1996 | H | Folded into 1 as inputs unless 1 shows accruals carry it | Standalone | 0-5 |
| 6 | INDUSTRY-RELATIVE - cells 1-3 with industry-relative inputs (rank within SIC group). Moskowitz & Grinblatt 1999; GKX's industry effects | M (submissions pull) | Variant of 1-3, registered only if 1-3 show any lift | Same as parent | +0-2 on the parent |
| 7 | LAZY-PRICES - year-over-year similarity of 10-K / 10-Q text; firms whose filings change most underperform. Cohen, Malloy & Nguyen 2020 | M (full-text pull, large) | No text signal in the house | Standalone, slow (quarterly) | 2-8 historically; post-publication decay |
| 8 | FACTOR-TIMING - learned timing of 3-5 fundamental factor portfolios from their valuation spreads. Haddad, Kozak & Santosh 2020 | H | Few independent bets (monthly x 5 factors) - low power; RISK r1-type risk timing died | Earner if it de-risks before sell-offs | Power too low to judge; forward-shadow material |
| 9 | SHORTINT-ML - learned use of short interest with fundamentals. Rapach, Ringgenberg & Zhou 2016 | H (FINRA from 2018-06) | SB owns SHORTINT as a sort; data starts 2018 = forward-shadow material per the catalog | Standalone | Not judgeable on 2018-2025 alone |
| 10 | DIVIDEND-SAFETY - learned dividend-cut probability from payout and cash flow | H | SB's DIVRUN is dead; event-adjacent | Earner-ish | Low |
| 11 | FUND-PRICE INTERACTION - fundamentals x XSML price set (does the learned model find interactions the twin cannot?) | H | Inside cell 1 by design | - | Part of 1 |
| 12 | GROWTH-QUALITY on NDX names only (EDGAR calendar, 176 firms) - learned model on the NQ universe; a stock-side twin of the NQ legs | H | NQBRD (breadth timing NQ) dead; this is cross-sectional | Probably falls with #463 (NQ beta) - map says no unless beta-neutral | Low |

## Ranked queue (never below three live preregs)
1. **FUND-ML** - prereg draft next (after the extractor extension and a coverage-only dry load: names x months with
   each input, no return read).
2. **DISTRESS-ML** - the drawdown-week earner candidate; prereg drafted beside 1 (shares the extractor).
3. **EARN-FCST** - after a boundary note with STRATEGY-BEATING (EDRIFT) so the two never trade the same thing.
Then 4 / 7 (7 needs the pull) / 6 (needs submissions). 8, 9, 10, 12 are parked as low-power or out of lane.

## Pull list for MANAGER
- SEC submissions JSON for the mapped CIKs (SIC, fiscal-year end, former names): ~4,950 requests, public, photograph
  rule, cut 2025-06-30. Needed for 6 and for the fiscal-calendar join in 3; 1 and 2 do not need it.
- (Later, only if 1-3 show any learned lift) 10-K / 10-Q primary documents for cell 7.

## What would change this plan / could fool us
- XSML r1's verdict: if every learned price cell loses to its twin, the prior that a learned fundamentals model beats
  the plain composite drops further - 1 then runs as registered but 3 waits.
- Look-ahead through restatements or the frames API (never used); fiscal-period mislabelling (fy / fp) - every input is
  dated by `filed`, never by period end.
- Survivorship through the CIK map (unmapped names are disproportionately small or delisted) - reported.
- One episode: value's 2022 rally could make a value-tilted cell look like a drawdown-week earner from one year - the
  per-episode rows and DD5 are there for that.

## RESULTS 2026-10-08 - the queue is exhausted
| # | Item | Outcome |
|---|---|---|
| 1 | FUND-ML r1 | DEAD at Stage A: net WF ROC -0.2 (gross 2.6 vs null 95th 10.5); FF5/HXZ twin -2.0. |
| 2 | DISTRESS-ML r1 | DEAD at Stage A: net -0.8; DO +0.086, no earner route; AUC 0.60-0.82 but shorting likely crashers lost. CHS twin -1.2 (DO +0.41). |
| 3 | EARN-FCST r1 | CLOSED by MANAGER #84's map check, no Stage A: central median ROC +0.2, P(>= 15) 1.7%. |
| 7 | LAZY-PRICES | CLOSED by the same map check BEFORE any pull: CMN 2020 value-weighted hedge 0.34-0.55%/month, post-publication x0.42, cost $17,200/yr -> central median +0.5, P(>= 15) 1.7%; even with NO decay the best cell is median +10.3 (P 32%). MAPCHECK_LAZY.txt. |
| 4 | INTANGIBLE-VALUE | Closed: a value variant; FUND-ML r1's value composite lost in this window (twin -2.0). |
| 5, 11 | ACCRUAL-QUALITY, FUND-PRICE | Were inside item 1 (dead). |
| 6 | INDUSTRY-RELATIVE | Closed: registered only if 1-3 showed lift; none did. |
| 8, 9, 10, 12 | FACTOR-TIMING, SHORTINT-ML, DIVIDEND-SAFETY, GROWTH-QUALITY | Parked as before (low power / forward-only / map says no). |
Lessons: (1) on the 500 most liquid US names 2018-2025, filed fundamentals - learned or the published composite - carried
no monthly cross-sectional edge after costs; (2) a monthly 50/50 beta-neutral book costs ~$17k a year (5 bps + 1%/yr
borrow) against random-book noise of ~$72k a year - the published, decayed, large-cap effect sizes of every stock
anomaly in this scope sit below that; (3) the map check (literature effect x decay x liquid haircut - costs on the
harness's own random-book noise; tools/earnfcst_mapcheck.py) is the cheap first step for any further stock idea;
(4) split-adjusted prices leak future splits into any price LEVEL - FUND-ML addendum 2.
