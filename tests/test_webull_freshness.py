"""tests/test_webull_freshness.py -- the box half of the Webull pipeline freshness monitor
(tools/webull_freshness.py). Every check against fixture files in a temp EDGELOG_HOME (fresh vs
stale, weekend / holiday / half day), episode dedupe + recovery, the persisted ntfy outbox, and
the auto-restart gate. Nothing here pushes to ntfy, runs systemctl or sudo, or reads a live
file: push_fn / run_cmd are fakes and every path is under tmp_path.
"""
import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.webull_freshness as wf  # noqa: E402

ET = wf.ET
FAKE_TOKEN = "FAKETOKEN-must-never-leave-the-file-0123"


def et(y, mo, d, h, mi, s=0):
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=ET)


MON_1030 = et(2026, 10, 5, 10, 30)     # Monday session day
SAT_1200 = et(2026, 10, 3, 12, 0)      # Saturday
THANKSGIVING = et(2026, 11, 26, 10, 30)
HALF_DAY = dt.date(2026, 11, 27)       # day after Thanksgiving, 13:00 close


# -- fixture home ---------------------------------------------------------------------------
def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _wj(path, data):
    _w(path, json.dumps(data))


def _set_mtime(path, epoch):
    os.utime(path, (epoch, epoch))


class Home:
    """A healthy box home as of `now`; tweak with the setters, then run()."""

    def __init__(self, tmp_path, now, mode="PAPER"):
        self.root = str(tmp_path / "edgelog")
        self.paths = wf.default_paths(self.root)
        self.pushes = []
        self.push_ok = True
        self.cmds = []
        self.failed = []
        self.unit_state = "active"     # `systemctl is-active edgelog-qqq-exec.service`
        self.restart_hook = None       # called on the sudo restart (e.g. to kill the pass)
        self.set_now(now)
        _wj(os.path.join(self.root, "webull_orders", "config.json"), {"mode": mode})
        _w(self.paths["exec_log"], "[qqq-exec] boot\n")
        self.exec_state()
        self.engine_hb(now)
        self.shadow_hb(now)
        self.cs_state()
        self.bars(now)
        self.keel()
        self.token(days_left=14, status="NORMAL")

    def set_now(self, now):
        self.now = now

    def advance(self, now):
        """Move the clock AND keep the live processes looking alive at the new time (the
        executor ticking and publishing, the engine/shadow heartbeats and the newest closed
        bar current) -- the files' other contents are kept as they are."""
        self.now = now
        st = json.load(open(self.paths["exec_state"], encoding="utf-8"))
        st["last_publish_ok_et"] = (now - dt.timedelta(seconds=10)).strftime("%H:%M:%S")
        _wj(self.paths["exec_state"], st)
        tick = now - dt.timedelta(seconds=3)
        _set_mtime(self.paths["exec_state"], tick.timestamp())
        _w(self.paths["serving_lock"], f"4242 {tick.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.engine_hb(now)
        self.shadow_hb(now)
        cs = json.load(open(self.paths["cs_state"], encoding="utf-8"))
        cs["bar_source"]["5m"]["newest_epoch"] = int(now.timestamp()) // 300 * 300 - 300
        _wj(self.paths["cs_state"], cs)

    # writers --------------------------------------------------------------------------------
    def exec_state(self, publish_ago=10.0, loop_ago=3.0, renew=20.0, **over):
        now = self.now
        st = {
            "trading_day": now.date().isoformat(), "legs": {}, "_broker_resend": {},
            "_broker_fill_capture": {}, "breaker_tripped": False, "kill_done": False,
            "last_publish_ok_et": (now - dt.timedelta(seconds=publish_ago)).strftime("%H:%M:%S"),
            "_lease_renew_every_sec": renew, "_broker_lease_ok": True,
            "_broker_lease_reason": "lease ok (free or already ours)",
            "_tick_gap_day": now.date().isoformat(), "tick_gap_max_s_today": 5.0,
            "eod_summary_done_date": now.date().isoformat(),
            "_webull_flat_after_eod": {"date": now.date().isoformat(), "flat": True, "shares": 0},
        }
        st.update(over)
        _wj(self.paths["exec_state"], st)
        tick = now - dt.timedelta(seconds=loop_ago)
        _set_mtime(self.paths["exec_state"], tick.timestamp())
        _w(self.paths["serving_lock"], f"4242 {tick.strftime('%Y-%m-%d %H:%M:%S')}\n")
        return st

    def engine_hb(self, ts, ok=True):
        _wj(self.paths["cs_heartbeat"], {"ts": ts.isoformat(), "ok": ok, "note": "0 event(s)"})

    def shadow_hb(self, ts, ok=True):
        _wj(self.paths["shadow_heartbeat"], {"ts": ts.isoformat(), "ok": ok, "note": ""})

    def cs_state(self, newest_bar_start=None, source="webull", settled_days=None):
        now = self.now
        if newest_bar_start is None:
            # the newest CLOSED 5m bar: the one that started at least 5 minutes ago
            e = int(now.timestamp()) // 300 * 300 - 300
        else:
            e = int(newest_bar_start.timestamp())
        days = settled_days if settled_days is not None else [now.date().isoformat()]
        _wj(self.paths["cs_state"], {
            "bar_source": {"5m": {"source": source, "newest_epoch": e,
                                  "checked_at": now.isoformat()}},
            "eod_settled": {d: {"at": "x"} for d in days}})

    def bars(self, now, nq_day=None, d1_day=None):
        e5 = int(now.timestamp()) // 300 * 300 - 300
        _w(self.paths["qqq_5m"], f"time,open,high,low,close,volume\n{e5},1,1,1,1,1\n")
        nq_day = nq_day or now.date()
        nq_e = int(wf.at(nq_day, (15, 55)).timestamp())
        _w(self.paths["nq_master"],
           f"time,open,high,low,close,volume,source\n{nq_e - 300},1,1,1,1,1,x\n{nq_e},1,1,1,1,1,x\n")
        # what the engine's cache really holds: QQQ_1d is refreshed once a day at ~09:35 ET
        # (cloud_signal step(), RTH only), when it gains the PREVIOUS session -- so before
        # 09:35 it still ends two sessions back.
        d1_day = d1_day or wf.prev_session(wf.latest_session_due(now, (9, 35)))
        d1_e = int(dt.datetime(d1_day.year, d1_day.month, d1_day.day, tzinfo=ET).timestamp())
        _w(self.paths["qqq_1d"], f"time,open,high,low,close,volume\n{d1_e},1,1,1,1,1\n")

    def keel(self, through=None):
        through = through or wf.keel_expected(wf.prev_session(self.now.date()))
        for leg in ("NOISE_382_v12", "NOISE_422_KEEL_v12"):
            _wj(os.path.join(self.paths["keel_dir"], f"{leg}_summary.json"),
                {"data_through": str(through), "leg": leg})

    def token(self, days_left=14, status="NORMAL"):
        exp_ms = int((self.now.timestamp() + days_left * 86400) * 1000)
        _w(self.paths["token_files"][0], f"{FAKE_TOKEN}\n{exp_ms}\n{status}\n")

    def config(self, **cfg):
        _wj(self.paths["config"], cfg)

    # running --------------------------------------------------------------------------------
    def push_fn(self, message, title, priority):
        self.pushes.append({"title": title, "message": message, "priority": priority})
        return self.push_ok

    def run_cmd(self, cmd, **kw):
        self.cmds.append(list(cmd))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        if cmd[:2] == ["systemctl", "--failed"]:
            R.stdout = "".join(f"{u} loaded failed failed x\n" for u in self.failed)
        if cmd[:2] == ["systemctl", "is-active"]:
            R.stdout = self.unit_state + "\n"
            R.returncode = 0 if self.unit_state == "active" else 3
        if cmd[:1] == ["sudo"] and self.restart_hook is not None:
            self.restart_hook()
        return R()

    def run(self, now=None, **kw):
        if now is not None:
            self.set_now(now)
        return wf.run_once(self.paths, now=self.now, push_fn=self.push_fn,
                           run_cmd=self.run_cmd, log=lambda line: None, **kw)

    def status(self):
        with open(self.paths["status"], encoding="utf-8") as f:
            return json.load(f)


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def failing(summary):
    return {k for k, v in summary["status"]["verdicts"].items() if v["ok"] is False}


# -- healthy baseline -----------------------------------------------------------------------
def test_healthy_session_has_no_failures_and_no_pushes(tmp_path):
    h = Home(tmp_path, MON_1030)
    out = h.run()
    assert failing(out) == set()
    assert h.pushes == []
    assert {"exec", "session", "evening", "systemd", "disk"} <= set(out["status"]["groups_checked"])
    hb = json.load(open(h.paths["heartbeat"], encoding="utf-8"))
    assert hb["ok"] is True and hb["open_alerts"] == 0


def test_weekend_and_holiday_skip_session_eod_and_preopen(tmp_path):
    h = Home(tmp_path, SAT_1200)
    out = h.run()
    assert "session" not in out["status"]["groups_checked"]
    assert "eod" not in out["status"]["groups_checked"]
    h2 = Home(tmp_path / "hol", THANKSGIVING)
    out2 = h2.run()
    assert "session" not in out2["status"]["groups_checked"]
    assert wf.preopen_slot(et(2026, 11, 26, 8, 31)) is None
    assert wf.preopen_slot(et(2026, 10, 3, 8, 31)) is None
    assert wf.preopen_slot(et(2026, 10, 5, 8, 31)) == "08:30"
    assert wf.preopen_slot(et(2026, 10, 5, 9, 20)) == "09:15"


# -- ALWAYS: executor publish ---------------------------------------------------------------
def test_publish_stale_pages_urgent_while_armed_in_session(tmp_path):
    h = Home(tmp_path, MON_1030)
    h.exec_state(publish_ago=20 * 60)
    out = h.run()
    assert "exec_publish" in failing(out)
    assert out["opened"][0]["severity"] == wf.URGENT
    assert h.pushes and h.pushes[0]["priority"] == "urgent"


def test_publish_limit_follows_the_advertised_cadence_off_hours(tmp_path):
    h = Home(tmp_path, SAT_1200, mode="OFF")
    h.exec_state(publish_ago=14 * 60, renew=600.0)
    assert "exec_publish" not in failing(h.run())
    h.exec_state(publish_ago=16 * 60, renew=600.0)
    out = h.run()
    assert "exec_publish" in failing(out)
    assert out["opened"][0]["severity"] == wf.HIGH      # not armed / not in session


def test_publish_wedge_longer_than_a_day_reads_its_true_age(tmp_path):
    """last_publish_ok_et has no date: the monitor floors the age by how long it has seen
    the same value -- a 30 h wedge must not read as a few minutes."""
    h = Home(tmp_path, SAT_1200)
    h.exec_state(publish_ago=5)                       # value V, fresh
    h.run()
    later = SAT_1200 + dt.timedelta(hours=30)         # same V still there 30 h later
    h.set_now(later)
    state = json.load(open(h.paths["exec_state"], encoding="utf-8"))
    _wj(h.paths["exec_state"], state)
    out = h.run(later)
    ev = wf.exec_view(wf.collect(h.paths, h.run_cmd), later,
                      json.load(open(h.paths["monitor_state"], encoding="utf-8")))
    assert ev["publish_age"] >= 30 * 3600 - 5
    assert "exec_publish" in failing(out)


# -- ALWAYS: suppressing broker sends -------------------------------------------------------
def _append(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


SUPPRESS = ("[qqq-exec] broker lease check could not read Firestore (Timeout) -- "
            "suppressing broker sends this tick (fail-CLOSED for real orders)\n")


def test_suppress_streak_alerts_once_and_recovers(tmp_path):
    h = Home(tmp_path, MON_1030)
    _append(h.paths["exec_log"], SUPPRESS * 5)        # history before the first run
    assert "exec_suppress" not in failing(h.run())    # first sight counts nothing
    h.advance(MON_1030 + dt.timedelta(minutes=2))
    _append(h.paths["exec_log"], SUPPRESS * 3)
    h.exec_state(_broker_lease_ok=False, _broker_lease_reason="lease unverifiable: x")
    out = h.run()
    assert "exec_suppress" in failing(out)
    assert len(h.pushes) == 1
    h.advance(MON_1030 + dt.timedelta(minutes=4))
    _append(h.paths["exec_log"], SUPPRESS)            # still failing: no second push
    out = h.run()
    assert "exec_suppress" in failing(out) and len(h.pushes) == 1
    h.advance(MON_1030 + dt.timedelta(minutes=6))
    h.exec_state()                                    # lease ok again, no new lines
    out = h.run()
    assert "exec_suppress" not in failing(out)
    assert len(h.pushes) == 2 and "OK again" in h.pushes[1]["title"]


def test_suppress_scan_survives_copytruncate(tmp_path):
    h = Home(tmp_path, MON_1030)
    _append(h.paths["exec_log"], "x" * 5000 + "\n")
    h.run()
    h.advance(MON_1030 + dt.timedelta(minutes=2))
    _w(h.paths["exec_log"], SUPPRESS * 3)             # truncated, then 3 new lines
    h.exec_state(_broker_lease_ok=False)
    assert "exec_suppress" in failing(h.run())


# -- ALWAYS: tick loop, systemd, disk -------------------------------------------------------
def test_exec_loop_silent_over_ten_minutes(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.exec_state(loop_ago=9 * 60)
    assert "exec_loop" not in failing(h.run())
    h.exec_state(loop_ago=11 * 60)
    assert "exec_loop" in failing(h.run())


def test_failed_units_open_and_recover_per_unit(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.failed = ["logrotate.service"]
    out = h.run()
    assert "failed_unit:logrotate.service" in failing(out)
    assert len(h.pushes) == 1 and "logrotate.service" in h.pushes[0]["title"]
    h.failed = ["logrotate.service", "edgelog-qqq-bars.service"]
    h.advance(SAT_1200 + dt.timedelta(minutes=2))
    h.run()
    assert len(h.pushes) == 2 and "edgelog-qqq-bars" in h.pushes[1]["title"]
    h.failed = []
    h.advance(SAT_1200 + dt.timedelta(minutes=4))
    h.run()
    assert len(h.pushes) == 3 and "2 alert(s) closed" in h.pushes[2]["title"]
    assert h.status()["open_alerts"] == []


def test_systemctl_unavailable_skips_the_group(tmp_path):
    h = Home(tmp_path, SAT_1200)

    def boom(cmd, **kw):
        raise FileNotFoundError("systemctl")
    out = wf.run_once(h.paths, now=SAT_1200, push_fn=h.push_fn, run_cmd=boom,
                      log=lambda s: None)
    assert "systemd" not in out["status"]["groups_checked"]


def test_disk_and_log_size(tmp_path, monkeypatch):
    h = Home(tmp_path, SAT_1200)

    class DU:
        total, used, free = 100, 85, 15
    monkeypatch.setattr(wf.shutil, "disk_usage", lambda p: DU)
    monkeypatch.setattr(wf, "LOG_MAX_BYTES", 10)
    _w(os.path.join(h.paths["logs_dir"], "cloud_signal.log"), "y" * 50)
    out = h.run()
    assert {"disk", "log_size"} <= failing(out)


# -- SESSION --------------------------------------------------------------------------------
def test_engine_heartbeat_stale_needs_two_runs_lot_or_not(tmp_path):
    h = Home(tmp_path, MON_1030)
    h.engine_hb(MON_1030 - dt.timedelta(minutes=5))
    out = h.run()
    assert "engine_hb" in failing(out) and h.pushes == []      # first bad run: pending
    h.advance(MON_1030 + dt.timedelta(minutes=2))
    h.engine_hb(MON_1030 - dt.timedelta(minutes=5))
    h.run()
    assert len(h.pushes) == 1 and "signal engine STALLED" in h.pushes[0]["title"]
    h.advance(MON_1030 + dt.timedelta(minutes=4))
    h.engine_hb(h.now, ok=False)                                # fresh but ok=false: still bad
    h.run()
    assert len(h.pushes) == 1
    h.advance(MON_1030 + dt.timedelta(minutes=6))
    h.run()
    assert len(h.pushes) == 2 and "OK again" in h.pushes[1]["title"]


def test_engine_heartbeat_not_judged_off_hours(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.engine_hb(SAT_1200 - dt.timedelta(hours=5))
    out = h.run()
    assert "engine_hb" not in out["status"]["verdicts"]


def test_bar_age_fresh_stale_and_not_before_0941(tmp_path):
    h = Home(tmp_path, MON_1030)
    h.cs_state(newest_bar_start=et(2026, 10, 5, 10, 15))       # closed 10:20, 600 s ago
    assert "bar_age" not in failing(h.run())
    h.cs_state(newest_bar_start=et(2026, 10, 5, 10, 10))       # closed 10:15, 900 s ago
    assert "bar_age" in failing(h.run())
    early = et(2026, 10, 5, 9, 38)
    h2 = Home(tmp_path / "early", early)
    h2.cs_state(newest_bar_start=et(2026, 10, 2, 15, 55))      # Friday's last bar
    out = h2.run()
    assert "bar_age" not in out["status"]["verdicts"]


def test_bar_age_on_a_half_day_stops_at_the_1300_close(tmp_path):
    h = Home(tmp_path, et(2026, 11, 27, 12, 30))
    assert "session" in h.run()["status"]["groups_checked"]
    h.advance(et(2026, 11, 27, 13, 30))
    out = h.run()
    assert "session" not in out["status"]["groups_checked"]


def test_bar_source_yfinance_alerts_after_two_runs(tmp_path):
    h = Home(tmp_path, MON_1030)
    h.cs_state(source="yfinance")
    h.run()
    assert h.pushes == []
    h.advance(MON_1030 + dt.timedelta(minutes=2))
    h.run()
    assert len(h.pushes) == 1 and "yfinance" in h.pushes[0]["title"]


def test_tick_gap_current_and_daily_max(tmp_path):
    h = Home(tmp_path, MON_1030)
    h.exec_state(loop_ago=45)
    assert "tick_gap" in failing(h.run())
    h.advance(MON_1030 + dt.timedelta(minutes=2))
    h.exec_state(loop_ago=3, tick_gap_max_s_today=5.0)
    assert "tick_gap" not in failing(h.run())
    h.advance(MON_1030 + dt.timedelta(minutes=4))
    h.exec_state(loop_ago=3, tick_gap_max_s_today=290.0)       # a 290 s stall since last run
    assert "tick_gap" in failing(h.run())
    h.advance(MON_1030 + dt.timedelta(minutes=6))
    h.exec_state(loop_ago=3, tick_gap_max_s_today=290.0)       # no new stall
    assert "tick_gap" not in failing(h.run())


def test_shadow_heartbeat_is_medium(tmp_path):
    h = Home(tmp_path, MON_1030)
    h.shadow_hb(MON_1030 - dt.timedelta(minutes=30))
    h.run()
    h.advance(MON_1030 + dt.timedelta(minutes=2))
    h.shadow_hb(MON_1030 - dt.timedelta(minutes=30))
    out = h.run()
    assert out["opened"][0]["key"] == "shadow_hb" and out["opened"][0]["severity"] == wf.MEDIUM


def test_session_alert_closes_as_no_longer_checked_at_the_close(tmp_path):
    h = Home(tmp_path, et(2026, 10, 5, 15, 56))
    h.cs_state(source="yfinance")
    h.run()
    h.advance(et(2026, 10, 5, 15, 58))
    h.run()
    assert len(h.pushes) == 1
    h.advance(et(2026, 10, 5, 16, 0))
    h.run()
    assert len(h.pushes) == 2 and "No longer checked" in h.pushes[1]["message"]


# -- EOD ------------------------------------------------------------------------------------
def test_eod_checks_from_1610_urgent_when_missing(tmp_path):
    t = et(2026, 10, 5, 16, 12)
    h = Home(tmp_path, t)
    h.exec_state(eod_summary_done_date="2026-10-02",
                 _webull_flat_after_eod={"date": "2026-10-02", "flat": True, "shares": 0})
    h.cs_state(settled_days=["2026-10-02"])
    out = h.run()
    assert {"eod_summary", "webull_flat", "eod_settled"} <= failing(out)
    assert h.pushes[0]["priority"] == "urgent"
    h.advance(et(2026, 10, 5, 16, 14))
    h.exec_state()                                              # today's EOD all done
    h.cs_state()
    out = h.run()
    assert not ({"eod_summary", "webull_flat", "eod_settled"} & failing(out))


def test_eod_not_checked_before_1610_or_on_a_weekend(tmp_path):
    h = Home(tmp_path, et(2026, 10, 5, 15, 59))
    h.exec_state(eod_summary_done_date="2026-10-02")
    assert "eod" not in h.run()["status"]["groups_checked"]
    h2 = Home(tmp_path / "sat", et(2026, 10, 3, 16, 30))
    assert "eod" not in h2.run()["status"]["groups_checked"]


def test_eod_webull_still_holding_shares(tmp_path):
    t = et(2026, 10, 5, 16, 12)
    h = Home(tmp_path, t)
    h.exec_state(_webull_flat_after_eod={"date": "2026-10-05", "flat": False, "shares": 133})
    out = h.run()
    assert "webull_flat" in failing(out)
    assert "133" in out["status"]["verdicts"]["webull_flat"]["detail"]


def test_eod_on_a_half_day(tmp_path):
    t = et(2026, 11, 27, 16, 12)
    h = Home(tmp_path, t)
    out = h.run()
    assert "eod" in out["status"]["groups_checked"]
    assert not ({"eod_summary", "webull_flat", "eod_settled"} & failing(out))


# -- EVENING (19:00): NQ master + KEEL ------------------------------------------------------
def test_nq_master_and_keel_due_after_1900(tmp_path):
    t = et(2026, 10, 5, 19, 5)
    h = Home(tmp_path, t)
    h.bars(t, nq_day=dt.date(2026, 10, 2))                     # PC push did not land
    h.keel(through="2026-10-02")
    out = h.run()
    assert {"nq_master", "keel:NOISE_382_v12", "keel:NOISE_422_KEEL_v12"} <= failing(out)
    h.advance(et(2026, 10, 5, 19, 7))
    h.bars(t)                                                   # landed + rebuilt
    h.keel(through="2026-10-05")
    out = h.run()
    assert not ({"nq_master", "keel:NOISE_382_v12"} & failing(out))


def test_evening_before_1900_expects_the_previous_session(tmp_path):
    t = et(2026, 10, 5, 18, 0)
    h = Home(tmp_path, t)
    h.bars(t, nq_day=dt.date(2026, 10, 2))
    h.keel(through="2026-10-02")
    assert not ({"nq_master", "keel:NOISE_382_v12"} & failing(h.run()))


def test_evening_over_a_weekend_and_a_holiday(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.bars(SAT_1200, nq_day=dt.date(2026, 10, 2))
    h.keel(through="2026-10-02")
    assert not ({"nq_master", "keel:NOISE_382_v12"} & failing(h.run()))
    t = et(2026, 11, 26, 20, 0)                                 # Thanksgiving evening
    h2 = Home(tmp_path / "hol", t)
    h2.bars(t, nq_day=dt.date(2026, 11, 25))
    h2.keel(through="2026-11-25")
    assert not ({"nq_master", "keel:NOISE_382_v12"} & failing(h2.run()))


def test_keel_after_a_half_day_expects_the_session_before_it(tmp_path):
    t = et(2026, 11, 27, 19, 30)                                # half day evening
    h = Home(tmp_path, t)
    h.bars(t, nq_day=HALF_DAY)
    h.keel(through="2026-11-25")                                # short session dropped
    assert not ({"nq_master", "keel:NOISE_382_v12"} & failing(h.run()))
    assert wf.keel_expected(HALF_DAY) == dt.date(2026, 11, 25)


# -- PRE-OPEN GATE --------------------------------------------------------------------------
def test_preopen_pass_pushes_ready_once_a_day(tmp_path):
    h = Home(tmp_path, et(2026, 10, 5, 8, 30, 30))
    h.run()
    assert len(h.pushes) == 1 and "QQQ book ready" in h.pushes[0]["title"]
    h.advance(et(2026, 10, 5, 8, 32))
    h.run()                                                     # same slot: nothing
    h.advance(et(2026, 10, 5, 9, 16))
    h.run()                                                     # 09:15 slot passes: no repeat
    assert len(h.pushes) == 1
    assert h.status()["preopen"]["slots"]["09:15"]["misses"] == []


def test_preopen_miss_is_urgent_each_slot_then_ready_when_fixed(tmp_path):
    h = Home(tmp_path, et(2026, 10, 5, 8, 31))
    h.token(days_left=3)
    h.run()
    assert h.pushes[-1]["priority"] == "urgent"
    assert "expires in 3.0 days" in h.pushes[-1]["message"]
    assert any(a["key"] == "preopen" for a in h.status()["open_alerts"])
    h.advance(et(2026, 10, 5, 8, 45))
    h.run()                                                     # between slots: still open
    assert len(h.pushes) == 1
    assert any(a["key"] == "preopen" for a in h.status()["open_alerts"])
    h.advance(et(2026, 10, 5, 9, 15, 30))
    h.run()                                                     # still missing at 09:15
    assert len(h.pushes) == 2 and h.pushes[-1]["priority"] == "urgent"
    h2 = Home(tmp_path / "fixed", et(2026, 10, 5, 8, 31))
    h2.token(status="PENDING")
    h2.run()
    h2.advance(et(2026, 10, 5, 9, 16))
    h2.token()
    h2.run()
    assert "ready (fixed since" in h2.pushes[-1]["title"]
    assert h2.status()["open_alerts"] == []


def test_preopen_open_alert_expires_quietly_at_the_open(tmp_path):
    h = Home(tmp_path, et(2026, 10, 5, 9, 16))
    h.token(status="PENDING")
    h.run()
    n = len(h.pushes)
    h.advance(et(2026, 10, 5, 9, 31))
    h.run()
    assert len(h.pushes) == n
    assert h.status()["open_alerts"] == []


def test_preopen_each_miss(tmp_path):
    t = et(2026, 10, 5, 9, 16)
    h = Home(tmp_path, t)
    h.keel(through="2026-10-01")
    h.bars(t, d1_day=dt.date(2026, 9, 30))
    h.exec_state(publish_ago=300)                               # > max(90, 2x20)
    h.engine_hb(t - dt.timedelta(minutes=10))
    _w(h.paths["exec_kill"], "x")
    snap = wf.collect(h.paths, h.run_cmd)
    misses = wf.preopen_misses(snap, t, wf.exec_view(snap, t, {}))
    text = " | ".join(misses)
    for frag in ("KEEL NOISE_382_v12 trained through 2026-10-01", "QQQ_1d newest bar 2026-09-30",
                 "lease not fresh", "KILL file present", "signal engine heartbeat"):
        assert frag in text, frag


def test_preopen_passes_with_the_real_shaped_daily_cache(tmp_path):
    """Regression: before the open QQQ_1d cannot hold the previous session (the engine adds it
    at ~09:35). On the box at 08:30 Mon 10-05 the newest bar was Thu 10-01 -- the gate must pass
    on that, and a cache one more session behind must still miss."""
    t = et(2026, 10, 5, 8, 30, 20)
    h = Home(tmp_path, t)
    h.bars(t, d1_day=dt.date(2026, 10, 1))
    h.run()
    assert len(h.pushes) == 1 and "QQQ book ready" in h.pushes[0]["title"]
    h.bars(t, d1_day=dt.date(2026, 9, 30))
    snap = wf.collect(h.paths, h.run_cmd)
    assert any("QQQ_1d newest bar 2026-09-30, expected 2026-10-01" in m
               for m in wf.preopen_misses(snap, t, wf.exec_view(snap, t, {})))
    # Tuesday 08:30: Friday's bar is all the cache can hold (Monday's lands at 09:35)
    t2 = et(2026, 10, 6, 8, 30, 20)
    h2 = Home(tmp_path / "tue", t2)
    h2.bars(t2, d1_day=dt.date(2026, 10, 2))
    snap = wf.collect(h2.paths, h2.run_cmd)
    assert wf.preopen_misses(snap, t2, wf.exec_view(snap, t2, {})) == []


def test_qqq_1d_must_hold_the_previous_session_from_0940(tmp_path):
    t = et(2026, 10, 5, 9, 38)
    h = Home(tmp_path, t)
    h.bars(t, d1_day=dt.date(2026, 10, 1))                      # 09:35 refresh not landed
    assert "qqq_1d" not in h.run()["status"]["verdicts"]        # not judged before 09:40
    h.advance(et(2026, 10, 5, 9, 45))
    out = h.run()
    assert "qqq_1d" in failing(out) and h.pushes == []          # debounced: first bad run
    h.advance(et(2026, 10, 5, 9, 47))
    h.run()
    assert len(h.pushes) == 1 and "QQQ daily cache" in h.pushes[0]["title"]
    assert "expected 2026-10-02" in h.pushes[0]["message"]
    h.advance(et(2026, 10, 5, 9, 49))
    h.bars(h.now, d1_day=dt.date(2026, 10, 2))                  # refreshed
    out = h.run()
    assert "qqq_1d" not in failing(out) and "OK again" in h.pushes[-1]["title"]


def test_preopen_halt_only_counts_for_today(tmp_path):
    t = et(2026, 10, 5, 8, 31)
    h = Home(tmp_path, t)
    h.exec_state(trading_day="2026-10-02", breaker_tripped=True)  # yesterday's trip
    snap = wf.collect(h.paths, h.run_cmd)
    assert wf.preopen_misses(snap, t, wf.exec_view(snap, t, {})) == []


def test_token_is_never_read_into_any_output(tmp_path):
    h = Home(tmp_path, et(2026, 10, 5, 8, 31))
    h.token(days_left=2, status="PENDING")
    out = h.run()
    blobs = [json.dumps(out, default=str), json.dumps(h.pushes)]
    for p in (h.paths["status"], h.paths["monitor_state"], h.paths["outbox"],
              h.paths["heartbeat"]):
        blobs.append(open(p, encoding="utf-8").read())
    assert not any(FAKE_TOKEN in b for b in blobs)
    assert wf.read_token_meta(h.paths["token_files"][0])[1] == "PENDING"


# -- episodes + outbox ----------------------------------------------------------------------
def test_apply_verdicts_dedupes_and_recovers():
    alerts = {}
    bad = [wf._verdict("k", "g", False, wf.HIGH, "t", "d")]
    good = [wf._verdict("k", "g", True, wf.HIGH, "t")]
    o, r, e = wf.apply_verdicts(alerts, bad, {"g"}, 1.0, "L")
    assert len(o) == 1 and alerts["k"]["open"]
    o, r, e = wf.apply_verdicts(alerts, bad, {"g"}, 2.0, "L")
    assert o == [] and r == []
    o, r, e = wf.apply_verdicts(alerts, good, {"g"}, 3.0, "L")
    assert len(r) == 1 and alerts == {}
    o, r, e = wf.apply_verdicts(alerts, bad, {"g"}, 4.0, "L")   # a NEW episode pages again
    assert len(o) == 1


def test_apply_verdicts_unknown_leaves_the_episode_alone():
    alerts = {}
    wf.apply_verdicts(alerts, [wf._verdict("k", "g", False, wf.HIGH, "t", "d")], {"g"}, 1.0, "L")
    o, r, e = wf.apply_verdicts(alerts, [wf._verdict("k", "g", None, wf.HIGH, "t")], {"g"},
                                2.0, "L")
    assert (o, r, e) == ([], [], []) and alerts["k"]["open"]


def test_unreadable_exec_state_does_not_fake_a_recovery(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.exec_state(publish_ago=3600)
    h.run()
    assert len(h.pushes) == 1
    _w(h.paths["exec_state"], "{not json")
    h.run(SAT_1200 + dt.timedelta(minutes=2))
    assert all("OK again" not in p["title"] for p in h.pushes)
    assert any(a["key"] == "exec_publish" for a in h.status()["open_alerts"])


def test_outbox_keeps_a_failed_push_and_retries_next_run(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.failed = ["logrotate.service"]
    h.push_ok = False
    out = h.run()
    assert out["status"]["outbox_pending"] == 1
    box = json.load(open(h.paths["outbox"], encoding="utf-8"))
    assert box[0]["attempts"] == 1
    h.push_ok = True
    out = h.run(SAT_1200 + dt.timedelta(minutes=2))
    assert out["status"]["outbox_pending"] == 0
    assert h.pushes[-1]["message"].startswith("(delayed: raised")
    assert json.load(open(h.paths["outbox"], encoding="utf-8")) == []


def test_outbox_stops_at_first_failure_and_drops_after_12h():
    sent = []

    def push(m, t, p):
        sent.append(t)
        return False
    box = []
    wf.outbox_add(box, "a", "m", "high", 0.0)
    wf.outbox_add(box, "b", "m", "high", 0.0)
    left, n = wf.outbox_flush(box, push, 10.0, log=lambda s: None)
    assert sent == ["a"] and len(left) == 2 and n == 0
    left, n = wf.outbox_flush(left, push, 13 * 3600.0, log=lambda s: None)
    assert left == []


def test_dry_run_writes_nothing_and_pushes_nothing(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.failed = ["logrotate.service"]
    out = h.run(dry_run=True)
    assert out["pushes"] and h.pushes == []
    assert not os.path.exists(h.paths["status"])
    assert not os.path.exists(h.paths["monitor_state"])


# -- auto-restart gate ----------------------------------------------------------------------
def _sudo_calls(h):
    return [c for c in h.cmds if c[:1] == ["sudo"]]


def test_auto_restart_flag_off_never_restarts(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.exec_state(publish_ago=3600)
    lines = []
    out = wf.run_once(h.paths, now=SAT_1200, push_fn=h.push_fn, run_cmd=h.run_cmd,
                      log=lines.append)
    assert out["decision"]["action"] == "would_restart"
    assert _sudo_calls(h) == []
    assert any("would restart" in ln for ln in lines)
    out = h.run(SAT_1200 + dt.timedelta(minutes=2))
    assert out["decision"]["action"] == "blocked" and _sudo_calls(h) == []


def test_auto_restart_flag_on_outside_hours_flat_once_a_day(tmp_path):
    h = Home(tmp_path, SAT_1200)
    h.config(auto_restart_exec=True)
    h.exec_state(publish_ago=3600)
    out = h.run()
    assert out["decision"]["action"] == "restart"
    assert _sudo_calls(h) == [["sudo", "-n", "systemctl", "restart", "edgelog-qqq-exec.service"]]
    assert any("restarted the executor" in p["title"] for p in h.pushes)
    h.run(SAT_1200 + dt.timedelta(minutes=30))
    assert len(_sudo_calls(h)) == 1                              # cooldown
    h.run(SAT_1200 + dt.timedelta(minutes=62))
    assert len(_sudo_calls(h)) == 1                              # owner: once a day
    assert h.run(SAT_1200 + dt.timedelta(hours=11, minutes=50))["decision"]["why"] == \
        "at most once a day (owner rule 2026-10-05)"           # Sat 23:50, same day
    h.run(SAT_1200 + dt.timedelta(hours=24))                     # Sunday 12:00
    assert len(_sudo_calls(h)) == 2
    assert all(c[3:] == ["restart", "edgelog-qqq-exec.service"] for c in _sudo_calls(h))


def test_auto_restart_flag_on_blocked_in_hours_and_when_not_flat(tmp_path):
    t = et(2026, 10, 5, 12, 0)                                   # session day, in window
    h = Home(tmp_path, t)
    h.config(auto_restart_exec=True)
    h.exec_state(publish_ago=3600)
    assert h.run()["decision"]["why"].startswith("inside 09:25-16:10")
    h.exec_state(publish_ago=3600, legs={"NOISE": {"shares_remaining": 10}})
    out = h.run(et(2026, 10, 5, 18, 0))                          # after hours but holding
    assert out["decision"]["action"] == "blocked" and "flat" in out["decision"]["why"]
    h.exec_state(publish_ago=3600, _broker_resend={"x": {"intent": "CLOSE"}})
    assert h.run(et(2026, 10, 5, 18, 2))["decision"]["action"] == "blocked"
    assert _sudo_calls(h) == []


def test_restart_decision_rules():
    ev_down = {"publish_age": 700.0, "loop_age": 5.0, "flat": True, "renew": 20.0}
    ev_gap = {"publish_age": 5.0, "loop_age": 700.0, "flat": True, "renew": 20.0}
    ok = {"publish_age": 5.0, "loop_age": 5.0, "flat": True, "renew": 20.0}
    sat = et(2026, 10, 3, 12, 0)
    assert wf.restart_decision(sat, ok, {}, True)["action"] == "none"
    assert wf.restart_decision(sat, ev_down, {}, True)["action"] == "restart"
    assert wf.restart_decision(sat, ev_gap, {}, True)["action"] == "restart"
    assert wf.restart_decision(sat, ev_down, {}, False)["action"] == "would_restart"
    # session day: 09:24 allowed, 09:25 and 16:09 blocked, 16:10 allowed
    for hm, act in (((9, 24), "restart"), ((9, 25), "blocked"), ((16, 9), "blocked"),
                    ((16, 10), "restart")):
        assert wf.restart_decision(et(2026, 10, 5, *hm), ev_down, {}, True)["action"] == act
    # a holiday is not a session day: any time
    assert wf.restart_decision(et(2026, 11, 26, 12, 0), ev_down, {}, True)["action"] == "restart"
    recent = {"restart": {"last_restart_epoch": sat.timestamp() - 1800}}
    assert wf.restart_decision(sat, ev_down, recent, True)["why"] == "at most once per hour"
    today = {"restart": {"last_restart_epoch": sat.timestamp() - 5 * 3600,
                         "last_restart_day": "2026-10-03"}}
    assert wf.restart_decision(sat, ev_down, today, True)["why"].startswith("at most once a day")
    yday = {"restart": {"last_restart_epoch": sat.timestamp() - 13 * 3600,
                        "last_restart_day": "2026-10-02"}}
    assert wf.restart_decision(sat, ev_down, yday, True)["action"] == "restart"
    # 00:10 after a 23:40 restart: a new day, but still inside the hour floor
    late = {"restart": {"last_restart_epoch": et(2026, 10, 3, 23, 40).timestamp(),
                        "last_restart_day": "2026-10-03"}}
    assert wf.restart_decision(et(2026, 10, 4, 0, 10), ev_down, late, True)["why"] == \
        "at most once per hour"
    assert wf.restart_decision(sat, dict(ev_down, flat=None), {}, True)["action"] == "blocked"


def test_default_config_is_off(tmp_path):
    paths = wf.default_paths(str(tmp_path))
    assert wf.load_config(paths) == {"auto_restart_exec": False}


def test_restart_publish_bound_follows_the_offhours_cadence():
    """An unarmed executor publishes every 600 s: just before each publish a healthy one reads
    600-610 s old. That must never (would-)restart it; 1.5x the cadence is the bound."""
    sat = et(2026, 10, 3, 12, 0)
    healthy = {"publish_age": 605.0, "loop_age": 3.0, "flat": True, "renew": 600.0}
    assert wf.restart_decision(sat, healthy, {}, True)["action"] == "none"
    assert wf.restart_decision(sat, healthy, {}, False)["action"] == "none"
    down = dict(healthy, publish_age=901.0)
    assert wf.restart_decision(sat, down, {}, True)["action"] == "restart"


def test_offhours_unarmed_executor_never_would_restart(tmp_path):
    h = Home(tmp_path, SAT_1200, mode="OFF")
    h.exec_state(publish_ago=608, renew=600.0)
    out = h.run()
    assert out["decision"]["action"] == "none"
    assert "exec_publish" not in failing(out)


@pytest.mark.parametrize("value", ["false", "true", "0", "off", 1, "yes"])
def test_auto_restart_only_on_the_json_literal_true(tmp_path, value):
    h = Home(tmp_path, SAT_1200)
    h.config(auto_restart_exec=value)
    h.exec_state(publish_ago=3600)
    out = h.run()
    assert out["decision"]["action"] == "would_restart"
    assert out["status"]["auto_restart"]["enabled"] is False
    assert _sudo_calls(h) == []


# -- DST: last_publish_ok_et is a bare wall-clock time ----------------------------------------
def _publish_age(now, hms):
    snap = {"exec_state": {"last_publish_ok_et": hms, "legs": {}}}
    return wf.exec_view(snap, now, {})["publish_age"]


def test_publish_age_across_spring_forward():
    # 2026-03-08: 02:00 EST -> 03:00 EDT. A publish at 01:59:50 EST read at 03:00:05 EDT is
    # 15 s old, not an hour.
    now = dt.datetime(2026, 3, 8, 3, 0, 5, tzinfo=ET)
    assert abs(_publish_age(now, "01:59:50") - 15) < 1


def test_publish_age_across_fall_back():
    # 2026-11-01: 02:00 EDT -> 01:00 EST. A publish at 01:59:50 EDT read at 01:00:05 EST (the
    # repeated hour, fold=1) is 15 s old, not 23 h; one at 01:30 EST read at 01:40 EST is
    # 10 min old, not 70 min.
    now = dt.datetime(2026, 11, 1, 1, 0, 5, tzinfo=ET, fold=1)
    assert abs(_publish_age(now, "01:59:50") - 15) < 1
    now2 = dt.datetime(2026, 11, 1, 1, 40, 0, tzinfo=ET, fold=1)
    assert abs(_publish_age(now2, "01:30:00") - 600) < 1
    # an ordinary night: yesterday's 23:55 read at 00:05
    assert abs(_publish_age(et(2026, 10, 6, 0, 5), "23:55:00") - 600) < 1


# -- outbox: crash-safe and capped ----------------------------------------------------------
def test_outbox_saved_after_each_send_and_capped_per_run():
    saves, sent = [], []

    def push(m, t, p):
        sent.append(t)
        return True
    box = []
    for n in range(8):
        wf.outbox_add(box, f"p{n}", "m", "high", 0.0)
    left, n = wf.outbox_flush(box, push, 10.0, log=lambda s: None, save=saves.append)
    assert n == wf.OUTBOX_MAX_SENDS_PER_RUN == 5
    assert sent == ["p0", "p1", "p2", "p3", "p4"]
    assert [x["title"] for x in left] == ["p5", "p6", "p7"]
    assert [len(x) for x in saves] == [7, 6, 5, 4, 3]       # each delivered push already gone
    left, n = wf.outbox_flush(left, push, 20.0, log=lambda s: None)
    assert n == 3 and left == []


def test_run_killed_mid_flush_neither_resends_nor_repages(tmp_path):
    """Killed after one push went out and while sending the next: the delivered one is already
    off the outbox, and the episode the run opened is already saved, so the next run re-sends
    only the unconfirmed push and opens nothing new."""
    h = Home(tmp_path, SAT_1200)
    old = []
    wf.outbox_add(old, "older push", "m", "default", SAT_1200.timestamp() - 60)
    _wj(h.paths["outbox"], old)
    h.failed = ["logrotate.service"]
    titles = []

    def push_then_die(message, title, priority):
        titles.append(title)
        if len(titles) == 2:
            raise SystemExit("killed by systemd at TimeoutStartSec")
        return True
    with pytest.raises(SystemExit):
        wf.run_once(h.paths, now=SAT_1200, push_fn=push_then_die, run_cmd=h.run_cmd,
                    log=lambda s: None)
    state = json.load(open(h.paths["monitor_state"], encoding="utf-8"))
    assert state["alerts"]["failed_unit:logrotate.service"]["open"] is True
    left = json.load(open(h.paths["outbox"], encoding="utf-8"))
    assert [x["title"] for x in left] == [titles[1]]
    h.run(SAT_1200 + dt.timedelta(minutes=2))
    assert [p["title"] for p in h.pushes] == [titles[1]]     # the unconfirmed one, once
    assert titles[0] == "older push"


# -- review follow-ups (2026-10-05) ---------------------------------------------------------
def test_auto_restart_never_starts_a_unit_stopped_on_purpose(tmp_path):
    """`systemctl restart` STARTS an inactive unit: an executor the owner or a deploy lane
    stopped (`systemctl stop`) must stay stopped, flag on or off."""
    h = Home(tmp_path, SAT_1200)
    h.config(auto_restart_exec=True)
    h.exec_state(publish_ago=3600)
    h.unit_state = "inactive"
    lines = []
    out = wf.run_once(h.paths, now=SAT_1200, push_fn=h.push_fn, run_cmd=h.run_cmd,
                      log=lines.append)
    assert out["decision"]["action"] == "blocked"
    assert "stopped on purpose" in out["decision"]["why"]
    assert _sudo_calls(h) == []
    assert any("stopped on purpose" in ln for ln in lines)
    assert not any("restarted the executor" in p["title"] for p in h.pushes)
    # flag off: no "would restart" for a stopped unit either
    h2 = Home(tmp_path / "off", SAT_1200)
    h2.exec_state(publish_ago=3600)
    h2.unit_state = "inactive"
    assert h2.run()["decision"]["action"] == "blocked"


@pytest.mark.parametrize("state,acts", [("active", True), ("failed", True),
                                        ("activating", False), ("unknown", False)])
def test_auto_restart_only_for_an_active_or_failed_unit(tmp_path, state, acts):
    h = Home(tmp_path, SAT_1200)
    h.config(auto_restart_exec=True)
    h.exec_state(publish_ago=3600)
    h.unit_state = state
    out = h.run()
    assert (out["decision"]["action"] == "restart") is acts
    assert bool(_sudo_calls(h)) is acts


def test_exec_unit_state_when_systemctl_is_missing():
    def boom(cmd, **kw):
        raise FileNotFoundError("systemctl")
    assert wf.exec_unit_state(boom) == "unknown"


def test_restart_cooldown_is_saved_before_the_restart_runs(tmp_path):
    """A pass killed while `systemctl restart` runs (OOM, reboot, TimeoutStartSec) must not let
    the next pass, 2 minutes later, restart again: the cooldown is on disk first."""
    h = Home(tmp_path, SAT_1200)
    h.config(auto_restart_exec=True)
    h.failed = ["logrotate.service"]                 # an episode opened in the same pass
    h.exec_state(publish_ago=3600)

    def die():
        raise SystemExit("killed mid-restart")
    h.restart_hook = die
    with pytest.raises(SystemExit):
        h.run()
    assert len(_sudo_calls(h)) == 1
    state = json.load(open(h.paths["monitor_state"], encoding="utf-8"))
    assert state["restart"]["last_restart_epoch"] == SAT_1200.timestamp()
    assert state["restart"]["last_restart_day"] == "2026-10-03"
    assert state["alerts"]["failed_unit:logrotate.service"]["open"] is True
    queued = json.load(open(h.paths["outbox"], encoding="utf-8"))
    assert any("logrotate.service" in x["message"] for x in queued)  # its page is not lost
    h.restart_hook = None
    out = h.run(SAT_1200 + dt.timedelta(minutes=2))
    assert out["decision"]["why"].startswith("at most once a day")
    assert len(_sudo_calls(h)) == 1
    assert any("logrotate.service" in p["message"] for p in h.pushes)


def test_eod_flat_check_with_a_leftover_kill_file_is_high_not_urgent(tmp_path):
    """A KILL file from an earlier day: the executor skips flat_by (so the post-close flat check
    never runs). Still reported, but HIGH and saying the book is halted -- not a daily URGENT."""
    t = et(2026, 10, 5, 16, 12)
    h = Home(tmp_path, t)
    h.exec_state(kill_done=True, kill_flatten_date="2026-10-01",
                 _webull_flat_after_eod={"date": "2026-10-01", "flat": True, "shares": 0})
    _w(h.paths["exec_kill"], "x")
    out = h.run()
    v = out["status"]["verdicts"]["webull_flat"]
    assert v["ok"] is False and v["severity"] == wf.HIGH
    assert "HALTED by a KILL file" in v["detail"]
    assert h.pushes[-1]["priority"] == "high"
    # the order adapter's KILL alone does not stop the executor's flatten: still URGENT
    h2 = Home(tmp_path / "orders", t)
    h2.exec_state(_webull_flat_after_eod={"date": "2026-10-02", "flat": True, "shares": 0})
    _w(h2.paths["orders_kill"], "x")
    v2 = h2.run()["status"]["verdicts"]["webull_flat"]
    assert v2["severity"] == wf.URGENT and "KILL" not in v2["detail"]


def test_kill_fired_today_keeps_the_flat_check_urgent(tmp_path):
    t = et(2026, 10, 5, 16, 12)
    h = Home(tmp_path, t)
    h.exec_state(kill_done=True, kill_flatten_date="2026-10-05",
                 _webull_flat_after_eod={"date": "2026-10-05", "flat": False, "shares": 50})
    _w(h.paths["exec_kill"], "x")
    v = h.run()["status"]["verdicts"]["webull_flat"]
    assert v["severity"] == wf.URGENT and "50" in v["detail"]


def test_apply_verdicts_window_alert_closes_as_expired_not_recovered():
    alerts = {}
    bad = wf._verdict("box:preopen", "box", False, wf.URGENT, "t", "d")
    bad["window_alert"] = True
    wf.apply_verdicts(alerts, [bad], {"box"}, 1.0, "L")
    o, r, e = wf.apply_verdicts(alerts, [], {"box"}, 2.0, "L")
    assert r == [] and len(e) == 1 and alerts == {}
    # without the mark the same disappearance is a recovery
    wf.apply_verdicts(alerts, [wf._verdict("k", "box", False, wf.HIGH, "t", "d")], {"box"},
                      1.0, "L")
    o, r, e = wf.apply_verdicts(alerts, [], {"box"}, 2.0, "L")
    assert len(r) == 1 and e == []


def test_status_open_alerts_carry_quiet_expire_for_the_pc_relay(tmp_path):
    h = Home(tmp_path, et(2026, 10, 5, 9, 16))
    h.token(status="PENDING")
    h.run()
    po = [a for a in h.status()["open_alerts"] if a["key"] == "preopen"]
    assert po and po[0]["quiet_expire"] is True
