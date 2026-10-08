"""api/qqq_exec.py _notify + its persisted ntfy outbox (sweep 2026-10-05, finding 16).

Before: every push -- URGENT "BROKER NOT FLAT" included -- was ONE 4 s POST with the result
ignored. Now a 'high' or 'urgent' push that fails is kept on disk (NTFY_OUTBOX_PATH, beside
state.json) and retried off the tick; routine pushes stay a single fire-and-forget try.
conftest points NTFY_OUTBOX_PATH at a temp file and turns the retry thread off for every test.
No network: urlopen is always a fake.
"""
import json
import os

import pytest

from api import qqq_exec as qe

NOOP = lambda *a, **k: None


class Opener:
    """Fake urlopen: fails while `down` is True, records every request."""

    def __init__(self, down=True):
        self.down = down
        self.reqs = []

    def __call__(self, req, timeout=4):
        self.reqs.append(req)
        if self.down:
            raise OSError("Network is unreachable")

        class R:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()


@pytest.fixture
def net(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    op = Opener(down=True)
    monkeypatch.setattr(qe.urllib.request, "urlopen", op)
    return op


def _outbox_file():
    with open(qe.NTFY_OUTBOX_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_a_failed_urgent_push_is_kept_on_disk_not_lost(net):
    logs = []
    r = qe._notify("Webull still holds 10 QQQ", "EDGELOG QQQ BROKER NOT FLAT", log=logs.append,
                   priority="urgent")
    assert r == "queued", "before the outbox this returned False and the page was gone"
    items = _outbox_file()
    assert len(items) == 1 and items[0]["priority"] == "urgent"
    assert items[0]["message"] == "Webull still holds 10 QQQ"
    assert len(net.reqs) == 1
    assert sum("kept in the outbox" in ln for ln in logs) == 1


def test_a_second_high_push_while_one_waits_never_touches_the_network(net):
    qe._notify("first", "T1", log=NOOP, priority="high")
    assert len(net.reqs) == 1
    for i in range(5):
        assert qe._notify(f"n{i}", "T", log=NOOP, priority="high") == "queued"
    assert len(net.reqs) == 1, "the 5 s tick must not wait 4 s per push on a dead network"
    assert len(_outbox_file()) == 6


def test_outbox_survives_a_restart_and_delivers(net, monkeypatch):
    qe._notify("lease blocked", "EDGELOG QQQ BROKER", log=NOOP, priority="high")
    # a restart: the module-level holder is rebuilt from the file
    monkeypatch.setattr(qe, "_NTFY_OUTBOX", {"box": None})
    logs = []
    assert qe._ntfy_outbox_resume(log=logs.append) == 1
    assert any("kept from before the restart" in ln for ln in logs)
    net.down = False
    box = qe._ntfy_outbox(logs.append)
    sent, left = box.flush(now=box.next_due() + 1)
    assert (sent, left) == (1, 0)
    req = net.reqs[-1]
    assert req.get_header("Priority") == "high" and req.get_header("Title") == "EDGELOG QQQ BROKER"
    assert req.data.decode().startswith("(late: raised ") and req.data.decode().endswith("lease blocked")
    assert _outbox_file() == []
    assert sum("push delivered on try 2" in ln for ln in logs) == 1


def test_a_delivered_high_push_logs_one_success_line(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    op = Opener(down=False)
    monkeypatch.setattr(qe.urllib.request, "urlopen", op)
    logs = []
    assert qe._notify("m", "T", log=logs.append, priority="high") is True
    assert logs == ["[qqq-exec] ntfy push sent (high, HTTP 200): T"]
    assert not os.path.exists(qe.NTFY_OUTBOX_PATH)


def test_routine_pushes_stay_fire_and_forget(net):
    logs = []
    assert qe._notify("QQQ SHADOW NOISE buy 5 @ 600", "EDGELOG QQQ SHADOW", log=logs.append) is False
    assert not os.path.exists(qe.NTFY_OUTBOX_PATH)
    assert logs == ["[qqq-exec] ntfy push failed: OSError: Network is unreachable"]


def test_no_topic_queues_nothing(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert qe._notify("m", "T", log=NOOP, priority="urgent") is None
    assert not os.path.exists(qe.NTFY_OUTBOX_PATH)


def test_outbox_is_bounded(net):
    for i in range(qe.ntfy_push.OUTBOX_MAX_ITEMS + 7):
        qe._notify(f"m{i}", f"T{i}", log=NOOP, priority="high")
    items = _outbox_file()
    assert len(items) == qe.ntfy_push.OUTBOX_MAX_ITEMS
    assert items[-1]["title"] == f"T{qe.ntfy_push.OUTBOX_MAX_ITEMS + 6}"


def test_the_firestore_outage_page_is_not_retried_twice_once_queued(net, monkeypatch):
    """_maybe_rebuild_firestore retries its own page while _notify says False. A push the
    outbox keeps ("queued") is owned by the outbox: the episode's page is spent, so the same
    alert is not queued again every FS_ALERT_RETRY_SEC."""
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)

    class _Store:
        pass

    class _Client:
        def collection(self, name):
            return self
    h = qe._as_firestore_handle(_Client())
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError("503 wedged"), now=1000.0)
    state = {}
    assert qe._maybe_rebuild_firestore(h, state, log=NOOP, now=1000.0) == "alerted"
    assert qe._FS_HEALTH.alerted is True
    assert qe._maybe_rebuild_firestore(h, state, log=NOOP, now=1000.0 + qe.FS_ALERT_RETRY_SEC + 1) is None
    assert len(_outbox_file()) == 1


def test_an_outbox_that_cannot_take_the_push_still_makes_one_plain_try(monkeypatch):
    """Outbox.send() returns False only when the outbox itself broke before any network try:
    _notify must then still make the one plain POST, not drop an urgent page."""
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    op = Opener(down=False)
    monkeypatch.setattr(qe.urllib.request, "urlopen", op)

    class Broken:
        def send(self, *a, **k):
            return False
    monkeypatch.setattr(qe, "_ntfy_outbox", lambda log=None: Broken())
    logs = []
    assert qe._notify("Webull still holds 10 QQQ", "EDGELOG QQQ BROKER NOT FLAT",
                      log=logs.append, priority="urgent") is True
    assert len(op.reqs) == 1
    assert any("one plain try" in ln for ln in logs)
