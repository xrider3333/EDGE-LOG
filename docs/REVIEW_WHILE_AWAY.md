# Review — what I built while you were away

The AUGUR section inside EDGELOG, built out tab-by-tab. Phase 1 is live on `main`; the rest
is staged on ONE branch for your review. All backend is verified end-to-end against your real
Firebase.

## Live now on `main` — Phase 1 (Runs)
EDGELOG **v21.8**: the AUGUR tab has **Launch / Runs** sub-tabs. **Runs browses all 112 of your
past optimizations** (synced to `users/{uid}/runs`) → click any run for stat cards + top-config
rankings. Hard-refresh EDGELOG to see it.

## On branch `phase2-executions` (NOT merged) — Phases 2, 3 + equity charts
EDGELOG **v22.1**. The AUGUR tab gains three more sub-tabs:
- **EXECUTIONS** — launch grid sweeps from the web: pick strategy + scope/preset (loaded from
  your synced library) + market + min-trades + workers → **RUN SWEEP** → live progress + ranked
  top-config results, computed on your PC.
- **LIBRARY** — your 20 strategies (with scope counts) and 16 masters (instrument/tf/session/
  source/rows/range), read from synced meta.
- **Equity curves** — the Runs detail view now draws the best config's equity curve (decoded
  from the gzip'd `equity_curves_json`, downsampled, synced to Firestore).

**To review/go live:** open the PR (https://github.com/xrider3333/EDGE-LOG/pull/new/phase2-executions)
and merge, or tell me and I'll merge it. (A branch can't be previewed on Pages without merging,
since your Firebase config lives in the live page's localStorage.)

## Backend added (local, all verified)
- `augur_engine/optimize.py` — `run_grid()` (preset/grid expand, multicore via the proven
  `augur_mp_worker`, min-trades gate, ranked top-N). Verified: ORB Short 8/8 valid, best PF 1.49.
- `augur_engine/history.py` — `list_runs/get_run`, now also **decodes the equity curve**
  (base64+gzip JSON) and downsamples it.
- `api/runner.py` — handles `type:'grid'` jobs with **live progress** writes; `sync_meta()`
  publishes 20 strategies (+scopes) and 16 masters to `users/{uid}/meta`.
- Verified end-to-end: a grid job queued into your real Firestore was processed and ranked
  results written back.

## How to run it (when you're back)
1. Double-click **`run_augur_runner.bat`** (already has your UID). On start it syncs run history
   + library meta to Firestore, then watches for jobs (backtests AND grid sweeps).
   Only ONE runner should watch at a time (two would double-process).
2. Merge the `phase2-executions` branch to get Executions / Library / equity live.

## On branch `phase4-analytics` (NOT merged) — Phase 4: Analytics
EDGELOG **v22.2**. Backend `augur_engine/analytics.py` (faithful ports of the app's math):
- **Monte-Carlo drawdown** — block-shuffle the trades, report the p50..p99 drawdown
  distribution. Launch backtests now request it (mc_sims) and show a **P95 DD** column
  ("size your account to survive this").
- **Deflated Sharpe** (Bailey/Lopez de Prado) — Executions sweeps request it; a **VALIDATION**
  line shows winner Sharpe vs the best-of-N **luck bar** + DSR % verdict above the rankings.
Verified headlessly: ORB backtest p95 DD ~$29k; ORB Short-grid winner Sharpe 1.33 vs luck bar
0.27 → DSR 100% (consistent with the high luck bar that failed the 2,304-config run #114).
Merge `phase4-analytics` after the others to turn it on. (Backend is already in your local
`augur_engine`/runner, so the runner computes these as soon as the frontend requests them.)

## On branch `phase5-ai` (NOT merged) — Phase 5: AI Optimize
EDGELOG **v22.3**. `augur_engine/ai.py` runs the agentic loop: sweep in-sample → validate
out-of-sample (75/25) → an LLM proposes the next ranges → repeat. **Pluggable backend, default
is FREE + local** on your `qwen3.6` via Ollama (also Claude CLI, or Anthropic API). Executions
gets a **MODE** selector (Grid sweep | AI optimize) + provider/rounds; AI runs show in SWEEPS and
land in Runs history. Verified end-to-end on qwen3.6: it reasoned about the in/out-of-sample
overfit gap and converged on the deployable config (IS 11,236 / OOS 8,680 pts), zero token cost.
(Anthropic key, if you pick that provider, is read from local `augur_config.json` — never the job.)

Branch `phase5-ai` (v22.4) ALSO includes **AI Evolve**: the LLM may rewrite the strategy's
Python *code* each round. Every edit passes a hard gate (compile + plugin-contract + smoke
test) before use and is saved as a NEW `augur_strategies/<base>_evo_<ts>.py` — existing
strategies are never touched. Verified with real qwen3.6: it reasoned about overfit, wrote
valid code (added a profit-target sweep), passed the gate, and improved OOS. Pick it from the
Executions MODE dropdown (Grid | AI optimize | AI evolve).

## Live on `main` — v22.6 / v22.7 (tab restructure + missing scopes)
**v22.6** — AUGUR sub-tabs now match the original app order exactly:
**Results · Executions · Library · Compare · Reference · Research · Settings** (7 tabs).
- **Compare** — pick two runs (A/B) → side-by-side metrics (Net P&L, PF, Win%, Trades,
  Max DD, $/day).
- **Reference** — instruments ($/pt), cost model ($5.66 RT), session/RTH definitions.
- **Research** — validation methodology cards (OOS 75/25, Deflated Sharpe, Monte-Carlo,
  walk-forward).
- Strategy dropdowns in Executions show the assigned **#numbers**.

**v22.7** — the two missing smart-search **scopes** are now in the Executions MODE
dropdown (single · grid · **Auto-Optimize** · **Walk-Forward** · AI optimize · AI evolve):
- **Auto-Optimize** — seeded smart search maximizing PnL on the first 75% of history, then
  re-tested **out-of-sample** on the held-out 25%. Shows OOS $ / OOS PF columns (the
  overfit guardrail). Verified: NQ 5m RTH, 60 trials, best PF 1.44, OOS +16,230 pts,
  DSR 99.99%.
- **Walk-Forward** — anchored folds, each re-optimized then tested on the next unseen
  slice; one champion row per fold. Verified: 3 folds all OOS-positive (PF 1.43/1.26/1.17).
- Engine: new `augur_engine/auto.py` (faithful port of the app's `_AutoSampler` path incl.
  realism gates WF_MIN_SIDE/MAX_TRADE_RATE/MAX_PF). Runner dispatches `type:auto`/
  `walkforward` and persists to Runs history (scope "Auto-Optimize"/"Walk-Forward").

**v22.8** — **Results analytics panels** (the original app's research read-outs) now
render in a run's detail view (Results tab → click a run):
- **VALIDATION** line — Deflated Sharpe luck-bar + P95 Monte-Carlo drawdown.
- **Regime report card** — per-trade PnL/PF sliced by volatility tercile (ATR20),
  trend-vs-chop (efficiency ratio), day-of-week, plus a monthly PnL heat-grid. On 16yr
  NQ the ORB edge concentrates in **High-vol + Chop** (PF 1.51 / 1.68) — visible at a
  glance, the basis for a regime filter.
- **Neighborhood robustness** — the winner's ±1-step parameter neighbors' profit factors
  with a HIGH GROUND / CHECK NEIGHBORS verdict (a real optimum has profitable neighbors).
- Engine: `augur_engine/analytics.py` gains `regime_report()` + `neighborhood()`; run_grid
  + run_auto compute them for the winner; the runner requests both by default and stores
  them in the run doc. (Older synced runs predate these fields → panels show only on new
  web sweeps / auto / walk-forward runs.)

**v22.9 — UI polish pass:**
- Results tab no longer shows a run-count; the past-runs list is now AUGUR-style clickable
  **tiles** (strategy / market / scope / P&L / PF / WR / TRD) → click loads the report card.
- Every table/list sits in a rounded **tile** (Library strategies + masters, Executions
  runs + top configs, Compare, Reference).
- Sub-tab headers gained monochrome geometric **icons** (▦ Results · ▸ Executions · ◫ Library
  · ◧ Compare · ◈ Reference · ◎ Research · ◆ Settings).
- **Settings** now has a DEFAULTS panel (instrument / session / timeframe / workers / AI
  rounds / trials / min-trades / provider) saved to localStorage and used by the Executions
  launcher — and launching remembers the last-used values (CLAUDE.md TODO #4).

## Still optional (not started)
- Runner-side auto-refresh toggles surfaced in the web (Settings is otherwise complete).
- Dead `launch` sub-tab branch still in index.html (unreachable; could be deleted for tidiness).

Plan: `docs/EDGELOG_PORT_PLAN.md`.
