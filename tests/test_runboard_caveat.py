r"""CAVEAT markers on a RUNBOARD row (tools/runboard_watch.py, MANAGER #72 item 2, 2026-10-07).

WHY A MARKER EXISTS AT ALL. Two kinds of row on the watch list do not mean what a reader assumes:
NOISE lockbox cells taken from run docs are cold-restart reloads and drop roughly a quarter of the
year's trades, and ORB #234 / #239 / #257 walk-forward cells are pinned-card in-sample replays, so
the "walk-forward" column there is not out-of-sample. Both have already been quoted forward as if
they were comparable.

WHY A FIXED VOCABULARY RATHER THAN A NOTE. The list already has a free-text `note`, and that is
exactly why it is not the answer: a warning written twelve different ways stops being read. The
marker is one of two keys, and the HOUSE WORDING travels with the key so the web app renders the
same sentence every time instead of inventing one.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import runboard_watch as rw  # noqa: E402


# ═══════════════════════════════════════════════════ the vocabulary
def test_the_two_markers_the_owner_asked_for_exist():
    assert set(rw.CAVEATS) == {"cold", "replay"}


def test_each_marker_carries_its_own_explanation():
    """The web app renders this text rather than writing its own, so the house wording lives
    here and cannot drift between readers."""
    for key, why in rw.CAVEATS.items():
        assert isinstance(why, str) and len(why) > 40, key


def test_the_cold_marker_says_what_is_actually_missing():
    why = rw.CAVEATS["cold"]
    assert "quarter" in why, "a reader needs the SIZE of the problem, not just its name"
    assert "comparable" in why


def test_the_replay_marker_says_it_is_not_out_of_sample():
    why = rw.CAVEATS["replay"]
    assert "NOT out-of-sample" in why, "that is the whole point of the marker"
    assert "in-sample replay" in why


def test_an_unknown_marker_is_refused_and_lists_the_real_ones():
    """A typo must not become a silent third category."""
    with pytest.raises(rw.ToolError) as e:
        rw._check_caveat("warm")
    msg = str(e.value)
    assert "cold" in msg and "replay" in msg, msg
    assert "none" in msg, "it has to say how to clear one"


@pytest.mark.parametrize("key", ["cold", "replay", "none"])
def test_every_accepted_key_passes_the_check(key):
    rw._check_caveat(key)


def test_the_check_is_case_sensitive_on_purpose():
    """One spelling, so a grep for a marker finds every row carrying it."""
    with pytest.raises(rw.ToolError):
        rw._check_caveat("COLD")


# ═══════════════════════════════════════════════════ the mutation, against a fake store
class _FakeRef:
    def __init__(self, store):
        self.store = store

    def collection(self, _n):
        return self

    def document(self, _n):
        return self

    def get(self, transaction=None):
        class _S:
            exists = True

            def __init__(self, d):
                self._d = d

            def to_dict(self):
                return self._d
        return _S(self.store["doc"])

    def set(self, value):
        self.store["doc"] = value


def _db_with(runs):
    store = {"doc": {"version": 1, "runs": runs}}
    ref = _FakeRef(store)

    class _DB:
        def collection(self, _n):
            return ref

    return _DB(), store, ref


def _apply(monkeypatch, runs, run_id, key, frm="ELwA-FEATURES"):
    db, store, ref = _db_with(runs)
    monkeypatch.setattr(rw, "watch_ref", lambda _db: ref)
    monkeypatch.setattr(rw, "_dry_or_apply",
                        lambda _db, _ref, mutate, dry: mutate(store["doc"]))
    rw.cmd_caveat(db, run_id, key, frm, dry=False)
    return store


def test_marking_a_row_records_the_key_the_wording_and_who(monkeypatch):
    out = _apply(monkeypatch, [{"id": 234, "family": "ORB", "verdict": "crown"}], 234, "replay")
    row = out["doc"]["runs"][0]
    assert row["caveat"] == "replay"
    assert row["caveat_why"] == rw.CAVEATS["replay"]
    assert row["caveat_by"] == "ELwA-FEATURES"
    assert row["caveat_at"]


def test_marking_does_not_disturb_the_verdict_or_the_note(monkeypatch):
    """The marker is additive - it must never overwrite the lane's own words."""
    runs = [{"id": 382, "family": "NOISE", "verdict": "LIVE - Webull NOISE leg",
             "note": "keep an eye on the tail"}]
    out = _apply(monkeypatch, runs, 382, "cold")
    row = out["doc"]["runs"][0]
    assert row["verdict"] == "LIVE - Webull NOISE leg"
    assert row["note"] == "keep an eye on the tail"
    assert row["caveat"] == "cold"


def test_clearing_removes_every_caveat_field(monkeypatch):
    """A stale explanation left behind would be worse than none."""
    runs = [{"id": 234, "family": "ORB", "caveat": "replay", "caveat_why": "x",
             "caveat_by": "someone", "caveat_at": "2026-10-07"}]
    out = _apply(monkeypatch, runs, 234, "none")
    row = out["doc"]["runs"][0]
    for k in ("caveat", "caveat_why", "caveat_by", "caveat_at"):
        assert k not in row, k


def test_remarking_overwrites_rather_than_accumulates(monkeypatch):
    runs = [{"id": 234, "family": "ORB"}]
    db, store, ref = _db_with(runs)
    monkeypatch.setattr(rw, "watch_ref", lambda _db: ref)
    monkeypatch.setattr(rw, "_dry_or_apply",
                        lambda _db, _ref, mutate, dry: mutate(store["doc"]))
    rw.cmd_caveat(db, 234, "cold", "a", dry=False)
    rw.cmd_caveat(db, 234, "replay", "b", dry=False)
    row = store["doc"]["runs"][0]
    assert row["caveat"] == "replay"
    assert row["caveat_why"] == rw.CAVEATS["replay"]
    assert row["caveat_by"] == "b"


def test_a_row_that_is_not_on_the_list_is_refused(monkeypatch):
    """Silently adding it would put an unreviewed row on the owner's board."""
    db, store, ref = _db_with([{"id": 382}])
    monkeypatch.setattr(rw, "watch_ref", lambda _db: ref)
    monkeypatch.setattr(rw, "_dry_or_apply",
                        lambda _db, _ref, mutate, dry: mutate(store["doc"]))
    with pytest.raises(rw.ToolError) as e:
        rw.cmd_caveat(db, 999, "cold", "me", dry=False)
    assert "not on the watch list" in str(e.value)


def test_a_research_row_can_carry_one_too(monkeypatch):
    """Research ids are strings, not numbers, and a replayed research row is just as misleading."""
    runs = [{"id": "R2.55", "kind": "research", "family": "MISC", "verdict": "DEAD"}]
    out = _apply(monkeypatch, runs, "R2.55", "replay")
    assert out["doc"]["runs"][0]["caveat"] == "replay"


# ═══════════════════════════════════════════════════ the CLI wiring
def test_the_cli_exposes_caveat_and_documents_the_keys():
    src = open(os.path.join(TOOLS, "runboard_watch.py"), encoding="utf-8").read()
    assert 'sub.add_parser("caveat")' in src
    assert 'args.cmd == "caveat"' in src, "a parser with no dispatch is a silent no-op"
    assert "caveat 234 replay" in src, "the usage block must show it"


def test_the_marker_is_not_the_free_text_note():
    """If this ever becomes free text the marker stops being a marker - that is the design."""
    import inspect
    src = inspect.getsource(rw.cmd_caveat)
    assert "CAVEATS[key]" in src, "the wording must come from the table, not the caller"
