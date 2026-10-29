import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import auto_recovery as ar  # noqa: E402

NOW = datetime.datetime(2026, 10, 29, 6, 0)


def _job(tmp_path, name, cmd, log_text, age_h=1.0):
    d = tmp_path / "detach"
    d.mkdir(exist_ok=True)
    log = tmp_path / (name + ".log")
    log.write_text(log_text, encoding="utf-8")
    (d / (name + ".cmd")).write_text(
        '@echo off\r\ncd /d "C:\repo"\r\n'
        'echo [detach] %%DATE%% %%TIME%% start: %s>> "%s"\r\n'
        '%s >> "%s" 2>&1\r\n'
        'echo [detach] %%DATE%% %%TIME%% exit %%ERRORLEVEL%%>> "%s"\r\n' % (cmd, log, cmd, log, log), encoding="ascii")
    t = (NOW - datetime.timedelta(hours=age_h)).timestamp()
    os.utime(log, (t, t))
    os.utime(d / (name + ".cmd"), (t, t))
    return str(d)


def _states(d):
    return {r["name"]: (r["state"], r.get("relaunch")) for r in ar.scan(days=3, stale_h=6, now=NOW, detach_dir=d)}


def test_landed_ship_is_ok_and_killed_ship_is_dead_with_relaunch(tmp_path):
    _job(tmp_path, "a", "python -u tools/wt.py ship wa", "[detach] x start: s\npushed (verified on main): abc\n[detach] y exit \n")
    d = _job(tmp_path, "b", "python -u tools/wt.py ship wb", "[detach] x start: s\nPRE-LOCK\n[detach] y exit 1073807364\n")
    s = _states(d)
    assert s["a"][0] == "OK"
    assert s["b"][0] == "DIED" and "detach.py b" in s["b"][1] and "wt.py ship wb" in s["b"][1]


def test_failed_exit_code_stale_ship_and_running(tmp_path):
    _job(tmp_path, "c", "python job.py", "[detach] x start: s\nTraceback boom\n[detach] y exit 1\n")
    _job(tmp_path, "d", "python -u tools/wt.py ship wd", "[detach] x start: s\nwaiting for the push lock\n", age_h=10)
    d = _job(tmp_path, "e", "python -u tools/wt.py ship we", "[detach] x start: s\ngates\n", age_h=0.5)
    s = _states(d)
    assert s["c"][0] == "FAILED" and s["d"][0] == "DIED" and s["e"][0] == "RUNNING"


def test_superseded_by_a_later_landing_and_only_newest_launch_counts(tmp_path):
    _job(tmp_path, "f1", "python -u tools/wt.py ship wf", "[detach] x start: s\n[detach] y exit 1\n", age_h=5)
    _job(tmp_path, "f2", "python -u tools/wt.py ship wf", "[detach] x start: s\npushed (verified on main): z\n", age_h=1)
    # an old failure followed by a new launch that landed, in ONE log
    d = _job(tmp_path, "g", "python -u tools/wt.py ship wg",
             "[detach] a start: s\n[detach] b exit 1\n[detach] c start: s\npushed (verified on main): q\n")
    s = _states(d)
    assert s["f1"] == ("SUPERSEDED", None) and s["f2"][0] == "OK" and s["g"][0] == "OK"


def test_quiet_old_nonship_is_unknown_not_dead_and_digest_lists_bad_only(tmp_path):
    _job(tmp_path, "h", "python long_study.py", "progress 1\nprogress 2\n", age_h=30)
    d = _job(tmp_path, "i", "python other.py", "[detach] x start: s\n[detach] y exit 2\n")
    rows = ar.scan(days=3, stale_h=6, now=NOW, detach_dir=d)
    L = "\n".join(ar.digest_lines(rows))
    assert "FAILED **i**" in L and "**h**" not in L and "may have finished): h" in L


def test_old_launchers_outside_the_window_are_skipped(tmp_path):
    d = _job(tmp_path, "old", "python x.py", "[detach] y exit 1\n", age_h=24 * 5)
    assert ar.scan(days=3, now=NOW, detach_dir=d) == []
