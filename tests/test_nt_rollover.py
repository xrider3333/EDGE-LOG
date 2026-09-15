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
