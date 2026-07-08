"""Contract tests for the duplicated net-metrics math.

The same "subtract per-trade cost, then re-derive net metrics from the trade list"
logic is implemented in three places that are supposed to agree — every headline
number the app and the web engine report (total PnL, win rate, profit factor,
max drawdown, ...) flows through one of them:

  * augur_engine.engine._apply_costs   — the web engine's single-thread path
  * augur_mp_worker._apply_costs       — the multiprocessing sweep workers
  * augur_engine.ml_gate._stats        — the ML-gate's post-filter metrics

`engine` and `mp_worker` are meant to be BYTE-IDENTICAL (their own docstrings say
so, and tools/test_mp_worker.py relies on it): a drift between them silently
corrupts every parallel sweep. These tests pin that invariant across the tricky
edges — empty trade list, all-wins (profit_factor -> inf), all-losses
(profit_factor -> 0), and costs applied per round-trip.

They ALSO document the one place `ml_gate._stats` currently diverges from the
`_apply_costs` pair: max drawdown when the equity curve is underwater from the
very first trade. `_apply_costs` seeds the running peak at 0.0 (drawdown measured
from flat starting equity); `_stats` seeds it at the first cumulative value, so it
under-reports drawdown for a strategy that never trades above its starting point.
The divergence test pins the current numbers so the discrepancy stays visible and
can't silently widen — see the note there before "fixing" either side.
"""
import math

import pytest

from augur_engine.engine import _apply_costs as engine_apply_costs
from augur_mp_worker import _apply_costs as mpw_apply_costs
from augur_engine.ml_gate import _stats

# The metric keys the three helpers all claim to produce.
SHARED_KEYS = ("total_pnl", "num_trades", "win_rate", "profit_factor",
               "max_drawdown", "avg_pnl", "wins", "losses")

# (id, per-trade PnLs in points). Chosen to hit each branch of the metrics math.
SCENARIOS = [
    ("mixed",               [5.0, -3.0, 4.0, -2.0]),
    ("single_win",          [7.0]),
    ("single_loss",         [-4.0]),
    ("all_wins_pf_inf",     [2.0, 3.0, 1.0]),
    ("all_losses_pf_zero",  [-2.0, -3.0]),
    ("has_zero_trade",      [3.0, 0.0, -1.0]),   # a zero is neither win nor loss
    ("recovers_late",       [-5.0, -3.0, 20.0]),
    ("big_underwater",      [-5.0, -3.0]),       # underwater from bar 0
]

# PnL series whose equity curve never dips below its starting point, so the
# peak-seeding difference between _stats and _apply_costs cannot show up.
NEVER_UNDERWATER = [
    ("mixed_up",   [5.0, -3.0, 4.0, -2.0]),
    ("all_wins",   [2.0, 3.0, 1.0]),
    ("win_first",  [10.0, -4.0, -3.0, 2.0]),
    ("flat_start", [0.0, 1.0, -0.5]),
]

COSTS = [0.0, 0.283, 1.5]


def _assert_metrics_equal(a, b, keys=SHARED_KEYS, approx=False):
    """Compare two metrics dicts on `keys`, handling inf/nan the way == won't."""
    for k in keys:
        av, bv = a[k], b[k]
        if isinstance(av, float) and math.isnan(av):
            assert isinstance(bv, float) and math.isnan(bv), f"{k}: {av!r} != {bv!r}"
        elif isinstance(av, float) and math.isinf(av):
            assert bv == av, f"{k}: {av!r} != {bv!r}"
        elif approx:
            assert bv == pytest.approx(av), f"{k}: {av!r} != {bv!r}"
        else:
            assert bv == av, f"{k}: {av!r} != {bv!r}"


# ── engine._apply_costs ≡ augur_mp_worker._apply_costs (the critical invariant) ──

@pytest.mark.parametrize("cost", COSTS)
@pytest.mark.parametrize("name,pnls", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_engine_matches_mp_worker(trades_from_pnls, name, pnls, cost):
    """The single-thread engine path and the multiprocessing workers must derive
    identical net metrics — a drift here corrupts every parallel grid sweep."""
    trades = trades_from_pnls(pnls)
    a = engine_apply_costs({"trades": list(trades)}, cost)
    b = mpw_apply_costs({"trades": list(trades)}, cost)
    _assert_metrics_equal(a, b)
    # and the net trade lists themselves (t[2] reduced by cost) must match
    assert a["trades"] == b["trades"]


@pytest.mark.parametrize("cost", COSTS)
def test_cost_subtracted_once_per_trade(trades_from_pnls, cost):
    """Net total PnL drops by exactly n * cost vs the gross series."""
    pnls = [5.0, -3.0, 4.0, -2.0]
    trades = trades_from_pnls(pnls)
    net = engine_apply_costs({"trades": list(trades)}, cost)
    assert net["total_pnl"] == pytest.approx(sum(pnls) - len(pnls) * cost)


def test_profit_factor_edges(trades_from_pnls):
    """PF is +inf with wins but no losses, and 0.0 with losses but no wins."""
    all_wins = engine_apply_costs({"trades": trades_from_pnls([1.0, 2.0])}, 0.0)
    assert all_wins["profit_factor"] == float("inf")
    all_losses = engine_apply_costs({"trades": trades_from_pnls([-1.0, -2.0])}, 0.0)
    assert all_losses["profit_factor"] == 0.0


def test_empty_trades_passthrough_is_identical(trades_from_pnls):
    """Both _apply_costs copies short-circuit on an empty/missing trade list and
    return the input dict UNCHANGED (they do not synthesize a zeroed metrics dict).
    Pin that shared behavior so neither copy starts re-deriving on its own."""
    src = {"total_pnl": 123.0, "num_trades": 0, "trades": []}
    a = engine_apply_costs(dict(src), 0.5)
    b = mpw_apply_costs(dict(src), 0.5)
    assert a == b == src


# ── ml_gate._stats vs _apply_costs ──────────────────────────────────────────────

@pytest.mark.parametrize("name,pnls", NEVER_UNDERWATER, ids=[s[0] for s in NEVER_UNDERWATER])
def test_stats_matches_apply_costs_when_not_underwater(trades_from_pnls, name, pnls):
    """When the equity curve never dips below its starting point, ml_gate._stats
    agrees with _apply_costs on every shared metric (including max_drawdown)."""
    trades = trades_from_pnls(pnls)
    costed = engine_apply_costs({"trades": list(trades)}, 0.0)
    stats = _stats([t[2] for t in trades])
    _assert_metrics_equal(costed, stats, approx=True)


def test_stats_agrees_with_apply_costs_when_underwater(trades_from_pnls):
    """After the issue #7 fix, _stats seeds its drawdown peak at flat starting equity
    (0.0) like _apply_costs, so the two agree on EVERY metric even when the curve is
    underwater from the first trade."""
    trades = trades_from_pnls([-5.0, -3.0])
    costed = engine_apply_costs({"trades": list(trades)}, 0.0)
    stats = _stats([t[2] for t in trades])
    _assert_metrics_equal(costed, stats, approx=True)


def test_underwater_drawdown_measured_from_flat_equity(trades_from_pnls):
    """A curve that is underwater from the first trade reports its true drawdown
    (measured from flat starting equity) in both helpers — the fix for issue #7."""
    trades = trades_from_pnls([-5.0, -3.0])
    costed = engine_apply_costs({"trades": list(trades)}, 0.0)
    stats = _stats([t[2] for t in trades])
    assert costed["max_drawdown"] == -8.0
    assert stats["max_drawdown"] == -8.0
