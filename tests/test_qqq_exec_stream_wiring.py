"""api/qqq_exec.py's live Webull price stream wiring (2026-09-23, item 3 -- running
api.webull_stream.WebullBarStreamer on a guarded background thread while this process
is SERVING).

Every test here uses a FAKE streamer class installed via
qe._webull_stream_factory -- never the real api.webull_stream.WebullBarStreamer,
which would open a real MQTT connection. tests/conftest.py's autouse
_isolate_qqq_stream fixture already forces this factory to an inert stub for every
test in the whole suite; these tests explicitly override that stub with their OWN
fakes to exercise the real wiring logic (thread lifecycle, exception containment, the
standby-must-not-stream rule).
"""
import threading
import time

import pytest

from api import qqq_exec as qe


def _wait_for(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


@pytest.fixture(autouse=True)
def _clean_stream_state():
    """Belt-and-suspenders alongside conftest's autouse isolation: guarantee every
    test in this file starts and ends with no streamer registered, even though each
    test also stops what it started."""
    qe._qqq_stream_state = {"streamer": None, "starting": False, "stop_requested": False}
    yield
    qe._qqq_stream_state = {"streamer": None, "starting": False, "stop_requested": False}


class _FakeStreamer:
    """Records construction args and start()/stop() calls; never touches a thread or
    the network."""
    def __init__(self, symbols=None, log=print, **kwargs):
        self.symbols = symbols
        self.log = log
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def last_trade(self):
        return {"price": 500.0, "epoch": time.time(), "size": 1, "age": 0.5}

    def is_fresh(self):
        return True

    def health(self):
        return {"connected": True, "fresh": True}


class _SlowFakeStreamer(_FakeStreamer):
    """start() takes a moment -- simulates the real ~20s MQTT connect wait, used to
    exercise the stop-while-connecting race."""
    def start(self):
        time.sleep(0.15)
        self.started = True


class _BoomOnConstructStreamer:
    def __init__(self, *a, **k):
        raise RuntimeError("simulated: could not build the SDK client")


class _BoomOnStartStreamer(_FakeStreamer):
    def start(self):
        raise RuntimeError("simulated: MQTT connect failed")


# ── _start_qqq_stream / _stop_qqq_stream: basic lifecycle ──────────────────────────────

def test_start_qqq_stream_builds_via_factory_and_starts(monkeypatch):
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _FakeStreamer)
    qe._start_qqq_stream({"live_stream_enabled": True}, log=lambda *_: None)
    assert _wait_for(lambda: qe._qqq_stream_instance() is not None)
    inst = qe._qqq_stream_instance()
    assert isinstance(inst, _FakeStreamer)
    assert inst.started is True
    assert inst.symbols == ["QQQ"]
    qe._stop_qqq_stream(log=lambda *_: None)
    assert inst.stopped is True
    assert qe._qqq_stream_instance() is None


def test_start_qqq_stream_default_enabled_when_flag_absent(monkeypatch):
    """DEFAULT_CONFIG['live_stream_enabled'] is True -- an owner config.json that
    predates this feature (no such key at all) must still get the stream."""
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _FakeStreamer)
    qe._start_qqq_stream({}, log=lambda *_: None)
    assert _wait_for(lambda: qe._qqq_stream_instance() is not None)
    qe._stop_qqq_stream(log=lambda *_: None)


def test_start_qqq_stream_disabled_by_config_flag(monkeypatch):
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _FakeStreamer)
    qe._start_qqq_stream({"live_stream_enabled": False}, log=lambda *_: None)
    time.sleep(0.1)
    assert qe._qqq_stream_instance() is None


def test_start_qqq_stream_is_idempotent_while_running(monkeypatch):
    built = []

    def factory():
        return _FakeStreamer

    def counting_factory():
        built.append(1)
        return _FakeStreamer

    monkeypatch.setattr(qe, "_webull_stream_factory", counting_factory)
    qe._start_qqq_stream({}, log=lambda *_: None)
    assert _wait_for(lambda: qe._qqq_stream_instance() is not None)
    qe._start_qqq_stream({}, log=lambda *_: None)   # second call: must be a no-op
    time.sleep(0.05)
    assert len(built) == 1
    qe._stop_qqq_stream(log=lambda *_: None)


def test_stop_qqq_stream_is_safe_when_nothing_started():
    qe._stop_qqq_stream(log=lambda *_: None)   # must not raise
    assert qe._qqq_stream_instance() is None


# ── a stream exception must never reach the tick loop ───────────────────────────────────

def test_start_qqq_stream_start_exception_is_contained(monkeypatch):
    logs = []
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _BoomOnStartStreamer)
    qe._start_qqq_stream({}, log=logs.append)   # must not raise
    time.sleep(0.1)
    assert qe._qqq_stream_instance() is None, "a streamer whose start() raised must never be published"
    assert any("failed to start" in str(m) for m in logs)


def test_start_qqq_stream_construction_exception_is_contained(monkeypatch):
    logs = []
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _BoomOnConstructStreamer)
    qe._start_qqq_stream({}, log=logs.append)
    time.sleep(0.1)
    assert qe._qqq_stream_instance() is None
    assert any("failed to start" in str(m) for m in logs)


def test_start_qqq_stream_factory_lookup_exception_is_contained(monkeypatch):
    def boom_factory():
        raise ImportError("api.webull_stream not importable in this build")
    logs = []
    monkeypatch.setattr(qe, "_webull_stream_factory", boom_factory)
    qe._start_qqq_stream({}, log=logs.append)   # must not raise
    time.sleep(0.05)
    assert qe._qqq_stream_instance() is None
    assert any("failed to start" in str(m) for m in logs)


def test_a_failed_start_does_not_block_a_later_retry(monkeypatch):
    """After a failed start, the 'starting' flag must clear so a LATER call (e.g. the
    next time qqq_exec_thread enters serving) can try again."""
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _BoomOnStartStreamer)
    qe._start_qqq_stream({}, log=lambda *_: None)
    time.sleep(0.1)
    assert qe._qqq_stream_instance() is None
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _FakeStreamer)
    qe._start_qqq_stream({}, log=lambda *_: None)
    assert _wait_for(lambda: qe._qqq_stream_instance() is not None)
    qe._stop_qqq_stream(log=lambda *_: None)


# ── the stop-while-connecting race ───────────────────────────────────────────────────────

def test_stop_while_still_connecting_tears_down_immediately(monkeypatch):
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _SlowFakeStreamer)
    qe._start_qqq_stream({}, log=lambda *_: None)
    time.sleep(0.02)   # still inside the simulated slow .start()
    assert qe._qqq_stream_instance() is None, "not published yet -- still connecting"
    qe._stop_qqq_stream(log=lambda *_: None)   # stand-down arrives mid-connect
    time.sleep(0.3)   # let the slow .start() finish
    assert qe._qqq_stream_instance() is None, (
        "a streamer that finished connecting AFTER stand-down must never be handed to "
        "the rest of the process")


# ── qqq_exec_thread integration: standby never streams, serving starts/stops it ────────

def _thread_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec_out"
    for name, path in {"OUT_DIR": out, "CONFIG_PATH": out / "config.json",
                       "STATE_PATH": out / "state.json", "ORDERS_CSV": out / "orders.csv",
                       "TRADES_CSV": out / "trades.csv",
                       "BROKER_ORDERS_CSV": out / "broker_orders.csv",
                       "SERVING_LOCK": out / "SERVING.lock"}.items():
        monkeypatch.setattr(qe, name, str(path))
    monkeypatch.setattr(qe, "_reconcile_broker_at_boot", lambda log=print: None)
    monkeypatch.setattr(qe, "publish_async", lambda *a, **k: None)
    monkeypatch.setattr(qe, "TICK_SEC", 0.02)
    # Item B (2026-09-25): qqq_exec_thread now only starts the stream INSIDE
    # _stream_should_run's market-hours window (see _qqq_stream_window_step), which
    # depends on the real wall clock at whatever moment this test suite happens to
    # run. These lifecycle/wiring tests care about thread start/stop/exception
    # handling, not the window decision itself (that's tests/test_qqq_exec_stream_window.py's
    # job) -- force it on so they pass at any time of day.
    monkeypatch.setattr(qe, "_stream_should_run", lambda now_et: True)


def _fake_doc(positions=None):
    return {"mode": "SHADOW", "signal_source": "engine", "updated_at": "x",
           "feed_stale": False, "px_feed_stale": False, "breaker_tripped": False,
           "kill": False, "positions": positions or {},
           "today": {"orders": [], "trades": [], "realized_pnl": 0.0, "unrealized_pnl": 0.0},
           "events": [], "broker": {"effective_mode": "OFF"},
           "lease": {"host_id": "h", "leased_at": 1.0}}


def test_standby_host_never_starts_the_stream(tmp_path, monkeypatch):
    """A process that never claims the cross-host lease must never reach the point
    where the live stream could start -- 'the standby host must NOT stream' (item 3),
    since a second live MQTT session on the same Webull key can kick the first."""
    _thread_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_claim_lease",
                        lambda db, uid, log=print: (False, "another host holds a fresh lease", None))
    monkeypatch.setattr(qe, "_note_standby", lambda reason, log=print: None)
    started = []
    monkeypatch.setattr(qe, "_start_qqq_stream", lambda cfg, log=print: started.append(1))

    qe.qqq_exec_thread(object(), ["uid-standby"], stop=threading.Event(), log=lambda *_: None)

    assert started == [], "a process refused the lease must never attempt to start the live stream"
    assert qe._qqq_stream_instance() is None


def test_serving_process_starts_and_stops_the_stream_around_the_loop(tmp_path, monkeypatch):
    _thread_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "tick", lambda **kw: (kw.get("cfg") or {}, kw.get("state") or {},
                                                  _fake_doc()))
    calls = {"start": 0, "stop": 0}
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(qe, "_stop_qqq_stream",
                        lambda log=print: calls.__setitem__("stop", calls["stop"] + 1))

    stop = threading.Event()
    t = threading.Thread(target=qe.qqq_exec_thread, args=(None, ["uid1"]),
                        kwargs={"stop": stop, "log": lambda *_: None}, daemon=True)
    t.start()
    assert _wait_for(lambda: calls["start"] == 1)
    stop.set()
    t.join(timeout=3)
    assert not t.is_alive()
    assert calls["start"] == 1
    assert calls["stop"] == 1


def test_serving_process_stops_the_stream_even_when_tick_keeps_raising(tmp_path, monkeypatch):
    """qqq_exec_thread's per-tick try/except swallows a tick() failure and keeps
    looping -- the stream must still be torn down once the loop is finally told to
    stop, not leaked because the loop body kept erroring."""
    _thread_paths(tmp_path, monkeypatch)

    def boom_tick(**kw):
        raise RuntimeError("simulated tick failure")
    monkeypatch.setattr(qe, "tick", boom_tick)
    calls = {"start": 0, "stop": 0}
    monkeypatch.setattr(qe, "_start_qqq_stream",
                        lambda cfg, log=print: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(qe, "_stop_qqq_stream",
                        lambda log=print: calls.__setitem__("stop", calls["stop"] + 1))

    stop = threading.Event()
    t = threading.Thread(target=qe.qqq_exec_thread, args=(None, ["uid1"]),
                        kwargs={"stop": stop, "log": lambda *_: None}, daemon=True)
    t.start()
    assert _wait_for(lambda: calls["start"] == 1)
    time.sleep(0.1)   # let a few failing ticks go by
    stop.set()
    t.join(timeout=3)
    assert not t.is_alive()
    assert calls["stop"] == 1


def test_real_fake_streamer_survives_a_full_serve_and_stand_down_cycle(tmp_path, monkeypatch):
    """End-to-end with the REAL _start_qqq_stream/_stop_qqq_stream (not stubbed) and a
    fake streamer class -- proves the whole chain (qqq_exec_thread -> _start_qqq_stream
    -> factory -> background thread -> instance registered -> loop stop -> teardown)
    without ever touching api.webull_stream or the network."""
    _thread_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "tick", lambda **kw: (kw.get("cfg") or {}, kw.get("state") or {},
                                                  _fake_doc()))
    monkeypatch.setattr(qe, "_webull_stream_factory", lambda: _FakeStreamer)

    stop = threading.Event()
    t = threading.Thread(target=qe.qqq_exec_thread, args=(None, ["uid1"]),
                        kwargs={"stop": stop, "log": lambda *_: None}, daemon=True)
    t.start()
    assert _wait_for(lambda: qe._qqq_stream_instance() is not None)
    inst = qe._qqq_stream_instance()
    assert inst.started is True
    stop.set()
    t.join(timeout=3)
    assert not t.is_alive()
    assert qe._qqq_stream_instance() is None
    assert inst.stopped is True
