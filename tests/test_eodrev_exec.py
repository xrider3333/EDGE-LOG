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
    """`fill` = {signal_id: shares that order really filled} for an ACCEPTED close that did not
    fill whole (default: an accepted order fills whole); `broker` overrides positions()."""
    def __init__(self, refuse=()):
        self.sent, self.refuse = [], set(refuse)
        self.fill, self.broker, self.ok_sent = {}, None, []

    def positions(self):
        if self.broker is not None:
            return {"broker": self.broker(self) if callable(self.broker) else self.broker}
        b = {}
        for k in self.ok_sent:
            q = self.fill.get(k["signal_id"], k["qty"])
            b[k["symbol"]] = b.get(k["symbol"], 0) + (q if k["side"] == "BUY" else -q)
        return {"broker": {s: q for s, q in b.items() if q}}

    def place_stock_order(self, **k):
        self.sent.append(k)
        bad = (k["symbol"], k["order_type"]) in self.refuse
        if not bad:
            self.ok_sent.append(k)
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
    ad.fill["EODREV-20261116-S2-X"] = 0                      # refused: XOM still held
    rec, notes = _run(tmp_path, ad, monkeypatch)
    types = [(k["symbol"], k["intent"], k["order_type"]) for k in ad.sent]
    assert sum(1 for t in types if t[1] == "OPEN") == 6
    assert not any(t[2] == "MARKET_ON_CLOSE" for t in types)
    assert sum(1 for t in types if t[1] == "CLOSE") == 7      # 6 exits + XOM fallback
    assert [k["signal_id"] for k in ad.sent].count("EODREV-20261116-S2-FB") == 1
    assert rec["result"] == "traded" and rec["one_sided"] is None
    assert ex._at(DAY, ex.DEFAULTS["exit_at"]) == dt.datetime(2026, 11, 16, 15, 59, 50, tzinfo=ET)
    sides = {(k["symbol"], k["intent"]): k["side"] for k in ad.sent if not k["signal_id"].endswith("-X")}
    assert sides[("JPM", "OPEN")] == "SHORT" and sides[("AAPL", "OPEN")] == "BUY"
    again, _ = _run(tmp_path, FakeAd(), monkeypatch)
    assert again["result"] == "already ran today"


def test_dead_exit_gets_fallback(tmp_path, monkeypatch):
    _sig(str(tmp_path))
    ad = FakeAd()
    fills = {"EODREV-20261116-L2-X": {"status": "CANCELLED", "filled": 0, "price": None}}
    ad.fill["EODREV-20261116-L2-X"] = 0
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


def _probe(tmp, ad, monkeypatch, look, notes, **kw):
    clock = {"t": dt.datetime(2026, 11, 20, 15, 35, 0, tzinfo=ET)}
    sends = []
    orig = ad.place_stock_order

    def place(**k):
        sends.append((clock["t"].strftime("%H:%M:%S"), k["symbol"], k["side"], k["qty"]))
        return orig(**k)
    ad.place_stock_order = place
    ad.cancel_order = lambda cid: {"ok": True}
    monkeypatch.setattr(ex, "lookup", look)
    monkeypatch.setattr(ex, "LOOKUP_PAUSE_S", 0)
    monkeypatch.setattr(ex, "_sleep_until", lambda t, now_fn, log: clock.update(t=max(clock["t"], t)))
    ex.run_probe("AAPL", ex.paths(str(tmp)), adapter=ad, log=lambda *a: None,
                 notify=lambda m, **k: notes.append(m), wait_s=0, wait_tries=3,
                 now_fn=lambda: clock["t"], **kw)
    return sends


def test_probe_holds_to_1559_on_separate_symbols(tmp_path, monkeypatch):
    ad, notes = FakeAd(), []
    sends = _probe(tmp_path, ad, monkeypatch,
                   lambda a, rec: {"status": "FILLED", "filled": 1, "price": 1.0}, notes)
    assert [s[0] for s in sends] == ["15:35:00", "15:35:00", "15:59:50", "15:59:50"]
    assert {s[1] for s in sends[:2]} == {"AAPL", "MSFT"}            # never opposing on one sym
    assert [k["order_type"] for k in ad.sent] == ["MARKET"] * 4
    assert ex.probe_ok(ex.paths(str(tmp_path))) and "PASSED" in notes[-1]


def test_probe_unfilled_entry_alerts_unwinds_and_fails(tmp_path, monkeypatch):
    ad, notes = FakeAd(), []
    sends = _probe(tmp_path, ad, monkeypatch,
                   lambda a, rec: {"status": "SUBMITTED", "filled": 0, "price": None}, notes)
    assert len(sends) == 2                                          # no exit for a non-fill
    assert any("entry not filled" in n for n in notes) and "FAILED" in notes[-1]
    assert not ex.probe_ok(ex.paths(str(tmp_path)))


def test_probe_exit_unfilled_uses_1559_35_fallback(tmp_path, monkeypatch):
    ad, notes = FakeAd(), []

    def look(a, rec):
        if rec["_sid"].endswith("-PX"):
            return {"status": "REJECTED", "filled": 0}
        return {"status": "FILLED", "filled": 1, "price": 1.0}
    sends = _probe(tmp_path, ad, monkeypatch, look, notes)
    assert [s[0] for s in sends][-2:] == ["15:59:56", "15:59:56"]
    assert ex.probe_ok(ex.paths(str(tmp_path)))

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
    seq = {"EODREV-20261116-L2-O": [None] * 7}       # unwind (3) + prep (3) + exit retry (1) reads all fail
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
    ad.fill.update({"EODREV-20261116-L2-UW": 0, "EODREV-20261116-L2-X": 0, "EODREV-20261116-L2-FB": 0})
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


# -- 15:59:40 prep / 15:59:50 parallel exits / 15:59:56 pending-aware fallback --------------
def _clock_day(tmp_path, monkeypatch, look, ad=None, cancel_ok=True, fill=None):
    """run_day on a fake clock: every wait jumps the clock; lookups and sends record the time."""
    _sig(str(tmp_path))
    ad = ad or CancelAd(cancel_ok=cancel_ok)
    ad.fill.update(fill or {})
    clock = {"t": dt.datetime(2026, 11, 16, 15, 27, tzinfo=ET)}
    sends, looks, notes = [], [], []
    orig = ad.place_stock_order

    def place(**k):
        sends.append((clock["t"].strftime("%H:%M:%S"), k["signal_id"], k["qty"]))
        return orig(**k)
    ad.place_stock_order = place

    def lk(a, rec):
        looks.append((clock["t"].strftime("%H:%M:%S"), rec["_sid"]))
        return look(rec["_sid"], rec)
    monkeypatch.setattr(ex, "lookup", lk)
    monkeypatch.setattr(ex, "LOOKUP_PAUSE_S", 0)
    monkeypatch.setattr(ex, "_sleep_until", lambda t, now_fn, log: clock.update(t=max(clock["t"], t)))
    open(os.path.join(str(tmp_path), "probe.jsonl"), "w").write(
        json.dumps({"results": [{"open_ok": 1, "exit_filled": 1}] * 2}) + "\n")
    rec = ex.run_day(ex.paths(str(tmp_path)), now_fn=lambda: clock["t"], adapter=ad,
                     log=lambda *a: None, notify=lambda m, **k: notes.append(m), sleep=True)
    return rec, ad, sends, looks, notes


def _filled(sid, rec):
    return {"status": "FILLED", "filled": rec.get("_qty", 0), "price": 100.0}


def test_prep_reads_at_1559_10_and_all_exits_go_at_1559_30(tmp_path, monkeypatch):
    rec, ad, sends, looks, _ = _clock_day(tmp_path, monkeypatch, _filled)
    entry_reads = [t for t, sid in looks if sid.endswith("-O") and "15:59:00" <= t < "16:00:00"]
    assert entry_reads and set(entry_reads) == {"15:59:40"}            # close_qty read at prep
    exits = [(t, sid) for t, sid, _ in sends if sid.endswith("-X")]
    assert len(exits) == 6 and {t for t, _ in exits} == {"15:59:50"}
    assert not any(sid.endswith("-FB") for _, sid, _ in sends)
    assert rec["result"] == "traded"


def test_exits_are_sent_in_parallel(tmp_path, monkeypatch):
    import threading
    gate = threading.Barrier(6, timeout=5)      # 6 sends must be in flight together
    ad = CancelAd()
    orig = ad.place_stock_order

    def place(**k):
        if k["signal_id"].endswith("-X"):
            gate.wait()
        return orig(**k)
    ad.place_stock_order = place
    rec, ad, sends, _, _ = _clock_day(tmp_path, monkeypatch, _filled, ad=ad)
    assert sum(1 for _, sid, _ in sends if sid.endswith("-X")) == 6 and not gate.broken


def test_prep_unreadable_retries_once_at_exit(tmp_path, monkeypatch):
    calls = {"n": 0}

    def look(sid, rec):
        if sid == "EODREV-20261116-L1-O" and rec is not None:
            calls["n"] += 1
            if calls["n"] > 1 and calls["n"] <= 4:        # 15:31 read ok, prep 3 tries fail
                return None
        return _filled(sid, rec)
    rec, ad, sends, looks, notes = _clock_day(tmp_path, monkeypatch, look)
    l1 = [t for t, sid in looks if sid == "EODREV-20261116-L1-O" and t < "16:00:00"]
    assert l1[-1] == "15:59:50" and ("15:59:50", "EODREV-20261116-L1-X", 14) in sends
    assert not any("unreadable" in n for n in notes)


def test_prep_and_exit_unreadable_alerts_and_sends_nothing(tmp_path, monkeypatch):
    def look(sid, rec):
        if sid == "EODREV-20261116-L1-O":
            return None
        return _filled(sid, rec)
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, look)
    assert not any(sid.startswith("EODREV-20261116-L1-") and not sid.endswith("-O")
                   for _, sid, _ in sends)
    assert any("AAPL" in n and "NOTHING sent" in n for n in notes)


def test_pending_exit_alert_cancel_resend_remaining(tmp_path, monkeypatch):
    seq = {"n": 0}

    def look(sid, rec):
        if sid == "EODREV-20261116-S1-X":
            seq["n"] += 1
            if seq["n"] == 1:
                return {"status": "SUBMITTED", "filled": 0, "price": None}   # at fallback
            return {"status": "CANCELLED", "filled": 0, "price": None}        # after the cancel
        return _filled(sid, rec)
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, look,
                                          fill={"EODREV-20261116-S1-X": 0})
    assert ad.cancelled == ["EODREV-20261116-S1-X"]
    fb = [s for s in sends if s[1] == "EODREV-20261116-S1-FB"]
    assert fb == [("15:59:56", "EODREV-20261116-S1-FB", 13)]
    assert any("JPM" in n and "SUBMITTED" in n and "cancelling" in n for n in notes)


def test_partially_filled_exit_resends_only_the_rest(tmp_path, monkeypatch):
    seq = {"n": 0}

    def look(sid, rec):
        if sid == "EODREV-20261116-L2-X":
            seq["n"] += 1
            if seq["n"] == 1:
                return {"status": "PARTIALLY_FILLED", "filled": 3, "price": 409.0}
            if seq["n"] == 2:
                return {"status": "PARTIALLY_FILLED", "filled": 4, "price": 409.0}  # cancel pending
            return {"status": "CANCELLED", "filled": 5, "price": 409.0}             # final
        if sid == "EODREV-20261116-L2-FB":
            return {"status": "FILLED", "filled": 3, "price": 408.0}
        return _filled(sid, rec)
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, look,
                                          fill={"EODREV-20261116-L2-X": 5})
    assert ad.cancelled == ["EODREV-20261116-L2-X"]
    assert [s for s in sends if s[1] == "EODREV-20261116-L2-FB"] == [
        ("15:59:56", "EODREV-20261116-L2-FB", 8 - 5)]                     # MSFT 8 shares
    leg = next(e for e in rec["entries"] if e["leg"] == "EODREV_L2")
    assert leg["exit_filled"] == 8                                       # 5 + 3, no false alert
    assert not any("exit filled" in n for n in notes)


def test_unconfirmed_cancel_alerts_and_does_not_resend(tmp_path, monkeypatch):
    def look(sid, rec):
        if sid == "EODREV-20261116-L3-X":
            return {"status": "PENDING_CANCEL", "filled": 0, "price": None}
        return _filled(sid, rec)
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, look, cancel_ok=False)
    assert ad.cancelled == ["EODREV-20261116-L3-X"]
    assert not any(s[1] == "EODREV-20261116-L3-FB" for s in sends)
    assert any("NVDA" in n and "cancel NOT confirmed" in n for n in notes)


def test_refused_exit_gets_fallback_at_1559_45(tmp_path, monkeypatch):
    ad = CancelAd()
    orig = ad.place_stock_order
    ad.place_stock_order = lambda **k: (dict(orig(**k), ok=False, reason="417")
                                        if k["signal_id"] == "EODREV-20261116-S3-X" else orig(**k))
    rec, ad, sends, _, _ = _clock_day(tmp_path, monkeypatch, _filled, ad=ad,
                                      fill={"EODREV-20261116-S3-X": 0})
    assert [s for s in sends if s[1] == "EODREV-20261116-S3-FB"] == [
        ("15:59:56", "EODREV-20261116-S3-FB", 4)]                          # LLY 4 shares
    assert ad.cancelled == []


# -- 11-21: prebuilt 15:59:40 / parallel 15:59:50 / capped 15:59:56 / after-close flatten ------
def test_exit_orders_prebuilt_at_prep_and_sent_unlocked_at_exit(tmp_path, monkeypatch):
    events = []
    orig_build = ex._build_exit

    def spy(e, day, what="X", qty=None):
        o = orig_build(e, day, what, qty)
        events.append(("build", o["signal_id"]))
        return o
    monkeypatch.setattr(ex, "_build_exit", spy)
    ad = CancelAd()
    orig = ad.place_stock_order

    def place(**k):
        events.append(("send", k["signal_id"]))
        return orig(**k)
    ad.place_stock_order = place
    rec, ad, sends, looks, _ = _clock_day(tmp_path, monkeypatch, _filled, ad=ad)
    xs = [k for k in ad.sent if k["signal_id"].endswith("-X")]
    assert len(xs) == 6 and all(k["wire_unlocked"] is True and k["order_type"] == "MARKET"
                                and k["tif"] == "DAY" for k in xs)
    first_send = events.index(next(ev for ev in events if ev[0] == "send" and ev[1].endswith("-X")))
    builds = [i for i, ev in enumerate(events) if ev[0] == "build" and ev[1].endswith("-X")]
    assert len(builds) == 6 and max(builds) < first_send          # all built before any send
    assert {t for t, sid in looks if sid.endswith("-O") and "15:59" <= t < "16:00"} == {"15:59:40"}
    o = rec["entries"][0]["exit_order"]
    assert o["session"] == "CORE" and o["client_order_id"] and o["side"] == "SELL"


def test_six_exits_in_flight_together_at_1559_50(tmp_path, monkeypatch):
    import threading
    gate = threading.Barrier(6, timeout=5)
    ad = CancelAd()
    orig = ad.place_stock_order

    def place(**k):
        if k["signal_id"].endswith("-X"):
            gate.wait()
        return orig(**k)
    ad.place_stock_order = place
    rec, ad, sends, _, _ = _clock_day(tmp_path, monkeypatch, _filled, ad=ad)
    assert {t for t, sid, _ in sends if sid.endswith("-X")} == {"15:59:50"} and not gate.broken
    sp = rec["entries"][0]["exit_spread"]
    assert sp["n"] == 6 and sp["start_ms"] < 1000


def test_late_fill_between_read_and_resend_capped_by_live_position(tmp_path, monkeypatch):
    """JPM short 13: exit reads SUBMITTED 0, cancel confirms CANCELLED 0 -- but 9 filled late
    at Webull, so the live position shows only 4 short. The resend is 4, never 13."""
    seq = {"n": 0}

    def look(sid, rec):
        if sid == "EODREV-20261116-S1-X":
            seq["n"] += 1
            return ({"status": "SUBMITTED", "filled": 0, "price": None} if seq["n"] == 1
                    else {"status": "CANCELLED", "filled": 0, "price": None})
        return _filled(sid, rec)
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, look,
                                          fill={"EODREV-20261116-S1-X": 9})
    assert ad.cancelled == ["EODREV-20261116-S1-X"]
    fb = [s for s in sends if s[1] == "EODREV-20261116-S1-FB"]
    assert fb == [("15:59:56", "EODREV-20261116-S1-FB", 4)]
    assert "JPM" not in ad.positions()["broker"]                          # flat, not long


def test_live_position_flat_sends_no_resend(tmp_path, monkeypatch):
    def look(sid, rec):
        if sid == "EODREV-20261116-S1-X":
            return {"status": "CANCELLED", "filled": 0, "price": None}
        return _filled(sid, rec)
    ad = CancelAd()
    ad.broker = {}                                                        # all filled late
    _, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, look, ad=ad)
    assert not any(s[1].endswith("-FB") for s in sends)


def test_live_position_unreadable_alerts_and_sends_nothing(tmp_path, monkeypatch):
    def look(sid, rec):
        if sid == "EODREV-20261116-S1-X":
            return {"status": "CANCELLED", "filled": 0, "price": None}
        return _filled(sid, rec)
    ad = CancelAd()
    ad.positions = lambda: {"broker": None, "error": "timeout"}
    _, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, look, ad=ad)
    assert not any(s[1].endswith("-FB") for s in sends)
    assert any("JPM" in n and "could not be read" in n for n in notes)


def test_fallback_hard_cap_nothing_sent_after_1559_59_5(tmp_path):
    ad, notes = CancelAd(), []
    ad.broker = {"AAPL": 14}
    late = dt.datetime(2026, 11, 16, 15, 59, 59, 600000, tzinfo=ET)
    e = {"leg": "EODREV_L1", "sym": "AAPL", "side": "long", "close_qty": 14, "open_ok": True,
         "exit_ok": False, "exit_rec": {"ok": False, "_sid": "EODREV-20261116-L1-X"}}
    ex._fallback_one(ad, e, DAY, lambda m, **k: notes.append(m), lambda *a: None,
                     now_fn=lambda: late, cap=ex._at(DAY, ex.HARD_CAP))
    assert ad.sent == [] and e["fb_skipped"] == "past hard cap"
    assert any("15:59:59.5" in n for n in notes)
    assert ex._at(DAY, ex.HARD_CAP) == dt.datetime(2026, 11, 16, 15, 59, 59, 500000, tzinfo=ET)
    ok = dt.datetime(2026, 11, 16, 15, 59, 59, 400000, tzinfo=ET)
    e.pop("fb_skipped")
    ex._fallback_one(ad, e, DAY, lambda m, **k: None, lambda *a: None,
                     now_fn=lambda: ok, cap=ex._at(DAY, ex.HARD_CAP))
    assert [k["qty"] for k in ad.sent] == [14]


def test_after_close_leftover_alerts_then_extended_hours_limit(tmp_path, monkeypatch):
    ad = CancelAd()
    orig = ad.place_stock_order
    order = []

    def place(**k):
        order.append(("send", k["signal_id"]))
        r = orig(**k)
        if k["symbol"] == "AAPL" and k["intent"] == "CLOSE" and not k.get("extended_hours"):
            r = dict(r, ok=False, reason="417")
        return r
    ad.place_stock_order = place
    monkeypatch.setattr(ex, "_last_price", lambda sym, log=print: 200.0)
    fill = {"EODREV-20261116-L1-X": 0, "EODREV-20261116-L1-FB": 0,
            "EODREV-20261116-L1-AH": 0}                                   # still held at 16:05
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, _filled, ad=ad, fill=fill)
    ah = [k for k in ad.sent if k["signal_id"].endswith("-AH")]
    assert len(ah) == 1 and ah[0]["signal_id"] == "EODREV-20261116-L1-AH"   # only the leftover
    assert ah[0]["order_type"] == "LIMIT" and ah[0]["extended_hours"] is True
    assert ah[0]["limit_price"] == round(200.0 * 0.997, 2) and ah[0]["side"] == "SELL"
    assert ah[0]["qty"] == 14
    assert [s[0] for s in sends if s[1].endswith("-AH")] == ["16:00:05"]
    assert any("AAPL" in n and "STILL HELD after the close" in n for n in notes)
    assert any("AAPL" in n and "STILL 14 held at settle" in n for n in notes)   # 16:05 re-check


def test_after_close_alert_fires_even_when_flatten_refused(tmp_path, monkeypatch):
    ad = CancelAd()
    orig = ad.place_stock_order
    ad.place_stock_order = lambda **k: (dict(orig(**k), ok=False, reason="417")
                                        if k["symbol"] == "AAPL" and k["intent"] == "CLOSE"
                                        else orig(**k))
    monkeypatch.setattr(ex, "_last_price", lambda sym, log=print: None)     # no quote either
    fill = {"EODREV-20261116-L1-X": 0, "EODREV-20261116-L1-FB": 0, "EODREV-20261116-L1-AH": 0}
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, _filled, ad=ad, fill=fill)
    i = next(i for i, n in enumerate(notes) if "STILL HELD after the close" in n)
    assert any("REFUSED" in n and "AAPL" in n for n in notes[i + 1:])


def test_after_close_flat_book_sends_nothing(tmp_path, monkeypatch):
    rec, ad, sends, _, notes = _clock_day(tmp_path, monkeypatch, _filled)
    assert not any(s[1].endswith("-AH") for s in sends)
    assert not any("after the close" in n for n in notes)


def test_bad_config_times_refused_with_alert(tmp_path):
    notes = []

    def note(m, **k):
        notes.append(m)
    pinned = {"prep_at": "15:58:40", "exit_at": "15:59:00", "fallback_at": "15:59:35"}
    assert ex.exit_times(pinned, note) == pinned and not notes            # box pins: valid
    for bad in ({"prep_at": "15:59:50", "exit_at": "15:59:50"},
                {"prep_at": "15:59:55", "exit_at": "15:59:00"},
                {"exit_at": "15:59:58", "fallback_at": "15:59:57"},
                {"fallback_at": "15:59:59.5"}, {"prep_at": "junk"}):
        notes.clear()
        assert ex.exit_times(dict(ex.DEFAULTS, **bad), note) == ex.SAFE_TIMES
        assert notes and "refused" in notes[0]
    d = ex.DEFAULTS
    assert (d["prep_at"], d["exit_at"], d["fallback_at"]) == ("15:59:40", "15:59:50", "15:59:56")


def test_bad_config_day_uses_safe_times(tmp_path, monkeypatch):
    with open(os.path.join(str(tmp_path), "config.json"), "w") as f:
        json.dump({"prep_at": "15:59:55", "exit_at": "15:59:00"}, f)
    rec, ad, sends, looks, notes = _clock_day(tmp_path, monkeypatch, _filled)
    assert {t for t, sid, _ in sends if sid.endswith("-X")} == {"15:59:50"}
    assert any("exit times refused" in n for n in notes)


def test_probe_stuck_exit_cancelled_before_resend(tmp_path, monkeypatch):
    ad, notes, order = CancelAd(), [], []
    dead = set()

    def look(a, rec):
        if rec["_sid"].endswith("-PX"):
            return ({"status": "CANCELLED", "filled": 0} if rec["_sid"] in dead
                    else {"status": "SUBMITTED", "filled": 0})
        return {"status": "FILLED", "filled": 1, "price": 1.0}
    orig = ad.place_stock_order
    ad.place_stock_order = lambda **k: order.append(("send", k["signal_id"])) or orig(**k)

    def cancel(cid):
        order.append(("cancel", cid))
        dead.add(cid)
        return {"ok": True}
    _probe(tmp_path, ad, monkeypatch, look, notes)          # first pass: patches lookup / pauses
    ad2, notes2, order[:] = CancelAd(), [], []
    orig2 = ad2.place_stock_order
    ad2.place_stock_order = lambda **k: order.append(("send", k["signal_id"])) or orig2(**k)
    clock = {"t": dt.datetime(2026, 11, 20, 15, 35, tzinfo=ET)}
    monkeypatch.setattr(ex, "_sleep_until", lambda t, now_fn, log: clock.update(t=max(clock["t"], t)))
    ad2.cancel_order = cancel
    os.makedirs(tmp_path / "p2")
    ex.run_probe("AAPL", ex.paths(str(tmp_path / "p2")), adapter=ad2, log=lambda *a: None,
                 notify=lambda m, **k: notes2.append(m), wait_s=0, wait_tries=2,
                 now_fn=lambda: clock["t"])
    for tag in ("PL", "PS"):
        px, pf = f"EODREV-20261120-{tag}-PX", f"EODREV-20261120-{tag}-PF"
        assert order.index(("cancel", px)) < order.index(("send", pf))
        assert order.count(("send", pf)) == 1


def test_probe_unconfirmed_cancel_never_sends_second_order(tmp_path, monkeypatch):
    ad, notes = CancelAd(cancel_ok=False), []

    def look(a, rec):
        if rec["_sid"].endswith("-PX"):
            return {"status": "PENDING_CANCEL", "filled": 0}
        return {"status": "FILLED", "filled": 1, "price": 1.0}
    _probe(tmp_path, ad, monkeypatch, look, notes)
    assert not any(k["signal_id"].endswith("-PF") for k in ad.sent)
    assert any("cancel NOT confirmed" in n for n in notes) and "FAILED" in notes[-1]


def test_adapter_wire_unlocked_sends_six_symbols_concurrently(tmp_path, monkeypatch):
    """Real OrderAdapter, mock client whose place_order takes 0.25 s: six CLOSEs on six
    symbols from six threads overlap with wire_unlocked; without it they queue on the lock."""
    import threading
    import time as _t
    from unittest.mock import MagicMock
    cfg = wo.load_config("__no_such_file__")
    cfg["mode"] = "PAPER"
    cfg["rails"]["session_start"], cfg["rails"]["session_end"] = "00:00", "23:59"
    for k in ("state_path", "paper_keys_path", "live_keys_path", "arm_live_file", "kill_file"):
        cfg[k] = str(tmp_path / k)
    with open(cfg["paper_keys_path"], "w") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}

    def slow(acct, orders):
        _t.sleep(0.25)
        r = MagicMock()
        r.json.return_value = {"status": "SUBMITTED"}
        return r
    client.order_v3.place_order.side_effect = slow
    ad = wo.OrderAdapter(config=cfg, log=lambda *a, **k: None)
    monkeypatch.setattr(ad, "_build_client", lambda mode: client)
    syms = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "LLY"]

    def burst(tag, side, intent, unlocked):
        out = []
        t0 = _t.monotonic()
        ths = [threading.Thread(target=lambda i=i, s=s: out.append(ad.place_stock_order(
            leg=f"EODREV_T{i}", signal_id=f"{tag}-{s}", symbol=s, side=side, qty=1,
            intent=intent, wire_unlocked=unlocked))) for i, s in enumerate(syms)]
        for t in ths:
            t.start()
        for t in ths:
            t.join(10)
        return _t.monotonic() - t0, out
    burst("o", "BUY", "OPEN", True)
    took, out = burst("x", "SELL", "CLOSE", True)
    assert len(out) == 6 and all(r["ok"] for r in out), out
    assert took < 0.25 * 3, took                                          # overlapping
    burst("o2", "BUY", "OPEN", True)
    took_serial, out2 = burst("y", "SELL", "CLOSE", False)
    assert all(r["ok"] for r in out2) and took_serial > 0.25 * 5          # one at a time
