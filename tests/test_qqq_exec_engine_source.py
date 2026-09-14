"""api/qqq_exec.py, signal_source == "engine" -- the QQQ shadow book taking its
entries/exits from api/cloud_signal.py's own signal ledger instead of NinjaTrader's
fills.csv (2026-09-13, "move QQQ shadow off NinjaTrader").

Coverage:
  1. The NOISE leg resolves to the api/paper.py PAPER_LEGS run #304 definition, not
     the retired #243 SBS_V90 config.
  2. Consuming api.cloud_signal's signals.csv is idempotent across a simulated adapter
     restart: the same rows are never re-entered/re-exited twice.
  3. First-ever activation of engine mode absorbs any PRE-EXISTING signal rows without
     acting on them (cloud_signal's own SEED rule, mirrored on this side of the fence).
  4. A signal consumed long after it was emitted (this adapter was "down") is never
     entered.
  5. Engine mode never opens fills.csv, addon_heartbeat.json, or the NQ 10s export --
     asserted by patching `open` and failing the test if any of those paths are touched.
"""
import builtins
import csv
import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import qqq_exec as qe                 # noqa: E402
from api import cloud_signal as cs              # noqa: E402
from api import paper                           # noqa: E402


# ── 1. leg definition -----------------------------------------------------------------
def test_noise_leg_resolves_to_run_304():
    """api/cloud_signal.py's NOISE leg must be exactly api.paper's own run #304
    definition (NOISE_304_NBHD on NOISE_1_1_NBHD.py) -- not re-derived, not left on the
    retired #243 SBS_V90 config."""
    assert "NOISE_304" in cs.CROWN_LEGS
    assert "NOISE_SBS_V90" not in cs.CROWN_LEGS, "the stale #243 key must be gone, not just added-alongside"
    leg = cs.CROWN_LEGS["NOISE_304"]
    assert leg["strategy"] == "NOISE_1_1_NBHD.py"
    assert leg["params"] == paper.NOISE_304_NBHD
    assert qe.ENGINE_LEG_MAP.get("NOISE_304") == "NOISE", (
        "qqq_exec's own leg map must track the cloud_signal rename")


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


def _row(leg, event, ref_time, ref_price, side="long", emitted_at=None, bar_source="webull"):
    return {"emitted_at": emitted_at or ref_time, "leg": leg, "event": event, "side": side,
           "ref_time": ref_time, "ref_price": ref_price, "shares": 5, "reason": "",
           "bar_source": bar_source}


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
