# ORB GAP38 r1: result (2026-10-15)

**Setup:**
- Prereg: `docs/PREREG_orb_gap38_r1_2026-10-15.md` (LF sha256 64e4170c..., branch prereg/orb-gap38-r1 = cb181cf1, pushed before the run).
- Harness: `tools/orb_gap38_r1.py` (LF sha256 51e16dec...). The note hash was checked at start.
- Output: `C:\EdgeLog\_anatomy_cache\orb_gap38\orb_gap38_r1.json`.
- Scope: WF 2016-07-01 .. 2025-06-27, lockbox unread, report-only.

**Source:** reading shelf No. 38, "Price gap anomaly in the US stock market: The whole story" (MANAGER #93 restock).

**The leg:** ORB crown #314 settings (`CROWN_LEGS["ORB_R6"]`) on NQ 5m RTH back-adjusted (`ADJ_NQ_5m_RTH.csv`), 0.533 points cost, one contract.
- 1,281 WF trades (143 a year): 606 went WITH the opening gap, 672 AGAINST it, 3 neutral.
- Gap = (RTH open - prior RTH close) / the prior 10 sessions' mean range.

**The split** (each trade's return in % of its entry price):

| | With the gap | Against the gap | With minus against (95%) |
|---|---|---|---|
| All trades | +0.079% (n 606) | +0.067% (n 672) | +0.012% (-0.063 .. +0.087), t 0.31 |
| Gap >= 0.25 of the range | +0.097% (n 349) | +0.082% (n 418) | +0.015% (-0.076 .. +0.107), t 0.33 |

**Verdict (pre-set): NO GAP EFFECT.**
- The draft prior (pre-walk-forward 2010-2016: +$50 with vs -$35 against, t 2.6) did not carry into the walk-forward.
- Against-gap trades earn about as much as with-gap ones.

**The four numbers per arm** (WF, at $30k):

| Arm | ROC @ $30k | DD5 | DD % from peak | Sortino | Net a year | Trades a year |
|---|---|---|---|---|---|---|
| A: #314 as is | 36.2 (one episode) | $22,382 | 17.1 | 2.26 | $34,839 | 142.5 |
| B: skip against-gap | 32.7 | $25,155 | 12.9 | 1.76 | $18,073 | 67.8 |
| C: half size against-gap | 45.6 | $27,484 | 15.1 | 2.25 | $26,456 | 142.5 |

- B - A ROC: -3.5 (90% block bootstrap -37.2 .. +10.4). No lift.
- C - A ROC: +9.4 (90% block bootstrap -14.0 .. +12.2). No lift.
  - C's higher ROC comes from A's single worst drawdown episode, not from the gap.
  - C's DD5 is worse ($27.5k vs $22.4k), and it gives up $8.4k a year.

**Map:** 14 of the 26 WF money days traded against the gap. Skipping those trades would cut ORB's tail.

**What it means:**
- Gap direction does not sort ORB's trades. Don't filter or shrink ORB on it.
- This fits ledger 2.96: ORB's money is trend days, and a trend day can open against the overnight gap.
- The pre-walk-forward prior came from ORB's flat era (net $188 a year) and went to about zero out of sample.
- Closed. No rule, size or live change; #314 untouched.
