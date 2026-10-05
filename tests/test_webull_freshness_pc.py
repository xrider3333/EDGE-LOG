"""tests/test_webull_freshness_pc.py -- the PC half of the Webull pipeline freshness monitor
(tools/webull_freshness_pc.py): the read-only ssh fetch and its failure path, the box-monitor
silence check, relaying the box's open alerts once per episode + a cleared post, the PC-log
checks (NQ push, ledger pull, nightly backup), and the inbox poster's dedupe and retry. ssh is
a fake run_cmd, the inbox a fake post_fn (or chat_inbox pointed at tmp_path), every log a
tmp file.
"""
import datetime as dt
import json
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.webull_freshness as wf  # noqa: E402
import tools.webull_freshness_pc as pc  # noqa: E402

ET = wf.ET
MST = ZoneInfo("America/Phoenix")     # the owner's PC clock (no DST)


def et(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=ET)


MON_1100 = et(2026, 10, 5, 11, 0)


class FakeSSH:
    """run_cmd stand-in: answers like `ssh ... cat status.json; echo SPLIT; cat hb.json`."""

    def __init__(self):
        self.calls = []
        self.fail = None          # None | "rc" | "timeout"
        self.status = {"open_alerts": [], "outbox_pending": 0}
        self.hb_epoch = None

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        if self.fail == "timeout":
            raise subprocess.TimeoutExpired(cmd, 60)

        class R:
            pass
        r = R()
        if self.fail == "rc":
            r.returncode, r.stdout, r.stderr = 255, "", "ssh: connect to host port 22: Unknown error\n"
            return r
        hb = {"epoch": self.hb_epoch, "ok": True} if self.hb_epoch is not None else None
        r.returncode = 0
        r.stdout = (json.dumps(self.status) + "\n\n" + pc.SPLIT + "\n"
                    + (json.dumps(hb) if hb else "") + "\n")
        r.stderr = ""
        return r


class PC:
    def __init__(self, tmp_path, now):
        self.paths = pc.default_paths(str(tmp_path / "EdgeLog"))
        self.ssh = FakeSSH()
        self.ssh.hb_epoch = now.timestamp() - 60
        self.posts = []
        self.post_ok = True
        self.now = now
        # healthy PC logs
        self.push_log([(et(2026, 10, 2, 17, 21), "OK pushed 18.5 MB (sha abc) to box")])
        self.ledger_log([(now - dt.timedelta(hours=20), "OK copied 18/18 into x")])
        self.backup_log([(now - dt.timedelta(hours=10), "=== nightly backup ok ===")])

    def _write(self, key, rows, iso=False):
        os.makedirs(os.path.dirname(self.paths[key]), exist_ok=True)
        with open(self.paths[key], "w", encoding="utf-8") as f:
            for t, rest in rows:
                local = t.astimezone(MST).replace(tzinfo=None)
                stamp = local.isoformat(timespec="seconds") if iso else \
                    local.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{stamp} {rest}\n")

    def push_log(self, rows):
        self._write("push_nq_log", rows, iso=True)

    def ledger_log(self, rows):
        self._write("pull_ledgers_log", rows)

    def backup_log(self, rows):
        self._write("backup_log", [(t, " " + r) for t, r in rows])

    def post_fn(self, chat, text, frm):
        if self.post_ok is not True and (self.post_ok is False or chat in self.post_ok):
            raise OSError("inbox locked")
        self.posts.append((chat, text, frm))

    def run(self, now=None, **kw):
        if now is not None:
            self.now = now
            if self.ssh.hb_epoch is not None:     # the box monitor keeps running meanwhile
                self.ssh.hb_epoch = now.timestamp() - 60
        return pc.run_once(self.paths, now=self.now, run_cmd=self.ssh, post_fn=self.post_fn,
                           local_tz=MST, log=lambda s: None, **kw)


def bad_keys(out):
    return {v["key"] for v in out["verdicts"] if v["ok"] is False}


def test_box_auto_restart_is_posted_to_both_inboxes_once(tmp_path):
    """Owner rule 2026-10-05 (MANAGER #69): an executor auto-restart reaches the inboxes."""
    p = PC(tmp_path, MON_1100)
    p.ssh.status["auto_restart"] = {"enabled": True, "last_restart_et": "Sat 10-03 17:21 ET",
                                     "last_restart_result": "ok"}
    p.run()
    texts = [t for _c, t, _f in p.posts]
    assert len(p.posts) == len(pc.INBOXES)
    assert all("AUTO-RESTART" in t and "Sat 10-03 17:21 ET" in t for t in texts)
    p.run(MON_1100 + dt.timedelta(minutes=10))
    assert len(p.posts) == len(pc.INBOXES)                     # relayed once
    p.ssh.status["auto_restart"]["last_restart_et"] = "Sun 10-04 03:05 ET"
    p.run(MON_1100 + dt.timedelta(minutes=20))
    assert len(p.posts) == 2 * len(pc.INBOXES)                 # a new restart, once more


def test_box_auto_restart_not_relayed_when_the_box_read_failed(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.fail = "rc"
    p.ssh.status["auto_restart"] = {"last_restart_et": "Sat 10-03 17:21 ET"}
    p.run()
    assert not any("AUTO-RESTART" in t for _c, t, _f in p.posts)


def test_healthy_run_posts_nothing(tmp_path):
    p = PC(tmp_path, MON_1100)
    out = p.run()
    assert bad_keys(out) == set() and p.posts == []
    assert os.path.exists(p.paths["state"])


def test_ssh_command_is_read_only_batch_and_windowless(tmp_path, monkeypatch):
    p = PC(tmp_path, MON_1100)
    p.run()
    cmd, kw = p.ssh.calls[0]
    assert cmd[0] == pc.ssh_exe()
    assert "BatchMode=yes" in cmd and pc.HOST in cmd
    remote = cmd[-1]
    assert remote.startswith("cat ") and ">" not in remote.replace("2>/dev/null", "")
    assert "rm " not in remote and "mv " not in remote
    assert kw["stdin"] is subprocess.DEVNULL and kw["timeout"] == pc.SSH_TIMEOUT_SEC
    if os.name == "nt":
        assert kw["creationflags"] & 0x08000000


def test_ssh_exe_prefers_the_explicit_windows_path(tmp_path, monkeypatch):
    fake_root = tmp_path / "Windows"
    exe = fake_root / "System32" / "OpenSSH" / "ssh.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setenv("SystemRoot", str(fake_root))
    assert pc.ssh_exe(is_nt=True) == str(exe)


def test_ssh_failure_alerts_on_the_second_run_and_clears(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.fail = "rc"
    out = p.run()
    assert "box_ssh" in bad_keys(out) and p.posts == []          # one blip: pending
    p.ssh.fail = "timeout"
    p.run(MON_1100 + dt.timedelta(minutes=10))
    assert [c for c, _, _ in p.posts] == ["MANAGER", "PAPER-WB"]
    assert "cannot reach the box over ssh" in p.posts[0][1]
    assert all(frm == "PAPER-WB-MONITOR" for _, _, frm in p.posts)
    p.ssh.fail = "rc"
    p.run(MON_1100 + dt.timedelta(minutes=20))                     # same episode: no repost
    assert len(p.posts) == 2
    p.ssh.fail = None
    p.ssh.hb_epoch = (MON_1100 + dt.timedelta(minutes=29)).timestamp()
    p.run(MON_1100 + dt.timedelta(minutes=30))
    assert len(p.posts) == 4 and "CLEARED" in p.posts[-1][1]


def test_box_monitor_silent_and_never_ran(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.hb_epoch = MON_1100.timestamp() - 15 * 60
    out = p.run()
    assert "box_monitor" in bad_keys(out)
    assert "SILENT" in p.posts[0][1]
    p2 = PC(tmp_path / "never", MON_1100)
    p2.ssh.hb_epoch = None
    p2.ssh.status = None
    out = p2.run()
    assert "box_monitor" in bad_keys(out)
    assert "never ran" in [v for v in out["verdicts"] if v["key"] == "box_monitor"][0]["detail"]


def test_box_alerts_are_relayed_once_per_episode_and_survive_an_ssh_outage(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.status["open_alerts"] = [{"key": "exec_publish", "severity": "URGENT",
                                    "title": "executor Firestore publish DOWN",
                                    "detail": "last good publish 17:11:40 ET",
                                    "opened_et": "Sat 10-03 17:21 ET"}]
    p.run()
    assert len(p.posts) == 2 and "NEW [URGENT] box: executor Firestore publish DOWN" in p.posts[0][1]
    p.run(MON_1100 + dt.timedelta(minutes=10))
    assert len(p.posts) == 2                                       # deduped
    p.ssh.fail = "rc"                                              # can't see the box: no clear
    p.ssh.hb_epoch = (MON_1100 + dt.timedelta(minutes=19)).timestamp()
    p.run(MON_1100 + dt.timedelta(minutes=20))
    assert len(p.posts) == 2
    state = json.load(open(p.paths["state"], encoding="utf-8"))
    assert state["alerts"]["box:exec_publish"]["open"] is True
    p.ssh.fail = None
    p.ssh.status["open_alerts"] = []
    p.ssh.hb_epoch = (MON_1100 + dt.timedelta(minutes=29)).timestamp()
    p.run(MON_1100 + dt.timedelta(minutes=30))
    assert len(p.posts) == 4 and "CLEARED box: executor Firestore publish DOWN" in p.posts[-1][1]


def test_box_outbox_backlog_is_relayed(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.status["outbox_pending"] = 3
    assert "box_outbox" in bad_keys(p.run())


# -- PC logs --------------------------------------------------------------------------------
def test_nq_push_after_1720_et_on_a_session_day(tmp_path):
    t = et(2026, 10, 5, 18, 0)
    p = PC(tmp_path, t)
    p.push_log([(et(2026, 10, 5, 10, 23), "OK pushed 18.5 MB (sha a9c) to box"),
                (et(2026, 10, 5, 17, 20, ), "FAIL scp: ")])
    out = p.run()
    assert "nq_push" in bad_keys(out)
    assert "no OK push since 2026-10-05 16:10 ET" in p.posts[0][1]
    p.push_log([(et(2026, 10, 5, 17, 21), "SKIP box already has this master (18.5 MB)")])
    out = p.run(et(2026, 10, 5, 18, 10))
    assert "nq_push" not in bad_keys(out) and "CLEARED" in p.posts[-1][1]


def test_nq_push_before_1735_judges_the_previous_session(tmp_path):
    t = et(2026, 10, 5, 17, 30)                                    # Monday, before due
    p = PC(tmp_path, t)
    p.push_log([(et(2026, 10, 2, 17, 21), "OK pushed")])          # Friday's push
    assert "nq_push" not in bad_keys(p.run())


def test_nq_push_missed_overnight_still_open_next_morning(tmp_path):
    t = et(2026, 10, 6, 10, 0)                                     # Tue morning, PC just woke
    p = PC(tmp_path, t)
    p.push_log([(et(2026, 10, 5, 10, 23), "OK pushed"),
                (et(2026, 10, 5, 17, 20), "FAIL mkdir on box: ")])
    assert "nq_push" in bad_keys(p.run())


def test_nq_push_weekend_and_holiday(tmp_path):
    p = PC(tmp_path, et(2026, 10, 4, 12, 0))                       # Sunday: Friday counts
    p.push_log([(et(2026, 10, 2, 17, 21), "OK pushed")])
    assert "nq_push" not in bad_keys(p.run())
    p2 = PC(tmp_path / "hol", et(2026, 11, 26, 20, 0))             # Thanksgiving: Wed counts
    p2.push_log([(et(2026, 11, 25, 17, 22), "OK pushed")])
    assert "nq_push" not in bad_keys(p2.run())


def test_nq_push_in_winter_when_the_task_fires_at_1620_est(tmp_path):
    """The PC is on Arizona time (no DST): its 14:20 task is 17:20 EDT but 16:20 EST. A push
    window pinned to 17:20 ET would open a false episode every winter evening and never clear."""
    t = et(2026, 11, 9, 18, 0)                                     # Monday, EST
    p = PC(tmp_path, t)
    push_at = dt.datetime(2026, 11, 9, 14, 20, 30, tzinfo=MST)     # the task's own time
    assert push_at.astimezone(ET).strftime("%H:%M") == "16:20"
    p.push_log([(push_at, "OK pushed 18.5 MB (sha w1) to box")])
    out = p.run()
    assert "nq_push" not in bad_keys(out) and p.posts == []
    # the next evening's push at the same local time also counts; a missed one does not
    p.push_log([(push_at, "OK pushed"),
                (dt.datetime(2026, 11, 10, 9, 0, tzinfo=MST), "OK manual push before the open")])
    out = p.run(et(2026, 11, 10, 18, 0))
    assert "nq_push" in bad_keys(out)
    assert "no OK push since 2026-11-10 16:10 ET" in p.posts[0][1]


def test_nq_push_on_a_half_day_counts_from_its_1300_close(tmp_path):
    t = et(2026, 11, 27, 18, 0)
    p = PC(tmp_path, t)
    p.push_log([(dt.datetime(2026, 11, 27, 14, 20, tzinfo=MST), "OK pushed")])
    assert "nq_push" not in bad_keys(p.run())


def test_ledger_pull_fail_and_age(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ledger_log([(MON_1100 - dt.timedelta(hours=20), "OK copied 18/18 into x"),
                  (MON_1100 - dt.timedelta(hours=1), "FAIL copied 0/18 into y")])
    assert "ledger_pull" in bad_keys(p.run())
    p.ledger_log([(MON_1100 - dt.timedelta(hours=40), "OK copied 18/18 into x")])
    assert "ledger_pull" in bad_keys(p.run(MON_1100 + dt.timedelta(minutes=10)))


def test_nightly_backup_age(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.backup_log([(MON_1100 - dt.timedelta(hours=40), "=== nightly backup ok ==="),
                  (MON_1100 - dt.timedelta(hours=2), "=== nightly backup start ===")])
    assert "nightly_backup" in bad_keys(p.run())


def test_missing_pc_logs_are_alerts_not_crashes(tmp_path):
    p = PC(tmp_path, MON_1100)
    for k in ("push_nq_log", "pull_ledgers_log", "backup_log"):
        os.remove(p.paths[k])
    out = p.run()
    assert {"nq_push", "ledger_pull", "nightly_backup"} <= bad_keys(out)


# -- poster ---------------------------------------------------------------------------------
def test_one_post_per_inbox_per_run_even_with_several_new_alerts(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.status["open_alerts"] = [
        {"key": "a", "severity": "HIGH", "title": "A", "detail": "x"},
        {"key": "b", "severity": "HIGH", "title": "B", "detail": "y"}]
    p.run()
    assert len(p.posts) == 2
    assert "box: A" in p.posts[0][1] and "box: B" in p.posts[0][1]


def test_failed_inbox_post_is_retried_next_run(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.status["open_alerts"] = [{"key": "a", "severity": "HIGH", "title": "A", "detail": "x"}]
    p.post_ok = False
    p.run()
    assert p.posts == []
    p.post_ok = True
    p.run(MON_1100 + dt.timedelta(minutes=10))
    assert len(p.posts) == 2 and "NEW [HIGH] box: A" in p.posts[0][1]


def test_one_inbox_failing_retries_only_that_inbox(tmp_path):
    """MANAGER written, PAPER-WB not: next run posts to PAPER-WB only (no MANAGER duplicate),
    and a cleared notice is retried the same way."""
    p = PC(tmp_path, MON_1100)
    p.ssh.status["open_alerts"] = [{"key": "a", "severity": "HIGH", "title": "A", "detail": "x"}]
    p.post_ok = {"PAPER-WB"}
    out = p.run()
    assert [c for c, _, _ in p.posts] == ["MANAGER"] and out["pending_posts"] == 1
    p.post_ok = True
    out = p.run(MON_1100 + dt.timedelta(minutes=10))
    assert [c for c, _, _ in p.posts] == ["MANAGER", "PAPER-WB"]
    assert "NEW [HIGH] box: A" in p.posts[1][1] and p.posts[1][1].startswith("(delayed")
    assert out["pending_posts"] == 0
    p.run(MON_1100 + dt.timedelta(minutes=20))
    assert len(p.posts) == 2                                       # no repeat after delivery
    p.ssh.status["open_alerts"] = []
    p.post_ok = {"MANAGER"}
    p.run(MON_1100 + dt.timedelta(minutes=30))
    assert [c for c, _, _ in p.posts[2:]] == ["PAPER-WB"] and "CLEARED" in p.posts[2][1]
    p.post_ok = True
    p.run(MON_1100 + dt.timedelta(minutes=40))
    assert [c for c, _, _ in p.posts[3:]] == ["MANAGER"] and "CLEARED" in p.posts[3][1]
    p.run(MON_1100 + dt.timedelta(minutes=50))
    assert len(p.posts) == 4


def test_debounced_ssh_alert_not_rearmed_by_a_failed_post(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.fail = "rc"
    p.run()
    p.post_ok = False
    p.run(MON_1100 + dt.timedelta(minutes=10))                    # episode opens, post fails
    assert p.posts == []
    p.post_ok = True
    p.run(MON_1100 + dt.timedelta(minutes=20))                    # retried at once
    assert [c for c, _, _ in p.posts] == ["MANAGER", "PAPER-WB"]
    assert "cannot reach the box over ssh" in p.posts[0][1]


def test_undeliverable_posts_dropped_after_three_days(tmp_path):
    left, posted = pc.flush_posts(
        [{"chat": "MANAGER", "text": "x", "created_epoch": 0.0, "created_et": "L"}],
        lambda c, t, f: None, 4 * 86400.0, lambda s: None)
    assert left == [] and posted == []


def test_dry_run_posts_and_writes_nothing(tmp_path):
    p = PC(tmp_path, MON_1100)
    p.ssh.fail = "rc"
    p.run()
    p.ssh.fail = "rc"
    out = p.run(MON_1100 + dt.timedelta(minutes=10), dry_run=True)
    assert out["text"] and p.posts == []


def test_real_chat_inbox_post_lands_in_the_tmp_inbox(tmp_path, monkeypatch):
    from tools import chat_inbox
    monkeypatch.setattr(chat_inbox, "BOX", str(tmp_path / "inbox"))
    p = PC(tmp_path, MON_1100)
    p.ssh.status["open_alerts"] = [{"key": "a", "severity": "HIGH", "title": "A", "detail": "x"}]
    pc.run_once(p.paths, now=MON_1100, run_cmd=p.ssh, local_tz=MST, log=lambda s: None)
    for chat in ("MANAGER", "PAPER-WB"):
        items = chat_inbox.load(chat)
        assert len(items) == 1 and items[0]["from"] == "PAPER-WB-MONITOR"
        assert items[0]["status"] == "open" and "box: A" in items[0]["text"]


# -- review follow-ups (2026-10-05) ---------------------------------------------------------
PREOPEN_ALERT = {"key": "preopen", "severity": "URGENT", "title": "QQQ book NOT ready",
                 "detail": "Webull token (webull_token) status PENDING",
                 "opened_et": "Mon 10-05 08:30 ET", "quiet_expire": True}


def test_preopen_alert_that_expires_at_the_open_is_closed_not_cleared(tmp_path):
    p = PC(tmp_path, et(2026, 10, 5, 9, 20))
    p.ssh.status["open_alerts"] = [dict(PREOPEN_ALERT)]
    p.ssh.status["preopen"] = {"date": "2026-10-05", "ready_pushed": False, "slots": {
        "08:30": {"at": "08:30", "misses": ["x"]}, "09:15": {"at": "09:15", "misses": ["x"]}}}
    p.run()
    assert "NEW [URGENT] box: QQQ book NOT ready" in p.posts[0][1]
    p.ssh.status["open_alerts"] = []                       # the box let it expire at 09:30
    p.run(et(2026, 10, 5, 9, 32))
    assert len(p.posts) == 4
    assert "CLEARED" not in p.posts[-1][1]
    assert "CLOSED (no longer checked, never seen OK) box: QQQ book NOT ready" in p.posts[-1][1]


def test_preopen_alert_fixed_by_the_0915_slot_is_cleared(tmp_path):
    p = PC(tmp_path, et(2026, 10, 5, 8, 40))
    p.ssh.status["open_alerts"] = [dict(PREOPEN_ALERT)]
    p.ssh.status["preopen"] = {"date": "2026-10-05", "ready_pushed": False,
                               "slots": {"08:30": {"at": "08:30", "misses": ["x"]}}}
    p.run()
    p.ssh.status["open_alerts"] = []
    p.ssh.status["preopen"] = {"date": "2026-10-05", "ready_pushed": True, "slots": {
        "08:30": {"at": "08:30", "misses": ["x"]}, "09:15": {"at": "09:16", "misses": []}}}
    p.run(et(2026, 10, 5, 9, 20))
    assert len(p.posts) == 4 and "CLEARED box: QQQ book NOT ready" in p.posts[-1][1]


def test_unreadable_box_status_neither_clears_nor_reposts_relayed_alerts(tmp_path):
    """ssh works but status.json is missing / half-written: relayed alerts stay as they are
    (no CLEARED now, no NEW again on the next good read); the unreadable status is its own
    alert after 2 runs."""
    p = PC(tmp_path, MON_1100)
    alert = {"key": "exec_publish", "severity": "URGENT", "title": "executor publish DOWN",
             "detail": "x", "opened_et": "Mon 10-05 10:50 ET"}
    p.ssh.status["open_alerts"] = [alert]
    p.run()
    assert len(p.posts) == 2
    good = p.ssh.status
    p.ssh.status = None                                    # cat printed nothing / bad JSON
    out = p.run(MON_1100 + dt.timedelta(minutes=10))
    assert len(p.posts) == 2
    assert "box_status" in bad_keys(out)
    assert {v["key"]: v["ok"] for v in out["verdicts"]}["box_outbox"] is None
    p.run(MON_1100 + dt.timedelta(minutes=20))             # 2nd run: its own alert
    assert len(p.posts) == 4 and "status.json unreadable" in p.posts[-1][1]
    assert "CLEARED box: executor publish DOWN" not in p.posts[-1][1]
    p.ssh.status = good
    p.run(MON_1100 + dt.timedelta(minutes=30))
    assert "NEW" not in p.posts[-1][1]                     # the relayed one never re-opened
    assert "CLEARED box monitor status.json unreadable" in p.posts[-1][1]
    state = json.load(open(p.paths["state"], encoding="utf-8"))
    assert state["alerts"]["box:exec_publish"]["open"] is True


def test_state_saved_after_each_post_so_a_kill_does_not_double_post(tmp_path):
    """Killed after MANAGER was written: the next run posts to PAPER-WB only."""
    p = PC(tmp_path, MON_1100)
    p.ssh.status["open_alerts"] = [{"key": "a", "severity": "HIGH", "title": "A", "detail": "x"}]
    calls = []

    def post_then_die(chat, text, frm):
        calls.append(chat)
        if len(calls) == 2:
            raise SystemExit("task killed")
        p.posts.append((chat, text, frm))
    try:
        pc.run_once(p.paths, now=MON_1100, run_cmd=p.ssh, post_fn=post_then_die, local_tz=MST,
                    log=lambda s: None)
    except SystemExit:
        pass
    state = json.load(open(p.paths["state"], encoding="utf-8"))
    assert [x["chat"] for x in state["pending_posts"]] == ["PAPER-WB"]
    assert state["alerts"]["box:a"]["open"] is True
    p.run(MON_1100 + dt.timedelta(minutes=10))
    assert [c for c, _, _ in p.posts] == ["MANAGER", "PAPER-WB"]


def test_flush_posts_save_callback_sees_what_is_still_queued():
    saves = []
    pending = [{"chat": c, "text": "t", "created_epoch": 0.0, "created_et": "L"}
               for c in ("MANAGER", "PAPER-WB")]
    left, posted = pc.flush_posts(pending, lambda c, t, f: None, 10.0, lambda s: None,
                                  save=saves.append)
    assert posted == ["MANAGER", "PAPER-WB"] and left == []
    assert [[x["chat"] for x in s] for s in saves] == [["PAPER-WB"], []]


def test_import_failure_under_pythonw_leaves_a_fatal_log_line(tmp_path):
    """Run as a script with tools.webull_freshness unimportable: exit 1 AND one FATAL line in
    <EDGELOG_HOME>/logs/webull_freshness_pc.log (pythonw has no console to show it)."""
    import shutil
    fake_root = tmp_path / "repo"
    (fake_root / "tools").mkdir(parents=True)
    shutil.copy(os.path.join(ROOT, "tools", "webull_freshness_pc.py"), fake_root / "tools")
    (fake_root / "tools" / "__init__.py").write_text("")
    (fake_root / "tools" / "webull_freshness.py").write_text("raise ImportError('broken')\n")
    home = tmp_path / "home"
    env = dict(os.environ, EDGELOG_HOME=str(home), PYTHONPATH="")
    r = subprocess.run([sys.executable, str(fake_root / "tools" / "webull_freshness_pc.py"),
                        "--dry-run"], env=env, capture_output=True, text=True, timeout=60,
                       cwd=str(tmp_path))
    assert r.returncode == 1
    log = (home / "logs" / "webull_freshness_pc.log").read_text(encoding="utf-8")
    assert "FATAL import failed: ImportError: broken" in log
