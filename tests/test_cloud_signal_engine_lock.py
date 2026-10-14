"""api/cloud_signal.py -- ONE ENGINE PER HOST (owner 2026-10-14 via MANAGER #162/#163: "make
sure it does not happen again").

On 09-21 the box ran two copies of the signal engine, each rewriting state.json / signals.csv /
heartbeat.json from its own memory. The heartbeat refusal only ever guarded a HAND run
(cmd_once / cmd_loop) and, on purpose, never cloud_signal_thread. Now every live entry point
takes a non-blocking OS lock on <state_dir>/engine.lock first (msvcrt / flock, the
api/qqq_exec.py _acquire_host_slot pattern); a second copy logs and returns at once, writing
nothing. Pinned here:

  1. a lock held by ANOTHER PROCESS makes cloud_signal_thread return at once -- state.json,
     signals.csv and heartbeat.json byte- and mtime-identical -- and the lock frees itself
     when that process ends;
  2. a second handle in the SAME process is refused too (a second engine thread is a second
     writer), and cmd_once / cmd_loop refuse with exit code 2, writing nothing;
  3. the thread releases the lock when it returns, so a restart in-process can take it.

Every store is under tmp_path; the holder subprocess imports nothing from this repo.
"""
import os
import subprocess
import sys
import threading

import pytest

import api.cloud_signal as cs


_HOLDER = r"""
import sys
f = open(sys.argv[1], "a+b")
try:
    import msvcrt
    f.seek(0)
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
except ImportError:
    import fcntl
    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
print("locked", flush=True)
sys.stdin.read()          # hold the lock until the test closes our stdin
"""

LIVE_FILES = ("state_path", "signals_path", "heartbeat_path")


def _armed_home(tmp_path, monkeypatch):
    """A live store a running engine has written to, made DEFAULT_PATHS; this host is serving."""
    paths = cs._paths(home=str(tmp_path / "live_home"))
    os.makedirs(paths["state_dir"], exist_ok=True)
    cs._write_state({"legs": {"STUB": {"trades": {}, "seeded": True}},
                     "generated_at": "2026-10-14T09:00:00-04:00"}, paths)
    cs._append_signals([{"emitted_at": "2026-10-14T09:00:00-04:00", "leg": "STUB",
                         "event": "SEED", "reason": "the live run's own seed"}], paths)
    cs._write_heartbeat(paths, ok=True, note="the other engine's beat")
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(cs, "_serving_hosts_ok", lambda log=print: (True, None))
    # never reached when the lock works; kept harmless (no network, no real files) if it does not
    monkeypatch.setattr(cs, "log_history_windows", lambda *a, **k: None)

    def no_fetch(*a, **k):
        raise RuntimeError("the refused engine must never fetch")
    monkeypatch.setattr(cs, "fetch_and_merge", no_fetch)
    return paths


def _snapshot(paths):
    out = {}
    for key in LIVE_FILES:
        p = paths[key]
        with open(p, "rb") as f:
            out[key] = (os.stat(p).st_mtime_ns, f.read())
    return out


def _run_thread(logs, timeout=10.0):
    """cloud_signal_thread on a daemon thread with a stop event that is NOT set: it may only
    come back on its own by refusing. Returns True when it did, within `timeout`."""
    stop = threading.Event()
    th = threading.Thread(target=cs.cloud_signal_thread, kwargs=dict(stop=stop, log=logs.append),
                          daemon=True)
    th.start()
    th.join(timeout)
    returned = not th.is_alive()
    stop.set()
    return returned


@pytest.fixture
def holder(tmp_path):
    """Starts a separate process holding a path's engine lock; yields a starter function."""
    procs = []

    def start(path):
        p = subprocess.Popen([sys.executable, "-I", "-c", _HOLDER, path],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        procs.append(p)
        assert p.stdout.readline().strip() == "locked", "the holder could not take the lock"
        return p

    yield start
    for p in procs:
        try:
            p.stdin.close()
        except Exception:
            pass
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()


def _release(proc):
    proc.stdin.close()
    proc.wait(timeout=10)


def test_second_cloud_signal_thread_exits_when_lock_held(tmp_path, monkeypatch, holder):
    paths = _armed_home(tmp_path, monkeypatch)
    lock_path = cs._engine_lock_path(paths)
    assert lock_path == os.path.join(paths["state_dir"], "engine.lock")
    proc = holder(lock_path)
    before = _snapshot(paths)
    names_before = sorted(os.listdir(paths["state_dir"]))

    logs = []
    assert _run_thread(logs), "the second engine must return at once, not run"

    assert _snapshot(paths) == before, "state.json / signals.csv / heartbeat.json untouched"
    assert sorted(os.listdir(paths["state_dir"])) == names_before, "no file created either"
    assert any("REFUSING" in m and "engine.lock" in m for m in logs), logs
    assert not any("parallel run: ON" in m for m in logs)

    # the OS frees the lock when the holder ends -- nothing stale to clean up
    _release(proc)
    fh = cs._acquire_engine_lock(paths)
    assert fh is not None
    cs._release_engine_lock(fh)


def test_a_second_handle_in_the_same_process_is_refused_too(tmp_path):
    paths = cs._paths(home=str(tmp_path / "h"))
    first = cs._acquire_engine_lock(paths)
    try:
        assert first is not None
        assert cs._acquire_engine_lock(paths) is None
    finally:
        cs._release_engine_lock(first)
    again = cs._acquire_engine_lock(paths)
    assert again is not None
    cs._release_engine_lock(again)


def test_cmd_once_and_cmd_loop_refuse_while_another_engine_holds_the_lock(
        tmp_path, monkeypatch, capsys):
    paths = _armed_home(tmp_path, monkeypatch)
    # an old heartbeat: the heartbeat check alone would let both through
    monkeypatch.setattr(cs, "_live_writer_age_sec", lambda p: cs.LIVE_WRITER_FRESH_SEC + 60)
    held = cs._acquire_engine_lock(paths)
    try:
        before = _snapshot(paths)
        assert cs.cmd_once() == 2
        assert cs.cmd_loop() == 2, "refused before its first iteration -- never loops"
        assert _snapshot(paths) == before
        out = capsys.readouterr().out
        assert "cloud_signal --once: REFUSED" in out and "cloud_signal --loop: REFUSED" in out
        assert out.count("engine.lock") == 2
    finally:
        cs._release_engine_lock(held)


def test_the_thread_releases_the_lock_when_it_returns(tmp_path, monkeypatch):
    paths = _armed_home(tmp_path, monkeypatch)
    stop = threading.Event()
    stop.set()                               # boot, then leave the loop straight away
    logs = []
    cs.cloud_signal_thread(stop=stop, log=logs.append)
    assert any("parallel run: ON" in m for m in logs)
    fh = cs._acquire_engine_lock(paths)
    assert fh is not None, "a returned engine thread must not keep the lock"
    cs._release_engine_lock(fh)


def test_cmd_once_releases_the_lock_even_when_its_step_raises(tmp_path, monkeypatch):
    paths = _armed_home(tmp_path, monkeypatch)
    monkeypatch.setattr(cs, "_live_writer_age_sec", lambda p: None)
    with pytest.raises(RuntimeError, match="never fetch"):
        cs.cmd_once()                        # step() -> the no_fetch stub raises
    fh = cs._acquire_engine_lock(paths)
    assert fh is not None
    cs._release_engine_lock(fh)
