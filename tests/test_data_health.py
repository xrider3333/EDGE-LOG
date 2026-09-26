"""Unit tests for api.data_health -- the NT-capture / master-freshness watchdog.

WHY (2026-09-26): NQ_1m.csv and NQ_1s.csv were flagged ~44 days stale. Both were written
by dedicated NQ 1-Minute / 1-Second charts that closed in the 2026-08-11 NT outage and
were never reopened -- only the 10s chart capture came back. Nothing live reads either
file any more: the production NQ 1m master (augur_uploads/NOADJ_NQ_1m_RTH.csv, read by
the ENGUQ_1M_*.py strategies) is Yahoo/Databento-fed, and tools/backfill_1m_from_10s.py
derives 1m bars from the live 10s capture instead. So they are RETIRED from the active
watch (NT_RETIRED) rather than removed outright: still reported for visibility, with a
note, but never counted as a "problem". These tests pin that retirement.

Never touches C:\\EdgeLog -- every test points NT_OHLC_DIR at tmp_path via monkeypatch.
"""
import os
import time

from api import data_health as H


def test_nt_watch_no_longer_includes_the_retired_nq_1m_1s_files():
    assert "NQ_1m.csv" not in H.NT_WATCH
    assert "NQ_1s.csv" not in H.NT_WATCH
    assert set(H.NT_RETIRED) == {"NQ_1m.csv", "NQ_1s.csv"}
    # still watching the files that matter
    assert "NQ_10s.csv" in H.NT_WATCH
    assert "ES_10s.csv" in H.NT_WATCH


def test_nt_capture_reports_retired_files_but_never_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "NT_OHLC_DIR", str(tmp_path))
    # a genuinely ancient retired file on disk
    old = tmp_path / "NQ_1m.csv"
    old.write_text("time,open,high,low,close\n")
    old_ts = time.time() - 60 * 60 * 24 * 44   # 44 days old
    os.utime(old, (old_ts, old_ts))
    # NQ_1s.csv left missing entirely -- also must not alarm
    (tmp_path / "NQ_10s.csv").write_text("time,open,high,low,close\n")   # fresh

    entries = {e["name"]: e for e in H._nt_capture()}

    assert entries["NQ_1m.csv"]["retired"] is True
    assert entries["NQ_1m.csv"]["present"] is True
    assert entries["NQ_1m.csv"]["stale"] is False
    assert "note" in entries["NQ_1m.csv"]

    assert entries["NQ_1s.csv"]["retired"] is True
    assert entries["NQ_1s.csv"]["present"] is False
    assert entries["NQ_1s.csv"]["stale"] is False
    assert "note" in entries["NQ_1s.csv"]

    # the active watch is unaffected: still detects a genuinely missing NQ_10s.csv
    assert entries["NQ_10s.csv"]["stale"] is False


def test_nt_capture_still_flags_a_stale_active_file(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "NT_OHLC_DIR", str(tmp_path))
    stale = tmp_path / "NQ_10s.csv"
    stale.write_text("time,open,high,low,close\n")
    old_ts = time.time() - 60 * 60 * 5   # 5 hours old > STALE_NT_MIN (180 min)
    os.utime(stale, (old_ts, old_ts))

    entries = {e["name"]: e for e in H._nt_capture()}
    assert entries["NQ_10s.csv"]["stale"] is True
    assert "retired" not in entries["NQ_10s.csv"]


def test_check_never_reports_a_problem_for_retired_files(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "NT_OHLC_DIR", str(tmp_path))
    monkeypatch.setattr(H, "_weekend", lambda ts: False)   # force a weekday check
    monkeypatch.setattr(H, "_masters", lambda: [])
    # NQ_1m.csv / NQ_1s.csv both absent -- would have been "NT capture missing" pre-fix
    # NQ_10s.csv / ES_10s.csv also absent -- these SHOULD still raise
    problems = H.check()["problems"]

    assert not any("NQ_1m.csv" in p for p in problems)
    assert not any("NQ_1s.csv" in p for p in problems)
    assert any("NQ_10s.csv" in p for p in problems)
    assert any("ES_10s.csv" in p for p in problems)


def test_check_ok_when_only_retired_files_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "NT_OHLC_DIR", str(tmp_path))
    monkeypatch.setattr(H, "_weekend", lambda ts: False)
    monkeypatch.setattr(H, "_masters", lambda: [])
    (tmp_path / "NQ_10s.csv").write_text("time,open,high,low,close\n")
    (tmp_path / "ES_10s.csv").write_text("time,open,high,low,close\n")
    # NQ_1m.csv / NQ_1s.csv absent (retired) -- must not break ok=True

    rep = H.check()
    assert rep["ok"] is True
    assert rep["problems"] == []
    # still surfaced in the report, just marked retired
    retired_names = {e["name"] for e in rep["nt_capture"] if e.get("retired")}
    assert retired_names == {"NQ_1m.csv", "NQ_1s.csv"}
