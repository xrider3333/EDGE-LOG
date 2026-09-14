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

ONE COPY PER HOST (2026-09-14). The heartbeat is check-then-write, so two processes could
both find it absent and both tick -- on the VM, the systemd unit plus the runner's fallback
thread, each with its own memory and, once the broker mirror is armed, its own orders. The
slot is now an OS file lock that the loop itself takes (bottom of this file), and a unit that
was refused the cross-host lease leaves a STANDBY marker that keeps the runner's fallback off.
"""
import os
import sys
import subprocess
import threading
import time

import pytest

from api import qqq_exec as qe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


@pytest.mark.skipif(os.name != "nt", reason="the wscript launcher is Windows-only; Linux is "
                    "covered by test_ensure_standalone_on_linux_* in test_qqq_exec_edgelog_home.py")
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


# ── one copy per host: the serving slot is an OS lock the loop itself takes ─────────

def _slot_child(lock, hold_sec=0.0):
    """A separate PROCESS that tries to take the serving slot for `lock`, prints held/refused,
    and keeps the slot for `hold_sec` if it got it."""
    code = ("import sys, time\n"
            f"sys.path.insert(0, {ROOT!r})\n"
            "from api import qqq_exec as qe\n"
            f"qe.SERVING_LOCK = {lock!r}\n"
            "slot = qe._acquire_host_slot(log=lambda *_: None)\n"
            "print('held' if slot is not None else 'refused', flush=True)\n"
            f"time.sleep({float(hold_sec)!r} if slot is not None else 0)\n")
    return subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, stdout=subprocess.PIPE,
                            text=True)


def _acquire_within(sec):
    end = time.time() + sec
    while True:
        slot = qe._acquire_host_slot(log=lambda *_: None)
        if slot is not None or time.time() > end:
            return slot
        time.sleep(0.05)


def test_the_serving_slot_admits_exactly_one_process(tmp_path, monkeypatch):
    lock = str(tmp_path / "SERVING.lock")
    monkeypatch.setattr(qe, "SERVING_LOCK", lock)
    mine = qe._acquire_host_slot(log=lambda *_: None)
    assert mine is not None
    try:
        assert qe._acquire_host_slot(log=lambda *_: None) is None, \
            "a second loop in the SAME process is a second copy of the book too"
        out, _ = _slot_child(lock).communicate(timeout=120)
        assert out.strip() == "refused"
    finally:
        qe._leave_host_slot(mine)
    out, _ = _slot_child(lock).communicate(timeout=120)
    assert out.strip() == "held", "released on exit, free for the next process"


def test_a_hard_killed_holder_frees_the_slot_with_nothing_stale_to_wait_out(tmp_path, monkeypatch):
    lock = str(tmp_path / "SERVING.lock")
    monkeypatch.setattr(qe, "SERVING_LOCK", lock)
    child = _slot_child(lock, hold_sec=120)
    try:
        assert child.stdout.readline().strip() == "held"
        assert qe._acquire_host_slot(log=lambda *_: None) is None
    finally:
        child.kill()
        child.wait(timeout=10)
    slot = _acquire_within(5.0)
    assert slot is not None
    qe._leave_host_slot(slot)


def test_unit_and_runner_fallback_on_one_host_never_both_tick(tmp_path, monkeypatch):
    """The same-host half of scenario D. The unit holds the slot but its first heartbeat has
    not been written yet (e.g. both start at VM boot), so the runner starts its fallback
    thread anyway -- which must refuse instead of running a second copy of the book."""
    out = tmp_path / "qqq_exec"
    lock = str(out / "SERVING.lock")
    for name, path in {"OUT_DIR": out, "CONFIG_PATH": out / "config.json",
                       "STATE_PATH": out / "state.json", "SERVING_LOCK": lock}.items():
        monkeypatch.setattr(qe, name, str(path))
    monkeypatch.setattr(qe, "HOST_SLOT_WAIT_SEC", 0.5)
    stop = threading.Event()
    ticks = []
    monkeypatch.setattr(qe, "_reconcile_broker_at_boot", lambda log=print: None)
    monkeypatch.setattr(qe, "tick", lambda **kw: (ticks.append(1), stop.set())
                        and (kw["cfg"], kw["state"], {}))
    child = _slot_child(lock, hold_sec=120)
    try:
        assert child.stdout.readline().strip() == "held"
        logs = []
        qe.qqq_exec_thread(None, ["u"], stop=stop, log=logs.append)
        assert ticks == [], "the fallback thread must not tick while the unit holds the slot"
        assert any("REFUSING" in m for m in logs)
    finally:
        stop.set()
        child.kill()
        child.wait(timeout=10)


# ── a unit refused the cross-host lease keeps the runner's fallback off ─────────────

class _LeaseDb:
    def __init__(self, doc):
        self.doc = doc

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def get(self, **kwargs):
        doc = self.doc
        return type("Snap", (), {"exists": doc is not None, "to_dict": lambda self: doc})()


def test_a_unit_refused_the_lease_keeps_the_runner_fallback_off(tmp_path, monkeypatch):
    """Simulation scenario D: serve() refuses and exits (on the VM systemd restarts it), so
    there is no heartbeat -- which ensure_standalone() used to read as "start the runner's
    own copy". The refusal's STANDBY marker now counts as a standalone being present."""
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "SERVING.lock"))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    db = _LeaseDb({"lease": {"host_id": "owners-pc", "leased_at": time.time()}})
    ticked = []
    monkeypatch.setattr(qe, "qqq_exec_thread", lambda *a, **k: ticked.append(1))
    qe.serve(db, ["uid1"], log=lambda *_: None)
    assert ticked == []
    fresh, note = qe.standby_fresh()
    assert fresh and "owners-pc" in note
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a))
    vbs = tmp_path / "_run_qqq_exec.vbs"
    vbs.write_text("' launcher", encoding="utf-8")
    assert qe.ensure_standalone(log=lambda *_: None, vbs=str(vbs)) is True, \
        "a unit standing by for the lease must keep the runner's fallback thread off"
    assert launched == [], "and nothing is (re)launched either"


def test_standby_marker_stops_windows_relaunching_a_standalone_that_would_be_refused(
        tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "SERVING.lock"))
    qe._note_standby("host 'cloud-vm' holds a fresh lease (3s old)", log=lambda *_: None)
    vbs = tmp_path / "_run_qqq_exec.vbs"
    vbs.write_text("' launcher", encoding="utf-8")
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a))
    assert qe.ensure_standalone(log=lambda *_: None, vbs=str(vbs)) is True
    assert launched == []


def test_a_stale_standby_marker_no_longer_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "SERVING.lock"))
    qe._note_standby("an old refusal", log=lambda *_: None)
    old = time.time() - qe.SERVING_STALE_SEC - 30
    os.utime(qe._standby_path(), (old, old))
    assert qe.standby_fresh() == (False, None)
    # no launcher anywhere: an ignored marker means "fall back", on either OS
    assert qe.ensure_standalone(log=lambda *_: None, vbs=str(tmp_path / "no_such.vbs")) is False


def test_a_relaunch_waits_briefly_for_a_just_released_slot(tmp_path, monkeypatch):
    """Windows can free a killed holder's lock a moment late; the relaunch right after a
    hard kill (2026-09-11) must wait a few seconds for it instead of exiting at once."""
    out = tmp_path / "qqq_exec"
    lock = str(out / "SERVING.lock")
    monkeypatch.setattr(qe, "SERVING_LOCK", lock)
    child = _slot_child(lock, hold_sec=1.5)
    try:
        assert child.stdout.readline().strip() == "held"
        slot, why = qe._enter_host_slot(log=lambda *_: None)
        assert slot is not None, why
        qe._leave_host_slot(slot)
    finally:
        child.kill()
        child.wait(timeout=10)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork-inherited locks are a POSIX matter")
def test_leaving_the_slot_releases_it_even_if_a_forked_child_still_holds_the_fd(tmp_path, monkeypatch):
    """The runner's process pools fork on Linux; a child forked while the fallback thread
    held the slot shares the lock, so closing only our descriptor would keep the systemd
    unit locked out until that child exits."""
    lock = str(tmp_path / "SERVING.lock")
    monkeypatch.setattr(qe, "SERVING_LOCK", lock)
    slot = qe._acquire_host_slot(log=lambda *_: None)
    assert slot is not None
    pid = os.fork()
    if pid == 0:                      # child: keep the inherited descriptor open a while
        time.sleep(20)
        os._exit(0)
    try:
        qe._leave_host_slot(slot)
        out, _ = _slot_child(lock).communicate(timeout=120)
        assert out.strip() == "held"
    finally:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
