"""A run whose trades close on a bar closing across the VWAP (NOISE exit_mode 'vwap') marks every blotter row
exit_line='vwap', so the charts draw that line bold while the trade is open (owner 2026-11-26: "highlight it")."""
import csv
import os
import types

import numpy as np
import pandas as pd

import api.blotter as B

C = 0.533


def _mod(default_params=None, sig_default=None):
    m = types.SimpleNamespace()
    if default_params is not None:
        m.DEFAULT_PARAMS = default_params
    if sig_default is None:
        def run_backtest(o, h, l, c, **kw):
            return None
    else:
        def run_backtest(o, h, l, c, exit_mode=sig_default, **kw):
            return None
    m.run_backtest = run_backtest
    return m


def test_the_champions_own_value_wins():
    assert B._exit_line(_mod({"exit_mode": "band"}), {"exit_mode": "vwap"}) == "vwap"
    assert B._exit_line(_mod({"exit_mode": "vwap"}), {"exit_mode": "band"}) == ""


def test_default_params_plain_value_or_spec():
    assert B._exit_line(_mod({"exit_mode": "vwap"}), {}) == "vwap"                     # NOISE_1_8_CT304H shape
    assert B._exit_line(_mod({"exit_mode": {"default": "vwap", "type": "str"}}), {}) == "vwap"   # NOISE_1_1_NBHD shape


def test_signature_default_then_nothing():
    assert B._exit_line(_mod(sig_default="vwap"), None) == "vwap"
    assert B._exit_line(_mod(), {}) == ""
    assert B._exit_line(_mod({"exit_mode": "Stop / Target"}), {}) == ""              # ENGU's knob of the same name
    assert B._exit_line("no_such_file_anywhere.py", {}) == ""


def test_the_real_555_file_exits_on_the_vwap():
    assert B._exit_line("NOISE_1_8_CT304H_FT.py", {"gate_ratio": 1.15, "tilt_mult": 1.75, "gate_len": 16}) == "vwap"


def _fake(monkeypatch, xline):
    idx = pd.date_range("2025-10-17 09:30", periods=40, freq="5min")
    monkeypatch.setattr(B, "find_master", lambda *a, **k: {"name": "fake NQ 5m", "source": "tv"})
    monkeypatch.setattr(B, "load_master_arrays", lambda m, **k: {"index": idx, "close": np.linspace(1, 2, 40)})
    monkeypatch.setattr(B, "_wants_levels", lambda s: False)
    monkeypatch.setattr(B, "_exit_line", lambda s, p: xline)
    monkeypatch.setattr(B.ae, "run_backtest", lambda *a, **k: {"trades": [(2, 6, 5.0, 1, 25000.0)]})


def test_rows_carry_the_mark_only_when_set(monkeypatch):
    _fake(monkeypatch, "vwap")
    assert B.champion_blotter("X.py", "NQ", "5m", cost_pts=C)[0][0]["exit_line"] == "vwap"
    _fake(monkeypatch, "")
    assert "exit_line" not in B.champion_blotter("X.py", "NQ", "5m", cost_pts=C)[0][0]


def test_a_cache_without_the_column_is_rebuilt_for_a_vwap_run(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    (root / "augur_strategies").mkdir(parents=True)
    (root / "augur_strategies" / "VW.py").write_text("def run_backtest(o): pass\n", encoding="utf-8")
    bdir = tmp_path / "blotters"
    os.makedirs(bdir)
    monkeypatch.setattr(B, "blotter_dir", lambda: str(bdir))
    old = [f for f in B.FIELDS if f != "exit_line"]
    with open(bdir / "run7_NQ_5m.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({"trade_no": 1, "entry_time": "2025-10-17 09:40", "exit_time": "2025-10-17 10:00",
                    "hold_bars": 4, "entry_px": 25000.0, "exit_px": 25005.53, "pnl_pts": 5.0, "pnl_usd": 100,
                    "cum_usd": 100, "side": "long", "size": 1.0})
    _fake(monkeypatch, "vwap")
    pay = {"run_id": 7, "instrument": "NQ", "timeframe": "5m", "strategy": "VW.py", "params": {"a": 1}, "cost_pts": C}
    out = B.load_blotter_rows(str(root), pay, log=lambda *a: None)
    assert out.get("regenerated") and out["rows"][0]["exit_line"] == "vwap"
    out2 = B.load_blotter_rows(str(root), pay, log=lambda *a: None)
    assert not out2.get("regenerated")
    _fake(monkeypatch, "")          # a run that does not exit on the VWAP: its old cache is served as it is
    with open(bdir / "run8_NQ_5m.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({"trade_no": 1, "side": "long"})
    out3 = B.load_blotter_rows(str(root), dict(pay, run_id=8), log=lambda *a: None)
    assert out3["ok"] and not out3.get("regenerated")
