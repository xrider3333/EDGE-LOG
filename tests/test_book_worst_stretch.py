"""A BOOK must say WHO paid for its worst stretch - and name the legs that were absent.

WHY (2026-09-09): every book bar in this repo used to read "whole-run drawdown within X
percent of the adopted book". That clause is INERT on a leg that took no trades in the one
stretch which sets that drawdown - the TTM leg was scaled 1 -> 4 contracts with the book
drawdown identical to the cent. augur_engine.book now decomposes the stretch per leg, so a
bar can be written on the number that actually responds to weight.

Two properties are guarded, because both are what makes the block trustworthy:
  1. the legs' dollars inside the stretch sum to the drawdown EXACTLY (the span is the days
     strictly AFTER the peak - including the peak day double-counts its P&L);
  2. a leg with no trades inside the stretch is reported at zero days and lands in
     `inert_legs`, which is the whole point of the block.
"""
import numpy as np

from augur_engine.book import _stretch_attribution


def _d(s):
    return np.datetime64(s, "D")


def test_stretch_decomposes_exactly_and_names_the_absent_leg():
    # leg A trades through the drawdown; leg B trades only before and only after it.
    a = [(_d("2020-01-02"), 1000.0), (_d("2020-01-06"), -400.0), (_d("2020-01-07"), -600.0),
         (_d("2020-01-08"), -300.0), (_d("2020-01-20"), 5000.0)]
    b = [(_d("2020-01-02"), 500.0), (_d("2020-01-20"), 700.0)]
    info = [{"strategy": "A.py", "instrument": "NQ", "timeframe": "5m", "weight": 1.0},
            {"strategy": "B.py", "instrument": "ES", "timeframe": "30m", "weight": 3.0}]
    w = _stretch_attribution(a + b, [a, b], info)

    assert w["peak"] == "2020-01-02" and w["to"] == "2020-01-08"
    assert w["depth"] == 1300.0                      # 400 + 600 + 300, the peak day excluded
    rows = {r["leg"]: r for r in w["legs"]}
    assert rows["A.py"]["usd"] == -1300.0 and rows["A.py"]["days"] == 3
    assert rows["B.py"]["usd"] == 0.0 and rows["B.py"]["days"] == 0
    assert sum(r["usd"] for r in w["legs"]) == -w["depth"]   # property 1, to the cent


def test_absent_leg_cannot_move_the_whole_run_drawdown_at_any_weight():
    """The finding itself, as a test: scaling the absent leg leaves the drawdown untouched."""
    a = [(_d("2020-01-02"), 1000.0), (_d("2020-01-06"), -900.0), (_d("2020-01-20"), 5000.0)]
    info = [{"strategy": "A.py"}, {"strategy": "B.py"}]
    depths = []
    for w in (1.0, 3.0, 10.0, 100.0):
        b = [(_d("2020-01-02"), 500.0 * w), (_d("2020-01-20"), 700.0 * w)]
        st = _stretch_attribution(a + b, [a, b], info)
        depths.append(st["depth"])
        assert [r["days"] for r in st["legs"] if r["leg"] == "B.py"] == [0]
    assert len(set(depths)) == 1, "an absent leg changed the drawdown - the diagnostic is wrong"


def test_empty_book_stretch_is_none_not_a_crash():
    assert _stretch_attribution([], [[]], [{"strategy": "A.py"}]) is None
