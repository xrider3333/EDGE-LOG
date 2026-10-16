# LW44 PAIRED SHARPE r1: result (2026-10-16)

**Setup:**
- Prereg: `docs/PREREG_lw44_paired_sharpe_r1_2026-10-16.md` (LF sha256 30b2a66c..., branch prereg/orb-lw44-r1 = 43e6f81f, pushed before the run).
- Harness: `tools/lw44_paired_sharpe_r1.py` (LF sha256 ede56e8b...). Test module `augur_engine/sharpe_diff.py` (704559490f..., b667b674).
- Every hash was checked at start: the note, the test module, book_sizing.py, drawdowns.py and all 20 input caches.
- Output: `C:\EdgeLog\_anatomy_cache\lw44\lw44_r1_result.json` and `lw44_r1_stdout.txt`.
- Scope: cached daily series only; each claim's own walk-forward rows; no lockbox row; no engine run.

**Source:** reading shelf No. 44, Ledoit & Wolf (2008), "Robust performance hypothesis testing with the Sharpe ratio" (MANAGER #96).
- The test: a paired Sharpe-difference test that allows fat tails and serial correlation.
- Method: the studentized circular block bootstrap (block 20, 4,999 draws), plus the prewhitened HAC test.
- The design was checked by a 6-agent adversarial review and a recheck before the freeze.

## Headline

**3 of 15 claimed lifts SURVIVE, all three also after Holm, and all three are NOISE: P16, P18, P22. The other 12 are NOT SHOWN; none is
REVERSED.**
- Every ORB, TTM, ENGU-Q, DIP, V2, RESMOM and seat-swap lift reads NOT SHOWN on Sharpe.
- **Read NOT SHOWN as unproven, not as refuted.** Most of those claims were ROC @ $30k lifts, and ROC @ $30k turns on the worst drawdown. This
  test reads mean over sd. MDE80 says how big a Sharpe gain each pair could have shown.

**Of the 6 keep-decisions, 5 AGREE (no difference) and 1 DISAGREES.**
- P11: the r70 NOISE short tilt, recorded DEAD on the ROC bootstrap, beats its size-matched twin on Sharpe.
- +0.049 (95% +0.003 .. +0.096), p 0.036. Report-only and in-sample (the WF side split was seen before the tilt was written).

## Every pair

- SR diff = candidate minus baseline, Sharpe per row x sqrt(252), with the 95% bootstrap interval.
- The four numbers per side: ROC @ $30k / DD5 at $30k / DD % from peak at $30k / Sortino, on the primary walk-forward rows.
- "1 ep" = one-episode drawdown.

| id | group | claim | SR diff (95%) | p | MDE80 | reading | candidate | baseline | pre-WF diff (report) |
|---|---|---|---|---|---|---|---|---|---|
| P16 | LIFT | NOISE x1.25 forward line vs #463 | +0.051 (+0.020 .. +0.082) | 0.002 | 0.044 | **SURVIVES** | 99.83 / $24,802 / 11.02 / 3.967 | 93.81 / $24,145 / 11.44 / 3.816 | -0.005, p 0.81 |
| P18 | LIFT | #463 (NOISE #422 seat) vs #471 (#304 in the seat) | +0.104 (+0.053 .. +0.156) | 0.0006 | 0.073 | **SURVIVES** | 93.81 / $24,145 / 11.44 / 3.816 | 85.12 / $23,725 / 12.01 / 3.539 | +0.031, p 0.37 |
| P22 | LIFT | NOISE #422 + KEEL v12 fixed package vs raw #422 | +0.195 (+0.062 .. +0.328) | 0.003 | 0.184 | **SURVIVES** | 109.05 / $22,480 / 10.05 / 5.175 (1 ep) | 84.65 / $21,832 / 9.97 / 4.205 (1 ep) | +0.061, p 0.52 |
| P19 | LIFT | crown NOISE #422 vs #382 | +0.170 (-0.019 .. +0.358) | 0.077 | 0.267 | NOT SHOWN | 84.65 / $21,832 / 9.97 / 4.205 (1 ep) | 80.20 / $25,904 / 10.68 / 3.533 | -0.013, p 0.92 |
| P04 | LIFT | DIP #424 on QQQ: fixed size (live) vs KEEL v12 | +0.195 (-0.072 .. +0.461) | 0.144 | 0.366 | NOT SHOWN | 21.32 / $22,076 / 15.85 / 2.527 (1 ep) | 19.47 / $22,097 / 17.84 / 2.225 (1 ep) | - |
| P01 | LIFT | #463 with TTM vs without | +0.085 (-0.036 .. +0.206) | 0.168 | 0.174 | NOT SHOWN | 93.81 / $24,145 / 11.44 / 3.816 | 99.56 / $27,599 / 11.40 / 3.532 | +0.426, p 0.016 |
| P07 | LIFT | RESMOM line L vs #463 | +0.076 (-0.058 .. +0.210) | 0.266 | 0.187 | NOT SHOWN | 121.06 / $28,248 / 9.87 / 3.926 | 93.81 / $24,145 / 11.44 / 3.816 | - |
| P14 | LIFT | #473: ORB #314 in the ORB seat vs #463 | +0.047 (-0.063 .. +0.158) | 0.389 | 0.149 | NOT SHOWN | 125.55 / $28,257 / 8.57 / 3.947 | 93.81 / $24,145 / 11.44 / 3.816 | +0.043, p 0.44 |
| P05 | LIFT | ENGU-Q on QQQ: NQ signals (B) vs QQQ bars (A) | +0.172 (-0.293 .. +0.636) | 0.462 | 0.645 | NOT SHOWN | 28.42 / $23,823 / 9.56 / 1.642 | 19.91 / $23,884 / 13.36 / 1.276 | - |
| P13 | LIFT | KEEL line: TTM #458 x KEEL vs RAW twin #468 | -0.079 (-0.424 .. +0.265) | 0.521 | 0.278 | NOT SHOWN | 119.66 / $26,501 / 8.45 / 4.275 | 113.84 / $27,207 / 10.10 / 3.894 | +0.089, p 0.25 |
| P21 | LIFT | crown ORB #314 vs #234 | +0.075 (-0.210 .. +0.359) | 0.594 | 0.381 | NOT SHOWN | 35.82 / $22,382 / 17.45 / 2.223 (1 ep) | 34.49 / $23,320 / 19.50 / 2.092 | +0.064, p 0.68 |
| P12 | LIFT | V2 vol target vs #463 raw | +0.030 (-0.141 .. +0.202) | 0.708 | 0.226 | NOT SHOWN | 117.81 / $26,941 / 11.01 / 3.914 | 93.81 / $24,145 / 11.44 / 3.816 | -0.173, p 0.14 |
| P02 | LIFT | NOISE #382 + KEEL v12 (live) vs raw #382 | +0.036 (-0.212 .. +0.284) | 0.766 | 0.346 | NOT SHOWN | 82.90 / $25,993 / 11.96 / 3.938 | 80.63 / $25,904 / 10.68 / 3.549 | -0.062, p 0.63 |
| P15 | LIFT | #478: ORB #239 in the ORB seat vs #463 | +0.003 (-0.026 .. +0.032) | 0.863 | 0.040 | NOT SHOWN | 101.76 / $25,897 / 10.87 / 3.836 | 93.81 / $24,145 / 11.44 / 3.816 | +0.005, p 0.80 |
| P20 | LIFT | NOISE #382 size tilt vs #304 | +0.015 (-0.161 .. +0.191) | 0.876 | 0.251 | NOT SHOWN | 80.20 / $25,904 / 10.68 / 3.533 | 66.01 / $22,022 / 8.95 / 3.526 (1 ep) | +0.139, p 0.29 |
| P11 | KEEP | plain NOISE (kept) vs r70 shorts x1.5 (DEAD) | -0.049 (-0.096 .. -0.003) | 0.036 | 0.063 | **DISAGREES** | 97.10 / $24,503 / 11.21 / 3.902 | 100.54 / $24,380 / 10.99 / 4.024 | - |
| P03 | KEEP | Webull NOISE_382 (kept) vs the #422 file on QQQ | -0.164 (-0.375 .. +0.048) | 0.130 | 0.295 | AGREES | 83.14 / $25,701 / 7.92 / 3.534 | 73.15 / $20,611 / 7.98 / 4.124 (1 ep) | - |
| P08 | KEEP | ENGU-Q x1.00 in L (kept) vs the x0.75 rung | -0.036 (-0.104 .. +0.032) | 0.273 | 0.089 | AGREES | 121.06 / $28,248 / 9.87 / 3.926 | 126.10 / $28,365 / 10.54 / 4.074 | - |
| P17 | KEEP | #463 (kept) vs #468 (TTM #458) | -0.025 (-0.074 .. +0.024) | 0.319 | 0.068 | AGREES | 93.81 / $24,145 / 11.44 / 3.816 | 113.27 / $27,207 / 10.00 / 3.889 | +0.092, p 0.18 |
| P09 | KEEP | #463 (kept) vs #463 + TREND seat | +0.016 (-0.137 .. +0.170) | 0.833 | 0.216 | AGREES | 93.81 / $24,145 / 11.44 / 3.816 | 106.36 / $24,707 / 9.28 / 3.707 | +0.034, p 0.70 |
| P06 | KEEP | ENGU-Q seat in L (kept) vs its always-on twin | -0.017 (-0.243 .. +0.210) | 0.883 | 0.311 | AGREES | 121.06 / $28,248 / 9.87 / 3.926 | 96.41 / $25,444 / 9.78 / 3.907 | - |

**Sensitivity:**
- Every verdict is the same at block 5 and block 60, and the HAC p agrees with the bootstrap p in every pair.
- Holm over the 15 LIFT pairs keeps all three survivors (largest p 0.0032 vs its Holm bar 0.0038).
- Clusters: P18 is the one survivor in the P18/P19/P20 cluster, and P22 in P02/P22. No ORB, TTM or ENGU-Q cluster has a survivor.

## What it means

**1. NOISE is the only family whose claimed gains read as real on Sharpe.**
- **P18:** #422 earns its seat in the book over #304 (+0.104, the tightest interval in the set).
- **P16:** adding NOISE to #463 raises the book's Sharpe at the margin (+0.051, 95% +0.020 .. +0.082).
- **P22:** the KEEL v12 fixed package on #422 beats raw #422 (+0.195).
- P16's x1.25 weight and P22's KEEL design were picked with these rows in view, so their p-values are optimistic.
- P16 is the one survivor that is a book change. At $30k, DD5 moves from $24,145 to $24,802 (the book bar asks "DD5 no worse"). A
  FRONTIER/STRATEGY-BEATING call, flagged to MANAGER.

**2. The big ROC lifts are drawdown-shape gains, not Sharpe gains.**
- P14 (ORB #314 seat): 125.6 vs 93.8 ROC, but Sharpe +0.047, p 0.39.
- P07 (RESMOM line): 121.1 vs 93.8, p 0.27.
- P12 (V2): 117.8 vs 93.8, p 0.71.
- They change the worst drawdown and DD % much more than the day-to-day ratio. That is consistent with 2.118's "half is the 2020 crash".
  They are not refuted, and they are not demonstrated.

**3. Crowns.**
- ORB #314 over #234 (P21): not shown. It needs about 0.38 Sharpe to show, and has 0.075.
- NOISE #422 over #382 (P19): close, p 0.077.
- The fixed-size DIP choice (P04): not shown.
- TTM in the book (P01): not shown on WF, but +0.43 on the pre-WF rows (p 0.016, report-only).
- Crown choices on these legs rest on judgment and forward data, not on a demonstrated Sharpe gap.

**4. Keep-decisions.**
- Five keeps are consistent with "no difference".
- The r70 short tilt (P11) is the one place the house's rejection is contradicted: its Sharpe gain is small (+0.049) but significant on its own,
  and in-sample. NOISE lane to judge.

**5. As a house tool.** `augur_engine/sharpe_diff.py` is ready to be the house paired test.
- It checks out against the authors' algorithm, its synthetic size is 4.5-5.9%, and it has 12 unit tests.
- Use it beside, not instead of, the ROC @ $30k bootstrap. The two answer different questions: the day-to-day ratio vs the drawdown path.

**Not run:** the 7 claims that need an engine rebuild, plus the other exclusions, all named in the prereg.
