r"""ONE place for "wait until it happened", for tests that start real threads.

WHY (2026-10-04/05). `tests/test_qqq_exec_stream_wiring.py` joined a real thread with a 3-second
timeout and then asserted the thread had stopped. It passed alone in 10 seconds and with all 802
qqq_exec tests in 70, and failed in the full 3,600-test suite beside the live runner fleet - and
since the pre-push gate runs the full suite, it refused EVERY lane's engine-tier push until it was
fixed. Two tests there were converted to wait on conditions; this module exists because the same
shape was still in four other places, and a fix applied by hand four times is a fix that comes
back.

WHY A LONG DEADLINE DOES NOT WEAKEN A TEST. These assertions are about whether something happens
AT ALL - a stream torn down, a loop standing down, a state saved. If the thing is broken the
predicate never becomes true however long you wait, so a slow pass and a real failure stay exactly
as far apart as they were. What a SHORT deadline adds is only the chance of calling healthy code
broken because the box was busy. The cost of being generous is paid only when a test is already
failing; the cost of being tight is paid at random, on green code, in everyone's gate.

WHAT STILL BELONGS AS A FIXED SLEEP. Making something deliberately SLOWER than a patched timeout
(`time.sleep(2.0)` against a 0.1s limit) is the opposite direction and is safe: a busy box makes
those more reliable, not less. So is sleeping before asserting that something did NOT happen -
waiting longer only makes that stricter. This module is for the other direction, and
tests/test_thread_wait_pattern.py keeps it that way.
"""
import time

# One number, deliberately generous. See the module docstring for why this cannot mask a bug.
WAIT_SECONDS = 30.0

# A join shorter than this is the pattern that broke the gate. The guard test enforces it.
MIN_JOIN_SECONDS = 10.0


def wait_for(pred, timeout=WAIT_SECONDS, interval=0.01):
    """Block until `pred()` is true, or `timeout` passes. Returns what pred() last said.

    Use this instead of sleeping for however long you guess the work takes:
        assert wait_for(lambda: calls["start"] == 1)
    """
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(interval)
    return bool(pred())


def join_done(t, timeout=WAIT_SECONDS):
    """Join a thread and report whether it actually finished.

        assert join_done(t), "the loop must stand down"

    A thread that has already exited returns immediately, so the generous default costs nothing
    on the happy path - which is every run except the one where the test has found a real bug.
    """
    t.join(timeout=timeout)
    return not t.is_alive()
