r"""DIP #424 LIVE LEG -- the executor, adapter, broker ids and rails (OWNER GO 2026-10-10, MANAGER
#115; build map C:\EdgeLog\manager\paperwb_1007\DIP_LIVE_BUILD_MAP_1010.md, Option A).

DIP #424 FIXED 1.245x trades on the Webull paper QQQ book as SEVEN one-lot exec legs, one per
NQDIP_1_1.py mechanism (DIP_RSI, DIP_DBL, DIP_PB, DIP_CAP, DIP_IBS, DIP_STREAK, DIP_GAPDN --
family "DIP"), fed by ONE engine key, DIP_424, whose trade ids carry the mechanism slot
(<leg>-<UTC>-L-<SLOT>). 6 shares a lot (the 1.245 is inside the 6), at most 42 DIP shares, book
gross cap 85 (the adapter's rails), DIP OFF the shared $400 daily loss breaker with its OWN -$800
rail that only blocks DIP entries through the next session (never sells), the shared KILL sells
everything (deferred to the open outside regular hours), DIP held overnight (mark-to-open: the
overnight gap is outside every rail).

Driven the way the box drives it: engine ENTRY/EXIT rows routed through api/qqq_exec.tick (the
consumer stubbed to hand them over) or _route_engine_events, a real api.webull_orders.OrderAdapter
in PAPER mode, and a fake Webull account holding ONE QQQ position that enforces Webull's rules --
including DUPLICATE_ORDER_CHECK while orders are still working (the pattern of
tests/test_qqq_exec_enguq_live_netting.py, copied, not imported). No SDK, network or credentials.

COVERS: slot mapping + unknown-slot refusal + the entry id check WITH the slot (the blocker); 7
lots x 6 at one open and ONE batched fill note; the 42 cap refusing a lot past it; flatten holds
DIP (also on a shared-breaker day); DIP -$700 does not trip the $400 breaker while ORB -$450 trips
it and spares DIP; DIP's rail never sells, blocks DIP through the next session, then resets; the
adapter leaves DIP out of its daily P&L and exempts DIP from its loss check, while gross 85
counts DIP; KILL in and out of regular hours; a carried DIP exit reads ~0 on the rail with its
gap in the P&L; EXIT then ENTRY on one slot in one tick; seven identical BUY 6 -> duplicates ->
all filled through the one-per-tick re-send queue; the boot check, orphan repair and after-close
check expecting DIP lots; the "open" parity code; the status doc's families.
"""
import csv
import json
import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from api import cloud_signal as cs
from api import ntfy_push
from api import qqq_exec as qe
from api import trade_id as T
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731

DAY = (2026, 10, 13)      # Tuesday -- the DIP leg's first live session
DAY2 = (2026, 10, 14)     # Wednesday
DAY3 = (2026, 10, 15)     # Thursday
SLOTS = ("RSI", "DBL", "PB", "CAP", "IBS", "STREAK", "GAPDN")
DIP = tuple(f"DIP_{s}" for s in SLOTS)
DUP = "OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK"
_REAL_BUILD_DOC = qe._build_doc
_REAL_CONSUME = qe._consume_engine_signals


def at(day, h, m, s=0):
    return datetime(day[0], day[1], day[2], h, m, s)


def ds(day):
    return "%04d-%02d-%02d" % day


def _ref(day, hh=9, mm=30):
    return f"{ds(day)}T{hh:02d}:{mm:02d}:00-04:00"


def dip_entry(slot, day, px, hh=9, mm=30):
    """A DIP_424 ENTRY row: the session's 09:30 bar at its open, the mechanism in the id's slot."""
    ref = _ref(day, hh, mm)
    return {"leg": "DIP_424", "event": "ENTRY", "side": "long", "ref_time": ref, "ref_price": px,
            "bar_source": "webull", "trade_id": T.make("DIP_424", ref, "long", slot=slot),
            "size": "1.0", "keel_size": "", "reason": f"slot={slot}"}


def dip_exit(entry, day, px):
    """Its EXIT: decided at the prior close, filled at `day`'s 09:30 open."""
    return dict(entry, event="EXIT", ref_time=_ref(day), ref_price=px, reason="strategy_exit")


def orb_entry(day, hh, mm, side, px):
    ref = _ref(day, hh, mm)
    return {"leg": "ORB_R6", "event": "ENTRY", "side": side, "ref_time": ref, "ref_price": px,
            "bar_source": "webull", "trade_id": T.make("ORB_R6", ref, side), "size": "",
            "keel_size": "", "reason": ""}


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeAccount:
    """One Webull margin account, QQQ only -- tests/test_qqq_exec_enguq_live_netting.py's rules
    (copied): a SHORT on a long account, a SELL past the long, a BUY crossing a short straight to
    long and an opposite opening order next to a working one are refused; while `async_fills`
    keeps orders working, a new order identical to a working one (same side, same quantity) is
    refused with Webull's DUPLICATE_ORDER_CHECK. Fills at `fill_px`."""

    def __init__(self):
        self.pos = 0
        self.pending = []
        self.status = {}
        self.async_fills = False
        self.fill_px = 700.0
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
        if self.async_fills:
            self.pending.append({"coid": coid, "side": side, "qty": qty, "opening": opening})
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
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": self.status.get(coid) or "REJECTED",
             "filled_quantity": "0"}]})


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
    """The box's sizing (ORB / ENGUQ / NOISE 10, cap 60, the shared $400) -- DIP's 6 shares a
    lot, 42 cap and -$800 rail come from the code defaults, as on the box."""
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
    """A tick()-driven book: a temp qqq_exec home, a controllable New York clock, one QQQ price
    per leg (`px`, default `price`), the held lots' session marks, captured phone notes, engine
    rows handed straight to the router, and a real PAPER adapter on FakeAccount."""

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
        self.fake = FakeAccount()
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

    def restart(self):
        qe.save_state(self.state)
        self.state = qe.load_state()
        self._new_adapter()

    def tick(self, now, events=None, cfg=None):
        self.clock[0] = now
        if events:
            self.events.append(events)
        qe._BREAKER_ADJ_CACHE["key"] = None
        _cfg, self.state, _doc = qe.tick(cfg=cfg or self.cfg, state=self.state, now=now, log=self.log)
        return self.state

    def enter_dip(self, slots, day, px, when=None, cfg=None):
        """The given mechanisms enter at `day`'s 09:30 open (`px`), seen at 09:35:10."""
        self.price = self.fake.fill_px = px
        rows = [dip_entry(s, day, px) for s in slots]
        self.tick(when or at(day, 9, 35, 10), events=rows, cfg=cfg)
        return rows

    def hold_dip(self, slots, day=DAY, px=700.0, close_px=None):
        rows = self.enter_dip(slots, day, px)
        self.price = close_px if close_px is not None else px
        self.tick(at(day, 15, 59, 5))
        for s in slots:
            assert self.lot(f"DIP_{s}")["hold"]["flat_by_day"] == ds(day)
        return rows

    def lot(self, leg):
        return self.state["legs"][leg]

    def books(self):
        return {leg: p["qty"] for leg, p in (self.adapter._state.get("broker_sent_positions") or {}).items()}

    def broker_rows(self):
        return _rows(qe.BROKER_ORDERS_CSV)

    def trades(self):
        return _rows(qe.TRADES_CSV)

    def orders(self):
        return _rows(qe.ORDERS_CSV)

    def issues(self):
        return (self.state.get("trade_id_checks") or {}).get("today") or {}

    def sent(self, start=0):
        return [(s, q) for s, q, _c in self.fake.sent[start:]]

    def titled(self, title):
        return [p for p in self.pushes if p["title"] == title]

    def kill(self, on=True):
        p = self.tmp / "KILL"
        if on:
            p.write_text("")
        elif p.exists():
            p.unlink()


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


# ── the shape: seven exec legs, one engine key, code defaults ──────────────────────────────────

def test_seven_exec_legs_one_engine_key_and_the_code_defaults(tmp_path):
    assert qe.DIP_LEGS == DIP and qe.DIP_SLOTS == SLOTS == tuple(m for m, _f in cs.DIP_MECHS)
    assert qe.LEGS == ("ORB", "ENGUQ", "NOISE") + DIP
    assert qe.HOLD_OVERNIGHT_LEGS == ("ENGUQ",) + DIP
    assert "DIP_424" not in qe.ENGINE_LEG_MAP, "one engine key, seven exec legs: _exec_leg_for"
    for s in SLOTS:
        tid = T.make("DIP_424", _ref(DAY), "long", slot=s)
        assert qe._exec_leg_for("DIP_424", tid) == f"DIP_{s}"
        assert qe._engine_key_for_leg(f"DIP_{s}") == "DIP_424"
        assert qe.is_dip_leg(f"DIP_{s}") and qe.leg_family(f"DIP_{s}") == "DIP"
    assert qe._exec_leg_for("DIP_424", T.make("DIP_424", _ref(DAY), "long")) is None, "no slot"
    assert qe._exec_leg_for("DIP_424", T.make("DIP_424", _ref(DAY), "long", slot="FOO")) is None
    assert qe._exec_leg_for("NOISE_382", "NOISE_382-20261013T140000Z-L") == "NOISE"
    assert qe._exec_leg_for("DIP_424F", "DIP_424F-20261013T133000Z-L-RSI") is None, "shadows stay out"
    assert not qe.is_dip_leg("DIP") and qe.leg_family("ORB") == "ORB"
    assert qe.LEG_FAMILIES == dict({"ORB": "ORB", "ENGUQ": "ENGUQ", "NOISE": "NOISE"},
                                   **{leg: "DIP" for leg in DIP})
    # code defaults that survive the box's config.json (load_config merges ONE level deep: the
    # box's "shares" block names only ORB / ENGUQ / NOISE, and no DIP key at all)
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"shares": {"ORB": 10, "ENGUQ": 10, "NOISE": 10}, "max_shares_per_leg": 60,
                             "daily_loss_limit_usd": 400,
                             "session": {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}}),
                 encoding="utf-8")
    cfg = qe.load_config(path=str(p), log=NOOP)
    assert {leg: cfg["shares"][leg] for leg in DIP} == {leg: 6 for leg in DIP}
    assert cfg["shares"]["ORB"] == 10
    assert cfg["dip_max_total_shares"] == 42 and cfg["dip_daily_loss_limit_usd"] == 800
    assert qe._hold_legs(cfg) == ("ENGUQ",) + DIP, "the box sets no hold list: the code default"
    assert qe._dip_cap({}) == 42 and qe._dip_limit({}) == 800.0
    assert qe._dip_cap({"dip_max_total_shares": "x"}) == 42 and qe._dip_limit({"dip_daily_loss_limit_usd": 0}) == 0
    # nothing the book WRITES is baked into DEFAULT_CONFIG by this change
    assert not any(k.startswith("dip_") and "path" in k for k in qe.DEFAULT_CONFIG)


# ── the entry id check with the slot (THE BLOCKER) and the slot mapping ───────────────────────

def test_a_dip_entry_opens_its_mechanism_s_lot_under_its_slot_id(env):
    e = env
    e.enter_dip(["RSI"], DAY, 700.0)
    lot = e.lot("DIP_RSI")
    assert lot["trade_id"] == "DIP_424-20261013T133000Z-L-RSI"
    assert lot["shares_total"] == 6 and lot["side"] == "long"
    assert "entry_id_conflict" not in e.issues(), "the id is rebuilt WITH its slot"
    assert e.fake.sent == [("BUY", 6, "qxDIP42420261013T133000ZLRO")]
    assert e.books() == {"DIP_RSI": 6} and e.fake.pos == 6


def test_an_unknown_slot_or_a_wrong_stamp_is_refused_and_counted(env):
    e = env
    foo = dip_entry("RSI", DAY, 700.0)
    foo["trade_id"] = T.make("DIP_424", _ref(DAY), "long", slot="FOO")
    wrong = dip_entry("DBL", DAY, 700.0)
    wrong["trade_id"] = T.make("DIP_424", _ref(DAY, 9, 35), "long", slot="DBL")
    e.price = e.fake.fill_px = 700.0
    e.tick(at(DAY, 9, 35, 10), events=[foo, wrong])
    assert e.state["legs"] == {} and e.fake.sent == []
    assert e.issues().get("unknown_slot") == 1 and e.issues().get("entry_id_conflict") == 1
    assert qe._build_trade_id_status(e.state, ds(DAY))["today"]["unknown_slot"] == 1


def test_an_engine_size_never_multiplies_a_dip_lot(env):
    e = env
    row = dip_entry("PB", DAY, 700.0)
    row["size"] = "1.245"
    e.price = e.fake.fill_px = 700.0
    e.tick(at(DAY, 9, 35, 10), events=[row])
    assert e.lot("DIP_PB")["shares_total"] == 6, "FIXED 1.245x is already inside the 6"
    assert any("ignored -- DIP trades a fixed 6 shares a lot" in ln for ln in e.lines)


# ── seven lots of six at one open; the 42 cap ────────────────────────────────────────────────

def test_seven_mechanisms_open_seven_lots_of_six_and_one_fill_note(env):
    e = env
    e.enter_dip(SLOTS, DAY, 700.0)
    assert set(e.state["legs"]) == set(DIP)
    assert all(e.lot(leg)["shares_remaining"] == 6 for leg in DIP)
    assert e.sent() == [("BUY", 6)] * 7 and len({c for _s, _q, c in e.fake.sent}) == 7
    assert e.fake.pos == 42 and e.books() == {leg: 6 for leg in DIP}
    assert e.adapter.reconcile()["ok"] is True
    (note,) = [p for p in e.pushes if p["title"].startswith("QQQ fill")]
    assert note["title"] == "QQQ fill: DIP bought" and note["priority"] == "low"
    assert "several DIP lots at 700.00" in note["message"] and ntfy_push.lint(note) == []
    (day_row,) = qe._build_signals_day(e.state)
    assert set(day_row["by_leg"]) == {"ORB", "ENGUQ", "NOISE", "DIP"}, "by family"
    assert day_row["by_leg"]["DIP"] == {"fired": 7, "taken": 7, "refused": 0, "oos": 0}
    assert day_row["taken"] == 7
    assert "DIP_RSI" in (e.state["signals_days"][ds(DAY)]), "counted per exec leg underneath"


def test_the_42_cap_takes_seven_lots_of_six_exactly_and_refuses_a_lot_past_it(env):
    e = env
    cfg = json.loads(json.dumps(e.cfg))
    cfg["shares"]["DIP_GAPDN"] = 7          # one lot one share bigger: 36 + 7 = 43 > 42
    e.enter_dip(SLOTS, DAY, 700.0, cfg=cfg)
    assert set(e.state["legs"]) == set(DIP) - {"DIP_GAPDN"}
    assert e.sent() == [("BUY", 6)] * 6 and e.fake.pos == 36
    (ref,) = [o for o in e.orders() if o["leg"] == "DIP_GAPDN"]
    assert ref["reason"] == "REFUSED DIP total 36 + 7 > dip_max_total_shares 42"
    assert any(ev["kind"] == "dip_cap" for ev in e.state["events"])
    assert qe._build_signals_day(e.state)[0]["by_leg"]["DIP"]["refused"] == 1
    # 0 = no cap
    cfg["dip_max_total_shares"] = 0
    e.price = e.fake.fill_px = 701.0
    e.tick(at(DAY, 10, 0, 5), events=[dip_entry("GAPDN", DAY, 701.0)], cfg=cfg)
    assert e.lot("DIP_GAPDN")["shares_total"] == 7 and e.fake.pos == 43


# ── the flatten holds DIP (also on a shared-breaker day) ──────────────────────────────────────

def test_the_flatten_closes_orb_and_holds_every_dip_lot_with_one_note(env):
    e = env
    e.enter_dip(["RSI", "PB"], DAY, 700.0)
    e.tick(at(DAY, 10, 5, 5), events=[orb_entry(DAY, 10, 0, "long", 700.0)])
    assert e.fake.pos == 22
    start = len(e.fake.sent)
    e.tick(at(DAY, 15, 59, 5))
    assert set(e.state["legs"]) == {"DIP_RSI", "DIP_PB"}
    assert e.sent(start) == [("SELL", 10)], "ORB's own sell; DIP never in the flatten"
    for leg in ("DIP_RSI", "DIP_PB"):
        assert e.lot(leg)["hold"]["since"] == ds(DAY)
    assert e.fake.pos == 12 and e.books() == {"DIP_RSI": 6, "DIP_PB": 6, "ORB": 0}
    held = [ev["text"] for ev in e.state["events"] if ev["kind"] == "held_overnight"]
    assert held == ["DIP long 12 (2 lots) held overnight -- the end-of-day flatten skips it (it holds "
                    "like its backtest); each lot sells on its own strategy exit, at market in "
                    "regular hours"]
    (note,) = e.titled("QQQ book: held overnight")
    assert "DIP keeps its 12 QQQ shares overnight across its open lots" in note["message"]
    assert note["priority"] == "low" and ntfy_push.lint(note) == []


def test_dip_minus_700_never_trips_the_400_breaker_and_orb_minus_450_trips_it_sparing_dip(env):
    e = env
    e.enter_dip(SLOTS, DAY, 716.67)
    for leg in DIP:
        e.px[leg] = 700.0                   # 42 x -16.67 = -700.14 on DIP
    e.tick(at(DAY, 10, 0, 5))
    assert e.state["breaker_tripped"] is False and set(e.state["legs"]) == set(DIP)
    assert e.state["_breaker_input"]["pnl"] == 0.0, "the shared rail never counts DIP"
    assert e.state["_dip_rail_input"]["pnl"] == pytest.approx(-700.14)
    assert e.state.get("dip_rail") is None, "-700 is inside DIP's own -800"
    # ORB short 10 at 655 -> marked at 700: -450 on the shared rail
    e.px["ORB"] = e.fake.fill_px = 655.0
    e.tick(at(DAY, 10, 10, 5), events=[orb_entry(DAY, 10, 5, "short", 655.0)])
    assert e.state["breaker_tripped"] is False and "ORB" in e.state["legs"]
    start = len(e.fake.sent)
    e.px["ORB"] = e.fake.fill_px = 700.0
    e.tick(at(DAY, 10, 15, 5))
    assert e.state["breaker_tripped"] is True
    assert e.sent(start) == [("BUY", 10)], "only ORB is closed -- no DIP sell"
    assert set(e.state["legs"]) == set(DIP) and e.fake.pos == 42
    assert e.state["_breaker_input"]["pnl"] == -450.0
    assert e.trades()[-1]["leg"] == "ORB" and e.trades()[-1]["exit_reason"].startswith("BREAKER")
    (stop,) = e.titled("QQQ book: daily stop hit")
    assert "DIP is not on this limit and keeps its trades" in stop["message"]
    assert ntfy_push.lint(stop) == []
    bk = [ev["text"] for ev in e.state["events"] if ev["kind"] == "breaker"]
    assert bk and "except DIP's (7 lots, its own rail)" in bk[-1]
    # the adapter's own daily P&L is the shared figure: ORB's -450, never DIP's -700 mark
    assert e.adapter._state["daily_pnl"] == pytest.approx(-450.0)
    # the shared trip blocks ORB, never DIP; the flatten still holds DIP on this breaker day
    e.tick(at(DAY, 15, 59, 5))
    assert set(e.state["legs"]) == set(DIP) and e.fake.pos == 42
    assert all(e.lot(leg)["hold"]["flat_by_day"] == ds(DAY) for leg in DIP)


def test_the_shared_trip_never_blocks_a_dip_entry(env):
    e = env
    e.state["realized_pnl_today"] = -500.0
    e.state["trading_day"] = ds(DAY)
    e.tick(at(DAY, 9, 30, 5))
    assert e.state["breaker_tripped"] is True
    e.price = e.fake.fill_px = 700.0
    e.tick(at(DAY, 9, 35, 10), events=[dip_entry("CAP", DAY, 700.0), orb_entry(DAY, 9, 30, "long", 700.0)])
    assert set(e.state["legs"]) == {"DIP_CAP"}
    (orb,) = [o for o in e.orders() if o["leg"] == "ORB"]
    assert orb["reason"] == "REFUSED -- breaker/feed/kill blocked"


# ── DIP's own rail: never sells, blocks DIP through the next session, then resets ─────────────

def test_dip_s_rail_blocks_dip_through_the_next_session_then_resets_and_never_sells(env):
    e = env
    rows = e.enter_dip(SLOTS, DAY, 720.0)
    for leg in DIP:
        e.px[leg] = 699.5                    # 42 x -20.5 = -861
    sells = len(e.fake.sent)
    e.tick(at(DAY, 11, 0, 5))
    assert e.state["dip_rail"] == {"tripped_on": ds(DAY), "blocks_until": ds(DAY2), "loss_usd": -861.0}
    assert len(e.fake.sent) == sells and set(e.state["legs"]) == set(DIP), "nothing is ever sold"
    assert e.state["breaker_tripped"] is False and e.state["_breaker_input"]["pnl"] == 0.0
    (note,) = e.titled("QQQ book: DIP stop hit")
    assert note["priority"] == "high" and ntfy_push.lint(note) == []
    assert "no new DIP trades today or next session" in note["message"]
    kinds = [ev["kind"] for ev in e.state["events"]]
    assert "dip_rail" in kinds and "breaker" not in kinds
    e.tick(at(DAY, 11, 5, 5))
    assert len(e.titled("QQQ book: DIP stop hit")) == 1, "one trip a day"
    # the shared book still trades
    e.px["ORB"] = e.fake.fill_px = 699.5
    e.tick(at(DAY, 11, 10, 5), events=[orb_entry(DAY, 11, 5, "long", 699.5)])
    assert "ORB" in e.state["legs"]
    e.tick(at(DAY, 15, 59, 5))
    assert "ORB" not in e.state["legs"] and set(e.state["legs"]) == set(DIP)

    # next session: the block stands (midnight never clears it); an exit still goes, an entry not
    e.tick(at(DAY2, 0, 0, 5))
    assert e.state["dip_rail"]["blocks_until"] == ds(DAY2)
    e.marks.update(prior_close=699.5, today_open=699.5, today_last=699.5)
    e.price = e.fake.fill_px = 699.5
    for leg in DIP:
        e.px.pop(leg, None)
    start = len(e.fake.sent)
    e.tick(at(DAY2, 9, 35, 10), events=[dip_exit(rows[0], DAY2, 699.5), dip_entry("RSI", DAY2, 699.5),
                                        orb_entry(DAY2, 9, 30, "long", 699.5)])
    assert "DIP_RSI" not in e.state["legs"], "the rail never blocks an exit"
    assert "ORB" in e.state["legs"]
    assert e.sent(start) == [("SELL", 6), ("BUY", 10)]
    (refused,) = [o for o in e.orders() if o["leg"] == "DIP_RSI" and o["reason"].startswith("REFUSED")]
    assert refused["reason"] == ("REFUSED -- DIP daily loss rail (tripped 2026-10-13) blocks DIP "
                                 "entries through 2026-10-14")
    assert any(ev["kind"] == "dip_rail_blocked" for ev in e.state["events"])
    assert e.state["dip_rail"]["tripped_on"] == ds(DAY), "a quiet day 2 never re-trips"

    # the session after: reset, DIP trades again
    e.tick(at(DAY2, 15, 59, 5))
    e.tick(at(DAY3, 0, 0, 5))
    assert e.state["dip_rail"] is None
    assert e.state["dip_rail_last"]["tripped_on"] == ds(DAY) and e.state["dip_rail_last"]["reset_on"] == ds(DAY3)
    assert any(ev["kind"] == "dip_rail_reset" for ev in e.state["events"])
    e.tick(at(DAY3, 9, 35, 10), events=[dip_entry("RSI", DAY3, 699.5)])
    assert e.lot("DIP_RSI")["trade_id"] == "DIP_424-20261015T133000Z-L-RSI"


def test_next_session_after_skips_weekends_and_holidays():
    assert qe._next_session_after("2026-10-13") == "2026-10-14"
    assert qe._next_session_after("2026-10-16") == "2026-10-19", "Friday -> Monday"
    assert qe._next_session_after("2026-11-25") == "2026-11-27", "Thanksgiving skipped"
    assert qe._next_session_after("2026-10-13", 2) == "2026-10-15"
    st = {"dip_rail": {"tripped_on": "2026-10-16", "blocks_until": "2026-10-19"}}
    assert [qe._dip_rail_blocking(st, d) for d in ("2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20")] \
        == [False, True, True, False]
    assert qe._dip_rail_blocking({}, "2026-10-16") is False
    assert qe._dip_rail_blocking({"dip_rail": None}, "2026-10-16") is False


def test_roll_day_keeps_the_dip_rail_and_resets_dip_s_realized():
    st = {"trading_day": "2026-10-13", "realized_pnl_today_dip": -900.0,
          "dip_rail": {"tripped_on": "2026-10-13", "blocks_until": "2026-10-14", "loss_usd": -900.0}}
    qe._roll_day(st, "2026-10-14")
    assert st["realized_pnl_today_dip"] == 0.0 and st["dip_rail"]["tripped_on"] == "2026-10-13"


def test_dip_s_rail_counts_its_realized_its_fill_shortfall_and_its_marks_only():
    st = {"trading_day": "2026-10-13", "realized_pnl_today": -1000.0, "realized_pnl_today_dip": -600.0,
          "legs": {"DIP_RSI": {"side": "long", "shares_remaining": 6}, "ORB": {"side": "long"}},
          "events": []}
    assert qe._rail_realized_today(st) == -1000.0
    assert qe._rail_realized_today(st, qe.RAIL_SHARED) == -400.0
    assert qe._rail_realized_today(st, qe.DIP_FAMILY) == -600.0
    qe._check_dip_rail(st, {"dip_daily_loss_limit_usd": 800}, {"DIP_RSI": -150.0, "ORB": -999.0},
                       log=NOOP)
    assert st["_dip_rail_input"]["pnl"] == -750.0 and st.get("dip_rail") is None
    qe._check_dip_rail(st, {"dip_daily_loss_limit_usd": 800}, {"DIP_RSI": -250.0}, log=NOOP)
    assert st["dip_rail"]["loss_usd"] == -850.0
    off = {"trading_day": "2026-10-13", "realized_pnl_today_dip": -5000.0, "events": [], "legs": {}}
    qe._check_dip_rail(off, {"dip_daily_loss_limit_usd": 0}, {}, log=NOOP)
    assert off.get("dip_rail") is None, "0 turns DIP's rail off"


# ── the adapter: DIP out of the shared daily P&L and loss check; gross 85 counts DIP ─────────

def test_the_adapter_exempts_dip_from_its_loss_check_but_not_from_the_gross_cap(tmp_path, monkeypatch):
    assert WO.DEFAULT_RAILS["max_total_position_shares"] == 85
    assert WO.DEFAULT_RAILS["own_loss_rail_prefixes"] == ["DIP_"]
    # a box-like config.json that names its own rails keeps the code default prefixes
    p = tmp_path / "wo.json"
    p.write_text(json.dumps({"mode": "PAPER", "rails": {"max_total_position_shares": 80,
                                                        "daily_loss_limit_usd": 400}}), encoding="utf-8")
    box = WO.load_config(str(p))
    assert box["rails"]["max_total_position_shares"] == 80 and box["rails"]["own_loss_rail_prefixes"] == ["DIP_"]
    box["rails"]["own_loss_rail_prefixes"].append("X_")
    assert WO.DEFAULT_RAILS["own_loss_rail_prefixes"] == ["DIP_"], "never the shared default list"

    cfg = _wo_cfg(tmp_path)
    cfg["rails"]["max_total_position_shares"] = 85
    a = WO.OrderAdapter(config=cfg, log=NOOP)
    a._state["daily_pnl"] = -500.0
    ok, why = a._check_rails("ORB", 10, "OPEN")
    assert ok is False and "daily loss limit" in why
    assert a._check_rails("DIP_RSI", 6, "OPEN") == (True, "rails ok")
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["rails"]["own_loss_rail_prefixes"] = []
    c = WO.OrderAdapter(config=cfg2, log=NOOP)
    c._state["daily_pnl"] = -500.0
    assert c._check_rails("DIP_RSI", 6, "OPEN")[0] is False, "[] -> DIP on the shared limit"
    cfg2["rails"]["own_loss_rail_prefixes"] = "DIP_"            # garbage -> the code default
    b = WO.OrderAdapter(config=cfg2, log=NOOP)
    b._state["daily_pnl"] = -500.0
    assert b._check_rails("DIP_RSI", 6, "OPEN")[0] is True

    # gross 85: DIP's 42 + ORB / NOISE / ENGUQ 10 each = 72
    a._state["daily_pnl"] = 0.0
    a._state["believed_positions"] = dict({leg: {"symbol": "QQQ", "qty": 6} for leg in DIP},
                                          ORB={"symbol": "QQQ", "qty": -10},
                                          NOISE={"symbol": "QQQ", "qty": 10},
                                          ENGUQ={"symbol": "QQQ", "qty": 10})
    assert a._check_rails("XLEG", 13, "OPEN") == (True, "rails ok")
    ok, why = a._check_rails("XLEG", 14, "OPEN")
    assert ok is False and "projected total position 86 exceeds max_total_position_shares 85" in why


def test_the_broker_daily_pnl_leaves_dip_out(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(tmp_path / "bo.csv"))
    monkeypatch.setattr(qe, "_now_et", lambda: at(DAY, 11, 0))
    with open(qe.BROKER_ORDERS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        for leg, intent, side, n, px in (("DIP_RSI", "OPEN", "BUY", 6, "700.00"),
                                         ("DIP_RSI", "CLOSE", "SELL", 6, "600.00"),
                                         ("ORB", "OPEN", "BUY", 10, "700.00"),
                                         ("ORB", "CLOSE", "SELL", 10, "690.00")):
            w.writerow({"ts_et": "2026-10-13 10:00:00", "leg": leg, "intent": intent, "side": side,
                        "shares": n, "mode": "PAPER", "ok": "True", "broker_fill_px": px})
    assert qe._broker_realized_today(ds(DAY), log=NOOP) == (-700.0, True)
    assert qe._broker_realized_today(ds(DAY), log=NOOP, family=qe.RAIL_SHARED) == (-100.0, True)

    class _A:
        def status(self):
            return {"open_legs": {"DIP_PB": True, "NOISE": True}}
    st = {"_rail_unrl_by_leg": {"DIP_PB": -300.0, "NOISE": -20.0}}
    assert qe._compute_broker_daily_pnl(st, _A(), log=NOOP) == (-120.0, "broker_fills")
    # no broker row today: the shadow fallback, DIP out as well
    with open(qe.BROKER_ORDERS_CSV, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS).writeheader()
    st.update(realized_pnl_today=-700.0, realized_pnl_today_dip=-600.0, trading_day=ds(DAY))
    assert qe._compute_broker_daily_pnl(st, _A(), log=NOOP) == (-120.0, "shadow_fallback")


# ── KILL sells DIP too: at once in regular hours, at the open outside them ────────────────────

def test_kill_in_regular_hours_sells_every_dip_lot(env):
    e = env
    e.hold_dip(["RSI", "DBL", "PB"])
    e.marks.update(prior_close=700.0, today_open=701.0, today_last=702.0)
    e.tick(at(DAY2, 9, 31))
    start = len(e.fake.sent)
    e.kill(True)
    e.price = e.fake.fill_px = 702.0
    e.tick(at(DAY2, 11, 0))
    assert e.state["legs"] == {} and e.fake.pos == 0
    assert e.sent(start) == [("SELL", 6)] * 3
    assert all(t["exit_reason"].startswith("KILL") for t in e.trades())
    (sold,) = [p for p in e.pushes if p["title"] == "QQQ fill: DIP sold"]
    assert "several DIP lots" in sold["message"] and "(kill switch)" in sold["message"]


@pytest.mark.parametrize("when,opening", [(at(DAY, 20, 0), at(DAY2, 9, 30, 5)),
                                          (at(DAY2, 8, 0), at(DAY2, 9, 30, 5))])
def test_kill_outside_regular_hours_waits_for_the_open_then_sells_dip(env, when, opening):
    e = env
    e.hold_dip(["RSI", "DBL", "PB"])
    start = len(e.fake.sent)
    e.kill(True)
    e.tick(when)
    assert all(e.lot(f"DIP_{s}")["close_pending"]["reason"] == "KILL" for s in ("RSI", "DBL", "PB"))
    assert len(e.fake.sent) == start
    (k,) = e.titled("QQQ book: kill switch on")
    assert "DIP's held shares sell when the market opens" in k["message"] and ntfy_push.lint(k) == []
    e.tick(opening)
    assert e.state["legs"] == {} and e.fake.pos == 0
    assert e.sent(start) == [("SELL", 6)] * 3


# ── a carried DIP exit: ~0 on the rail, its gap in the P&L ─────────────────────────────────────

def test_a_carried_dip_exit_reads_zero_on_the_rail_and_keeps_its_gap(env):
    e = env
    rows = e.hold_dip(["RSI"], px=700.0, close_px=690.0)
    e.marks.update(prior_close=690.0, today_open=680.0, today_last=681.0)
    e.price = 681.0
    e.tick(at(DAY2, 9, 31))
    h = e.lot("DIP_RSI")["hold"]
    assert (h["open_mark_px"], h["close_mark_px"], h["gap_today_usd"]) == (680.0, 690.0, -60.0)
    assert e.state["_dip_rail_input"]["pnl"] == pytest.approx(6.0), "(681 - 680) x 6 from the open"
    e.price = e.fake.fill_px = 680.0
    e.tick(at(DAY2, 9, 35, 10), events=[dip_exit(rows[0], DAY2, 680.0)])
    assert "DIP_RSI" not in e.state["legs"]
    (t,) = e.trades()
    assert float(t["pnl"]) == -120.0, "P&L of record: (680 - 700) x 6, the gap included"
    assert float(t["overnight_gap_usd"]) == -60.0 and t["nights_held"] == "1"
    assert qe._rail_realized_today(e.state, qe.DIP_FAMILY) == pytest.approx(0.0)
    assert e.state["realized_pnl_today_dip"] == -120.0
    assert qe._rail_realized_today(e.state, qe.RAIL_SHARED) == pytest.approx(0.0), "never the shared rail"
    assert e.state["_dip_rail_input"]["pnl"] == pytest.approx(0.0)
    assert e.state.get("dip_rail") is None


# ── EXIT then ENTRY on one slot in one tick ────────────────────────────────────────────────────

def test_exit_then_entry_of_one_slot_in_one_tick(env):
    e = env
    rows = e.hold_dip(["RSI", "PB"])
    e.marks.update(prior_close=700.0, today_open=698.0, today_last=698.0)
    e.price = e.fake.fill_px = 698.0
    start = len(e.fake.sent)
    new = dip_entry("RSI", DAY2, 698.0)
    # the ENTRY row first on purpose: the router frees the slot with its EXIT before the entry
    e.tick(at(DAY2, 9, 35, 10), events=[new, dip_exit(rows[0], DAY2, 698.0)])
    assert e.lot("DIP_RSI")["trade_id"] == new["trade_id"] == "DIP_424-20261014T133000Z-L-RSI"
    assert "hold" not in e.lot("DIP_RSI") and e.lot("DIP_PB")["trade_id"] == rows[1]["trade_id"]
    assert [(s, q) for s, q, _c in e.fake.sent[start:]] == [("SELL", 6), ("BUY", 6)]
    assert [c for _s, _q, c in e.fake.sent[start:]] == ["qxDIP42420261013T133000ZLRC",
                                                         "qxDIP42420261014T133000ZLRO"]
    assert "entry_leg_busy" not in e.issues()
    assert e.books()["DIP_RSI"] == 6 and e.fake.pos == 12
    assert e.adapter.reconcile()["ok"] is True



def test_a_second_entry_on_an_open_slot_is_not_taken_and_says_its_exit_was_missed(env):
    """DISC #119 (3): the 42 cap is 7 x 6, so it could bind only on a SECOND entry in one slot --
    which never reaches it: one lot per slot (one_open_position_per_leg), the new entry is not
    taken (entry_leg_busy), no BUY goes out, and the held lot's missed exit is said once (the
    strategy holds one trade per mechanism, so a new entry means its exit was missed). The held
    trade's own entry replayed next day is refused as another session's."""
    e = env
    rows = e.hold_dip(["RSI"])
    e.marks.update(prior_close=700.0, today_open=700.0, today_last=700.0)
    start = len(e.fake.sent)
    e.tick(at(DAY2, 9, 35, 10), events=[dip_entry("RSI", DAY2, 700.0)])
    assert e.sent(start) == [], "no BUY for a second entry in a held slot"
    assert e.lot("DIP_RSI")["trade_id"] == rows[0]["trade_id"]
    assert "entry_leg_busy" in e.issues() and e.fake.pos == 6 and e.books()["DIP_RSI"] == 6
    assert [ev for ev in e.state["events"] if ev["kind"] == "held_exit_missed"]
    (note,) = e.titled("QQQ book: CHECK NOW")
    assert "DIP" in note["message"] and ntfy_push.lint(note) == []
    assert not [ev for ev in e.state["events"] if ev["kind"] == "dip_cap"], "the cap never binds"
    e.tick(at(DAY2, 9, 40, 10), events=[dict(rows[0])])
    assert e.sent(start) == [] and "entry_other_session" in e.issues(), "yesterday's entry replayed"
    assert len(e.titled("QQQ book: CHECK NOW")) == 1, "one note a day"


def test_a_dip_exit_sells_exactly_its_own_six_while_orb_holds_qqq_the_other_way(env):
    """DISC #119 (6), ONE Webull account: ORB goes short 10 while DIP holds 12 long, so the
    account is net +2. PB's exit must take exactly PB's 6 off the account (SELL 2 + SHORT 4 --
    the netting split), RSI's next exit 6 more (SHORT 6), and ORB's cover lands the account flat.
    Each leg's sent book moves by its own shares only; an EXIT for a slot the book does not hold
    (an absorbed position's, DISC #119 (5)) sends nothing."""
    e = env
    rows = e.hold_dip(["RSI", "PB"])
    e.marks.update(prior_close=700.0, today_open=700.0, today_last=700.0)
    e.price = e.fake.fill_px = 700.0
    start = len(e.fake.sent)
    e.tick(at(DAY2, 10, 5, 10), events=[orb_entry(DAY2, 10, 5, "short", 700.0)])
    assert e.sent(start) == [("SELL", 10)] and e.fake.pos == 2
    assert e.books() == {"DIP_RSI": 6, "DIP_PB": 6, "ORB": -10}
    start = len(e.fake.sent)
    e.tick(at(DAY2, 10, 10, 10), events=[dip_exit(rows[1], DAY2, 700.0)])
    assert e.sent(start) == [("SELL", 2), ("SHORT", 4)], "PB's 6 shares, netted across zero"
    assert e.fake.pos == -4 and "DIP_PB" not in e.state["legs"]
    assert e.books()["DIP_PB"] == 0 and e.books()["DIP_RSI"] == 6 and e.books()["ORB"] == -10
    start = len(e.fake.sent)
    absorbed = dip_entry("DBL", DAY, 700.0)
    e.tick(at(DAY2, 10, 15, 10), events=[dip_exit(rows[0], DAY2, 700.0),
                                         dip_exit(absorbed, DAY2, 700.0)])
    assert e.sent(start) == [("SHORT", 6)], "RSI's 6 only -- nothing for the slot not held"
    assert e.fake.pos == -10 and set(e.state["legs"]) == {"ORB"}
    assert e.books()["DIP_RSI"] == 0 and e.books()["ORB"] == -10
    assert e.adapter.reconcile()["ok"] is True
    start = len(e.fake.sent)
    e.tick(at(DAY2, 15, 59, 5))
    assert e.sent(start) == [("BUY", 10)] and e.fake.pos == 0 and e.state["legs"] == {}
    assert e.adapter.reconcile()["ok"] is True

def test_two_slots_exit_and_one_re_enters_while_its_sell_is_a_webull_duplicate(env, monkeypatch):
    """Two held slots exit at one open and one of them re-enters, with orders still working at
    Webull: RSI's SELL 6 goes, PB's identical SELL 6 is a Webull duplicate (queued), and PB's new
    BUY 6 meets the adapter's one-open-position rule while that old sell is still queued. The buy
    waits for the old sell's re-send and then goes -- Webull ends holding PB's 6, no "entry
    missed" note, the books agree (fixer 10-10: it used to be refused for good, leaving a book-only
    lot that was then held overnight)."""
    e = env
    rows = e.hold_dip(["RSI", "PB"])
    e.marks.update(prior_close=700.0, today_open=698.0, today_last=698.0)
    e.price = e.fake.fill_px = 698.0
    clock = [3_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    e.fake.async_fills = True
    start = len(e.fake.sent)
    new = dip_entry("PB", DAY2, 698.0)
    e.tick(at(DAY2, 9, 35, 10), events=[dip_exit(rows[0], DAY2, 698.0),
                                        dip_exit(rows[1], DAY2, 698.0), new])
    assert e.lot("DIP_PB")["trade_id"] == new["trade_id"] and "DIP_RSI" not in e.state["legs"]
    assert e.sent(start) == [("SELL", 6)] and e.fake.refused == [("SELL", 6, DUP)]
    q = e.state["_broker_resend"]
    assert {k: v["why"] for k, v in q.items()} == {"DIP_PB:CLOSE": "duplicate",
                                                   "DIP_PB:OPEN": "after_close"}
    for i in range(4):
        e.fake.fill_pending()
        clock[0] += 5
        e.tick(at(DAY2, 9, 35, 15 + 5 * i))
    e.fake.fill_pending()
    assert e.sent(start) == [("SELL", 6), ("SELL", 6), ("BUY", 6)], "the old sell, then the buy"
    assert e.state.get("_broker_resend") == {}
    assert e.fake.pos == 6 and e.books()["DIP_PB"] == 6 and e.books()["DIP_RSI"] == 0
    assert not [p for p in e.pushes if "entry missed" in p["title"]]
    assert e.adapter.reconcile()["ok"] is True
    texts = [ev["text"] for ev in e.state["events"]]
    assert any("re-sent and accepted (after its own sell went through)" in t for t in texts)


# ── seven identical BUY 6: Webull's duplicate check, then the one-per-tick re-send queue ───────

@pytest.fixture
def account(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir()
    for attr, fname in (("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv"), ("SERVING_LOCK", "SERVING.lock")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (700.0, "live_stream"))
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        pushes.append({"title": title, "message": msg, "priority": priority}) or True)
    clock = [2_000_000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    monkeypatch.setattr(qe, "_now_et", lambda: at(DAY, 9, 35, 10))
    cfg = _wo_cfg(tmp_path)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    fake = FakeAccount()
    monkeypatch.setattr(adapter, "_build_client", lambda mode: fake)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    return adapter, fake, clock, pushes


def test_seven_identical_buys_meet_the_duplicate_check_and_all_fill_through_the_resend_queue(
        account, tmp_path):
    adapter, fake, clock, pushes = account
    cfg = _qe_cfg(tmp_path)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    fake.async_fills = True
    qe._route_engine_events(state, cfg, [dip_entry(s, DAY, 700.0) for s in SLOTS], False, log=NOOP,
                            now=at(DAY, 9, 35, 10), dip_entries_blocked=False)
    assert set(state["legs"]) == set(DIP), "the book holds all seven"
    assert [(s, q) for s, q, _c in fake.sent] == [("BUY", 6)]
    assert fake.refused == [("BUY", 6, DUP)] * 6
    q = state["_broker_resend"]
    assert list(q) == [f"{leg}:OPEN" for leg in DIP[1:]]
    assert {v["why"] for v in q.values()} == {"duplicate"}

    for i in range(6):                     # each re-send waits for the one before it to fill
        fake.fill_pending()
        clock[0] += 5
        qe._maybe_resend_broker_orders(state, cfg, at(DAY, 9, 35, 15 + 5 * i), True, log=NOOP)
        assert len(fake.sent) == 2 + i, "ONE re-send per tick"
    fake.fill_pending()
    assert fake.refused == [("BUY", 6, DUP)] * 6, "no re-send met a duplicate"
    assert fake.pos == 42 and state.get("_broker_resend") == {}
    assert {leg: p["qty"] for leg, p in adapter._state["broker_sent_positions"].items()} == \
        {leg: 6 for leg in DIP}
    coids = [c for _s, _q, c in fake.sent]
    assert len(set(coids)) == 7
    assert all(c.endswith("R1") and len(c) == 29 for c in coids[1:]), "a fresh, unhashed id"
    assert adapter.reconcile()["ok"] is True
    assert not [p for p in pushes if "entry missed" in p["title"]]
    texts = [ev["text"] for ev in state["events"]]
    assert sum("re-sent and accepted (after a same-instant duplicate)" in t for t in texts) == 6
    assert not any("gave up" in t for t in texts)


def test_several_dip_exits_at_one_open_meet_the_duplicate_check_with_no_false_alarm(account, tmp_path):
    """Three mechanisms exit at one open: three identical SELL 6. The 2nd and 3rd are Webull
    duplicates while the 1st works -- never a "sell is late" note; each goes again a tick later."""
    adapter, fake, clock, pushes = account
    cfg = _qe_cfg(tmp_path)
    state = {"legs": {}, "events": [], "_px_source": "test"}
    rows = [dip_entry(s, DAY, 700.0) for s in ("RSI", "DBL", "PB")]
    qe._route_engine_events(state, cfg, rows, False, log=NOOP, now=at(DAY, 9, 35, 10),
                            dip_entries_blocked=False)
    assert fake.pos == 18
    fake.async_fills = True
    start = len(fake.sent)
    qe._route_engine_events(state, cfg, [dip_exit(r, DAY, 701.0) for r in rows], False, log=NOOP,
                            now=at(DAY, 10, 0, 5), dip_entries_blocked=False)
    assert state["legs"] == {}, "the book closed all three"
    assert [(s, q) for s, q, _c in fake.sent[start:]] == [("SELL", 6)]
    assert fake.refused == [("SELL", 6, DUP)] * 2
    assert {v["why"] for v in state["_broker_resend"].values()} == {"duplicate"}
    for i in range(2):
        fake.fill_pending()
        clock[0] += 5
        qe._maybe_resend_broker_orders(state, cfg, at(DAY, 10, 0, 10 + 5 * i), True, log=NOOP)
    fake.fill_pending()
    assert fake.pos == 0 and state.get("_broker_resend") == {}
    assert {leg: p["qty"] for leg, p in adapter._state["broker_sent_positions"].items()} == \
        {"DIP_RSI": 0, "DIP_DBL": 0, "DIP_PB": 0}
    assert not [p for p in pushes if p["title"] == "QQQ book: CHECK NOW"], "no false alarm"
    (bought,) = [p for p in pushes if p["title"] == "QQQ fill: DIP bought"]
    (sold,) = [p for p in pushes if p["title"] == "QQQ fill: DIP sold"]
    assert "several DIP lots at 701.00 (strategy exit)" in sold["message"]


def test_a_late_dip_exit_of_a_held_lot_is_consumed_through_its_slot(env):
    """The consumer's never-stale rule for a held lot's own exit maps the DIP row to its exec leg
    by the slot -- a 17-hour-old DIP_424 EXIT for the held RSI lot is routed; one for a slot the
    book does not hold, and an old entry, are not."""
    e = env
    rows = e.hold_dip(["RSI"])
    paths = cs.DEFAULT_PATHS
    os.makedirs(paths["state_dir"], exist_ok=True)
    other = dip_entry("DBL", DAY, 700.0)
    sig = [dict(dip_exit(rows[0], DAY, 699.0), emitted_at="2026-10-13 16:00:30"),
           dict(dip_exit(other, DAY, 699.0), emitted_at="2026-10-13 16:00:30"),
           dict(dip_entry("PB", DAY, 700.0), emitted_at="2026-10-13 16:00:30")]
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
        w.writeheader()
        for r in sig:
            w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})
    st = {"legs": e.state["legs"], "engine_cursor": 0, "events": []}
    got = _REAL_CONSUME(st, e.cfg, at(DAY2, 9, 30, 0), log=NOOP)
    assert [(g["leg"], g["event"], g["trade_id"]) for g in got] == \
        [("DIP_424", "EXIT", rows[0]["trade_id"])]


# ── the boot check, orphan repair and after-close check expect DIP lots ───────────────────────

def test_after_close_boot_and_orphan_repair_expect_the_held_dip_lots(env):
    e = env
    e.hold_dip(SLOTS)
    e.state["_last_broker_send_at"] = 0.0            # the post-order grace is wall-clock
    e.tick(at(DAY, 16, 0, 40))
    v = e.state["_webull_flat_after_eod"]
    assert v["flat"] is True and v["held"] == {leg: 6 for leg in DIP}
    assert not e.titled("QQQ book: CHECK NOW")

    e.restart()
    assert e.adapter.reconcile()["ok"] is True
    qe._reconcile_broker_at_boot(log=NOOP)
    assert not e.adapter._halted and not e.titled("QQQ book: CHECK NOW")

    trigger = e.out / "FLATTEN_BROKER"
    trigger.write_text("")
    e.marks.update(prior_close=700.0, today_open=700.0, today_last=700.0)
    sent_before = len(e.fake.sent)
    e.tick(at(DAY2, 9, 35))
    assert len(e.fake.sent) == sent_before and set(e.state["legs"]) == set(DIP)
    assert not trigger.exists(), "no orphan: the repair never sells a held DIP lot"

    # a book that lost its state.json: the boot check names DIP once, plainly
    with open(qe.STATE_PATH, "w", encoding="utf-8") as f:
        f.write("{ torn")
    e._new_adapter()
    qe._reconcile_broker_at_boot(log=NOOP)
    (p,) = e.titled("QQQ book: CHECK NOW")
    assert p["priority"] == "urgent" and ntfy_push.lint(p) == []
    assert "lost DIP's held shares" in p["message"]


def test_a_dip_lot_webull_never_got_is_not_held_overnight(env):
    """A DIP buy the adapter refused (here its gross cap; on the box also a re-send that gave up,
    a lease block, a long reconcile halt) leaves a lot only the book holds. The 15:59 flatten
    closes that lot with the day's other lots -- no sell goes out, Webull never held it -- instead
    of holding it overnight, where it would page "CHECK NOW" every evening and block every deploy
    until its strategy exit (fixer 10-10). The lot Webull does hold stays held."""
    e = env
    e.adapter.cfg["rails"]["max_total_position_shares"] = 6
    e.enter_dip(["RSI", "PB"], DAY, 700.0)
    assert set(e.state["legs"]) == {"DIP_RSI", "DIP_PB"}
    assert e.sent() == [("BUY", 6)] and e.books() == {"DIP_RSI": 6}
    sent_before = len(e.fake.sent)
    e.tick(at(DAY, 15, 59, 5))
    assert e.lot("DIP_RSI")["hold"]["flat_by_day"] == ds(DAY)
    assert "DIP_PB" not in e.state["legs"], "closed at the flatten, not held"
    assert len(e.fake.sent) == sent_before, "no sell: Webull never held it"
    texts = [ev["text"] for ev in e.state["events"]]
    assert any("DIP_PB" in t and "Webull never held" in t for t in texts)
    e.state["_last_broker_send_at"] = 0.0            # the post-order grace is wall-clock
    e.tick(at(DAY, 16, 0, 40))
    v = e.state["_webull_flat_after_eod"]
    assert v["flat"] is True and v["held"] == {"DIP_RSI": 6}
    assert not e.titled("QQQ book: CHECK NOW")


def test_after_close_check_words_a_dip_mismatch_by_family(monkeypatch):
    class _Pos:
        def effective_mode(self):
            return "PAPER", "test"

        def positions(self, account_id=None):
            return {"believed": {}, "broker": {"QQQ": 36.0}, "mode": "PAPER"}
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Pos())
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        pushes.append({"title": title, "message": msg, "priority": priority}) or True)
    state = {"events": [], "legs": {leg: {"leg": leg, "side": "long", "shares_remaining": 6,
                                          "hold": {"since": ds(DAY)}} for leg in DIP}}
    assert qe._check_webull_flat_after_eod(state, log=NOOP) == (False, 36)
    assert state["_eod_flat_off"] == 6
    (p,) = pushes
    assert "6 shares off the DIP trade held overnight" in p["message"] and ntfy_push.lint(p) == []
    assert "DIP long 42 (7 lots)" in state["events"][-1]["text"]


# ── parity: DIP's "open" design gap ───────────────────────────────────────────────────────────

def test_dip_s_open_is_a_design_gap_on_both_sides():
    tid = T.make("DIP_424", _ref(DAY), "long", slot="RSI")
    by_base = qe._broker_orders_by_base([
        {"signal_id": qe._broker_signal_id(None, None, "OPEN", trade_id=tid), "ok": "True",
         "broker_fill_px": "700.30", "shares": "6"},
        {"signal_id": qe._broker_signal_id(None, None, "CLOSE", trade_id=tid), "ok": "True",
         "broker_fill_px": "709.60", "shares": "6"}])
    eng = {"ENTRY": {"px": 700.0, "reason": ""}, "EXIT": {"px": 710.0, "reason": ""}}
    row = {"leg": "DIP_RSI", "side": "long", "trade_id": tid, "entry_px": 700.0, "exit_px": 710.0,
           "exit_reason": "signal exit"}
    op = qe._side_parity(row, "OPEN", by_base, eng)
    assert op["why"] == "open" and op["dsg"] == pytest.approx(-0.30) and op["slp"] == 0.0
    cl = qe._side_parity(row, "CLOSE", by_base, eng)
    assert cl["why"] == "open" and cl["slp"] == 0.0
    eod = qe._side_parity(dict(row, exit_reason="KILL (px: live_stream)"), "CLOSE", by_base, eng)
    assert eod["why"] == "kill", "a rail close keeps its own code"
    assert "open" in qe.DESIGN_ONLY_WHY and "09:30 open" in qe.FP_WHY["open"]


# ── the status doc: families ──────────────────────────────────────────────────────────────────

def test_cum_pnl_adds_dip_s_lots_into_one_family_curve():
    rows = [{"leg": "DIP_RSI", "entry_ts": "2026-10-13 09:35:10", "exit_ts": "2026-10-14 09:35:10", "pnl": "12.0"},
            {"leg": "DIP_PB", "entry_ts": "2026-10-13 09:35:10", "exit_ts": "2026-10-14 09:35:11", "pnl": "-2.0"},
            {"leg": "ORB", "entry_ts": "2026-10-14 10:00:00", "exit_ts": "2026-10-14 11:00:00", "pnl": "5.0"}]
    cum = qe._cum_pnl_by_leg(rows)
    assert set(cum) == {"ORB", "ENGUQ", "NOISE", "DIP", "total"}
    assert cum["DIP"] == [{"date": "2026-10-14", "cum_pnl": 10.0}]
    assert cum["total"] == [{"date": "2026-10-14", "cum_pnl": 15.0}]
    assert not any(k.startswith("DIP_") for k in cum)


def test_the_status_doc_carries_families_and_dip_s_rail(env, monkeypatch):
    e = env
    e.enter_dip(["RSI", "DBL"], DAY, 720.0)
    e.state["dip_rail"] = {"tripped_on": ds(DAY), "blocks_until": ds(DAY2), "loss_usd": -810.0}
    e.px.update({"DIP_RSI": 710.0, "DIP_DBL": 710.0})
    e.tick(at(DAY, 10, 0))
    monkeypatch.setattr(qe, "_build_doc", _REAL_BUILD_DOC)
    for name, fn in (("_trade_parity", lambda row, log=print: {}),
                     ("_load_reprice_sidecar", lambda log=print: {}),
                     ("_engine_prices_by_trade", lambda *a, **k: {}),
                     ("_build_price_status", lambda cfg, state, log=print: {}),
                     ("_build_run_location", lambda: {}),
                     ("_build_ratio_health", lambda state, nowdt, cfg=None, log=print: {}),
                     ("_build_keel_status", lambda log=print: {}),
                     ("_build_equity_status", lambda state, nowdt, log=print: {}),
                     ("_build_shadow_trades", lambda cfg, positions_live=None, log=print: {"trades": []}),
                     ("_live_price_for_leg", lambda leg, log=print: (710.0, 1.0, "live_stream"))):
        monkeypatch.setattr(qe, name, fn)
    doc = qe._build_doc(e.cfg, e.state, False, -120.0, log=NOOP)
    assert doc["leg_families"]["DIP_RSI"] == "DIP" and doc["leg_families"]["ORB"] == "ORB"
    assert set(doc["leg_families"]) == set(qe.LEGS)
    assert doc["positions"]["DIP_RSI"]["family"] == "DIP" and doc["positions"]["DIP_RSI"]["shares"] == 6
    assert {lg["leg"]: lg["family"] for lg in doc["positions_live"]["legs"]} == {"DIP_RSI": "DIP", "DIP_DBL": "DIP"}
    r = doc["rails"]
    assert r["dip_rail"] == {"tripped_on": ds(DAY), "blocks_until": ds(DAY2), "loss_usd": -810.0}
    assert r["dip_max_total_shares"] == 42 and r["dip_daily_loss_limit_usd"] == 800.0
    assert list(r["hold_overnight_legs"]) == ["ENGUQ"] + list(DIP)
    t = doc["today"]
    assert t["dip_rail_input"]["pnl"] == -120.0 and t["unrealized_rail"] == 0.0
    assert t["breaker_input"] == round(t["realized_pnl_rail"] + t["breaker_fill_adj"] + t["unrealized_rail"], 2)
    assert doc["signals_day"][-1]["by_leg"]["DIP"]["taken"] == 2
    assert qe._publish_fingerprint(doc)["dip_rail"] == r["dip_rail"]
    json.dumps(doc, allow_nan=False)
