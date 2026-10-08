"""Small labels from the 2026-09-28 parity audit (owner decisions B and D):
the EOD phone line leads with the P&L of record (Webull fills) and the fills-vs-backtest
check, and the engine signal ledger's notional `shares` column never reaches the book."""
import csv
import datetime

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731


def test_eod_summary_leads_with_the_pnl_of_record(monkeypatch):
    pushed = []
    monkeypatch.setattr(qe, "_notify", lambda msg, title, log=print, priority=None: pushed.append(msg))
    monkeypatch.setattr(qe, "_log_event", NOOP)
    nowdt = datetime.datetime(2026, 9, 28, 16, 10, 0)
    doc = {"today": {"trades": [1, 2, 3], "realized_pnl": -88.95, "realized_pnl_record": -84.5},
           "parity": {"checked": 0, "failed": 0},
           "broker_parity": {"checked": 10, "failed": 3, "board_flag": False,
                             "checked_all": 31, "flagged_all": 5},
           "feed_days": [{"date": "2026-09-28", "uptime_pct": 1.0}], "breaker_tripped": False}
    logs = []
    qe._maybe_send_eod_summary({}, doc, nowdt, log=logs.append)
    # WEBULL PUSH PLAN 10-07, group G: the phone note leads with the P&L of record in plain words;
    # the full line (both figures, the fills-vs-backtest check) is the log line and event
    assert "Lost $84 today at Webull prices" in pushed[0]
    line = next(ln for ln in logs if "EOD summary" in ln)
    assert "P&L $-84.50 at Webull fills (book $-88.95)" in line
    # the last-20 window, and the whole history beside it so an old flag stays visible
    assert "fills vs backtest checked/flagged last 10/3, all 31/5" in line


def test_engine_events_never_carry_the_notional_shares(tmp_path, monkeypatch):
    p = tmp_path / "signals.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares",
                    "reason", "bar_source", "trade_id", "size", "keel_size"])
        w.writerow(["2026-09-28T10:50:05.8-04:00", "ORB_R6", "ENTRY", "short",
                    "2026-09-28T10:45:00-04:00", "732.33", "136", "", "webull",
                    "ORB_R6-20260928T144500Z-S", "1.0", ""])

    class _CS:
        DEFAULT_PATHS = {"signals_path": str(p)}
    monkeypatch.setattr(qe, "_cs_module", lambda: _CS)
    monkeypatch.setattr(qe, "_log_event", NOOP)
    state = {"engine_cursor": 0}
    now = datetime.datetime(2026, 9, 28, 10, 50, 10)
    ev = qe._consume_engine_signals(state, {}, now, log=NOOP)
    assert len(ev) == 1
    assert "shares" not in ev[0], "the ledger's notional 136 must never reach the book"
