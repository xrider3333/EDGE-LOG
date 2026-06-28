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

## Roadmap / TODO
All backlog and migration planning lives in **`ROADMAP.md`** (repo root) — the single
source of truth for what's done and what's next: infra consolidation, the EDGELOG web
port (tab-by-tab gaps), engine research items (#11–23), and remaining `optimizer.py`
Streamlit bugs (#1–9). `docs/` holds reference (architecture, go-live, port plan).
Update `ROADMAP.md` as work ships; keep this file for durable context/conventions only.

## Guardrails / security (hard lines — keep across sessions)
- **Secrets stay local.** `serviceAccount.json` (Firebase admin key) is backend-only and
  gitignored — NEVER commit it. The Anthropic API key is read from local
  `augur_config.json` only — never from a Firestore job doc, never from the browser.
- **Never handle the user's Firebase login/password.**
- **Runner command channel** only processes commands behind a uid allowlist
  (`--allow-uid`); jobs from other uids are ignored.
- **Git (standing authorization — granted by owner 2026-06-27):** AUTO-COMMIT AND PUSH. After
  any change, bump the website version by 0.1 (`const VERSION` in `index.html`), commit, and
  push to `main` WITHOUT asking — GitHub serves the live site, so the push IS the deploy, and a
  change that isn't pushed is invisible to the owner. Always state the version you pushed. You
  have full standing permission to edit ANY file and to start/restart `EdgeLog.bat`. (Only true
  history-rewrites — force-push to `main`, branch deletion — still warrant a quick heads-up.)
  **Before bumping VERSION: `git fetch` + read the CURRENT `const VERSION` from `index.html`
  (don't assume the next number), and `git diff index.html` to confirm ONLY your changes are
  staged.** A second Claude session may be committing to this same repo/working tree
  concurrently (e.g. the trades-table work that jumped 36.0→36.5) — fetch-first avoids
  version clashes and clobbering its in-flight edits.
  **Multi-session protocol (shared working tree):** `git add` ONLY the specific file(s) you
  changed — never `git add -A` / `git add .` (it sweeps in another session's files). Before
  committing, `git diff` your file; if it carries uncommitted edits you did NOT make (another
  agent mid-task on a different feature in the SAME file), do NOT commit — you'd bundle and
  maybe ship its half-finished work. Wait for it to commit/push, then `git pull` and rebuild
  on top. Different tabs/features rarely touch the same code, but they share `index.html` and
  the `VERSION` line, so always verify your diff before pushing.
- **Keyless-AI doctrine** (the documented AUGUR convention): prefer a file-handoff through
  the Claude Code session over direct paid-CLI spend. NOTE: `make_pine`/`review_pine`
  currently call the provider directly (qwen/claude-cli/anthropic) — this is the open
  exception tracked in `ROADMAP.md` §1.

## Working style the user likes
Iterative, version-bumped releases (`__version__`), each targeting specific bugs/features.
Validate before shipping. Explain what changed and any honest caveats. Confirm before
destructive actions. Don't over-format. The user is sharp at reproducing and describing
bugs precisely — trust their repro steps.
