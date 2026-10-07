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


def test_december_roll_watch_warns_until_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EL", str(tmp_path))
    assert S.check_roll_watch(dt.datetime(2026, 12, 6, 9, 0)) == []
    assert S.check_roll_watch(dt.datetime(2026, 12, 10, 9, 0))[0]["status"] == "warn"
    (tmp_path / "enguq_dec_roll_checked").write_text("ok")
    assert S.check_roll_watch(dt.datetime(2026, 12, 10, 9, 0)) == []


# ── 2026-10-07: plain phone text, no echoes, once-a-day repeats ("make the notifications simpler") ──────────
import time as _time

from api import ntfy_push as N


def _tasks(result, name="EdgeLog NT readiness", last=None):
    return [{"name": name, "enabled": True, "last": last or NOW, "result": result}]


def test_readiness_exit_code_1_is_ran_and_reported_not_a_failure():
    # tools/nt_readiness.py exits 1 when it FOUND problems (and pushed them itself): not a task failure
    out = S.check_tasks(NOW, _tasks(1))
    assert [i["status"] for i in out] == ["pass"]


def test_readiness_other_codes_and_staleness_are_still_failures():
    assert S.check_tasks(NOW, _tasks(2))[0]["status"] == "fail"                         # a crash
    assert S.check_tasks(NOW, _tasks(-1073741510))[0]["status"] == "fail"               # killed
    stale = S.check_tasks(NOW, _tasks(1, last=NOW - dt.timedelta(hours=90)))            # did not run when due
    assert stale[0]["status"] == "fail" and "more than 80 h ago" in stale[0]["detail"]
    # and the exemption is only for the readiness task
    other = S.check_tasks(NOW, _tasks(1, name="EdgeLog nightly backup"))
    assert other[0]["status"] == "fail"


def _capture_csv(path, now_ts, n=360, classified=0.46, rt_blind=False, last_age=0):
    """n traded 10s bars ending last_age seconds before now; `classified` share carries buy/sell."""
    lines = ["time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt"]
    for k in range(n):
        t = now_ts - last_age - (n - 1 - k) * 10
        ok = (k % 100) < classified * 100
        lines.append("%d,1,1,1,1,5,1,%d,%d,5,%s" % (t, 3 if ok else 0, 2 if ok else 0, 1 if ok else (3 if rt_blind else 1)))
    path.write_text("\n".join(lines) + "\n")


WED_10 = int(dt.datetime(2026, 10, 7, 10, 0, tzinfo=S.ET).timestamp())


def test_orderflow_classifier_matches_the_real_capture_and_repair_items(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EL", str(tmp_path))
    ohlc = tmp_path / "ohlc"
    ohlc.mkdir()
    _capture_csv(ohlc / "NQ_10s.csv", WED_10, classified=0.46)
    _capture_csv(ohlc / "ES_10s.csv", WED_10, classified=1.0, last_age=20 * 60)             # a stale feed: NOT order flow
    cap = {i["id"]: i for i in S.check_capture(WED_10, str(ohlc))}
    assert cap["capture_NQ"]["status"] == "fail" and "buy/sell" in cap["capture_NQ"]["detail"]
    assert S.is_orderflow(cap["capture_NQ"]) is True
    assert cap["capture_ES"]["status"] == "fail" and "min old" in cap["capture_ES"]["detail"]
    assert S.is_orderflow(cap["capture_ES"]) is False
    # the no-tick repair warning is order flow too
    _capture_csv(ohlc / "NQ_10s.csv", WED_10, n=500, classified=0.0, rt_blind=True)
    rep = S.check_repair(WED_10, str(ohlc))
    assert rep and rep[0]["id"] == "repair_NQ" and S.is_orderflow(rep[0])
    assert S.push_items(cap.values()) == [cap["capture_ES"]]                                # only the stale feed would be pushed


def _it(cid, status="fail", detail="x"):
    return S._item(cid, status, cid, detail)


def test_orderflow_only_failure_builds_no_note_and_nothing_is_pushed():
    items = [_it("capture_NQ", detail="only 46% of the last hour's traded bars carry buy/sell"),
             _it("repair_NQ", "warn", "8982 no-tick bars since 10-04 18:03 ET are not yet rebuilt"),
             _it("task:EdgeLog NT readiness", "pass")]
    action, st, note = S.decide_push(items, {}, 1000, NOW)
    assert action is None and note is None and st["set"] == {}


def test_note_text_is_plain_and_leaves_out_order_flow():
    items = [_it("capture_NQ", detail="only 46% of the last hour's traded bars carry buy/sell"),
             _it("box_push", detail="newest run FAILED (ssh timeout) - the box's KEEL refresh reads stale NQ data"),
             _it("repair_NQ", "warn", "8982 no-tick bars since 10-04 18:03 ET")]
    note = S.build_note(items, NOW)
    assert note["title"] == "Paper NT8: needs a fix" and note["priority"] == "default"
    assert note["message"].split("\n") == ["Trading: not affected.", "The NQ data upload to the cloud box failed.",
                                           "Do: ask Claude (PAPER-NT8 chat)."]
    assert not N.lint(note)


def test_a_strategy_down_is_the_one_high_priority_item():
    items = [_it("roster", detail="the watchdog has not reported healthy since 10-05 09:12 (STOP / INCOMPLETE) - a strategy is down"),
             _it("nt_backup_age", detail="newest snapshot is 2026-09-30")]
    note = S.build_note(items, NOW)
    assert note["title"] == "Paper NT8: CHECK NOW" and note["priority"] == "high"
    lines = note["message"].split("\n")
    assert lines[0] == "Trading: AFFECTED - a strategy is down."
    assert lines[1] == "A strategy has been down since 09:12. The NinjaTrader backup is out of date."
    assert lines[2] == "Do: open NinjaTrader and check the strategies."
    assert not N.lint(note)


def test_every_item_kind_reads_plainly():
    ids = [("task:EdgeLog NT 10s import", "last run ended with code 1 (not 0)"),
           ("task:EdgeLog premarket wake", "last ran 10-01 06:00, more than 80 h ago"),
           ("box_push", "no successful push since 10-02 21:00"), ("nt_backup_rows", "x"), ("capture_NQ", "newest bar is 9 min old"),
           ("readiness", "no readiness result for today"), ("report", "no report for 2026-10-06 (the 16:10 ET runner pass)"),
           ("bundle", "last rebuilt 10-04 09:00 ET"), ("something_new", "?")]
    for cid, detail in ids:
        note = S.build_note([_it(cid, detail=detail)], NOW)
        assert not N.lint(note), (cid, note, N.lint(note))


def test_push_repeat_rule_once_then_daily_new_at_once_back_only_after_high():
    box = [_it("box_push")]
    a, st, n = S.decide_push(box, {}, 1000, NOW)
    assert a == "push" and n["priority"] == "default"
    assert S.decide_push(box, st, 1000 + 1800, NOW)[0] is None                              # the next 30-minute run
    assert S.decide_push(box, st, 1000 + 6 * 3600, NOW)[0] is None                          # the old 6 h repeat is gone
    assert S.decide_push(box, st, 1000 + 23 * 3600, NOW)[0] is None
    assert S.decide_push(box, st, 1000 + 24 * 3600, NOW)[0] == "push"                       # once a day
    two = box + [_it("readiness")]
    a2, st2, n2 = S.decide_push(two, st, 2000, NOW)
    assert a2 == "push"                                                                     # a NEW problem: at once
    # everything clears after a default-priority-only episode: no "back to normal"
    assert S.decide_push([], st2, 3000, NOW)[0] is None
    # a high push in the episode -> ONE low back-to-normal, then silence
    roster = [_it("roster", detail="since 10-05 09:12")]
    a3, st3, n3 = S.decide_push(roster, {}, 5000, NOW)
    assert a3 == "push" and n3["priority"] == "high"
    a4, st4, n4 = S.decide_push([], st3, 6000, NOW)
    assert a4 == "clear" and n4["title"] == "Paper NT8: OK" and n4["priority"] == "low"
    assert "A strategy has been down" in n4["message"] and not N.lint(n4)
    assert S.decide_push([], st4, 7000, NOW)[0] is None


def test_a_worse_problem_pushes_at_once_even_inside_the_day():
    a, st, _ = S.decide_push([_it("capture_ES", detail="newest bar is 9 min old")], {}, 1000, NOW)      # low
    assert a == "push"
    a2, st2, n2 = S.decide_push([_it("capture_ES", detail="newest bar is 9 min old"), _it("roster", detail="since 10-05 09:12")], st, 1500, NOW)
    assert a2 == "push" and n2["priority"] == "high"


def _stub_main(monkeypatch, tmp_path, items, tasks=None):
    monkeypatch.setattr(S, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(S, "RESULT_PATH", str(tmp_path / "result.json"))
    monkeypatch.setattr(S, "maybe_backup", lambda *a, **k: None)
    monkeypatch.setattr(S, "read_tasks", lambda: tasks or [])
    for fn in ("check_box_push", "check_nt_backup", "check_roster", "check_capture", "check_repair", "check_readiness",
               "check_roll_watch"):
        monkeypatch.setattr(S, fn, lambda *a, **k: [])
    if items is not None:
        monkeypatch.setattr(S, "check_tasks", lambda now_local, tasks=None: list(items))
    posted, pushed = [], []
    monkeypatch.setattr(S, "_post_inbox", posted.append)
    monkeypatch.setattr(S, "_push_note", lambda note: pushed.append(note) or True)
    return posted, pushed


def test_main_order_flow_only_failure_posts_to_the_inbox_but_never_the_phone(monkeypatch, tmp_path):
    items = [_it("capture_NQ", detail="only 46% of the last hour's traded bars carry buy/sell")]
    posted, pushed = _stub_main(monkeypatch, tmp_path, items)
    assert S.main(["--no-firestore"]) == 1                                                  # the check still fails
    assert len(posted) == 1 and "buy/sell" in posted[0] and posted[0].startswith("NT8 PIPELINE SWEEP: FAIL")   # inbox post unchanged
    assert pushed == []
    saved = json.load(open(tmp_path / "result.json"))
    assert saved["items"][0]["id"] == "capture_NQ"                                          # JSON unchanged in shape


def test_main_pushes_once_per_day_while_unchanged(monkeypatch, tmp_path):
    items = [_it("box_push", detail="newest run FAILED")]
    posted, pushed = _stub_main(monkeypatch, tmp_path, items)
    S.main(["--no-firestore"])
    S.main(["--no-firestore"])
    S.main(["--no-firestore"])
    assert len(pushed) == 1 and pushed[0]["title"] == "Paper NT8: needs a fix"
    state = json.load(open(tmp_path / "state.json"))
    assert state["set"] == ["box_push"] and state["push"]["set"] == {"box_push": 1}         # the inbox state keeps its shape


def test_main_failed_delivery_is_retried_next_run(monkeypatch, tmp_path):
    items = [_it("box_push", detail="newest run FAILED")]
    posted, pushed = _stub_main(monkeypatch, tmp_path, items)
    ok = {"v": False}
    monkeypatch.setattr(S, "_push_note", lambda note: pushed.append(note) or ok["v"])
    S.main(["--no-firestore"])
    ok["v"] = True
    S.main(["--no-firestore"])
    S.main(["--no-firestore"])
    assert len(pushed) == 2                                                                  # tried, retried, then quiet


def test_main_dry_run_prints_the_note_and_sends_nothing(monkeypatch, tmp_path, capsys):
    items = [_it("roster", detail="the watchdog has not reported healthy since 10-05 09:12")]
    posted, pushed = _stub_main(monkeypatch, tmp_path, items)
    assert S.main(["--dry-run", "--no-firestore"]) == 1
    out = capsys.readouterr().out
    assert "title: Paper NT8: CHECK NOW" in out and "priority: high" in out and "Trading: AFFECTED - a strategy is down." in out
    assert posted == [] and pushed == [] and not (tmp_path / "state.json").exists()


def test_main_readiness_exit_1_alone_does_not_alert(monkeypatch, tmp_path):
    # the real check_tasks, fed what Task Scheduler reports after a readiness run that found problems
    posted, pushed = _stub_main(monkeypatch, tmp_path, None, tasks=_tasks(1, last=dt.datetime.now()))
    assert S.main(["--no-firestore"]) == 0
    assert posted == [] and pushed == []
    # ... but a readiness run that crashed (any other code) still alerts, once
    posted, pushed = _stub_main(monkeypatch, tmp_path, None, tasks=_tasks(2, last=dt.datetime.now()))
    assert S.main(["--no-firestore"]) == 1
    assert len(posted) == 1 and len(pushed) == 1 and pushed[0]["message"].split("\n")[1] == "The morning check failed on its last run."


def test_sweep_script_can_import_the_api_package():
    import sys
    assert S.ROOT in sys.path          # run as a script, only tools/ is on the path; the phone text imports api.ntfy_push
