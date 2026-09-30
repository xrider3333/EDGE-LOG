"""Review 2026-09-30 #5: the NT and Webull journal syncs must never re-send blank owner fields
(notes, chart link, setup, grade, timeframe) or createdAt for a trade doc that already exists."""
import sys
import types

from api import nt_sync


class _Snap:
    def __init__(self, i, exists):
        self.id, self.exists = i, exists


class _Ref:
    def __init__(self, i):
        self.id = i


class _Col:
    def document(self, i):
        return _Ref(i)


class _Db:
    def __init__(self, existing):
        self.existing = set(existing)
        self.asked = []

    def get_all(self, refs):
        refs = list(refs)
        self.asked.append(len(refs))
        return [_Snap(r.id, r.id in self.existing) for r in refs]


def _doc():
    return {"entry": 1, "exit": 2, "fees": 1.9, "setup": "-", "grade": "-", "timeframe": "-",
            "notes": "", "chartUrl": "", "createdAt": "ts", "ntSync": True}


def test_existing_trades_keep_what_the_owner_typed(monkeypatch):
    got = []
    monkeypatch.setitem(sys.modules, "__main__", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "api.runner", types.SimpleNamespace(_note_reads=lambda b, n: got.append((b, n))))
    db = _Db(existing={"old"})
    out = dict(nt_sync.owner_safe(db, _Col(), [("old", _doc()), ("new", _doc())]))
    for f in nt_sync.OWNER_FIELDS:
        assert f not in out["old"], f
    assert out["old"]["fees"] == 1.9 and out["old"]["ntSync"] is True
    assert out["new"]["notes"] == "" and out["new"]["setup"] == "-" and out["new"]["createdAt"] == "ts"
    assert got == [("other", 2)]


def test_nothing_to_write_reads_nothing():
    db = _Db(existing=set())
    assert nt_sync.owner_safe(db, _Col(), []) == []
    assert db.asked == []


def test_webull_sync_uses_the_same_guard():
    from api import webull_sync
    assert webull_sync.owner_safe is nt_sync.owner_safe
