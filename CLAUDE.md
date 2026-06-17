# AUGUR — Strategy Optimizer (project context for Claude Code)

## What this is
Augur is a **Streamlit** desktop app (single file: `optimizer.py`, ~5300 lines) for
**backtesting and optimizing trading strategies**. It runs pluggable Python "strategy
plugin" files against OHLCV price data (TradingView CSV exports or Yahoo Finance pulls).
It is NOT a Pine Script backtester — strategies are Python ports of Pine logic.

Owner: an active futures trader (ES/MES/NQ/MNQ/etc.). Works on Windows (PowerShell + a
`.bat` launcher) and iPad. Prefers an iOS-glass / minimalist look, monochrome icons,
minimal vertical space, readable text, and confirm-before-destructive-actions.

## Run / restart
- Launch: `streamlit run optimizer.py` (the user has a `.bat` that loops it).
- A loud banner prints at startup: `AUGUR vX.Y.Z — running from this file` — use it to
  confirm the running version. Also: `findstr "__version__" optimizer.py`.
- After editing, the user fully restarts (Ctrl+C, Y to terminate, relaunch) and
  hard-refreshes the browser (Ctrl+Shift+R).

## Layout on disk (Windows)
- `optimizer.py` — the whole app.
- `augur_strategies/` — strategy plugin `.py` files (currently engu.py, engu_v25.py,
  plus user files like GROK_ENGU__I__V20.py, ENGU_II.py, ENGU_3__CLAUDE_.py).
- `augur_uploads/` — saved CSVs (CSV_DIR). Masters live here too.
- `augur_watch/` + `augur_watch/_ingested/` — drop-folder for TradingView exports that
  auto-refresh ingests into masters on app open.
- `optimizer_history.db` — SQLite. Tables: `runs`, `strategies`, `csv_files`,
  `executions`. All have auto-migration blocks that ADD missing columns on connect.
- `augur_config.json` — persisted settings (active_strategy, workers, anthropic_key,
  autorefresh).

## Strategy plugin contract (REQUIRED of every strategy file)
Module-level globals:
- `STRATEGY_NAME: str`
- `DEFAULT_PARAMS: dict` — {param_name: {type:'int'|'float'|'bool'|'str', min, max, step,
  default, label, tooltip, optional depends_on:{other_param:value}}}
- `PARAM_GRID_PRESETS: dict` — {label: {param: [values...]}}. Labels conventionally start
  with a tier word: "Short …", "Medium …", "Long …", "XL …", "XXL …".
- `run_backtest(opens, highs, lows, closes, **params, return_trades=False,
  _stop_event=None, _pause_event=None) -> dict` returning at least: total_pnl,
  num_trades, win_rate, profit_factor, max_drawdown, avg_pnl, wins, losses.
- PNL convention: `SHARES*(EXIT-ENTRY)+FEE` (fees included).

## Key architecture in optimizer.py
- `INSTRUMENTS` dict: {short_key: {ticker, multiplier}} (ES→ES=F, mult 50; MES mult 5; etc.).
- `_load_strategy_module(path)` — mtime-cached loader (`_STRAT_MOD_CACHE`), keyed by
  filepath, returns distinct module objects per file. Uses fixed spec name "augur_strategy"
  but caching is by path (verified no cross-contamination).
- `get_strategy_registry()` — @st.cache_resource singleton holding current_path/current_module.
- `_ExecManager` (@st.cache_resource singleton) — ThreadPoolExecutor; runs backtests in a
  worker thread, writes progress to SQLite `executions`. `_run_job` branches on
  `config["opt_mode"]`: "grid" (exhaustive, parallelized via ProcessPoolExecutor
  `_mp_eval_chunk` workers that reload the strategy from file path per process) vs "auto"
  (Bayesian/random `_AutoSampler`, single-thread, seed=42).
- Scopes (in the Executions "Scope" dropdown): tiers SHORT/MEDIUM/LONG/XL/XXL (grid
  presets), CUSTOM, 🤖 AUTO-OPTIMIZE (smart search), 🧠 AI OPTIMIZE, 🧬 AI EVOLVE.
- AI scopes (agentic, need Anthropic API key in Settings): `ai_run_one_round(session,
  api_key)` runs a round (sweep → in-sample/out-of-sample validate → Claude proposes next
  ranges, and in Evolve, optional code rewrite → apply → repeat). Helpers: `_split_is_oos`
  (75/25), `ai_propose_next` (model claude-sonnet-4-20250514), `validate_strategy_code`
  (compile+contract+smoke-test before running AI-written code), `_promote_evolved_strategy`
  (auto-saves evolved strategy to Library), `_ai_save_to_history`. Driven by a
  @st.fragment(run_every="1s") round driver in the Executions tab.
- Master CSVs: `combine_ohlcv_frames` (dedupe overlaps, detect gaps→segments, tag row
  source), `save_master_csv` (extend-in-place via overwrite_filename), `find_master`,
  `list_masters`, `_csv_in_master` (exact via provenance source_csv_ids, else inferred by
  date-span overlap), `recommend_masters`, `auto_refresh_masters` (Yahoo pull + watch-folder
  ingest on app open). Masters keyed by instrument+timeframe+source (tv vs yahoo).

## CRITICAL Streamlit gotchas (hard-won — keep in mind)
- **Widget state on rerun**: relying on a widget `key` to persist a value FAILS when the
  options list is rebuilt on a strategy-switch `st.rerun()` — Streamlit silently resets to
  the first option / default. FIX PATTERN (used for the Scope dropdown and Trials slider):
  store the value in your OWN session_state var (e.g. `_scope_tier_committed`,
  `_ntrials_committed`), drive the widget's `index`/`value` from it, DON'T pass a widget
  key, and write the widget's return value back into your var each render. This is the
  single most important lesson — several bugs traced to this.
- `st.tabs` resets to the first tab on a full app rerun → wrap tab bodies in @st.fragment.
- A fragment with `run_every` that does an app-scoped rerun INTERRUPTS user clicks; scope
  reruns narrowly.
- Functions used at module-load must be defined earlier; functions only CALLED at runtime
  can be defined later (caused several NameErrors when moved).
- str_replace edits: a too-broad old_str can delete adjacent code (once deleted a
  `def _render_results` header → NameError). Re-view after edits.
- Glyphs: gear ⚙ renders blank on the user's system; use Geometric Shapes block
  (◫◎▦◆) with `font-variant-emoji:text`.
- `use_container_width` is deprecated in the user's Streamlit — replace with `width`
  (a current warning in the logs; not yet fixed).
- pip in this environment: `pip install X --break-system-packages`.

## A load-test harness exists for blind testing
`/tmp/loadtest.py` (in the dev sandbox) mocks streamlit and execs the backend half of the
file (split at the marker comment `#  AUGUR v4.0  —  UI Layer`). "↪ hit st.rerun()" = the
backend imported and ran without error. In Claude Code you can instead just RUN the app.

## Current state (v5.8.5) and OPEN ITEMS
Recently fixed: the "identical PNL/trades across different strategies" bug — root cause was
the Scope dropdown AND Trials slider silently resetting on strategy-switch reruns (so all
runs used a stale fallback grid). Both now use the committed-state pattern above. Confirmed
fixed: three different strategy files now produce three different code hashes and run their
own code.

**Known open bugs / TODO (numbered):**
1. **Results shows only the most-recent completed run** — when several runs are queued and
   complete, the live Results panel hydrates only the latest; earlier ones are in Past Runs
   but not shown live. (Look at the "Hydrate freshly-completed results" loop near the
   `# Status / Run dock` section and the per-exec results hydration keyed by exec_uuid.)
2. Replace all `use_container_width=` with `width=` (Streamlit deprecation in logs).
3. Auto-Optimize has NO out-of-sample validation — it can report unrealistically high
   (overfit) PNLs with no warning. The AI scopes have a 75/25 OOS toggle (default on);
   port the same in-sample-vs-out-of-sample readout/guardrail to Auto-Optimize. (User is
   seeing ~162k PNL on 1 ES contract over ~3 weeks of 1-min data — almost certainly overfit.)
4. Page/layout/speed/navigation audit (user wants all of: faster reruns, fewer clicks to
   launch, less scrolling). Sub-ideas: cache stable per-rerun queries; scope the AI round
   driver's rerun tighter; lazy-build Results charts; a re-run-last / Quick Run button;
   remember last instrument/timeframe/strategy/scope.
5. Cost estimate (tokens/$ per round) in the AI panel.
6. Compare evolved-vs-original strategy in Results (PNL delta + code diff).
7. Walk-forward / rolling out-of-sample validation (beyond the single 75/25 split).
8. Optimistic-vs-pessimistic intrabar fill toggle for engu/v25 (stop-vs-target fill order).
9. Relabel a SUBSET of runs in Past Runs (backend `set_runs_strategy` exists; only
   "Apply to ALL" is surfaced).
10. Auto-detect instrument from CSV filename/symbol on upload.

**Expert-level backtesting additions (research-grade TODO — drawn from Pardo
"Evaluation & Optimization of Trading Strategies", Bandy, Aronson "Evidence-Based
TA", López de Prado "Advances in Financial ML", Chan, Tomasini/Jaekle):**
11. **Deflated performance / multiple-testing haircut** — a grid winner's PF/Sharpe
    is inflated by having searched N configs. Report a deflated Sharpe
    (Bailey/López de Prado) or a "best-of-N expected by pure luck" benchmark next
    to every grid winner. Directly quantifies the best-of-2,304 selection bias.
12. **Neighborhood robustness table** — the winner's ±1-step parameter neighbors'
    PF/PNL in a mini-grid; a real optimum has good neighbors (gives the existing
    PLATEAU verdict concrete numbers).
13. **Regime-sliced report card** — per-config performance by volatility tercile
    (rolling ATR), trend-vs-chop, day-of-week, monthly PnL heatmap. ORB's losses
    cluster in chop regimes — make that visible per run.
14. **MAE/MFE distributions** (max adverse/favorable excursion per trade) — the
    empirical basis for stop/target placement instead of guessed R-multiples.
15. **Risk-of-ruin + bootstrap MC** — extend Monte-Carlo with resample-with-
    replacement, ruin probability for a given account + per-trade risk, and a
    time-to-recovery distribution.
16. **Vol-targeted position sizing layer** — size by ATR so $ risk per trade is
    constant (the 1-contract assumption hides large risk swings across regimes).
17. **Half-day / holiday calendar handling** — Thanksgiving/Xmas-eve sessions
    close 13:00 ET; ORB EOD-flat exits and session stats are subtly wrong those
    days. Tag and exclude (or handle).
18. **Event-day tagging** — FOMC/CPI/NFP dates as a CSV; report PnL with/without
    event days, optional skip-event-days toggle.
19. **Lockbox holdout** — reserve the most recent ~1 year, never optimized or even
    browsed, as the one-shot final pre-deploy gate.
20. **Live-vs-backtest drift monitor** — once paper trading starts, track realized
    fills/PnL vs the engine's prediction for the same signals; alert when tracking
    error leaves a band (catches engine optimism early).
21. **Slippage scaled by volatility/gap** — flat pts/RT understates fast-market
    stop slippage; scale stop-fill slippage with bar range or gap-through size.
22. **Capacity check** — max contracts vs typical volume in the entry bars per
    instrument (ORB trades the open — thick, but get the number).
23. **Order-flow data enrichment (Databento)** — pull CME Globex MDP3 *Trades*
    schema ($28/GB — the practical one; skip MBO/MBP depth for now) and compute
    per-5-min-bar aggressor DELTA (buy vol − sell vol) into enriched masters
    (extra column). Strategies then filter on real buying/selling pressure at
    the breakout — a sharper version of the volume filter (which was ORB's best
    single lever, suggesting flow carries real signal). Also enables stop
    placement beyond liquidity-cluster levels. Deeper history across more
    instruments from the same source helps validate new strategies sooner.

## Working style the user likes
Iterative, version-bumped releases (`__version__`), each targeting specific bugs/features.
Validate before shipping. Explain what changed and any honest caveats. Confirm before
destructive actions. Don't over-format. The user is sharp at reproducing and describing
bugs precisely — trust their repro steps.
