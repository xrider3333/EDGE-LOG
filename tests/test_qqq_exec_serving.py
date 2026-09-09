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
import time

import pytest

from api import qqq_exec as qe


def _lock(tmp_path, pid=4242, age_sec=0.0):
    p = tmp_path / "SERVING.lock"
    p.write_text(f"{pid} 2026-09-09 14:00:00\n", encoding="utf-8")
    if age_sec:
        old = time.time() - age_sec
        os.utime(p, (old, old))
    return str(p)


def test_fresh_lock_reads_as_alive(tmp_path):
    alive, pid = qe.serving_alive(_lock(tmp_path, pid=4242))
    assert alive is True
    assert pid == 4242


def test_stale_lock_frees_the_slot(tmp_path):
    # a hard-killed process never removes its lock, so age is the only honest signal
    alive, pid = qe.serving_alive(_lock(tmp_path, age_sec=qe.SERVING_STALE_SEC + 30))
    assert alive is False
    assert pid is None


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
    monkeypatch.setattr(qe, "SERVING_LOCK", _lock(tmp_path, pid=777))
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
    monkeypatch.setattr(qe, "SERVING_LOCK", _lock(tmp_path, pid=999))
    ticked = []
    monkeypatch.setattr(qe, "qqq_exec_thread", lambda *a, **k: ticked.append(1))
    qe.serve(db=None, uids=["u"], log=lambda *_: None)
    assert ticked == [], "a second serving process must exit rather than double-tick"


@pytest.mark.parametrize("field", ["SERVING_LOCK", "SERVING_STALE_SEC", "QQQ_EXEC_VBS"])
def test_serving_contract_is_present(field):
    assert hasattr(qe, field)
