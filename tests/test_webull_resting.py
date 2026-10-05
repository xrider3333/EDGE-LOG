"""RESTING ORDERS AND THE ORDER GATEWAY (2026-09-29, owner GO via MANAGER) --
api.webull_orders.OrderAdapter's resting ORB stop / OCO target lifecycle and the
cancel-first / previous-order-terminal gateway in place_stock_order.

FakeWebullBook models ONE Webull paper account on QQQ the way the 2026-09-29 paper probe
(tools/webull_resting_probe.py) and the 09-28 15:59:01 refusal showed it behaves:
  * the box rule -- a buy-OPENING and a sell-OPENING order may not both be pending
    (417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER), for resting AND market orders;
  * side validation -- SELL needs a long, SHORT needs no long (417 side not match);
  * reserved shares -- a pending closing order holds the shares it would sell / cover;
  * asynchronous fills -- a market order acks SUBMITTED and fills on its first lookup,
    position read or step() (never, while `market_stuck`);
  * stops and limits triggered by a scripted price path (set_price), whole or partial;
  * cancel lag (a cancel shows CANCELLED on the second lookup), cancel races (the order
    fills as the cancel arrives), lookups that time out;
  * OCO legs where cancelling -- or filling -- one leaves the other live (the probe: a
    cancelled leg's sibling stayed SUBMITTED; auto-cancel on a fill is unverified);
  * replace_order moving a stop in place, refused, or racing a fill;
  * DAY expiry (close_session) and a restart on the same state file.
No real SDK, network or credentials; tests/conftest.py makes the adapter's waits instant.
"""
import os
import sys
import datetime
import json
from unittest.mock import MagicMock

import pytest

from api import webull_orders as WO

# One generous deadline for every real-thread wait in the suite - see tests/_threadwait.py
# for why a long deadline cannot mask a bug and a short one blocked every lane's push.
_THREADWAIT_DIR = os.path.dirname(os.path.abspath(__file__))
if _THREADWAIT_DIR not in sys.path:
    sys.path.insert(0, _THREADWAIT_DIR)
from _threadwait import WAIT_SECONDS  # noqa: E402

NOOP = lambda *a, **k: None  # noqa: E731
TID = "ORB_314-20260929T143500Z-L"
SYM = "QQQ"


class ServerException(Exception):
    pass


def _417(code, msg="refused"):
    return ServerException(f"HTTP Status: 417, Code: {code}, Msg: {msg}")


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


LIVE = ("PENDING", "SUBMITTED", "PARTIAL_FILLED")


class FakeWebullBook:
    """One account, one symbol. `order_v3` is the book itself."""

    def __init__(self, price=500.0, pos=0):
        self.price = price
        self.pos = pos
        self.orders = {}            # coid -> order dict (Webull's view)
        self.calls = []             # (method, coid-or-detail)
        self.market_stuck = False
        self.cancel_lag = 1         # lookups after a cancel that still read SUBMITTED
        self.cancel_fills = set()   # coids that fill as their cancel arrives (race)
        self.replace_fills = set()  # coids that fill as a replace arrives
        self.replace_fail = False
        self.detail_down = False
        self.detail_fail = {}       # coid -> lookups that time out first
        self.place_raise = []       # exceptions for the next place_order calls
        self.place_lands = True     # a place_order that raises (non-4xx) still landed?
        self.partial = {}           # coid -> shares a trigger fills
        self.oco_auto_cancel = False
        self.on_place = None        # hook(book, orders) before a place is judged
        self.order_v3 = self
        self.account_v2 = MagicMock()
        self.account_v2.get_account_list.return_value.json.return_value = {
            "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
        self.account_v2.get_account_position.side_effect = self._positions

    # -- Webull's rules --
    def _live(self):
        return {c: o for c, o in self.orders.items() if o["status"] in LIVE}

    def _reserved(self, side_kind):
        """Shares pending closing orders hold (an OCO group counted once)."""
        seen, total = set(), 0
        for o in self._live().values():
            if o["kind"] != side_kind:
                continue
            key = o.get("combo") or o["coid"]
            if key in seen:
                continue
            seen.add(key)
            total += o["qty"] - o["filled"]
        return total

    def _judge(self, side, qty):
        """(opening, direction) or raise the 417 Webull would."""
        if side == "SELL":
            if self.pos <= 0:
                raise _417("OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION", "no long to sell")
            if qty > self.pos - self._reserved("close_sell"):
                raise _417("OPENAPI_INSUFFICIENT_POSITION", "exceeds the available position")
            kind = "close_sell"
        elif side == "SHORT":
            if self.pos > 0:
                raise _417("OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION", "close your long first")
            kind = "open_sell"
        else:
            if self.pos < 0:
                if qty > -self.pos - self._reserved("close_buy"):
                    raise _417("OPENAPI_INSUFFICIENT_POSITION", "exceeds the short to cover")
                kind = "close_buy"
            else:
                kind = "open_buy"
        if kind.startswith("open"):
            other = "open_buy" if kind == "open_sell" else "open_sell"
            if any(o["kind"] == other for o in self._live().values()):
                raise _417("OPENAPI_OPEN_ORDER_HAS_BOX_ORDER",
                           "Buy opening orders and sell opening orders cannot exist simultaneously")
        return kind

    # -- order_v3 --
    def place_order(self, account_id, new_orders, client_combo_order_id=None):
        self.calls.append(("place", [o["client_order_id"] for o in new_orders]))
        if self.on_place:
            self.on_place(self, new_orders)
        exc = self.place_raise.pop(0) if self.place_raise else None
        if exc is not None and "HTTP Status: 4" in str(exc):
            raise exc
        if exc is not None and not self.place_lands:
            raise exc
        first = new_orders[0]
        kind = self._judge(first["side"], int(first["quantity"]))
        for o in new_orders:
            self.orders[o["client_order_id"]] = {
                "coid": o["client_order_id"], "side": o["side"], "type": o["order_type"],
                "qty": int(o["quantity"]), "stop": float(o["stop_price"]) if "stop_price" in o else None,
                "limit": float(o["limit_price"]) if "limit_price" in o else None,
                "status": "SUBMITTED", "filled": 0, "px": None, "kind": kind,
                "combo": client_combo_order_id, "combo_type": o["combo_type"],
                "tif": o["time_in_force"], "session": o["support_trading_session"],
                "lookups": 0, "cancel_at": None, "raw": dict(o)}
        if exc is not None:
            raise exc
        return _Resp({"client_order_id": first["client_order_id"]})

    def _fill(self, o, shares, px):
        shares = min(shares, o["qty"] - o["filled"])
        o["filled"] += shares
        o["px"] = px
        self.pos += shares if o["side"] == "BUY" else -shares
        o["status"] = "FILLED" if o["filled"] >= o["qty"] else "PARTIAL_FILLED"
        if o["status"] == "FILLED" and o.get("combo") and self.oco_auto_cancel:
            for s in self._live().values():
                if s.get("combo") == o["combo"]:
                    s["status"] = "CANCELLED"

    def _progress(self, o):
        """What time does to one order before it is read."""
        if o["status"] not in LIVE:
            return
        if o["cancel_at"] is not None:
            if o["cancel_at"] <= 0:
                o["status"] = "CANCELLED"
            else:
                o["cancel_at"] -= 1
            return
        if o["type"] == "MARKET" and not self.market_stuck:
            self._fill(o, o["qty"], self.price)

    def step(self):
        for o in list(self._live().values()):
            self._progress(o)

    def set_price(self, px):
        """The tape trades at `px`: stops and limits trigger (in placement order)."""
        self.price = px
        for o in list(self.orders.values()):
            if o["status"] not in LIVE or o["cancel_at"] is not None:
                continue
            hit = False
            if o["type"] == "STOP_LOSS":
                hit = px >= o["stop"] if o["side"] == "BUY" else px <= o["stop"]
            elif o["type"] == "LIMIT":
                hit = px <= o["limit"] if o["side"] == "BUY" else px >= o["limit"]
            if hit:
                fill_px = o["limit"] if o["type"] == "LIMIT" else px
                self._fill(o, self.partial.get(o["coid"], o["qty"]), fill_px)

    def close_session(self):
        for o in self._live().values():
            o["status"] = "EXPIRED"

    def cancel_order(self, account_id, client_order_id):
        self.calls.append(("cancel", client_order_id))
        o = self.orders.get(client_order_id)
        if o is None:
            raise _417("OPENAPI_ORDER_NOT_FOUND", "no such order")
        if client_order_id in self.cancel_fills and o["status"] in LIVE:
            self.cancel_fills.discard(client_order_id)
            self._fill(o, o["qty"], o["stop"] or o["limit"] or self.price)
        if o["status"] not in LIVE:
            raise _417("OPENAPI_ORDER_STATUS_NOT_ALLOW_CANCEL", "order already final")
        if o["cancel_at"] is None:
            o["cancel_at"] = self.cancel_lag
        return _Resp({"client_order_id": client_order_id})

    def replace_order(self, account_id, modify_orders, client_combo_order_id=None):
        self.calls.append(("replace", [m["client_order_id"] for m in modify_orders]))
        for m in modify_orders:
            o = self.orders.get(m["client_order_id"])
            if m["client_order_id"] in self.replace_fills and o["status"] in LIVE:
                self._fill(o, o["qty"], self.price)
            if self.replace_fail or o is None or o["status"] not in LIVE:
                raise _417("OPENAPI_ORDER_STATUS_NOT_ALLOW_MODIFY", "cannot modify")
            o["stop"] = float(m["stop_price"])
        return _Resp({})

    def _view(self, o):
        return {"client_order_id": o["coid"], "symbol": SYM, "side": o["side"],
                "order_type": o["type"], "status": o["status"], "quantity": str(o["qty"]),
                "filled_quantity": None if o.get("filled_unknown") else str(o["filled"]),
                "filled_price": None if o["px"] is None else str(o["px"]),
                "stop_price": None if o["stop"] is None else f"{o['stop']:.2f}",
                "limit_price": None if o["limit"] is None else f"{o['limit']:.2f}",
                "combo_type": o["combo_type"], "time_in_force": o["tif"]}

    def get_order_detail(self, account_id, client_order_id):
        self.calls.append(("detail", client_order_id))
        if self.detail_down:
            raise TimeoutError("read timed out")
        if self.detail_fail.get(client_order_id):
            self.detail_fail[client_order_id] -= 1
            raise TimeoutError("read timed out")
        o = self.orders.get(client_order_id)
        if o is None:
            raise _417("OPENAPI_ORDER_NOT_FOUND", "no such order")
        self._progress(o)
        return _Resp({"client_order_id": client_order_id, "orders": [self._view(o)]})

    def get_order_open(self, account_id, page_size=None, last_client_order_id=None):
        self.calls.append(("open", None))
        return _Resp({"data": [{"client_order_id": o["coid"], "orders": [self._view(o)]}
                               for o in self._live().values()]})

    def _positions(self, account_id):
        self.step()
        if not self.pos:
            return _Resp({"data": []})
        return _Resp({"data": [{"symbol": SYM, "quantity": str(abs(self.pos)),
                                "side": "SHORT" if self.pos < 0 else "LONG"}]})

    # -- helpers for asserts --
    def sent(self, method):
        return [c for m, c in self.calls if m == method]

    def placed_types(self):
        return [(o["side"], o["type"], o["qty"]) for o in self.orders.values()]


# ── fixtures ────────────────────────────────────────────────────────────────────────

def _cfg(tmp_path, mode="PAPER"):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = mode
    cfg["rails"].update(session_start="00:00", session_end="23:59",
                        max_shares_per_leg=100, max_total_position_shares=500)
    for k, name in (("state_path", "state.json"), ("paper_keys_path", "paper_keys.json"),
                    ("live_keys_path", "live_keys.json"), ("arm_live_file", "ARM_LIVE"),
                    ("kill_file", "KILL")):
        cfg[k] = str(tmp_path / name)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    return cfg


def _adapter(tmp_path, monkeypatch, book, mode="PAPER", log=NOOP):
    adapter = WO.OrderAdapter(config=_cfg(tmp_path, mode), log=log)
    monkeypatch.setattr(adapter, "_build_client", lambda m: book)
    return adapter


@pytest.fixture
def book():
    return FakeWebullBook()


def _seed(adapter, book, **legs):
    """Legs already held at the broker (booked AND at Webull)."""
    for leg, qty in legs.items():
        adapter._state.setdefault("broker_sent_positions", {})[leg] = {
            "symbol": SYM, "qty": qty, "account_id": "ACCT1"}
        adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": SYM, "qty": qty}
        adapter._state.setdefault("open_legs", {})[leg] = True
        book.pos += qty


def _sent(adapter, leg):
    return (adapter._state.get("broker_sent_positions") or {}).get(leg, {}).get("qty", 0)


def _arm(adapter, qty=10, direction="SELL", stop=495.0, limit=None, **kw):
    return adapter.place_resting(leg="ORB", trade_id=TID, symbol=SYM, direction=direction,
                                 qty=qty, stop_price=stop, limit_price=limit, **kw)


def _order(adapter, leg, signal, side, qty, intent="OPEN"):
    return adapter.place_stock_order(leg=leg, signal_id=signal, symbol=SYM, side=side,
                                     qty=qty, intent=intent)


# ── ids and the side table ──────────────────────────────────────────────────────────

def test_ids_fit_webull_and_are_new_per_rearm():
    p1, t1, k1 = WO.resting_ids(TID, 1)
    p2, t2, k2 = WO.resting_ids(TID, 2)
    assert p1 == "qxORB31420260929T143500ZLP1" and t1.endswith("T1") and k1.endswith("K1")
    assert len({p1, t1, k1, p2, t2, k2}) == 6
    for i in (p1, t1, k1, WO.resting_ids(TID, 123)[0]):
        assert len(i) <= WO.CLIENT_ORDER_ID_MAX and i.isalnum()
        assert WO._sanitize_client_order_id(i) == i
    long_tid = "SOME_VERY_LONG_LEG_NAME_999-20260929T143500Z-L"
    a = WO.resting_ids(long_tid, 7)
    assert a == WO.resting_ids(long_tid, 7)
    assert all(len(i) <= 32 and i.isalnum() for i in a) and a[0].endswith("P7")


@pytest.mark.parametrize("net,direction,qty,side", [
    (10, "SELL", 10, "SELL"), (30, "SELL", 10, "SELL"), (0, "SELL", 10, "SHORT"),
    (-10, "SELL", 10, "SHORT"), (5, "SELL", 10, None), (3, "SELL", 10, None),
    (-10, "BUY", 10, "BUY"), (-30, "BUY", 10, "BUY"), (0, "BUY", 10, "BUY"),
    (20, "BUY", 10, "BUY"), (-5, "BUY", 10, None), (-7, "BUY", 10, None)])
def test_side_table(net, direction, qty, side):
    assert WO.plan_resting_side(net, direction, qty) == side


@pytest.mark.parametrize("noise,outcome,side", [
    (0, "RESTING", "SELL"), (20, "RESTING", "SELL"), (-10, "RESTING", "SHORT"),
    (-20, "RESTING", "SHORT"), (-5, "CROSSING", None), (-7, "CROSSING", None)])
def test_arm_side_follows_the_account_net(tmp_path, monkeypatch, book, noise, outcome, side):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, **({"NOISE": noise} if noise else {}))
    rec = _arm(ad)
    assert rec["outcome"] == outcome and rec["side"] == side
    if side is None:
        assert book.sent("place") == []
    else:
        assert [o["side"] for o in book.orders.values()] == [side]
    assert ad.resting_plan(SYM, "SELL", 10)["side"] == (side if outcome == "RESTING" else None)


# ── placement ───────────────────────────────────────────────────────────────────────

def test_stop_is_pending_on_disk_before_the_send_and_never_booked_on_the_ack(
        tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    seen = {}

    def hook(b, orders):
        with open(ad._state_path(), encoding="utf-8") as f:
            seen.update(json.load(f)["resting"])
    book.on_place = hook
    rec = _arm(ad, stop=494.995)
    p = WO.resting_ids(TID, 1)[0]
    assert seen[p]["status"] == "PENDING" and seen[p]["pending"] is True
    assert rec["ok"] and rec["outcome"] == "RESTING" and rec["client_order_ids"] == [p]
    raw = book.orders[p]["raw"]
    assert raw["order_type"] == "STOP_LOSS" and raw["stop_price"] == "495.00"
    assert raw["side"] == "SELL" and raw["quantity"] == "10" and raw["combo_type"] == "NORMAL"
    assert raw["time_in_force"] == "DAY" and raw["support_trading_session"] == "CORE"
    assert _sent(ad, "ORB") == 10 and ad._state["order_parts"][p]["booked"] == 0
    assert ad._state["resting"][p]["live"] and not ad._state["resting"][p]["pending"]
    assert ad.take_resting_events() == []


def test_off_mode_never_reaches_webull(tmp_path, monkeypatch):
    ad = WO.OrderAdapter(config=_cfg(tmp_path, "OFF"), log=NOOP)

    def boom(mode):
        raise AssertionError("OFF built a client")
    monkeypatch.setattr(ad, "_build_client", boom)
    assert _arm(ad)["outcome"] == "NOT_SENT"
    assert ad.cancel_resting()["ok"] and ad.resolve_resting() is None
    assert ad.open_orders() == [] and ad.boot_sweep() is None
    assert "resting" not in ad._state and "resting_seq" not in ad._state


def test_refusals_send_nothing(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    assert _arm(ad, qty=11)["outcome"] == "NOT_SENT"                 # more than the leg holds
    assert _arm(ad, direction="BUY", stop=505)["outcome"] == "NOT_SENT"   # wrong direction
    r = _arm(ad, last_price=494.5)
    assert r["outcome"] == "CROSSED" and r["crossed"] == "stop"
    r = _arm(ad, limit=510.0, last_price=510.5)
    assert r["outcome"] == "CROSSED" and r["crossed"] == "target"
    ad._halted, ad._halt_source, ad._halt_reason = True, "reconcile", "mismatch"
    assert _arm(ad)["outcome"] == "BLOCKED"
    ad._halted = False
    ad._halt_source = None
    assert book.sent("place") == []
    with pytest.raises(ValueError):
        _arm(ad, limit=490.0)                                          # target behind the stop
    open(ad._kill_file(), "w").close()                                 # protection still arms
    assert _arm(ad)["outcome"] == "RESTING"
    assert _arm(ad)["outcome"] == "BUSY"                               # one group at a time
    assert len(book.sent("place")) == 1


def test_no_arm_while_an_earlier_order_is_still_working(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.market_stuck = True
    assert _order(ad, "NOISE", "qxNOISEO", "BUY", 5)["ok"]
    r = _arm(ad)
    assert r["outcome"] == "BUSY" and "not yet FILLED" in r["reason"]
    assert [o["type"] for o in book.orders.values()] == ["MARKET"]


def test_a_refused_stop_is_dead_and_frees_the_symbol(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.place_raise = [_417("OPENAPI_TEST_REFUSAL")]
    r = _arm(ad)
    assert r["outcome"] == "REFUSED" and r["http_status"] == 417 and not r["ok"]
    assert ad._live_resting() == []
    r = _arm(ad)
    assert r["outcome"] == "RESTING" and r["n"] == 2       # a new id after the refusal


def test_send_that_raised_is_resolved_by_lookup(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.place_raise = [TimeoutError("read timed out")]     # it landed anyway
    r = _arm(ad)
    assert r["outcome"] == "RESTING" and r["ok"]
    assert ad._live_resting() == [WO.resting_ids(TID, 1)[0]]


def test_send_that_never_landed_blocks_then_clears_after_the_grace(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=20)
    book.place_lands = False
    book.place_raise = [TimeoutError("read timed out")]
    r = _arm(ad)
    p = WO.resting_ids(TID, 1)[0]
    assert r["outcome"] == "UNKNOWN" and ad._state["resting"][p]["pending"]
    # the next order's gateway cannot prove it dead inside the grace: nothing sent
    rec = _order(ad, "NOISE", "qxNOISEC", "SELL", 20, intent="CLOSE")
    assert rec["outcome"] == "RESTING_UNRESOLVED" and not rec["sent"] and rec["busy"]
    assert [o["type"] for o in book.orders.values()] == []
    ad._state["resting"][p]["placed_at"] -= 60                # past the grace: never placed
    rec = _order(ad, "NOISE", "qxNOISEC2", "SELL", 20, intent="CLOSE")
    assert rec["ok"] and ad._state["resting"][p]["status"] == "NOT_PLACED"
    assert _sent(ad, "ORB") == 10 and _sent(ad, "NOISE") == 0


# ── the gateway ─────────────────────────────────────────────────────────────────────

def test_box_rule_regression_gateway_off_417_gateway_on_none(tmp_path, monkeypatch):
    # ORB +10, NOISE -10: the account is flat, so ORB's stop is a SHORT (sell-opening).
    raw = FakeWebullBook()
    (tmp_path / "a").mkdir()
    ad = _adapter(tmp_path / "a", monkeypatch, raw)
    _seed(ad, raw, ORB=10, NOISE=-10)
    # without the gateway: the same stop rests at Webull but this state does not know it
    raw.place_order("ACCT1", [{"combo_type": "NORMAL", "client_order_id": "rawP1", "symbol": SYM,
                               "order_type": "STOP_LOSS", "quantity": "10", "side": "SHORT",
                               "stop_price": "495.00", "time_in_force": "DAY",
                               "support_trading_session": "CORE"}])
    rec = _order(ad, "NOISE", "qxNOISEC", "BUY", 10, intent="CLOSE")
    assert not rec["ok"] and "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER" in rec["error"]

    book = FakeWebullBook()
    (tmp_path / "b").mkdir()
    ad = _adapter(tmp_path / "b", monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=-10)
    assert _arm(ad)["side"] == "SHORT"
    rec = _order(ad, "NOISE", "qxNOISEC", "BUY", 10, intent="CLOSE")
    assert rec["ok"], rec
    methods = [m for m, _ in book.calls]
    assert methods.index("cancel") < len(methods) - 1 - methods[::-1].index("place")
    assert book.orders[WO.resting_ids(TID, 1)[0]]["status"] == "CANCELLED"
    assert _sent(ad, "ORB") == 10 and _sent(ad, "NOISE") == 0 and ad._live_resting() == []


def test_reserved_shares_are_real_and_the_gateway_frees_them(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _arm(ad)
    with pytest.raises(ServerException, match="INSUFFICIENT"):
        book.place_order("ACCT1", [{"combo_type": "NORMAL", "client_order_id": "raw1",
                                    "symbol": SYM, "order_type": "MARKET", "quantity": "10",
                                    "side": "SELL", "time_in_force": "DAY",
                                    "support_trading_session": "CORE"}])
    # NOISE SHORT 20 on +10: gateway cancels ORB's stop, then SELL 10 + SHORT 10
    rec = _order(ad, "NOISE", "qxNOISEO", "SHORT", 20)
    assert rec["ok"] and [p["side"] for p in rec["parts"]] == ["SELL", "SHORT"]
    book.step()
    assert book.pos == -10 and _sent(ad, "NOISE") == -20 and _sent(ad, "ORB") == 10


def test_cancel_race_fill_is_booked_and_the_order_replanned(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.cancel_fills.add(p)
    rec = _order(ad, "NOISE", "qxNOISEO", "SHORT", 10)
    assert rec["ok"] and [q["side"] for q in rec["parts"]] == ["SHORT"]   # net was 0, not +10
    assert _sent(ad, "ORB") == 0 and "ORB" not in ad._state["open_legs"]
    ev = ad.take_resting_events()
    assert [(e["client_order_id"], e["status"], e["change"], e["source"]) for e in ev] == [
        (p, "FILLED", 10, "gateway")]
    assert ev[0]["filled_price"] == 495.0 and ev[0]["trade_id"] == TID
    assert ad.take_resting_events() == []


def test_cancel_unknown_nothing_sent_open_and_close(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    _arm(ad)
    book.detail_down = True
    o = _order(ad, "ENGUQ", "qxENGUQO", "BUY", 5)
    c = _order(ad, "NOISE", "qxNOISEC", "SELL", 5, intent="CLOSE")
    for rec in (o, c):
        assert rec["outcome"] == "RESTING_UNRESOLVED" and rec["busy"]
        assert not rec["ok"] and not rec["sent"] and rec["mode"] == "PAPER"
    assert [x["type"] for x in book.orders.values()] == ["STOP_LOSS"]
    assert _sent(ad, "NOISE") == 5
    book.detail_down = False
    assert _order(ad, "NOISE", "qxNOISEC2", "SELL", 5, intent="CLOSE")["ok"]


def test_engine_exit_with_a_live_stop_cancels_then_closes(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _arm(ad)
    rec = _order(ad, "ORB", "qxORB31420260929T143500ZLC", "SELL", 10, intent="CLOSE")
    assert rec["ok"] and rec["sent"] and "closed_by_resting" not in rec
    book.step()
    assert book.pos == 0 and _sent(ad, "ORB") == 0


def test_engine_exit_after_the_stop_filled_sends_nothing_and_no_never_held(
        tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.set_price(494.8)
    r = ad.resolve_resting()
    assert r["checked"] == p and r["status"] == "FILLED" and r["change"] == 10
    ev = ad.take_resting_events()
    assert ev[0]["filled_price"] == 494.8 and ev[0]["stop_price"] == 495.0
    n_place = len(book.sent("place"))
    rec = _order(ad, "ORB", "qxORB31420260929T143500ZLC", "SELL", 10, intent="CLOSE")
    assert rec["ok"] and not rec["sent"] and not rec.get("nothing_to_close")
    assert rec["closed_by_resting"]["client_order_id"] == p
    assert rec["closed_by_resting"]["filled"] == 10 and "already closed" in rec["reason"]
    assert len(book.sent("place")) == n_place
    # a later trade's CLOSE with nothing held is still "nothing to close"
    other = _order(ad, "ORB", "qxORB31420260930T143500ZLC", "SELL", 10, intent="CLOSE")
    assert other.get("nothing_to_close") and "closed_by_resting" not in other


def test_stop_fill_found_by_the_gateway_on_the_legs_own_close(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _arm(ad)
    book.set_price(494.0)                     # filled at Webull; the books do not know yet
    rec = _order(ad, "ORB", "qxORB31420260929T143500ZLC", "SELL", 10, intent="CLOSE")
    assert rec["ok"] and not rec["sent"] and rec["closed_by_resting"]
    assert book.pos == 0 and _sent(ad, "ORB") == 0


# ── previous order terminal ─────────────────────────────────────────────────────────

def test_prev_terminal_off_by_default_changes_nothing(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    book.market_stuck = True
    assert _order(ad, "NOISE", "qxNOISEO", "BUY", 10)["ok"]
    assert _order(ad, "ENGUQ", "qxENGUQO", "BUY", 5)["ok"]
    assert [m for m, _ in book.calls] == ["place", "place"]
    assert "resting" not in ad._state and "resting_live" not in ad.status()


def test_prev_terminal_waits_then_sends_or_says_busy(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    ad.set_prev_terminal(True)
    book.market_stuck = True
    noise = _order(ad, "NOISE", "qxNOISEO", "BUY", 10)
    assert noise["ok"]
    busy = _order(ad, "ENGUQ", "qxENGUQO", "BUY", 5)
    assert busy["outcome"] == "NOT_SENT" and busy["busy"] and not busy["sent"]
    assert "qxNOISEO" in busy["reason"] and len(book.sent("place")) == 1
    book.market_stuck = False
    ok = _order(ad, "ENGUQ", "qxENGUQOR1", "BUY", 5)
    assert ok["ok"] and ad._state["order_parts"]["qxNOISEO"]["final_status"] == "FILLED"


def test_prev_terminal_books_a_dead_part_and_queues_its_event(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    ad.set_prev_terminal(True)
    book.market_stuck = True
    assert _order(ad, "NOISE", "qxNOISEO", "BUY", 10)["ok"]
    book.orders["qxNOISEO"]["status"] = "CANCELLED"      # Webull killed it unfilled
    assert _order(ad, "ENGUQ", "qxENGUQO", "BUY", 5)["ok"]
    assert _sent(ad, "NOISE") == 0
    assert [e["change"] for e in ad.take_part_events()] == [-10]


def test_prev_terminal_from_config(tmp_path, monkeypatch, book):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"gateway": {"prev_terminal": True}}), encoding="utf-8")
    assert WO.load_config(str(cfg_path))["gateway"]["prev_terminal"] is True
    assert WO.load_config("__no_such_file__")["gateway"]["prev_terminal"] is False


# ── replace (breakeven) ─────────────────────────────────────────────────────────────

def test_breakeven_replace_in_place(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    r = ad.replace_resting(p, stop_price=500.25)
    assert r["ok"] and r["outcome"] == "REPLACED"
    assert book.orders[p]["stop"] == 500.25 and ad._state["resting"][p]["stop_price"] == 500.25
    assert len(book.sent("place")) == 1
    r = ad.replace_resting(p, stop_price=501.0, last_price=500.9)
    assert r["outcome"] == "CROSSED" and book.orders[p]["stop"] == 500.25


def test_breakeven_replace_refused_falls_back_to_cancel_and_new_id(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p1 = _arm(ad)["client_order_ids"][0]
    book.replace_fail = True
    r = ad.replace_resting(p1, stop_price=500.25)
    p2 = WO.resting_ids(TID, 2)[0]
    assert r["ok"] and r["outcome"] == "REARMED" and r["placed"]["client_order_ids"] == [p2]
    assert book.orders[p1]["status"] == "CANCELLED" and book.orders[p2]["stop"] == 500.25
    assert ad._live_resting() == [p2]


def test_breakeven_replace_race_books_the_fill_and_places_nothing(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.replace_fills.add(p)
    r = ad.replace_resting(p, stop_price=500.25)
    assert r["outcome"] == "FILLED" and not r["ok"]
    assert len(book.sent("place")) == 1 and _sent(ad, "ORB") == 0
    assert [e["status"] for e in ad.take_resting_events()] == ["FILLED"]


# ── OCO ─────────────────────────────────────────────────────────────────────────────

def _oco(ad):
    r = _arm(ad, stop=495.0, limit=510.0)
    assert r["ok"] and r["kind"] == "oco"
    return r["client_order_ids"] + [r["combo_id"]]


def test_oco_is_one_native_combo(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p, t, k = _oco(ad)
    assert book.sent("place") == [[p, t]]
    assert book.orders[p]["combo"] == k == WO.resting_ids(TID, 1)[2]
    assert {book.orders[c]["raw"]["combo_type"] for c in (p, t)} == {"OCO"}
    assert book.orders[t]["raw"]["limit_price"] == "510.00" and book.orders[t]["side"] == "SELL"
    # cancelling ONE leg cancels and confirms BOTH
    r = ad.cancel_resting(client_order_id=t)
    assert r["ok"] and sorted(r["cancelled"]) == sorted([p, t])
    assert {book.orders[c]["status"] for c in (p, t)} == {"CANCELLED"}


def test_oco_single_fill_cancels_and_confirms_the_sibling(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p, t, _ = _oco(ad)
    book.set_price(510.5)                        # target fills; the stop stays live
    assert book.orders[p]["status"] == "SUBMITTED"
    r = ad.resolve_resting(t)                    # the stream printed through the target
    # the sibling's cancel goes out in the SAME call (2026-09-29 second review)
    assert r["status"] == "FILLED" and ("cancel", p) in book.calls
    assert ad._state["resting"][p]["cancel_sent_at"]
    for _ in range(3):
        ad.resolve_resting()
    assert book.orders[p]["status"] == "CANCELLED" and ad._live_resting() == []
    assert book.pos == 0 and _sent(ad, "ORB") == 0
    assert [(e["kind"], e["change"]) for e in ad.take_resting_events()] == [("target", 10)]


def test_oco_auto_cancelled_sibling_is_not_booked_twice(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.oco_auto_cancel = True
    p, t, _ = _oco(ad)
    book.set_price(494.0)
    ad.cancel_resting()
    assert _sent(ad, "ORB") == 0 and book.orders[t]["status"] == "CANCELLED"
    assert [e["kind"] for e in ad.take_resting_events()] == ["stop"]


def test_oco_partial_target_fill_books_the_part_and_cancels_the_rest(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p, t, _ = _oco(ad)
    book.partial[t] = 3
    book.set_price(510.2)
    r = ad.resolve_resting(t)
    assert r["status"] == "PARTIAL_FILLED" and r["change"] == 3 and _sent(ad, "ORB") == 7
    # both legs' cancels -- the full-size stop's first of all -- went out in that same call
    assert ("cancel", p) in book.calls and ("cancel", t) in book.calls
    res = ad.cancel_resting(trade_id=TID)
    assert res["ok"] and book.orders[t]["status"] == "CANCELLED" and book.orders[t]["filled"] == 3
    assert _sent(ad, "ORB") == 7 and book.pos == 7
    assert [e["change"] for e in ad.take_resting_events()] == [3]


def test_both_oco_legs_filling_books_the_flip_webull_really_holds(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p, t, _ = _oco(ad)
    book.set_price(510.5)
    book.set_price(494.0)                        # a spike through both, no auto-cancel
    ad.resolve_resting()
    ad.resolve_resting()
    assert _sent(ad, "ORB") == -10 == book.pos
    assert ad.reconcile()["ok"]


# ── reconcile, KILL, end of day ─────────────────────────────────────────────────────

def test_reconcile_books_a_resting_fill_first_no_false_halt(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _arm(ad)
    book.set_price(494.0)
    r = ad.reconcile()
    assert r["ok"] and not ad._halted and _sent(ad, "ORB") == 0
    assert [e["source"] for e in ad.take_resting_events()] == ["reconcile"]


def test_reconcile_mismatch_cancels_resting_and_blocks_rearm_until_it_agrees(
        tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.pos = 15                                # something outside the books
    r = ad.reconcile()
    assert not r["ok"] and ad._halted and ad._state.get("resting_blocked")
    # no network call under the lock: the cancel is due, the next resolve sends it
    assert ("cancel", p) not in book.calls and ad._state["resting"][p]["cancel_due"]
    ad.resolve_resting()
    assert ("cancel", p) in book.calls
    for _ in range(2):
        ad.resolve_resting()
    assert ad._live_resting() == [] and book.orders[p]["status"] == "CANCELLED"
    assert _arm(ad)["outcome"] == "BLOCKED"
    assert "resting_blocked" in ad.status()
    book.pos = 10
    assert ad.reconcile()["ok"] and "resting_blocked" not in ad._state
    assert _arm(ad)["outcome"] == "RESTING"


def test_kill_file_close_goes_through_the_gateway(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=-10)
    _arm(ad)
    open(ad._kill_file(), "w").close()
    assert _order(ad, "NOISE", "qxNOISEO2", "SHORT", 5)["mode"] == "BLOCKED"   # entries halted
    assert ad._live_resting()                                                # a block cancels nothing
    rec = _order(ad, "NOISE", "qxNOISEC", "BUY", 10, intent="CLOSE")
    book.step()
    assert rec["ok"] and ad._live_resting() == [] and book.pos == 10


def test_internal_cross_leaves_a_leg_with_a_live_resting_order_alone(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, ENGUQ=-10)
    _arm(ad)
    r = ad.cross_legs_internally(SYM, {"ORB": 1, "ENGUQ": -1})
    assert r["crossed"] == {}
    ad.cancel_resting()
    assert ad.cross_legs_internally(SYM, {"ORB": 1, "ENGUQ": -1})["crossed"] == {"ORB": 10, "ENGUQ": 10}


def test_day_expiry_after_the_close_is_dead_with_nothing_filled(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.close_session()
    book.orders[p]["filled_unknown"] = True                    # no filled_quantity on it
    today = datetime.datetime.now(WO._NY)                      # the day it was placed
    monkeypatch.setattr(WO, "_now_ny", lambda: today.replace(hour=11, minute=0))
    r = ad.resolve_resting()
    assert r["status"] == "EXPIRED" and ad._live_resting() == [p]   # in session: not settled
    monkeypatch.setattr(WO, "_now_ny", lambda: today.replace(hour=16, minute=5))
    ad.resolve_resting()
    assert ad._live_resting() == [] and ad._state["resting"][p]["final_status"] == "EXPIRED"
    assert _sent(ad, "ORB") == 10 and ad.take_resting_events() == []


# ── restart ─────────────────────────────────────────────────────────────────────────

def test_restart_boot_sweep_keeps_live_books_filled_and_cancels_unknown(tmp_path, monkeypatch):
    book = FakeWebullBook()
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    ad._save_state()
    # another host's order this state never saw
    book.place_order("ACCT1", [{"combo_type": "NORMAL", "client_order_id": "otherhostX1",
                                "symbol": SYM, "order_type": "LIMIT", "quantity": "1",
                                "side": "BUY", "limit_price": "400.00", "time_in_force": "DAY",
                                "support_trading_session": "CORE"}])
    ad2 = _adapter(tmp_path, monkeypatch, book)                # same state file
    r = ad2.boot_sweep(symbols=(SYM,))
    assert r["resolved"] == {p: "SUBMITTED"} and r["live"] == [p]
    assert [u["client_order_id"] for u in r["unknown"]] == ["otherhostX1"]
    assert book.orders["otherhostX1"]["status"] == "CANCELLED" and not r["ok"]
    assert ad2.halt_state()[:2] == (True, "reconcile")
    assert ad2.reconcile()["ok"] and not ad2.halt_state()[0]


def test_restart_after_the_stop_filled_while_down(tmp_path, monkeypatch):
    book = FakeWebullBook()
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    ad._save_state()
    book.set_price(494.0)
    ad2 = _adapter(tmp_path, monkeypatch, book)
    r = ad2.boot_sweep(symbols=(SYM,))
    assert r["ok"] and r["resolved"] == {p: "FILLED"} and r["live"] == []
    assert _sent(ad2, "ORB") == 0 and ad2.reconcile()["ok"]
    assert [e["source"] for e in ad2.take_resting_events()] == ["boot"]


def test_restart_with_an_unknown_send_that_never_landed(tmp_path, monkeypatch):
    book = FakeWebullBook()
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.place_lands = False
    book.place_raise = [ConnectionError("connection reset")]
    p = _arm(ad)["client_order_ids"][0]
    ad._state["resting"][p]["placed_at"] -= 120
    ad._save_state()
    ad2 = _adapter(tmp_path, monkeypatch, book)
    r = ad2.boot_sweep(symbols=(SYM,))
    assert r["ok"] and r["live"] == [] and ad2._state["resting"][p]["status"] == "NOT_PLACED"


# ── plumbing ────────────────────────────────────────────────────────────────────────

def test_open_orders_wrapper(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p, t, _ = _oco(ad)
    oo = ad.open_orders(SYM)
    assert sorted(o["client_order_id"] for o in oo) == sorted([p, t])
    assert {o["order_type"] for o in oo} == {"STOP_LOSS", "LIMIT"}
    assert ad.open_orders("SPY") == []
    book.get_order_open = MagicMock(side_effect=TimeoutError("down"))
    assert ad.open_orders(SYM) is None


def test_resolve_is_at_most_one_lookup_per_call(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _oco(ad)
    before = len(book.sent("detail"))
    ad.resolve_resting()
    assert len(book.sent("detail")) == before + 1
    assert ad.resolve_resting()["checked"] != ad.resolve_resting()["checked"]


def test_nothing_in_the_log_is_a_secret(tmp_path, monkeypatch, book):
    lines = []
    ad = _adapter(tmp_path, monkeypatch, book, log=lines.append)
    _seed(ad, book, ORB=10)
    _arm(ad)
    _order(ad, "NOISE", "qxNOISEO", "SHORT", 5)
    text = "\n".join(lines)
    assert "AK" not in text.split() and "AS" not in text.split() and "ACCT1" not in text


def test_fill_capture_never_books_a_resting_part(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    assert ad.apply_order_outcome(p, "FILLED", "10") is None
    assert _sent(ad, "ORB") == 10
    book.set_price(494.0)
    ad.resolve_resting()
    assert [e["change"] for e in ad.take_resting_events()] == [10]


# ── stuck records: the escape (2026-09-29 review) ─────────────────────────────────────

def _age_unclear(ad, coid, sec=WO.RESTING_ESCAPE_AFTER_SEC + 5):
    ad._state["resting"][coid]["unclear_since"] -= sec


def _escapes(ad):
    return [e for e in ad.take_resting_events() if e.get("escaped")]


@pytest.mark.parametrize("failure", ["timeout", "429"])
def test_a_lookup_that_never_answers_blocks_then_escapes_via_open_orders(
        tmp_path, monkeypatch, book, failure):
    """Webull already dropped the stop (here: cancelled at its end), but every lookup fails
    -- a timeout, or a 429 streak. The gateway holds NOISE's orders back only until the
    record has been unclear for RESTING_ESCAPE_AFTER_SEC and get_order_open does not list
    it; then it is settled dead with 0 filled (one escape event) and QQQ orders flow."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    book.orders[p]["status"] = "CANCELLED"
    if failure == "timeout":
        book.detail_down = True
    else:
        def too_many(account_id, client_order_id):
            book.calls.append(("detail", client_order_id))
            raise ServerException("HTTP Status: 429, Code: TOO_MANY_REQUESTS, Msg: slow down")
        monkeypatch.setattr(book, "get_order_detail", too_many)
    rec = _order(ad, "NOISE", "qxNOISEC", "SELL", 5, intent="CLOSE")
    assert rec["outcome"] == "RESTING_UNRESOLVED" and not rec["sent"]
    assert ad._state["resting"][p]["unclear_n"] >= WO.RESTING_ESCAPE_MIN_TRIES
    assert ("open", None) not in book.calls              # too soon for the escape read
    _age_unclear(ad, p)
    rec = _order(ad, "NOISE", "qxNOISEC2", "SELL", 5, intent="CLOSE")
    assert rec["ok"] and rec["sent"] and ("open", None) in book.calls
    r = ad._state["resting"][p]
    assert (r["live"], r["status"], r["booked"]) == (False, "ABSENT", 0)
    (ev,) = _escapes(ad)
    assert ev["client_order_id"] == p and ev["change"] == 0 and ev["status"] == "ABSENT"
    assert _sent(ad, "ORB") == 10                           # a real fill shows in a reconcile


def test_an_unclear_record_still_listed_open_stays_live(tmp_path, monkeypatch, book):
    """The escape never settles an order get_order_open still lists: it is live (a clear
    answer, the streak starts over) and keeps blocking until it is really cancelled."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.detail_down = True
    ad.resolve_resting()
    ad.resolve_resting()
    ad.resolve_resting()
    _age_unclear(ad, p)
    ad.resolve_resting()
    r = ad._state["resting"][p]
    assert r["live"] and r["status"] == "SUBMITTED" and "unclear_since" not in r
    assert _escapes(ad) == []


def test_cancelled_without_a_filled_quantity_mid_session_escapes(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    book.orders[p]["status"] = "CANCELLED"
    book.orders[p]["filled_unknown"] = True
    today = datetime.datetime.now(WO._NY)
    monkeypatch.setattr(WO, "_now_ny", lambda: today.replace(hour=11, minute=0))
    rec = _order(ad, "NOISE", "qxNOISEC", "SELL", 5, intent="CLOSE")
    assert rec["outcome"] == "RESTING_UNRESOLVED"
    assert ad._state["resting"][p]["last_answer"] == "CANCELLED"
    _age_unclear(ad, p)
    assert _order(ad, "NOISE", "qxNOISEC2", "SELL", 5, intent="CLOSE")["ok"]
    assert ad._state["resting"][p]["status"] == "ABSENT" and len(_escapes(ad)) == 1


def test_mode_off_in_the_book_still_lets_qqq_orders_through_a_stuck_record(
        tmp_path, monkeypatch, book):
    """The gateway does not depend on qqq_exec's orb_resting.mode: a stuck record left by a
    stop mode is escaped the same way when nothing but NOISE trades any more."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    ad.set_prev_terminal(None)                                   # what 'off' hands back
    del book.orders[p]                                           # Webull has no record of it
    rec = _order(ad, "NOISE", "qxNOISEC", "SELL", 5, intent="CLOSE")
    assert rec["outcome"] == "RESTING_UNRESOLVED"
    assert ad._state["resting"][p]["last_answer"] == "NOT_FOUND"  # acked: never "never placed"
    _age_unclear(ad, p)
    assert _order(ad, "NOISE", "qxNOISEC2", "SELL", 5, intent="CLOSE")["ok"]
    assert ad._live_resting() == []


def test_restart_the_next_day_expires_yesterdays_acked_stop_that_webull_no_longer_finds(
        tmp_path, monkeypatch):
    """The process was down over the close: yesterday's DAY stop is gone from Webull and its
    lookup says 'not found'. The boot sweep reads that as expired unfilled (one escape
    event) instead of a record that blocks every order -- the EOD flatten included."""
    book = FakeWebullBook()
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    ad._state["resting"][p]["placed_at"] -= 24 * 3600
    ad._save_state()
    del book.orders[p]
    ad2 = _adapter(tmp_path, monkeypatch, book)
    r = ad2.boot_sweep(symbols=(SYM,))
    assert r["ok"] and r["live"] == [] and r["resolved"] == {p: "EXPIRED"}
    assert ad2._state["resting"][p]["final_status"] == "EXPIRED"
    (ev,) = _escapes(ad2)
    assert ev["status"] == "EXPIRED" and ev["change"] == 0
    assert _order(ad2, "NOISE", "qxNOISEC", "SELL", 5, intent="CLOSE")["ok"]


def test_a_send_that_raised_but_landed_is_kept_live_when_open_orders_lists_it(
        tmp_path, monkeypatch, book):
    """Never-acked + 'not found' past the grace is NOT enough to call it never placed: the
    order index may lag. get_order_open lists it -> the record stays live and acked, so the
    gateway still cancels it before NOISE's next order."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.place_raise = [TimeoutError("read timed out")]       # it landed anyway
    lagging = set()
    real_detail = book.get_order_detail

    def detail(account_id, client_order_id):
        if client_order_id in lagging:
            book.calls.append(("detail", client_order_id))
            raise _417("OPENAPI_ORDER_NOT_FOUND", "no such order")
        return real_detail(account_id, client_order_id)
    monkeypatch.setattr(book, "get_order_detail", detail)
    p = WO.resting_ids(TID, 1)[0]
    lagging.add(p)
    r = _arm(ad)
    assert r["outcome"] == "UNKNOWN" and ad._state["resting"][p]["pending"]
    ad._state["resting"][p]["placed_at"] -= 60
    ad.resolve_resting()
    rec = ad._state["resting"][p]
    assert rec["live"] and rec["acked"] and rec["status"] == "SUBMITTED"
    assert ("open", None) in book.calls


def test_session_over_follows_the_half_day_close(monkeypatch):
    rec = {"placed_at": datetime.datetime(2026, 11, 27, 10, 0, tzinfo=WO._NY).timestamp()}
    monkeypatch.setattr(WO, "_now_ny", lambda: datetime.datetime(2026, 11, 27, 12, 59, tzinfo=WO._NY))
    assert WO.OrderAdapter._session_over(rec) is False
    monkeypatch.setattr(WO, "_now_ny", lambda: datetime.datetime(2026, 11, 27, 13, 1, tzinfo=WO._NY))
    assert WO.OrderAdapter._session_over(rec) is True       # the day after Thanksgiving: 13:00
    rec = {"placed_at": datetime.datetime(2026, 9, 29, 10, 0, tzinfo=WO._NY).timestamp()}
    monkeypatch.setattr(WO, "_now_ny", lambda: datetime.datetime(2026, 9, 29, 15, 59, tzinfo=WO._NY))
    assert WO.OrderAdapter._session_over(rec) is False


# ── no network call under the adapter lock (2026-09-29 review) ───────────────────────

def _lock_free_from_another_thread(ad):
    import threading
    got = []

    def probe():
        ok = ad._lock.acquire(timeout=1.0)
        got.append(ok)
        if ok:
            ad._lock.release()
    t = threading.Thread(target=probe)
    t.start()
    t.join(timeout=WAIT_SECONDS)
    return got == [True]


def test_place_cancel_and_replace_let_the_lock_go_on_the_wire(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    seen = {}
    book.on_place = lambda b, orders: seen.setdefault("place", _lock_free_from_another_thread(ad))
    real_cancel, real_replace = book.cancel_order, book.replace_order

    def cancel(account_id, client_order_id):
        seen.setdefault("cancel", _lock_free_from_another_thread(ad))
        return real_cancel(account_id, client_order_id)

    def replace(account_id, modify_orders, client_combo_order_id=None):
        seen.setdefault("replace", _lock_free_from_another_thread(ad))
        return real_replace(account_id, modify_orders, client_combo_order_id)
    monkeypatch.setattr(book, "cancel_order", cancel)
    monkeypatch.setattr(book, "replace_order", replace)
    r = _arm(ad)
    assert r["outcome"] == "RESTING"
    assert ad.replace_resting(r["group"], stop_price=497.0)["outcome"] == "REPLACED"
    assert ad.cancel_resting()["ok"]
    assert seen == {"place": True, "replace": True, "cancel": True}
    assert ad._resting_sending == set()


def test_resting_orders_says_none_when_the_lock_stays_busy(tmp_path, monkeypatch, book):
    import threading
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _arm(ad)
    held, done = threading.Event(), threading.Event()

    def hold():
        with ad._lock:
            held.set()
            done.wait(5)
    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        assert ad.resting_orders(SYM, lock_timeout=0.05) is None
    finally:
        done.set()
        t.join(timeout=WAIT_SECONDS)
    assert len(ad.resting_orders(SYM, lock_timeout=0.05)) == 1


def test_requeued_events_come_back_first(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _arm(ad)
    book.set_price(494.0)
    ad.resolve_resting()
    ev = ad.take_resting_events()
    assert len(ev) == 1 and ad.take_resting_events() == []
    assert ad.requeue_resting_events(ev)
    assert ad.take_resting_events() == ev


def test_boot_sweep_without_the_lease_lists_unknown_orders_and_cancels_nothing(
        tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.place_order("ACCT1", [{"combo_type": "NORMAL", "client_order_id": "otherhostX1",
                                "symbol": SYM, "order_type": "STOP_LOSS", "quantity": "10",
                                "side": "SELL", "stop_price": "480.00", "time_in_force": "DAY",
                                "support_trading_session": "CORE"}])
    r = ad.boot_sweep(symbols=(SYM,), cancel_unknown=False)
    assert [u["client_order_id"] for u in r["unknown"]] == ["otherhostX1"] and not r["ok"]
    assert "NOT cancelled" in r["reason"] and book.sent("cancel") == []
    assert book.orders["otherhostX1"]["status"] == "SUBMITTED"
    assert ad.halt_state()[0] is False


def test_a_cancel_that_raised_stays_due_and_the_next_resolve_sends_it_again(
        tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    real_cancel = book.cancel_order
    fails = [TimeoutError("read timed out")]

    def cancel(account_id, client_order_id):
        if fails:
            book.calls.append(("cancel", client_order_id))
            raise fails.pop()
        return real_cancel(account_id, client_order_id)
    monkeypatch.setattr(book, "cancel_order", cancel)
    ad.cancel_resting(confirm=False)
    assert ad._state["resting"][p]["cancel_due"] and "cancel_error" in ad._state["resting"][p]
    ad.resolve_resting()
    assert book.sent("cancel") == [p, p] and not ad._state["resting"][p]["cancel_due"]
    ad.resolve_resting()
    assert ad._live_resting() == [] and book.orders[p]["status"] == "CANCELLED"


# ── second review (2026-09-29): absence is never "unfilled" on its own ─────────────────

def _lookups_fail_past_the_escape(ad, book, coid):
    """Every lookup of `coid` times out, for longer than RESTING_ESCAPE_AFTER_SEC."""
    book.detail_fail[coid] = 10 ** 6
    for _ in range(WO.RESTING_ESCAPE_MIN_TRIES):
        ad.resolve_resting()
    _age_unclear(ad, coid)


@pytest.mark.parametrize("noise", [0, -20])
def test_a_stop_that_filled_while_its_lookups_fail_is_booked_filled_never_closed_twice(
        tmp_path, monkeypatch, book, noise):
    """The major finding: ORB long 10 (NOISE -20 -> the stop rests as a SHORT 10 opening
    stop), the stop FILLS while every lookup of it times out for 120 s+. get_order_open
    does not list a FILLED order, so absence alone used to book it 0 filled and ORB's
    engine CLOSE then went out as a second order. Now the positions read decides: the
    books take the fill (an inferred event), and ORB's close sends nothing."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, **({"ORB": 10, "NOISE": noise} if noise else {"ORB": 10}))
    r = _arm(ad)
    assert r["side"] == ("SHORT" if noise else "SELL")
    p = r["client_order_ids"][0]
    book.set_price(494.0)                                  # filled at Webull
    real_pos = book.pos
    _lookups_fail_past_the_escape(ad, book, p)
    ad.resolve_resting()                                    # the escape read
    rec = ad._state["resting"][p]
    assert (rec["live"], rec["status"], rec["booked"]) == (False, "FILLED", 10)
    (ev,) = ad.take_resting_events()
    assert ev["inferred"] and ev["change"] == 10 and ev["filled_price"] is None
    assert not ev.get("escaped") and "resting_blocked" not in ad._state
    close = _order(ad, "ORB", "qxORB31420260929T143500ZLC", "SELL", 10, intent="CLOSE")
    assert close["ok"] and not close["sent"] and close["closed_by_resting"]
    assert [t for t in book.placed_types() if t[1] == "MARKET"] == []
    assert book.pos == real_pos == ad._account_net(SYM) and ad.reconcile()["ok"]


def test_an_absent_stop_whose_fill_cannot_be_decided_stays_live_and_orders_wait(
        tmp_path, monkeypatch, book):
    """The position fits neither 'unfilled' nor 'this stop filled' (shares nobody in the
    books knows): nothing is settled, ONE undecided event, the gateway keeps holding every
    QQQ order -- ORB's close included -- and re-reads at most every
    RESTING_ABSENT_RECHECK_SEC."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    book.set_price(494.0)
    book.pos += 13                                          # and something else moved
    _lookups_fail_past_the_escape(ad, book, p)
    ad.resolve_resting()
    rec = ad._state["resting"][p]
    assert rec["live"] and rec["absent_undecided"] and _sent(ad, "ORB") == 10
    (ev,) = ad.take_resting_events()
    assert ev["undecided"] and ev["change"] == 0 and "is not one resting order" in ev["reason"]
    close = _order(ad, "ORB", "qxORB31420260929T143500ZLC", "SELL", 10, intent="CLOSE")
    assert close["outcome"] == "RESTING_UNRESOLVED" and not close["sent"]
    assert ad.take_resting_events() == []                   # one alert per record
    n_pos = book.account_v2.get_account_position.call_count
    ad.resolve_resting()
    assert book.account_v2.get_account_position.call_count == n_pos   # inside the recheck gap
    book.pos -= 13                                          # the stray shares are gone
    rec["absent_checked_at"] -= WO.RESTING_ABSENT_RECHECK_SEC + 1
    ad.resolve_resting()
    assert rec["status"] == "FILLED" and _sent(ad, "ORB") == 0


def test_an_absent_stop_is_undecided_while_another_order_is_still_working(
        tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    book.orders[p]["status"] = "CANCELLED"
    import time
    ad._parts()["qxENGUQO"] = {"leg": "ENGUQ", "symbol": SYM, "side": "BUY", "qty": 5,
                               "intent": "OPEN", "account_id": "ACCT1", "ts": time.time() - 60,
                               "booked": 5, "pending": False}          # acked, still working
    _lookups_fail_past_the_escape(ad, book, p)
    ad.resolve_resting()
    assert ad._state["resting"][p]["live"]
    assert "qxENGUQO" in ad.take_resting_events()[0]["reason"]


def test_an_escaped_order_webull_still_works_is_found_by_the_reconcile_before_any_rearm(
        tmp_path, monkeypatch, book):
    """Minor 2: get_order_open once omitted an order Webull is still working. It is settled
    ABSENT (the position shows it unfilled), but re-arming stays BLOCKED; the reconcile's
    own get_order_open read finds it working -> live again and due a cancel, so there are
    never two closing stops at Webull."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=10)
    p = _arm(ad)["client_order_ids"][0]
    real_open = book.get_order_open
    monkeypatch.setattr(book, "get_order_open", lambda *a, **k: _Resp({"data": []}))
    _lookups_fail_past_the_escape(ad, book, p)
    ad.resolve_resting()
    assert ad._state["resting"][p]["status"] == "ABSENT" and ad._state["resting_blocked"]
    assert [e["status"] for e in _escapes(ad)] == ["ABSENT"]
    assert _arm(ad)["outcome"] == "BLOCKED"
    monkeypatch.setattr(book, "get_order_open", real_open)
    book.detail_fail.clear()
    assert ad.reconcile()["ok"]
    rec = ad._state["resting"][p]
    assert rec["live"] and rec["cancel_due"] and "resting_absent" not in ad._state
    assert _arm(ad)["outcome"] == "BUSY"
    ad.resolve_resting()
    ad.resolve_resting()
    assert book.orders[p]["status"] == "CANCELLED" and ad._live_resting() == []
    assert _arm(ad)["outcome"] == "RESTING"
    assert len([o for o in book._live().values() if o["type"] == "STOP_LOSS"]) == 1


def test_an_escaped_order_still_absent_at_the_reconcile_frees_the_rearm(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    book.orders[p]["status"] = "CANCELLED"
    _lookups_fail_past_the_escape(ad, book, p)
    ad.resolve_resting()
    assert _arm(ad)["outcome"] == "BLOCKED"
    assert ad.reconcile()["ok"] and "resting_blocked" not in ad._state
    book.detail_fail.clear()
    assert _arm(ad)["outcome"] == "RESTING"


def test_yesterdays_stop_webull_no_longer_finds_is_booked_filled_when_the_position_says_so(
        tmp_path, monkeypatch):
    """The process was down over the close and the stop FILLED before it aged out of
    Webull's order lookup: 'not found' the next day is not 'expired unfilled' when the
    position shows the fill."""
    book = FakeWebullBook()
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10, NOISE=5)
    p = _arm(ad)["client_order_ids"][0]
    book.set_price(494.0)
    ad._state["resting"][p]["placed_at"] -= 24 * 3600
    ad._save_state()
    del book.orders[p]
    ad2 = _adapter(tmp_path, monkeypatch, book)
    r = ad2.boot_sweep(symbols=(SYM,))
    assert r["resolved"] == {p: "FILLED"} and _sent(ad2, "ORB") == 0
    (ev,) = ad2.take_resting_events()
    assert ev["inferred"] and ev["change"] == 10 and ev["placed_at"]
    assert ad2.reconcile()["ok"]


# ── reconcile while lookups are off ────────────────────────────────────────────────

def test_reconcile_without_lookups_is_undecided_for_an_unbooked_stop_fill(tmp_path, monkeypatch, book):
    """Minor 7/16: qqq_exec passes resolve_pending=False while its order lookups time out.
    A stop fill not yet booked is then 'look it up first' -- no halt, no resting_blocked,
    the stop marked due -- and, looked up, the next reconcile agrees."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.set_price(494.0)
    r = ad.reconcile(resolve_pending=False)
    assert r["undecided"] and not r["ok"] and not ad._halted
    assert "resting_blocked" not in ad._state and ad._state["resting"][p]["check_due"]
    assert ad.resolve_resting()["checked"] == p
    r = ad.reconcile(resolve_pending=False)
    assert r["ok"] and "reconcile_undecided_n" not in ad._state


def test_undecided_reconciles_halt_after_a_few_in_a_row(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.pos -= 4                                   # within what the stop could fill
    for _ in range(WO.RECONCILE_UNDECIDED_MAX):
        assert ad.reconcile(resolve_pending=False)["undecided"]
    r = ad.reconcile(resolve_pending=False)
    assert not r["ok"] and not r.get("undecided") and ad._halted
    assert ad._state["resting"][p]["cancel_due"]


def test_a_mismatch_the_stop_could_not_explain_halts_at_once(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    _arm(ad)
    book.pos += 4                                   # the wrong way for a SELL stop
    r = ad.reconcile(resolve_pending=False)
    assert not r["ok"] and not r.get("undecided") and ad._halted


def test_the_resting_pass_runs_first_on_its_own_budget(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.set_price(494.0)
    order = []
    real_pending = ad._resolve_pending
    monkeypatch.setattr(ad, "_resolve_pending", lambda c: (order.append("pending"), real_pending(c)))
    real_pass = ad._resolve_resting_pass
    monkeypatch.setattr(ad, "_resolve_resting_pass",
                        lambda c, s: (order.append("resting"), real_pass(c, s))[1])
    assert ad.reconcile()["ok"] and order == ["resting", "pending"]
    assert ad._state["resting"][p]["status"] == "FILLED"


# ── the previous order is still working, whatever its age ──────────────────────────

def test_no_arm_next_to_a_market_order_webull_still_works_after_30s(tmp_path, monkeypatch, book):
    """Minor 3: an acked NOISE BUY 20 still working at Webull 31 s later used to stop
    blocking, and a stop sized from a net that assumed its fill was placed next to it."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.market_stuck = True
    assert _order(ad, "NOISE", "qxNOISEO", "BUY", 20)["ok"]
    ad._parts()["qxNOISEO"]["ts"] -= 31
    r = _arm(ad)
    assert r["outcome"] == "BUSY" and "qxNOISEO" in r["reason"]
    assert [o["type"] for o in book.orders.values()] == ["MARKET"]
    assert ad.apply_order_outcome("qxNOISEO", "FILLED", "20") is None   # booked at the ack
    assert ad._parts()["qxNOISEO"]["final_status"] == "FILLED"
    book.step()
    assert _arm(ad, qty=10)["outcome"] == "RESTING"


def test_a_refused_order_never_holds_the_stop_back(tmp_path, monkeypatch, book):
    """A part Webull refused outright (a 4xx) never reached its book: the 10-minute
    'still working' window must not keep ORB's stop from arming."""
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.place_raise = [_417("OPENAPI_TEST_REFUSAL")]
    assert not _order(ad, "NOISE", "qxNOISEO", "SHORT", 5)["ok"]
    assert _arm(ad)["outcome"] == "RESTING"


# ── rate limits, replaces that did not take, two-step fills, a dead send ────────────

def test_a_429_on_place_is_rate_limited_and_on_replace_leaves_the_stop(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    book.place_raise = [ServerException("HTTP Status: 429, Code: TOO_MANY_REQUESTS, Msg: slow")]
    r = _arm(ad)
    assert r["outcome"] == "RATE_LIMITED" and not r["ok"] and ad._live_resting() == []
    p = _arm(ad)["client_order_ids"][0]
    monkeypatch.setattr(book, "replace_order", lambda *a, **k: (_ for _ in ()).throw(
        ServerException("HTTP Status: 429, Code: TOO_MANY_REQUESTS, Msg: slow")))
    r = ad.replace_resting(p, stop_price=500.25)
    assert r["outcome"] == "RATE_LIMITED" and book.sent("cancel") == []
    assert book.orders[p]["stop"] == 495.0 and ad._live_resting() == [p]


def test_a_replace_that_did_not_take_is_corrected_by_the_next_lookup(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    ad._state["resting"][p]["stop_price"] = 500.25       # recorded as moved, Webull says no
    ad.resolve_resting()
    assert ad._state["resting"][p]["stop_price"] == 495.0


def test_a_fill_in_two_steps_prices_each_step_at_its_own_average(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    p = _arm(ad)["client_order_ids"][0]
    book.partial[p] = 4
    book.cancel_fills.add(p)                             # the rest fills as the cancel lands
    book.set_price(494.0)
    ad.resolve_resting()                                 # 4 @ 494.00; the cancel goes out
    assert book.orders[p]["status"] == "FILLED"          # ... and meets the other 6 @ 495.00
    book.orders[p]["px"] = (4 * 494.0 + 6 * 495.0) / 10  # Webull reports the average
    ad.resolve_resting()
    ev = ad.take_resting_events()
    assert [(e["change"], e["filled_price"]) for e in ev] == [(4, 494.0), (6, 495.0)]


def test_a_send_settled_while_on_the_wire_is_not_reported_armed(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    _seed(ad, book, ORB=10)
    real = book.place_order

    def place_then_settled(account_id, new_orders, client_combo_order_id=None):
        resp = real(account_id, new_orders, client_combo_order_id)
        c = new_orders[0]["client_order_id"]              # a gateway settles it meanwhile
        book.orders[c]["status"] = "CANCELLED"
        ad._state["resting"][c].update(live=False, status="CANCELLED", final_status="CANCELLED")
        return resp
    monkeypatch.setattr(book, "place_order", place_then_settled)
    r = _arm(ad)
    assert r["outcome"] == "DEAD" and not r["ok"]


def test_boot_sweep_names_the_callers_reason_for_not_cancelling(tmp_path, monkeypatch, book):
    ad = _adapter(tmp_path, monkeypatch, book)
    book.place_order("ACCT1", [{"combo_type": "NORMAL", "client_order_id": "handplaced1",
                                "symbol": SYM, "order_type": "LIMIT", "quantity": "1",
                                "side": "BUY", "limit_price": "400.00", "time_in_force": "DAY",
                                "support_trading_session": "CORE"}])
    r = ad.boot_sweep(symbols=(SYM,), cancel_unknown=False, no_cancel_reason="log_only")
    assert "NOT cancelled: log_only" in r["reason"] and book.sent("cancel") == []
    assert book.orders["handplaced1"]["status"] == "SUBMITTED" and not ad.halt_state()[0]
