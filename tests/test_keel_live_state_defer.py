"""tests/test_keel_live_state_defer.py -- tools/keel_live_state.py's
--defer-in-session flag (deadman/deadman_keel_guard, 2026-09-26): KEEL must never
rebuild mid-session, so edgelog-keel-state.path's on-push rebuild has to defer to the
18:30 ET timer whenever a push lands 09:25-16:05 ET on a trading day.

should_defer_in_session() is pure (takes an aware datetime, touches no clock, no
Firestore, no live files), so every case here is a plain function call -- no
monkeypatching of time itself needed.
"""
import datetime
import os
import sys
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tools.keel_live_state as kls  # noqa: E402

ET = zoneinfo.ZoneInfo("America/New_York")


def _et(y, mo, d, h, mi):
    return datetime.datetime(y, mo, d, h, mi, tzinfo=ET)


# 2026-09-22 is a real trading Tuesday (per api/market_calendar); 2026-09-26 is a Saturday.
TRADING_DAY = (2026, 9, 22)
WEEKEND_DAY = (2026, 9, 26)


def test_mid_session_on_a_trading_day_defers():
    assert kls.should_defer_in_session(_et(*TRADING_DAY, 12, 0)) is True


def test_window_boundaries_are_inclusive():
    assert kls.should_defer_in_session(_et(*TRADING_DAY, 9, 25)) is True
    assert kls.should_defer_in_session(_et(*TRADING_DAY, 16, 5)) is True


def test_just_outside_the_window_does_not_defer():
    assert kls.should_defer_in_session(_et(*TRADING_DAY, 9, 24)) is False
    assert kls.should_defer_in_session(_et(*TRADING_DAY, 16, 6)) is False


def test_evening_18_30_timer_slot_never_defers():
    """The nightly 18:30 ET timer (edgelog-keel-state.timer) shares this exact unit
    with the on-push path -- it must never be deferred, or KEEL would never rebuild
    at all."""
    assert kls.should_defer_in_session(_et(*TRADING_DAY, 18, 30)) is False


def test_weekend_never_defers_even_at_a_mid_session_clock_time():
    assert kls.should_defer_in_session(_et(*WEEKEND_DAY, 12, 0)) is False


def test_main_defer_in_session_skips_build_and_exits_cleanly(tmp_path, monkeypatch, capsys):
    """--defer-in-session must return without calling build() -- proved by pointing it
    at an NQ file that does not exist, which would otherwise raise SystemExit."""
    monkeypatch.setattr(kls, "_now_et", lambda: _et(*TRADING_DAY, 12, 0))
    called = []
    monkeypatch.setattr(kls, "build", lambda *a, **k: called.append(True))
    missing_nq = str(tmp_path / "does_not_exist.csv")
    old_argv = sys.argv
    sys.argv = ["keel_live_state.py", "--nq-file", missing_nq, "--out-dir", str(tmp_path),
               "--defer-in-session"]
    try:
        kls.main()
    finally:
        sys.argv = old_argv
    assert not called, "build() must not run while --defer-in-session is honoured"
    assert "deferring to the 18:30 ET timer" in capsys.readouterr().out


def test_main_without_defer_flag_still_requires_the_nq_file(tmp_path, monkeypatch):
    """Sanity check that --defer-in-session alone changed behaviour above -- without
    it, a missing NQ file still raises exactly as before this feature."""
    monkeypatch.setattr(kls, "_now_et", lambda: _et(*TRADING_DAY, 12, 0))
    missing_nq = str(tmp_path / "does_not_exist.csv")
    old_argv = sys.argv
    sys.argv = ["keel_live_state.py", "--nq-file", missing_nq, "--out-dir", str(tmp_path)]
    try:
        try:
            kls.main()
            assert False, "expected SystemExit for a missing NQ master"
        except SystemExit:
            pass
    finally:
        sys.argv = old_argv
