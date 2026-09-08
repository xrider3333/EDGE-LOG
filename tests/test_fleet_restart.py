"""tools/fleet_restart.py - keep-aware runner-set restart, pure parts only (no processes)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import tools.fleet_restart as fr  # noqa: E402

PY = "python3.13.exe"
RUNNER = "python.exe -u -m api.runner --firestore --cred serviceAccount.json --watch"


def _rows():
    """A realistic snapshot: the bat's cmd -> primary python; four `cmd /c "set
    EDGELOG_WORKER=N && ..."` wrappers -> worker pythons; plus a bash shell whose own
    command line mentions api.runner (must never count as a runner)."""
    rows = [
        {"pid": 100, "ppid": 1, "name": "cmd.exe", "cmd": 'cmd /c ""C:\\EdgeLog\\_restart_runner.bat""'},
        {"pid": 101, "ppid": 100, "name": PY, "cmd": RUNNER + " --refresh-min 240 --interval 30"},
        {"pid": 900, "ppid": 1, "name": "bash.exe", "cmd": "bash -c 'grep api.runner runner.log'"},
    ]
    for n in (2, 3, 4, 5):
        rows.append({"pid": 200 + n, "ppid": 1, "name": "cmd.exe",
                     "cmd": 'cmd /c "set EDGELOG_WORKER=%d && set AUGUR_TRIAL_CACHE=1 && '
                            'python -u -m api.runner --firestore >> C:\\EdgeLog\\runner_worker%d.log 2>&1"'
                            % (n, n)})
        rows.append({"pid": 300 + n, "ppid": 200 + n, "name": PY,
                     "cmd": RUNNER + " --interval 12 --refresh-min 0 --trades-sec 0"})
    return rows


def test_classify_roles_come_from_the_parent_wrapper():
    inv = fr.classify(_rows())
    roles = {r["pid"]: r["role"] for r in inv}
    assert roles == {101: "primary", 302: "worker 2", 303: "worker 3", 304: "worker 4",
                     305: "worker 5"}
    # the bash shell that merely mentions api.runner is not a runner
    assert 900 not in roles
    # primary sorts first
    assert inv[0]["role"] == "primary"


def test_parse_keep():
    assert fr.parse_keep(None) == set()
    assert fr.parse_keep("") == set()
    assert fr.parse_keep("2") == {"2"}
    assert fr.parse_keep("2, 3,primary") == {"2", "3", "primary"}
    assert fr.parse_keep("Primary 4") == {"primary", "4"}
    with pytest.raises(SystemExit):
        fr.parse_keep("worker2")


def test_plan_full_restart_kills_all_and_launches_all_workers():
    p = fr.plan(fr.classify(_rows()), set(), 4)
    assert sorted(p["kill"]) == [101, 302, 303, 304, 305]
    assert p["launch"] == [2, 3, 4, 5]
    assert p["keep_primary"] is False


def test_plan_keep_worker_2_spares_its_pid_and_slot():
    p = fr.plan(fr.classify(_rows()), {"2"}, 4)
    assert sorted(p["kill"]) == [101, 303, 304, 305]
    assert p["launch"] == [3, 4, 5]
    assert p["keep_primary"] is False


def test_plan_keep_primary_signals_the_bat():
    p = fr.plan(fr.classify(_rows()), {"primary", "5"}, 4)
    assert sorted(p["kill"]) == [302, 303, 304]
    assert p["launch"] == [2, 3, 4]
    assert p["keep_primary"] is True


def test_plan_kept_number_with_no_live_worker_is_launched():
    rows = [r for r in _rows() if r["pid"] not in (202, 302)]   # worker 2 is dead
    p = fr.plan(fr.classify(rows), {"2"}, 4)
    assert 2 in p["launch"]                    # keep protects a live process only
    assert sorted(p["kill"]) == [101, 303, 304, 305]


def test_plan_keep_primary_with_no_primary_alive_launches_normally():
    rows = [r for r in _rows() if r["pid"] not in (100, 101)]
    p = fr.plan(fr.classify(rows), {"primary"}, 4)
    assert p["keep_primary"] is False          # nothing alive to keep -> bat launches one


def test_run_helper_uses_plan_and_returns_3_when_primary_kept(monkeypatch):
    killed, launched = [], []
    monkeypatch.setattr(fr, "live_rows", _rows)
    monkeypatch.setattr(fr, "kill_pid", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(fr, "launch_worker", lambda n: launched.append(n))
    monkeypatch.setattr(fr.time, "sleep", lambda s: None)
    monkeypatch.setattr(fr, "LOG_PATH", os.devnull)
    rc = fr.run_helper({"primary", "2"}, 4)
    assert rc == 3
    assert sorted(killed) == [303, 304, 305]
    assert launched == [3, 4, 5]


def test_run_helper_full_restart_returns_0(monkeypatch):
    killed, launched = [], []
    monkeypatch.setattr(fr, "live_rows", _rows)
    monkeypatch.setattr(fr, "kill_pid", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(fr, "launch_worker", lambda n: launched.append(n))
    monkeypatch.setattr(fr.time, "sleep", lambda s: None)
    monkeypatch.setattr(fr, "LOG_PATH", os.devnull)
    assert fr.run_helper(set(), 4) == 0
    assert sorted(killed) == [101, 302, 303, 304, 305]
    assert launched == [2, 3, 4, 5]


def test_main_helper_reads_env(monkeypatch):
    seen = {}
    monkeypatch.setenv("EDGELOG_KEEP", "2,primary")
    monkeypatch.setenv("EDGELOG_WORKERS", "4")
    monkeypatch.setattr(fr, "run_helper", lambda keep, n: seen.update(keep=keep, n=n) or 0)
    assert fr.main(["--helper"]) == 0
    assert seen == {"keep": {"2", "primary"}, "n": 4}
