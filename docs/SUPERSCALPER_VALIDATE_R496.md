# SUPERSCALPER Auto-Validate run #496: DEAD (TV, 2026-11-06)

OUR PORT MISC_SUPERSCALPER_1_0 (LF b8ef032f), 900 trials, job Lrp43nRV2uevSPAuWUU5, NQ 1m ETH no-adjust, 2016-07-01..2026-06-30, cost 0.706 pt.
Daily numbers come from `python tools/superscalper_validate_read.py --run 496 --replay`; parity PASS on all 8 folds and the lockbox stretch.

| Stretch | Trades | PF | Net | ROC@30k | DD5@30k | DD% from peak | Sortino | Shape |
|---|---|---|---|---|---|---|---|---|
| WF 2020-02-24..2025-06-27 | 5,803 | 1.03 | $63,892 | 3.9 | $16,072 | 22.6% | 0.37 | 1 EPISODE |
| LB 2025-06-30..2026-06-30 | 433 | 1.08 | $12,341 | 28.0 | $19,582 | 23.1% | 0.92 | 1 EPISODE |
| Folds 1-4 (pre-2023) | 2,889 | - | $20,707 | 3.3 | $10,692 | 29.2% | 0.24 | 1 EPISODE |
| Folds 5-8 (dev-year overlap) | 2,914 | - | $43,184 | 5.1 | $11,656 | 21.1% | 0.49 | 1 EPISODE |

Pre-set verdict: DEAD (WF ROC@30k under 15, and 1 EPISODE). Engine verdict: FAIL, 4 of 6 gates; consistency and luck failed.
DSR 0.292 (luck bar 0.72), PBO 0.230, WFE 0.508, folds held 5 of 8.

Fold OOS net: -$47,482, $5,357, $26,805, $36,027, $51,412, $46,251, -$17,311, -$37,168.

## Reading
- The lockbox year cannot rescue this: it is one year, it is veto-only, and the walk-forward already failed.
- 1_0 carries the 240-minute look-ahead (docs/SUPERSCALPER_LEAK_R1.md). It moved 0 trades at 16 knob points on the pre-WF rows; it was not sized on the WF rows.
- The confirmation run on the fixed rules was conditional on a pass, so it is not run.
- The tuned run's trade edge is thin: PF 1.03 on 5,803 trades, with fold results that swing from -$47k to +$51k.

The r2c / r2d / r2e harnesses pin 1_0 at b8ef032f, so re-running them needs that revision from git history. The LEAKS header changes no rule.
