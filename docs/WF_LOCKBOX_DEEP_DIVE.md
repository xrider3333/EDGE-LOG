# Walk-forward vs lockbox: what should decide a go-live? (deep dive, 2026-09-16)

Owner questions, answered from the saved run records (351 runs read once from Firestore by the
Gather agent, 310 non-book), four analysis lenses, and an adversarial verification of every lens.
Every number below is the VERIFIED version; refuted claims are dropped, revised ones appear as
revised. Where the data is thin it says so.

Units: the engine keeps money in NQ points; the web multiplies by $20 a point. Ratios and profit
factors are unitless and are the numbers to trust across eras.

Vocabulary used throughout:

- **Tuning window** = everything before the sealed year. **Sealed year** = the lockbox (usually the
  last 12 months, settings frozen, looked at once).
- **Tuning search** = the main optimisation. It sees only the first three quarters of the tuning
  window (for the ENGU-Q crown #335: mid-2010 to late 2021).
- **Finalists** = the ten best in-sample settings the search produced.
- **Crowning step** = the finalists are each replayed with fixed settings over the walk-forward years
  and the one with the most walk-forward money is crowned. On by default since 2026-07-23.
- **Walk-forward, fixed settings** ("WF fixed") = the crowned settings held constant over the
  walk-forward years (2016 to 2025 on the crowns). This is the run report's 1E walk-forward column.
- **Walk-forward, re-tuned** ("WF blind" / the walk-forward test) = eight folds, each re-tuned on its
  own past only, then traded blind on the next unseen slice; the eight unseen slices stitched
  together. This is the WF OOS pill, the 1C curve and what COMPARE now reads on the WF stage.
- **Pinned run** = a strategy file with every knob fixed, so the search evaluates one configuration.
  47 of the 187 validates are pinned, including the ORB crown #257 and the NOISE run #243. On a
  pinned run "re-tuned" and "fixed" are the same configuration by construction.

---

## 1. Short answers

**Q1. Why is the re-tuned walk-forward lower than the fixed-settings walk-forward?**
Because the fixed-settings number is the score the crown was picked on, and about half of it was
inside the tuning search's own data. The crowning step tries ten finalists on the walk-forward years
and keeps the best one, so the fixed number is a best-of-ten on exactly that stretch. On top of that
the tuning search itself had already seen the first 58% of the walk-forward span (its data runs to
late 2021; the walk-forward years start in 2016). The re-tuned folds have neither advantage: each
fold picks from a fixed list of 300 random candidates with a weaker search, on a shorter window,
and never gets to look at the years it is scored on. Measured on identical slices the re-tuned
number sits about 16% below the crown's fixed number on runs with a real shortlist, and exactly
equal on pinned runs where there was nothing to choose. A further one to two percent (17% on NOISE)
is a cold-start artefact of slicing the folds. The re-tuned number is the honest one; it is lower
because the fixed number is inflated, not because re-tuning is broken. Confidence: high.

**Q2. Should go-live decisions rank on walk-forward at all?**
Yes, but on the re-tuned walk-forward, not the fixed one. Your instinct that fixed-settings
walk-forward is hindsight picking is correct and now measured. Your other instinct, that the sealed
year is the only true test, is half right: it is the cleanest test of the frozen settings, but it is
far too short to rank on. The engine's own power calculation says a 12-month lockbox has roughly an
11% chance of confirming a crown's claimed edge, and even 36 months would not get any crown near
80%; the pass rule (money above zero) lets a no-edge strategy through half the time at any length.
The re-tuned walk-forward profit factor, by contrast, predicts the sealed year's profit factor
almost exactly (sealed year lands within one to two percent of it on average), while the fixed
walk-forward profit factor runs five to nine percent too high. And ranking many runs on one sealed
year has the same selection problem you object to in the fixed number: it becomes the luckiest year
out of many looks. Confidence: medium-high for the calibration, medium for the selection findings.

**Q3. Is the walk-forward tuning span too long? Do the later years add edge?**
The later walk-forward years are not a tuning resource that adds edge; they are the test. Pooled
across every strategy, later folds are no better than early ones. Per family the picture splits:
ENGU-Q and ORB folds get harder as the years go on, NOISE and TTM squeeze folds get easier. Neither
is "more data makes better settings"; it is the market changing. Whether the early data does the
legwork depends on the family: for the 2-3 knob NOISE filters freezing the settings after the first
fold loses almost nothing, but for ENGU-Q (the one crown with a real search) frozen early settings
give up about a fifth of the walk-forward money, and the very first fold's settings lose money in
the sealed year while the last fold's settings beat the crown there. The one direct test of tuning
on less data (ENGU-Q only, one seed) found three to five years of training picks the same settings
as six; below three years the answer flips on a single fold. Not enough evidence to shorten
anything. Confidence: medium on the trend, low on any specific window length.

**Q4. Could we give more time to a longer lockbox instead (24 to 36 months)?**
Worth doing for slow-warm-up strategies (anything on daily bars or with a 250-day filter), and
worth considering at 24 months for the rest, but it will not turn the sealed year into a ranking
statistic. What it does buy: the false-fail chance on a real edge drops (a random 12-month slice of
the crowns' own post-2021 record is positive about 95% of the time, 99% at 24 months; the weakest
crown goes from 87% to 95%), and the cold-start loss at the start of the sealed year falls from a
quarter of the trades to a twentieth. What it costs: the most recent year of tuning data, which for
ORB and NOISE is above-average and improving. The cold-start problem is better fixed at the root by
warm-starting the sealed year and the folds, which is an engine change awaiting your call.
Recommendation: 24 months for daily-bar and long-warm-up legs (already done for NQDIP), 12 months
plus a warm start for intraday legs, do not go to 36. Confidence: medium.

---

## 2. Evidence per question

Sample sizes are given as runs / families, where a family is one strategy file on one market and
bar size. The families collapse into eight mechanisms (ORB, ENGU-Q, NOISE, TTM squeeze, NQDIP,
ETF dip, GAPGO, TTIBS), and NOISE and ENGU-Q variants dominate the recent record, so any
corpus-wide share is closer to eight votes than a hundred. Runs that share one strategy file
re-validated with small tweaks are counted once wherever "dedup" is stated. Books (pooled legs, no
folds) and zero-trade tests are excluded everywhere.

### Q1: the gap between fixed-settings and re-tuned walk-forward

**The mechanism, read from the engine (not inferred).**
- The crown is chosen as the maximum summed walk-forward money among the finalists (up to ten,
  the runner passes ten), each replayed with fixed settings on the anchored fold test slices. The
  saved record confirms the crowned finalist is the top walk-forward scorer on 118 of 118
  multi-finalist runs (79 families), tautologically.
- The tuning search sees the first 75% of the tuning-window bars; the walk-forward folds test bars
  40% to 100%. So 58% of the fixed walk-forward span is inside the search's own data. For the 20
  crowns replayed by the lockbox-length lens, 45% to 64% (median 53%) of the trades after the first
  fold start were in-sample for the crowned settings (#257 51%, #335 45%, #243 53%). The 75% cut
  reproduces the saved in-sample trade counts exactly on 18 of 20 runs.
- Each re-tuned fold draws a fresh list of 300 random candidates with a fixed seed and keeps the
  best training profit after a realism gate. No model steering, no range expansion (both are on
  in the main search). Because the seed is fixed, every fold of every scheme ranks the same 300
  candidates; the crowned settings are not among them (#335: not in the first 900 draws).

**Corpus decomposition (predict-lockbox lens, verified; 180 runs / 125 families with a usable
sealed year).**

| What is compared | Median ratio | 90% CI | n |
|---|---|---|---|
| Re-tuned / fixed, identical cold fold slices, runs with 2+ finalists | 0.844 | 0.776-0.920 | 98 / 74 |
| Same, runs with exactly ten finalists | 0.840 | 0.742-0.911 | 89 / 65 |
| Same, single-finalist (pinned) runs | 1.000 | 1.000-1.000 | 46 / 40 |
| Cold per-fold replay / warm continuous, SAME fixed settings | 0.985 | 0.946-0.995 | 156 / 118 |
| Re-tuned / warm fixed (what the app shows) | 0.836 | 0.797-0.936 | 144 / 114 |

Read: ~16% of the gap is selection among finalists plus the weaker per-fold search; ~1.5% is the
cold start of each fold slice (17% on NOISE #243, whose filter needs 40 sessions to warm up); the
in-sample overlap is on top and is quantified next.

**Where the crown's advantage sits (frozen-vs-retuned replay, verified; 30 runs replayed, of which
15 have a real search: ENGU-Q 5, NOISE 9, GAPGO 1 - three mechanisms).**
Crown fixed / re-tuned, same slices: 1.256 (CI 1.04-1.38) on the folds inside the search's data
versus 1.010 (CI 1.00-1.22) on the folds after it. #335: 1.66 inside, 1.22 after. The crowning step
itself changed nothing on 7 of the 21 "clean" runs including #335 (the in-sample best was crowned).
So the fixed number is inflated in two layers: fitting on the early folds, then best-of-ten on all
of them.

**Corpus split by whether a choice was made (lockbox-length lens, verified; 148 runs / 117
families / 8 mechanisms with both readings).**
- Families whose crown was picked among 9-10 finalists (77): fixed beats re-tuned on profit factor
  60/77 (78%) and on money 75/77 (97%).
- Families with one candidate (40, no choice possible): 20/40 on both, a coin flip. Within ORB
  single-candidate runs re-tuned wins 16/23 on profit factor.
- Warm-up confound: in the 28 families where the re-tuned folds trade under 0.8x the fixed count,
  fixed wins 96% on money but only 54% on profit factor.

**The three crowns.**
- #335 ENGU-Q (real search, ten finalists): fixed 22,377 pts / $447,548 / PF 1.94 / 729 trades;
  crowning score 21,868 pts (cold slices); re-tuned anchored 19,044; re-tuned rolling (the primary,
  saved test) 16,402 pts / $328,037 / PF 1.37 / 1,822 trades. Fixed profit factor on the in-sample
  part of the walk-forward span 2.59, on the out-of-sample part 1.64, sealed year 1.53. After the
  search's data ends (2021-11-24): fixed 11,344 pts on 297 trades vs re-tuned 8,537 on 1,056.
- #257 ORB (pinned, zero free knobs): fixed 16,620 pts / PF 1.35 / 1,539 trades vs re-tuned
  16,955 / PF 1.36 / 1,541: the 2% is slicing, not selection. After 2021-10-28 the re-tuned figure
  is slightly ahead (12,007 vs 11,726). Not evidence about re-tuning either way.
- #243 NOISE (pinned): fixed 15,184 pts / 2,571 trades vs re-tuned 12,687 / 2,141: a 17% cold-start
  haircut from slicing, identical configuration.

Confidence: high. The mechanism is code-verified; the corpus ratios reproduce to three decimals
across two independent scripts; the split by finalist count is the decisive check.

### Q2: which reading predicts the sealed year, and what the sealed year can carry

**Calibration on profit factor (unitless; predict-lockbox lens, verified).**

| Reading | Sealed-year PF / reading PF, median | 90% CI | n | Verdict |
|---|---|---|---|---|
| WF fixed | 0.946 | 0.883-0.981 | 156 / 118 | 5-9% optimistic, CI excludes 1 |
| WF re-tuned | 0.986 | 0.921-1.020 | 155 / 115 | calibrated |
| In-sample (first 75%) | 0.958 | 0.916-1.018 | 180 / 125 | no detectable bias |

Paired within-run error on profit factor, fixed minus re-tuned: +0.006 (CI 0.004-0.009), i.e. the
re-tuned reading is the more accurate one by a small, consistent margin. The lens's original
raw-point version (fixed "least biased" at 1.31x) was refuted: raw-point ratios across eras are
dominated by the NQ price level (the in-sample "3.16x" is the 2010-2021 vs 2025 price ratio, not
a model defect) and must not be used to rank readings.

**Ranking power (Spearman to sealed-year profit factor).** Fixed 0.37 (CI 0.20-0.50; 156/118),
re-tuned 0.33 (CI 0.14-0.50; 155/115), in-sample 0.32 (CI 0.17-0.45; 180/125). Indistinguishable.
Given a reading's profit factor above 1, the sealed year's is above 1 in 89-90% of runs whichever
reading is used; the three readings agree on sign in 143 of 144 runs and the 16 profitable-reading
to losing-year flips are the same 16 runs. Only one run in the universe had a negative reading, so
"a negative reading is a stop signal" is untestable here.

**The gap itself is a warning light.** Rank correlation between (fixed minus re-tuned, as a
fraction of fixed) and (sealed-year shortfall versus fixed) = 0.52 (CI 0.28-0.68; 98 pairs /
74 families; permutation null mean 0.035, p < 0.0005). The crowned finalist beats the median of
the other finalists by 22% on the walk-forward years (118 runs / 79 families).

**Does crowning on walk-forward years pick a better config? (the #88b holdout: every finalist's
sealed year is saved.)** Runs where the crowning step changed the pick away from the in-sample
best: 57 runs / 45 families. The walk-forward-crowned config beat the in-sample best on the sealed
year 20/45 (44%), two-sided p = 0.55; it was the best of its ~10-candidate field 7/45 (15.6%) vs
10.2% chance; median sealed-year rank of the crown 6 of 10. Across all runs with 4+ lockbox-scored
candidates (77 runs / 63 families) the within-run rank correlation to the sealed year is 0.118
for the walk-forward score and 0.117 for in-sample profit. #335's crown ranked 6th of 10 on its
sealed year; three finalists with lower walk-forward scores made twice its money. This matches the
candidate board (2026-09-09: rho +0.023, crown beats the other nine 19/46) and the frozen-vs-retuned
replay (in 13 re-crowned clean runs the crown had the better sealed year 4 times). Confidence:
medium (n = 45 cannot separate 44% from 50%; it can rule out a large benefit).

**What the sealed year can carry (lockbox-length lens, verified).**
- Engine's own power field (saved on 163 runs = 118 families = 8 mechanisms): median achieved
  power 0.11; 1 run powered (NQDIP #401, 24-month lockbox); 91.5% of families below 0.20. Crowns:
  #257 0.11 (minimum detectable edge 36.6 pts/trade = $731 vs claimed 6.3 pts = $126), #335 0.20
  (63.5 pts vs 20.1), #243 0.17 (14.2 pts vs 3.9; its lockbox is 18 months, 349 trades). Extrapolated
  power at 12/18/24/36 months: #257 0.11/0.13/0.15/0.18, #335 0.20/0.25/0.30/0.39, #243
  0.14/0.17/0.20/0.25. Months for 80% power on the claimed edge: 404, 120, 232.
- The pass rule (money above zero and profit factor at least 1) reduces to a sign test: a
  demeaned no-edge series passes 44-53% of the time at every length 12 to 36 months (identity, not
  a finding). 90% of 120 dedup families pass the sealed year; 100% of single-candidate families,
  81% of walk-forward-crowned ones.
- Sealed-year profit factor sits below the fixed walk-forward profit factor in 81% of
  walk-forward-crowned families (median gap -0.245) and below the re-tuned one in 72% (gap -0.149);
  in single-candidate families it sits ABOVE the fixed one in 83% (median +0.14).
- Cold start: the saved sealed-year run starts cold. Cold trades under 90% of the warm slice on
  42 of 171 runs (31 families); NQDIP #401 111 vs 174 trades (26,606 vs 71,446 pts), #400 100 vs 149,
  #307 30 vs 56, ETF dip #355 2 vs 9, NOISE #321 63 vs 101, #395 132 vs 208.

### Q3: the walk-forward span and whether later years add edge

**Fold position vs fold quality (predict-lockbox lens, verified).** Excluding pinned runs:
1,247 fold rows / 171 runs / 107 families, Spearman(fold position, fold profit factor) = -0.024
(CI -0.083 to 0.034); within-run mean -0.045. Per family, CIs exclude zero in opposite directions:
ENGU-Q -0.186 (CI -0.28 to -0.10; 236 rows / 22 families), ORB -0.19 (CI -0.32 to -0.04; 291 /
17), NOISE +0.15 (CI 0.02 to 0.32; 240 / 22), TTM squeeze +0.138 (CI 0.03 to 0.22; 152 / 16).
Late-half minus early-half median profit factor -0.056 (CI -0.135 to -0.007) while the share of
profitable folds rises +0.054 (CI 0.02 to 0.09). The training-bars correlation was dropped: it is
constant within rolling runs and measures bar density between runs.

**Freeze early vs keep re-tuning (frozen-vs-retuned replay, verified; 15 real-search runs in 3
mechanisms after removing 2 pinned crowns, 6 runs whose folds never changed settings, and one
duplicate pair #385/#387).**
- Frozen at fold 1 / re-tuned, folds 2-8: money 0.973 (CI 0.81-1.01; below in 11/15); by
  mechanism ENGU-Q 0.81, NOISE 0.98, GAPGO 1.28. Profit factor 1.015 (CI 0.99-1.07). On folds 6-8
  (after the search's data) money 0.898 (CI 0.67-1.05), ENGU-Q 0.62.
- Frozen at the midpoint / re-tuned, folds 6-8 (excluding the midpoint fold's own diagonal, which
  the lens had wrongly counted on both sides): money 0.946 (CI 0.67-1.00), below in 10/15; ENGU-Q
  0.73, GAPGO 0.30, NOISE 0.95. Profit factor 1.00 (CI 0.92-1.08). #335 0.46 on money, and #384
  0.51, #399 0.30, #386 0.67 are as clear, so #335 is the typical ENGU-Q case, not an exception.
- Learning curve: when re-tuning actually changed the settings, the fresher settings beat fold 1's
  on the next unseen slice 39 wins / 28 losses (58%). The lens's "31%" counted 59 identical cells
  as losses and is refuted. Consecutive folds of one strategy are not independent trials.
- Sealed year, the walk's last-fold settings vs the crown (15 runs): 5 last-fold wins, 3 crown
  wins, 7 ties (the last fold had picked the crown's settings). ENGU-Q 5/5 for the last fold,
  24,703 vs 9,805 pts summed. #335: last-fold 4,785 pts (214 trades, PF 1.43), the file's own
  defaults 4,327 (PF 1.60), crown 2,908 (129 trades, PF 1.53), fold-1 settings -1,100 (PF 0.83).
- Rolling (~6-year window: fold 1's training length, 2010-06 to 2016-10 on #335) vs anchored (all
  history), raw fold money, identical test slices: 0.975 (CI 0.88-1.00), anchored better in 13/21,
  equal 3, rolling better 5. The earlier "rolling wins 64%" was 53 ties counted as rolling wins.
  Among non-pinned, non-tied runs anchored wins 45/73 (62%). This says nothing about training on
  LESS than ~6 years.

**Direct tune-on-less-data test (training-length lens, verified; effectively ONE family).**
#257 has zero free knobs (13/13 pinned), so it contributes nothing. #335, folds 4-8 only, one seed,
the same 300-candidate list every cell:
- 5-year vs 3-year training window: identical pick on 4 of 5 folds; fold 4 flipped to a candidate
  that did +27% better. Pooled 3-year +4.1% vs 5-year, +2.3% vs the deployed rolling scheme.
- 2-year window: pooled -40.6% vs 3-year, but entirely fold 8 (test 2024-05 to 2025-06, -79%);
  excluding fold 8 the 2-year window BEATS the 3-year one by +33%. Per fold vs 3-year: worse 2,
  equal 2, better 1. No ordering below 5 years is established.
- All history = the engine's own saved anchored scheme (all 5 cells reproduce the saved rows).
  Over all 8 folds anchored made +16.1% more than rolling (19,044 vs 16,402 pts) with one losing
  fold (fold 6: -1,190 pts, the only negative cell in the grid); the engine picks the primary
  scheme by fold consistency, so rolling won 8/8 vs 7/8.
- Fold 5 had three different picks across five training windows; across the 20 cells there are
  7 distinct picks from one candidate list. The pick is window-sensitive because runner-up gaps are
  small, not because a search fails to converge.
- Speed: mean seconds per 300-trial fold search: all history 118, 5-year 77, 3-year 49, 2-year 29.

**Prior evidence (memory).** ORB meta walk-forward 2026-09-09: re-picking each August on all
history made $166k over 11 forward years, on recent history $233-279k, pooling the top K
$182-225k, a random eligible config $312k, leaving the defaults alone $377k. Candidate board: 71%
of knobs have zero predictive power.

Confidence: medium that the later years are the test, not a tuning resource, and that the effect
of re-tuning is family-specific (helps ENGU-Q net, neutral for the small NOISE filters, hurts ORB
by the meta walk-forward); low for any statement about a specific training length (one family, one
seed, one candidate list, five folds).

### Q4: lockbox length

- Real-edge pass probability of the crowns' own post-2021 record, month-block bootstrap: median
  across 20 runs (6 mechanisms) 0.955 at 12 months, 0.981 at 18, 0.991 at 24, 0.998 at 36; the
  weakest 0.723 / 0.774 / 0.807 / 0.847. #335 0.872 at 12 months, 0.948 at 24; #257 0.968 / 0.994;
  #243 0.984 / 0.998. This is the share of the champion's own history that is net-positive over
  a window of that length (a sign test), not detection power; the lens's "trades the search never
  saw" pool was refuted (53% of it was in-sample) and these are the corrected post-split numbers.
- No-edge false pass: ~50% at every length (see Q2). No length reaches the "20% false pass /
  80% real pass" crossing under the current rule.
- Cold start at true window lengths, fresh cold replays: median trade loss 24% at 12 months, 5.3%
  at 24 (20 runs). NQDIP #401 loses 71% of a true 12-month lockbox (25 vs 87 trades, cold net
  -8,286 vs warm +9,400 pts) and 36% at 24 months; #400 58% / 33%; NOISE variants 17-37% at 12
  months, 4-15% at 24; #243 19% at 12 months (219 vs 269), 6% at 24; #257 and #335 0%.
- Cost of the extra year (the 12 months that would move from tuning-visible to sealed): #257 ORB
  174 trades / +4,641 pts / PF 1.52 (post-2021 average 1.45); #335 ENGU-Q 98 / +4,780 / PF 1.95
  (average 1.60); #243 NOISE 267 / +3,240 / PF 1.50 (average 1.45; the lens's 138 / +2,474 / 1.81
  was a six-month window). Fixed-champion profit factor rises significantly with calendar year on
  #257 (rho 0.53, p 0.04, partial years dropped) and #243 (0.59, p 0.02), both single-candidate so
  not selection artefacts; flat on ENGU-Q and NQDIP. But the sealed year itself trades below the
  preceding post-2021 stretch in 17 of 20 runs, so "most recent = best" is not general.
- Engine support: 28 runs already ran 18-month lockboxes and 2 ran 24 months (#400, #401); the
  18-month runs are early NOISE/TTIBS batches (median lockbox PF 1.17 vs 1.44 for 12-month runs) and
  say nothing about length itself.

Confidence: medium. Direction and cold-start effect are solid; the net effect on crowning was not
tested (no run was re-validated with a different lockbox length in this dive).

---

## 3. What the evidence does NOT show, and open risks

- **Independent votes are few.** 125 families are 8 mechanisms; NOISE and ENGU-Q variants dominate
  everything after August. Every corpus share should be read as roughly eight votes with unequal
  weights. Several lens claims of "high confidence on 21 families" were really 3-4 mechanisms.
- **The training-length answer rests on one family, one seed, one candidate list, five folds.**
  With a different seed the candidate list changes and so may every pick. #257 cannot inform it.
- **The "re-tuned WF is calibrated" result is empirical, not structural.** It holds because
  freezing settings keeps profit factor roughly level (frozen/re-tuned PF 1.00-1.02 on every cut)
  while the crown's inflation roughly cancels; a family with a very different knob count or search
  could behave differently. It is also a forecast of the sealed year's profit factor, which is
  itself a noisy 130-350-trade number.
- **The sealed year is cold.** Every sealed-year number in this dive (and in the app's verdicts)
  is the cold figure; for NQDIP/ETF dip the sealed year is understated by 50-70% of profit. A
  24-month lockbox only patches the lockbox, not the folds, which are also cold.
- **Crowning-on-walk-forward "adds nothing" is n = 45.** It rules out a large benefit; it cannot
  rule out a small one. The one demonstration that motivated it (run #168, 2026-07-20) was a single
  case. The shortlist itself does carry information (run #360: finalists beat a decile-stratified
  sample of the cloud, per-trade p = 0.039).
- **The 58% in-sample overlap of the fixed walk-forward span is a bar-count fact plus a 15-run
  replay.** The queued 5-crown replay to quantify it directly (#335/#243/#257/#304/#384) never ran
  (its log is empty); the post-split figures in Q1 come from the lockbox-length verifier's replay of
  the same crowns and are consistent.
- **Per-family fold trends could be regime, not tuning.** ENGU-Q's later folds being harder and
  NOISE's easier match what is already known (NOISE amplitude grew ~7x, ORB profit factor rose
  1.09 to 1.41). This dive did not separate calendar year from fold position.
- **The file defaults beat the crown on ENGU-Q** (walk-forward folds 3/5 runs, sealed year 4/5;
  #335 defaults 4,327 vs crown 2,908 pts). Provenance is ambiguous: today's defaults may post-date
  those runs, so this is flagged, not concluded.
- **Zero-trade or near-zero sealed years** (ETF dip legs trading 7-13 times a year) carry no
  information at 12 or 24 months; length does not fix trade scarcity.

---

## 4. Recommendation

**What the COMPARE board should rank on for a go-live decision.**

1. Primary ranking reading: the re-tuned walk-forward (the walk-forward test), on profit factor
   first and money per year second, with a minimum trade count. It is the only pre-sealed-year
   reading that cannot be selected on, it forecasts the sealed year's profit factor within one to
   two percent, and its rank power is as good as either alternative. Default the board to it.
2. Show the fixed-settings walk-forward beside it, labelled as the crowning score, never as a
   test. Show the gap between the two as a chip; a large gap predicts a worse sealed year
   (rank correlation 0.52) and is the single most useful overfit warning the record already holds.
   On pinned runs the two are equal and the chip should say so.
3. The sealed year is a veto and a confirmation, not a ranking column. Require it positive with a
   trade floor and show it with the existing power pill; do not sort strategies by sealed-year
   money or R per year across many runs. With ten finalists per run all lockbox-scored, and dozens
   of runs on one calendar year, a lockbox leaderboard is a best-of-many-looks on a coin-flip
   pass rule: 90% of families pass it, and the sealed year ranks finalists no better than chance.
   This means the default rank read agreed on 2026-09-08 (R per year on the lockbox) should move to
   the walk-forward test, with the lockbox kept as the pass gate.
4. Sink zero-trade walk-forward tests below every run that traded (already decided 2026-09-16),
   and flag cold-start runs on the board: any run whose cold sealed-year trade count is under 90%
   of the warm continuous slice gets a warm-up badge and its sealed-year money is read as a floor.

**What the validation design should change.**

5. The crowning step (best walk-forward money among the finalists) should stop deciding the
   crown. The evidence says it does not pick a better config for the sealed year (44% wins, sixth
   of ten on average) and it costs the honesty of the fixed walk-forward column for every run.
   Keep the shortlist and keep saving every finalist's walk-forward and sealed-year figures as
   evidence; crown from the tuning search alone (its in-sample best, or the plateau pick when the
   search produced one). Then the fixed-settings walk-forward on the stretch after the search's
   data ends (roughly the last quarter of the tuning window, three to four years on the crowns) is
   a clean out-of-sample test of the crowned settings, and the re-tuned walk-forward stays the
   blind test of the whole procedure. This reverses a decision approved on 2026-07-20 on one
   example, so it is an owner call; the prospective check costs nothing because both crowns'
   sealed years are already saved on every run.
6. If the crowning step is kept, then the fixed walk-forward must be reported only on the stretch
   after the search's data ends and labelled as selected, and the board must not rank on it.
7. Warm-start the walk-forward folds and the sealed year: evaluate on all history up to the end of
   the slice and keep only trades that enter inside the slice. This is the root fix for the
   cold-start defect (50-70% of NQDIP's sealed-year profit, 17% of NOISE's re-tuned walk-forward).
   It changes every future verdict, so it is an owner call; re-judge the ETF stack and NQDIP 1.1
   afterwards.
8. Lockbox length: 24 months for daily-bar and long-warm-up legs (in place for NQDIP), 12 months
   with a warm start for intraday legs. Do not move to 36 months: it does not make the sealed year
   a statistical test and it removes an above-average year from tuning on ORB and NOISE.
9. Do not shorten the walk-forward training span on the current evidence. The span's value is as
   a test; the one direct test of tuning on less data is one family and one seed. If the goal is
   to make the re-tuned number stronger rather than shorter, the lever is giving each fold the same
   search quality the main search has (model steering and range expansion), which is an engine
   change to weigh separately.
10. Keep the "leave the parameters alone" bar for re-crowning: a candidate must beat the standing
    settings forward, not win in-sample or on one sealed year. The record shows ORB re-picks lose
    to defaults and the NOISE crown swap (#243 to #304) was a coin flip.

---

## 5. Proposed follow-up experiments, with cost

All CPU work under the shared CPU lock, below-normal priority, off market hours.

| # | Experiment | What it settles | Cost |
|---|---|---|---|
| 1 | Run the queued in-sample-overlap replay on #335 / #243 / #257 / #304 / #384: fixed walk-forward on the full span vs the post-split stretch, per crown | The exact size of the in-sample layer of the fixed number on the traded crowns | ~5 replays, under 10 minutes CPU; script exists (`tools/wfdive/verify_predict_replay.py`) |
| 2 | Corpus read of every saved finalist's sealed year: crowned vs in-sample best vs plateau pick vs the median finalist, dedup by family | Which crowning rule the record favours before changing the engine; also the prospective check if the rule changes | JSON only, minutes |
| 3 | Seed robustness of the per-fold search on #335: 3 extra seeds, 8 folds, primary scheme | How much of the re-tuned number is seed noise; whether the fold pick is stable enough to call a trend | 24 fold searches at ~80 s = ~35 min CPU |
| 4 | Train-length sweep on a second real-search family (NOISE #304 or #382 on 5m; 4 windows x 5 folds) | Whether "3-5 years picks the same as 6" generalises past ENGU-Q | ~20 cells at ~20 s = ~10 min CPU |
| 5 | Warm-start prototype: evaluate folds and the sealed year on history-to-slice-end, entry inside the slice; re-run the 20 replayed crowns fixed-settings only | Size of the cold-start correction per family before deciding the engine change | ~1 day engineering; replay ~10 min CPU |
| 6 | Re-validate the three crowns at 24-month lockboxes, windows pinned | Whether the crowning and the verdict move when a year leaves the tuning window; the only direct Q4 test | 3 full validates: ORB 5m ~20 min, NOISE 5m ~30 min, ENGU-Q 1m ~1-2 h runner time |
| 7 | Per-family fold trend by calendar year rather than fold position | Separates regime from tuning-span effects | JSON only, minutes |
| 8 | Steered per-fold search (steering + expansion inside folds) on #335 | Whether a stronger fold search closes the fixed-vs-re-tuned gap | ~1 day engineering + ~1 h CPU per run |

---

## 6. History: why the pipeline ranks on walk-forward

- **Before 2026-07-20.** The champion was the best realism-gated in-sample configuration, plateau-
  informed. The walk-forward stage produced efficiency and consistency gates only; the sealed year
  got one look at the in-sample champion.
- **2026-07-20, the trigger.** Run #167 (TTIBS) crowned the sharpest in-sample config ($257,873
  in-sample) which collapsed in the sealed year ($35,083, overfit gate fired, verdict WEAK) while
  run #165's weaker-in-sample champion had double the sealed-year money. The ledger entry
  (BACKTESTING_STACK.md item 3) proposed: take the top ~5 plateau-distinct in-sample configs, score
  each across the walk-forward folds ("legitimately usable for selection"), crown the best
  fold-out-of-sample performer, give only the crown the single sealed-year look. It explicitly
  rejected selecting on the sealed year: "Selection on the LOCKBOX top-5 would be the trap (spends
  the holdout, 5 looks instead of 1) - WF folds are the correct middle tier." Owner-approved the
  same day, together with the sealed-year power calculation (#94).
- **2026-07-20, the demonstration.** Run #168 re-ran #167's job with the new step: the in-sample
  best was dethroned and the walk-forward-crowned config paid $87,936 at PF 1.56 in the sealed year
  vs #167's $35,083 at PF 1.21 - one case, the machinery test.
- **2026-07-21.** Finalists carried through the sealed year for display only (#88b, top 3), with
  a broader display set of 10 for the robustness chart; "NEVER used to pick the champion".
- **2026-07-23.** The step became the default (owner "option A") after run #175 (deploy book) had
  saved no crown pool because only the runner's validate branch had been passing it.
- **2026-08-02 to 08-06 (web v64.96 to v68.5).** Rank-by controls and a HINDSIGHT badge on the
  gate matrix ("the crown never moves"); v68.1 every listed config got a sealed-year number after
  the owner asked "why only push the WF years ... I would like it to run through the LB as well to
  see apples to apples"; v68.5 the crown pool widened from the top 5 to the top 10 in-sample configs
  "still ranked by walk-forward, and the LB still never chooses". 2026-08-03: the ML gate's own
  crowning rule became net dollars with an 80% MAR floor.
- **2026-08-08 (web v70.8).** The report's KPI and 1E walk-forward column were rebuilt from the
  crowned configuration's own trade list sliced at calendar boundaries - the owner asked for "whats
  most accurate for the configs performance" - and the re-tuned procedure moved to a separate WF
  OOS chip. From this point the column called walk-forward on the report was the fixed-settings
  reading.
- **2026-08-18.** Net over drawdown shown to be a coin flip at these sample sizes; guidance became
  prefer profit factor and sealed-year behaviour.
- **2026-09-05.** NOISE crown moved from #243 to #304 on a studies read that "the lockbox agrees
  independently" (rank correlation all-stage to lockbox 0.29); on 2026-09-13 the board recorded the
  swap "was a coin flip, not an upgrade".
- **2026-09-08.** COMPARE rebuild signed off; the leaderboard's default rank read set to R per
  year on the lockbox (v73.609).
- **2026-09-09.** Candidate board over 771 finalists / 135 validates: the crown beats the mean of
  the other nine on the sealed year 19/46, walk-forward rank to sealed-year rank rho +0.023; run
  #360 showed the shortlist does beat the field. ORB meta walk-forward: re-optimising yearly $166k
  vs leaving defaults alone $377k. Guidance: "stop treating the crowned cell as special", freeze
  the crowns.
- **2026-09-14.** ORB variants judged on walk-forward plus calendar-year money (ORB_BEST_WF.md),
  with the caveat that walk-forward on a pinned run is the fixed config over history it was chosen
  on.
- **2026-09-15.** The engine began saving the re-tuned folds' stitched out-of-sample block on every
  validate (06bffa6) and 160 older runs were backfilled; web 73.816 drew it in the report and
  73.819 made COMPARE, RUNBOARD, PICK RUNS and EXPLORE read it on the WF stage.
- **2026-09-16.** Owner decisions: sink zero-trade walk-forward tests; the two walk-forward
  readings named ("WF fixed" = crowning score, "WF blind" = re-tuned test); the owner leaned fixed,
  the lead recommended blind; this deep dive was commissioned to settle the ranking basis.

The through-line: every step chose walk-forward over the sealed year for selection because the
sealed year must stay unspent, and every step chose the fixed-settings reading for display because
it describes the configuration that is actually traded. What was never measured until now is that
the fixed reading is the selection score itself, and that the crowning step's benefit was a single
case.

---

## 7. Files and scripts

Worktree: `C:/Users/xride/AppData/Local/EdgeLog-worktrees/wfdive/` (nothing committed; Firestore
read once by the Gather agent, never written).

Data (all under `_wfdive_data/`):
- `runs.json` - the 351 run records as read; `coverage.json` - field coverage; `probe_*_full.json`
  - full docs of #257 / #335 / #366.
- `lens_predict.json`, `fold_position_trend.json` and `verify_predict-lockbox.json` (+ `.log`) -
  which reading predicts the sealed year; the verifier's numbers are the ones quoted.
- `lens_frozen.json`, `verify_frozen-vs-retuned.json`, `verify_frozen_matrix.json` (+
  `verify_frozen.run.log`) - the frozen-vs-re-tuned replay matrix and sealed-year replays.
- `lens_trainlen.json` (+ `lens_trainlen.log`, `lens_trainlen2.log`), `verify_training-length.json`
  - the training-window experiment on #335 / #257.
- `lens_lblen.json`, `aux_power_field_corpus.json`, `aux_fixed_vs_retuned_corpus.json`,
  `verify_lockbox-length.json` (+ `.run.log`) - lockbox length, power field, corpus fixed vs re-tuned.
- `verify_predict_replay.log` - empty: the in-sample-overlap replay never ran (follow-up 1).

Scripts (all under `tools/wfdive/`): `common.py` (CPU lock, low priority, shared paths),
`extract_runs.py`, `build_coverage.py`, `probe_doc.py`, `lens_predict.py`, `fold_position_trend.py`,
`verify_predict-lockbox.py`, `verify_predict_replay.py`, `lens_frozen.py`, `lens_frozen_addendum.py`,
`verify_frozen-vs-retuned.py`, `lens_trainlen.py`, `verify_training-length.py`, `lens_lblen.py`,
`lens_lblen_summary.py`, `aux_power_field_corpus.py`, `aux_fixed_vs_retuned_corpus.py`,
`verify_lockbox-length.py`.

Engine read for semantics (worktree copies, identical to main): `augur_engine/validate.py` (the
crowning step, its #88 docstring and the #88b / #94 blocks), `augur_engine/auto.py` (75/25 split,
fold construction, per-fold sampler), `augur_engine/wf_pool.py`, `augur_engine/ml_gate.py`,
`tools/backfill_wf_oos.py`.

History sources: `BACKTESTING_STACK.md` (items 3 and 13, the 2026-07-20 entries), the CHANGELOG in
`index.html` (v68.1, v68.5, v70.8, v73.609, v73.816, v73.819), and the memory notes
edgelog-wf-oos-curve, edgelog-candidate-board, edgelog-reoptimising-doesnt-pay,
edgelog-which-orb-to-trade, edgelog-gate-floor-rule, edgelog-netdd-unreliable,
edgelog-validate-header-75-split, edgelog-validate-coldstart-folds, edgelog-compare-rebuild.
