"""Tests for PR2 of "Incremental Backtest Reuse" (docs/INCREMENTAL_BACKTEST_REUSE.md #7.2):
per-JOB reuse accounting/logging on top of PR1's trial-level cache (tests/test_trial_cache.py).

Two things are under test:

  1. `trial_cache.job_reuse_summary()` — a pure readout of the module's in-process hit/miss
     counters, shaped for a job result/log line (hits/misses/total/pct_reused).
  2. `api.runner.process_job()`'s wiring around it: reset-right-before-dispatch / attach-
     right-after, gated entirely off when the cache is disabled (byte-identical to pre-PR2),
     and the HONESTY CAVEAT for a `grid` job that used `workers>1` — those configs run in
     separate OS processes (augur_mp_worker.eval_chunk), so the parent's in-process counters
     structurally cannot see them; a low/zero parent-side count must be LABELED as
     parent-process-only, never presented as if it were the complete picture.

`process_job` resolves data via `find_master(instrument, timeframe, session, source)` for
every real job type, which needs a real master CSV on disk — too heavy for a synthetic-data
unit test. Instead, each `process_job` test monkeypatches the specific `augur_engine`
function `process_job` calls (`ae.run_backtest` / `ae.run_grid` / `ae.run_auto` — `api.runner`
calls these as `ae.X(...)` attribute lookups, so patching `runner.ae.X` is exactly what a real
call sees) with a thin wrapper that forwards into the REAL engine function with synthetic
`arrays=` (mirroring test_trial_cache.py's `_syn_arrays`/`_write_strategy`), bypassing
`find_master` while still exercising the real trial-cache read-through and the real
record_hit/record_miss calls process_job's accounting reads.
"""
import numpy as np
import pytest

from augur_engine import trial_cache as TC
from augur_engine.engine import run_backtest as engine_run_backtest
from augur_engine.auto import run_auto as engine_run_auto
from augur_engine.optimize import run_grid as engine_run_grid
from api import runner


@pytest.fixture(autouse=True)
def _isolated_cache_db(tmp_path, monkeypatch):
    """Same isolation contract as test_trial_cache.py: every test gets its OWN fresh
    sqlite file and starts with the cache OFF, so nothing here ever touches the real
    repo's trial_cache.db and no test depends on another's leftover state."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE_DB", str(tmp_path / "trial_cache_test.db"))
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    TC.reset_stats()
    yield


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic strategy + arrays — identical shape to test_trial_cache.py's helpers,
# duplicated here (rather than imported) so this file stays independently readable
# and doesn't couple to another test module's internals.
# ─────────────────────────────────────────────────────────────────────────────

_STRATEGY_SRC = '''
STRATEGY_NAME = "SYN CACHE REUSE LOGGING TEST"
DEFAULT_PARAMS = {
    "knob": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
    "knob2": {"type": "int", "min": 1, "max": 5, "step": 1, "default": 3},
}
PARAM_GRID_PRESETS = {
    "Short test": {"knob": [1.0, 3.0], "knob2": [1, 2]},
}

def run_backtest(opens, highs, lows, closes, knob=5.0, knob2=3, return_trades=False, **kw):
    n = len(closes)
    if n == 0:
        return None
    marker = float(closes[0])
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


def _write_strategy(tmp_path, name="syn_reuse_log_strategy.py"):
    p = tmp_path / name
    p.write_text(_STRATEGY_SRC, encoding="utf-8")
    return str(p)


def _syn_arrays(n=400, instrument="SYNI", source="test"):
    close = 100.0 + np.arange(n, dtype=float)
    return {
        "open": close.copy(), "high": close + 1.0, "low": close - 1.0, "close": close.copy(),
        "volume": np.full(n, 1000.0), "day_id": (np.arange(n) // 20).astype("int64"),
        "index": None,
        "meta": {"name": "SYN_REUSE_LOG_MASTER", "instrument": instrument,
                 "timeframe": "5m", "source": source},
        "fingerprint": "reuselogfingerprint" + "0" * 20,
    }


# ─────────────────────────────────────────────────────────────────────────────
# job_reuse_summary() — pure math on top of _STATS
# ─────────────────────────────────────────────────────────────────────────────

def test_job_reuse_summary_zero_when_no_activity():
    TC.reset_stats()
    assert TC.job_reuse_summary() == {"hits": 0, "misses": 0, "total": 0, "pct_reused": 0.0}


def test_job_reuse_summary_computes_hits_misses_total_pct():
    TC.reset_stats()
    TC.record_hit(); TC.record_hit(); TC.record_hit()
    TC.record_miss()
    assert TC.job_reuse_summary() == {"hits": 3, "misses": 1, "total": 4, "pct_reused": 75.0}


def test_job_reuse_summary_rounds_to_one_decimal():
    TC.reset_stats()
    TC.record_hit(); TC.record_hit()
    TC.record_miss()
    s = TC.job_reuse_summary()
    assert s["total"] == 3
    assert s["pct_reused"] == round(200.0 / 3, 1)   # 66.7


def test_job_reuse_summary_all_misses_is_zero_pct_not_error():
    TC.reset_stats()
    TC.record_miss(); TC.record_miss()
    assert TC.job_reuse_summary()["pct_reused"] == 0.0


def test_job_reuse_summary_all_hits_is_100_pct():
    TC.reset_stats()
    TC.record_hit(); TC.record_hit()
    assert TC.job_reuse_summary()["pct_reused"] == 100.0


def test_job_reuse_summary_is_a_pure_readout_does_not_mutate_stats():
    TC.reset_stats()
    TC.record_hit()
    s1 = TC.job_reuse_summary()
    s2 = TC.job_reuse_summary()
    assert s1 == s2 == {"hits": 1, "misses": 0, "total": 1, "pct_reused": 100.0}
    assert TC.get_stats() == {"hits": 1, "misses": 0}   # unchanged by reading the summary


# ─────────────────────────────────────────────────────────────────────────────
# process_job wiring — cache ON, single-process job types (backtest / auto): the
# spec's "heaviest, most-rerun jobs" where the parent-process counters ARE accurate.
# ─────────────────────────────────────────────────────────────────────────────

def test_process_job_backtest_second_run_shows_full_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()

    def _fake_run_backtest(strategy, *, params=None, cost_pts=0.0, return_trades=False,
                           mc_sims=0, sizing=None, ml_filter=None, ml_threshold=0.5,
                           ml_min_history=30, **kw):
        return engine_run_backtest(strat_path, arrays=arrays, params=params or {},
                                   cost_pts=cost_pts, return_trades=return_trades,
                                   mc_sims=mc_sims, sizing=sizing, ml_filter=ml_filter,
                                   ml_threshold=ml_threshold, ml_min_history=ml_min_history)

    monkeypatch.setattr(runner.ae, "run_backtest", _fake_run_backtest)
    job = {"type": "backtest", "strategy": strat_path,
           "params": {"knob": 2.0, "knob2": 2}, "cost_pts": 0.0}

    patch1 = runner.process_job(job)
    assert patch1["status"] == "done"
    assert patch1["result"]["cache_reuse"] == {"hits": 0, "misses": 1, "total": 1, "pct_reused": 0.0}

    patch2 = runner.process_job(job)
    assert patch2["status"] == "done"
    assert patch2["result"]["cache_reuse"] == {"hits": 1, "misses": 0, "total": 1, "pct_reused": 100.0}


def test_process_job_backtest_logs_one_honest_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()

    def _fake_run_backtest(strategy, *, params=None, cost_pts=0.0, **kw):
        return engine_run_backtest(strat_path, arrays=arrays, params=params or {}, cost_pts=cost_pts)

    monkeypatch.setattr(runner.ae, "run_backtest", _fake_run_backtest)
    job = {"type": "backtest", "strategy": strat_path, "params": {"knob": 2.0, "knob2": 2}}

    runner.process_job(job)
    out1 = capsys.readouterr().out
    assert out1.count("-> cache:") == 1
    assert "reused 0/1 configs (0.0%)" in out1

    runner.process_job(job)
    out2 = capsys.readouterr().out
    assert out2.count("-> cache:") == 1
    assert "reused 1/1 configs (100.0%)" in out2


def test_process_job_auto_job_type_reuse_wiring(tmp_path, monkeypatch):
    """The heaviest job type (auto/walk-forward/validate all funnel through
    make_slice_evaluator, single-process) -- run twice, second run must show reuse."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()

    def _fake_run_auto(strategy, **kw):
        return engine_run_auto(strat_path, arrays=arrays, cost_pts=0.0, min_trades=1,
                               n_trials=10, top_n=5, method="single", oos=True, seed=42,
                               session="rth", date_from=None, date_to=None,
                               auto_expand=False, compute_surrogate=False, auto_steer=False)

    monkeypatch.setattr(runner.ae, "run_auto", _fake_run_auto)
    job = {"type": "auto", "strategy": strat_path}

    patch1 = runner.process_job(job)
    assert patch1["status"] == "done"
    cr1 = patch1["result"]["cache_reuse"]
    assert cr1["misses"] > 0 and cr1["hits"] == 0 and "note" not in cr1

    patch2 = runner.process_job(job)
    cr2 = patch2["result"]["cache_reuse"]
    assert cr2["hits"] > 0 and cr2["misses"] == 0
    assert cr2["total"] == cr1["total"]           # same job, same config set re-evaluated
    assert cr2["pct_reused"] == 100.0
    assert "note" not in cr2                       # single-process -> accurate, no caveat


# ─────────────────────────────────────────────────────────────────────────────
# Cache OFF — byte-identical to pre-PR2: no cache_reuse key, no log line.
# ─────────────────────────────────────────────────────────────────────────────

def test_process_job_no_cache_reuse_key_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)   # explicit OFF
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()

    def _fake_run_backtest(strategy, *, params=None, cost_pts=0.0, **kw):
        return engine_run_backtest(strat_path, arrays=arrays, params=params or {}, cost_pts=cost_pts)

    monkeypatch.setattr(runner.ae, "run_backtest", _fake_run_backtest)
    job = {"type": "backtest", "strategy": strat_path, "params": {"knob": 2.0, "knob2": 2}}

    patch = runner.process_job(job)
    assert patch["status"] == "done"
    assert "cache_reuse" not in patch["result"]
    # the underlying counters must also reflect "never consulted" -- the cache read-
    # through itself is gated off inside engine.run_backtest, not just the summary.
    assert TC.get_stats() == {"hits": 0, "misses": 0}


def test_process_job_no_log_noise_when_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()

    def _fake_run_backtest(strategy, *, params=None, cost_pts=0.0, **kw):
        return engine_run_backtest(strat_path, arrays=arrays, params=params or {}, cost_pts=cost_pts)

    monkeypatch.setattr(runner.ae, "run_backtest", _fake_run_backtest)
    job = {"type": "backtest", "strategy": strat_path, "params": {"knob": 2.0, "knob2": 2}}

    runner.process_job(job)
    out = capsys.readouterr().out
    assert "cache:" not in out


def test_process_job_error_path_has_no_cache_reuse_key(monkeypatch):
    """Fail-safe: an engine exception must return the normal error patch untouched --
    accounting/logging only ever runs on the success path (after `r` exists)."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")

    def _boom(strategy, **kw):
        raise ValueError("synthetic engine failure")

    monkeypatch.setattr(runner.ae, "run_backtest", _boom)
    job = {"type": "backtest", "strategy": "whatever.py", "params": {}}
    patch = runner.process_job(job)
    assert patch["status"] == "error"
    assert "result" not in patch


# ─────────────────────────────────────────────────────────────────────────────
# The honesty caveat — a `grid` job with workers>1 runs augur_mp_worker.eval_chunk
# in SEPARATE OS processes; their record_hit/record_miss calls land in THEIR OWN
# process-local _STATS, never this parent's. process_job must never present that
# parent-side undercount as a complete number -- it must attach a `note` (and say
# so in the log line) instead of silently printing e.g. "0/12 reused".
# ─────────────────────────────────────────────────────────────────────────────

def test_process_job_grid_parallel_workers_gets_honesty_note(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)

    def _fake_run_grid(strategy, *, workers=1, **kw):
        # Stands in for a REAL multi-process grid run: from the parent's point of
        # view, none of the pool workers' hits/misses are visible (they never were,
        # even before this PR -- PR1 wired eval_chunk's OWN per-process counters,
        # which this test doesn't touch), so 0/0 is the honest in-process reading
        # despite real backtests having run in the pool.
        return {"n_combos": 12, "n_valid": 10, "top": [], "best_params": {"knob": 1.0},
                "best": {"total_pnl": 1.0, "num_trades": 5, "win_rate": 60.0,
                         "profit_factor": 1.5, "max_drawdown": -1.0}, "bars": 400}

    monkeypatch.setattr(runner.ae, "run_grid", _fake_run_grid)
    job = {"type": "grid", "strategy": strat_path, "preset": "Short test", "workers": 4}

    patch = runner.process_job(job)
    assert patch["status"] == "done"
    cr = patch["result"]["cache_reuse"]
    assert cr["hits"] == 0 and cr["misses"] == 0 and cr["total"] == 0
    assert "note" in cr and "workers>1" in cr["note"]

    out = capsys.readouterr().out
    assert "-> cache:" in out
    assert "parent-process only" in out   # the log line itself carries the caveat too


def test_process_job_grid_single_worker_reports_accurate_counts_no_note(tmp_path, monkeypatch):
    """workers==1 (or absent) never spawns a pool -- the parent-process counters ARE
    the complete picture, so no honesty note should be attached."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()
    grid = {"knob": [1.0, 3.0]}

    def _fake_run_grid(strategy, *, workers=1, **kw):
        return engine_run_grid(strat_path, arrays=arrays, grid=grid, cost_pts=0.0,
                               min_trades=1, top_n=5, workers=1, session="rth")

    monkeypatch.setattr(runner.ae, "run_grid", _fake_run_grid)
    job = {"type": "grid", "strategy": strat_path, "workers": 1}

    patch = runner.process_job(job)
    cr = patch["result"]["cache_reuse"]
    assert cr == {"hits": 0, "misses": 2, "total": 2, "pct_reused": 0.0}
    assert "note" not in cr

    # rerun -> everything now cached, single-process counters stay trustworthy
    patch2 = runner.process_job(job)
    cr2 = patch2["result"]["cache_reuse"]
    assert cr2 == {"hits": 2, "misses": 0, "total": 2, "pct_reused": 100.0}
    assert "note" not in cr2


def test_process_job_grid_workers_missing_defaults_to_single_no_note(tmp_path, monkeypatch):
    """No 'workers' key at all in the job dict must behave like workers=1 (matches
    ae.run_grid's own default and process_job's int(job.get('workers', 1)) parse) --
    no honesty note."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()
    grid = {"knob": [1.0, 3.0]}

    def _fake_run_grid(strategy, *, workers=1, **kw):
        assert workers == 1   # process_job must have defaulted it, not passed None/garbage
        return engine_run_grid(strat_path, arrays=arrays, grid=grid, cost_pts=0.0,
                               min_trades=1, top_n=5, workers=1, session="rth")

    monkeypatch.setattr(runner.ae, "run_grid", _fake_run_grid)
    job = {"type": "grid", "strategy": strat_path}   # no "workers" key

    patch = runner.process_job(job)
    cr = patch["result"]["cache_reuse"]
    assert cr["total"] == 2
    assert "note" not in cr
