"""The runner's main watch loop is watched (api/runner.py LoopWatchdog, 2026-11-18).

The runner can be alive as a process and dead as a service: one blocked call inside the
`while True` and the log just stops, with no line saying so. These tests pin the four
behaviours that make the watchdog trustworthy rather than annoying:

  1. a ticking loop is silent,
  2. a long job in flight is silent HOWEVER long it takes - it must never kill a running
     backtest and leave the job doc stuck on status='running',
  3. an idle loop that stopped ticking shouts on every check, and
  4. it restarts only after three strikes, and not at all with the exit knob off.
"""
import os

import pytest

from api.runner import LoopWatchdog


def _wd(**kw):
    """A watchdog with a captured log and a captured exit - nothing really exits."""
    lines, exits = [], []
    kw.setdefault("stale_sec", 100.0)
    kw.setdefault("allow_exit", True)
    wd = LoopWatchdog(log=lines.append, exiter=exits.append, **kw)
    return wd, lines, exits


def test_a_loop_that_keeps_ticking_is_silent():
    wd, lines, exits = _wd()
    t = wd._stamp
    for i in range(10):
        wd.beat("poll")
        assert wd.check(now=wd._stamp + 50) == "ok"
    assert lines == [] and exits == []
    assert wd._stamp >= t


def test_a_job_in_flight_never_trips_it_however_long_it_runs():
    # A validate runs 30-90 minutes inside run_once(). That is work, not a hang, and a
    # restart there would kill the job and orphan its doc.
    wd, lines, exits = _wd()
    with wd.busy("run_once (listener)"):
        for hours in (1, 2, 6, 24):
            assert wd.check(now=wd._stamp + hours * 3600) == "busy"
    assert exits == [], "the watchdog must not exit while a job is in flight"
    assert lines == []
    # leaving busy re-stamps, so the long job does not immediately read as stale
    assert wd.check() == "ok"


def test_an_idle_loop_that_stopped_ticking_shouts_with_the_age_and_the_last_pass():
    wd, lines, exits = _wd(stale_sec=600.0)
    wd.beat("backstop")
    assert wd.check(now=wd._stamp + 900) == "stale"
    assert exits == []
    assert len(lines) == 1
    line = lines[0]
    assert "STOPPED TICKING" in line
    assert "900" in line and "600" in line, line        # age and limit are both stated
    assert "backstop" in line, line                      # and WHAT the last pass was
    assert "strike 1 of 3" in line


def test_it_restarts_only_on_the_third_strike_and_exit_3_means_the_watchdog():
    wd, lines, exits = _wd(stale_sec=10.0)
    wd.beat("poll")
    base = wd._stamp
    assert wd.check(now=base + 60) == "stale"
    assert wd.check(now=base + 90) == "stale"
    assert exits == [], "two strikes is not a restart - one slow call must not cost one"
    assert wd.check(now=base + 120) == "exit"
    assert exits == [3], "exit code 3 is how the launcher log says the watchdog did it"
    assert any("restarting the runner now" in s for s in lines)
    assert any("no job is being killed" in s for s in lines)


def test_a_beat_clears_the_strikes():
    wd, lines, exits = _wd(stale_sec=10.0)
    base = wd._stamp
    assert wd.check(now=base + 60) == "stale"
    assert wd.check(now=base + 70) == "stale"
    wd.beat("poll")                                      # the loop came back on its own
    assert wd.check(now=wd._stamp + 1) == "ok"
    assert wd.check(now=wd._stamp + 60) == "stale"
    assert "strike 1 of 3" in lines[-1]                   # counted from scratch
    assert exits == []


def test_the_exit_knob_off_keeps_the_shouting_and_never_exits():
    wd, lines, exits = _wd(stale_sec=10.0, allow_exit=False)
    base = wd._stamp
    for n in (60, 90, 120, 150):
        assert wd.check(now=base + n) == "stale"
    assert exits == []
    assert any("NOT restarting" in s for s in lines)


def test_zero_seconds_turns_it_off_and_starts_no_thread():
    wd, lines, exits = _wd(stale_sec=0.0)
    assert wd.start() is None
    assert any("OFF" in s for s in lines)


@pytest.mark.parametrize("val,on", [("600", True), ("0", False), ("", True), ("bad", True)])
def test_the_threshold_comes_from_the_environment(monkeypatch, val, on):
    monkeypatch.setenv("EDGELOG_LOOP_WATCHDOG_SEC", val)
    wd = LoopWatchdog(log=lambda *_a: None, exiter=lambda *_a: None)
    assert (wd.stale_sec > 0) is on
    if val in ("", "bad"):
        assert wd.stale_sec == 600.0, "an unreadable value falls back to the default, not off"


@pytest.mark.parametrize("val,allow", [("0", False), ("off", False), ("false", False),
                                       ("1", True), ("", True)])
def test_the_exit_knob_comes_from_the_environment(monkeypatch, val, allow):
    monkeypatch.setenv("EDGELOG_LOOP_WATCHDOG_EXIT", val)
    wd = LoopWatchdog(stale_sec=5.0, log=lambda *_a: None, exiter=lambda *_a: None)
    assert wd.allow_exit is allow


def test_the_watch_loop_actually_beats_and_marks_itself_busy():
    """The class is only useful if the loop uses it - pin the three call sites."""
    import io
    import api.runner as R
    src = io.open(R.__file__, encoding="utf-8").read()
    loop = src.split("while True:", 1)[1]
    assert "WD.beat(" in loop, "the watch loop must stamp a completed pass"
    assert 'WD.busy("run_once' in loop, "running a job must silence the watchdog"
    assert 'WD.busy("run_commands' in loop
    assert "WD = LoopWatchdog(" in src and "WD.start()" in src
