# AUGUR / EDGELOG — Roadmap & Backlog

Single source of truth for what's done and what's next. `CLAUDE.md` holds durable
context/conventions and points here; `docs/` holds reference (architecture, go-live).
Newest/priority items near the top of each section. Status as of **index.html v36.0**.

The big picture (see `docs/EDGELOG_PORT_PLAN.md` for the phased detail): port the entire
AUGUR optimizer (`optimizer.py`, Streamlit) into the EDGELOG website, with compute on the
PC via the runner (`api/runner.py` + `augur_engine`). Streamlit keeps working until the web
app reaches parity, then is retired. Ship tab-by-tab, version-bumped 0.1 each change.

---

## 0. Infra / data consolidation (loose ends)
- [x] **Single EDGE-LOG folder for runner + edits (done 2026-06-22).** There were TWO clones
      of this repo: `C:\Users\xride\EDGE-LOG` (code-only — no cred, no `augur_uploads/` masters)
      and `C:\Users\xride\OneDrive\Desktop\EDGE-LOG` (data-rich — `serviceAccount.json`,
      `augur_config.json`, 1.1 GB masters; **this is where the runner actually runs**, via its
      `run_augur_runner.bat`). Engine pushes were going to the code-only clone while the runner
      read the data-rich one, so a 13-commit-stale `augur_engine` silently dropped new fields
      (this is what made `win_dist` / the trade-PnL distribution curve never populate). FIX:
      **`OneDrive\Desktop\EDGE-LOG` is now canonical for both editing AND the runner**; the
      `C:\Users\xride\EDGE-LOG` clone is retired (left as a backup). After any engine change,
      **restart the runner** so it reloads `augur_engine`. Do NOT reintroduce a second clone.
- [x] **Retire the duplicate AUGUR desktop folder (done 2026-06-27).** EDGE-LOG verified as the
      complete copy (serviceAccount.json + optimizer_history.db [112 runs] + augur_uploads
      [25 CSVs] + augur_config.json with model numbers + migrated ORB roadmap + pine/ [23 files])
      and the AUGUR desktop folder was deleted to the Recycle Bin. The stale
      `run_augur_runner.bat` (cred → `C:\Users\xride\Downloads\edge-tracker-…json`) is gone;
      the sole launcher is now `EdgeLog.bat`, which reads the **local** `serviceAccount.json`.
      EDGE-LOG is the single canonical folder for editing AND the runner — do NOT reintroduce a
      second clone, and restart `EdgeLog.bat` after any engine change so it reloads `augur_engine`.
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
- [~] **Reference** *(partial, 2026-06-27)* — INSTRUMENTS table trimmed to the minis we actually
      have data for (ES, NQ; micros dropped), with a note that YM/RTY/CL/GC are selectable in the
      Builder but unbacked until their OHLC is imported (only ES/NQ exist, via Databento). The
      VALIDATION METHODOLOGY block was moved here from Research and expanded to 10 methods (OOS,
      walk-forward, lockbox, plateau/neighborhood, stress, cross-instrument transfer, DSR, MC,
      sample-adequacy/DOF, regime). **Dropped by decision:** Yahoo data-limit table (low value
      while ES/NQ run on Databento) and the maturity-roadmap block (already covered by the Library
      VALIDATION CHECKLIST + Results pills). **Open:** signal-logic block.
- [~] **Research** — methodology text moved out to Reference; tab now shows a WALK-FORWARD STUDIES
      placeholder. Real tab should render study JSON (walk-forward studies) — needs runner sync of
      `augur_research/`.
- [x] **Results** — filters (strategy/market) + sort (newest/score/$/PF), per-run star/favorite
      + notes (write-back to Firestore), Rankings 0–100 leaderboard, and full legacy chart parity
      (distribution+plateau, scatter, heatmap, top-N equity, stress). *(v27.x)* Open: TF/scope
      filter facets, relabel/delete from web.
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
- [~] **#14 MAE/MFE distributions** per trade — engine computes max adverse/favorable
      excursion from rich trades and the Results panel turns it into stop/target guidance
      (median/90th heat winners took → stop; median/75th reach → target) + histograms.
      Needs each strategy to emit 5-tuple trades `(entry_i, exit_i, pnl, side, entry_px)`;
      ORB_SIMPLE_1_0 done, others fall back to no-panel until upgraded. *(v28.3)*
- [ ] **#15 Risk-of-ruin + bootstrap MC** (resample-with-replacement, ruin prob, time-to-recovery).
- [ ] **#16 Vol-targeted position sizing** (size by ATR so $ risk/trade is constant).
- [ ] **#17 Half-day / holiday calendar** (13:00 ET closes break ORB EOD-flat & session stats).
- [ ] **#18 Event-day tagging** (FOMC/CPI/NFP CSV; PnL with/without; skip-event toggle).
- [x] **#19 Lockbox holdout** — web Builder LOCKBOX group: "reserve since" date caps every
      optimization mode's window the day before it (never seen during search), + a one-shot
      "test last winner on lockbox" action (single backtest over the reserved slice). *(v26.6)*
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
- **v36.0** (2026-06-27) Account balance is now **live / auto-derived** instead of a static
  field. `accountEquity` is treated as the STARTING balance and the shown balance =
  starting + cumulative net P&L (new helpers `totalNetPnl()` / `liveBalance()`). Settings field
  relabeled **CURRENT BALANCE** — entering a value back-solves the start
  (`accountEquity = entered − ΣP&L`) so it reads correct immediately and then tracks every new
  trade; equity-chart footer shows live **BALANCE**. Deposits/withdrawals still fold in via the
  existing ledger (they raise `accountEquity`). Migration: a stored "current" equity should be
  re-saved once (or set `el_equity = current − ΣP&L`).
- **v35.4** (2026-06-27) Reference tab rebuilt (ES/NQ-only instruments + the 10-method
  VALIDATION METHODOLOGY moved here from Research); Research → walk-forward-studies placeholder;
  Settings launcher name fixed to `EdgeLog.bat`. Results: dropped the "Results View" header row
  and the MODE pill from the run-report header; trimmed chart 1b's footnote; **PAST RUNS filters
  embedded into the column headers** (pivot-style sort+filter; the separate filter bar is gone).
  Runner/engine: console rebranded AUGUR→EDGELOG and now reports the **website** version (legacy
  `optimizer.py` 5.8.103 banner suppressed). Tooling: standing auto-push authorization added to
  CLAUDE.md.
- **v35.3 (NinjaTrader auto-sync, runner-bridged).** Hands-free live trade import: a NinjaScript
  AddOn (`tools/EdgeLogExport.cs`) subscribes to every account's `ExecutionUpdate` and appends each
  fill to `C:\EdgeLog\fills.csv` (captures manual *and* automated trades — an AddOn, not a Strategy).
  The always-on runner (`api/nt_sync.py`, wired into `api/runner.py` watch loop, default every 20s +
  on a `sync_trades` command) FIFO-pairs fills into round-trip trades — P&L/symbol/schema mirror
  index.html's `calcPnl`/PRESETS exactly — and upserts them to `users/{uid}/trades` with deterministic
  doc ids (`nt_<exitExecId>`), so re-reading the whole file never duplicates. Status doc at
  `users/{uid}/meta/nt_sync`. Web: DATA→IMPORT tab gains a NINJATRADER AUTO-SYNC panel (live
  connected/last-sync/open-positions status, ↻ REFRESH NOW → enqueues `sync_trades`, collapsible
  one-time AddOn setup). Runner flags: `--nt-fills PATH` (env `EDGELOG_NT_FILLS`), `--trades-sec N`.
  NOTE: there is no NinjaTrader web/cloud login API — "connect from the website" is intentionally the
  PC-side bridge. A true server-side login→pull is only possible for API brokers (Tradovate /
  TopstepX-ProjectX); revisit if the user moves execution there.
- **v28.8** Auto-Validate gains a DISCOVER WITH selector: Statistical (default, fast/free) or
  AI-evolve (rewrites the strategy code on the pre-lockbox window via ai_evolve, then judges
  the evolved strategy through the full pipeline — lockbox stays untouched). Provider/rounds
  reuse the existing AI fields; card shows the evolved file. Also fixed a 5-tuple-trade bug
  that crashed regime_report on the upgraded ORB strategies.
- **v28.6** Builder MODE numbered in workflow order (1 Single … 7 Auto-Validate = judge);
  Auto-Validate now surfaces the full Regime card + Neighborhood table + MC (not just the
  card summary) so the DSR/Regime/NBHD panels render for validate runs too; Library
  "DEPLOY READINESS" renamed to "VALIDATION CHECKLIST".
- **v28.2** Closed the Results audit: TF/scope filter facets + clear; PARAM CORRELATION panel
  (Pearson r per param vs PnL); WALK-FORWARD IS-vs-OOS per-fold bars; delete + relabel runs
  from the web (runner delete_run/relabel_run commands); SPY buy-&-hold benchmark over each
  run's window. Deferred: MAE/MFE (needs per-trade direction in the strategy contract — legacy
  never finished it either).
- **v27.9** Past Runs: filter by strategy / market, sort (newest / score / $ / PF), per-run
  ★ star toggle + editable notes (write back to Firestore users/{uid}/runs). Closes the
  Results filters/sort/favorite backlog.
- **v27.8** Fix: equity_top was a nested array → Firestore "Nested arrays not allowed" crashed
  the runner sync; wrapped each curve as {cum:[...]}.
- **v27.7** Compare goes N-way: add/remove any number of runs as columns; per-row best-value
  highlight; rows incl. robustness score, DSR, verdict; grouped Net P&L bar chart. Plus
  legacy-run migration (history.get_run derives dist/points/equity_top/stress) so all 112
  historical runs light up the new Results panels after a runner re-sync.
- **v27.6** Stress-test across time in Results — winner PnL across 8 chronological windows
  with a SPREAD vs CONCENTRATED verdict (one lucky stretch = red flag). Completes Results-tab
  parity with legacy AUGUR (distribution, scatter, heatmap, top-N equity, rankings, stress).
- **v27.5** Top-N equity overlay in Results: engine computes the top-6 configs' equity
  curves (grid/auto/validate); Results overlays them (best highlighted) so you can see if
  the winners climb alike (robust) or only the best does (fragile). Only stress-test-across-
  time remains for full legacy Results parity.
- **v27.4** RANKINGS sub-tab: 0–100 robustness leaderboard across all saved runs
  (frontend-only score blends DSR, walk-forward folds held, lockbox, PF, sample; Auto-Validate
  runs use their gate results + verdict badge). Click a row → opens the run in Results.
- **v27.3** Results-tab parity (part 2): SCATTER (param vs PnL) + HEATMAP (param X×Y → avg
  PnL, 8×8) panels with param pickers. Engine syncs a compact per-config `points` array
  (params + PnL) from grid/auto/validate. Remaining vs legacy: top-N equity overlay,
  Rankings leaderboard, stress-test.
- **v27.2** Results-tab parity (part 1): PNL DISTRIBUTION panel with PLATEAU / ISOLATED-SPIKE
  verdict — histogram of every tested config's net PnL (engine syncs a compact `dist` from
  grid/auto/validate). Still missing vs legacy: scatter, heatmap, top-N equity overlay,
  Rankings leaderboard, stress-test (need fuller param-point sync — next).
- **v27.1** Cross-instrument transfer gate (the last auto-gatable validation-roadmap step):
  Builder TRANSFER TO picker (defaults to the sibling, NQ↔ES) re-tests the champion on
  another instrument with NO re-optimization; 6th gate passes if it stays profitable there.
  Card shows the transfer gate + per-instrument holds/fails · PF · $ · trades.
- **v27.0** Auto-Validate card now renders in the Results/Past-Runs tab too (not just the
  Builder): factored into a shared `validateCardHtml` helper — verdict, 5 gates, equity
  curve (lockbox shaded), lockbox HELD/FAILED + MC drawdown — so saved validate runs show
  the full report card. (Results already had equity/regime/neighborhood for grid/auto runs.)
- **v26.9** Auto-Validate UX + visuals: VALIDATE SCOPE (Short/Medium/Long/XL) sets the data
  window + trials + lockbox months in one pick (no more 15-yr-by-default); WF folds dropped
  from the mode (auto-fit). Report card now shows 5 gates incl. **Plateau** (param robustness)
  + a **Monte-Carlo P95 drawdown** readout, plus an **equity curve** (champion PnL, lockbox
  slice shaded) annotated with IS PF/Sharpe.
- **v26.7** Auto-Validate mode (UI): one-click full validation pipeline — Builder MODE
  "🧭 Auto-Validate" (TRIALS/stage, WF FOLDS, LOCKBOX MO) queues a `validate` job that runs
  in-sample Auto-Optimize → rolling walk-forward → lockbox one-shot on the PC, and renders a
  PASS/WEAK/FAIL report card (4 gates + lockbox HELD/FAILED). Backend in d7ac309.
- **v26.6** Lockbox holdout (#19): Builder LOCKBOX group — a "reserve since" date that caps
  every optimization mode's window the day before it (the holdout is never seen during the
  search), plus a one-shot "🔒 test last winner on lockbox" button that runs the most recent
  winning config as a single backtest over only the reserved slice. The final overfit gate.
- **v26.5** Rolling walk-forward: engine `run_auto(wf_mode=...)` adds a fixed-length IS
  window that slides forward (regime-honest) alongside the existing anchored/expanding
  mode; Builder has a WF TYPE selector (Anchored / Rolling) for Walk-Forward runs. Realism
  gate + train_bars (→WFE) use the true rolling window length.
- **v26.4** Sample-adequacy (degrees-of-freedom) surfacing: pre-run IS-window readout
  (bars + span in years for the selected CSV/date range, flags <2yr) and a post-run
  trades-per-optimized-parameter gauge in VALIDATION (<10 red, 30+ green) — the
  overfitting governor that answers "is my in-sample big enough for this search".
- **v26.3** Walk-Forward validation readout: Builder now shows **Walk-forward efficiency**
  (OOS return-per-bar ÷ IS return-per-bar) + **fold consistency** (held X/N folds OOS) +
  OOS net, color-graded. Engine records each fold's train-window length (train_bars) so
  WFE is computed correctly. First of the validation series (next: rolling WF, lockbox #19).
- **v26.2** Builder fields size to their width and wrap instead of stretching to fill the row.
- **v26.1** SCOPE selection survives a strategy switch: the chosen tier (SHORT/MEDIUM/
  LONG/XL/XXL/CUSTOM) is persisted and re-matched against the new strategy's presets
  instead of silently resetting to the first option ("Short").
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
