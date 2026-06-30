# EDGELOG — 12-Step Data-Testing Method Stack

*Adapted from Dr. Carl McBride Ellis's "A selection of my Kaggle notebooks" (12 categories, 1 = EDA → 12 = Generative AI), translated into EDGELOG / Augur engine + Pinscripts for futures (ES/NQ) backtesting.*

**How to read each step:** what the method *is* (plain) → **the actual models/notebooks Carl uses** (numbered, each with a one-line "what it is") → what it *computes* → how it plugs into **EDGELOG** (Augur engine, Pinscripts, the strip backtest, the matrix, folds/gates, the lockbox) → the concrete thing to **build**.

The whole point, repeated at every step: *don't trust the final mean-profit number.* Look at the distribution, prove the edge is real, and make every test reproducible before it touches the lockbox.

---

## 1. EDA — look at the data before you model it
- **Is:** Plot and summarize the raw numbers before drawing any conclusion. Anscombe's quartet is the classic warning — four datasets with identical means/correlations that look completely different once plotted.
- **Carl's notebooks / methods:**
  1. **Anscombe's quartet** — 4 datasets with identical summary stats but wildly different plots; proves you must *plot*, not just summarize.
  2. **dabl EDA (Titanic)** — one-line auto-EDA library that plots a whole dataset for you.
  3. **pandas pivot-table EDA** — slice/aggregate with pivot tables to spot group patterns.
  4. **Pearson / MI / PPS** — three ways to score how strongly two variables relate: linear (Pearson), information-theoretic (Mutual Information), predictive (Predictive Power Score).
  5. **Jane Street: EDA of day 0 + feature importance** — exploring a real quant dataset and ranking features.
  6. **Riiid: EDA + feature importance** — same workflow on a large behavioral dataset.
  7. **Ventilator Pressure: EDA + simple submission** — EDA followed by a baseline model.
- **Computes:** Distribution shape of returns/PNL, median vs mean, quartiles, skew/kurtosis, missing/weird values, and resampling (bootstrap) to ask "if I ran this 500×, what's the *median* outcome?"
- **EDGELOG / Augur:** A Pinscript pre-flight that runs **before the strip backtest**. For any new strategy or dataset it auto-builds: PNL histogram, median & quartiles (not just mean), skew flag, and a bootstrap of trade outcomes. If mean ≫ median, the edge is a few lucky trades — flag it.
- **Build:** `EDA pre-flight` Pinscript → emits charts + an "honest stats" block (median, IQR, skew, bootstrap median win-rate) attached to every backtest report.

## 2. Data Cleaning / Preparation — trust the inputs first
- **Is:** Catch bad/outlier/missing data before it poisons everything downstream.
- **Carl's notebooks / methods:**
  1. **Isolation Forest outlier filtering** — tree-based anomaly detector that "isolates" weird points (bad ticks, fat-finger prints).
  2. **Faker anonymization (Titanic)** — generate fake-but-realistic values to anonymize sensitive data.
  3. **AWS PyDeequ unit tests** — automated data-quality assertions (nulls, ranges, uniqueness, completeness) run like unit tests on big data.
  4. **Naïve Dataset Distillation** — compress a dataset into a tiny synthetic set that still trains an equivalent model.
- **Computes:** Outlier scores on bars/ticks, schema/range/null assertions ("price > 0", "10s bar has OHLC", "volume not null"), duplicate detection.
- **EDGELOG / Augur:** A **data-quality gate** on the 10s OHLC + order-flow import (`EdgeLogOHLCExport.cs`). Directly addresses the known gap where **web/mobile NinjaTrader fills skip the local DB & AddOn** — the gate should detect missing-fill windows and gaps, not silently backtest on holey data. Reconcile against the Position History CSV before a run is allowed to proceed.
- **Build:** `import_quality_gate` Pinscript → PyDeequ-style assertions + Isolation-Forest outlier flag on each import; refuses (or loudly warns) when fills/bars are missing.

## 3. Classification / Regression — learn the signal, don't just hand-code it
- **Is:** Fit a model that maps features → outcome (win/loss, or next-bar move). Carl's notebooks walk the full zoo, simplest → strongest. **~17 models:**
- **Carl's notebooks / methods (the model zoo):**
  1. **Logistic regression** — linear model that outputs a probability; the baseline classifier everything else must beat.
  2. **Generalized Additive Model (GAM)** — sum of smooth per-feature curves; nonlinear but still readable.
  3. **Iterative Dichotomiser 3 (ID3)** — the original decision-tree algorithm, splitting on information gain.
  4. **Decision tree** — learned if/else splits; the building block of every forest.
  5. **Regularized Greedy Forest (RGF)** — builds a forest greedily with regularization; a boosting alternative.
  6. **XGBoost** — gradient-boosted trees; the workhorse and usual winner on tabular data.
  7. **TabNet** — attention-based neural net designed specifically for tabular data.
  8. **Neural networks (Keras)** — standard feed-forward deep net.
  9. **Gaussian process** — non-parametric model that returns a prediction *with* uncertainty built in.
  10. **Hyperparameter grid search** — brute-force search over parameter combos (not a model, the tuning method).
  11. **TensorFlow Decision Forests** — Google's library for random forests / gradient-boosted trees.
  12. **Titanic in pure H2O.ai** — AutoML platform doing classification end-to-end.
  13. **House prices in H2O.ai** — same AutoML, regression flavor.
  14. **XGBTune** — auto-tunes XGBoost hyperparameters so you don't grid-search by hand.
  15. **MNIST with no neural network** — image classification using *classical* ML; proof you don't always need deep nets.
  16. **PyTorch Tabular: Gated Additive Tree Ensemble (GATE)** — neural/tree hybrid for tables.
  17. **TabPFN** — a pretrained transformer that classifies *small* tabular datasets instantly, with **no training step** at all.
- **Computes:** P(win) or expected next-bar move from order-flow + OHLC features, instead of (or alongside) a fixed rule threshold.
- **EDGELOG / Augur:** Add a model-backed signal type to Pinscripts. Start with a **decision tree / XGBoost** on order-flow features (delta, imbalance, OHLC shape) predicting trade win/loss. Keep the rule-based Pinscript as the baseline to beat — never replace until it actually beats it out-of-sample. TabPFN is worth a look for *small* sample setups (rare patterns) since it needs no training.
- **Build:** `model_signal` Pinscript node that loads a trained tree/XGB and outputs P(win) as a gate input. Always logged next to the hand-coded rule's result.

## 4. Conformal Prediction — honest confidence, not point guesses
- **Is:** Wrap any model's output in a *calibrated* interval: "90% of the time the real PNL lands in this band."
- **Carl's notebooks / methods:**
  1. **MAPIE regression intervals** — library that wraps any regressor with statistically valid prediction intervals.
  2. **Quantile Regression Forests** — a forest that predicts quantiles directly, giving you a low/high band.
  3. **Locally-weighted conformal regression** — conformal intervals that widen where the model is less sure.
  4. **Venn-ABERS calibration** — turns raw classifier scores into well-calibrated probabilities (a "70%" really wins ~70%).
- **Computes:** Prediction intervals around per-trade expected PNL, and calibrated win probabilities.
- **EDGELOG / Augur:** Replaces the single expected-value number per fold with a band. A gate becomes "pass only if the *lower* conformal bound on edge > 0," which is far harder to fool than mean PNL.
- **Build:** `conformal_band` step that attaches a calibrated [low, high] PNL interval to each fold and each model signal; feed the lower bound into gate logic.

## 5. Feature Selection / Engineering — keep what matters, kill leakage
- **Is:** Find which inputs actually carry signal and remove the rest; detect train-vs-live drift.
- **Carl's notebooks / methods:**
  1. **LASSO importance** — L1-penalized regression that drives useless features' weights to exactly zero.
  2. **Boruta-SHAP** — all-relevant feature selection using SHAP values vs randomized "shadow" features.
  3. **Recursive Feature Elimination (RFE)** — repeatedly drop the weakest feature and re-fit.
  4. **Permutation importance** — shuffle one feature, measure how much the score drops.
  5. **SHAP permutation explainer + random "probe"** — sanity-check importances against a deliberately random feature.
  6. **Adversarial validation** — train a classifier to tell *train* from *test*; if it can, your distributions differ (leakage/drift).
  7. **t-SNE via RAPIDS cuML** — GPU dimensionality reduction for visualizing feature clusters.
  8. **Synthanic feature engineering: Beware!** — cautionary tale on feature engineering that overfits.
- **Computes:** Ranked feature importances + a drift score telling you whether the backtest period resembles the current regime.
- **EDGELOG / Augur:** Feeds the **matrix** — only promote features/params that rank above noise. Adversarial validation is the early warning that a curve-slice won't generalize to live because the regime shifted.
- **Build:** `feature_rank` Pinscript (PPS/MI + permutation importance over order-flow features) and an `adversarial_validation` check comparing backtest window vs recent live data; surface both in the matrix view.

## 6. Time Series & Forecasting — respect time, no leakage
- **Is:** Methods built for ordered data; and the honest lesson that naive deep nets on price *fail*.
- **Carl's notebooks / methods:**
  1. **Simple moving-average (MA) model** — baseline forecast = recent average.
  2. **Time series decomposition** — split a series into trend + seasonality + residual.
  3. **LSTM sine wave** — RNN learning a clean periodic signal (it *works* here).
  4. **LSTM stock price = FAIL** — the *same* RNN on real prices fails; the cautionary headline.
  5. **Causal Impact (interrupted time series)** — Bayesian structural model for "did this change move the series?"
  6. **Temporal Convolutional Network (Keras-TCN)** — conv net for sequences, an LSTM alternative.
  7. **mplfinance OHLC + volume plotting** — candlestick/volume charts.
  8. **Correlograms of 14 cryptocurrencies** — autocorrelation / cross-correlation visualization.
  9. **Granger causality** — test whether series A helps predict series B.
  10. **Store Sales: day-of-the-week model** — exploit calendar/session effects.
  11. **TPS: simple average (no ML)** — a no-ML baseline that's hard to beat.
  12. **Prophet + holidays + GDP regressor** — Facebook Prophet forecasting with extra regressors.
  13. **Multivariable forecasting: linear tree** — tree with linear leaves for multivariate series.
  14. **Probabilistic forecasting w/ GluonTS (Bitcoin)** — deep model that outputs full forecast distributions.
  15. **Skforecast example** — sklearn-style API for recursive forecasting.
- **Computes:** Forward-only (no peeking) splits, trend/seasonality components, day-of-week effects, lead/lag relationships.
- **EDGELOG / Augur:** Governs how **folds** are cut — strictly chronological, train-before-test, with embargo so a trade near the boundary can't leak. This is the difference between a real walk-forward and an accidentally-shuffled fantasy. Use mplfinance-style OHLC plots in the EDA pre-flight.
- **Build:** Enforce time-ordered, embargoed folds in the engine; add a `walk_forward` mode and a day-of-week / session-effect decomposition to the report.

## 7. Ensemble Methods — combine strategies instead of betting on one ⭐
- **Is:** Blend several models/strategies into one stronger, lower-variance one.
- **Carl's notebooks / methods:**
  1. **Majority voting** — combine classifiers by simple vote (enter only on agreement).
  2. **ML-Ensemble** — library for building layered/stacked ensembles.
  3. **Stacking** — train a meta-model *on top of* base-model predictions.
  4. **Convex Combination of Model Predictions (CCMP) + hillclimbers** — weighted blend of predictions, with weights found by hill-climbing on out-of-sample score.
- **Computes:** A weighted/voted combination whose variance is lower than any single member; weights found by hill-climbing on out-of-sample score.
- **EDGELOG / Augur:** The headline upgrade. Treat each Pinscript strategy (or matrix slice) as an ensemble member and combine them: vote to enter only on agreement, or convex-combine their position sizing by out-of-sample-fitted weights. Exactly what the matrix is positioned to feed.
- **Build:** `ensemble` Pinscript that takes N strategy outputs and produces (a) a voting gate and (b) a hill-climbed convex-combination sizer; weights fit only on validation folds, frozen before the lockbox.

## 8. Explainability — know *why* a fold passed or failed
- **Is:** Open the black box; keep a dead-simple baseline to measure against.
- **Carl's notebooks / methods:**
  1. **VIF / collinearity** — Variance Inflation Factor flags redundant, correlated features.
  2. **KISS small & simple Titanic models** — tiny models that score shockingly well.
  3. **House Prices using only 'OverallQual'** — a *one-feature* baseline that's hard to beat.
  4. **Simple two-variable model** — proof of how much edge sits in just two inputs.
  5. **Titanic explainability: "Why me?"** — per-prediction (local) explanations.
  6. **TabNet interpretability** — read the model's attention masks as feature explanations.
  7. **GPU-accelerated SHAP values** — fast SHAP on large data.
- **Computes:** Per-feature contribution to each decision, redundancy between features, and how a simple model compares to the complex one.
- **EDGELOG / Augur:** When a gate passes, attach "which features drove it." When a fold fails, SHAP tells you whether it's one broken feature or genuine regime change. Always keep a KISS 1–2 rule baseline so you can see how much the fancy model actually adds.
- **Build:** `explain` step → SHAP summary + VIF table per fold; auto-include a KISS baseline strategy in every comparison.

## 9. Causality — is it the rule, or just the regime?
- **Is:** Distinguish "my rule caused the edge" from "the market happened to trend."
- **Carl's notebooks / methods:**
  1. **Causal Forests / Double ML (EconML)** — estimate the treatment effect of a signal, and how it varies across conditions.
  2. **Interrupted time series / Causal Impact** — model the counterfactual: what PNL *would* have happened without the signal.
- **Computes:** Counterfactual equity curve and the estimated causal contribution of the rule itself.
- **EDGELOG / Augur:** Before trusting a matrix slice, test whether the edge survives a counterfactual: did the setup add value, or would buy-and-hold / random-entry over the same window do as well? Guards against curve-fit "edges" that are really just a directional regime.
- **Build:** `causal_check` → Causal Impact on the strategy's equity vs a no-signal counterfactual; report the estimated *causal* contribution per setup.

## 10. Statistics — prove the edge is real, not noise
- **Is:** Classical inference to separate skill from luck.
- **Carl's notebooks / methods:**
  1. **Animated histogram of the Central Limit Theorem** — visual intuition for why averages/bootstraps stabilize.
  2. **Two-sample t-test, p-value & power** — is the difference between two results statistically real, and did you have enough samples to tell?
  3. **VIF / collinearity** — also lives here, as a stats diagnostic.
- **Computes:** Probability the observed edge could arise from luck, and how many trades you'd need for a result to be trustworthy (power).
- **EDGELOG / Augur:** The math under **folds/gates**. A gate shouldn't just check "PNL > 0" — it should check "edge is significant at p < α with adequate power given N trades." Underpins why bootstrap medians (Step 1) beat single means.
- **Build:** `significance` step → t-test / bootstrap p-value + power estimate per fold; expose α and minimum-N as gate parameters.

## 11. Didactic / Sanity Checks — the guardrails for the lockbox
- **Is:** Carl's teaching notebooks on the traps that wreck backtests.
- **Carl's notebooks / methods:**
  1. **Beautiful math in your notebook** — LaTeX/formatting (presentation, not a method).
  2. **Titanic: In all the confusion...** — reading a confusion matrix properly.
  3. **How imbalanced is "imbalanced"?** — class-imbalance handling (few winners vs many losers).
  4. **Overfitting and underfitting the Titanic** — the train-vs-validation gap, made visible.
  5. **False positives, false negatives & the discrimination threshold** — tune the entry threshold on the FP/FN trade-off, not a round number.
  6. **Introduction to the Regularized Greedy Forest** — didactic walk-through of RGF.
  7. **Extrapolation: Do not stray out of the forest!** — trees can't extrapolate beyond training range; live inputs outside it are dangerous.
  8. **Some sex, a bit of class, and a tree** — a simple, readable Titanic decision tree.
  9. **The Lehmer RNG (seed=42)** — reproducibility and why the random seed matters.
- **Computes:** Train-vs-validation gap (overfit detector), class balance, the entry-threshold trade-off curve, and out-of-range input warnings.
- **EDGELOG / Augur:** The pre-lockbox guardrails. Before a strip backtest becomes authoritative: check overfit gap, fix the random seed for reproducibility, warn when live inputs fall outside the backtested range (extrapolation), and tune the entry threshold on the FP/FN curve.
- **Build:** `sanity_panel` → overfit gap, fixed-seed reproducibility stamp, extrapolation/out-of-range flag, and a threshold-tuning curve; required to pass before a result is written to the lockbox.

## 12. Generative AI — synthetic data + an LLM co-pilot
- **Is:** Generate new data or text.
- **Carl's notebooks / methods:**
  1. **StableDiffusion: text-to-image with KerasCV** — generate images from a prompt (the generative-model mechanics).
  2. **[Gemma] I am replacing myself with an LLM** — using a local LLM to do the analyst's reading/writing work.
- **Computes:** For tabular trading the useful forms are synthetic-scenario generation (augment thin samples, stress-test rare regimes) and an LLM that reads/writes for you.
- **EDGELOG / Augur:** Two practical uses — (1) generate synthetic stress scenarios (gaps, halts, low-liquidity sessions) to test a strategy where history is thin; (2) an LLM assistant that reads EDGELOG reports/matrix output in plain English and drafts Pinscripts from a description. Keep synthetic data clearly tagged and never let it leak into the authoritative lockbox backtest.
- **Build:** `scenario_gen` (synthetic stress paths, tagged non-authoritative) + an LLM report-reader / Pinscript-drafter assistant.

---

## Suggested build order for EDGELOG
1. **Steps 1–2 first** (EDA pre-flight + import quality gate) — they protect everything else and directly fix the web/mobile-fills-miss-local gap.
2. **Steps 5, 6, 10** (feature ranking, time-ordered folds, significance) — make the existing folds/gates honest.
3. **Step 7** (ensemble of strategies) — the biggest edge upgrade, once the matrix feeds it clean members.
4. **Steps 3–4, 8–9** (models, conformal bands, explainability, causality) — layer learned signals on top with calibration and proof.
5. **Steps 11–12** (sanity guardrails, generative) — lockbox guardrails and the co-pilot/scenario tooling last.

*Mapping source: Carl McBride Ellis's 12-category Kaggle notebook index (notebook titles reproduced per category). EDGELOG translation by Claude, matching the Augur/Pinscripts framing from the Grok thread.*
