"""Nightly reprice: a failed run is not "done" (sweep 2026-10-05, finding 27).

Before: api/qqq_exec.py's _maybe_run_reprice stamped reprice_done_date BEFORE running
tools/qqq_reprice.py, ignored its exit code, and the tool exited 0 even on an error -- a failed
run left the day's real-price P&L and slippage missing with no retry and nothing said. Now the
date is stamped only after exit code 0, a failure is retried once from 19:00 ET, a second
failure pushes ONE alert, and the tool exits non-zero on an error. No real subprocess runs:
subprocess.run is a fake.
"""
import datetime as dt
import os
import subprocess
import sys

import pytest

from api import qqq_exec as qe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import tools.qqq_reprice as R  # noqa: E402

ET = qe._NY
NOOP = lambda *a, **k: None


def at(h, m, day=dt.date(2026, 10, 5)):      # a Monday
    return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=ET)


class Runs:
    def __init__(self, rcs):
        self.rcs = list(rcs)
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        rc = self.rcs.pop(0) if self.rcs else 0
        if isinstance(rc, BaseException):
            raise rc

        class P:
            returncode = rc
        return P()


@pytest.fixture
def pushes(monkeypatch):
    out = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        out.append((msg, title, priority)))
    return out


def _kinds(state):
    return [e["kind"] for e in state.get("events", [])]


def test_a_failed_run_leaves_the_date_unstamped_retries_once_then_alerts_once(monkeypatch, pushes):
    runs = Runs([1, 1])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(16, 15), log=NOOP)
    assert runs.calls == [], "not before 16:20"
    qe._maybe_run_reprice(state, at(16, 20), log=NOOP)
    assert len(runs.calls) == 1
    assert state.get("reprice_done_date") != "2026-10-05", "a failed run is not done"
    assert state["reprice_fail"]["tries"] == 1 and "exit code 1" in state["reprice_fail"]["last_error"]
    assert _kinds(state) == ["reprice_failed"] and pushes == []
    # every tick until 19:00 does nothing
    for t in (at(16, 21), at(17, 30), at(18, 59)):
        qe._maybe_run_reprice(state, t, log=NOOP)
    assert len(runs.calls) == 1
    # the one evening retry
    qe._maybe_run_reprice(state, at(19, 0), log=NOOP)
    assert len(runs.calls) == 2
    assert state.get("reprice_done_date") != "2026-10-05"
    assert len(pushes) == 1 and pushes[0][1] == "QQQ book: re-price failed"
    # Do: nothing (it catches up by itself) -> information, low (api/ntfy_push PRIORITY)
    assert "failed twice" in pushes[0][0] and pushes[0][2] == "low"
    from api import ntfy_push
    assert ntfy_push.lint({"title": pushes[0][1], "message": pushes[0][0],
                           "priority": pushes[0][2]}) == []
    assert "exit code" not in pushes[0][0], "the error detail stays in the log and the event"
    assert _kinds(state) == ["reprice_failed", "reprice_failed"]
    # and nothing more that evening, however many ticks
    for t in (at(19, 1), at(20, 0), at(23, 50)):
        qe._maybe_run_reprice(state, t, log=NOOP)
    assert len(runs.calls) == 2 and len(pushes) == 1


def test_success_stamps_the_date_and_runs_once(monkeypatch, pushes):
    runs = Runs([0])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(16, 20), log=NOOP)
    qe._maybe_run_reprice(state, at(16, 21), log=NOOP)
    assert len(runs.calls) == 1 and state["reprice_done_date"] == "2026-10-05"
    assert "reprice_fail" not in state and _kinds(state) == ["reprice"] and pushes == []


def test_the_retry_succeeds_quietly(monkeypatch, pushes):
    runs = Runs([2, 0])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(16, 20), log=NOOP)
    qe._maybe_run_reprice(state, at(19, 5), log=NOOP)
    assert state["reprice_done_date"] == "2026-10-05" and "reprice_fail" not in state
    assert pushes == [] and _kinds(state) == ["reprice_failed", "reprice"]
    assert "on try 2" in state["events"][-1]["text"]


def test_a_timeout_is_a_failure(monkeypatch, pushes):
    runs = Runs([subprocess.TimeoutExpired(["x"], 120)])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(16, 20), log=NOOP)
    assert state.get("reprice_done_date") is None
    assert "timed out" in state["reprice_fail"]["last_error"]


def test_a_late_first_try_waits_30_min_for_its_retry(monkeypatch, pushes):
    runs = Runs([1, 1])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(21, 0), log=NOOP)        # the executor was down at 16:20
    qe._maybe_run_reprice(state, at(21, 10), log=NOOP)
    assert len(runs.calls) == 1
    qe._maybe_run_reprice(state, at(21, 31), log=NOOP)
    assert len(runs.calls) == 2 and len(pushes) == 1


def test_a_first_try_too_late_for_a_retry_alerts_at_once(monkeypatch, pushes):
    """A first try that fails after ~23:30 ET has no room for its 30-min-later retry before the
    per-date record rolls over at midnight: it used to be dropped silently; now it pages once."""
    runs = Runs([1])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(23, 40), log=NOOP)
    assert len(runs.calls) == 1 and len(pushes) == 1
    assert "too late to try again" in pushes[0][0]
    assert state["reprice_fail"]["alerted"] is True
    qe._maybe_run_reprice(state, at(23, 55), log=NOOP)
    assert len(runs.calls) == 1 and len(pushes) == 1


def test_a_first_try_at_2329_still_gets_its_retry(monkeypatch, pushes):
    runs = Runs([1, 1])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(23, 29), log=NOOP)
    assert pushes == []
    qe._maybe_run_reprice(state, at(23, 59), log=NOOP)
    assert len(runs.calls) == 2 and len(pushes) == 1 and "failed twice" in pushes[0][0]


def test_the_next_weekday_starts_clean(monkeypatch, pushes):
    runs = Runs([1, 1, 0])
    monkeypatch.setattr(qe.subprocess, "run", runs)
    state = {}
    qe._maybe_run_reprice(state, at(16, 20), log=NOOP)
    qe._maybe_run_reprice(state, at(19, 0), log=NOOP)
    tue = dt.date(2026, 10, 6)
    qe._maybe_run_reprice(state, at(16, 20, tue), log=NOOP)
    assert len(runs.calls) == 3 and state["reprice_done_date"] == "2026-10-06"
    assert "reprice_fail" not in state


# -- tools/qqq_reprice.py exit codes ------------------------------------------------------------
def test_reprice_tool_exits_1_on_an_unexpected_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("sidecar locked")
    monkeypatch.setattr(R, "run", boom)
    monkeypatch.setattr(sys, "argv", ["qqq_reprice.py", "--apply"])
    with pytest.raises(SystemExit) as ex:
        R.main()
    assert ex.value.code == 1, "it used to exit 0, which read as done"


def test_reprice_tool_returns_2_when_the_data_source_is_down(tmp_path, monkeypatch):
    import csv
    trades = tmp_path / "trades.csv"
    with open(trades, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["leg", "entry_ts", "exit_ts", "side", "shares",
                                          "entry_px", "exit_px", "pnl"])
        w.writeheader()
        w.writerow({"leg": "NOISE", "entry_ts": "2026-10-05 12:30:16",
                    "exit_ts": "2026-10-05 15:58:05", "side": "long", "shares": "5",
                    "entry_px": "490", "exit_px": "495", "pnl": "25"})
    cfg = tmp_path / "config.json"
    cfg.write_text('{"slippage_per_share": 0.01}', encoding="utf-8")
    monkeypatch.setattr(R, "_now_et", lambda: dt.datetime(2026, 10, 5, 16, 20))
    monkeypatch.setattr(R, "fetch_webull_rest_1m", lambda **k: {})

    def down(day, log=print):
        raise R.NetworkUnavailable("ConnectionError: no route")
    monkeypatch.setattr(R, "fetch_day_bars", down)
    rc = R.run(str(trades), str(tmp_path / "reprice.csv"), str(cfg), apply=True,
               stream_home=str(tmp_path / "no_home"),
               webull_keys_path=str(tmp_path / "no_keys.json"), log=NOOP)
    assert rc == 2
    assert not os.path.exists(tmp_path / "reprice.csv")
