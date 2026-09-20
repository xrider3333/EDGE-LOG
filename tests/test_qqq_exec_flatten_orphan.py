"""api/qqq_exec.py's orphan-broker repair (_maybe_flatten_orphan_broker, 2026-09-20).

WHY IT EXISTS: session.flat_by was set to "16:00", so the 5s tick fired the EOD flatten
at 16:00:02-16:00:05 ET -- after the regular close. Webull rejects a market order there
("only limit orders are supported for extended-hours trading"), so on 2026-09-17 and
2026-09-18 the shadow book recorded its exits while 20 real paper shares stayed open, and
the adapter's one-open-position-per-leg rail then BLOCKED the next day's entry for those
legs. This repair closes a broker lot the shadow book has no lot for, but only inside
regular hours -- the exact condition that was missing.

Same harness conventions as tests/test_qqq_exec_broker_mirror.py: a throwaway
OrderAdapter on tmp_path, the webull SDK replaced by a MagicMock, no network, no real
C:\\EdgeLog path.
"""
import csv
import datetime
import json
import os
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import webull_orders as WO


ET = qe._ET if hasattr(qe, "_ET") else None


def _broker_cfg(tmp_path, mode="PAPER"):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _mock_client():
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_CASH"}]
    }
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _paper_adapter(tmp_path, monkeypatch):
    cfg = _broker_cfg(tmp_path, mode="PAPER")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    client = _mock_client()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: client)
    return adapter, client


def _patch_qqq_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _setup(tmp_path, monkeypatch, *, believed, shadow_legs):
    """A cfg/state pair whose broker believes `believed` and whose shadow book holds
    `shadow_legs`. Returns (cfg, state, adapter, client, trigger_path, out_dir)."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    adapter._state["believed_positions"] = {
        leg: {"symbol": "QQQ", "qty": qty} for leg, qty in believed.items()}
    adapter._state["open_legs"] = {leg: True for leg, qty in believed.items() if qty}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (712.5, "test"))
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: None)
    trigger = out / "FLATTEN_BROKER"
    trigger.write_text("flatten\n", encoding="utf-8")
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
    cfg["flatten_broker_file"] = str(trigger)
    cfg["kill_file"] = str(out / "KILL")
    state = {"legs": {leg: {"nq_qty_remaining": 1} for leg in shadow_legs}, "events": []}
    return cfg, state, adapter, client, trigger, out


def _broker_rows(out):
    path = out / "broker_orders.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _at(h, m):
    """A weekday (Monday 2026-09-21) at ET h:m -- what tick() passes as nowdt."""
    return datetime.datetime(2026, 9, 21, h, m, 0)


# ── the repair itself ──────────────────────────────────────────────────────────────

def test_orphan_leg_is_closed_in_market_hours(tmp_path, monkeypatch):
    """The 2026-09-18 state exactly: broker holds ENGUQ 10 + ORB 10, shadow book flat."""
    cfg, state, adapter, client, trigger, out = _setup(
        tmp_path, monkeypatch, believed={"ENGUQ": 10, "ORB": 10, "NOISE": 0}, shadow_legs=[])

    qe._maybe_flatten_orphan_broker(state, cfg, _at(9, 35))

    rows = _broker_rows(out)
    assert [r["leg"] for r in rows] == ["ENGUQ", "ORB"], rows
    for r in rows:
        assert r["intent"] == "CLOSE"
        assert r["side"] == "SELL"          # closing a long
        assert r["shares"] == "10"
        assert r["mode"] == "PAPER"
        assert r["ok"] == "True", r["reason"]
    # a repair id of its own, never the original close's (Webull refuses a repeat)
    assert {r["client_order_id"] for r in rows} == {"qxFIXENGUQ20260921C", "qxFIXORB20260921C"}
    # the adapter's own belief went to zero, so a later reconcile agrees with a flat broker
    assert adapter._state["believed_positions"]["ENGUQ"]["qty"] == 0
    assert adapter._state["believed_positions"]["ORB"]["qty"] == 0


def test_trigger_is_consumed_so_it_cannot_fire_twice(tmp_path, monkeypatch):
    cfg, state, adapter, client, trigger, out = _setup(
        tmp_path, monkeypatch, believed={"ENGUQ": 10}, shadow_legs=[])

    qe._maybe_flatten_orphan_broker(state, cfg, _at(9, 35))
    assert not trigger.exists()
    assert [p.name for p in out.iterdir() if p.name.startswith("FLATTEN_BROKER.done-")]

    before = len(_broker_rows(out))
    qe._maybe_flatten_orphan_broker(state, cfg, _at(9, 40))
    assert len(_broker_rows(out)) == before    # nothing sent the second time


def test_a_leg_the_shadow_book_still_holds_is_left_alone(tmp_path, monkeypatch):
    """Only an ORPHAN is closed -- a live lot must not be flattened out from under the book."""
    cfg, state, adapter, client, trigger, out = _setup(
        tmp_path, monkeypatch, believed={"ENGUQ": 10, "ORB": 10}, shadow_legs=["ORB"])

    qe._maybe_flatten_orphan_broker(state, cfg, _at(9, 35))

    assert [r["leg"] for r in _broker_rows(out)] == ["ENGUQ"]
    assert adapter._state["believed_positions"]["ORB"]["qty"] == 10


# ── the guard that the whole bug was about ─────────────────────────────────────────

@pytest.mark.parametrize("when", [
    _at(9, 20),    # pre-market
    _at(16, 2),    # the exact window that rejected the real 09-17/09-18 sells
    datetime.datetime(2026, 9, 20, 11, 0, 0),   # a Sunday
])
def test_nothing_is_sent_outside_regular_hours_and_the_trigger_survives(
        tmp_path, monkeypatch, when):
    cfg, state, adapter, client, trigger, out = _setup(
        tmp_path, monkeypatch, believed={"ENGUQ": 10}, shadow_legs=[])

    qe._maybe_flatten_orphan_broker(state, cfg, when)

    assert _broker_rows(out) == []
    assert trigger.exists(), "the trigger must survive until the market is actually open"
    assert adapter._state["believed_positions"]["ENGUQ"]["qty"] == 10


def test_no_trigger_file_is_a_no_op(tmp_path, monkeypatch):
    cfg, state, adapter, client, trigger, out = _setup(
        tmp_path, monkeypatch, believed={"ENGUQ": 10}, shadow_legs=[])
    trigger.unlink()

    qe._maybe_flatten_orphan_broker(state, cfg, _at(9, 35))

    assert _broker_rows(out) == []
    assert adapter._state["believed_positions"]["ENGUQ"]["qty"] == 10


def test_trigger_with_nothing_orphaned_is_consumed_without_sending(tmp_path, monkeypatch):
    cfg, state, adapter, client, trigger, out = _setup(
        tmp_path, monkeypatch, believed={"ENGUQ": 0}, shadow_legs=[])

    qe._maybe_flatten_orphan_broker(state, cfg, _at(9, 35))

    assert _broker_rows(out) == []
    assert not trigger.exists()


def test_an_adapter_failure_never_raises_into_the_tick(tmp_path, monkeypatch):
    cfg, state, adapter, client, trigger, out = _setup(
        tmp_path, monkeypatch, believed={"ENGUQ": 10}, shadow_legs=[])

    def boom(log=print):
        raise RuntimeError("broker down")

    monkeypatch.setattr(qe, "_get_broker_adapter", boom)
    qe._maybe_flatten_orphan_broker(state, cfg, _at(9, 35))     # must not raise
    assert not trigger.exists(), "a failed repair still consumes its trigger"
