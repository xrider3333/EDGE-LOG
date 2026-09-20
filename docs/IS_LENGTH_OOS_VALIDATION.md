# How much history to tune on, and how long to seal? In-sample length and out-of-sample validation (2026-09-16)

Owner question: "off of approx 16 years of data, using 15 of those to parametrize (IS/WF) and ranking
off 1 year of lockbox out-of-sample doesn't feel right; I'd guess 2-3 years of LB would be
sufficient. Is 15 years of IS parametrization really needed? And what does the professional /
academic literature say about out-of-sample validation?"

This document combines three inputs:

1. A new EDGELOG experiment (the "candidate matrix"): five strategy mechanisms, each re-scored over
   every training-depth / test-window combination the 16-year record allows, then independently
   re-verified. Only VERIFIED numbers are used; refuted claims are dropped and named.
2. Four literature sweeps (about 50 sources) with a citation check on every one. Sources that do
   not exist, or whose specific claims could not be confirmed, are dropped from the argument or
   flagged. Metadata is corrected where the check found errors.
3. The first deep dive, `docs/WF_LOCKBOX_DEEP_DIVE.md` (walk-forward vs lockbox), whose vocabulary
   is kept: tuning window, tuning search, finalists, crowning step, WF fixed, WF re-tuned / blind,
   sealed year / lockbox, pinned run.

New vocabulary for this document:

- **Training depth (K)** = how many years of history the pick is tuned on before a test year.
- **Test percentile** = where the picked settings land, in the test year, among every candidate
  that was eligible to be picked. 50 means the pick did no better than drawing a random eligible
  candidate; 90 means it beat 90% of them.
- **Fence** = a strategy file whose "free" knobs are narrow verification ranges around an
  already-chosen crown (three of the five files: 81 to 324 distinct settings in total).
  **Wide space** = a real search (the other two: billions of settings, no repeats in 1,000 draws).
- **Calibration** = how honestly the tuning-window profit factor forecasts the next year's.

Units: profit factor and percentiles are unitless and are the numbers to trust across eras. Dollar
ratios across eras were refuted in both dives (NQ's price level grew ~3x; NOISE amplitude ~7x).

---

## 1. Short answers (plain language)

**Is ~15 years of tuning needed?** No, not for choosing the settings. Across five mechanisms, the
settings the engine's own pick rule chooses with two to three years of history are as good in the
next unseen year as those chosen with six, eight or all fifteen: paired on the same test years,
no family shows a longer window winning at any conventional significance, and the median difference
is zero in 14 of 15 family-by-depth cells. Nor does recent data beat old data (tuning on the last
three years vs the three years before that: a coin flip in all five families). Three of the five
files are fences whose pick never beats a random eligible candidate at any depth, so for them
depth is moot; the two real searches reach the 85th to 95th percentile by year two or three and
stay there. What the extra years DO buy is an honest in-sample number: the tuning-window profit
factor overstates the next year by about 2.3x with one year of history, 1.3x with three, and
roughly 1.05x with eight (pooled median), so read a tuning-window profit factor as a forecast only
with six or more years behind it. The extra years also feed the walk-forward test, which is where
the first deep dive already located their value. Practical reading: keeping fifteen years costs
nothing, and moving the last one or two years from tuning to the sealed stretch costs nothing
measurable either. The owner's bet is right: the tuning window is not the scarce resource.
Confidence: high that depth beyond three years does not improve the pick; medium on what the
extra years buy (calibration rises in four of five families).

**How long should the lockbox be?** Twenty-four months as the default, thirty-six for legs with a
long warm-up (daily bars, 250-day regime filters), warm-started, one look, used as a veto. Reserving
two or three more years costs the pick nothing measurable (the pick tuned to two or three years
before the test year is as good as the pick tuned right up to it, in 60 of 60 family-by-design
cells; the worst single cell, NOISE at three years, is a 12-point loss that does not reach
significance). A longer sealed stretch removes most of the cold-start tax (a quarter of the trades
at 12 months, a twentieth at 24), and two to three years is where a sealed stretch first separates
good settings from bad ones in the two real searches. The first deep dive's objection to 36
months (it takes an above-average year from tuning) is not borne out: the tuning cost is zero in
four of five families. The literature agrees on the direction (a short evaluation window is the
lowest-power, most easily fooled design; power rises with the evaluation window) and disagrees only
on magnitude (it would go further, toward a third or half of the history held out). What no
length does: turn the pass rule into a real test, or make the sealed stretch a leaderboard.
Confidence: medium; no family has yet been re-validated by the engine at 24 or 36 months.

**Can a lockbox of any realistic length rank strategies, or only veto them?** Only veto, and even
the veto is weak under the current rule. At one year, the rank of candidates on the sealed stretch
carries no information about their rank the next year in any family (correlations between -0.24
and +0.26; among the ten finalists, a median of 0.01). At two to three years, a sealed stretch can
tell the good settings from the losers in a wide search (top decile beats bottom decile by 20 to
44 points) but still cannot order the top ten (median correlation 0.11; the in-sample rank does as
well). The pass rule (money above zero, profit factor at least one) is a sign test: a no-edge
strategy passes about half the time at every length, and in four of five families the settings
that FAILED their sealed stretch went on to a profitable next year as often as those that passed.
Worse, a strong sealed year is followed by a weaker next year in four of five families (the
family's own edge mean-reverts), so a lockbox leaderboard across many runs would crown the
luckiest year out of many looks. The literature is unanimous here: a holdout used to choose among
many candidates becomes part of the selection and stops being a test.
Confidence: high for the fences and for one year; medium for the wide spaces at two to three years.

**What should the go-live decision rest on?** A stack, not a single number:

1. The walk-forward test (settings re-tuned on the past only, traded blind on the next slice) on
   profit factor with a trade floor, as the ranking reading and the forecast. It is the only
   pre-sealed reading that was never selected on, and it forecasts the sealed stretch's profit
   factor within one to two percent on average (first deep dive).
2. The gap between the fixed-settings walk-forward (the crowning score) and the walk-forward test,
   shown as an overfit warning; a large gap predicts a worse sealed stretch (rank correlation 0.52).
3. A luck-adjusted bar that counts how many settings were tried, at the family level and across
   the record, not just inside one run. Today's checks count one run's own search only.
4. A 24-month sealed stretch, warm-started, as a veto with a rule tied to the forecast: the sealed
   profit factor must land within a margin of the walk-forward test's profit factor, with a trade
   floor, rather than merely above one.
5. Stability of risk shape across the folds (volatility, drawdown), which the best real-world
   evidence says carries over from backtest to live far better than the profit metric.
6. The paper and live record. The literature's blunt point: no historical holdout is truly blind
   once you have lived through it; the only real out-of-sample is trading. EDGELOG already collects
   this (NT paper legs, Webull paper); it should weigh in the go-live call explicitly.

---

## 2. EDGELOG evidence per question

### 2.0 What was built and how far it was trusted

**The candidate matrix.** For each of five families, 1,000 settings (590 to 690 for the two slowest
files) were drawn from the file's own search space with the engine's own seeded sampler, so the
first 200 to 300 draws are exactly the candidate list every walk-forward fold searches. The run's
crown and the file's defaults were added as tagged rows. Every setting was backtested once, warm,
over the run's full window (lockbox included), with every trade's entry and exit time stored. Any
training-window / test-window pair can then be scored from the stored trades without re-running the
engine (`tools/wfdive/isdepth/build_matrix.py`, `analyze_matrix.py`; 47 to 250 s per analysis).

| Family | File | Run | Market / bars | Free knobs | Distinct settings | Trades / yr | Space type |
|---|---|---|---|---|---|---|---|
| TTM squeeze | `TTMSQZ_3_0_ES30N.py` | #299 | ES 30m RTH | 4 | 81 | 22 | fence |
| ORB | `ORB_3_6_R6.py` | #314 | NQ 5m RTH | 5 | 324 | 142 | fence |
| NOISE | `NOISE_1_1_NBHD.py` | #304 | NQ 5m RTH | 5 | 243 | 299 | fence |
| NQDIP | `NQDIP_1_0.py` | #307 | NQ 5m, daily regime filter | 14 | ~1e10 | 56 | wide |
| ENGU-Q R2 | `ENGUQ_1M_ETH_R2_1_0.py` | #335 | NQ 1m ETH | 14 | ~1e10+ | 84 | wide |

**Engine reproduction (the trust check).** Full-window and lockbox trade counts and net are exact
in 5/5 families (e.g. #335: 1,344 trades full, 128 trades / 2,490.6 pts lockbox; #304: 4,833 /
409 / $4,106.16). The saved walk-forward fold champions are reproduced by re-running the engine's
argmax rule over the matrix's own candidate list: 8/8 on TTM, NOISE and ENGU-Q; 7/8 on ORB (fold 6
is a $20 tie flipped by one trade straddling the train/test cut); **0/8 on NQDIP**, which is an
engine-side discrepancy, not a strategy leak (a cold replay of the fold-1 training bars matches the
warm matrix trade for trade, 321/321; a candidate on the same seeded list scores higher than the
saved fold champion under today's rule; the search code changed 8+ times since run #307 validated).
NQDIP's matrix results are internally valid but describe the warm procedure, not the engine's actual
cold picks.

**Four tests, then an adversarial re-verification.** A1 learning curve (train K years, test the
next year, pick by the engine's rule, score the test percentile); A2 rank persistence (rank all
candidates on the last L years, correlate with their rank over a fixed next year); A3 design
backtest (tune to a date, seal L years, apply the pass rule, look at the year after); A4 calibration
(how much the tuning-window profit factor overstates the test year's). The verifier
(`verify_isdepth.py`, no shared code) reproduced the family authors' curves to 0.1 percentile,
then re-read every claim on COMMON origin sets (the same 15 to 19 test years at every depth), with
paired sign tests within origin and seed-0 origin counts. Several author headlines did not survive
(section 2.5).

### 2.1 Is 15 years of tuning needed?

**Learning curve, common-origin test percentile (50 = random eligible candidate).**

| Family | K=1 | K=2 | K=3 | K=4 | K=5 | K=6 | K=8 | all (~15) |
|---|---|---|---|---|---|---|---|---|
| TTM (fence) | (a) | - | 48.6 | 50.5 | 53.6 | 59.1 | 59.0 | 50.6 |
| ORB (fence) | 50.9 | 48.8 | 50.9 | 48.4 | 48.4 | 48.4 | 46.6 | 46.6 |
| NOISE (fence) | 54.6 | 47.0 | 37.5 | 52.0 | 56.4 | 61.4 | 53.9 | 56.4 |
| NQDIP (wide) | 88.4 (a) | 94.9 | 94.2 | 92.5 | 95.5 | 94.2 | 95.2 | 94.1 |
| ENGU-Q (wide) | 84.2 | 76.6 | 85.9 | 85.9 | 81.9 | 85.9 | 81.9 | 88.8 |
| Pooled median (5) | - | - | 50.9 | - | - | 61.4 | 59.0 | 56.4 |

(a) K=1 is a different rule, not a depth point: only 28% (TTM), 20% (NQDIP) and 56% (ENGU-Q) of
candidates clear the 30-trade floor in one year, so K=1 favours the most active settings. The
family authors' "TTM flattens at K=5" and "TTM K=1 = 70" were the all-origins era mix and this
artefact; both are refuted on the common set.

Read: the three fences never rise above chance at any depth (45th to 61st percentile); their
candidates barely differ (one-year-window profit factor 10th-90th percentile: ORB 1.25-1.45,
NOISE 1.21-1.49, 0% losers), so there is nothing for depth to resolve and nothing to lose. The two
wide spaces are at the 85th to 95th percentile from year two or three and flat after. Regret
against the hindsight-best candidate stays large at every depth (TTM 62-81%, ORB 30-44%, NQDIP
35-48%): more history does not close the ceiling gap.

**Does a longer window beat three years? Paired within origin, wins / n (p, two-sided sign).**

| Family | K=6 vs 3 | K=8 vs 3 | all vs 3 | median diff |
|---|---|---|---|---|
| TTM | 6/9 (0.51) | 6/10 (0.75) | 6/13 (1.0) | 0 |
| ORB | 3/7 (0.73-1.0) | 3/7 | 3/8 | 0 |
| NOISE | 8/10 (0.11), +8 pts | 7/10 (0.34) | 8/10 (0.11), +8 pts | +8 at 6 / all |
| NQDIP | 4/9 | 5/8 | 2/9 (0.18), slightly worse | 0 |
| ENGU-Q | 2/5 | 3/6 | 7/9 (0.18) | 0 |

Verdict (verified, high confidence): 0 of 5 families at p < 0.1 in either direction; median
difference vs K=3 is 0.0 in 14 of 15 cells. Leans: NOISE and ENGU-Q toward longer, NQDIP toward
shorter, TTM and ORB flat.

**Does recent data beat old data?** Tune on the last 3 years vs the 3 years before that, same
next-year test: wins 6/19, 11/18, 11/17, 11/19, 9/19 (TTM, ORB, NQDIP, NOISE, ENGU-Q), p >= 0.17
in all five; last-1-year vs year-3-back likewise (p >= 0.06). Verdict: refuted, medium confidence.

**What depth DOES buy: calibration.** Unitless shrinkage (test PF - 1) / (train PF - 1), common
origins; 1.0 = the tuning-window profit factor is an honest forecast.

| Family | K=1 | K=2 | K=3 | K=5 | K=6 | K=8 | all |
|---|---|---|---|---|---|---|---|
| TTM | 0.43 | 0.11 | 0.21 | 0.22 | 0.23 | 0.24 | 0.21 |
| ORB | 0.62 | 0.97 | 1.11 | 0.84 | 0.94 | 0.98 | 1.06 |
| NOISE | 0.58 | 0.65 | 0.78 | 0.88 | 0.95 | 0.97 | 1.17 |
| NQDIP | 0.43 | 0.55 | 0.79 | 0.93 | 0.52 | 0.95 | 0.67 |
| ENGU-Q | 0.29 | 0.40 | 0.52 | 0.51 | 0.54 | 0.53 | 0.78 |
| Pooled median | 0.43 | 0.55 | 0.78 | 0.84 | - | 0.95 | 0.78 |

Read: the in-sample profit factor overstates the next year ~2.3x at one year, ~1.3x at three,
~1.05x at eight; rises with depth in 4/5 families (TTM flat at ~0.2 at every depth). ENGU-Q is
the strongest case for a long window on this ground (0.29 -> 0.78). Verdict: confirmed, medium.
The family authors' raw-dollar shrinkage (ratios of 2.3x to 5.3x at K=14) was era-confounded
and is replaced by this table.

**Pool size vs window length (unverifiable, low confidence).** With 1,000 candidates instead of
the engine's 300, ENGU-Q gains 7-9 points at every K >= 3 (93-95 vs 82-86) but NQDIP loses 15-25
points at K = 1, 4, 5 (more candidates overfit a short window); the fences are unchanged (their
grids are exhausted by ~100 draws). More candidates need more data, which is exactly the
Minimum-Backtest-Length logic in the literature (section 3.4).

**The ~15-year crown vs the 3-year pick (unverifiable).** Only one near-honest window exists per
family (the run's own lockbox, 2025-06 to 2026-06): crown percentile 59, 68, 94, 75, 88 vs the K=3
pick 68, 30, 97, 81, 96 (TTM, ORB, NQDIP, NOISE, ENGU-Q); the crown is ahead in 1 of 5. The family
authors' crown percentiles over 2018-2026 (78 to 97) are hindsight: the crown was chosen on those
windows.

**Prior evidence (first deep dive, memory).** ENGU-Q #335, folds 4-8, one seed: 3-5 years picks the
same settings as 6; below 3 years the answer flips on one fold. Anchored (all history) vs ~6-year
rolling, identical slices: anchored ahead in 45/73 non-tied non-pinned runs (62%), raw money ratio
0.975. ORB meta walk-forward: re-picking yearly on all history $166k, on recent history $233-279k,
leaving defaults alone $377k. Candidate board: 71% of knobs have no predictive power.

**Limits.** Five mechanisms, not five independent votes; 15-19 overlapping origins per family
(one-year tests six months apart, so effective n is roughly half); warm evaluation (the engine's
cold folds differ, section 2.2); the fences cannot speak to discovery-stage tuning because they are
neighbourhoods around a crown; the Stage A search's model steering and range expansion are not
reproduced (the matrix uses the plain per-fold sampler); no ETF-dip, GAPGO or TTIBS mechanism.

### 2.2 How long should the lockbox be?

**Cost of reserving years (frozen pick vs tune-through pick, same next year).** Median 0.0
percentile points in 60 of 60 family-by-design cells; pooled medians 0.0 at L = 0.5, 1, 2 years
and +0.9 at 3 years. Worst single cells: NOISE K=6/L=3 -11.7 (2/11, p = 0.07), NOISE K=all/L=3
-8.9 (p = 0.24), ENGU-Q K=all/L=3 2/10 (p = 0.11). Retuning after a pass (extending the tuning
window through the former lockbox) does not beat freezing the passed pick in any family. Verdict:
"a longer lockbox costs tuning quality" is refuted, high confidence.

**Cold start (engine defect, both dives).** Corpus (first deep dive, 20 runs): median trade loss
24% at a true 12-month lockbox, 5.3% at 24; NQDIP #401 loses 71% at 12 months (25 vs 87 trades,
cold net -8,286 vs warm +9,400 pts). Engine probes this dive (`leak_probe_engine.py`): a cold
restart's first trade comes at bar 7,885 vs 346 warm for NQDIP (~100 sessions lost), 3,137 vs 25
for NOISE (~40 sessions), 0 for ENGU-Q and TTM; ORB trades MORE cold (first trade at bar 53 vs 678;
1,297 vs 1,289 trades) because its ATR/pace filters open on an empty reference. Cold-start error is
therefore two-sided across families, and warm-vs-cold fold deltas run 10-30% of a fold's net on
ORB. Every sealed-year and fold number the app shows is the cold figure.

**Real-edge pass probability of the crowns' own post-2021 record** (first deep dive, month-block
bootstrap, 20 runs / 6 mechanisms): median 0.955 at 12 months, 0.981 at 18, 0.991 at 24, 0.998 at
36; weakest run 0.72 / 0.77 / 0.81 / 0.85. This is a sign test of the champion's own history, not
detection power.

**Power.** Engine power field on 163 runs / 118 families: median achieved power 0.11 at 12 months;
91.5% of families below 0.20; one run powered (NQDIP #401, 24-month lockbox). Months for 80% power
on the claimed edge: 404 (#257 ORB), 120 (#335 ENGU-Q), 232 (#243 NOISE). Extrapolated power at
36 months: 0.18 / 0.39 / 0.25. No realistic length turns the sealed stretch into a confirmation.

**The "above-average most recent year" objection.** The first deep dive found the fixed-champion
profit factor rising with calendar year on #257 and #243 (rho 0.53 / 0.59), but also that the
sealed year trades below the preceding post-2021 stretch in 17 of 20 runs, and this dive found a
zero tuning cost from reserving the years. The most recent year is more valuable as evidence than
as tuning fuel.

**Limits.** No family has been re-validated by the engine at 24 or 36 months (first deep dive
experiment 6 still open). Zero-trade or near-zero sealed stretches (ETF dip legs, 7-13 trades a
year) carry no information at any length.

### 2.3 Can a lockbox rank, or only veto?

**Rank persistence across all candidates, Spearman(net over the last L years, net over a fixed
next year), 19 common origins.**

| Family | L=0.5 | L=1 | L=2 | L=3 | L=4 | L=6 |
|---|---|---|---|---|---|---|
| TTM | 0.09 | -0.24 (CI -0.32..-0.12) | -0.16 | -0.11 | -0.12 | 0.04 |
| ORB | -0.03 | -0.04 | 0.11 (CI 0.05..0.25) | 0.05 | 0.03 | -0.05 |
| NOISE | 0.04 | 0.04 | 0.06 | -0.02 | -0.14 | -0.05 |
| NQDIP | 0.07 | 0.11 | 0.26 (CI 0.20..0.44) | 0.51 (CI 0.36..0.54) | 0.50 | 0.47 |
| ENGU-Q | 0.13 (CI 0.09..0.26) | 0.26 | 0.29 | 0.39 (CI 0.30..0.44) | 0.38 | 0.43 |

Top-decile minus bottom-decile next-year percentile: NQDIP 5, 6, 20, 44, 47 and ENGU-Q 10, 21,
26, 32 points at L = 0.5, 1, 2, 3, (4); fences 2-10 points (TTM's top decile lands BELOW its bottom
decile the next year at L = 1-2). The family authors' "rho ~0.6 at L >= 3" for TTM/ORB rested on
2-4 non-overlapping pairs and vanishes with a fixed future. NOISE's "profit factor is the more
persistent metric" (rho 0.5-0.6) is real but structural: the configs' profit-factor order is set by
band width and trade count and does not carry to next-year money rank.

**Among the ten finalists** (rho of lockbox rank to next-year rank): at L=1: 0.01, -0.03, 0.15,
0.13, -0.09 (median 0.01); at L=3: -0.26, 0.11, 0.38, 0.22, 0.05 (median 0.11; CI above zero only
for NQDIP). The lockbox-best finalist beats the finalist median 37-63% of the time at one year,
58-79% (NQDIP) at best. The in-sample rank orders finalists as well or better (ENGU-Q 0.33 / 0.20 /
0.14 / 0.09 at L = 0.5..3 vs the lockbox's -0.14 / -0.09 / -0.05 / +0.05).

**The pass rule discriminates nothing.** At origin level (seed 0, 19 origins), fail branches hold
0-9 origins; P(next year > 0 | fail) >= P(next year > 0 | pass) in every family but ORB (where K=3 /
L=2 gives 0.88 on 16 passes vs 0.67 on 3 fails). The NOISE author's "K=all / L=2 discriminates,
n = 659 vs 61" was 2 failing origins x 30 near-identical pseudo-seeds; at origin level that design
has 19 passes and 0 fails. Verdict: the rule is a sign test at every length from 6 to 36 months,
high confidence.

**A strong sealed year predicts a weaker next year.** Origin-level rho(lockbox PF, next-year PF)
is negative in 4/5 families (K=3/L=1: -0.41 TTM, -0.21 ORB, -0.51 NQDIP, -0.41 NOISE; ranges -0.2
to -0.8 across designs) and positive only for ENGU-Q (+0.2 to +0.7), the one family whose own edge
persists year to year. Consistent with the first deep dive's "sealed year below the preceding
stretch in 17 of 20 runs". Verdict: refuted, medium.

**Corpus evidence (first deep dive).** 90% of 120 dedup families pass the sealed year (100% of
pinned, 81% of walk-forward-crowned); the crown's sealed-year rank among its ten finalists is 6 of
10 on average; within-run rank correlation of the walk-forward score to the sealed year 0.118, of
in-sample profit 0.117 (77 runs / 63 families).

### 2.4 What should the go-live decision rest on?

**Calibration of the readings** (first deep dive, verified; sealed-year PF / reading PF, median):
WF fixed 0.946 (CI 0.883-0.981; 5-9% optimistic), WF re-tuned 0.986 (CI 0.921-1.020; calibrated),
in-sample 0.958. Rank power to the sealed year: 0.37 / 0.33 / 0.32, indistinguishable. Given a
reading above 1, the sealed year is above 1 in 89-90% of runs whichever reading is used.

**The gap is the warning light.** Rank correlation between (fixed minus re-tuned, as a fraction of
fixed) and the sealed-year shortfall: 0.52 (CI 0.28-0.68; 98 runs / 74 families; permutation
p < 0.0005). The fixed number sits 16% above the re-tuned one on runs with a real shortlist, 0% on
pinned runs; its span is 45-64% inside the tuning search's own data.

**Crowning on walk-forward money adds nothing detectable** (n = 45 families where the step changed
the pick): the walk-forward-crowned config beat the in-sample best on the sealed year 20/45 (44%,
p = 0.55); best of its field 7/45 (15.6%) vs 10.2% chance.

**Scope of the engine's multiple-testing checks (read from the engine source this session).** The
luck bar (deflated Sharpe) uses N = the number of settings the run's own Stage A search evaluated
(`len(records)` / `len(combos)`), with the spread of Sharpe ratios taken from that run's top 40. The
overfit-of-selection check builds its performance matrix from the run's top 24 in-sample settings
replayed on the pre-lockbox window, monthly P&L, gate at PBO <= 0.5. Neither counts: the per-fold
searches (300 candidates x 8 folds), other runs of the same file, other rounds of the same family
(NOISE rounds 16-25, ENGU-Q R2-R5), or the corpus of 187 validates compared on COMPARE. The
adversarial pill (AUC < 0.75) checks lockbox regime drift, not multiplicity. So within-run
multiplicity is corrected; cross-run and cross-round multiplicity is not.

### 2.5 Method problems found in this dive (and what was done about them)

- **Pseudo-seeds are not independent.** 30 random 200/300-of-1,000 subsets yield a median of 2
  (TTM), 3 (NOISE), 4-5 (ORB), 6 (NQDIP), 7-9 (ENGU-Q) distinct picks per cell; author "n" that
  counted seed rows was inflated 4-15x. All A3 headlines were re-read at origin level.
- **Era mixing.** The authors' all-origins learning curves use a different origin set at each
  depth (K = 12-14 = 2024+ only, n = 3-7); on common origins numbers move up to 20 points. The
  flat conclusion survives; specific flatten points do not. K >= 12 and L >= 4 cells are dropped.
- **Raw-dollar shrinkage mixes eras** (NOISE 2.35x, ORB 5.3x at K=14); replaced by unitless
  profit-factor shrinkage, which reverses the read (calibration improves with depth).
- **Trade-floor survivorship at K=1** (above); the realism gate otherwise never binds.
- **Overlapping origins** make every within-family CI optimistic (effective n ~ half); paired sign
  tests within origin are the safer read and were used.
- **A2 confounded ranking-window and future-window length**; re-done with a fixed one-year future.
- **Straddling trades** leak post-cut P&L into training scores for the two multi-day families
  (ENGU-Q holds up to 449 days, NQDIP 73): picks change in 26-41% / 12-24% of cells under a strict
  cut, percentile effect <= 5 points, no consistent sign. Not decision-changing; the "0 look-ahead
  violations" counter only checks window edges. Zero for the three session-flat families.
- **NQDIP 0/8 fold reproduction** is real and unresolved on the engine side.
- **Crown and default rows are hindsight references**, not evidence about depth.

---

## 3. What the literature says, by question

Paraphrase only. Every citation below passed a check that the source exists with the stated
metadata; where a specific figure could not be re-checked against the text it is marked
"(figure not re-checked)". Sources that exist but whose claims were not checked are listed
separately in section 8 and are used only as pointers.

### 3.1 How much history to tune on

- Under structural breaks, using all available history is not automatically best: pre-break data
  is biased but lowers variance, so the right window is a bias-variance trade-off; the paper
  proposes cross-validating the window length itself, or pooling forecasts across several window
  lengths, and shows in simulation that these beat both "use everything" and "use only recent
  data". Pesaran & Timmermann (2007), "Selection of Estimation Window in the Presence of Breaks",
  Journal of Econometrics 137(1), 134-161.
  https://rady.ucsd.edu/_files/faculty-research/timmermann/estimation-window.pdf
- Reporting results for one ad hoc window size is fragile; trying several and keeping the best is
  data snooping over window size. The remedy is a statistic that pools over a range of window
  lengths. Rossi & Inoue (2012), "Out-of-Sample Forecast Tests Robust to the Choice of Window
  Size", Journal of Business & Economic Statistics 30(3), 432-453.
  https://www.tandfonline.com/doi/abs/10.1080/07350015.2012.693850
- Return predictability is local and short-lived because investors' own search changes the
  process ("creative self-destruction"); fitting one model to the longest history blends extinct
  regimes; adaptive combination that weights recent performance is the proposed response.
  Timmermann (2008), "Elusive Return Predictability", International Journal of Forecasting 24(1),
  1-18. https://rady.ucsd.edu/_files/faculty-research/timmermann/ijf_invited.pdf
- The required backtest length grows only with the logarithm of the number of independent
  settings tried; the paper's worked figures (about 45 settings on 5 years of daily data before a
  Sharpe of 1 is expected by chance) were not re-checked against the text. Bailey, Borwein, Lopez
  de Prado & Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest
  Overfitting on Out-of-Sample Performance", Notices of the AMS 61(5), 458-471.
  https://www.ams.org/notices/201405/rnoti-p458.pdf
- The validation-to-training size ratio should scale with the square root of the ratio of
  selection complexity to fitting complexity: a file with many free knobs and a real search
  deserves relatively more validation data than a pinned one. Guyon (1997), "A Scaling Law for the
  Validation-Set Training-Set Size Ratio", AT&T Bell Laboratories technical report.
  https://www.semanticscholar.org/paper/452e6c05d46e061290fefff8b46d0ff161998677
- For a broad class of loss functions the variance-optimal training share of a sample is one
  half, independent of the data distribution; the textbook heuristic is 50% train / 25% validate /
  25% test with the test set "kept in a vault" and opened once. Afendras & Markatou (2019),
  "Optimality of training/test size and resampling effectiveness in cross-validation", Journal of
  Statistical Planning and Inference 199, 286-301, https://arxiv.org/abs/1511.02980; Hastie,
  Tibshirani & Friedman (2009), The Elements of Statistical Learning, 2nd ed., Springer, ch. 7
  p. 222, https://faculty.stat.ucla.edu/ywu/research/documents/BOOKS/ElementsLearningII.pdf
- Financial history is small: about 55 years of good equity data is under 700 monthly
  observations, "far too small" for most machine learning; tuning ten hyperparameters by
  cross-validation on 50 years of returns is described as a terrible idea. Arnott, Harvey &
  Markowitz (2019), "A Backtesting Protocol in the Era of Machine Learning", Journal of Financial
  Data Science 1(1), 64-74.
  https://people.duke.edu/~charvey/Research/Published_Papers/P138_A_backtesting_protocol.pdf

### 3.2 How long a holdout or track record must be

- Out-of-sample tests are generically lower-powered than in-sample tests of the same hypothesis
  on the same data, because splitting wastes information; a weak out-of-sample result does not by
  itself debunk a good in-sample one. Inoue & Kilian (2004/2005), "In-Sample or Out-of-Sample
  Tests of Predictability: Which One Should We Use?", Econometric Reviews 23(4), 371-402.
  https://www.tandfonline.com/doi/abs/10.1081/ETC-200040785
- The split point is a free choice with no accepted rule; treating it as fixed when several could
  have been tried inflates a nominal 5% test to roughly 15%; spurious rejections are most likely
  with a SHORT evaluation window, and power is highest when the split comes early (a long
  evaluation period). Hansen & Timmermann (2012), "Choice of Sample Split in Out-of-Sample
  Forecast Evaluation", EUI ECO 2012/10 / CREATES 2012-43 working paper (never published in a
  journal; one sweep's "Econometric Theory 2015" attribution is wrong).
  https://rady.ucsd.edu/_files/faculty-research/timmermann/samplesplitmining2012_feb07.pdf
- Minimum Track Record Length: the number of observations needed to reject "true Sharpe below a
  benchmark" at a stated confidence, given the observed Sharpe, skew and kurtosis. Worked
  example: an annualized Sharpe of 2 against a benchmark of 1 (not 0.5, as one sweep said) needs
  2.73 years of daily data, 3.24 years monthly, and 4.99 years with hedge-fund-like negative skew
  and fat tails, 54% longer than the Normal case. Bailey & Lopez de Prado (2012), "The Sharpe Ratio
  Efficient Frontier", Journal of Risk 15(2), 3-44.
  https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
- A Sharpe ratio is a noisy estimate with its own standard error; naive annualization is invalid
  under serial correlation and can overstate the annual figure by up to 65%. Lo (2002), "The
  Statistics of Sharpe Ratios", Financial Analysts Journal 58(4), 36-52.
  https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios
- Practitioner arithmetic: a rule with Sharpe 0.3 on one instrument needs about 37 years before
  its lower two-sigma band clears zero, Sharpe 0.5 about 10 years; pooling across uncorrelated
  instruments accumulates independent bets faster than waiting for calendar years. Carver (2015),
  Systematic Trading, Harriman House (verified via a secondary summary).
  https://the7circles.uk/systematic-trading-2-fitting-and-allocation/
- Low power means low positive predictive value: a "pass" from a test with 11% power is mostly
  uninformative regardless of domain. Ioannidis (2005), "Why Most Published Research Findings Are
  False", PLoS Medicine 2(8), e124.
  https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124
- Even a rule that survives a proper multiple-testing correction on 90 years of data (7,846
  technical rules on the Dow, adjusted p < 0.002 over 1897-1986) showed "scant evidence" of value
  over the following decade. Sullivan, Timmermann & White (1999), "Data-Snooping, Technical
  Trading Rule Performance, and the Bootstrap", Journal of Finance 54(5), 1647-1691.
  https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf
- "No true out-of-sample data exist; the only true out-of-sample is live trading": a researcher
  who lived through the holdout already knows its history. Arnott, Harvey & Markowitz (2019), as
  above.

### 3.3 Ranking with a holdout, selection bias, and re-using a holdout

- Picking the best of many candidates by their score on one stretch and then reporting that score
  is data snooping; the Reality Check bootstrap gives the correct p-value for the best of a search.
  Worked case: 3,654 candidate models on the S&P 500, naive p = 0.0036, search-adjusted p = 0.204.
  White (2000), "A Reality Check for Data Snooping", Econometrica 68(5), 1097-1126.
  https://users.ssc.wisc.edu/~bhansen/718/White2000.pdf
- A studentized version with a sample-dependent null recovers power that the Reality Check loses
  when the candidate set includes many weak alternatives (power 15% to 53% in the paper's
  example). Hansen (2005), "A Test for Superior Predictive Ability", Journal of Business &
  Economic Statistics 23(4), 365-380. https://cdr.lib.unc.edu/downloads/zp38wf793
- A stepwise version certifies several genuine outperformers at once while controlling the
  family-wise error rate (hedge-fund example not re-checked). Romano & Wolf (2005), "Stepwise
  Multiple Testing as Formalized Data Snooping", Econometrica 73(4), 1237-1282.
  https://onlinelibrary.wiley.com/doi/10.1111/j.1468-0262.2005.00615.x
- Reporting the score that was used to select the model as the performance estimate is a selection
  bias "often of comparable magnitude to differences between learning algorithms"; a small
  validation set makes the selection step itself overfit; the fix is nested (double)
  cross-validation. Cawley & Talbot (2010), "On Over-fitting in Model Selection and Subsequent
  Selection Bias in Performance Evaluation", JMLR 11, 2079-2107.
  https://www.jmlr.org/papers/v11/cawley10a.html
- On data with no signal at all, tuned classifiers reported cross-validation error under 30% in
  18.5% (shrunken centroids) and 38% (SVM) of datasets; nested cross-validation brings the bias to
  near zero. Varma & Simon (2006), "Bias in error estimation when using cross-validation for model
  selection", BMC Bioinformatics 7:91. https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/
- Pseudo-out-of-sample splitting is not inherently the right way to choose between models; the
  test's own author says full-sample comparison is often more compelling for selection, while
  pseudo-out-of-sample analysis keeps its value as a historical track record. Diebold (2015),
  "Comparing Predictive Accuracy, Twenty Years Later", Journal of Business & Economic Statistics
  33(1), 1-9. https://www.nber.org/papers/w18391
- Adaptive re-use of one holdout breaks its guarantees unless the answers are thresholded or
  noised; with that machinery a holdout can answer far more adaptively chosen questions than the
  naive linear budget. Dwork, Feldman, Hardt, Pitassi, Reingold & Roth (2015), "The reusable
  holdout: Preserving validity in adaptive data analysis", Science 349(6248), 636-638.
  https://www.science.org/doi/10.1126/science.aaa9375
- A leaderboard that reports a new score only when it beats the submitter's previous best by a
  statistically significant margin keeps its worst-case error growing like the cube root of
  log(looks)/n instead of linearly in looks; validated on a real Kaggle log. Blum & Hardt (2015),
  "The Ladder: A Reliable Leaderboard for Machine Learning Competitions", ICML 2015 / arXiv
  1502.04585. https://arxiv.org/abs/1502.04585
- Across more than one hundred Kaggle competitions, repeated querying of the public holdout
  produced little substantial overfitting; the exceptions had small or non-i.i.d. test sets. The
  "10,000-example floor" quoted by one sweep could not be found in the paper and is dropped.
  Roelofs, Shankar, Recht, Fridovich-Keil, Hardt, Miller & Schmidt (2019), "A Meta-Analysis of
  Overfitting in Machine Learning", NeurIPS 2019, 9175-9185.
  https://proceedings.neurips.cc/paper_files/paper/2019/file/ee39e503b6bedf0c98c388b7e8589aca-Paper.pdf
- A drop on a freshly built test set (11-14% on ImageNet) came from distribution shift, not from
  years of adaptive overfitting to the reused test set, and model rankings were preserved. Recht,
  Roelofs, Schmidt & Shankar (2019), "Do ImageNet Classifiers Generalize to ImageNet?", ICML 2019,
  PMLR 97, 5389-5400. https://proceedings.mlr.press/v97/recht19a.html
- Iterating strategy ideas by repeatedly examining backtest results is itself a pitfall; results
  should not be fed back into the research loop. Lopez de Prado (2018), Advances in Financial
  Machine Learning, Wiley, ch. 7, 11, 12 (purging, embargo, combinatorial purged cross-validation
  confirmed via a secondary source, not the chapter text).
  https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086
- Single-layer walk-forward is often insufficient once selection has happened inside it; nest an
  outer walk-forward or cross-validation layer around the selection step. Masters (2018), Testing
  and Tuning Market Trading Systems, Apress. https://link.springer.com/book/10.1007/978-1-4842-4173-8

### 3.4 Multiple testing across many trials, runs and rounds

- The expected maximum Sharpe across N trials grows with the trials' spread and with log N; the
  Deflated Sharpe Ratio tests the winner against that rising bar, also adjusting for skew and
  kurtosis. Worked case: an apparently excellent Sharpe of 2.5 over 5 years of daily data fails a
  95% bar once 100 trials are counted (the exact value ~0.90 not re-checked; 46 trials would have
  passed). Applying a one-shot holdout about 20 times at 95% confidence makes a false pass the
  expected outcome. Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio: Correcting for
  Selection Bias, Backtest Overfitting and Non-Normality", Journal of Portfolio Management 40(5),
  94-107. https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- Probability of Backtest Overfitting via combinatorially symmetric cross-validation: split the
  trials-by-time performance matrix into S blocks (S = 16 recommended, N >> 10 trials), score the
  in-sample winner on every complementary out-of-sample combination, and report how often it
  falls below the out-of-sample median. Example: 8,800 seasonal settings on ~4 years of random
  data give PBO 55%; with a real effect embedded, 13%. A single train/holdout split cannot detect
  this. Bailey, Borwein, Lopez de Prado & Zhu (2017), "The Probability of Backtest Overfitting",
  Journal of Computational Finance 20(4), 39-69.
  https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- Haircut Sharpe ratios: with 200 prior trials, a Sharpe of 0.75 over 20 years falls to about
  0.32 (a 60% haircut); the haircut is strongly nonlinear (marginal strategies lose most), so a flat
  50% rule is wrong in both directions; the false-discovery-rate correction (BHY) is recommended;
  require BOTH a multiple-testing-adjusted in-sample pass and an out-of-sample confirmation.
  Harvey & Liu (2015), "Backtesting", Journal of Portfolio Management 42(1), 13-28.
  https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
- Simple, implementable multiple-testing adjustments for trading strategies, with the bar rising
  as a research program accumulates tests. Harvey & Liu (2014), "Evaluating Trading Strategies",
  Journal of Portfolio Management 40(5), 108-118.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2474755
- After 316 published factors, a new one needs a t-ratio above about 3.0, not 2.0, and the
  hurdle keeps rising as tests accumulate. Harvey, Liu & Zhu (2016), "...and the Cross-Section of
  Expected Returns", Review of Financial Studies 29(1), 5-68.
  https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
- Of about 2.1 million data-mined equity strategies, roughly 45% of those that look significant
  without correction are false; after correction 17 survive; required t-statistics about 3.8
  (time-series) and 3.4 (cross-sectional). Chordia, Goyal & Saretto (2020), "Anomalies and False
  Rejections", Review of Financial Studies 33(5), 2134-2179.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3017677
- A multiple-comparisons problem exists even in one honest analysis whenever analytic choices
  would have been made differently under different data (the "garden of forking paths"); a
  steered, auto-expanding search has an effective trial count that is not the nominal one.
  Gelman & Loken (2013), "The Garden of Forking Paths", Columbia University working paper.
  https://sites.stat.columbia.edu/gelman/research/unpublished/p_hacking.pdf
- Public demonstration tools showing an in-sample Sharpe rising smoothly with the number of
  parameter combinations tried on random data. Bailey, Borwein, Lopez de Prado, Salehipour & Zhu
  (2016), "Backtest Overfitting in Financial Markets", Automated Trader 39(2), 52-57 (trade
  magazine; one sweep conflated it with the AMS paper above).
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2731886

### 3.5 Fold design and cross-validation for time series

- Multiple rolling test origins beat one fixed split; the many implementation choices (fixed vs
  rolling origin, fixed vs expanding window, recalibration) are rarely reported and should be
  justified. Tashman (2000), "Out-of-sample tests of forecasting accuracy: an analysis and
  review", International Journal of Forecasting 16(4), 437-450.
  https://www.sciencedirect.com/science/article/abs/pii/S0169207000000650
- Shuffled K-fold cross-validation is valid for purely autoregressive models whose errors are
  uncorrelated, and can then be more data-efficient than out-of-sample evaluation; it is not
  licensed for models with structural or non-stationary dependence. Bergmeir, Hyndman & Koo
  (2018), "A note on the validity of cross-validation for evaluating autoregressive time series
  prediction", Computational Statistics & Data Analysis 120, 70-83.
  https://robjhyndman.com/publications/cv-time-series/
- On 62 real-world series (not 174, as one sweep said) plus three synthetic ones,
  cross-validation is accurate when the series is near-stationary, and order-preserving
  out-of-sample methods give the least biased estimates under real non-stationarity; no method
  dominates. Cerqueira, Torgo & Mozetic (2020), "Evaluating time series forecasting models: an
  empirical study on performance estimation methods", Machine Learning 109(11), 1997-2028.
  https://arxiv.org/abs/1905.11744
- A fixed set of rolling or anchored folds is one deterministic path through history;
  combinatorial purged cross-validation resamples many train/test combinations from the same
  history to produce a distribution of out-of-sample results instead of one point. Lopez de Prado
  (2018), as above (secondary source).
- Walk-forward analysis formalized as the practitioner standard, with a walk-forward efficiency
  ratio (out-of-sample over in-sample performance) as the diagnostic; the specific thresholds
  quoted in practitioner lore (50%) and window ratios (4-6x) could not be located in the text.
  Pardo (2008), The Evaluation and Optimization of Trading Strategies, 2nd ed., Wiley, ch. 11.
  https://onlinelibrary.wiley.com/doi/abs/10.1002/9781119196969.ch11

### 3.6 Boundaries, warm starts, purging

- No classical source treats a cold start at a fold boundary as a design choice; recursive and
  rolling schemes implicitly initialize on pre-window history. The nearest literature is
  purging (drop training observations whose outcome window overlaps the test slice) and an
  embargo (drop a further buffer after the test slice), which force explicit boundary handling in
  the opposite direction (stopping forward leakage rather than restoring warm-up). Lopez de Prado
  (2018), as above; Tashman (2000), Rossi & Inoue (2012), Hansen & Timmermann (2012) for the
  implicit-initialization point.
- The one-trade-straddling-the-cut effect this dive found (ORB fold 6, ENGU-Q 26-41% of cells
  changing pick under a strict cut) is precisely the label-overlap leakage purging addresses.

### 3.7 Base rates: how much a validated strategy decays

- 888 real algorithms with 6-12+ months of genuine forward data: the backtest Sharpe explains
  almost none of the out-of-sample Sharpe (R^2 0.02); backtest volatility (R^2 0.67) and maximum
  drawdown (R^2 0.34) carry over; more backtesting days predict a larger shortfall (p < 0.0001);
  a model on backtest-behaviour features reached R^2 0.17 and its portfolio beat the
  highest-backtest-Sharpe portfolio forward. Wiecki, Campbell, Lent & Stauth (2016), "All That
  Glitters Is Not Gold: Comparing Backtest and Out-of-Sample Performance on a Large Cohort of
  Trading Algorithms", Journal of Investing 25(3), 69-80.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220
- 215 bank alternative-beta strategies (10.7-year average backtest, 4.6-year live): median Sharpe
  1.20 in backtest to 0.31 live (73% haircut); 8.4% matched their backtest; 30% went negative;
  the most complex strategies lost over 30 points more than the simplest. Suhonen, Lennkh & Perez
  (2017), "Quantifying Backtest Overfitting in Alternative Beta Strategies", Journal of Portfolio
  Management 43(2), 90-104. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2757113
- 97 published return predictors: 26% lower out-of-sample (statistical bias), 58% lower
  post-publication (finer decomposition not re-checked). McLean & Pontiff (2016), "Does Academic
  Research Destroy Stock Return Predictability?", Journal of Finance 71(1), 5-32.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623

### 3.8 Where the literature and our data agree and disagree

| Point | Literature | EDGELOG data | Read |
|---|---|---|---|
| Short OOS windows are low-power and easily fooled | Inoue & Kilian; Hansen & Timmermann | power 0.11 at 12 months; pass rule a sign test at every L | agree |
| Power rises with a longer evaluation period | Hansen & Timmermann | real-edge pass 0.955 -> 0.991 at 24 months; ranking power appears at 2-3 years in wide spaces | agree on direction |
| More history is not automatically better under breaks | Pesaran & Timmermann; Timmermann 2008 | no depth wins in either direction; recent-vs-old a coin flip | partly: no harm found, no benefit either |
| Recent data should matter more | Timmermann 2008; McLean & Pontiff | refuted (p >= 0.17 in all five) | disagree; fences have nothing to resolve, wide spaces plateau early |
| Hold out a third to a half | ESL; Afendras & Markatou; Guyon | the pick needs 2-3 years; calibration needs 6-8 | consistent with a larger holdout than today; a 50/50 split neither supported nor refuted |
| Backtest profit metric barely predicts OOS | Wiecki; Suhonen | rank power of every reading ~0.33; crown 6th of 10 on the sealed year | agree |
| In-sample evidence is not inherently worse than OOS | Inoue & Kilian; Diebold | in-sample rank power 0.32 vs re-tuned 0.33 vs fixed 0.37 | agree |
| Best-of-N selection needs a correction | White; Hansen; Cawley & Talbot | fixed WF 16% above re-tuned; crowning wins 44% | agree |
| More trials need more data | Bailey et al. MinBTL | 1,000 vs 300 candidates: helps ENGU-Q, hurts NQDIP at short K | agree |
| Holdout re-use is less damaging than theory says | Roelofs et al. | ten finalists' lockbox looks carry so little signal (rank 6/10) there is little to overfit to | consistent, for the wrong reason |
| Risk-shape metrics carry over better than profit | Wiecki | not yet tested here (net/DD known unreliable, memory) | open |

---

## 4. Assumption scorecard H1-H9 (plain language)

| # | Held assumption | Verdict | Evidence for keeping | Evidence for changing |
|---|---|---|---|---|
| H1 | A 12-month lockbox with pass = money above zero is an adequate go-live test | **Change** | A sealed stretch is the cleanest test of the frozen settings; ESL's "vault" principle | Pass rule is a sign test (no-edge passes ~50%; failing settings profitable next year as often as passing ones); power 0.11; a quarter of the trades lost to the cold start; the literature's minimum track record for a strong edge is years, not months |
| H2 | Rank on the walk-forward test (re-tuned), not the fixed reading or the lockbox | **Keep, with caveats** | Only reading never selected on; forecasts the sealed profit factor within 1-2%; Reality-Check logic says use a score not used for selection; procedure-testing frameworks favour it | Its rank power is only ~0.33, no better than in-sample; the test's own author of the standard comparison test warns pseudo-out-of-sample splitting is not automatically the right selection basis; it is still compared across runs without a cross-run correction |
| H3 | Crowning a finalist by fixed-settings money over the walk-forward years is useful | **Change** | The shortlist itself carries information (run #360); one demonstration (run #168) | Crowned config beats the in-sample best on the sealed year 44% (n = 45); ranks 6th of 10; this is the textbook selection-bias pattern; a search-adjusted p-value (Reality Check) would be the honest alternative if the step is kept |
| H4 | Using all ~15 years for tuning beats a shorter recent window | **Change** | Calibration of the in-sample number improves with depth (4/5 families); slight, non-significant lean to all-history on ENGU-Q and NOISE; keeping the years costs nothing | Pick quality flat from 2-3 years in 5/5 families; no depth wins in either direction; the last 1-2 years can move to the sealed stretch at zero measured cost |
| H5 | 8 walk-forward folds with ~6-year rolling training is a sound design | **Keep in kind, change details** | Order-preserving multi-origin evaluation is the empirically correct family for non-stationary series; 6 years sits above the 2-3-year pick plateau and near the 6-8-year calibration point; anchored vs rolling within 3% | Folds start cold (two-sided error, up to 30% of a fold's net on ORB); choosing rolling vs anchored by which scores better is window-size snooping; one fixed path through history vs a resampled distribution; NQDIP fold picks no longer reproduce |
| H6 | A 75/25 in-sample/holdout split inside the tuning window | **Test further** | Reproduces saved in-sample trade counts; convention | The split point is a mineable choice; power favours an earlier split; the pick does not need 75% of the years; 45-64% of the fixed walk-forward span sits inside the search's own data |
| H7 | Comparing hundreds of runs on one NQ history without a multiple-testing adjustment is acceptable | **Change** | The luck-bar and overfit-of-selection checks exist and implement the right papers; families collapse to ~8 mechanisms so the effective count is smaller than the run count | Both checks count only one run's own search; per-fold searches, repeated rounds of one family and the cross-run leaderboard are uncorrected; the literature's bar rises with trials ever run (t > 3, haircut 60% at 200 trials) |
| H8 | Folds and lockbox starting cold is acceptable | **Change** | Zero effect on session-flat intraday families (ENGU-Q, TTM) | NQDIP loses ~100 sessions and 50-70% of sealed-year profit; NOISE ~40 sessions; ORB trades MORE cold; no literature treats a cold start as a design choice; purging/embargo is the nearest analogue and points to explicit boundary handling |
| H9 | A single strategy's edge can be confirmed from its own lockbox | **Refuted; keep as "no"** | none | Power 0.11; months for 80% power 120-404; minimum-track-record arithmetic gives years for a strong edge and decades for a Sharpe of 0.3-0.5; a strong sealed year is followed by a weaker one in 4/5 families; 888-strategy study finds a 6-12-month forward Sharpe nearly uninformative |

---

## 5. Recommended validation design (owner calls; nothing decided)

Plain-language proposal for a ~16-year history (2010-06 to 2026-08 on NQ 5m; adjust dates per
file). Everything below is an option to weigh, with the evidence it rests on and what it would cost.

### 5.1 Time allocation

| Segment | Today | Proposed default (intraday legs) | Long-warm-up legs (daily bars, 250-day filters) |
|---|---|---|---|
| Sealed stretch (one look, veto) | 12 months, cold | **24 months** (2024-08 to 2026-08), warm-started | **36 months** (2023-08 to 2026-08), warm-started |
| Tuning window | 15.2 years | 14.2 years | 13.2 years |
| What the tuning search may see | first 75% of the tuning window (to ~2021-11) | first 60-75% (owner call; at 60% to ~2018-11) | same |
| Clean fixed-settings stretch of the crowned settings | ~3.8 years | 3.5 years at 75%, ~5.7 years at 60% | same |
| Walk-forward test | 8 folds, ~6-year rolling training, cold, scheme chosen by score | 8 folds, 6-year rolling training, warm-started, purge of the longest lookback at each cut; report anchored beside it, do not choose by score | same, with the purge sized to the regime filter |

Why these numbers: the pick is settled by 2-3 years in every family, so a 6-year rolling training
window is generous for the pick and sits where the in-sample number becomes honest (6-8 years);
the sealed stretch moves to 24 months because the two extra years cost the pick nothing measurable,
remove most of the cold-start tax, and are where a sealed stretch first separates good settings from
bad in a wide search; 36 months for slow legs because their cold-start loss is 50-70% at 12 months
and still a third at 24. Thirty-six months for everything is defensible on the evidence (the
tuning cost is zero) but buys no extra ranking power and costs a year of calendar time; the
literature would go further still (a third to half held out), which is the main open question in
section 7.

### 5.2 Pass rule for the sealed stretch

Replace "money above zero and profit factor at least one" with a rule tied to the forecast:

- The sealed stretch's profit factor must land within a margin of the walk-forward test's profit
  factor (the margin taken from the walk-forward test's own fold-to-fold spread, or a fixed 0.15 as
  a starting point), AND
- a trade floor (for example 60 trades over 24 months; zero-trade and near-zero stretches carry no
  information), AND
- the luck-adjusted bar (section 5.4) must clear.

This still cannot confirm an edge (nothing at these lengths can); what it does is catch the cases
the sign test lets through: a sealed stretch that is positive but far below what the blind test
forecast, which is the overfit signature the record already shows (a large fixed-vs-blind gap
predicts a worse sealed stretch, correlation 0.52).

### 5.3 Ranking and crowning

- Rank on the walk-forward test (profit factor first, money per year second, trade floor). Show
  the fixed-settings walk-forward as the crowning score, never as a test; show the gap as a chip.
- Crowning step: either drop it (crown from the tuning search alone; then the fixed-settings
  reading after the search's data ends is a clean test of the crowned settings), or keep it and
  attach a search-adjusted p-value (a Reality-Check-style bootstrap over the ten finalists) and
  report the fixed reading only on the post-search stretch, labelled as selected. Both reverse or
  amend the 2026-07-20 decision, so this is an owner call; the prospective check is free because
  every finalist's sealed stretch is already saved.
- Never sort strategies across runs by sealed-stretch money or R per year.

### 5.4 Multiple-testing adjustment across runs

- Keep a trial ledger per family: settings evaluated by the tuning search, per-fold candidates
  times folds, and the number of validates and rounds ever run on that mechanism. Today's checks
  see only the first item for one run.
- Compute the luck-adjusted bar at two levels: the family (all trials ever run on that mechanism)
  and the record (effective count of independent mechanisms, roughly 8 to 15, since NOISE and
  ENGU-Q variants are not independent votes). Show both beside the existing within-run check.
- For the crowning step and the cross-run leaderboard, a bootstrap that tests the best of the
  field against a benchmark, corrected for the size of the field (the studentized version handles
  candidates with very different trade counts and volatility).
- Pre-register search ranges and knob sets per round so the ledger counts something fixed; a
  steered, self-expanding search has an effective count that is larger than its nominal one.

### 5.5 Warm starts and boundaries

- Evaluate folds and the sealed stretch on all history up to the end of the slice, keeping only
  trades that enter inside the slice. This is the root fix for the cold start; it changes every
  future verdict, so the ETF stack and NQDIP 1.1 would need re-judging.
- Purge: assign trades that straddle a cut by exit time (or drop them from the training score) so
  post-cut profit cannot leak into the pick. This dive found it moves 26-41% of ENGU-Q picks at
  short depths, with a small and unsigned effect on outcome; it is cheap and removes a known
  channel.

### 5.6 The go-live call itself

Rest it on the stack in section 1: blind test reading with trade floor, gap chip, luck-adjusted
bar at family level, sealed stretch as a forecast-tied veto, risk-shape stability across folds,
and the paper/live record weighed explicitly (the literature's only "true" out-of-sample). A
strategy whose blind test, sealed stretch and paper record all agree on profit factor within the
forecast margin is the go-live case; disagreement is the stop signal, not a low sealed-stretch
number on its own.

### 5.7 What adoption would cost

| Change | Engineering | CPU / runner | Re-judging |
|---|---|---|---|
| Sealed stretch 24 / 36 months | none (the engine already accepts 18- and 24-month lockboxes; 30 runs used them) | re-validate the three crowns with windows pinned: ORB ~20 min, NOISE ~30 min, ENGU-Q 1-2 h | every crown's verdict is re-read on a longer stretch; older 12-month runs stay comparable only on the blind test |
| Warm-started folds and sealed stretch | ~1 day | ~10 min to replay the 20 crowns already used in the first dive | every future verdict changes; ETF stack and NQDIP 1.1 re-judged; two-sided on ORB |
| Forecast-tied pass rule | small (engine verdict + web pill) | none | recompute from saved fields for existing runs |
| Trial ledger + family/record luck bar | moderate (registry read + new fields + chips) | none | existing crowns get a new, stricter reading; expect the marginal ones to fall below the bar |
| Crowning change | small (crown rule) | none | reverses 2026-07-20; the alternative crown's sealed stretch is already saved for every run |
| Search cut 75% -> 60% | small (one parameter) | 3 validates to test | changes every future crown; existing crowns unaffected |
| Purge at cuts | small | none | tiny effect on picks |
| NQDIP fold reproduction (0/8) | half a day of engine debugging | minutes | needed before any NQDIP fold number is trusted |

---

## 6. Anything else useful, ranked by value for this owner

1. **The gap chip is the best overfit signal the record already holds.** Fixed-vs-blind gap
   predicts the sealed-stretch shortfall at 0.52; the 888-algorithm study found the same
   dose-response (more iteration, bigger gap). Costs nothing to show.
2. **Risk-shape stability across folds.** Volatility and maximum drawdown carried over from
   backtest to live far better than any profit metric in the largest real-world cohort (R^2 0.67
   and 0.34 vs 0.02). EDGELOG saves per-fold equity; a "shape consistency" chip and a test of its
   rank power to the sealed stretch is a JSON-only job.
3. **A per-strategy minimum track record.** The engine's power field already answers "how many
   months for 80% power"; the literature's closed form (from the strategy's own Sharpe, skew,
   kurtosis) is a cheap cross-check and makes the "cannot confirm from its own lockbox" point
   visible on every card instead of buried in a pill.
4. **Fences vs wide spaces should be labelled.** Three of five files are verification
   neighbourhoods where the search has nothing to resolve; their walk-forward and depth readings
   describe the crown's neighbourhood, not a search. A "fence" badge (distinct settings under
   ~500) would stop them being read as discovery evidence.
5. **Cross-market as a second out-of-sample.** Pooling instruments accumulates independent bets
   faster than calendar years (Carver); testing on a different market is the protocol's own
   recommendation (Arnott, Harvey & Markowitz). All three crowns are NQ-only; ES and QQQ replays
   of the same mechanism would add evidence the NQ lockbox cannot.
6. **A trial ledger is the missing input to every correction.** Every multiple-testing method
   needs the count of trials; the number is currently reconstructable per run but not per family
   or per round. Recording it is the prerequisite for items in 5.4.
7. **Ladder-style holdout re-use.** If finalists must keep being scored on the sealed stretch,
   reveal a finalist's sealed number only when it beats the standing champion by a significant
   margin; this bounds the spending of the holdout without freezing it after one look.
8. **Combinatorial resampling on the candidate matrices.** The matrices already store per-trade
   arrays for 1,000 settings over 16 years; a combinatorially-symmetric resample (the PBO method)
   per family is a script, not an engine change, and would give a distribution of walk-forward
   outcomes instead of one path.
9. **Pre-registration per round.** Write the knob set, ranges, and pass rule before the round
   runs (the protocol's checklist); the record's repeated rounds on one family (NOISE 16-25,
   ENGU-Q R2-R5) are exactly the uncounted looks the literature warns about.
10. **Base rates for expectation-setting.** Median 73% Sharpe haircut from backtest to live on 215
    bank strategies; 26% pure-overfitting decay on 97 published predictors. EDGELOG's own
    blind-to-sealed ratio (0.986 on profit factor) is far better than these because the blind test
    is already out-of-sample; the relevant comparison for the paper legs is sealed-to-live.

Pitfalls picked up in this dive that apply to any future study on the record: pseudo-seeds are
not independent draws; origins six months apart overlap; raw dollars across eras mislead; K=1 is
a trade-floor rule; crown and default rows are hindsight; "0 look-ahead violations" counters that
check window edges miss straddling trades; and a bit-identical refactor claim on the fold search
did not hold for NQDIP.

---

## 7. Follow-up experiments, with cost

All CPU work under the shared CPU lock, below-normal priority, off market hours.

| # | Experiment | What it settles | Cost |
|---|---|---|---|
| 1 | Re-validate the three crowns at 24-month sealed stretches, windows pinned (first dive #6) | Whether the crown and verdict move when two years leave tuning; the only direct engine test of the allocation | ORB ~20 min, NOISE ~30 min, ENGU-Q 1-2 h runner |
| 2 | Warm-start prototype for folds and sealed stretch, then replay the 20 crowns (first dive #5) | Size of the cold-start correction per family before the engine change | ~1 day engineering, ~10 min CPU |
| 3 | Search-cut sweep (60 / 70 / 75%) on the two wide families via full validates | Whether an earlier cut changes the crown or the blind test | 3-6 validates, ~1-3 h runner |
| 4 | Trial ledger from the registry + family-level and record-level luck bars for every crown | How many current crowns clear a corrected bar | JSON only, hours of scripting |
| 5 | Root-cause NQDIP 0/8 fold reproduction | Whether the fold search drifted; whether other wide-space runs are affected | half a day engine debugging |
| 6 | Corpus read of every saved finalist's sealed stretch: crowned vs in-sample best vs plateau vs median (first dive #2) | Which crowning rule the record favours before changing it | minutes |
| 7 | Risk-shape stability chips (fold volatility, drawdown consistency) and their rank power to the sealed stretch | Whether the Wiecki finding transfers to this record | JSON only, hours |
| 8 | Cross-market replay of ENGU-Q and NOISE on ES (and QQQ where data allows) | An independent out-of-sample read per mechanism | ~30 min per validate |
| 9 | Combinatorially-symmetric resampling on the five candidate matrices | A PBO per family from many paths rather than one | half a day scripting, minutes CPU |
| 10 | Seed robustness of the per-fold search on #335 (first dive #3) | How much of the blind number is seed noise | ~35 min CPU |
| 11 | A sixth mechanism in the matrix (TTIBS or ETF dip) | Whether the fence/wide split holds beyond five | ~25 min build + ~5 min analysis |
| 12 | Per-crown minimum track record from lockbox trade statistics vs the engine's power field | A cheap closed-form cross-check on the "cannot confirm" claim | minutes |
| 13 | Purge-at-cut variant of the fold search on ENGU-Q and NQDIP | Whether straddling trades ever change a fold champion in the engine | ~1 h CPU |

---

## 8. Sources and files

### 8.1 Verified sources (exist; metadata checked; claims used above confirmed unless marked)

Econometrics / forecasting:
- Inoue & Kilian (2004/2005). In-Sample or Out-of-Sample Tests of Predictability: Which One Should We Use? Econometric Reviews 23(4), 371-402. https://www.tandfonline.com/doi/abs/10.1081/ETC-200040785
- Hansen & Timmermann (2012). Choice of Sample Split in Out-of-Sample Forecast Evaluation. EUI ECO 2012/10 / CREATES 2012-43 working paper (unpublished; specific p-value example not re-checked). https://rady.ucsd.edu/_files/faculty-research/timmermann/samplesplitmining2012_feb07.pdf
- Rossi & Inoue (2012). Out-of-Sample Forecast Tests Robust to the Choice of Window Size. JBES 30(3), 432-453. https://www.tandfonline.com/doi/abs/10.1080/07350015.2012.693850
- Pesaran & Timmermann (2007). Selection of Estimation Window in the Presence of Breaks. Journal of Econometrics 137(1), 134-161. https://rady.ucsd.edu/_files/faculty-research/timmermann/estimation-window.pdf
- Timmermann (2008). Elusive Return Predictability. International Journal of Forecasting 24(1), 1-18. https://rady.ucsd.edu/_files/faculty-research/timmermann/ijf_invited.pdf
- Diebold (2015). Comparing Predictive Accuracy, Twenty Years Later. JBES 33(1), 1-9. https://www.nber.org/papers/w18391
- Tashman (2000). Out-of-sample tests of forecasting accuracy: an analysis and review. IJF 16(4), 437-450. https://www.sciencedirect.com/science/article/abs/pii/S0169207000000650
- White (2000). A Reality Check for Data Snooping. Econometrica 68(5), 1097-1126. https://users.ssc.wisc.edu/~bhansen/718/White2000.pdf
- Hansen (2005). A Test for Superior Predictive Ability. JBES 23(4), 365-380. https://cdr.lib.unc.edu/downloads/zp38wf793
- Sullivan, Timmermann & White (1999). Data-Snooping, Technical Trading Rule Performance, and the Bootstrap. Journal of Finance 54(5), 1647-1691. https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf

Backtest overfitting / multiple testing in finance:
- Bailey & Lopez de Prado (2012). The Sharpe Ratio Efficient Frontier. Journal of Risk 15(2), 3-44 (benchmark in the worked example is 1, not 0.5). https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
- Bailey & Lopez de Prado (2014). The Deflated Sharpe Ratio. Journal of Portfolio Management 40(5), 94-107. https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- Bailey, Borwein, Lopez de Prado & Zhu (2014). Pseudo-Mathematics and Financial Charlatanism. Notices of the AMS 61(5), 458-471 (worked MinBTL figures not re-checked). https://www.ams.org/notices/201405/rnoti-p458.pdf
- Bailey, Borwein, Lopez de Prado & Zhu (2017). The Probability of Backtest Overfitting. Journal of Computational Finance 20(4), 39-69. https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- Bailey, Borwein, Lopez de Prado, Salehipour & Zhu (2016). Backtest Overfitting in Financial Markets. Automated Trader 39(2), 52-57 (practitioner). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2731886
- Harvey & Liu (2014). Evaluating Trading Strategies. Journal of Portfolio Management 40(5), 108-118. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2474755
- Harvey & Liu (2015). Backtesting. Journal of Portfolio Management 42(1), 13-28. https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
- Harvey, Liu & Zhu (2016). ...and the Cross-Section of Expected Returns. Review of Financial Studies 29(1), 5-68. https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
- Chordia, Goyal & Saretto (2020). Anomalies and False Rejections. Review of Financial Studies 33(5), 2134-2179 (sample period not re-checked). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3017677
- Arnott, Harvey & Markowitz (2019). A Backtesting Protocol in the Era of Machine Learning. Journal of Financial Data Science 1(1), 64-74. https://people.duke.edu/~charvey/Research/Published_Papers/P138_A_backtesting_protocol.pdf
- Wiecki, Campbell, Lent & Stauth (2016). All That Glitters Is Not Gold. Journal of Investing 25(3), 69-80. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220
- Suhonen, Lennkh & Perez (2017). Quantifying Backtest Overfitting in Alternative Beta Strategies. Journal of Portfolio Management 43(2), 90-104. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2757113
- McLean & Pontiff (2016). Does Academic Research Destroy Stock Return Predictability? Journal of Finance 71(1), 5-32. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623
- Lo (2002). The Statistics of Sharpe Ratios. Financial Analysts Journal 58(4), 36-52. https://rpc.cfainstitute.org/research/financial-analysts-journal/2002/the-statistics-of-sharpe-ratios

General statistics / machine learning:
- Hastie, Tibshirani & Friedman (2009). The Elements of Statistical Learning, 2nd ed., Springer, ch. 7 p. 222. https://faculty.stat.ucla.edu/ywu/research/documents/BOOKS/ElementsLearningII.pdf
- Cawley & Talbot (2010). On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation. JMLR 11, 2079-2107. https://www.jmlr.org/papers/v11/cawley10a.html
- Varma & Simon (2006). Bias in error estimation when using cross-validation for model selection. BMC Bioinformatics 7:91. https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/
- Dwork, Feldman, Hardt, Pitassi, Reingold & Roth (2015). The reusable holdout. Science 349(6248), 636-638. https://www.science.org/doi/10.1126/science.aaa9375
- Blum & Hardt (2015). The Ladder: A Reliable Leaderboard for Machine Learning Competitions. ICML 2015 / arXiv 1502.04585. https://arxiv.org/abs/1502.04585
- Recht, Roelofs, Schmidt & Shankar (2019). Do ImageNet Classifiers Generalize to ImageNet? ICML 2019, PMLR 97, 5389-5400. https://proceedings.mlr.press/v97/recht19a.html
- Roelofs, Shankar, Recht, Fridovich-Keil, Hardt, Miller & Schmidt (2019). A Meta-Analysis of Overfitting in Machine Learning. NeurIPS 2019, 9175-9185 (author order and pages corrected; "10,000-example floor" and "120 competitions" not in the paper). https://proceedings.neurips.cc/paper_files/paper/2019/file/ee39e503b6bedf0c98c388b7e8589aca-Paper.pdf
- Guyon (1997). A Scaling Law for the Validation-Set Training-Set Size Ratio. AT&T Bell Laboratories technical report. https://www.semanticscholar.org/paper/452e6c05d46e061290fefff8b46d0ff161998677
- Afendras & Markatou (2019). Optimality of training/test size and resampling effectiveness in cross-validation. JSPI 199, 286-301. https://arxiv.org/abs/1511.02980
- Bergmeir, Hyndman & Koo (2018). A note on the validity of cross-validation for evaluating autoregressive time series prediction. CSDA 120, 70-83. https://robjhyndman.com/publications/cv-time-series/
- Cerqueira, Torgo & Mozetic (2020). Evaluating time series forecasting models: an empirical study on performance estimation methods. Machine Learning 109(11), 1997-2028 (62 real series, not 174). https://arxiv.org/abs/1905.11744
- Gelman & Loken (2013). The Garden of Forking Paths. Columbia University working paper ("revised 2019" not confirmed). https://sites.stat.columbia.edu/gelman/research/unpublished/p_hacking.pdf
- Ioannidis (2005). Why Most Published Research Findings Are False. PLoS Medicine 2(8), e124. https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124

Practitioner books:
- Masters (2018). Testing and Tuning Market Trading Systems: Algorithms in C++. Apress. https://link.springer.com/book/10.1007/978-1-4842-4173-8
- Carver (2015). Systematic Trading. Harriman House (figures verified via https://the7circles.uk/systematic-trading-2-fitting-and-allocation/).
- Lopez de Prado (2018). Advances in Financial Machine Learning. Wiley (purging / embargo / CPCV mechanics confirmed via a secondary source only). https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086
- Pardo (2008). The Evaluation and Optimization of Trading Strategies, 2nd ed., Wiley, ch. 11 (walk-forward efficiency thresholds and 4-6x window ratio NOT found in the text; treat as lore). https://onlinelibrary.wiley.com/doi/abs/10.1002/9781119196969.ch11

### 8.2 Sources that exist but whose specific claims were not checked against the text (pointers only)

- Pesaran, Pick & Pranovich (2013). Optimal Forecasts in the Presence of Structural Breaks. Journal of Econometrics 177(2), 134-152.
- Clark & McCracken (2009). Improving Forecast Accuracy by Combining Recursive and Rolling Forecasts. International Economic Review 50(2), 363-395.
- Giacomini & White (2006). Tests of Conditional Predictive Ability. Econometrica 74(6), 1545-1578 (partially confirmed).
- Romano & Wolf (2005). Stepwise Multiple Testing as Formalized Data Snooping. Econometrica 73(4), 1237-1282 (hedge-fund example unchecked).
- Lo (2004). The Adaptive Markets Hypothesis. Journal of Portfolio Management 30(5), 15-29.
- Widmer & Kubat (1996). Learning in the Presence of Concept Drift and Hidden Contexts. Machine Learning 23(1), 69-101.
- Bergmeir & Benitez (2012). On the Use of Cross-Validation for Time Series Predictor Evaluation. Information Sciences 191, 192-213.
- Kearns (1997). A Bound on the Error of Cross Validation. Neural Computation 9(5), 1143-1161.
- Opdyke (2007). Comparing Sharpe Ratios: So Where Are the P-Values? Journal of Asset Management 8(5), 308-336 (simulation claims unchecked).

### 8.3 Suggested by the citation checks, not read in this dive

Harvey (2017), Presidential Address: The Scientific Outlook in Financial Economics, Journal of
Finance 72(4); Harvey & Liu (2020), False (and Missed) Discoveries in Financial Economics, Journal
of Finance 75(5); Jensen, Kelly & Pedersen (2023), Is There a Replication Crisis in Finance?,
Journal of Finance 78(5) (pushes back on the "most factors are false" reading); Linnainmaa &
Roberts (2018), The History of the Cross-Section of Stock Returns, RFS 31(7); Kaufman, Rosset,
Perlich & Stitelman (2012), Leakage in Data Mining, ACM TKDD 6(4).

### 8.4 Files and scripts (worktree `C:/Users/xride/AppData/Local/EdgeLog-worktrees/wfdive/`; nothing committed, no Firestore writes, no runner jobs)

Scripts (`tools/wfdive/isdepth/`): `scout_families.py` (family choice, knob counts, replay
check), `build_matrix.py <run_id>` (candidate matrix), `validate_matrix.py <run_id> [--folds ...]`
(engine reproduction), `analyze_matrix.py <run_id>` (A1-A4), `validate_matrix_NOISE.py` /
`analyze_matrix_NOISE.py` (per-family copies with the npz materialization fix; the shared scripts
re-inflate the compressed arrays on every access and stall on trade-dense families),
`verify_isdepth.py`, `aggregate_verify.py`, `print_verify.py` (independent re-verification),
`leak_probe_engine.py` (cold-vs-warm engine probes).

Data (`_wfdive_data/isdepth/`): `families.json`, `scout_families_raw.json`,
`timings_summary.json`; `matrix_{299,304,314,307,335}.{npz,json}` (per-trade arrays: entry/exit
bar and epoch-ns, net already after costs; per-config summaries; fold bounds; `profit_factor` may be
IEEE inf); `validate_{299,304,314,307,335}.json`; `analysis_{299,304,314,307}.{json,md}`;
`verify_{299,314,307,304,335}.json`, `verify_cross.json`, `leak_probe_engine.json`.

Reader notes for the matrices: window membership by `entry_bar` against the sidecar's fold bounds
(or `entry_ns` against a calendar cutoff, `>= t0`, `< t1`); apply the realism gate per window with
the window's own bar count; pick rule is argmax net over the gated set, else over the eligible set;
never subtract costs again; check unique-candidate counts before reading a fenced family's
landscape.

First deep dive artefacts: `docs/WF_LOCKBOX_DEEP_DIVE.md` and its `_wfdive_data/` and
`tools/wfdive/` files (listed there). Engine read for semantics this session:
`augur_engine/validate.py` (PBO matrix from the top 24 in-sample configs, gate at 0.5; power field;
adversarial pill), `augur_engine/optimize.py` and `augur_engine/auto.py` (deflated Sharpe with
N = the run's own evaluated configs), `augur_engine/analytics.py` (`deflated_sharpe`,
`probability_backtest_overfitting`).
