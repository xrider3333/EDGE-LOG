"""Review notes on the 2026-09-28 fill-parity build: the NOISE reason after 09-26, the
'level with' wording, the typical (middle) design gap, the round-trip reading kept off
until the owner says yes, per-fill breaker shortfall, the flat breaker push after the
bell, and the empty NinjaTrader columns dropped from published engine rows."""
import csv
from datetime import datetime

import pytest

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731
DAY = "2026-09-28"


def _row(tid, day=DAY, leg="NOISE", side="short", exit_reason="signal exit"):
    return {"leg": leg, "trade_id": tid, "side": side, "shares": "10",
            "entry_px": "100.00", "exit_px": "99.00", "pnl": "10.0",
            "exit_reason": exit_reason, "signal_source": "engine",
            "entry_ts": f"{day} 10:15:11", "exit_ts": f"{day} 11:40:09"}


def _broker(tid, intent, px, ok=True):
    return {"ts_et": f"{DAY} 10:00:00", "leg": "NOISE", "intent": intent,
            "signal_id": qe._broker_signal_id(None, None, intent, trade_id=tid),
            "ok": "True" if ok else "False", "mode": "PAPER", "shares": "10",
            "broker_fill_px": "" if px is None else str(px)}


def _eng(entry, exit_, ref_en="", ref_ex="", dac_en=False, dac_ex=False):
    tag = "decide_at_close: decided at the close"
    return {"ENTRY": {"px": entry, "ref_time": ref_en, "reason": tag if dac_en else ""},
            "EXIT": {"px": exit_, "ref_time": ref_ex,
                     "reason": "strategy_exit" + (f"; {tag}" if dac_ex else "")}}


def _run(row, brokers, eng):
    by_base = qe._broker_orders_by_base(brokers)
    return qe._broker_trade_parity(row, by_base, engine_px={row["trade_id"]: eng}, log=NOOP)


# -- NOISE after 09-26 without the decide-at-close tag ------------------------------
def test_noise_untagged_exit_after_0926_is_a_level_not_the_pre_0926_reason():
    t = "NOISE_382-20260928T141500Z-S"
    out = _run(_row(t), [_broker(t, "OPEN", 100.00), _broker(t, "CLOSE", 99.40)],
               _eng(100.00, 99.00, "2026-09-28T10:15:00-04:00", "2026-09-28T11:35:00-04:00",
                    dac_en=True))
    ex = out["fp"]["ex"]
    assert ex["why"] == "level" and ex["dsg"] == pytest.approx(-0.40) and ex["slp"] == 0
    assert out["fp"]["en"]["why"] == ""          # the tagged entry is slippage as before
    assert "before 09-26" not in qe.FP_WHY[ex["why"]]


def test_noise_untagged_entry_after_0926_says_the_close_decision_did_not_run():
    t = "NOISE_382-20260928T141500Z-S"
    out = _run(_row(t), [_broker(t, "OPEN", 99.80), _broker(t, "CLOSE", 99.00)],
               _eng(100.00, 99.00, "2026-09-28T10:15:00-04:00", "", dac_ex=True))
    assert out["fp"]["en"]["why"] == "nodac" and out["fp"]["en"]["slp"] == 0
    assert "nodac" in qe.DESIGN_ONLY_WHY
    assert "before 09-26" not in qe.FP_WHY["nodac"]


def test_noise_before_0926_keeps_late_keyed_on_the_engine_bar_then_the_row():
    t = "NOISE_382-20260925T141500Z-S"
    out = _run(_row(t, day="2026-09-25"), [_broker(t, "OPEN", 99.80), _broker(t, "CLOSE", 99.10)],
               _eng(100.00, 99.00, "2026-09-25T10:10:00-04:00", ""))
    assert out["fp"]["en"]["why"] == "late" and out["fp"]["ex"]["why"] == "late"
    # the engine's bar wins over the row's own (later) stamp
    out = _run(_row(t, day=DAY), [_broker(t, "OPEN", 99.80), _broker(t, "CLOSE", 99.10)],
               _eng(100.00, 99.00, "2026-09-25T15:55:00-04:00", "2026-09-25T15:55:00-04:00"))
    assert out["fp"]["en"]["why"] == "late" and out["fp"]["ex"]["why"] == "late"


# -- wording ------------------------------------------------------------------------
def test_level_average_never_reads_than_the_backtest_twice():
    assert qe._cents_than(0.0001) == "level with the backtest"
    assert qe._cents_than(-0.012) == "1.2 cents a share worse than the backtest"
    side = {"bt": 1.0, "wb": 1.0, "bk": 1.0, "fs": "ok", "edge": 0.0001, "dsg": 0.0,
            "slp": 0.0001, "unx": 0.0, "why": ""}
    row = {"leg": "NOISE", "signal_source": "engine", "exit_ts": f"{DAY} 10:00:00",
           "broker_parity_ok": True, "fp": {"en": dict(side), "ex": dict(side),
                                            "exec_ps": 0.0002, "flag": False}}
    note = qe._broker_parity_summary([row])["note"]
    assert "were level with the backtest on slippage" in note
    assert "than the backtest than" not in note and "level with than" not in note


# -- typical design gap -------------------------------------------------------------
def _side(edge, why, dsg=None):
    d = edge if dsg is None else dsg
    return {"bt": 1.0, "wb": 1.0, "fs": "ok", "edge": edge, "dsg": d, "slp": edge - d,
            "unx": 0.0, "why": why}


def test_one_multi_day_rail_exit_does_not_swamp_the_typical_design_gap():
    rows = [{"en": _side(-0.02, "late"), "ex": _side(0.04, "late"), "flag": False},
            {"en": _side(0.03, "limit"), "ex": _side(6.715, "eod", dsg=6.715), "flag": False},
            {"en": _side(0.10, ""), "ex": _side(-0.05, ""), "flag": False}]
    blk = qe._roll_block(rows)
    assert blk["avg_dsg_ps"] > 1.0          # the old headline: the 671.5-cent exit dominates
    assert blk["dsg_fills"] == 4
    assert blk["med_dsg_ps"] == pytest.approx(0.035)


# -- round trip: off until the owner says yes ---------------------------------------
def test_round_trip_reading_is_off_by_default_and_flags_when_switched_on(monkeypatch):
    t = "NOISE_382-20260928T141500Z-S"
    brokers = [_broker(t, "OPEN", 99.86), _broker(t, "CLOSE", 99.14)]   # 14c worse twice
    eng = _eng(100.00, 99.00, dac_en=True, dac_ex=True)
    assert qe.PARITY_ROUND_TRIP is False
    assert _run(_row(t), brokers, eng)["broker_parity_ok"] is True
    monkeypatch.setattr(qe, "PARITY_ROUND_TRIP", True)
    out = _run(_row(t), brokers, eng)
    assert out["broker_parity_ok"] is False
    assert out["broker_parity_note"].startswith("FLAGGED, the two fills together")
    # a single-side trade never double-counts
    out = _run(_row(t), [_broker(t, "OPEN", 99.86)], eng)
    assert out["broker_parity_ok"] is True


# -- breaker: per fill, and no push after the bell ----------------------------------
def _write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


@pytest.fixture
def ledgers(tmp_path, monkeypatch):
    tp, bp = str(tmp_path / "trades.csv"), str(tmp_path / "broker_orders.csv")
    monkeypatch.setattr(qe, "TRADES_CSV", tp)
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", bp)

    def put(trades, brokers):
        _write(tp, qe.TRADE_COLS, trades)
        _write(bp, qe.BROKER_ORDER_COLS, brokers)
        qe._BREAKER_ADJ_CACHE["key"] = None
    return put


def test_a_helpful_fill_cannot_cancel_a_bad_one_on_the_same_trade(ledgers):
    # short 10: sold 30c ABOVE the book (+3.00), covered 10c above the book (-1.00).
    # Per trade that nets +2.00 -> 0; per fill the bad cover still counts.
    ledgers([_row("T1")], [_broker("T1", "OPEN", 100.30), _broker("T1", "CLOSE", 99.10)])
    assert qe._breaker_fill_shortfall({"trading_day": DAY, "legs": {}}, log=NOOP) == -1.0


def test_flat_breaker_after_the_bell_trips_but_does_not_push(ledgers, monkeypatch):
    ledgers([_row("T1")], [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10)])
    pushed, events = [], []
    monkeypatch.setattr(qe, "_notify", lambda msg, *a, **k: pushed.append(msg))
    monkeypatch.setattr(qe, "_log_event", lambda *a, **k: events.append(a))
    cfg = {"signal_source": "engine", "daily_loss_limit_usd": 5.0}
    st = {"trading_day": DAY, "realized_pnl_today": -3.0, "legs": {}}
    after = datetime(2026, 9, 28, 16, 3, tzinfo=qe._NY)
    qe._mark_and_check_breaker(st, cfg, None, None, log=NOOP, nowdt=after)
    assert st["breaker_tripped"] is True and pushed == [] and events


# -- published rows -------------------------------------------------------------------
def test_engine_rows_drop_their_empty_ninjatrader_columns_nt_rows_keep_theirs():
    eng_row = {"signal_source": "engine", "nt_entry_px": "", "nt_mult": None,
               "notional_ratio": "", "ratio_at_entry": "0.0412", "pnl": "1.0"}
    nt_row = {"signal_source": "ninjatrader", "nt_entry_px": "", "nt_mult": ""}
    qe._compact_published_trades([eng_row, nt_row])
    assert "nt_entry_px" not in eng_row and "nt_mult" not in eng_row
    assert "notional_ratio" not in eng_row
    assert eng_row["ratio_at_entry"] == "0.0412", "a filled value is never dropped"
    assert nt_row == {"signal_source": "ninjatrader", "nt_entry_px": "", "nt_mult": ""}
