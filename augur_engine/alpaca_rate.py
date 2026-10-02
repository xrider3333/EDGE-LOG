r"""ONE ACCOUNT-WIDE PACE FOR EVERY ALPACA REQUEST, SHARED ACROSS PROCESSES.

THE PROBLEM (2026-10-02). Alpaca's 200 requests/minute is per ACCOUNT, and five lanes now pull
through the same key: NQBRD, TTM 20c, TBIS r3, TRANSFER r2 and SIPORB. Every one of them paces
itself at ~195/min on the assumption that it is alone (`time.sleep(0.31)` between pages), so two
running at once is already over the cap and five is five times over. What that looks like in
practice is not a clean error: every lane gets 429s, every lane sleeps 20 seconds, and they all
come back together and do it again. A multi-hour pull turns into a multi-day one, and the lane
that happens to ask last wears the failure.

Running the pulls strictly one at a time fixes it, but only while somebody is there to sequence
them. This paces them instead: a token bucket in one small file that every process checks before
every request, so the ACCOUNT stays under the cap no matter how many lanes are running and they
can all run at once.

HOW: the file holds the timestamps of recent requests. Before a request, a caller takes the lock,
drops timestamps older than the window, and either records its own and goes, or sleeps until the
oldest falls out of the window and tries again. The lock is a separate file created O_EXCL, with a
stale-breaker, so one process killed mid-pull cannot wedge every other lane.

FAIL-OPEN, DELIBERATELY. Any failure in here - no state directory, a corrupt file, a lock that
cannot be taken - lets the request through rather than raising. A limiter that can kill a six-hour
pull is worse than the 429s it exists to avoid, and the per-caller `time.sleep` pacing each tool
already does is still in place underneath as the floor.

VERIFIED ACROSS REAL PROCESSES, not only by the unit tests. tools/alpaca_rate_check.py runs
several processes against one budget and checks the invariant; it is what caught both real
defects in this module, neither of which a single-process test could reproduce:

  - the first version's lock was an O_EXCL file with a timestamp in it and a stale-breaker whose
    threshold (15s) was LONGER than the wait (10s), so a leftover lock could never be broken: one
    process waited its full ten seconds, failed open, and sent an UNRECORDED request. Ten
    requests at a cap of six put NINE in one window and recorded four.
  - with an OS lock: twelve requests across four processes, worst window six, the whole budget
    recorded, opening cluster 0.124s instead of 15.076s.

USE:
    from augur_engine import alpaca_rate
    alpaca_rate.wait()          # immediately before each HTTP request
"""
import contextlib
import json
import os
import time

# 200/min is the documented free-plan cap. 180 leaves room for the requests this cannot see:
# a lane someone runs by hand, a retry inside `requests`, the clock being a little off between
# a process's own view and Alpaca's.
DEFAULT_PER_MIN = 180
WINDOW_SECONDS = 60.0

# A small margin on top of the window before a held-back request is released. It is slack, not
# a correctness fix - what makes "no 60-second window holds more than the cap" true is the
# inclusive lower bound in _read, and its reasoning is written there. A quarter of a second
# costs nothing at 180/min.
RELEASE_MARGIN_SECONDS = 0.25

# A holder only ever reads a small file, appends one number and replaces it, so a few seconds is
# already generous. The lock is an OS lock (see _lock), which the kernel releases when the
# process dies, so this timeout covers CONTENTION only - never a dead holder.
LOCK_WAIT_SECONDS = 5.0

def _home():
    return os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def state_path():
    return os.path.join(_home(), "state", "alpaca_rate.json")


def per_min():
    """The cap, overridable per machine without an edit (a paid plan raises it)."""
    try:
        v = int(os.environ.get("ALPACA_RATE_PER_MIN", "") or DEFAULT_PER_MIN)
        return v if v > 0 else DEFAULT_PER_MIN
    except Exception:
        return DEFAULT_PER_MIN


# ── the lock ─────────────────────────────────────────────────────────────────────────────
# An OS lock on a small file that is created once and never removed. The earlier version was a
# lock FILE created O_EXCL plus a timestamp inside it and a stale-breaker, and two real
# processes showed what is wrong with that: the breaker's threshold (15s) was longer than the
# wait (10s), so a leftover lock could never be broken - the waiter always gave up first, failed
# open, and sent an UNRECORDED request. 10 requests at a cap of 6 put 9 into one window and
# recorded 4. An OS lock has no leftover state to reason about at all: the kernel drops it when
# the handle closes or the process exits, however it exits.
def _lock_fd(fd, blocking=False):
    """Take an exclusive lock on one byte of `fd`. Raises OSError if it is already held."""
    try:
        import fcntl
    except ImportError:
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
        return
    fcntl.flock(fd, fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB))


def _unlock_fd(fd):
    try:
        import fcntl
    except ImportError:
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass


@contextlib.contextmanager
def _lock(lock_path, timeout=LOCK_WAIT_SECONDS, sleep=time.sleep, now=time.time):
    """Yields True while the lock is held, False if it could not be taken in `timeout`.

    False means FAIL OPEN: the caller sends its request without recording it. That is the right
    trade for a credential-free pacing aid - a limiter must not be able to kill a six-hour pull -
    but it has to be RARE, which is the whole reason this is an OS lock rather than a flag file.
    """
    fd = None
    try:
        try:
            os.makedirs(os.path.dirname(lock_path), exist_ok=True)
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        except Exception:
            yield False
            return
        deadline = now() + timeout
        while True:
            try:
                _lock_fd(fd)
                break
            except OSError:
                if now() >= deadline:
                    yield False
                    return
                sleep(0.02)
        try:
            yield True
        finally:
            _unlock_fd(fd)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


# ── the bucket ───────────────────────────────────────────────────────────────────────────
def _read(path, now):
    """Recent request timestamps, oldest first. A timestamp in the future is discarded: the
    only ways to get one are a clock change or a corrupt file, and keeping it would throttle
    every lane for as long as it is ahead."""
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        stamps = [float(t) for t in (got.get("requests") or [])]
    except Exception:
        return []
    # <= on the lower bound, not <, and this is what makes "no 60-second window anywhere holds
    # more than the cap" true rather than merely likely. Take the last request granted inside
    # any such window: every earlier request in it is within 60 seconds of that one, so it was
    # counted when that one asked, and it was granted only because the count was below the cap.
    # With a strict < a request sitting exactly on the boundary drops out of that count, and the
    # window ends up holding one more than the cap - which two real processes duly did.
    return sorted(t for t in stamps if now - WINDOW_SECONDS <= t <= now + 1.0)


def _write(path, stamps):
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"requests": [round(t, 3) for t in stamps]}, fh)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False


def wait(path=None, limit=None, sleep=time.sleep, now=time.time, max_total_wait=120.0):
    """Block until this process may send one Alpaca request, then record it.

    Returns the seconds waited (0.0 when it went straight through), which is what a caller
    logs when it wants to show a lane being paced rather than stuck.

    `max_total_wait` is a backstop: if a bucket somehow stays full far longer than a window -
    another lane writing timestamps faster than it spends them, say - this gives up waiting and
    lets the request through. One 429 is recoverable; a pull wedged for an hour with nothing in
    the log is not.
    """
    path = path or state_path()
    limit = limit or per_min()
    lock = path + ".lock"
    started = now()
    while True:
        with _lock(lock, sleep=sleep, now=now) as held:
            if not held:
                # Fail open WITHOUT touching the state: reading and writing it unlocked is the
                # very race the lock exists to prevent, and it would corrupt the count for
                # every other lane as well as this one.
                return max(0.0, now() - started)
            t = now()
            stamps = _read(path, t)
            if len(stamps) < limit:
                stamps.append(t)
                if not _write(path, stamps):
                    # The request is about to be sent and nothing recorded it. Say so: a silent
                    # drop here is the account quietly going over the cap.
                    return max(0.0, t - started)
                return max(0.0, t - started)
            oldest = stamps[0]
            # the moment the oldest leaves the window there is room for exactly one more
            nap = max(0.01, (oldest + WINDOW_SECONDS) - t + RELEASE_MARGIN_SECONDS)
        if (now() - started) + nap > max_total_wait:
            return max(0.0, now() - started)
        sleep(min(nap, 5.0))


def snapshot(path=None, now=time.time):
    """(requests in the last window, the cap) - for a status line, never for a decision."""
    path = path or state_path()
    return len(_read(path, now())), per_min()
