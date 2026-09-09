"""Contract tests for the ETF dip book #332 SHADOW paper leg (api/etf_book_shadow.py).

Four things this leg can get wrong that nothing else would catch, all pinned cheaply:

1. IDEMPOTENCY. The leg runs twice most evenings -- once inside api.paper's 16:10 EOD pass
   and once from the runner's own 16:15 hook -- so a second run on the same evening must
   append no bar twice and must not re-record the same signals.
2. SHARE SIZING. $100,000 notional, shares = floor(notional / entry open), $20 a round
   trip. Getting this wrong scales every dollar on the board.
3. THE POSITION SET. The ETFDIP plugins only emit a trade when it CLOSES, so the leg
   recovers open positions by PROBING the plugin with synthetic high/low bars. That is the
   one genuinely clever thing in the module, so it is checked against ground truth taken
   from a full-history run (the trades whose entry_bar <= d < exit_bar) rather than trusted.
4. THE NO-ORDER INVARIANT. This is a SHADOW leg. The module is grepped for anything that
   could reach a broker.

No network: the one test that touches Yahoo replaces the download function.
"""
import io
import os

import numpy as np
import pandas as pd
import pytest

import api.etf_book_shadow as EB
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest


# A short window keeps every test in seconds: enough bars to clear the 200-day trend
# filter's warm-up (trend_len + 10) with room for a few dozen trades on top.
WINDOW_FROM, WINDOW_TO = "2022-01-03", "2025-06-25"


def _qqq(date_to=WINDOW_TO):
    row = find_master("QQQ", EB.TIMEFRAME, EB.SESSION, EB.MASTER_SOURCE)
    if not row:
        pytest.skip("QQQ 1d yahoo_adj master not registered in this checkout")
    return load_master_arrays(row, date_from=WINDOW_FROM, date_to=date_to)


def _leg(sub="QQQ/DBL7L"):
    for lg in EB.book_legs():
        if lg["sub"] == sub:
            return lg
    raise AssertionError(f"{sub} is not one of the seven #332 legs")


# ── 1. idempotency ───────────────────────────────────────────────────────────────
def test_second_run_the_same_evening_appends_nothing_and_repeats(tmp_path, monkeypatch):
    """A master that already carries the day's bar must not grow, and the second
    nightly_update of the same evening must report itself as a repeat."""
    monkeypatch.setattr(EB, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(EB, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(EB, "SIGNALS_CSV", str(tmp_path / "signals.csv"))

    # a tiny master of our own, so nothing real is touched
    path = tmp_path / "master_test.csv"
    days = pd.bdate_range("2026-09-01", "2026-09-04")
    pd.DataFrame({"time": [EB._stamp(d.date()) for d in days],
                  "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                  "volume": 1e6}).to_csv(path, index=False)
    monkeypatch.setattr(EB, "_master_path",
                        lambda tk: ({"filename": "master_test.csv"}, str(path)))
    # Yahoo hands back exactly what the master already has -- nothing new to append.
    monkeypatch.setattr(EB, "_yahoo_daily", lambda tk, start: pd.DataFrame({
        "day": [d.date() for d in days], "open": 100.0, "high": 101.0,
        "low": 99.0, "close": 100.5, "volume": 1e6}))

    before = io.open(path, encoding="utf-8").read()
    now = pd.Timestamp("2026-09-04 17:00", tz="US/Eastern")
    r1 = EB.update_master("QQQ", now=now)
    r2 = EB.update_master("QQQ", now=now)
    assert (r1["appended"], r1["replaced"]) == (0, 0)
    assert (r2["appended"], r2["replaced"]) == (0, 0)
    assert io.open(path, encoding="utf-8").read() == before

    # the compute half: same run_date twice -> the second call knows it is a repeat
    EB._write_state({"run_date": "2026-09-04", "positions": []})
    fake = {"asof": "2026-09-04", "legs": {}, "trades": [], "positions": [],
            "signals": [], "warnings": [], "open_pnl_usd": 0.0, "last_bar": None}
    monkeypatch.setattr(EB, "run_book", lambda **kw: dict(fake))
    monkeypatch.setattr(EB, "update_masters", lambda **kw: [])
    out = EB.nightly_update(now=now)
    assert out["repeat"] is True
    assert not os.path.exists(str(tmp_path / "signals.csv"))


# ── 2. share sizing ──────────────────────────────────────────────────────────────
def test_share_sizing_is_floor_notional_over_entry_open():
    arrays = _qqq()
    r = EB.scan_leg(_leg("QQQ/DBL7L"), arrays)
    assert r["trades"], "the QQQ 7-day-low leg produced no trades in the test window"
    assert EB.NOTIONAL == 100000 and EB.COST_USD_ROUND_TRIP == 20.0
    for t in r["trades"] + r["positions"]:
        px = t["entry_px"]
        want = int(EB.NOTIONAL // px)
        got = int(t.get("size", t.get("shares")))
        assert got == want, f"{px}: sized {got}, expected floor({EB.NOTIONAL}/{px})={want}"
        assert want * px <= EB.NOTIONAL          # never over-notional


def test_plugin_dollars_are_not_multiplied_again():
    """The ETFDIP plugins bill their own dollars, which is why the paper leg carries
    mult 1 / cost_pts 0. pnl_usd must be the plugin's own field, not a re-derivation."""
    arrays = _qqq()
    leg = _leg("QQQ/DBL7L")
    raw = run_backtest(leg["strategy"], arrays=arrays, params=leg["params"],
                       cost_pts=0.0, return_trades=True)
    plugin_net = sum(float(t[2]) for t in raw["trades"])
    ours = sum(t["pnl_usd"] for t in EB.scan_leg(leg, arrays)["trades"])
    assert ours == pytest.approx(plugin_net, abs=0.005)


# ── 3. the position probe, checked against ground truth ──────────────────────────
@pytest.mark.parametrize("sub", ["QQQ/DBL7L", "QQQ/RSI2B", "QQQ/PB20L"])
def test_position_set_matches_full_history_truth_and_diffs_into_signals(sub):
    leg = _leg(sub)
    full = _qqq()
    fidx = [pd.Timestamp(x).date() for x in full["index"]]
    truth_run = run_backtest(leg["strategy"], arrays=full, params=leg["params"],
                             cost_pts=0.0, return_trades=True)
    truth = list((truth_run or {}).get("trades") or [])
    assert truth, f"{sub} produced no trades to check against"

    n = len(fidx)
    checked = 0
    for k in range(n - 200, n - 1, 23):
        cut = _qqq(date_to=str(fidx[k]))
        got = {(p["entry_bar"], p["side"]) for p in EB.scan_leg(leg, cut)["positions"]}
        want = {(int(t[0]), int(t[3])) for t in truth if int(t[0]) <= k < int(t[1])}
        assert got == want, f"{sub} @ {fidx[k]}: probe {got}, truth {want}"
        checked += 1
    assert checked >= 5

    # and the day-over-day diff turns that position set into fills
    a = EB.scan_leg(leg, _qqq(date_to=str(fidx[n - 2])))["positions"]
    b = EB.scan_leg(leg, _qqq(date_to=str(fidx[n - 1])))["positions"]
    d = EB.diff_positions(a, b)
    keys = lambda ps: {(p["sub"], p["entry_date"], p["side"]) for p in ps}
    assert keys(d["opened"]) == keys(b) - keys(a)
    assert keys(d["closed"]) == keys(a) - keys(b)
    assert not (keys(d["opened"]) & keys(d["closed"]))


def test_todays_signals_fill_at_the_next_open():
    """An ENTER/EXIT signal is read on today's close; nothing fills today."""
    arrays = _qqq()
    seen = 0
    for lg in EB.book_legs():
        if lg["ticker"] != "QQQ":
            continue
        for s in EB.scan_leg(lg, arrays)["signals"]:
            assert s["action"] in ("ENTER", "EXIT")
            assert s["fill"] == "next open"
            seen += 1
    assert seen >= 0          # a quiet day is a legitimate result, not a failure


# ── 4. the no-order invariant ────────────────────────────────────────────────────
FORBIDDEN = [
    "place_order", "submit_order", "place_orders", "PlaceOrder", "SubmitOrder",
    "create_order", "new_order", "send_order", "submit_bracket", "OrderRequest",
    "buy(", "sell(", "market_order", "limit_order", "cancel_order",
    "webull_keys", "webull_token", "get_credential", "password", "api_secret",
    "/v1/orders", "AccountOpenOrders", "nt_bridge", "EdgeLogBridge",
]


def test_module_contains_no_order_placement():
    src = io.open(EB.__file__, encoding="utf-8").read()
    # the docstring names some of these on purpose; only real code may not
    body = src.split('"""', 2)[-1]
    hits = [tok for tok in FORBIDDEN if tok in body]
    assert not hits, f"api/etf_book_shadow.py must never reach a broker; found {hits}"
    assert EB.MODE == "SHADOW"
    assert not hasattr(EB, "place_order") and not hasattr(EB, "submit_order")


def test_module_imports_nothing_that_can_trade():
    src = io.open(EB.__file__, encoding="utf-8").read()
    for bad in ("webull", "nt_sync", "ib_insync", "alpaca", "tradovate", "requests.post",
                "urllib.request.urlopen"):
        assert bad not in src.split('"""', 2)[-1], f"unexpected import/use of {bad}"
