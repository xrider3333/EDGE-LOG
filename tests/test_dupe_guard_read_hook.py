"""
dupe_guard.find_duplicate's optional read_hook (2026-09-07 quota-burn fix).

WHY: find_duplicate() reads up to ~1,000 docs (400 completed backtests + 600 runs).
api/runner.py used to call it BEFORE attempting a job's claim, so with N runner
processes racing the same queued job, N-1 of them paid that cost and then lost the
claim anyway. The fix moved the call to after a successful claim (see runner.py's
run_once) and wired read_hook to the process's read-quota meter so that cost is
visible. This file pins find_duplicate's read-accounting contract in isolation, with
no real Firestore client — dupe_guard.py has no firebase_admin/google-cloud import,
so plain fakes are enough (same spirit as tests/test_runner_sweep.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import dupe_guard


class _FakeSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    """Answers .order_by(...).limit(n).stream() and .limit(n).stream() alike —
    find_duplicate tries the order_by path first and falls back on failure."""

    def __init__(self, snaps):
        self._snaps = list(snaps)

    def order_by(self, *_a, **_k):
        return self

    def limit(self, n):
        return _FakeQuery(self._snaps[:n])

    def stream(self):
        return iter(self._snaps)


class _FakeDocRef:
    def __init__(self, backtests, runs):
        self._cols = {"backtests": backtests, "runs": runs}

    def collection(self, name):
        return self._cols[name]


class _FakeDb:
    def __init__(self, backtests, runs):
        self._backtests = backtests
        self._runs = runs

    def collection(self, _name):
        return self

    def document(self, _uid):
        return _FakeDocRef(self._backtests, self._runs)


CANDIDATE = {"type": "backtest", "strategy": "NOISE_1_0.py", "instrument": "NQ",
            "timeframe": "5m", "date_from": "2024-01-01", "date_to": "2024-06-01"}


def _matching_prior_job(job_id="prior1", **extra):
    job = dict(CANDIDATE)
    job["status"] = "done"
    job["finishedAt"] = 100.0
    job.update(extra)
    return _FakeSnap(job_id, job)


def test_read_hook_reports_backtests_count_when_nothing_matches():
    backtests = _FakeQuery([_FakeSnap("a", {"strategy": "OTHER.py", "status": "done"})])
    runs = _FakeQuery([])
    db = _FakeDb(backtests, runs)
    calls = []
    match, run_id = dupe_guard.find_duplicate(
        db, "uid1", CANDIDATE, read_hook=calls.append)
    assert match is None and run_id is None
    # no match -> the runs collection is never touched, so read_hook fires exactly once
    assert calls == [1]


def test_read_hook_reports_both_reads_on_a_match():
    # NOTE: run_id is itself a MATERIAL field (two jobs differing only by run_id are
    # NOT considered the same work), so a matching prior job must NOT carry one here
    # -- that's also the realistic case (older jobs, or ones the guard itself hasn't
    # stamped yet) that makes find_duplicate fall through to the runs-collection scan.
    other = _matching_prior_job(job_id="other", strategy="OTHER.py")
    prior = _matching_prior_job(job_id="prior1")
    backtests = _FakeQuery([prior, other])   # 2 docs returned by the backtests query
    runs = _FakeQuery([])                    # empty runs page (still one read: 0 docs)
    db = _FakeDb(backtests, runs)
    calls = []
    match, run_id = dupe_guard.find_duplicate(
        db, "uid1", CANDIDATE, exclude_ids=(), read_hook=calls.append)
    assert match is not None
    assert run_id is None    # empty runs page -> nothing to resolve to, but it WAS read
    # first call = backtests docs returned (2), second = runs docs returned (0)
    assert calls == [2, 0]


def test_read_hook_is_optional_and_never_required():
    backtests = _FakeQuery([_matching_prior_job()])
    runs = _FakeQuery([])
    db = _FakeDb(backtests, runs)
    # no read_hook at all -- must behave exactly as before this fix
    match, run_id = dupe_guard.find_duplicate(db, "uid1", CANDIDATE)
    assert match is not None


def test_a_broken_read_hook_never_breaks_find_duplicate():
    backtests = _FakeQuery([_matching_prior_job()])
    runs = _FakeQuery([])
    db = _FakeDb(backtests, runs)

    def _boom(_n):
        raise RuntimeError("meter is down")

    match, run_id = dupe_guard.find_duplicate(db, "uid1", CANDIDATE, read_hook=_boom)
    assert match is not None, "a guard that can break a backtest is worse than the duplicate it prevents"
