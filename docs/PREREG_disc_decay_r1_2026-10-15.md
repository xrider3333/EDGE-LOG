# PREREG: DECAY r1 - how much do this house's own validated Sharpes shrink out of sample? (DISC, 2026-10-15)

**Source.** Reading shelf No. 19: Falck, Rej & Thesmar, "Why and how systematic strategies decay" (arXiv 2105.01380; Quantitative
Finance 22(11), 2022).
- 60 US stock anomalies, replicated.
- The discount ratio q = SR_OOS / SR_IS has a median of 0.55; post- on pre-publication Sharpe has a slope of 0.57 (their Fig. 1).
- Signs of overfitting predict a bigger drop: signal complexity, sensitivity of the in-sample Sharpe to outliers or subsets, and a short in-sample
  period. So does a later publication year (-0.05 a year).

**The house question.** Owner 10-15: "keep exploring the reading shelf".
- Every number we act on is a walk-forward (WF) figure from a search. How much of it survives a stretch nobody tuned on?
- Does the paper's overfitting story predict WHICH of our runs shrink?
- This is a REPORT. No strategy is selected, changed or added; no lockbox is read beyond what each run already stored.
  The book's lockbox status (BOOK LOOKS r1) is untouched.

## Data (frozen now, read after this note is pushed)
- **Source:** every saved run doc (Firestore `runs`, read-only) whose `validate` block carries all of the following:
  - `is_sharpe` (the search winner's in-sample Sharpe);
  - `wf_oos.sharpe` and `lockbox.sharpe`;
  - `is_trades >= 100`, `wf_oos.trades >= 100` and `lockbox.trades >= 30`.
- **Census before any outcome was read:** 129 runs in 8 families (NOISE 38, ORB 27, ENGU-Q 25, DIP 14, TTM 11, TTIBS 9, GAPGO 3, CBU-Q 2).
- **Exclusions:**
  - VOID runs #369, #428 and #455;
  - any run whose `note` contains "VOID".
- **Units.** All three Sharpes are the engine's one definition: annualised per-trade net Sharpe (analytics.sharpe_from_pnls), the same
  units at each stretch. The IS figure is the DSR winner's.
- **Paper's cut:** SR_IS >= 0.3. Primary uses it; a sensitivity read uses SR_IS > 0.
- **The three stretches:**
  - **IS** = the tuning stretch (the search winner);
  - **WF** = the walk-forward OOS folds (still downstream of a search over the rule family);
  - **LB** = the lockbox (12 months, never tuned on).

## Outcomes
- **Q1 (primary, the paper's q):** q_LB = SR_LB / SR_IS.
  - Report the median, a 90% interval from a family-cluster bootstrap (resample families with replacement, then runs within each;
    2,000 draws, seed 20261015), and the slope of SR_LB on SR_IS through the origin.
- **Q2:** q_WF = SR_WF / SR_IS. Same reads.
- **Q3 (what the house acts on):** h = SR_LB / SR_WF, for runs with SR_WF >= 0.3.
  - Report the median, the cluster-bootstrap interval and family medians.
  - **This is the haircut used below.**
- Ratios are winsorised at [-2, 3] before means and slopes. Medians are robust and are the headline.

## Predictors (signs fixed now)
Three, chosen for power. 129 runs in 8 families give a minimum detectable standardised slope of about 0.25 at run level.
1. **IS Sharpe level, standardised: predicted (-).** Bigger in-sample winners regress more.
2. **log(trades per knob)** (`trades_per_param`): predicted (+). More in-sample evidence per free knob means less decay; this is the paper's "months
   in-sample" logic.
3. **Plateau share** (`plateau.good / plateau.tot`): predicted (+). A flat neighbourhood means less "best-variant" luck; this is the paper's "deviation
   from best q".

Model:
- q_LB (winsorised) on the three predictors plus family fixed effects, OLS with HC1 standard errors.
- **A predictor HOLDS when:** t >= 2 in the predicted direction AND the same sign in all 8 leave-one-family-out refits.
- Same model on q_WF as a secondary read.
- Run date (the paper's publication year) is reported descriptively only. Our runs span a few months, so it has no power.

## Verdicts (set now)
- **"HOUSE DECAY LIKE THE PAPER"**: median q_LB in [0.35, 0.75]. Otherwise "LESS DECAY" (above 0.75) or "MORE DECAY" (below 0.35).
- **Forward haircut per book / live leg** = its family's median h (Q3). If the family has fewer than 8 runs, the house median is used.
  - Expected forward ROC @ $30k = the leg's WF ROC x h, printed beside its WF ROC.
  - DD5, DD % from peak and Sortino: '-' (no curve is simulated).
  - Legs: ORB #234 / #314, ENGU-Q #335, TTM #459, NOISE #422 / #382, DIP #424.
- **Predictors:** each one HOLDS or does not, per the rule above. A holding predictor becomes a screen to read beside a new run's WF number.
  It is not a gate until MANAGER says so.

Harness: `tools/disc_decay_r1.py`. It checks this note's LF sha256 at start and stops on a mismatch.
