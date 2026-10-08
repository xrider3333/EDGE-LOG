"""EOD SETTLE GAVE UP -> a record, a board event and ONE phone push (sweep 2026-10-05, #30).

Before: when the session's last bar never arrived by close + 5 min, _eod_settle_tick wrote one
log line and the day's end-of-day exits moved silently to the next morning with an old
ref_time. Now the engine records state["eod_gave_up"][date] ONCE (a restart inside the window
does not record again), api/qqq_exec.py turns the record into ONE timeline event the WEBULL
PAPER board shows, and ONE ALERTER PER PROBLEM (api/ntfy_push): only tools/webull_freshness.py's
eod_settled check pushes it -- naming the engine's cause -- so a give-up day or an engine-down
day sends exactly one phone push across the three. No network: steps run offline against a
temp bar cache and every sender is a recorder.
"""
import datetime
import importlib.util
import json
import os

import pytest

import api.cloud_signal as cs
from api import ntfy_push
from api import qqq_exec as qe

_spec = importlib.util.spec_from_file_location(
    "eod_settle_helpers",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_cloud_signal_eod_settle.py"))
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)
_fspec = importlib.util.spec_from_file_location(
    "freshness_helpers",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_webull_freshness.py"))
F = importlib.util.module_from_spec(_fspec)
_fspec.loader.exec_module(F)

NOOP = lambda *a, **k: None
DAY = "2026-09-28"


@pytest.fixture
def pushes(monkeypatch):
    out = []

    def rec(msg, title, priority="high", paths=None, log=print):
        out.append({"msg": msg, "title": title, "priority": priority})
        return True
    monkeypatch.setattr(cs, "_engine_push", rec)
    return out


def _run_window(paths, mem, lines, start_sec=30):
    close_dt = H._at(DAY, 16, 0)
    t = close_dt + datetime.timedelta(seconds=start_sec)
    while t <= close_dt + datetime.timedelta(seconds=cs.EOD_SETTLE_WINDOW_SEC):
        cs._eod_settle_tick(t, close_dt, mem, paths=paths, log=lines.append)
        t += datetime.timedelta(seconds=5)


def test_gave_up_records_the_day_once_and_does_not_push(tmp_path, monkeypatch, pushes):
    paths = H._home(tmp_path, H._session_bars(DAY, last_hhmm="15:50"))   # 15:55 never comes
    legs = H._legs()
    H._arm_and_enter(paths, legs)
    H._offline_step(monkeypatch, legs, [])
    lines = []
    _run_window(paths, {}, lines)
    assert sum("GAVE UP" in ln for ln in lines) == 1
    # ONE ALERTER PER PROBLEM: tools/webull_freshness.py pushes "not settled", not the engine
    assert pushes == []
    assert any("last bar 15:55 ET did not arrive" in ln for ln in lines)
    rec = cs._load_state(paths)["eod_gave_up"][DAY]
    assert rec["why"] == "the last bar never arrived"
    at0 = rec["at"]
    # a restart inside the window (fresh in-process memory) gives up again -- not re-recorded
    _run_window(paths, {}, lines, start_sec=240)
    assert pushes == [] and cs._load_state(paths)["eod_gave_up"][DAY]["at"] == at0


def test_a_step_that_keeps_failing_records_its_cause(tmp_path, monkeypatch, pushes):
    paths = H._home(tmp_path, H._session_bars(DAY))

    def boom(**kw):
        raise OSError("REST fetch timed out")
    monkeypatch.setattr(cs, "step", boom)
    lines = []
    _run_window(paths, {}, lines)
    assert pushes == []
    assert any("GAVE UP" in ln and "REST fetch timed out" in ln for ln in lines), \
        "the cause stays in the log"
    assert "REST fetch timed out" in cs._load_state(paths)["eod_gave_up"][DAY]["why"]


def test_a_settled_day_does_not_push(tmp_path, monkeypatch, pushes):
    paths = H._home(tmp_path, H._session_bars(DAY))
    legs = H._legs()
    H._arm_and_enter(paths, legs)
    H._offline_step(monkeypatch, legs, [])
    _run_window(paths, {}, [])
    assert pushes == [] and "eod_gave_up" not in cs._load_state(paths)


def test_engine_push_only_on_the_cloud_box_and_through_the_outbox(tmp_path, monkeypatch):
    paths = cs._paths(home=str(tmp_path / "h"))
    sent = []

    def down(msg, title=None, priority=None, timeout=8, log=None):
        sent.append(priority)
        return False, "URLError: down"
    monkeypatch.setattr(ntfy_push, "push_result", down)
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)
    logs = []
    assert cs._engine_push("m", "T", priority="high", paths=paths, log=logs.append) is None
    assert sent == [] and "not the cloud box" in logs[0]
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    assert cs._engine_push("m", "T", priority="high", paths=paths, log=logs.append) == "queued"
    assert os.path.exists(os.path.join(paths["state_dir"], "ntfy_outbox.json"))


# -- the executor turns the record into one board event -----------------------------------------
def _exec_at(h, m, s=0):
    return datetime.datetime(2026, 9, 28, h, m, s, tzinfo=qe._NY)


def test_executor_logs_one_board_event_for_the_give_up():
    rec = {"eod_gave_up": {DAY: {"at": "x", "why": "the last bar never arrived"}}}
    reads = []

    def read():
        reads.append(1)
        return rec
    state = {}
    assert qe._maybe_note_eod_gave_up(state, _exec_at(16, 3), log=NOOP, read_cs_state=read) is False
    assert reads == [], "the engine gives up at 16:05 -- nothing to read before"
    assert qe._maybe_note_eod_gave_up(state, _exec_at(16, 6), log=NOOP, read_cs_state=read) is True
    ev = [e for e in state["events"] if e["kind"] == "eod_settle_gave_up"]
    assert len(ev) == 1 and "tomorrow morning" in ev[0]["text"]
    for m in range(7, 60):
        qe._maybe_note_eod_gave_up(state, _exec_at(16, m), log=NOOP, read_cs_state=read)
    assert len([e for e in state["events"] if e["kind"] == "eod_settle_gave_up"]) == 1
    assert len(reads) == 1


def test_executor_reads_at_most_once_a_minute_and_stops_after_three_hours():
    reads = []

    def read():
        reads.append(1)
        return {}
    state = {}
    for s in range(0, 120, 5):
        qe._maybe_note_eod_gave_up(state, _exec_at(16, 6) + datetime.timedelta(seconds=s),
                                   log=NOOP, read_cs_state=read)
    assert len(reads) == 2
    state2 = {}
    qe._maybe_note_eod_gave_up(state2, _exec_at(19, 10), log=NOOP, read_cs_state=read)
    assert len(reads) == 2
    assert "events" not in state


def test_engine_down_through_the_window_logs_once_and_does_not_push(monkeypatch):
    """No settle and no give-up record by close + 10 min, though the engine stepped earlier
    today: its thread was down or stuck the whole window -- the executor logs the board event
    and leaves the push to tools/webull_freshness.py (ONE ALERTER PER PROBLEM)."""
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        sent.append((msg, title, priority)))
    cs_state = {"generated_at": "2026-09-28T15:41:10-04:00"}
    state = {}
    for m in range(5, 10):
        assert qe._maybe_note_eod_gave_up(state, _exec_at(16, m, 30), log=NOOP,
                                          read_cs_state=lambda: cs_state) is False
    assert sent == []
    assert qe._maybe_note_eod_gave_up(state, _exec_at(16, 10, 30), log=NOOP,
                                      read_cs_state=lambda: cs_state) is True
    assert sent == [] and "_phone_dedupe" not in state
    assert any("never settled" in e["text"] and "15:41" in e["text"] for e in state["events"])
    for m in range(11, 60):
        qe._maybe_note_eod_gave_up(state, _exec_at(16, m, 30), log=NOOP,
                                   read_cs_state=lambda: cs_state)
    assert sent == []
    assert len([e for e in state["events"] if e["kind"] == "eod_settle_gave_up"]) == 1


def test_a_settled_day_or_an_engine_not_on_this_host_never_pages(monkeypatch):
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: sent.append(a))
    reads = []

    def settled():
        reads.append(1)
        return {"generated_at": "2026-09-28T16:00:30-04:00",
                "eod_settled": {DAY: {"at": "x"}}}
    state = {}
    for m in range(6, 40):
        qe._maybe_note_eod_gave_up(state, _exec_at(16, m), log=NOOP, read_cs_state=settled)
    assert sent == [] and "events" not in state and len(reads) == 1, "settled: stop reading"
    # an engine that never stepped today on this host (generated_at yesterday): not this check's
    state2 = {}
    for m in range(6, 40):
        qe._maybe_note_eod_gave_up(state2, _exec_at(16, m), log=NOOP,
                                   read_cs_state=lambda: {"generated_at": "2026-09-25T15:55:00-04:00"})
    assert sent == [] and "events" not in state2


def test_tick_in_engine_mode_reads_the_real_engine_state(tmp_path, monkeypatch):
    """End to end through tick() (signal_source "engine") and the REAL read of the engine's
    state.json (cs.DEFAULT_PATHS): its eod_gave_up record becomes ONE board event."""
    import json as _json
    paths = cs._paths(home=str(tmp_path / "cs_home"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    os.makedirs(paths["state_dir"], exist_ok=True)
    st = cs._load_state(paths)
    st["eod_gave_up"] = {DAY: {"at": "2026-09-28T16:05:00-04:00",
                               "why": "the last bar never arrived"}}
    cs._write_state(st, paths)
    with open(paths["heartbeat_path"], "w", encoding="utf-8") as f:
        _json.dump({"ts": datetime.datetime.now(qe._NY).isoformat(), "ok": True, "note": "t"}, f)
    out = tmp_path / "exec_out"
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                        ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    monkeypatch.setattr(qe, "_notify", NOOP)
    monkeypatch.setattr(qe, "_maybe_run_reprice", NOOP)
    from api import webull_orders as WO
    wo_cfg = WO.load_config(str(out / "no_such_webull_orders_config.json"))
    wo_cfg.update(mode="OFF", state_path=str(out / "wo_state.json"), kill_file=str(out / "WO_KILL"),
                  arm_live_file=str(out / "WO_ARM_LIVE"), paper_keys_path=str(out / "no_paper.json"),
                  live_keys_path=str(out / "no_live.json"))
    adapter = WO.OrderAdapter(config=wo_cfg, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    cfg = dict(qe.DEFAULT_CONFIG, signal_source="engine", kill_file=str(tmp_path / "KILL"))
    state = qe._default_state()

    def boom(*a, **k):
        raise AssertionError("engine mode never prices off the quote/ratio path")
    for m in (6, 7, 30):
        qe.tick(cfg=cfg, state=state, now=_exec_at(16, m), quote_fn=boom, ratio_fn=boom, log=NOOP)
    ev = [e for e in state.get("events", []) if e["kind"] == "eod_settle_gave_up"]
    assert len(ev) == 1 and "tomorrow morning" in ev[0]["text"]


# -- ONE phone push per give-up day, across the three alerters ---------------------------------
def _freshness_eod_pushes(tmp_path, monkeypatch, cs_extra):
    """tools/webull_freshness.py's real runs from 16:12 ET on DAY with today missing from
    eod_settled and `cs_extra` merged into its cs_state -> the phone pushes it sends (the rest
    of its fixture box is healthy: no other push)."""
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)     # as F's autouse fixture
    h = F.Home(tmp_path / "box", F.et(2026, 9, 28, 16, 12))

    def write_cs():
        with open(h.paths["cs_state"], encoding="utf-8") as f:
            doc = json.load(f)
        doc["eod_settled"] = {}
        doc.update(cs_extra)
        F._wj(h.paths["cs_state"], doc)
    write_cs()
    out = h.run()
    assert "eod_settled" in F.failing(out)
    for m in (14, 16, 30):                    # later runs in the same episode: no repeat push
        h.advance(F.et(2026, 9, 28, 16, m))
        write_cs()
        assert "eod_settled" in F.failing(h.run())
    return h.pushes


def test_a_give_up_day_sends_exactly_one_phone_push(tmp_path, monkeypatch, pushes):
    """The engine gives up (last bar never came), the executor reads its record for the board,
    and the box monitor runs from 16:10 -- one push in all, naming the cause."""
    paths = H._home(tmp_path, H._session_bars(DAY, last_hhmm="15:50"))
    legs = H._legs()
    H._arm_and_enter(paths, legs)
    H._offline_step(monkeypatch, legs, [])
    _run_window(paths, {}, [])
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        sent.append((msg, title, priority)))
    cs_state = cs._load_state(paths)
    state = {}
    for m in range(5, 60):
        qe._maybe_note_eod_gave_up(state, _exec_at(16, m, 30), log=NOOP,
                                   read_cs_state=lambda: cs_state)
    assert len([e for e in state["events"] if e["kind"] == "eod_settle_gave_up"]) == 1
    phone = _freshness_eod_pushes(tmp_path, monkeypatch, {"eod_gave_up": cs_state["eod_gave_up"]})
    total = pushes + sent + phone
    assert len(total) == 1, total
    p = phone[0]
    assert p["title"] == "QQQ book: needs a fix" and p["priority"] == "default"
    assert ntfy_push.lint(p) == []
    assert "last QQQ price bar never came" in p["message"] and "recorded late" in p["message"]


def test_an_engine_down_day_sends_exactly_one_phone_push(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        sent.append((msg, title, priority)))
    cs_state = {"generated_at": "2026-09-28T15:41:10-04:00"}
    state = {}
    for m in range(5, 60):
        qe._maybe_note_eod_gave_up(state, _exec_at(16, m, 30), log=NOOP,
                                   read_cs_state=lambda: cs_state)
    phone = _freshness_eod_pushes(tmp_path, monkeypatch, {})
    assert sent == [] and len(phone) == 1
    assert "did not settle today's close" in phone[0]["message"]
    assert ntfy_push.lint(phone[0]) == []
