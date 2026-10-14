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
from datetime import datetime, timedelta
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
        # a fresh process: its first after-hours step runs the restart recovery scan once
        monkeypatch.setitem(qe._PROCESS, "ah_boot_scan", False)
        monkeypatch.setitem(qe._AH_SETTLED_TICK, "key", None)
        monkeypatch.setattr(qe, "_PHONE_PROCESS_STORE", {})

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

    def closed_by_book(self, *legs, day=DAY):
        """The book's own record that IT closed these legs on `day` (what _reduce_lot writes) --
        a hold leg's shares are sold after hours / at the next open only on it."""
        for leg in legs:
            self.state.setdefault("_book_closes", {})[leg] = {
                "day": ds(day), "at_et": f"{ds(day)} 15:59:00", "reason": "EOD"}

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
    env.closed_by_book("DIP_STREAK")          # a KILL / breaker close the book made today
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
    """Review of 1fdde9fb, item 6: refused tries are spaced 45 s apart -- three refusals take at
    least 90 s, never a whole evening given up in 15."""
    env.books(ORB=10)
    env.fake.refuse = ["OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET"] * 3
    assert "flatten_broker_file" not in env.cfg
    env.ah(at(DAY, 16, 0, 5))
    for s in (10, 15, 20, 25, 30, 35, 40, 45):
        env.ah(at(DAY, 16, 0, s))
    assert len(env.fake.orders) == 1, "no retry sooner than 45 s after the refusal at 16:00:05"
    env.ah(at(DAY, 16, 0, 50))
    assert len(env.fake.orders) == 2, "the retry at 16:00:50"
    env.ah(at(DAY, 16, 1, 30))
    assert len(env.fake.orders) == 2 and not env.trigger().exists()
    env.ah(at(DAY, 16, 1, 35))
    rec = env.rec("ORB")
    assert (rec["status"], rec["attempts"], rec["refusals"]) == ("gave_up", 3, 3)
    assert env.trigger().exists(), "the trigger resolved against the CURRENT OUT_DIR"
    assert rec["next_open_armed"] is True
    (note,) = env.titled("QQQ book: CHECK NOW")
    assert note["priority"] == "urgent" and ntfy_push.lint(note) == []
    assert "After-hours sell failed: 10 QQQ will sell at the 09:30 open" in note["message"]
    assert env.titled("QQQ book: selling after hours") == [], "nothing was ever accepted"
    for s in range(40, 60, 5):
        env.ah(at(DAY, 16, 1, s))
    env.ah(at(DAY, 16, 5, 0))
    assert len(env.fake.orders) == 3, "given up: nothing more today"
    assert [r["outcome"] for r in env.rows()] == ["REFUSED"] * 3
    assert env.held("ORB") == 10
    _no_market_after_close(env.fake)


def test_a_duplicate_refusal_waits_and_is_not_counted(env):
    env.books(ORB=10)
    env.fake.refuse = ["OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK"] * 3
    for t in (at(DAY, 16, 0, 5), at(DAY, 16, 0, 50), at(DAY, 16, 1, 35)):
        env.ah(t)
    assert len(env.fake.orders) == 3
    assert env.rec("ORB")["refusals"] == 0 and env.rec("ORB")["status"] == "idle"
    env.ah(at(DAY, 16, 2, 20))
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


def test_a_half_day_starts_at_13_00_and_ends_at_17_00(env):
    """Review of 1fdde9fb: Webull's post-market ends 4 h after the close -- the window ends at
    min(after_hours_end, close + 4 h), 17:00 on the 13:00 close of 2026-11-27."""
    env.books(ORB=10)
    env.ah(at(HALF, 12, 59, 58))
    assert env.fake.orders == []
    env.ah(at(HALF, 13, 0, 5))
    (o,) = env.fake.orders
    assert o["support_trading_session"] == "ALL" and o["client_order_id"] == "qxAHORB20261127130005C"
    assert qe._ah_end_dt(env.cfg, at(HALF, 13, 0, 5)) == at(HALF, 17, 0, 0)
    assert qe._ah_end_dt(env.cfg, at(DAY, 16, 0, 5)) == at(DAY, 20, 0, 0), "a full day: 20:00"
    env.cfg["session"]["after_hours_end"] = "16:30"
    assert qe._ah_end_dt(env.cfg, at(HALF, 13, 0, 5)) == at(HALF, 16, 30, 0), "the earlier wins"
    env.cfg["session"].pop("after_hours_end")
    env.ah(at(HALF, 17, 0, 0))
    assert env.fake.cancels == [o["client_order_id"]], "cancelled at 17:00"
    env.ah(at(HALF, 17, 0, 5))
    assert env.rec("ORB", day=HALF)["status"] == "gave_up" and env.trigger().exists()


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
    assert checks == [], "review item 2: not in the same tick -- after the post-order grace"
    qe._maybe_check_webull_flat_after_eod(env.state, env.cfg, at(DAY, 16, 0, 45), log=NOOP)
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
    for t in (at(DAY, 16, 0, 0), at(DAY, 16, 0, 45), at(DAY, 16, 1, 30)):
        env.ah(t)
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


# ══ REVIEW OF 1fdde9fb (independent adversarial review, 2026-10-14) ═════════════════════════════
# The reviewer's scenario tests (S1-S8) are reused below with the behaviour they now pin.

def _open_row(leg, side, qty, px, coid):
    """broker_orders.csv's OPEN row for a leg (what _mirror_to_broker writes at the entry)."""
    qe._append_csv(qe.BROKER_ORDERS_CSV, qe.BROKER_ORDER_COLS, {
        "ts_et": f"{ds(DAY)} 10:00:05", "leg": leg, "intent": "OPEN", "side": side,
        "shares": qty, "signal_id": coid, "client_order_id": coid, "mode": "PAPER", "ok": True,
        "sent": True, "shadow_px": px, "broker_fill_px": px, "slippage": 0.0, "reason": "",
        "duplicate": False, "host_id": "test", "outcome": "OK"}, qe.BROKER_ORDERS_KEEP)


# ── BLOCKER 1: a held lot the book lost is never sold ──────────────────────────────────────────

@pytest.mark.parametrize("leg,qty", [("DIP_PB", 12), ("ENGUQ", 10)])
def test_review_b1_a_held_lot_lost_with_state_json_is_never_sold_after_hours_or_at_the_open(
        env, monkeypatch, leg, qty):
    """S3: state.json was missing / unreadable at a restart, so the book starts empty while the
    adapter (and Webull) still hold a HOLD leg's lot. Nothing is sent at 16:00 (or at 20:00),
    nothing at 09:31 even with the FLATTEN_BROKER trigger dropped, and the existing urgent boot
    alert still fires."""
    env.books(**{leg: qty})
    env.state = qe._default_state()                    # what load_state hands back
    monkeypatch.setattr(env.adapter, "reconcile", lambda *a, **k: {"ok": True})
    qe._reconcile_broker_at_boot(log=env.log)
    (boot,) = [p for p in env.pushes if "may stay open" in p["title"] + p["message"]]
    assert boot["priority"] == "urgent", "the existing boot alert still fires"
    for t in (at(DAY, 16, 0, 0), at(DAY, 16, 0, 5), at(DAY, 16, 1, 0), at(DAY, 20, 30, 0)):
        env.ah(t)
    assert env.fake.orders == [] and not env.trigger().exists()
    assert not (env.state.get("after_hours_flatten") or {}).get(ds(DAY))
    assert any("never sold after hours" in ev["text"] for ev in env.state["events"])
    env.trigger().write_text("flatten\n", encoding="utf-8")      # dropped by hand
    env.clock[0] = at(DAY2, 9, 31)
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31), log=env.log)
    assert env.fake.orders == [], "the next-open repair never sells a held lot blind either"
    assert env.held(leg) == qty and env.fake.pos == qty
    assert any("never sold blind" in ev["text"] for ev in env.state["events"])


def test_review_b1_a_hold_leg_the_book_closed_yesterday_is_repaired_at_the_open(env):
    """The other side of BLOCKER 1: the book's own record that it closed the hold leg (a KILL /
    breaker close yesterday whose sell never reached Webull) lets the repair sell it."""
    env.books(ENGUQ=10)
    env.closed_by_book("ENGUQ", day=DAY)
    env.trigger().write_text("flatten\n", encoding="utf-8")
    env.clock[0] = at(DAY2, 9, 31)
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31), log=env.log)
    (o,) = env.fake.orders
    assert (o["side"], o["quantity"], o["order_type"]) == ("SELL", "10", "MARKET")


def test_review_b1_the_book_records_its_own_closes(env):
    """_reduce_lot's full close writes the record the hold rule reads."""
    qe._note_book_close(env.state, "DIP_PB", at(DAY, 15, 59, 0), "KILL")
    assert env.state["_book_closes"]["DIP_PB"]["day"] == ds(DAY)
    assert qe._book_closed_on(env.state, "DIP_PB", [ds(DAY)])
    assert not qe._book_closed_on(env.state, "DIP_PB", [ds(DAY2)])


def test_review_s2_a_held_short_beside_a_long_orphan_never_shorts(env):
    env.books(ENGUQ=-10, NOISE=5)
    env.state["legs"] = {"ENGUQ": {"leg": "ENGUQ", "side": "short", "shares_remaining": 10,
                                   "hold": {"since": ds(DAY)}}}
    env.ah(at(DAY, 16, 0, 5))
    assert env.fake.orders == []
    assert env.rec("NOISE")["status"] == "gave_up" and env.trigger().exists()


def test_review_s1_a_short_legs_buy_back_on_an_account_a_held_lot_keeps_long_waits_for_the_open(
        env):
    """S1, changed on purpose by the adapter backstop (review item: only a single-order REDUCE of
    the account's position goes out after hours): held DIP 12 long + an ORB -10 orphan leave the
    account +2 -- the BUY 10 would INCREASE the account's long position, so it is not sent after
    hours; the open repair buys it back."""
    env.books(DIP_PB=12, ORB=-10)
    env.state["legs"] = {"DIP_PB": {"leg": "DIP_PB", "side": "long", "shares_remaining": 12,
                                    "hold": {"since": ds(DAY)}}}
    env.ah(at(DAY, 16, 0, 5))
    assert env.fake.orders == []
    rec = env.rec("ORB")
    assert rec["status"] == "gave_up" and "increase" in rec["why"] and env.trigger().exists()
    (note,) = env.titled("QQQ book: CHECK NOW")
    assert "will be bought back at the 09:30 open" in note["message"]


# ── item 2: one story on the phone ────────────────────────────────────────────────────────────

def test_review_2_a_close_refused_to_the_deadline_never_says_by_hand(tenv):
    """15:59:00 -> 16:00:30 through tick(): ORB's end-of-day sell is refused until the re-send
    gives up at the 15:59:50 deadline. No push says "by hand", exactly one "selling after hours"
    note goes out, and the after-close Webull check waits for the after-hours run -- then judges
    the day 30 s after its fill."""
    e = tenv
    e.tick(at(DAY, 10, 5, 5), events=[_orb_entry(DAY, 10, 0, "long", REF)])
    n0 = len(e.fake.orders)
    e.fake.refuse = ["OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET"] * 500
    t = at(DAY, 15, 59, 0)
    while t <= at(DAY, 16, 0, 30):
        if t >= at(DAY, 15, 59, 55):
            e.fake.refuse = []                  # Webull takes the after-hours limit
        e.tick(t)
        t += timedelta(seconds=5)
    regular = [o for o in e.fake.orders[n0:] if o["order_type"] == "MARKET"]
    assert regular and all(o["side"] == "SELL" for o in regular), "refused to the deadline"
    (ah,) = e.fake.limits()
    assert (ah["side"], ah["quantity"], ah["support_trading_session"]) == ("SELL", "10", "ALL")
    assert not [p for p in e.pushes if "by hand" in p["message"]], \
        [p["message"] for p in e.pushes if "by hand" in p["message"]]
    assert len(e.titled("QQQ book: selling after hours")) == 1
    assert "_webull_flat_after_eod" not in e.state, "no verdict while the after-hours sell works"
    e.fake.fill(ah["client_order_id"], px=599.0)
    while t <= at(DAY, 16, 1, 30):
        e.tick(t)
        t += timedelta(seconds=5)
    assert e.state["after_hours_flatten"][ds(DAY)]["ORB"]["status"] == "filled"
    assert e.state["_webull_flat_after_eod"]["flat"] is True
    assert not [p for p in e.pushes if p["priority"] == "urgent"]


def test_review_2_the_after_bell_note_says_the_after_hours_sell_takes_it(env):
    env.books(ORB=10)
    qe._alert_close_blocked_after_close(env.state, "ORB", at(DAY, 16, 0, 1), log=env.log)
    (note,) = env.pushes
    assert "by hand" not in note["message"] and "leave QQQ alone" in note["message"]
    assert note["priority"] == "high" and ntfy_push.lint(note) == []
    # with the owner's switch off the old wording stands
    env.state["_ah_cfg"] = {"enabled": False}
    env.state.pop("_after_close_blocked_alerted", None)
    env.state.pop("_phone_dedupe", None)
    qe._alert_close_blocked_after_close(env.state, "ORB", at(DAY, 16, 0, 2), log=env.log)
    assert "by hand" in env.pushes[-1]["message"] and env.pushes[-1]["priority"] == "urgent"


def test_review_2_a_mid_day_stuck_exit_still_says_sell_by_hand(env):
    """Hours before the after-hours window, the urgent "sell by hand" is unchanged."""
    env.books(ORB=10)
    qe._say_exit_stuck(env.state, "ORB", "The ORB sell is stuck", log=env.log,
                       nowdt=at(DAY, 11, 0, 0), cfg=env.cfg)
    assert "by hand" in env.pushes[-1]["message"] and env.pushes[-1]["priority"] == "urgent"


# ── item 3: never on top of an unsettled regular close ───────────────────────────────────────

def _pending_close(env, coid="qxORBR620261014T140000ZLC", leg="ORB"):
    import time as _t
    env.adapter._state.setdefault("order_parts", {})[coid] = {
        "leg": leg, "symbol": "QQQ", "side": "SELL", "qty": 10, "intent": "CLOSE",
        "account_id": "ACCT1", "ts": _t.time(), "booked": 0, "pending": True}
    env.adapter._save_state()
    return coid


@pytest.mark.parametrize("outcome,sent_after", [("CANCELLED", 1), ("FILLED", 0)])
def test_review_3_a_pending_regular_close_holds_the_after_hours_sell_until_it_settles(
        env, outcome, sent_after):
    """S7: an UNKNOWN regular close of ORB (a pending part) at 16:00 -- nothing is sent until it
    settles: dead -> the after-hours sell goes; filled -> nothing is left to sell."""
    env.books(ORB=10)
    coid = _pending_close(env)
    for s in (0, 5, 30):
        env.ah(at(DAY, 16, 0, s))
    assert env.fake.orders == [], "never on top of a close whose outcome is unknown"
    assert any("waits" in ev["text"] and coid in ev["text"] for ev in env.state["events"])
    env.adapter.apply_order_outcome(coid, outcome, 10 if outcome == "FILLED" else 0)
    if outcome == "FILLED":
        env.fake.pos = 0
    env.ah(at(DAY, 16, 0, 35))
    assert len(env.fake.orders) == sent_after


def test_review_3_the_after_hours_sell_waits_30s_after_the_legs_last_regular_send(env):
    env.books(ORB=10)
    qe._ah_note_regular_send(env.state, "ORB", at(DAY, 15, 59, 55))
    for s in (0, 5, 20):
        env.ah(at(DAY, 16, 0, s))
    assert env.fake.orders == []
    env.ah(at(DAY, 16, 0, 25))
    assert len(env.fake.orders) == 1


def test_review_3_a_regular_send_is_stamped_on_the_ticks_clock(env):
    env.books(ORB=10)
    tid = T.make("ORB_R6", "2026-10-14T14:00:00-04:00", "long")
    qe._mirror_to_broker(env.state, leg="ORB", side="long", shares=10, shadow_px=REF,
                         intent="CLOSE", trade_id=tid, nowdt=at(DAY, 15, 59, 30), log=NOOP)
    assert env.state["_broker_send_e"]["ORB"] == qe._ah_epoch(at(DAY, 15, 59, 30))


# ── item 4: never a blind open order on an unknown outcome ───────────────────────────────────

def _unknown_fill_then_silence(env, monkeypatch, when=at(DAY, 19, 59, 55)):
    """S8: the limit went out with no answer, it DID fill at Webull, and no read ever says so."""
    monkeypatch.setattr(WO, "_sleep", NOOP)
    env.books(ORB=10)
    env.fake.drop_answer = True
    env.fake.detail_fail = 10 ** 6
    env.ah(when)
    coid = env.rec("ORB")["coid"]
    env.fake.fill(coid)
    return coid


def test_review_4_an_unconfirmed_fill_never_arms_a_blind_open_order(env, monkeypatch):
    coid = _unknown_fill_then_silence(env, monkeypatch)
    t = at(DAY, 20, 0, 0)
    while t <= at(DAY, 20, 31, 0):
        env.ah(t)
        t += timedelta(seconds=15)
    rec = env.rec("ORB")
    assert rec["status"] == "gave_up" and rec["unresolved_coid"] == coid
    assert rec["next_open_armed"] is False and rec["next_open_allowed"] is False
    assert not env.trigger().exists()
    (note,) = [p for p in env.pushes if p["priority"] == "urgent"]
    assert "unconfirmed" in note["message"] and ntfy_push.lint(note) == []
    # even a trigger dropped by hand sells nothing: the record is unsettled, and Webull (0)
    # disagrees with the books (10)
    env.trigger().write_text("flatten\n", encoding="utf-8")
    env.clock[0] = at(DAY2, 9, 31)
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31), log=env.log)
    assert [o["order_type"] for o in env.fake.orders] == ["LIMIT"], "no MARKET SELL at the open"
    assert env.fake.pos == 0, "never short"


def test_review_4_the_repair_checks_webull_before_every_send(env):
    env.books(NOISE=10)
    env.fake.pos = 0                                  # sold by hand (or by our limit) overnight
    env.trigger().write_text("flatten\n", encoding="utf-8")
    env.clock[0] = at(DAY2, 9, 31)
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31), log=env.log)
    assert env.fake.orders == [] and env.trigger().exists(), "kept for when they agree"
    assert len(env.titled("QQQ book: CHECK NOW")) == 1
    env.fake.pos = 10
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31, 10), log=env.log)
    assert env.fake.orders == [], "a disagreement is re-read after 30 s, not every tick"
    qe._maybe_flatten_orphan_broker(env.state, _repair_cfg(env), at(DAY2, 9, 31, 40), log=env.log)
    (o,) = env.fake.orders
    assert (o["side"], o["quantity"], o["order_type"]) == ("SELL", "10", "MARKET")


@pytest.mark.parametrize("webull_did", ["EXPIRED", "FILLED"])
def test_review_4_the_tick_settles_yesterdays_order_before_the_open_repair(tenv, webull_did):
    """A limit still working when the box went down at 19:59:56; back at 09:31 the next day with
    the trigger on disk. The tick reads that order FIRST: expired -> the books take the 10 back
    and the repair sells them; filled -> the books are flat and the repair sends nothing."""
    e = tenv
    e.books(ORB=10)
    e.ah(at(DAY, 19, 59, 55))
    (lim,) = e.fake.orders
    if webull_did == "FILLED":
        e.fake.fill(lim["client_order_id"])
    else:
        e.fake.st[lim["client_order_id"]]["status"] = "EXPIRED"
    e.trigger().write_text("flatten\n", encoding="utf-8")
    e.tick(at(DAY2, 9, 31, 0))
    market = [o for o in e.fake.orders if o["order_type"] == "MARKET"]
    if webull_did == "FILLED":
        assert market == [] and e.fake.pos == 0
        assert e.state["after_hours_flatten"][ds(DAY)]["ORB"]["status"] == "filled"
    else:
        assert [(o["side"], o["quantity"]) for o in market] == [("SELL", "10")]
        assert e.fake.pos == 0


# ── item 5: a restart right after an accepted send ───────────────────────────────────────────

def test_review_5_a_restart_after_an_accepted_send_reads_and_settles_the_working_order(env):
    """S4: the limit was accepted (booked: the books read flat), then the process died before
    the state was saved. The recovery scan runs every tick of the window whatever the books
    hold: the order is adopted, read, cancelled at its 45 s, and the shares re-sent."""
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    first = "qxAHORB20261014160005C"
    assert env.held("ORB") == 0, "acked: booked as sold"
    env.state = {"legs": {}, "events": []}
    env.new_adapter()
    assert qe._ah_reconcile_hold(env.state, env.adapter), "the reconcile waits for it"
    env.ah(at(DAY, 16, 0, 10))
    rec = env.rec("ORB")
    assert rec["coid"] == first and rec["status"] in qe.AH_IN_FLIGHT and rec["adopted"]
    for s in (15, 50):
        env.ah(at(DAY, 16, 0, s))
    assert env.fake.cancels == [first], "cancelled 45 s after its own send"
    env.ah(at(DAY, 16, 0, 55))
    assert env.rec("ORB")["history"][0]["coid"] == first
    assert len(env.fake.orders) == 2 and env.fake.orders[1]["limit_price"] == "594.12"
    assert env.row(first)["outcome"] == "CANCELLED"


def test_review_5_a_restart_after_the_window_still_finds_and_settles_the_order(env, monkeypatch):
    """The same crash at 19:59:30, back at 20:10 -- outside the window: the boot scan of the new
    process finds it, cancels it, and the boot reconcile waits for it."""
    env.books(ORB=10)
    env.ah(at(DAY, 19, 59, 30))
    (o,) = env.fake.orders
    env.state = {"legs": {}, "events": []}
    qe.save_state(env.state)
    env.new_adapter()
    monkeypatch.setitem(qe._PROCESS, "ah_boot_scan", False)      # a new process
    calls = []
    monkeypatch.setattr(env.adapter, "reconcile", lambda *a, **k: calls.append(1) or {"ok": True})
    qe._reconcile_broker_at_boot(log=env.log)
    assert calls == [], "no reconcile at boot while an after-hours order may be working"
    assert any("reconcile at boot HELD" in ln for ln in env.lines)
    env.ah(at(DAY, 20, 10, 0))
    assert env.fake.cancels == [o["client_order_id"]]
    env.ah(at(DAY, 20, 10, 5))
    rec = env.rec("ORB")
    assert rec["status"] == "gave_up" and env.held("ORB") == 10 and env.trigger().exists()
    assert len(env.fake.orders) == 1


# ── P&L of record ─────────────────────────────────────────────────────────────────────────────

def test_review_pnl_an_unknown_attempt_that_fills_turns_its_row_ok(env, monkeypatch):
    monkeypatch.setattr(WO, "_sleep", NOOP)
    env.books(ORB=10)
    _open_row("ORB", "BUY", 10, 595.0, "qxORBR620261014T140000ZLO")
    env.fake.drop_answer = True
    env.fake.detail_fail = 3
    env.ah(at(DAY, 16, 0, 5))
    coid = env.rec("ORB")["coid"]
    assert env.row(coid)["ok"] == "False" and env.rec("ORB")["status"] == "unknown"
    assert qe._broker_realized_today(ds(DAY))[0] == 0.0, "an unknown send is not a close yet"
    env.fake.fill(coid, px=599.0)
    env.ah(at(DAY, 16, 0, 15))
    row = env.row(coid)
    assert (row["ok"], row["outcome"], row["shares"], float(row["broker_fill_px"])) == (
        "True", "FILLED", "10", 599.0)
    assert qe._broker_realized_today(ds(DAY)) == (40.0, True)


def test_review_pnl_an_unresolved_give_up_leaves_no_ok_full_quantity_row(env):
    env.books(ORB=10)
    _open_row("ORB", "BUY", 10, 595.0, "qxORBR620261014T140000ZLO")
    env.ah(at(DAY, 16, 0, 5))                          # acked: an ok row for 10
    coid = env.rec("ORB")["coid"]
    assert env.row(coid)["ok"] == "True"
    env.fake.detail_fail = 10 ** 6                     # and then Webull never answers again
    t = at(DAY, 16, 0, 15)
    while t <= at(DAY, 16, 10, 30):
        env.ah(t)
        t += timedelta(seconds=15)
    rec = env.rec("ORB")
    assert rec["status"] == "gave_up" and rec["unresolved_coid"] == coid
    row = env.row(coid)
    assert (row["ok"], row["outcome"]) == ("False", "UNRESOLVED")
    assert qe._broker_realized_today(ds(DAY))[0] == 0.0, "never counted as a full close"


# ── silent stall ──────────────────────────────────────────────────────────────────────────────

def test_review_stall_an_unknown_send_unresolved_10_min_pushes_once_and_moves_on(env, monkeypatch):
    monkeypatch.setattr(WO, "_sleep", NOOP)
    env.books(ORB=10)
    env.fake.drop_answer = True
    env.fake.detail_fail = 10 ** 6
    env.ah(at(DAY, 16, 0, 5))
    coid = env.rec("ORB")["coid"]
    t = at(DAY, 16, 0, 20)
    while t < at(DAY, 16, 10, 5):
        env.ah(t)
        t += timedelta(seconds=15)
    assert qe._ah_in_flight(env.state) and env.rec("ORB")["status"] in qe.AH_IN_FLIGHT
    assert not [p for p in env.pushes if p["priority"] == "urgent"]
    env.ah(at(DAY, 16, 10, 5))
    rec = env.rec("ORB")
    assert rec["status"] == "gave_up" and rec["unresolved_coid"] == coid
    assert not qe._ah_in_flight(env.state), "the reconcile is no longer held"
    assert not qe._ah_active_today(env.state, ds(DAY)), "the after-close check may judge the day"
    for m in (11, 12, 20):
        env.ah(at(DAY, 16, m, 0))
    (note,) = [p for p in env.pushes if p["priority"] == "urgent"]
    assert "unconfirmed" in note["message"]
    assert len(env.fake.orders) == 1, "never a second order on top of the unconfirmed one"
    # Webull answers again: the order settles (it filled) -- books, record and row follow
    env.fake.fill(coid, px=598.0)
    env.fake.detail_fail = 0
    env.ah(at(DAY, 16, 21, 0))
    rec = env.rec("ORB")
    assert rec["settled"] and rec["filled_qty"] == 10 and env.held("ORB") == 0
    assert env.row(coid)["ok"] == "True" and env.row(coid)["outcome"] == "FILLED"
    assert not env.trigger().exists()


def test_review_stall_an_unconfirmed_order_that_expired_arms_the_open_once_it_settles(
        env, monkeypatch):
    coid = _unknown_fill_then_silence(env, monkeypatch, when=at(DAY, 16, 0, 5))
    env.fake.st[coid].update(status="CANCELLED", filled=0)      # it did NOT fill after all
    env.fake.pos = 10
    t = at(DAY, 16, 0, 20)
    while t <= at(DAY, 16, 10, 30):
        env.ah(t)
        t += timedelta(seconds=15)
    assert env.rec("ORB")["status"] == "gave_up" and not env.trigger().exists()
    env.fake.detail_fail = 0
    env.ah(at(DAY, 16, 12, 0))
    rec = env.rec("ORB")
    assert rec["settled"] and env.held("ORB") == 10
    assert rec["next_open_armed"] is True and env.trigger().exists()
    assert "will sell at the 09:30 open" in env.titled("QQQ book: CHECK NOW")[-1]["message"]


# ── boot reconcile ────────────────────────────────────────────────────────────────────────────

def test_review_boot_reconcile_waits_while_a_saved_after_hours_order_works(env, monkeypatch):
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    qe.save_state(env.state)
    calls = []
    monkeypatch.setattr(env.adapter, "reconcile", lambda *a, **k: calls.append(1) or {"ok": True})
    qe._reconcile_broker_at_boot(log=env.log)
    assert calls == []
    env.fake.fill("qxAHORB20261014160005C")
    env.ah(at(DAY, 16, 0, 15))
    qe.save_state(env.state)
    qe._reconcile_broker_at_boot(log=env.log)
    assert calls == [1]


# ── log spam ──────────────────────────────────────────────────────────────────────────────────

def test_review_could_not_cross_logs_once_a_day(env, monkeypatch):
    env.books(ORB=10, NOISE=-10)
    monkeypatch.setattr(env.adapter, "cross_legs_internally", lambda *a, **k: {})
    for s in range(0, 60, 5):
        env.ah(at(DAY, 16, 0, s))
    assert sum("could not cross" in ln for ln in env.lines) == 1


def test_review_nothing_to_close_logs_once_a_day_and_retries_spaced(env, monkeypatch):
    env.books(ORB=10)
    sends = []
    monkeypatch.setattr(qe, "_place_stock_order_with_timeout", lambda *a, **k: sends.append(1) or {
        "ok": False, "sent": False, "mode": "BLOCKED", "nothing_to_close": True,
        "reason": "nothing to close at the broker"})
    t = at(DAY, 16, 0, 0)
    while t <= at(DAY, 16, 2, 0):
        env.ah(t)
        t += timedelta(seconds=5)
    assert len(sends) == 3, "16:00:00, 16:00:45, 16:01:30 -- not every 5 s"
    assert sum("nothing is left to close" in ev["text"] for ev in env.state["events"]) == 1


# ── the adapter's own after-hours backstop ────────────────────────────────────────────────────

def _books_on(adapter, fake, legs):
    for leg, (qty, acct) in legs.items():
        adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
        adapter._state.setdefault("broker_sent_positions", {})[leg] = {
            "symbol": "QQQ", "qty": qty, "account_id": acct}
    adapter._save_state()


@pytest.mark.parametrize("legs,leg,side,qty,why", [
    ({"ORB": (10, "ACCT1"), "NOISE": (-10, "ACCT1")}, "ORB", "SELL", 10, "would open"),   # net 0
    ({"ORB": (10, "ACCT1"), "NOISE": (-5, "ACCT1")}, "ORB", "SELL", 10, "never split"),   # net 5
    ({"DIP_PB": (12, "ACCT1"), "ORB": (-10, "ACCT1")}, "ORB", "BUY", 10, "increase"),     # net 2
])
def test_review_backstop_refuses_an_after_hours_order_that_opens_increases_or_crosses(
        tmp_path, monkeypatch, legs, leg, side, qty, why):
    a, fake = _adapter(tmp_path, monkeypatch)
    _books_on(a, fake, legs)
    rec = a.place_stock_order(leg=leg, signal_id="qxAHX20261014160005C", symbol="QQQ", side=side,
                              qty=qty, intent="CLOSE", order_type="LIMIT", limit_price=600.0,
                              extended_hours=True)
    assert fake.orders == [], "refused before anything reaches Webull"
    assert rec["extended_refused"] is True and rec["ok"] is False and rec["sent"] is False
    assert why in rec["reason"]
    assert a._state["believed_positions"][leg]["qty"] == legs[leg][0], "the books never move"


def test_review_backstop_refuses_an_extended_hours_open(tmp_path, monkeypatch):
    a, fake = _adapter(tmp_path, monkeypatch)
    rec = a.place_stock_order(leg="ORB", signal_id="qxAHOPEN", symbol="QQQ", side="BUY", qty=10,
                              intent="OPEN", order_type="LIMIT", limit_price=600.0,
                              extended_hours=True)
    assert fake.orders == [] and rec["extended_refused"] is True and "only close" in rec["reason"]


@pytest.mark.parametrize("legs,leg,side", [
    ({"ORB": (10, "ACCT1")}, "ORB", "SELL"),
    ({"ORB": (-10, "ACCT1")}, "ORB", "BUY"),
    # the adapter's own account filter: a stale lot under another account never counts
    ({"ORB": (10, "ACCT1"), "NOISE": (-10, "OLDACCT")}, "ORB", "SELL"),
])
def test_review_backstop_lets_a_pure_reduce_through(tmp_path, monkeypatch, legs, leg, side):
    a, fake = _adapter(tmp_path, monkeypatch)
    _books_on(a, fake, legs)
    rec = a.place_stock_order(leg=leg, signal_id="qxAHY20261014160005C", symbol="QQQ", side=side,
                              qty=10, intent="CLOSE", order_type="LIMIT", limit_price=600.0,
                              extended_hours=True)
    assert rec["ok"] is True and not rec.get("extended_refused")
    (o,) = fake.orders
    assert (o["side"], o["quantity"], o["support_trading_session"]) == (side, "10", "ALL")


def test_review_2_after_a_give_up_the_after_close_check_adds_no_second_page(env):
    """The after-hours sell gave up (its own urgent note says what happens at the open); the
    after-close check then reads Webull still holding the shares -- recorded, not paged twice,
    and stamped as the executor's own note (the box monitor stays quiet on it)."""
    env.books(ORB=10)
    env.state.update(flat_by_done_date=ds(DAY), _last_broker_send_at=0.0)
    env.fake.refuse = ["OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET"] * 3
    for t in (at(DAY, 16, 0, 5), at(DAY, 16, 0, 50), at(DAY, 16, 1, 35)):
        env.ah(t)
        qe._maybe_check_webull_flat_after_eod(env.state, env.cfg, t, log=env.log)
    assert env.rec("ORB")["status"] == "gave_up"
    assert "_webull_flat_after_eod" not in env.state, "held: the give-up was less than 30 s ago"
    qe._maybe_check_webull_flat_after_eod(env.state, env.cfg, at(DAY, 16, 2, 10), log=env.log)
    flat = env.state["_webull_flat_after_eod"]
    assert (flat["flat"], flat["shares"], flat["pushed"]) == (False, 10, True)
    urgent = [p for p in env.pushes if p["priority"] == "urgent"]
    assert len(urgent) == 1 and "will sell at the 09:30 open" in urgent[0]["message"]


def test_review_2_the_day_summary_says_the_after_hours_sell_is_still_working(env):
    env.books(ORB=10)
    env.ah(at(DAY, 16, 0, 5))
    doc = {"today": {"trades": [], "realized_pnl": 0.0}, "parity": {"checked": 0, "failed": 0},
           "feed_days": []}
    qe._maybe_send_eod_summary(env.state, doc, at(DAY, 16, 5, 0), log=env.log)
    (note,) = env.titled("QQQ book: day done")
    assert "the after-hours sell is still working" in note["message"]
    assert any("Webull flat: after-hours sell in progress" in ev["text"]
               for ev in env.state["events"])
