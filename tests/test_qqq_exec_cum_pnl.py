"""The equity-curve series api/qqq_exec.py publishes as cum_pnl (2026-09-21).

WHY. Owner: "webull paper chart doesnt show all the trades". An exit the adapter could not
mark is written to trades.csv as pnl "nan" (the EOD flatten fired past the bell on 09-17 and
09-18, with no live price to mark against). float("nan") does not raise, so the running total
turned NaN for that leg and for TOTAL on every later day, and the web chart read NaN as $0 --
the three after-the-bell trades vanished from the curve. The fix counts a trade the way the web
tab's table, calendar and KPIs already do (pnl when it is a number, else the tape-repriced
real_pnl, else 0) and builds the curve after the reprice merge, so real_pnl is there to use.
The web tab now draws its own curve from trades_all; these pin the published copy.
"""
import json

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731

# trades_all exactly as published on 2026-09-21 (newest first), trimmed to what the curve reads
LIVE = [
    {"leg": "ORB", "entry_ts": "2026-09-18 15:50:37", "exit_ts": "2026-09-18 16:00:05", "pnl": "nan", "real_pnl": "11.9"},
    {"leg": "ENGUQ", "entry_ts": "2026-09-18 13:11:45", "exit_ts": "2026-09-18 16:00:03", "pnl": "nan", "real_pnl": "45.2"},
    {"leg": "ENGUQ", "entry_ts": "2026-09-17 15:08:24", "exit_ts": "2026-09-17 16:00:04", "pnl": "nan", "real_pnl": "0.65"},
    {"leg": "NOISE", "entry_ts": "2026-09-16 14:10:17", "exit_ts": "2026-09-16 14:35:20", "pnl": "-13.1", "real_pnl": "-34.5"},
    {"leg": "NOISE", "entry_ts": "2026-09-16 09:55:11", "exit_ts": "2026-09-16 13:15:31", "pnl": "-3.15", "real_pnl": "-2.6"},
    {"leg": "ORB", "entry_ts": "2026-09-03 12:30:18", "exit_ts": "2026-09-03 15:58:05", "pnl": "2.89", "real_pnl": "2.7"},
    {"leg": "NOISE", "entry_ts": "2026-09-03 12:30:16", "exit_ts": "2026-09-03 15:58:05", "pnl": "2.89", "real_pnl": "2.7"},
]


def _without_real_pnl(rows):
    return [{k: v for k, v in r.items() if k != "real_pnl"} for r in rows]


def _pts(series):
    return [(p["date"], p["cum_pnl"]) for p in series]


def test_an_unmarked_exit_no_longer_wipes_out_the_rest_of_the_curve():
    """The live failure, before the reprice has run: the nan rows count as 0 and every
    point stays a real number -- nothing after 09-17 turns into NaN."""
    cum = qe._cum_pnl_by_leg(_without_real_pnl(LIVE))
    json.dumps(cum, allow_nan=False)            # raises on any NaN/inf left in the series
    assert _pts(cum["total"]) == [("2026-09-03", 5.78), ("2026-09-16", -10.47),
                                  ("2026-09-17", -10.47), ("2026-09-18", -10.47)]


def test_a_repriced_exit_counts_at_its_tape_price():
    cum = qe._cum_pnl_by_leg(LIVE)
    assert _pts(cum["ENGUQ"]) == [("2026-09-17", 0.65), ("2026-09-18", 45.85)]
    assert _pts(cum["ORB"]) == [("2026-09-03", 2.89), ("2026-09-18", 14.79)]
    assert _pts(cum["NOISE"]) == [("2026-09-03", 2.89), ("2026-09-16", -13.36)]
    assert _pts(cum["total"]) == [("2026-09-03", 5.78), ("2026-09-16", -10.47),
                                  ("2026-09-17", -9.82), ("2026-09-18", 47.28)]
    # every closed trade is in the curve: TOTAL ends on the closed P&L the tab shows
    assert cum["total"][-1]["cum_pnl"] == round(sum(qe._curve_pnl(t) for t in LIVE), 2)


def test_a_marked_exit_keeps_its_own_pnl():
    """real_pnl is only the fallback. A trade the adapter did mark keeps that number, as
    the web table does (09-16 NOISE reads -13.10, not the repriced -34.50)."""
    assert qe._curve_pnl({"pnl": "-13.1", "real_pnl": "-34.5"}) == -13.1
    assert qe._curve_pnl({"pnl": "nan", "real_pnl": "0.65"}) == 0.65
    assert qe._curve_pnl({"pnl": 2.5}) == 2.5
    for junk in ({}, {"pnl": ""}, {"pnl": None}, {"pnl": "nan"}, {"pnl": "inf", "real_pnl": "nan"},
                 {"pnl": "garbled", "real_pnl": ""}):
        assert qe._curve_pnl(junk) == 0.0, junk


def test_build_doc_builds_the_curve_after_the_reprice_merge(tmp_path, monkeypatch):
    """real_pnl only exists once _merge_reprice has run, so the published curve has to be
    built after it -- built before (the old order), the fallback has nothing to fall back to."""
    raw = _without_real_pnl(reversed(LIVE))          # trades.csv order, no real_pnl yet
    sidecar = {(r["leg"], r["entry_ts"]): {"real_pnl": r["real_pnl"]} for r in LIVE}
    monkeypatch.setattr(qe, "ORDERS_CSV", str(tmp_path / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(tmp_path / "trades.csv"))
    # feature #56 (engine-vs-broker parity) reads BROKER_ORDERS_CSV inside _build_doc --
    # isolate it from the real EDGELOG_HOME exactly like ORDERS_CSV/TRADES_CSV above
    # (the file need not exist: _all_broker_orders_from_csv returns [] when it doesn't).
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(tmp_path / "broker_orders.csv"))
    monkeypatch.setattr(qe, "_all_trades_from_csv", lambda cap=500: [dict(r) for r in raw])
    monkeypatch.setattr(qe, "_trade_parity", lambda row, log=print: {})
    monkeypatch.setattr(qe, "_load_reprice_sidecar", lambda log=print: sidecar)
    monkeypatch.setattr(qe, "_build_price_status", lambda cfg, state, log=print: {})
    monkeypatch.setattr(qe, "_build_run_location", lambda: {})
    monkeypatch.setattr(qe, "_build_ratio_health", lambda state, nowdt, cfg=None, log=print: {})
    monkeypatch.setattr(qe, "_build_broker_status", lambda state, log=print: {})
    monkeypatch.setattr(qe, "_build_trade_id_status", lambda state, day: {})
    doc = qe._build_doc({}, {"trading_day": "2026-09-21"}, False, 0.0, log=NOOP)
    json.dumps(doc["cum_pnl"], allow_nan=False)
    assert _pts(doc["cum_pnl"]["total"])[-1] == ("2026-09-18", 47.28)
    assert len(doc["trades_all"]) == len(LIVE)
