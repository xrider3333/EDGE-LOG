"""B1 + B2 of the 11-04 live audit (owner GO A): LIVE has its own state file and refuses
to arm over paper shares; a disarm while LIVE holds shares keeps exits going (close-only)."""
import json
import os

from api import webull_orders as WO
import sys
sys.path.insert(0, os.path.dirname(__file__))
from test_webull_orders import _cfg, _write_keys  # noqa: E402


def _state(path, held):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"broker_sent_positions": {k: {"symbol": "QQQ", "qty": q} for k, q in held.items()}}, f)


def _live(tmp_path, armed=True):
    cfg = _cfg(tmp_path, mode="LIVE", rails={"live_legs": ["NOISE"]})
    cfg.setdefault("account", {})["stock_last4"] = "1234"
    _write_keys(cfg["live_keys_path"])
    if armed:
        open(cfg["arm_live_file"], "w").close()
    return cfg


def test_live_uses_its_own_state_file(tmp_path):
    cfg = _live(tmp_path)
    a = WO.OrderAdapter(config=cfg, log=lambda *x, **k: None)
    assert a._state_path() == str(tmp_path / "state.LIVE.json")
    p = WO.OrderAdapter(config=_cfg(tmp_path, mode="PAPER"), log=lambda *x, **k: None)
    assert p._state_path() == str(tmp_path / "state.json")


def test_live_refuses_to_arm_while_paper_holds_shares(tmp_path):
    cfg = _live(tmp_path)
    _state(cfg["state_path"], {"NOISE": 15})
    mode, why = WO.OrderAdapter(config=cfg, log=lambda *x, **k: None).effective_mode()
    assert mode == WO.MODE_OFF and "PAPER book still holds" in why
    _state(cfg["state_path"], {"NOISE": 0})
    mode, _ = WO.OrderAdapter(config=cfg, log=lambda *x, **k: None).effective_mode()
    assert mode == WO.MODE_LIVE


def test_disarm_while_live_holds_is_close_only(tmp_path):
    cfg = _live(tmp_path, armed=False)
    _state(str(tmp_path / "state.LIVE.json"), {"NOISE": 1})
    a = WO.OrderAdapter(config=cfg, log=lambda *x, **k: None)
    mode, why = a.effective_mode()
    assert mode == WO.MODE_LIVE and why.startswith("CLOSE-ONLY")
    rec = a.place_stock_order(leg="NOISE", signal_id="s1", symbol="QQQ", side="BUY", qty=1,
                              intent="OPEN")
    assert rec["ok"] is False and rec["sent"] is False and "CLOSE-ONLY" in rec["reason"]


def test_disarm_while_flat_is_off(tmp_path):
    cfg = _live(tmp_path, armed=False)
    mode, _ = WO.OrderAdapter(config=cfg, log=lambda *x, **k: None).effective_mode()
    assert mode == WO.MODE_OFF


# LIVE SIZE (2026-11-19): LIVE opens fail closed without today's equity (the adapter's % daily
# rail) -- these tests are about other LIVE rules, so every adapter here has read it today.
import pytest as _pytest_live_eq  # noqa: E402


@_pytest_live_eq.fixture(autouse=True)
def _live_equity_read_today(monkeypatch):
    monkeypatch.setattr(WO.OrderAdapter, "_equity_today",
                        {"day": WO._now_ny().strftime("%Y-%m-%d"), "equity": 1_000_000.0},
                        raising=False)
