# EDGELOG — Backtesting Stack (running status library)

**Single source of truth for where the backtesting engine stands.** Update this
whenever a method or strategy changes status, a run matters, or a decision is made.

- **Last updated:** 2026-07-17
- **Web VERSION:** 56.4 · **Stack board (`method_stack.html`):** v4.1
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
- **`close_confirm` entry option (2026-07-12):** implemented + verified in **ORB_3_0 / ORB_3_1**
  (default off; off = bit-identical to the old touch-entry behaviour). ON = only enter when a bar
  *closes* beyond the range edge (skips false-wick pokes) instead of on the touch. **Hypothesis dead
  at the validated config:** ON collapses net **$417k → $95k gross** (3.0 defaults, NQ 5m 16yr) —
  the worse fill on every *real* break swamps the false-wick savings. In both files' Medium/Long
  grid presets for future sweeps; not for deploy.

### ENGU-Q family (descending-trendline break, TF-branched) — `ENGUQ_1M/5M/15M_1_0.py`
Full running record: `Trading/ENGUQ_DB/ENGUQ_STRATEGY.md`. **NQ 1m = champion (run #149).**

**2026-07-12 — gap-honest fills restatement (status change):**
- All 3 ENGUQ files now **book gap-through stop fills at the bar's open** (hardcoded, like ORB 3.0)
  — prior numbers were **~35% optimistic** (full-history champion $688.5k → $448.6k net, maxDD
  -$47.5k → -$71.0k). `breakeven_R` param added (0=off) + grid presets.
- **#149 restated (lockbox, honest fills): $70,706 / PF 1.31 / DD -$70,959, 142 tr** (was
  $128,644 / PF 1.73 optimistic). Worst-ever DD is INSIDE the lockbox window (Nov 2025 → Mar 2026,
  recovered May 2026).
- Loss-tail study: worst-20 losses are all -1R initial stop-outs (trail never activated), 12/20
  entered 09:30–09:32; 2022 the only losing year. Only **breakeven 1.5R** survives honest fills
  (+$12.9k lockbox net, DD -7.5%); trade-multiplying fixes (time stop, risk caps, tighter stops)
  all fail — each overnight position costs ~$265 in gap slippage and they multiply position count.
- Re-optimization on the honest engine (**run #158**) **FAILED OOS** (lockbox PF 1.08, $9.4k,
  DSR 0.77 — overfit a sparse regime+breakeven config IS) → keep #149's params.
- **✅ DEPLOY CONFIG = #149 params + breakeven_R 1.5** → lockbox **$83,580 / PF 1.39 / maxDD
  -$65,635, 151 tr**. Honest expectation ≈ $83.6k/yr; tolerate -$66k DD, worst single loss ~-$8.5k.

**2026-07-13 — Round 2 (trade-management sweep) + Round 3 (ORB blend):**
- **Round 2 — trade-management sweep** (NQ 1m deploy config: #149 params + breakeven_R 1.5,
  gap-honest fills; baseline 2048 trades / $474,710.82 / maxDD −$65,635.22 / net-DD 7.23):
  - **Scale-out (partial at R-target): DEAD.** All 5 variants below baseline net/DD (best 5.86 at
    R=4.0/frac=0.33); negative by-year delta 16/17 years.
  - **ATR chandelier trail: DEAD.** No variant beats baseline (best x5-gated 5.38); trade count
    balloons 2.3-6x; deepens the current-DD segment to −$71.1k. Ungated (immediate) mode is
    net-negative.
  - **Pyramid (add 0.3 units at trail activation, act_R=2.5):** sole baseline-beater of 16
    variants — net +18% ($562.0k), PF 1.407 to 1.461, lockbox $83.6k to $93.2k, positive delta
    16/17 years incl 2022. BUT maxDD deepens to −$76.7k, net/DD flat (7.33 vs 7.23), and a
    concentration check shows 82% of the benefit sits in the top-10 pyramided trades
    (net-negative outside the baseline top-20 fat wins; loses on 360 of 611 fires). Verdict:
    equivalent to a smarter +18% size knob, not new edge. **PARKED** as an optional sizing
    decision — NOT adopted into the deploy config.
- **Round 3 — ORB + ENGU-Q portfolio blend** (2010-06-07 to 2026-06-30, exit-date daily PnL,
  both legs costed (pnl_pts − 0.533) × 20):
  - Legs: ENGU-Q 1m deploy config (checksum-gated, exact) + ORB 3.1 champion p0/trail5 (run #125
    config: or_bars=1, stop_frac=0.75, vol_filter=1.25, partial_exit_R=0, trail_bars=5;
    reproduced n=4064 / $360,640.26 / PF 1.611 / maxDD −$9,351.60 exactly).
  - Daily-PnL correlation ~ zero: Pearson +0.07 (daily, all sessions), +0.09 (both-traded days),
    +0.01 monthly (p=0.84). Rolling 12-mo monthly correlation is unstable (−0.69 to +0.54) —
    diversification comes from independence, not reliable hedging.
  - **1:1 combo (1 NQ each): net $835,351.08, maxDD −$60,097.59** (SHALLOWER than ENGU-Q alone
    at −$65,635.22), net/DD 13.90 vs 7.23 (ENGU-Q) / 38.6 (ORB). **ZERO losing years in 17** —
    ORB's 2022 (+$50.3k) fully covers ENGU-Q's only losing year (−$44.8k). During ENGU-Q's
    current DD (2025-12-12 to 2026-03-30) ORB netted +$7.3k; combo DD 8.4% shallower. Caveat:
    one simultaneous-stress case — ORB's worst episode (2025-02-28 to 03-14) sits inside
    ENGU-Q's #2 episode (2024-12-19 to 2025-04-21). Combo worst single day −$13,797 (2026-06-26,
    both legs lost).
  - Equal-DD weighting (w=7.02 on ORB) is analytic-only: net/DD 31.4 but requires ~7 NQ of ORB
    per 1 NQ ENGU-Q (~70 micros) — granularity/size noted, no recommendation at that scale.
  - Factual correction recorded: ORB 3.1 stop fills were confirmed already gap-honest in code
    (fills at the open on gap-through) — same realism standard as ENGU-Q.
  - Artifacts: session scratchpad round2_mgmt_report.md, round3_blend_report.md, r2/r3 pkl +
    drivers.

**2026-07-16 — Round 4 (risk quantification + final descriptives). Four studies, all independently verified. ZERO config changes — deploy config + 1:1 ORB blend stand, now risk-quantified:**
- Monte Carlo (10k paths, block bootstrap — the honest variant since losses cluster): the historical maxDD (−$65,635) is a MEDIAN outcome, not a worst case. 95th-percentile: ENGU-Q 16-yr −$114k; 1:1 blend 12-month −$44k with P(losing year)=8%. Account-sizing (P a 12-mo blend path draws down ≥33% / ≥50% of account): $75k → 35%/12%; $100k → 17%/2.6%; $150k → 2.8%/0.2%. Cost stress: ENGU-Q edge survives to 22.7x current costs, ORB to 9.3x; at 2x costs the blend still nets $766k with maxDD ~unchanged.
- NQ 5m (#146) honest-fills restate: lockbox drops $109,184/PF 1.722 (optimistic) → $81,821/PF 1.463 (honest); best variant +breakeven_R 1.5: full $546,186/PF 1.672/maxDD −$90,837, lockbox $84,877/PF 1.496, 4 losing years (2022 −$74,993). SURVIVES as a strategy but is NOT a diversifier: 1m+5m combined maxDD −$130,426 (~additive) and combined 2022 −$119,789 — both legs are long NQ simultaneously 87.9% of sessions; the +0.10 daily correlation is an exit-date-attribution artifact. Adding 5m = a size decision, same class as the parked pyramid. (Noted: 5m netted +$103k during the 1m's Dec-25→Mar-26 DD — single episode, not load-bearing.)
- ORB weight frontier (1×ENGUQ + w×ORB, w=0→4): w=1.0 is the drawdown-MINIMIZING weight (−$60,098); net/DD rises monotonically with w (no knee inside the grid) but higher w is just more size on one validated ORB config; 0 losing years at every w≥1.0.
- Trade anatomy: the 1.0R stop is placed about right — every tighter hypothetical stop (0.5-0.9R) loses more in forfeited winners than it saves on losers (0.9R still −$23k net). Overnight holding supplies 46.6% of all net PnL and weekends are +$115,945 over 573 boundaries → weekend/overnight flattening DEAD. Losses are sequentially independent (runs test p=0.53) and expectancy after 3+ consecutive losses is the strategy's BEST ($381 vs $232 unconditional) → all cooldown/stand-aside ideas DEAD; post-gap-stop conditioning not significant (p=0.11).
- Event days (FOMC 133 dates from Fed calendars incl 10 emergency; NFP 192 first-Friday+overrides; CPI honestly partial, 2024+ verified only): NO event type justifies a filter — union event days are 8.3% of sessions carrying 10.6% of losses (not significant), CPI±1 days average +$803 (the strategy likes event volatility), and the worst MTM day (2025-10-10, −$17,845) is not an event day.
- Artifacts: session scratchpad round4a-d reports + pkls + independent verification scripts.

### DRIVE 1.0 (first-hour momentum) — `DRIVE_1_0.py` · 🔬 research only

**2026-07-13 — new-strategy challenge (attempt to beat ORB 3.1 / ENGU-Q): NOT a challenger; kept as a research asset.**
- **Concept** (new to the library): direction = sign of the first hour's move (12 bars on 5m); enter at the
  next bar's open; stop = 0.75× first-hour range; ride to the session close; flat EOD; one trade/session.
  3 effective knobs. Exits/fills ORB-identical (stop-first pessimism, gap-through fills at the open).
- **Triage (pre-lockbox 2010→2025-06, NQ 5m RTH, 0.533 pts cost):** DRIVE beat 3 sibling concepts —
  prior-day-extreme break (PDX), N-day-high/low break (NDAY), late-day momentum (LDM). PDX/NDAY are DEAD
  (PF ≤ 1.14, MAR ≤ 2.6); LDM real but thin ($142k, MAR 6.0). Banked negatives.
- **Deep sweep (810 configs):** wide plateau at dr_bars=12 / stop 0.5–1.0 / no trail; deploy candidate
  n=3850 / **$295,437 / PF 1.18 / DD −$33,712 / MAR 8.8** pre-lockbox — net $ at ORB's level (ORB pre-lockbox
  $306.5k) but with 3.6× the drawdown; daily-PnL corr vs ORB **0.23** (a real diversifier); gap-aligned days
  PF 1.26 vs 1.08 opposed (tilt candidate); Friday strongest / Wednesday weakest.
- **Walk-forward: FAIL.** Frozen config 3/6 folds OOS+ (gate is ≥4/6); re-tuned picks 5/6 but WFE 0.32–0.43
  (< 0.5 gate) — essentially ALL profit sits in 2021–2025 (~$285k of $293k); 2010–2020 ≈ flat. Until proven
  otherwise, the edge reads as a post-2021 vol-regime artifact.
- **ES transfer: FAIL** (no re-fit: PF 1.04, MAR 0.8 — unlike ORB, the edge does not travel).
- **Lockbox: NOT SPENT.** Pre-lockbox gates failed, so the one-shot holdout stays sealed for a future DRIVE 2.0.
- **Verdict: champions unchanged** (ORB 3.1 MAR 38.6 · ENGU-Q net $474.7k). DRIVE 1.0 stays in the library
  as a research strategy (same precedent as ORB FADE): the only new concept of 4 with a real, if thin, edge —
  revisit if the 2021+ regime persists, or as a third portfolio-leg candidate after a regime-robust rework.
- Artifacts: `augur_strategies/DRIVE_1_0.py` (parity-gated vs the research code, smoke test in `__main__`);
  session scratchpad: triage_new_strats.py, drive_deep{.py,_report.md,_results.json}, drive_wf.py,
  drive_build_report.md.

**2026-07-13 — challenger rounds 2–3 (same brief: beat ORB 3.1 / ENGU-Q). Five more concept families, ~160 configs — none clears a champion bar. All pre-lockbox; lockbox still unspent.**
- **ORB 3.1 on 1-minute bars** (finer trail + sub-5-min opening ranges — the "different params" shot): best MAR 30.8
  vs champion 32.8, and every competitive 1m config trips the fill-artifact rule (avg loss 5–6 pts vs the ~8-pt floor
  the 0.25-pt slippage model can support). **The tighter-risk path to a higher MAR is physically closed by the fill model.**
- **MIDDAY** (lunch-range continuation breakout, new anchor): best MAR 19.5 — artifact-flagged, thin sample (n=488),
  profit 85% post-2021. Dead.
- **PULLBACK** (first-pullback continuation after the OR break, structural stop): best MAR 2.2. Dead.
- **ORB HOLDOVER** (hold winning ORB trades overnight on ETH bars, stop live on every Globex bar, roll-safe):
  overnight holding strictly SUBTRACTS — best genuine variant (hold ≥2R, ride, 3-day cap) MAR 32.02 / $299.5k vs
  flat-EOD 32.78 / $306.5k, and looser holds degrade monotonically to MAR 8. **Flat-EOD is confirmed optimal for ORB entries.**
- **SWING** (multi-day Donchian trend-follow, chandelier/Donchian exits, ETH-managed, roll-flat rule): best MAR 6.79
  ($206k, long-only, N=20, chandelier 3.5×ATR); every both-sides variant is worse (shorting the pattern loses outright);
  daily-PnL corr vs ORB 0.22 → **banked as a potential 3rd portfolio leg**, not a champion.
- **Roll-seam data finding (new):** the NOADJ stitcher rolls on volume dominance, so the ~77-pt quarterly price seam
  lands a few days BEFORE roll-Wednesday; a roll-Wednesday flatten rule is a backstop, not a dodge — any future
  multi-day strategy must detect the seam itself.
- **Cumulative verdict after 3 rounds / 9 concept families / ~1,150 configs: no new strategy beats the champions on
  honest fills.** The validated ways to raise the book remain the §5.6 sizing overlay (lockbox MAR 6.9→15) and the
  ORB×ENGU-Q blend (net/DD 13.9, zero losing years in 17) — layers on the champions, not new entries.
- Artifacts: session scratchpad round2_triage_report.md / round3_triage_report.md (+ results .json and drivers).

**2026-07-13 — challenger round 4 (bar relaxed to "beats or nearly beats"): four more families; SWING 2.0 reached the lockbox — and FAILED it. The 2025→2026 holdout is now spent for the SWING family.**
- **LDM deep-dive** (late-day momentum, incl. the academic gap-inclusive signal): best MAR 6.8; 2 of the top 3
  configs REGIME-CONCENTRATED. Dead as a champion; thin diversifier at best.
- **ES↔NQ spread reversion** (relative value — first RV family tried): 23/24 configs net-negative after
  two-leg costs. Dead outright.
- **Volume-ignition momentum** (volume as the signal, not a filter): best MAR 3.3. Dead.
- **SWING 2.0** (N-day Donchian long-only refinement of round 3's diversifier): pre-lockbox MAR 12.3–15.0,
  regime-OK, corr vs ORB ≈ 0. Validation battery: walk-forward 6/6 frozen folds PASS · trade bootstrap
  P(net≤0)=0.0014 · BUT neighborhood = spike (neighbors keep only 20–38% of peak MAR), ES transfer weak/FAIL,
  and rank-1-of-120 selection inflation (family median MAR 3.97). **Pre-registered lockbox one-shot**
  (SECONDARY config N=55/touch/donch_20/cap3.0, NQ+ES combined, entries ≥ 2025-06-30): **FAIL — combined net
  −$13,373 (NQ −$5.4k / ES −$8.0k) with blow-up losses on both markets** (worst NQ trade −$18.8k vs a $2.0k
  median pre-lockbox loss). The neighborhood/selection-inflation warnings were correct.
- **Lockbox accounting:** the one-shot burned the 2025-06-30→2026-06-30 holdout for the SWING family (one
  look, used, failed). ORB/ENGU-Q lockbox standing unaffected.
- **Program verdict after 4 rounds / 13 concept families / ~1,400 configs: no new strategy beats or honestly
  nearly-beats the champions on this data.** The validated paths to a better book remain the §5.6 sizing
  overlay and the ORB×ENGU-Q blend (see the 2026-07-13 Round-3 blend entry); genuinely new edges need new
  DATA (order-flow delta, economic calendar, more instruments), not more configs on the same OHLCV.
- Artifacts: session scratchpad round4_triage_report.md, swing_validation_report.md, swing_lockbox_oneshot.py
  (+ results .json and drivers).

**2026-07-13 — challenger round 5 (owner: "find a new strategy and test"): the last two untried OHLCV families — both dead in triage.**
- **EXPAND** (ATR range-expansion breakout from the open — the classic volatility-breakout anchor, 96 configs):
  best MAR 16.9, regime-healthy, no fill-artifact flags — BUT the overlap diagnostic shows it is
  **ORB in disguise**: on the 2,632 days both traded it picks the same direction 89.9% of the time
  (shared-day PnL corr 0.40) and captures the same trend-day edge less efficiently. Dead as a new edge.
- **VWAPT** (trend-side VWAP cross-and-hold — volume-weighted anchor, first non-fade VWAP test, 12 configs):
  best MAR 6.7 and **REGIME-CONCENTRATED** (2010–2020 = only 11–16% of net; 2022 alone 29–36%). Dead.
- Also this session: **ORB backlog item X resolved** (see ORB.md §4.21) — 1m ORB fails the pre-registered
  slippage stress (best MAR 24.3 at 0.75-pt vs the ≥25 bar) while the **5m champion holds MAR 28.3 under
  identical stress** (robust out to 1.0-pt slippage — a new robustness credential for the deployable).
- **Program running total: 5 rounds / 15 concept families / ~1,500 configs — no new strategy beats or
  honestly nearly-beats the champions on this data.** Every failure lands in one of three buckets: too thin
  after costs, regime-concentrated (post-2021 artifact), or ORB-in-disguise. The forward paths remain
  new DATA (order-flow delta, calendar, more instruments) or deploying the validated layers (§5.6 overlay,
  ORB×ENGU-Q blend).
- Artifacts: session scratchpad round5_triage_report.md (+ .json), itemX_slippage_report.md.

**2026-07-14 — challenger round 6: the three never-opened rooms — overnight session, weekly anchor, overnight→open relay. All empty (0/156).**
- **GLOBEX** (London-ORB + Asia-range break, traded inside the overnight session only, judged at a
  pre-registered 0.5-pt slippage for the thinner Globex book): best MAR 2.27 ($54k) — REGIME-CONCENTRATED
  *and* fill-artifact-flagged. **The NQ overnight session has no honestly-fillable edge at these costs.**
- **WEEKLY ORB** (Monday-range breakout, Tue–Fri touch entry, one trade/week): best MAR 3.82 ($50k) —
  REGIME-CONCENTRATED. The calendar-week anchor adds nothing over the daily one.
- **RELAY** (09:30 entry in the overnight/London-drive direction, overnight-range stop): best MAR 1.08 —
  REGIME-CONCENTRATED (2010-2020 subtotal negative). Overnight direction does not carry into the day at
  tradeable strength.
- All three are ~uncorrelated to ORB (0.01–0.14) — moot, since none clears any bar.
- **Program final tally: 6 rounds / 18 concept families / ~1,650 configs.** Every session (RTH, Globex),
  every anchor scale (1-minute to 55-day to calendar-week), every signal class (breakout, momentum,
  reversion, RV, volume, VWAP, order-flow-free structure) has now been probed under identical honest-fill
  rules. Every failure lands in the same three buckets: thin-after-costs · post-2021 regime artifact ·
  ORB-in-disguise. **The OHLCV edge inventory of this dataset is fully claimed by the champions.**
  Next-edge paths remain: the order-flow program (§7, revisit ~Oct 2026 at 3+ months of data) and the
  deployed layers (§5.6 overlay — now live-wired, see ORB.md item 4 — and the ORB×ENGU-Q blend).
- Artifacts: session scratchpad round6_triage_report.md (+ .json, r6_*.py drivers).

**2026-07-14 — challenger round 8 ("something intraday"): SWEEP + the LDM-0DTE reframe — both dead, both with clean autopsies.**
- **SWEEP** (stop-run reversal: intrabar sweep of the prior day's high/low + close-back reclaim → fade the
  trap, stop under the sweep extreme): best MAR 2.78 ($15.9k, n=176) — 0/36 beat or nearly-beat, all top
  configs REGIME-CONCENTRATED. The autopsy explains the starvation: ~25% of sessions gap through the
  prior-day level overnight (setup void), ~2/3 of the rest never touch it — the pattern fires on only
  3–7% of sessions. Prior-day stop-run reversal joins the fade family's graveyard.
- **LDM-0DTE reframe** (probe, pre-registered wording): is late-day momentum a structural daily-0DTE-era
  (2022-07+) effect? **ARTIFACT — CLOSED, 0/4.** No knob-free config clears PF ≥ 1.25 in the actual 0DTE
  era; rolling 6-month windows show burst-driven not stable PnL; the placebo-cut (2018-07) control confirms
  the failure is structural. Bonus finding: the late-day edge that killed LDM/DRIVE in earlier rounds
  actually lives in the **2020–2022-06 COVID-vol window**, not the 0DTE era — the "regime concentration"
  kill flags were correct for the right reason.
- **Program tally: 8 rounds / 21 concept families / ~1,700 configs.** Verdict unchanged for unconditioned price patterns: the champions hold every honest edge found so far. Open new-edge paths: the order-flow program (§7) and **TTIBS 1.0 (round 7, above) — the sole triage survivor, WF/lockbox still pending.**
- Artifacts: session scratchpad round7_report.md (+ .json, r7_*.py).

**2026-07-14 — challenger round 7: TTIBS 1.0 (daily buy-weakness mean reversion, from the owner's "proven strategies" web sweep) — FIRST family to SURVIVE triage since round 1. WF/lockbox still pending; champions unchanged.**
- **Where it came from:** a sourced-rules sweep (quantifiedstrategies.com Turnaround-Tuesday variants — the
  IBS article's own thresholds are paywalled, so thresholds were grid-searched, not copied). *IBS* = where
  the day's close sits in the day's range: (close−low)/(high−low), 0 = closed on the low.
- **Concept (LONG only, daily bars off the NQ 5m RTH master):** buy a weak close (IBS < threshold), exit the
  first close with IBS > 0.80, capped at 6 trading days. New file: `augur_strategies/TTIBS_1_0.py`
  (plugin-contract, gap-honest next-open fills, roll-seam flatten guard, __main__ smoke test).
- **Pre-registered triage (2010→2025-06-30, 180 configs, 0.533 pts cost, next-open fills gate-deciding):**
  representative cell `ibs_entry=0.20 / ibs_exit / hold_cap=6 / ma200=off` → **n=442, net $307,208, PF 1.82,
  win 68.1%, maxDD −$25,054, MAR 12.26, avg $695/trade**. All 6 gates PASS (regime spread 46.4% post-2021;
  avg loser 133 pts ≫ artifact floor; ORB corr −0.10; year-max 30.5%; **2022 = +$20,674** — the
  mean-reversion thesis's own stress test, profitable exactly where ENGU-Q lost). 4 of 6 neighbour cells
  (ibs_entry 0.20/0.30 × ma200 on/off) pass ALL gates — a broad shelf, not a spike.
- **The one non-free knob: hold_cap MUST be 6.** hold 2/4 versions of the same trigger fail the
  not-a-disguise gate vs ENGU-Q (corr up to 0.44) — short holds ride the same few-day NQ dip-bounce ENGU-Q
  already owns; only the full-week IBS-recovery exit decorrelates it (r 0.25). The prettiest corner
  (ibs 0.10: PF 2.89, MAR 20.5) is NOT deployable — n=283 < 300 floor, regime-concentrated, and the most
  ENGU-Q-correlated cell.
- **Honest caveats:** (1) G5's ENGU-Q daily-PnL series is a directional repro (its pre-lockbox net didn't
  reconcile to the doc's headline — corr is shape-reliable, not certified; re-verify with a checksum-exact
  repro at the blend stage). (2) Dollar profits are back-loaded (2010–2016 ≈ $25k of $307k) — partly
  mechanical ($/pt fixed while NQ 10×'d); WF folds must show the early-era edge in PF terms. (3) No
  stop-loss in v1.0: worst trade −$16.7k, max adverse excursion −$31k (Jan-2022) — tail must be priced
  before any deploy talk. (4) Close-fill look-ahead haircut measured at 21.5% (published SPY family ~25%) —
  the edge survives honest fills, it isn't a same-bar artifact.
- **Status: 🔬 SURVIVED TRIAGE — same stage DRIVE reached before dying at walk-forward. Next: frozen-config
  WF (≥4/6, WFE ≥0.5) + ES transfer + exact-repro G5 + pre-lockbox 3-leg blend read. Lockbox one-shot
  (2025-06-30→2026-06-30) SEALED — never loaded during triage (loader hard-cutoff), spend only on owner
  sign-off.** Round-6's "inventory fully claimed" verdict stands for *unconditioned* OHLCV patterns; TTIBS
  is the first *calendar/position-in-range-conditioned* family tried, which is why it wasn't covered by
  rounds 1–6.
- Artifacts: session scratchpad ttibs/ (prereg, triage report + .json, drivers); 3 trades hand-verified
  exactly (entry IBS, next-open fill, exit IBS, pnl−cost arithmetic); 0 of 442 trades cross a roll seam
  (48 seams detected, audited).

**2026-07-14 — round 7 stage 2 (walk-forward + ES transfer + blend read): ALL GATES PASS. One blocker
found — a pre-existing ENGU-Q reproducibility defect — before the lockbox should be spent.**
- **Walk-forward (the DRIVE-killer): 6/6 frozen folds net-positive** (DRIVE was 3/6). Early folds are real
  in POINTS/PF terms (fold-1 PF 1.68 / +586 pts, fold-2 PF 1.24 / +225 pts) — the dollar back-loading was
  NQ's ~10× price level, not a missing early edge. Re-tuned WFE 1.99 (gate ≥0.5; DRIVE 0.32–0.43) — every
  OOS fold beat its in-sample expectancy (partly era-inflated; the frozen 6/6 is the meaningful result).
- **ES transfer, no re-fit: PASS** — PF 1.695, net $170,492, 13/16 years positive (ORB's passing bar was
  PF 1.57; DRIVE failed at 1.04). 2022 profitable on BOTH instruments (ES +$30.6k, NQ +$20.7k).
- **Statistics:** edge significance t=3.94 (p=0.0001), 100% of bootstrap resamples profitable; Deflated
  Sharpe 0.96 vs the restricted 30-cell grid.
- ⚠️ **ENGU-Q reproducibility defect (pre-existing — NOT a TTIBS problem):** the deploy config (#149 params
  + breakeven_R 1.5) could NOT be rebuilt from the checked-in `ENGUQ_1M_1_0.py` — two independent attempts
  landed at n=3618 / $276k / DD −$133k vs the documented n=2048 / $474.7k / DD −$65.6k, and the ground-truth
  blotter (`Trading/ENGUQ_DB/blotters/run149_NQ_1m.csv`) opens with a trade the current file never
  generates → entry-logic drift, not a param typo. **Until fixed, every ENGU-Q-relative number is
  directional, not certified** (G5-real corr 0.254 — hold-cap-6 decorrelation confirmed directionally).
  ORB's side IS certified: #125 reproduced bit-for-bit (n=4064 / $360,640.26 / PF 1.611 / DD −$9,351.60),
  TTIBS↔ORB corr −0.103. Fix leads: #149's exact params are stored in `optimizer_history.db` (runs table),
  and the 2026-07-14 Pine-port session reproduced #149 successfully — diff that session's invocation
  against the file.
- **Blend read (2010-06-07→2025-06-30, exit-date daily PnL, 1:1:1) — directional pending the ENGU-Q fix:**
  2-leg baseline net $486,509 / DD −$117,070 / net-DD 4.16 / 3 losing yrs (baseline uses the BROKEN ENGU-Q
  repro — hence far below the round-3 figures) → 3-leg with TTIBS: net $793,718 / DD −$124,751 / net-DD
  **6.36** / **2 losing yrs**. TTIBS added +$27.7k during ENGU-Q's 2022 drawdown, −$7.7k during the
  Apr-2025 episode; worst 3-leg day (2025-04-07, −$29.4k) was ~100% ENGU-Q, TTIBS flat.
- **Status & order of operations: TTIBS standalone = fully validated pre-lockbox. (1) Fix the ENGU-Q
  repro → (2) re-certify G5 + the blend on the true legs → (3) owner sign-off to spend the TTIBS lockbox
  one-shot (2025-06-30→2026-06-30 — still sealed, never loaded).**
- Artifacts: scratchpad ttibs/ ttibs_stage2_report.md + ttibs_wf_prereg.md + per-task drivers/JSONs.

**2026-07-15 — round 7 lockbox one-shot (owner signed off): FAIL. TTIBS family CLOSED, lockbox spent.**
- Pre-registered frozen config, plumbing dry-run-verified on a seen year first, then ONE run on signals
  2025-07-01→2026-06-30: **n=16, net −$44,320.56, PF 0.44, WR 37.5%, worst trade −$20,710.66** (inside the
  pre-registered −$25k no-blowup floor). FAIL on the net>0 condition. Not a tail/sizing disaster — the
  pre-lockbox edge (6/6 WF folds, clean ES transfer) simply didn't show up in the held-out NQ year.
- Two months carried the loss (Nov-2025 −$28.9k, Jun-2026 −$16.9k); Jan-2026 +$10.9k; no exits Apr/May.
- **Report-only observations BANKED, not a re-tune license** (the year is spent — one look, same
  accounting as SWING): (1) ES same-frozen-config was POSITIVE in the identical window (+$11,563,
  PF 1.34, WR 72.7%) — NQ-specific failure, not a concept-wide one; (2) signal frequency halved
  (16/yr vs the 15-yr ~29/yr average). Any TTIBS 2.0 must be motivated by new data or a structural
  hypothesis, never by fitting this spent year.
- TTIBS 1.0 remains in the library as 🔬 research (validated pre-lockbox, failed the holdout) — same
  precedent as DRIVE/SWING. Champions and the blend unchanged.
- Program consequence (owner directive: keep hunting / adjust): **GAPFADE — conditioned small-gap fade,
  the #2 candidate from the web sweep — enters triage as round 9** with its own prereg, gates, and the
  same one-look lockbox accounting.
- Artifacts: scratchpad ttibs/ ttibs_lockbox_prereg.md, ttibs_lockbox_oneshot.py, ttibs_lockbox_report.md
  (+ oneshot/dryrun results .json).
- **2026-07-16 addendum — web run #161 (owner asked to SEE a full Auto-Validate on TTIBS): PASS 7/7 —
  but it does NOT reopen the family.** The run exposed and fixed a real engine bug first (see Changelog:
  `run_auto` never passed `index`; broken run #160 = FAIL 2/5 / PF 0.00 / $0 is the bug artifact, kept in
  history). The corrected #161 (XL, 300 trials, 18-mo lockbox 2024-12-30→2026-06-30): IS PF 1.97, lockbox
  HELD +$86,301 / PF 1.55 / 59 tr, ES transfer holds (PF 1.57 / $250.8k / 666 tr). ⚠️ Why this coexists
  with the round-7 FAIL: (1) its Bayesian champion FILLS AT THE CLOSE (blotter entries 15:55, exit next
  close) — the look-ahead-flavored mode round 7 excluded from deploy (next-open haircut ~21.5%);
  (2) different holdout (18 mo, includes the strong 2025-H1) and a config never taken through G3–G6
  (regime spread / ENGU-Q-disguise / year concentration); (3) the pre-registered 12-mo next-open one-shot
  FAILED and remains the binding verdict. #161 = visibility + engine-fix verification, not a deploy case.

**2026-07-15 — round 9 independent replication (parallel session): GAPFADE 1.0 built + triaged from
scratch (216 configs, fixed-%-band + conditioning variant) — DEAD. Same verdict as round 9 below, reached
via a different implementation: 0 of 36 plateau groups clear the pre-registered gates.**
- **Concept:** fade an overnight gap of 0.15–0.6% back toward yesterday's RTH close at the 09:30 open,
  intraday only, flat by close, roll-seam days skipped as fake gaps (48 seams detected; the guard rarely
  bites — seams dwarf the band — but worked when it did). New file: `augur_strategies/GAPFADE_1_0.py`
  (plugin-contract, research-only). 216 configs, 2010→2025-06-30, lockbox never touched.
- **The kill, precisely:** wide-band cells pass PF (best plateau: n=673, $28.2k, PF 1.19) but FAIL G3
  (post-2021 profit share 57.8–90%, regime-concentrated); the `yest_ibs_aligned` cells (the published-edge
  conditioning) fix G3 but FAIL G6 (single-year 55–56%). No cell threads both — and even the "best" group's
  economics are trivial (~$1.8k/yr). Confirms the published naive-ES-negative result extends to NQ even
  with conditioning.
- **Banked findings:** shorts (gap-UP fades) carried 83% of net (PF 1.23 vs longs 1.11) — the OPPOSITE of
  the published claim that gap-down fades are the stronger side; ORB #125 reproduced exactly again
  (n=3,815 / $306,331 / PF 1.61 pre-lockbox); GAPFADE↔ORB corr 0.118 with a 50/50 direction split (not a
  disguise — just not an edge). GAPFADE's lockbox: NOT spent (triage kill = holdout stays sealed).
- Artifacts: scratchpad gapfade/ (prereg, triage report + .json incl. the full 36-group gate scan, drivers);
  3 trades hand-verified to the tick.
- **⚠️ Cross-implementation reconciliation (matters for the round-9 META-FINDING below):** the two
  independent GAPFADE runs agree on DEAD but *disagree on which side carried the residue* — this run
  (fixed %-bands 0.15–0.6%, mirror-stop): shorts/gap-UP fades = 83% of net; the ATR-banded run below:
  longs +$32.8k / shorts −$26k to −$33k. Likely cause: band definition + stop scheme select different gap
  populations. Consequence: the meta-finding's citation of "GAPFADE's long leg" as buy-weakness evidence is
  implementation-dependent — the other three families (TTIBS, CALENDAR, SWING) still support it; GAPFADE
  should be treated as side-agnostic noise, not corroboration.

**2026-07-15 — challenger round 9: the last two web-shortlist entries (GAPFADE + CALENDAR) — both dead; the shortlist is fully dispatched.**
- **GAPFADE** (fade the overnight gap toward prior close, ATR-banded, 54 configs): nets to noise (best MAR
  0.11, $6.8k). The split is the story: **fading gap-DOWNS (buy-weakness) made +$32.8k; fading gap-UPS
  (sell-strength) lost −$26k to −$33k** across the best configs. Clears no bar. Dead.
- **CALENDAR** (turn-of-month long window + pre-holiday drift, 16 configs, roll-safe verified 0/1080):
  the ToM drift is REAL (short mirror loses −$82.5k → genuine long seasonal, not noise) but tops out at
  **MAR 2.19 / $78.7k** — a fact about the market, not a tradeable leg. Clears no bar. Dead.
- **META-FINDING (confirmed across 4 independent families):** the only daily-scale structure that even
  survives triage/WF in this data is **long-only buy-weakness** — TTIBS (round 7: passed WF + ES transfer,
  failed the lockbox), GAPFADE's long leg, CALENDAR's long-only drift, SWING's long-only Donchian — while
  every sell-strength / short-side mirror dies outright. This is an upward-drifting index; shorts only pay
  intraday via ORB.
- **Tally: 9 rounds / 23 concept families / ~1,770 configs · 2 lockboxes spent (SWING ✗, TTIBS ✗).** The
  owner's web shortlist is now fully dispatched (IBS→TTIBS ✗ failed lockbox (round 7) · GAPFADE ✗ ·
  calendar ✗ · delta gate — off-table, owner has no order-flow feed). **No live challengers remain.**
  New candidates require new data or a new owner-sourced idea; the deployed book (ORB×ENGU-Q blend +
  §5.6 overlay) is the working machine.
- Artifacts: session scratchpad round9_report.md (+ .json, r9_*.py).

**2026-07-15 — challenger round 10 (owner: "deep dive the web"): NOISE — the Zarattini/Aziz/Barbon intraday-momentum envelope. Real mechanism, wrong regime. Dead as a challenger.**
- Web deep-dive screening: the 2025–26 retail/quant literature is ~entirely our dead families renamed (ORB
  variants, IBS buy-weakness, gap plays, VWAP fades). The ONE mechanically new candidate: **NOISE** — a
  time-of-day-calibrated envelope around the open (mean |open→bar-t| move over N prior sessions, anchored
  to max/min(open, prior close)); long above / short below, exit on band re-entry / VWAP trail, flat EOD.
  Source: Quantitativo ES/NQ port of the "Beat the Market" paper (reported NQ Sharpe 1.67 at 8× vol-target).
- Faithful port, 54 configs, NQ 5m RTH, house costs: **all 54 net-positive** (the mechanism is real),
  best `LB=14 · band 1.25 · vwap-trail` = **MAR 6.90 / $253.8k / n=4,306** — clears NO bar (champion /
  nearly-beat / third-leg all miss). Corr vs ORB only **0.21–0.25** (distinct engine, ~80% same-direction
  on shared trend days); longs > shorts exactly as the paper reports; median 2.1 signals/session, fee drag
  up to 48% of gross on high-turnover cells; `flip` verified a no-op (hand-traced, not a bug).
- **Era verdict (the headline, pre-flagged from the authors' own caveat): all top-5 REGIME-CONCENTRATED —
  three post NEGATIVE 2010–2017 subtotals.** The paper's "flat until 2018" weakness replicates exactly on
  NQ. Same bucket as DRIVE/VWAPT: a post-2018 vol-regime harvest, not a durable edge.
- Status: 🔬 research knowledge — revisit ONLY as a regime-conditional diversifier candidate if the
  post-2018 regime is ever accepted as the trading assumption (it is not, per house rules).
- **Tally: 10 rounds / 24 concept families / ~1,820 configs · 2 lockboxes spent · no live challengers.**
  Both web sweeps (owner shortlist + deep-dive) are now exhausted.
- Artifacts: session scratchpad round10_report.md (+ .json, r10_*.py incl. the hand-verified sigma check).

**2026-07-15 — round 11 (owner: "deep dive the web, beat ORB"): web sweep round 2 + an ORB
external-conditioning diagnostic. Both come back empty — and the emptiness is now independently published.**
- **Web round 2 (sources round 1 never opened):** Quantpedia free tier, Alvarez Quant, Quantifiable Edges,
  Davey/Build Alpha, fresh 2023–26 SSRN/arXiv — nothing clears the bar (all graveyarded families,
  cross-sectional stock universes, or ~15-occurrences-in-60-years breadth thrusts). Key find = independent
  corroboration: a **May-2026 arXiv falsification series (Mesfin, 2605.04004 + two companions)** ran
  essentially our program on MNQ 5m 2021–25 at honest costs — 14 OHLCV signal families, none pass; no ML
  config beats the 51.8% base rate. Our graveyard conclusion is the published state of the art, not a
  house quirk.
- **ORB conditioning diagnostic** (§5-style slice study on the champion blotter, NO config search, window
  2010→2025-06-30 with the final year held out; blotter reproduced exactly: n=3,815 / $306,331 / PF 1.607).
  Sliced by VIX bins, VIX-vs-20dMA, VIX3M term structure, day-of-week, FOMC/CPI/NFP days, P/C quintiles —
  era-stability + permutation tests + overlay double-count checks. **Pre-stated graduation bar: NONE
  graduate.**
  - VIX bins = the one clean monotonic pattern (PF 2.06 at VIX<13 → 1.31 at VIX>30, stable both eras) —
    but mean stop-distance rises 3.5× across the same bins, so the deployed **§5.6 risk-parity overlay
    (size ∝ 1/stop) is ALREADY harvesting exactly this effect** — independent external validation of the
    overlay's rationale. A VIX tilt on raw ORB would double-count it.
  - Day-of-week: Wednesday's apparent weakness is 86% FOMC/CPI contamination (108/125 FOMC days = Wed);
    Wed-ex-event PF 1.61 = baseline → the gate RFE's original "dow uninformative" call CONFIRMED. Friday
    PF 1.77 looks genuine but permutation p=0.485.
  - Event days: **FOMC-day ORB PF 1.30 (era-1 net-losing, PF 0.86), direction stable both eras — but n=125,
    permutation p=0.904 → banked as a WATCH item only**, not actionable.
  - Every mean-shift delta fails permutation (p 0.25–0.90): the PF patterns are tail-shape effects the
    5-bar trail already manages, not size-tilt fuel.
  - Data notes: CBOE's free equity put/call feed is DEAD since 2019-10-04 (no free replacement found);
    ALFRED `downloaddates` returns FOMC revision-dates not meeting-dates (scraped federalreserve.gov
    instead); alfred/bls block plain urllib — browser fetch required.
- **Round-11 verdict: "beats ORB" is not on the open web.** Remaining levers, in order: (1) **more
  instruments** for the validated ORB recipe — needs new 5m history (YM/RTY/CL/GC), an owner
  data-acquisition decision; (2) the **order-flow program** at 3+ months of accumulated data (~Oct 2026);
  (3) **owner-originated ideas**. More configs or conditioning on the same public information is now
  quadruple-confirmed dead money.
- Artifacts: scratchpad orbcond/ (orbcond_report.md, results + followups .json, blotter csv, drivers);
  round-2 research summaries in-session.

**2026-07-16 — challenger round 12 ("new params on the promising ones"): NOISE-2 became the program's strongest challenger — 4 of 5 battery gates — then FAILED ES transfer. No lockbox fired; family shelved with its holdout INTACT.**
- This round's grid (108 configs): **wider symmetric bands (1.5× vs the paper's 1.0×) + VWAP exit turned NOISE
  regime-healthy on NQ 5m** — the pre-registered question answered YES: LB14/1.5/1.5/vwap/both/all-day =
  MAR 8.14, n=3,147, $254.4k, PF 1.31, DD −$31.2k, 2010–2017 **+$15.8k**, corr vs ORB 0.22. Long-only and
  time-window cuts HURT this family (unlike everywhere else in the program); 1-minute execution kills it
  (2010–17 flips negative) — the edge stands on 5m only. DRIVE closed permanently in the same round
  (best-ever MAR 10.91 long-only + gap-align, still regime-concentrated at 20.8% pre-2021).
- **Validation battery (pre-registered, all-five-or-nothing):** C1 walk-forward **PASS** (frozen 5/6 folds
  OOS-positive; per-fold re-selection over the full grid doesn't crater but never beats the frozen config) ·
  C2 neighborhood **PASS** (mean neighbor MAR 6.19 ≥ 4.89) · C3 family health **PASS** (median 5.91 ≥ 5) ·
  C5 bootstrap **PASS** (P(net≤0)=0.0000, 5th-pct +$140.7k) · **C4 ES TRANSFER FAIL: PF 1.123 < 1.2**, ES
  era table re-concentrates (2010–17 −$11.6k) and ES avg loss 5.9 pts = fill-artifact zone. **Verdict:
  FAIL — the edge does not travel; working suspicion = NQ post-2018-regime specificity.** Precedent note:
  TTIBS PASSED the ES gate and still died at its lockbox — 4/5 with the transfer gate failed earns no look.
- Status: **NOISE-2 = 🔬 research shelf, strongest failed challenger of the program.** Its lockbox was
  NEVER spent — honestly revisitable if a year of new data changes the regime picture. Banked autopsy for
  any revival: the VWAP exit whipsaws in extreme vol (2020: −$91.7k on vwap-exits vs +$84.1k on EOD-flats)
  → test a vol-conditional exit first.
- **Tally: 12 rounds across both sessions · ~2,000 configs · 2 lockboxes spent · 0 beat ORB.**
- Artifacts: session scratchpad round11_report.md, noise2_battery_report.md (+ per-condition .json,
  r11_*.py, run_c1_walkforward.py, r11_verify_yes.py).

**2026-07-17 — challenger round 13 (owner: import + test TradingView's most-boosted community
strategies): 12 verbatim Pine→Python ports, ~250 pre-registered cells — 0 of 12 survive triage.
Full running record: [`TV_SWEEP.md`](TV_SWEEP.md).**
- **The source:** the in-chart Community-scripts table sorted by boosts (BB+RSI Double 46.7K ·
  MACD+SMA200 30.4K · SuperTrend 24.4K · MACD/RSI-oversold 17.6K · PMax 16.6K · Hull Suite 14.2K ·
  AO+Stoch 13.5K · Golden Cross 10.9K · Flawless Victory 10.8K · EMA-cross 10.7K · Ichimoku-combo
  10.3K · RSI-Divergence 9.8K; 3Commas Bot + Ultimate Strategy Template skipped as non-strategies).
  Sources pulled verbatim (pine-facade; #4 from the author's GitHub — TV source protected); ported
  to 12 plugin files with TV-parity fills (close-signal → next-open, real stop-order semantics),
  roll-seam guards, and per-port hand/replay verification (ORB #125 anchor reproduced exactly in
  every triage run).
- **Kill summary (NQ 5m deciding, NQ/ES 1m+5m breadth):** as-shipped configs flat-to-negative
  everywhere (BBRSI −$171k; EMAX −$98k/5m and −$761k/1m; AOSTOCH negative on all four datasets;
  best published read anywhere = GOLDX MAR 2.45). Every family's best refined corner is the SAME
  long-only drift shelf (MAR 3–7.8, PF 1.2–1.6, corr vs ORB ≈ 0) — below the MAR ≥ 8 bar; the
  round-9 "long-only buy-weakness / shorts never pay" meta-finding reproduced 8 more times. High
  win rates (67–72%) are all stop-less dip-holding with 85–150-pt average losers. ICHIHULL's
  famous TV backtest is a `security()` repaint — the honest port is a coin-flip. **No family
  reached walk-forward; all 12 lockboxes sealed/unspent.**
- Notable side-settlement: **SUPERTREND 1.0/2.0's "not strongly validated" is now a measured
  verdict** — the verbatim Kivanc port (`SUPERTREND_3_0.py`) has no honest edge (0/24; ES 5m and
  both 1m feeds negative).
- **Tally: 13 rounds · ~2,250 configs · 2 lockboxes spent · 0 beat ORB. Three public-strategy
  sources now fully dispatched (web shortlist · web deep-dive ×2 · TV top-boosts).** Next-edge
  paths unchanged: more instruments (owner data decision) · order-flow (~Oct 2026) · owner ideas.
- Artifacts: `TV_SWEEP.md` (prereg + per-strategy records) · 12 committed ports in
  `augur_strategies/` · session scratchpad r13/ (driver + per-strategy JSONs, tv_sweep/ pine pulls).

### Other strategies
| # | Strategy | Type | Status (2026-06-20 screen) |
|---|---|---|---|
| 1–4, 9–12 | ENGU 1.1.20 / 1.1.21 / 1.2.1 / 1.3.1–1.3.5 | engulfing reversal | mostly WEAK/FAIL; 1.3.4 the least-bad (WEAK) |
| 5–7 | REVERT 1.0 / 1.1 / 1.2 | mean reversion | FAIL |
| 8, 16 | VWAP FADE 1.0 / 2.0 | fade stretch from VWAP | FAIL / weak |
| 14, 15 | SUPERTREND 1.0 / 2.0 | ATR trend-follow | ❌ settled by round 13: verbatim port (`SUPERTREND_3_0.py`) has no honest edge (0/24 cells) |
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
- `augur_engine/trial_cache.py` + `window_delta.py` — **#26 incremental reuse (SHIPPED
  2026-07-22)**: exact-hit per-config result cache (env `AUGUR_TRIAL_CACHE`, ON in the
  runner; `♻` chip on Builder launch rows) + data-prep memo + EOD-flat window-extension
  delta (dormant until a strategy sets `STATELESS_AT_EOD=True`). Spec + status:
  `docs/INCREMENTAL_BACKTEST_REUSE.md`.
- `augur_strategies/ORB_3_0.py` — the deployable ORB (formerly ORB_SIMPLE_1_0.py).
- `augur_engine/reconcile.py` — **backtest↔platform reconciler core** (importable). Turns an
  engine run into a normalized blotter and diffs it against a TradingView "List of Trades" *or*
  a NinjaTrader Strategy Analyzer export: tolerant CSV parsing (file *or* text), auto tz/DST
  offset detection, entry-time matching, and a diagnosis engine (fees, ETH-vs-RTH extras,
  contract-roll price offset, 1-bar entry-fill shift, side flips). `run_reconcile(...)` is the
  high-level entry. `tools/reconcile.py` is the thin CLI over it (`--tv/--nt auto` = newest
  Downloads CSV, `--from/--to` windows both sides, `--self-test`). **Live in the web app (v48.9):**
  Settings ▸ GENERAL ▸ OPEN RECONCILER — paste a TV/NT export → the runner `reconcile` command
  reruns the strategy and renders matched %, total-PnL Δ, diagnosis + the matched-trade table.
  Tests: `tests/test_reconcile.py`. **NOTE — backtest-vs-platform PARITY**, distinct from the §7
  "fills reconciliation" open item (live broker fills missing the DB).
  **Key finding (2026-07):** the ORB Pine port fills entries at the breakout bar's *close* (~35-70pt
  worse than the range level on fast moves) — a Pine `process_orders_on_close` limitation, not
  fixable cleanly; the ENGINE is authoritative on fills (use TV Bar Magnifier to close it). Full-year
  NQ 5m reconcile: 218/248 matched (88%), median Δ $1.87/trade.
- `method_stack.html` — the stack board (the visual of this doc).
- `index.html` — the deployed web app; `const VERSION` = deploy version.
- Deploy = push to `main` (GitHub Pages, ~10 min CDN). Runner executes queued jobs.

---

## 7. Open items / next up

🎉 **Every research/method pill is now LIVE** (41/41). The only remaining item is operational:
1. **fills reconciliation** (§1) — reconcile web/mobile NinjaTrader (+ Webull) fills that skip
   the local DB. *Needs your live broker data — do this one WITH the owner present.*
2. **Order-flow program (10s delta feed)** — accumulating since 2026-06-23 (`EdgeLogOHLCExport`). First
   bar-level probe (2026-07-14, ~113k 10s bars/instrument): delta carries a REAL short-horizon signal but it
   is **mean-reversion, not momentum** (aggressive buying → small negative next-bar return; strongest cell
   ES/ETH trade-imbalance @10s, stride-Spearman −0.041 ≈ 6× the noise floor; decays to noise by ~3 min;
   net-negative to trade directly at 10s costs). 21/96 tested cells clear the noise bar, all in one
   economically coherent corner → not multiple-testing noise. **Verdict: keep collecting.** Future use =
   entry-timing/fill improvement and gate features at longer horizons once months of data exist — not a
   standalone strategy. Revisit with a real study at ~3–6 months of data.
3. **⬜ PROPOSED (owner question 2026-07-20) — OOS-checked champion selection (train/validate/test)**:
   today the champion = best realism-gated IN-SAMPLE config (plateau-informed); a stronger search
   sharpens IS optima and widens the IS-to-OOS gap (winner's curse — exactly what run #167's PBO
   gate caught). Proposal: take the top-K (~5) plateau-distinct IS configs, score EACH across the
   walk-forward folds (legitimately usable for selection), crown the best FOLD-OOS performer, and
   only the crowned config gets the single lockbox look. Selection on the LOCKBOX top-5 would be
   the trap (spends the holdout, 5 looks instead of 1) — WF folds are the correct middle tier.
   Report shows the K-way IS-vs-WF-OOS candidate table so IS-max vs OOS-best is visible.
4. **⬜ TODO — steered Auto-Validate rerun, ORB 3.1** (added 2026-07-19): model-steered search is ON
   for every Auto-Validate; the ORB A/B found an in-sample region random never reached (+66%, an
   aggressive 6R corner). Rerun ORB 3.1 through the full gauntlet with steering. Brief: `ORB.md` §10.
4. **⬜ TODO — steered Auto-Validate rerun, ENGU-Q 1m** (added 2026-07-19): same rationale — rich
   param space, steering benefits scale with knob count; 1m data = slower trials, budget accordingly.
   Brief: `Trading/ENGUQ_DB/ENGUQ_STRATEGY.md` (TODO section at the end).
5. **⬜ NEXT UP (owner-flagged 2026-07-19) — P3 interaction-aware expansion**: let the 2L knob-pair
   map inform which ranges the auto-widener grows JOINTLY — the 2-D upgrade of the owner's own #30
   re-check-the-plateaus idea (`docs/SURROGATE_DISCOVERY_DESIGN.md` §7 P3). *(build in progress)*
6. **⬜ TODO (owner-approved 2026-07-19) — TabPFN as a 6th bake-off model**: a transformer
   pre-trained for TINY tabular datasets — the ~300-config bake-off is exactly its habitat, the
   one Carl §3 model that is genuinely new vs the five families already in the roster. Needs the
   `torch` dependency (owner has approved adding it to the TODO; install happens at build time).
7. **⬜ TODO (owner idea 2026-07-19) — 2L model-picks equity overlay**: chart each ML model's
   verified best-pick as its own equity curve on ONE chart (2A-style overlay, one colour per model,
   the search-best config as reference) so the five models compare visually, not just as scorecards.
   Needs engine support first: the ground-truth backtest of each model pick must SAVE its
   (downsampled) equity curve into the surrogate block — currently only the metrics are kept.
8. **✅ SHIPPED IN FULL 2026-07-22 (engine v64.13 · chart v64.23) — ML-gate before/after equity curves (report chart 3B)**.
   Engine done: `gate_trades` saves `summary.equity = {cum_ungated, cum_gated, n}` (both curves on the
   SAME trade-sequence grid — the gated line steps flat where the bouncer skipped — POINTS, ≤300 pts
   each via the new shared `analytics.downsample_curve`, which open item 7 should reuse) and
   `gate_validate` attaches the same block at `out.equity` for the CHOSEN candidate over the full
   span incl. lockbox (attached even on the "ungated wins" verdict). Verified end-to-end on NQ
   2022+: single-gate finals match totals (10,426.6 / 6,502.0 pts, 300 pts); bake-off path populated
   on the ungated-wins branch. Runner restarted, so runs from now on carry the curves; older runs
   (incl. #170) never will. **First PRODUCTION doc: run #173** (2026-07-22, same-window+master rerun
   of #170, pinned 2010-06-07→2026-07-16 on `NQ 5m RTH - no-adj`; champion params/PnL IDENTICAL to
   #170 — pin rule held): `gate_validate.equity` n=692 trades, 300 pts/curve, ungated final 21,333.2
   pts vs gated 18,440.0 (logistic@0.55, verdict "LOCKBOX FAILED — gate lost to ungated OOS"), PLUS
   `wf_alt_folds` ×8 (rolling) for the 1C ANCH/ROLL toggle. ♻ trial cache reused 97.2% (2,776/2,856)
   — 9.5 min vs #170's 22.5. **✅ UI half shipped v64.23**: `gateEquityHtml` draws chart **3B GATE
   EQUITY** in RESULTS §3 directly under the before/after cards — grey = every trade, coloured (by
   the verdict colour) = gated stepping flat on skipped trades, tinted band = running $ gap,
   endpoint totals inside the plot (1A convention), fmtAx axes, x = trade # in time order. Runs
   without saved curves show a one-line re-run-to-populate note (2H/2L pattern). Verified by
   extracting the served v64.23 function and rendering it against run #173's real curves in the
   deployed page (endpoint labels NO GATE $427k / GATED $369k ≡ doc finals; 3 paths; label
   anti-collision 12px). *Original brief kept below for reference.*
   - **What**: the report's §3 ML GATE shows only summary NUMBERS for gated vs ungated (net $, PF,
     max DD). Make the engine also save the two **equity curves** — the champion taking EVERY
     trade, and the same champion with the gate skipping trades — so the report can overlay them
     as a new chart **3B** under the gate's before/after numbers.
   - **Why**: the totals say the gate helped by $X but not WHEN. The overlay shows where the two
     lines separate: gap from dodging ONE bad stretch = luck (do not trust the gate live); gap
     widening steadily across years = a real filter. Same spread-vs-concentrated logic as report
     chart 1D, applied to the gate's value-add.
   - **Where**: `augur_engine/ml_gate.py` — `_summ` (~line 80) already computes cum PnL and
     max-drawdown from the per-trade `pnls` list, then discards the running curve. Save a
     **downsampled** cumulative curve (cap ~300 points, mirroring how `V.equity` is kept) into
     BOTH the gated and ungated summary blocks, for the single-gate (`ml_gate`) path AND each
     chosen candidate of the `gate_validate` bake-off path. Watch the Firestore 1 MiB run-doc
     limit — downsampling is mandatory, and open item 7 above needs the same
     save-a-downsampled-curve helper, so build it shared.
   - **No runner change needed**: `api/runner.py` already copies the whole `ml_gate` /
     `gate_validate` blocks into the run doc, so curves riding inside them arrive for free.
   - **UI half**: the EDGE-LOG UI session draws chart 3B once the data exists (report redesign
     ledger item 18). Existing runs (incl. #170) will never have the curves — only runs made
     after the engine change can draw the overlay.
9. **⬜ TODO (owner-approved 2026-07-22) — per-section REGIME buckets (report chart 1F,
   ledger item 66)**. *Self-contained brief — buildable cold by an engine session.*
   - **What**: the engine currently saves ONE regime table per run (`regime`: vol / trend /
     day-of-week / time-of-day buckets of the champion trades — whole-run when the
     full-window champion pass ran, else the in-sample slice). Compute and save the SAME
     bucket tables for each validation section so the report 1F card can switch slices:
     `regime_is` (in-sample slice), `regime_wf` (concatenated walk-forward out-of-sample
     trades), `regime_lb` (lockbox trades). Keep the existing `regime` field as-is (it is the
     TOTAL / whole-run table and stays the default fallback for old-run rendering).
   - **Why**: "the strategy makes its money in high-vol trend regimes" is only trustworthy if
     it also holds on UNSEEN data — the whole-run table is dominated by the in-sample years.
     A WF-slice regime card shows whether the regime profile SURVIVES out-of-sample, the same
     honesty upgrade 1G/1H already have via their WF/LB slices.
   - **Where**: the regime bucketing already exists as a function (it produces `rg.vol` /
     `rg.trend` / `rg.dow` / `rg.tod` rows with n / pnl / pf per bucket) — call it on the
     per-section trade lists that the validate pipeline already has (the same slices used for
     `win_dist_wf` / `win_dist_lb` / the in-sample stats). Wire the three new keys through
     `augur_engine/validate.py`'s return dict AND `api/runner.py`'s run-doc saver (the saver
     already carries `win_dist_wf/lb`, `mae_mfe_wf/lb`, `champ_dist_scope` since 2026-07-22 —
     add the three regime keys next to them; do NOT forget the runner half, three save-layer
     omissions have burned us already).
   - **Watch**: lockbox trade counts are small (run #173: 38) — buckets with n under ~5 are
     noise; save them anyway, the UI greys thin buckets.
   - **UI half** (EDGE-LOG session, after data exists): 1F gets its OWN scope toggle (owner
     2026-07-22 — NOT shared with the 1G/1H switch), options IS / WF / LB / TOTAL, with TOTAL
     backed by the existing `regime` field and the DEFAULT. (WF here = ALL the walk-forward
     out-of-sample trades concatenated across the folds, not a single fold.)
10. **✅ SHIPPED 2026-07-23 (web v64.30, commit 02fd1d7) — save the FULL config population for
    the report (ledger item 78)**. Engine: a curve per RECORDED config (search + auto-expand
    probes; int-rounded via `downsample_curve(ndp=None)`, ≤110 pts, `_ETOP_MAX=400` work cap +
    400 KB byte guard), `dist` REBUILT from the post-expansion record set (it was left at the
    pre-expansion sample — why 4B saw 73 of 171 on #173), caps raised (dist 400→4000, points
    400→1200), honest counts `equity_top_cap {saved, tested}` + `n_evaluated` (NOTE: `n_combos`
    is `n_trials×2` — an ESTIMATE, not a count; the UI should switch "M tested" to
    `n_evaluated`). DSR loop reuses the curve backtests (40 fewer). 537/537 tests pass.
    **First production doc: run #174** (pinned #170-window rerun, champion bit-identical again):
    171/171 curves (was 50), dist ≡ points ≡ n_evaluated = 171, doc 245 KB = 23.4% of cap,
    all item-18 + v64.19 fields intact — #174 supersedes #173 as the fully-loaded test doc.
    *Original brief below.*
    - **What**: the report can only draw what the run doc stores, and today that is SAMPLES:
      top-50 equity curves (`equity_top` — chart 2A), ~171 param points (`points` — 2B/2C),
      ~73 config PnLs + Sharpes (`dist` + the DSR sample — 4B and 1I). The owner wants 2A and
      4B to show ALL tested configs (all 300 on #173-class validates). Raise the caps: an
      equity curve for EVERY tested combo, and the FULL `dist` / `points` arrays.
    - **Size budget (why the caps exist)**: Firestore run docs hard-cap at 1 MiB. 300 curves
      × ~110 downsampled points × int-rounded values ≈ 150-200 KB — feasible. Round to whole
      points (no floats), downsample to ~110 pts/curve, and guard: if the doc would pass
      ~800 KB, fall back to a proportional cap and save `equity_top_cap` so the UI can keep
      saying "top N of M saved" honestly.
    - **Where**: the equity_top / dist / points sampling in the search stage
      (`augur_engine/auto.py` / optimize.py — wherever the top-N cut happens);
      `api/runner.py` passes the fields through unchanged if the names stay.
    - **UI half**: none needed — the 2A slider already spans every stored curve and reads
      "N/N saved · M tested"; 4B bins follow the sample size. Both grow automatically.
11. **⬜ TODO (found 2026-07-23 on run #174) — NEIGHBOUR ROBUSTNESS must nudge on the
    POST-auto-expand grid (report chart 4A, ledger item 109)**. *Self-contained brief.*
    - **What**: `run_auto`'s neighbour builder (`augur_engine/auto.py` ~line 1143) derives each
      param's ±1-step candidates clamped at the **DECLARED** `DEFAULT_PARAMS min/max` — it
      ignores any range auto-expand widened mid-run. On #174, `ibs_entry` winner 0.4 = the
      declared max, so the +1 cell came back None ("no step above") even though auto-expand
      had already TESTED 0.45 and 0.50 (they are in `points`). Clamp the candidates at the
      **post-expansion** range instead (fall back to `hard_min`/`hard_max`, then the declared
      bounds when no expansion ran). Old docs cannot backfill; the UI already renders a
      missing cell honestly as "edge" (web v64.35).
    - **Also noticed (smaller)**: the expander's per-round taper verdict and the FINAL
      full-population PDP boundary flag can disagree — #174 logged `ibs_entry` "tapered,
      interior peak 0.35" yet the final curve argmaxes at the 0.5 edge (+15% slope ⚠). With
      round budget left (1 of 2 used), a cheap fix: re-check the taper verdict against the
      final curve and spend the remaining round if it still flags (hard_max still binds —
      0.5 is TTIBS's declared strategy-identity cap, so ibs_entry specifically can never go
      further by design).
    - **Anchor mismatch (same fix batch)**: 4A's `neighborhood` anchors on run_auto's raw
      in-sample $ champion (`bp0` = Stage A `best`, #174: hold_cap **6**), but the report
      headline champion is the Stage A.5 `_select_oos_champion` re-pick (#88 — top-5 IS
      configs re-ranked by their walk-forward OOS results; #174: hold_cap **8**, and
      plateau_pick says 9). Either re-run the nudge test on the FINAL champion after A.5,
      or keep the current anchor and let the UI note stand (web v64.36 already labels the
      winner column "raw in-sample $ champion at nudge time"). Re-anchoring is the honest
      fix — 4A claims robustness for a config the report does not headline.

**Current Auto-Validate pipeline (as of 2026-07-20, for orientation):** 🎯 steered search (random
seed ~40% of trials → GP-aimed batches, #36; TPE and QRF brains available) → auto-expand of
edge-pinned rising knobs (#26/#30) + interaction-aware expansion (#72 P3) → plateau pick (broad
high ground, not argmax) → 2L ML bake-off read-out (6 models incl. pyGAM + QRF, CV-graded as a %,
every pick verified by one real backtest, #31/#35; each pick graded vs sampled territory, #91)
→ knob screen vs a planted noise probe (#39) → realism gates → #88 OOS-checked selection (top-5
IS candidates arbitrated on anchored WF fold slices; the crown goes to summed fold-OOS PnL, not
IS argmax) → walk-forward (anchored+rolling) → one-look lockbox + #94 verdict power (could this
few trades even detect the claimed edge?). Discovery maximizes in-sample by design; the WF folds
arbitrate the crown; ONLY the lockbox decides deployability.

*(✅ SHAP · ensemble top-K · adversarial validation · conformal band · causal check ·
synthetic scenarios all shipped 2026-07-04 — see Changelog.)*

### Carl master-notebook FULL re-read (2026-07-19, live page) — discovery-relevant finds
Confirmed: Carl has NO optuna/TPE/Bayesian-optimization notebook — his tuning coverage is
GridSearchCV + "Automatic tuning of XGBoost with XGBTune" (our per-model mini-GridSearchCV in
the bake-off is the equivalent). New candidates ranked by param-discovery value:
- **Quantile Regression Forests (QRF)** — ✅ BUILT 2026-07-19 (owner go): 6th bake-off roster
  model (`quantile-forest` dep) AND 3rd steering brain (`steer_method='qrf'`, median + UCB on
  tree-native quantile spread). Real-data A/B complete (150 trials, seed 42, lockbox held out) — FULL 4-WAY: TTIBS random 19,738 / GP 21,440 / TPE 21,205 / QRF 21,205 pts; ORB 3.1 random 14,418 / GP 24,002 / TPE 25,215 / QRF 24,989 pts. All three steering brains within ~1-5% of each other, all crush random; GP stays default. Original note: a
  map-maker with NATIVE uncertainty (quantiles) — tree-based so it handles categoricals and is
  cheap; could join the bake-off roster AND become a 3rd steering brain (UCB needs an
  uncertainty estimate; QRF provides it without the GP's O(n³)).
- **Extrapolation guard** (his §11 "Do not stray out of the forest!") — ✅ BUILT 2026-07-20
  (#91, owner go): `extrapolation_check` in `surrogate.py` grades every bake-off model pick
  against the ACTUALLY-SAMPLED records (never the auto-expand-widened bounds) — "extrapolated"
  (outside the sampled per-param range), "thin" (< 5 sampled neighbours within a normalized
  L∞ 0.25 ball), or clean. 2L rows show it as a `terr` column (⚠ / ◌, v62.1). The QRF steering
  brain also zeroes the exploration bonus (σ→0) for out-of-range candidates — a tree's spread
  out there is an artifact, not honest uncertainty (GP/TPE untouched by design). New runs only.
  Original rationale: tree models cannot extrapolate beyond their training range, so RF/XGBoost
  surrogate predictions inside auto-expand-WIDENED ranges are untrustworthy until sampled;
  ground-truthing already protects the headline, this makes the 2L cards honest about the rest.
- **MAPIE conformal intervals on surrogate predictions** (§4) — MEDIUM: put honest error bars on
  the 2L predicted-best ("predicted $261k, 90% interval $210k–$310k").
- **Venn-ABERS calibration** (§4, his prize-winner) — MEDIUM (gate-side): stronger probability
  calibration than the current isotonic headroom check.
- **Statistical POWER of the edge test** (§10 t-test/p-value/power) — ✅ BUILT 2026-07-20
  (#94, owner go): `power_stats` in `analytics.py` (pure stdlib) computes the lockbox's
  minimum detectable per-trade edge (MDE at one-sided α=0.05 / 80% power) and the achieved
  power at the champion's own claim (its optimize-window mean per-trade net PnL, points,
  from a fresh window-clipped backtest so the claim never touches lockbox trades). Persisted
  as `power`, rendered as the 📏 Verdict-power line under the lockbox (POWERED /
  UNDERPOWERED, v62.1). Pairs with the DOF gauge: DOF = was the SEARCH sample adequate;
  power = was the VERDICT sample adequate. New runs only.

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
- **2026-07-23** — **§7 item 10 SHIPPED (v64.30) + run #174 = the new fully-loaded test doc.**
  Full config population saved: curve per recorded config (int, ≤110 pts, 400-curve work cap,
  400 KB byte guard), dist rebuilt post-expansion (fixes the 73-vs-171 divergence 4B showed),
  `equity_top_cap`+`n_evaluated` honest counts (n_combos = trials×2 = estimate). Run #174
  (third pinned #170-window rerun, champion bit-identical, ♻ 97.2% reuse, ≤9.5 min): 171/171
  curves, dist≡points≡n_evaluated=171, 245 KB doc, item-18 gate curves + wf_alt_folds + the
  v64.19 WF/LB slice fields all present — supersedes #173 for UI verification.
- **2026-07-22** — **§7 open item 10 ADDED (owner-approved): save the FULL config population**
  (equity curves for every tested combo + full dist / points, int-rounded + downsampled to
  respect the 1 MiB run-doc cap) so report charts 2A / 4B can show every tested config
  instead of top-50 / 73-sample views.
- **2026-07-22** — **§7 item 8 COMPLETE (v64.23): chart 3B GATE EQUITY shipped — item CLOSED.**
  New `gateEquityHtml` in index.html renders the overlay in RESULTS §3 under the before/after
  cards, replacing the "coming once the engine saves both curves" placeholder; graceful re-run
  note on curve-less runs. Verified against run #173 by running the served function on the real
  doc curves in the deployed page (finals ≡ Firestore; geometry asserted). Engine v64.13 +
  production data (#173) + chart v64.23 = the full ledger-item-18 pipeline done.
- **2026-07-22** — **§7 open item 9 ADDED (owner-approved): per-section regime buckets**
  (`regime_is` / `regime_wf` / `regime_lb` alongside the existing whole-run `regime`) so the
  report 1F card can show whether the regime profile survives out-of-sample. Engine + runner
  halves specified in the brief; UI half waits on the data.
- **2026-07-22** — **§7 item 8 DATA LIVE IN PRODUCTION: run #173 carries the gate curves.**
  Same-window+master rerun of #170 (pinned 2010-06-07→2026-07-16, `NQ 5m RTH - no-adj`) queued via
  the backtests channel and completed in 9.5 min (♻ 97.2% trial reuse vs #170's 22.5 min cold —
  first big validate-rerun win for the §5 trial cache). Champion params + headline PnL IDENTICAL to
  #170 (window-pin rule held; engine changes proven purely additive). Doc now has BOTH missing
  blocks: `gate_validate.equity` (n=692, 300 pts/curve) and `wf_alt_folds` ×8 rolling (1C toggle).
  Chart 3B + the 1C ANCH/ROLL toggle can now be built against run #173.
- **2026-07-22** — **§7 item 8 ENGINE HALF SHIPPED (web v64.13): gate equity curves saved.**
  New shared `analytics.downsample_curve` (≤300 pts, last point exact, flat lists — Firestore-safe;
  built shared so §7 item 7's model-picks overlay reuses it). `ml_gate.gate_trades` now emits
  `summary.equity {cum_ungated, cum_gated, n}` on the shared trade-sequence grid (gated steps flat
  on skipped trades); `gate_validate` attaches the same at `out.equity` for the chosen candidate,
  full span incl. lockbox, even on the "ungated wins" verdict. No runner change (blocks copied
  wholesale). Verified: NQ 2022+ single-gate finals ≡ totals; bake-off branch populated; 41 sibling
  contract tests pass. Runner restarted → curves on all NEW gate runs. UI half (chart 3B) = redesign
  ledger item 18, pending. *(Implementation by Sonnet subagent, supervisor-reviewed.)*
- **2026-07-22** — **§7 open item 8 ADDED (owner-approved): ML-gate before/after equity curves.**
  Engine brief for saving downsampled gated + ungated champion equity curves out of
  `ml_gate.py _summ` so the run report can draw the gate-value overlay (chart 3B). Also of note
  (shipped same day, runner side): `api/runner.py` was silently dropping the engine's
  `wf_alt_folds`/`wf_alt_mode` (the comparison walk-forward scheme's per-fold rows) when saving
  runs — fixed, runner restarted; saved validates made before 2026-07-22 (incl. #170) need a
  same-window re-run to backfill their 1C anchored/rolling toggle.
- **2026-07-20** — **#91 extrapolation guard + #94 verdict power SHIPPED (engine + web v62.1):**
  every 2L model pick is now graded against the ACTUALLY-SAMPLED territory (`terr` column:
  ⚠ extrapolated / ◌ thin / blank = solid; tree models cannot predict beyond what they saw), and
  the QRF steering brain gives out-of-range candidates NO exploration bonus (σ→0). The run report
  gains a 📏 verdict-power line under the lockbox: minimum detectable per-trade edge (one-sided
  α=0.05, 80% power) vs the champion's own optimize-window claim → POWERED / UNDERPOWERED.
  Full suite 453 passed. Both are new-runs-only (old reports render unchanged).
- **2026-07-20** — **#88 OOS-checked selection DEMONSTRATED (run #168):** the #167 job re-run
  (500 steered trials, pinned window 2010-06-07 → 2026-07-16, `select_oos_topk=5`). The IS-max
  candidate — ibs_entry 0.3 / hold_cap 6, the very config #167 crowned — was DETHRONED
  (`is_max_crowned=False`): anchored-fold OOS arbitration crowned 0.4 / hold_cap 8 instead, and
  the one-look lockbox paid **$87,936 PF 1.56 (59 trades) vs #167's $35,083 PF 1.21** — ~$7.5k of
  in-sample given up for +$52.9k of holdout. Top-5 candidates + downsampled equities persisted
  (feeds the future 1A-style overlay, #88b). TTIBS itself stays CLOSED — this run tested the
  machinery, not the strategy.
  the 2L bake-off now runs 5 models (pyGAM added, `c12ad0d`); the knob screen adds a permutation
  vote + a planted random-noise probe with per-knob margins (`12224a1`); and **P2 GP-steered
  sampling is ON for Auto-Validate** (`fadd227`, validate.py Stage A) after passing the
  pre-registered 2-family acceptance A/B at equal budget/seed with the lockbox held out —
  TTIBS: steered found a +8.6% better IS optimum (21,440 vs 19,738 pts); ORB 3.1 (12-knob
  intraday surface): +66% (24,002 vs 14,418 pts); 0 GP-fit fallbacks in either. Steering
  changes how well the search maps the surface, never what passes — WF/lockbox gates unchanged.
  Full design + evidence: docs/SURROGATE_DISCOVERY_DESIGN.md.
- **2026-07-18** — **Param-discovery pipeline upgrade (#25–#30, owner-driven from the TTIBS 2C PDP
  observation that knobs peaked at their tested-range edges still rising):** (1) **boundary-peak
  detector** in `pdp_plateau` (5df5a76) — any numeric knob whose smoothed optimum is pinned at the
  min/max tested value and still rising is flagged `search_truncated`, stored on grid/auto/validate
  runs (validate previously DROPPED `plateau_pick` — also fixed); (2) **2C panel badge** (web v58.4,
  4736cbe) — amber ⚠ per-knob + panel banner, with a client-side fallback so it renders on older
  saved runs (live-verified on TTIBS #161: 3 knobs flagged); (3) **auto-expand-and-resample**
  (b6261de) — a flagged knob's range auto-widens (+50%/round) and re-samples until the curve tapers;
  (4) **logical `hard_min`/`hard_max`** DEFAULT_PARAMS convention (817698d, TTIBS first: ibs_entry
  ≤0.5 = strategy-identity line, mon_drop ≤0.10, hold_cap ≤20) so expansion roams the meaningful
  domain, not an arbitrary cap; (5) **iterative joint expansion** (5efd98f) — coordinate-descent
  re-flags ALL params each round, chasing knobs UNLOCKED by another's widening (proven on TTIBS:
  hold_cap emerged mid-run, tapered interior at 10; converged in 2 rounds), bounded by a permanent
  no-re-add set + global-round cap. All IS-only — the lockbox deploy gate is unchanged. NOTE: the
  plateau model remains ADDITIVE 1-D (no true interactions); the proposed fix is
  `docs/SURROGATE_DISCOVERY_DESIGN.md` (#31, 8d1b62e) — multi-surrogate bake-off (quadratic/RF/
  XGBoost/GP, CV-scored, per-model cards, ground-truthed picks) — awaiting owner go on roster/deps/
  phasing.
- **2026-07-17** — **Challenger round 13 (owner-directed TV top-boosts sweep): 12 most-boosted
  TradingView strategies pulled verbatim, ported (`augur_strategies/` — BBRSI, MACD200,
  SUPERTREND_3_0, MACDRSI, PMAX, HULL, AOSTOCH, GOLDX, FLAWLESS, EMAX, ICHIHULL, RSIDIV), and
  triaged across NQ/ES 1m+5m under house rules — 0 of 12 survive; all lockboxes sealed.**
  As-shipped configs flat-to-negative (top-boosted BBRSI −$171k NQ 5m); every refined best-corner
  = the same long-only drift shelf (MAR ≤ 7.8 < 8 bar); ICHIHULL's TV fame = `security()` repaint;
  SUPERTREND family verdict settled (no honest edge). Boosts ≠ edge, now measured. New running
  record: `TV_SWEEP.md`. Tally 13 rounds / ~2,250 configs / 0 beat ORB. Detail §3.
  *Addendum (same day):* round-13 artifacts made durable for individual pickups — driver
  `tools/r13_triage.py` + all grid/gate JSONs in `tools/r13_results/`; `TV_SWEEP.md` §4.2 KPI
  matrix + §5 pickup guide (ranked: EMAX 20/100-long → BBRSI 16/50-long → PMAX SMA20×2-long;
  stage-2 battery pre-registered incl. a new mandatory always-long drift baseline B0).
  *Deep-tune addendum (item 18, `tools/r13_deeptune.py`):* owner asked whether the promising
  ones were tuned with our BEST tooling, not just as-shipped + small grid. Ran the real
  Auto-Optimize search (`augur_engine.auto` sampler over full param ranges, 400 trials) on the
  **top 3 × all core-4 (NQ/ES × 1m/5m)**, lockbox HELD, champion selected on TRAIN(75%) then
  scored on honest OOS(25%). **0 of 12 pass** — the optimizer hits MAR 8.8–15.2 in-sample and
  every one collapses to OOS MAR ~0.4–3.5 (best = EMAX NQ 5m 3.54, still < half the bar). Textbook
  overfit; the grid had already found the honest ceiling. Verdict holds under best tooling;
  **round-13 lockboxes closed unspent.** Detail: TV_SWEEP.md §4.3.
- **2026-07-16** — **Paper-forward Phase 1: `tools/paper_forward.py` — dual-leg signal log + status page, VIX log column, gap-skip rule, stale-data guard.**
- **2026-07-16** — **ENGU-Q Round 4 (Monte Carlo sizing, cost stress, 5m restate = size-knob not diversifier, w=1.0 DD-optimal, stop/overnight/cooldown/event descriptives — zero config changes).**
- **2026-07-16** — **Challenger round 12: NOISE-2 (wide-band Zarattini envelope) = the program's strongest
  challenger — regime-healthy on NQ (MAR 8.14, 2010–17 positive, corr 0.22), passed 4/5 pre-registered
  battery gates (WF 5/6 · neighborhood · family · bootstrap P=0.0000) — then FAILED ES transfer (PF 1.12).
  No lockbox fired; shelved with holdout intact.** DRIVE closed permanently. Tally 12 rounds · ~2,000
  configs · 0 beat ORB. Detail §3.
- **2026-07-16** — **Engine fix (web run #160 → #161): `run_auto` never passed bar timestamps (`index`)
  to index-aware strategies** — TTIBS/REPLAY returned None on every trial, so Auto-Optimize/Auto-Validate
  on them degenerated to 0 valid configs (#160: FAIL 2/5, IS PF 0.00, $0, empty top-configs). All six
  evaluator sites in `augur_engine/auto.py` now mirror `engine.run_backtest`'s declare-and-pass pattern;
  verified with an 8-trial run_auto (real champion returned); runner restarted. Corrected **run #161
  Auto-Validate (XL, 18-mo lockbox): PASS 7/7, IS PF 1.97, lockbox HELD +$86.3k / PF 1.55** — read with
  the round-7 addendum caveats (close-fill champion, different holdout, G3–G6 never applied): the
  pre-registered round-7 one-shot FAIL remains the family verdict. Legacy `optimizer.py` has the same
  missing-index pattern (line ~2117) — noted, not fixed (web pipeline is canonical).
- **2026-07-15** — **Round 11 (web deep-dive round 2 + ORB conditioning diagnostic): EMPTY, decisively.**
  Untapped sources (Quantpedia/Alvarez/Quantifiable Edges/Davey/fresh SSRN-arXiv) yield nothing; a May-2026
  arXiv falsification series independently replicates our graveyard on MNQ 5m (14 families, none pass).
  ORB blotter sliced by VIX/term-structure/DOW/FOMC-CPI-NFP/put-call: **NONE graduate** — the clean VIX
  pattern (PF 2.06→1.31) is ALREADY harvested by the §5.6 risk-parity overlay (stop distance rises 3.5×
  with VIX); Wednesday weakness = 86% FOMC contamination (DOW-uninformative CONFIRMED); FOMC-day PF 1.30
  banked as a watch item (p=0.904). Every mean-shift delta fails permutation. Remaining levers: more
  instruments (owner data decision) · order-flow ~Oct 2026 · owner ideas. Detail §3 round 11.
- **2026-07-15** — **Challenger round 10 (web deep-dive): NOISE (Zarattini intraday-momentum envelope) —
  real mechanism (54/54 net-positive, corr 0.22 vs ORB), wrong regime (all top-5 REGIME-CONCENTRATED,
  three negative 2010–17, replicating the paper's own caveat). Best MAR 6.90 — no bar cleared.** Web fully
  swept twice; tally 10 rounds / 24 families / ~1,820 configs; no live challengers. Detail §3.
- **2026-07-15** — **Round 9 independent replication: a parallel 216-config fixed-band GAPFADE build reaches
  the same DEAD verdict (0/36 plateaus; wide bands fail regime-spread, IBS-conditioned cells fail
  year-concentration; best economics ~$1.8k/yr).** ⚠️ Side-split CONFLICTS with the ATR-banded run (this
  one: shorts carried 83%; that one: longs) → GAPFADE downgraded to side-agnostic noise in the
  meta-finding; TTIBS/CALENDAR/SWING still support long-only-buy-weakness. New research file
  `GAPFADE_1_0.py`; GAPFADE lockbox not spent. Detail §3 round 9 (replication entry).
- **2026-07-15** — **Challenger round 9: GAPFADE dead (MAR 0.11 — long leg +$33k, short leg gives it back);
  CALENDAR turn-of-month drift real but tiny (MAR 2.19). Web shortlist fully dispatched; with TTIBS's
  lockbox FAIL (round 7, same day) no live challengers remain.** Meta-finding confirmed 4 ways: daily-scale
  edges here are long-only buy-weakness; all short-side mirrors die. Tally 9 rounds / 23 families / ~1,770
  configs · 2 lockboxes spent. Detail §3.
- **2026-07-15** — **Round 7 lockbox one-shot: TTIBS FAIL — n=16, net −$44,320, PF 0.44 in the held-out
  year (no blowup: worst −$20.7k inside the −$25k floor). Family closed, lockbox spent.** Banked notes
  (not re-tune licenses): ES same-config was +$11.6k/PF 1.34 in the identical window; signal rate halved.
  TTIBS 1.0 stays 🔬 research, champions unchanged. **GAPFADE enters triage as round 9** per the owner's
  keep-hunting directive. Detail §3 round 7.
- **2026-07-14** — **Round 7 stage 2: TTIBS passes EVERYTHING — WF 6/6 frozen folds (WFE 1.99; the test
  DRIVE failed at 3/6), ES transfer PF 1.695 no-refit, t=3.94, DSR 0.96 — and exposes a pre-existing
  ENGU-Q reproducibility defect** (deploy config can't be rebuilt from `ENGUQ_1M_1_0.py`; even the run-149
  blotter's first trade never generates; fix leads = runs DB params + today's Pine session). Blend read
  directional until fixed: 3-leg net/DD 6.36 vs 4.16, losing years 3→2. TTIBS lockbox still sealed;
  order = fix ENGU-Q → certify blend → owner sign-off. Detail §3 round 7 stage 2.
- **2026-07-14** — **Challenger round 8: SWEEP (prior-day stop-run reversal) dead (best MAR 2.78, setup
  fires on 3–7% of sessions); LDM-0DTE probe ARTIFACT-CLOSED (placebo-controlled — the late-day edge was
  the 2020–22 COVID window, not 0DTE structure).** Tally 8 rounds / 21 families / ~1,700 configs; champions
  stand. Detail §3.
- **2026-07-14** — **Challenger round 7: TTIBS 1.0 (daily IBS buy-weakness, long-only, from the web
  "proven strategies" sweep) SURVIVES its pre-registered triage — first family past that bar since round 1.**
  n=442 / $307k / PF 1.82 / MAR 12.3 on next-open fills, all 6 gates pass on a 4-of-6-cell plateau
  (ibs_entry 0.20–0.30, hold_cap must be 6 — shorter holds are ENGU-Q-in-disguise, corr 0.44). 2022
  profitable (+$20.7k). WF + ES transfer + exact-repro corr + blend read queued; lockbox sealed. New file
  `augur_strategies/TTIBS_1_0.py`. Champions unchanged until WF says otherwise. Detail §3 (round 7).
- **2026-07-14** — **Challenger round 6 (final): GLOBEX overnight session (MAR 2.27, artifact+regime-flagged),
  WEEKLY ORB (3.82), and overnight RELAY (1.08) all dead — 0/156.** Program final tally 6 rounds / 18
  families / ~1,650 configs: the OHLCV edge inventory is fully claimed by ORB 3.1 / ENGU-Q; next edge
  requires the order-flow data (§7). Detail in §3 (challenger section).
- **2026-07-14** — **Sizing overlay live-wired (ORB.md item 4 DONE, web v55.6/v55.7) + first order-flow
  probe (verdict: keep collecting).** Run-report SIZING OVERLAY card now has adjustable lever toggles
  (rp / time-tilt / side-tilt + cap), defaults = the validated config; post-deploy verification caught a
  pre-existing gate bug that had hidden the card on all filename-style ORB runs (fixed v55.7, verified
  live on run 157). Order-flow delta probe on ~113k 10s bars: real but tiny short-horizon MEAN-REVERSION
  signal (~6× noise floor at 10s, gone by 3 min, untradeable at cost) — data collection continues; see §7.
- **2026-07-14** — **ENGUQ Pine port + first TV reconciliation (`pine/ENGUQ_1M_1_0.pine`).** Pine v5
  port of the 1m trendline-break strategy (defaults = run 149's config; `volMult` default 0 = the
  cross-check setting — TV's volume feed ≠ Databento, so the gate is validated separately). Reconciled
  vs a TV deep backtest (NQ1! 1m RTH, 2023-07-18→2026-06-30, vol off): **403 vs 400 trades, 317 matched,
  84.5% of matched EXACT (|ΔPnL| ≤ $5)** — entries at bar close reproduce to the cent (validates the
  `ta.linreg` trendline indexing + SMA-ATR + trailing exits). Matched-PnL Δ −$30.4k concentrates in ~36
  monster-move days = the documented **1-bar trailing-stop timing gap** (engine ratchets+checks the stop
  same-bar; Pine applies it next bar — e.g. 2025-04-09 engine +$589 vs TV +$26,284). Unmatched are
  near-symmetric (86/83) and **67% cascade-explained** (multi-day positions desync after one divergent
  exit — one side re-enters while the other still holds) + 4 warmup + feed knife-edges. Engine remains
  authoritative on exits. Not yet TV-tested: `vol_mult=0.8` (the run-149 gate) and anything pre-2023
  (TV has no older 1m data). Browser-automation note: blank TV charts in driven tabs = background-tab
  paint suspension (`document.visibilityState`), fixable with a JS visibility spoof.
- **2026-07-13** — **Challenger round 5: EXPAND (ATR expansion off the open) = ORB-in-disguise (89.9%
  direction overlap, MAR 16.9); VWAPT (trend-side VWAP) regime-concentrated (MAR 6.7). Both dead in triage.**
  ORB item X also resolved: 1m ORB slippage-fragile (closed), 5m champion proven robust to 1.0-pt slippage.
  Running total 5 rounds / 15 families / ~1,500 configs: champions stand. Detail §3 (challenger section) + ORB.md §4.21.
- **2026-07-13** — **Challenger round 4: SWING 2.0 reached the lockbox and FAILED it (combined NQ+ES −$13.4k,
  blow-ups both markets); LDM / ES↔NQ spread / volume-ignition all dead in triage.** The SWING-family lockbox
  is now spent. Program verdict after 4 rounds / 13 families / ~1,400 configs: nothing beats or honestly
  nearly-beats ORB 3.1 / ENGU-Q on this data; next edge requires new data. Detail in §3 (challenger section).
- **2026-07-13** — **Challenger rounds 2–3: five more concept families vs the champions — none beats the bar; negatives banked.**
  ORB-on-1m (fill-artifact wall, best MAR 30.8 vs 32.8) · MIDDAY lunch breakout (dead) · PULLBACK continuation (dead) ·
  ORB HOLDOVER (overnight strictly subtracts → flat-EOD confirmed optimal) · SWING Donchian (MAR 6.79, corr 0.22 →
  3rd-leg candidate). New data knowledge: the NOADJ quarterly roll seam (~77 pts) lands days before roll-Wednesday.
  Lockbox untouched across all three rounds. Detail in §3 (DRIVE 1.0 / challenger section).
- **2026-07-13** — **New-strategy challenge: DRIVE 1.0 (first-hour momentum) + 3 concepts triaged — champions hold.**
  Built and validated a from-scratch challenger on house rules (gap-honest fills, 0.533 pts costs, plateau
  pick, walk-forward, sealed lockbox). Triage: PDX (prior-day break) and NDAY (N-day break) DEAD, LDM
  (late-day momentum) thin, DRIVE best of 4. Deep sweep (810 configs) → deploy candidate $295k / PF 1.18 /
  MAR 8.8 pre-lockbox, corr 0.23 vs ORB. **Walk-forward FAIL** (frozen 3/6 folds; WFE 0.32–0.43; profit
  concentrated 2021+) + **ES transfer FAIL** → 🔬 research only, **lockbox not spent**, ORB 3.1 / ENGU-Q
  remain champions. New library file: `DRIVE_1_0.py`. Full detail in §3.
- **2026-07-13** — **ENGU-Q Round 2 (mgmt sweep) + Round 3 (ORB blend).** Round 2: pyramid
  sizing (add 0.3 units at trail activation) is the sole baseline-beater of 16 variants (net
  +18%, lockbox $83.6k→$93.2k) but maxDD deepens and 82% of the gain sits in the top-10 fires —
  **PARKED**, not adopted; scale-out and ATR chandelier trail both **DEAD** (no variant beats
  baseline net/DD). Round 3: ORB 3.1 + ENGU-Q 1m portfolio blend — daily-PnL correlation ~0
  (Pearson +0.07); **1:1 combo nets $835,351.08, maxDD −$60,097.59** (shallower than ENGU-Q
  alone), net/DD 13.90, **zero losing years in 17** (ORB's 2022 covers ENGU-Q's only losing
  year). Full detail in `Trading/ENGUQ_DB/ENGUQ_STRATEGY.md`.
- **2026-07-12** — **ENGUQ gap-honest fills + deploy config; ORB close_confirm.** All 3 ENGUQ TF
  files (`ENGUQ_1M/5M/15M_1_0.py`) now book gap-through stop fills at the bar's open (hardcoded,
  mirrors ORB 3.0) — prior ENGUQ results were ~35% optimistic; `breakeven_R` param added.
  Champion #149 restated on the lockbox: $70.7k / PF 1.31 (was $128.6k / 1.73). Loss-tail study:
  worst-20 all -1R stop-outs (12/20 at 09:30–09:32); only breakeven 1.5R survives honest fills;
  re-opt on the honest engine (#158) FAILED OOS (lockbox PF 1.08, DSR 0.77) → keep #149 params.
  **DEPLOY CONFIG = #149 params + breakeven_R 1.5 → lockbox $83.6k / PF 1.39 / DD -$65.6k.**
  Also completed `close_confirm` in ORB_3_1 (entry logic was a silent no-op; now mirrors ORB_3_0,
  off = bit-identical to before) — hypothesis dead at the validated config: ON collapses net
  $417k → $95k gross. Run notes updated (#149/#152/#158); details in `ENGUQ_STRATEGY.md`.
- **2026-07-09** — **Reconciler is a web feature + validated on a live TradingView run (web v48.9).**
  Moved the reconcile core to `augur_engine/reconcile.py` (importable; adds text-CSV parsing +
  `run_reconcile()` + structured `build_result`); `tools/reconcile.py` is now a thin CLI. Added a
  runner `reconcile` command and the **Settings ▸ GENERAL ▸ OPEN RECONCILER** web UI. Ran it against a
  real TradingView export of `ORB_3_0` (via the Chrome extension: added the strategy, fixed the chart to
  RTH/5m, exported). **The tool caught two silent setup errors** (chart was on ETH → 18% WR; strategy was
  on the 15-min pane not 5-min → entries 45 min late) and, once fixed, matched **218/248 (88%) over a
  full year, median Δ $1.87/trade**. Root-caused the residual $ gap to the Pine port's breakout-bar
  *close* fills (a `process_orders_on_close` limitation — engine is authoritative; corrected the pine's
  false fidelity note, recommended Bar Magnifier). See [[edgelog-reconcile-tool]].
- **2026-07-08** — **Automated backtest↔platform reconciliation (`tools/reconcile.py`).** New
  tool that automates the old manual `xcheck_orb.py` eyeball step: runs the EDGELOG engine into a
  normalized blotter (entry/exit time, side, price, PnL) and lines it up trade-for-trade against a
  **TradingView** "List of Trades" CSV and/or a **NinjaTrader** Strategy Analyzer trades export.
  Tolerant parsers (fuzzy header detection handle TV's two-rows-per-trade and NT's semicolon/
  currency/AM-PM quirks), **automatic tz/DST offset detection** (an ET-vs-UTC shift no longer reads
  as "every trade mismatched"), one-to-one entry-time matching, and a **diagnosis engine** that names
  the systematic cause of a gap from the ORB.md §7-8 rap sheet: tz offset, the ~$5.66 commission gap,
  ETH-vs-RTH extra trades, contract-roll price offset, 1-bar entry-convention shift, side flips.
  `--tv auto`/`--nt auto` grab the newest CSV from Downloads (the Chrome-export flow); `--self-test`
  forges a TV export from the real ORB blotter (+4h tz, −$5.66 fee) and confirms both are recovered.
  14 tests in `tests/test_reconcile.py` (full suite 235 pass). *Backtest-vs-platform PARITY — distinct
  from the §7 live-fills reconciliation item.* Next: drive TV's export via the Chrome extension for a
  live ORB/NQ run.
- **2026-07-08** — **PDP top-out curves + 3-D param surface in the run report (web v47.9).**
  Two new panels in §2 of every saved RUN REPORT, next to the 2H heatmap: **2J PARAM
  SURFACE 3-D** — the param→PnL surface as an isometric height map (floor = the two params
  chosen by the 2H dropdowns, which drive both charts; height + colour = avg net $ per
  cell; peak flagged in green, the argmax champion staked in yellow; never-tested cells
  interpolated from neighbours and drawn faded) — a broad ridge = robust plateau, a lone
  needle = luck. **2K PDP — WHERE EACH KNOB TOPS OUT** — 1-D partial-dependence
  mini-curves per parameter (avg net $ at each value, other params averaged out, 1-2-1
  smoothed — the same maths as the 3C.1 plateau pick), sorted by influence, green dot =
  the top-out value, "barely matters" flag for dead knobs. Both are pure SVG (no chart
  libs) and read the stored `points`, so they render **retroactively on every saved run**
  (verified on run 137's 300 stored configs: stop_frac tops out @ 0.75 — matching the
  validated ORB stop — and or_bars @ 1); the 1-D curves prefer the exact server curves
  saved with `plateau_pick` when present. Clarified in the ⓘ tooltips: the plateau pick
  maximises the SUM of the smoothed curves — deliberately NOT the raw argmax peak.
- **2026-07-08** — **Run-report parity + Auto-Optimize pills (web v46.1).** The saved RUN
  REPORT (Results → pick a run) is now the same one-stop-shop the Builder panel shows — a new
  **Robustness & Diagnostics** section renders every pill the run has: the 11 informational
  pills (adversarial · conformal · causal · synthetic · lead-lag/Granger · serial-dep ACF ·
  VIF · feature-select · edge-sig · tail-fit · seasonality), ensemble top-K + CCMP, plateau
  pick (3C.1), the ML-gate before/after card (SHAP/calibration/discrimination), the
  gate-validate **all-models bake-off table** (now with a WR column) and the previously
  invisible **sample-adequacy / DOF** value. Previously these lived ONLY in the Builder's
  transient last-run panel and ONLY for Auto-Validate runs. Renderers were extracted to shared
  functions (`pillsHtml`/`gateCardHtml`/`gvTableHtml`/`ensembleCardHtml`/`plateauCardHtml`) so
  Builder + Report stay identical. **Auto-Optimize (mode 3) + Walk-Forward (mode 4) now run the
  full pill set** via a new `analytics.run_pills` helper (shared with `run_validate`), gated by
  an **ALL PILLS** toggle in the Builder (default on; adversarial is skipped — it needs a
  lockbox). Persistence: `_persist_run` now carries `ensemble/plateau_pick/ml_gate/gate_validate`
  + the top-level pill keys, and gate-validate runs are saved to Runs history. Files:
  `augur_engine/analytics.py` (run_pills), `augur_engine/auto.py` (compute_pills),
  `api/runner.py` (flag + persist), `index.html` (shared renderers + report section + toggle).
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
