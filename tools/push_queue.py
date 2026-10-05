r"""FIRST COME, FIRST SERVED for the push lock.

THE PROBLEM I CAUSED. tools/push_lock.py serialises lanes, but it is not fair: a waiter takes the
lock whenever it happens to find it free, so arrival order means nothing. On 2026-10-04 the
rocfrontier lane waited more than 80 minutes while lanes that arrived later went ahead of it. With
~24-minute gates and a machine that turns off in the evening, losing the draw repeatedly means a
lane's work does not land at all that day. That is my design, not bad luck.

HOW A TURN IS ESTABLISHED. Each waiter mints a numbered ticket and then holds an exclusive OS lock
on its own ticket file for as long as it is waiting. A ticket counts as LIVE only while that lock
is held, so liveness is proved by the kernel: when a waiter exits, crashes or is killed, its lock
goes with the process and its ticket stops being live immediately. A lane may proceed when no live
ticket has a smaller number than its own.

WHY NOT A HEARTBEAT. Because a heartbeat needs a staleness threshold, and a threshold is the thing
I already got wrong once in this codebase: push_lock's first version had a stale-breaker whose
threshold (15s) was longer than the waiter's own timeout (10s), so a leftover lock could never be
broken and a waiter silently gave up and sent an unrecorded request. A rule the kernel enforces
has no threshold to misjudge - see [[edgelog-cross-process-lock]].

FAIRNESS IS NOT A GUARANTEE OF SERVICE. Everything here fails open the way the lock does: if the
ticket directory cannot be made, the counter cannot be minted, or a lane waits past its timeout,
it proceeds anyway and says so. A queue that can stop a lane shipping is worse than an unfair one.
"""
import contextlib
import os
import re
import time

try:
    from push_lock import _lock_fd, _unlock_fd        # one locking primitive, not two
except ImportError:                                    # imported as tools.push_queue
    from tools.push_lock import _lock_fd, _unlock_fd

# A lane holds its ticket across the rebase, the gates and the push: 24 minutes is normal, and a
# queue of three is routine. 3 hours is "something is wrong", not "somebody is slow".
DEFAULT_TIMEOUT = 3 * 60 * 60

# What one lane's turn costs, for the ETA. Measured on this box: the engine tier runs 9-24 min
# depending on how busy it is, plus the render gates.
MINUTES_PER_TURN = 24

TICKET_RE = re.compile(r"^(\d+)-(\d+)\.ticket$")


def _home():
    return os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def queue_dir():
    return os.path.join(_home(), "state", "push_queue")


def _counter_path(d):
    return os.path.join(d, "counter")


def _mint(d):
    """The next ticket number, allocated under a brief lock so two lanes cannot share one.

    The counter only ever goes up. It is not reset: a number is cheap and a reused number would
    put two lanes in the same position, which is the one thing a queue must not do.
    """
    lock = os.path.join(d, "counter.lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR)
    try:
        for _ in range(500):                      # ~10s of contention at most; minting is quick
            try:
                _lock_fd(fd)
                break
            except OSError:
                time.sleep(0.02)
        else:
            return None
        try:
            try:
                with open(_counter_path(d), encoding="utf-8") as fh:
                    n = int(fh.read().strip() or "0")
            except Exception:
                n = 0
            n += 1
            tmp = _counter_path(d) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(str(n))
            os.replace(tmp, _counter_path(d))
            return n
        finally:
            _unlock_fd(fd)
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


def _is_live(path):
    """Is somebody still waiting on this ticket? True when its lock is HELD by a live process.

    Tested by trying to take the lock: if that succeeds the holder is gone, so the ticket is dead
    and we release it again immediately. An unreadable or vanished ticket counts as dead.
    """
    try:
        fd = os.open(path, os.O_RDWR)
    except Exception:
        return False
    try:
        try:
            _lock_fd(fd)
        except OSError:
            return True                           # still held: a live waiter
        _unlock_fd(fd)
        return False
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


def live_tickets(d=None):
    """[(number, path)] of every ticket still being waited on, lowest number first."""
    d = d or queue_dir()
    out = []
    try:
        names = os.listdir(d)
    except Exception:
        return out
    for name in names:
        m = TICKET_RE.match(name)
        if not m:
            continue
        p = os.path.join(d, name)
        if _is_live(p):
            out.append((int(m.group(1)), p))
        else:
            try:
                os.remove(p)                      # a dead waiter's litter, swept as we pass
            except Exception:
                pass
    return sorted(out)


@contextlib.contextmanager
def wait_turn(who="", timeout=DEFAULT_TIMEOUT, log=print, sleep=time.sleep, now=time.time):
    """Hold a ticket until it is the oldest live one. Yields the ticket number, or None.

    None means "go anyway": the queue could not be used, or the wait ran past `timeout`. The
    caller still has to take the push lock itself - this decides WHOSE TURN it is, not who holds
    the lock, and the two are deliberately separate so a failure here cannot let two lanes gate at
    once.
    """
    d = queue_dir()
    fd = None
    path = None
    try:
        try:
            os.makedirs(d, exist_ok=True)
            n = _mint(d)
            if n is None:
                log("  push queue unavailable (could not mint a ticket) - going ahead unqueued")
                yield None
                return
            path = os.path.join(d, "%d-%d.ticket" % (n, os.getpid()))
            fd = os.open(path, os.O_CREAT | os.O_RDWR)
            _lock_fd(fd)                          # held for as long as we wait: this IS the proof
            try:
                os.write(fd, (who or "a lane").encode("utf-8", "replace"))
            except Exception:
                pass
        except Exception as e:
            log("  push queue unavailable (%s: %s) - going ahead unqueued"
                % (type(e).__name__, e))
            yield None
            return

        deadline = now() + timeout
        said = None
        while True:
            ahead = [t for t in live_tickets(d) if t[0] < n]
            if not ahead:
                if said:
                    log("  your turn (ticket %d)" % n)
                break
            if len(ahead) != said:
                log("  queued for the push gate: ticket %d, %d lane(s) ahead, roughly %d min"
                    % (n, len(ahead), len(ahead) * MINUTES_PER_TURN))
                said = len(ahead)
            if now() >= deadline:
                log("  still queued after %d min - going ahead out of turn rather than not at all"
                    % (timeout // 60))
                yield None
                return
            sleep(2.0)
        yield n
    finally:
        if fd is not None:
            _unlock_fd(fd)
            try:
                os.close(fd)
            except Exception:
                pass
        if path:
            try:
                os.remove(path)
            except Exception:
                pass


def hold_turn(who="", timeout=DEFAULT_TIMEOUT, log=print, sleep=time.sleep, now=time.time):
    """Wait for this lane's turn and KEEP the ticket for the rest of the process's life.

    Returns (number, handle), or (None, None) when the queue could not be used or the wait ran
    out - both of which mean "go ahead anyway". There is deliberately no release, for the same
    reason push_lock.hold has none: `ship` has a dozen SystemExit paths between here and its push,
    and the process exit IS the release, by every route including a kill.

    KEEP THE HANDLE IN A LIVE VARIABLE. If it is garbage collected the ticket stops being live and
    a later lane will go ahead of this one.
    """
    d = queue_dir()
    try:
        os.makedirs(d, exist_ok=True)
        n = _mint(d)
        if n is None:
            log("  push queue unavailable (could not mint a ticket) - going ahead unqueued")
            return None, None
        path = os.path.join(d, "%d-%d.ticket" % (n, os.getpid()))
        fd = os.open(path, os.O_CREAT | os.O_RDWR)
        _lock_fd(fd)
        try:
            os.write(fd, (who or "a lane").encode("utf-8", "replace"))
        except Exception:
            pass
    except Exception as e:
        log("  push queue unavailable (%s: %s) - going ahead unqueued" % (type(e).__name__, e))
        return None, None

    deadline = now() + timeout
    said = None
    while True:
        ahead = [t for t in live_tickets(d) if t[0] < n]
        if not ahead:
            if said:
                log("  your turn (ticket %d)" % n)
            return n, fd
        if len(ahead) != said:
            log("  queued for the push gate: ticket %d, %d lane(s) ahead, roughly %d min"
                % (n, len(ahead), len(ahead) * MINUTES_PER_TURN))
            said = len(ahead)
        if now() >= deadline:
            log("  still queued after %d min - going ahead out of turn rather than not at all"
                % (timeout // 60))
            return None, fd
        sleep(2.0)
