"""ORDER NETTING (2026-09-24) -- api.webull_orders.OrderAdapter.place_stock_order plans
the REAL broker order(s) for a leg's request from the ACCOUNT's current net position
for that symbol, instead of sending the leg's own literal SELL/SHORT/BUY straight
through. See that module's own "ORDER NETTING" docstring section for the full writeup
of why: the QQQ paper book runs three legs (ORB/ENGUQ/NOISE) on ONE Webull margin
account, Webull holds exactly ONE position per symbol, and a leg's own SELL/SHORT
literally sent to Webull collided with another leg's opposite position -- the
2026-09-23 incident this feature exists to fix (HTTP 417
OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION, then a "close" the per-leg nothing-to-close
guard correctly refused to send because the OPEN it was supposed to close had itself
been refused).

FakeWebullClient below is a hand-rolled double that enforces the three Webull rules
this feature exists to work around (never mocked to just always succeed, unlike most of
this repo's other webull_orders tests -- see tests/test_webull_orders.py's own
MagicMock-based `_mock_client`, which is right for tests that are not exercising
collision behaviour):
  * Webull holds exactly ONE position per symbol (self.positions[symbol], a signed int
    -- positive long, negative short, shared across every "leg" that sends through it,
    exactly like the real account);
  * SIDE=SHORT is refused while that position is already > 0 (long) -- the exact 417
    from the bug report;
  * SIDE=SELL for a qty greater than the current long position is refused (can't sell
    what you don't hold);
  * SIDE=BUY that would cross the position from negative straight through to positive
    in ONE order is refused -- the GUESSED BEHAVIOUR api.webull_orders's module
    docstring flags (no live sandbox to confirm this specific rule against; the SHORT
    and SELL refusals above ARE both real, observed 417s).
Every accepted order updates self.positions immediately (synchronous, like a market
fill) and is appended to self.orders for a test to inspect.

No real webull SDK, network, or credentials anywhere -- same discipline as
tests/test_webull_orders.py's own module docstring.
"""
import csv
import itertools
import json
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731


# ── fixtures / helpers (same shape as tests/test_webull_orders.py's own) ───────────

def _cfg(tmp_path, mode="PAPER", rails=None, **extra):
    cfg = WO.load_config("__no_such_file__")   # defaults only
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["rails"]["max_shares_per_leg"] = 100
    cfg["rails"]["max_total_position_shares"] = 500
    if rails:
        cfg["rails"].update(rails)
    cfg["state_path"] = str(tmp_path / "state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "KILL")
    cfg.update(extra)
    return cfg


def _write_keys(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)


class _Resp:
    """Just enough of the SDK's Response shape (`.json()`) for _safe_response."""
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeWebullClient:
    """See module docstring. `positions` is the account's one-per-symbol ground truth;
    `orders` is every ACCEPTED order in send order, each {account_id, symbol, side,
    qty, client_order_id} -- a test's own record of "what Webull actually did"."""

    def __init__(self):
        self.positions = {}
        self.orders = []
        self.account_v2 = MagicMock()
        self.account_v2.get_account_list.return_value.json.return_value = {
            "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
        self.account_v2.get_account_position.return_value.json.return_value = {"data": []}
        self.order_v3 = MagicMock()
        self.order_v3.place_order.side_effect = self._place_order

    def _place_order(self, account_id, orders):
        assert len(orders) == 1, "this adapter only ever places single-order combos"
        o = orders[0]
        symbol, side, qty = o["symbol"], o["side"], int(o["quantity"])
        pos = self.positions.get(symbol, 0)
        if side == "SHORT":
            if pos > 0:
                raise RuntimeError(
                    "HTTP 417 OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION: Please close "
                    "your existing long positions of this security before placing a "
                    "short order")
            new_pos = pos - qty
        elif side == "SELL":
            if qty > pos:
                raise RuntimeError(
                    "HTTP 417 OPENAPI_ORDER_EXCEED_POSITION: sell quantity exceeds the "
                    "held long position")
            new_pos = pos - qty
        elif side == "BUY":
            new_pos = pos + qty
            if pos < 0 and new_pos > 0:
                raise RuntimeError(
                    "HTTP 417 OPENAPI_ORDER_CROSSES_POSITION: this order would cross "
                    "from a short position to a long position")
        else:
            raise RuntimeError(f"unknown side {side!r}")
        self.positions[symbol] = new_pos
        self.orders.append({"account_id": account_id, "symbol": symbol, "side": side,
                            "qty": qty, "client_order_id": o["client_order_id"]})
        return _Resp({"client_order_id": o["client_order_id"], "combo_type": "NORMAL",
                      "orders": [{"client_order_id": o["client_order_id"], "status": "FILLED",
                                 "filled_price": "100.00", "filled_quantity": str(qty)}]})


def _adapter(tmp_path, monkeypatch, **cfg_kwargs):
    cfg = _cfg(tmp_path, **cfg_kwargs)
    _write_keys(cfg["paper_keys_path"])
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    fake = FakeWebullClient()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: fake)
    return adapter, fake


def _part_sides(rec):
    return [(p["side"], p["qty"]) for p in rec["parts"]]


# ── FakeWebullClient's own rules, exercised directly (proves the double models the
# real refusals this feature exists to work around, independent of the adapter) ────

def test_fake_broker_refuses_short_while_long():
    fake = FakeWebullClient()
    fake._place_order("A1", [{"symbol": "QQQ", "side": "BUY", "quantity": "10",
                              "client_order_id": "c1"}])
    with pytest.raises(RuntimeError, match="417"):
        fake._place_order("A1", [{"symbol": "QQQ", "side": "SHORT", "quantity": "5",
                                  "client_order_id": "c2"}])
    assert fake.positions["QQQ"] == 10, "a refused order must not move the position"


def test_fake_broker_refuses_oversized_sell():
    fake = FakeWebullClient()
    fake._place_order("A1", [{"symbol": "QQQ", "side": "BUY", "quantity": "5",
                              "client_order_id": "c1"}])
    with pytest.raises(RuntimeError, match="417"):
        fake._place_order("A1", [{"symbol": "QQQ", "side": "SELL", "quantity": "10",
                                  "client_order_id": "c2"}])
    assert fake.positions["QQQ"] == 5


def test_fake_broker_refuses_buy_crossing_short_to_long():
    fake = FakeWebullClient()
    fake._place_order("A1", [{"symbol": "QQQ", "side": "SHORT", "quantity": "10",
                              "client_order_id": "c1"}])
    with pytest.raises(RuntimeError, match="417"):
        fake._place_order("A1", [{"symbol": "QQQ", "side": "BUY", "quantity": "15",
                                  "client_order_id": "c2"}])
    assert fake.positions["QQQ"] == -10
    # covering EXACTLY to flat, or staying short, is fine -- only crossing THROUGH
    # zero in one order is refused.
    fake._place_order("A1", [{"symbol": "QQQ", "side": "BUY", "quantity": "10",
                              "client_order_id": "c3"}])
    assert fake.positions["QQQ"] == 0


# ── _plan_broker_parts: pure function, every boundary from the spec ────────────────

def test_plan_sell_direction_enough_long_is_a_plain_sell():
    assert WO._plan_broker_parts(10, "SELL", 5) == [("SELL", 5)]
    assert WO._plan_broker_parts(5, "SELL", 5) == [("SELL", 5)], "net == qty: no split"


def test_plan_sell_direction_flat_or_short_is_a_plain_short():
    assert WO._plan_broker_parts(0, "SELL", 5) == [("SHORT", 5)]
    assert WO._plan_broker_parts(-3, "SELL", 5) == [("SHORT", 5)]


def test_plan_sell_direction_crossing_splits_sell_then_short():
    assert WO._plan_broker_parts(3, "SELL", 5) == [("SELL", 3), ("SHORT", 2)]


def test_plan_buy_direction_plain_buy_when_not_crossing():
    assert WO._plan_broker_parts(-5, "BUY", 5) == [("BUY", 5)], "net == -qty: no split"
    assert WO._plan_broker_parts(-5, "BUY", 3) == [("BUY", 3)]
    assert WO._plan_broker_parts(0, "BUY", 5) == [("BUY", 5)]
    assert WO._plan_broker_parts(5, "BUY", 5) == [("BUY", 5)]


def test_plan_buy_direction_crossing_splits_cover_then_buy():
    assert WO._plan_broker_parts(-5, "BUY", 8) == [("BUY", 5), ("BUY", 3)]


def test_plan_zero_or_negative_qty_returns_nothing():
    assert WO._plan_broker_parts(0, "SELL", 0) == []
    assert WO._plan_broker_parts(5, "BUY", -1) == []


# ── _part_client_order_id ───────────────────────────────────────────────────────────

def test_part_id_unchanged_when_not_split():
    assert WO._part_client_order_id("abc123", 1, 1) == "abc123"


def test_part_id_distinct_and_within_32_chars_when_split():
    base = "qxNOISE38220260924T182500ZO"  # 28 chars, room to spare
    p1 = WO._part_client_order_id(base, 1, 2)
    p2 = WO._part_client_order_id(base, 2, 2)
    assert p1 != p2
    assert len(p1) <= WO.CLIENT_ORDER_ID_MAX and len(p2) <= WO.CLIENT_ORDER_ID_MAX
    assert p1.endswith("-1") and p2.endswith("-2")


def test_part_id_fits_32_chars_even_from_a_maxed_out_base():
    base = "a" * WO.CLIENT_ORDER_ID_MAX          # already at the limit (the sha1-hash case)
    p1 = WO._part_client_order_id(base, 1, 2)
    p2 = WO._part_client_order_id(base, 2, 2)
    assert len(p1) == WO.CLIENT_ORDER_ID_MAX and len(p2) == WO.CLIENT_ORDER_ID_MAX
    assert p1 != p2


# ── unchanged behaviour when only one leg is open ───────────────────────────────────

def test_single_leg_open_is_byte_identical_to_the_pre_netting_shape(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    rec = adapter.place_stock_order(leg="ORB", signal_id="sig-open", symbol="QQQ",
                                    side="BUY", qty=5, intent="OPEN")
    assert rec["ok"] is True and rec["sent"] is True
    assert rec["client_order_id"] == "sig-open"
    assert rec["side"] == "BUY" and rec["qty"] == 5
    assert len(rec["parts"]) == 1
    assert rec["parts"][0] == {"side": "BUY", "qty": 5, "client_order_id": "sig-open",
                               "ok": True, "sent": True, "reason": "",
                               "response": rec["response"]}
    assert fake.orders == [{"account_id": "ACCT1", "symbol": "QQQ", "side": "BUY",
                            "qty": 5, "client_order_id": "sig-open"}]

    rec_close = adapter.place_stock_order(leg="ORB", signal_id="sig-close", symbol="QQQ",
                                          side="SELL", qty=5, intent="CLOSE")
    assert rec_close["ok"] is True
    assert len(rec_close["parts"]) == 1
    assert rec_close["parts"][0]["side"] == "SELL"
    assert adapter._account_net("QQQ") == 0
    assert fake.positions["QQQ"] == 0


# ── today's exact sequence (2026-09-23 incident), replayed with netting live ───────
# The real broken day (see module docstring): NOISE's 14:10 and 14:30 re-opens were
# each refused (417), and NOISE's 14:25 close was correctly never sent because its
# own open never reached Webull. Same sequence, same sizes -- every step must now be
# ACCEPTED, and the account must be flat after the 15:59 EOD flatten.

def test_todays_exact_sequence_replayed(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    steps = []

    def do(leg, side, qty, intent, sig):
        rec = adapter.place_stock_order(leg=leg, signal_id=sig, symbol="QQQ", side=side,
                                        qty=qty, intent=intent)
        steps.append((sig, rec, adapter._account_net("QQQ")))
        return rec

    r1 = do("NOISE", "SHORT", 10, "OPEN", "1135-noise-open")            # 11:35
    r2 = do("ENGUQ", "BUY", 10, "OPEN", "1401-enguq-open")              # 14:01
    r3 = do("NOISE", "BUY", 10, "CLOSE", "1405-noise-close-1")          # 14:05
    r4 = do("NOISE", "SHORT", 10, "OPEN", "1410-noise-open-2")          # 14:10 -- was REFUSED
    r5 = do("NOISE", "BUY", 10, "CLOSE", "1425-noise-close-2")          # 14:25 -- was NOT SENT
    r6 = do("NOISE", "SHORT", 10, "OPEN", "1430-noise-open-3")          # 14:30 -- was REFUSED
    r7 = do("ENGUQ", "SELL", 10, "CLOSE", "1559-enguq-eod")             # 15:59 EOD
    r8 = do("NOISE", "BUY", 10, "CLOSE", "1559-noise-eod")              # 15:59 EOD

    # every single step is accepted -- the whole point of the fix.
    for sig, rec, _net in steps:
        assert rec["ok"] is True, f"{sig} was refused: {rec.get('reason') or rec.get('error')}"

    # the LEG's own request is preserved verbatim regardless of what actually got sent
    # to the broker -- qqq_exec's own P&L/side bookkeeping never sees a difference.
    assert r4["side"] == "SHORT" and r4["qty"] == 10
    assert r6["side"] == "SHORT" and r6["qty"] == 10

    # what actually reached Webull at each of the two previously-broken steps: the
    # account was long 10 (from ENGUQ) both times, so NOISE's own "open a short" is
    # translated into a SELL against that shared long, never a bare SHORT.
    assert _part_sides(r4) == [("SELL", 10)]
    assert _part_sides(r6) == [("SELL", 10)]
    # the steps that were already accidentally correct in the old, unfixed code (they
    # never collided) still send the plain order they always did.
    assert _part_sides(r1) == [("SHORT", 10)]
    assert _part_sides(r2) == [("BUY", 10)]
    assert _part_sides(r3) == [("BUY", 10)]
    assert _part_sides(r5) == [("BUY", 10)]

    # account net right after EACH step == sum of legs' own broker_sent_positions AT
    # THAT MOMENT (captured inline by `do`, since _account_net reflects live state --
    # checking it only at the end would just re-check the LAST value eight times).
    expected_net_after = [-10, 0, 10, 0, 10, 0, -10, 0]
    for (sig, rec, net_after), want in zip(steps, expected_net_after):
        assert net_after == want, f"after {sig}"
    assert fake.positions["QQQ"] == 0
    assert adapter._account_net("QQQ") == 0, "account must be flat after the 15:59 flatten"

    # each leg's OWN book is flat too (both fully closed by end of day).
    sent = adapter._state["broker_sent_positions"]
    assert sent["ENGUQ"]["qty"] == 0
    assert sent["NOISE"]["qty"] == 0


# ── ENGUQ long 10, then NOISE short 20 (run #382 2x sizing) -> SELL 10 + SHORT 10 ──

def test_enguq_long_then_noise_short_2x_splits_sell_and_short(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch, rails={"max_shares_per_leg": 20})
    r_enguq = adapter.place_stock_order(leg="ENGUQ", signal_id="e-open", symbol="QQQ",
                                        side="BUY", qty=10, intent="OPEN")
    assert r_enguq["ok"] is True
    r_noise = adapter.place_stock_order(leg="NOISE", signal_id="n-open", symbol="QQQ",
                                        side="SHORT", qty=20, intent="OPEN")
    assert r_noise["ok"] is True
    assert _part_sides(r_noise) == [("SELL", 10), ("SHORT", 10)]
    assert fake.positions["QQQ"] == -10
    assert adapter._account_net("QQQ") == -10
    # exits in both orders are covered by the parametrized test right below, each on
    # its own fresh copy of this exact book (see _fresh_split_book).


def _fresh_split_book(tmp_path, monkeypatch, name):
    """ENGUQ long 10 + NOISE short 20 (both already open, exactly like the test just
    above), in a brand-new tmp_path/adapter/fake so each exit-order permutation starts
    from identical, independent state."""
    sub = tmp_path / name
    sub.mkdir()
    adapter, fake = _adapter(sub, monkeypatch, rails={"max_shares_per_leg": 20})
    adapter.place_stock_order(leg="ENGUQ", signal_id="e-open", symbol="QQQ", side="BUY",
                              qty=10, intent="OPEN")
    adapter.place_stock_order(leg="NOISE", signal_id="n-open", symbol="QQQ", side="SHORT",
                              qty=20, intent="OPEN")
    return adapter, fake


@pytest.mark.parametrize("first, second", [("ENGUQ", "NOISE"), ("NOISE", "ENGUQ")])
def test_enguq_noise_2x_exits_in_both_orders_land_flat(tmp_path, monkeypatch, first, second):
    adapter, fake = _fresh_split_book(tmp_path, monkeypatch, f"order-{first}-{second}")
    close_side = {"ENGUQ": "SELL", "NOISE": "BUY"}
    close_qty = {"ENGUQ": 10, "NOISE": 20}
    for leg in (first, second):
        rec = adapter.place_stock_order(leg=leg, signal_id=f"{leg}-close", symbol="QQQ",
                                        side=close_side[leg], qty=close_qty[leg],
                                        intent="CLOSE")
        assert rec["ok"] is True, f"closing {leg} failed: {rec.get('reason')}"
    assert adapter._account_net("QQQ") == 0
    assert fake.positions["QQQ"] == 0
    sent = adapter._state["broker_sent_positions"]
    assert sent["ENGUQ"]["qty"] == 0 and sent["NOISE"]["qty"] == 0


# ── ORB long + ENGUQ long + NOISE short, exits in every permutation ─────────────────

@pytest.mark.parametrize("order", list(itertools.permutations(["ORB", "ENGUQ", "NOISE"])))
def test_three_leg_mixed_book_exits_in_every_permutation_land_flat(tmp_path, monkeypatch, order):
    sub = tmp_path / "-".join(order)
    sub.mkdir()
    adapter, fake = _adapter(sub, monkeypatch)
    adapter.place_stock_order(leg="ORB", signal_id="orb-open", symbol="QQQ", side="BUY",
                              qty=5, intent="OPEN")
    adapter.place_stock_order(leg="ENGUQ", signal_id="enguq-open", symbol="QQQ", side="BUY",
                              qty=5, intent="OPEN")
    adapter.place_stock_order(leg="NOISE", signal_id="noise-open", symbol="QQQ", side="SHORT",
                              qty=10, intent="OPEN")
    assert adapter._account_net("QQQ") == 0, "10 long + 10 short nets to flat before any exit"

    close_side = {"ORB": "SELL", "ENGUQ": "SELL", "NOISE": "BUY"}
    close_qty = {"ORB": 5, "ENGUQ": 5, "NOISE": 10}
    for leg in order:
        rec = adapter.place_stock_order(leg=leg, signal_id=f"{leg}-close", symbol="QQQ",
                                        side=close_side[leg], qty=close_qty[leg],
                                        intent="CLOSE")
        assert rec["ok"] is True, f"closing {leg} in order {order} failed: {rec.get('reason')}"

    assert adapter._account_net("QQQ") == 0, f"order {order} must still land flat"
    assert fake.positions["QQQ"] == 0
    for leg in order:
        assert adapter._state["broker_sent_positions"][leg]["qty"] == 0


# ── KILL flatten from a mixed book, through the real qqq_exec stack ────────────────

def _qqq_cfg(**overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 10}
    cfg["signal_source"] = "engine"
    cfg["max_shares_per_leg"] = 10
    cfg.update(overrides)
    return cfg


def test_kill_flatten_from_a_mixed_book_leaves_the_account_flat(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (510.0, "engine_cache"))

    adapter, fake = _adapter(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}, "_px_source": "test"}
    cfg = _qqq_cfg()
    qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    qe._open_lot(state, cfg, "ENGUQ", "long", 5, 700.0, 500.0, 0.0, log=NOOP)
    qe._open_lot(state, cfg, "NOISE", "short", 10, 700.0, 500.0, 0.0, log=NOOP)
    assert set(state["legs"]) == {"ORB", "ENGUQ", "NOISE"}
    assert adapter._account_net("QQQ") == 0

    qe._close_all(state, cfg, "KILL", quote_fn=None, ratio_fn=None, log=NOOP)

    assert state["legs"] == {}, "KILL must flatten every shadow lot"
    assert adapter._account_net("QQQ") == 0, "KILL must leave the broker account flat too"
    assert fake.positions["QQQ"] == 0


# ── a refused part (partial), and a resend that never re-sends the accepted part ──

def test_refused_part_is_partial_and_moves_belief_by_the_accepted_share_only(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    real_place = fake._place_order

    def flaky(account_id, orders):
        o = orders[0]
        if o["side"] == "SHORT" and o["quantity"] == "6":
            raise RuntimeError("simulated transient fault (not a Webull position rule)")
        return real_place(account_id, orders)

    fake.order_v3.place_order.side_effect = flaky

    adapter.place_stock_order(leg="ENGUQ", signal_id="e-open", symbol="QQQ", side="BUY",
                              qty=10, intent="OPEN")
    adapter.place_stock_order(leg="NOISE", signal_id="n-open", symbol="QQQ", side="SHORT",
                              qty=6, intent="OPEN")   # net_before=10, plain SELL 6, unaffected
    assert adapter._account_net("QQQ") == 4

    # ENGUQ closes 10: net_before=4 -> splits SELL 4 + SHORT 6, and the SHORT 6 leg is
    # the one wired to fail above.
    rec = adapter.place_stock_order(leg="ENGUQ", signal_id="e-close", symbol="QQQ",
                                    side="SELL", qty=10, intent="CLOSE")
    assert rec["ok"] is False
    assert rec["partial"] is True
    assert _part_sides(rec) == [("SELL", 4), ("SHORT", 6)]
    assert rec["parts"][0]["ok"] is True
    assert rec["parts"][1]["ok"] is False

    # only the accepted SELL 4 moved ENGUQ's own book (10 - 4 = 6 still believed open).
    assert adapter._state["broker_sent_positions"]["ENGUQ"]["qty"] == 6
    # the fake broker's OWN ground truth agrees: the failed SHORT 6 never touched it.
    assert fake.positions["QQQ"] == 0   # 10 (ENGUQ) - 6 (NOISE SELL) - 4 (ENGUQ SELL)

    accepted_ids = {o["client_order_id"] for o in fake.orders}

    # a same-signal_id "resend" is the existing idempotency cache -- returns the SAME
    # record, sends nothing new at all.
    calls_before = fake.order_v3.place_order.call_count
    replay = adapter.place_stock_order(leg="ENGUQ", signal_id="e-close", symbol="QQQ",
                                       side="SELL", qty=10, intent="CLOSE")
    assert replay["duplicate"] is True
    assert fake.order_v3.place_order.call_count == calls_before

    # the transient fault is gone by the time of the resend (that is what makes it
    # "transient" -- a permanent Webull refusal would not be worth resending at all).
    fake.order_v3.place_order.side_effect = real_place

    # a fresh-signal_id resend (qqq_exec's own convention after a queued retry) must
    # only go after the REMAINDER -- the nothing-to-close clamp reduces the requested
    # qty from 10 down to what ENGUQ's own book still shows open (6) -- and must never
    # reuse an already-accepted part's client_order_id.
    resend = adapter.place_stock_order(leg="ENGUQ", signal_id="e-close-R1", symbol="QQQ",
                                       side="SELL", qty=10, intent="CLOSE")
    assert resend["ok"] is True
    assert resend["qty"] == 6, "clamped to what was actually still open for this leg"
    assert _part_sides(resend) == [("SHORT", 6)], "net was 0 by now -- flat, so SHORT not SELL"
    resend_id = resend["parts"][0]["client_order_id"]
    assert resend_id not in accepted_ids, "a resend must never reuse an accepted part's id"

    assert adapter._state["broker_sent_positions"]["ENGUQ"]["qty"] == 0
    assert adapter._account_net("QQQ") == -6   # NOISE's 6-share short is all that remains
    assert fake.positions["QQQ"] == -6


# ── the nothing-to-close guard still blocks a leg whose own open never reached the
# broker -- unaffected by netting (regression guard) ───────────────────────────────

def test_nothing_to_close_still_blocks_a_leg_whose_open_failed(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    fake.order_v3.place_order.side_effect = RuntimeError("simulated: every order fails")

    r_open = adapter.place_stock_order(leg="ORB", signal_id="orb-open", symbol="QQQ",
                                       side="BUY", qty=5, intent="OPEN")
    assert r_open["ok"] is False
    assert adapter._state["broker_sent_positions"].get("ORB", {}).get("qty", 0) == 0

    r_close = adapter.place_stock_order(leg="ORB", signal_id="orb-close", symbol="QQQ",
                                        side="SELL", qty=5, intent="CLOSE")
    assert r_close["mode"] == "BLOCKED"
    assert r_close.get("nothing_to_close") is True
    assert "nothing to close" in r_close["reason"]


# ── fill-capture: quantity-weighted over the parts that filled ─────────────────────

def test_fill_capture_weights_price_by_qty_across_parts(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    out.mkdir()
    row = {c: "" for c in qe.BROKER_ORDER_COLS}
    row.update({"ts_et": "2026-09-24 14:10:00", "leg": "NOISE", "intent": "OPEN",
               "side": "SHORT", "shares": 20, "signal_id": "n-open",
               "client_order_id": "n-open", "mode": "PAPER", "ok": "True", "sent": "True",
               "shadow_px": 500.0, "duplicate": "False"})
    with open(out / "broker_orders.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        w.writerow(row)

    clock = [1_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])   # BEFORE queuing -- first_at
                                                              # must be stamped on this
                                                              # same fake clock, not the
                                                              # real wall clock.

    state = {}
    parts = [{"client_order_id": "n-open-1", "qty": 10, "ok": True},
             {"client_order_id": "n-open-2", "qty": 10, "ok": True}]
    qe._queue_broker_fill_capture(state, leg="NOISE", intent="OPEN", signal_id="n-open",
                                  account_id="ACCT1", shadow_px=500.0, parts=parts, log=NOOP)
    job = state["_broker_fill_capture"]["NOISE:OPEN"]
    assert len(job["parts"]) == 2

    prices = {"n-open-1": 100.0, "n-open-2": 102.0}

    def fake_query(adapter, coid, account_id=None, log=print):
        return prices[coid], None

    monkeypatch.setattr(qe, "_query_broker_fill", fake_query)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: object())

    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 0.1
    qe._maybe_capture_broker_fills(state, {}, None, True, log=NOOP)   # resolves part 1
    assert "NOISE:OPEN" in state["_broker_fill_capture"], "part 2 still outstanding"
    clock[0] += qe.BROKER_FILL_CAPTURE_RETRY_GAP_SEC + 0.1
    qe._maybe_capture_broker_fills(state, {}, None, True, log=NOOP)   # resolves part 2

    assert "NOISE:OPEN" not in state.get("_broker_fill_capture", {})
    with open(out / "broker_orders.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    # equal qty on both parts -> a plain average of 100.0 and 102.0.
    assert float(rows[-1]["broker_fill_px"]) == pytest.approx(101.0)


def test_fill_capture_single_part_job_is_unaffected_by_the_parts_plumbing(tmp_path, monkeypatch):
    """A job queued with parts=None (the ordinary, non-colliding case -- what every
    pre-existing caller/test does) must be serviced by the EXACT unchanged single-id
    path, never the new multi-part branch."""
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-1",
                                  account_id="A1", shadow_px=500.0, log=NOOP)
    job = state["_broker_fill_capture"]["ORB:OPEN"]
    assert "parts" not in job or not job.get("parts")

# -- a refused order still updates the status panel's last error (review fix) ----------

def test_a_refused_single_order_still_sets_last_error(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)

    def refuse(account_id, orders):
        raise RuntimeError("HTTP 417 OPENAPI_SOMETHING: refused for the test")

    fake.order_v3.place_order.side_effect = refuse
    rec = adapter.place_stock_order(leg="ORB", signal_id="o-open", symbol="QQQ",
                                    side="BUY", qty=10, intent="OPEN")
    assert rec["ok"] is False
    assert "refused for the test" in (rec.get("error") or "")
    assert "refused for the test" in (adapter._last_error or "")
    # nothing reached the broker, so nothing moved the book
    assert adapter._account_net("QQQ") == 0


def test_a_refused_part_of_a_split_sets_last_error(tmp_path, monkeypatch):
    adapter, fake = _adapter(tmp_path, monkeypatch)
    real_place = fake._place_order

    def flaky(account_id, orders):
        if orders[0]["side"] == "SHORT":
            raise RuntimeError("simulated refusal of the short half")
        return real_place(account_id, orders)

    adapter.place_stock_order(leg="ENGUQ", signal_id="e-open", symbol="QQQ", side="BUY",
                              qty=10, intent="OPEN")
    fake.order_v3.place_order.side_effect = flaky
    rec = adapter.place_stock_order(leg="NOISE", signal_id="n-open", symbol="QQQ",
                                    side="SHORT", qty=20, intent="OPEN")
    assert rec["partial"] is True
    assert "simulated refusal of the short half" in (adapter._last_error or "")
