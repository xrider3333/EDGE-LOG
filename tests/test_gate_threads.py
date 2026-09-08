"""
Every gate-zoo member fits on ONE thread (2026-09-08).

WHY: the gate refits every 25 trades as it walks a trade list, thousands of fits per
validate on a few hundred rows each. n_jobs=-1 made each fit start and tear down a joblib
pool (forests) or twenty OpenMP threads (XGBoost): two thirds of a validate's wall-clock
was worker start-up, and five runners sharing the box made it worse. This pins the rule
so a future "make it faster with n_jobs=-1" edit trips here first.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from augur_engine.ml_gate import _make_model, _GATE_N_JOBS


def test_gate_n_jobs_is_one():
    assert _GATE_N_JOBS == 1


@pytest.mark.parametrize("name", ["rf", "et", "xgb"])
def test_zoo_members_fit_single_threaded(name):
    clf = _make_model(name, seed=42).named_steps["clf"]
    n = getattr(clf, "n_jobs", None)
    # sklearn HistGradientBoosting (the xgboost fallback) has no n_jobs at all: fine
    assert n in (None, 1), f"{name}: n_jobs={n!r}, expected 1"


def test_keel_forest_is_single_threaded():
    import inspect
    from augur_engine import ml_keel
    body = inspect.getsource(ml_keel)
    i = body.index("ExtraTreesRegressor(")
    assert "n_jobs=1" in body[i:i + 220], "KEEL ExtraTrees must fit on one thread"
