"""tests/test_qqq_exec_stream_window.py -- item B (2026-09-25): the live Webull price
stream now runs only inside a market-hours window instead of starting once at boot and
running all night regardless (root cause of api/webull_stream.py's overnight SDK log
flood -- see that module's item A docstring).

Covers:
  1. _stream_should_run (pure): the exact boundary cases -- 09:28 no, 09:29 yes,
     16:01 yes, 16:03 no, weekend no, a holiday no, a half day stops after 13:02.
  2. _qqq_stream_window_step (the stateful tick-level wiring, fakes for
     _start_qqq_stream/_stop_qqq_stream/_qqq_stream_instance): starts inside the
     window, stops outside it with exactly one log line, is a silent no-op outside
     the window when nothing is running (no per-tick log spam all night), never
     raises, and the 120s start-retry spacing.
  3. An end-to-end round trip with the REAL _start_qqq_stream/_stop_qqq_stream (a fake
     streamer factory -- no thread lifecycle assumptions beyond what
     tests/test_qqq_exec_stream_wiring.py already exercises, no network) proving a
     LATER window's start still works after an EARLIER window's stop -- remember
     _stop_qqq_stream sets stop_requested=True; _start_qqq_stream must reset it.

tests/conftest.py's autouse _isolate_qqq_stream fixture already resets
qe._qqq_stream_state and stubs qe._webull_stream_factory before every test in the
whole suite; test #3 below overrides the factory with its OWN fake, exactly like
tests/test_qqq_exec_stream_wiring.py does.
"""
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe          # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


# All on 2026-09-08 (Tuesday) -- a plain trading day, no holiday/half-day involved.
IN_WINDOW = _et(2026, 9, 8, 10, 0)
OUTSIDE_WINDOW = _et(2026, 9, 8, 20, 0)


@pytest.fixture(autouse=True)
def _clean_stream_state():
    """Belt-and-suspenders alongside conftest's autouse isolation (same pattern as
    tests/test_qqq_exec_stream_wiring.py): guarantee every test in this file starts
    and ends with no streamer registered, even though the round-trip test also stops
    what it started."""
    qe._qqq_stream_state = {"streamer": None, "starting": False, "stop_requested": False}
    yield
    qe._qqq_stream_state = {"streamer": None, "starting": False, "stop_requested": False}


# ── 1. _stream_should_run: pure boundary cases ───────────────────────────────────────────
def test_before_open_is_no():
    assert qe._stream_should_run(_et(2026, 9, 8, 9, 28)) is False


def test_at_open_is_yes():
    assert qe._stream_should_run(_et(2026, 9, 8, 9, 29)) is True


def test_one_minute_before_close_is_yes():
    assert qe._stream_should_run(_et(2026, 9, 8, 16, 1)) is True


def test_past_close_is_no():
    assert qe._stream_should_run(_et(2026, 9, 8, 16, 3)) is False


def test_mid_session_is_yes():
    assert qe._stream_should_run(IN_WINDOW) is True


def test_weekend_is_no():
    # 2026-09-05 is a Saturday (Labor Day, the first Monday of Sept, falls on 09-07).
    assert qe._stream_should_run(_et(2026, 9, 5, 10, 0)) is False


def test_holiday_is_no():
    assert qe._stream_should_run(_et(2026, 9, 7, 10, 0)) is False   # Labor Day


def test_half_day_runs_until_1302_then_stops():
    # 2026-11-27 is the day after Thanksgiving -- a recognised 13:00 ET early close.
    assert qe._stream_should_run(_et(2026, 11, 27, 13, 1)) is True
    assert qe._stream_should_run(_et(2026, 11, 27, 13, 3)) is False


def test_half_day_open_side_is_unchanged():
    # only the CLOSE side narrows on a half day -- the open is always 09:29.
    assert qe._stream_should_run(_et(2026, 11, 27, 9, 28)) is False
    assert qe._stream_should_run(_et(2026, 11, 27, 9, 29)) is True


# ── 2. _qqq_stream_window_step: stateful wiring, fakes for start/stop ────────────────────
def test_inside_window_starts_when_nothing_running(monkeypatch):
    calls = {"start": 0, "stop": 0}
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(qe, "_stop_qqq_stream",
                        lambda log=print: calls.__setitem__("stop", calls["stop"] + 1))

    last = qe._qqq_stream_window_step({}, 0.0, now_et=IN_WINDOW, now_wall=1000.0,
                                      log=lambda *_: None)

    assert calls == {"start": 1, "stop": 0}
    assert last == 1000.0


def test_retry_gate_blocks_a_second_start_within_120s(monkeypatch):
    calls = {"start": 0}
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(qe, "_stop_qqq_stream", lambda log=print: None)

    last = qe._qqq_stream_window_step({}, 0.0, now_et=IN_WINDOW, now_wall=1000.0,
                                      log=lambda *_: None)
    assert calls["start"] == 1
    # 30s later -- still well inside the 120s retry gate, and the fake start() never
    # actually registers a streamer, so a real bug here would call it again.
    last = qe._qqq_stream_window_step({}, last, now_et=IN_WINDOW, now_wall=1030.0,
                                      log=lambda *_: None)
    assert calls["start"] == 1, "must not retry a start attempt inside the 120s gate"
    assert last == 1000.0, "no NEW attempt was made -- the timestamp must not move"


def test_retry_gate_allows_a_new_attempt_after_120s(monkeypatch):
    calls = {"start": 0}
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(qe, "_stop_qqq_stream", lambda log=print: None)

    last = qe._qqq_stream_window_step({}, 0.0, now_et=IN_WINDOW, now_wall=1000.0,
                                      log=lambda *_: None)
    last = qe._qqq_stream_window_step({}, last, now_et=IN_WINDOW, now_wall=1000.0 + 120.0,
                                      log=lambda *_: None)

    assert calls["start"] == 2
    assert last == 1120.0


def test_inside_window_does_not_restart_an_already_running_streamer(monkeypatch):
    calls = {"start": 0}
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: object())   # already running
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(qe, "_stop_qqq_stream", lambda log=print: None)

    qe._qqq_stream_window_step({}, 0.0, now_et=IN_WINDOW, now_wall=1000.0, log=lambda *_: None)

    assert calls["start"] == 0


def test_outside_window_stops_a_running_streamer_and_logs_one_line(monkeypatch):
    calls = {"stop": 0}
    logs = []
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: object())
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: pytest.fail("must not start outside the window"))
    monkeypatch.setattr(qe, "_stop_qqq_stream",
                        lambda log=print: calls.__setitem__("stop", calls["stop"] + 1))

    qe._qqq_stream_window_step({}, 0.0, now_et=OUTSIDE_WINDOW, now_wall=1000.0, log=logs.append)

    assert calls["stop"] == 1
    assert len(logs) == 1
    assert "outside" in logs[0].lower()


def test_outside_window_with_nothing_running_is_a_silent_no_op(monkeypatch):
    """The night-long no-spam case: outside the window with no streamer, this must
    call neither _start_qqq_stream nor _stop_qqq_stream, and log nothing -- calling
    _stop_qqq_stream every tick all night (it's a safe no-op, but a noisy one) would
    just be a smaller version of item A's own log-spam problem."""
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: pytest.fail("must not start"))
    monkeypatch.setattr(qe, "_stop_qqq_stream",
                        lambda log=print: pytest.fail("must not stop"))
    logs = []

    qe._qqq_stream_window_step({}, 0.0, now_et=OUTSIDE_WINDOW, now_wall=1000.0, log=logs.append)

    assert logs == []


def test_window_step_never_raises_when_start_qqq_stream_blows_up(monkeypatch):
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)

    def boom(cfg, log=print):
        raise RuntimeError("simulated: could not build the SDK client")
    monkeypatch.setattr(qe, "_start_qqq_stream", boom)
    logs = []

    last = qe._qqq_stream_window_step({}, 0.0, now_et=IN_WINDOW, now_wall=1000.0, log=logs.append)

    assert last == 1000.0   # the attempt still happened from the caller's perspective
    assert any("stream window step failed" in m for m in logs)


def test_disabled_by_config_flag_still_calls_start_which_itself_refuses(monkeypatch):
    """live_stream_enabled=False is enforced INSIDE _start_qqq_stream (unchanged by
    item B) -- _qqq_stream_window_step must still call it (not duplicate the check),
    so the kill switch keeps working exactly as before."""
    seen_cfg = []
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_start_qqq_stream", lambda cfg, log=print: seen_cfg.append(cfg))

    qe._qqq_stream_window_step({"live_stream_enabled": False}, 0.0, now_et=IN_WINDOW,
                               now_wall=1000.0, log=lambda *_: None)

    assert seen_cfg == [{"live_stream_enabled": False}]


# ── 3. end-to-end round trip: REAL _start_qqq_stream/_stop_qqq_stream ────────────────────
class _FakeStreamer:
    """Records start()/stop(); never touches a thread or the network -- same shape as
    tests/test_qqq_exec_stream_wiring.py's own _FakeStreamer."""
    def __init__(self, symbols=None, log=print, **kwargs):
        self.symbols = symbols
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def _wait_for(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def test_stop_then_a_later_window_start_both_work(monkeypatch):
    """Remember _stop_qqq_stream sets stop_requested=True -- make sure a later
    window's start still works (_start_qqq_stream resets it)."""
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _FakeStreamer)

    last = qe._qqq_stream_window_step({}, 0.0, now_et=IN_WINDOW, now_wall=1000.0,
                                      log=lambda *_: None)
    assert _wait_for(lambda: qe._qqq_stream_instance() is not None)
    first = qe._qqq_stream_instance()
    assert first.started is True

    # market close: outside the window, the running streamer must be stopped
    last = qe._qqq_stream_window_step({}, last, now_et=OUTSIDE_WINDOW, now_wall=1001.0,
                                      log=lambda *_: None)
    assert qe._qqq_stream_instance() is None
    assert first.stopped is True

    # a LATER window (e.g. the next trading day) must still be able to start fresh
    last = qe._qqq_stream_window_step({}, 0.0, now_et=IN_WINDOW, now_wall=2000.0,
                                      log=lambda *_: None)
    assert _wait_for(lambda: qe._qqq_stream_instance() is not None)
    second = qe._qqq_stream_instance()
    assert second is not first
    assert second.started is True
    qe._stop_qqq_stream(log=lambda *_: None)
