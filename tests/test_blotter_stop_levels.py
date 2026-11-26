"""A run blotter row carries its strategy's own stop (owner 2026-11-26: "show the stop line moving on the
gallery charts too"; api/blotter.py LEVELS_MARK). The levels come from the strategy's (possibly roll-adjusted)
series and are mapped back to raw prices by the transform that took the entry there; run #555 #4592's stop maps
onto its exit exactly (24,850.40)."""
import csv
import os

import numpy as np
import pandas as pd
import pytest

import api.blotter as B

C = 0.533


def _lv(entry_bar, side, entry, stop, **k):
    row = {"entry_bar": entry_bar, "side": side, "entry": entry, "risk": abs(entry - stop), "stop": stop,
           "target": None, "be_trigger": None, "be_stop": None, "be_bar": None, "trail": False, "partial": False}
    row.update(k)
    return row


def _fake(monkeypatch, trades, levels, method=None, wants=True, seen=None):
    idx = pd.date_range("2025-10-17 09:30", periods=40, freq="5min")
    close = np.linspace(24900.0, 24950.0, 40)
    monkeypatch.setattr(B, "find_master", lambda *a, **k: {"name": "fake NQ 5m", "source": "tv"})
    monkeypatch.setattr(B, "load_master_arrays", lambda m, **k: {"index": idx, "close": close})
    monkeypatch.setattr(B, "_wants_levels", lambda s: wants)

    def run(*a, **k):
        if seen is not None:
            seen.append(dict(k.get("params") or {}))
        out = {"trades": [tuple(t) for t in trades]}
        if (k.get("params") or {}).get("return_levels"):
            out["levels"] = levels
        if method:
            out["_meta"] = {"roll_stamp": {"signal_method": method}}
        return out
    monkeypatch.setattr(B.ae, "run_backtest", run)
    return idx


def test_4592_ratio_adjusted_stop_maps_onto_its_exit(monkeypatch):
    # the engine numbers for #4592: raw entry 24,931.25, adjusted entry 25,912.262..., adjusted stop 25,828.234...
    raw_e, adj_e, adj_s = 24931.25, 25912.26201984642, 25828.234611081592
    real_exit = adj_s * raw_e / adj_e
    net = real_exit - raw_e - C
    _fake(monkeypatch, [(2, 6, net, 1, raw_e)], [_lv(2, 1, adj_e, adj_s)], method="ratio")
    r = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)[0][0]
    assert r["stop_px"] == pytest.approx(24850.40, abs=0.005)
    assert r["exit_why"] == "stop"


def test_difference_adjusted_stop_shifts_by_the_entry_offset(monkeypatch):
    _fake(monkeypatch, [(2, 6, 12.0, -1, 25000.0)], [_lv(2, -1, 25100.0, 25140.0)], method="difference")
    r = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)[0][0]
    assert r["stop_px"] == pytest.approx(25040.0)
    assert r.get("exit_why", "") == ""          # a winner closed by its rule, not at the stop


def test_adjusted_with_no_method_draws_no_stop(monkeypatch):
    _fake(monkeypatch, [(2, 6, -5.0, 1, 25000.0)], [_lv(2, 1, 25100.0, 25080.0)], method=None)
    r = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)[0][0]
    assert "stop_px" not in r


def test_breakeven_step_target_and_trail_flag(monkeypatch):
    idx = _fake(monkeypatch, [(2, 9, -C, 1, 25000.0)],
                [_lv(2, 1, 25000.0, 24980.0, target=25040.0, be_stop=25000.0, be_trigger=25010.0, be_bar=4,
                     trail=True)])
    r = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)[0][0]
    assert r["stop_px"] == 24980.0 and r["target_px"] == 25040.0
    assert r["be_px"] == 25000.0 and r["be_time"] == str(idx[5])[:16]     # live from the bar after the arming close
    assert r["stop_moves"] == 1 and r["exit_why"] == "breakeven"


def test_a_row_for_another_trade_is_not_used(monkeypatch):
    _fake(monkeypatch, [(2, 6, -5.0, 1, 25000.0)], [_lv(3, 1, 25000.0, 24990.0)])
    r = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)[0][0]
    assert "stop_px" not in r


def test_a_file_without_levels_is_called_exactly_as_before(monkeypatch):
    seen = []
    _fake(monkeypatch, [(2, 6, -5.0, 1, 25000.0)], None, wants=False, seen=seen)
    rows, _ = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0, params={"a": 1})
    assert seen == [{"a": 1}] and "stop_px" not in rows[0]


def test_a_pre_levels_cache_of_a_levels_file_is_rebuilt(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    (root / "augur_strategies").mkdir(parents=True)
    (root / "augur_strategies" / "LV.py").write_text("def run_backtest(o, return_levels=False): pass\n",
                                                     encoding="utf-8")
    bdir = tmp_path / "blotters"
    monkeypatch.setattr(B, "blotter_dir", lambda: str(bdir))
    os.makedirs(bdir)
    old = [f for f in B.FIELDS if f not in ("stop_px", "target_px", "be_px", "be_time", "stop_moves", "exit_why")]
    with open(bdir / "run9_NQ_5m.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({"trade_no": 1, "entry_time": "2025-10-17 09:40", "exit_time": "2025-10-17 10:00", "hold_bars": 4,
                    "entry_px": 25000.0, "exit_px": 24990.0, "pnl_pts": -10.53, "pnl_usd": -210.6, "cum_usd": -211,
                    "side": "long", "size": 1.0})
    _fake(monkeypatch, [(2, 6, -10.0 - C, 1, 25000.0)], [_lv(2, 1, 25000.0, 24990.0)])
    pay = {"run_id": 9, "instrument": "NQ", "timeframe": "5m", "strategy": "LV.py", "params": {"a": 1}, "cost_pts": C}
    out = B.load_blotter_rows(str(root), pay, log=lambda *a: None)
    assert out["ok"] and out.get("regenerated")
    assert float(out["rows"][0]["stop_px"]) == 24990.0
    out2 = B.load_blotter_rows(str(root), pay, log=lambda *a: None)
    assert not out2.get("regenerated") and out2["rows"][0]["exit_why"] == "stop"
