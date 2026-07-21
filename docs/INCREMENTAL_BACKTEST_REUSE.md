# Incremental Backtest Reuse — scoping doc (ROADMAP §3 #26)

**Status:** proposed, not started. This is a hand-off spec so another Claude session can pick
it up cold. Owner idea (2026-07-21): *"a way for auto-validate to compile/use similar past
runs to speed up backtesting — if we add/change a small section or add dates, it shouldn't
need a whole engine rerun to recalc something already computed."*

**One-line goal:** never recompute a (config × data) backtest the runner has already computed.
Most of the win is a **result cache**; the rest is careful invalidation and a couple of
window tricks. Build (a) first — it captures ~all the savings on its own.

**Corrections after code-mapping (2026-07-21):** verified against the real engine. The key gains
ML/sizing params + bar-index slice bounds (and caches `mc_sims==0` runs only); the wire-in covers
**THREE** eval paths (grid `augur_mp_worker.eval_chunk`, auto/validate `augur_engine.auto`'s
`make_slice_evaluator.ev`, and the default `engine.run_backtest`), not just one; the cache is an
**engine-level sidecar** (the runner opens no SQLite of its own); and it ships behind an
`AUGUR_TRIAL_CACHE` flag (default OFF) until the correctness harness passes. Details inline below.

---

## 1. Why it matters (the waste today)

A backtest job (grid / auto / **auto-validate**) evaluates the same strategy over hundreds of
parameter configs, each config = one full run over the price array. Reruns are common and
mostly redundant:

- **Comparison / tuning reruns** re-evaluate a config set that overlaps 60–95% with a prior run
  (owner widens ONE knob's range, or re-runs a champion with a slightly different exit sweep).
- **Window nudges** (`date_to` moved two weeks) re-run the *entire* search from scratch even
  though the strategy logic and 95% of the bars are identical.
- **Auto-validate** is the worst offender because it is the heaviest job: in-sample sweep +
  walk-forward folds + lockbox + robustness suite. A tiny change re-pays the whole bill.

The engine already slices the master array cheaply by date (`load_master_arrays(date_from,
date_to)` — see ROADMAP §2 Builder) and factorizes `day_id` after slicing, so the *data prep*
is not the bottleneck — the **per-config backtest loop** is.

## 2. Architecture — three layers, ship in order

### (a) Trial-level result cache  ← the core win, build this first

Memoize each single-config backtest result, keyed by a hash that captures everything that can
change the numbers:

```
key = sha1(join([
  strategy_file_sha,      # SHA-256 of the strategy .py TEXT (not mtime — content). NB: the
                          #   loader (strategies.py) keys on MTIME today — NO content hash
                          #   exists yet, so add a sha256(file-bytes) helper (memoize by mtime).
  ENGINE_CACHE_EPOCH,     # bumpable int in augur_engine/__init__.py (add it beside __version__)
  canonical_params,       # params sorted by key, floats rounded to a fixed precision, JSON
  ml_filter, ml_threshold, ml_min_history, ml_refit_every,   # ML-gate overlay changes PnL
  sizing,                 # sizing overlay changes PnL (canonicalize like params)
  master_id,              # the master CSV id (instrument+timeframe+source), NOT the filename
  data_fingerprint,       # sha1 of (first_bar_ts, last_bar_ts, bar_count) of the sliced window
  slice_a, slice_b,       # bar-index slice bounds — the AUTO/VALIDATE path slices arrays[a:b]
                          #   by INDEX, not by date; fold the bounds in or WF folds false-hit
  date_from, date_to,     # the exact window (grid path)
  cost_pts,               # commission + slippage that feeds PnL
  session,                # rth/eth etc.
]))
# Cache ONLY mc_sims==0 runs — Monte-Carlo (mc_sims>0) is RANDOM; never cache a random result.
value = {total_pnl, num_trades, win_rate, profit_factor, max_drawdown, avg_pnl, wins,
         losses, equity_downsampled?, trades?}   # whatever run_backtest returns
```

- **Store:** a new SQLite table `trial_cache(key TEXT PRIMARY KEY, value_json TEXT, created,
  strategy_file_sha, master_id, engine_epoch)` in a **sidecar `trial_cache.db`** owned by a new
  engine-level module (put it beside `augur_engine/history.py` — the only engine-side SQLite
  today). The **runner opens no SQLite of its own**, so "in the runner's DB" from an earlier
  draft is wrong. WAL mode + `INSERT OR REPLACE` (idempotent — safe against the stacked-runner
  double-execute hazard CLAUDE.md warns about). Auto-migrate via the
  `PRAGMA table_info`+`ALTER TABLE ADD COLUMN` idiom (mirror `optimizer.py`'s `_db_init_extras`,
  ~L700). Index on `(strategy_file_sha, master_id)` so a strategy/data change can bulk-evict.
- **Wire-in (THREE paths — do all, or auto-validate gets zero benefit):**
  1. **Grid** — `augur_mp_worker.eval_chunk` (separate ProcessPool workers; the doc's old
     `_mp_eval_chunk` name = the *Streamlit* app's worker). Workers can't see timestamps, so pass
     the CONSTANT key material (strategy_file_sha, ENGINE_CACHE_EPOCH, master_id,
     data_fingerprint, cost_pts, session, ml/sizing params) into `init_worker` as an initarg
     dict; only `params` varies per config. Short-lived SQLite connection per chunk (WAL).
  2. **Auto / auto-validate** — `augur_engine/auto.py` `make_slice_evaluator.ev(a,b,params)`
     (single-process, single-thread). THIS is the heaviest job (~2k–8k evals/run) and the old
     draft missed it entirely. Key includes the `(a,b)` slice bounds.
  3. Also the `run_grid` single-thread branch (`optimize.py`) and top-level `engine.run_backtest`
     (the default `backtest` job) for completeness.
  On hit → return the cached value; on miss → compute then insert. ALL paths gated by one enable
  flag (`AUGUR_TRIAL_CACHE`, default OFF) so it ships dark and flips on only after the harness
  passes.
- **Hit rate:** exact-config reruns hit 100%; a "widen one knob" rerun hits on every config
  that didn't change. Expected 60–95% fewer `run_backtest` calls on a typical rerun.
- **Safety:** exact-hit reuse only. If ANY key field differs, it's a miss → recompute. No
  approximation, no interpolation. This alone is safe to ship.

### (b) Data-prep memoization  ← cheap add, do with (a)

The per-window array load + `day_id` factorization + data-quality/health check is repeated on
every job over the same master+window. Cache the *prepared arrays* (or at least the health
verdict) keyed by `(master_id, data_fingerprint, date_from, date_to, session)`. Saves the
fixed per-job overhead; independent of the trial cache.

### (c) Window-extension deltas  ← LATER / research, gated per-strategy

When only `date_to` moves forward (window is a superset), you *cannot* blindly reuse — indicator
warm-up state and open positions cross the old boundary. But for strategies that are **flat at
end-of-day** (ORB-style; the engine already knows EOD-flat setups), you can:

1. Reuse all trades that closed at/before the last fully-computed flat point.
2. Recompute only from that flat point forward over the appended bars.

Requires a per-strategy `stateless_at_eod` capability flag (default **false** = never delta,
always full recompute). Only turn on where proven. This is the only layer that can be *wrong*
if mis-scoped, so it stays opt-in and last.

## 3. Cache invalidation — the hard part (get this right or ship nothing)

A stale hit returns confidently-wrong numbers, which is worse than slow. Rules:

- **Strategy code change → miss.** The key includes the strategy file's content SHA, so any
  edit (even a comment) changes the key. Coarse but correct. (Optional refinement later: hash
  only the compiled logic, so comment-only edits still hit — NOT for v1.)
- **Engine change → miss.** Bump `ENGINE_CACHE_EPOCH` in `augur_engine` whenever the backtest
  math changes; it's in the key. The runner should log its epoch on boot.
- **Data change → miss.** `data_fingerprint` = hash of (first ts, last ts, bar count) of the
  *sliced* window. A master that auto-synced new bars changes the fingerprint for any window
  that now includes them → miss. (This is exactly the silent-slide bug class CLAUDE.md warns
  about — the fingerprint makes a slid window a cache MISS, not a false hit.)
- **Cost/session change → miss** (both in the key).
- **Never cache incomplete/aborted runs** — insert ONLY after `fn(...)` returns a complete
  result. (The engine paths don't actually thread `_stop_event`/`_pause_event`; abort raises
  `_JobStopped(BaseException)` out of `process_job`, discarding the in-flight config — so "insert
  only on clean return" is inherently safe: there is no partial object to store.)

Pinned **comparison reruns** (CLAUDE.md hard rule: same window + same master) become a pure
exact-hit reuse by construction — the safe case, and a nice free speed-up for the owner's most
discipline-sensitive workflow.

## 4. Correctness harness (before trusting it on real reruns)

1. **Golden equality:** run any job twice with the cache OFF, then ON; assert byte-identical
   `top10_results` / summary. Any diff = a key is missing a field that affects PnL.
2. **Invalidation tests:** flip each key field (edit strategy, bump epoch, extend window, change
   cost) and assert a MISS + recompute each time.
3. **Concurrency:** two runner processes writing the same key must not corrupt (SQLite
   `INSERT OR REPLACE`, WAL mode).
4. **No-silent-cap logging:** log per-job `cache: X/Y configs reused (Z% saved)` so a reuse is
   visible, never mistaken for "it ran everything."

## 5. Web / UX surfacing (small, optional)

- Builder RUNS row: a `♻ 812/900 reused` chip so the owner *sees* the speed-up and that it was
  a reuse, not a fresh compute.
- Settings: a "clear backtest cache" button + a size readout (the cache is disposable — it can
  always be rebuilt by recomputing).

## 6. Explicit non-goals (v1)

- No approximate / nearest-neighbour reuse. Exact hits only.
- No cross-strategy reuse (different file SHA = different everything).
- No delta for non-EOD-flat strategies.
- Not tied to the web port work — this is a runner/engine change and can land independently.

## 7. Suggested build order for the next session

1. `trial_cache` table + read-through in the per-config eval path (layer a) + golden-equality
   test. **This is 80% of the value.**
2. Per-job reuse logging + Builder chip.
3. Data-prep memoization (layer b).
4. (Research spike) EOD-flat window-extension delta (layer c) behind a per-strategy flag.

Cross-references: ROADMAP §3 #26 (the one-liner), `BACKTESTING_STACK.md` (job pipeline),
CLAUDE.md "Comparison reruns PIN the data window AND the master" (why data_fingerprint must
make a slid window a miss).
