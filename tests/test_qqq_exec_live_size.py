"""api/qqq_exec.py LIVE SIZE (2026-11-19): per-tier live shares, the round-half-up rule, the
open-notional / buying-power refusal, pct-of-equity daily + weekly rails, weekly counts LIVE
rows only, and the balance read's buying-power capture in api/webull_orders.py.

LIVE is simulated by patching qe._broker_is_live; the adapter itself stays OFF, so nothing
can reach Webull. No network, every path under tmp_path."""
import csv
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api import qqq_exec as qe
from api import trade_id
from api import webull_orders as WO

NY = ZoneInfo("America/New_York")
NOOP = lambda *a, **k: None  # noqa: E731
NOW = datetime(2026, 11, 19, 10, 30, tzinfo=NY)


def _isolate(tmp_path, monkeypatch, live):
    out = tmp_path / "out"
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                        ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    pushes = []
    monkeypatch.setattr(qe, "_notify",
                        lambda msg, title, log=print, priority=None: pushes.append(title) or True)
    wo_cfg = WO.load_config(str(out / "none.json"))
    wo_cfg.update(mode="OFF", state_path=str(out / "wo_state.json"), kill_file=str(out / "K"),
                  arm_live_file=str(out / "A"), paper_keys_path=str(out / "p.json"),
                  live_keys_path=str(out / "l.json"))
    adapter = WO.OrderAdapter(config=wo_cfg, log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_broker_is_live", lambda log=print: live)
    return pushes


def _cfg(**kw):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["signal_source"] = "engine"
    cfg["shares"] = {"ORB": 10, "ENGUQ": 5, "NOISE": 10}
    cfg["max_shares_per_leg"] = 60
    cfg.update(kw)
    return cfg


def _state(equity=5000.0, bp=10000.0):
    return {"legs": {}, "events": [],
            "equity": {"first_net_liq_today": equity, "net_liq": equity, "buying_power": bp}}


def _enter(state, cfg, size="", leg="NOISE", px=600.0):
    iso = "2026-11-19T09:40:00-05:00"
    sig = {"NOISE": "NOISE_304", "ORB": "ORB_R6"}[leg]
    ev = {"leg": sig, "event": "ENTRY", "side": "long", "ref_time": iso, "ref_price": px,
          "bar_source": "webull", "trade_id": trade_id.make(sig, iso, "long"), "size": size}
    qe._route_engine_events(state, cfg, [ev], False, log=NOOP, now=NOW)
    return state["legs"].get(leg)


def _orders():
    if not os.path.exists(qe.ORDERS_CSV):
        return []
    with open(qe.ORDERS_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("x,want", [(0.5, 1), (1.4, 1), (1.5, 2), (2.5, 3), (0.49, 0)])
def test_round_half_up(x, want):
    assert qe._round_half_up(x) == want


@pytest.mark.parametrize("equity,tier", [(None, "3000"), (2500, "3000"), (3000, "3000"),
                                         (4999, "3000"), (5000, "5000"), (7999, "5000"),
                                         (8000, "8000"), (50000, "8000")])
def test_tier_selection(equity, tier):
    assert qe._live_tier(_cfg(), equity)[0] == tier


def test_tier_defaults_and_config_override():
    st = {"equity": {"first_net_liq_today": 5200}}
    assert qe._live_leg_limits(_cfg(), st, "NOISE") == (2, 6)
    assert qe._live_leg_limits(_cfg(), st, "ORB") == (3, 9)
    cfg = _cfg(live=dict(qe.DEFAULT_CONFIG["live"], base_shares={"NOISE": 4},
                         max_shares={"NOISE": 5}))
    assert qe._live_leg_limits(cfg, st, "NOISE") == (4, 5)
    # session-start equity wins over a later intraday read
    st2 = {"equity": {"first_net_liq_today": 8100, "net_liq": 4000}}
    assert qe._live_leg_limits(_cfg(), st2, "NOISE") == (3, 9)


@pytest.mark.parametrize("size,want", [(1.0, 1), (1.4, 1), (1.5, 2), (0.2, 1), (2.6, 3), (9, 3)])
def test_live_rounding_rule_at_3k(size, want):
    st = {"equity": {"first_net_liq_today": 3000}}
    assert qe._live_sized_shares(_cfg(), st, "NOISE", size) == want


def test_paper_unaffected(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, live=False)
    lot = _enter(_state(equity=3000, bp=1), _cfg(), size=1.5)
    assert lot["shares_total"] == 15          # 10 x 1.5, no live scaling, no BP refusal
    assert qe._daily_loss_limit(_cfg(), _state()) == 150.0


def test_live_scales_to_tier(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, live=True)
    lot = _enter(_state(equity=5000), _cfg(), size=1.5)
    assert lot["shares_total"] == 3           # 2 x 1.5 = 3
    lot = _enter(_state(equity=8000), _cfg(), size=5.0, leg="ORB")
    assert lot["shares_total"] == 15          # 5 x 5 = 25 clipped to max 15


def test_live_refuses_over_notional_cap(tmp_path, monkeypatch):
    pushes = _isolate(tmp_path, monkeypatch, live=True)
    st = _state(equity=3000, bp=1e9)
    st["legs"]["ORB"] = {"leg": "ORB", "shares_remaining": 7, "entry_px": 600.0}  # 4200 held
    cfg = _cfg(live=dict(qe.DEFAULT_CONFIG["live"], max_open_notional_pct_equity=1.5))
    assert _enter(st, cfg, size=1.0) is None  # 4200 + 600 > 4500
    row = _orders()[-1]
    assert row["action"] == "ENTER" and "notional" in row["reason"]
    assert pushes and any(e["kind"] == "live_cap" for e in st["events"])


def test_live_refuses_over_buying_power(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, live=True)
    st = _state(equity=8000, bp=1000)
    assert _enter(st, _cfg(), size=1.0) is None   # 3 x 600 = 1800 > BP 1000
    assert "buying power" in _orders()[-1]["reason"]


def test_live_refuses_without_equity(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, live=True)
    st = {"legs": {}, "events": []}
    assert _enter(st, _cfg(), size=1.0) is None
    assert "equity not read" in _orders()[-1]["reason"]


def test_live_open_within_caps_passes():
    st = _state(equity=5000, bp=5000)
    assert qe._live_open_refusal(_cfg(), st, "NOISE", 6, 600.0) is None


def test_rails_pct_in_live(monkeypatch):
    monkeypatch.setattr(qe, "_broker_is_live", lambda log=print: True)
    assert qe._daily_loss_limit(_cfg(), _state(equity=5000)) == 100.0   # 2 pct
    assert qe._live_pct_limit(_cfg(), _state(equity=5000), "weekly_loss_pct") == 250.0
    cfg = _cfg(live=dict(qe.DEFAULT_CONFIG["live"], daily_loss_pct=3))
    assert qe._daily_loss_limit(cfg, _state(equity=8000)) == 240.0
    # equity unread: the $ rail still guards
    assert qe._daily_loss_limit(_cfg(), {"legs": {}}) == 150.0


def _write_broker_rows(rows):
    cols = ["ts_et", "mode", "ok", "leg", "intent", "side", "shares", "broker_fill_px", "shadow_px"]
    with open(qe.BROKER_ORDERS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(dict(zip(cols, r)))


def test_weekly_counts_live_rows_only(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch, live=True)

    class A:
        def effective_mode(self):
            return WO.MODE_LIVE, "armed"
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: A())
    monkeypatch.setattr(qe, "_close_all", NOOP)
    monkeypatch.setattr(qe, "_held_legs_to_defer", lambda *a, **k: [])
    monkeypatch.setattr(qe, "_loss_stop_halt_path", lambda cfg: str(tmp_path / "HALT"))
    # PAPER lost 1000 this week, LIVE lost 100 -- 5 pct of 5000 = 250: no trip
    _write_broker_rows([
        ("2026-11-17 10:00:00", "PAPER", "True", "NOISE", "OPEN", "BUY", "10", "600", ""),
        ("2026-11-17 11:00:00", "PAPER", "True", "NOISE", "CLOSE", "SELL", "10", "500", ""),
        ("2026-11-18 10:00:00", "LIVE", "True", "ORB", "OPEN", "BUY", "2", "600", ""),
        ("2026-11-18 11:00:00", "LIVE", "True", "ORB", "CLOSE", "SELL", "2", "550", ""),
    ])
    st = _state(equity=5000)
    assert qe._check_loss_stops(st, _cfg(), NOW, None, None, log=NOOP) is None
    assert st["loss_stop"]["weekly_pnl"] == -100.0
    # a bigger LIVE loss (-300) trips the 250 pct stop
    _write_broker_rows([
        ("2026-11-18 10:00:00", "LIVE", "True", "ORB", "OPEN", "BUY", "6", "600", ""),
        ("2026-11-18 11:00:00", "LIVE", "True", "ORB", "CLOSE", "SELL", "6", "550", ""),
    ])
    st = _state(equity=5000)
    assert qe._check_loss_stops(st, _cfg(), NOW, None, None, log=NOOP) == "weekly"


def test_balance_reads_buying_power_and_logs_keys_once(monkeypatch):
    logs = []
    payload = {"total_net_liquidation_value": "5000", "total_cash_balance": "4000",
               "account_currency_assets": [{"currency": "USD", "day_buying_power": "20000"}]}

    class R:
        def json(self):
            return payload

    class C:
        class account_v2:
            @staticmethod
            def get_account_balance(aid):
                return R()
    ad = WO.OrderAdapter.__new__(WO.OrderAdapter)
    ad.log = logs.append
    ad.effective_mode = lambda: (WO.MODE_LIVE, "")
    ad._client = lambda mode: C()
    ad._account_id = lambda mode, client, purpose="stock": "acct"
    monkeypatch.setattr(WO, "_BALANCE_KEYS_LOGGED", False)
    b = ad.get_stock_account_balance()
    assert b["buying_power"] == 20000.0 and b["net_liq"] == 5000.0
    ad.get_stock_account_balance()
    key_lines = [m for m in logs if "balance reply keys" in m]
    assert len(key_lines) == 1 and "20000" not in key_lines[0]
    assert "account_currency_assets[0].day_buying_power" in key_lines[0]
