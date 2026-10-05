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
