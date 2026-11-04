import datetime as dt
import json

from tools import day_mode as D

CFG = dict(D.DEFAULTS)


def _t(h, m):
    return dt.datetime(2026, 11, 4, h, m, tzinfo=D.MST)


def test_slots():
    assert D.slot("") == 1 and D.slot("1") == 2 and D.slot("3") == 4


def test_day_holds_only_slots_above_two():
    assert not D.hold(_t(10, 0), "", CFG)
    assert not D.hold(_t(10, 0), "1", CFG)
    assert D.hold(_t(10, 0), "2", CFG)
    assert D.hold(_t(7, 0), "3", CFG)


def test_night_holds_nothing():
    assert not D.hold(_t(16, 0), "3", CFG)
    assert not D.hold(_t(6, 59), "3", CFG)


def test_disabled_and_file_reload(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    monkeypatch.setenv("EDGELOG_RUNNER_SCHEDULE", str(p))
    D._cache["mtime"] = None
    assert D.load()["day_runners"] == 2            # missing file = defaults
    p.write_text(json.dumps({"enabled": False}))
    assert not D.hold(_t(10, 0), "3")
    p.write_text("not json")
    import os, time
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert D.load()["enabled"] is True             # broken file = defaults
