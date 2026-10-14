# ORB COSTSTRESS r1: result (2026-10-14)

**Setup:**
- Prereg: `docs/PREREG_orb_coststress_r1_2026-10-14.md` (LF sha256 0d56ed9f..., branch prereg/orb-coststress-r1 = c28bb87d, pushed before the run).
- Harness: `tools/orb_coststress_r1.py` (LF sha256 f0126bd6...). The note hash was checked at start.
- Output: `C:\EdgeLog\_anatomy_cache\orb_coststress_r1.json`.
- Scope: WF 2016-07-01 .. 2025-06-27, lockbox unread, report-only.

**The leg:**
- ORB_R6 as the box runs it: `api.cloud_signal.CROWN_LEGS["ORB_R6"]`, #314's settings.
- Market and data: QQQ 5m Alpaca master (id 113), 10 shares a trade.
- Volume: 1,161 trades, 129 a year; gross $3,328 over the WF at 10 shares.

| Cost $/share round trip | ROC @ $30k | DD5 (at $30k) | DD % from peak (at $30k) | Sortino | Net a year at 10 sh | PF |
|---|---|---|---|---|---|---|
| 0.00 | 25.41 | $19,474 | 19.2 | 2.01 | $370 | 1.39 |
| 0.02 (house) | 23.47 | $19,729 | 20.1 | 1.86 | $344 | 1.36 |
| 0.05 | 20.60 | $20,123 | 21.5 | 1.64 | $306 | 1.31 |
| 0.10 | 14.61 | $19,508 | 24.3 | 1.27 | $241 | 1.24 |
| 0.15 | 8.81 | $17,803 | 27.2 | 0.92 | $176 | 1.17 |
| 0.20 | 4.68 | $17,155 | 29.6 | 0.57 | $112 | 1.10 |
| 0.25 | 1.45 | $10,476 | 30.0 | 0.24 | $47 | 1.04 |
| 0.30 | -0.41 | - | 30.0 | -0.09 | -$17 | 0.99 |
| 0.40 | -1.98 | - | 30.0 | -0.71 | -$146 | 0.88 |

**Break-evens:**
- **c15 (ROC @ $30k = 15):** $0.097 a share per round trip.
- **c0 (WF net = 0):** $0.287 a share per round trip.
- **V1:** the leg carries up to about 10 cents of cost. It is not cost-fragile on its own backtest.

**Live:**
- **Source:** box ledgers, pull-job folder 2026-10-13_1445.
- **Trades:** 6 engine trades; 5 have fills. 09-18 has no fill.

| Measure | $ a share |
|---|---|
| Shortfall vs the engine's prices, per round trip | 0.19 (sd 0.32; 95% range -0.20 .. +0.58) |
| Entry gap | 0.01 (the box's own slip setting) |
| Exit gap | 0.18 |
| EOD exits (4 trades) | 0.18 |
| The one other exit | 0.24 |

- **V2, as pre-set:** the point estimate is above c15, so the leg is **flagged for the owner; nothing changes.**
- **How firm the read is:** it is weak.
  - About 259 trades (about two years) are needed before the 95% range is half of (c15 - 0.02).
  - The gap sits in the end-of-day exit. The executor sells at about 15:59, while the engine prices its 15:55 bar. That is a timing difference of uncertain sign, and may not be a real cost.
- **Suggested to the Webull lane:** book or log the EOD exit at the same bar the engine prices, so the forward read measures cost and not timing.
