# ORB CLOSEXIT r1: result (2026-10-15)

**Setup:**
- Prereg: `docs/PREREG_orb_closexit_r1_2026-10-15.md` (LF sha256 6c2421f7..., branch prereg/orb-closexit-r1 = 5eb09d1c, pushed before the run).
- Harness: `tools/orb_closexit_r1.py` (LF sha256 494af042...). The note hash was checked at start.
- Output: `C:\EdgeLog\_anatomy_cache\orb_closexit_r1.json`.
- Scope: WF 2016-07-01 .. 2025-06-27, lockbox unread, report-only.

**Source:** reading shelf #27, Bogousslavsky & Muravyev, "Who trades at the close?" (JFM 2023).
- Closing prices are pushed off the midpoint and revert after the close.
- Our RTH minute data stops before the 16:00 auction print, so this measures the last minute, not the auction.

**The leg:** live Webull ORB, ORB_R6 on QQQ (box settings). 1,161 WF trades, of which **869 (75%) exit at the end of the day**.
- On every one of them the 15:59 minute's close equals the engine's exit price (0 mismatches).

**Signed by side, per share** (positive = the move kept going the position's way):

| Gap | All EOD exits (869) | Trend days (125, QQQ \|C-O\|/O >= 1.76%) | Other days (744) |
|---|---|---|---|
| E0 - E1: last minute (15:59 close - 15:59 open) | +$0.017 (95% -0.001 .. +0.035), t 1.87, $16 a year at 10 sh | **+$0.100 (95% +0.023 .. +0.177)** | +$0.003 (95% -0.013 .. +0.019) |
| E0 - E2: last four minutes (15:59 close - 15:55 close) | +$0.018 (95% -0.008 .. +0.044) | **+$0.168 (95% +0.049 .. +0.286)** | -$0.007 (95% -0.030 .. +0.016) |

**The leg's four numbers** (WF, $0.02 a share):

| EOD exit booked at | ROC @ $30k | DD5 (at $30k) | DD % from peak (at $30k) | Sortino | Net a year at 10 sh |
|---|---|---|---|---|---|
| E0, the 15:59 close (the backtest) | 23.47 | $19,729 | 20.1 | 1.86 | $344 |
| E1, the 15:59 open (the live executor) | 19.55 | $18,394 | 21.2 | 1.77 | $328 |

Both rows are driven by one episode.

**Verdict (pre-set, on E0 - E1 over all EOD exits): NO LAST-MINUTE EFFECT.** The 95% interval touches 0 (lower end -$0.0008).

**What it means:**
- **Across all days:** the last minute is close to neutral.
- **On trend days it is not:** those are ORB's money days (ledger 2.96: 24 of its 26 best days are trend days).
  - The close keeps running the position's way: +$0.10 a share in the last minute and +$0.17 over the last four.
  - The split was pre-registered as a report, not as the verdict.
- **Consistency:** this fits the paper's closing pressure, and Baltussen et al.'s hedging flow into the close (shelf #2).
- **Cost of exiting at 15:59:01 instead of the close:** about 4 ROC points on the leg (23.5 to 19.6). In dollars that is about $16 a year at 10 shares.
- **The live exit gap (COSTSTRESS, $0.18 a share on 5 trades):** only partly this. On ordinary days the last minute gives about nothing.

**Design note for PAPER-WB and the owner (not a verdict):**
- A market-on-close exit, or a last-second exit, would book the backtest's price.
- On trend days it would also collect the push into the close.
- It would trade away the half of the push that reverts after the close (the paper) - that half does not matter to a position that is flat by then.
