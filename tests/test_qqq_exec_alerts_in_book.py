"""ALERTS IN BOOK (2026-09-26, continuing EXIT SAFETY): four more phone-alert/safety
gaps in api/qqq_exec.py, same "no exit fails silently" theme:
  1. a signal-engine stall (cloud_signal's own heartbeat gone stale) while the book
     holds an open lot pushes one high-priority alert per stall EPISODE, plus one
     recovery push when the heartbeat comes back -- _check_feed_engine.
  2. a broker reconcile MISMATCH or READ FAILURE pushes the first occurrence of the
     calendar day at once, then at most once every 30 minutes while it persists --
     _maybe_notify_reconcile_halt, called from _maybe_run_broker_reconcile's own
     failure branch.
  3. three or more CONSECUTIVE failed ticks of qqq_exec_thread's own while loop push
     one high-priority alert per episode, never once per failure after that --
     _note_tick_result.
  4. adapter.place_stock_order() runs on its own worker thread bounded to
     BROKER_SEND_HARD_TIMEOUT_SEC (40s) so a hung SDK call can never freeze the tick
     loop -- _place_stock_order_with_timeout. On timeout the outcome is UNKNOWN, never
     "not placed": sent=True, ok=False, outcome="UNKNOWN", the client_order_id computed
     the same deterministic way place_stock_order itself would have, and a dedicated
     always-fires phone push (_alert_broker_send_unknown, never throttled the way an
     ordinary "not ok" OPEN is). An UNKNOWN OPEN is never auto-resent (the existing
     _queue_broker_resend only ever queues an OPEN for why="halt"/"duplicate"); an
     UNKNOWN CLOSE joins the existing close_retry/needs_verify path unchanged, so it is
     only retried once _order_known_at_broker confirms the previous attempt never
     landed.

REVIEW FIXES (2026-09-26, review of item 4 above -- see _inflight_send's own module
comment in api/qqq_exec.py for the full write-up):
  * major #1: a still-hung send keeps holding OrderAdapter._lock in the background, so
    the tick thread's OWN later update_daily_pnl/reset_daily_pnl/reconcile calls
    (_run_broker_housekeeping) would block on that same lock and freeze the whole tick
    loop one tick later -- housekeeping now skips itself while a send is still in
    flight, resuming once it resolves.
  * major #2: the shared single-worker executor meant a second send queued behind a
    still-hung first one, only really reaching Webull later against stale state --
    _place_stock_order_with_timeout now refuses to submit at all while a previous send
    has not resolved, returning a definite mode="BLOCKED"/sent=False record instead.
  * minor: _note_tick_result now runs before save_state in qqq_exec_thread, so a
    recovered tick's streak/alerted reset is persisted in the SAME save as the
    recovery, not one save later.

HARNESS: same conventions as tests/test_qqq_exec_exit_safety.py and
tests/test_qqq_exec_broker_reconcile_schedule.py (helpers copied LOCALLY, not
imported). No real Firestore/Webull/network call anywhere -- the SDK client is always a
MagicMock or a tiny local fake, and tests/conftest.py's autouse fixtures already
isolate api.qqq_exec._ORDER_ADAPTER / the live-stream factory / EDGELOG_HOME for every
test here even when a test does not build its own adapter.
"""
import csv
import datetime
import json
import os
import threading
import time as real_time
from unittest.mock import MagicMock

from api import cloud_signal as cs
from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731

ORB_TRADE_ID = "ORB_257-20260926T093100Z-L"


# ── harness (copied from tests/test_qqq_exec_exit_safety.py) ───────────────────────

def _broker_cfg(tmp_path, mode="PAPER"):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _mock_client():
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _paper_adapter(tmp_path, monkeypatch, mode="PAPER"):
    cfg = _broker_cfg(tmp_path, mode=mode)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    client = _mock_client()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: client)
    return adapter, client


def _patch_qqq_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    monkeypatch.setattr(qe, "SERVING_LOCK", str(out / "SERVING.lock"))
    return out


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _seed_sent(adapter, leg, qty, account_id="ACCT1"):
    adapter._state.setdefault("broker_sent_positions", {})[leg] = {
        "symbol": "QQQ", "qty": qty, "account_id": account_id}
    adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
    if qty:
        adapter._state.setdefault("open_legs", {})[leg] = True


def _capture_notify(monkeypatch):
    pushed = []
    monkeypatch.setattr(
        qe, "_notify",
        lambda msg, title, log=print, priority=None: pushed.append((title, msg, priority)))
    return pushed


# ═══════════════ item 1: signal-engine stall + open lot -> phone push ══════════════

def _fake_cs(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=str(tmp_path / "cs_home")))
    monkeypatch.setattr(qe, "_cs_module", lambda: cs)
    return cs


def _write_heartbeat(cs_mod, age_sec, ok=True):
    path = cs_mod.DEFAULT_PATHS["heartbeat_path"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_sec)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"ts": ts.isoformat(), "ok": ok}, f)


def test_signal_stall_with_open_lot_pushes_high_priority_once(tmp_path, monkeypatch):
    cs_mod = _fake_cs(tmp_path, monkeypatch)
    _write_heartbeat(cs_mod, age_sec=200)   # well past ENGINE_HEARTBEAT_STALE_SEC (90s)
    pushed = _capture_notify(monkeypatch)
    state = {"legs": {"NOISE": {"shares_remaining": 10}}, "events": []}

    stale = qe._check_feed_engine(state, log=NOOP)

    assert stale is True
    assert len(pushed) == 1
    title, msg, priority = pushed[0]
    assert priority == "high"
    assert "NOISE" in msg
    assert "STALLED" in msg
    assert state["_signal_stall_alerted"] is True
    # item 6 (2026-09-26 minor review): must say SIGNAL-DRIVEN exits are blocked, and
    # that the rail-driven closes still work -- the old wording ("exits are blocked")
    # falsely implied the EOD flatten/KILL/breaker could not close the lot either.
    assert "signal-driven exits are blocked" in msg
    assert "end-of-day flatten, KILL and breaker still work" in msg

    # a second stale tick must not page again -- one push per episode
    qe._check_feed_engine(state, log=NOOP)
    assert len(pushed) == 1


def test_signal_stall_with_no_open_lot_never_pages(tmp_path, monkeypatch):
    cs_mod = _fake_cs(tmp_path, monkeypatch)
    _write_heartbeat(cs_mod, age_sec=200)
    pushed = _capture_notify(monkeypatch)
    state = {"legs": {}, "events": []}

    stale = qe._check_feed_engine(state, log=NOOP)

    assert stale is True
    assert pushed == []
    assert not state.get("_signal_stall_alerted")


def test_signal_stall_recovery_pushes_once_after_an_alerted_stall(tmp_path, monkeypatch):
    cs_mod = _fake_cs(tmp_path, monkeypatch)
    _write_heartbeat(cs_mod, age_sec=200)
    pushed = _capture_notify(monkeypatch)
    state = {"legs": {"ORB": {}}, "events": []}
    qe._check_feed_engine(state, log=NOOP)
    assert len(pushed) == 1

    _write_heartbeat(cs_mod, age_sec=1)
    stale = qe._check_feed_engine(state, log=NOOP)

    assert stale is False
    assert len(pushed) == 2
    assert "recovered" in pushed[1][1].lower()
    assert not state.get("_signal_stall_alerted")


def test_signal_stall_recovery_stays_quiet_when_never_alerted(tmp_path, monkeypatch):
    cs_mod = _fake_cs(tmp_path, monkeypatch)
    _write_heartbeat(cs_mod, age_sec=200)
    pushed = _capture_notify(monkeypatch)
    state = {"legs": {}, "events": []}
    qe._check_feed_engine(state, log=NOOP)
    assert pushed == []

    _write_heartbeat(cs_mod, age_sec=1)
    qe._check_feed_engine(state, log=NOOP)

    assert pushed == [], "no stall alert ever fired (no open lot), so no recovery push either"


# ═══════════════ item 2: broker reconcile MISMATCH/READ FAILURE -> phone push ══════

class _FakeReconcileAdapter:
    def __init__(self, mode="PAPER", result=None):
        self._mode = mode
        self._result = result

    def effective_mode(self):
        return self._mode, "test"

    def reconcile(self):
        return self._result


def test_reconcile_mismatch_pushes_the_first_occurrence(monkeypatch):
    adapter = _FakeReconcileAdapter(result={"ok": False, "mismatches": ["ORB off by 5"]})
    pushed = _capture_notify(monkeypatch)
    state = {"_reconcile_due": True, "events": []}

    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)

    assert len(pushed) == 1
    title, msg, priority = pushed[0]
    assert priority == "high"
    assert "MISMATCH" in msg


def test_reconcile_read_failure_labeled_as_read_failure(monkeypatch):
    adapter = _FakeReconcileAdapter(
        result={"ok": False, "error": "can't read positions at Webull: timed out"})
    pushed = _capture_notify(monkeypatch)
    state = {"_reconcile_due": True, "events": []}

    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)

    assert len(pushed) == 1
    assert "READ FAILURE" in pushed[0][1]


def test_reconcile_ok_never_pages(monkeypatch):
    adapter = _FakeReconcileAdapter(result={"ok": True, "mismatches": []})
    pushed = _capture_notify(monkeypatch)
    state = {"_reconcile_due": True, "events": []}

    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)

    assert pushed == []


def test_reconcile_alert_capped_at_30_minutes_while_it_persists(monkeypatch):
    adapter = _FakeReconcileAdapter(result={"ok": False, "mismatches": ["ORB off by 5"]})
    pushed = _capture_notify(monkeypatch)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    state = {"_reconcile_due": True, "events": []}

    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert len(pushed) == 1

    clock[0] += 5 * 60
    state["_reconcile_due"] = True
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert len(pushed) == 1, "still under 30 minutes since the last push -- must not page again"

    clock[0] += 26 * 60
    state["_reconcile_due"] = True
    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)
    assert len(pushed) == 2, "30+ minutes elapsed while it persists -- pages again"


def test_reconcile_alert_first_occurrence_repeats_on_a_new_day(monkeypatch):
    adapter = _FakeReconcileAdapter(result={"ok": False, "mismatches": ["ORB off by 5"]})
    pushed = _capture_notify(monkeypatch)
    state = {"_reconcile_due": True, "events": [],
            "_reconcile_alert": {"day": "2020-01-01", "last_at": real_time.time()}}

    qe._maybe_run_broker_reconcile(state, {}, adapter, None, active=True, log=NOOP)

    assert len(pushed) == 1, "a new calendar day always pages on its own first occurrence"


# ═══════════════ item 3: repeated tick-loop exceptions -> phone push ═══════════════

def test_tick_failure_alert_fires_once_at_the_threshold(monkeypatch):
    pushed = _capture_notify(monkeypatch)
    state = {"events": []}

    qe._note_tick_result(state, False, exc=RuntimeError("boom1"), log=NOOP)
    qe._note_tick_result(state, False, exc=RuntimeError("boom2"), log=NOOP)
    assert pushed == [], "two consecutive failures is not yet an episode worth a page"

    qe._note_tick_result(state, False, exc=RuntimeError("boom3"), log=NOOP)
    assert len(pushed) == 1
    assert pushed[0][2] == "high"

    qe._note_tick_result(state, False, exc=RuntimeError("boom4"), log=NOOP)
    assert len(pushed) == 1, "one push per episode -- a 4th consecutive failure must not re-page"


def test_tick_failure_streak_resets_on_a_successful_tick(monkeypatch):
    pushed = _capture_notify(monkeypatch)
    state = {"events": []}

    qe._note_tick_result(state, False, exc=RuntimeError("boom1"), log=NOOP)
    qe._note_tick_result(state, True, log=NOOP)
    assert state["_tick_fail_streak"] == 0

    qe._note_tick_result(state, False, exc=RuntimeError("boom2"), log=NOOP)
    qe._note_tick_result(state, False, exc=RuntimeError("boom3"), log=NOOP)
    assert pushed == [], "the earlier success reset the streak -- this is only 2 in a row"


def test_tick_failure_new_episode_after_recovery_pages_again(monkeypatch):
    pushed = _capture_notify(monkeypatch)
    state = {"events": []}

    for i in range(3):
        qe._note_tick_result(state, False, exc=RuntimeError(f"a{i}"), log=NOOP)
    assert len(pushed) == 1

    qe._note_tick_result(state, True, log=NOOP)

    for i in range(3):
        qe._note_tick_result(state, False, exc=RuntimeError(f"b{i}"), log=NOOP)
    assert len(pushed) == 2, "a fresh episode after a recovery must be able to page again"


# ═══════ item 4: hard timeout around the broker send -> outcome UNKNOWN ════════════

def test_place_stock_order_with_timeout_never_blocks_past_the_bound(monkeypatch):
    monkeypatch.setattr(qe, "BROKER_SEND_HARD_TIMEOUT_SEC", 0.05)
    # MINOR REVIEW FIX (2026-09-26): an Event this test itself releases in `finally`,
    # not a fixed real_time.sleep() -- a plain sleep left the shared single-worker
    # executor (_place_order_executor) busy for up to that long after this test
    # returned, so every LATER test that goes through a real
    # _place_stock_order_with_timeout call queued behind it (the same queue-behind
    # hazard major finding #2 above fixes for a genuine hung send, showing up here
    # inside the suite itself).
    release = threading.Event()

    class _HangAdapter:
        def place_stock_order(self, **kw):
            release.wait(timeout=5.0)   # released below once this test has its answer
            return {"ok": True, "sent": True}

    start = real_time.time()
    try:
        rec = qe._place_stock_order_with_timeout(
            _HangAdapter(), leg="ORB", signal_id="ORB_257-20260926T093100Z-L", symbol="QQQ",
            side="BUY", qty=5, intent="OPEN", mode="PAPER", log=NOOP)
        elapsed = real_time.time() - start

        assert elapsed < 1.5, "must give up at BROKER_SEND_HARD_TIMEOUT_SEC, not wait for the call"
        assert rec["outcome"] == "UNKNOWN"
        assert rec["ok"] is False
        assert rec["sent"] is True, "never claim a timed-out send was 'not placed'"
        assert rec["mode"] == "PAPER"
        assert rec["client_order_id"] == WO._sanitize_client_order_id(
            "ORB_257-20260926T093100Z-L")
    finally:
        # let the hung fake return, then wait for the background worker to actually
        # finish before this test ends -- see the comment above `release`.
        release.set()
        fut = qe._inflight_send.get("future")
        if fut is not None:
            fut.result(timeout=5.0)


def test_place_stock_order_with_timeout_passes_through_a_normal_result(monkeypatch):
    class _FastAdapter:
        def place_stock_order(self, **kw):
            return {"ok": True, "sent": True, "mode": "PAPER", "client_order_id": "sig1"}

    rec = qe._place_stock_order_with_timeout(
        _FastAdapter(), leg="ORB", signal_id="sig1", symbol="QQQ", side="BUY", qty=5,
        intent="OPEN", mode="PAPER", log=NOOP)

    assert rec == {"ok": True, "sent": True, "mode": "PAPER", "client_order_id": "sig1"}


def test_is_unknown_outcome():
    assert qe._is_unknown_outcome({"outcome": "UNKNOWN"}) is True
    assert qe._is_unknown_outcome({"outcome": "unknown"}) is True
    assert qe._is_unknown_outcome({"outcome": None}) is False
    assert qe._is_unknown_outcome({}) is False
    assert qe._is_unknown_outcome(None) is False


def _unknown_rec_stub(*, mode="PAPER"):
    """Exactly the shape _place_stock_order_with_timeout returns on a real timeout --
    used to drive _mirror_to_broker's OWN handling of that shape directly, instead of
    racing a real background thread against a live OrderAdapter/mock SDK client (that
    race is real: the worker thread's dispatch can outlast a short patched
    BROKER_SEND_HARD_TIMEOUT_SEC, so the test's own monkeypatch of adapter._build_client
    can already be undone by the time the thread reaches it, leaking a genuine webull
    client-build attempt onto a LATER test's teardown -- exactly the failure mode this
    helper exists to avoid)."""
    return {"leg": "ORB", "symbol": qe.BROKER_SYMBOL, "side": "BUY", "qty": 5,
           "intent": "OPEN", "signal_id": "sig", "client_order_id": "coid123",
           "mode": mode, "ok": False, "sent": True, "duplicate": False,
           "outcome": "UNKNOWN", "reason": "broker send timed out after 40s"}


def test_broker_send_timeout_on_open_pushes_and_is_never_auto_resent(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_place_stock_order_with_timeout",
                        lambda *a, **k: _unknown_rec_stub())
    pushed = _capture_notify(monkeypatch)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=ORB_TRADE_ID, seq=0, log=NOOP)

    assert len(pushed) == 1
    title, msg, priority = pushed[0]
    assert priority == "high"
    assert "UNKNOWN" in msg
    assert state.get("_broker_resend", {}) == {}, \
        "an UNKNOWN OPEN must never be queued for auto-resend"


def test_broker_send_timeout_on_close_queues_needs_verify_close_retry(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_place_stock_order_with_timeout",
                        lambda *a, **k: _unknown_rec_stub())
    _seed_sent(adapter, "ORB", 5)
    pushed = _capture_notify(monkeypatch)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    entry = state["_broker_resend"][f"ORB:CLOSE:{ORB_TRADE_ID}"]
    assert entry["why"] == "close_retry"
    assert entry["needs_verify"] is True, \
        "an UNKNOWN CLOSE must be verified against Webull before ever re-sending blind"
    assert len(pushed) == 1 and pushed[0][2] == "high"


def test_alert_broker_send_unknown_pushes_every_time_never_throttled(monkeypatch):
    pushed = _capture_notify(monkeypatch)
    state = {"events": []}

    qe._alert_broker_send_unknown(state, leg="ORB", intent="OPEN", side="BUY", shares=5,
                                  reason="timed out", client_order_id="abc123", log=NOOP)
    qe._alert_broker_send_unknown(state, leg="ORB", intent="OPEN", side="BUY", shares=5,
                                  reason="timed out again", client_order_id="abc124", log=NOOP)

    assert len(pushed) == 2, "unlike _alert_broker_not_ok's OPEN throttle, this always pages"
    assert all(p == "high" for _t, _m, p in pushed)
    assert "abc123" in pushed[0][1] and "abc124" in pushed[1][1]


# ═══ review fix major #2: a second send must never queue behind a hung first one ═══

def test_second_send_while_first_is_hung_returns_blocked_without_waiting(monkeypatch):
    monkeypatch.setattr(qe, "BROKER_SEND_HARD_TIMEOUT_SEC", 5.0)
    calls = []
    release = threading.Event()

    class _HangAdapter:
        def place_stock_order(self, **kw):
            calls.append(kw)
            release.wait(timeout=5.0)
            return {"ok": True, "sent": True}

    adapter = _HangAdapter()
    t = threading.Thread(target=lambda: qe._place_stock_order_with_timeout(
        adapter, leg="ORB", signal_id="sig1", symbol="QQQ", side="BUY", qty=5,
        intent="OPEN", mode="PAPER", log=NOOP))
    t.start()
    try:
        # wait for the worker thread to actually start send 1 (not just be submitted)
        deadline = real_time.time() + 2.0
        while not calls and real_time.time() < deadline:
            real_time.sleep(0.01)
        assert calls, "send 1 never started -- test setup is broken"

        start = real_time.time()
        rec2 = qe._place_stock_order_with_timeout(
            adapter, leg="NOISE", signal_id="sig2", symbol="QQQ", side="SELL", qty=3,
            intent="CLOSE", mode="PAPER", log=NOOP)
        elapsed = real_time.time() - start

        assert elapsed < 1.0, "must not queue behind the hung send and wait out its timeout"
        assert rec2["ok"] is False
        assert rec2["sent"] is False, "a blocked send must be a definite not-sent, not UNKNOWN"
        assert rec2["mode"] == "BLOCKED"
        assert len(calls) == 1, "place_stock_order must never be called for the blocked send"
    finally:
        release.set()
        t.join(timeout=5.0)

    # even after the hang clears, the blocked send is never retroactively placed
    real_time.sleep(0.05)
    assert len(calls) == 1


def test_third_send_goes_through_once_the_hang_clears(monkeypatch):
    monkeypatch.setattr(qe, "BROKER_SEND_HARD_TIMEOUT_SEC", 5.0)
    calls = []
    release = threading.Event()

    class _HangAdapter:
        def place_stock_order(self, **kw):
            calls.append(kw)
            if len(calls) == 1:
                release.wait(timeout=5.0)
            return {"ok": True, "sent": True, "mode": "PAPER"}

    adapter = _HangAdapter()
    t = threading.Thread(target=lambda: qe._place_stock_order_with_timeout(
        adapter, leg="ORB", signal_id="sig1", symbol="QQQ", side="BUY", qty=5,
        intent="OPEN", mode="PAPER", log=NOOP))
    t.start()
    try:
        deadline = real_time.time() + 2.0
        while not calls and real_time.time() < deadline:
            real_time.sleep(0.01)
        assert calls

        blocked = qe._place_stock_order_with_timeout(
            adapter, leg="NOISE", signal_id="sig2", symbol="QQQ", side="SELL", qty=3,
            intent="CLOSE", mode="PAPER", log=NOOP)
        assert blocked["mode"] == "BLOCKED"
    finally:
        release.set()
        t.join(timeout=5.0)

    # send 1 has now resolved -- a fresh send must go straight through, not stay blocked
    rec3 = qe._place_stock_order_with_timeout(
        adapter, leg="GAPGO", signal_id="sig3", symbol="QQQ", side="BUY", qty=1,
        intent="OPEN", mode="PAPER", log=NOOP)
    assert rec3 == {"ok": True, "sent": True, "mode": "PAPER"}
    assert len(calls) == 2, "the blocked send 2 must never have actually reached place_stock_order"


# ═══ review fix major #1: housekeeping must not block on the lock a hung send holds ═══

def test_housekeeping_skips_while_a_broker_send_is_hung_on_the_lock(tmp_path, monkeypatch):
    """A real OrderAdapter whose place_stock_order is hung deep inside `with
    self._lock:` (webull_orders.py) via a blocked mocked SDK call must not freeze
    _run_broker_housekeeping's own update_daily_pnl/reset_daily_pnl/reconcile calls,
    which take that same lock."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "BROKER_SEND_HARD_TIMEOUT_SEC", 5.0)
    monkeypatch.setattr(adapter, "update_daily_pnl", MagicMock())
    monkeypatch.setattr(adapter, "reset_daily_pnl", MagicMock())

    entered = threading.Event()
    release = threading.Event()
    orig_return = client.order_v3.place_order.return_value

    def _blocking_place_order(*a, **k):
        entered.set()
        release.wait(timeout=5.0)
        return orig_return

    client.order_v3.place_order.side_effect = _blocking_place_order

    t = threading.Thread(target=lambda: qe._place_stock_order_with_timeout(
        adapter, leg="ORB", signal_id="sig1", symbol="QQQ", side="BUY", qty=5,
        intent="OPEN", mode="PAPER", log=NOOP))
    t.start()
    try:
        assert entered.wait(timeout=2.0), "the fake send never started -- test setup is broken"

        start = real_time.time()
        qe._run_broker_housekeeping({}, {}, datetime.datetime.now(), True, log=NOOP)
        elapsed = real_time.time() - start

        assert elapsed < 1.0, \
            "housekeeping must skip while the send is in flight, not block on its lock"
        adapter.update_daily_pnl.assert_not_called()
        adapter.reset_daily_pnl.assert_not_called()
    finally:
        release.set()
        t.join(timeout=5.0)


def test_housekeeping_resumes_once_the_hung_send_resolves(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "BROKER_SEND_HARD_TIMEOUT_SEC", 5.0)

    entered = threading.Event()
    release = threading.Event()
    orig_return = client.order_v3.place_order.return_value

    def _blocking_place_order(*a, **k):
        entered.set()
        release.wait(timeout=5.0)
        return orig_return

    client.order_v3.place_order.side_effect = _blocking_place_order

    t = threading.Thread(target=lambda: qe._place_stock_order_with_timeout(
        adapter, leg="ORB", signal_id="sig1", symbol="QQQ", side="BUY", qty=5,
        intent="OPEN", mode="PAPER", log=NOOP))
    t.start()
    assert entered.wait(timeout=2.0)
    qe._run_broker_housekeeping({}, {}, datetime.datetime.now(), False, log=NOOP)
    assert qe._send_inflight_future() is not None, "still hung -- housekeeping should have skipped"

    release.set()
    t.join(timeout=5.0)
    # give _send_inflight_future a chance to observe the now-finished future
    for _ in range(200):
        if qe._send_inflight_future() is None:
            break
        real_time.sleep(0.01)
    assert qe._send_inflight_future() is None

    # a fresh housekeeping call now runs normally (no adapter to touch here, this only
    # asserts it no longer thinks a send is in flight and does not skip)
    qe._run_broker_housekeeping({}, {}, datetime.datetime.now(), False, log=NOOP)


# ═══ review fix minor: _note_tick_result before save_state in qqq_exec_thread ═══

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
    monkeypatch.setattr(qe, "_stream_should_run", lambda now_et: True)


def _fake_doc(positions=None):
    return {"mode": "SHADOW", "signal_source": "engine", "updated_at": "x",
           "feed_stale": False, "px_feed_stale": False, "breaker_tripped": False,
           "kill": False, "positions": positions or {},
           "today": {"orders": [], "trades": [], "realized_pnl": 0.0, "unrealized_pnl": 0.0},
           "events": [], "broker": {"effective_mode": "OFF"},
           "lease": {"host_id": "h", "leased_at": 1.0}}


def test_save_state_persists_the_reset_streak_on_the_recovery_tick(tmp_path, monkeypatch):
    """MINOR REVIEW FIX (2026-09-26, item 3): _note_tick_result must update `state`
    BEFORE save_state persists it in qqq_exec_thread's loop body -- it used to run
    after, so the FIRST successful tick after an alerted episode saved the STALE
    streak/alerted flag a moment before this call would have reset them; a restart
    landing right there loaded _tick_fail_alerted=True and suppressed the page for a
    genuinely new episode."""
    _thread_paths(tmp_path, monkeypatch)
    calls = {"n": 0}

    def fake_tick(**kw):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError(f"boom{calls['n']}")
        return (kw.get("cfg") or {}, kw.get("state") or {}, _fake_doc())

    monkeypatch.setattr(qe, "tick", fake_tick)
    saved = []
    real_save_state = qe.save_state

    def _spy_save_state(state, log=print):
        saved.append(dict(state))
        return real_save_state(state, log=log)

    monkeypatch.setattr(qe, "save_state", _spy_save_state)
    pushed = _capture_notify(monkeypatch)

    stop = threading.Event()
    t = threading.Thread(target=qe.qqq_exec_thread, args=(None, ["uid1"]),
                        kwargs={"stop": stop, "log": lambda *_: None}, daemon=True)
    t.start()
    deadline = real_time.time() + 3.0
    while not saved and real_time.time() < deadline:
        real_time.sleep(0.02)
    stop.set()
    t.join(timeout=3)

    assert len(pushed) == 1, "3 consecutive failures should have paged once"
    assert saved, "the recovery tick never reached save_state"
    first_save = saved[0]
    assert first_save.get("_tick_fail_streak") == 0, \
        "save_state ran with the streak already reset -- _note_tick_result must run first"
    assert first_save.get("_tick_fail_alerted") is False


# ═══ SECOND REVIEW (2026-09-26) of item 4 above -- see the review findings against
# api/qqq_exec.py's own module comments for _queue_broker_resend / _is_unknown_outcome /
# _place_stock_order_with_timeout for the full write-up:
#   * minor: an adapter-side UNKNOWN can live on rec["parts"][i]["outcome"] (the OTHER
#     track's own part shape), never the top-level record -- _is_unknown_outcome must
#     check both.
#   * minor: a paging storm -- every close_retry re-send that bounces off a STILL-hung
#     earlier send (mode="BLOCKED", inflight_blocked=True) must not re-page; the
#     UNKNOWN alert already covered the episode once.
# (the two MAJOR findings from this same review -- the needs_verify/last_signal_id
# carryover, and split-order per-part verification -- have their own tests in
# tests/test_qqq_exec_exit_safety.py, alongside the rest of the close_retry suite.)

def test_is_unknown_outcome_also_reads_the_other_tracks_part_shape():
    assert qe._is_unknown_outcome({"outcome": None, "parts": [{"outcome": "UNKNOWN"}]}) is True
    assert qe._is_unknown_outcome({"parts": [{"outcome": "unknown"}, {"outcome": "OK"}]}) is True
    assert qe._is_unknown_outcome({"parts": [{"outcome": "OK"}]}) is False
    assert qe._is_unknown_outcome({"parts": None}) is False
    assert qe._is_unknown_outcome({}) is False


def test_inflight_blocked_record_never_pages_not_ok_but_still_logs(tmp_path, monkeypatch):
    """PAGING STORM (minor, 2026-09-26 review): a close_retry re-send that bounces off a
    STILL-hung earlier send comes back mode="BLOCKED"/inflight_blocked=True -- it must
    never trigger _alert_broker_not_ok's own phone push (the UNKNOWN alert for the
    original hang already paged for this episode), but the plain not-ok log line must
    still run -- nothing here is silently swallowed, only the repeat push."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_place_stock_order_with_timeout", lambda *a, **k: {
        "leg": "ORB", "symbol": qe.BROKER_SYMBOL, "side": "SELL", "qty": 5,
        "intent": "CLOSE", "signal_id": "sig1", "client_order_id": "sig1", "mode": "BLOCKED",
        "ok": False, "sent": False, "duplicate": False, "inflight_blocked": True,
        "reason": "previous broker send still in flight (hung) -- not queuing another "
                 "send behind it"})
    _seed_sent(adapter, "ORB", 5)
    pushed = _capture_notify(monkeypatch)
    logged = []
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID,
                         log=lambda m: logged.append(m))

    assert pushed == [], "an in-flight-blocked record must never trigger its own phone push"
    assert any("NOT ok" in m for m in logged), \
        "the plain not-ok log line must still run -- nothing silently lost"
    assert state["_broker_resend"][f"ORB:CLOSE:{ORB_TRADE_ID}"]["why"] == "close_retry", \
        "still queued for a later retry, only the push is skipped"


def test_ordinary_not_ok_close_still_pages_when_not_inflight_blocked(tmp_path, monkeypatch):
    """Guard against over-suppressing: an ordinary not-ok CLOSE (no inflight_blocked
    flag at all) must keep paging exactly as before this fix."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    client.order_v3.place_order.side_effect = RuntimeError("boom")
    pushed = _capture_notify(monkeypatch)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    assert len(pushed) == 1 and pushed[0][2] == "high"


# ═ item 5 minor (2026-09-26 THIRD review): _broker_row_outcome must classify an
# AMBIGUOUS send (sent=True, ok=False, no definite 4xx of its own -- a 5xx, a timeout, a
# dropped connection) as UNKNOWN, never REFUSED. It used to check _is_unknown_outcome
# alone, which only fires once something upstream had ALREADY tagged the record
# outcome="UNKNOWN" explicitly -- an ordinary exception/5xx/dropped-connection record
# never gets that tag, so it was written to broker_orders.csv as REFUSED even though
# _queue_broker_resend's own needs_verify judgment (on that SAME rec) treats it as
# genuinely unresolved and re-verifies before ever re-sending -- misreporting exactly
# the rows this column exists to flag.

def test_broker_row_outcome_ambiguous_5xx_is_unknown_not_refused():
    rec = {"ok": False, "sent": True,
          "reason": "ServerException: HTTP Status: 503, Code: SERVICE_UNAVAILABLE, "
                    "Msg: x, RequestID: r1"}
    assert qe._broker_row_outcome(rec) == "UNKNOWN"


def test_broker_row_outcome_dropped_connection_is_unknown_not_refused():
    rec = {"ok": False, "sent": True, "reason": "RuntimeError: dropped connection"}
    assert qe._broker_row_outcome(rec) == "UNKNOWN"


def test_broker_row_outcome_definite_4xx_is_refused():
    rec = {"ok": False, "sent": True,
          "reason": "ServerException: HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_"
                    "FOR_FIXGW_NOT_READY_MARKET, Msg: x, RequestID: r2"}
    assert qe._broker_row_outcome(rec) == "REFUSED"


def test_broker_row_outcome_ok_record_is_ok():
    assert qe._broker_row_outcome({"ok": True, "sent": True}) == "OK"


def test_broker_row_outcome_blocked_before_send_is_blocked_not_unknown():
    """A lease/halt BLOCKED record never reached the send path at all (sent=False) --
    it is a definite decision, not an ambiguous outcome."""
    rec = {"ok": False, "sent": False, "mode": "BLOCKED", "reason": "halted: reconcile"}
    assert qe._broker_row_outcome(rec) == "BLOCKED"


def test_broker_row_outcome_explicit_unknown_tag_wins_even_if_ok():
    """_is_unknown_outcome's own explicit tag still takes priority, exactly as before."""
    assert qe._broker_row_outcome({"outcome": "UNKNOWN", "ok": True, "sent": True}) == "UNKNOWN"


def test_broker_row_outcome_split_order_ambiguous_part_is_unknown():
    """A netted CLOSE split into two parts: part 1 got a definite 417 refusal, part 2
    timed out with no status at all. The combined top-level `reason` text (whichever
    part's text happens to be there) must never hide part 2's own ambiguity -- checked
    PER PART, the same way _queue_broker_resend's own needs_verify judgment is."""
    rec = {"ok": False, "sent": True, "reason": "see parts",
          "parts": [
              {"ok": False, "sent": True,
               "reason": "ServerException: HTTP Status: 417, Code: X, Msg: y, "
                         "RequestID: r3"},
              {"ok": False, "sent": True, "reason": "RuntimeError: timed out"},
          ]}
    assert qe._broker_row_outcome(rec) == "UNKNOWN"


def test_broker_row_outcome_split_order_every_part_definite_4xx_is_refused():
    rec = {"ok": False, "sent": True, "reason": "see parts",
          "parts": [
              {"ok": False, "sent": True,
               "reason": "ServerException: HTTP Status: 417, Code: X, Msg: y, "
                         "RequestID: r4"},
              {"ok": True, "sent": True, "reason": ""},
          ]}
    assert qe._broker_row_outcome(rec) == "REFUSED"


def test_mirror_to_broker_writes_unknown_outcome_for_a_5xx_row_and_refused_for_a_417(
        tmp_path, monkeypatch):
    """CSV-level repro of the exact review finding: a 503/dropped-connection send is
    written with outcome=UNKNOWN, a 417 (definite refusal) with outcome=REFUSED."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    state = {"legs": {}, "events": []}

    client.order_v3.place_order.side_effect = RuntimeError(
        "ServerException: HTTP Status: 503, Code: SERVICE_UNAVAILABLE, Msg: x, "
        "RequestID: r5")
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["outcome"] == "UNKNOWN"

    client.order_v3.place_order.side_effect = RuntimeError(
        "ServerException: HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_"
        "NOT_READY_MARKET, Msg: x, RequestID: r6")
    # resend=1 (a fresh signal_id/client_order_id, exactly like a real retry under a
    # fresh id) -- same ts/trade_id would otherwise hit place_stock_order's own
    # idempotent signal_id cache and never call place_order a second time at all.
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, resend=1, log=NOOP)
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["outcome"] == "REFUSED"
