"""api/nt_held_back.py - the NT8 board's 'NEEDS YOU' list from the recover watchdog's log (2026-10-09)."""
from api import nt_held_back as H

POS = '{"positions":[{"account":"DEMO7240108","instrument":"MNQ 12-26","side":"Short","qty":10,"avg_price":31027.25}]}'
STOP = [
    "2026-10-08 12:35:20  === recover start (WhatIf=False) ===",
    "2026-10-08 12:35:40  STOP: the account is holding a position while strategies are down:",
    "2026-10-08 12:35:40    " + POS,
    "2026-10-08 12:35:40    not ENGU-Q's adoptable trade: the position is Short and ENGU-Q only goes long",
]
LIVE = [{"instrument": "MNQ 12-26", "side": "Short", "qty": 10}]
ORDERS = [{"instrument": "MNQ 12-26", "type": "StopMarket", "state": "Working", "stop": 31348.75}]


def test_stop_holds_noise_with_its_stop_and_since():
    later = [s.replace("12:35", "12:38") for s in STOP]
    got = H.build(STOP + later, LIVE, ORDERS)
    assert len(got) == 1
    g = got[0]
    assert (g["strategy"], g["instrument"], g["side"], g["qty"], g["avg"], g["stop"]) == \
           ("NOISE", "MNQ", "SHORT", 10, 31027.25, 31348.75)
    assert g["since"].startswith("2026-10-08T12:35:40")           # the first hold of the run, not the latest
    assert "flatten" in g["reason"]


def test_held_back_line_names_only_the_held_strategy():
    lines = ["2026-10-09 08:44:00  HELD BACK for a person: EdgeLogNOISE - the account holds an open position on its contract:",
             "2026-10-09 08:44:00    " + POS,
             "2026-10-09 08:44:10  PARTIAL: EdgeLogENGUQ1m Realtime; HELD BACK for a person: EdgeLogNOISE (open position on its contract)"]
    assert [g["strategy"] for g in H.build(lines, LIVE, [])] == ["NOISE"]


def test_flat_account_or_a_later_recovery_clears_it():
    assert H.build(STOP, [], ORDERS) == []                          # flattened by hand: gone before the next pass
    rec = STOP + ["2026-10-09 08:41:51  RECOVERED: EdgeLogNOISE, EdgeLogENGUQ1m are Realtime"]
    assert H.build(rec, LIVE, ORDERS) == []
    assert H.build(["2026-10-09 08:50:00  healthy: bridge up, all expected strategies Realtime"], None) == []


def test_bridge_down_lets_the_log_decide_and_bad_input_never_raises():
    assert [g["stop"] for g in H.build(STOP, None, None)] == [None]
    assert H.build(["garbage", "", "2026-10-08 12:35:40  STOP: the account is holding a position", "  {bad json"]) == []
    assert H.state.__call__(None, None) == [] or isinstance(H.state(None, None), list)
