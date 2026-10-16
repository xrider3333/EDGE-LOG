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

## ADDENDUM 1 (2026-10-14, before the freeze - no forward trade scored)
- **Scorer:** `tools/event_sleeve_shadow.py` (commit 398fd56c). LF sha256 `399d914f72874fe627b0142be15664f73abc1475be7e5261dc64410000462352`.
- **Constants file:** `C:\EdgeLog\event_sleeve\addendum1_constants.json` (written by `constants`, same sha inside).

**Parity** (each part rebuilt by its own source harness; WF only; no lockbox number printed):
- **A AUCTION K5:** source +$35.5k, t 1.997, 7 of 9 years -> rebuilt +$35,503, t 1.997, 7 of 9 (PF 1.25, ROC 7.9, DD $14,915).
- **B MONTH-END ES:** source 133 trades, PF 2.27, 12 of 16 years -> rebuilt 133, PF 2.27, 12 of 16.
- **C 08:30 FADE NQ:** source 210 WF trades, +$37,066, t 1.77 -> rebuilt 210, +$37,066, t 1.77.

**Measured trade rates** (2016-07-16..2025-06-30 = 8.96 years):
- **A:** 621 trades = about 69 a year. One continuous position per fund is one trade, as in the source. The "about 24 trades a year" in section 1A was wrong.
- **B:** 79 trades = about 8.8 a year.
- **C:** 209 trades = about 23.3 a year.
- **Pooled:** 909 trades = 101.5 a year, not the 55 of sections 2, 4 and 5.
- **So 50 trades come about 5.9 months after the shadow starts,** not about 2027-09. The start is the day all three feeds are approved - not yet.
- **The map prior** (MAPCHECK-F, ledger 2.138) used n = 55. With the measured rate the per-trade figures change; the yearly Sharpe prior (0.64 +- 0.30) does not.

**Frozen scale factors** (one risk unit = $1,000 of per-trade SD; trades wholly inside the stretch; sample SD):
- **A:** SD $711.19 on 621 trades -> scale 1.406090 x $50,000 per fund.
- **B:** SD $4,296.73 on 79 trades -> 0.232735 ES contracts.
- **C:** SD $1,447.99 on 209 trades -> 0.690612 NQ contracts.

**Harm bar** (section 5, recomputed at the measured rate):
- Same draws: 20,000, seed 20261011, yearly Sharpe ~ N(0.64, 0.30), t3 unit-SD noise, per-trade mean = Sharpe / sqrt(101.5).
- **CLOSE if cumulative forward P&L at 50 trades < -8.2749 risk units** (about -$8,275). At 55 a year it would have been -7.3603.

**ES cost:** 0.363 pt a round trip, per section 1B, for the constants and the forward read. The 0.533 pt of `rebal_scan.run` was used only to rebuild the source for parity. Month-end holds never cross a roll, so B's SD is the same at either cost.

**B's constants use the source's 09-24 ES cache** (`ES_daily_rth.csv`).
- The 10-14 fill of the ES master moves two 2020 closes (2020-02-28, 2020-06-30).
- On the new master B's SD is $4,087.96 - reported, not used. The forward read uses the master.

**Calendar and data notes:**
- Part C's forward days come from `tools/data/bls_dates.txt` in the shared checkout (untracked; another lane owns it). It ends 2026-12-10, and the scorer prints its path and last date.
- Over the WF it holds the same 216 release days as the source's `cpi_dates.csv` + `nfp_dates.csv`.
- The forward read applies section 6's every-bar rule. On the WF that drops one source trade, 2022-12-13 (one 1-minute bar missing).

**The clock has not started.**
- Parts A and B refuse on stale data (fund closes end 2026-09-08 / 2026-09-23; the auction calendar was fetched 2026-10-05) until the owner approves the two feeds (MANAGER #1041).
- Part C runs. The check run used `--since 2026-10-14`, so no forward trade was scored.

**Host (MANAGER #121, replaces section 6's proposal):** the owner's PC, run by Custom ML - forward / report-only, never the box.

## ADDENDUM 2 (2026-10-14, evening - before any forward trade is scored): the two forward feeds

**Owner YES**, 2026-10-14 about 17:40 MST, via MANAGER #124: "Yes, both pulls."
- **Start of the forward read:** Addendum 1 says the start is the day all three feeds are approved, so it is 2026-10-14.
- The read counts trades ENTERED after 2026-10-14 (`forward --since 2026-10-14`).
- **Sections 1-5 and Addendum 1's constants are unchanged.** This addendum changes only where the forward read gets fund prices and the auction calendar.

**Feeds:** `tools/event_sleeve_pull.py` writes only under `C:\EdgeLog\event_sleeve\fwd_data\`.
- Every pull is a new file. Nothing is overwritten.
- Each pull gets a record in `provenance.jsonl`: source, time fetched, bytes, sha256 and the tool's own hash.
- **yahoo:**
  - yfinance daily closes for SPY, TLT and IEF.
  - Adjusted with auto_adjust=True, the house convention of `build_etf_masters.py`, from 2025-06-01.
  - A session still open (before 16:30 ET) is dropped.
  - Run after each close.
- **auctions:**
  - The same Fiscal Data query as `tvnt2_triage.fetch()`, saved byte for byte.
  - Run weekly.

**How a pull is used (forward mode only; `parity` and `constants` are unchanged):**
- The research snapshots are never rewritten:
  - the yahoo_adj 1d masters for SPY and TLT;
  - `nonequity_close.csv` for IEF;
  - `treasury_auctions_raw.json`.
- **Splice:**
  - Forward prices are the snapshot through its last date L.
  - After L they are the newest pull's closes times snapshot[L] / pull[L]. So every return after L is the pull's own return.
  - If the pull has no close on L, the part refuses.
- **Acceptance:**
  - The pull is used only if its close-to-close returns agree with the snapshot's within 0.001 on at least 95% of at least 20 common days.
  - Otherwise the part refuses that day, and the share and the largest difference are printed.
- **Integrity:**
  - The newest pull's sha256 is checked again before use. A mismatch refuses its parts; there is no fallback to an older pull.
- **Staleness:**
  - Same 3-business-day rule.
  - It is read on the spliced series and on the forward calendar's fetch date.
- **Part C:** unchanged.

**Cadence:**
- Custom ML runs the pulls and the scorer from its own turns on the PC.
- No scheduled task is registered; that needs the owner's own yes.
- A missed day only delays scoring. A trade's P&L comes from the bars, never from the day the scorer runs.

**Hashes** (LF sha256; posted to MANAGER before the first forward run; witness branch `prereg/custom-ml-event-sleeve-a2`):
- Scorer `tools/event_sleeve_shadow.py`: `316c7c0925a795b4ab6cd00ce952b2ad88f0ac9d7e351d70c4a049c175a2dc92`.
- Puller `tools/event_sleeve_pull.py`: `4616219c123a4e35409c8530ee7da4b6d64c192bc733760fd2e96e561585ecd4`.
- This file's own hash after this addendum goes to MANAGER with the push.

## ADDENDUM 3 (2026-10-16, before any forward trade is scored): equal YEARLY risk per part

**Why** (MANAGER #153c, FRONTIER remap #1281):
- Addendum 1 froze equal risk PER TRADE. AUCTION K5 trades about 69 times a year, so it carried about 68% of the sleeve's yearly risk (B 9%, C 23%).
- That dropped the pooled Sharpe the map was built on. MANAGER's design intent (#94) was equal YEARLY risk per part.
- **Zero forward trades had been scored when this was frozen.** No trade is ever scored under Addendum 1's sizing. Sections 1-5 are otherwise unchanged, and so are Addendum 2's feeds.

**Rule:**
- n_p = each part's WF trade count / 8.955510 years: A 69.342785, B 8.821385, C 23.337588 a year (pooled 101.501758).
- The pooled yearly risk stays at Addendum 1's: R_pooled = $1,000 x sqrt(sum n_p) = $10,074.81.
- Each part gets an equal share: R_part = R_pooled / sqrt(3) = $5,816.69 a year.
- Per-trade risk u_p = R_part / sqrt(n_p): A $698.51, B $1,958.43, C $1,204.06 of per-trade SD.
- **New scales** = Addendum 1 scale x u_p / 1,000:
  - A 0.982174 x $50,000 per fund;
  - B 0.455795 ES;
  - C 0.831538 NQ.
- The risk unit for reading stays $1,000: forward P&L in risk units = trade P&L at the new scales / 1,000.

**Harm bar, recomputed:**
- Same 20,000 draws, seed 20261011, yearly Sharpe ~ N(0.64, 0.30), t3 unit-SD noise, 50 trades, 5th percentile.
- Each part gets an equal share of the sleeve's yearly mean, so a part-p trade's mean = S x R_pooled / (3 n_p).
- A draw's trades are assigned to parts by their trade rates.
- RNG order: Sharpes, then the t3 noise block (both exactly as in Addendum 1), then the part draws. With equal trade rates this reproduces Addendum 1's bar exactly.
- **CLOSE if the cumulative forward P&L at 50 trades < -8.0465 risk units** (Addendum 1's bar was -8.2749).

**Verification:**
- An independent blind recompute from this rule's text alone matched the code to full precision: n_p, u_p, R and the scales at relative difference 0, and the bar at -8.046525.
- It also reproduced Addendum 1's -8.2749 as a calibration.
- Drawing the part assignments before the noise would give -8.2656. That gap is Monte Carlo noise (SE of the 5th percentile about 0.11); the order above is the one that nests Addendum 1.

**Implementation:**
- `constants --addendum 3` writes `C:\EdgeLog\event_sleeve\addendum3_constants.json`. It is built only from the frozen `addendum1_constants.json` (sha b56a4e39...) and records that it supersedes it.
- `forward` now requires the Addendum 3 constants file and records its name and sha256 in `forward_status.json`.
- `parity` and the Addendum 1 `constants` path are unchanged.

**Hashes** (LF sha256; posted to MANAGER before the next scoring day; witness branch `prereg/custom-ml-event-sleeve-a3`):
- Scorer `tools/event_sleeve_shadow.py`: `50b9a0285f69a95f232d0acaae8c48a41a9cff96db93d34e23dda94acfa1a524`.
- Puller unchanged: `4616219c123a4e35409c8530ee7da4b6d64c192bc733760fd2e96e561585ecd4`.
- This file's own hash after this addendum goes to MANAGER with the push.
