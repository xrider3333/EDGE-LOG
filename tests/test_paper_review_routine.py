"""tools/paper_review_routine.py - hermetic tests.

No real Firestore, no real C:\\EdgeLog logs: FakeDB stands in for firestore.client(), and
the module's log-path constants (RUNNER_LOG / NT_RECOVER_LOG / GATE_LIVE_LOG) are
monkeypatched onto tmp_path files for every test. tests/conftest.py's live_system_guard
would fail any test that touched the real C:\\EdgeLog anyway.
"""
import datetime as dt
import json
import os

import pytest

from tools import paper_review_routine as R


# ── FakeDB: just enough of the firestore.Client surface this module uses ────────────────
class FakeSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeQuery:
    def __init__(self, coll):
        self._coll = coll
        self._filters = []

    def where(self, field, op, value):
        assert op == "=="
        q = FakeQuery(self._coll)
        q._filters = self._filters + [(field, value)]
        return q

    def stream(self):
        for doc_id, data in self._coll.docs.items():
            if all(data.get(f) == v for f, v in self._filters):
                yield FakeSnap(doc_id, data)


class FakeColl:
    def __init__(self, store, path):
        self.store = store
        self.path = path
        self.docs = store.setdefault(path, {})

    def document(self, doc_id):
        return FakeDoc(self.store, self.path, doc_id)

    def where(self, field, op, value):
        return FakeQuery(self).where(field, op, value)

    def stream(self):
        return FakeQuery(self).stream()


class FakeDoc:
    def __init__(self, store, coll_path, doc_id):
        self.store = store
        self.coll_path = coll_path
        self.doc_id = doc_id

    def get(self):
        data = self.store.get(self.coll_path, {}).get(self.doc_id)
        return FakeSnap(self.doc_id, data)

    def set(self, payload, merge=False):
        coll = self.store.setdefault(self.coll_path, {})
        cur = coll.get(self.doc_id) if merge else None
        merged = dict(cur or {})
        merged.update(payload)
        coll[self.doc_id] = merged

    def collection(self, name):
        return FakeColl(self.store, self.coll_path + (self.doc_id, name))


class FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return FakeColl(self.store, (name,))

    def seed_report(self, date_str, data):
        (self.collection("users").document(R.UID).collection("paper_reports")
         .document(date_str).set(data))

    def seed_trade(self, doc_id, data):
        (self.collection("users").document(R.UID).collection("paper_trades")
         .document(doc_id).set(data))

    def seed_webull(self, data):
        (self.collection("users").document(R.UID).collection("meta")
         .document("qqq_exec").set(data))

    def get_report(self, date_str):
        return (self.collection("users").document(R.UID).collection("paper_reports")
                .document(date_str).get().to_dict())


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "INBOX", str(tmp_path / "inbox"))
    monkeypatch.setattr(R, "RUNNER_LOG", str(tmp_path / "runner.log"))
    monkeypatch.setattr(R, "NT_RECOVER_LOG", str(tmp_path / "nt_recover.log"))
    monkeypatch.setattr(R, "GATE_LIVE_LOG", str(tmp_path / "gate_live.log"))
    for p in (R.RUNNER_LOG, R.NT_RECOVER_LOG, R.GATE_LIVE_LOG):
        with open(p, "w", encoding="utf-8") as f:
            f.write("")
    yield


def _basic_report(pnl=100.0, status="runner_done", warnings=None):
    return {
        "legs": {"ORB": {"n_signals": 1, "pnl_usd": pnl, "n_since_start": 5,
                          "bars_appended": 1, "data_fresh_thru": "16:00",
                          "warnings": warnings or []}},
        "blend": {"pnl_usd": pnl}, "book": {"pnl_usd": pnl},
        "live": {}, "status": status,
    }


class _Args:
    def __init__(self, **kw):
        self.date = kw.get("date")
        self.selftest = kw.get("selftest", False)
        self.dry_run = kw.get("dry_run", False)


# ── date scan: oldest unreviewed first, weekend/holiday skipped ─────────────────────────
def test_start_picks_oldest_unreviewed_skipping_weekend(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    # window (last 5 sessions ending Mon 2026-09-28) = 09-22,23,24,25,28; Sat/Sun never
    # appear as candidates at all. 09-22/23 already reviewed, 09-24 is the oldest one
    # that is not, 09-25 is reviewed again (must not be picked over the older gap).
    monkeypatch.setattr(R, "et_now",
                        lambda: dt.datetime(2026, 9, 28, 17, 0))
    db.seed_report("2026-09-22", dict(_basic_report(pnl=1), status="reviewed"))
    db.seed_report("2026-09-23", dict(_basic_report(pnl=2), status="reviewed"))
    db.seed_report("2026-09-24", _basic_report(pnl=10))
    db.seed_report("2026-09-25", dict(_basic_report(pnl=20), status="reviewed"))
    R.cmd_start(_Args())
    out = capsys.readouterr().out
    assert "RESULT: REVIEW 2026-09-24" in out
    facts = json.loads(open(os.path.join(R.INBOX, "facts.json"), encoding="utf-8").read())
    assert facts["date"] == "2026-09-24"
    assert facts["nt_book"]["legs"]["ORB"]["pnl_usd"] == 10


def test_start_nothing_to_review_when_all_reviewed(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 9, 28, 17, 0))
    for d in ("2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28"):
        db.seed_report(d, dict(_basic_report(), status="reviewed"))
    R.cmd_start(_Args())
    assert "RESULT: NOTHING TO REVIEW" in capsys.readouterr().out


def test_start_missing_report_wins_over_later_unreviewed(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 9, 28, 17, 0))
    # 09-22/23 already reviewed, 09-24 has NO report at all, 09-25 does and is
    # unreviewed. The chronologically-first gap (09-24) must win, not the later day
    # that happens to have a report - a missing report is a runner failure and must
    # not be silently skipped past.
    db.seed_report("2026-09-22", dict(_basic_report(pnl=1), status="reviewed"))
    db.seed_report("2026-09-23", dict(_basic_report(pnl=2), status="reviewed"))
    db.seed_report("2026-09-25", _basic_report(pnl=5))
    with open(R.RUNNER_LOG, "w", encoding="utf-8") as f:
        f.write("2026-09-24 09:00:00  [paper] uid=X leg=ORB crashed: boom\n")
        f.write("2026-09-24 09:00:01  something unrelated\n")
    R.cmd_start(_Args())
    out = capsys.readouterr().out
    assert "RESULT: MISSING REPORT 2026-09-24" in out
    assert "crashed: boom" in out


def test_start_date_override_non_trading_day(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 9, 28, 17, 0))
    R.cmd_start(_Args(date="2026-09-27"))    # a Sunday
    assert "not a US trading day" in capsys.readouterr().out


def test_start_date_override_missing_report(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 9, 28, 17, 0))
    R.cmd_start(_Args(date="2026-09-24"))
    assert "RESULT: MISSING REPORT 2026-09-24" in capsys.readouterr().out


# ── cumulative sum + trades + roll_artifact ──────────────────────────────────────────────
def test_cumulative_sums_across_report_days(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 8, 13, 17, 0))
    db.seed_report("2026-08-11", _basic_report(pnl=100))
    db.seed_report("2026-08-12", _basic_report(pnl=-30))
    db.seed_report("2026-08-13", _basic_report(pnl=50))
    R.cmd_start(_Args(date="2026-08-13"))
    assert "RESULT: REVIEW 2026-08-13" in capsys.readouterr().out
    facts = json.loads(open(os.path.join(R.INBOX, "facts.json"), encoding="utf-8").read())
    cum = facts["nt_book"]["cumulative"]
    assert cum["n_report_days"] == 3
    assert cum["per_leg_pnl_usd"]["ORB"] == pytest.approx(120.0)
    assert cum["blend_pnl_usd"] == pytest.approx(120.0)


def test_trades_and_roll_artifact_surface(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 9, 15, 17, 0))
    db.seed_report("2026-09-15", _basic_report(pnl=10))
    db.seed_trade("pt_ORB_1", {"leg": "ORB", "run_date": "2026-09-15", "pnl_usd": 10,
                               "roll_artifact": True})
    db.seed_trade("pt_ORB_2", {"leg": "ORB", "run_date": "2026-09-14", "pnl_usd": 5})
    R.cmd_start(_Args(date="2026-09-15"))
    capsys.readouterr()
    facts = json.loads(open(os.path.join(R.INBOX, "facts.json"), encoding="utf-8").read())
    ids = [t["_id"] for t in facts["nt_book"]["trades_today"]]
    assert ids == ["pt_ORB_1"]
    assert facts["nt_book"]["roll_artifact_trade_ids"] == ["pt_ORB_1"]


def test_webull_doc_missing_is_reported_not_fatal(monkeypatch, capsys):
    db = FakeDB()
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 8, 11, 17, 0))
    db.seed_report("2026-08-11", _basic_report(pnl=10))
    R.cmd_start(_Args(date="2026-08-11"))
    assert "RESULT: REVIEW" in capsys.readouterr().out
    facts = json.loads(open(os.path.join(R.INBOX, "facts.json"), encoding="utf-8").read())
    assert facts["webull_book"]["available"] is False


# ── finish: validation FIX lines ─────────────────────────────────────────────────────────
def _start_one(monkeypatch, db, date_str="2026-09-24"):
    monkeypatch.setattr(R, "_db", lambda: db)
    monkeypatch.setattr(R, "et_now", lambda: dt.datetime(2026, 9, 25, 17, 0))
    db.seed_report(date_str, _basic_report(pnl=10))
    R.cmd_start(_Args(date=date_str))


def _write_verdict(v):
    R.dump(R.inbox("verdict.json"), v)


def test_finish_no_verdict_file_fails(monkeypatch, capsys):
    db = FakeDB()
    _start_one(monkeypatch, db)
    capsys.readouterr()
    with pytest.raises(SystemExit, match="FIX: write"):
        R.cmd_finish(_Args())


def test_finish_reports_fix_lines_for_bad_verdict(monkeypatch, capsys):
    db = FakeDB()
    _start_one(monkeypatch, db)
    capsys.readouterr()
    _write_verdict({"date": "2026-09-24", "verdict": "ok",
                    "nt_book": {}, "webull_book": {"orders": 1}, "owner_actions": "nope"})
    with pytest.raises(SystemExit, match="fixes above"):
        R.cmd_finish(_Args())
    out = capsys.readouterr().out
    assert "FIX: nt_book must be a non-empty object" in out
    assert "FIX: webull_book.verdict must be a non-empty string" in out
    assert "FIX: owner_actions must be a JSON list" in out


def test_finish_word_limit_and_date_mismatch(monkeypatch, capsys):
    db = FakeDB()
    _start_one(monkeypatch, db)
    capsys.readouterr()
    long_verdict = " ".join(["word"] * 130)
    _write_verdict({"date": "2026-09-23", "verdict": long_verdict,
                    "nt_book": {"ORB": "flat"},
                    "webull_book": {"orders": 0, "trades": 0, "realized_pnl": 0.0,
                                   "rail_trips": 0, "feed_stale_minutes": 0, "verdict": "quiet"},
                    "owner_actions": []})
    with pytest.raises(SystemExit):
        R.cmd_finish(_Args())
    out = capsys.readouterr().out
    assert "date must be exactly" in out
    assert "<=120 words" in out


# ── finish: dry-run and real merge write ─────────────────────────────────────────────────
def _good_verdict(date_str):
    return {"date": date_str, "verdict": "Quiet day, ORB signalled once, data fresh, no warnings.",
            "nt_book": {"ORB": "one signal, +$10, data fresh"},
            "webull_book": {"orders": 0, "trades": 0, "realized_pnl": 0.0, "rail_trips": 0,
                            "feed_stale_minutes": 0, "verdict": "no activity"},
            "owner_actions": []}


def test_finish_dry_run_does_not_write_firestore(monkeypatch, capsys):
    db = FakeDB()
    _start_one(monkeypatch, db)
    capsys.readouterr()
    _write_verdict(_good_verdict("2026-09-24"))
    R.cmd_finish(_Args(dry_run=True))
    out = capsys.readouterr().out
    assert "RESULT: DRY RUN OK" in out
    rep = db.get_report("2026-09-24")
    assert rep.get("status") == "runner_done"     # untouched


def test_finish_merge_writes_expected_fields_only(monkeypatch, capsys):
    db = FakeDB()
    _start_one(monkeypatch, db)
    capsys.readouterr()
    _write_verdict(_good_verdict("2026-09-24"))
    R.cmd_finish(_Args())
    out = capsys.readouterr().out
    assert "RESULT: WRITTEN 2026-09-24" in out
    rep = db.get_report("2026-09-24")
    assert rep["status"] == "reviewed"
    assert "reviewedAt" in rep
    assert rep["verdict"].startswith("Quiet day")
    assert rep["nt_book_review"] == {"ORB": "one signal, +$10, data fresh"}
    assert rep["webull_book_review"]["verdict"] == "no activity"
    assert rep["owner_actions"] == []
    # untouched fields from the runner's own write:
    assert rep["legs"]["ORB"]["pnl_usd"] == 10.0
    assert rep["blend"]["pnl_usd"] == 10.0
    # inbox cleared
    assert not os.path.exists(R.inbox("verdict.json"))
    assert not os.path.exists(R.inbox("state.json"))


# ── abort ─────────────────────────────────────────────────────────────────────────────
def test_abort_clears_in_progress_run(monkeypatch, capsys):
    db = FakeDB()
    _start_one(monkeypatch, db)
    capsys.readouterr()
    assert os.path.exists(R.inbox("state.json"))
    R.cmd_abort(_Args())
    out = capsys.readouterr().out
    assert "RESULT: ABORTED" in out
    assert not os.path.exists(R.inbox("state.json"))


def test_abort_with_nothing_in_progress(capsys):
    R.cmd_abort(_Args())
    assert "nothing was in progress" in capsys.readouterr().out


# ── selftest: full loop with no Firestore access at all ─────────────────────────────────
def test_selftest_start_and_dry_finish_need_no_firestore(monkeypatch, capsys):
    def _boom():
        raise AssertionError("selftest must never touch Firestore")
    monkeypatch.setattr(R, "_db", lambda: _boom())
    R.cmd_start(_Args(selftest=True))
    out = capsys.readouterr().out
    assert "SELFTEST" in out
    assert "RESULT: REVIEW 2026-08-11" in out
    facts = json.loads(open(os.path.join(R.INBOX, "facts.json"), encoding="utf-8").read())
    assert facts["selftest"] is True
    _write_verdict(_good_verdict("2026-08-11"))
    R.cmd_finish(_Args())   # no --dry-run flag - selftest forces dry anyway
    out = capsys.readouterr().out
    assert "RESULT: DRY RUN OK" in out
