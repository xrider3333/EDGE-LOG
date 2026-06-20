# AUGUR / EDGELOG — Roadmap & Backlog

Single source of truth for what's done and what's next. `CLAUDE.md` holds durable
context/conventions and points here; `docs/` holds reference (architecture, go-live).
Newest/priority items near the top of each section. Status as of **index.html v25.0**.

The big picture (see `docs/EDGELOG_PORT_PLAN.md` for the phased detail): port the entire
AUGUR optimizer (`optimizer.py`, Streamlit) into the EDGELOG website, with compute on the
PC via the runner (`api/runner.py` + `augur_engine`). Streamlit keeps working until the web
app reaches parity, then is retired. Ship tab-by-tab, version-bumped 0.1 each change.

---

## 0. Infra / data consolidation (loose ends)
- [ ] **Retire the duplicate AUGUR desktop folder.** EDGE-LOG is now the complete copy
      (serviceAccount.json + optimizer_history.db [112 runs] + augur_uploads [25 CSVs] +
      augur_config.json with model numbers + migrated ORB roadmap + pine/ [22 files]). The
      AUGUR folder has an *older* runner.py and a stale `run_augur_runner.bat` whose cred
      points at `C:\Users\xride\Downloads\edge-tracker-…json` — kill that .bat so EDGE-LOG's
      launcher (cred = local `serviceAccount.json`) is the only one. Confirm a clean runner
      start, then archive/ignore AUGUR.
- [x] **`pine/` parity** — copied the 12 AI-generated (qwen) `.pine` files that existed only
      in AUGUR (ENGU_1_2_1, ENGU_1_3_4, ORB_1_0/2_0, OVERNIGHT_HOLD_1_0, REVERT_1_0/1_1/1_2,
      RF_ML_1_0, SUPERTREND_1_0/2_0, VWAP_FADE_2_0) into EDGE-LOG/pine. They are unreviewed —
      use the site's Review-with-Claude flow before trusting any for live.
- [ ] **Package the runner as a desktop app** (PyInstaller → `AugurRunner.exe`): tray icon,
      auto-start with Windows, connected/disconnected dot, pause/quit menu — kills the
      `.bat` + console friction. Optional later: PWA "install" of the site.

## 1. Library tab — open
- [ ] **Keyless-AI decision for Pine (open)** — `make_pine`/`review_pine` currently call the
      AI provider directly (qwen/claude-cli/anthropic), which contradicts AUGUR's keyless-AI
      doctrine (file-handoff through the Claude Code session, no direct paid-CLI spend).
      Decide: keep direct-CLI, or convert Pine generation/review to true file-handoff.
      Provider cost model as shipped: **qwen = free/local**, **claude-cli (Review/Regenerate)
      = spends Claude credits**, **anthropic = API key from local augur_config.json only**
      (the credit-spend surprise that drove v24.1's qwen default).
- [ ] **Per-master actions** — masters pane is read-only; add select → toggle auto-pull
      (writes augur_config `autorefresh.masters[key]`) + delete master.
- [ ] **Multi-instrument master pull** — "+ PULL MASTER" picker for GC/YM/CL/RTY/etc.
      (instruments already in optimizer.INSTRUMENTS); needs a `pull_master
      {instrument,timeframe,session}` runner command (initial Yahoo pull → save_master_csv).
      **Data ceiling:** Yahoo is OHLCV-only — no Time & Sales / tick / order-flow, and only
      ~recent intraday history. Intraday T&S is a Databento-only (paid) path (see #23).
- [ ] **Expand a strategy** to view its params / preset tiers (today: just a SCOPES count).
- [ ] **Auto-detect instrument from CSV filename/symbol** on upload (was AUGUR TODO #10).

## 2. Other AUGUR sub-tabs — migration gaps (not started)
- [ ] **Reference** — only 4 instruments (add YM/MYM/RTY/M2K/CL/GC); add signal-logic block,
      Yahoo data-limit table, and the backtesting-maturity roadmap. Also move the
      validation-methodology text here from Research. *Cheap, mostly static — recommended next.*
- [ ] **Research** — currently shows the methodology text (belongs in Reference). Real tab
      should render study JSON (walk-forward studies) — needs runner sync of `augur_research/`.
- [ ] **Results** — add filters (strategy/instrument/TF/scope), sort, star/favorite, and the
      **Rankings** 0–100 robustness leaderboard.
- [x] **Builder** — DATA (master) picker (overrides instrument/TF/session/source), DATE
      FROM/TO window, per-run COMMISSION $/RT + SLIPPAGE pts/RT (→ cost_pts), and a live
      progress bar in the RUNS table. Engine: `load_master_arrays(date_from,date_to)` slices
      before day_id factorization; threaded through run_backtest/grid/auto/ai_optimize/evolve
      + runner; cost/date fields persisted to run history. *(v25.0)*
- [ ] **Compare** — N-way (currently 2-way), grouped bar chart (SVG), parameter rows.
- [ ] **Settings** — auto-refresh toggles (write-back to Firestore), table density.

## 3. Engine research items (future — largely independent of the web port)
New backtesting capabilities for `optimizer.py` / `augur_engine`, drawn from Pardo, Bandy,
Aronson, López de Prado, Chan, Tomasini/Jaekle. Some already compute & render in Results
(DSR, Monte-Carlo, regime, neighborhood) — those are noted.
- [~] **#11 Deflated Sharpe / multiple-testing haircut** — DSR computed (analytics.py) &
      shown; extend to a "best-of-N luck bar" next to every grid winner.
- [~] **#12 Neighborhood robustness table** — computed & shown; tie to the PLATEAU verdict.
- [~] **#13 Regime-sliced report card** — computed & shown; expand slices (DoW, monthly heatmap).
- [ ] **#14 MAE/MFE distributions** per trade (basis for stop/target placement).
- [ ] **#15 Risk-of-ruin + bootstrap MC** (resample-with-replacement, ruin prob, time-to-recovery).
- [ ] **#16 Vol-targeted position sizing** (size by ATR so $ risk/trade is constant).
- [ ] **#17 Half-day / holiday calendar** (13:00 ET closes break ORB EOD-flat & session stats).
- [ ] **#18 Event-day tagging** (FOMC/CPI/NFP CSV; PnL with/without; skip-event toggle).
- [ ] **#19 Lockbox holdout** (reserve most recent ~1yr, never optimized, final pre-deploy gate).
- [ ] **#20 Live-vs-backtest drift monitor** (track realized fills/PnL vs engine once paper trading).
- [ ] **#21 Slippage scaled by volatility/gap** (flat pts/RT understates fast-market stops).
- [ ] **#22 Capacity check** (max contracts vs typical entry-bar volume per instrument).
- [ ] **#23 Order-flow enrichment (Databento, paid)** — CME MDP3 *Trades* ($28/GB); per-bar
      aggressor DELTA (buy−sell vol) into enriched masters; strategies filter on real pressure.

## 4. optimizer.py (Streamlit) — open bugs (only while Streamlit is still in use)
- [ ] **#1 Results shows only the most-recent completed run** — live panel hydrates only the
      latest of several queued/completed; earlier ones are in Past Runs but not shown live.
- [ ] **#2** Replace remaining `use_container_width=` with `width=` (deprecation in logs).
- [ ] **#3 Auto-Optimize has no out-of-sample guardrail** — can report overfit PNLs with no
      warning; port the AI scopes' 75/25 OOS readout to Auto-Optimize.
- [ ] **#4 Page/layout/speed/navigation audit** — faster reruns, fewer clicks, less scrolling;
      cache stable queries, tighten AI-round rerun scope, lazy charts, re-run-last button,
      remember last inst/tf/strategy/scope.
- [ ] **#5** Cost estimate (tokens/$ per round) in the AI panel.
- [ ] **#6** Compare evolved-vs-original strategy in Results (PNL delta + code diff).
- [ ] **#7** Walk-forward / rolling OOS beyond the single 75/25 split.
- [ ] **#8** Optimistic-vs-pessimistic intrabar fill toggle for engu/v25 (stop-vs-target order).
- [ ] **#9** Relabel a SUBSET of runs in Past Runs (backend `set_runs_strategy` exists; only
      "Apply to ALL" is surfaced).

---

## Done (recent — website)
- **v26.0** CUSTOM scope restricted to Grid sweep (it's an exhaustive-grid concept). AI
  optimize/evolve explore params themselves — the preset only seeds round 1 — so the CUSTOM
  option is disabled in non-grid modes and falls back to a real preset if left selected.
- **v25.9** CUSTOM scope in the Builder: runner now syncs each strategy's numeric
  DEFAULT_PARAMS spec (name/type/min/max/step) to meta; SCOPE has a ◆ CUSTOM option that
  reveals per-param min/max/step rows with a live combo count, sending an explicit grid
  dict (engine prefers grid over preset). Works for grid/AI/evolve modes. Closes the
  param-spec gap that also blocked a single-mode param editor.
- **v25.8** Date-range calendar no longer closes when picking a day or changing month
  (popover clicks no longer bubble to the outside-close handler); added «/» quick
  year jump alongside ‹/› month nav.
- **v25.7** Builder DATE RANGE is now a single pill opening one bounded month-view calendar
  (click start then end, like legacy AUGUR); bounds to the selected CSV's span. Mode-aware
  fields are now HIDDEN (not just dimmed) when the current mode ignores them — no AI ROUNDS
  on a grid sweep, etc. (Open: no CUSTOM scope / per-param range editor in the web port yet.)
- **v25.6** Builder tile now uses the themed `section` class (picks up the active iOS-glass
  theme's bg/blur) + scoped pill-rounded controls; DATE FROM/TO combined into one DATE
  RANGE cell (from → to).
- **v25.5** Builder top row is DATA & STRATEGY (Strategy · Instrument · TF · Session ·
  CSV · Date From · Date To, dates via native calendar dropdown); MODE moved to the
  second row (Run mode · search params); COSTS on a third row. Removed the hardcoded
  single-mode VOL FILTER — single backtests now run the strategy's own DEFAULT_PARAMS.
- **v25.4** Builder data flow inverted to legacy order: MODE · STRATEGY · INSTRUMENT ·
  TIMEFRAME · SESSION · CSV FILE, where the CSV picker only lists masters matching the
  chosen instrument/TF/session (repopulates live on change). Selections drive the run;
  the CSV pick only refines which master (source). Replaces the old master-overrides-selects.
- **v25.3** Builder relaid out horizontally (like legacy AUGUR "Executions"): a full-width
  BUILD A BACKTEST tile where fields flow left-to-right and wrap, grouped in build order
  (Setup → Data window · Costs → Search params → Run), with the RUNS table full-width below.
  Replaces the narrow 280px vertical config column.
- **v25.2** Builder is mode-aware: each MODE greys out the fields it doesn't feed (SCOPE for
  single/auto/WF, VOL for non-single, TRIALS for grid/AI, AI ROUNDS+PROVIDER for non-AI,
  WF FOLDS off walk-forward), matching the engine. MODE choice now persists across reruns.
  Keeps the split MODE/SCOPE design but removes its only downside (inert active controls).
- **v25.1** Builder selectors aligned with legacy AUGUR: INSTRUMENT now lists all 12
  (ES/MES/NQ/MNQ/RTY/M2K/YM/MYM/CL/MCL/GC/MGC) in optimizer.py order; TIMEFRAME is the
  standard 1m/5m/15m/30m/1h/1d set. Added MCL/MGC to the point-value map.
- **v25.0** Builder §2 parity: DATA master picker, DATE FROM/TO window, COMMISSION+SLIPPAGE
  cost inputs, live progress bar. Engine date-range slicing in load_master_arrays threaded
  through all run modes + runner; cost/date persisted to run history.
- **v24.9** Library: keep scroll on select; document-level arrow-key nav; Sharpe reads
  dsr.winner_sharpe + shows DSR%; walk-forward shows folds-held-OOS.
- **v24.8** ADD next to DELETE; roadmap moved to its own tile below the split; panes
  vertically resizable; arrow-key nav; launcher checks for serviceAccount.json.
  Runner: list_runs() tolerates a missing `runs` table.
- **v24.7** Library roadmap mirrors optimizer.py's 10-step validation; runner syncs each
  strategy's saved roadmap state (augur_config roadmaps[file]).
- **v24.6** Roadmap folded into the strategies tile; Pine `?` fixed (provider aliases
  ollama→qwen, claude-cli/anthropic→claude); dropped SET ACTIVE (USE IN BUILDER only).
- **v24.5** Fixed dropdown menus clipped by action-tile overflow.
- **v24.4** Download/AI dropdown menus; SET ACTIVE + USE IN BUILDER quick-launch; inline
  per-strategy stats; ROADMAP checklist tab.
- **v24.3** Pine provenance badge; downloads grouped by DELETE; masters title inside its tile.
- **v24.2** Per-click AI provider toggle; Claude REVIEW → APPLY flow.
- **v24.1** MAKE PINE defaults to free local qwen; cost shown on button.
- **v24.0** STRATEGY header sorts by # or name; no fade-flash on select.
- **v23.8** Command channel (download/delete/add/make-pine); clickable headers.
- **v23.7** Action bar + compact table + py/pine chips + date-added + last-ran.
- **v23.5–23.6** Library split layout, clickable rows, delete-with-confirm, side/stack toggle.
