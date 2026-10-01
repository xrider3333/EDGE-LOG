"""END-OF-DAY INTERNAL CROSS + AFTER-CLOSE GUARDS (2026-09-28).

THE INCIDENT (box qqq_exec.log, 2026-09-28 15:59:01). The end-of-day flatten closed ORB
short 10 and ENGUQ long 10 with one market order each, back to back. The account was flat
at Webull the whole time (-10 + 10). ORB's BUY 10 went first -- a buy-OPENING order on a flat
account -- and the adapter booked it in full on its ack, so ENGUQ's SELL 10 was planned as a
closing sell on a +10 account. At Webull the buy was still pending on a flat account, so the
sell was a sell-OPENING order and Webull refused it: 417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER.
close_retry re-sent it 5 s later. Right number of orders: zero.

FakeWebullBook below models what the real account did that day and what a synchronous fake
cannot show: an accepted market order stays PENDING until the test fills it; a pending
buy-opening and a new sell-opening order (or the reverse) on one symbol are refused with the
box-order 417; a closing SELL may not exceed the long shares not already reserved by pending
closing sells; a SHORT on a long account and a BUY that crosses a short are refused.

Also covered here (the api/qqq_exec.py half of the last-bar work): no broker order after the
session close (_mirror_to_broker's AFTER-CLOSE GUARD), no engine ENTRY opened after
last_entry / flat_by / the close, and a post-close backtest EXIT for a lot the flatten already
closed is recorded for comparison without any order or warning.

No real SDK, network or credentials: tests/conftest.py isolates the live system as usual.
"""
import copy
import csv
import datetime
import json
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import trade_id as T
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731

ORB_TID = "ORB_R6-20260928T134000Z-S"
ENGUQ_TID = "ENGUQ_335-20260928T150500Z-L"
NOISE_TID = "NOISE_382-20260928T150000Z-L"
FLAT_AT = datetime.datetime(2026, 9, 28, 15, 59, 1)       # the incident's own second
CROSS_PX = 736.58


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeWebullBook:
    """One Webull margin account, QQQ only. See the module docstring for the rules."""

    def __init__(self):
        self.pos = 0                 # FILLED position
        self.pending = []            # [{coid, side, qty, opening}]
        self.status = {}             # coid -> FILLED / SUBMITTED
        self.async_fills = False
        self.sent = []               # every ACCEPTED order, in order
        self.refused = []            # every refused order: (side, qty, reason)
        self.account_v2 = MagicMock()
        self.account_v2.get_account_list.return_value.json.return_value = {
            "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
        self.account_v2.get_account_position.side_effect = lambda acct: _Resp(
            {"data": ([{"symbol": "QQQ", "quantity": str(abs(self.pos)),
                        "side": "SHORT" if self.pos < 0 else "LONG"}] if self.pos else [])})
        self.order_v3 = MagicMock()
        self.order_v3.place_order.side_effect = self._place
        self.order_v3.get_order_detail.side_effect = self._detail

    def _refuse(self, side, qty, code, msg):
        self.refused.append((side, qty, code))
        raise RuntimeError(f"ServerException: HTTP Status: 417, Code: {code}, Msg: {msg}")

    def _place(self, account_id, orders):
        o = orders[0]
        side, qty, coid = o["side"], int(o["quantity"]), o["client_order_id"]
        pend_buy_open = any(p["side"] == "BUY" and p["opening"] for p in self.pending)
        pend_sell_open = any(p["side"] in ("SELL", "SHORT") and p["opening"] for p in self.pending)
        reserved_sell = sum(p["qty"] for p in self.pending if p["side"] == "SELL" and not p["opening"])
        reserved_buy = sum(p["qty"] for p in self.pending if p["side"] == "BUY" and not p["opening"])
        if side == "BUY":
            if self.pos >= 0:
                opening = True
                if pend_sell_open:
                    self._refuse(side, qty, "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER", "box order")
            else:
                opening = False
                if qty > -self.pos - reserved_buy:
                    self._refuse(side, qty, "OPENAPI_ORDER_CROSSES_POSITION", "crosses short")
        elif side == "SELL":
            if qty <= self.pos - reserved_sell:
                opening = False
            else:
                # more than the free long: Webull reads it as a sell-OPENING order
                if pend_buy_open:
                    self._refuse(side, qty, "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER",
                                 "Buy opening orders and sell opening orders for the same "
                                 "stock ... cannot exist simultaneously")
                self._refuse(side, qty, "OPENAPI_ORDER_EXCEED_POSITION", "exceeds position")
        elif side == "SHORT":
            if self.pos > 0:
                self._refuse(side, qty, "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION", "long held")
            if pend_buy_open:
                self._refuse(side, qty, "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER", "box order")
            opening = True
        else:
            raise AssertionError(side)
        self.sent.append({"side": side, "qty": qty, "coid": coid, "opening": opening})
        if self.async_fills:
            self.pending.append({"coid": coid, "side": side, "qty": qty, "opening": opening})
            self.status[coid] = "SUBMITTED"
        else:
            self._apply(side, qty)
            self.status[coid] = "FILLED"
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": self.status[coid],
             "filled_price": "736.58", "filled_quantity": str(qty) if not self.async_fills else "0"}]})

    def _apply(self, side, qty):
        self.pos += qty if side == "BUY" else -qty

    def fill_pending(self):
        for p in self.pending:
            self._apply(p["side"], p["qty"])
            self.status[p["coid"]] = "FILLED"
        self.pending = []

    def _detail(self, account_id, coid):
        st = self.status.get(coid)
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": st or "REJECTED", "filled_quantity": "0"}]})


def _broker_cfg(tmp_path):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["rails"]["max_shares_per_leg"] = 100
    cfg["rails"]["max_total_position_shares"] = 500
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


@pytest.fixture
def book(tmp_path, monkeypatch):
    """(adapter, fake) wired into api.qqq_exec, CSVs under tmp_path, EOD priced at the
    09-28 live print for every leg."""
    out = tmp_path / "qqq_out"
    out.mkdir()
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    monkeypatch.setattr(qe, "SERVING_LOCK", str(out / "SERVING.lock"))
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (CROSS_PX, "live_stream"))
    cfg = _broker_cfg(tmp_path)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    fake = FakeWebullBook()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: fake)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    return adapter, fake


def _cfg(**shares):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["shares"] = {"ORB": 10, "ENGUQ": 10, "NOISE": 10, **shares}
    cfg["signal_source"] = "engine"
    cfg["max_shares_per_leg"] = 60
    cfg["slippage_per_share"] = 0.0
    cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
    return cfg


def _open(state, cfg, leg, side, tid, px=735.0):
    assert qe._open_lot(state, cfg, leg, side, cfg["shares"][leg], None, px, 0.0, log=NOOP,
                        trade_id=tid, nowdt=datetime.datetime(2026, 9, 28, 11, 0))


def _rows(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def _sent_books(adapter):
    return {leg: p["qty"] for leg, p in (adapter._state.get("broker_sent_positions") or {}).items()}


# ── the fake reproduces the incident on the old per-leg path ─────────────────────────

def test_fake_book_reproduces_the_0928_box_order_refusal_without_the_cross(book, monkeypatch):
    """Sanity check of the harness: with the cross switched off (the old per-leg path), the
    09-28 pair is refused exactly as on the box -- so the tests below prove the fix, not a
    fake that could never refuse."""
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    assert fake.pos == 0 and adapter._account_net("QQQ") == 0
    opens_sent = len(fake.sent)

    monkeypatch.setattr(adapter, "cross_legs_internally", lambda *a, **k: None)
    fake.async_fills = True
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    assert [r[2] for r in fake.refused] == ["OPENAPI_OPEN_ORDER_HAS_BOX_ORDER"]
    assert [(o["side"], o["qty"], o["opening"]) for o in fake.sent[opens_sent:]] == \
        [("BUY", 10, True)], "ORB's cover went out as a buy-OPENING order on a flat account"
    assert f"ENGUQ:CLOSE:{ENGUQ_TID}" in state["_broker_resend"], "the refused sell went to close_retry"


# ── the 09-28 pair: zero orders ──────────────────────────────────────────────────────

def test_0928_pair_on_a_net_flat_account_sends_no_order_and_nothing_is_refused(book):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    opens_sent = len(fake.sent)

    fake.async_fills = True
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    assert fake.sent[opens_sent:] == [], "net-flat account: the right number of orders is zero"
    assert fake.refused == []
    assert state["legs"] == {}, "the shadow book still closes both lots"
    assert _sent_books(adapter) == {"ORB": 0, "ENGUQ": 0}
    assert adapter._state.get("open_legs") == {}
    assert state.get("_broker_resend", {}) == {}, "nothing to retry"
    # reconcile agrees with Webull (flat) -- no false halt
    res = adapter.reconcile(broker_positions_fn=lambda: {})
    assert res["ok"] is True
    # one NETTED allocation row per leg, under each leg's own CLOSE id, at ONE price
    rows = [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["intent"] == "CLOSE"]
    assert {r["leg"]: r["signal_id"] for r in rows} == {
        "ORB": qe._broker_signal_id("ORB", None, "CLOSE", trade_id=ORB_TID),
        "ENGUQ": qe._broker_signal_id("ENGUQ", None, "CLOSE", trade_id=ENGUQ_TID)}
    assert {r["outcome"] for r in rows} == {"NETTED"}
    assert {r["sent"] for r in rows} == {"False"} and {r["ok"] for r in rows} == {"True"}
    assert {float(r["broker_fill_px"]) for r in rows} == {CROSS_PX}
    assert {r["side"] for r in rows} == {"BUY", "SELL"}


def test_crossed_rows_keep_parity_and_daily_pnl_whole(book):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    by_base = qe._broker_orders_by_base(qe._all_broker_orders_from_csv())
    for tid in (ORB_TID, ENGUQ_TID):
        row = qe._broker_order_for(tid, "CLOSE", by_base)
        assert row is not None and float(row["broker_fill_px"]) == CROSS_PX
    # both OPENs filled at the fake's 736.58 and both closed at 736.58: flat round trips,
    # and the account's realized P&L is exactly the two legs' sum
    today = qe._now_et().strftime("%Y-%m-%d")
    realized, priced = qe._broker_realized_today(today)
    assert priced is True
    assert realized == pytest.approx(0.0)


# ── ORB short + NOISE long, opposite and unequal: partial cross + one closing order ───

def test_orb_short_against_bigger_noise_long_crosses_10_and_sells_only_the_rest(book):
    adapter, fake = book
    cfg = _cfg(NOISE=26)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "NOISE", "long", NOISE_TID)
    assert fake.pos == 16
    opens_sent = len(fake.sent)

    fake.async_fills = True
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    assert [(o["side"], o["qty"], o["opening"]) for o in fake.sent[opens_sent:]] == \
        [("SELL", 16, False)], "one plain closing sell for the account's own net"
    assert fake.refused == []
    fake.fill_pending()
    assert fake.pos == 0
    assert _sent_books(adapter) == {"ORB": 0, "NOISE": 0}
    rows = [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["intent"] == "CLOSE"]
    alloc = {r["leg"]: r for r in rows if r["outcome"] == "NETTED"}
    assert alloc["ORB"]["shares"] == "10" and alloc["NOISE"]["shares"] == "10"
    noise_base = qe._broker_signal_id("NOISE", None, "CLOSE", trade_id=NOISE_TID)
    assert alloc["NOISE"]["signal_id"] == noise_base + "X", \
        "a partly crossed leg's allocation row must not share its real CLOSE order's id"
    real = [r for r in rows if r["outcome"] != "NETTED"]
    assert [(r["leg"], r["signal_id"], r["shares"]) for r in real] == [("NOISE", noise_base, "16")]


# ── same side: nothing to cross, two closing orders, never refused ───────────────────

def test_same_side_legs_are_not_crossed_and_both_close_without_a_refusal(book):
    adapter, fake = book
    cfg = _cfg(NOISE=20)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "long", "ORB_R6-20260928T134000Z-L")
    _open(state, cfg, "NOISE", "long", NOISE_TID)
    opens_sent = len(fake.sent)

    fake.async_fills = True
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    assert sorted((o["side"], o["qty"], o["opening"]) for o in fake.sent[opens_sent:]) == \
        [("SELL", 10, False), ("SELL", 20, False)]
    assert fake.refused == []
    assert not [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["outcome"] == "NETTED"]
    fake.fill_pending()
    assert fake.pos == 0


# ── one leg flat at the broker (its OPEN never landed) ───────────────────────────────

def test_a_leg_whose_open_never_reached_webull_is_not_crossed(book):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    real_place = fake._place
    fake.order_v3.place_order.side_effect = lambda a, o: (_ for _ in ()).throw(
        RuntimeError("HTTP Status: 417, Code: OPENAPI_SOMETHING, Msg: refused"))
    _open(state, cfg, "NOISE", "long", NOISE_TID)            # book-only lot
    fake.order_v3.place_order.side_effect = real_place
    assert _sent_books(adapter).get("NOISE", 0) == 0 and fake.pos == -10
    opens_sent = len(fake.sent)

    fake.async_fills = True
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    assert [(o["side"], o["qty"], o["opening"]) for o in fake.sent[opens_sent:]] == \
        [("BUY", 10, False)], "ORB covers its own short; NOISE had nothing at Webull"
    assert fake.refused == []
    assert not [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["outcome"] == "NETTED"]
    nothing = [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["leg"] == "NOISE" and r["intent"] == "CLOSE"]
    assert nothing and "nothing to close" in nothing[-1]["reason"]


# ── partial state: a leg whose real position is not known yet is left out ─────────────

def test_a_leg_with_a_pending_part_or_a_queued_close_keeps_its_own_path(book):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    # ENGUQ's OPEN part is still PENDING in the adapter (outcome not confirmed yet)
    coid = next(c for c, p in adapter._state["order_parts"].items() if p["leg"] == "ENGUQ")
    adapter._state["order_parts"][coid]["pending"] = True
    assert adapter.cross_legs_internally("QQQ", {"ORB": -1, "ENGUQ": 1})["crossed"] == {}

    adapter._state["order_parts"][coid]["pending"] = False
    state["_broker_resend"] = {f"ENGUQ:CLOSE:{ENGUQ_TID}": {"leg": "ENGUQ", "intent": "CLOSE"}}
    assert qe._internal_cross_for_flatten(
        state, [("ORB", None, CROSS_PX, "live_stream"), ("ENGUQ", None, CROSS_PX, "live_stream")],
        "EOD", nowdt=FLAT_AT, log=NOOP) == {}
    assert _sent_books(adapter) == {"ORB": -10, "ENGUQ": 10}, "books untouched"


# ── a fresh OPEN Webull acked but has not filled is never crossed (2026-09-28 review) ──

def _fresh_unfilled_enguq(book):
    """ORB short 10 (filled), then a fresh ENGUQ long 10 that Webull acked SUBMITTED and
    has not filled -- booked in full, not pending, like a real market order's ack."""
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    fake.async_fills = True
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    coid = next(c for c, p in adapter._state["order_parts"].items() if p["leg"] == "ENGUQ")
    part = adapter._state["order_parts"][coid]
    assert part["pending"] is False and part["booked"] == 10 and not part.get("final_status")
    return adapter, fake, cfg, state, coid


def test_a_kill_seconds_after_a_fresh_entry_does_not_cross_it_and_its_death_leaves_orb_held(book):
    adapter, fake, cfg, state, coid = _fresh_unfilled_enguq(book)
    priced = [("ORB", None, CROSS_PX, "live_stream"), ("ENGUQ", None, CROSS_PX, "live_stream")]
    # the KILL flatten a few seconds later: ENGUQ is left out, so nothing offsets
    assert qe._internal_cross_for_flatten(state, priced, "KILL",
                                          nowdt=datetime.datetime(2026, 9, 28, 11, 30),
                                          log=NOOP) == {}
    assert _sent_books(adapter) == {"ORB": -10, "ENGUQ": 10}
    # ... and the order then dies with 0 filled: ORB's short is still on the books (and
    # at Webull), so ORB's own CLOSE goes out for it -- never a phantom cross
    adapter.apply_order_outcome(coid, "CANCELLED", 0)
    assert _sent_books(adapter) == {"ORB": -10, "ENGUQ": 0}
    assert adapter._state["order_parts"][coid]["final_status"] == "CANCELLED"
    assert not adapter._state.get("internal_crosses")


def test_a_fresh_entry_is_crossed_once_webull_reports_it_filled(book):
    adapter, fake, cfg, state, coid = _fresh_unfilled_enguq(book)
    fake.fill_pending()
    adapter.apply_order_outcome(coid, "FILLED", 10)
    res = adapter.cross_legs_internally("QQQ", {"ORB": -1, "ENGUQ": 1})
    assert res["crossed"] == {"ORB": 10, "ENGUQ": 10}


def test_a_fresh_entry_is_crossed_once_it_is_older_than_the_grace(book, monkeypatch):
    adapter, fake, cfg, state, coid = _fresh_unfilled_enguq(book)
    now = WO.time.time()
    monkeypatch.setattr(WO.time, "time", lambda: now + WO.CROSS_FRESH_PART_SEC + 1)
    res = adapter.cross_legs_internally("QQQ", {"ORB": -1, "ENGUQ": 1})
    assert res["crossed"] == {"ORB": 10, "ENGUQ": 10}


# ── a crash between the adapter's cross and qqq_exec's own save (2026-09-28 review) ──

class _Crash(Exception):
    pass


def test_a_rerun_after_a_crash_reuses_the_booked_cross_and_never_pushes_never_held(book, monkeypatch):
    adapter, fake = book
    cfg = _cfg(NOISE=26)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "NOISE", "long", NOISE_TID)
    saved = copy.deepcopy(state)                # qqq_exec's state as last saved
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: pushes.append((a, k)))
    real_reduce = qe._reduce_lot
    calls = {"n": 0}

    def crash_on_second(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise _Crash()
        return real_reduce(*a, **k)
    monkeypatch.setattr(qe, "_reduce_lot", crash_on_second)
    with pytest.raises(_Crash):
        qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)
    # the adapter saved the cross; ORB's NETTED row is on file; NOISE's is not
    assert _sent_books(adapter) == {"ORB": 0, "NOISE": 16}
    cross_id = adapter._state["internal_crosses"][-1]["id"]
    monkeypatch.setattr(qe, "_reduce_lot", real_reduce)

    state = copy.deepcopy(saved)                # the restart reads the old state
    opens_sent = len(fake.sent)
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    assert [(o["side"], o["qty"], o["opening"]) for o in fake.sent[opens_sent:]] == \
        [("SELL", 16, False)], "only NOISE's remainder goes out; the crossed 10 never do"
    assert fake.refused == [] and fake.pos == 0
    assert state["legs"] == {}
    netted = [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["outcome"] == "NETTED"]
    assert sorted((r["leg"], r["shares"]) for r in netted) == [("NOISE", "10"), ("ORB", "10")], \
        "one allocation row per leg -- ORB's is not written twice"
    assert not [r for r in _rows(qe.BROKER_ORDERS_CSV) if "nothing to close" in r["reason"]]
    assert not [p for p in pushes if "never held" in p[0][0]]
    assert state["_crosses_booked"] == [cross_id]


def test_a_booked_cross_is_never_reused_for_other_lots(book):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)
    cross_id = adapter._state["internal_crosses"][-1]["id"]
    assert state["_crosses_booked"] == [cross_id]
    sides = {"ORB": -1, "ENGUQ": 1}
    tids = {"ORB": ORB_TID, "ENGUQ": ENGUQ_TID}
    assert qe._replay_internal_cross(state, adapter, sides, tids, log=NOOP) is None, "already booked"
    other = {"ORB": "ORB_R6-20260928T150000Z-S", "ENGUQ": ENGUQ_TID}
    assert qe._replay_internal_cross({"legs": {}}, adapter, sides, other, log=NOOP) is None, \
        "a different trade id never matches"


def test_three_legs_cross_what_offsets_and_send_one_closing_order(book):
    adapter, fake = book
    cfg = _cfg(NOISE=20, ENGUQ=5)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "long", "ORB_R6-20260928T134000Z-L")    # +10
    _open(state, cfg, "NOISE", "short", "NOISE_382-20260928T150000Z-S")   # -20
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)                     # +5
    assert fake.pos == -5
    opens_sent = len(fake.sent)

    fake.async_fills = True
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)

    assert [(o["side"], o["qty"], o["opening"]) for o in fake.sent[opens_sent:]] == [("BUY", 5, False)]
    assert fake.refused == []
    fake.fill_pending()
    assert fake.pos == 0 and sum(_sent_books(adapter).values()) == 0


# ── close_retry and the refused-order path: never a double close ─────────────────────

def test_a_refused_remainder_retries_only_the_remainder_and_never_double_closes(book, monkeypatch):
    adapter, fake = book
    cfg = _cfg(NOISE=26)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "NOISE", "long", NOISE_TID)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    real_place = fake._place
    calls = {"n": 0}

    def refuse_once(a, o):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("ServerException: HTTP Status: 417, Code: OPENAPI_X, Msg: busy")
        return real_place(a, o)
    fake.order_v3.place_order.side_effect = refuse_once

    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)
    item = state["_broker_resend"][f"NOISE:CLOSE:{NOISE_TID}"]
    assert item["why"] == "close_retry" and int(item["shares"]) == 16

    clock[0] += 6
    qe._maybe_resend_broker_orders(state, cfg, FLAT_AT + datetime.timedelta(seconds=6), True, log=NOOP)
    assert state.get("_broker_resend") == {}
    sells = [o for o in fake.sent if o["side"] == "SELL"]
    assert [o["qty"] for o in sells] == [16], "the crossed 10 are never sold at Webull"
    assert fake.pos == 0 and _sent_books(adapter) == {"ORB": 0, "NOISE": 0}


# ── KILL and BREAKER share the same flatten ───────────────────────────────────────────

@pytest.mark.parametrize("reason", ["KILL", "BREAKER"])
def test_kill_and_breaker_flatten_cross_too(book, reason):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    opens_sent = len(fake.sent)
    fake.async_fills = True
    qe._close_all(state, cfg, reason, None, None, log=NOOP,
                  nowdt=datetime.datetime(2026, 9, 28, 11, 30))
    assert fake.sent[opens_sent:] == [] and fake.refused == []
    assert state["legs"] == {} and _sent_books(adapter) == {"ORB": 0, "ENGUQ": 0}


def test_no_cross_in_off_mode_the_would_be_orders_are_recorded_as_before(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir()
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (CROSS_PX, "live_stream"))
    cfg_b = _broker_cfg(tmp_path)
    cfg_b["mode"] = "OFF"
    adapter = WO.OrderAdapter(config=cfg_b, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP, nowdt=FLAT_AT)
    closes = [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["intent"] == "CLOSE"]
    assert [(r["leg"], r["mode"]) for r in closes] == [("ORB", "OFF"), ("ENGUQ", "OFF")]


# ── AFTER-CLOSE GUARD: no broker order after the bell ────────────────────────────────

def test_mirror_after_the_close_is_blocked_without_touching_the_adapter(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir()
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    adapter = MagicMock()
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    for intent in ("OPEN", "CLOSE"):
        qe._mirror_to_broker(state, leg="ORB", side="short", shares=10, shadow_px=736.5,
                             intent=intent, trade_id=ORB_TID,
                             nowdt=datetime.datetime(2026, 9, 28, 16, 0, 1), log=NOOP)
    assert not [c for c in adapter.method_calls if c[0] != "status"], \
        "no adapter call after the close but the blocked CLOSE's read-only status check"
    assert state.get("_broker_resend", {}) == {}, "nothing queued to retry after the bell"
    rows = _rows(qe.BROKER_ORDERS_CSV)
    assert [r["outcome"] for r in rows] == ["BLOCKED", "BLOCKED"]
    assert all("market closed" in r["reason"] for r in rows)


def test_the_close_guard_is_seconds_exact_and_follows_a_half_day():
    assert not qe._market_closed_for_orders(datetime.datetime(2026, 9, 28, 15, 59, 59))
    assert qe._market_closed_for_orders(datetime.datetime(2026, 9, 28, 16, 0, 0))
    # 2026-11-27, the day after Thanksgiving, closes at 13:00
    assert qe._market_closed_for_orders(datetime.datetime(2026, 11, 27, 13, 0, 0))
    assert not qe._market_closed_for_orders(datetime.datetime(2026, 11, 27, 12, 59, 59))
    # not a session day: the guard stays out of the way
    assert not qe._market_closed_for_orders(datetime.datetime(2026, 9, 27, 17, 0, 0))


def test_a_close_blocked_after_the_bell_pushes_once_while_the_adapter_holds_shares(book, monkeypatch):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: pushes.append((a, k)))
    opens_sent = len(fake.sent)
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP,
                  nowdt=datetime.datetime(2026, 9, 28, 16, 0, 5))
    assert fake.sent[opens_sent:] == []
    high = [p for p in pushes if p[1].get("priority") == "high"]
    assert len(high) == 1 and "after the bell" in high[0][0][0] and "10 share(s)" in high[0][0][0]
    # a second blocked CLOSE for the same leg that day does not push again
    qe._mirror_to_broker(state, leg="ORB", side="short", shares=10, shadow_px=736.5,
                         intent="CLOSE", trade_id=ORB_TID,
                         nowdt=datetime.datetime(2026, 9, 28, 16, 1, 0), log=NOOP)
    assert len([p for p in pushes if p[1].get("priority") == "high"]) == 1
    # a blocked OPEN never pushes
    qe._mirror_to_broker(state, leg="NOISE", side="long", shares=10, shadow_px=736.5,
                         intent="OPEN", trade_id=NOISE_TID,
                         nowdt=datetime.datetime(2026, 9, 28, 16, 1, 0), log=NOOP)
    assert len([p for p in pushes if p[1].get("priority") == "high"]) == 1


def test_a_close_blocked_after_the_bell_does_not_push_for_a_leg_webull_never_held(book, monkeypatch):
    adapter, fake = book
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: pushes.append((a, k)))
    state = {"legs": {}, "events": [], "_px_source": "test"}
    qe._mirror_to_broker(state, leg="ORB", side="short", shares=10, shadow_px=736.5,
                         intent="CLOSE", trade_id=ORB_TID,
                         nowdt=datetime.datetime(2026, 9, 28, 16, 0, 5), log=NOOP)
    assert pushes == []


def test_the_orphan_repair_passes_its_tick_clock_to_the_after_close_guard(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir()
    trigger = out / "FLATTEN_BROKER"
    trigger.write_text("", encoding="utf-8")
    adapter = MagicMock()
    adapter.status.return_value = {"believed_positions": {"ENGUQ": {"symbol": "QQQ", "qty": 10}}}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (736.5, "test"))
    seen = []
    monkeypatch.setattr(qe, "_mirror_to_broker", lambda state, **k: seen.append(k))
    cfg = _cfg()
    cfg["flatten_broker_file"] = str(trigger)
    nowdt = datetime.datetime(2026, 9, 28, 10, 0, 0)
    qe._maybe_flatten_orphan_broker({"legs": {}, "events": []}, cfg, nowdt, log=NOOP)
    assert len(seen) == 1 and seen[0]["nowdt"] == nowdt


def test_flatten_after_the_close_never_crosses_or_sends(book):
    adapter, fake = book
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _open(state, cfg, "ORB", "short", ORB_TID)
    _open(state, cfg, "ENGUQ", "long", ENGUQ_TID)
    opens_sent = len(fake.sent)
    qe._close_all(state, cfg, "EOD", None, None, log=NOOP,
                  nowdt=datetime.datetime(2026, 9, 28, 16, 0, 5))
    assert fake.sent[opens_sent:] == []
    assert _sent_books(adapter) == {"ORB": -10, "ENGUQ": 10}, "books untouched after the bell"
    assert state.get("_broker_resend", {}) == {}


# ── engine rows consumed after the close / after flat_by ─────────────────────────────

def _entry_event(leg_engine, ref_time, side, px=736.5):
    tid = T.make(leg_engine, ref_time, side)
    return {"leg": leg_engine, "event": "ENTRY", "side": side, "ref_time": ref_time,
            "ref_price": px, "bar_source": "webull", "trade_id": tid, "size": "1.0",
            "keel_size": "", "reason": ""}


@pytest.mark.parametrize("now,ref_time", [
    (datetime.datetime(2026, 9, 28, 16, 0, 35), "2026-09-28T15:50:00-04:00"),   # after the bell
    (datetime.datetime(2026, 9, 28, 15, 59, 20), "2026-09-28T15:50:00-04:00"),  # past flat_by
    (datetime.datetime(2026, 9, 28, 15, 58, 5), "2026-09-28T15:50:00-04:00"),   # last minute before flat_by
    (datetime.datetime(2026, 9, 28, 15, 55, 20), "2026-09-28T15:56:00-04:00"),  # bar after last_entry
])
def test_engine_entry_too_late_is_never_opened_or_sent(tmp_path, monkeypatch, now, ref_time):
    out = tmp_path / "qqq_out"
    out.mkdir()
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    adapter = MagicMock()
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    qe._route_engine_events(state, _cfg(), [_entry_event("ORB_R6", ref_time, "short")],
                            False, log=NOOP, now=now)
    assert state["legs"] == {}
    assert adapter.method_calls == []
    refused = [r for r in _rows(qe.ORDERS_CSV) if "REFUSED" in (r.get("reason") or "")]
    assert refused, "the refusal is on the record"


@pytest.mark.parametrize("now", [
    datetime.datetime(2026, 9, 28, 15, 55, 20),
    # 2026-09-28 review: the 15:50 bar's entry consumed after 15:55:59 (fetch throttle +
    # REST latency, or one failed fetch) -- the backtest takes it, so live does too
    datetime.datetime(2026, 9, 28, 15, 56, 5),
    datetime.datetime(2026, 9, 28, 15, 57, 59),
])
def test_engine_entry_inside_the_window_still_opens(tmp_path, monkeypatch, now):
    out = tmp_path / "qqq_out"
    out.mkdir()
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    state = {"legs": {}, "events": [], "_px_source": "test"}
    qe._route_engine_events(state, _cfg(), [_entry_event("ORB_R6", "2026-09-28T15:50:00-04:00", "short")],
                            False, log=NOOP, now=now)
    assert "ORB" in state["legs"]


def test_post_close_exit_with_no_lot_records_the_backtest_price_and_sends_nothing(tmp_path, monkeypatch):
    adapter = MagicMock()
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"legs": {}, "events": [], "_px_source": "test", "flat_by_done_date": "2026-09-28"}
    ev = {"leg": "ORB_R6", "event": "EXIT", "side": "short",
          "ref_time": "2026-09-28T15:55:00-04:00", "ref_price": 736.54, "bar_source": "webull",
          "trade_id": ORB_TID, "size": "1.0", "keel_size": "",
          "reason": "strategy_exit; eod_settle"}
    qe._route_engine_events(state, _cfg(), [ev], False, log=NOOP,
                            now=datetime.datetime(2026, 9, 28, 16, 0, 35))
    assert adapter.method_calls == []
    assert state["backtest_eod_exits"][ORB_TID]["px"] == 736.54
    assert not (state.get("trade_id_checks") or {}).get("today"), "not an exit_no_lot warning"
    rows = [{"trade_id": ORB_TID}, {"trade_id": "other"}]
    qe._merge_backtest_exits(rows, state)
    assert rows[0]["backtest_exit_px"] == 736.54 and "backtest_exit_px" not in rows[1]


def test_post_close_exit_for_a_lot_still_open_closes_the_shadow_only(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir()
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    adapter = MagicMock()
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    cfg = _cfg()
    state = {"legs": {}, "events": [], "_px_source": "test"}
    tid = T.make("ORB_R6", "2026-09-28T13:40:00Z", "short")
    qe._route_engine_events(state, cfg, [_entry_event("ORB_R6", "2026-09-28T13:40:00Z", "short")],
                            False, log=NOOP, now=datetime.datetime(2026, 9, 28, 9, 45))
    assert "ORB" in state["legs"]
    adapter.reset_mock()
    ev = {"leg": "ORB_R6", "event": "EXIT", "side": "short",
          "ref_time": "2026-09-28T15:55:00-04:00", "ref_price": 736.54, "bar_source": "webull",
          "trade_id": tid, "size": "1.0", "keel_size": "", "reason": "strategy_exit; eod_settle"}
    qe._route_engine_events(state, cfg, [ev], False, log=NOOP,
                            now=datetime.datetime(2026, 9, 28, 16, 0, 35))
    assert state["legs"] == {}
    assert not [c for c in adapter.method_calls if c[0] != "status"], \
        "the broker mirror is refused after the bell (only a read-only status check)"
    trades = _rows(qe.TRADES_CSV)
    assert trades and trades[-1]["exit_reason"].startswith("EOD settle (backtest)")


# ── the adapter's own session rail: the end is exclusive, to the second ──────────────

@pytest.mark.parametrize("hms,allowed", [("15:59:59", True), ("16:00:00", False),
                                         ("16:00:59", False), ("09:30:00", True),
                                         ("09:29:59", False)])
def test_adapter_session_rail_refuses_an_open_from_16_00_00(tmp_path, monkeypatch, hms, allowed):
    cfg = _broker_cfg(tmp_path)
    cfg["mode"] = "OFF"
    cfg["rails"]["session_start"] = "09:30"
    cfg["rails"]["session_end"] = "16:00"
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    h, m, s = (int(x) for x in hms.split(":"))
    monkeypatch.setattr(WO, "_now_ny", lambda: datetime.datetime(2026, 9, 28, h, m, s))
    rec = adapter.place_stock_order(leg="ORB", signal_id=f"t{h}{m}{s}", symbol="QQQ",
                                    side="BUY", qty=10, intent="OPEN")
    assert (rec["mode"] != "BLOCKED") is allowed, rec.get("reason")
    # a CLOSE is never blocked by the entry rails (never trap a position)
    ok, _why = adapter._check_rails("ORB", 10, "CLOSE")
    assert ok


def test_adapter_session_rail_end_of_23_59_still_means_all_day(tmp_path, monkeypatch):
    cfg = _broker_cfg(tmp_path)
    cfg["mode"] = "OFF"
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    monkeypatch.setattr(WO, "_now_ny", lambda: datetime.datetime(2026, 9, 28, 23, 59, 30))
    assert adapter._in_session_window({"session_start": "00:00", "session_end": "23:59"})


# ── the order log keeps its own 2000-row history (inventory finding 2026-10-01) ──────
def test_internal_cross_row_keeps_the_order_logs_2000_row_history(tmp_path, monkeypatch):
    """_record_internal_cross used to append with ORDERS_KEEP (100): the first 15:59 cross
    would have cut broker_orders.csv to 100 rows, so older trades lost their Webull fill
    (P&L of record, parity and candle marks fall back to the book)."""
    path = tmp_path / "broker_orders.csv"
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(path))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        for i in range(150):
            w.writerow({"ts_et": f"2026-09-0{1 + i % 9} 10:00:00", "leg": "NOISE", "intent": "OPEN",
                        "side": "BUY", "shares": 10, "signal_id": f"qxOLD{i}", "ok": True,
                        "sent": True, "outcome": "OK"})
    qe._record_internal_cross({}, leg="ORB", side="short", shares=10, shadow_px=736.76,
                              cross={"px": 736.7, "against": "NOISE", "id": "x1",
                                     "reason": "flatten"},
                              ts="2026-09-28 15:59:01", seq=0, trade_id="ORB_R6-20260928T144500Z-S",
                              partial=False, log=lambda *a, **k: None)
    rows = _rows(str(path))
    assert len(rows) == 151 and rows[0]["signal_id"] == "qxOLD0"
    assert rows[-1]["outcome"] == "NETTED"


def test_every_order_log_append_uses_the_order_logs_own_cap():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(qe))
    caps = [c.args[3].id for c in ast.walk(tree)
            if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_append_csv"
            and len(c.args) >= 4 and getattr(c.args[0], "id", None) == "BROKER_ORDERS_CSV"]
    assert caps and set(caps) == {"BROKER_ORDERS_KEEP"}, caps
