# SCOPE - STRATEGY-BEATING lane: the stock EVENT space (2026-10-05)

Owner standing order addendum 2 (10-05 12:45 MST, via MANAGER #74): every strategy lane scopes its domain from the literature
before it queues more tests; MANAGER reviews this, then the lane works it as a queue that never drops below 3 live
pre-registrations. MANAGER named this lane's domain: **the stock EVENT space** - the house's live vein since RESMOM r1
earned in #463's drawdown days - plus insider trading (Form 4), buybacks, index inclusion and earnings dates (TV's EDGAR
calendar). Written before any number of any family below except those already on the ledger.

## What the house already knows (read first)

- **Stock edges at daily or weekly turnover are dead on costs** in 2016-25 large caps: SIPORB (2.60), ATTN (2.61), DDW r1
  (2.62), XGAP r1 (2.63) - every one a gross edge of a few bps a trade (SIPORB's under a cent a share) against a 10-15 bps
  round trip.
- **Monthly turnover survives costs, and WHERE a leg earns matters more than how much** - RESMOM r1 (10-05, this lane): standalone
  ROC @ $30k 7.1 (dead against the 15 bar), but it earns in #463's drawdown days (DO 0.160, above all 500 random books),
  so #463 + 0.264 x RES reads WF 120.8 / Sortino 3.92 and opened a forward book line (MANAGER #70).
- **NQ / ES intraday and overnight are closed for this lane** (ledger 2.12-2.19, 2.24 and later rounds): the European-open
  dealer drift, European-morning momentum, leveraged-ETF late-day continuation, the crash-regime short, a walk-forward
  xgboost direction model, ENGU-Q's short mirror, NQ vs ES relative value (SPREAD r1 / r2), REVERT, VOLCARRY, NQBRD, and
  the overnight drift after a sell-off (DD-WEEK r1 overnight, 10-05).
- **The bar for a new stock leg is now INCREMENTAL** (MANAGER #73 / #74): the book-add report compares #463 + 0.264 x RES +
  c x cell against #463 + 0.264 x RES (WF 120.82 / Sortino 3.916 / worst drawdown $36,526; RES's series pinned as
  resmom_cells_daily_wf.csv, sha256 bed7bf8b...). A new leg must help a book that already has RESMOM's drawdown help.
- **What the map says a leg must look like** (MDL r1): near-zero drawdown-week correlation -> standalone ROC ~15; a leg that
  EARNS while the book falls -> almost any positive return. So every candidate below is placed first on WHEN it should earn.

## How the candidates are judged here

For each: the mechanism and its evidence; the DATA (held = already cached and pinned; public = no-key public source,
pulled by TV / MANAGER with URL, time, size and sha256 provenance and the photograph rule; pull = Alpaca through
MANAGER's wrapper); the dead-list cross-check; the MAP placement (does the mechanism predict earning in #463's drawdown
weeks - growth / NQ sell-offs - or only a standalone return?); a rough expected size at monthly turnover in the 500 most
liquid US names (this lane's prior from the literature, written before any number - not a forecast); and whether it
duplicates RESMOM (one finding on continuation if so).

## The candidates, ranked

| # | Family | Mechanism (evidence) | Data | Map placement | Expected size | Notes |
|---|---|---|---|---|---|---|
| 1 | **DIVRUN r1** (queued, GO) | Run-up into the ex-dividend date: demand for dividends as income (Hartzmark & Solomon 2013, 2019) | held (pinned wide calendar) | standalone; payers are defensive, ES-hedged - no drawdown-week mechanism | ~15-30 bps an event before costs; ROC 8-25 | harness built; runs first |
| 2 | **EDRIFT r1** (queued, GO) | Drift after a volume-confirmed news reaction (Brandt et al. 2008; Chan 2003) | held (volume proxy for news) | continuation, like RESMOM - may earn when growth losers keep falling | drift faded in large caps (Martineau 2021); RESMOM-like ROC ~7 | correlation with RES reported; one finding if both run |
| 3 | **NEWISSUE r1** (queued, GO) | New-issues puzzle: listings underperform for 2-5 years (Ritter 1991; Loughran & Ritter 1995) | held (first cached bar) + calendar | short growth / attention names -> a drawdown-week earner if not just beta (beta <= 0.20 rule) | weak in large caps (Brav & Gompers 1997); one boom-bust | borrow 3%/yr binding |
| 4 | **NETISS** - net share issuance | Firms that issue shares underperform, firms that shrink their share count outperform, in ALL size groups (Pontiff & Woodgate 2008; Daniel & Titman 2006; Fama & French 2008 "pervasive") | public: SEC XBRL company facts (shares outstanding, dei:EntityCommonStockSharesOutstanding, quarterly) + held prices | issuers are stock-comp-heavy growth names -> short side earns in growth sell-offs (a drawdown-week earner by mechanism, like RESMOM) | one of the few anomalies documented among the largest stocks; annual rebalance in the papers, monthly here with low turnover | **top new-data candidate** |
| 5 | **SHORTINT** - days to cover | Heavily shorted stocks underperform; days-to-cover (short interest / daily volume) is the cleanest measure (Hong, Li, Ni, Scheinkman & Yan 2015; Boehmer, Huszar & Jordan 2010) | public: FINRA consolidated short interest (twice a month); 2016-25 history coverage to be confirmed by TV's catalog | crowded shorts are speculative growth -> short side earns in sell-offs; the long side (low DTC) is quality | monthly, low turnover; robust in large caps in the 2015 paper | data availability is the first question |
| 6 | **INSIDER** - opportunistic insider buys | Non-routine insider purchases predict returns; routine ones do not (Cohen, Malloy & Pomorski 2012; Lakonishok & Lee 2001) | public: SEC EDGAR Form 4 (filing index + XML), via TV's EDGAR calendar | insiders buy after sell-offs (contrarian) -> earns in the recovery legs of drawdowns | large-cap insider buys are rare; a long-only, ES-hedged basket of a few dozen names | needs the routine / opportunistic rule (3-year history of each insider) |
| 7 | **BUYBACK** - repurchase announcements and payout yield | Open-market repurchase announcements drift up for years (Ikenberry, Lakonishok & Vermaelen 1995; Peyer & Vermaelen 2009); net payout yield predicts returns (Boudoukh et al. 2007) | public: SEC XBRL (PaymentsForRepurchaseOfCommonStock, quarterly) ; announcement dates from 8-K text are messy | buyback announcements cluster after price falls (undervaluation) -> recovery-leg earner | overlaps NETISS (share count) - run as NETISS's second cell, not a separate family | fold into #4 |
| 8 | **EAP** - earnings-announcement premium | Stocks earn a premium in the days around SCHEDULED earnings releases (Frazzini & Lamont 2007; Savor & Wilson 2016; Barber et al. 2013) | public: EDGAR 8-K item 2.02 dates (TV's calendar); the NEXT date predicted from last year's same quarter (no look-ahead) | a risk premium - likely LOSES in sell-offs; standalone only | ~10-30 bps an event in large caps; event turnover is the cost question | rank by data once TV's calendar exists |
| 9 | **EDRIFT r2** | EDRIFT with true earnings dates instead of volume days | public (TV's 8-K 2.02 calendar) | as EDRIFT | as EDRIFT | only if EDRIFT r1 shows a drawdown profile |
| 10 | **MERGER-ARB** | Long announced cash-deal targets, collect the spread (Mitchell & Pulvino 2001) | public: EDGAR 8-K 1.01 / DEFM14A; deal terms need parsing | loses when deals break in crashes - wrong sign for the book | 4-8%/yr on gross; crash-shaped | low rank: wrong drawdown sign |
| 11 | **IVOL** - idiosyncratic volatility | Low-IVOL stocks beat high-IVOL stocks (Ang et al. 2006) | held | short high-IVOL growth -> sell-off earner in principle | TV's BAB r1 (dead) is its sibling; 2016-21 high-IVOL rallies | low: dead sibling |
| 12 | **SEASON** - same-month seasonality | A stock's return in a calendar month repeats in that month in later years (Heston & Sadka 2008; Keloharju et al. 2016) | held (only 1-9 annual lags exist in the cache) | none | full monthly turnover; weak with few lags | low |
| 13 | **SPINOFF** | Spin-offs and parents outperform (Cusatis, Miles & Woolridge 1993) | held (the pinned calendar: 128 spin-off rows; with stock dividends, 67 ex-dates on names ever in the universe) | none | too few events for the 60-rebalance bar | low |
| 14 | **INDEX-ADD** - S&P 500 / Nasdaq-100 inclusion | Price pressure around index changes (Shleifer 1986) - gone for the S&P 500 since 2010 (Greenwood & Sammon 2022) | held: tools/data/ndx_members.csv (point-in-time Nasdaq-100, built for NQBRD); S&P change lists public, weak provenance | none | ~30 events a year; effect largely arbitraged | low |
| 15 | **RUSSELL** - reconstitution | Stocks just inside the Russell 2000 outperform those just inside the 1000 (Chang, Hong & Liskovich 2015) | public rank lists not held; once a year | none | one rebalance a year cannot meet the bars | low |
| 16 | **RESREV** - 1-month residual reversal | Last month's residual losers rebound (Blitz et al. 2013) | held (RESMOM machinery) | losers keep losing in sell-offs (DDW r1's L1 lesson) - wrong sign | full monthly turnover | low: wrong drawdown sign |
| 17 | **52WH** - 52-week-high | Stocks near their 52-week high keep rising (George & Hwang 2004) | held | continuation - RESMOM's sibling | overlaps RES | low: one finding with RESMOM |

## The ranked queue this proposes

**Amended 2026-10-05 15:00 MST for MANAGER #80's lane split** (this lane owns stock EVENT families; FRONTIER owns
single-signal basket SEATS - stock BAB, quality sorts, seasonality - and the incremental yardstick; Custom ML owns learned
models on XBRL fundamentals) and for TV's EDGAR earnings calendar (arrived 14:29: 11,091 8-K item 2.02 releases of the 146
Nasdaq-100 members ever listed, 2004-26, sha256 09b815b7...). The table above is unchanged as the literature map; the
queue is re-cut by owner:

1. **DIVRUN r1 -> EDRIFT r1 -> NEWISSUE r1** (registered, harnesses next; each incremental over the RESMOM line, deeper
   diagnostics per the addendum). EDRIFT absorbs FRONTIER's C1 PEAD (MANAGER #80) and carries one reported check on TV's
   calendar (pre-data addendum 3: do its volume days mark earnings releases?).
2. **EAP r1** (the earnings-announcement premium on PREDICTED release dates - last year's same-quarter release + 52 weeks,
   so no look-ahead) and **EDRIFT r2** (the drift after a true 2.02 release) - Nasdaq-100 members, on TV's calendar. EAP's
   map placement is the honest risk: a risk premium can lose in sell-offs.
3. **BUYBACK r1** - repurchase and issuance EVENTS: a quarter whose reported share count falls (or rises) by more than a
   threshold, dated at the 10-Q / 10-K acceptance time (SEC XBRL company facts, public, no keys), plus 8-K announcements where
   TV's filing index tags them. The event framing of the net-issuance mechanism (Pontiff & Woodgate 2008; Ikenberry et al.
   1995); the drawdown-week story is the same (issuers are stock-comp growth names).
4. **INSIDER r1** - opportunistic Form 4 purchases (Cohen, Malloy & Pomorski 2012); TV's Form 4 pull is next; the
   routine / opportunistic rule needs each insider's history from 2013.
5. Parked, with reasons: MERGER-ARB and RESREV lose in sell-offs (wrong drawdown sign); SPINOFF, INDEX-ADD (Nasdaq-100
   additions are held in tools/data/ndx_members.csv, but the effect is arbitraged away) and RUSSELL have too few events
   for the 60-rebalance bar.

**SUPERSEDED the same afternoon by MANAGER #84 (15:19 MST, the final split - it replaces the paragraph that stood here):**
earnings is ONE family in this lane (EDRIFT r1 on volume days + EDRIFT r2 on TV's calendar + EAP, counted once); TV runs
INSIDER r1 on its Form 4 data (this lane is second reviewer; item 4 above folds into it) and the non-earnings 8-K event
drift; BUYBACK, **NETISS and SHORTINT stay in this lane as characteristic sorts on the RESMOM harness**; FRONTIER keeps
BAB / IVOL, quality, seasonality and 52WH as seats. **The live queue after DIVRUN r1 died (10-05):** EDRIFT r1 -> NEWISSUE r1
-> **NETISS r1** (draft v1 for MANAGER's review: the 1- and 2-year change in split-adjusted shares outstanding from SEC XBRL
company facts, long the 50 biggest shrinkers / short the 50 biggest issuers, monthly; TV's public pull after the GO), then
EAP / EDRIFT r2, BUYBACK events and SHORTINT.

## What every one of these will print (standing order addendum 2)

The incremental book-add report over #463 + RESMOM; the cost curve 0 / 5 / 10 / 20 bps; a row per July-June year; the
regime halves 2016-21 / 2022-25; a row per drawdown episode of the reference book; long and short sides apart; the
event-time path where there is an event; the realised beta to ES (a drawdown profile that is only beta is never credited);
the correlation with RESMOM's RES. A near-miss must say WHY it missed.

## Data asks this creates (none started; pulls are MANAGER's / TV's, never this lane's)

- **SEC XBRL company facts** (data.sec.gov/api/xbrl/companyfacts/CIK*.json) + the ticker -> CIK map
  (www.sec.gov/files/company_tickers.json): public, no keys; SEC's fair-access rule asks for a declared User-Agent and
  at most 10 requests a second - TV's scout catalog sets the house's User-Agent and provenance (the owner's contact
  details are the owner's to give, not a lane's).
- **FINRA consolidated short interest**, 2016-25, twice-monthly files: public; TV's catalog (docs/PUBLIC_DATA_CATALOG.md
  row 6) finds the public archive starts ~2018-06, so SHORTINT's walk-forward would be 2018-07 .. 2025-06 (about 84
  rebalances); it stays in this lane (MANAGER #84). SEC XBRL company facts (row 3): per-company API reachable, 2009-.
- **SEC EDGAR Form 4 index + XML** from 2013: public; the largest of the three (millions of filings); scoped by CIK of the
  ~1,900 names ever in the universe. TV's pull is next (10-05); asked for the transaction code, the filer's role, shares,
  price and acceptance time.
- **Received 10-05: TV's EDGAR earnings calendar** (C:/EdgeLog/_research_cache/edgar/earnings_calendar_ndx.csv, sha256
  09b815b7...; 39 delisted Nasdaq-100 tickers not yet mapped - asked for the 2016-25 ones first; foreign filers absent).

## Could fool us (all families)

One regime (2016-25) with one growth boom and bust (2020-22) - every growth-short family above can be that one episode,
so each carries a "net > 0 without 2022" row; the book-add uses #463's walk-forward only (its sealed year is never a pass
route - the owner's lockbox rule of 10-05); survivorship (Alpaca's inactive names only); public filings are themselves
photographs (amended filings, restated XBRL facts) - each pull is pinned by sha256 before it is read.
