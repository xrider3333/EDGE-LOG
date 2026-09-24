"""tools/push_nq_master_to_box.py: the refresh-before-push step (2026-09-24). No network, no
child process -- subprocess.run is faked; the ssh/scp half is exercised live, never here."""
import subprocess
import types

import pytest

from tools import push_nq_master_to_box as P


def _fake_run(returncode=0, stdout="", stderr=""):
    def run(*a, **k):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return run


def test_refresh_reports_the_nq_5m_rth_line(monkeypatch):
    out = ("  NOADJ_ES_5m_RTH.csv: +78 bars -> 1,000 total, now through 2026-09-24\n"
           "  NOADJ_NQ_5m_RTH.csv: +78 bars -> 321,724 total, now through 2026-09-24\n"
           "Done. Non-adj masters extended from Yahoo (free, raw front-month).\n")
    monkeypatch.setattr(P.subprocess, "run", _fake_run(0, out))
    ok, note = P._refresh_master()
    assert ok is True
    assert "NOADJ_NQ_5m_RTH.csv: +78 bars" in note and "ES" not in note


def test_refresh_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(P.subprocess, "run", _fake_run(1, "", "yfinance not installed"))
    ok, note = P._refresh_master()
    assert ok is False and "yfinance" in note

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=600)
    monkeypatch.setattr(P.subprocess, "run", boom)
    ok, note = P._refresh_master()
    assert ok is False and "TimeoutExpired" in note
