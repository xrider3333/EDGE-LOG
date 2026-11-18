from api import qqq_exec as qe


def test_retired_legs_shape():
    d = {k: {"since": v, "reason": "owner retired"} for k, v in qe.RETIRED_LEGS.items()}
    assert d["DIP"] == {"since": "2026-11-16", "reason": "owner retired"}
    src = open(qe.__file__, encoding="utf-8").read()
    assert 'doc["retired_legs"]' in src
