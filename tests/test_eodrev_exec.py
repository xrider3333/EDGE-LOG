import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from api import eodrev_exec as ex
from api import webull_orders as wo

ET = ZoneInfo("America/New_York")
DAY = dt.date(2026, 11, 16)          # a Monday


def _sig(tmp, day=DAY, **kw):
    s = {"date": day.isoformat(), "asof_et": "15:20:00", "status": "OK", "k": 3,
         "long": [{"sym": s, "px": px, "exch": "NASDAQ"} for s, px in
                  (("AAPL", 230.0), ("MSFT", 410.0), ("NVDA", 140.0))],
         "short": [{"sym": s, "px": px, "exch": "NYSE"} for s, px in
                   (("JPM", 250.0), ("XOM", 115.0), ("LLY", 800.0))],
         "panel_date": "2026-11-13"}
    s.update(kw)
    with open(os.path.join(tmp, f"signal_{day.isoformat()}.json"), "w") as f:
        json.dump(s, f)
    return s


class FakeAd:
    def __init__(self, refuse=()):
        self.sent, self.refuse = [], set(refuse)

    def place_stock_order(self, **k):
        self.sent.append(k)
        bad = (k["symbol"], k["order_type"]) in self.refuse
        return {"ok": not bad, "reason": "417 refused" if bad else "",
                "client_order_id": k["signal_id"], "parts": [{"client_order_id": k["signal_id"]}]}


def _run(tmp_path, ad, monkeypatch, fills=None, notes=None):
    p = ex.paths(str(tmp_path))
    fills = fills or {}
    monkeypatch.setattr(ex, "lookup", lambda a, rec: fills.get(rec["_sid"], {
        "status": "FILLED", "filled": rec.get("_qty", 0), "price": None}))
    notes = notes if notes is not None else []
    return ex.run_day(p, now_fn=lambda: dt.datetime(2026, 11, 16, 15, 27, tzinfo=ET),
                      adapter=ad, log=lambda *a: None,
                      notify=lambda m, **k: notes.append(m), sleep=False), notes


def test_read_signal_cases(tmp_path):
    cfg = dict(ex.DEFAULTS)
    sig, why = ex.read_signal(DAY, cfg, str(tmp_path))
    assert sig is None and why[0] == "alert"
    _sig(str(tmp_path), status="SKIP", reason="half day")
    assert ex.read_signal(DAY, cfg, str(tmp_path))[1][0] == "skip"
    _sig(str(tmp_path), date="2026-11-13")
    assert ex.read_signal(DAY, cfg, str(tmp_path))[1][0] == "alert"
    _sig(str(tmp_path), short=[{"sym": "QQQ", "px": 600}, {"sym": "A", "px": 70}, {"sym": "B", "px": 80}])
    assert "QQQ" in ex.read_signal(DAY, cfg, str(tmp_path))[1][1]
    _sig(str(tmp_path))
    sig, why = ex.read_signal(DAY, cfg, str(tmp_path))
    assert why is None and len(sig["long"]) == 3


def test_plan_equal_dollars_and_sides(tmp_path):
    sig = _sig(str(tmp_path))
    plan = ex.plan_entries(sig, dict(ex.DEFAULTS), DAY)
    assert [e["side"] for e in plan] == ["long"] * 3 + ["short"] * 3
    aapl = plan[0]
    assert aapl["qty"] == int((10000 / 3) // 230.0) and aapl["leg"] == "EODREV_L1"
    for e in plan:
        assert e["qty"] * e["ref_px"] <= 10000 / 3 + 1e-9
    assert ex.broker_side("short", "OPEN") == "SHORT" and ex.broker_side("short", "CLOSE") == "BUY"


def test_full_day_moc_and_fallback(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd(refuse={("XOM", "MARKET_ON_CLOSE")})
    rec, notes = _run(tmp_path, ad, monkeypatch)
    types = [(k["symbol"], k["intent"], k["order_type"]) for k in ad.sent]
    assert sum(1 for t in types if t[1] == "OPEN") == 6
    assert sum(1 for t in types if t[2] == "MARKET_ON_CLOSE") == 6
    assert ("XOM", "CLOSE", "MARKET") in types and len(types) == 13
    assert rec["result"] == "traded"
    sides = {(k["symbol"], k["intent"]): k["side"] for k in ad.sent if k["order_type"] != "MARKET_ON_CLOSE"}
    assert sides[("JPM", "OPEN")] == "SHORT" and sides[("AAPL", "OPEN")] == "BUY"
    again, _ = _run(tmp_path, FakeAd(), monkeypatch)
    assert again["result"] == "already ran today"


def test_dead_moc_gets_fallback(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd()
    fills = {"EODREV-20261116-L2-MOC": {"status": "CANCELLED", "filled": 0, "price": None}}
    _run(tmp_path, ad, monkeypatch, fills=fills)
    assert ("MSFT", "MARKET") in [(k["symbol"], k["order_type"]) for k in ad.sent if k["intent"] == "CLOSE"]


def test_missing_file_alerts_skip_does_not(tmp_path, monkeypatch):
    rec, notes = _run(tmp_path, FakeAd(), monkeypatch)
    assert rec["result"] == "no trade" and notes
    os.remove(os.path.join(str(tmp_path), "exec_state.json"))
    _sig(str(tmp_path), status="SKIP")
    rec, notes = _run(tmp_path, FakeAd(), monkeypatch)
    assert rec["result"] == "no trade" and not notes


def test_loss_rail_blocks_next_session(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    fills = {}
    for i, (sym, px) in enumerate((("AAPL", 230.0), ("MSFT", 410.0), ("NVDA", 140.0)), 1):
        q = int((10000 / 3) // px)
        fills[f"EODREV-20261116-L{i}-O"] = {"status": "FILLED", "filled": q, "price": px}
        fills[f"EODREV-20261116-L{i}-MOC"] = {"status": "FILLED", "filled": q, "price": px * 0.95}
    for i, (sym, px) in enumerate((("JPM", 250.0), ("XOM", 115.0), ("LLY", 800.0)), 1):
        q = int((10000 / 3) // px)
        fills[f"EODREV-20261116-S{i}-O"] = {"status": "FILLED", "filled": q, "price": px}
        fills[f"EODREV-20261116-S{i}-MOC"] = {"status": "FILLED", "filled": q, "price": px}
    rec, notes = _run(tmp_path, FakeAd(), monkeypatch, fills=fills)
    assert rec["pnl"] < -400
    st = json.load(open(os.path.join(str(tmp_path), "exec_state.json")))
    assert st["rail_blocks_through"] == "2026-11-17"
    assert ex.rail_blocks(st, dt.date(2026, 11, 17)) and not ex.rail_blocks(st, dt.date(2026, 11, 18))


def test_kill_file_blocks_entries(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    open(os.path.join(str(tmp_path), "KILL"), "w").close()
    ad = FakeAd()
    rec, _ = _run(tmp_path, ad, monkeypatch)
    assert rec["result"] == "no trade" and not ad.sent


def test_other_book_symbols_skip_in_paper_reconcile(tmp_path):
    other = tmp_path / "eod.json"
    other.write_text(json.dumps({"broker_sent_positions": {
        "EODREV_L1": {"symbol": "AAPL", "qty": 14}, "EODREV_S1": {"symbol": "JPM", "qty": 0}}}))
    cfg = {"other_book_states": [str(other)]}
    assert wo.other_book_symbols(cfg, str(tmp_path / "mine.json")) == {"AAPL"}
    assert wo.other_book_symbols(cfg, str(other)) == set()
    assert wo.other_book_symbols({"other_book_states": [str(tmp_path / "nope.json")]}, None) == set()
