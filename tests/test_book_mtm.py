"""A BOOK must also report its drawdown with OPEN trades valued daily - and never change the money.

WHY (2026-09-24, book round 56, BOOK_ROUND56_ROC.txt section 5): a book counts each trade on the
day it CLOSES. ENGU-Q holds trades for weeks (up to 143 days on NQ), so the swings of an open
position never reached the book's daily curve: on the FRONTIER book #397 the lockbox drawdown is
$49,855 with open trades valued daily against the stored $25,357 at close. augur_engine.book now
scores the same dollars both ways and stores the second reading as `book.mtm`.

Three properties are guarded, because they are what make the second reading trustworthy:
  1. each trade's daily increments sum EXACTLY to its closed dollars - the money never moves,
     only the day it is counted - so the whole-run net is identical to the cent;
  2. an open-profit giveback (a trade that was well up and closed barely up) deepens the
     marked drawdown while the at-close curve never sees it - which is the finding itself;
  3. a same-day trade reads identically both ways, so an intraday-only book is unchanged and
     never flagged.
"""
import numpy as np

from augur_engine.book import _mtm_increments


def _days(*spec):
    """_days(("2021-01-04", 2), ("2021-01-05", 2)) -> a per-bar day stamp, n bars per day."""
    out = []
    for d, n in spec:
        out += [np.datetime64(d, "D")] * n
    return np.array(out, dtype="datetime64[D]")


def test_a_multi_day_trade_is_valued_each_day_and_still_sums_to_its_closed_dollars():
    days = _days(("2021-01-04", 2), ("2021-01-05", 2), ("2021-01-06", 1))
    close = np.array([100.0, 105.0, 120.0, 110.0, 104.0])
    # long filled at 100 on bar 0, closed on bar 4 for +3.5 points after costs; x20 x1 x1
    trades = [((0, 4, 3.5, 1, 100.0), 1.0)]
    inc, marked, unmarked = _mtm_increments(days, close, trades, 20.0, 1.0)

    assert (marked, unmarked) == (1, 0)
    assert [str(d) for d, _ in inc] == ["2021-01-04", "2021-01-05", "2021-01-06"]
    assert [round(p, 6) for _, p in inc] == [100.0, 100.0, -130.0]   # +5, +10 open, then 3.5 closed
    assert round(sum(p for _, p in inc), 6) == 70.0                    # property 1: 3.5 pts x $20


def test_an_open_profit_giveback_deepens_the_marked_drawdown(monkeypatch):
    """Property 2, through run_book: the at-close curve sees one small win, the marked one sees
    the whole ride up and most of it given back."""
    import augur_engine.book as B

    d = lambda s: np.datetime64(s, "D")
    closed = [(d("2021-01-04"), 50.0), (d("2021-01-08"), 70.0)]           # two winners at close
    marked = [(d("2021-01-04"), 50.0),                                      # first trade, same day
              (d("2021-01-05"), 400.0), (d("2021-01-06"), 300.0),         # second trade open: +700
              (d("2021-01-07"), -500.0), (d("2021-01-08"), -130.0)]       # given back to +70

    def fake(leg, date_from, date_to):
        return list(closed), {"strategy": "A.py", "instrument": "NQ", "timeframe": "1m",
                              "session": "eth", "mult": 20.0, "weight": 1.0, "trades": 2,
                              "net": 120.0, "master": "x", "cost_pts": 0.0, "mtm_marked": 1,
                              "_session_day": list(closed), "_mtm_day": list(marked)}

    monkeypatch.setattr(B, "_leg_trades", fake)
    bk = B.run_book([{"strategy": "A.py", "instrument": "NQ"}],
                    date_from="2021-01-01", date_to="2021-02-01", lockbox_months=0, slices=2)["book"]
    m = bk["mtm"]

    assert m["whole"]["total_pnl"] == bk["whole"]["total_pnl"] == 120.0   # property 1, to the cent
    assert m["net_differs"] is False
    assert bk["whole"]["max_drawdown"] == 0.0                             # at close: never fell
    assert m["whole"]["max_drawdown"] == 630.0                            # valued daily: 750 -> 120
    assert m["drawdown_differs"] is True
    assert m["marked_trades"] == 1 and m["multi_day_legs"] == ["A.py"]
    assert m["worst_stretch"]["to"] == "2021-01-08"


def test_same_day_trades_read_identically_and_are_not_flagged(monkeypatch):
    """Property 3: an intraday leg's marks ARE its closed trades."""
    import augur_engine.book as B

    days = _days(("2021-01-04", 3), ("2021-01-05", 3))
    close = np.array([10.0, 11.0, 12.0, 13.0, 12.0, 11.0])
    trades = [((0, 2, 1.5, 1, 10.0), 1.0), ((3, 5, -2.0, -1, 13.0), 1.0)]
    inc, marked, unmarked = _mtm_increments(days, close, trades, 50.0, 3.0)
    assert (marked, unmarked) == (0, 0)
    assert [(str(a), round(b, 6)) for a, b in inc] == [("2021-01-04", 225.0), ("2021-01-05", -300.0)]

    # and a book whose leg carries no marks at all scores the closed series as its second reading
    d = lambda s: np.datetime64(s, "D")
    tr = [(d("2021-01-04"), 100.0), (d("2021-01-06"), -300.0), (d("2021-01-20"), 500.0)]

    def fake(leg, date_from, date_to):
        return list(tr), {"strategy": "A.py", "instrument": "NQ", "timeframe": "5m",
                          "session": "rth", "mult": 20.0, "weight": 1.0, "trades": 3,
                          "net": 300.0, "master": "x", "cost_pts": 0.0,
                          "_session_day": list(tr)}

    monkeypatch.setattr(B, "_leg_trades", fake)
    bk = B.run_book([{"strategy": "A.py", "instrument": "NQ"}],
                    date_from="2021-01-01", date_to="2021-02-01", lockbox_months=0, slices=2)["book"]
    assert bk["mtm"]["whole"] == {"total_pnl": bk["whole"]["total_pnl"],
                                  "max_drawdown": bk["whole"]["max_drawdown"]}
    assert bk["mtm"]["drawdown_differs"] is False and bk["mtm"]["net_differs"] is False


def test_short_trades_and_unmarkable_trades():
    days = _days(("2021-01-04", 1), ("2021-01-05", 1), ("2021-01-06", 1))
    close = np.array([200.0, 190.0, 195.0])
    # a short from 200: flat at the fill day's close, +10 points open after day 2, closes +4 after costs
    inc, marked, _ = _mtm_increments(days, close, [((0, 2, 4.0, -1, 200.0), 1.0)], 2.0, 1.0)
    assert marked == 1 and [round(p, 6) for _, p in inc] == [0.0, 20.0, -12.0]
    # a multi-day trade with no usable side / entry price is booked at close, never guessed at
    inc, marked, unmarked = _mtm_increments(days, close, [((0, 2, 4.0, 0, float("nan")), 1.0)], 2.0, 1.0)
    assert (marked, unmarked) == (0, 1) and [(str(a), b) for a, b in inc] == [("2021-01-06", 8.0)]


def test_empty_leg_is_empty_not_a_crash():
    assert _mtm_increments(np.array([], dtype="datetime64[D]"), np.array([]), [], 20.0, 1.0) == ([], 0, 0)
