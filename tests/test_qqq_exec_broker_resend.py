"""Guards around the 2026-09-21 QQQ broker order failures: a blocked buy that never
got retried, and two same-instant sells that collided at Webull.

THE INCIDENT (2026-09-21). A false reconcile mismatch halted new broker entries at
09:42 ET. NOISE entered in the shadow book at 09:45:12 (trade id
NOISE_304-20260921T134000Z-L, 10 shares long at 729.82); its broker BUY was BLOCKED by
that halt. The halt cleared a few seconds later, but nothing re-sent the buy -- so for
the rest of the day the shadow book believed it held NOISE and Webull did not. Worse:
when the book eventually closed NOISE, the old code would have sent a SELL for 10 QQQ
shares Webull never held, because a CLOSE deliberately skips every rail ("never trap a
position") -- on a cash account that is refused at best, and wherever shorting is
allowed it silently opens an untracked short nobody is watching. Separately, at 09:31
that same morning two legs each sent a SELL for 10 QQQ in the same instant (the
orphan-broker repair), and Webull filled one and rejected the other as a duplicate
(HTTP 417 OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK) -- it compares the order
itself, not our client_order_id.

THE FIX, in two layers:
  1. api/webull_orders.py's place_stock_order ("NOTHING TO CLOSE", 2026-09-21): a
     CLOSE is only ever sent to the broker for shares THIS adapter's own
     broker_sent_positions book says it actually put there for that leg. Nothing sent
     -> BLOCKED, record["nothing_to_close"] = True, place_order is never called. A
     CLOSE bigger than what was sent is clamped down to it instead of over-selling
     (or opening an untracked position on the other side).
  2. api/qqq_exec.py's re-send queue (_queue_broker_resend / _maybe_resend_broker_orders,
     driven through _mirror_to_broker's `resend=`/`requeue=` params): an OPEN blocked
     by the adapter's OWN reconcile halt, or ANY order Webull rejected as a
     same-instant duplicate, is queued and tried again later under a fresh
     client_order_id (Webull, and this adapter's own idempotency cache, both refuse a
     reused one) -- one re-send per 5s tick, never in the tick right after the
     failure (BROKER_RESEND_MIN_GAP_SEC), at most BROKER_RESEND_MAX_TRIES times, and
     an OPEN only within BROKER_OPEN_RESEND_WINDOW_MIN minutes of its first try and
     only while the book still holds that exact trade. api/qqq_exec.py's
     _maybe_run_broker_reconcile also starts looking every
     BROKER_RECONCILE_HALTED_RECHECK_SEC seconds (instead of the normal ~5-minute
     periodic cadence) while the adapter's own reconcile halt is on, so a false halt
     clears fast -- a kill-file halt is the owner's and stays on the normal cadence.

HARNESS: same conventions as tests/test_qqq_exec_flatten_orphan.py (helpers copied
LOCALLY below, not imported -- no test in this repo imports from another test
module): a real api.webull_orders.OrderAdapter on tmp_path with the Webull SDK
replaced by a MagicMock client, no network, no real C:\\EdgeLog path (blocked anyway
by tests/conftest.py's live-system guard). qqq_exec's own clock (qe.time.time) is
monkeypatched to a controllable value; api/webull_orders.py reads that very same
stdlib time module, so it sees the same clock without needing its own patch.
"""
import csv
import datetime
import json
from unittest.mock import MagicMock

from api import qqq_exec as qe
from api import webull_orders as WO


NOOP = lambda *a, **k: None  # noqa: E731 -- a log=... sink, matches the harness note

# The lot this whole incident is about: NOISE entered 2026-09-21 09:45:12 ET, 10
# shares long at 729.82, trade id NOISE_304-20260921T134000Z-L.
NOWDT = datetime.datetime(2026, 9, 21, 9, 45, 12)
NOISE_TRADE_ID = "NOISE_304-20260921T134000Z-L"
ENGUQ_TRADE_ID = "ENGUQ_335-20260921T171000Z-L"
ORB_TRADE_ID = "ORB_257-20260921T093100Z-L"


# ── harness (copied from tests/test_qqq_exec_flatten_orphan.py) ────────────────────

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
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]
    }
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _paper_adapter(tmp_path, monkeypatch):
    cfg = _broker_cfg(tmp_path, mode="PAPER")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)
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
    return out


def _broker_rows(out):
    path = out / "broker_orders.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── small extra helpers, specific to this file ──────────────────────────────────────

def _order_dicts(client):
    """The order dict actually handed to place_order(account_id, [order_dict]), in
    call order."""
    return [c.args[1][0] for c in client.order_v3.place_order.call_args_list]


def _seed_sent(adapter, leg, qty, account_id="ACCT1"):
    """As if a real OPEN for `leg` already reached the broker and filled -- mirrors
    broker_sent_positions (what reconcile()/the NOTHING TO CLOSE guard trust) and, for
    realism, believed_positions/open_legs too."""
    adapter._state.setdefault("broker_sent_positions", {})[leg] = {
        "symbol": "QQQ", "qty": qty, "account_id": account_id}
    adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
    if qty:
        adapter._state.setdefault("open_legs", {})[leg] = True


def _dup_error():
    return RuntimeError(
        "HTTP Status: 417, Code: OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK, "
        "Msg: Duplicate Order")


def _noise_state():
    """A shadow book holding exactly the live NOISE lot from the incident."""
    return {"legs": {"NOISE": {"side": "long", "shares_remaining": 10,
                               "entry_px": 729.82, "entry_ts": "2026-09-21 09:45:12",
                               "trade_id": NOISE_TRADE_ID}},
            "events": []}


def _setup(tmp_path, monkeypatch):
    """Common rig for every qqq_exec-level re-send test below: a real PAPER
    OrderAdapter wired in as qqq_exec's broker adapter, BROKER_ORDERS_CSV pointed at a
    private temp dir, a controllable clock (qe.time.time -- webull_orders.py reads the
    same stdlib time module, so it is controlled too), and a captured _notify()
    outbox."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    sent = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print: sent.append((title, msg)))
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = {"session": {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}}
    return cfg, adapter, client, out, sent, clock


# ── adapter guard: NOTHING TO CLOSE (api/webull_orders.py, place_stock_order) ──────

def test_close_blocked_when_nothing_was_sent(tmp_path, monkeypatch):
    """The exact live bug: the book asks to close a leg this adapter never actually
    sent an OPEN for at the broker. Must be refused locally, not sent."""
    adapter, client = _paper_adapter(tmp_path, monkeypatch)

    rec = adapter.place_stock_order(leg="NOISE", signal_id="sig-close-1", symbol="QQQ",
                                    side="SELL", qty=10, intent="CLOSE")

    assert rec["mode"] == "BLOCKED"
    assert rec["ok"] is False
    assert rec["nothing_to_close"] is True
    assert client.order_v3.place_order.call_count == 0
    assert adapter._state.get("broker_sent_positions", {}) == {}
    assert adapter._state.get("believed_positions", {}) == {}


def test_close_goes_through_for_shares_actually_sent(tmp_path, monkeypatch):
    """The normal case: the broker really does hold what the book is closing."""
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    _seed_sent(adapter, "NOISE", 10)

    rec = adapter.place_stock_order(leg="NOISE", signal_id="sig-close-2", symbol="QQQ",
                                    side="SELL", qty=10, intent="CLOSE")

    assert rec["ok"] is True
    assert "nothing_to_close" not in rec
    assert client.order_v3.place_order.call_count == 1
    assert adapter._state["broker_sent_positions"]["NOISE"]["qty"] == 0


def test_close_larger_than_sent_is_clamped_to_sent(tmp_path, monkeypatch):
    """Only 5 shares ever reached the broker for this leg -- a CLOSE for 10 must not
    over-sell (or, on a symbol that allows it, open a short nobody is tracking)."""
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    _seed_sent(adapter, "NOISE", 5)

    rec = adapter.place_stock_order(leg="NOISE", signal_id="sig-close-3", symbol="QQQ",
                                    side="SELL", qty=10, intent="CLOSE")

    assert rec["ok"] is True
    assert rec["qty_requested"] == 10
    assert rec["qty"] == 5
    sent_order = _order_dicts(client)[0]
    assert sent_order["quantity"] == "5"


def test_close_short_goes_through_when_a_short_was_sent(tmp_path, monkeypatch):
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    adapter._state["broker_sent_positions"] = {
        "NOISE": {"symbol": "QQQ", "qty": -10, "account_id": "ACCT1"}}

    rec = adapter.place_stock_order(leg="NOISE", signal_id="sig-close-4a", symbol="QQQ",
                                    side="BUY", qty=10, intent="CLOSE")

    assert rec["ok"] is True
    assert client.order_v3.place_order.call_count == 1


def test_close_short_blocked_when_a_long_was_sent(tmp_path, monkeypatch):
    """side=BUY only closes a SHORT -- a long sent for this leg must not let a BUY
    "close" (which would really just add to the position) through."""
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    adapter._state["broker_sent_positions"] = {
        "NOISE": {"symbol": "QQQ", "qty": 10, "account_id": "ACCT1"}}

    rec = adapter.place_stock_order(leg="NOISE", signal_id="sig-close-4b", symbol="QQQ",
                                    side="BUY", qty=10, intent="CLOSE")

    assert rec["mode"] == "BLOCKED"
    assert rec["nothing_to_close"] is True
    assert client.order_v3.place_order.call_count == 0


def test_off_mode_close_is_not_gated_by_nothing_to_close(tmp_path):
    """OFF mode records a would-be order locally and returns before the broker-side
    guard even runs -- this guard must never change OFF's pre-existing behaviour."""
    cfg = _broker_cfg(tmp_path, mode="OFF")
    adapter = WO.OrderAdapter(config=cfg, log=lambda *a, **k: None)

    rec = adapter.place_stock_order(leg="NOISE", signal_id="sig-close-5", symbol="QQQ",
                                    side="SELL", qty=10, intent="CLOSE")

    assert rec["ok"] is True
    assert rec["mode"] == "OFF"
    assert "nothing_to_close" not in rec


# ── qqq_exec re-send (_mirror_to_broker / _maybe_resend_broker_orders /
#    _maybe_run_broker_reconcile) ───────────────────────────────────────────────────

def test_halted_open_is_queued_then_resent_and_the_close_then_succeeds(tmp_path, monkeypatch):
    """THE LIVE FAILURE, end to end: a reconcile halt blocks NOISE's buy; while still
    halted a resend tick sends nothing; once the halt clears a resend tick puts the
    shares at Webull under a fresh id and tells the owner; the book's later CLOSE then
    finds them there (the NOTHING TO CLOSE guard passes) and a real SELL goes out."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = _noise_state()

    # a false reconcile mismatch halts new entries (broker shows 10 QQQ, this adapter
    # never sent any)
    adapter.reconcile(broker_positions_fn=lambda: {"QQQ": 10.0})
    assert adapter.halt_state()[:2] == (True, "reconcile")

    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=729.82,
                         intent="OPEN", ts="2026-09-21 09:45:12", trade_id=NOISE_TRADE_ID,
                         log=NOOP)
    assert client.order_v3.place_order.call_count == 0, "the halt must block the send"
    assert state["_broker_resend"]["NOISE:OPEN"]["why"] == "halt"

    # still halted -- a resend tick must send nothing
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 0

    # a later reconcile agrees with what this adapter actually sent (nothing) -- clears
    adapter.reconcile(broker_positions_fn=lambda: {})
    assert adapter.halt_state()[0] is False

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    order = _order_dicts(client)[0]
    assert order["client_order_id"] == "qxNOISE30420260921T134000ZLOR1"
    assert order["side"] == "BUY"
    assert order["quantity"] == "10"
    assert state.get("_broker_resend") == {}
    assert any("re-sent and accepted" in msg for _title, msg in sent)

    # the book now closes NOISE -- the guard must see the re-sent shares and let a real
    # sell through instead of silently no-op'ing
    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=731.0,
                         intent="CLOSE", ts="2026-09-21 09:45:12", seq=1,
                         trade_id=NOISE_TRADE_ID, log=NOOP)

    assert client.order_v3.place_order.call_count == 2
    close_order = _order_dicts(client)[1]
    assert close_order["side"] == "SELL"
    assert close_order["quantity"] == "10"
    assert adapter._state["broker_sent_positions"]["NOISE"]["qty"] == 0


def test_close_without_a_resend_tells_the_owner_and_sends_nothing(tmp_path, monkeypatch):
    """If the halt never clears (no resend tick ever runs), the book's later CLOSE must
    still refuse the sell -- and say so, rather than silently doing nothing."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = _noise_state()

    adapter.reconcile(broker_positions_fn=lambda: {"QQQ": 10.0})
    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=729.82,
                         intent="OPEN", ts="2026-09-21 09:45:12", trade_id=NOISE_TRADE_ID,
                         log=NOOP)
    assert "NOISE:OPEN" in state.get("_broker_resend", {})
    sent.clear()

    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=731.0,
                         intent="CLOSE", ts="2026-09-21 09:45:12", seq=1,
                         trade_id=NOISE_TRADE_ID, log=NOOP)

    assert client.order_v3.place_order.call_count == 0, "nothing was ever sent to close"
    assert any("never held it" in msg for _title, msg in sent)
    rows = _broker_rows(out)
    close_rows = [r for r in rows if r["intent"] == "CLOSE"]
    assert len(close_rows) == 1
    assert close_rows[0]["mode"] == "BLOCKED"


def test_kill_file_halt_is_not_queued_for_resend(tmp_path, monkeypatch):
    """A kill-file halt is the owner's decision, not a timing glitch -- it must never
    be auto-retried the way a reconcile halt is."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = _noise_state()
    with open(adapter.cfg["kill_file"], "w", encoding="utf-8") as f:
        f.write("halt\n")

    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=729.82,
                         intent="OPEN", ts="2026-09-21 09:45:12", trade_id=NOISE_TRADE_ID,
                         log=NOOP)

    assert client.order_v3.place_order.call_count == 0
    last = state.get("_broker_last") or {}
    assert last.get("reason", "").startswith("halted: kill file present")
    assert state.get("_broker_resend", {}) == {}


def test_resend_dropped_when_book_closes_trade_first(tmp_path, monkeypatch):
    """The book closed (or otherwise dropped) the trade before Webull ever got the
    buy -- re-sending a stale OPEN at that point would be wrong; the queue entry must
    just be dropped, quietly, not sent."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = _noise_state()

    adapter.reconcile(broker_positions_fn=lambda: {"QQQ": 10.0})
    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=729.82,
                         intent="OPEN", ts="2026-09-21 09:45:12", trade_id=NOISE_TRADE_ID,
                         log=NOOP)
    assert "NOISE:OPEN" in state["_broker_resend"]

    adapter.reconcile(broker_positions_fn=lambda: {})
    del state["legs"]["NOISE"]
    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 0
    assert state.get("_broker_resend") == {}


def test_resend_gives_up_after_the_open_window_passes(tmp_path, monkeypatch):
    """A buy re-sent too late is worse than none at all (a stale price) -- past
    BROKER_OPEN_RESEND_WINDOW_MIN minutes it must be dropped and the owner told."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = _noise_state()

    adapter.reconcile(broker_positions_fn=lambda: {"QQQ": 10.0})
    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=729.82,
                         intent="OPEN", ts="2026-09-21 09:45:12", trade_id=NOISE_TRADE_ID,
                         log=NOOP)
    adapter.reconcile(broker_positions_fn=lambda: {})

    clock[0] += 11 * 60   # BROKER_OPEN_RESEND_WINDOW_MIN is 10
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 0
    assert state.get("_broker_resend") == {}
    assert any("gave up" in msg and "its window passed" in msg for _title, msg in sent)


def test_duplicate_reject_resent_under_a_fresh_client_order_id(tmp_path, monkeypatch):
    """Webull rejected the CLOSE as a same-instant duplicate of another leg's order --
    it was never actually placed, so it must go again (once the minimum gap has
    passed) under a new id, since both Webull and the local idempotency cache refuse a
    reused one."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = {"legs": {}, "events": []}
    _seed_sent(adapter, "ENGUQ", 10)
    client.order_v3.place_order.side_effect = [_dup_error()]

    qe._mirror_to_broker(state, leg="ENGUQ", side="long", shares=10, shadow_px=740.0,
                         intent="CLOSE", ts="x", seq=1, trade_id=ENGUQ_TRADE_ID, log=NOOP)
    assert client.order_v3.place_order.call_count == 1
    assert state["_broker_resend"]["ENGUQ:CLOSE"]["why"] == "duplicate"

    # the very same instant -- the minimum gap must suppress a resend
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 1

    client.order_v3.place_order.side_effect = None   # the collision has cleared
    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 2
    order = _order_dicts(client)[1]
    assert order["client_order_id"] == "qxENGUQ33520260921T171000ZLCR1"
    assert state.get("_broker_resend") == {}
    assert adapter._state["broker_sent_positions"]["ENGUQ"]["qty"] == 0


def test_one_resend_per_tick_across_two_queued_legs(tmp_path, monkeypatch):
    """The 09:31 live regression: two legs' CLOSEs collided as duplicates in the same
    instant. Both get queued, but only ONE goes out per tick -- oldest first -- so a
    resend can never itself collide with another resend."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = {"legs": {}, "events": []}
    _seed_sent(adapter, "ENGUQ", 10)
    _seed_sent(adapter, "ORB", 10)
    client.order_v3.place_order.side_effect = [_dup_error(), _dup_error()]

    qe._mirror_to_broker(state, leg="ENGUQ", side="long", shares=10, shadow_px=740.0,
                         intent="CLOSE", ts="x", seq=1, trade_id=ENGUQ_TRADE_ID, log=NOOP)
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=480.0,
                         intent="CLOSE", ts="x", seq=1, trade_id=ORB_TRADE_ID, log=NOOP)
    assert set(state["_broker_resend"]) == {"ENGUQ:CLOSE", "ORB:CLOSE"}
    assert client.order_v3.place_order.call_count == 2

    client.order_v3.place_order.side_effect = None   # both collisions have cleared

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 3, "exactly one resend this tick"
    assert set(state["_broker_resend"]) == {"ORB:CLOSE"}, "the oldest-queued leg goes first"

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 4
    assert state.get("_broker_resend") == {}


def test_requeue_false_opts_out_of_the_resend_queue(tmp_path, monkeypatch):
    """The orphan-broker repair (_maybe_flatten_orphan_broker) runs its own per-tick
    retries and passes requeue=False -- the same failure must not ALSO land in this
    queue, or one order would be retried by two independent mechanisms at once."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = {"legs": {}, "events": []}
    _seed_sent(adapter, "ORB", 10)
    client.order_v3.place_order.side_effect = [_dup_error()]

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=480.0,
                         intent="CLOSE", ts="x", seq=1, trade_id=ORB_TRADE_ID,
                         requeue=False, log=NOOP)

    assert client.order_v3.place_order.call_count == 1
    assert state.get("_broker_resend", {}) == {}


def test_resend_gives_up_after_max_tries(tmp_path, monkeypatch):
    """A leg that keeps colliding forever must not be hammered at Webull indefinitely
    -- BROKER_RESEND_MAX_TRIES caps it, and the tick that finally gives up must not
    itself send yet another attempt."""
    cfg, adapter, client, out, sent, clock = _setup(tmp_path, monkeypatch)
    state = {"legs": {}, "events": []}
    _seed_sent(adapter, "ORB", 10)
    client.order_v3.place_order.side_effect = _dup_error()   # every call raises

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=480.0,
                         intent="CLOSE", ts="x", seq=1, trade_id=ORB_TRADE_ID, log=NOOP)
    assert client.order_v3.place_order.call_count == 1

    for _ in range(qe.BROKER_RESEND_MAX_TRIES):
        clock[0] += 5
        qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)
    assert client.order_v3.place_order.call_count == 1 + qe.BROKER_RESEND_MAX_TRIES == 4
    assert "ORB:CLOSE" in state["_broker_resend"], "not popped yet -- the NEXT tick gives up"

    clock[0] += 5
    qe._maybe_resend_broker_orders(state, cfg, NOWDT, True, log=NOOP)

    assert client.order_v3.place_order.call_count == 4, "the give-up tick sends nothing more"
    assert state.get("_broker_resend") == {}
    assert any("gave up" in msg for _title, msg in sent)


def test_halted_recheck_cadence_vs_normal_periodic_cadence(monkeypatch):
    """_maybe_run_broker_reconcile looks every BROKER_RECONCILE_HALTED_RECHECK_SEC (30s)
    while the adapter's OWN reconcile halt is on, so a false halt (like the one behind
    this whole file) clears fast -- but a kill-file halt is the owner's and stays on
    the normal ~5-minute periodic cadence, same as no halt at all."""
    clock = [2_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = {}
    t0 = clock[0]

    class _FakeAdapter:
        def __init__(self, halt_tuple):
            self._halt_tuple = halt_tuple
            self.calls = 0

        def effective_mode(self):
            return "PAPER", "test"

        def reconcile(self):
            self.calls += 1
            return {"ok": False, "mismatches": [], "checked_at": 0}

        def halt_state(self):
            return self._halt_tuple

    # a reconcile halt -- re-checked every 30s, well inside the normal 5-minute cadence
    adapter = _FakeAdapter((True, "reconcile", "x"))
    state = {"_last_broker_reconcile_at": t0, "events": []}
    clock[0] = t0 + 31
    qe._maybe_run_broker_reconcile(state, cfg, adapter, NOWDT, True, log=NOOP)
    assert adapter.calls == 1, "31s into a reconcile halt must already re-check"

    # a kill-file halt is the owner's -- no fast re-check
    adapter = _FakeAdapter((True, "kill_file", "x"))
    state = {"_last_broker_reconcile_at": t0, "events": []}
    clock[0] = t0 + 31
    qe._maybe_run_broker_reconcile(state, cfg, adapter, NOWDT, True, log=NOOP)
    assert adapter.calls == 0, "a kill-file halt does not get the fast re-check"

    # not halted at all -- the normal ~5 minute periodic cadence applies
    adapter = _FakeAdapter((False, None, None))
    state = {"_last_broker_reconcile_at": t0, "events": []}
    clock[0] = t0 + 31
    qe._maybe_run_broker_reconcile(state, cfg, adapter, NOWDT, True, log=NOOP)
    assert adapter.calls == 0, "31s is too soon for the normal cadence"
    clock[0] = t0 + 301
    qe._maybe_run_broker_reconcile(state, cfg, adapter, NOWDT, True, log=NOOP)
    assert adapter.calls == 1, "301s clears the normal 5-minute cadence"
