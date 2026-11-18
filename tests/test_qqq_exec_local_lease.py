import os

from api import qqq_exec as qe


def _host(monkeypatch, name="edgelog"):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: name)


def test_mode_switch():
    assert qe._lease_mode({}) == "firestore"
    assert qe._lease_mode({"lease_mode": "LOCAL"}) == "local"


def test_local_lease_fails_closed(monkeypatch):
    _host(monkeypatch)
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", True)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())
    assert not qe._local_lease_ok({"lease_mode": "local"})[0]                      # no list
    assert not qe._local_lease_ok({"serving_hosts": []})[0]
    _host(monkeypatch, "RAZER")
    assert not qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]               # PC
    _host(monkeypatch)
    assert qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", -1)                                # other process
    assert not qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", False)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())
    assert not qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]


def test_local_mode_never_reads_firestore(monkeypatch):
    _host(monkeypatch)
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", True)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())

    def boom(*a, **k):
        raise AssertionError("Firestore lease read in local mode")
    monkeypatch.setattr(qe, "_lease_verify_cached", boom)
    monkeypatch.setattr(qe, "_check_lease_for_broker", boom)
    src = open(qe.__file__, encoding="utf-8").read()
    assert "lease_ok, lease_reason = _local_lease_ok(cfg)" in src
    assert qe._local_lease_ok({"lease_mode": "local", "serving_hosts": ["edgelog"]}) == (
        True, "lease ok (local: serving host + host slot)")


def test_default_is_firestore_lease_unchanged():
    # the shipped default must keep today's Firestore lease until the owner sets lease_mode=local
    assert "lease_mode" not in qe.DEFAULT_CONFIG
    assert qe._lease_mode(dict(qe.DEFAULT_CONFIG)) == "firestore"
    assert qe._lease_mode(qe._read_config_for_gate(path="no-such-file.json")) == "firestore"
    for v in (None, "", "firestore", "Firestore", "loc", 1):
        assert qe._lease_mode({"lease_mode": v}) == "firestore"
