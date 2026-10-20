"""SAME-ORDER WAIT (2026-10-20, G1) -- api.webull_orders.OrderAdapter's half.

THE INCIDENT (box qqq_exec.log, 2026-10-20 09:35:12). DIP_STREAK and DIP_GAPDN both exited at the
open and sent SELL 6 QQQ in the same instant. Webull took the first and refused the second: 417
OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK -- its risk rule compares the ORDER (side,
quantity, order type, session) against the orders still working on the account, never our
client_order_id. The re-send queue sent it again 6 s later (its R1 id, a REFUSED row and a
re-send row). Same on 10-05 at the 15:59 flatten (ORB + NOISE SELL 10).

THE FIX (this file): place_stock_order(dup_wait_until=...) -- only api/qqq_exec.py's
_mirror_to_broker passes it -- first looks for ANOTHER leg's acked, unsettled part identical to a
part it is about to send. Found: it waits (bounded: gateway.dup_wait_sec, default 3 s, never past
DUP_WAIT_HARD_CAP_SEC from the send's start nor `dup_wait_until`) for Webull's terminal answer,
books it exactly like fill capture, re-plans from the account net, and sends under its OWN id. Not
found: no lookup at all. A wait that runs out sends anyway -- today's path (the 417 and the queue).

FakeWebull scripts the account: an accepted order stays working (async) until its N-th lookup
(`fill_after_lookups`, None = never) fills it -- or kills it, REJECTED with 0 filled, when its id
is in `die`; an order identical to a working one is refused with the duplicate 417. The order
path's waits advance the test clock (webull_orders._sleep), so every bound is checked in time,
not only in lookup counts. No SDK, network or credentials.
"""
import json
from unittest.mock import MagicMock

import pytest

from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731
DUP = "OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK"
T0 = 1_000_000.0


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeWebull:
    """One Webull account, QQQ only: Webull's duplicate rule against working orders, fills on
    the N-th lookup (`fill_after_lookups`), deaths (`die`), scripted refusals (`refuse_next`
    [(qty or None, code)]), lookups counted per id and the clock at every send."""

    def __init__(self, clock):
        self.clock = clock
        self.pos = 0
        self.pending = []
        self.status = {}
        self.qty = {}
        self.fill_after_lookups = None
        self.die = set()
        self.lookups = {}
        self.detail_calls = []
        self.refuse_next = []
        self.sent = []          # (coid, side, qty) of every ACCEPTED order
        self.refused = []       # (side, qty, code)
        self.send_at = {}       # coid -> clock at its place_order
        self.account_v2 = MagicMock()
        self.account_v2.get_account_list.return_value.json.return_value = {
            "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
        self.order_v3 = MagicMock()
        self.order_v3.place_order.side_effect = self._place
        self.order_v3.get_order_detail.side_effect = self._detail

    def working(self, coid, side, qty, kind=("MARKET", "CORE")):
        """An order of another leg Webull is still working (seeded straight into the fake)."""
        self.pending.append({"coid": coid, "side": side, "qty": qty, "kind": kind})
        self.status[coid] = "SUBMITTED"
        self.qty[coid] = qty

    def _refuse(self, side, qty, code):
        self.refused.append((side, qty, code))
        raise RuntimeError(f"ServerException: HTTP Status: 417, Code: {code}, Msg: refused")

    def _place(self, account_id, orders):
        o = orders[0]
        side, qty, coid = o["side"], int(o["quantity"]), o["client_order_id"]
        kind = (o.get("order_type"), o.get("support_trading_session"))
        self.send_at[coid] = self.clock[0]
        if self.refuse_next and self.refuse_next[0][0] in (None, qty):
            self._refuse(side, qty, self.refuse_next.pop(0)[1])
        if any(p["side"] == side and p["qty"] == qty and p["kind"] == kind for p in self.pending):
            self._refuse(side, qty, DUP)
        self.sent.append((coid, side, qty))
        self.working(coid, side, qty, kind)
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": "SUBMITTED", "filled_quantity": "0"}]})

    def _detail(self, account_id, coid):
        self.detail_calls.append(coid)
        self.lookups[coid] = self.lookups.get(coid, 0) + 1
        p = next((p for p in self.pending if p["coid"] == coid), None)
        if p is not None and self.fill_after_lookups is not None \
                and self.lookups[coid] >= self.fill_after_lookups:
            self.pending.remove(p)
            if coid in self.die:
                self.status[coid] = "REJECTED"
            else:
                self.pos += p["qty"] if p["side"] == "BUY" else -p["qty"]
                self.status[coid] = "FILLED"
        st = self.status.get(coid) or "REJECTED"
        item = {"client_order_id": coid, "status": st, "filled_quantity": "0"}
        if st == "FILLED":
            item.update(filled_quantity=str(self.qty[coid]), filled_price="700.00")
        return _Resp({"client_order_id": coid, "orders": [item]})


def _rig(tmp_path, monkeypatch, cfg_extra=None):
    """(adapter, fake, clock): a PAPER adapter on FakeWebull, the order path's clock at T0 and
    its waits advancing it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    clock = [T0]
    monkeypatch.setattr(WO.time, "time", lambda: clock[0])
    monkeypatch.setattr(WO, "_sleep", lambda sec: clock.__setitem__(0, clock[0] + sec))
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"].update(session_start="00:00", session_end="23:59",
                        max_shares_per_leg=100, max_total_position_shares=500)
    for k, name in (("state_path", "state.json"), ("paper_keys_path", "paper_keys.json"),
                    ("live_keys_path", "live_keys.json"), ("arm_live_file", "ARM_LIVE"),
                    ("kill_file", "KILL")):
        cfg[k] = str(tmp_path / name)
    if cfg_extra:
        cfg_extra(cfg)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    fake = FakeWebull(clock)
    monkeypatch.setattr(adapter, "_build_client", lambda mode: fake)
    return adapter, fake, clock


def _seed(adapter, leg, qty, account_id="ACCT1"):
    """As if `leg`'s earlier orders reached Webull and filled: both books hold `qty`."""
    adapter._state.setdefault("broker_sent_positions", {})[leg] = {
        "symbol": "QQQ", "qty": qty, "account_id": account_id}
    adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
    if qty:
        adapter._state.setdefault("open_legs", {})[leg] = True


def _part(adapter, coid, **kw):
    """An order part of another leg the adapter recorded a second ago: acked by Webull, booked
    in full, no terminal answer yet (what a market order looks like until it fills)."""
    p = {"leg": "ORB", "symbol": "QQQ", "side": "SELL", "qty": 10, "intent": "CLOSE",
         "account_id": "ACCT1", "ts": WO.time.time() - 1, "booked": 10, "pending": False,
         "order_type": "MARKET", "session": "CORE"}
    p.update(kw)
    adapter._state.setdefault("order_parts", {})[coid] = p
    return p


def _sent(adapter, leg):
    return (adapter._state.get("broker_sent_positions") or {}).get(leg, {}).get("qty", 0)


def _place(adapter, leg, signal, side, qty, intent, **kw):
    return adapter.place_stock_order(leg=leg, signal_id=signal, symbol="QQQ", side=side,
                                     qty=qty, intent=intent, **kw)


def _long_20_with_orb_s_close_working(tmp_path, monkeypatch, **kw):
    """ORB long 10 + NOISE long 10 (account +20); ORB's CLOSE SELL 10 acked and still working --
    the 10-05 15:59:01 pair."""
    adapter, fake, clock = _rig(tmp_path, monkeypatch, **kw)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "NOISE", 10)
    fake.pos = 20
    orb = _place(adapter, "ORB", "qxORBC", "SELL", 10, "CLOSE")
    assert orb["ok"] is True and [p["coid"] for p in fake.pending] == ["qxORBC"]
    return adapter, fake, clock


# ── A1. the identical close waits for the other leg's fill, then goes under its own id ─────────

def test_a1_an_identical_close_waits_for_the_fill_and_goes_under_its_primary_id(tmp_path, monkeypatch):
    adapter, fake, clock = _long_20_with_orb_s_close_working(tmp_path, monkeypatch)
    fake.fill_after_lookups = 1

    rec = _place(adapter, "NOISE", "qxNOISEC", "SELL", 10, "CLOSE", dup_wait_until=clock[0] + 8)

    assert fake.refused == [], "no 417"
    assert rec["ok"] is True and rec["dup_wait"]["settled"] is True
    assert rec["dup_wait"]["for"] == ["qxORBC"] and rec["dup_wait"]["changed"] == 0
    assert adapter._state["order_parts"]["qxORBC"]["final_status"] == "FILLED"
    assert fake.detail_calls == ["qxORBC"], "exactly one lookup"
    assert (_sent(adapter, "ORB"), _sent(adapter, "NOISE")) == (0, 0)
    assert [s for s in fake.sent] == [("qxORBC", "SELL", 10), ("qxNOISEC", "SELL", 10)]
    assert rec["client_order_id"] == rec["parts"][0]["client_order_id"] == "qxNOISEC", \
        "the PRIMARY id -- never an R<n> re-send id, never a split suffix"
    assert "dup_wait" not in adapter._state["orders"]["qxORBC"]
    assert adapter._state.get("part_events") is None, "nothing changed, no part event"


# ── A2. no lookup at all when nothing identical of another leg is working ──────────────────────

@pytest.mark.parametrize("why,kw", [
    ("a different quantity", {"qty": 9}),
    ("a different side (SHORT, not SELL)", {"side": "SHORT"}),
    ("a different side (BUY)", {"side": "BUY"}),
    ("a LIMIT extended-hours order", {"order_type": "LIMIT", "session": "ALL"}),
    ("older than 30 s", {"ts": T0 - WO.DUP_WAIT_FRESH_SEC - 1}),
    ("refused outright (4xx: booked 0, not pending)", {"booked": 0, "pending": False}),
    ("a resting order", {"resting": True}),
    ("the SAME leg's own order", {"leg": "NOISE"}),
    ("another account's order", {"account_id": "ACCT2"}),
    ("already answered terminal", {"final_status": "FILLED"}),
])
def test_a2_no_lookup_and_no_dup_wait_key_when_nothing_identical_is_working(
        tmp_path, monkeypatch, why, kw):
    adapter, fake, clock = _rig(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "NOISE", 10)
    _part(adapter, "qxORBC", **kw)

    rec = _place(adapter, "NOISE", "qxNOISEC", "SELL", 10, "CLOSE", dup_wait_until=clock[0] + 8)

    assert fake.detail_calls == [], why
    assert "dup_wait" not in rec and rec["ok"] is True
    assert clock[0] == T0, "not a moment waited"


def test_a2_control_the_same_part_unchanged_is_waited_for(tmp_path, monkeypatch):
    adapter, fake, clock = _rig(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "NOISE", 10)
    _part(adapter, "qxORBC")
    fake.status["qxORBC"], fake.qty["qxORBC"] = "FILLED", 10

    rec = _place(adapter, "NOISE", "qxNOISEC", "SELL", 10, "CLOSE", dup_wait_until=clock[0] + 8)

    assert fake.detail_calls == ["qxORBC"] and rec["dup_wait"]["settled"] is True


def test_a2_a_split_s_second_part_is_checked_up_front(tmp_path, monkeypatch):
    """ORB long 10 filled, DIP_RSI's SHORT 6 acked and working (books net +4): NOISE's SHORT 10
    is planned SELL 4 + SHORT 6 -- its part 2 is DIP_RSI's order, so it waits before part 1."""
    adapter, fake, clock = _rig(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "DIP_RSI", -6)
    _part(adapter, "qxDIPRSI", leg="DIP_RSI", side="SHORT", qty=6, intent="OPEN", booked=6)
    fake.working("qxDIPRSI", "SHORT", 6)
    fake.pos = 10
    fake.fill_after_lookups = 1

    rec = _place(adapter, "NOISE", "qxNOISEO", "SHORT", 10, "OPEN", dup_wait_until=clock[0] + 8)

    assert fake.detail_calls[0] == "qxDIPRSI" and rec["dup_wait"]["for"] == ["qxDIPRSI"]
    assert [(s, q) for _c, s, q in fake.sent] == [("SELL", 4), ("SHORT", 6)]
    assert fake.refused == [] and rec["ok"] is True


def test_a2_an_extended_hours_order_never_waits(tmp_path, monkeypatch):
    """After hours (LIMIT, session ALL) the adapter never waits, even for an identical working
    after-hours order of another leg -- api/qqq_exec.py's _ah_send never asks either."""
    adapter, fake, clock = _rig(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 10)
    _seed(adapter, "NOISE", 10)
    _part(adapter, "qxORBA", order_type="LIMIT", session="ALL")
    fake.working("qxORBA", "SELL", 10, kind=("LIMIT", "ALL"))
    fake.pos = 20

    rec = _place(adapter, "NOISE", "qxNOISEA", "SELL", 10, "CLOSE", order_type="LIMIT",
                 limit_price=700.0, extended_hours=True, dup_wait_until=clock[0] + 8)

    assert fake.detail_calls == [] and "dup_wait" not in rec
    assert fake.refused == [("SELL", 10, DUP)], "today's path: Webull's own answer"


# ── A3 + the kill switch: no dup_wait_until, or dup_wait_sec 0, is today's path byte for byte ──

def _today_s_send(tmp_path, monkeypatch, **kw):
    adapter, fake, clock = _long_20_with_orb_s_close_working(tmp_path, monkeypatch)
    fake.fill_after_lookups = 1      # a lookup WOULD fill it -- none may happen
    if kw.pop("kill", False):
        adapter.set_dup_wait(0)
    rec = _place(adapter, "NOISE", "qxNOISEC", "SELL", 10, "CLOSE", **kw)
    return rec, json.loads(json.dumps(adapter._state)), fake


@pytest.mark.parametrize("kw", [{"dup_wait_until": None},
                                {"dup_wait_until": T0 + 8, "kill": True}])
def test_a3_no_until_or_the_kill_switch_is_byte_identical_to_today(tmp_path, monkeypatch, kw):
    base_rec, base_state, base_fake = _today_s_send(tmp_path / "base", monkeypatch)
    rec, state, fake = _today_s_send(tmp_path / "other", monkeypatch, **kw)

    assert fake.detail_calls == base_fake.detail_calls == []
    assert fake.refused == base_fake.refused == [("SELL", 10, DUP)]
    assert rec == base_rec and "dup_wait" not in rec
    assert state == base_state


# ── A4. the bounds, in time: the wait runs out, the order goes anyway (today's 417) ────────────

@pytest.mark.parametrize("until_in,cap,window", [
    (8.0, None, 3.0),     # the config's 3 s binds
    (1.0, None, 1.0),     # the caller's until binds first
    (8.0, 10.0, 4.0),     # dup_wait_sec 10 is capped at DUP_WAIT_HARD_CAP_SEC
])
def test_a4_a_wait_that_runs_out_sends_anyway_inside_its_bounds(
        tmp_path, monkeypatch, until_in, cap, window):
    adapter, fake, clock = _long_20_with_orb_s_close_working(tmp_path, monkeypatch)
    if cap is not None:
        adapter.set_dup_wait(cap)
    started = clock[0]

    rec = _place(adapter, "NOISE", "qxNOISEC", "SELL", 10, "CLOSE",
                 dup_wait_until=started + until_in)

    assert rec["ok"] is False and rec["http_status"] == 417
    assert adapter._state["order_parts"]["qxNOISEC"]["booked"] == 0
    assert fake.refused == [("SELL", 10, DUP)], "sent anyway: today's refusal"
    assert rec["dup_wait"]["settled"] is False
    assert 1 <= fake.lookups["qxORBC"] <= WO.DUP_WAIT_POLL_TRIES
    assert fake.send_at["qxNOISEC"] - started <= window + 1e-9, "never past its bound"
    assert rec["dup_wait"]["waited_sec"] >= window * 7 / 8 - 1e-6, "and it used the window"
    assert window <= WO.DUP_WAIT_HARD_CAP_SEC


def test_a4_no_wait_once_the_send_has_already_used_its_hard_cap(tmp_path, monkeypatch):
    """A send that waited on the adapter lock (or the gateway) past DUP_WAIT_HARD_CAP_SEC from
    its start never waits more -- no lookup, today's path."""
    adapter, fake, clock = _long_20_with_orb_s_close_working(tmp_path, monkeypatch)
    until = clock[0] + 8
    real = adapter._account_id

    def slow_account_read(*a, **k):
        clock[0] += WO.DUP_WAIT_HARD_CAP_SEC + 0.5
        return real(*a, **k)
    monkeypatch.setattr(adapter, "_account_id", slow_account_read)

    rec = _place(adapter, "NOISE", "qxNOISEC", "SELL", 10, "CLOSE", dup_wait_until=until)

    assert fake.detail_calls == [] and rec["dup_wait"]["settled"] is False
    assert rec["dup_wait"]["waited_sec"] == 0.0
    assert fake.refused == [("SELL", 10, DUP)]


# ── A5. the identical order dies: books roll back, NOISE is re-planned from the true net ───────

def test_a5_a_dead_identical_order_rolls_back_and_the_send_is_re_planned(tmp_path, monkeypatch):
    """ENGUQ long 5, ORB short 10 (account -5). ORB's covering BUY 10 is acked and working --
    the books count it, net +5. NOISE's OPEN BUY 10 is planned [BUY 10] on that net: identical,
    so it waits. Webull then reports ORB's cover REJECTED with nothing filled: ORB's books go
    back to -10, one part event says so, and NOISE goes out planned from the TRUE net -5 --
    BUY 5 (closing) + BUY 5 (opening), the existing split sequencing."""
    adapter, fake, clock = _rig(tmp_path, monkeypatch)
    _seed(adapter, "ENGUQ", 5)
    _seed(adapter, "ORB", 0)
    _part(adapter, "qxORBC", side="BUY", qty=10, booked=10)
    fake.working("qxORBC", "BUY", 10)
    fake.pos = -5
    fake.die = {"qxORBC"}
    fake.fill_after_lookups = 1
    assert adapter._account_net("QQQ") == 5

    rec = _place(adapter, "NOISE", "qxNOISEO", "BUY", 10, "OPEN", dup_wait_until=clock[0] + 8)

    assert _sent(adapter, "ORB") == -10, "ORB's cover never happened -- rolled back"
    assert adapter._state["part_events"] == [
        {"client_order_id": "qxORBC", "leg": "ORB", "intent": "CLOSE", "status": "REJECTED",
         "qty": 10, "booked": 0, "change": -10}]
    assert rec["dup_wait"] == {"for": ["qxORBC"], "settled": True, "changed": 10,
                               "waited_sec": 0.0}
    assert [(c, s, q) for c, s, q in fake.sent] == [("qxNOISEO-1", "BUY", 5),
                                                    ("qxNOISEO-2", "BUY", 5)]
    assert rec["ok"] is True and _sent(adapter, "NOISE") == 10
    assert fake.refused == []


# ── A6. the config ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,cap", [
    (0, 0.0), ("x", 0.0), (float("nan"), 0.0), (float("inf"), 0.0), (-1, 0.0), (None, 0.0),
    (10, WO.DUP_WAIT_HARD_CAP_SEC), (2.5, 2.5), ("1.5", 1.5),
])
def test_a6_dup_wait_sec_parses_bad_values_as_off_and_caps_big_ones(tmp_path, monkeypatch, value, cap):
    adapter, fake, clock = _rig(tmp_path, monkeypatch,
                                cfg_extra=lambda c: c["gateway"].update(dup_wait_sec=value))
    assert adapter._dup_wait_cap() == cap
    adapter.set_dup_wait(1.0)
    assert adapter._dup_wait_cap() == 1.0, "set_dup_wait overrides the config"
    adapter.set_dup_wait(None)
    assert adapter._dup_wait_cap() == cap, "None goes back to the config"


@pytest.mark.parametrize("value", [0, "x", float("nan"), -1])
def test_a6_an_off_value_means_no_lookup_at_all(tmp_path, monkeypatch, value):
    adapter, fake, clock = _long_20_with_orb_s_close_working(
        tmp_path, monkeypatch, cfg_extra=lambda c: c["gateway"].update(dup_wait_sec=value))
    fake.fill_after_lookups = 1
    rec = _place(adapter, "NOISE", "qxNOISEC", "SELL", 10, "CLOSE", dup_wait_until=clock[0] + 8)
    assert fake.detail_calls == [] and "dup_wait" not in rec
    assert fake.refused == [("SELL", 10, DUP)]


def test_a6_the_default_is_on_at_3s_and_a_box_gateway_block_without_it_keeps_3s(tmp_path):
    assert WO.DEFAULT_GATEWAY["dup_wait_sec"] == 3.0
    assert WO.load_config(str(tmp_path / "missing.json"))["gateway"]["dup_wait_sec"] == 3.0
    path = tmp_path / "webull_orders_config.json"
    path.write_text(json.dumps({"mode": "OFF", "gateway": {"prev_terminal": False}}),
                    encoding="utf-8")
    cfg = WO.load_config(str(path))
    assert cfg["gateway"] == {"prev_terminal": False, "dup_wait_sec": 3.0}
    cfg["state_path"] = str(tmp_path / "state.json")
    cfg["kill_file"] = str(tmp_path / "KILL")
    assert WO.OrderAdapter(config=cfg, log=NOOP)._dup_wait_cap() == 3.0
    path.write_text(json.dumps({"mode": "OFF", "gateway": {"dup_wait_sec": 0}}), encoding="utf-8")
    assert WO.load_config(str(path))["gateway"]["dup_wait_sec"] == 0, "the kill switch"
    assert WO.DUP_WAIT_FRESH_SEC == WO.CROSS_FRESH_PART_SEC


# ── A7. an OPEN whose wait moved the books goes through the rails again ────────────────────────

def test_a7_an_open_is_re_railed_when_a_dead_close_rolled_the_books_back(tmp_path, monkeypatch):
    """Gross cap 20. ORB's cover BUY 10 (acked, working) has the books at ORB 0 + ENGUQ 5, so
    NOISE's OPEN BUY 10 passes the rails (15). Webull then reports that cover dead: ORB is
    short 10 again, the books hold 25 with NOISE's 10 -- BLOCKED, nothing sent."""
    adapter, fake, clock = _rig(
        tmp_path, monkeypatch,
        cfg_extra=lambda c: c["rails"].update(max_total_position_shares=20))
    _seed(adapter, "ENGUQ", 5)
    _seed(adapter, "ORB", 0)
    _part(adapter, "qxORBC", side="BUY", qty=10, booked=10)
    fake.working("qxORBC", "BUY", 10)
    fake.die = {"qxORBC"}
    fake.fill_after_lookups = 1

    rec = _place(adapter, "NOISE", "qxNOISEO", "BUY", 10, "OPEN", dup_wait_until=clock[0] + 8)

    assert rec["mode"] == "BLOCKED" and rec["ok"] is False and rec["sent"] is False
    assert "projected total position 25 exceeds max_total_position_shares 20" in rec["reason"]
    assert rec["dup_wait"]["changed"] == 10
    assert fake.sent == [], "nothing sent"
    assert _sent(adapter, "ORB") == -10 and _sent(adapter, "NOISE") == 0
    assert adapter._state["orders"]["qxNOISEO"]["mode"] == "BLOCKED"
    assert "qxNOISEO" not in adapter._state["order_parts"]


def test_a7_a_close_is_never_re_railed(tmp_path, monkeypatch):
    """Same roll-back, but the order waiting is NOISE's CLOSE (a cover BUY 10 planned on net +5):
    a close is never blocked by the entry rails, so it goes -- re-planned on the true net -5."""
    adapter, fake, clock = _rig(
        tmp_path, monkeypatch,
        cfg_extra=lambda c: c["rails"].update(max_total_position_shares=1))
    _seed(adapter, "ENGUQ", 15)
    _seed(adapter, "NOISE", -10)
    _seed(adapter, "ORB", 0)
    _part(adapter, "qxORBC", side="BUY", qty=10, booked=10)
    fake.working("qxORBC", "BUY", 10)
    fake.die = {"qxORBC"}
    fake.fill_after_lookups = 1

    rec = _place(adapter, "NOISE", "qxNOISEC", "BUY", 10, "CLOSE", dup_wait_until=clock[0] + 8)

    assert rec["dup_wait"]["changed"] == 10 and rec["mode"] == "PAPER"
    assert [(c, s, q) for c, s, q in fake.sent] == [("qxNOISEC-1", "BUY", 5),
                                                    ("qxNOISEC-2", "BUY", 5)]
    assert _sent(adapter, "ORB") == -10 and _sent(adapter, "NOISE") == 0


# ── the settle helper ──────────────────────────────────────────────────────────────────────────

def test_settle_part_answer_books_only_a_terminal_answer(tmp_path, monkeypatch):
    adapter, fake, clock = _rig(tmp_path, monkeypatch)
    _seed(adapter, "ORB", 0)
    _part(adapter, "qxORBC", side="SELL", qty=10, booked=10)
    assert adapter._settle_part_answer("nope", {"status": "FILLED", "filled": 10}) == 0
    assert adapter._settle_part_answer("qxORBC", None) is None
    assert adapter._settle_part_answer("qxORBC", {"status": "SUBMITTED", "filled": 0}) is None
    assert adapter._settle_part_answer("qxORBC", {"status": "CANCELLED", "filled": None}) is None
    assert "final_status" not in adapter._state["order_parts"]["qxORBC"]
    assert adapter._settle_part_answer("qxORBC", {"status": "CANCELLED", "filled": 4}) == -6
    assert adapter._state["order_parts"]["qxORBC"]["final_status"] == "CANCELLED"
    assert _sent(adapter, "ORB") == 6
    assert adapter._settle_part_answer("qxORBC", {"status": "CANCELLED", "filled": 4}) == 0, \
        "idempotent"
    assert len(adapter._state["part_events"]) == 1
