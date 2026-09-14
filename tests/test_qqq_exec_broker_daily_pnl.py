"""Two defects folded into the FIX 1/FIX 2 work (found while reviewing the ORDERS
card, v73.790):

1) api.webull_orders.OrderAdapter.update_daily_pnl() existed but nothing ever called
   it, so daily_loss_limit_usd could never trip for the broker mirror. Wired via
   api/qqq_exec.py's _sync_broker_daily_pnl (preferred source: today's broker fills
   from broker_orders.csv, see _broker_realized_today; fallback: the shadow book's
   own today figures) -- see test_a_losing_day_crosses_the_limit_and_blocks_opens
   below for the end-to-end rail check.
2) broker.last_order had no timestamp -- _build_broker_status now adds
   last_order.ts_et (ISO-8601 US/Eastern), a NEW field alongside the existing ones
   (leg/side/qty/mode/ok/reason) the web tab already reads -- see
   test_last_order_carries_an_iso_et_timestamp.

No real Firestore/Webull network anywhere.
"""
import csv
import json
import time as real_time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731


def _patch_qqq_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _write_broker_rows(path, rows):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        for r in rows:
            row = {c: "" for c in qe.BROKER_ORDER_COLS}
            row.update(r)
            w.writerow(row)


def _row(ts, leg, intent, side, shares, broker_fill_px="", shadow_px="500.0",
        mode="PAPER", ok="True"):
    return {"ts_et": ts, "leg": leg, "intent": intent, "side": side, "shares": shares,
           "mode": mode, "ok": ok, "sent": "True", "shadow_px": shadow_px,
           "broker_fill_px": broker_fill_px}


# ── _broker_realized_today: FIFO pairing off broker_orders.csv ─────────────────────

def test_realized_uses_broker_fill_price_when_present(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    _write_broker_rows(qe.BROKER_ORDERS_CSV, [
        _row("2026-09-14 09:31:00", "ORB", "OPEN", "BUY", 5, broker_fill_px="500.00"),
        _row("2026-09-14 10:00:00", "ORB", "CLOSE", "SELL", 5, broker_fill_px="503.00"),
    ])
    realized, any_priced = qe._broker_realized_today("2026-09-14", log=NOOP)
    assert any_priced is True
    assert realized == pytest.approx(15.0)   # (503-500) * 5


def test_realized_falls_back_to_shadow_px_for_a_row_missing_broker_fill_price(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    _write_broker_rows(qe.BROKER_ORDERS_CSV, [
        _row("2026-09-14 09:31:00", "ORB", "OPEN", "BUY", 5, broker_fill_px="", shadow_px="500.0"),
        _row("2026-09-14 10:00:00", "ORB", "CLOSE", "SELL", 5, broker_fill_px="", shadow_px="502.0"),
    ])
    realized, any_priced = qe._broker_realized_today("2026-09-14", log=NOOP)
    assert any_priced is False   # neither row had a REAL broker fill price
    assert realized == pytest.approx(10.0)


def test_realized_ignores_off_mode_and_not_ok_rows(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    _write_broker_rows(qe.BROKER_ORDERS_CSV, [
        _row("2026-09-14 09:00:00", "ORB", "OPEN", "BUY", 5, broker_fill_px="900.00", mode="OFF"),
        _row("2026-09-14 09:05:00", "ORB", "CLOSE", "SELL", 5, broker_fill_px="1.00", mode="OFF"),
        _row("2026-09-14 09:10:00", "NOISE", "OPEN", "BUY", 3, broker_fill_px="500.00", ok="False"),
        _row("2026-09-14 09:31:00", "ENGUQ", "OPEN", "BUY", 5, broker_fill_px="500.00"),
        _row("2026-09-14 10:00:00", "ENGUQ", "CLOSE", "SELL", 5, broker_fill_px="504.00"),
    ])
    realized, any_priced = qe._broker_realized_today("2026-09-14", log=NOOP)
    assert any_priced is True
    assert realized == pytest.approx(20.0)   # only the ENGUQ PAPER/ok round trip counts


def test_realized_ignores_rows_from_a_different_day(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    _write_broker_rows(qe.BROKER_ORDERS_CSV, [
        _row("2026-09-13 09:31:00", "ORB", "OPEN", "BUY", 5, broker_fill_px="500.00"),
        _row("2026-09-13 10:00:00", "ORB", "CLOSE", "SELL", 5, broker_fill_px="600.00"),
    ])
    realized, any_priced = qe._broker_realized_today("2026-09-14", log=NOOP)
    assert realized == 0.0
    assert any_priced is False


def test_realized_handles_a_multi_part_close(tmp_path, monkeypatch):
    """A leg opened once and closed across TWO partial CLOSE mirrors (ninjatrader
    signal_source mode's partial exits) must not lose the second reduction."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    _write_broker_rows(qe.BROKER_ORDERS_CSV, [
        _row("2026-09-14 09:31:00", "ORB", "OPEN", "BUY", 10, broker_fill_px="500.00"),
        _row("2026-09-14 09:45:00", "ORB", "CLOSE", "SELL", 4, broker_fill_px="510.00"),
        _row("2026-09-14 10:00:00", "ORB", "CLOSE", "SELL", 6, broker_fill_px="505.00"),
    ])
    realized, any_priced = qe._broker_realized_today("2026-09-14", log=NOOP)
    assert any_priced is True
    expected = (510.0 - 500.0) * 4 + (505.0 - 500.0) * 6
    assert realized == pytest.approx(expected)


def test_realized_missing_csv_is_zero_not_an_error(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    realized, any_priced = qe._broker_realized_today("2026-09-14", log=NOOP)
    assert realized == 0.0
    assert any_priced is False


# ── _compute_broker_daily_pnl: source selection ─────────────────────────────────────

class _FakeAdapter:
    def __init__(self, open_legs=None):
        self._open_legs = open_legs or []

    def status(self):
        return {"open_legs": self._open_legs}


def test_compute_pnl_prefers_broker_fills_when_available(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 9, 14, 11, 0, 0))
    _write_broker_rows(qe.BROKER_ORDERS_CSV, [
        _row("2026-09-14 09:31:00", "ORB", "OPEN", "BUY", 5, broker_fill_px="500.00"),
        _row("2026-09-14 10:00:00", "ORB", "CLOSE", "SELL", 5, broker_fill_px="510.00"),
    ])
    state = {"_unrl_by_leg": {"NOISE": 7.5}}
    pnl, source = qe._compute_broker_daily_pnl(state, _FakeAdapter(open_legs=["NOISE"]), log=NOOP)
    assert source == "broker_fills"
    assert pnl == pytest.approx(50.0 + 7.5)   # realized + the one still-open leg's mark


def test_compute_pnl_falls_back_to_shadow_when_no_broker_activity_today(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 9, 14, 11, 0, 0))
    state = {"realized_pnl_today": -120.0, "_unrl_by_leg": {"ORB": -30.0}}
    pnl, source = qe._compute_broker_daily_pnl(state, _FakeAdapter(), log=NOOP)
    assert source == "shadow_fallback"
    assert pnl == pytest.approx(-150.0)


# ── _sync_broker_daily_pnl: day reset + delta wiring into update_daily_pnl ──────────

def test_sync_resets_once_per_day_and_feeds_absolute_total_as_a_delta(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 9, 14, 10, 0, 0))
    state = {"realized_pnl_today": -50.0, "_unrl_by_leg": {}}

    calls = {"reset": 0, "deltas": []}

    class _Adapter(_FakeAdapter):
        def reset_daily_pnl(self):
            calls["reset"] += 1

        def update_daily_pnl(self, delta):
            calls["deltas"].append(delta)

    adapter = _Adapter()
    nowdt = datetime(2026, 9, 14, 10, 0, 0)
    qe._sync_broker_daily_pnl(state, adapter, nowdt, log=NOOP)
    assert calls["reset"] == 1
    assert calls["deltas"] == [-50.0]
    assert state["_broker_pnl_source"] == "shadow_fallback"

    # Same day, P&L worsens -- must push only the INCREMENTAL delta, not double-count.
    state["realized_pnl_today"] = -80.0
    qe._sync_broker_daily_pnl(state, adapter, nowdt, log=NOOP)
    assert calls["reset"] == 1   # not reset again, same ET day
    assert calls["deltas"] == [-50.0, -30.0]

    # A new ET day resets before syncing.
    nowdt2 = datetime(2026, 9, 15, 9, 31, 0)
    monkeypatch.setattr(qe, "_now_et", lambda: nowdt2)
    state["realized_pnl_today"] = -10.0
    qe._sync_broker_daily_pnl(state, adapter, nowdt2, log=NOOP)
    assert calls["reset"] == 2
    assert calls["deltas"][-1] == -10.0   # fresh day, tracked total starts back at 0


def test_sync_never_raises_when_adapter_method_missing(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 9, 14, 10, 0, 0))
    state = {}

    class _BrokenAdapter:
        pass   # no reset_daily_pnl/update_daily_pnl/status at all
    qe._sync_broker_daily_pnl(state, _BrokenAdapter(), datetime(2026, 9, 14, 10, 0, 0), log=NOOP)
    # must not raise -- the try/except inside _sync_broker_daily_pnl/_compute_broker_daily_pnl
    # falls back all the way to the shadow figures (0.0 for an empty state).


# ── end-to-end: a losing day crosses the $400 limit and blocks OPENs ───────────────

def test_a_losing_day_crosses_the_limit_and_blocks_opens_but_not_exits(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["rails"]["daily_loss_limit_usd"] = 400
    cfg["rails"]["one_open_position_per_leg"] = False
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    mock_client = MagicMock()
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_CASH"}]}
    mock_client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    monkeypatch.setattr(adapter, "_build_client", lambda mode: mock_client)

    nowdt = datetime(2026, 9, 14, 14, 0, 0)
    monkeypatch.setattr(qe, "_now_et", lambda: nowdt)
    state = {"realized_pnl_today": -412.0, "_unrl_by_leg": {}}
    qe._sync_broker_daily_pnl(state, adapter, nowdt, log=NOOP)
    assert adapter._state["daily_pnl"] == pytest.approx(-412.0)

    blocked = adapter.place_stock_order(leg="ORB", signal_id="new-open", symbol="QQQ",
                                        side="BUY", qty=5)
    assert blocked["mode"] == "BLOCKED"
    assert "daily loss limit" in blocked["reason"]

    exit_rec = adapter.place_stock_order(leg="ORB", signal_id="flatten", symbol="QQQ",
                                         side="SELL", qty=5, intent="CLOSE")
    assert exit_rec["mode"] != "BLOCKED", "a flatten must still be allowed once the daily stop trips"


# ── defect 2: broker.last_order carries an ISO US/Eastern timestamp ─────────────────

def test_last_order_carries_an_iso_et_timestamp(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "OFF"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    before = real_time.time()
    adapter.place_stock_order(leg="ORB", signal_id="s1", symbol="QQQ", side="BUY", qty=5)
    after = real_time.time()

    status = qe._build_broker_status(log=NOOP)
    ts_et = status["last_order"]["ts_et"]
    assert ts_et is not None
    parsed = datetime.fromisoformat(ts_et)
    assert parsed.tzinfo is not None, "must carry the US/Eastern offset, not a naive timestamp"
    # Round-trip sanity: the parsed epoch falls within the call's own wall-clock window.
    assert before - 1 <= parsed.timestamp() <= after + 1
    # Existing fields untouched.
    for key in ("leg", "side", "qty", "intent", "mode", "ok", "sent", "reason"):
        assert key in status["last_order"]


def test_last_order_ts_et_is_none_when_no_order_yet(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    cfg = WO.load_config("__no_such_file__")
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    status = qe._build_broker_status(log=NOOP)
    assert status["last_order"]["ts_et"] is None
