"""
FirestoreQueue.sync_runs must never clobber a web-owned run field (api/runner.py,
confirmed live 2026-09-16).

WHY THESE EXIST. sync_runs() pushes every row of optimizer_history.db's `runs` table
up to users/{uid}/runs with batch.set(doc, merge=True) on every primary runner boot.
merge=True means: a key ABSENT from the outgoing doc leaves Firestore's current value
alone, but a key PRESENT in the doc overwrites it. `starred` and `note` ARE columns in
the local SQLite table (the old Streamlit app's save_run() still inserts starred=0,
note='' on every new row -- see optimizer.py), so they travel with EVERY synced doc,
almost always stale. The web is the only thing that still edits them (index.html's
_toggleStar/_toggleArch/the note prompt write straight to Firestore) -- so every
runner restart overwrote the owner's web edits with the stale local values. 11 runs
the owner had unstarred in the web came back starred this way. `archived` has no local
column at all, so it was already safe under the old code; it is pinned here too so a
future local column of that name can't silently reopen the same bug.

This file uses fake Firestore collection/batch objects only -- no real Firestore, no
real optimizer_history.db (ae.list_runs/ae.get_run are monkeypatched).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.runner as runner_mod
from api.runner import FirestoreQueue


class _Ref:
    """One Firestore document reference. set(merge=True) applies Firestore's own merge
    semantics (top-level only, same as the real SDK for the plain dict docs used here):
    a key present in `data` overwrites; a key simply absent leaves the stored value."""

    def __init__(self, col, doc_id):
        self.col, self.id = col, doc_id

    def set(self, data, merge=False):
        cur = dict(self.col.docs.get(self.id, {})) if merge else {}
        cur.update(data)
        self.col.docs[self.id] = cur


class _Col:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def document(self, doc_id):
        return _Ref(self, doc_id)


class _Batch:
    """Mirrors the handful of firestore.WriteBatch methods sync_runs calls. Writes are
    queued and only applied on commit(), same shape as the real SDK."""

    def __init__(self):
        self._pending = []

    def set(self, ref, data, merge=False):
        self._pending.append((ref, dict(data), merge))

    def commit(self):
        for ref, data, merge in self._pending:
            ref.set(data, merge=merge)
        self._pending = []


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

    def batch(self):
        return _Batch()


def _queue(runs_col):
    q = FirestoreQueue.__new__(FirestoreQueue)   # skip __init__ -- no real firebase_admin
    q.allow = {"uid1"}
    q.db = _Db({"runs": runs_col})
    return q


def test_web_owned_fields_survive_resync_engine_fields_still_update(monkeypatch):
    """A local run with starred=1/note='x' (the legacy SQLite defaults/toggle) synced
    over a Firestore doc the owner already curated (starred=0, note='owner') must leave
    the web's values alone -- while an engine-owned field (best_pf) still updates."""
    runs = _Col({"42": {"id": 42, "strategy": "OLD_LABEL.py", "best_pf": 1.0,
                        "starred": 0, "note": "owner", "archived": True}})
    q = _queue(runs)
    local_doc = {"id": 42, "strategy": "ORB_1_0.py", "best_pf": 2.1,
                 "starred": 1, "note": "x"}   # stale local starred/note, per the bug
    monkeypatch.setattr(runner_mod.ae, "list_runs", lambda: [{"id": 42}])
    monkeypatch.setattr(runner_mod.ae, "get_run", lambda rid: dict(local_doc) if rid == 42 else None)

    total = q.sync_runs(log=lambda *a: None)

    assert total == 1
    doc = runs.docs["42"]
    assert doc["starred"] == 0, "web-set starred must survive the resync"
    assert doc["note"] == "owner", "web-set note must survive the resync"
    assert doc["best_pf"] == 2.1, "engine-owned fields must still update"
    assert doc["strategy"] == "ORB_1_0.py", "engine-owned fields must still update"


def test_archived_untouched_across_resync(monkeypatch):
    """archived has no local SQLite column at all, so the local doc never carries it --
    confirm a re-sync still leaves the web's archived flag exactly as it was."""
    runs = _Col({"7": {"id": 7, "strategy": "X.py", "best_pf": 0.5, "archived": True}})
    q = _queue(runs)
    monkeypatch.setattr(runner_mod.ae, "list_runs", lambda: [{"id": 7}])
    monkeypatch.setattr(runner_mod.ae, "get_run",
                         lambda rid: {"id": 7, "strategy": "X.py", "best_pf": 0.9} if rid == 7 else None)

    q.sync_runs(log=lambda *a: None)

    assert runs.docs["7"]["archived"] is True
    assert runs.docs["7"]["best_pf"] == 0.9   # engine field still moved


def test_run_with_no_firestore_doc_yet_is_created_without_error(monkeypatch):
    """A run local history has but Firestore has never seen must be created cleanly --
    dropping the web-owned keys must not raise on a doc.pop() of a missing key."""
    runs = _Col({})   # no "99" doc yet
    q = _queue(runs)
    monkeypatch.setattr(runner_mod.ae, "list_runs", lambda: [{"id": 99}])
    monkeypatch.setattr(runner_mod.ae, "get_run",
                         lambda rid: {"id": 99, "strategy": "NEW.py", "best_pf": 3.0} if rid == 99 else None)

    total = q.sync_runs(log=lambda *a: None)

    assert total == 1
    assert runs.docs["99"]["best_pf"] == 3.0
    assert runs.docs["99"]["strategy"] == "NEW.py"
    # no sane-default claim beyond "absent" -- the web already treats a missing
    # `starred`/`archived` key as falsy (index.html: `r.starred?0:1`), so a brand new
    # run reads as unstarred/unarchived without sync_runs having to invent the key.
    assert "starred" not in runs.docs["99"]
