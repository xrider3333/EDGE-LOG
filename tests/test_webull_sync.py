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


# -- reconcile log line: ASCII on a cp1252 console (MANAGER #128, 2026-10-11) ----------------

def _cp1252_log(lines):
    """The PC runner's console: a line that cp1252 cannot encode raises, as print() did."""
    def log(msg):
        msg.encode("cp1252")
        lines.append(msg)
    return log


def test_a_reconcile_drift_is_logged_in_ascii_and_never_reads_as_failed(monkeypatch):
    monkeypatch.setattr(W, "fetch_positions", lambda keys, log=print: {"QQQ": 6.0})
    lines = []
    recon = W.reconcile_and_log([], {"app_key": "k"}, log=_cp1252_log(lines))
    assert recon is not None and recon["ok"] is False
    assert recon["mismatches"] == [{"symbol": "QQQ", "broker": 6.0, "log": 0.0}]
    assert lines == ["  [webull] WARNING reconcile drift: QQQ Webull 6 vs journal 0"]
    assert not any("reconcile failed" in x for x in lines)


def test_a_log_that_cannot_print_keeps_the_reconcile_result(monkeypatch):
    monkeypatch.setattr(W, "fetch_positions", lambda keys, log=print: {"QQQ": 6.0})

    def bad_log(msg):
        raise UnicodeEncodeError("charmap", "x", 0, 1, "boom")
    recon = W.reconcile_and_log([], {}, log=bad_log)
    assert recon is not None and recon["ok"] is False


def test_a_position_read_failure_logs_failed_and_returns_none(monkeypatch):
    def boom(keys, log=print):
        raise RuntimeError("no positions")
    monkeypatch.setattr(W, "fetch_positions", boom)
    lines = []
    assert W.reconcile_and_log([], {}, log=_cp1252_log(lines)) is None
    assert lines == ["  [webull] reconcile failed: RuntimeError: no positions"]


def test_flat_and_matching_logs_nothing(monkeypatch):
    monkeypatch.setattr(W, "fetch_positions", lambda keys, log=print: {})
    lines = []
    recon = W.reconcile_and_log([], {}, log=_cp1252_log(lines))
    assert recon["ok"] is True and recon["flat"] is True and lines == []


def test_every_log_line_in_webull_sync_is_ascii():
    """Every source line that logs or prints is plain ASCII, so the runner's cp1252 console
    can always print it."""
    import inspect
    bad = [(i, ln) for i, ln in enumerate(inspect.getsource(W).splitlines(), 1)
           if ("log(" in ln or "print(" in ln) and not ln.isascii()]
    assert bad == []
