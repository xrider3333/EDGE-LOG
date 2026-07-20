"""Unit tests for the #91 extrapolation guard — augur_engine.surrogate.extrapolation_check
and the QRF steering de-bias it feeds (propose_candidates_qrf).

Motivation (see surrogate.py's #91 section docstring): tree models (RF/XGB/QRF) can't
extrapolate honestly beyond sampled territory. After auto-expand widens a param's legal
range, a model's argmax pick over the (wider) candidate-grid bounds can land in thin or
entirely un-sampled territory and look like a real optimum when it's actually an
unconstrained-extrapolation artifact. `extrapolation_check` flags that; the QRF steering
brain additionally must not reward a candidate's (possibly inflated) predictive spread
with an exploration bonus when that candidate sits outside the sampled range.

All synthetic — deterministic points/grids, no real data files (mirrors
tests/test_surrogate.py's and tests/test_steering.py's own conventions).
"""
import numpy as np
import pytest

import augur_engine.surrogate as S
from augur_engine.auto import _auto_space_from_params
from augur_engine.surrogate import extrapolation_check, propose_candidates_qrf


def _dp_2num(step=0.5):
    return {
        "a": {"type": "float", "min": 0.0, "max": 10.0, "step": step, "default": 5.0},
        "b": {"type": "float", "min": 0.0, "max": 10.0, "step": step, "default": 5.0},
    }


# ─────────────────────────────────────────────────────────────────────────────
# (i) pick inside a dense synthetic grid -> flag None
# ─────────────────────────────────────────────────────────────────────────────
def test_pick_inside_dense_grid_is_not_flagged():
    dp = _dp_2num()
    pkeys = ["a", "b"]
    recs = [{"a": round(float(a), 1), "b": round(float(b), 1)}
            for a in np.arange(0.0, 10.5, 0.5) for b in np.arange(0.0, 10.5, 0.5)]
    pick = {"a": 5.0, "b": 5.0}

    out = extrapolation_check(pick, recs, pkeys, dp)
    assert out["outside"] == []
    assert out["thin"] is False
    assert out["flag"] is None
    assert out["neighbors"] >= 5   # a dense grid has plenty of records within the radius


# ─────────────────────────────────────────────────────────────────────────────
# (ii) pick beyond sampled max on one param -> that param in "outside", flag "extrapolated"
# ─────────────────────────────────────────────────────────────────────────────
def test_pick_beyond_sampled_max_is_flagged_extrapolated():
    dp = _dp_2num()
    pkeys = ["a", "b"]
    # sampled territory only covers a in [0, 8], b in [0, 10]
    recs = [{"a": round(float(a), 1), "b": round(float(b), 1)}
            for a in np.arange(0.0, 8.5, 0.5) for b in np.arange(0.0, 10.5, 0.5)]
    pick = {"a": 9.5, "b": 5.0}   # beyond the sampled max of "a" (8.0), "b" still in-range

    out = extrapolation_check(pick, recs, pkeys, dp)
    assert out["outside"] == ["a"]
    assert out["flag"] == "extrapolated"


def test_categorical_value_never_seen_is_flagged_extrapolated():
    dp = {"a": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.5, "default": 5.0},
          "mode": {"type": "str", "default": "x"}}
    pkeys = ["a", "mode"]
    recs = [{"a": round(float(a), 1), "mode": m}
            for a in np.arange(0.0, 10.5, 0.5) for m in ("x", "y")]
    pick = {"a": 5.0, "mode": "z"}   # "z" never appears in the sampled records

    out = extrapolation_check(pick, recs, pkeys, dp)
    assert out["outside"] == ["mode"]
    assert out["flag"] == "extrapolated"


# ─────────────────────────────────────────────────────────────────────────────
# (iii) in-range pick far from all samples -> thin True, flag "thin"
# ─────────────────────────────────────────────────────────────────────────────
def test_in_range_pick_far_from_all_samples_is_thin():
    dp = _dp_2num(step=0.1)
    pkeys = ["a", "b"]
    # samples only cluster at the two opposite corners -> sampled min/max span the
    # WHOLE [0,10] range on both axes (so the center is technically "in range"), but
    # nothing lives anywhere near the center.
    recs = ([{"a": 0.0, "b": 0.0} for _ in range(15)] +
            [{"a": 10.0, "b": 10.0} for _ in range(15)])
    pick = {"a": 5.0, "b": 5.0}

    out = extrapolation_check(pick, recs, pkeys, dp)
    assert out["outside"] == []             # in range on both axes
    assert out["neighbors"] == 0             # distance to each corner is 0.5 > radius 0.25
    assert out["thin"] is True
    assert out["flag"] == "thin"


# ─────────────────────────────────────────────────────────────────────────────
# (iv) propose_candidates_qrf: out-of-range candidates never get a sigma bonus
# ─────────────────────────────────────────────────────────────────────────────
def test_qrf_extrapolation_guard_ignores_sigma_bonus_outside_sampled_range(monkeypatch):
    """Monkeypatch the QRF model itself so its predicted quantiles are fully under
    our control: candidates OUTSIDE the sampled range [3, 7] get a rock-bottom median
    (-1000) but an ENORMOUS spread (so an un-guarded UCB score, mu + kappa*sigma,
    would be gigantic and dominate the ranking); in-range candidates get a flat
    median (0) and zero spread. Without the #91 guard, the top `n_propose` slots
    would all be out-of-range picks (score ~= kappa*1e6). With the guard, their
    sigma is zeroed before ranking, so their score collapses back to mu=-1000 --
    clearly worse than any in-range candidate's score of 0 -- and none should
    survive into the returned list."""
    class _FakeQRF:
        def __init__(self, **kw):
            pass

        def fit(self, X, y):
            return self

        def predict(self, X, quantiles=None):
            a = X[:, 0]
            outside = (a < 3.0) | (a > 7.0)
            mu = np.where(outside, -1000.0, 0.0)
            spread = np.where(outside, 1e6, 0.0)     # (q84-q16)/2 == spread
            return np.stack([mu - spread, mu, mu + spread], axis=1)

    monkeypatch.setattr(S, "HAS_QRF", True)
    monkeypatch.setattr(S, "_QRF", _FakeQRF)

    # step=0.25 so the pool can draw plenty of DISTINCT fractional in-range values
    # (3.25, 3.5, 3.75, 4.25, ...) that are NOT already in `records` (whole-number
    # 3..7) -- otherwise every in-range pool draw would collide with an already-
    # "seen" record and get filtered out, leaving too few distinct safe candidates
    # to fill n_propose=5 (a starved pool, not a guard failure, would then force in
    # a low-score leftover just to hit the quota -- a separate concern from what
    # this test checks).
    dp = {"a": {"type": "float", "min": 0.0, "max": 10.0, "step": 0.25, "default": 5.0}}
    pkeys = ["a"]
    space = _auto_space_from_params(dp)
    records = [{"a": float(3 + (i % 5)), "total_pnl": float(3 + (i % 5))} for i in range(50)]

    out = propose_candidates_qrf(records, pkeys, dp, space, n_propose=5, seed=1, pool_size=300)

    assert out, "expected at least one surviving candidate"
    for cand in out:
        assert 3.0 <= cand["a"] <= 7.0, (
            "an out-of-range candidate was ranked ahead of in-range ones -- "
            "the fake-sigma exploration bonus was not suppressed")


def test_qrf_absent_still_returns_empty_with_guard_code_present(monkeypatch):
    """Sanity check that the #91 guard addition didn't disturb the pre-existing
    HAS_QRF short-circuit (tests/test_steering.py's own test_qrf_absent_returns_empty)."""
    monkeypatch.setattr(S, "HAS_QRF", False)
    dp = _dp_2num()
    pkeys = ["a", "b"]
    space = _auto_space_from_params(dp)
    records = [{"a": float(i % 10), "b": float((i * 3) % 10), "total_pnl": float(i)}
               for i in range(50)]
    assert propose_candidates_qrf(records, pkeys, dp, space, 5, seed=1) == []
