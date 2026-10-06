# INSIDER r1 - pre-registration (TV lane, 2026-10-05; scope rank 1, docs/SCOPE_TV_2026-10-05.md)

Written and committed BEFORE any real-direction number exists. The only numbers below are event counts (scope addendum A) and
the FAMILY NULL (random event dates, `python tools/tvins1_triage.py --null`), which reads no real event's return.
Harness: `tools/tvins1_triage.py` (selftest on synthetic data passes). Review: MANAGER (standing order 10-04 item 2 - Stage A
runs 60 minutes after this lands if no answer; the review folds in as a dated addendum).

## Mechanism (from the literature, not from our data)

Officers and directors who buy their own company's stock in the open market have information or conviction the price does
not yet carry; the purchase predicts abnormal returns over the following weeks (Seyhun 1986; Lakonishok & Lee 2001; Jeng,
Metrick & Zeckhauser 2003), concentrated in "opportunistic" buys by insiders without a fixed calendar habit (Cohen, Malloy &
Pomorski 2012, ~0.8 % a month). Mega-caps show smaller effects; this round asks whether the effect survives in Nasdaq-100
names, hedged with NQ, at a size that clears the MDL map.

## Map placement (docs/MDL_MAP_R1.md, before drafting)

Standalone, market-hedged leg: must earn ROC >= 15 %/yr at a $30k drawdown of its OWN. Expected size from the literature at
~72 events a year x $50k x ~1 % over a month: ~$36k a year gross before costs and hedge noise - plausible, power is the risk
(scope addendum A). Drawdown-week overlap with #463 is expected low (stock-specific information, NQ-hedged). The book add is a
REPORT at the volatility c (house line #45); it decides nothing.

## Data (photographs, read only; sha256 printed by the harness into its output JSON)

- Form 4: `C:\EdgeLog\_research_cache\form4\form4_ndx_open_market.csv` (tools/fetch_form4.py; SEC insider-transaction data sets
  2006Q1-2025Q2), with the EDGAR acceptance time per filing.
- Membership: `tools/data/ndx_members.csv` (spells; joined on each company's `ndx_tickers`).
- Stock bars: `C:\EdgeLog\alpaca_cache\siporb\daily_split.parquet` (Alpaca daily OHLC, split-adjusted, NO dividends; SIPORB pull
  2026-10-03/04). Renamed tickers carry full history under the new symbol (META, BKNG, GEN). 10 companies have NO bars (EA and
  9 delisted names: ATVI, BBBY, DISH, ENDP, HOLX, QVC/LVNTA, SGEN, SRCL, WBA) - their events are dropped and COUNTED; this is a
  known survivorship tilt (delisted names missing), reported, and a bar pull for them is asked of MANAGER for r2.
- Hedge: NQ 5m RTH masters (`db_adj_rth` for P&L, `db_noadj_rth` for sizing), 09:30 bar open and 15:55 bar close; roll costs
  from `tools/data/rolls_NQ.csv`.
- Window: walk-forward 2016-07-01 .. 2025-06-29 (Stage A). Arrays end before 2025-06-30. No EARLY block exists (bars start
  2016-01), so the RISK r1 2010-16 check is NOT testable here and is stated as such.

## Event, trade and cells (fixed now)

1. **Event** = one company x Form 4 filing date with >= 1 open-market purchase (transaction code P) by an officer or director,
   filed inside the company's Nasdaq-100 membership spell. Known at the EARLIEST EDGAR acceptance time that day.
2. **Entry** at the stock's OPEN of the first session the market could act: the acceptance day's session if accepted before
   09:30 ET on a session day, else the next session. **Exit** at the OPEN H sessions after entry.
3. **Size** $50,000 per position (shares = 50,000 / entry open). **No stacking**: one position per company at a time; a new
   event in a held company restarts the clock (exit = the new entry + H), size unchanged.
4. **Hedge**: short NQ micros ($2 a point) against the summed open stock notional, rebalanced at every 09:30 open, whole
   micros sized on the previous raw close; $3.00 per micro per side (fee + one tick), rolls charged twice.
5. **Stock costs** 5 bp per side (primary). Borrow is not needed (long only).
6. **Cells (6)**: H in {5, 20, 60} sessions x event value floor in {all, >= $100,000 of purchases that day}.
7. **Family null**: 500 draws (seed 20261005); each draw moves every event to a random session inside the same company's
   membership spell within the walk-forward window (with a real bar), keeping its value; the statistic is the MAX ROC@$30k over
   the 6 cells. Power line = null 95th minus 50th percentile.

## Stage A bars (walk-forward only; all must hold for the best cell)

- ROC %/yr at $30k own drawdown (30 x (net / years) / drawdown, valued daily) **>= 15** (map) AND **above the null's 95th
  percentile of the max-over-cells statistic**.
- >= 100 walk-forward trades (positions).
- RISK r1: positive without 2020-02-01 .. 2020-04-30; >= 6 of 9 walk-forward July-years positive; profitable without its
  biggest trade; leave-one-company-out keeps the sign for every company.
- A pass -> MANAGER decides the route (the job runner cannot host stock legs today; RESMOM's book line is the precedent). The
  lockbox (one read, Stage B veto) waits for MANAGER's line; the lockbox year holds roughly 45-70 events, so the 50-trade
  lockbox bar may fail on count alone (stated before any data).

## Reported, never deciding (addendum-2 diagnostics)

Event-time path (-10 .. +60 sessions, stock minus NQ); regime halves 2016-07..2021-06 / 2021-07..2025-06; cost curve 0 / 2 / 5 /
10 / 20 bp; per July-year; per company (top-10 share of net, leave-one-company-out); top-10-trade share; stock leg and hedge
leg apart; the unhedged long; CMP classes (opportunistic / routine / unclassified) and clustered (2+ insiders) as SPLITS;
dropped-event count (no bars); missing dividends (~1 %/yr on held notional, a conservative bias); book add at the vol c
(seat report, drawdown-day dollars) - report only.

## Power line (family null, computed before the real run)

Run 2026-10-05 (`--null`; output `C:\EdgeLog\_anatomy_cache\tv_insider_r1\null_power.json`; input sha256 form4 33c5f7f9...,
bars 083f8c23..., members cfca0f85...). Events: 648 inside membership spells, 37 without bars (ATVI, DISH, EA, HOLX, QVC/LVNTA,
WBA in the window), **606 entering inside the walk-forward**, 103 companies. Positions per cell after the no-stacking rule:
H5 509 / 376 (all / >= $100k), H20 421 / 315, H60 336 / 260 - every cell clears 100 trades.

**Family null (max ROC@$30k over the 6 cells, 500 random-date draws, seed 20261005): 50th -1.79, 95th 2.32, 99th 5.67,
max 10.37. Power line = 4.11.** Random-date long-stock / short-NQ positions LOSE on balance (a steady loser reads about -3.3
on this yardstick), so the null band is narrow and far below the map line: **the binding bar is ROC >= 15, not the null**;
an effect at the map line would sit ~3x beyond the null's maximum. The test is well powered at the size the map needs; the
open risk is the lockbox count, not walk-forward power.

Plumbing check (`--dry`): one random-date draw through the real-run code completes every report block (no real-direction
number read).

## Addendum 1 (2026-10-05, MANAGER review #68 "GO WITH EDITS", applied BEFORE any real-direction run)

1. **Fill timing.** Entry = the first 09:30 open at least 30 minutes after the EDGAR acceptance: accepted before 09:00 ET on a
   session day -> that session's open, else the next session's open (was: before 09:30). An acceptance at 09:29 cannot be acted
   on at 09:30.
2. **Dividends.** Cash dividends from `C:\EdgeLog\alpaca_cache\xgap\corporate_actions_wide.csv` (Alpaca corporate actions, sha
   pinned in the output JSON) are added on held notional: a position held at the close before an ex-date earns cash / previous
   RAW close x shares x split-adjusted close. The verdict reads the WITH-dividends book; the without-dividends cell is reported
   beside it.
3. **Survivorship.** MANAGER pulls daily split + raw bars for the 12 member tickers missing from the SIPORB set (EA, ATVI, DISH,
   HOLX, QVCA, QRTEA, LVNTA, WBA, BBBY, ENDP, SGEN, SRCL) through `tools/import_alpaca_stocks.py`; the harness reads them from the
   library masters (`alpaca_split_*` / `alpaca_raw_*`, 1D) and lists which arrived. Alpaca history starts 2016-01, which covers
   the walk-forward window. Any company still without bars is dropped and counted, and the long-only survivorship tilt is stated
   with that count.
4. **Splits and path.** CMP opportunistic / routine / unclassified and clustered buys stay REPORTED rows; the event-time path
   (all events, -10 .. +60 sessions, stock minus NQ) is printed FIRST, before any cell.
5. **Stage B** = the leg's own sealed-year veto (one read, after MANAGER's line; the count flag stands). The book add is a
   report at the volatility c.
6. **The family null is re-run** with items 1-3 in place before the real run (same seed, same 6 cells); the power line below is
   replaced by the re-run's and the first run is kept for the record.

**Re-run null with addendum 1 in place (2026-10-05, same seed, same 6 cells; run 1 kept as null_power_run1_pre_addendum.json):** events 648 inside membership spells, 0 without bars, **643 entering inside the walk-forward**, 110 companies (pulled names carrying events: ATVI, DISH, EA, HOLX, QRTEA, WBA). Positions per cell: H5_v0 539, H5_v100000 400, H20_v0 445, H20_v100000 336, H60_v0 354, H60_v100000 276. **Family null: 50th -1.85, 95th 1.84; power line 3.69.** The binding bar stays the map line ROC >= 15. Input sha256: form4 33c5f7f9..., bars 083f8c23..., bars_raw fa42412d..., corporate_actions e5bc8487..., members cfca0f85....

## Stage A RESULT (2026-10-05 15:47 MST, `--real`, after addendum 1 and the re-run null were committed) - **DEAD**

**Verdict: FAIL (roc30_ge_15, years_6_of_9).** Best cell H5_v100000: ROC@$30k **1.88** (net $+18k over 9 walk-forward years, drawdown $32k, Sortino 0.20,
400 positions) against the map line 15 (and the null 95th 1.84, which it clears by a hair - a max-cell that size is a ~5 %
event under the null). No cell is near the line.

- All 6 cells (ROC@$30k): H5_v0 -0.85 (net $-11k, DD $45k, n 539); H5_v100000 1.88 (net $+18k, DD $32k, n 400); H20_v0 0.56 (net $+21k, DD $123k, n 445); H20_v100000 1.24 (net $+36k, DD $97k, n 336); H60_v0 -1.95 (net $-225k, DD $386k, n 354); H60_v100000 -2.34 (net $-223k, DD $319k, n 276).
- Event-time path (all 643 events, mean cumulative stock minus NQ, %, zero at the close before entry): -10 2.292, -5 1.157,
  entry 0.54, +5 0.676, +20 1.041, +40 1.08, +60 1.057. Insiders buy AFTER a ~2.3 % relative slide over the 9 sessions before (part of the +0.5 entry-day move is the overnight gap, before the open fill); the drift
  after the buy is ~+0.5 % over 60 sessions - a fraction of the published ~1 % a month, and too small to pay costs and the
  hedge's tracking.
- Best cell, July-years: 2016-17 +8k, 2017-18 +3k, 2018-19 +4k, 2019-20 -23k, 2020-21 +16k, 2021-22 +20k, 2022-23 -1k, 2023-24 -5k, 2024-25 -3k (5 of 9 positive). Without Feb-Apr 2020 $+34k. Halves: 2016-21 ROC 1.30, 2021-25 ROC 3.12.
- Legs: stock $+135k, NQ hedge $-117k. Unhedged long ROC 11.22 (that is the market, not the signal). Without dividends ROC
  0.91. Cost curve (stock bp a side): 0bp 4.37, 2bp 3.33, 5bp 1.88, 10bp -0.17, 20bp -2.79.
- Concentration: top-10 trades = 128 % of net; top-10 companies = 146 % of net; worst leave-one-company-out AKAM $+4k.
- Reported splits (best cell's H and floor): opportunistic n 60 ROC 1.57; routine n 22 ROC 4.99; unclassified n 330 ROC 0.06; clustered n 39 ROC 1.78. The published "opportunistic" class does not carry in Nasdaq-100 names.
- The 60-session cells lose ~$225k: repeat buyers restart the clock and keep a position through long relative slides (H60, all
  events: WBA -$63k over 605 sessions held, WBD -$39k, AAL -$36k, ATVI -$27k, INTC -$22k over 1,365 sessions; best ALGN +$84k,
  FAST +$48k), while the short-NQ hedge pays the 2016-25 NQ rally. Bars were checked for unadjusted splits (AAPL, NVDA,
  TSLA, GOOGL, AMZN, AVGO split dates clean; the only < -45 % member day outside real crashes is KDP 2018-07-10, the Keurig
  merger's special dividend, before KDP's membership spell - no position can hold it).

**Next:** no Stage B (dead on the walk-forward). Ledger row + RUNBOARD research row filed. Per MANAGER #68 the queue moves
to the non-earnings 8-K drift (map check first - scope addendum B says its prior is under the line) and the catalog mechanisms.

## Correction 1 (2026-10-05 evening, STRATEGY-BEATING second review #80) - verdict unchanged (DEAD)

The event-time path above divided NQ's daily point moves by the BACK-ADJUSTED NQ level, which is not a price; that understated
NQ's returns and flattered the drift. Recomputed with NQ's return = point move / previous RAW close (the harness now does this;
the hedge P&L always used point moves and is unchanged): -10 2.33, -5 1.19, entry 0.47, +5 0.46, +10 0.35, +20 0.54, +30 0.30,
+40 0.19, +50 0.25, +60 **-0.38**. So insiders buy after a ~2.3 % relative slide and the stock keeps LAGGING NQ by ~0.85 % over
the next 60 sessions - there is no post-buy drift at all, which is what the losing 60-session cells already said. The
earlier "+0.5 % drift over 60 sessions" line is withdrawn. Also from the review: the selftest's hedge check now asserts the exact
rebalance cost on a flat NQ (it passed for any negative number before); 48 Form 5 rows without an EDGAR stamp drop out of the
events (an r2 would state that rule explicitly); 66 of 1,122 events are only late or amended filings (22 of 820 at >= $100k).
