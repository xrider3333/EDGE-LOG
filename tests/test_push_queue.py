r"""FIRST COME, FIRST SERVED for the push gate (tools/push_queue.py, 2026-10-05).

THE PROBLEM THIS FIXES IS MINE. tools/push_lock.py serialises lanes but is not fair: a waiter
takes the lock whenever it finds it free, so arrival order meant nothing. On 2026-10-04 the
rocfrontier lane waited more than 80 minutes while lanes that arrived later went ahead. With
~24-minute gates and a machine that shuts down in the evening, losing that draw repeatedly means
a lane's work does not land at all that day.

THE TWO TESTS THAT CARRY THE WEIGHT both need real processes, because a fake clock cannot show
either (see [[edgelog-cross-process-lock]]):
  - five lanes arriving in a known order are served in that order;
  - a waiter KILLED while holding the oldest ticket does not wedge the queue, because its lock
    dies with the process. That is why liveness is proved by the kernel and not by a heartbeat
    with a staleness threshold - push_lock's first version had exactly such a threshold, set
    longer than the waiter's own timeout, so a leftover lock could never be broken at all.
"""
import os
import subprocess
import sys
import tempfile
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import push_queue as q  # noqa: E402


@pytest.fixture(autouse=True)
def _own_home(monkeypatch, tmp_path):
    """Never the real C:\\EdgeLog\\state - conftest's guard blocks that write and fails the test,
    which is the correct outcome."""
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    return str(tmp_path)


# ═══════════════════════════════════════════════════ tickets
def test_a_lone_lane_waits_for_nobody():
    msgs = []
    with q.wait_turn(who="solo", log=msgs.append) as n:
        assert n == 1
    assert not msgs, "nothing to say when there is no queue"


def test_numbers_only_ever_go_up():
    seen = []
    for _ in range(3):
        with q.wait_turn(who="lane", log=lambda m: None) as n:
            seen.append(n)
    assert seen == [1, 2, 3], "a reused number would put two lanes in one position"


def test_a_ticket_is_live_only_while_it_is_held():
    with q.wait_turn(who="lane", log=lambda m: None) as n:
        assert [t[0] for t in q.live_tickets()] == [n]
    assert q.live_tickets() == [], "released on the way out"


def test_a_dead_ticket_is_swept_up_when_passed():
    d = q.queue_dir()
    os.makedirs(d, exist_ok=True)
    stray = os.path.join(d, "7-999999.ticket")
    open(stray, "w").close()                      # a ticket nobody holds
    assert q.live_tickets() == []
    assert not os.path.exists(stray), "litter from a crashed lane is removed as we pass it"


def test_a_file_that_is_not_a_ticket_is_ignored():
    d = q.queue_dir()
    os.makedirs(d, exist_ok=True)
    for name in ("counter", "counter.lock", "notes.txt", "x.ticket", "-1.ticket"):
        open(os.path.join(d, name), "w").close()
    assert q.live_tickets() == []


def _hold_ticket_number_one():
    """Pre-hold ticket 1 AND mark it as allocated.

    Seeding the counter is not decoration: without it the next mint also returns 1, so the new
    ticket is the SAME FILENAME, and Windows refuses a second lock on a file this process already
    holds - which is how the first version of these tests failed, with a PermissionError that
    looked like a defect in the queue.
    """
    d = q.queue_dir()
    os.makedirs(d, exist_ok=True)
    with open(q._counter_path(d), "w", encoding="utf-8") as fh:
        fh.write("1")
    path = os.path.join(d, "1-%d.ticket" % os.getpid())
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    q._lock_fd(fd)
    return fd


# ═══════════════════════════════════════════════════ it must never stop a lane shipping
def test_it_goes_ahead_when_a_ticket_cannot_be_minted(monkeypatch):
    monkeypatch.setattr(q, "_mint", lambda d: None)
    msgs = []
    with q.wait_turn(who="lane", log=msgs.append) as n:
        assert n is None, "None means go anyway"
    assert any("unavailable" in m for m in msgs), "and it must say so"


def test_it_goes_ahead_when_the_queue_directory_cannot_be_made(monkeypatch):
    monkeypatch.setattr(q.os, "makedirs",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError(13, "nope")))
    msgs = []
    with q.wait_turn(who="lane", log=msgs.append) as n:
        assert n is None
    assert any("unavailable" in m for m in msgs)


def test_it_gives_up_waiting_rather_than_never_shipping(monkeypatch):
    """Fairness is not worth a lane not landing at all."""
    fd = _hold_ticket_number_one()                # an older ticket, held for the whole test
    try:
        msgs = []
        with q.wait_turn(who="later", timeout=2, log=msgs.append, sleep=lambda s: None) as n:
            assert n is None
        assert any("out of turn" in m for m in msgs), "it must admit it jumped"
    finally:
        q._unlock_fd(fd)
        os.close(fd)


def test_the_default_timeout_outlasts_a_real_queue():
    """A queue of three at ~24 minutes each is a routine morning, so the timeout must comfortably
    exceed that - otherwise the lane at the back jumps the queue it was waiting in."""
    assert q.DEFAULT_TIMEOUT >= 3 * q.MINUTES_PER_TURN * 60


def test_the_wait_message_says_position_and_an_estimate():
    fd = _hold_ticket_number_one()
    try:
        msgs = []
        with q.wait_turn(who="later", timeout=1, log=msgs.append, sleep=lambda s: None):
            pass
        joined = " ".join(msgs)
        assert "1 lane(s) ahead" in joined and "min" in joined, joined
    finally:
        q._unlock_fd(fd)
        os.close(fd)


# ═══════════════════════════════════════════════════ real processes: the only honest test
def _lane_script(home):
    p = os.path.join(home, "lane.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(
            "import os, sys, time\n"
            "sys.path.insert(0, r'%s')\n" % TOOLS +
            "os.environ['EDGELOG_HOME'] = sys.argv[1]\n"
            "import push_queue as q\n"
            "with q.wait_turn(who=sys.argv[2], log=lambda m: None) as n:\n"
            "    print('%s|%s|%.6f' % (sys.argv[2], n, time.time()), flush=True)\n"
            "    time.sleep(float(sys.argv[3]))\n")
    return p


def test_four_real_lanes_are_served_in_the_order_they_arrived():
    home = tempfile.mkdtemp()
    script = _lane_script(home)
    procs = []
    for i in range(4):
        procs.append(subprocess.Popen([sys.executable, script, home, "lane%d" % i, "0.5"],
                                      stdout=subprocess.PIPE, text=True))
        time.sleep(0.35)                          # a clear arrival order
    served = []
    for p in procs:
        out, _ = p.communicate(timeout=180)
        name, ticket, when = out.strip().split("|")
        served.append((float(when), name, int(ticket)))
    served.sort()
    names = [n for _w, n, _t in served]
    tickets = [t for _w, _n, t in served]
    assert names == sorted(names), "served out of arrival order: %r" % (names,)
    assert tickets == sorted(tickets)


def test_a_killed_lane_does_not_wedge_the_queue():
    """THE PROPERTY THE DESIGN RESTS ON. The oldest ticket's holder is killed with no cleanup; the
    next lane must proceed, because the kernel released that ticket's lock with the process."""
    home = tempfile.mkdtemp()
    script = _lane_script(home)
    victim = subprocess.Popen([sys.executable, script, home, "victim", "300"],
                              stdout=subprocess.PIPE, text=True)
    nxt = None
    try:
        assert victim.stdout.readline().startswith("victim|1|")
        nxt = subprocess.Popen([sys.executable, script, home, "next", "0.2"],
                               stdout=subprocess.PIPE, text=True)
        time.sleep(2.5)
        assert nxt.poll() is None, "it must wait while the older ticket is genuinely held"
        victim.kill()
        victim.wait(timeout=30)
        out, _ = nxt.communicate(timeout=60)
        assert out.startswith("next|2|"), "a killed lane wedged the queue: %r" % out
    finally:
        for p in (victim, nxt):
            if p is not None and p.poll() is None:
                p.kill()


# ═══════════════════════════════════════════════════ how ship uses it
def test_ship_takes_a_ticket_BEFORE_it_takes_the_lock():
    """The ticket decides whose turn it is; the lock decides who holds it. Taking the lock first
    would make the queue decorative."""
    src = open(os.path.join(TOOLS, "wt.py"), encoding="utf-8").read()
    body = src[src.index("def cmd_ship"):]
    i_ticket = body.index("push_queue.hold_turn(")
    i_lock = body.index("push_lock.hold(")
    assert i_ticket < i_lock


def test_ship_keeps_the_ticket_in_a_live_variable():
    """A garbage-collected handle stops the ticket being live and lets a later lane jump."""
    src = open(os.path.join(TOOLS, "wt.py"), encoding="utf-8").read()
    assert "_queue_ticket = " in src


def test_ship_survives_a_shared_checkout_without_push_queue():
    src = open(os.path.join(TOOLS, "wt.py"), encoding="utf-8").read()
    assert "push_queue = None" in src
    assert "if push_queue else" in src, "a missing module must not stop a ship"
