# CANDIDATE BOARD -- does the search's own picking generalise?

Built 2026-09-09 by `tools/candidate_board.py`. Pool: **135 Auto-Validate runs / 771 candidates**; **46 runs** have a lockbox score on >= 3 candidates and carry the questions below. Every question was written down before any answer was computed (see the module docstring).

**Terms.** *Candidate* = one of the ~10 parameter sets a run short-lists. *Crowned* = the one the run declared champion. *In-sample (IS)* = the window the search fitted on. *Walk-forward (WF)* = rolling out-of-sample folds inside that window. *Lockbox (LB)* = the final months the search never saw -- the honest score. *net* = dollars. *PF* = gross win / gross loss. *net/DD* = net per dollar of worst drawdown. *Spearman rho* = rank correlation, 0 means the ordering carries no information. *Fence* = a crowned knob sitting on the edge of the range searched.

## SCOPE CORRECTION (supervisor, verified independently)

The crown is NOT picked on in-sample net. `augur_engine/validate.py` picks it with
`max(crown_pool, key=(wf_oos_pnl, folds_held, is_pnl))` -- walk-forward out-of-sample PnL first,
in-sample only as the last tiebreaker. In-sample net decides the SHORTLIST (which ten configs get
scored out of sample), not the winner. So the results above say:

* The final tie-break among the ten finalists adds nothing measurable. Walk-forward rank does not
  predict lockbox rank (rho +0.023, p=0.74) and the crowned cell does not beat the average of the
  other nine in the sealed year (19 of 46 runs, p=0.30, median -$73). Numbers re-derived by the
  supervisor from candidates.csv: identical.
* This does NOT show the search is worthless. All ten finalists are already elite by in-sample, so
  this is a test of picking among finalists, not of finalists versus the field. Whether the
  shortlist beats a random config from the searched cloud is UNTESTED, because the cloud is stored
  with in-sample scores only. The `oos_sample_k` engine flag being built alongside this study is
  what would answer it.
* Power: 46 runs, dominated by NOISE (14) and TTMSQZ (13) on overlapping tape, so the effective
  sample is smaller still. A null here rules out a large effect, not a small one.

## Q1 -- Does the in-sample winner win out of sample?

Per run, rank the candidates by IS net and by LB net, then correlate the two orderings. Row 1 (**primary**) ranks on `is_pnl`, the number the search itself optimises. Row 2 ranks on the `cal.is` 75%-split calibration slice -- both were pre-committed and both are shown; see the Q1 disclosure in the module docstring.

| in_sample_field | runs | mean_rho | median_rho | share_rho_negative | perm_p | top3_share | top3_null |
| --- | --- | --- | --- | --- | --- | --- | --- |
| is_pnl (PRIMARY) | 46 | 0.018 | 0.000 | 0.500 | 0.779 | 0.370 | 0.330 |
| cal.is (robustness) | 46 | 0.123 | 0.152 | 0.370 | 0.033 | 0.304 | 0.330 |

On the primary field the top-IS candidate lands **top-3 in the lockbox in 37% of runs** vs **33% expected by chance** (binomial p = 0.334).

## Q2 -- Is the crowned candidate better than a random one of the ten?

Paired per run: crowned lockbox score minus the mean of the other candidates. Sign test on the differences; effect size = Cohen's d on the paired differences.

| metric | n_runs | crown_wins | share | median_diff | cohens_d | sign_p |
| --- | --- | --- | --- | --- | --- | --- |
| LB net ($) | 46 | 19 | 0.413 | -72.937 | -0.163 | 0.302 |
| LB profit factor | 46 | 19 | 0.413 | -0.031 | -0.162 | 0.302 |
| LB net/DD | 46 | 19 | 0.413 | -0.088 | -0.193 | 0.302 |

## Q3 -- Which knobs are structural constants and which are noise?

For each family and knob, the crowned value in each run is expressed as a POSITION in the range the search covered (0 = bottom of range, 1 = top). `iqr_frac` = interquartile spread of that position: <=0.10 = **CONSTANT** (the crown always lands in the same place -- a real structural value), >0.35 = **NOISE** (the crown lands anywhere). `drift_rho` = rank correlation of the crowned value with run date.

Across 54 (family, knob) pairs with >=3 crowned runs: **9 CONSTANT, 27 loose, 18 NOISE.**

Most stable knobs (lowest spread):

| famKey | param | kind | n_runs | iqr_frac | median_pos | drift_rho | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NOISE | flat_eod | on/off | 9 | 0.000 | 1.000 | -0.411 | CONSTANT |
| NOISE | band_mult_short | range | 13 | 0.000 | 0.500 | -0.419 | CONSTANT |
| TTIBS | ibs_entry | range | 7 | 0.000 | 0.778 |  | CONSTANT |
| TTIBS | ma200 | on/off | 7 | 0.000 | 0.000 |  | CONSTANT |
| ENGU-Q | er_th | range | 3 | 0.024 | 0.333 | 0.000 | CONSTANT |
| TTIBS | mon_drop | range | 7 | 0.033 | 0.133 |  | CONSTANT |
| TTIBS | hold_cap | range | 7 | 0.036 | 0.500 | 0.374 | CONSTANT |
| ORB | target_R | range | 21 | 0.042 | 0.333 | 0.014 | CONSTANT |
| NOISE | vol_skip_pct | range | 6 | 0.058 | 0.909 | 0.696 | CONSTANT |
| ENGU-Q | max_tnx_chg20 | range | 3 | 0.117 | 0.300 | 0.500 | loose |

Loosest knobs (the search picks a different value every time):

| famKey | param | kind | n_runs | iqr_frac | median_pos | drift_rho | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ORB | skip_holidays | on/off | 12 | 1.000 | 0.000 | 0.171 | NOISE |
| NOISE | skip_holidays | on/off | 9 | 1.000 | 0.000 | 0.693 | NOISE |
| ORB | close_confirm | on/off | 13 | 1.000 | 0.000 | 0.866 | NOISE |
| ORB | flat_eod | on/off | 12 | 1.000 | 1.000 | 0.051 | NOISE |
| TTMSQZ | stop_atr | range | 10 | 0.911 | 0.857 | -0.805 | NOISE |
| TTMSQZ | kc_mult | range | 13 | 0.667 | 0.667 | -0.509 | NOISE |
| ORB | breakout_buf | range | 8 | 0.667 | 0.283 | -0.170 | NOISE |
| ORB | partial_exit_R | range | 8 | 0.625 | 0.500 | 0.810 | NOISE |


`kind` = *on/off* when the search only ever tried two values (a switch, e.g. `skip_holidays`); a NOISE verdict there means the search flips that switch from run to run rather than that it wanders a wide range.

## Q4 -- Which knobs actually move the result?

`pps` = predictive power score, the run's own measure of how much a knob explains the result (0 = explains nothing). Pooled across runs of a family, median.

| famKey | param | n_runs | med_pps | med_mi | med_absr | share_pps0 |
| --- | --- | --- | --- | --- | --- | --- |
| ENGU-Q | max_vix | 3 | 0.820 | 1.800 | 0.674 | 0.000 |
| ENGU-Q | vol_mult | 12 | 0.230 | 0.293 | 0.564 | 0.167 |
| ENGU-Q | trail_frac | 12 | 0.120 | 0.207 | 0.494 | 0.250 |
| ENGU-Q | er_len | 4 | 0.024 | 0.040 | 0.241 | 0.250 |
| ENGU-Q | er_th | 3 | 0.015 | 0.073 | 0.192 | 0.333 |
| ENGU-Q | tl_len | 12 | 0.009 | 0.058 | 0.291 | 0.500 |
| ENGU-Q | act_R | 11 | 0.000 | 0.001 | 0.079 | 0.909 |
| ENGU-Q | atr_len | 11 | 0.000 | 0.002 | 0.038 | 0.909 |
| ENGU-Q | breakeven_R | 12 | 0.000 | 0.071 | 0.112 | 0.833 |
| ENGU-Q | buf_atr | 11 | 0.000 | 0.012 | 0.073 | 1.000 |
| ENGU-Q | ema_len | 11 | 0.000 | 0.000 | 0.107 | 1.000 |
| ENGU-Q | limit_atr | 4 | 0.000 | 0.006 | 0.043 | 1.000 |


**71% of (family, knob) pairs have a median predictive power score of zero** -- the search reports most of its own knobs as explaining nothing.

## Q5 -- Should we crown on walk-forward or on in-sample?

Per run: how well does IS net order the lockbox, vs how well does WF out-of-sample net order it? Same primary/robustness split as Q1.

| in_sample_field | runs | mean_rho_IS | perm_p_IS | mean_rho_WF | perm_p_WF | wf_better_share | sign_p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| is_pnl (PRIMARY) | 46 | 0.018 | 0.779 | 0.023 | 0.749 | 0.435 | 0.461 |
| cal.is (robustness) | 46 | 0.123 | 0.033 | 0.023 | 0.749 | 0.522 | 0.883 |

## Q6 -- Fence check: did the search ever see the real optimum?

A crowned knob is *on a fence* when its value sits within 2% of the range width of the lowest or highest value the search covered (after auto-expansion). A fence crown means the true optimum may lie outside the box that was searched. **On/off switches are excluded** -- a knob with only two values searched has had its whole space covered, so it cannot be fenced in any useful sense; counting them would inflate this number (84% unfiltered vs 58% here). `med_binary` = how many such switches a typical crown in that family carries.

| famKey | n_runs | share_any | mean_frac | med_knobs | med_binary |
| --- | --- | --- | --- | --- | --- |
| ORB | 24 | 0.833 | 0.355 | 2.000 | 0.000 |
| ENGU-Q | 18 | 0.556 | 0.184 | 11.000 | 0.000 |
| NOISE | 15 | 0.400 | 0.141 | 4.000 | 2.000 |
| TTMSQZ | 13 | 0.615 | 0.257 | 4.000 | 0.000 |
| TTIBS | 7 | 0.000 | 0.000 | 3.000 | 1.000 |
| GAPGO | 2 | 0.500 | 0.167 | 2.500 | 0.500 |
| NQDIP | 2 | 1.000 | 0.209 | 13.500 | 5.500 |


Overall: **58% of crowned candidates have at least one knob on a fence**; on average **22% of a crown's knobs** sit on an edge.


## What this means for where new parameters come from

1. **The score the search optimises does not order the lockbox.** Ranking on `is_pnl` gives mean rank correlation 0.02 across 46 runs, permutation p = 0.779 -- indistinguishable from shuffling the ten candidates, and the top-in-sample candidate reaches the lockbox top-3 no more often than chance. The `cal.is` slice does slightly better but is not what the search ranks on, so it cannot be claimed as a working selection rule.
2. **Crowning adds nothing measurable.** The crowned candidate beats the mean of the others in the lockbox in 19/46 runs (sign p = 0.302, d = -0.16). On this evidence the choice among the short-list is a coin flip -- the short-listing itself may still be doing work, but the final pick is not.
3. Of 54 (family, knob) pairs, 9 land in the same place every run (structural) and 18 land anywhere in their range (noise). Only the constants are worth carrying into a new strategy; the noise knobs should be FROZEN at their median rather than re-optimised, because re-optimising them is what burns the degrees of freedom that PBO and DSR then have to pay for.
4. 71% of knobs have zero median predictive power in the search's own relationship block. A search over knobs that explain nothing is a search over noise -- the fix is fewer knobs, not more trials (see also edgelog-validate-trial-budget).
5. Walk-forward orders the lockbox better than in-sample in 43% of runs (sign p = 0.461; mean rho WF 0.02 vs IS 0.02). Neither number is a usable ranking signal on its own.
6. 58% of crowns sit on at least one range edge. Where a crown is fenced the search never bracketed the optimum, so that knob's value is a statement about the box we drew, not about the market.

**Where new parameters should come from.** Not from re-running the same search wider or longer: the numbers above say the ranking inside a short-list is close to chance, most knobs explain nothing, and a large share of crowns are pinned to a fence we drew ourselves. The leverage is (a) freeze the noise knobs at their pooled median and search only the constants, which shrinks the effective parameter count and lifts DSR for free; (b) stop treating the crowned row as the answer -- neither in-sample NOR walk-forward orders the lockbox, so the short-list should be carried forward as a SET (or pooled as a book leg) rather than collapsed to one cell by a tie-breaker that measures nothing; (c) treat any fenced crown as an unfinished search -- widen that one knob or drop it; and (d) spend the saved compute on NEW INFORMATION (the KEEL v12 lesson) rather than finer slicing of the same tape.
