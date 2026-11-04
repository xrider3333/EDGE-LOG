"""WEBULL LIVE SAFETY (2026-11-04, MANAGER #270): S1 weekly / since-arm realised loss stops
and S2 kill_from_broker (the KILL file flattens whatever Webull itself holds).

Harness: no real Firestore/Webull/network -- the SDK client is a MagicMock, every path is a
temp dir (tests/conftest.py's autouse fixtures isolate the adapter singleton and EDGELOG_HOME).
"""
import csv
import datetime
import json
import os
import time
from unittest.mock import MagicMock

import pytest

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731
MON = "2026-11-02"   # a Monday
WED = datetime.datetime(2026, 11, 4, 10, 30, 0)   # inside regular hours


# -- harness ----------------------------------------------------------------------------

def _paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    out.mkdir(exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    monkeypatch.setattr(qe, "STATE_PATH", str(out / "state.json"))
    return out


def _write_broker(rows):
    with open(qe.BROKER_ORDERS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in qe.BROKER_ORDER_COLS})


def _row(ts, leg, intent, side, px, shares=10, mode="LIVE", ok=True):
    return {"ts_et": ts, "leg": leg, "intent": intent, "side": side, "shares": str(shares),
            "signal_id": f"{leg}{ts}{intent}", "mode": mode, "ok": "True" if ok else "False",
            "broker_fill_px": str(px)}


def _trade(ts_open, ts_close, leg, open_px, close_px, mode="LIVE", shares=10):
    return [_row(ts_open, leg, "OPEN", "BUY", open_px, shares, mode),
            _row(ts_close, leg, "CLOSE", "SELL", close_px, shares, mode)]


class _FakeAdapter:
    def __init__(self, mode="LIVE", arm=None):
        self.mode, self.arm = mode, arm

    def effective_mode(self):
        return self.mode, "test"

    def _arm_file(self):
        return self.arm

    def status(self):
        return {"open_legs": [], "believed_positions": {}}


def _says(monkeypatch):
    sent = []
    monkeypatch.setattr(qe, "_say", lambda state, key, pid, note, log=print:
                        (sent.append((key, pid, note)) or ("push", True)))
    return sent


def _cfg(**kw):
    cfg = json.loads(json.dumps(qe.DEFAULT_CONFIG))
    cfg["signal_source"] = "engine"
    cfg.update(kw)
    return cfg


# -- S1 ------------------------------------------------------------------------------------

def test_defaults_are_off_and_nothing_trips(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    _write_broker(_trade(f"{MON} 10:00:00", f"{MON} 11:00:00", "NOISE", 100.0, 50.0))
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter())
    sent = _says(monkeypatch)
    state = {"legs": {}}
    assert qe._check_loss_stops(state, _cfg(), WED, None, None, log=NOOP) is None
    assert not qe._loss_stop_halted(_cfg())
    assert sent == []
    assert qe.DEFAULT_CONFIG["weekly_loss_limit_usd"] is None
    assert qe.DEFAULT_CONFIG["max_loss_since_arm_usd"] is None


def test_weekly_stop_trips_on_realised_live_fills_only(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    rows = []
    rows += _trade("2026-10-30 10:00:00", "2026-10-30 11:00:00", "NOISE", 100.0, 50.0)  # last week
    rows += _trade(f"{MON} 10:00:00", f"{MON} 11:00:00", "NOISE", 100.0, 95.0)          # -50
    rows += _trade("2026-11-03 10:00:00", "2026-11-03 11:00:00", "ORB", 100.0, 96.0)    # -40
    rows += _trade("2026-11-03 12:00:00", "2026-11-03 13:00:00", "ENGUQ", 100.0, 90.0,
                   mode="PAPER")                                                        # not LIVE
    _write_broker(rows)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter())
    sent = _says(monkeypatch)
    cfg = _cfg(weekly_loss_limit_usd=100)
    state = {"legs": {}}
    assert qe._check_loss_stops(state, cfg, WED, None, None, log=NOOP) is None   # -90 > -100
    assert state["loss_stop"]["weekly_pnl"] == -90.0
    rows += _trade("2026-11-04 09:40:00", "2026-11-04 09:50:00", "NOISE", 100.0, 98.0)  # -20
    _write_broker(rows)
    assert qe._check_loss_stops(state, cfg, WED, None, None, log=NOOP) == "weekly"
    assert state["loss_stop"]["weekly_pnl"] == -110.0
    assert state["breaker_tripped"] is True
    path = qe._loss_stop_halt_path(cfg)
    assert os.path.exists(path) and qe._loss_stop_halted(cfg)
    halt = json.load(open(path, encoding="utf-8"))
    assert halt["stop"] == "weekly" and halt["pnl"] == -110.0 and halt["limit"] == 100.0
    assert len(sent) == 1
    key, _pid, note = sent[0]
    assert key == "loss_stop" and note["priority"] == "urgent"
    assert "weekly" in note["message"] and "$110" in note["message"] and "$100" in note["message"]
    # the same tick again, still halted: no second close, no second push
    assert qe._check_loss_stops(state, cfg, WED, None, None, log=NOOP) is None
    assert len(sent) == 1


def test_weekly_stop_closes_open_lots_through_the_breaker_path(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    _write_broker(_trade(f"{MON} 10:00:00", f"{MON} 11:00:00", "NOISE", 100.0, 80.0))  # -200
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter())
    _says(monkeypatch)
    closed = []
    monkeypatch.setattr(qe, "_close_all", lambda state, cfg, reason, q, r, log=print, nowdt=None,
                        legs=None: closed.append((reason, legs)))
    state = {"legs": {"NOISE": {"side": "long", "shares_remaining": 10}}}
    assert qe._check_loss_stops(state, _cfg(weekly_loss_limit_usd=150), WED, None, None,
                                log=NOOP) == "weekly"
    assert closed == [("BREAKER", ["NOISE"])]


def test_halt_survives_a_restart_and_clears_only_when_the_owner_deletes_the_file(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    _write_broker(_trade(f"{MON} 10:00:00", f"{MON} 11:00:00", "NOISE", 100.0, 80.0))  # -200
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter())
    sent = _says(monkeypatch)
    cfg = _cfg(weekly_loss_limit_usd=150)
    state = {"legs": {}}
    assert qe._check_loss_stops(state, cfg, WED, None, None, log=NOOP) == "weekly"
    # restart: a fresh state, the file still there -> halted, nothing re-trips or re-pushes
    state2 = {"legs": {}}
    assert qe._loss_stop_halted(cfg)
    assert qe._check_loss_stops(state2, cfg, WED, None, None, log=NOOP) is None
    assert len(sent) == 1
    # the owner deletes it: the weekly figure counts from now, the same rows do not re-trip
    os.remove(qe._loss_stop_halt_path(cfg))
    later = WED + datetime.timedelta(minutes=5)
    assert qe._check_loss_stops(state, cfg, later, None, None, log=NOOP) is None
    assert state["loss_stop"]["halt"] is None
    assert state["loss_stop"]["weekly_floor"] == later.strftime("%Y-%m-%d %H:%M:%S")
    assert state["loss_stop"]["weekly_pnl"] == 0.0
    assert not os.path.exists(qe._loss_stop_halt_path(cfg))
    # a new Monday resets the floor with the week
    nxt = datetime.datetime(2026, 11, 9, 10, 0, 0)
    qe._check_loss_stops(state, cfg, nxt, None, None, log=NOOP)
    assert state["loss_stop"]["week_anchor"] == "2026-11-09"
    assert state["loss_stop"]["weekly_floor"] is None


def test_since_arm_stop_counts_only_fills_after_the_arm_file(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    arm = tmp_path / "ARM_LIVE"
    arm.write_text("armed", encoding="utf-8")
    arm_dt = datetime.datetime(2026, 11, 3, 9, 0, 0, tzinfo=qe._NY)
    os.utime(str(arm), (arm_dt.timestamp(), arm_dt.timestamp()))
    rows = []
    rows += _trade(f"{MON} 10:00:00", f"{MON} 11:00:00", "NOISE", 100.0, 10.0)        # before arm
    rows += _trade("2026-11-03 10:00:00", "2026-11-03 11:00:00", "NOISE", 100.0, 97.0)  # -30
    rows += _trade("2026-11-04 09:40:00", "2026-11-04 09:50:00", "ORB", 100.0, 96.0)    # -40
    _write_broker(rows)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter(arm=str(arm)))
    sent = _says(monkeypatch)
    cfg = _cfg(max_loss_since_arm_usd=60)
    state = {"legs": {}}
    assert qe._check_loss_stops(state, cfg, WED, None, None, log=NOOP) == "since_arm"
    ls = state["loss_stop"]
    assert ls["arm_anchor"] == "2026-11-03 10:00:00"
    assert ls["since_arm_pnl"] == -70.0
    assert ls["halt"]["stop"] == "since_arm"
    assert "since-arm" in sent[0][2]["message"] and "$70" in sent[0][2]["message"]
    # a restart keeps the anchor (persisted in state), a re-created arm file re-anchors
    assert qe._since_arm_anchor(state, _FakeAdapter(arm=str(arm)), ("LIVE",)) == "2026-11-03 10:00:00"
    new_dt = datetime.datetime(2026, 11, 4, 10, 0, 0, tzinfo=qe._NY)
    os.utime(str(arm), (new_dt.timestamp(), new_dt.timestamp()))
    assert qe._since_arm_anchor(state, _FakeAdapter(arm=str(arm)), ("LIVE",)) is None


def test_loss_stop_halt_blocks_resting_and_routed_entries(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    cfg = _cfg()
    path = qe._loss_stop_halt_path(cfg)
    assert path.startswith(str(tmp_path))
    with open(path, "w", encoding="utf-8") as f:
        f.write("{}")
    assert qe._loss_stop_halted(cfg)
    # the resting gate names it
    adapter = _FakeAdapter(mode="PAPER")
    why = qe._resting_arm_gate({"legs": {}}, cfg, adapter, {}, WED, True)
    assert why and "loss stop" in why
    os.remove(path)
    why2 = qe._resting_arm_gate({"legs": {}}, cfg, adapter, {}, WED, True)
    assert not (why2 and "loss stop" in why2)


# -- S2 ------------------------------------------------------------------------------------

def _broker_cfg(tmp_path, mode="PAPER"):
    cfg = WO.load_config("__no_such_file__")
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _mock_client(qqq=0):
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    _set_positions(client, qqq)
    return client


def _set_positions(client, qqq):
    data = [] if not qqq else [{"symbol": "QQQ", "quantity": abs(qqq),
                                "side": "SHORT" if qqq < 0 else "LONG"}]
    client.account_v2.get_account_position.return_value.json.return_value = {"data": data}


def _paper_adapter(tmp_path, monkeypatch, qqq=0):
    cfg = _broker_cfg(tmp_path)
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    client = _mock_client(qqq)
    monkeypatch.setattr(adapter, "_build_client", lambda mode: client)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    return adapter, client


def _clock(monkeypatch, start=1_000_000.0):
    t = {"now": start}
    monkeypatch.setattr(qe.time, "time", lambda: t["now"])
    return t


def test_no_kill_file_reads_nothing(tmp_path, monkeypatch):
    out = _paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch, qqq=10)
    cfg = _cfg(kill_file=str(out / "KILL"))
    state = {"legs": {}, "_kill_broker": {"last_try": 1.0}}
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) is None
    assert state["_kill_broker"] == {}
    client.account_v2.get_account_position.assert_not_called()
    client.order_v3.place_order.assert_not_called()


def test_kill_flattens_what_webull_holds_then_confirms_flat_once(tmp_path, monkeypatch):
    out = _paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch, qqq=10)
    sent = _says(monkeypatch)
    clock = _clock(monkeypatch)
    cfg = _cfg(kill_file=str(out / "KILL"))
    (out / "KILL").write_text("x", encoding="utf-8")
    state = {"legs": {}}
    # the first tick after the book's own KILL flatten only arms the read
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "armed"
    client.account_v2.get_account_position.assert_not_called()
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "waiting"
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "sent"
    args = client.order_v3.place_order.call_args[0]
    assert args[0] == "ACCT1"
    order = args[1][0]
    assert (order["symbol"], order["side"], order["quantity"], order["order_type"]) == \
        ("QQQ", "SELL", "10", "MARKET")
    assert order["client_order_id"].startswith("qxKILL") and len(order["client_order_id"]) <= 32
    assert state["_kill_broker"]["sent"] == 1
    with open(qe.BROKER_ORDERS_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[-1]["leg"] == "KILL" and rows[-1]["side"] == "SELL" and rows[-1]["shares"] == "10"
    assert rows[-1]["outcome"] == "OK"
    # still held 30 s later: another market order, a fresh id
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "waiting"
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    assert qe.kill_from_broker(state, cfg, WED + datetime.timedelta(seconds=30), log=NOOP) == "sent"
    assert client.order_v3.place_order.call_count == 2
    ids = {c[0][1][0]["client_order_id"] for c in client.order_v3.place_order.call_args_list}
    assert len(ids) == 2
    assert sent == []
    # Webull reads flat: ONE 'flat confirmed' push, then nothing more while the file stays
    _set_positions(client, 0)
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "flat"
    assert len(sent) == 1 and sent[0][0] == "kill_flat"
    assert "flat confirmed" in sent[0][2]["title"] and "2 kill order" in sent[0][2]["message"]
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "confirmed"
    assert client.order_v3.place_order.call_count == 2 and len(sent) == 1
    # file removed: the loop resets so the next kill confirms again
    os.remove(str(out / "KILL"))
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) is None
    assert state["_kill_broker"] == {}


def test_kill_buys_back_a_short_and_waits_outside_regular_hours(tmp_path, monkeypatch):
    out = _paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch, qqq=-5)
    _says(monkeypatch)
    clock = _clock(monkeypatch)
    cfg = _cfg(kill_file=str(out / "KILL"))
    (out / "KILL").write_text("x", encoding="utf-8")
    state = {"legs": {}}
    evening = datetime.datetime(2026, 11, 4, 18, 0, 0)
    assert qe.kill_from_broker(state, cfg, evening, log=NOOP) == "armed"
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    assert qe.kill_from_broker(state, cfg, evening, log=NOOP) == "closed"
    client.order_v3.place_order.assert_not_called()
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "sent"
    order = client.order_v3.place_order.call_args[0][1][0]
    assert (order["side"], order["quantity"]) == ("BUY", "5")


def test_kill_off_mode_and_unreadable_positions_never_send(tmp_path, monkeypatch):
    out = _paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch, qqq=10)
    _says(monkeypatch)
    clock = _clock(monkeypatch)
    cfg = _cfg(kill_file=str(out / "KILL"))
    (out / "KILL").write_text("x", encoding="utf-8")
    state = {"legs": {}}
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "armed"
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    client.account_v2.get_account_position.side_effect = RuntimeError("down")
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) == "unread"
    assert state["_kill_broker"]["unread"] == 1
    client.order_v3.place_order.assert_not_called()
    # OFF mode (no paper keys): nothing at all
    monkeypatch.setattr(adapter, "effective_mode", lambda: (WO.MODE_OFF, "off"))
    clock["now"] += qe.KILL_BROKER_RETRY_SEC
    assert qe.kill_from_broker(state, cfg, WED, log=NOOP) is None


def test_tick_runs_kill_from_broker_only_with_the_kill_file(tmp_path, monkeypatch):
    out = _paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "CONFIG_PATH", str(out / "config.json"))
    calls = []
    monkeypatch.setattr(qe, "kill_from_broker", lambda state, cfg, nowdt, log=print:
                        calls.append(os.path.exists(cfg.get("kill_file") or "")))
    cfg = _cfg(kill_file=str(out / "KILL"), shares={"ORB": 5, "ENGUQ": 5, "NOISE": 5})
    qe.tick(cfg=cfg, state={"legs": {}}, now=WED, log=NOOP)
    assert calls == [False]
    (out / "KILL").write_text("x", encoding="utf-8")
    qe.tick(cfg=cfg, state={"legs": {}}, now=WED, log=NOOP)
    assert calls == [False, True]
