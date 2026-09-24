# SEARCH-ADJUSTED P-VALUE FOR THE CROWN (RESEARCH.md item 3)

White's Reality Check over each run's ten finalists and their walk-forward folds.
A small p means the best finalist beat what a no-edge search of the same size and
the same fold noise would have produced. **Eight folds is a tiny sample: a large p
means this test cannot separate the crown from luck, not that the strategy is bad.**

Driver `tools/reality_check.py` (20000 bootstrap draws, seed 42).

| Run | Family | Verdict | Finalists | Folds | Crown's rank | Best mean fold net | p (finalists) | p (wider pool) |
|---|---|---|---|---|---|---|---|---|
| #380 | ENGU-Q | PASS | 10 | 8 | 1 of 10 | 2,276 | 0.0193 | 0.0209 (40 cfg) |
| #381 | ENGU-Q | FAIL | 10 | 8 | 1 of 10 | 2,482 | 0.0109 | 0.0109 (40 cfg) |
| #382 | NOISE | PASS | 10 | 8 | 1 of 10 | 2,621 | <0.0001 | <0.0001 (24 cfg) |
| #383 | ENGU-Q | WEAK | 10 | 8 | 1 of 10 | 2,946 | 0.0012 | 0.0013 (40 cfg) |
| #384 | ENGU-Q | WEAK | 10 | 8 | 1 of 10 | 3,027 | 0.0009 | 0.0011 (40 cfg) |
| #385 | NOISE | PASS | 10 | 8 | 1 of 10 | 966 | 0.0001 | 0.0001 (26 cfg) |
| #386 | NOISE | PASS | 10 | 8 | 1 of 10 | 1,008 | 0.0001 | 0.0001 (27 cfg) |
| #387 | NOISE | PASS | 10 | 8 | 1 of 10 | 966 | 0.0001 | 0.0001 (27 cfg) |
| #388 | NOISE | PASS | 10 | 8 | 1 of 10 | 1,659 | <0.0001 | <0.0001 (40 cfg) |
| #394 | NOISE | PASS | 10 | 8 | 1 of 10 | 1,493 | <0.0001 | <0.0001 (40 cfg) |
| #395 | NOISE | WEAK | 10 | 8 | 1 of 10 | 812 | 0.0004 | 0.0035 (40 cfg) |
| #398 | NOISE | PASS | 9 | 8 | 1 of 9 | 813 | 0.0015 | n/a |
| #399 | GAPGO | FAIL | 10 | 8 | 1 of 10 | 1,100 | <0.0001 | <0.0001 (40 cfg) |
| #400 | NQDIP | FAIL | 10 | 8 | 1 of 10 | 20,433 | 0.0059 | 0.0069 (40 cfg) |
| #401 | NQDIP | FAIL | 10 | 8 | 1 of 10 | 11,498 | 0.0296 | <0.0001 (40 cfg) |
| #402 | ENGU-Q | WEAK | 10 | 8 | 1 of 10 | 2,301 | 0.0053 | 0.0092 (40 cfg) |
| #403 | ORB | FAIL | 10 | 8 | 1 of 10 | 935 | 0.0701 | 0.1087 (40 cfg) |
| #404 | ORB | FAIL | 10 | 8 | 1 of 10 | 1,545 | 0.0215 | 0.0163 (40 cfg) |
| #405 | NOISE | WEAK | 10 | 8 | 1 of 10 | 1,229 | 0.0123 | 0.0124 (40 cfg) |
| #406 | NOISE | PASS | 10 | 8 | 1 of 10 | 1,758 | 0.0001 | 0.0003 (40 cfg) |
| #407 | ENGU-Q | PASS | 10 | 8 | 1 of 10 | 1,900 | 0.0032 | 0.0046 (40 cfg) |
| #409 | NOISE | PASS | 10 | 8 | 1 of 10 | 2,621 | <0.0001 | <0.0001 (24 cfg) |
| #410 | NOISE | PASS | 10 | 8 | 1 of 10 | 3,151 | <0.0001 | <0.0001 (24 cfg) |
| #411 | ETFDIP | FAIL | 10 | 8 | 1 of 10 | 2,681 | 0.1793 | 0.2198 (38 cfg) |
| #412 | ETFDIP | WEAK | 10 | 8 | 1 of 10 | 8,131 | 0.0534 | 0.0896 (29 cfg) |
| #413 | ETFDIP | WEAK | 10 | 8 | 1 of 10 | 14,474 | 0.0013 | 0.0006 (40 cfg) |
| #414 | ETFDIP | FAIL | 10 | 8 | 1 of 10 | 7,969 | 0.0029 | 0.1417 (40 cfg) |
| #415 | ETFDIP | WEAK | 10 | 8 | 1 of 10 | 15,523 | 0.0092 | 0.0078 (40 cfg) |

**Summary.** 28 runs tested. Against the finalists: median p 0.001, 25 below 0.05. Against the wider pool (27 runs have one): median p 0.001, 23 below 0.05.

**Read this before quoting it.** The finalists trade the same tape with near-identical settings, so their fold results are highly correlated, and a multiplicity adjustment over correlated candidates is WEAK by construction. That is why nearly every run clears the bar: the test is closer to asking whether the best finalist's mean fold result is large next to fold-to-fold noise than to asking whether the SEARCH found something. It adjusts for ten when the search looked at nine hundred, and not at all for how many rounds a family has had. Item 1 is the test that answers that; this is not a substitute.

The crown's rank column is where the crowned config sits among its own
finalists on mean fold net - a rank far from 1 means the crowning rule chose
something other than the walk-forward leader, which it is entitled to do
(it ranks on the fold TOTAL and the count of folds held, not the mean).

## 2026-09-24 - how much this table is worth (measured)

The search-adjusted p-value in this table clears every PASSED run, and that is close to the
problem. Four measurements, all on the cached run documents:

1. **It does not discriminate.** Seven of the eight FAIL/WEAK runs in #385-#410 clear the same
   0.05 bar the PASSes clear, and a stored-FAIL run (GAPGO #399, p 0.000107) outscores most of the
   PASSes. Necessary, not sufficient - never cite it in a crown decision.
2. **The multiplicity correction is usually small and occasionally decisive.** Ratio of the
   adjusted p to the crowned row alone: median about 1.16x across the cached runs, but 3 runs
   exceed 10x (ENGU-Q #380 387x or more, ENGU-Q #402 107x, ENGU-Q #383 24x). Report the ratio.
3. **It adjusts for ten when the search looked at hundreds.** Read at the true search size, two
   PASSED runs stop being significant: NOISE #406 (2,144 configurations) 0.0001 -> about 0.18 and
   ENGU-Q #407 (1,486) 0.0032 -> about 0.89. Both are lockbox-length arms, neither is a crown, so
   nothing unwinds - but neither may be promoted on its walk-forward record. Record n_evaluated.
4. **Some headline p-values are resolution limits, not tails.** With eight folds a re-centred mean
   cannot exceed (best fold - mean fold), so several runs' own p is a structural zero at any number
   of draws (NOISE #409 is still exactly 0.000000 at 2,000,000). Print "below the resolution of an
   eight-fold resample", not "<0.0001". The fix is more folds, not more draws.
