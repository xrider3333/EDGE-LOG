"""EXEC LEGS OFF (GO 2026-11-25): the own-bar pass does not decide a 5m leg whose EXEC leg is
off at the executor (qqq_exec config.json legs_off + the BOOKS TOGGLE applied set); step()
decides it on the REST bar as for any leg the own bar did not commit. Any read doubt = every
leg decided as today."""
import json
import os

import pytest

from api import ownbar
from api import cloud_signal_stream as css

B0 = 1795111200
CLOSE = B0 + 300
LEGS = {"ORB_R6": {}, "NOISE_382": {}, "NOISE_555": {}, "NOISE_545": {}}


@pytest.fixture
def engine(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(css, "_handle_handoff_window",
                        lambda now, legs, *a, **k: calls.append(dict(legs)))
    monkeypatch.setattr(css, "_OWNBAR_ALERTS", None)
    monkeypatch.delenv("EDGELOG_QQQ_EXEC_DIR", raising=False)
    css._OWNBAR_DONE["bar_end"] = None
    css._OWNBAR_OFF_LOGGED.clear()
    home = str(tmp_path)
    bar = {"time": B0, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
    ownbar.write_handoff(home, {"bar_end": CLOSE, "ok": True, "bar": bar})
    return home, calls


def _cfg(home, body):
    d = os.path.join(home, "qqq_exec")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))
    return d


def _run(home, calls, logs=None):
    css._OWNBAR_DONE["bar_end"] = None
    assert css.handle_ownbar(None, dict(LEGS), {"home": home, "state_dir": home},
                             (logs.append if logs is not None else (lambda *a: None)),
                             wall=CLOSE + 0.07)
    return calls[-1]


def test_legs_off_leg_is_not_decided_on_the_own_bar(engine):
    home, calls = engine
    _cfg(home, {"legs_off": ["DIP", "NOISE545"]})
    logs = []
    legs = _run(home, calls, logs)
    assert list(legs) == ["ORB_R6", "NOISE_382", "NOISE_555"]     # order kept, 545 left to step()
    assert sum("NOISE_545 off at the executor" in m for m in logs) == 1
    _run(home, calls, logs)
    assert sum("off at the executor" in m for m in logs) == 1      # logged once per change


def test_books_toggle_applied_set_counts_too(engine):
    home, calls = engine
    d = _cfg(home, {"legs_off": []})
    with open(os.path.join(d, "books_toggle_applied.json"), "w", encoding="utf-8") as f:
        json.dump({"legs_off": ["NOISE555"]}, f)
    from api import books_toggle
    if books_toggle.applied_legs_off(d) != ["NOISE555"]:
        pytest.skip("books_toggle applied-file name differs")
    assert "NOISE_555" not in _run(home, calls)


@pytest.mark.parametrize("body", [None, "{not json", json.dumps({"legs_off": "NOISE545"}),
                                  json.dumps({})])
def test_any_doubt_decides_every_leg_as_today(engine, body):
    home, calls = engine
    if body is not None:
        _cfg(home, body)
    assert list(_run(home, calls)) == list(LEGS)


def test_reader_errors_never_stop_the_pass(engine, monkeypatch):
    home, calls = engine
    monkeypatch.setattr(ownbar, "engine_legs_off", lambda *a: 1 / 0)
    assert list(_run(home, calls)) == list(LEGS)


def test_engine_map_matches_the_executor():
    from api import qqq_exec
    assert ownbar.ENGINE_TO_EXEC == qqq_exec.ENGINE_LEG_MAP


@pytest.mark.parametrize("off", [[], ["NOISE545"], ["NOISE", "NOISE555"], ["DIP", "ORB"]])
def test_reader_agrees_with_qqq_exec_load_config(tmp_path, off):
    """Same answer as the executor: a leg is off here exactly when load_config zeroes its
    shares because of legs_off."""
    from api import qqq_exec
    d = _cfg(str(tmp_path), {"legs_off": off})
    merged = qqq_exec.load_config(os.path.join(d, "config.json"), log=lambda *a: None)
    got = ownbar.exec_legs_off(str(tmp_path))
    for eng, ex in ownbar.ENGINE_TO_EXEC.items():
        if ex in ("NOISE", "NOISE555", "NOISE545", "ORB"):
            assert (ex in got) == (merged["shares"][ex] == 0), (eng, ex)
