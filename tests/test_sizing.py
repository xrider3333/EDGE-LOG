"""Unit tests for augur_engine.sizing — the execution-layer position-sizing overlays.

All pure numpy: each trade's size is reweighted (risk-parity / time-of-day / side)
without touching entries or exits, then capital-matched so every scheme deploys the
same total dollar-risk. These tests pin the invariants that make the comparison fair
(capital-match, division guards, the inf-drawdown mar edge) and the individual rules.
"""
import numpy as np
import pytest

from augur_engine import sizing as S


# ── mar (drawdown-adjusted return) ──────────────────────────────────────────────

def test_mar_uses_drawdown_magnitude():
    # signed or magnitude drawdown must give the same MAR
    assert S.mar(100.0, -25.0) == 4.0
    assert S.mar(100.0, 25.0) == 4.0


def test_mar_zero_drawdown_is_inf():
    """No drawdown -> infinite MAR (documented behavior; callers treat inf as "no DD")."""
    assert S.mar(100.0, 0.0) == float("inf")
    assert S.mar(100.0, None) == float("inf")


# ── time_weight (time-of-day tier bands) ────────────────────────────────────────

@pytest.mark.parametrize("bar,expected", [
    (0, 2.0), (11, 2.0),      # first-hour band  [0, 12)
    (12, 1.0), (35, 1.0),     # mid band         [12, 36)
    (36, 0.5), (500, 0.5),    # tail band        [36, inf)
])
def test_time_weight_default_bands(bar, expected):
    assert S.time_weight([bar])[0] == expected


def test_time_weight_is_vectorized_and_ordered():
    w = S.time_weight([0, 11, 12, 35, 36, 100])
    assert w.tolist() == [2.0, 2.0, 1.0, 1.0, 0.5, 0.5]


def test_time_weight_custom_tiers():
    tiers = ((2, 3.0), (10**9, 1.0))
    assert S.time_weight([0, 1, 2, 5], tiers=tiers).tolist() == [3.0, 3.0, 1.0, 1.0]


# ── sizing_weights (compose the rules, pre capital-match) ────────────────────────

def test_risk_parity_is_inverse_risk_normalized_to_mean_one():
    w = S.sizing_weights(np.array([1.0, 2.0, 4.0]), risk_parity=True)
    # inverse of risk, then divided by its own mean -> mean 1.0, and monotically
    # decreasing in risk (higher risk -> smaller size)
    assert w.mean() == pytest.approx(1.0)
    assert w[0] > w[1] > w[2]


def test_risk_parity_cap_clamps_small_risk_spikes():
    # one tiny-risk trade would blow up 1/risk; rp_cap caps the final multiplier
    w = S.sizing_weights(np.array([0.01, 1.0, 1.0, 1.0]), risk_parity=True, rp_cap=2.0)
    assert w.max() <= 2.0 + 1e-12


def test_side_and_time_tilts_multiply_in():
    risk = np.array([1.0, 1.0])
    side = np.array([1.0, -1.0])   # long, short
    w = S.sizing_weights(risk, side=side, risk_parity=False, long_w=1.0, short_w=2.0)
    assert w.tolist() == [1.0, 2.0]


def test_no_rules_gives_unit_weights():
    w = S.sizing_weights(np.array([1.0, 3.0, 5.0]), risk_parity=False)
    assert w.tolist() == [1.0, 1.0, 1.0]


# ── sized_metrics (capital-match + net metrics) ─────────────────────────────────

def test_uniform_weights_reduce_to_size_one_baseline():
    """Capital-matching uniform weights to the size-1 risk budget must leave size == 1,
    so the metrics equal a plain 1-contract backtest."""
    pnl = np.array([2.0, -1.0, 3.0])
    risk = np.array([1.0, 1.0, 1.0])
    m = S.sized_metrics(pnl, risk, np.ones(3), mult=2.0, fee_pts=0.0)
    assert m["avg_size"] == pytest.approx(1.0)
    assert m["max_size"] == pytest.approx(1.0)
    assert m["net"] == pytest.approx((2.0 - 1.0 + 3.0) * 2.0)     # sum(pnl) * mult
    assert m["num_trades"] == 3
    assert m["win_rate"] == pytest.approx(100.0 * 2 / 3)


def test_capital_match_preserves_total_risk_budget():
    """Whatever the weights, the total dollar-risk deployed equals the size-1 budget
    (sum of per-trade risk). Recover per-trade size as weight * k and check the sum."""
    pnl = np.array([2.0, -1.0, 3.0, 0.5])
    risk = np.array([1.0, 2.0, 4.0, 0.5])
    weights = S.sizing_weights(risk, risk_parity=True)
    m = S.sized_metrics(pnl, risk, weights, mult=1.0, fee_pts=0.0)
    denom = float((weights * risk).sum())
    k = float(risk.sum()) / denom
    size = weights * k
    assert float((size * risk).sum()) == pytest.approx(float(risk.sum()))
    assert m["avg_size"] == pytest.approx(float(size.mean()))


def test_zero_risk_budget_returns_none():
    assert S.sized_metrics(np.array([1.0]), np.array([1.0]),
                           np.array([0.0]), mult=1.0, fee_pts=0.0) is None


def test_cap_final_clamps_contract_size():
    pnl = np.array([1.0, 1.0, 1.0, 1.0])
    risk = np.array([0.01, 1.0, 1.0, 1.0])   # tiny-risk trade -> big raw size
    weights = S.sizing_weights(risk, risk_parity=True, rp_cap=100.0)
    m = S.sized_metrics(pnl, risk, weights, mult=1.0, fee_pts=0.0, cap_final=1.5)
    assert m["max_size"] <= 1.5 + 1e-12


def test_fees_reduce_net():
    pnl = np.array([2.0, 2.0])
    risk = np.array([1.0, 1.0])
    gross = S.sized_metrics(pnl, risk, np.ones(2), mult=1.0, fee_pts=0.0)
    net = S.sized_metrics(pnl, risk, np.ones(2), mult=1.0, fee_pts=0.5)
    assert net["net"] < gross["net"]
    assert net["net"] == pytest.approx(gross["net"] - 2 * 0.5)


def test_mar_field_matches_mar_helper():
    pnl = np.array([3.0, -1.0, -1.0, 2.0])
    risk = np.ones(4)
    m = S.sized_metrics(pnl, risk, np.ones(4), mult=1.0, fee_pts=0.0)
    assert m["mar"] == S.mar(m["net"], m["max_drawdown"])
