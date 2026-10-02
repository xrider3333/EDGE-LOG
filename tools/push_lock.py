r"""ONE LANE AT A TIME THROUGH THE PRE-PUSH GATE.

THE PROBLEM, measured on 2026-10-02. The pre-push hook re-runs the engine test tier for any
change under augur_engine/, api/ or tests/ - almost every backend change - and that tier takes
about 23 minutes. With ~10 sessions shipping, main moves during those 23 minutes, the push is
rejected on a stale ref, and the lane starts over. This session ran the gate three times in a
row, 23m38s each, and was overtaken every time. Nothing was wrong with any of the three runs.

Two smaller things make it worse:
  - `git push` piped into another command reports the pipe's exit code, so a REJECTED push can
    look like a clean one. A lane then says "landed" when nothing landed (NOISE's 9be7e32e).
  - Every lane that loses the race re-runs a full suite, so the machine spends its time
    re-validating work that was already green rather than running anything new.

WHAT THIS DOES. One machine-wide lock, taken before the rebase and held through the gates and
the push. Whoever holds it is the only lane rebasing, gating and pushing, so nobody is overtaken
and nobody re-runs a suite for that reason. Throughput does not drop: the machine could only run
one suite quickly at a time anyway - the lock replaces several lanes running suites that will be
thrown away with one lane running a suite that counts.

WHY AN OS LOCK and not a lock file with a timestamp in it: the kernel releases an OS lock when
the handle closes OR the process dies, however it dies. A lock FILE needs a stale-breaker, and a
stale-breaker needs a threshold, and this session got that wrong in exactly the way that matters
earlier today - the breaker fired at 15s while the waiter gave up at 10s, so a leftover lock
could never be broken and a waiter silently gave up instead. There is no leftover state here to
get wrong.

FAIL OPEN. If the lock cannot be taken at all - no state directory, no permission, a timeout -
`ship` says so and proceeds unlocked. A lock that can stop every lane from pushing is worse than
the contention it exists to remove.
"""
import contextlib
import os
import time

LOCK_NAME = "push.lock"

# A holder keeps it across a rebase, several render gates and the engine tier: 23 minutes is
# normal and 40 has been seen on a busy box. 75 minutes is "something has gone wrong", not
# "somebody is slow".
DEFAULT_TIMEOUT = 75 * 60


def _home():
    return os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def lock_path():
    return os.path.join(_home(), "state", LOCK_NAME)


def _lock_fd(fd):
    """Exclusive, non-blocking. Raises OSError when another handle holds it."""
    try:
        import fcntl
    except ImportError:
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


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


# The lock covers BYTE 0 only, and the holder's name is written from BYTE 1 on. That split is
# not tidiness: on Windows msvcrt.locking takes a MANDATORY lock, so another process reading the
# locked byte gets a permission error - a reader that started at 0 could never read the name and
# the waiting message silently said nobody held it. Measured, then fixed.
_NAME_OFFSET = 1


def holder(path=None):
    """Who says they hold it, for a waiting message. Advisory only - it is read WITHOUT the
    lock, so it can be a moment stale, or empty between taking the lock and writing the name."""
    try:
        with open(path or lock_path(), "rb") as fh:
            fh.seek(_NAME_OFFSET)
            return fh.read(200).decode("utf-8", "replace").strip(chr(0) + " ").strip()
    except Exception:
        return ""


def _write_name(fd, who):
    """Record who holds it, past the locked byte. Never fails a ship - it is a convenience."""
    try:
        os.truncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"#")                      # the locked byte; readers must not need it
        os.write(fd, ("%s  pid %d  since %s"
                      % (who or "a lane", os.getpid(),
                         time.strftime("%H:%M:%S"))).encode("utf-8", "replace"))
    except Exception:
        pass


@contextlib.contextmanager
def exclusive(who="", path=None, timeout=DEFAULT_TIMEOUT, log=print,
              sleep=time.sleep, now=time.time):
    """Hold the machine-wide push lock. Yields True while held, False if it could not be taken.

    False always means "go anyway": see FAIL OPEN above. `who` is written into the lock file so
    a waiting lane can say who it is waiting for.
    """
    path = path or lock_path()
    fd = None
    try:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_RDWR)
        except Exception as e:
            log("  push lock unavailable (%s: %s) - shipping unlocked" % (type(e).__name__, e))
            yield False
            return

        deadline = now() + timeout
        said = False
        while True:
            try:
                _lock_fd(fd)
                break
            except OSError:
                if not said:
                    other = holder(path)
                    log("  waiting for the push lock%s - one lane gates and pushes at a time, "
                        "so neither of us re-runs a suite for nothing"
                        % (" (held by %s)" % other if other else ""))
                    said = True
                if now() >= deadline:
                    log("  push lock still held after %d min - shipping unlocked rather than "
                        "blocking (expect a possible rejection)" % (timeout // 60))
                    yield False
                    return
                sleep(2.0)

        try:
            try:
                _write_name(fd, who)
            except Exception:
                pass        # the name is a convenience; never fail a ship over it
            yield True
        finally:
            _unlock_fd(fd)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass


def hold(who="", path=None, timeout=DEFAULT_TIMEOUT, log=print,
         sleep=time.sleep, now=time.time):
    """Take the lock FOR THE REST OF THIS PROCESS'S LIFE. Returns the open handle, or None.

    There is deliberately no release. The caller - `wt.py ship` - has a dozen `raise SystemExit`
    paths between here and its push (a failed rebase, each render gate, the test tiers), and
    threading a release through all of them is how a lock ends up leaked on the one path nobody
    thought about. An OS lock on an open handle is released by the kernel when the process ends,
    by every route including a kill, so there is nothing to thread.

    KEEP THE RETURN VALUE IN A LIVE VARIABLE. If the handle is garbage collected and closed the
    lock goes with it.
    """
    path = path or lock_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR)
    except Exception as e:
        log("  push lock unavailable (%s: %s) - shipping unlocked" % (type(e).__name__, e))
        return None

    deadline = now() + timeout
    said = False
    while True:
        try:
            _lock_fd(fd)
            break
        except OSError:
            if not said:
                other = holder(path)
                log("  waiting for the push lock%s - one lane gates and pushes at a time, so "
                    "neither of us re-runs a suite for nothing"
                    % (" (held by %s)" % other if other else ""))
                said = True
            if now() >= deadline:
                log("  push lock still held after %d min - shipping unlocked rather than "
                    "blocking (a rejection is possible)" % (timeout // 60))
                try:
                    os.close(fd)
                except Exception:
                    pass
                return None
            sleep(2.0)

    try:
        _write_name(fd, who)
    except Exception:
        pass                # the name is a convenience; never fail a ship over it
    if who:
        log("  push lock held by this lane (%s) - other lanes will wait here" % who)
    return fd
