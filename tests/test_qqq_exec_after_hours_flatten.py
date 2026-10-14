r"""AFTER-HOURS EOD FALLBACK (OWNER ORDER 2026-10-14 via MANAGER #155: "there's something called
POST MARKET!! ... I want NO more EOD issues") -- api/qqq_exec.py's _after_hours_flatten, the
adapter's extended_hours switch (api/webull_orders.py), and the EOD audit's two companions:
G3 (the next-open repair closes a SHORT orphan with a BUY) and G2 (a non-held lot still in the
book after the close is closed there, so its shares become an orphan the sweep sells).

Shares Webull still holds for a leg the shadow book has closed are sold AFTER HOURS with a
marketable LIMIT on the extended session (support_trading_session "ALL", DAY), re-priced every
45 s with a wider cushion until 20:00 New York; only if that fails too is the FLATTEN_BROKER
next-open repair armed. No MARKET order is ever sent after the bell.

Harness (tests/test_qqq_exec_flatten_orphan.py / tests/test_qqq_exec_dip_live.py, copied, not
imported): a REAL api.webull_orders.OrderAdapter in PAPER mode on tmp_path, whose SDK client is a
fake Webull account (FakeAccount) holding one QQQ position -- no SDK, no network, no credentials,
no real C:\EdgeLog path (every qqq_exec path is repointed at tmp_path, the trigger included).
"""
import csv
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from api import cloud_signal as cs
from api import ntfy_push
from api import qqq_exec as qe
from api import trade_id as T
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731

DAY = (2026, 10, 14)       # Wednesday, a full session (close 16:00)
DAY2 = (2026, 10, 15)      # Thursday
HALF = (2026, 11, 27)      # the day after Thanksgiving: close 13:00
HOLIDAY = (2026, 11, 26)   # Thanksgiving
SATURDAY = (2026, 10, 17)
REF = 600.13               # the session close the engine's bar cache reports


def at(day, h, m, s=0):
    return datetime(day[0], day[1], day[2], h, m, s)


def ds(day):
    return "%04d-%02d-%02d" % day


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeAccount:
    """One Webull margin account, QQQ only. Every order dict that reaches place_order is kept
    whole (`orders`). A MARKET order fills at once at `fill_px`; a LIMIT order works (SUBMITTED)
    until the test fills it (`fill`, whole or partial) or it is cancelled (CANCELLED, keeping
    what filled). `refuse` holds Webull codes the next sends are refused with (HTTP 417)."""

    def __init__(self, pos=0):
        self.pos = pos
        self.orders = []
        self.st = {}
        self.refuse = []
        self.fill_px = REF
        self.cancels = []
        self.details = []
        self.drop_answer = False    # the next send is placed but its answer never comes back
        self.detail_fail = 0        # this many order lookups raise (no answer)
        self.account_v2 = MagicMock()
        self.account_v2.get_account_list.return_value.json.return_value = {
            "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
        self.account_v2.get_account_position.side_effect = lambda acct: _Resp(
            {"data": ([{"symbol": "QQQ", "quantity": str(abs(self.pos)),
                        "side": "SHORT" if self.pos < 0 else "LONG"}] if self.pos else [])})
        self.order_v3 = MagicMock()
        self.order_v3.place_order.side_effect = self._place
        self.order_v3.get_order_detail.side_effect = self._detail
        self.order_v3.cancel_order.side_effect = self._cancel

    def _item(self, coid):
        r = self.st[coid]
        return {"client_order_id": coid, "status": r["status"], "filled_quantity": str(r["filled"]),
                "filled_price": f"{r['px']:.2f}" if r["px"] else "0"}

    def _place(self, account_id, orders):
        o = dict(orders[0])
        self.orders.append(o)
        if self.refuse:
            code = self.refuse.pop(0)
            raise RuntimeError(f"ServerException: HTTP Status: 417, Code: {code}, Msg: refused")
        coid = o["client_order_id"]
        self.st[coid] = {"status": "SUBMITTED", "qty": int(o["quantity"]), "filled": 0, "px": None,
                         "side": o["side"]}
        if o["order_type"] == "MARKET":
            self.fill(coid)
        if self.drop_answer:
            self.drop_answer = False
            raise RuntimeError("ConnectionResetError: the connection dropped before an answer")
        return _Resp({"client_order_id": coid, "orders": [self._item(coid)]})

    def fill(self, coid, qty=None, px=None):
        r = self.st[coid]
        n = (r["qty"] - r["filled"]) if qty is None else qty
        px = self.fill_px if px is None else px
        r["px"] = round(((r["px"] or 0.0) * r["filled"] + px * n) / (r["filled"] + n), 4)
        r["filled"] += n
        self.pos += n if r["side"] == "BUY" else -n
        r["status"] = "FILLED" if r["filled"] >= r["qty"] else "PARTIAL_FILLED"

    def _cancel(self, account_id, coid):
        self.cancels.append(coid)
        r = self.st.get(coid)
        if r and r["status"] in ("SUBMITTED", "PARTIAL_FILLED", "PENDING"):
            r["status"] = "CANCELLED"
        return _Resp({"client_order_id": coid})

    def _detail(self, account_id, coid):
        self.details.append(coid)
        if self.detail_fail:
            self.detail_fail -= 1
            raise RuntimeError("ReadTimeout: no answer")
        if coid not in self.st:
            raise RuntimeError("ServerException: HTTP Status: 404, Code: ORDER_NOT_FOUND")
        return _Resp({"client_order_id": coid, "orders": [self._item(coid)]})

    def limits(self):
        return [o for o in self.orders if o["order_type"] == "LIMIT"]


def _wo_cfg(tmp_path, mode="PAPER"):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["rails"]["max_shares_per_leg"] = 60
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _rows(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


class Env:
    """A temp qqq_exec home, a real PAPER adapter on FakeAccount, captured phone notes, the
    engine's session close stubbed at REF. `books(...)` puts shares in the adapter's books (and
    at Webull) for legs the shadow book has NO lot for -- the orphan the fallback sells."""

    def __init__(self, tmp_path, monkeypatch, mode="PAPER"):
        self.tmp, self.mp = tmp_path, monkeypatch
        out = tmp_path / "qqq_out"
        out.mkdir()
        self.out = out
        monkeypatch.setattr(qe, "OUT_DIR", str(out))
        for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                            ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                            ("BROKER_ORDERS_CSV", "broker_orders.csv"),
                            ("SERVING_LOCK", "SERVING.lock")):
            monkeypatch.setattr(qe, attr, str(out / fname))
        monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=str(tmp_path / "cs_home")))
        self.clock = [at(DAY, 16, 0)]
        monkeypatch.setattr(qe, "_now_et", lambda: self.clock[0])
        self.price = REF
        monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (self.price, "engine_cache"))
        monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (self.price, "engine_cache"))
        monkeypatch.setattr(qe, "_leg_timeframe_bar_close_age", lambda leg, log=print: 180.0)
        monkeypatch.setattr(qe, "_held_session_marks",
                            lambda leg, nowdt, log=print: {"prior_close": None, "today_open": None,
                                                           "today_last": None, "src": "test"})
        self.pushes = []
        monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                            self.pushes.append({"title": title, "message": msg,
                                                "priority": priority}) or True)
        self.wo_cfg = _wo_cfg(tmp_path, mode)
        with open(self.wo_cfg["paper_keys_path"], "w", encoding="utf-8") as f:
            json.dump({"app_key": "AK", "app_secret": "AS"}, f)
        self.fake = FakeAccount()
        self.new_adapter()
        self.cfg = json.loads(json.dumps(qe.DEFAULT_CONFIG))
        self.cfg.update(signal_source="engine", kill_file=str(out / "KILL"),
                        orb_resting={"mode": "off"}, slippage_per_share=0.0,
                        max_shares_per_leg=60, daily_loss_limit_usd=400)
        self.cfg["shares"].update({"ORB": 10, "ENGUQ": 10, "NOISE": 10})
        self.cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
        self.state = {"legs": {}, "events": []}
        self.lines = []
        qe._ah_call_state["future"] = None

    def log(self, *a, **k):
        self.lines.append(" ".join(str(x) for x in a))

    def new_adapter(self):
        self.adapter = WO.OrderAdapter(config=json.loads(json.dumps(self.wo_cfg)), log=NOOP)
        self.mp.setattr(self.adapter, "_build_client", lambda mode: self.fake)
        self.mp.setattr(qe, "_get_broker_adapter", lambda log=print: self.adapter)

    def books(self, **legs):
        """Shares the adapter's books hold for each leg (believed AND sent, as a real orphan's
        accepted OPEN leaves them) -- and Webull holds their sum."""
        for leg, qty in legs.items():
            self.adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
            self.adapter._state.setdefault("broker_sent_positions", {})[leg] = {
                "symbol": "QQQ", "qty": qty, "account_id": "ACCT1"}
            if qty:
                self.adapter._state.setdefault("open_legs", {})[leg] = True
        self.adapter._save_state()
        self.fake.pos = sum(int(p["qty"]) for p in self.adapter._state["broker_sent_positions"].values())

    def held(self, leg):
        q = qe._ah_books_qty(self.adapter.status(), leg)
        return q

    def ah(self, now):
        """One after-hours step, exactly as tick() calls it."""
        self.clock[0] = now
        qe._after_hours_flatten(self.state, self.cfg, now, log=self.log)
        return self.state

    def rec(self, leg, day=DAY):
        return self.state["after_hours_flatten"][ds(day)][leg]

    def rows(self):
        return _rows(qe.BROKER_ORDERS_CSV)

    def row(self, coid):
        (r,) = [r for r in self.rows() if r["signal_id"] == coid]
        return r

    def titled(self, title):
        return [p for p in self.pushes if p["title"] == title]

    def trigger(self):
        return self.out / "FLATTEN_BROKER"


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def _no_market_after_close(fake):
    """Every order that reached Webull in these tests went out after the bell: each one must be a
    LIMIT with a price on the extended session -- never a MARKET order."""
    for o in fake.orders:
        assert o["order_type"] == "LIMIT", o
        assert o["support_trading_session"] == "ALL", o
        assert o["time_in_force"] == "DAY", o
        assert float(o["limit_price"]) > 0, o


# ── 1. the first attempt ───────────────────────────────────────────────────────────────────────

def test_an_orb_long_left_at_webull_is_sold_after_hours_with_a_limit_on_the_extended_session(env):
    env.books(ORB=10)
    env.ah(at(DAY, 15, 59, 58))
    assert env.fake.orders == [], "nothing from this path before the session close"
    assert "after_hours_flatten" not in env.state

    env.ah(at(DAY, 16, 0, 5))
    (o,) = env.fake.orders
    assert o == {"combo_type": "NORMAL", "client_order_id": "qxAHORB20261014160005C",
                 "symbol": "QQQ", "instrument_type": "EQUITY", "market": "US",
                 "order_type": "LIMIT", "quantity": "10", "support_trading_session": "ALL",
                 "side": "SELL", "time_in_force": "DAY", "entrust_type": "QTY",
                 "limit_price": "597.12"}, "600.13 x 0.995 = 597.129 -> floored to the cent"
    assert len(o["client_order_id"]) <= 32
    rec = env.rec("ORB")
    assert (rec["status"], rec["attempts"], rec["coid"], rec["limit"], rec["side"], rec["qty"]) == (
        "working", 1, "qxAHORB20261014160005C", 597.12, "SELL", 10)
    assert rec["ref_px"] == REF and rec["ref_src"] == "session_close"
    # the adapter's own record says it is an extended-hours order
    wrec = env.adapter._state["orders"]["qxAHORB20261014160005C"]
    assert wrec["extended_hours"] is True and wrec["support_trading_session"] == "ALL"
    assert wrec["order_type"] == "LIMIT" and wrec["limit_price"] == 597.12
    row = env.row("qxAHORB20261014160005C")
    assert row["intent"] == "CLOSE" and row["side"] == "SELL" and row["shares"] == "10"
    assert row["ok"] == "True" and row["mode"] == "PAPER" and row["outcome"] == "OK"
    assert row["reason"].startswith("after-hours EOD fallback, attempt 1, limit 597.12")
    assert "support_trading_session ALL" in row["reason"]
    (note,) = env.titled("QQQ book: selling after hours")
    assert note["priority"] == "high" and ntfy_push.lint(note) == []
    assert "EOD exit missed: selling 10 QQQ after hours" in note["message"]
    assert any("after-hours" in ev["text"].lower() for ev in env.state["events"])
    _no_market_after_close(env.fake)


def test_the_window_opens_at_the_close_to_the_second(env):
    env.books(ORB=10)
    env.ah(at(DAY, 15, 59, 59))
    assert env.fake.orders == []
    env.ah(at(DAY, 16, 0, 0))
    assert len(env.fake.orders) == 1


# ── 2. re-price, then a fill ───────────────────────────────────────────────────────────────────

def test_not_filled_after_45s_is_cancelled_then_repriced_wider_and_a_fill_finishes_it(env):
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    first = "qxAHORB20261014160005C"
    for s in (15, 25, 35, 45):
        env.ah(at(DAY, 16, 0, s))
    assert env.fake.cancels == [] and len(env.fake.orders) == 1, "still inside its 45 s"
    assert env.fake.details, "a working order is read"

    env.ah(at(DAY, 16, 0, 50))                       # 45 s after the send
    assert env.fake.cancels == [first]
    assert env.rec("ORB")["status"] == "cancelling" and len(env.fake.orders) == 1, \
        "never a new order before Webull confirms the old one terminal"

    env.ah(at(DAY, 16, 0, 55))                       # CANCELLED confirmed -> attempt 2
    h = env.rec("ORB")["history"][0]
    assert (h["coid"], h["status"], h["filled"]) == (first, "CANCELLED", 0)
    assert env.fake.pos == 10, "nothing sold; the books took the 10 back and re-sent them"
    assert len(env.fake.orders) == 2
    second = env.fake.orders[1]
    assert second["client_order_id"] == "qxAHORB20261014160055C" != first
    assert second["limit_price"] == "594.12", "c = 1.0% on the re-price: 600.13 x 0.99 floored"
    rec = env.rec("ORB")
    assert (rec["attempts"], rec["reprices"], rec["cushion"]) == (2, 1, 0.01)
    r1 = env.row(first)
    assert (r1["outcome"], r1["shares"]) == ("CANCELLED", "0"), \
        "an unfilled attempt never pairs as a close in the realized P&L"

    env.fake.fill(second["client_order_id"], px=598.40)
    env.ah(at(DAY, 16, 1, 5))
    rec = env.rec("ORB")
    assert (rec["status"], rec["filled_qty"], rec["filled_px"]) == ("filled", 10, 598.4)
    assert env.held("ORB") == 0 and env.fake.pos == 0
    r2 = env.row(second["client_order_id"])
    assert r2["outcome"] == "FILLED" and float(r2["broker_fill_px"]) == 598.4
    assert float(r2["slippage"]) == round(598.40 - REF, 4)
    (note,) = env.titled("QQQ book: sold after hours")
    assert "Sold 10 QQQ after hours at $598.40" in note["message"]
    assert ntfy_push.lint(note) == []
    for s in range(10, 60, 5):
        env.ah(at(DAY, 16, 1, s))
    assert len(env.fake.orders) == 2, "nothing more once filled"
    _no_market_after_close(env.fake)


def test_an_immediate_fill_ends_the_leg_on_the_next_read(env):
    env.books(NOISE=5)
    env.ah(at(DAY, 16, 0, 5))
    env.fake.fill("qxAHNOISE20261014160005C", px=599.0)
    env.ah(at(DAY, 16, 0, 15))
    assert env.rec("NOISE")["status"] == "filled" and env.fake.cancels == []


# ── 3. a short leg buys back ───────────────────────────────────────────────────────────────────

def test_a_short_leg_buys_back_with_ref_x_1005_rounded_up(env):
    env.books(ORB=-10)
    env.ah(at(DAY, 16, 0, 5))
    (o,) = env.fake.orders
    assert (o["side"], o["quantity"], o["order_type"], o["support_trading_session"]) == (
        "BUY", "10", "LIMIT", "ALL")
    assert o["limit_price"] == "603.14", "600.13 x 1.005 = 603.1307 -> rounded UP"
    (note,) = env.titled("QQQ book: buying back after hours")
    assert "EOD exit missed: buying back 10 QQQ after hours" in note["message"]
    env.fake.fill(o["client_order_id"], px=601.0)
    env.ah(at(DAY, 16, 0, 15))
    assert env.rec("ORB")["status"] == "filled" and env.fake.pos == 0
    assert "Bought back 10 QQQ after hours at $601.00" in \
        env.titled("QQQ book: bought back after hours")[0]["message"]


# ── 4. one new order per tick ──────────────────────────────────────────────────────────────────

def test_two_orphan_legs_send_one_order_per_tick(env):
    env.books(ORB=10, NOISE=5)
    env.ah(at(DAY, 16, 0, 5))
    assert [(o["client_order_id"], o["quantity"]) for o in env.fake.orders] == [
        ("qxAHNOISE20261014160005C", "5")]
    env.ah(at(DAY, 16, 0, 10))
    assert [(o["client_order_id"], o["quantity"]) for o in env.fake.orders] == [
        ("qxAHNOISE20261014160005C", "5"), ("qxAHORB20261014160010C", "10")]
    env.ah(at(DAY, 16, 0, 15))
    assert len(env.fake.orders) == 2
    _no_market_after_close(env.fake)


def test_two_identical_orders_are_never_working_at_once(env):
    """Webull's duplicate rule compares the ORDER (side, quantity, price), not our id."""
    env.books(ORB=10, NOISE=10)
    env.ah(at(DAY, 16, 0, 5))
    env.ah(at(DAY, 16, 0, 10))
    assert len(env.fake.orders) == 1, "the second leg's SELL 10 @ 597.12 would be identical"
    env.fake.fill(env.fake.orders[0]["client_order_id"])
    env.ah(at(DAY, 16, 0, 15))
    assert len(env.fake.orders) == 2 and env.fake.orders[1]["client_order_id"].startswith("qxAHORB")


def test_dip_lots_carry_their_one_character_slot_code_in_the_id(env):
    env.books(DIP_STREAK=6)
    env.ah(at(DAY, 16, 0, 5))
    (o,) = env.fake.orders
    assert o["client_order_id"] == "qxAHDIPS20261014160005C" and o["quantity"] == "6"


# ── 5. a partial fill ──────────────────────────────────────────────────────────────────────────

def test_a_partial_fill_is_kept_working_then_only_the_remainder_is_resent(env):
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    first = "qxAHORB20261014160005C"
    env.fake.fill(first, qty=4, px=599.0)
    env.ah(at(DAY, 16, 0, 20))
    assert env.fake.cancels == [] and env.rec("ORB")["attempt_filled"] == 4, \
        "a partial fill keeps the order working until its re-price"
    env.ah(at(DAY, 16, 0, 50))
    assert env.fake.cancels == [first]
    env.ah(at(DAY, 16, 0, 55))
    assert env.fake.pos == 6 and env.rec("ORB")["history"][0]["filled"] == 4
    second = env.fake.orders[1]
    assert second["quantity"] == "6" and second["limit_price"] == "594.12"
    r1 = env.row(first)
    assert (r1["outcome"], r1["shares"], float(r1["broker_fill_px"])) == ("CANCELLED", "4", 599.0)
    env.fake.fill(second["client_order_id"], px=598.0)
    env.ah(at(DAY, 16, 1, 5))
    rec = env.rec("ORB")
    assert (rec["status"], rec["filled_qty"]) == ("filled", 10)
    assert rec["filled_px"] == round((4 * 599.0 + 6 * 598.0) / 10, 4)
    assert env.fake.pos == 0 and env.held("ORB") == 0


# ── 6. refusals -> give up -> next open ────────────────────────────────────────────────────────

def test_three_refusals_in_a_row_give_up_and_arm_the_next_open_repair(env):
    env.books(ORB=10)
    env.fake.refuse = ["OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET"] * 3
    assert "flatten_broker_file" not in env.cfg
    env.ah(at(DAY, 16, 0, 5))
    env.ah(at(DAY, 16, 0, 10))
    assert not env.trigger().exists()
    env.ah(at(DAY, 16, 0, 15))
    rec = env.rec("ORB")
    assert (rec["status"], rec["attempts"], rec["refusals"]) == ("gave_up", 3, 3)
    assert env.trigger().exists(), "the trigger resolved against the CURRENT OUT_DIR"
    assert rec["next_open_armed"] is True
    (note,) = env.titled("QQQ book: CHECK NOW")
    assert note["priority"] == "urgent" and ntfy_push.lint(note) == []
    assert "After-hours sell failed: 10 QQQ will sell at the 09:30 open" in note["message"]
    assert env.titled("QQQ book: selling after hours") == [], "nothing was ever accepted"
    for s in range(20, 60, 5):
        env.ah(at(DAY, 16, 0, s))
    assert len(env.fake.orders) == 3, "given up: nothing more today"
    assert [r["outcome"] for r in env.rows()] == ["REFUSED"] * 3
    assert env.held("ORB") == 10
    _no_market_after_close(env.fake)


def test_a_duplicate_refusal_waits_and_is_not_counted(env):
    env.books(ORB=10)
    env.fake.refuse = ["OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK"] * 3
    for s in (5, 10, 15):
        env.ah(at(DAY, 16, 0, s))
    assert env.rec("ORB")["refusals"] == 0 and env.rec("ORB")["status"] == "idle"
    env.ah(at(DAY, 16, 0, 20))
    assert env.rec("ORB")["status"] == "working"


# ── 7. the window's end ────────────────────────────────────────────────────────────────────────

def test_20_00_with_an_order_working_cancels_gives_up_and_arms_the_trigger(env):
    env.books(ORB=10)
    env.ah(at(DAY, 19, 59, 40))
    (o,) = env.fake.orders
    env.ah(at(DAY, 20, 0, 0))
    assert env.fake.cancels == [o["client_order_id"]], "cancelled at the window's end"
    env.ah(at(DAY, 20, 0, 5))
    rec = env.rec("ORB")
    assert rec["status"] == "gave_up" and env.trigger().exists()
    assert env.held("ORB") == 10, "the cancelled order is booked back"
    for m in (1, 30):
        env.ah(at(DAY, 20, m, 0))
    assert len(env.fake.orders) == 1, "nothing after 20:00"
    (note,) = env.titled("QQQ book: CHECK NOW")
    assert "will sell at the 09:30 open" in note["message"]


def test_shares_found_only_after_20_00_give_up_at_once_without_a_send(env):
    """The book was down all evening: nothing is sent past AH_END, the open repair is armed."""
    env.books(NOISE=10)
    env.ah(at(DAY, 20, 30, 0))
    assert env.fake.orders == [] and env.trigger().exists()
    assert env.rec("NOISE")["status"] == "gave_up"


def test_the_end_is_configurable(env):
    env.cfg["session"]["after_hours_end"] = "18:00"
    env.books(ORB=10)
    env.ah(at(DAY, 18, 0, 5))
    assert env.fake.orders == [] and env.rec("ORB")["status"] == "gave_up"


# ── 8. held lots are never touched ─────────────────────────────────────────────────────────────

def test_a_held_dip_lot_and_the_enguq_hold_are_never_targeted(env):
    env.books(DIP_RSI=6, ENGUQ=10)
    env.state["legs"] = {
        "DIP_RSI": {"leg": "DIP_RSI", "side": "long", "shares_remaining": 6,
                    "hold": {"since": ds(DAY)}},
        "ENGUQ": {"leg": "ENGUQ", "side": "long", "shares_remaining": 10,
                  "close_pending": {"reason": "KILL"}},
    }
    for s in (5, 10, 15):
        env.ah(at(DAY, 16, 0, s))
    env.ah(at(DAY, 20, 30, 0))
    assert env.fake.orders == [] and not env.trigger().exists()
    assert not (env.state.get("after_hours_flatten") or {}).get(ds(DAY))


def test_a_book_lot_beside_an_orphan_leaves_the_book_lot_alone(env):
    env.books(DIP_PB=6, ORB=10)
    env.state["legs"] = {"DIP_PB": {"leg": "DIP_PB", "side": "long", "shares_remaining": 6,
                                    "hold": {"since": ds(DAY)}}}
    env.ah(at(DAY, 16, 0, 5))
    (o,) = env.fake.orders
    assert o["client_order_id"].startswith("qxAHORB") and o["quantity"] == "10"


# ── 9. restart mid-loop ────────────────────────────────────────────────────────────────────────

def test_a_restart_mid_loop_reads_the_working_order_first_and_never_doubles(env):
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    qe.save_state(env.state)
    env.state = qe.load_state()
    env.new_adapter()                          # a fresh process: the adapter reloads its file
    details = len(env.fake.details)
    env.ah(at(DAY, 16, 0, 20))
    assert len(env.fake.orders) == 1, "the recorded working order is read, never re-sent"
    assert len(env.fake.details) == details + 1
    env.ah(at(DAY, 16, 0, 50))
    assert env.fake.cancels == ["qxAHORB20261014160005C"] and len(env.fake.orders) == 1
    env.ah(at(DAY, 16, 0, 55))
    assert len(env.fake.orders) == 2, "the next attempt only once the first is confirmed dead"


def test_an_unknown_send_the_state_never_saved_is_adopted_before_anything_is_sent(
        env, monkeypatch):
    """The send's answer never came back (a dropped connection, no lookup answered: the adapter
    keeps the part PENDING and the books still count the shares), and the process died before
    this tick's state was saved. The adapter cached the id before sending, so the order is found
    there and read first -- never a second order on top of one Webull may be working."""
    monkeypatch.setattr(WO, "_sleep", NOOP)
    env.books(ORB=10)
    env.fake.drop_answer = True               # placed at Webull, but the send raises
    env.fake.detail_fail = 3                  # and the adapter's own lookups get no answer
    env.ah(at(DAY, 16, 0, 5))
    assert len(env.fake.orders) == 1 and env.rec("ORB")["status"] == "unknown"
    assert env.held("ORB") == 10, "UNKNOWN: the books still count the shares"
    env.state = {"legs": {}, "events": []}     # the tick's state was never saved
    env.ah(at(DAY, 16, 0, 10))
    assert len(env.fake.orders) == 1, "never a second order on top of one Webull may hold"
    rec = env.rec("ORB")
    assert rec["coid"] == "qxAHORB20261014160005C" and rec["status"] == "unknown"
    env.ah(at(DAY, 16, 0, 15))
    assert env.rec("ORB")["status"] == "working" and len(env.fake.orders) == 1
    env.fake.fill("qxAHORB20261014160005C", px=599.5)
    env.ah(at(DAY, 16, 0, 30))
    assert env.rec("ORB")["status"] == "filled" and len(env.fake.orders) == 1
    assert env.held("ORB") == 0 and env.fake.pos == 0


def test_an_order_still_working_at_midnight_is_settled_the_next_morning(env):
    env.books(ORB=10)
    env.ah(at(DAY, 19, 59, 55))
    env.fake.st["qxAHORB20261014195955C"]["status"] = "EXPIRED"   # what Webull did at 20:00
    env.ah(at(DAY2, 8, 0, 0))                  # the box was down from 19:59:56
    assert env.rec("ORB")["status"] == "gave_up"
    assert env.held("ORB") == 10, "an expired order is booked back like a cancelled one"
    assert env.trigger().exists() and len(env.fake.orders) == 1


# ── 10. when it runs at all ────────────────────────────────────────────────────────────────────

def test_off_mode_sends_nothing(tmp_path, monkeypatch):
    e = Env(tmp_path, monkeypatch, mode="OFF")
    e.books(ORB=10)
    e.ah(at(DAY, 16, 0, 5))
    assert e.fake.orders == [] and "after_hours_flatten" not in e.state


@pytest.mark.parametrize("when", [at(SATURDAY, 16, 0, 5), at(HOLIDAY, 16, 0, 5)])
def test_weekends_and_holidays_send_nothing(env, when):
    env.books(ORB=10)
    env.ah(when)
    assert env.fake.orders == []


def test_a_half_day_starts_at_13_00_and_still_ends_at_20_00(env):
    env.books(ORB=10)
    env.ah(at(HALF, 12, 59, 58))
    assert env.fake.orders == []
    env.ah(at(HALF, 13, 0, 5))
    (o,) = env.fake.orders
    assert o["support_trading_session"] == "ALL" and o["client_order_id"] == "qxAHORB20261127130005C"
    assert qe._ah_end_dt(env.cfg, at(HALF, 13, 0, 5)) == at(HALF, 20, 0, 0)


def test_the_owner_switch_turns_it_off(env):
    env.cfg["after_hours_flatten"] = {"enabled": False}
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    assert env.fake.orders == []


# ── never guesses ──────────────────────────────────────────────────────────────────────────────

def test_a_reconcile_halt_sends_nothing_and_says_so_once(env):
    env.books(ORB=10)
    env.adapter._halted, env.adapter._halt_source = True, "reconcile"
    env.adapter._halt_reason = "reconcile mismatch vs Webull: QQQ broker=0 shadow_sent=10"
    for s in (5, 10, 15):
        env.ah(at(DAY, 16, 0, s))
    assert env.fake.orders == []
    (note,) = env.titled("QQQ book: CHECK NOW")
    assert note["priority"] == "high" and "on hold" in note["message"]
    assert env.state.get("_reconcile_due") is True, "asks for a fresh look"
    env.ah(at(DAY, 20, 30, 0))
    assert not env.trigger().exists(), "never sent and never agreed: no blind open order"


def test_webull_disagreeing_with_the_books_sends_nothing(env):
    env.books(ORB=10)
    env.fake.pos = 0                       # someone sold by hand
    env.ah(at(DAY, 16, 0, 5))
    assert env.fake.orders == [] and env.titled("QQQ book: CHECK NOW") == [], \
        "one disagreeing read may be a fill lag: no note yet"
    env.ah(at(DAY, 16, 0, 40))
    assert env.fake.orders == []
    assert len(env.titled("QQQ book: CHECK NOW")) == 1
    env.fake.pos = 10                      # it agrees again
    env.ah(at(DAY, 16, 1, 15))
    assert len(env.fake.orders) == 1


def test_shares_sold_by_hand_mid_loop_stop_the_loop_and_never_arm_a_blind_open_order(env):
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    env.fake.pos = 0                       # the owner sold by hand while our limit worked
    env.ah(at(DAY, 16, 0, 50))             # re-price due: cancelled
    env.ah(at(DAY, 16, 0, 55))             # confirmed; the books take the 10 back -- Webull: 0
    assert len(env.fake.orders) == 1, "Webull and the books disagree: nothing re-sent"
    env.ah(at(DAY, 16, 1, 30))
    assert len(env.fake.orders) == 1 and env.rec("ORB")["blocked_why"]
    env.ah(at(DAY, 20, 0, 0))
    rec = env.rec("ORB")
    assert rec["status"] == "gave_up" and rec["next_open_armed"] is False
    assert not env.trigger().exists(), "never a blind market order at the open"
    (note,) = [p for p in env.titled("QQQ book: CHECK NOW") if p["priority"] == "urgent"]
    assert "the book and Webull disagree on 10 QQQ" in note["message"]


def test_orphans_on_both_sides_are_crossed_in_the_books_with_no_order(env):
    env.books(ORB=10, NOISE=-10)           # Webull is flat: they offset
    env.ah(at(DAY, 16, 1, 0))
    assert env.fake.orders == []
    assert env.held("ORB") == 0 and env.held("NOISE") == 0
    netted = [r for r in env.rows() if r["outcome"] == "NETTED"]
    assert sorted(r["leg"] for r in netted) == ["NOISE", "ORB"]
    env.ah(at(DAY, 16, 1, 5))
    assert env.fake.orders == []
    assert {env.rec(l)["status"] for l in ("ORB", "NOISE")} == {"done"}


def test_the_lease_gate_blocks_the_send(env):
    env.books(ORB=10)
    env.state["_broker_lease_ok"] = False
    env.state["_broker_lease_reason"] = "host 'oracle' holds a fresh lease"
    env.ah(at(DAY, 16, 0, 5))
    assert env.fake.orders == []


def test_the_reconcile_waits_while_an_after_hours_order_works(env, monkeypatch):
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    calls = []
    monkeypatch.setattr(env.adapter, "reconcile", lambda *a, **k: calls.append(1) or {"ok": True})
    env.state["_last_broker_send_at"] = 0.0
    qe._maybe_run_broker_reconcile(env.state, env.cfg, env.adapter, at(DAY, 16, 0, 10), True,
                                   log=NOOP)
    assert calls == [], "its unfilled shares would read as a mismatch"
    env.fake.fill("qxAHORB20261014160005C")
    env.ah(at(DAY, 16, 0, 15))
    env.state["_last_broker_send_at"] = 0.0
    qe._maybe_run_broker_reconcile(env.state, env.cfg, env.adapter, at(DAY, 16, 0, 20), True,
                                   log=NOOP)
    assert calls == [1]


def test_the_after_close_webull_check_waits_for_the_sale_then_judges_again(env, monkeypatch):
    checks = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: checks.append(1) or (True, 0))
    env.books(ORB=10)
    env.state.update(flat_by_done_date=ds(DAY), _last_broker_send_at=0.0,
                     _eod_flat_checked_for={"date": ds(DAY), "flat_by": True, "kill": False})
    env.ah(at(DAY, 16, 0, 5))
    env.state.pop("_eod_flat_checked_for")
    qe._maybe_check_webull_flat_after_eod(env.state, env.cfg, at(DAY, 16, 0, 6), log=NOOP)
    assert checks == [], "no verdict (and no 'sell by hand') while it is still selling"
    env.state["_eod_flat_checked_for"] = {"date": ds(DAY), "flat_by": True, "kill": False}
    env.fake.fill("qxAHORB20261014160005C")
    env.ah(at(DAY, 16, 0, 15))
    assert "_eod_flat_checked_for" not in env.state, "ended flat: the day is judged again"
    qe._maybe_check_webull_flat_after_eod(env.state, env.cfg, at(DAY, 16, 0, 16), log=NOOP)
    assert checks == [1]


# ── 11. the adapter's extended_hours switch ────────────────────────────────────────────────────

def _adapter(tmp_path, monkeypatch):
    cfg = _wo_cfg(tmp_path)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    a = WO.OrderAdapter(config=cfg, log=NOOP)
    fake = FakeAccount()
    monkeypatch.setattr(a, "_build_client", lambda mode: fake)
    return a, fake


@pytest.mark.parametrize("kw", [
    {"order_type": "MARKET"},
    {"order_type": "MARKET", "limit_price": 600.0},
    {"order_type": "STOP_LOSS", "limit_price": 600.0},
    {"order_type": "LIMIT"},
    {"order_type": "LIMIT", "limit_price": 0},
    {"order_type": "LIMIT", "limit_price": -1.0},
    {"order_type": "LIMIT", "limit_price": "abc"},
    {"order_type": "LIMIT", "limit_price": float("nan")},
])
def test_extended_hours_without_a_valid_limit_is_a_value_error(tmp_path, monkeypatch, kw):
    a, fake = _adapter(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="extended_hours"):
        a.place_stock_order(leg="ORB", signal_id="qxAHORB20261014160005C", symbol="QQQ",
                            side="BUY", qty=10, intent="OPEN", extended_hours=True, **kw)
    assert fake.orders == [] and not a._state.get("orders"), "refused before anything is recorded"


def test_the_default_order_dict_is_still_core_byte_for_byte(tmp_path, monkeypatch):
    a, fake = _adapter(tmp_path, monkeypatch)
    rec = a.place_stock_order(leg="ORB", signal_id="qxORBR620261014T140000ZLO", symbol="QQQ",
                              side="BUY", qty=10, intent="OPEN")
    assert rec["ok"] is True
    assert fake.orders == [{"combo_type": "NORMAL", "client_order_id": "qxORBR620261014T140000ZLO",
                            "symbol": "QQQ", "instrument_type": "EQUITY", "market": "US",
                            "order_type": "MARKET", "quantity": "10",
                            "support_trading_session": "CORE", "side": "BUY",
                            "time_in_force": "DAY", "entrust_type": "QTY"}]
    assert "extended_hours" not in rec and "support_trading_session" not in rec
    # a regular-hours LIMIT keeps its old str() price and CORE
    a.place_stock_order(leg="NOISE", signal_id="lim1", symbol="QQQ", side="BUY", qty=1,
                        intent="OPEN", order_type="LIMIT", limit_price=599.5)
    assert fake.orders[1]["support_trading_session"] == "CORE"
    assert fake.orders[1]["limit_price"] == "599.5"


def test_an_extended_hours_limit_goes_out_as_all_with_a_cent_price(tmp_path, monkeypatch):
    a, fake = _adapter(tmp_path, monkeypatch)
    a.place_stock_order(leg="ORB", signal_id="qxORBR620261014T140000ZLO", symbol="QQQ",
                        side="BUY", qty=10, intent="OPEN")
    rec = a.place_stock_order(leg="ORB", signal_id="qxAHORB20261014160005C", symbol="QQQ",
                              side="SELL", qty=10, intent="CLOSE", order_type="LIMIT",
                              limit_price=597.1, tif="DAY", extended_hours=True)
    o = fake.orders[-1]
    assert o["support_trading_session"] == "ALL" and o["limit_price"] == "597.10"
    assert rec["extended_hours"] is True and rec["support_trading_session"] == "ALL"
    assert a._state["orders"]["qxAHORB20261014160005C"]["support_trading_session"] == "ALL"


def test_preview_takes_the_same_switch(tmp_path, monkeypatch):
    a, fake = _adapter(tmp_path, monkeypatch)
    fake.order_v3.preview_order.return_value.json.return_value = {"ok": 1}
    a.preview_stock_order(symbol="QQQ", side="SELL", qty=10)
    assert fake.order_v3.preview_order.call_args[0][1][0]["support_trading_session"] == "CORE"
    a.preview_stock_order(symbol="QQQ", side="SELL", qty=10, order_type="LIMIT",
                          limit_price=597.12, extended_hours=True)
    o = fake.order_v3.preview_order.call_args[0][1][0]
    assert o["support_trading_session"] == "ALL" and o["limit_price"] == "597.12"
    with pytest.raises(ValueError):
        a.preview_stock_order(symbol="QQQ", side="SELL", qty=10, extended_hours=True)


# ── 12. the after-close guard is unchanged ─────────────────────────────────────────────────────

def test_the_after_close_guard_still_refuses_a_market_close_at_16_00_01(env):
    env.books(ORB=10)
    tid = T.make("ORB_R6", "2026-10-14T14:00:00-04:00", "long")
    qe._mirror_to_broker(env.state, leg="ORB", side="long", shares=10, shadow_px=REF,
                         intent="CLOSE", trade_id=tid, nowdt=at(DAY, 16, 0, 1), log=NOOP)
    assert env.fake.orders == [], "no MARKET order after the bell, ever"
    (row,) = env.rows()
    assert row["mode"] == "BLOCKED" and "market closed" in row["reason"]
    assert env.held("ORB") == 10
    env.ah(at(DAY, 16, 0, 5))                 # ... and the fallback takes the shares instead
    _no_market_after_close(env.fake)
    assert len(env.fake.orders) == 1


# ── G3: the next-open repair closes a SHORT orphan ─────────────────────────────────────────────

def _repair_cfg(env):
    cfg = dict(env.cfg)
    cfg.pop("flatten_broker_file", None)
    return cfg


def test_the_open_repair_buys_back_a_short_orphan(env):
    env.books(ORB=-10)
    env.trigger().write_text("flatten\n", encoding="utf-8")
    env.clock[0] = at(DAY2, 9, 31)
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31))
    (o,) = env.fake.orders
    assert (o["side"], o["quantity"], o["order_type"], o["support_trading_session"]) == (
        "BUY", "10", "MARKET", "CORE")
    assert env.held("ORB") == 0 and env.fake.pos == 0


def test_the_open_repair_still_sells_a_long_orphan(env):
    env.books(NOISE=10)
    env.trigger().write_text("flatten\n", encoding="utf-8")
    env.clock[0] = at(DAY2, 9, 31)
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31))
    (o,) = env.fake.orders
    assert (o["side"], o["quantity"]) == ("SELL", "10")


def test_a_failed_after_hours_buy_back_is_bought_back_at_the_next_open(env):
    env.books(ORB=-10)
    env.fake.refuse = ["OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET"] * 3
    for s in (0, 5, 10):
        env.ah(at(DAY, 16, 0, s))
    assert env.rec("ORB")["status"] == "gave_up" and env.trigger().exists()
    assert [o["side"] for o in env.fake.orders] == ["BUY"] * 3
    _no_market_after_close(env.fake)
    env.clock[0] = at(DAY2, 9, 31)
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31))
    assert [(o["side"], o["quantity"], o["order_type"]) for o in env.fake.orders[3:]] == [
        ("BUY", "10", "MARKET")]
    assert env.held("ORB") == 0 and env.fake.pos == 0


# ── G2: a non-held lot still in the book after the close ───────────────────────────────────────

def _orb_entry(day, hh, mm, side, px):
    ref = f"{ds(day)}T{hh:02d}:{mm:02d}:00-04:00"
    return {"leg": "ORB_R6", "event": "ENTRY", "side": side, "ref_time": ref, "ref_price": px,
            "bar_source": "webull", "trade_id": T.make("ORB_R6", ref, side), "size": "",
            "keel_size": "", "reason": ""}


def _dip_entry(slot, day, px):
    ref = f"{ds(day)}T09:30:00-04:00"
    return {"leg": "DIP_424", "event": "ENTRY", "side": "long", "ref_time": ref, "ref_price": px,
            "bar_source": "webull", "trade_id": T.make("DIP_424", ref, "long", slot=slot),
            "size": "1.0", "keel_size": "", "reason": f"slot={slot}"}


class TickEnv(Env):
    """Env driven through api/qqq_exec.tick, the engine consumer stubbed to hand rows over."""

    def __init__(self, tmp_path, monkeypatch):
        super().__init__(tmp_path, monkeypatch)
        self.events = []
        monkeypatch.setattr(qe, "_check_feed_engine", lambda state, log=print: False)
        monkeypatch.setattr(qe, "_consume_engine_signals",
                            lambda state, cfg, now, log=print: self.events.pop(0) if self.events else [])
        for name in ("_maybe_run_reprice", "_maybe_read_account_equity",
                     "_maybe_capture_broker_fills", "_maybe_send_eod_summary"):
            monkeypatch.setattr(qe, name, NOOP)
        monkeypatch.setattr(qe, "_maybe_note_eod_gave_up", lambda *a, **k: False)
        monkeypatch.setattr(qe, "_build_doc", lambda cfg, state, fs, unrl, log=print: {})
        qe._BREAKER_ADJ_CACHE["key"] = None

    def tick(self, now, events=None):
        self.clock[0] = now
        if events:
            self.events.append(events)
        qe._BREAKER_ADJ_CACHE["key"] = None
        _cfg, self.state, _doc = qe.tick(cfg=self.cfg, state=self.state, now=now, log=self.log)
        return self.state

    def trades(self):
        return _rows(qe.TRADES_CSV)


@pytest.fixture
def tenv(tmp_path, monkeypatch):
    return TickEnv(tmp_path, monkeypatch)


def _open_orb_and_dip(e):
    e.tick(at(DAY, 9, 35, 10), events=[_dip_entry("RSI", DAY, REF)])
    e.tick(at(DAY, 10, 5, 5), events=[_orb_entry(DAY, 10, 0, "long", REF)])
    assert set(e.state["legs"]) == {"DIP_RSI", "ORB"} and e.fake.pos == 16
    market_orders = len(e.fake.orders)
    assert all(o["order_type"] == "MARKET" for o in e.fake.orders)
    return market_orders


def test_an_orb_lot_still_in_the_book_at_16_03_is_closed_eod_and_sold_after_hours(tenv):
    e = tenv
    before = _open_orb_and_dip(e)
    # the flatten "ran" at 15:59 but ORB was still in the book (a stalled tick, an unpriced lot)
    e.state["flat_by_done_date"] = ds(DAY)
    e.tick(at(DAY, 16, 3, 0))
    assert "ORB" not in e.state["legs"], "closed in the book after the close"
    (trade,) = [t for t in e.trades() if t["leg"] == "ORB"]
    assert trade["exit_reason"].startswith("EOD") and "engine_cache" in trade["exit_reason"]
    assert "DIP_RSI" in e.state["legs"], "the held DIP lot is untouched"
    after = e.fake.orders[before:]
    assert all(o["order_type"] == "LIMIT" for o in after), "no MARKET order after the bell"
    blocked = [r for r in e.rows() if r["leg"] == "ORB" and r["mode"] == "BLOCKED"]
    assert blocked and "market closed" in blocked[0]["reason"]
    e.tick(at(DAY, 16, 3, 5))
    after = e.fake.orders[before:]
    assert [(o["side"], o["quantity"], o["order_type"], o["support_trading_session"])
            for o in after] == [("SELL", "10", "LIMIT", "ALL")]
    assert after[0]["client_order_id"].startswith("qxAHORB")


def test_a_book_down_across_the_close_closes_orb_at_16_10_and_leaves_dip_held(tenv):
    """Back at 16:10 -- past the loop's 16:05 active window, so the flat_by block never ran."""
    e = tenv
    before = _open_orb_and_dip(e)
    assert e.state.get("flat_by_done_date") != ds(DAY)
    e.tick(at(DAY, 16, 10, 0))
    assert "ORB" not in e.state["legs"] and "DIP_RSI" in e.state["legs"]
    dip = e.state["legs"]["DIP_RSI"]
    assert dip.get("close_pending") is None and dip["shares_remaining"] == 6
    assert "hold" not in dip, "untouched: adopted as held the next morning (_adopt_missed_holds)"
    assert e.state.get("flat_by_done_date") != ds(DAY),         "not stamped while an unmarked hold-leg lot is open -- the after-close check would misread it"
    (trade,) = [t for t in e.trades() if t["leg"] == "ORB"]
    assert trade["exit_reason"].startswith("EOD")
    e.tick(at(DAY, 16, 10, 5))
    after = e.fake.orders[before:]
    assert [(o["side"], o["quantity"], o["support_trading_session"]) for o in after] == [
        ("SELL", "10", "ALL")]
    assert not any(o["client_order_id"].startswith("qxAHDIP") for o in e.fake.orders)
    e.fake.fill(after[0]["client_order_id"], px=600.0)
    e.tick(at(DAY, 16, 10, 20))
    assert e.fake.pos == 6, "ORB sold after hours; DIP's 6 held overnight"
    assert e.state["after_hours_flatten"][ds(DAY)]["ORB"]["status"] == "filled"
    assert not [p for p in e.pushes if "Webull still holds" in p["message"]],         "DIP's held shares are never read as left-over shares"


def test_a_held_dip_lot_alone_at_16_03_is_untouched(tenv):
    e = tenv
    e.tick(at(DAY, 9, 35, 10), events=[_dip_entry("PB", DAY, REF)])
    n = len(e.fake.orders)
    e.tick(at(DAY, 16, 3, 0))
    e.tick(at(DAY, 16, 3, 5))
    assert "DIP_PB" in e.state["legs"] and len(e.fake.orders) == n
    assert not (e.state.get("after_hours_flatten") or {}).get(ds(DAY))
