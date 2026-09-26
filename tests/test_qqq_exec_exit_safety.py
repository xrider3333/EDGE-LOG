"""EXIT SAFETY (2026-09-26): "no exit can fail silently, and the end of day ends flat
or loudly not flat." Seven items, api/qqq_exec.py only:
  1. a phone alert on every broker record with ok=False (CLOSE every time, OPEN at most
     once per leg per day) -- _alert_broker_not_ok, wired into _mirror_to_broker's own
     "NOT ok" log line.
  2. a CLOSE that comes back not ok for ANY reason (except confirmed "nothing to
     close") joins the existing broker re-send queue as why="close_retry" and is
     retried with backoff until the session flatten deadline, re-checking the
     adapter's own believed position before every attempt -- _queue_broker_resend /
     _maybe_resend_broker_orders / _believed_qty_for_leg.
  3. a CLOSE is never blocked by the Firestore lease send-gate while THIS process
     holds the LOCAL serving lock -- _is_serving_standalone, _mirror_to_broker.
  4. after the EOD flatten and its retries, read Webull's own QQQ position and push
     urgently if it is not flat -- _check_webull_flat_after_eod /
     _maybe_check_webull_flat_after_eod, plus the EOD summary's own line.
  5. a half-day's flat_by clamps to the early close MINUS 3 minutes (not the bell
     itself) and last_entry to minus 10 minutes -- the tick() half-day block.
  6. an EOD/forced exit in engine mode prices off the live Webull stream when it is
     at most 15s old, else the bar close -- _exit_price_for_leg, _close_all.
  7. _notify grew an optional `priority` argument, backward compatible.

REVIEW FIXES (2026-09-26, same day): a critical double-sell gap and five major/minor
findings against the above, fixed in place -- see the "review" markers in each section:
  * item 1 CRITICAL: a CLOSE whose previous attempt actually reached place_stock_order
    (rec['sent']) but came back not ok is now verified against Webull's own order
    record (_order_known_at_broker) before ever re-sending -- believed_positions alone
    cannot tell "never sent" apart from "sent, outcome unknown".
  * item 2 major: _maybe_check_webull_flat_after_eod now waits
    BROKER_RECONCILE_POST_ORDER_GRACE_SEC after the last broker send and for every
    CLOSE of any `why` (not only close_retry) before reading Webull's position.
  * item 3 major: adapter.positions() now runs through a bounded executor
    (_positions_with_timeout), never inline on the tick thread.
  * item 3 major (a second finding against the same item): the CLOSE lease-gate
    exemption now fires only for a genuinely unverifiable ("outage") lease reason, never
    a confirmed fresh foreign lease or this process's own confirmed stand-down.
  * item 4 major: the EOD summary's line is now dated and prints "not checked" instead
    of defaulting to a false "yes"; the check also now runs on a KILL-file day.
  * item 2 minor: the re-send queue keys a close_retry CLOSE by trade_id, so an older
    trade's still-pending retry survives a newer trade's own failed close.
  * item 2 minor: _believed_qty_for_leg now reads the smaller of believed_positions and
    broker_sent_positions.

FOURTH REVIEW (2026-09-26, same day): one more critical/major double-sell gap plus two
minor findings against the SECOND/THIRD review's own fixes above:
  * item 1 major: (SUPERSEDED by the FINAL RULE below) the account-position fallback
    was withheld for a grace period after the unclear send.
  * item 3 minor (paging): the CLOSE-retry "stalled" push now shares the leg's own plain
    CLOSE-failure throttle key (_close_fail_should_alert(state, leg, ...)) instead of a
    separate "<leg>#stall" one -- the separate key let a leg page twice per 5 minutes
    (once NOT OK/UNKNOWN, once stalled), not the one point 3 calls for.
  * item 2 minor (docstring): _order_known_at_broker_any's docstring and the dead "every
    part positively never reached the book -- safe to retry" (False) return path are
    removed -- _order_known_at_broker itself can no longer produce that answer.

FINAL CLOSE RE-SEND RULE (2026-09-26, lead decision after four review rounds): one
Webull margin account nets every leg, so an ACCOUNT position read can never say which
leg's shares are still out -- the account-position fallback is DELETED and an ambiguous
CLOSE is never re-sent on position arithmetic. Only Webull's own record of the earlier
attempt (by order id, per unresolved part id for a split) decides:
  * FILLED -> drop, never re-send; still WORKING/PENDING -> keep waiting, never re-send;
  * REJECTED/CANCELLED/FAILED with an EXPLICIT filled quantity -> dead: re-send now,
    only the unfilled remainder;
  * not found / lookup error / missing filled quantity -> hold, re-check every backoff
    step, urgent push at 2+ holds (shared per-leg throttle), give up at the flatten
    deadline with the urgent give-up push.
A definite 4xx at SEND time still retries right away, no lookup.

HARNESS: same conventions as tests/test_qqq_exec_broker_resend.py (helpers copied
LOCALLY, not imported). No real Firestore/Webull/network call anywhere -- the SDK
client is always a MagicMock, and tests/conftest.py's autouse fixtures already isolate
api.qqq_exec._ORDER_ADAPTER / the live-stream factory / EDGELOG_HOME for every test
here even when a test does not build its own adapter.
"""
import csv
import datetime
import json
import os
import time
from unittest.mock import MagicMock

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731


# ── harness (copied from tests/test_qqq_exec_broker_resend.py) ─────────────────────

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
    """As if a real OPEN for `leg` already reached the broker and filled -- mirrors
    broker_sent_positions (what reconcile()/the NOTHING TO CLOSE guard trust) AND
    believed_positions (what item 2's never-double-sell re-check trusts)."""
    adapter._state.setdefault("broker_sent_positions", {})[leg] = {
        "symbol": "QQQ", "qty": qty, "account_id": account_id}
    adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
    if qty:
        adapter._state.setdefault("open_legs", {})[leg] = True


NOISE_TRADE_ID = "NOISE_304-20260926T140000Z-L"
ORB_TRADE_ID = "ORB_257-20260926T093100Z-L"


def _resend_cfg():
    return {"session": {"open": "09:31", "last_entry": "15:55", "flat_by": "15:58"}}


# ═════════════════════════ item 7: _notify priority ════════════════════════════════

def test_notify_omits_priority_defaults_header_to_default(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    captured = {}

    def fake_urlopen(req, timeout=4):
        captured["priority"] = req.get_header("Priority")
        return object()

    monkeypatch.setattr(qe.urllib.request, "urlopen", fake_urlopen)
    qe._notify("routine ping", "Title", log=NOOP)
    assert captured["priority"] == "default"


def test_notify_priority_override_reaches_the_header(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    captured = {}

    def fake_urlopen(req, timeout=4):
        captured["priority"] = req.get_header("Priority")
        return object()

    monkeypatch.setattr(qe.urllib.request, "urlopen", fake_urlopen)
    qe._notify("hold on", "Title", log=NOOP, priority="urgent")
    assert captured["priority"] == "urgent"


def test_notify_still_no_network_when_topic_unset(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)

    def boom(req, timeout=4):
        raise AssertionError("must never touch the network with no topic configured")

    monkeypatch.setattr(qe.urllib.request, "urlopen", boom)
    qe._notify("no topic", "Title", log=NOOP, priority="high")   # must not raise


# ═════════════════ item 1: phone alert on every not-ok broker record ═══════════════

# EXIT SAFETY item 3 (2026-09-26, LEAD DECISION on the "alerts in book" review): a CLOSE
# that keeps failing across many backoff retries used to page on EVERY not-ok
# _mirror_to_broker call -- a real outage could then page every 5-30s for hours. The
# lead's call: page on the FIRST failure, then at most once per CLOSE_FAIL_ALERT_GAP_SEC
# per leg while it keeps failing, plus the give-up push (always, at urgent priority).
# NOT one push per retry -- see _close_fail_should_alert/_close_fail_alert_reset.

def test_alert_close_pages_first_failure_then_throttles_until_the_gap_elapses(monkeypatch):
    pushed = []
    state = {"events": []}
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    monkeypatch.setattr(
        qe, "_notify",
        lambda msg, title, log=print, priority=None: pushed.append((title, msg, priority)))

    qe._alert_broker_not_ok(state, leg="NOISE", intent="CLOSE", side="SELL",
                            shares=10, reason="refused", log=NOOP)
    assert len(pushed) == 1, "the first failure must always page"

    clock[0] += 5   # well inside CLOSE_FAIL_ALERT_GAP_SEC
    qe._alert_broker_not_ok(state, leg="NOISE", intent="CLOSE", side="SELL",
                            shares=10, reason="refused again", log=NOOP)
    assert len(pushed) == 1, "a retry inside the gap must not page again (not per-retry)"

    clock[0] += qe.CLOSE_FAIL_ALERT_GAP_SEC + 1
    qe._alert_broker_not_ok(state, leg="NOISE", intent="CLOSE", side="SELL",
                            shares=10, reason="still refused", log=NOOP)
    assert len(pushed) == 2, "once the gap elapses, the still-failing CLOSE pages again"
    assert all(p == "high" for _t, _m, p in pushed)
    assert all("CLOSE NOT OK" in m for _t, m, _p in pushed)
    # a throttled failure (same style as the pre-existing OPEN once-per-day throttle)
    # logs no timeline event either -- the caller's own "NOT ok" log line (right above
    # this function's call site in _mirror_to_broker) already recorded it either way.
    assert len(state["events"]) == 2

    # a different leg's own failure must page immediately, independent of NOISE's gate
    qe._alert_broker_not_ok(state, leg="ORB", intent="CLOSE", side="SELL",
                            shares=5, reason="refused", log=NOOP)
    assert len(pushed) == 3


def test_alert_close_reset_lets_the_next_episode_page_immediately(monkeypatch):
    """_close_fail_alert_reset (called once a CLOSE-failure episode resolves -- a retry
    lands, the queue gives up, the position reads already gone) must let the NEXT
    failure for the same leg page right away, not inherit the old episode's cooldown."""
    pushed = []
    state = {"events": []}
    clock = [2_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append(msg))

    qe._alert_broker_not_ok(state, leg="NOISE", intent="CLOSE", side="SELL",
                            shares=10, reason="refused", log=NOOP)
    assert len(pushed) == 1

    qe._close_fail_alert_reset(state, "NOISE")
    clock[0] += 1   # nowhere near the gap -- would still be throttled without the reset

    qe._alert_broker_not_ok(state, leg="NOISE", intent="CLOSE", side="SELL",
                            shares=10, reason="a new episode's own failure", log=NOOP)
    assert len(pushed) == 2


def test_alert_open_pushes_at_most_once_per_leg_per_day():
    pushed = []
    state = {"events": []}

    def fake_notify(msg, title, log=print, priority=None):
        pushed.append(msg)

    import unittest.mock as um
    with um.patch.object(qe, "_notify", fake_notify):
        qe._alert_broker_not_ok(state, leg="ORB", intent="OPEN", side="BUY",
                                shares=5, reason="blocked", log=NOOP)
        qe._alert_broker_not_ok(state, leg="ORB", intent="OPEN", side="BUY",
                                shares=5, reason="blocked again", log=NOOP)
        assert len(pushed) == 1, "a second failure the same leg/day must not page again"
        # a different leg still gets its own alert
        qe._alert_broker_not_ok(state, leg="NOISE", intent="OPEN", side="BUY",
                                shares=5, reason="blocked", log=NOOP)
    assert len(pushed) == 2


def test_alert_broker_not_ok_translates_the_raw_servererror_text(tmp_path, monkeypatch):
    """REVIEW FIX (2026-09-26 review, minor): the push must carry _plain_broker_error's
    one-sentence translation, not the raw ServerException dump (HTTP status, Webull
    code, RequestID) -- that raw text is unreadable on a phone and is already logged by
    the 'NOT ok' log line right above this function's own call site."""
    pushed = []
    state = {"events": []}
    raw = ("ServerException: HTTP Status: 417, Code: "
           "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION_OPEN, Msg: x, RequestID: r1")

    def fake_notify(msg, title, log=print, priority=None):
        pushed.append(msg)

    import unittest.mock as um
    with um.patch.object(qe, "_notify", fake_notify):
        qe._alert_broker_not_ok(state, leg="NOISE", intent="CLOSE", side="SELL",
                                shares=10, reason=raw, log=NOOP)
    assert len(pushed) == 1
    assert "HTTP Status" not in pushed[0] and "RequestID" not in pushed[0]
    assert "already holds the opposite side of QQQ" in pushed[0]


def test_mirror_to_broker_alerts_high_priority_on_close_failure(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    client.order_v3.place_order.side_effect = RuntimeError("network exploded")
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((title, msg, priority)))
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    assert any(p == "high" and "CLOSE NOT OK" in m for _t, m, p in pushed)


def test_mirror_to_broker_does_not_alert_on_confirmed_nothing_to_close(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    # nothing seeded -- the broker never actually held ORB
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((title, msg, priority)))
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    assert not any("NOT OK" in m for _t, m, _p in pushed), \
        "the confirmed-benign nothing-to-close case must not also fire the generic alert"
    assert any("never held it" in m for _t, m, _p in pushed)
    assert client.order_v3.place_order.call_count == 0


def test_orphan_repair_close_does_not_double_alert(tmp_path, monkeypatch):
    """requeue=False (the orphan-broker repair's own retries) must not also fire the
    per-record alert -- that repair already escalates on its own after
    FLATTEN_MAX_TRIES, and paging on every one of its own attempts would be noise."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    client.order_v3.place_order.side_effect = RuntimeError("boom")
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append(msg))
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, requeue=False, log=NOOP)

    assert not any("NOT OK" in m for m in pushed)
    assert state.get("_broker_resend", {}) == {}, "requeue=False must never join the queue either"


# ═════════════ item 2: CLOSE re-send queue (why="close_retry") + backoff ═══════════

def test_close_failure_other_than_duplicate_or_halt_is_queued_close_retry(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    client.order_v3.place_order.side_effect = RuntimeError("network exploded")
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    assert state["_broker_resend"][f"ORB:CLOSE:{ORB_TRADE_ID}"]["why"] == "close_retry"


def test_close_retry_backs_off_then_succeeds(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    # a definite 4xx refusal (item 2 major, SECOND 2026-09-26 review) -- needs_verify is
    # False, so the retry below proceeds on backoff alone, without an order_status
    # lookup; this test is about the BACKOFF timing, not the verification gate.
    client.order_v3.place_order.side_effect = RuntimeError(
        "HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET, "
        "Msg: market not ready, RequestID: r1")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)   # nowhere near the flatten deadline
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1

    # backoff #1 is ~5s -- too soon at +2s
    clock[0] += 2
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 1

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 2, "5s backoff elapsed -- first retry sent"
    assert f"ORB:CLOSE:{ORB_TRADE_ID}" in state["_broker_resend"], "still failing -- stays queued"

    client.order_v3.place_order.side_effect = None   # the outage clears
    clock[0] += 10   # backoff #2 is ~10s
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 3
    assert state.get("_broker_resend") == {}
    assert adapter._state["broker_sent_positions"]["ORB"]["qty"] == 0


def test_close_retry_not_bounded_by_broker_resend_max_tries(tmp_path, monkeypatch):
    """Unlike an OPEN blocked by a duplicate/halt, a close_retry keeps going past
    BROKER_RESEND_MAX_TRIES -- only the session flatten deadline stops it."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    # a definite 4xx refusal (item 2 major, SECOND 2026-09-26 review) -- needs_verify is
    # False, so every retry proceeds on backoff alone; this test is about the retry
    # COUNT never being capped, not the verification gate.
    client.order_v3.place_order.side_effect = RuntimeError(
        "HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET, "
        "Msg: market not ready, RequestID: r1")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)

    for _ in range(qe.BROKER_RESEND_MAX_TRIES + 2):
        clock[0] += 60
        qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert f"ORB:CLOSE:{ORB_TRADE_ID}" in state["_broker_resend"], \
        "must still be retrying well past BROKER_RESEND_MAX_TRIES tries"
    assert client.order_v3.place_order.call_count == 1 + qe.BROKER_RESEND_MAX_TRIES + 2


def test_close_retry_gives_up_at_the_session_flatten_deadline(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("boom")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 15, 58, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)

    past_deadline = qe._session_flatten_deadline(nowdt) + datetime.timedelta(seconds=1)
    clock[0] += 60
    qe._maybe_resend_broker_orders(state, cfg, past_deadline, True, log=NOOP)

    assert state.get("_broker_resend") == {}
    # item 3 (2026-09-26 lead decision): the give-up push for a CLOSE is now "urgent" --
    # Webull may still hold real shares with nobody retrying any more.
    assert any("gave up" in m and "flatten deadline" in m and p == "urgent"
              for m, p in pushed)


def test_close_retry_never_double_sells_when_already_flat(tmp_path, monkeypatch):
    """Re-check the adapter's own believed position before every retry -- if it
    already reads flat for this leg, some other path already closed it; the retry
    must be dropped, never sent."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("boom")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1

    # some other path (a manual sell, the orphan repair) already flattened it
    adapter._state["believed_positions"]["ORB"] = {"symbol": "QQQ", "qty": 0}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1, "must never re-send once already flat"
    assert state.get("_broker_resend") == {}


def test_close_retry_clamps_to_the_believed_qty(tmp_path, monkeypatch):
    """A partial fill (belief now 3, not the originally-requested 5) must clamp the
    retry down, never resend the stale larger amount."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    # a definite 4xx refusal (item 2 major, SECOND 2026-09-26 review) -- needs_verify is
    # False, so the retry proceeds without an order_status lookup; this test is about
    # the believed-qty CLAMP, not the verification gate.
    client.order_v3.place_order.side_effect = RuntimeError(
        "HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET, "
        "Msg: market not ready, RequestID: r1")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)

    adapter._state["believed_positions"]["ORB"] = {"symbol": "QQQ", "qty": 3}
    client.order_v3.place_order.side_effect = None

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 2
    sent_order = client.order_v3.place_order.call_args_list[-1].args[1][0]
    assert sent_order["quantity"] == "3"


# ═══════ item 1 CRITICAL (2026-09-26 review): never blind-resend an unknown-outcome CLOSE ═══════

def test_close_retry_drops_when_webulls_own_record_shows_the_order_landed(tmp_path, monkeypatch):
    """place_stock_order's call to Webull raises (a timeout, or a dropped connection
    AFTER Webull already took the order) -- ok=False but sent=True, and
    believed_positions/broker_sent_positions are NOT rolled back on that path (see
    api.webull_orders.place_stock_order's own per-part try/except), so the believed-
    position re-check alone reads the shares as still held and cannot tell this apart
    from a genuine send failure -- blindly resending risks a real double-sell. Before
    ever re-sending, the adapter's own order_status for the PREVIOUS attempt's
    signal_id must be consulted -- here it says FILLED, so the retry must be dropped,
    never sent, and paged high."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "FILLED"}]}
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1
    assert state["_broker_resend"][f"ORB:CLOSE:{ORB_TRADE_ID}"]["sent"] is True

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1, \
        "must never send a second place_order once Webull's own record shows the first landed"
    assert state.get("_broker_resend") == {}
    assert any("reached the book" in m and p == "high" for m, p in pushed)


def test_close_retry_holds_when_the_order_status_lookup_itself_fails(tmp_path, monkeypatch):
    """Webull's order-status query itself fails (a network blip during the lookup, not
    a definitive answer) -- the retry must be HELD, never sent blind, and must stay
    queued to ask again on the next backoff step."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.side_effect = RuntimeError("order-status query failed too")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1, \
        "must never send blind when the order-status lookup itself fails"
    assert f"ORB:CLOSE:{ORB_TRADE_ID}" in state["_broker_resend"], "must stay queued to try again"


def test_close_retry_holds_on_a_rejected_lookup_no_longer_a_shortcut(tmp_path, monkeypatch):
    """FINAL CLOSE RE-SEND RULE (2026-09-26): a REJECTED lookup only counts as 'dead,
    re-send' when it ALSO carries an EXPLICIT filled quantity -- without one, how much
    landed before the rejection is unknown, so it is unverifiable and must be HELD at
    every backoff step (never released by an account position read, which the lead's
    final decision removed outright)."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "REJECTED"}]}   # no filled_quantity on the record
    client.account_v2.get_account_position.return_value.json.return_value = {
        "data": [{"symbol": "QQQ", "quantity": 5, "side": "LONG"}]}
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
    assert client.order_v3.place_order.call_count == 1, \
        "REJECTED with no filled quantity is unverifiable -- must not re-send"
    assert state["_broker_resend"][key]["verify_holds"] == 1

    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2
    assert client.order_v3.place_order.call_count == 1, \
        "still held at 2 holds -- the account read showing 5 shares never releases it"
    assert state["_broker_resend"][key]["verify_holds"] == 2
    # the stalled push shares the leg's own CLOSE-failure throttle -- the t=0 "NOT OK"
    # push already used this window's budget
    assert len(pushed) == 1


def test_close_retry_skips_the_lookup_when_the_previous_attempt_never_sent(tmp_path, monkeypatch):
    """rec['sent'] False (BLOCKED before send, no client, an adapter ERROR before the
    send) -- the believed-position re-check alone is already safe (place_stock_order
    was never actually called), so no order_status lookup should even be attempted."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": [],
            "_broker_lease_ok": False, "_broker_lease_reason": "lease unverifiable: test"}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 0
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    assert state["_broker_resend"][key]["sent"] is False

    state["_broker_lease_ok"] = True   # the outage clears
    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    client.order_v3.get_order_detail.assert_not_called()
    assert client.order_v3.place_order.call_count == 1


# ═════ item 2 major, 2026-09-26 REVIEW FIX: the real 417/ORDER_NOT_FOUND gap ═════
# The tests above already covered a bare "dropped connection" RuntimeError -- but the
# actual 2026-09-25 incident was FOUR live Webull refusals ("ServerException: HTTP
# Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET"): a definite,
# synchronous "refused" answer, not an ambiguous dropped connection. The adapter still
# records these as sent=True/ok=False (see api.webull_orders.place_stock_order's per-
# part except), so the ORIGINAL code asked Webull's order_status for an order it never
# created -- which answers ORDER_NOT_FOUND, an exception, not a REJECTED status -- and
# treated that "the lookup itself failed" answer as unverifiable, holding the retry
# every backoff step until the session flatten deadline gave up ~6 hours later.
#
# SECOND REVIEW (2026-09-26, MAJOR): the FIRST fix over-corrected -- it trusted
# ORDER_NOT_FOUND/404 (and a successfully-looked-up REJECTED/FAILED status) as a
# POSITIVE "never landed" answer, safe to retry immediately. Neither actually is: a
# just-placed order may not be visible yet at the lookup endpoint, and a 404 can be an
# endpoint/routing error rather than a true absence. _order_known_at_broker may now only
# ever answer "known -> do not resend" or "unverifiable" -- see its own docstring -- and
# the tests below (renamed from "_proceeds_..." to "_holds_...") now confirm ORDER_NOT_
# FOUND/404 and REJECTED are held exactly like a 5xx. FINAL CLOSE RE-SEND RULE
# (2026-09-26 lead decision): nothing but the order lookup itself ever releases the
# hold -- REJECTED/CANCELLED/FAILED only once it carries an EXPLICIT filled quantity --
# and the account-position fallback that used to release it after 2 holds is deleted.

def test_close_retry_skips_the_lookup_after_a_4xx_refusal_and_succeeds(tmp_path, monkeypatch):
    """A 4xx ServerException is Webull answering SYNCHRONOUSLY that it refused this
    order outright -- a definite 'never landed' outcome, not an ambiguous one. No
    order_status verification lookup is needed (there is nothing for Webull to have a
    record of) before the very next retry goes."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError(
        "HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET, "
        "Msg: market not ready, RequestID: r1")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    assert state["_broker_resend"][key]["sent"] is True
    assert state["_broker_resend"][key]["needs_verify"] is False, \
        "a 4xx refusal is a definite outcome -- no verification needed"

    client.order_v3.place_order.side_effect = None   # the outage clears
    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    client.order_v3.get_order_detail.assert_not_called()
    assert client.order_v3.place_order.call_count == 2, \
        "a definite 4xx refusal must retry without ever consulting order_status"


def test_close_retry_holds_on_an_order_not_found_lookup_no_longer_a_shortcut(
        tmp_path, monkeypatch):
    """The actual 2026-09-25 shape: place_order raised (a bare dropped connection, no
    HTTP status of its own) and Webull's get_order_detail answers ORDER_NOT_FOUND --
    reaching order_status() as an EXCEPTION. Not proof the order never landed (it may
    not be visible yet; a 404 can be a routing error): held at every step, and the
    account position is never even read to decide (FINAL CLOSE RE-SEND RULE)."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.side_effect = RuntimeError(
        "ServerException: HTTP Status: 400, Code: ORDER_NOT_FOUND, Msg: no such order, "
        "RequestID: r2")
    client.account_v2.get_account_position.return_value.json.return_value = {
        "data": [{"symbol": "QQQ", "quantity": 5, "side": "LONG"}]}
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    positions_reads = client.account_v2.get_account_position.call_count

    for step in range(1, 5):
        clock[0] += 35
        qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
        assert client.order_v3.place_order.call_count == 1, \
            "ORDER_NOT_FOUND on the lookup must never release a re-send"
        assert state["_broker_resend"][key]["verify_holds"] == step

    assert client.account_v2.get_account_position.call_count == positions_reads, \
        "the hold is decided by the order lookup alone -- never an account position read"
    assert len(pushed) == 1   # throttled: the t=0 push used this window's budget


def test_close_retry_stays_held_on_a_5xx_lookup_failure(tmp_path, monkeypatch):
    """A 5xx/timeout on the order_status lookup itself is genuinely unverifiable
    (unlike ORDER_NOT_FOUND above) -- must stay held, never sent blind."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.side_effect = RuntimeError(
        "ServerException: HTTP Status: 504, Code: GATEWAY_TIMEOUT, Msg: x, RequestID: r3")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    assert client.order_v3.place_order.call_count == 1

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1, "a 5xx lookup failure must stay held"
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    assert key in state["_broker_resend"]
    assert state["_broker_resend"][key]["verify_holds"] == 1


def test_close_retry_stalled_after_two_holds_stays_held_even_when_shares_still_out(
        tmp_path, monkeypatch):
    """2+ consecutive unverifiable holds (a 5xx on every lookup) used to fall back to
    the account position read and re-send when it still showed the shares. FINAL CLOSE
    RE-SEND RULE (2026-09-26): one margin account nets every leg, so that read can never
    say which leg's shares are out -- it stays held (and pages, throttled) however long
    the lookup outage lasts, even though the account still shows ORB's 5 shares."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.side_effect = RuntimeError(
        "ServerException: HTTP Status: 504, Code: GATEWAY_TIMEOUT, Msg: x, RequestID: r4")
    client.account_v2.get_account_position.return_value.json.return_value = {
        "data": [{"symbol": "QQQ", "quantity": 5, "side": "LONG"}]}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    assert len(pushed) == 1, "the very first CLOSE failure must page immediately"

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2

    assert client.order_v3.place_order.call_count == 1, \
        "never re-sent on account arithmetic -- the account read showing 5 is not proof"
    assert key in state["_broker_resend"]
    assert state["_broker_resend"][key]["verify_holds"] == 2
    assert len(pushed) == 1   # inside the t=0 push's own throttle window


# ═ FINAL CLOSE RE-SEND RULE (2026-09-26): an unverifiable CLOSE holds and pages ═
# (replaces the FOURTH review's grace-period test -- the account-position fallback it
# guarded is deleted). Not found on every lookup: held at every step, paged per the
# per-leg throttle (urgent at 2+ holds), given up at the flatten deadline with the
# urgent give-up push.

def test_close_retry_not_found_lookup_holds_pages_urgently_then_gives_up_at_the_deadline(
        tmp_path, monkeypatch):
    """Not found on every lookup -> hold and page: the t=0 failure pages at once (high);
    the 2+-hold stall push fires URGENT, telling the owner to check Webull and sell by
    hand, once the leg's throttle window has passed; the hold never re-sends; at the
    session flatten deadline the retry gives up with its own urgent push."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.side_effect = RuntimeError(
        "ServerException: HTTP Status: 400, Code: ORDER_NOT_FOUND, Msg: no such order, "
        "RequestID: r7")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    assert len(pushed) == 1 and pushed[0][1] == "high", "t=0: pages at once"

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
    assert len(pushed) == 1, "one hold is not a stall yet"

    clock[0] += qe.CLOSE_FAIL_ALERT_GAP_SEC + 1
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2
    assert client.order_v3.place_order.call_count == 1
    assert len(pushed) == 2
    stall_msg, stall_pri = pushed[1]
    assert stall_pri == "urgent"
    assert "stalled" in stall_msg and "check Webull" in stall_msg and "sell by hand" in stall_msg

    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 3
    assert len(pushed) == 2, "throttled again inside the new window"
    assert client.order_v3.place_order.call_count == 1

    past_deadline = qe._session_flatten_deadline(nowdt) + datetime.timedelta(seconds=1)
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, past_deadline, True, log=NOOP)
    assert key not in state["_broker_resend"]
    assert client.order_v3.place_order.call_count == 1, "never re-sent at any point"
    assert any("gave up" in m and "flatten deadline" in m and "sell by hand" in m
               and p == "urgent" for m, p in pushed)


def test_close_retry_not_dropped_on_an_account_read_showing_flat(tmp_path, monkeypatch):
    """The old fallback DROPPED a stalled retry when the account read flat. That read
    cannot say which leg's shares are gone either (FINAL CLOSE RE-SEND RULE), so a flat
    account read neither drops nor sends -- the retry stays held on its order lookup."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.side_effect = RuntimeError(
        "ServerException: HTTP Status: 504, Code: GATEWAY_TIMEOUT, Msg: x, RequestID: r6")
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2

    assert client.order_v3.place_order.call_count == 1, "must not resend"
    assert key in state["_broker_resend"], "a flat account read must not drop it either"
    assert state["_broker_resend"][key]["verify_holds"] == 2


# ═══ item 3 minor (2026-09-26 THIRD review, CONSOLIDATED FOURTH review): the "CLOSE ═══
# retry ... stalled" push must be throttled the same as any other CLOSE-failure push --
# at most once per CLOSE_FAIL_ALERT_GAP_SEC PER LEG TOTAL while retries continue, never
# once per 2-hold episode AND never a second independent stream alongside the plain
# per-send "NOT OK" push. FOURTH REVIEW (2026-09-26, minor): the THIRD review's own fix
# throttled the stalled push against itself via a SEPARATE "<leg>#stall" key, which let
# it still page independently of (and in the same window as) the ordinary "NOT OK" push
# -- up to two pushes per 5 minutes per leg, not the one point 3 of the spec calls for.
# The stalled push now shares the leg's own plain throttle key -- whichever push reaches
# the gate first in a window wins, exactly like two ordinary "NOT OK" pushes would.

def test_close_retry_failure_pushes_throttled_across_many_rebuilt_cycles(tmp_path, monkeypatch):
    """The very first CLOSE failure (t=0, this attempt's own 'NOT OK' push) already uses
    up the leg's per-5-minute budget. Runs several more unverifiable holds afterward --
    each 2+-hold step would, under the OLD separate-budget scheme, add its own
    'stalled' push -- all inside one CLOSE_FAIL_ALERT_GAP_SEC window, and checks for at
    most the ONE push from t=0 throughout, whatever its own wording. Then advances past
    the gap and confirms the still-held CLOSE pages again. (FINAL CLOSE RE-SEND RULE:
    the holds never re-send -- the account-position fallback is deleted.)"""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    client.order_v3.get_order_detail.side_effect = RuntimeError(
        "ServerException: HTTP Status: 504, Code: GATEWAY_TIMEOUT, Msg: x, RequestID: r5")
    client.account_v2.get_account_position.return_value.json.return_value = {
        "data": [{"symbol": "QQQ", "quantity": 5, "side": "LONG"}]}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    assert len(pushed) == 1, "the very first CLOSE failure must page immediately"

    # +35s clears the close-retry backoff (5/10/20/30s, capped at 30s) no matter how far
    # `tries` has climbed by this point, so every call below actually gets processed
    # instead of bouncing off the backoff gate.
    for _ in range(3):   # six more unverifiable holds
        clock[0] += 35
        qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
        assert key in state["_broker_resend"], "outage continues -- must still be queued"
        clock[0] += 35
        qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2+

    assert len(pushed) == 1, \
        "must page at most once per 5 minutes total -- the stalled push and every " \
        "resend's own NOT OK push must share the first failure's own budget"

    clock[0] += qe.CLOSE_FAIL_ALERT_GAP_SEC + 1
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1, fresh episode
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2 -> pages again

    assert len(pushed) == 2, "once the gap elapses, a still-failing CLOSE pages again"


# ═══════ item 4 minor (2026-09-26 review): a close_retry from an earlier day ═══════

def test_close_retry_gives_up_when_left_over_from_an_earlier_trading_day(tmp_path, monkeypatch):
    """A close_retry item queued yesterday (the process was down from before the prior
    day's deadline until after this morning's session start) must never fire today --
    it would start pre-open (Webull refuses a market order then) and keep going into
    the session, an unplanned stale exit."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))
    cfg = _resend_cfg()
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    state = {"legs": {}, "events": [],
            "_broker_resend": {key: {"leg": "ORB", "intent": "CLOSE", "side": "long",
                                     "shares": 5, "shadow_px": 500.0, "ts": "x", "seq": 0,
                                     "trade_id": ORB_TRADE_ID, "why": "close_retry",
                                     "tries": 2, "first_at": 0.0, "last_at": 0.0,
                                     "session_date": "2026-09-25", "sent": False,
                                     "needs_verify": False, "last_signal_id": None}}}
    nowdt = datetime.datetime(2026, 9, 26, 9, 26, 0)

    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 0
    assert key not in state["_broker_resend"]
    # item 3 (2026-09-26 lead decision): the give-up push for a CLOSE is now "urgent".
    assert any("gave up" in m and "earlier trading day" in m and p == "urgent"
              for m, p in pushed)


# ═══ SECOND REVIEW (2026-09-26) of item 4's "alerts in book" hard-timeout work ═══
# item 1 CRITICAL, restated for this fix's own scratch-probe repro: an UNKNOWN timeout
# (S0) queues needs_verify=True/last_signal_id=S0. While S0 is still genuinely hung in
# the background, a retry's own needs_verify check can read Webull as having no record
# of S0 YET (indistinguishable from "never sent" while it is still in flight) and judge
# it safe to try again -- but that very attempt is refused BLOCKED (sent=False) because
# the shared single send-worker still has S0 running. The BLOCKED record alone says
# nothing about S0's own outcome; before this fix, re-queuing from it alone silently
# cleared needs_verify to False and moved last_signal_id to the never-sent retry's own
# id, so the NEXT retry skipped _order_known_at_broker entirely and sent blind.

def test_close_retry_preserves_s0s_unresolved_verify_across_an_inflight_blocked_requeue(
        tmp_path, monkeypatch):
    """S0 times out (UNKNOWN) and stays hung. While its lookup says not found the retry
    is held (FINAL CLOSE RE-SEND RULE -- never released by an account read). A second
    send for the same trade bounces off the hung S0 (BLOCKED, sent=False): that requeue
    must keep S0's own needs_verify/last_signal_id/verify_qty, so the next check still
    asks about S0 -- and once S0 shows FILLED the retry is dropped, never re-sent."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    client.account_v2.get_account_position.return_value.json.return_value = {
        "data": [{"symbol": "QQQ", "quantity": 5, "side": "LONG"}]}   # ORB's shares still out

    send_calls = []

    def fake_send(adapter_arg, *, leg, signal_id, symbol, side, qty, intent, mode, log=print):
        send_calls.append(signal_id)
        if len(send_calls) == 1:
            return {"leg": leg, "symbol": symbol, "side": side, "qty": qty, "intent": intent,
                   "signal_id": signal_id, "client_order_id": signal_id, "mode": mode,
                   "ok": False, "sent": True, "duplicate": False, "outcome": "UNKNOWN",
                   "reason": "broker send timed out after 40s"}
        # every attempt after the first is refused BLOCKED -- S0's own send is still
        # hung in the background (this repro never actually finishes it)
        return {"leg": leg, "symbol": symbol, "side": side, "qty": qty, "intent": intent,
               "signal_id": signal_id, "client_order_id": signal_id, "mode": "BLOCKED",
               "ok": False, "sent": False, "duplicate": False, "inflight_blocked": True,
               "reason": "previous broker send still in flight (hung) -- not queuing "
                        "another send behind it"}
    monkeypatch.setattr(qe, "_place_stock_order_with_timeout", fake_send)

    status_calls = []

    def fake_order_status(signal_id, account_id=None):
        status_calls.append(signal_id)
        if len(status_calls) <= 2:
            # S0 has no record at Webull YET -- unverifiable, never "dead"
            return {"ok": False, "reason": "ServerException: ... ORDER_NOT_FOUND ..."}
        # S0 actually reached the book after all
        return {"ok": True, "response": {"orders": [{"status": "FILLED"}]},
               "client_order_id": signal_id}
    monkeypatch.setattr(adapter, "order_status", fake_order_status)

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    s0 = state["_broker_resend"][key]["last_signal_id"]
    assert state["_broker_resend"][key]["needs_verify"] is True
    assert state["_broker_resend"][key]["verify_qty"] == 5

    # hold 1: order_status(S0) says "not found" -- unverifiable, held, no send
    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    assert status_calls == [s0]
    assert len(send_calls) == 1

    # another send for the same trade bounces off the still-hung S0 (sent=False)
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, resend=1, nowdt=nowdt,
                         log=NOOP)
    assert len(send_calls) == 2
    entry = state["_broker_resend"][key]
    assert entry["needs_verify"] is True, \
        "a not-sent in-flight-blocked requeue must never clear S0's own unresolved verify"
    assert entry["last_signal_id"] == s0, "must still point at S0, not the never-sent id"
    assert entry["verify_qty"] == 5

    # hold 2: still not found -- held, still no re-send
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    assert status_calls == [s0, s0]
    assert len(send_calls) == 2, "an unverifiable S0 never releases a re-send"

    # next check: S0 shows FILLED -- dropped, never re-sent
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    assert status_calls == [s0, s0, s0], "must verify S0 again, not a different id"
    assert len(send_calls) == 2, "must NOT re-send once Webull shows S0 reached the book"
    assert key not in state["_broker_resend"]
    assert any("reached the book" in m and p == "high" for m, p in pushed)


def test_queue_broker_resend_keeps_needs_verify_true_directly(tmp_path, monkeypatch):
    """Narrower unit-level check of the same fix, straight against _queue_broker_resend:
    a not-sent record on top of an existing needs_verify=True entry must never clear
    it, whatever `why` the not-sent record itself would otherwise compute."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    state = {"legs": {}, "events": [],
            "_broker_resend": {f"ORB:CLOSE:{ORB_TRADE_ID}": {
                "leg": "ORB", "intent": "CLOSE", "side": "long", "shares": 5,
                "shadow_px": 500.0, "ts": "x", "seq": 0, "trade_id": ORB_TRADE_ID,
                "why": "close_retry", "tries": 0, "first_at": 0.0, "last_at": 0.0,
                "session_date": "2026-09-26", "sent": True, "needs_verify": True,
                "last_signal_id": "S0", "unresolved_part_ids": None}}}
    blocked_rec = {"ok": False, "sent": False, "mode": "BLOCKED",
                   "reason": "previous broker send still in flight (hung) -- not "
                            "queuing another send behind it"}

    qe._queue_broker_resend(state, blocked_rec, leg="ORB", side="long", shares=5,
                            shadow_px=500.0, intent="CLOSE", ts="x", seq=0,
                            trade_id=ORB_TRADE_ID, resend=1, signal_id="S0R1", log=NOOP)

    entry = state["_broker_resend"][f"ORB:CLOSE:{ORB_TRADE_ID}"]
    assert entry["needs_verify"] is True
    assert entry["last_signal_id"] == "S0"


# ═ item 2 major, SECOND 2026-09-26 review: split (netted) CLOSE verify per part ═
# A netted CLOSE sends each part under its OWN client_order_id (see
# api.webull_orders._part_client_order_id) -- a single combined-text regex can hide one
# part's timeout behind another part's own definite 4xx, and a lookup against the BASE
# id (which a split order never actually sent to Webull) always answers "not found"
# regardless of what the real parts did.

def _split_rec(part1_reason, part2_reason):
    return {"ok": False, "sent": True, "mode": "PAPER", "partial": True,
           "reason": "netted against account position 3: split into 2 broker orders "
                    f"(SELL 3{'' if not part1_reason else f' REFUSED ({part1_reason})'}; "
                    f"SHORT 2{'' if not part2_reason else f' REFUSED ({part2_reason})'})",
           "parts": [
               {"side": "SELL", "qty": 3, "client_order_id": "coidA-1",
                "ok": part1_reason is None, "reason": part1_reason or ""},
               {"side": "SHORT", "qty": 2, "client_order_id": "coidA-2",
                "ok": part2_reason is None, "reason": part2_reason or ""},
           ]}


def test_split_close_needs_verify_judged_per_part_not_the_combined_text(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    state = {"legs": {}, "events": []}
    rec = _split_rec(
        part1_reason="RuntimeError: socket read timed out",   # no HTTP status of its own
        part2_reason="HTTP Status: 417, Code: OPENAPI_SOMETHING, Msg: no, RequestID: r")

    qe._queue_broker_resend(state, rec, leg="ORB", side="long", shares=5, shadow_px=500.0,
                            intent="CLOSE", ts="x", seq=0, trade_id=ORB_TRADE_ID,
                            resend=0, signal_id="coidA", log=NOOP)

    entry = state["_broker_resend"][f"ORB:CLOSE:{ORB_TRADE_ID}"]
    assert entry["needs_verify"] is True
    assert entry["unresolved_part_ids"] == ["coidA-1"], \
        "only the part with no definite 4xx of its own needs verifying"


def test_split_close_needs_verify_false_when_every_refused_part_has_its_own_4xx(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    state = {"legs": {}, "events": []}
    rec = _split_rec(
        part1_reason="HTTP Status: 417, Code: A, Msg: no, RequestID: r1",
        part2_reason="HTTP Status: 417, Code: B, Msg: no, RequestID: r2")

    qe._queue_broker_resend(state, rec, leg="ORB", side="long", shares=5, shadow_px=500.0,
                            intent="CLOSE", ts="x", seq=0, trade_id=ORB_TRADE_ID,
                            resend=0, signal_id="coidA", log=NOOP)

    entry = state["_broker_resend"][f"ORB:CLOSE:{ORB_TRADE_ID}"]
    assert entry["needs_verify"] is False, "every part has its own definite 4xx -- no ambiguity"
    assert entry["unresolved_part_ids"] == []


def test_split_close_retry_holds_while_any_unresolved_part_is_unverifiable(
        tmp_path, monkeypatch):
    """FINAL CLOSE RE-SEND RULE: a split is judged part by part. coidA-1 FILLED is
    known, but coidA-2 is not found -- unverifiable -- so the whole close stays HELD
    (neither dropped on coidA-1's say-so, which would abandon coidA-2's shares, nor
    re-sent), and is asked about again next step."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))
    rec = _split_rec(part1_reason="RuntimeError: dropped connection",
                     part2_reason="RuntimeError: dropped connection")
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"

    qe._queue_broker_resend(state, rec, leg="ORB", side="long", shares=5, shadow_px=500.0,
                            intent="CLOSE", ts="x", seq=0, trade_id=ORB_TRADE_ID,
                            resend=0, signal_id="coidA", nowdt=nowdt, log=NOOP)
    assert state["_broker_resend"][key]["unresolved_part_ids"] == ["coidA-1", "coidA-2"]

    checked = []

    def fake_order_status(signal_id, account_id=None):
        checked.append(signal_id)
        if signal_id == "coidA-2":
            return {"ok": False, "reason": "ServerException: ... ORDER_NOT_FOUND ..."}
        return {"ok": True, "response": {"orders": [{"status": "FILLED"}]},
               "client_order_id": signal_id}
    monkeypatch.setattr(adapter, "order_status", fake_order_status)

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert checked == ["coidA-1", "coidA-2"]
    assert client.order_v3.place_order.call_count == 0
    assert key in state["_broker_resend"], "held, not dropped"
    assert state["_broker_resend"][key]["verify_holds"] == 1
    assert not any("reached the book" in m for m, p in pushed)


def test_split_close_retry_holds_when_every_unresolved_part_reads_rejected(
        tmp_path, monkeypatch):
    """A netted CLOSE's unresolved parts reading REJECTED with NO filled quantity on the
    record are unverifiable (how much landed first is unknown) -- held at every step,
    never re-sent, and never released by the account position read (FINAL CLOSE
    RE-SEND RULE)."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    rec = _split_rec(part1_reason="RuntimeError: dropped connection",
                     part2_reason="RuntimeError: dropped connection")
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"

    qe._queue_broker_resend(state, rec, leg="ORB", side="long", shares=5, shadow_px=500.0,
                            intent="CLOSE", ts="x", seq=0, trade_id=ORB_TRADE_ID,
                            resend=0, signal_id="coidA", nowdt=nowdt, log=NOOP)

    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "REJECTED"}]}   # no filled_quantity on either part
    client.account_v2.get_account_position.return_value.json.return_value = {
        "data": [{"symbol": "QQQ", "quantity": 5, "side": "LONG"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
    assert client.order_v3.place_order.call_count == 0
    assert state["_broker_resend"][key]["verify_holds"] == 1

    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2
    assert client.order_v3.place_order.call_count == 0, \
        "still held -- the account read showing 5 shares never releases it"
    assert state["_broker_resend"][key]["verify_holds"] == 2


# ═ _order_known_at_broker_any (helper backing the split-verify fix just above) ═

def test_order_known_at_broker_any_stops_at_the_first_unverifiable_part(monkeypatch):
    calls = []

    def fake(adapter, sid, log=print):
        calls.append(sid)
        return {"p1": {"verdict": "filled"}, "p2": None, "p3": {"verdict": "filled"}}[sid]
    monkeypatch.setattr(qe, "_order_known_at_broker", fake)

    assert qe._order_known_at_broker_any(None, ["p1", "p2", "p3"], log=NOOP) is None
    assert calls == ["p1", "p2"], "an unverifiable part decides the step -- stop asking"


def test_order_known_at_broker_any_working_wins_over_filled_and_dead(monkeypatch):
    parts = {"p1": {"verdict": "filled"}, "p2": {"verdict": "working"},
             "p3": {"verdict": "dead", "filled": 0}}
    monkeypatch.setattr(qe, "_order_known_at_broker", lambda adapter, sid, log=print: parts[sid])
    out = qe._order_known_at_broker_any(None, ["p1", "p2", "p3"], log=NOOP)
    assert out["verdict"] == "working"
    assert out["parts"] == parts


def test_order_known_at_broker_any_filled_only_when_every_part_filled_else_dead(monkeypatch):
    parts = {"p1": {"verdict": "filled"}, "p2": {"verdict": "filled"},
             "p3": {"verdict": "dead", "filled": 1}}
    monkeypatch.setattr(qe, "_order_known_at_broker", lambda adapter, sid, log=print: parts[sid])
    assert qe._order_known_at_broker_any(None, ["p1", "p2"], log=NOOP)["verdict"] == "filled"
    assert qe._order_known_at_broker_any(None, ["p1", "p3"], log=NOOP)["verdict"] == "dead"
    # a stand-in answering the OLD bare True/False shape is unverifiable, never a verdict
    monkeypatch.setattr(qe, "_order_known_at_broker", lambda adapter, sid, log=print: True)
    assert qe._order_known_at_broker_any(None, ["p1"], log=NOOP) is None
    monkeypatch.setattr(qe, "_order_known_at_broker", lambda adapter, sid, log=print: False)
    assert qe._order_known_at_broker_any(None, ["p1"], log=NOOP) is None


def test_order_known_at_broker_any_empty_ids_is_unverifiable():
    assert qe._order_known_at_broker_any(None, [], log=NOOP) is None
    assert qe._order_known_at_broker_any(None, None, log=NOOP) is None


# ═ FINAL CLOSE RE-SEND RULE (2026-09-26 lead decision): the order lookup decides ═
# Per attempt id (per unresolved part id for a split): FILLED -> drop; still WORKING/
# PENDING -> wait; REJECTED/CANCELLED/FAILED with an EXPLICIT filled quantity -> dead,
# re-send now, only the unfilled remainder; not found / lookup error / missing filled
# quantity -> hold and page. Never an account position read.

def _dropped_close_setup(tmp_path, monkeypatch, shares=5, seeded=5):
    """A dropped-connection CLOSE of `shares` ORB shares (ORB seeded at `seeded`),
    queued as close_retry with needs_verify=True. Returns (adapter, client, state, cfg,
    nowdt, clock, pushed, key)."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", seeded)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    client.order_v3.place_order.side_effect = RuntimeError("dropped connection")
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=shares, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, nowdt=nowdt, log=NOOP)
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    assert state["_broker_resend"][key]["needs_verify"] is True
    assert client.order_v3.place_order.call_count == 1
    return adapter, client, state, cfg, nowdt, clock, pushed, key


def _last_broker_row_shares():
    return _read_csv(qe.BROKER_ORDERS_CSV)[-1]["shares"]


def test_close_retry_resends_at_once_when_the_lookup_reads_rejected_with_zero_filled(
        tmp_path, monkeypatch):
    """REJECTED with an EXPLICIT filled quantity of 0: that order is dead and nothing of
    it landed -- re-send the whole close right away (first verify step, no 2-hold wait)."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "REJECTED", "filled_quantity": "0"}]}
    client.order_v3.place_order.side_effect = None   # the re-send itself goes through

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 2, "dead with 0 filled -- re-send now"
    assert _last_broker_row_shares() == "5"
    assert key not in state["_broker_resend"], "the re-send was accepted -- queue cleared"


def test_close_retry_holds_when_a_rejected_lookup_has_a_blank_filled_quantity(
        tmp_path, monkeypatch):
    """REJECTED whose filled quantity is present but blank/unreadable is the same as
    missing -- unverifiable, held, never re-sent."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "REJECTED", "filled_quantity": ""}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    assert state["_broker_resend"][key]["verify_holds"] == 1


def test_close_retry_partial_terminal_resends_only_the_unfilled_remainder(
        tmp_path, monkeypatch):
    """CANCELLED after 2 of 5 filled: re-send only the 3 that did not fill -- never the
    whole 5 (a 2-share double sell)."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "CANCELLED", "filled_quantity": "2"}]}
    client.order_v3.place_order.side_effect = None

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 2
    assert _last_broker_row_shares() == "3", "only the unfilled remainder goes"
    assert key not in state["_broker_resend"]


def test_close_retry_partial_terminal_remainder_survives_a_failed_resend(
        tmp_path, monkeypatch):
    """Same partial CANCELLED (2 of 5 filled), but the remainder re-send itself fails
    with a definite 4xx -- the requeued item must carry the REMAINDER (3) as its size and
    no stale verify of the old attempt, so the next re-send is 3 again, not 5 and not 1."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "CANCELLED", "filled_quantity": "2"}]}
    client.order_v3.place_order.side_effect = RuntimeError(
        "HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET, "
        "Msg: market not ready, RequestID: r1")

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 2
    entry = state["_broker_resend"][key]
    assert entry["shares"] == 3
    assert entry["needs_verify"] is False, "a definite 4xx at send time needs no lookup"

    client.order_v3.place_order.side_effect = None
    client.order_v3.get_order_detail.reset_mock()
    clock[0] += 60
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    client.order_v3.get_order_detail.assert_not_called()
    assert client.order_v3.place_order.call_count == 3
    assert _last_broker_row_shares() == "3"
    assert key not in state["_broker_resend"]


def test_close_retry_terminal_with_everything_filled_is_dropped(tmp_path, monkeypatch):
    """CANCELLED but its filled quantity already covers the whole close -- nothing left
    to sell, dropped like FILLED, never re-sent."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "CANCELLED", "filled_quantity": "5"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    assert key not in state["_broker_resend"]
    assert any("reached the book" in m and p == "high" for m, p in pushed)


def test_close_retry_waits_while_the_previous_attempt_is_still_working(tmp_path, monkeypatch):
    """SUBMITTED / PENDING / PARTIAL_FILLED at Webull: known, still live -- keep waiting,
    never re-send, not an unverifiable hold (no stall page however long it takes), and
    drop once it shows FILLED."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    for status in ("SUBMITTED", "PENDING", "PARTIAL_FILLED", "SUBMITTED"):
        client.order_v3.get_order_detail.return_value.json.return_value = {
            "orders": [{"status": status, "filled_quantity": "0"}]}
        clock[0] += qe.CLOSE_FAIL_ALERT_GAP_SEC + 1
        qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
        assert client.order_v3.place_order.call_count == 1, f"{status}: must not re-send"
        assert key in state["_broker_resend"]
        assert state["_broker_resend"][key].get("verify_holds", 0) == 0

    assert len(pushed) == 1, "a live order is a known answer -- no stall page"

    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "FILLED", "filled_quantity": "5"}]}
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 1
    assert key not in state["_broker_resend"]


def test_close_retry_dropped_when_the_lookup_reads_filled(tmp_path, monkeypatch):
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "FILLED", "filled_quantity": "5"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    assert key not in state["_broker_resend"]
    assert any("reached the book" in m and p == "high" for m, p in pushed)


def test_close_retry_not_found_holds_and_pages_urgently_at_two_holds(tmp_path, monkeypatch):
    """Not found -> hold (never re-send) and page: with the throttle window clear, the
    second consecutive hold pushes URGENT telling the owner to check Webull and sell by
    hand."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.side_effect = RuntimeError(
        "ServerException: HTTP Status: 404, Code: ORDER_NOT_FOUND, Msg: x, RequestID: r9")
    state["_close_fail_alert"] = {}   # the t=0 push's throttle window is over

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
    assert len(pushed) == 1
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2

    assert client.order_v3.place_order.call_count == 1
    assert key in state["_broker_resend"]
    assert pushed[-1][1] == "urgent"
    assert "check Webull" in pushed[-1][0] and "sell by hand" in pushed[-1][0]


def test_split_close_retry_resends_only_the_dead_parts_unfilled_shares(tmp_path, monkeypatch):
    """Split 3 + 2: coidA-1 (3) REJECTED with 0 filled, coidA-2 (2) FILLED -- re-send
    exactly the 3 that never landed."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    rec = _split_rec(part1_reason="RuntimeError: dropped connection",
                     part2_reason="RuntimeError: dropped connection")
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    qe._queue_broker_resend(state, rec, leg="ORB", side="long", shares=5, shadow_px=500.0,
                            intent="CLOSE", ts="x", seq=0, trade_id=ORB_TRADE_ID,
                            resend=0, signal_id="coidA", nowdt=nowdt, log=NOOP)
    entry = state["_broker_resend"][key]
    assert entry["verify_qty"] == 5
    assert entry["unresolved_part_qty"] == {"coidA-1": 3, "coidA-2": 2}
    assert entry["verify_landed_qty"] == 0

    def fake_order_status(signal_id, account_id=None):
        order = ({"status": "REJECTED", "filled_quantity": "0"} if signal_id == "coidA-1"
                 else {"status": "FILLED", "filled_quantity": "2"})
        return {"ok": True, "response": {"orders": [order]}, "client_order_id": signal_id}
    monkeypatch.setattr(adapter, "order_status", fake_order_status)
    sent = []

    def fake_send(adapter_arg, *, leg, signal_id, symbol, side, qty, intent, mode, log=print):
        sent.append(qty)
        return {"leg": leg, "symbol": symbol, "side": side, "qty": qty, "intent": intent,
               "signal_id": signal_id, "client_order_id": signal_id, "mode": mode,
               "ok": True, "sent": True, "duplicate": False}
    monkeypatch.setattr(qe, "_place_stock_order_with_timeout", fake_send)

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert sent == [3]
    assert key not in state["_broker_resend"]


def test_split_close_retry_dropped_when_every_unresolved_part_filled(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    rec = _split_rec(part1_reason="RuntimeError: dropped connection",
                     part2_reason="RuntimeError: dropped connection")
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    qe._queue_broker_resend(state, rec, leg="ORB", side="long", shares=5, shadow_px=500.0,
                            intent="CLOSE", ts="x", seq=0, trade_id=ORB_TRADE_ID,
                            resend=0, signal_id="coidA", nowdt=nowdt, log=NOOP)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "FILLED"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 0
    assert key not in state["_broker_resend"]


def test_split_close_retry_resends_a_4xx_refused_part_once_the_other_part_filled(
        tmp_path, monkeypatch):
    """Split 3 + 2: part 1 timed out (unresolved), part 2 refused with its own 4xx (never
    landed). Part 1 then reads FILLED -- the close is NOT over: part 2's 2 shares still
    need to go, so exactly 2 are re-sent (never dropped, never 5)."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = _resend_cfg()
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    state = {"legs": {}, "events": []}
    rec = _split_rec(part1_reason="RuntimeError: socket read timed out",
                     part2_reason="HTTP Status: 417, Code: X, Msg: no, RequestID: r")
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    qe._queue_broker_resend(state, rec, leg="ORB", side="long", shares=5, shadow_px=500.0,
                            intent="CLOSE", ts="x", seq=0, trade_id=ORB_TRADE_ID,
                            resend=0, signal_id="coidA", nowdt=nowdt, log=NOOP)
    assert state["_broker_resend"][key]["unresolved_part_ids"] == ["coidA-1"]
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "FILLED"}]}
    sent = []

    def fake_send(adapter_arg, *, leg, signal_id, symbol, side, qty, intent, mode, log=print):
        sent.append(qty)
        return {"leg": leg, "symbol": symbol, "side": side, "qty": qty, "intent": intent,
               "signal_id": signal_id, "client_order_id": signal_id, "mode": mode,
               "ok": True, "sent": True, "duplicate": False}
    monkeypatch.setattr(qe, "_place_stock_order_with_timeout", fake_send)

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert sent == [2]


# ── _order_known_at_broker verdicts, straight against a fake adapter ──

class _FakeStatusAdapter:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    def order_status(self, signal_id, account_id=None):
        if self.exc:
            raise self.exc
        return self.result


def _detail(order, coid="S0"):
    return {"ok": True, "response": {"orders": [order]}, "client_order_id": coid}


def test_order_known_verdicts_filled_working_dead():
    k = qe._order_known_at_broker
    assert k(_FakeStatusAdapter(_detail({"status": "FILLED"})), "S0", log=NOOP) == \
        {"verdict": "filled", "status": "FILLED"}
    for s in ("PENDING", "SUBMITTED", "PARTIAL_FILLED", "PARTIAL FILLED", "submitted"):
        v = k(_FakeStatusAdapter(_detail({"status": s, "filled_quantity": "0"})), "S0", log=NOOP)
        assert v["verdict"] == "working", s
    for s in ("REJECTED", "CANCELLED", "FAILED"):
        v = k(_FakeStatusAdapter(_detail({"status": s, "filled_quantity": "0"})), "S0", log=NOOP)
        assert v == {"verdict": "dead", "status": s, "filled": 0}, s
    v = k(_FakeStatusAdapter(_detail({"status": "CANCELLED", "filledQuantity": 2})), "S0", log=NOOP)
    assert v == {"verdict": "dead", "status": "CANCELLED", "filled": 2}


def test_order_known_verdicts_unverifiable_shapes():
    k = qe._order_known_at_broker
    for order in ({"status": "REJECTED"}, {"status": "REJECTED", "filled_quantity": None},
                  {"status": "FAILED", "filled_quantity": ""},
                  {"status": "CANCELLED", "filled_quantity": "abc"},
                  {"status": "CANCELLED", "filled_quantity": "-1"},
                  {"status": "CANCELLED", "filled_quantity": "1.5"},
                  {"filled_quantity": "0"}, {"status": ""}):
        assert k(_FakeStatusAdapter(_detail(order)), "S0", log=NOOP) is None, order
    assert k(_FakeStatusAdapter({"ok": False, "reason": "ORDER_NOT_FOUND"}), "S0", log=NOOP) is None
    assert k(_FakeStatusAdapter(exc=RuntimeError("504")), "S0", log=NOOP) is None
    assert k(_FakeStatusAdapter("not a dict"), "S0", log=NOOP) is None
    assert k(_FakeStatusAdapter(_detail({"status": "FILLED"})), "", log=NOOP) is None


def test_order_known_never_judges_ours_by_another_orders_record():
    other = _detail({"client_order_id": "OTHER", "status": "REJECTED", "filled_quantity": "0"})
    assert qe._order_known_at_broker(_FakeStatusAdapter(other), "S0", log=NOOP) is None
    ours = _detail({"client_order_id": "S0", "status": "REJECTED", "filled_quantity": "0"})
    assert qe._order_known_at_broker(_FakeStatusAdapter(ours), "S0", log=NOOP)["verdict"] == "dead"


def test_close_resend_remainder_shapes():
    r = qe._close_resend_remainder
    single = {"shares": 5, "verify_qty": 5}
    assert r(single, {"verdict": "filled"}) == 0
    assert r(single, {"verdict": "dead", "filled": 0}) == 5
    assert r(single, {"verdict": "dead", "filled": 2}) == 3
    assert r(single, {"verdict": "dead", "filled": 9}) == 0
    assert r(single, {"verdict": "working"}) is None
    assert r({"shares": 4, "verify_qty": 5}, {"verdict": "dead", "filled": 0}) == 4, \
        "never more than this close asked for"
    assert r({"shares": 5}, {"verdict": "dead", "filled": 1}) == 4, \
        "an item queued before verify_qty existed falls back to its own shares"
    split = {"shares": 5, "verify_qty": 5, "verify_landed_qty": 0,
             "unresolved_part_ids": ["a", "b"], "unresolved_part_qty": {"a": 3, "b": 2}}
    assert r(split, {"verdict": "dead", "parts": {"a": {"verdict": "dead", "filled": 1},
                                                  "b": {"verdict": "filled"}}}) == 2
    missing = dict(split, unresolved_part_qty={"a": 3, "b": None})
    assert r(missing, {"verdict": "dead", "parts": {"a": {"verdict": "dead", "filled": 0},
                                                    "b": {"verdict": "filled"}}}) is None, \
        "a FILLED part of unknown size -- cannot compute, hold"


# ═══════ item 2 minor (2026-09-26 review): re-send queue keyed by trade_id ═══════

def test_close_retry_queue_keeps_the_older_trades_own_retry(tmp_path, monkeypatch):
    """A leg re-enters and its NEW close also fails while the OLDER trade's close_retry
    is still pending (its own retry not yet successful) -- the older lot's own retry
    must not be silently dropped by an overwrite under the same plain key."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 8)
    client.order_v3.place_order.side_effect = RuntimeError("boom")
    state = {"legs": {}, "events": []}
    new_trade_id = "ORB_257-20260926T120000Z-L"

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=3, shadow_px=505.0,
                         intent="CLOSE", ts="x", trade_id=new_trade_id, log=NOOP)

    q = state["_broker_resend"]
    assert f"ORB:CLOSE:{ORB_TRADE_ID}" in q, "the OLDER trade's retry must survive"
    assert f"ORB:CLOSE:{new_trade_id}" in q
    assert q[f"ORB:CLOSE:{ORB_TRADE_ID}"]["shares"] == 5
    assert q[f"ORB:CLOSE:{new_trade_id}"]["shares"] == 3


# ══════════════════ item 3: CLOSE never blocked by lease while serving ═════════════

def _write_serving_lock(out, pid, stamp="2026-09-26 09:00:00"):
    with open(out / "SERVING.lock", "w", encoding="utf-8") as f:
        f.write(f"{pid} {stamp}\n")


def test_close_bypasses_an_unverifiable_lease_while_this_process_serves(tmp_path, monkeypatch):
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    _write_serving_lock(out, os.getpid())
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "lease unverifiable: Firestore read failed"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_called_once()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "PAPER"


def test_open_still_blocked_by_the_same_unverifiable_lease_while_serving(tmp_path, monkeypatch):
    """Item 3 says the gate stays UNCHANGED for an OPEN -- serving standalone must
    never exempt an entry, only an exit."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    _write_serving_lock(out, os.getpid())
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "lease unverifiable: Firestore read failed"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_not_called()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "BLOCKED"


def test_close_still_blocked_without_the_serving_lock(tmp_path, monkeypatch):
    """No local SERVING_LOCK held by this process (the ordinary test/--once shape,
    and every pre-2026-09-14 caller) -- the exemption must never fire, matching the
    pre-existing test_qqq_exec_broker_lease.py behaviour exactly."""
    _patch_qqq_paths(tmp_path, monkeypatch)   # no SERVING.lock written
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "lease unverifiable: Firestore read failed"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_not_called()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "BLOCKED"


def test_close_still_blocked_when_a_different_pid_holds_the_lock(tmp_path, monkeypatch):
    """The lock file exists and is fresh, but for a DIFFERENT process -- this process
    is not the one serving, so the exemption must not apply."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    _write_serving_lock(out, os.getpid() + 1)   # almost certainly not our own pid
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "lease unverifiable: Firestore read failed"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_not_called()


def test_is_serving_standalone_false_by_default():
    assert qe._is_serving_standalone() is False


# ═══ item 3 major (2026-09-26 review): the exemption must NEVER cover a CONFIRMED ═══
# ═══ foreign lease or this process's own confirmed stand-down -- only an outage. ═══

def test_close_still_blocked_by_a_confirmed_fresh_foreign_lease_while_serving(tmp_path, monkeypatch):
    """reason text 'host ... holds a fresh lease (...)' from _check_lease_for_broker
    means ANOTHER host has POSITIVELY taken over and may send the identical CLOSE right
    now -- this must stay BLOCKED even though our own local SERVING_LOCK is held,
    because that lock only arbitrates between two processes on ONE machine, never
    between the PC and the cloud VM."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    _write_serving_lock(out, os.getpid())
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "host 'pc' holds a fresh lease (5s old)"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_not_called()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "BLOCKED"


def test_close_still_blocked_when_this_processs_own_lease_is_confirmed_lost(tmp_path, monkeypatch):
    """send_gate's 'lease lost: ...' (held=False) is THIS process's own confirmed
    stand-down mid-tick, not an outage -- must stay BLOCKED even while serving
    standalone locally."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    _write_serving_lock(out, os.getpid())
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    lease = qe._LeaseHolder()
    lease.begin("uid1")
    lease.end("another host claimed the lease")
    monkeypatch.setattr(qe, "_LEASE", lease)

    state = {"legs": {}}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_not_called()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "BLOCKED"


def test_close_still_exempt_when_this_processs_own_lease_is_merely_unverifiable(tmp_path, monkeypatch):
    """send_gate's OTHER not-ok reason -- held=True but no stamp has landed in
    LEASE_SEND_MAX_AGE_SEC -- is genuinely 'lease unverifiable', an outage, not a
    confirmed stand-down: the exemption must still fire for it while serving."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    _write_serving_lock(out, os.getpid())
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)
    lease = qe._LeaseHolder()
    lease.begin("uid1", time.time() - qe.LEASE_SEND_MAX_AGE_SEC - 5)
    monkeypatch.setattr(qe, "_LEASE", lease)

    state = {"legs": {}}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_called_once()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "PAPER"


def test_close_still_blocked_by_a_foreign_claim_with_an_unreadable_timestamp(tmp_path, monkeypatch):
    """REVIEW FIX (2026-09-26 review, minor, flagged for the lead): _check_lease_for_
    broker's 'lease unverifiable: host X claims the lease but its timestamp is
    missing/unreadable' reason also starts with 'lease unverifiable', but it is a
    FOREIGN claim -- a positive sign another host may genuinely hold it -- not an
    outage on our own side. Must stay BLOCKED even while serving standalone, exactly
    like the CONFIRMED-fresh-foreign-lease reason above."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    _write_serving_lock(out, os.getpid())
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", 5)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": ("lease unverifiable: host 'cloud' claims the lease "
                                    "but its timestamp is missing")}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=ORB_TRADE_ID, log=NOOP)

    client.order_v3.place_order.assert_not_called()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "BLOCKED"


# ═══════════════════ item 4: Webull flat after EOD + summary line ══════════════════

class _FakePositionsAdapter:
    def __init__(self, mode, broker=None, error=None):
        self._mode = mode
        self._broker = broker
        self._error = error

    def effective_mode(self):
        return self._mode, "test"

    def positions(self, account_id=None):
        out = {"believed": {}, "broker": self._broker, "mode": self._mode}
        if self._error:
            out["error"] = self._error
        return out


def test_flat_check_reports_flat_no_push(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter",
                        lambda log=print: _FakePositionsAdapter("PAPER", broker={"QQQ": 0.0}))
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((title, priority)))
    state = {"events": []}

    flat, qty = qe._check_webull_flat_after_eod(state, log=NOOP)

    assert (flat, qty) == (True, 0)
    assert pushed == []


def test_flat_check_reports_not_flat_urgent_push(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter",
                        lambda log=print: _FakePositionsAdapter("PAPER", broker={"QQQ": 7.0}))
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((title, priority)))
    state = {"events": []}

    flat, qty = qe._check_webull_flat_after_eod(state, log=NOOP)

    assert (flat, qty) == (False, 7)
    assert pushed == [("EDGELOG QQQ BROKER NOT FLAT", "urgent")]
    assert "still holds 7 QQQ" in state["events"][-1]["text"]


def test_flat_check_short_position_reports_absolute_shares(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter",
                        lambda log=print: _FakePositionsAdapter("PAPER", broker={"QQQ": -4.0}))
    state = {"events": []}
    flat, qty = qe._check_webull_flat_after_eod(state, log=NOOP)
    assert (flat, qty) == (False, 4)


def test_flat_check_unverifiable_read_failure_pushes_high(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter",
                        lambda log=print: _FakePositionsAdapter("PAPER", broker=None,
                                                                error="RuntimeError: boom"))
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((title, priority)))
    state = {"events": []}

    flat, qty = qe._check_webull_flat_after_eod(state, log=NOOP)

    assert (flat, qty) == (None, None)
    assert pushed == [("EDGELOG QQQ BROKER", "high")]


def test_flat_check_off_mode_nothing_to_check(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakePositionsAdapter("OFF"))
    state = {"events": []}
    flat, qty = qe._check_webull_flat_after_eod(state, log=NOOP)
    assert (flat, qty) == (True, None)


# ═══ item 4 major (2026-09-26 review): adapter.positions() must never hang the tick ═══

class _SlowPositionsAdapter:
    """Never actually returns -- api.webull_orders's own history: this SDK does not
    reliably honour its own timeouts (the shadow thread once hung 10 hours inside
    get_snapshot)."""

    def effective_mode(self):
        return "PAPER", "test"

    def positions(self, account_id=None):
        time.sleep(2.0)   # far longer than the patched timeout below
        return {"believed": {}, "broker": {"QQQ": 0.0}, "mode": "PAPER"}


def test_flat_check_bounded_when_the_positions_read_hangs(monkeypatch):
    monkeypatch.setattr(qe, "RECONCILE_HARD_TIMEOUT_SEC", 0.1)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _SlowPositionsAdapter())
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((title, priority)))
    state = {"events": []}

    start = time.time()
    flat, qty = qe._check_webull_flat_after_eod(state, log=NOOP)
    elapsed = time.time() - start

    assert elapsed < 1.5, "must give up at RECONCILE_HARD_TIMEOUT_SEC, not wait for the call"
    assert (flat, qty) == (None, None)
    assert pushed == [("EDGELOG QQQ BROKER", "high")]


def test_scheduler_skips_when_no_flatten_fired_today(monkeypatch):
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1))
    state = {}
    qe._maybe_check_webull_flat_after_eod(state, {}, datetime.datetime(2026, 9, 26, 16, 10), log=NOOP)
    assert calls == []


def test_scheduler_waits_for_close_retry_or_deadline_then_runs_once(monkeypatch):
    calls = []

    def fake_check(state, log=print):
        calls.append(1)
        return True, 0

    monkeypatch.setattr(qe, "_check_webull_flat_after_eod", fake_check)
    nowdt = datetime.datetime(2026, 9, 26, 15, 59, 0)
    state = {"legs": {}, "flat_by_done_date": "2026-09-26",
            "_last_broker_send_at": time.time() - qe.BROKER_RECONCILE_POST_ORDER_GRACE_SEC - 1,
            "_broker_resend": {"ORB:CLOSE:t1": {"intent": "CLOSE", "why": "close_retry"}}}

    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == [], "must wait while a CLOSE is pending and before the deadline"

    past_deadline = qe._session_flatten_deadline(nowdt) + datetime.timedelta(seconds=1)
    qe._maybe_check_webull_flat_after_eod(state, {}, past_deadline, log=NOOP)
    assert calls == [1]
    assert state["_webull_flat_after_eod"] == {"date": "2026-09-26", "flat": True, "shares": 0}

    # a second call the same day must not run it again
    qe._maybe_check_webull_flat_after_eod(state, {}, past_deadline, log=NOOP)
    assert calls == [1]


def test_scheduler_waits_out_the_grace_period_even_with_no_close_pending(monkeypatch):
    """EXIT SAFETY item 4 major (2026-09-26): the flatten's own CLOSEs are sent in the
    SAME tick as the flatten -- reading Webull's position milliseconds later (before
    even the grace period, let alone a fill) used to fire a false URGENT 'sell by hand'.
    The check must wait BROKER_RECONCILE_POST_ORDER_GRACE_SEC from the last broker send
    even when nothing is left in the re-send queue at all (the CLOSEs came back ok)."""
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1) or (True, 0))
    nowdt = datetime.datetime(2026, 9, 26, 15, 58, 5)
    state = {"legs": {}, "flat_by_done_date": "2026-09-26",
            "_last_broker_send_at": time.time()}   # sent THIS instant

    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == [], "must not read Webull's position before the grace period elapses"


def test_scheduler_runs_after_grace_period_with_no_close_pending(monkeypatch):
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1) or (True, 0))
    nowdt = datetime.datetime(2026, 9, 26, 15, 58, 5)
    state = {"legs": {}, "flat_by_done_date": "2026-09-26",
            "_last_broker_send_at": time.time() - qe.BROKER_RECONCILE_POST_ORDER_GRACE_SEC - 1}

    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == [1]


def test_scheduler_waits_on_a_duplicate_close_too_not_only_close_retry(monkeypatch):
    """A CLOSE still queued as why=='duplicate' (two legs flattening in the same
    instant) must hold the check exactly like a close_retry one -- the old check only
    ever looked at why=='close_retry'."""
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1))
    nowdt = datetime.datetime(2026, 9, 26, 15, 59, 0)
    state = {"legs": {}, "flat_by_done_date": "2026-09-26",
            "_last_broker_send_at": time.time() - qe.BROKER_RECONCILE_POST_ORDER_GRACE_SEC - 1,
            "_broker_resend": {"ORB:CLOSE": {"intent": "CLOSE", "why": "duplicate"}}}

    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == [], "a pending duplicate-CLOSE must hold the check just like close_retry"


def test_scheduler_runs_on_a_kill_day_even_with_no_flat_by(monkeypatch):
    """EXIT SAFETY item 4 major (2026-09-26): a kill-file day never sets
    flat_by_done_date at all -- before this fix the check (and so the EOD summary line)
    never ran on one."""
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1) or (True, 0))
    nowdt = datetime.datetime(2026, 9, 26, 11, 0, 0)
    state = {"legs": {}, "kill_flatten_date": "2026-09-26",
            "_last_broker_send_at": time.time() - qe.BROKER_RECONCILE_POST_ORDER_GRACE_SEC - 1}

    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == [1]


def test_scheduler_waits_while_a_leg_is_still_open_in_the_book_before_the_deadline(monkeypatch):
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1))
    nowdt = datetime.datetime(2026, 9, 26, 15, 59, 0)
    state = {"legs": {"ORB": {"trade_id": "t1"}}, "flat_by_done_date": "2026-09-26",
            "_last_broker_send_at": time.time() - qe.BROKER_RECONCILE_POST_ORDER_GRACE_SEC - 1}

    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == []


def test_scheduler_runs_at_the_deadline_even_with_a_leg_still_open(monkeypatch):
    """EXIT SAFETY item 3 minor (2026-09-26 review): a lot that could not be priced at
    flat_by stays in state['legs'] (_close_all logs 'lot left open' and skips it) --
    before this fix the legs-still-open wait applied even PAST the session flatten
    deadline, so exactly the day something went wrong was the day the Webull-flat check
    (and so the urgent 'not flat' push) never ran at all."""
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1) or (False, 5))
    nowdt = datetime.datetime(2026, 9, 26, 16, 10, 0)
    state = {"legs": {"ORB": {"trade_id": "t1"}}, "flat_by_done_date": "2026-09-26",
            "_last_broker_send_at": time.time() - qe.BROKER_RECONCILE_POST_ORDER_GRACE_SEC - 1}

    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == [1]


def _min_doc(today):
    return {"today": {"trades": [], "realized_pnl": 0.0},
           "parity": {"checked": 0, "failed": 0},
           "feed_days": [{"date": today, "uptime_pct": 1.0}],
           "breaker_tripped": False}


def test_eod_summary_line_flat(monkeypatch):
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append(msg))
    nowdt = datetime.datetime(2026, 9, 25, 16, 10, 0)   # a Friday
    today = nowdt.strftime("%Y-%m-%d")
    state = {"_webull_flat_after_eod": {"date": today, "flat": True, "shares": 0}}
    qe._maybe_send_eod_summary(state, _min_doc(today), nowdt, log=NOOP)
    assert any("Webull flat: yes" in m for m in pushed)


def test_eod_summary_line_not_flat(monkeypatch):
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append(msg))
    nowdt = datetime.datetime(2026, 9, 25, 16, 10, 0)   # a Friday
    today = nowdt.strftime("%Y-%m-%d")
    state = {"_webull_flat_after_eod": {"date": today, "flat": False, "shares": 7}}
    qe._maybe_send_eod_summary(state, _min_doc(today), nowdt, log=NOOP)
    assert any("Webull flat: NO (7 shares)" in m for m in pushed)


def test_eod_summary_line_not_checked_when_never_run_today(monkeypatch):
    """EXIT SAFETY item 4 major (2026-09-26): the old default silently printed 'yes'
    when the check never ran at all (a kill day before this fix, a crash/restart around
    the flatten) -- exactly the false reassurance item 4 exists to prevent. It must now
    say 'not checked' instead of guessing flat."""
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append(msg))
    nowdt = datetime.datetime(2026, 9, 25, 16, 10, 0)   # a Friday
    today = nowdt.strftime("%Y-%m-%d")
    qe._maybe_send_eod_summary({}, _min_doc(today), nowdt, log=NOOP)
    assert any("Webull flat: not checked" in m for m in pushed)


def test_eod_summary_line_not_checked_when_stale_from_a_prior_day(monkeypatch):
    """A verdict left over from a previous day (a crash/restart around the flatten)
    must never be shown as TODAY's answer -- neither its stale 'yes' nor its stale
    'NO'."""
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append(msg))
    nowdt = datetime.datetime(2026, 9, 25, 16, 10, 0)   # a Friday
    today = nowdt.strftime("%Y-%m-%d")
    state = {"_webull_flat_after_eod": {"date": "2026-09-24", "flat": False, "shares": 5}}
    qe._maybe_send_eod_summary(state, _min_doc(today), nowdt, log=NOOP)
    assert any("Webull flat: not checked" in m for m in pushed)
    assert not any("Webull flat: NO" in m for m in pushed)


# ═════════════════════════ item 5: half-day flat_by/last_entry clamp ═══════════════

def _tick_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "CONFIG_PATH", str(out / "config.json"))
    monkeypatch.setattr(qe, "STATE_PATH", str(out / "state.json"))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _tick_cfg():
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["signal_source"] = "engine"
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}
    return cfg


def test_half_day_2026_11_27_clamps_flat_by_and_last_entry(tmp_path, monkeypatch):
    """2026-11-27 (day after Thanksgiving) is a recognised 13:00 ET early close --
    flat_by must land at 12:57 (13:00 - 3min), last_entry at 12:50 (13:00 - 10min),
    never at the bell itself (which used to fire the flatten AFTER the close --
    Webull then refuses it, as happened for real on 09-17/09-18)."""
    _tick_paths(tmp_path, monkeypatch)
    nowdt = datetime.datetime(2026, 11, 27, 10, 0, 0)   # well inside the half-day session
    cfg, state, doc = qe.tick(cfg=_tick_cfg(), state={"legs": {}}, now=nowdt, log=lambda *_: None)
    assert cfg["session"]["flat_by"] == "12:57"
    assert cfg["session"]["last_entry"] == "12:50"


def test_normal_trading_day_session_unchanged(tmp_path, monkeypatch):
    _tick_paths(tmp_path, monkeypatch)
    nowdt = datetime.datetime(2026, 9, 8, 10, 0, 0)   # an ordinary trading Tuesday
    cfg, state, doc = qe.tick(cfg=_tick_cfg(), state={"legs": {}}, now=nowdt, log=lambda *_: None)
    assert cfg["session"]["flat_by"] == qe.DEFAULT_CONFIG["session"]["flat_by"]
    assert cfg["session"]["last_entry"] == qe.DEFAULT_CONFIG["session"]["last_entry"]


def test_hhmm_minus_helper():
    assert qe._hhmm_minus("13:00", 3) == "12:57"
    assert qe._hhmm_minus("13:00", 10) == "12:50"
    assert qe._hhmm_minus("00:05", 10) == "00:00", "clamped at midnight, never negative"


# ═══════════════ item 6: EOD/forced exit prices off the live feed ══════════════════

class _FreshStream:
    def __init__(self, price, age):
        self._price, self._age = price, age

    def is_fresh(self):
        return True

    def last_trade(self):
        return {"price": self._price, "age": self._age}


class _NotFreshStream:
    def is_fresh(self):
        return False

    def last_trade(self):
        raise AssertionError("must not be read when the stream itself is not fresh")


class _BoomStream:
    def is_fresh(self):
        raise RuntimeError("boom")


def test_exit_price_prefers_a_fresh_recent_stream_print(monkeypatch):
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _FreshStream(744.60, 3.0))
    px, src = qe._exit_price_for_leg("NOISE", log=NOOP)
    assert (px, src) == (744.60, "live_stream")


def test_exit_price_falls_back_when_the_print_is_too_old(monkeypatch):
    monkeypatch.setattr(qe, "_qqq_stream_instance",
                        lambda: _FreshStream(744.60, qe.EXIT_LIVE_PRICE_MAX_AGE_SEC + 1))
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (744.92, "engine_cache"))
    px, src = qe._exit_price_for_leg("NOISE", log=NOOP)
    assert (px, src) == (744.92, "engine_cache")


def test_exit_price_falls_back_when_stream_not_fresh(monkeypatch):
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _NotFreshStream())
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (744.92, "engine_cache"))
    px, src = qe._exit_price_for_leg("NOISE", log=NOOP)
    assert (px, src) == (744.92, "engine_cache")


def test_exit_price_falls_back_on_stream_exception(monkeypatch):
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _BoomStream())
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (744.92, "engine_cache"))
    px, src = qe._exit_price_for_leg("NOISE", log=NOOP)   # must not raise
    assert (px, src) == (744.92, "engine_cache")


def test_exit_price_falls_back_when_no_stream_instance(monkeypatch):
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (744.92, "engine_cache"))
    px, src = qe._exit_price_for_leg("NOISE", log=NOOP)
    assert (px, src) == (744.92, "engine_cache")


def test_close_all_records_the_price_source_in_the_trades_csv_exit_reason(tmp_path, monkeypatch):
    """TRADE_COLS has no dedicated price-source column -- it travels in exit_reason
    instead (the base reason word stays first, unchanged, for anything reading it as
    a tag)."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _FreshStream(744.60, 2.0))
    state = {"legs": {}, "_px_source": "test"}
    cfg = dict(qe.DEFAULT_CONFIG, signal_source="engine", shares={"NOISE": 10})
    qe._open_lot(state, cfg, "NOISE", "long", 10, 700.0, 500.0, 0.0, log=NOOP)
    assert "NOISE" in state["legs"]

    qe._close_all(state, cfg, "EOD", quote_fn=None, ratio_fn=None, log=NOOP)

    rows = _read_csv(qe.TRADES_CSV)
    assert rows[-1]["exit_reason"] == "EOD (px: live_stream)"
    assert float(rows[-1]["exit_px"]) == 744.59   # 744.60 less the 1c long-exit slippage


def test_close_all_falls_back_to_bar_close_note_when_stream_absent(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (510.0, "engine_cache"))
    state = {"legs": {}, "_px_source": "test"}
    cfg = dict(qe.DEFAULT_CONFIG, signal_source="engine", shares={"ORB": 5})
    qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)

    qe._close_all(state, cfg, "KILL", quote_fn=None, ratio_fn=None, log=NOOP)

    rows = _read_csv(qe.TRADES_CSV)
    assert rows[-1]["exit_reason"] == "KILL (px: engine_cache)"


# ═══════ FIFTH REVIEW (2026-09-26): remainder vs the adapter's clamp, lookup hygiene,
# ═══════ booking fills from a not-ok send ═══════
# * MAJOR: a timeout-shaped record (no parts, qty = the ASKED size) or a legacy queue
#   entry with no verify_qty must size the remainder against what the adapter actually
#   held for the leg (its CLOSE clamp), never the asked size -- else a 4-share oversell.
# * minor: only DOCUMENTED live statuses read as "working"; anything else (EXPIRED, an
#   unknown string, a numeric status) is unverifiable -> hold and page. A working answer
#   no longer resets the unverifiable-hold count.
# * minor: a timed-out lookup is cancelled and the next lookup is not queued behind it.
# * minor: shares that filled on a not-ok send are booked onto the adapter's own books.

def _timeout_rec(qty=10, coid="S0"):
    return {"leg": "ORB", "symbol": "QQQ", "side": "SELL", "qty": qty, "intent": "CLOSE",
            "signal_id": coid, "client_order_id": coid, "mode": "PAPER", "ok": False,
            "sent": True, "duplicate": False, "outcome": "UNKNOWN",
            "reason": "broker send timed out after 8s -- Webull may or may not have "
                      "received this order, outcome unknown"}


def _held_close_setup(tmp_path, monkeypatch, seeded):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    _seed_sent(adapter, "ORB", seeded)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    pushed = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushed.append((msg, priority)))
    state = {"legs": {}, "events": []}
    nowdt = datetime.datetime(2026, 9, 26, 12, 0, 0)
    return adapter, client, state, _resend_cfg(), nowdt, clock, pushed


def test_close_retry_timeout_record_resends_only_what_the_adapter_held_minus_the_fill(
        tmp_path, monkeypatch):
    """Book lot 10, adapter holds 6 for ORB, the timed-out send actually went out as
    SELL 6 (the adapter's clamp), Webull reads CANCELLED with 4 filled: exactly 2 are
    left -- the re-send must be SELL 2, never SELL 6 (a 4-share oversell that in the
    netted account sells another leg's shares or opens a short)."""
    adapter, client, state, cfg, nowdt, clock, pushed = _held_close_setup(
        tmp_path, monkeypatch, seeded=6)
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    qe._queue_broker_resend(state, _timeout_rec(qty=10), leg="ORB", side="long", shares=10,
                            shadow_px=500.0, intent="CLOSE", ts="x", seq=0,
                            trade_id=ORB_TRADE_ID, resend=0, signal_id="S0", nowdt=nowdt,
                            log=NOOP)
    entry = state["_broker_resend"][key]
    assert entry["needs_verify"] is True
    assert entry["verify_qty"] == 6, "capped at the adapter's own clamp at queue time"
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "CANCELLED", "filled_quantity": "4"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    assert client.order_v3.place_order.call_args_list[-1].args[1][0]["quantity"] == "2"
    assert key not in state["_broker_resend"]
    assert adapter._state["broker_sent_positions"]["ORB"]["qty"] == 0
    assert adapter._state["believed_positions"]["ORB"]["qty"] == 0


def test_close_retry_legacy_entry_without_verify_qty_is_capped_by_the_believed_qty(
        tmp_path, monkeypatch):
    """A queue entry written before verify_qty existed falls back to its own `shares`
    (the ASKED 10) -- the single-order remainder must still be min(10, adapter's 6) - 4
    filled = 2."""
    adapter, client, state, cfg, nowdt, clock, pushed = _held_close_setup(
        tmp_path, monkeypatch, seeded=6)
    key = f"ORB:CLOSE:{ORB_TRADE_ID}"
    state["_broker_resend"] = {key: {
        "leg": "ORB", "intent": "CLOSE", "side": "long", "shares": 10, "shadow_px": 500.0,
        "ts": "x", "seq": 0, "trade_id": ORB_TRADE_ID, "why": "close_retry", "tries": 0,
        "first_at": clock[0], "last_at": clock[0], "session_date": "2026-09-26",
        "sent": True, "needs_verify": True, "last_signal_id": "S0",
        "unresolved_part_ids": None}}
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "CANCELLED", "filled_quantity": "4"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    assert client.order_v3.place_order.call_args_list[-1].args[1][0]["quantity"] == "2"


def test_close_resend_sizes_cap_the_single_order_attempt_by_believed():
    r = qe._close_resend_remainder
    assert r({"shares": 10}, {"verdict": "dead", "filled": 4}, believed=6) == 2
    assert r({"shares": 10, "verify_qty": 10}, {"verdict": "dead", "filled": 4},
             believed=6) == 2
    assert r({"shares": 10, "verify_qty": 10}, {"verdict": "filled"}, believed=6) == 0
    assert r({"shares": 5, "verify_qty": 5}, {"verdict": "dead", "filled": 2},
             believed=None) == 3, "no believed read -- uncapped, as before"
    sizes = qe._close_resend_sizes
    assert sizes({"shares": 10}, {"verdict": "dead", "filled": 4}, believed=6) == (2, 4)
    assert sizes({"shares": 10}, {"verdict": "filled"}, believed=6) == (0, 6)
    split = {"shares": 5, "verify_qty": 5, "verify_landed_qty": 1,
             "unresolved_part_ids": ["a", "b"], "unresolved_part_qty": {"a": 2, "b": 2}}
    assert sizes(split, {"verdict": "dead", "parts": {"a": {"verdict": "dead", "filled": 1},
                                                      "b": {"verdict": "filled"}}}) == (1, 3), \
        "only the unresolved parts' fills are unbooked -- the accepted part already was"
    assert sizes({"shares": 5}, {"verdict": "working"}) == (None, None)


def test_close_retry_partial_dead_books_the_filled_shares_on_the_adapter(tmp_path, monkeypatch):
    """CANCELLED after 2 of 5 filled on a dropped-connection send: the remainder 3 is
    re-sent AND the adapter's own books lose the 2 that filled -- so after the accepted
    re-send the leg reads 0, not a phantom 2."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "CANCELLED", "filled_quantity": "2"}]}
    client.order_v3.place_order.side_effect = None

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert _last_broker_row_shares() == "3"
    assert adapter._state["broker_sent_positions"]["ORB"]["qty"] == 0
    assert adapter._state["believed_positions"]["ORB"]["qty"] == 0
    assert "ORB" not in (adapter._state.get("open_legs") or {})


def test_close_retry_filled_drop_books_the_shares_on_the_adapter(tmp_path, monkeypatch):
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "FILLED", "filled_quantity": "5"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert key not in state["_broker_resend"]
    assert adapter._state["broker_sent_positions"]["ORB"]["qty"] == 0
    assert adapter._state["believed_positions"]["ORB"]["qty"] == 0
    assert not any("FLATTEN_BROKER" in m for m, p in pushed)


def test_close_retry_filled_booking_skipped_and_paged_while_a_send_is_in_flight(
        tmp_path, monkeypatch):
    """A broker send still hung on the send worker holds the adapter lock and may yet
    book the same shares itself -- never force the booking; push that the books are off
    and FLATTEN_BROKER must not be used for the leg until they are corrected."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "FILLED", "filled_quantity": "5"}]}

    class _Hung:
        def done(self):
            return False
    qe._inflight_send["future"] = _Hung()

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert key not in state["_broker_resend"]
    assert adapter._state["broker_sent_positions"]["ORB"]["qty"] == 5, "not forced"
    assert any("FLATTEN_BROKER" in m and p == "high" for m, p in pushed)


def test_order_known_unrecognised_or_garbage_status_is_unverifiable():
    k = qe._order_known_at_broker
    for order in ({"status": "EXPIRED", "filled_quantity": "0"},
                  {"status": "SOMETHING_NEW", "filled_quantity": "0"},
                  {"status": "WORKING"},
                  {"status": 5, "filled_quantity": "0"},
                  {"status": ["SUBMITTED"]}):
        assert k(_FakeStatusAdapter(_detail(order)), "S0", log=NOOP) is None, order


def test_close_retry_expired_status_holds_and_never_resends(tmp_path, monkeypatch):
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "EXPIRED", "filled_quantity": "0"}]}

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    assert state["_broker_resend"][key]["verify_holds"] == 1


def test_close_retry_alternating_working_and_unverifiable_still_pages_at_two_holds(
        tmp_path, monkeypatch):
    """not found -> SUBMITTED -> not found: a working answer in between no longer resets
    the hold count, so the second unverifiable answer pushes urgently."""
    adapter, client, state, cfg, nowdt, clock, pushed, key = _dropped_close_setup(
        tmp_path, monkeypatch)
    state["_close_fail_alert"] = {}
    not_found = RuntimeError(
        "ServerException: HTTP Status: 404, Code: ORDER_NOT_FOUND, Msg: x, RequestID: r9")

    client.order_v3.get_order_detail.side_effect = not_found
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 1
    client.order_v3.get_order_detail.side_effect = None
    client.order_v3.get_order_detail.return_value.json.return_value = {
        "orders": [{"status": "SUBMITTED", "filled_quantity": "0"}]}
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # working
    assert state["_broker_resend"][key]["verify_holds"] == 1
    n_before = len(pushed)
    client.order_v3.get_order_detail.side_effect = not_found
    clock[0] += 35
    qe._maybe_resend_broker_orders(state, cfg, nowdt, True, log=NOOP)   # hold 2

    assert client.order_v3.place_order.call_count == 1
    assert state["_broker_resend"][key]["verify_holds"] == 2
    assert len(pushed) == n_before + 1 and pushed[-1][1] == "urgent"


def test_order_lookup_timeout_is_cancelled_and_the_next_lookup_not_queued_behind_it(
        monkeypatch):
    import threading
    release = threading.Event()
    calls = []

    class _HungStatus:
        def order_status(self, signal_id, account_id=None):
            calls.append(signal_id)
            release.wait(5)
            return _detail({"status": "FILLED"}, coid=signal_id)

    monkeypatch.setattr(qe, "ORDER_STATUS_HARD_TIMEOUT_SEC", 0.2)
    monkeypatch.setitem(qe._order_lookup_timeout_at, "t", 0.0)
    try:
        assert qe._order_known_at_broker(_HungStatus(), "S0", log=NOOP) is None
        assert qe._order_known_at_broker(_HungStatus(), "S1", log=NOOP) is None
        assert len(calls) == 1, "a second lookup must never queue behind the hung one"
    finally:
        release.set()
    fut = qe._order_lookup_inflight.get("future")
    if fut is not None:
        fut.result(timeout=5)
    # inside the cooldown after a timeout, lookups are skipped (one wait per tick)
    assert qe._order_known_at_broker(_HungStatus(), "S1b", log=NOOP) is None
    assert "S1b" not in calls
    qe._order_lookup_timeout_at["t"] = 0.0   # cooldown over
    assert qe._order_known_at_broker(_HungStatus(), "S2", log=NOOP) == \
        {"verdict": "filled", "status": "FILLED"}
    assert qe._order_lookup_inflight.get("future") is None


def test_adapter_apply_unacked_close_fill_moves_toward_zero_never_past_it(tmp_path, monkeypatch):
    import threading
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    _seed_sent(adapter, "ORB", 6)
    _seed_sent(adapter, "NOISE", -3)
    assert adapter.apply_unacked_close_fill("ORB", 4) == {"sent": 4, "believed": 4}
    assert adapter._state["broker_sent_positions"]["ORB"]["qty"] == 2
    assert adapter.apply_unacked_close_fill("ORB", 9) == {"sent": 2, "believed": 2}
    assert adapter._state["believed_positions"]["ORB"]["qty"] == 0
    assert "ORB" not in adapter._state["open_legs"]
    assert adapter.apply_unacked_close_fill("NOISE", 1) == {"sent": 1, "believed": 1}
    assert adapter._state["broker_sent_positions"]["NOISE"]["qty"] == -2
    assert adapter.apply_unacked_close_fill("ENGUQ", 2) == {"sent": 0, "believed": 0}

    held, done = threading.Event(), threading.Event()

    def _hold():
        with adapter._lock:
            held.set()
            done.wait(5)
    t = threading.Thread(target=_hold)
    t.start()
    try:
        held.wait(5)
        assert adapter.apply_unacked_close_fill("NOISE", 1, lock_timeout=0.05) is None
        assert adapter._state["broker_sent_positions"]["NOISE"]["qty"] == -2
    finally:
        done.set()
        t.join(5)
