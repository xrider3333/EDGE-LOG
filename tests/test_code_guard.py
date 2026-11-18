"""A worker does not claim a job whose STRATEGY FILE it does not have (2026-11-18).

The data half of this guard shipped in 559dca1d. MANAGER found the other half within the
hour, once the desktop workers were live: a box that has not pulled yet does not have the
strategy file a lane just pushed, so it claimed the auto-queued job and failed "strategy
not found: <name>.py". It bites every time a lane pushes a new file and queues a run
against it, because a box will not pull while a job is running.

Claiming a job you cannot run is worse than leaving it queued: it takes the work away from
a box that could have run it and spends a run slot on an error.
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
    # the DATA guard is not what is under test here - give every job its master
    monkeypatch.setattr(r.ae, "find_master", lambda *a, **k: {"instrument": "NQ", "date_to": "2026-11-17"})
    # the DATA guard is not under test in this file: give every job a master that is
    # really there, so what fails here can only be the code guard (2026-11-18: the data
    # guard now stats the master file, not just its registry row).
    import augur_engine.data as _D
    monkeypatch.setattr(_D, "master_on_disk", lambda row: True)
    return r


def _strategies(monkeypatch, path, sha=None):
    """Point the runner's strategy resolver at a path we control."""
    import augur_engine.strategies as S
    monkeypatch.setattr(S, "strategy_path", lambda n: path, raising=False)
    if sha is not None:
        monkeypatch.setattr(S, "strategy_file_sha", lambda p: sha, raising=False)


def _runs(R, monkeypatch, q):
    ran = []
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: (ran.append(job),
                                              {"status": "error", "error": "x", "finishedAt": 1.0})[1])
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    return ran


def test_a_job_whose_strategy_file_is_missing_is_left_queued_and_named(R, monkeypatch, tmp_path):
    _strategies(monkeypatch, str(tmp_path / "ORB_9_9.py"))
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ", "strategy": "ORB_9_9.py"})
    q = _queue(R, [snap], None)
    ran = _runs(R, monkeypatch, q)
    logs = []
    assert q.run_once(log=logs.append) == 0
    assert ran == [], "a box without the file must not claim the job"
    assert snap.reference.updates == [], "the doc stays queued and untouched"
    line = [s for s in logs if s.startswith("[code]")]
    assert len(line) == 1, logs
    assert "ORB_9_9.py" in line[0] and "not on disk" in line[0]
    assert "queued" in line[0]


def test_a_box_that_has_the_file_claims_as_before(R, monkeypatch, tmp_path):
    f = tmp_path / "ORB_3_0.py"
    f.write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    _strategies(monkeypatch, str(f))
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ", "strategy": "ORB_3_0.py"})
    q = _queue(R, [snap], None)
    _runs(R, monkeypatch, q)
    logs = []
    q.run_once(log=logs.append)
    assert snap.reference.updates, "the job is claimed"
    assert not [s for s in logs if s.startswith("[code]")]


def test_the_wrong_version_of_the_file_is_as_unrunnable_as_none(R, monkeypatch, tmp_path):
    """A box holding a DIFFERENT build of the file would quietly run the wrong code - the
    worst outcome of the three, because it produces a number instead of an error."""
    f = tmp_path / "NOISE_1_0.py"
    f.write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    _strategies(monkeypatch, str(f), sha="bbbbbbbbbbbbbbbb")
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ",
                  "strategy": "NOISE_1_0.py", "strategy_sha": "aaaaaaaaaaaaaaaa"})
    q = _queue(R, [snap], None)
    ran = _runs(R, monkeypatch, q)
    logs = []
    assert q.run_once(log=logs.append) == 0
    assert ran == [] and snap.reference.updates == []
    line = [s for s in logs if s.startswith("[code]")][0]
    assert "this box has bbbbbbbbbbbb" in line and "queued against aaaaaaaaaaaa" in line


def test_the_matching_sha_claims(R, monkeypatch, tmp_path):
    f = tmp_path / "NOISE_1_0.py"
    f.write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    _strategies(monkeypatch, str(f), sha="aaaaaaaaaaaaaaaaaaaa")
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ",
                  "strategy": "NOISE_1_0.py", "strategy_sha": "aaaaaaaaaaaaaaaaaaaa"})
    q = _queue(R, [snap], None)
    _runs(R, monkeypatch, q)
    logs = []
    q.run_once(log=logs.append)
    assert snap.reference.updates
    assert not [s for s in logs if s.startswith("[code]")]


def test_no_sha_on_the_job_is_not_a_reason_to_refuse(R, monkeypatch, tmp_path):
    """Most jobs carry no sha. Presence is then all that can be checked, and that is all
    the guard may demand - refusing unstamped work would stop the whole queue."""
    f = tmp_path / "TTM_2_9.py"
    f.write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    _strategies(monkeypatch, str(f), sha="deadbeefdeadbeef")
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ", "strategy": "TTM_2_9.py"})
    q = _queue(R, [snap], None)
    _runs(R, monkeypatch, q)
    q.run_once(log=lambda *_a: None)
    assert snap.reference.updates


def test_the_line_is_throttled_to_once_per_job_per_ten_minutes(R, monkeypatch, tmp_path):
    _strategies(monkeypatch, str(tmp_path / "GONE.py"))
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ", "strategy": "GONE.py"})
    q = _queue(R, [snap], None)
    _runs(R, monkeypatch, q)
    first, second = [], []
    q.run_once(log=first.append)
    q.run_once(log=second.append)
    assert [s for s in first if s.startswith("[code]")]
    assert not [s for s in second if s.startswith("[code]")]


def test_a_book_is_not_checked_against_one_file(R, monkeypatch, tmp_path):
    """A BOOK's "strategy" is the book NAME and its params are a leg list - there is no one
    file to look for, exactly as the blotter code already notes."""
    _strategies(monkeypatch, str(tmp_path / "nope.py"))
    snap = _Snap({"status": "queued", "type": "book", "instrument": "NQ", "strategy": "BOOK #463"})
    q = _queue(R, [snap], None)
    _runs(R, monkeypatch, q)
    logs = []
    q.run_once(log=logs.append)
    assert snap.reference.updates, "a book is still claimed"
    assert not [s for s in logs if s.startswith("[code]")]


def test_a_research_beacon_is_left_to_its_driver(R, monkeypatch, tmp_path):
    """A beacon is a dial for a local driver and has no strategy file at all - MANAGER #118.
    It must keep going down its own path, not be re-labelled a missing-code skip."""
    _strategies(monkeypatch, str(tmp_path / "QWEN LAB 7.py"))
    snap = _Snap({"status": "queued", "type": "research", "instrument": "NQ",
                  "strategy": "QWEN LAB 7.py"})
    q = _queue(R, [snap], None)
    _runs(R, monkeypatch, q)
    logs = []
    q.run_once(log=logs.append)
    assert not [s for s in logs if s.startswith("[code]")], \
        "a beacon has its own handling further up and must not reach this guard"


def test_a_read_error_does_not_starve_the_queue(R, monkeypatch, tmp_path):
    f = tmp_path / "ORB_3_0.py"
    f.write_text("x\n", encoding="utf-8")
    import augur_engine.strategies as S
    monkeypatch.setattr(S, "strategy_path", lambda n: str(f), raising=False)

    def _boom(_p):
        raise OSError("file locked")
    monkeypatch.setattr(S, "strategy_file_sha", _boom, raising=False)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ",
                  "strategy": "ORB_3_0.py", "strategy_sha": "aaaa"})
    q = _queue(R, [snap], None)
    _runs(R, monkeypatch, q)
    logs = []
    q.run_once(log=logs.append)
    assert snap.reference.updates, "an unreadable file must not refuse the work"
    assert any("strategy check skipped" in s for s in logs)


def test_the_guard_sits_before_the_claim_write():
    import io
    import api.runner as Rr
    src = io.open(Rr.__file__, encoding="utf-8").read()
    assert src.index("THE SAME GUARD FOR THE CODE") < \
        src.index('ref.update({"status": "running", "progress": 0,')


def test_strategy_path_resolves_exactly_where_the_loader_looks():
    """If the two ever disagree the guard is worse than nothing: it would refuse jobs whose
    file is right there, or pass jobs whose file is not."""
    from augur_engine.strategies import strategy_path, _resolve
    for n in ("ORB_3_0", "ORB_3_0.py", "NOISE_1_0.py"):
        assert strategy_path(n) == _resolve(n)
