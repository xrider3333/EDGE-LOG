"""RESTING ORB STOP -- the executor half (api/qqq_exec.py, 2026-09-29, owner GO via MANAGER).

ORB #314's stop (and, opt-in, its 5R target inside ONE native OCO) rests at Webull on the one
netted QQQ paper account the NOISE and ORB legs share. The adapter half (the cancel-first
order gateway, place/cancel/replace/resolve, boot sweep) is tests/test_webull_resting.py; the
engine levels are tests/test_orb_resting_levels.py. This file drives the book end to end --
_route_engine_events -> fill capture -> _maybe_manage_resting -> _close_all -- against a REAL
OrderAdapter in PAPER mode whose client is test_webull_resting.FakeWebullBook: one account on
QQQ with the box rule (417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER), reserved shares, side
validation, market orders that fill on their first lookup, stops/limits triggered by
set_price, cancel lag, cancel/replace races, partial fills and a restart on the same state file.

The 09-28 anchor: ORB short 10 at 732.33 (10:45 bar), buy stop 740.77, breakeven stop 732.33,
target 690.14. No real SDK, network or credentials: tests/conftest.py isolates the live system.
"""
import csv
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import types

import pytest

from api import cloud_signal as cs
from api import qqq_exec as qe
from api import trade_id as T
from api import webull_orders as WO

from test_webull_resting import FakeWebullBook, LIVE

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    NY = None

NOOP = lambda *a, **k: None  # noqa: E731
ORB_REF = "2026-09-28T10:45:00-04:00"
ORB_TID = "ORB_R6-20260928T144500Z-S"
STOP, BE_STOP, TARGET, ENTRY = 740.77, 732.33, 690.14, 732.33


def at(h, m, s=0):
    return datetime.datetime(2026, 9, 28, h, m, s, tzinfo=NY)


class RecordingBook(FakeWebullBook):
    """FakeWebullBook that also records every refused order (the 417s)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.refused = []

    def place_order(self, account_id, new_orders, client_combo_order_id=None):
        try:
            return super().place_order(account_id, new_orders, client_combo_order_id)
        except Exception as e:
            self.refused.append((new_orders[0]["side"], new_orders[0]["order_type"], str(e)))
            raise

    def box_refusals(self):
        return [r for r in self.refused if "OPEN_ORDER_HAS_BOX_ORDER" in r[2]]

    def stops(self, status=None):
        return [o for o in self.orders.values() if o["type"] in ("STOP_LOSS", "LIMIT")
                and (status is None or o["status"] in status)]

    def markets(self):
        return [o for o in self.orders.values() if o["type"] == "MARKET"]


def _wo_cfg(tmp_path):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"].update(session_start="00:00", session_end="23:59",
                        max_shares_per_leg=100, max_total_position_shares=500)
    for k, name in (("state_path", "wo_state.json"), ("paper_keys_path", "paper_keys.json"),
                    ("live_keys_path", "live_keys.json"), ("arm_live_file", "ARM_LIVE"),
                    ("kill_file", "WO_KILL")):
        cfg[k] = str(tmp_path / name)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    return cfg


class Book:
    """The book (qqq_exec state + cfg) wired to a real PAPER OrderAdapter on a fake Webull."""

    def __init__(self, tmp_path, monkeypatch, mode="stop", price=735.0, noise_shares=20):
        self.tmp, self.mp = tmp_path, monkeypatch
        out = tmp_path / "qqq_out"
        out.mkdir(exist_ok=True)
        for attr, fname in (("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                            ("BROKER_ORDERS_CSV", "broker_orders.csv"),
                            ("SERVING_LOCK", "SERVING.lock"), ("STATE_PATH", "state.json"),
                            ("CONFIG_PATH", "config.json")):
            monkeypatch.setattr(qe, attr, str(out / fname))
        monkeypatch.setattr(qe, "OUT_DIR", str(out))
        self.pushes, self.lines = [], []
        monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                            self.pushes.append((msg, priority)))
        monkeypatch.setattr(qe, "BROKER_FILL_CAPTURE_FIRST_DELAY_SEC", 0.0)
        monkeypatch.setattr(qe, "BROKER_FILL_CAPTURE_RETRY_GAP_SEC", 0.0)
        self.px = None   # the live stream's last trade (None = no fresh stream)
        monkeypatch.setattr(qe, "_resting_stream_price", lambda log=print: self.px)
        monkeypatch.setattr(qe, "_exit_price_for_leg",
                            lambda leg, log=print: (self.book.price, "live_stream"))
        monkeypatch.setitem(qe._RESTING_PROCESS, "prev_terminal", False)
        # every tick looks the live order up (the ticks here are 5 s apart on the scripted
        # clock but microseconds apart on the wall clock the cadence reads) -- the cadence
        # itself has its own test; a fresh resting worker record per test
        monkeypatch.setattr(qe, "RESTING_LOOKUP_EVERY_SEC", 0.0)
        monkeypatch.setattr(qe, "_resting_inflight",
                            {"future": None, "what": None, "timed_out_at": 0.0})
        self.book = RecordingBook(price=price)
        self.wo_cfg = _wo_cfg(tmp_path)
        self.adapter = None
        self.restart_adapter()
        monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: self.adapter)
        cfg = json.loads(json.dumps(qe.DEFAULT_CONFIG))
        cfg.update(signal_source="engine", max_shares_per_leg=60, slippage_per_share=0.0,
                   kill_file=str(tmp_path / "KILL"))
        cfg["shares"] = {"ORB": 10, "ENGUQ": 10, "NOISE": noise_shares}
        cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
        cfg["orb_resting"] = {"mode": mode}
        if mode == "stop_target":
            cfg["orb_resting"]["oco_verified"] = True   # the opt-in the mode needs
        self.cfg = cfg
        self.state = qe._default_state()

    def restart_adapter(self):
        self.adapter = WO.OrderAdapter(config=self.wo_cfg, log=self.lines.append)
        self.mp.setattr(self.adapter, "_build_client", lambda m: self.book)
        return self.adapter

    def log(self, *a, **k):
        self.lines.append(" ".join(str(x) for x in a))

    # -- engine rows --
    def route(self, now, *events):
        qe._resting_gateway_step(self.cfg, log=self.log)
        qe._route_engine_events(self.state, self.cfg, list(events), False, log=self.log, now=now)

    def entry(self, now, leg_key, ref_time, px, side, **levels):
        tid = T.make(leg_key, ref_time, side, default_tz=NY)
        e = {"leg": leg_key, "event": "ENTRY", "side": side, "ref_time": ref_time,
             "ref_price": px, "bar_source": "webull", "trade_id": tid, "size": "",
             "keel_size": "", "reason": ""}
        e.update({k: v for k, v in levels.items() if v is not None})
        self.route(now, e)
        return tid

    def orb_entry(self, now=None, stop=STOP, target=TARGET):
        return self.entry(now or at(10, 50, 5), "ORB_R6", ORB_REF, ENTRY, "short",
                          stop_px=stop, target_px=target)

    def exit(self, now, leg_key, tid, px, side, reason=""):
        self.route(now, {"leg": leg_key, "event": "EXIT", "side": side,
                         "ref_time": now.isoformat(), "ref_price": px, "bar_source": "webull",
                         "trade_id": tid, "size": "", "keel_size": "", "reason": reason})

    def levels(self, now, stop=BE_STOP, target=TARGET, tid=ORB_TID):
        self.route(now, {"leg": "ORB_R6", "event": "LEVELS", "side": "short",
                         "ref_time": "2026-09-28T11:05:00-04:00", "ref_price": stop,
                         "bar_source": "webull", "trade_id": tid, "size": "", "keel_size": "",
                         "reason": "breakeven armed", "stop_px": stop, "target_px": target})

    # -- one tick's worth of the resting work (fill capture, then the manager) --
    def tick(self, now, captures=4):
        qe._resting_gateway_step(self.cfg, log=self.log)
        for _ in range(captures):
            qe._maybe_capture_broker_fills(self.state, self.cfg, now, True, log=self.log)
        qe._maybe_manage_resting(self.state, self.cfg, now, True, log=self.log)

    def close_all(self, now, reason="EOD"):
        qe._close_all(self.state, self.cfg, reason, None, None, log=self.log, nowdt=now)

    # -- reads --
    def rows(self):
        try:
            with open(qe.BROKER_ORDERS_CSV, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            return []

    def sent(self, leg):
        return (self.adapter._state.get("broker_sent_positions") or {}).get(leg, {}).get("qty", 0)

    def blk(self):
        return self.state.get("orb_resting") or {}

    def live_stops(self):
        return self.book.stops(status=LIVE)

    def never_held_pushes(self):
        return [m for m, _p in self.pushes if "never held it" in m]


@pytest.fixture
def book(tmp_path, monkeypatch):
    return Book(tmp_path, monkeypatch)


def _armed(b, now=None):
    """ORB short entered and its stop armed (NOISE flat): the 09-28 anchor."""
    b.orb_entry()
    b.tick(now or at(10, 50, 10))
    return b


# ── arming rule ────────────────────────────────────────────────────────────────────

def test_arms_only_after_the_entry_is_filled_at_the_engine_levels(book):
    book.book.market_stuck = True          # Webull has not filled ORB's SHORT yet
    book.orb_entry()
    lot = book.state["legs"]["ORB"]
    assert lot["levels"] == {"stop_px": STOP, "target_px": TARGET, "initial_stop_px": STOP,
                             "be_armed_at": None}
    book.tick(at(10, 50, 10))
    assert book.book.stops() == [], "nothing rests while the entry is not confirmed FILLED"
    assert "not confirmed FILLED" in book.blk()["last"]["text"]
    book.book.market_stuck = False
    book.tick(at(10, 50, 15))
    (stop,) = book.book.stops()
    raw = stop["raw"]
    assert (raw["side"], raw["order_type"], raw["stop_price"], raw["quantity"]) == \
        ("BUY", "STOP_LOSS", "740.77", "10")
    assert (raw["time_in_force"], raw["support_trading_session"], raw["combo_type"]) == \
        ("DAY", "CORE", "NORMAL")
    assert stop["coid"] == "qxORBR620260928T144500ZSP1" and len(stop["coid"]) <= 32
    assert book.blk()["counts"]["armed"] == 1
    # a resting part is never booked on its ack: ORB still counts its -10, nothing else
    assert book.sent("ORB") == -10
    assert book.adapter._state["order_parts"][stop["coid"]]["booked"] == 0


def test_stop_target_mode_rests_one_native_oco(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="stop_target")
    _armed(b)
    legs = sorted((o["type"], o["raw"]["side"], o["combo_type"], o["combo"]) for o in b.book.stops())
    k = "qxORBR620260928T144500ZSK1"
    assert legs == [("LIMIT", "BUY", "OCO", k), ("STOP_LOSS", "BUY", "OCO", k)]
    assert {o["raw"].get("limit_price") or o["raw"].get("stop_price") for o in b.book.stops()} == \
        {"690.14", "740.77"}


def test_book_only_trade_rests_nothing(book):
    book.book.place_raise = [WO_417()]     # Webull refuses ORB's entry outright
    book.orb_entry()
    book.tick(at(10, 50, 10))
    assert book.book.stops() == []
    assert "book-only" in book.blk()["last"]["text"]


def WO_417():
    return Exception("HTTP Status: 417, Code: OPENAPI_SOMETHING, Msg: refused")


@pytest.mark.parametrize("noise,side", [
    (0, "SELL"), (20, "SELL"), (-10, "SHORT"), (-20, "SHORT"), (-5, None), (-7, None)])
def test_side_follows_the_account_net_and_never_crosses_zero(tmp_path, monkeypatch, noise, side):
    """ORB LONG 10 on NOISE 0 / +20 / -10 / -20 rests SELL / SELL / SHORT / SHORT; on -5 and
    -7 (account +5 / +3) a resting order would cross zero: nothing rests, one event."""
    b = Book(tmp_path, monkeypatch, noise_shares=abs(noise) or 20)
    if noise:
        b.entry(at(10, 0, 5), "NOISE_382", "2026-09-28T10:00:00-04:00", 700.0,
                "long" if noise > 0 else "short")
        b.tick(at(10, 0, 10))
    b.entry(at(10, 50, 5), "ORB_R6", ORB_REF, 700.0, "long", stop_px=690.0, target_px=740.0)
    b.tick(at(10, 50, 10))
    b.tick(at(10, 50, 15))
    assert b.sent("ORB") == 10 and b.sent("NOISE") == noise
    stops = b.book.stops()
    if side is None:
        assert stops == []
        assert b.blk()["counts"]["crossing"] == 1
        assert sum("would cross zero" in e["text"] for e in b.state["events"]) == 1
    else:
        assert [(o["raw"]["side"], o["qty"], o["raw"]["stop_price"]) for o in stops] == \
            [(side, 10, "690.00")]
    assert b.book.refused == []


def test_live_price_already_through_the_stop_sends_the_market_close(book):
    book.orb_entry()
    book.px = 741.20                       # the tape already traded through 740.77
    book.tick(at(10, 50, 10))
    assert book.book.stops() == []
    closes = [o for o in book.book.markets() if o["raw"]["side"] == "BUY"]
    assert len(closes) == 1 and closes[0]["qty"] == 10
    assert book.state["legs"]["ORB"]["broker_closed"]["by"] == "market"
    row = book.rows()[-1]
    assert (row["intent"], row["signal_id"], row["shadow_px"]) == \
        ("CLOSE", "qxORBR620260928T144500ZSC", "740.77")
    # the engine's own EXIT later closes the book with no second order and no misleading push
    book.book.step()
    book.exit(at(10, 55, 5), "ORB_R6", ORB_TID, STOP, "short")
    assert len([o for o in book.book.markets() if o["raw"]["side"] == "BUY"]) == 1
    assert "ORB" not in book.state["legs"] and book.never_held_pushes() == []


def test_no_arm_in_the_last_minute_before_flat_by(book):
    book.orb_entry(now=at(15, 57, 50))
    book.tick(at(15, 58, 5))               # flat_by 15:59 -> nothing arms from 15:58
    assert book.book.stops() == []
    assert "outside the arming window" in book.blk()["last"]["text"]


def test_three_failed_tries_then_one_push_and_the_engine_exit(book, monkeypatch):
    book.orb_entry()
    book.tick(at(10, 50, 10))
    book.book.orders.clear()               # (start over with a refusing Webull)
    book.adapter._state.pop("resting", None)
    book.adapter._state["order_parts"] = {k: v for k, v in book.adapter._state["order_parts"].items()
                                          if not v.get("resting")}
    calls = []

    def refuse(*a, **k):
        calls.append(1)
        return {"ok": False, "sent": True, "outcome": "REFUSED", "reason": "417 test refusal"}
    monkeypatch.setattr(book.adapter, "place_resting", refuse)
    clock = [1000.0]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    for i in range(8):
        book.tick(at(10, 51, i))
        clock[0] += 30.0
    assert len(calls) == 3
    assert book.blk()["counts"]["fallback"] == 1
    assert sum("could not be placed after 3 tries" in m for m, _ in book.pushes) == 1


# ── the gateway: cancel first, re-arm with the new side ────────────────────────────

def test_gateway_cancels_before_a_noise_order_and_rearms_with_the_new_side(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch)
    b.entry(at(10, 50, 5), "ORB_R6", ORB_REF, 700.0, "long", stop_px=690.0, target_px=740.0)
    b.tick(at(10, 50, 10))
    (first,) = b.live_stops()
    assert first["raw"]["side"] == "SELL"
    b.entry(at(11, 0, 5), "NOISE_382", "2026-09-28T11:00:00-04:00", 700.0, "short")  # SHORT 20
    assert first["status"] == "CANCELLED", "cancelled and confirmed before NOISE was planned"
    assert b.book.refused == []
    b.tick(at(11, 0, 10))
    b.tick(at(11, 0, 15))
    (second,) = b.live_stops()
    assert (second["raw"]["side"], second["qty"], second["coid"][-2:]) == ("SHORT", 10, "P2")
    assert first["coid"] != second["coid"] and len(second["coid"]) <= 32
    assert b.blk()["counts"]["rearmed"] == 1
    assert b.sent("NOISE") == -20 and b.sent("ORB") == 10


def test_cancel_race_the_stop_fills_during_the_cancel_and_noise_is_replanned(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.cancel_fills.add(stop["coid"])            # it fills as the cancel arrives
    tid = book.entry(at(11, 0, 5), "NOISE_382", "2026-09-28T11:00:00-04:00", 700.0, "long")
    assert book.book.refused == []
    assert book.sent("ORB") == 0
    # NOISE's BUY 20 was planned on the account AFTER the stop's BUY 10 cover: opening only
    assert [(o["raw"]["side"], o["qty"]) for o in book.book.markets()][-1] == ("BUY", 20)
    book.tick(at(11, 0, 10))
    fill = [r for r in book.rows() if r["client_order_id"] == stop["coid"]]
    assert len(fill) == 1
    assert (fill[0]["intent"], fill[0]["signal_id"], fill[0]["shares"], fill[0]["shadow_px"],
            fill[0]["reason"]) == ("CLOSE", "qxORBR620260928T144500ZSC", "10", "740.77",
                                   "resting stop filled at Webull")
    assert book.state["legs"]["ORB"]["broker_closed"]["id"] == stop["coid"]
    assert tid and book.book.stops(status=LIVE) == []


def test_cancel_unknown_nothing_is_sent_open_requeued_close_goes_to_close_retry(book):
    _armed(book)
    noise_tid = None
    book.book.detail_down = True                       # no lookup answers: cancel unconfirmed
    n_before = len(book.book.markets())
    noise_tid = book.entry(at(11, 0, 5), "NOISE_382", "2026-09-28T11:00:00-04:00", 700.0, "long")
    assert len(book.book.markets()) == n_before, "NOISE's OPEN was not sent"
    q = book.state["_broker_resend"]
    assert q["NOISE:OPEN"]["why"] == "busy"
    # the engine exit of ORB while the cancel is still unconfirmed -> close_retry
    book.exit(at(11, 1, 5), "ORB_R6", ORB_TID, 735.0, "short")
    assert len(book.book.markets()) == n_before
    assert q[f"ORB:CLOSE:{ORB_TID}"]["why"] == "close_retry"
    assert noise_tid and book.book.refused == []


def test_busy_open_is_resent_once_the_gateway_clears(book):
    _armed(book)
    book.book.detail_down = True
    book.entry(at(11, 0, 5), "NOISE_382", "2026-09-28T11:00:00-04:00", 700.0, "long")
    book.book.detail_down = False
    item = book.state["_broker_resend"]["NOISE:OPEN"]
    item["last_at"] = 0.0
    qe._maybe_resend_broker_orders(book.state, book.cfg, at(11, 0, 20), True, log=book.log)
    assert "NOISE:OPEN" not in book.state["_broker_resend"]
    assert book.sent("NOISE") == 20 and book.book.refused == []


# ── engine EXIT ────────────────────────────────────────────────────────────────────

def test_engine_exit_with_the_stop_live_cancels_then_sends_the_market_close(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.exit(at(11, 30, 5), "ORB_R6", ORB_TID, 720.0, "short")
    assert stop["status"] == "CANCELLED"
    assert book.book.markets()[-1]["raw"]["side"] == "BUY" and book.book.markets()[-1]["qty"] == 10
    assert book.rows()[-1]["signal_id"] == "qxORBR620260928T144500ZSC"
    assert book.rows()[-1]["client_order_id"] == "qxORBR620260928T144500ZSC"
    assert book.never_held_pushes() == []


def test_engine_exit_after_the_stop_filled_sends_nothing_and_no_never_held_push(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.set_price(741.0)                         # Webull's tape hits 740.77
    book.tick(at(10, 55, 5))                           # the per-tick lookup finds the fill
    assert stop["status"] == "FILLED" and book.sent("ORB") == 0
    n_markets = len(book.book.markets())
    book.exit(at(10, 55, 10), "ORB_R6", ORB_TID, STOP, "short")
    assert len(book.book.markets()) == n_markets, "no market close"
    assert book.never_held_pushes() == []
    assert "ORB" not in book.state["legs"]
    closes = [r for r in book.rows() if r["intent"] == "CLOSE"]
    assert len(closes) == 1 and closes[0]["broker_fill_px"] == "741.0"


def test_engine_exit_finds_the_fill_through_the_gateway(book):
    """The stop filled between two lookups; the engine EXIT's gateway finds it: no market
    close, no push, and the fill row lands on the next manager pass."""
    _armed(book)
    book.book.set_price(741.0)
    n_markets = len(book.book.markets())
    book.exit(at(10, 55, 10), "ORB_R6", ORB_TID, STOP, "short")
    assert len(book.book.markets()) == n_markets and book.never_held_pushes() == []
    book.tick(at(10, 55, 15))
    assert [r["client_order_id"] for r in book.rows() if r["intent"] == "CLOSE"] == \
        ["qxORBR620260928T144500ZSP1"]


# ── breakeven ──────────────────────────────────────────────────────────────────────

def test_breakeven_levels_row_moves_the_resting_stop_in_place(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.levels(at(11, 10, 5))
    assert book.state["legs"]["ORB"]["levels"]["stop_px"] == BE_STOP
    book.tick(at(11, 10, 10))
    assert ("replace", [stop["coid"]]) in book.book.calls
    assert stop["stop"] == BE_STOP and stop["status"] == "SUBMITTED"
    assert book.blk()["counts"]["replaced"] == 1
    assert len(book.book.stops()) == 1


def test_breakeven_replace_race_books_the_fill_and_places_nothing(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.replace_fills.add(stop["coid"])
    book.levels(at(11, 10, 5))
    book.tick(at(11, 10, 10))
    assert stop["status"] == "FILLED" and len(book.book.stops()) == 1
    assert book.sent("ORB") == 0
    assert book.state["legs"]["ORB"]["broker_closed"]["id"] == stop["coid"]


def test_breakeven_already_crossed_sends_the_market_close(book):
    _armed(book)
    book.levels(at(11, 10, 5))
    book.px = 733.0                                    # already above the new 732.33 buy stop
    book.tick(at(11, 10, 10))
    assert book.book.markets()[-1]["raw"]["side"] == "BUY"
    assert book.live_stops() == [] and book.sent("ORB") == 0


# ── OCO fills ──────────────────────────────────────────────────────────────────────

def test_oco_single_fill_cancels_the_sibling(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="stop_target")
    _armed(b)
    b.book.set_price(690.0)                            # the 690.14 target fills
    b.tick(at(12, 0, 5))
    b.tick(at(12, 0, 10))
    b.tick(at(12, 0, 15))
    kinds = {o["type"]: o["status"] for o in b.book.stops()}
    assert kinds == {"LIMIT": "FILLED", "STOP_LOSS": "CANCELLED"}
    row = [r for r in b.rows() if r["intent"] == "CLOSE"][-1]
    assert (row["reason"], row["shadow_px"]) == ("resting target filled at Webull", "690.14")
    assert b.state["legs"]["ORB"]["broker_closed"]["by"] == "resting target"


def test_oco_partial_target_fill_rearms_the_remainder(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="stop_target")
    _armed(b)
    tgt = next(o for o in b.book.stops() if o["type"] == "LIMIT")
    b.book.partial[tgt["coid"]] = 4
    b.book.set_price(690.0)
    for s in range(0, 30, 5):
        b.tick(at(12, 0, s))
    assert b.sent("ORB") == -6
    live = b.live_stops()
    assert sorted((o["type"], o["qty"]) for o in live) == [("LIMIT", 6), ("STOP_LOSS", 6)]
    assert [r["shares"] for r in b.rows() if r["reason"].startswith("resting target")] == ["4"]
    assert "broker_closed" not in b.state["legs"]["ORB"]


# ── end of day, KILL, breaker ──────────────────────────────────────────────────────

def test_eod_flatten_cancels_before_the_net_order(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.calls.clear()
    book.close_all(at(15, 59, 1))
    kinds = [m for m, _ in book.book.calls if m in ("cancel", "place")]
    assert kinds[0] == "cancel" and "place" in kinds and kinds.index("place") > 0
    assert stop["status"] == "CANCELLED"
    assert book.sent("ORB") == 0 and "ORB" not in book.state["legs"]


def test_kill_file_cancels_the_resting_stop_and_nothing_rearms(book):
    _armed(book)
    (stop,) = book.live_stops()
    open(book.cfg["kill_file"], "w").close()
    book.tick(at(11, 0, 5))
    assert stop["status"] == "CANCELLED" and book.live_stops() == []
    book.tick(at(11, 0, 10))
    assert book.live_stops() == [] and "KILL" in book.blk()["last"]["text"]


def test_breaker_flatten_cancels_first_and_blocks_rearming(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.state["breaker_tripped"] = True
    book.close_all(at(11, 0, 5), reason="BREAKER")
    assert stop["status"] == "CANCELLED"
    book.orb_entry(now=at(11, 5, 5))     # even a fresh lot never arms while tripped
    book.tick(at(11, 5, 10))
    assert book.live_stops() == []


# ── reconcile ──────────────────────────────────────────────────────────────────────

def test_reconcile_books_a_resting_fill_without_a_halt(book):
    _armed(book)
    book.book.set_price(741.0)
    book.state["_last_broker_reconcile_at"] = 0.0
    book.state["_reconcile_due"] = False                # the periodic look, not the grace
    qe._maybe_run_broker_reconcile(book.state, book.cfg, book.adapter, at(10, 56), True,
                                   log=book.log)
    assert book.adapter._state.get("last_reconcile_at"), "the reconcile ran"
    assert book.adapter.halt_state()[0] is False
    assert book.sent("ORB") == 0, "its resting pass booked the fill before reading positions"
    book.tick(at(10, 56, 5))
    assert [r["client_order_id"] for r in book.rows() if r["intent"] == "CLOSE"] == \
        ["qxORBR620260928T144500ZSP1"]


def test_a_real_mismatch_cancels_the_resting_stop_and_blocks_rearming(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.pos += 7                                  # shares nobody in the book knows
    book.state["_last_broker_reconcile_at"] = 0.0
    book.state["_reconcile_due"] = False                # the periodic look, not the grace
    qe._maybe_run_broker_reconcile(book.state, book.cfg, book.adapter, at(10, 56), True,
                                   log=book.log)
    assert book.adapter.halt_state()[0] is True
    for s in range(5, 30, 5):
        book.tick(at(10, 56, s))
    assert stop["status"] == "CANCELLED"
    assert book.live_stops() == [] and len(book.book.stops()) == 1


# ── restart ────────────────────────────────────────────────────────────────────────

def test_restart_keeps_a_live_stop_and_the_first_tick_reverifies_it(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.restart_adapter()
    qe._reconcile_broker_at_boot(log=book.log)
    assert stop["status"] == "SUBMITTED"
    book.tick(at(11, 0, 5))
    assert book.live_stops() == [stop] and len(book.book.stops()) == 1


def test_restart_after_the_stop_filled_while_down_books_the_fill(book):
    _armed(book)
    book.book.set_price(741.0)
    book.restart_adapter()
    qe._reconcile_broker_at_boot(log=book.log)
    assert book.adapter.halt_state()[0] is False
    book.tick(at(11, 0, 5))
    assert [r["client_order_id"] for r in book.rows() if r["intent"] == "CLOSE"] == \
        ["qxORBR620260928T144500ZSP1"]
    assert book.state["legs"]["ORB"]["broker_closed"]["by"] == "resting stop"


def test_restart_cancels_an_unknown_open_order_halts_and_pushes(book):
    _armed(book)
    book.book.orders["qxFOREIGN1"] = dict(book.live_stops()[0], coid="qxFOREIGN1",
                                          raw={}, cancel_at=None)
    book.restart_adapter()
    qe._reconcile_broker_at_boot(log=book.log)
    assert book.book.orders["qxFOREIGN1"]["status"] == "CANCELLED"
    assert any("did not know" in m for m, _ in book.pushes)
    # the sweep halts entries (source "reconcile"); the boot reconcile right after it reads
    # the books and Webull agreeing again, and lifts it -- a disagreement would keep it
    assert any("entries halted until a reconcile agrees" in ln for ln in book.lines)
    assert book.adapter._state.get("last_reconcile_result", {}).get("ok") is True
    assert book.live_stops()[0]["coid"] == "qxORBR620260928T144500ZSP1"


# ── the fill row: parity and the Webull P&L of record ──────────────────────────────

def test_resting_fill_row_keeps_parity_and_the_daily_realized(book):
    _armed(book)
    book.book.set_price(741.0)
    book.tick(at(10, 55, 5))
    rows = book.rows()
    by_base = qe._broker_orders_by_base(rows)
    close = qe._broker_order_for(ORB_TID, "CLOSE", by_base)
    assert close["client_order_id"] == "qxORBR620260928T144500ZSP1"
    assert close["broker_fill_px"] == "741.0"
    opened = qe._broker_order_for(ORB_TID, "OPEN", by_base)
    today = qe._now_et().strftime("%Y-%m-%d")
    realized, priced = qe._broker_realized_today(today, log=NOOP)
    open_px = float(opened["broker_fill_px"] or opened["shadow_px"])
    assert realized == pytest.approx(round((open_px - 741.0) * 10, 2))
    fill, st, _ = qe._webull_fill_for_side({"trade_id": ORB_TID}, "CLOSE", by_base)
    assert (fill, st) == (741.0, "ok")


# ── the 09-28 pair: ORB short + NOISE orders, never a 417 with the gateway on ─────

def _pair_session(b):
    noise = b.entry(at(10, 0, 5), "NOISE_382", "2026-09-28T10:00:00-04:00", 700.0, "long")
    b.tick(at(10, 0, 10))
    b.orb_entry()
    b.tick(at(10, 50, 10))
    b.tick(at(10, 50, 15))
    b.exit(at(11, 30, 5), "NOISE_382", noise, 701.0, "long")        # SELL 20 through zero
    b.tick(at(11, 30, 10))
    b.tick(at(11, 30, 15))
    b.entry(at(14, 0, 5), "NOISE_382", "2026-09-28T14:00:00-04:00", 702.0, "long")  # BUY 20
    b.tick(at(14, 0, 10))
    b.tick(at(14, 0, 15))
    b.close_all(at(15, 59, 1))
    return b


def test_0928_pair_never_gets_a_417_with_the_gateway_on(book):
    _pair_session(book)
    assert book.book.refused == []
    assert book.blk()["counts"]["armed"] == 1 and book.blk()["counts"]["rearmed"] >= 2
    book.book.step()                                   # the flatten's market orders fill
    assert book.book.pos == 0 and book.sent("ORB") == 0 and book.sent("NOISE") == 0
    assert book.live_stops() == []


def test_0928_pair_gets_the_box_order_417_with_the_gateway_off(book, monkeypatch):
    monkeypatch.setattr(WO.OrderAdapter, "_order_gateway", lambda self, *a, **k: None)
    _pair_session(book)
    assert book.book.box_refusals(), "without cancel-first, Webull's box rule refuses"


# ── log_only: decide and publish, send nothing ─────────────────────────────────────

def test_log_only_logs_and_publishes_every_decision_and_sends_nothing(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="log_only")
    _pair_session_log_only(b)
    assert b.book.stops() == [], "no resting order is ever sent"
    assert [m for m, _ in b.book.calls if m in ("cancel", "replace")] == []
    assert not any(isinstance(c, list) and any(str(i).endswith(("P1", "K1")) for i in c)
                   for _m, c in b.book.calls)
    counts = b.blk()["counts"]
    assert counts["armed"] == 1 and counts["rearmed"] >= 1 and counts["replaced"] == 1
    assert counts["cancelled"] >= 1
    texts = [e["text"] for e in b.state["events"] if e["kind"] == "orb_resting"]
    assert any("would rest BUY 10 QQQ stop 740.77" in t for t in texts)
    assert any("would move the resting stop 740.77 -> 732.33" in t for t in texts)
    assert any("would cancel and confirm" in t and "EOD flatten" in t for t in texts)
    status = qe._build_resting_status(b.cfg, b.state)
    assert status["mode"] == "log_only" and status["counts"] == counts
    json.dumps(status)
    assert b.adapter._prev_terminal_on() is False


def _pair_session_log_only(b):
    noise = b.entry(at(10, 0, 5), "NOISE_382", "2026-09-28T10:00:00-04:00", 700.0, "long")
    b.tick(at(10, 0, 10))
    b.orb_entry()
    b.tick(at(10, 50, 10))
    b.tick(at(10, 50, 15))
    b.levels(at(11, 10, 5))
    b.tick(at(11, 10, 10))
    b.exit(at(11, 30, 5), "NOISE_382", noise, 701.0, "long")
    b.tick(at(11, 30, 10))
    b.tick(at(11, 30, 15))
    b.close_all(at(15, 59, 1))


def test_switching_back_to_log_only_cancels_what_still_rests(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.cfg["orb_resting"] = {"mode": "log_only"}
    book.tick(at(11, 0, 5))
    assert stop["status"] == "CANCELLED"
    assert book.adapter._prev_terminal_on() is False


# ── off: today's behaviour, byte for byte ──────────────────────────────────────────

_RESTING_METHODS = ("resting_orders", "resting_plan", "order_parts", "place_resting",
                    "cancel_resting", "replace_resting", "resolve_resting",
                    "take_resting_events", "boot_sweep", "set_prev_terminal")


class _Clock:
    """A scripted wall clock for both modules (time.time) and qqq_exec's _now_et."""

    def __init__(self):
        self.now = at(9, 50)

    def time(self):
        return self.now.timestamp()

    def sleep(self, s):
        pass

    def monotonic(self):
        return self.now.timestamp()


def _session_rows(orb_levels=True):
    """(tick time, [signals.csv rows so far]) for a scripted day: NOISE long, ORB short with
    engine levels and a breakeven LEVELS row, NOISE exit, then the 15:59 flatten."""
    orb_tid, noise_tid = ORB_TID, "NOISE_382-20260928T140000Z-L"

    def row(emitted, leg, event, side, ref, px, tid, reason="", stop="", target=""):
        return {"emitted_at": emitted, "leg": leg, "event": event, "side": side,
                "ref_time": ref, "ref_price": px, "shares": 135, "reason": reason,
                "bar_source": "webull", "trade_id": tid,
                "stop_px": stop if orb_levels else "", "target_px": target if orb_levels else ""}
    rows = [row("2026-09-28T10:00:05-04:00", "NOISE_382", "ENTRY", "long",
                "2026-09-28T10:00:00-04:00", 736.0, noise_tid),
            row("2026-09-28T10:50:05-04:00", "ORB_R6", "ENTRY", "short", ORB_REF, ENTRY, orb_tid,
                stop=STOP, target=TARGET)]
    levels = row("2026-09-28T11:10:05-04:00", "ORB_R6", "LEVELS", "short",
                 "2026-09-28T11:05:00-04:00", BE_STOP, orb_tid, reason="breakeven armed",
                 stop=BE_STOP, target=TARGET)
    rows_l = rows + ([levels] if orb_levels else [])
    exit_n = row("2026-09-28T11:30:05-04:00", "NOISE_382", "EXIT", "long",
                 "2026-09-28T11:30:00-04:00", 737.0, noise_tid)
    return [(at(9, 50), []), (at(10, 0, 6), rows[:1]), (at(10, 0, 11), rows[:1]),
            (at(10, 50, 6), rows), (at(10, 50, 11), rows), (at(10, 50, 16), rows),
            (at(11, 10, 6), rows_l), (at(11, 10, 11), rows_l),
            (at(11, 30, 6), rows_l + [exit_n]), (at(11, 30, 11), rows_l + [exit_n]),
            (at(15, 59, 1), rows_l + [exit_n]), (at(16, 1), rows_l + [exit_n])]


def run_scripted_session(mod, tmp_path, monkeypatch, mode="off", orb_levels=True, spy=None,
                         wo=WO, fake=None, on_tick=None):
    """Drive `mod.tick()` (api/qqq_exec.py, or a baseline copy of it) through the scripted
    day against a PAPER adapter on FakeWebullBook (or `fake`); return every output the book
    writes. `on_tick(i, now, fake, wall_sec)` runs after each tick."""
    home = tmp_path / "home"
    out = home / "qqq_exec"
    out.mkdir(parents=True)
    for attr, fname in (("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv"), ("SERVING_LOCK", "SERVING.lock"),
                        ("STATE_PATH", "state.json"), ("CONFIG_PATH", "config.json")):
        monkeypatch.setattr(mod, attr, str(out / fname))
    monkeypatch.setattr(mod, "OUT_DIR", str(out))
    paths = cs._paths(home=str(home / "cs"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    os.makedirs(paths["state_dir"], exist_ok=True)
    clock = _Clock()
    fake_time = types.SimpleNamespace(time=clock.time, sleep=clock.sleep,
                                      monotonic=clock.monotonic, perf_counter=clock.monotonic)
    monkeypatch.setattr(mod, "time", fake_time)
    monkeypatch.setattr(wo, "time", fake_time)
    monkeypatch.setattr(mod, "_now_et", lambda: clock.now)
    # process-level memory starts fresh for each module, whatever ran earlier in this process
    monkeypatch.setattr(mod, "_PROCESS", {"booted": False})
    monkeypatch.setattr(mod, "_BREAKER_ADJ_CACHE", {"key": None, "val": 0.0})
    monkeypatch.setattr(mod, "_ENGINE_PX_CACHE", {"key": None, "val": {}})
    if hasattr(mod, "_resting_inflight"):   # its timeout stamp is read on the scripted clock
        monkeypatch.setattr(mod, "_resting_inflight",
                            {"future": None, "what": None, "timed_out_at": 0.0})
    monkeypatch.setattr(mod, "_notify", NOOP)
    monkeypatch.setattr(mod, "_exit_price_for_leg", lambda leg, log=print: (736.58, "live_stream"))
    monkeypatch.setattr(mod, "_engine_mark_price", lambda leg, log=print: (736.58, "engine_cache"))
    monkeypatch.setattr(mod, "_maybe_run_reprice", NOOP)
    monkeypatch.setattr(mod, "_maybe_send_eod_summary", NOOP)
    monkeypatch.setattr(mod, "_maybe_read_account_equity", NOOP)
    monkeypatch.setattr(mod, "BROKER_FILL_CAPTURE_FIRST_DELAY_SEC", 0.0)
    monkeypatch.setattr(mod, "BROKER_FILL_CAPTURE_RETRY_GAP_SEC", 0.0)
    fake = fake or FakeWebullBook(price=736.58)
    wo_cfg = _wo_cfg(tmp_path)
    adapter = wo.OrderAdapter(config=wo_cfg, log=NOOP)
    monkeypatch.setattr(adapter, "_build_client", lambda m: fake)
    if spy is not None:
        for name in _RESTING_METHODS:
            real = getattr(adapter, name)

            def wrapped(*a, _n=name, _r=real, **k):
                spy.append(_n)
                return _r(*a, **k)
            monkeypatch.setattr(adapter, name, wrapped)
    monkeypatch.setattr(mod, "_get_broker_adapter", lambda log=print: adapter)
    cfg = json.loads(json.dumps(mod.DEFAULT_CONFIG))
    cfg.update(signal_source="engine", max_shares_per_leg=60, slippage_per_share=0.0,
               kill_file=str(tmp_path / "KILL"), daily_loss_limit_usd=5000)
    cfg["shares"] = {"ORB": 10, "ENGUQ": 10, "NOISE": 20}
    cfg["session"] = {"open": "09:31", "last_entry": "15:55", "flat_by": "15:59"}
    if mode is None:
        cfg.pop("orb_resting", None)
    else:
        cfg["orb_resting"] = {"mode": mode}
    state = mod._default_state()
    docs = []
    for i, (now, rows) in enumerate(_session_rows(orb_levels=orb_levels)):
        clock.now = now
        with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})
        with open(paths["heartbeat_path"], "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.datetime.now(NY).isoformat(), "ok": True}, f)
        t0 = time.monotonic()
        _c, state, doc = mod.tick(cfg=cfg, state=state, now=now, quote_fn=NOOP, ratio_fn=NOOP,
                                  log=NOOP)
        if on_tick is not None:
            on_tick(i, now, fake, time.monotonic() - t0)
        docs.append(json.loads(json.dumps(doc, default=str)))

    def read(p):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None
    return {"orders.csv": read(mod.ORDERS_CSV), "trades.csv": read(mod.TRADES_CSV),
            "broker_orders.csv": read(mod.BROKER_ORDERS_CSV), "state.json": read(mod.STATE_PATH),
            "adapter_state.json": read(wo_cfg["state_path"]), "docs": docs,
            "book": sorted((o["coid"], o["type"], o["side"], o["qty"], o["status"])
                           for o in fake.orders.values()), "state": state}


def test_off_mode_never_touches_a_resting_path(tmp_path, monkeypatch):
    spy = []
    out = run_scripted_session(qe, tmp_path, monkeypatch, mode="off", spy=spy)
    assert spy == [], f"'off' asked the adapter for {sorted(set(spy))}"
    assert all(t == "MARKET" for _c, t, *_ in out["book"]), "no resting order at Webull"
    assert "orb_resting" not in out["state"]
    assert all("orb_resting" not in d for d in out["docs"])
    assert "levels" not in out["state"].get("legs", {}).get("ORB", {})
    assert '"levels"' not in out["state.json"] and "orb_resting" not in out["state.json"]
    assert "orb_resting" not in json.dumps(out["docs"])
    # the book really traded: NOISE round trip, ORB flattened at 15:59
    assert "NOISE" in out["trades.csv"] and "ORB" in out["trades.csv"]


def test_off_mode_ignores_the_engine_levels_entirely(tmp_path, monkeypatch):
    """A ledger carrying stop_px/target_px and a LEVELS row produces byte-identical outputs
    in 'off' to one with neither -- what this book did before the resting build."""
    a = run_scripted_session(qe, tmp_path / "a", monkeypatch, mode="off", orb_levels=True)
    b = run_scripted_session(qe, tmp_path / "b", monkeypatch, mode="off", orb_levels=False)
    # the only difference allowed: the row cursor counts the one extra (LEVELS) ledger row
    for out in (a, b):
        st = json.loads(out["state.json"])
        st.pop("engine_cursor", None)
        out["state.json"] = json.dumps(st, sort_keys=True)
    for k in ("orders.csv", "trades.csv", "broker_orders.csv", "state.json",
              "adapter_state.json", "book"):
        assert _scrub(a[k]) == _scrub(b[k]), k
    assert [_scrub_doc(d) for d in a["docs"]] == [_scrub_doc(d) for d in b["docs"]]


def test_log_only_sends_exactly_what_off_sends(tmp_path, monkeypatch):
    """The whole scripted day through tick(): log_only's order flow (every CSV row, the
    adapter's state, every order Webull saw) is byte-identical to 'off' -- it only adds its
    decisions to the book's own state and the published status block."""
    off = run_scripted_session(qe, tmp_path / "off", monkeypatch, mode="off")
    lo = run_scripted_session(qe, tmp_path / "lo", monkeypatch, mode="log_only")
    for k in ("orders.csv", "trades.csv", "broker_orders.csv", "adapter_state.json", "book"):
        assert _scrub(off[k]) == _scrub(lo[k]), k
    assert all(t == "MARKET" for _c, t, *_ in lo["book"])
    status = lo["docs"][-2]["orb_resting"]
    assert status["mode"] == "log_only" and status["counts"]["armed"] == 1
    assert status["counts"]["replaced"] == 1 and status["counts"]["cancelled"] >= 1
    texts = [e["text"] for e in lo["state"]["events"] if e["kind"] == "orb_resting"]
    assert any("would rest BUY 10 QQQ stop 740.77" in t for t in texts)
    assert any("before the EOD flatten" in t for t in texts)
    assert "orb_resting" not in off["docs"][-1]
    # the status block never rides on the published trade rows
    assert _scrub(off["docs"][-1]["trades_all"]) == _scrub(lo["docs"][-1]["trades_all"])


@pytest.mark.parametrize("raw,mode", [(None, "log_only"), ({}, "log_only"),
                                      ({"mode": "STOP"}, "stop"), ({"mode": "off"}, "off"),
                                      ({"mode": "bogus"}, "log_only"), ("stop_target", "stop"),
                                      ({"mode": "stop_target"}, "stop"),
                                      ({"mode": "stop_target", "oco_verified": "yes"}, "stop"),
                                      ({"mode": "stop_target", "oco_verified": True}, "stop_target")])
def test_mode_defaults_to_log_only_and_normalises(raw, mode):
    cfg = {} if raw is None else {"orb_resting": raw}
    assert qe._orb_resting_mode(cfg) == mode
    assert qe.DEFAULT_CONFIG["orb_resting"] == {"mode": "log_only"}


def test_stop_mode_scripted_day_through_tick(tmp_path, monkeypatch):
    """The same day through tick() in 'stop': armed after the entry filled, moved in place at
    breakeven, cancelled by the gateway for NOISE's exit and re-armed on the new account net,
    cancelled as step 1 of the 15:59 flatten -- every broker row ok, nothing left resting."""
    out = run_scripted_session(qe, tmp_path, monkeypatch, mode="stop")
    stops = [(c, st) for c, t, _side, _q, st in out["book"] if t == "STOP_LOSS"]
    assert stops == [("qxORBR620260928T144500ZSP1", "CANCELLED"),
                     ("qxORBR620260928T144500ZSP2", "CANCELLED")]
    rows = list(csv.DictReader(out["broker_orders.csv"].splitlines()))
    assert all(r["ok"] == "True" for r in rows)
    counts = out["docs"][-1]["orb_resting"]["counts"]
    assert (counts["armed"], counts["replaced"], counts["rearmed"]) == (1, 1, 1)
    texts = [e["text"] for e in out["state"]["events"] if e["kind"] == "orb_resting"]
    assert any("re-armed BUY 10 QQQ stop 732.33 (account net -10" in t for t in texts)
    assert any("EOD flatten, step 1" in t for t in texts)


def _scrub(v):
    """Paths differ between two tmp dirs; nothing else may."""
    s = json.dumps(v, sort_keys=True, default=str) if not isinstance(v, str) else v
    import re
    return re.sub(r"[A-Za-z]:[\\/][^\"',\s]*|/tmp[^\"',\s]*|/private[^\"',\s]*", "<path>", s)


def _scrub_doc(d):
    return _scrub(d)


def _baseline_ref():
    """QQQ_EXEC_BASELINE_REF when set, else the merge-base of HEAD and origin/main (2026-09-29
    second review: the proof used to be opt-in, so the mandated run skipped it). None when
    git cannot say (no repo, no origin/main)."""
    ref = os.environ.get("QQQ_EXEC_BASELINE_REF")
    if ref:
        return ref
    repo = os.path.dirname(os.path.dirname(os.path.abspath(qe.__file__)))
    try:
        out = subprocess.run(["git", "-C", repo, "merge-base", "HEAD", "origin/main"],
                             capture_output=True, check=True, timeout=30).stdout.decode().strip()
        return out or None
    except Exception:
        return None


BASELINE_REF = _baseline_ref()


@pytest.mark.skipif(not BASELINE_REF, reason="no baseline: set QQQ_EXEC_BASELINE_REF=<git ref> "
                    "(the commit this build branched from), or run inside a git checkout with "
                    "origin/main")
def test_off_mode_is_byte_identical_to_the_baseline_qqq_exec(tmp_path, monkeypatch):
    """SHIP-TIME PROOF: the scripted day through the baseline commit's own api/qqq_exec.py
    (loaded from git next to today's adapter and signal engine) and through this one in
    'off' writes the same orders/trades/broker rows, state, adapter state and docs, byte for
    byte. The baseline is QQQ_EXEC_BASELINE_REF, else the merge-base with origin/main (it
    skips itself once that base already carries the resting build)."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(qe.__file__)))

    def load(path, name, like):
        try:
            src = subprocess.run(["git", "-C", repo, "show", f"{BASELINE_REF}:{path}"],
                                 capture_output=True, check=True).stdout.decode("utf-8")
        except Exception as e:  # pragma: no cover
            pytest.skip(f"baseline {path} not readable: {e}")
        if "_maybe_manage_resting" in src or "def place_resting" in src:
            pytest.skip(f"{BASELINE_REF} already has the resting build -- point it at the "
                        f"commit before it")
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
        mod.__package__, mod.__file__ = "api", like.__file__
        sys.modules[name] = mod
        exec(compile(src, f"{name}.py", "exec"), mod.__dict__)
        return mod

    try:
        # BOTH halves as they were: the baseline order adapter (no gateway at all) under the
        # baseline book, against today's adapter (B2) under today's book in 'off'
        base_wo = load("api/webull_orders.py", "api.webull_orders_baseline", WO)
        base = load("api/qqq_exec.py", "api.qqq_exec_baseline", qe)
        base.webull_orders = base_wo
        new = run_scripted_session(qe, tmp_path / "new", monkeypatch, mode="off")
        old = run_scripted_session(base, tmp_path / "old", monkeypatch, mode=None, wo=base_wo)
    finally:
        sys.modules.pop("api.qqq_exec_baseline", None)
        sys.modules.pop("api.webull_orders_baseline", None)
    assert "ORB" in old["trades.csv"] and "NOISE" in old["trades.csv"], "the day really traded"
    for k in ("orders.csv", "trades.csv", "broker_orders.csv", "state.json",
              "adapter_state.json", "book"):
        assert _scrub(new[k]) == _scrub(old[k]), k
    assert [_scrub_doc(d) for d in new["docs"]] == [_scrub_doc(d) for d in old["docs"]]


# ── bounded resting calls: a hung SDK call never freezes the tick (2026-09-29 review) ──

class HangingBook(RecordingBook):
    """RecordingBook whose place_order / get_order_detail / cancel_order can hang (the
    09-03 10-hour hang: the SDK's own timeouts are not honoured) until `release` is set."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.hang = set()
        self.release = threading.Event()

    def _maybe_hang(self, name):
        if name in self.hang:
            self.release.wait(30)

    def place_order(self, account_id, new_orders, client_combo_order_id=None):
        self._maybe_hang("place_order")
        return super().place_order(account_id, new_orders, client_combo_order_id)

    def get_order_detail(self, account_id, client_order_id):
        self._maybe_hang("get_order_detail")
        return super().get_order_detail(account_id, client_order_id)

    def cancel_order(self, account_id, client_order_id):
        self._maybe_hang("cancel_order")
        return super().cancel_order(account_id, client_order_id)


def _fast_timeouts(monkeypatch):
    for name in ("RESTING_RESOLVE_HARD_TIMEOUT_SEC", "RESTING_PLACE_HARD_TIMEOUT_SEC",
                 "RESTING_CANCEL_HARD_TIMEOUT_SEC", "RESTING_REPLACE_HARD_TIMEOUT_SEC",
                 "ORDER_STATUS_HARD_TIMEOUT_SEC"):
        monkeypatch.setattr(qe, name, 0.3)
    monkeypatch.setattr(qe, "BROKER_SEND_HARD_TIMEOUT_SEC", 0.6)
    monkeypatch.setattr(qe, "_inflight_send", {"future": None, "leg": None, "intent": None})
    monkeypatch.setattr(qe, "_order_lookup_inflight", {"future": None})
    monkeypatch.setattr(qe, "_order_lookup_timeout_at", {"t": 0.0})


def _drain(*futs):
    for f in futs:
        if f is not None:
            try:
                f.result(timeout=15)
            except Exception:
                pass


def test_hung_place_lookup_and_cancel_never_freeze_the_tick_and_the_flatten_still_runs(
        tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch)
    b.book = HangingBook(price=735.0)
    _fast_timeouts(monkeypatch)
    _armed(b)
    (stop,) = b.live_stops()
    b.book.hang = {"place_order", "get_order_detail", "cancel_order"}
    try:
        t0 = time.monotonic()
        b.tick(at(11, 0, 5))                              # the lookup hangs: bounded
        assert time.monotonic() - t0 < 5
        assert qe._resting_busy()
        assert any("did not answer" in ln for ln in b.lines)
        t0 = time.monotonic()
        b.tick(at(11, 0, 10))                             # still out: the step skips
        b.tick(at(11, 0, 15))
        assert time.monotonic() - t0 < 5
        t0 = time.monotonic()
        b.close_all(at(15, 59, 1))                        # step 1 skipped, closes go on
        assert time.monotonic() - t0 < 8
        assert "ORB" not in b.state["legs"], "the book's flatten ran"
        assert any("flatten: step 1 skipped" in ln for ln in b.lines)
        t0 = time.monotonic()
        b.tick(at(15, 59, 6))
        assert time.monotonic() - t0 < 5
    finally:
        b.book.release.set()
        _drain(qe._resting_inflight.get("future"), qe._inflight_send.get("future"),
               qe._order_lookup_inflight.get("future"))


def test_a_hung_place_is_bounded_and_nothing_rearms_until_it_answers(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch)
    b.book = HangingBook(price=735.0)
    _fast_timeouts(monkeypatch)
    b.orb_entry()
    b.book.hang = {"place_order"}
    try:
        t0 = time.monotonic()
        b.tick(at(10, 50, 10))
        assert time.monotonic() - t0 < 5
        assert qe._resting_busy() and b.book.stops() == []
        places = len(b.book.sent("place"))
        b.tick(at(10, 50, 15))
        assert len(b.book.sent("place")) == places, "no second send while the first is out"
        # the adapter lock is free meanwhile: the tick's other reads go on
        assert b.adapter.resting_orders(lock_timeout=0.2) is not None
    finally:
        b.book.release.set()
        _drain(qe._resting_inflight.get("future"))
    monkeypatch.setattr(qe, "RESTING_CALL_COOLDOWN_SEC", 0.0)
    b.tick(at(10, 50, 20))
    assert [o["status"] for o in b.book.stops()] == ["SUBMITTED"]
    assert len(b.adapter.resting_orders()) == 1


# ── lookup cadence ─────────────────────────────────────────────────────────────────

def test_a_healthy_stop_is_looked_up_every_30s_or_at_once_when_it_matters(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "RESTING_LOOKUP_EVERY_SEC", 30.0)
    clock = [1_000_000.0]
    monkeypatch.setattr(qe, "time", types.SimpleNamespace(
        time=lambda: clock[0], sleep=time.sleep, monotonic=time.monotonic,
        perf_counter=time.perf_counter))
    _armed(b)
    (stop,) = b.live_stops()

    def looks():
        return sum(1 for m, c in b.book.calls if m == "detail" and c == stop["coid"])
    n = looks()
    for dt, now in ((5, at(10, 50, 15)), (10, at(10, 50, 20))):
        clock[0] = 1_000_000.0 + dt
        b.tick(now, captures=0)
    assert looks() == n, "no background lookup inside 30 s"
    clock[0] = 1_000_031.0
    b.tick(at(10, 50, 41), captures=0)
    assert looks() == n + 1
    b.px = 741.0                                          # the stream prints through the stop
    clock[0] = 1_000_033.0
    b.tick(at(10, 50, 43), captures=0)
    assert looks() == n + 2
    b.px = None
    b.state["_last_broker_send_at"] = 1_000_034.0         # another order went out
    clock[0] = 1_000_035.0
    b.tick(at(10, 50, 45), captures=0)
    assert looks() == n + 3
    clock[0] = 1_000_040.0
    b.tick(at(10, 50, 50), captures=0)
    assert looks() == n + 3


# ── a partial resting fill, then the engine EXIT: two rows, two prices ──────────────

def test_partial_stop_fill_then_the_engine_exit_keeps_both_webull_prices(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.partial[stop["coid"]] = 4
    book.book.set_price(741.0)
    for s in range(5, 30, 5):
        book.tick(at(10, 55, s))
    book.book.price = 741.5
    book.exit(at(11, 0, 5), "ORB_R6", ORB_TID, 741.5, "short")
    for s in range(10, 30, 5):
        book.tick(at(11, 0, s))
    assert book.sent("ORB") == 0 and book.book.pos == 0
    closes = [r for r in book.rows() if r["intent"] == "CLOSE"]
    assert [(r["client_order_id"][-2:], r["shares"], r["broker_fill_px"]) for r in closes] == [
        ("P1", "4", "741.0"), ("SC", "10", "741.5")], "the capture never overwrites the stop's row"
    by_base = qe._broker_orders_by_base(book.rows())
    fill, st, _ = qe._webull_fill_for_side({"trade_id": ORB_TID}, "CLOSE", by_base)
    assert st == "ok" and fill == pytest.approx((4 * 741.0 + 6 * 741.5) / 10)
    opened = qe._broker_order_for(ORB_TID, "OPEN", by_base)
    open_px = float(opened["broker_fill_px"])
    realized, _ = qe._broker_realized_today(qe._now_et().strftime("%Y-%m-%d"), log=NOOP)
    assert realized == pytest.approx(round((open_px - 741.0) * 4 + (open_px - 741.5) * 6, 2))


def test_parity_counts_a_resting_stops_fill_gap_as_slippage():
    rows = [{"leg": "ORB", "intent": "OPEN", "side": "SHORT", "shares": "10",
             "signal_id": "qxORBR620260928T144500ZSO", "ok": "True", "broker_fill_px": "732.33"},
            {"leg": "ORB", "intent": "CLOSE", "side": "BUY", "shares": "10",
             "signal_id": "qxORBR620260928T144500ZSC", "client_order_id": "qxORBR620260928T144500ZSP1",
             "ok": "True", "shadow_px": "740.77", "broker_fill_px": "741.0",
             "reason": "resting stop filled at Webull"}]
    by_base = qe._broker_orders_by_base(rows)
    trade = {"leg": "ORB", "side": "short", "trade_id": ORB_TID, "exit_px": 740.7712,
             "exit_reason": "stop"}
    eng = {"ENTRY": {"px": 732.33, "reason": ""}, "EXIT": {"px": 740.7712, "reason": ""}}
    side = qe._side_parity(trade, "CLOSE", by_base, eng)
    # the backtest exited AT the level: only the cent rounding is design, never "level"
    # (a design-only code would keep the real slippage out of the rolling averages)
    assert side["why"] == ""
    assert side["dsg"] == pytest.approx(0.0012) and side["slp"] == pytest.approx(-0.23)
    # a market EXIT (no resting row) keeps the whole gap as design, as before
    plain = [rows[0], dict(rows[1], client_order_id="qxORBR620260928T144500ZSC", reason="")]
    side = qe._side_parity(trade, "CLOSE", qe._broker_orders_by_base(plain), eng)
    assert side["slp"] == pytest.approx(0.0)


# ── escape events, re-queued events ────────────────────────────────────────────────

def test_an_escaped_record_pushes_and_asks_for_a_reconcile(book):
    _armed(book)
    (stop,) = book.live_stops()
    rec = book.adapter._state["resting"][stop["coid"]]
    with book.adapter._lock:
        book.adapter._queue_escape(stop["coid"], rec, "ABSENT", "no clear answer", "resolve")
    book.state["_reconcile_due"] = False
    assert qe._book_resting_fills(book.state, book.adapter, at(11, 0), log=book.log) == 0
    assert book.state["_reconcile_due"] is True
    assert [p for m, p in book.pushes if "settled ABSENT" in m] == ["high"]
    assert not [r for r in book.rows() if r["intent"] == "CLOSE"]


def test_a_fill_row_that_could_not_be_written_is_handed_back_not_lost(book, monkeypatch):
    _armed(book)
    book.book.set_price(741.0)
    real = qe._append_csv
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk hiccup")
        return real(*a, **k)
    monkeypatch.setattr(qe, "_append_csv", flaky)
    book.tick(at(10, 55, 5), captures=0)
    assert [r for r in book.rows() if r["intent"] == "CLOSE"] == []
    assert any("handed back" in ln for ln in book.lines)
    book.tick(at(10, 55, 10), captures=0)
    assert [r["client_order_id"] for r in book.rows() if r["intent"] == "CLOSE"] == \
        ["qxORBR620260928T144500ZSP1"]


# ── the market close after a crossing that was not accepted ───────────────────────

def test_engine_exit_still_closes_when_the_crossing_market_close_was_not_accepted(book):
    _armed(book)
    lot = book.state["legs"]["ORB"]
    lot["broker_closed"] = {"by": "market", "ok": False, "px": None, "id": "x", "at": "",
                            "note": "its broker close already went out ... (the close re-send "
                                    "queue owns it)"}
    book.exit(at(11, 0, 5), "ORB_R6", ORB_TID, 736.0, "short")
    book.tick(at(11, 0, 10))
    assert book.sent("ORB") == 0 and book.book.pos == 0, "ORB's close went to Webull"


# ── boot sweep: log_only only lists (see below); no lease, no cancel ──────────────

def _foreign(b):
    b.book.place_order("ACCT1", [{"combo_type": "NORMAL", "client_order_id": "otherhostP1",
                                  "symbol": "QQQ", "order_type": "STOP_LOSS", "quantity": "1",
                                  "side": "BUY", "stop_price": "900.00", "time_in_force": "DAY",
                                  "support_trading_session": "CORE"}])


def test_boot_sweep_without_the_lease_cancels_nothing(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="stop")
    monkeypatch.setattr(qe, "_read_config_for_gate", lambda log=print: b.cfg)
    monkeypatch.setattr(qe._LEASE, "send_gate", lambda uid: (False, "lease lost: test"))
    _foreign(b)
    qe._reconcile_broker_at_boot(log=b.log)
    assert b.book.orders["otherhostP1"]["status"] == "SUBMITTED"
    assert any("NOT cancelled: this host does not hold the lease" in m for m, _ in b.pushes)


def test_off_boot_sweep_asks_webull_nothing(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="off")
    monkeypatch.setattr(qe, "_read_config_for_gate", lambda log=print: b.cfg)
    _foreign(b)
    b.book.calls.clear()
    qe._resting_boot_sweep(b.adapter, log=b.log)
    assert b.book.calls == []


# ── a late LEVELS row still moves the stop; late ENTRY/EXIT rows stay skipped ─────

def test_a_late_levels_row_still_applies_but_a_late_entry_does_not(tmp_path, monkeypatch):
    home = tmp_path / "cs"
    paths = cs._paths(home=str(home))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    os.makedirs(paths["state_dir"], exist_ok=True)
    rows = [{"emitted_at": "2026-09-28T11:10:05-04:00", "leg": "ORB_R6", "event": "LEVELS",
             "side": "short", "ref_time": "2026-09-28T11:05:00-04:00", "ref_price": BE_STOP,
             "trade_id": ORB_TID, "stop_px": BE_STOP, "target_px": TARGET, "bar_source": "webull"},
            {"emitted_at": "2026-09-28T11:10:05-04:00", "leg": "NOISE_382", "event": "ENTRY",
             "side": "long", "ref_time": "2026-09-28T11:10:00-04:00", "ref_price": 736.0,
             "trade_id": "NOISE_382-20260928T151000Z-L", "bar_source": "webull"}]
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})
    cfg = {"orb_resting": {"mode": "stop"}}
    state = {"engine_cursor": 0}
    out = qe._consume_engine_signals(state, cfg, at(11, 55), log=NOOP)   # 45 min late
    assert [e["event"] for e in out] == ["LEVELS"]
    state = {"engine_cursor": 0}
    assert qe._consume_engine_signals(state, {"orb_resting": {"mode": "off"}}, at(11, 55),
                                      log=NOOP) == []


def test_wait_notes_stay_off_the_timeline(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="log_only")
    _pair_session_log_only(b)
    texts = [e["text"] for e in b.state["events"] if e["kind"] == "orb_resting"]
    assert not any("nothing would rest" in t or "would stay until" in t for t in texts)
    assert not any("qxNOISE" in t for t in texts)


# ── second review (2026-09-29) ─────────────────────────────────────────────────────

def _fail_lookups_past_the_escape(b, coid, start):
    """Every lookup of `coid` times out; ticks until the record is unclear long enough for
    the stuck-record escape (the age is moved back, not waited)."""
    b.book.detail_fail[coid] = 10 ** 6
    for s in range(WO.RESTING_ESCAPE_MIN_TRIES + 1):
        b.tick(start + datetime.timedelta(seconds=5 * s), captures=0)
    b.adapter._state["resting"][coid]["unclear_since"] -= WO.RESTING_ESCAPE_AFTER_SEC + 5


@pytest.mark.parametrize("noise", [0, 20])
def test_a_filled_stop_whose_lookups_fail_then_the_engine_exit_never_closes_twice(
        tmp_path, monkeypatch, noise):
    """The major finding end to end: ORB short 10 (with NOISE long 20 the account is +10, so
    the stop rests as a BUY 10 OPENING stop), the stop fills while every lookup of it times
    out past the escape; the engine's EXIT then comes. The adapter books the fill from
    Webull's position (inferred, one high push, a CLOSE row with no fill price), and ORB's
    exit sends nothing -- Webull ends where the books do."""
    b = Book(tmp_path, monkeypatch, noise_shares=noise or 20)
    if noise:
        b.entry(at(10, 0, 5), "NOISE_382", "2026-09-28T10:00:00-04:00", 735.0, "long")
        b.tick(at(10, 0, 10))
    _armed(b)
    (stop,) = b.live_stops()
    assert stop["side"] == "BUY"
    b.book.set_price(741.0)                               # filled at Webull
    real_pos = b.book.pos
    _fail_lookups_past_the_escape(b, stop["coid"], at(10, 55))
    b.tick(at(10, 56), captures=0)                        # the escape read decides: filled
    closes = [r for r in b.rows() if r["intent"] == "CLOSE"]
    assert [(r["client_order_id"], r["shares"], r["broker_fill_px"]) for r in closes] == [
        (stop["coid"], "10", "")]
    assert "inferred" in closes[0]["reason"]
    assert [p for m, p in b.pushes if "INFERRED" in m] == ["high"]
    b.exit(at(11, 0, 5), "ORB_R6", ORB_TID, 741.0, "short")
    for s in range(10, 30, 5):
        b.tick(at(11, 0, s))
    b.book.step()
    assert b.book.pos == real_pos == b.adapter._account_net("QQQ")
    assert sum(1 for o in b.book.markets() if o["side"] == "BUY") == (1 if noise else 0)
    assert b.sent("ORB") == 0


def test_an_undecided_absent_stop_holds_orbs_close_back_and_pushes_once(book):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.set_price(741.0)
    book.book.pos -= 13                                  # shares nobody in the books knows
    _fail_lookups_past_the_escape(book, stop["coid"], at(10, 55))
    book.tick(at(10, 56), captures=0)
    assert [p for m, p in book.pushes if "cannot be told yet" in m] == ["high"]
    book.exit(at(11, 0, 5), "ORB_R6", ORB_TID, 741.0, "short")
    book.tick(at(11, 0, 10))
    assert book.book.markets()[1:] == [], "no second close while the stop's fill is undecided"
    assert len([m for m, _p in book.pushes if "cannot be told yet" in m]) == 1


def test_log_only_boot_sweep_lists_a_foreign_order_and_never_cancels_it(tmp_path, monkeypatch):
    """Minor 4/12/14: the default mode sends nothing -- a hand-placed (or other host's) open
    QQQ order is listed and pushed at a restart, never cancelled, and entries are not halted."""
    b = Book(tmp_path, monkeypatch, mode="log_only")
    monkeypatch.setattr(qe, "_read_config_for_gate", lambda log=print: b.cfg)
    _foreign(b)
    qe._reconcile_broker_at_boot(log=b.log)
    assert b.book.orders["otherhostP1"]["status"] == "SUBMITTED" and b.book.sent("cancel") == []
    assert [p for m, p in b.pushes if "NOT cancelled: orb_resting.mode is 'log_only'" in m] == [None]
    assert b.adapter.halt_state()[0] is False


def test_stop_mode_boot_sweep_still_cancels_a_foreign_order(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="stop")
    monkeypatch.setattr(qe, "_read_config_for_gate", lambda log=print: b.cfg)
    _foreign(b)
    qe._reconcile_broker_at_boot(log=b.log)
    assert b.book.orders["otherhostP1"]["status"] == "CANCELLED"
    assert [p for m, p in b.pushes if "did not know -- cancelled" in m] == ["high"]


def test_a_lost_lease_cancels_the_resting_stop_but_an_unverifiable_one_keeps_it(book, monkeypatch):
    _armed(book)
    (stop,) = book.live_stops()
    book.state["_broker_lease_ok"] = False
    book.state["_broker_lease_reason"] = "lease unverifiable: Firestore read failed (Timeout)"
    book.tick(at(10, 55, 5))
    assert stop["status"] == "SUBMITTED", "a Firestore outage keeps the protection"
    book.state["_broker_lease_ok"] = True
    monkeypatch.setattr(qe._LEASE, "send_gate", lambda uid: (False, "lease lost: host 'box' took over"))
    for s in (10, 15, 20):
        book.tick(at(10, 55, s))
    assert stop["status"] == "CANCELLED" and book.live_stops() == []
    assert "cross-host lease" in book.blk()["last"]["text"]


def test_standing_down_cancels_this_hosts_resting_stop(book):
    _armed(book)
    (stop,) = book.live_stops()
    qe._cancel_resting_on_stand_down(book.state, log=book.log)
    assert stop["status"] == "CANCELLED" and book.live_stops() == []
    assert any("stand-down: cancelled" in ln for ln in book.lines)


def test_off_and_log_only_never_touch_webull_at_stand_down(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="log_only")
    b.orb_entry()
    b.tick(at(10, 50, 10))
    b.book.calls.clear()
    qe._cancel_resting_on_stand_down(b.state, log=b.log)
    assert b.book.calls == []


def test_a_rate_limited_arm_waits_and_is_never_a_failed_try(book):
    book.orb_entry()
    book.book.place_raise = [Exception("HTTP Status: 429, Code: TOO_MANY_REQUESTS, Msg: slow")] * 4
    book.tick(at(10, 50, 10))
    t = next(iter(book.blk()["tries"].values()))
    assert t["n"] == 0 and not t.get("gave_up") and "rate limit" in book.blk()["last"]["text"]
    places = len(book.book.sent("place"))
    book.tick(at(10, 50, 15))
    assert len(book.book.sent("place")) == places, "waits out the rate limit"
    assert not [p for m, p in book.pushes if "could not be placed" in m]


def test_a_changing_lease_age_is_one_log_line(book, monkeypatch):
    book.orb_entry()
    ages = __import__("itertools").count(100, 5)
    monkeypatch.setattr(qe._LEASE, "send_gate", lambda uid: (
        False, f"lease unverifiable: no stamp of this host's has landed in {next(ages)}s -- "
               f"broker sends blocked until a renewal lands"))
    for s in range(10, 60, 5):
        book.tick(at(10, 50, s))
    lines = [ln for ln in book.lines if "ORB resting (stop): nothing rests -- the cross-host" in ln]
    assert len(lines) == 1


def test_a_partial_stop_fill_found_by_orbs_own_close_is_written_before_the_market_row(book):
    """Minor 10: the gateway finds a PARTIAL stop fill while ORB's engine close is being
    sent (no tick between): the resting row (4 @ 741.00) is written before the market row,
    so the FIFO pairing prices both parts."""
    _armed(book)
    (stop,) = book.live_stops()
    book.book.partial[stop["coid"]] = 4
    book.book.set_price(741.0)
    book.book.price = 741.5
    book.exit(at(10, 55, 5), "ORB_R6", ORB_TID, 741.5, "short")
    for s in range(10, 30, 5):
        book.tick(at(10, 55, s))
    closes = [r for r in book.rows() if r["intent"] == "CLOSE"]
    assert [r["client_order_id"][-2:] for r in closes] == ["P1", "SC"]
    opened = qe._broker_order_for(ORB_TID, "OPEN", qe._broker_orders_by_base(book.rows()))
    open_px = float(opened["broker_fill_px"])
    realized, _ = qe._broker_realized_today(qe._now_et().strftime("%Y-%m-%d"), log=NOOP)
    assert realized == pytest.approx(round((open_px - 741.0) * 4 + (open_px - 741.5) * 6, 2))


def test_a_fill_booked_the_next_day_is_stamped_on_its_own_session(book):
    ev = {"change": 10, "leg": "ORB", "trade_id": ORB_TID, "kind": "stop", "side": "BUY",
          "client_order_id": "qxORBR620260928T144500ZSP1", "filled_price": 741.0,
          "stop_price": 740.77, "final": True, "filled": 10,
          "placed_at": at(10, 50, 10).timestamp()}
    stamp, note = qe._resting_fill_stamp(ev, datetime.datetime(2026, 9, 29, 9, 20, tzinfo=NY))
    assert stamp == "2026-09-28 16:00:00" and "while the book was down" in note
    stamp, note = qe._resting_fill_stamp(ev, at(11, 0))
    assert stamp == "2026-09-28 11:00:00" and note == ""


def test_parity_a_resting_fill_where_the_backtest_did_not_exit_is_diverged():
    """Minor 9 (a): Webull's stop filled at 740.77, but the backtest exited at its target
    690.14 -- that gap is unexplained ("diverged"), never design; (b) a gap-through (the
    backtest filled at the open beyond the level) is all slippage, no design."""
    rows = [{"leg": "ORB", "intent": "OPEN", "side": "SHORT", "shares": "10",
             "signal_id": "qxORBR620260928T144500ZSO", "ok": "True", "broker_fill_px": "732.33"},
            {"leg": "ORB", "intent": "CLOSE", "side": "BUY", "shares": "10",
             "signal_id": "qxORBR620260928T144500ZSC", "client_order_id": "qxORBR620260928T144500ZSP1",
             "ok": "True", "shadow_px": "740.77", "broker_fill_px": "741.0",
             "reason": "resting stop filled at Webull"}]
    by_base = qe._broker_orders_by_base(rows)
    trade = {"leg": "ORB", "side": "short", "trade_id": ORB_TID, "exit_reason": "target"}
    eng = {"ENTRY": {"px": 732.33, "stop_px": 740.77, "reason": ""},
           "EXIT": {"px": 690.14, "reason": ""}}
    side = qe._side_parity(trade, "CLOSE", by_base, eng)
    assert side["why"] == "diverged" and side["dsg"] == 0.0
    assert side["unx"] == pytest.approx(690.14 - 740.77) and qe._side_is_suspect(side)
    eng["EXIT"]["px"] = 741.2                           # (b) the backtest filled at the gap open
    side = qe._side_parity(trade, "CLOSE", by_base, eng)
    assert side["why"] == "" and side["dsg"] == 0.0 and side["slp"] == pytest.approx(0.2)
    assert "diverged" in qe.FP_WHY_RESTING and "diverged" not in qe.FP_WHY


def test_a_hung_webull_through_the_whole_tick_never_freezes_the_day(tmp_path, monkeypatch):
    """The hang through qe.tick() itself (2026-09-29 second review: the earlier hang tests
    drive Book.tick + _close_all). The stop rests; from then on every lookup, cancel and
    place hangs. Every later tick -- the breakeven move, NOISE's exit through the gateway,
    the 15:59 flatten -- returns within its bounds (a reconcile whose resting lookup hangs
    is bounded by RECONCILE_HARD_TIMEOUT_SEC, shortened here), and the shadow book still
    flattens."""
    _fast_timeouts(monkeypatch)
    monkeypatch.setattr(qe, "RECONCILE_HARD_TIMEOUT_SEC", 1.0)
    fake = HangingBook(price=736.58)
    walls = []

    def on_tick(i, now, fk, wall):
        walls.append((now.strftime("%H:%M:%S"), wall))
        if any(o["type"] == "STOP_LOSS" for o in fk.orders.values()) and not fk.hang:
            fk.hang = {"place_order", "get_order_detail", "cancel_order"}
    try:
        out = run_scripted_session(qe, tmp_path, monkeypatch, mode="stop", fake=fake,
                                   on_tick=on_tick)
    finally:
        fake.release.set()
        _drain(qe._resting_inflight.get("future"), qe._inflight_send.get("future"),
               qe._order_lookup_inflight.get("future"))
    assert fake.hang, "the stop rested, then Webull hung"
    slow = [(t, w) for t, w in walls if w > 5.0]
    assert slow == [], f"ticks that froze: {slow}"
    assert "ORB" not in out["state"].get("legs", {}) and "NOISE" not in out["state"].get("legs", {})


# ── third review (2026-09-29): minor notes ─────────────────────────────────────────

def test_parity_a_resting_fill_wins_over_the_books_eod_rail_exit():
    """The book's trade closed on a rail (EOD) but Webull's side was closed earlier by the
    resting stop: the resting logic decides ("diverged", the level-vs-backtest gap
    unexplained), never the rail's design/slippage split."""
    rows = [{"leg": "ORB", "intent": "OPEN", "side": "SHORT", "shares": "10",
             "signal_id": "qxORBR620260928T144500ZSO", "ok": "True", "broker_fill_px": "732.33"},
            {"leg": "ORB", "intent": "CLOSE", "side": "BUY", "shares": "10",
             "signal_id": "qxORBR620260928T144500ZSC", "client_order_id": "qxORBR620260928T144500ZSP1",
             "ok": "True", "shadow_px": "740.77", "broker_fill_px": "741.0",
             "reason": "resting stop filled at Webull"}]
    trade = {"leg": "ORB", "side": "short", "trade_id": ORB_TID,
             "exit_reason": "EOD (px: live_stream)", "exit_px": "735.0"}
    eng = {"ENTRY": {"px": 732.33, "stop_px": 740.77, "reason": ""},
           "EXIT": {"px": 735.0, "reason": ""}}
    side = qe._side_parity(trade, "CLOSE", qe._broker_orders_by_base(rows), eng)
    assert side["why"] == "diverged" and side["dsg"] == 0.0
    assert side["unx"] == pytest.approx(qe._edge_ps(735.0, 740.77, True))
    assert side["slp"] == pytest.approx(qe._edge_ps(740.77, 741.0, True))
    # the same trade closed by a plain market close is still the rail's split
    rows[1].update(client_order_id="qxORBR620260928T144500ZSC", shadow_px="735.0", reason="")
    side = qe._side_parity(trade, "CLOSE", qe._broker_orders_by_base(rows), eng)
    assert side["why"] == "eod"


def test_an_unreadable_broker_quantity_never_cancels_a_healthy_stop(book, monkeypatch):
    _armed(book)
    (stop,) = book.live_stops()
    book.book.calls.clear()

    def boom():
        raise RuntimeError("dictionary changed size during iteration")
    monkeypatch.setattr(book.adapter, "status", boom)
    book.tick(at(10, 55, 5), captures=0)
    assert stop["status"] == "SUBMITTED" and book.book.sent("cancel") == []
    assert "not readable" in book.blk()["last"]["text"]


def test_a_reconcile_read_failure_keeps_the_stop(book):
    """A positions READ failure (fail_closed) halts entries but is not a mismatch: the stop
    keeps working (test_a_real_mismatch_cancels_the_resting_stop_and_blocks_rearming is the
    other half)."""
    _armed(book)
    (stop,) = book.live_stops()
    book.book.calls.clear()
    book.adapter.fail_closed("can't read positions at Webull: ReadTimeout")
    assert book.adapter.halt_state()[0] is True
    for s in range(5, 20, 5):
        book.tick(at(10, 55, s), captures=0)
    assert stop["status"] == "SUBMITTED", "a Webull blip keeps the protection"
    assert book.book.sent("cancel") == []


def test_log_only_boot_sweep_cancels_a_crashed_stop_hosts_resting_order(tmp_path, monkeypatch):
    """A resting-pattern id (qx<tid>P<n>) Webull still works that this state does not know is
    this book's own stop from a host that crashed in a stop mode: with the lease it is
    cancelled in log_only too (high push, entries halted until a reconcile agrees); a
    hand-placed order next to it is only listed."""
    b = Book(tmp_path, monkeypatch, mode="log_only")
    monkeypatch.setattr(qe, "_read_config_for_gate", lambda log=print: b.cfg)
    b.book.place_order("ACCT1", [{"combo_type": "NORMAL",
                                  "client_order_id": "qxORBR620260928T144500ZSP2",
                                  "symbol": "QQQ", "order_type": "STOP_LOSS", "quantity": "1",
                                  "side": "BUY", "stop_price": "900.00", "time_in_force": "DAY",
                                  "support_trading_session": "CORE"}])
    _foreign(b)
    qe._resting_boot_sweep(b.adapter, log=b.log)
    assert b.book.orders["qxORBR620260928T144500ZSP2"]["status"] == "CANCELLED"
    assert b.book.orders["otherhostP1"]["status"] == "SUBMITTED"
    assert [p for m, p in b.pushes if "did not know -- cancelled (1 of them)" in m] == ["high"]
    assert b.adapter.halt_state()[0] is True


def test_log_only_boot_sweep_pushes_a_hand_placed_order_once_not_per_restart(tmp_path, monkeypatch):
    b = Book(tmp_path, monkeypatch, mode="log_only")
    monkeypatch.setattr(qe, "_read_config_for_gate", lambda log=print: b.cfg)
    _foreign(b)
    for _ in range(3):
        b.restart_adapter()
        qe._resting_boot_sweep(b.adapter, log=b.log)
    assert len([m for m, _p in b.pushes if "did not know" in m]) == 1
    assert b.book.orders["otherhostP1"]["status"] == "SUBMITTED"
    assert any("already reported" in ln for ln in b.lines)


def test_an_earlier_sessions_undecided_stop_holds_only_orbs_own_close(book):
    """A resting record from an earlier session left live and undecided holds back ORB's own
    CLOSE (the double-close risk) but never NOISE's orders: a DAY order that old cannot
    be working at Webull."""
    _armed(book)
    (stop,) = book.live_stops()
    stop["status"] = "EXPIRED"                           # yesterday's DAY order, long gone
    rec = book.adapter._state["resting"][stop["coid"]]
    rec["placed_at"] -= 2 * 24 * 3600
    rec["absent_undecided"] = "Webull's QQQ position differs from the books by 13"
    rec["absent_checked_at"] = time.time()               # not due another positions read
    noise = book.adapter.place_stock_order(leg="NOISE", signal_id="qxNOISETESTO", symbol="QQQ",
                                           side="BUY", qty=5, intent="OPEN")
    assert noise.get("outcome") != "RESTING_UNRESOLVED" and noise.get("sent") is True
    orb = book.adapter.place_stock_order(leg="ORB", signal_id="qxORBTESTC", symbol="QQQ",
                                         side="BUY", qty=10, intent="CLOSE")
    assert orb["outcome"] == "RESTING_UNRESOLVED" and orb["sent"] is False
    assert "earlier session" in orb["reason"]


def test_a_late_flatten_only_sends_the_cancels(book, monkeypatch):
    """With under RESTING_FLATTEN_CONFIRM_MIN_LEFT_SEC to the close, step 1 sends the cancels
    without waiting for Webull's confirm; ORB's close gateway confirms, and the book still
    ends flat. An on-time 15:59 flatten (59 s left) still confirms first."""
    _armed(book)
    (stop,) = book.live_stops()
    seen = []
    real = book.adapter.cancel_resting
    monkeypatch.setattr(book.adapter, "cancel_resting",
                        lambda **k: (seen.append(k.get("confirm")), real(**k))[1])
    book.close_all(at(15, 59, 40))
    assert seen[:1] == [False]
    assert stop["status"] == "CANCELLED" and book.live_stops() == []
    book.book.step()
    assert "ORB" not in book.state["legs"] and book.sent("ORB") == 0 and book.book.pos == 0
    assert qe._resting_seconds_to_close(at(15, 59, 1)) == pytest.approx(59.0)
    assert qe._resting_seconds_to_close(at(15, 59, 1)) >= qe.RESTING_FLATTEN_CONFIRM_MIN_LEFT_SEC


def test_a_resting_call_on_the_wire_past_a_minute_pushes_once(monkeypatch):
    import concurrent.futures as cf
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        pushes.append((msg, priority)))
    fut = cf.Future()
    monkeypatch.setattr(qe, "_resting_inflight",
                        {"future": fut, "what": "place", "timed_out_at": 0.0,
                         "started_at": time.time() - qe.RESTING_HANG_ALERT_SEC - 1,
                         "hang_alerted": False})
    monkeypatch.setattr(qe, "_log_event", NOOP)
    state = qe._default_state()
    qe._resting_hang_alert(state, log=NOOP)
    qe._resting_hang_alert(state, log=NOOP)
    assert [p for m, p in pushes if "has not answered" in m] == ["high"]
    fut.set_result(None)
