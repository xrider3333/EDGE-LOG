"""W46 (owner 2026-10-18, "why is it taking 11 hours"): Auto-Validate Stage A's TAIL -
the warmed out-of-sample re-test of every searched config, the up-to-400 full-window
equity-top backtests + the DSR loop, the neighbourhood runs and the surrogate picks'
in-sample curves - never reached the trial cache, so every restart of a long validate
re-paid it. These tests pin the S1 fix:

  A. trial_cache.make_key(..., tag=None): every pre-existing key is byte-identical
     (golden digests computed BEFORE the change), and a tag yields a different key.
  B/C/D. run_auto's full result is deep-equal with the cache OFF, cold (fresh DB) and
     replayed, the replay is all hits, the warm / etop / full / iscurve keys never collide
     with the plain (untagged) keys, and a backtest that CRASHED is never cached.
  E. a memory failure in a backtest (MemoryError, or an OSError whose code says out of
     memory) is retried after waiting - always at least one backoff step - then RAISED,
     never a silent None; no older broad handler can swallow that raise (run_auto and
     run_validate re-raise it: lockbox, selection, surrogate). Any other exception, a
     missing or locked file included, still returns None but is counted by class.
  F. failed cache writes are counted (evaluator, run_backtest, run_grid), walk-forward
     worker processes hand their counts back, and the runner's line reports them - on a
     failed job too.
  G. run_validate saves `timings` and `code_stamps` (the commit the code was LOADED from,
     plus the checkout's HEAD at each stage) and prints stage markers.
  Pool. A failed walk-forward fold stops the workers still running; a worker that ran
     out of memory is answered with an identical in-line re-run.

Everything is synthetic (a strategy file written to tmp_path, arrays built here); the
cache DB is redirected to tmp_path for every test, so nothing touches the real one, and the
trade-context block reads fixed external series instead of Yahoo.
"""
import errno
import json
import os
import re
import subprocess
import time
import types

import numpy as np
import pandas as pd
import pytest

import augur_engine.auto as AUTO
from augur_engine import trial_cache as TC
from augur_engine.auto import run_auto, make_slice_evaluator
from augur_engine.strategies import load_strategy


@pytest.fixture(autouse=True)
def _isolated_cache_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE_DB", str(tmp_path / "trial_cache_tail.db"))
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    monkeypatch.delenv("EDGELOG_VALIDATE_WORKERS", raising=False)
    TC.reset_stats()
    TC.reset_health()
    yield
    TC.reset_stats()
    TC.reset_health()


def _fake_external_series():
    """Fixed daily closes for the four context tickers over 2018-2025: the trade-context
    block's external join runs for real and identically on every call, with no network."""
    days = pd.date_range("2018-01-01", "2025-12-31", freq="B")
    i = np.arange(len(days), dtype=float)
    vix = 16.0 + 5.0 * np.sin(i / 17.0)
    cols = {"^VIX": vix, "^VIX3M": vix + 1.0 + 0.5 * np.cos(i / 29.0),
            "^TNX": 2.0 + 0.01 * (i % 97), "^IRX": 1.0 + 0.005 * (i % 53)}
    return {t: pd.Series(v, index=days.date) for t, v in cols.items()}


_FAKE_EXT = _fake_external_series()


@pytest.fixture(autouse=True)
def _offline_context(tmp_path, monkeypatch):
    """run_validate always builds the TRADE CONTEXT block, whose external features come
    from Yahoo (context._fetch_one -> yfinance) and are cached under <tree>/augur_uploads.
    A rate-limited ticker on one of the off / cold / replay calls changed that call's
    context and failed the equality for a reason that has nothing to do with the trial
    cache - so every test here reads fixed series instead, and writes nothing to the tree."""
    import augur_engine.context as CTX
    monkeypatch.setattr(CTX, "CACHE_DIR", str(tmp_path / "_context"))
    monkeypatch.setattr(CTX, "_fetch_one", lambda ticker: _FAKE_EXT.get(ticker))


@pytest.fixture
def no_waits(monkeypatch):
    """Out-of-memory retries without the real backoff sleeps or a psutil reading."""
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(AUTO, "_available_memory", lambda: None)
    return sleeps


# ─────────────────────────────────────────────────────────────────────────────
# A. golden make_key digests - computed with the code as it was BEFORE `tag` existed
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


_GOLDEN = [
    (lambda: (_base_ctx(), {"knob": 1.0}, 10, 20),
     "ffc77f1b1544fea5eea6ac8a0b5ad8cc16b30964"),
    (lambda: (None, {"knob": 1.0}, 0, 10),
     "ba7ca2f3bdefe94840bc126f741464d25527aa53"),
    (lambda: ({}, {}, None, None),
     "a415e532787b7391235051805d66010d5db50f87"),
    (lambda: (dict(_base_ctx(), roll_guard="v4|unplanned|abc123", sizing={"risk_parity": True}),
              {"knob": 2.5, "knob2": 3, "mode": "x"}, 0, 300),
     "e1e67cb5656831aa9c8b54980d55eb37fab1a3cf"),
    (lambda: (_base_ctx(), {"b": 2, "a": 1.0 / 3}, 0, 1000),
     "4c2a9e3825e52bb1be903b4c2590ef4054e7dc14"),
]


@pytest.mark.parametrize("args_fn,digest", _GOLDEN)
def test_make_key_golden_digests_unchanged(args_fn, digest):
    ctx, params, a, b = args_fn()
    assert TC.make_key(ctx, params, a, b) == digest
    assert TC.make_key(ctx, params, a, b, tag=None) == digest      # explicit None == absent


@pytest.mark.parametrize("args_fn,digest", _GOLDEN)
def test_make_key_tag_changes_the_key(args_fn, digest):
    ctx, params, a, b = args_fn()
    tagged = {TC.make_key(ctx, params, a, b, tag=t)
              for t in ("full:v1", "etop:v1|years=1.0|cap=110|ndp=None|a=0|b=400",
                        "warm:v1|wd=3|w=240", "iscurve:v1|cap=80")}
    assert digest not in tagged
    assert len(tagged) == 4


# ─────────────────────────────────────────────────────────────────────────────
# synthetic strategy + arrays
# ─────────────────────────────────────────────────────────────────────────────

_STRATEGY_SRC = '''
STRATEGY_NAME = "SYN TAIL CACHE TEST"
DEFAULT_PARAMS = {
    "knob": {"type": "float", "min": 0.5, "max": 5.0, "step": 0.5, "default": 2.0},
    "knob2": {"type": "int", "min": 1, "max": 5, "step": 1, "default": 3},
}


def run_backtest(opens, highs, lows, closes, knob=2.0, knob2=3, return_trades=False, **kw):
    n = len(closes)
    if n < 10:
        return None
    trades = []
    # knob2 == 5 trades nothing over a long window (the full 400-bar run) while still
    # trading on the shorter search / out-of-sample slices -> an EMPTY equity-top entry.
    # (It also loses 3 pts a trade, so it never becomes the winner, whose own full-window
    # trades the whole equity / DSR block needs.)
    if not (knob2 == 5 and n >= 380):
        step = 3 + int(knob2)
        hold = 2
        for i in range(0, n - hold, step):
            pnl = (float(closes[i + hold]) - float(closes[i])) * float(knob) * 0.5 \\
                + (float(knob) - 2.5) * 0.3 - (3.0 if knob2 == 5 else 0.0)
            trades.append((i, i + hold, pnl))
    pnls = [t[2] for t in trades]
    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gw = sum(x for x in pnls if x > 0)
    gl = -sum(x for x in pnls if x < 0)
    total = float(sum(pnls))
    cum = peak = mdd = 0.0
    for x in pnls:
        cum += x
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    out = {"total_pnl": total, "num_trades": len(pnls),
           "win_rate": (100.0 * wins / len(pnls)) if pnls else 0.0,
           "profit_factor": (gw / gl) if gl > 1e-9 else (99.0 if gw > 0 else 0.0),
           "max_drawdown": float(mdd), "avg_pnl": (total / len(pnls)) if pnls else 0.0,
           "wins": wins, "losses": losses}
    if return_trades:
        out["trades"] = trades
    return out
'''


def _write_strategy(tmp_path, name="syn_tail_cache_strategy.py", src=_STRATEGY_SRC):
    p = tmp_path / name
    p.write_text(src, encoding="utf-8")
    return str(p)


def _syn_arrays(n=400):
    rng = np.random.default_rng(7)
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n))
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1D")
    return {
        "open": close.copy(), "high": close + 1.0, "low": close - 1.0, "close": close.copy(),
        "volume": np.full(n, 1000.0), "day_id": (np.arange(n) // 20).astype("int64"),
        "index": idx,
        "meta": {"name": "SYN_TAIL_MASTER", "instrument": "SYNT", "timeframe": "5m",
                 "source": "test"},
        "fingerprint": "tailcachefingerprint" + "0" * 20,
    }


_RUN_KW = dict(cost_pts=0.25, min_trades=1, n_trials=30, top_n=8, method="single",
               oos=True, seed=42, session="rth", compute_dsr=True, mc_sims=50,
               compute_neighbors=True, compute_regime=True, compute_context=False,
               auto_expand=True, compute_surrogate=False, auto_steer=False, warm_days=3)

# The surrogate bake-off needs >= 40 searched points (surrogate.MIN_POINTS); the space has
# 50 configs, so 150 draws reach nearly all of them.
_SURR_KW = dict(_RUN_KW, n_trials=150, compute_surrogate=True)


def _run(strat_path):
    return run_auto(strat_path, arrays=_syn_arrays(), **_RUN_KW)


def _json_default(o):
    item = getattr(o, "item", None)
    if callable(item):
        return o.item()
    tolist = getattr(o, "tolist", None)
    if callable(tolist):
        return o.tolist()
    return str(o)


def _canon(r):
    return json.dumps(r, sort_keys=True, default=_json_default)


def _is_neighbour(p, best):
    """neighborhood() moves ONE knob of the winner by one step."""
    return ((p["knob"] == best["knob"] and abs(p["knob2"] - best["knob2"]) <= 1)
            or (p["knob2"] == best["knob2"] and abs(p["knob"] - best["knob"]) <= 0.5 + 1e-9))


# ─────────────────────────────────────────────────────────────────────────────
# B/C/D. three-way equality: cache OFF / cold / replay
# ─────────────────────────────────────────────────────────────────────────────

def test_run_auto_tail_identical_off_cold_and_replay(tmp_path, monkeypatch):
    strat_path = _write_strategy(tmp_path)

    r_off = _run(strat_path)
    assert not os.path.exists(os.environ["AUGUR_TRIAL_CACHE_DB"])   # off writes nothing

    # the run must actually exercise every tail the cache now covers
    assert r_off.get("equity_top"), "equity_top did not run"
    assert r_off.get("dsr"), "DSR did not run"
    assert r_off.get("neighborhood"), "neighbourhood did not run"
    assert r_off["equity_top_cap"]["saved"] < r_off["equity_top_cap"]["tested"], \
        "no EMPTY equity-top entry was exercised (knob2 == 5 configs)"

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    r_cold = _run(strat_path)
    cold = TC.get_stats()
    assert cold["misses"] > 0
    assert TC.health_stats()["put_failed"] == 0

    TC.reset_stats()
    r_replay = _run(strat_path)
    rep = TC.get_stats()
    assert rep["hits"] > 0
    assert rep["misses"] == 0, "the replay recomputed something the cold run should have cached"

    assert _canon(r_off) == _canon(r_cold)
    assert _canon(r_cold) == _canon(r_replay)
    assert r_off == r_cold == r_replay


def test_tagged_keys_disjoint_from_plain_keys(tmp_path, monkeypatch):
    strat_path = _write_strategy(tmp_path)
    seen = []
    real = TC.make_key

    def _spy(ctx, params, a=None, b=None, tag=None):
        k = real(ctx, params, a, b, tag=tag)
        seen.append((tag, k))
        return k

    monkeypatch.setattr(TC, "make_key", _spy)
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    _run(strat_path)

    plain = {k for t, k in seen if t is None}
    tagged = {k for t, k in seen if t is not None}
    families = {t.split(":")[0] for t, _ in seen if t is not None}
    assert plain and tagged
    assert families == {"warm", "etop", "full"}
    assert not (plain & tagged)
    for fam in families:      # and the three families never collide with each other
        fk = {k for t, k in seen if t is not None and t.startswith(fam + ":")}
        other = {k for t, k in seen if t is not None and not t.startswith(fam + ":")}
        assert not (fk & other)


def test_warm_leg_cached_only_when_the_warm_branch_succeeded(tmp_path, monkeypatch):
    """A strategy that returns no trade list cannot be warmed: ev falls back to the cold
    slice, and that cold result must never be written under the warm tag."""
    src = _STRATEGY_SRC.replace('    if return_trades:\n        out["trades"] = trades\n', "")
    assert src != _STRATEGY_SRC
    strat_path = _write_strategy(tmp_path, name="syn_tail_no_trades.py", src=src)
    arrays = _syn_arrays()
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    mod = load_strategy(strat_path)
    ctx = TC.build_ctx(mod, arrays, cost_pts=0.0)
    assert ctx is not None
    ev = make_slice_evaluator(mod, arrays, 0.0, cache_ctx=ctx, warm_days=3)
    params = {"knob": 2.0, "knob2": 3}
    m1 = ev(300, 400, params, warm=True)
    m_cold = make_slice_evaluator(mod, arrays, 0.0)(300, 400, params)
    assert m1 == m_cold                                   # the cold fallback, as before
    wkey = TC.make_key(ctx, params, 300, 400, tag="warm:v1|wd=3|w=240")
    assert TC.get(wkey) is None                           # never cached under the warm tag
    assert TC.get(TC.make_key(ctx, params, 300, 400)) is not None   # cold key as always


def test_warm_leg_replay_matches_compute(tmp_path, monkeypatch):
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()
    mod = load_strategy(strat_path)
    params = {"knob": 3.5, "knob2": 2}
    want = make_slice_evaluator(mod, arrays, 0.25, warm_days=3)(300, 400, params, warm=True)
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    ctx = TC.build_ctx(mod, arrays, cost_pts=0.25)
    ev = make_slice_evaluator(mod, arrays, 0.25, cache_ctx=ctx, warm_days=3)
    TC.reset_stats()
    got_cold = ev(300, 400, params, warm=True)
    assert TC.get_stats() == {"hits": 0, "misses": 1}
    got_hit = ev(300, 400, params, warm=True)
    assert TC.get_stats() == {"hits": 1, "misses": 1}
    assert want == got_cold == got_hit
    assert "trades" not in got_hit
    # keep_trades=True is never served from the cache
    full = ev(300, 400, params, keep_trades=True, warm=True)
    assert full.get("trades") is not None
    assert TC.get_stats() == {"hits": 1, "misses": 1}


def test_crashed_equity_top_backtest_is_never_cached(tmp_path, monkeypatch):
    """A config whose full-window backtest RAISES on the cold run (a transient failure)
    must not be cached as "this config has no trades" - otherwise every replay silently
    drops its curve from equity_top and its Sharpe from the DSR. The replay recomputes it
    (one miss) and the whole result equals the cache-off one again."""
    strat_path = _write_strategy(tmp_path)
    mod = load_strategy(strat_path)
    real = mod.run_backtest
    n_full = len(_syn_arrays()["close"])
    crash = {"params": None, "n": 0}

    def wrapped(opens, highs, lows, closes, **kw):
        tp = crash["params"]
        if tp is not None and len(closes) == n_full and all(kw.get(k) == v for k, v in tp.items()):
            crash["n"] += 1
            raise MemoryError("synthetic transient failure")
        return real(opens, highs, lows, closes, **kw)

    monkeypatch.setattr(mod, "run_backtest", wrapped)
    r_off = run_auto(mod, arrays=_syn_arrays(), **_RUN_KW)
    best = r_off["best_params"]
    # a non-winner that trades over the full window and is no neighbour of the winner, so
    # only the equity-top / DSR loops ever run it on the full window
    target = next(({"knob": r["knob"], "knob2": r["knob2"]} for r in r_off["top"]
                   if r["knob2"] != 5 and {"knob": r["knob"], "knob2": r["knob2"]} != best
                   and not _is_neighbour(r, best)), None)
    assert target is not None, r_off["top"]

    etop_keys = []
    real_make_key = TC.make_key

    def _spy(ctx, params, a=None, b=None, tag=None):
        k = real_make_key(ctx, params, a, b, tag=tag)
        if tag is not None and tag.startswith("etop:") and dict(params) == target:
            etop_keys.append(k)
        return k

    monkeypatch.setattr(TC, "make_key", _spy)
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    crash["params"] = target
    run_auto(mod, arrays=_syn_arrays(), **_RUN_KW)      # cold: the target crashes every time
    assert crash["n"] >= 1 and etop_keys
    assert all(TC.get(k) is None for k in etop_keys), "a crashed backtest was cached"

    crash["params"] = None
    TC.reset_stats()
    r_rep = run_auto(mod, arrays=_syn_arrays(), **_RUN_KW)
    assert TC.get_stats()["misses"] == 1                 # the target's entry, recomputed
    assert _canon(r_rep) == _canon(r_off)


def test_surrogate_in_sample_curves_replay_from_the_cache(tmp_path, monkeypatch):
    """The surrogate bake-off's per-pick in-sample curves (and the sampled best's) were one
    uncached backtest each on every restart. Cached under "iscurve:v1", the replay runs no
    in-sample backtest at all, and every number is unchanged."""
    strat_path = _write_strategy(tmp_path)
    mod = load_strategy(strat_path)
    real = mod.run_backtest
    ksplit = int(len(_syn_arrays()["close"]) * AUTO.OOS_SPLIT)
    is_calls = {"n": 0}

    def counted(opens, highs, lows, closes, **kw):
        if len(closes) == ksplit:
            is_calls["n"] += 1
        return real(opens, highs, lows, closes, **kw)

    monkeypatch.setattr(mod, "run_backtest", counted)
    r_off = run_auto(mod, arrays=_syn_arrays(), **_SURR_KW)
    surr = r_off.get("surrogate") or {}
    assert surr.get("models"), f"the surrogate bake-off did not run: {surr}"
    assert surr.get("sampled_best_curve"), "no in-sample curve was built"

    tags = []
    real_make_key = TC.make_key

    def _spy(ctx, params, a=None, b=None, tag=None):
        tags.append(tag)
        return real_make_key(ctx, params, a, b, tag=tag)

    monkeypatch.setattr(TC, "make_key", _spy)
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    r_cold = run_auto(mod, arrays=_syn_arrays(), **_SURR_KW)
    assert any(t and t.startswith("iscurve:") for t in tags)

    TC.reset_stats()
    is_calls["n"] = 0
    r_rep = run_auto(mod, arrays=_syn_arrays(), **_SURR_KW)
    assert TC.get_stats()["misses"] == 0
    assert is_calls["n"] == 0, "the replay re-ran an in-sample backtest"
    assert _canon(r_off) == _canon(r_cold) == _canon(r_rep)


# ─────────────────────────────────────────────────────────────────────────────
# E. out-of-memory retry / raise; other exceptions -> None, counted by class
# ─────────────────────────────────────────────────────────────────────────────

def _enomem():
    return OSError(errno.ENOMEM, "Cannot allocate memory")


class _PagingFileTooSmall(OSError):
    """What Windows raises when a commit of the paging file fails (winerror 1455) - built
    portably: CI runs on Linux, where OSError carries no winerror of its own."""
    winerror = property(lambda self: 1455)


def _flaky_module(tmp_path, monkeypatch, fail_times, exc=MemoryError):
    """`exc`: an exception class (raised with a message) or a zero-argument factory."""
    mod = load_strategy(_write_strategy(tmp_path, name="syn_tail_flaky.py"))
    real = mod.run_backtest
    calls = {"n": 0, "left": fail_times}

    def flaky(opens, highs, lows, closes, **kw):
        calls["n"] += 1
        if calls["left"] is None or calls["left"] > 0:
            if calls["left"] is not None:
                calls["left"] -= 1
            raise (exc("synthetic allocation failure") if isinstance(exc, type) else exc())
        return real(opens, highs, lows, closes, **kw)

    monkeypatch.setattr(mod, "run_backtest", flaky)
    return mod, real, calls


def test_is_oom_tells_memory_failures_from_other_os_errors():
    assert AUTO._is_oom(MemoryError())
    assert AUTO._is_oom(_enomem())
    assert AUTO._is_oom(_PagingFileTooSmall("The paging file is too small"))
    for e in (OSError("x"), FileNotFoundError(errno.ENOENT, "gone", "rolls_NQ.csv"),
              PermissionError(errno.EACCES, "locked", "rolls_NQ.csv"), TimeoutError(),
              ConnectionResetError(), ValueError(), RuntimeError()):
        assert not AUTO._is_oom(e), e


def test_memory_error_is_retried_then_succeeds(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(AUTO, "_available_memory", lambda: None)      # no psutil reading
    mod, real, calls = _flaky_module(tmp_path, monkeypatch, fail_times=2)
    arrays = _syn_arrays()
    params = {"knob": 2.0, "knob2": 3}
    got = make_slice_evaluator(mod, arrays, 0.25)(0, 300, params)
    want = make_slice_evaluator(load_strategy(_write_strategy(tmp_path, name="syn_tail_ok.py")),
                                arrays, 0.25)(0, 300, params)
    assert got == want
    assert calls["n"] == 3
    assert sleeps == [15, 30]
    assert TC.health_stats()["none_trials"] == {}


def test_memory_error_after_every_retry_raises(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(AUTO, "_available_memory", lambda: None)
    mod, _, calls = _flaky_module(tmp_path, monkeypatch, fail_times=None)
    ev = make_slice_evaluator(mod, _syn_arrays(), 0.0)
    mark = AUTO.oom_mark()
    with pytest.raises(RuntimeError, match="out of memory after retries"):
        ev(0, 300, {"knob": 2.0, "knob2": 3})
    assert calls["n"] == 1 + AUTO._OOM_RETRIES
    assert sleeps == [15, 30, 60]
    assert AUTO.oom_mark() == mark + 1                 # counted, for the stage-boundary check


def test_memory_error_with_plenty_of_ram_still_backs_off(tmp_path, monkeypatch):
    """psutil's 'available' is physical RAM, not the Windows commit limit a MemoryError
    usually means: even with plenty of it reported, every retry waits its backoff step
    (they used to run back to back in 0.1 s), and the final error says what it saw."""
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(AUTO, "_available_memory", lambda: 8 * 1024 ** 3)
    mod, _, calls = _flaky_module(tmp_path, monkeypatch, fail_times=None)
    with pytest.raises(AUTO.EngineOutOfMemory,
                       match=r"RAM available before the last attempt: 8\.0 GiB"):
        make_slice_evaluator(mod, _syn_arrays(), 0.0)(0, 300, {"knob": 2.0, "knob2": 3})
    assert sleeps == [15, 30, 60]
    assert calls["n"] == 1 + AUTO._OOM_RETRIES


def test_memory_wait_polls_until_memory_returns_and_caps_total_wait(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    low = 1 * 1024 ** 3
    monkeypatch.setattr(AUTO, "_available_memory", lambda: low)        # never recovers
    mod, _, calls = _flaky_module(tmp_path, monkeypatch, fail_times=None, exc=_enomem)
    ev = make_slice_evaluator(mod, _syn_arrays(), 0.0)
    with pytest.raises(AUTO.EngineOutOfMemory):
        ev(0, 300, {"knob": 2.0, "knob2": 3})
    assert sum(sleeps) == AUTO._OOM_MAX_WAIT_S        # ~10 min in all, then it gives up
    assert sleeps[:3] == [15, 30, 60]
    assert calls["n"] == 1 + AUTO._OOM_RETRIES

    # memory is back by the second reading -> exactly two sleeps, then the retry succeeds
    sleeps.clear()
    readings = iter([low, 4 * 1024 ** 3])
    monkeypatch.setattr(AUTO, "_available_memory", lambda: next(readings))
    mod2, _, calls2 = _flaky_module(tmp_path, monkeypatch, fail_times=1)
    m = make_slice_evaluator(mod2, _syn_arrays(), 0.0)(0, 300, {"knob": 2.0, "knob2": 3})
    assert m and m["num_trades"] > 0
    assert sleeps == [15, 30]
    assert calls2["n"] == 2


def test_paging_file_oserror_counts_as_out_of_memory(tmp_path, no_waits, monkeypatch):
    mod, _, calls = _flaky_module(tmp_path, monkeypatch, fail_times=None,
                                  exc=lambda: _PagingFileTooSmall("paging file too small"))
    with pytest.raises(AUTO.EngineOutOfMemory, match="_PagingFileTooSmall"):
        make_slice_evaluator(mod, _syn_arrays(), 0.0)(0, 300, {"knob": 2.0, "knob2": 3})
    assert calls["n"] == 1 + AUTO._OOM_RETRIES


@pytest.mark.parametrize("exc", [
    lambda: FileNotFoundError(errno.ENOENT, "No such file", "rolls_NQ.csv"),
    lambda: PermissionError(errno.EACCES, "being used by another process", "rolls_NQ.csv"),
    lambda: TimeoutError("read timed out"),
    lambda: ConnectionResetError("reset by peer"),
])
def test_non_memory_oserrors_are_not_retried_and_return_none(tmp_path, no_waits, monkeypatch,
                                                              exc):
    """A missing or briefly locked side file is a strategy failure for that config - None,
    counted by class, as before W46 - not an 'out of memory' that stops the job."""
    mod, _, calls = _flaky_module(tmp_path, monkeypatch, fail_times=None, exc=exc)
    mark = AUTO.oom_mark()
    assert make_slice_evaluator(mod, _syn_arrays(), 0.0)(0, 300, {"knob": 2.0, "knob2": 3}) is None
    assert calls["n"] == 1
    assert no_waits == []
    assert TC.health_stats()["none_trials"] == {type(exc()).__name__: 1}
    assert AUTO.oom_mark() == mark


def test_run_auto_raises_instead_of_scoring_oom_configs_as_no_result(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(AUTO, "_available_memory", lambda: None)
    mod, _, _ = _flaky_module(tmp_path, monkeypatch, fail_times=None)
    with pytest.raises(RuntimeError, match="out of memory after retries"):
        run_auto(mod, arrays=_syn_arrays(), n_trials=3, min_trades=1, oos=True,
                 method="single", seed=42, auto_expand=False)


def test_run_auto_raises_when_the_surrogate_bakeoff_swallowed_an_oom(tmp_path, no_waits,
                                                                     monkeypatch):
    """surrogate_bakeoff scores each model pick inside its own `except Exception: m = None`.
    An out-of-memory pick must still stop the job - and the picks after it must not each pay
    a fresh round of retries first."""
    import augur_engine.surrogate as SUR
    mod = load_strategy(_write_strategy(tmp_path))
    real = mod.run_backtest
    flag = {"on": False, "raised": 0}

    def wrapped(opens, highs, lows, closes, **kw):
        if flag["on"]:
            flag["raised"] += 1
            raise MemoryError("synthetic allocation failure")
        return real(opens, highs, lows, closes, **kw)

    monkeypatch.setattr(mod, "run_backtest", wrapped)
    real_bake = SUR.surrogate_bakeoff
    picks = []

    def bake(*a, **k):
        gt = k["ground_truth_fn"]

        def gt_oom(p):
            picks.append(dict(p))
            flag["on"] = True
            try:
                return gt(p)
            finally:
                flag["on"] = False

        k["ground_truth_fn"] = gt_oom
        return real_bake(*a, **k)

    monkeypatch.setattr(SUR, "surrogate_bakeoff", bake)
    with pytest.raises(AUTO.EngineOutOfMemory, match="out of memory after retries"):
        run_auto(mod, arrays=_syn_arrays(), **_SURR_KW)
    assert picks, "no model pick was ground-truthed"
    assert flag["raised"] == 1 + AUTO._OOM_RETRIES


def test_other_exceptions_still_return_none_and_are_counted(tmp_path, monkeypatch):
    mod, _, calls = _flaky_module(tmp_path, monkeypatch, fail_times=None, exc=ValueError)
    ev = make_slice_evaluator(mod, _syn_arrays(), 0.0)
    assert ev(0, 300, {"knob": 2.0, "knob2": 3}) is None
    assert ev(0, 200, {"knob": 2.0, "knob2": 3}) is None
    assert calls["n"] == 2                                 # no retry for a plain bug
    assert TC.health_stats()["none_trials"] == {"ValueError": 2}


def test_stage_clock_reraises_an_oom_a_broad_handler_swallowed(tmp_path, no_waits, monkeypatch):
    import augur_engine.validate as validate_mod
    mark = AUTO.oom_mark()
    clk = validate_mod._StageClock(check=lambda: AUTO.raise_if_oom_since(mark))
    clk.begin("selection")
    mod, _, _ = _flaky_module(tmp_path, monkeypatch, fail_times=None)
    try:
        make_slice_evaluator(mod, _syn_arrays(), 0.0)(0, 300, {"knob": 2.0, "knob2": 3})
    except Exception:
        pass                                   # what an older `except Exception` does
    with pytest.raises(AUTO.EngineOutOfMemory, match="out of memory after retries"):
        clk.end("selection")
    with pytest.raises(AUTO.EngineOutOfMemory):
        clk.begin("lockbox")                   # and the next stage never starts


# ─────────────────────────────────────────────────────────────────────────────
# F. failed cache writes are counted, never fatal; the runner line reports them
# ─────────────────────────────────────────────────────────────────────────────

def _boom_put(*a, **k):
    raise OSError("database is locked")


def test_failed_put_is_counted_and_result_unchanged(tmp_path, monkeypatch):
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()
    mod = load_strategy(strat_path)
    params = {"knob": 2.0, "knob2": 3}
    want = make_slice_evaluator(mod, arrays, 0.0)(0, 300, params)

    monkeypatch.setattr(TC, "put", _boom_put)
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    ctx = TC.build_ctx(mod, arrays, cost_pts=0.0)
    ev = make_slice_evaluator(mod, arrays, 0.0, cache_ctx=ctx, warm_days=3)
    assert ev(0, 300, params) == want
    assert ev(300, 400, params, warm=True) is not None
    assert TC.health_stats()["put_failed"] == 2


def test_failed_put_in_run_backtest_and_run_grid_is_counted(tmp_path, monkeypatch):
    """engine.run_backtest and optimize.run_grid's single-thread loop write through
    TC.put directly; their failed writes are counted too, and nothing else changes."""
    from augur_engine.engine import run_backtest
    from augur_engine.optimize import run_grid
    strat_path = _write_strategy(tmp_path)
    arrays = _syn_arrays()
    bt_kw = dict(arrays=arrays, params={"knob": 2.0, "knob2": 3}, cost_pts=0.25)
    grid_kw = dict(arrays=arrays, grid={"knob": [1.5, 2.0], "knob2": [3]}, cost_pts=0.25,
                   min_trades=1, workers=1)
    want_bt = run_backtest(strat_path, **bt_kw)
    want_grid = run_grid(strat_path, **grid_kw)

    monkeypatch.setattr(TC, "put", _boom_put)
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    got_bt = run_backtest(strat_path, **bt_kw)
    assert TC.get_stats()["misses"] == 1                   # the cache path really ran
    assert TC.health_stats()["put_failed"] == 1
    TC.reset_stats()
    got_grid = run_grid(strat_path, **grid_kw)
    assert TC.get_stats()["misses"] == 2
    assert TC.health_stats()["put_failed"] == 2
    assert _canon(got_bt) == _canon(want_bt)
    assert _canon(got_grid) == _canon(want_grid)


def test_health_delta_and_merge_count_other_processes_only():
    h0 = TC.health_stats()
    TC.record_put_failed()
    TC.record_none("ValueError")
    TC.record_none("ValueError")
    TC.record_none(KeyError)
    d = TC.health_delta(h0, TC.health_stats(), pid=os.getpid())
    assert d == {"pid": os.getpid(), "put_failed": 1,
                 "none_trials": {"KeyError": 1, "ValueError": 2}}
    TC.merge_health(d)                            # produced in THIS process: already counted
    assert TC.health_stats() == {"put_failed": 1, "none_trials": {"KeyError": 1, "ValueError": 2}}
    TC.merge_health(dict(d, pid=-1))              # a worker's
    assert TC.health_stats() == {"put_failed": 2, "none_trials": {"KeyError": 2, "ValueError": 4}}
    TC.merge_health(None)                         # never raises
    TC.merge_health({"pid": -1, "put_failed": "not a number"})
    assert TC.health_stats()["put_failed"] == 2


_NONE_STRATEGY_SRC = _STRATEGY_SRC.replace(
    "    n = len(closes)\n",
    "    n = len(closes)\n    if int(knob2) == 2:\n        raise ValueError('synthetic strategy bug')\n", 1)

_WF_KW = dict(method="walkforward", wf_folds=2, n_trials=10, seed=11, min_trades=1,
              cost_pts=0.25, oos=True, auto_expand=False)


def test_walk_forward_worker_counts_reach_the_parent(tmp_path, capsys, monkeypatch):
    """Stage B's folds run in wf_pool workers; their None backtests (and failed cache
    writes) used to stay in those processes, so the runner's line under-reported."""
    # Spawned workers import augur_engine through THIS process's sys.path, which some tools
    # collected earlier in a session (tools/rocfrontier/feats.py, tools/balance_r1_stageA.py)
    # lead with the SHARED checkout - whose older engine would then run the folds.
    monkeypatch.syspath_prepend(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert _NONE_STRATEGY_SRC != _STRATEGY_SRC
    strat_path = _write_strategy(tmp_path, name="syn_tail_none_wf.py", src=_NONE_STRATEGY_SRC)
    seq = run_auto(strat_path, arrays=_syn_arrays(n=4500), workers=1, **_WF_KW)
    h_seq = TC.health_stats()
    assert h_seq["none_trials"].get("ValueError", 0) > 0
    TC.reset_health()
    capsys.readouterr()
    par = run_auto(strat_path, arrays=_syn_arrays(n=4500), workers=2, **_WF_KW)
    if "parallel folds failed" in capsys.readouterr().out:
        pytest.skip("the walk-forward pool could not start on this machine")
    assert TC.health_stats() == h_seq
    assert _canon(par["top"]) == _canon(seq["top"])


def _runner():
    from api import runner
    # tools/balance_r1_stageA.py (collected via tests/test_balance_r1.py) puts the SHARED
    # checkout first on sys.path at import; tests/test_balance_r1.py now binds this tree's
    # `api` before that happens. Fail with the reason if anything ever unbinds it again.
    repo_api = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api")
    assert os.path.normcase(os.path.dirname(os.path.abspath(runner.__file__))) == \
        os.path.normcase(repo_api), f"api.runner was imported from {runner.__file__}"
    return runner


def test_runner_cache_line_reports_put_failed_and_none_trials(monkeypatch, capsys):
    runner = _runner()
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")

    def _fake_run_backtest(strategy, **kw):
        TC.record_hit()
        TC.record_put_failed()
        TC.record_none("ValueError")
        return {"total_pnl": 1.0, "num_trades": 1}

    monkeypatch.setattr(runner.ae, "run_backtest", _fake_run_backtest)
    TC.record_put_failed()                       # a previous job's count must not leak in
    patch = runner.process_job({"type": "backtest", "strategy": "x.py", "params": {}})
    assert patch["status"] == "done"
    assert patch["result"]["cache_reuse"] == {"hits": 1, "misses": 0, "total": 1,
                                              "pct_reused": 100.0}
    out = capsys.readouterr().out
    assert "reused 1/1 configs (100.0%)" in out
    assert "put_failed 1" in out
    assert "none_trials {'ValueError': 1}" in out


def test_runner_reports_health_with_the_cache_off_and_on_a_failed_job(monkeypatch, capsys):
    runner = _runner()

    def _fake_ok(strategy, **kw):
        TC.record_none("ValueError")
        return {"total_pnl": 1.0, "num_trades": 1}

    monkeypatch.setattr(runner.ae, "run_backtest", _fake_ok)
    patch = runner.process_job({"type": "backtest", "strategy": "x.py", "params": {}})
    assert patch["status"] == "done"
    assert "cache_reuse" not in patch["result"]
    out = capsys.readouterr().out
    assert "-> engine: none_trials {'ValueError': 1}" in out
    assert "cache: reused" not in out

    def _fake_oom(strategy, **kw):
        TC.record_put_failed()
        TC.record_none("ValueError")
        raise AUTO.EngineOutOfMemory("out of memory after retries: synthetic")

    monkeypatch.setattr(runner.ae, "run_backtest", _fake_oom)
    patch = runner.process_job({"type": "backtest", "strategy": "x.py", "params": {}})
    assert patch["status"] == "error"
    assert patch["error"].startswith("EngineOutOfMemory: out of memory after retries")
    out = capsys.readouterr().out
    assert "engine (job failed): put_failed 1 none_trials {'ValueError': 1}" in out


def test_runner_labels_validate_reuse_parent_only_when_folds_ran_in_workers(monkeypatch,
                                                                            capsys):
    runner = _runner()
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    monkeypatch.setenv("EDGELOG_VALIDATE_WORKERS", "3")
    monkeypatch.setattr(runner.ae, "gate_plugin", lambda path: None)

    def _fake_validate(strategy, **kw):
        TC.record_hit()
        TC.merge_health({"pid": -1, "put_failed": 2, "none_trials": {"ValueError": 3}})
        return {"mode": "validate"}

    monkeypatch.setattr(runner.ae, "run_validate", _fake_validate)
    patch = runner.process_job({"type": "validate", "strategy": "syn_missing_file.py"})
    assert patch["status"] == "done", patch
    assert "parent-process only" in patch["result"]["cache_reuse"]["note"]
    out = capsys.readouterr().out
    assert ("[hits/total parent-process only; validate workers>1] put_failed 2 "
            "none_trials {'ValueError': 3}") in out


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward pool: a failed fold stops the running workers; an out-of-memory worker
# is answered by an identical in-line re-run
# ─────────────────────────────────────────────────────────────────────────────

def test_a_failed_fold_terminates_the_still_running_workers(monkeypatch):
    """shutdown(wait=False, cancel_futures=True) only cancels folds that had not started;
    a running one kept computing (with its own copy of the master) next to the caller's
    in-line re-run, or into the next job."""
    import operator
    from concurrent.futures import ProcessPoolExecutor
    seen = {}

    def fake_boot(specs, nproc, *a, **k):
        ex = ProcessPoolExecutor(max_workers=2)
        futs = [ex.submit(time.sleep, 120), ex.submit(operator.truediv, 1, 0)]
        seen["procs"] = list(dict(getattr(ex, "_processes", None) or {}).values())
        return ex, futs

    monkeypatch.setattr(AUTO, "_boot_wf_pool", fake_boot)
    specs = [(0, 0, 10, 10, 20), (1, 0, 20, 20, 30)]
    try:
        t0 = time.monotonic()
        with pytest.raises(ZeroDivisionError):
            AUTO._run_folds_parallel("unused.py", None, None, None, None, 0.0, "rth", {}, {},
                                     [], 1, 1, 1, specs, 2, None, 2)
        procs = seen.get("procs") or []
        if not procs:
            pytest.skip("this Python's ProcessPoolExecutor exposes no worker list")
        for p in procs:
            p.join(15)
        assert not any(p.is_alive() for p in procs), "a worker kept running its fold"
        assert time.monotonic() - t0 < 60
    finally:
        for p in seen.get("procs") or []:
            if p.is_alive():
                p.terminate()


def test_worker_out_of_memory_reruns_the_folds_in_line_identically(tmp_path, monkeypatch,
                                                                    capsys):
    strat_path = _write_strategy(tmp_path)
    seq = run_auto(strat_path, arrays=_syn_arrays(n=4500), workers=1, **_WF_KW)

    def _oom_pool(*a, **k):
        raise AUTO.EngineOutOfMemory("out of memory after retries: a fold worker (synthetic)")

    monkeypatch.setattr(AUTO, "_run_folds_parallel", _oom_pool)
    mark = AUTO.oom_mark()
    capsys.readouterr()
    par = run_auto(strat_path, arrays=_syn_arrays(n=4500), workers=2, **_WF_KW)
    assert _canon(par) == _canon(seq)
    assert AUTO.oom_mark() == mark          # recovered in-line: nothing for a caller to re-raise
    assert "a fold worker ran out of memory" in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# G. run_validate stage markers, timings and code stamps (metadata only)
# ─────────────────────────────────────────────────────────────────────────────

_V_IDX = pd.date_range(pd.Timestamp("2020-01-01", tz="US/Eastern"),
                       pd.Timestamp("2020-01-26", tz="US/Eastern"), freq="5min",
                       tz="US/Eastern")
_V_CLOSE = 1000.0 + np.arange(len(_V_IDX), dtype=float)
_V_MASTER = {"filename": "SYN_TAIL_V.csv", "instrument": "SYN_TV", "timeframe": "5m",
             "date_from": "2020-01-01", "date_to": "2020-01-26", "name": "SYN_TV"}


def _v_find_master(instrument, timeframe, session=None, source=None):
    return dict(_V_MASTER)


def _v_load_master_arrays(master, date_from=None, date_to=None):
    idx = _V_IDX
    mask = np.ones(len(idx), dtype=bool)
    if date_from:
        mask &= (idx >= pd.Timestamp(date_from, tz="US/Eastern"))
    if date_to:
        mask &= (idx < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
    sub_idx, sub_close = idx[mask], _V_CLOSE[mask]
    n = len(sub_close)
    day_id = (pd.factorize(pd.Series(sub_idx).dt.date)[0].astype("int64")
              if n else np.array([], dtype="int64"))
    return {"open": sub_close.copy(), "high": sub_close + 1.0, "low": sub_close - 1.0,
            "close": sub_close.copy(), "volume": np.full(n, 1000.0), "day_id": day_id,
            "index": sub_idx, "meta": master}


def _v_patch(monkeypatch, loader=_v_load_master_arrays):
    import augur_engine.engine as engine_mod
    import augur_engine.optimize as optimize_mod
    import augur_engine.validate as validate_mod
    for m in (validate_mod, AUTO, engine_mod, optimize_mod):
        monkeypatch.setattr(m, "find_master", _v_find_master)
        monkeypatch.setattr(m, "load_master_arrays", loader)
    return validate_mod


def _v_strategy():
    mod = types.ModuleType("fake_tail_validate_strategy")
    mod.STRATEGY_NAME = "SYN TAIL VALIDATE"
    mod.DEFAULT_PARAMS = {"knob": {"type": "float", "min": 0.0, "max": 10.0,
                                   "step": 0.5, "default": 5.0}}

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        n = len(c)
        pnl = 50.0 * (n / 100.0) + (10.0 - abs(float(knob) - 3.0))
        trades_n = 10
        out = {"total_pnl": float(pnl), "num_trades": trades_n, "win_rate": 60.0,
               "profit_factor": 3.0 if pnl > 0 else 0.3, "max_drawdown": -10.0,
               "avg_pnl": pnl / trades_n, "wins": 5, "losses": 5}
        if return_trades:
            out["trades"] = [(i, i + 1, pnl / trades_n, 1, 100.0) for i in range(trades_n)]
        return out

    mod.run_backtest = run_backtest
    return mod


_V_KW = dict(instrument="SYN_TV", timeframe="5m", session="rth", source=None,
             cost_pts=0.0, min_trades=1, n_trials=20, wf_folds=2, seed=42,
             lockbox_months=0.2, equity_points=200, select_oos_topk=3, compute_pills=False)


def _git_head():
    """`git rev-parse HEAD` of this tree, or None when git cannot say here."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=30)
    except Exception:
        return None
    sha = (r.stdout or "").strip()
    return sha if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else None


def test_run_validate_saves_timings_and_code_stamps(monkeypatch, capsys):
    import augur_engine
    validate_mod = _v_patch(monkeypatch)
    res = validate_mod.run_validate(_v_strategy(), **_V_KW, warm_days=0)
    tm = res["timings"]
    for stage in ("stage_a", "stage_a_search", "stage_a_tail", "stage_b", "stage_b_rolling",
                  "stage_b_anchored", "selection", "lockbox", "whole_run", "surrogate",
                  "gate", "pills", "total"):
        assert stage in tm, stage
        assert isinstance(tm[stage], float) and tm[stage] >= 0.0
    assert tm["total"] >= tm["stage_a"]
    stamps = res["code_stamps"]
    assert [s["stage"] for s in stamps] == ["stage_a", "stage_b", "selection", "lockbox",
                                            "whole_run", "surrogate", "gate", "pills"]
    head = _git_head()
    for s in stamps:
        assert set(s) == {"stage", "git_sha", "disk_git_sha", "engine_epoch"}
        assert s["engine_epoch"] == augur_engine.ENGINE_CACHE_EPOCH
        assert s["git_sha"] == validate_mod._LOADED_GIT_SHA    # the code that RAN
        if head is not None:                                  # nothing shipped mid-test
            assert s["git_sha"] == head and s["disk_git_sha"] == head
    json.dumps({"timings": tm, "code_stamps": stamps})          # saveable as-is
    out = capsys.readouterr().out
    for marker in ("STAGE stage_a start", "STAGE stage_a stage_a_search done",
                   "STAGE stage_a end", "STAGE stage_b start", "STAGE stage_b end",
                   "STAGE lockbox start", "STAGE surrogate end", "STAGE gate end",
                   "STAGE validate end", "[cache put_failed 0 none_trials {}]"):
        assert marker in out, marker


def test_engine_git_sha_is_the_repo_head_read_once_at_import(monkeypatch):
    """`git_sha` must be the commit this process LOADED: the runner keeps running its
    boot-time code while ships fast-forward the checkout under it. '' only when git
    really cannot answer - never quietly '' when it can."""
    import augur_engine.validate as validate_mod
    head = _git_head()
    if head is None:
        pytest.skip("git cannot read this tree's HEAD here")
    assert validate_mod._engine_git_sha() == head
    assert validate_mod._LOADED_GIT_SHA == head

    def _no_git(*a, **k):
        raise OSError("git is not installed")

    monkeypatch.setattr(subprocess, "run", _no_git)
    assert validate_mod._engine_git_sha() == ""


def test_code_stamps_carry_the_loaded_commit_and_the_disk_head(monkeypatch):
    import augur_engine
    import augur_engine.validate as validate_mod
    monkeypatch.setattr(validate_mod, "_LOADED_GIT_SHA", "a" * 40)       # what was imported
    monkeypatch.setattr(validate_mod, "_engine_git_sha", lambda: "b" * 40)  # a ship since
    clk = validate_mod._StageClock()
    clk.begin("stage_b")
    assert clk.code_stamps == [{"stage": "stage_b", "git_sha": "a" * 40,
                                "disk_git_sha": "b" * 40,
                                "engine_epoch": augur_engine.ENGINE_CACHE_EPOCH}]


def _oom_v_strategy(flag):
    """_v_strategy, raising MemoryError while flag['on'] is set."""
    mod = _v_strategy()
    real = mod.run_backtest

    def run_backtest(o, h, l, c, knob=None, return_trades=False, **kw):
        if flag["on"]:
            flag["raised"] += 1
            raise MemoryError("synthetic allocation failure")
        return real(o, h, l, c, knob=knob, return_trades=return_trades, **kw)

    mod.run_backtest = run_backtest
    return mod


def test_run_validate_stops_when_the_lockbox_runs_out_of_memory(monkeypatch, no_waits):
    """The warm lockbox leg goes through the slice evaluator, whose out-of-memory raise
    the champion-lockbox `except Exception: lb = None` used to turn into a recorded 0-trade
    lockbox FAIL - spending the one-shot lockbox on a result that never ran."""
    validate_mod = _v_patch(monkeypatch)
    flag = {"on": False, "raised": 0}
    real_mk = validate_mod._make_lockbox_runner

    def mk(*a, **k):
        run = real_mk(*a, **k)

        def lockbox_run(params):
            flag["on"] = True
            try:
                return run(params)
            finally:
                flag["on"] = False

        return lockbox_run

    monkeypatch.setattr(validate_mod, "_make_lockbox_runner", mk)
    with pytest.raises(AUTO.EngineOutOfMemory, match="out of memory after retries"):
        validate_mod.run_validate(_oom_v_strategy(flag), **_V_KW, warm_days=2)
    assert flag["raised"] == 1 + AUTO._OOM_RETRIES       # the champion's, and nothing after


def test_run_validate_stops_when_selection_runs_out_of_memory(monkeypatch, no_waits):
    """An out-of-memory candidate in the OOS-checked selection used to be swallowed into
    selection['error'], crowning the in-sample max and opening the lockbox on it."""
    validate_mod = _v_patch(monkeypatch)
    flag = {"on": False, "raised": 0}
    real_sel = validate_mod._select_oos_champion
    lockbox_runs = []
    real_mk = validate_mod._make_lockbox_runner

    def sel(*a, **k):
        flag["on"] = True
        try:
            return real_sel(*a, **k)
        finally:
            flag["on"] = False

    def mk(*a, **k):
        run = real_mk(*a, **k)

        def lockbox_run(params):
            lockbox_runs.append(dict(params))
            return run(params)

        return lockbox_run

    monkeypatch.setattr(validate_mod, "_select_oos_champion", sel)
    monkeypatch.setattr(validate_mod, "_make_lockbox_runner", mk)
    with pytest.raises(AUTO.EngineOutOfMemory, match="out of memory after retries"):
        validate_mod.run_validate(_oom_v_strategy(flag), **_V_KW, warm_days=2)
    assert flag["raised"] == 1 + AUTO._OOM_RETRIES
    assert lockbox_runs == [], "the one-shot lockbox was opened after an out-of-memory stop"


_V_NOISY = 1000.0 + np.cumsum(np.random.default_rng(11).normal(0.0, 1.0, len(_V_IDX)))


def _v_load_master_arrays_fp(master, date_from=None, date_to=None):
    """_v_load_master_arrays on a noisy series, plus a window-specific data fingerprint so
    the trial cache is live on every path (build_ctx needs one)."""
    a = _v_load_master_arrays(master, date_from=date_from, date_to=date_to)
    idx = _V_IDX
    mask = np.ones(len(idx), dtype=bool)
    if date_from:
        mask &= (idx >= pd.Timestamp(date_from, tz="US/Eastern"))
    if date_to:
        mask &= (idx < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
    c = _V_NOISY[mask]
    a.update({"open": c.copy(), "high": c + 1.0, "low": c - 1.0, "close": c.copy(),
              "fingerprint": f"tailv|{date_from}|{date_to}|{int(mask.sum())}"})
    return a


# The end-to-end strategy is _STRATEGY_SRC THINNED 12x. Unthinned it takes ~1,200 trades
# over this 7,200-bar master, and the ML gate bake-off (ml_gate.gate_validate: five models,
# each refit every 25 trades - untouched by W46) then spent ~185 s of every run_validate, so
# three calls took 632 s and this test never finished inside a 600 s budget. Thinned, the
# gate still runs for real on ~100-150 trades (~8 s a call) and the whole test takes well
# under a minute. The knob2 == 5 cut-off moves from 380 to 5,000 bars: those configs still
# trade (and lose) on Stage A's search and out-of-sample slices (~4,100 / ~1,400 bars) but
# trade NOTHING over Stage A's full ~5,500-bar window, so EMPTY equity-top entries are
# exercised end to end as well.
_V_STRATEGY_SRC = (_STRATEGY_SRC
                   .replace("step = 3 + int(knob2)", "step = 12 * (3 + int(knob2))")
                   .replace("n >= 380", "n >= 5000"))


def test_run_validate_identical_cache_off_cold_and_replay(tmp_path, monkeypatch):
    """End to end, on Auto-Validate's own Stage A settings (steering, surrogate, DSR, MC,
    neighbourhood, regime, warm legs): every saved number is the same with the cache off,
    cold and replayed - only the W46 metadata (`timings`, `code_stamps`) may differ - and
    the replay recomputes nothing the cold run cached (warm legs, equity-top entries,
    neighbourhood runs and surrogate in-sample curves included)."""
    assert "step = 12 * (3 + int(knob2))" in _V_STRATEGY_SRC
    assert "n >= 5000" in _V_STRATEGY_SRC
    validate_mod = _v_patch(monkeypatch, loader=_v_load_master_arrays_fp)
    strat_path = _write_strategy(tmp_path, name="syn_tail_validate.py", src=_V_STRATEGY_SRC)
    # 120 trials, not 20: the surrogate bake-off needs >= 40 searched points
    # (surrogate.MIN_POINTS) before it fits, ground-truths its picks and builds their curves
    kw = dict(_V_KW, cost_pts=0.25, warm_days=2, n_trials=120)

    tags = []
    real_make_key = TC.make_key

    def _spy(ctx, params, a=None, b=None, tag=None):
        tags.append(tag)
        return real_make_key(ctx, params, a, b, tag=tag)

    monkeypatch.setattr(TC, "make_key", _spy)

    def _strip(r):
        r = dict(r)
        assert isinstance(r.pop("timings"), dict)
        assert isinstance(r.pop("code_stamps"), list)
        return _canon(r)

    res_off = validate_mod.run_validate(strat_path, **kw)
    assert not os.path.exists(os.environ["AUGUR_TRIAL_CACHE_DB"])   # off writes nothing
    # the run must actually exercise every tail the cache now covers
    assert res_off.get("equity_top"), "equity_top did not run"
    assert res_off.get("dsr"), "DSR did not run"
    assert res_off.get("neighborhood"), "neighbourhood did not run"
    assert res_off["equity_top_cap"]["saved"] < res_off["equity_top_cap"]["tested"], \
        "no EMPTY equity-top entry was exercised (knob2 == 5 configs)"
    assert (res_off.get("surrogate") or {}).get("sampled_best_curve"), \
        "the surrogate bake-off did not build its in-sample curves"
    r_off = _strip(res_off)

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    TC.reset_stats()
    tags.clear()
    r_cold = _strip(validate_mod.run_validate(strat_path, **kw))
    assert TC.get_stats()["misses"] > 0
    assert TC.health_stats()["put_failed"] == 0
    assert {t.split(":")[0] for t in tags if t is not None} == {"warm", "etop", "full",
                                                                 "iscurve"}

    TC.reset_stats()
    r_replay = _strip(validate_mod.run_validate(strat_path, **kw))
    rep = TC.get_stats()
    assert rep["hits"] > 0
    assert rep["misses"] == 0, "the replay recomputed something the cold run should have cached"
    assert TC.health_stats()["put_failed"] == 0
    assert r_off == r_cold
    assert r_cold == r_replay
