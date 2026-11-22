"""augur_engine/risk_sizing.py - RISK-% sizing (board 132, owner 11-22). Hand-computed fixture.

Fixture: NQ point value $20, cost 0.5 pts, start $30,000, 1 % risk.
  T1 enters t=1 (nothing banked): equity 30,000 -> risk $300 / (15 pts x $20) = 1.0 -> +10 gross x 20 x 1 - 0.5 x 20 x 1 = +190
  T2 enters t=3 (T1 banked):      equity 30,190 -> $301.90 / (7 x 20) = 2.156 -> 2.1 MNQ steps -> -20 x 20 x 2.1 - 21 = -861
  T3 enters t=3.5, T2 STILL OPEN: equity 30,190 -> $301.90 / (100 x 20) = 0.151 -> 0.1 -> +5 x 20 x 0.1 - 1 = +9
  T4 enters t=7:                  equity 29,338 -> $293.38 / (400 x 20) = 0.037 -> 0 -> SKIPPED
  T5 no stop -> median losing trade per contract = 20.5 pts: $293.38 / (20.5 x 20) = 0.716 -> 0.7 -> +3 x 20 x 0.7 - 7 = +35
  net -627, taken 4, skipped 1, max 2.1 contracts, worst fall $861 from the $30,190 high = 2.852 %.
FIXED 1: +190, -410, +90, +30, +50 = -50."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from augur_engine import risk_sizing as RS  # noqa: E402

TR = [
    {"e": 1.0, "x": 2.0, "p": 9.5, "z": 1, "r": 15.0, "d": "2024-01-02"},
    {"e": 3.0, "x": 4.0, "p": -20.5, "z": 1, "r": 7.0, "d": "2024-01-03"},
    {"e": 3.5, "x": 6.0, "p": 4.5, "z": 1, "r": 100.0, "d": "2024-01-04"},
    {"e": 7.0, "x": 8.0, "p": 1.5, "z": 1, "r": 400.0, "d": "2024-01-04"},
    {"e": 9.0, "x": 10.0, "p": 2.5, "z": 1, "r": None, "d": "2024-01-05"},
]
DAYS = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]


def test_contracts_floor_to_micro_and_cap():
    assert RS.contracts_for(30_000, 0.01, 15, 20) == 1.0
    assert RS.contracts_for(30_190, 0.01, 7, 20) == 2.1
    assert RS.contracts_for(29_338, 0.01, 400, 20) == 0.0
    assert RS.contracts_for(30_000, 0.03, 0.5, 20) == 10.0          # 90 -> owner cap 10
    assert RS.contracts_for(-5, 0.01, 10, 20) == 0.0
    assert RS.contracts_for(30_000, 0.01, None, 20) == 0.0


def test_median_loss_pts():
    assert RS.median_loss_pts([1, -2, -6, 3]) == 4.0
    assert RS.median_loss_pts([1, 2]) is None


def test_one_pct_hand_computed():
    fb = RS.median_loss_pts([t["p"] for t in TR])
    assert fb == 20.5
    s = RS.size_chain(TR, point_value=20, cost_pts=0.5, pct=0.01, fallback_risk=fb)
    usd = dict((d, 0.0) for d in DAYS)
    for d, u in s["rows"]:
        usd[d] += u
    assert [round(x, 6) for x in s and [u for _, u in s["rows"]]] == [190.0, -861.0, 9.0, 35.0]
    assert s["taken"] == 4 and s["skipped"] == 1 and s["max_c"] == 2.1 and s["risk_fallback_n"] == 1
    r = RS.read_chain(s, DAYS)
    assert r["net"] == -627.0 and r["end_equity"] == 29_373.0
    assert r["eq"] == [30_000.0, 30_190.0, 29_329.0, 29_338.0, 29_373.0]
    assert r["max_dd_usd"] == 861.0
    assert r["dd_pct"] == pytest.approx(100 * 861 / 30_190, abs=0.01)
    assert r["ruin"] is False and r["trades"] == 4 and r["skipped"] == 1 and r["max_contracts"] == 2.1


def test_fixed_one_contract():
    s = RS.size_chain(TR, point_value=20, cost_pts=0.5, pct=None)
    assert [round(u, 6) for _, u in s["rows"]] == [190.0, -410.0, 90.0, 30.0, 50.0]
    assert s["skipped"] == 0 and s["max_c"] == 1.0


def test_table_columns_and_risk_src():
    t = RS.sizing_table(TR, DAYS, point_value=20, cost_pts=0.5)
    assert set(t["cols"]) == {"fixed", "r1", "r2", "r3"}
    assert t["risk_src"] == "mixed" and t["fallback_risk_pts"] == 20.5
    assert t["cols"]["fixed"]["net"] == -50.0 and t["cols"]["r1"]["net"] == -627.0
    for k in ("net", "end_equity", "dd_pct", "roc30", "dd5", "sortino", "trades", "skipped", "max_contracts", "ruin"):
        assert k in t["cols"]["r3"]


def test_size_column_divides_out_the_files_own_size():
    # NOISE tilt: p is 1.5 x the per-contract net; per contract it is the same trade as a z=1 one
    a = RS.size_chain([dict(TR[0], p=9.5 * 1.5, z=1.5)], point_value=20, cost_pts=0.5, pct=0.01)
    assert [u for _, u in a["rows"]] == [190.0]


def test_ruin_flag_and_no_trades_at_zero_equity():
    tr = [{"e": 1, "x": 2, "p": -1000.0, "z": 1, "r": 1.0, "d": "2024-01-02"},
          {"e": 3, "x": 4, "p": 5.0, "z": 1, "r": 1.0, "d": "2024-01-03"}]
    r = RS.read_chain(RS.size_chain(tr, point_value=20, cost_pts=0.0, pct=None), DAYS)
    assert r["ruin"] is True and r["min_equity"] == 10_000.0
    s = RS.size_chain([dict(tr[0], p=-2000.0)] + tr[1:], point_value=20, cost_pts=0.0, pct=0.01)
    assert s["taken"] == 1 and s["skipped"] == 1                   # equity -10,000 takes nothing
