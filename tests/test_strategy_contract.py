"""Contract tests run against EVERY strategy plugin in augur_strategies/.

The whole engine relies on all strategies honoring one contract (see CLAUDE.md):
run_backtest(O,H,L,C, [volumes,day_id,index], **params, return_trades=...) -> a metrics
dict (or None when there isn't enough data). Rather than trust that by convention, this
parametrizes over list_strategies() and asserts it for each — so a new or edited plugin
that breaks the shape, is non-deterministic, or peeks at future bars fails CI.

Everything runs on seeded synthetic OHLCV through augur_engine.run_backtest (which does
the same volumes/day_id/index introspection the app and workers do), so no real data or
network is touched. The strongest check is test_no_look_ahead: truncating the tail must
not change any trade that already closed — the property a backtester lives or dies on.
"""
import numpy as np
import pandas as pd
import pytest

from augur_engine import list_strategies, run_backtest, load_strategy
from augur_engine.strategies import strategy_params

REQUIRED_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor",
                 "max_drawdown", "avg_pnl", "wins", "losses"}

# Collected at import time so every plugin becomes its own parametrized case/id.
STRATEGY_FILES = [s["file"] for s in list_strategies()]

N_DAYS, PER_DAY = 10, 78            # ~10 ET days of 5m RTH bars
TRUNCATE_KEEP_DAYS = 7             # look-ahead test removes the last 3 days


def _make_arrays(n_days=N_DAYS):
    """Seeded random-walk OHLCV with a contiguous ET day_id and a bar index."""
    rng = np.random.default_rng(7)
    n = n_days * PER_DAY
    close = 15000 + rng.normal(0, 1, n).cumsum()
    high = close + np.abs(rng.normal(0, 2, n))
    low = close - np.abs(rng.normal(0, 2, n))
    openp = close + rng.normal(0, 1, n)
    vol = np.abs(rng.normal(1000, 200, n))
    day_id = np.repeat(np.arange(n_days), PER_DAY).astype("int64")
    idx = pd.date_range("2026-03-02 09:30", periods=n, freq="5min", tz="US/Eastern")
    return {"open": openp, "high": high, "low": low, "close": close, "volume": vol,
            "day_id": day_id, "index": idx, "meta": {"name": "SYN"}}


@pytest.fixture(scope="module")
def full_arrays():
    return _make_arrays()


def _default_params(mod):
    return {k: v.get("default") for k, v in strategy_params(mod).items()
            if isinstance(v, dict) and "default" in v}


def _run(strategy_file, arrays):
    mod = load_strategy(strategy_file)
    return run_backtest(mod, arrays=arrays, params=_default_params(mod), return_trades=True)


@pytest.mark.parametrize("strategy_file", STRATEGY_FILES)
def test_declares_contract_globals(strategy_file):
    mod = load_strategy(strategy_file)
    assert isinstance(getattr(mod, "STRATEGY_NAME", None), str)
    assert isinstance(getattr(mod, "DEFAULT_PARAMS", None), dict)
    assert callable(getattr(mod, "run_backtest", None))


@pytest.mark.parametrize("strategy_file", STRATEGY_FILES)
def test_returns_none_or_wellformed_metrics(strategy_file, full_arrays):
    r = _run(strategy_file, full_arrays)
    if r is None:                                  # not enough data / no setup — allowed
        return
    assert REQUIRED_KEYS <= set(r), f"missing keys: {REQUIRED_KEYS - set(r)}"
    nt, wins, losses, wr, pf = (r["num_trades"], r["wins"], r["losses"],
                                r["win_rate"], r["profit_factor"])
    assert nt >= 0 and wins >= 0 and losses >= 0
    assert wins + losses <= nt                     # some closes may be scratches
    assert 0.0 <= wr <= 100.0
    assert pf >= 0.0 or pf == float("inf")
    assert np.isfinite(r["total_pnl"])


@pytest.mark.parametrize("strategy_file", STRATEGY_FILES)
def test_trade_tuples_carry_pnl(strategy_file, full_arrays):
    r = _run(strategy_file, full_arrays)
    for t in (r or {}).get("trades") or []:
        assert isinstance(t, (list, tuple)) and len(t) >= 3
        assert isinstance(t[2], (int, float)) and np.isfinite(t[2])


@pytest.mark.parametrize("strategy_file", STRATEGY_FILES)
def test_deterministic(strategy_file, full_arrays):
    a = _run(strategy_file, full_arrays)
    b = _run(strategy_file, full_arrays)
    if a is None:
        assert b is None
        return
    assert (a["num_trades"], a["total_pnl"], a["win_rate"]) == \
           (b["num_trades"], b["total_pnl"], b["win_rate"])


@pytest.mark.parametrize("strategy_file", STRATEGY_FILES)
def test_no_look_ahead(strategy_file, full_arrays):
    """Trades that closed before the truncation cut must be byte-identical when the
    future bars are removed. If they change, the strategy used data from after the
    exit to decide the trade — a look-ahead bug."""
    full = _run(strategy_file, full_arrays)
    trades = (full or {}).get("trades") or []
    if not trades or len(trades[0]) < 3:
        pytest.skip("strategy returns no indexed trades to check")

    cut = int((full_arrays["day_id"] < TRUNCATE_KEEP_DAYS).sum())
    truncated = {k: (v[:cut] if k in ("open", "high", "low", "close", "volume",
                                       "day_id", "index") else v)
                 for k, v in full_arrays.items()}
    tr = _run(strategy_file, truncated)
    early_after = {(t[0], t[1], round(float(t[2]), 6))
                   for t in ((tr or {}).get("trades") or []) if t[1] < cut}
    for t in trades:
        if t[1] < cut:
            assert (t[0], t[1], round(float(t[2]), 6)) in early_after, \
                f"trade closing at bar {t[1]} changed when future bars were removed"
