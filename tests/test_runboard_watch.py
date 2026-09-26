"""tools/runboard_watch.py against an in-memory fake Firestore client.

WHY: runboard_watch.py is how MANAGER and the strategy chats edit the COMPARE > RUNBOARD watch
list (users/{uid}/meta/runboard_watch) without a code ship. Every write is meant to be a
read-modify-write so two chats appending at once never stomp each other; `_apply()` does that with
a real Firestore transaction against a live client, and falls back to a plain get-then-set when the
client has no `.transaction()` (see its docstring). FakeClient below is exactly such a client: an
in-memory stand-in with just enough surface (collection/document/get/set, no transaction) for every
command to run against it unchanged. This suite never imports firebase_admin, builds no real
client and reads no credentials -- conftest.py's live-system guard would fail any test that tried.
"""
import copy
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import tools.runboard_watch as rw  # noqa: E402


# ── in-memory fake Firestore client ──────────────────────────────────────────────────────────
class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def collection(self, name):
        return FakeCollRef(self._store, self._path + (name,))

    def get(self, transaction=None):
        return FakeSnapshot(self._store.get(self._path))

    def set(self, data, merge=False):
        if merge and self._path in self._store:
            cur = copy.deepcopy(self._store[self._path])
            cur.update(copy.deepcopy(data))
            self._store[self._path] = cur
        else:
            self._store[self._path] = copy.deepcopy(data)


class FakeCollRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id):
        return FakeDocRef(self._store, self._path + (str(doc_id),))


class FakeClient:
    """In-memory stand-in for firebase_admin's Firestore client. Deliberately has NO
    `.transaction()` method: `runboard_watch._apply()` detects that with `hasattr()` and falls
    back to a plain get-then-set, which is enough to exercise every merge/validation rule below --
    real cross-process contention needs a real backend and is out of scope for an in-memory fake."""
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return FakeCollRef(self._store, (name,))


@pytest.fixture
def db():
    return FakeClient()


def _seed_run(db, run_id, famKey=None, **extra):
    data = {"id": run_id}
    if famKey is not None:
        data["famKey"] = famKey
    data.update(extra)
    rw.run_ref(db, run_id).set(data)


def _house_vocab():
    spec = importlib.util.spec_from_file_location(
        "_tfv_for_runboard_watch", os.path.join(ROOT, "tests", "test_family_vocabulary.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.VOCAB


# ── add / update-in-place / order ────────────────────────────────────────────────────────────
def test_add_new_run_resolves_family_from_famkey_and_appends(db):
    _seed_run(db, 382, famKey="NOISE")
    doc = rw.cmd_add(db, [382], None, None, None, None, "MANAGER", False, False)
    assert [r["id"] for r in doc["runs"]] == [382]
    entry = doc["runs"][0]
    assert entry["family"] == "NOISE"
    assert entry["lane"] == ""
    assert entry["verdict"] == ""
    assert entry["added_by"] == "MANAGER"
    assert entry["added_at"]
    assert doc["version"] == 1
    assert doc["updated_by"] == "MANAGER"
    assert rw._read(rw.watch_ref(db)) == doc   # really persisted, not just previewed


def test_add_update_in_place_only_changes_given_fields(db):
    _seed_run(db, 382, famKey="NOISE")
    rw.cmd_add(db, [382], None, None, None, None, "MANAGER", False, False)
    doc = rw.cmd_add(db, [382], None, None, None, "watch the tail", "MANAGER", False, False)
    assert len(doc["runs"]) == 1                       # no duplicate row
    entry = doc["runs"][0]
    assert entry["family"] == "NOISE"                  # untouched
    assert entry["added_by"] == "MANAGER"               # untouched
    assert entry["note"] == "watch the tail"            # the one field given


def test_add_order_preserved_new_appends_at_end(db):
    for rid, fam in [(100, "ORB"), (200, "NOISE"), (300, "DIP")]:
        _seed_run(db, rid, famKey=fam)
    rw.cmd_add(db, [100], None, None, None, None, "MANAGER", False, False)
    rw.cmd_add(db, [200], None, None, None, None, "MANAGER", False, False)
    rw.cmd_add(db, [100], None, None, "still good", None, "NOISE", False, False)  # update, no reorder
    doc = rw.cmd_add(db, [300], None, None, None, None, "MANAGER", False, False)
    assert [r["id"] for r in doc["runs"]] == [100, 200, 300]


def test_add_unknown_run_refused_without_force(db):
    with pytest.raises(rw.ToolError, match="not found"):
        rw.cmd_add(db, [999], None, None, None, None, "MANAGER", False, False)


def test_add_force_bypasses_existence_but_still_needs_family(db):
    with pytest.raises(rw.ToolError, match="no --family"):
        rw.cmd_add(db, [999], None, None, None, None, "MANAGER", True, False)
    doc = rw.cmd_add(db, [999], "MISC", None, None, None, "MANAGER", True, False)
    assert doc["runs"][0]["family"] == "MISC"


def test_add_rejects_family_outside_vocabulary(db):
    with pytest.raises(rw.ToolError, match="house vocabulary"):
        rw.cmd_add(db, [1], "BOGUS", None, None, None, "MANAGER", True, False)


# ── verdict / note ────────────────────────────────────────────────────────────────────────────
def test_verdict_requires_existing_entry_then_stamps(db):
    with pytest.raises(rw.ToolError, match="not on the watch list"):
        rw.cmd_verdict(db, 382, "LIVE", "NOISE", None, False)
    _seed_run(db, 382, famKey="NOISE")
    rw.cmd_add(db, [382], None, None, None, None, "MANAGER", False, False)
    doc = rw.cmd_verdict(db, 382, "LIVE - Webull NOISE leg", "NOISE", None, False)
    entry = doc["runs"][0]
    assert entry["verdict"] == "LIVE - Webull NOISE leg"
    assert entry["verdict_by"] == "NOISE"          # falls back to --from when --lane omitted
    assert entry["verdict_at"]
    doc2 = rw.cmd_verdict(db, 382, "still live", "SOMEONE", "NOISE", False)
    assert doc2["runs"][0]["verdict_by"] == "NOISE"   # --lane wins over --from when given


def test_verdict_length_limit(db):
    rw._check_verdict("y" * 80)   # exactly 80 is fine
    with pytest.raises(rw.ToolError, match="80"):
        rw.cmd_verdict(db, 1, "x" * 81, "NOISE", None, False)
    with pytest.raises(rw.ToolError, match="80"):
        rw.cmd_add(db, [1], "MISC", None, "x" * 81, None, "MANAGER", True, False)


def test_note_requires_existing_entry_then_sets(db):
    with pytest.raises(rw.ToolError, match="not on the watch list"):
        rw.cmd_note(db, 1, "text", "NOISE", False)
    _seed_run(db, 1, famKey="MISC")
    rw.cmd_add(db, [1], None, None, None, None, "MANAGER", False, False)
    doc = rw.cmd_note(db, 1, "keep an eye on the tail", "NOISE", False)
    assert doc["runs"][0]["note"] == "keep an eye on the tail"


# ── remove ────────────────────────────────────────────────────────────────────────────────────
def test_remove_idempotent_and_order_preserved(db, capsys):
    for rid, fam in [(1, "ORB"), (2, "NOISE"), (3, "DIP")]:
        _seed_run(db, rid, famKey=fam)
        rw.cmd_add(db, [rid], None, None, None, None, "MANAGER", False, False)
    doc = rw.cmd_remove(db, [2], "MANAGER", False)
    assert [r["id"] for r in doc["runs"]] == [1, 3]
    doc2 = rw.cmd_remove(db, [2, 3], "MANAGER", False)   # 2 is already gone -- must not raise
    assert [r["id"] for r in doc2["runs"]] == [1]
    assert "not on the watch list" in capsys.readouterr().out


# ── import ────────────────────────────────────────────────────────────────────────────────────
def test_import_new_and_merge(db, tmp_path):
    _seed_run(db, 335, famKey="ENGU-Q")
    rw.cmd_add(db, [335], None, None, None, None, "MANAGER", False, False)
    payload = [
        {"id": 335, "note": "seeded note", "verdict": "candidate"},
        {"id": 257, "family": "ORB", "lane": "ORB", "verdict": "LIVE", "added_by": "MANAGER",
         "added_at": "2026-09-20"},
    ]
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    doc = rw.cmd_import(db, str(p), "MANAGER", False)
    by_id = {r["id"]: r for r in doc["runs"]}
    assert by_id[335]["note"] == "seeded note"
    assert by_id[335]["verdict"] == "candidate"
    assert by_id[335]["family"] == "ENGU-Q"           # untouched -- absent from the imported entry
    assert by_id[257]["family"] == "ORB"
    assert by_id[257]["added_at"] == "2026-09-20"      # preserved verbatim from the seed file
    assert [r["id"] for r in doc["runs"]] == [335, 257]   # new entries append at the end


def test_import_new_entry_without_family_raises(db, tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps([{"id": 900}]), encoding="utf-8")
    with pytest.raises(rw.ToolError, match="missing family"):
        rw.cmd_import(db, str(p), "MANAGER", False)


def test_import_validates_family_and_verdict(db, tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps([{"id": 1, "family": "BOGUS"}]), encoding="utf-8")
    with pytest.raises(rw.ToolError, match="house vocabulary"):
        rw.cmd_import(db, str(p), "MANAGER", False)
    p2 = tmp_path / "seed2.json"
    p2.write_text(json.dumps([{"id": 1, "family": "MISC", "verdict": "z" * 81}]), encoding="utf-8")
    with pytest.raises(rw.ToolError, match="80"):
        rw.cmd_import(db, str(p2), "MANAGER", False)


# ── --dry writes nothing ─────────────────────────────────────────────────────────────────────
def test_dry_add_writes_nothing(db):
    _seed_run(db, 382, famKey="NOISE")
    doc = rw.cmd_add(db, [382], None, None, "preview", None, "MANAGER", False, True)
    assert doc["runs"][0]["verdict"] == "preview"     # preview reflects the hypothetical write
    assert rw._read(rw.watch_ref(db)) is None          # but nothing was actually persisted


def test_dry_verdict_note_remove_import_write_nothing(db, tmp_path):
    _seed_run(db, 382, famKey="NOISE")
    rw.cmd_add(db, [382], None, None, None, None, "MANAGER", False, False)
    baseline = rw._read(rw.watch_ref(db))

    rw.cmd_verdict(db, 382, "preview verdict", "NOISE", None, True)
    assert rw._read(rw.watch_ref(db)) == baseline

    rw.cmd_note(db, 382, "preview note", "NOISE", True)
    assert rw._read(rw.watch_ref(db)) == baseline

    rw.cmd_remove(db, [382], "MANAGER", True)
    assert rw._read(rw.watch_ref(db)) == baseline

    p = tmp_path / "seed.json"
    p.write_text(json.dumps([{"id": 900, "family": "MISC"}]), encoding="utf-8")
    rw.cmd_import(db, str(p), "MANAGER", True)
    assert rw._read(rw.watch_ref(db)) == baseline


# ── family vocabulary stays in step with the house list ─────────────────────────────────────
def test_family_vocabulary_matches_house_list():
    assert rw.FAMILIES == _house_vocab()
