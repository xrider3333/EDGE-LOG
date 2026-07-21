"""Trial-level backtest result cache (PR1 of "Incremental Backtest Reuse").

See docs/INCREMENTAL_BACKTEST_REUSE.md for the full design. In one line: memoize a
SINGLE-CONFIG backtest result, keyed by a hash of every field that can change the
numbers (strategy content, engine version, params, ML/sizing overlay, data window +
fingerprint, cost, session). An EXACT-hit cache only -- no approximation, no
interpolation, no nearest-neighbour reuse.

GUIDING PRINCIPLE: a stale HIT returns a confidently-wrong backtest -- real money
risk. A MISS just recomputes (slower, never wrong). So every function here is
designed to fail toward MISS:
  - is_enabled() defaults OFF (env unset -> False).
  - get() swallows ANY internal error and returns None (never raises into a caller
    that would otherwise have gotten a correct recomputed value).
  - build_ctx() returns None -- "do not cache this job" -- the instant a REQUIRED
    field (strategy content hash, master id, data fingerprint) can't be cleanly
    sourced, rather than guessing or defaulting it.
  - Every wiring site in the engine only ever WRITES a cache entry after a clean,
    COMPLETE, trades-free scalar-metrics result -- see each call site's own guard
    (return_trades/keep_trades True, or mc_sims>0, always skips the cache).

This module is intentionally stdlib-only (sqlite3, hashlib, json, os) -- no new
dependency, and safe to import from augur_mp_worker's separate OS-process workers
without pulling anything heavy in beyond what `augur_engine.paths` already needs.
"""
import hashlib
import json
import os
import sqlite3

from . import paths

_TABLE = "trial_cache"
# column -> DDL type, for the auto-migration idiom below (mirrors optimizer.py's
# csv_files PRAGMA table_info + ALTER TABLE ADD COLUMN pattern, ~L700-709).
_COLUMNS = {
    "key": "TEXT PRIMARY KEY",
    "value_json": "TEXT",
    "created": "TEXT",
    "strategy_file_sha": "TEXT",
    "master_id": "TEXT",
    "engine_epoch": "INTEGER",
}

# Best-effort IN-PROCESS counters (module globals). Precise cross-process accounting
# (what the runner/Builder chip needs) is PR2 -- this is just enough to unit-test the
# hit/miss bookkeeping now and give a same-process caller a cheap readout.
_STATS = {"hits": 0, "misses": 0}


def is_enabled() -> bool:
    """True iff env AUGUR_TRIAL_CACHE is truthy ("1"/"true"/"yes", case-insensitive).
    Re-read from the environment on EVERY call (never cached at import time) so a
    test's monkeypatch.setenv -- or the owner flipping it between runs -- takes
    effect immediately, and so a disabled-by-default process never has to be
    restarted to pick up the flag."""
    v = os.environ.get("AUGUR_TRIAL_CACHE", "")
    return str(v).strip().lower() in ("1", "true", "yes")


def _db_path() -> str:
    """AUGUR_TRIAL_CACHE_DB, re-read live (so a test's monkeypatch.setenv is honored
    even though augur_engine.paths already computed its own import-time default),
    else paths.TRIAL_CACHE_DB."""
    return os.environ.get("AUGUR_TRIAL_CACHE_DB") or paths.TRIAL_CACHE_DB


def _conn():
    """Short-lived connection to the sidecar trial_cache.db -- WAL mode + a short
    busy-timeout (INSERT OR REPLACE is idempotent, so this is safe against the
    stacked-runner double-execute hazard CLAUDE.md warns about: two writers racing
    the same key just both succeed, last one wins). Creates the table + index and
    runs the PRAGMA table_info + ALTER TABLE ADD COLUMN auto-migration idiom on
    every open (mirrors optimizer.py's csv_files migration, ~L700) -- cheap, and
    means a future column addition never needs a separate migration step."""
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
            key               TEXT PRIMARY KEY,
            value_json        TEXT,
            created           TEXT,
            strategy_file_sha TEXT,
            master_id         TEXT,
            engine_epoch      INTEGER
        )
    """)
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({_TABLE})").fetchall()]
        for c, ddl in _COLUMNS.items():
            if c in cols or "PRIMARY KEY" in ddl:   # PK can't be ADD COLUMN'd; CREATE
                continue                            # TABLE above already covers `key`.
            conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {c} {ddl}")
    except Exception:
        pass
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_sha_master "
                f"ON {_TABLE}(strategy_file_sha, master_id)")
    return conn


def canonical_params(params) -> str:
    """Sorted-key, fixed-precision, JSON-canonical string for a params dict (or any
    JSON-ish value) so equal params ALWAYS produce the same string regardless of
    key insertion order or a float's exact repr. None-safe -- None serializes to
    the JSON literal null, same as json.dumps(None)."""
    def _round(v):
        if isinstance(v, float):
            return round(v, 10)
        if isinstance(v, dict):
            return {k: _round(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [_round(x) for x in v]
        return v
    return json.dumps(_round(params), sort_keys=True, separators=(",", ":"), default=str)


def make_key(ctx: dict, params: dict, a=None, b=None) -> str:
    """sha1 over every field that can change a backtest's numbers, in a FIXED field
    order shared by every call path (grid worker / grid single-thread / auto /
    validate selection / default backtest) so equal inputs -> an equal key
    regardless of which path computed them. `ctx` is the per-job constant key
    material (see build_ctx); a missing ctx field is treated as None, same as an
    explicit None -- ctx itself may also be None/empty (treated as all-None).

    The field LIST is serialized via json.dumps (not a naive "|".join) before
    hashing -- some field values (master_id in particular, "instrument|timeframe|
    source" by its own spec'd definition) legitimately CONTAIN the separator
    character a naive join would use, which could otherwise let two logically
    different inputs collide onto the same hashed string. JSON's own array/string
    delimiting rules out that ambiguity.
    """
    ctx = ctx or {}
    fields = [
        ctx.get("strategy_file_sha"), ctx.get("engine_epoch"),
        canonical_params(params),
        ctx.get("ml_filter"), ctx.get("ml_threshold"),
        ctx.get("ml_min_history"), ctx.get("ml_refit_every"),
        canonical_params(ctx.get("sizing") or {}),
        ctx.get("master_id"), ctx.get("data_fingerprint"),
        a, b,
        ctx.get("date_from"), ctx.get("date_to"),
        ctx.get("cost_pts"), ctx.get("session"),
    ]
    blob = json.dumps(fields, separators=(",", ":"), default=str)
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()


def get(key):
    """SELECT value_json -> json.loads, or None on a miss OR ANY error (corrupt
    row, locked/missing DB file, missing table, bad JSON -- every failure mode is
    just a MISS; callers never need their own try/except around this)."""
    try:
        conn = _conn()
        try:
            row = conn.execute(
                f"SELECT value_json FROM {_TABLE} WHERE key=?", (key,)).fetchone()
        finally:
            conn.close()
        if not row or row[0] is None:
            return None
        return json.loads(row[0])
    except Exception:
        return None


def _json_default(o):
    """json.dumps `default` hook for put(): coerce a value json can't natively
    serialize into the SAME native value a fresh compute would hand back -- never a
    silent str() of it. numpy.float64 already subclasses float (json serializes it
    as a number without ever calling this), but numpy.int64/bool_ do NOT subclass
    int/bool, so json routes them here -> .item() returns the python scalar ->
    serialized as a number -> a cache HIT round-trips to the SAME python int/bool a
    cache MISS (fresh compute) compares against. numpy arrays -> .tolist(). Anything
    still unserializable RAISES, which propagates out of put() to the wiring site's
    try/except, which then just skips caching that one entry (fail-open to a
    recompute) -- so an exotic un-JSON-able metric is a MISS, never a wrong/typed-
    differently HIT. Duck-typed (getattr, not isinstance) so this module never has
    to import numpy/pandas -- it stays as light as the mp-worker needs."""
    item = getattr(o, "item", None)
    if callable(item):
        try:
            return o.item()          # numpy.int64 / bool_ / 0-d array scalar -> python scalar
        except Exception:
            pass
    tolist = getattr(o, "tolist", None)
    if callable(tolist):
        try:
            return o.tolist()        # numpy.ndarray -> list
        except Exception:
            pass
    raise TypeError(f"trial_cache: value not JSON-serializable: {type(o).__name__}")


def put(key, value: dict, *, strategy_file_sha, master_id, engine_epoch) -> None:
    """INSERT OR REPLACE the (already-computed, complete) scalar-metrics dict.
    Idempotent -- safe against two writers racing the same key (WAL + INSERT OR
    REPLACE, last commit wins, never an exception from the race itself).

    Callers must only call this with a JSON-serializable dict that was NOT computed
    with return_trades/keep_trades=True or mc_sims>0 -- this function does not
    itself enforce that (each wiring site guards it, since the guard needs
    context -- e.g. `keep_trades` -- this module doesn't have). May raise (a bad
    value_json serialization, a DB error) -- wrap the call at the wiring site if a
    write failure must never surface as a computation error (every current call
    site does)."""
    payload = json.dumps(value, default=_json_default)
    conn = _conn()
    try:
        conn.execute(
            f"INSERT OR REPLACE INTO {_TABLE} "
            f"(key, value_json, created, strategy_file_sha, master_id, engine_epoch) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (key, payload, "", strategy_file_sha, master_id, engine_epoch))
        conn.commit()
    finally:
        conn.close()


def record_hit():
    _STATS["hits"] += 1


def record_miss():
    _STATS["misses"] += 1


def get_stats():
    return dict(_STATS)


def reset_stats():
    _STATS["hits"] = 0
    _STATS["misses"] = 0


def job_reuse_summary() -> dict:
    """Snapshot _STATS as the per-JOB reuse summary (PR2, docs/INCREMENTAL_BACKTEST_
    REUSE.md #7.2 "per-job reuse logging"). A pure readout -- does NOT reset/mutate
    _STATS itself, so calling this twice in a row returns the same numbers; the
    runner (api/runner.py process_job) is what scopes these counts to a single job,
    by calling reset_stats() right before it dispatches to the engine and reading
    this right after. hits+misses==0 (cache off, or a job that never reached a
    cacheable eval path) reports pct_reused=0.0 rather than raising
    ZeroDivisionError -- consistent with this module's fail-toward-honest-zero
    stance rather than fail-toward-exception."""
    h = _STATS["hits"]
    m = _STATS["misses"]
    total = h + m
    return {"hits": h, "misses": m, "total": total,
            "pct_reused": round(100.0 * h / total, 1) if total else 0.0}


def build_ctx(mod, arrays, *, cost_pts=0.0, session=None, date_from=None, date_to=None,
              ml_filter=None, ml_threshold=None, ml_min_history=None, ml_refit_every=None,
              sizing=None, master=None):
    """Assemble the CONSTANT-per-job cache_ctx dict make_key() reads from -- called
    ONCE per job by the parent of each eval path (run_grid, run_auto,
    score_candidates_on_folds, run_backtest), never per-config. Returns None the
    instant a REQUIRED field can't be cleanly sourced; every wiring site's contract
    is "a None ctx means skip caching for this job," never "guess and maybe hit
    wrong" -- see this module's docstring.

    Required (any missing -> None overall):
      - strategy_file_sha: needs `mod.__file__` (a module loaded BY FILE PATH --
        not a hand-built module, e.g. a test's types.ModuleType() fake, which has
        no __file__ and correctly disables caching for that call).
      - master_id: needs `master` (a master-CSV row dict: instrument/timeframe/
        source) OR arrays["meta"] carrying the same (load_master_arrays sets
        meta=master, so this is the same row either way) -- with both an
        instrument and a timeframe present.
      - data_fingerprint: needs arrays["fingerprint"], only ever set by
        load_master_arrays -- a caller that supplied `arrays` directly (bypassing
        it, e.g. synthetic test arrays or a hand-rolled slice) correctly disables
        caching rather than guessing at what the data actually is.

    ml_filter/ml_threshold/ml_min_history/ml_refit_every/sizing/session/date_from/
    date_to/cost_pts are passed straight through (None where a call path has no
    such concept at all, e.g. run_grid never applies an ML gate) -- see make_key's
    docstring for why that's the correct, consistent choice.
    """
    path = getattr(mod, "__file__", None)
    if not path:
        return None
    try:
        from .strategies import strategy_file_sha as _sha_of
        sha = _sha_of(path)
    except Exception:
        return None
    if not sha:
        return None

    mrow = master if isinstance(master, dict) else None
    if mrow is None and isinstance(arrays, dict):
        m2 = arrays.get("meta")
        if isinstance(m2, dict):
            mrow = m2
    master_id = None
    if isinstance(mrow, dict):
        instrument = mrow.get("instrument")
        timeframe = mrow.get("timeframe")
        if instrument is not None and timeframe is not None:
            master_id = f"{instrument}|{timeframe}|{mrow.get('source')}"
    if not master_id:
        return None

    fp = arrays.get("fingerprint") if isinstance(arrays, dict) else None
    if not fp:
        return None

    # Deferred import: augur_engine/__init__.py imports .engine/.optimize/.auto
    # (which import THIS module) before ENGINE_CACHE_EPOCH is assigned at the
    # bottom of __init__.py, so a module-level `from . import ENGINE_CACHE_EPOCH`
    # here would raise ImportError on a fresh `import augur_engine` (a circular-
    # import hazard). Deferring it into this function body is safe: by the time
    # ANY caller actually INVOKES build_ctx (as opposed to merely importing this
    # module), augur_engine/__init__.py has always already finished executing --
    # Python fully initializes a parent package before any of its submodules'
    # functions can be called from outside code, even code that imports a
    # submodule path directly (import augur_engine.trial_cache still runs
    # augur_engine/__init__.py first).
    from . import ENGINE_CACHE_EPOCH

    return {
        "strategy_file_sha": sha, "engine_epoch": ENGINE_CACHE_EPOCH,
        "ml_filter": ml_filter, "ml_threshold": ml_threshold,
        "ml_min_history": ml_min_history, "ml_refit_every": ml_refit_every,
        "sizing": sizing, "master_id": master_id, "data_fingerprint": fp,
        "date_from": date_from, "date_to": date_to, "cost_pts": cost_pts,
        "session": session,
    }
