"""setup_journal's prior-day guard reads the house roll table, not an open gap (MANAGER #98-3).

The old rule called a >0.6% gap between the prior day's last 1m close and today's first open a roll,
in roll months only. The median switch offset is 0.21% (NQ) / 0.38% (ES), so a gap rule misses most
rolls, and it flags news gaps. Since 2026-10-16 the prior-day features are blanked when a real switch from
tools/data/rolls_<root>.csv falls between the prior regular session's open and the signal bar.
On the owner's 45 journal trades both rules flag the same one (MES 2026-06-15).
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import setup_journal as sj  # noqa: E402

ET = "America/New_York"


def _ts(s):
    return pd.Timestamp(s, tz=ET)


def test_a_switch_between_the_prior_session_and_the_signal_is_a_roll():
    # NQ/ES 2026-03 switch: 2026-03-15 20:00 ET (the 00:00 UTC bar of the Sunday evening)
    assert sj.roll_inside("NQ", _ts("2026-03-13 09:30"), _ts("2026-03-16 09:35"))
    assert sj.roll_inside("ES", _ts("2026-03-13 09:30"), _ts("2026-03-16 09:35"))


def test_no_switch_in_the_window_is_no_roll():
    assert not sj.roll_inside("NQ", _ts("2026-03-16 09:30"), _ts("2026-03-17 10:00"))
    assert not sj.roll_inside("ES", _ts("2026-07-09 09:30"), _ts("2026-07-10 10:00"))


def test_an_in_bar_switch_belongs_to_the_bar_it_fell_inside():
    # 2026-09-14 11:30 is an in-bar row: the switch happened inside the 11:30 bar, just after it opened.
    # trade_features passes the signal bar's CLOSE, so a 1m '11:30' signal asks up to 11:31: flagged.
    assert not sj.roll_inside("NQ", _ts("2026-09-11 09:30"), _ts("2026-09-14 11:30"))
    assert sj.roll_inside("NQ", _ts("2026-09-11 09:30"), _ts("2026-09-14 11:31"))
    # a window that starts after the switch sits wholly on the new contract
    assert not sj.roll_inside("NQ", _ts("2026-09-14 11:31"), _ts("2026-09-15 10:00"))


def test_the_old_quarter_window_helper_is_gone():
    assert not hasattr(sj, "is_roll_window") and not hasattr(sj, "ROLL_MONTHS")


def test_a_switch_at_the_signal_close_instant_is_the_next_bar_not_this_one():
    # 2026-03-15 20:00 is a mid-session row: the 20:00 bar is the first bar on the new contract, so a
    # signal bar CLOSING at 20:00 (the 19:59 1m bar) is still wholly on the old contract
    assert not sj.roll_inside("NQ", _ts("2026-03-13 09:30"), _ts("2026-03-15 20:00"))
    assert sj.roll_inside("NQ", _ts("2026-03-13 09:30"), _ts("2026-03-15 20:01"))
