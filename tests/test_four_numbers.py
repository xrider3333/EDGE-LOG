"""THE FOUR NUMBERS from one source (augur_engine/drawdowns.four_numbers, MANAGER #170, 2026-10-15).

Every result carries ROC@30k, DD5, DD% from peak and Sortino. They were re-implemented in 10+ lane scripts, and one
lane fed per-TRADE P&L to its Sortino (ENGU-Q's hold-cap rows), which flipped a clause verdict. These tests pin:
  * three published rows reproduce exactly from #463's own daily P&L (RISK r1 records cache, rule U, exported to
    tests/fixtures/four_numbers/book463_wf_lb_daily.csv at the cent): #463 WF 93.81 / $36,095 / 13.09% / 3.816,
    #463 without TTM WF 99.56 / $34,798 / 12.39% / 3.532 (BOOK.md 10bb), #463 LB 155.54 / $35,034 / 18.33% / 4.150,
    one episode (BOOK LOOKS r1);
  * the Sortino is DAILY with zero days included (FRONTIER #73) - a case where the per-trade figure differs;
  * the figures agree with book_sizing.stretch_reading, the yardstick's own reader, and with seat_pipeline's Sortino.
"""
import math
import os

import numpy as np
import pandas as pd
import pytest

from augur_engine.drawdowns import four_numbers

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "four_numbers", "book463_wf_lb_daily.csv")
WF1, LB0 = "2025-06-29", "2025-06-30"


@pytest.fixture(scope="module")
def book():
    return pd.read_csv(FIX, index_col=0, parse_dates=True)


def _published(f):
    return (round(f["roc30"], 2), round(f["dd5_usd"]), round(f["dd_pct_peak"], 2), round(f["sortino"], 3), f["one_episode"])


# ------------------------------------------------------------------ three published rows
def test_463_walk_forward_reproduces_the_published_row(book):
    f = four_numbers(book["book"][:WF1])
    assert _published(f) == (93.81, 36095, 13.09, 3.816, False)
    assert (f["from"], f["to"]) == ("2016-07-01", "2025-06-29")
    assert round(f["net_per_year"]) == 140235


def test_463_without_ttm_walk_forward_reproduces_the_published_row(book):
    f = four_numbers((book["book"] - book["ttm"])[:WF1])
    assert _published(f) == (99.56, 34798, 12.39, 3.532, False)


def test_463_lockbox_reproduces_the_published_row_and_its_one_episode_flag(book):
    f = four_numbers(book["book"][LB0:])
    assert _published(f) == (155.54, 35034, 18.33, 4.15, True)
    assert f["max_dd"] > 1.3 * f["dd5_usd"]


# ------------------------------------------------------------------ the zero-day convention
def test_sortino_is_daily_with_zero_days_included_not_per_trade():
    days = pd.date_range("2026-01-05", periods=8, freq="B")
    daily = pd.Series([100.0, 0.0, 0.0, -50.0, 0.0, 200.0, 0.0, -30.0], index=days)
    f = four_numbers(daily)
    want = (220.0 / 8) / math.sqrt((50.0 ** 2 + 30.0 ** 2) / 8) * math.sqrt(252.0)       # 21.18
    per_trade = (220.0 / 4) / math.sqrt((50.0 ** 2 + 30.0 ** 2) / 4) * math.sqrt(252.0)  # 29.95
    assert f["sortino"] == pytest.approx(want, rel=1e-12)
    assert abs(want - per_trade) > 8
    # the trap, shown: dropping the zero days IS the per-trade figure
    assert four_numbers(daily[daily != 0])["sortino"] == pytest.approx(per_trade, rel=1e-12)


def test_zero_days_change_the_sortino_but_not_the_roc_or_drawdowns():
    days = pd.date_range("2026-01-05", periods=8, freq="B")
    daily = pd.Series([100.0, 0.0, 0.0, -50.0, 0.0, 200.0, 0.0, -30.0], index=days)
    f, g = four_numbers(daily), four_numbers(daily[daily != 0], years=four_numbers(daily)["years"])
    assert f["roc30"] == pytest.approx(g["roc30"]) and f["dd5_usd"] == g["dd5_usd"] and f["dd_pct_peak"] == g["dd_pct_peak"]
    assert f["sortino"] != pytest.approx(g["sortino"])


# ------------------------------------------------------------------ agreement with the existing readers
def test_agrees_with_the_yardstick_reader_stretch_reading(book):
    from augur_engine.book_sizing import stretch_reading
    for lo, hi in (("2016-07-01", WF1), (LB0, "2026-06-30"), ("2019-01-01", "2021-12-31")):
        s = book["book"]
        f = four_numbers(s[lo:hi])
        r = stretch_reading(s, lo, hi)
        assert round(f["roc30"], 3) == r["roc_30k"]
        assert round(f["sortino"], 4) == r["sortino"]
        assert f["dd_pct_peak"] == r["dd_pct_peak"]
        assert f["max_dd"] == r["max_drawdown"]


def test_agrees_with_the_seat_pipeline_sortino(book):
    from augur_engine import seat_pipeline as SP
    x = book["book"][:WF1]
    assert four_numbers(x)["sortino"] == pytest.approx(SP.sortino(x.to_numpy(float)), rel=1e-12)


def test_years_override_uses_a_fixed_window_length(book):
    x = book["book"][:WF1]
    f = four_numbers(x, years=9.0)
    assert f["years"] == 9.0
    assert f["roc30"] == pytest.approx(30.0 * (x.sum() / 9.0) / f["max_dd"], rel=1e-9)


# ------------------------------------------------------------------ inputs and edge cases
def test_accepts_pairs_and_values_with_dates():
    pairs = [("2026-01-05", 100.0), ("2026-01-06", -40.0), ("2026-01-07", 10.0)]
    a = four_numbers(pairs)
    b = four_numbers([v for _, v in pairs], dates=[d for d, _ in pairs])
    assert a == b and a["from"] == "2026-01-05" and a["to"] == "2026-01-07"


def test_none_when_the_stretch_never_draws_down_or_never_loses():
    f = four_numbers([10.0, 0.0, 5.0], dates=["2026-01-05", "2026-01-06", "2026-01-07"])
    assert f["roc30"] is None and f["sortino"] is None
    assert f["dd5_usd"] == 0.0 and f["dd_pct_peak"] == 0.0 and f["one_episode"] is False


@pytest.mark.parametrize("args, kw", [
    (([5.0],), {"dates": ["2026-01-05"]}),                                        # one row
    (([5.0, -1.0],), {}),                                                         # no dates, no years
    (([5.0, -1.0],), {"dates": ["2026-01-06", "2026-01-05"]}),                    # unsorted
    (([5.0, float("nan")],), {"dates": ["2026-01-05", "2026-01-06"]}),            # not finite
    (([5.0, -1.0],), {"dates": ["2026-01-05"]}),                                  # length mismatch
    (([5.0, -1.0],), {"years": 0}),                                               # bad years
])
def test_refuses_bad_input(args, kw):
    with pytest.raises(ValueError):
        four_numbers(*args, **kw)


def test_numpy_input_with_years_needs_no_dates():
    f = four_numbers(np.array([100.0, -50.0, 80.0]), years=1.0)
    assert f["roc30"] == pytest.approx(30.0 * 130.0 / 50.0) and f["from"] is None
