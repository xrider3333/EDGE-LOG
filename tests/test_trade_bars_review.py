"""api/trade_bars.py - review 2026-09-30 items #1 (stale point-score bars), #2 (stale master stub),
#6 (minute-only 10s shift) and #7 (read meter)."""
import sys
import types

import pandas as pd

from api import trade_bars as tb

ET = "America/New_York"


def _bars(t0, n, step, px=100.0):
    rows = [{"time": t0 + i * step, "open": px, "high": px + 1, "low": px - 1, "close": px, "volume": 1}
            for i in range(n)]
    return pd.DataFrame(rows)


def test_minute_only_fill_is_tested_against_the_whole_minute():
    # 10s bars at 100 for the first 50 s of the minute, then a jump to 130 in the last 10 s
    df = _bars(0, 6, 10)
    df.loc[5, ["open", "high", "low", "close"]] = [130, 131, 129, 130]
    assert tb._shift_onto_fill(df, 130.0, 0, 10) != 0.0              # the one bar at HH:MM:00 misses it
    assert tb._shift_onto_fill(df, 130.0, 0, 10, span=60) == 0.0     # somewhere in that minute: fine
    assert tb._shift_onto_fill(df, 200.0, 0, 10, span=60) == 70.0    # a real roll still shifts


class _Doc:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def collection(self, name):
        return _Doc(self.store, self.path + "/" + name)

    def document(self, name):
        return _Doc(self.store, self.path + "/" + name)

    def set(self, data, merge=False):
        cur = self.store.get(self.path, {}) if merge else {}
        self.store[self.path] = dict(cur, **data)


class _Db(_Doc):
    def __init__(self):
        super().__init__({}, "")


def _trade():
    return {"date": "2026-09-30", "entryTime": "11:52", "exitTime": "11:54", "entry": 30872.25,
            "exit": 30872.75, "type": "LONG", "symbol": "MNQ", "size": 1}


NOBAR = "no 1-minute bar for the signal minute"


def test_a_score_waiting_on_bars_is_retried_after_the_chart_completes(monkeypatch):
    t = _trade()
    recs = [{"total": 0, "max": 0, "na_count": 9, "trend": None, "signal_bar": "s",
             "points": [{"k": "a", "hit": None, "na_reason": NOBAR}]},
            {"total": 7, "max": 9, "na_count": 0, "trend": None, "signal_bar": "s",
             "points": [{"k": "a", "hit": True, "na_reason": None}]}]
    calls = []

    def fake_score(tt, fills=None):
        calls.append(1)
        return dict(recs[min(len(calls), 2) - 1], sig=tb.signature(tt))

    fake_mod = types.SimpleNamespace(NA_NOBAR=NOBAR, NA_NO10BAR="x", NA_NO10="y")
    monkeypatch.setattr(tb, "_point_score_module", lambda: fake_mod)
    monkeypatch.setattr(tb, "point_score", fake_score)
    monkeypatch.setattr(tb, "build", lambda *a, **k: (None, "no_bars"))
    db = _Db()
    tid = "nt_1"
    key = "/users/u/trades/" + tid
    state = {tid: {"sig": tb.signature(t), "complete": True, "covers": True}}   # chart already final
    now = pd.Timestamp("2026-09-30 12:00", tz=ET)
    quiet = lambda *_: None

    tb.publish(db, "u", [(tid, t)], log=quiet, state=state, fills=({}, {}), now=now)
    assert db.store[key]["pointScore"]["max"] == 0                  # data not there yet: all NA
    t["pointScore"] = db.store[key]["pointScore"]
    tb.publish(db, "u", [(tid, t)], log=quiet, state=state, fills=({}, {}), now=now + pd.Timedelta(minutes=20))
    assert db.store[key]["pointScore"]["total"] == 7                # retried once the bars arrived

    t["pointScore"] = db.store[key]["pointScore"]                   # a finished score is left alone
    n = len(calls)
    tb.publish(db, "u", [(tid, t)], log=quiet, state=state, fills=({}, {}), now=now + pd.Timedelta(minutes=40))
    assert len(calls) == n

    t["pointScore"] = dict(recs[0], sig=tb.signature(t))            # an old all-NA score stays final
    tb.publish(db, "u", [(tid, t)], log=quiet, state=state, fills=({}, {}), now=now + pd.Timedelta(days=3))
    assert len(calls) == n


def test_point_score_bars_cache_drops_when_a_source_file_changes(tmp_path, monkeypatch):
    (tmp_path / "a.csv").write_text("x")
    mod = types.SimpleNamespace(_BARS_CACHE={"k": 1}, uploads_dir=lambda: str(tmp_path),
                                MASTER_1M={"NQ": "a.csv"}, MASTER_10S={"NQ": "b.csv"})
    monkeypatch.setattr(tb, "_PS_SRC", None)
    tb._ps_fresh_bars(mod)                       # first look in this process: dropped
    mod._BARS_CACHE["k"] = 1
    tb._ps_fresh_bars(mod)
    assert mod._BARS_CACHE == {"k": 1}           # nothing changed: kept
    (tmp_path / "b.csv").write_text("new capture rows")
    tb._ps_fresh_bars(mod)
    assert mod._BARS_CACHE == {}                 # a source file changed: dropped


def _et_epoch(s):
    return int(pd.Timestamp(s, tz=ET).timestamp())


def test_a_stale_master_never_replaces_a_capture_that_covers_the_trade(monkeypatch, tmp_path):
    t = {"date": "2026-09-30", "entryTime": "15:45", "exitTime": "15:50", "entry": 100.0, "exit": 100.0,
         "type": "LONG", "symbol": "MNQ", "size": 1}
    # capture: 10s rows (bar-END stamps) from 14:15 to 16:00, then NinjaTrader closed
    c0, c1 = _et_epoch("2026-09-30 14:15"), _et_epoch("2026-09-30 16:00")
    ticks = _bars(c0 + 10, (c1 - c0) // 10, 10)
    # master: last refreshed at 14:20 - 5 bars that end before the entry
    m = tmp_path / "m.csv"
    with open(m, "w") as f:
        f.write("time,open,high,low,close,volume\n")
        for i in range(5):
            f.write(f"{c0 + i * 60},100,101,99,100,1\n")
    monkeypatch.setattr(tb, "_read_10s", lambda inst, cache: ticks)
    monkeypatch.setattr(tb, "_master_path", lambda inst: (str(m), "NOADJ"))
    for now in ("2026-09-30 15:55", "2026-09-30 16:10", "2026-09-30 21:51"):
        doc, why = tb.build(t, "x", ({}, {}), {}, pd.Timestamp(now, tz=ET))
        assert why is None and doc["covers"], now
        assert doc["b1m"]["src"] == tb.CAPTURE_SRC, now
    # a master refreshed past the capture's end, covering the trade, is taken instead
    with open(m, "a") as f:
        for i in range(5, 200):
            f.write(f"{c0 + i * 60},100,101,99,100,1\n")
    doc, _ = tb.build(t, "x", ({}, {}), {}, pd.Timestamp("2026-09-30 19:00", tz=ET))
    assert doc["b1m"]["src"].startswith("1-minute master") and doc["covers"]


def test_a_published_covering_chart_is_kept_when_no_source_covers_any_more(monkeypatch):
    t = _trade()
    stub = {"covers": False, "complete": False, "b1m": {"s": "0,1,1,1,1,1"}, "b10s": None}
    monkeypatch.setattr(tb, "build", lambda *a, **k: (dict(stub), None))
    db = _Db()
    state = {"nt_1": {"sig": tb.signature(t), "complete": False, "covers": True}}
    t["symbol"] = "AAPL"                                             # no point score in this test
    state["nt_1"]["sig"] = tb.signature(t)
    tb.publish(db, "u", [("nt_1", t)], log=lambda *_: None, state=state, fills=({}, {}),
               now=pd.Timestamp("2026-09-30 16:10", tz=ET))
    assert db.store == {}


def test_sweep_counts_its_reads_into_the_runner_meter(monkeypatch):
    got = []
    monkeypatch.setitem(sys.modules, "__main__", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "api.runner", types.SimpleNamespace(_note_reads=lambda b, n: got.append((b, n))))

    class _S:
        def __init__(self, i):
            self.id = i

        def to_dict(self):
            return {"symbol": "AAPL"}

    class _D:
        def collection(self, _):
            return self

        def document(self, _):
            return self

        def stream(self):
            return [_S("a"), _S("b"), _S("c")]

    monkeypatch.setattr(tb, "publish", lambda *a, **k: 0)
    monkeypatch.setattr(tb, "_full_done", set())
    monkeypatch.setattr(tb, "_sweep_missed", lambda *a, **k: 0)     # this test is about the journal read
    tb.sweep(_D(), "u", log=lambda *_: None, force=True)
    assert got == [("other", 3)]


def test_a_record_from_an_older_spec_version_is_rescored_once(monkeypatch):
    t = _trade()
    calls = []
    fake_mod = types.SimpleNamespace(VERSION="ps1.1", NA_NOBAR=NOBAR, NA_NO10BAR="x", NA_NO10="y")
    monkeypatch.setattr(tb, "_point_score_module", lambda: fake_mod)

    def fake_score(tt, fills=None):
        calls.append(1)
        return {"v": "ps1.1", "total": 1, "max": 6, "na_count": 3, "trend": None, "signal_bar": "s",
                "points": [{"k": "a", "hit": True, "na_reason": None}], "sig": tb.signature(tt)}

    monkeypatch.setattr(tb, "point_score", fake_score)
    monkeypatch.setattr(tb, "build", lambda *a, **k: (None, "no_bars"))
    db = _Db()
    state = {"nt_1": {"sig": tb.signature(t), "complete": True, "covers": True}}
    old = now = pd.Timestamp("2026-10-01 12:00", tz=ET) + pd.Timedelta(days=30)          # long after the trade
    t["pointScore"] = {"v": "ps1", "total": 3, "max": 9, "na_count": 0, "points": [], "trend": None,
                       "signal_bar": "s", "sig": tb.signature(t)}
    tb.publish(db, "u", [("nt_1", t)], log=lambda *_: None, state=state, fills=({}, {}), now=old)
    assert len(calls) == 1 and db.store["/users/u/trades/nt_1"]["pointScore"]["v"] == "ps1.1"
    t["pointScore"] = db.store["/users/u/trades/nt_1"]["pointScore"]
    tb.publish(db, "u", [("nt_1", t)], log=lambda *_: None, state=state, fills=({}, {}), now=now)
    assert len(calls) == 1                                                              # current: left alone


def test_the_scorer_is_reloaded_when_its_file_changes(tmp_path, monkeypatch):
    import os
    f = tmp_path / "point_score.py"
    f.write_text("VERSION = 'ps1'\n")
    monkeypatch.setattr(tb, "PS_PATH", str(f))
    monkeypatch.setattr(tb, "_PS", None)
    monkeypatch.setattr(tb, "_PS_MTIME", None)
    assert tb._point_score_module().VERSION == "ps1"
    assert tb._point_score_module() is tb._point_score_module()                         # unchanged: cached
    f.write_text("VERSION = 'ps1.1'\n")
    st = os.stat(f)
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert tb._point_score_module().VERSION == "ps1.1"
