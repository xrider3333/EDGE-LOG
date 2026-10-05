"""Ledger unify 13 (owner 'go for all', 2026-10-03): every money figure on HOME > WEBULL
PAPER uses the P&L of record. Two new published fields under `today`:

  legs_record    {leg: {pnl, n, book}} -- each strategy's TODAY figure: the trades that
                 CLOSED today (New York close day), each at _curve_pnl, the same rule
                 today.realized_pnl_record sums (it used to be the raw book rows of
                 today.trades, where an unmarked 'nan' exit read $0).
  breaker_input  the exact figure the daily loss breaker compared with the limit this
                 tick (realized + fill shortfall + open marks), never re-derived.

Shadow legs never reach trades.csv, so they can never add to either figure.
"""
import csv
import json
import os
import re
from datetime import datetime

import pytest

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731
DAY = "2026-10-05"           # a Monday
YDAY = "2026-10-02"          # the Friday before


def _write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _broker(tid, intent, px, ok=True, leg="NOISE", reason=""):
    return {"ts_et": f"{DAY} 10:00:00", "leg": leg, "intent": intent,
            "signal_id": qe._broker_signal_id(None, None, intent, trade_id=tid),
            "ok": "True" if ok else "False", "mode": "PAPER", "shares": "10", "sent": "True",
            "broker_fill_px": "" if px is None else str(px), "reason": reason}


def _trade(tid, leg, side, entry, exit_, pnl, entry_day=DAY, exit_day=DAY):
    return {"leg": leg, "entry_ts": f"{entry_day} 10:15:00", "exit_ts": f"{exit_day} 11:40:00",
            "side": side, "shares": "10", "entry_px": entry, "exit_px": exit_, "pnl": pnl,
            "exit_reason": "signal exit", "signal_source": "engine", "trade_id": tid}


@pytest.fixture
def box(tmp_path, monkeypatch):
    """Every file _build_doc / tick() reads or writes -> tmp; the slow or outside-world
    builders stubbed exactly like tests/test_qqq_exec_cum_pnl.py does."""
    out = tmp_path / "qqq_exec_out"
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    for attr, fname in (("CONFIG_PATH", "config.json"), ("STATE_PATH", "state.json"),
                        ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                        ("BROKER_ORDERS_CSV", "broker_orders.csv")):
        monkeypatch.setattr(qe, attr, str(out / fname))
    monkeypatch.setattr(qe, "_notify", NOOP)
    monkeypatch.setattr(qe, "_trade_parity", lambda row, log=print: {})
    monkeypatch.setattr(qe, "_load_reprice_sidecar", lambda log=print: {})
    monkeypatch.setattr(qe, "_engine_prices_by_trade", lambda *a, **k: {})
    monkeypatch.setattr(qe, "_build_price_status", lambda cfg, state, log=print: {})
    monkeypatch.setattr(qe, "_build_run_location", lambda: {})
    monkeypatch.setattr(qe, "_build_ratio_health", lambda state, nowdt, cfg=None, log=print: {})
    monkeypatch.setattr(qe, "_build_broker_status", lambda state, log=print: {})
    monkeypatch.setattr(qe, "_build_trade_id_status", lambda state, day: {})
    qe._BREAKER_ADJ_CACHE["key"] = None

    def put(trades=(), brokers=(), orders=()):
        _write(qe.TRADES_CSV, qe.TRADE_COLS, list(trades))
        _write(qe.BROKER_ORDERS_CSV, qe.BROKER_ORDER_COLS, list(brokers))
        _write(qe.ORDERS_CSV, qe.ORDER_COLS, list(orders))
        qe._BREAKER_ADJ_CACHE["key"] = None
    return put


def _doc(state=None, unrealized=0.0):
    st = {"trading_day": DAY, "legs": {}}
    st.update(state or {})
    return qe._build_doc({}, st, False, unrealized, log=NOOP)


# ── today.legs_record ─────────────────────────────────────────────────────────────────
def test_captured_fills_win_and_an_unmarked_exit_no_longer_reads_zero(box):
    """Both Webull fills captured: the strategy's TODAY is the fill P&L. The second trade's
    book exit was never marked (pnl 'nan', the 09-17/18 after-the-bell case) -- the old
    figure read it as $0; its fills now count."""
    box([_trade("T1", "NOISE", "short", "100.0", "99.0", "10.0"),
         _trade("T2", "NOISE", "long", "100.0", "nan", "nan")],
        [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10),
         _broker("T2", "OPEN", 100.05), _broker("T2", "CLOSE", 100.65)])
    rec = _doc()["today"]["legs_record"]
    # T1 (99.10 - 99.80) x -1 x 10 = +7.00 ; T2 (100.65 - 100.05) x 10 = +6.00
    assert rec == {"NOISE": {"pnl": 13.0, "n": 2, "book": 0}}


def test_missing_fill_counts_at_the_book_price_and_is_labelled(box):
    box([_trade("T1", "NOISE", "short", "100.0", "99.0", "10.0")], [])
    assert _doc()["today"]["legs_record"] == {"NOISE": {"pnl": 10.0, "n": 1, "book": 1}}


def test_suspect_fill_uses_the_book_price_on_that_side(box, monkeypatch):
    base = qe._broker_signal_id(None, None, "OPEN", trade_id="T3")
    monkeypatch.setitem(qe.SUSPECT_BROKER_FILLS, base, "below that minute's low")
    box([_trade("T3", "ORB", "long", "100.0", "101.0", "10.0")],
        [_broker("T3", "OPEN", 95.00, leg="ORB"), _broker("T3", "CLOSE", 100.90, leg="ORB")])
    # entry at the book's 100.00 (the 95.00 fill does not fit the tape), exit at 100.90
    assert _doc()["today"]["legs_record"] == {"ORB": {"pnl": 9.0, "n": 1, "book": 1}}


def test_refused_open_counts_at_book_price_and_a_rail_refusal_adds_nothing(box):
    """Webull refused the OPEN (HTTP 417): a BOOK ONLY trade -- counted at the book price,
    like the hero and the curve, and labelled. An entry the rails refused never became a
    trade at all (orders.csv REFUSED row only), so it adds nothing."""
    box([_trade("T4", "NOISE", "short", "100.0", "99.5", "5.0")],
        [_broker("T4", "OPEN", None, ok=False, reason="HTTP 417 OPENAPI_GENERATE_NEW_SHORT_POSITION")],
        [{"ts_et": f"{DAY} 10:20:00", "leg": "ENGUQ", "action": "ENTER", "side": "long",
          "shares": "10", "reason": "REFUSED -- breaker/fill-feed/price-feed/kill blocked"}])
    doc = _doc()
    assert doc["today"]["legs_record"] == {"NOISE": {"pnl": 5.0, "n": 1, "book": 1}}
    (row,) = doc["trades_all"]
    assert row["book_only"] is True


def test_opened_yesterday_closed_today_counts_today_closed_yesterday_does_not(box):
    box([_trade("T0", "ENGUQ", "long", "100.0", "102.0", "20.0", entry_day=YDAY, exit_day=YDAY),
         _trade("T5", "ENGUQ", "long", "100.0", "101.0", "10.0", entry_day=YDAY)],
        [_broker("T5", "OPEN", 100.10, leg="ENGUQ"), _broker("T5", "CLOSE", 101.00, leg="ENGUQ")])
    assert _doc()["today"]["legs_record"] == {"ENGUQ": {"pnl": 9.0, "n": 1, "book": 0}}


def test_open_lot_is_not_a_trade_and_legs_add_up_to_the_hero_today(box):
    box([_trade("T1", "NOISE", "short", "100.0", "99.0", "10.0"),
         _trade("T3", "ORB", "long", "100.0", "101.0", "10.0")],
        [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10)])
    lot = {"side": "long", "shares_remaining": 10, "shares_total": 10, "entry_px": 100.0,
           "entry_ts": f"{DAY} 13:00:00", "trade_id": "T9"}
    doc = _doc({"legs": {"ENGUQ": lot}, "_unrl_by_leg": {"ENGUQ": -4.0}}, unrealized=-4.0)
    rec = doc["today"]["legs_record"]
    assert set(rec) == {"NOISE", "ORB"}                    # the open ENGU-Q lot is not in it
    assert doc["positions"]["ENGUQ"]["unrealized"] == -4.0
    assert round(sum(b["pnl"] for b in rec.values()), 2) == doc["today"]["realized_pnl_record"]
    json.dumps(doc["today"], allow_nan=False)


def test_legs_record_never_raises_and_stays_small():
    assert qe._legs_record_today(None, DAY) == {}
    assert qe._legs_record_today([{"exit_ts": None}, {"leg": "ORB", "exit_ts": f"{DAY} 10:00:00",
                                                       "pnl": "nan"}], DAY) == \
        {"ORB": {"pnl": 0.0, "n": 1, "book": 1}}
    many = [{"leg": "NOISE", "exit_ts": f"{DAY} 10:00:00", "pnl": "1", "pnl_record_src": "webull"}] * 40
    assert qe._legs_record_today(many, DAY) == {"NOISE": {"pnl": 40.0, "n": 40, "book": 0}}


# ── today.breaker_input ──────────────────────────────────────────────────────────────
def test_breaker_input_is_only_published_on_its_own_day(box):
    box()
    assert _doc()["today"]["breaker_input"] is None                       # not checked yet
    assert _doc({"_breaker_input": {"day": YDAY, "pnl": -40.0}})["today"]["breaker_input"] is None
    assert _doc({"_breaker_input": {"day": DAY, "pnl": -12.345}})["today"]["breaker_input"] == -12.35


def _tick_cfg(tmp_path, limit):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg.update(signal_source="engine", daily_loss_limit_usd=limit,
               shares={"ORB": 10, "ENGUQ": 10, "NOISE": 10},
               kill_file=str(tmp_path / "NO_KILL_HERE"))
    return cfg


def _open_state(realized=-3.0):
    return {"trading_day": DAY, "realized_pnl_today": realized,
            "legs": {"NOISE": {"leg": "NOISE", "side": "long", "shares_remaining": 10,
                               "shares_total": 10, "entry_px": 100.0,
                               "entry_ts": f"{DAY} 09:50:00", "trade_id": "T9"}}}


PRE_OPEN = datetime(2026, 10, 5, 8, 0, 0)   # a session day, before the window: no signals


def test_published_daily_stop_equals_the_breaker_input_in_the_same_tick(box, tmp_path, monkeypatch):
    """Open NOISE lot marked 1.00 under its entry (-10.00), Webull's entry fill 25 cents
    worse (-2.50 shortfall), -3.00 realized: the breaker compares -15.50 with the limit,
    and the published figure is that same -15.50 -- open marks and fill shortfall
    included, which the hero's today figure would not show."""
    box([], [_broker("T9", "OPEN", 100.25)])
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (99.0, "test"))
    seen = []
    real = qe._note_breaker_input
    monkeypatch.setattr(qe, "_note_breaker_input",
                        lambda state, total: (seen.append(round(total, 2)), real(state, total)))
    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path, 150.0), state=_open_state(),
                              now=PRE_OPEN, log=NOOP)
    assert seen == [-15.5]
    t = doc["today"]
    assert t["breaker_input"] == -15.5
    assert t["breaker_input"] == round(t["realized_pnl"] + t["breaker_fill_adj"] + t["unrealized_pnl"], 2)
    assert not doc["breaker_tripped"]


def test_a_trip_publishes_the_figure_it_tripped_on_not_a_re_derived_one(box, tmp_path, monkeypatch):
    """Same book under a $10 limit: the breaker trips at -15.50 and its flatten books more
    loss in the same tick. The published figure is the -15.50 the breaker compared (the
    one in its own log line), not today's parts added up again after the flatten."""
    box([], [_broker("T9", "OPEN", 100.25)])
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (99.0, "test"))

    def flatten(state, cfg, reason, *a, **k):
        state["realized_pnl_today"] = round(state["realized_pnl_today"] - 20.0, 2)
        state["legs"].clear()
    monkeypatch.setattr(qe, "_close_all", flatten)
    monkeypatch.setattr(qe, "_log_event", NOOP)
    lines = []
    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path, 10.0), state=_open_state(),
                              now=PRE_OPEN, log=lines.append)
    (trip,) = [ln for ln in lines if "BREAKER TRIPPED" in ln]
    tripped_at = float(re.search(r"P&L (-?\d+\.\d+)", trip).group(1))
    t = doc["today"]
    assert doc["breaker_tripped"] is True
    assert t["breaker_input"] == tripped_at == -15.5
    assert round(t["realized_pnl"] + t["breaker_fill_adj"] + t["unrealized_pnl"], 2) != -15.5


def test_flat_book_publishes_realized_plus_the_fill_shortfall(box, tmp_path):
    """Flat: the breaker's input is today's realized plus the shortfall of today's closed
    trades at Webull's fills (here -3.00), with no open marks."""
    box([_trade("T1", "NOISE", "short", "100.0", "99.0", "10.0")],
        [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10)])
    st = {"trading_day": DAY, "realized_pnl_today": 10.0, "legs": {}}
    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path, 150.0), state=st, now=PRE_OPEN, log=NOOP)
    assert doc["today"]["breaker_input"] == 7.0
    assert doc["today"]["breaker_fill_adj"] == -3.0
    # and the strategy's TODAY at the P&L of record reads the same +7.00 fills figure
    assert doc["today"]["legs_record"] == {"NOISE": {"pnl": 7.0, "n": 1, "book": 0}}


def test_after_a_trip_the_published_figure_keeps_up_with_the_close_out(box, tmp_path, monkeypatch):
    """Review 2026-10-05: tripped and flat, the breaker makes no further check, but the
    figure it would count keeps moving (the close-out booked more loss). The next tick
    publishes today's realized + the fill shortfall again -- the trip itself unchanged."""
    box([], [_broker("T9", "OPEN", 100.25)])
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (99.0, "test"))

    def flatten(state, cfg, reason, *a, **k):
        state["realized_pnl_today"] = round(state["realized_pnl_today"] - 20.0, 2)
        state["legs"].clear()
    monkeypatch.setattr(qe, "_close_all", flatten)
    monkeypatch.setattr(qe, "_log_event", NOOP)
    cfg = _tick_cfg(tmp_path, 10.0)
    cfg, state, doc = qe.tick(cfg=cfg, state=_open_state(), now=PRE_OPEN, log=NOOP)
    assert doc["today"]["breaker_input"] == -15.5 and state["breaker_tripped"] is True
    cfg, state, doc = qe.tick(cfg=cfg, state=state, now=PRE_OPEN, log=NOOP)
    t = doc["today"]
    assert doc["breaker_tripped"] is True
    assert t["breaker_input"] == round(t["realized_pnl"] + t["breaker_fill_adj"], 2) == -23.0


def test_kill_day_keeps_the_figure_current_and_never_trips(box, tmp_path):
    """KILL file present: the breaker makes no check (and must not trip), but the flat
    book's figure is still today's realized + the fill shortfall, not a stale one."""
    box([_trade("T1", "NOISE", "short", "100.0", "99.0", "10.0")],
        [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10)])
    kill = tmp_path / "KILL"
    kill.write_text("")
    cfg = _tick_cfg(tmp_path, 5.0)
    cfg["kill_file"] = str(kill)
    st = {"trading_day": DAY, "realized_pnl_today": -10.0, "legs": {}, "kill_done": True,
          "_breaker_input": {"day": DAY, "pnl": -1.0}}
    cfg, state, doc = qe.tick(cfg=cfg, state=st, now=PRE_OPEN, log=NOOP)
    assert doc["today"]["breaker_input"] == -13.0
    assert not doc["breaker_tripped"]


def test_a_nan_realized_figure_publishes_none_not_zero(box, tmp_path):
    """An exit booked at a nan price can leave realized_pnl_today NaN: there is then no
    breaker figure to show -- None (the page falls back to its estimate), never 0."""
    box()
    st = {"trading_day": DAY, "realized_pnl_today": float("nan"), "legs": {}}
    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path, 150.0), state=st, now=PRE_OPEN, log=NOOP)
    assert doc["today"]["breaker_input"] is None


def test_a_fill_captured_in_the_tick_reaches_the_figure_in_the_same_tick(box, tmp_path, monkeypatch):
    """Review 2026-10-05: the breaker checks before the tick's broker fill capture. When
    the capture brings in Webull's CLOSE fill (10 cents worse a share here, -1.00), the
    published figure takes it in the same tick (+7.00), not one tick late (+8.00) --
    so the bar never reads better than the hero's today line."""
    trades = [_trade("T1", "NOISE", "short", "100.0", "99.0", "10.0")]
    box(trades, [_broker("T1", "OPEN", 99.80)])

    def capture(state, cfg, nowdt, active, log=print):
        box(trades, [_broker("T1", "OPEN", 99.80), _broker("T1", "CLOSE", 99.10)])
    monkeypatch.setattr(qe, "_maybe_capture_broker_fills", capture)
    st = {"trading_day": DAY, "realized_pnl_today": 10.0, "legs": {}}
    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path, 150.0), state=st, now=PRE_OPEN, log=NOOP)
    assert doc["today"]["breaker_input"] == 7.0
    assert doc["today"]["breaker_fill_adj"] == -3.0
    assert doc["today"]["realized_pnl_record"] == 7.0


def test_the_after_capture_refresh_never_makes_the_figure_read_better(box, tmp_path, monkeypatch):
    """Anything after the breaker's check that would make the figure BETTER is not taken
    on that tick: the bar keeps what the breaker compared."""
    box()

    def capture(state, cfg, nowdt, active, log=print):
        state["realized_pnl_today"] = state["realized_pnl_today"] + 5.0
    monkeypatch.setattr(qe, "_maybe_capture_broker_fills", capture)
    st = {"trading_day": DAY, "realized_pnl_today": -10.0, "legs": {}}
    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path, 150.0), state=st, now=PRE_OPEN, log=NOOP)
    assert doc["today"]["breaker_input"] == -10.0


def test_kill_day_with_lots_still_open_counts_their_last_marks(box, tmp_path):
    """Review 2026-10-05: a kill close-out that failed or is partial leaves lots open.
    The figure is then today's realized + the fill shortfall + the last per-leg marks the
    breaker took for the legs STILL open (-3.00 - 2.50 - 10.00), not the stale figure from
    before the kill -- and a leg that is no longer open adds nothing."""
    box([], [_broker("T9", "OPEN", 100.25)])
    kill = tmp_path / "KILL"
    kill.write_text("")
    cfg = _tick_cfg(tmp_path, 5.0)
    cfg["kill_file"] = str(kill)
    st = _open_state()
    st.update(kill_done=True, _unrl_by_leg={"NOISE": -10.0, "ENGUQ": -99.0},
              _breaker_input={"day": DAY, "pnl": -1.0})
    cfg, state, doc = qe.tick(cfg=cfg, state=st, now=PRE_OPEN, log=NOOP)
    assert doc["today"]["breaker_input"] == -15.5
    assert not doc["breaker_tripped"]
