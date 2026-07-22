"""EOD-flat window-extension delta (PR4 of "Incremental Backtest Reuse").

See docs/INCREMENTAL_BACKTEST_REUSE.md §2(c) + §4 for the full design. In one
line: when a rerun's window is a FORWARD EXTENSION (same date_from, larger
date_to) of a window this feature has already computed IN FULL for the
identical (strategy, params, master, session, cost, ml, sizing), and the
strategy has opted in via a module-level `STATELESS_AT_EOD = True`, reuse the
trades from the cached window unchanged and recompute the strategy logic ONLY
over the newly-appended bars -- then splice the two gross trade lists back
together in chronological order. `engine.run_backtest` re-derives the window's
headline metrics from that spliced list via the SAME `_apply_costs` function
the full-recompute path already uses, so the two are provably identical (see
below) rather than merely "usually agree."

GUIDING PRINCIPLE (same as trial_cache.py): a stale/wrong delta is a
confidently-wrong backtest -- real money risk. So every function here is
designed to fail toward a FULL RECOMPUTE:
  - try_extend() returns None -- "do a normal full recompute" -- the instant
    ANY precondition isn't cleanly satisfied, or on ANY internal exception.
    It never guesses and never returns a partial/best-effort result.
  - record_full() (the write side) silently no-ops on any failure -- a
    caching write must never turn an already-successful backtest into an
    error.
  - Activation requires ALL of: trial_cache.is_enabled(), the strategy's own
    `STATELESS_AT_EOD` opt-in, cost_pts > 0, and both date_from/date_to
    present as explicit values (never an open-ended/blank date_to -- the
    exact hazard CLAUDE.md's comparison-rerun hard rule warns about).

WHY cost_pts > 0 specifically (a deliberate narrowing beyond the spec's
literal precondition list): it is what makes "byte-identical" a STRUCTURAL
guarantee instead of a hopeful one. `engine.run_backtest` only ever calls
`_apply_costs` (which re-derives total_pnl/win_rate/profit_factor/
max_drawdown/avg_pnl/wins/losses from a trade list via a fixed, cost-
independent aggregation formula) when cost_pts > 0; at cost_pts == 0 it
returns the strategy's OWN unprocessed native dict instead. Since this module
also always merges through `_apply_costs` (engine.py does this uniformly for
both the delta and full-recompute paths -- see engine.run_backtest), a delta
result is trivially and PROVABLY equal to a full recompute of the same window
whenever cost_pts > 0: both are literally "`_apply_costs` applied to a trade
list with identical values in identical order," and the identical-values-and-
order part is exactly what the day-block-independence contract implied by
STATELESS_AT_EOD guarantees (see _run_tail's docstring). At cost_pts == 0
there is no such structural guarantee -- this module would have to trust that
an arbitrary future strategy's own native aggregation formula (which it has
no way to inspect) is bit-for-bit identical to `_apply_costs`'s, which is not
provable in general (floating-point summation is not associative, and numpy
vs. plain-Python accumulation can legitimately differ in the last bit). Rather
than gamble on that, PR4 simply declines at cost_pts == 0 and falls back to a
full recompute, exactly like every other unmet precondition.

SCOPE (deliberately narrow for v1): only wired into `engine.run_backtest` (the
single-config "default backtest job" path docs/INCREMENTAL_BACKTEST_REUSE.md
§2(a) names as in scope for completeness). NOT wired into the grid worker
(augur_mp_worker.eval_chunk), augur_engine.optimize.run_grid, or
augur_engine.auto's slice evaluators -- those sweep many DIFFERENT param
configs per job, where the trial-level scalar cache (PR1) already captures
the overwhelming majority of the win; a window-extension delta for a
multi-thousand-config sweep is a much bigger correctness surface (every
config would need its own stored trade list) for a proportionally smaller
marginal benefit, and is left for a future PR if ever needed.

STATELESS_AT_EOD is a TRUST contract, not a verified property: this module
correctly identifies the day boundary and correctly splices/offsets trade
indices, but it has no way to confirm a given strategy's run_backtest is
truly free of state that crosses a day boundary (e.g. a multi-day rolling
indicator) -- that property is exactly what a strategy author asserts by
setting the flag. Per the hard instruction this PR ships under, the flag is
NOT set on any real strategy file -- only on the synthetic strategies in
tests/test_window_delta.py.
"""
import hashlib
import inspect
import json
import os
import sqlite3

import numpy as np

from . import trial_cache as TC
from .data import load_master_arrays

_TABLE = "window_cache"

# Best-effort in-process counters, mirroring trial_cache._STATS -- lets a test
# (or a future runner log line) distinguish "the delta genuinely fired" from
# "the normal fallback path happened to produce the right answer anyway."
_STATS = {"hits": 0, "misses": 0}


def record_hit():
    _STATS["hits"] += 1


def record_miss():
    _STATS["misses"] += 1


def get_stats():
    return dict(_STATS)


def reset_stats():
    _STATS["hits"] = 0
    _STATS["misses"] = 0


def _eligible(mod, cost_pts, date_from, date_to) -> bool:
    """Shared precondition gate for both try_extend (read) and record_full
    (write) -- ONE function so the two can never drift apart on when this
    feature is allowed to activate at all. See module docstring for why
    cost_pts > 0 is required."""
    return bool(
        TC.is_enabled()
        and getattr(mod, "STATELESS_AT_EOD", False)
        and cost_pts and cost_pts > 0
        and date_from and date_to
    )


def _window_key(ctx: dict, params: dict) -> str:
    """Like trial_cache.make_key, but DELIBERATELY excludes `date_to` and
    `data_fingerprint` -- matching ACROSS a larger date_to is the entire point
    of a window-extension key (the prefix's unchanged-ness is verified
    separately, via a fresh fingerprint re-slice at use time -- see
    try_extend). Everything else mirrors make_key's field list and its
    JSON-array-before-hashing rationale (see that function's docstring)."""
    ctx = ctx or {}
    fields = [
        ctx.get("strategy_file_sha"), ctx.get("engine_epoch"),
        TC.canonical_params(params),
        ctx.get("ml_filter"), ctx.get("ml_threshold"),
        ctx.get("ml_min_history"), ctx.get("ml_refit_every"),
        TC.canonical_params(ctx.get("sizing") or {}),
        ctx.get("master_id"), ctx.get("date_from"),
        ctx.get("cost_pts"), ctx.get("session"),
    ]
    blob = json.dumps(fields, separators=(",", ":"), default=str)
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()


def _content_hash(arrays) -> str:
    """A sha1 over the ACTUAL open/high/low/close/volume VALUES of a window --
    deliberately STRONGER than data.py's own `arrays["fingerprint"]`, which by
    design is only sha1(first_ts|last_ts|bar_count) of the sliced window (see
    that module's docstring): built to catch a SLID window (new bars synced
    under a blank date_to), it does NOT change if an already-covered
    historical bar's PRICE is corrected in place without touching the row
    count or the first/last timestamp. window_delta specifically straddles
    that risk -- its entire purpose is reusing OLDER cached data across time,
    so a silent revision to a bar inside the already-cached prefix is exactly
    the failure mode a "when in doubt, miss" cache must not paper over. This
    is used ONLY as window_delta's own prefix-integrity check (try_extend
    below); it never touches or replaces data.py's fingerprint, which keeps
    doing its own job (PR1's exact-hit key, PR3's memo key) unchanged."""
    h = hashlib.sha1()
    for k in ("open", "high", "low", "close", "volume"):
        v = arrays.get(k)
        if v is not None:
            h.update(np.ascontiguousarray(v, dtype=np.float64).tobytes())
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────────
# Storage — its OWN table in the same sidecar DB trial_cache.py uses (a
# separate concern from the scalar `trial_cache` table: this one stores full
# GROSS, pre-cost trade lists, keyed WITHOUT date_to so a later, larger
# date_to can look up the best prior window to extend from).
# ─────────────────────────────────────────────────────────────────────────

def _db_path() -> str:
    return TC._db_path()   # same env-override-aware sidecar path as trial_cache.py


def _conn():
    """Short-lived connection, WAL mode, INSERT OR REPLACE idempotent writes --
    identical safety posture to trial_cache._conn (see that function's
    docstring): two writers racing the same (ctx_key, date_to) just both
    succeed, last commit wins, never an exception from the race itself."""
    path = _db_path()
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            ctx_key           TEXT,
            date_to           TEXT,
            trades_json       TEXT,
            fingerprint       TEXT,
            n_bars            INTEGER,
            created           TEXT,
            strategy_file_sha TEXT,
            master_id         TEXT,
            engine_epoch      INTEGER,
            PRIMARY KEY (ctx_key, date_to)
        )
    """)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_ctx ON {_TABLE}(ctx_key)")
    return conn


def _store(ctx_key, date_to, trades, fingerprint, n_bars, *,
          strategy_file_sha, master_id, engine_epoch) -> None:
    """INSERT OR REPLACE the full window's GROSS (pre-cost) trade list. May
    raise (bad JSON, DB error) -- every caller wraps this in its own
    try/except (a store failure must never surface as a computation error)."""
    payload = json.dumps(list(trades), default=TC._json_default)
    conn = _conn()
    try:
        conn.execute(
            f"INSERT OR REPLACE INTO {_TABLE} "
            f"(ctx_key, date_to, trades_json, fingerprint, n_bars, created, "
            f" strategy_file_sha, master_id, engine_epoch) VALUES (?,?,?,?,?,?,?,?,?)",
            (ctx_key, date_to, payload, fingerprint, int(n_bars), "",
             strategy_file_sha, master_id, engine_epoch))
        conn.commit()
    finally:
        conn.close()


def _lookup(ctx_key, max_date_to):
    """The cached row with the LARGEST date_to <= max_date_to for this
    ctx_key, or None on a miss OR ANY error (corrupt row, locked/missing DB,
    missing table, bad JSON -- every failure mode is just a miss, mirroring
    trial_cache.get's own fail-open contract). date_to strings compare
    lexicographically == chronologically for the YYYY-MM-DD format this
    codebase uses throughout."""
    try:
        conn = _conn()
        try:
            row = conn.execute(
                f"SELECT date_to, trades_json, fingerprint, n_bars FROM {_TABLE} "
                f"WHERE ctx_key=? AND date_to<=? ORDER BY date_to DESC LIMIT 1",
                (ctx_key, max_date_to)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        date_to, trades_json, fingerprint, n_bars = row
        trades = [tuple(t) for t in json.loads(trades_json)]
        return {"date_to": date_to, "trades": trades, "fingerprint": fingerprint,
                "n_bars": n_bars}
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────
# The tail recompute
# ─────────────────────────────────────────────────────────────────────────

def _run_tail(mod, arrays, params, split, n_total):
    """Call the strategy's OWN run_backtest on JUST arrays[split:n_total]
    (gross, pre-cost, return_trades=True) -- the exact same kwarg-detection
    pattern (volumes/day_id/index passed only if the plugin declares them)
    engine.run_backtest and auto.make_slice_evaluator already use, so a
    day_id-driven strategy sees THE SAME kind of slice a walk-forward fold
    evaluator already hands it today (day_id is NOT re-based to 0 for the
    slice, same as there -- a day_id-aware strategy only ever compares day_id
    for EQUALITY within its own slice to find day-block boundaries, e.g.
    ORB_1_0.py's `while j < n and did[j] == did[i]`, never against a literal/
    absolute value, so an un-rebased day_id is safe).

    Each returned trade tuple's first two elements are then shifted by
    `+split` so they land on the FULL window's own bar numbering -- the
    documented (entry_idx, exit_idx, pnl[, side, entry_px]) convention every
    strategy in this repo follows (see ORB_1_0.py and conftest.py's own
    `trades_from_pnls` fixture). If a trade tuple doesn't fit that shape
    (fewer than 2 elements, or non-integer index fields), this returns None
    rather than guess at an unshiftable index -- a decline, not a silent
    wrong offset.

    Returns a possibly-empty list of trade tuples, or None on any exception
    or unusable shape (never raises)."""
    try:
        fn = mod.run_backtest
        sp = inspect.signature(fn).parameters
        has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
        O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
        V, did, IDX = arrays.get("volume"), arrays.get("day_id"), arrays.get("index")
        ex = {}
        if V is not None and (has_kw or "volumes" in sp):
            ex["volumes"] = V[split:n_total]
        if did is not None and (has_kw or "day_id" in sp):
            ex["day_id"] = did[split:n_total]
        if IDX is not None and (has_kw or "index" in sp):
            ex["index"] = IDX[split:n_total]
        res = fn(O[split:n_total], H[split:n_total], L[split:n_total], C[split:n_total],
                 return_trades=True, **ex, **params)
        if not isinstance(res, dict):
            return []
        trades = res.get("trades")
        if not trades:
            return []
        shifted = []
        for t in trades:
            if len(t) < 2:
                return None
            nt = list(t)
            try:
                nt[0] = int(nt[0]) + split
                nt[1] = int(nt[1]) + split
            except (TypeError, ValueError):
                return None
            shifted.append(tuple(nt))
        return shifted
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────
# Public entry points — called from engine.run_backtest
# ─────────────────────────────────────────────────────────────────────────

def try_extend(mod, arrays, params, *, cost_pts, session, date_from, date_to, master,
               ml_filter=None, ml_threshold=0.50, ml_min_history=30, ml_refit_every=25,
               sizing=None):
    """Attempt the window-extension delta. `arrays` MUST be the caller's
    already-loaded FULL [date_from, date_to] window (as engine.run_backtest
    always has by the time it could call this). Returns the full window's
    GROSS (pre-cost) trade list -- cached prefix trades unchanged, ++ freshly
    computed & index-shifted tail trades -- on a successful, provably-safe
    delta, or None ("do a normal full recompute") the instant any
    precondition isn't cleanly satisfied or on ANY internal exception. Never
    raises. See module docstring for the full precondition list.

    A caller (engine.run_backtest) is expected to then (a) compute the
    returned window's headline metrics via `_apply_costs({"trades": result},
    cost_pts)` -- this function deliberately does NOT do that itself (keeps
    this module independent of engine.py, avoiding any import-order coupling)
    -- and (b) call record_full(...) with the same result if it wants THIS
    (now-extended) window persisted for a future further extension to chain
    off of. try_extend() itself only READS the store; it never writes, so
    calling it directly (e.g. for testing) has no persistence side effect."""
    if not _eligible(mod, cost_pts, date_from, date_to):
        return None
    try:
        ctx = TC.build_ctx(mod, arrays, cost_pts=cost_pts, session=session,
                           date_from=date_from, date_to=date_to,
                           ml_filter=ml_filter, ml_threshold=ml_threshold,
                           ml_min_history=ml_min_history, ml_refit_every=ml_refit_every,
                           sizing=sizing, master=master)
        if ctx is None:
            record_miss()
            return None
        key = _window_key(ctx, params)

        cached = _lookup(key, date_to)
        if cached is None or cached["date_to"] >= date_to:
            record_miss()          # no prior window, or nothing STRICTLY smaller to extend from
            return None

        # Re-slice the master at the CACHED window's exact date_to using the
        # SAME load_master_arrays function that produced it in the first
        # place -- never hand-roll date-boundary arithmetic here. This gives
        # (a) the exact bar-count split point, guaranteed day-boundary-aligned
        # since load_master_arrays' date_to slicing is inclusive-of-the-
        # whole-day, and (b) a FRESH content hash of that exact sub-window to
        # detect a data revision (e.g. a correction landed on an already-
        # cached historical day) since the entry was stored -- see
        # _content_hash's docstring for why this is a STRONGER check than
        # data.py's own cheap (first_ts,last_ts,n_bars) fingerprint.
        prefix_arrays = load_master_arrays(master, date_from=date_from, date_to=cached["date_to"])
        if _content_hash(prefix_arrays) != cached.get("fingerprint"):
            record_miss()          # prefix data changed under us -- full recompute
            return None
        split = len(prefix_arrays["close"])
        n_total = len(arrays["close"])
        if split <= 0 or split > n_total:
            record_miss()
            return None

        tail_trades = []
        if split < n_total:
            tail_trades = _run_tail(mod, arrays, params, split, n_total)
            if tail_trades is None:
                record_miss()      # strategy raised / unusable trade shape on the tail
                return None

        merged = list(cached["trades"]) + tail_trades
        record_hit()
        return merged
    except Exception:
        record_miss()
        return None


def record_full(mod, arrays, params, *, cost_pts, session, date_from, date_to, master,
                ml_filter=None, ml_threshold=0.50, ml_min_history=30, ml_refit_every=25,
                sizing=None, gross_trades) -> None:
    """Persist a FRESH, from-scratch full-window GROSS (pre-cost) trade list
    so a LATER forward-extension request can delta off it. Mirrors
    try_extend's own eligibility gate exactly (via the shared _eligible()) so
    the two can never activate under different conditions. Called by
    engine.run_backtest right after a normal (non-delta) compute succeeds,
    AND after a delta itself (so a chain of extensions always builds on the
    newest window). Best-effort: any failure is swallowed -- never turns an
    already-successful backtest into an error; the next request simply won't
    find a cached window and will fall back to a full recompute, same as
    today."""
    if not _eligible(mod, cost_pts, date_from, date_to) or not gross_trades:
        return
    try:
        ctx = TC.build_ctx(mod, arrays, cost_pts=cost_pts, session=session,
                           date_from=date_from, date_to=date_to,
                           ml_filter=ml_filter, ml_threshold=ml_threshold,
                           ml_min_history=ml_min_history, ml_refit_every=ml_refit_every,
                           sizing=sizing, master=master)
        if ctx is None:
            return
        key = _window_key(ctx, params)
        n_total = len(arrays["close"])
        _store(key, date_to, list(gross_trades), _content_hash(arrays), n_total,
              strategy_file_sha=ctx["strategy_file_sha"], master_id=ctx["master_id"],
              engine_epoch=ctx["engine_epoch"])
    except Exception:
        pass
