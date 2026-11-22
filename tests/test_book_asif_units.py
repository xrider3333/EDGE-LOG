"""tools/book_asif_series.py - each leg's cost / mult / size must fit how its strategy reports P&L (owner 11-21).

A "points" file needs the run's cost and the contract multiplier; a "usd" file charges its own cost inside and must
run at job cost 0, mult 1; the weight must match the book row's size (PICK6 = the $10k-a-side paper size).
The live-table checks skip where the book table or a cached run doc is not on the machine (CI).
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import book_asif_series as b  # noqa: E402


def _spec(units_cost, mult, inst="NQ"):
    return {"cost_pts": units_cost, "mult": mult, "instrument": inst}


def test_unit_check_points_and_usd():
    assert b.unit_check(_spec(0.533, 20.0), "points") == ""
    assert "cost_pts 0" in b.unit_check(_spec(0.0, 20.0), "points")
    assert "mult 1.0" in b.unit_check(_spec(0.533, 1.0), "points")
    assert b.unit_check(_spec(0.363, 50.0, "ES"), "points") == ""
    assert b.unit_check(_spec(0.0, 1.0, "SPY"), "usd") == ""
    assert "dollars file" in b.unit_check(_spec(0.533, 1.0), "usd")
    assert "dollars file" in b.unit_check(_spec(0.0, 20.0), "usd")
    assert b.unit_check(_spec(0.533, 20.0), None) == "strategy file not found"


def test_strategy_units_read_from_the_files():
    assert b.strategy_pnl_units("MISC_EXPCAL_1_0.py") == "usd"
    assert b.strategy_pnl_units("MISC_GLDNIGHT_1_0.py") == "usd"
    assert b.strategy_pnl_units("MISC_EODREV_1_2.py") == "usd"
    assert b.strategy_pnl_units("MISC_SMALLLEGS_1_0.py") == "points"
    assert b.strategy_pnl_units("NOISE_1_0.py") == "points"          # no constant = points
    assert b.strategy_pnl_units("NO_SUCH_FILE_9_9.py") is None


@pytest.mark.parametrize("size,want", [
    ("1 NQ", 1.0), ("3 ES", 3.0), ("TTM x3", 3.0), ("half size", 0.5), ("up to 2 NQ", 1.0),
    ("$100k", 1.0), ("$100k a side", 1.0), ("as tested", 1.0), ("1 NQ (OR15, run #546)", 1.0)])
def test_size_weight_from_book_row(size, want):
    assert b.size_weight(size, {}, {}) == want


def test_pick6_paper_size_is_a_tenth():
    s = b.LEG_SPECS["PICK6"]
    assert b.size_weight("$100k a side, realistic exit", s, {"notional": 100000}) == pytest.approx(0.1)
    assert s["size"] == "$10k a side (paper size)"


def test_specs_pinned_by_the_owner_review():
    assert b.LEG_SPECS["NOISE398"]["params_run"] == 528 and b.LEG_SPECS["NOISE398"]["run"] == 398
    assert b.LEG_SPECS["OPUS58c_h"]["weight"] == 0.5
    assert b.LEG_SPECS["OPUS58c"]["params"] == {"cost_pts": 0.533, "point_value": 20}


def test_every_live_leg_is_consistent(monkeypatch):
    table = b._load_json(b.BOOK_TABLE)
    if not isinstance(table, dict) or not table.get("books"):
        pytest.skip("book table not on this machine")
    real = b.run_doc
    monkeypatch.setattr(b, "run_doc", lambda rid, allow_fetch=False: real(rid, allow_fetch=False))
    checked = 0
    for lid, leg in b.distinct_legs(table).items():
        assert lid in b.LEG_SPECS, "%s has no LEG_SPECS entry" % lid
        s = b.LEG_SPECS[lid]
        if real(int(s.get("params_run") or s["run"]), allow_fetch=False) is None:
            continue
        spec = b.leg_spec(lid, leg)               # raises on a cost / mult that does not fit the units
        assert b.unit_check(spec, spec["pnl_units"]) == ""
        want = float(s["weight"]) if "weight" in s else b.size_weight(leg.get("size"), s, spec["params"])
        if "weight" in s:                         # an explicit weight must agree with the row's size text
            assert b.size_weight(leg.get("size"), {}, {}) in (want, 1.0), (lid, leg.get("size"), want)
        assert spec["weight"] == pytest.approx(want), lid
        if spec["pnl_units"] == "points":
            assert spec["cost_pts"] > 0 and spec["mult"] == b.MULT[spec["instrument"]], lid
        checked += 1
    if not checked:
        pytest.skip("no cached run docs on this machine")
