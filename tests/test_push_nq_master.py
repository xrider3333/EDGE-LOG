"""tools/push_nq_master_to_box.py: the refresh-before-push step (2026-09-24). No network, no
child process -- subprocess.run is faked; the ssh/scp half is exercised live, never here."""
import subprocess
import types

import pytest

from tools import push_nq_master_to_box as P


def _fake_run(returncode=0, stdout="", stderr=""):
    def run(*a, **k):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return run


def test_refresh_reports_the_nq_5m_rth_line(monkeypatch):
    out = ("  NOADJ_ES_5m_RTH.csv: +78 bars -> 1,000 total, now through 2026-09-24\n"
           "  NOADJ_NQ_5m_RTH.csv: +78 bars -> 321,724 total, now through 2026-09-24\n"
           "Done. Non-adj masters extended from Yahoo (free, raw front-month).\n")
    monkeypatch.setattr(P.subprocess, "run", _fake_run(0, out))
    ok, note = P._refresh_master()
    assert ok is True
    assert "NOADJ_NQ_5m_RTH.csv: +78 bars" in note and "ES" not in note


def test_refresh_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(P.subprocess, "run", _fake_run(1, "", "yfinance not installed"))
    ok, note = P._refresh_master()
    assert ok is False and "yfinance" in note

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=600)
    monkeypatch.setattr(P.subprocess, "run", boom)
    ok, note = P._refresh_master()
    assert ok is False and "TimeoutExpired" in note


# -- ROBUST UNDER TASK SCHEDULER (2026-10-05) -------------------------------------------------
# 09-30 "FAIL scp: " and 10-01 "FAIL mkdir on box: " (both blank), 10-03 "ssh: connect to host
# ... Unknown error": retries, a failure line that is never blank, explicit ssh/scp paths.
# Still no network: P._run (the one place ssh/scp start) is scripted per command.
import hashlib
import os
import sys


class _Box:
    """Scripts every ssh/scp call. `script[kind]` is a list of results consumed in order
    (the last one repeats); kind is "mkdir", "scp", "mv", "sha_final", "sha_tmp", "rm"."""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def kind(self, args):
        if "scp" in os.path.basename(args[0]).lower():
            return "scp"
        cmd = args[-1]
        if cmd.startswith("mkdir"):
            return "mkdir"
        if cmd.startswith("mv"):
            return "mv"
        if cmd.startswith("rm"):
            return "rm"
        return "sha_tmp" if ".tmp" in cmd else "sha_final"

    def run(self, args, timeout):
        k = self.kind(args)
        self.calls.append(k)
        seq = self.script.get(k) or [(0, "", "")]
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, BaseException):
            raise item
        rc, out, err = item
        return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


@pytest.fixture
def box_env(tmp_path, monkeypatch):
    local = tmp_path / "NOADJ_NQ_5m_RTH.csv"
    local.write_text("ts,open\n1,2\n", encoding="utf-8")
    sha = hashlib.sha256(local.read_bytes()).hexdigest()
    log_path = tmp_path / "push_nq_master.log"
    monkeypatch.setattr(P, "LOG_PATH", str(log_path))
    sleeps = []
    monkeypatch.setattr(P, "_sleep", sleeps.append)
    clients = ["OpenSSH"]
    monkeypatch.setattr(P, "_find_clients",
                        lambda name: [f"C:/fake/{c}/{name}.exe" for c in clients])

    def go(script):
        box = _Box(script)
        monkeypatch.setattr(P, "_run", box.run)
        rc = P.main(["--local", str(local), "--no-refresh"])
        text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        return rc, box, text

    return types.SimpleNamespace(go=go, sha=sha, sleeps=sleeps, clients=clients)


def test_mkdir_retries_with_backoff_then_the_push_lands(box_env):
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "mkdir": [(255, "", ""), (255, "", "ssh: connect to host x port 22: Unknown error"),
                  (0, "", "")],
        "sha_tmp": [(0, box_env.sha + "\n", "")],
    })
    assert rc == 0
    assert box.calls.count("mkdir") == 3
    assert box_env.sleeps == list(P.RETRY_DELAYS_SEC) == [90, 180]
    assert "RETRY mkdir on box: try 1/3 failed (rc=255: no output)" in log
    assert "Unknown error" in log
    assert "OK pushed" in log and "C:/fake/OpenSSH/scp.exe" in log, "the line names what ran"


def test_scp_failure_logs_rc_and_stdout_when_stderr_is_blank(box_env):
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "scp": [(1, "lost connection\n", "")],
    })
    assert rc == 1
    assert box.calls.count("scp") == 3
    assert "FAIL scp after 3 tries: rc=1: stdout: lost connection" in log
    assert "FAIL scp: \n" not in log
    assert "mv" not in box.calls, "a failed upload never renames"


def test_a_timeout_is_a_failed_try_not_a_crash(box_env):
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "mkdir": [subprocess.TimeoutExpired(cmd="ssh", timeout=120), (0, "", "")],
        "sha_tmp": [(0, box_env.sha + "\n", "")],
    })
    assert rc == 0
    assert "try 1/3 failed (timeout after 120s)" in log


def test_rename_retries_and_a_lost_reply_still_counts_when_the_file_is_in_place(box_env):
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", ""), (0, box_env.sha + "\n", "")],
        "sha_tmp": [(0, box_env.sha + "\n", "")],
        "mv": [(255, "", "Connection reset"), (1, "", "mv: cannot stat: No such file")],
    })
    assert rc == 0
    assert box.calls.count("mv") == 3
    assert "but the box holds the new file" in log


def test_rename_that_never_lands_fails(box_env):
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "sha_tmp": [(0, box_env.sha + "\n", "")],
        "mv": [(1, "", "Permission denied")],
    })
    assert rc == 1
    assert "FAIL rename on box after 3 tries: rc=1: Permission denied" in log


def test_box_already_current_skips_without_retrying(box_env):
    rc, box, log = box_env.go({"sha_final": [(0, box_env.sha + "\n", "")]})
    assert rc == 0 and box.calls == ["sha_final"] and box_env.sleeps == []
    assert "SKIP" in log


class _TwoClientBox(_Box):
    """Windows' own OpenSSH fails blank on every call (what a stripped environment does);
    Git's client works."""

    def run(self, args, timeout):
        if "/OpenSSH/" in args[0]:
            self.calls.append("win-" + self.kind(args))
            return types.SimpleNamespace(returncode=255, stdout="", stderr="")
        return super().run(args, timeout)


def test_a_client_that_fails_blank_falls_back_to_the_other_at_once(box_env, monkeypatch):
    box_env.clients[:] = ["OpenSSH", "Git"]
    made = []

    def two(script):
        b = _TwoClientBox(script)
        made.append(b)
        return b
    monkeypatch.setattr(sys.modules[__name__], "_Box", two)
    rc, _box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "sha_tmp": [(0, box_env.sha + "\n", "")],
    })
    box = made[0]
    assert rc == 0
    assert box_env.sleeps == [], "the other client runs at once, not after a retry wait"
    assert "FALLBACK ssh: C:/fake/OpenSSH/ssh.exe failed (rc=255: no output); trying " \
           "C:/fake/Git/ssh.exe" in log
    assert "FALLBACK scp: C:/fake/OpenSSH/scp.exe failed" in log
    # once Git's client worked it is tried first: Windows' own ran once per kind, no more
    assert box.calls.count("win-sha_final") == 1 and box.calls.count("win-scp") == 1
    assert "win-mkdir" not in box.calls and "win-mv" not in box.calls
    assert "OK pushed" in log and "[ssh C:/fake/Git/ssh.exe, scp C:/fake/Git/scp.exe]" in log


def test_both_clients_failing_still_retries_and_names_each(box_env):
    box_env.clients[:] = ["OpenSSH", "Git"]
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "mkdir": [(255, "", "Permission denied (publickey).")],
    })
    assert rc == 1
    assert box.calls.count("mkdir") == 6, "two clients on each of the three tries"
    assert log.count("FALLBACK ssh: C:/fake/OpenSSH/ssh.exe failed") >= 3
    assert "FAIL mkdir on box after 3 tries: rc=255: Permission denied (publickey)." in log


def test_exes_lists_each_client_once_and_the_one_that_worked_first(tmp_path, monkeypatch):
    suffix = ".exe" if os.name == "nt" else ""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / ("ssh" + suffix)).write_text("", encoding="utf-8")
    (b / ("ssh" + suffix)).write_text("", encoding="utf-8")
    for f in (a / ("ssh" + suffix), b / ("ssh" + suffix)):
        os.chmod(f, 0o755)          # shutil.which needs the execute bit on Linux (the CI runner); a no-op on Windows
    monkeypatch.setenv("EDGELOG_SSH_DIR", str(a))
    monkeypatch.setenv("PATH", str(a) + os.pathsep + str(b))
    monkeypatch.setattr(P, "_worked", {})
    if os.name == "nt":
        monkeypatch.setenv("SystemRoot", str(tmp_path / "nowin"))
        monkeypatch.setenv("ProgramFiles", str(tmp_path / "nopf"))
    def norm(paths):
        return [os.path.normcase(p) for p in paths]
    got = P._exes("ssh")
    assert norm(got) == norm([str(a / ("ssh" + suffix))]), "the override and PATH hit are one"
    monkeypatch.setenv("PATH", str(b))
    got = P._exes("ssh")
    assert norm(got) == norm([str(a / ("ssh" + suffix)), str(b / ("ssh" + suffix))])
    P._worked["ssh"] = got[1]
    assert P._exes("ssh")[0] == got[1]


def test_exe_prefers_an_explicit_path(tmp_path, monkeypatch):
    suffix = ".exe" if os.name == "nt" else ""
    (tmp_path / ("ssh" + suffix)).write_text("", encoding="utf-8")
    monkeypatch.setenv("EDGELOG_SSH_DIR", str(tmp_path))
    assert P._exe("ssh") == os.path.join(str(tmp_path), "ssh" + suffix)
    # nothing at the override: falls through to the next explicit path / PATH, never raises
    monkeypatch.setenv("EDGELOG_SSH_DIR", str(tmp_path / "nowhere"))
    assert P._exe("ssh")


def test_run_closes_stdin_and_opens_no_console(monkeypatch):
    seen = {}

    def run(args, **kw):
        seen.update(kw)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(P.subprocess, "run", run)
    P._ssh("true")
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["capture_output"] is True
    if os.name == "nt":
        assert seen["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)

# -- apply notes (2026-10-05): the run's deadline, keep-alives, an unreadable checksum ---------
def test_ssh_keepalives_end_a_dead_link_in_about_a_minute():
    opts = " ".join(P.SSH_OPTS)
    assert "ServerAliveInterval=15" in opts and "ServerAliveCountMax=4" in opts


def test_an_unreadable_checksum_says_so_and_does_not_claim_a_removal(box_env):
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "sha_tmp": [(255, "", "Connection reset by peer")],
        "rm": [(255, "", "Connection reset by peer")],
    })
    assert rc == 1
    assert box.calls.count("sha_tmp") == 3
    assert ("FAIL could not read the uploaded file's checksum after 3 tries: "
            "rc=255: Connection reset by peer") in log
    assert "temp file may still be there" in log
    assert "checksum mismatch" not in log and "temp file removed" not in log
    assert "mv" not in box.calls


def test_a_real_mismatch_still_logs_a_mismatch_and_the_removal(box_env):
    rc, box, log = box_env.go({
        "sha_final": [(0, "old\n", "")],
        "sha_tmp": [(0, "deadbeef\n", "")],
        "rm": [(0, "", "")],
    })
    assert rc == 1
    assert "FAIL checksum mismatch after upload; temp file removed" in log


def test_retries_stop_before_the_task_limit_and_the_last_line_is_a_fail(box_env, monkeypatch):
    """The scheduled task is killed at 30 minutes. A stalled upload must not leave the log
    ending on a RETRY line: near the run's deadline it stops retrying and logs the FAIL."""
    clock = {"t": 0.0}
    monkeypatch.setattr(P, "_clock", lambda: clock["t"])

    def slow_scp_box(script):
        box = _Box(script)
        real = box.run

        def run(args, timeout):
            if box.kind(args) == "scp":
                clock["t"] += timeout          # the upload stalls for its whole timeout
                box.calls.append("scp")
                raise subprocess.TimeoutExpired(cmd="scp", timeout=timeout)
            return real(args, timeout)
        return box, run

    box, run = slow_scp_box({"sha_final": [(0, "old\n", "")]})
    monkeypatch.setattr(P, "_run", run)
    monkeypatch.setattr(P, "_sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    rc = P.main(["--local", str(box_env_local(box_env)), "--no-refresh"])
    log = open(P.LOG_PATH, encoding="utf-8").read()
    assert rc == 1
    last = log.strip().splitlines()[-1]
    assert "FAIL scp after" in last and "time limit is near" in last, last
    assert clock["t"] <= P.RUN_DEADLINE_SEC, "nothing ran past the run's deadline"
    assert P._deadline["at"] is None, "the deadline belongs to one run only"


def box_env_local(env):
    """The master file box_env made (its fixture writes it next to the log)."""
    return os.path.join(os.path.dirname(P.LOG_PATH), "NOADJ_NQ_5m_RTH.csv")
