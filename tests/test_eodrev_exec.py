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
    if not os.path.exists(os.path.join(str(tmp_path), "probe.jsonl")):
        with open(os.path.join(str(tmp_path), "probe.jsonl"), "w") as f:
            f.write(json.dumps({"results": [{"open_ok": 1, "exit_filled": 1}] * 2}) + "\n")
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


def test_full_day_market_exit_and_fallback(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd()
    orig = ad.place_stock_order
    ad.place_stock_order = lambda **k: (dict(orig(**k), ok=False, reason="417")
                                        if k["signal_id"] == "EODREV-20261116-S2-X" else orig(**k))
    rec, notes = _run(tmp_path, ad, monkeypatch)
    types = [(k["symbol"], k["intent"], k["order_type"]) for k in ad.sent]
    assert sum(1 for t in types if t[1] == "OPEN") == 6
    assert not any(t[2] == "MARKET_ON_CLOSE" for t in types)
    assert sum(1 for t in types if t[1] == "CLOSE") == 7      # 6 exits + XOM fallback
    assert [k["signal_id"] for k in ad.sent].count("EODREV-20261116-S2-FB") == 1
    assert rec["result"] == "traded" and rec["one_sided"] is None
    assert ex._at(DAY, ex.DEFAULTS["exit_at"]) == dt.datetime(2026, 11, 16, 15, 57, 0, tzinfo=ET)
    sides = {(k["symbol"], k["intent"]): k["side"] for k in ad.sent if not k["signal_id"].endswith("-X")}
    assert sides[("JPM", "OPEN")] == "SHORT" and sides[("AAPL", "OPEN")] == "BUY"
    again, _ = _run(tmp_path, FakeAd(), monkeypatch)
    assert again["result"] == "already ran today"


def test_dead_exit_gets_fallback(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd()
    fills = {"EODREV-20261116-L2-X": {"status": "CANCELLED", "filled": 0, "price": None}}
    _run(tmp_path, ad, monkeypatch, fills=fills)
    assert "EODREV-20261116-L2-FB" in [k["signal_id"] for k in ad.sent]


def test_refused_short_unwinds_its_long_pair(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd(refuse={("XOM", "MARKET")})          # S2 short refused
    fills = {"EODREV-20261116-L2-O": {"status": "FILLED", "filled": 8, "price": 410.0},
             "EODREV-20261116-L2-UW": {"status": "FILLED", "filled": 8, "price": 409.0}}
    rec, notes = _run(tmp_path, ad, monkeypatch, fills=fills)
    sids = [k["signal_id"] for k in ad.sent]
    assert "EODREV-20261116-L2-UW" in sids and "EODREV-20261116-L2-X" not in sids
    assert not any(s.startswith("EODREV-20261116-S2-") and not s.endswith("-O") for s in sids)
    assert sum(1 for s in sids if s.endswith("-X")) == 4
    assert rec["one_sided"]["unwound"] == ["EODREV_L2"] and "XOM" in rec["one_sided"]["reason"]
    assert len(notes) == 1 and "MSFT" in notes[0]


def test_refused_short_cancels_unfilled_pair(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd(refuse={("JPM", "MARKET")})
    ad.cancelled = []
    ad.cancel_order = lambda sid: ad.cancelled.append(sid) or {"ok": True}
    fills = {"EODREV-20261116-L1-O": {"status": "SUBMITTED", "filled": 0, "price": None}}
    rec, _ = _run(tmp_path, ad, monkeypatch, fills=fills)
    assert ad.cancelled == ["EODREV-20261116-L1-O"]
    assert not any(k["signal_id"].startswith("EODREV-20261116-L1-") and k["intent"] == "CLOSE" for k in ad.sent)
    leg = next(e for e in rec["entries"] if e["leg"] == "EODREV_L1")
    assert leg["unwind"] == "cancelled"


def test_two_refused_flattens_basket(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd(refuse={("JPM", "MARKET"), ("LLY", "MARKET")})
    rec, notes = _run(tmp_path, ad, monkeypatch, fills={})
    sids = [k["signal_id"] for k in ad.sent]
    assert sum(1 for s in sids if s.endswith("-UW")) == 4 and not any(s.endswith("-X") for s in sids)
    assert rec["one_sided"]["action"] == "flattened the whole basket" and len(notes) == 1


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
        fills[f"EODREV-20261116-L{i}-X"] = {"status": "FILLED", "filled": q, "price": px * 0.95}
    for i, (sym, px) in enumerate((("JPM", 250.0), ("XOM", 115.0), ("LLY", 800.0)), 1):
        q = int((10000 / 3) // px)
        fills[f"EODREV-20261116-S{i}-O"] = {"status": "FILLED", "filled": q, "price": px}
        fills[f"EODREV-20261116-S{i}-X"] = {"status": "FILLED", "filled": q, "price": px}
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


def test_no_basket_until_probe_passed(tmp_path):
    _sig(str(tmp_path))
    with open(os.path.join(str(tmp_path), "probe.jsonl"), "w") as f:
        f.write(json.dumps({"results": [{"open_ok": True, "moc_ok": True}] * 2}) + "\n")     # old MOC record no longer counts
        f.write(json.dumps({"results": [{"open_ok": True, "exit_filled": 0}, {"open_ok": True, "exit_filled": 1}]}) + "\n")
    ad, notes = FakeAd(), []
    rec = ex.run_day(ex.paths(str(tmp_path)), now_fn=lambda: dt.datetime(2026, 11, 16, 15, 27, tzinfo=ET),
                     adapter=ad, log=lambda *a: None, notify=lambda m, **k: notes.append(m), sleep=False)
    assert rec["why"] == "probe not passed" and not ad.sent and notes
    with open(os.path.join(str(tmp_path), "probe.jsonl"), "a") as f:
        f.write(json.dumps({"results": [{"open_ok": True, "exit_filled": 1}] * 2}) + "\n")
    assert ex.probe_ok(ex.paths(str(tmp_path)))


def test_probe_uses_market_exit_and_needs_fill(tmp_path, monkeypatch):
    ad, notes = FakeAd(), []
    monkeypatch.setattr(ex, "lookup", lambda a, rec: {"status": "FILLED", "filled": 1, "price": 1.0})
    ex.run_probe("AAPL", ex.paths(str(tmp_path)), adapter=ad, log=lambda *a: None,
                 notify=lambda m, **k: notes.append(m), wait_s=0)
    assert [k["order_type"] for k in ad.sent] == ["MARKET"] * 4
    assert ex.probe_ok(ex.paths(str(tmp_path))) and "PASSED" in notes[0]
    monkeypatch.setattr(ex, "lookup", lambda a, rec: {"status": "SUBMITTED", "filled": 0, "price": None})
    tmp2 = tmp_path / "b"
    ex.run_probe("AAPL", ex.paths(str(tmp2)), adapter=FakeAd(), log=lambda *a: None,
                 notify=lambda m, **k: notes.append(m), wait_s=0, wait_tries=2)
    assert not ex.probe_ok(ex.paths(str(tmp2))) and "FAILED" in notes[-1]
