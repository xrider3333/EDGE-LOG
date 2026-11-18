"""The PC-load chip's data source (api/pc_load.py, board item 12, 2026-11-18).

The chip exists so the owner can see at a glance that the box is buried - on 2026-11-14 six
ships plus a workflow ran the PC out of RAM and the whole fleet had to be killed by hand.

Two rules matter more than the numbers:
  * UNKNOWN IS NOT ZERO. A box without psutil, or a reading that threw, must come back
    ok=False and draw NOTHING. A zero would read as "idle", which is the opposite.
  * IT CAN NEVER TAKE DOWN THE RUNNER. check() and publish() swallow everything, including
    a Firestore write that fails.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import pc_load  # noqa: E402


class _Doc:
    def __init__(self, bag, name):
        self.bag, self.name = bag, name

    def set(self, body):
        self.bag.append((self.name, body))


class _Col:
    """users/{uid} -> .collection('meta') -> .document('pc_load'), the real chain."""

    def __init__(self, bag):
        self.bag = bag

    def document(self, n):
        return _Doc(self.bag, n)

    def collection(self, _n):
        return self


class _DocThenCol(_Doc):
    def collection(self, _n):
        return _Col(self.bag)


class _DB:
    def __init__(self):
        self.writes = []

    def collection(self, _n):
        class _Users:
            def __init__(s, bag):
                s.bag = bag

            def document(s, n):
                return _DocThenCol(s.bag, n)
        return _Users(self.writes)


def test_a_reading_carries_the_four_numbers_the_chip_draws():
    r = pc_load.check(sample_sec=0.05)
    if not r.get("ok"):
        pytest.skip("no psutil on this box - the unknown path is covered below")
    for k in ("cpu_pct", "mem_pct", "free_gb", "total_gb"):
        assert isinstance(r[k], float), k
    assert 0.0 <= r["cpu_pct"] <= 100.0
    assert 0.0 <= r["mem_pct"] <= 100.0
    assert r["free_gb"] <= r["total_gb"]
    assert r["checked_at"] and r["checked_at"][:2] == "20"


def test_the_runner_count_counts_runners_not_the_shells_that_launched_them(monkeypatch):
    """Each worker is started by `cmd /c "set EDGELOG_WORKER=N && ... -m api.runner ..."`, so
    the cmd.exe shell carries the same text - and so does anything inspecting it. Matching on
    the text alone counted 9 on a box running 5."""
    class P:
        def __init__(self, name, cmd):
            self.info = {"name": name, "cmdline": cmd}

    rows = [P("python.exe", ["python", "-u", "-m", "api.runner", "--firestore"]),
            P("python3.13.exe", ["python3.13", "-m", "api.runner"]),
            P("cmd.exe", ["cmd", "/c", "set EDGELOG_WORKER=5 && python -u -m api.runner"]),
            P("python.exe", ["python", "-c", "print('-m api.runner')"]),
            P("chrome.exe", ["chrome"])]
    monkeypatch.setattr(pc_load, "_ps", type("S", (), {"process_iter": staticmethod(lambda _f: rows)}))
    assert pc_load._runners() == 2


def test_a_box_without_psutil_says_unknown_never_zero(monkeypatch):
    monkeypatch.setattr(pc_load, "_ps", None)
    r = pc_load.check()
    assert r["ok"] is False
    assert "cpu_pct" not in r and "mem_pct" not in r, "an absent reading must not look like 0%"
    assert "psutil" in r["note"]


def test_a_sampling_error_is_reported_not_raised(monkeypatch):
    def _boom(**_k):
        raise OSError("no counters")
    monkeypatch.setattr(pc_load, "_ps", type("S", (), {"cpu_percent": staticmethod(_boom)}))
    r = pc_load.check()
    assert r["ok"] is False and "OSError" in r["note"]


def test_a_broken_process_row_does_not_lose_the_count(monkeypatch):
    class Bad:
        @property
        def info(self):
            raise RuntimeError("process died mid-walk")

    class Good:
        info = {"name": "python.exe", "cmdline": ["python", "-m", "api.runner"]}

    monkeypatch.setattr(pc_load, "_ps",
                        type("S", (), {"process_iter": staticmethod(lambda _f: [Bad(), Good()])}))
    assert pc_load._runners() == 1


def test_publish_writes_one_doc_at_the_path_the_app_listens_on(monkeypatch):
    monkeypatch.setattr(pc_load, "check", lambda **_k: {"ok": True, "cpu_pct": 1.0})
    db = _DB()
    out = pc_load.publish(db, "UID")
    assert len(db.writes) == 1, "one small doc per publish - this runs forever on a Spark plan"
    assert db.writes[0][0] == "pc_load"
    assert out == {"ok": True, "cpu_pct": 1.0}


def test_a_failed_write_is_swallowed_and_logged(monkeypatch):
    class _Dead(_DB):
        def collection(self, _n):
            raise RuntimeError("firestore unreachable")

    monkeypatch.setattr(pc_load, "check", lambda **_k: {"ok": True})
    logs = []
    assert pc_load.publish(_Dead(), "UID", log=logs.append) is None
    assert logs and "publish failed" in logs[0]


def test_the_runner_publishes_on_a_throttle_and_only_as_the_primary():
    """A worker publishing would overwrite the same box's numbers for no gain, and a publish
    every tick would be thousands of writes a day."""
    import io
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "api", "runner.py"), encoding="utf-8").read()
    i = src.index("from api import pc_load as _pcl")
    guard = src[src.rindex("if ", 0, i):i]
    assert "not _IS_WORKER" in guard, "primary only"
    assert "next_pc_load" in guard, "throttled"
    assert "_PC_LOAD_SEC = 60.0" in src
