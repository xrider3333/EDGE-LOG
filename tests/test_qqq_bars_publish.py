"""tools/qqq_bars_publish.py -- the box's per-day QQQ bars doc for the Webull paper
candle charts. Doc shape, packing, the size cap, the three-ledger marks join (signal
bar rules, refused Webull tries and retries, book-only rows), and that --dry-run writes
nothing anywhere. Every fixture is synthetic and lives in tmp_path."""
import csv
import datetime as dt
import io
import json
import os
import sys
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import qqq_bars_publish as qb  # noqa: E402

ET = ZoneInfo("America/New_York")
DAY = "2026-09-28"


def _epoch(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    y, mo, d = map(int, day.split("-"))
    return int(dt.datetime(y, mo, d, h, m, tzinfo=ET).timestamp())


def _write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _bars_rows(day, step, last="15:59", special=None):
    """A flat 700.00 session with a few hand-set bars (special: {hh:mm: (o,h,l,c)})."""
    special = special or {}
    rows = []
    # a pre-market and an after-hours bar that must be dropped (regular session only)
    rows.append([_epoch(day, "09:25"), 1, 1, 1, 1, 5])
    m = 9 * 60 + 30
    lh, lm = map(int, last.split(":"))
    while m <= lh * 60 + lm:
        hhmm = f"{m // 60:02d}:{m % 60:02d}"
        o, h, l, c = special.get(hhmm, (700.0, 700.5, 699.5, 700.0))
        rows.append([_epoch(day, hhmm), o, h, l, c, 1000.0])
        m += step
    rows.append([_epoch(day, "16:00"), 2, 2, 2, 2, 5])
    return rows


BAR_HDR = ["time", "open", "high", "low", "close", "volume"]
SIG_HDR = ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares", "reason",
           "bar_source", "trade_id", "size", "keel_size"]
TR_HDR = ["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px", "pnl",
          "exit_reason", "trade_id"]
BO_HDR = ["ts_et", "leg", "intent", "side", "shares", "signal_id", "client_order_id", "mode",
          "ok", "sent", "shadow_px", "broker_fill_px", "slippage", "reason", "duplicate",
          "host_id", "outcome"]

NOISE_ID = "NOISE_382-20260928T141500Z-S"
ORB_ID = "ORB_R6-20260928T144500Z-S"
ENGU_ID = "ENGUQ_335-20260928T163200Z-L"
BOOKONLY_ID = "NOISE_382-20260928T180000Z-S"


def _make_home(tmp_path, last_5m="15:55", last_1m="15:59"):
    home = str(tmp_path / "home")
    special5 = {"10:10": (736.7, 736.7, 735.31, 735.6599),   # NOISE decides at this close
                "10:45": (733.39, 733.49, 731.63, 732.33)}   # ORB: priced at this close
    special1 = {"12:32": (739.06, 739.1, 737.92, 738.0927)}  # ENGU-Q limit fills inside
    _write_csv(os.path.join(home, "ohlc", "QQQ_5m.csv"), BAR_HDR,
               _bars_rows(DAY, 5, last_5m, special5))
    _write_csv(os.path.join(home, "ohlc", "QQQ_1m.csv"), BAR_HDR,
               _bars_rows(DAY, 1, last_1m, special1))
    _write_csv(os.path.join(home, "cloud_signal", "signals.csv"), SIG_HDR, [
        ["x", "NOISE_382", "ENTRY", "short", "2026-09-28T10:15:00-04:00", "735.6599", "135",
         "decide_at_close: decided at the close of the 10:10 bar, priced at that close",
         "webull", NOISE_ID, "2.0", "1.0"],
        ["x", "NOISE_382", "EXIT", "short", "2026-09-28T11:40:00-04:00", "735.695", "135",
         "strategy_exit; decide_at_close: decided at the close of the 11:35 bar, priced at that close",
         "webull", NOISE_ID, "2.0", "1.0"],
        ["x", "ORB_R6", "ENTRY", "short", "2026-09-28T10:45:00-04:00", "732.33", "136", "",
         "webull", ORB_ID, "1.0", ""],
        ["x", "ENGUQ_335", "VOID_ENTRY", "long", "2026-09-28T12:20:00-04:00", "737.5", "135",
         "ghost", "webull", ENGU_ID, "", ""],
        ["x", "ENGUQ_335", "ENTRY", "long", "2026-09-28T12:32:00-04:00", "738.0295", "135", "",
         "webull", ENGU_ID, "1.0", ""],
    ])
    _write_csv(os.path.join(home, "qqq_exec", "trades.csv"), TR_HDR, [
        ["NOISE", "2026-09-28 10:15:11", "2026-09-28 11:40:09", "short", "20", "735.6499",
         "735.705", "-1.1", "signal exit", NOISE_ID],
        ["ORB", "2026-09-28 10:50:06", "2026-09-28 15:59:01", "short", "10", "732.32", "736.76",
         "-44.4", "EOD", ORB_ID],
        ["ENGUQ", "2026-09-28 12:33:38", "2026-09-28 15:59:01", "long", "10", "738.0395",
         "736.66", "-13.8", "EOD", ENGU_ID],
        ["NOISE", "2026-09-28 14:00:05", "2026-09-28 14:30:05", "short", "10", "735.0", "734.0",
         "10.0", "signal exit", BOOKONLY_ID],
        # a legacy row with no trade id -> no marks at all (never guessed)
        ["ORB", "2026-09-28 13:00:00", "2026-09-28 13:30:00", "long", "5", "735", "736", "5",
         "EOD", ""],
        # another day's trade -> not in this day's doc
        ["NOISE", "2026-09-25 10:00:00", "2026-09-25 10:30:00", "long", "5", "744", "745", "5",
         "signal exit", "NOISE_382-20260925T140000Z-L"],
    ])
    _write_csv(os.path.join(home, "qqq_exec", "broker_orders.csv"), BO_HDR, [
        ["2026-09-28 10:15:11", "NOISE", "OPEN", "SHORT", "20", "qxNOISE38220260928T141500ZSO",
         "c", "PAPER", "True", "True", "735.6499", "735.87", "0.22", "", "False", "edgelog", "OK"],
        ["2026-09-28 11:40:09", "NOISE", "CLOSE", "BUY", "20", "qxNOISE38220260928T141500ZSC",
         "c", "PAPER", "True", "True", "735.705", "735.57", "-0.13", "", "False", "edgelog", "OK"],
        ["2026-09-28 10:50:06", "ORB", "OPEN", "SHORT", "10", "qxORBR620260928T144500ZSO",
         "c", "PAPER", "True", "True", "732.32", "732.58", "0.26", "", "False", "edgelog", "OK"],
        ["2026-09-28 12:33:38", "ENGUQ", "OPEN", "BUY", "10", "qxENGUQ33520260928T163200ZLO",
         "c", "PAPER", "True", "True", "738.0395", "738.56", "0.52", "", "False", "edgelog", "OK"],
        ["2026-09-28 15:59:01", "ENGUQ", "CLOSE", "SELL", "10", "qxENGUQ33520260928T163200ZLC",
         "c", "PAPER", "False", "True", "736.66", "", "",
         "ServerException: HTTP Status: 417, Code: X, Msg: Buy opening orders and sell opening "
         "orders cannot exist simultaneously., RequestID: abc", "False", "edgelog", "REFUSED"],
        ["2026-09-28 15:59:06", "ENGUQ", "CLOSE", "SELL", "10", "qxENGUQ33520260928T163200ZLCR1",
         "c", "PAPER", "True", "True", "736.66", "736.58", "-0.08", "", "False", "edgelog", "OK"],
        # a duplicate refusal is the adapter's own guard, not an attempt
        ["2026-09-28 15:59:07", "ENGUQ", "CLOSE", "SELL", "10", "qxENGUQ33520260928T163200ZLCR1",
         "c", "PAPER", "False", "False", "736.66", "", "", "duplicate", "True", "edgelog", ""],
    ])
    return home


NOW = dt.datetime(2026, 9, 28, 16, 10, tzinfo=ET)


def _doc(tmp_path, **kw):
    home = _make_home(tmp_path, **kw)
    data = qb.load_all(qb.default_paths(home))
    return qb.build_day_doc(DAY, data, now=NOW), data


def _mark(doc, tid):
    return [m for m in doc["marks"] if m["trade_id"] == tid][0]


# ── doc shape + packing ──────────────────────────────────────────────────────────────
def test_doc_shape(tmp_path):
    doc, _ = _doc(tmp_path)
    assert doc["v"] == 1 and doc["date"] == DAY and doc["session"] == "rth"
    assert set(doc["bars"]) == {"1m", "5m"}
    assert doc["bar_counts"] == {"1m": 390, "5m": 78}   # 09:25 and 16:00 dropped
    assert doc["bars_through"] == {"1m": "15:59", "5m": "15:55"}
    assert doc["complete"] is True and doc["final"] is False   # today: not final yet
    assert doc["levels_note"] == qb.LEVELS_NOTE
    # Firestore rejects arrays of arrays: nothing anywhere may be a list inside a list
    def walk(v, parent_list=False):
        if isinstance(v, list):
            assert not parent_list, "array directly inside an array"
            for x in v:
                walk(x, True)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x, False)
    walk(doc)
    json.dumps(doc)   # plain JSON types only
    assert qb.doc_size(doc) < 60_000


def test_pack_roundtrip_and_offsets(tmp_path):
    doc, _ = _doc(tmp_path)
    b5 = qb.unpack_bars(doc["bars"]["5m"], DAY)
    assert b5[0]["t"] == "2026-09-28 09:30" and b5[-1]["t"] == "2026-09-28 15:55"
    ten10 = [b for b in b5 if b["t"].endswith("10:10")][0]
    assert (ten10["o"], ten10["h"], ten10["l"], ten10["c"]) == (736.7, 736.7, 735.31, 735.6599)
    assert doc["bars"]["5m"].startswith("0,700,700.5,699.5,700,1000;")


def test_incomplete_day_and_final_rules(tmp_path):
    doc, data = _doc(tmp_path, last_5m="15:50", last_1m="15:58")
    assert doc["complete"] is False and doc["final"] is False
    assert doc["bars_through"] == {"1m": "15:58", "5m": "15:50"}
    later = NOW + dt.timedelta(days=1)
    assert qb.build_day_doc(DAY, data, now=later)["final"] is False     # still incomplete
    much_later = NOW + dt.timedelta(days=qb.FINAL_AFTER_DAYS)
    assert qb.build_day_doc(DAY, data, now=much_later)["final"] is True
    complete, data2 = _doc(tmp_path / "b")
    assert qb.build_day_doc(DAY, data2, now=later)["final"] is True


# ── the size cap ─────────────────────────────────────────────────────────────────────
def test_size_cap_drops_1m_first_then_refuses(tmp_path):
    doc, _ = _doc(tmp_path)
    full = qb.doc_size(doc)
    assert qb.enforce_cap(doc, cap=full) is doc                  # under the cap: untouched
    small = qb.enforce_cap(doc, cap=full - 1)
    assert "1m" not in small["bars"] and small["bars_dropped"] == ["1m"]
    assert small["final"] is False                               # never cache a cut doc
    assert qb.doc_size(small) < full - 1
    with pytest.raises(qb.DocTooLarge):
        qb.enforce_cap(doc, cap=2_000)
    assert "1m" in doc["bars"]                                   # original not mutated


def test_real_sized_day_well_under_cap(tmp_path):
    doc, _ = _doc(tmp_path)
    assert qb.doc_size(doc) < qb.DOC_CAP_BYTES // 4


# ── the marks join ───────────────────────────────────────────────────────────────────
def test_marks_only_for_this_days_trades_with_ids(tmp_path):
    doc, _ = _doc(tmp_path)
    ids = [m["trade_id"] for m in doc["marks"]]
    assert ids == [NOISE_ID, ORB_ID, ENGU_ID, BOOKONLY_ID]      # legacy + other day left out


def test_noise_signal_bar_recorded_and_fills(tmp_path):
    doc, _ = _doc(tmp_path)
    m = _mark(doc, NOISE_ID)
    assert m["tf"] == "5m" and m["side"] == "short"
    assert m["signal"] == {"t": "2026-09-28 10:10", "rule": "recorded"}
    assert m["bt_in"] == {"t": "2026-09-28 10:15:00", "px": 735.6599}
    assert m["signal_out"] == {"t": "2026-09-28 11:35", "rule": "recorded"}
    assert m["bt_out"] == {"t": "2026-09-28 11:40:00", "px": 735.695}
    assert m["book_in"] == {"t": "2026-09-28 10:15:11", "px": 735.6499}
    assert m["book_out"]["px"] == 735.705 and m["book_out"]["why"] == "signal exit"
    assert [a["px"] for a in m["wb_in"]] == [735.87] and m["wb_in"][0]["ok"] is True
    assert [a["px"] for a in m["wb_out"]] == [735.57]
    assert m["book_only"] is False


def test_orb_signal_bar_is_the_bar_it_was_priced_at(tmp_path):
    doc, _ = _doc(tmp_path)
    m = _mark(doc, ORB_ID)
    assert m["signal"] == {"t": "2026-09-28 10:45", "rule": "fill bar close"}
    assert m["bt_out"] is None and m["signal_out"] is None     # book flattened, no exit signal
    assert m["wb_out"] == []


def test_enguq_limit_fill_has_no_guessed_signal_bar(tmp_path):
    doc, _ = _doc(tmp_path)
    m = _mark(doc, ENGU_ID)
    assert m["tf"] == "1m"
    assert m["signal"] == {"t": None, "rule": "not recorded"}
    assert m["bt_in"] == {"t": "2026-09-28 12:32:00", "px": 738.0295}  # VOID_ENTRY ignored


def test_refused_close_and_retry_both_kept(tmp_path):
    doc, _ = _doc(tmp_path)
    out = _mark(doc, ENGU_ID)["wb_out"]
    assert [(a["ok"], a["sent"], a["outcome"], a["px"]) for a in out] == [
        (False, True, "REFUSED", None), (True, True, "OK", 736.58)]   # duplicate row dropped
    # Webull's own words, first sentence only
    assert out[0]["why"] == "Buy opening orders and sell opening orders cannot exist simultaneously"
    assert "RequestID" not in out[0]["why"] and len(out[0]["why"]) <= qb.REASON_MAX


def test_book_only_row(tmp_path):
    doc, _ = _doc(tmp_path)
    m = _mark(doc, BOOKONLY_ID)
    assert m["wb_in"] == [] and m["wb_out"] == [] and m["book_only"] is True
    assert m["signal"] is None and m["bt_in"] is None             # no signal row either


def test_shadow_ledger_rows_are_book_only(tmp_path):
    home = _make_home(tmp_path)
    sp = os.path.join(home, "qqq_exec", "shadow_trades.csv")
    _write_csv(sp, TR_HDR, [["ENGUQ", "2026-09-28 12:33:38", "2026-09-28 15:59:01", "long", "10",
                             "738.0395", "736.66", "-13.8", "EOD", "ENGUQS-20260928T163200Z-L"]])
    data = qb.load_all(qb.default_paths(home), shadow_paths=[sp])
    m = _mark(qb.build_day_doc(DAY, data, now=NOW), "ENGUQS-20260928T163200Z-L")
    assert m["shadow"] is True and m["book_only"] is True and m["wb_in"] == []


def test_signal_id_matches_the_exec_rule():
    """The join key must be the exec's own client-order-id rule, not a copy that drifts."""
    from api.qqq_exec import _broker_signal_id
    for tid in (NOISE_ID, ORB_ID, ENGU_ID):
        for intent in ("OPEN", "CLOSE"):
            assert qb.signal_id_base(tid, intent) == _broker_signal_id("X", "t", intent, trade_id=tid)


def test_signal_bar_rules_are_per_leg_and_exact():
    """A price match is proof only for ORB's ENTRY (decided + priced at that bar's close),
    and only to 4 decimals. NOISE before 2026-09-26 priced at the next bar's OPEN, so an
    open that happened to equal the previous close must NOT draw a signal bar."""
    bars = {"5m": {DAY: [(630, 1, 2, 0.5, 700.25, 1), (635, 700.25, 701, 700, 700.9, 1)]}}
    noise = {"leg": "NOISE_304", "event": "ENTRY", "ref_time": "2026-09-28T10:35:00-04:00",
             "ref_price": "700.25", "reason": ""}
    assert qb.signal_bar(noise, "5m", bars) == (None, "not recorded")     # old prior-close rule gone
    noise["ref_price"] = "700.9"                                          # = the ref bar's close
    assert qb.signal_bar(noise, "5m", bars) == (None, "not recorded")     # NOISE: price proves nothing
    orb = {"leg": "ORB_R6", "event": "ENTRY", "ref_time": "2026-09-28T10:35:00-04:00",
           "ref_price": "700.9", "reason": ""}
    assert qb.signal_bar(orb, "5m", bars) == ("2026-09-28 10:35", "fill bar close")
    orb["ref_price"] = "700.905"                                          # half a cent off
    assert qb.signal_bar(orb, "5m", bars) == (None, "not recorded")
    orb.update(ref_price="700.9", event="EXIT")                           # ORB exits: not proven
    assert qb.signal_bar(orb, "5m", bars) == (None, "not recorded")
    engu = {"leg": "ENGUQ_335", "event": "ENTRY", "ref_time": "2026-09-28T10:35:00-04:00",
            "ref_price": "700.9", "reason": ""}
    assert qb.signal_bar(engu, "5m", bars) == (None, "not recorded")


def test_backtest_fill_times_are_the_fill_moment_for_every_leg(tmp_path):
    """ORB's ref_time names the bar it closed on -> stamped one bar later (its close);
    NOISE's ref_time already is the fill moment (the signal bar's close = next bar start)."""
    doc, _ = _doc(tmp_path)
    assert _mark(doc, ORB_ID)["bt_in"] == {"t": "2026-09-28 10:50:00", "px": 732.33}
    assert _mark(doc, NOISE_ID)["bt_in"]["t"] == "2026-09-28 10:15:00"
    assert _mark(doc, ENGU_ID)["bt_in"]["t"] == "2026-09-28 12:32:00"


# ── CLI: dry run writes nothing; publish path; intraday throttle ─────────────────────
class _FakeRef:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def collection(self, name):
        return type(self)(self.store, self.path + [name])

    def document(self, name):
        return type(self)(self.store, self.path + [name])

    def set(self, doc):
        self.store["/".join(self.path)] = doc


def _snapshot(root):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[p] = (os.path.getsize(p), os.path.getmtime(p))
    return out


def test_dry_run_writes_nothing(tmp_path):
    home = _make_home(tmp_path)
    before = _snapshot(str(tmp_path))

    def boom(_cred):
        raise AssertionError("dry run must never create a Firestore client")
    buf = io.StringIO()
    rc = qb.main(["--dry-run", "--home", home, "--date", DAY, "--intraday"], db_factory=boom,
                 now=NOW, out=buf)
    rc2 = qb.main(["--dry-run", "--print-doc", "--home", home, "--backfill", "2026-09-03"],
                  db_factory=boom, now=NOW, out=buf)
    assert rc == 0 and rc2 == 0
    assert _snapshot(str(tmp_path)) == before
    text = buf.getvalue()
    assert "DRY RUN 2026-09-28" in text and "bytes" in text and '"marks"' in text


def test_publish_writes_one_doc_per_day(tmp_path):
    home = _make_home(tmp_path)
    store = {}
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda cred: _FakeRef(store, []), now=NOW, out=io.StringIO())
    assert rc == 0
    assert list(store) == ["users/U1/qqq_bars/2026-09-28"]
    assert store["users/U1/qqq_bars/2026-09-28"]["marks"][0]["trade_id"] == NOISE_ID


def test_publish_needs_uid(tmp_path):
    home = _make_home(tmp_path)
    buf = io.StringIO()
    assert qb.main(["--home", home], db_factory=lambda c: None, now=NOW, out=buf) == 2
    assert "--uid is required" in buf.getvalue()


def test_intraday_writes_only_when_a_trade_changed(tmp_path, monkeypatch):
    home = _make_home(tmp_path)
    store = {}
    fac = lambda cred: _FakeRef(store, [])   # noqa: E731
    clock = [1_000_000.0]
    monkeypatch.setattr(qb.time, "time", lambda: clock[0])
    args = ["--home", home, "--intraday", "--uid", "U1"]
    assert qb.main(args, db_factory=fac, now=NOW, out=io.StringIO()) == 0
    assert len(store) == 1
    store.clear()
    clock[0] += 3600
    buf = io.StringIO()
    qb.main(args, db_factory=fac, now=NOW, out=buf)          # nothing new closed
    assert store == {} and "no trade closed" in buf.getvalue()
    # a new Webull row lands -> changed, but inside the 5-minute floor -> still skipped
    with open(os.path.join(home, "qqq_exec", "broker_orders.csv"), "a", newline="") as f:
        csv.writer(f).writerow(["2026-09-28 14:00:05", "NOISE", "OPEN", "SHORT", "10",
                                "qxNOISE38220260928T180000ZSO", "c", "PAPER", "True", "True",
                                "735", "735.1", "0.1", "", "False", "edgelog", "OK"])
    state = json.load(open(os.path.join(home, "qqq_bars", "publish_state.json")))
    state[DAY]["at"] = clock[0] - 10
    json.dump(state, open(os.path.join(home, "qqq_bars", "publish_state.json"), "w"))
    buf = io.StringIO()
    qb.main(args, db_factory=fac, now=NOW, out=buf)
    assert store == {} and "under 300s" in buf.getvalue()
    clock[0] += qb.INTRADAY_MIN_SEC
    qb.main(args, db_factory=fac, now=NOW, out=io.StringIO())
    assert len(store) == 1


def test_publish_failure_is_reported_not_raised(tmp_path):
    home = _make_home(tmp_path)

    class Broken(_FakeRef):
        def set(self, doc):
            raise RuntimeError("quota")
    buf = io.StringIO()
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda c: Broken({}, []), now=NOW, out=buf)
    assert rc == 1 and "publish failed (RuntimeError: quota)" in buf.getvalue()


# ── Webull attempts: sent vs held back by the book vs netted (real 09-23 pattern) ────
def _home_with_orders(tmp_path, trades, orders):
    home = _make_home(tmp_path)
    _write_csv(os.path.join(home, "qqq_exec", "trades.csv"), TR_HDR, trades)
    _write_csv(os.path.join(home, "qqq_exec", "broker_orders.csv"), BO_HDR, orders)
    return home


def test_held_back_tries_are_not_webull_refusals(tmp_path):
    """The real 2026-09-23 NOISE pattern (box broker_orders.csv): Webull refused the OPEN
    (sent=True ok=False), then the book itself held the CLOSE back (sent=False ok=False,
    'nothing to close at the broker ...'). Only the first is Webull's refusal. A trade
    whose every try was held back (never sent) is book only."""
    tid1, tid2 = "NOISE_304-20260928T140500Z-S", "NOISE_304-20260928T151500Z-L"
    home = _home_with_orders(tmp_path, [
        ["NOISE", "2026-09-28 10:10:29", "2026-09-28 11:00:33", "short", "10", "742.78",
         "742.28", "5.0", "signal exit", tid1],
        ["NOISE", "2026-09-28 11:20:29", "2026-09-28 11:30:09", "long", "10", "741.7",
         "742.1", "4.0", "signal exit", tid2],
    ], [
        ["2026-09-28 10:10:29", "NOISE", "OPEN", "SHORT", "10", qb.signal_id_base(tid1, "OPEN"),
         "", "PAPER", "False", "True", "742.78", "", "",
         "ServerException: HTTP Status: 417, Code: OPENAPI_GENERATE_NEW_SHORT_POSITION, Msg: "
         "This order will generate new short stock positions, which is not allowed. More.",
         "False", "edgelog", ""],
        ["2026-09-28 11:00:33", "NOISE", "CLOSE", "BUY", "10", qb.signal_id_base(tid1, "CLOSE"),
         "", "PAPER", "False", "False", "742.28", "", "",
         "nothing to close at the broker for leg 'NOISE': no position this adapter sent is "
         "held there (sent qty 0) -- its OPEN was blocked or failed, so this CLOSE is a no-op",
         "False", "edgelog", ""],
        ["2026-09-28 11:20:29", "NOISE", "OPEN", "BUY", "10", qb.signal_id_base(tid2, "OPEN"),
         "", "PAPER", "False", "False", "741.7", "", "",
         "halted: reconcile mismatch vs Webull: QQQ broker=10 shadow_sent=0", "False", "edgelog", ""],
        ["2026-09-28 11:30:09", "NOISE", "CLOSE", "SELL", "10", qb.signal_id_base(tid2, "CLOSE"),
         "", "PAPER", "False", "False", "742.1", "", "",
         "nothing to close at the broker for leg 'NOISE'", "False", "edgelog", ""],
    ])
    doc = qb.build_day_doc(DAY, qb.load_all(qb.default_paths(home)), now=NOW)
    m1, m2 = _mark(doc, tid1), _mark(doc, tid2)
    (o,), (c,) = m1["wb_in"], m1["wb_out"]
    assert (o["sent"], o["ok"], o["outcome"]) == (True, False, "REFUSED")
    assert o["why"].startswith("This order will generate new short stock positions")
    assert (c["sent"], c["ok"], c["outcome"]) == (False, False, "HELD")
    assert c["why"].startswith("nothing to close at the broker")   # the book's own words
    assert m1["book_only"] is False and "wb_gap" not in m1          # an order WAS sent
    assert [a["outcome"] for a in m2["wb_in"] + m2["wb_out"]] == ["HELD", "HELD"]
    assert m2["book_only"] is True                                  # nothing ever sent


def test_internal_cross_row_is_netted_not_refused(tmp_path):
    """_record_internal_cross writes sent=False ok=True outcome=NETTED at the cross price."""
    home = _home_with_orders(tmp_path, [
        ["ORB", "2026-09-28 10:50:06", "2026-09-28 15:59:01", "short", "10", "732.32", "736.76",
         "-44.4", "EOD", ORB_ID]], [
        ["2026-09-28 10:50:06", "ORB", "OPEN", "SHORT", "10", qb.signal_id_base(ORB_ID, "OPEN"),
         "c", "PAPER", "True", "True", "732.32", "732.58", "0.26", "", "False", "edgelog", "OK"],
        ["2026-09-28 15:59:01", "ORB", "CLOSE", "BUY", "10", qb.signal_id_base(ORB_ID, "CLOSE"),
         "", "PAPER", "True", "False", "736.76", "736.7", "-0.06",
         "flatten: crossed internally against ENGUQ (x1) -- already flat at Webull, no order sent",
         "False", "edgelog", "NETTED"]])
    m = _mark(qb.build_day_doc(DAY, qb.load_all(qb.default_paths(home)), now=NOW), ORB_ID)
    (x,) = m["wb_out"]
    assert (x["sent"], x["ok"], x["outcome"], x["px"]) == (False, True, "NETTED", 736.7)
    assert m["book_only"] is False


# ── a trimmed order ledger never becomes "book only" ──────────────────────────────────
TRIM_ID = "NOISE_382-20260928T133000Z-L"


def _trimmed_home(tmp_path):
    """The ledger's oldest row is 10:15:11; TRIM_ID traded 09:30-09:45 (its rows are gone)."""
    home = _make_home(tmp_path)
    with open(os.path.join(home, "qqq_exec", "trades.csv"), "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["NOISE", "2026-09-28 09:30:08", "2026-09-28 09:45:08", "long",
                                "10", "736", "737", "10", "signal exit", TRIM_ID])
    return home


def test_trade_older_than_the_order_ledger_is_not_book_only(tmp_path):
    home = _trimmed_home(tmp_path)
    data = qb.load_all(qb.default_paths(home))
    assert data["wb_from"] == "2026-09-28 10:15:11"
    m = _mark(qb.build_day_doc(DAY, data, now=NOW), TRIM_ID)
    assert m["wb_gap"] == ["in", "out"] and m["book_only"] is False
    assert _mark(qb.build_day_doc(DAY, data, now=NOW), BOOKONLY_ID)["book_only"] is True
    buf = io.StringIO()
    qb.main(["--dry-run", "--home", home, "--date", DAY], db_factory=None, now=NOW, out=buf)
    assert "predate the order ledger" in buf.getvalue()


def test_empty_order_ledger_marks_every_side_unknown(tmp_path):
    home = _make_home(tmp_path)
    _write_csv(os.path.join(home, "qqq_exec", "broker_orders.csv"), BO_HDR, [])
    data = qb.load_all(qb.default_paths(home))
    doc = qb.build_day_doc(DAY, data, now=NOW)
    assert data["wb_from"] is None
    assert all(m["wb_gap"] == ["in", "out"] and m["book_only"] is False for m in doc["marks"])


class _Store(_FakeRef):
    def get(self):
        v = self.store.get("/".join(self.path))
        return type("Snap", (), {"exists": v is not None, "to_dict": lambda s: v})()


def test_rewrite_keeps_the_published_webull_rows_for_trimmed_sides(tmp_path):
    """A --backfill after a bar-cache repair: the published copy's real Webull fill for a
    trade whose rows have since been trimmed must survive the rewrite."""
    home = _trimmed_home(tmp_path)
    key = "users/U1/qqq_bars/" + DAY
    fill = {"t": "2026-09-28 09:30:09", "px": 736.1, "ok": True, "sent": True, "outcome": "OK",
            "side": "BUY", "why": ""}
    store = {key: {"date": DAY, "marks": [{"trade_id": TRIM_ID, "wb_in": [fill], "wb_out": [],
                                           "book_only": False}]}}
    buf = io.StringIO()
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda c: _Store(store, []), now=NOW, out=buf)
    assert rc == 0 and "kept 2 Webull side(s)" in buf.getvalue()
    m = _mark(store[key], TRIM_ID)
    assert m["wb_in"] == [fill] and m["wb_out"] == [] and "wb_gap" not in m
    assert m["book_only"] is False


def test_rewrite_skips_a_day_whose_published_copy_cannot_be_read(tmp_path):
    home = _trimmed_home(tmp_path)

    class NoRead(_Store):
        def get(self):
            raise RuntimeError("deadline")
    store = {}
    buf = io.StringIO()
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda c: NoRead(store, []), now=NOW, out=buf)
    assert rc == 1 and store == {} and "could not read the published copy" in buf.getvalue()


# ── torn ledger reads (the exec trims by truncate + rewrite) ─────────────────────────
def test_torn_ledger_read_is_retried_then_refused(tmp_path):
    home = _make_home(tmp_path)
    bo = os.path.join(home, "qqq_exec", "broker_orders.csv")
    good = open(bo, encoding="utf-8", newline="").read()
    open(bo, "w").close()                                   # caught mid-trim: 0 bytes
    store, buf, naps = {}, io.StringIO(), []
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda c: _FakeRef(store, []), now=NOW, out=buf, sleep=naps.append)
    assert rc == 1 and store == {} and "mid-rewrite" in buf.getvalue()
    assert naps == [qb.LEDGER_RETRY_SEC]

    def heal(_sec):                                         # the rewrite finishes meanwhile
        with open(bo, "w", encoding="utf-8", newline="") as f:
            f.write(good)
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda c: _FakeRef(store, []), now=NOW, out=io.StringIO(), sleep=heal)
    assert rc == 0 and _mark(store["users/U1/qqq_bars/" + DAY], NOISE_ID)["wb_in"]


def test_short_row_and_row_count_drop_are_suspicious(tmp_path):
    home = _make_home(tmp_path)
    tr = os.path.join(home, "qqq_exec", "trades.csv")
    with open(tr, "a", encoding="utf-8", newline="") as f:
        f.write("NOISE,2026-09-28 15:00:00\r\n")            # cut off mid-row
    with pytest.raises(qb.LedgerUnreliable):
        qb.read_ledger(tr, sleep=lambda s: None)
    _write_csv(tr, TR_HDR, [["NOISE", "2026-09-28 10:15:11", "2026-09-28 11:40:09", "short",
                             "20", "1", "1", "0", "x", NOISE_ID]])
    # 1 row where the last run saw 40: accepted only because it holds still on the re-read
    assert len(qb.read_ledger(tr, prev_count=40, sleep=lambda s: None)) == 1


def test_state_file_remembers_ledger_row_counts(tmp_path):
    home = _make_home(tmp_path)
    qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
            db_factory=lambda c: _FakeRef({}, []), now=NOW, out=io.StringIO())
    st = json.load(open(os.path.join(home, "qqq_bars", "publish_state.json")))
    assert st["_ledger_rows"] == {"trades": 6, "broker_orders": 7}


# ── guards: too many days, a hung Firestore call ─────────────────────────────────────
def test_backfill_wider_than_max_days_needs_yes_many(tmp_path, monkeypatch):
    home = _make_home(tmp_path)
    monkeypatch.setattr(qb, "MAX_DAYS", 0)
    buf = io.StringIO()
    assert qb.main(["--dry-run", "--home", home, "--backfill", "2026-06-08"],
                   db_factory=None, now=NOW, out=buf) == 2
    assert "REFUSED" in buf.getvalue() and "--yes-many" in buf.getvalue()
    assert qb.main(["--dry-run", "--home", home, "--backfill", "2026-06-08", "--yes-many"],
                   db_factory=None, now=NOW, out=io.StringIO()) == 0


def test_hung_set_times_out_on_a_daemon_thread():
    import threading
    import time as _t
    gate = threading.Event()

    class Hung(_FakeRef):
        def set(self, doc):
            gate.wait(30)
    t0 = _t.time()
    with pytest.raises(TimeoutError):
        qb.publish_doc(Hung({}, []), "U1", {"date": DAY}, timeout=0.2)
    assert _t.time() - t0 < 5
    hung = [th for th in threading.enumerate() if th.name == "qqq-bars-set"]
    assert hung and all(th.daemon for th in hung)          # cannot hold the process open
    gate.set()


# ── outcome column: an answer that never came back is not a refusal (2026-09-29) ─────
def _orders_home(tmp_path, orders, trades=None):
    return _home_with_orders(tmp_path, trades or [
        ["ENGUQ", "2026-09-28 12:33:38", "2026-09-28 15:59:01", "long", "10", "738.0395",
         "736.66", "-13.8", "EOD", ENGU_ID]], orders)


def _bo(ts, intent, sid, ok, sent, px="", reason="", outcome="", mode="PAPER", side="SELL"):
    return [ts, "ENGUQ", intent, side, "10", sid, "c", mode, ok, sent, "736.66", px, "",
            reason, "False", "edgelog", outcome]


def test_unknown_outcome_is_not_refused_and_carries_what_came_next(tmp_path):
    base = qb.signal_id_base(ENGU_ID, "CLOSE")
    home = _orders_home(tmp_path, [
        _bo("2026-09-28 15:59:01", "CLOSE", base, "False", "True",
            reason="hard timeout: no answer from Webull after 25s", outcome="UNKNOWN"),
        _bo("2026-09-28 15:59:40", "CLOSE", base + "R1", "True", "True", px="736.58", outcome="OK"),
    ])
    m = _mark(qb.build_day_doc(DAY, qb.load_all(qb.default_paths(home)), now=NOW), ENGU_ID)
    u, r = m["wb_out"]
    assert (u["sent"], u["ok"], u["outcome"]) == (True, False, "UNKNOWN")
    assert u["then"] == {"t": "2026-09-28 15:59:40", "outcome": "OK", "px": 736.58}
    assert r["outcome"] == "OK" and r.get("resend") is True and "then" not in r
    assert "wb_part" not in m                      # the first try is on file


def test_rows_without_the_outcome_column_are_read_like_the_exec_writes_them():
    """Old rows (no outcome column): sent + not ok is a refusal only with a definite 4xx;
    a timeout / 5xx / dropped connection is UNKNOWN. Not-sent rows are never Webull's."""
    oc = qb.row_outcome
    assert oc({"sent": "True", "ok": "False",
               "reason": "ServerException: HTTP Status: 417, Code: X, Msg: no"}) == "REFUSED"
    assert oc({"sent": "True", "ok": "False", "reason": "ReadTimeout: read timed out"}) == "UNKNOWN"
    assert oc({"sent": "True", "ok": "False", "reason": "ServerException: HTTP Status: 503"}) == "UNKNOWN"
    assert oc({"sent": "True", "ok": "True"}) == "OK"
    assert oc({"sent": "", "ok": "True"}) == "OK"                      # blank sent = sent
    assert oc({"sent": "True", "ok": "False", "outcome": "WORKING"}) == "UNKNOWN"
    assert oc({"sent": "True", "ok": "False", "outcome": "unknown"}) == "UNKNOWN"
    # the column wins where it exists, even over a 4xx-looking reason
    assert oc({"sent": "True", "ok": "False", "outcome": "UNKNOWN", "reason": "HTTP 417"}) == "UNKNOWN"
    # never sent: the exec's column says REFUSED / BLOCKED for these -- neither is Webull's
    assert oc({"sent": "False", "ok": "False", "mode": "ERROR", "outcome": "REFUSED"}) == "ERROR"
    assert oc({"sent": "False", "ok": "False", "mode": "BLOCKED", "outcome": "BLOCKED"}) == "HELD"
    assert oc({"sent": "False", "ok": "False", "mode": "PAPER", "outcome": "REFUSED"}) == "HELD"
    assert oc({"sent": "False", "ok": "True", "outcome": "NETTED"}) == "NETTED"
    assert oc({"sent": "False", "ok": "True",
               "reason": "flatten: crossed internally against NOISE_382"}) == "NETTED"
    # an ok row logged while Webull orders were OFF is not a netted cross
    assert oc({"sent": "False", "ok": "True", "mode": "OFF", "outcome": "OK"}) == "HELD"
    # a rail-blocked row is held back even when the old blank sent field reads as sent
    assert oc({"sent": "", "ok": "False", "mode": "BLOCKED", "reason": "rail"}) == "HELD"
    assert oc({"sent": "True", "ok": "False", "outcome": "BLOCKED"}) == "HELD"


def test_http_status_pattern_matches_the_adapter():
    from api import webull_orders
    assert qb._HTTP_STATUS_RE.pattern == webull_orders._HTTP_STATUS_RE.pattern


def test_exec_outcome_column_round_trip():
    """What api/qqq_exec.py writes for each failure shape reads back as the same class."""
    from api.qqq_exec import _broker_row_outcome
    cases = [
        ({"ok": False, "sent": True, "reason": "ServerException: HTTP Status: 417, Msg: x"}, "REFUSED"),
        ({"ok": False, "sent": True, "error": "ConnectionError: dropped"}, "UNKNOWN"),
        ({"ok": False, "sent": True, "outcome": "UNKNOWN", "reason": "hard timeout"}, "UNKNOWN"),
        ({"ok": True, "sent": True}, "OK"),
        ({"ok": False, "sent": False, "mode": "ERROR", "error": "ValueError: bad"}, "ERROR"),
        ({"ok": False, "sent": False, "mode": "BLOCKED", "reason": "rail"}, "HELD"),
    ]
    for rec, want in cases:
        row = {"ok": str(rec.get("ok")), "sent": str(rec.get("sent")), "mode": rec.get("mode", "PAPER"),
               "reason": rec.get("reason") or rec.get("error") or "",
               "outcome": _broker_row_outcome(rec)}
        assert qb.row_outcome(row) == want, (rec, row)
        row.pop("outcome")                          # an old row: same reading without it
        assert qb.row_outcome(row) == want, (rec, row)


def test_failed_order_call_is_error_not_held(tmp_path):
    base = qb.signal_id_base(ENGU_ID, "OPEN")
    home = _orders_home(tmp_path, [
        _bo("2026-09-28 12:33:38", "OPEN", base, "False", "False", mode="ERROR",
            reason="TypeError: place_stock_order() got an unexpected keyword", outcome="REFUSED",
            side="BUY")])
    m = _mark(qb.build_day_doc(DAY, qb.load_all(qb.default_paths(home)), now=NOW), ENGU_ID)
    (a,) = m["wb_in"]
    assert (a["sent"], a["ok"], a["outcome"]) == (False, False, "ERROR")
    assert a["why"].startswith("TypeError")


def test_partly_crossed_leg_row_joins_its_trade(tmp_path):
    """_record_internal_cross: a partly crossed leg's netted row is the CLOSE id + "X"."""
    base = qb.signal_id_base(ENGU_ID, "CLOSE")
    home = _orders_home(tmp_path, [
        _bo("2026-09-28 12:33:38", "OPEN", qb.signal_id_base(ENGU_ID, "OPEN"), "True", "True",
            px="738.56", outcome="OK", side="BUY"),
        _bo("2026-09-28 15:59:01", "CLOSE", base + "X", "True", "False", px="736.7",
            reason="flatten: crossed internally", outcome="NETTED"),
        _bo("2026-09-28 15:59:01", "CLOSE", base, "True", "True", px="736.58", outcome="OK"),
    ])
    data = qb.load_all(qb.default_paths(home))
    assert base + "X" not in data["brokers"]
    m = _mark(qb.build_day_doc(DAY, data, now=NOW), ENGU_ID)
    assert [a["outcome"] for a in m["wb_out"]] == ["NETTED", "OK"]
    assert "wb_part" not in m


def test_over_long_row_is_torn(tmp_path):
    home = _make_home(tmp_path)
    tr = os.path.join(home, "qqq_exec", "trades.csv")
    with open(tr, "a", encoding="utf-8", newline="") as f:
        # two rows run together (the rewrite caught mid-write): extra fields
        csv.writer(f).writerow(["NOISE", "2026-09-28 15:00:00", "2026-09-28 15:10:00", "short",
                                "10", "1", "1", "0", "x", "T1", "NOISE", "2026"])
    rows = list(csv.DictReader(open(tr, encoding="utf-8", newline="")))
    assert None in rows[-1]                        # csv files the extras under the key None
    with pytest.raises(qb.LedgerUnreliable):
        qb.read_ledger(tr, sleep=lambda s: None)


# ── a trim that cuts INSIDE one side: the resend kept, the unanswered first try gone ──
PART_ID = "NOISE_382-20260928T133000Z-S"


def _part_home(tmp_path):
    base = qb.signal_id_base(PART_ID, "CLOSE")
    return _home_with_orders(tmp_path, [
        ["NOISE", "2026-09-28 09:30:08", "2026-09-28 10:20:05", "short", "10", "736", "737",
         "-10", "signal exit", PART_ID]], [
        ["2026-09-28 10:20:10", "NOISE", "CLOSE", "BUY", "10", base + "R1", "c", "PAPER", "True",
         "True", "737", "737.02", "0.02", "", "False", "edgelog", "OK"]])


def test_side_cut_inside_is_marked_and_the_published_rows_put_back(tmp_path):
    home = _part_home(tmp_path)
    data = qb.load_all(qb.default_paths(home))
    m = _mark(qb.build_day_doc(DAY, data, now=NOW), PART_ID)
    assert m["wb_gap"] == ["in"] and m["wb_part"] == ["out"]
    unanswered = {"t": "2026-09-28 10:20:05", "px": None, "ok": False, "sent": True,
                  "outcome": "UNKNOWN", "side": "BUY", "why": "timed out"}
    kept_fill = {"t": "2026-09-28 10:20:10", "px": 737.02, "ok": True, "sent": True,
                 "outcome": "OK", "side": "BUY", "why": "", "resend": True}
    fill_in = {"t": "2026-09-28 09:30:09", "px": 736.1, "ok": True, "sent": True, "outcome": "OK",
               "side": "SELL", "why": ""}
    key = "users/U1/qqq_bars/" + DAY
    prior = {"date": DAY, "marks": [{"trade_id": PART_ID, "wb_in": [fill_in],
                                     "wb_out": [unanswered], "book_only": False}]}
    store = {key: prior}
    buf = io.StringIO()
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda c: _Store(store, []), now=NOW, out=buf)
    assert rc == 0 and "kept 2 Webull side(s)" in buf.getvalue()
    m = _mark(store[key], PART_ID)
    assert "wb_gap" not in m and "wb_part" not in m
    assert [a["outcome"] for a in m["wb_out"]] == ["UNKNOWN", "OK"]
    assert m["wb_out"][1] == kept_fill
    # the unanswered try now says what the ledger shows happened next
    assert m["wb_out"][0]["then"] == {"t": "2026-09-28 10:20:10", "outcome": "OK", "px": 737.02}
    assert "then" not in unanswered                # the copy read back was not mutated
    assert m["wb_in"] == [fill_in]


def test_side_cut_inside_stays_marked_when_the_copy_lacks_the_rows(tmp_path):
    home = _part_home(tmp_path)
    key = "users/U1/qqq_bars/" + DAY
    store = {key: {"date": DAY, "marks": [{"trade_id": PART_ID, "wb_in": [], "wb_out": [],
                                           "wb_gap": ["in"], "wb_part": ["out"]}]}}
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1"],
                 db_factory=lambda c: _Store(store, []), now=NOW, out=io.StringIO())
    m = _mark(store[key], PART_ID)
    assert rc == 0 and m["wb_part"] == ["out"] and m["wb_gap"] == ["in"]


def test_size_cap_is_checked_again_after_the_merge(tmp_path):
    """The published copy's rows are merged back AFTER the first cap check: an oversize
    result must drop its 1-minute bars (or be refused), never be written as is."""
    home = _trimmed_home(tmp_path)
    key = "users/U1/qqq_bars/" + DAY
    row = {"t": "2026-09-28 09:30:09", "px": 736.1, "ok": True, "sent": True,
           "outcome": "OK", "side": "BUY", "why": "x" * 120}
    doc0 = qb.build_day_doc(DAY, qb.load_all(qb.default_paths(home)), now=NOW)
    one_m = len(doc0["bars"]["1m"])
    n = (one_m - 3_000) // (len(json.dumps(row, separators=(",", ":"))) + 1)
    big = [dict(row) for _ in range(n)]            # adds a bit less than the 1m string
    cap = qb.doc_size(doc0) + 1_000                # the fresh doc fits, the merged one not
    store = {key: {"date": DAY, "marks": [{"trade_id": TRIM_ID, "wb_in": big, "wb_out": [],
                                           "book_only": False}]}}
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1", "--cap", str(cap)],
                 db_factory=lambda c: _Store(store, []), now=NOW, out=io.StringIO())
    written = store[key]
    assert rc == 0 and len(_mark(written, TRIM_ID)["wb_in"]) == n
    assert qb.doc_size(written) <= cap and written.get("bars_dropped") == ["1m"]
    assert written["final"] is False
    huge = {"date": DAY, "marks": [{"trade_id": TRIM_ID, "wb_in": big * 3, "wb_out": [],
                                    "book_only": False}]}
    store2 = {key: huge}
    buf = io.StringIO()
    rc = qb.main(["--home", home, "--date", DAY, "--uid", "U1", "--cap", str(cap)],
                 db_factory=lambda c: _Store(store2, []), now=NOW, out=buf)
    assert rc == 1 and "after keeping the published Webull rows" in buf.getvalue()
    assert store2[key] is huge                     # nothing overwritten
