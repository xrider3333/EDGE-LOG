"""Correctness harness for the trial-level backtest result cache (PR1 of
"Incremental Backtest Reuse", docs/INCREMENTAL_BACKTEST_REUSE.md).

Every test here runs with AUGUR_TRIAL_CACHE_DB redirected to a per-test temp file
(the `_isolated_cache_db` autouse fixture below) so nothing ever touches the real
repo's trial_cache.db, and AUGUR_TRIAL_CACHE unset (cache OFF) unless a test
explicitly turns it on -- mirroring the feature's own "off by default" contract.

The single most important test in this file is the golden-equality pair near the
bottom: it proves the cache is a PURE speed optimization that never changes a
result, by running the same job three ways (cache off / cache on+empty DB / cache
on+populated DB) and asserting byte-identical champion output every time. If that
test is broken, the cache is unsafe to ship regardless of anything else here.
"""
import json
import os
import time
import types

import numpy as np
import pandas as pd
import pytest

from augur_engine import trial_cache as TC
from augur_engine.strategies import strategy_file_sha, load_strategy
from augur_engine.auto import run_auto, make_slice_evaluator
from augur_engine.optimize import run_grid
from augur_engine.engine import run_backtest
import augur_mp_worker as MPW


@pytest.fixture(autouse=True)
def _isolated_cache_db(tmp_path, monkeypatch):
    """Every test gets its OWN fresh sqlite file (tmp_path is function-scoped, so a
    new temp dir every test) and starts with the cache OFF -- a test that wants it
    on sets AUGUR_TRIAL_CACHE itself. This NEVER touches the real repo's
    trial_cache.db."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE_DB", str(tmp_path / "trial_cache_test.db"))
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    TC.reset_stats()
    yield


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic strategy + arrays shared by several tests below
# ─────────────────────────────────────────────────────────────────────────────

_STRATEGY_SRC = '''
STRATEGY_NAME = "SYN CACHE TEST"
DEFAULT_PARAMS = {
    "knob": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
    "knob2": {"type": "int", "min": 1, "max": 5, "step": 1, "default": 3},
}
PARAM_GRID_PRESETS = {
    "Short test": {"knob": [1.0, 3.0, 5.0, 7.0], "knob2": [1, 2, 3]},
}

def run_backtest(opens, highs, lows, closes, knob=5.0, knob2=3, return_trades=False, **kw):
    n = len(closes)
    if n == 0:
        return None
    marker = float(closes[0])   # ties the result to the SLICE, not just the params --
                                 # so a caching bug that ignored the (a, b) slice bounds
                                 # would be caught by the golden-equality tests below.
    per_trade = (knob * 10.0) - ((knob - 4.0) ** 2) * 3.0 + knob2 * 2.0 + marker * 0.01
    trades_n = 12
    wins = 7
    losses = trades_n - wins
    total = per_trade * trades_n
    out = {
        "total_pnl": float(total), "num_trades": trades_n,
        "win_rate": 100.0 * wins / trades_n, "profit_factor": 1.8,
        "max_drawdown": -abs(total) * 0.2 - 1.0, "avg_pnl": total / trades_n,
        "wins": wins, "losses": losses,
    }
    if return_trades:
        out["trades"] = [(i, i + 1, per_trade) for i in range(trades_n)]
    return out
'''


def _write_strategy(tmp_path, name="syn_cache_strategy.py"):
    """A REAL .py file on disk (not a types.ModuleType() fake) -- load_strategy
    gives it a real __file__, which strategy_file_sha/build_ctx need to consider a
    job cacheable at all. Returns the absolute path string."""
    p = tmp_path / name
    p.write_text(_STRATEGY_SRC, encoding="utf-8")
    return str(p)


def _syn_arrays(n=400, instrument="SYNI", source="test"):
    close = 100.0 + np.arange(n, dtype=float)
    return {
        "open": close.copy(), "high": close + 1.0, "low": close - 1.0, "close": close.copy(),
        "volume": np.full(n, 1000.0), "day_id": (np.arange(n) // 20).astype("int64"),
        "index": None,
        "meta": {"name": "SYN_CACHE_MASTER", "instrument": instrument,
                 "timeframe": "5m", "source": source},
        "fingerprint": "fixedfingerprint" + "0" * 24,
    }


# ─────────────────────────────────────────────────────────────────────────────
# canonical_params
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_params_sorts_keys_and_ignores_dict_order():
    a = TC.canonical_params({"b": 1, "a": 2})
    b = TC.canonical_params({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_canonical_params_rounds_floats_to_10_decimals():
    a = TC.canonical_params({"x": 1.0 / 3})
    b = TC.canonical_params({"x": round(1.0 / 3, 10)})
    assert a == b


def test_canonical_params_none_safe():
    assert TC.canonical_params(None) == "null"


def test_canonical_params_distinguishes_real_differences():
    assert TC.canonical_params({"a": 1}) != TC.canonical_params({"a": 2})
    assert TC.canonical_params({"a": 1}) != TC.canonical_params({"a": 1, "b": 1})


# ─────────────────────────────────────────────────────────────────────────────
# is_enabled — env parsing, re-read live every call
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("val,expected", [
    ("1", True), ("true", True), ("True", True), ("YES", True), ("yes", True),
    ("0", False), ("false", False), ("no", False), ("", False), ("random", False),
])
def test_is_enabled_parses_truthy_values(monkeypatch, val, expected):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", val)
    assert TC.is_enabled() is expected


def test_is_enabled_defaults_false_when_unset(monkeypatch):
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    assert TC.is_enabled() is False


def test_is_enabled_flips_immediately_mid_process(monkeypatch):
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    assert TC.is_enabled() is False
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    assert TC.is_enabled() is True   # no restart / no import-time caching needed


# ─────────────────────────────────────────────────────────────────────────────
# get / put roundtrip
# ─────────────────────────────────────────────────────────────────────────────

def test_put_then_get_roundtrips_exactly():
    key = "k1"
    value = {"total_pnl": 123.456, "num_trades": 7, "win_rate": 57.14,
             "profit_factor": 1.85, "max_drawdown": -45.0, "wins": 4, "losses": 3}
    TC.put(key, value, strategy_file_sha="sha1", master_id="ES|5m|tv", engine_epoch=1)
    assert TC.get(key) == value


def test_get_miss_returns_none():
    assert TC.get("this-key-was-never-written") is None


def test_get_returns_none_on_a_corrupt_db_file(tmp_path, monkeypatch):
    bad = tmp_path / "not_a_real_sqlite_file.db"
    bad.write_text("this is not a sqlite database", encoding="utf-8")
    monkeypatch.setenv("AUGUR_TRIAL_CACHE_DB", str(bad))
    assert TC.get("anything") is None   # fail-open: never raises


def test_put_handles_inf_profit_factor_roundtrip():
    key = "k-inf"
    value = {"total_pnl": 1.0, "profit_factor": float("inf")}
    TC.put(key, value, strategy_file_sha="s", master_id="m", engine_epoch=1)
    got = TC.get(key)
    assert got["profit_factor"] == float("inf")


def test_put_is_insert_or_replace_idempotent():
    key = "k2"
    TC.put(key, {"total_pnl": 1.0}, strategy_file_sha="s", master_id="m", engine_epoch=1)
    TC.put(key, {"total_pnl": 2.0}, strategy_file_sha="s", master_id="m", engine_epoch=1)
    assert TC.get(key) == {"total_pnl": 2.0}


# ─────────────────────────────────────────────────────────────────────────────
# strategy_file_sha
# ─────────────────────────────────────────────────────────────────────────────

def test_strategy_file_sha_is_stable_for_unchanged_content(tmp_path):
    p = tmp_path / "s.py"
    p.write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    assert strategy_file_sha(str(p)) == strategy_file_sha(str(p))


def test_strategy_file_sha_changes_when_content_changes(tmp_path):
    p = tmp_path / "s.py"
    p.write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    a = strategy_file_sha(str(p))
    time.sleep(0.05)   # force a distinct mtime so the (path, mtime) memoization re-hashes
    p.write_text("STRATEGY_NAME='y'\n", encoding="utf-8")
    b = strategy_file_sha(str(p))
    assert a != b


def test_strategy_file_sha_raises_on_missing_file(tmp_path):
    with pytest.raises(OSError):
        strategy_file_sha(str(tmp_path / "does_not_exist.py"))


# ─────────────────────────────────────────────────────────────────────────────
# build_ctx — fail-open contract: None the instant a required field is missing
# ─────────────────────────────────────────────────────────────────────────────

def test_build_ctx_none_when_module_has_no_file():
    fake_mod = types.ModuleType("fake_no_file")   # no __file__ at all -- e.g. a
                                                    # hand-built test double
    arrays = _syn_arrays()
    assert TC.build_ctx(fake_mod, arrays, master=arrays["meta"]) is None


def test_build_ctx_none_when_master_id_unavailable(tmp_path):
    mod = load_strategy(_write_strategy(tmp_path))
    arrays = _syn_arrays()
    arrays["meta"] = {"name": "no instrument/timeframe here"}
    assert TC.build_ctx(mod, arrays, master=None) is None


def test_build_ctx_none_when_fingerprint_unavailable(tmp_path):
    mod = load_strategy(_write_strategy(tmp_path))
    arrays = _syn_arrays()
    del arrays["fingerprint"]
    assert TC.build_ctx(mod, arrays, master=arrays["meta"]) is None


def test_build_ctx_returns_full_dict_when_everything_available(tmp_path):
    strat_path = _write_strategy(tmp_path)
    mod = load_strategy(strat_path)
    arrays = _syn_arrays()
    ctx = TC.build_ctx(mod, arrays, cost_pts=0.5, session="rth",
                       date_from="2026-01-01", date_to="2026-01-31",
                       master=arrays["meta"])
    assert ctx is not None
    assert ctx["strategy_file_sha"] == strategy_file_sha(strat_path)
    assert ctx["engine_epoch"] == 1
    assert ctx["master_id"] == "SYNI|5m|test"
    assert ctx["data_fingerprint"] == arrays["fingerprint"]
    assert ctx["cost_pts"] == 0.5
    assert ctx["session"] == "rth"
    assert ctx["date_from"] == "2026-01-01" and ctx["date_to"] == "2026-01-31"


def test_build_ctx_falls_back_to_arrays_meta_when_master_arg_is_none(tmp_path):
    """arrays=... called directly (bypassing master=...) still works as long as
    arrays["meta"] itself carries instrument/timeframe/source -- exactly what
    load_master_arrays sets meta to."""
    mod = load_strategy(_write_strategy(tmp_path))
    arrays = _syn_arrays()
    ctx = TC.build_ctx(mod, arrays, master=None)
    assert ctx is not None
    assert ctx["master_id"] == "SYNI|5m|test"


# ─────────────────────────────────────────────────────────────────────────────
# make_key — invalidation: flipping ANY key field must change the key
# ─────────────────────────────────────────────────────────────────────────────

def _base_ctx():
    return {
        "strategy_file_sha": "sha-AAA", "engine_epoch": 1,
        "ml_filter": None, "ml_threshold": 0.5,
        "ml_min_history": 30, "ml_refit_every": 25,
        "sizing": None, "master_id": "ES|5m|tv", "data_fingerprint": "fp-AAA",
        "date_from": "2026-01-01", "date_to": "2026-06-01",
        "cost_pts": 0.283, "session": "rth",
    }


def test_make_key_changes_when_any_ctx_field_flips():
    base_ctx = _base_ctx()
    base_params = {"knob": 1.0}
    base_key = TC.make_key(base_ctx, base_params, a=10, b=20)

    variants = {
        "strategy_file_sha": "sha-BBB",
        "engine_epoch": 2,
        "ml_filter": "logistic",
        "ml_threshold": 0.6,
        "ml_min_history": 50,
        "ml_refit_every": 10,
        "master_id": "NQ|5m|tv",
        "data_fingerprint": "fp-BBB",
        "date_from": "2026-02-01",
        "date_to": "2026-07-01",
        "cost_pts": 0.5,
        "session": "eth",
    }
    for field, new_value in variants.items():
        ctx2 = dict(base_ctx)
        ctx2[field] = new_value
        key2 = TC.make_key(ctx2, base_params, a=10, b=20)
        assert key2 != base_key, f"flipping ctx field {field!r} did not change the key"


def test_make_key_changes_when_sizing_flips():
    base_ctx = _base_ctx()
    base_key = TC.make_key(base_ctx, {"knob": 1.0}, a=10, b=20)
    ctx2 = dict(base_ctx)
    ctx2["sizing"] = {"risk_parity": True}
    assert TC.make_key(ctx2, {"knob": 1.0}, a=10, b=20) != base_key


def test_make_key_changes_when_a_param_value_flips():
    base_ctx = _base_ctx()
    k1 = TC.make_key(base_ctx, {"knob": 1.0}, a=10, b=20)
    k2 = TC.make_key(base_ctx, {"knob": 2.0}, a=10, b=20)
    assert k1 != k2


def test_make_key_changes_when_a_or_b_flips():
    base_ctx = _base_ctx()
    base_params = {"knob": 1.0}
    base_key = TC.make_key(base_ctx, base_params, a=10, b=20)
    assert TC.make_key(base_ctx, base_params, a=11, b=20) != base_key
    assert TC.make_key(base_ctx, base_params, a=10, b=21) != base_key


def test_make_key_stable_for_identical_inputs_regardless_of_dict_order():
    ctx1 = _base_ctx()
    ctx2 = {k: ctx1[k] for k in reversed(list(ctx1.keys()))}   # same content, built in reverse
    assert TC.make_key(ctx1, {"a": 1, "b": 2}, 0, 10) == TC.make_key(ctx2, {"b": 2, "a": 1}, 0, 10)


def test_make_key_missing_ctx_fields_treated_as_none():
    assert TC.make_key({}, {"knob": 1.0}, 0, 10) == TC.make_key(None, {"knob": 1.0}, 0, 10)


# ─────────────────────────────────────────────────────────────────────────────
# mc_sims / return_trades / keep_trades bypass -- never cache those
# ─────────────────────────────────────────────────────────────────────────────

def test_run_backtest_never_caches_when_return_trades_true(tmp_path, monkeypatch):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)
    r = run_backtest(strat_path, arrays=_syn_arrays(), params={"knob": 2.0, "knob2": 2},
                     return_trades=True)
    assert r is not None and "trades" in r
    stats = TC.get_stats()
    assert stats == {"hits": 0, "misses": 0}   # the cache was never even consulted


def test_run_backtest_never_caches_when_mc_sims_positive(tmp_path, monkeypatch):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)
    r = run_backtest(strat_path, arrays=_syn_arrays(), params={"knob": 2.0, "knob2": 2},
                     mc_sims=5)
    assert r is not None
    assert TC.get_stats() == {"hits": 0, "misses": 0}


def test_make_slice_evaluator_never_caches_when_keep_trades_true(tmp_path, monkeypatch):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    mod = load_strategy(_write_strategy(tmp_path))
    arrays = _syn_arrays()
    ctx = TC.build_ctx(mod, arrays, cost_pts=0.0, master=arrays["meta"])
    assert ctx is not None
    ev = make_slice_evaluator(mod, arrays, cost_pts=0.0, cache_ctx=ctx)
    m = ev(0, 100, {"knob": 3.0, "knob2": 2}, keep_trades=True)
    assert m is not None and "trades" in m
    assert TC.get_stats() == {"hits": 0, "misses": 0}
    # the key that WOULD have been used had keep_trades been False -- assert
    # nothing was ever written under it either
    would_be_key = TC.make_key(ctx, {"knob": 3.0, "knob2": 2}, 0, 100)
    assert TC.get(would_be_key) is None


# ─────────────────────────────────────────────────────────────────────────────
# Concurrency -- two connections writing the same key must not corrupt/raise
# ─────────────────────────────────────────────────────────────────────────────

def test_two_connections_can_both_write_the_same_key():
    c1 = TC._conn()
    c2 = TC._conn()
    key = "concurrent-key"
    try:
        c1.execute(
            "INSERT OR REPLACE INTO trial_cache "
            "(key, value_json, created, strategy_file_sha, master_id, engine_epoch) "
            "VALUES (?,?,?,?,?,?)",
            (key, json.dumps({"total_pnl": 1.0}), "", "sha-a", "m-a", 1))
        c1.commit()
        c2.execute(
            "INSERT OR REPLACE INTO trial_cache "
            "(key, value_json, created, strategy_file_sha, master_id, engine_epoch) "
            "VALUES (?,?,?,?,?,?)",
            (key, json.dumps({"total_pnl": 2.0}), "", "sha-b", "m-b", 1))
        c2.commit()
    finally:
        c1.close()
        c2.close()
    assert TC.get(key) == {"total_pnl": 2.0}   # last commit wins; neither raised


def test_conn_auto_migration_adds_missing_columns(monkeypatch, tmp_path):
    """Simulates an OLDER trial_cache.db missing a newer column -- the PRAGMA
    table_info + ALTER TABLE ADD COLUMN idiom must backfill it without raising."""
    import sqlite3
    db = tmp_path / "old_schema.db"
    monkeypatch.setenv("AUGUR_TRIAL_CACHE_DB", str(db))
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE trial_cache (key TEXT PRIMARY KEY, value_json TEXT)")
    raw.commit()
    raw.close()

    TC.put("k", {"total_pnl": 1.0}, strategy_file_sha="s", master_id="m", engine_epoch=7)
    assert TC.get("k") == {"total_pnl": 1.0}

    conn = TC._conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trial_cache)").fetchall()}
    conn.close()
    assert {"key", "value_json", "created", "strategy_file_sha",
            "master_id", "engine_epoch"} <= cols


# ─────────────────────────────────────────────────────────────────────────────
# The hard constraint: cache OFF touches NOTHING on disk
# ─────────────────────────────────────────────────────────────────────────────

def test_disabled_cache_never_creates_the_db_file(tmp_path):
    db_path = os.environ["AUGUR_TRIAL_CACHE_DB"]   # set by the autouse fixture
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()
    run_backtest(strat_path, arrays=arrays, params={"knob": 2.0, "knob2": 2})
    run_grid(strat_path, arrays=arrays, grid={"knob": [1.0, 2.0]}, workers=1)
    run_auto(strat_path, arrays=arrays, n_trials=3, min_trades=1, oos=False,
             method="single", seed=42)
    assert not os.path.exists(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# GOLDEN EQUALITY — the cache must NEVER change a result. This is the test that
# gates the whole feature: if it fails, do not ship.
# ─────────────────────────────────────────────────────────────────────────────

def test_golden_equality_run_auto_three_ways(tmp_path, monkeypatch):
    strat_path = _write_strategy(tmp_path)

    def _run():
        return run_auto(strat_path, arrays=_syn_arrays(), cost_pts=0.0, min_trades=1,
                        n_trials=15, top_n=5, method="single", oos=True, seed=42,
                        session="rth", date_from=None, date_to=None,
                        auto_expand=False, compute_surrogate=False, auto_steer=False)

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    r0 = _run()

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    r1 = _run()                                    # empty DB -> real work, populates
    stats1 = TC.get_stats()
    assert stats1["misses"] > 0

    TC.reset_stats()
    r2 = _run()                                    # DB now populated -> reused
    stats2 = TC.get_stats()
    assert stats2["hits"] > 0
    assert stats2["misses"] == 0                    # R1 already populated every key R2 touches

    for a, b, label in ((r0, r1, "off vs on-empty"), (r1, r2, "on-empty vs on-populated")):
        assert a["best_params"] == b["best_params"], label
        for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown"):
            assert a["best"][k] == b["best"][k], f"{label}: {k}"
        assert a["top"] == b["top"], label


def test_golden_equality_run_grid_three_ways(tmp_path, monkeypatch):
    strat_path = _write_strategy(tmp_path)
    grid = {"knob": [1.0, 3.0, 5.0, 7.0], "knob2": [1, 2, 3]}
    n_combos = len(grid["knob"]) * len(grid["knob2"])

    def _run():
        return run_grid(strat_path, arrays=_syn_arrays(), grid=grid, cost_pts=0.0,
                        min_trades=1, top_n=10, workers=1, session="rth")

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    r0 = _run()

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    r1 = _run()
    stats1 = TC.get_stats()
    assert stats1 == {"hits": 0, "misses": n_combos}   # every combo is distinct -> all misses

    TC.reset_stats()
    r2 = _run()
    stats2 = TC.get_stats()
    assert stats2 == {"hits": n_combos, "misses": 0}   # every combo now cached -> all hits

    for a, b, label in ((r0, r1, "off vs on-empty"), (r1, r2, "on-empty vs on-populated")):
        assert a["best_params"] == b["best_params"], label
        for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown"):
            assert a["best"][k] == b["best"][k], f"{label}: {k}"
        assert a["top"] == b["top"], label


def test_golden_equality_run_backtest_three_ways(tmp_path, monkeypatch):
    """The plain default-backtest path (engine.run_backtest, no ML/sizing/MC/
    return_trades) — the lower-volume path the spec allows skipping if it can't be
    cleanly wired, but it could be here."""
    strat_path = _write_strategy(tmp_path)
    params = {"knob": 4.0, "knob2": 2}

    def _run():
        return run_backtest(strat_path, arrays=_syn_arrays(), params=params, cost_pts=0.1)

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    r0 = _run()

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    r1 = _run()
    assert TC.get_stats()["misses"] == 1

    TC.reset_stats()
    r2 = _run()
    assert TC.get_stats() == {"hits": 1, "misses": 0}

    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown",
              "avg_pnl", "wins", "losses"):
        assert r0[k] == r1[k] == r2[k], k


# ─────────────────────────────────────────────────────────────────────────────
# Gate-1 + Gate-2 hardening (added on supervisor review): a strategy that returns
# NUMPY-typed metrics (the case the old put()'s json.dumps(default=str) would have
# silently stringified into a wrong hit), and a REAL plugin (ORB_1_0) through the
# cache -- so golden-equality is proven beyond the synthetic test double.
# ─────────────────────────────────────────────────────────────────────────────

_NUMPY_METRICS_STRATEGY_SRC = '''
import numpy as np
STRATEGY_NAME = "SYN NUMPY METRICS"
DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0}}
PARAM_GRID_PRESETS = {"Short test": {"knob": [1.0, 3.0, 5.0]}}

def run_backtest(opens, highs, lows, closes, knob=5.0, return_trades=False, **kw):
    n = len(closes)
    if n == 0:
        return None
    marker = float(closes[0])
    per = (knob * 10.0) - ((knob - 4.0) ** 2) * 3.0 + marker * 0.01
    trades_n = np.int64(12)          # numpy int -- json.dumps(default=str) would make this "12"
    wins = np.int64(7)
    total = np.float64(per) * trades_n
    out = {
        "total_pnl": np.float64(total), "num_trades": trades_n,
        "win_rate": np.float64(100.0 * 7 / 12), "profit_factor": np.float64(1.8),
        "max_drawdown": np.float64(-abs(total) * 0.2 - 1.0), "avg_pnl": np.float64(total / 12),
        "wins": wins, "losses": np.int64(5),
    }
    if return_trades:
        out["trades"] = [(i, i + 1, float(per)) for i in range(int(trades_n))]
    return out
'''


def _real_arrays(n_days=10, per_day=78, instrument="ES", source="test"):
    """Seeded random-walk (mirrors test_strategy_contract.py's _make_arrays) but WITH
    a master identity (instrument/timeframe/source) + a fingerprint, so build_ctx
    treats it as cacheable -- for driving a REAL plugin through the cache."""
    rng = np.random.default_rng(7)
    n = n_days * per_day
    close = 15000 + rng.normal(0, 1, n).cumsum()
    high = close + np.abs(rng.normal(0, 2, n))
    low = close - np.abs(rng.normal(0, 2, n))
    openp = close + rng.normal(0, 1, n)
    vol = np.abs(rng.normal(1000, 200, n))
    day_id = np.repeat(np.arange(n_days), per_day).astype("int64")
    idx = pd.date_range("2026-03-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    return {"open": openp, "high": high, "low": low, "close": close, "volume": vol,
            "day_id": day_id, "index": idx,
            "meta": {"name": "SYN_REAL", "instrument": instrument, "timeframe": "5m",
                     "source": source},
            "fingerprint": "realfp" + "0" * 34}


def test_golden_equality_numpy_typed_metrics_run_grid(tmp_path, monkeypatch):
    """GATE-1 PROOF: a strategy returning NUMPY-typed metrics (np.int64/np.float64) --
    the exact case the OLD put()'s json.dumps(default=str) would have STRINGIFIED
    (a cached hit would come back "12", != a fresh compute's 12). Golden-equality
    must hold across off/on-empty/on-populated, AND a hit must round-trip to NATIVE
    python numbers. This test FAILS on the pre-hardening put() and passes after it."""
    p = tmp_path / "syn_numpy.py"
    p.write_text(_NUMPY_METRICS_STRATEGY_SRC, encoding="utf-8")
    strat_path = str(p)
    grid = {"knob": [1.0, 3.0, 5.0]}

    def _run():
        return run_grid(strat_path, arrays=_syn_arrays(), grid=grid, cost_pts=0.0,
                        min_trades=1, top_n=5, workers=1, session="rth")

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    r0 = _run()
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    r1 = _run()
    assert TC.get_stats() == {"hits": 0, "misses": 3}
    TC.reset_stats()
    r2 = _run()
    assert TC.get_stats() == {"hits": 3, "misses": 0}

    for a, b, label in ((r0, r1, "off vs on-empty"), (r1, r2, "on-empty vs on-populated")):
        assert a["best_params"] == b["best_params"], label
        for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown"):
            assert a["best"][k] == b["best"][k], f"{label}: {k}"
    # The fix itself: a HIT round-trips to a native python int, never the "12" string
    # json.dumps(default=str) would have produced.
    hit_nt = r2["best"]["num_trades"]
    assert isinstance(hit_nt, int) and not isinstance(hit_nt, bool)
    assert hit_nt == 12


def test_golden_equality_real_strategy_run_backtest(tmp_path, monkeypatch):
    """GATE-2: a REAL plugin (ORB_1_0, ~10 trades on this synthetic walk) through the
    engine.run_backtest cache path three ways -- proving the cache round-trips a real
    strategy's actual return shape identically, not only the synthetic test double."""
    from augur_engine.strategies import strategy_params
    arrays = _real_arrays()
    mod = load_strategy("ORB_1_0.py")
    params = {k: v.get("default") for k, v in strategy_params(mod).items()
              if isinstance(v, dict) and "default" in v}

    def _run():
        return run_backtest("ORB_1_0.py", arrays=arrays, params=params,
                            cost_pts=0.0, session="rth")

    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    r0 = _run()
    assert r0 is not None and r0["num_trades"] > 0

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    r1 = _run()
    assert TC.get_stats()["misses"] == 1
    TC.reset_stats()
    r2 = _run()
    assert TC.get_stats() == {"hits": 1, "misses": 0}

    for k in ("total_pnl", "num_trades", "win_rate", "profit_factor",
              "max_drawdown", "avg_pnl", "wins", "losses"):
        assert r0[k] == r1[k] == r2[k], k


# ─────────────────────────────────────────────────────────────────────────────
# Grid MULTIPROCESS-worker wiring — direct in-process calls to init_worker/
# eval_chunk (the exact functions a spawned OS process runs), proving the cache
# read-through inside eval_chunk is correct without the slowness/flakiness of a
# real ProcessPoolExecutor spawn inside a test suite. The concurrency test above
# separately proves the underlying SQLite store is safe across genuinely separate
# connections/processes -- eval_chunk's own read-through logic is identical either
# way, so testing it in-process is a faithful, deterministic proxy.
# ─────────────────────────────────────────────────────────────────────────────

def test_mp_worker_eval_chunk_cache_read_through(tmp_path, monkeypatch):
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays(n=200)
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V, did = arrays["volume"], arrays["day_id"]

    mod = load_strategy(strat_path)
    cache_ctx = TC.build_ctx(mod, arrays, cost_pts=0.0, session="rth", master=arrays["meta"])
    assert cache_ctx is not None

    combos = [{"knob": 1.0, "knob2": 1}, {"knob": 3.0, "knob2": 2}, {"knob": 5.0, "knob2": 3}]
    chunk = list(enumerate(combos))

    # cache OFF -- eval_chunk must behave exactly as it did before this feature
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    MPW.init_worker(strat_path, O, H, L, C, V, did, 0.0, cache_ctx)
    out_off = MPW.eval_chunk(chunk)
    assert all(err is None for _, _, err in out_off)
    assert TC.get_stats() == {"hits": 0, "misses": 0}   # is_enabled() gated it out entirely

    # cache ON, empty DB -> all misses, populates
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    MPW.init_worker(strat_path, O, H, L, C, V, did, 0.0, cache_ctx)
    out_on1 = MPW.eval_chunk(chunk)
    assert TC.get_stats() == {"hits": 0, "misses": 3}

    # cache ON again -> all hits, byte-identical metrics
    TC.reset_stats()
    MPW.init_worker(strat_path, O, H, L, C, V, did, 0.0, cache_ctx)
    out_on2 = MPW.eval_chunk(chunk)
    assert TC.get_stats() == {"hits": 3, "misses": 0}

    for (idx0, m0, e0), (idx1, m1, e1), (idx2, m2, e2) in zip(out_off, out_on1, out_on2):
        assert idx0 == idx1 == idx2
        assert e0 is None and e1 is None and e2 is None
        for k in ("total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown"):
            assert m0[k] == m1[k] == m2[k]


def test_mp_worker_init_worker_backward_compatible_without_cache_ctx(tmp_path):
    """The existing 8-positional-arg call (optimizer.py's Streamlit app,
    tools/test_mp_worker.py) must keep working -- no cache_ctx arg at all."""
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays(n=50)
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V, did = arrays["volume"], arrays["day_id"]
    MPW.init_worker(strat_path, O, H, L, C, V, did, 0.0)   # no cache_ctx
    out = MPW.eval_chunk([(0, {"knob": 2.0, "knob2": 1})])
    assert out[0][2] is None
    assert out[0][1] is not None


def test_mp_worker_eval_chunk_error_handling_unchanged(tmp_path):
    """A genuinely failing config must still come back as (idx, None, err_str) --
    the cache wiring must not swallow or reshape a real backtest error."""
    src = '''
STRATEGY_NAME = "ALWAYS FAILS"
DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 1.0, "default": 0.5}}
def run_backtest(o, h, l, c, knob=0.5, return_trades=False, **kw):
    raise ValueError("synthetic failure")
'''
    p = tmp_path / "always_fails.py"
    p.write_text(src, encoding="utf-8")
    arrays = _syn_arrays(n=20)
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    MPW.init_worker(str(p), O, H, L, C, arrays["volume"], arrays["day_id"], 0.0)
    out = MPW.eval_chunk([(0, {"knob": 0.5})])
    idx, m, err = out[0]
    assert idx == 0 and m is None
    assert err is not None and "synthetic failure" in err


# ─────────────────────────────────────────────────────────────────────────────
# record_hit / record_miss / get_stats / reset_stats
# ─────────────────────────────────────────────────────────────────────────────

def test_stats_counters_basic():
    TC.reset_stats()
    assert TC.get_stats() == {"hits": 0, "misses": 0}
    TC.record_hit()
    TC.record_hit()
    TC.record_miss()
    assert TC.get_stats() == {"hits": 2, "misses": 1}
    TC.reset_stats()
    assert TC.get_stats() == {"hits": 0, "misses": 0}
