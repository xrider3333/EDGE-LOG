import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from augur_engine.auto import lint_hard_bounds, unbounded_widened  # noqa: E402

DP = {
    "streak_n": {"min": 2, "max": 5, "type": "int", "hard_min": 2},
    "gap_atr": {"min": 0.25, "max": 1.0, "type": "float"},
    "mode": {"default": "a", "type": "choice"},
}


def test_lint_lists_only_unfenced_numeric():
    assert lint_hard_bounds(DP) == ["gap_atr"]
    assert lint_hard_bounds(None) == []


def test_unbounded_widened_names_unfenced_side_only():
    log = [{"param": "gap_atr", "orig_range": [0.25, 1.0], "final_range": [0.0, 1.0]},
           {"param": "streak_n", "orig_range": [2, 5], "final_range": [2, 7]},
           {"param": "bad"}]
    out = unbounded_widened(log, DP)
    assert out == [{"param": "gap_atr", "side": "min", "declared": 0.25, "reached": 0.0},
                   {"param": "streak_n", "side": "max", "declared": 5, "reached": 7}]


def test_unbounded_widened_quiet_when_fenced():
    dp = {"x": {"hard_min": 0, "hard_max": 9}}
    assert unbounded_widened([{"param": "x", "orig_range": [1, 2], "final_range": [0, 9]}], dp) == []
