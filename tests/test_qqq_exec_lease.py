"""api/qqq_exec.py's cross-host lease guard (2026-09-13, "moving the stack to a
cloud VM is fill-in-the-blanks") -- the owner's PC and the future Oracle Cloud VM
must never both serve the QQQ shadow book (and its Webull order mirror) at the same
time. Unlike SERVING_LOCK (a local file, arbitrating between processes on the SAME
machine), the lease is read from the same Firestore doc this adapter already
publishes to every tick (users/{uid}/meta/qqq_exec's "lease" field), so it works
across two different hosts that never share a filesystem.

No real Firestore is used anywhere here -- `db` is always a small fake with just
enough surface (.collection().document().collection().document().get()) to drive
_check_lease.

LEASE PROTOCOL (2026-09-14, the second half of this file). tools/qqq_failover_sim.py
proved the lease was advisory: the runner's fallback thread never checked it (scenario
D), a serving host never re-checked it, every publish blind-wrote it, and once writes
stopped both hosts passed the broker gate (scenario E). The tests below pin the fix: a
compare-and-set claim before the first tick on every path that runs the book, a publish
that can no longer overwrite another host's claim after our own writes lapsed, a loop
that stands down the moment it finds the lease taken, and broker sends that need this
host's own stamp to be fresh.
"""
import copy
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe


class _FakeSnap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, data):
        self._data = data

    def collection(self, name):
        return _FakeColl(self._data)

    def get(self):
        return _FakeSnap(self._data)


class _FakeColl:
    def __init__(self, data):
        self._data = data

    def document(self, name):
        return _FakeDocRef(self._data)


class _FakeDb:
    """Stands in for a real Firestore client -- only the exact chain _check_lease
    calls (.collection("users").document(uid).collection("meta").document("qqq_exec")
    .get()) is wired; `doc` is whatever that .get() should return as to_dict()."""
    def __init__(self, doc=None):
        self.doc = doc

    def collection(self, name):
        return _FakeColl(self.doc)


def _lease_doc(host_id, age_sec=0.0):
    return {"lease": {"host_id": host_id, "leased_at": time.time() - age_sec}}


NOOP = lambda *a, **k: None  # noqa: E731


# ── no Firestore / no uid: always proceeds (nothing to check against) ──────────────

def test_no_db_configured_is_free(monkeypatch):
    ok, reason = qe._check_lease(None, "uid1", log=NOOP)
    assert ok is True


def test_no_uid_configured_is_free(monkeypatch):
    ok, reason = qe._check_lease(_FakeDb({}), "", log=NOOP)
    assert ok is True


# ── missing doc / missing lease field: free ────────────────────────────────────────

def test_missing_doc_is_free():
    ok, reason = qe._check_lease(_FakeDb(None), "uid1", log=NOOP)
    assert ok is True


def test_doc_without_lease_field_is_free():
    ok, reason = qe._check_lease(_FakeDb({"mode": "SHADOW"}), "uid1", log=NOOP)
    assert ok is True


# ── our own host's lease is always free (we own it) ─────────────────────────────────

def test_own_host_lease_is_free(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "this-host")
    ok, reason = qe._check_lease(_FakeDb(_lease_doc("this-host", age_sec=1.0)), "uid1", log=NOOP)
    assert ok is True


# ── a DIFFERENT host's FRESH heartbeat refuses ──────────────────────────────────────

def test_other_hosts_fresh_lease_refuses(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    ok, reason = qe._check_lease(_FakeDb(_lease_doc("owners-pc", age_sec=5.0)), "uid1", log=NOOP)
    assert ok is False
    assert "owners-pc" in reason


# ── a STALE heartbeat frees the slot -- a second instance takes over ───────────────

def test_other_hosts_stale_lease_is_free(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    stale_age = qe.LEASE_STALE_SEC + 30
    ok, reason = qe._check_lease(_FakeDb(_lease_doc("owners-pc", age_sec=stale_age)), "uid1", log=NOOP)
    assert ok is True
    assert "stale" in reason


def test_lease_boundary_just_under_stale_still_refuses(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    ok, reason = qe._check_lease(
        _FakeDb(_lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC - 5)), "uid1", log=NOOP)
    assert ok is False


# ── fail-open on any read problem (never block the legitimate owner on an outage) ──

def test_firestore_read_error_fails_open():
    class _BoomDb:
        def collection(self, name):
            raise RuntimeError("Firestore unreachable")
    ok, reason = qe._check_lease(_BoomDb(), "uid1", log=NOOP)
    assert ok is True
    assert "fail-open" in reason


def test_unreadable_leased_at_fails_open(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    doc = {"lease": {"host_id": "owners-pc", "leased_at": "not-a-number"}}
    ok, reason = qe._check_lease(_FakeDb(doc), "uid1", log=NOOP)
    assert ok is True


def test_missing_leased_at_is_free(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    doc = {"lease": {"host_id": "owners-pc"}}
    ok, reason = qe._check_lease(_FakeDb(doc), "uid1", log=NOOP)
    assert ok is True


# ── host id resolution ──────────────────────────────────────────────────────────────

def test_host_id_override_env_var(monkeypatch):
    monkeypatch.setenv("EDGELOG_HOST_ID", "my-custom-host")
    assert qe._lease_host_id() == "my-custom-host"


def test_host_id_falls_back_to_hostname(monkeypatch):
    monkeypatch.delenv("EDGELOG_HOST_ID", raising=False)
    host = qe._lease_host_id()
    assert host and host != "unknown-host" or host == "unknown-host"  # never raises


# ── serve() end to end: refuses while another host's lease is fresh, takes over once
# it goes stale ──────────────────────────────────────────────────────────────────────

def test_serve_refuses_while_other_host_lease_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "OUT_DIR", str(tmp_path))   # _touch_serving_lock's mkdir target
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    db = _FakeDb(_lease_doc("owners-pc", age_sec=1.0))
    ticked = []
    monkeypatch.setattr(qe, "qqq_exec_thread", lambda *a, **k: ticked.append(1))
    qe.serve(db, ["uid1"], log=NOOP)
    assert ticked == [], "serve() must refuse while the other host's lease is fresh"
    assert not os.path.exists(str(tmp_path / "absent.lock"))


def test_serve_proceeds_once_other_host_lease_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "OUT_DIR", str(tmp_path))   # _touch_serving_lock's mkdir target
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    db = _FakeDb(_lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC + 30))
    ticked = []
    monkeypatch.setattr(qe, "qqq_exec_thread", lambda *a, **k: ticked.append(1))
    qe.serve(db, ["uid1"], log=NOOP)
    assert ticked == [1], "serve() must proceed once the other host's lease has gone stale"


# ══ LEASE PROTOCOL (2026-09-14) ═══════════════════════════════════════════════════════
# See the module docstring. Every test gets a fresh per-process lease holder, so no test
# can inherit another's "held" state.

@pytest.fixture(autouse=True)
def _fresh_lease_holder(monkeypatch):
    monkeypatch.setattr(qe, "_LEASE", qe._LeaseHolder())


class _BoomDb:
    def collection(self, name):
        raise RuntimeError("Firestore unreachable")


class _Store:
    """One users/{uid}/meta/qqq_exec doc with the client surface the protocol uses --
    get(), set(merge=) and NO transaction(), so _lease_txn takes its read-then-write path.
    `fail_writes` makes every set() raise: this host's writes not landing."""

    def __init__(self, doc=None):
        self.doc = copy.deepcopy(doc)
        self.sets = []
        self.fail_writes = False
        self.lock = threading.Lock()

    def collection(self, name):
        return _StoreRef(self)


class _StoreRef:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def get(self, **kwargs):
        with self.store.lock:
            return _FakeSnap(copy.deepcopy(self.store.doc))

    def set(self, data, merge=False, **kwargs):
        with self.store.lock:
            if self.store.fail_writes:
                raise RuntimeError("503 failed to connect to all addresses")
            data = copy.deepcopy(data)
            self.store.doc = dict(self.store.doc or {}, **data) if merge else data
            self.store.sets.append(data)


def _holder(store):
    with store.lock:
        return ((store.doc or {}).get("lease") or {}).get("host_id")


def _wait_for(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def _loop_env(tmp_path, monkeypatch, host):
    """Everything qqq_exec_thread/run_once touch, pointed at tmp_path; tick() stubbed (these
    tests are about who may run the book, not what a tick computes); ntfy captured."""
    out = tmp_path / "qqq_exec"
    for name, path in {"OUT_DIR": out, "CONFIG_PATH": out / "config.json",
                       "STATE_PATH": out / "state.json", "ORDERS_CSV": out / "orders.csv",
                       "TRADES_CSV": out / "trades.csv",
                       "BROKER_ORDERS_CSV": out / "broker_orders.csv",
                       "SERVING_LOCK": out / "SERVING.lock"}.items():
        monkeypatch.setattr(qe, name, str(path))
    env = SimpleNamespace(logs=[], ticks=[], pushes=[])
    env.log = lambda m: env.logs.append(str(m))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: host)
    monkeypatch.setattr(qe, "_reconcile_broker_at_boot", lambda log=print: None)
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print: env.pushes.append((title, msg)))
    monkeypatch.setattr(qe, "TICK_SEC", 0.02)

    def fake_tick(**kw):
        env.ticks.append(time.time())
        # events grows every call -- a STRUCTURAL change api/qqq_exec.py's
        # _publish_fingerprint (2026-09-14, FIX 1) actually notices, unlike
        # updated_at/leased_at (deliberately excluded -- see that function's own
        # docstring): these tests want a publish on every tick to observe the
        # claim/renewal machinery repeatedly, and a bare timestamp no longer forces
        # that once the fingerprint ignores volatile timestamps.
        doc = {"mode": "SHADOW", "updated_at": repr(time.time()), "feed_stale": False,
               "breaker_tripped": False, "positions": {}, "calib": None,
               "today": {"realized_pnl": 0.0, "unrealized_pnl": 0.0},
               "events": [None] * len(env.ticks),
               "lease": {"host_id": host, "leased_at": time.time()}}
        return kw.get("cfg") or {"mode": "SHADOW"}, kw.get("state") or {}, doc

    monkeypatch.setattr(qe, "tick", fake_tick)
    return env


def _start_loop(store, uid, env):
    stop = threading.Event()
    t = threading.Thread(target=qe.qqq_exec_thread, args=(store, [uid]),
                         kwargs={"stop": stop, "log": env.log}, daemon=True)
    t.start()
    return t, stop


# ── claim by compare-and-set ─────────────────────────────────────────────────────────

def test_claim_writes_our_lease_when_free(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    store = _Store({"mode": "SHADOW"})
    ok, reason, stamp = qe._claim_lease(store, "uid1", log=NOOP)
    assert ok is True and stamp
    assert store.doc["lease"] == {"host_id": "cloud-vm", "leased_at": stamp}
    assert store.doc["mode"] == "SHADOW", "the claim merges the lease in; it must not wipe the doc"


def test_claim_refuses_and_writes_nothing_while_another_host_is_fresh(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    store = _Store(_lease_doc("owners-pc", age_sec=5.0))
    ok, reason, stamp = qe._claim_lease(store, "uid1", log=NOOP)
    assert ok is False and stamp is None
    assert "owners-pc" in reason
    assert store.sets == []


def test_claim_takes_over_a_stale_lease(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    store = _Store(_lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC + 30))
    ok, reason, stamp = qe._claim_lease(store, "uid1", log=NOOP)
    assert ok is True and stamp
    assert _holder(store) == "cloud-vm"


def test_claim_fails_open_on_a_firestore_error_and_writes_nothing():
    """Same split as _check_lease: trouble reading never stops the shadow book -- but no
    stamp of ours landed, so broker sends stay blocked (see the send-gate test below)."""
    ok, reason, stamp = qe._claim_lease(_BoomDb(), "uid1", log=NOOP)
    assert ok is True and stamp is None
    assert "fail-open" in reason


def test_a_hung_claim_fails_open_within_its_timeout():
    class _HangRef:
        def collection(self, name):
            return self

        def document(self, name):
            return self

        def get(self, **kwargs):
            time.sleep(3)
            raise RuntimeError("never answers")

    t0 = time.time()
    ok, reason, stamp = qe._claim_lease(_HangRef(), "uid1", log=NOOP, timeout=0.2)
    assert time.time() - t0 < 2.0, "a hung Firestore must not hold the adapter's start"
    assert ok is True and stamp is None and "timed out" in reason


def _txn_db(lease_doc):
    txn = MagicMock(_max_attempts=5, _read_only=False, _id=b"txn-1")
    snap = MagicMock(exists=True)
    snap.to_dict.return_value = lease_doc
    ref = MagicMock()
    ref.get.return_value = snap
    db = MagicMock()
    db.transaction.return_value = txn
    db.collection.return_value.document.return_value.collection.return_value \
        .document.return_value = ref
    return db, txn, ref


def test_on_a_real_client_the_claim_is_one_firestore_transaction(monkeypatch):
    """Drives the REAL google.cloud.firestore.transactional decorator: the read happens
    inside the transaction and the write is buffered into the same commit -- never a plain
    read followed by a separate set()."""
    pytest.importorskip("google.cloud.firestore")
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    db, txn, ref = _txn_db(_lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC + 30))
    ok, reason, stamp = qe._claim_lease(db, "uid1", log=NOOP)
    assert ok is True and stamp
    ref.get.assert_called_once_with(transaction=txn, retry=None, timeout=qe.PUBLISH_TIMEOUT_SEC)
    txn.set.assert_called_once_with(ref, {"lease": {"host_id": "cloud-vm", "leased_at": stamp}},
                                    merge=True)
    txn._commit.assert_called_once()
    ref.set.assert_not_called()


def test_a_failed_transaction_reports_the_firestore_error_not_the_rollback_noise(monkeypatch):
    """firestore 2.27 answers a failed BeginTransaction with its own rollback ValueError
    ("has no transaction ID, so it cannot be rolled back"), which used to replace the real
    503/429 in the log and in the publish_down event."""
    pytest.importorskip("google.cloud.firestore")
    db, txn, ref = _txn_db(None)
    txn._begin.side_effect = RuntimeError("503 failed to connect to all addresses")
    txn._rollback.side_effect = ValueError(
        "The transaction has no transaction ID, so it cannot be rolled back.")
    ok, reason, stamp = qe._claim_lease(db, "uid1", log=NOOP)
    assert ok is True and stamp is None
    assert "503 failed to connect" in reason and "rolled back" not in reason


def test_on_a_real_client_a_refused_claim_buffers_no_write(monkeypatch):
    pytest.importorskip("google.cloud.firestore")
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    db, txn, ref = _txn_db(_lease_doc("owners-pc", age_sec=5.0))
    ok, reason, stamp = qe._claim_lease(db, "uid1", log=NOOP)
    assert ok is False and "owners-pc" in reason
    txn.set.assert_not_called()
    ref.set.assert_not_called()


# ── renew without clobbering ─────────────────────────────────────────────────────────

def test_a_process_that_does_not_manage_the_lease_publishes_exactly_as_before():
    assert qe._LEASE.write_mode("uid1") is None
    assert qe._LEASE.send_gate("uid1") is None


def test_plain_overwrite_only_inside_both_bounds_otherwise_compare_and_set():
    h = qe._LEASE
    now = time.time()
    h.begin("uid1", now)
    assert h.write_mode("uid1") == "blind"
    assert h.write_mode("some-other-uid") is None
    h.committed_at = now - qe.LEASE_HOLD_SEC - 1            # our stamps stopped landing
    assert h.write_mode("uid1") == "cas"
    h.committed_at, h.checked_at = now, now - qe.LEASE_RECHECK_SEC - 1   # periodic re-check due
    assert h.write_mode("uid1") == "cas"
    h.end("stood down")
    assert h.write_mode("uid1") == "skip"


def test_a_late_publish_cannot_overwrite_the_host_that_took_over(monkeypatch):
    """The partition case. Our stamps stopped landing, another host legitimately claimed,
    then our queued publish finally goes out: it must compare-and-set, find the other
    host fresh, write NOTHING and stand this process down."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time() - qe.LEASE_HOLD_SEC - 5)
    store = _Store(_lease_doc("cloud-vm", age_sec=2.0))
    with pytest.raises(qe._LeaseNotHeld):
        qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW"})
    assert store.sets == []
    assert _holder(store) == "cloud-vm"
    assert qe._LEASE.held is False and "cloud-vm" in qe._LEASE.lost_reason


def test_compare_and_set_publish_renews_a_lease_that_is_still_ours(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time() - qe.LEASE_HOLD_SEC - 5)
    store = _Store(_lease_doc("owners-pc", age_sec=qe.LEASE_HOLD_SEC + 5))
    qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW"})
    assert store.doc["mode"] == "SHADOW" and _holder(store) == "owners-pc"
    assert time.time() - store.doc["lease"]["leased_at"] < 5
    assert qe._LEASE.write_mode("uid1") == "blind", "a landed renewal restores plain publishes"


def test_a_check_that_errors_inside_the_hold_bound_still_renews(monkeypatch):
    """Read quota spent, writes fine (it has happened twice): the periodic compare-and-set
    errors. Inside LEASE_HOLD_SEC a plain renewal is as safe as ever -- the phone tab must
    not freeze and the lease must not lapse."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    now = time.time()
    qe._LEASE.begin("uid1", now)
    qe._LEASE.checked_at = now - qe.LEASE_RECHECK_SEC - 1          # a re-check is due
    store = _Store(_lease_doc("owners-pc", age_sec=5.0))
    monkeypatch.setattr(qe, "_cas_publish", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("429 Quota exceeded")))
    qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW", "updated_at": "new"})
    assert store.doc["updated_at"] == "new" and _holder(store) == "owners-pc"
    assert time.time() - store.doc["lease"]["leased_at"] < 5, "the lease was renewed"


def test_a_check_that_errors_past_the_hold_bound_publishes_without_the_lease(monkeypatch):
    """Past the bound a plain overwrite could clobber a legitimate claim, so the status goes
    out WITHOUT the lease field: the tab stays alive, whoever holds the lease keeps it."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time() - qe.LEASE_HOLD_SEC - 5)
    store = _Store(dict(_lease_doc("cloud-vm", age_sec=3.0), updated_at="old"))
    monkeypatch.setattr(qe, "_cas_publish", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("429 Quota exceeded")))
    with pytest.raises(qe._LeaseNotRenewed):
        qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW", "updated_at": "new"})
    assert store.doc["updated_at"] == "new", "the status still went out"
    assert _holder(store) == "cloud-vm", "and the other host's lease was not touched"
    assert qe._LEASE.held is True, "an ERROR is not a refusal -- no stand-down"


def test_a_publish_never_queues_behind_one_still_running(monkeypatch):
    calls, release = [], threading.Event()

    def slow_do_set(db, uid, doc, renew_every_sec=None):
        calls.append(doc)
        release.wait(5)

    pub = qe._Publisher()
    monkeypatch.setattr(pub, "_do_set", slow_do_set)
    monkeypatch.setattr(qe, "PUBLISH_TIMEOUT_SEC", 0.1)
    state = {}
    try:
        pub.write_one(None, "uid1", {"n": 1}, state, log=NOOP)     # times out, still running
        t0 = time.time()
        pub.write_one(None, "uid1", {"n": 2}, state, log=NOOP)
        assert time.time() - t0 < 0.1, "the second write must not wait behind the first"
        assert calls == [{"n": 1}]
        assert state["publish_fail_today"] == 2
    finally:
        release.set()


def test_a_stood_down_process_publishes_nothing():
    qe._LEASE.begin("uid1", time.time())
    qe._LEASE.end("host 'cloud-vm' holds a fresh lease")
    store = _Store(_lease_doc("cloud-vm", age_sec=1.0))
    with pytest.raises(qe._LeaseNotHeld):
        qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW"})
    assert store.sets == []


def test_a_plain_renewal_is_one_attempt_with_a_deadline(monkeypatch):
    """The client's default commit retry re-sends for up to a minute; an overwrite landing
    that late could clobber a legitimate claim, so it goes out once or not at all."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time())
    ref = MagicMock()
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value \
        .document.return_value = ref
    qe._Publisher._do_set(db, "uid1", {"mode": "SHADOW"})
    args, kwargs = ref.set.call_args
    assert "retry" in kwargs and kwargs["retry"] is None
    assert kwargs.get("timeout") == qe.PUBLISH_TIMEOUT_SEC
    assert args[0]["lease"]["host_id"] == "owners-pc"


# ── every path that runs the book: the loop, the runner fallback, --once ────────────

def test_runner_fallback_thread_refuses_while_another_host_holds_the_lease(tmp_path, monkeypatch):
    """Simulation scenario D, pinned: api/runner.py's fallback thread used to tick, publish,
    and from then on read itself as the lease holder."""
    env = _loop_env(tmp_path, monkeypatch, host="cloud-vm")
    store = _Store(_lease_doc("owners-pc", age_sec=5.0))
    before = copy.deepcopy(store.doc)
    qe.qqq_exec_thread(store, ["uid-d"], stop=threading.Event(), log=env.log)
    assert env.ticks == [], "no tick without the lease"
    assert store.sets == [] and store.doc == before, "nothing published, the lease untouched"
    assert any("REFUSING" in m and "owners-pc" in m for m in env.logs)
    assert qe.standby_fresh()[0], "the refusal must keep the runner from starting another copy"
    assert not os.path.exists(qe.SERVING_LOCK), "a refused loop leaves no heartbeat behind"


def test_loop_claims_a_free_lease_then_ticks_and_publishes_as_the_holder(tmp_path, monkeypatch):
    env = _loop_env(tmp_path, monkeypatch, host="cloud-vm")
    store = _Store({"mode": "SHADOW"})
    t, stop = _start_loop(store, "uid-claim", env)
    try:
        assert _wait_for(lambda: len(env.ticks) >= 3 and len(store.sets) >= 3)
        assert set(store.sets[0]) == {"lease"}, "the first write is the compare-and-set claim"
        assert _holder(store) == "cloud-vm"
        assert os.path.exists(qe.SERVING_LOCK), "a serving loop keeps its heartbeat"
    finally:
        stop.set()
        t.join(5)
    assert not t.is_alive()
    assert not os.path.exists(qe.SERVING_LOCK), "and removes it when it exits"


def test_serving_loop_stands_down_when_another_host_takes_the_lease(tmp_path, monkeypatch):
    """The re-check with stand-down. Our writes stop landing long enough that another host
    may legitimately claim; it does. The loop must stop ticking and publishing, say so on
    the phone, record it, and leave the new holder's lease alone."""
    env = _loop_env(tmp_path, monkeypatch, host="owners-pc")
    monkeypatch.setattr(qe, "LEASE_HOLD_SEC", 0.3)
    monkeypatch.setattr(qe, "LEASE_RECHECK_SEC", 60.0)
    store = _Store(None)
    t, stop = _start_loop(store, "uid-standdown", env)
    try:
        assert _wait_for(lambda: len(store.sets) >= 3)
        store.fail_writes = True                   # our stamps stop landing...
        time.sleep(0.6)                            # ...past LEASE_HOLD_SEC
        with store.lock:                           # the other host claims
            store.doc["lease"] = {"host_id": "cloud-vm", "leased_at": time.time()}
        t.join(5)
        assert not t.is_alive(), "the loop must stand down, not keep ticking"
        store.fail_writes = False
        writes, ticks = len(store.sets), len(env.ticks)
        time.sleep(0.3)
        assert len(env.ticks) == ticks, "no tick after standing down"
        assert len(store.sets) == writes, "no publish after standing down"
        assert _holder(store) == "cloud-vm"
        assert any("STANDING DOWN" in m and "cloud-vm" in m for m in env.logs)
        assert env.pushes and "STOOD DOWN" in env.pushes[-1][0]
        assert qe.standby_fresh()[0]
        assert any(e.get("kind") == "lease_lost" for e in qe.load_state().get("events", []))
        assert not os.path.exists(qe.SERVING_LOCK)
    finally:
        stop.set()
        t.join(5)


def test_a_suspended_loop_reclaims_before_its_next_tick(tmp_path, monkeypatch):
    """The PC slept with the adapter process alive (2026-09-10: 21 h) and another host took
    over meanwhile. On wake the loop must re-claim BEFORE ticking again -- nothing in its
    memory says the lease is gone -- and stand down when refused."""
    env = _loop_env(tmp_path, monkeypatch, host="owners-pc")
    monkeypatch.setattr(qe, "LEASE_STALE_SEC", 2.0)   # the VM's stamp must still read fresh
    monkeypatch.setattr(qe, "publish_async", lambda *a, **k: None)   # only the wake-up path can notice
    store = _Store(None)
    awake_tick = qe.tick

    def sleepy_tick(**kw):
        result = awake_tick(**kw)
        if len(env.ticks) == 2:
            time.sleep(2.5)                                            # suspended...
            with store.lock:                                           # ...and the VM took over
                store.doc["lease"] = {"host_id": "cloud-vm", "leased_at": time.time()}
        return result

    monkeypatch.setattr(qe, "tick", sleepy_tick)
    t, stop = _start_loop(store, "uid-wake", env)
    t.join(5)
    stop.set()
    assert not t.is_alive(), "the loop must stand down on wake"
    assert len(env.ticks) == 2, "no tick after waking into someone else's lease"
    assert any("STANDING DOWN" in m and "cloud-vm" in m for m in env.logs)
    assert _holder(store) == "cloud-vm"


def test_once_refuses_while_another_host_holds_the_lease(tmp_path, monkeypatch):
    env = _loop_env(tmp_path, monkeypatch, host="cloud-vm")
    store = _Store(_lease_doc("owners-pc", age_sec=5.0))
    assert qe.run_once(uid="uid1", db=store, log=env.log) is None
    assert env.ticks == [] and store.sets == []
    assert not os.path.exists(qe.SERVING_LOCK)


def test_once_claims_then_publishes_when_the_lease_is_free(tmp_path, monkeypatch):
    env = _loop_env(tmp_path, monkeypatch, host="cloud-vm")
    store = _Store(None)
    doc = qe.run_once(uid="uid1", db=store, log=env.log)
    assert doc is not None and len(env.ticks) == 1
    assert _holder(store) == "cloud-vm" and store.doc.get("mode") == "SHADOW"
    assert not os.path.exists(qe.SERVING_LOCK)


def test_once_whose_claim_failed_open_cannot_overwrite_the_holder(tmp_path, monkeypatch):
    """--once on the VM while the PC serves, and the claim's read happens to fail: the tick
    may run, but its publish is a compare-and-set that refuses -- it must not knock the PC's
    lease out (the PC would then stand down with nobody left serving)."""
    env = _loop_env(tmp_path, monkeypatch, host="cloud-vm")
    store = _Store(_lease_doc("owners-pc", age_sec=3.0))
    real_claim = qe._claim_lease
    monkeypatch.setattr(qe, "_claim_lease",
                        lambda db, uid, log=print: real_claim(_BoomDb(), uid, log=log))
    qe.run_once(uid="uid1", db=store, log=env.log)
    assert store.sets == [] and _holder(store) == "owners-pc"


def test_once_refuses_while_an_adapter_is_serving_on_this_host(tmp_path, monkeypatch):
    """A second copy of the book on one host ticks with its own memory -- and, once the
    broker mirror is armed, places its own orders."""
    import subprocess
    import sys
    env = _loop_env(tmp_path, monkeypatch, host="owners-pc")
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        os.makedirs(os.path.dirname(qe.SERVING_LOCK), exist_ok=True)
        with open(qe.SERVING_LOCK, "w", encoding="utf-8") as fh:
            fh.write(f"{other.pid} 2026-09-14 11:00:00\n")
        assert qe.run_once(uid=None, db=None, log=env.log) is None
        assert env.ticks == []
        assert any("REFUSING --once" in m for m in env.logs)
    finally:
        other.kill()
        other.wait(timeout=10)


# ── broker sends need a fresh stamp of this host's own ──────────────────────────────

def test_broker_gate_counts_our_own_lease_only_while_it_is_fresh(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    ok, _ = qe._check_lease_for_broker(_FakeDb(_lease_doc("owners-pc", age_sec=5.0)), "uid1",
                                       log=NOOP)
    assert ok is True
    ok, reason = qe._check_lease_for_broker(
        _FakeDb(_lease_doc("owners-pc", age_sec=qe.LEASE_HOLD_SEC + 5)), "uid1", log=NOOP)
    assert ok is False and "unverifiable" in reason
    ok, reason = qe._check_lease_for_broker(_FakeDb({"lease": {"host_id": "owners-pc"}}), "uid1",
                                            log=NOOP)
    assert ok is False and "unverifiable" in reason


def test_scenario_e_last_writer_and_other_host_can_no_longer_both_pass(monkeypatch):
    """Simulation scenario E, pinned: writes stopped 120 s ago. The last writer used to read
    'ours' and the other host 'stale', and both passed the broker gate."""
    db = _FakeDb(_lease_doc("owners-pc", age_sec=120.0))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    pc_ok, _ = qe._check_lease_for_broker(db, "uid1", log=NOOP)
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    vm_ok, _ = qe._check_lease_for_broker(db, "uid1", log=NOOP)
    assert not (pc_ok and vm_ok)


def test_stand_down_pushes_once_per_real_loss_not_per_flapping_restart(tmp_path, monkeypatch):
    env = _loop_env(tmp_path, monkeypatch, host="cloud-vm")
    qe._stand_down({}, "uid1", "host 'owners-pc' holds a fresh lease (4s old)", log=env.log)
    assert len(env.pushes) == 1
    # systemd restarts it; flaky reads let the claim fail open; it finds the PC again
    qe._stand_down({}, "uid1", "host 'owners-pc' holds a fresh lease (2s old)", log=env.log)
    assert len(env.pushes) == 1, "a host that was already standing by must not page again"


def test_each_order_rechecks_this_hosts_own_stamp_not_only_the_tick(tmp_path, monkeypatch):
    """tick() said ok when it started; the first order call was slow (or the PC slept), and
    by the next order this host's newest landed stamp is too old -- that order is BLOCKED."""
    out = tmp_path / "out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    sent = []

    class _Armed:
        def effective_mode(self):
            return "PAPER", "armed for test"

        def place_stock_order(self, **kw):
            sent.append(kw)
            return {"ok": True, "sent": True, "mode": "PAPER", "side": kw["side"],
                    "client_order_id": kw["signal_id"]}

    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Armed())
    state = {"legs": {}, "_broker_lease_ok": True, "_broker_lease_reason": None}
    qe._LEASE.begin("uid1", time.time())
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    assert len(sent) == 1
    qe._LEASE.committed_at = time.time() - qe.LEASE_SEND_MAX_AGE_SEC - 5
    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    assert len(sent) == 1, "the second order must not go out"
    import csv as _csv
    with open(qe.BROKER_ORDERS_CSV, encoding="utf-8", newline="") as fh:
        last = list(_csv.DictReader(fh))[-1]
    assert last["leg"] == "NOISE" and last["mode"] == "BLOCKED" and "unverifiable" in last["reason"]


class _PaperAdapter:
    def effective_mode(self):
        return "PAPER", "forced PAPER for test"

    def status(self):
        return {"requested_mode": "PAPER", "effective_mode": "PAPER", "halted": False,
                "last_order": None, "open_legs": []}


def test_tick_blocks_sends_until_a_stamp_of_this_hosts_own_has_landed(tmp_path, monkeypatch):
    """A claim that failed open lets the shadow book tick but must not let it SEND: the doc
    still shows the old holder's stale lease, which on its own reads as ok."""
    import datetime as _dt
    out = tmp_path / "out"
    for name, path in {"OUT_DIR": out, "CONFIG_PATH": out / "config.json",
                       "STATE_PATH": out / "state.json", "ORDERS_CSV": out / "orders.csv",
                       "TRADES_CSV": out / "trades.csv",
                       "BROKER_ORDERS_CSV": out / "broker_orders.csv"}.items():
        monkeypatch.setattr(qe, name, str(path))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _PaperAdapter())
    db = _FakeDb(_lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC + 30))
    cfg = dict(qe.DEFAULT_CONFIG, signal_source="engine", kill_file=str(tmp_path / "KILL"))
    outside_hours = _dt.datetime(2026, 9, 8, 3, 0)

    qe._LEASE.begin("uid1", None)                      # started fail-open: nothing landed yet
    _, state, doc = qe.tick(cfg=cfg, state={"legs": {}}, now=outside_hours, db=db, uid="uid1",
                            log=NOOP)
    assert state["_broker_lease_ok"] is False
    assert "unverifiable" in state["_broker_lease_reason"]
    assert doc["broker"]["lease_ok_to_send"] is False

    qe._LEASE.note_committed(time.time())              # our stamp lands
    _, state, doc = qe.tick(cfg=cfg, state=state, now=outside_hours, db=db, uid="uid1", log=NOOP)
    assert state["_broker_lease_ok"] is True


# ══ LEASE PROTOCOL step 3.1 (2026-09-25) -- ADVERTISED CADENCE ═══════════════════════
# WEBULL_PAPER_TODO.md item 3, "keep the QQQ lease fresh when status publishes are
# throttled". FIX 1 (2026-09-14) backs the OFF-mode publish interval off to
# publish_interval_offhours_sec (600s default) to save the daily write quota -- but every
# publish is also this host's lease renewal, so a healthy off-hours holder's stamp is
# routinely older than the fixed LEASE_STALE_SEC (90s) alone (live 2026-09-14: 89.8s at
# 16:48:31 ET). These tests pin the fix: a holder now advertises how often it renews
# (lease["renew_every_sec"]), and a claimer judges staleness against whichever is larger
# of the fixed floor or 1.5x that cadence -- see api/qqq_exec.py's _lease_stale_bound and
# the LEASE_STALE_MARGIN comment above it.

def test_lease_stale_bound_widens_for_a_slow_advertised_cadence():
    lease = {"host_id": "owners-pc", "leased_at": time.time(), "renew_every_sec": 600.0}
    assert qe._lease_stale_bound(lease) == 900.0                    # 1.5 x 600


def test_lease_stale_bound_never_drops_below_the_fixed_floor():
    """A fast (armed, 20s) cadence must not shrink the bound below LEASE_STALE_SEC --
    1.5 x 20 = 30, well under the 90s floor."""
    lease = {"host_id": "owners-pc", "leased_at": time.time(), "renew_every_sec": 20.0}
    assert qe._lease_stale_bound(lease) == qe.LEASE_STALE_SEC


def test_lease_stale_bound_falls_back_to_the_fixed_floor_without_a_usable_cadence():
    assert qe._lease_stale_bound({"host_id": "owners-pc"}) == qe.LEASE_STALE_SEC
    assert qe._lease_stale_bound(
        {"host_id": "owners-pc", "renew_every_sec": "not-a-number"}) == qe.LEASE_STALE_SEC
    assert qe._lease_stale_bound({"host_id": "owners-pc", "renew_every_sec": 0}) == qe.LEASE_STALE_SEC
    assert qe._lease_stale_bound({"host_id": "owners-pc", "renew_every_sec": -5}) == qe.LEASE_STALE_SEC
    assert qe._lease_stale_bound({}) == qe.LEASE_STALE_SEC


def test_a_healthy_offhours_throttled_holder_is_never_claimable_within_its_cadence(monkeypatch):
    """THE LIVE CASE (2026-09-14, 16:48:31 ET): stamp age 89.8s, already past the fixed 90s
    alone, with the PC perfectly healthy and just quiet on purpose. 150s here is comfortably
    past the OLD fixed bound but nowhere near the 600s off-hours cadence x1.5 = 900s bound."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    doc = {"lease": {"host_id": "owners-pc", "leased_at": time.time() - 150,
                     "renew_every_sec": qe.PUBLISH_INTERVAL_OFFHOURS_SEC}}
    ok, reason = qe._check_lease(_FakeDb(doc), "uid1", log=NOOP)
    assert ok is False, "150s old must still read fresh at a 600s advertised cadence"
    assert "fresh" in reason
    ok, reason = qe._check_lease_for_broker(_FakeDb(doc), "uid1", log=NOOP)
    assert ok is False, ("_check_lease_for_broker's foreign-claim branch must agree, or a VM "
                         "about to arm real sends could double-arm against a healthy PC")


def test_a_genuinely_dead_offhours_holder_still_frees_up_in_bounded_time(monkeypatch):
    """The advertised cadence must not trust a holder FOREVER -- well past even its own
    generous bound, it is still claimable."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    dead_age = 1.5 * qe.PUBLISH_INTERVAL_OFFHOURS_SEC + 100
    doc = {"lease": {"host_id": "owners-pc", "leased_at": time.time() - dead_age,
                     "renew_every_sec": qe.PUBLISH_INTERVAL_OFFHOURS_SEC}}
    ok, reason = qe._check_lease(_FakeDb(doc), "uid1", log=NOOP)
    assert ok is True
    assert "stale" in reason


def test_an_armed_holders_fast_cadence_gets_no_extra_grace():
    """Once armed, publish_interval_armed_sec (20s) applies -- 1.5x that is 30s, under the
    90s floor, so the bound stays exactly LEASE_STALE_SEC: an armed host gets no MORE grace
    than it always had."""
    doc = {"lease": {"host_id": "owners-pc",
                     "leased_at": time.time() - (qe.LEASE_STALE_SEC - 5),
                     "renew_every_sec": qe.PUBLISH_INTERVAL_ARMED_SEC}}
    ok, _ = qe._lease_claimable(doc, "cloud-vm", time.time())
    assert ok is False, "still within the fixed floor -- unaffected by the cadence fix"


def test_a_lease_doc_from_before_this_fix_behaves_exactly_as_before():
    """No renew_every_sec key at all (an older host, or a doc from before this shipped):
    falls back to the fixed LEASE_STALE_SEC alone, never less safe than pre-fix."""
    fresh = _lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC - 5)
    stale = _lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC + 30)
    assert qe._lease_claimable(fresh, "cloud-vm", time.time())[0] is False
    assert qe._lease_claimable(stale, "cloud-vm", time.time())[0] is True


def test_do_set_advertises_the_cadence_it_is_given(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time())
    store = _Store({"mode": "SHADOW"})
    qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW"},
                          renew_every_sec=qe.PUBLISH_INTERVAL_OFFHOURS_SEC)
    assert store.doc["lease"]["renew_every_sec"] == qe.PUBLISH_INTERVAL_OFFHOURS_SEC


def test_do_set_omits_the_cadence_when_the_caller_does_not_know_it(monkeypatch):
    """Every direct _do_set caller elsewhere in this file (all written before this fix) must
    keep publishing the exact pre-fix lease shape -- no renew_every_sec key at all."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time())
    store = _Store({"mode": "SHADOW"})
    qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW"})
    assert "renew_every_sec" not in store.doc["lease"]


def test_do_set_ignores_a_bogus_cadence_and_omits_the_field(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time())
    store = _Store({"mode": "SHADOW"})
    qe._Publisher._do_set(store, "uid1", {"mode": "SHADOW"}, renew_every_sec="garbage")
    assert "renew_every_sec" not in store.doc["lease"]


def test_publish_now_advertises_the_same_interval_should_publish_used(monkeypatch):
    """End to end: publish_now -> _should_publish's own interval selection -> the doc that
    actually lands, with no extra Firestore read needed to know what to advertise."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    monkeypatch.setattr(qe, "_in_market_window", lambda *a, **k: False)   # off-session
    qe._LEASE.begin("uid1", time.time())
    store = _Store({"mode": "SHADOW"})
    doc = {"mode": "SHADOW", "broker": {"effective_mode": "OFF"}}
    qe.publish_now(store, "uid1", doc, {}, force=True, log=NOOP)
    assert store.doc["lease"]["renew_every_sec"] == qe.PUBLISH_INTERVAL_OFFHOURS_SEC
    assert _holder(store) == "owners-pc"


def test_publish_now_advertises_the_armed_cadence_once_armed(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    qe._LEASE.begin("uid1", time.time())
    store = _Store({"mode": "SHADOW"})
    doc = {"mode": "SHADOW", "broker": {"effective_mode": "PAPER"}}
    qe.publish_now(store, "uid1", doc, {}, force=True, log=NOOP)
    assert store.doc["lease"]["renew_every_sec"] == qe.PUBLISH_INTERVAL_ARMED_SEC
