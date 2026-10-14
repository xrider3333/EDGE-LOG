# ORB-RELAY r1: result (2026-10-14)

**Setup:**
- Prereg: `docs/PREREG_orb_relay_r1_2026-10-14.md` (LF sha256 0da0f8ee..., branch prereg/orb-relay-r1 = 23a49e3f, pushed before the run).
- Harness: `tools/orb_relay_r1.py` (LF sha256 aa9b6ebb...). The note hash was checked at start.
- Output: `C:\EdgeLog\_anatomy_cache\orb_relay_r1.json`.
- Scope: WF 2016-07-01 .. 2025-06-27, lockbox unread, report-only.

**The question:** should the live Webull ORB leg (ORB_R6, #314's settings, QQQ, 10 shares) take its signals from NQ's bars instead of QQQ's own?

| Row | ROC @ $30k | DD5 (at $30k) | DD % from peak (at $30k) | Sortino | Net a year | Trades a year |
|---|---|---|---|---|---|---|
| A AS LIVE: QQQ's own 5m bars | 23.47 | $19,729 | 20.1 | 1.86 | $344 (10 sh) | 129 |
| B RELAY: NQ 5m signals, QQQ 1m fills at the same instants | 35.18 | $22,199 | 17.7 | 2.25 | $415 (10 sh) | 142 |
| C RELAY + one-minute executor lag on entry | 34.36 | $21,919 | 17.9 | 2.22 | $411 (10 sh) | 141 |
| D REFERENCE: NQ #314 itself | 36.22 | $22,382 | 17.1 | 2.26 | $34,839 (1 NQ) | 142 |

All four rows are driven by one episode (worst drawdown > 1.3 x DD5).

**The paired read:**
- **C's lead over A:** +10.9 ROC points (90% block bootstrap -10.9 .. +38.2). B's lead: +11.7 (-10.3 .. +38.8).
- **The lag costs almost nothing:** C keeps 99% of B's net.
- **Overlap:** B takes 93% of A's trades (same day, same side).
- **Relay fills:** 1,281 NQ trades; 2 had no QQQ minute and were dropped; 951 exited at EOD. Every stop or target exit found its NQ minute.

**Verdict (pre-set): LEADS, NOT DISTINGUISHABLE.** The +10.9 lead clears the +5 bar, but the 90% interval reaches below 0. Nothing changes.

**What it means:**
- On QQQ fills, NQ's signals keep about 95% of NQ's own ROC (34.4 vs 36.2). QQQ's own bars keep about 65% (23.5).
- This repeats ledger 2.96's mechanism: the shared trades are identical; NQ-only signals earn and QQQ-only signals lose.
- It also repeats FRONTIER Q36 for ENGU-Q: NQ signals on QQQ keep 98%.
- The bootstrap cannot separate two ROC figures that each rest on one drawdown episode.
- The case for an NQ signal relay is a mechanism argument plus a +11-point point estimate. That makes it a design call for PAPER-WB and the owner, alongside ENGU-Q's NQ relay. A box-side NQ feed (Yahoo, for KEEL) already exists.
