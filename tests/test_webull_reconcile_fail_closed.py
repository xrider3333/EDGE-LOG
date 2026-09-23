"""api.webull_orders.OrderAdapter.reconcile() hardening (2026-09-14, FIX 2).

Covers what tests/test_webull_orders.py's existing reconcile tests do NOT: a broker
read failure must fail CLOSED (halt new entries) instead of silently returning None,
a halt reconcile() itself raised must self-clear once a later reconcile succeeds
(but a kill-file halt must NEVER be cleared this way), the comparison basis is now
"orders that actually reached the broker" (broker_sent_positions) rather than
believed_positions (which also absorbs OFF-mode would-be orders), and the comparison
is scoped to one account_id.

Same no-network discipline as test_webull_orders.py: OFF mode never imports webull;
PAPER-mode tests monkeypatch OrderAdapter._build_client with a MagicMock so even the
real installed SDK package is never asked to make an HTTP call.
"""
import json
from unittest.mock import MagicMock

import pytest

from api import webull_orders as WO


def _cfg(tmp_path, mode="PAPER", **extra):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "KILL")
    cfg.update(extra)
    return cfg


def _write_keys(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)


def _mock_client():
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _paper_adapter(tmp_path, monkeypatch, log=None):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    adapter = WO.OrderAdapter(config=cfg, log=log or (lambda *a, **k: None))
    mock_client = _mock_client()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: mock_client)
    return adapter, mock_client


# ── fail-closed on a broker read failure ────────────────────────────────────────────

def test_read_failure_halts_new_entries(tmp_path, monkeypatch):
    adapter, _ = _paper_adapter(tmp_path, monkeypatch)

    def boom():
        raise RuntimeError("connection reset")
    result = adapter.reconcile(broker_positions_fn=boom)

    assert result["ok"] is False
    assert "can't read positions at Webull" in result["error"]
    assert adapter._halted is True
    assert adapter._halt_source == "reconcile"
    # status() surfaces it for the published doc's broker block.
    st = adapter.status()
    assert st["halted"] is True
    assert st["last_reconcile_result"]["ok"] is False
    assert st["last_reconcile_at"] is not None


def test_read_failure_blocks_open_but_not_close(tmp_path, monkeypatch):
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="QQQ", side="BUY", qty=5)

    def boom():
        raise TimeoutError("read timed out")
    adapter.reconcile(broker_positions_fn=boom)
    assert adapter._halted is True

    blocked = adapter.place_stock_order(leg="L2", signal_id="s2", symbol="QQQ",
                                        side="BUY", qty=1)
    assert blocked["mode"] == "BLOCKED"
    assert "halted" in blocked["reason"]

    exit_rec = adapter.place_stock_order(leg="L1", signal_id="s3", symbol="QQQ",
                                         side="SELL", qty=5, intent="CLOSE")
    assert exit_rec["mode"] != "BLOCKED", "a flatten must never be blocked by the reconcile halt"


def test_timeout_error_produces_readable_reason(tmp_path, monkeypatch):
    adapter, _ = _paper_adapter(tmp_path, monkeypatch)

    def timeout():
        raise TimeoutError("upstream read timed out after 25s")
    result = adapter.reconcile(broker_positions_fn=timeout)
    assert "can't read positions at Webull" in result["error"]
    assert "TimeoutError" in result["error"]


# ── mismatch reason is readable, and includes the diff ──────────────────────────────

def test_mismatch_reason_names_symbol_and_both_quantities(tmp_path, monkeypatch):
    adapter, _ = _paper_adapter(tmp_path, monkeypatch)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="QQQ", side="BUY", qty=5)
    result = adapter.reconcile(broker_positions_fn=lambda: {"QQQ": 12})
    assert result["ok"] is False
    assert adapter._halt_reason is not None
    assert "QQQ" in adapter._halt_reason
    assert "12" in adapter._halt_reason
    assert "5" in adapter._halt_reason


# ── recovery clears a reconcile-caused halt, never a kill-file halt ─────────────────

def test_recovery_clears_a_reconcile_halt(tmp_path, monkeypatch):
    adapter, _ = _paper_adapter(tmp_path, monkeypatch)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="QQQ", side="BUY", qty=5)

    bad = adapter.reconcile(broker_positions_fn=lambda: {"QQQ": 999})
    assert bad["ok"] is False
    assert adapter._halted is True

    good = adapter.reconcile(broker_positions_fn=lambda: {"QQQ": 5})
    assert good["ok"] is True
    assert adapter._halted is False
    assert adapter._halt_reason is None
    assert adapter._halt_source is None

    rec = adapter.place_stock_order(leg="L2", signal_id="s2", symbol="QQQ", side="BUY", qty=1)
    assert rec["mode"] != "BLOCKED"


def test_recovery_never_clears_a_kill_file_halt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="PAPER")
    _write_keys(cfg["paper_keys_path"])
    with open(cfg["kill_file"], "w", encoding="utf-8") as f:
        f.write("stop")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mock_client = _mock_client()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: mock_client)
    assert adapter._halted is True
    assert adapter._halt_source == "kill_file"

    # A reconcile that finds everything matching (both sides empty) must NOT clear a
    # kill-file halt -- only removing the kill file (and a fresh _check_rails call)
    # may do that.
    result = adapter.reconcile(broker_positions_fn=lambda: {})
    assert result["ok"] is True
    assert adapter._halted is True
    assert adapter._halt_source == "kill_file"


# ── "sent" positions exclude OFF-mode would-be orders ───────────────────────────────

def test_off_mode_orders_never_poison_the_reconcile_baseline(tmp_path, monkeypatch):
    """An OFF-era phantom order must not surface as a mismatch the moment the config
    flips to PAPER -- see OrderAdapter.reconcile()'s own docstring for why comparing
    against believed_positions (which DOES include OFF) would have false-positived
    here."""
    cfg = _cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    off_rec = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="QQQ",
                                        side="BUY", qty=7)
    assert off_rec["mode"] == "OFF"
    assert adapter._state["believed_positions"]["L1"]["qty"] == 7
    assert adapter._state.get("broker_sent_positions", {}) == {}, (
        "an OFF-mode order must never populate broker_sent_positions")

    # Flip to PAPER on a FRESH adapter reading the same on-disk state (mirrors a
    # config edit + restart) -- the broker genuinely holds nothing.
    cfg2 = dict(cfg)
    cfg2["mode"] = "PAPER"
    _write_keys(cfg2["paper_keys_path"])
    adapter2 = WO.OrderAdapter(config=cfg2, log=lambda *a, **k: None)
    monkeypatch.setattr(adapter2, "_build_client", lambda mode: _mock_client())

    result = adapter2.reconcile(broker_positions_fn=lambda: {})
    assert result["ok"] is True, "the OFF-era phantom order must be ignored, not flagged"
    assert adapter2._halted is False


def test_only_ok_paper_orders_count_as_sent(tmp_path, monkeypatch):
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch)
    mock_client.order_v3.place_order.side_effect = RuntimeError("rejected")
    rec = adapter.place_stock_order(leg="L1", signal_id="s1", symbol="QQQ", side="BUY", qty=5)
    assert rec["ok"] is False
    assert adapter._state.get("broker_sent_positions", {}) == {}, (
        "a failed send must not be counted as sent to the broker")


# ── per-account scoping ──────────────────────────────────────────────────────────────

def test_sent_position_under_a_different_account_is_excluded(tmp_path, monkeypatch):
    adapter, _ = _paper_adapter(tmp_path, monkeypatch)
    adapter.place_stock_order(leg="L1", signal_id="s1", symbol="QQQ", side="BUY", qty=5)
    assert adapter._state["broker_sent_positions"]["L1"]["account_id"] == "ACCT1"

    # Reconcile called against a DIFFERENT account_id (e.g. after an account reset)
    # must not fold the OLD account's sent lot into the new account's comparison.
    result = adapter.reconcile(account_id="ACCT2", broker_positions_fn=lambda: {})
    assert result["ok"] is True
    assert result["shadow_sent"] == {}


# ── status() shape ───────────────────────────────────────────────────────────────────

def test_status_carries_new_reconcile_fields_without_dropping_old_ones(tmp_path, monkeypatch):
    adapter, _ = _paper_adapter(tmp_path, monkeypatch)
    st = adapter.status()
    for key in ("requested_mode", "effective_mode", "halted", "halt_reason", "last_order",
               "daily_pnl", "believed_positions", "rails",
               "last_reconcile_at", "last_reconcile_result", "broker_sent_positions"):
        assert key in st
    assert st["last_reconcile_at"] is None   # never reconciled yet
