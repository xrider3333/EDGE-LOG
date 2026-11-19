"""HATCH VERDICT (2026-11-19): the engine stamps a per-fill verdict the page only reads --
a delay-scaled band, outside-the-minute check, ORB breakout-level design, book-only kind."""
import math
import os

import pandas as pd
import pytest

from api import qqq_exec as qe

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "parity0928")
NOOP = lambda *a, **k: None  # noqa: E731


def test_band_formula_and_default_delay():
    assert qe.parity_band_ps(0) == pytest.approx(0.15)
    assert qe.parity_band_ps(60) == pytest.approx(0.15 + 0.726)
    eight = 0.15 + 2 * 0.363 * math.sqrt(8 / 60)
    for bad in (None, "", "x", -3, float("nan")):
        assert qe.parity_band_ps(bad) == pytest.approx(eight)
    assert qe.parity_band_ps(8) == pytest.approx(eight)   # ~41.5c at the usual 8 s


def test_book_only_kind():
    assert qe.book_only_kind("ServerException: HTTP Status: 417, Code: OPENAPI_X") == "broker"
    assert qe.book_only_kind("lease unverifiable: Firestore read failed") == "infra"
    assert qe.book_only_kind("HTTP 429 rate limit") == "infra"
    assert qe.book_only_kind("leg 'ENGUQ' already has an open position") == ""
    assert qe.book_only_kind("") == ""


def _ctx(bars, orders=()):
    return {"bars": bars, "orders": list(orders)}


def _by_base(tid, intent, ts):
    return {qe._broker_signal_id(None, None, intent, trade_id=tid): [
        {"ts_et": ts, "ok": "True", "intent": intent, "shares": "10"}]}


def test_fill_verdict_band_range_and_orb_design(monkeypatch):
    tid = "ORB_R6-20260928T144500Z-S"
    ts = "2026-09-28 10:50:06"
    ep = qe._et_epoch(ts)
    m = int(ep // 60 * 60)
    monkeypatch.setattr(qe, "_broker_order_for",
                        lambda t, i, b: {"ts_et": ts} if t == tid else None)
    bars = {m - 60: (732.0, 732.5, 731.9, 732.33), m: (732.30, 732.40, 732.10, 732.20)}
    row = {"leg": "ORB", "trade_id": tid}
    # signal bar close == backtest price: no design gap, fill within the 6.654 s band
    v = qe._fill_verdict(row, "OPEN", {"bt": 732.33, "wb": 732.32}, None, {},
                         _ctx(bars, [("ORB", ep, 6.654)]))
    assert v["parity_band_c"] == pytest.approx(qe.parity_band_ps(6.654), abs=1e-4)
    assert v["parity_ok"] is True and v["outside_minute_range"] is False
    assert v["orb_breakout_gap_design"] is False
    # fill outside the minute's low/high and > band away
    v = qe._fill_verdict(row, "OPEN", {"bt": 732.33, "wb": 733.0}, None, {}, _ctx(bars))
    assert v["outside_minute_range"] is True and v["parity_ok"] is False
    # breakout level != signal bar close: measured vs the send minute's open
    v = qe._fill_verdict(row, "OPEN", {"bt": 731.00, "wb": 732.35}, None, {}, _ctx(bars))
    assert v["orb_breakout_gap_design"] is True and v["parity_ok"] is True
    # no bar on file: range unknown, parity still judged vs the backtest
    v = qe._fill_verdict(row, "CLOSE", {"bt": 732.33, "wb": 732.40}, None, {}, _ctx({}))
    assert v["outside_minute_range"] is None and v["parity_ok"] is True
    # no fill: nothing judged, never raises
    v = qe._fill_verdict(row, "CLOSE", {"bt": None, "wb": None}, None, {}, None)
    assert v["parity_ok"] is None and v["outside_minute_range"] is None


def test_real_0928_rows_carry_and_publish_the_verdict(monkeypatch):
    class _CS:
        DEFAULT_PATHS = {}

        @staticmethod
        def load_cached_bars(tf, paths):
            return pd.read_csv(os.path.join(FIX, "QQQ_1m.csv"))

    monkeypatch.setattr(qe, "TRADES_CSV", os.path.join(FIX, "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", os.path.join(FIX, "broker_orders.csv"))
    monkeypatch.setattr(qe, "ORDERS_CSV", os.path.join(FIX, "orders.csv"))
    monkeypatch.setattr(qe, "_cs_module", lambda: _CS)
    qe._ENGINE_PX_CACHE["key"] = None
    rows = [dict(r) for r in reversed(qe._all_trades_from_csv())]
    qe._merge_reprice(rows, log=NOOP)
    eng = qe._engine_prices_by_trade(path=os.path.join(FIX, "signals.csv"), bars_dir=FIX, log=NOOP)
    by_base = qe._broker_orders_by_base(qe._all_broker_orders_from_csv())
    qe._apply_broker_parity(rows, by_base, engine_px=eng, log=NOOP)
    r = next(x for x in rows if x["trade_id"] == "ORB_R6-20260928T144500Z-S")
    en = r["fp"]["en"]
    assert en["parity_band_c"] == pytest.approx(qe.parity_band_ps(6.654), abs=1e-4)
    assert en["parity_ok"] is True and en["outside_minute_range"] in (True, False)
    assert en["orb_breakout_gap_design"] is False
    assert "broker_parity_ok" in r                       # the old flag stays
    qe._compact_published_trades(rows)
    parts = r["fp"]["en"].split("|")
    assert len(parts) == 12 and parts[9] == "1" and parts[11] == "0"
    assert float(parts[8]) == pytest.approx(qe.parity_band_ps(6.654), abs=1e-4)
    # book-only rows say what kind of refusal
    qe._apply_book_only(rows, by_base, log=NOOP)
    kinds = {x.get("book_only_kind") for x in rows if x.get("book_only")}
    assert kinds <= {"broker", "infra", ""}


def test_parity_ok_uses_the_design_adjusted_gap(monkeypatch):
    monkeypatch.setattr(qe, "_broker_order_for", lambda t, i, b: None)
    row = {"leg": "ENGUQ", "trade_id": "x"}
    # a 0.90 edge that is all limit design: slippage 0 -> in band
    s = {"bt": 700.0, "wb": 699.1, "edge": 0.9, "dsg": 0.9, "slp": 0.0, "unx": 0.0}
    assert qe._fill_verdict(row, "OPEN", s, None, {}, _ctx({}))["parity_ok"] is True
    s = dict(s, dsg=0.0, slp=-0.9)
    assert qe._fill_verdict(row, "OPEN", s, None, {}, _ctx({}))["parity_ok"] is False
