"""HOLD OVERNIGHT (OWNER GO 2026-10-09, MANAGER #106): ENGU-Q (exec leg ENGUQ, engine key
ENGUQ_335) holds its trade overnight on the Webull paper QQQ book, like its backtest.

Covered here (api/qqq_exec.py, with a real api.webull_orders.OrderAdapter in PAPER mode on a
synchronous fake Webull account -- no SDK, network or credentials):
  * the flat_by flatten skips ENGU-Q and still closes ORB / NOISE; config
    session.hold_overnight_legs [] turns the hold off; a bad value falls back to the code
    default; ninjatrader mode never holds;
  * the flat_by internal cross never offsets a closing leg against a held lot;
  * KILL and the daily loss BREAKER close a held lot inside regular hours; outside them
    nothing is sent -- the lot waits (close_pending) and is sold at market from the next
    open; a KILL whose file is gone by the open is cancelled; a BREAKER close survives
    midnight;
  * the lot survives a day rollover, a weekend, a holiday and a process restart (state.json
    reload + a fresh adapter, boot reconcile OK) and its later-day strategy EXIT sells it at
    market in regular hours; an EXIT after the bell waits for the open; a held lot's EXIT is
    never skipped as stale;
  * the $400 daily loss rail is MARK-TO-OPEN on BOTH rail sites (the book breaker and the
    adapter's daily_pnl): a big overnight gap trips nothing, a loss after the open does; the
    gap stays in the P&L of record (trades.csv pnl, overnight_gap_usd) and is published on
    its own;
  * next-morning netting with the held lot in the account net;
  * the orphan repair never sells a held lot; the after-close check is quiet with only the
    held lot and loud with anything else; status doc fields, the day summary and every phone
    note about the hold are plain.
"""
import csv
import json
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api import cloud_signal as cs
from api import ntfy_push
from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731

DAY1 = (2026, 10, 8)      # Thursday
DAY2 = (2026, 10, 9)      # Friday
SAT = (2026, 10, 10)
MON = (2026, 10, 12)
TID_E = "ENGUQ_335-20261008T150000Z-L"
TID_E2 = "ENGUQ_335-20261009T150000Z-L"
TID_O = "ORB_R6-20261008T144000Z-S"
TID_N = "NOISE_382-20261008T143000Z-L"
TID_N2 = "NOISE_382-20261009T143500Z-S"
# the real functions, before any test stubs them
_REAL_BUILD_DOC = qe._build_doc
_REAL_CONSUME = qe._consume_engine_signals
_REAL_MARKS = qe._held_session_marks


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
    """One Webull margin account, QQQ only, synchronous market fills at `fill_px`. Refuses
    what Webull refuses: a SHORT on a long account, a SELL past the long shares, a BUY that
    crosses a short straight to long."""

    def __init__(self):
        self.pos = 0
        self.sent = []
        self.refused = []
        self.fill_px = 700.0
        self.status = {}
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
        if side == "SHORT" and self.pos > 0:
            self._refuse(side, qty, "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION")
        if side == "SELL" and qty > self.pos:
            self._refuse(side, qty, "OPENAPI_ORDER_EXCEED_POSITION")
        if side == "BUY" and self.pos < 0 and self.pos + qty > 0:
            self._refuse(side, qty, "OPENAPI_ORDER_CROSSES_POSITION")
        self.pos += qty if side == "BUY" else -qty
        self.sent.append((side, qty, coid))
        self.status[coid] = "FILLED"
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": "FILLED", "filled_price": f"{self.fill_px:.2f}",
             "filled_quantity": str(qty)}]})

    def _detail(self, account_id, coid):
        return _Resp({"client_order_id": coid, "orders": [
            {"client_order_id": coid, "status": self.status.get(coid) or "REJECTED",
             "filled_quantity": "0"}]})


def _wo_cfg(tmp_path):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["rails"]["max_shares_per_leg"] = 100
    cfg["rails"]["max_total_position_shares"] = 500
    cfg["rails"]["daily_loss_limit_usd"] = 400
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _qe_cfg(tmp_path, **kw):
    cfg = json.loads(json.dumps(qe.DEFAULT_CONFIG))
    cfg.update(signal_source="engine", shares={"ORB": 10, "ENGUQ": 10, "NOISE": 10},
               max_shares_per_leg=60, slippage_per_share=0.0, daily_loss_limit_usd=400,
               kill_file=str(tmp_path / "KILL"), orb_resting={"mode": "off"})
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
        self.clock = [at(DAY1, 9, 0)]
        monkeypatch.setattr(qe, "_now_et", lambda: self.clock[0])
        self.px = {"ORB": 700.0, "ENGUQ": 700.0, "NOISE": 700.0}
        self.marks = {"prior_close": None, "today_open": None, "today_last": None}
        monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (self.px[leg], "live_stream"))
        monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (self.px[leg], "engine_test"))
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
        self.adapter = WO.OrderAdapter(config=dict(self.wo_cfg), log=NOOP)
        self.mp.setattr(self.adapter, "_build_client", lambda mode: self.fake)
        self.mp.setattr(qe, "_get_broker_adapter", lambda log=print: self.adapter)

    def restart(self):
        """A process restart: state.json read back from disk, a fresh adapter that loads its
        own state file."""
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

    def open(self, leg, side, tid, px, when):
        self.clock[0] = when
        qe._roll_day(self.state, when.strftime("%Y-%m-%d"))
        self.state["_px_source"] = "test"
        self.fake.fill_px = px
        self.px[leg] = px
        assert qe._open_lot(self.state, self.cfg, leg, side, self.cfg["shares"][leg], None, px, 0.0,
                            log=self.log, trade_id=tid, nowdt=when)

    def close(self, leg, px, when, reason="signal exit"):
        self.clock[0] = when
        qe._roll_day(self.state, when.strftime("%Y-%m-%d"))
        self.state["_px_source"] = "test"
        self.fake.fill_px = px
        lot = self.state["legs"][leg]
        return qe._reduce_lot(self.state, self.cfg, leg, lot["nq_qty_total"], None, px, 0.0, reason,
                              log=self.log, nowdt=when)

    def lot(self, leg):
        return self.state["legs"][leg]

    def books(self):
        return {leg: p["qty"] for leg, p in (self.adapter._state.get("broker_sent_positions") or {}).items()}

    def broker_rows(self):
        return _rows(qe.BROKER_ORDERS_CSV)

    def trades(self):
        return _rows(qe.TRADES_CSV)

    def kill(self, on=True):
        p = self.tmp / "KILL"
        if on:
            p.write_text("")
        elif p.exists():
            p.unlink()


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def _hold_enguq(e, px_close=690.0):
    """DAY1: ENGU-Q long 10 at 700.00 from 11:00, held at the 15:59 flatten."""
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    e.px["ENGUQ"] = px_close
    e.tick(at(DAY1, 15, 59, 5))
    assert "ENGUQ" in e.state["legs"]
    assert e.lot("ENGUQ")["hold"]["since"] == ds(DAY1)


def _exit_event(tid, px, ref_time, reason=""):
    return {"leg": "ENGUQ_335", "event": "EXIT", "side": "long", "ref_time": ref_time,
            "ref_price": px, "bar_source": "webull", "trade_id": tid, "size": "",
            "keel_size": "", "reason": reason}


# ── config ─────────────────────────────────────────────────────────────────────────────

def test_hold_legs_default_override_garbage_and_ninjatrader():
    assert qe.HOLD_OVERNIGHT_LEGS == ("ENGUQ",)
    assert qe._hold_legs({}) == ("ENGUQ",)
    assert qe._hold_legs({"session": {"flat_by": "15:59"}}) == ("ENGUQ",)
    assert qe._hold_legs({"session": {"hold_overnight_legs": []}}) == ()
    assert qe._hold_legs({"session": {"hold_overnight_legs": ["ENGUQ", "NOISE"]}}) == ("ENGUQ", "NOISE")
    for bad in ("ENGUQ", ["SPY"], [1], {"ENGUQ": 1}):
        assert qe._hold_legs({"session": {"hold_overnight_legs": bad}}) == ("ENGUQ",)
    assert qe._hold_legs({"signal_source": "ninjatrader"}) == (), \
        "the NinjaTrader fallback never replays an old fill, so it keeps flat-at-close"


def test_load_config_keeps_a_list_and_drops_a_bad_value(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"session": {"hold_overnight_legs": []}}), encoding="utf-8")
    cfg = qe.load_config(path=str(p), log=NOOP)
    assert cfg["session"]["hold_overnight_legs"] == [] and qe._hold_legs(cfg) == ()
    assert cfg["session"]["flat_by"] == qe.DEFAULT_CONFIG["session"]["flat_by"]
    lines = []
    p.write_text(json.dumps({"session": {"hold_overnight_legs": "ENGUQ"}}), encoding="utf-8")
    cfg = qe.load_config(path=str(p), log=lines.append)
    assert "hold_overnight_legs" not in cfg["session"] and qe._hold_legs(cfg) == ("ENGUQ",)
    assert any("invalid session.hold_overnight_legs" in ln for ln in lines)
    assert "hold_overnight_legs" not in qe.DEFAULT_CONFIG["session"], \
        "code default only -- nothing baked into DEFAULT_CONFIG"


# ── flat_by ───────────────────────────────────────────────────────────────────────────

def test_flat_by_keeps_enguq_and_closes_orb_and_noise(env):
    e = env
    e.open("ORB", "short", TID_O, 700.0, at(DAY1, 10, 40))
    e.open("NOISE", "long", TID_N, 700.0, at(DAY1, 10, 30))
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    assert e.fake.pos == 10 and e.books() == {"ORB": -10, "NOISE": 10, "ENGUQ": 10}
    sent_before = len(e.fake.sent)

    e.tick(at(DAY1, 15, 59, 5))

    assert set(e.state["legs"]) == {"ENGUQ"}
    h = e.lot("ENGUQ")["hold"]
    assert h["since"] == ds(DAY1) and h["flat_by_day"] == ds(DAY1) and h["nights"] == 0
    assert e.state["flat_by_done_date"] == ds(DAY1)
    # ORB short 10 and NOISE long 10 cross each other (already flat at Webull); ENGU-Q is
    # never in the flatten -- no order at all, Webull keeps ENGU-Q's 10
    assert e.fake.sent[sent_before:] == []
    assert e.books() == {"ORB": 0, "NOISE": 0, "ENGUQ": 10}
    assert e.fake.pos == 10
    assert not [r for r in e.broker_rows() if r["leg"] == "ENGUQ" and r["intent"] == "CLOSE"]
    assert {t["leg"] for t in e.trades()} == {"ORB", "NOISE"}
    kinds = [ev["kind"] for ev in e.state["events"]]
    assert "eod_flatten" in kinds and "held_overnight" in kinds
    assert [ev["text"] for ev in e.state["events"] if ev["kind"] == "eod_flatten"] == \
        ["End-of-day flatten closed: ORB, NOISE"]
    held_notes = [p for p in e.pushes if p["title"] == "QQQ book: held overnight"]
    assert len(held_notes) == 1 and held_notes[0]["priority"] == "low"


def test_flat_by_never_crosses_a_closing_leg_against_the_held_lot(env):
    """The 09-28 pair shape -- ORB short 10, ENGU-Q long 10, account flat -- with ENGU-Q held:
    no cross (that would close ENGU-Q in the books with no order); ORB's own BUY 10 goes out
    and Webull ends holding exactly ENGU-Q's 10."""
    e = env
    e.open("ORB", "short", TID_O, 700.0, at(DAY1, 10, 40))
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    assert e.fake.pos == 0
    sent_before = len(e.fake.sent)

    e.tick(at(DAY1, 15, 59, 5))

    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("BUY", 10)]
    assert e.fake.refused == []
    assert e.books() == {"ORB": 0, "ENGUQ": 10}
    assert e.fake.pos == 10
    assert not [r for r in e.broker_rows() if r.get("outcome") == "NETTED"]
    assert not e.adapter._state.get("internal_crosses")
    assert e.adapter.reconcile()["ok"] is True


def test_config_empty_list_flattens_enguq_like_before(env):
    e = env
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    cfg = dict(e.cfg)
    cfg["session"] = dict(cfg["session"], hold_overnight_legs=[])
    e.tick(at(DAY1, 15, 59, 5), cfg=cfg)
    assert e.state["legs"] == {}
    assert e.fake.pos == 0 and e.books() == {"ENGUQ": 0}


# ── the lot survives the night, a restart and closes on its own exit ───────────────────

def test_held_lot_survives_rollover_and_restart_then_its_exit_sells_at_market(env):
    e = env
    _hold_enguq(e, px_close=690.0)
    e.tick(at(DAY1, 16, 0, 40))           # the after-close check: Webull 10 = the held 10
    v = e.state["_webull_flat_after_eod"]
    assert v["flat"] is True and v["held"] == {"ENGUQ": 10}
    assert not [p for p in e.pushes if "CHECK NOW" in p["title"]]
    e.tick(at(DAY1, 23, 59, 55))

    e.restart()                            # overnight restart: state.json + adapter state file
    lot = e.lot("ENGUQ")
    assert lot["hold"]["since"] == ds(DAY1) and lot["trade_id"] == TID_E
    assert e.books() == {"ENGUQ": 10} and e.adapter._state["open_legs"] == {"ENGUQ": True}
    assert e.adapter.reconcile()["ok"] is True
    qe._reconcile_broker_at_boot(log=NOOP)
    assert not e.adapter._halted

    e.tick(at(DAY2, 0, 0, 5))              # midnight roll: nothing dropped, nothing sent
    assert "ENGUQ" in e.state["legs"] and e.fake.pos == 10
    e.marks.update(prior_close=690.0, today_open=640.0, today_last=650.0)
    e.px["ENGUQ"] = 650.0
    e.tick(at(DAY2, 9, 31, 0))
    h = e.lot("ENGUQ")["hold"]
    assert (h["open_mark_px"], h["close_mark_px"], h["gap_today_usd"], h["nights"]) == \
        (640.0, 690.0, -500.0, 1)

    sent_before = len(e.fake.sent)
    e.px["ENGUQ"] = e.fake.fill_px = 660.0
    e.tick(at(DAY2, 10, 30, 5), events=[_exit_event(TID_E, 660.0, "2026-10-09 10:29:00")])

    assert "ENGUQ" not in e.state["legs"]
    assert e.fake.sent[sent_before:] == [("SELL", 10, "qx" + TID_E.replace("_", "").replace("-", "") + "C")]
    assert e.fake.pos == 0 and e.books() == {"ENGUQ": 0}
    (t,) = e.trades()
    assert float(t["pnl"]) == -400.0, "P&L of record is exit - entry, the gap included"
    assert float(t["overnight_gap_usd"]) == -500.0 and t["nights_held"] == "1"
    assert t["entry_ts"].startswith(ds(DAY1)) and t["exit_ts"].startswith(ds(DAY2))
    # the rail counts exit - open mark: (660 - 640) x 10
    assert qe._rail_realized_today(e.state) == pytest.approx(200.0)
    assert e.state["realized_pnl_today"] == -400.0
    assert e.adapter._state["daily_pnl"] == pytest.approx(200.0)


def test_held_session_marks_read_the_engine_1m_cache(env):
    """The real reader: prior close = the last bar before today, open = today's first bar's
    open from 09:30, last = today's newest close; None before today's first bar."""
    import pandas as pd
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")

    def ep(day, h, m):
        return int(datetime(day[0], day[1], day[2], h, m, tzinfo=ny).timestamp())
    rows = [(ep(DAY1, 15, 58), 690.5, 690.9), (ep(DAY1, 15, 59), 690.9, 690.0),
            (ep(DAY2, 9, 30), 640.0, 641.0), (ep(DAY2, 9, 31), 641.0, 642.5)]
    os.makedirs(cs.DEFAULT_PATHS["ohlc_dir"], exist_ok=True)
    pd.DataFrame([{"time": t, "open": o, "high": max(o, c), "low": min(o, c), "close": c,
                   "volume": 100} for t, o, c in rows]).to_csv(
        os.path.join(cs.DEFAULT_PATHS["ohlc_dir"], "QQQ_1m.csv"), index=False)
    got = _REAL_MARKS("ENGUQ", at(DAY2, 9, 33), log=NOOP)
    assert (got["prior_close"], got["today_open"], got["today_last"]) == (690.0, 640.0, 642.5)
    pre = _REAL_MARKS("ENGUQ", at(DAY1, 23, 0), log=NOOP)
    assert pre["prior_close"] is None and pre["today_open"] == 690.5
    sat = _REAL_MARKS("ENGUQ", at(SAT, 10, 0), log=NOOP)
    assert (sat["prior_close"], sat["today_open"], sat["today_last"]) == (642.5, None, None)


def test_held_lot_rides_a_weekend_and_a_second_night(env):
    e = env
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    e.tick(at(DAY1, 15, 59, 5))
    e.marks.update(prior_close=700.0, today_open=705.0, today_last=706.0)
    e.px["ENGUQ"] = 706.0
    e.tick(at(DAY2, 9, 31))
    e.tick(at(DAY2, 15, 59, 5))            # Friday's flatten keeps it again
    assert e.lot("ENGUQ")["hold"]["flat_by_day"] == ds(DAY2)
    e.marks.update(prior_close=710.0, today_open=None, today_last=None)
    e.px["ENGUQ"] = 710.0
    for when in (at(SAT, 0, 0, 5), at(SAT, 12, 0), at((2026, 10, 11), 20, 0)):
        e.tick(when)
        assert e.state["_rail_unrl_by_leg"]["ENGUQ"] == 0.0
        assert e.lot("ENGUQ")["hold"]["nights"] == 1
    e.marks.update(prior_close=710.0, today_open=700.0, today_last=701.0)
    e.px["ENGUQ"] = 701.0
    e.tick(at(MON, 9, 31))
    h = e.lot("ENGUQ")["hold"]
    assert h["nights"] == 2 and h["gap_today_usd"] == -100.0
    assert h["gap_usd"] == pytest.approx(50.0 - 100.0)
    assert e.state["_rail_unrl_by_leg"]["ENGUQ"] == 10.0
    assert e.fake.pos == 10


def test_a_holiday_leaves_the_held_lot_untouched(env):
    e = env
    wed, thanks, fri = (2026, 11, 25), (2026, 11, 26), (2026, 11, 27)
    e.open("ENGUQ", "long", "ENGUQ_335-20261125T150000Z-L", 700.0, at(wed, 11, 0))
    e.tick(at(wed, 15, 59, 5))
    before = json.loads(json.dumps(e.lot("ENGUQ")))
    sent_before = len(e.fake.sent)
    e.kill(True)                           # even a KILL waits: the holiday tick does nothing
    e.tick(at(thanks, 10, 0))
    assert e.lot("ENGUQ") == before and len(e.fake.sent) == sent_before
    e.kill(False)
    e.marks.update(prior_close=700.0, today_open=702.0, today_last=702.5)
    e.tick(at(fri, 9, 31))                 # the half day: open mark as usual
    assert e.lot("ENGUQ")["hold"]["open_mark_px"] == 702.0


# ── strategy exits outside regular hours ───────────────────────────────────────────────

def test_after_the_bell_exit_of_a_held_lot_waits_for_the_open(env):
    e = env
    _hold_enguq(e)
    sent_before = len(e.fake.sent)
    e.tick(at(DAY1, 16, 0, 35), events=[_exit_event(TID_E, 689.0, "2026-10-08 15:59:00",
                                                     reason="eod_settle")])
    lot = e.lot("ENGUQ")
    assert lot["close_pending"]["reason"] == "signal exit"
    assert lot["close_pending"]["trade_id"] == TID_E and lot["close_pending"]["px"] == 689.0
    assert len(e.fake.sent) == sent_before
    assert not [p for p in e.pushes if p["priority"] in ("urgent", "high")], \
        "a deferred held exit is planned, never 'the sell came after the close'"
    e.tick(at(DAY2, 9, 25))                # inside the window, still before the open
    assert len(e.fake.sent) == sent_before and "ENGUQ" in e.state["legs"]

    e.marks.update(prior_close=690.0)      # today's first bar not in yet at 09:30:05
    e.px["ENGUQ"] = e.fake.fill_px = 680.0
    e.tick(at(DAY2, 9, 30, 5))
    assert "ENGUQ" not in e.state["legs"]
    assert e.fake.sent[sent_before:] == [("SELL", 10, "qx" + TID_E.replace("_", "").replace("-", "") + "C")]
    (t,) = e.trades()
    assert t["exit_reason"] == qe.HELD_EXIT_REASON
    assert float(t["pnl"]) == -200.0 and float(t["overnight_gap_usd"]) == -100.0
    assert qe._rail_realized_today(e.state) == 0.0, "closed at its own open mark: nothing on the rail"
    assert any(ev["kind"] == "held_close_at_open" for ev in e.state["events"])


def test_an_old_exit_of_a_held_lot_is_never_skipped_as_stale(env):
    e = env
    _hold_enguq(e)
    paths = cs.DEFAULT_PATHS               # the env's private cloud_signal home
    os.makedirs(paths["state_dir"], exist_ok=True)
    rows = [
        {"emitted_at": "2026-10-08 16:00:30", "leg": "ENGUQ_335", "event": "EXIT", "side": "long",
         "ref_time": "2026-10-08 15:59:00", "ref_price": 689.0, "trade_id": TID_E},
        {"emitted_at": "2026-10-09 08:41:00", "leg": "NOISE_382", "event": "ENTRY", "side": "long",
         "ref_time": "2026-10-09 08:40:00", "ref_price": 700.0, "trade_id": TID_N2},
        {"emitted_at": "2026-10-08 16:00:30", "leg": "ENGUQ_335", "event": "EXIT", "side": "long",
         "ref_time": "2026-10-08 15:59:00", "ref_price": 689.0, "trade_id": "ENGUQ_335-x-L"},
    ]
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})
    st = {"legs": e.state["legs"], "engine_cursor": 0, "events": []}
    got = _REAL_CONSUME(st, e.cfg, at(DAY2, 9, 30, 0), log=NOOP)
    assert [(g["leg"], g["event"], g["trade_id"]) for g in got] == [("ENGUQ_335", "EXIT", TID_E)], \
        "17 h old: the held lot's own exit is routed; a 49-min-old entry and another trade's exit are not"


# ── KILL ──────────────────────────────────────────────────────────────────────────────

def test_kill_in_regular_hours_closes_the_held_lot(env):
    e = env
    _hold_enguq(e)
    e.marks.update(prior_close=690.0, today_open=691.0, today_last=692.0)
    e.tick(at(DAY2, 9, 31))
    sent_before = len(e.fake.sent)
    e.kill(True)
    e.px["ENGUQ"] = 692.0
    e.tick(at(DAY2, 11, 0))
    assert e.state["legs"] == {}
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    assert e.trades()[-1]["exit_reason"].startswith("KILL")


@pytest.mark.parametrize("when,opening", [(at(DAY1, 20, 0), at(DAY2, 9, 30, 5)),
                                          (at(DAY2, 8, 0), at(DAY2, 9, 30, 5)),
                                          (at(SAT, 10, 0), at(MON, 9, 30, 5))])
def test_kill_outside_regular_hours_sends_nothing_and_sells_at_the_open(env, when, opening):
    e = env
    _hold_enguq(e)
    sent_before = len(e.fake.sent)
    e.kill(True)
    e.tick(when)
    lot = e.lot("ENGUQ")
    assert lot["close_pending"]["reason"] == "KILL"
    assert len(e.fake.sent) == sent_before
    assert e.state["kill_done"] is True
    kill_notes = [p for p in e.pushes if p["title"] == "QQQ book: kill switch on"]
    assert kill_notes and "held shares sell when the market opens" in kill_notes[-1]["message"]
    e.tick(opening)
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    assert e.trades()[-1]["exit_reason"].startswith("KILL")
    assert e.fake.pos == 0


def test_a_pending_close_survives_a_restart_and_goes_out_at_the_open(env):
    e = env
    _hold_enguq(e)
    e.kill(True)
    e.tick(at(DAY2, 7, 0))
    sent_before = len(e.fake.sent)
    e.restart()
    cp = e.lot("ENGUQ")["close_pending"]
    assert cp["reason"] == "KILL" and cp["trade_id"] == TID_E
    assert e.lot("ENGUQ")["hold"]["since"] == ds(DAY1)
    e.tick(at(DAY2, 9, 30, 5))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]


def test_a_kill_cancelled_before_the_open_keeps_the_lot_held(env):
    e = env
    _hold_enguq(e)
    sent_before = len(e.fake.sent)
    e.kill(True)
    e.tick(at(SAT, 10, 0))
    assert e.lot("ENGUQ")["close_pending"]["reason"] == "KILL"
    e.kill(False)
    e.tick(at((2026, 10, 11), 18, 0))
    assert "close_pending" not in e.lot("ENGUQ")
    assert any(ev["kind"] == "held_close_cancelled" for ev in e.state["events"])
    e.tick(at(MON, 9, 30, 5))
    assert "ENGUQ" in e.state["legs"] and len(e.fake.sent) == sent_before


# ── the daily loss rail: mark-to-open on both rail sites ───────────────────────────────

def test_a_big_gap_never_trips_but_a_loss_after_the_open_does_on_both_rails(env):
    e = env
    _hold_enguq(e, px_close=690.0)        # day 1: -100 open on the lot
    e.marks.update(prior_close=690.0, today_open=None, today_last=None)
    e.px["ENGUQ"] = 641.0                 # what an entry-based mark would read: -590

    e.tick(at(DAY2, 0, 0, 5))
    assert e.state["_unrl_by_leg"]["ENGUQ"] == -590.0
    assert e.state["_rail_unrl_by_leg"]["ENGUQ"] == 0.0
    assert not e.state["breaker_tripped"]
    assert e.adapter._state["daily_pnl"] == pytest.approx(0.0), \
        "the adapter's rail must not block every OPEN from midnight on the held lot's record mark"

    e.marks.update(today_open=640.0, today_last=641.0)   # gap -50 a share = -500
    e.tick(at(DAY2, 9, 31, 0))
    assert not e.state["breaker_tripped"] and "ENGUQ" in e.state["legs"]
    assert e.state["_rail_unrl_by_leg"]["ENGUQ"] == 10.0
    assert e.state["_breaker_input"]["pnl"] == 10.0
    assert e.adapter._state["daily_pnl"] == pytest.approx(10.0)
    ok = e.adapter._check_rails("ORB", 10, "OPEN")
    assert ok[0] is True, ok

    # 41 a share under today's open: -410, past the $400 limit -> trips and closes ENGU-Q
    e.marks["today_last"] = 599.0
    e.px["ENGUQ"] = e.fake.fill_px = 599.0
    sent_before = len(e.fake.sent)
    e.tick(at(DAY2, 10, 0, 0))
    assert e.state["breaker_tripped"] is True
    assert e.state["legs"] == {}
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    assert e.state["_breaker_input"]["pnl"] == -410.0
    assert e.state["realized_pnl_today"] == -1010.0, "P&L of record keeps the gap and day 1"
    assert qe._rail_realized_today(e.state) == pytest.approx(-410.0)
    assert e.adapter._state["daily_pnl"] == pytest.approx(-410.0)
    blocked = e.adapter.place_stock_order(leg="ORB", signal_id="late-open", symbol="QQQ",
                                          side="BUY", qty=10)
    assert blocked["mode"] == "BLOCKED" and "daily loss limit" in blocked["reason"]
    (t,) = e.trades()
    assert float(t["overnight_gap_usd"]) == -500.0


def test_a_breaker_trip_after_the_bell_waits_for_the_open_and_survives_midnight(env):
    e = env
    _hold_enguq(e, px_close=694.0)        # -60 on the lot
    e.state["realized_pnl_today"] = -350.0
    sent_before = len(e.fake.sent)
    e.tick(at(DAY1, 16, 0, 30))           # -410 after the bell
    assert e.state["breaker_tripped"] is True
    assert e.lot("ENGUQ")["close_pending"]["reason"] == "BREAKER"
    assert len(e.fake.sent) == sent_before
    stop = [p for p in e.pushes if p["title"] == "QQQ book: daily stop hit"]
    assert stop and "held shares sell when the market opens" in stop[-1]["message"]
    e.tick(at(DAY2, 0, 0, 5))
    assert e.state["breaker_tripped"] is False, "the daily stop itself resets at midnight"
    assert e.lot("ENGUQ")["close_pending"]["reason"] == "BREAKER", "its close does not"
    e.tick(at(DAY2, 9, 30, 5))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    assert e.trades()[-1]["exit_reason"].startswith("BREAKER")


def test_a_carried_lot_entry_fill_shortfall_belongs_to_its_entry_day(env):
    e = env
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    # Webull filled the entry 25 cents worse than the book
    rows = e.broker_rows()
    for r in rows:
        if r["intent"] == "OPEN":
            r["broker_fill_px"] = "700.25"
    with open(qe.BROKER_ORDERS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        w.writerows(rows)
    qe._BREAKER_ADJ_CACHE["key"] = None
    e.state["trading_day"] = ds(DAY1)
    assert qe._breaker_fill_shortfall(e.state, log=NOOP) == -2.5, "counts on its entry day"
    e.tick(at(DAY1, 15, 59, 5))
    qe._roll_day(e.state, ds(DAY2))
    qe._BREAKER_ADJ_CACHE["key"] = None
    assert qe._breaker_fill_shortfall(e.state, log=NOOP) == 0.0, "never again on a later day"


def test_broker_realized_pairs_the_held_close_with_its_open_mark(env):
    """_broker_realized_today: the held lot's OPEN row is an earlier day's -- seeded with the
    open mark, its CLOSE today counts exit - open mark; an unseeded close stays ignored."""
    e = env
    e.clock[0] = at(DAY2, 10, 0)
    with open(qe.BROKER_ORDERS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        w.writerow({"ts_et": "2026-10-08 11:00:00", "leg": "ENGUQ", "intent": "OPEN", "side": "BUY",
                    "shares": 10, "mode": "PAPER", "ok": "True", "broker_fill_px": "700.00"})
        w.writerow({"ts_et": "2026-10-09 10:00:00", "leg": "ENGUQ", "intent": "CLOSE", "side": "SELL",
                    "shares": 10, "mode": "PAPER", "ok": "True", "broker_fill_px": "655.00"})
    assert qe._broker_realized_today("2026-10-09", log=NOOP) == (0.0, True)
    seeds = {"ENGUQ": {"px": 640.0, "side": "BUY", "shares": 10}}
    assert qe._broker_realized_today("2026-10-09", log=NOOP, held_seeds=seeds) == (150.0, True)
    # closed before today's first bar: its fill is today's first price -- nothing realized
    seeds["ENGUQ"]["at_fill"] = True
    assert qe._broker_realized_today("2026-10-09", log=NOOP, held_seeds=seeds) == (0.0, True)


def test_a_close_at_the_open_waits_for_a_price_from_today(env, monkeypatch):
    """No fresh live print and no 1m bar from today yet at 09:30: the book would record the
    exit at yesterday's close and the gap would leak into the rail through the fill
    shortfall -- so the sell waits for today's first price, never past 09:35."""
    e = env
    _hold_enguq(e)
    e.kill(True)
    e.tick(at(DAY2, 8, 0))
    sent_before = len(e.fake.sent)
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (690.0, "engine_test"))
    e.tick(at(DAY2, 9, 30, 5))
    assert "ENGUQ" in e.state["legs"] and len(e.fake.sent) == sent_before
    e.marks.update(prior_close=690.0, today_open=640.0, today_last=641.0)
    e.px["ENGUQ"] = e.fake.fill_px = 641.0
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (641.0, "engine_test"))
    e.tick(at(DAY2, 9, 31, 25))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    (t,) = e.trades()
    assert float(t["exit_px"]) == 641.0 and float(t["overnight_gap_usd"]) == -500.0
    assert qe._rail_realized_today(e.state) == pytest.approx(10.0)


def test_a_close_at_the_open_never_waits_past_0935(env, monkeypatch):
    e = env
    _hold_enguq(e)
    e.kill(True)
    e.tick(at(DAY2, 8, 0))
    sent_before = len(e.fake.sent)
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (690.0, "engine_test"))
    e.tick(at(DAY2, 9, 34, 55))
    assert "ENGUQ" in e.state["legs"]
    e.tick(at(DAY2, 9, 35, 0))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]


# ── next-morning netting ───────────────────────────────────────────────────────────────

def test_next_morning_netting_runs_through_the_held_lot(env):
    """Held ENGU-Q +10; NOISE opens short 10 -> a plain SELL 10 at Webull (the account is long
    the held 10); ENGU-Q's exit -> SHORT 10; NOISE's cover -> BUY 10, flat. Per-leg books
    stay right at every step."""
    e = env
    _hold_enguq(e)
    e.marks.update(prior_close=690.0, today_open=691.0, today_last=691.0)
    e.tick(at(DAY2, 9, 31))
    start = len(e.fake.sent)

    e.open("NOISE", "short", TID_N2, 691.0, at(DAY2, 9, 40))
    assert [(s, q) for s, q, _ in e.fake.sent[start:]] == [("SELL", 10)]
    assert e.books() == {"ENGUQ": 10, "NOISE": -10} and e.fake.pos == 0

    e.close("ENGUQ", 692.0, at(DAY2, 10, 15))
    assert [(s, q) for s, q, _ in e.fake.sent[start + 1:]] == [("SHORT", 10)]
    assert e.books() == {"ENGUQ": 0, "NOISE": -10} and e.fake.pos == -10

    e.close("NOISE", 690.0, at(DAY2, 11, 0))
    assert [(s, q) for s, q, _ in e.fake.sent[start + 2:]] == [("BUY", 10)]
    assert e.books() == {"ENGUQ": 0, "NOISE": 0} and e.fake.pos == 0
    assert e.fake.refused == []
    assert e.adapter.reconcile()["ok"] is True


def test_a_new_day_enguq_entry_is_refused_while_the_lot_is_held(env):
    e = env
    _hold_enguq(e)
    e.marks.update(prior_close=690.0, today_open=691.0, today_last=691.0)
    entry = {"leg": "ENGUQ_335", "event": "ENTRY", "side": "long", "ref_time": "2026-10-09 11:00:00",
             "ref_price": 691.0, "bar_source": "webull", "trade_id": TID_E2, "size": "",
             "keel_size": "", "reason": ""}
    sent_before = len(e.fake.sent)
    e.tick(at(DAY2, 11, 0, 30), events=[entry])
    assert e.lot("ENGUQ")["trade_id"] == TID_E
    assert e.state["trade_id_checks"]["today"].get("entry_leg_busy") == 1
    assert len(e.fake.sent) == sent_before
    assert e.adapter._check_rails("ENGUQ", 10, "OPEN")[0] is False
    # the strategy trades one position at a time: its new entry means the held trade's exit
    # was missed -- the flatten no longer closes it, so the owner hears it once, plainly
    (p,) = [p for p in e.pushes if p["title"] == "QQQ book: CHECK NOW"]
    assert p["priority"] == "high" and ntfy_push.lint(p) == []
    assert "ENGU-Q cannot take new trades" in p["message"]
    assert any(ev["kind"] == "held_exit_missed" for ev in e.state["events"])
    e.tick(at(DAY2, 11, 5, 30), events=[dict(entry, ref_time="2026-10-09 11:05:00",
                                             trade_id="ENGUQ_335-20261009T150500Z-L")])
    assert len([p for p in e.pushes if p["title"] == "QQQ book: CHECK NOW"]) == 1, "once a day"


def test_an_entry_while_the_held_exit_waits_for_the_open_is_not_a_missed_exit(env, monkeypatch):
    e = env
    _hold_enguq(e)
    e.tick(at(DAY1, 16, 0, 35), events=[_exit_event(TID_E, 689.0, "2026-10-08 15:59:00",
                                                     reason="eod_settle")])
    assert e.lot("ENGUQ")["close_pending"]["reason"] == "signal exit"
    monkeypatch.setattr(qe, "_held_open_price_ready", lambda leg, nowdt, log=print: False)
    entry = {"leg": "ENGUQ_335", "event": "ENTRY", "side": "long", "ref_time": "2026-10-09 09:31:00",
             "ref_price": 691.0, "bar_source": "webull", "trade_id": "ENGUQ_335-20261009T133100Z-L",
             "size": "", "keel_size": "", "reason": ""}
    e.tick(at(DAY2, 9, 31, 30), events=[entry])
    assert e.state["trade_id_checks"]["today"].get("entry_leg_busy") == 1
    assert not [p for p in e.pushes if p["title"] == "QQQ book: CHECK NOW"], \
        "its exit is known and only waits for a price from today"


# ── orphan repair, after-close check, boot reconcile ───────────────────────────────────

def test_orphan_repair_never_sells_a_held_lot(env):
    e = env
    _hold_enguq(e)
    trigger = e.out / "FLATTEN_BROKER"
    trigger.write_text("")
    sent_before = len(e.fake.sent)
    e.marks.update(prior_close=690.0, today_open=691.0, today_last=691.0)
    e.tick(at(DAY2, 9, 35))
    assert len(e.fake.sent) == sent_before and "ENGUQ" in e.state["legs"]
    assert not trigger.exists(), "nothing to repair -- the trigger is consumed"


class _Positions:
    def __init__(self, qty):
        self.qty = qty

    def effective_mode(self):
        return "PAPER", "test"

    def positions(self, account_id=None):
        return {"believed": {}, "broker": ({"QQQ": float(self.qty)} if self.qty else {}),
                "mode": "PAPER"}


def _held_state(side="long", n=10):
    return {"events": [], "legs": {"ENGUQ": {"leg": "ENGUQ", "side": side, "shares_remaining": n,
                                             "shares_total": n, "entry_px": 700.0,
                                             "trade_id": TID_E, "hold": {"since": ds(DAY1)}}}}


@pytest.mark.parametrize("webull,flat,off", [(10, True, None), (7, False, 3), (0, False, 10),
                                              (17, False, 7), (-10, False, 20)])
def test_after_close_check_is_quiet_with_only_the_held_lot_and_loud_otherwise(monkeypatch, webull,
                                                                             flat, off):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Positions(webull))
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        pushes.append({"title": title, "message": msg, "priority": priority}) or True)
    state = _held_state()
    # `shares` is what Webull holds (as before the hold); "off" -- how far from the held lot
    assert qe._check_webull_flat_after_eod(state, log=NOOP) == (flat, 0 if flat else abs(webull))
    assert state.get("_eod_flat_off") == off
    if flat:
        assert pushes == []
    else:
        (p,) = pushes
        assert p["title"] == "QQQ book: CHECK NOW" and p["priority"] == "urgent"
        assert ntfy_push.lint(p) == []
        assert "held overnight" in p["message"]


def test_after_close_check_without_a_held_lot_is_unchanged(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Positions(7))
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: True)
    state = {"events": [], "legs": {}}
    assert qe._check_webull_flat_after_eod(state, log=NOOP) == (False, 7)
    assert "still holds 7 QQQ" in state["events"][-1]["text"]


def test_after_close_scheduler_stamps_what_webull_holds_and_how_far_off(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _Positions(7))
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: True)
    state = _held_state()
    state.update({"flat_by_done_date": ds(DAY1), "_last_broker_send_at": 0.0})
    qe._maybe_check_webull_flat_after_eod(state, {}, at(DAY1, 16, 1), log=NOOP)
    v = state["_webull_flat_after_eod"]
    assert (v["flat"], v["shares"], v["off"], v["held"]) == (False, 7, 3, {"ENGUQ": 10})
    assert "_eod_flat_off" not in state


def test_after_close_scheduler_judges_a_held_lot_from_the_bell_and_stamps_it(monkeypatch):
    calls = []
    monkeypatch.setattr(qe, "_check_webull_flat_after_eod",
                        lambda state, log=print: calls.append(1) or (True, 0))
    nowdt = at(DAY1, 15, 59, 0)
    state = _held_state()
    state.update({"flat_by_done_date": ds(DAY1),
                  "_last_broker_send_at": 0.0})
    for early in (nowdt, at(DAY1, 15, 59, 55)):     # before and past the 15:59:50 deadline
        qe._maybe_check_webull_flat_after_eod(state, {}, early, log=NOOP)
    assert calls == [], ("the held lot can still sell on its own exit before the bell -- a "
                         "verdict stamped now would stand for the day")
    qe._maybe_check_webull_flat_after_eod(state, {}, at(DAY1, 16, 0, 0), log=NOOP)
    assert calls == [1], "only a held lot open: judged at the bell, no other wait"
    assert state["_webull_flat_after_eod"] == {"date": ds(DAY1), "flat": True, "shares": 0,
                                               "held": {"ENGUQ": 10}}
    # a non-held lot still open before the deadline is still waited for
    calls.clear()
    state = _held_state()
    state["legs"]["ORB"] = {"side": "short", "shares_remaining": 10}
    state.update({"flat_by_done_date": ds(DAY1), "_last_broker_send_at": 0.0})
    qe._maybe_check_webull_flat_after_eod(state, {}, nowdt, log=NOOP)
    assert calls == []


def test_boot_reconcile_is_ok_with_the_held_lot_and_halts_when_webull_lost_it(env):
    e = env
    _hold_enguq(e)
    e.restart()
    assert e.adapter.reconcile()["ok"] is True and not e.adapter._halted
    e.fake.pos = 0                         # Webull no longer holds the held shares
    res = e.adapter.reconcile()
    assert res["ok"] is False and e.adapter._halted


# ── status doc, day summary, phone wording ─────────────────────────────────────────────

def test_status_doc_shows_the_held_lot_as_planned_with_its_gap(env, monkeypatch):
    e = env
    _hold_enguq(e)
    e.marks.update(prior_close=690.0, today_open=640.0, today_last=645.0)
    e.px["ENGUQ"] = 645.0
    e.tick(at(DAY2, 9, 45))
    monkeypatch.setattr(qe, "_build_doc", _REAL_BUILD_DOC)
    for name, fn in (("_trade_parity", lambda row, log=print: {}),
                     ("_load_reprice_sidecar", lambda log=print: {}),
                     ("_engine_prices_by_trade", lambda *a, **k: {}),
                     ("_build_price_status", lambda cfg, state, log=print: {}),
                     ("_build_run_location", lambda: {}),
                     ("_build_ratio_health", lambda state, nowdt, cfg=None, log=print: {}),
                     ("_build_keel_status", lambda log=print: {}),
                     ("_build_equity_status", lambda state, nowdt, log=print: {}),
                     ("_live_price_for_leg", lambda leg, log=print: (645.0, 1.0, "live_stream"))):
        monkeypatch.setattr(qe, name, fn)
    doc = qe._build_doc(e.cfg, e.state, False, -550.0, log=NOOP)
    p = doc["positions"]["ENGUQ"]
    assert p["held_overnight"] is True and p["held_since"] == ds(DAY1) and p["nights_held"] == 1
    assert (p["gap_usd"], p["gap_today_usd"], p["close_mark_px"], p["open_mark_px"]) == \
        (-500.0, -500.0, 690.0, 640.0)
    assert p["unrealized"] == -550.0 and p["unrealized_rail"] == 50.0
    assert p["close_pending"] is None
    t = doc["today"]
    assert t["overnight_gap_usd"] == -500.0 and t["unrealized_rail"] == 50.0
    assert t["realized_pnl_rail"] == 0.0
    assert t["breaker_input"] == round(t["realized_pnl_rail"] + t["breaker_fill_adj"]
                                       + t["unrealized_rail"], 2)
    assert doc["rails"]["hold_overnight_legs"] == ["ENGUQ"]
    assert doc["rails"]["session"]["hold_overnight_legs"] == ["ENGUQ"], "the effective list"
    assert doc["rails"]["session"]["flat_by"] == "15:59"
    live = doc["positions_live"]
    (leg,) = live["legs"]
    assert leg["held_overnight"] is True and leg["gap_usd"] == -500.0
    assert live["mismatch"] is False and live["broker_net_qty"] == 10
    json.dumps(doc, allow_nan=False)


def test_day_summary_names_the_held_shares_plainly(monkeypatch):
    pushes = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None:
                        pushes.append({"title": title, "message": msg, "priority": priority}) or True)
    nowdt = at(DAY1, 16, 10)
    state = {"_webull_flat_after_eod": {"date": ds(DAY1), "flat": True, "shares": 0,
                                        "held": {"ENGUQ": 10}}}
    doc = {"today": {"trades": [], "realized_pnl": 0.0}, "parity": {"checked": 0, "failed": 0},
           "feed_days": [{"date": ds(DAY1), "uptime_pct": 1.0}], "breaker_tripped": False}
    qe._maybe_send_eod_summary(state, doc, nowdt, log=NOOP)
    (p,) = pushes
    assert "Webull holds only ENGU-Q's 10 shares held overnight" in p["message"]
    assert p["priority"] == "low" and ntfy_push.lint(p) == []
    assert any("Webull flat: yes, except held overnight (ENGU-Q long 10)" in ev["text"]
               for ev in state["events"])


def test_every_hold_phone_note_is_plain(env):
    e = env
    _hold_enguq(e)
    e.kill(True)
    e.tick(at(DAY1, 20, 0))
    e.kill(False)
    e.tick(at(DAY1, 20, 1))
    e.state["realized_pnl_today"] = -1000.0
    e.tick(at(DAY1, 20, 2))
    notes = [qe._held_note("ENGUQ", 10), qe._kill_note(["ENGUQ"]), qe._kill_note()] + e.pushes
    assert len(e.pushes) >= 3
    for n in notes:
        assert ntfy_push.lint(n) == [], n
    assert all(len(n["title"]) < 40 for n in notes)


# ── review fixes (FIXER 2026-10-09) ──────────────────────────────────────────────────────

def _write_signals(rows):
    paths = cs.DEFAULT_PATHS
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cs.SIGNAL_COLS})


def test_a_same_day_exit_consumed_late_still_closes_the_hold_leg_at_a_price_from_now(env):
    """ENGU-Q opens 11:00; its exit is emitted 14:00:30 and the book only consumes it at 15:45
    (down or restarting). Before the hold the 15:59 flatten was the backstop; now the flatten
    keeps ENGU-Q, so its own exit must never be dropped as stale -- and its 14:00 price is not
    booked: it sells at market at a price from now. Another leg's late exit is still skipped."""
    e = env
    e.open("NOISE", "long", TID_N, 700.0, at(DAY1, 10, 30))
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    _write_signals([
        {"emitted_at": "2026-10-08 14:00:30", "leg": "ENGUQ_335", "event": "EXIT", "side": "long",
         "ref_time": "2026-10-08 14:00:00", "ref_price": 705.0, "trade_id": TID_E},
        {"emitted_at": "2026-10-08 14:00:30", "leg": "NOISE_382", "event": "EXIT", "side": "long",
         "ref_time": "2026-10-08 14:00:00", "ref_price": 705.0, "trade_id": TID_N}])
    st = {"legs": e.state["legs"], "engine_cursor": 0, "events": []}
    got = _REAL_CONSUME(st, e.cfg, at(DAY1, 15, 45), log=NOOP)
    assert [(g["leg"], g["trade_id"], g.get("late")) for g in got] == [("ENGUQ_335", TID_E, True)]
    sent_before = len(e.fake.sent)
    e.px["ENGUQ"] = e.fake.fill_px = 702.0
    e.tick(at(DAY1, 15, 45), events=got)
    assert e.lot("ENGUQ")["close_pending"]["late"] is True
    assert "hold" not in e.lot("ENGUQ"), "a late exit on its entry day starts no overnight hold"
    e.tick(at(DAY1, 15, 45, 5))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    (t,) = e.trades()
    assert float(t["exit_px"]) == 702.0, "a price from now, never the 14:00 row's 705"
    assert t["exit_reason"] == qe.LATE_EXIT_REASON and t["overnight_gap_usd"] == ""
    e.tick(at(DAY1, 15, 59, 5))
    assert set(e.state["legs"]) == set() and e.fake.pos == 0


def test_a_carried_lot_exit_stamped_with_an_earlier_session_sells_at_todays_price(env):
    """Long 10 @ 700, prior close 690, today's open 720 (+300 gap). The engine's late settle
    row for the held trade -- stamped with yesterday's 15:59 bar at 689 -- is written at 09:45.
    Booked at 689 the trade would read -110 and the rail -310 (the gap); it must sell at today's
    price: pnl of record 220, the gap 300 in its own column, the rail exit - open = 20."""
    e = env
    _hold_enguq(e, px_close=690.0)
    e.marks.update(prior_close=690.0, today_open=720.0, today_last=722.0)
    e.px["ENGUQ"] = e.fake.fill_px = 722.0
    e.tick(at(DAY2, 9, 31))
    sent_before = len(e.fake.sent)
    e.tick(at(DAY2, 9, 45), events=[_exit_event(TID_E, 689.0, "2026-10-08 15:59:00",
                                                 reason="eod_settle")])
    assert e.lot("ENGUQ")["close_pending"]["reason"] == "signal exit"
    assert len(e.fake.sent) == sent_before
    e.tick(at(DAY2, 9, 45, 5))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    (t,) = e.trades()
    assert float(t["exit_px"]) == 722.0 and float(t["pnl"]) == 220.0
    assert float(t["overnight_gap_usd"]) == 300.0 and t["exit_reason"] == qe.HELD_EXIT_REASON
    assert qe._rail_realized_today(e.state) == pytest.approx(20.0)
    assert e.state["breaker_tripped"] is False
    assert qe._held_carry_closed_today(e.state, ds(DAY2)) == -100.0, \
        "what it had made by the prior close: (690 - 700) x 10, in today's record but not today's move"


def test_a_breaker_trip_that_cannot_price_the_hold_leg_is_closed_by_the_flatten(env, monkeypatch):
    """The breaker trips at 11:00 but cannot price ENGU-Q on that tick (lot left open) and never
    retries; the 15:59 flatten must close it, not hold it overnight -- hard stops stay hard."""
    e = env
    _hold_enguq(e)
    e.marks.update(prior_close=690.0, today_open=691.0, today_last=691.0)
    e.px["ENGUQ"] = 691.0
    e.tick(at(DAY2, 9, 31))
    e.marks["today_last"] = 640.0                # (640 - 691) x 10 = -510 on the rail
    e.px["ENGUQ"] = 640.0
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (None, None))
    sent_before = len(e.fake.sent)
    e.tick(at(DAY2, 11, 0))
    assert e.state["breaker_tripped"] is True and "ENGUQ" in e.state["legs"]
    assert len(e.fake.sent) == sent_before
    monkeypatch.setattr(qe, "_exit_price_for_leg", lambda leg, log=print: (e.px[leg], "live_stream"))
    e.fake.fill_px = 641.0
    e.px["ENGUQ"] = 641.0
    e.tick(at(DAY2, 15, 59, 5))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent_before:]] == [("SELL", 10)]
    assert e.trades()[-1]["exit_reason"].startswith("EOD") and e.fake.pos == 0


def test_a_lot_whose_flatten_was_missed_is_adopted_as_held(env):
    """The executor is down through DAY1's 15:59-16:05 flatten and comes back at 16:15: ENGU-Q's
    lot has no hold mark. It is carried all the same -- adopted from its entry day -- so a big
    gap the next morning stays off the $400 rail and is recorded as the gap."""
    e = env
    e.open("ENGUQ", "long", TID_E, 700.0, at(DAY1, 11, 0))
    e.px["ENGUQ"] = 690.0
    e.tick(at(DAY1, 16, 15))
    assert "hold" not in e.lot("ENGUQ")
    e.tick(at(DAY2, 0, 0, 5))
    h = e.lot("ENGUQ")["hold"]
    assert h["since"] == ds(DAY1) and h["flat_by_day"] == ds(DAY1)
    assert any("without its end-of-day hold mark" in ev["text"] for ev in e.state["events"]
               if ev["kind"] == "held_overnight")
    assert not [p for p in e.pushes if p["priority"] in ("high", "urgent")]
    e.marks.update(prior_close=690.0, today_open=640.0, today_last=645.0)
    e.px["ENGUQ"] = 645.0
    e.tick(at(DAY2, 9, 31))
    assert e.state["breaker_tripped"] is False and "ENGUQ" in e.state["legs"]
    assert e.state["_rail_unrl_by_leg"]["ENGUQ"] == 50.0
    assert e.state["_breaker_input"]["pnl"] == 50.0
    h = e.lot("ENGUQ")["hold"]
    assert (h["gap_today_usd"], h["nights"]) == (-500.0, 1)
    assert e.fake.pos == 10


def test_a_pre_open_kill_is_checked_after_its_sale_not_before(env):
    """A KILL at 08:00 with only the held lot open: Webull is not judged then (the lot sells at
    09:30), so the after-close check runs once the sale has emptied the book."""
    e = env
    _hold_enguq(e)
    e.kill(True)
    e.state["_last_broker_send_at"] = 0.0      # the post-order grace is wall-clock
    e.tick(at(DAY2, 8, 0, 5))
    assert e.lot("ENGUQ")["close_pending"]["reason"] == "KILL"
    assert e.state["kill_flatten_date"] == ds(DAY2)
    assert (e.state.get("_webull_flat_after_eod") or {}).get("date") != ds(DAY2)
    e.tick(at(DAY2, 9, 30, 5))
    assert e.state["legs"] == {} and e.fake.pos == 0
    e.state["_last_broker_send_at"] = 0.0      # the post-order grace is wall-clock
    e.tick(at(DAY2, 9, 31))
    v = e.state["_webull_flat_after_eod"]
    assert v["date"] == ds(DAY2) and v["flat"] is True and "held" not in v


def test_boot_says_so_when_the_book_lost_a_held_lot(env):
    e = env
    _hold_enguq(e)
    e.restart()
    qe._reconcile_broker_at_boot(log=NOOP)
    assert not [p for p in e.pushes if p["title"] == "QQQ book: CHECK NOW"], "book and adapter agree"
    with open(qe.STATE_PATH, "w", encoding="utf-8") as f:
        f.write("{ torn")                          # load_state starts empty on this
    e._new_adapter()
    qe._reconcile_broker_at_boot(log=NOOP)
    (p,) = [p for p in e.pushes if p["title"] == "QQQ book: CHECK NOW"]
    assert p["priority"] == "urgent" and ntfy_push.lint(p) == []
    assert "lost ENGU-Q's held shares" in p["message"]


def test_feed_stall_and_gave_up_wording_name_the_held_lot():
    state = {"legs": {"ENGUQ": {"hold": {"since": ds(DAY1)}, "side": "long",
                                "shares_remaining": 10}}}
    assert "ENGU-Q is held overnight" in qe._eod_gave_up_order_words(state)
    assert qe._eod_gave_up_order_words({"legs": {}}) == "No order depends on it."


# ── END TO END: the live engine's EXIT reaches the held lot (ENGU-Q live + hold, 2026-10-09) ──
# ENGU-Q is a CROWN_LEGS leg again (MANAGER #102) AND its lot holds overnight (MANAGER #106).
# Nothing between the two halves is stubbed here: api/cloud_signal.step() (fetch=False, a
# temp 1m bar cache, the SHIPPED ENGUQ_335 cfg -- live_since included -- with only its
# strategy swapped for a scripted one) writes the SEED / ENTRY / EXIT rows into its own
# signals.csv, qqq_exec's real _consume_engine_signals reads them on its own cursor, and the
# held lot's prior close / open marks come from that same bar cache (_held_session_marks).

E2E_A, E2E_B, E2E_C = DAY2, MON, (2026, 10, 13)          # Fri, Mon, Tue
E2E_BASE = {"2026-10-08": 710.0, "2026-10-09": 700.0, "2026-10-12": 690.0, "2026-10-13": 705.0}
# (entry, exit, side, entry_px, exit_px): T1 is bought Friday 11:00 and exits Monday 10:30 in
# regular hours; T2 is bought Monday 11:00 and exits on Monday's last 1m bar (15:59), which the
# engine first sees after the bell (an eod_settle row)
E2E_T1 = ("2026-10-09T11:00:00-04:00", "2026-10-12T10:30:00-04:00", 1, 700.90, 690.65)
E2E_T2 = ("2026-10-12T11:00:00-04:00", "2026-10-12T15:59:00-04:00", 1, 690.90, 693.95)


def _e2e_strategy(trades):
    """A strategy module that takes exactly `trades` whenever their entry bar is in the window
    it is handed (matched by bar time); a trade whose exit bar is not in it yet is still open
    (marked at the last close, which run_leg_trades reads as open)."""
    import types
    import pandas as pd
    mod = types.ModuleType("hold_e2e_scripted")
    mod.DEFAULT_PARAMS = {}

    def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     return_trades=False, **kw):
        pos = {pd.Timestamp(x).value: i for i, x in enumerate(index)}
        n, out = len(closes), []
        for entry_ts, exit_ts, side, entry_px, exit_px in trades:
            i = pos.get(pd.Timestamp(entry_ts).value)
            if i is None:
                continue
            j = pos.get(pd.Timestamp(exit_ts).value)
            if j is None:
                out.append((i, n - 1, (float(closes[n - 1]) - entry_px) * side, side, entry_px))
            else:
                out.append((i, j, (exit_px - entry_px) * side, side, entry_px))
        return {"trades": out if return_trades else None, "num_trades": len(out),
                "total_pnl": sum(t[2] for t in out), "win_rate": 0, "profit_factor": 0,
                "max_drawdown": 0, "avg_pnl": 0, "wins": 0, "losses": 0}

    mod.run_backtest = run_backtest
    return mod


class _Engine:
    """api/cloud_signal driven by hand: its own clock (the ledger's emitted_at), its 1m bar
    cache as of `now` (only the bars closed by then, `time` = the bar's START epoch, as the
    live cache holds them) and a real step() on the shipped ENGUQ_335 cfg."""

    def __init__(self, monkeypatch):
        import datetime as dtm
        from zoneinfo import ZoneInfo
        import pandas as pd
        self.ny = ZoneInfo("America/New_York")
        self.paths = cs.DEFAULT_PATHS                     # the env's private cloud_signal home
        os.makedirs(self.paths["ohlc_dir"], exist_ok=True)
        os.makedirs(self.paths["state_dir"], exist_ok=True)
        self.clock = [None]
        clock = self.clock

        class FixedDT(dtm.datetime):
            @classmethod
            def now(cls, tz=None):
                return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
        monkeypatch.setattr(cs, "_dt", SimpleNamespace(datetime=FixedDT, timedelta=dtm.timedelta,
                                                       time=dtm.time, date=dtm.date))
        self.rows = []
        for d, base in sorted(E2E_BASE.items()):
            start = pd.Timestamp(d + " 09:30", tz=cs.TZ)
            for b in range(390):
                o = round(base + 0.01 * b, 2)
                self.rows.append((int((start + pd.Timedelta(minutes=b)).timestamp()), o,
                                  round(o + 0.05, 2), round(o - 0.05, 2), round(o + 0.01, 2), 1000.0))
        self.legs = {"ENGUQ_335": dict(cs.CROWN_LEGS["ENGUQ_335"], warmup_sessions=10,
                                       strategy=_e2e_strategy([E2E_T1, E2E_T2]))}

    def step(self, now):
        aware = now.replace(tzinfo=self.ny)
        self.clock[0] = aware
        cut = aware.timestamp()
        with open(os.path.join(self.paths["ohlc_dir"], "QQQ_1m.csv"), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time", "open", "high", "low", "close", "volume"])
            w.writerows(r for r in self.rows if r[0] + 60 <= cut)
        return cs.step(now=aware, legs=self.legs, paths=self.paths, fetch=False)

    def ledger(self):
        return _rows(self.paths["signals_path"])


def test_end_to_end_the_engine_exit_rows_sell_the_held_enguq_lot(env, monkeypatch):
    """ENGU-Q live + held overnight, end to end: the engine cold-starts the leg (SEED only),
    emits T1's ENTRY Friday 11:01 -> the book buys 10; the 15:59 flatten keeps it (the engine's
    own trade stays open past the bell too: no eod_flat, no settle EXIT); it rides the weekend
    and a restart; Monday's open mark comes from the engine's own cache; the engine's later-day
    EXIT (Monday 10:30 bar, regular hours) sells it at market at Monday's price -- P&L of record
    exit - entry, the gap in its own column, the $400 rail exit - open mark on both rail sites.
    T2 then enters Monday and exits on Monday's last bar, first seen by the post-close step (an
    eod_settle EXIT): nothing is sent after the bell; Tuesday 09:30 sells it at market at
    Tuesday's price, never the row's own Monday price."""
    e = env
    monkeypatch.setattr(qe, "_consume_engine_signals", _REAL_CONSUME)
    monkeypatch.setattr(qe, "_held_session_marks", _REAL_MARKS)
    eng = _Engine(monkeypatch)
    tid1 = cs._trade_id.make("ENGUQ_335", E2E_T1[0], "long")
    tid2 = cs._trade_id.make("ENGUQ_335", E2E_T2[0], "long")
    assert tid1 == TID_E2

    e.tick(at(E2E_A, 9, 40))                  # the book arms its cursor before any row exists
    assert e.state["engine_cursor"] == 0
    seed = eng.step(at(E2E_A, 9, 45, 10))
    assert [r["event"] for r in seed] == ["SEED"] and "live_since=2026-10-09" in seed[0]["reason"]

    # Friday: the ENTRY row -> the book buys 10
    (row,) = eng.step(at(E2E_A, 11, 1, 10))
    assert (row["event"], row["trade_id"], row["ref_price"]) == ("ENTRY", tid1, 700.9)
    e.px["ENGUQ"] = e.fake.fill_px = 700.9
    e.tick(at(E2E_A, 11, 1, 15))
    assert e.lot("ENGUQ")["trade_id"] == tid1 and e.fake.pos == 10
    assert [(s, q) for s, q, _ in e.fake.sent] == [("BUY", 10)]

    # 15:59: the flatten keeps it; after the bell the engine's own trade is still open
    e.px["ENGUQ"] = 703.9
    e.tick(at(E2E_A, 15, 59, 5))
    assert e.lot("ENGUQ")["hold"]["since"] == ds(E2E_A) and e.fake.pos == 10
    assert eng.step(at(E2E_A, 16, 0, 35)) == [], "no eod_flat: the strategy's trade stays open"
    e.tick(at(E2E_A, 16, 0, 40))
    assert e.state["_webull_flat_after_eod"]["held"] == {"ENGUQ": 10}

    # the weekend, a restart
    e.tick(at(SAT, 12, 0))
    e.restart()
    assert e.lot("ENGUQ")["trade_id"] == tid1 and e.books() == {"ENGUQ": 10}

    # Monday 09:31: the open mark from the engine's own 1m cache (Friday's last close 703.90,
    # Monday's first open 690.00 -> gap -139.00)
    eng.step(at(E2E_B, 9, 31, 0))
    e.px["ENGUQ"] = 690.01
    e.tick(at(E2E_B, 9, 31, 5))
    h = e.lot("ENGUQ")["hold"]
    assert (h["close_mark_px"], h["open_mark_px"], h["gap_today_usd"], h["nights"]) == \
        (703.9, 690.0, -139.0, 1)

    # Monday 10:31: the engine's later-day EXIT for the ENTRY it emitted on Friday
    (row,) = eng.step(at(E2E_B, 10, 31, 10))
    assert (row["event"], row["trade_id"], row["ref_price"]) == ("EXIT", tid1, 690.65)
    assert row["reason"] == "strategy_exit" and row["ref_time"] == E2E_T1[1]
    led = eng.ledger()[-1]                     # the exact row the book reads, SIGNAL_COLS
    assert list(led) == list(cs.SIGNAL_COLS)
    assert (led["event"], led["trade_id"], led["ref_price"]) == ("EXIT", tid1, "690.65")
    sent = len(e.fake.sent)
    e.px["ENGUQ"] = e.fake.fill_px = 690.65
    e.tick(at(E2E_B, 10, 31, 15))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent:]] == [("SELL", 10)], "at market, in regular hours"
    assert e.fake.pos == 0 and e.books() == {"ENGUQ": 0}
    (t1,) = e.trades()
    assert t1["trade_id"] == tid1 and t1["exit_ts"].startswith(ds(E2E_B))
    assert float(t1["exit_px"]) == 690.65 and float(t1["pnl"]) == pytest.approx(-102.5)
    assert float(t1["overnight_gap_usd"]) == -139.0 and t1["nights_held"] == "1"
    assert qe._rail_realized_today(e.state) == pytest.approx(6.5), "exit - open mark, the gap left out"
    assert e.adapter._state["daily_pnl"] == pytest.approx(6.5), "the adapter's rail agrees"

    # Monday 11:01: T2's ENTRY -- the leg is free again
    (row,) = eng.step(at(E2E_B, 11, 1, 10))
    assert (row["event"], row["trade_id"]) == ("ENTRY", tid2)
    e.px["ENGUQ"] = e.fake.fill_px = 690.9
    e.tick(at(E2E_B, 11, 1, 15))
    assert e.lot("ENGUQ")["trade_id"] == tid2 and e.fake.pos == 10
    e.px["ENGUQ"] = 693.89
    e.tick(at(E2E_B, 15, 59, 5))
    assert e.lot("ENGUQ")["hold"]["since"] == ds(E2E_B)
    assert eng.step(at(E2E_B, 15, 59, 10)) == [], "its exit bar (15:59) has not closed yet"

    # after the bell: the settle step sees the 15:59 bar -> EXIT tagged eod_settle; the book
    # keeps the lot and sends nothing
    (row,) = eng.step(at(E2E_B, 16, 0, 35))
    assert (row["event"], row["trade_id"], row["ref_price"]) == ("EXIT", tid2, 693.95)
    assert row["reason"] == "strategy_exit; eod_settle"
    sent = len(e.fake.sent)
    e.tick(at(E2E_B, 16, 0, 40))
    cp = e.lot("ENGUQ")["close_pending"]
    assert (cp["reason"], cp["trade_id"], cp["px"]) == ("signal exit", tid2, 693.95)
    assert len(e.fake.sent) == sent and e.fake.pos == 10
    e.tick(at(E2E_C, 9, 25))
    assert len(e.fake.sent) == sent and "ENGUQ" in e.state["legs"]

    # Tuesday 09:30: sold at market at Tuesday's price (705.00), not the row's 693.95
    e.px["ENGUQ"] = e.fake.fill_px = 705.0
    e.tick(at(E2E_C, 9, 30, 5))
    assert "ENGUQ" not in e.state["legs"]
    assert [(s, q) for s, q, _ in e.fake.sent[sent:]] == [("SELL", 10)]
    assert e.fake.pos == 0 and e.books() == {"ENGUQ": 0} and e.fake.refused == []
    t2 = e.trades()[-1]
    assert t2["trade_id"] == tid2 and t2["exit_reason"] == qe.HELD_EXIT_REASON
    assert t2["exit_ts"].startswith(ds(E2E_C)) and float(t2["exit_px"]) == 705.0
    assert float(t2["pnl"]) == pytest.approx(141.0)
    assert float(t2["overnight_gap_usd"]) == pytest.approx(111.0), "Monday's last close 693.90 to 705.00"
    assert qe._rail_realized_today(e.state) == pytest.approx(0.0), "sold at its own open mark"
    assert [r["event"] for r in eng.ledger()] == ["SEED", "ENTRY", "EXIT", "ENTRY", "EXIT"]
    assert not e.state.get("trade_id_checks", {}).get("today"), "every row matched its lot"


def test_status_doc_carries_the_held_lot_and_the_shadow_block_inside_the_firestore_budget(env, monkeypatch):
    """The two 10-09 additions to the status doc side by side: the held lot's fields
    (positions / positions_live / today / rails) and the display-only shadow_trades block
    (MANAGER #87 d). Both present, the shadow rows never in trades_all, the doc inside its
    Firestore budget; with the budget squeezed the block drops its own oldest trades and the
    held lot's fields are untouched."""
    e = env
    _hold_enguq(e)
    e.marks.update(prior_close=690.0, today_open=640.0, today_last=645.0)
    e.px["ENGUQ"] = 645.0
    e.tick(at(DAY2, 9, 45))
    monkeypatch.setattr(qe, "_build_doc", _REAL_BUILD_DOC)
    for name, fn in (("_trade_parity", lambda row, log=print: {}),
                     ("_load_reprice_sidecar", lambda log=print: {}),
                     ("_engine_prices_by_trade", lambda *a, **k: {}),
                     ("_build_price_status", lambda cfg, state, log=print: {}),
                     ("_build_run_location", lambda: {}),
                     ("_build_ratio_health", lambda state, nowdt, cfg=None, log=print: {}),
                     ("_build_keel_status", lambda log=print: {}),
                     ("_build_equity_status", lambda state, nowdt, log=print: {}),
                     ("_live_price_for_leg", lambda leg, log=print: (645.0, 1.0, "live_stream"))):
        monkeypatch.setattr(qe, name, fn)
    shadow = cs.shadow_paths(cs.DEFAULT_PATHS)["signals_path"]
    os.makedirs(os.path.dirname(shadow), exist_ok=True)

    def srow(leg, ev, ts, px, tid, side="long"):
        return {"emitted_at": ts, "leg": leg, "event": ev, "side": side, "ref_time": ts,
                "ref_price": px, "shares": "135", "reason": ev.lower(), "bar_source": "webull",
                "trade_id": tid, "size": "1.0", "keel_size": ""}
    with open(shadow, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cs.SIGNAL_COLS, restval="")
        w.writeheader()
        for i in range(6):
            tid = "NOISE_422_PLAIN-202610%02dT143500Z-S" % (1 + i)
            w.writerow(srow("NOISE_422_PLAIN", "ENTRY", "2026-10-%02dT10:35:00-04:00" % (1 + i), "741.00",
                            tid, side="short"))
            w.writerow(srow("NOISE_422_PLAIN", "EXIT", "2026-10-%02dT11:10:00-04:00" % (1 + i), "739.50",
                            tid, side="short"))

    def build():
        monkeypatch.setattr(qe, "_SHADOW_TRADES_CACHE", {"key": None, "value": None, "logged": None})
        monkeypatch.setattr(qe, "_SHADOW_MARK_CACHE", {})
        return qe._build_doc(e.cfg, e.state, False, -550.0, log=NOOP)

    doc = build()
    held = {k: v for k, v in doc["positions"]["ENGUQ"].items()}
    assert held["held_overnight"] is True and held["gap_usd"] == -500.0
    assert doc["today"]["overnight_gap_usd"] == -500.0 and doc["rails"]["hold_overnight_legs"] == ["ENGUQ"]
    st = doc["shadow_trades"]
    assert "error" not in st and len(st["trades"]) == 6 and st["capped"] == 0
    assert not {t.get("trade_id") for t in st["trades"]} & {t.get("trade_id") for t in doc["trades_all"]}
    size, leaves = qe._fs_size(doc) + 232, qe._fs_leaves(doc)
    assert size <= qe.FS_DOC_BUDGET_BYTES and leaves <= qe.FS_DOC_BUDGET_LEAVES
    json.dumps(doc, allow_nan=False)

    monkeypatch.setattr(qe, "FS_DOC_BUDGET_BYTES", size - 1)
    squeezed = build()
    assert squeezed["shadow_trades"]["capped"] >= 1 and len(squeezed["shadow_trades"]["trades"]) < 6
    assert squeezed["trades_all_trimmed"] == 0, "the block gives way, never trades_all"
    assert squeezed["positions"]["ENGUQ"] == held, "the held lot's fields are never trimmed"
    assert qe._fs_size(squeezed) + 232 <= size - 1
