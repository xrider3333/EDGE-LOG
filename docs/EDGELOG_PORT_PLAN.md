# Optimizer → EDGELOG full-port plan

Goal: the ENTIRE AUGUR optimizer (every tab, every function, all history) running inside
EDGELOG as a web app, with compute on the PC via the runner. Streamlit (`optimizer.py`)
keeps working until EDGELOG reaches parity, then is retired.

Architecture (unchanged from the MVP): EDGELOG (web) ⇄ Firestore (per-user docs) ⇄ runner
(PC) ⇄ `augur_engine`. The runner both *processes jobs* and *syncs local data* (runs,
strategies, masters) up to Firestore so the web UI reads it with onSnapshot.

## Phases

### Phase 1 — History + Results  ◀ IN PROGRESS
Surface all 112 past runs (read-only).
- Backend: `augur_engine.history.list_runs/get_run` (reads the `runs` table — stats,
  best_params, top10_results, equity_curves_json). Runner syncs them to
  `users/{uid}/runs` (and on each watch start).
- Frontend: a "RUNS" view — sortable list (date, strategy, inst, tf, scope, PnL, PF, WR,
  trades, DD) → click a run → detail: stat cards, equity curve (SVG), top-10 rankings table.

### Phase 2 — Launching (Executions)
Run new optimizations from the web.
- Backend: extend the runner's job types beyond single backtest → grid sweep / auto-optimize
  / walk-forward (reuse `optimizer.py`'s `_run_job` backend + `augur_mp_worker`); write live
  progress to the job doc.
- Frontend: scope picker (Short/Med/Long/XL/XXL/Custom/Auto/WF), param-grid controls, a live
  progress bar, queue. On finish, the run lands in Phase-1 history automatically.

### Phase 3 — Library
Strategies + master CSVs.
- Backend: `augur_engine.list_strategies/list_masters` (done) + strategy source/Pine read.
- Frontend: strategies table (select, view params, download Pine) + masters table.

### Phase 4 — Analytics
The research panels: Monte-Carlo, Deflated Sharpe, regime report card, neighborhood
robustness, walk-forward equity, compare-two-runs. Extract each from `optimizer.py` into
`augur_engine.analytics`, expose per-run, render in the Results detail view.

### Phase 5 — Settings + AI scopes
Workers, master auto-refresh toggles, API keys; then the agentic AI Optimize/Evolve rounds.

## Notes / risks
- Biggest backend lift is Phase 2 (extracting the optimization driver streamlit-free).
- UI is built somewhat blind (no live render here) → go tab-by-tab, user eyeballs each, ship
  with a version bump (0.1) per change.
- Firestore free-tier limits are ample for this volume (112 runs × ~20KB ≪ 1GB; reads/writes
  well under daily caps). Big blobs (code_snapshot) are NOT synced.
