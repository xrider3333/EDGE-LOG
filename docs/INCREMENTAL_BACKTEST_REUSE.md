# Incremental Backtest Reuse — scoping doc (ROADMAP §3 #26)

**Status:** proposed, not started. This is a hand-off spec so another Claude session can pick
it up cold. Owner idea (2026-07-21): *"a way for auto-validate to compile/use similar past
runs to speed up backtesting — if we add/change a small section or add dates, it shouldn't
need a whole engine rerun to recalc something already computed."*

**One-line goal:** never recompute a (config × data) backtest the runner has already computed.
Most of the win is a **result cache**; the rest is careful invalidation and a couple of
window tricks. Build (a) first — it captures ~all the savings on its own.

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
  strategy_file_sha,      # SHA-256 of the strategy .py TEXT (not mtime — content)
  engine_version,         # augur_engine version / a bumpable ENGINE_CACHE_EPOCH constant
  canonical_params,       # params sorted by key, floats rounded to a fixed precision, JSON
  master_id,              # the master CSV id (instrument+timeframe+source), NOT the filename
  data_fingerprint,       # sha1 of (first_bar_ts, last_bar_ts, bar_count) of the sliced window
  date_from, date_to,     # the exact window
  cost_pts,               # commission + slippage that feeds PnL
  session,                # rth/eth etc.
]))
value = {total_pnl, num_trades, win_rate, profit_factor, max_drawdown, avg_pnl, wins,
         losses, equity_downsampled?, trades?}   # whatever run_backtest returns
```

- **Store:** a new SQLite table `trial_cache(key TEXT PRIMARY KEY, value_json TEXT, created,
  strategy_file_sha, master_id, engine_version)` in the runner's DB (or a sidecar
  `trial_cache.db`). Auto-migrate like the other tables. Index on `(strategy_file_sha,
  master_id)` so a strategy/data change can bulk-evict.
- **Wire-in:** in `_mp_eval_chunk` / the per-config eval path (the ProcessPool workers that
  reload the strategy per process), check the cache before calling `run_backtest`; on miss,
  compute then insert. Because workers are separate processes, use a short-lived connection
  per chunk or a read-through cache passed as a dict for the hot set.
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
- **Never cache incomplete/aborted runs** (respect `_stop_event`/`_pause_event` — only insert
  on clean completion).

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
