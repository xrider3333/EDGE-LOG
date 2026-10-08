r"""The machine-wide push lock (tools/push_lock.py), added 2026-10-02.

WHAT IT IS FOR. The pre-push hook re-runs the engine test tier for any change under
augur_engine/, api/ or tests/ - almost every backend change - and that tier takes about 23
minutes. With ten sessions shipping, main moves inside that window and the push is rejected on a
stale ref. This session ran three gates in a row, 23m38s each, all green, and was overtaken every
time; TTM and TBIS sat blocked behind the commit for over three hours.

TWO THINGS HERE ARE WORTH MORE THAN THE REST:

  - `test_a_killed_holder_does_not_wedge_the_lock` is the property the whole design rests on. A
    lock FILE would need a stale-breaker, a stale-breaker needs a threshold, and this session got
    that wrong earlier the same day in the Alpaca limiter: the breaker fired at 15s while the
    waiter gave up at 10s, so a leftover lock could never be broken and the waiter silently gave
    up and sent an unrecorded request. An OS lock on an open handle has no leftover state - the
    kernel drops it when the process ends, however it ends.

  - `test_a_waiting_lane_can_read_the_holders_name` is a regression. On Windows `msvcrt.locking`
    takes a MANDATORY lock, so a reader that starts at byte 0 gets a permission error: the name
    was unreadable and the waiting message said nobody held it. The lock covers byte 0 and the
    name lives from byte 1.

Every test here uses its own path under tmp_path, never the real C:\EdgeLog\state - conftest's
live-system guard blocks that write and fails the test, which is the correct outcome.
"""
import os
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import push_lock  # noqa: E402


@pytest.fixture
def lock(tmp_path):
    return str(tmp_path / "state" / "push.lock")


# ═══════════════════════════════════════════════════ taking and releasing it
def test_it_is_taken_and_released(lock):
    with push_lock.exclusive(who="lane-a", path=lock, log=lambda m: None) as held:
        assert held is True
    # released: a second caller gets it without waiting
    t0 = time.time()
    with push_lock.exclusive(who="lane-b", path=lock, log=lambda m: None) as held:
        assert held is True
    assert time.time() - t0 < 1.0


def test_hold_returns_a_handle_that_must_stay_alive(lock):
    h = push_lock.hold(who="lane-a", path=lock, log=lambda m: None)
    assert h is not None
    os.close(h)                                   # what the process exit does for us
    assert push_lock.hold(who="lane-b", path=lock, log=lambda m: None) is not None


def test_the_state_directory_is_created(lock):
    h = push_lock.hold(who="lane", path=lock, log=lambda m: None)
    assert os.path.exists(lock)
    os.close(h)


def test_the_lock_lives_under_edgelog_home(monkeypatch, tmp_path):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    assert push_lock.lock_path().startswith(str(tmp_path))
    assert push_lock.lock_path().endswith("push.lock")


# ═══════════════════════════════════════════════════ the holder's name
def test_a_waiting_lane_can_read_the_holders_name(lock):
    """REGRESSION. On Windows msvcrt.locking is MANDATORY: a reader starting at byte 0 gets a
    permission error, so the name came back empty and the waiting message said nobody held it.
    Byte 0 is the lock; the name starts at byte 1."""
    h = push_lock.hold(who="alpacakeys", path=lock, log=lambda m: None)
    try:
        name = push_lock.holder(lock)
        assert "alpacakeys" in name, "a waiting lane must be able to say who it waits for"
        assert str(os.getpid()) in name, "and which process, so a human can go and look"
    finally:
        os.close(h)


def test_an_unnamed_or_missing_lock_reads_as_empty_not_an_error(tmp_path):
    assert push_lock.holder(str(tmp_path / "nothing" / "push.lock")) == ""


def test_the_name_never_stops_a_ship(lock, monkeypatch):
    """The name is a convenience; the LOCK is the point. A first version of this test patched
    the failure away and then asserted that a no-op does not raise, which tested nothing - and
    the code really would have propagated, because hold() called _write_name outside any try.
    Both are fixed: the raise is left in place and the lock must still be held."""
    def _boom(fd, who):
        raise OSError(28, "no space left on device")
    monkeypatch.setattr(push_lock, "_write_name", _boom)

    h = push_lock.hold(who="lane", path=lock, log=lambda m: None)
    assert h is not None, "a failed name write must not cost the lock"
    try:
        # and it really is held: nobody else can take it
        assert push_lock.hold(who="other", path=lock, timeout=1, log=lambda m: None) is None
    finally:
        os.close(h)

    with push_lock.exclusive(who="lane", path=lock, log=lambda m: None) as held:
        assert held is True, "same for the context-manager form"


# ═══════════════════════════════════════════════════ it must never block a ship forever
def test_it_fails_open_after_its_timeout_rather_than_blocking(lock):
    """A lock that can stop every lane from pushing is worse than the contention it removes."""
    h = push_lock.hold(who="holder", path=lock, log=lambda m: None)
    try:
        msgs = []
        t0 = time.time()
        assert push_lock.hold(who="waiter", path=lock, timeout=2, log=msgs.append) is None
        assert time.time() - t0 < 30
        assert any("unlocked" in m for m in msgs), "it must SAY it is going anyway"
        assert any("holder" in m for m in msgs), "and name who it waited for"
    finally:
        os.close(h)


def test_it_fails_open_when_the_lock_cannot_be_opened_at_all(monkeypatch, lock):
    monkeypatch.setattr(push_lock.os, "open",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError(13, "nope")))
    msgs = []
    assert push_lock.hold(who="lane", path=lock, log=msgs.append) is None
    assert any("unavailable" in m for m in msgs)


def test_the_default_timeout_outlasts_a_real_gate():
    """23 minutes is the normal engine tier and 40 has been seen on a busy box. A timeout
    shorter than a real gate would make the lock fail open exactly when it is working."""
    assert push_lock.DEFAULT_TIMEOUT > 23 * 60 * 2


# ═══════════════════════════════════════════════════ real processes: the only honest test
def _child_script(tmp_path):
    p = tmp_path / "child.py"
    p.write_text(
        "import sys, time\n"
        "sys.path.insert(0, r'%s')\n" % TOOLS +
        "import push_lock\n"
        "h = push_lock.hold(who=sys.argv[1], path=sys.argv[2], log=lambda m: None)\n"
        "print('%s|%s|%.6f|ACQ' % (sys.argv[1], 'got' if h else 'FAILOPEN', time.time()),"
        " flush=True)\n"
        "time.sleep(float(sys.argv[3]))\n"
        "print('%s|%s|%.6f|REL' % (sys.argv[1], 'got' if h else 'FAILOPEN', time.time()),"
        " flush=True)\n")
    return str(p)


def test_three_real_processes_never_overlap(tmp_path, lock):
    """A cross-process lock is only really tested across processes. Three lanes, each holding
    for a third of a second: no two may hold it at once, and none may fail open."""
    child = _child_script(tmp_path)
    procs = [subprocess.Popen([sys.executable, child, "lane%d" % i, lock, "0.3"],
                              stdout=subprocess.PIPE, text=True) for i in range(3)]
    events = []
    for p in procs:
        out, _ = p.communicate(timeout=120)
        for line in out.strip().splitlines():
            who, how, t, what = line.split("|")
            events.append((float(t), who, how, what))
    events.sort()
    assert not [e for e in events if e[2] == "FAILOPEN"], "a lane gave up instead of waiting"

    open_now, overlaps = set(), []
    for _t, who, _how, what in events:
        if what == "ACQ":
            if open_now:
                overlaps.append((who, sorted(open_now)))
            open_now.add(who)
        else:
            open_now.discard(who)
    assert not overlaps, "two lanes held the push lock at once: %r" % overlaps


def test_a_killed_holder_does_not_wedge_the_lock(tmp_path, lock):
    """THE PROPERTY THE DESIGN RESTS ON. A lane killed mid-gate releases nothing and cleans up
    nothing; the kernel drops its lock anyway. This is why the lock is an OS lock and not a file
    with a timestamp in it needing a stale-breaker - and why ship never releases it explicitly."""
    child = tmp_path / "holder.py"
    child.write_text(
        "import sys, time\n"
        "sys.path.insert(0, r'%s')\n" % TOOLS +
        "import push_lock\n"
        "h = push_lock.hold(who='victim', path=sys.argv[1], log=lambda m: None)\n"
        "print('held' if h else 'failopen', flush=True)\n"
        "time.sleep(300)\n")
    p = subprocess.Popen([sys.executable, str(child), lock], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "held"
        p.kill()
        p.wait(timeout=30)
        h = push_lock.hold(who="next lane", path=lock, timeout=20, log=lambda m: None)
        assert h is not None, "a killed holder wedged the lock"
        os.close(h)
    finally:
        if p.poll() is None:
            p.kill()


# ═══════════════════════════════════════════════════ how ship uses it
def _wt_source():
    return open(os.path.join(TOOLS, "wt.py"), encoding="utf-8").read()


def test_ship_takes_the_lock_before_it_rebases():
    """Taking it after the rebase would leave the window the lock exists to close. Since
    2026-10-07 ship ALSO rebases once before the lock (gate_before_lock, so the slow selftests run
    on a recent tree without holding anybody up) - but the rebase whose result is pushed is the
    one cmd_ship does after taking the lock, and that order is what this pins."""
    src = _wt_source()
    body = src[src.index("def cmd_ship"):]
    body = body[:body.index("push_lock.hold") + 200]
    assert "push_lock.hold(" in body
    i_lock = src.index("push_lock.hold(", src.index("def cmd_ship"))
    i_rebase = src.index("'rebase', 'origin/main'", i_lock)
    i_push = src.index("'push', '-q', 'origin', 'HEAD:main'", i_lock)
    assert i_lock < i_rebase < i_push, "the lock must be held across the rebase AND the push"
    # and the VERSION realign and the RESEARCH_LEDGER renumbering that go with that rebase
    # happen under the lock too, after it
    assert i_rebase < src.index("realign_version(wt)", i_rebase) < i_push
    assert i_rebase < src.index("renumber_ledger_rows(wt)", i_rebase) < i_push


def test_the_phase_before_the_lock_never_pushes():
    """The pre-lock phase rebases and gates, nothing more: a push from there would land a tree
    no lock ever covered."""
    src = _wt_source()
    # everything the pre-lock phase calls that cmd_ship does not: the worktree guard, the tree
    # check, the gate runner and gate_before_lock itself
    pre = src[src.index("def hold_worktree"):src.index("def _release_fd")]
    assert "def gate_before_lock" in pre and "def run_plan" in pre
    assert "'push'" not in pre and "HEAD:main" not in pre
    assert "push_lock.hold(" not in pre and "push_queue.hold_turn(" not in pre


def test_ship_lets_go_of_the_lock_only_before_it_has_pushed_anything():
    """2026-10-07: ship gives the lock (and its ticket) back by hand in exactly ONE place - when a
    slow selftest has to re-run because main changed what it reads, or (2026-10-08) the pre-push
    tests would re-run for longer than the lock should be held - BEFORE anything is pushed - so
    the next lane goes meanwhile. Every other route still leaves the release to the process exit,
    and the overtaken retry after a push keeps the lock (test_affected_tests.py)."""
    src = _wt_source()
    body = src[src.index("def cmd_ship"):src.index("def warn_pages_budget")]
    assert body.count("_let_go(") == 1, "one hand release, no more"
    i_let_go = body.index("_let_go(")
    i_branch = body.rindex("if (too_slow or tests_long) and rnd < PRELOCK_ROUNDS:", 0, i_let_go)
    assert "continue" in body[i_let_go:i_let_go + 120], "and it goes straight back to pre-lock"
    assert i_branch < i_let_go < body.index("'push', '-q', 'origin', 'HEAD:main'")
    let_go = src[src.index("def _release_fd"):src.index("def cmd_ship")]
    assert "push_lock._unlock_fd" in let_go and "push_queue._unlock_fd" in let_go
    assert "os.close(" in let_go
    # msvcrt unlocks the byte at the CURRENT position and both holders wrote their name past
    # byte 0 - without the seek the unlock misses and only the close lets go (test_wt.py proves
    # the release is immediate)
    assert "os.lseek(" in let_go


def test_ship_still_works_when_the_shared_checkout_has_no_push_lock_yet():
    """Lanes run the SHARED checkout's wt.py. One that has not synced yet must still ship."""
    src = _wt_source()
    assert "except Exception:" in src.split("import push_lock")[1][:200]
    assert "push_lock = None" in src
    assert "if push_lock else None" in src, "a missing module must not stop a ship"


def test_ship_proves_the_sha_is_on_main_before_saying_it_landed():
    """`git push` succeeding is not evidence: piped into anything it reports the PIPE's exit
    code, so a rejection reads as clean. ship's old line printed its own local head."""
    src = _wt_source()
    # Anchored on the report line, not on a fixed window after the push: narrow re-validation
    # later inserted a retry block in between, which pushed the report past a 2500-character
    # window and failed this test on perfectly correct code.
    i_push = src.index("'push', '-q', 'origin', 'HEAD:main'")
    i_report = src.index("safe_print('pushed", i_push)
    after = src[i_push:i_report]
    assert "merge-base" in after and "--is-ancestor" in after, (
        "the proof must come BEFORE anything claims the push landed")
    assert "'fetch'" in after, "it has to fetch first or it checks a stale ref"
    assert after.index("'fetch'") < after.index("merge-base")
    assert "NOT on origin/main" in after, "and say so plainly when it did not"


def test_ship_does_not_release_the_lock_early():
    """There are a dozen SystemExit paths between taking it and the push; threading a release
    through all of them is how a lock gets leaked on the one path nobody thought about. The
    process exit is the release."""
    src = _wt_source()
    body = src[src.index("def cmd_ship"):src.index("def warn_pages_budget")]
    assert "_unlock_fd" not in body and "push_lock.release" not in body
