"""api/qqq_exec.py's broker reconcile SCHEDULING (2026-09-14, FIX 2) --
_maybe_run_broker_reconcile / _reconcile_with_timeout / _run_broker_housekeeping, and
the state["_reconcile_due"] flag _mirror_to_broker sets.

api.webull_orders.OrderAdapter.reconcile() itself (what gets compared, fail-closed on
a read failure, halt recovery) is covered by tests/test_webull_reconcile_fail_closed.py
-- this file is about WHEN it gets called: at boot (tests/test_qqq_exec_broker_mirror.py
already covers _reconcile_broker_at_boot), immediately after any broker order this tick
attempted to send, and otherwise at most once per broker_reconcile_interval_min while
the tick loop is in its active market window -- never on the bare 5s tick cadence, and
never at all in OFF mode.

No real Webull/Firestore network anywhere -- reconcile() itself is replaced with a
small fake per test.
"""
import json
import time as real_time
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731


class _FakeAdapter:
    """Stands in for a real OrderAdapter -- only the methods
    _maybe_run_broker_reconcile/_sync_broker_daily_pnl/_run_broker_housekeeping
    actually call."""
    def __init__(self, mode="PAPER", reconcile_fn=None):
        self._mode = mode
        self._reconcile_fn = reconcile_fn or (lambda: {"ok": True, "mismatches": [],
                                                        "checked_at": real_time.time()})
        self.reconcile_calls = 0
        self.fail_closed_calls = []
        self._state = {"open_legs": []}

    def effective_mode(self):
        return self._mode, "test"

    def reconcile(self):
        self.reconcile_calls += 1
        return self._reconcile_fn()

    def fail_closed(self, reason):
        self.fail_closed_calls.append(reason)
        result = {"ok": False, "error": reason, "checked_at": real_time.time()}
        return result

    def status(self):
        return {"open_legs": []}

    def reset_daily_pnl(self):
        pass

    def update_daily_pnl(self, delta):
        pass


# ── OFF mode: never touches reconcile() at all ──────────────────────────────────────

def test_off_mode_never_calls_reconcile():
    adapter = _FakeAdapter(mode="OFF")
    state = {"_reconcile_due": True}   # even if "due" -- OFF must still no-op
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 0


# ── post-order: runs immediately, clears the flag ───────────────────────────────────

def test_reconcile_due_flag_forces_an_immediate_run_regardless_of_interval_or_active():
    adapter = _FakeAdapter(mode="PAPER")
    state = {"_reconcile_due": True, "_last_broker_reconcile_at": real_time.time()}
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=False, log=NOOP)
    assert adapter.reconcile_calls == 1
    assert state["_reconcile_due"] is False


def test_mirror_to_broker_sets_reconcile_due_on_a_real_paper_send(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    mock_client = MagicMock()
    mock_client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
    mock_client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    monkeypatch.setattr(adapter, "_build_client", lambda mode: mock_client)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}}
    assert not state.get("_reconcile_due")
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    assert state["_reconcile_due"] is True


def test_mirror_to_broker_off_mode_never_sets_reconcile_due(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    cfg = WO.load_config("__no_such_file__")
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    assert not state.get("_reconcile_due")


# ── periodic: respects the interval, only while active ──────────────────────────────

def test_periodic_reconcile_waits_for_the_interval(monkeypatch):
    adapter = _FakeAdapter(mode="PAPER")
    now = 100000.0
    monkeypatch.setattr(qe.time, "time", lambda: now)
    state = {"_last_broker_reconcile_at": now - 60.0}   # only 60s of a 5-min interval
    cfg = {"broker_reconcile_interval_min": 5}
    qe._maybe_run_broker_reconcile(state, cfg, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 0


def test_periodic_reconcile_fires_once_interval_elapses(monkeypatch):
    adapter = _FakeAdapter(mode="PAPER")
    now = 100000.0
    monkeypatch.setattr(qe.time, "time", lambda: now)
    state = {"_last_broker_reconcile_at": now - 301.0}
    cfg = {"broker_reconcile_interval_min": 5}
    qe._maybe_run_broker_reconcile(state, cfg, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 1
    assert state["_last_broker_reconcile_at"] == now


def test_periodic_reconcile_never_fires_when_not_active(monkeypatch):
    """Outside the tick loop's own market window, the periodic cadence must not run
    even if the interval has long since elapsed -- boot and post-order still cover the
    off-hours cases that matter (a KILL-triggered flatten can happen any time)."""
    adapter = _FakeAdapter(mode="PAPER")
    now = 100000.0
    monkeypatch.setattr(qe.time, "time", lambda: now)
    state = {"_last_broker_reconcile_at": 0.0}
    cfg = {"broker_reconcile_interval_min": 5}
    qe._maybe_run_broker_reconcile(state, cfg, adapter, None, active=False, log=NOOP)
    assert adapter.reconcile_calls == 0


def test_periodic_cadence_respects_cfg_override(monkeypatch):
    adapter = _FakeAdapter(mode="PAPER")
    now = 100000.0
    monkeypatch.setattr(qe.time, "time", lambda: now)
    state = {"_last_broker_reconcile_at": now - 61.0}
    cfg = {"broker_reconcile_interval_min": 1}   # 60s instead of the 5-min default
    qe._maybe_run_broker_reconcile(state, cfg, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 1


# ── mismatch/failure logging + event ────────────────────────────────────────────────

def test_reconcile_failure_logs_a_halt_event():
    adapter = _FakeAdapter(mode="PAPER",
                           reconcile_fn=lambda: {"ok": False, "error": "can't read positions at Webull: boom"})
    state = {"_reconcile_due": True, "events": []}
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert state["events"], "a reconcile read failure must be recorded on the event timeline"
    assert "halted" in state["events"][-1]["text"]


# ── hard timeout wrapper -- never hangs the tick loop ───────────────────────────────

def test_reconcile_with_timeout_fails_closed_on_a_hang(monkeypatch):
    monkeypatch.setattr(qe, "RECONCILE_HARD_TIMEOUT_SEC", 0.1)

    class _SlowAdapter(_FakeAdapter):
        def reconcile(self):
            real_time.sleep(2.0)   # far longer than the patched 0.1s timeout
            return {"ok": True}

    adapter = _SlowAdapter(mode="PAPER")
    start = real_time.time()
    result = qe._reconcile_with_timeout(adapter, log=NOOP)
    elapsed = real_time.time() - start
    assert elapsed < 1.5, "the wrapper must give up at RECONCILE_HARD_TIMEOUT_SEC, not wait for the call"
    assert result["ok"] is False
    assert "can't read positions at Webull" in result["error"]
    assert adapter.fail_closed_calls, "a timeout must fail closed via adapter.fail_closed()"


def test_reconcile_with_timeout_passes_through_a_normal_result():
    adapter = _FakeAdapter(mode="PAPER", reconcile_fn=lambda: {"ok": True, "mismatches": []})
    result = qe._reconcile_with_timeout(adapter, log=NOOP)
    assert result == {"ok": True, "mismatches": []}
    assert not adapter.fail_closed_calls


def test_reconcile_with_timeout_fails_closed_on_an_unexpected_crash():
    def boom():
        raise RuntimeError("unexpected bug")
    adapter = _FakeAdapter(mode="PAPER", reconcile_fn=boom)
    result = qe._reconcile_with_timeout(adapter, log=NOOP)
    assert result["ok"] is False
    assert adapter.fail_closed_calls


# ── _run_broker_housekeeping: one adapter fetch feeds both sub-systems ──────────────

def test_run_broker_housekeeping_uses_exactly_one_adapter_fetch(monkeypatch):
    fetch_calls = []

    def fetch(log=print):
        fetch_calls.append(1)
        return _FakeAdapter(mode="OFF")   # OFF -- both sub-calls should no-op cleanly
    monkeypatch.setattr(qe, "_get_broker_adapter", fetch)

    state = {}
    qe._run_broker_housekeeping(state, {}, qe._now_et(), active=True, log=NOOP)
    assert len(fetch_calls) == 1


def test_run_broker_housekeeping_never_raises_when_adapter_unavailable(monkeypatch):
    def boom(log=print):
        raise RuntimeError("adapter build failed")
    monkeypatch.setattr(qe, "_get_broker_adapter", boom)
    qe._run_broker_housekeeping({}, {}, qe._now_et(), active=True, log=NOOP)  # must not raise
