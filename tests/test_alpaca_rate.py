r"""One account-wide pace for Alpaca requests, shared across processes (2026-10-02).

WHAT THIS IS FOR. The 200 req/min cap is per ACCOUNT and five lanes now pull through the same
key (NQBRD, TTM 20c, TBIS r3, TRANSFER r2, SIPORB). Each one paces itself at ~195/min believing
it is alone, so two at once is already over and five is five times over - and the symptom is not
a clean error but every lane 429ing, sleeping 20s, and colliding again on the way back.

Every test here drives time and sleep through the injected `now`/`sleep` seams, so the suite
never actually waits, and points the state file at tmp_path, so it never touches the real
C:\EdgeLog\state. Two "processes" are two calls against the same path - which is exactly what
they are, since the state is the file.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import alpaca_rate as rate  # noqa: E402


class Clock:
    """A clock that only moves when something sleeps, so a test can assert the exact wait."""

    def __init__(self, t=1_000_000.0):
        self.t = float(t)
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, sec):
        self.slept.append(float(sec))
        self.t += float(sec)

    @property
    def total_slept(self):
        return sum(self.slept)


def _refuse(fd, blocking=False):
    """Stand in for a lock somebody else holds."""
    raise OSError(11, "already locked")


def _must_not_write(path, stamps):
    raise AssertionError("the state must never be written without the lock")


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "state" / "alpaca_rate.json")


# ══════════════════════════════════════════════════════ under the cap: straight through
def test_the_first_request_does_not_wait(path):
    c = Clock()
    assert rate.wait(path, limit=5, sleep=c.sleep, now=c.now) == 0.0
    assert c.total_slept == 0.0


def test_the_state_file_and_its_directory_are_created_on_first_use(path):
    """Without this the limiter fails open forever on a machine that has never run it, and
    nothing would ever say so."""
    c = Clock()
    rate.wait(path, limit=5, sleep=c.sleep, now=c.now)
    assert os.path.exists(path)
    assert json.load(open(path, encoding="utf-8"))["requests"], "the request must be recorded"


def test_requests_up_to_the_cap_all_go_straight_through(path):
    c = Clock()
    for _ in range(5):
        assert rate.wait(path, limit=5, sleep=c.sleep, now=c.now) == 0.0
    assert rate.snapshot(path, now=c.now)[0] == 5


# ══════════════════════════════════════════════════════ at the cap: it waits, then goes
def test_the_request_over_the_cap_waits_for_the_oldest_to_age_out(path):
    c = Clock()
    for _ in range(3):
        rate.wait(path, limit=3, sleep=c.sleep, now=c.now)
    oldest = c.t
    waited = rate.wait(path, limit=3, sleep=c.sleep, now=c.now)
    assert waited > 0.0
    # it may not go before the oldest timestamp has left the 60s window
    assert c.t >= oldest + rate.WINDOW_SECONDS
    # and not meaningfully after it either - this is pacing, not a penalty
    assert c.t < oldest + rate.WINDOW_SECONDS + 1.0


def test_the_window_slides_rather_than_resetting(path):
    """A fixed-window counter would let 2x the cap through across a boundary. The oldest
    timestamp ageing out is what makes room, one request at a time."""
    c = Clock()
    for _ in range(3):
        rate.wait(path, limit=3, sleep=c.sleep, now=c.now)
        c.t += 1.0                              # three requests, one second apart
    first, second = 1_000_000.0, 1_000_001.0
    rate.wait(path, limit=3, sleep=c.sleep, now=c.now)
    assert c.t >= first + rate.WINDOW_SECONDS
    rate.wait(path, limit=3, sleep=c.sleep, now=c.now)
    assert c.t >= second + rate.WINDOW_SECONDS, "the second request gates the next one"


def test_timestamps_older_than_the_window_stop_counting(path):
    c = Clock()
    for _ in range(5):
        rate.wait(path, limit=5, sleep=c.sleep, now=c.now)
    c.t += rate.WINDOW_SECONDS + 1.0            # a minute later the bucket is empty again
    assert rate.wait(path, limit=5, sleep=c.sleep, now=c.now) == 0.0
    assert rate.snapshot(path, now=c.now)[0] == 1


# ══════════════════════════════════════════════════════ the point: lanes share one budget
def test_two_lanes_share_one_budget(path):
    """THE WHOLE REASON THIS EXISTS. Two processes, one account: the cap applies to the pair,
    not to each. Two 'processes' here are two callers against one state file, which is what
    they are - the file IS the shared state."""
    c = Clock()
    for _ in range(2):                          # lane A spends two
        assert rate.wait(path, limit=4, sleep=c.sleep, now=c.now) == 0.0
    for _ in range(2):                          # lane B spends the other two
        assert rate.wait(path, limit=4, sleep=c.sleep, now=c.now) == 0.0
    # the fifth request from EITHER lane must wait, even though neither sent four itself
    assert rate.wait(path, limit=4, sleep=c.sleep, now=c.now) > 0.0


def test_five_lanes_at_once_stay_under_the_cap(path):
    """The real shape: five lanes, interleaved, asking for far more than a minute's worth.
    What must hold is that no 60-second window ever contains more than the cap."""
    c = Clock()
    limit = 10
    granted = []
    for _ in range(50):
        rate.wait(path, limit=limit, sleep=c.sleep, now=c.now)
        granted.append(c.t)                     # when this request was actually allowed to go
        c.t += 0.01                             # a little work between requests
    # the state file only keeps the live window, so check every window over the WHOLE run
    for i, t0 in enumerate(granted):
        in_window = [t for t in granted[i:] if t < t0 + rate.WINDOW_SECONDS]
        assert len(in_window) <= limit, (
            "%d requests inside one %gs window, cap is %d"
            % (len(in_window), rate.WINDOW_SECONDS, limit))
    assert c.total_slept > 0, "50 requests at a cap of 10/min cannot have been free"


def test_no_window_anywhere_holds_more_than_the_cap_when_requests_are_unevenly_spaced():
    """THE INVARIANT THAT MATTERS: no 60-second window anywhere holds more than the cap.

    It is not the same as the rule the code applies ("at most `limit` in the 60 seconds before
    THIS request"), and the difference is a real off-by-one: two REAL processes at a cap of 6
    put 7 into one window. What closes the gap is the lower bound being inclusive. Take the
    last request granted inside any window [x, x+60); every earlier request in that window lies
    within 60 seconds of it, so it was counted when that request asked, and it was only granted
    because the count was below the cap. A strict `<` lets a request sitting exactly on the
    boundary fall out of that count, and then the window holds one more than the cap.

    Honest about what this test is: a frozen test clock cannot land two stamps exactly 60
    seconds apart, so it would NOT have caught the original - a two-process run did, and the
    reasoning above is why the fix holds in general. This pins the invariant so a later change
    to the window arithmetic has to keep it.
    """
    import tempfile
    c = Clock()
    limit = 6
    granted = []
    gaps = [0.0, 0.013, 0.004, 0.021, 0.002, 0.037]     # a burst, unevenly spaced
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "state", "rate.json")
        for i in range(24):
            rate.wait(p, limit=limit, sleep=c.sleep, now=c.now)
            granted.append(c.t)
            c.t += gaps[i % len(gaps)]
    for i, t0 in enumerate(granted):
        n = sum(1 for t in granted[i:] if t < t0 + rate.WINDOW_SECONDS)
        assert n <= limit, ("%d requests in the window starting at offset %.3f, cap is %d"
                            % (n, t0 - granted[0], limit))


# ══════════════════════════════════════════════════════ it must never break a pull
def test_a_corrupt_state_file_does_not_raise(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("{not json")
    c = Clock()
    assert rate.wait(path, limit=5, sleep=c.sleep, now=c.now) == 0.0


def test_a_state_file_holding_rubbish_is_ignored(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({"requests": ["banana", None, {}]}, open(path, "w", encoding="utf-8"))
    c = Clock()
    assert rate.wait(path, limit=5, sleep=c.sleep, now=c.now) == 0.0


def test_a_timestamp_in_the_future_is_discarded(path):
    """A clock change or a corrupt write would otherwise throttle every lane for as long as
    the bad stamp is ahead - potentially hours."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = Clock()
    json.dump({"requests": [c.t + 86400.0] * 5}, open(path, "w", encoding="utf-8"))
    assert rate.wait(path, limit=5, sleep=c.sleep, now=c.now) == 0.0


def test_a_lock_that_cannot_be_taken_fails_open(path, monkeypatch):
    """Fail open is deliberate: a pacing aid must not be able to kill a six-hour pull. It has
    to be RARE, which is what the OS lock below is for."""
    monkeypatch.setattr(rate, "_lock_fd", _refuse)
    c = Clock()
    assert rate.wait(path, limit=1, sleep=c.sleep, now=c.now) >= 0.0
    assert rate.snapshot(path, now=c.now)[0] == 0, (
        "a request it could not record must not be recorded")


def test_failing_open_never_writes_the_state_unlocked(path, monkeypatch):
    """Reading and writing the shared count without the lock is the very race the lock exists
    for - it would corrupt the budget for every other lane, not just skip this one."""
    monkeypatch.setattr(rate, "_lock_fd", _refuse)
    monkeypatch.setattr(rate, "_write", _must_not_write)
    c = Clock()
    rate.wait(path, limit=1, sleep=c.sleep, now=c.now)


def test_it_gives_up_waiting_for_the_lock_rather_than_blocking_forever(path, monkeypatch):
    monkeypatch.setattr(rate, "_lock_fd", _refuse)
    c = Clock()
    rate.wait(path, limit=5, sleep=c.sleep, now=c.now)
    assert c.total_slept <= rate.LOCK_WAIT_SECONDS + 1.0


def test_a_lock_held_by_someone_else_is_waited_for_then_taken(path):
    """A REAL lock on a REAL file, taken twice. Two handles contend whether they are in two
    processes or one, so this exercises the same kernel path the lanes do.

    This is what the OS lock buys: the previous version was an O_EXCL lock FILE with a
    timestamp inside it and a stale-breaker, and its two constants were the wrong way round -
    the breaker fired at 15s but a waiter gave up at 10, so a leftover lock could never be
    broken. Two real processes duly produced it: one waited its full 10s, failed open, and sent
    an UNRECORDED request; 10 requests at a cap of 6 put 9 into one window and recorded 4. A
    kernel lock has no leftover state at all - it is released when the handle closes or the
    process dies.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = path + ".lock"
    held = os.open(lock, os.O_CREAT | os.O_RDWR)
    try:
        rate._lock_fd(held)                      # somebody else is holding it
        c = Clock()
        rate.wait(path, limit=5, sleep=c.sleep, now=c.now)
        assert rate.snapshot(path, now=c.now)[0] == 0, "it must not have jumped the lock"
        assert c.total_slept >= rate.LOCK_WAIT_SECONDS, "and it must have waited its timeout"
        rate._unlock_fd(held)
        # released: the next call goes straight through and records
        c2 = Clock()
        assert rate.wait(path, limit=5, sleep=c2.sleep, now=c2.now) == 0.0
        assert rate.snapshot(path, now=c2.now)[0] == 1
    finally:
        os.close(held)


def test_the_lock_file_is_left_in_place_not_deleted(path):
    """It is a handle to lock, not a flag to set. Deleting it is what made two processes able
    to each hold their own 'lock' on a file the other had already removed."""
    c = Clock()
    rate.wait(path, limit=5, sleep=c.sleep, now=c.now)
    assert os.path.exists(path + ".lock")


def test_a_failed_state_write_is_not_reported_as_paced(path, monkeypatch):
    """If the count could not be written, the request is about to be sent with nothing
    recording it. Silently treating that as paced is the account going over the cap unseen."""
    monkeypatch.setattr(rate, "_write", lambda p, stamps: False)
    c = Clock()
    rate.wait(path, limit=5, sleep=c.sleep, now=c.now)
    assert rate.snapshot(path, now=c.now)[0] == 0


# ══════════════════════════════════════════════════════ the cap itself
def test_the_default_cap_leaves_headroom_under_the_documented_limit():
    """200/min is the documented cap. Pacing exactly at it means the first retry inside
    `requests`, or a pull somebody starts by hand, is already over."""
    assert rate.DEFAULT_PER_MIN < 200
    assert rate.DEFAULT_PER_MIN >= 150, "too much headroom and the pulls take all week"


def test_the_cap_can_be_raised_without_an_edit(monkeypatch):
    monkeypatch.setenv("ALPACA_RATE_PER_MIN", "1000")
    assert rate.per_min() == 1000


def test_a_nonsense_cap_falls_back_to_the_default(monkeypatch):
    for bad in ("", "banana", "0", "-5"):
        monkeypatch.setenv("ALPACA_RATE_PER_MIN", bad)
        assert rate.per_min() == rate.DEFAULT_PER_MIN


def test_the_state_lives_under_edgelog_home(monkeypatch, tmp_path):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    assert rate.state_path().startswith(str(tmp_path))


# ══════════════════════════════════════════════════════ every caller goes through it
def test_every_alpaca_request_path_is_paced():
    """A limiter half the callers bypass does not limit anything. These are every place in the
    repo that sends an Alpaca bars request."""
    for rel in ("tools/import_alpaca_stocks.py", "tools/backfill_qqq_5m_alpaca.py",
                "tools/rocfrontier/r5_nqbrd.py", "tools/rocfrontier/r5_siporb.py"):
        src = open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()
        assert "alpaca_rate" in src, f"{rel} sends Alpaca requests without the shared pace"
