"""RESUME across shutdowns (owner 10-31, augur_engine/resume_ckpt): a run_auto call that finished
returns its saved result, and a walk-forward call killed mid-Stage-B re-runs only the folds that
had not finished - with rows identical to an uninterrupted run."""
import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine import auto as _auto
from augur_engine import resume_ckpt as RC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_wf_parallel import STRAT, _arrays, _strip

KEY = "ab" * 20


@pytest.fixture
def strat_path(tmp_path):
    p = tmp_path / "RESUMETEST_1_0.py"
    p.write_text(STRAT, encoding="utf-8")
    return str(p)


@pytest.fixture
def ckpt(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_RESUME_DIR", str(tmp_path / "ckpt"))
    monkeypatch.setattr(RC, "call_key", lambda strategy, kw: KEY)
    return tmp_path / "ckpt"


def _common():
    return dict(arrays=_arrays(), method="walkforward", wf_folds=4, n_trials=20, seed=11,
                min_trades=5, cost_pts=0.1, oos=True, auto_expand=False, workers=1)


def _count_folds(monkeypatch):
    calls = []
    real = _auto._wf_fold_row

    def counting(*a, **k):
        calls.append(a[10])
        return real(*a, **k)
    monkeypatch.setattr(_auto, "_wf_fold_row", counting)
    return calls


def test_finished_call_returns_the_saved_result(strat_path, ckpt, monkeypatch):
    first = _auto.run_auto(strat_path, **_common())
    assert first["top"]
    monkeypatch.setattr(_auto, "_run_auto_search",
                        lambda *a, **k: pytest.fail("a finished call must not re-run"))
    ticks = []
    again = _auto.run_auto(strat_path, progress_cb=lambda d, t: ticks.append((d, t)),
                           **_common())
    assert _strip(again["top"]) == _strip(first["top"])
    assert ticks == [(100, 100)]


def test_killed_walkforward_reruns_only_unfinished_folds(strat_path, ckpt, monkeypatch):
    whole = _auto.run_auto(strat_path, **_common())
    # simulate a sign-out after folds 0 and 1: no whole result, folds 2 and 3 never saved
    for p in glob.glob(str(ckpt / "**" / "*.pkl"), recursive=True):
        if p.endswith("_result.pkl") or p.endswith("_fold2.pkl") or p.endswith("_fold3.pkl"):
            os.remove(p)
    calls = _count_folds(monkeypatch)
    resumed = _auto.run_auto(strat_path, **_common())
    assert sorted(calls) == [2, 3]
    assert _strip(resumed["top"]) == _strip(whole["top"])
    assert resumed["best_params"] == whole["best_params"]


def test_parallel_path_saves_each_fold(strat_path, ckpt, monkeypatch):
    kw = dict(_common(), workers=2)
    whole = _auto.run_auto(strat_path, **kw)
    folds = glob.glob(str(ckpt / "**" / "*_fold*.pkl"), recursive=True)
    assert len(folds) == 4
    os.remove(glob.glob(str(ckpt / "**" / "*_result.pkl"), recursive=True)[0])
    calls = _count_folds(monkeypatch)
    resumed = _auto.run_auto(strat_path, **dict(_common()))
    assert calls == []                      # every fold came back from disk
    assert _strip(resumed["top"]) == _strip(whole["top"])


def test_no_key_without_a_master_file_or_when_off(strat_path, monkeypatch):
    assert RC.call_key(strat_path, {"arrays": {"close": []}}) is None
    monkeypatch.setenv("AUGUR_RESUME", "0")
    assert RC.call_key(strat_path, {"instrument": "NQ"}) is None


def test_key_ignores_progress_and_workers_but_not_trials(strat_path, tmp_path, monkeypatch):
    monkeypatch.setenv("AUGUR_RESUME", "1")
    from augur_engine import data as D
    up = tmp_path / "up"
    up.mkdir()
    (up / "m.csv").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(D, "UPLOADS", str(up))
    m = {"filename": "m.csv"}
    k1 = RC.call_key(strat_path, {"master": m, "n_trials": 900, "workers": 1,
                                  "progress_cb": print})
    k2 = RC.call_key(strat_path, {"master": m, "n_trials": 900, "workers": 4})
    k3 = RC.call_key(strat_path, {"master": m, "n_trials": 901, "workers": 4})
    assert k1 and k1 == k2 and k3 != k1
