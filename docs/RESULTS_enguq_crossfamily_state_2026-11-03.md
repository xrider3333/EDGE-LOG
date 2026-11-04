# RESULTS - ENGU-Q <-> NOISE CROSS-FAMILY STATE FILTERS r1, GATE G0 (GAUNTLET w93)

Run 2026-11-03. Prereg `docs/PREREG_enguq_crossfamily_state_2026-11-03.md` (LF sha
`36510b301bfc0833db43dbe9d440347ad97dddbb294df5ba3e7a4ad9068ea39a`, byte-identical to the copy in
`C:\EdgeLog\manager\prereg\`), frozen and pushed as `prereg/enguq-crossfamily-state-r1` commit
`46a87de7` before the run; harness `tools/enguq_crossfamily_state_r1.py` (LF sha
`f25cb4db58a728bc9e352c9e80756d3a65a6fffbc3fa5271371fcaacc9992cbf`, selftest PASS) checked the
prereg's sha at start and matched. Log `C:\EdgeLog\enguq_xf_g0.log`, record
`C:\EdgeLog\_anatomy_cache\enguq_crossfamily_r1\g0.json`.

Masters pinned by filename AND row count: `ADJ_NQ_1m_ETH.csv` 5,560,727 rows (5,440,704 bars loaded,
2,053 ENGU-Q trades) and `NOADJ_NQ_5m_RTH.csv` 324,162 rows (317,215 bars, 4,820 NOISE trades).

**The answer in one line: G0 closes BOTH directions at draft - one on sample, one on power - so no
arm was sized, no veto was built, no trial was spent and the lockbox was never opened.**

## 1. A1 - NOISE's state read at ENGU-Q's entry bars

1,167 walk-forward entries, 2016-10-12 .. 2025-06-27, 8.71 years. Cost 0.783 points a round trip.

| NOISE state at the signal bar | trades | a year | net pts a trade | gross a trade | 80% power line |
|---|---|---|---|---|---|
| flat | 434 | 49.8 | 25.03 | 25.81 | 1,888 |
| long | 66 | 7.6 | 34.06 | 34.84 | 1,037 |
| short | 16 | 1.8 | **-39.57** | -38.79 | 116 |
| **unavailable** | **651** | **74.8** | 9.93 | 10.71 | - |

- **A1 dies on SAMPLE.** The only cells a filter could act on hold 66 and 16 entries across nine
  years - 7.6 and 1.8 trades a year against the house's 50-a-year floor.
- The -39.57 points a trade when NOISE is short is **sixteen trades**. It is not quoted as a finding
  anywhere, and it is printed here only so nobody rediscovers it and believes it.
- **It also corrects the prereg's own estimate, which was mine.** Section 1 said "roughly two thirds
  of the entries are addressable and one third is not", reasoning from executor r1's measurement that
  an RTH-only executor loses 31% of the leg's trades. The true figure is the other way round:
  **56% of entries (651 of 1,167) have NO NOISE state at all** because NOISE's tape is not open.
  Executor r1's 31% counted trades the RTH executor could not TAKE; this counts entry bars with no
  closed NOISE bar within five minutes, which is a stricter and different question.

## 2. A2 / A3 - ENGU-Q's state read at NOISE's entry bars

2,685 walk-forward entries, same stretch. Cost 0.533 points a round trip.

| ENGU-Q state at the signal bar | trades | a year | net pts a trade | gross a trade | 80% power line |
|---|---|---|---|---|---|
| flat | 1,184 | 136.0 | **10.34** | 10.87 | 6,695 |
| long | 1,501 | 172.4 | **6.72** | 7.26 | 6,695 |
| short | 0 | - | - | - | - |
| unavailable | 0 | - | - | - | - |

The two zero rows are CORRECT, not missing data: ENGU-Q is long only (asserted in the harness, which
raises on a short), and NOISE's regular hours sit inside ENGU-Q's 23-hour tape, so a state is always
available.

- **A2 dies on POWER, not on sample, and this is the half worth recording.** There is no shortage of
  trades - 1,501 NOISE entries while ENGU-Q holds its long, 172 a year - and the difference is
  economically large: **NOISE earns 6.72 points a trade while ENGU-Q is long against 10.34 when it is
  flat, about 35% less.**
- Reading a difference that size against the per-trade spread needs about **6,695 trades a side. We
  have 1,501 - four and a half times short.** At NOISE's own rate that is another 39 years of tape.
- **The sign is the OPPOSITE of ledger 2.55's hedge story**, which sized NOISE UP while ENGU-Q held
  its long on the theory that the stacked position is the better one. This reading says NOISE's
  trades taken while ENGU-Q is long are the WORSE population. Both readings are unpowered; 2.55's
  arm already failed Stage A at the 39th percentile of 200 shifted-calendar placebos.

## 3. Verdict

**Both directions close at draft, by the gate written in the prereg before any of this was computed.**
No plugin, no fork, no trial, no runner night, no lockbox read.

- **A1 (NOISE state -> ENGU-Q size tilt): CLOSED** - no state cell is both powered and above 50
  trades a year.
- **A2 / A3 (ENGU-Q state -> NOISE veto or tilt): CLOSED** - powered nowhere, 4.5x short.

**The 10.34-versus-6.72 split is recorded as an UNPOWERED OBSERVATION and nothing more.** It is
exactly the shape this house has repeatedly mistaken for an edge
(`edgelog-noise-scatter-winrate-trap`, `edgelog-roc30-lead-can-be-one-episode`), and it arrives with
the wrong sign for the only prior hypothesis anyone has written down about this pair. If it is ever
revived it needs more tape, not a cleverer test.

**This is the thirteenth round on this shape.** Cross-family day-type r1/r2/r3 (2026-08) failed on
both ENGU-Q and ORB, ledger 2.55 failed in the reverse direction, and ENGU-Q rounds 57/62/65/66
killed seven entry filters. The revive reason accepted by MANAGER was the co-tuning the scope's C3
asks for - and G0 says the data cannot support a co-tuned run either, which is a cheaper answer than
spending the night to find out.
