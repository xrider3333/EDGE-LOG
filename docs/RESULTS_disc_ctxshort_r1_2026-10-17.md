# RESULTS: CTXSHORT r1 - the owner's CBD / ENGD NQ 1m shorts with his context filter (DISC, 2026-10-17)

- **Prereg:** docs/PREREG_disc_ctxshort_r1_2026-10-17.md. Branch prereg/disc-ctxshort-r1 = 0229072d was pushed and its hashes posted to
  MANAGER (#1394) before the run.
  - LF sha256: prereg a53b1256...d384, harness 640fe08a...82a4. Both were checked at the run's start.
- **Harness:** tools/disc_ctxshort_r1.py.
- **Outputs:** C:\EdgeLog\_anatomy_cache\ctxshort_r1\ (run.log, trades_E1/E2/E3.csv, ctxshort_r1_result.json).
- **Data:** ADJ_NQ_1m_ETH id 66, fingerprint 067ea375.
- **Window:** WF 2016-07-01..2025-06-29 only, 59 holiday stubs excluded. Crowns re-run from their run docs: NOISE #382 (3,184 trades) and
  ORB #314 (1,481 trades).

## Verdict (pre-set): 0 of 3 pass - FAIL on every exit, all UNDERPOWERED, all CROWN SHADOWS
- **Power line:**
  - signals capped at 2 a session: 272, or 30 a year;
  - MDE 0.24 / 0.27 / 0.68 R vs a prior of +0.10 R.

  So the FAILs read "not shown", not "dead". At 25-27 trades a year, the Auto-Validate route (>= 50 a year) was out of reach anyway.

WF, NQ cost 0.783 pt, $ curve at 1 NQ:

| exit | trades | ROC@30k | DD5 | DD % from peak | Sortino | gross pt/trade | boot t (R) | failed guards |
|---|---|---|---|---|---|---|---|---|
| E1 2R bracket | 244 | -0.2 | $3,066 | 8.76 | -0.03 | 0.69 (< cost) | -1.05 | gross, ROC, one episode, first half |
| **E2 half at 2R + 5m trail (primary)** | 224 | 2.2 | $3,635 | 5.29 | 0.22 | 1.60 | -0.38 | one episode, first half (-$2,844) |
| E3 hold to the close | 218 | 3.1 | $6,148 | 10.50 | 0.62 | 3.37 | 0.98 | one episode |

- **R curve** (fixed $ risk a trade):
  - E1: ROC -2.1, DD5 $8,215, 18.3%, Sortino -0.52.
  - E2: -1.3, $3,875, 11.7%, -0.21.
  - E3: 4.2, $8,158, 13.4%, 0.90.
- **Excluding the 3 best trades:** E2 -$5,243 (ROC -1.4, DD5 $2,899, 12.0%, Sortino -0.31); E3 -$4,767 (ROC -0.9, $5,203, 15.8%, -0.26).
- **E3's halves:**
  - 2016-20: +$10,241 (ROC 28.0, DD5 $1,957, 2.3%, Sortino 1.67).
  - 2021-25: +$1,045 (ROC 0.6, $5,580, 11.5%, 0.09).

## The shadow: the context picks NOISE #382 short days
- Every exit makes its money on NOISE #382 short days and loses on #382-flat days:

  | exit | #382 short days | #382 flat days |
  |---|---|---|
  | E2 | 141 trades, +$19,569: ROC 27.6, DD5 $1,833, 2.1%, Sortino 1.65 | 75 trades, -$12,617: ROC -3.3, DD5 $12,726, 12.7%, Sortino -1.13 |
  | E3 | +$32,555 | -$17,984 |

- On days both crowns are flat: E2 has 20 trades, -$1,586 (ROC -2.9, DD5 $1,269, 1.8%, Sortino -0.41).
- **Entries made while a NOISE short is already open:** 39-43%. For ORB #314 it is 61-62%.
  - So the "short day" split is not a tradable filter as it stands. The NOISE short often comes after the CTXSHORT entry.
- **The precedent test** (on each crown's flat days: net > 0 and >= 30% of own net) fails #382 on all three exits.

## Answer key (flags only, after the WF read)
- **The trigger fired at the owner's exact candle on all 3 design dates:** 10-12 10:06 (CBD + ENGD), 10-14 09:57 (CBD) and 10-16 10:51
  (ENGD). **But the frozen context rejected all 3:**
  - **C4 failed on 10-12 and 10-14.** The deep dive's "last 3 30m bars red, 3 of 3" counted the 30m bar still FORMING at the signal. The
    last three COMPLETED 30m bars were 2 of 3:
    - 10-12: 08:30 green, 09:00 red, 09:30 red;
    - 10-14: 08:00 green, 08:30 red, 09:00 red.
  - **C3 failed on 10-16:** the 5m 20 EMA rose 1.7 points on the last completed bar.
- **Journal:** 0 of the 2 reachable real signals fired (04-28 10:35 and 06-12 09:45, both MES). The other 3 lie outside the window by
  construction.
- **This is an instrument-vs-reference mismatch.** The prereg froze "completed bars only", while the deep dive measured with the forming
  bar. It could only show up on the answer key, which MANAGER's hold kept closed until after the WF read. It is disclosed here; nothing
  was re-run.

## What it means for the owner
- His CBD / ENGD shorts, with his context, paid inside NOISE short days and lost outside them. That is the same finding as CBU-Q's three
  NOISE shadows.
- As a frozen rule there is no edge shown, and no book value, since it is a shadow of a leg already held.
- As a discretionary aid, the read says: the setup is worth taking when the day is already a NOISE-short day. This is a description,
  not a tested rule.
- **Possible r2 (MANAGER's call; not run):**
  - the deep dive's own forming-bar context;
  - plus a gate of "NOISE #382 short already open at entry";
  - read as a discretionary aid only (a shadow by construction).
