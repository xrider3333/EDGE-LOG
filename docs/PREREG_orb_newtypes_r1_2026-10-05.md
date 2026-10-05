# PRE-REGISTRATION — ORB lane NEW STRATEGY TYPES r1 (2026-10-05)

Owner standing-order addendum 10-05 (MANAGER inbox #36): ORB's family is used up (rounds 64 and 65 dead), so the lane hunts
NEW strategy types from theory, on data already held, Stage A walk-forward only, 60-minute review rule. Written before any
number of these three exists. Family name for all three: **MISC** (house vocabulary), research ids NT1 / NT2 / NT3.

## What is already dead nearby (RESEARCH_LEDGER), and what is different here

- Dead: closing-auction reversal (2.41, real but under cost), late-day leveraged-ETF momentum (2.14), European-morning
  momentum (2.15), overnight dealer drift (2.13, tiny), failed-high fade (2.38), weekend gap, FOMC-cycle weeks and
  mega-cap earnings nights (2.33), month-end pension rebalancing (2.18, real but small), NQ/ES spreads (2.24, 2.45), NQ-100
  breadth (2.48), crown transfer to funds (2.49), the event-size scan (CPI/NFP/FOMC as SIZE multipliers on existing legs:
  a noise list), TV's daily fade (dead 10-05).
- **The house lesson that shapes all three:** intraday NQ/ES edges have been real but smaller than the 0.53 / 0.36-point
  round trip. So each type below either trades bigger moves (announcements, stress days) or a cheaper instrument (funds).
- What is different, one line each:
  - **NT1** trades the scheduled-news reaction itself, through the cash open. Nothing in the ledger trades the release.
  - **NT2** is a premium, long on announcement days only, against a random-day null. The event scan only re-sized
    existing legs on those days.
  - **NT3** is a cross-asset leg on bond and gold funds, triggered by equity stress. The ledger has no intraday
    safe-haven leg; TREND r1 / Q9 is monthly trend.

## Shared rules (all three)

- **Stage A only** (walk-forward 2016-07-01..2025-06-29). The lockbox stays sealed; the calendars end 2025-06.
- **#463 reproduction first:** 93.81 / 3.816 / $44,849, or nothing runs. Its drawdown days are #463's walk-forward
  valued-daily drawdown episodes at least $14,950 deep (MDL r1 / DD-WEEK definitions).
- **Yardstick:** ROC %/yr at a $30k worst drawdown valued daily, the unified convention.
- **Stage A pass, per cell, needs ALL of:**
  - (a) >= 100 WF trades;
  - (b) the map: own WF ROC @ $30k >= 15, OR >= 5 with (h) passing (the drawdown-week earner route);
  - (c) profit factor >= 1.05;
  - (d) per-trade t >= 2.0 AND above the family null's 95th percentile of the max t over the family's cells;
  - (e) net > 0 at the stress cost;
  - (f) profitable without its single best day;
  - (g) positive in >= 6 of the 9 July-June WF years;
  - (h) for the (b) earner route only: summed P&L over #463's drawdown days > 0, still > 0 without its 3 best days there,
    AND above the family null's 95th percentile;
  - (i) net > 0 without 2020-02-15..2020-04-30;
  - (j) the 2010-06..2016-06 block net > 0 where data exist (NT3's fund bars start in 2016: stated, not checked);
  - (k) **A2:** #463 + the cell at c in {0.5, 1, 2} (the best c frozen) reaches WF ROC >= 98.50 with Sortino >= 3.816.
- **A pass** goes to a pinned Auto-Validate the same day (900 trials, pinned date_from/date_to: its own first lockbox
  look, allowed for a new standalone strategy under the 10-05 addendum), then to the RUNBOARD with ROC @ $30k and DD%.
  A book add is judged forward only.
- **A fail** = the ledger and ORB.md, with no variant tried in its place.

## NT1 — MACRO830: the 08:30 release reaction carried into the cash open (NQ, ES)

- **Mechanism.** At 08:30 ET (CPI, payrolls) the futures react while the cash market is shut. The pre-open crowd is
  thin, mostly dealers and fast traders who keep inventory light, so the first reaction is incomplete. Institutional
  capital that trades at the cash open finishes the adjustment (slow-moving capital, Duffie 2010; institutions trade at
  the open, Lou, Polk & Skouras 2019). **Prediction: continuation from 08:35 to 10:00.** The fade is the control.
- **Days:** `tools/data/cpi_dates.csv` and `nfp_dates.csv` (BLS schedules; dates with a different release time are
  skipped). This gives about 24 trades a year.
- **Signal:** m = close of the 08:34 bar / close of the 08:29 bar - 1 (house 1-minute ETH masters, bars stamped at the
  START, Eastern). Enter at the open of the 08:35 bar in the direction of m; exit at the close of the 09:59 bar.
- **Cells (4):** market {NQ, ES} x {every release day; only |m| >= the median |m| of the previous 24 release days}.
- **Cost:** NQ 0.533 pt, ES 0.363 pt a round trip; stress +0.25 pt.
- **Null:** a fair coin for the side on the same days (shared across a market's cells), 500 reps, seed 20261005.
  Reported: the fade mirror.
- **Map:** about 24 trades a year. 2022's CPI days were among #463's falling weeks, so the earner route is plausible if
  continuation holds both ways.

## NT2 — ANNPREM: the macro-announcement-day premium (NQ, ES)

- **Mechanism.** Investors demand a premium for bearing scheduled macro-news risk, so the equity premium concentrates on
  announcement days (Savor & Wilson 2013, JFQA; Ai & Bansal 2018, Econometrica; Lucca & Moench 2015 for FOMC).
  **Prediction: long the index from the prior 16:00 close to the announcement day's 16:00 close earns more than on
  ordinary days.**
- **Days:** CPI + payrolls + scheduled FOMC decision days (`fomc_dates.txt`, the canonical file), about 32 a year.
- **Trade:** long 1 contract, the prior session's 15:55-bar close to the day's 15:55-bar close (house 5-minute RTH masters,
  roll-corrected; `rolls.is_trustworthy()` checked).
- **Cells (4):** market {NQ, ES} x {all three types; CPI + payrolls only}.
- **Null: random-day, family-wide.** Each rep replaces the announcement days with the same number of random
  non-announcement sessions per year, scored the same way, max over cells. This removes plain market drift: the leg must
  beat being long on ordinary days, not just be long.
- **Map, stated honestly.** It is long beta on about 13% of sessions, so it is likely to LOSE in #463's falling weeks
  (2022's CPI days fell hard). The earner route is unlikely and it must clear the 15 %/yr route on its own.
  Post-publication decay is documented. My prior is weak. It is drafted because it is the canonical literature effect on
  our own instruments and the house has never tested it. **If MANAGER judges it fails the map, I drop it** and draft a
  replacement.

## NT3 — SAFEHAVEN: intraday flight to quality on equity-stress days (IEF, GLD)

- **Mechanism.** When equities fall sharply, investors move into Treasuries and gold, and the moves persist through the
  session (flights to safety, Baele, Bekaert, Inghelbrecht & Wei 2020, RFS). Prediction: on days the equity market is
  already stressed by 10:30, long IEF or GLD from 10:30 to the close earns, by construction on the book's bad days.
- **Trigger:** ES return from the prior 16:00 close to 10:30 <= -k x its median |same window| over the previous 60
  sessions (house ES 5-minute RTH master).
- **Trade:** long $100,000 of the fund at the 10:30 bar's open, out at the 15:55 bar's close (Alpaca 5-minute bars,
  split-adjusted, 2016-01..2026-06). An intraday hold is untouched by dividends.
- **Cells (4):** fund {IEF, GLD} x k {1, 2}.
- **Cost:** 2 bp a side; stress 5 bp.
- **Null: random-day.** Same count of random non-trigger sessions per year, same trade, 500 reps, max over cells.
- **Map:** it trades only on stress days, so it is built for the earner route (b + h).
- **Known enemies, stated now:** the March 2020 "dash for cash" (Treasuries and gold were sold, 2020-03-09..18) and
  2022's positive stock-bond correlation (bonds fell with stocks). If (h) fails because of them, the mechanism failed
  where the book needs it, and that is the answer.
- **Not checked:** (j), since there are no fund bars before 2016. Q9 (FRONTIER's monthly fund trend) uses some of the
  same funds; the mechanism and horizon differ, and overlap is reported.

## Power and order

- NT1 has about 220 WF trades, NT2 about 290, and NT3 depends on k (roughly 150-500).
- Run order: NT1, NT3, NT2. NT2 runs last and is dropped first if MANAGER says it fails the map.
- Tools: `tools/orb_nt1_macro830.py`, `orb_nt2_annprem.py`, `orb_nt3_safehaven.py`, written after this draft and run from
  the shared checkout.
- Results: `ORB_NEWTYPES_R1.md` plus the ledger.

## Addendum 1 — MANAGER review (inbox #39, `C:/EdgeLog/manager/reviews/orb_newtypes_r1_review_2026-10-05.md`), folded in before any number

- **NT2 ANNPREM is DROPPED on the map.** It is long beta on the book's worst days, so it cannot be a seat, and one bad CPI
  day eats its drawdown. No number was read. A replacement is due with the next queue.
- **Edit 1, clock.**
  - The 1-minute ETH masters are stamped at the bar START. The loader doc says so, and on 2022-09-13 the CPI jump sits
    in the bar labelled 08:30, while the 08:29 bar closes before the release. NT1's 08:34 bar is complete at 08:35:00,
    so entry at the 08:35 bar's open is strictly after the signal.
  - NT3 reads ES at the 10:25 bar's close and fills the fund at the **10:35 bar's OPEN** (not 10:30).
- **Edit 2, points.** NT1's m and its median-|m| filter, and NT3's ES trigger and its 60-session median, are in POINTS.
  Points are shift-invariant, so the roll-corrected masters are right.
- **Edit 3, c from volatility.** A2's c sets the cell's daily P&L standard deviation over the first two WF years
  (2016-07-01..2018-06-30) to 25% of #463's over the same days. A2 is judged at c; 0.5c and 2c are reported. This
  replaces the best of {0.5, 1, 2}.
- **Edit 4, NT3 data: no pull is needed.** The registry already holds both funds as Alpaca 5-minute RTH split-adjusted
  masters, 2016-01-04..2026-06-30, from TRANSFER r2's pull:
  - GLD `augur_uploads/master_90ca117d.csv`, 204,915 rows, sha256 8636706acc25d727...;
  - IEF `master_8715eb14.csv`, 204,743 rows, sha256 3d93b57cc83018cb....
- **Edit 5, what a pass earns.** An NT1 pass gets a strategy file with parity to the harness to the cent, then a pinned
  Auto-Validate the same day. An NT3 pass gets a RUNBOARD research row and a written forward no-order shadow.
- **Edit 6:** each cell also reports net without 2022, beside the without-Feb-Apr-2020 check.
- **Edit 7:** NT3's k = 2 is the mechanism's test. k = 1 triggers on about half of all sessions, so it is a dilution
  check that is reported and cannot pass.

