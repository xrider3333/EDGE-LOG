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
        # account_class is what _account_id() now selects on (default purpose "stock"
        # wants INDIVIDUAL_CASH, see api/webull_orders.py's DEFAULT_ACCOUNT_SELECT) --
        # without it, a single-account mock like this used to still work because the
        # old code just took accts[0] unconditionally.
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_CASH"}]
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
    assert len(hashed) <= 32
    assert WO._sanitize_client_order_id(long_id) == hashed   # deterministic


def test_client_order_id_fits_webulls_documented_32_characters():
    """Webull's US stock order reference: client_order_id "max 32 chars, must be unique per
    account" (the 40 once used here is the SDK's Hong Kong docstring)."""
    assert WO.CLIENT_ORDER_ID_MAX == 32
    exactly = "a" * 32
    assert WO._sanitize_client_order_id(exactly) == exactly
    over = WO._sanitize_client_order_id("a" * 33)
    assert len(over) == 32 and over.isalnum() and over != "a" * 32
    # ids that differ only in characters the sanitizer maps still hash apart once too long
    assert (WO._sanitize_client_order_id("q" * 30 + ":1:") !=
            WO._sanitize_client_order_id("q" * 30 + "|1|"))


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


def test_load_config_default_account_selection_is_individual_cash(tmp_path):
    cfg = WO.load_config(str(tmp_path / "nope.json"))
    assert cfg["account"] == WO.DEFAULT_ACCOUNT_SELECT
    assert cfg["account"]["stock"] == "INDIVIDUAL_CASH"


def test_load_config_account_override_merges_not_replaces(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"account": {"stock": "INDIVIDUAL_MARGIN"}}), encoding="utf-8")
    cfg = WO.load_config(str(p))
    assert cfg["account"]["stock"] == "INDIVIDUAL_MARGIN"
    assert cfg["account"]["futures"] == "FUTURES"     # untouched default survives the merge


# ── order_status_fields() -- v3 orders[] nesting (first LIVE paper smoke test,
# 2026-09-14 12:04 ET) ──────────────────────────────────────────────────────────────
# Webull's v3 order-detail/place/cancel responses nest every per-order field under
# response["orders"][] -- the combo wrapper's OWN top level only ever carries
# client_order_id/combo_order_id/combo_type. This is the exact shape the real sandbox
# returned that day (ids redacted) -- see api/webull_orders.py's order_status_fields()
# docstring and developer.webull.com/apis/docs/reference/order-detail/.

_REAL_ORDER_DETAIL_RESPONSE = {
    "client_order_id": "SMOKE-abc123", "combo_order_id": "COMBO-xyz",
    "combo_type": "NORMAL",
    "orders": [{
        "client_order_id": "SMOKE-abc123", "commission": {}, "entrust_type": "QTY",
        "fees": [], "filled_quantity": "0", "instrument_type": "EQUITY",
        "limit_price": "354.62", "order_id": "ORDID-1", "order_type": "LIMIT",
        "place_time": "1789401892218", "place_time_at": "2026-09-14T16:04:52.218Z",
        "side": "BUY", "status": "SUBMITTED", "support_trading_session": "CORE",
        "symbol": "QQQ", "time_in_force": "DAY", "total_quantity": "1",
    }],
}


def test_order_status_fields_reads_the_nested_orders_list():
    fields = WO.order_status_fields(_REAL_ORDER_DETAIL_RESPONSE, "SMOKE-abc123")
    assert fields["status"] == "SUBMITTED"
    assert fields["filled_quantity"] == "0"
    assert fields["commission"] == {}
    assert fields["fees"] == []


def test_order_status_fields_top_level_never_carries_status():
    # The combo wrapper's OWN top level has no "status" key -- confirms the bug this
    # fixes: reading response.get("status") directly (or WO._as_list(resp)[0], which
    # for this dict shape just re-wraps the WHOLE combo as one list item since
    # WO._as_list only unwraps "data"/"items"/"positions"/"list", never "orders") always
    # returned None, which is what the smoke test's "saw None" FAIL printed.
    assert "status" not in _REAL_ORDER_DETAIL_RESPONSE


def test_order_status_fields_matches_by_client_order_id_not_position():
    multi = {"orders": [
        {"client_order_id": "OTHER", "status": "FILLED"},
        {"client_order_id": "WANTED", "status": "CANCELLED"},
    ]}
    assert WO.order_status_fields(multi, "WANTED")["status"] == "CANCELLED"
    assert WO.order_status_fields(multi, "OTHER")["status"] == "FILLED"


def test_order_status_fields_falls_back_to_first_when_no_coid_given():
    multi = {"orders": [{"client_order_id": "A", "status": "SUBMITTED"}]}
    assert WO.order_status_fields(multi)["status"] == "SUBMITTED"


def test_order_status_fields_falls_back_to_top_level_when_orders_absent():
    flat = {"status": "CANCELLED"}
    assert WO.order_status_fields(flat, "anything")["status"] == "CANCELLED"


def test_order_status_fields_finds_documented_filled_price_field():
    # "filled_price" is the field name documented at developer.webull.com/apis/docs/
    # reference/order-detail/ ("Average transaction price of the filled quantity") --
    # NOT avg_price/avgFillPrice/etc, which api/qqq_exec.py's OLD hand-rolled scan
    # guessed at instead (and never actually listed "filled_price" itself).
    resp = {"orders": [{"client_order_id": "X", "status": "FILLED",
                        "filled_price": "11.05"}]}
    assert WO.order_status_fields(resp, "X")["filled_price"] == "11.05"


def test_fees_total_sums_fee_breakdown_list_and_commission_object():
    fields = {"fees": [{"type": "FINRA_CAT_REGULATORY_FEE", "actual_value": "0.02"},
                       {"type": "SEC_FEE", "actual_value": "0.01"}],
             "commission": {"actual_commission": "0.0"}}
    assert WO.fees_total(fields) == pytest.approx(0.03)


def test_fees_total_handles_empty_fees_and_commission():
    assert WO.fees_total({"fees": [], "commission": {}}) == 0.0


# ── deliberate account selection (first LIVE paper smoke test, 2026-09-14) ─────────
# _account_id() used to take accts[0] unconditionally. The real sandbox account list
# came back Individual Margin, Futures, Individual Cash, Events, Crypto -- Individual
# Cash (the one stock orders must use) sits in the MIDDLE, not first, and a paper
# account RESET renumbers accounts on top of that.

def _accounts_real_order(cash_id="CASH_ID"):
    """Same order/labelling the real sandbox account list came back in that day."""
    return [
        {"account_id": "MARGIN_ID", "account_number": "111100000000HM55",
         "account_class": "INDIVIDUAL_MARGIN", "account_type": "MARGIN"},
        {"account_id": "FUT_ID", "account_number": "222200000000HAZ7",
         "account_class": "FUTURES", "account_type": "MARGIN"},
        {"account_id": cash_id, "account_number": "333300000000HLZ5",
         "account_class": "INDIVIDUAL_CASH", "account_type": "CASH"},
        {"account_id": "EVENTS_ID", "account_number": "444400000000HEG2",
         "account_class": "EVENTS_CASH", "account_type": "CASH"},
        {"account_id": "CRYPTO_ID", "account_number": "555500000000HE74",
         "account_class": "CRYPTO", "account_type": "CASH"},
    ]


def test_account_selection_picks_individual_cash_regardless_of_list_order(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": _accounts_real_order("CASH_ID")}

    rec = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="AAPL", side="BUY", qty=1)
    assert rec["mode"] == "PAPER" and rec["ok"] is True
    args, _ = mock_client.order_v3.place_order.call_args
    account_id, _new_orders = args
    assert account_id == "CASH_ID", "must select Individual Cash, not accts[0] (Individual Margin)"


def test_account_selection_raises_when_class_not_found(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "MARGIN_ID", "account_class": "INDIVIDUAL_MARGIN"}]}
    with pytest.raises(RuntimeError, match="no account matches"):
        adapter._account_id("PAPER", mock_client)


def test_account_selection_raises_when_ambiguous(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "A1", "account_class": "INDIVIDUAL_CASH"},
                 {"account_id": "A2", "account_class": "INDIVIDUAL_CASH"}]}
    with pytest.raises(RuntimeError, match="ambiguous"):
        adapter._account_id("PAPER", mock_client)


def test_account_selection_explicit_last4_override(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    cfg["account"]["stock_last4"] = "HAZ7"        # deliberately pin the FUTURES-labelled one
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": _accounts_real_order()}
    assert adapter._account_id("PAPER", mock_client) == "FUT_ID"


def test_account_selection_configured_class_change_invalidates_cache(tmp_path, monkeypatch):
    """A disk-cached id resolved for one class must never be reused once the config
    asks for a DIFFERENT class."""
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": _accounts_real_order("CASH_ID")}
    assert adapter._account_id("PAPER", mock_client) == "CASH_ID"

    # A FRESH adapter instance (simulated restart) reading the SAME on-disk state, now
    # configured for a DIFFERENT class -- must re-resolve live, not reuse CASH_ID.
    cfg2 = dict(cfg)
    cfg2["account"] = {"stock": "FUTURES"}
    adapter2 = WO.OrderAdapter(config=cfg2, log=lambda *a, **k: None)
    monkeypatch.setattr(adapter2, "_build_client", lambda mode: mock_client)
    assert adapter2._account_id("PAPER", mock_client) == "FUT_ID"


def test_account_selection_disk_cache_refreshed_after_account_reset(tmp_path, monkeypatch):
    """A paper-account RESET renumbers accounts (same class, new account_id) -- the
    NEXT process (fresh OrderAdapter, same on-disk state) must pick up the new id live,
    not keep trusting the pre-reset one."""
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": _accounts_real_order("CASH_ID_OLD")}
    assert adapter._account_id("PAPER", mock_client) == "CASH_ID_OLD"

    # Simulated restart with a FRESH adapter (same state file) after Webull reset the
    # paper account -- same class, brand new account_id; the old id is gone entirely.
    adapter2 = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mock_client2 = MagicMock()
    mock_client2.account_v2.get_account_list.return_value.json.return_value = {
        "data": _accounts_real_order("CASH_ID_NEW")}
    monkeypatch.setattr(adapter2, "_build_client", lambda mode: mock_client2)
    assert adapter2._account_id("PAPER", mock_client2) == "CASH_ID_NEW"


def test_account_selection_falls_back_to_disk_cache_when_live_fetch_fails(tmp_path, monkeypatch):
    """The disk cache is a last resort for a FAILED live call (network/SDK error), and
    only when its stored class still matches what's configured now."""
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": _accounts_real_order("CASH_ID")}
    assert adapter._account_id("PAPER", mock_client) == "CASH_ID"

    adapter2 = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    broken_client = MagicMock()
    broken_client.account_v2.get_account_list.side_effect = RuntimeError("network down")
    monkeypatch.setattr(adapter2, "_build_client", lambda mode: broken_client)
    assert adapter2._account_id("PAPER", broken_client) == "CASH_ID"


def test_account_selection_disk_cache_ignored_when_last4_override_added(tmp_path, monkeypatch):
    """A disk-cached id resolved under the CLASS-based default must not be resurrected
    to answer a DIFFERENT selector (a newly-added last4 override) just because a naive
    comparison only checked the resolved CLASS -- caught in review: comparing on class
    alone, this scenario would wrongly hand back CASH_ID (cached under "class:
    INDIVIDUAL_CASH") to satisfy a "last4:HAZ7" selector it was never resolved under,
    even though CASH_ID isn't even the HAZ7 account."""
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter, mock_client = _adapter_with_mock_client(monkeypatch, cfg)
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": _accounts_real_order("CASH_ID")}
    assert adapter._account_id("PAPER", mock_client) == "CASH_ID"
    # disk cache now holds {"account_id": "CASH_ID", "selector": "class:INDIVIDUAL_CASH"}

    # A fresh adapter, SAME disk state, now configured with a last4 override -- but its
    # OWN live call fails. The cache was tagged under the OLD class-based selector, not
    # this NEW last4-based one, so it must NOT be used to answer it.
    cfg2 = dict(cfg)
    cfg2["account"] = {"stock_last4": "HAZ7"}
    adapter2 = WO.OrderAdapter(config=cfg2, log=lambda *a, **k: None)
    broken_client = MagicMock()
    broken_client.account_v2.get_account_list.side_effect = RuntimeError("network down")
    monkeypatch.setattr(adapter2, "_build_client", lambda mode: broken_client)
    with pytest.raises(RuntimeError):
        adapter2._account_id("PAPER", broken_client)


def test_account_selection_live_fetch_fails_and_no_usable_cache_raises(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    broken_client = MagicMock()
    broken_client.account_v2.get_account_list.side_effect = RuntimeError("network down")
    monkeypatch.setattr(adapter, "_build_client", lambda mode: broken_client)
    with pytest.raises(RuntimeError):
        adapter._account_id("PAPER", broken_client)
