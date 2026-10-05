"""Unit tests for tools/nt8_freshness_sweep.py - the NT8 paper pipeline silent-failure sweep (2026-10-05)."""
import datetime as dt
import json

from tools import nt8_freshness_sweep as S

NOW = dt.datetime(2026, 10, 5, 10, 0)


def test_failed_task_and_stale_task_are_failures():
    tasks = [
        {"name": "EdgeLog push NQ master to box", "enabled": True, "last": NOW, "result": 1},
        {"name": "EdgeLog NT recover watchdog", "enabled": True, "last": NOW - dt.timedelta(hours=2), "result": 0},
        {"name": "EdgeLog NT 10s import", "enabled": True, "last": NOW, "result": 267009},
        {"name": "EdgeLog nightly backup", "enabled": False, "last": None, "result": 5},
    ]
    out = {i["id"]: i["status"] for i in S.check_tasks(NOW, tasks)}
    assert out == {"task:EdgeLog push NQ master to box": "fail", "task:EdgeLog NT recover watchdog": "fail"}


def test_box_push_failed_line_is_a_failure(tmp_path):
    p = tmp_path / "push.log"
    p.write_text("2026-10-02T21:00:01 OK pushed\n2026-10-03T21:00:01 FAIL ssh timeout\n")
    assert S.check_box_push(NOW, str(p))[0]["status"] == "fail"
    p.write_text("2026-10-05T07:23:00 OK pushed\n")
    assert S.check_box_push(NOW, str(p))[0]["status"] == "pass"


def _snap(root, day, ids):
    (root / day).mkdir()
    (root / day / "edgelog_strategy_rows.json").write_text(json.dumps([{"Id": i} for i in ids]))


def test_backup_missing_a_roster_row_names_the_last_complete_snapshot(tmp_path):
    _snap(tmp_path, "2026-10-01", [386606468, 386606474])
    _snap(tmp_path, "2026-10-03", [386606474])
    items = S.check_nt_backup(NOW, str(tmp_path))
    assert [i["id"] for i in items] == ["nt_backup_rows"]
    assert "EdgeLogNOISE" in items[0]["detail"] and "2026-10-01" in items[0]["detail"]


def test_backup_too_old_fails_and_fresh_complete_passes(tmp_path):
    _snap(tmp_path, "2026-09-30", [386606468, 386606474])
    assert S.check_nt_backup(NOW, str(tmp_path))[0]["id"] == "nt_backup_age"
    _snap(tmp_path, "2026-10-05", [386606468, 386606474])
    assert S.check_nt_backup(NOW, str(tmp_path))[0]["status"] == "pass"


def test_daytime_backup_runs_once_after_the_halt_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EL", str(tmp_path))
    calls = []
    run = lambda: calls.append(1) or "done"
    assert S.maybe_backup(dt.datetime(2026, 10, 5, 14, 0), run) is None
    assert S.maybe_backup(dt.datetime(2026, 10, 5, 14, 5), run) == "done"
    (tmp_path / "_ntbackup" / "2026-10-05").mkdir(parents=True)
    assert S.maybe_backup(dt.datetime(2026, 10, 5, 16, 0), run) is None
    assert calls == [1]


def test_alert_posts_on_change_and_repeats_only_after_six_hours():
    bad = [S._item("box_push", "fail", "x", "y"), S._item("tasks", "pass", "x", "y")]
    alert, st = S.decide_alert(bad, {}, 1000)
    assert alert and st == {"set": ["box_push"], "at": 1000}
    assert S.decide_alert(bad, st, 1000 + 3600)[0] is False
    assert S.decide_alert(bad, st, 1000 + S.REPEAT_SEC)[0] is True
    alert, st2 = S.decide_alert([S._item("tasks", "pass", "x", "y")], st, 2000)
    assert not alert and st2 == {"set": [], "at": 0}


def test_cme_hours():
    E = S.ET
    assert S.cme_open(dt.datetime(2026, 10, 5, 10, 0, tzinfo=E))
    assert not S.cme_open(dt.datetime(2026, 10, 5, 17, 30, tzinfo=E))
    assert not S.cme_open(dt.datetime(2026, 10, 3, 12, 0, tzinfo=E))
    assert S.cme_open(dt.datetime(2026, 10, 4, 18, 30, tzinfo=E))
