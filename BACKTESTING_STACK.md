# EDGELOG — Backtesting Stack (running status library)

**Single source of truth for where the backtesting engine stands.** Update this
whenever a method or strategy changes status, a run matters, or a decision is made.

- **Last updated:** 2026-07-04
- **Web VERSION:** 45.7 · **Stack board (`method_stack.html`):** v4.1
- **Board tally:** 45 method pills LIVE; 1 planned — operational fills reconciliation (see §7). **Every no-dep Carl method is built** (all icon-tagged).

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
| 4 | **Validation** — rigor | ✅ walk-forward · ✅ stress windows · ✅ lockbox one-shot · ✅ cross-instrument transfer · ✅ Deflated Sharpe · ✅ Monte-Carlo · ✅ sample adequacy (DOF) · ✅ ML-gate validate · ✅ adversarial validation · ✅ conformal band |
| 5 | **Explain** — where the edge lives | ✅ regime report card · ✅ MAE/MFE (heat/reach) · ✅ SHAP (gate feature attribution) |
| 6 | **Ensemble** | ✅ ensemble top-K (blend of top configs vs single best) |
| 7 | **Causality** | ✅ causal check (random-entry randomization test) |
| 8 | **Generative** | ✅ synthetic scenarios (trading-day bootstrap) |

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
| [SHAP explainability](https://www.kaggle.com/code/carlmcbrideellis/titanic-explainability-why-me-asks-miss-doyle) | feature attribution for the gate | §8.3 | SHAP (§5) — real TreeSHAP for tree gates (shap 0.52), permutation fallback; on the gate card |
| [Self-made ensemble methods](https://www.kaggle.com/code/caerno/eda-self-made-ensemble-methods) | blend top models | §7.1 | ensemble top-K (§6) — equal-weight blend of top-K vs single best, auto on grid sweeps |

### ⏳ On the board, not built yet
*(none — every Carl notebook the owner sent is now built or superseded.)*

### ❌ Not adopted — different method on purpose
| Carl notebook | Why not | We use instead |
|---|---|---|
| [Outliers via inverse-PCA](https://www.kaggle.com/code/carlmcbrideellis/filtering-outliers-using-inverse-pca) | one outlier tool is enough | Isolation Forest |
| [A bit of class and a tree](https://www.kaggle.com/code/carlmcbrideellis/titanic-some-sex-a-bit-of-class-and-a-tree) | single tree overfits | Random Forest gate |
| [ID3 decision tree](https://www.kaggle.com/code/carlmcbrideellis/titanic-using-the-iterative-dichotomiser-3-id3) | teaching algo, not deployable | Random Forest / XGBoost gate |
| [Naïve dataset distillation](https://www.kaggle.com/code/carlmcbrideellis/ps-s3-e21-na-ve-dataset-distillation) | distillation doesn't apply to price backtesting | §8 built as a trading-day bootstrap instead |
| [Data anonymization with Faker](https://www.kaggle.com/code/carlmcbrideellis/data-anonymization-using-faker-titanic-example) | no need to anonymize your own OHLC | (same — day bootstrap fills the §8 slot) |

### 🔖 Index / reference (not methods)
[A selection of my Kaggle notebooks](https://www.kaggle.com/code/carlmcbrideellis/a-selection-of-my-kaggle-notebooks#--7.-ensemble-methods-) (the source page) ·
[carlmcbrideellis/code](https://www.kaggle.com/carlmcbrideellis/code) ·
[/notebooks](https://www.kaggle.com/carlmcbrideellis/notebooks) ·
[GitHub mirror](https://github.com/Carl-McBride-Ellis/My-kaggle-notebooks) ·
LinkedIn: [ensembling guide](https://www.linkedin.com/posts/carl-mcbride-ellis_kaggle-ensembling-guide-activity-7041377476710653952-iEGp) · [ML regression](https://www.linkedin.com/posts/carl-mcbride-ellis_kaggle-machinelearning-regression-activity-7155071941773516800-qsn8) · [competitions](https://www.linkedin.com/posts/carl-mcbride-ellis_kaggle-competitions-activity-6989874021894885376-s2zX)

**Score (the sub-links originally sent):** 11 methods live · 5 skipped/superseded.

### Full master-notebook coverage — all 14 sections
The [master notebook](https://www.kaggle.com/code/carlmcbrideellis/a-selection-of-my-kaggle-notebooks)'s
table of contents has **14 sections** — far more than the sub-links first sent. Assessment:

| Carl master § | Topic | EDGELOG status |
|---|---|---|
| 1 | EDA | ✅ EDA pre-flight · Pearson/MI/PPS · ✅ **return tail-fit** (Student-t) · ✅ **seasonality** |
| 2 | Data cleaning | ✅ Isolation-Forest outliers · PyDeequ (gap-check). Distillation/anonymization skipped (n/a to price) |
| 3 | Classification / Regression | ✅ Logistic · RF · XGBoost gates · GAM (plateau). NN/TabNet/GP/RGF **deferred** (heavy deps, little over XGBoost) |
| 4 | Conformal prediction | ✅ conformal PnL band · ✅ **gate calibration** (reliability + ECE + isotonic headroom, on the gate card) |
| 5 | Feature selection / eng | ✅ MI/PPS screen · adversarial validation · SHAP · ✅ **feature selection (RFE-CV)** |
| 6 | Time series / forecasting | ~ regime + time features · ✅ **lead-lag/Granger** · ✅ **serial-dependence (ACF)** · ✅ **seasonality**. Direct forecasting (LSTM/Prophet/GluonTS) deferred — heavy-dep + low-success (Carl's own "LSTM = FAIL"), **not** *inapplicable* |
| 7 | Ensemble | ✅ ensemble top-K · ✅ **stacking/CCMP** |
| 8 | Explainability | ✅ SHAP · regime report card · ✅ **VIF/collinearity** |
| 9 | Causality | ✅ causal check (randomization). Double-ML / Causal Forests **deferred** (EconML dep) |
| 10 | Statistics | ✅ Deflated Sharpe · ✅ **edge significance** (t-test + bootstrap CI on mean PnL) |
| 11 | Didactic | mostly n/a (teaching); but ✅ **gate discrimination** (ROC / confusion / discrimination threshold) built from here |
| 12 | Generative AI | ~ AI-evolve (Claude). StableDiffusion/Gemma **n/a** to trading |
| 13 | Miscellaneous | mostly n/a; finance notebooks (returns Normal-vs-Cauchy) ✅ built as **return tail-fit** (§1) |
| 14 | Meta-Kaggle | n/a |

**6 NEW planned pills added from these passes** (board v3.5): gate calibration (§3A) · feature selection (§2) · VIF/collinearity (§2) · stacking/CCMP (§6) · lead-lag/Granger (§7) · serial-dependence ACF (§1).

**"Deferred" ≠ "inapplicable" — three honest buckets:**
- **Needs a heavy dependency** (applicable, buildable *if you approve the dep*): neural-net /
  TabNet gate models (torch), Double-ML / Causal Forests (EconML). Payoff is small — boosted
  trees already match/beat NNs on ~9 features + a few-thousand trades.
- **Different paradigm, known-low-success:** direct price/return forecasting (LSTM / Prophet /
  GluonTS / TCN). EDGELOG *can* host a forecast strategy (GAINZ_RF already is one), but Carl's
  own notebook is titled "LSTM + stock-price prediction = FAIL" — low expected value.
- **Genuinely not applicable:** generative image/LLM (StableDiffusion/Gemma), meta-Kaggle
  stats, geospatial, Titanic didactics — these truly don't map to a futures backtester.

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
| new | **ORB 3.1** · low-DOF + scale-out *(`ORB_3_1.py`)* | ORB 3.0 base + optional partial + **bar-trailing stop** | ✅ **Current deployable** at `p0/trail5` (single-lot ride + 5-bar trail). Run #125. WF + lockbox + ES transfer all PASS. See [`ORB.md`](ORB.md). |
| new | ORB 3.2 · trail research *(`ORB_3_2.py`)* | 3.1 + chandelier/activate/breakeven levers | 🔬 research only — the smarter trails overfit / don't beat the simple bar-trail (invariant-verified == 3.1 when off) |
| new | ORB 3.3 · time-structure research *(`ORB_3_3.py`)* | 3.1 + entry-time cutoff + midday time-stop | 🔬 research only — time-stop ✗; entry-cutoff shows morning breakouts carry ~2× PF (a size-concentration lead, not a truncation) |
| 20 | **ORB 3.0** · low-DOF deployable *(formerly "ORB SIMPLE")* | breakout of the opening range, stripped to **5 knobs** (no ATR/partials/trail) | ✅ **Strongest validated asset.** Auto-Validate 6yr PASS 6/6 (+$85.7k lockbox); XL 16yr PASS 6/6, WFE 176% (+$156.8k lockbox), DSR ~100%. Needs **no gate**. |
| 18 | ORB 2.0 · trail + ATR stop + vol filter | the complex ORB (ATR-normalized stop, partial exits, trailing) | ⚠️ WEAK on screen — the extra knobs didn't earn their keep |
| 19 | ORB 1.0 · open-momentum | the earliest, looser ORB | ⚠️ WEAK raw; became viable **only with the Random-Forest ML gate on 16yr** (see §4) |

**ORB 3.0 forward-test pick = run 119** (see §5): robust, tiny drawdown, sits on the
plateau (stop 0.75). Run 121 makes more money but rides a few big winners = riskier.

**ORB 3.1 / 3.2 are now REAL committed files (not informal), with a full deep-dive.**
> **Full running record: [`ORB.md`](ORB.md)** — deployable config, all results, backlog. Summary:
- **Deployable (2026-07-03): single-lot · ride-to-close · 0.75 stop · vol 1.25 · flat-EOD · 5-bar
  trailing stop** = `ORB_3_1.py` at `p0/trail5`. Saved as **starred run #125**. Full-history net
  $361k · PF 1.61 · maxDD −$9.4k · **MAR 38.6**.
- **The trailing stop is the risk-adjusted lever** — halves drawdown vs no-trail, doubles MAR (15→33).
  The 2-lot **partial** only lifts win-rate (→50-60%), not MAR — optional psychology, not edge.
- **Triple-validated:** walk-forward 6/6 folds OOS+, lockbox one-shot PASS (PF 1.63), **ES transfer
  PASS with no re-fit** (ES lockbox PF 1.57) → the edge is structural, not an NQ artifact.
- **Vol-target (risk-parity) sizing** = modest WIN that generalizes (lockbox MAR +29%, DD ~halved);
  best = `rp-cap3` execution-layer overlay (size ∝ 1/stop-distance, cap 3×).
- **Time-of-day is a real edge signal:** morning breakouts carry ~2× the profit factor of afternoon
  ones (first-hour PF 2.2 vs all-day 1.6; **lockbox PF 3.5 vs 1.6**, 6/6 WF folds).
- **★ Best result — the 3-lever sizing overlay:** risk-parity (∝1/stop) **×** time-tilt (~2× morning PF)
  **×** short-tilt are three *independent* edges that *stack*. **Longs are ~deadweight (PF 1.03) vs shorts
  (PF 2.74)** — confirmed on NQ *and* ES. Capital-matched, the full stack lifts **lockbox MAR 6.9 → 15.0
  (+118%)**, PF 1.63→2.85, 5/6 WF folds. Execution-layer only, no entry/exit change. *Tilt, don't cut*
  (truncation / hard short-only balloon drawdown). Durable code: `augur_engine/sizing.py` +
  `tools/orb_edge_report.py`; `run_grid(rank_by="mar")` added.
- **Tested & rejected:** chandelier ATR trail (overfits), trail-activation (hurts), breakeven (wash),
  regime-skip `atr_filter` and midday time-stop (the trail already handles low-vol / stalled trades).
- Run 121's headline came partly from an **inflated 0.25 stop** (below the 0.5 floor) — treat with caution.
- `ORB_3_2.py` (trail research) + `ORB_3_3.py` (time-structure research) = A/B forks, invariant-verified
  == 3.1 when their levers are off; research only, not for deploy.

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
| **125** ⭐ | NQ | **3.1 single-lot ride + 5-bar trail** | 1.61 | 41% | 4,064 | +$360.6k | **−$9.4k** | **deployable — WF + lockbox + ES transfer all PASS** |

*2026-07-03 prune: removed 4 exact-duplicate re-runs + 3 superseded ETH runs (backup
`optimizer_history.db.bak_20260703_163836_preprune`); ORB family 20 → 13 runs. Runs 119/121/112
relabeled with notes; double-star on 112/114 fixed.*

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

🎉 **Every research/method pill is now LIVE** (41/41). The only remaining item is operational:
1. **fills reconciliation** (§1) — reconcile web/mobile NinjaTrader (+ Webull) fills that skip
   the local DB. *Needs your live broker data — do this one WITH the owner present.*

*(✅ SHAP · ensemble top-K · adversarial validation · conformal band · causal check ·
synthetic scenarios all shipped 2026-07-04 — see Changelog.)*

### Deferred candidates — full backlog (nothing lost)
Applicable in principle; deferred for the reason shown. Promote any to a pill on request.

**Needs a heavy dependency:**
- **Neural-net / TabNet gate model** — `torch`. Tabular payoff usually ≤ XGBoost on ~9 features + a few-thousand trades.
- **Double-ML / Causal Forests** — `EconML`. Rigorous causal effect (controls for regime) — deeper than the randomization causal check.
- **Regularized Greedy Forest (RGF) gate** — `rgf-python`. Another tree learner; marginal over XGBoost.
- **Gaussian-Process gate** — sklearn (no new dep) but O(n³); impractical at thousands of trades.

**Different paradigm / known-low-success:**
- **Direct forecasting strategy** (LSTM / TCN) — `torch`/`keras`. Predict return → trade it. `GAINZ_RF` is the existing example; Carl's own notebook is "LSTM = FAIL."
- **Prophet / GluonTS probabilistic forecasting** — deps; overlaps the conformal band.
- ✅ **Seasonality** (intraday / weekly) — BUILT (§1 seasonality).

**Cheap — promotable to planned any time:**
- ✅ **Hypothesis test** (t-test + bootstrap CI) — BUILT as **edge significance** (§4). Confusion-matrix / discrimination-threshold (Carl §11) BUILT as **gate discrimination** (§5).
- ✅ **Return fat-tail fit** (Student-t) — BUILT (§1 return tail-fit).
- **t-SNE / UMAP** of the gate's entry-feature space — visualize win/loss separability.

**Truly not applicable:** generative image/LLM (StableDiffusion, Gemma), meta-Kaggle stats, geospatial maps, Titanic didactics.

---

## Changelog
- **2026-07-04** — **Two more no-dep diagnostics: return tail-fit (§1) + seasonality (§1)**
  (web v45.7, stack v4.1; board 45 live / 1 planned). `analytics.return_tailfit` — Student-t fit
  of **within-session** returns (drops overnight jumps that fake extreme tails). NQ 5m: df 2.6,
  excess kurtosis 29.4 (matches the EDA pre-flight), 1% bar move −32bp (1.23× normal) → extreme
  fat tails. `analytics.seasonality` — return/vol by ET hour + day-of-week; NQ: vol peaks at the
  09:00 open (U-shape). Both auto-run in Auto-Validate. **Every no-dep Carl method is now built;
  the only remaining items need heavy deps (torch/EconML) the project doctrine avoids on the
  trading PC, or are operational (fills reconciliation).**
- **2026-07-04** — **Two more from Carl's TOC + pill icons.** Iconified all 43 board pills
  (matching the card icons). Built **edge significance** (§4 · `analytics.edge_significance` —
  t-stat + p-value + bootstrap CI on mean trade PnL; ORB 3.1: mean +6.05 pts/trade, t 5.89, p≈0,
  bootstrap 100% profitable → significant; Carl §10) and **gate discrimination** (§5 ·
  `gate_calibration`→discrimination — ROC-AUC + confusion/precision-recall at the cut-off; ORB 3.1
  + RF: AUC 0.61, precision 43% vs 38% base, recall 71%; Carl §11). Board **43 live / 1 planned**, v4.0.
- **2026-07-04** — **Stacking / CCMP shipped — the LAST research pill** (board §6 → LIVE, web
  v45.5, stack v3.9; board 41 live / 1 planned). `analytics.ensemble_ccmp`: greedy hill-climb
  (Caruana ensemble selection) of config weights on a train split, tested on a held-out split
  vs equal-weight — on the ensemble card of every grid sweep. First run (ORB 3.0 top-5, avg
  corr 0.89): stacking BEAT equal-weight OOS (recovery 10.57 vs 8.17) by concentrating on 2
  configs [0, .24, 0, .76, 0]. **Every Carl-derived method pill is now live; only operational
  fills-reconciliation remains.**
- **2026-07-04** — **Three diagnostics shipped: serial-dependence ACF (§1) + VIF/collinearity (§2)
  + feature selection RFE-CV (§2)** (web v45.4, stack v3.8; board 40 live / 2 planned). All auto-run
  in Auto-Validate:
  • **serial_dependence** — ACF + variance-ratio of returns. NQ 5m: lag-1 −0.019, VR 0.94 → mild mean-reversion.
  • **vif_collinearity** — VIF per entry feature. NQ: range_pos 5.67 flagged (correlates w/ momentum/trend).
  • **gate_feature_select** — RFE-CV on entry features vs win. ORB 3.1: keeps 6/9, drops trend_20/atr_norm/dow
    (matches SHAP). Only stacking/CCMP (last research pill) + operational fills-reconciliation remain.
- **2026-07-04** — **Lead-lag / Granger shipped** (board §7 → LIVE, web v45.2, stack v3.7).
  `analytics.lead_lag`: aligns two sibling closes (ES↔NQ), returns, cross-correlation at ±lags +
  a native Granger F-test each way (numpy OLS, no statsmodels). Auto-runs in Auto-Validate vs
  the sibling / transfer instrument. First run (NQ vs ES, 5m, 317k bars): contemporaneous r 0.93,
  lag correlations ~0.02 → **no usable lead-lag at 5m** (it lives at the tick scale). Honest trap
  flagged: Granger is "significant" both ways (p≈0) only because of the 317k-bar sample —
  statistically real, not tradeable. Board 37 live / 5 planned.
- **2026-07-04** — **Gate calibration shipped** (board §3A → LIVE, web v45.1, stack v3.6).
  `ml_gate.gate_calibration`: 5-fold out-of-fold reliability of the gate's P(win) (|PnL|-weighted
  like the live gate) — ECE + a reliability table (predicted P vs actual win rate vs mean $/trade
  per bin) on the gate card. Because the gate trains |PnL|-weighted it targets EXPECTANCY, not
  win-frequency, so the check that matters is "higher score → higher $/trade". First run
  (ORB 3.1 + RF gate): expectancy MONOTONE (Spearman 1.0; predicted 0.39→−$121 … 0.82→+$458/trade),
  frequency ECE 0.18 → 0.06 if isotonic-calibrated. Board 36 live / 6 planned.
- **2026-07-04** — **Deferred list reclassified (honest).** Split "deferred" into three buckets —
  *heavy-dep* (NN/TabNet/Double-ML — buildable if a dep is approved), *different paradigm /
  low-success* (direct forecasting; Carl's own "LSTM = FAIL"), and *truly n/a* (image/LLM,
  meta-Kaggle, geospatial). Reclaimed **serial-dependence (ACF)** as a cheap applicable
  diagnostic → new planned pill (§1, board v3.5). Only image/LLM/meta/geo are genuinely inapplicable.
- **2026-07-04** — **Full master-TOC pass.** Pulled Carl's complete
  [master notebook](https://www.kaggle.com/code/carlmcbrideellis/a-selection-of-my-kaggle-notebooks)
  TOC (14 sections — many more than the sub-links first sent), assessed coverage (§2), and
  added **5 NEW planned pills** for genuinely-applicable gaps (board v3.4): gate calibration
  (Venn-ABERS), feature selection (Boruta/RFE), VIF/collinearity, stacking/CCMP,
  lead-lag/Granger. Forecasting / neural / generative-image / EconML items deferred as
  out-of-paradigm or heavy-dep for a rule-based futures backtester.
- **2026-07-04** — **Method stack COMPLETE: conformal band (§4) + causal check (§7) +
  synthetic scenarios (§8) shipped** (web v44.7, stack v3.3; board 35 live / 1 planned).
  All three are distribution-free (numpy/sklearn only), auto-run in Auto-Validate on the
  champion's whole-history trades, and are INFORMATIONAL (verdict unchanged):
  • **conformal band** (`analytics.conformal_pnl_band`) — split-conformal per-trade net-PnL
    interval with coverage MEASURED on a held-out split (self-check). ORB 3.1: 80% band ≈
    [−$900, +$713]/trade, measured coverage 79% ✓.
  • **causal check** (`analytics.causal_entry_test`) — randomization test vs random-entry
    nulls (same direction + holding length, random timing). ORB 3.1: beats 100% of nulls →
    entry timing carries real signal.
  • **synthetic scenarios** (`analytics.synthetic_day_bootstrap`) — trading-day bootstrap
    (resample days with replacement → alternate histories). ORB 3.1: profitable in 100% of
    800 histories. Only the operational fills-reconciliation pill now remains.
- **2026-07-04** — **Stack verified end-to-end.** Full Auto-Validate on the deployable
  **ORB 3.1** (NQ 5m RTH) exercised the whole session's stack in the real pipeline:
  **PASS 5/5** · WFE **1.63** (163%) · **8/8** folds held · DSR **~100%** · lockbox
  **+$64.2k** PF **1.70** · adversarial **AUC 0.60** (mild drift, matches standalone → the
  new checks are wired correctly). Cross-instrument regime read: NQ AUC 0.60 / ES 0.62 —
  both mild drift, both driven by a **modestly lower recent volatility** regime (a lockbox
  PASS on a calmer market is *reassuring* for a breakout strategy).
- **2026-07-04** — **Adversarial validation shipped** (board §4 → LIVE, web v44.4, stack v3.2).
  `ml_gate.adversarial_validation`: trains an RF to tell LOCKBOX bars from the pre-lockbox
  training history on market-state features; cross-validated ROC-AUC. AUC≈0.5 = the lockbox
  looks like history (trust the holdout); high AUC = regime drift, so a lockbox PASS/FAIL is
  weaker evidence. Reports the most-shifted inputs (in σ). Auto-runs in Auto-Validate
  (`run_validate` → `report.adversarial`), rendered as a strip; **informational — does NOT
  change the PASS/WEAK/FAIL verdict.** First run (NQ, 12-mo lockbox): AUC 0.60 = mild drift,
  driven by the volatility regime (atr_ratio/atr_norm).
- **2026-07-04** — **Ensemble top-K shipped** (board §6 → LIVE, web v44.3, stack v3.1).
  Equal-weight blend of the top-K sweep configs vs the single rank-1 winner, auto-computed
  on every grid sweep (`analytics.ensemble_blend` + `optimize._topk_ensemble`, opt-in
  `compute_ensemble`), shown as a card. Verdict on recovery (profit ÷ drawdown), with the
  top-K avg pairwise correlation as the diversification read. First run (ORB 3.0): recovery
  12.4 → 12.9 keeping 92% of PnL, avg corr 0.89 — a modest gain because the top ORB configs
  cluster tightly (a clean, low-DOF strategy has little to diversify).
- **2026-07-04** — **ORB items D + F.** D: **long/short asymmetry — shorts carry the whole edge**
  (LONG PF 1.03 deadweight vs SHORT PF 2.74; holds on lockbox + ES). Short-tilt stacks on the sizing
  overlay → 3-lever full stack **lockbox MAR 6.9 → 15.0 (+118%)**, PF 2.85 (5/6 WF folds). *Tilt, don't
  cut* (hard short-only balloons DD). F (consolidate): promoted the research into durable code —
  `augur_engine/sizing.py` (rp × time × side overlay + MAR), `tools/orb_edge_report.py` (reproduces
  the tables), `run_grid(rank_by="mar")`. See `ORB.md` §4.11 + §5.6. ORB edge-hunting complete.
- **2026-07-04** — **ORB item G (entry-time × sizing) — best result of the study.** Time-of-day tilt
  and risk-parity are independent edges that *stack*: capital-matched, the size overlay lifts ORB's
  **lockbox MAR +85% (6.9→12.7)**, PF 1.61→2.16, winning 5/6 WF folds — execution-layer only. Morning-only
  *truncation* is worse than baseline (concentration balloons DD) → tilt size, don't cut trades. `ORB.md` §4.10 + §5.6 deploy rule.
- **2026-07-04** — **SHAP shipped** (board §5 → LIVE, web v44.1, stack board v3.0). Gate
  feature attribution: `ml_gate.gate_explain`, surfaced as a bar panel on the gate
  before/after card. **shap 0.52 installed (owner-approved dep 2026-07-04):** tree gates
  (RF/XGBoost) use real TreeSHAP (mean|value|); logistic falls back to permutation
  importance (Δ log-loss). Per-trade local SHAP is a further step. First result on
  ORB + RF gate: keys on **momentum** (mom_20/mom_5) and **range-position**, not time-of-day.
- **2026-07-04** — ORB time-structure (`ORB_3_3.py`): midday time-stop rejected (cuts winners);
  **entry-time cutoff surfaced a real signal — morning breakouts carry ~2× the profit factor**
  (first-hour PF 2.2 / lockbox 3.5 vs all-day 1.6, 6/6 WF folds). Quality-vs-quantity, so best used
  as size-concentration, not truncation (new lead: entry-time × sizing). See `ORB.md` §4.9. *(NB: the
  SHAP note above found the RF **gate** keys on momentum not time-of-day — different question; that's
  gate trade-selection features, this is raw-strategy PF by entry hour.)*
- **2026-07-04** — ORB deep-dive folded in (see [`ORB.md`](ORB.md) for the full record).
  Real `ORB_3_1.py` (deployable single-lot ride + 5-bar trailing stop, run #125) + `ORB_3_2.py`
  (trail research). Findings: the trailing stop is the risk-adjusted lever (MAR 15→33); triple-
  validated (WF, lockbox, **ES transfer PASS**); vol-target sizing a modest generalizing win
  (`rp-cap3`); chandelier/activation/breakeven and regime-skip `atr_filter` tested & rejected.
  Pruned the runs DB (ORB 20→13, dupes + ETH). Added ORB 3.1/3.2 to §3; run #125 to §5.
- **2026-07-04** — Created this doc. Renamed ORB SIMPLE → **ORB 3.0** across engine +
  site (web VERSION 44.0). Confirmed ORB 3.0 is the strongest validated asset and needs
  no gate; documented the 16yr RF-gate flip on ORB 1.0. Mapped all Carl McBride Ellis
  notebooks to board status (9 live / 4 planned / 3 skipped).

> **How to keep this current:** update the relevant section + the changelog whenever a
> pill flips LIVE, a strategy changes verdict, a notable run lands, or a decision is made.
