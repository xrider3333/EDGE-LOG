"""Unit tests for api.util.json_safe — the inf/nan/numpy sanitizer.

Every API/runner response passes through this before hitting JSON/Firestore, and the
engine legitimately emits inf (profit_factor with no losses) and numpy scalars, so a
regression here corrupts or crashes the whole API surface. Cheap, high-leverage.
"""
import math

import numpy as np

from api.util import json_safe


def test_inf_and_nan_become_none():
    assert json_safe(float("inf")) is None
    assert json_safe(float("-inf")) is None
    assert json_safe(float("nan")) is None


def test_finite_floats_pass_through():
    assert json_safe(1.5) == 1.5
    assert json_safe(0.0) == 0.0


def test_numpy_scalars_become_python():
    out_i = json_safe(np.int64(3))
    out_f = json_safe(np.float64(1.5))
    assert out_i == 3 and isinstance(out_i, int)
    assert out_f == 1.5 and isinstance(out_f, float)


def test_numpy_non_finite_also_none():
    assert json_safe(np.float32("inf")) is None
    assert json_safe(np.float64("nan")) is None


def test_recurses_through_containers():
    got = json_safe({"a": float("inf"), "b": [np.float32(2.0), float("-inf")],
                     "c": (np.int64(1), 2)})
    assert got == {"a": None, "b": [2.0, None], "c": [1, 2]}


def test_non_numeric_passthrough():
    assert json_safe("hi") == "hi"
    assert json_safe(None) is None
    assert json_safe(True) is True
