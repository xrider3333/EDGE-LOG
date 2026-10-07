"""The job runner's FIRESTORE SELF-HEAL (api/fs_heal.py + its wiring in api/runner.py).

WHY THESE EXIST. On 2026-10-07 every Firestore call in all five runner processes failed for
3 h 20 min ("503 failed to connect to all addresses ... tcp handshaker shutdown / socket is
null") while a fresh python on the same PC connected at once; nothing relaunched a runner
that exited, so only a person restarting the fleet fixed it. These pin the cure:

  * fails, then the REBUILT client works        -> one rebuild, "reconnected", no restart
  * fails forever while IDLE                    -> rebuild, then relaunch + exit 75
  * fails forever while a JOB RUNS              -> never exits; rebuilds every 10 min
  * the network itself down / no launcher / the per-outage cap -> stays up
  * the "Job runner: reconnected" phone note    -> at most once a day across processes
  * run_once holds the job slot from the claim to the save; a job's control reads are
    skipped while Firestore is down; a rebuilt client reaches a running job's refs.

Every test uses fakes: no live Firestore, no real relaunch, no real exit, no push.
"""
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import fs_heal as F
from _threadwait import WAIT_SECONDS, wait_for  # noqa: E402

WEDGE = ("RetryError: Timeout of 300.0s exceeded, last exception: 503 failed to connect to "
         "all addresses; last error: UNKNOWN: ipv4:192.178.164.95:443: tcp handshaker shutdown")
SOCKET_NULL = ("ServiceUnavailable: 503 failed to connect to all addresses; last error: "
               "UNKNOWN: ipv4:172.217.75.95:443: socket is null")
T0 = 1_791_400_000.0


class _Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class _FakeClient:
    """Fails every probe while its generation is in `broken` (a set the test can change)."""

    def __init__(self, gen, broken):
        self.gen, self._broken, self.closed, self.probes = gen, broken, False, 0

    def probe_read(self):
        self.probes += 1
        if self.gen in self._broken:
            raise RuntimeError(WEDGE)
        return {"exists": False}

    def close(self):
        self.closed = True


class _Rig:
    """A Monitor wired to fakes. Generation 0 is the client the process booted with."""

    def __init__(self, tmp_path, broken=("all",), is_worker=True, env=None, net=True,
                 extra_busy=None, launchers=True, relaunch_raises=False):
        self.clock = _Clock()
        self.health = F.FsHealth(clock=self.clock)
        self.broken = set(broken)
        self.clients = []
        self.handle = F.FirestoreHandle(self._make(), factory=self._make)
        self.slot = threading.Lock()
        self.logs, self.relaunches, self.exits, self.sleeps, self.pushes = [], [], [], [], []
        self.rebuild_hooks = 0
        self.net = net
        self.launch_dir = tmp_path / "EdgeLog"
        self.launch_dir.mkdir()
        if launchers:
            (self.launch_dir / "_run_worker.vbs").write_text("' fake", encoding="utf-8")
            (self.launch_dir / "_restart_runner_hidden.vbs").write_text("' fake", encoding="utf-8")
        self.env = dict(env or {"PATH": os.environ.get("PATH", "")})
        self.relaunch_raises = relaunch_raises
        self.mon = F.Monitor(
            self.handle, probe=lambda: self.handle.probe_read(), health=self.health,
            on_rebuild=self._hook, job_slot=self.slot, extra_busy=extra_busy,
            is_worker=is_worker, worker_n="3", log=self.logs.append, env=self.env,
            launch_dir=str(self.launch_dir), net_ok=lambda: self.net, relaunch=self._relaunch,
            exit_fn=self.exits.append, sleep=self.sleeps.append, bounded=lambda fn, t: fn(),
            push=lambda mins, log=None: self.pushes.append(mins), windows=True)

    def _make(self):
        gen = len(self.clients)
        broken = self.broken if "all" not in self.broken else _AllBroken()
        c = _FakeClient(gen, broken)
        self.clients.append(c)
        return c

    def _hook(self):
        self.rebuild_hooks += 1

    def _relaunch(self, plan):
        if self.relaunch_raises:
            raise OSError("wscript is missing")
        self.relaunches.append(plan)

    def fail_once(self, text=WEDGE):
        """What the main loop does on '[queue] skipped: <503 ...>'."""
        assert self.health.note_fail(RuntimeError(text))

    def run(self, minutes, every=F.CHECK_SEC, stop_on=None):
        out = []
        for _ in range(int(round(minutes * 60 / every))):
            self.clock.t += every
            r = self.mon.step()
            out.append(r)
            if stop_on is not None and r == stop_on:
                break
        return out

    def said(self, text):
        return [m for m in self.logs if text in m]


class _AllBroken:
    def __contains__(self, _gen):
        return True


# ── classification ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    WEDGE, SOCKET_NULL,
    "RetryError: Timeout of 60.0s exceeded, last exception: 503 failed to connect to all addresses",
    "DeadlineExceeded: 504 Deadline Exceeded",
    "ServiceUnavailable: 503 DNS resolution failed for firestore.googleapis.com:443",
])
def test_the_10_07_failures_count_as_connection_errors(text):
    assert F.is_conn_error(RuntimeError(text))


@pytest.mark.parametrize("text", [
    "ResourceExhausted: 429 Quota exceeded.",
    "RetryError: Timeout of 300.0s exceeded, last exception: 429 Quota exceeded.",
    "PermissionDenied: 403 Missing or insufficient permissions.",
    "FailedPrecondition: 400 the stored version does not match the required base version",
    "ValueError: something else entirely",
])
def test_answers_from_the_server_are_not_connection_errors(text):
    # a rebuild or a restart cannot fix a quota, a permission or a lost claim race
    assert not F.is_conn_error(RuntimeError(text))


def test_one_success_resets_the_count():
    h = F.FsHealth(clock=_Clock())
    h.note_fail(RuntimeError(WEDGE))
    h.note_fail(RuntimeError(WEDGE))
    assert h.down() and h.streak == 2
    h.note_ok()
    assert not h.down() and h.streak == 0 and h.first_fail_at is None
    assert not h.note_fail(RuntimeError("ResourceExhausted: 429 Quota exceeded"))
    assert h.streak == 0


# ── the client handle ─────────────────────────────────────────────────────────────────
def test_handle_forwards_and_rebuild_swaps_every_holder():
    built = []

    class _C:
        def __init__(self, n):
            self.n, self.closed = n, threading.Event()

        def collection(self, name):
            return (self.n, name)

        def close(self):
            self.closed.set()

    first = _C(0)

    def factory():
        built.append(_C(len(built) + 1))
        return built[-1]

    h = F.FirestoreHandle(first, factory=factory)
    holder = h                                    # e.g. the cmd thread's self.db
    assert holder.collection("users") == (0, "users") and h.generation == 0
    assert h.rebuild(log=lambda *_: None) == (True, None)
    assert holder.collection("users") == (1, "users") and h.generation == 1
    # the boot client is firebase_admin's cached one - other code may hold it raw
    time.sleep(0.05)
    assert not first.closed.is_set()
    assert h.rebuild(log=lambda *_: None) == (True, None)
    # a client this handle built itself IS closed once replaced
    assert built[0].closed.wait(WAIT_SECONDS)
    assert holder.collection("x") == (2, "x")


def test_a_failing_factory_keeps_the_old_client():
    c = object()

    def boom():
        raise RuntimeError("no app")
    h = F.FirestoreHandle(c, factory=boom)
    ok, why = h.rebuild(log=lambda *_: None)
    assert not ok and "no app" in why and h.client is c and h.generation == 0
    assert F.FirestoreHandle(c).rebuild()[0] is False      # no factory at all


def test_rebuilt_client_gets_a_channel_of_its_own():
    gcf = pytest.importorskip("google.cloud.firestore",
                              reason="google-cloud-firestore is not part of the CI dev deps")
    creds = pytest.importorskip("google.auth.credentials")
    client = gcf.Client(credentials=creds.AnonymousCredentials(), project="fs-heal-test")
    assert F._own_channel(client) is True               # built offline, connects lazily
    assert client._firestore_api is client._firestore_api_internal
    assert F._own_channel(client) is False              # never twice
    client._transport.close()


# ── the monitor: the three cases the brief names ──────────────────────────────────────
def test_fails_then_the_rebuilt_client_works(tmp_path):
    rig = _Rig(tmp_path, broken={0})                    # only the boot client is stuck
    rig.fail_once()                                     # "[queue] skipped: RetryError ... 503"
    out = rig.run(9.5)
    assert "rebuilt" not in out, "no rebuild before REBUILD_AFTER_SEC of failures"
    assert rig.health.streak >= 2, "the monitor probes every minute while calls fail"
    out = rig.run(1.0, stop_on="rebuilt")
    assert out[-1] == "rebuilt" and rig.handle.generation == 1 and rig.rebuild_hooks == 1
    assert len(rig.said("rebuilt the connection")) == 1
    out = rig.run(2.0, stop_on="reconnected")
    assert out[-1] == "reconnected"
    assert len(rig.said("reconnected after rebuilding")) == 1
    assert rig.relaunches == [] and rig.exits == []
    assert not rig.clients[0].closed, "the boot client is dropped, never closed"
    assert rig.pushes == [], "only a self-RESTARTED runner sends the phone note"
    # a healthy runner spends nothing on probes
    probes = sum(c.probes for c in rig.clients)
    rig.health.note_ok()
    rig.run(5.0)
    assert sum(c.probes for c in rig.clients) == probes


def test_fails_forever_while_idle_relaunches_and_exits(tmp_path):
    rig = _Rig(tmp_path, is_worker=True)
    rig.fail_once()
    first_fail = rig.health.first_fail_at
    out = rig.run(25, stop_on="exit")
    assert out[-1] == "exit"
    elapsed = rig.clock.t - first_fail
    assert F.REBUILD_AFTER_SEC + F.EXIT_AFTER_SEC <= elapsed <= F.REBUILD_AFTER_SEC + F.EXIT_AFTER_SEC + 60
    assert rig.exits == [F.EXIT_CODE] == [75]
    (plan,) = rig.relaunches
    assert plan["argv"][-2:] == [str(rig.launch_dir / "_run_worker.vbs"), "3"]
    assert plan["argv"][0].lower().endswith("wscript.exe") or plan["argv"][0].lower().endswith("wscript")
    assert plan["env"][F.RELAUNCH_ENV] == f"{int(first_fail)}:1"
    assert "EDGELOG_KEEP" not in plan["env"]
    # the old worker outlives its replacement's launch, so a worker 3 always exists
    assert rig.sleeps == [F.WORKER_GRACE_SEC]
    assert rig.slot.locked(), "the monitor holds the job slot so nothing is claimed meanwhile"
    assert len(rig.said("restarting this runner (exit 75)")) == 1


def test_primary_restart_goes_through_the_keep_every_worker_path(tmp_path):
    rig = _Rig(tmp_path, is_worker=False)
    rig.fail_once()
    assert rig.run(25, stop_on="exit")[-1] == "exit"
    (plan,) = rig.relaunches
    assert plan["argv"][-1] == str(rig.launch_dir / "_restart_runner_hidden.vbs")
    keep = plan["env"]["EDGELOG_KEEP"].split(",")
    assert {"2", "3", "4", "5"} <= set(keep) and "primary" not in keep
    assert rig.sleeps == [F.PRIMARY_GRACE_SEC]
    # fleet_restart's own parser accepts it (a bad token would make the bat FULL-kill)
    from tools import fleet_restart as FR
    assert {"2", "3", "4", "5"} <= FR.parse_keep(plan["env"]["EDGELOG_KEEP"])


def test_fails_forever_while_a_job_runs_never_exits(tmp_path):
    rig = _Rig(tmp_path)
    rig.slot.acquire()                                  # run_once holds it: a job is running
    rig.fail_once()
    out = rig.run(65)
    assert rig.exits == [] and rig.relaunches == []
    assert "exit" not in out
    # it keeps trying a new connection every EXIT_AFTER_SEC instead
    assert rig.handle.generation >= 5
    assert len(rig.said("it holds a job")) == 1, "one log line, not one per rebuild"
    # the job ends (still failing): the next escalation restarts it
    rig.slot.release()
    out = rig.run(F.EXIT_AFTER_SEC / 60 + 1, stop_on="exit")
    assert out[-1] == "exit" and rig.exits == [75]


def test_a_master_refresh_counts_as_busy(tmp_path):
    rig = _Rig(tmp_path, is_worker=False, extra_busy=lambda: "a master refresh is running")
    rig.fail_once()
    rig.run(40)
    assert rig.exits == [] and len(rig.said("a master refresh is running")) == 1


def test_network_down_waits_instead_of_looping_restarts(tmp_path):
    rig = _Rig(tmp_path, net=False)
    rig.fail_once()
    rig.run(40)
    assert rig.exits == [] and len(rig.said("the network itself is down")) == 1
    rig.net = True
    assert rig.run(2, stop_on="exit")[-1] == "exit"


def test_no_launcher_means_it_stays_up(tmp_path):
    rig = _Rig(tmp_path, launchers=False)
    rig.fail_once()
    out = rig.run(45)
    assert rig.exits == [] and "no-relaunch" in out
    assert len(rig.said("cannot restart itself")) == 1
    assert not rig.slot.locked()


def test_a_failed_spawn_releases_the_slot_and_stays_up(tmp_path):
    rig = _Rig(tmp_path, relaunch_raises=True)
    rig.fail_once()
    out = rig.run(30)
    assert rig.exits == [] and "relaunch-failed" in out and not rig.slot.locked()


def test_restarts_per_outage_are_capped(tmp_path):
    marker = f"{int(T0 - 3600)}:{F.MAX_RESTARTS_PER_OUTAGE}"
    rig = _Rig(tmp_path, env={F.RELAUNCH_ENV: marker})
    assert F.RELAUNCH_ENV not in rig.env, "the marker is read once and dropped"
    rig.fail_once()
    out = rig.run(45)
    assert rig.exits == [] and "capped" in out
    # one restart earlier in the outage: the next one carries the count on
    other = tmp_path / "second"
    other.mkdir()
    rig2 = _Rig(other, env={F.RELAUNCH_ENV: f"{int(T0 - 1800)}:1"})
    rig2.fail_once()
    assert rig2.run(25, stop_on="exit")[-1] == "exit"
    assert rig2.relaunches[0]["env"][F.RELAUNCH_ENV] == f"{int(T0 - 1800)}:2"


def test_interleaved_successes_never_trigger_anything(tmp_path):
    rig = _Rig(tmp_path, broken=set())                  # probes always work
    for _ in range(30):
        rig.fail_once()
        rig.run(1)
    assert rig.handle.generation == 0 and rig.exits == []


def test_a_quiet_process_probes_once(tmp_path):
    rig = _Rig(tmp_path, broken=set())
    rig.run(F.QUIET_PROBE_SEC / 60 - 1)
    assert sum(c.probes for c in rig.clients) == 0
    rig.run(2)
    assert sum(c.probes for c in rig.clients) == 1


def test_a_stuck_probe_is_never_stacked(tmp_path):
    rig = _Rig(tmp_path)
    gate = threading.Event()
    calls = []

    def bounded(fn, timeout):
        calls.append(1)
        threading.Thread(target=fn, daemon=True).start()
        raise TimeoutError("probe still running after 25s")
    rig.mon.bounded = bounded
    rig.mon.probe = gate.wait                           # never returns until the gate opens
    rig.fail_once()
    rig.run(5)
    assert len(calls) == 1, "one probe out at a time"
    assert rig.health.streak > 3, "a probe still out counts as a failure each minute"
    gate.set()
    assert wait_for(lambda: rig.mon._probe_done.is_set()), "the stuck probe ends once released"
    rig.run(1.5)
    assert len(calls) >= 2, "probing resumes once the stuck probe has ended"


# ── the phone note ────────────────────────────────────────────────────────────────────
def test_a_self_restarted_runner_sends_the_note_on_its_first_success(tmp_path):
    rig = _Rig(tmp_path, broken=set(), env={F.RELAUNCH_ENV: f"{int(T0 - 25 * 60)}:1"})
    rig.health.note_ok()
    rig.run(1)
    rig.run(10)
    assert len(rig.pushes) == 1 and 24 <= rig.pushes[0] <= 27


def test_reconnected_note_is_plain_and_at_most_once_a_day(tmp_path):
    from api import ntfy_push
    note = F.reconnect_note(25)
    assert ntfy_push.lint(note) == []
    assert note["title"] == "Job runner: reconnected" and note["priority"] == "low"
    assert note["message"].splitlines()[0] == "Trading: not affected."
    assert note["message"].splitlines()[2] == "Do: nothing."
    state = str(tmp_path / "state" / "runner_reconnect_push.json")
    sent = []
    send = lambda n, log=None: sent.append(n)               # noqa: E731
    assert F.push_reconnected(25, now=T0, state_path=state, send=send) is True
    # four more processes reconnect the same morning: no more notes
    for k in range(4):
        assert F.push_reconnected(20, now=T0 + 60 * (k + 1), state_path=state, send=send) is False
    assert len(sent) == 1
    assert F.push_reconnected(30, now=T0 + 86400 + 1, state_path=state, send=send) is True
    assert len(sent) == 2
    assert json.load(open(state, encoding="utf-8"))["set"] == {F.PUSH_KEY: 0}


def test_wait_until_reachable(tmp_path):
    h = F.FsHealth(clock=_Clock())
    slept = []
    assert F.wait_until_reachable(health=h, sleep=slept.append, log=lambda *_: None) is True
    assert slept == []
    h.note_fail(RuntimeError(WEDGE))
    h.note_fail(RuntimeError(WEDGE))

    def sleep_then_recover(s):
        slept.append(s)
        if len(slept) == 3:
            h.note_ok()
    logs = []
    assert F.wait_until_reachable(health=h, sleep=sleep_then_recover, log=logs.append) is True
    assert len(slept) == 3 and len(logs) == 2
    h.note_fail(RuntimeError(WEDGE))
    h.note_fail(RuntimeError(WEDGE))
    slept.clear()
    assert F.wait_until_reachable(max_wait=60, poll=15, health=h, sleep=slept.append,
                                  log=lambda *_: None) is False
    assert sum(slept) == 60


# ── the runner wiring ─────────────────────────────────────────────────────────────────
def _runner():
    pytest.importorskip("google.cloud.firestore_v1.base_query",
                        reason="google-cloud-firestore is not part of the CI dev deps")
    pytest.importorskip("firebase_admin", reason="firebase-admin is not part of the CI dev deps")
    from api import runner as R
    return R


class _Ref:
    def __init__(self, path="users/uid1/backtests/job1", fail_claim=False):
        self.path, self.updates, self.gets, self.fail_claim = path, [], 0, fail_claim

    def update(self, patch, option=None):
        if option is not None and self.fail_claim:
            raise RuntimeError("FailedPrecondition: 400 the stored version does not match")
        self.updates.append(dict(patch))

    def get(self):
        self.gets += 1

        class _S:
            def to_dict(self_inner):
                return {"status": "running"}
        return _S()


class _Snap:
    def __init__(self, ref, doc):
        self.reference, self._doc, self.id = ref, doc, "job1"
        self.create_time = self.update_time = None

    def to_dict(self):
        return dict(self._doc)


class _Query:
    def __init__(self, snaps):
        self._snaps = snaps

    def where(self, filter=None):
        return self

    def limit(self, _n):
        return self

    def stream(self):
        return iter(self._snaps)

    def order_by(self, *a, **k):
        return self


class _Db:
    def __init__(self, snaps):
        self._q = _Query(snaps)

    def collection(self, _name):
        return self

    def document(self, _uid):
        return self

    def where(self, filter=None):
        return self._q

    def write_option(self, **_k):
        return object()


def _queue(R, snaps):
    q = R.FirestoreQueue.__new__(R.FirestoreQueue)
    q.col, q.allow = "backtests", {"uid1"}
    q.db = _Db(snaps)
    return q


def test_run_once_holds_the_job_slot_from_claim_to_save(monkeypatch):
    R = _runner()
    monkeypatch.setattr(R, "_psutil", None)            # no free-RAM guard in a test
    ref = _Ref()
    q = _queue(R, [_Snap(ref, {"status": "queued", "type": "backtest"})])
    seen = {}

    def fake_job(job, cb=None):
        seen["slot_held"] = F.JOB_SLOT.locked()
        return {"status": "error", "error": "fake", "finishedAt": 1.0}
    monkeypatch.setattr(R, "process_job", fake_job)
    saves = []
    monkeypatch.setattr(q, "_save_job_doc",
                        lambda r, patch, log=print: saves.append((F.JOB_SLOT.locked(), patch)))
    assert q.run_once(log=lambda *_: None) == 1
    assert seen["slot_held"] is True and saves and saves[0][0] is True
    assert not F.JOB_SLOT.locked(), "released once the job is saved"
    assert F.HEALTH.last_ok_at is not None, "a working queue poll counts as a success"


def test_a_lost_claim_releases_the_slot(monkeypatch):
    R = _runner()
    monkeypatch.setattr(R, "_psutil", None)
    q = _queue(R, [_Snap(_Ref(fail_claim=True), {"status": "queued"})])
    monkeypatch.setattr(R, "process_job", lambda *a, **k: pytest.fail("must not run"))
    assert q.run_once(log=lambda *_: None) == 0
    assert not F.JOB_SLOT.locked()
    assert F.HEALTH.streak == 0, "a lost precondition is not a connection failure"


def test_control_reads_are_skipped_while_firestore_is_down(monkeypatch):
    R = _runner()
    monkeypatch.setattr(R, "_psutil", None)
    ref = _Ref()
    q = _queue(R, [_Snap(ref, {"status": "queued", "type": "backtest"})])
    gets = {}

    def fake_job(job, cb=None):
        F.HEALTH.note_fail(RuntimeError(WEDGE))
        F.HEALTH.note_fail(RuntimeError(WEDGE))
        cb(1, 10)                                       # outage: no read, no write
        gets["down"] = ref.gets
        F.HEALTH.note_ok()
        monkeypatch.setattr(R, "CTRL_CHECK_SEC", -1.0)
        cb(2, 10)                                       # back: the STOP/PAUSE check resumes
        gets["up"] = ref.gets
        return {"status": "error", "error": "fake", "finishedAt": 1.0}
    monkeypatch.setattr(R, "process_job", fake_job)
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    q.run_once(log=lambda *_: None)
    assert gets == {"down": 0, "up": 1}


def test_a_running_job_reaches_the_rebuilt_client(monkeypatch):
    R = _runner()
    made = []

    class _C:
        def __init__(self, n):
            self.n = n

        def document(self, path):
            made.append((self.n, path))
            return ("ref-on-client", self.n, path)
    q = R.FirestoreQueue.__new__(R.FirestoreQueue)
    q.db = F.FirestoreHandle(_C(0), factory=lambda: _C(1))
    ref = _Ref("users/uid1/backtests/abc")
    assert q._live_ref(ref) is ref, "unchanged until a rebuild"
    q.db.rebuild(log=lambda *_: None)
    assert q._live_ref(ref) == ("ref-on-client", 1, "users/uid1/backtests/abc")
    plain = R.FirestoreQueue.__new__(R.FirestoreQueue)
    plain.db = object()                                 # a test double: never touched
    assert plain._live_ref(ref) is ref


def test_command_thread_poll_failures_are_counted():
    R = _runner()

    class _BadDb:
        def collection(self, _n):
            return self

        def document(self, _u):
            return self

        def where(self, filter=None):
            return self

        def limit(self, _n):
            return self

        def stream(self):
            raise RuntimeError(SOCKET_NULL)
    ct = R.CommandThread(db=_BadDb(), allow_uids=("u1",), root=".", log=lambda *_: None)
    ct.poll_once()
    ct.poll_once()
    assert F.HEALTH.streak == 2 and F.HEALTH.down()


def test_reattach_only_when_listeners_were_up():
    R = _runner()

    class _Watch:
        def __init__(self):
            self.gone = threading.Event()

        def unsubscribe(self):
            self.gone.set()

    class _Owner:
        def __init__(self, watches):
            self._watches, self.calls = list(watches), []

        def start_listeners(self, log=print, ready_timeout=15.0):
            self.calls.append(ready_timeout)
            self._watches.append("new")
            return False

    w = _Watch()
    up = _Owner([w])
    assert R._reattach_watches(up, log=lambda *_: None) is True
    assert w.gone.wait(WAIT_SECONDS) and up.calls == [0.0] and up._watches == ["new"]
    polling = _Owner([])
    assert R._reattach_watches(polling, log=lambda *_: None) is False
    assert polling.calls == []


def test_start_fs_heal_wires_the_queue(monkeypatch):
    R = _runner()
    calls = []

    class _Q:
        db = F.FirestoreHandle(object())

        def probe(self):
            calls.append("probe")

        def reattach_listeners(self, log=print):
            calls.append("q-reattach")

    class _Ct:
        def reattach_listeners(self, log=print):
            calls.append("ct-reattach")
    busy = threading.Event()
    logs = []
    mon = R._start_fs_heal(_Q(), _Ct(), busy, log=logs.append, start=False)
    assert isinstance(mon, F.Monitor) and logs and logs[0].startswith("self-heal: ON")
    mon.probe()
    mon.on_rebuild()
    assert calls == ["probe", "q-reattach", "ct-reattach"]
    assert mon.extra_busy() is None
    busy.set()
    assert mon.extra_busy() == "a master refresh is running"
