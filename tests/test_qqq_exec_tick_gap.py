"""api/qqq_exec.py's _track_tick_gap (2026-09-25 fix): the overnight/weekend gap between
the previous session's last ACTIVE tick and today's first one must never read as a stall.

THE BUG. _track_tick_gap is only ever called `if active` (tick()'s own caller), so "the
previous active tick" for the FIRST tick of a fresh trading session is routinely the prior
session's close -- ~62,344s overnight in the live 2026-09-25 case, longer over a weekend.
Before this fix that fired "[qqq-exec] WARN tick loop gap {gap}s" every single morning,
logged a `tick_gap` event, and set tick_gap_max_s_today to that whole overnight span --
polluting the day's health figures with a number that says nothing about today. A real
intraday stall (previous active tick on the SAME ET day) must still warn exactly as before.
"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe   # noqa: E402

NOOP = lambda *a, **k: None  # noqa: E731


def test_first_tick_of_a_fresh_state_returns_none():
    state = {}
    gap = qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 30), now_wall=1_000_000.0, log=NOOP)
    assert gap is None
    assert state["tick_gap_max_s_today"] == 0.0
    assert state.get("events", []) == []


def test_overnight_gap_does_not_warn():
    """The exact live case: last active tick 2026-09-24 15:59 ET, first active tick
    2026-09-25 09:30 ET, ~62,344s of real wall-clock time apart."""
    logs = []
    state = {}
    qe._track_tick_gap(state, datetime(2026, 9, 24, 15, 59), now_wall=1_000_000.0, log=logs.append)
    gap = qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 30), now_wall=1_000_000.0 + 62344.0,
                             log=logs.append)
    assert gap is None, "the first active tick of a new ET session must not report a real gap"
    assert not any("tick loop gap" in m for m in logs), "must never warn on an overnight gap"
    assert state.get("events", []) == [], "must never log a tick_gap event for an overnight gap"
    assert state["tick_gap_max_s_today"] == 0.0, "the new day's rolling max must start at 0"


def test_overnight_gap_is_detected_by_et_date_not_by_gap_size():
    """A weekend (or holiday) gap is even longer than one night -- still no warning, because
    the rule is "previous active tick on a different ET date", not a size threshold."""
    logs = []
    state = {}
    qe._track_tick_gap(state, datetime(2026, 9, 25, 15, 59), now_wall=0.0, log=logs.append)   # Fri
    gap = qe._track_tick_gap(state, datetime(2026, 9, 28, 9, 30), now_wall=250000.0,           # Mon
                             log=logs.append)
    assert gap is None
    assert logs == []


def test_a_200s_gap_inside_one_session_still_warns():
    logs = []
    state = {}
    qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 30), now_wall=1_000_000.0, log=logs.append)
    gap = qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 35), now_wall=1_000_000.0 + 200.0,
                             log=logs.append)
    assert gap == 200.0
    assert any("WARN tick loop gap 200s" in m for m in logs)
    assert state["tick_gap_max_s_today"] == 200.0
    assert any(e.get("kind") == "tick_gap" for e in state.get("events", []))


def test_a_short_intraday_gap_neither_warns_nor_raises():
    """Below TICK_GAP_WARN_SEC -- the normal, boring tick-to-tick case."""
    logs = []
    state = {}
    qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 30), now_wall=0.0, log=logs.append)
    gap = qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 30, 5), now_wall=5.0, log=logs.append)
    assert gap == 5.0
    assert logs == []
    assert state["tick_gap_max_s_today"] == 5.0


def test_tick_gap_max_s_today_resets_per_day_even_across_an_overnight_gap():
    state = {}
    qe._track_tick_gap(state, datetime(2026, 9, 24, 9, 30), now_wall=0.0, log=NOOP)
    qe._track_tick_gap(state, datetime(2026, 9, 24, 9, 35), now_wall=300.0, log=NOOP)   # a real stall
    assert state["tick_gap_max_s_today"] == 300.0

    # next morning: the overnight gap must not carry yesterday's max forward
    gap = qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 30), now_wall=100000.0, log=NOOP)
    assert gap is None
    assert state["tick_gap_max_s_today"] == 0.0

    # a small real gap later that same (new) day updates the freshly-reset max
    gap = qe._track_tick_gap(state, datetime(2026, 9, 25, 9, 30, 5), now_wall=100005.0, log=NOOP)
    assert gap == 5.0
    assert state["tick_gap_max_s_today"] == 5.0
