"""Unit tests for #94 — statistical power for the lockbox verdict
(augur_engine.analytics.power_stats).

A lockbox can PASS (PnL>0, PF>=1) while still being underpowered: too few trades to
reliably distinguish a real (small) edge from noise. `power_stats` reports the minimum
detectable edge (MDE) at 80% power / one-sided 5% significance, and — given a claimed
per-trade edge (e.g. the same champion's mean per-trade PnL over the optimize window) —
the achieved power to detect that specific claim at this lockbox's sample size.

Pure stdlib math (no scipy) by design — these tests hand-verify the same formulas
independently (plain math.sqrt/math.erf) rather than re-deriving them from scipy.
"""
import math

import pytest

from augur_engine.analytics import power_stats

Z_ALPHA = 1.6449
Z_POWER = 0.8416


def _hand_stats(pnls):
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    sd = math.sqrt(var)
    se = sd / math.sqrt(n)
    return sd, se


# ─────────────────────────────────────────────────────────────────────────────
# (i) hand-computed MDE check for a fixed pnl list
# ─────────────────────────────────────────────────────────────────────────────
def test_mde_hand_computed_for_fixed_pnl_list():
    pnls = [10.0, -5.0, 20.0, 0.0, 15.0, -10.0, 5.0, 8.0, -3.0, 12.0]
    sd, se = _hand_stats(pnls)
    expected_mde = (Z_ALPHA + Z_POWER) * se

    out = power_stats(pnls)

    assert "error" not in out
    assert out["n"] == len(pnls)
    assert out["sd"] == pytest.approx(sd, abs=1e-3)
    assert out["se"] == pytest.approx(se, abs=1e-3)
    assert out["mde_per_trade"] == pytest.approx(expected_mde, abs=1e-3)
    assert out["claimed_per_trade"] is None
    assert out["achieved_power"] is None
    assert out["powered"] is None
    assert out["alpha"] == 0.05
    assert out["target_power"] == 0.80


# ─────────────────────────────────────────────────────────────────────────────
# (ii) claimed edge far above the MDE -> powered True, achieved_power > 0.95
# ─────────────────────────────────────────────────────────────────────────────
def test_claimed_far_above_mde_is_powered_with_high_achieved_power():
    pnls = [10.0, -5.0, 20.0, 0.0, 15.0, -10.0, 5.0, 8.0, -3.0, 12.0, 6.0, -2.0]
    _, se = _hand_stats(pnls)
    claimed = se * 20.0   # comfortably above the MDE (~2.5x se) -> huge achieved power

    out = power_stats(pnls, claimed_per_trade=claimed)

    assert out["claimed_per_trade"] == claimed
    assert out["achieved_power"] is not None
    assert out["achieved_power"] > 0.95
    assert out["powered"] is True


# ─────────────────────────────────────────────────────────────────────────────
# (iii) claimed edge of 0 -> powered False, achieved_power small
# ─────────────────────────────────────────────────────────────────────────────
def test_claimed_zero_is_not_powered_with_small_achieved_power():
    pnls = [10.0, -5.0, 20.0, 0.0, 15.0, -10.0, 5.0, 8.0, -3.0, 12.0]

    out = power_stats(pnls, claimed_per_trade=0.0)

    assert out["claimed_per_trade"] == 0.0
    assert out["achieved_power"] is not None
    # Phi(-z_alpha) == alpha == 0.05 at claimed==0 (z == 0/se - z_alpha == -z_alpha)
    assert out["achieved_power"] == pytest.approx(0.05, abs=0.01)
    assert out["achieved_power"] < 0.10
    assert out["powered"] is False


# ─────────────────────────────────────────────────────────────────────────────
# (iv) n=2 -> error path
# ─────────────────────────────────────────────────────────────────────────────
def test_n_equals_two_returns_insufficient_trades_error():
    out = power_stats([5.0, 10.0])
    assert out == {"error": "insufficient lockbox trades", "n": 2}


def test_zero_variance_pnls_also_returns_insufficient_trades_error():
    out = power_stats([7.0, 7.0, 7.0, 7.0])   # n>=3 but sd==0
    assert out == {"error": "insufficient lockbox trades", "n": 4}


def test_empty_pnls_returns_error():
    out = power_stats([])
    assert out == {"error": "insufficient lockbox trades", "n": 0}
