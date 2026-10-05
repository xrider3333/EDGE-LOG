"""api/qqq_exec.py's FIRESTORE WEDGE RECOVERY (2026-10-05).

THE INCIDENT. From the 2026-10-02 close until a manual restart on 10-05 the box's executor
logged, every ~5 minutes: the broker lease read hanging for the client's 300s default retry
("503 failed to connect to all addresses ... FD Shutdown"), every publish timing out after
8s, and a ~280s loop gap whose lease re-claim timed out too. Plain HTTPS to Firestore worked
and a restart fixed it at once: the process's one long-lived gRPC client sat on a dead
channel. Every Webull order was blocked (the lease could not be confirmed) for 2.5 days.

These tests pin the fix with fake clients only (no network, no real Firestore): a client
that WEDGES (every read hangs until the connection is closed, every write fails at once)
and a healthy one over the same doc. They prove the lease read can no longer hold the loop,
the connection is rebuilt in-process after enough connection failures, the lease lands
through the new connection afterwards, broker sends stay blocked the whole time it cannot,
and the owner gets exactly one high push when a rebuild does not help.
"""
import copy
import threading
import time
from types import SimpleNamespace

import pytest

from api import qqq_exec as qe
import os as _os
import sys as _sys
_THREADWAIT_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _THREADWAIT_DIR not in _sys.path:
    _sys.path.insert(0, _THREADWAIT_DIR)
from _threadwait import join_done  # noqa: E402

NOOP = lambda *a, **k: None  # noqa: E731

# Warm the google-api-core import the lease read's retry needs: cold it takes ~0.3s, longer
# than the 0.2s limits below, and a read whose worker is still importing never reaches get().
qe._lease_read_retry(1.0)

WEDGE_ERR = ("RetryError: Timeout of 300.0s exceeded, last exception: 503 failed to connect "
             "to all addresses; last error: UNKNOWN: ipv4:142.251.211.10:443: Failed to "
             "connect to remote host: Timeout occurred: FD Shutdown")


# -- fakes -------------------------------------------------------------------------------
class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Store:
    """The one users/{uid}/meta/qqq_exec doc every fake client reads and writes."""

    def __init__(self, doc=None):
        self.doc = copy.deepcopy(doc)
        self.sets = []
        self.lock = threading.Lock()


class _Client:
    """A Firestore client over `store`. WEDGED: every get() hangs until the client's
    transport is closed (what a rebuild does to the old channel), then raises the 503;
    every set() raises the 503 at once. No transaction(), so the lease code takes its
    read-then-write path."""

    def __init__(self, store, wedged=False):
        self.store = store
        self.wedged = wedged
        self.release = threading.Event()
        self.closed = False
        self.gets = 0
        self._transport = SimpleNamespace(close=self._close)

    def _close(self):
        self.closed = True
        self.release.set()

    def collection(self, name):
        return _Ref(self)


class _Ref:
    def __init__(self, client):
        self.client = client

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def get(self, **kwargs):
        c = self.client
        c.gets += 1
        if c.wedged:
            c.release.wait(10)
            raise RuntimeError(WEDGE_ERR)
        with c.store.lock:
            return _Snap(copy.deepcopy(c.store.doc))

    def set(self, data, merge=False, **kwargs):
        c = self.client
        if c.wedged:
            raise RuntimeError(WEDGE_ERR)
        with c.store.lock:
            data = copy.deepcopy(data)
            c.store.doc = dict(c.store.doc or {}, **data) if merge else data
            c.store.sets.append(data)


def _wait_for(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


@pytest.fixture
def pushes(monkeypatch):
    out = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: out.append((title, msg, priority)))
    return out


@pytest.fixture
def fresh_publisher(monkeypatch):
    pub = qe._Publisher()
    monkeypatch.setattr(qe, "_publisher", pub)
    yield pub
    pub.stop()


@pytest.fixture
def clients():
    """Every fake client a test makes; all released at the end so no thread lingers."""
    made = []
    yield made
    for c in made:
        c.release.set()


# -- what counts as a connection failure ---------------------------------------------------
def test_connection_class_errors_are_recognised():
    assert qe._fs_conn_error(RuntimeError(WEDGE_ERR))
    assert qe._fs_conn_error("timed out after 8s")
    assert qe._fs_conn_error("previous publish still running")
    assert qe._fs_conn_error("lease claim timed out after 15s")
    assert qe._fs_conn_error(qe._FsCallTimeout("lease read timed out after 10s"))
    assert qe._fs_conn_error(RuntimeError("504 Deadline Exceeded"))
    assert qe._fs_conn_error(RuntimeError("ServiceUnavailable: UNAVAILABLE"))
    # the server ANSWERED: a rebuilt connection would not help
    assert not qe._fs_conn_error(RuntimeError("429 Quota exceeded."))
    assert not qe._fs_conn_error(RuntimeError("403 Missing or insufficient permissions."))


def test_errors_where_firestore_answered_neither_count_nor_reset():
    qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR))
    qe._FS_HEALTH.note_fail(RuntimeError("429 Quota exceeded."))
    assert qe._FS_HEALTH.streak == 1
    qe._FS_HEALTH.note_ok(log=NOOP)
    assert qe._FS_HEALTH.streak == 0


# -- part 1: the lease read has a hard wall-clock limit -------------------------------------
def test_broker_lease_read_is_bounded_and_fails_closed(monkeypatch, clients):
    monkeypatch.setattr(qe, "LEASE_READ_TIMEOUT_SEC", 0.2)
    wedged = _Client(_Store(), wedged=True)
    clients.append(wedged)
    t0 = time.time()
    ok, reason = qe._check_lease_for_broker(wedged, "uid1", log=NOOP)
    assert time.time() - t0 < 2.0, "one stuck read must not hold the loop for minutes"
    assert ok is False and "unverifiable" in reason and "timed out after 0.2s" in reason
    # the stuck read is still running: the next check fails closed AT ONCE, no second read
    t0 = time.time()
    ok, reason = qe._check_lease_for_broker(wedged, "uid1", log=NOOP)
    assert time.time() - t0 < 0.15
    assert ok is False and "still running" in reason
    assert wedged.gets == 1
    assert qe._FS_HEALTH.streak == 2


def test_shadow_lease_check_stays_fail_open_on_a_stuck_read(monkeypatch, clients):
    monkeypatch.setattr(qe, "LEASE_READ_TIMEOUT_SEC", 0.2)
    wedged = _Client(_Store(), wedged=True)
    clients.append(wedged)
    ok, reason = qe._check_lease(wedged, "uid1", log=NOOP)
    assert ok is True and "fail-open" in reason


def test_a_healthy_read_resets_the_count(monkeypatch):
    qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR))
    ok, _ = qe._check_lease_for_broker(_Client(_Store()), "uid1", log=NOOP)
    assert ok is True
    assert qe._FS_HEALTH.streak == 0


class _BlipClient(_Client):
    """A healthy client whose first `fails` reads raise `err` -- the routine one-off 503 when
    Google's front end resets a long-lived gRPC connection. Like the real client, get() runs
    its one attempt under the `retry` it is handed (None = exactly one attempt)."""

    def __init__(self, store, fails=1, err=None):
        super().__init__(store)
        self.fails = fails
        self.err = err
        self.retry_seen = []
        self.attempts = 0

    def collection(self, name):
        return _BlipRef(self)


class _BlipRef(_Ref):
    def get(self, retry=None, timeout=None, **kwargs):
        c = self.client
        c.retry_seen.append(retry)

        def attempt():
            c.attempts += 1
            if c.attempts <= c.fails:
                raise c.err
            with c.store.lock:
                return _Snap(copy.deepcopy(c.store.doc))
        return retry(attempt)() if retry is not None else attempt()


def test_one_503_on_the_broker_lease_read_is_retried_not_a_lost_entry(monkeypatch):
    from google.api_core import exceptions as gex
    c = _BlipClient(_Store(), fails=1, err=gex.ServiceUnavailable("connection reset"))
    ok, reason = qe._check_lease_for_broker(c, "uid1", log=NOOP)
    assert ok is True, reason
    assert c.attempts == 2 and c.retry_seen[0] is not None
    assert qe._FS_HEALTH.streak == 0
    # and through the cached verdict the order path reads: no 30s "blocked" window
    c = _BlipClient(_Store(), fails=1, err=gex.ServiceUnavailable("connection reset"))
    state = {}
    ok, reason = qe._lease_verify_cached(c, "uid1", state, {}, log=NOOP)
    assert ok is True and state["_lease_verify_ok"] is True, reason


def test_the_lease_read_retry_ends_at_its_wall_clock_limit(monkeypatch):
    """A connection that stays down: the read fails closed at its limit, and its retry stops
    there too -- it does not keep the one lease-read slot for the default five minutes."""
    from google.api_core import exceptions as gex
    monkeypatch.setattr(qe, "LEASE_READ_TIMEOUT_SEC", 0.5)
    c = _BlipClient(_Store(), fails=10 ** 6, err=gex.ServiceUnavailable("down"))
    t0 = time.time()
    ok, reason = qe._check_lease_for_broker(c, "uid1", log=NOOP)
    assert ok is False and "unverifiable" in reason
    assert time.time() - t0 < 2.0
    assert c.attempts >= 2, "a blip inside the limit is retried"
    assert _wait_for(lambda: qe._lease_read_inflight["future"].done(), timeout=3.0), \
        "the abandoned read must end near its limit, not run on in the background"


def test_errors_where_firestore_answered_are_not_retried():
    from google.api_core import exceptions as gex
    c = _BlipClient(_Store(), fails=1, err=gex.PermissionDenied("no"))
    ok, reason = qe._check_lease_for_broker(c, "uid1", log=NOOP)
    assert ok is False and "PermissionDenied" in reason
    assert c.attempts == 1


# -- the handle ------------------------------------------------------------------------------
def test_handle_forwards_to_the_current_client_and_wraps_only_real_clients():
    store = _Store({"mode": "SHADOW"})
    raw = _Client(store)
    h = qe._as_firestore_handle(raw)
    assert isinstance(h, qe._FirestoreHandle) and h.client is raw
    assert h.can_rebuild is False, "a test double gets no factory"
    assert qe._as_firestore_handle(h) is h
    assert qe._as_firestore_handle(None) is None
    assert getattr(h, "transaction", None) is None, "missing attributes stay missing"
    assert h.collection("users").document("u").get().to_dict() == {"mode": "SHADOW"}


def test_a_failed_factory_keeps_the_old_client(monkeypatch):
    old = _Client(_Store())

    def boom():
        raise RuntimeError("no credentials")
    h = qe._FirestoreHandle(old, factory=boom)
    ok, why = h.rebuild(log=NOOP)
    assert ok is False and "no credentials" in why
    assert h.client is old and h.generation == 0 and not old.closed


# -- part 3: trip, rebuild, back off, alert once ----------------------------------------------
def test_rebuild_after_n_connection_failures_swaps_every_holder(monkeypatch, pushes,
                                                               fresh_publisher, clients):
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 3)
    store = _Store()
    wedged, healthy = _Client(store, wedged=True), _Client(store)
    clients.extend([wedged, healthy])
    h = qe._FirestoreHandle(wedged, factory=lambda: healthy)
    logs, state = [], {"_lease_verify_at": time.time(), "_lease_verify_ok": False}
    # a write and a lease read still stuck on the old connection
    stuck = qe.concurrent.futures.Future()
    fresh_publisher._inflight = stuck
    qe._lease_read_inflight["future"] = stuck
    old_ex = fresh_publisher._ex

    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR))
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append) is None, "not yet"
    qe._FS_HEALTH.note_fail("timed out after 8s")
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append) == "rebuilt"

    assert h.client is healthy and h.generation == 1
    assert _wait_for(lambda: wedged.closed), "the old channel is closed"
    assert fresh_publisher._inflight is None and fresh_publisher._ex is not old_ex
    assert qe._lease_read_inflight["future"] is None
    assert "_lease_verify_at" not in state, "the next tick re-reads the lease, new connection"
    assert any("rebuilt the Firestore connection" in m for m in logs)
    assert pushes == [], "a rebuild that may work is not worth a page"
    assert qe._FS_HEALTH.streak == 0
    # the rebuild never vouches for the lease itself: the local send gate is untouched
    ok, _ = qe._check_lease_for_broker(h, "uid1", log=NOOP)
    assert ok is True, "reads now go through the new client"


def test_time_based_trip(monkeypatch, pushes, clients):
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 100)
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_SEC", 300.0)
    store = _Store()
    healthy = _Client(store)
    h = qe._FirestoreHandle(_Client(store, wedged=True), factory=lambda: healthy)
    clients.append(h.client)
    t = 1_000_000.0
    qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR), now=t)
    qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR), now=t + 200)
    assert qe._maybe_rebuild_firestore(h, None, log=NOOP, now=t + 200) is None
    qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR), now=t + 301)
    assert qe._maybe_rebuild_firestore(h, None, log=NOOP, now=t + 301) == "rebuilt"


def test_still_failing_after_a_rebuild_pushes_once_high_and_backs_off(monkeypatch, pushes,
                                                                     fresh_publisher, clients):
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)
    monkeypatch.setattr(qe, "FS_REBUILD_BACKOFF_SEC", 120.0)
    store = _Store()

    def factory():                      # every rebuild lands on another dead connection
        c = _Client(store, wedged=True)
        clients.append(c)
        return c
    h = qe._FirestoreHandle(factory(), factory=factory)
    logs, state = [], {}
    t = 2_000_000.0

    def fail(n):
        for _ in range(n):
            qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR), now=t)

    fail(2)
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=t) == "rebuilt"
    assert pushes == []
    fail(2)
    # tripped again after a rebuild: say so once; the next rebuild waits for its backoff
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=t + 10) == "alerted"
    assert len(pushes) == 1
    title, msg, priority = pushes[0]
    assert priority == "high" and "FIRESTORE" in title
    assert "still unreachable" in msg and "Webull orders stay blocked" in msg
    assert any(e.get("kind") == "firestore_down" for e in state.get("events", []))
    fail(5)
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=t + 20) is None
    assert len(pushes) == 1, "one push per episode, not one per pass"
    # backoff elapsed: rebuild again, still no second push
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=t + 121) == "rebuilt"
    assert h.generation == 2 and len(pushes) == 1
    # backoff doubles
    fail(2)
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=t + 122 + 200) is None
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=t + 121 + 241) == "rebuilt"
    # one working call is not recovery: the episode (backoff, its one push) stays open
    qe._FS_HEALTH.note_ok(log=logs.append, now=t + 400)
    assert qe._FS_HEALTH.rebuilds == 3 and qe._FS_HEALTH.alerted is True
    assert not any("Firestore reachable again" in m for m in logs)
    # sustained health closes the episode: a later wedge gets its own push
    for i in range(qe.FS_HEALTHY_AFTER_OKS):
        qe._FS_HEALTH.note_ok(log=logs.append, now=t + 500 + i)
    assert any("Firestore reachable again" in m for m in logs)
    assert qe._FS_HEALTH.rebuilds == 0 and qe._FS_HEALTH.alerted is False


def test_a_flapping_connection_keeps_its_backoff_and_pushes_once(monkeypatch, pushes,
                                                                 fresh_publisher, clients):
    """Many 503s with the odd success between them: each lucky call resets the in-a-row
    count, but not the episode -- no fresh rebuild without backoff, no second push."""
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)
    monkeypatch.setattr(qe, "FS_REBUILD_BACKOFF_SEC", 120.0)
    store = _Store()

    def factory():
        c = _Client(store, wedged=True)
        clients.append(c)
        return c
    h = qe._FirestoreHandle(factory(), factory=factory)
    t = 3_000_000.0

    def flap(at):
        qe._FS_HEALTH.note_ok(log=NOOP, now=at)
        for _ in range(2):
            qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR), now=at)

    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR), now=t)
    assert qe._maybe_rebuild_firestore(h, {}, log=NOOP, now=t) == "rebuilt"
    flap(t + 5)
    assert qe._maybe_rebuild_firestore(h, {}, log=NOOP, now=t + 5) == "alerted", \
        "the next run of failures is the same episode: no rebuild before its backoff"
    for k in range(1, 6):
        flap(t + 5 + k)
        assert qe._maybe_rebuild_firestore(h, {}, log=NOOP, now=t + 5 + k) is None
    assert h.generation == 1 and len(pushes) == 1


# -- the runner's shared client is never closed ------------------------------------------------
class _GoogleLookingClient(_Client):
    """A fake whose class module reads like google-cloud-firestore's, so
    _as_firestore_handle treats it as a real client handed in raw (the runner's self.db)."""


_GoogleLookingClient.__module__ = "google.cloud.firestore_v1.client"


def test_a_client_handed_in_raw_is_never_closed_by_a_rebuild(monkeypatch, clients):
    """api/runner.py hands qqq_exec_thread its shared self.db -- also firebase_admin's
    cached firestore.client(), used by the queue listener, job writes and the command
    channel. A rebuild must drop it from this adapter, not close its channel."""
    store = _Store()
    shared = _GoogleLookingClient(store, wedged=True)
    built = []

    def factory():
        c = _Client(store)
        built.append(c)
        clients.append(c)
        return c
    clients.append(shared)
    monkeypatch.setattr(qe, "_new_firestore_client", factory)
    h = qe._as_firestore_handle(shared)
    assert h.can_rebuild is True, "a real client handed in raw can still rebuild"
    ok, _ = h.rebuild(log=NOOP)
    assert ok and h.client is built[0]
    time.sleep(0.2)                     # the close (if any) runs on a daemon thread
    assert shared.closed is False, "the runner's shared client must stay open"
    # a client the handle built itself IS its own: the next rebuild closes it
    ok, _ = h.rebuild(log=NOOP)
    assert ok and h.client is built[1]
    assert _wait_for(lambda: built[0].closed)
    assert shared.closed is False


def test_a_standalone_process_closes_the_client_it_replaces(clients):
    store = _Store()
    old, new = _Client(store, wedged=True), _Client(store)
    clients.extend([old, new])
    h = qe._FirestoreHandle(old, factory=lambda: new, owns_client=True)
    ok, _ = h.rebuild(log=NOOP)
    assert ok and _wait_for(lambda: old.closed)


# -- the publisher's worker swap cannot race a submit -------------------------------------------
def test_a_rebuild_during_a_submit_cannot_put_the_old_write_back(monkeypatch, fresh_publisher):
    """reset_worker (loop thread) landing between write_one's submit and its bookkeeping
    (publisher thread) used to leave the OLD worker's stuck write as the one in flight, so
    every later publish failed as "previous publish still running"."""
    monkeypatch.setattr(qe, "PUBLISH_TIMEOUT_SEC", 0.1)
    pub = fresh_publisher
    stuck = qe.concurrent.futures.Future()     # a write hung on the old connection
    resetter = {}

    class _OldWorker:
        def submit(self, *a, **k):
            # the rebuild arrives right now, from the loop thread
            t = threading.Thread(target=pub.reset_worker, daemon=True)
            t.start()
            time.sleep(0.3)   # let it reach the lock write_one holds (it may or may not; the reset wins either way)
            resetter["t"] = t
            return stuck

    pub._ex = _OldWorker()
    pub.write_one(_Client(_Store()), "uid1", {"mode": "SHADOW"}, {}, log=NOOP)
    assert join_done(resetter["t"])
    assert pub._inflight is None, "the reset wins: the old worker's write is forgotten"
    assert not isinstance(pub._ex, _OldWorker)
    stuck.set_result(None)


def test_a_process_that_cannot_rebuild_alerts_once(monkeypatch, pushes):
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)
    h = qe._as_firestore_handle(_Client(_Store()))
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR))
    assert qe._maybe_rebuild_firestore(h, {}, log=NOOP) == "alerted"
    for _ in range(5):
        qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR))
    assert qe._maybe_rebuild_firestore(h, {}, log=NOOP) is None
    assert len(pushes) == 1 and pushes[0][2] == "high"
    assert "cannot rebuild" in pushes[0][1] and h.generation == 0


# -- end to end: the serving loop wedges, rebuilds, and the lease lands after it ----------------
def _loop_env(tmp_path, monkeypatch, host):
    out = tmp_path / "qqq_exec"
    for name, path in {"OUT_DIR": out, "CONFIG_PATH": out / "config.json",
                       "STATE_PATH": out / "state.json", "ORDERS_CSV": out / "orders.csv",
                       "TRADES_CSV": out / "trades.csv",
                       "BROKER_ORDERS_CSV": out / "broker_orders.csv",
                       "SERVING_LOCK": out / "SERVING.lock"}.items():
        monkeypatch.setattr(qe, name, str(path))
    env = SimpleNamespace(logs=[], verdicts=[])
    env.log = lambda m: env.logs.append(str(m))
    monkeypatch.setattr(qe, "_LEASE", qe._LeaseHolder())
    monkeypatch.setattr(qe, "_lease_host_id", lambda: host)
    monkeypatch.setattr(qe, "_reconcile_broker_at_boot", lambda log=print: None)
    monkeypatch.setattr(qe, "TICK_SEC", 0.02)
    monkeypatch.setattr(qe, "LEASE_READ_TIMEOUT_SEC", 0.1)
    real_claim = qe._claim_lease   # its timeout default is bound at import: pass one
    monkeypatch.setattr(qe, "_claim_lease",
                        lambda db, uid, log=print: real_claim(db, uid, log=log, timeout=0.2))
    monkeypatch.setattr(qe, "PUBLISH_TIMEOUT_SEC", 0.1)

    def fake_tick(**kw):
        # the same two gates tick() puts in front of every real broker send: the lease
        # read (fail closed) and this host's own committed-stamp gate
        db, uid = kw["db"], kw["uid"]
        ok, reason = qe._check_lease_for_broker(db, uid, log=env.log)
        gate = qe._LEASE.send_gate(uid)
        allowed = bool(ok and (gate is None or gate[0]))
        env.verdicts.append((db.generation, allowed))
        doc = {"mode": "SHADOW", "feed_stale": False, "breaker_tripped": False,
               "positions": {}, "today": {}, "events": [None] * len(env.verdicts)}
        return kw.get("cfg") or {"mode": "SHADOW"}, kw.get("state") or {}, doc

    monkeypatch.setattr(qe, "tick", fake_tick)
    return env


def _start_loop(db, uid, env):
    stop = threading.Event()
    t = threading.Thread(target=qe.qqq_exec_thread, args=(db, [uid]),
                         kwargs={"stop": stop, "log": env.log}, daemon=True)
    t.start()
    return t, stop


def test_wedged_loop_rebuilds_then_the_lease_lands_and_sends_unblock(tmp_path, monkeypatch,
                                                                     pushes, fresh_publisher,
                                                                     clients):
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 6)
    env = _loop_env(tmp_path, monkeypatch, host="oracle-box")
    store = _Store({"mode": "SHADOW"})
    wedged, healthy = _Client(store, wedged=True), _Client(store)
    clients.extend([wedged, healthy])
    h = qe._FirestoreHandle(wedged, factory=lambda: healthy)
    t, stop = _start_loop(h, "uid-wedge", env)
    try:
        assert _wait_for(lambda: any(g == 1 and ok for g, ok in env.verdicts), timeout=10), \
            "after the rebuild the lease must land and sends unblock"
    finally:
        stop.set()
    assert join_done(t)
    assert h.generation == 1 and wedged.closed
    before = [ok for g, ok in env.verdicts if g == 0]
    assert before and not any(before), "every send stays blocked while the lease is unverifiable"
    assert any("rebuilt the Firestore connection" in m for m in env.logs)
    assert any("lease claim timed out" in m for m in env.logs), "the boot claim hit the wedge"
    lease = (store.doc or {}).get("lease") or {}
    assert lease.get("host_id") == "oracle-box", "our lease landed through the new client"
    assert store.sets, "every write that landed went through the new client (the old one can't write)"
    assert store.doc.get("mode") == "SHADOW"
    assert pushes == [], "the rebuild worked: nothing to page about"
    assert not any("STANDING DOWN" in m for m in env.logs), "a wedge is not a lost lease"


def test_wedged_loop_that_cannot_recover_keeps_sends_blocked_and_pages_once(tmp_path, monkeypatch,
                                                                           pushes,
                                                                           fresh_publisher,
                                                                           clients):
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 4)
    monkeypatch.setattr(qe, "FS_REBUILD_BACKOFF_SEC", 0.2)
    env = _loop_env(tmp_path, monkeypatch, host="oracle-box")
    store = _Store({"mode": "SHADOW"})

    def factory():
        c = _Client(store, wedged=True)
        clients.append(c)
        return c
    h = qe._FirestoreHandle(factory(), factory=factory)
    t, stop = _start_loop(h, "uid-dead", env)
    try:
        assert _wait_for(lambda: h.generation >= 3 and pushes, timeout=10)
    finally:
        stop.set()
    assert join_done(t)
    assert env.verdicts and not any(ok for _g, ok in env.verdicts), \
        "no send may pass while no connection can confirm the lease"
    assert len(pushes) == 1 and pushes[0][2] == "high"
    assert store.sets == [], "nothing landed, and nothing claims it did"

# -- apply notes (2026-10-05) ------------------------------------------------------------------
def test_an_outage_push_that_did_not_go_out_is_tried_again(monkeypatch):
    """The box may lose the whole network, not just the gRPC channel: a push that fails to
    send must not use up the episode's one page. The log line and the event go out once;
    only the push is retried, spaced FS_ALERT_RETRY_SEC apart."""
    monkeypatch.setattr(qe, "FS_REBUILD_AFTER_FAILS", 2)
    sent = []
    results = [False, True]
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None:
                        (sent.append(msg), results.pop(0))[1])
    h = qe._as_firestore_handle(_Client(_Store()))     # cannot rebuild: alerts at once
    state, logs = {}, []
    for _ in range(2):
        qe._FS_HEALTH.note_fail(RuntimeError(WEDGE_ERR), now=1000.0)
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=1000.0) == "alerted"
    assert len(sent) == 1 and qe._FS_HEALTH.alerted is False
    assert any("did not go out" in ln for ln in logs)
    # too soon: no second try yet
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=1010.0) is None
    assert len(sent) == 1
    # after the spacing: tried again, this time it lands and the episode's page is spent
    later = 1000.0 + qe.FS_ALERT_RETRY_SEC
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=later) == "alerted"
    assert len(sent) == 2 and qe._FS_HEALTH.alerted is True
    assert qe._maybe_rebuild_firestore(h, state, log=logs.append, now=later + 999) is None
    assert len(sent) == 2
    downs = [e for e in state.get("events", []) if e.get("kind") == "firestore_down"]
    assert len(downs) == 1, "one event per episode, however many tries the push took"


def test_notify_reports_whether_the_push_went_out(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert qe._notify("m", "t", log=NOOP) is None
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.setattr(qe.urllib.request, "urlopen", lambda req, timeout=4: object())
    assert qe._notify("m", "t", log=NOOP) is True

    def down(req, timeout=4):
        raise OSError("Network is unreachable")
    monkeypatch.setattr(qe.urllib.request, "urlopen", down)
    assert qe._notify("m", "t", log=NOOP) is False


class _RealishRef:
    """Looks like google-cloud-firestore's DocumentReference (its module name) and raises a
    TypeError from INSIDE get() on the first call -- not a keyword mismatch."""
    calls = []

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def get(self, *args, **kwargs):
        _RealishRef.calls.append(kwargs)
        if len(_RealishRef.calls) == 1:
            raise TypeError("something inside the client")
        return _Snap({"mode": "SHADOW"})


_RealishRef.__module__ = "google.cloud.firestore_v1.document"


def test_a_real_client_never_drops_to_the_unbounded_bare_read():
    _RealishRef.calls = []
    d = qe._get_lease_doc(_RealishRef(), "uid1", 3.0)
    assert d == {"mode": "SHADOW"}
    assert len(_RealishRef.calls) == 2
    second = _RealishRef.calls[1]
    assert second.get("retry", "missing") is None and second.get("timeout") == 3.0, \
        "the fallback read is one attempt, still bounded -- never the 300s default retry"
