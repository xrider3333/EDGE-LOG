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


# ── the day-stamping choice, made visible ────────────────────────────────────────
def test_a_book_reports_both_day_rules_and_only_the_curve_moves(monkeypatch):
    """A trade's calendar day has two defensible answers; a book must report both.

    The engine truncates a US/Eastern index, which numpy does in UTC, so a 24h leg exiting at or
    after 20:00 ET books on the NEXT day. The other answer is the ET session day. NET IS THE SAME
    under both -- only the daily curve moves -- and because drawdown is measured on the daily
    curve, the two can disagree about the drawdown and about which stretch is worst.

    Pinned here because the whole point is that the disagreement is VISIBLE. If a future change
    drops `day_rule`, or lets the two nets drift apart (which would mean trades were lost rather
    than restamped), this fails.
    """
    import augur_engine.book as B

    # one leg, same four trades, stamped one day apart by the two rules
    utc = [(_d("2021-01-04"), 100.0), (_d("2021-01-06"), -900.0),
           (_d("2021-01-07"), 100.0), (_d("2021-01-20"), 900.0)]
    sess = [(_d("2021-01-04"), 100.0), (_d("2021-01-05"), -900.0),
            (_d("2021-01-07"), 100.0), (_d("2021-01-20"), 900.0)]

    def fake(leg, date_from, date_to):
        return list(utc), {"strategy": "A.py", "instrument": "NQ", "timeframe": "1m",
                           "session": "eth", "source": None, "mult": 1.0, "weight": 1.0,
                           "trades": len(utc), "net": 200.0, "master": "x", "cost_pts": 0.0,
                           "_session_day": list(sess)}

    monkeypatch.setattr(B, "_leg_trades", fake)
    r = B.run_book([{"strategy": "A.py", "instrument": "NQ"}],
                   date_from="2021-01-01", date_to="2021-02-01", lockbox_months=0, slices=2)
    dr = r["book"]["day_rule"]

    assert dr["used"] == "utc_truncated"
    assert dr["session_day"]["total_pnl"] == r["book"]["whole"]["total_pnl"], (
        "the two rules disagree about NET -- they must only restamp trades, never lose them")
    assert dr["net_differs"] is False
    assert dr["session_day"]["max_drawdown"] == r["book"]["whole"]["max_drawdown"]
    # both stampings put the -900 in the same relative place here, so nothing should be flagged
    assert dr["drawdown_differs"] is False
    assert dr["session_day"]["worst_stretch"]["to"] == "2021-01-05"   # the restamped day, one earlier


def test_the_day_rule_block_flags_a_real_disagreement(monkeypatch):
    """When the restamp moves a loss across a peak, the drawdown differs and the book says so."""
    import augur_engine.book as B

    # Both curves open with the same gain, so both have a real peak to fall from -- a series
    # that only ever falls has no drawdown by definition and would test nothing. Under the
    # engine rule the two losses sit either side of a recovery; under the session rule they land
    # on the SAME day, so the fall is taken in one step and is twice as deep.
    utc = [(_d("2021-01-04"), 1000.0), (_d("2021-01-05"), -500.0),
           (_d("2021-01-06"), 800.0), (_d("2021-01-07"), -500.0)]
    sess = [(_d("2021-01-04"), 1000.0), (_d("2021-01-05"), -500.0),
            (_d("2021-01-05"), -500.0), (_d("2021-01-06"), 800.0)]

    def fake(leg, date_from, date_to):
        return list(utc), {"strategy": "A.py", "instrument": "NQ", "timeframe": "1m",
                           "session": "eth", "mult": 1.0, "weight": 1.0, "trades": 4,
                           "net": 800.0, "master": "x", "cost_pts": 0.0,
                           "_session_day": list(sess)}

    monkeypatch.setattr(B, "_leg_trades", fake)
    bk = B.run_book([{"strategy": "A.py", "instrument": "NQ"}],
                    date_from="2021-01-01", date_to="2021-02-01",
                    lockbox_months=0, slices=2)["book"]
    dr, r_dd = bk["day_rule"], bk["whole"]["max_drawdown"]

    assert dr["net_differs"] is False, "restamping must never change the money"
    assert dr["drawdown_differs"] is True, "a moved loss deepened the curve and was not flagged"
    assert r_dd == 500.0, "engine rule: two separated 500s"
    assert dr["session_day"]["max_drawdown"] == 1000.0, "session rule: one 1000 step"
