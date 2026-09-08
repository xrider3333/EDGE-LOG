"""
Firestore read-quota guards in api/runner.py (2026-09-07).

WHY: five runner processes (primary + 4 drain-only _run_worker.vbs workers) each
polled Firestore independently with no read accounting and no backoff on 429
(ResourceExhausted), and blew the whole Spark-plan 50,000-reads/day quota in under
two hours, twice. These pin the pure pieces of the fix: the read counter, the 429
backoff, the 429 detector, and CommandThread's primary-vs-worker poll cadence.
None of this needs a real Firestore client — see test_runner_sweep.py for the
fake-Firestore tests that exercise the claim/sweep paths this fix also touches.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.runner as R


# ── _is_quota_exhausted ──────────────────────────────────────────────────────────

def test_recognizes_resource_exhausted_by_class_name():
    class ResourceExhausted(Exception):
        pass
    assert R._is_quota_exhausted(ResourceExhausted("quota")) is True


def test_recognizes_429_in_message_text():
    assert R._is_quota_exhausted(Exception("429 Quota exceeded")) is True


def test_ordinary_errors_are_not_quota_exhaustion():
    assert R._is_quota_exhausted(ValueError("bad param")) is False
    assert R._is_quota_exhausted(ConnectionError("timed out")) is False


# ── _Backoff ─────────────────────────────────────────────────────────────────────

def test_backoff_steps_up_then_caps():
    b = R._Backoff()
    assert b.hit() == 30.0
    assert b.hit() == 60.0
    assert b.hit() == 120.0
    assert b.hit() == 120.0        # capped, does not keep growing


def test_backoff_resets_on_ok():
    b = R._Backoff()
    b.hit(); b.hit()
    b.ok()
    assert b.hit() == 30.0          # back to the first step


# ── _ReadMeter / _note_reads ──────────────────────────────────────────────────────

def test_read_meter_accumulates_by_bucket_and_drains_on_summary():
    m = R._ReadMeter()
    m.add("poll", 10)
    m.add("poll", 5)
    m.add("claim", 3)
    m.add("other", 0)               # zero reads never shows up
    snap = m.summary()
    assert snap == {"poll": 15, "claim": 3}
    assert m.summary() == {}, "summary() must drain the counters, not just read them"


def test_note_reads_never_raises_on_bad_input():
    R._note_reads("poll", None)     # falsy count -> no-op, no exception
    R._note_reads("poll", "not-a-number")   # int(...) fails -> swallowed


# ── CommandThread cadence: primary vs drain-only worker ───────────────────────────
# (2026-09-07 fix) A worker exists to run backtest jobs, not answer chart lookups;
# unlike the job queue, CommandThread has no on_snapshot listener and used to poll
# on the SAME fixed cadence on every one of the 5 processes. This is the "primary
# stays fast, workers slow way down" half of the fix.

def test_command_thread_uses_primary_cadence_by_default(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", False)
    ct = R.CommandThread(db=None, allow_uids=(), root=".", log=lambda *_: None)
    assert ct._poll_sec == R.CommandThread.POLL_SEC == 5.0
    assert ct._busy_poll_sec == R.CommandThread.BUSY_POLL_SEC == 0.75


def test_command_thread_uses_slower_cadence_on_a_worker(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", True)
    ct = R.CommandThread(db=None, allow_uids=(), root=".", log=lambda *_: None)
    assert ct._poll_sec == R.CommandThread.WORKER_POLL_SEC == 30.0
    assert ct._busy_poll_sec == R.CommandThread.WORKER_BUSY_POLL_SEC == 5.0
    # and the worker cadence really is slower than the primary's, not just different
    assert ct._poll_sec > R.CommandThread.POLL_SEC
    assert ct._busy_poll_sec > R.CommandThread.BUSY_POLL_SEC


def test_command_thread_poll_once_backs_off_on_quota_exhaustion(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", False)
    ct = R.CommandThread(db=None, allow_uids=("u1", "u2"), root=".", log=lambda *_: None)

    class _Boom(Exception):
        pass

    def _fake_poll_uid(uid):
        raise _Boom("429 ResourceExhausted")

    monkeypatch.setattr(R, "_is_quota_exhausted", lambda e: True)
    ct._poll_uid = _fake_poll_uid
    n = ct.poll_once()
    assert n == 0
    assert ct._quota_backoff == 30.0, "first 429 should arm the first backoff step"


def test_command_thread_poll_once_clears_backoff_after_a_clean_pass(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", False)
    ct = R.CommandThread(db=None, allow_uids=("u1",), root=".", log=lambda *_: None)
    ct._quota_backoff = 60.0
    ct._poll_uid = lambda uid: 0
    ct.poll_once()
    assert ct._quota_backoff == 0.0
