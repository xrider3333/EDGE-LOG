# BOOK LOOKS r1 - how sure a lockbox pass must be (2026-10-05)

**After 71 printed looks at #463's lockbox year (51 leg looks, 20 sizing looks), no margin on the grid up to 100 % brings a no-edge candidate's family-wise false-pass rate under 5 % - the lockbox clause cannot be rescued by a margin at this K.**

**What the nulls say.** At today's bar a no-edge candidate has ALREADY cleared the lockbox somewhere in the pile with probability FWER(0) = 1.000: a no-information seat swap / add passes it with p_leg(0) = 0.42445 (16,978 of 40,000) and a no-information sizing rule with p_size(0) = 0.24369 (1,024 of 4,202). The registered reading of H0 ("today's bar controls the family-wise false-pass rate"): **FAILS** - the bar does NOT control the family-wise false-pass rate at the looks already spent; the FAIL is not a discovery - the product is g_adj and the tables.

**The margin.** No margin on the 0..1.0 grid brings FWER under 0.05 (g* > 1.0); band: > 1.0 at 0.025, > 1.0 at 0.10. Per seat: ORB > 1.0, ENGU-Q > 1.0, TTM 0.565, NOISE 0.670. With the top lockbox trade removed g*_x = > 1.0; with CDR in place of ROC g*_CDR = > 1.0. The walk-forward analogue (report only): p_WF(0) = 0.27163 (10,865 of 40,000) leg / 0.07187 (302 of 4,202) size, WF margin at 5 % = 0.560.

**Calibration.** The ten real one-change reads spread sd_real = 0.086 in ln(LB ratio) (n = 10 of 10); the null's centred spread is sd_null = 0.248 (n = 40,000 draws, 0 without a positive LB ROC dropped); r = 0.35, so g_adj = g* x max(1, r) = > 1.0. **FLAG: r is outside [0.5, 2.0] - the null does not describe the real swaps' spread.**

**What a future read costs (margin ladder, FWER 5 %).**

| K looks | g*(K) |
|---|---|
| 1 | 0.410 |
| 10 | 0.990 |
| 50 | > 1.0 |
| 71 (K_book) | > 1.0 |
| 100 | > 1.0 |
| 142 (2K_book) | > 1.0 |
| 181 (K_ceiling) | > 1.0 |
| 500 | > 1.0 |

**Past passes, re-judged at g_adj (context lines, not re-verdicts).**

| candidate | LB ratio | printed | K then | g_adj then | survives | K now | g_adj now | survives | context |
|---|---|---|---|---|---|---|---|---|---|
| 58d | 1.048 | PASS (every clause, thin margins), then REFUTED by the adversarial check | 17 | > 1.0 | no | 71 | > 1.0 | no |  |
| #444 | 1.056 | MISSES clause 3 only, by $767 (LB DD at close $27,955 vs cap $27,188) | 30 | > 1.0 | no | 71 | > 1.0 | no |  |
| #449 | 1.056 | CLEARS all four clauses (15 of 15 years) | 31 | > 1.0 | no | 71 | > 1.0 | no | adopted on more than the lockbox (clauses 1-8, BOOK.md 10m) |
| round-61 best | 1.442 | misses clause (4) (LB DD at the WF-matched size $33,098, +9.8%) | 35 | > 1.0 | no | 71 | > 1.0 | no |  |
| V2 | 1.573 | PASS both stretches; a tail hedge (two episodes); not adopted -> nightly VT shadow | 49 | > 1.0 | no | 71 | > 1.0 | no | failed RISK r1 |
| V2-500 | 1.453 | PASS | 50 | > 1.0 | no | 71 | > 1.0 | no |  |
| Q4 | 1.142 | PASS (post-hoc) -> forward paper shadow book_shadow_q4, never an adoption | 63 | > 1.0 | no | 71 | > 1.0 | no | post-hoc |
| Q6 | 1.021 | PASS (clears the bar narrowly in both stretches) -> owner call: shadow first (book_shadow_orb239); #463 stays adopted | 63 | > 1.0 | no | 71 | > 1.0 | no | ORB #239 in the ORB seat is a forward shadow |

**The nulls.** N-LEG: 10,000 draws per seat (block 21, seeds ORB 20261004, ENGU-Q 20261005, TTM 20261006, NOISE 20261007), centred on each seat's own draw median; the medians sit ORB +8.6%, ENGU-Q +5.9%, TTM -0.1%, NOISE +28.1% from the reference (the alignment artefact the centring removes). N-SIZE: 4,202 circular shifts of the V2 multipliers (k in [250, 4451] of 4701 rows), uncentred at the bar as written; V2-500 and V2-60 cells: V2-500 0.24465 (1,028 of 4,202); V2-60 0.27082 (1,138 of 4,202) (reported, not pooled). Largest lockbox trade: ENGU-Q 2026-04-07..2026-05-12 $91,152; LB_x not computed for the ENGU-Q seat.

**The rule this round proposes (an owner decision via MANAGER, never automatic).** for any BACKTEST candidate judged on the spent lockbox year from now on: LB ROC >= 155.54 x (1 + g_adj > 1.0) = beyond the 0..1.0 grid (more than 2 x the reference) at a $30k drawdown, Sortino >= 4.150 unchanged; a candidate that clears WF but not that margin is 'not refuted', never 'a pass'; FORWARD reads are untouched; an owner decision via MANAGER.

**Not claimed.** The nulls stand in for a candidate of that type with no information, not for any particular candidate; K counts printed looks, so it is a floor and FWER(0) a lower bound; one realised history (block-21 bootstrap keeps three-week structure, not regimes; the shifts keep everything but the timing).

Files: C:\EdgeLog\_anatomy_cache\rocfrontier\looks_r1 (LOOKS.txt, margin_curve.csv, past_passes.csv, nulls.json, draws.npz). prereg sha256 26957d922b2cd61ce2acf8f30641511797db9b8d9fbd8a6f08423a0fdf413a62; ledger sha256 f55656b4f1481917efdcef1c7e779bd6fb8f5728ac31396cb2fc86174d118f52; wall time 80.3s.
