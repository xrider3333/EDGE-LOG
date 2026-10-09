"""ENGU-Q BACK ON THE LIVE BOOK (OWNER DECISION 2026-10-09, via MANAGER #102) -- the executor
half: ENGU-Q's engine rows (ENGUQ_335 -> exec leg "ENGUQ") share the ONE Webull QQQ account
with NOISE and ORB again, so every one of its orders is NETTED (api/webull_orders.py
_plan_broker_parts, from the ACCOUNT net = the sum of every leg's broker_sent_positions):
  SELL direction: SELL if the account is long >= q, SHORT if flat/short, else SELL the long
                  and SHORT the rest;
  BUY direction:  BUY, split at zero when it crosses short -> long.

Driven the way the box drives it: engine ENTRY/EXIT rows through
api/qqq_exec._route_engine_events (the engine-mode consumer), a close of every open lot at once
through _close_all, a real api.webull_orders.OrderAdapter in PAPER, and a fake Webull account
(FakeAccount below) that holds ONE QQQ position and enforces Webull's rules.

HOLD OVERNIGHT (owner GO 2026-10-09, MANAGER #106): the 15:59 flat_by flatten no longer closes
ENGU-Q -- it holds overnight and sells on its own exit (tests/test_qqq_exec_hold_overnight.py,
incl. the flatten never crossing a closing leg against the held lot). Cases 1, 3 and 4 below call
_close_all over EVERY open lot (reason "EOD", at 15:59): what the flatten does with the hold
turned off (session.hold_overnight_legs []), and what KILL and the daily loss BREAKER still do
to ENGU-Q inside regular hours -- the netting is the same.

COVERS:
  1. A realistic day: NOISE short 10 open -> ENGU-Q BUY 10 (covers at the broker, books
     NOISE -10 / ENGUQ +10, account flat) -> NOISE's cover BUY 10 (the broker opens long 10)
     -> a close of every lot at 15:59 SELLs ENGU-Q's 10 -> the account and every book are flat.
  2. ENGU-Q long first, then NOISE short: the SELL 10 nets against the account's long 10 ->
     a plain closing SELL, never a SHORT (Webull refuses a short while long).
  3. Both closed at once, opposite sides (ENGU-Q long + NOISE short, account flat): one tick
     crosses them in the books -- ZERO orders, nothing refused.
  4. Both closed at once, SAME side (ORB long + ENGU-Q long, account +20): two identical
     SELL 10s in one tick -- Webull's DUPLICATE_ORDER_CHECK refuses the second while the first
     is working; it is queued and re-sent a tick later under a fresh id; the account ends flat.
  5. ENGU-Q's entry refused by the session window (bar after last_entry / after the bell)
     sends nothing and logs ONE plain line: strategy, side, signal time, why.
  6. ENGU-Q's BUY 10 still working at Webull when NOISE's short arrives in the same tick
     (MANAGER GO 10-09): the SELL 10 is refused 417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER, queued
     (why "box_order") and re-sent once the buy has filled -- a closing SELL 10, accepted;
     no give-up and no "entry missed" note.
  7. Still refused after BROKER_RESEND_MAX_TRIES re-sends: it gives up with one plain line
     naming the opposite order, and ONE "entry missed" note then.
No real SDK, network or credentials: tests/conftest.py isolates the live system as usual.
"""
import csv
import datetime
import json
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import trade_id as T
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731
DAY = "2026-10-09"           # the day ENGU-Q went live again (a Friday session)
EOD_PX = 745.10


def _at(hh, mm, ss=0):
    return datetime.datetime(2026, 10, 9, hh, mm, ss)


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeAccount:
    """One Webull margin account, QQQ only -- the rules of tests/test_qqq_exec_eod_net_flatten.py's
    FakeWebullBook (copied, not imported: no test module here imports another), plus Webull's
    DUPLICATE_ORDER_CHECK: while `async_fills` keeps orders pending, a new order identical to
    a pending one (same side, same quantity) is refused with that 417."""

    def __init__(self):
        self.pos = 0
        self.pending = []
        self.status = {}
        self.async_fills = False
        self.sent = []
        self.refused = []
        self.account_v2 = MagicMock()
        self.account_v2.get_account_list.return_value.json.return_value = {
            "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
        self.account_v2.get_account_position.side_effect = lambda acct: _Resp(
            {"data": ([{"symbol": "QQQ", "quantity": str(abs(self.pos)),
                        "side": "SHORT" if self.pos < 0 else "LONG"}] if self.pos else [])})
        self.order_v3 = MagicMock()
        self.order_v3.place_order.side_effect = self._place
        self.order_v3.get_order_detail.side_effect = self._detail

    def _refuse(self, side, qty, code):
        self.refused.append((side, qty, code))
        raise RuntimeError(f"ServerException: HTTP Status: 417, Code: {code}, Msg: refused")

    def _place(self, account_id, orders):
        o = orders[0]
        side, qty, coid = o["side"], int(o["quantity"]), o["client_order_id"]
        if any(p["side"] == side and p["qty"] == qty for p in self.pending):
            self._refuse(side, qty, "OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK")
        pend_buy_open = any(p["side"] == "BUY" and p["opening"] for p in self.pending)
        pend_sell_open = any(p["side"] in ("SELL", "SHORT") and p["opening"] for p in self.pending)
        reserved_sell = sum(p["qty"] for p in self.pending if p["side"] == "SELL" and not p["opening"])
        reserved_buy = sum(p["qty"] for p in self.pending if p["side"] == "BUY" and not p["opening"])
        if side == "BUY":
            if self.pos >= 0:
                opening = True
                if pend_sell_open:
                    self._refuse(side, qty, "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER")
            else:
                opening = False
                if qty > -self.pos - reserved_buy:
                    self._refuse(side, qty, "OPENAPI_ORDER_CROSSES_POSITION")
        elif side == "SELL":
            if qty > self.pos - reserved_sell:
                if pend_buy_open:
                    self._refuse(side, qty, "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER")
                self._refuse(side, qty, "OPENAPI_ORDER_EXCEED_POSITION")
            opening = False
        elif side == "SHORT":
            if self.pos > 0:
                self._refuse(side, qty, "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION")
            if pend_buy_open:
                self._refuse(side, qty, "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER")
            opening = True
        else:
            raise AssertionError(side)
        self.sent.append({"side": side, "qty": qty, "coid": coid, "opening": opening})
        if self.async_fills:
            self.pending.append({"coid": coid, "side": side, "qty": qty, "opening": opening})
            self.status[coid] = "SUBMITTED"
        else:
            self.pos += qty if side == "BUY" else -qty
            self.status[coid] = "FILLED"
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": self.status[coid], "filled_price": str(EOD_PX),
             "filled_quantity": "0" if self.async_fills else str(qty)}]})

    def fill_pending(self):
        for p in self.pending:
            self.pos += p["qty"] if p["side"] == "BUY" else -p["qty"]
            self.status[p["coid"]] = "FILLED"
        self.pending = []

    def _detail(self, account_id, coid):
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": self.status.get(coid) or "REJECTED",
             "filled_quantity": "0"}]})


@pytest.fixture
def account(tmp_path, monkeypatch):
    """(adapter, fake, clock) wired into api.qqq_exec: CSVs under tmp_path, a controllable
    clock (qe.time.time -- webull_orders reads the same stdlib module), EOD priced at EOD_PX,
    pushes captured."""
    out = tmp_path / "qqq_out"
    out.mkdir()
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    monkeypatch.setattr(qe, "SERVING_LOCK", str(out / "SERVING.lock"))
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (EOD_PX, "live_stream"))
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: None)
    clock = [2_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["rails"]["max_shares_per_leg"] = 60
    cfg["rails"]["max_total_position_shares"] = 500
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    fake = FakeAccount()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: fake)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    return adapter, fake, clock


def _cfg():
    """The box's qqq_exec sizing (config.json 2026-10-05): 10 shares a leg, cap 60."""
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["shares"] = {"ORB": 10, "ENGUQ": 10, "NOISE": 10}
    cfg["signal_source"] = "engine"
    cfg["max_shares_per_leg"] = 60
    cfg["slippage_per_share"] = 0.0
    cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
    return cfg


def _entry(engine_leg, hhmm, side, px=740.0):
    ref = f"{DAY}T{hhmm}:00-04:00"
    return {"leg": engine_leg, "event": "ENTRY", "side": side, "ref_time": ref,
            "ref_price": px, "bar_source": "webull", "trade_id": T.make(engine_leg, ref, side),
            "size": "1.0", "keel_size": "", "reason": ""}


def _exit(entry, hhmm, px=741.0):
    return dict(entry, event="EXIT", ref_time=f"{DAY}T{hhmm}:00-04:00", ref_price=px,
                reason="strategy_exit")


def _route(state, ev, now, log=NOOP):
    qe._route_engine_events(state, _cfg(), [ev], False, log=log, now=now)


def _books(adapter):
    return {leg: p["qty"] for leg, p in (adapter._state.get("broker_sent_positions") or {}).items()}


def _orders(fake, start=0):
    return [(o["side"], o["qty"]) for o in fake.sent[start:]]


def _rows(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


# ── 1. a realistic day on the one account ───────────────────────────────────────────────
def test_noise_short_then_enguq_long_then_noise_cover_then_eod_flatten(account):
    adapter, fake, _clock = account
    state = {"legs": {}, "events": [], "_px_source": "test"}

    noise = _entry("NOISE_382", "09:55", "short", 741.20)
    _route(state, noise, _at(10, 0, 10))
    assert _orders(fake) == [("SHORT", 10)] and fake.pos == -10
    assert _books(adapter) == {"NOISE": -10}

    enguq = _entry("ENGUQ_335", "10:59", "long", 740.40)
    _route(state, enguq, _at(11, 0, 5))
    assert state["legs"]["ENGUQ"]["trade_id"] == "ENGUQ_335-20261009T145900Z-L"
    assert _orders(fake, 1) == [("BUY", 10)], "ENGU-Q's buy covers NOISE's short at Webull"
    assert fake.sent[1]["opening"] is False and fake.pos == 0
    assert _books(adapter) == {"NOISE": -10, "ENGUQ": 10}, "each leg keeps its own book"
    assert adapter._account_net("QQQ") == 0

    _route(state, _exit(noise, "12:59", 739.90), _at(13, 0, 5))
    assert _orders(fake, 2) == [("BUY", 10)], "NOISE's cover opens long 10 at the broker"
    assert fake.sent[2]["opening"] is True and fake.pos == 10
    assert _books(adapter) == {"NOISE": 0, "ENGUQ": 10}
    assert set(state["legs"]) == {"ENGUQ"}

    # every open lot closed at once (the hold off, or KILL / BREAKER in regular hours): with the
    # default hold the 15:59 flatten keeps ENGU-Q -- see tests/test_qqq_exec_hold_overnight.py
    qe._close_all(state, _cfg(), "EOD", None, None, log=NOOP, nowdt=_at(15, 59, 1))
    assert _orders(fake, 3) == [("SELL", 10)], "closing every lot sells ENGU-Q's 10"
    assert fake.pos == 0 and adapter._account_net("QQQ") == 0
    assert _books(adapter) == {"NOISE": 0, "ENGUQ": 0}
    assert state["legs"] == {} and fake.refused == []
    trades = _rows(qe.TRADES_CSV)
    assert [t["leg"] for t in trades] == ["NOISE", "ENGUQ"]
    assert trades[-1]["exit_reason"].startswith("EOD")


# ── 2. ENGU-Q long first, then NOISE short: SELL against the long, never SHORT ──────────
def test_enguq_long_first_then_noise_short_sells_against_the_account_long(account):
    adapter, fake, _clock = account
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _route(state, _entry("ENGUQ_335", "10:31", "long"), _at(10, 32, 5))
    assert _orders(fake) == [("BUY", 10)] and fake.pos == 10
    _route(state, _entry("NOISE_382", "11:15", "short"), _at(11, 20, 10))
    assert _orders(fake, 1) == [("SELL", 10)], "account long 10 >= 10: a plain closing SELL"
    assert fake.sent[1]["opening"] is False and fake.refused == []
    assert fake.pos == 0 and _books(adapter) == {"ENGUQ": 10, "NOISE": -10}


# ── 3. both closed at once, opposite sides: crossed in one tick, zero orders ────────────
# (_close_all over every lot -- the 15:59 flatten itself keeps ENGU-Q since the hold, 10-09)
def test_enguq_long_and_noise_short_at_flat_by_cross_with_no_order(account):
    adapter, fake, _clock = account
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _route(state, _entry("ENGUQ_335", "10:31", "long"), _at(10, 32, 5))
    _route(state, _entry("NOISE_382", "11:15", "short"), _at(11, 20, 10))
    n = len(fake.sent)

    fake.async_fills = True
    qe._close_all(state, _cfg(), "EOD", None, None, log=NOOP, nowdt=_at(15, 59, 1))

    assert fake.sent[n:] == [] and fake.refused == [], "a flat account needs no order"
    assert state["legs"] == {}, "the book still closes both lots"
    assert _books(adapter) == {"ENGUQ": 0, "NOISE": 0} and fake.pos == 0
    assert state.get("_broker_resend", {}) == {}
    rows = [r for r in _rows(qe.BROKER_ORDERS_CSV) if r["intent"] == "CLOSE"]
    assert {r["leg"] for r in rows} == {"ENGUQ", "NOISE"} and {r["outcome"] for r in rows} == {"NETTED"}


# ── 4. both closed at once, same side: Webull's duplicate check, then the re-send ───────
# (_close_all over every lot -- the 15:59 flatten itself keeps ENGU-Q since the hold, 10-09)
def test_orb_and_enguq_long_at_flat_by_survive_webull_s_duplicate_order_check(account):
    adapter, fake, clock = account
    state = {"legs": {}, "events": [], "_px_source": "test"}
    _route(state, _entry("ORB_R6", "09:45", "long"), _at(9, 50, 10))
    _route(state, _entry("ENGUQ_335", "10:31", "long"), _at(10, 32, 5))
    assert fake.pos == 20 and _books(adapter) == {"ORB": 10, "ENGUQ": 10}
    n = len(fake.sent)

    fake.async_fills = True                    # the first SELL is still working at Webull
    flat_at = _at(15, 59, 1)
    qe._close_all(state, _cfg(), "EOD", None, None, log=NOOP, nowdt=flat_at)
    assert _orders(fake, n) == [("SELL", 10)], "ORB's SELL 10 went out"
    assert fake.refused == [("SELL", 10, "OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK")], \
        "ENGU-Q's identical SELL 10 in the same instant is Webull's duplicate"
    assert state["legs"] == {}, "the book closed both lots"
    queued = state.get("_broker_resend") or {}
    assert [q.get("leg") for q in queued.values()] == ["ENGUQ"]

    fake.fill_pending()                        # ORB's sell fills; the duplicate rule clears
    clock[0] += 5
    qe._maybe_resend_broker_orders(state, _cfg(), _at(15, 59, 6), True, log=NOOP)
    assert _orders(fake, n) == [("SELL", 10), ("SELL", 10)]
    assert fake.sent[-1]["coid"] != fake.sent[-2]["coid"], "re-sent under a fresh id"
    fake.fill_pending()
    assert fake.pos == 0 and _books(adapter) == {"ORB": 0, "ENGUQ": 0}
    assert state.get("_broker_resend") == {}


# ── 5. refused by the session window: nothing sent, ONE plain log line ──────────────────
@pytest.mark.parametrize("now,hhmm,why", [
    (_at(15, 57, 10), "15:57", "its bar (15:57) is after last_entry 15:55"),
    (_at(16, 0, 35), "15:58", "consumed after the session close"),
])
def test_enguq_entry_outside_the_session_window_logs_one_plain_line(account, now, hhmm, why):
    adapter, fake, _clock = account
    state = {"legs": {}, "events": [], "_px_source": "test"}
    ev = _entry("ENGUQ_335", hhmm, "long")
    logs = []
    _route(state, ev, now, log=logs.append)
    assert state["legs"] == {} and fake.sent == [] and adapter._state.get("broker_sent_positions", {}) == {}
    assert logs == [
        f"[qqq-exec] ENGU-Q long signal at {hhmm} ET on {DAY} not taken: the market is closed "
        f"for new entries -- {why}. No order sent. ({ev['trade_id']})"]
    refused = [r for r in _rows(qe.ORDERS_CSV) if r["leg"] == "ENGUQ"]
    assert len(refused) == 1 and refused[0]["reason"] == f"REFUSED -- {why}", \
        "the orders.csv row is unchanged"
    assert any(e["kind"] == "entry_too_late" for e in state["events"])


# ── 6. ENGU-Q's buy still working when NOISE's short arrives: Webull's box-order rule ───
BOX = ("SELL", 10, "OPENAPI_OPEN_ORDER_HAS_BOX_ORDER")


def _box_order_tick(account, monkeypatch):
    """Flat account, async fills on: ENGU-Q long and NOISE short enter in ONE tick. ENGU-Q's
    BUY 10 goes out (a buy-opening order) and stays working; the adapter booked it on the
    ack, so NOISE's SELL 10 is planned as a closing sell on +10 -- at Webull it is a
    sell-OPENING order next to a working buy-opening one: 417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER.
    Returns (adapter, fake, clock, state, missed) -- `missed` collects every "entry missed"
    phone title (the book's own low "QQQ fill" notes are not this test's business)."""
    adapter, fake, clock = account
    missed = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None: (
        missed.append(title) if "entry missed" in title else None))
    state = {"legs": {}, "events": [], "_px_source": "test"}
    fake.async_fills = True
    qe._route_engine_events(state, _cfg(), [_entry("ENGUQ_335", "10:59", "long", 740.40),
                                            _entry("NOISE_382", "10:59", "short", 740.40)],
                            False, log=NOOP, now=_at(11, 0, 5))
    assert _orders(fake) == [("BUY", 10)] and fake.sent[0]["opening"] is True
    assert fake.refused == [BOX], "NOISE's SELL 10 met ENGU-Q's working buy-opening order"
    assert set(state["legs"]) == {"ENGUQ", "NOISE"}, "the book holds both trades"
    queued = state.get("_broker_resend") or {}
    assert list(queued) == ["NOISE:OPEN"] and queued["NOISE:OPEN"]["why"] == "box_order"
    assert queued["NOISE:OPEN"]["needs_verify"] is False, "a 417 never landed: nothing to verify"
    assert missed == [], "no 'entry missed' yet -- the re-send a few seconds later decides"
    return adapter, fake, clock, state, missed


def test_noise_short_refused_while_enguq_buy_works_is_re_sent_once_the_buy_fills(account,
                                                                                monkeypatch):
    adapter, fake, clock, state, missed = _box_order_tick(account, monkeypatch)

    fake.fill_pending()                        # ENGU-Q's buy fills: Webull holds +10
    assert fake.pos == 10
    clock[0] += qe.BROKER_RESEND_MIN_GAP_SEC + 1
    qe._maybe_resend_broker_orders(state, _cfg(), _at(11, 0, 10), True, log=NOOP)
    assert _orders(fake, 1) == [("SELL", 10)], "NOISE goes out as a SELL 10 against the +10"
    assert fake.sent[1]["opening"] is False and fake.refused == [BOX]
    assert fake.sent[1]["coid"] != fake.sent[0]["coid"]
    fake.fill_pending()
    assert fake.pos == 0 and adapter._account_net("QQQ") == 0
    assert _books(adapter) == {"ENGUQ": 10, "NOISE": -10}, "each leg keeps its own book"
    assert set(state["legs"]) == {"ENGUQ", "NOISE"}
    assert state.get("_broker_resend") == {}
    noise_open = [r["outcome"] for r in _rows(qe.BROKER_ORDERS_CSV)
                  if r["leg"] == "NOISE" and r["intent"] == "OPEN"]
    assert noise_open == ["REFUSED", "OK"], "a definite 4xx refusal, then the accepted re-send"
    texts = [e["text"] for e in state["events"]]
    assert any(t.startswith("QQQ BROKER: NOISE ")
               and t.endswith("re-sent and accepted (after the opposite order finished)")
               for t in texts)
    assert not any("gave up" in t or "entry missed" in t for t in texts)
    assert missed == [] and "entry:NOISE" not in (state.get("_phone_dedupe") or {})


# ── 7. still refused after BROKER_RESEND_MAX_TRIES: one give-up line naming the opposite order ─
def test_noise_short_still_refused_after_max_tries_gives_up_naming_the_opposite_order(
        account, monkeypatch):
    adapter, fake, clock, state, missed = _box_order_tick(account, monkeypatch)

    # ENGU-Q's buy never fills: every re-send meets the same working buy-opening order
    for i in range(qe.BROKER_RESEND_MAX_TRIES):
        clock[0] += qe.BROKER_RESEND_MIN_GAP_SEC + 1
        qe._maybe_resend_broker_orders(state, _cfg(), _at(11, 0, 10 + 5 * i), True, log=NOOP)
    assert fake.refused == [BOX] * (1 + qe.BROKER_RESEND_MAX_TRIES)
    coids = [c.args[1][0]["client_order_id"] for c in fake.order_v3.place_order.call_args_list]
    assert len(coids) == 2 + qe.BROKER_RESEND_MAX_TRIES and len(set(coids)) == len(coids), \
        "ENGU-Q's buy, NOISE's first try, then each re-send under a fresh id"
    assert state["_broker_resend"]["NOISE:OPEN"]["tries"] == qe.BROKER_RESEND_MAX_TRIES
    assert missed == [], "still no 'entry missed' while the re-sends are running"

    clock[0] += qe.BROKER_RESEND_MIN_GAP_SEC + 1
    qe._maybe_resend_broker_orders(state, _cfg(), _at(11, 0, 30), True, log=NOOP)
    assert fake.order_v3.place_order.call_count == len(coids), "the give-up tick sends nothing"
    assert state.get("_broker_resend") == {}
    gave = [e["text"] for e in state["events"] if "gave up" in e["text"]]
    assert len(gave) == 1
    assert gave[0].startswith("QQQ BROKER: gave up re-sending the NOISE ")
    assert (f"({qe.BROKER_RESEND_MAX_TRIES} re-sends failed; first try refused while an "
            f"opposite order was still working)") in gave[0]
    assert gave[0].endswith("The book holds NOISE but Webull does not.")
    assert missed == ["QQQ book: entry missed"], "ONE plain note, at the give-up"
    assert _books(adapter).get("NOISE", 0) == 0 and _books(adapter)["ENGUQ"] == 10
    assert set(state["legs"]) == {"ENGUQ", "NOISE"}, "the book still counts NOISE's trade"
