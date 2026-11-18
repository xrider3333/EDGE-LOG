from api import qqq_exec as qe


def test_late_alert_fires_once_per_leg_action_day(monkeypatch):
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda m, t, log=None, priority=None: sent.append((t, m)))
    monkeypatch.setattr(qe, "_late_alerted", set())
    assert not qe._late_order_alert("ORB", "ENTER", "long", 8.4, log=lambda *a: None)
    assert not qe._late_order_alert("ORB", "ENTER", "long", "", log=lambda *a: None)
    assert not qe._late_order_alert("ORB", "ENTER", "long", None, log=lambda *a: None)
    assert qe._late_order_alert("ORB", "ENTER", "long", 307.4, log=lambda *a: None)
    assert not qe._late_order_alert("ORB", "ENTER", "long", 310.0, log=lambda *a: None)
    assert qe._late_order_alert("ORB", "EXIT", "long", 61.0, log=lambda *a: None)
    assert len(sent) == 2 and "307 s" in sent[0][1]


def test_late_alert_never_raises(monkeypatch):
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(qe, "_late_alerted", set())
    assert qe._late_order_alert("NOISE", "ENTER", "short", 999, log=lambda *a: None) is False
