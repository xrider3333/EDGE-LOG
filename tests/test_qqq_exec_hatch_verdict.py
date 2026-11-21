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
    # off tape (11-20): never judged, tagged instead
    assert v["outside_minute_range"] is True and v["parity_ok"] is None and v["off_tape"] is True
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


def test_book_only_kind_please_is_not_lease():
    r = ("ServerException: HTTP Status: 417, Code: OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION_OPEN, "
         "Msg: Please close your existing long position, RequestID: a4291b")
    assert qe.book_only_kind(r) == "broker"
    assert qe.book_only_kind("cross-host lease held by box") == "infra"


def test_verifier_nits():
    assert qe.book_only_kind("webull adapter halted") == ""
    s = qe._pack_side({"bt": 1, "wb": 1, "fs": "ok", "why": "a|b", "parity_band_c": 0.4,
                       "parity_ok": True, "outside_minute_range": None,
                       "orb_breakout_gap_design": False})
    assert len(s.split("|")) == 12 and s.split("|")[8] == "0.4"


# -- 11-20: the published row reads the hatch verdict, not the old 15c rule ----------
def _side(bt, wb, band, pok, orb=False, omr=False):
    e = wb - bt   # a short-side-agnostic test: edge == slippage, no design part
    return {"bt": bt, "wb": wb, "edge": e, "dsg": 0.0, "slp": e, "unx": 0.0, "why": "",
            "fs": "ok", "parity_band_c": band, "parity_ok": pok,
            "outside_minute_range": omr, "orb_breakout_gap_design": orb}


def _publish(monkeypatch, en, ex):
    monkeypatch.setattr(qe, "_side_parity",
                        lambda row, intent, b, eng: dict(en if intent == "OPEN" else ex))
    monkeypatch.setattr(qe, "_fill_verdict", lambda *a, **k: {})
    return qe._broker_trade_parity({"trade_id": "NOISE_382-20261119T144500Z-L",
                                    "leg": "NOISE", "shares": "10"}, {}, log=NOOP)


def _none_side():
    return {"bt": None, "wb": None, "edge": None, "dsg": 0.0, "slp": 0.0, "unx": 0.0,
            "why": "nofill", "fs": "", "parity_band_c": None, "parity_ok": None,
            "outside_minute_range": None, "orb_breakout_gap_design": False}


def test_1119_0945_pok1_22c_gap_is_not_flagged(monkeypatch):
    # fp en '674.09|674.31|o|-0.22|0|-0.22|0||0.4234|1|0|0'
    out = _publish(monkeypatch, _side(674.31, 674.09, 0.4234, True), _none_side())
    assert out["broker_parity_ok"] is True and out["fp"]["flag"] is False
    assert out["fill_parity_ok"] is True and out["fill_parity_band_c"] == pytest.approx(42.3)
    assert out["fill_parity_outside_minute_range"] is False and out["fill_parity_orb_design"] is False
    assert "15c" not in out["broker_parity_note"] and "42.3c band" in out["broker_parity_note"]


def test_1119_1205_pok0_64c_vs_42_6c_band_is_flagged(monkeypatch):
    # fp en '649.99|649.35|o|-0.64|0|-0.64|0||0.426|0|0|0'
    out = _publish(monkeypatch, _side(649.99, 649.35, 0.426, False), _none_side())
    assert out["broker_parity_ok"] is False and out["fp"]["flag"] is True
    assert out["fill_parity_ok"] is False and out["fill_parity_band_c"] == pytest.approx(42.6)
    assert out["broker_parity_note"].startswith("FLAGGED, a fill 64.0c worse, outside its 42.6c band")
    assert "15c" not in out["broker_parity_note"]
    assert out["fill_parity_side"] == "worse"


def test_two_sided_band_flags_a_better_fill_and_says_so(monkeypatch):
    out = _publish(monkeypatch, _side(649.35, 649.99, 0.426, False), _none_side())
    assert out["broker_parity_ok"] is False and out["fill_parity_side"] == "better"
    assert out["broker_parity_note"].startswith("FLAGGED, a fill 64.0c better, outside its 42.6c band")


def test_parity_side_blank_when_clear_or_unjudged(monkeypatch):
    out = _publish(monkeypatch, _side(674.31, 674.09, 0.4234, True), _none_side())
    assert out["fill_parity_side"] == ""
    out = _publish(monkeypatch, _side(700.0, 699.0, None, None), _none_side())
    assert out["fill_parity_side"] == ""


def test_unjudgeable_side_publishes_none(monkeypatch):
    out = _publish(monkeypatch, _side(700.0, 699.0, None, None), _none_side())
    assert out["broker_parity_ok"] is None and out["fill_parity_ok"] is None
    assert out["fill_parity_band_c"] is None and out["fp"]["flag"] is False


def test_orb_breakout_design_gap_is_never_flagged(monkeypatch):
    out = _publish(monkeypatch, _side(731.0, 732.35, 0.415, False, orb=True), _none_side())
    assert out["fill_parity_orb_design"] is True
    assert out["broker_parity_ok"] is None and out["fp"]["flag"] is False


def test_board_rollup_reads_the_new_flag(monkeypatch):
    good = _publish(monkeypatch, _side(674.31, 674.09, 0.4234, True), _none_side())
    bad = _publish(monkeypatch, _side(649.99, 649.35, 0.426, False), _none_side())
    rows = []
    for i, r in enumerate((good, bad)):
        r = dict(r, leg="NOISE", signal_source="engine", exit_ts=f"2026-11-19 1{i}:00")
        rows.append(r)
    s = qe._broker_parity_summary(rows)
    assert s["checked"] == 2 and s["failed"] == 1
    assert s["legs"]["NOISE"]["flagged"] == 1


def test_fill_parity_fields_never_touch_the_nt_parity_ok(monkeypatch):
    out = _publish(monkeypatch, _side(649.99, 649.35, 0.426, False), _none_side())
    for k in ("parity_ok", "parity_band_c", "parity_side", "outside_minute_range",
              "orb_breakout_gap_design"):
        assert k not in out
    row = {"parity_ok": True}            # the NinjaTrader read on the same row
    row.update(out)
    assert row["parity_ok"] is True and row["fill_parity_ok"] is False


def test_off_tape_fill_never_flags_or_fails(monkeypatch):
    """MANAGER 11-20: an off-tape side (outside its minute, or suspect) is not judged:
    the trade is not flagged and publishes fill_parity_off_tape."""
    en = {"parity_ok": True, "parity_band_c": 0.05, "outside_minute_range": False,
          "orb_breakout_gap_design": False, "slp": 0.0, "unx": 0.0}
    ex = {"parity_ok": None, "parity_band_c": 0.05, "outside_minute_range": True,
          "orb_breakout_gap_design": False, "off_tape": True, "slp": 0.0, "unx": 2.34}
    hv = qe._trade_hatch_verdict(en, ex)
    assert hv["ok"] is True and hv["top"]["fill_parity_off_tape"] is True
    hv2 = qe._trade_hatch_verdict({}, ex)
    assert hv2["ok"] is None and hv2["top"]["fill_parity_off_tape"] is True
    s = {"bt": 609.46, "wb": 607.12, "fs": "suspect", "slp": 0.0, "unx": 2.34}
    v = qe._fill_verdict({"leg": "ORB"}, "CLOSE", s, None, {}, {"bars": {}, "orders": []})
    assert v["parity_ok"] is None and v["off_tape"] is True
