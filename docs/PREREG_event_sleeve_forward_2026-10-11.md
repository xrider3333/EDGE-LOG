# PREREG - EVENT SLEEVE, forward shadow only (Custom ML, 2026-10-11)

MANAGER #94 (a) GO: "draft the FORWARD-SHADOW prereg (calendars, K=5, equal risk per part and the bar frozen NOW,
no orders, judged on post-freeze trades only; say the expected date to 50 trades)". Origin: MAPCHECK-F r1
(ledger 2.138) - the only parked idea that clears the map (P(lift #463, WF) 56% on its prior).
Family name: **EVENT SLEEVE** (one leg, three calendar parts).

## Why forward only
All three parts were already run on the walk-forward years:
- ES month-end is ledger 2.18, and its lockbox columns were printed.
- AUCTION K5 is 2.70.
- The 08:30 fade mirror is 2.95. That row says "a fade is NOT proposed from this ... judged forward".

A history test of the pooled sleeve would only re-add numbers already seen. So nothing in this file reads any trade
before the freeze, except to fix the sizing constants (section 3), which are a scale and never a verdict.

What is different from the dead rows: those were judged as single legs on history. This judges the three, pooled as
one leg with a frozen equal-risk weight, on trades that have not happened yet.

## 1. The three parts (rules copied from their source preregs, unchanged)
**A. AUCTION K5** (docs/TV_NEWTYPES_R2.md section 1, the K = 5 cell exactly as tested - both funds, both halves, no picking of
the half that carried it):
- **Calendar:** every Treasury NOTE and BOND auction (no bills, TIPS or FRNs). 5-, 7- and 10-year auctions trade IEF; 20- and 30-year auctions trade TLT.
- **Short leg:** SHORT the fund from the close of t-6 to the close of auction day t.
- **Long leg:** LONG from the close of t to the close of t+5.
- **Announcement rule:** an auction is usable only if announced on or before the session whose close opens the short; otherwise the short opens at the first close on or after the announcement.
- **Overlaps:** short beats long; one position per fund.
- **Early closes:** an auction is skipped when any session of its window is an early close.
- **Cost:** as in the source prereg.
- **Notional:** the source used $50,000 per fund; here it is rescaled by section 3.
- **About 24 trades a year.**

**B. MONTH-END ES** (tools/rocfrontier/rebal_scan.py, ledger 2.18's cell ES, K = 5, threshold 2%):
- **Spread:** at the RTH close 5 trading days before the month's last trading day, spread = month-to-date return of SPY minus month-to-date return of TLT. Both are measured from the prior month's last close (Yahoo adjusted daily).
- **Position:** if |spread| >= 2%, take -sign(spread) in ES, entered at that close.
- **Exit:** at the close of the month's last trading day.
- **Roll:** the roll seam is removed from P&L as in the source.
- **Cost:** 0.363 pt per round trip (house ES).
- **About 8 trades a year.**

**C. 08:30 FADE on NQ** (docs/PREREG_orb_newtypes_r1_2026-10-05.md NT1, the fade MIRROR of the "every release day" NQ cell):
- **Days:** CPI and payrolls release days at 08:30 ET (`tools/data/bls_dates.txt`; a day with any other release time is skipped).
- **Signal:** m = close of the 08:34 bar / close of the 08:29 bar - 1 (house 1-minute ETH bars, START-stamped, Eastern).
- **Trade:** enter at the open of the 08:35 bar AGAINST m; exit at the close of the 09:59 bar.
- **Cost:** 0.533 pt.
- **About 23 trades a year.**

## 2. One leg
The three parts' trades are pooled into one daily P&L series, about 55 trades a year. A day's P&L is the sum of the
parts' marked-to-market P&L.

## 3. Equal risk per part (frozen constants, set ONCE before the first forward trade)
- **Scaling:** each part is scaled so that its per-trade P&L standard deviation over its OWN walk-forward trades (2016-07-16..2025-06-30, the stretch its source row already read) equals ONE RISK UNIT = $1,000. This is a scale, not a fit: no rule, threshold or K changes.
- **Constants:** the three scale factors and the trade counts behind them are printed by the scorer (section 6). They are posted with the scorer's LF sha256 as ADDENDUM 1 before the freeze date. They never change after that.
- **No orders,** so sizes stay fractional (no whole-contract rounding).

## 4. Freeze and the forward window
- **FREEZE** = the push of this file (prereg/custom-ml-event-sleeve on origin) plus Addendum 1.
- **Window:** only trades whose ENTRY is after the freeze date count.
- **Expected count:** about 55 trades a year. With a shadow start of about **2026-10-19**, 50 trades lands about **2027-09** (the month-end and auction calendars are lumpy, so +-6 weeks).
- **Power, said plainly:**
  - The map prior is a yearly Sharpe of 0.64 +- 0.30. After one year of trades the expected t is about 0.6. Reaching t 2 needs roughly ten years.
  - **This forward test cannot confirm an edge on any horizon we care about. It can catch a broken one.** The bar below is built for that.

## 5. The bar (frozen now)
- **Harm read at 50 trades (about 2027-09):** CLOSE the sleeve if its cumulative forward P&L in risk units sits in the
  bottom 5% of the prior-predictive distribution of a 50-trade sleeve.
  - The distribution is built from MAPCHECK-F's prior: Sharpe 0.64 +- 0.30, t3 tails, 55 trades a year; 20,000 draws, seed 20261011.
  - The threshold is printed by the scorer in Addendum 1.
  - Above it: continue, and nothing is adopted.
- **Interim:** at every 10 trades, the four house numbers are reported. Same read, no decision before 50 trades. Exception: a single-part break (a part's calendar or data feed failing), which is fixed and logged, never re-tuned.
- **Promotion review, not before 165 trades (about 3 years):** the forward yearly Sharpe t >= 1.0 AND a positive vol-sized book-add REPORT on #463 (BOOK LOOKS r1). Then MANAGER and the owner decide. Until then the sleeve is a shadow and nothing live or in the book changes.
- **Every read carries the four numbers** (MANAGER #95): ROC %/yr at $30k DD, DD5, DD % from peak and Sortino, on the forward stretch only.
- **Book looks:**
  - Synthetic priors are not book looks.
  - **The forward series added to #463 is ONE book look per read** (FRONTIER #92); each read is posted to MANAGER for the tally first.

## 6. Scorer and host
- **Scorer:** `tools/event_sleeve_shadow.py` (Custom ML builds it). It reads house data only and writes C:\EdgeLog\event_sleeve\forward_*.csv plus one daily P&L file. No orders, no broker.
  - Inputs: TLT / IEF / SPY Yahoo daily masters, the ES and NQ RTH masters, and NQ 1-minute ETH bars.
- **Host proposal: PAPER-NT8.**
  - Two of the three parts are CME futures.
  - The 08:30 part needs NQ bars from 08:29 to 09:59 ET, which the NT8 capture records and Webull cannot.
  - The fund part needs only daily closes, which both hosts have.
  - PAPER-NT8 runs the scorer nightly after its EOD checks; Custom ML reads and reports.
- **Data the forward run needs that we do not hold yet (each needs the owner's yes, via MANAGER, before the freeze):**
  - **Treasury auction calendar:** the cached file (sha256 75e2f5e3...) ends with auctions announced by 2026-10-08. Forward use needs a weekly read of the same public fiscaldata.treasury.gov query (announcements come about 6 days ahead).
  - **BLS 2027 schedule:** `bls_dates.txt` ends 2026-12-10. The 2027 schedule must be added before then, or part C stops trading in 2027 (logged, not silently).
- **1-minute ETH bars:** the house 1-minute data has a known hole ([1m hole]). The scorer refuses a release day whose 08:29-09:59 bars are incomplete and counts it as skipped. A skipped day is never filled from another source after the fact.

## 7. What would void this
- Any change to sections 1-5 after the freeze voids the forward read up to that date. The read restarts at the change, with a dated addendum.
- Any look at pre-freeze sleeve P&L beyond the section-3 scale is reported as a breach.
