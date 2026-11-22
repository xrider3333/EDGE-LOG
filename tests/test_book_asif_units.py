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


# ── v91.74: the QQQ conversion WEBULL PAPER reads (the box's fixed lot, gross points x QQQ/NQ, slippage both sides) ──
def test_qqq_trade_usd_known_nq_trade():
    # +25 NQ points gross, NQ 21,000 / QQQ 525 (ratio 40), 10 shares, $0.01 a share each side
    # = 25 / 40 x 10 - 2 x 0.01 x 10 = 6.25 - 0.20 = $6.05
    assert b.qqq_trade_usd(25.0, 21000.0, 525.0, 10, 0.01) == pytest.approx(6.05)
    # an ES leg through a beta: 30 ES points at 6000 = 0.5 pct x beta 1.4 x QQQ 600 x 30 sh - 0.60
    assert b.qqq_trade_usd(30.0, 6000.0, 600.0, 30, 0.01, beta=1.4) == pytest.approx(126.0 - 0.6)


def test_qqq_shares_follow_the_box_lot():
    sz = {"shares": {"ORB": 10, "ENGUQ": 10, "NOISE": 10}, "slip": 0.01, "src": "t"}
    assert b.qqq_shares("NOISE422", 1.0, sz)[0] == 10 and b.exec_leg_for("NOISE422") == "NOISE"
    assert b.qqq_shares("ORB314", 1.0, sz)[0] == 10 and b.exec_leg_for("ENGUQ335") == "ENGUQ"
    assert b.qqq_shares("TTMx3", 3.0, sz)[0] == 30 and b.exec_leg_for("TTMx3") is None
    assert b.qqq_shares("OPUS58c_h", 0.5, sz)[0] == 5
    assert b.exec_sizing(cfg_path=None) == {"shares": {"ORB": 5, "ENGUQ": 5, "NOISE": 5}, "slip": 0.01,
                                            "src": "api/qqq_exec.py DEFAULT_CONFIG"}


def _st(trades, days):
    import numpy as np
    return {"sized": [(t, 1.0) for t in trades], "sess_idx": np.array(days, dtype="datetime64[D]"),
            "last": len(days) - 1, "days_idx": None}


def test_qqq_block_replays_a_known_nq_trade():
    refs = {"qqq": {"2026-07-01": 525.0}, "NQ": {"2026-07-01": 21000.0}, "ES": {}, "beta_es": 1.4, "beta_src": "t",
            "sizing": {"shares": {"ORB": 10, "ENGUQ": 10, "NOISE": 10}, "slip": 0.01, "src": "t"}}
    spec = {"instrument": "NQ", "pnl_units": "points", "cost_pts": 0.5, "weight": 1.0, "params": {},
            "_leg_id": "NOISE422"}
    # one trade: net 24.5 pts (the replay already charged the 0.5-pt NQ cost) -> gross 25 -> $6.05; exits the day after
    q = b.qqq_block(spec, _st([(0, 1, 24.5)], ["2026-07-01", "2026-07-02", "2026-07-03"]), refs)
    assert q["d"] == ["2026-07-02"] and q["p"] == [6.05] and q["n"] == [1] and q["shares"] == 10
    assert q["net"] == 6.05 and "the box's NOISE lot" in q["rule"] and q["via"] == "QQQ/NQ ratio"
    # a dollars file (EXPCAL: $20 a point, cost inside): -$100 net = -5 pts net = -4.467 gross at 0.533; half size = 5 sh
    spec2 = {"instrument": "NQ", "pnl_units": "usd", "cost_pts": 0.0, "weight": 0.5,
             "params": {"point_value": 20, "cost_pts": 0.533}, "_leg_id": "OPUS58c_h"}
    q2 = b.qqq_block(spec2, _st([(0, 1, -100.0)], ["2026-07-01", "2026-07-02", "2026-07-03"]), refs)
    assert q2["shares"] == 5 and q2["p"][0] == pytest.approx(round(-4.467 / 40 * 5 - 0.10, 2))
    # stock legs stay as dollars; an instrument the box cannot map says why
    assert b.qqq_block({"instrument": "SPY", "pnl_units": "usd"}, {}, refs)["same"] is True
    assert "no QQQ map for ZN" in b.qqq_block({"instrument": "ZN", "pnl_units": "points"}, {}, refs)["reason"]
