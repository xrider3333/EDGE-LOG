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


# ── the hold says so in the log (MANAGER 11-16) ────────────────────────────────────────────
def test_runner_says_why_it_is_not_claiming(monkeypatch):
    """A day-mode hold used to be silent, so a worker box looked idle for no stated reason.
    One line, then nothing for 10 minutes however many jobs are queued."""
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_quiet import _runner, _queue, _Snap
    R = _runner()
    monkeypatch.setattr(R, "_psutil", None)
    monkeypatch.setattr(D, "hold", lambda *a, **k: True)
    monkeypatch.setattr(D, "slot", lambda *a, **k: 7)
    snaps = [_Snap({"status": "queued", "type": "backtest"}),
             _Snap({"status": "queued", "type": "backtest"})]
    q = _queue(R, snaps, None)
    logs = []
    assert q.run_once(log=logs.append) == 0
    assert [s for s in logs if s.startswith("[day]")], "the hold must say so once"
    assert sum(s.startswith("[day]") for s in logs) == 1, "not once per queued job"
    assert all(s.reference.updates == [] for s in snaps), "jobs stay queued, untouched"
    logs2 = []
    assert q.run_once(log=logs2.append) == 0
    assert not [s for s in logs2 if s.startswith("[day]")], "throttled for 10 minutes"
