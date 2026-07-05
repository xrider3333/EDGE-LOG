# DISCRETIONARY → QUANT — project brief & handoff

**One-line mission:** turn the owner's *discretionary* trades (setups taken by feel —
ENGU, CBD, etc., logged as screenshots + OHLC + timestamps) into *quantitative,
automatable* strategies — and honestly measure, at each step, whether the discretionary
"eye" has real, tradeable edge.

> **Reading this cold in a new chat?** Read `CLAUDE.md` first (durable project context +
> guardrails), then this file. This is a *separate scope* from the core backtest stack —
> the running library of validation methods lives in `BACKTESTING_STACK.md`; the ORB
> strategy project lives in `ORB.md`. This doc is only about the discretionary→quant path.

---

## Status — where we are right now

**Shipped (commit `76e09ba`, backend-only, no site VERSION change):**

- **`augur_strategies/REPLAY_1_0.py`** — a strategy plugin that "enters" at a CSV of
  timestamps + sides *you actually traded*, then either replays your logged exit
  (as-taken) or manages the trade mechanically (stop / target / end-of-day flat). It emits
  a normal engine trade list, so it flows straight into the **ML gate** and
  **`run_validate`** (edge-significance, conformal band, etc.) with zero extra wiring.
- **`augur_engine/engine.py`** — `run_backtest` now hands the bar-timestamp `index` to any
  strategy that declares an `index=` parameter. No-op for every existing strategy.
- **`augur_uploads/replay/_TEMPLATE.csv`** — the CSV format (this folder is gitignored, so
  it stays local).

**Verified end-to-end** on the NQ 5m master (316,983 bars, 2010–2026): 60 synthetic entries
→ trade list → gate (60→33 trades) → edge-significance. As a control, **60 *random* entries
correctly returned "no edge"** (p=0.12, verdict *negative*) — the test won't flatter you.

**Not built:** any web-UI card for REPLAY (runs via the Python engine / optimizer app for
now); the timestamp-vs-rule *overlap* report (see Next steps); anything torch/vision.

---

## How REPLAY works (usage)

1. **Make a CSV** in `augur_uploads/replay/` (see `_TEMPLATE.csv`). Columns are
   case-insensitive; only the first two are required:

   ```
   timestamp,side,exit_time,stop_pts,target_pts
   2024-03-11 09:35,long,2024-03-11 10:05,,
   2024-03-12 14:10,short,,20,40
   ```

   - `timestamp` / `side` — required. side = long|short|buy|sell|1|-1.
   - `exit_time` — optional. **Present → "as-taken"** (replays *your* real exit → your
     actual P&L). **Blank → "mechanical"** (takes your entry, exits by rule).
   - `stop_pts` / `target_pts` — optional per-row overrides (in POINTS) of the mechanical
     stop/target.

2. **Run it** (Python engine):

   ```python
   from augur_engine import engine
   # plain
   res = engine.run_backtest("REPLAY_1_0.py", instrument="NQ", timeframe="5m",
           params={"entries_file":"my_engu.csv","default_stop_pts":25,"default_target_pts":50})
   # with the gate (learns which of YOUR entries to keep)
   resg = engine.run_backtest("REPLAY_1_0.py", instrument="NQ", timeframe="5m",
           params={"entries_file":"my_engu.csv"}, ml_filter="logistic", ml_threshold=0.5,
           ml_min_history=20, return_trades=True)
   ```

3. **Read the result:** win rate / profit factor / drawdown on your real trades; the gate's
   before/after (`res["ml_gate"]["ungated"]` vs headline); and edge-significance from
   `run_validate` — which tells you if the edge clears the bar, with an honestly-wide
   confidence band at low trade counts.

**Two questions it answers:** *as-taken* = "did my discretionary trades make money?";
*mechanical* = "what if I'd taken my entries but managed them by rule?" (the automation
question). The `PARAM_GRID_PRESETS` stop/target sweep answers "what mechanical management
would have made my entries best?"

**Caveat:** fills are approximated at the matched bar's open — a few points of slippage vs
your real fill. Read results as *"did my entries have edge,"* not P&L to the tick.

---

## The decision map (the core of this project)

Two paths from discretionary → automated. **The gating factor is sample size**, and the
owner currently has **under ~100 trades per setup type.**

| | **Path A — rule + learned filter** | **Path B — neural net (torch) on data/images** |
|---|---|---|
| **Idea** | Encode the setup as a mechanical rule (e.g. `ENGU_*.py`), backtest it over 16yr → thousands of trades; wrap the **ML gate** to learn which signals to take | Train a **CNN** (image-recognizing neural net) on the screenshots, or a sequence model on the bars, to detect the setup + predict outcome |
| **Viable at <100 trades?** | ✅ Yes — the *rule* fires thousands of times; your <100 are the **answer key**, not the training data | ❌ No — a neural net trained on <100 examples memorizes them, learns nothing general (needs ~1,000+ per type) |
| **When** | Now — the backbone | Later, once enough trades are logged; the 3080 Ti makes it feasible *then* |

**Key mental model:** the owner's <100 discretionary trades are **ground truth to check the
rule against** ("does my mechanical ENGU fire when I actually pulled the trigger?"), *not* a
dataset to train a model on directly. REPLAY is how we run that ground truth through the
engine.

**Connection to the AI code-writer (AI EVOLVE, see `CLAUDE.md`):** the discretionary trades
become a *second fitness signal* for the AI strategy-writer — "write a strategy whose entries
overlap these real trades AND is profitable over 16yr." This anchors the AI to the owner's
actual style instead of arbitrary curve-fits. At <100, use it as a **guide alongside** the
big backtest, not the sole objective (else it overfits to reproduce those trades).

---

## torch & EconML — what they are, and the ruling

- **`torch` (PyTorch)** — the standard **deep-learning** library (builds neural networks).
  Relevant uses here: a **CNN** to recognize setups from **screenshots** (vision — the *one*
  place neural nets genuinely beat gradient-boosting), or a sequence model on the bars.
  **Ruling:** *not now* — <100 trades is far too few (it would memorize); and Carl's own
  notebook labels the LSTM attempt "FAIL." Revisit when trade counts hit ~1,000+/type.
- **`EconML`** — Microsoft's **causal-inference** library (Double Machine Learning: "does X
  *cause* Y, or just correlate?"). **Ruling:** *skip* — the existing causal-entry
  randomization test (board §7) already answers the core question; EconML duplicates it and
  wants more samples than we have.
- **Hardware:** owner has an **NVIDIA 3080 Ti (12 GB)** — plenty for local NN training *when*
  Path B becomes viable. So the GPU is not a blocker; sample size is.

### Deployment / isolation (if Path B ever proceeds)
- **Never install torch/EconML into the runner's Python env** — `CLAUDE.md` doctrine: heavy
  pinned deps risk destabilizing the trading-PC env the auto-start runner depends on.
- Use a **venv** — a sealed, separate library folder. *Same PC is fine* (the isolation unit
  is the Python environment, not the machine). A separate machine only helps for heavy
  training.
- **How the two talk:** file/folder handoff — exactly the pattern already used by the
  NinjaScript OHLC export and the Webull watch-folder. The torch model writes scores to a
  file; the runner reads it. (Alternatives: a tiny local API, or a shared DB — but
  file-handoff matches existing architecture and adds no new moving parts.)

---

## Next steps (open TODO)

1. **Get a real export.** Owner exports one setup (even 20–40 ENGU rows: timestamp + side,
   + exit if logged). Run through REPLAY + gate + edge-significance; interpret *straight* —
   including "sample too thin to conclude" if that's the truth.
2. **Overlap report (not yet built):** compare the mechanical rule's entries to the owner's
   discretionary timestamps — where they agree/disagree reveals the "feel" the rule misses.
   A small addition (both are trade lists with entry bar indices).
3. **Gate as the discretionary-filter deliverable:** if a rule + gate on real entries shows
   edge, that *is* an automatable bot — package it.
4. **(Deferred) Path B:** only after trade counts justify it — CNN on screenshots in an
   isolated venv on the 3080 Ti, validated back through the engine for actual P&L.
5. **(Optional) Web-UI card** for REPLAY if the owner wants to run it from the site rather
   than the Python engine.

---

## Guardrails for this scope
- Standing git auth applies (auto-commit/push; `git add` only your files; fetch-first;
  bump `VERSION` only for web-facing changes — REPLAY is backend, so no bump).
- Don't install heavy deps on the runner env (venv only). Secrets stay local. Never handle
  the owner's broker/Firebase login.
- Report edge honestly — at <100 trades, wide confidence bands are the correct answer, not a
  bug to hide.

## Glossary (plain language)
- **Discretionary trade** — one you took by judgment/feel, not a fixed rule.
- **Meta-label / ML gate** — a secondary model that scores each rule-generated trade's
  P(win) from entry-time features and skips the low-scoring ones. Turns "feel" into a filter.
- **Edge-significance** — a statistical test (t-test + bootstrap) that says whether the mean
  per-trade P&L is really positive or could be luck.
- **CNN (convolutional neural net)** — a neural network built to recognize shapes in images.
- **venv** — a sealed folder holding its own copy of Python libraries, isolated from the
  system/runner Python. Same machine, no cross-contamination.
- **API** — one program calling another program's function across a wire (e.g. "score this
  setup" → a number back).
- **POINTS vs $** — the engine works in price POINTS; the web/instrument layer multiplies by
  the point value (NQ ×20, ES ×50) for dollars.

---
*Created 2026-07-04. Owner: active ES/NQ futures trader. Keep this doc updated as the scope
moves; it is the cold-start brief for the discretionary→quant project.*
