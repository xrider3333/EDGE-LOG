"""Unit tests for api.webull_sync.build_trades — Webull fills -> round-trip trades.

Shares the FIFO open->flat pairing (and the position-flip splitter) with nt_sync, but
with stock P&L and the full symbol kept. These pin the basic round-trip and the flip
fix from issue #7 (a single fill overshooting flat becomes a close + a new open).
"""
from datetime import datetime

from api import webull_sync as W


def _fill(action, qty, price, dt, *, account="Main", symbol="AAPL", exec_id="x", fee=0.0):
    return {"account": account, "symbol": symbol, "action": action, "qty": qty,
            "price": price, "dt": dt, "exec_id": exec_id, "fee": fee}


T0 = datetime(2026, 3, 2, 15, 0, 0)
T1 = datetime(2026, 3, 2, 15, 5, 0)
T2 = datetime(2026, 3, 2, 15, 10, 0)


def test_simple_long_round_trip_stock_pnl():
    trades = W.build_trades([_fill("BUY", 10, 100, T0, exec_id="a"),
                             _fill("SELL", 10, 110, T1, exec_id="b")])
    assert len(trades) == 1
    t = trades[0]
    assert (t["type"], t["entry"], t["exit"], t["size"]) == ("LONG", 100.0, 110.0, 10)
    assert t["grossPnl"] == 100.0                 # (110-100) * 10 shares


def test_position_flip_splits_into_close_and_new_open():
    trades = W.build_trades([_fill("BUY", 10, 100, T0, exec_id="a"),
                             _fill("SELL", 20, 110, T1, exec_id="b"),
                             _fill("BUY", 10, 120, T2, exec_id="c")])
    assert len(trades) == 2
    assert (trades[0]["type"], trades[0]["entry"], trades[0]["exit"], trades[0]["size"]) == \
           ("LONG", 100.0, 110.0, 10)
    assert (trades[1]["type"], trades[1]["entry"], trades[1]["exit"], trades[1]["size"]) == \
           ("SHORT", 110.0, 120.0, 10)
