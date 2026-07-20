# Surrogate-Model Param Discovery (#31) — design proposal

**Status:** P1 (read-out bake-off) SHIPPED 2026-07-18 (`augur_engine/surrogate.py`, 2L panel;
5 models incl. pyGAM since #35). P2 (steering) SHIPPED 2026-07-19 behind the off-by-default
`auto_steer` flag (#36): `propose_candidates` (GP + Upper-Confidence-Bound over a legal-grid
candidate pool) + the seed→steer loop in `run_auto`. Acceptance A/B (TTIBS NQ, 150 trials,
seed 42, lockbox held out): random best IS 19,738 pts (found at trial 28, then flat) vs
steered 21,440 pts (+8.6%, still improving at trial 107); 0 GP-fit fallbacks. Second-family
A/B (ORB 3.1, 12 knobs, intraday 5m — as different a surface as the book owns) PASSED the
same day: random 14,418 pts vs steered 24,002 pts (+66%) at equal budget/seed, 0 fallbacks.
2-for-2 → steering is ON for Auto-Validate (validate.py Stage A passes auto_steer=True);
run_auto's own default stays False. P3 (interaction-aware expansion) still open.

**Plain-language rule:** every term is defined on first use.

---

## 1. The problem it solves

Today's param discovery (Auto-Optimize / Auto-Validate) is:
- **Random search** — the sampler is `_RandomSampler` (seed 42); optuna is absent, so
  "Bayesian" falls back to plain random. It samples configs blindly.
- **1-D additive plateau** — `pdp_plateau` reads each param's effect *independently*
  (`score = mean + Σ per-param smoothed 1-D curve`), computed **directly from the raw
  sampled points** with no model in between.

Two consequences:
1. **No interactions.** An additive 1-D model *cannot* represent "widening `ibs_entry`
   unlocks a higher peak in `hold_cap`." #30 (iterative expansion) catches *marginal*
   shifts by re-checking, but still can't model a true joint surface.
2. **Blind sampling.** Random search wastes trials in bad regions; it never learns the
   shape and aims the next samples at promising ones.

A **surrogate model** fixes both. *Surrogate* = a fast model that learns
`params → PnL` from the sampled configs, so you can (a) read the *joint* surface
(interactions), (b) find the predicted joint optimum, and (c) aim the next samples where
the model predicts high PnL. This is standard "surrogate-based / Bayesian optimization."

**Key relationship (the owner's question):** a **2-way PDP** is *not* a model — it is a
*diagnostic read off a fitted model*. XGBoost / Gaussian-Process / GAM-with-interactions
are the **models** that learn the surface; the 2-way PDP is what you **read** from
whichever model you fit. So they are two layers, not alternatives:

| Layer | Job | Options |
|---|---|---|
| **Model** | learn `params → PnL` incl. interactions | GAM-interactions · Random Forest · XGBoost · Gaussian Process · quadratic response-surface (baseline) |
| **Read-out** | inspect / exploit the fitted surface | 2-way PDP · joint-optimum · interaction strength (Friedman H-statistic) · acquisition (where to sample next) |

---

## 2. Pipeline

All of this runs **IN-SAMPLE ONLY** — the lockbox is never loaded. The output is a
proposed champion that STILL must pass the OOS/lockbox gate before deploy. Discovery
maximizes IS on purpose; the lockbox is the separate deploy filter.

```
1. SEED      random-sample the param space (reuse today's search) → points {params → real PnL}
2. BAKE-OFF  fit N surrogate models to the points; cross-validate each (below)
3. PICK      rank surrogates by out-of-fold accuracy; choose best (or consensus)
4. READ      from the chosen model: joint optimum, 2-way PDPs, interaction strengths
5. STEER     sample the next batch where the model predicts high PnL (acquisition)
6. GROUND-TRUTH  actually RUN the model's proposed optimum (real backtest) — never trust
             the prediction alone; add the result back into the points
7. REPEAT    2-6 until the proposed optimum stops improving (or a trial budget)
8. REPORT    per-surrogate cards (§4) + the ground-truthed champion → into the run report
```

Steps 1 and 6 are the only places a **real backtest** runs; 2-5 are cheap model math.

---

## 3. The surrogate bake-off (the owner's "run several, pick the best")

Fit these to the same points (roster is configurable; start with 3-4):

| Model | Strength | Weakness | Dep |
|---|---|---|---|
| **Quadratic response surface** | trivial, interpretable baseline; smooth interactions | low capacity (only 2nd-order) | numpy (none) |
| **GAM + interaction terms** | smooth, interpretable, honest about shape | limited interaction capacity | pyGAM (new) or hand-rolled tensor-product |
| **Random Forest** | captures interactions, robust, no tuning, handles sparse grids | stair-step surface, weak extrapolation | sklearn (have) |
| **XGBoost** | strong interactions, high accuracy | overfits sparse data → hallucinated peaks | xgboost (have — used by the gate) |
| **Gaussian Process** | best for steering — gives an *uncertainty* estimate per point | O(n³); fine at ≤~1000 configs | sklearn (have) |

**Scoring / picking (objective, not vibes):** k-fold cross-validation — hold out a slice
of the sampled configs, fit on the rest, measure how well the model predicts the held-out
configs' PnL (R² or RMSE). The model with the best out-of-fold accuracy is the most
trustworthy map of the surface; use it to pick the optimum + steer. **Consensus check:**
if the diverse models agree on the optimum region → high confidence; if they diverge →
the surface is noisy/under-sampled → widen sampling before trusting any single pick.

**Same XGBoost as the gate — different target.** We already run XGBoost for the trade
gate (`trade features → win/loss`). Here it learns `params → run-PnL`. Same algorithm,
different label. No new capability, just a second use.

---

## 4. What each surrogate reports (transparency + learning)

For every model in the bake-off, the run report shows a card:
- **CV accuracy** (R² / RMSE) — how well it maps the surface.
- **Its predicted-best config** AND **that config's real PnL when actually run** (the
  honesty column — prediction vs reality).
- **Its top interactions** — which param *pairs* matter (Friedman H-statistic and/or the
  strongest 2-way PDP), e.g. "ibs_entry × hold_cap = strong."
- **Agreement flag** — does this model's optimum region match the others?

Example row you'd read: `GAM   R²0.71  best ibs0.45/hold12  ran +$310k  |  XGB  R²0.66
best ibs0.50/hold18  ran +$284k  |  GP  R²0.74  best ibs0.45/hold12  ran +$312k, HIGH
uncertainty past ibs0.45`. You *see* the models differ — GAM smooth, XGBoost sharper/more
aggressive, GP flags where it doesn't trust itself.

---

## 5. Steering (acquisition) — why it beats random

The Gaussian Process (or any model + an uncertainty proxy) supports an **acquisition
function**: sample next where *predicted PnL is high* OR *the model is most uncertain*
(explore vs exploit). That turns blind random search into a search that *learns the shape
and aims* — the actual meaning of "Bayesian optimization" that the current code only
stubs. Effect: far fewer real backtests to find the true joint optimum.

---

## 6. The non-negotiable guardrails

- **IS-only.** Every step above runs on the in-sample window. The lockbox is never touched
  by discovery. (The owner's clarified point: discovery maximizes IS; the lockbox is the
  separate deploy gate.)
- **Surrogate-overfitting is the real risk.** With only a few hundred configs over ~5-9
  params, a flexible model (XGBoost) can hallucinate a peak that isn't there. Two defenses:
  (a) CV-scoring picks the model that *generalizes*, not the one that memorizes; (b) every
  proposed optimum is **ground-truthed by a real backtest** — the model never gets to
  "win" on a prediction alone.
- **Still faces the lockbox.** A better IS optimum is still just an IS optimum. It deploys
  only if it clears the sealed year. Smarter discovery finds the true peak *faster*; it
  does not lower the deploy bar.
- **hard_min/hard_max bound the steering** (#29) so acquisition can't chase the surface
  into an impossible/degenerate region (e.g. IBS > 1, or ibs_entry > 0.5 which is a
  different strategy).

---

## 7. Build phases (proposed)

- **P1 — read-out only (no steering):** after the existing random search, fit the bake-off,
  CV-score, show the per-surrogate cards + the best model's joint optimum + 2-way PDPs, and
  ground-truth the top pick. Low risk, high learning value, reuses existing points. *Ships
  the 2-D read-out + the model comparison the owner wants.*
- **P2 — steering:** add the GP/acquisition loop so sampling is model-guided, not random.
  Bigger; changes the search loop. Gated behind a flag; `auto_expand`/random stays default
  until proven.
- **P3 — integrate with #30:** let the surrogate's interaction map inform which knobs the
  iterative expander widens (interaction-aware expansion).

Recommend building **P1 first** (safe, reuses everything, delivers the multi-surrogate
comparison + 2-way interactions) and reviewing before P2/P3.

---

## 8. Open decisions for the owner

1. Roster for v1 — start with {quadratic, RandomForest, XGBoost, GP}? (GAM-interactions
   needs pyGAM or a hand-rolled tensor spline — add later.)
2. New dep tolerance — pyGAM (yes/no). Everything else uses deps we already have.
3. P1-only for now, or authorize P2 (steering) in the same build?
