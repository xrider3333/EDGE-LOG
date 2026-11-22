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
                                            "src": "api/qqq_exec.py DEFAULT_CONFIG", "max": 10}


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


# ── 11-21 asifml: ML leak guard, per-trade sizes, the side-panel env var ──────────────────────────────────────────
def _ml_model(tmp_path, body=b"fitted-model-bytes"):
    import hashlib
    p = tmp_path / "leg.pkl"
    p.write_bytes(body)
    return str(p), hashlib.sha256(body).hexdigest()


def test_ml_guard_ignores_a_leg_with_no_model():
    assert b.ml_guard("NOISE422", {"strategy": "NOISE_1_0.py", "run": 1}, {}, registry={}) is None


def test_ml_guard_refuses_a_model_trained_into_the_window(tmp_path):
    path, sha = _ml_model(tmp_path)
    reg = {"MLX": {"model_path": path, "sha256": sha, "trained_through": "2026-06-01"}}
    with pytest.raises(ValueError, match="on or after the as-if window start"):
        b.ml_guard("MLX", {"strategy": "NOISE_1_0.py", "run": 7}, {}, registry=reg)
    reg["MLX"]["trained_through"] = "2026-09-30"
    with pytest.raises(ValueError, match="ML leak guard"):
        b.ml_guard("MLX", {"strategy": "NOISE_1_0.py", "run": 7}, {}, registry=reg)


def test_ml_guard_refuses_an_unknown_training_end(tmp_path):
    path, sha = _ml_model(tmp_path)
    reg = {"MLX": {"model_path": path, "sha256": sha}}
    with pytest.raises(ValueError, match="training end .* is unknown"):
        b.ml_guard("MLX", {"strategy": "NOISE_1_0.py", "run": 7}, {}, registry=reg)


def test_ml_guard_needs_the_run_pinned_artifact(tmp_path):
    path, sha = _ml_model(tmp_path)
    with pytest.raises(ValueError, match="not pinned"):
        b.ml_guard("MLX", {"strategy": "NOISE_1_0.py", "run": 7}, {},
                   registry={"MLX": {"model_path": path, "trained_through": "2026-03-31"}})
    with pytest.raises(ValueError, match="not the run's model"):     # the run doc's pin wins over the registry
        b.ml_guard("MLX", {"strategy": "NOISE_1_0.py", "run": 7}, {"model_sha256": "0" * 64},
                   registry={"MLX": {"model_path": path, "sha256": sha, "trained_through": "2026-03-31"}})


def test_ml_guard_passes_a_pinned_model_trained_before_the_window(tmp_path):
    path, sha = _ml_model(tmp_path)
    doc = {"model_path": path, "model_sha256": sha, "model_trained_through": "2026-05-29T16:00:00"}
    g = b.ml_guard("MLX", {"strategy": "NOISE_1_0.py", "run": 7}, doc, registry={})
    assert g["sha12"] == sha[:12] and g["trained_through"] == "2026-05-29" and g["model_path"] == path


def test_ml_registry_is_empty_and_documented():
    assert b.ML_LEGS == {} and "leak" in (b.__doc__ + b.ML_LEGS.__class__.__doc__ + open(b.__file__).read()).lower()


def test_box_sized_shares_follows_the_box_rule():
    assert b.box_sized_shares(10, 1.0, 60) == (10, False)
    assert b.box_sized_shares(10, 1.5, 60) == (15, False)
    assert b.box_sized_shares(10, 0.04, 60) == (1, False)        # floored at one share
    assert b.box_sized_shares(10, 8.0, 60) == (60, True)         # clamped, not refused
    assert b.box_sized_shares(0, 2.0, 60) == (0, False)          # a leg the owner turned off stays off


def test_qqq_block_applies_a_file_size():
    refs = {"qqq": {"2026-07-01": 525.0}, "NQ": {"2026-07-01": 21000.0}, "ES": {}, "beta_es": 1.4, "beta_src": "t",
            "sizing": {"shares": {"ORB": 10, "ENGUQ": 10, "NOISE": 10}, "slip": 0.01, "src": "t", "max": 60}}
    spec = {"instrument": "NQ", "pnl_units": "points", "cost_pts": 0.533, "weight": 1.0, "params": {},
            "_leg_id": "NOISE422", "strategy": "NOISE_1_8_CT304H.py"}
    # a 1.5x tilted trade, raw 25.533 gross pts a contract: the file folds 1.5 x 25.533 - 0.5 x 0.533, the engine
    # charges 0.533 once -> t[2] = 1.5 x 25 = 37.5. The box: 15 shares at 25.533 gross / 40 - slippage
    t = (0, 1, 37.5)
    st = _st([t], ["2026-07-01", "2026-07-02", "2026-07-03"])
    st["file_sizes"] = {id(t): 1.5}
    q = b.qqq_block(spec, st, refs)
    assert q["shares"] == 10 and q["p"][0] == pytest.approx(round(25.533 / 40 * 15 - 2 * 0.01 * 15, 2))
    assert "1 trade(s) carry a per-trade size" in q["sized"]
    st0 = _st([t], ["2026-07-01", "2026-07-02", "2026-07-03"])        # unsized: the old reading
    assert b.qqq_block(spec, st0, refs)["p"][0] == pytest.approx(round((37.5 + 0.533) / 40 * 10 - 0.2, 2))


def _fake_state(trades, sizes, days):
    import numpy as np
    return {"_state": {"sized": [(t, s) for t, s in zip(trades, sizes)], "mult": 20.0, "weight": 1.0,
                       "sess_idx": np.array(days, dtype="datetime64[D]"), "last": len(days) - 1, "days_idx": None,
                       "file_sizes": None}, "master": "fake"}


def test_simulate_applies_the_gate_size_and_scopes_the_panel_env(monkeypatch):
    import augur_engine.book as eb
    seen = {}
    env = "MISC_TEST_PANEL_EXT"
    monkeypatch.delenv(env, raising=False)

    def fake(leg, a, z, keep_state=False):
        seen["env"] = os.environ.get(env)
        return [], _fake_state([(0, 1, 10.0), (1, 2, 10.0)], [1.0, 0.5], ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"])
    monkeypatch.setattr(eb, "_leg_trades", fake)
    monkeypatch.setattr(b, "qqq_block", lambda spec, st: {"same": True})
    spec = {"strategy": "X.py", "params": {}, "instrument": "SPY", "timeframe": "5m", "session": "rth", "source": None,
            "cost_pts": 0.0, "mult": 20.0, "weight": 1.0, "panel_ext": {"env": env, "path": "C:/x/panel.npz"}}
    days, info = b.simulate(spec)
    assert seen["env"] == "C:/x/panel.npz"            # set while the leg replays
    assert os.environ.get(env) is None                # and gone after it
    assert days["2026-07-02"][0] == pytest.approx(200.0) and days["2026-07-03"][0] == pytest.approx(100.0)
    assert "1 trade(s) carry a per-trade size" in info["sized"]


def test_leg_env_restores_a_previous_value(monkeypatch):
    monkeypatch.setenv(b.MODEL_ENV, "before")
    with b.leg_env({"ml": {"model_path": "C:/m.pkl"}}):
        assert os.environ[b.MODEL_ENV] == "C:/m.pkl"
    assert os.environ[b.MODEL_ENV] == "before"


def test_panel_refresh_once_per_master_day(monkeypatch):
    monkeypatch.setattr(b, "panel_ext_info", lambda env, path: {"end": "2026-11-19"})
    legs = ["PICK6", "OPUS86a", "GLDNIGHT", "NOISE422"]
    assert b.panels_to_refresh(legs, "2026-11-20", {}, "2026-11-20") == [
        ("PICK6", "eodrev"), ("OPUS86a", "auchabit"), ("GLDNIGHT", "gldnight")]
    assert b.panels_to_refresh(legs, "2026-11-20", {"PICK6": "2026-11-20"}, "2026-11-20")[0][0] == "OPUS86a"
    assert b.panels_to_refresh(legs, "2026-11-19", {}, "2026-11-20") == []      # panel already at the master's end
    assert b.panels_to_refresh(legs, "2026-11-21", {}, "2026-11-19") == []      # today's session is not complete yet
    assert b.panels_to_refresh(legs, None, {}, "2026-11-20") == []
