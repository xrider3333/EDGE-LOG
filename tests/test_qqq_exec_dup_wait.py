r"""SAME-ORDER WAIT (2026-10-20, G1) -- the api/qqq_exec.py half, driven the way the box drives it.

THE INCIDENT (box qqq_exec.log, 2026-10-20 09:35:12). DIP_STREAK and DIP_GAPDN exited at the open
and both sent SELL 6 QQQ in one instant; Webull refused the second (417
OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK -- an identical order still working on the one
netted account) and the re-send queue sent it again 6 s later under its R1 id. 10-05 at the 15:59
flatten: ORB + NOISE SELL 10, same story.

THE FIX: _mirror_to_broker hands a real (PAPER/LIVE) OrderAdapter send `dup_wait_until`
(_dup_wait_until): the tick's start + DUP_WAIT_TICK_WINDOW_SEC (8 s), never past the session close
- DUP_WAIT_CLOSE_MARGIN_SEC (15 s), and nothing more once a wait of this tick ran out
(_note_dup_wait). The adapter (tests/test_webull_orders_dup_wait.py) waits for the identical
order's answer and sends under the leg's PRIMARY id. Also here: a close_retry that meets a
duplicate stays a close_retry, and a duplicate CLOSE out of re-sends becomes one (EXIT SAFETY).

Harness: tests/test_qqq_exec_dip_live.py's (copied, not imported -- no test module here imports
another): tick() with the engine consumer stubbed, a real PAPER OrderAdapter, and FakeAccount --
ONE QQQ position with Webull's rules, its duplicate rule keyed on (side, qty, order type,
session) against orders still working. A working order fills on its N-th lookup
(`fill_after_lookups`) or `fill_after_sec` after it was placed. The wall clock (time.time) is the
test's; the order path's waits (webull_orders._sleep) advance it, so every bound is measured in
time. No SDK, network or credentials.
"""
import csv
import inspect
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from api import cloud_signal as cs
from api import qqq_exec as qe
from api import trade_id as T
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731

DAY = (2026, 10, 13)      # Tuesday
DAY2 = (2026, 10, 14)     # Wednesday
HALF = (2026, 11, 27)     # the day after Thanksgiving: the session closes at 13:00
SLOTS = ("RSI", "DBL", "PB", "CAP", "IBS", "STREAK", "GAPDN")
DIP = tuple(f"DIP_{s}" for s in SLOTS)
DUP = "OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK"
W0 = 1_000_000.0          # the wall clock at DAY 00:00 ET
_REAL_CAPTURE = qe._maybe_capture_broker_fills


def at(day, h, m, s=0):
    return datetime(day[0], day[1], day[2], h, m, s)


def ds(day):
    return "%04d-%02d-%02d" % day


def _ref(day, hh=9, mm=30):
    return f"{ds(day)}T{hh:02d}:{mm:02d}:00-04:00"


def dip_entry(slot, day, px, hh=9, mm=30):
    ref = _ref(day, hh, mm)
    return {"leg": "DIP_424", "event": "ENTRY", "side": "long", "ref_time": ref, "ref_price": px,
            "bar_source": "webull", "trade_id": T.make("DIP_424", ref, "long", slot=slot),
            "size": "1.0", "keel_size": "", "reason": f"slot={slot}"}


def dip_exit(entry, day, px):
    return dict(entry, event="EXIT", ref_time=_ref(day), ref_price=px, reason="strategy_exit")


def orb_entry(day, hh, mm, side, px):
    ref = _ref(day, hh, mm)
    return {"leg": "ORB_R6", "event": "ENTRY", "side": side, "ref_time": ref, "ref_price": px,
            "bar_source": "webull", "trade_id": T.make("ORB_R6", ref, side), "size": "",
            "keel_size": "", "reason": ""}


def noise_entry(day, hh, mm, side, px, size=1.0):
    ref = _ref(day, hh, mm)
    return {"leg": "NOISE_382", "event": "ENTRY", "side": side, "ref_time": ref, "ref_price": px,
            "bar_source": "webull", "trade_id": T.make("NOISE_382", ref, side), "size": str(size),
            "keel_size": "", "reason": ""}


def an_exit(entry, day, hh, mm, px):
    return dict(entry, event="EXIT", ref_time=_ref(day, hh, mm), ref_price=px,
                reason="strategy_exit")


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeAccount:
    """tests/test_qqq_exec_dip_live.py's FakeAccount (copied): one Webull margin account, QQQ only
    -- a SHORT on a long account, a SELL past the long, a BUY crossing a short and an opposite
    opening order next to a working one are refused; while `async_fills` keeps orders working, an
    order identical to a working one (side, quantity, order type, session) is refused with
    DUPLICATE_ORDER_CHECK. A working order fills on its `fill_after_lookups`-th get_order_detail,
    or once `fill_after_sec` have passed on the wall clock since it was placed (None: never --
    only fill_pending() fills it); an id in `die` dies REJECTED with 0 filled instead.
    `refuse_next` [(qty or None, code)] scripts refusals. Fills at `fill_px`."""

    def __init__(self, wall):
        self.wall = wall
        self.pos = 0
        self.pending = []
        self.status = {}
        self.qty = {}
        self.placed_at = {}
        self.async_fills = False
        self.fill_px = 700.0
        self.fill_after_lookups = None
        self.fill_after_sec = None
        self.die = set()
        self.lookups = {}
        self.refuse_next = []
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
        kind = (o.get("order_type"), o.get("support_trading_session"))
        if self.refuse_next and self.refuse_next[0][0] in (None, qty):
            self._refuse(side, qty, self.refuse_next.pop(0)[1])
        if any(p["side"] == side and p["qty"] == qty and p["kind"] == kind for p in self.pending):
            self._refuse(side, qty, DUP)
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
        self.sent.append((side, qty, coid))
        self.qty[coid] = qty
        self.placed_at[coid] = self.wall[0]
        if self.async_fills:
            self.pending.append({"coid": coid, "side": side, "qty": qty, "opening": opening,
                                 "kind": kind})
            self.status[coid] = "SUBMITTED"
        else:
            self.pos += qty if side == "BUY" else -qty
            self.status[coid] = "FILLED"
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": self.status[coid],
             "filled_price": f"{self.fill_px:.2f}",
             "filled_quantity": "0" if self.async_fills else str(qty)}]})

    def fill_pending(self):
        for p in self.pending:
            self.pos += p["qty"] if p["side"] == "BUY" else -p["qty"]
            self.status[p["coid"]] = "FILLED"
        self.pending = []

    def _detail(self, account_id, coid):
        self.lookups[coid] = self.lookups.get(coid, 0) + 1
        p = next((p for p in self.pending if p["coid"] == coid), None)
        due = p is not None and (
            (self.fill_after_lookups is not None and self.lookups[coid] >= self.fill_after_lookups)
            or (self.fill_after_sec is not None
                and self.wall[0] - self.placed_at[coid] >= self.fill_after_sec))
        if due:
            self.pending.remove(p)
            if coid in self.die:
                self.status[coid] = "REJECTED"
            else:
                self.pos += p["qty"] if p["side"] == "BUY" else -p["qty"]
                self.status[coid] = "FILLED"
        st = self.status.get(coid) or "REJECTED"
        item = {"client_order_id": coid, "status": st, "filled_quantity": "0"}
        if st == "FILLED":
            item.update(filled_quantity=str(self.qty.get(coid, 0)),
                        filled_price=f"{self.fill_px:.2f}")
        return _Resp({"client_order_id": coid, "orders": [item]})


def _wo_cfg(tmp_path):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["rails"]["max_shares_per_leg"] = 60
    cfg["rails"]["daily_loss_limit_usd"] = 400
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _qe_cfg(tmp_path, **kw):
    cfg = json.loads(json.dumps(qe.DEFAULT_CONFIG))
    cfg.update(signal_source="engine", max_shares_per_leg=60, slippage_per_share=0.0,
               daily_loss_limit_usd=400, kill_file=str(tmp_path / "KILL"),
               orb_resting={"mode": "off"})
    cfg["shares"].update({"ORB": 10, "ENGUQ": 10, "NOISE": 10})
    cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
    cfg.update(kw)
    return cfg


def _rows(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


class Env:
    """tests/test_qqq_exec_dip_live.py's Env (copied) plus a wall clock: time.time() reads
    `wall`, which follows the New York clock tick by tick (W0 at DAY 00:00) and is advanced by
    every wait of the order path inside a tick."""

    def __init__(self, tmp_path, monkeypatch):
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
        self.clock = [at(DAY, 9, 0)]
        monkeypatch.setattr(qe, "_now_et", lambda: self.clock[0])
        self.wall = [W0]
        monkeypatch.setattr(qe.time, "time", lambda: self.wall[0])
        monkeypatch.setattr(WO, "_sleep", lambda sec: self.wall.__setitem__(0, self.wall[0] + sec))
        self.price = 700.0
        self.px = {}
        self.marks = {"prior_close": None, "today_open": None, "today_last": None}
        monkeypatch.setattr(qe, "_exit_price_for_leg",
                            lambda leg, log=print: (self.px.get(leg, self.price), "live_stream"))
        monkeypatch.setattr(qe, "_engine_mark_price",
                            lambda leg, log=print: (self.px.get(leg, self.price), "engine_test"))
        monkeypatch.setattr(qe, "_held_session_marks",
                            lambda leg, nowdt, log=print: dict(self.marks, src="engine_1m_bar"))
        self.pushes = []
        monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                            self.pushes.append({"title": title, "message": msg,
                                                "priority": priority}) or True)
        monkeypatch.setattr(qe, "_check_feed_engine", lambda state, log=print: False)
        self.events = []
        monkeypatch.setattr(qe, "_consume_engine_signals",
                            lambda state, cfg, now, log=print: self.events.pop(0) if self.events else [])
        for name in ("_maybe_run_reprice", "_maybe_read_account_equity", "_maybe_capture_broker_fills",
                     "_maybe_send_eod_summary"):
            monkeypatch.setattr(qe, name, NOOP)
        monkeypatch.setattr(qe, "_maybe_note_eod_gave_up", lambda *a, **k: False)
        monkeypatch.setattr(qe, "_build_doc", lambda cfg, state, fs, unrl, log=print: {})
        self.wo_cfg = _wo_cfg(tmp_path)
        with open(self.wo_cfg["paper_keys_path"], "w", encoding="utf-8") as f:
            json.dump({"app_key": "AK", "app_secret": "AS"}, f)
        self.fake = FakeAccount(self.wall)
        self._new_adapter()
        self.cfg = _qe_cfg(tmp_path)
        self.state = {"legs": {}, "events": [], "_px_source": "test"}
        self.lines = []
        qe._BREAKER_ADJ_CACHE["key"] = None

    def log(self, *a, **k):
        self.lines.append(" ".join(str(x) for x in a))

    def _new_adapter(self):
        self.adapter = WO.OrderAdapter(config=json.loads(json.dumps(self.wo_cfg)), log=NOOP)
        self.mp.setattr(self.adapter, "_build_client", lambda mode: self.fake)
        self.mp.setattr(qe, "_get_broker_adapter", lambda log=print: self.adapter)

    def at_wall(self, now):
        """The wall clock follows the New York clock, never backwards."""
        self.clock[0] = now
        self.wall[0] = max(self.wall[0], W0 + (now - at(DAY, 0, 0)).total_seconds())

    def tick(self, now, events=None, cfg=None):
        self.at_wall(now)
        if events:
            self.events.append(events)
        qe._BREAKER_ADJ_CACHE["key"] = None
        _cfg, self.state, _doc = qe.tick(cfg=cfg or self.cfg, state=self.state, now=now, log=self.log)
        return self.state

    def enter_dip(self, slots, day, px, when=None, cfg=None):
        self.price = self.fake.fill_px = px
        rows = [dip_entry(s, day, px) for s in slots]
        self.tick(when or at(day, 9, 35, 10), events=rows, cfg=cfg)
        return rows

    def hold_dip(self, slots, day=DAY, px=700.0):
        rows = self.enter_dip(slots, day, px)
        self.tick(at(day, 15, 59, 5))
        for s in slots:
            assert self.state["legs"][f"DIP_{s}"]["hold"]["flat_by_day"] == ds(day)
        return rows

    def books(self):
        return {leg: p["qty"] for leg, p in (self.adapter._state.get("broker_sent_positions") or {}).items()}

    def broker_rows(self):
        return _rows(qe.BROKER_ORDERS_CSV)

    def sent(self, start=0):
        return [(s, q) for s, q, _c in self.fake.sent[start:]]

    def ids(self, start=0):
        return [c for _s, _q, c in self.fake.sent[start:]]

    def alarms(self, start=0):
        """Every push (from the `start`-th on) that is not a plain fill note."""
        return [p for p in self.pushes[start:] if not p["title"].startswith("QQQ fill")]

    def texts(self):
        return [ev["text"] for ev in self.state.get("events") or []]

    def next_day_open(self, px=698.0):
        self.marks.update(prior_close=700.0, today_open=px, today_last=px)
        self.price = self.fake.fill_px = px


@pytest.fixture(autouse=True)
def _fresh_tick_budget():
    qe._DUP_WAIT_TICK.update(key=None, wall0=None, timed_out=False)
    yield
    qe._DUP_WAIT_TICK.update(key=None, wall0=None, timed_out=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def _close_id(leg, row):
    return qe._broker_signal_id(leg, None, "CLOSE", trade_id=row["trade_id"])


# ── Q1. the 10-20 case: two DIP lots exit at the open, SELL 6 + SELL 6 ─────────────────────────

def test_q1_two_dip_exits_at_the_open_both_go_under_their_primary_ids_with_no_refusal(env):
    e = env
    rows = e.hold_dip(["STREAK", "GAPDN"])
    e.next_day_open()
    e.fake.async_fills = True
    e.fake.fill_after_lookups = 1
    start, pushed = len(e.fake.sent), len(e.pushes)

    e.tick(at(DAY2, 9, 35, 10), events=[dip_exit(rows[0], DAY2, 698.0),
                                        dip_exit(rows[1], DAY2, 698.0)])

    assert e.fake.refused == []
    assert e.sent(start) == [("SELL", 6), ("SELL", 6)]
    ids = e.ids(start)
    assert ids == [_close_id("DIP_STREAK", rows[0]), _close_id("DIP_GAPDN", rows[1])]
    assert all(len(c) == 27 and c.endswith("C") for c in ids), "the PRIMARY ids, no R<n>"
    closes = [r for r in e.broker_rows() if r["intent"] == "CLOSE"]
    assert [(r["leg"], r["outcome"]) for r in closes] == [("DIP_STREAK", "OK"), ("DIP_GAPDN", "OK")]
    assert not [r for r in e.broker_rows() if r["outcome"] != "OK"], "no REFUSED row"
    assert e.state.get("_broker_resend", {}) == {}
    assert e.books()["DIP_STREAK"] == 0 and e.books()["DIP_GAPDN"] == 0
    assert e.alarms(pushed) == [], "no push but the fill notes"
    assert any("waited 0s for identical order(s)" in ln for ln in e.lines)
    assert e.state["dup_wait_today"] == {"date": ds(DAY2), "waits": 1, "settled": 1,
                                         "timed_out": 0, "max_sec": 0.0}
    # fill capture (the real one, one Webull call a tick) prices both rows
    for i in range(2):
        e.wall[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 1
        _REAL_CAPTURE(e.state, e.cfg, at(DAY2, 9, 35, 15 + 5 * i), True, log=NOOP)
    closes = [r for r in e.broker_rows() if r["intent"] == "CLOSE"]
    assert [float(r["broker_fill_px"]) for r in closes] == [698.0, 698.0]
    assert e.fake.pos == 0 and e.adapter.reconcile()["ok"] is True


# ── Q2. seven DIP BUY 6 at one open ────────────────────────────────────────────────────────────

def test_q2_seven_identical_dip_buys_in_one_tick_all_go_with_no_refusal(env):
    e = env
    e.fake.async_fills = True
    e.fake.fill_after_lookups = 1

    e.enter_dip(SLOTS, DAY, 700.0)

    assert e.fake.refused == []
    assert e.sent() == [("BUY", 6)] * 7
    assert sum(e.fake.lookups.values()) == 6, "each buy waited for the one before it, once"
    opens = [r for r in e.broker_rows() if r["intent"] == "OPEN"]
    assert len(opens) == 7 and {r["outcome"] for r in opens} == {"OK"}
    assert all(c.endswith("O") for c in e.ids()), "primary ids"
    assert {leg: e.books()[leg] for leg in DIP} == {leg: 6 for leg in DIP}
    assert not [p for p in e.pushes if "entry missed" in p["title"]]
    assert e.state.get("_broker_resend", {}) == {}
    assert e.state["dup_wait_today"]["waits"] == 6 and e.state["dup_wait_today"]["settled"] == 6
    e.fake.fill_pending()
    assert e.fake.pos == 42 and e.adapter.reconcile()["ok"] is True


# ── Q3. Webull never answers FILLED in time: one wait runs out, then today's path ──────────────

def test_q3_a_wait_that_runs_out_is_today_s_path_and_the_only_wait_of_its_tick(env):
    e = env
    e.fake.async_fills = True          # never fills on a lookup

    rows = e.enter_dip(SLOTS, DAY, 700.0)

    assert e.sent() == [("BUY", 6)]
    assert e.fake.refused == [("BUY", 6, DUP)] * 6, "exactly today's refusals"
    first = e.ids()[0]
    assert e.fake.lookups == {first: WO.DUP_WAIT_POLL_TRIES}, "ONE wait, all in that tick"
    assert e.wall[0] - qe._DUP_WAIT_TICK["wall0"] <= WO.DUP_WAIT_HARD_CAP_SEC
    sent_anyway = [t for t in e.texts() if "sent anyway" in t]
    assert len(sent_anyway) == 1 and "no more waits this tick" in sent_anyway[0]
    assert e.state["dup_wait_today"]["timed_out"] == 1 and e.state["dup_wait_today"]["waits"] == 1
    assert e.alarms() == [], "group E: timeline only"
    q = e.state["_broker_resend"]
    assert list(q) == [f"{leg}:OPEN" for leg in DIP[1:]] and {v["why"] for v in q.values()} == {"duplicate"}

    for i in range(6):                  # the one-per-tick queue drains as before
        e.fake.fill_pending()
        e.tick(at(DAY, 9, 35, 20 + 5 * i))
        assert len(e.fake.sent) == 2 + i, "ONE re-send per tick"
    e.fake.fill_pending()
    assert e.fake.refused == [("BUY", 6, DUP)] * 6, "no re-send met a duplicate"
    assert e.fake.pos == 42 and e.state.get("_broker_resend") == {}
    assert {leg: e.books()[leg] for leg in DIP} == {leg: 6 for leg in DIP}
    assert all(c.endswith("R1") for c in e.ids(1))
    assert not [p for p in e.pushes if "entry missed" in p["title"]]
    assert rows


# ── Q4. the 10-05 case: ORB + NOISE SELL 10 at the 15:59 flatten ───────────────────────────────

def _orb_and_noise_long(e):
    e.tick(at(DAY, 10, 5, 5), events=[orb_entry(DAY, 10, 0, "long", 700.0)])
    e.tick(at(DAY, 10, 35, 5), events=[noise_entry(DAY, 10, 30, "long", 700.0)])
    assert e.fake.pos == 20 and e.books() == {"ORB": 10, "NOISE": 10}


def test_q4_the_flatten_s_two_identical_sells_both_go_at_15_59_01(env):
    e = env
    _orb_and_noise_long(e)
    e.fake.async_fills = True
    e.fake.fill_after_lookups = 1
    start = len(e.fake.sent)

    e.tick(at(DAY, 15, 59, 1))

    assert e.sent(start) == [("SELL", 10), ("SELL", 10)] and e.fake.refused == []
    closes = [r for r in e.broker_rows() if r["intent"] == "CLOSE"]
    assert sorted(r["leg"] for r in closes) == ["NOISE", "ORB"]
    assert {r["outcome"] for r in closes} == {"OK"}
    assert e.state.get("_broker_resend", {}) == {} and e.state["legs"] == {}
    e.fake.fill_pending()
    assert e.fake.pos == 0 and e.books() == {"ORB": 0, "NOISE": 0}


def test_q4_no_wait_at_15_59_46_today_s_refusal_and_the_re_send_before_the_bell(env):
    e = env
    _orb_and_noise_long(e)
    e.fake.async_fills = True
    e.fake.fill_after_lookups = 1
    start = len(e.fake.sent)

    e.tick(at(DAY, 15, 59, 46))          # past close - 15 s: no wait at all

    assert e.fake.lookups == {}
    assert e.sent(start) == [("SELL", 10)] and e.fake.refused == [("SELL", 10, DUP)]
    q = e.state["_broker_resend"]
    assert [v["why"] for v in q.values()] == ["duplicate"]
    e.fake.fill_pending()
    e.tick(at(DAY, 15, 59, 51))          # the next tick re-sends it, still before 16:00:00
    assert e.sent(start) == [("SELL", 10), ("SELL", 10)] and e.ids()[-1].endswith("CR1")
    assert e.state.get("_broker_resend") == {}
    e.fake.fill_pending()
    assert e.fake.pos == 0 and e.books() == {"ORB": 0, "NOISE": 0}


# ── Q5. gap (a): the queue's re-send meets this tick's fresh identical order ──────────────────

def test_q5_a_queued_duplicate_re_send_waits_for_this_tick_s_fresh_identical_order(env):
    e = env
    rows = e.hold_dip(["RSI", "DBL", "PB"])
    e.next_day_open()
    e.fake.async_fills = True            # nothing fills on a lookup yet
    start = len(e.fake.sent)
    e.tick(at(DAY2, 9, 35, 10), events=[dip_exit(rows[0], DAY2, 698.0),
                                        dip_exit(rows[1], DAY2, 698.0)])
    assert e.fake.refused == [("SELL", 6, DUP)]
    assert {k: v["why"] for k, v in e.state["_broker_resend"].items()} == {"DIP_DBL:CLOSE": "duplicate"}

    e.fake.fill_after_lookups = 1         # Webull now answers on the first look
    e.tick(at(DAY2, 9, 35, 20), events=[dip_exit(rows[2], DAY2, 698.0)])

    assert e.sent(start) == [("SELL", 6)] * 3, "RSI, then PB (routing), then DBL's re-send"
    assert e.ids(start)[1] == _close_id("DIP_PB", rows[2])
    assert e.ids(start)[2] == _close_id("DIP_DBL", rows[1]) + "R1"
    assert e.fake.refused == [("SELL", 6, DUP)], "the re-send is not refused again"
    assert e.state.get("_broker_resend") == {}
    assert e.state["dup_wait_today"]["settled"] == 2
    e.fake.fill_pending()
    assert e.fake.pos == 0


# ── Q6. gap (b): a close_retry that meets a duplicate stays a close_retry ─────────────────────

def test_q6_a_close_retry_meeting_a_duplicate_stays_a_close_retry_until_the_deadline(env):
    e = env
    rows = e.hold_dip(["RSI"])
    tid = rows[0]["trade_id"]
    del e.state["legs"]["DIP_RSI"]        # the book closed it; Webull still holds the 6
    key = f"DIP_RSI:CLOSE:{tid}"
    e.at_wall(at(DAY2, 10, 0, 0))
    e.state["_broker_resend"] = {key: dict(
        leg="DIP_RSI", intent="CLOSE", side="long", shares=6, shadow_px=700.0, ts=None, seq=0,
        trade_id=tid, why="close_retry", tries=3, first_at=e.wall[0] - 120,
        last_at=e.wall[0] - 31, session_date=ds(DAY2), sent=False, needs_verify=False,
        last_signal_id=None, unresolved_part_ids=None, verify_qty=6, unresolved_part_qty=None,
        verify_landed_qty=0)}
    e.fake.refuse_next = [(6, DUP), (6, DUP)]
    start = len(e.fake.sent)

    qe._maybe_resend_broker_orders(e.state, e.cfg, at(DAY2, 10, 0, 0), True, log=e.log)
    assert list(e.state["_broker_resend"]) == [key], "still under its trade key"
    item = e.state["_broker_resend"][key]
    assert item["why"] == "close_retry" and item["tries"] == 4 and item["needs_verify"] is False

    e.at_wall(at(DAY2, 10, 0, 5))
    qe._maybe_resend_broker_orders(e.state, e.cfg, at(DAY2, 10, 0, 5), True, log=e.log)
    assert key in e.state["_broker_resend"], "the next tick does not give it up"
    assert len(e.fake.refused) == 1, "inside its backoff: nothing sent"

    e.at_wall(at(DAY2, 10, 0, 35))
    qe._maybe_resend_broker_orders(e.state, e.cfg, at(DAY2, 10, 0, 35), True, log=e.log)
    assert len(e.fake.refused) == 2 and e.state["_broker_resend"][key]["tries"] == 5, \
        "re-sent on the backoff"
    assert e.state["_broker_resend"][key]["why"] == "close_retry"

    e.at_wall(at(DAY2, 15, 59, 49))
    e.fake.refuse_next = [(6, DUP)]
    qe._maybe_resend_broker_orders(e.state, e.cfg, at(DAY2, 15, 59, 49), True, log=e.log)
    assert key in e.state["_broker_resend"], "not given up before 15:59:50"
    e.at_wall(at(DAY2, 15, 59, 50))
    qe._maybe_resend_broker_orders(e.state, e.cfg, at(DAY2, 15, 59, 50), True, log=e.log)
    assert e.state.get("_broker_resend") == {}
    assert any("gave up" in t and "the session flatten deadline passed" in t for t in e.texts())
    assert e.sent(start) == [], "every try was refused"


# ── Q7. the orphan repair's FIX SELL 10 and a strategy SELL 10 in one tick ────────────────────

def test_q7_an_orphan_repair_sell_and_a_same_tick_strategy_sell_are_not_duplicates(env):
    e = env
    entry = noise_entry(DAY, 10, 0, "long", 700.0)
    e.tick(at(DAY, 10, 5, 5), events=[entry])
    # ORB's 10 at Webull that the book holds no lot for (an orphan)
    e.adapter._state["broker_sent_positions"]["ORB"] = {"symbol": "QQQ", "qty": 10,
                                                        "account_id": "ACCT1"}
    e.adapter._state["believed_positions"]["ORB"] = {"symbol": "QQQ", "qty": 10}
    e.adapter._state["open_legs"]["ORB"] = True
    e.fake.pos += 10
    (e.out / "FLATTEN_BROKER").write_text("", encoding="utf-8")
    e.fake.async_fills = True
    e.fake.fill_after_lookups = 1
    start = len(e.fake.sent)

    e.tick(at(DAY, 10, 30, 5), events=[an_exit(entry, DAY, 10, 25, 700.0)])

    assert e.sent(start) == [("SELL", 10), ("SELL", 10)] and e.fake.refused == []
    assert e.ids(start)[0].startswith("qxFIXORB")
    assert e.ids(start)[1] == qe._broker_signal_id("NOISE", None, "CLOSE",
                                                   trade_id=entry["trade_id"])
    e.fake.fill_pending()
    assert e.fake.pos == 0 and e.books()["ORB"] == 0 and e.books()["NOISE"] == 0


# ── Q8. the session close: no wait past close - 15 s, a half day too ─────────────────────────

@pytest.mark.parametrize("now,until_off", [
    (at(DAY, 15, 59, 20), qe.DUP_WAIT_TICK_WINDOW_SEC),   # the tick window binds
    (at(DAY, 15, 59, 40), 5.0),                           # close - 15 s binds: 15:59:45
    (at(DAY, 15, 59, 45), None),
    (at(DAY, 15, 59, 46), None),
    (at(HALF, 12, 59, 20), qe.DUP_WAIT_TICK_WINDOW_SEC),
    (at(HALF, 12, 59, 44), 1.0),                          # 12:59:45 on a half day
    (at(HALF, 12, 59, 46), None),
    (at(HALF, 15, 59, 20), None),                         # long after a half day's close
])
def test_q8_no_wait_ends_past_the_close_minus_15s(monkeypatch, now, until_off):
    wall = [W0]
    monkeypatch.setattr(qe.time, "time", lambda: wall[0])
    state = {}
    got = qe._dup_wait_until(state, now)
    assert got == (None if until_off is None else W0 + until_off)
    assert qe._dup_wait_until(state, None) is None


def test_q8_a_half_day_s_12_59_46_pair_never_waits(env):
    e = env
    for leg in ("ORB", "NOISE"):
        e.adapter._state.setdefault("broker_sent_positions", {})[leg] = {
            "symbol": "QQQ", "qty": 10, "account_id": "ACCT1"}
        e.adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": 10}
    e.fake.pos = 20
    e.fake.async_fills = True
    e.fake.fill_after_lookups = 1
    now = at(HALF, 12, 59, 46)
    e.at_wall(now)
    for leg in ("ORB", "NOISE"):
        qe._mirror_to_broker(e.state, leg=leg, side="long", shares=10, shadow_px=700.0,
                             intent="CLOSE", trade_id=f"{leg}_X-20261127T150000Z-L", nowdt=now,
                             log=e.log)
    assert e.fake.lookups == {} and e.fake.refused == [("SELL", 10, DUP)]


# ── Q9. driven by tick(): every wait of one tick fits inside its 8 s ──────────────────────────

def test_q9_the_waits_of_one_tick_end_by_its_start_plus_8s(env):
    e = env
    e.fake.async_fills = True
    e.fake.fill_after_sec = 2.0           # each order fills 2 s after it went out
    start_wall = W0 + (at(DAY, 9, 35, 10) - at(DAY, 0, 0)).total_seconds()

    e.enter_dip(SLOTS, DAY, 700.0)

    assert qe._DUP_WAIT_TICK["wall0"] == start_wall, "the budget starts when the tick does"
    spent = e.wall[0] - start_wall
    assert 0 < spent <= qe.DUP_WAIT_TICK_WINDOW_SEC, spent
    c = e.state["dup_wait_today"]
    # 2.25 s each for three buys, then the fourth wait is cut at 8 s: still working, sent anyway
    assert (c["waits"], c["settled"], c["timed_out"]) == (4, 3, 1)
    assert c["max_sec"] == pytest.approx(2.25)
    assert e.fake.refused == [("BUY", 6, DUP)] * 3, "after the cut: today's path"
    assert len([t for t in e.texts() if "sent anyway" in t]) == 1


# ── Q10. callers that never wait ──────────────────────────────────────────────────────────────

def _spy_sends(e, monkeypatch):
    calls = []
    real = e.adapter.place_stock_order

    def spy(**kw):
        calls.append(kw)
        return real(**kw)
    monkeypatch.setattr(e.adapter, "place_stock_order", spy)
    return calls


def test_q10_a_real_armed_send_is_given_dup_wait_until(env, monkeypatch):
    e = env
    calls = _spy_sends(e, monkeypatch)
    e.enter_dip(["RSI"], DAY, 700.0)
    assert len(calls) == 1 and isinstance(calls[0]["dup_wait_until"], float)


def test_q10_off_mode_is_never_given_dup_wait_until(env, monkeypatch):
    e = env
    e.adapter.cfg["mode"] = "OFF"
    calls = _spy_sends(e, monkeypatch)
    e.enter_dip(["RSI", "DBL"], DAY, 700.0)
    assert len(calls) == 2 and all("dup_wait_until" not in kw for kw in calls)


def test_q10_a_test_double_adapter_is_never_given_dup_wait_until(env, monkeypatch):
    e = env
    adapter = MagicMock()
    adapter.effective_mode.return_value = ("PAPER", "test double")
    adapter.place_stock_order.return_value = {"ok": True, "sent": True, "mode": "PAPER",
                                              "client_order_id": "x", "duplicate": False}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    e.at_wall(at(DAY, 10, 0, 0))
    qe._mirror_to_broker(e.state, leg="ORB", side="long", shares=10, shadow_px=700.0,
                         intent="OPEN", trade_id="ORB_R6-20261013T140000Z-L",
                         nowdt=at(DAY, 10, 0, 0), log=e.log)
    assert adapter.place_stock_order.call_count == 1
    assert "dup_wait_until" not in adapter.place_stock_order.call_args.kwargs


def test_q10_the_after_hours_sell_is_never_given_dup_wait_until(env):
    e = env
    adapter = MagicMock()
    adapter.place_stock_order.return_value = {"ok": True, "sent": True, "mode": "PAPER",
                                              "client_order_id": "qxAHORB20261013160500C"}
    now = at(DAY, 16, 5, 0)
    e.at_wall(now)
    qe._ah_send(e.state, e.cfg, adapter, "ORB", {}, now, at(DAY, 20, 0, 0), bside="SELL", qty=10,
                limit=699.0, cushion=0.001, ref_px=700.0, ref_src="test", ref_age=1.0,
                mode="PAPER", log=e.log)
    kw = adapter.place_stock_order.call_args.kwargs
    assert kw["extended_hours"] is True and kw["order_type"] == "LIMIT"
    assert "dup_wait_until" not in kw


def test_q10_resting_orders_do_not_go_through_this_path():
    for name in ("place_resting", "replace_resting"):
        assert "dup_wait_until" not in inspect.signature(getattr(WO.OrderAdapter, name)).parameters


# ── the phone: a split close whose second part meets the duplicate rule ───────────────────────

def test_a_partial_close_refused_as_a_duplicate_pushes_nothing_the_queue_owns_it(env):
    """ORB long 10 against NOISE short 6 (account +4): ORB's SELL 10 goes as SELL 4 + SHORT 6,
    and Webull refuses the SHORT 6 as a same-instant duplicate. Never placed, and the re-send
    queue takes it -- so no "the sell is late" push now (its give-up still pages); the timeline
    still says it only partly reached Webull."""
    e = env
    for leg, qty in (("ORB", 10), ("NOISE", -6)):
        e.adapter._state.setdefault("broker_sent_positions", {})[leg] = {
            "symbol": "QQQ", "qty": qty, "account_id": "ACCT1"}
        e.adapter._state.setdefault("believed_positions", {})[leg] = {"symbol": "QQQ", "qty": qty}
    e.fake.pos = 4
    e.fake.refuse_next = [(6, DUP)]
    now = at(DAY, 11, 0, 0)
    e.at_wall(now)

    qe._mirror_to_broker(e.state, leg="ORB", side="long", shares=10, shadow_px=700.0,
                         intent="CLOSE", trade_id="ORB_R6-20261013T140000Z-L", nowdt=now,
                         log=e.log)

    assert e.sent() == [("SELL", 4)] and e.fake.refused == [("SHORT", 6, DUP)]
    assert e.pushes == [], "no push: the queue owns it"
    assert any("only PARTIALLY reached Webull" in t for t in e.texts())
    assert [v["why"] for v in e.state["_broker_resend"].values()] == ["duplicate"]


# ── the kill switch: gateway.dup_wait_sec 0 is today's behaviour ──────────────────────────────

def test_the_kill_switch_dup_wait_sec_0_is_today_s_behaviour(env):
    e = env
    e.adapter.cfg["gateway"]["dup_wait_sec"] = 0
    e.fake.async_fills = True
    e.fake.fill_after_lookups = 1         # a lookup WOULD fill -- none may happen

    e.enter_dip(SLOTS, DAY, 700.0)

    assert e.fake.lookups == {}
    assert e.sent() == [("BUY", 6)] and e.fake.refused == [("BUY", 6, DUP)] * 6
    assert "dup_wait_today" not in e.state
    assert not any("dup_wait" in r for r in e.adapter._state["orders"].values())
    assert e.wall[0] == W0 + (at(DAY, 9, 35, 10) - at(DAY, 0, 0)).total_seconds(), "no time spent"
