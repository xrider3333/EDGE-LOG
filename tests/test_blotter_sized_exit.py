"""A sized trade's blotter exit price (owner 2026-11-26, run #555 #4592).

A strategy file that folds its own size into t[2] (NOISE's tilt, the v12 fixed tilts) reports
`trade_sizes` + `size_cost_pts`. The blotter used to invert the exit as if every trade were ONE
contract, so a 2.625x loser's exit was drawn 2.625x as far from the entry as price ever went.
"""
import csv
import os

import numpy as np
import pandas as pd
import pytest

import api.blotter as B

C = 0.533          # the files' folded cost per extra contract, and the run's cost_pts


def _fake(monkeypatch, trades, sizes=None, fold_c=None):
    idx = pd.date_range("2025-10-17 09:30", periods=40, freq="5min")
    close = np.linspace(24900.0, 24950.0, 40)
    monkeypatch.setattr(B, "find_master", lambda *a, **k: {"name": "fake NQ 5m", "source": "tv"})
    monkeypatch.setattr(B, "load_master_arrays", lambda m, **k: {"index": idx, "close": close})

    def run(*a, **k):
        out = {"trades": [tuple(t) for t in trades]}
        if sizes is not None:
            out["trade_sizes"] = list(sizes)
            out["size_cost_pts"] = fold_c
        return out
    monkeypatch.setattr(B.ae, "run_backtest", run)


def _sized_net(entry, exit_, side, s, cost=C, fold=C):
    """What the engine hands the blotter for a size-s trade: s*gross - (s-1)*fold - cost."""
    g = (exit_ - entry) * side
    return s * g - (s - 1.0) * fold - cost


def test_a_sized_losers_exit_is_where_price_went_not_size_times_further(monkeypatch):
    entry, real_exit, s = 24931.25, 24809.75, 2.625
    net = _sized_net(entry, real_exit, 1, s)
    _fake(monkeypatch, [(2, 8, net, 1, entry)], sizes=[s], fold_c=C)
    rows, _ = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)
    r = rows[0]
    assert r["exit_px"] == pytest.approx(real_exit, abs=0.01)
    assert r["size"] == pytest.approx(s)
    # the P&L of record is untouched: the sized net, in points and dollars
    assert r["pnl_pts"] == pytest.approx(round(net, 2))
    assert r["pnl_usd"] == pytest.approx(round(net * 20.0, 2))


def test_a_sized_short_inverts_the_other_way(monkeypatch):
    entry, real_exit, s = 29857.5, 29960.0, 3.0
    net = _sized_net(entry, real_exit, -1, s)
    _fake(monkeypatch, [(2, 6, net, -1, entry)], sizes=[s], fold_c=C)
    rows, _ = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)
    assert rows[0]["exit_px"] == pytest.approx(real_exit, abs=0.01)
    assert rows[0]["side"] == "short"


def test_an_unsized_file_is_the_old_arithmetic_exactly(monkeypatch):
    entry = 25000.0
    _fake(monkeypatch, [(1, 3, -10.0, 1, entry), (4, 9, 7.25, -1, entry)])
    rows, _ = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)
    assert rows[0]["exit_px"] == pytest.approx(round(entry + (-10.0 + C), 2))
    assert rows[1]["exit_px"] == pytest.approx(round(entry - (7.25 + C), 2))
    assert rows[0]["size"] == 1.0 and rows[1]["size"] == 1.0


def test_misaligned_sizes_are_ignored_not_misapplied(monkeypatch):
    entry = 25000.0
    _fake(monkeypatch, [(1, 3, -10.0, 1, entry), (4, 9, 7.25, 1, entry)], sizes=[2.0], fold_c=C)
    rows, _ = B.champion_blotter("X.py", "NQ", "5m", cost_pts=C, mult=20.0)
    assert [r["size"] for r in rows] == [1.0, 1.0]
    assert rows[0]["exit_px"] == pytest.approx(round(entry + (-10.0 + C), 2))


def _write_old_csv(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = [f for f in B.FIELDS if f != "size"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({"trade_no": 1, "entry_time": "2025-10-17 10:15", "exit_time": "2025-10-17 10:45",
                    "hold_bars": 6, "entry_px": 24931.25, "exit_px": 24611.35, "pnl_pts": -320.45,
                    "pnl_usd": -6409.0, "cum_usd": -6409, "side": "long"})


def test_a_pre_size_cache_of_a_sized_file_is_rebuilt(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    (root / "augur_strategies").mkdir(parents=True)
    (root / "augur_strategies" / "SIZED.py").write_text('out["trade_sizes"] = sizes\n', encoding="utf-8")
    bdir = tmp_path / "blotters"
    monkeypatch.setattr(B, "blotter_dir", lambda: str(bdir))
    _write_old_csv(str(bdir / "run555_NQ_5m.csv"))
    entry, real_exit, s = 24931.25, 24809.75, 2.625
    _fake(monkeypatch, [(2, 8, _sized_net(entry, real_exit, 1, s), 1, entry)], sizes=[s], fold_c=C)
    out = B.load_blotter_rows(str(root), {"run_id": 555, "instrument": "NQ", "timeframe": "5m",
                                          "strategy": "SIZED.py", "params": {"a": 1}, "cost_pts": C},
                              log=lambda *a: None)
    assert out["ok"] and out.get("regenerated")
    assert float(out["rows"][0]["exit_px"]) == pytest.approx(real_exit, abs=0.01)
    # and the rebuilt CSV now carries the size column, so the next read is served from cache
    out2 = B.load_blotter_rows(str(root), {"run_id": 555, "instrument": "NQ", "timeframe": "5m",
                                           "strategy": "SIZED.py", "params": {"a": 1}, "cost_pts": C},
                               log=lambda *a: None)
    assert not out2.get("regenerated") and float(out2["rows"][0]["size"]) == pytest.approx(s)


def test_a_pre_size_cache_of_an_unsized_file_is_still_served(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    (root / "augur_strategies").mkdir(parents=True)
    (root / "augur_strategies" / "PLAIN.py").write_text("def run_backtest(): pass\n", encoding="utf-8")
    bdir = tmp_path / "blotters"
    monkeypatch.setattr(B, "blotter_dir", lambda: str(bdir))
    _write_old_csv(str(bdir / "run7_NQ_5m.csv"))
    out = B.load_blotter_rows(str(root), {"run_id": 7, "instrument": "NQ", "timeframe": "5m",
                                          "strategy": "PLAIN.py", "params": {"a": 1}, "cost_pts": C},
                              log=lambda *a: None)
    assert out["ok"] and not out.get("regenerated") and out["n"] == 1
