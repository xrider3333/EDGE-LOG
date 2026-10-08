"""tools/nt_night.py - the NinjaTrader end-of-day close and the two desktop switches (owner 2026-10-07).

A fake world replaces every seam (bridge, processes, nt_eod_safe.ps1, the repair, the 10s counts, the
fills file, pushes, the clock), so nothing here touches NinjaTrader, C:\\EdgeLog or ntfy. Pinned:
  * the order of the sequence and that night mode is written BEFORE anything is stopped;
  * flat -> strategies stopped by nt_eod_safe, clean exit; paper position with its stop -> force-close,
    nothing disabled, one push; paper position without a stop / REAL account open -> left on, push;
  * the 10s backfill gives up after 45 minutes and says so, without blocking the close;
  * the switches: one repair pass, an on-screen answer, no push; ON ends the window and starts NinjaTrader;
  * the automatic run's gates (time, trading day, once a day, skip file, already night).
"""
import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.nt_night as T  # noqa: E402
from api import nt_night_mode as nm  # noqa: E402
from api import ntfy_push  # noqa: E402

AZ = nm.LOCAL


def az(y, m, d, hh, mm, ss=20):
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=AZ)


WED_1320 = az(2026, 10, 7, 13, 20)        # 16:20 New York on a trading Wednesday
THU_0545 = az(2026, 10, 8, 5, 45, 0)

STRATS = [{"account": "DEMO7240108", "name": "EdgeLogNOISE", "state": "Realtime", "instrument": "MNQ 12-26",
           "position": "Flat 0"},
          {"account": "DEMO7240108", "name": "EdgeLogENGUQ1m", "state": "Realtime", "instrument": "NQ 12-26",
           "position": "Flat 0"}]
NQ_LONG = {"account": "DEMO7240108", "instrument": "NQ 12-26", "side": "Long", "qty": 1, "avg_price": 31000}
NQ_STOP = {"account": "DEMO7240108", "order_id": "s1", "instrument": "NQ 12-26", "action": "Sell",
           "type": "StopMarket", "state": "Working", "qty": 1, "stop": 30900}
REAL_POS = {"account": "1810769", "instrument": "MNQ 12-26", "side": "Short", "qty": 1, "avg_price": 31172}
REAL_ORD = {"account": "1810769", "order_id": "r1", "instrument": "MNQ 12-26", "action": "Buy",
            "type": "Limit", "state": "Working", "qty": 1}


def rth(bars=2340, delta=99.5, gap=0.0):
    return {"rth": {"bars": bars, "expected": 2340, "bars_pct": round(100.0 * bars / 2340, 1), "delta_pct": delta,
                    "unclassified_bars": 0, "rt_bars": bars, "longest_gap_min": gap,
                    "gap_start_et": "11:02" if gap else None}}


class World:
    def __init__(self, mp, tmp_path, now=WED_1320):
        self.t = now
        self.mono = 0.0
        self.calls = []                      # ordered record of every action
        self.pids = [4242]
        self.bridge = {"/health": {"ok": True}, "/positions": {"positions": []}, "/orders": {"orders": []},
                       "/strategies": {"strategies": [dict(s) for s in STRATS]},
                       "/executions": {"executions": [{"exec_id": "e1"}, {"exec_id": "e2"}]}}
        self.eod_rc = None                   # None = 0 when flat, 2 when a position is open
        self.on_eod_safe = None
        self.capture = lambda inst, day: rth()
        self.fills = {"e1", "e2"}
        self.pushes = []
        self.recover = []                    # successive answers of recover_running()
        self.state_at_eod_safe = None
        self.kill_raises = False
        self.backup = False
        mp.setattr(T, "_now", lambda: self.t)
        mp.setattr(T, "_mono", lambda: self.mono)
        mp.setattr(T, "_sleep", self.sleep)
        mp.setattr(T, "bridge_get", self.get)
        mp.setattr(T, "bridge_post", self.post)
        mp.setattr(T, "nt_pids", lambda: list(self.pids))
        mp.setattr(T, "kill_nt", self.kill)
        mp.setattr(T, "recover_running", lambda: self.recover.pop(0) if self.recover else False)
        mp.setattr(T, "run_eod_safe", self.eod_safe)
        mp.setattr(T, "run_repair", self.repair)
        mp.setattr(T, "capture", lambda inst, day: self.capture(inst, day))
        mp.setattr(T, "backup_done", lambda day: self.backup)
        mp.setattr(T, "run_backup", self.run_backup)
        mp.setattr(T, "fills_ids", lambda: set(self.fills))
        mp.setattr(T, "push", self.push)
        mp.setattr(T, "start_recover", lambda: self.calls.append("start_recover") or "started the watchdog task now")
        mp.setattr(T, "take_lock", lambda: True)

    # seams
    def sleep(self, s):
        self.mono += s
        self.t += dt.timedelta(seconds=s)

    def get(self, path, timeout=8):
        if self.pids == []:
            return None                      # NinjaTrader closed: nothing answers
        return self.bridge.get(path)

    def post(self, path, timeout=8):
        self.calls.append("post " + path)
        if path == "/shutdown":
            self.pids = []
        return True

    def kill(self):
        self.calls.append("kill")
        if self.kill_raises:
            raise RuntimeError("boom")
        self.pids = []

    def eod_safe(self, whatif):
        self.calls.append("eod_safe whatif=%s" % whatif)
        self.state_at_eod_safe = nm.read_state()
        pos = self.bridge["/positions"]["positions"]
        rc = self.eod_rc if self.eod_rc is not None else (2 if pos else 0)
        if rc == 0 and not whatif:
            for s in self.bridge["/strategies"]["strategies"]:
                s["state"] = "Terminated"
            self.calls.append("strategies stopped")
        if self.on_eod_safe:
            self.on_eod_safe()
        return rc, ["eod-safe said %d" % rc]

    def repair(self, dry):
        self.calls.append("repair dry=%s" % dry)
        return 0, ["NQ: nothing to merge"]

    def run_backup(self):
        self.calls.append("backup")
        return "[nt-backup] 2026-10-07 snapshot complete"

    def push(self, note):
        assert ntfy_push.lint(note) == [], ntfy_push.lint(note)
        self.pushes.append(note)
        return True

    def log(self):
        try:
            return open(nm.LOG_PATH, encoding="utf-8").read()
        except OSError:
            return ""

    def last(self):
        return open(nm.LAST_PATH, encoding="ascii").read()


@pytest.fixture
def w(monkeypatch, tmp_path):
    return World(monkeypatch, tmp_path)


def state():
    return nm.read_state()


# -- the normal flat evening ---------------------------------------------------------------------------
def test_flat_evening_backs_up_repairs_stops_cleanly_and_sets_the_window(w):
    assert T.main(["eod"]) == 0
    order = [c for c in w.calls if c in ("backup", "repair dry=False", "eod_safe whatif=False", "post /shutdown", "kill")]
    assert order == ["backup", "repair dry=False", "eod_safe whatif=False", "post /shutdown"]
    a = state()["active"]
    assert nm.to_local(a["until"]) == THU_0545
    assert a["how"] == "clean" and a["flat"] is True and a["closed_at"]
    # night mode was ALREADY on when the strategies were stopped (the watchdog cannot re-enable them)
    assert w.state_at_eod_safe["active"]["how"] == "closing"
    assert w.pushes == []                                              # a normal night pushes nothing
    assert state()["eod"]["day"] == "2026-10-07" and state()["eod"]["result"] == "night-clean"
    assert w.last().startswith("NinjaTrader is OFF until 05:45.")
    log = w.log()
    assert log.splitlines()[0].split("  ", 1)[1] == nm.CAVEAT          # the caveat is the first log line
    assert "all 2 executions of this session are in fills.csv" in log
    assert "today's session is complete" in log


def test_strategies_are_stopped_only_in_a_quiet_second(w):
    w.t = az(2026, 10, 7, 13, 20, 55)                                  # :55 -> waits for :15..:40
    seen = []
    w.on_eod_safe = lambda: seen.append(w.t.second)
    T.main(["eod"])
    lo, hi = nm.QUIET_SECONDS
    assert seen and lo <= seen[0] <= hi


def test_a_running_watchdog_pass_finishes_before_anything_is_stopped(w):
    w.recover = [True, True, False]
    T.main(["eod"])
    assert "a watchdog pass is running" in w.log() and "the watchdog pass finished" in w.log()
    assert w.calls.index("eod_safe whatif=False") > 0


def test_clean_exit_falls_back_to_a_kill_when_ninjatrader_will_not_close(w, monkeypatch):
    monkeypatch.setattr(T, "bridge_post", lambda path, timeout=8: w.calls.append("post " + path) or True)
    T.main(["eod"])
    assert "kill" in w.calls and state()["active"]["how"] == "clean-then-killed"


# -- a paper trade open at the close -------------------------------------------------------------------
def test_paper_position_with_its_stop_is_force_closed_nothing_disabled_one_push(w):
    w.bridge["/positions"] = {"positions": [NQ_LONG]}
    w.bridge["/orders"] = {"orders": [NQ_STOP]}
    w.bridge["/strategies"]["strategies"][1]["position"] = "Long 1"
    T.main(["eod"])
    assert "kill" in w.calls and "post /shutdown" not in w.calls and "strategies stopped" not in w.calls
    a = state()["active"]
    assert a["how"] == "killed-with-position" and a["flat"] is False and a["position"] == ["ENGU-Q's NQ trade"]
    assert len(w.pushes) == 1
    n = w.pushes[0]
    assert n["title"] == "NinjaTrader: night mode" and n["priority"] == nm.PRIORITY_CLOSED_WITH_POSITION
    assert "keeps its stop, but nothing trails it until 05:45" in n["message"]
    assert "stays open with its stop at the broker" in w.last()


def test_paper_position_without_a_stop_is_left_on_and_pages_high(w):
    w.bridge["/positions"] = {"positions": [NQ_LONG]}
    T.main(["eod"])
    assert "kill" not in w.calls and "post /shutdown" not in w.calls
    assert not any(c.startswith("eod_safe") for c in w.calls)
    assert (state().get("active") or None) is None
    assert w.pushes[0]["title"] == "NinjaTrader: CHECK NOW" and w.pushes[0]["priority"] == "high"
    assert "unprotected" in w.pushes[0]["message"]
    assert state()["eod"]["result"] == "left-on-no-stop"


def test_a_stop_for_less_than_the_position_counts_as_no_stop(w):
    w.bridge["/positions"] = {"positions": [dict(NQ_LONG, qty=2)]}
    w.bridge["/orders"] = {"orders": [NQ_STOP]}
    T.main(["eod"])
    assert "kill" not in w.calls and state()["eod"]["result"] == "left-on-no-stop"


# -- the owner's REAL account --------------------------------------------------------------------------
@pytest.mark.parametrize("pos,orders", [([REAL_POS], []), ([], [REAL_ORD])])
def test_real_account_open_leaves_ninjatrader_on_tonight(w, pos, orders):
    w.bridge["/positions"] = {"positions": pos}
    w.bridge["/orders"] = {"orders": orders}
    T.main(["eod"])
    assert "kill" not in w.calls and "post /shutdown" not in w.calls
    assert not any(c.startswith("eod_safe") for c in w.calls)
    assert (state().get("active") or None) is None
    assert [p["title"] for p in w.pushes] == ["NinjaTrader: left on"]
    assert w.pushes[0]["priority"] == nm.PRIORITY_LEFT_ON_REAL == "default"
    assert "real account" in w.pushes[0]["message"]
    # the second trigger the same afternoon does nothing (one push a night)
    w.t += dt.timedelta(hours=1)
    T.main(["eod"])
    assert len(w.pushes) == 1 and "already ran today" in w.log()


# -- NinjaTrader already closed / hung -----------------------------------------------------------------
def test_ninjatrader_not_running_just_sets_the_window(w):
    w.pids = []
    T.main(["eod"])
    assert "kill" not in w.calls and state()["active"]["how"] == "already-closed"


def test_hung_ninjatrader_is_waited_on_then_force_closed(w, monkeypatch):
    monkeypatch.setattr(T, "bridge_get", lambda path, timeout=8: None)      # process up, nothing answers
    T.main(["eod"])
    assert "kill" in w.calls and state()["active"]["how"] == "killed-unresponsive"
    assert w.mono >= nm.BRIDGE_WAIT_MIN * 60


def test_ninjatrader_up_but_positions_unreadable_is_left_on(w):
    w.bridge["/positions"] = None
    T.main(["eod"])
    assert "kill" not in w.calls and (state().get("active") or None) is None
    assert w.pushes[0]["title"] == "NinjaTrader: needs a fix"


# -- the 10s backfill ----------------------------------------------------------------------------------
def test_backfill_gap_retries_every_5_min_gives_up_after_45_and_still_closes(w):
    w.capture = lambda inst, day: rth(bars=2200, delta=70.0, gap=4.0)
    T.main(["eod"])
    passes = [c for c in w.calls if c == "repair dry=False"]
    assert len(passes) == nm.BACKFILL_GIVE_UP_MIN // nm.BACKFILL_RETRY_MIN + 1
    assert "GAVE UP after 45 min" in w.log() and "longest gap 4.0 min from 11:02 New York" in w.log()
    assert "post /shutdown" in w.calls and state()["active"]["how"] == "clean"
    assert "10s data has a gap (logged)" in w.last()
    assert w.pushes == []                                # order-flow gaps are api/delta_alarm.py's to push


def test_backfill_that_completes_on_a_later_pass_stops_waiting(w):
    seq = iter([rth(bars=2300), rth(bars=2300), rth()] + [rth()] * 10)
    w.capture = lambda inst, day: next(seq) if inst == "NQ" else rth()
    T.main(["eod"])
    assert len([c for c in w.calls if c == "repair dry=False"]) == 3


def test_missing_fills_are_waited_for_then_logged(w):
    w.fills = {"e1"}
    T.main(["eod"])
    assert "1 of 2 executions are NOT in fills.csv after 3 min (e2)" in w.log()
    assert "post /shutdown" in w.calls


# -- races ---------------------------------------------------------------------------------------------
def test_a_position_that_opens_while_stopping_clears_night_mode_and_pages(w):
    def opened():
        w.bridge["/positions"] = {"positions": [NQ_LONG]}
    w.on_eod_safe = opened
    T.main(["eod"])
    assert "post /shutdown" not in w.calls and "kill" not in w.calls
    assert (state().get("active") or None) is None                        # the watchdog takes it back
    assert w.pushes[0]["title"] == "NinjaTrader: CHECK NOW" and w.pushes[0]["priority"] == "high"


def test_eod_safe_failing_leaves_ninjatrader_on(w):
    w.eod_rc = 5
    T.main(["eod"])
    assert "post /shutdown" not in w.calls and (state().get("active") or None) is None
    assert w.pushes[0]["title"] == "NinjaTrader: needs a fix"


def test_a_crash_while_closing_puts_the_watchdog_back_in_charge(w):
    w.bridge["/positions"] = {"positions": [NQ_LONG]}
    w.bridge["/orders"] = {"orders": [NQ_STOP]}
    w.kill_raises = True
    assert T.main(["eod"]) == 2
    assert (state().get("active") or None) is None and "CRASHED" in w.log()


def test_pressing_on_during_the_run_keeps_ninjatrader_on(w):
    orig = w.capture

    def press(inst, day):
        if inst == "NQ":
            T.cmd_on()
        return orig(inst, day)
    w.capture = press
    T.main(["eod"])
    assert "post /shutdown" not in w.calls and (state().get("active") or None) is None
    assert "pressed NinjaTrader ON during this run" in w.log()


# -- dry run -------------------------------------------------------------------------------------------
def test_dry_run_changes_nothing(w):
    assert T.main(["eod", "--dry-run"]) == 0
    assert state() == {}
    assert "eod_safe whatif=True" in w.calls and "repair dry=True" in w.calls
    assert not any(c in w.calls for c in ("kill", "post /shutdown", "backup", "strategies stopped"))
    assert w.pushes == [] and not os.path.exists(nm.LAST_PATH)
    assert "DRY RUN: account flat" in w.log()


# -- the desktop switches ------------------------------------------------------------------------------
def test_off_switch_one_repair_pass_no_push_answer_on_screen(w):
    w.t = az(2026, 10, 7, 19, 30)
    w.capture = lambda inst, day: rth(bars=2000)
    w.bridge["/positions"] = {"positions": [NQ_LONG]}
    w.bridge["/orders"] = {"orders": [NQ_STOP]}
    assert T.main(["off"]) == 0
    assert len([c for c in w.calls if c == "repair dry=False"]) == 1
    assert w.pushes == []                                               # PUSH_FROM_SWITCH is False
    assert w.last().startswith("NinjaTrader is OFF until 05:45. ENGU-Q's NQ trade stays open")
    assert "eod" not in state()                                         # does not use up the automatic run


def test_off_switch_refuses_with_the_real_account_open(w):
    w.bridge["/orders"] = {"orders": [REAL_ORD]}
    T.main(["off"])
    assert "kill" not in w.calls and w.last().startswith("NinjaTrader left ON: your real account")


def test_on_switch_ends_the_window_and_starts_ninjatrader(w):
    T.main(["eod"])
    assert nm.active(now=w.t)
    w.t = az(2026, 10, 7, 20, 0)
    assert T.main(["on"]) == 0
    st = state()
    assert st["active"] is None and st["history"][-1]["ended"] == nm.iso(az(2026, 10, 7, 20, 0))
    assert "start_recover" in w.calls and w.last().startswith("Night mode is off. NinjaTrader is starting")


def test_skip_command_then_next_end_of_day_leaves_it_on_once(w):
    T.main(["skip"])
    T.main(["eod"])
    assert "post /shutdown" not in w.calls and state()["eod"]["result"] == "skipped-file"
    assert not os.path.exists(nm.SKIP_PATH)                             # used up: one night only
    assert [f for f in os.listdir(os.path.dirname(nm.SKIP_PATH)) if f.startswith("nt_night_mode.SKIP.done-")]


# -- the automatic run's gates -------------------------------------------------------------------------
@pytest.mark.parametrize("now,why", [
    (az(2026, 10, 7, 13, 10), "too early"),                 # 16:10 New York
    (az(2026, 10, 10, 13, 20), "not a trading day"),        # Saturday
    (az(2026, 11, 26, 14, 20), "not a trading day"),        # Thanksgiving
])
def test_gates(w, now, why):
    w.t = now
    T.main(["eod"])
    assert why in w.log() and not any(c.startswith("eod_safe") for c in w.calls)


def test_winter_clock_runs_from_the_later_trigger(w):
    w.t = az(2026, 12, 2, 13, 15)                           # 15:15 New York in winter -> too early
    T.main(["eod"])
    assert "too early" in w.log() and not w.calls
    w.t = az(2026, 12, 2, 14, 15)                           # 16:15 New York -> runs
    T.main(["eod"])
    assert "post /shutdown" in w.calls


def test_an_owner_off_earlier_today_means_the_automatic_run_leaves_it_alone(w):
    w.t = az(2026, 10, 7, 10, 0)
    T.main(["off"])
    w.calls.clear()
    w.pids = [99]                                           # the owner reopened NinjaTrader by hand
    w.t = WED_1320
    T.main(["eod"])
    assert w.calls == [] and "night mode is already on" in w.log()


def test_disabled_setting_does_nothing(w, monkeypatch):
    monkeypatch.setattr(nm, "ENABLED", False)
    T.main(["eod"])
    assert w.calls == [] and "ENABLED = False" in w.log()


def test_friday_close_runs_to_monday_morning(w):
    w.t = az(2026, 10, 9, 13, 20)
    T.main(["eod"])
    assert nm.to_local(state()["active"]["until"]) == az(2026, 10, 12, 5, 45, 0)
    assert w.last().startswith("NinjaTrader is OFF until Mon 05:45.")


def test_status_prints_without_touching_anything(w, capsys):
    T.main(["eod"])
    before = json.dumps(state(), sort_keys=True)
    capsys.readouterr()
    assert T.main(["status", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["night_mode"]["active"] is True and info["night_mode"]["until_hhmm"] == "05:45"
    T.main(["status"])
    assert "night mode: ON until 05:45 (end of day, clean)" in capsys.readouterr().out
    assert json.dumps(state(), sort_keys=True) == before


def test_pressing_on_while_the_strategies_stop_keeps_ninjatrader_open(w):
    w.on_eod_safe = lambda: T.cmd_on()
    T.main(["eod"])
    assert "post /shutdown" not in w.calls and "kill" not in w.calls
    assert (state().get("active") or None) is None and "start_recover" in w.calls
