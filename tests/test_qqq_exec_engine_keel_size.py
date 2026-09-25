"""api/qqq_exec.py, engine ENTRY signals carrying a KEEL multiplier (2026-09-25 fix).

THE BUG. Live 2026-09-25 09:45 ET, NOISE entered 15 shares. The signal row in
api.cloud_signal's signals.csv carried size=1.5 and keel_size=1.5 (run #382 x KEEL), but
the book's lot and its closed-trade row both came back with keel_size blank -- the web
drawer's "#382 x KEEL" breakdown had nothing to show.

CAUSE. _consume_engine_signals (the function that turns new signals.csv rows into the
ENTRY/EXIT event dicts _route_engine_events acts on) copied "size" from each row but never
"keel_size", even though _route_engine_events (~line 3394) already forwards
`keel_size=e.get("keel_size")` to _open_lot, and _open_lot/_record_trade already know what
to do with it (_resolve_keel_size, TRADE_COLS' "keel_size" column) -- the value just never
reached the event dict in the first place.

This file proves the missing copy end to end -- signals.csv row -> _consume_engine_signals
-> _route_engine_events -> _open_lot -> the lot -> the closed trades.csv row -- and that the
ORDER QUANTITY still comes from "size" alone, never from "keel_size" (DISPLAY ONLY, see
_resolve_keel_size's own docstring vs _resolve_entry_size's): the two columns are given
deliberately DIFFERENT values below so a sizing regression that swapped one for the other,
or that started letting keel_size influence shares, would fail loudly.
"""
import csv
import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe                 # noqa: E402
from api import cloud_signal as cs              # noqa: E402
from api import trade_id                        # noqa: E402
from api import webull_orders as WO             # noqa: E402

NOOP = lambda *a, **k: None  # noqa: E731
NY_ENTRY = "2026-09-25T09:45:00-04:00"
NOW = datetime(2026, 9, 25, 9, 46)


def _cfg(tmp_path, **overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg.update(overrides)
    cfg["signal_source"] = "engine"
    # base share count deliberately NOT 1 -- proves sizing scales off "size", not off a
    # coincidental base of 1 that would hide a keel_size/size mixup.
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 10}
    # comfortably above the sized 10 x 1.5 = 15 shares below -- this file is about
    # keel_size, not about max_shares_per_leg's own clamp (see test_qqq_exec_order_sizing.py).
    cfg["max_shares_per_leg"] = 30
    return cfg


def _cs_paths(home):
    return cs._paths(home=str(home))


def _write_signal_rows(paths, rows):
    """Straight to cloud_signal's own signals.csv, bypassing step() -- these tests exercise
    qqq_exec's CONSUMPTION of the ledger, same convention as test_qqq_exec_engine_source.py."""
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})


@pytest.fixture(autouse=True)
def _patch_cs_home(tmp_path, monkeypatch):
    """Private tmp EDGELOG_HOME for cloud_signal's own paths -- never the owner's real
    C:\\EdgeLog (tests/conftest.py's live-system guard would fail this test if it tried)."""
    paths = _cs_paths(tmp_path / "cs_home")
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    return paths


def _isolate_adapter(tmp_path, monkeypatch, name="qqq_exec_out"):
    """Every file a lot open/close writes -> tmp, no phone push, broker adapter OFF with
    its own state in tmp too -- mirrors test_qqq_exec_engine_source.py's helper of the
    same name."""
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


def _csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ── 1. the exact regression: the raw CSV value must survive the ledger -> event step ──
def test_consume_engine_signals_copies_keel_size_raw_like_size(_patch_cs_home, tmp_path):
    paths = _patch_cs_home
    cfg = _cfg(tmp_path)
    tid = trade_id.make("NOISE_304", NY_ENTRY, "long")
    row = {"emitted_at": NY_ENTRY, "leg": "NOISE_304", "event": "ENTRY", "side": "long",
          "ref_time": NY_ENTRY, "ref_price": 729.82, "shares": 10, "reason": "",
          "bar_source": "webull", "trade_id": tid, "size": "1.5", "keel_size": "1.5"}
    state = {"legs": {}}
    _write_signal_rows(paths, [])                           # cold-activate the cursor
    assert qe._consume_engine_signals(state, cfg, datetime(2026, 9, 25, 9, 40), log=NOOP) == []
    _write_signal_rows(paths, [row])
    events = qe._consume_engine_signals(state, cfg, NOW, log=NOOP)
    assert len(events) == 1
    assert events[0]["size"] == "1.5", "unchanged -- this column already worked"
    assert events[0]["keel_size"] == "1.5", (
        "keel_size must survive the ledger -> event step exactly like size does")


def test_consume_engine_signals_keel_size_blank_on_an_older_row(_patch_cs_home, tmp_path):
    """A row written before the "keel_size" column existed (or a non-KEEL leg's row) must
    resolve to blank, never a guessed number -- csv.DictReader hands back "" for a column
    present in the header but empty on that row."""
    paths = _patch_cs_home
    cfg = _cfg(tmp_path)
    tid = trade_id.make("ORB_R6", NY_ENTRY, "long")
    row = {"emitted_at": NY_ENTRY, "leg": "ORB_R6", "event": "ENTRY", "side": "long",
          "ref_time": NY_ENTRY, "ref_price": 700.0, "shares": 5, "reason": "",
          "bar_source": "webull", "trade_id": tid}                 # no size/keel_size at all
    state = {"legs": {}}
    _write_signal_rows(paths, [])
    assert qe._consume_engine_signals(state, cfg, datetime(2026, 9, 25, 9, 40), log=NOOP) == []
    _write_signal_rows(paths, [row])
    events = qe._consume_engine_signals(state, cfg, NOW, log=NOOP)
    assert events[0]["keel_size"] == ""


# ── 2. end to end: the opened lot, the order size, and the closed trade row ────────────
def _ev(event, ref_time, ref_price, tid, size=None, keel_size=None, leg="NOISE_304", side="long"):
    """One event exactly as the fixed _consume_engine_signals hands it to
    _route_engine_events."""
    return {"leg": leg, "event": event, "side": side, "ref_time": ref_time,
           "ref_price": float(ref_price), "bar_source": "webull", "trade_id": tid,
           "size": size, "keel_size": keel_size}


def test_keel_size_flows_to_the_lot_and_the_trade_row_without_moving_the_order_size(
        tmp_path, monkeypatch):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg, state = _cfg(tmp_path), {"legs": {}}
    tid = trade_id.make("NOISE_304", NY_ENTRY, "long")

    # size and keel_size are DELIBERATELY different (1.5 vs 3.0): if a future change ever
    # sized the order off keel_size instead of size, this test would catch it.
    qe._route_engine_events(
        state, cfg, [_ev("ENTRY", NY_ENTRY, 729.82, tid, size="1.5", keel_size="3.0")],
        False, log=NOOP, now=datetime(2026, 9, 25, 10, 0))

    lot = state["legs"]["NOISE"]
    assert lot["keel_size"] == 3.0, "the KEEL multiplier must reach the lot for display"
    assert lot["size"] == 1.5, "the sizing multiplier is unaffected by keel_size"
    # cfg["shares"]["NOISE"] (10) x size (1.5) = 15 -- the live bug's own numbers.
    assert lot["shares_total"] == 15, "order quantity must come from size alone, never keel_size"
    order = _csv_rows(qe.ORDERS_CSV)[-1]
    assert int(order["shares"]) == 15

    qe._route_engine_events(
        state, cfg, [_ev("EXIT", "2026-09-25T10:05:00-04:00", 731.0, tid)],
        False, log=NOOP, now=datetime(2026, 9, 25, 10, 6))
    assert "NOISE" not in state["legs"]
    (trade,) = _csv_rows(qe.TRADES_CSV)
    assert trade["keel_size"] == "3.0", "the trade row -- the web drawer's '#382 x KEEL' source"
    assert trade["size"] == "1.5"
    assert int(trade["shares"]) == 15


def test_a_leg_with_no_keel_overlay_publishes_a_blank_keel_size(tmp_path, monkeypatch):
    """No KEEL block on this leg (or an older row): keel_size must read blank on both the
    lot and the trade row, never a guessed number (see _resolve_keel_size's own contract:
    a real 1.0 means "keel ran and stood down", not "no overlay at all")."""
    _isolate_adapter(tmp_path, monkeypatch)
    cfg, state = _cfg(tmp_path), {"legs": {}}
    tid = trade_id.make("ORB_R6", NY_ENTRY, "long")

    qe._route_engine_events(
        state, cfg, [_ev("ENTRY", NY_ENTRY, 700.0, tid, size=None, keel_size=None, leg="ORB_R6")],
        False, log=NOOP, now=datetime(2026, 9, 25, 10, 0))
    lot = state["legs"]["ORB"]
    assert lot["keel_size"] is None
    assert lot["shares_total"] == 5, "unsized -- the plain configured share count"

    qe._route_engine_events(
        state, cfg, [_ev("EXIT", "2026-09-25T10:05:00-04:00", 701.0, tid, leg="ORB_R6")],
        False, log=NOOP, now=datetime(2026, 9, 25, 10, 6))
    (trade,) = _csv_rows(qe.TRADES_CSV)
    assert trade["keel_size"] == ""
