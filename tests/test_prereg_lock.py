"""tools/prereg_lock.py + the run_record verdict gate (board C8: prereg locked before a run; no verdict without it).

Offline: EDGELOG_HOME and EDGELOG_RUN_RECORDS are tmp_path, so the real C:/EdgeLog/prereg_locks.jsonl is never touched.
"""
import datetime
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import prereg_lock as pl  # noqa: E402
from tools import run_record as rr  # noqa: E402
from tools import run_records_sync as rs  # noqa: E402

UTC = datetime.timezone.utc
LOCK_T = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
SHA = "a" * 40


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EDGELOG_RUN_RECORDS", str(tmp_path / "rr"))
    monkeypatch.setenv("EDGELOG_HOST_ID", "test-box")
    return tmp_path


@pytest.fixture
def prereg(home):
    p = home / "PREREG_test_r1.md"
    p.write_bytes(b"# test r1\nPASS if ROC@30k > 10\n")
    return p


def _record(**kw):
    nums = dict(roc30k=12.0, dd5=4000.0, ddpct=5.0, sortino=1.2, one_episode=False)
    return rr.build_record("TEST", "lane", "WF", strategy="s", family="F", instrument="NQ", timeframe="5m",
                           numbers=nums, trades=100, sha=SHA, **kw)


# ---------------------------------------------------------------- lock / check / amend
def test_lock_then_check_reads_locked(prereg):
    entry, msg = pl.lock(str(prereg), now=LOCK_T)
    assert entry["id"] == "PREREG_test_r1" and entry["version"] == 1 and len(entry["sha256"]) == 64
    assert "LOCKED" in msg
    assert pl.check("PREREG_test_r1")[0] == "LOCKED"
    assert pl.check(str(prereg))[0] == "LOCKED"
    assert pl.check("NOPE")[0] == "NOT LOCKED"


def test_crlf_is_the_same_prereg(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    prereg.write_bytes(prereg.read_bytes().replace(b"\n", b"\r\n"))
    assert pl.check("PREREG_test_r1")[0] == "LOCKED"


def test_relock_unchanged_is_a_noop(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    pl.lock(str(prereg))
    assert len(pl.read_locks()) == 1


def test_changed_file_is_refused_without_amend_and_old_hash_shown(prereg):
    e1, _ = pl.lock(str(prereg), now=LOCK_T)
    prereg.write_text("# test r1\nPASS if ROC@30k > 5\n", encoding="utf-8")
    assert pl.check("PREREG_test_r1")[0] == "CHANGED"
    with pytest.raises(pl.PreregError, match=e1["sha256"]):
        pl.lock(str(prereg))
    assert len(pl.read_locks()) == 1


def test_amend_appends_a_version_and_keeps_the_old(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    prereg.write_text("changed\n", encoding="utf-8")
    e2, _ = pl.lock(str(prereg), amend="typo in threshold")
    rows = pl.read_locks()
    assert [r["version"] for r in rows] == [1, 2] and rows[1]["reason"] == "typo in threshold"
    assert rows[0]["sha256"] != rows[1]["sha256"]
    assert pl.check("PREREG_test_r1")[0] == "LOCKED"


def test_cli_lock_check_list(prereg, capsys):
    assert pl.main(["lock", str(prereg)]) == 0
    assert pl.main(["check", "PREREG_test_r1"]) == 0
    assert pl.main(["list"]) == 0
    assert "PREREG_test_r1" in capsys.readouterr().out
    assert pl.main(["check", "UNKNOWN"]) == 1


# ---------------------------------------------------------------- the choke point: run_record.build_record
def test_no_verdict_record_is_unchanged(home):
    rec = _record()
    assert "verdict" not in rec and "prereg" not in rec
    assert tuple(rec) == rr.FIELDS


def test_verdict_with_locked_prereg_before_run_is_stored(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    rec = _record(verdict="PASS", prereg="PREREG_test_r1", ts="2026-10-20 10:00")
    assert rec["verdict"] == "PASS" and rec["prereg"] == "PREREG_test_r1"


def test_verdict_without_prereg_is_refused(home):
    with pytest.raises(rr.RunRecordError, match="no prereg"):
        _record(verdict="PASS", ts="2026-10-20 10:00")


def test_verdict_with_unlocked_prereg_is_refused(home):
    with pytest.raises(rr.RunRecordError, match="NOT LOCKED|no lock"):
        _record(verdict="DEAD", prereg="PREREG_never", ts="2026-10-20 10:00")


def test_verdict_locked_after_run_start_is_refused(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    with pytest.raises(rr.RunRecordError, match="NOT before the run started"):
        _record(verdict="PASS", prereg="PREREG_test_r1", ts="2026-10-20 10:00", run_start="2026-09-30T00:00:00+00:00")


def test_verdict_with_changed_prereg_is_refused(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    prereg.write_text("moved the goalposts\n", encoding="utf-8")
    with pytest.raises(rr.RunRecordError, match="CHANGED"):
        _record(verdict="PASS", prereg="PREREG_test_r1", ts="2026-10-20 10:00")


def test_amended_prereg_counts_from_the_amend_time(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    prereg.write_text("v2\n", encoding="utf-8")
    pl.lock(str(prereg), amend="fix")                       # amended NOW (2026-10-31-ish or later)
    with pytest.raises(rr.RunRecordError, match="NOT before"):
        _record(verdict="PASS", prereg="PREREG_test_r1", ts="2026-10-20 10:00")


def test_exploratory_downgrades_the_verdict(home):
    rec = _record(verdict="crown", prereg="none - exploratory", ts="2026-10-20 10:00")
    assert rec["verdict"] == "EXPLORATORY" and rec["prereg"] == "none - exploratory"


def test_write_record_forgiving_mode_refuses_with_one_line(home, capsys):
    nums = dict(roc30k=12.0, dd5=4000.0, ddpct=5.0, sortino=1.2, one_episode=False)
    out = rr.write_record("TEST", "lane", "WF", strategy="s", family="F", instrument="NQ", timeframe="5m",
                          numbers=nums, trades=100, sha=SHA, verdict="PASS")
    assert out is None
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and "no prereg" in err[0]
    assert not os.path.exists(os.path.join(str(home), "rr"))


def test_cli_verdict_round_trip(prereg, home):
    pl.lock(str(prereg), now=LOCK_T)
    args = ["--lane", "TEST", "--where", "lane", "--stage", "WF", "--strategy", "s", "--family", "F",
            "--instrument", "NQ", "--timeframe", "5m", "--roc30k", "12", "--dd5", "4000", "--ddpct", "5",
            "--sortino", "1.2", "--one-episode", "false", "--trades", "100", "--sha", SHA,
            "--ts", "2026-10-20 10:00", "--verdict", "HOLDS", "--prereg", "PREREG_test_r1", "--strict"]
    assert rr.main(args) == 0
    files = os.listdir(str(home / "rr"))
    line = json.loads(open(os.path.join(str(home / "rr"), files[0]), encoding="utf-8").readline())
    assert line["verdict"] == "HOLDS"
    assert rr.main(args[:-5] + ["--verdict", "PASS", "--strict"]) == 2


# ---------------------------------------------------------------- the sync accepts the two fields, hash unchanged without them
def test_sync_accepts_verdict_fields_and_keeps_old_hash(prereg):
    pl.lock(str(prereg), now=LOCK_T)
    plain = _record(ts="2026-10-20 10:00")
    with_v = _record(verdict="PASS", prereg="PREREG_test_r1", ts="2026-10-20 10:00")
    vp = rs.validate(plain)
    assert "verdict" not in vp
    vv = rs.validate(with_v)
    assert vv["verdict"] == "PASS" and vv["prereg"] == "PREREG_test_r1"
    assert rs.content_hash(vp) != rs.content_hash(vv)
    bad = dict(with_v)
    del bad["prereg"]
    with pytest.raises(rs.Refusal, match="go together"):
        rs.validate(bad)
