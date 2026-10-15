# PREREG: ORB CLOSEXIT r1 - does the last minute pay the live ORB leg's end-of-day exits? (ORB lane, 2026-10-15)

**Why.** The owner 10-15 asked for a reading-shelf paper; this is shelf #27, Bogousslavsky & Muravyev, "Who trades at the close?" (JFM 2023).
- **The paper:** closing-auction volume grew to about 7.5% of US stock volume (2018), and closing prices are pushed off the quote midpoint. That push
  reverts, half shortly after the close.
- **Why it matters for ORB:**
  - About three in four of ORB's trades exit at the end of the day.
  - The live Webull ORB leg's executor sells at about 15:59:01, while the backtest books the 15:59 minute's close (its 15:55 bar close).
  - ORB COSTSTRESS r1 found the live leg's whole shortfall sits in that exit ($0.18 a share, 5 trades).
- **The question:** does the price move in the position's favour over the last minute of the session, so that a 15:59:01 exit gives it away? The auction
  print itself is not in our RTH minute data (it prints at 16:00), so this measures the run-up to it, not the auction.

**Trades.** WF only, 2016-07-01 .. 2025-06-27; the lockbox is not read.
- The leg as the box runs it: `api.cloud_signal.CROWN_LEGS["ORB_R6"]` on the QQQ 5m Alpaca master (id 113), through the engine (row A of ORB-RELAY r1).
- Only end-of-day exits: the exit bar is the session's last bar, and the exit price is that bar's close.

**Prices, from the QQQ 1m Alpaca master (id 144), per share and signed by the trade's side.**

| Label | Price | Who books it |
|---|---|---|
| E0 | close of the session's last minute (15:59) | the backtest |
| E1 | open of that minute | the live executor at ~15:59:01 |
| E2 | close of the minute ending 4 minutes earlier (15:55 close) | the shape of the drift |

**Numbers.** For E0 - E1 and E0 - E2:
- n, mean, sd, the 95% t interval, and the mean x trades a year x 10 shares;
- the same split by NQ-style trend day: QQQ |close - open| / open in the WF top 10%.

The leg's four numbers (ROC @ $30k, DD5, DD % from peak sized to $30k, Sortino) are computed with its EOD exits booked at E0 and at E1, at the
house $0.02 a share.

**Verdict on E0 - E1 (set now).**
- **"THE LAST MINUTE PAYS THE POSITION"**: the 95% interval is above 0. A 15:59:01 exit gives up the mean x 10 shares a trade. A market-on-close or
  last-second exit becomes a design call for PAPER-WB and the owner.
- **"EXITING EARLY IS BETTER"**: the 95% interval is below 0.
- **"NO LAST-MINUTE EFFECT"**: otherwise. Then the live exit gap is execution or timing noise, not the last minute.

Report-only: no rule, size or live change, #314 untouched. Harness: `tools/orb_closexit_r1.py`, which checks this note's LF sha256 at start.
