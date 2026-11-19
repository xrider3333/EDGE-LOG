"""api/qqq_exec.py -- the guards around WITHDRAWN signals (ENGU-Q hardening, 2026-11-18).

WHY. The two ENGU-Q "ghost" entries (2026-09-17 15:07, 2026-09-23 14:00) sit in the live
ledger as VOID_ENTRY rows, and each has a Webull order stamped a couple of seconds after the
void row's own `emitted_at`. That reads like the executor ordering a bar the engine had just
withdrawn, and it is not: VOID_* rows are written RETROSPECTIVELY by a repair tool
(tools/cloud_signal_repair_20260914.py, tools/enguq_phantom_mark_20260926.py) that relabels the
original ENTRY row and KEEPS its stamp, so at order time the row was an ordinary ENTRY. These
tests hold the three doors that follow shut, and hold the audit that counts them honest.

Coverage:
  1. A VOID_ENTRY / VOID_EXIT / VOID_SEED row is never returned as an actionable event, and is
     refused BY NAME -- counted under `engine_void_row` with a timeline event -- instead of
     falling silently down the same branch that skips SEED.
  2. An ENTRY whose own engine trade record carries `ghost: true` is refused
     (`entry_ghost_record`) and opens no lot; the same ENTRY without the marker opens one, so
     the guard is the marker and not the shape of the row.
  3. A busy-leg refusal now leaves an orders.csv row -- REFUSED, no price, nothing sent -- so
     the entry a ghost's still-open lot held out is visible in the one ledger a reconciliation
     reads (the 2026-09-17 ghost held the REAL 15:09 entry out with nothing but a WARN line).
  4. The engine ghost reader never raises and refuses nothing when the engine's state file is
     missing or unreadable.
  5. TRADE_COLS carries the _migrate_csv_header warning, which is why the ghost-marking tool
     could not add a `note` column.
"""
import csv
import json
import os
import sys
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe                 # noqa: E402
from api import cloud_signal as cs              # noqa: E402
from api import trade_id as _tid                # noqa: E402

NY = qe._NY


def _cfg(**overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["signal_source"] = "engine"
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}
    cfg.update(overrides)
    return cfg


def _write_rows(paths, rows):
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})


def _row(leg, event, ref_time, ref_price, side="long", trade_id="", emitted_at=None):
    return {"emitted_at": emitted_at or ref_time, "leg": leg, "event": event, "side": side,
            "ref_time": ref_time, "ref_price": ref_price, "shares": 5, "reason": "",
            "bar_source": "webull", "trade_id": trade_id}


@pytest.fixture(autouse=True)
def _cs_home(tmp_path, monkeypatch):
    """Private EDGELOG_HOME for cloud_signal's module-level paths, so nothing here can
    reach the owner's real C:\\EdgeLog store."""
    paths = cs._paths(home=str(tmp_path / "cs_home"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    return paths


# ── 1. withdrawn rows are refused by name ------------------------------------------------
@pytest.mark.parametrize("event", ["VOID_ENTRY", "VOID_EXIT", "VOID_SEED"])
def test_void_rows_are_refused_by_name_and_counted(_cs_home, event):
    paths = _cs_home
    _write_rows(paths, [])
    state, cfg = {"legs": {}}, _cfg()
    now = datetime(2026, 9, 17, 15, 9)
    assert qe._consume_engine_signals(state, cfg, now, log=lambda *_: None) == []

    tid = "ENGUQ_335-20260917T190700Z-L"
    _write_rows(paths, [_row("ENGUQ_335", event, "2026-09-17 15:07:00", 716.8592, trade_id=tid)])
    events = qe._consume_engine_signals(state, cfg, now, log=lambda *_: None)

    assert events == [], "a withdrawn row must never come back as an actionable event"
    counts = (state.get("trade_id_checks") or {}).get("today") or {}
    assert counts.get("engine_void_row") == 1, (
        "the refusal must be COUNTED, not silent -- a withdrawn row that reaches the consumer "
        "is the one thing this guard exists to say out loud")
    last = (state.get("trade_id_checks") or {}).get("last") or {}
    assert last.get("kind") == "engine_void_row" and last.get("event") == event
    assert last.get("row_trade_id") == tid
    assert state["engine_cursor"] == 1, "the cursor still advances past a refused row"


def test_engine_void_row_is_a_declared_issue_kind():
    """A counter nothing publishes is a counter nobody sees: both new kinds must be in
    TRADE_ID_ISSUES, which is what _build_trade_id_status walks."""
    assert "engine_void_row" in qe.TRADE_ID_ISSUES
    assert "entry_ghost_record" in qe.TRADE_ID_ISSUES
    pub = qe._build_trade_id_status({"trade_id_checks": {}})
    assert "engine_void_row" in (pub.get("today") or {})
    assert "entry_ghost_record" in (pub.get("today") or {})


# ── 2. ghost-marked engine records ------------------------------------------------------
def _engine_state_with_ghost(paths, tid, ghost=True):
    os.makedirs(paths["state_dir"], exist_ok=True)
    rec = {"entry_time": "2026-09-17T15:07:00-04:00", "side": "long", "entry_px": 716.8592,
           "shares": 139, "exit_emitted": False, "exit_time": None, "exit_px": None}
    if ghost:
        rec["ghost"] = True
        rec["ghost_reason"] = "ghost: phantom limit entry, the backtest never takes it"
    with open(paths["state_path"], "w", encoding="utf-8") as f:
        json.dump({"legs": {"ENGUQ_335": {"trades": {tid: rec}}}}, f)


def _entry_event(day, hhmm, tid, price=716.8592):
    return {"leg": "ENGUQ_335", "event": "ENTRY", "side": "long",
            "ref_time": f"{day} {hhmm}:00", "ref_price": price, "bar_source": "webull",
            "trade_id": tid, "size": "", "keel_size": "", "reason": ""}


def test_ghost_marked_entry_is_refused(_cs_home, monkeypatch, tmp_path):
    paths = _cs_home
    now = datetime(2026, 9, 17, 15, 8, tzinfo=NY)
    tid = _tid.make("ENGUQ_335", "2026-09-17 15:07:00", "long", default_tz=NY)
    _engine_state_with_ghost(paths, tid, ghost=True)
    monkeypatch.setattr(qe, "ORDERS_CSV", str(tmp_path / "orders.csv"))

    state = {"legs": {}, "trading_day": "2026-09-17"}
    qe._route_engine_events(state, _cfg(), [_entry_event("2026-09-17", "15:07", tid)],
                            False, log=lambda *_: None, now=now)

    assert state["legs"].get("ENGUQ") in (None, {}), "a ghost-marked entry must open no lot"
    counts = (state.get("trade_id_checks") or {}).get("today") or {}
    assert counts.get("entry_ghost_record") == 1


def test_the_same_entry_without_the_marker_opens_a_lot(_cs_home, monkeypatch, tmp_path):
    """The guard must be the MARKER, not the row: the identical ENTRY with ghost absent
    still opens its lot, so this change refuses nothing that trades today."""
    paths = _cs_home
    now = datetime(2026, 9, 17, 15, 8, tzinfo=NY)
    tid = _tid.make("ENGUQ_335", "2026-09-17 15:07:00", "long", default_tz=NY)
    _engine_state_with_ghost(paths, tid, ghost=False)
    monkeypatch.setattr(qe, "ORDERS_CSV", str(tmp_path / "orders.csv"))

    state = {"legs": {}, "trading_day": "2026-09-17"}
    qe._route_engine_events(state, _cfg(), [_entry_event("2026-09-17", "15:07", tid)],
                            False, log=lambda *_: None, now=now)

    assert (state["legs"].get("ENGUQ") or {}).get("trade_id") == tid
    counts = (state.get("trade_id_checks") or {}).get("today") or {}
    assert not counts.get("entry_ghost_record")


# ── 3. a busy-leg refusal leaves an orders.csv row --------------------------------------
def test_entry_leg_busy_writes_a_refused_orders_row(_cs_home, monkeypatch, tmp_path):
    """The 2026-09-17 shape: a lot that should not exist is open, the REAL later entry is
    refused, and before this change the refusal existed only as a WARN line and a counter."""
    orders = tmp_path / "orders.csv"
    monkeypatch.setattr(qe, "ORDERS_CSV", str(orders))
    now = datetime(2026, 9, 17, 15, 10, tzinfo=NY)
    open_tid = _tid.make("ENGUQ_335", "2026-09-17 15:07:00", "long", default_tz=NY)
    new_tid = _tid.make("ENGUQ_335", "2026-09-17 15:09:00", "long", default_tz=NY)
    state = {"legs": {"ENGUQ": {"trade_id": open_tid, "side": "long", "shares": 5,
                                "entry_px": 716.8592, "entry_ts": "2026-09-17 15:07:00"}},
             "trading_day": "2026-09-17"}

    qe._route_engine_events(state, _cfg(), [_entry_event("2026-09-17", "15:09", new_tid, 716.7405)],
                            False, log=lambda *_: None, now=now)

    counts = (state.get("trade_id_checks") or {}).get("today") or {}
    assert counts.get("entry_leg_busy") == 1
    assert orders.exists(), "the busy-leg refusal must leave a row in orders.csv"
    rows = list(csv.DictReader(open(orders, encoding="utf-8", newline="")))
    busy = [r for r in rows if "entry_leg_busy" in str(r.get("reason") or "")]
    assert len(busy) == 1, "exactly one refused row for the refused entry"
    assert busy[0]["action"] == "ENTER" and busy[0]["leg"] == "ENGUQ"
    assert str(busy[0]["reason"]).startswith("REFUSED"), "same convention as the other guards"
    assert not str(busy[0].get("qqq_px") or ""), "a refusal carries no price: nothing was sent"


# ── 4. the ghost reader is fail-open -----------------------------------------------------
def test_ghost_reader_returns_empty_when_the_engine_state_is_missing(_cs_home):
    assert not os.path.exists(_cs_home["state_path"])
    assert qe._engine_ghost_trade_ids(log=lambda *_: None) == set()


def test_ghost_reader_returns_empty_on_unreadable_state(_cs_home):
    os.makedirs(_cs_home["state_dir"], exist_ok=True)
    with open(_cs_home["state_path"], "w", encoding="utf-8") as f:
        f.write("{not json")
    assert qe._engine_ghost_trade_ids(log=lambda *_: None) == set(), (
        "an unreadable engine state must refuse nothing -- fail-open, like every other "
        "cross-process read in this module")


# ── 5. the TRADE_COLS warning -------------------------------------------------------------
def test_trade_cols_carries_the_migrate_header_warning():
    src = open(os.path.join(ROOT, "api", "qqq_exec.py"), encoding="utf-8").read()
    head = src[:src.index("TRADE_COLS = ")]
    note = head[head.rindex("# NOTE (2026-11-18)"):]
    assert "_migrate_csv_header" in note and "corrections.log" in note, (
        "TRADE_COLS must say that _migrate_csv_header rewrites the on-disk header to this "
        "tuple, so a column added anywhere else disappears on the next append")
