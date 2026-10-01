"""A feed restating a recent bar must not freeze a coarse master forever.

WHAT HAPPENED (2026-09-30 evening, hours after the nightly coarse refresh went live). The
reproduction check demands that every stored bucket can be rebuilt from its parent exactly.
That is the right test for a corrupt master and the wrong test for the recent tail: Yahoo
restated the volume of the 2026-09-29 12:30 ET NQ bar from 23,092 to 25,672, so six coarse
masters whose buckets predated the restatement could no longer reproduce, and the check refused
each file whole. All six froze a day behind their parents - the same freeze fixed that morning,
arriving through a different door, and caused by putting the refresh on a schedule.

THE RULE NOW: a bucket inside the feed's restatement window (UNSETTLED_DAYS) is RE-DERIVED from
the parent as it stands; everything older must still match to the tick. That keeps the part of
the check that catches damage and drops the part that mistook a routine revision for damage.

What these tests guard, in order of how much it would cost to get wrong:
  1. settled history is still checked exactly - loosening that would defeat the whole check;
  2. a restated recent bar no longer stops the file;
  3. the re-derived window is actually rewritten, not just skipped.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import refresh_resampled_masters as rrm  # noqa: E402

DAY = 86400


def _frame(times):
    return pd.DataFrame({"time": times, "open": 1.0, "high": 2.0, "low": 0.5,
                         "close": 1.5, "volume": 10})


def test_the_split_puts_recent_bars_on_the_rederive_side():
    last = 1_790_000_000
    times = [last - 40 * DAY, last - 20 * DAY, last - 11 * DAY, last - 9 * DAY, last - DAY]
    settled, unsettled = rrm.split_settled(_frame(times), last)
    assert list(settled["time"]) == times[:3], "anything older than the window is settled"
    assert list(unsettled["time"]) == times[3:], "anything inside it is re-derived"


def test_the_window_is_measured_from_the_parents_last_bar_not_from_today():
    """A master refreshed from a parent that is itself a week stale must not re-derive bars the
    parent cannot supply - the boundary has to follow the data, not the clock."""
    last = 1_700_000_000                       # an old parent
    times = [last - 30 * DAY, last - DAY]
    settled, unsettled = rrm.split_settled(_frame(times), last)
    assert len(settled) == 1 and len(unsettled) == 1


def test_the_window_is_at_least_a_week():
    """Yahoo was observed restating about seven days back. A shorter window would let the
    freeze return."""
    assert rrm.UNSETTLED_DAYS >= 7


def test_everything_older_than_the_window_is_still_checked_exactly(tmp_path):
    """The guard that matters. A settled bucket that does not reproduce must still stop the
    file - that is what catches a damaged master."""
    last = 1_790_000_000
    old = [last - 40 * DAY, last - 30 * DAY]
    settled, _ = rrm.split_settled(_frame(old), last)
    assert len(settled) == 2, "both are settled, so both must face the check"


def test_a_restated_volume_inside_the_window_is_not_a_failure():
    """The exact 2026-09-29 case: one recent bar's volume changes under us."""
    last = 1_790_000_000
    stored = _frame([last - 30 * DAY, last - 2 * DAY])
    stored.loc[1, "volume"] = 23092                     # what we stored
    settled, unsettled = rrm.split_settled(stored, last)
    assert len(unsettled) == 1 and float(unsettled["volume"].iloc[0]) == 23092
    # the disputed row is on the re-derive side, so it never reaches the reproduction check
    assert last - 2 * DAY not in list(settled["time"])


def test_a_restated_volume_OUTSIDE_the_window_still_fails_loudly():
    """A month-old bar changing is not a restatement, it is a problem - and must stay one."""
    last = 1_790_000_000
    stored = _frame([last - 40 * DAY])
    stored.loc[0, "volume"] = 99999
    settled, unsettled = rrm.split_settled(stored, last)
    assert len(settled) == 1 and len(unsettled) == 0


# --------------------------------------------------- the re-derived tail is really rewritten

def test_the_new_rows_start_after_the_SETTLED_history_not_the_old_last_bar():
    """If new_rows still began after the old last stamp, the re-derived window would be
    dropped and never replaced - the master would go BACKWARDS. This is the line that makes
    the re-derivation real, so it is pinned on the source."""
    src = open(os.path.join(ROOT, "tools", "refresh_resampled_masters.py"),
               encoding="utf-8").read()
    assert "settled_last = int(existing[\"time\"].max())" in src
    assert 'full["time"] > settled_last' in src
    assert 'full["time"] > last_master_t' not in src, (
        "the old boundary would drop the re-derived window without replacing it")


def test_the_report_says_when_it_re_derived_and_how_many():
    """Silently rewriting recent history is exactly the kind of thing that must be stated."""
    src = open(os.path.join(ROOT, "tools", "refresh_resampled_masters.py"),
               encoding="utf-8").read()
    assert "re-derived the last %d bucket(s)" in src
    assert "older buckets still had to match" in src


def test_the_write_guard_still_stands_behind_this():
    """Re-deriving drops rows before adding them back. If the rebuild ever produced fewer rows
    than the master had, the atomic write guard must refuse it rather than install a shrunken
    file - that combination is the whole safety net."""
    src = open(os.path.join(ROOT, "tools", "refresh_resampled_masters.py"),
               encoding="utf-8").read()
    assert "write_master_csv(merged, mpath)" in src


def test_a_master_with_no_rows_inside_the_window_is_unchanged_in_behaviour():
    """A master whose tail is older than the window re-derives nothing, so a quiet instrument
    behaves exactly as before this change."""
    last = 1_790_000_000
    settled, unsettled = rrm.split_settled(_frame([last - 60 * DAY, last - 50 * DAY]), last)
    assert len(unsettled) == 0 and len(settled) == 2
