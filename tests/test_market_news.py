import datetime
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import market_news as mn  # noqa: E402

TZ = "America/New_York"


def _bars(day0, close0, ah, day1_pre=None):
    """5m closes: day0 regular 09:30-15:55 at close0, after-hours 16:00-19:55 ending at ah,
    and optionally day1 pre-market 04:00-09:25 ending at day1_pre."""
    idx, val = [], []
    for t in pd.date_range(f"{day0} 09:30", f"{day0} 15:55", freq="5min", tz=TZ):
        idx.append(t); val.append(close0)
    for t in pd.date_range(f"{day0} 16:00", f"{day0} 19:55", freq="5min", tz=TZ):
        idx.append(t); val.append(ah)
    if day1_pre is not None:
        d1 = (pd.Timestamp(day0) + pd.Timedelta(days=1)).date()
        for t in pd.date_range(f"{d1} 04:00", f"{d1} 09:25", freq="5min", tz=TZ):
            idx.append(t); val.append(day1_pre)
    return pd.Series(val, index=pd.DatetimeIndex(idx))


def test_moves_next_morning_pre_and_last_evening_after_hours():
    c = _bars("2026-10-28", 100.0, 103.0, day1_pre=98.0)
    pre, post = mn._moves(c, datetime.date(2026, 10, 29))
    assert round(post, 6) == 3.0 and round(pre, 6) == -2.0


def test_moves_before_any_pre_market_today_gives_after_hours_only():
    c = _bars("2026-10-28", 100.0, 101.5)
    pre, post = mn._moves(c, datetime.date(2026, 10, 29))
    assert pre is None and round(post, 6) == 1.5


def test_movers_floor_split_and_order():
    q = {"A": {"pre": 5.0}, "B": {"pre": -4.0}, "C": {"pre": 0.4}, "D": {"pre": None}, "E": {"pre": 2.0}}
    assert mn.movers(q, "pre") == [("A", 5.0), ("E", 2.0), ("B", -4.0)]


RSS = """<?xml version="1.0"?><rss><channel><title>x</title>
<item><title>First  headline</title></item><item><title>Second</title></item><item><title>Third</title></item>
</channel></rss>"""


def test_headlines_and_block_text():
    assert mn.headlines("A", fetch=lambda u: RSS) == ["First headline", "Second"]
    assert mn.headlines("A", fetch=lambda u: (_ for _ in ()).throw(OSError())) == []
    q = {"A": {"pre": 5.0, "post": None, "name": "A"}}
    L = mn.block("Pre-market news", q, "pre", "none", fetch=lambda u: RSS)
    assert L[:3] == ["## Pre-market news", "- **A** +5.0%", "  - First headline"]
    assert mn.block("After-hours news", q, "post", "nothing moved")[1] == "- nothing moved"
    assert "quote pull failed" in mn.block("X", {}, "pre", "n")[1]


def test_ndx_members_applies_adds_and_drops(tmp_path):
    p = tmp_path / "ndx.json"
    p.write_text('{"source": "", "base": "AAA BBB CCC", "months": ['
                 '["2026-01-01", 1, "", "", "", "DDD", "BBB", 3], ["2026-02-01", 1, "", "", "", "", "CCC", 2]]}',
                 encoding="utf-8")
    assert mn.ndx_members(str(p)) == ["AAA", "DDD"]
    assert "NVDA" in mn.ndx_members()          # the real file still reads


def test_news_blocks_never_raise_on_a_failed_download():
    class Boom:
        @staticmethod
        def download(*a, **k):
            raise OSError("offline")
    L = mn.news_blocks(symbols=["A"], yf=Boom)
    assert "## Pre-market news" in L and any("quote pull failed" in x for x in L)
