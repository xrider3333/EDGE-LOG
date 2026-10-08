"""tests/test_webull_push_plan_phone.py -- the WEBULL PUSH PLAN 10-07 (MANAGER #86, GO 10-08):
C:\\EdgeLog\\manager\\paperwb_1007\\WEBULL_PUSH_PLAN_1007.md built on the owner's plain phone
contract (api/ntfy_push.plain / dedupe / lint).

  1. api/qqq_exec.py: every push goes through _say() (plain text + the shared repeat rule);
     the benign / other-owner sites keep only their log line and timeline event; a send that
     FAILED (False) does not count, "no topic set" (None) does -- a box with no topic never
     loops.
  2. api/cloud_signal.py: the KEEL push goes through api/ntfy_push (NTFY_TOKEN / NTFY_SERVER)
     and only for a REAL fallback to 1.0; staleness within KEEL_MAX_STALE_SESSIONS is a fact
     for state.json and the log.
  3. "NQ data did not reach the box": ONE push per missed night across the box monitor
     (tools/webull_freshness.py nq_master, from 18:00 ET), tools/keel_live_state.py (marker,
     no push) and the pre-open gate; a second only when the model reaches its fallback age.

No network, no live files: every sender is a fake, every path is under tmp_path.
"""
import datetime as dt
import inspect
import json
import os
import sys

import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for p in (ROOT, THIS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import api.cloud_signal as cs  # noqa: E402
import tools.keel_live_state as kls  # noqa: E402
import tools.webull_freshness as wf  # noqa: E402
from api import ntfy_push  # noqa: E402
from api import qqq_exec as qe  # noqa: E402
from api import webull_orders  # noqa: E402
from test_cloud_signal_keel import _arrays, _fitted_state, _write_state  # noqa: E402
from test_webull_freshness import Home, et  # noqa: E402

NOOP = lambda *a, **k: None  # noqa: E731


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


@pytest.fixture
def notes(monkeypatch):
    """Every executor push, as the note it would put on the phone."""
    out = []

    def fake(msg, title, log=print, priority=None):
        out.append({"title": title, "message": msg, "priority": priority})
        return True
    monkeypatch.setattr(qe, "_notify", fake)
    return out


def _lint_all(ns):
    assert ns, "expected at least one push"
    for n in ns:
        assert ntfy_push.lint(n) == [], n


def _events(state):
    return [e.get("text", "") for e in state.get("events", [])]


# == 1. api/qqq_exec.py ========================================================================
def test_every_executor_push_goes_through_say():
    """Structural: _notify is called from exactly one place -- _say -- so no push can skip the
    plain text and the repeat rule again."""
    src = inspect.getsource(qe)
    calls = src.count("_notify(") - src.count("def _notify(")
    assert calls == 1
    assert "_notify(note[\"message\"], note[\"title\"]" in inspect.getsource(qe._say)


def test_say_repeat_rule_once_worse_then_daily(notes, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    st = {}
    hi = ntfy_push.plain("QQQ book", "CHECK NOW", "x is late", "The x sell did not go through",
                         "nothing yet", priority="high")
    ur = dict(hi, priority="urgent")
    assert qe._say(st, "exit:NOISE", "d1", hi)[0] == "push"
    assert qe._say(st, "exit:NOISE", "d1", hi) == (None, None)        # same problem: held
    clock[0] += 3600
    assert qe._say(st, "exit:NOISE", "d1", ur)[0] == "push"           # worse: at once
    assert qe._say(st, "exit:NOISE", "d1", ur)[0] is None
    clock[0] += 24 * 3600
    assert qe._say(st, "exit:NOISE", "d1", ur)[0] == "push"           # a day on: once more
    assert len(notes) == 3
    qe._say_clear(st, "exit:NOISE")                                   # episode over
    assert qe._say(st, "exit:NOISE", "d1", hi)[0] == "push"
    assert "exit:NOISE" in st["_phone_dedupe"], "the memory rides in state.json"


def test_say_a_failed_send_does_not_count_but_no_topic_does(monkeypatch):
    results = [False, True]
    sent = []

    def fake(msg, title, log=print, priority=None):
        sent.append(title)
        return results.pop(0)
    monkeypatch.setattr(qe, "_notify", fake)
    st = {}
    note = qe._kill_note()
    assert qe._say(st, "kill", "d1", note) == ("push", False)
    assert "kill" not in st.get("_phone_dedupe", {}), "a failed send leaves no memory"
    assert qe._say(st, "kill", "d1", note) == ("push", True)          # tried again
    assert qe._say(st, "kill", "d1", note) == (None, None)
    # no topic set: the real _notify returns None -- counted as done, never looped
    monkeypatch.undo()
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    st2 = {}
    assert qe._say(st2, "kill", "d1", note) == ("push", None)
    assert qe._say(st2, "kill", "d1", note) == (None, None)


def test_firestore_alert_keeps_none_and_false_apart(monkeypatch):
    """The database alert retries its page while the send FAILED (False) and stops on None
    (no topic set) -- now through _say, which must hand both back unchanged."""
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)

    class _Client:
        def collection(self, name):
            return self

    # no topic: the real sender returns None -> the episode's page is spent, no loop
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    h = qe._as_firestore_handle(_Client())
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError("503 wedged"), now=1000.0)
    st = {}
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=1000.0) == "alerted"
    assert qe._FS_HEALTH.alerted is True
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP,
                                       now=1000.0 + qe.FS_ALERT_RETRY_SEC + 1) is None

    # a failed send: tried again after the spacing, and it is the plain note both times
    qe._FS_HEALTH.__init__()
    results, sent = [False, True], []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        (sent.append({"title": title, "message": msg, "priority": priority}),
                         results.pop(0))[1])
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError("503 wedged"), now=5000.0)
    st = {}
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=5000.0) == "alerted"
    assert qe._FS_HEALTH.alerted is False
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP,
                                       now=5000.0 + qe.FS_ALERT_RETRY_SEC) == "alerted"
    assert qe._FS_HEALTH.alerted is True and len(sent) == 2
    _lint_all(sent)
    assert sent[0]["priority"] == "high" and "cloud database" in sent[0]["message"]


def test_entry_and_exit_notes(notes, monkeypatch):
    st = {"events": []}
    raw = ("ServerException: HTTP Status: 417, Code: "
           "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION_OPEN, Msg: x, RequestID: r1")
    # B: a missed entry -- high, ONCE per strategy per day (the give-up folds into it)
    qe._alert_broker_not_ok(st, leg="ENGUQ", intent="OPEN", side="BUY", shares=5, reason=raw,
                            log=NOOP)
    qe._say_entry_missed(st, "ENGUQ", "The ENGU-Q buy never reached Webull (the re-sends "
                         "gave up)", log=NOOP)
    assert len(notes) == 1
    assert notes[0]["title"] == "QQQ book: entry missed" and notes[0]["priority"] == "high"
    assert "ENGU-Q" in notes[0]["message"] and "ENGUQ" not in notes[0]["message"]
    # A: the first exit failure is high; the give-up is urgent (worse: pushes)
    qe._alert_broker_not_ok(st, leg="NOISE", intent="CLOSE", side="SELL", shares=10,
                            reason="insufficient position", log=NOOP)
    qe._say_exit_stuck(st, "NOISE", "The NOISE sell gave up at 12:59 (still not sent)",
                       log=NOOP)
    assert [n["priority"] for n in notes[1:]] == ["high", "urgent"]
    assert "not enough shares to sell" in notes[1]["message"]
    # the Webull-only repair gave up: urgent, legs in words
    n = qe._repair_gave_up_note(["NOISE", "ENGUQ"])
    assert n["priority"] == "urgent" and "NOISE and ENGU-Q" in n["message"]
    notes.append(n)
    _lint_all(notes)
    assert any("NOT OK" in t and "already holds the opposite side" in t for t in _events(st))


def test_after_the_bell_sell_is_urgent(notes, monkeypatch):
    class _A:
        def status(self):
            return {"effective_mode": "PAPER",
                    "believed_positions": {"NOISE": {"qty": 10}},
                    "broker_sent_positions": {"NOISE": {"qty": 10}}}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _A())
    st = {"events": []}
    now = dt.datetime(2026, 10, 8, 16, 1, 0)
    qe._alert_close_blocked_after_close(st, "NOISE", now, log=NOOP)
    qe._alert_close_blocked_after_close(st, "NOISE", now, log=NOOP)
    assert len(notes) == 1 and notes[0]["priority"] == "urgent"
    assert "came after the close at 13:01" in notes[0]["message"], "owner's clock, not ET"
    _lint_all(notes)


def test_the_after_bell_fact_is_not_held_behind_a_stuck_sell(notes, monkeypatch):
    """Review fix: an urgent 'sell is stuck' earlier the same day (same leg, no reset) must
    not swallow the after-the-bell note -- it carries its own problem id."""
    class _A:
        def status(self):
            return {"effective_mode": "PAPER",
                    "believed_positions": {"NOISE": {"qty": 10}},
                    "broker_sent_positions": {"NOISE": {"qty": 10}}}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _A())
    st = {"events": []}
    qe._say_exit_stuck(st, "NOISE", "The NOISE sell is stuck (no answer from Webull)",
                       log=NOOP)
    qe._say_exit_stuck(st, "NOISE", "The NOISE sell is stuck (no answer from Webull)",
                       log=NOOP)
    assert len(notes) == 1
    qe._alert_close_blocked_after_close(st, "NOISE", dt.datetime(2026, 10, 8, 16, 1, 0),
                                        log=NOOP)
    assert len(notes) == 2 and notes[1]["priority"] == "urgent"
    assert "came after the close" in notes[1]["message"]
    _lint_all(notes)


class _HungFut:
    def done(self):
        return False


def test_a_flapping_reconcile_holds_once_a_day(notes):
    """Group C, hold:reconcile: re-entered every 30 s while halted, and flapping in and out of
    MISMATCH all morning -- one 'orders on hold' note that day."""
    st = {"events": []}
    for _ in range(5):
        qe._maybe_notify_reconcile_halt(st, "MISMATCH", "ORB off by 5", log=NOOP)
        qe._maybe_notify_reconcile_halt(st, "READ FAILURE", "timeout", log=NOOP)
    assert len(notes) == 1
    assert notes[0]["title"] == "QQQ book: orders on hold" and notes[0]["priority"] == "high"
    assert "new QQQ entries wait" in notes[0]["message"]
    _lint_all(notes)


def test_a_flapping_reconcile_pushes_at_most_once_a_new_york_day(notes, monkeypatch):
    """10-08 review: the reconcile hold's episode ends after RECONCILE_HOLD_CLEAR_OKS agreeing
    looks, so a reconcile that flaps all day used to push once per flap. Now the cause pushes
    at most once per New York day -- whatever the kind (mismatch or unreadable) -- and the
    next New York day pushes again. A send that FAILED does not use up the day."""
    clock = [dt.datetime(2026, 10, 8, 10, 0, tzinfo=qe._NY).timestamp()]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    st = {"events": []}

    def flap(kind="MISMATCH"):
        qe._maybe_notify_reconcile_halt(st, kind, "ORB off by 5", log=NOOP)
        for _ in range(qe.RECONCILE_HOLD_CLEAR_OKS):
            clock[0] += 300
            qe._note_reconcile_agreed(st, log=NOOP)
        st["_reconcile_ok_streak"] = 0
        clock[0] += 300

    for kind in ("MISMATCH", "READ FAILURE", "MISMATCH", "MISMATCH"):
        flap(kind)
    assert len(notes) == 1 and notes[0]["title"] == "QQQ book: orders on hold"
    assert st["_hold_pushed_day"] == {"reconcile": "2026-10-08"}
    # a late-evening flap (after midnight UTC, still 10-08 in New York): still capped
    clock[0] = dt.datetime(2026, 10, 8, 21, 30, tzinfo=qe._NY).timestamp()
    flap()
    assert len(notes) == 1
    # the next New York day: one more note
    clock[0] = dt.datetime(2026, 10, 9, 9, 40, tzinfo=qe._NY).timestamp()
    flap()
    flap()
    assert len(notes) == 2
    _lint_all(notes)
    # a send that failed does not count: the next flap the same day tries again
    st2 = {"events": []}
    results = [False, True]
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None: (
        notes.append({"title": title, "message": msg, "priority": priority}),
        results.pop(0))[1])
    qe._maybe_notify_reconcile_halt(st2, "MISMATCH", "x", log=NOOP)
    assert "_hold_pushed_day" not in st2 or not st2["_hold_pushed_day"]
    qe._maybe_notify_reconcile_halt(st2, "MISMATCH", "x", log=NOOP)
    assert st2["_hold_pushed_day"] == {"reconcile": "2026-10-09"} and len(notes) == 4


def test_a_hold_that_blocks_the_close_pushes_after_an_earlier_hold(notes, monkeypatch):
    """Review fix (group C = one note per hold EPISODE): a morning reconcile halt that cleared
    must not silence a 12:40 resting hang that keeps the 12:59 close waiting -- each cause of
    a hold is its own problem. The same hung call re-checked is held; a NEW hung call later
    pushes again; a resting stop nobody can settle pushes once per order."""
    st = {"events": []}
    qe._maybe_notify_reconcile_halt(st, "MISMATCH", "ORB off by 5", log=NOOP)
    assert len(notes) == 1
    started = qe.time.time() - 600
    monkeypatch.setattr(qe, "_resting_inflight", {"future": _HungFut(), "what": "place",
                                                  "started_at": started,
                                                  "hang_alerted": False})
    qe._resting_hang_alert(st, log=NOOP)
    assert len(notes) == 2, "the hang that blocks the close is not held behind the reconcile"
    assert "Webull has not answered the ORB stop order for 10 min" in notes[1]["message"]
    assert "the 15:59 close included" not in notes[1]["message"], "owner's clock"
    assert "close included" in notes[1]["message"] and notes[1]["priority"] == "high"
    # the same hung call, re-armed (a restart of the check): held, one note per hung call
    qe._resting_inflight.update(hang_alerted=False)
    qe._resting_hang_alert(st, log=NOOP)
    assert len(notes) == 2
    # a NEW hung call later the same day: its own note
    qe._resting_inflight.update(hang_alerted=False, started_at=started - 60)
    qe._resting_hang_alert(st, log=NOOP)
    assert len(notes) == 3
    # an undecided resting stop: once per order, and a second order is a new hold
    ev = {"leg": "ORB", "kind": "stop", "client_order_id": "R1", "reason": "no lookup"}
    now = dt.datetime(2026, 10, 8, 11, 0)
    qe._book_resting_undecided(st, ev, now, log=NOOP)
    qe._book_resting_undecided(st, ev, now, log=NOOP)
    assert len(notes) == 4
    qe._book_resting_undecided(st, dict(ev, client_order_id="R2"), now, log=NOOP)
    assert len(notes) == 5
    # the reconcile, still flapping: its own slot still holds it
    qe._maybe_notify_reconcile_halt(st, "MISMATCH", "ORB off by 5", log=NOOP)
    assert len(notes) == 5
    assert any("not answered for" in t for t in _events(st)), "each hold still logs its event"
    assert {k for k in st["_phone_dedupe"] if k.startswith("hold:")} == {
        "hold:reconcile", "hold:resting_hang", "hold:resting_undecided"}
    _lint_all(notes)


def test_the_start_up_hold_is_its_own_problem(notes, monkeypatch):
    """The boot sweep has no state.json yet (process memory, hold:boot): a reconcile that then
    disagrees is a different hold cause -- by design its own note."""
    monkeypatch.setattr(qe, "_PHONE_PROCESS_STORE", {})
    qe._say_hold(None, "new QQQ entries wait until the book and Webull agree",
                 "At start-up Webull held 2 QQQ orders the book did not know; they were "
                 "cancelled", "check Webull's open QQQ orders", cause="boot", log=NOOP)
    qe._say_hold(None, "new QQQ entries wait until the book and Webull agree",
                 "At start-up Webull held 2 QQQ orders the book did not know; they were "
                 "cancelled", "check Webull's open QQQ orders", cause="boot", log=NOOP)
    assert len(notes) == 1 and "hold:boot" in qe._PHONE_PROCESS_STORE
    _lint_all(notes)


def test_book_and_webull_disagree_is_default_unless_sell_by_hand(notes, monkeypatch):
    st = {"events": [], "legs": {}}
    qe._book_resting_escape(st, {"leg": "ORB", "kind": "stop", "client_order_id": "R1",
                                 "status": "CANCELLED", "reason": "gone"},
                            dt.datetime(2026, 10, 8, 11, 0), log=NOOP)
    held = {"events": [], "legs": {"NOISE": {"side": "long", "trade_id": "NOISE_382-20261008T140000Z-L"}}}
    qe._push_fill_outcome(held, {"intent": "OPEN", "leg": "NOISE", "signal_id":
                                 qe._broker_signal_id("NOISE", None, "OPEN", trade_id="NOISE_382-20261008T140000Z-L")},
                          "O1", {"status": "PARTIAL_FILLED", "filled": 3, "qty": 5,
                                 "change": -2}, log=NOOP)

    class _A:
        def take_part_events(self, lock_timeout=None):
            return [{"leg": "NOISE", "intent": "CLOSE", "client_order_id": "C1",
                     "status": "CANCELLED", "booked": 0, "qty": 5, "change": -5},
                    {"leg": "ORB", "intent": "OPEN", "client_order_id": "C2",
                     "status": "FILLED", "booked": 5, "qty": 5, "change": 5}]
    qe._push_pending_changes(st, _A(), log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: object())
    qe._apply_unacked_close_fill(st, "NOISE", 40, log=NOOP)
    blk = {}
    for _ in range(qe.RESTING_MAX_TRIES):
        qe._resting_try_failed(st, blk, "k", "rate limited", dt.datetime(2026, 10, 8, 11, 0),
                               log=NOOP)
    by = {n["message"].split("\n")[1]: n["priority"] for n in notes}
    # 10-08 review: high where the strategy's trade did not (fully) happen at Webull or
    # shares sit there that nobody will sell; default for the rest of group D
    high = {"Webull still holds 5 NOISE shares after an unclear sell.",
            "Webull filled only 3 shares of the NOISE buy; the book still counts the trade.",
            "An unclear ORB buy landed at Webull after the book closed that trade."}
    assert {line for line, p in by.items() if p == "high"} == high
    assert all(p == "default" for line, p in by.items() if line not in high)
    assert any("40 more NOISE shares than Webull holds" in line for line in by)
    assert any("stop order could not be placed" in line for line in by)
    _lint_all(notes)


def test_fill_day_summary_and_safety_stop_notes(notes):
    st = {"events": []}
    nowdt = dt.datetime(2026, 10, 8, 16, 10, 0)
    today = "2026-10-08"
    st["_webull_flat_after_eod"] = {"date": today, "flat": True, "shares": 0}
    doc = {"today": {"trades": [{"x": 1}], "realized_pnl": 400.0, "realized_pnl_record": 412.4},
           "parity": {"checked": 0, "failed": 0},
           "feed_days": [{"date": today, "uptime_pct": 1.0}], "breaker_tripped": False}
    qe._maybe_send_eod_summary(st, doc, nowdt, log=NOOP)
    assert notes[-1]["priority"] == "low" and notes[-1]["title"] == "QQQ book: day done"
    assert "Made $412 today at Webull prices; Webull is flat." in notes[-1]["message"]
    qe._say_daily_stop(st, -1512.0, "open trades were closed", nowdt, log=NOOP)
    qe._say_daily_stop(st, -1600.0, "no trades were open", nowdt, log=NOOP)
    assert [n["priority"] for n in notes] == ["low", "high"], "the daily stop: ONE note"
    assert "$1,512" in notes[-1]["message"]
    for n in (qe._fill_note("NOISE", "bought", "Bought QQQ at 612.34 (share count stays on "
                            "the board)"),
              qe._fill_note("ENGUQ", "sold", "Sold QQQ at 615.10 (%s)"
                            % qe._exit_reason_words("EOD (px: live_stream)")),
              qe._kill_note(), qe._stood_down_note()):
        notes.append(n)
    assert notes[2]["title"] == "QQQ fill: NOISE bought" and notes[2]["priority"] == "low"
    assert "end-of-day close" in notes[3]["message"]
    assert notes[4]["priority"] == "low" and notes[5]["priority"] == "high"
    _lint_all(notes)


def test_tick_crash_and_flat_check_notes(notes, monkeypatch):
    st = {"events": []}
    for i in range(qe.TICK_FAILURE_ALERT_THRESHOLD + 2):
        qe._note_tick_result(st, False, exc=RuntimeError(f"boom{i}"), log=NOOP)
    assert len(notes) == 1 and notes[0]["priority"] == "high"

    class _Pos:
        def effective_mode(self):
            return "PAPER", "t"

        def positions(self, account_id=None):
            return {"broker": {"QQQ": 120.0}}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Pos())
    assert qe._check_webull_flat_after_eod(st, log=NOOP) == (False, 120)
    assert notes[-1]["priority"] == "urgent"
    assert "Webull still holds 120 QQQ shares." in notes[-1]["message"]
    _lint_all(notes)


def test_the_flat_check_that_raises_still_pushes_once(notes, monkeypatch):
    """Review fix: the executor stamps an unverified result ({flat: None}) as its own, so the
    box monitor stays quiet on it -- the executor's exception path must push the same high
    'could not be read' note (once a day), or nobody buzzes for a position held overnight."""
    class _Boom:
        def effective_mode(self):
            raise RuntimeError("adapter down")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Boom())
    st = {"events": []}
    assert qe._check_webull_flat_after_eod(st, log=NOOP) == (None, None)
    assert qe._check_webull_flat_after_eod(st, log=NOOP) == (None, None)
    assert len(notes) == 1 and notes[0]["priority"] == "high"
    assert "could not be read after the close" in notes[0]["message"]
    _lint_all(notes)
    # the monitor reads that stamped result as the executor's own: quiet, not a second buzz
    now = et(2026, 10, 8, 16, 30)
    snap = {"exec_state": {"eod_summary_done_date": "2026-10-08",
                           "_webull_flat_after_eod": {"date": "2026-10-08", "flat": None,
                                                      "pushed": True}},
            "exec_kill_files": []}
    v = {r["key"]: r for r in wf.check_eod(snap, now)}
    assert v["webull_flat"]["ok"] is False and v["webull_flat"].get("quiet") is True


def test_a_second_database_outage_the_same_day_pushes_again(monkeypatch):
    """Review fix: the 'database' note's episode ends when Firestore is healthy again (the
    process store at once, state.json's slot on the next rebuild pass), so a second wedge the
    same day pushes again instead of being held by the repeat rule."""
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)
    monkeypatch.setattr(qe, "FS_HEALTHY_AFTER_OKS", 1)
    monkeypatch.setattr(qe, "FS_HEALTHY_AFTER_SEC", 0)
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        (sent.append({"title": title, "message": msg, "priority": priority}),
                         True)[1])

    class _Client:
        def collection(self, name):
            return self
    h = qe._as_firestore_handle(_Client())
    qe._FS_HEALTH.__init__()
    st = {}
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError("503 wedged"), now=1000.0)
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=1000.0) == "alerted"
    assert len(sent) == 1 and "database" in st["_phone_dedupe"]
    qe._FS_HEALTH.note_ok(log=NOOP, now=2000.0)                       # healthy again
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=2001.0) is None
    assert "database" not in st["_phone_dedupe"], "the episode's note ended with it"
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError("503 wedged"), now=3000.0)
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=3000.0) == "alerted"
    assert len(sent) == 2, "a NEW outage pushes again"
    _lint_all(sent)
    qe._FS_HEALTH.__init__()


def test_drop_sites_log_and_time_line_but_never_push(notes, monkeypatch, tmp_path):
    """Group E / the other-owner sites: no push, the log line and timeline event stay."""
    # the NinjaTrader fill feed (dead on the box) -- a log line, no push
    monkeypatch.setattr(qe.nt_sync, "_addon_heartbeat", lambda path: (None, None, None))
    st, logs = {"events": []}, []
    qe._check_feed(st, str(tmp_path / "fills.csv"), log=logs.append)
    assert notes == [] and any("fill feed stale" in ln for ln in logs)
    assert any(e["kind"] == "feed_down" for e in st["events"])
    # nothing to close at Webull (the safe outcome) -- covered end to end in
    # tests/test_qqq_exec_exit_safety.py; the signal stall in test_qqq_exec_alerts_in_book.py.
    # Every group E block: a timeline event, never a push, up to the end of its branch.
    src = inspect.getsource(qe)
    starts = [i for i in range(len(src)) if src.startswith("PLAN 10-07, group E", i)]
    assert len(starts) >= 3
    for i in starts:
        ends = [j for j in (src.find(w, i) for w in ("continue", "return", "elif ",
                                                     "\n    if ", "\n    unsent_qty"))
                if j > i]
        block = src[i:min(ends)]
        assert "_log_event(" in block and "_say" not in block, block


# == 2. api/cloud_signal.py: the KEEL push ======================================================
def test_only_a_real_fallback_is_real():
    assert cs._keel_fallback_is_real("keel state unavailable")
    assert cs._keel_fallback_is_real("keel feature columns do not match the state")
    assert cs._keel_fallback_is_real("keel scoring error: RuntimeError: x")
    assert not cs._keel_fallback_is_real("keel state stale: 2 session(s) since 2026-10-01")
    assert not cs._keel_fallback_is_real(
        f"keel state stale: {cs.KEEL_MAX_STALE_SESSIONS} session(s) since 2026-10-01")
    assert cs._keel_fallback_is_real(
        f"keel state stale: {cs.KEEL_MAX_STALE_SESSIONS + 1} session(s) since 2026-10-01")
    assert not cs._keel_fallback_is_real(None)


def _stale_keel(tmp_path, last_session):
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ))
    state, _ = _fitted_state(arrays)
    return _write_state(tmp_path, state, last_nq_session=last_session), arrays


def test_a_few_stale_sessions_are_recorded_not_pushed(tmp_path, monkeypatch):
    """Box proof (10-05): 4 stale sessions pushed "KEEL fell back to 1.0" while sizing had
    not. Now: the facts in state.json and one log line a day, no push."""
    pushed, logs = [], []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    keel_cfg, _ = _stale_keel(tmp_path, "2026-09-02")         # Wed -> Tue 09-08: 3 sessions
    st = {}
    now = pd.Timestamp("2026-09-08 12:00:00", tz=cs.TZ)
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now, st, log=logs.append)
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now, st, log=logs.append)
    assert pushed == []
    rec = st["keel_alerts"]["NOISE_382"]
    assert rec["stale_sessions"] == 3 and "stale" in rec["last_reason"]
    assert rec["last_stale_date"] == "2026-09-08" and "last_pushed_date" not in rec
    assert sum("still sizing on the model" in ln for ln in logs) == 1
    # the sizing itself agrees: still the model (not the 1.0 fallback)
    size, diag = cs._keel_size_for_entry(keel_cfg, _stale_keel(tmp_path, "2026-09-02")[1], 10,
                                         pd.Timestamp("2026-09-08 10:20:00", tz=cs.TZ))
    assert not (isinstance(diag, str) and "stale" in diag)


def test_past_the_sizing_limit_it_pushes_once_a_day_plain(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push",
                        lambda msg, title, log=print: (sent.append(
                            {"title": title, "message": msg, "priority": "high"}), True)[1])
    keel_cfg, _ = _stale_keel(tmp_path, "2026-08-25")
    st = {}
    now = pd.Timestamp("2026-09-08 12:00:00", tz=cs.TZ)
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now, st)
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now + pd.Timedelta(hours=2), st)
    assert len(sent) == 1
    assert sent[0]["title"] == "QQQ book: CHECK NOW"
    assert "trading sessions old, too old to use" in sent[0]["message"]
    _lint_all(sent)


@pytest.mark.parametrize("reason", [
    "keel state unavailable", "keel feature columns do not match the state",
    "keel scoring error: RuntimeError: x", "keel freshness check error: OSError: x",
    "keel fixed tilts error: ValueError: x", "keel config has no state_path",
    "unknown keel mode '?'", "keel state stale: 9 session(s) since 2026-08-25"])
def test_every_keel_fallback_note_is_plain(reason):
    n = cs._keel_fallback_note("ENGUQ_335", reason)
    assert ntfy_push.lint(n) == [] and n["priority"] == "high"
    assert n["message"].startswith("Trading: AFFECTED - ENGU-Q trades at base size")
    assert "keel" not in n["message"].split("\n")[1].replace("KEEL", ""), "no reason codes"


def test_keel_push_failed_send_retries_no_topic_does_not(monkeypatch):
    results = [False, None]
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: results.pop(0))
    rec = {}
    assert cs._keel_fallback_push_once("NOISE_382", "keel state unavailable", "2026-09-08",
                                       [rec], log=NOOP) is False
    assert "last_pushed_date" not in rec, "a failed send stamps nothing -- a later tick retries"
    assert cs._keel_fallback_push_once("NOISE_382", "keel state unavailable", "2026-09-08",
                                       [rec], log=NOOP) is True
    assert rec["last_pushed_date"] == "2026-09-08", "no topic set counts as done -- no loop"


def test_step_and_scoring_time_share_one_push_a_day(monkeypatch):
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    today = "2026-09-08"
    st = {"legs": {"NOISE_382": {"keel_alert": {"last_pushed_date": today}}}}
    cs._maybe_push_keel_fallback("NOISE_382", {"state_path": "/nope.joblib", "summary_path": ""},
                                 pd.Timestamp(f"{today} 12:00:00", tz=cs.TZ), st)
    assert pushed == [], "the scoring-time push already told the owner today"


def test_the_box_monitor_owns_the_old_model_episode(tmp_path, monkeypatch):
    pushed = []
    monkeypatch.setattr(cs, "_keel_ntfy_push", lambda msg, title, log=print: pushed.append(msg))
    home = tmp_path / "home"
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=str(home)))
    os.makedirs(home / "freshness")
    with open(home / "freshness" / "state.json", "w", encoding="utf-8") as f:
        json.dump({"alerts": {"keel_fallback:NOISE_382_v12": {"open": True, "quiet": False}}}, f)
    rec = {}
    cs._keel_fallback_push_once("NOISE_382", "keel state stale: 7 session(s) since x",
                                "2026-09-08", [rec], log=NOOP)
    assert pushed == [] and rec["last_pushed_date"] == "2026-09-08"
    # a missing state is not the monitor's old-model episode: still pushed
    cs._keel_fallback_push_once("NOISE_382", "keel state unavailable", "2026-09-09", [{}],
                                log=NOOP)
    assert len(pushed) == 1


def test_keel_push_honours_token_and_server_and_keeps_none_apart(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=str(tmp_path / "h")))
    reqs = []

    class _Ok:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=8):
        reqs.append(req)
        return _Ok()
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen", opener)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert cs._keel_ntfy_push("m", "t", log=NOOP) is None and reqs == []
    monkeypatch.setenv("NTFY_TOPIC", " mytopic ")
    monkeypatch.setenv("NTFY_TOKEN", "tok123")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example/")
    assert cs._keel_ntfy_push("m", "t", log=NOOP) is True
    assert reqs[0].full_url == "https://ntfy.example/mytopic"
    assert reqs[0].get_header("Authorization") == "Bearer tok123"
    assert reqs[0].get_header("Priority") == "high"

    def down(req, timeout=8):
        raise OSError("Network is unreachable")
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen", down)
    assert cs._keel_ntfy_push("m", "t", log=NOOP, priority="default") is False
    assert 'f"https://ntfy.sh/{topic}"' not in inspect.getsource(cs), "no raw post is left"


# == 3. "NQ data did not reach the box": one owner ==============================================
def test_keel_fallback_age_matches_the_engine():
    assert wf.KEEL_FALLBACK_SESSIONS == cs.KEEL_MAX_STALE_SESSIONS
    assert wf.NQ_MARKER == kls.STALE_MARKER


def test_one_push_per_missed_night_then_one_at_the_fallback(tmp_path, monkeypatch):
    """Mon 10-05: the PC's upload never lands. 18:00 ET the monitor pushes (default, with the
    15:30 Arizona deadline); 18:30 keel_live_state notes it (no push); 19:05 the KEEL legs go
    stale (folded, quiet); Tue 08:30 the pre-open gate sees the KEEL miss (no second buzz).
    One push for the night. Fri 10-09 the model is 5 sessions old: the second (high) push."""
    from api import ntfy_push as np_mod

    def boom(*a, **k):
        raise AssertionError("keel_live_state must not push")
    fri = dt.date(2026, 10, 2)
    h = Home(tmp_path, et(2026, 10, 5, 17, 59))
    h.bars(h.now, nq_day=fri)
    h.run()
    assert h.pushes == []

    h.advance(et(2026, 10, 5, 18, 0))
    h.run()
    assert len(h.pushes) == 1
    p = h.pushes[0]
    assert p["title"] == "QQQ book: needs a fix" and p["priority"] == "default"
    assert p["message"] == ("Trading: not affected.\n"
                            "The PC's after-close NQ data upload did not reach the cloud box.\n"
                            "Do: run the upload on the PC before 15:30, or ask Claude "
                            "(PAPER-WB chat).")
    assert ntfy_push.lint(p) == []

    # 18:30 ET: the KEEL build loads the stale master -- marker, log, NO push
    monkeypatch.setattr(np_mod, "push", boom)
    monkeypatch.setattr(np_mod, "push_result", boom)
    idx = pd.DatetimeIndex([pd.Timestamp("2026-10-02 15:55", tz=wf.ET)])
    r = kls.check_nq_freshness({"arr": {"index": idx.values}, "dropped_session": None},
                               h.paths["keel_dir"], now_et=et(2026, 10, 5, 18, 30), log=NOOP)
    assert r["stale"] and r["noted"]
    monkeypatch.undo()

    h.advance(et(2026, 10, 5, 19, 5))
    out = h.run()
    assert {"keel:NOISE_382_v12", "keel:NOISE_422_KEEL_v12"} <= {
        r["key"] for r in out["opened"]}
    assert all(r["quiet"] for r in out["opened"] if r["key"].startswith("keel:"))
    assert len(h.pushes) == 1, "the KEEL legs fold into the NQ note"

    h.advance(et(2026, 10, 6, 8, 30))
    out = h.run()
    assert any(m.startswith("KEEL") for m in out["status"]["preopen"]["slots"]["08:30"]["misses"])
    assert len(h.pushes) == 1, "the pre-open gate does not re-push the same missed night"

    # Fri 10-09 evening: still not fixed, the model is 5 sessions old -> sizing falls back
    friday = et(2026, 10, 9, 19, 5)
    h.set_now(friday)
    h.exec_state(eod_summary_done_date="2026-10-09",
                 _webull_flat_after_eod={"date": "2026-10-09", "flat": True, "shares": 0})
    h.cs_state(settled_days=["2026-10-09"])
    h.advance(friday)
    h.run()
    assert len(h.pushes) == 2
    p = h.pushes[1]
    assert p["priority"] == "high" and p["title"] == "QQQ book: CHECK NOW"
    assert "NOISE trades at base size without its sizing model" in p["message"]
    assert "5 sessions old" in p["message"]
    assert ntfy_push.lint(p) == []


def test_a_cut_short_upload_is_named_from_the_marker(tmp_path):
    """Today's bars are in the file but keel_live_state found the last day incomplete: the
    newest-bar test passes, the marker does not -- the monitor's note names it."""
    h = Home(tmp_path, et(2026, 10, 5, 18, 32))
    with open(os.path.join(h.paths["keel_dir"], wf.NQ_MARKER), "w", encoding="utf-8") as f:
        json.dump({"newest": "2026-10-02", "expected": "2026-10-05",
                   "incomplete_day": "2026-10-05"}, f)
    out = h.run()
    assert "nq_master" in {r["key"] for r in out["opened"]}
    assert len(h.pushes) == 1
    assert "reached the cloud box cut short (its last day is incomplete)" in h.pushes[0]["message"]
    assert "the model rebuilds when it lands" in h.pushes[0]["message"], "15:30 has passed"
    assert ntfy_push.lint(h.pushes[0]) == []


def test_keel_not_rebuilt_alone_is_default_and_still_one_push(tmp_path):
    """The data landed but KEEL was not rebuilt (a build failure): its own default note --
    and the next morning's pre-open gate does not buzz for it again."""
    h = Home(tmp_path, et(2026, 10, 5, 19, 5))
    h.keel(through="2026-10-02")
    h.run()
    assert len(h.pushes) == 1 and h.pushes[0]["priority"] == "default"
    h.advance(et(2026, 10, 6, 8, 30))
    h.run()
    assert len(h.pushes) == 1


def test_a_quiet_keel_miss_counts_only_while_the_nq_episode_is_open():
    """Review fix: a keel:<leg> folded (quiet) into the nq_master note is 'already pushed' only
    while nq_master is open; once the data landed and nq_master closed, a model still not
    rebuilt was never named on the phone -- the pre-open gate says it."""
    quiet_keel = {"open": True, "quiet": True}
    assert wf._keel_miss_pushed("keel:NOISE_382_v12", {
        "nq_master": {"open": True}, "keel:NOISE_382_v12": quiet_keel})
    assert not wf._keel_miss_pushed("keel:NOISE_382_v12", {
        "nq_master": {"open": False}, "keel:NOISE_382_v12": quiet_keel})
    assert wf._keel_miss_pushed("keel:NOISE_382_v12", {
        "keel:NOISE_382_v12": {"open": True}}), "a loud keel:<leg> pushed it itself"


def test_the_monitor_leaves_a_database_outage_to_the_executor():
    """Plan 'Book stopped publishing': the executor owns 'cloud database unreachable'. While
    its state.json shows that note went out during THIS outage, exec_publish / exec_suppress
    track the episode quietly; a note from an earlier outage (before the last good publish)
    does not silence them."""
    now = et(2026, 10, 8, 11, 0)
    now_e = now.timestamp()
    ev = {"readable": True, "renew": 60, "publish_age": 1200.0, "last_ok": "10:40",
          "loop_age": 5.0}

    def run(at):
        st = {"_phone_dedupe": {"database": {"set": {"2026-10-08": 2}, "at": at, "high": True}},
              "_broker_lease_ok": False}
        snap = {"exec_state": st, "broker_mode": "PAPER", "_suppress_hits": 5}
        mstate = {}
        return {v["key"]: v for v in wf.check_exec(snap, now, mstate, ev)}
    during = run(now_e - 600)
    assert during["exec_publish"]["ok"] is False and during["exec_publish"].get("quiet")
    assert during["exec_suppress"]["ok"] is False and during["exec_suppress"].get("quiet")
    earlier = run(now_e - 3 * 3600)
    assert earlier["exec_publish"]["ok"] is False and not earlier["exec_publish"].get("quiet")
    assert not wf._exec_pushed_database({}, now_e, 1200.0)
    assert not wf._exec_pushed_database(None, now_e, None)


def test_the_stall_note_names_the_open_trade():
    snap = {"exec_state": {"legs": {"NOISE": {}, "ENGUQ": {}}}}
    assert wf._engine_problem(300, {}, snap) == (
        "The QQQ signal program has not reported for 5 min, with an open ENGU-Q and NOISE "
        "trade.")
    assert wf._engine_problem(None, {}, {"exec_state": {"legs": {}}}) == (
        "The QQQ signal program is not reporting.")


# == 10-08 review fixes ========================================================================
def _stale_close_retry(state, leg="NOISE", tid="T-yday"):
    """A close_retry left over from yesterday: the first tick of the day gives it up."""
    state.setdefault("_broker_resend", {})[f"{leg}:CLOSE:{tid}"] = {
        "leg": leg, "intent": "CLOSE", "why": "close_retry", "side": "SELL", "shares": 10,
        "trade_id": tid, "session_date": "2026-10-07", "first_at": 1.0, "last_at": 1.0,
        "tries": 3}


def test_a_give_up_ends_the_episode_so_the_next_close_failure_pushes(notes):
    """Review (major): the give-up used to reset the leg's exit episode BEFORE its own urgent
    push, leaving exit:<leg> at urgent for the day -- a later trade's first CLOSE failure on
    that leg was then held until its own give-up. Now the give-up pushes, then ends the
    episode: the next failure pushes high at once."""
    st = {"events": [], "legs": {}}
    _stale_close_retry(st)
    qe._maybe_resend_broker_orders(st, {"session": {}}, dt.datetime(2026, 10, 8, 9, 31), True,
                                   log=NOOP)
    assert [n["priority"] for n in notes] == ["urgent"]
    assert "gave up" in notes[0]["message"]
    assert "exit:NOISE" not in st.get("_phone_dedupe", {})
    assert any("gave up re-sending the NOISE sell" in t for t in _events(st))
    # trade 2 on the same leg, same day: its first CLOSE failure pushes at once
    qe._alert_broker_not_ok(st, leg="NOISE", intent="CLOSE", side="SELL", shares=10,
                            reason="insufficient position", log=NOOP)
    assert [n["priority"] for n in notes] == ["urgent", "high"]
    _lint_all(notes)


def test_a_give_up_after_a_same_day_urgent_stall_is_held(notes):
    """Review (minor): one stuck sell buzzes urgent ONCE -- the stall said 'check the Webull
    app and sell NOISE by hand'; the give-up says the same and is held (logged + timeline),
    then still ends the episode."""
    st = {"events": [], "legs": {}}
    qe._say_exit_stuck(st, "NOISE", "The NOISE sell is stuck: Webull cannot confirm the last "
                       "try", log=NOOP)
    _stale_close_retry(st)
    qe._maybe_resend_broker_orders(st, {"session": {}}, dt.datetime(2026, 10, 8, 9, 31), True,
                                   log=NOOP)
    assert len(notes) == 1, "the give-up is the same fact as the urgent stall"
    assert any("gave up re-sending the NOISE sell" in t for t in _events(st))
    assert "exit:NOISE" not in st.get("_phone_dedupe", {})
    _lint_all(notes)


def test_a_held_lower_call_does_not_lower_the_stored_rank(notes):
    """A 'sell is late' (high) held after the same day's urgent must not lower the stored rank
    -- else the next urgent for the same fact would count as worse and buzz again."""
    st = {}
    qe._say_exit_stuck(st, "NOISE", "The NOISE sell is stuck", log=NOOP)
    qe._say_exit_late(st, "NOISE", "Webull did not accept it", log=NOOP)
    assert st["_phone_dedupe"]["exit:NOISE"]["set"] == {qe._phone_day(): ntfy_push.RANK["urgent"]}
    qe._say_exit_stuck(st, "NOISE", "The NOISE sell is stuck", log=NOOP)
    assert len(notes) == 1


def test_each_sell_by_hand_order_pushes_its_own_note(notes):
    """Review (minor): two different orders' unsold shares the same day are two facts -- each
    'sell them by hand' pushes; the same order again is held; the default notes keep their
    own once-a-day slot."""
    st = {"events": [], "legs": {}}

    class _A:
        def __init__(self, evs):
            self.evs = evs

        def take_part_events(self, lock_timeout=None):
            return self.evs
    dead = {"leg": "NOISE", "intent": "CLOSE", "status": "CANCELLED", "booked": 0, "qty": 5,
            "change": -5}
    qe._push_pending_changes(st, _A([dict(dead, client_order_id="C1")]), log=NOOP)
    qe._push_pending_changes(st, _A([dict(dead, client_order_id="C1")]), log=NOOP)
    qe._push_pending_changes(st, _A([dict(dead, client_order_id="C3")]), log=NOOP)
    hand = [n for n in notes if "nobody will sell" in n["title"] + n["message"]]
    assert len(hand) == 2 and all(n["priority"] == "high" for n in hand)
    other = {"leg": "NOISE", "intent": "OPEN", "client_order_id": "C9", "status": "FILLED",
             "booked": 0, "qty": 5, "change": 0}
    qe._push_pending_changes(st, _A([other]), log=NOOP)
    qe._push_pending_changes(st, _A([dict(other, client_order_id="C10")]), log=NOOP)
    assert len(notes) == 3, "the default 'unclear order' note is once a day"
    _lint_all(notes)


def test_a_database_slot_from_before_a_restart_ends_once_firestore_works(monkeypatch):
    """Review (minor): an outage before a restart left state.json's 'database' slot set; the
    fresh process never entered that episode, so note_ok never ended it. Firestore working
    with no episode open ends the slot: a new outage the same day pushes at ~7 min again."""
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        (sent.append({"title": title, "message": msg, "priority": priority}),
                         True)[1])

    class _Client:
        def collection(self, name):
            return self
    h = qe._as_firestore_handle(_Client())
    qe._FS_HEALTH.__init__()
    st = {"_phone_dedupe": {"database": {"set": {qe._phone_day(): 2}, "at": 900.0,
                                         "high": True}}}
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=1000.0) is None
    assert "database" in st["_phone_dedupe"], "no call has worked yet: nothing is known"
    qe._FS_HEALTH.note_ok(log=NOOP, now=1001.0)
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=1002.0) is None
    assert "database" not in st["_phone_dedupe"]
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError("503 wedged"), now=3000.0)
    assert qe._maybe_rebuild_firestore(h, st, log=NOOP, now=3000.0) == "alerted"
    assert len(sent) == 1
    _lint_all(sent)
    qe._FS_HEALTH.__init__()


def test_an_unknown_entry_outcome_says_may_not(notes):
    """Review (minor): the UNKNOWN-outcome OPEN note's Trading line matches its problem line
    (it 'may not' be at Webull), not 'is not at Webull'."""
    st = {"events": []}
    qe._alert_broker_send_unknown(st, leg="ORB", intent="OPEN", side="BUY", shares=5,
                                  reason="timed out", client_order_id="X1", log=NOOP)
    assert len(notes) == 1
    line1, line2 = notes[0]["message"].split("\n")[:2]
    assert "the ORB buy may not be at Webull" in line1 and "is not at Webull" not in line1
    assert "may or may not have landed" in line2
    _lint_all(notes)


def _crash_marker(h, ago):
    with open(h.paths["exec_tick_crash"], "w", encoding="utf-8") as f:
        json.dump({"at_epoch": h.now.timestamp() - ago, "streak": 3}, f)


def test_tick_gap_is_quiet_while_the_executor_owns_a_tick_crash(tmp_path):
    """Plan 'Tick loop crashing vs stuck': while the executor's tick crash episode is open
    (its tick_crash.json marker, newer than the last good tick), tick_gap is tracked without
    a second push."""
    from test_webull_freshness import MON_1030
    h = Home(tmp_path, MON_1030)
    h.exec_state(loop_ago=45)
    _crash_marker(h, ago=20)
    out = h.run()
    gap = [r for r in out["opened"] if r["key"] == "tick_gap"]
    assert gap and gap[0]["quiet"]
    assert not any("stalled for" in p["message"] for p in h.pushes)
    # no crash episode: the same stall pushes
    h2 = Home(tmp_path / "b", MON_1030)
    h2.exec_state(loop_ago=45)
    out2 = h2.run()
    gap2 = [r for r in out2["opened"] if r["key"] == "tick_gap"]
    assert gap2 and not gap2[0]["quiet"]
    assert any("stalled for" in p["message"] for p in h2.pushes)
    # a marker older than the last good tick (an earlier, finished episode) does not count
    h3 = Home(tmp_path / "c", MON_1030)
    h3.exec_state(loop_ago=45)
    _crash_marker(h3, ago=100)
    out3 = h3.run()
    gap3 = [r for r in out3["opened"] if r["key"] == "tick_gap"]
    assert gap3 and not gap3[0]["quiet"]
    assert any("stalled for" in p["message"] for p in h3.pushes)


def test_exec_loop_is_quiet_only_while_a_fresh_tick_crash_marker_is_open(tmp_path):
    """10-08 review (plan 'Tick loop crashing vs stuck'): the executor's crash note already
    went out and its tick_crash.json marker is fresh -- the box monitor's exec_loop 'stuck'
    check is tracked (JSON, status) without a push, like tick_gap. A stale marker (the crash
    turned into a hang, or the process died) never silences it; nor does no marker."""
    from test_webull_freshness import MON_1030
    loop_ago = wf.EXEC_LOOP_SILENT_SEC + 300

    def run(home, marker_ago):
        home.exec_state(loop_ago=loop_ago)
        if marker_ago is not None:
            _crash_marker(home, ago=marker_ago)
        out = home.run()
        loop = [r for r in out["opened"] if r["key"] == "exec_loop"]
        assert loop, out["opened"]
        return loop[0], any("has been stuck for" in p["message"] for p in home.pushes)

    fresh, pushed = run(Home(tmp_path / "fresh", MON_1030), marker_ago=5)
    assert fresh["quiet"] and not pushed
    stale, pushed = run(Home(tmp_path / "stale", MON_1030),
                        marker_ago=wf.TICK_CRASH_MARKER_FRESH_SEC + 60)
    assert stale["quiet"] is False and pushed
    none, pushed = run(Home(tmp_path / "none", MON_1030), marker_ago=None)
    assert none["quiet"] is False and pushed


def test_the_strategy_word_takes_its_article():
    """10-08 review: 'an ORB' / 'an ENGU-Q' / 'a NOISE' -- never 'a ORB'."""
    assert ntfy_push.with_article("ORB") == "an ORB"
    assert ntfy_push.with_article("ENGU-Q") == "an ENGU-Q"
    assert ntfy_push.with_article("NOISE") == "a NOISE"
    assert ntfy_push.with_article("a strategy") == "a strategy"
    note = cs._keel_fallback_note("ENGUQ_335", "scoring error: boom")
    assert "size an ENGU-Q trade" in note["message"]
    assert "size a NOISE trade" in cs._keel_fallback_note("NOISE_382", "scoring error")["message"]
    # the executor's sentence-start strategy word (sell re-send dropped, stop fill not written)
    assert qe._a_leg_word("ORB") == "An ORB" and qe._a_leg_word("ENGUQ") == "An ENGU-Q"
    assert qe._a_leg_word("NOISE") == "A NOISE" and qe._a_leg_word(None) == "A strategy"
    src = inspect.getsource(qe)
    assert 'f"A {' not in src and 'f"a {_leg_word' not in src
    assert "{_a_leg_word(leg)} sell re-send was dropped" in src


def test_the_stop_fill_not_written_note_says_an_orb(notes, monkeypatch):
    """10-08 review: the dropped resting fill note starts 'An ORB stop fill', not 'A ORB'."""
    st = {"events": [], "legs": {}}

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(qe, "_book_one_resting_fill", boom)

    class _A:
        def take_resting_events(self, lock_timeout=None):
            return [{"leg": "ORB", "kind": "stop", "client_order_id": "R1", "side": "SELL",
                     "change": 5, "requeued": qe.RESTING_EVENT_MAX_REQUEUES}]

        def effective_mode(self):
            return "paper", None

        def requeue_resting_events(self, rest):
            return True
    qe._book_resting_fills(st, _A(), dt.datetime(2026, 10, 8, 11, 0), log=NOOP)
    assert len(notes) == 1 and notes[0]["priority"] == "default"
    assert "An ORB stop fill could not be written" in notes[0]["message"]
    _lint_all(notes)


def test_a_dead_cover_of_a_short_lot_is_a_buy_back(notes):
    """10-08 review: fill capture and the PENDING pass hand over the LOT side ('short');
    its close is a buy-back on the phone, never a sell."""
    assert qe._close_word("short") == "buy-back" and qe._close_word("BUY") == "buy-back"
    assert qe._close_word("long") == "sell" and qe._close_word("SELL") == "sell"
    assert qe._close_word(None) == "sell"
    st = {"events": []}
    qe._say_order_outcome(st, "NOISE", "CLOSE", "short", "REJECTED", 0, 5, True, True,
                          log=NOOP)
    assert len(notes) == 1 and notes[0]["priority"] == "high"
    assert "the NOISE buy-back is late" in notes[0]["message"]
    assert "sell" not in notes[0]["message"].split(chr(10))[1]
    _lint_all(notes)


def test_a_dead_entry_the_book_already_closed_does_not_say_it_counts(notes):
    """10-08 review: fill capture (up to a minute after the ack) or the PENDING pass finds
    the OPEN dead after the book closed that lot -- 'the book still counts the trade' would
    be wrong, so it is a group D default note; the held trade keeps the high entry-missed."""
    sid = qe._broker_signal_id("NOISE", None, "OPEN", trade_id="NOISE_382-20261008T140000Z-L")
    item = {"intent": "OPEN", "leg": "NOISE", "side": "long", "signal_id": sid}
    dead = {"status": "REJECTED", "filled": 0, "qty": 5, "change": -5}
    # the book holds no NOISE any more
    qe._push_fill_outcome({"events": [], "legs": {}}, item, sid, dead, log=NOOP)
    # the book holds a LATER NOISE trade, not this one
    later = {"side": "long", "trade_id": "NOISE_382-20261008T170000Z-L"}
    qe._push_fill_outcome({"events": [], "legs": {"NOISE": later}}, item, sid, dead, log=NOOP)
    assert [n["priority"] for n in notes] == ["default", "default"]
    for n in notes:
        assert "book still counts" not in n["message"]
        assert "after the book closed that trade" in n["message"]
    # the book still holds THIS trade (a split part id or a seq'd re-send of it): high
    lot = {"side": "long", "trade_id": "NOISE_382-20261008T140000Z-L"}
    for oid in (sid, sid + "2", webull_orders._part_client_order_id(sid, 2, 2)):
        assert qe._book_holds_open({"legs": {"NOISE": lot}}, "NOISE", oid)
    assert not qe._book_holds_open({"legs": {"NOISE": later}}, "NOISE", sid)
    qe._push_fill_outcome({"events": [], "legs": {"NOISE": lot}}, item, sid, dead, log=NOOP)
    assert notes[-1]["priority"] == "high" and "book still counts" in notes[-1]["message"]

    class _A:
        def take_part_events(self, lock_timeout=None):
            return [{"leg": "NOISE", "intent": "OPEN", "client_order_id": sid,
                     "status": "CANCELLED", "booked": 2, "qty": 5, "change": -3}]
    n0 = len(notes)
    qe._push_pending_changes({"events": [], "legs": {"NOISE": later}}, _A(), log=NOOP)
    assert len(notes) == n0 + 1 and notes[-1]["priority"] == "default"
    assert "book still counts" not in notes[-1]["message"]
    _lint_all(notes)


def test_the_pre_open_keel_miss_is_default_until_the_fallback_age():
    """Review (minor): a model 1-4 sessions old still sizes -- the pre-open gate names it at
    default; only at the fallback age (sizing at 1.0) is it high."""
    now = et(2026, 10, 6, 8, 30)
    want = wf.keel_expected(wf.prev_session(now.date()))
    ev = {"readable": True, "renew": 20.0, "publish_age": 5.0}

    def keel_miss(through):
        snap = {"keel": {"NOISE_382_v12": through}}
        ms = [m for m in wf.preopen_checks(snap, now, ev) if m["id"].startswith("keel:")]
        assert len(ms) == 1
        return ms[0]
    young = "2026-10-01"
    assert 1 <= wf._keel_behind(young, want) < wf.KEEL_FALLBACK_SESSIONS
    m = keel_miss(young)
    assert m["priority"] == "default" and m["affects"] is None
    old = "2026-09-25"
    assert wf._keel_behind(old, want) >= wf.KEEL_FALLBACK_SESSIONS
    m = keel_miss(old)
    assert m["priority"] == "high" and m["affects"] == wf.OLD_MODEL


def test_an_unreadable_keel_age_is_not_a_fallback(tmp_path):
    """Review (minor): api/cloud_signal reads data_through, else last_nq_session, and with
    neither skips the stale check (keeps the model). The monitor uses the same rule: no
    'too old to use' high push for a summary whose age cannot be read."""
    h = Home(tmp_path, et(2026, 10, 5, 19, 5))
    for leg in ("NOISE_382_v12", "NOISE_422_KEEL_v12"):
        with open(os.path.join(h.paths["keel_dir"], f"{leg}_summary.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"leg": leg}, f)
    out = h.run()
    keys = {r["key"] for r in out["opened"]}
    assert "keel:NOISE_382_v12" in keys
    assert not any(k.startswith("keel_fallback:") for k in keys)
    assert all(p["priority"] != "high" for p in h.pushes)
    # an older summary with only last_nq_session: read like cloud_signal reads it
    with open(os.path.join(h.paths["keel_dir"], "NOISE_382_v12_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump({"last_nq_session": "2026-10-02"}, f)
    assert wf.collect(h.paths, run_cmd=h.run_cmd)["keel"]["NOISE_382_v12"] == "2026-10-02"


# == 10-08 third review ==========================================================================
class _Stop:
    """A stop event for qqq_exec_thread run in line: set after `n` waits, never sleeps."""

    def __init__(self, n):
        self.n, self.waits = n, 0

    def is_set(self):
        return self.waits >= self.n

    def wait(self, timeout=None):
        self.waits += 1


def test_a_real_tick_crash_keeps_the_monitor_quiet(tmp_path, monkeypatch, notes):
    """Review (major): drive the REAL loop with a tick() that raises. The loop never saves
    state.json on a failed tick, so the crash episode reaches the box monitor through the
    tick_crash.json marker -- and tick_gap opens quiet: ONE push per crash episode."""
    from test_webull_freshness import MON_1030
    h = Home(tmp_path, MON_1030)
    h.exec_state(loop_ago=45)                     # the last GOOD tick's save, 45 s ago
    monkeypatch.setattr(qe, "STATE_PATH", h.paths["exec_state"])
    monkeypatch.setattr(qe, "TICK_CRASH_MARKER", h.paths["exec_tick_crash"])
    with open(h.paths["exec_state"], "rb") as f:
        before = f.read()
    before_mtime = os.path.getmtime(h.paths["exec_state"])
    saves = []
    monkeypatch.setattr(qe, "save_state", lambda *a, **k: saves.append(1))
    monkeypatch.setattr(qe, "_enter_host_slot", lambda log=print: ("slot", None))
    monkeypatch.setattr(qe, "_leave_host_slot", lambda slot: None)
    monkeypatch.setattr(qe, "_ntfy_outbox_resume", lambda log=print: None)
    monkeypatch.setattr(qe, "_reconcile_broker_at_boot", lambda log=print: None)
    monkeypatch.setattr(qe, "load_config", lambda log=print: {})
    monkeypatch.setattr(qe, "_qqq_stream_window_step", lambda cfg, last, log=print: last)
    monkeypatch.setattr(qe, "_stop_qqq_stream", lambda log=print: None)

    def boom(**kw):
        raise RuntimeError("tick blew up")
    monkeypatch.setattr(qe, "tick", boom)
    fake_now = h.now.timestamp() - 20
    monkeypatch.setattr(qe.time, "time", lambda: fake_now)
    qe.qqq_exec_thread(None, [], stop=_Stop(4), log=NOOP)
    assert saves == [], "a failed tick never saves state.json"
    with open(h.paths["exec_state"], "rb") as f:
        assert f.read() == before
    assert os.path.getmtime(h.paths["exec_state"]) == before_mtime
    crash = [n for n in notes if "keeps crashing" in n["message"]]
    assert len(crash) == 1
    _lint_all(crash)
    assert os.path.exists(h.paths["exec_tick_crash"])
    monkeypatch.setattr(qe.time, "time", lambda: h.now.timestamp())
    out = h.run()
    gap = [r for r in out["opened"] if r["key"] == "tick_gap"]
    assert gap and gap[0]["quiet"]
    assert not any("stalled for" in p["message"] for p in h.pushes)
    # the first good tick after it ends the episode: the marker goes
    qe._note_tick_result({"_tick_fail_streak": 4, "_tick_fail_alerted": True}, True, log=NOOP)
    assert not os.path.exists(h.paths["exec_tick_crash"])


def test_a_new_process_sweeps_a_stale_crash_marker(tmp_path, monkeypatch):
    """A process that died mid-crash leaves its marker; the next process's first good tick
    removes it (once), so it never silences a later stall."""
    marker = tmp_path / "tick_crash.json"
    marker.write_text('{"at_epoch": 1.0}', encoding="utf-8")
    monkeypatch.setattr(qe, "TICK_CRASH_MARKER", str(marker))
    qe._note_tick_result({}, True, log=NOOP)
    assert not marker.exists()


def test_a_failed_crash_note_is_retried_and_leaves_no_marker(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: (sent.append(title), False)[1])
    marker = tmp_path / "tick_crash.json"
    monkeypatch.setattr(qe, "TICK_CRASH_MARKER", str(marker))
    st = {"events": []}
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD + 1):
        qe._note_tick_result(st, False, exc=RuntimeError("x"), log=NOOP)
    assert len(sent) == 2, "a send that failed is tried again on the next failed tick"
    assert not marker.exists() and st["_tick_fail_alerted"] is False


def test_an_unknown_exit_outcome_says_it_may_have_gone_through(notes):
    """Review (minor): the UNKNOWN-outcome CLOSE note does not claim the sell failed."""
    st = {"events": []}
    qe._alert_broker_send_unknown(st, leg="NOISE", intent="CLOSE", side="SELL", shares=5,
                                  reason="timed out", client_order_id="X2", log=NOOP)
    assert len(notes) == 1
    line2 = notes[0]["message"].split("\n")[1]
    assert "did not go through" not in line2
    assert "Webull did not answer the NOISE sell in time" in line2
    assert "may or may not have gone through" in line2
    _lint_all(notes)


def test_a_feature_mismatch_beats_a_stale_only_reason(tmp_path, monkeypatch):
    """Review (minor): a model a few sessions old (stale, still sizing) whose feature
    columns do not match is a REAL fallback -- the step-time check pushes it."""
    sent = []
    monkeypatch.setattr(cs, "_keel_ntfy_push",
                        lambda msg, title, log=print: (sent.append(msg), True)[1])
    arrays = _arrays(base=pd.Timestamp("2026-09-08 09:30:00", tz=cs.TZ))
    state, _ = _fitted_state(arrays)
    state = dict(state, feature_names=list(state["feature_names"]) + ["not_a_feature"])
    keel_cfg = _write_state(tmp_path, state, last_nq_session="2026-09-02")   # 3 sessions
    now = pd.Timestamp("2026-09-08 12:00:00", tz=cs.TZ)
    assert "stale" in cs._keel_fallback_reason(keel_cfg, now)      # no arrays: the fact only
    reason = cs._keel_fallback_reason(keel_cfg, now, arrays=arrays)
    assert reason == "keel feature columns do not match the state"
    st = {}
    cs._maybe_push_keel_fallback("NOISE_382", keel_cfg, now, st, arrays=arrays)
    assert len(sent) == 1


# == 10-08 fourth review =========================================================================
def test_a_stale_crash_marker_does_not_keep_tick_gap_quiet(tmp_path):
    """A crash that turned into a hang (or a process that died mid-crash, with nothing after
    it to remove the marker) stops refreshing tick_crash.json: once it is older than
    TICK_CRASH_MARKER_FRESH_SEC, tick_gap pages in its normal window."""
    from test_webull_freshness import MON_1030
    h = Home(tmp_path, MON_1030)
    h.exec_state(loop_ago=400)                     # last good tick 400 s ago
    _crash_marker(h, ago=wf.TICK_CRASH_MARKER_FRESH_SEC + 60)   # newer than it, but stale
    out = h.run()
    gap = [r for r in out["opened"] if r["key"] == "tick_gap"]
    assert gap and not gap[0]["quiet"]
    assert any("stalled for" in p["message"] for p in h.pushes)
    # the same crash, refreshed a moment ago: quiet
    h2 = Home(tmp_path / "b", MON_1030)
    h2.exec_state(loop_ago=400)
    _crash_marker(h2, ago=5)
    out2 = h2.run()
    gap2 = [r for r in out2["opened"] if r["key"] == "tick_gap"]
    assert gap2 and gap2[0]["quiet"]


def test_every_failed_tick_after_the_note_refreshes_the_marker(tmp_path, monkeypatch, notes):
    marker = tmp_path / "tick_crash.json"
    monkeypatch.setattr(qe, "TICK_CRASH_MARKER", str(marker))
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(qe.time, "time", lambda: clock["t"])
    st = {"events": []}
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD):
        qe._note_tick_result(st, False, exc=RuntimeError("x"), log=NOOP)
    first = json.loads(marker.read_text(encoding="utf-8"))
    assert first["at_epoch"] == first["pushed_epoch"] == clock["t"]
    assert first["day"] == qe._phone_day()
    clock["t"] += 50
    qe._note_tick_result(st, False, exc=RuntimeError("x"), log=NOOP)
    again = json.loads(marker.read_text(encoding="utf-8"))
    assert again["at_epoch"] == clock["t"], "refreshed on every failed tick"
    assert again["pushed_epoch"] == first["pushed_epoch"] and again["day"] == first["day"]
    assert again["streak"] == qe.TICK_FAILURE_ALERT_THRESHOLD + 1
    assert len(notes) == 1


def test_a_crash_before_the_tick_gap_is_not_recorded_as_a_stall(tmp_path, monkeypatch, notes):
    """A tick that crashes before _track_tick_gap never advances _last_tick_wall: the first
    good tick after the crash note used to record the whole crash as tick_gap_max_s_today,
    and the monitor's 'rose' check pushed it after the marker was gone. The crash is not a
    stall: no second push."""
    monkeypatch.setattr(qe, "TICK_CRASH_MARKER", str(tmp_path / "tick_crash.json"))
    nowdt = dt.datetime(2026, 10, 8, 10, 30)
    st = {"events": []}
    assert qe._track_tick_gap(st, nowdt, now_wall=1000.0, log=NOOP) is None   # good tick
    assert qe._track_tick_gap(st, nowdt, now_wall=1005.0, log=NOOP) == 5.0   # good tick
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD + 5):     # crashes before the gap check
        qe._note_tick_result(st, False, exc=RuntimeError("load_config"), log=NOOP)
    assert len(notes) == 1
    qe._track_tick_gap(st, nowdt, now_wall=1005.0 + 600, log=NOOP)   # the recovery tick
    qe._note_tick_result(st, True, log=NOOP)
    assert st["tick_gap_max_s_today"] == 5.0, "the 10-min crash is not today's max stall"
    assert qe._track_tick_gap(st, nowdt, now_wall=1005.0 + 605, log=NOOP) == 5.0
    # a crash whose note did NOT go out keeps the gap: the monitor owns it then
    st2 = {"events": []}
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None: False)
    qe._track_tick_gap(st2, nowdt, now_wall=1000.0, log=NOOP)
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD + 1):
        qe._note_tick_result(st2, False, exc=RuntimeError("x"), log=NOOP)
    qe._track_tick_gap(st2, nowdt, now_wall=1300.0, log=NOOP)
    assert st2["tick_gap_max_s_today"] == 300.0


def test_a_restart_inside_one_crash_loop_does_not_push_again(tmp_path, monkeypatch, notes):
    """The crash note's repeat memory lives in state.json, which a failed tick never saves:
    a NEW process that starts into the same crash loop (no good tick in between) finds the
    first process's tick_crash.json from today and does not push the same note again."""
    marker = tmp_path / "tick_crash.json"
    monkeypatch.setattr(qe, "TICK_CRASH_MARKER", str(marker))
    monkeypatch.setattr(qe, "_TICK_CRASH_MARKER_SWEPT", {"done": False})
    p1 = {"events": []}                                      # process 1
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD + 1):
        qe._note_tick_result(p1, False, exc=RuntimeError("x"), log=NOOP)
    assert len(notes) == 1 and marker.exists()
    pushed = json.loads(marker.read_text(encoding="utf-8"))["pushed_epoch"]
    monkeypatch.setattr(qe, "_TICK_CRASH_MARKER_SWEPT", {"done": False})
    p2 = {"events": []}                                      # process 2: same loaded state
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD + 1):
        qe._note_tick_result(p2, False, exc=RuntimeError("x"), log=NOOP)
    assert len(notes) == 1, "once a day, not once per restart"
    assert p2["_tick_fail_alerted"] is True
    body = json.loads(marker.read_text(encoding="utf-8"))
    assert body["pushed_epoch"] == pushed and body["pid"] == os.getpid()
    # a good tick ends the episode: the next crash loop pushes again
    qe._note_tick_result(p2, True, log=NOOP)
    assert not marker.exists()
    p3 = {"events": []}
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD):
        qe._note_tick_result(p3, False, exc=RuntimeError("x"), log=NOOP)
    assert len(notes) == 2
    # a marker from an EARLIER day does not hold today's note
    qe._note_tick_result(p3, True, log=NOOP)
    marker.write_text(json.dumps({"at_epoch": 1.0, "day": "2026-10-01"}), encoding="utf-8")
    p4 = {"events": []}
    for _ in range(qe.TICK_FAILURE_ALERT_THRESHOLD):
        qe._note_tick_result(p4, False, exc=RuntimeError("x"), log=NOOP)
    assert len(notes) == 3


def test_a_refused_close_retry_ends_the_sell_episode(notes, monkeypatch):
    """A close_retry refused for good (kill file, rails, nothing held) leaves the queue: it
    ends the leg's exit:<leg> phone episode, so a later trade's first CLOSE failure on that
    leg the same day pushes at once (not held until its own stall or give-up)."""
    st = {"events": [], "legs": {}}
    qe._alert_broker_not_ok(st, leg="NOISE", intent="CLOSE", side="SELL", shares=10,
                            reason="insufficient position", log=NOOP)
    assert len(notes) == 1 and "exit:NOISE" in st["_phone_dedupe"]
    st["_broker_resend"] = {"NOISE:CLOSE:T1": {
        "leg": "NOISE", "intent": "CLOSE", "why": "close_retry", "side": "SELL", "shares": 10,
        "trade_id": "T1", "session_date": "2026-10-08", "first_at": 1.0, "last_at": 1.0,
        "tries": 0}}
    monkeypatch.setattr(qe, "_believed_qty_for_leg", lambda leg, log=print, larger=False: 10)

    def refused(state, **kw):
        state["_broker_last"] = {"ok": False, "leg": kw["leg"], "reason": "kill file present"}
    monkeypatch.setattr(qe, "_mirror_to_broker", refused)
    qe._maybe_resend_broker_orders(st, {"session": {}}, dt.datetime(2026, 10, 8, 10, 0), True,
                                   log=NOOP)
    assert st["_broker_resend"] == {}
    assert "exit:NOISE" not in st.get("_phone_dedupe", {})
    assert any("refused" in t for t in _events(st))
    qe._alert_broker_not_ok(st, leg="NOISE", intent="CLOSE", side="SELL", shares=5,
                            reason="insufficient position", log=NOOP)
    assert len(notes) == 2 and notes[1]["priority"] == "high"
    _lint_all(notes)


def test_the_monitor_pushes_an_after_close_result_whose_one_send_failed(monkeypatch):
    """The executor pushes its after-close result once. When that one send fails (False),
    its stamp says so and the box monitor pushes 'Webull not flat' itself -- never nobody."""
    sends = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None: (
        sends.append(priority), False)[1])

    class _Pos:
        def effective_mode(self):
            return "PAPER", "t"

        def positions(self, account_id=None):
            return {"broker": {"QQQ": 40.0}}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Pos())
    monkeypatch.setattr(qe, "_session_flatten_deadline",
                        lambda nowdt: dt.datetime(2026, 10, 8, 15, 59))
    st = {"events": [], "flat_by_done_date": "2026-10-08"}
    qe._maybe_check_webull_flat_after_eod(st, {}, dt.datetime(2026, 10, 8, 16, 5), log=NOOP)
    flat = st["_webull_flat_after_eod"]
    assert flat["flat"] is False and flat["pushed"] is False and sends == ["urgent"]
    now = et(2026, 10, 8, 16, 30)
    snap = {"exec_state": {"eod_summary_done_date": "2026-10-08",
                           "_webull_flat_after_eod": flat}, "exec_kill_files": []}
    v = {r["key"]: r for r in wf.check_eod(snap, now)}
    assert v["webull_flat"]["ok"] is False and not v["webull_flat"].get("quiet")
    # the same result whose note went out: the executor owns it, the monitor is quiet
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None: True)
    st2 = {"events": [], "flat_by_done_date": "2026-10-08"}
    qe._maybe_check_webull_flat_after_eod(st2, {}, dt.datetime(2026, 10, 8, 16, 5), log=NOOP)
    assert st2["_webull_flat_after_eod"]["pushed"] is True
    assert "_eod_flat_pushed" not in st2
    snap["exec_state"]["_webull_flat_after_eod"] = st2["_webull_flat_after_eod"]
    v = {r["key"]: r for r in wf.check_eod(snap, now)}
    assert v["webull_flat"].get("quiet") is True
