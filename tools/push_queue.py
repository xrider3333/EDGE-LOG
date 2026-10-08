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

A LIVE QUEUE IS NEVER JUMPED (2026-10-08). This used to give up after 3 hours and go "ahead out
of turn rather than not at all". With ~25 lanes queued on 2026-10-08 every lane that arrived
after 10:36 hit that timeout, jumped, then hit the push lock's own timeout and shipped unlocked
(MANAGER's table-band ship: 180 min queued, 75 min on the lock, every gate passed, rejected at the
push because ORB's ship had moved main) - order broke down into unlocked races and wasted
re-runs. A ticket ahead is live only while its lane's process holds its lock (the kernel proves
it), so a lane is never waiting on a dead one; it waits as long as the lanes ahead are alive:
  * a progress line every push_lock.PROGRESS_EVERY (10 min): position, and who holds the push
    lock for how long;
  * a push-lock holder past push_lock.LONG_HOLD (3 h) is reported ONCE, machine-wide, to MANAGER
    (push_lock.report_long_hold); the lane keeps waiting;
  * EDGELOG_SHIP_UNLOCKED=1, set by a HUMAN, restores the old timeout and going out of turn, said
    loudly.
It still FAILS OPEN when the queue MACHINERY is unusable - the ticket directory cannot be made or
opened, the counter cannot be minted - and says so: a queue that cannot even be joined must not
stop a lane shipping.
"""
import contextlib
import os
import re
import time

try:
    import push_lock as _pl                           # one locking primitive, not two
except ImportError:                                    # imported as tools.push_queue
    from tools import push_lock as _pl
_lock_fd, _unlock_fd = _pl._lock_fd, _pl._unlock_fd

# How long a lane waits behind LIVE lanes before going out of turn - ONLY under the human
# override (EDGELOG_SHIP_UNLOCKED=1). Without it a live queue is waited for.
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


class _Waiting(object):
    """The shared wait loop of wait_turn and hold_turn: the old position message whenever the
    number ahead changes, a progress line every PROGRESS_EVERY, the long-hold report, and - only
    under the human override - the old timeout."""

    def __init__(self, n, timeout, log, now, notify):
        self.n, self.log, self.now, self.notify = n, log, now, notify
        self.override = _pl.unlocked_override()
        self.start = now()
        self.deadline = self.start + timeout
        self.timeout = timeout
        self.said = None
        self.next_progress = self.start + _pl.PROGRESS_EVERY
        if self.override:
            log("  !!! %s=1 - a human asked for the OLD behaviour: still queued after %d min "
                "this lane goes ahead OUT OF TURN" % (_pl.UNLOCKED_ENV, timeout // 60))

    def tick(self, ahead):
        """Called while `ahead` (live tickets older than ours) is not empty. True: stop waiting
        (the override's timeout ran out)."""
        n, log = self.n, self.log
        if len(ahead) != self.said:
            log("  queued for the push gate: ticket %d, %d lane(s) ahead, roughly %d min"
                % (n, len(ahead), len(ahead) * MINUTES_PER_TURN))
            self.said = len(ahead)
        t = self.now()
        lock = _pl.lock_path()
        other = _pl.holder(lock) if os.path.exists(lock) else ""
        hf = _pl.held_for(other, time.time()) if other else None
        if t >= self.next_progress:
            log("  still queued: ticket %d, %d live lane(s) ahead (oldest ticket %d); the push "
                "lock is %s; this lane has waited %s"
                % (n, len(ahead), ahead[0][0],
                   "held by %s%s" % (other, " for %s" % _pl._mins(hf) if hf is not None else "")
                   if other and _held(lock) else "free", _pl._mins(t - self.start)))
            self.next_progress = t + _pl.PROGRESS_EVERY
        if hf is not None and hf > _pl.LONG_HOLD and _held(lock):
            _pl.report_long_hold(lock, other, hf, self.notify, log)
        if self.override and t >= self.deadline:
            log("  !!! still queued after %d min and %s=1 - going ahead OUT OF TURN, as a human "
                "asked" % (self.timeout // 60, _pl.UNLOCKED_ENV))
            return True
        return False


def _held(path):
    """Is the push lock at `path` held right now (by anyone)?"""
    try:
        fd = os.open(path, os.O_RDWR)
    except Exception:
        return False
    try:
        try:
            _lock_fd(fd)
        except OSError:
            return True
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
def wait_turn(who="", timeout=DEFAULT_TIMEOUT, log=print, sleep=time.sleep, now=time.time,
              notify=None):
    """Hold a ticket until it is the oldest live one. Yields the ticket number, or None.

    None means "go anyway": the queue could not be used at all, or - only under the human
    override - the wait ran past `timeout`. The caller still has to take the push lock itself -
    this decides WHOSE TURN it is, not who holds the lock, and the two are deliberately separate
    so a failure here cannot let two lanes gate at once.
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

        w = _Waiting(n, timeout, log, now, notify)
        while True:
            ahead = [t for t in live_tickets(d) if t[0] < n]
            if not ahead:
                if w.said:
                    log("  your turn (ticket %d)" % n)
                break
            if w.tick(ahead):
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


def hold_turn(who="", timeout=DEFAULT_TIMEOUT, log=print, sleep=time.sleep, now=time.time,
              notify=None):
    """Wait for this lane's turn and KEEP the ticket for the rest of the process's life.

    Returns (number, handle); (None, None) when the queue could not be used at all; (None,
    handle) only under the human override once its timeout ran out - "go ahead anyway" (module
    docstring: a live queue is otherwise waited for). There is deliberately no release, for the same
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

    w = _Waiting(n, timeout, log, now, notify)
    while True:
        ahead = [t for t in live_tickets(d) if t[0] < n]
        if not ahead:
            if w.said:
                log("  your turn (ticket %d)" % n)
            return n, fd
        if w.tick(ahead):
            return None, fd
        sleep(2.0)
