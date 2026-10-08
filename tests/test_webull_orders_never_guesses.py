"""THE ORDER PATH NEVER GUESSES (2026-09-26, WEBULL_PAPER_TODO item 17 / go-live 1.5 +
3.5) -- api.webull_orders.OrderAdapter's SEND side and its api/qqq_exec.py glue:

  1. every broker part is recorded PENDING (state["order_parts"]) before it is sent; a
     send that raises is looked up by client_order_id before anything is decided; an
     answer that stays unclear is outcome "UNKNOWN" (part AND record) and stays PENDING
     until reconcile()'s PENDING pass settles it -- never "not placed";
  2. an acknowledgement is not a fill: fill capture hands Webull's status + filled
     quantity to apply_order_outcome (REJECTED/CANCELLED/FAILED roll back, a partial
     keeps only the filled shares) and qqq_exec pushes once, high;
  3. a split order's part 2 goes only after part 1 reports FILLED; otherwise (or when
     part 2 is refused) the rest comes back in record["unsent_parts"] and qqq_exec
     re-queues it (a CLOSE through close_retry, an OPEN once, then a push);
  4. part records older than 7 days are pruned.

FakeClient below scripts Webull: place_order behaviours in order ("ack" = SUBMITTED,
"filled" = FILLED, or an exception to raise) and get_order_detail answers per
client_order_id (a list, the last one repeating; "*" is the fallback for any id).
No real SDK, network or credentials anywhere; tests/conftest.py makes the order path's
own waits instant (webull_orders._sleep).
"""
import datetime
import json
from unittest.mock import MagicMock

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731
TID = "ORB_257-20260926T093100Z-L"
REFUSED_417 = "ServerException: HTTP Status: 417, Code: OPENAPI_TEST_REFUSAL, Msg: no"


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def od(status, filled):
    return {"status": status, "filled_quantity": str(filled)}


class FakeClient:
    def __init__(self):
        self.place = []            # behaviours, consumed in order ("ack" when empty)
        self.detail = {}           # client_order_id -> list of answers
        self.sent = []             # (client_order_id, side, qty) per place_order call
        self.detail_calls = []
        self.positions = []
        self.account_v2 = MagicMock()
        self.account_v2.get_account_list.return_value.json.return_value = {
            "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
        self.account_v2.get_account_position.side_effect = (
            lambda acct: _Resp({"data": list(self.positions)}))
        self.order_v3 = MagicMock()
        self.order_v3.place_order.side_effect = self._place
        self.order_v3.get_order_detail.side_effect = self._detail

    def _place(self, account_id, orders):
        o = orders[0]
        self.sent.append((o["client_order_id"], o["side"], int(o["quantity"])))
        b = self.place.pop(0) if self.place else "ack"
        if isinstance(b, Exception):
            raise b
        filled = b == "filled"
        return _Resp({"client_order_id": o["client_order_id"], "orders": [{
            "client_order_id": o["client_order_id"],
            "status": "FILLED" if filled else "SUBMITTED",
            "filled_quantity": o["quantity"] if filled else "0",
            "filled_price": "500.0" if filled else None}]})

    def _detail(self, account_id, coid):
        self.detail_calls.append(coid)
        answers = self.detail.get(coid) or self.detail.get("*") or [RuntimeError("ORDER_NOT_FOUND")]
        a = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(a, Exception):
            raise a
        return _Resp({"client_order_id": coid, "orders": [dict(a, client_order_id=coid)]})


def _adapter(tmp_path, monkeypatch):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"].update(session_start="00:00", session_end="23:59",
                        max_shares_per_leg=100, max_total_position_shares=500)
    for k, name in (("state_path", "state.json"), ("paper_keys_path", "paper_keys.json"),
                    ("live_keys_path", "live_keys.json"), ("arm_live_file", "ARM_LIVE"),
                    ("kill_file", "KILL")):
        cfg[k] = str(tmp_path / name)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    fake = FakeClient()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: fake)
    return adapter, fake


def _seed(adapter, leg, qty):
    adapter._state.setdefault("broker_sent_positions", {})[leg] = {
        "symbol": "QQQ", "qty": qty, "account_id": "ACCT1"}
    adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
    adapter._state.setdefault("open_legs", {})[leg] = True


def _sent(adapter, leg):
    return (adapter._state.get("broker_sent_positions") or {}).get(leg, {}).get("qty", 0)


def _believed(adapter, leg):
    return (adapter._state.get("believed_positions") or {}).get(leg, {}).get("qty", 0)


def _place(adapter, leg="ORB", signal="S1", side="BUY", qty=5, intent="OPEN", **kw):
    return adapter.place_stock_order(leg=leg, signal_id=signal, symbol="QQQ", side=side,
                                     qty=qty, intent=intent, **kw)


def _no_duplicate_ids(fake):
    ids = [s[0] for s in fake.sent]
    assert len(ids) == len(set(ids)), f"a client_order_id was sent twice: {ids}"


# ── 1. unknown send outcome, resolved by lookup ────────────────────────────────────

def test_unclear_send_found_filled_by_lookup_counts_as_sent(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.place = [RuntimeError("Read timed out")]
    fake.detail["S1"] = [RuntimeError("not visible yet"), od("FILLED", 5)]

    rec = _place(adapter)

    assert rec["ok"] is True and rec.get("outcome") is None
    assert rec["parts"][0]["resolved_by_lookup"] == "FILLED"
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (5, 5)
    assert adapter.status()["pending_parts"] == []
    assert len(fake.sent) == 1 and fake.detail_calls == ["S1", "S1"]


def test_unclear_send_found_dead_with_nothing_filled_is_not_unknown(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.place = [RuntimeError("connection reset")]
    fake.detail["S1"] = [od("REJECTED", 0)]

    rec = _place(adapter)

    assert rec["ok"] is False and rec.get("outcome") is None
    assert rec["parts"][0]["outcome"] == "REJECTED"
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (0, 0)
    assert "ORB" not in adapter._state.get("open_legs", {})
    assert adapter.status()["pending_parts"] == []


def test_unclear_send_found_dead_after_a_partial_fill_books_only_the_fill(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.place = [RuntimeError("HTTP Status: 503, gateway")]
    fake.detail["S1"] = [od("CANCELLED", 2)]

    rec = _place(adapter)

    assert rec["ok"] is False and rec["parts"][0]["outcome"] == "CANCELLED"
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (2, 2)


def test_still_unclear_send_is_unknown_and_stays_pending(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.place = [RuntimeError("Read timed out")]
    fake.detail["S1"] = [RuntimeError("ORDER_NOT_FOUND")]

    rec = _place(adapter)

    assert rec["ok"] is False and rec["sent"] is True
    assert rec["outcome"] == "UNKNOWN" and rec["parts"][0]["outcome"] == "UNKNOWN"
    assert fake.detail_calls == ["S1"] * WO.UNKNOWN_LOOKUP_TRIES
    assert adapter.status()["pending_parts"] == ["S1"]
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (0, 0)
    # the same signal again is the cached record -- never a second send
    again = _place(adapter)
    assert again["duplicate"] is True and len(fake.sent) == 1
    # qqq_exec reads it as UNKNOWN, never as a plain refusal
    assert qe._is_unknown_outcome(rec) and qe._broker_row_outcome(rec) == "UNKNOWN"


def test_a_definite_4xx_refusal_is_not_looked_up_or_left_pending(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.place = [RuntimeError(REFUSED_417)]

    rec = _place(adapter)

    assert rec["ok"] is False and rec.get("outcome") is None
    assert fake.detail_calls == []
    assert adapter.status()["pending_parts"] == []


def test_pending_entry_is_on_disk_before_the_order_is_sent(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    seen = {}

    def place(account_id, orders):
        with open(adapter._state_path(), encoding="utf-8") as f:
            disk = json.load(f)
        seen["part"] = disk["order_parts"]["S1"]
        seen["record"] = disk["orders"]["S1"]
        raise RuntimeError("process dies here")

    fake.order_v3.place_order.side_effect = place
    _place(adapter)

    assert seen["part"]["pending"] is True and seen["part"]["booked"] == 0
    assert seen["record"]["outcome"] == "UNKNOWN"   # a restart can never re-send it
    # ... and a fresh adapter on the same state file refuses to send the signal again
    fresh = WO.OrderAdapter(config=adapter.cfg, log=NOOP)
    monkeypatch.setattr(fresh, "_build_client", lambda mode: fake)
    assert _place(fresh)["duplicate"] is True


# ── 1b. reconcile settles leftover PENDING parts ───────────────────────────────────

def test_reconcile_resolves_leftover_pending_parts(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.place = [RuntimeError("timeout")] * 3
    for leg, sig in (("ORB", "A"), ("NOISE", "B"), ("ENGUQ", "C")):
        fake.detail[sig] = [RuntimeError("not found")]
        assert _place(adapter, leg=leg, signal=sig, qty=1)["outcome"] == "UNKNOWN"
    assert adapter.status()["pending_parts"] == ["A", "B", "C"]

    fake.detail["A"] = [od("FILLED", 1)]            # it did land
    fake.detail["B"] = [od("CANCELLED", 0)]         # dead, nothing filled
    fake.detail["C"] = [RuntimeError("not found")]  # still unclear
    fake.positions = [{"symbol": "QQQ", "quantity": 1, "side": "LONG"}]
    fake.detail_calls.clear()

    for n in (1, 2, 3):                 # review note 3: ONE lookup per reconcile() pass
        result = adapter.reconcile()
        assert len(fake.detail_calls) == n

    assert result["ok"] is True, result
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (1, 1)
    assert _sent(adapter, "NOISE") == 0 and _sent(adapter, "ENGUQ") == 0
    assert adapter.status()["pending_parts"] == ["C"]
    assert len(fake.sent) == 3


def test_close_resend_verify_never_double_books_a_fill_reconcile_already_booked(
        tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)                            # a partial close of 5 of 10
    fake.place = [RuntimeError("timeout")]
    fake.detail["X"] = [RuntimeError("not found")]
    assert _place(adapter, signal="X", side="SELL", intent="CLOSE")["outcome"] == "UNKNOWN"

    fake.detail["X"] = [od("FILLED", 5)]
    fake.positions = [{"symbol": "QQQ", "quantity": 5, "side": "LONG"}]
    assert adapter.reconcile()["ok"] is True             # PENDING pass books the sell
    assert _sent(adapter, "ORB") == 5

    # qqq_exec's close re-send later verifies the same order FILLED and books it
    applied = adapter.apply_unacked_close_fill(
        "ORB", 5, part_outcomes={"X": {"status": "FILLED"}})
    assert applied == {"sent": 0, "believed": 0}
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (5, 5)


# ── 2. acknowledgement is not a fill ───────────────────────────────────────────────

def test_fill_capture_rolls_back_rejected_and_keeps_a_live_partial_in_full(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    assert _place(adapter, signal="R", qty=10)["ok"] is True       # ack SUBMITTED
    assert _sent(adapter, "ORB") == 10

    out = adapter.apply_order_outcome("R", "REJECTED", "0")
    assert out["final"] is True and out["filled"] == 0
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (0, 0)
    assert "ORB" not in adapter._state["open_legs"]
    assert adapter.apply_order_outcome("R", "REJECTED", "0") is None   # idempotent

    # a live PARTIAL_FILLED is never trimmed: the rest may still fill (2026-09-26 review)
    assert _place(adapter, leg="NOISE", signal="P", qty=10)["ok"] is True
    assert adapter.apply_order_outcome("P", "PARTIAL FILLED", "4") is None
    assert _sent(adapter, "NOISE") == 10
    assert adapter.apply_order_outcome("P", "FILLED", "10") is None
    assert _sent(adapter, "NOISE") == 10 and adapter.status()["pending_parts"] == []

    assert _place(adapter, leg="ENGUQ", signal="C", qty=10)["ok"] is True
    adapter.apply_order_outcome("C", "CANCELLED", "3")
    assert (_sent(adapter, "ENGUQ"), _believed(adapter, "ENGUQ")) == (3, 3)
    # a dead status with no filled quantity never guesses: nothing moves, kept pending
    assert _place(adapter, leg="KEEL", signal="D", qty=10)["ok"] is True
    assert adapter.apply_order_outcome("D", "FAILED", None) is None
    assert _sent(adapter, "KEEL") == 10 and "D" in adapter.status()["pending_parts"]


def _patch_qqq(tmp_path, monkeypatch, adapter):
    out = tmp_path / "qqq_out"
    out.mkdir(exist_ok=True)
    for name, fn in (("OUT_DIR", ""), ("ORDERS_CSV", "orders.csv"),
                     ("TRADES_CSV", "trades.csv"), ("BROKER_ORDERS_CSV", "broker_orders.csv"),
                     ("SERVING_LOCK", "SERVING.lock")):
        monkeypatch.setattr(qe, name, str(out / fn) if fn else str(out))
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    pushed = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        pushed.append((msg, priority)))
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    return pushed, clock


def test_qqq_fill_capture_pushes_once_when_webull_rejects_an_acked_order(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    # the book still holds the trade (10-08 review: else the note is group D, default)
    state = {"legs": {"ORB": {"trade_id": TID, "side": "long", "shares_remaining": 10}},
             "events": []}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    assert _sent(adapter, "ORB") == 10 and "ORB:OPEN" in state["_broker_fill_capture"]

    fake.detail["*"] = [od("REJECTED", 0)]
    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 1
    qe._maybe_capture_broker_fills(state, {}, None, True, log=NOOP)

    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (0, 0)
    # WEBULL PUSH PLAN 10-07 group B (10-08 review): the strategy's trade did not happen
    # at Webull -- trading affected, high, in plain words
    high = [m for m, p in pushed if p == "high" and "Webull rejected the ORB buy" in m]
    assert len(high) == 1 and "Trading: AFFECTED" in high[0]
    assert not any(" a ORB" in m for m, _p in pushed)
    assert state["_broker_fill_capture"] == {}          # dead: no price will ever come
    clock[0] += 60
    qe._maybe_capture_broker_fills(state, {}, None, True, log=NOOP)
    assert len([m for m, p in pushed if p == "high"]) == 1
    assert len(fake.sent) == 1


# ── 3. split orders wait for part 1 ────────────────────────────────────────────────

def _split_open(tmp_path, monkeypatch):
    """NOISE holds -4 at the account, so an ORB BUY 10 splits BUY 4 (cover) + BUY 6."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    return adapter, fake, WO._part_client_order_id("S1", 1, 2), WO._part_client_order_id("S1", 2, 2)


def test_split_sends_part2_only_after_part1_reports_filled(tmp_path, monkeypatch):
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.detail[p1] = [od("SUBMITTED", 0), od("FILLED", 4)]

    rec = _place(adapter, qty=10)

    assert [s[0] for s in fake.sent] == [p1, p2]
    assert fake.detail_calls == [p1, p1]
    assert rec["ok"] is True and "unsent_parts" not in rec
    assert _sent(adapter, "ORB") == 10


def test_split_part1_ack_filled_needs_no_poll(tmp_path, monkeypatch):
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.place = ["filled", "ack"]

    assert _place(adapter, qty=10)["ok"] is True
    assert fake.detail_calls == [] and [s[0] for s in fake.sent] == [p1, p2]


def test_split_part1_not_filled_in_time_returns_part2_unsent(tmp_path, monkeypatch):
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.detail[p1] = [od("SUBMITTED", 0)]

    rec = _place(adapter, qty=10)

    assert [s[0] for s in fake.sent] == [p1]
    assert fake.detail_calls == [p1] * WO.SPLIT_FILL_POLL_TRIES
    assert rec["ok"] is False
    assert rec["parts"][0]["ok"] is False and rec["parts"][0]["outcome"] == "WORKING"
    assert rec["unsent_parts"] == [{"side": "BUY", "qty": 6, "client_order_id": p2}]
    assert rec["parts"][1]["sent"] is False and rec["parts"][1]["outcome"] == "NOT_SENT"
    assert adapter.status()["pending_parts"] == [p1]   # reconcile keeps asking about it
    assert _sent(adapter, "ORB") == 4                  # part 1 still counts in full


def test_split_part1_rejected_during_the_wait_is_rolled_back(tmp_path, monkeypatch):
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.detail[p1] = [od("REJECTED", 0)]

    rec = _place(adapter, qty=10)

    assert fake.detail_calls == [p1]                   # a terminal status stops the poll
    assert rec["parts"][0]["ok"] is False and rec["parts"][0]["outcome"] == "REJECTED"
    # the WHOLE unfilled quantity comes back, part 1's included (2026-09-26 review)
    assert [(u["client_order_id"], u["qty"]) for u in rec["unsent_parts"]] == [(p1, 4), (p2, 6)]
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (0, 0)
    assert len(fake.sent) == 1


def test_split_part1_unclear_send_holds_part2_back(tmp_path, monkeypatch):
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.place = [RuntimeError("timeout")]

    rec = _place(adapter, qty=10)

    assert rec["outcome"] == "UNKNOWN" and [s[0] for s in fake.sent] == [p1]
    assert [u["client_order_id"] for u in rec["unsent_parts"]] == [p2]


def test_split_part2_refused_is_returned_unsent(tmp_path, monkeypatch):
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.place = ["filled", RuntimeError(REFUSED_417)]

    rec = _place(adapter, qty=10)

    assert [u["client_order_id"] for u in rec["unsent_parts"]] == [p2]
    assert rec["partial"] is True and _sent(adapter, "ORB") == 4


# ── 3b. qqq_exec re-queues the unsent rest ─────────────────────────────────────────

def _resend(state, clock, gap):
    clock[0] += gap
    qe._maybe_resend_broker_orders(
        state, {"session": {"open": "09:31", "last_entry": "15:55", "flat_by": "15:58"}},
        datetime.datetime(2026, 9, 26, 12, 0, 0), True, log=NOOP)


def test_qqq_open_split_remainder_is_resent_once(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["filled", RuntimeError(REFUSED_417), "filled"]
    state = {"legs": {"ORB": {"trade_id": TID, "shares_remaining": 10}}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    item = state["_broker_resend"]["ORB:OPEN"]
    assert (item["why"], item["shares"]) == ("remainder", 6)

    _resend(state, clock, qe.BROKER_RESEND_MIN_GAP_SEC + 1)

    assert [(s[1], s[2]) for s in fake.sent] == [("BUY", 4), ("BUY", 6), ("BUY", 6)]
    assert _sent(adapter, "ORB") == 10 and state["_broker_resend"] == {}
    # WEBULL PUSH PLAN 10-07 group E: the remainder re-sent and accepted is timeline only,
    # and the refused part 2 waits for that re-send (10-08 review): no push at all
    assert any("re-sent and accepted" in e["text"] for e in state["events"])
    assert pushed == []
    _resend(state, clock, 60)
    assert len(fake.sent) == 3
    _no_duplicate_ids(fake)


def test_qqq_open_split_remainder_failing_again_pushes_and_stops(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["filled", RuntimeError(REFUSED_417), RuntimeError(REFUSED_417)]
    state = {"legs": {"ORB": {"trade_id": TID, "shares_remaining": 10}}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    _resend(state, clock, qe.BROKER_RESEND_MIN_GAP_SEC + 1)
    _resend(state, clock, 60)

    assert len(fake.sent) == 3 and state["_broker_resend"] == {}
    assert any("could not be sent either" in e["text"] for e in state["events"])
    # WEBULL PUSH PLAN 10-07 group B: ONE high "entry missed" note, sent when the re-send fails
    assert [p for _m, p in pushed] == ["high"]
    assert "The rest of the ORB buy could not be sent" in pushed[0][0]
    _no_duplicate_ids(fake)


def test_qqq_open_split_with_unknown_part1_never_resends_the_rest(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = [RuntimeError("Read timed out")]      # part 1: no clear answer
    state = {"legs": {"ORB": {"trade_id": TID, "shares_remaining": 10}}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    _resend(state, clock, 60)

    assert len(fake.sent) == 1 and not state.get("_broker_resend")
    assert any("OUTCOME UNKNOWN" in e["text"] for e in state["events"])
    # WEBULL PUSH PLAN 10-07 group B: high, the "may not be at Webull" plain note
    assert any(p == "high" and "Webull did not answer the ORB buy in time" in m
               for m, p in pushed)


def test_qqq_close_split_refused_part2_is_resent_through_close_retry(tmp_path, monkeypatch):
    """ORB long 10 closes while NOISE is short 6 (account +4): SELL 4 + SHORT 6. The
    SHORT is refused -- close_retry re-sends only what the adapter still holds for ORB."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "NOISE", -6)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["filled", RuntimeError(REFUSED_417), "filled"]
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=TID,
                         nowdt=datetime.datetime(2026, 9, 26, 12, 0, 0), log=NOOP)
    key = f"ORB:CLOSE:{TID}"
    assert state["_broker_resend"][key]["needs_verify"] is False
    assert _sent(adapter, "ORB") == 6

    _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4), ("SHORT", 6), ("SHORT", 6)]
    assert _sent(adapter, "ORB") == 0 and key not in state["_broker_resend"]
    _resend(state, clock, 60)
    assert len(fake.sent) == 3
    _no_duplicate_ids(fake)


def test_qqq_close_split_with_part2_held_back_resends_only_the_rest(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "NOISE", -6)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.detail["*"] = [od("SUBMITTED", 0)]            # part 1 never confirms in time
    state = {"legs": {}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=TID,
                         nowdt=datetime.datetime(2026, 9, 26, 12, 0, 0), log=NOOP)
    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4)]
    item = state["_broker_resend"][f"ORB:CLOSE:{TID}"]
    p1 = WO._part_client_order_id(item["last_signal_id"], 1, 2)
    # part 1 is still working at Webull: it is verified by id before any re-send
    assert item["needs_verify"] is True and item["unresolved_part_ids"] == [p1]
    _resend(state, clock, 60)
    assert len(fake.sent) == 1                         # still working: no re-send

    fake.detail["*"] = [od("FILLED", 4)]
    fake.place = ["filled"]
    _resend(state, clock, 60)
    assert [(s[1], s[2]) for s in fake.sent][1:] == [("SHORT", 6)]
    assert _sent(adapter, "ORB") == 0
    _no_duplicate_ids(fake)


# ── 4. pruning ─────────────────────────────────────────────────────────────────────

def test_part_records_older_than_seven_days_are_pruned(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    old = {"leg": "ORB", "symbol": "QQQ", "side": "BUY", "qty": 1, "booked": 0,
           "pending": True, "ts": WO.time.time() - WO.ORDER_PART_KEEP_SEC - 60}
    adapter._state["order_parts"] = {"OLD": dict(old), "NEW": dict(old, ts=WO.time.time())}

    _place(adapter, leg="NOISE", signal="N1", qty=1)

    assert "OLD" not in adapter._state["order_parts"]
    assert {"NEW", "N1"} <= set(adapter._state["order_parts"])


# ── 5. 2026-09-26 review fixes ─────────────────────────────────────────────────────

NOWDT = datetime.datetime(2026, 9, 26, 12, 0, 0)


def _close(state, shares=10):
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=shares, shadow_px=500.0,
                         intent="CLOSE", ts="x", trade_id=TID, nowdt=NOWDT, log=NOOP)


def _sold(fake):
    return sum(q for _c, side, q in fake.sent if side in ("SELL", "SHORT"))


def test_qqq_single_close_dead_with_a_partial_at_send_resends_the_true_remainder(
        tmp_path, monkeypatch):
    """critical: the send-time lookup books 4 of 10; the re-send must be 6, not 2."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = [RuntimeError("dropped connection"), "filled"]
    fake.detail["*"] = [od("REJECTED", 4)]
    state = {"legs": {}, "events": []}

    _close(state)
    assert _sent(adapter, "ORB") == 6
    _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 10), ("SELL", 6)]
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (0, 0)
    assert state["_broker_resend"] == {}
    _resend(state, clock, 60)
    assert len(fake.sent) == 2
    _no_duplicate_ids(fake)


def test_qqq_single_close_unknown_then_reconcile_books_a_partial_resends_the_true_remainder(
        tmp_path, monkeypatch):
    """critical: UNKNOWN at send, reconcile's PENDING pass books CANCELLED 4 of 10 --
    the close re-send must still be 6."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = [RuntimeError("dropped connection"), "filled"]
    fake.detail["*"] = [RuntimeError("not found")]
    state = {"legs": {}, "events": []}

    _close(state)
    assert adapter.status()["pending_parts"] != []

    fake.detail["*"] = [od("CANCELLED", 4)]
    fake.positions = [{"symbol": "QQQ", "quantity": 6, "side": "LONG"}]
    assert adapter.reconcile()["ok"] is True
    assert _sent(adapter, "ORB") == 6

    _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 10), ("SELL", 6)]
    assert _sent(adapter, "ORB") == 0 and state["_broker_resend"] == {}
    _no_duplicate_ids(fake)


def _split_close(tmp_path, monkeypatch):
    """ORB long 10 closes while NOISE is short 6 (account +4): SELL 4, then SHORT 6."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "NOISE", -6)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    return adapter, fake, pushed, clock


def test_qqq_split_close_part1_partial_at_the_deadline_then_filled_sells_exactly_the_close(
        tmp_path, monkeypatch):
    """critical: part 1 PARTIAL_FILLED 2 of 4 when the split wait ends -- nothing may be
    re-sent while it is still working, and the total sold is exactly 10."""
    adapter, fake, pushed, clock = _split_close(tmp_path, monkeypatch)
    fake.detail["*"] = [od("PARTIAL_FILLED", 2)]
    state = {"legs": {}, "events": []}

    _close(state)
    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4)]
    assert _sent(adapter, "ORB") == 6                    # part 1 still counted in full
    _resend(state, clock, 60)
    _resend(state, clock, 60)
    assert len(fake.sent) == 1                           # working: never stacked on

    fake.detail["*"] = [od("FILLED", 4)]
    fake.place = ["filled"]
    _resend(state, clock, 60)
    _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4), ("SHORT", 6)]
    assert _sold(fake) == 10 and _sent(adapter, "ORB") == 0
    assert state["_broker_resend"] == {}
    _no_duplicate_ids(fake)


def test_qqq_split_close_part1_cancelled_after_a_partial_resends_what_did_not_sell(
        tmp_path, monkeypatch):
    adapter, fake, pushed, clock = _split_close(tmp_path, monkeypatch)
    fake.detail["*"] = [od("PARTIAL_FILLED", 2)]
    state = {"legs": {}, "events": []}
    _close(state)

    fake.detail["*"] = [od("CANCELLED", 2)]              # 2 of part 1's 4 never sold
    fake.place = ["filled", "filled"]
    _resend(state, clock, 60)
    _resend(state, clock, 60)

    # 2 landed on part 1; the re-send of 8 splits again on account +2: SELL 2 + SHORT 6
    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4), ("SELL", 2), ("SHORT", 6)]
    assert _sold(fake) - 2 == 10                         # part 1 only sold 2 of its 4
    assert _sent(adapter, "ORB") == 0 and state["_broker_resend"] == {}
    _no_duplicate_ids(fake)


def test_qqq_close_found_live_at_send_then_cancelled_is_resent_once(tmp_path, monkeypatch):
    """major: the send raised, the lookup found it SUBMITTED (ok, counted); fill capture
    later sees CANCELLED 4 of 10 -- the unsold 6 are re-sent exactly once."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = [RuntimeError("dropped connection"), "filled"]
    fake.detail["*"] = [od("SUBMITTED", 0)]
    state = {"legs": {}, "events": []}

    _close(state)
    assert _sent(adapter, "ORB") == 0 and not state.get("_broker_resend")

    first = WO._sanitize_client_order_id(qe._broker_signal_id("ORB", "x", "CLOSE", trade_id=TID))
    fake.detail[first] = [od("CANCELLED", 4)]
    fake.detail["*"] = [od("FILLED", 6)]                  # the re-send itself fills
    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 1
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
    assert _sent(adapter, "ORB") == 6
    assert any("re-sending the unsold 6" in e["text"] for e in state["events"])
    # WEBULL PUSH PLAN 10-07 group A: unsold shares are trading affected -- high
    assert any(p == "high" and "Webull did not fill 6 shares of the ORB sell; they are "
               "re-sent" in m for m, p in pushed)

    for _ in range(3):
        _resend(state, clock, 60)
        qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 10), ("SELL", 6)]
    assert _sent(adapter, "ORB") == 0 and state["_broker_resend"] == {}
    _no_duplicate_ids(fake)


def test_qqq_acked_close_cancelled_with_a_partial_is_resent_once(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["ack", "filled"]
    state = {"legs": {}, "events": []}
    _close(state)

    fake.detail["*"] = [od("CANCELLED", 4)]
    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 1
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
    for _ in range(3):
        _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 10), ("SELL", 6)]
    assert _sent(adapter, "ORB") == 0
    _no_duplicate_ids(fake)


def test_reconcile_booking_an_unknown_open_the_book_no_longer_holds_pushes_high(
        tmp_path, monkeypatch):
    """minor: the PENDING pass books a fill that makes the books match Webull -- that
    must still page, loudly, when the book holds none of that leg."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = [RuntimeError("Read timed out")]
    fake.detail["*"] = [RuntimeError("not found")]
    state = {"legs": {}, "events": []}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    n_before = len(pushed)

    fake.detail["*"] = [od("FILLED", 10)]
    fake.positions = [{"symbol": "QQQ", "quantity": 10, "side": "LONG"}]
    state["_reconcile_due"], state["_last_broker_send_at"] = True, 0
    qe._maybe_run_broker_reconcile(state, {}, adapter, NOWDT, True, log=NOOP)
    state["_reconcile_due"] = True
    qe._maybe_run_broker_reconcile(state, {}, adapter, NOWDT, True, log=NOOP)

    assert any("outcome was not known" in e["text"] and "the book holds no ORB" in e["text"]
               for e in state["events"])
    # WEBULL PUSH PLAN 10-07 group D's "sell by hand" case: high, plain
    new = [(m, p) for m, p in pushed[n_before:] if "landed at Webull after the book" in m]
    assert len(new) == 1 and new[0][1] == "high"
    assert "sell any ORB shares the book does not hold by hand" in new[0][0]
    assert _sent(adapter, "ORB") == 10


def test_split_open_part2_duplicate_refusal_keeps_the_remainder(tmp_path, monkeypatch):
    """minor: a 417 DUPLICATE on part 2 must not overwrite the remainder item, and the
    generic 'only PARTIALLY' push is left to the remainder's own push."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["filled", RuntimeError(
        "ServerException: HTTP Status: 417, Code: OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK")]
    state = {"legs": {"ORB": {"trade_id": TID, "shares_remaining": 10}}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)

    item = state["_broker_resend"]["ORB:OPEN"]
    assert (item["why"], item["shares"]) == ("remainder", 6)
    assert not any("PARTIALLY" in m for m, _p in pushed)


def test_lookups_stop_once_the_send_or_reconcile_budget_is_spent(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(WO, "SEND_LOOKUP_BUDGET_SEC", -1.0)
    fake.place = [RuntimeError("Read timed out")]
    fake.detail["*"] = [od("FILLED", 5)]

    rec = _place(adapter)

    assert rec["outcome"] == "UNKNOWN" and fake.detail_calls == []   # never "not placed"
    monkeypatch.setattr(WO, "RECONCILE_PENDING_BUDGET_SEC", -1.0)
    adapter.reconcile()
    assert fake.detail_calls == [] and adapter.status()["pending_parts"] == ["S1"]


# ── review critical (2026-09-26): a 5xx on a split CLOSE part is not "never placed" ──

HTTP_503 = "ServerException: HTTP Status: 503, Code: SERVICE_UNAVAILABLE, Msg: try later"


def test_qqq_split_close_503_on_part1_resends_nothing_until_verified(tmp_path, monkeypatch):
    adapter, fake, pushed, clock = _split_close(tmp_path, monkeypatch)
    p1 = WO._part_client_order_id(
        WO._sanitize_client_order_id(qe._broker_signal_id("ORB", "x", "CLOSE", trade_id=TID)), 1, 2)
    fake.place = [RuntimeError(HTTP_503), "filled"]
    fake.detail[p1] = [RuntimeError("not found")]
    state = {"legs": {}, "events": []}

    _close(state)
    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4)]   # part 2 held back
    _resend(state, clock, 60)
    _resend(state, clock, 60)
    assert len(fake.sent) == 1                                   # unclear: never re-sent blind

    fake.detail[p1] = [od("FILLED", 4)]                          # the 503 order did land
    _resend(state, clock, 60)
    _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4), ("SHORT", 6)]
    assert _sold(fake) == 10 and _sent(adapter, "ORB") == 0
    assert state["_broker_resend"] == {}
    _no_duplicate_ids(fake)


def test_qqq_split_close_503_on_part2_resends_nothing_until_verified(tmp_path, monkeypatch):
    adapter, fake, pushed, clock = _split_close(tmp_path, monkeypatch)
    p2 = WO._part_client_order_id(
        WO._sanitize_client_order_id(qe._broker_signal_id("ORB", "x", "CLOSE", trade_id=TID)), 2, 2)
    fake.place = ["filled", RuntimeError(HTTP_503), "filled"]
    fake.detail[p2] = [RuntimeError("not found")]
    state = {"legs": {}, "events": []}

    _close(state)
    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4), ("SHORT", 6)]
    _resend(state, clock, 60)
    _resend(state, clock, 60)
    assert len(fake.sent) == 2                                   # unclear: never re-sent blind

    fake.detail[p2] = [od("CANCELLED", 0)]                       # the 503 order never filled
    _resend(state, clock, 60)
    _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4), ("SHORT", 6), ("SHORT", 6)]
    assert _sold(fake) - 6 == 10 and _sent(adapter, "ORB") == 0
    assert state["_broker_resend"] == {}
    _no_duplicate_ids(fake)


def test_qqq_open_split_remainder_is_capped_at_what_the_lot_still_lacks(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["filled", RuntimeError(REFUSED_417), "filled"]
    state = {"legs": {"ORB": {"trade_id": TID, "shares_remaining": 10}}, "events": []}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)

    state["legs"]["ORB"]["shares_remaining"] = 7      # the book trimmed the lot meanwhile
    _resend(state, clock, qe.BROKER_RESEND_MIN_GAP_SEC + 1)
    assert [(s[1], s[2]) for s in fake.sent] == [("BUY", 4), ("BUY", 6), ("BUY", 3)]

    state["legs"]["ORB"]["shares_remaining"] = 4
    fake.place = [RuntimeError(REFUSED_417)]
    state["_broker_resend"] = {"ORB:OPEN": dict(
        leg="ORB", intent="OPEN", side="long", shares=6, shadow_px=500.0, ts="x", seq=0,
        trade_id=TID, why="remainder", tries=0, first_at=clock[0], last_at=0,
        session_date="2026-09-26")}
    _resend(state, clock, qe.BROKER_RESEND_MIN_GAP_SEC + 1)
    assert len(fake.sent) == 3 and state["_broker_resend"] == {}   # nothing lacking: dropped


# ── 2026-09-26 review follow-ups ───────────────────────────────────────────────────

def test_split_part1_cancelled_after_a_partial_returns_only_its_unfilled_rest(tmp_path, monkeypatch):
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.detail[p1] = [od("CANCELLED", 1)]

    rec = _place(adapter, qty=10)

    assert [(u["client_order_id"], u["qty"]) for u in rec["unsent_parts"]] == [(p1, 3), (p2, 6)]
    assert _sent(adapter, "ORB") == 1


def test_qqq_split_open_part1_dead_during_the_wait_requeues_the_whole_entry(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.detail["*"] = [od("REJECTED", 0)]
    state = {"legs": {"ORB": {"trade_id": TID, "shares_remaining": 10}}, "events": []}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    item = state["_broker_resend"]["ORB:OPEN"]
    assert (item["why"], item["shares"]) == ("remainder", 10)
    assert _sent(adapter, "ORB") == 0

    fake.place = ["filled", "filled"]
    _resend(state, clock, qe.BROKER_RESEND_MIN_GAP_SEC + 1)
    assert [(s[1], s[2]) for s in fake.sent] == [("BUY", 4), ("BUY", 4), ("BUY", 6)]
    assert _sent(adapter, "ORB") == 10 and state["_broker_resend"] == {}
    _no_duplicate_ids(fake)


def test_split_wait_lets_go_of_the_adapter_lock(tmp_path, monkeypatch):
    import threading
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    fake.detail[p1] = [od("SUBMITTED", 0), od("FILLED", 4)]
    free = []
    real = fake._detail

    def detail(account_id, coid):   # another thread (reconcile, status) tries the lock
        got = []

        def probe():
            ok = adapter._lock.acquire(timeout=0.5)
            got.append(ok)
            if ok:
                adapter._lock.release()
        t = threading.Thread(target=probe)
        t.start()
        t.join()
        free.append(got[0])
        return real(account_id, coid)

    fake.order_v3.get_order_detail.side_effect = detail
    rec = _place(adapter, qty=10)

    assert rec["ok"] is True and free == [True, True]
    free.clear()
    detail("ACCT1", p1)                                # and the send gave it back
    assert free == [True]


def test_qqq_fill_capture_keeps_a_partial_open_then_books_only_the_fill(tmp_path, monkeypatch):
    """major: PARTIAL_FILLED with an average price is not the fill -- the job stays open
    past the one-minute give-up, then CANCELLED 4 of 10 books 4 with one high push."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    # the book still holds the trade (10-08 review: else the note is group D, default)
    state = {"legs": {"ORB": {"trade_id": TID, "side": "long", "shares_remaining": 10}},
             "events": []}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    fake.detail["*"] = [dict(od("PARTIAL_FILLED", 4), filled_price="500.10")]

    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 1
    for _ in range(12):                                  # ~2 minutes of working answers
        qe._maybe_capture_broker_fills(state, {}, None, True, log=NOOP)
        clock[0] += qe.BROKER_FILL_CAPTURE_RETRY_GAP_SEC + 1
    assert "ORB:OPEN" in state["_broker_fill_capture"]
    assert _sent(adapter, "ORB") == 10 and pushed == []

    fake.detail["*"] = [dict(od("CANCELLED", 4), filled_price="500.10")]
    qe._maybe_capture_broker_fills(state, {}, None, True, log=NOOP)

    assert state["_broker_fill_capture"] == {}
    assert (_sent(adapter, "ORB"), _believed(adapter, "ORB")) == (4, 4)
    # WEBULL PUSH PLAN 10-07 group B: only part of the buy is at Webull -- high
    assert len([m for m, p in pushed if p == "high"]) == 1
    assert "Webull filled only 4 shares of the ORB buy" in pushed[0][0]
    assert "only part of the ORB buy is at Webull" in pushed[0][0]
    clock[0] += 120
    qe._maybe_capture_broker_fills(state, {}, None, True, log=NOOP)
    assert len(pushed) == 1


# ── review notes (2026-09-26, round 3) ─────────────────────────────────────────────

def test_qqq_fill_capture_never_books_a_record_about_another_order():
    """note 1: order_status_fields falls back to orders[0] -- never apply that."""
    adapter = MagicMock()
    adapter.order_status.return_value = {
        "ok": True, "client_order_id": "S1",
        "response": {"orders": [{"client_order_id": "OTHER", "status": "CANCELLED",
                                 "filled_quantity": "0", "filled_price": "1.0"}]}}
    outcome = {}

    px, note = qe._query_broker_fill(adapter, "S1", outcome=outcome, log=NOOP)

    assert (px, note) == (None, "record is about another order")
    adapter.apply_order_outcome.assert_not_called()
    assert outcome == {}


def test_qqq_dead_close_settled_by_reconcile_requeues_the_unsold_shares(tmp_path, monkeypatch):
    """note 2: fill capture sees FAILED with no filled qty (kept pending, job ages out);
    a later reconcile gets CANCELLED 4 of 10 -- the unsold 6 go back through
    close_retry once, with one high push, and never twice."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["ack", "filled"]
    state = {"legs": {}, "events": []}
    _close(state)

    fake.detail["*"] = [{"status": "FAILED"}]
    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 1
    for _ in range(12):
        qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
        clock[0] += qe.BROKER_FILL_CAPTURE_RETRY_GAP_SEC + 1
    assert state["_broker_fill_capture"] == {} and not state.get("_broker_resend")
    assert _sent(adapter, "ORB") == 0 and adapter.status()["pending_parts"] != []

    fake.detail["*"] = [od("CANCELLED", 4)]
    fake.positions = [{"symbol": "QQQ", "quantity": 6, "side": "LONG"}]
    state["_reconcile_due"], state["_last_broker_send_at"] = True, 0
    qe._maybe_run_broker_reconcile(state, {}, adapter, NOWDT, True, log=NOOP)

    assert _sent(adapter, "ORB") == 6
    assert any("outcome was not known" in e["text"] and "re-sending the unsold 6" in e["text"]
               for e in state["events"])
    # WEBULL PUSH PLAN 10-07 group A: unsold shares are trading affected -- high, once
    high = [m for m, p in pushed if p == "high"]
    assert len(high) == 1
    assert "Webull did not fill 6 shares of the ORB sell; they are re-sent" in high[0]
    for _ in range(3):
        _resend(state, clock, 60)
    state["_reconcile_due"] = True
    qe._maybe_run_broker_reconcile(state, {}, adapter, NOWDT, True, log=NOOP)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 10), ("SELL", 6)]
    assert _sent(adapter, "ORB") == 0
    assert len([m for m, p in pushed if "ORB sell" in m]) == 1, "never twice"
    _no_duplicate_ids(fake)


def test_send_lookups_count_from_when_the_send_started(tmp_path, monkeypatch):
    """note 3: a place_order that took 14 s leaves room for one lookup, not three --
    none may start within ~25 s of qqq_exec's 40 s hard timeout."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    clock = [1_000_000.0]
    monkeypatch.setattr(WO.time, "time", lambda: clock[0])
    monkeypatch.setattr(WO, "_sleep", lambda sec: clock.__setitem__(0, clock[0] + sec))

    def slow_timeout(account_id, orders):
        fake.sent.append((orders[0]["client_order_id"], orders[0]["side"],
                          int(orders[0]["quantity"])))
        clock[0] += 14.0
        raise RuntimeError("Read timed out")

    fake.order_v3.place_order.side_effect = slow_timeout
    fake.detail["*"] = [RuntimeError("not visible yet")]

    rec = _place(adapter)

    assert WO.SEND_LOOKUP_BUDGET_SEC <= qe.BROKER_SEND_HARD_TIMEOUT_SEC - 25
    assert rec["outcome"] == "UNKNOWN" and fake.detail_calls == ["S1"]


# ── review notes (2026-09-26, round 4) ─────────────────────────────────────────────

def test_split_part2_is_not_sent_once_the_send_budget_is_spent(tmp_path, monkeypatch):
    """note 1: part 1 took past SEND_LOOKUP_BUDGET_SEC (even FILLED) -- part 2 comes back
    NOT_SENT instead of pushing the send past qqq_exec's 40 s hard timeout."""
    adapter, fake, p1, p2 = _split_open(tmp_path, monkeypatch)
    clock = [1_000_000.0]
    monkeypatch.setattr(WO.time, "time", lambda: clock[0])
    real = fake._place

    def slow_fill(account_id, orders):
        clock[0] += WO.SEND_LOOKUP_BUDGET_SEC + 1
        fake.place = ["filled"]
        return real(account_id, orders)

    fake.order_v3.place_order.side_effect = slow_fill
    rec = _place(adapter, qty=10)

    assert [s[0] for s in fake.sent] == [p1]
    assert rec["parts"][0]["ok"] is True and rec["parts"][1]["outcome"] == "NOT_SENT"
    assert rec["unsent_parts"] == [{"side": "BUY", "qty": 6, "client_order_id": p2}]
    assert _sent(adapter, "ORB") == 4


def test_qqq_open_remainder_is_sized_by_the_larger_book(tmp_path, monkeypatch):
    """note 2: believed and sent disagree (7 vs 4) -- the re-buy shrinks to 3, never 6."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "NOISE", -4)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    fake.place = ["filled", RuntimeError(REFUSED_417), "filled"]
    state = {"legs": {"ORB": {"trade_id": TID, "shares_remaining": 10}}, "events": []}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=10, shadow_px=500.0,
                         intent="OPEN", ts="x", trade_id=TID, log=NOOP)
    adapter._state["believed_positions"]["ORB"]["qty"] = 7

    _resend(state, clock, qe.BROKER_RESEND_MIN_GAP_SEC + 1)

    assert [(s[1], s[2]) for s in fake.sent] == [("BUY", 4), ("BUY", 6), ("BUY", 3)]


def test_a_4xx_the_adapter_read_off_the_exception_is_a_refusal_in_qqq_exec_too(
        tmp_path, monkeypatch):
    """note 3: an http_status attribute (no "HTTP Status:" text) -- both sides say 4xx."""
    adapter, fake = _adapter(tmp_path, monkeypatch)

    class Refused(Exception):
        http_status = 417

    fake.place = [Refused("order refused")]
    rec = _place(adapter)

    assert fake.detail_calls == [] and rec["http_status"] == 417
    assert qe._broker_row_outcome(rec) == "REFUSED"
    rec2 = dict(rec, parts=[dict(rec["parts"][0]), dict(rec["parts"][0], ok=True)])
    assert qe._broker_row_outcome(rec2) == "REFUSED"


def test_qqq_unsold_shares_of_another_order_wait_for_the_verify(tmp_path, monkeypatch):
    """note 4: the item verifies attempt A (6); order B died with 4 unsold. A FILLED must
    not drop the item -- B's 4 are still sold, once."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    pushed, clock = _patch_qqq(tmp_path, monkeypatch, adapter)
    state = {"legs": {}, "events": [], "_broker_resend": {f"ORB:CLOSE:{TID}": dict(
        leg="ORB", intent="CLOSE", side="long", shares=6, shadow_px=500.0, ts="x", seq=0,
        trade_id=TID, why="close_retry", tries=1, first_at=clock[0], last_at=0,
        session_date="2026-09-26", sent=True, needs_verify=True, last_signal_id="A",
        unresolved_part_ids=None, verify_qty=6, unresolved_part_qty=None,
        verify_landed_qty=0)}}
    ctx = {"leg": "ORB", "shadow_px": 500.0, "retry": {"trade_id": TID, "side": "long"}}

    assert qe._requeue_close_unfilled(state, ctx, "B", 4, nowdt=NOWDT, log=NOOP) is True
    item = state["_broker_resend"][f"ORB:CLOSE:{TID}"]
    assert (item["verify_qty"], item["pending_add"]) == (6, 4)

    fake.detail["A"] = [od("FILLED", 6)]
    fake.place = ["filled"]
    _resend(state, clock, 60)

    assert [(s[1], s[2]) for s in fake.sent] == [("SELL", 4)]
    assert _sent(adapter, "ORB") == 0


def test_reconcile_skips_the_pending_pass_while_order_lookups_time_out(tmp_path, monkeypatch):
    """note 5: a lookup timed out moments ago -- reconcile() reads positions only."""
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.place = [RuntimeError("Read timed out")]
    fake.detail["*"] = [RuntimeError("not found")]
    assert _place(adapter, qty=1)["outcome"] == "UNKNOWN"
    fake.detail["*"] = [od("FILLED", 1)]
    fake.positions = [{"symbol": "QQQ", "quantity": 1, "side": "LONG"}]
    fake.detail_calls.clear()

    qe._order_lookup_timeout_at["t"] = qe.time.time()
    qe._reconcile_with_timeout(adapter, log=NOOP)
    assert fake.detail_calls == [] and adapter.status()["pending_parts"] == ["S1"]

    qe._order_lookup_timeout_at["t"] = 0.0
    assert qe._reconcile_with_timeout(adapter, log=NOOP)["ok"] is True
    assert fake.detail_calls == ["S1"] and adapter.status()["pending_parts"] == []
