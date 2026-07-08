"""Unit tests for augur_engine.analytics — the streamlit-free research stats.

Every function here is pure and (where randomness is involved) seeded, so it is
snapshot-testable. These tests pin the small-sample None guards, the seeded
reproducibility, one golden value per function, and — importantly — two degenerate
inputs that currently misbehave rather than guard:

  * annualized_sr(years=0) raises ZeroDivisionError (no guard).
  * deflated_sharpe(n_cfg=1) returns luck_bar = -inf and "beats the luck bar",
    i.e. a one-config search reports a confident pass from a meaningless luck bar.

Both are pinned here so the behavior is visible and can't silently change; see the
notes on those tests before "fixing" either — a guard is a deliberate stats change.
"""
import numpy as np
import pytest

from augur_engine import analytics as A


# ── downsample_pnls ─────────────────────────────────────────────────────────────

def test_downsample_pnls_sorts_desc_and_rounds():
    assert A.downsample_pnls([3, 1, 2, 5, 4]) == [5.0, 4.0, 3.0, 2.0, 1.0]
    assert A.downsample_pnls([1.234, 2.567]) == [2.6, 1.2]


def test_downsample_pnls_caps_length():
    out = A.downsample_pnls(list(range(1000)), cap=50)
    assert len(out) == 50
    assert out == sorted(out, reverse=True)


def test_downsample_pnls_handles_none_as_zero():
    assert A.downsample_pnls([None, 1.0, None]) == [1.0, 0.0, 0.0]


# ── annualized_sr ───────────────────────────────────────────────────────────────

def test_annualized_sr_needs_three_trades():
    assert A.annualized_sr([1.0, 2.0], 1.0) is None


def test_annualized_sr_zero_variance_returns_none():
    assert A.annualized_sr([5.0, 5.0, 5.0, 5.0], 1.0) is None


def test_annualized_sr_uses_sample_std_ddof1():
    pnls = [1.0, -0.5, 2.0, -1.0, 0.5, 1.5]
    p = np.asarray(pnls)
    expected = (p.mean() / p.std(ddof=1)) * np.sqrt(len(p) / 1.0)
    r = A.annualized_sr(pnls, 1.0)
    assert set(r) == {"sr", "n", "tpy", "skew", "kurt"}
    assert r["sr"] == pytest.approx(expected)
    assert r["n"] == len(pnls)


def test_annualized_sr_years_zero_raises_unguarded():
    """KNOWN LANDMINE (pinned, not endorsed): years=0 divides by zero. Direct callers
    that don't clamp `years` (the engine passes max(0.1, ...)) will crash. If you add a
    guard that returns None, update this test."""
    with pytest.raises(ZeroDivisionError):
        A.annualized_sr([1.0, 2.0, -1.0, 3.0], 0.0)


# ── monte_carlo_drawdown ────────────────────────────────────────────────────────

def test_monte_carlo_needs_two_points():
    assert A.monte_carlo_drawdown([1.0]) is None


def test_monte_carlo_is_seeded_reproducible():
    pnls = [1.0, -2.0, 3.0, -1.0, 0.5, -0.5]
    a = A.monte_carlo_drawdown(pnls, n_sims=200, seed=42)
    b = A.monte_carlo_drawdown(pnls, n_sims=200, seed=42)
    assert a == b


def test_monte_carlo_as_traded_is_deterministic_max_dd():
    # as_traded is the observed (unshuffled) max drawdown, independent of the sims
    pnls = [1.0, -2.0, 3.0, -1.0, 0.5]
    r = A.monte_carlo_drawdown(pnls, n_sims=100, seed=42)
    assert r["as_traded"] == -2.0            # cum: 1,-1,2,1,1.5 -> min(cum-peak) = -2


def test_monte_carlo_percentiles_ordered_by_severity():
    pnls = [2.0, -3.0, 1.0, -4.0, 5.0, -2.0, 1.5, -1.0]
    r = A.monte_carlo_drawdown(pnls, n_sims=500, seed=42)
    # drawdowns are negative; deeper percentiles must be <= shallower ones
    assert r["p99"] <= r["p95"] <= r["p90"] <= r["p75"] <= r["p50"]


# ── deflated_sharpe ─────────────────────────────────────────────────────────────

def _winner():
    return A.annualized_sr([1.0, -0.5, 2.0, -1.0, 0.5, 1.5, 0.3, -0.2, 1.1, -0.7], 1.0)


def test_deflated_sharpe_needs_eight_samples():
    assert A.deflated_sharpe(_winner(), [0.1] * 5, 50, 1.0) is None


def test_deflated_sharpe_normal_case():
    srs = [0.1, 0.2, -0.1, 0.15, 0.05, -0.05, 0.12, 0.3, 0.0, 0.22]
    ds = A.deflated_sharpe(_winner(), srs, 50, 1.0)
    assert set(ds) == {"winner_sharpe", "luck_bar", "dsr", "n_cfg", "verdict"}
    assert 0.0 <= ds["dsr"] <= 1.0
    assert ds["luck_bar"] > ds["winner_sharpe"] or ds["dsr"] < 1.0   # luck bar is meaningful


def test_deflated_sharpe_single_config_luck_bar_degenerates():
    """KNOWN LANDMINE (pinned, not endorsed): with n_cfg=1 the luck bar is
    norm.ppf(0) = -inf, so ANY strategy "beats" it and dsr collapses to 1.0. A
    one-config search can't be deflated — callers should require n_cfg >= 2. Pinned
    so the misleading pass stays visible."""
    srs = [0.1, 0.2, -0.1, 0.15, 0.05, -0.05, 0.12, 0.3, 0.0, 0.22]
    ds = A.deflated_sharpe(_winner(), srs, 1, 1.0)
    assert ds["luck_bar"] == float("-inf")
    assert ds["dsr"] == 1.0
    assert ds["verdict"] == "beats the luck bar"


# ── mae_mfe ─────────────────────────────────────────────────────────────────────

def test_mae_mfe_none_on_legacy_three_tuples():
    assert A.mae_mfe([(0, 1, 2.0)], np.array([1.0, 2.0]), np.array([0.0, 1.0])) is None


def test_mae_mfe_long_and_short_excursions():
    highs = np.array([10.0, 12.0, 11.0])
    lows = np.array([8.0, 9.0, 7.0])
    # long, entry_px 9: adverse = low-entry = 7-9 = -2; favourable = high-entry = 12-9 = 3
    lng = A.mae_mfe([(0, 2, 1.0, 1, 9.0)], highs, lows)
    assert lng == {"mae": [-2.0], "mfe": [3.0], "won": [1]}
    # short, entry_px 9: adverse = entry-high = 9-12 = -3; favourable = entry-low = 9-7 = 2
    sht = A.mae_mfe([(0, 2, -1.0, -1, 9.0)], highs, lows)
    assert sht == {"mae": [-3.0], "mfe": [2.0], "won": [0]}
