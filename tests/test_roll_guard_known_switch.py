"""A contract switch the roll table already vouches for must not block an append.

WHY THIS EXISTS (2026-09-29). The guard holds back any bar that looks like an in-bar
contract switch and says, in its own docstring, that the tail "appends by itself once a
human has either confirmed the roll or cleared the false alarm". Nothing ever read that
confirmation back, so confirming a roll changed nothing - and the four coarse masters
(15m/30m/60m/2m, both roots) sat frozen at 2026-09-14 for two weeks on a switch that was
recorded in `tools/data/rolls_<root>.csv`, measured against a second feed on 2026-09-28,
and ALREADY PRESENT in the 1m/5m parent they resample from. Refusing bought nothing and
cost every coarse timeframe its tail.

The rule now: a switch whose table row passes `rolls.is_trustworthy` is a KNOWN roll and
is passed through (the bar is still flagged in the refresh report, never silently fixed).
An ESTIMATED row is not a confirmation and still blocks - an estimate is a guess about a
bar nobody has checked.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import roll_guard, rolls  # noqa: E402

TABLE_DIR = os.path.join(ROOT, "tools", "data")


def _sec(stamp):
    return int(pd.Timestamp(stamp, tz="US/Eastern").timestamp())


def _bars(switch_et, body, tf_min=5, n_before=60, level=29000.0):
    """A quiet run of `tf_min` bars with one carry-sized jump at `switch_et`."""
    t0 = _sec(switch_et) - n_before * tf_min * 60
    times = [t0 + i * tf_min * 60 for i in range(n_before + 5)]
    opens, closes, vols = [], [], []
    for i, t in enumerate(times):
        o = level + i * 0.25
        jump = body if t == _sec(switch_et) else 0.5
        opens.append(o)
        closes.append(o + jump)
        vols.append(50000.0 if jump == body else 3000.0)
    return (np.array(times, dtype="int64"), np.array(opens), np.array(closes),
            np.array(vols))


# ------------------------------------------------------------------ the real 2026-09-14

ROOT_LEVEL = {"NQ": 29000.0, "ES": 7600.0}   # a root's carry floor scales with its price


@pytest.mark.parametrize("root,switch_et,body", [
    ("NQ", "2026-09-14 11:30", 377.5),
    ("ES", "2026-09-14 11:30", 79.5),
])
def test_the_recorded_september_switch_no_longer_blocks_an_append(root, switch_et, body):
    """This is the bar that froze the coarse masters. It is in the table, measured, and
    already inside the parent - so the append must proceed."""
    times, o, c, v = _bars(switch_et, body, level=ROOT_LEVEL[root])
    hit = roll_guard.first_suspect_after(times, o, c, after_time=times[0],
                                         volumes=v, root=root, table_dir=TABLE_DIR)
    assert hit is None, "a measured, recorded switch must not hold the refresh back"


@pytest.mark.parametrize("root,switch_et,body", [
    ("NQ", "2026-09-14 11:30", 377.5),
    ("ES", "2026-09-14 11:30", 79.5),
])
def test_it_is_still_DETECTED_just_not_refused(root, switch_et, body):
    """Passing it through must not mean going blind to it: the bar is still a hit, tagged
    `known`, so a report can name it and a human can still find it."""
    times, o, c, v = _bars(switch_et, body, level=ROOT_LEVEL[root])
    hits = roll_guard.suspect_bars(times, o, c, volumes=v, root=root, table_dir=TABLE_DIR)
    assert len(hits) == 1, "the bar must still be recognised as a contract switch"
    assert hits[0]["known"] is True
    assert hits[0]["known_switch_sec"] == _sec(switch_et)


# ------------------------------------------------------------- what must STILL be refused

def test_an_unrecorded_switch_in_a_future_window_still_blocks():
    """December 2026 is not in the table yet. Until roll_watch measures it that evening,
    a carry-sized jump inside a bar is exactly what the guard is for."""
    times, o, c, v = _bars("2026-12-14 11:30", 380.0)
    hit = roll_guard.first_suspect_after(times, o, c, after_time=times[0],
                                         volumes=v, root="NQ", table_dir=TABLE_DIR)
    assert hit is not None and not hit.get("known")


def test_an_estimated_row_is_not_a_confirmation_and_still_blocks():
    """June 2026 can never be measured (the capture starts after it). An estimate is a
    guess about a bar nobody checked, so it must not unblock anything."""
    est = rolls.estimated_switches("NQ", TABLE_DIR)
    assert len(est) == 1 and est[0]["switch_et"].startswith("2026-06"), \
        "fixture assumes June 2026 is the one estimated NQ switch"

    times, o, c, v = _bars(est[0]["switch_et"][:16], 380.0)
    hit = roll_guard.first_suspect_after(times, o, c, after_time=times[0],
                                         volumes=v, root="NQ", table_dir=TABLE_DIR)
    assert hit is not None, "an estimated offset must not pass a bar through"
    assert not hit.get("known")


def test_is_trustworthy_is_what_decides_not_the_status_string():
    """The gate asks rolls.is_trustworthy(), so adding a new status word later cannot
    accidentally unblock the guard."""
    known = roll_guard._known_switch_secs("NQ", TABLE_DIR)
    trustworthy = [int(r["switch_sec"]) for r in rolls.real_switches("NQ", TABLE_DIR)
                   if rolls.is_trustworthy(r)]
    assert known == sorted(trustworthy)
    assert _sec("2026-09-14 11:30") in known


# ------------------------------------------------------------------- nothing else moved

def test_without_a_root_the_guard_behaves_exactly_as_before():
    """Every existing caller that does not pass a root must get the old behaviour, so the
    change cannot quietly loosen a path nobody updated."""
    times, o, c, v = _bars("2026-09-14 11:30", 377.5)
    hit = roll_guard.first_suspect_after(times, o, c, after_time=times[0], volumes=v)
    assert hit is not None, "no root -> no table lookup -> refuse, as before"


def test_an_unreadable_table_falls_back_to_refusing(tmp_path):
    """If the table is missing or corrupt the guard must fail CLOSED - hold the bar back -
    rather than treat 'I could not check' as 'it is fine'."""
    times, o, c, v = _bars("2026-09-14 11:30", 377.5)
    hit = roll_guard.first_suspect_after(times, o, c, after_time=times[0], volumes=v,
                                         root="NQ", table_dir=str(tmp_path))
    assert hit is not None


def test_a_switch_outside_the_bar_does_not_clear_that_bar():
    """The match is per-BAR, not per-day: a bar only passes when the recorded switch falls
    inside its own window. Otherwise one known roll would clear a whole session."""
    sec = _sec("2026-09-14 11:30")
    # a 5m bar starting 20 minutes before the switch does not contain it
    assert roll_guard._bar_seconds([sec, sec + 300, sec + 600, sec + 900]) == 300
    times, o, c, v = _bars("2026-09-14 11:30", 377.5)
    i = int(np.where(times == sec)[0][0])
    hits = roll_guard.suspect_bars(times, o, c, volumes=v, root="NQ", table_dir=TABLE_DIR)
    assert hits and hits[0]["index"] == i
    assert hits[0]["known_switch_sec"] == sec
    assert sec >= times[i] and sec < times[i] + 300
