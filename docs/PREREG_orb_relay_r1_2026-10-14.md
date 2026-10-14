# PREREG: ORB-RELAY r1 - the live QQQ ORB leg on NQ's signals instead of QQQ's own (ORB lane, 2026-10-14)

**Why.** Owner 10-14 via MANAGER #77: keep testing. This is the next best-ROI ORB item. There are two facts behind it.
- **Ledger 2.96 (QQQ VALIDATE r1):** #314 run on QQQ's own bars keeps 0.78 of its NQ edge (interval 0.40-1.06). The trades both markets take are
  identical; the gap is that NQ-only signals earn and QQQ-only signals lose.
- **For ENGU-Q, FRONTIER Q36 found the cure is the signal source:** NQ's own signals filled on QQQ keep 98% of the dollars.

The live Webull ORB leg (ORB_R6) trades QQQ on QQQ's own bars, at walk-forward ROC @ $30k 23.5 (ORB COSTSTRESS r1, $0.02 a share). A
box-side NQ feed now exists (Yahoo NQ for KEEL, 10-14). This test asks whether ORB should take its signals from NQ.

**Rows.** WF only: 2016-07-01 .. 2025-06-27 (the QQQ master's last WF session); the lockbox is not read. All rows are 10 shares of QQQ at
$0.02 a share a round trip, booked on the exit day.

| Row | Signals | Fills |
|---|---|---|
| A, AS LIVE | `api.cloud_signal.CROWN_LEGS["ORB_R6"]` on the QQQ 5m Alpaca master (id 113), through the engine | the bar-close fill the box's engine prices |
| B, RELAY | the same settings (#314's) on the NQ 5m RTH back-adjusted master (id 73), through the engine | on the QQQ 1m Alpaca master (id 144), at the same instants |
| C, RELAY + LAG | as B | entry at the OPEN of the first QQQ minute after the NQ signal bar closes (one minute of executor delay); exits as B |
| D, REFERENCE | NQ #314 itself, per NQ contract ($20 a point, cost 0.533 points) | NQ |

How B fills each NQ trade on QQQ:
- **Entry:** the close of the QQQ minute that ends when the NQ 5m signal bar ends. ORB enters at that bar's close.
- **Stop, target or breakeven exit:** in the NQ 5m exit bar, find the first NQ 1m minute that reaches the NQ exit level (low <= level for a long's stop or
  breakeven, high >= level for a long's target, mirrored for shorts). The exit is the QQQ close of that same minute. If no NQ minute
  reaches the level, the exit is the QQQ close of the bar's last minute; such cases are counted.
- **End of day:** the close of QQQ's 15:59 minute.
- **Point mapping:** none. QQQ's own prices are used.

**Numbers per row.** The house four for WF, on the daily curve:
- ROC @ $30k;
- DD5;
- DD % from peak (sized to a $30k worst drawdown, start $100,000);
- Sortino.
- Also: trades a year, net a year at 10 shares, and B's fallback count.

**Paired read.**
- **Lead:** B's ROC minus A's (and C - A).
- **Interval:** 90% from 2,000 paired block-bootstrap draws (blocks of 20 sessions, the same days for both rows, seed 20261014).
- **Overlap:** the share of A's trades that B also takes, on the same day and side.

**Verdict (set now).**
- **"RELAY RECOMMENDED"**, as a design call for PAPER-WB and the owner (nothing changes here): C's lead >= +5 ROC points, AND its 90% interval's
  lower end > 0, AND C keeps >= 90% of B's net.
- **"LEADS, NOT DISTINGUISHABLE"**: C's lead >= +5, but the interval reaches 0.
- **"NO CASE FOR THE RELAY"**: otherwise.

Report-only: no rule, size or live change, #314 untouched. Harness: `tools/orb_relay_r1.py`, which checks this note's LF sha256 at start and
stops on a mismatch.
