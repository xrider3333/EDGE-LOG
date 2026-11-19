"""END-TO-END arm/disarm of LIVE through the real executor route (owner runbook
docs/WEBULL_LIVE_RUNBOOK.md). A real OrderAdapter (LIVE config, fake keys, fake Webull
client) is handed to api/qqq_exec.py's own _mirror_to_broker -- the function every tick's
open/close goes through -- so the path is qqq_exec -> _place_stock_order_with_timeout ->
OrderAdapter.place_stock_order -> client.order_v3.place_order.

  1. Arming LIVE needs a flat PAPER book: with paper shares booked the adapter refuses
     (mode OFF) and the executor sends nothing to the (live) client.
  2. Armed + flat paper: an OPEN reaches the LIVE path and is booked in state.LIVE.json,
     never in the paper state file.
  3. ARM_LIVE removed mid-session while LIVE holds shares: the next OPEN is refused
     (close-only), the CLOSE still goes out to Webull.
No network: the Webull client is a MagicMock, every path is under tmp_path."""
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for p in (ROOT, THIS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import qqq_exec as qe  # noqa: E402
from api import webull_orders as WO  # noqa: E402
from test_webull_orders import _cfg, _mock_client, _write_keys  # noqa: E402
from test_qqq_exec_alerts_in_book import _patch_qqq_paths, _capture_notify  # noqa: E402

NOOP = lambda *a, **k: None  # noqa: E731
LEG = "ORB"


def _live_cfg(tmp_path, armed=True):
    cfg = _cfg(tmp_path, mode="LIVE", rails={"live_legs": [LEG]})
    cfg.setdefault("account", {})["stock_last4"] = "1234"
    _write_keys(cfg["live_keys_path"])
    if armed:
        open(cfg["arm_live_file"], "w").close()
    return cfg


def _wire(tmp_path, monkeypatch, cfg):
    """A fresh real adapter (mode is read at construction, as on a restart) behind the
    executor's own adapter accessor."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    client = _mock_client()
    client.account_v2.get_account_list.return_value.json.return_value = {"data": [
        {"account_id": "ACCT1", "account_number": "LIVE001234",
         "account_class": "INDIVIDUAL_MARGIN"}]}
    monkeypatch.setattr(adapter, "_build_client", lambda mode: client)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    return adapter, client


def _send(state, intent, trade_id, shares=3):
    qe._mirror_to_broker(state, leg=LEG, side="long", shares=shares, shadow_px=500.0,
                         intent=intent, ts="x", trade_id=trade_id, seq=0, log=NOOP)


def _held(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {k: (v or {}).get("qty") for k, v in (d.get("broker_sent_positions") or {}).items()}


def test_arming_live_refuses_while_paper_holds(tmp_path, monkeypatch):
    cfg = _live_cfg(tmp_path)
    with open(cfg["state_path"], "w", encoding="utf-8") as f:
        json.dump({"broker_sent_positions": {LEG: {"symbol": "QQQ", "qty": 5}}}, f)
    adapter, client = _wire(tmp_path, monkeypatch, cfg)
    _capture_notify(monkeypatch)
    mode, why = adapter.effective_mode()
    assert mode == WO.MODE_OFF and "PAPER book still holds" in why
    _send({"legs": {}, "events": []}, "OPEN", "ORB_1-20261119T143100Z-L")
    client.order_v3.place_order.assert_not_called()
    assert not os.path.exists(str(tmp_path / "state.LIVE.json")) or \
        _held(str(tmp_path / "state.LIVE.json")).get(LEG) in (None, 0)


def test_armed_open_goes_live_then_disarm_is_close_only(tmp_path, monkeypatch):
    cfg = _live_cfg(tmp_path)
    live_path = str(tmp_path / "state.LIVE.json")
    adapter, client = _wire(tmp_path, monkeypatch, cfg)
    _capture_notify(monkeypatch)
    assert adapter.effective_mode()[0] == WO.MODE_LIVE
    assert adapter._state_path() == live_path

    # -- armed: the OPEN reaches the LIVE client and is booked in state.LIVE.json --
    # v91.01 LIVE sizing fails closed without today's equity + buying power: seed both
    # (qqq_exec state for the cap / BP check, the adapter for its % daily rail)
    monkeypatch.setattr(WO.OrderAdapter, "_equity_today",
                        {"day": WO._now_ny().strftime("%Y-%m-%d"), "equity": 5000.0}, raising=False)
    state = {"legs": {}, "events": [], "equity": {"first_net_liq_today": 5000.0, "net_liq": 5000.0,
             "buying_power": 10000.0, "day": qe._now_et().strftime("%Y-%m-%d")}}
    _send(state, "OPEN", "ORB_1-20261119T143100Z-L")
    assert client.order_v3.place_order.call_count == 1
    assert _held(live_path).get(LEG) == 3
    assert _held(cfg["state_path"]).get(LEG) in (None, 0), "paper state must stay untouched"

    # -- owner removes ARM_LIVE mid-session --
    os.remove(cfg["arm_live_file"])
    mode, why = adapter.effective_mode()
    assert mode == WO.MODE_LIVE and why.startswith("CLOSE-ONLY")

    # next tick: a new OPEN is refused, nothing new reaches Webull
    _send(state, "OPEN", "ORB_2-20261119T150000Z-L", shares=2)
    assert client.order_v3.place_order.call_count == 1
    assert _held(live_path).get(LEG) == 3

    # the CLOSE of the held lot still goes out
    _send(state, "CLOSE", "ORB_1-20261119T143100Z-L")
    assert client.order_v3.place_order.call_count == 2
    assert _held(live_path).get(LEG) in (None, 0)

    # flat + disarmed = OFF
    assert adapter.effective_mode()[0] == WO.MODE_OFF
