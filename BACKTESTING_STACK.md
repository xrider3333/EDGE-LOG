# EDGELOG — Backtesting Stack (running status library)

**Single source of truth for where the backtesting engine stands.** Update this
whenever a method or strategy changes status, a run matters, or a decision is made.

- **Last updated:** 2026-07-04
- **Web VERSION:** 44.0 · **Stack board (`method_stack.html`):** v2.9
- **Board tally:** most method pills LIVE; 7 still planned (see §7)

> **Plain-language rule** (owner preference): every technical term is defined in
> EDGELOG terms the first time it appears. Don't assume the reader knows the jargon.

**Glossary of the words used most below**
- **Strategy** — the trading rules being tuned (e.g. ORB, ENGU). The "knobs".
- **Gate / ML gate** — a *second* model (the "bouncer") that scores each trade the
  strategy fires and skips the low-confidence ones. It never changes the strategy;
  it only filters. Also called *meta-labeling*.
- **Ungated** — the raw strategy, every signal taken, no gate.
- **Pill** — one box on the stack board (`method_stack.html`). **LIVE** = built,
  **PLANNED** = on the board but not built yet.
- **Lockbox** — the most recent slice of history that is sealed off before testing,
  looked at exactly once, to check a result wasn't just curve-fit.
- **Recovery factor** — profit ÷ drawdown. The fair way to compare a gate to ungated
  (a gate trades less, so raw dollars unfairly favor ungated).
- **Walk-forward (WF)** — tune on a past window, test on the next unseen window, roll
  forward. **DOF** = degrees of freedom (how many knobs; fewer = harder to overfit).

---

## 1. The Stack Board — 8 native sections

The board (`method_stack.html`) is organized on EDGELOG's own pipeline, not Carl's
numbering. Each pill still carries its old Carl section as a `· was §X.Y` tag.

| § | Section | Pills (✅ LIVE / ⏳ PLANNED) |
|---|---|---|
| 1 | **Data health & EDA** — know your input | ✅ gap-check (1.5× bar; ETH/sub-1m ≥2h) · ✅ Isolation-Forest outliers · ✅ coverage map · ✅ roll-seam check · ✅ EDA pre-flight (`_profiles/*.html` return-dist) · ⏳ fills reconciliation |
| 2 | **Feature screen** — which inputs matter | ✅ Pearson r · ✅ Mutual Information · ✅ PPS (predictive power score) |
| 3 | **Model & Search** — make + tune the signal | **3A Models:** ✅ Logistic · ✅ Random Forest · ✅ XGBoost gate  **3B Search:** ✅ grid sweep · ✅ Bayesian search  **3C Pick-winner:** ✅ PDP plateau (GAM) · ✅ neighborhood/plateau · ✅ highest-PnL (argmax)  **3D AI assist:** ✅ AI-evolve (Claude in the loop) |
| 4 | **Validation** — rigor | ✅ walk-forward · ✅ stress windows · ✅ lockbox one-shot · ✅ cross-instrument transfer · ✅ Deflated Sharpe · ✅ Monte-Carlo · ✅ sample adequacy (DOF) · ✅ ML-gate validate · ⏳ conformal band · ⏳ adversarial validation |
| 5 | **Explain** — where the edge lives | ✅ regime report card · ✅ MAE/MFE (heat/reach) · ⏳ SHAP |
| 6 | **Ensemble** | ⏳ ensemble top-K |
| 7 | **Causality** | ⏳ causal check |
| 8 | **Generative** | ⏳ synthetic scenarios |

---

## 2. Carl McBride Ellis notebooks → EDGELOG mapping

Source page the links came from: [A selection of my Kaggle notebooks](https://www.kaggle.com/code/carlmcbrideellis/a-selection-of-my-kaggle-notebooks).
Legend: ✅ built · ⏳ planned · ❌ not adopted (used a different method) · 🔖 reference.

### ✅ Built (LIVE)
| Carl notebook | Method | Carl § | EDGELOG pill |
|---|---|---|---|
| [Pearson, MI & predictive power](https://www.kaggle.com/code/carlmcbrideellis/pearson-mutual-information-and-predictive-power) | 3 feature scores | §5.1–5.3 | Pearson r · Mutual Information · PPS (§2) — 1:1 |
| [Mutual Information (Holbrook, ref)](https://www.kaggle.com/code/ryanholbrook/mutual-information) | MI tutorial | §5.2 | Mutual Information |
| [Isolation Forest outliers](https://www.kaggle.com/code/carlmcbrideellis/filtering-outliers-using-the-isolation-forest) | outlier flagging | §2.3 | Isolation Forest outliers (§1) — 1:1 |
| [EDA in one line (pandas-profiling)](https://www.kaggle.com/code/carlmcbrideellis/titanic-eda-in-one-line-with-pandas-profiling) | auto-EDA | §1.1 | EDA pre-flight |
| [Beginners EDA using dabl](https://www.kaggle.com/code/carlmcbrideellis/absolute-beginners-titanic-eda-using-dabl) | auto-EDA | §1.1 | EDA pre-flight (same slot) |
| [EDA with pivot tables](https://www.kaggle.com/code/carlmcbrideellis/exploratory-data-analysis-using-pandas-pivot-table) | EDA | §1.1 | EDA pre-flight (same slot) |
| [Missing values with missingno](https://www.kaggle.com/code/carlmcbrideellis/titanic-view-missing-values-with-missingno) | missing-data view | §2.4 | coverage map / gap-check (§1) |
| [pydeequ data-quality tests](https://www.kaggle.com/code/carlmcbrideellis/aws-pydeequ-unit-tests-to-measure-data-quality) | data-quality unit tests | §2.1 | gap-check (`data_quality.py`) |
| [Classification using GAMs](https://www.kaggle.com/code/carlmcbrideellis/classification-using-generalized-additive-models) | GAM smoothing | §5.4 | PDP plateau (GAM) — *used as the plateau **selector**, not a standalone classifier gate* |

### ⏳ On the board, not built yet
| Carl notebook | Method | Carl § | Planned pill |
|---|---|---|---|
| [SHAP explainability](https://www.kaggle.com/code/carlmcbrideellis/titanic-explainability-why-me-asks-miss-doyle) | per-trade feature attribution | §8.3 | SHAP (§5) — **highest-value next gap** |
| [Self-made ensemble methods](https://www.kaggle.com/code/caerno/eda-self-made-ensemble-methods) | blend top models | §7.1 | ensemble top-K (§6) |
| [Naïve dataset distillation](https://www.kaggle.com/code/carlmcbrideellis/ps-s3-e21-na-ve-dataset-distillation) | shrink/synthesize data | §12 | synthetic scenarios (§8) |
| [Data anonymization with Faker](https://www.kaggle.com/code/carlmcbrideellis/data-anonymization-using-faker-titanic-example) | synthetic data | §12 | synthetic scenarios (§8, same slot) |

### ❌ Not adopted — different method on purpose
| Carl notebook | Why not | We use instead |
|---|---|---|
| [Outliers via inverse-PCA](https://www.kaggle.com/code/carlmcbrideellis/filtering-outliers-using-inverse-pca) | one outlier tool is enough | Isolation Forest |
| [A bit of class and a tree](https://www.kaggle.com/code/carlmcbrideellis/titanic-some-sex-a-bit-of-class-and-a-tree) | single tree overfits | Random Forest gate |
| [ID3 decision tree](https://www.kaggle.com/code/carlmcbrideellis/titanic-using-the-iterative-dichotomiser-3-id3) | teaching algo, not deployable | Random Forest / XGBoost gate |

### 🔖 Index / reference (not methods)
[A selection of my Kaggle notebooks](https://www.kaggle.com/code/carlmcbrideellis/a-selection-of-my-kaggle-notebooks#--7.-ensemble-methods-) (the source page) ·
[carlmcbrideellis/code](https://www.kaggle.com/carlmcbrideellis/code) ·
[/notebooks](https://www.kaggle.com/carlmcbrideellis/notebooks) ·
[GitHub mirror](https://github.com/Carl-McBride-Ellis/My-kaggle-notebooks) ·
LinkedIn: [ensembling guide](https://www.linkedin.com/posts/carl-mcbride-ellis_kaggle-ensembling-guide-activity-7041377476710653952-iEGp) · [ML regression](https://www.linkedin.com/posts/carl-mcbride-ellis_kaggle-machinelearning-regression-activity-7155071941773516800-qsn8) · [competitions](https://www.linkedin.com/posts/carl-mcbride-ellis_kaggle-competitions-activity-6989874021894885376-s2zX)

**Score:** 9 methods live · 4 planned · 3 skipped on purpose.

---

## 3. Strategy library

Library #s come from `augur_config.json` → `strat_nums`. Validation verdicts are
from the 2026-06-20 auto-screen (`_augur_screen_results.md`) unless noted. *Caveat:
that screen tested many strategies at once (multiple testing) — a PASS there still
deserves a fresh single-strategy re-validation before trust.*

### ORB family (Opening Range Breakout) — the clarified lineage
1.0 → 2.0 → 3.0. They are **three distinct strategies**, not versions of one config.

| # | Strategy | What it is | Status |
|---|---|---|---|
| 20 | **ORB 3.0** · low-DOF deployable *(formerly "ORB SIMPLE")* | breakout of the opening range, stripped to **5 knobs** (no ATR/partials/trail) | ✅ **Strongest validated asset.** Auto-Validate 6yr PASS 6/6 (+$85.7k lockbox); XL 16yr PASS 6/6, WFE 176% (+$156.8k lockbox), DSR ~100%. Needs **no gate**. |
| 18 | ORB 2.0 · trail + ATR stop + vol filter | the complex ORB (ATR-normalized stop, partial exits, trailing) | ⚠️ WEAK on screen — the extra knobs didn't earn their keep |
| 19 | ORB 1.0 · open-momentum | the earliest, looser ORB | ⚠️ WEAK raw; became viable **only with the Random-Forest ML gate on 16yr** (see §4) |

**ORB 3.0 forward-test pick = run 119** (see §5): robust, tiny drawdown, sits on the
plateau (stop 0.75). Run 121 makes more money but rides a few big winners = riskier.

**Scale-out finding** (earlier session; that config was informally called "ORB 3.1" —
it's ORB 3.0 with partial exits + a trailing stop bolted on): the partial+trail version
passes WF and the lockbox, **but the scale-out only makes the curve *smoother* (better
risk-adjusted), not *richer***. On the safe **0.75 stop**, single-lot **ride-to-close**
is the PnL champ. Run 121's headline came partly from an **inflated 0.25 stop** — treat
its raw dollars with caution. Net: deploy the simple single-lot ORB 3.0; add scale-out
only if you specifically want a smoother equity curve, not more money.

### Other strategies
| # | Strategy | Type | Status (2026-06-20 screen) |
|---|---|---|---|
| 1–4, 9–12 | ENGU 1.1.20 / 1.1.21 / 1.2.1 / 1.3.1–1.3.5 | engulfing reversal | mostly WEAK/FAIL; 1.3.4 the least-bad (WEAK) |
| 5–7 | REVERT 1.0 / 1.1 / 1.2 | mean reversion | FAIL |
| 8, 16 | VWAP FADE 1.0 / 2.0 | fade stretch from VWAP | FAIL / weak |
| 14, 15 | SUPERTREND 1.0 / 2.0 | ATR trend-follow | not strongly validated |
| 17 | OVERNIGHT HOLD 1.0 | close→open risk premium | FAIL |
| 13 | GAINZ RF 1.0 | random-forest signal strategy *(a strategy, not a gate)* | in library; not a validated deploy candidate |

---

## 4. ML gate (meta-labeling) — how it works + what we learned

**Engine:** `augur_engine/ml_gate.py`. **Board:** §3A (models) + §4 "ML-gate validate".

### How the honest test works (`gate_validate`, board 4.10)
The comparison is **always gate vs. ungated** (same trades, filter on/off), scored by
**recovery factor**. Never compared to a different strategy.
1. **PICK (in-sample):** seal the last 12 months. On the rest, try 9 gates (3 models ×
   3 cut-offs), keep the best by recovery factor. If none beats ungated → stop.
2. **CHECK:** the chosen gate must beat ungated in each of 4 time windows.
3. **LOCKBOX (one look):** the winner — only the winner — is tested once on the sealed
   12 months. `HELD` (green light) or `FAILED`. **This**, not the in-sample slice, is
   what decides "proceed." The lockbox is still historical, so HELD earns a *real*
   forward test — it is not itself the forward test.

Leakage-safe by construction: the gate only ever trains on trades that finished before
each new trade; 30-trade warm-up ungated; refit every 25; samples weighted by |PnL| so
cut-off 50% ≈ positive expectancy (matters for low-win-rate strategies).

### Key finding: gates barely help ORB
- **ORB 3.0 (strong):** never needed a gate — passes clean ungated.
- **ORB 1.0 (weak) on 6yr / 4.5yr:** no gate earned its keep.
- **ORB 1.0 (weak) on full 16yr:** the **Random Forest gate @ 50% DID earn its keep** —
  beat ungated pre-lockbox, held 4/4 windows, held the lockbox (recovery 16.66 vs 6.77).
  The flip came from **data volume** (owner's "use the whole CSV" instinct).

**Why gates struggle on ORB:** ORB is already a picky, rule-filtered strategy (little
junk left to prune), and its profit lives in unpredictable post-entry trend follow-through
that entry-bar features can't see. A strategy a gate *can't* improve is a good sign — it
means its trades are all roughly equally worth taking. Meta-labeling pays off on messy,
over-firing strategies, not clean ones like ORB 3.0.

The single-run gate PFs (log 1.20 / RF 1.21 / XGB 1.43) were **hindsight** — whole-window
scores with no held-out test; not tradeable numbers.

---

## 5. Notable runs (from `optimizer_history.db`)

ORB family walk-forward, 16yr (2010-06 → 2026-06), NQ/ES 5m RTH. `#` = real run id.

| # | Inst | Config | PF | Win | Trades | Net | Max DD | Read |
|---|---|---|---|---|---|---|---|---|
| **119** ⭐ | NQ | stop 0.75, target 4.5R | 1.69 | 39% | 2,242 | +$133.6k | **−$5.8k** | **robust — forward-test pick** |
| 120 | ES | stop 0.25, target 6R | 2.51 | 39% | 3,798 | +$314.3k | −$4.0k | strong ES |
| 121 | NQ | stop 0.25, no target | 2.50 | **20%** | 3,801 | +$614.9k | −$10.0k | big-winner — biggest $, riskier |
| 122 | NQ | stop 2.0 | 1.34 | 51% | 3,765 | +$517.9k | **−$62.7k** | drawdown too deep |
| 123 | ES | or 4, stop 0.75 | 1.41 | 43% | 3,733 | +$273.7k | −$18.4k | — |
| 124 | ES | Short sweep | 1.35 | 45% | 3,857 | +$251.3k | −$16.1k | — |

*Yesterday's gate/validate experiments ran as engine jobs (task outputs + Firestore),
not saved to the runs DB — so they carry no run id.*

---

## 6. Engine / file map

- `augur_engine/ml_gate.py` — the ML gate + `gate_validate` (meta-labeling).
- `augur_engine/analytics.py` — `pdp_plateau` (GAM-style broad-high-ground selector).
- `augur_engine/engine.py` — `run_backtest` (ml_filter/ml_threshold kwargs), `run_gate_validate`.
- `augur_engine/optimize.py` + `auto.py` — wire `plateau_pick` alongside argmax `best`.
- `augur_engine/data_quality.py` — gap/coverage/data-health checks (§1).
- `augur_strategies/ORB_3_0.py` — the deployable ORB (formerly ORB_SIMPLE_1_0.py).
- `method_stack.html` — the stack board (the visual of this doc).
- `index.html` — the deployed web app; `const VERSION` = deploy version.
- Deploy = push to `main` (GitHub Pages, ~10 min CDN). Runner executes queued jobs.

---

## 7. Open items / next up

Planned pills, best-value first:
1. **SHAP** (§5) — show *which entry features* the ML gate uses to skip trades. Natural
   follow-up to the gate work; turns the gate from a black box into an explanation.
2. **ensemble top-K** (§6) — blend the top configs instead of crowning one.
3. **conformal band** / **adversarial validation** (§4) — extra validation rigor.
4. **synthetic scenarios** (§8) — dataset distillation / synthetic stress data.
5. **causal check** (§7).
6. **fills reconciliation** (§1) — reconcile web/mobile NinjaTrader fills that skip the
   local DB.

---

## Changelog
- **2026-07-04** — Created this doc. Renamed ORB SIMPLE → **ORB 3.0** across engine +
  site (web VERSION 44.0). Confirmed ORB 3.0 is the strongest validated asset and needs
  no gate; documented the 16yr RF-gate flip on ORB 1.0. Mapped all Carl McBride Ellis
  notebooks to board status (9 live / 4 planned / 3 skipped).

> **How to keep this current:** update the relevant section + the changelog whenever a
> pill flips LIVE, a strategy changes verdict, a notable run lands, or a decision is made.
