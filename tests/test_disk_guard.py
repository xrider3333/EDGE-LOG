"""The pre-claim guard asks the DISK, not the registry (2026-11-18 incident).

What happened: desktop worker 7 claimed two gate_validate jobs it could not run - GLD
(MISC_GLDNIGHT_1_0) and TLT (MISC_AUCSHORT_1_0) - and both ended "no result (0 trades or
invalid window)" with no run record. The data guard shipped that morning had passed them,
because find_master answers from the master REGISTRY (optimizer_history.db, an untracked
local file that can list masters whose CSV is not on this machine) while the CSVs were not
on that box. The strategies' pinned .npz side panels were missing too, and by their own
design a missing panel returns None rather than guessing.

Both failures are silent in the same way: a box with no data and a strategy that simply did
not trade both report zero trades. That is why these have to be caught before the claim.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_quiet import _runner, _queue, _Snap          # noqa: E402  (shared harness)

from augur_engine.data import master_file, master_on_disk
from augur_engine.strategies import strategy_panels


# ── master_on_disk ─────────────────────────────────────────────────────────────────────
def test_a_registry_row_whose_csv_is_absent_is_not_on_disk(tmp_path, monkeypatch):
    import augur_engine.data as D
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    assert master_on_disk({"id": 7, "filename": "master_90ca117d.csv"}) is False


def test_a_row_whose_csv_is_there_is_on_disk(tmp_path, monkeypatch):
    import augur_engine.data as D
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    (tmp_path / "m.csv").write_text("t,o,h,l,c\n1,2,3,4,5\n", encoding="utf-8")
    assert master_on_disk({"id": 1, "filename": "m.csv"}) is True


def test_an_empty_csv_does_not_count(tmp_path, monkeypatch):
    """A zero-byte file is the shape a half-finished copy or a failed sync leaves behind."""
    import augur_engine.data as D
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    (tmp_path / "m.csv").write_text("", encoding="utf-8")
    assert master_on_disk({"id": 1, "filename": "m.csv"}) is False


@pytest.mark.parametrize("row", [None, {}, {"id": 3}, {"filename": ""}])
def test_a_row_naming_no_file_is_not_on_disk(row):
    assert master_on_disk(row) is False
    assert master_file(row) is None


def test_the_path_is_taken_as_a_basename_under_uploads(tmp_path, monkeypatch):
    """A registry copied from another box can carry a path from that box - only the name
    travels, so the lookup must be under THIS box's uploads folder."""
    import augur_engine.data as D
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    got = master_file({"filename": "D:/someone/elses/disk/master_abc.csv"})
    assert got == os.path.join(str(tmp_path), "master_abc.csv")


# ── the panels a strategy names ────────────────────────────────────────────────────────
def test_the_panel_path_is_read_without_importing_the_strategy():
    """Reading it by import would run the module body and the plugin gate - on a box that
    may not be able to run that file at all, and before the job is even claimed."""
    got = strategy_panels("MISC_AUCSHORT_1_0.py")
    assert got and got[0].endswith("aucshort_panel_v1.npz")
    assert strategy_panels("MISC_GLDNIGHT_1_0.py")[0].endswith("gldnight_panel_v1.npz")


def test_a_strategy_with_no_panel_names_none():
    assert strategy_panels("ORB_3_0.py") == []


def test_a_file_that_is_not_there_names_none():
    assert strategy_panels("NO_SUCH_STRATEGY_9_9.py") == []


# ── the guard, in the claim path ───────────────────────────────────────────────────────
@pytest.fixture
def R(monkeypatch):
    r = _runner()
    monkeypatch.setattr(r, "_psutil", None)
    return r


def _claims(snap):
    """The claim write only - a sha stamp is not a claim. The primary stamps the build it
    holds before it judges the data, which is right: it HAS the strategy file, and the stamp
    is what lets the next box tell a missing file from a wrong build."""
    return [u for u in snap.reference.updates if (u or {}).get("status") == "running"]


def _no_run(R, monkeypatch, q):
    ran = []
    monkeypatch.setattr(R, "process_job", lambda job, cb=None: ran.append(job))
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    return ran


def test_the_gld_job_is_left_queued_when_the_registry_has_the_row_but_not_the_file(R, monkeypatch, tmp_path):
    """The incident itself: the row is there, the CSV is not, and the box must not claim."""
    monkeypatch.setattr(R.ae, "find_master",
                        lambda *a, **k: {"id": 42, "filename": "master_90ca117d.csv"})
    import augur_engine.data as D
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))          # empty: no CSV here
    snap = _Snap({"status": "queued", "type": "gate_validate", "instrument": "GLD",
                  "timeframe": "5m", "session": "rth", "source": "alpaca_split_rth",
                  "strategy": "MISC_GLDNIGHT_1_0.py"})
    q = _queue(R, [snap], None)
    ran = _no_run(R, monkeypatch, q)
    logs = []
    assert q.run_once(log=logs.append) == 0
    assert ran == [] and _claims(snap) == []
    line = [s for s in logs if s.startswith("[data]")]
    assert len(line) == 1, logs
    assert "master_90ca117d.csv" in line[0] and "not on this disk" in line[0]
    assert "registry row 42" in line[0], "say WHICH row lied, so the registry can be fixed"


def test_a_gate_validate_with_the_file_present_is_claimed(R, monkeypatch, tmp_path):
    """gate_validate was never excluded - proving the type is not the thing being judged."""
    monkeypatch.setattr(R.ae, "find_master", lambda *a, **k: {"id": 1, "filename": "m.csv"})
    import augur_engine.data as D
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    (tmp_path / "m.csv").write_text("t\n1\n", encoding="utf-8")
    import augur_engine.strategies as S
    monkeypatch.setattr(S, "strategy_path", lambda n: str(tmp_path / "S.py"), raising=False)
    monkeypatch.setattr(S, "strategy_panels", lambda p: [], raising=False)
    (tmp_path / "S.py").write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    snap = _Snap({"status": "queued", "type": "gate_validate", "instrument": "GLD",
                  "strategy": "S.py"})
    q = _queue(R, [snap], None)
    monkeypatch.setattr(R, "process_job",
                        lambda job, cb=None: {"status": "error", "error": "x", "finishedAt": 1.0})
    monkeypatch.setattr(q, "_save_job_doc", lambda r, patch, log=print: None)
    logs = []
    q.run_once(log=logs.append)
    assert _claims(snap), "a box holding the data still claims the job"
    assert not [s for s in logs if s.startswith("[data]") or s.startswith("[code]")]


def test_a_missing_side_panel_leaves_the_job_queued(R, monkeypatch, tmp_path):
    monkeypatch.setattr(R.ae, "find_master", lambda *a, **k: {"id": 1, "filename": "m.csv"})
    import augur_engine.data as D
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    (tmp_path / "m.csv").write_text("t\n1\n", encoding="utf-8")
    (tmp_path / "S.py").write_text("STRATEGY_NAME='x'\n", encoding="utf-8")
    import augur_engine.strategies as S
    monkeypatch.setattr(S, "strategy_path", lambda n: str(tmp_path / "S.py"), raising=False)
    monkeypatch.setattr(S, "strategy_panels",
                        lambda p: [str(tmp_path / "aucshort_panel_v1.npz"),     # not written: missing
                                   str(tmp_path / "there.npz")], raising=False)
    (tmp_path / "there.npz").write_text("x", encoding="utf-8")
    snap = _Snap({"status": "queued", "type": "gate_validate", "instrument": "TLT",
                  "strategy": "S.py"})
    q = _queue(R, [snap], None)
    ran = _no_run(R, monkeypatch, q)
    logs = []
    assert q.run_once(log=logs.append) == 0
    assert ran == [] and _claims(snap) == []
    line = [s for s in logs if s.startswith("[code]")][0]
    assert "pinned side panel" in line and "aucshort_panel_v1.npz" in line
    assert "there.npz" not in line, "name only the panels that are MISSING"


def test_both_guards_still_run_before_the_claim_write():
    import io
    import api.runner as Rr
    src = io.open(Rr.__file__, encoding="utf-8").read()
    claim = src.index('ref.update({"status": "running", "progress": 0,')
    assert src.index("THE REGISTRY ROW IS NOT THE FILE") < claim
    assert src.index("AND ITS PINNED SIDE PANEL") < claim
