"""MANAGER #135 (2026-10-09): a hand-closed live trade is recorded, never rewritten.

The closing fill's name rides on the round trip (exit_signal: 'Close' = NinjaTrader's own account-level
close), and the shadow row carries a committed manual_exit note from tools/data/paper_manual_exits.json."""
from datetime import datetime

from api import nt_sync, paper, paper_bundle


def _fill(i, dt, action, price, signal):
    return {"exec_id": f"x{i}", "dt": dt, "account": "DEMO7240108", "instrument": "MNQ 12-26",
            "action": action, "qty": 10, "price": price, "commission": 0, "order_id": str(i),
            "signal": signal, "_i": i}


def test_round_trip_carries_the_closing_fill_name():
    t = nt_sync.build_trades([_fill(1, datetime(2026, 10, 8, 16, 55), "SELL", 31027.25, "NZ"),
                              _fill(2, datetime(2026, 10, 9, 15, 39, 52), "BUY", 31071.5, "Close")])[0]
    assert (t["signal"], t["exit_signal"], t["type"]) == ("NZ", "Close", "SHORT")


def test_strategy_exit_keeps_its_own_name():
    t = nt_sync.build_trades([_fill(1, datetime(2026, 10, 7, 14, 0), "BUY", 30000.0, "NZ"),
                              _fill(2, datetime(2026, 10, 7, 15, 0), "SELL", 30010.0, "NZexit")])[0]
    assert t["exit_signal"] == "NZexit"


def test_the_10_08_noise_short_is_on_the_committed_list_and_kept_by_the_bundle():
    e = paper.MANUAL_EXITS[("NOISE_H_RF", 1791478500)]
    assert e["note"].startswith("MANUAL EXIT 10-09 11:39 ET @ 31,071.50")
    assert e["live"]["exit_signal"] == "Close"
    assert "manual_exit" in paper_bundle.FIELDS
    assert paper._load_roll_artifacts(r"C:\no\such\file.json") == {}            # a missing list flags nothing
