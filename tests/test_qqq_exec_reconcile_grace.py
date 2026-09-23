"""The POST-ORDER GRACE in api/qqq_exec.py's _maybe_run_broker_reconcile (2026-09-21).

WHY. Webull paper's POSITIONS lag a FILL by more than one 5 s tick. The reconcile that ran on
the tick after a send read the pre-fill position, called it a mismatch, and halted new broker
entries on EVERY leg until the 5-minute periodic check cleared it. That happened twice live on
2026-09-21 (broker 20 vs sent 10 at 09:31, broker 10 vs sent 0 at 09:42) and both were false.
Owner: "wait 30 seconds and look again before panicking."

These pin the new WHEN, with time controlled exactly. What reconcile() compares and how it
halts is unchanged and covered elsewhere (tests/test_webull_reconcile_fail_closed.py).
"""
import json
import time as real_time
from unittest.mock import MagicMock

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731


class _FakeAdapter:
    """Only what _maybe_run_broker_reconcile calls -- same shape as the fake in
    tests/test_qqq_exec_broker_reconcile_schedule.py, kept local so no test imports
    from another test module."""
    def __init__(self, mode="PAPER", reconcile_fn=None):
        self._mode = mode
        self._reconcile_fn = reconcile_fn or (lambda: {"ok": True, "mismatches": [],
                                                        "checked_at": real_time.time()})
        self.reconcile_calls = 0

    def effective_mode(self):
        return self._mode, "test"

    def reconcile(self):
        self.reconcile_calls += 1
        return self._reconcile_fn()

    def fail_closed(self, reason):
        return {"ok": False, "error": reason, "checked_at": real_time.time()}

T0 = 200000.0


def _clock(monkeypatch, t):
    monkeypatch.setattr(qe.time, "time", lambda: t)


def _after_send(sent_at):
    """The state _mirror_to_broker leaves behind after a real PAPER send."""
    return {"_reconcile_due": True, "_last_broker_send_at": sent_at,
            "_last_broker_reconcile_at": sent_at - 10.0, "events": []}


def test_no_look_on_the_very_next_tick(monkeypatch):
    """The exact live failure: the tick 5 s after the sale must not check yet."""
    adapter = _FakeAdapter(mode="PAPER")
    state = _after_send(T0)
    _clock(monkeypatch, T0 + 5.0)
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 0
    assert state["_reconcile_due"] is True, "still owed -- deferred, not dropped"


def test_the_look_happens_once_the_grace_has_passed(monkeypatch):
    adapter = _FakeAdapter(mode="PAPER")
    state = _after_send(T0)
    _clock(monkeypatch, T0 + qe.BROKER_RECONCILE_POST_ORDER_GRACE_SEC + 0.5)
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 1
    assert state["_reconcile_due"] is False


def test_a_slow_fill_never_halts_the_book(monkeypatch):
    """End to end over the ticks of a real sale: the broker still shows the OLD position for
    the first 12 s, then the new one. The old code halted at +5 s; now nothing halts, because
    the only look lands after the fill has settled."""
    sent_at = T0

    def broker_view():
        settled = qe.time.time() - sent_at >= 12.0
        return ({"ok": True, "mismatches": [], "checked_at": real_time.time()} if settled else
                {"ok": False, "mismatches": [{"symbol": "QQQ", "broker": 10.0, "shadow_sent": 0.0}],
                 "checked_at": real_time.time()})

    adapter = _FakeAdapter(mode="PAPER", reconcile_fn=broker_view)
    state = _after_send(sent_at)
    for dt in range(5, 60, 5):                      # every 5 s tick for a minute
        _clock(monkeypatch, sent_at + dt)
        qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 1, "one look, after the grace"
    assert not [e for e in state["events"] if e.get("kind") == "broker_reconcile_halt"]


def test_a_real_mismatch_still_halts_after_the_grace(monkeypatch):
    """The grace delays the panic; it must not remove it."""
    adapter = _FakeAdapter(mode="PAPER", reconcile_fn=lambda: {
        "ok": False, "mismatches": [{"symbol": "QQQ", "broker": 10.0, "shadow_sent": 0.0}],
        "checked_at": real_time.time()})
    state = _after_send(T0)
    _clock(monkeypatch, T0 + 31.0)
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 1
    assert [e for e in state["events"] if e.get("kind") == "broker_reconcile_halt"]


def test_the_routine_check_is_held_off_inside_the_grace_too(monkeypatch):
    """A periodic check landing mid-fill would false-halt the same way, so it waits as well --
    even when its own 5-minute interval has long elapsed."""
    adapter = _FakeAdapter(mode="PAPER")
    state = _after_send(T0)
    state["_last_broker_reconcile_at"] = T0 - 3600.0     # periodic is overdue
    _clock(monkeypatch, T0 + 10.0)
    qe._maybe_run_broker_reconcile(state, {"broker_reconcile_interval_min": 5}, adapter, None,
                                   active=True, log=NOOP)
    assert adapter.reconcile_calls == 0


def test_a_burst_of_orders_is_checked_once_after_the_last_one(monkeypatch):
    """ENGU-Q at +0 s and NOISE at +20 s: the look waits for 30 s after the SECOND send."""
    adapter = _FakeAdapter(mode="PAPER")
    state = _after_send(T0)
    state["_last_broker_send_at"] = T0 + 20.0            # what the second send writes
    _clock(monkeypatch, T0 + 35.0)                        # 35 s after the first, 15 after the last
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 0
    _clock(monkeypatch, T0 + 51.0)
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 1


def test_the_grace_is_owner_configurable(monkeypatch):
    """A config.json override moves the wait. Like every other throttle/interval knob here it
    goes through _cfg_num, which ignores a zero, negative or garbled value and keeps the
    default -- so a typo in config.json can never switch the grace off."""
    cfg = {"broker_reconcile_post_order_grace_sec": 10}
    adapter = _FakeAdapter(mode="PAPER")
    state = _after_send(T0)
    _clock(monkeypatch, T0 + 5.0)
    qe._maybe_run_broker_reconcile(state, cfg, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 0
    _clock(monkeypatch, T0 + 11.0)
    qe._maybe_run_broker_reconcile(state, cfg, adapter, None, active=True, log=NOOP)
    assert adapter.reconcile_calls == 1

    for junk in (0, -5, "thirty", None):
        adapter = _FakeAdapter(mode="PAPER")
        state = _after_send(T0)
        _clock(monkeypatch, T0 + 11.0)
        qe._maybe_run_broker_reconcile(state, {"broker_reconcile_post_order_grace_sec": junk},
                                       adapter, None, active=True, log=NOOP)
        assert adapter.reconcile_calls == 0, f"{junk!r} must fall back to the 30 s default"


def test_mirror_to_broker_records_when_it_sent(tmp_path, monkeypatch):
    """The scheduler can only wait from the send if the send is timestamped."""
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    cfg = WO.load_config("__no_such_file__")
    cfg.update(mode="PAPER", state_path=str(tmp_path / "wo_state.json"),
               paper_keys_path=str(tmp_path / "paper_keys.json"),
               live_keys_path=str(tmp_path / "live_keys.json"),
               arm_live_file=str(tmp_path / "ARM_LIVE"), kill_file=str(tmp_path / "WO_KILL"))
    cfg["rails"].update(session_start="00:00", session_end="23:59")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    monkeypatch.setattr(adapter, "_build_client", lambda mode: client)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _clock(monkeypatch, T0)
    state = {}
    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=700.0,
                         intent="OPEN", trade_id="NOISE_304-20260921T140000Z-L", log=NOOP)
    assert state["_reconcile_due"] is True
    assert state["_last_broker_send_at"] == T0
