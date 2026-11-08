"""Owner order 11-08 (MANAGER #185): no ROC @ $30k on a window under a quarter year."""
import datetime as dt

from tools import run_record as R
from tools import run_records_sync as S


def _daily(n, start="2026-10-12"):
    d0 = dt.date.fromisoformat(start)
    days = [d0 + dt.timedelta(days=i) for i in range(n)]
    vals = [100.0 if i % 3 else -150.0 for i in range(n)]
    return vals, [d.isoformat() for d in days]


def _rec(n):
    vals, dates = _daily(n)
    return R.build_record("TBIS", "lane", "LB", strategy="X.py", family="MISC", instrument="NQ",
                          timeframe="5m", daily=vals, dates=dates, trades=30, ts="2026-11-08 13:00")


def test_short_window_nulls_roc_and_tags_note():
    r = _rec(25)
    assert r["roc30k"] is None and "SHORT WINDOW" in r["note"]
    assert r["net_usd"] is not None and r["max_dd_usd"] > 0     # still plots on the dollar axes


def test_long_window_keeps_roc():
    r = _rec(200)
    assert r["roc30k"] is not None and "SHORT WINDOW" not in r["note"]


def test_is_short_window_from_dates():
    assert R.is_short_window(None, "2026-10-12", "2026-11-06")
    assert not R.is_short_window(None, "2026-01-01", "2026-06-01")
    assert not R.is_short_window(None, None, None)


def test_sync_nulls_a_hand_written_short_roc():
    r = dict(_rec(200))
    r.update(roc30k=1043.98, years=0.07, win_start="2026-10-12", win_end="2026-11-06")
    out = S.validate(r)
    assert out["roc30k"] is None and "SHORT WINDOW" in (out["note"] or "")
