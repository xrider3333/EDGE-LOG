"""
Provisional run ids and their repair (api/runner.py, 2026-09-08).

WHY. During the 2026-09-07 Firestore read-quota outage a finished validate could not get a
run number (the counter is read inside a transaction), fell through to the epoch-second
fallback and was saved as run 1788836275 - a "number" that sorts above every real run for
ever. The rule now: never invent an id. Save it PROVISIONAL, and let the primary's sweep
renumber it once reads work again. These pin both halves.
"""
import os
import sys

import pytest

pytest.importorskip("google.cloud.firestore_v1.base_query",
                    reason="google-cloud-firestore is not part of the CI dev deps")
pytest.importorskip("firebase_admin", reason="firebase-admin is not part of the CI dev deps")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.runner import FirestoreQueue


class _Ref:
    def __init__(self, col, doc_id):
        self.col, self.id = col, doc_id

    def set(self, data, merge=False):
        cur = self.col.docs.get(self.id, {}) if merge else {}
        cur.update(data)
        self.col.docs[self.id] = cur
        self.col.log.append(("set", self.id))

    def update(self, patch):
        self.col.docs.setdefault(self.id, {}).update(patch)
        self.col.log.append(("update", self.id))

    def delete(self):
        self.col.docs.pop(self.id, None)
        self.col.log.append(("delete", self.id))


class _Snap:
    def __init__(self, col, doc_id):
        self.id, self._col = doc_id, col
        self.reference = _Ref(col, doc_id)

    def to_dict(self):
        return dict(self._col.docs[self.id])


class _Query:
    def __init__(self, col, field, value):
        self.col, self.field, self.value = col, field, value

    def stream(self):
        return iter([_Snap(self.col, k) for k, v in list(self.col.docs.items())
                     if v.get(self.field) == self.value])


class _Col:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.log = []

    def where(self, filter=None):
        return _Query(self, filter.field_path, filter.value)

    def document(self, doc_id):
        return _Ref(self, doc_id)


class _Root:
    def __init__(self, cols):
        self._cols = cols

    def collection(self, name):
        return self._cols[name]


class _Db:
    def __init__(self, cols):
        self._root = _Root(cols)

    def collection(self, _users):
        return self

    def document(self, _uid):
        return self._root


def _queue(runs, jobs):
    q = FirestoreQueue.__new__(FirestoreQueue)
    q.col = "backtests"
    q.allow = {"uid1"}
    q.db = _Db({"runs": runs, "backtests": jobs})
    return q


def test_provisional_run_is_renumbered_and_its_job_repointed(monkeypatch):
    runs = _Col({"1788836275": {"id": 1788836275, "id_provisional": True,
                                "strategy": "ENGUQ_1M_ETH_ERW_1_0.py", "best_pf": 3.44},
                 "327": {"id": 327, "strategy": "NOISE_1_1_SBS_V90_MT.py"}})
    jobs = _Col({"jobA": {"run_id": 1788836275, "status": "done"}})
    q = _queue(runs, jobs)
    monkeypatch.setattr(q, "_next_run_id", lambda uid: 328)
    monkeypatch.setattr(q, "_assign_family", lambda uid, strat: ("ENGUQ", 41))

    assert q.repair_provisional_run_ids(log=lambda *a: None) == 1
    assert "1788836275" not in runs.docs
    new = runs.docs["328"]
    assert new["id"] == 328
    assert "id_provisional" not in new
    assert new["id_was_provisional"] == 1788836275
    assert new["best_pf"] == 3.44                      # payload carried whole
    assert (new["famKey"], new["famSeq"]) == ("ENGUQ", 41)
    assert jobs.docs["jobA"]["run_id"] == 328
    assert runs.docs["327"]["id"] == 327                # untouched


def test_repair_stops_quietly_while_reads_still_fail(monkeypatch):
    runs = _Col({"1788836275": {"id": 1788836275, "id_provisional": True, "strategy": "X.py"}})
    q = _queue(runs, _Col())
    monkeypatch.setattr(q, "_next_run_id", lambda uid: None)
    assert q.repair_provisional_run_ids(log=lambda *a: None) == 0
    assert "1788836275" in runs.docs                    # nothing destroyed


def test_two_provisionals_are_renumbered_oldest_first(monkeypatch):
    runs = _Col({"1788900000": {"id": 1788900000, "id_provisional": True, "strategy": "B.py"},
                 "1788800000": {"id": 1788800000, "id_provisional": True, "strategy": "A.py"}})
    q = _queue(runs, _Col())
    seq = iter([328, 329])
    monkeypatch.setattr(q, "_next_run_id", lambda uid: next(seq))
    monkeypatch.setattr(q, "_assign_family", lambda uid, strat: (None, None))
    assert q.repair_provisional_run_ids(log=lambda *a: None) == 2
    assert runs.docs["328"]["strategy"] == "A.py"
    assert runs.docs["329"]["strategy"] == "B.py"
