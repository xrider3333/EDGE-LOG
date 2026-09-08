"""
Firestore read-quota guards in api/runner.py (2026-09-07).

WHY: five runner processes (primary + 4 drain-only _run_worker.vbs workers) each
polled Firestore independently with no read accounting and no backoff on 429
(ResourceExhausted), and blew the whole Spark-plan 50,000-reads/day quota in under
two hours, twice. These pin the pure pieces of the fix: the read counter, the 429
backoff, the 429 detector, and CommandThread's primary-vs-worker poll cadence.
None of this needs a real Firestore client — see test_runner_sweep.py for the
fake-Firestore tests that exercise the claim/sweep paths this fix also touches.

2026-09-08 additions: the meter above was itself under-reporting (an empty poll
recorded 0 reads when Firestore actually bills a minimum of 1 per query), a worker
no longer constructs CommandThread at all, and CommandThread's poll is now
on_snapshot listener-driven with a flat-poll fallback — same shape as
FirestoreQueue's job-queue listener. The two tests that need a real query object
built inside the code under test (`google.cloud.firestore_v1.base_query.FieldFilter`)
use `pytest.importorskip` so they skip cleanly where that dependency isn't installed,
same as test_runner_sweep.py.
"""
import argparse
import os
import sys

import pytest

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


# ── minimum-charge rule (2026-09-08) ──────────────────────────────────────────────
# Firestore bills a minimum of one document read for EVERY query, even one that
# returns nothing (see _note_reads's docstring for the quoted pricing-page rule).
# The `[reads]` meter used to idle at "0 reads in the last 60s" on a quiet queue
# because every call site passed the raw doc COUNT (0 on an empty poll) instead of
# max(1, n). These pin the fix at the two real call sites that are cheapest to
# exercise without a live Firestore project: FirestoreQueue.run_once's queued-docs
# poll (bucket 'poll') and CommandThread._poll_uid's commands poll (bucket 'cmd').

class _EmptyStream:
    def limit(self, _n):
        return self

    def stream(self):
        return iter(())


class _EmptyCollection:
    def where(self, filter=None):
        return _EmptyStream()


class _EmptyDoc:
    def collection(self, _name):
        return _EmptyCollection()


class _EmptyDb:
    """A Firestore client stub whose every query returns zero documents — enough to
    drive FirestoreQueue.run_once / CommandThread._poll_uid without a real project.
    Needs google.cloud.firestore_v1.base_query importable because the code under
    test builds a real FieldFilter internally (see the importorskip in each test)."""

    def collection(self, _name):
        return self

    def document(self, _uid):
        return _EmptyDoc()


def test_run_once_empty_poll_meters_minimum_one_read_not_zero():
    pytest.importorskip("google.cloud.firestore_v1.base_query",
                        reason="google-cloud-firestore is not part of the CI dev deps")
    q = R.FirestoreQueue.__new__(R.FirestoreQueue)   # no credentials, no network
    q.col = "backtests"
    q.allow = {"uid1"}
    q.db = _EmptyDb()
    R._READS.summary()                                # drain any earlier counts
    q.run_once(log=lambda *_: None)
    snap = R._READS.summary()
    assert snap.get("poll") == 1, (
        "an empty queued-docs query still bills 1 read -- the meter must not report 0")


def test_command_thread_poll_uid_empty_result_meters_minimum_one_read():
    pytest.importorskip("google.cloud.firestore_v1.base_query",
                        reason="google-cloud-firestore is not part of the CI dev deps")
    monkeypatch_is_worker = R._IS_WORKER
    try:
        R._IS_WORKER = False
        ct = R.CommandThread(db=_EmptyDb(), allow_uids=("u1",), root=".",
                             log=lambda *_: None)
        R._READS.summary()                            # drain any earlier counts
        n = ct._poll_uid("u1")
        assert n == 0
        snap = R._READS.summary()
        assert snap.get("cmd") == 1, (
            "an empty commands poll still bills 1 read -- the meter must not report 0")
    finally:
        R._IS_WORKER = monkeypatch_is_worker


# ── workers don't get a CommandThread at all (2026-09-08) ─────────────────────────
# A drain-only worker's whole job is to run backtest jobs; it never answers
# get_bars/get_blotter/similar_setups/config_trades (verified: CommandThread._serve
# only has branches for those four actions, nothing job-control shaped — cancel/
# pause/resume/requeue live in FirestoreQueue.run_once/sweep_orphans instead, which
# every worker still runs unchanged via main()'s watch loop). So main() must not
# even construct the thread there. _start_cmd_thread_if_primary is main()'s
# construction site pulled out into a plain function so this is testable without
# running the --watch loop, which never returns.

def test_worker_does_not_construct_command_thread(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", True)
    calls = []
    monkeypatch.setattr(R, "CommandThread", lambda *a, **k: calls.append((a, k)))
    a = argparse.Namespace(firestore=True, allow_uid=["uid1"])
    q = argparse.Namespace(db=None)
    result = R._start_cmd_thread_if_primary(a, q)
    assert calls == [], "a worker must never construct CommandThread"
    assert result is None


def test_primary_does_construct_command_thread(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", False)
    calls = []

    class _FakeCommandThread:
        def __init__(self, db, allow_uids, root, log=print):
            calls.append((db, allow_uids, root))

        def run_forever(self):
            return None   # real thread target: must return promptly for the test

    monkeypatch.setattr(R, "CommandThread", _FakeCommandThread)
    a = argparse.Namespace(firestore=True, allow_uid=["uid1"])
    q = argparse.Namespace(db=None)
    result = R._start_cmd_thread_if_primary(a, q)
    assert len(calls) == 1, "the primary must construct exactly one CommandThread"
    assert isinstance(result, _FakeCommandThread)


def test_local_queue_path_never_constructs_command_thread(monkeypatch):
    # a.firestore False (LocalQueue) has no commands subcollection to poll at all,
    # on the primary or a worker.
    monkeypatch.setattr(R, "_IS_WORKER", False)
    calls = []
    monkeypatch.setattr(R, "CommandThread", lambda *a, **k: calls.append((a, k)))
    a = argparse.Namespace(firestore=False, allow_uid=[])
    q = argparse.Namespace(db=None)
    assert R._start_cmd_thread_if_primary(a, q) is None
    assert calls == []


# ── CommandThread listener conversion (2026-09-08) ────────────────────────────────
# Mirrors FirestoreQueue's job-queue listener: an on_snapshot callback sets a wake
# Event instead of the thread polling on a flat timer; a backstop poll underneath
# covers a wedged channel; the fallback (listener attach fails) keeps the old flat
# POLL_SEC/BUSY_POLL_SEC poll. These drive run_forever directly with poll_once/
# start_listeners monkeypatched, so no real Firestore listener is needed, and each
# test stops the thread itself (run_forever's `while not self._stop` loop) so
# nothing here can hang.

def test_command_thread_on_snapshot_sets_wake_and_meters_cmd_bucket(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", False)
    ct = R.CommandThread(db=None, allow_uids=("u1",), root=".", log=lambda *_: None)
    assert not ct.wake.is_set()
    R._READS.summary()                                # drain any earlier counts
    ct._on_snapshot(_col_snapshot=[], _changes=[], _read_time=None)
    assert ct.wake.is_set(), "a snapshot callback (even an empty one) must set wake"
    snap = R._READS.summary()
    assert snap.get("cmd") == 1, "an empty snapshot still bills the minimum 1 read"


def test_command_thread_run_forever_serves_on_wake_then_stops(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", False)
    ct = R.CommandThread(db=None, allow_uids=("u1",), root=".", log=lambda *_: None)
    monkeypatch.setattr(ct, "start_listeners",
                        lambda log=print, ready_timeout=15.0: True)
    calls = {"n": 0}

    def _fake_poll_once():
        calls["n"] += 1
        if calls["n"] == 1:
            return 1          # served the one command the wake was about
        # the busy-cadence re-check finds nothing more -- stop the thread so the
        # test's call to run_forever() returns instead of blocking on the trailing
        # self.wake.wait()
        ct._stop = True
        ct.wake.set()
        return 0

    monkeypatch.setattr(ct, "poll_once", _fake_poll_once)
    ct.wake.set()   # simulate a snapshot callback having already fired before start
    ct.run_forever()
    assert calls["n"] == 2, "serve once, then the immediate busy-cadence re-check"
    assert ct._stop is True


def test_command_thread_run_forever_falls_back_to_flat_poll_when_listener_attach_raises(monkeypatch):
    monkeypatch.setattr(R, "_IS_WORKER", False)
    logged = []
    ct = R.CommandThread(db=None, allow_uids=("u1",), root=".",
                         log=lambda m: logged.append(m))

    def _boom(log=print, ready_timeout=15.0):
        raise RuntimeError("listener attach failed")

    monkeypatch.setattr(ct, "start_listeners", _boom)
    calls = {"n": 0}

    def _fake_poll_once():
        calls["n"] += 1
        ct._stop = True
        return 0

    monkeypatch.setattr(ct, "poll_once", _fake_poll_once)
    monkeypatch.setattr(R.time, "sleep", lambda _s: None)   # skip the real POLL_SEC wait
    ct.run_forever()
    assert calls["n"] == 1, "the flat-poll fallback must still serve every pass"
    assert any("cmd listener: FAILED -> polling every" in m for m in logged), (
        "a failed listener attach must log the documented fallback message")
