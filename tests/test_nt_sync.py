"""Unit tests for api.nt_sync — NinjaTrader fills -> round-trip trades.

This is financially load-bearing and was previously untested: build_trades pairs raw
fills into trades with FIFO position tracking, and calc_pnl converts price moves to
dollars using the per-instrument tick schedule. These tests pin the correct
round-trip cases (simple long/short, scale-in/out, grouping, unclosed) and calc_pnl,
and DOCUMENT two known limitations the pairing shares with index.html:

  * a single fill that overshoots flat (a position FLIP) is mispaired, and
  * get_base drops digits from a root, so 'M2K' (Micro Russell) parses to 'MK'
    and never matches its PRESETS / FEE_PER_SIDE entries.

Both are pinned so the behavior stays visible; see the notes on those tests.
"""
from datetime import datetime

import pytest

from api import nt_sync as N


def _fill(i, action, qty, price, dt, *, comm=0.0, account="Sim", instrument="MNQ 03-26",
          order_id="", exec_id=None):
    return {"exec_id": exec_id or f"e{i}", "dt": dt, "account": account,
            "instrument": instrument, "action": action, "qty": qty, "price": price,
            "commission": comm, "order_id": order_id, "_i": i}


T0 = datetime(2026, 3, 2, 15, 0, 0)
T1 = datetime(2026, 3, 2, 15, 5, 0)
T2 = datetime(2026, 3, 2, 15, 10, 0)


# ── calc_pnl ────────────────────────────────────────────────────────────────────

def test_calc_pnl_futures_uses_tick_schedule():
    # NQ: tick value 5.00, tick size 0.25 -> 10 pts = 40 ticks * $5 = $200
    assert N.calc_pnl("NQ", "LONG", 100, 110, 1, 0.0) == (200.0, 200.0)


def test_calc_pnl_short_sign_and_size():
    # short profits when price falls; x2 size doubles it
    assert N.calc_pnl("NQ", "SHORT", 110, 100, 2, 0.0) == (400.0, 400.0)


def test_calc_pnl_subtracts_fees_for_net():
    # MNQ: tick value 0.50 -> 10 pts = 40 ticks * $0.50 = $20 gross; net = gross - fees
    assert N.calc_pnl("MNQ", "LONG", 100, 110, 1, 1.90) == (20.0, 18.1)


def test_calc_pnl_non_future_is_plain_price_move():
    # unknown symbol -> stock math: (exit-entry)*dir*size
    assert N.calc_pnl("AAPL", "LONG", 100, 110, 10, 0.0) == (100.0, 100.0)


def test_calc_pnl_non_long_side_is_treated_as_short():
    """side is 'LONG' or anything-else==short (d = 1 if 'LONG' else -1)."""
    g_short, _ = N.calc_pnl("NQ", "SHORT", 100, 110, 1, 0.0)
    g_other, _ = N.calc_pnl("NQ", "anything", 100, 110, 1, 0.0)
    assert g_short == g_other == -200.0


# ── get_base ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,base", [
    ("ES 03-26", "ES"), ("MNQ 03-26", "MNQ"), ("es", "ES"), ("MES 06-26", "MES"),
])
def test_get_base_normal(raw, base):
    assert N.get_base(raw) == base


def test_get_base_keeps_digits_in_root():
    """Fix for issue #7: the root is the first token, so a digit-bearing root like
    Micro Russell 'M2K' survives and matches PRESETS / FEE_PER_SIDE."""
    assert N.get_base("M2K 03-26") == "M2K"
    assert N.get_base("M2K") in N.FEE_PER_SIDE
    assert N.get_base("") == ""


# ── build_trades: correct round-trip pairing ────────────────────────────────────

def test_simple_long_round_trip():
    trades = N.build_trades([_fill(0, "BUY", 1, 100, T0),
                             _fill(1, "SELL", 1, 110, T1)])
    assert len(trades) == 1
    t = trades[0]
    assert (t["symbol"], t["type"], t["entry"], t["exit"], t["size"]) == \
           ("MNQ", "LONG", 100.0, 110.0, 1)
    assert t["grossPnl"] == 20.0                 # MNQ 10pts
    assert t["fees"] == pytest.approx(0.95 * 1 * 2)   # micro fee schedule, both sides
    assert t["pnl"] == pytest.approx(20.0 - 1.90)
    assert t["durationSecs"] == 300


def test_simple_short_round_trip():
    trades = N.build_trades([_fill(0, "SELL", 1, 110, T0),
                             _fill(1, "BUY", 1, 100, T1)])
    assert len(trades) == 1
    t = trades[0]
    assert (t["type"], t["entry"], t["exit"]) == ("SHORT", 110.0, 100.0)
    assert t["grossPnl"] == 20.0                 # short profits as price falls


def test_scale_in_then_scale_out_averages_prices():
    # BUY 1@100 + BUY 1@102 -> avg entry 101, size 2; SELL 2@110 -> exit 110
    trades = N.build_trades([_fill(0, "BUY", 1, 100, T0),
                             _fill(1, "BUY", 1, 102, T1),
                             _fill(2, "SELL", 2, 110, T2)])
    assert len(trades) == 1
    t = trades[0]
    assert (t["entry"], t["exit"], t["size"]) == (101.0, 110.0, 2)
    assert t["grossPnl"] == 36.0                 # (110-101)=9pts * 40/pt * 0.50 * ... = 36


def test_partial_exits_average_to_flat():
    # BUY 2@100 -> SELL 1@110 -> SELL 1@120 : avg exit 115, size 2
    trades = N.build_trades([_fill(0, "BUY", 2, 100, T0),
                             _fill(1, "SELL", 1, 110, T1),
                             _fill(2, "SELL", 1, 120, T2)])
    assert len(trades) == 1
    assert (trades[0]["entry"], trades[0]["exit"], trades[0]["size"]) == (100.0, 115.0, 2)


def test_unclosed_position_emits_nothing():
    assert N.build_trades([_fill(0, "BUY", 1, 100, T0)]) == []


def test_two_round_trips_emit_two_trades():
    trades = N.build_trades([_fill(0, "BUY", 1, 100, T0), _fill(1, "SELL", 1, 110, T1),
                             _fill(2, "SELL", 1, 120, T2), _fill(3, "BUY", 1, 115, T2)])
    assert len(trades) == 2
    assert {t["type"] for t in trades} == {"LONG", "SHORT"}


def test_positions_grouped_by_account_and_instrument():
    trades = N.build_trades([
        _fill(0, "BUY", 1, 100, T0, instrument="MNQ 03-26"),
        _fill(1, "SELL", 1, 110, T1, instrument="MNQ 03-26"),
        _fill(2, "SELL", 1, 200, T0, instrument="MES 03-26"),
        _fill(3, "BUY", 1, 190, T1, instrument="MES 03-26"),
    ])
    assert {(t["symbol"], t["type"]) for t in trades} == {("MNQ", "LONG"), ("MES", "SHORT")}


def test_position_flip_splits_into_close_and_new_open():
    """Fix for issue #7: a single fill that overshoots flat (long 1, then SELL 2) closes
    the long at the crossing and opens a short for the remainder. The later cover-buy
    then closes the short — two clean round-trips, not one mangled trade."""
    trades = N.build_trades([_fill(0, "BUY", 1, 100, T0),
                             _fill(1, "SELL", 2, 110, T1),
                             _fill(2, "BUY", 1, 120, T2)])
    assert len(trades) == 2
    long_t, short_t = trades
    assert (long_t["type"], long_t["entry"], long_t["exit"], long_t["size"]) == \
           ("LONG", 100.0, 110.0, 1)
    assert (short_t["type"], short_t["entry"], short_t["exit"], short_t["size"]) == \
           ("SHORT", 110.0, 120.0, 1)


def test_larger_flip_closes_full_position_then_opens_remainder():
    # long 2 -> SELL 3 (close 2, open short 1) -> BUY 1 (close short)
    trades = N.build_trades([_fill(0, "BUY", 2, 100, T0),
                             _fill(1, "SELL", 3, 110, T1),
                             _fill(2, "BUY", 1, 120, T2)])
    assert len(trades) == 2
    assert (trades[0]["type"], trades[0]["size"], trades[0]["exit"]) == ("LONG", 2, 110.0)
    assert (trades[1]["type"], trades[1]["size"], trades[1]["entry"]) == ("SHORT", 1, 110.0)


def test_flip_that_never_returns_flat_emits_only_the_closed_leg():
    # long 1 -> SELL 2 : closes the long, opens a short that stays open (no second trade)
    trades = N.build_trades([_fill(0, "BUY", 1, 100, T0),
                             _fill(1, "SELL", 2, 110, T1)])
    assert len(trades) == 1
    assert (trades[0]["type"], trades[0]["entry"], trades[0]["exit"]) == ("LONG", 100.0, 110.0)


# ── _parse_dt ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("s,expected", [
    ("2026-03-02 15:04:05", datetime(2026, 3, 2, 15, 4, 5)),
    ("2026-03-02 15:04",    datetime(2026, 3, 2, 15, 4, 0)),
    ("03/02/2026 15:04:05", datetime(2026, 3, 2, 15, 4, 5)),
    ("2026-03-02T15:04:05", datetime(2026, 3, 2, 15, 4, 5)),   # ISO fallback
])
def test_parse_dt_supported_formats(s, expected):
    assert N._parse_dt(s) == expected


def test_parse_dt_garbage_returns_none():
    assert N._parse_dt("not a date") is None
    assert N._parse_dt("") is None
