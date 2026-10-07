r"""FIRESTORE SELF-HEAL for the job runner (api/runner.py) -- 2026-10-07.

THE INCIDENT. From ~09:25 MST on 2026-10-07 every Firestore call in all five runner
processes (the primary and drain-only workers 2-5) failed for 3 h 20 min:

    [queue] skipped: RetryError: Timeout of 300.0s exceeded, last exception: 503 failed to
    connect to all addresses; last error: UNKNOWN: ipv4:192.178.164.95:443: tcp handshaker
    shutdown            (and "... socket is null")

plus "[orphan] sweep skipped", "[cmd-thread] poll skipped", the paper-leg prunes, the
nt-heartbeat and nt-bridge publishes - while a FRESH python process on the same PC reached
Firestore at once. A full fleet restart at 12:48 fixed it instantly. The same shape was seen
on 2026-09-08 (long-lived channels stuck on a dead IPv6 path) and on the cloud box on 10-05
(api/qqq_exec.py's FIRESTORE WEDGE RECOVERY, the prior art this module follows). The PC has
two default routes and sleeps at night; a long-lived gRPC channel can wedge and never come
back on its own, and NOTHING relaunched a runner that exited, so the only cure was a person.

WHAT THIS DOES, smallest step first:
  1. COUNT (FsHealth, the module-level HEALTH). The runner's Firestore call sites report in:
     the queue poll, the commands poll, the orphan sweep, the cmd-thread poll, a running job's
     heartbeat and control reads, the queue/commands listener snapshots. Connection-class
     failures (503 / UNAVAILABLE, RetryError and deadline timeouts, "failed to connect", DNS,
     "tcp handshaker shutdown", "socket is null") count; ANY success resets the count; a
     quota / permission / precondition error is neither - the server answered, and neither a
     new connection nor a restart can fix those.
  2. PROBE (Monitor). While the count is above zero the monitor makes one bounded read of a
     doc that never exists (FirestoreQueue.probe: retry=None, PROBE_TIMEOUT_SEC) every
     PROBE_EVERY_SEC, so detection does not depend on what the main loop happens to be doing
     (on 10-07 the primary's main loop sat inside ~18 paper-leg prunes of 300 s each for 90
     min). A process that has recorded nothing at all for QUIET_PROBE_SEC also probes once.
     A healthy runner records successes every few minutes, so this costs no reads normally.
  3. REBUILD after REBUILD_AFTER_SEC of nothing but failures (at least two in a row): a new
     client object (FirestoreHandle.rebuild) built on a channel of its OWN - a local gRPC
     subchannel pool, so the new channel cannot be handed the old one's stuck connection -
     and the queue / commands listeners re-attached to it. Every holder of the runner's
     `q.db` (main loop, cmd thread, nt-bridge thread, paper hooks, a running job's refs via
     FirestoreQueue._live_ref) moves to it at once. The very first client is firebase_admin's
     cached one, which other code may hold raw (the qqq-exec fallback thread), so it is only
     DROPPED, never closed; a client this module built is closed when it is replaced. One
     log line.
  4. RESTART after EXIT_AFTER_SEC more of failures with no success through the rebuilt
     client: the process relaunches its replacement and exits with EXIT_CODE (75) - BUT ONLY
     when (a) it holds no job (JOB_SLOT, held by FirestoreQueue.run_once from the claim write
     to the end of the job's save; the monitor takes it itself before exiting, so nothing can
     be claimed in the meantime), (b) the primary is not mid master-refresh, (c) the network
     itself is up (a plain TCP connect to firestore.googleapis.com:443 - when the PC is
     offline a restart cannot help, so it waits instead of looping), and (d) this outage has
     not already cost MAX_RESTARTS_PER_OUTAGE restarts. A process that cannot exit for any
     of those reasons stays up and rebuilds again every EXIT_AFTER_SEC instead, with one log
     line saying why.
  5. RELAUNCH. Nothing used to relaunch an exited runner: the primary is the last line of
     C:\EdgeLog\_restart_runner.bat and a worker is a bare `cmd /c python ...` started by
     C:\EdgeLog\_run_worker.vbs. So the exiting process starts its replacement first,
     through the SAME detached launchers tools/fleet_restart.py uses (wscript, window style
     0 - never a console-attached launch: see the 0xC0000142 notes in fleet_restart.py):
       worker N  -> wscript C:\EdgeLog\_run_worker.vbs N, then waits WORKER_GRACE_SEC before
                    exiting, so a worker N python exists at every instant (the primary's own
                    keep-aware relaunch can then never start a second worker N);
       primary   -> wscript C:\EdgeLog\_restart_runner_hidden.vbs with EDGELOG_KEEP set to
                    every worker number, i.e. the everyday `fleet_restart.py --keep 2 3 4 5`
                    path: the bat's helper kills only the old primary, relaunches any worker
                    that is missing, and starts the new primary. Workers are never touched.
     No scheduled task, no Windows setting, no launcher edit. If the launcher is missing
     (not Windows, a test, the cloud box - where the runner refuses to start anyway) or the
     spawn fails, the process does NOT exit; it stays up and keeps rebuilding.
  6. MID-JOB the process never exits. The job keeps computing: while HEALTH is down() its
     progress callback skips the control read and progress write (each would otherwise block
     the engine for the client's 300 s retry), the heartbeat keeps trying on its own thread,
     and a job that finishes during the outage holds its result up to SAVE_WAIT_MAX_SEC for
     the connection to come back (wait_until_reachable) before the normal save runs through
     the rebuilt client. If it never comes back the save's own fallbacks run as before and
     the orphan sweep requeues the job once a runner can reach Firestore again.
  7. PHONE NOTE. A runner that was started by step 5 (RELAUNCH_ENV in its environment) sends
     ONE low-priority plain note when its first Firestore call succeeds - "Job runner:
     reconnected" - at most once a day across all five processes (ntfy_push.dedupe over a
     shared state file under an OS lock).

TIMINGS (constants below): rebuild after 10 min of failures, restart 10 min after that, so an
idle runner is back ~20-35 min after an outage starts instead of 3 h 20 min. Logs: one
`[fs-health] HH:MM:SS ...` line per state change.
"""
import contextlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

REBUILD_AFTER_SEC = 10 * 60.0      # nothing but connection failures this long -> new client
EXIT_AFTER_SEC = 10 * 60.0         # still failing this long after a rebuild -> restart (idle only)
CHECK_SEC = 30.0                   # monitor cadence
PROBE_EVERY_SEC = 60.0             # one bounded probe read this often while failing
PROBE_TIMEOUT_SEC = 20.0           # the probe's own deadline (retry=None)
QUIET_PROBE_SEC = 15 * 60.0        # nothing recorded at all for this long -> one probe
SAVE_WAIT_MAX_SEC = 30 * 60.0      # a job finishing mid-outage holds its result this long
MAX_RESTARTS_PER_OUTAGE = 3        # self-restarts in one outage before it just stays up
EXIT_CODE = 75                     # EX_TEMPFAIL: "restarted itself to reconnect"
WORKER_GRACE_SEC = 10.0            # the old worker outlives its replacement's launch this long
PRIMARY_GRACE_SEC = 3.0            # the bat's helper kills the old primary anyway
RELAUNCH_ENV = "EDGELOG_FS_RELAUNCH"   # "<first failure epoch>:<restart count>"
LAUNCH_DIR = r"C:\EdgeLog"         # where _run_worker.vbs / _restart_runner_hidden.vbs live
NET_HOST = ("firestore.googleapis.com", 443)
KEEP_ALL_WORKERS = ",".join(str(n) for n in range(2, 22))   # every worker number, never 'primary'
PUSH_KEY = "runner_reconnected"

# The quota / permission family: the server ANSWERED. Checked first. Status codes are
# matched as whole numbers (an address or a port must never read as one).
_NOT_CONN = ("resourceexhausted", "resource exhausted", "quota",
             "permissiondenied", "permission denied", "unauthenticated", "invalid authentication",
             "failedprecondition", "failed precondition", "invalidargument", "notfound")
_NOT_CONN_CODE = re.compile(r"(?<![\d.:])(?:429|403|401|400|404|409|412)(?![\d.])")
_CONN_CODE = re.compile(r"(?<![\d.:])(?:503|504)(?![\d.])")
_CONN = ("unavailable", "failed to connect", "deadline", "timed out", "timeout of",
         "retryerror", "handshaker", "socket is null", "socket closed", "fd shutdown",
         "connection reset", "connection refused", "connection aborted", "connectionerror",
         "dns", "getaddrinfo", "name resolution", "unreachable", "network is down",
         "probe still running")


def is_conn_error(err):
    """True when `err` (an exception or its text) reads as "could not reach Firestore" -
    the failures a new connection or a fresh process can fix."""
    if isinstance(err, (TimeoutError, ConnectionError, socket.gaierror)):
        return True
    text = (f"{type(err).__name__}: {err}" if isinstance(err, BaseException)
            else str(err or "")).lower()
    if any(m in text for m in _NOT_CONN) or _NOT_CONN_CODE.search(text):
        return False
    return bool(_CONN_CODE.search(text)) or any(m in text for m in _CONN)


class FsHealth:
    """Consecutive connection-class Firestore failures for THIS process. Thread-safe: the
    main loop, the cmd thread, a job's heartbeat thread, the listener callbacks (the
    Firestore SDK's own thread) and the monitor all report here. In memory only - a fresh
    process starts healthy."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self._lock = threading.Lock()
        self.born = clock()
        self.streak = 0
        self.first_fail_at = None
        self.last_fail_at = None
        self.last_ok_at = None
        self.last_err = None

    def note_ok(self):
        now = self.clock()
        with self._lock:
            self.streak, self.first_fail_at, self.last_ok_at = 0, None, now

    def note_fail(self, err):
        """Count `err` if it is connection-class (returns True); anything else is ignored."""
        if not is_conn_error(err):
            return False
        now = self.clock()
        text = f"{type(err).__name__}: {err}" if isinstance(err, BaseException) else str(err)
        with self._lock:
            self.streak += 1
            if self.first_fail_at is None:
                self.first_fail_at = now
            self.last_fail_at = now
            self.last_err = " ".join(text.split())[:240]
        return True

    def down(self):
        """Two or more connection failures in a row and no success since."""
        return self.streak >= 2

    def failing_for(self, now):
        with self._lock:
            if self.streak < 2 or self.first_fail_at is None:
                return 0.0
            return max(0.0, now - self.first_fail_at)

    def last_activity(self):
        return max(t for t in (self.born, self.last_ok_at, self.last_fail_at) if t is not None)


HEALTH = FsHealth()
# Held by FirestoreQueue.run_once from just before a claim write until the claimed job's
# result is saved; the monitor takes it before a self-restart. A process whose slot is held
# never exits on its own.
JOB_SLOT = threading.Lock()


# ── the client handle ─────────────────────────────────────────────────────────────────
def close_client_async(client, log=print):
    """Best-effort close of a client we are replacing, on a daemon thread nobody waits for
    (closing a channel that is itself stuck must not stall anything)."""
    def _close():
        try:
            transport = getattr(client, "_transport", None)
            if transport is not None and callable(getattr(transport, "close", None)):
                transport.close()
        except Exception as e:
            log(f"[fs-health] closing the old connection failed (ignored): {type(e).__name__}: {e}")
        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        except Exception:
            pass
    threading.Thread(target=_close, name="fs-close", daemon=True).start()


class FirestoreHandle:
    """Stands in for the runner's Firestore client (FirestoreQueue.db) and forwards every
    attribute to the CURRENT client, so rebuild() moves every holder at once. `factory`
    builds a replacement (None = this process cannot). The first client - firebase_admin's
    cached one - is never closed (other code may hold it raw); a client this handle built
    itself is closed when it is replaced."""

    def __init__(self, client, factory=None):
        self._client = client
        self._factory = factory
        self._owns = False
        self._lock = threading.Lock()
        self.generation = 0

    @property
    def client(self):
        return self._client

    @property
    def can_rebuild(self):
        return self._factory is not None

    def __getattr__(self, name):
        client = self.__dict__.get("_client")
        if client is None:
            raise AttributeError(name)
        return getattr(client, name)

    def rebuild(self, log=print):
        """(ok, why). Builds the new client FIRST; a factory that fails leaves the old one."""
        if self._factory is None:
            return False, "this process has no way to build a new client"
        try:
            new = self._factory()
        except Exception as e:
            return False, f"building a new client failed ({type(e).__name__}: {e})"
        if new is None:
            return False, "building a new client returned nothing"
        with self._lock:
            old, self._client = self._client, new
            close_old, self._owns = self._owns, True
            self.generation += 1
        if close_old:
            close_client_async(old, log=log)
        return True, None


def _own_channel(client):
    """Give a fresh google-cloud-firestore Client a gRPC channel of its own: the same
    channel the library builds lazily (_firestore_api_helper: keepalive 30 s), plus a LOCAL
    subchannel pool. By default gRPC shares subchannels between channels with the same
    target and arguments, so a new channel could be handed the very connection that is
    stuck. Best-effort: any mismatch with the library's internals leaves the client to build
    its own channel exactly as before."""
    try:
        if getattr(client, "_firestore_api_internal", None) is not None:
            return False
        if getattr(client, "_emulator_host", None) is not None:
            return False
        from google.cloud.firestore_v1.services.firestore import client as fs_client_mod
        from google.cloud.firestore_v1.services.firestore.transports import grpc as fs_grpc
        channel = fs_grpc.FirestoreGrpcTransport.create_channel(
            client._target, credentials=client._credentials,
            options=[("grpc.keepalive_time_ms", 30000), ("grpc.use_local_subchannel_pool", 1)])
        transport = fs_grpc.FirestoreGrpcTransport(host=client._target, channel=channel)
        api = fs_client_mod.FirestoreClient(transport=transport,
                                            client_options=client._client_options)
        client._transport = transport
        client._firestore_api_internal = api
        fs_client_mod._client_info = client._client_info
        return True
    except Exception:
        return False


def new_client():
    """A brand-new Firestore client for the firebase_admin app this process initialised -
    built directly, because firebase_admin.firestore.client() hands back the SAME cached
    (stuck) client every time. No network here; it connects on its first call."""
    import firebase_admin
    from google.cloud import firestore as gcf
    app = firebase_admin.get_app()
    client = gcf.Client(credentials=app.credential.get_credential(), project=app.project_id)
    _own_channel(client)
    return client


# ── small helpers ─────────────────────────────────────────────────────────────────────
def network_reachable(host=NET_HOST, timeout=5.0):
    """A plain TCP connect, outside gRPC. True = the network is fine, so a fresh process
    can be expected to connect where this one's channel cannot."""
    try:
        s = socket.create_connection(host, timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def _bounded(fn, timeout):
    """fn() on a daemon thread; its result, its exception, or TimeoutError after `timeout`."""
    box, done = {}, threading.Event()

    def _run():
        try:
            box["r"] = fn()
        except BaseException as e:   # noqa: BLE001 - handed back to the caller
            box["e"] = e
        finally:
            done.set()
    threading.Thread(target=_run, name="fs-probe", daemon=True).start()
    if not done.wait(timeout):
        raise TimeoutError(f"probe still running after {timeout:g}s")
    if "e" in box:
        raise box["e"]
    return box.get("r")


def parse_relaunch(value):
    """'<first failure epoch>:<count>' -> (first_fail_at, count), or None."""
    try:
        first, count = str(value).split(":", 1)
        return float(first), int(count)
    except Exception:
        return None


def relaunch_plan(is_worker, worker_n, env, first_fail_at, count, launch_dir=LAUNCH_DIR,
                  windows=None):
    """(plan, None) or (None, why). `plan` = {argv, env, grace, how}: the detached launch
    of this runner's replacement - see the module docstring, step 5. `windows` None = this
    machine's own answer (os.name == "nt"); tests pass it so the plan is checked anywhere."""
    if not (os.name == "nt" if windows is None else windows):
        return None, "not Windows - no launcher to relaunch through"
    if is_worker:
        n = str(worker_n or "").strip()
        if not n.isdigit():
            return None, f"worker number {worker_n!r} is unknown"
        vbs = os.path.join(launch_dir, "_run_worker.vbs")
    else:
        vbs = os.path.join(launch_dir, "_restart_runner_hidden.vbs")
    if not os.path.exists(vbs):
        return None, f"{vbs} is missing"
    wscript = shutil.which("wscript") or os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")
    e = dict(env)
    e[RELAUNCH_ENV] = f"{int(first_fail_at)}:{int(count)}"
    if is_worker:
        e.pop("EDGELOG_KEEP", None)
        return {"argv": [wscript, vbs, n], "env": e, "grace": WORKER_GRACE_SEC,
                "how": f"_run_worker.vbs {n}"}, None
    # every worker kept, the primary not: the bat's helper kills only the old primary
    e["EDGELOG_KEEP"] = KEEP_ALL_WORKERS
    return {"argv": [wscript, vbs], "env": e, "grace": PRIMARY_GRACE_SEC,
            "how": "_restart_runner_hidden.vbs, every worker kept"}, None


def spawn(plan):
    """Start the replacement exactly like tools/fleet_restart.py's launch_worker()."""
    subprocess.Popen(plan["argv"], env=plan["env"], close_fds=True)


def hard_exit(code):
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)


@contextlib.contextmanager
def _os_lock(path):
    """Exclusive, NON-blocking OS lock (released by the kernel if the process dies).
    Raises OSError when another process holds it."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            import msvcrt
        except ImportError:
            msvcrt = None
        if msvcrt is not None:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                try:
                    os.lseek(fd, 0, 0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
    finally:
        os.close(fd)


def push_state_path():
    home = os.environ.get("EDGELOG_HOME") or (r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog")
    return os.path.join(home, "state", "runner_reconnect_push.json")


def reconnect_note(minutes):
    from api import ntfy_push
    mins = max(1, int(round(float(minutes or 0))))
    return ntfy_push.plain("Job runner", "reconnected", None,
                           f"Lost its database link for about {mins} min and restarted itself",
                           "nothing")


def push_reconnected(minutes, now=None, state_path=None, log=print, send=None):
    """The one low-priority 'reconnected' note, at most once a day across every runner
    process. True = sent, False = deduped, None = another process is deciding right now."""
    from api import ntfy_push
    now = time.time() if now is None else now
    state_path = state_path or push_state_path()
    try:
        with _os_lock(state_path + ".lock"):
            try:
                with open(state_path, encoding="utf-8") as f:
                    state = json.load(f)
            except Exception:
                state = {}
            action, new_state = ntfy_push.dedupe({PUSH_KEY: ntfy_push.RANK["low"]}, state, now)
            tmp = state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(new_state, f)
            os.replace(tmp, state_path)
    except OSError:
        return None
    if action != "push":
        return False
    (send or ntfy_push.send)(reconnect_note(minutes),
                             log=lambda t: log(f"[fs-health] {t}"))
    return True


def wait_until_reachable(max_wait=SAVE_WAIT_MAX_SEC, poll=15.0, health=None, log=print,
                         sleep=time.sleep, what="the job's result"):
    """Called by run_once before a finished job's save. Returns at once when Firestore is
    not down(); otherwise waits (bounded) for any success to be recorded - the monitor's
    probes and rebuilds keep going meanwhile - and returns True when it came back."""
    h = health or HEALTH
    if not h.down():
        return True
    log(f"[fs-health] {time.strftime('%H:%M:%S')} the database is unreachable - holding "
        f"{what} up to {max_wait / 60:g} min for it to come back")
    waited = 0.0
    while h.down() and waited < max_wait:
        sleep(poll)
        waited += poll
    ok = not h.down()
    log(f"[fs-health] {time.strftime('%H:%M:%S')} "
        + ("reachable again - saving" if ok else
           f"still unreachable after {max_wait / 60:g} min - trying the save anyway"))
    return ok


# ── the monitor ───────────────────────────────────────────────────────────────────────
class Monitor:
    """Drives steps 2-5 and 7 of the module docstring from its own daemon thread
    (run_forever), so it works while the main loop is busy or stuck. step() is the whole
    state machine and takes every outside effect as an argument, so the tests drive it with
    a fake clock, a fake client and fake relaunch/exit."""

    def __init__(self, handle, probe=None, health=None, on_rebuild=None, job_slot=None,
                 extra_busy=None, is_worker=False, worker_n=None, log=print, env=None,
                 launch_dir=LAUNCH_DIR, net_ok=network_reachable, relaunch=spawn,
                 exit_fn=hard_exit, sleep=time.sleep, bounded=_bounded, push=push_reconnected,
                 windows=None):
        self.handle = handle
        self.probe = probe
        self.health = health or HEALTH
        self.on_rebuild = on_rebuild
        self.job_slot = job_slot or JOB_SLOT
        self.extra_busy = extra_busy
        self.is_worker = bool(is_worker)
        self.worker_n = worker_n
        self.log = log
        self.env = os.environ if env is None else env
        self.launch_dir = launch_dir
        self.net_ok = net_ok
        self.relaunch = relaunch
        self.exit_fn = exit_fn
        self.sleep = sleep
        self.bounded = bounded
        self.push = push
        self.windows = windows
        # A runner started by a self-restart: read the marker and drop it, so processes
        # this one starts later (the bat's helper relaunching workers) do not inherit it.
        self.relaunched = parse_relaunch(self.env.pop(RELAUNCH_ENV, None))
        self.pushed = False
        self.phase = "ok"           # "ok" | "rebuilt" (this outage already rebuilt once)
        self.rebuilt_at = None
        self.rebuilds = 0
        self.last_probe_at = 0.0
        self.next_net_check = 0.0
        self._said = set()
        self._probe_done = None

    # -- logging: one line per state change --------------------------------------------
    def _say(self, now, msg, key=None):
        if key is not None:
            if key in self._said:
                return
            self._said.add(key)
        try:
            self.log(f"[fs-health] {time.strftime('%H:%M:%S', time.localtime(now))} {msg}")
        except Exception:
            pass

    def describe(self):
        how = (f"_run_worker.vbs {self.worker_n}" if self.is_worker
               else "_restart_runner_hidden.vbs, workers kept")
        return (f"self-heal: ON - rebuild the database connection after "
                f"{REBUILD_AFTER_SEC / 60:g} min of failed calls, restart this runner "
                f"{EXIT_AFTER_SEC / 60:g} min after that when it holds no job "
                f"(exit {EXIT_CODE}, relaunched via {how})")

    def run_forever(self):
        while True:
            try:
                self.step()
            except Exception as e:
                self._say(self.health.clock(), f"monitor error (continuing): {type(e).__name__}: {e}",
                          key="monitor-error")
            self.sleep(CHECK_SEC)

    # -- the state machine -------------------------------------------------------------
    def step(self, now=None):
        """One pass. Returns what it did: None, 'rebuilt', 'reconnected', 'held',
        'net-down', 'capped', 'no-relaunch', 'relaunch-failed' or 'exit'."""
        h = self.health
        now = h.clock() if now is None else now
        self._maybe_probe(now)
        if self.relaunched and not self.pushed and h.last_ok_at is not None:
            self._push_reconnected()
        if self.phase == "rebuilt":
            if h.last_ok_at is not None and h.last_ok_at >= self.rebuilt_at:
                self._say(now, f"reconnected after rebuilding the connection "
                               f"({self.rebuilds} time(s))")
                self._reset()
                return "reconnected"
            if now - self.rebuilt_at < EXIT_AFTER_SEC:
                return None
            if h.last_fail_at is None or h.last_fail_at < self.rebuilt_at:
                return None
            return self._escalate(now)
        if h.failing_for(now) >= REBUILD_AFTER_SEC:
            self._rebuild(now, first=True)
            return "rebuilt"
        return None

    def _reset(self):
        self.phase, self.rebuilt_at, self.rebuilds = "ok", None, 0
        self._said.clear()

    def _maybe_probe(self, now):
        if self.probe is None:
            return
        h = self.health
        if h.streak > 0:
            due = now - self.last_probe_at >= PROBE_EVERY_SEC
        else:
            due = now - max(h.last_activity(), self.last_probe_at) >= QUIET_PROBE_SEC
        if not due:
            return
        self.last_probe_at = now
        if self._probe_done is not None and not self._probe_done.is_set():
            h.note_fail(TimeoutError("probe still running"))   # never stack a second one
            return
        done = threading.Event()
        self._probe_done = done
        probe = self.probe

        def _run():
            try:
                return probe()
            finally:
                done.set()         # set by the probe's own thread, however late it ends
        try:
            self.bounded(_run, PROBE_TIMEOUT_SEC + 5.0)
            h.note_ok()
        except Exception as e:
            # A connection failure (or our own timeout) counts; any other answer (quota,
            # permission) means the server is reachable, which is all a probe asks.
            if not h.note_fail(e):
                h.note_ok()

    def _rebuild(self, now, first=False):
        h = self.health
        rebuild = getattr(self.handle, "rebuild", None)
        ok, why = rebuild(log=self.log) if callable(rebuild) else (False, "no rebuildable client")
        self.rebuilds += 1
        self.rebuilt_at, self.phase = now, "rebuilt"
        if ok and self.on_rebuild is not None:
            try:
                self.on_rebuild()
            except Exception as e:
                self._say(now, f"re-attaching the listeners failed: {type(e).__name__}: {e}")
        if first:
            mins = h.failing_for(now) / 60.0
            if ok:
                self._say(now, f"database calls failing for {mins:.0f} min ({h.streak} in a "
                               f"row; last: {h.last_err}) - rebuilt the connection")
            else:
                self._say(now, f"database calls failing for {mins:.0f} min ({h.streak} in a "
                               f"row; last: {h.last_err}) - could not rebuild: {why}")

    def _busy(self):
        if self.job_slot.locked():
            return "it holds a job"
        if self.extra_busy is not None:
            try:
                return self.extra_busy()
            except Exception:
                return None
        return None

    def _escalate(self, now):
        h = self.health
        busy = self._busy()
        if busy:
            self._say(now, f"still failing after the rebuild, but {busy} - staying up and "
                           f"rebuilding every {EXIT_AFTER_SEC / 60:g} min", key="held")
            self._rebuild(now)
            return "held"
        never_ok = h.last_ok_at is None
        prior = self.relaunched if never_ok else None
        count = (prior[1] + 1) if prior else 1
        first_fail = prior[0] if prior else (h.first_fail_at or now)
        if prior and prior[1] >= MAX_RESTARTS_PER_OUTAGE:
            self._say(now, f"still failing after {prior[1]} restart(s) in this outage - "
                           f"staying up and rebuilding instead", key="capped")
            self._rebuild(now)
            return "capped"
        if now < self.next_net_check:
            return "net-down"
        if not self.net_ok():
            self.next_net_check = now + PROBE_EVERY_SEC
            self._say(now, "still failing, but the network itself is down - not restarting "
                           "until it is back", key="net-down")
            return "net-down"
        plan, why = relaunch_plan(self.is_worker, self.worker_n, self.env, first_fail, count,
                                  self.launch_dir, windows=self.windows)
        if plan is None:
            self._say(now, f"still failing, and cannot restart itself ({why}) - staying up "
                           "and rebuilding instead", key="no-relaunch")
            self._rebuild(now)
            return "no-relaunch"
        if not self.job_slot.acquire(blocking=False):
            return "held"              # a claim started this very moment
        busy = self._busy_after_slot()
        if busy:
            self.job_slot.release()
            return "held"
        try:
            self.relaunch(plan)
        except Exception as e:
            self.job_slot.release()
            self._say(now, f"starting the replacement failed ({type(e).__name__}: {e}) - "
                           "staying up", key="relaunch-failed")
            self._rebuild(now)
            return "relaunch-failed"
        mins = max(0.0, now - first_fail) / 60.0
        self._say(now, f"database calls failing for {mins:.0f} min, the rebuilt connection "
                       f"too, the network is up and no job is held - restarting this runner "
                       f"(exit {EXIT_CODE}); replacement started via {plan['how']}")
        self.sleep(plan["grace"])
        self.exit_fn(EXIT_CODE)
        return "exit"

    def _busy_after_slot(self):
        if self.extra_busy is None:
            return None
        try:
            return self.extra_busy()
        except Exception:
            return None

    def _push_reconnected(self):
        self.pushed = True
        h = self.health
        try:
            mins = max(0.0, (h.last_ok_at or h.clock()) - self.relaunched[0]) / 60.0
            self.push(mins, log=self.log)
        except Exception as e:
            self._say(h.clock(), f"reconnected note failed: {type(e).__name__}: {e}")
