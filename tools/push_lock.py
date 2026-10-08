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

A LIVE HOLDER IS WAITED FOR, HOWEVER LONG (2026-10-08). This used to fail open after 75 minutes
("shipping unlocked rather than blocking"). That was measured to be wrong the day the queue got
long: MANAGER's table-band ship waited 75 minutes behind tl-ship1's two-hour selftest, shipped
unlocked, passed every gate - and was rejected at the push because ORB's ship had moved main
meanwhile. Every lane queued since 10:36 was about to do the same, so the lock was turning into
an unlocked race plus a wasted re-run per lane. A waiter cannot be waiting on a DEAD holder - the
kernel drops the lock the moment its process ends, however it ends - so a held lock always means
a live ship, and going around it can only cost both of them. So now:
  * while the lock is held, the waiter keeps waiting, saying who holds it and for how long once
    every PROGRESS_EVERY (10 min);
  * a holder past LONG_HOLD (3 h) is reported ONCE, machine-wide, to the MANAGER inbox
    (tools/chat_inbox.py post MANAGER --from SHIP-QUEUE ...) with its pid and worktree - a human
    decides; the waiter keeps waiting;
  * EDGELOG_SHIP_UNLOCKED=1, set by a HUMAN for one ship, restores the old timeout and fail-open,
    said loudly when it starts and when it fires.
FAIL OPEN only when the lock MACHINERY is unusable - no state directory, no permission to open
the file: `ship` says so and proceeds unlocked. A lock that cannot be opened at all must not stop
every lane from pushing.
"""
import contextlib
import os
import re
import subprocess
import sys
import time

LOCK_NAME = "push.lock"

# How long a waiter gives a live holder before going unlocked - ONLY under the human override
# (EDGELOG_SHIP_UNLOCKED=1, see the module docstring). Without it a live holder is waited for.
DEFAULT_TIMEOUT = 75 * 60

# A progress line while waiting on a live holder (who, for how long), at most this often.
PROGRESS_EVERY = 10 * 60

# A holder past this is told to MANAGER, once per hold, machine-wide. The longest healthy hold
# measured is a two-hour selftest; three hours is a ship that needs a human.
LONG_HOLD = 3 * 60 * 60

UNLOCKED_ENV = "EDGELOG_SHIP_UNLOCKED"


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


def unlocked_override():
    """EDGELOG_SHIP_UNLOCKED=1: a human asked for the old fail-open behaviour."""
    return os.environ.get(UNLOCKED_ENV, "").strip() not in ("", "0", "false", "no")


_SINCE = re.compile(r"since (\d\d):(\d\d):(\d\d)")
_PID = re.compile(r"pid (\d+)")


def held_for(text, at=None):
    """Seconds the holder named in `text` ("lane  pid 123  since 13:06:32") has held the lock at
    epoch `at`, from its own clock-time stamp (today, or yesterday when that is in the future).
    None when the text carries no stamp."""
    m = _SINCE.search(text or "")
    if not m:
        return None
    at = time.time() if at is None else at
    lt = time.localtime(at)
    since = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, int(m.group(1)), int(m.group(2)),
                         int(m.group(3)), 0, 0, -1))
    if since > at + 60:
        since -= 24 * 3600
    return max(0.0, at - since)


def _mins(secs):
    secs = int(secs or 0)
    return "%d h %02d min" % (secs // 3600, secs % 3600 // 60) if secs >= 3600 \
        else "%d min" % (secs // 60)


def inbox_command(text):
    """The one line a long hold costs: a post to MANAGER's inbox, as SHIP-QUEUE."""
    return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "chat_inbox.py"),
            "post", "MANAGER", "--from", "SHIP-QUEUE", text]


def _post_to_manager(text):
    try:
        subprocess.run(inbox_command(text), capture_output=True, timeout=60)
    except Exception:
        pass                    # a missed post never stops a waiter


def report_long_hold(path, text, secs, notify=None, log=print):
    """Tell MANAGER, ONCE per hold machine-wide, that the lock at `path` has been held `secs` by
    the holder named in `text` - then the caller goes on waiting. Once is enforced by a marker
    file per (pid, since) created exclusively beside the lock: however many lanes wait, only the
    first to notice posts. Returns True when this call posted."""
    m = _PID.search(text or "")
    pid = m.group(1) if m else "?"
    since = _SINCE.search(text or "")
    tag = "%s-%s" % (pid, since.group(0)[6:].replace(":", "") if since else "nostamp")
    d = os.path.join(os.path.dirname(path), "long_holds")
    try:
        os.makedirs(d, exist_ok=True)
        fd = os.open(os.path.join(d, tag + ".posted"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return False
    except Exception:
        return False            # cannot mark it: better silent than one post per waiter
    worktree = (text or "?").split("  pid")[0].strip() or "?"
    line = ("push lock held %s by %s (pid %s, worktree %s) - every other lane is waiting behind "
            "it and none ships unlocked. Check that ship: kill it if it is stuck (the lock frees "
            "the moment it dies); a human may set EDGELOG_SHIP_UNLOCKED=1 for one ship to go "
            "around it." % (_mins(secs), worktree, pid, worktree))
    (notify or _post_to_manager)(line)
    log("  the push lock has been held %s by %s (pid %s) - told MANAGER once; still waiting"
        % (_mins(secs), worktree, pid))
    return True


def _wait_for_lock(fd, path, timeout, log, sleep, now, notify):
    """Block until this handle holds the lock. True when it does; False only under the human
    override, past `timeout`. While a live holder has it: a progress line every PROGRESS_EVERY,
    and one MANAGER post past LONG_HOLD."""
    override = unlocked_override()
    start = now()
    deadline = start + timeout
    said, next_progress = False, start + PROGRESS_EVERY
    if override:
        log("  !!! %s=1 - a human asked for the OLD behaviour: if the push lock is still held "
            "after %d min this lane ships UNLOCKED (a rejected push is likely)"
            % (UNLOCKED_ENV, timeout // 60))
    while True:
        try:
            _lock_fd(fd)
            return True
        except OSError:
            pass
        t = now()
        other = holder(path)
        if not said:
            log("  waiting for the push lock%s - one lane gates and pushes at a time, so "
                "neither of us re-runs a suite for nothing; a live holder is waited for "
                "(the lock frees the moment its ship ends, however it ends)"
                % (" (held by %s)" % other if other else ""))
            said = True
        if t >= next_progress:
            hf = held_for(other, time.time())
            log("  still waiting for the push lock: held by %s%s; this lane has waited %s"
                % (other or "an unnamed lane", " for %s" % _mins(hf) if hf is not None else "",
                   _mins(t - start)))
            next_progress = t + PROGRESS_EVERY
        hf = held_for(other, time.time())
        if hf is not None and hf > LONG_HOLD:
            report_long_hold(path, other, hf, notify, log)
        if override and t >= deadline:
            log("  !!! push lock still held after %d min and %s=1 - shipping UNLOCKED, as a "
                "human asked (expect a rejection)" % (timeout // 60, UNLOCKED_ENV))
            return False
        sleep(2.0)


@contextlib.contextmanager
def exclusive(who="", path=None, timeout=DEFAULT_TIMEOUT, log=print,
              sleep=time.sleep, now=time.time, notify=None):
    """Hold the machine-wide push lock. Yields True while held, False if it could not be taken.

    False means "go anyway", and happens only when the lock cannot be opened at all, or under
    the human override past `timeout` (module docstring). `who` is written into the lock file so
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

        if not _wait_for_lock(fd, path, timeout, log, sleep, now, notify):
            yield False
            return

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
         sleep=time.sleep, now=time.time, notify=None):
    """Take the lock FOR THE REST OF THIS PROCESS'S LIFE. Returns the open handle, or None.

    None - ship proceeds unlocked - only when the lock cannot be opened at all, or under the
    human override past `timeout`. A live holder is otherwise waited for (module docstring).

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

    if not _wait_for_lock(fd, path, timeout, log, sleep, now, notify):
        try:
            os.close(fd)
        except Exception:
            pass
        return None

    try:
        _write_name(fd, who)
    except Exception:
        pass                # the name is a convenience; never fail a ship over it
    if who:
        log("  push lock held by this lane (%s) - other lanes will wait here" % who)
    return fd
