"""api/qqq_exec.py's broker mirror -- every shadow OPEN/CLOSE also hands its intent
to api.webull_orders (via _mirror_to_broker), wired 2026-09-13 so flipping Webull
paper orders on is a one-line config change (mode: PAPER in
webull_orders/config.json) with no other code change needed.

Every test here monkeypatches qe._get_broker_adapter to point at a throwaway
OrderAdapter (its own tmp_path state file) instead of the real module-level
singleton or any real C:\\EdgeLog path. The webull SDK is never hit over the network
-- PAPER-mode tests replace OrderAdapter._build_client with a MagicMock, exactly like
tests/test_webull_orders.py does for the adapter itself.
"""
import csv
import json
import os
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import webull_orders as WO


# ── fixtures / helpers ────────────────────────────────────────────────────────────

def _broker_cfg(tmp_path, mode="OFF"):
    cfg = WO.load_config("__no_such_file__")   # defaults only
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _mock_client(fill_price=None):
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1"}]
    }
    resp = {"status": "SUBMITTED"}
    if fill_price is not None:
        resp["avg_fill_price"] = fill_price
    client.order_v3.place_order.return_value.json.return_value = resp
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _paper_adapter(tmp_path, monkeypatch, fill_price=None):
    cfg = _broker_cfg(tmp_path, mode="PAPER")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    mock_client = _mock_client(fill_price=fill_price)
    monkeypatch.setattr(adapter, "_build_client", lambda mode: mock_client)
    return adapter, mock_client


def _patch_broker_adapter(monkeypatch, adapter):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)


def _patch_qqq_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _base_state():
    return {"legs": {}, "_px_source": "test"}


def _base_cfg(**overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}
    cfg.update(overrides)
    return cfg


def _read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


NOOP = lambda *a, **k: None  # noqa: E731


# ── OFF mode: shadow output unchanged, would-be order recorded separately ──────────

def test_off_mode_shadow_csvs_unchanged_broker_record_added(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)

    state = _base_state()
    cfg = _base_cfg()
    opened = qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    assert opened is True
    qe._reduce_lot(state, cfg, "ORB", 5, 705.0, 505.0, 0.0, "signal exit", log=NOOP)

    with open(qe.ORDERS_CSV, encoding="utf-8", newline="") as f:
        header = f.readline().strip()
    assert header == ",".join(qe.ORDER_COLS), "OFF mode must never change orders.csv's columns"

    with open(qe.TRADES_CSV, encoding="utf-8", newline="") as f:
        header = f.readline().strip()
    assert header == ",".join(qe.TRADE_COLS), "OFF mode must never change trades.csv's columns"

    assert os.path.exists(qe.BROKER_ORDERS_CSV), "the would-be order must be recorded somewhere"
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert [r["intent"] for r in rows] == ["OPEN", "CLOSE"]
    assert all(r["mode"] == "OFF" for r in rows)
    assert all(r["sent"] == "False" for r in rows)
    assert all(r["ok"] == "True" for r in rows)


def test_off_mode_broker_side_mapping(tmp_path, monkeypatch):
    """OPEN long -> BUY, CLOSE long -> SELL, OPEN short -> SHORT, CLOSE short -> BUY
    (the installed Webull SDK's OrderSide enum has no COVER member -- see
    api/qqq_exec.py's _broker_side)."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)

    state = _base_state()
    cfg = _base_cfg()
    qe._open_lot(state, cfg, "ORB", "short", 5, 700.0, 500.0, 0.0, log=NOOP)
    qe._reduce_lot(state, cfg, "ORB", 5, 695.0, 495.0, 0.0, "signal exit", log=NOOP)
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[0]["side"] == "SHORT"
    assert rows[1]["side"] == "BUY"


# ── PAPER mode: real send, once each, survives a simulated restart ─────────────────

def test_broker_mirror_idempotent_across_simulated_restart(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch)
    _patch_broker_adapter(monkeypatch, adapter)

    state = _base_state()
    ts = "2026-09-13 09:31:05"
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts=ts, log=NOOP)
    mock_client.order_v3.place_order.assert_called_once()

    # SIMULATED RESTART: a fresh OrderAdapter built from the SAME on-disk state file --
    # exactly what api/qqq_exec.py would reconstruct after a process restart, since the
    # lot's entry_ts (persisted in ITS own state.json) is unchanged.
    adapter2 = WO.OrderAdapter(config=adapter.cfg, log=NOOP)
    monkeypatch.setattr(adapter2, "_build_client", lambda mode: mock_client)
    _patch_broker_adapter(monkeypatch, adapter2)

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts=ts, log=NOOP)
    assert mock_client.order_v3.place_order.call_count == 1, \
        "a restart replay of the same OPEN must not re-send"

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=506.0,
                         intent="CLOSE", ts=ts, seq=1, log=NOOP)
    assert mock_client.order_v3.place_order.call_count == 2, "CLOSE is a different signal_id"

    # And replaying the CLOSE again must also not re-send.
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=506.0,
                         intent="CLOSE", ts=ts, seq=1, log=NOOP)
    assert mock_client.order_v3.place_order.call_count == 2


def test_open_lot_and_reduce_lot_each_send_once_via_paper(tmp_path, monkeypatch):
    """End-to-end through the real _open_lot/_reduce_lot wiring (not _mirror_to_broker
    directly) -- confirms the lot lifecycle actually calls the adapter once per side."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch)
    _patch_broker_adapter(monkeypatch, adapter)

    state = _base_state()
    cfg = _base_cfg()
    qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    assert mock_client.order_v3.place_order.call_count == 1
    qe._reduce_lot(state, cfg, "ORB", 5, 705.0, 505.0, 0.0, "signal exit", log=NOOP)
    assert mock_client.order_v3.place_order.call_count == 2

    args, _ = mock_client.order_v3.place_order.call_args_list[0]
    _, new_orders = args
    assert new_orders[0]["symbol"] == "QQQ"
    assert new_orders[0]["side"] == "BUY"
    assert new_orders[0]["quantity"] == "5"


# ── a broker error never crashes/unwinds the shadow ────────────────────────────────

def test_broker_adapter_construction_exception_does_not_crash_shadow(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)

    def boom(log=print):
        raise RuntimeError("adapter unavailable")

    monkeypatch.setattr(qe, "_get_broker_adapter", boom)

    state = _base_state()
    cfg = _base_cfg()
    opened = qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    assert opened is True, "the shadow lot must still open even if the broker adapter blows up"
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["mode"] == "ERROR"
    assert "RuntimeError" in rows[-1]["reason"]


def test_broker_place_order_exception_does_not_crash_shadow(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch)
    mock_client.order_v3.place_order.side_effect = RuntimeError("network exploded")
    _patch_broker_adapter(monkeypatch, adapter)

    state = _base_state()
    cfg = _base_cfg()
    opened = qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    assert opened is True, "a broker send failure must not stop the shadow from opening"
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["ok"] == "False"


# ── slippage recorded when the broker's fill differs from the shadow's price ───────

def test_slippage_recorded_when_broker_fill_differs(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch, fill_price=501.50)
    _patch_broker_adapter(monkeypatch, adapter)

    state = _base_state()
    cfg = _base_cfg()
    qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)

    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    row = rows[-1]
    assert row["shadow_px"] == "500.0"
    assert row["broker_fill_px"] == "501.5"
    assert float(row["slippage"]) == pytest.approx(1.5, abs=1e-6)


def test_no_slippage_field_when_broker_reports_no_fill_price(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch, fill_price=None)
    _patch_broker_adapter(monkeypatch, adapter)

    state = _base_state()
    cfg = _base_cfg()
    qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["broker_fill_px"] == ""
    assert rows[-1]["slippage"] == ""


# ── flat-by / EOD / KILL (via _close_all) mirrors the close, never leaves a broker
# position open past flat-by ─────────────────────────────────────────────────────────

def test_close_all_mirrors_close_to_broker_in_engine_mode(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (510.0, "engine_cache"))

    state = _base_state()
    cfg = _base_cfg(signal_source="engine")
    qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    assert "ORB" in state["legs"]

    qe._close_all(state, cfg, "EOD", quote_fn=None, ratio_fn=None, log=NOOP)
    assert "ORB" not in state["legs"], "flat-by must close the shadow lot"

    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["intent"] == "CLOSE", "flat-by must also close the broker mirror position"


# ── startup reconcile: mismatch halts new broker entries, shadow still opens ───────

def test_reconcile_at_boot_mismatch_halts_new_broker_entries(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch)
    _patch_broker_adapter(monkeypatch, adapter)
    mock_client.account_v2.get_account_position.return_value.json.return_value = {
        "data": [{"symbol": "QQQ", "quantity": 999, "side": "LONG"}]
    }

    qe._reconcile_broker_at_boot(log=NOOP)
    assert adapter._halted is True

    state = _base_state()
    cfg = _base_cfg()
    opened = qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    assert opened is True, "the shadow stays the source of truth even while the broker mirror is halted"
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["mode"] == "BLOCKED"
    assert "halted" in rows[-1]["reason"]


def test_reconcile_at_boot_matching_positions_does_not_halt(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _paper_adapter(tmp_path, monkeypatch)
    _patch_broker_adapter(monkeypatch, adapter)
    # No believed positions yet (fresh state) and the broker also reports flat -> match.
    mock_client.account_v2.get_account_position.return_value.json.return_value = {"data": []}

    qe._reconcile_broker_at_boot(log=NOOP)
    assert adapter._halted is False


def test_reconcile_at_boot_off_mode_is_a_noop(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)
    qe._reconcile_broker_at_boot(log=NOOP)   # must not raise
    assert adapter._halted is False


# ── doc status ("broker" key) ────────────────────────────────────────────────────────

def test_build_broker_status_shape(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)

    # No `state` arg -- confirms the 2026-09-14 lease fields stay optional/backward
    # compatible for a caller that predates them.
    status = qe._build_broker_status(log=NOOP)
    for key in ("requested_mode", "effective_mode", "mode_reason", "environment",
               "paper_credentials_present", "live_credentials_present", "live_armed",
               "kill_file_present", "halted", "halt_reason", "last_error", "last_order",
               "daily_pnl", "open_legs",
               # CROSS-HOST LEASE (2026-09-14): loud, phone-visible record of whether
               # broker sends are currently gated by an unverifiable/lost lease.
               "lease_ok_to_send", "lease_block_reason"):
        assert key in status
    assert status["effective_mode"] == "OFF"
    assert status["lease_ok_to_send"] is True, "no state given -> defaults to ok, never phantom-blocked"
    assert status["lease_block_reason"] is None


def test_build_broker_status_surfaces_lease_block(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="PAPER"), log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)

    state = {"_broker_lease_ok": False, "_broker_lease_reason": "lease unverifiable: timeout"}
    status = qe._build_broker_status(state, log=NOOP)
    assert status["lease_ok_to_send"] is False
    assert status["lease_block_reason"] == "lease unverifiable: timeout"


def test_build_broker_status_never_raises_on_adapter_error(tmp_path, monkeypatch):
    def boom(log=print):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(qe, "_get_broker_adapter", boom)
    status = qe._build_broker_status(log=NOOP)
    assert "error" in status
