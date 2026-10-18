"""tools/pull_box_ledgers.py -- the box ledger backup to the PC (2026-10-16 rewrite).

The 10-15 14:45 MST scheduled run died SILENTLY: one of 19 per-file scp connections stalled past
its 120 s timeout, the uncaught TimeoutExpired killed the run before it logged, and the PC monitor
only saw the backup go 36 h stale. These tests pin the rewrite: one ssh connection carrying a tar
of the files that exist, bounded tries on two clients, and ALWAYS one OK/FAIL line -- which is all
the monitor (tools/webull_freshness_pc.check_ledger_pull) reads. They replace c3d3d373's per-file scp
tests; its two promises hold here too: a hung try is retried and the night can still be OK
(test_a_failed_client_goes_at_once_to_the_other_one, test_one_client_only_still_gets_a_late_retry), and
a copy that keeps hanging is a logged FAIL naming the cause, with files not on the box listed as
missing (test_every_try_timing_out_logs_fail_and_exits_1_never_silent,
test_a_file_not_on_the_box_yet_is_listed_as_missing_and_the_night_is_still_ok).
"""
import datetime as _dt
import io
import os
import subprocess
import sys
import tarfile

import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import pull_box_ledgers as pb  # noqa: E402

FAKE_CLIENTS = [r"C:\Windows\System32\OpenSSH\ssh.exe", r"C:\Program Files\Git\usr\bin\ssh.exe"]


def _tar(files, extra=None):
    """A tar stream like the box sends: {name: bytes}; `extra` = raw TarInfo members to add."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in files.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        for ti, data in (extra or []):
            tf.addfile(ti, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


def _all_files(skip=()):
    return {f: f"content of {f}\n".encode() for f in pb.FILES if f not in skip}


class Box:
    """Stands in for _run: each call pops the next scripted outcome (a CompletedProcess, an
    exception to raise) and records the client used."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, args, timeout):
        self.calls.append((args[0], timeout, args))
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out


def _ok(stream, missing=(), rc=0, extra_err=""):
    err = "".join(f"{pb.MISSING_TAG}{m}\n" for m in missing) + extra_err
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stream,
                                       stderr=err.encode())


@pytest.fixture
def env(tmp_path, monkeypatch):
    log = tmp_path / "logs" / "pull_box_ledgers.log"
    monkeypatch.setattr(pb, "LOG_PATH", str(log))
    monkeypatch.setattr(pb, "_find_clients", lambda: list(FAKE_CLIENTS))
    sleeps = []
    monkeypatch.setattr(pb.time, "sleep", lambda s: sleeps.append(s))
    dest = tmp_path / "box_backup"

    class E:
        pass
    e = E()
    e.log, e.dest, e.sleeps = log, dest, sleeps
    e.lines = lambda: log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    e.run = lambda: pb.main(["--dest", str(dest)])

    def use(box):
        monkeypatch.setattr(pb, "_run", box)
        return box
    e.use = use
    return e


def _run_dirs(dest):
    return sorted(p for p in dest.iterdir() if p.is_dir()) if dest.exists() else []


def _result_words(lines):
    return [ln.split()[2] for ln in lines]


# -- the normal night ---------------------------------------------------------------------------
def test_every_listed_file_arrives_byte_exact_over_one_connection(env):
    files = _all_files()
    box = env.use(Box(_ok(_tar(files))))
    assert env.run() == 0
    assert len(box.calls) == 1, "one ssh connection for all files, not one per file"
    (run_dir,) = _run_dirs(env.dest)
    for name, data in files.items():
        assert (run_dir / name).read_bytes() == data
    words = _result_words(env.lines())
    assert words[0] == "START" and words[-1] == "OK"
    assert f"OK copied {len(pb.FILES)}/{len(pb.FILES)}" in env.lines()[-1]
    assert "Windows OpenSSH" in env.lines()[-1]


def test_the_one_call_is_read_only_ssh_with_bounded_time_and_keepalives(env):
    box = env.use(Box(_ok(_tar(_all_files()))))
    env.run()
    client, timeout, args = box.calls[0]
    assert client == FAKE_CLIENTS[0] and timeout == pb.TRY_TIMEOUT_SEC
    assert "BatchMode=yes" in args and "ServerAliveInterval=15" in args
    cmd = args[-1]
    assert cmd.startswith(f"cd {pb.REMOTE_HOME} ") and cmd.endswith("tar -chf - -T -")
    assert "\n" not in cmd
    for verb in (" rm ", " mv ", " > ", ">>", " cp ", "truncate", "sed -i"):
        assert verb not in cmd, f"the box side must stay read-only: {verb!r} in {cmd!r}"
    for f in pb.FILES:
        assert f in cmd


def test_a_file_not_on_the_box_yet_is_listed_as_missing_and_the_night_is_still_ok(env):
    gone = "cloud_signal/keel/DIP_424K_v12_summary.json"
    env.use(Box(_ok(_tar(_all_files(skip=[gone])), missing=[gone])))
    assert env.run() == 0
    last = env.lines()[-1]
    assert last.split()[2] == "OK" and f"missing on box: {gone}" in last


def test_tar_exit_1_file_grew_while_read_is_still_a_good_copy_and_is_noted(env):
    env.use(Box(_ok(_tar(_all_files()), rc=1, extra_err="tar: qqq_exec/orders.csv: file changed as we read it\n")))
    assert env.run() == 0
    last = env.lines()[-1]
    assert last.split()[2] == "OK" and "grew while read (kept): qqq_exec/orders.csv" in last


# -- whole copies only (review 2026-10-18) --------------------------------------------------------
SHRANK = "tar: qqq_exec/orders.csv: File shrank by 120 bytes; padding with zeros\n"


def test_a_file_that_shrank_while_read_is_retried_and_the_clean_copy_kept(env):
    padded = _all_files()
    padded["qqq_exec/orders.csv"] = b"half a rewrite" + b"\0" * 120
    clean = _all_files()
    box = env.use(Box(_ok(_tar(padded), rc=1, extra_err=SHRANK), _ok(_tar(clean))))
    assert env.run() == 0
    assert len(box.calls) == 2
    (run_dir,) = _run_dirs(env.dest)
    assert (run_dir / "qqq_exec" / "orders.csv").read_bytes() == clean["qqq_exec/orders.csv"]
    assert any(ln.split()[2] == "TRY" and "File shrank" in ln for ln in env.lines())


def test_a_file_that_shrank_on_every_try_is_never_saved_and_fails_the_night(env):
    padded = _all_files()
    padded["qqq_exec/orders.csv"] = b"torn" + b"\0" * 120
    env.use(Box(*[_ok(_tar(padded), rc=1, extra_err=SHRANK) for _ in range(3)]))
    assert env.run() == 1
    (run_dir,) = _run_dirs(env.dest)
    assert not (run_dir / "qqq_exec" / "orders.csv").exists(), "a zero-padded copy is never saved"
    assert (run_dir / "qqq_exec" / "trades.csv").exists(), "the other 18 are still kept"
    last = env.lines()[-1]
    assert last.split()[2] == "FAIL" and "FAILED: qqq_exec/orders.csv (File shrank" in last
    assert f"copied {len(pb.FILES) - 1}/{len(pb.FILES)}" in last


def test_tar_exit_2_for_one_unreadable_file_keeps_the_other_18_and_fails_loudly(env):
    bad = "webull_orders/config.json"
    err = f"tar: {bad}: Cannot open: Permission denied\ntar: Exiting with failure status due to previous errors\n"
    env.use(Box(*[_ok(_tar(_all_files(skip=[bad])), rc=2, extra_err=err) for _ in range(3)]))
    assert env.run() == 1
    (run_dir,) = _run_dirs(env.dest)
    assert not (run_dir / "webull_orders" / "config.json").exists()
    assert (run_dir / "qqq_exec" / "state.json").exists()
    last = env.lines()[-1]
    assert last.split()[2] == "FAIL" and f"FAILED: {bad} (Cannot open" in last


def test_tar_exit_2_naming_no_listed_file_is_a_failed_try(env):
    env.use(Box(*[_ok(_tar(_all_files()), rc=2, extra_err="tar: -: Cannot write: Broken pipe\n")
                  for _ in range(3)]))
    assert env.run() == 1
    assert env.lines()[-1].split()[2] == "FAIL" and _run_dirs(env.dest) == []


def test_an_unreadable_file_or_folder_on_the_box_fails_the_night_not_missing(env):
    bad = "cloud_signal/shadow/state.json"
    env.use(Box(_ok(_tar(_all_files(skip=[bad])),
                    extra_err=f"{pb.UNREADABLE_TAG}{bad}\n")))
    assert env.run() == 1
    last = env.lines()[-1]
    assert "missing on box" not in last
    assert f"FAILED: {bad} (unreadable on the box)" in last


class _FixedNow:
    """Stands in for the module's datetime alias so every run lands in one same-minute folder."""
    timedelta = _dt.timedelta

    class datetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(2026, 10, 18, 11, 50, 7)


def test_a_failed_run_never_deletes_a_same_minute_earlier_copy(env, monkeypatch):
    monkeypatch.setattr(pb, "_dt", _FixedNow)
    earlier = env.dest / "2026-10-18_1150" / "qqq_exec"
    earlier.mkdir(parents=True)
    (earlier / "trades.csv").write_bytes(b"the earlier good copy")
    env.use(Box(_ok(b"garbage, not a tar" * 40)))
    assert env.run() == 1
    assert (earlier / "trades.csv").read_bytes() == b"the earlier good copy"
    assert [p.name for p in env.dest.iterdir()] == ["2026-10-18_1150"], "no .partial left behind"


def test_a_same_minute_rerun_replaces_shared_files_and_keeps_the_rest(env, monkeypatch):
    monkeypatch.setattr(pb, "_dt", _FixedNow)
    run_dir = env.dest / "2026-10-18_1150"
    (run_dir / "qqq_exec").mkdir(parents=True)
    (run_dir / "qqq_exec" / "trades.csv").write_bytes(b"older")
    (run_dir / "qqq_exec" / "only_in_the_earlier_run.txt").write_bytes(b"keep me")
    files = _all_files()
    env.use(Box(_ok(_tar(files))))
    assert env.run() == 0
    assert (run_dir / "qqq_exec" / "trades.csv").read_bytes() == files["qqq_exec/trades.csv"]
    assert (run_dir / "qqq_exec" / "only_in_the_earlier_run.txt").read_bytes() == b"keep me"


def test_prune_never_counts_or_keeps_a_staging_folder(tmp_path):
    for d in ["2026-10-0%d_1445" % i for i in range(1, 6)] + ["2026-10-05_1445.partial"]:
        (tmp_path / d).mkdir()
    pb._prune(str(tmp_path), 3)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["2026-10-03_1445", "2026-10-04_1445", "2026-10-05_1445",
                    "2026-10-05_1445.partial"]


# -- the box-side shell line, run for real where bash + tar exist ---------------------------------
def _bash():
    import shutil as _sh
    for c in (r"C:\Program Files\Git\bin\bash.exe", _sh.which("bash")):
        if c and os.path.isfile(c) and "system32" not in c.lower():
            return c
    return None


@pytest.mark.skipif(_bash() is None, reason="no bash with tar on this machine")
def test_the_remote_command_lists_missing_files_and_streams_the_rest(tmp_path):
    home = tmp_path / "edgelog"
    files = ["qqq_exec/trades.csv", "qqq_exec/gone.csv", "nofolder/x.json", "cloud_signal/a b.json"]
    (home / "qqq_exec").mkdir(parents=True)
    (home / "cloud_signal").mkdir()
    (home / "qqq_exec" / "trades.csv").write_bytes(b"t1\nt2\n")
    (home / "cloud_signal" / "a b.json").write_bytes(b"{}")
    cmd = pb.remote_command(files, home=str(home).replace("\\", "/"))
    r = subprocess.run([_bash(), "-c", cmd], capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr
    err = r.stderr.decode()
    assert pb._tagged(err, pb.MISSING_TAG) == ["qqq_exec/gone.csv", "nofolder/x.json"]
    assert pb._tagged(err, pb.UNREADABLE_TAG) == []
    out = tmp_path / "out"
    written = pb.unpack(r.stdout, str(out), files=files)
    assert written == {"qqq_exec/trades.csv", "cloud_signal/a b.json"}
    assert (out / "qqq_exec" / "trades.csv").read_bytes() == b"t1\nt2\n"
    assert not list(home.rglob("*.tar")), "nothing is written on the box side"


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs POSIX permissions and a non-root user")
def test_the_remote_command_calls_an_unsearchable_folder_unreadable(tmp_path):
    home = tmp_path / "edgelog"
    (home / "locked").mkdir(parents=True)
    (home / "locked" / "x.csv").write_bytes(b"x")
    (home / "locked").chmod(0)
    try:
        cmd = pb.remote_command(["locked/x.csv"], home=str(home))
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=60)
        assert pb._tagged(r.stderr.decode(), pb.UNREADABLE_TAG) == ["locked/x.csv"]
    finally:
        (home / "locked").chmod(0o755)


def test_a_listed_file_absent_from_the_stream_without_a_missing_line_fails_the_night(env):
    lost = "qqq_exec/broker_orders.csv"
    env.use(Box(_ok(_tar(_all_files(skip=[lost])))))
    assert env.run() == 1
    last = env.lines()[-1]
    assert last.split()[2] == "FAIL" and f"FAILED: {lost}" in last


# -- the 10-15 failure: a stall must end in a logged FAIL ----------------------------------------
def test_every_try_timing_out_logs_fail_and_exits_1_never_silent(env):
    box = env.use(Box(*[subprocess.TimeoutExpired(cmd="ssh", timeout=pb.TRY_TIMEOUT_SEC)] * 3))
    assert env.run() == 1
    lines = env.lines()
    words = _result_words(lines)
    assert words[0] == "START" and words.count("TRY") == 3 and words[-1] == "FAIL"
    assert "timed out" in lines[-1]
    assert [c for c, _t, _a in box.calls] == [FAKE_CLIENTS[0], FAKE_CLIENTS[1], FAKE_CLIENTS[0]]
    assert env.sleeps == [pb.RETRY_DELAY_SEC]
    assert _run_dirs(env.dest) == [], "a failed night leaves no empty dated folder behind"


def test_the_worst_case_fits_inside_the_scheduled_tasks_15_minute_limit():
    tries = pb._attempts(FAKE_CLIENTS)
    worst = sum(d for _c, d in tries) + len(tries) * pb.TRY_TIMEOUT_SEC
    assert worst < 15 * 60 - 60


def test_a_failed_client_goes_at_once_to_the_other_one(env):
    box = env.use(Box(_ok(b"", rc=255, extra_err="ssh: connect to host: Connection timed out\n"),
                      _ok(_tar(_all_files()))))
    assert env.run() == 0
    assert [c for c, _t, _a in box.calls] == FAKE_CLIENTS
    assert env.sleeps == []
    lines = env.lines()
    assert any(ln.split()[2] == "TRY" and "rc=255" in ln and "Connection timed out" in ln
               for ln in lines)
    assert "Git ssh" in lines[-1] and lines[-1].split()[2] == "OK"


def test_a_client_that_cannot_start_is_a_failed_try_not_a_crash(env):
    env.use(Box(FileNotFoundError("ssh.exe"), _ok(_tar(_all_files()))))
    assert env.run() == 0


def test_one_client_only_still_gets_a_late_retry(env, monkeypatch):
    monkeypatch.setattr(pb, "_find_clients", lambda: ["ssh"])
    box = env.use(Box(subprocess.TimeoutExpired(cmd="ssh", timeout=1), _ok(_tar(_all_files()))))
    assert env.run() == 0
    assert len(box.calls) == 2 and env.sleeps == [pb.RETRY_DELAY_SEC]


def test_a_garbled_stream_is_a_logged_fail_and_leaves_no_folder(env):
    env.use(Box(_ok(b"this is not a tar stream" * 50)))
    assert env.run() == 1
    assert env.lines()[-1].split()[2] == "FAIL" and "could not be read" in env.lines()[-1]
    assert _run_dirs(env.dest) == []


def test_a_truncated_stream_is_never_written_as_a_short_file(env):
    whole = _tar(_all_files())
    env.use(Box(_ok(whole[: len(whole) // 3])))
    assert env.run() == 1
    assert env.lines()[-1].split()[2] == "FAIL"
    assert _run_dirs(env.dest) == []


def test_anything_not_listed_in_the_stream_is_never_written(env, tmp_path):
    evil = tarfile.TarInfo("../../escaped.txt")
    evil.size = 4
    absolute = tarfile.TarInfo("/etc/evil.txt")
    absolute.size = 4
    link = tarfile.TarInfo("qqq_exec/trades.csv.lnk")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    unlisted = tarfile.TarInfo("qqq_exec/secret_extra.json")
    unlisted.size = 4
    stream = _tar(_all_files(), extra=[(evil, b"evil"), (absolute, b"evil"), (link, None),
                                       (unlisted, b"evil")])
    env.use(Box(_ok(stream)))
    assert env.run() == 0
    (run_dir,) = _run_dirs(env.dest)
    written = sorted(str(p.relative_to(run_dir)).replace("\\", "/")
                     for p in run_dir.rglob("*") if p.is_file())
    assert written == sorted(pb.FILES)
    assert not (tmp_path / "escaped.txt").exists()


def test_a_listed_name_that_arrives_as_a_link_is_not_followed(env):
    link = tarfile.TarInfo("qqq_exec/trades.csv")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    env.use(Box(_ok(_tar(_all_files(skip=["qqq_exec/trades.csv"]), extra=[(link, None)]))))
    assert env.run() == 1
    assert "FAILED: qqq_exec/trades.csv" in env.lines()[-1]


def test_any_unexpected_crash_is_logged_as_fail(env, monkeypatch):
    env.use(Box(_ok(_tar(_all_files()))))

    def boom(*a, **k):
        raise PermissionError("disk says no")
    monkeypatch.setattr(pb, "unpack", boom)
    assert env.run() == 1
    assert env.lines()[-1].split()[2] == "FAIL"


def test_a_crash_finding_the_clients_is_still_logged(env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("clients exploded")
    monkeypatch.setattr(pb, "_find_clients", boom)
    assert env.run() == 1
    assert env.lines()[-1].split()[2] == "FAIL"


def test_a_crash_no_pull_step_catches_reaches_mains_catch_all_and_is_logged(env, monkeypatch):
    env.use(Box(_ok(_tar(_all_files()))))

    def boom(*a, **k):
        raise ValueError("prune exploded")
    monkeypatch.setattr(pb, "_prune", boom)
    assert env.run() == 1
    last = env.lines()[-1]
    assert last.split()[2] == "FAIL" and "crashed: ValueError: prune exploded" in last


def test_dry_run_touches_nothing(env):
    box = env.use(Box())
    assert pb.main(["--dest", str(env.dest), "--dry-run"]) == 0
    assert box.calls == [] and _run_dirs(env.dest) == []
    assert env.lines()[-1].split()[2] == "DRY-RUN"


# -- the monitor reads only OK / FAIL ------------------------------------------------------------
def test_the_monitor_ignores_start_and_try_lines_and_sees_the_result(tmp_path):
    from tools import webull_freshness_pc as wpc
    tz = _dt.timezone(_dt.timedelta(hours=-7))
    now = _dt.datetime(2026, 10, 16, 12, 0, tzinfo=tz)
    log = tmp_path / "pull.log"
    log.write_text(
        "2026-10-16 11:40:00 FAIL copied 0/19 into C:\\x; try 1 ...: timed out after 180 s\n"
        "2026-10-16 11:50:09 OK copied 19/19 into C:\\x via Git ssh (y)\n"
        "2026-10-16 11:55:00 START pulling 19 file(s) from host over one ssh connection\n"
        "2026-10-16 11:55:05 TRY 1 failed via Windows OpenSSH (x): rc=255: boom\n",
        encoding="utf-8")
    (v,) = wpc.check_ledger_pull(str(log), now, local_tz=tz)
    assert v["ok"] is True, "START / TRY lines after the newest OK are not results"
    log.write_text(
        "2026-10-16 11:50:09 OK copied 19/19 into C:\\x via Git ssh (y)\n"
        "2026-10-16 11:55:00 START pulling 19 file(s) from host over one ssh connection\n"
        "2026-10-16 11:58:00 FAIL copied 0/19 into C:\\x; try 1 ...: timed out after 180 s\n",
        encoding="utf-8")
    (v,) = wpc.check_ledger_pull(str(log), now, local_tz=tz)
    assert v["ok"] is False
