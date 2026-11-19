"""The PC-load publish throttle (MANAGER 2026-11-19, after the 11-18 quota night).

A write a minute is 1,440 writes a day and, worse, one READ for every open tab holding the
listener. The chip is a glance, not a monitor, so a reading that has not moved is skipped.

The rule the tests hold to: SKIPPING IS ONLY EVER ALLOWED WHEN WE KNOW NOTHING CHANGED. A
first reading, a reading that failed, a state flip and a missing number all publish.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import pc_load  # noqa: E402


def R(cpu=50.0, mem=50.0, runners=5, at=0.0, ok=True):
    return {"ok": ok, "cpu_pct": cpu, "mem_pct": mem, "runners": runners, "_at": at}


def test_a_first_reading_always_publishes():
    assert pc_load.moved(R(), None) is True
    assert pc_load.moved(R(), {}) is True


def test_a_reading_that_has_not_moved_is_skipped():
    assert pc_load.moved(R(at=60.0), R(at=0.0)) is False


def test_a_real_move_publishes_immediately():
    assert pc_load.moved(R(cpu=56.0, at=60.0), R(cpu=50.0, at=0.0)) is True
    assert pc_load.moved(R(mem=44.0, at=60.0), R(mem=50.0, at=0.0)) is True


def test_a_move_smaller_than_the_bar_is_noise_and_waits():
    assert pc_load.moved(R(cpu=53.0, mem=52.0, at=60.0), R(cpu=50.0, mem=50.0, at=0.0)) is False


def test_a_runner_appearing_or_dying_always_publishes():
    """The runner count is the one number the owner acts on - never let it sit stale."""
    assert pc_load.moved(R(runners=4, at=10.0), R(runners=5, at=0.0)) is True
    assert pc_load.moved(R(runners=None, at=10.0), R(runners=5, at=0.0)) is True


def test_an_unchanged_box_still_publishes_on_the_idle_timer():
    assert pc_load.moved(R(at=pc_load.IDLE_PUBLISH_SEC), R(at=0.0)) is True


def test_a_state_flip_publishes_even_with_identical_numbers():
    assert pc_load.moved(R(at=10.0), dict(R(at=0.0), ok=False)) is True
    assert pc_load.moved(dict(R(at=10.0), ok=False), R(at=0.0)) is True


def test_two_failed_readings_in_a_row_still_respect_the_idle_timer():
    bad = {"ok": False, "note": "psutil not installed on this box", "_at": 0.0}
    assert pc_load.moved(dict(bad, _at=60.0), bad) is False
    assert pc_load.moved(dict(bad, _at=pc_load.IDLE_PUBLISH_SEC), bad) is True


def test_a_missing_number_publishes_rather_than_guessing():
    last = R(at=0.0)
    assert pc_load.moved({"ok": True, "mem_pct": 50.0, "runners": 5, "_at": 60.0}, last) is True


def test_a_skipped_publish_writes_nothing_and_returns_none(monkeypatch):
    class _DB:
        def __init__(self):
            self.n = 0

        def collection(self, _n):
            self.n += 1
            raise AssertionError("a skipped publish must not touch Firestore")

    monkeypatch.setattr(pc_load, "check", lambda **_k: R(at=0.0))
    monkeypatch.setattr(pc_load.time, "time", lambda: 60.0)
    db = _DB()
    assert pc_load.publish(db, "UID", last=R(at=0.0)) is None
    assert db.n == 0


def test_the_written_document_carries_no_bookkeeping_field(monkeypatch):
    bag = []

    class _Doc:
        def set(self, body):
            bag.append(body)

    class _Chain:
        def collection(self, _n):
            return self

        def document(self, _n):
            return self if not bag else self

        def set(self, body):
            bag.append(body)

    class _DB:
        def collection(self, _n):
            return _C()

    class _C:
        def document(self, _n):
            return _D()

    class _D:
        def collection(self, _n):
            return _C2()

    class _C2:
        def document(self, _n):
            return _Doc()

    monkeypatch.setattr(pc_load, "check", lambda **_k: {"ok": True, "cpu_pct": 1.0})
    out = pc_load.publish(_DB(), "UID")
    assert bag and "_at" not in bag[0], "the page never sees the throttle's own clock"
    assert "_at" in out, "the caller keeps it, to compare against next time"


def test_the_runner_keeps_the_last_PUBLISHED_report_not_the_last_reading():
    """A slow drift must still publish: comparing against the last READING would let the box
    creep from 40 to 90 per cent four points at a time and never write."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "api", "runner.py"), encoding="utf-8").read()
    i = src.index("_pcl.publish(")
    seg = src[i:i + 400]
    assert "last=pc_load_last.get(" in seg
    assert "if _done:" in seg and "pc_load_last[_u] = _done" in seg
