# PREREG: LW44 PAIRED SHARPE r1 - do the house's recent claimed lifts survive a robust paired Sharpe test? (ORB lane, 2026-10-16)

**Why.** Reading shelf No. 44: Ledoit & Wolf (2008), "Robust performance hypothesis testing with the Sharpe ratio", Journal of Empirical
Finance 15, 850-859. MANAGER #96 moved it to the ORB lane:
- run the bootstrap Sharpe-difference test on the last ~20 claimed lifts across the families (candidate vs crown, same days);
- report how many survive, with each one's interval;
- report-only; it may become the house paired test;
- pre-walk-forward or already-read walk-forward rows only, nothing new opened.

A 6-agent adversarial review checked this design before the freeze (pairs, method, protocol). Its fixes are in this note.

## The test

`augur_engine/sharpe_diff.py`, frozen at commit b667b674 (LF sha256 704559490f7b3dd1c393c9b8ccdd5333321ddd4ff5269ea55246570a5e3af894). It
follows the authors' reference code:
- the delta-method HAC standard error with a prewhitened Parzen kernel (Andrews 1991 plug-in, VAR(1) prewhitening with the Andrews-Monahan
  0.97 singular-value cap);
- the studentized circular block bootstrap, floor(T/b) blocks, each draw's standard error the Goetze-Kuensch block estimate.

Additions:
- Both series are standardised for the HAC step (the ratios do not depend on units).
- Constant series are refused, and proportional series return p = 1.
- A bootstrap draw with a zero-variance side counts as extreme.

The test was checked on synthetic data: null size 4.5-5.9% at 5% across AR(1), GARCH, near-duplicate, sparse and t3 designs; interval coverage
93.5-96.7%. It has 12 unit tests.

**Settings:**
- Block b = 20 rows, fixed a priori (the paper also offers a calibration step, not used); M = 4,999 draws; seed 7.
- p = (1 + #{|d* - d| / se* >= |d| / se}) / (M + 1). The 95% interval is d +/- q x se, with q the order statistic that makes "interval
  excludes 0" equal to "p < 0.05".
- Sharpe ratios are per row x sqrt(252), for reading only. Book-calendar pairs carry UTC Sunday rows (about 292 rows a year, the same on both
  sides), so their annualised levels are not on the same scale as business-day pairs. p-values do not depend on this.

**Also printed for every pair:**
- the HAC p and interval;
- the bootstrap p at b = 5 and b = 60 (sensitivity);
- MDE80 = 2.8 x HAC se (the smallest Sharpe difference the pair could show at 80% power);
- the correlation of the two sides;
- the four numbers per side: ROC @ $30k, DD5 and DD % from peak at the size whose worst drawdown is $30k (account from $100k), and Sortino.
  DD5 and DD % at the series' own size are printed too, so book pairs can be checked against the ledger.

## Rows

- **PRIMARY:** the claim's own walk-forward stretch, or the book's walk-forward where the pair is read inside the book or has no common own
  stretch (P21). Windows are in the table. No lockbox row is read in any pair; P12's V2 multipliers are built from rows up to 2025-06-29 only.
- **SECONDARY, report-only:** the pre-walk-forward rows from 2010-06-07 to the day before each pair's primary window or 2016-06-30, whichever
  is earlier, with four numbers per side.
  - Pairs: P01, P02, P09, P12, P13, P14, P15, P16, P17, P18, P19, P20, P21, P22.
  - P03 is not read: its pre-window rows fall outside the book's pre-WF convention.
  - P04-P08 and P11 have no rows before their walk-forward (WF-only files).
  - Many candidates were tuned on these rows, so this is not a test.
- **Every primary read uses the rows the claim was made on.** The test asks whether a claimed difference is distinguishable from noise on its
  own rows, not whether it holds out of sample.

## Groups and verdicts (set now)

**LIFT** = the ledger claimed the candidate better on its WF rows, or the house adopted it, crowned it or opened a forward line on it.
- **SURVIVES**: candidate Sharpe > baseline Sharpe AND bootstrap p < 0.05 (b = 20).
- **SURVIVES HOLM**: also passes Holm's step-down on the two-sided bootstrap p over the LIFT pairs tested (15 today; family-wise 5%).
  P15 counts in LIFT and in Holm by the rule above, although its claim is drawdown-only and the test is nearly blind to it (see caveats).
- **REVERSED**: the 95% bootstrap interval lies entirely below 0.
- **NOT SHOWN**: otherwise. Printed with MDE80. NOT SHOWN never reads as refuted.

**KEEP** = the house reported a null or rejected a challenger. The candidate is the side the house KEPT. These are reported only, outside
Holm.
- **CONFIRMS THE KEEP**: the kept side is better at p < 0.05.
- **DISAGREES**: the 95% interval is entirely below 0 (the rejected side is better).
- **AGREES (no difference)**: otherwise.

**Parity:** a pair whose two sides do not reproduce the frozen ROC @ $30k within 0.1 point is DROPPED and named, with no test read. All 21
reproduce today.

**Selection rule:**
- Included: every ledger or crown claim dated 09-05..10-15 whose headline is a WF ROC @ $30k (or MAR) difference between a candidate and an
  incumbent, with both daily series already cached and parity-reproducible, plus the house's keep-decisions on the same basis.
- Excluded claims are named below with one reason each.

## The pairs

Daily $. Book pairs use `rocfrontier\r4\book463_daily.csv` (`mtm`, `L0..L3_mtm` = ORB #234, ENGU-Q, TTM #459 x3, NOISE #422; valued daily)
on its own calendar. Sparse leg files are put on that calendar, or on business days for leg pairs, with zeros. "Expected" = this harness's
reproduction; "ledger" = the claimed figure where it differs.

| id | grp | source | candidate | baseline | primary rows | expected cand / base | ledger, if different |
|---|---|---|---|---|---|---|---|
| P01 | LIFT | 2.175 (TTM kept) | mtm | mtm - L2 | 2016-07-01..2025-06-29 | 93.81 / 99.56 | |
| P02 | LIFT | 2.160 (#382 + KEEL v12 live) | replay_NOISE_382 pnl x 20 x walk_size, by entry day | pnl x 20 | 2016-06-30..2025-07-15 | 82.90 / 80.63 | 83.0 / 80.7 |
| P05 | LIFT | 2.133 (ENGU-Q needs NQ signals) | q36 B (NQ #335 signals, QQQ fills) | q36 A (the leg on QQQ bars) | 2016-07-01..2025-06-29 | 28.42 / 19.91 | |
| P07 | LIFT | 2.76/2.99 (RESMOM line) | L = book_mtm + 0.264 RES (resmom close file) | book_mtm | 2016-07-01..2025-06-29 | 121.06 / 93.81 | |
| P12 | LIFT | 2.32/2.47 (V2; failed RISK r1, kept as a shadow line) | rule-U records x vt_multipliers at each trade's entry day | rule-U records raw | 2016-07-01..2025-06-29 | 117.81 / 93.81 | 116.1 / 92.7 (r11's own year count) |
| P13 | LIFT | adopt449 PREREG_KEEL458 + keel_results (09-28); BOOK 10p | mtm - L2 + TTM458_keel | mtm - L2 + TTM458_raw (#468) | 2016-07-27..2025-06-29 | 119.66 / 113.84 | 118.55 / 112.61 |
| P14 | LIFT | 2.44 Q1a (#473) | mtm - L0 + X_orb314_raw | mtm | 2016-07-01..2025-06-29 | 125.55 / 93.81 | |
| P15 | LIFT | 2.44 Q6 (#478) | mtm - L0 + leg_ORB_239 (no-adj build; equals the adj leg to the cent) | mtm | 2016-07-01..2025-06-29 | 101.76 / 93.81 | |
| P16 | LIFT | 2.51 / BOOK 10t Q8 (forward line; owner kept 1.0x) | mtm + 0.25 L3 | mtm | 2016-07-01..2025-06-29 | 99.83 / 93.81 | |
| P18 | LIFT | 2.26 as re-read in 10r (Q2ctx #471) | mtm | mtm - L3 + B_noise304 | 2016-07-01..2025-06-29 | 93.81 / 85.12 | |
| P19 | LIFT | NOISE r61 (crown) | X_noise422_raw | X_noise382_raw | 2016-06-30..2025-07-15 | 84.65 / 80.20 | MAR 2.82 / 2.67 |
| P20 | LIFT | 2.8 (#382 tilt crowned) | X_noise382_raw | B_noise304 | 2016-06-30..2025-07-15 | 80.20 / 66.01 | |
| P21 | LIFT | ORB 09-05 (crown) | X_orb314_raw | B_orb234 | 2016-07-01..2025-06-29 | 35.82 / 34.49 | |
| P22 | LIFT | book_legs README_ml_legs_NOISE (09-27) | NOISE422_fixed_daily | NOISE422_raw_daily | 2016-06-30..2025-07-15 | 109.05 / 84.65 | MAR 3.63 / 2.82 |
| P04 | LIFT | 2.134 Q37 QQQ arm (fixed size adopted; DIP_424F went live) | q37 QQQ F fixed at s_bar (KEEL's QQQ mean 1.227x; live is 1.245x, same Sharpe; exit-day booked) | q37 QQQ KEEL v12 | 2017-08-07..2025-08-24 | 21.32 / 19.47 | 21.34 / 19.47 |
| P03 | KEEP | 2.171 (NOISE_382 stays the Webull seat) | q43 S382 | q43 S422 (challenger) | 2017-08-07..2025-06-29 | 83.14 / 73.15 | 83.08 / 73.10 |
| P06 | KEEP | 2.127 (not distinguishable; no change) | L | L - q34 leg + q34 always-on | 2016-07-01..2025-06-29 | 121.06 / 96.41 | |
| P08 | KEEP | 2.81 S1 re-read (report, no verdict; x1.0 kept) | L | L - 0.25 L1 (x0.75 rung) | 2016-07-01..2025-06-29 | 121.06 / 126.10 | registered L 120.82 / 125.83 |
| P09 | KEEP | 2.58 (TREND seat FAILED Stage A) | q9 book463 | q9 book463 + trend_primary | 2016-07-01..2025-06-29 | 93.81 / 106.36 | |
| P11 | KEEP | 2.53 (r70 tilt DEAD) | mtm + 0.135 L3 (plain NOISE, which the house kept, as the size-matched twin) | mtm + r70 diff_usd | 2016-07-01..2025-06-29 | 97.10 / 100.54 | |
| P17 | KEEP | 2.30 / 10n (#463 kept; the deciding stretch was the spent lockbox) | mtm | mtm - L2 + TTM458_raw (#468) | 2016-07-01..2025-06-29 | 93.81 / 113.27 | pre-LB 60.3 / 72.1 (old convention) |

**Families with a tested claimed lift:**
- BOOK, NOISE, ORB, TTM (book level only), ENGU-Q (P05) and DIP (P04, the QQQ arm).
- Group rule applied the same way everywhere: a report that ended in an adoption (P04 fixed DIP live; P05 'ENGU-Q needs NQ signals') is LIFT.
- Overlapping evidence clusters: P06/P07/P08 share L; P13/P17 share #468; P14/P21 are the same ORB swap at two levels; P18 is about P19 + P20
  inside the book; P02/P22 are KEEL on NOISE. Survivors are also reported per cluster.

**Not tested, named:**
- Needs an engine rebuild (not opened here):
  - SUPERSCALPER improved vs as-ported (2.172/2.173)
  - NOISE +1R target and run #490 (2.154/2.166/2.167)
  - ENGU-Q hold cap #491 (2.162)
  - Q4 #476 (2.44)
  - #463 vs #366's re-run #460 (2.30)
  - ENGU-Q #335 vs #309 (09-08)
  - NOISE r65/r66/r67 on #304 (2.36/2.42/2.43)
  - 2.44 Q2/Q3/Q5
  - 2.55 hedge-tilt arm
- Recompute needed (not opened here): the NOISE squeeze arm (2.56). Its squeeze flag must be recomputed from the NQ master (keel_features).
- Summaries only, no cached daily series: Q12 LONGVOL (2.59), Q15 STEEPENER (2.64).
- VOID leg: 2.27's round-61 ML books (TTM #368, stop-bug era).
- Not a paired claim: EVENT SLEEVE (2.138, synthetic legs), DIP #434 vs #424 (2.169, a restatement), 2.124's leave-one-out "every leg earns
  its seat" (outside claimed lifts; P01 covers the TTM seat).

## Read-with caveats (printed beside the verdicts, not changing them)

- **In-sample candidates** (designed or picked with these rows in view): P02, P13, P22 and P04's baseline (KEEL, designed on 2010-26 walks;
  a KEEL flattered in-sample makes a fixed-size win conservative);
  P05, P06 and P08 (ENGU-Q R2 knobs picked on a window to 2025-06-30); P08 (the x0.75 rung was picked after the ladder was read); P11 (WF side
  split seen); P12 (V2 repair); P14 and P15 (seat picks); P16 (weight read off WF + LB); P19, P20 and P21 (crowns chosen with WF in view).
  Their p-values are optimistic.
- **Scale:** ROC @ $30k and Sharpe are both scale-free. The claims were made on ROC @ $30k (and Sortino); this test reads Sharpe (mean over
  sd), not drawdown shape or downside skew. A ROC lift with no Sharpe lift is a drawdown-shape gain (see DD5 and the one-episode flag), not
  leverage.
  - Drawdown-shaped claims: P14 (31.1 of its 31.7 points are the drawdown) and P15 (WF net -$795; all of its ROC lift is the drawdown, one
    episode). A non-survive does not refute them, and a survive would not confirm the ROC size.
- **Sizing lines change the mix:** P16 re-sizes NOISE; P13's KEEL averages 1.81x RAW's size on the same trades, so a book gain mixes TTM weight
  with KEEL's timing. P11's twin is size-matched, so P11 tests the side mix at equal mean size.
- **Same trades re-sized, or one leg swapped:** these pairs are highly correlated, which is where the paired test has most power.

## Pins (checked by the harness before anything is computed; any mismatch = refuse)

- This note's LF sha256 and the test module's (above); also the LF sha256 of `augur_engine/book_sizing.py` (P12's multipliers)
  7c87cb0968896c0f0bd0cc94338a5bab8617661b032718273599b61669acb24f and `augur_engine/drawdowns.py` (the four numbers)
  e31a8404cdb170cec3463be868e3bcaecb2ab38194a73df6c061746cd2f569d5.
- Every input file, raw-byte sha256:

| key | file (under C:\EdgeLog) | sha256 |
|---|---|---|
| book463 | `_anatomy_cache\rocfrontier\r4\book463_daily.csv` | d1543735b5408f50be5971089e00a800f8e510af3d4a63678ff8939f41277dff |
| resmom_close | `_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv` | e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18 |
| q34 | `_anatomy_cache\q34\q34_daily.csv` | d03ef890d7146598d91639fc91a75088559e3784eb8c1437ffe1f29534245b3a |
| q9 | `_anatomy_cache\q9\daily.csv` | 4ef06f5c8d95a1946dfe445a3a2b0118b0667341a0e7b4d36cc1dfb0dc5078ef |
| r70 | `custom_ml\noise_r70_sidetilt_wf_daily_diff.csv` | 2b27c7b9c2c624e86eb47ce6ee08809eaf5740cf95b9b5d7b6b2cc3179b048a2 |
| ttm458_keel | `book_legs\TTM458_keel_daily.csv` | 04fe514f38121c3af6f67e0d67b248b85d9d5b625fbf96862fe7997f6fce5c30 |
| ttm458_raw | `book_legs\TTM458_raw_daily.csv` | 46fdb3f34fbd13e09f32697cf89533a657b120653c4ea30f633d422e75950635 |
| orb314 | `_anatomy_cache\frontier_combo\legs\X_orb314_raw.csv` | 993901498c0851f06f342180bc29f5a765717f27eec2ccce496917f8f1cd7b54 |
| orb234 | `_anatomy_cache\frontier_combo\legs\B_orb234.csv` | 20deecf7cd29a2431c96c9b33ebed12aa521082bacc2eecebbadeccd8c6ef29b |
| orb239 | `_anatomy_cache\rocfrontier\mdl_r1\refs\leg_ORB_239.csv` | 2e3964a8d65777f1886543df962ec5a65d0961f38f4cd496056f4c0f5a639eb3 |
| noise304 | `_anatomy_cache\frontier_combo\legs\B_noise304.csv` | 0c4e30b972a4c0111e6e61b76fb6b7d8c00bd0b6b15c6dad1c32ddf3a1955fe8 |
| noise382 | `_anatomy_cache\frontier_combo\legs\X_noise382_raw.csv` | 41126b857af3b884bc4812993c8cb29bdfd0067d6508acf987e6b5678519fb53 |
| noise422 | `_anatomy_cache\frontier_combo\legs\X_noise422_raw.csv` | 7e6cb0e03da219e8829aa35300b5df0a528bcb831c9bf7d1835663c998cac78a |
| noise422_fixed | `book_legs\NOISE422_fixed_daily.csv` | 57d4d272bcaf2f73c3fc0456fde852837bbb7ec1de303dcd9c95b23124df7dc4 |
| noise422_rawbl | `book_legs\NOISE422_raw_daily.csv` | c51b0a20e806dd543157798972ed87eec371264bea0cdce4b1e506dfb3982646 |
| records_U | `_anatomy_cache\rocfrontier\r11\records_U.npz` | d1774ccf0adc7c9a2a3fb20d99673ddfb4568b63ed7b6875ab08bd5138de8ee2 |
| q43 | `_anatomy_cache\q43\q43_noise_daily.csv` | 6593f22e84983ef71198853c59927661a6321050039b7f501b4c91585ac6e4ba |
| q37 | `_anatomy_cache\q37\q37_daily.csv` | 7de64c400cfe5b53a5b14ee89a0cbd15cbfedb482528d2cf00a4989323a086f5 |
| q36 | `_anatomy_cache\q36\q36_daily.csv` | 4612ca2a367c7cce8a4bbcb0258b565be02a78115a45f27dee633c598ae61f86 |
| keel382 | `_anatomy_cache\keel_parity\pertrade_full\replay_NOISE_382.csv` | 4a6b4a3f9021689fbadad7b1843169f49625ccad380fcf3aaf6c37ec40369c42 |

Report-only: no crown, leg, size or live change.
- Harness: `tools/lw44_paired_sharpe_r1.py`.
- `--parity` builds the pairs and prints only the already-read ROC, Sortino and day counts (no Sharpe, no test).
- The result is saved to `C:\EdgeLog\_anatomy_cache\lw44\lw44_r1_result.json`.
