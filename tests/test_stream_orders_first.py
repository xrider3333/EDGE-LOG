"""ORDERS FIRST (2026-11-18): run_stream_aware_step runs step() before the diagnostic stream
extras when the owner switch is off, and keeps the old order when it is on or unknown.
The full equivalence replay is tools/qqq_orders_first_replay.py."""
import datetime as _dt

from api import cloud_signal as cs
from api import cloud_signal_stream as css


def _wire(monkeypatch, flag, calls):
    monkeypatch.setattr(cs, "bar_cache_refusal", lambda tf, paths: False)
    monkeypatch.setattr(css, "load_stream_config",
                        lambda paths, log=print: {"bar_close_from_stream": flag})
    monkeypatch.setattr(css, "in_handoff_window", lambda now: True)
    monkeypatch.setattr(cs, "_load_state", lambda paths: {"legs": {"ORB_R6": {"x": 1}}})

    def fake_step(**k):
        calls.append("step")
        return ["ev"]

    def fake_handoff(now, legs, paths, cfg, log, state=None):
        calls.append(("handoff", None if state is None else dict(state)))

    monkeypatch.setattr(cs, "step", fake_step)
    monkeypatch.setattr(css, "_handle_handoff_window", fake_handoff)
    monkeypatch.setattr(css, "_resolve_pending_against_rest",
                        lambda *a, **k: calls.append("resolve"))


LEGS = {"ORB_R6": {"timeframe": "5m"}}
NOW = _dt.datetime(2026, 11, 17, 10, 30, 1, tzinfo=cs._zi(cs.TZ))


def test_switch_off_step_runs_first_and_extras_get_pre_step_snapshot(monkeypatch):
    calls = []
    _wire(monkeypatch, False, calls)
    out = css.run_stream_aware_step(now=NOW, legs=LEGS, paths={"home": "x"}, fetch=False,
                                    log=lambda *a: None)
    assert out == ["ev"]
    assert calls[0] == "step"
    assert calls[1] == ("handoff", {"legs": {"ORB_R6": {"x": 1}}})
    assert calls[2] == "resolve"


def test_switch_on_keeps_extras_before_step(monkeypatch):
    calls = []
    _wire(monkeypatch, True, calls)
    css.run_stream_aware_step(now=NOW, legs=LEGS, paths={"home": "x"}, fetch=False,
                              log=lambda *a: None)
    assert calls == [("handoff", None), "resolve", "step"]


def test_unreadable_switch_keeps_old_order(monkeypatch):
    calls = []
    _wire(monkeypatch, False, calls)
    monkeypatch.setattr(cs, "bar_cache_refusal", lambda tf, paths: True)
    css.run_stream_aware_step(now=NOW, legs=LEGS, paths={"home": "x"}, fetch=False,
                              log=lambda *a: None)
    assert calls == ["step"]   # refused cache: extras skip entirely, step still runs

def test_snapshot_passed_with_switch_flipped_on_never_commits(monkeypatch):
    """VERIFIER 11-18: switch read OFF by the caller, flipped ON before the hand-off reads
    it again -> the pre-step snapshot must never be written back nor rows appended."""
    import time
    writes = []
    epoch = int(time.time()) // 300 * 300
    monkeypatch.setattr(css, "read_closed_bar_handoff", lambda tf, home=None: {
        "time": epoch, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})
    monkeypatch.setattr(css, "stream_bar_is_usable", lambda p, now: (True, ""))
    monkeypatch.setattr(cs, "historical_bars", lambda tf, paths: None)
    monkeypatch.setattr(css, "_augment_with_stream_bar", lambda df, bar: None)
    monkeypatch.setattr(css, "already_shadowed", lambda *a: False)
    monkeypatch.setattr(css, "_daily_cache_may_still_change", lambda *a: False)
    monkeypatch.setattr(css, "_is_disagreement_tripped", lambda *a: False)
    monkeypatch.setattr(css, "_dry_run_decision", lambda *a, **k: (
        [{"event": "ENTRY", "leg": "ORB_R6"}], {"trades": {}}))
    monkeypatch.setattr(css, "record_shadow_decision", lambda *a, **k: None)
    monkeypatch.setattr(cs, "_append_signals", lambda ev, paths: writes.append("signals"))
    monkeypatch.setattr(cs, "_write_state", lambda st, paths: writes.append("state"))
    snap = {"legs": {"ORB_R6": {"trades": {}}}}
    css._handle_handoff_window(NOW, LEGS, {"home": None},
                               {"bar_close_from_stream": True}, lambda *a: None, state=snap)
    assert writes == []
