"""Unit tests for api.webull_orders.OrderAdapter — the Webull ORDER adapter.

The Webull SDK is NEVER hit over the network here: OFF mode never imports webull at
all, and every PAPER-mode test monkeypatches OrderAdapter._build_client to return a
MagicMock in place of the real webull.core.client.ApiClient / webull.trade.trade_client.
TradeClient construction, so even the (test-machine-installed) real SDK package is
never asked to make an HTTP call, sign a request, or read a token. No paper or live
credentials exist anywhere in this repo or on the CI box.
"""
import json
import os
from unittest.mock import MagicMock

import pytest

from api import webull_orders as WO


# ── fixtures ────────────────────────────────────────────────────────

def _cfg(tmp_path, mode="OFF", rails=None, **extra):
    cfg = WO.load_config("__no_such_file__")   # defaults only
    cfg["mode"] = mode
    # Tests run at whatever wall-clock time CI happens to execute at -- default the
    # session window wide open so only test_rail_session_window_blocks (which sets
    # its own narrow window) exercises that rail.
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    if rails:
        cfg["rails"].update(rails)
    cfg["state_path"] = str(tmp_path / "state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "KILL")
    cfg.update(extra)
    return cfg


def _write_keys(path, app_key="AK", app_secret="AS"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"app_key": app_key, "app_secret": app_secret}, f)


def _mock_client():
    """A MagicMock standing in for webull.trade.trade_client.TradeClient, wired just
    enough for place_stock_order's happy path (account lookup, order_v3.place_order)
    without touching the real SDK or network. v3 orders are symbol-keyed -- see
    api/webull_orders.py's ORDER API VERSION docstring section -- so there is no
    instrument lookup call to mock any more."""
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1"}]
    }
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _adapter_with_mock_client(monkeypatch, cfg, log=None):
    adapter = WO.OrderAdapter(config=cfg, log=log or (lambda *a, **k: None))
    mock_client = _mock_client()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: mock_client)
    return adapter, mock_client


# ── default OFF sends nothing ────────────────────────────────────────

def test_default_config_is_off(tmp_path):
    cfg = WO.load_config(str(tmp_path / "does_not_exist.json"))
    assert cfg["mode"] == WO.MODE_OFF


def test_off_mode_records_but_sends_nothing(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    rec = adapter.place_stock_order(leg="ORB_1", signal_id="sig-1", symbol="AAPL",
                                    side="BUY", qty=5)
    assert rec["mode"] == "OFF"
    assert rec["sent"] is False
    assert rec["ok"] is True
    st = adapter.status()
    assert st["effective_mode"] == "OFF"
    assert st["last_order"]["sent"] is False


# ── PAPER without creds no-ops (never sends) ─────────────────────────

def test_paper_without_creds_noops(tmp_path):
    cfg = _cfg(tmp_path, mode="PAPER")   # no paper_keys.json written
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mode, reason = adapter.effective_mode()
    assert mode == WO.MODE_OFF
    assert "no paper credentials" in reason
    rec = adapter.place_stock_order(leg="L1", signal_id="sig-2", symbol="MSFT",
                                    side="BUY", qty=3)
    assert rec["sent"] is False
    assert rec["mode"] == "OFF"


# ── PAPER never uses live keys, even when both files exist ───────────

def test_paper_never_falls_back_to_live_keys(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["live_keys_path"], app_key="LIVE_KEY", app_secret="LIVE_SECRET")
    # paper_keys.json deliberately NOT written
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mode, reason = adapter.effective_mode()
    assert mode == WO.MODE_OFF
    assert adapter.status()["paper_credentials_present"] is False
    assert adapter.status()["live_credentials_present"] is True   # sanity: live file IS there
    # And even load_paper_keys() itself must never read the live path.
    assert WO.load_paper_keys(cfg["paper_keys_path"]) is None


def test_paper_keys_placeholder_treated_as_missing(tmp_path):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"], app_key="PASTE_APP_KEY_HERE", app_secret="PASTE_APP_SECRET_HERE")
    assert WO.load_paper_keys(cfg["paper_keys_path"]) is None


# ── PAPER with creds actually sends (via a fully mocked SDK client) ──

def test_paper_with_creds_sends_via_mocked_sdk(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    rec = adapter.place_stock_order(leg="ORB_1", signal_id="sig-3", symbol="AAPL",
                                    side="BUY", qty=2)
    assert rec["mode"] == "PAPER"
    assert rec["sent"] is True
    assert rec["ok"] is True
    mock_client.order_v3.place_order.assert_called_once()
    args, kwargs = mock_client.order_v3.place_order.call_args
    account_id, new_orders = args
    assert account_id == "ACCT1"
    assert new_orders[0]["side"] == "BUY"
    assert new_orders[0]["symbol"] == "AAPL"
    assert new_orders[0]["quantity"] == "2"
    assert new_orders[0]["client_order_id"] == "sig-3"


# ── LIVE refuses without the arm file (even with mode=LIVE + live creds) ──

def test_live_refuses_without_arm_file(tmp_path):
    cfg = _cfg(tmp_path, mode="LIVE")
    _write_keys(cfg["live_keys_path"])
    # arm_live_file deliberately not created
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mode, reason = adapter.effective_mode()
    assert mode == WO.MODE_OFF
    assert "arm file missing" in reason
    rec = adapter.place_stock_order(leg="L1", signal_id="sig-4", symbol="AAPL",
                                    side="BUY", qty=1)
    assert rec["mode"] == "OFF"
    assert rec["sent"] is False


def test_live_refuses_without_config_setting_even_with_arm_file(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")   # config setting never flipped to LIVE
    _write_keys(cfg["live_keys_path"])
    with open(cfg["arm_live_file"], "w", encoding="utf-8") as f:
        f.write("armed")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mode, _ = adapter.effective_mode()
    assert mode == WO.MODE_OFF


def test_live_armed_with_both_gates_satisfied(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="LIVE")
    _write_keys(cfg["live_keys_path"])
    with open(cfg["arm_live_file"], "w", encoding="utf-8") as f:
        f.write("armed")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mode, reason = adapter.effective_mode()
    assert mode == WO.MODE_LIVE
    assert "armed" in reason.lower()


# ── idempotent client_order_id across a simulated restart ────────────

def test_idempotent_ids_across_restart(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter1 = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    rec1 = adapter1.place_stock_order(leg="L1", signal_id="sig-restart", symbol="AAPL",
                                      side="BUY", qty=4)
    assert rec1.get("duplicate") is not True

    # Simulate a process restart: a BRAND NEW OrderAdapter, same state file on disk.
    adapter2 = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    rec2 = adapter2.place_stock_order(leg="L1", signal_id="sig-restart", symbol="AAPL",
                                      side="BUY", qty=4)
    assert rec2["duplicate"] is True
    assert rec2["client_order_id"] == rec1["client_order_id"]
    # Only ONE belief mutation should have happened (not double-applied on replay).
    assert adapter2._state["believed_positions"]["L1"]["qty"] == 4


def test_client_order_id_stable_and_bounded():
    short = WO._sanitize_client_order_id("abc-123")
    assert short == "abc-123"
    long_id = "x" * 100
    hashed = WO._sanitize_client_order_id(long_id)
    assert len(hashed) <= 40
    assert WO._sanitize_client_order_id(long_id) == hashed   # deterministic


# ── each rail blocks ──────────────────────────────────────────────────

def test_rail_max_shares_per_leg_blocks(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF", rails={"max_shares_per_leg": 5})
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    rec = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=10)
    assert rec["mode"] == "BLOCKED"
    assert "max_shares_per_leg" in rec["reason"]


def test_rail_max_total_position_blocks(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF", rails={"max_shares_per_leg": 100,
                                            "max_total_position_shares": 8,
                                            "one_open_position_per_leg": False})
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    r1 = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=5)
    assert r1["mode"] == "OFF"
    r2 = adapter.place_stock_order(leg="L2", signal_id="s2", symbol="MSFT", side="BUY", qty=5)
    assert r2["mode"] == "BLOCKED"
    assert "max_total_position_shares" in r2["reason"]


def test_rail_daily_loss_limit_blocks(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF", rails={"daily_loss_limit_usd": 100})
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    adapter.update_daily_pnl(-150)
    rec = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=1)
    assert rec["mode"] == "BLOCKED"
    assert "daily loss limit" in rec["reason"]


def test_rail_session_window_blocks(tmp_path, monkeypatch):
    # Pin the clock rather than picking a narrow real-world window -- a fixed window
    # like "00:00"-"00:01" is flaky (it really did land on the test run once, at
    # 2026-09-14 00:00 NY). Freeze "now" at 03:00 NY, well outside 09:30-16:00.
    import datetime as _dt
    frozen = _dt.datetime(2026, 1, 5, 3, 0, 0)
    monkeypatch.setattr(WO, "_now_ny", lambda: frozen)
    cfg = _cfg(tmp_path, mode="OFF", rails={"session_start": "09:30", "session_end": "16:00"})
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    rec = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=1)
    assert rec["mode"] == "BLOCKED"
    assert "session window" in rec["reason"]


def test_rail_kill_file_blocks(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    with open(cfg["kill_file"], "w", encoding="utf-8") as f:
        f.write("stop")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    rec = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=1)
    assert rec["mode"] == "BLOCKED"
    assert "kill file" in rec["reason"]


def test_rail_kill_file_does_not_block_close_intent(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=1)
    with open(cfg["kill_file"], "w", encoding="utf-8") as f:
        f.write("stop")
    rec = adapter.place_stock_order(leg="L1", signal_id="s2", symbol="AAPL", side="SELL",
                                    qty=1, intent="CLOSE")
    assert rec["mode"] == "OFF"    # not blocked -- flattening always goes through


def test_rail_one_open_position_per_leg_blocks(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=1)
    rec = adapter.place_stock_order(leg="L1", signal_id="s2", symbol="AAPL", side="BUY", qty=1)
    assert rec["mode"] == "BLOCKED"
    assert "one_open_position_per_leg" in rec["reason"]
    # Closing the leg should clear it so a NEW open is allowed again.
    adapter.place_stock_order(leg="L1", signal_id="s3", symbol="AAPL", side="SELL",
                              qty=1, intent="CLOSE")
    assert "L1" not in adapter._state["open_legs"]
    rec2 = adapter.place_stock_order(leg="L1", signal_id="s4", symbol="AAPL", side="BUY", qty=1)
    assert rec2["mode"] == "OFF"


# ── reconcile mismatch halts entries ──────────────────────────────────

def test_reconcile_mismatch_halts_new_entries(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=3)

    result = adapter.reconcile(broker_positions_fn=lambda: {"AAPL": 999})
    assert result["ok"] is False
    assert result["mismatches"]
    assert adapter._halted is True

    rec = adapter.place_stock_order(leg="L2", signal_id="s2", symbol="MSFT", side="BUY", qty=1)
    assert rec["mode"] == "BLOCKED"
    assert "halted" in rec["reason"]
    # A close should still be allowed through even while halted.
    rec_close = adapter.place_stock_order(leg="L1", signal_id="s3", symbol="AAPL",
                                          side="SELL", qty=3, intent="CLOSE")
    assert rec_close["mode"] != "BLOCKED"


def test_reconcile_matching_positions_ok(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=3)
    result = adapter.reconcile(broker_positions_fn=lambda: {"AAPL": 3})
    assert result["ok"] is True
    assert adapter._halted is False


def test_reconcile_returns_none_in_off_mode(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    assert adapter.reconcile() is None


# ── futures path raises "not enabled" ─────────────────────────────────

def test_futures_place_order_not_enabled(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    with pytest.raises(NotImplementedError, match="not enabled|NOT ENABLED"):
        adapter.place_futures_order(leg="L1", signal_id="s1", symbol="MNQ", side="BUY", qty=1)


def test_futures_resolve_contract_not_enabled(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    with pytest.raises(NotImplementedError):
        adapter.resolve_futures_contract("MNQ")


# ── validation guards ──────────────────────────────────────────────────

def test_invalid_side_rejected(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    with pytest.raises(ValueError):
        adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="YOLO", qty=1)


def test_invalid_intent_rejected(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    with pytest.raises(ValueError):
        adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY",
                                  qty=1, intent="MAYBE")


# ── status dict shape (what a future web tab would read) ──────────────

def test_status_shape(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    st = adapter.status()
    for key in ("requested_mode", "effective_mode", "mode_reason", "environment",
               "paper_credentials_present", "live_credentials_present", "live_armed",
               "kill_file_present", "halted", "halt_reason", "last_order", "last_error",
               "daily_pnl", "open_legs", "believed_positions", "futures_enabled", "rails"):
        assert key in st


def test_get_status_module_function(tmp_path):
    cfg = _cfg(tmp_path, mode="OFF")
    st = WO.get_status(config=cfg)
    assert st["effective_mode"] == "OFF"


# ── config loading is defensive ───────────────────────────────────────

def test_load_config_missing_file_is_off(tmp_path):
    cfg = WO.load_config(str(tmp_path / "nope.json"))
    assert cfg["mode"] == WO.MODE_OFF
    assert cfg["rails"] == WO.DEFAULT_RAILS


def test_load_config_malformed_file_does_not_raise(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    cfg = WO.load_config(str(p))
    assert cfg["mode"] == WO.MODE_OFF
