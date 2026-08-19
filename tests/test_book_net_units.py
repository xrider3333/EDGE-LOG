"""BOOK runs are already in DOLLARS - the save layer must not multiply them again.

augur_engine/book.py converts every leg's trades with that leg's own contract multiplier
before pooling, so a book result's `best.total_pnl` is USD, not points. The runner's save
layer turns points into dollars with `mult`, which for a book is a SECOND multiplication.
Runs #238/#258/#261/#262/#263 were queued by script (no `mult` in the job doc), fell through
to the default 20, and stored a headline exactly 20x too large while their `book` block and
lockbox stayed correct. Regression-guard both directions: a book pins mult to 1.0, a normal
points-denominated run still converts.
"""
import types

import pytest

from api.runner import FirestoreQueue


def _persist(job, result):
    """Call the real _persist_run with every Firestore/disk touch stubbed out."""
    q = FirestoreQueue.__new__(FirestoreQueue)
    saved = {}

    class _Doc:
        def set(self, d):
            saved.update(d)

    class _Col:
        def document(self, *a):
            return _Ref()

        def collection(self, *a):
            return _Col()

    class _Ref(_Doc):
        def collection(self, *a):
            return _Col()

    q.db = types.SimpleNamespace(collection=lambda *a: _Col())
    q._next_run_id = lambda uid: 999
    q._assign_family = lambda uid, s: (None, None)
    q._master_of = lambda job: None
    q._run_window = lambda job, result, mm: (job.get("date_from"), job.get("date_to"), 100)
    q._winner_equity = lambda job, bp: None
    q._persist_run("uid", job, result, log=lambda *a, **k: None)
    return saved


BOOK_RESULT = {
    "best": {"total_pnl": 984200.31, "max_drawdown": 56090.18,
             "num_trades": 8494, "profit_factor": 1.3427, "win_rate": 41.0},
    "equity": [0.0, 1245993.95],
    "book": {"name": "3-leg", "legs": [{"strategy": "a.py", "mult": 20.0}],
             "whole": {"total_pnl": 1245993.95},
             "pre_lockbox": {"total_pnl": 984200.31, "max_drawdown": 56090.18},
             "lockbox": {"total_pnl": 261793.65}},
    "validate": {"verdict": "PASS"},
}


@pytest.mark.parametrize("job_mult", [None, 1, 20, 50])
def test_book_headline_stays_in_dollars(job_mult):
    """Whatever `mult` the job doc carries, a book headline equals the book's own $ figure."""
    job = {"type": "book", "strategy": "BOOK - 3-leg", "instrument": "NQ"}
    if job_mult is not None:
        job["mult"] = job_mult
    doc = _persist(job, BOOK_RESULT)
    assert doc["best_pnl_usd"] == pytest.approx(984200.31)
    assert doc["best_dd_usd"] == pytest.approx(56090.18)
    assert doc["multiplier"] == 1.0
    # the headline must agree with the block the RUNBOARD BOOKS tile reads
    assert doc["best_pnl_usd"] == pytest.approx(doc["book"]["pre_lockbox"]["total_pnl"])


def test_non_book_run_still_converts_points_to_dollars():
    """A normal run's `best` is in POINTS - the mult conversion must survive untouched."""
    job = {"type": "validate", "strategy": "ORB.py", "instrument": "NQ", "mult": 20}
    result = {"best": {"total_pnl": 1000.0, "max_drawdown": 250.0, "num_trades": 10}}
    doc = _persist(job, result)
    assert doc["best_pnl_usd"] == pytest.approx(20000.0)
    assert doc["best_dd_usd"] == pytest.approx(5000.0)
    assert doc["multiplier"] == 20.0
