"""tests/test_nt_cloud_watchdog.py -- the off-PC NinjaTrader dead-man's-switch
(tools/nt_cloud_watchdog.py, GitHub Actions every 15 min) in the plain phone format
(2026-10-07, owner GO "yes deploy box pings").

Pins the MANAGER-approved texts and priorities (offline = low, a strategy was running = high,
an open position = urgent, a position nobody can see = high), the repeat rule (ntfy_push.dedupe:
once, then once a day; worse at once; one low "OK" only after a high/urgent push), lint() on every
note, the remembered positions, and main()'s Firestore/ntfy plumbing with fakes -- no network,
no Firestore, never a real push.
"""
import datetime as dt
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.nt_cloud_watchdog as cw  # noqa: E402
from api import ntfy_push  # noqa: E402

UTC = dt.timezone.utc


def utc_epoch(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


# 2026-10-08 04:30 UTC = 21:30 on Oct 7 in Phoenix; "now" half an hour later
LAST_BEAT = "2026-10-08 04:30:00"
NOW = utc_epoch(2026, 10, 8, 5, 0)


def bridge(up=True, positions=(), partial=None, checked_at=LAST_BEAT):
    d = {"checked_at": checked_at, "up": up, "strategies": [], "positions": list(positions)}
    if partial:
        d["partial"] = list(partial)
    return d


def rep(severity="warning", stale=30.0, roster=()):
    return {"severity": severity, "stale_minutes": stale, "message": "x",
            "last_realtime_strategies": list(roster), "checked_utc": "2026-10-08 05:00:00"}


NQ_LONG = {"account": "DEMO7240108", "instrument": "NQ 12-26", "side": "Long", "qty": 1,
           "avg_price": 21000.25}


# -- the texts --------------------------------------------------------------------------------
def test_pc_asleep_with_nothing_running_is_one_quiet_note():
    action, state, note = cw.decide(rep(), bridge(), {}, NOW)
    assert action == "push"
    assert note == {"title": "NinjaTrader: offline", "priority": "low", "message":
                    "Trading: not affected (no strategy was running).\n"
                    "NinjaTrader has been silent since 21:30 - the PC is probably asleep.\n"
                    "Do: nothing."}
    assert ntfy_push.lint(note) == []


def test_silent_while_a_strategy_was_running_is_check_now_high():
    r = rep("critical", 40.0, ["EdgeLogENGUQ1m"])
    action, state, note = cw.decide(r, bridge(checked_at="2026-10-07 10:12:00"), {},
                                    utc_epoch(2026, 10, 7, 10, 52))
    assert note == {"title": "NinjaTrader: CHECK NOW", "priority": "high", "message":
                    "Trading: AFFECTED - ENGU-Q was running and has stopped reporting.\n"
                    "NinjaTrader has been silent since 03:12.\n"
                    "Do: wake the PC and open NinjaTrader."}
    assert ntfy_push.lint(note) == []


def test_two_strategies_read_as_a_list():
    r = rep("critical", 40.0, ["EdgeLogENGUQ1m", "EdgeLogNOISE", "EdgeLogENGUQ1m"])
    _, _, note = cw.decide(r, bridge(), {}, NOW)
    assert note["message"].split("\n")[0] == \
        "Trading: AFFECTED - ENGU-Q and NOISE were running and have stopped reporting."


def test_an_open_position_is_the_only_urgent_case():
    r = rep("critical", 40.0, ["EdgeLogENGUQ1m"])
    _, _, note = cw.decide(r, bridge(positions=[NQ_LONG]), {}, NOW)
    assert note["title"] == "NinjaTrader: CHECK NOW" and note["priority"] == "urgent"
    assert note["message"].split("\n")[0] == (
        "Trading: AFFECTED - ENGU-Q was running with an open NQ position and has stopped "
        "reporting.")
    assert ntfy_push.lint(note) == []
    # no strategy, but a position open (a hand trade): still urgent
    _, _, note2 = cw.decide(rep(), bridge(positions=[NQ_LONG]), {}, NOW)
    assert note2["priority"] == "urgent"
    assert note2["message"].split("\n")[0] == \
        "Trading: AFFECTED - NinjaTrader stopped reporting with an open NQ position."


def test_account_numbers_never_reach_the_phone():
    real = dict(NQ_LONG, account="1810769", instrument="ES 12-26")
    _, state, note = cw.decide(rep(), bridge(positions=[real, NQ_LONG]), {}, NOW)
    first = note["message"].split("\n")[0]
    assert first == ("Trading: AFFECTED - NinjaTrader stopped reporting with open ES and NQ "
                     "positions (your real account).")
    assert "1810769" not in str(note) and "DEMO" not in str(note) and "DEMO" not in str(state)
    assert ntfy_push.lint(note) == []


def test_a_position_nobody_can_see_reads_the_safe_way_high_not_urgent():
    """The bridge doc was written while NinjaTrader was closed (up:false resets positions) and
    this script never saw an up:true doc: the position is UNKNOWN -> "may be affected", high."""
    _, state, note = cw.decide(rep(), bridge(up=False), {}, NOW)
    assert note["priority"] == "high" and note["title"] == "NinjaTrader: CHECK NOW"
    assert note["message"].split("\n")[0] == \
        "Trading: AFFECTED - a position may be open and NinjaTrader has stopped reporting."
    # a partial positions read is just as unknown
    _, _, n2 = cw.decide(rep(), bridge(partial=["positions"]), {}, NOW)
    assert n2["priority"] == "high"
    # a strategy running with the position unknown: high, never urgent
    _, _, n3 = cw.decide(rep("critical", 40.0, ["EdgeLogNOISE"]), bridge(up=False), {}, NOW)
    assert n3["priority"] == "high"


def test_the_last_positions_it_saw_are_remembered():
    # a healthy up:true doc while the PC is on: flat, remembered
    _, state, note = cw.decide(rep("ok", 2.0), bridge(), {}, NOW)
    assert note is None and state["positions"] == {"open": []}
    # later NinjaTrader is closed (up:false) and then the PC goes silent: last known = flat
    _, state2, note2 = cw.decide(rep(), bridge(up=False), state, NOW + 3600)
    assert note2["title"] == "NinjaTrader: offline" and note2["priority"] == "low"
    # remembered as open -> urgent even though the silent doc cannot say
    held = {"positions": {"open": [{"inst": "NQ", "acct": "paper"}]}}
    _, _, note3 = cw.decide(rep(), bridge(up=False), held, NOW)
    assert note3["priority"] == "urgent"


def test_ninjatrader_closed_before_the_pc_went_silent_is_not_a_stopped_strategy():
    """The runner kept publishing up:false (NinjaTrader closed) and then the PC shut down. The
    roster evaluate() holds over from earlier says ENGU-Q was Realtime -- but nothing was running
    when the PC went silent, so with the position known flat this is the quiet note."""
    flat = {"positions": {"open": []}}
    r = rep("critical", 40.0, ["EdgeLogENGUQ1m"])
    _, _, note = cw.decide(r, bridge(up=False, checked_at="2026-10-08 00:45:00"), flat,
                           utc_epoch(2026, 10, 8, 1, 15))
    assert note == {"title": "NinjaTrader: offline", "priority": "low", "message":
                    "Trading: not affected (no strategy was running).\n"
                    "NinjaTrader was closed and the PC has been silent since 17:45.\n"
                    "Do: nothing."}
    assert ntfy_push.lint(note) == []
    # the same with a remembered open position is still the urgent case, naming no strategy
    held = {"positions": {"open": [{"inst": "NQ", "acct": "paper"}]}}
    _, _, n2 = cw.decide(r, bridge(up=False), held, NOW)
    assert n2["priority"] == "urgent"
    assert n2["message"].split("\n")[0] == \
        "Trading: AFFECTED - NinjaTrader stopped reporting with an open NQ position."


def test_missing_bridge_doc_changes_nothing():
    prior = {"push": {"set": {"running": 2}, "at": NOW - 60, "high": True}, "since": NOW - 900,
             "positions": None}
    r = {"severity": "warning", "stale_minutes": None, "last_realtime_strategies": []}
    action, state, note = cw.decide(r, None, prior, NOW)
    assert (action, note) == (None, None)
    assert state == prior


# -- the repeat rule ------------------------------------------------------------------------------
def test_same_state_pushes_once_then_once_a_day():
    r = rep("critical", 40.0, ["EdgeLogENGUQ1m"])
    a1, s1, n1 = cw.decide(r, bridge(), {}, NOW)
    a2, s2, n2 = cw.decide(r, bridge(), s1, NOW + 15 * 60)
    a3, s3, n3 = cw.decide(r, bridge(), s2, NOW + 23 * 3600)
    a4, s4, n4 = cw.decide(r, bridge(), s3, NOW + 24 * 3600 + 60)
    assert [a1, a2, a3, a4] == ["push", None, None, "push"]
    assert n2 is None and n3 is None and n4["priority"] == "high"


def test_worse_pushes_at_once():
    a1, s1, n1 = cw.decide(rep(), bridge(), {}, NOW)
    assert n1["priority"] == "low"
    a2, s2, n2 = cw.decide(rep("critical", 40.0, ["EdgeLogNOISE"]), bridge(), s1, NOW + 900)
    assert a2 == "push" and n2["priority"] == "high"
    a3, s3, n3 = cw.decide(rep("critical", 40.0, ["EdgeLogNOISE"]), bridge(positions=[NQ_LONG]),
                           s2, NOW + 1800)
    assert a3 == "push" and n3["priority"] == "urgent"


def test_ok_note_only_after_a_high_or_urgent_push():
    a1, s1, _ = cw.decide(rep("critical", 40.0, ["EdgeLogENGUQ1m"]), bridge(), {}, NOW)
    a2, s2, ok = cw.decide(rep("ok", 1.0), bridge(checked_at="2026-10-08 05:59:00"), s1, NOW + 3600)
    assert a2 == "clear"
    assert ok == {"title": "NinjaTrader: OK", "priority": "low", "message":
                  "Trading: not affected.\n"
                  "Back to normal (was: silent since 21:30).\n"
                  "Do: nothing."}
    assert ntfy_push.lint(ok) == []
    # the next healthy run says nothing
    a3, s3, n3 = cw.decide(rep("ok", 1.0), bridge(), s2, NOW + 4500)
    assert (a3, n3) == (None, None)
    # an episode that only ever sent the quiet "offline" note owes no "OK"
    b1, t1, _ = cw.decide(rep(), bridge(), {}, NOW)
    b2, t2, n = cw.decide(rep("ok", 1.0), bridge(), t1, NOW + 3600)
    assert b2 is None and n is None


# -- main(): Firestore + ntfy plumbing with fakes ---------------------------------------------------
class FakeStore:
    def __init__(self, docs):
        self.docs = dict(docs)
        self.writes = []
        self.fail_read = set()

    def read(self, db, uid, name):
        if name in self.fail_read:
            raise RuntimeError("boom")
        return self.docs.get(name)

    def write(self, db, uid, name, data):
        self.writes.append((name, data))
        self.docs[name] = data


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("EDGELOG_UID", "test-uid")
    monkeypatch.setenv("NTFY_TOPIC", "test-topic-never-used")
    monkeypatch.setattr(cw, "_get_firestore_client", lambda: object())
    sent = []

    def fake_push(message, title=None, priority=None, timeout=8, log=None):
        sent.append({"message": message, "title": title, "priority": priority, "timeout": timeout})
        return env.ok
    monkeypatch.setattr(ntfy_push, "push", fake_push)

    class E:
        pass
    env = E()
    env.ok = True
    env.sent = sent

    def install(store, report):
        monkeypatch.setattr(cw, "_read_meta_doc", store.read)
        monkeypatch.setattr(cw, "_write_meta_doc", store.write)
        monkeypatch.setattr(cw.nt_heartbeat, "evaluate", lambda b, p: report)
    env.install = install
    return env


def test_main_pushes_once_writes_its_memory_and_keeps_the_body_out_of_the_log(env, capsys):
    store = FakeStore({"nt_bridge": bridge(positions=[NQ_LONG]), "nt_alert": {}})
    env.install(store, rep("critical", 40.0, ["EdgeLogENGUQ1m"]))
    assert cw.main() == 0
    assert len(env.sent) == 1
    assert env.sent[0]["title"] == "NinjaTrader: CHECK NOW"
    assert env.sent[0]["priority"] == "urgent" and env.sent[0]["timeout"] == 10
    assert [w[0] for w in store.writes] == ["nt_watchdog"]
    out = capsys.readouterr().out
    assert "pushed [urgent] NinjaTrader: CHECK NOW: ok" in out
    assert "NQ position" not in out and "positions" not in out    # public GitHub log
    assert "test-topic-never-used" not in out
    # the next run (15 minutes later in real life): same state, no push, no write
    assert cw.main() == 0
    assert len(env.sent) == 1 and len(store.writes) == 1


def test_main_failed_push_exits_1_and_tries_again_next_run(env):
    store = FakeStore({"nt_bridge": bridge(), "nt_alert": {}})
    env.install(store, rep("critical", 40.0, ["EdgeLogNOISE"]))
    env.ok = False
    assert cw.main() == 1
    assert not (store.docs.get("nt_watchdog") or {}).get("push", {}).get("set")
    env.ok = True
    assert cw.main() == 0
    assert len(env.sent) == 2


def test_main_state_read_failure_still_pushes(env, capsys):
    store = FakeStore({"nt_bridge": bridge(), "nt_alert": {}})
    store.fail_read.add("nt_watchdog")
    env.install(store, rep("critical", 40.0, ["EdgeLogNOISE"]))
    assert cw.main() == 0
    assert len(env.sent) == 1
    assert "state read failed" in capsys.readouterr().out


def test_main_needs_its_uid_and_topic(env, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC")
    assert cw.main() == 2
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.delenv("EDGELOG_UID")
    assert cw.main() == 2
    assert env.sent == []


def test_main_firestore_read_failure_is_red(env):
    store = FakeStore({})
    store.fail_read.add("nt_bridge")
    env.install(store, rep())
    assert cw.main() == 2
    assert env.sent == []


# -- NIGHT MODE (2026-10-07, api/nt_night_mode.py) ---------------------------------------------------------
from api import nt_night_mode  # noqa: E402

NIGHT = {"active": True, "since": "2026-10-07T13:20:00-07:00", "until": "2026-10-08T05:45:00-07:00",
         "grace_until": "2026-10-08T06:30:00-07:00", "until_hhmm": "05:45", "reason": "end of day",
         "how": "clean", "position_open": False}


def night_bridge(**kw):
    d = bridge(up=False, **kw)
    d["night_mode"] = dict(NIGHT)
    return d


def test_pc_silent_inside_the_night_window_is_expected_and_silent():
    prior = {"push": {}, "since": None, "positions": {"open": [{"inst": "NQ", "acct": "paper"}]}}
    action, state, note = cw.decide(rep("critical", 30.0, ["EdgeLogENGUQ1m"]), night_bridge(), prior, NOW)
    assert (action, note) == (None, None)
    assert state["push"] == {}                           # the episode memory is left exactly as it was


def test_night_window_can_send_one_low_note_instead(monkeypatch):
    monkeypatch.setattr(nt_night_mode, "CLOUD_NIGHT_PUSH", "low")
    action, state, note = cw.decide(rep(), night_bridge(), {}, NOW)
    assert action == "push"
    assert note == {"title": "NinjaTrader: night mode until 05:45", "priority": "low", "message":
                    "Trading: not affected (NinjaTrader is closed for the night on purpose).\n"
                    "The PC has been silent since 21:30; NinjaTrader starts again at 05:45.\n"
                    "Do: nothing."}
    assert ntfy_push.lint(note) == []
    # the next run inside the window does not repeat it
    assert cw.decide(rep(), night_bridge(), state, NOW + 900)[2] is None


def test_a_morning_where_the_pc_never_came_back_pages_after_the_grace():
    prior = {"push": {}, "since": None, "positions": {"open": [{"inst": "NQ", "acct": "paper"}]}}
    late = utc_epoch(2026, 10, 8, 13, 35)                 # 06:35 Phoenix, past the 06:30 grace
    action, state, note = cw.decide(rep("warning", 600.0), night_bridge(), prior, late)
    assert action == "push" and note["priority"] == "urgent" and note["title"] == "NinjaTrader: CHECK NOW"
    early = utc_epoch(2026, 10, 8, 13, 20)                # 06:20 Phoenix: still inside the grace
    assert cw.decide(rep("warning", 600.0), night_bridge(), prior, early)[2] is None


def test_night_block_from_before_the_window_or_unreadable_changes_nothing():
    for blk in ({"active": False}, {"since": "garbage", "grace_until": None}, "not a dict"):
        b = bridge()
        b["night_mode"] = blk
        action, _, note = cw.decide(rep(), b, {}, NOW)
        assert action == "push" and note["title"] == "NinjaTrader: offline"
    assert cw.night_window({"night_mode": dict(NIGHT)}, utc_epoch(2026, 10, 7, 19, 0)) is None   # before since


def test_low_night_note_says_an_open_trade_keeps_its_stop(monkeypatch):
    monkeypatch.setattr(nt_night_mode, "CLOUD_NIGHT_PUSH", "low")
    b = night_bridge()
    b["night_mode"]["position_open"] = True
    note = cw.decide(rep(), b, {}, NOW)[2]
    assert note["priority"] == "low" and ntfy_push.lint(note) == []
    assert note["message"].split("\n")[0] == \
        "Trading: AFFECTED - an open paper trade keeps its stop, but nothing trails it until 05:45."
