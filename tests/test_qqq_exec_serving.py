"""Standalone serving for the QQQ shadow adapter (api/qqq_exec.py).

WHY IT EXISTS. The adapter used to run as a thread inside the job runner, so its uptime was
a property of the busiest process on the box: roughly 30 concurrent sessions restart the
fleet all day to load code, and on 2026-09-09 that booted the adapter EIGHT times between
09:47 and 13:49. The day recorded ~94% tick coverage against a 95% readiness bar — the
forward trial was being failed by deploys rather than by anything wrong with the adapter.

The adapter now runs detached, and the runner calls `ensure_standalone()`, which leaves a
live one strictly alone. These tests pin the two behaviours that make that safe: liveness is
decided by a heartbeat (never a bare pid, which can be reused and is never cleaned up after
a hard kill), and the runner only ever launches when the slot is genuinely free.
"""
import os
import sys
import subprocess
import time

import pytest

from api import qqq_exec as qe


def _lock(tmp_path, pid=None, age_sec=0.0):
    """`pid` defaults to THIS process, because since 2026-09-11 a lock is only live when its
    process is too -- an invented pid now correctly reads as a freed slot."""
    pid = os.getpid() if pid is None else pid
    p = tmp_path / "SERVING.lock"
    p.write_text(f"{pid} 2026-09-09 14:00:00\n", encoding="utf-8")
    if age_sec:
        old = time.time() - age_sec
        os.utime(p, (old, old))
    return str(p)


def test_fresh_lock_reads_as_alive(tmp_path):
    alive, pid = qe.serving_alive(_lock(tmp_path))
    assert alive is True
    assert pid == os.getpid()


def test_stale_lock_frees_the_slot(tmp_path):
    # a hard-killed process never removes its lock, so age is the only honest signal
    alive, pid = qe.serving_alive(_lock(tmp_path, age_sec=qe.SERVING_STALE_SEC + 30))
    assert alive is False
    assert pid is None


def test_fresh_lock_whose_process_is_GONE_frees_the_slot(tmp_path):
    """The 2026-09-11 failure. A hard Stop-Process skips serve()'s cleanup, so the lock sits
    there FRESH for up to two minutes. The replacement launched five seconds later read that
    fresh lock, decided another adapter was serving, and exited -- leaving NO adapter at all,
    with nothing due to revive it until the next runner boot. The heartbeat alone cannot see
    this; the pid can."""
    # pid 1 exists on POSIX, so use an id that cannot be running
    dead = 999999
    alive, pid = qe.serving_alive(_lock(tmp_path, pid=dead))
    assert alive is False, "a fresh lock held by a dead process must not block a replacement"
    assert pid is None


def test_unknowable_pid_is_treated_as_alive():
    """Fail-safe direction: if the platform will not tell us, assume the process IS running
    and let the heartbeat age free the slot instead. A false 'dead' would run two adapters."""
    assert qe._pid_alive(os.getpid()) is True
    assert qe._pid_alive(0) is False
    assert qe._pid_alive(None) is False


def test_missing_lock_frees_the_slot(tmp_path):
    alive, pid = qe.serving_alive(str(tmp_path / "nope.lock"))
    assert alive is False
    assert pid is None


def test_unreadable_lock_never_raises(tmp_path):
    p = tmp_path / "SERVING.lock"
    p.write_text("not-a-pid\n", encoding="utf-8")
    alive, pid = qe.serving_alive(str(p))
    assert alive is False          # garbage is treated as "no one is serving", not a crash


def test_runner_does_not_launch_when_one_is_already_serving(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "SERVING_LOCK", _lock(tmp_path))
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a))
    assert qe.ensure_standalone(log=lambda *_: None) is True
    assert launched == [], "a live adapter must never be restarted by a fleet restart"


def test_runner_launches_when_the_slot_is_free(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    vbs = tmp_path / "_run_qqq_exec.vbs"
    vbs.write_text("' launcher", encoding="utf-8")
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a[0]))
    assert qe.ensure_standalone(log=lambda *_: None, vbs=str(vbs)) is True
    assert launched and launched[0][0] == "wscript.exe", "must launch DETACHED, not inline"


def test_missing_launcher_falls_back_to_the_in_runner_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    assert qe.ensure_standalone(log=lambda *_: None,
                                vbs=str(tmp_path / "no_such.vbs")) is False


def test_serve_refuses_to_double_run(tmp_path, monkeypatch):
    """A second serving process must exit rather than double-tick. The lock has to name a
    real, LIVE, *different* process for this to mean anything, so spawn one: since the pid
    check landed, a made-up pid reads as a freed slot and would let this pass vacuously."""
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        monkeypatch.setattr(qe, "SERVING_LOCK", _lock(tmp_path, pid=other.pid))
        ticked = []
        monkeypatch.setattr(qe, "qqq_exec_thread", lambda *a, **k: ticked.append(1))
        qe.serve(db=None, uids=["u"], log=lambda *_: None)
        assert ticked == [], "a second serving process must exit rather than double-tick"
    finally:
        other.kill()
        other.wait(timeout=10)


@pytest.mark.parametrize("field", ["SERVING_LOCK", "SERVING_STALE_SEC", "QQQ_EXEC_VBS"])
def test_serving_contract_is_present(field):
    assert hasattr(qe, field)
