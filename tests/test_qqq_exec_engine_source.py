"""api/qqq_exec.py, signal_source == "engine" -- the QQQ shadow book taking its
entries/exits from api/cloud_signal.py's own signal ledger instead of NinjaTrader's
fills.csv (2026-09-13, "move QQQ shadow off NinjaTrader").

Coverage:
  1. The NOISE leg resolves to run #382's definition (NOISE_1_8_CT304.py, OWNER DECISION
     2026-09-23), and the retired run #304 engine key still resolves through qqq_exec's
     own leg map even though it is gone from cloud_signal.CROWN_LEGS.
  2. Consuming api.cloud_signal's signals.csv is idempotent across a simulated adapter
     restart: the same rows are never re-entered/re-exited twice.
  3. First-ever activation of engine mode absorbs any PRE-EXISTING signal rows without
     acting on them (cloud_signal's own SEED rule, mirrored on this side of the fence).
  4. A signal consumed long after it was emitted (this adapter was "down") is never
     entered.
  5. Engine mode never opens fills.csv, addon_heartbeat.json, or the NQ 10s export --
     asserted by patching `open` and failing the test if any of those paths are touched.
  6. TRADE IDENTITY (2026-09-14, tools/qqq_failover_sim.py scenario F): an EXIT closes only
     the lot whose trade id it carries; id-less / foreign / replay-leftover rows are never
     applied, and are counted and published; broker order ids come from the trade id.
"""
import builtins
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe                 # noqa: E402
from api import cloud_signal as cs              # noqa: E402
from api import trade_id                        # noqa: E402
from api import webull_orders as WO             # noqa: E402


# ── 1. leg definition -----------------------------------------------------------------
def test_noise_leg_resolves_to_run_382():
    """api/cloud_signal.py's NOISE leg must be exactly run #382's definition
    (NOISE_1_8_CT304.py: the #304 crown's own core, frozen literally inside that file,
    plus the validated hourly-compression SIZE tilt) -- OWNER DECISION 2026-09-23, not
    re-derived, not left on the retired #304 config. The retired #304 engine key must be
    GONE from CROWN_LEGS (replaced, not kept alongside) but must still resolve through
    qqq_exec's own leg map, so an old signals.csv row or an in-flight trade id from
    before the swap is never orphaned."""
    assert "NOISE_382" in cs.CROWN_LEGS
    assert "NOISE_304" not in cs.CROWN_LEGS, (
        "the retired #304 engine key must be gone from CROWN_LEGS, not just added-alongside")
    assert "NOISE_SBS_V90" not in cs.CROWN_LEGS, "the stale #243 key must be gone, not just added-alongside"
    leg = cs.CROWN_LEGS["NOISE_382"]
    assert leg["strategy"] == "NOISE_1_8_CT304.py"
    assert leg["timeframe"] == "5m"
    assert leg["params"] == {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16,
                             "gate_ratio": 1.15}
    assert leg["warmup_sessions"] == cs.DEFAULT_WARMUP_SESSIONS, "same warm-up as before the swap"
    assert qe.ENGINE_LEG_MAP.get("NOISE_382") == "NOISE", (
        "qqq_exec's own leg map must track the cloud_signal rename")
    assert qe.ENGINE_LEG_MAP.get("NOISE_304") == "NOISE", (
        "the retired engine key must still resolve to the same exec leg, so an old ledger "
        "row or in-flight trade id from before the swap is never orphaned")


def _cfg(tmp_path, **overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg.update(overrides)
    cfg["signal_source"] = "engine"
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}
    return cfg


def _cs_paths(home):
    return cs._paths(home=str(home))


def _write_signal_rows(paths, rows):
    """Write `rows` (each a SIGNAL_COLS-shaped dict) straight to cloud_signal's own
    signals.csv, bypassing step() -- these tests exercise qqq_exec's CONSUMPTION of the
    ledger, not cloud_signal's own emission (that is tests/test_cloud_signal.py's job)."""
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})


def _row(leg, event, ref_time, ref_price, side="long", emitted_at=None, bar_source="webull",
         trade_id=""):
    return {"emitted_at": emitted_at or ref_time, "leg": leg, "event": event, "side": side,
           "ref_time": ref_time, "ref_price": ref_price, "shares": 5, "reason": "",
           "bar_source": bar_source, "trade_id": trade_id}


@pytest.fixture(autouse=True)
def _patch_cs_home(tmp_path, monkeypatch):
    """Point api.cloud_signal's module-level DEFAULT_PATHS (what qqq_exec's
    _cs_module()-based helpers read) at a private tmp EDGELOG_HOME for every test in
    this file, so nothing here can ever touch the owner's real C:\\EdgeLog."""
    paths = _cs_paths(tmp_path / "cs_home")
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    return paths


# ── 2+3. idempotent consumption across a simulated restart ----------------------------
def test_cold_activation_absorbs_existing_rows_without_acting(_patch_cs_home, tmp_path):
    paths = _patch_cs_home
    _write_signal_rows(paths, [
        _row("ORB_R6", "SEED", "", ""),
        _row("ORB_R6", "ENTRY", "2026-09-01 09:40:00", 700.0),
        _row("ORB_R6", "EXIT", "2026-09-01 10:00:00", 701.0),
    ])
    state = {"legs": {}}
    cfg = _cfg(tmp_path)
    events = qe._consume_engine_signals(state, cfg, datetime(2026, 9, 2, 9, 45), log=lambda *_: None)
    assert events == [], "first-ever activation must absorb pre-existing rows, not replay them"
    assert state["engine_cursor"] == 3


def test_restart_resumes_from_saved_cursor_never_double_enters(_patch_cs_home, tmp_path):
    paths = _patch_cs_home
    now = datetime(2026, 9, 8, 9, 41)
    _write_signal_rows(paths, [_row("ORB_R6", "ENTRY", "2026-09-08 09:40:00", 700.0)])

    # activation (seeds cursor at 0 rows... no, at len==1 since the row is already there)
    state = {"legs": {}}
    cfg = _cfg(tmp_path)
    assert qe._consume_engine_signals(state, cfg, now, log=lambda *_: None) == []
    assert state["engine_cursor"] == 1

    # a NEW entry arrives
    _write_signal_rows(paths, [
        _row("ORB_R6", "ENTRY", "2026-09-08 09:40:00", 700.0),
        _row("ORB_R6", "EXIT", "2026-09-08 09:45:00", 702.0),
    ])
    events = qe._consume_engine_signals(state, cfg, now + timedelta(minutes=5), log=lambda *_: None)
    assert [e["event"] for e in events] == ["EXIT"]
    assert state["engine_cursor"] == 2

    # SIMULATED RESTART: fresh in-memory state built from the persisted cursor value
    # only (as load_state() would hand back from state.json) -- must not re-emit EXIT.
    restarted_state = {"legs": {}, "engine_cursor": state["engine_cursor"]}
    events2 = qe._consume_engine_signals(restarted_state, cfg, now + timedelta(minutes=6),
                                        log=lambda *_: None)
    assert events2 == [], "a restart must never re-emit an already-consumed row"


# ── 4. a signal consumed long after emission is never entered -------------------------
def test_stale_by_consumption_lag_is_never_entered(_patch_cs_home, tmp_path):
    paths = _patch_cs_home
    now0 = datetime(2026, 9, 8, 9, 40)
    _write_signal_rows(paths, [])
    state = {"legs": {}}
    cfg = _cfg(tmp_path)
    assert qe._consume_engine_signals(state, cfg, now0, log=lambda *_: None) == []
    assert state["engine_cursor"] == 0

    # a real, timely ENTRY was emitted while this adapter was "down" -- discovered only
    # much later (longer than ENGINE_CONSUME_STALE_SEC after its own emitted_at)
    emitted = "2026-09-08 09:41:00"
    _write_signal_rows(paths, [_row("ORB_R6", "ENTRY", emitted, 700.0, emitted_at=emitted)])
    late_now = datetime(2026, 9, 8, 10, 30)  # 49 minutes later > ENGINE_CONSUME_STALE_SEC (30min)
    events = qe._consume_engine_signals(state, cfg, late_now, log=lambda *_: None)
    assert events == [], "a signal discovered long after it was emitted must never be entered"
    assert state["engine_cursor"] == 1, "the row must still be marked consumed (never re-checked)"


def test_timely_consumption_is_entered(_patch_cs_home, tmp_path):
    paths = _patch_cs_home
    _write_signal_rows(paths, [])  # cloud_signal's ledger already exists (it ticks first in prod)
    state = {"legs": {}}
    cfg = _cfg(tmp_path)
    assert qe._consume_engine_signals(state, cfg, datetime(2026, 9, 8, 9, 40), log=lambda *_: None) == []

    emitted = "2026-09-08 09:41:00"
    _write_signal_rows(paths, [_row("NOISE_304", "ENTRY", emitted, 500.0, emitted_at=emitted)])
    events = qe._consume_engine_signals(state, cfg, datetime(2026, 9, 8, 9, 42),
                                        log=lambda *_: None)
    assert len(events) == 1 and events[0]["event"] == "ENTRY" and events[0]["leg"] == "NOISE_304"


# ── 5. engine mode never touches NinjaTrader/NQ files ----------------------------------
_FORBIDDEN_SUBSTRINGS = ("fills.csv", "addon_heartbeat.json", "NQ_10s.csv")


def test_engine_mode_tick_never_opens_a_ninjatrader_or_nq_file(_patch_cs_home, tmp_path, monkeypatch):
    """Runs a full tick() with signal_source=engine and patches builtins.open to raise
    if anything asks for fills.csv / addon_heartbeat.json / NQ_10s.csv -- the exact
    files the module docstring promises engine mode will never touch."""
    paths = _patch_cs_home
    _write_signal_rows(paths, [])  # empty ledger, but present -- exercises the real read path

    out_dir = tmp_path / "qqq_exec_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out_dir))
    monkeypatch.setattr(qe, "CONFIG_PATH", str(out_dir / "config.json"))
    monkeypatch.setattr(qe, "STATE_PATH", str(out_dir / "state.json"))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out_dir / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out_dir / "trades.csv"))

    real_open = builtins.open

    def guarded_open(file, *a, **k):
        s = str(file)
        for bad in _FORBIDDEN_SUBSTRINGS:
            assert bad not in s, f"engine mode must never open {bad} (tried to open {s!r})"
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", guarded_open)

    def boom_quote(*a, **k):
        raise AssertionError("engine mode must never call the Webull quote function")

    def boom_ratio(*a, **k):
        raise AssertionError("engine mode must never calibrate the NQ:QQQ ratio")

    cfg, state, doc = qe.tick(
        fills_path=r"C:\EdgeLog\fills.csv",   # deliberately points at a real-looking path
        now=datetime(2026, 9, 8, 9, 40), quote_fn=boom_quote, ratio_fn=boom_ratio,
        force_calib=True, log=lambda *_: None)

    assert cfg["signal_source"] == "engine"
    assert doc["signal_source"] == "engine"


def test_invalid_signal_source_falls_back_to_engine(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"signal_source": "bogus"}', encoding="utf-8")
    cfg = qe.load_config(path=str(cfg_path), log=lambda *_: None)
    assert cfg["signal_source"] == "engine"


# ── 6. TRADE IDENTITY (2026-09-14) -----------------------------------------------------------
# The live evidence behind these: C:\EdgeLog\cloud_signal\signals.csv delivered, at 09:31 ET on
# 2026-09-14, the EXIT of a 2026-09-03 NOISE_304 trade (entered 11:00, exit bar 15:55) that a
# replay had left behind. The adapter used to close whatever NOISE lot was open.
NY = ZoneInfo("America/New_York")
NOOP = lambda *a, **k: None  # noqa: E731
NOW = datetime(2026, 9, 15, 10, 30, tzinfo=NY)
TODAY_ENTRY = "2026-09-15T09:55:00-04:00"
OLD_ENTRY = "2026-09-03T11:00:00-04:00"
OLD_EXIT = "2026-09-03T15:55:00-04:00"
TODAY_TID = trade_id.make("NOISE_304", TODAY_ENTRY, "long")
OLD_TID = trade_id.make("NOISE_304", OLD_ENTRY, "long")


def _isolate_adapter(tmp_path, monkeypatch, name="qqq_exec_out"):
    """Every file a lot open/close writes -> tmp, no phone push, and a broker order adapter
    in OFF mode whose own state file is in tmp too (the real one defaults to C:\\EdgeLog)."""
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


def _ev(event, ref_time, ref_price, tid="", leg="NOISE_304", side="long"):
    """One event exactly as _consume_engine_signals hands it to _route_engine_events."""
    return {"leg": leg, "event": event, "side": side, "ref_time": ref_time,
            "ref_price": float(ref_price), "bar_source": "webull", "trade_id": tid}


def _route(state, cfg, *events):
    qe._route_engine_events(state, cfg, list(events), False, log=NOOP, now=NOW)


def _csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _issues(state):
    return {k: v for k, v in ((state.get("trade_id_checks") or {}).get("today") or {}).items() if v}


def test_exit_closes_only_the_lot_whose_trade_id_it_carries(tmp_path, monkeypatch):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg, state = _cfg(tmp_path), {"legs": {}}
    _route(state, cfg, _ev("ENTRY", TODAY_ENTRY, 700.00, TODAY_TID))
    assert state["legs"]["NOISE"]["trade_id"] == TODAY_TID
    assert state["legs"]["NOISE"]["entry_ref_time"] == TODAY_ENTRY

    _route(state, cfg, _ev("EXIT", OLD_EXIT, 717.61, OLD_TID))
    assert "NOISE" in state["legs"], "the 09-03 trade's EXIT must never close today's lot"
    assert _csv_rows(qe.TRADES_CSV) == []
    assert [r["intent"] for r in _csv_rows(qe.BROKER_ORDERS_CSV)] == ["OPEN"], "and never mirrors a SELL"
    assert _issues(state) == {"exit_id_mismatch": 1}
    last = state["trade_id_checks"]["last"]
    assert (last["row_trade_id"], last["lot_trade_id"]) == (OLD_TID, TODAY_TID)
    assert state["events"][-1]["kind"] == "exit_id_mismatch"
    assert "2026-09-03 11:00" in state["events"][-1]["text"]

    _route(state, cfg, _ev("EXIT", "2026-09-15T10:25:00-04:00", 704.00, TODAY_TID))
    assert "NOISE" not in state["legs"], "the trade's own EXIT still closes it"
    (trade,) = _csv_rows(qe.TRADES_CSV)
    assert float(trade["exit_px"]) == pytest.approx(703.99)   # 704.00 less the 1c exit slippage
    assert [r["intent"] for r in _csv_rows(qe.BROKER_ORDERS_CSV)] == ["OPEN", "CLOSE"]


def test_exit_without_a_matching_identity_is_never_applied(tmp_path, monkeypatch):
    """OLD ROWS rule: an EXIT with no trade id closes nothing, and neither does any EXIT
    against a lot that predates trade ids -- both left for the flat-by/breaker/kill closes."""
    _isolate_adapter(tmp_path, monkeypatch)
    cfg, state = _cfg(tmp_path), {"legs": {}}
    _route(state, cfg, _ev("ENTRY", TODAY_ENTRY, 700.00, TODAY_TID))
    _route(state, cfg, _ev("EXIT", "2026-09-15T10:25:00-04:00", 704.00, tid=""))
    assert state["legs"]["NOISE"]["trade_id"] == TODAY_TID
    assert _issues(state) == {"exit_no_id": 1}

    legacy = {"legs": {"NOISE": dict(state["legs"]["NOISE"], trade_id=None, entry_ref_time=None)}}
    _route(legacy, cfg, _ev("EXIT", "2026-09-15T10:25:00-04:00", 704.00, TODAY_TID))
    assert "NOISE" in legacy["legs"], "a lot with no trade id cannot be proven to be this EXIT's trade"
    assert _issues(legacy) == {"exit_id_mismatch": 1}
    assert _csv_rows(qe.TRADES_CSV) == []
    # ...and it blocks the leg's next entry, so the rails must still be able to close it
    later = "2026-09-15T10:40:00-04:00"
    _route(legacy, cfg, _ev("ENTRY", later, 702.00, trade_id.make("NOISE_304", later, "long")))
    assert _issues(legacy) == {"exit_id_mismatch": 1, "entry_leg_busy": 1}
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (701.0, "engine_test"))
    qe._close_all(legacy, cfg, "EOD", quote_fn=None, ratio_fn=None, log=NOOP)
    assert "NOISE" not in legacy["legs"] and len(_csv_rows(qe.TRADES_CSV)) == 1

    # an EXIT with nothing open is only bookkeeping -- published, but not a refused signal
    flat, lines = {"legs": {}}, []
    qe._route_engine_events(flat, cfg, [_ev("EXIT", OLD_EXIT, 717.61, OLD_TID)], False,
                            log=lines.append, now=NOW)
    assert _issues(flat) == {"exit_no_lot": 1}
    assert qe._build_trade_id_status(flat, "2026-09-15")["refused_today"] == 0
    # the log keeps the old wording verbatim: tools/qqq_failover_sim.py scenario A and the
    # verification step of docs/CLOUD_SIGNAL_REPAIR_20260914.md both search for it
    assert any("engine EXIT for NOISE with no open shadow lot -- skipped" in s for s in lines)


def test_entry_rows_whose_identity_does_not_check_out_open_nothing(tmp_path, monkeypatch):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg, state = _cfg(tmp_path), {"legs": {}}
    _route(state, cfg,
           _ev("ENTRY", TODAY_ENTRY, 700.00, tid=""),                                  # old row
           _ev("ENTRY", TODAY_ENTRY, 700.00,
               trade_id.make("NOISE_304", "2026-09-15T09:50:00-04:00", "long")),       # id != its bar
           _ev("ENTRY", OLD_ENTRY, 713.57, OLD_TID))                                   # replay leftover
    assert state["legs"] == {}
    assert _csv_rows(qe.ORDERS_CSV) == [] and _csv_rows(qe.BROKER_ORDERS_CSV) == []
    assert _issues(state) == {"entry_no_id": 1, "entry_id_conflict": 1, "entry_other_session": 1}
    assert qe._build_trade_id_status(state, "2026-09-15")["refused_today"] == 3


def test_repeat_or_second_entry_while_a_lot_is_open(tmp_path, monkeypatch):
    _isolate_adapter(tmp_path, monkeypatch)
    cfg, state = _cfg(tmp_path), {"legs": {}}
    other = "2026-09-15T10:20:00-04:00"
    _route(state, cfg, _ev("ENTRY", TODAY_ENTRY, 700.00, TODAY_TID),
           _ev("ENTRY", TODAY_ENTRY, 700.00, TODAY_TID),
           _ev("ENTRY", other, 702.00, trade_id.make("NOISE_304", other, "long")))
    assert state["legs"]["NOISE"]["trade_id"] == TODAY_TID
    assert len(_csv_rows(qe.BROKER_ORDERS_CSV)) == 1
    assert _issues(state) == {"entry_duplicate": 1, "entry_leg_busy": 1}


def test_broker_order_ids_come_from_the_trade_id_not_the_clock(tmp_path, monkeypatch):
    """Two hosts (separate folders, separate order adapters) open and close the same trade at
    different wall-clock moments: the client_order_ids must be identical, fit Webull's 40
    characters verbatim, and never depend on when a process happened to open the lot."""
    ids = []
    for host, clock in (("pc", datetime(2026, 9, 15, 10, 0, 7, tzinfo=NY)),
                        ("vm", datetime(2026, 9, 15, 10, 3, 41, tzinfo=NY))):
        _isolate_adapter(tmp_path, monkeypatch, name=host)
        monkeypatch.setattr(qe, "_now_et", lambda clock=clock: clock)
        cfg, state = _cfg(tmp_path), {"legs": {}}
        _route(state, cfg, _ev("ENTRY", TODAY_ENTRY, 700.00, TODAY_TID))
        _route(state, cfg, _ev("EXIT", "2026-09-15T10:25:00-04:00", 704.00, TODAY_TID))
        ids.append([(r["signal_id"], r["client_order_id"]) for r in _csv_rows(qe.BROKER_ORDERS_CSV)])
    assert ids[0] == ids[1], f"order ids differ between hosts: {ids}"
    assert ids[0] == [("qxNOISE30420260915T135500ZLO",) * 2,
                      ("qxNOISE30420260915T135500ZLC",) * 2]
    # Webull's US order reference: "max 32 chars, must be unique per account" -- every current
    # leg's id must reach the broker verbatim, letters and digits only
    for leg in cs.CROWN_LEGS:
        for intent in ("OPEN", "CLOSE"):
            sid = qe._broker_signal_id(leg, "x", intent, seq=1,
                                       trade_id=trade_id.make(leg, TODAY_ENTRY, "short"))
            assert len(sid) <= 32 and sid.isalnum() and WO._sanitize_client_order_id(sid) == sid, sid

    # a later partial reduce keeps its number; a leg too long for 32 characters falls to
    # webull_orders' hash form, which is still the same on every host
    assert qe._broker_signal_id("NOISE", "x", "CLOSE", seq=2, trade_id=TODAY_TID).endswith("ZLC2")
    long_tid = trade_id.make("NOISE_304_NEIGHBOURHOOD_V2", TODAY_ENTRY, "long")
    long_id = qe._broker_signal_id("NOISE", "2026-09-15 10:00:07", "OPEN", trade_id=long_tid)
    assert WO._sanitize_client_order_id(long_id) == WO._sanitize_client_order_id(
        qe._broker_signal_id("NOISE", "2026-09-15 10:03:41", "OPEN", trade_id=long_tid))
    assert len(WO._sanitize_client_order_id(long_id)) <= 32

    # ninjatrader mode has no engine row: the id comes from the NT entry fill's own timestamp
    _isolate_adapter(tmp_path, monkeypatch, name="nt")
    state = {"legs": {}, "_px_source": "test"}
    fill_dt = datetime(2026, 9, 15, 9, 35, 0, tzinfo=NY)
    qe._open_lot(state, _cfg(tmp_path), "ORB", "long", 2, 30000.0, 700.0, 0.0, log=NOOP,
                 f={"dt": fill_dt, "exec_id": "e1", "price": 30000.0, "instrument": "NQ 12-26"})
    assert state["legs"]["ORB"]["trade_id"] == "NT_ORB-20260915T133500Z-L"


def test_tick_publishes_the_lot_trade_id_and_the_mismatch_count(_patch_cs_home, tmp_path, monkeypatch):
    """End to end through signals.csv and tick(): the stale EXIT is refused, and the published
    doc says so (trade_ids counters + the event timeline) while the position keeps its id."""
    paths = _patch_cs_home
    _isolate_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (701.0, "engine_test"))
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["heartbeat_path"], "w", encoding="utf-8") as f:
        json.dump({"ts": datetime.now(NY).isoformat(), "ok": True, "note": "test"}, f)
    cfg = _cfg(tmp_path, kill_file=str(tmp_path / "KILL"))
    state = qe._default_state()

    def boom(*a, **k):
        raise AssertionError("engine mode never prices off the quote/ratio path")

    def run(now):
        return qe.tick(cfg=cfg, state=state, now=now, quote_fn=boom, ratio_fn=boom, log=NOOP)[2]

    _write_signal_rows(paths, [])
    run(datetime(2026, 9, 15, 9, 50, tzinfo=NY))                     # arms the row cursor
    entry = _row("NOISE_304", "ENTRY", TODAY_ENTRY, 700.0, emitted_at="2026-09-15T09:56:05-04:00",
                 trade_id=TODAY_TID)
    _write_signal_rows(paths, [entry])
    doc = run(datetime(2026, 9, 15, 10, 0, tzinfo=NY))
    assert doc["positions"]["NOISE"]["trade_id"] == TODAY_TID
    assert doc["trade_ids"]["refused_today"] == 0

    stale = _row("NOISE_304", "EXIT", OLD_EXIT, 717.61, emitted_at="2026-09-15T10:29:05-04:00",
                 trade_id=OLD_TID)
    _write_signal_rows(paths, [entry, stale])
    doc = run(NOW)
    assert doc["positions"]["NOISE"]["trade_id"] == TODAY_TID, "still open after the stale EXIT"
    assert doc["trade_ids"]["today"]["exit_id_mismatch"] == 1
    assert doc["trade_ids"]["total"]["exit_id_mismatch"] == 1
    assert doc["trade_ids"]["refused_today"] == 1
    assert doc["trade_ids"]["last"]["row_trade_id"] == OLD_TID
    assert any(e["kind"] == "exit_id_mismatch" for e in doc["events"])
    json.dumps(doc["trade_ids"])            # plain JSON, no nested arrays for Firestore


def test_writer_rows_round_trip_into_the_adapter(_patch_cs_home, tmp_path, monkeypatch):
    """The ids must agree across the fence: rows written by cloud_signal's own diff and
    ledger writer open and close the adapter's lot -- including when the bar cache has
    re-priced the entry by a cent between the ENTRY and the EXIT."""
    paths = _patch_cs_home
    _isolate_adapter(tmp_path, monkeypatch)
    cfg, state, leg_state = _cfg(tmp_path), {"legs": {}}, {}

    def write(events):
        for e in events:            # the writer stamps the real clock; this test's clock is NOW
            e["emitted_at"] = NOW.isoformat()
        cs._append_signals(events, paths)
        got = qe._consume_engine_signals(state, cfg, NOW, log=NOOP)
        _route(state, cfg, *got)
        return got

    trade = {"side": "long", "entry_time": TODAY_ENTRY, "entry_px": 700.0, "shares": 140,
             "exit_time": None, "exit_px": None, "still_open": True}
    write(cs._diff_leg("NOISE_304", [], leg_state, NOW))                  # SEED, arms the cursor
    got = write(cs._diff_leg("NOISE_304", [trade], leg_state, NOW, max_entry_age_sec=3600))
    assert [e["event"] for e in got] == ["ENTRY"]
    assert state["legs"]["NOISE"]["trade_id"] == TODAY_TID == got[0]["trade_id"]

    closed = dict(trade, entry_px=700.01, exit_time="2026-09-15T10:25:00-04:00", exit_px=704.0,
                  still_open=False)
    got = write(cs._diff_leg("NOISE_304", [closed], leg_state, NOW, max_entry_age_sec=3600))
    assert [(e["event"], e["trade_id"]) for e in got] == [("EXIT", TODAY_TID)]
    assert state["legs"] == {} and len(_csv_rows(qe.TRADES_CSV)) == 1
    assert _issues(state) == {}


def test_a_short_read_of_the_ledger_never_moves_the_cursor_back(_patch_cs_home, tmp_path):
    """A read that lands inside another process's in-place rewrite sees fewer rows. Taking
    that count as the cursor would re-consume the rows it hid on the next tick."""
    paths = _patch_cs_home
    cfg = _cfg(tmp_path)
    rows = [_row("NOISE_304", "SEED", "", ""),
            _row("NOISE_304", "ENTRY", TODAY_ENTRY, 700.0, trade_id=TODAY_TID,
                 emitted_at="2026-09-15T09:56:05-04:00"),
            _row("NOISE_304", "EXIT", "2026-09-15T10:25:00-04:00", 704.0, trade_id=TODAY_TID,
                 emitted_at="2026-09-15T10:25:05-04:00")]
    state = {"legs": {}, "engine_cursor": 3}

    _write_signal_rows(paths, rows[:1])                                   # torn: 1 of 3 rows
    assert qe._consume_engine_signals(state, cfg, NOW, log=NOOP) == []
    assert state["engine_cursor"] == 3, "a short read must not drop the cursor"
    _write_signal_rows(paths, rows + [_row("NOISE_304", "ENTRY", "2026-09-15T10:28:00-04:00", 703.0,
                                           trade_id=trade_id.make("NOISE_304", "2026-09-15T10:28:00-04:00", "long"),
                                           emitted_at="2026-09-15T10:29:05-04:00")])
    got = qe._consume_engine_signals(state, cfg, NOW, log=NOOP)
    assert [e["ref_time"] for e in got] == ["2026-09-15T10:28:00-04:00"], "only the genuinely new row"

    # a ledger that STAYS shorter was really replaced: re-armed at its end, nothing replayed
    _write_signal_rows(paths, rows[:2])
    for _ in range(qe.ENGINE_SHORT_READ_TICKS):
        assert qe._consume_engine_signals(state, cfg, NOW, log=NOOP) == []
    assert state["engine_cursor"] == 2
    assert state["events"][-1]["kind"] == "engine_reseed"
