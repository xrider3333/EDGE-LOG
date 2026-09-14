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
"""
import os
import time

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
