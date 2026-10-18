# RESULTS: CTXSHORT r2 - the owner's CBD / ENGD shorts, taken only while NOISE #382 is short (DISC, 2026-10-18)

- **Prereg:** docs/PREREG_disc_ctxshort_r2_2026-10-18.md. Branch prereg/disc-ctxshort-r2 = 4316f58a was pushed and its hashes posted to
  MANAGER (#1456) before the run.
  - LF sha256: prereg 37e848b4...4575, harness 6447861d...4558, r1 code 640fe08a...82a4. All three were checked at start.
- **Harness:** tools/disc_ctxshort_r2.py.
- **Outputs:** C:\EdgeLog\_anatomy_cache\ctxshort_r2\ (run.log, trades_<arm>_<exit>.csv, ctxshort_r2_result.json). 9 run-record lines are
  in C:\EdgeLog\run_records\DISC_202610.jsonl.
- **Data:** ADJ_NQ_1m_ETH id 66, WF 2016-07-01..2025-06-29.
  - Its fingerprint differs from r1's (03860718 vs 067ea375), because the 10-17 ETH date_to fix cuts the closing Sunday's evening.
  - The RTH rows are identical (924,284).
- **Crowns:** NOISE #382 re-run from its run doc (3,184 trades); ORB #314 for the second-crown read.

## Verdict (pre-set): 0 of 6 gated cells SUPPORTED; house bar 0 of 6 (expected, by the MDL clause)
- Every cell is UNDERPOWERED: capped signals per year are A 14.1, B 21.3 and B0 50.7; the MDE of 0.28-0.99 R is far above the prior.
- **Every cell is one episode.** Every cell loses money without its 3 best trades: those 3 trades are 92-164% of arm A's net and
  107-1,487% of arm B's.

WF, NQ cost 0.783, 1 NQ:

| arm | exit | trades | ROC@30k | DD5 | DD % from peak | Sortino | gross pt/trade | boot t (R) | why NOT SUPPORTED |
|---|---|---|---|---|---|---|---|---|---|
| **A (completed + gate)** | **E2 (first-named)** | 102 | 6.1 | $2,271 | 3.53 | 0.56 | 3.98 | 0.18 | one episode; 2016-20 half -$523 |
| A | E1 | 114 | 2.1 | $1,760 | 5.71 | 0.31 | 2.37 | -0.32 | one episode; 2016-20 half -$1,678 |
| A | E3 | 99 | 7.1 | $2,876 | 5.96 | 1.09 | 7.87 | 1.05 | one episode (ex top 3: -$2,018) |
| B (so far + gate) | E1 | 169 | 0.2 | $2,915 | 9.05 | 0.03 | 0.91 | -1.59 | one episode; 2016-20 half -$3,622 |
| B | E2 | 155 | 2.0 | $3,328 | 7.50 | 0.33 | 2.29 | -0.70 | one episode; 2016-20 half -$1,767 |
| B | E3 | 152 | 6.9 | $4,149 | 7.09 | 1.07 | 6.21 | 0.51 | one episode (ex top 3: -$1,138) |
| B0 (so far, no gate; report) | E1 | 396 | -0.9 | $6,425 | 16.87 | -0.22 | 0.16 | -1.32 | report only |
| B0 | E2 | 371 | -0.3 | $4,988 | 14.80 | -0.06 | 0.61 | -0.61 | report only |
| B0 | E3 | 362 | 0.9 | $8,720 | 27.20 | 0.33 | 1.94 | 0.60 | report only |

**R curve** ($500 a 1R): A / E2 1.0, DD5 $2,796, 4.95%, Sortino 0.10. A / E3 7.3, $4,384, 6.63%, 1.08. B / E3 3.0, $6,335, 9.40%, 0.48.

## What the gate does (B0, the ungated base, split by NOISE's position at the entry)
| exit | NOISE short open at entry | NOT open |
|---|---|---|
| E2 | 135 trades, +$4,821: ROC 2.1, DD5 $2,979, 7.25%, Sortino 0.36 | 236 trades, -$6,083: ROC -1.6, $4,460, 11.95%, -0.34 |
| E3 | 129 trades, +$14,665: ROC 6.7, $3,889, 6.44%, 1.00 | 233 trades, -$6,264: ROC -0.7, $7,584, 27.23%, -0.31 |

- This confirms r1 with a gate a trader can know: the setup makes money only while NOISE is short.
- But even then it is about 11-17 trades a year, resting on a handful of large winners.

## Answer key (flags only, after the WF read; NOISE #382 warmed from 2024-06-01)
- **The bar-so-far context passes at the owner's exact candle on 10-12 (10:06) and 10-14 (09:57).** B0, the ungated rule, fires there
  at the same minute. This is the deep dive's reading, now measured.
  - 10-16 10:51 fails B's C4: the 30m bar so far was not red. It also failed A's C3.
- **NOISE #382 was NOT short at the entry on any of the three dates.** So the gated arms A and B fire on none of them. The owner's three
  best shorts were exactly the kind the gate rejects.
- **Journal:** 0 of the 2 reachable MES signals (04-28 10:35, 06-12 09:45) show an NQ trigger within 5 minutes.
  - 04-28: so-far context on, NOISE not short.
  - The other 3 are outside the window by construction.

## What it means for the owner
- No version of the rule, gated or not, shows an edge that survives its 3 best trades.
- The NOISE gate sorts the setup's trades the right way (winners while NOISE is short, losers otherwise). But it would have skipped all
  three of his should-have-traded days, and the trades it keeps rest on a few big days.
- **As a discretionary aid:** the context reading he sees on the chart (bar so far) is now defined and reproduces his three entries.
  The backtest says the setup is a tail trade: about 1 in 5 wins (E3 win rate 17-21%), and the money is in holding the winners.
  - So sizing by the stop and holding the winners matters more than the filter.
  - Nothing here supports adding it as a rule.
- **Closed:** CTXSHORT r1 + r2. No r3 is proposed.
