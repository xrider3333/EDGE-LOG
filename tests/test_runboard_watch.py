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


# ── research rows (no engine run; MANAGER #38, 2026-10-05) ───────────────────────────────────
def test_research_row_carries_its_own_numbers_and_never_checks_runs(db):
    wf = rw.stretch_numbers(6.1, 31200)
    doc = rw.cmd_research(db, "R2.55", "DAILYFADE", "MISC", "TV", "DEAD at Stage A, 0 of 8 cells", wf, None,
                          None, "TV", False)
    e = doc["runs"][0]
    assert e["id"] == "R2.55" and e["kind"] == "research" and e["name"] == "DAILYFADE"
    assert e["wf"] == {"roc30": 6.1, "dd_usd": 31200.0, "roc_pct": 6.34}   # no dd_pct: dd / $100k is not a DD %
    assert "lb" not in e and e["verdict_by"] == "TV" and e["verdict_at"]


def test_research_update_in_place_and_shares_verdict_note_remove(db):
    rw.cmd_research(db, "R2.55", "DAILYFADE", "MISC", "TV", "DEAD", rw.stretch_numbers(6.1, 31200), None,
                    None, "TV", False)
    doc = rw.cmd_research(db, "R2.55", None, None, None, None, None, rw.stretch_numbers(2.0, 20000), "lb read",
                          "TV", False)
    e = doc["runs"][0]
    assert len(doc["runs"]) == 1 and e["verdict"] == "DEAD" and e["note"] == "lb read"
    assert e["lb"]["dd_usd"] == 20000.0 and "dd_pct" not in e["lb"]
    rw.cmd_verdict(db, rw.parse_id("R2.55"), "DEAD - confirmed", "MANAGER", None, False)
    rw.cmd_note(db, rw.parse_id("R2.55"), "see ledger", "TV", False)
    e = rw._read(rw.watch_ref(db))["runs"][0]
    assert e["verdict"] == "DEAD - confirmed" and e["note"] == "see ledger"
    doc = rw.cmd_remove(db, [rw.parse_id("R2.55")], "TV", False)
    assert doc["runs"] == []


def test_research_rows_sit_beside_engine_runs_without_touching_them(db):
    _seed_run(db, 382, famKey="NOISE")
    rw.cmd_add(db, [382], None, None, None, None, "MANAGER", False, False)
    doc = rw.cmd_research(db, "SIPORB-R2", "SIPORB", "MISC", "STRATEGY-BEATING", "DEAD",
                          rw.stretch_numbers(3.0, 45000, dd_pct_peak=45.0), None, None, "TV", False)
    assert [r["id"] for r in doc["runs"]] == [382, "SIPORB-R2"]
    assert "kind" not in doc["runs"][0]


def test_research_refusals(db):
    with pytest.raises(rw.ToolError, match="research id"):
        rw.cmd_research(db, "2.55", None, "MISC", "TV", "x", rw.stretch_numbers(1, 1000), None, None, "TV", False)
    with pytest.raises(rw.ToolError, match="needs --family"):
        rw.cmd_research(db, "R2.60", None, None, "TV", "x", rw.stretch_numbers(1, 1000), None, None, "TV", False)
    doc = rw.cmd_research(db, "R2.52", "V3", "BOOK", "FRONTIER", "STEP 1 FAIL - no ROC computed", None, None, None,
                          "TV", False)
    assert "wf" not in doc["runs"][-1]                 # a verdict with no numbers is listed, not plotted
    with pytest.raises(rw.ToolError, match="BOTH"):
        rw.stretch_numbers(6.1, None)
    with pytest.raises(rw.ToolError, match="vocabulary"):
        rw.cmd_research(db, "R2.61", None, "DAILYFADE", "TV", "x", rw.stretch_numbers(1, 1000), None, None, "TV", False)
    _seed_run(db, 382, famKey="NOISE")
    rw.cmd_add(db, [382], None, None, None, None, "MANAGER", False, False)
    assert rw.parse_id("382") == 382 and rw.parse_id(" R2.55 ") == "R2.55"


def test_research_dd5_is_optional_stored_only_when_given_and_checked(db):
    """DD5 (owner 2026-10-07): the average of the 5 worst drawdowns rides beside a stretch's worst drawdown.
    It is stored only when given, so a row written before it (or without it) keeps its exact old shape."""
    assert "dd5_usd" not in rw.stretch_numbers(6.1, 31200)
    wf = rw.stretch_numbers(93.8, 44849, dd5_usd=33612.4)
    assert wf == {"roc30": 93.8, "dd_usd": 44849.0, "roc_pct": 140.23, "dd5_usd": 33612.4}
    lb = rw.stretch_numbers(155.5, 21000, None, 21000)                  # n=1: DD5 equals the worst drawdown
    assert lb["dd5_usd"] == 21000.0
    doc = rw.cmd_research(db, "B463-DD5", "BOOK463", "BOOK", "MANAGER", "REFERENCE", wf, lb, None, "MANAGER", False)
    e = doc["runs"][0]
    assert e["wf"]["dd5_usd"] == 33612.4 and e["lb"]["dd5_usd"] == 21000.0
    with pytest.raises(rw.ToolError, match="cannot be deeper"):
        rw.stretch_numbers(93.8, 44849, dd5_usd=50000)
    with pytest.raises(rw.ToolError, match="positive"):
        rw.stretch_numbers(93.8, 44849, dd5_usd=0)
    with pytest.raises(rw.ToolError, match="belongs to a stretch"):
        rw.stretch_numbers(None, None, None, 30000)


def test_list_prints_dd5_when_a_row_has_it(db, capsys):
    rw.cmd_research(db, "R9.01", "WITHDD5", "MISC", "TV", "DEAD", rw.stretch_numbers(6.1, 31200, dd5_usd=20000),
                    None, None, "TV", False)
    rw.cmd_research(db, "R9.02", "NODD5", "MISC", "TV", "DEAD", rw.stretch_numbers(6.1, 31200), None, None, "TV", False)
    capsys.readouterr()
    rw.cmd_list(db)
    out = capsys.readouterr().out
    line1 = [l for l in out.splitlines() if "R9.01" in l][0]
    line2 = [l for l in out.splitlines() if "R9.02" in l][0]
    assert "DD5 $20,000" in line1 and "DD5" not in line2


def test_import_accepts_research_ids(db, tmp_path):
    f = tmp_path / "seed.json"
    f.write_text(json.dumps([{"id": "R2.53", "kind": "research", "family": "MISC", "verdict": "DEAD",
                              "wf": rw.stretch_numbers(3.0, 45000)}, {"id": "382", "family": "NOISE"}]))
    doc = rw.cmd_import(db, str(f), "MANAGER", False)
    assert [r["id"] for r in doc["runs"]] == ["R2.53", 382]


# ── DD % is BROKER STYLE: "DD % from peak (start $100k)" (owner 2026-10-08, MANAGER #35 / ELWA #37) ──────────
# The lane works the figure out with augur_engine.drawdowns.dd_pct_peak and passes it in; this tool only STORES
# it. The old dd_pct (= 100 x dd_usd / $100,000) is retired: it is never written and never invented from dollars.
class _Exit(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _cli(monkeypatch, db, *argv, client=None):
    """Run the real main() against the fake client (no credentials, no network); returns the exit code."""
    monkeypatch.setattr(rw, "real_client", client or (lambda: db))
    monkeypatch.setattr(sys, "argv", ["runboard_watch.py", *argv])

    def fake_exit(code):
        raise _Exit(code)

    monkeypatch.setattr(rw.os, "_exit", fake_exit)
    with pytest.raises(_Exit) as ei:
        rw.main()
    return ei.value.code


def _research_args(*flags):
    return rw.build_parser().parse_args(["research", "R9.10", "--from", "TV", *flags])


def test_no_dd_pct_key_is_written_with_or_without_a_peak_figure(db):
    for s in (rw.stretch_numbers(6.1, 31200), rw.stretch_numbers(6.1, 31200, 12.5),
              rw.stretch_numbers(6.1, 31200, dd5_usd=20000), rw.stretch_numbers(6.1, 31200, 12.5, 20000)):
        assert "dd_pct" not in s
    doc = rw.cmd_research(db, "R9.11", "NOPCT", "MISC", "TV", "DEAD", rw.stretch_numbers(6.1, 31200),
                          rw.stretch_numbers(2.0, 20000, 8.0), None, "TV", False)
    e = rw._read(rw.watch_ref(db))["runs"][0]
    assert e == doc["runs"][0] and "dd_pct" not in e["wf"] and "dd_pct" not in e["lb"]
    with pytest.raises(TypeError):                      # the old keyword is gone: nothing can pass a share of $100k in
        rw.stretch_numbers(6.1, 31200, dd_pct=31.2)


def test_peak_figure_is_stored_when_given_and_absent_when_not():
    assert "dd_pct_peak" not in rw.stretch_numbers(93.8, 44849)
    assert rw.stretch_numbers(93.8, 44849, 12.3456)["dd_pct_peak"] == 12.35            # rounded to 2 dp
    assert rw.stretch_numbers(93.8, 44849, dd_pct_peak=0.01)["dd_pct_peak"] == 0.01
    assert rw.stretch_numbers(93.8, 44849, dd_pct_peak=100)["dd_pct_peak"] == 100.0    # a total wipe-out is the top
    assert rw.stretch_numbers(93.8, 44849, 12.3, 33612.4) == {
        "roc30": 93.8, "dd_usd": 44849.0, "roc_pct": 140.23, "dd_pct_peak": 12.3, "dd5_usd": 33612.4}


@pytest.mark.parametrize("bad", [0, 0.0, 0.001, -1, -0.01, 100.01, 101, 117, float("nan")])
def test_peak_figure_outside_zero_to_hundred_is_rejected(bad):
    with pytest.raises(rw.ToolError, match=r"percent of the peak, 0-100"):
        rw.stretch_numbers(93.8, 44849, bad)


def test_424_case_dollar_drawdown_alone_stores_no_percent_at_all(db):
    """Run #424: a $116,916 worst drop read ~117% (dd / $100k) though its P&L never went below zero."""
    wf = rw.stretch_numbers(50.0, 116916)
    assert set(wf) == {"roc30", "dd_usd", "roc_pct"}                                    # no percent of any kind
    rw.cmd_research(db, "R4.24", "R424", "MISC", "TV", "REF", wf, None, None, "TV", False)
    e = rw._read(rw.watch_ref(db))["runs"][0]
    assert not [k for k in e["wf"] if "pct" in k and k != "roc_pct"]
    # a row written before this change still carries its retired share-of-start figure; it is never shown as a DD %
    old = rw._read(rw.watch_ref(db))
    old["runs"].append({"id": "R4.25", "kind": "research", "family": "MISC", "verdict": "OLD",
                        "wf": {"roc30": 50.0, "dd_usd": 116916.0, "dd_pct": 116.92, "roc_pct": 194.86}})
    rw.watch_ref(db).set(old)
    out = _capture_list(db)
    for row_id in ("R4.24", "R4.25"):
        line = [l for l in out.splitlines() if row_id in l][0]
        assert "DD $116,916" in line and "117" not in line and "116.9" not in line and "from peak" not in line
    # re-running the research row replaces the old wf wholesale, so the retired key is gone from it
    doc = rw.cmd_research(db, "R4.25", None, None, None, None, rw.stretch_numbers(50.0, 116916), None, None, "TV", False)
    assert "dd_pct" not in _find_row(doc, "R4.25")["wf"]


def _capture_list(db):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rw.cmd_list(db)
    return buf.getvalue()


def _find_row(doc, rid):
    return next(r for r in doc["runs"] if r["id"] == rid)


def test_peak_figure_without_its_roc_and_dollar_drawdown_is_rejected():
    with pytest.raises(rw.ToolError, match="belongs to a stretch"):
        rw.stretch_numbers(None, None, 25.0)
    with pytest.raises(rw.ToolError, match="BOTH"):
        rw.stretch_numbers(6.1, None, 25.0)
    with pytest.raises(rw.ToolError, match="BOTH"):
        rw.stretch_numbers(None, 31200, 25.0)
    with pytest.raises(rw.ToolError, match="belongs to a stretch"):                      # same rule as DD5
        rw.research_numbers(_research_args("--wf-dd-pct-peak", "25"))
    with pytest.raises(rw.ToolError, match="belongs to a stretch"):                      # LB peak, only WF numbers given
        rw.research_numbers(_research_args("--wf-roc30", "6.1", "--wf-dd", "31200", "--lb-dd-pct-peak", "25"))
    assert rw.research_numbers(_research_args()) == (None, None)


def test_retired_dd_pct_flag_fails_naming_the_new_flags(db, monkeypatch, capsys):
    with pytest.raises(rw.ToolError) as ei:
        rw.research_numbers(_research_args("--wf-roc30", "6.1", "--wf-dd", "31200", "--dd-pct", "31.2"))
    assert "--wf-dd-pct-peak" in str(ei.value) and "--lb-dd-pct-peak" in str(ei.value)
    code = _cli(monkeypatch, db, "research", "R9.12", "--family", "MISC", "--verdict", "DEAD", "--wf-roc30", "6.1",
                "--wf-dd", "31200", "--dd-pct", "31.2", "--from", "TV",
                client=lambda: pytest.fail("a refused flag must not even build a Firestore client"))
    assert code == 1 and rw._read(rw.watch_ref(db)) is None                              # refused, nothing written
    err = capsys.readouterr().err
    assert "--wf-dd-pct-peak" in err and "--lb-dd-pct-peak" in err


def test_lb_and_wf_peak_flags_round_trip_through_the_cli(db, monkeypatch):
    code = _cli(monkeypatch, db, "research", "R9.13", "--name", "PEAKS", "--family", "BOOK", "--lane", "TV",
                "--verdict", "REFERENCE", "--wf-roc30", "93.8", "--wf-dd", "44849", "--wf-dd-pct-peak", "21.4",
                "--wf-dd5", "33612.4", "--lb-roc30", "155.5", "--lb-dd", "21000", "--lb-dd-pct-peak", "9.876",
                "--from", "TV")
    assert code == 0
    e = rw._read(rw.watch_ref(db))["runs"][0]
    assert e["wf"] == {"roc30": 93.8, "dd_usd": 44849.0, "roc_pct": 140.23, "dd_pct_peak": 21.4, "dd5_usd": 33612.4}
    assert e["lb"]["dd_pct_peak"] == 9.88 and e["lb"]["dd_usd"] == 21000.0 and "dd_pct" not in e["lb"]
    # LB peak alone (no WF peak): the WF stretch carries none, the LB stretch carries its own
    code = _cli(monkeypatch, db, "research", "R9.14", "--family", "MISC", "--verdict", "DEAD", "--wf-roc30", "6.1",
                "--wf-dd", "31200", "--lb-roc30", "2.0", "--lb-dd", "20000", "--lb-dd-pct-peak", "7.5", "--from", "TV")
    e2 = _find_row(rw._read(rw.watch_ref(db)), "R9.14")
    assert code == 0 and "dd_pct_peak" not in e2["wf"] and e2["lb"]["dd_pct_peak"] == 7.5


def test_cli_rejects_an_out_of_range_peak_and_writes_nothing(db, monkeypatch, capsys):
    code = _cli(monkeypatch, db, "research", "R9.15", "--family", "MISC", "--verdict", "DEAD", "--wf-roc30", "6.1",
                "--wf-dd", "31200", "--wf-dd-pct-peak", "117", "--from", "TV")
    assert code == 1 and rw._read(rw.watch_ref(db)) is None
    assert "percent of the peak, 0-100" in capsys.readouterr().err


def test_dry_run_and_summary_say_from_peak_only_when_a_peak_figure_was_given(db, capsys):
    with_peak = rw.stretch_numbers(93.8, 44849, 21.4)
    without = rw.stretch_numbers(93.8, 44849)
    rw.cmd_research(db, "R9.20", "WITHPK", "MISC", "TV", "DEAD", with_peak, rw.stretch_numbers(2.0, 20000, 8.0), None,
                    "TV", True)                                                         # --dry
    out = capsys.readouterr().out
    assert "WF 93.8 @30k DD $44,849 / DD 21.4% from peak" in out and "LB 2.0 @30k DD $20,000 / DD 8.0% from peak" in out
    assert "--dry: wrote nothing" in out and rw._read(rw.watch_ref(db)) is None
    rw.cmd_research(db, "R9.21", "NOPK", "MISC", "TV", "DEAD", without, rw.stretch_numbers(2.0, 20000), None, "TV", True)
    out = capsys.readouterr().out
    assert "WF 93.8 @30k DD $44,849" in out and "LB 2.0 @30k DD $20,000" in out
    assert "peak" not in out                                                            # no peak wording, no peak key
    rw.cmd_research(db, "R9.22", "REAL", "MISC", "TV", "DEAD", with_peak, None, None, "TV", False)   # a real write prints it too
    assert "DD 21.4% from peak" in capsys.readouterr().out


def test_list_shows_a_percent_only_as_from_peak(db, capsys):
    rw.cmd_research(db, "R9.30", "PK", "MISC", "TV", "DEAD", rw.stretch_numbers(6.1, 31200, 14.3, 20000), None, None,
                    "TV", False)
    rw.cmd_research(db, "R9.31", "NOPK", "MISC", "TV", "DEAD", rw.stretch_numbers(6.1, 31200), None, None, "TV", False)
    capsys.readouterr()
    out = _capture_list(db)
    l1 = [l for l in out.splitlines() if "R9.30" in l][0]
    l2 = [l for l in out.splitlines() if "R9.31" in l][0]
    assert "DD $31,200 / DD 14.3% from peak DD5 $20,000" in l1
    assert "DD $31,200" in l2 and "%" not in l2 and "peak" not in l2
