"""api/ntfy_push.Outbox -- the persisted outbox for HIGH/URGENT pushes (sweep 2026-10-05,
finding 16: every alert was one 4 s POST with the result ignored, so silence looked the same as
delivery).

Pinned here: one try now and nothing queued on success; a failed push kept ON DISK and picked
up by a NEW Outbox on the same file (a restart); bounded size (oldest non-urgent dropped first)
and age (12 h); spaced retries that stop at the first failure and hold the rest; a new push
queued behind waiting ones WITHOUT a network try (the executor's 5 s tick never waits on a
network that just failed); one log line per push outcome; the background retry thread
delivering and then exiting. No network: every sender is a fake.
"""
import json
import os
import threading

import pytest

from api import ntfy_push
from _threadwait import wait_for


class Sender:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def __call__(self, message, title, priority):
        self.calls.append({"message": message, "title": title, "priority": priority})
        r = self.results.pop(0) if self.results else (True, "HTTP 200")
        return r


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _box(tmp_path, sender, clock=None, logs=None, **kw):
    return ntfy_push.Outbox(str(tmp_path / "outbox.json"), sender, tag="t",
                            background=False, clock=clock or Clock(),
                            log=(logs.append if logs is not None else (lambda s: None)), **kw)


def _file(tmp_path):
    with open(tmp_path / "outbox.json", encoding="utf-8") as f:
        return json.load(f)


def test_durable_priorities():
    assert ntfy_push.is_durable("high") and ntfy_push.is_durable("URGENT")
    assert not ntfy_push.is_durable(None) and not ntfy_push.is_durable("default")
    assert not ntfy_push.is_durable("low")


def test_delivered_now_queues_nothing_and_logs_one_line(tmp_path):
    logs = []
    s = Sender()
    box = _box(tmp_path, s, logs=logs)
    assert box.send("m", "T", "high") is True
    assert len(s.calls) == 1 and box.pending() == []
    assert not os.path.exists(tmp_path / "outbox.json")
    assert len(logs) == 1 and "push sent (high, HTTP 200): T" in logs[0]


def test_failed_push_survives_a_restart_and_is_delivered_late(tmp_path):
    clock = Clock()
    logs = []
    s = Sender([(False, "URLError: down")])
    box = _box(tmp_path, s, clock=clock, logs=logs)
    assert box.send("BROKER NOT FLAT", "T", "urgent") == "queued"
    on_disk = _file(tmp_path)
    assert len(on_disk) == 1 and on_disk[0]["message"] == "BROKER NOT FLAT"
    assert on_disk[0]["attempts"] == 1 and on_disk[0]["last_error"] == "URLError: down"
    assert len(logs) == 1 and "kept in the outbox" in logs[0]

    # a restart: a brand-new Outbox on the same file
    logs2 = []
    s2 = Sender()
    box2 = _box(tmp_path, s2, clock=clock, logs=logs2)
    assert box2.resume() == 1
    clock.t += 10
    assert box2.flush() == (0, 1), "not due yet (first retry after 30 s)"
    clock.t += 25
    assert box2.flush() == (1, 0)
    assert s2.calls[0]["priority"] == "urgent"
    assert s2.calls[0]["message"].startswith("(late: raised ")
    assert " ET)" not in s2.calls[0]["message"], "the owner's Phoenix clock, never ET"
    assert s2.calls[0]["message"].endswith("BROKER NOT FLAT")
    assert _file(tmp_path) == []
    delivered = [ln for ln in logs2 if "push delivered" in ln]
    assert len(delivered) == 1 and "on try 2" in delivered[0]


def test_queued_behind_waiting_pushes_without_a_network_try(tmp_path):
    clock = Clock()
    s = Sender([(False, "timeout")])
    box = _box(tmp_path, s, clock=clock)
    assert box.send("one", "T1", "high") == "queued"
    assert len(s.calls) == 1
    for i in range(3):
        assert box.send(f"more {i}", f"M{i}", "high") == "queued"
    assert len(s.calls) == 1, "a new push behind waiting ones never waits on the network"
    assert [i["title"] for i in box.pending()] == ["T1", "M0", "M1", "M2"]
    # the new ones are due now, and a new push lifts the hold: the next pass sends in order
    sent, left = box.flush()
    assert (sent, left) == (3, 1)
    assert [c["title"] for c in s.calls[1:]] == ["M0", "M1", "M2"]
    clock.t += 31
    assert box.flush() == (1, 0)


def test_a_failed_retry_stops_the_pass_and_holds_the_rest(tmp_path):
    clock = Clock()
    s = Sender([(False, "a"), (False, "b")])
    box = _box(tmp_path, s, clock=clock)
    box.send("x", "X", "high")              # fails, queued, next try +30 s
    box.send("y", "Y", "high")              # queued behind, due now
    sent, left = box.flush()                # Y tried, fails -> holds everything
    assert (sent, left) == (0, 2) and len(s.calls) == 2
    clock.t += 31                           # X's 30 s is up but the hold (Y: +30 s) also
    s.results = [(True, "HTTP 200"), (True, "HTTP 200")]
    assert box.flush() == (2, 0)
    # spacing grows: 30 s, 60 s, 2 min, 5 min, 10 min, then every 10 min
    assert [box._retry_gap(n) for n in (1, 2, 3, 4, 5, 9)] == [30, 60, 120, 300, 600, 600]


def test_bounded_size_drops_oldest_non_urgent_first(tmp_path):
    logs = []
    s = Sender([(False, "down")] * 10)
    box = _box(tmp_path, s, logs=logs, max_items=3)
    box.send("u", "URG", "urgent")
    for i in range(4):
        box.send(f"h{i}", f"H{i}", "high")
    titles = [i["title"] for i in box.pending()]
    assert len(titles) == 3 and titles[0] == "URG", titles
    assert titles[1:] == ["H2", "H3"]
    assert sum("outbox full" in ln for ln in logs) == 2
    assert len(_file(tmp_path)) == 3


def test_a_push_older_than_12h_is_dropped_with_one_line(tmp_path):
    clock = Clock()
    logs = []
    s = Sender([(False, "down")] + [(False, "down")] * 200)
    box = _box(tmp_path, s, clock=clock, logs=logs)
    box.send("m", "OLD", "high")
    for _ in range(100):
        clock.t += 600
        box.flush()
    assert box.pending() == []
    dropped = [ln for ln in logs if "dropped after" in ln]
    assert len(dropped) == 1 and "OLD" in dropped[0]
    assert not any("delivered" in ln for ln in logs)


def test_no_topic_is_not_queued(tmp_path):
    s = Sender([(None, "NTFY_TOPIC unset")])
    box = _box(tmp_path, s)
    assert box.send("m", "T", "high") is None
    assert box.pending() == []


def test_a_sender_that_raises_counts_as_a_failure(tmp_path):
    def boom(m, t, p):
        raise OSError("socket")
    box = _box(tmp_path, boom)
    assert box.send("m", "T", "high") == "queued"
    assert box.pending()[0]["last_error"] == "OSError: socket"


def test_unreadable_outbox_file_starts_empty(tmp_path):
    (tmp_path / "outbox.json").write_text("{not json", encoding="utf-8")
    logs = []
    box = _box(tmp_path, Sender(), logs=logs)
    assert box.pending() == []
    assert any("unreadable" in ln for ln in logs)


def test_background_thread_delivers_then_exits(tmp_path):
    s = Sender([(False, "down")])
    box = ntfy_push.Outbox(str(tmp_path / "outbox.json"), s, tag="t", background=True,
                           log=lambda line: None, spacing=(0.05,))
    assert box.send("m", "T", "high") == "queued"
    assert wait_for(lambda: box.pending() == [])
    assert len(s.calls) == 2
    assert wait_for(lambda: box._thread is None), "the retry thread stops once nothing waits"
    assert not any(t.name == "t-ntfy-outbox" for t in threading.enumerate())


def test_push_result_reports_status_and_no_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert ntfy_push.push_result("m", title="t") == (None, "NTFY_TOPIC unset")

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setenv("NTFY_TOPIC", "x")
    monkeypatch.setattr(ntfy_push.urllib.request, "urlopen", lambda req, timeout=None: Resp())
    assert ntfy_push.push_result("m", title="t") == (True, "HTTP 200")
    assert ntfy_push.push("m") is True


def test_a_bad_row_on_disk_is_dropped_and_never_breaks_later_pushes(tmp_path):
    """A hand-edited or foreign outbox file whose row holds a non-number time used to make every
    pass and every later send() fail ('outbox pass failed' forever, urgent pages lost)."""
    (tmp_path / "outbox.json").write_text(json.dumps([
        {"id": "x", "title": "OLD", "message": "m", "priority": "high",
         "created_epoch": "yesterday", "next_try_epoch": None, "attempts": "two"},
        {"id": "y", "title": "GOOD", "message": "m2", "priority": "high",
         "created_epoch": "999990", "next_try_epoch": 0, "attempts": 1}]), encoding="utf-8")
    logs = []
    s = Sender()
    box = _box(tmp_path, s, logs=logs)
    assert [i["title"] for i in box.pending()] == ["GOOD"]
    assert sum("unreadable push" in ln for ln in logs) == 1
    assert box.flush() == (1, 0)
    assert not any("pass failed" in ln for ln in logs)
    assert box.send("Webull still holds 10 QQQ", "BROKER NOT FLAT", "urgent") is True
    assert s.calls[-1]["title"] == "BROKER NOT FLAT"


# -- the plain phone format (v73.1120/1121) through the outbox --------------------------------
def test_a_plain_note_delivered_late_keeps_its_three_lines_and_passes_lint(tmp_path):
    """A plain() note retried from the outbox says when it was raised on its PROBLEM line, on
    the owner's clock -- never an "ET" prefix that would break lint() and the 3-line shape."""
    clock = Clock(1_791_400_000.0)
    s = Sender([(False, "URLError: down")])
    box = _box(tmp_path, s, clock=clock)
    note = ntfy_push.plain("QQQ book", "prices stopped", "the QQQ book cannot enter or exit trades",
                           "No new QQQ price bar since 07:05.", "nothing")
    assert box.send(note["message"], note["title"], note["priority"]) == "queued"
    clock.t += 31
    assert box.flush() == (1, 0)
    late = s.calls[-1]["message"]
    lines = late.split("\n")
    assert len(lines) == 3 and "(Sent late - raised at " in lines[1]
    assert ntfy_push.lint({"title": note["title"], "message": late,
                           "priority": note["priority"]}) == []


def test_dedupe_in_keeps_independent_problems_apart():
    store = {}
    a = {"x": ntfy_push.RANK["high"]}
    assert ntfy_push.dedupe_in(store, "stall", a, 100.0) == "push"
    assert ntfy_push.dedupe_in(store, "stall", a, 200.0) is None, "same problem, same day"
    assert ntfy_push.dedupe_in(store, "yf", {"y": 1}, 200.0) == "push", "another key is its own"
    assert ntfy_push.dedupe_in(store, "stall", a, 100.0 + ntfy_push.DAY_S) == "push"
    # cleared after a high push -> one "clear", then the key is gone
    assert ntfy_push.dedupe_in(store, "stall", {}, 300.0) == "clear"
    assert "stall" not in store and "yf" in store
    assert ntfy_push.dedupe_in(store, "stall", {}, 400.0) is None
    # a low-only episode owes no "back to normal"
    assert ntfy_push.dedupe_in(store, "yf", {}, 500.0) is None


def test_outbox_ids_are_unique_within_one_millisecond(tmp_path):
    """ids are uuid4, not "<ms>-<len(items)>": flush() matches by id, and a flush that removed
    an item plus an enqueue in the same millisecond could have repeated one. The Clock here
    never moves, so every push is enqueued in the same millisecond."""
    box = _box(tmp_path, Sender([(False, "URLError: down")] * 10))
    for i in range(5):
        box.send("m%d" % i, "T", "high")
    ids = [it["id"] for it in _file(tmp_path)]
    assert len(ids) == 5 and len(set(ids)) == 5


def test_permanent_reject_is_a_4xx_about_the_push_itself():
    pr = ntfy_push.permanent_reject
    assert pr("HTTP 400") and pr("HTTPError: HTTP Error 413: Payload Too Large")
    # auth / topic (the same for every push) and the throttles stay retryable
    for code in (401, 403, 404, 408, 425, 429):
        assert not pr(f"HTTP {code}") and not pr(f"HTTPError: HTTP Error {code}: x")
    assert not pr("HTTP 500") and not pr("URLError: down") and not pr("") and not pr(None)


def test_a_push_ntfy_refuses_is_not_kept(tmp_path):
    logs = []
    s = Sender([(False, "HTTPError: HTTP Error 400: Bad Request")])
    box = _box(tmp_path, s, logs=logs)
    assert box.send("m", "BAD", "high") == "rejected"
    assert box.pending() == [] and len(logs) == 1 and "refused by ntfy" in logs[0]


def test_a_refused_push_at_the_head_never_holds_an_urgent_one(tmp_path):
    """Review 10-07: flush() ended its pass on the first failure, so one push ntfy refuses
    (HTTP 400/413) held every later HIGH/URGENT push -- "BROKER NOT FLAT" included -- for up
    to 12 h. It is now dropped (one line) and the pass goes on."""
    clock = Clock()
    logs = []
    s = Sender([(False, "URLError: down")])
    box = _box(tmp_path, s, clock=clock, logs=logs)
    assert box.send("bad", "BAD", "high") == "queued"
    assert box.send("BROKER NOT FLAT", "URGENT", "urgent") == "queued"   # behind, no try
    clock.t += 31
    s.results = [(False, "HTTPError: HTTP Error 413: Payload Too Large"), (True, "HTTP 200")]
    assert box.flush() == (1, 0)
    assert [c["title"] for c in s.calls[-2:]] == ["BAD", "URGENT"]
    assert sum("ntfy refused it" in line for line in logs) == 1
    assert box.pending() == []
