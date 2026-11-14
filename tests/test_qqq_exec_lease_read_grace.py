import time
from api import qqq_exec as qe

FAIL = "lease unverifiable: Firestore read failed (ResourceExhausted: 429 Quota exceeded.)"


def _holder(monkeypatch, uid="U", age=5.0, held=True):
    h = qe._LeaseHolder()
    h.begin(uid, stamp=time.time() - age)
    if not held:
        h.end("lost")
    monkeypatch.setattr(qe, "_LEASE", h)
    return h


def test_grace_allows_when_own_stamp_fresh_and_last_read_ours(monkeypatch):
    _holder(monkeypatch)
    now = time.time()
    st = {"_lease_read_ok_at": now - 60}
    ok, why = qe._lease_read_fail_grace(False, FAIL, "U", st, now, log=lambda *a: None)
    assert ok and why.startswith("lease ok (read failed")


def test_no_grace_when_own_stamp_old(monkeypatch):
    _holder(monkeypatch, age=qe.LEASE_SEND_MAX_AGE_SEC + 5)
    now = time.time()
    ok, _ = qe._lease_read_fail_grace(False, FAIL, "U", {"_lease_read_ok_at": now - 60}, now)
    assert not ok


def test_no_grace_without_recent_good_read(monkeypatch):
    _holder(monkeypatch)
    now = time.time()
    assert not qe._lease_read_fail_grace(False, FAIL, "U", {}, now)[0]
    old = {"_lease_read_ok_at": now - qe.LEASE_READ_GRACE_SEC - 1}
    assert not qe._lease_read_fail_grace(False, FAIL, "U", old, now)[0]


def test_no_grace_for_foreign_claim_or_lost_or_other_uid(monkeypatch):
    now = time.time()
    st = {"_lease_read_ok_at": now - 60}
    _holder(monkeypatch)
    foreign = "host 'pc' holds a fresh lease (5s old) -- broker sends blocked"
    assert not qe._lease_read_fail_grace(False, foreign, "U", st, now)[0]
    claims = "lease unverifiable: host 'pc' claims the lease but its timestamp is missing"
    assert not qe._lease_read_fail_grace(False, claims, "U", st, now)[0]
    assert not qe._lease_read_fail_grace(False, FAIL, "OTHER", st, now)[0]
    _holder(monkeypatch, held=False)
    assert not qe._lease_read_fail_grace(False, FAIL, "U", st, now)[0]


def test_cached_check_records_good_read_and_grace(monkeypatch):
    _holder(monkeypatch)
    calls = iter([(True, "lease ok (free or already ours)"), (False, FAIL)])
    monkeypatch.setattr(qe, "_check_lease_for_broker", lambda db, uid, log=print: next(calls))
    monkeypatch.setattr(qe, "_track_fs_read", lambda st: None)
    st = {}
    cfg = {"lease_verify_interval_sec": 0}
    assert qe._lease_verify_cached(object(), "U", st, cfg)[0]
    assert st["_lease_read_ok_at"]
    st["_lease_verify_at"] = 0
    ok, why = qe._lease_verify_cached(object(), "U", st, cfg, log=lambda *a: None)
    assert ok and "read failed" in why
