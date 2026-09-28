"""Daily loss breaker input with the P&L OF RECORD (owner decision 2026-09-28 (B)):
changing the breaker's input is allowed only if it stays FAIL-SAFE. Webull's fills may
only make the breaker's figure MORE negative (min(0, fill-based - book) per closed trade
and per open lot); a side with no captured fill keeps the book's value, and any error
falls back to exactly the old input."""
import csv
import os
from datetime import datetime

import pytest

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731
DAY = "2026-09-28"


def _write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _broker(tid, intent, px, ok=True):
    return {"ts_et": f"{DAY} 10:00:00", "leg": "NOISE", "intent": intent,
            "signal_id": qe._broker_signal_id(None, None, intent, trade_id=tid),
            "ok": "True" if ok else "False", "mode": "PAPER", "shares": "10",
            "broker_fill_px": "" if px is None else str(px)}


@pytest.fixture
def ledgers(tmp_path, monkeypatch):
    tp, bp = str(tmp_path / "trades.csv"), str(tmp_path / "broker_orders.csv")
    monkeypatch.setattr(qe, "TRADES_CSV", tp)
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", bp)
    qe._BREAKER_ADJ_CACHE["key"] = None

    def put(trades, brokers):
        _write(tp, qe.TRADE_COLS, trades)
        _write(bp, qe.BROKER_ORDER_COLS, brokers)
        qe._BREAKER_ADJ_CACHE["key"] = None
    return put


def _trade(tid, pnl="10.0", entry="100.0", exit_="99.0", side="short", day=DAY):
    return {"leg": "NOISE", "entry_ts": f"{day} 10:15:00", "exit_ts": f"{day} 11:40:00",
            "side": side, "shares": "10", "entry_px": entry, "exit_px": exit_, "pnl": pnl,
            "exit_reason": "signal exit", "signal_source": "engine", "trade_id": tid}


def test_worse_fills_lower_the_breaker_input(ledgers):
    ledgers([_trade("T1")], [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10)])
    # fills: (99.10 - 99.80) * -1 * 10 = +7.00 vs the book's +10.00 -> -3.00
    assert qe._breaker_fill_shortfall({"trading_day": DAY, "legs": {}}, log=NOOP) == -3.0


def test_better_fills_never_raise_it(ledgers):
    ledgers([_trade("T1")], [_broker("T1", "OPEN", 100.30), _broker("T1", "CLOSE", 98.70)])
    assert qe._breaker_fill_shortfall({"trading_day": DAY, "legs": {}}, log=NOOP) == 0.0


def test_no_fill_keeps_the_book_value(ledgers):
    ledgers([_trade("T1")], [_broker("T1", "OPEN", None), _broker("T1", "CLOSE", 98.0, ok=False)])
    assert qe._breaker_fill_shortfall({"trading_day": DAY, "legs": {}}, log=NOOP) == 0.0


def test_other_days_do_not_count(ledgers):
    ledgers([_trade("T0", day="2026-09-25")],
            [_broker("T0", "OPEN", 99.0), _broker("T0", "CLOSE", 100.0)])
    assert qe._breaker_fill_shortfall({"trading_day": DAY, "legs": {}}, log=NOOP) == 0.0


def test_open_lot_worse_entry_fill_counts(ledgers):
    ledgers([], [_broker("T2", "OPEN", 100.25)])
    state = {"trading_day": DAY,
             "legs": {"NOISE": {"trade_id": "T2", "entry_px": 100.0, "side": "long",
                                "shares_remaining": 10}}}
    assert qe._breaker_fill_shortfall(state, log=NOOP) == -2.5


def test_errors_fall_back_to_the_old_input(monkeypatch):
    qe._BREAKER_ADJ_CACHE["key"] = None
    monkeypatch.setattr(qe, "_all_broker_orders_from_csv",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert qe._breaker_fill_shortfall({"trading_day": DAY, "legs": {}}, log=NOOP) == 0.0


def test_breaker_trips_on_the_fill_shortfall_but_not_on_the_book_alone(ledgers, monkeypatch):
    """Book: -3.00 realized, open lot flat at its mark -> -3.00, under a $5 limit. With
    Webull's entry fill 25 cents worse on the open 10-share lot the input is -5.50 and
    the breaker trips -- sooner, never later."""
    ledgers([], [_broker("T2", "OPEN", 100.25)])
    closed = []
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (100.0, "test"))
    monkeypatch.setattr(qe, "_close_all", lambda *a, **k: closed.append(a[2]))
    monkeypatch.setattr(qe, "_notify", NOOP)
    monkeypatch.setattr(qe, "_log_event", NOOP)
    cfg = {"signal_source": "engine", "daily_loss_limit_usd": 5.0}

    def _state():
        return {"trading_day": DAY, "realized_pnl_today": -3.0,
                "legs": {"NOISE": {"trade_id": "T2", "entry_px": 100.0, "side": "long",
                                   "shares_remaining": 10}}}

    st = _state()
    qe._mark_and_check_breaker(st, cfg, None, None, log=NOOP)
    assert closed == ["BREAKER"] and st["breaker_tripped"] is True
    assert st["_breaker_fill_adj"] == -2.5

    # same book, no captured fill -> the old input, no trip
    ledgers([], [_broker("T2", "OPEN", None)])
    closed.clear()
    st = _state()
    qe._mark_and_check_breaker(st, cfg, None, None, log=NOOP)
    assert closed == [] and not st.get("breaker_tripped")


def test_a_flat_book_trips_without_closing_anything(ledgers, monkeypatch):
    """Review 2026-09-28: with no lots open the check used to return before looking at
    the total at all, so a fill shortfall that pushed today past the limit was only
    acted on once the NEXT entry opened (and was flattened at once). Flat now trips on
    the spot -- breaker_tripped blocks new entries -- and never calls _close_all."""
    # book +10.00 on T1, Webull fills +7.00 -> shortfall -3.00; realized -3.00 -> -6.00
    ledgers([_trade("T1")], [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10)])
    closed, pushed = [], []
    monkeypatch.setattr(qe, "_close_all", lambda *a, **k: closed.append(a[2]))
    monkeypatch.setattr(qe, "_notify", lambda msg, *a, **k: pushed.append(msg))
    monkeypatch.setattr(qe, "_log_event", NOOP)
    cfg = {"signal_source": "engine", "daily_loss_limit_usd": 5.0}
    st = {"trading_day": DAY, "realized_pnl_today": -3.0, "legs": {}}
    in_session = datetime(2026, 9, 28, 11, 45, tzinfo=qe._NY)
    assert qe._mark_and_check_breaker(st, cfg, None, None, log=NOOP, nowdt=in_session) == 0.0
    assert st["breaker_tripped"] is True and closed == [] and pushed
    assert st["_breaker_fill_adj"] == -3.0

    # the book alone (-3.00, no fill shortfall) stays under the $5 limit: no trip
    ledgers([_trade("T1")], [_broker("T1", "OPEN", None)])
    st = {"trading_day": DAY, "realized_pnl_today": -3.0, "legs": {}}
    qe._mark_and_check_breaker(st, cfg, None, None, log=NOOP)
    assert not st.get("breaker_tripped")
