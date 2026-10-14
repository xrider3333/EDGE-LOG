"""tools/pull_box_ledgers.py - a hung or failed copy is retried once and always logged (2026-10-14 14:45: an uncaught
scp timeout exited 1 with no log line; the NT8 sweep's phone push read as NinjaTrader trouble)."""
import subprocess
import types

from tools import pull_box_ledgers as P


def _setup(monkeypatch, tmp_path, script):
    log = tmp_path / "pull.log"
    monkeypatch.setattr(P, "LOG_PATH", str(log))
    monkeypatch.setattr(P, "_sleep", lambda sec: None)
    calls = []

    def fake_run(cmd, **kw):
        rel = cmd[-2].split(P.REMOTE_HOME + "/", 1)[1]
        calls.append(rel)
        return script(rel, calls.count(rel))

    monkeypatch.setattr(P.subprocess, "run", fake_run)
    return log, calls


def _ok():
    return types.SimpleNamespace(returncode=0, stderr="")


def test_a_hung_copy_is_retried_once_and_the_run_is_ok(monkeypatch, tmp_path):
    first = P.FILES[0]

    def script(rel, n):
        if rel == first and n == 1:
            raise subprocess.TimeoutExpired(cmd="scp", timeout=P.SCP_TIMEOUT_S)
        return _ok()

    log, calls = _setup(monkeypatch, tmp_path, script)
    assert P.main(["--dest", str(tmp_path / "dest")]) == 0
    assert calls.count(first) == 2 and len(calls) == len(P.FILES) + 1
    assert f"OK copied {len(P.FILES)}/{len(P.FILES)}" in log.read_text()


def test_a_copy_that_keeps_hanging_is_a_logged_fail_not_a_crash(monkeypatch, tmp_path):
    first = P.FILES[0]
    missing = P.FILES[-1]

    def script(rel, n):
        if rel == first:
            raise subprocess.TimeoutExpired(cmd="scp", timeout=P.SCP_TIMEOUT_S)
        if rel == missing:
            return types.SimpleNamespace(returncode=1, stderr="scp: No such file or directory")
        return _ok()

    log, calls = _setup(monkeypatch, tmp_path, script)
    assert P.main(["--dest", str(tmp_path / "dest")]) == 1
    text = log.read_text()
    assert " FAIL copied " in text
    assert f"FAILED: {first} (timed out after {P.SCP_TIMEOUT_S}s)" in text
    assert f"missing on box: {missing}" in text
    assert calls.count(missing) == 1                       # a file not on the box is not retried
