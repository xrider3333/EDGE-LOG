"""api/trade_bars.py - SHOULD HAVE TRADED entries (users/{uid}/missed_trades -> trade_bars/missed_{id}
+ pointScore) and the whole-session 1-minute window (2026-10-02). Fake Firestore, no network, no
C:\\EdgeLog (state file, fills file and price masters are all stubbed)."""
import json
import types
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from api import trade_bars as tb

ET = "America/New_York"
UID = "u"
NOBAR = "no 1-minute bar for the signal minute"


# ── a small fake Firestore ──────────────────────────────────────────────────────────────────
class NotFound(Exception):
    """Same class name as google.api_core.exceptions.NotFound."""


class _Snap:
    def __init__(self, id_, data):
        self.id, self._d = id_, data

    def to_dict(self):
        return dict(self._d)


class _Ref:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, name):
        return _Coll(self.db, self.path + "/" + name)

    def set(self, data, merge=False):
        cur = self.db.store.get(self.path, {}) if merge else {}
        self.db.store[self.path] = dict(cur, **data)
        self.db.writes.append(("set", self.path, sorted(data)))

    def update(self, data):
        if self.path not in self.db.store:
            raise NotFound(self.path)
        self.db.store[self.path] = dict(self.db.store[self.path], **data)
        self.db.writes.append(("update", self.path, sorted(data)))


class _Coll:
    def __init__(self, db, path, flt=None):
        self.db, self.path, self.flt = db, path, flt

    def document(self, name):
        return _Ref(self.db, self.path + "/" + name)

    def where(self, filter=None):
        return _Coll(self.db, self.path, filter)

    def stream(self):
        pre = self.path + "/"
        out = []
        for p, d in sorted(self.db.store.items()):
            if p.startswith(pre) and "/" not in p[len(pre):]:
                if self.flt is not None:
                    v = d.get(self.flt.field_path)
                    if v is None or not v >= self.flt.value:            # a doc without the field never matches
                        continue
                out.append(_Snap(p[len(pre):], d))
        flt = None if self.flt is None else (self.flt.field_path, self.flt.op_string, self.flt.value)
        self.db.queries.append((self.path, flt, len(out)))
        return out


class _Db:
    def __init__(self):
        self.store, self.queries, self.writes = {}, [], []

    def collection(self, name):
        return _Coll(self, name)


# ── fixtures ────────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Fresh module state per test; nothing may touch C:\\EdgeLog."""
    for name in ("_last_sweep", "_missed_mem", "_missed_since"):
        monkeypatch.setattr(tb, name, {})
    monkeypatch.setattr(tb, "_full_done", set())
    state = {}
    monkeypatch.setattr(tb, "_load_state", lambda path=None: state)
    monkeypatch.setattr(tb, "_save_state", lambda st, path=None: None)
    monkeypatch.setattr(tb, "_fills_index", lambda path=None: ({}, {}))
    reads = []
    monkeypatch.setattr(tb, "_note_reads", lambda n: reads.append(n))
    return types.SimpleNamespace(state=state, reads=reads)


def _score(tt, total=7):
    return {"v": "ps1.1", "total": total, "max": 9, "na_count": 0, "trend": None, "signal_bar": "s",
            "points": [{"k": "a", "hit": True, "na_reason": None}], "sig": tb.signature(tt)}


class _Engine:
    """Stands in for build() and point_score(): records what they were given."""

    def __init__(self, monkeypatch, complete=True):
        self.complete, self.builds, self.scores, self.total = complete, [], [], 7
        monkeypatch.setattr(tb, "_point_score_module",
                            lambda: types.SimpleNamespace(VERSION="ps1.1", NA_NOBAR=NOBAR, NA_NO10BAR="x", NA_NO10="y"))
        monkeypatch.setattr(tb, "build", self.build)
        monkeypatch.setattr(tb, "point_score", self.point_score)

    def build(self, t, key, fills=None, cache=None, now=None):
        self.builds.append((key, dict(t)))
        return {"v": 1, "trade_id": key, "b1m": {"s": "0,1,1,1,1,1"}, "b10s": None,
                "complete": self.complete, "covers": True}, None

    def point_score(self, t, fills=None):
        self.scores.append(dict(t))
        return _score(t, self.total)


def _missed(**kw):
    d = {"url": "https://www.tradingview.com/x/abc/", "setup": "ORB", "symbol": "MNQ", "date": "2026-09-30",
         "entryTime": "10:00", "type": "LONG", "note": "late", "entry": 30000.25, "stop": 29990.0,
         "target": 30020.0, "source": "web", "createdAt": datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc),
         "updatedAt": datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)}
    d.update(kw)
    return d


def _put(db, coll, id_, d):
    db.store[f"users/{UID}/{coll}/{id_}"] = d


def _sweep(db):
    return tb.sweep(db, UID, log=lambda *_: None, force=True)


# ── TASK 1: SHOULD HAVE TRADED entries ──────────────────────────────────────────────────────
def test_a_missed_entry_gets_a_bars_doc_and_only_a_point_score_merged_back(monkeypatch, _isolate):
    eng = _Engine(monkeypatch)
    db = _Db()
    original = _missed()
    _put(db, "missed_trades", "a1", dict(original))
    _put(db, "missed_trades", "stock1", _missed(symbol="AAPL"))             # not a futures root: left alone
    assert _sweep(db) == 1

    # the bars doc: trade_bars/missed_a1, built from the entry as a trade with no exit
    assert f"users/{UID}/trade_bars/missed_a1" in db.store
    assert f"users/{UID}/trade_bars/missed_stock1" not in db.store
    key, t = eng.builds[0]
    assert key == "missed_a1"
    assert (t["date"], t["entryTime"], t["exitTime"], t["entry"], t["type"], t["symbol"]) == \
           ("2026-09-30", "10:00", "10:00", None, "LONG", "MNQ")      # a snapshot level never shifts the chart

    # the point score: merged onto the missed_trades doc, every other field untouched
    got = db.store[f"users/{UID}/missed_trades/a1"]
    assert got["pointScore"]["total"] == 7
    assert {k: v for k, v in got.items() if k != "pointScore"} == original
    assert [w for w in db.writes if "missed_trades" in w[1]] == [("update", f"users/{UID}/missed_trades/a1", ["pointScore"])]
    assert "pointScore" not in db.store[f"users/{UID}/missed_trades/stock1"]
    # nothing was written to the journal
    assert not [w for w in db.writes if w[1].startswith(f"users/{UID}/trades/")]
    assert set(_isolate.state) == {"missed_a1"}


def test_a_missed_id_never_collides_with_a_trade_id(monkeypatch, _isolate):
    _Engine(monkeypatch)
    db = _Db()
    today = pd.Timestamp.now(tz=ET).strftime("%Y-%m-%d")
    _put(db, "trades", "x1", {"date": today, "entryTime": "09:40", "exitTime": "09:50", "entry": 1, "exit": 2,
                              "type": "LONG", "symbol": "MNQ", "size": 1})
    _put(db, "missed_trades", "x1", _missed())
    assert _sweep(db) == 2
    assert f"users/{UID}/trade_bars/x1" in db.store and f"users/{UID}/trade_bars/missed_x1" in db.store
    assert set(_isolate.state) == {"x1", "missed_x1"}
    # the trade's score landed on the trade, the entry's on the entry
    assert db.store[f"users/{UID}/trades/x1"]["pointScore"]["total"] == 7
    assert db.store[f"users/{UID}/missed_trades/x1"]["pointScore"]["total"] == 7


def test_the_score_is_taken_at_the_entry_minute(monkeypatch):
    seen = []
    mod = types.SimpleNamespace(VERSION="ps1.1", score_trade=lambda tr: seen.append(tr) or {"total": 7, "max": 9})
    monkeypatch.setattr(tb, "_point_score_module", lambda: mod)
    rec = tb.point_score(tb._missed_trade(_missed(type="SHORT")))
    assert seen == [{"sym": "MNQ", "side": "SHORT", "fill": "2026-09-30 10:00:00"}]
    assert rec["fill"] == "2026-09-30 10:00:00" and rec["total"] == 7


def test_the_first_sweep_reads_everything_then_only_what_changed(monkeypatch, _isolate):
    eng = _Engine(monkeypatch, complete=False)             # the chart is not final yet
    db = _Db()
    _put(db, "missed_trades", "a1", _missed())
    _put(db, "missed_trades", "a2", _missed(entryTime="10:30", updatedAt=datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)))

    _sweep(db)
    first = [q for q in db.queries if q[0].endswith("missed_trades")]
    assert first == [(f"users/{UID}/missed_trades", None, 2)]                 # one full read
    assert _isolate.reads == [1, 2]                                           # journal (empty: 1), missed (2)
    assert [b[0] for b in eng.builds] == ["missed_a1", "missed_a2"]
    t_first = tb._missed_since[UID]

    _isolate.reads.clear()
    db.queries.clear()
    eng.builds.clear()
    _sweep(db)
    second = [q for q in db.queries if q[0].endswith("missed_trades")]
    assert len(second) == 1
    path, flt, n = second[0]
    assert flt == ("updatedAt", ">=", t_first - timedelta(minutes=10)) and flt[2].tzinfo is not None
    assert n == 0                                                             # nothing edited
    assert _isolate.reads == [1, 1]                                           # an empty query is still billed 1 read
    # the unfinished charts were re-processed from memory: no re-read of the docs
    assert [b[0] for b in eng.builds] == ["missed_a1", "missed_a2"]


def test_a_finished_entry_is_not_rebuilt_and_an_edited_one_is(monkeypatch, _isolate):
    eng = _Engine(monkeypatch, complete=False)
    db = _Db()
    _put(db, "missed_trades", "a1", _missed())
    _sweep(db)
    assert len(eng.builds) == 1 and len(eng.scores) == 1

    eng.complete = True
    _sweep(db)                                                                # unfinished: built again, memory copy has its score
    assert len(eng.builds) == 2 and len(eng.scores) == 1
    stored = db.store[f"users/{UID}/missed_trades/a1"]["pointScore"]
    assert tb._missed_mem[UID]["a1"]["pointScore"] == stored                  # memory knows what was stored

    _sweep(db)                                                                # complete + scored: untouched
    assert len(eng.builds) == 2 and len(eng.scores) == 1

    # the owner edits the entry time: the web bumps updatedAt, the next sweep picks it up and redoes both
    d = db.store[f"users/{UID}/missed_trades/a1"]
    d.update(entryTime="10:45", updatedAt=datetime.now(timezone.utc))
    _sweep(db)
    assert len(eng.builds) == 3 and eng.builds[-1][1]["entryTime"] == "10:45"
    assert len(eng.scores) == 2


def test_a_deleted_entry_is_dropped_without_a_ghost_doc(monkeypatch, _isolate):
    eng = _Engine(monkeypatch, complete=False)
    db = _Db()
    _put(db, "missed_trades", "a1", _missed())
    _sweep(db)
    assert "a1" in tb._missed_mem[UID]
    del db.store[f"users/{UID}/missed_trades/a1"]                             # deleted in the web
    # a spec bump makes the score due again, so the next sweep tries to merge it and finds nothing there
    monkeypatch.setattr(tb, "_point_score_module",
                        lambda: types.SimpleNamespace(VERSION="ps2", NA_NOBAR=NOBAR, NA_NO10BAR="x", NA_NO10="y"))
    eng.total = 8                                                             # and the new spec scores it differently
    n_builds = len(eng.builds)
    _sweep(db)
    assert f"users/{UID}/missed_trades/a1" not in db.store                    # not re-created
    assert "a1" not in tb._missed_mem[UID]
    assert len(eng.builds) == n_builds                                        # and no more chart rebuilds for it
    _sweep(db)
    assert len(eng.builds) == n_builds


def test_a_bad_missed_entry_does_not_block_the_others(monkeypatch, master, _isolate):
    _write_master(master, "2026-09-29 18:00", "2026-09-30 16:59")
    mod = types.SimpleNamespace(VERSION="ps1.1", NA_NOBAR=NOBAR, NA_NO10BAR="x", NA_NO10="y",
                                score_trade=lambda tr: {"total": 7, "max": 9, "na_count": 0, "trend": None,
                                                        "signal_bar": "s", "points": []})
    monkeypatch.setattr(tb, "_point_score_module", lambda: mod)
    db = _Db()
    _put(db, "missed_trades", "bad1", _missed(date="2026-13-45"))             # not a date
    _put(db, "missed_trades", "bad2", _missed(entryTime="10:5"))              # not a time
    _put(db, "missed_trades", "bad3", _missed(entry="abc"))                   # not a price: charted without one
    _put(db, "missed_trades", "ok", _missed(entry=None))
    _sweep(db)
    for i in ("bad3", "ok"):
        assert f"users/{UID}/trade_bars/missed_{i}" in db.store, i
        assert db.store[f"users/{UID}/missed_trades/{i}"]["pointScore"]["total"] == 7
    for i in ("bad1", "bad2"):
        assert f"users/{UID}/trade_bars/missed_{i}" not in db.store
        assert "pointScore" not in db.store[f"users/{UID}/missed_trades/{i}"]
        assert _isolate.state[f"missed_{i}"]["skip"] == "no_times"            # final: never retried
    assert db.store[f"users/{UID}/trade_bars/missed_bad3"]["entry"]["px"] is None
    assert tb._missed_trade({"entry": "abc"})["entry"] is None and tb._missed_trade({"entry": float("nan")})["entry"] is None


def test_a_failed_missed_read_is_retried_as_a_full_read(monkeypatch, _isolate):
    _Engine(monkeypatch)
    db = _Db()
    _put(db, "missed_trades", "a1", _missed())
    orig_stream, calls = _Coll.stream, []

    def flaky(self):                                      # the missed_trades read fails once (quota, network)
        if self.path.endswith("missed_trades") and not calls:
            calls.append(1)
            raise RuntimeError("quota")
        return orig_stream(self)

    monkeypatch.setattr(_Coll, "stream", flaky)
    logs = []
    tb.sweep(db, UID, log=logs.append, force=True)        # must not raise: the journal side is unaffected
    assert UID not in tb._missed_since and any("missed entries skipped" in m for m in logs)
    tb.sweep(db, UID, log=logs.append, force=True)
    assert f"users/{UID}/trade_bars/missed_a1" in db.store and UID in tb._missed_since
    assert [q[1] for q in db.queries if q[0].endswith("missed_trades")] == [None]   # retried as the full read


# ── TASK 2: the session window ──────────────────────────────────────────────────────────────
def _ts(s):
    return pd.Timestamp(s, tz=ET)


def _bounds(s):
    a, b = tb._session_bounds(_ts(s))
    return (pd.Timestamp(a, unit="s", tz="UTC").tz_convert(ET).strftime("%Y-%m-%d %H:%M %Z"),
            pd.Timestamp(b, unit="s", tz="UTC").tz_convert(ET).strftime("%Y-%m-%d %H:%M %Z"))


def test_session_bounds_for_a_day_entry():
    assert _bounds("2026-09-30 10:00") == ("2026-09-29 18:00 EDT", "2026-09-30 17:00 EDT")
    assert _bounds("2026-09-30 17:59") == ("2026-09-29 18:00 EDT", "2026-09-30 17:00 EDT")
    assert _bounds("2026-09-30 00:05") == ("2026-09-29 18:00 EDT", "2026-09-30 17:00 EDT")   # overnight part of the same session


def test_session_bounds_for_an_entry_at_or_after_the_evening_open():
    assert _bounds("2026-09-30 18:30") == ("2026-09-30 18:00 EDT", "2026-10-01 17:00 EDT")   # next session
    assert _bounds("2026-09-30 18:00") == ("2026-09-30 18:00 EDT", "2026-10-01 17:00 EDT")
    assert _bounds("2026-10-02 18:30") == ("2026-10-02 18:00 EDT", "2026-10-03 17:00 EDT")   # Friday evening -> Saturday date
    assert _bounds("2026-10-04 19:00") == ("2026-10-04 18:00 EDT", "2026-10-05 17:00 EDT")   # Sunday open
    assert _bounds("2026-10-05 09:30") == ("2026-10-04 18:00 EDT", "2026-10-05 17:00 EDT")   # Monday: starts Sunday


def test_session_bounds_follow_the_wall_clock_across_a_dst_change():
    # spring forward Sun 2026-03-08 02:00: Mon's session is entirely EDT (23 h), Sun's runs EST -> EDT (22 h)
    a, b = tb._session_bounds(_ts("2026-03-09 10:00"))
    assert (b - a) == 23 * 3600
    assert _bounds("2026-03-09 10:00") == ("2026-03-08 18:00 EDT", "2026-03-09 17:00 EDT")
    a, b = tb._session_bounds(_ts("2026-03-08 12:00"))
    assert _bounds("2026-03-08 12:00") == ("2026-03-07 18:00 EST", "2026-03-08 17:00 EDT") and (b - a) == 22 * 3600
    # fall back Sun 2026-11-01 02:00: 24 h
    a, b = tb._session_bounds(_ts("2026-11-01 12:00"))
    assert _bounds("2026-11-01 12:00") == ("2026-10-31 18:00 EDT", "2026-11-01 17:00 EST") and (b - a) == 24 * 3600
    assert _bounds("2026-11-02 10:00") == ("2026-11-01 18:00 EST", "2026-11-02 17:00 EST")
    # a time given in UTC is read as the ET wall-clock it is
    a, b = tb._session_bounds(pd.Timestamp("2026-09-30 14:00", tz="UTC"))
    assert (a, b) == tb._session_bounds(_ts("2026-09-30 10:00"))


# ── build(): window, completeness, size ─────────────────────────────────────────────────────
def _epoch(s):
    return int(_ts(s).timestamp())


def _write_master(path, first, last, px=30000.0):
    """1-minute master rows (bar-START epochs) from ET wall-clock 'first' to 'last' inclusive."""
    t, n = _epoch(first), 0
    with open(path, "w") as f:
        f.write("time,open,high,low,close,volume\n")
        while t <= _epoch(last):
            p = px + (n % 40) * 0.25
            f.write(f"{t},{p},{p + 2.75},{p - 1.5},{p + 0.5},{1500 + n % 900}\n")
            t += 60
            n += 1


def _trade_for_build():
    return {"date": "2026-09-30", "entryTime": "10:00", "exitTime": "10:05", "entry": 30000.0, "exit": 30003.0,
            "type": "LONG", "symbol": "MNQ", "size": 1}


@pytest.fixture
def master(tmp_path, monkeypatch):
    m = tmp_path / "m.csv"
    monkeypatch.setattr(tb, "_master_path", lambda inst: (str(m), "NOADJ"))
    monkeypatch.setattr(tb, "_read_10s", lambda inst, cache: None)
    return m


def _build(now, t=None):
    doc, why = tb.build(t or _trade_for_build(), "x", ({}, {}), {}, _ts(now))
    assert why is None, why
    return doc


def test_the_chart_is_the_whole_session_and_complete_only_at_its_end(master):
    _write_master(master, "2026-09-29 18:00", "2026-09-30 14:00")            # the master has run only to 14:00
    doc = _build("2026-09-30 14:10")
    assert doc["b1m"]["t0"] == _epoch("2026-09-29 18:00")                     # from the session open
    assert doc["covers"] and not doc["complete"]
    last = doc["b1m"]["t0"] + int(doc["b1m"]["s"].rsplit(";", 1)[1].split(",")[0]) * 60
    assert last == _epoch("2026-09-30 14:00")

    _write_master(master, "2026-09-29 18:00", "2026-09-30 16:56")            # last bar 16:56 -> reaches 16:57
    assert not _build("2026-09-30 17:30")["complete"]
    _write_master(master, "2026-09-29 18:00", "2026-09-30 16:57")            # reaches 16:58 = session end - 2 min
    doc = _build("2026-09-30 17:30")
    assert doc["complete"]
    assert len(json.dumps(doc)) < tb.DOC_CAP_BYTES                           # a full session fits the doc cap
    assert doc["b1m"]["s"].count(";") + 1 == 1378


def test_an_unfinished_chart_is_given_up_two_hours_after_the_session_end(master):
    _write_master(master, "2026-09-29 18:00", "2026-09-30 14:00")
    assert not _build("2026-09-30 18:59")["complete"]
    assert _build("2026-09-30 19:00")["complete"]                             # 17:00 + 2 h
    assert _build("2026-10-01 08:00")["complete"]


def test_the_session_end_is_wall_clock_in_a_dst_week(master):
    _write_master(master, "2026-03-08 18:00", "2026-03-09 14:00")
    t = dict(_trade_for_build(), date="2026-03-09")
    # Mon 2026-03-09 17:00 EDT = 21:00 UTC; give-up at 19:00 EDT
    assert not _build("2026-03-09 18:59", t)["complete"]
    assert _build("2026-03-09 19:00", t)["complete"]


def test_a_trade_held_across_the_close_runs_to_the_end_of_the_session_it_exits_in(master):
    _write_master(master, "2026-09-29 18:00", "2026-09-30 16:59")
    t = dict(_trade_for_build(), entryTime="16:55", exitTime="18:05")        # in at 16:55, out after the 18:00 reopen
    doc = _build("2026-09-30 17:30", t)
    assert not doc["complete"] and not doc["covers"]                          # the exit bar is not there yet
    _write_master(master, "2026-09-29 18:00", "2026-10-01 16:59")
    doc = _build("2026-10-01 17:30", t)
    assert doc["complete"] and doc["covers"]


def test_the_10s_closeup_is_the_trade_plus_or_minus_thirty_minutes(monkeypatch, master):
    _write_master(master, "2026-09-29 18:00", "2026-09-30 16:59")
    e0 = _epoch("2026-09-30 09:00")
    ticks = pd.DataFrame([{"time": e0 + 10 + i * 10, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                           "volume": 1} for i in range((4 * 3600) // 10)])     # 09:00 - 13:00, bar-END stamps
    monkeypatch.setattr(tb, "_read_10s", lambda inst, cache: ticks)
    doc = _build("2026-09-30 17:30")
    b10 = doc["b10s"]
    assert b10["t0"] == _epoch("2026-09-30 09:30")                           # entry 10:00 - 30 min
    n = b10["s"].count(";") + 1
    assert n == (65 * 60) // 10 + 1                                           # 09:30 .. 10:35 inclusive
    assert len(json.dumps(doc)) < tb.DOC_CAP_BYTES


def test_a_one_hour_hold_keeps_every_10s_bar(monkeypatch, master):
    _write_master(master, "2026-09-29 18:00", "2026-09-30 16:59")
    e0 = _epoch("2026-09-30 09:00")
    ticks = pd.DataFrame([{"time": e0 + 10 + i * 10, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                           "volume": 1} for i in range((4 * 3600) // 10)])
    monkeypatch.setattr(tb, "_read_10s", lambda inst, cache: ticks)
    doc = _build("2026-09-30 17:30", dict(_trade_for_build(), exitTime="11:00"))
    assert doc["b10s"]["s"].count(";") + 1 == (2 * 3600) // 10 + 1         # 1 h hold + 2 x 30 min, no head/tail cut
    assert tb.MAX_10S >= 2 * 3600 // 10 + 1
