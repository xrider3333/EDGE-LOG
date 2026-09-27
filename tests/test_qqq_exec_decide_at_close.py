"""api/qqq_exec.py with api/cloud_signal.py's decide_at_close probe (WEBULL_PAPER_TODO.md
item 16, 2026-09-26). A probe ENTRY/EXIT is written at the close of bar D with ref_time =
the start of bar D+1 -- a bar that has only just begun -- and ref_price = D's close.

What the book must do with that: take it exactly like any other engine signal (nothing
checks ref_time against the clock beyond "today's session"; the shadow fill is ref_price
plus slippage), and report its after-close latency from ref_time itself, which IS the
close that justified it -- not ref_time + one bar, which would read ~-270 s. No network,
no live files: the same isolation harness as tests/test_qqq_exec_order_sizing.py.
"""
import csv
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from api import cloud_signal as cs
from api import qqq_exec as qe
from api import trade_id
from api import webull_orders as WO

NY = ZoneInfo("America/New_York")
NOOP = lambda *a, **k: None  # noqa: E731
BAR = "2026-09-23T10:05:00-04:00"                  # D+1: starts at the instant D closed
NOW = datetime(2026, 9, 23, 10, 5, 12, tzinfo=NY)  # 12 s after D's close
TAG = cs.DECIDE_AT_CLOSE_TAG + ": decided at the close of the 10:00 bar, priced at that close"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec_out"
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                        ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    monkeypatch.setattr(qe, "_notify", NOOP)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=str(tmp_path / "cs_home")))
    wo_cfg = WO.load_config(str(out / "no_such_webull_orders_config.json"))
    wo_cfg.update(mode="OFF", state_path=str(out / "wo_state.json"), kill_file=str(out / "WO_KILL"),
                  arm_live_file=str(out / "WO_ARM_LIVE"), paper_keys_path=str(out / "no_paper.json"),
                  live_keys_path=str(out / "no_live.json"))
    wo_cfg["rails"] = dict(wo_cfg["rails"], session_start="00:00", session_end="23:59")
    adapter = WO.OrderAdapter(config=wo_cfg, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_now_et", lambda: NOW)


def _cfg():
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["signal_source"] = "engine"
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}
    return cfg


def _ev(event, ref_time, ref_price, reason, tid):
    return {"leg": "NOISE_382", "event": event, "side": "long", "ref_time": ref_time,
            "ref_price": float(ref_price), "bar_source": "webull", "trade_id": tid,
            "size": "", "keel_size": "", "reason": reason}


def _orders():
    with open(qe.ORDERS_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_probe_entry_on_a_bar_only_just_starting_is_taken_at_its_ref_price(monkeypatch):
    tid = trade_id.make("NOISE_382", BAR, "long")
    state = {"legs": {}}
    qe._route_engine_events(state, _cfg(), [_ev("ENTRY", BAR, 701.25, TAG, tid)], False,
                            log=NOOP, now=NOW)
    lot = state["legs"]["NOISE"]
    assert lot["trade_id"] == tid and lot["entry_ref_time"] == BAR
    assert lot["entry_px"] == pytest.approx(701.25 + _cfg().get("slippage_per_share", 0.0))
    row = _orders()[-1]
    assert row["action"] == "ENTER" and row["reason"] == "signal entry"
    assert float(row["latency_s"]) == pytest.approx(12.0)
    assert float(row["after_close_s"]) == pytest.approx(12.0)    # not 12 - 300

    # its EXIT, also a probe row one bar later, closes the same lot
    exit_bar = "2026-09-23T10:35:00-04:00"
    later = datetime(2026, 9, 23, 10, 35, 9, tzinfo=NY)
    monkeypatch.setattr(qe, "_now_et", lambda: later)
    qe._route_engine_events(state, _cfg(), [_ev("EXIT", exit_bar, 702.0, "strategy_exit; " + TAG, tid)],
                            False, log=NOOP, now=later)
    assert state["legs"].get("NOISE") is None
    row = _orders()[-1]
    assert row["action"] == "EXIT"
    assert float(row["after_close_s"]) == pytest.approx(9.0)


def test_ordinary_engine_row_after_close_unchanged():
    """A normal (closed-bar) row still subtracts the bar width: sent 12 s after its own
    bar closed reads after_close_s = 12."""
    bar = "2026-09-23T10:00:00-04:00"
    tid = trade_id.make("NOISE_382", bar, "long")
    state = {"legs": {}}
    qe._route_engine_events(state, _cfg(), [_ev("ENTRY", bar, 701.25, "", tid)], False,
                            log=NOOP, now=NOW)
    row = _orders()[-1]
    assert float(row["latency_s"]) == pytest.approx(312.0)
    assert float(row["after_close_s"]) == pytest.approx(12.0)


def test_consume_forwards_the_reason_column(tmp_path):
    paths = cs.DEFAULT_PATHS
    os.makedirs(paths["state_dir"], exist_ok=True)
    tid = trade_id.make("NOISE_382", BAR, "long")
    ev = {"emitted_at": NOW.isoformat(), "leg": "NOISE_382", "event": "ENTRY", "side": "long",
          "ref_time": BAR, "ref_price": 701.25, "shares": 1, "reason": TAG, "bar_source": "webull",
          "trade_id": tid, "size": 1.0, "keel_size": ""}
    cs._append_signals([ev], paths)
    out = qe._consume_engine_signals({"engine_cursor": 0}, _cfg(), NOW, log=NOOP)
    assert [e["reason"] for e in out] == [TAG]
