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
        return {"ok": not bad, "reason": "417 refused" if bad else "", "_qty": k["qty"],
                "client_order_id": k["signal_id"], "parts": [{"client_order_id": k["signal_id"]}]}


def _run(tmp_path, ad, monkeypatch, fills=None, notes=None):
    p = ex.paths(str(tmp_path))
    if not os.path.exists(os.path.join(str(tmp_path), "probe.jsonl")):
        with open(os.path.join(str(tmp_path), "probe.jsonl"), "w") as f:
            f.write(json.dumps({"results": [{"open_ok": 1, "exit_filled": 1}] * 2}) + "\n")
    fills = fills or {}
    monkeypatch.setattr(ex, "lookup", lambda a, rec: fills.get(rec["_sid"], {
        "status": "FILLED", "filled": rec.get("_qty", 0), "price": None}))
    monkeypatch.setattr(ex, "LOOKUP_PAUSE_S", 0)
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
    assert ex._at(DAY, ex.DEFAULTS["exit_at"]) == dt.datetime(2026, 11, 16, 15, 59, 0, tzinfo=ET)
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
    fills = {f"EODREV-20261116-{l}-O": {"status": "FILLED", "filled": 5, "price": 100.0}
             for l in ("L1", "L2", "L3", "S2")}
    rec, notes = _run(tmp_path, ad, monkeypatch, fills=fills)
    sids = [k["signal_id"] for k in ad.sent]
    assert sum(1 for s in sids if s.endswith("-UW")) == 4 and not any(s.endswith("-X") for s in sids)
    assert rec["one_sided"]["action"] == "flattened the whole basket"
    assert sum("entries refused" in n for n in notes) == 1


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


class CancelAd(FakeAd):
    def __init__(self, refuse=(), cancel_ok=True):
        super().__init__(refuse)
        self.cancelled, self.cancel_ok = [], cancel_ok

    def cancel_order(self, sid):
        self.cancelled.append(sid)
        return {"ok": self.cancel_ok}


def _seq_lookup(monkeypatch, seqs, fills):
    """lookup that walks a per-sid list of answers (None = failed read), then falls to fills."""
    def f(a, rec):
        sid = rec["_sid"]
        if seqs.get(sid):
            return seqs[sid].pop(0)
        return fills.get(sid, {"status": "FILLED", "filled": 0, "price": None})
    return f


def _qty(ad, sid):
    return next(k["qty"] for k in ad.sent if k["signal_id"] == sid)


def test_unwind_partial_fill_cancels_rest_then_closes_filled_only(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = CancelAd(refuse={("XOM", "MARKET")})
    seq = {"EODREV-20261116-L2-O": [{"status": "PARTIALLY_FILLED", "filled": 3, "price": 410.0}]}
    monkeypatch.setattr(ex, "LOOKUP_PAUSE_S", 0)
    monkeypatch.setattr(ex, "lookup", _seq_lookup(monkeypatch, seq, {}))
    p = ex.paths(str(tmp_path))
    open(os.path.join(str(tmp_path), "probe.jsonl"), "w").write(
        json.dumps({"results": [{"open_ok": 1, "exit_filled": 1}] * 2}) + "\n")
    ex.run_day(p, now_fn=lambda: dt.datetime(2026, 11, 16, 15, 27, tzinfo=ET), adapter=ad,
               log=lambda *a: None, notify=lambda m, **k: None, sleep=False)
    sids = [k["signal_id"] for k in ad.sent]
    assert ad.cancelled[0] == "EODREV-20261116-L2-O"
    assert sids.index("EODREV-20261116-L2-UW") > 0 and _qty(ad, "EODREV-20261116-L2-UW") == 3


def _day(tmp_path, monkeypatch, ad, seq, fills=None):
    monkeypatch.setattr(ex, "LOOKUP_PAUSE_S", 0)
    monkeypatch.setattr(ex, "lookup", _seq_lookup(monkeypatch, seq, fills or {}))
    open(os.path.join(str(tmp_path), "probe.jsonl"), "w").write(
        json.dumps({"results": [{"open_ok": 1, "exit_filled": 1}] * 2}) + "\n")
    notes = []
    rec = ex.run_day(ex.paths(str(tmp_path)), now_fn=lambda: dt.datetime(2026, 11, 16, 15, 27, tzinfo=ET),
                     adapter=ad, log=lambda *a: None, notify=lambda m, **k: notes.append(m), sleep=False)
    return rec, notes, [k["signal_id"] for k in ad.sent]


def test_unwind_cancel_raced_by_fill_closes_and_exit_does_not_skip(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = CancelAd(refuse={("XOM", "MARKET")})
    # cancel "ok" but the order had filled: the post-cancel read shows FILLED 8
    seq = {"EODREV-20261116-L2-O": [{"status": "FILLED", "filled": 8, "price": 410.0}]}
    rec, _, sids = _day(tmp_path, monkeypatch, ad, seq)
    leg = next(e for e in rec["entries"] if e["leg"] == "EODREV_L2")
    assert leg["unwind"] == "closed" and _qty(ad, "EODREV-20261116-L2-UW") == 8


def test_unwind_failed_lookup_sends_no_close(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = CancelAd(refuse={("XOM", "MARKET")})
    seq = {"EODREV-20261116-L2-O": [None] * 6}       # unwind reads + exit reconcile reads all fail
    rec, notes, sids = _day(tmp_path, monkeypatch, ad, seq)
    assert not any(s.startswith("EODREV-20261116-L2-") and s != "EODREV-20261116-L2-O" for s in sids)
    assert "lookup failed" in notes[0] and any("NOTHING sent" in n for n in notes)


def test_unwind_failed_lookup_reconciled_at_exit(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = CancelAd(refuse={("XOM", "MARKET")})
    seq = {"EODREV-20261116-L2-O": [None] * 3 + [{"status": "FILLED", "filled": 6, "price": 410.0}]}
    rec, notes, sids = _day(tmp_path, monkeypatch, ad, seq)
    assert _qty(ad, "EODREV-20261116-L2-X") == 6


def test_unwind_close_refused_gets_exit_and_fallback(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = CancelAd(refuse={("XOM", "MARKET")})
    orig = ad.place_stock_order
    ad.place_stock_order = lambda **k: (dict(orig(**k), ok=False, reason="nope")
                                        if k["symbol"] == "MSFT" and k["intent"] == "CLOSE" else orig(**k))
    seq = {"EODREV-20261116-L2-O": [{"status": "FILLED", "filled": 8, "price": 410.0}]}
    rec, notes, sids = _day(tmp_path, monkeypatch, ad, seq)
    for w in ("UW", "X", "FB"):
        assert f"EODREV-20261116-L2-{w}" in sids and _qty(ad, f"EODREV-20261116-L2-{w}") == 8
    assert any("NOT CLOSED" in n for n in notes)


def test_async_reject_after_accept_unwinds_pair(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = CancelAd()
    fills = {"EODREV-20261116-S3-O": {"status": "REJECTED", "filled": 0, "price": None},
             "EODREV-20261116-L3-O": {"status": "FILLED", "filled": 23, "price": 140.0}}
    rec, notes, sids = _day(tmp_path, monkeypatch, ad, {}, fills)
    assert "EODREV-20261116-L3-UW" in sids and "EODREV-20261116-S3-X" not in sids
    assert rec["one_sided"]["when"] == ["15:31 check"] and "LLY" in notes[0]


def _basket_state(tmp_path, bday, entries):
    with open(os.path.join(str(tmp_path), "exec_state.json"), "w") as f:
        json.dump({"open_basket": {"day": bday, "entries": entries}}, f)


def _leg(leg, sym, side, qty, bday, **kw):
    sid = f"EODREV-{bday.replace('-', '')}-{leg.split('_')[-1]}-O"
    return dict({"leg": leg, "sym": sym, "side": side, "qty": qty, "open_ok": True, "open_sid": sid,
                 "open_rec": {"ok": True, "_sid": sid, "client_order_id": sid}}, **kw)


def test_restart_same_day_resumes_exits_and_alerts(tmp_path, monkeypatch):
    xsid = "EODREV-20261116-L1-X"
    _basket_state(tmp_path, "2026-11-16", [
        _leg("EODREV_L1", "AAPL", "long", 14, "2026-11-16",
             exit_ok=True, exit_rec={"ok": True, "_sid": xsid}),
        _leg("EODREV_S1", "JPM", "short", 13, "2026-11-16")])
    ad, notes = FakeAd(), []
    monkeypatch.setattr(ex, "lookup", lambda a, rec: {"status": "FILLED", "filled": 13, "price": 1.0})
    rec = ex.run_day(ex.paths(str(tmp_path)), now_fn=lambda: dt.datetime(2026, 11, 16, 15, 45, tzinfo=ET),
                     adapter=ad, log=lambda *a: None, notify=lambda m, **k: notes.append(m), sleep=False)
    assert [k["signal_id"] for k in ad.sent] == ["EODREV-20261116-S1-X"]   # no re-entry, no double exit
    assert "RESTART" in notes[0] and rec["resumed_on"] == "2026-11-16"
    st = json.load(open(os.path.join(str(tmp_path), "exec_state.json")))
    assert "open_basket" not in st and st["last_day"] == "2026-11-16"


def test_restart_next_day_closes_stranded_basket_now(tmp_path, monkeypatch):
    _basket_state(tmp_path, "2026-11-16", [_leg("EODREV_L2", "MSFT", "long", 8, "2026-11-16")])
    ad, notes = FakeAd(), []
    monkeypatch.setattr(ex, "lookup", lambda a, rec: {"status": "FILLED", "filled": 8, "price": 1.0})
    rec = ex.run_day(ex.paths(str(tmp_path)), now_fn=lambda: dt.datetime(2026, 11, 17, 9, 0, tzinfo=ET),
                     adapter=ad, log=lambda *a: None, notify=lambda m, **k: notes.append(m), sleep=False)
    assert [k["signal_id"] for k in ad.sent] == ["EODREV-20261117-L2-X"]
    assert rec["day"] == "2026-11-16" and "NOW" in notes[0]


def test_basket_saved_to_state_mid_day(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    seen = []
    orig = ex._save_basket
    monkeypatch.setattr(ex, "_save_basket", lambda p, st, d, e: (seen.append(len(e)), orig(p, st, d, e)))
    _run(tmp_path, FakeAd(), monkeypatch)
    assert seen and seen[0] == 6


def test_half_day_and_holiday_refused(tmp_path, monkeypatch):
    _sig(str(tmp_path), day=dt.date(2026, 11, 27))
    ad = FakeAd()
    p = ex.paths(str(tmp_path))
    rec = ex.run_day(p, now_fn=lambda: dt.datetime(2026, 11, 27, 15, 27, tzinfo=ET), adapter=ad,
                     log=lambda *a: None, notify=lambda m, **k: None, sleep=False)
    assert rec["result"] == "no trade" and "early close 13:00" in rec["why"] and not ad.sent
    rec = ex.run_day(p, now_fn=lambda: dt.datetime(2026, 11, 26, 15, 27, tzinfo=ET), adapter=ad,
                     log=lambda *a: None, notify=lambda m, **k: None, sleep=False)
    assert rec["result"] == "holiday"


def test_basket_saved_right_after_entries(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    calls = []
    orig = ex._save_basket
    monkeypatch.setattr(ex, "_save_basket", lambda p, st, d, e: (calls.append(
        [k["signal_id"] for k in ad.sent]), orig(p, st, d, e)))
    ad = FakeAd()
    _run(tmp_path, ad, monkeypatch)
    assert len(calls) >= 3 and len(calls[0]) == 6 and all(s.endswith("-O") for s in calls[0])


def test_exit_and_fallback_close_filled_qty(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = CancelAd()
    orig = ad.place_stock_order
    ad.place_stock_order = lambda **k: (dict(orig(**k), ok=False, reason="417")
                                        if k["signal_id"] == "EODREV-20261116-L1-X" else orig(**k))
    fills = {"EODREV-20261116-L1-O": {"status": "PARTIALLY_FILLED", "filled": 5, "price": 230.0},
             "EODREV-20261116-S1-O": {"status": "FILLED", "filled": 13, "price": 250.0}}
    rec, notes, sids = _day(tmp_path, monkeypatch, ad, {}, fills)
    assert _qty(ad, "EODREV-20261116-L1-X") == 5 and _qty(ad, "EODREV-20261116-L1-FB") == 5
    assert _qty(ad, "EODREV-20261116-S1-X") == 13
    assert "EODREV-20261116-L2-X" not in sids        # nothing filled -> nothing to close
