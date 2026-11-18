from api import qqq_exec as qe


def test_alert_only_on_change(monkeypatch):
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None: sent.append((title, priority)))
    st = {}
    q = "lease unverifiable: Firestore read failed (ResourceExhausted: 429 Quota exceeded.)"
    assert qe._lease_alert_transition(st, True, "lease ok", log=lambda *a: None) is None
    assert qe._lease_alert_transition(st, False, q, log=lambda *a: None) == "quota"
    for _ in range(5):
        assert qe._lease_alert_transition(st, False, q, log=lambda *a: None) is None
    assert qe._lease_alert_transition(st, False, "lease held by other host", log=lambda *a: None) == "blocked"
    assert qe._lease_alert_transition(st, True, "lease ok", log=lambda *a: None) == "ok"
    assert [p for _, p in sent] == ["high", "high", "default"] and "429" in sent[0][0]


def test_grace_ok_counts_as_ok():
    assert qe._lease_alert_kind(True, "lease ok (read failed, own stamp fresh)") == "ok"


def test_verify_cached_still_fails_closed(monkeypatch):
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: None)
    monkeypatch.setattr(qe, "_check_lease_for_broker",
                        lambda db, uid, log=print: (False, "lease unverifiable: Firestore read failed (429 Quota exceeded)"))
    st = {}
    ok, reason = qe._lease_verify_cached(object(), "u", st, {}, log=lambda *a: None)
    assert ok is False and st["_lease_alert_kind"] == "quota"
