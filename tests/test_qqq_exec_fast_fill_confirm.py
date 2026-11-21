"""Latency item G (2026-11-21): fast fill confirmation between ticks.

_maybe_capture_broker_fills(fast=True) queries a job inside its fast window every
BROKER_FILL_FAST_GAP_SEC (first after BROKER_FILL_FAST_FIRST_DELAY_SEC), still one SDK
call per pass; the tick path (fast=False) keeps its 3 s / 10 s schedule; a 429 note
drops the job out of fast mode; _wait_next_tick drives fill_step only while hot.
"""
from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731


class _Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _setup(monkeypatch, answers, t0=1000.0):
    clock = _Clock(t0)
    monkeypatch.setattr(qe.time, "time", clock)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: object())
    monkeypatch.setattr(qe, "_push_fill_outcome", lambda *a, **k: None)
    calls, finished = [], []

    def fake_query(adapter, coid, account_id=None, log=print, outcome=None):
        calls.append((clock.t, coid))
        return answers.pop(0) if answers else (None, "no fill price yet")

    monkeypatch.setattr(qe, "_query_broker_fill", fake_query)
    monkeypatch.setattr(qe, "_finish_fill_capture",
                        lambda item, px, note, log=print: finished.append((item["signal_id"], px)))
    state = {}
    qe._queue_broker_fill_capture(state, leg="L1", intent="OPEN", signal_id="S1",
                                  account_id="A", shadow_px=100.0, log=NOOP)
    return clock, state, calls, finished


def test_fast_pass_queries_after_short_delay_and_finishes(monkeypatch):
    clock, state, calls, finished = _setup(monkeypatch, [(None, "no fill price yet"), (101.5, None)])
    clock.t += 0.1
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    assert calls == []                       # before the 0.3 s first delay
    clock.t += 0.3
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    assert len(calls) == 1
    clock.t += 0.2
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    assert len(calls) == 1                   # inside the 0.5 s gap: no call
    clock.t += 0.4
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    assert len(calls) == 2
    assert finished == [("S1", 101.5)]
    assert not state["_broker_fill_capture"]


def test_fast_pass_ignores_jobs_past_window(monkeypatch):
    clock, state, calls, _ = _setup(monkeypatch, [])
    clock.t += qe.BROKER_FILL_FAST_WINDOW_SEC + 0.1
    assert not qe._fill_capture_hot(state)
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    assert calls == []


def test_tick_path_schedule_unchanged(monkeypatch):
    clock, state, calls, _ = _setup(monkeypatch, [])
    clock.t += 1.0
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP)
    assert calls == []                       # tick path still waits 3 s
    clock.t += 2.5
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP)
    assert len(calls) == 1
    clock.t += 5.0
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP)
    assert len(calls) == 1                   # 10 s retry gap kept


def test_rate_limit_note_leaves_fast_mode(monkeypatch):
    clock, state, calls, _ = _setup(monkeypatch, [(None, "HTTP 429 Too Many Requests")])
    clock.t += 0.5
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    assert len(calls) == 1
    assert state["_broker_fill_capture"]["L1:OPEN"]["fast_off"] is True
    assert not qe._fill_capture_hot(state)
    clock.t += 1.0
    qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    assert len(calls) == 1


def test_fast_calls_bounded_per_order(monkeypatch):
    clock, state, calls, _ = _setup(monkeypatch, [])
    for _ in range(200):
        clock.t += 0.05
        qe._maybe_capture_broker_fills(state, None, None, True, log=NOOP, fast=True)
    # 5 s window / 0.5 s gap -> at most ~10 fast calls for a job that never fills
    assert len(calls) <= 10


def test_wait_next_tick_runs_fill_step_only_while_hot(monkeypatch):
    monkeypatch.setattr(qe, "TICK_SEC", 1.2)
    monkeypatch.setattr(qe, "_signals_mtime", lambda: None)
    steps = []
    hot = {"v": True}

    def step():
        steps.append(1)
        if len(steps) >= 2:
            hot["v"] = False

    assert qe._wait_next_tick(fill_step=step, fill_hot=lambda: hot["v"]) is False
    assert len(steps) == 2

    steps.clear()
    qe._wait_next_tick(fill_step=step, fill_hot=lambda: False)
    assert steps == []
