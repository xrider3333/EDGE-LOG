"""tools/nt_rollover.py -- the quarterly futures roll for the NinjaTrader paper strategies.

WHY IT EXISTS (2026-09-15). NinjaTrader's own roll dialog moved NOISE's chart to MNQ 12-26
but left ENGU-Q on NQ 09-26 three days before that contract expired, and nothing noticed.
These tests pin the parts that decide WHETHER and WHAT to roll -- the contract calendar,
the market-shut window, and the text edits -- because a wrong answer there either trades a
dead contract or restarts NinjaTrader in the middle of a session.
"""
import datetime as dt
import importlib.util
import os

import pytest

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "nt_rollover.py")
_spec = importlib.util.spec_from_file_location("nt_rollover", _P)
ro = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ro)

ET = ro.ET


def test_third_friday_and_roll_date():
    assert ro.third_friday(2026, 9) == dt.date(2026, 9, 18)
    assert ro.roll_date(2026, 9) == dt.date(2026, 9, 10)
    assert ro.third_friday(2026, 12) == dt.date(2026, 12, 18)
    assert ro.third_friday(2027, 3) == dt.date(2027, 3, 19)


@pytest.mark.parametrize("day,front", [
    (dt.date(2026, 9, 9), (2026, 9)),      # the day before the roll date: still September
    (dt.date(2026, 9, 10), (2026, 12)),    # roll date: December is the front month
    (dt.date(2026, 9, 15), (2026, 12)),
    (dt.date(2026, 12, 10), (2027, 3)),    # year boundary
    (dt.date(2027, 1, 5), (2027, 3)),
])
def test_front_month(day, front):
    assert ro.front_month(day) == front


def test_stale_contracts_never_roll_backward_or_touch_non_quarterly():
    txt = "NQ 09-26 (1 Minute) MNQ 12-26 ES 03-27 NQ 10-26 CL 09-26 MES 06-26"
    assert ro.stale_contracts(txt, (2026, 12)) == ["MES 06-26", "NQ 09-26"]


def test_roll_text_tags_only_inside_instrument_and_label():
    s = ("<Label>NQ 09-26</Label><Instrument>MNQ 09-26</Instrument>"
         "<Note>NQ 09-26 stays</Note><Instrument>NQ 12-26</Instrument>")
    out, n = ro.roll_text_tags(s, (2026, 12))
    assert n == 2
    assert out == ("<Label>NQ 12-26</Label><Instrument>MNQ 12-26</Instrument>"
                   "<Note>NQ 09-26 stays</Note><Instrument>NQ 12-26</Instrument>")


def test_roll_userdata_keeps_the_series_suffix():
    ud = "x&lt;InstrumentOrInstrumentList&gt;NQ 09-26 (1 Minute)&lt;/InstrumentOrInstrumentList&gt;y"
    out, n = ro.roll_userdata(ud, (2026, 12))
    assert n == 1
    assert "&lt;InstrumentOrInstrumentList&gt;NQ 12-26 (1 Minute)&lt;/" in out
    again, n2 = ro.roll_userdata(out, (2026, 12))
    assert n2 == 0 and again == out, "rolling twice must be a no-op"


@pytest.mark.parametrize("when,shut", [
    (dt.datetime(2026, 9, 15, 16, 30, tzinfo=ET), False),   # after the cash close: ETH still trades
    (dt.datetime(2026, 9, 15, 17, 10, tzinfo=ET), True),    # Tuesday daily halt
    (dt.datetime(2026, 9, 15, 17, 50, tzinfo=ET), False),   # too close to the 18:00 reopen
    (dt.datetime(2026, 9, 18, 20, 0, tzinfo=ET), True),     # Friday evening
    (dt.datetime(2026, 9, 19, 12, 0, tzinfo=ET), True),     # Saturday
    (dt.datetime(2026, 9, 20, 17, 45, tzinfo=ET), False),   # Sunday, near the open
    (dt.datetime(2026, 9, 16, 10, 0, tzinfo=ET), False),    # Wednesday session
])
def test_market_shut(when, shut):
    assert ro.market_shut(when) is shut


# -- NIGHT MODE (2026-10-07): a roll inside a clean, flat night is made offline ------------------------------
def _night(how="clean", flat=True, position=None, closed="2026-10-07T13:22:00-07:00"):
    from api import nt_night_mode as nm
    now = nm.now_local()
    st = nm.enter({}, now - dt.timedelta(hours=2), now + dt.timedelta(hours=10), "end of day", "eod",
                  how=how, flat=flat, position=position)
    st["active"]["closed_at"] = closed
    return st


def test_offline_roll_only_after_a_clean_flat_close_with_ninjatrader_still_closed():
    ok, why = ro.night_flat_offline(_night(), running=False, heartbeat_utc="2026-10-07 20:21:00")
    assert ok and "closed flat" in why
    ok, why = ro.night_flat_offline(_night(how="killed-with-position", flat=False, position=["ENGU-Q's NQ trade"]),
                                    running=False, heartbeat_utc=None)
    assert not ok and "ENGU-Q's NQ trade open" in why
    assert ro.night_flat_offline(_night(how="already-closed", flat=None), running=False)[0] is False
    assert ro.night_flat_offline(_night(), running=True)[0] is False
    # the add-on heartbeat says NinjaTrader ran after the close (the owner opened it by hand)
    ok, why = ro.night_flat_offline(_night(), running=False, heartbeat_utc="2026-10-07 23:00:00")
    assert not ok and "ran after the night-mode close" in why
    assert ro.night_flat_offline({}, running=False) == (False, "night mode is not on")
