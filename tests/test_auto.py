"""Unit tests for augur_engine.auto pure helpers — the auto-optimizer's search space,
seeded sampler, conditional-param collapse, and the realism gate.

These govern which configs the smart search even considers and which get to headline,
so their edges (int step coercion, seeded reproducibility, depends_on resets, the
gate thresholds) are worth pinning. No backtests run here.
"""
from augur_engine import auto as A


# ── _auto_space_from_params ─────────────────────────────────────────────────────

def test_space_maps_each_param_type():
    dp = {
        "a": {"type": "int", "min": 1, "max": 5, "step": 2},
        "b": {"type": "float", "min": 0.0, "max": 1.0, "step": 0.25},
        "c": {"type": "bool"},
        "d": {"type": "str", "options": ["x", "y"]},
        "e": {"type": "float", "min": 0, "max": 2},          # no step -> 0.0
        "skip": "not a dict",
    }
    space = A._auto_space_from_params(dp)
    assert space["a"] == ("int", 1, 5, 2)
    assert space["b"] == ("float", 0.0, 1.0, 0.25)
    assert space["c"] == ("cat", [True, False])
    assert space["d"] == ("cat", ["x", "y"])
    assert space["e"] == ("float", 0.0, 2.0, 0.0)
    assert "skip" not in space


def test_str_without_options_falls_back_to_default():
    space = A._auto_space_from_params({"m": {"type": "str", "default": "only"}})
    assert space["m"] == ("cat", ["only"])


# ── _RandomSampler ──────────────────────────────────────────────────────────────

SPACE = {"a": ("int", 1, 5, 2), "b": ("float", 0.0, 1.0, 0.25), "c": ("cat", [True, False])}


def test_sampler_is_seeded_reproducible():
    a = [A._RandomSampler(SPACE, seed=42).ask() for _ in range(1)]
    b = [A._RandomSampler(SPACE, seed=42).ask() for _ in range(1)]
    assert a == b


def test_sampler_respects_bounds_and_step():
    s = A._RandomSampler(SPACE, seed=1)
    for _ in range(300):
        p = s.ask()
        assert 1 <= p["a"] <= 5 and (p["a"] - 1) % 2 == 0     # on the int grid
        assert 0.0 <= p["b"] <= 1.0
        assert p["c"] in (True, False)


def test_sampler_float_without_step_stays_in_range():
    s = A._RandomSampler({"x": ("float", -2.0, 2.0, 0.0)}, seed=7)
    assert all(-2.0 <= s.ask()["x"] <= 2.0 for _ in range(100))


# ── _collapse ───────────────────────────────────────────────────────────────────

def test_collapse_resets_inactive_conditional_param():
    dp = {"mode": {"type": "str", "default": "off"},
          "lvl": {"type": "int", "default": 3, "depends_on": {"mode": "on"}}}
    assert A._collapse({"mode": "off", "lvl": 9}, dp) == {"mode": "off", "lvl": 3}


def test_collapse_keeps_active_conditional_param():
    dp = {"mode": {"type": "str", "default": "off"},
          "lvl": {"type": "int", "default": 3, "depends_on": {"mode": "on"}}}
    assert A._collapse({"mode": "on", "lvl": 9}, dp) == {"mode": "on", "lvl": 9}


# ── _is_real (realism gate) ─────────────────────────────────────────────────────

GOOD = {"wins": 5, "losses": 5, "num_trades": 10, "profit_factor": 2.0}


def test_is_real_accepts_a_healthy_config():
    assert A._is_real(GOOD, nbars=10_000) is True


def test_is_real_needs_enough_wins_and_losses():
    assert A._is_real({**GOOD, "wins": A.WF_MIN_SIDE - 1}, 10_000) is False
    assert A._is_real({**GOOD, "losses": A.WF_MIN_SIDE - 1}, 10_000) is False


def test_is_real_rejects_overtrading():
    # 10 trades over only 100 bars = 0.1 > MAX_TRADE_RATE
    assert A._is_real(GOOD, nbars=100) is False


def test_is_real_rejects_implausible_profit_factor():
    assert A._is_real({**GOOD, "profit_factor": A.MAX_PF + 0.1}, 10_000) is False
