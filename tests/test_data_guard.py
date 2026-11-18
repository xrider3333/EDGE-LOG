"""A worker does not claim work its own box cannot do (api/runner.py, 2026-11-18).

The claim used to happen before anything looked for the data, so a runner on a box
without a job's master claimed it and then failed "no master" - which is what the cloud
box did on 2026-09-21 with two re-validate jobs off this queue. It matters again now the
owner's DESKTOP runs workers 6-8: that box has the NQ and ES masters but not the QQQ /
Alpaca side files, so a QQQ job reaching it would die instead of waiting for a host that
can run it.

The job must stay QUEUED and untouched, and the skip must be audible - a job no host can
run has to be visible rather than silently circling.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_quiet import _runner, _queue, _Snap          # noqa: E402  (shared harness)


@pytest.fixture
def R(monkeypatch):
    r = _runner()
    monkeypatch.setattr(r, "_psutil", None)
    return r


def _no_master(R, monkeypatch, found=None):
    """Point the runner's master lookup at a fake registry."""
    calls = []

    def _fm(inst, tf="5m", session=None, source=None):
        calls.append((inst, tf, session, source))
        return found
    monkeypatch.setattr(R.ae, "find_master", _fm)
    return calls


def test_a_job_whose_master_is_missing_is_left_queued_and_said_out_loud(R, monkeypatch):
    _no_master(R, monkeypatch, found=None)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "QQQ",
                  "timeframe": "5m", "session": "rth"})
    q = _queue(R, [snap], None)
    ran = []
    monkeypatch.setattr(R, "process_job", lambda job, cb=None: ran.append(job))
    logs = []
    assert q.run_once(log=logs.append) == 0
    assert ran == [], "the job must not run on a box without its data"
    assert snap.reference.updates == [], "and must be left queued, untouched"
    line = [s for s in logs if s.startswith("[data]")]
    assert len(line) == 1, logs
    assert "QQQ" in line[0] and "5m" in line[0], line[0]
    assert "queued" in line[0]


def test_a_job_whose_master_is_there_is_claimed_as_before(R, monkeypatch):
    _no_master(R, monkeypatch, found={"instrument": "NQ", "date_to": "2026-11-17"})
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ",
                  "timeframe": "5m", "session": "rth"})
    q = _queue(R, [snap], None)
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: {"status": "error", "error": "x", "finishedAt": 1.0})
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    logs = []
    q.run_once(log=logs.append)
    assert snap.reference.updates, "a host with the data still claims the job"
    assert not [s for s in logs if s.startswith("[data]")]


def test_the_source_is_part_of_the_question(R, monkeypatch):
    """A roll-adjusted source is a different file - the check has to pass it through, or a
    host with the plain master would claim a job that needs the adjusted one."""
    calls = _no_master(R, monkeypatch, found=None)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ",
                  "timeframe": "1m", "session": "eth", "source": "db_adj_eth"})
    q = _queue(R, [snap], None)
    logs = []
    q.run_once(log=logs.append)
    assert calls and calls[0] == ("NQ", "1m", "eth", "db_adj_eth")
    assert "db_adj_eth" in [s for s in logs if s.startswith("[data]")][0]


def test_the_line_is_throttled_to_once_per_job_per_ten_minutes(R, monkeypatch):
    _no_master(R, monkeypatch, found=None)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "QQQ"})
    q = _queue(R, [snap], None)
    first, second = [], []
    assert q.run_once(log=first.append) == 0
    assert q.run_once(log=second.append) == 0
    assert [s for s in first if s.startswith("[data]")]
    assert not [s for s in second if s.startswith("[data]")], "a queue polled every few " \
        "seconds must not reprint this line every tick"


def test_a_book_job_is_not_judged_on_one_master(R, monkeypatch):
    """A BOOK spans several instruments, so one missing master says nothing about it."""
    calls = _no_master(R, monkeypatch, found=None)
    snap = _Snap({"status": "queued", "type": "book", "instrument": "NQ"})
    q = _queue(R, [snap], None)
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: {"status": "error", "error": "x", "finishedAt": 1.0})
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    q.run_once(log=lambda *_a: None)
    assert calls == [], "a book is not master-checked here"
    assert snap.reference.updates, "and is still claimed"


def test_a_broken_registry_read_does_not_refuse_work(R, monkeypatch):
    """Failing to READ the registry is not evidence the data is absent - the job runs and
    fails loudly, as it did before this guard existed."""
    def _boom(*_a, **_k):
        raise OSError("registry locked")
    monkeypatch.setattr(R.ae, "find_master", _boom)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "QQQ"})
    q = _queue(R, [snap], None)
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: {"status": "error", "error": "x", "finishedAt": 1.0})
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    logs = []
    q.run_once(log=logs.append)
    assert snap.reference.updates, "a registry error must not starve the queue"
    assert any("master check skipped" in s for s in logs)


def test_the_guard_sits_before_the_claim_write():
    """Order is the whole point: a check after the claim is the bug this fixes."""
    import io
    import api.runner as Rr
    src = io.open(Rr.__file__, encoding="utf-8").read()
    assert src.index("DATA GUARD: DO NOT CLAIM WORK THIS HOST CANNOT DO") < \
        src.index('ref.update({"status": "running", "progress": 0,')
