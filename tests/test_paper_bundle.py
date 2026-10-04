"""api/paper_bundle.py - every paper trade in a few documents (LEDGER step 3, owner GO 2026-10-03).

Synthetic only: Firestore is an in-memory fake, nothing touches the network or C:\\EdgeLog.
Covers: the round trip keeps every field the board reads; a bundle bigger than one chunk splits and rejoins
in order; chunk 0 is written last and a shrunk bundle leaves no stale tail; a short read cannot shrink the
standing bundle; a torn set (two generations) or a missing part is refused so the board falls back.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import paper_bundle as pb  # noqa: E402

UID = "uid-test"


class _Snap:
    def __init__(self, id_, data):
        self.id, self._d, self.exists = id_, data, data is not None

    def to_dict(self):
        return None if self._d is None else dict(self._d)


class _Doc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def get(self):
        return _Snap(self.path.rsplit("/", 1)[-1], self.db.store.get(self.path))

    def set(self, data, merge=False):
        self.db.order.append(self.path)
        self.db.store[self.path] = dict(data)

    def delete(self):
        self.db.store.pop(self.path, None)

    def collection(self, name):
        return _Col(self.db, self.path + "/" + name)


class _Col:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def document(self, id_):
        return _Doc(self.db, self.path + "/" + id_)

    def stream(self):
        pre = self.path + "/"
        return [_Snap(p[len(pre):], d) for p, d in sorted(self.db.store.items())
                if p.startswith(pre) and "/" not in p[len(pre):]]


class _DB:
    def __init__(self):
        self.store, self.order = {}, []

    def collection(self, name):
        return _Col(self, name)


def _trade(i, leg="ORB", **kw):
    d = {"leg": leg, "strategy": "X.py", "side": 1, "entryTime": 1_790_000_000 + i * 60,
         "exitTime": 1_790_000_000 + i * 60 + 300, "entryIso": "2026-09-30T10:00:00-04:00",
         "exitIso": "2026-09-30T10:05:00-04:00", "entry_px": 100.5, "exit_px": 101.25, "pnl_pts": 0.75,
         "pnl_usd": 15.0 + i, "backfill": False, "live_from": "2026-09-01", "open": False,
         "close_day": "2026-09-30", "flags": [], "size": 1.0, "run_date": "2026-09-30",
         "createdAt": "never kept"}
    d.update(kw)
    return d


def _seed(db, n, **kw):
    for i in range(n):
        db.store["users/%s/paper_trades/t%04d" % (UID, i)] = _trade(i, **kw)


def test_round_trip_keeps_the_board_fields_and_drops_the_rest():
    db = _DB()
    _seed(db, 3)
    db.store["users/%s/paper_trades/t0001" % UID].update(roll_artifact=True, roll_note="splice", open=True)
    st = pb.write_bundle(db, UID)
    assert st["n_total"] == 3 and st["parts"] == 1
    rows, meta = pb.read_bundle(db, UID)
    assert meta["n_total"] == 3 and len(rows) == 3
    by = {r["id"]: r for r in rows}
    r = by["t0001"]
    assert r["roll_artifact"] is True and r["roll_note"] == "splice" and r["open"] is True
    assert r["pnl_usd"] == 16.0 and r["entryIso"].startswith("2026-09-30") and r["leg"] == "ORB"
    assert "createdAt" not in r and "size" not in r          # fields the board never reads stay out
    assert "roll_artifact" not in by["t0000"]                # only flagged trades carry it
    assert by["t0000"]["backfill"] is False and by["t0000"]["open"] is False   # a real False survives


def test_big_bundle_splits_into_chunks_and_rejoins_in_order(monkeypatch):
    monkeypatch.setattr(pb, "CHUNK_CHARS", 1500)
    db = _DB()
    _seed(db, 40)
    st = pb.write_bundle(db, UID)
    assert st["parts"] > 1
    assert all(len(c) <= 1500 + 400 for c in (db.store["users/%s/paper_bundle/%d" % (UID, p)]["rows"]
                                              for p in range(st["parts"])))
    rows, meta = pb.read_bundle(db, UID)
    assert len(rows) == 40 and meta["n_total"] == 40
    assert [r["entryTime"] for r in rows] == sorted(r["entryTime"] for r in rows)
    assert st["n_total"] == 40


def test_chunk_zero_is_written_last_and_a_shrunk_bundle_leaves_no_tail(monkeypatch):
    db = _DB()
    _seed(db, 30)
    monkeypatch.setattr(pb, "CHUNK_CHARS", 1200)
    st = pb.write_bundle(db, UID)
    assert st["parts"] >= 3
    written = [p for p in db.order if "/paper_bundle/" in p]
    assert written[-1].endswith("/paper_bundle/0")
    # now the collection loses a few trades (a prune): fewer chunks, and the old tail is deleted
    for i in range(10, 30):
        db.store.pop("users/%s/paper_trades/t%04d" % (UID, i))
    monkeypatch.setattr(pb, "SHRINK_GUARD", 0.0)
    st2 = pb.write_bundle(db, UID)
    assert st2["parts"] < st["parts"]
    left = [p for p in db.store if "/paper_bundle/" in p]
    assert len(left) == st2["parts"]


def test_a_short_read_cannot_shrink_the_standing_bundle():
    db = _DB()
    _seed(db, 50)
    assert pb.write_bundle(db, UID)["n_total"] == 50
    for i in range(10, 50):
        db.store.pop("users/%s/paper_trades/t%04d" % (UID, i))      # 10 of 50 trades now read
    msgs = []
    assert pb.write_bundle(db, UID, log=msgs.append) is None
    assert msgs and "NOT written" in msgs[0]
    rows, meta = pb.read_bundle(db, UID)
    assert meta["n_total"] == 50 and len(rows) == 50                # the standing bundle is untouched


def test_a_torn_or_incomplete_set_is_refused():
    a = {"gen": "1", "part": 0, "parts": 2, "fields": pb.FIELDS, "rows": "[]"}
    b = {"gen": "2", "part": 1, "parts": 2, "fields": pb.FIELDS, "rows": "[]"}
    with pytest.raises(ValueError):
        pb.decode_chunks([a, b])                                    # two writes mixed
    with pytest.raises(ValueError):
        pb.decode_chunks([a])                                       # part 1 missing
    with pytest.raises(ValueError):
        pb.decode_chunks([])
    db = _DB()
    db.store["users/%s/paper_bundle/0" % UID] = dict(a)
    db.store["users/%s/paper_bundle/1" % UID] = dict(b)
    assert pb.read_bundle(db, UID) == (None, None)


def test_empty_collection_writes_an_empty_bundle():
    db = _DB()
    st = pb.write_bundle(db, UID)
    assert st["n_total"] == 0 and st["parts"] == 1
    rows, meta = pb.read_bundle(db, UID)
    assert rows == [] and meta["n_total"] == 0
    json.loads(db.store["users/%s/paper_bundle/0" % UID]["rows"])
