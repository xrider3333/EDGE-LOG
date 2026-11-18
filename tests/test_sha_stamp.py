"""Every job gets the sha of the strategy build it was queued against (2026-11-18).

v90.53 taught the pre-claim guard to refuse a job whose strategy file this box lacks, and
to refuse one whose file is a DIFFERENT build - but only if the job carried a sha, and
nothing wrote one. MANAGER's GO: write it. A box missing the file fails loudly; a box with
the wrong build hands back a number and nothing in the result says it was not the code the
run was meant to test.

Two ways in, because there is no single place jobs are queued:
  * stamp_strategy_sha(job) for a queue script, called in the breath before writing the doc,
  * and the PRIMARY runner stamping any job it sees without one - which is what covers the
    Builder (a browser, with no access to the PC's disk) and the 93 scripts that write the
    doc their own way.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_quiet import _runner, _queue, _Snap          # noqa: E402  (shared harness)

from augur_engine.strategies import stamp_strategy_sha, strategy_file_sha


# ── the helper a queue script calls ────────────────────────────────────────────────────
def _file(tmp_path, name="ORB_3_0.py", body="STRATEGY_NAME='x'\n"):
    f = tmp_path / name
    f.write_text(body, encoding="utf-8")
    return f


def _point_at(monkeypatch, path):
    import augur_engine.strategies as S
    monkeypatch.setattr(S, "_resolve", lambda n: str(path))


def test_the_helper_stamps_the_sha_of_the_file_on_this_box(monkeypatch, tmp_path):
    f = _file(tmp_path)
    _point_at(monkeypatch, f)
    job = {"type": "backtest", "strategy": "ORB_3_0.py"}
    sha = stamp_strategy_sha(job)
    assert sha and job["strategy_sha"] == sha
    assert sha == strategy_file_sha(str(f)), "it must be the content hash, not a guess"


def test_a_different_build_of_the_same_name_gets_a_different_sha(monkeypatch, tmp_path):
    """The whole point: same filename, different code, and the stamp has to tell them apart."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    fa = _file(a, body="STRATEGY_NAME='v1'\n")
    fb = _file(b, body="STRATEGY_NAME='v2'\n")
    j1, j2 = {"type": "backtest", "strategy": "ORB_3_0.py"}, {"type": "backtest", "strategy": "ORB_3_0.py"}
    _point_at(monkeypatch, fa); stamp_strategy_sha(j1)
    _point_at(monkeypatch, fb); stamp_strategy_sha(j2)
    assert j1["strategy_sha"] != j2["strategy_sha"]


def test_a_sha_already_on_the_job_is_never_overwritten(monkeypatch, tmp_path):
    """Whoever queued the job knew which build they meant - a later box must not re-point it
    at its own copy, which would turn a wrong-build refusal into a silent wrong-build run."""
    _point_at(monkeypatch, _file(tmp_path))
    job = {"type": "backtest", "strategy": "ORB_3_0.py", "strategy_sha": "aaaaaaaaaaaa"}
    assert stamp_strategy_sha(job) is None
    assert job["strategy_sha"] == "aaaaaaaaaaaa"


@pytest.mark.parametrize("job", [
    {"type": "book", "strategy": "BOOK #463"},          # a NAME and a leg list, not a file
    {"type": "research", "strategy": "QWEN LAB 7.py"},  # a beacon, no file at all
    {"type": "backtest"},                               # no strategy
    {},
    None,
])
def test_there_is_nothing_to_stamp_on_these(monkeypatch, tmp_path, job):
    _point_at(monkeypatch, _file(tmp_path))
    assert stamp_strategy_sha(job) is None


def test_a_file_this_box_does_not_have_is_not_stamped(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path / "GONE.py")
    job = {"type": "backtest", "strategy": "GONE.py"}
    assert stamp_strategy_sha(job) is None
    assert "strategy_sha" not in job


def test_the_helper_never_raises(monkeypatch, tmp_path):
    """It is called in the breath before queueing. It must not give a queue script a new way
    to fail - an unstamped job is claimed on presence, exactly as before."""
    import augur_engine.strategies as S

    def _boom(_n):
        raise OSError("nope")
    monkeypatch.setattr(S, "_resolve", _boom)
    job = {"type": "backtest", "strategy": "ORB_3_0.py"}
    assert stamp_strategy_sha(job) is None
    assert job == {"type": "backtest", "strategy": "ORB_3_0.py"}


# ── the primary runner stamping what it sees ───────────────────────────────────────────
@pytest.fixture
def R(monkeypatch):
    r = _runner()
    monkeypatch.setattr(r, "_psutil", None)
    monkeypatch.setattr(r.ae, "find_master", lambda *a, **k: {"instrument": "NQ", "date_to": "2026-11-17"})
    # the DATA guard is not under test in this file: give every job a master that is
    # really there, so what fails here can only be the code guard (2026-11-18: the data
    # guard now stats the master file, not just its registry row).
    import augur_engine.data as _D
    monkeypatch.setattr(_D, "master_on_disk", lambda row: True)
    return r


def _resolver(monkeypatch, path, sha="ccccccccccccffff"):
    import augur_engine.strategies as S
    monkeypatch.setattr(S, "strategy_path", lambda n: str(path), raising=False)
    monkeypatch.setattr(S, "strategy_file_sha", lambda p: sha, raising=False)


def test_the_primary_stamps_a_job_that_arrived_without_one(R, monkeypatch, tmp_path):
    f = _file(tmp_path)
    _resolver(monkeypatch, f)
    monkeypatch.setattr(R, "_IS_WORKER", False, raising=False)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ", "strategy": "ORB_3_0.py"})
    q = _queue(R, [snap], None)
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: {"status": "error", "error": "x", "finishedAt": 1.0})
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    logs = []
    q.run_once(log=logs.append)
    stamped = [u for u in snap.reference.updates if "strategy_sha" in (u or {})]
    assert stamped, "the primary must write the sha onto the doc"
    assert stamped[0]["strategy_sha"] == "ccccccccccccffff"
    assert any("stamped" in s for s in logs)
    assert snap.reference.updates, "and the job is still claimed and run"


def test_a_worker_never_stamps(R, monkeypatch, tmp_path):
    """A worker that has not pulled would brand its own stale build as the intended one -
    the exact mistake the sha exists to catch."""
    f = _file(tmp_path)
    _resolver(monkeypatch, f)
    monkeypatch.setattr(R, "_IS_WORKER", True, raising=False)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ", "strategy": "ORB_3_0.py"})
    q = _queue(R, [snap], None)
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: {"status": "error", "error": "x", "finishedAt": 1.0})
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    q.run_once(log=lambda *_a: None)
    assert not [u for u in snap.reference.updates if "strategy_sha" in (u or {})]


def test_a_stamp_write_that_fails_does_not_stop_the_job(R, monkeypatch, tmp_path):
    f = _file(tmp_path)
    _resolver(monkeypatch, f)
    monkeypatch.setattr(R, "_IS_WORKER", False, raising=False)
    snap = _Snap({"status": "queued", "type": "backtest", "instrument": "NQ", "strategy": "ORB_3_0.py"})
    q = _queue(R, [snap], None)
    real = snap.reference.update

    def _flaky(patch, **kw):
        if "strategy_sha" in (patch or {}):
            raise RuntimeError("write rejected")
        return real(patch, **kw)
    monkeypatch.setattr(snap.reference, "update", _flaky)
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: {"status": "error", "error": "x", "finishedAt": 1.0})
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    logs = []
    q.run_once(log=logs.append)
    assert any("could not stamp" in s for s in logs)
    assert snap.reference.updates, "the job is claimed on presence, as before today"


def test_the_stamp_sits_before_the_claim_so_the_sha_is_on_the_doc_first():
    import io
    import api.runner as Rr
    src = io.open(Rr.__file__, encoding="utf-8").read()
    assert src.index("STAMP IT ON FIRST SIGHT") < \
        src.index('ref.update({"status": "running", "progress": 0,')
