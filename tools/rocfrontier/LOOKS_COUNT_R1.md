# LOOKS r1 - how many lockbox looks the frontier bar has absorbed (step 1 ledger count)

Built 2026-10-05 from the registered sources (tools/rocfrontier/PREREG_LOOKS_R1.txt, step 1), read-only on the repo. The counting rule was applied literally: one LOOK = one candidate book, seat swap, leg add, combination or book-level / leg-level SIZING rule whose figure on the lockbox year 2025-06-30..2026-06-30 (or the round-61 sub-window) was PRINTED against a frontier bar or reference book; a re-read of the same candidate adds no row (dup_of); reference re-runs of the frontier are REF context rows; leg-level reads of #463's own legs by the family lanes are LANE (K_lane, reported, not in the formula).

Ledger: `LOOKS_LEDGER_R1.csv` (141 rows: 71 looks, 23 REF context rows, 21 dup rows, 26 LANE rows).

**sha256 of LOOKS_LEDGER_R1.csv: `f55656b4f1481917efdcef1c7e779bd6fb8f5728ac31396cb2fc86174d118f52`**

## 1. Totals (registered rule)

| total | value | definition |
|---|---|---|
| **K_book** | **71** | all non-REF, non-LANE, non-dup rows |
| **K_size** | **20** | type = SIZE |
| **K_leg** | **51** | K_book - K_size (SWAP 25 + ADD 14 + COMBO 12) |
| **K_lane** | **26** | type = LANE (leg-level lockbox reads of #463's own legs; reported, not in the formula) |

By source (looks only):

| source | looks | SIZE | leg |
|---|---|---|---|
| RESEARCH_LEDGER.md 2.18 (rebalancing add on #397) | 1 | 0 | 1 |
| BOOK_ROUND58_ML.txt / BOOK.md 10g (round 58) | 22 | 7 | 15 |
| BOOK.md 10h (#430 / #429 / #431) | 3 | 0 | 3 |
| BOOK.md 10j (DIP on ES #432 seats, own book) | 3 | 0 | 3 |
| BOOK.md 10k (round 60 / 60b) | 4 | 0 | 4 |
| docs/BOOK_397_ADOPTION_STAGED.md 5 (V347) | 1 | 1 | 0 |
| BOOK.md 10l (round 61 grid, DIP #452 seats, addendum B) | 12 | 3 | 9 |
| BOOK.md 10n (#468) | 1 | 0 | 1 |
| BOOK.md 10o (round 62 sizing rules) | 6 | 6 | 0 |
| BOOK.md 10p (#469 / #470) | 2 | 0 | 2 |
| BOOK.md 10r (Q1a-Q6; first printed 10q) | 8 | 0 | 8 |
| docs/PREREG_frontier_shadows (AG tilt, 10-01 correction) | 1 | 1 | 0 |
| ORB_ROUND64_BE1R_RIDE.md (P1 / P2 in #463) | 2 | 0 | 2 |
| docs/MDL_MAP_R1.md / ledger 2.51 (reference seats, NOISE re-sizing) | 5 | 2 | 3 |
| **total** | **71** | **20** | **51** |

## 2. Cumulative K_book at the time of each past pass

Counted by each look's FIRST print date (a candidate first printed under the old convention or by another lane counts from that date), in ledger order within a day. A pass that is itself a dup row (#444) does not add to its own count.

| past pass | ledger id | date of the print | cumulative K_book then | note |
|---|---|---|---|---|
| round 58's 58d | L020 | 2026-09-25 | **17** |  |
| #444 | L044 | 2026-09-27 | **30** | #444 is recorded as a dup of L015 (58c's '#422 in #397's NOISE slot'); if data-basis re-runs count as looks it would be the 31st |
| #449 (the adoption read) | L046 | 2026-09-27 | **31** |  |
| round-61 best | L053 | 2026-09-27 | **35** |  |
| V2 (10o) | L085 | 2026-09-28 | **49** | V2 and V2-500 are the 48th-49th leg-or-size looks after #468 (10n) and V (10o) |
| V2-500 (10o) | L086 | 2026-09-28 | **50** |  |
| Q4 (10r) | L118 | 2026-10-01 | **63** | Q1a-Q6 were all first printed on 2026-09-30 (10q / ORB round 63), so they count before the 10r re-score |
| Q6 (10r) | L120 | 2026-10-01 | **63** | same day and table as Q4; AG (10-01) is ordered after it |

After Q6: AG tilt (L121, 10-01), ORB round 64's P2 / P1 (10-02), MDL r1's five reference seats and re-sizings (10-04) bring K_book to 71.

## 3. The past passes, each by its printed LB ratio to its own reference

| past pass | id | candidate | reference in force | convention | printed LB | reference LB (same table) | LB ratio | verdict as printed |
|---|---|---|---|---|---|---|---|---|
| round 58's 58d | L020 | #397 with ENGU-Q et@0.55 CUT + NOISE #422 (the 58d book) | #397 | other | 321.0 | 306.3 | **1.0480** | PASS (every clause, thin margins), then REFUTED by the adversarial check |
| #444 | L044 | #444 = #437 with NOISE = run #422 (1.75x compression tilt) | #437 | other | 309.8 | 293.3 | **1.0563** | MISSES clause 3 only, by $767 (LB DD at close $27,955 vs cap $27,188) |
| #449 (the adoption read) | L046 | #449 = #436 with NOISE #422 in the NOISE slot | #436 | other | 310.8 | 294.4 | **1.0557** | CLEARS all four clauses (15 of 15 years) |
| round-61 best | L053 | round-61 best: best of the 18-book grid = NOISE #422 raw + ORB #257 raw + ENGU-Q book leg + TTM #368 KEEL x3 (LB as run 402.9) | #449 | other | 284.6 | 197.3 | **1.4425** | misses clause (4) (LB DD at the WF-matched size $33,098, +9.8%) |
| V2 (10o) | L085 | V2: book vol target vs its own trailing year (20-day vol / median of prior 250 days, clip 0.5-2.0) | #463 | old | 259.3 | 164.8 | **1.5734** | PASS both stretches; a tail hedge (two episodes); not adopted -> nightly VT shadow |
| V2-500 (10o) | L086 | V2-500: V2 sensitivity, 500-day reference | #463 | old | 239.5 | 164.8 | **1.4533** | PASS |
| Q4 (10r) | L118 | Q4 ORB #314 + ENGU-Q gate S1 together, post-hoc (run #476) | #463 | unified | 177.6 | 155.5 | **1.1421** | PASS (post-hoc) -> forward paper shadow book_shadow_q4, never an adoption |
| Q6 (10r) | L120 | Q6 ORB #239 (#234's settings with breakeven 0.8 R) in the ORB seat (run #478) | #463 | unified | 158.7 | 155.5 | **1.0206** | PASS (clears the bar narrowly in both stretches) -> owner call: shadow first (book_shadow_orb239); #463 stays adopted |

Context (not re-verdicts): #449 was adopted on more than the lockbox (clauses 1-8, BOOK.md 10m); V2 failed RISK r1 (ledger 2.47); Q4 is post-hoc; Q6 = ORB #239 in the ORB seat is a forward shadow. 58d, #444 and #449 are on the old $100k-at-size ROC convention and the round-61 best is on the sub-window at the WF-set $30k size; V2 / V2-500 on the old $30k convention; Q4 / Q6 unified.

## 4. The ten calibration reads (BOOK.md 10n / 10p / 10r)

| read | id | convention | WF ROC | LB ROC | reference LB | LB ratio | ln(ratio) |
|---|---|---|---|---|---|---|---|
| #468 | L081 | old | 72.1 | 163.6 | 164.8 | 0.9927 | -0.0073 |
| #469 | L099 | old | 82.9 | 149.1 | 164.3 | 0.9075 | -0.0971 |
| #470 | L100 | old | 82.6 | 166.9 | 164.3 | 1.0158 | 0.0157 |
| Q1a | L113 | unified | 125.6 | 147.3 | 155.5 | 0.9473 | -0.0541 |
| Q1b | L114 | unified | 108.5 | 146.3 | 155.5 | 0.9408 | -0.0610 |
| Q2 | L115 | unified | 69.6 | 169.0 | 155.5 | 1.0868 | 0.0832 |
| Q2ctx | L116 | unified | 85.1 | 145.6 | 155.5 | 0.9363 | -0.0658 |
| Q3 | L117 | unified | 84.5 | 188.4 | 155.5 | 1.2116 | 0.1919 |
| Q5 | L119 | unified | 103.1 | 149.6 | 155.5 | 0.9621 | -0.0386 |
| Q6 | L120 | unified | 101.8 | 158.7 | 155.5 | 1.0206 | 0.0204 |

sd of ln(LB ratio) over the ten = 0.0859 (sample sd, n = 10); mean -0.0013. Note #468 / #469 / #470 are on the old $30k convention (reference 164.8 / 164.3) and Q1a-Q6 on the unified one (155.5); each ratio is to the reference printed in its own table, as the pre-registration asks. The old-convention prints of Q1a-Q5 are in the ledger as dup rows (L101-L107) if the harness prefers one convention.

## 5. Alternative counts (so a different reading of the rule is one subtraction or addition away)

| count | value | what it adds to / removes from K_book = 71 |
|---|---|---|
| K_book_rerun | 78 | + 7 data-basis re-runs by the same lane recorded as dups: #444 (L044), #446 (L045), #457 (L067), #466 (L076), #462 (L077), #465 (L078), #464 (L079) |
| K_book_ext (round 56 added) | 80 | + 9 looks from BOOK_ROUND56_ROC.txt (2026-09-24, outside the registered 10g-10s scope): Test A re-weights A1 / A2 (LB $327,319 / $336,974 vs $306,042; SIZE x2), + ENGU-Q on ES #370 x0.5 / x1 (LB 360.3 / 414.2 vs 306.3), + NQ 15m squeeze #280 x0.5 / x1 (315.4 / 324.5), both x1 (432.5), hindsight ORB x0.5 (270.5; SIZE), hindsight squeeze x4 (329.0; SIZE); its '#397 with NOISE #382 in the slot' (327.6) would become the primary of L007, not a new look. K_size would be 24 |
| K_book_scored (ceiling) | 181 | + candidates that were SCORED on the lockbox but print no figure of their own in git (verdict-only / unprinted; NOT counted under 'printed'): 58a's other 50 books, 58b's 2 volatility-dial books, round 61's other 11 grid books, the other 19 rebalancing weightings (ledger 2.18, 'the lockbox drawdown rises in every one'), the 18 crash-short cells (ledger 2.16; the script prints LBnet / bkLBr per cell, the ledger row does not), MDL r1's +25..100% re-sizing of ORB / ENGU-Q / TTM (>= 6) and its 4 leave-one-out books |
| K_book_minus_arguable | 68 | - the 3 looks whose inclusion is the weakest call: #441 (own two-leg DIP book, L041), the flat NOISE x1.2 leverage control (L026), the rebalancing nearest weighting with no ROC figure (L003) |

The pre-registration's resolution paragraph assumed K_leg ~ 156 and K_size ~ 10; the printed-figure floor gives K_leg = 51 and K_size = 20. The margin curve is printed at every K, so the choice of count moves the headline only.

## 6. K_lane - leg-level lockbox reads of #463's own legs (reported, not in the formula)

| leg | LANE looks | rows | where |
|---|---|---|---|
| ENGU-Q #335 (paper cell) | 16 | L027, L028, L029, L068, L091, L092, L093, L094, L095, L096, L097, L111, L130, L131, L132, L133 | BOOK_ROUND58_ML.txt 6 + 58d (3 gate transplants), ENGUQ.md hold cap (1 of 5 caps printed), rf HYBRID on the paper cell, round 62 S1 + 5 plateau windows, round 65, round 66 + 3 plateau thresholds |
| NOISE #422 | 5 | L069, L070, L071, L072, L126 | NOISE.md round 62 (#422 + KEEL v12; without the squeeze multiplier), NOISE #447 memory cells 68 / 160, round 68 breakeven |
| ORB #234 | 3 | L001, L002, L125 | ORB.md 09-05 (#239 $94,268; #314 $92,102 - flagged), ORB_ROUND64 P2 standalone |
| TTM #459 | 2 | L128, L129 | tools/data/ttmsqz_r22a_breakeven.txt (22A / 22B); TTM.md prints no #459 lockbox read |
| **K_lane** | **26** | | lane reference twins are REF rows (L090, L042, L124, L127) |

Lane reads NOT counted: the late-fill stress read of #422 (NOISE.md round 61), round 68 on #382, rounds 63-67 / 69 (on #304 / #243, or lockbox not read), the partial exit (on #309), the validate-champion cell reads (not the traded leg), ORB round 64's P1 / D1 / D2 (#314 variants), ORB round 7's #325 (on #314), TTM rounds 20 / 21 (other cells and sleeves), the four unprinted ENGU-Q hold caps, the six unprinted NOISE #447 memory cells.

## 7. Judgment calls (every one, numbered; the row-level text is in the csv's judgment column)

1. **Printed figure, not printed verdict.** A candidate counts only when a numeric lockbox figure of its own (ROC, net, drawdown or an explicit delta) is printed in git against the reference. Candidates covered only by an aggregate verdict ('NO PASS' for 58a's 60, 'rises in every one' for the 20 rebalancing weightings, 'every cell lowers #397's MAR' for the 18 crash-short cells, 'the median of the 18 reads 94.0') are not counted; section 5 gives the ceiling. This follows the pre-registration's own sentence 'unprinted scans that were run and discarded are not counted, so K is a floor', even though its QUESTION paragraph cites 'round 58's ~71 books, round 61's 18 ... the crash-short and rebalancing cells' as if all were looks.
2. **Same candidate, new data basis = dup.** #444 (= 58c's #422-in-#397's-slot on roll-corrected masters), #446 (= 58a's #382 row), #457 (= addendum B's #422 + fixed tilts on the standard window), #466 / #462 / #465 / #464 (bug-fix re-runs of #457 / #456 / #450 / #448) are dup rows. The rule names only 'another lane', so this extension to same-lane re-runs is a call; K_book_rerun (section 5) is the other reading. #438 is REF because the rule lists it, although it is the #430 candidate re-run.
3. **Same candidate, new convention = dup.** The 10q (old) and 10r (unified) prints of Q1a-Q5 are one look each; the 10r unified rows are primary (the registered calibration set names 10r) and the 10q prints are dup rows with their own ratios. ORB round 63's three reads of #314 / #257 / #239 in #463 are dups of Q1a / Q1b / Q6 (another lane). MDL r1's #239 / #257 / S1 reference seats are dups of Q6 / Q1b / Q3 (S1's MDL figures differ slightly: rebuilt from rule-U records).
4. **Different base book = different look.** #449 (#422 on #396's legs) is distinct from #444 (#422 on #397's legs); #429 (#366 + #382) from #430 (#396 + #382); DIP on ES #452 as a seat in #463 (MDL) from #453 / #454 (seats in #436), which are themselves distinct from #440 / #439 (DIP #432, the pre-roll-correction run) - the last pair is the most arguable (flagged on the rows).
5. **SIZE typing.** KEEL v12 overlays (58c, 4 rows), the fixed-tilt / KEEL 7-seed NOISE packages (addendum B, 3 rows), the 58d book at 1.7x / 1.8x and the flat #304 x1.2 control (3 rows), V347 whole-contract rounding, the AG tilt, MDL's NOISE +25% / x2, and all six round-62 rules are SIZE. 'O sensitivity: skip the overlap' is a filter typed SIZE because the registered type list has no FILTER type. #422 in the seat (58c, #444, #449), TTM R347 (#448 / #450) and TTM #458 (#468) are typed SWAP although each is the same mechanism re-sized - the N-LEG null is the closer stand-in because a different validated run sits in the seat.
6. **COMBO for round 61's ML-twin reads.** The five 'ML leg vs its raw twin inside the best book' reads (ORB tree / raw, ENGU-Q rf / raw, TTM #368 raw) are grid books whose LB figures were printed in prose; their reference (197.3) is the section's table, not the same bullet. Counted as looks; 11 grid books remain unprinted.
7. **Round-61 figures used.** For the sub-window rows the LB ROC 'at the WF-set $30k size' is recorded as lb_roc (the bar's clause 3), the 'as run' figure in the candidate text; the reference is #449's at-$30k LB (197.3, or 196.2 in addendum B).
8. **#441 (DIP on ES + DIP on NQ, its own book)** is counted as a COMBO look: a candidate book printed with its LB in the reference table, even though it was 'not gated'.
9. **The rebalancing nearest weighting (L003)** is counted as a look with lb_ratio blank: its printed LB figures are '+3.5% net' and '+6.0% drawdown' relative to #397, not a ROC. The script's 20 weightings are 4 legs x 5 sizes.
10. **AG tilt (L121)** is a look: the 10-01 correction printed 'LB 177.7 at $30k' beside 'WF 92.8 vs 92.7' (old convention); #463's old-convention LB 164.8 is taken from 10o because no reference LB sits on that line.
11. **V347 (L049)** comes from docs/BOOK_397_ADOPTION_STAGED.md section 5, which is not on the registered source list but is linked from BOOK.md 10k; V428 and V428_347 there are the same prints as #445 / #450.
12. **Q2ctx** is counted as a look (a candidate book printed with its LB against #463, and one of the ten calibration reads) despite its 'context' label.
13. **Not looks, by the rule:** 58b's two volatility-dial books (pre ROC only); 10l's 'DIP #452 added to the best book' and addendum B's ORB #314-base reads (WF only); 10s's V3 (WF / LB never computed); RISK r1's rule S (IS* only; its P3 is a V2 parity re-read); the KEEL shadow (no backtest LB printed); MDL's NQBRD 0.70 (LB sealed) and 224,000 synthetic legs; ledger 2.12 (REF context), 2.13-2.15, 2.17, 2.19, 2.24, 2.29, 2.31, 2.33, 2.35-2.43, 2.45, 2.46, 2.48-2.50, 2.52 (Stage A only, lockbox sealed, or leg-level on legs that are not #463's); tools/TTM_R23_PREREG.txt and docs/PREREG_frontier_bookq_2026-09-30.txt (reference figures and the Q4 local read only, already counted); the broken #417 / #418 / #419 (no figures in 10h); the 58d book's seed / start-date / cost / day-stamping / boundary / extension re-reads (same candidate).
14. **Out of scope but printed:** BOOK_ROUND56_ROC.txt (2026-09-24) printed nine further candidate lockbox figures against #397 (section 5, K_book_ext); ORB_ROUND55_FRONTIER.txt (09-14), ORB_ROUND53_BOOK_LEG.txt (09-09), BOOK.md 10a-10f and TTM.md's #361 / #371 rows predate 10g and were not read for looks. STUDIES_BOARD.md / RUNBOARD.md / BOOKMARKS.md re-print the same runs and were not used as sources.
15. **K_lane scope.** Lane reads are counted when the candidate is a variant, gate or sizing of #463's own leg (#234, #335 paper cell, #459, #422) with an LB figure printed against the leg; the four lane twins are REF rows. ORB.md's #239 ($94,268) and #314 ($92,102) prints (2026-09-05, ORB's own lockbox window, no #234 LB on the line) are the weakest inclusions and are flagged on the rows; round 66's three plateau thresholds and round 62's five window rows are counted because each prints its own LB figure. The lane lockbox windows differ from the book's (ORB 2025-08-13..2026-08-13; NOISE #422's validate to 2026-07-16; TTM from 2025-07-01).
16. **Dates.** Rows carry the date of the section that printed them; cumulative counts use each look's earliest print (dups included). ORB.md's two lane rows predate the scope (09-05) and are listed first.

## 8. Sources read

Exhaustively: BOOK.md 10g-10s (10g, 10h, 10i, 10j, 10k, 10l incl. addenda A-C, 10m, 10n, 10o, 10p, 10q, 10r, 10s; no 10t+ exists), BOOK_ROUND58_ML.txt (58a-58d, sections 5-9), ORB_ROUND64_BE1R_RIDE.md, ORB_ROUND63_BOOK463_LEG.md, RESEARCH_LEDGER.md rows 2.12-2.52, docs/MDL_MAP_R1.md, docs/PREREG_frontier_bookq_2026-09-30.txt, tools/TTM_R23_PREREG.txt, tools/rocfrontier/PREREG_LOOKS_R1.txt, docs/BOOK_397_ADOPTION_STAGED.md, docs/PREREG_frontier_shadows / keel458 / ttm458 preregs, tools/rocfrontier/rebal_book.py and crash_short_scan.py (to see what they print), tools/data/ttmsqz_r22a_breakeven.txt (+ r20 / r21 files), ENGUQ.md (2026-09-24 .. 10-04 sections), NOISE.md (rounds 61, 62, 68, 69 and the 10-04 decision), ORB.md (crown sections), TTM.md, BOOK_ROUND56_ROC.txt (scope check), plus a repo-wide grep for the reference figures (155.5 / 164.3 / 164.8 / 306.3 / 293.3 / 294.4 / 310.8 / 273.8) to catch prints outside the list.

Files: `/tmp/claude-0/-home-user-EDGE-LOG/7f579229-7020-5946-a590-b17d13a970fb/scratchpad/looks/LOOKS_LEDGER_R1.csv` (sha256 above), `/tmp/claude-0/-home-user-EDGE-LOG/7f579229-7020-5946-a590-b17d13a970fb/scratchpad/looks/LOOKS_COUNT.md`, builder `build_ledger.py` / `build_count.py` in the same folder.
