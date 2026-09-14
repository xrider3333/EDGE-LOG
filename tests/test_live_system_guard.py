"""tests/conftest.py's guard rails, pinned: every test starts with an OFF-mode order adapter in a
temp dir, and a write under the real EDGELOG_HOME (or a Webull connection, or on Windows a
console-wide Ctrl+C) is blocked and fails the test that made it.

Every path this file aims at the real home sits inside a directory that does not exist
(_guard_selftest_<uuid>) and nothing here creates parent directories, so even a broken guard
could only raise FileNotFoundError -- never leave a file on the owner's machine.
"""
import csv
import json
import os
import socket
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime

import pytest

from api import cloud_signal as cs
from api import qqq_exec as qe
from api import webull_orders as wo

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _unreachable(guard, *parts):
    """A path under the real home, inside a directory that does not exist."""
    missing = os.path.join(guard.real_home, f"_guard_selftest_{uuid.uuid4().hex}")
    assert not os.path.exists(missing)
    return os.path.join(missing, *parts)


def test_writes_under_the_real_home_are_blocked_and_recorded(live_system_guard):
    target = _unreachable(live_system_guard, "x.txt")
    with pytest.raises(PermissionError, match="real EDGELOG_HOME"):
        open(target, "w")
    with pytest.raises(PermissionError, match="real EDGELOG_HOME"):
        os.open(target, os.O_WRONLY | os.O_CREAT)
    fd, tmp = tempfile.mkstemp()
    os.close(fd)
    try:
        with pytest.raises(PermissionError, match="real EDGELOG_HOME"):
            os.replace(tmp, target)
    finally:
        os.remove(tmp)
    with pytest.raises(PermissionError, match="real EDGELOG_HOME"):
        os.mkdir(os.path.join(os.path.dirname(target), "sub"))
    assert [b["event"] for b in live_system_guard.take()] == ["open", "open", "os.rename", "os.mkdir"]


def test_reads_under_the_real_home_and_temp_writes_pass_through(live_system_guard, tmp_path):
    with pytest.raises(FileNotFoundError):
        open(_unreachable(live_system_guard, "x.txt"), encoding="utf-8")   # the read reaches the OS
    (tmp_path / "ok.txt").write_text("fine", encoding="utf-8")
    assert live_system_guard.take() == []


def test_a_swallowed_write_is_still_caught(live_system_guard):
    """The leak's own shape: OrderAdapter._save_state catches every exception and only logs."""
    try:
        with open(_unreachable(live_system_guard, "state.json"), "w", encoding="utf-8") as f:
            f.write("{}")
    except Exception:
        pass
    (blocked,) = live_system_guard.take()
    assert blocked["event"] == "open" and "_guard_selftest_" in blocked["target"]


def test_a_webull_connection_is_blocked(live_system_guard):
    host = "guard-selftest.webull.invalid"   # .invalid never resolves, even past a broken guard
    with pytest.raises(PermissionError, match="connect to Webull"):
        socket.getaddrinfo(host, 443)
    assert [b["target"] for b in live_system_guard.take()] == [host]


def test_a_console_wide_ctrl_c_is_blocked_on_windows(live_system_guard):
    """os.kill(pid, 0) is POSIX's liveness probe; on Windows it is CTRL_C_EVENT, a Ctrl+C to every
    process on the console. The event is raised with sys.audit, never os.kill, so even a broken
    guard sends nothing."""
    if sys.platform != "win32":
        sys.audit("os.kill", os.getpid(), 0)   # the genuine probe: left alone
        assert live_system_guard.take() == []
        return
    with pytest.raises(PermissionError, match="console-wide Ctrl"):
        sys.audit("os.kill", os.getpid(), 0)
    sys.audit("os.kill", os.getpid(), 9)       # TerminateProcess on one pid: left alone
    (blocked,) = live_system_guard.take()
    assert blocked["event"] == "os.kill" and blocked["target"].startswith(f"pid {os.getpid()},")


def test_every_test_starts_with_an_isolated_off_mode_order_adapter(live_system_guard):
    adapter = qe._get_broker_adapter()
    assert adapter is qe._ORDER_ADAPTER, "the singleton is pre-set, never built from the defaults"
    assert adapter.effective_mode()[0] == wo.MODE_OFF
    assert adapter._state_path() != wo.DEFAULT_STATE_PATH
    for path in (adapter._state_path(), adapter._kill_file(), adapter._arm_file(),
                 adapter._paper_keys_path(), adapter._live_keys_path(),
                 adapter.cfg["paper_token_dir"], adapter.cfg["live_token_dir"], qe.BROKER_ORDERS_CSV):
        assert not live_system_guard.is_live(path), path
    assert os.path.dirname(qe.BROKER_ORDERS_CSV) == os.path.dirname(adapter._state_path())


def test_a_tick_that_does_not_stub_the_adapter_saves_to_temp_not_the_live_file(
        tmp_path, monkeypatch, live_system_guard):
    """The leak end to end: tick() -> _run_broker_housekeeping -> reset_daily_pnl -> _save_state,
    set up like tests/test_qqq_exec_engine_source.py's
    test_engine_mode_tick_never_opens_a_ninjatrader_or_nq_file, which wrote the live state file
    because nothing in it stubs the adapter."""
    paths = cs._paths(home=str(tmp_path / "cs_home"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(cs.SIGNAL_COLS)
    out = tmp_path / "qqq_exec_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, name in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                       ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv")):
        monkeypatch.setattr(qe, attr, str(out / name))
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: None)

    def boom(*a, **k):
        raise AssertionError("engine mode never prices off the quote/ratio path")

    qe.tick(fills_path=str(tmp_path / "fills.csv"), now=datetime(2026, 9, 8, 9, 40),
            quote_fn=boom, ratio_fn=boom, force_calib=True, log=lambda *_: None)
    with open(qe._ORDER_ADAPTER._state_path(), encoding="utf-8") as f:
        assert json.load(f)["daily_pnl"] == 0.0, "housekeeping ran and saved to the temp state file"
    assert live_system_guard.take() == []


def test_a_test_that_writes_under_the_real_home_fails_even_when_it_swallows_the_error(
        tmp_path, live_system_guard):
    """The guard end to end: a separate pytest run of this very conftest."""
    inner = tmp_path / "inner"
    inner.mkdir()
    with open(os.path.join(TESTS_DIR, "conftest.py"), encoding="utf-8") as f:
        (inner / "conftest.py").write_text(f.read(), encoding="utf-8")
    target = _unreachable(live_system_guard, "x.txt")
    (inner / "test_inner.py").write_text(
        "def test_swallows_a_live_write():\n"
        "    try:\n"
        f"        open({target!r}, 'w')\n"
        "    except OSError:\n"
        "        pass\n"
        "\n"
        "def test_clean():\n"
        "    pass\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "--rootdir", str(inner), "--basetemp", str(tmp_path / "bt"), str(inner)],
                       cwd=str(inner), capture_output=True, text=True, timeout=120)
    assert r.returncode == 1, r.stdout + r.stderr
    # the swallowed write fails at teardown (pytest counts that test "passed" AND "error")
    assert "2 passed, 1 error" in r.stdout, r.stdout
    assert "ERROR test_inner.py::test_swallows_a_live_write" in r.stdout, r.stdout
    assert "reached for the owner's live setup" in r.stdout and "_guard_selftest_" in r.stdout
