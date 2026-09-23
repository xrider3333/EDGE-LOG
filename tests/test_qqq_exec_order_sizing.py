"""api/qqq_exec.py -- the ORDER side of per-trade SIZE (2026-09-23), the second half of
the run #382 (NOISE_1_8_CT304, size 1.0 or 2.0) / later KEEL (0.5x-2.0x, hard cap 3x)
prerequisite. Commit 10744e0 made size a first-class field on the SIGNAL side
(api/cloud_signal.py's run_leg_trades records it on every trade; signals.csv carries a
trailing "size" column). Nothing on the order side read it before this change --
api/qqq_exec.py sent a fixed share count per leg from cfg["shares"][leg] regardless of
what a signal asked for.

Coverage:
  1. _resolve_entry_size / _sized_shares (pure): the size -> wanted-quantity math --
     every default/edge case (missing, blank, unparseable, non-positive, non-finite),
     fractional rounding, floored at 1 (never 0), a disabled (0-share) leg stays 0.
  2. _open_lot, through _route_engine_events with a real engine ENTRY event: size 1.0
     (explicit, blank, or the key entirely absent -- an old ledger row) is BYTE FOR
     BYTE today's fixed-shares behaviour, including the REFUSE-not-clamp rail when the
     plain config alone exceeds max_shares_per_leg. A genuine size that pushes the
     wanted quantity over the rail is CLAMPED instead (never refused), logged, and
     both the wanted and the sent quantity land on the lot and on
     orders.csv/trades.csv.
  3. CLOSE MUST MATCH OPEN: _reduce_lot always closes the lot's own shares_total,
     never a value recomputed from (possibly since-changed) config. Then, at the
     broker-mirror layer (_mirror_to_broker / api.webull_orders' NOTHING TO CLOSE
     guard, 2f99aad / the re-send queue), a sized quantity that is neither the old
     default 5 nor 10 flows correctly through an OPEN the broker's own rail blocks, a
     duplicate-reject resend, and a CLOSE -- proving none of that machinery assumed a
     fixed share count.
  4. P&L scales with the real (sent, possibly clamped) share count, never the
     wanted-before-clamp one.
"""
import csv
import json
import os
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from api import qqq_exec as qe
from api import trade_id
from api import webull_orders as WO

NY = ZoneInfo("America/New_York")
NOOP = lambda *a, **k: None  # noqa: E731
NOW = datetime(2026, 9, 23, 10, 30, tzinfo=NY)


# ── harness (same conventions as tests/test_qqq_exec_engine_source.py and
#    tests/test_qqq_exec_broker_resend.py -- copied locally, not imported: no test in
#    this repo imports from another test module) ────────────────────────────────────
def _cfg(tmp_path, **overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["signal_source"] = "engine"
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}
    cfg.update(overrides)
    return cfg


def _isolate_adapter(tmp_path, monkeypatch, name="qqq_exec_out"):
    """Every file a lot open/close writes -> tmp, no phone push, and a broker order
    adapter in OFF mode whose own state file is in tmp too (the real one defaults to
    C:\\EdgeLog). Used by every test that is really about the SHADOW book's own
    quantity math, not the broker wiring (see _paper_adapter below for that)."""
    out = tmp_path / name
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                        ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    monkeypatch.setattr(qe, "_notify", NOOP)
    wo_cfg = WO.load_config(str(out / "no_such_webull_orders_config.json"))
    wo_cfg.update(mode="OFF", state_path=str(out / "wo_state.json"), kill_file=str(out / "WO_KILL"),
                  arm_live_file=str(out / "WO_ARM_LIVE"), paper_keys_path=str(out / "no_paper.json"),
                  live_keys_path=str(out / "no_live.json"))
    wo_cfg["rails"] = dict(wo_cfg["rails"], session_start="00:00", session_end="23:59")
    adapter = WO.OrderAdapter(config=wo_cfg, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    return out


def _ev(event, ref_time, ref_price, tid="", leg="NOISE_304", side="long", size=""):
    """One event exactly as _consume_engine_signals hands it to _route_engine_events --
    size defaults to "" (a blank signals.csv cell), the realistic shape of a leg that
    does not size."""
    return {"leg": leg, "event": event, "side": side, "ref_time": ref_time,
           "ref_price": float(ref_price), "bar_source": "webull", "trade_id": tid,
           "size": size}


def _route(state, cfg, *events, now=NOW):
    qe._route_engine_events(state, cfg, list(events), False, log=NOOP, now=now)


def _csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _tid(entry_iso, leg="NOISE_304", side="long"):
    return trade_id.make(leg, entry_iso, side)


# ── A. _resolve_entry_size / _sized_shares (pure math) ──────────────────────────────

@pytest.mark.parametrize("raw", [
    None, "", "   ", "abc", "0", "-1", "-3.5", "nan", "inf", "-inf",
    0, -1, float("nan"), float("inf"), float("-inf"),
])
def test_resolve_entry_size_defaults_to_unsized(raw):
    assert qe._resolve_entry_size(raw) == 1.0


@pytest.mark.parametrize("raw,expected", [
    ("2.0", 2.0), ("0.5", 0.5), (2, 2.0), (1.5, 1.5), ("  1.3  ", 1.3), (1.0, 1.0),
])
def test_resolve_entry_size_parses_valid_values(raw, expected):
    assert qe._resolve_entry_size(raw) == pytest.approx(expected)


@pytest.mark.parametrize("base,size,expected", [
    (10, 1.0, 10),   # unsized -- exactly base
    (10, 2.0, 20),   # task's own example
    (10, 0.5, 5),    # task's own example
    (10, 1.24, 12),  # rounds down
    (10, 1.26, 13),  # rounds up
    (9, 1.5, 14),    # a distinctive, non-5/non-10 result
    (3, 0.1, 1),     # rounds to 0 -- floored at 1, never 0
    (10, 0.01, 1),   # tiny but positive size -- still at least 1 share
])
def test_sized_shares_rounds_and_floors_at_1(base, size, expected):
    assert qe._sized_shares(base, size) == expected


@pytest.mark.parametrize("size", [0.1, 1.0, 2.0, 100.0])
def test_sized_shares_disabled_leg_stays_zero(size):
    """A leg configured at 0 shares (owner-disabled) must never be sized UP to 1 --
    that would silently re-enable a leg the owner turned off."""
    assert qe._sized_shares(0, size) == 0


# ── B. OPEN quantity: size 1.0 is byte-for-byte; a genuine size clamps, never refuses ─

def test_size_1_0_blank_and_absent_are_byte_for_byte_identical(tmp_path, monkeypatch):
    """All three live legs run size 1.0 today. Whether a signal spells that out
    (size=1.0), leaves it blank (size="", the normal signals.csv cell for a leg that
    does not size), or the event dict omits the key entirely (an old
    _consume_engine_signals shape), the resulting lot and orders.csv row are
    identical."""
    cfg = _cfg(tmp_path)  # shares 5/5/5, max_shares_per_leg 10 (DEFAULT_CONFIG)
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    results = {}
    for label, size_kwargs in (("blank", {"size": ""}), ("explicit_1_0", {"size": 1.0}),
                               ("absent", {"size": ""})):
        _isolate_adapter(tmp_path, monkeypatch, name=f"out_{label}")
        state = {"legs": {}}
        ev = _ev("ENTRY", entry_iso, 700.0, tid, **size_kwargs)
        if label == "absent":
            del ev["size"]
        _route(state, cfg, ev)
        lot = state["legs"]["NOISE"]
        row = _csv_rows(qe.ORDERS_CSV)[-1]
        results[label] = (lot["shares_total"], lot["shares_wanted"], lot["size"],
                          row["shares"], row["shares_wanted"], row["size"])
    assert results["blank"] == results["explicit_1_0"] == results["absent"]
    assert results["blank"] == (5, 5, 1.0, "5", "5", "1.0")


def test_unsized_over_cap_still_refuses_like_today(tmp_path, monkeypatch):
    """size 1.0 (unsized) is BYTE FOR BYTE today's rail: a plain misconfiguration (the
    leg's own configured share count already over the cap) REFUSES the whole trade --
    it does not clamp. Only a genuine signal size clamps (see the next test)."""
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 20})  # 20 > max 10, no sizing
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=""))

    assert "NOISE" not in state["legs"], "an unsized over-cap config must refuse, not clamp"
    row = _csv_rows(qe.ORDERS_CSV)[-1]
    assert row["reason"] == "REFUSED shares 20 > max_shares_per_leg 10"
    assert not any(e["kind"] == "size_clamped" for e in state.get("events", []))


def test_size_2_0_wanted_20_clamped_to_10(tmp_path, monkeypatch):
    """The task's own example: base 10, size 2.0 -> wants 20, the rail (10 today)
    clamps it and the clamp is logged and recorded, not silently applied."""
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 10})  # max_shares_per_leg stays 10
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=2.0))

    lot = state["legs"]["NOISE"]
    assert (lot["shares_total"], lot["shares_wanted"], lot["size"]) == (10, 20, 2.0)

    row = _csv_rows(qe.ORDERS_CSV)[-1]
    assert (row["action"], row["shares"], row["shares_wanted"], row["size"]) == (
        "ENTER", "10", "20", "2.0")

    kinds = [e["kind"] for e in state.get("events", [])]
    assert "size_clamped" in kinds
    clamp_evt = next(e for e in state["events"] if e["kind"] == "size_clamped")
    assert "20" in clamp_evt["text"] and "10" in clamp_evt["text"]


def test_size_0_5_wanted_5_no_clamp(tmp_path, monkeypatch):
    """The task's other example: base 10, size 0.5 -> wants 5, well under the rail --
    no clamp fires."""
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 10})
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=0.5))

    lot = state["legs"]["NOISE"]
    assert (lot["shares_total"], lot["shares_wanted"], lot["size"]) == (5, 5, 0.5)
    assert not any(e["kind"] == "size_clamped" for e in state.get("events", []))


@pytest.mark.parametrize("size,expected", [(1.24, 12), (1.26, 13)])
def test_fractional_size_rounds_to_nearest_share(tmp_path, monkeypatch, size, expected):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 10}, max_shares_per_leg=25)
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=size))
    lot = state["legs"]["NOISE"]
    assert (lot["shares_total"], lot["shares_wanted"]) == (expected, expected)


def test_tiny_size_floors_at_1_not_0(tmp_path, monkeypatch):
    """A leg's configured count times a small size can round to 0 -- that must open a
    1-share trade, never silently vanish it."""
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 3})
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=0.1))
    lot = state["legs"]["NOISE"]
    assert (lot["shares_total"], lot["shares_wanted"]) == (1, 1)


def test_unparseable_size_defaults_to_unsized(tmp_path, monkeypatch):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path)  # shares 5/5/5
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size="not-a-number"))
    lot = state["legs"]["NOISE"]
    assert (lot["shares_total"], lot["size"]) == (5, 1.0)


def test_disabled_leg_ignores_size_entirely(tmp_path, monkeypatch):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 0})
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=3.0))
    assert "NOISE" not in state["legs"], "a leg the owner disabled must stay disabled regardless of size"
    assert _csv_rows(qe.ORDERS_CSV) == []


def test_consume_engine_signals_size_is_none_when_column_absent(tmp_path, monkeypatch):
    """A signals.csv written before commit 10744e0 added the "size" column -- read
    through the REAL _consume_engine_signals, not a hand-built event dict."""
    from api import cloud_signal as cs
    paths = cs._paths(home=str(tmp_path / "cs_home"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    os.makedirs(paths["state_dir"], exist_ok=True)
    old_cols = ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares",
               "reason", "bar_source", "trade_id"]  # no "size" -- pre-10744e0 shape
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=old_cols).writeheader()

    cfg = _cfg(tmp_path)
    state = {}
    assert qe._consume_engine_signals(state, cfg, NOW, log=NOOP) == [], "cold-start seed"

    # within ENGINE_CONSUME_STALE_SEC (30 min) of NOW (10:30 ET) -- a row emitted
    # further back than that is deliberately skipped as stale, see that constant.
    entry_iso = "2026-09-23T10:25:00-04:00"
    with open(paths["signals_path"], "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=old_cols).writerow(
            {"emitted_at": entry_iso, "leg": "NOISE_304", "event": "ENTRY", "side": "long",
             "ref_time": entry_iso, "ref_price": 700.0, "shares": 5, "reason": "",
             "bar_source": "webull", "trade_id": _tid(entry_iso)})
    events = qe._consume_engine_signals(state, cfg, NOW, log=NOOP)
    assert len(events) == 1
    assert events[0]["size"] is None


# ── D. P&L scales with the real (sent) share count ──────────────────────────────────

def test_trade_row_carries_size_and_wanted_pnl_scales_with_sent_not_wanted(tmp_path, monkeypatch):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 10})  # max stays 10
    entry_iso = "2026-09-23T09:40:00-04:00"
    exit_iso = "2026-09-23T10:00:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.00, tid, size=2.0))  # wanted 20, clamped to 10
    _route(state, cfg, _ev("EXIT", exit_iso, 705.00, tid))

    assert "NOISE" not in state["legs"]
    trade = _csv_rows(qe.TRADES_CSV)[-1]
    assert trade["shares"] == "10"
    assert trade["shares_wanted"] == "20"
    assert trade["size"] == "2.0"
    # entry slippage 0.01 (DEFAULT_CONFIG), long: buy fill 700.01, sell fill 704.99
    expected_pnl_sent = round((704.99 - 700.01) * 10, 2)
    expected_pnl_wanted = round((704.99 - 700.01) * 20, 2)
    assert float(trade["pnl"]) == pytest.approx(expected_pnl_sent)
    assert float(trade["pnl"]) != pytest.approx(expected_pnl_wanted), (
        "pnl must scale with the SENT shares (10), never the wanted-before-clamp one (20)")


@pytest.mark.parametrize("size,expected_shares", [(1.0, 10), (0.5, 5), (2.0, 20)])
def test_pnl_scales_linearly_with_the_sent_share_count(tmp_path, monkeypatch, size, expected_shares):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 10}, max_shares_per_leg=25)
    entry_iso = "2026-09-23T09:40:00-04:00"
    exit_iso = "2026-09-23T10:00:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=size))
    assert state["legs"]["NOISE"]["shares_total"] == expected_shares
    _route(state, cfg, _ev("EXIT", exit_iso, 701.0, tid))
    trade = _csv_rows(qe.TRADES_CSV)[-1]
    expected_pnl = round(0.98 * expected_shares, 2)  # (701.00-0.01) - (700.00+0.01) = 0.98/sh
    assert float(trade["pnl"]) == pytest.approx(expected_pnl)


# ── E. CLOSE MUST MATCH OPEN ─────────────────────────────────────────────────────────

def test_close_never_recomputes_from_config_even_if_config_changed(tmp_path, monkeypatch):
    """The sharpest proof that a CLOSE reads the lot's own shares_total, never cfg:
    both knobs change between the OPEN and the EXIT, and the CLOSE must still be the
    ORIGINAL sized/clamped quantity."""
    _isolate_adapter(tmp_path, monkeypatch)
    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 10})  # -> wanted 20, clamped to 10
    entry_iso = "2026-09-23T09:40:00-04:00"
    exit_iso = "2026-09-23T10:00:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=2.0))
    assert state["legs"]["NOISE"]["shares_total"] == 10

    # the owner (or a config reload) changes BOTH knobs before the exit arrives
    cfg["shares"]["NOISE"] = 3
    cfg["max_shares_per_leg"] = 1

    _route(state, cfg, _ev("EXIT", exit_iso, 705.0, tid))

    assert "NOISE" not in state["legs"]
    trade = _csv_rows(qe.TRADES_CSV)[-1]
    assert trade["shares"] == "10", (
        "must close what actually opened, not a value re-derived from the now-changed config")
    exit_row = [r for r in _csv_rows(qe.ORDERS_CSV) if r["action"] == "EXIT"][-1]
    assert exit_row["shares"] == "10"


# ── E (broker layer): a sized quantity through the REAL webull_orders.OrderAdapter,
#    proving 2f99aad's NOTHING TO CLOSE guard and the re-send queue never assumed a
#    fixed share count ───────────────────────────────────────────────────────────────
def _patch_qqq_paths(tmp_path, monkeypatch, name="qqq_out"):
    out = tmp_path / name
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _broker_cfg(tmp_path, mode="PAPER", max_shares_per_leg=None):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    if max_shares_per_leg is not None:
        cfg["rails"]["max_shares_per_leg"] = max_shares_per_leg
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _mock_client():
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]
    }
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _paper_adapter(tmp_path, monkeypatch, max_shares_per_leg=None):
    cfg = _broker_cfg(tmp_path, mode="PAPER", max_shares_per_leg=max_shares_per_leg)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    client = _mock_client()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: client)
    return adapter, client


def _order_dicts(client):
    return [c.args[1][0] for c in client.order_v3.place_order.call_args_list]


def test_broker_open_blocked_by_its_own_rail_leaves_nothing_to_close_for_a_sized_lot(
        tmp_path, monkeypatch):
    """The 2f99aad NOTHING TO CLOSE guard, proven with a quantity that is neither the
    old default 5 nor 10: the shadow books a 14-share sized lot (9 configured x 1.5),
    but the BROKER's own rail (a separate, lower cap here) blocks the mirrored OPEN.
    The shadow book still closes all 14 later -- CLOSE MUST MATCH OPEN -- and the
    broker mirror must recognise it never actually holds anything, sending no phantom
    SELL for shares Webull was never given."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch, max_shares_per_leg=5)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_notify", NOOP)

    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 9}, max_shares_per_leg=25)
    entry_iso = "2026-09-23T09:40:00-04:00"
    exit_iso = "2026-09-23T10:00:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}

    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=1.5))
    assert state["legs"]["NOISE"]["shares_total"] == 14, "shadow book sizes the lot the normal way"
    assert client.order_v3.place_order.call_count == 0, (
        "the broker's OWN rail must block the OPEN before any SDK call")
    open_row = [r for r in _csv_rows(qe.BROKER_ORDERS_CSV) if r["intent"] == "OPEN"][-1]
    assert open_row["mode"] == "BLOCKED"
    assert "max_shares_per_leg" in open_row["reason"]
    assert adapter._state.get("broker_sent_positions", {}) == {}

    _route(state, cfg, _ev("EXIT", exit_iso, 705.0, tid))
    assert "NOISE" not in state["legs"]
    trade = _csv_rows(qe.TRADES_CSV)[-1]
    assert trade["shares"] == "14", "the shadow book must still close exactly what it opened"

    assert client.order_v3.place_order.call_count == 0, "nothing was ever really held at the broker"
    close_row = [r for r in _csv_rows(qe.BROKER_ORDERS_CSV) if r["intent"] == "CLOSE"][-1]
    assert close_row["mode"] == "BLOCKED"
    assert close_row["reason"]


def test_resend_after_duplicate_reject_uses_the_lots_own_sized_quantity(tmp_path, monkeypatch):
    """A sized OPEN's broker send collides as a same-instant duplicate (2f99aad) and is
    queued; the resend AND the later CLOSE must both carry the exact sized quantity
    the lot actually opened with (14 = 9 configured x 1.5), never the old default 5 or
    10, and never a re-derived one."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch, max_shares_per_leg=25)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print: sent.append(msg))
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])

    cfg = _cfg(tmp_path, shares={"ORB": 5, "ENGUQ": 5, "NOISE": 9}, max_shares_per_leg=25)
    entry_iso = "2026-09-23T09:40:00-04:00"
    tid = _tid(entry_iso)
    state = {"legs": {}, "events": []}

    client.order_v3.place_order.side_effect = [RuntimeError(
        "HTTP Status: 417, Code: OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK, "
        "Msg: Duplicate Order")]
    _route(state, cfg, _ev("ENTRY", entry_iso, 700.0, tid, size=1.5))

    assert state["legs"]["NOISE"]["shares_total"] == 14
    assert client.order_v3.place_order.call_count == 1
    assert state["_broker_resend"]["NOISE:OPEN"]["shares"] == 14

    client.order_v3.place_order.side_effect = None  # the collision has cleared
    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, NOW, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 2
    assert _order_dicts(client)[1]["quantity"] == "14"
    assert state.get("_broker_resend") == {}
    assert any("re-sent and accepted" in msg for msg in sent)

    # the book now exits -- CLOSE must send the SAME 14, matching the OPEN exactly
    exit_iso = "2026-09-23T10:00:00-04:00"
    _route(state, cfg, _ev("EXIT", exit_iso, 705.0, tid))

    assert client.order_v3.place_order.call_count == 3
    assert _order_dicts(client)[2]["quantity"] == "14"
    assert adapter._state["broker_sent_positions"]["NOISE"]["qty"] == 0
