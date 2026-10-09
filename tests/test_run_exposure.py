"""The RUN EXPOSURE TABLE (MANAGER #41 phase 2, DISC's recipe #42): augur_engine/exposure.py and tools/run_exposure.py.

The maths is pure (blotter rows + a series of session closes in, plain numbers out), so most of this file is hand
examples on a few synthetic sessions. The CLI half runs against an in-memory fake Firestore client, a temp blotter CSV
and a fake closes provider: nothing here reads the master registry, the real blotters, firebase_admin or any credential
(conftest.py's live-system guard would fail a test that tried).
"""
import copy
import csv
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine import exposure as X  # noqa: E402
import tools.run_exposure as rx  # noqa: E402
import tools.runboard_watch as rw  # noqa: E402

DAYS = pd.bdate_range("2024-07-08", periods=5)           # Mon 8 Jul .. Fri 12 Jul 2024 (no holiday)
D = [d.strftime("%Y-%m-%d") for d in DAYS]


def closes(vals, days=DAYS):
    return pd.Series([float(v) for v in vals], index=days)


def row(entry, exit_, pnl=1.0):
    return {"entry_time": entry, "exit_time": exit_, "pnl_pts": pnl}


def at(day, hhmm="10:00"):
    return "%s %s" % (day, hhmm)


# ── lots held at the close ───────────────────────────────────────────────────────────────────
def test_three_session_swing_trade_counts_on_two_sessions():
    # entered on session 1, exited on session 3: held at the close of sessions 1 and 2 only
    r = [row(at(D[0]), at(D[2], "15:55"), 5.0)]
    e = X.exposure(r, closes([100, 101, 102, 103, 104]))
    assert e["in_mkt_pct"] == pytest.approx(40.0)          # 2 of 5 sessions
    assert e["lots_mean_all"] == pytest.approx(0.4)
    assert e["lots_mean_in"] == pytest.approx(1.0)
    assert e["lots_max"] == 1
    assert e["hold_med_sessions"] == 2.0


def test_same_day_trade_counts_on_none_and_is_never_flagged():
    r = [row(at(D[1], "09:35"), at(D[1], "15:55"), 7.0)]
    e = X.exposure(r, closes([100, 101, 102, 103, 104]))
    assert e["in_mkt_pct"] == 0.0 and e["lots_mean_all"] == 0.0 and e["lots_mean_in"] == 0.0
    assert e["lots_max"] == 0
    assert e["hold_med_sessions"] == 0.0
    assert e["n_trades"] == 1 and e["strat_pts"] == 7.0     # the trade still counts as a trade
    assert e["twin_pts"] == 0.0
    assert e["ratio"] is None and "flat at every session close" in e["ratio_why"]


def test_two_overlapping_lots_hand_example():
    # lot A: sessions 1,2,3 held (exit session 4); lot B: session 2 held (exit session 3)
    r = [row(at(D[0]), at(D[3]), 10.0), row(at(D[1]), at(D[2]), 4.0)]
    e = X.exposure(r, closes([100, 102, 101, 105, 110]))
    # lots at the five closes: [1, 2, 1, 0, 0]
    assert e["in_mkt_pct"] == pytest.approx(60.0)
    assert e["lots_mean_all"] == pytest.approx(0.8)         # 4 lot-sessions / 5 sessions (zeros included)
    assert e["lots_mean_in"] == pytest.approx(4 / 3, abs=1e-4)   # 4 lot-sessions / 3 sessions in the market
    assert e["lots_max"] == 2
    assert e["n_trades"] == 2 and e["strat_pts"] == 14.0
    assert e["sessions"] == 5 and e["first"] == D[0] and e["last"] == D[4]


def test_twin_is_mean_lots_times_the_price_change_and_carries_no_cost():
    r = [row(at(D[0]), at(D[3]), 10.0), row(at(D[1]), at(D[2]), 4.0)]
    c = closes([100, 102, 101, 105, 110])
    e = X.exposure(r, c)
    assert e["twin_pts"] == pytest.approx(0.8 * (110 - 100))             # 8.0
    assert e["ratio"] == pytest.approx(14.0 / 8.0)
    # the engine's cost is already inside pnl_pts; the twin must not move when the trades' pnl does
    costly = [row(at(D[0]), at(D[3]), 10.0 - 0.533), row(at(D[1]), at(D[2]), 4.0 - 0.533)]
    e2 = X.exposure(costly, c)
    assert e2["twin_pts"] == e["twin_pts"]
    assert e2["strat_pts"] == pytest.approx(14.0 - 2 * 0.533, abs=0.01)


def test_ratio_is_null_with_a_reason_when_the_twin_is_not_positive():
    r = [row(at(D[0]), at(D[3]), 9.0)]
    falling = X.exposure(r, closes([110, 108, 107, 105, 100]))
    assert falling["twin_pts"] < 0
    assert falling["ratio"] is None and "twin lost points" in falling["ratio_why"]
    unchanged = X.exposure(r, closes([100, 103, 99, 104, 100]))
    assert unchanged["twin_pts"] == 0.0
    assert unchanged["ratio"] is None and "about nothing" in unchanged["ratio_why"]
    rising = X.exposure(r, closes([100, 101, 102, 103, 106]))
    assert rising["ratio"] is not None and "ratio_why" not in rising


def test_one_session_has_no_price_change_to_earn():
    e = X.exposure([row(at(D[0]), at(D[0]), 1.0)], closes([100], DAYS[:1]))
    assert e["sessions"] == 1 and e["ratio"] is None and "fewer than 2 sessions" in e["ratio_why"]


def test_median_hold_in_sessions():
    days = pd.bdate_range("2024-07-01", periods=12)
    d = [x.strftime("%Y-%m-%d") for x in days]
    c = closes(range(100, 112), days)
    odd = [row(at(d[0]), at(d[1])), row(at(d[0]), at(d[3])), row(at(d[0]), at(d[10]))]    # holds 1, 3, 10
    assert X.exposure(odd, c)["hold_med_sessions"] == 3.0
    even = [row(at(d[0]), at(d[2])), row(at(d[0]), at(d[5]))]                             # holds 2, 5
    assert X.exposure(even, c)["hold_med_sessions"] == 3.5


def test_no_trades_is_a_valid_empty_table():
    e = X.exposure([], closes([100, 101, 102, 103, 104]))
    assert e["n_trades"] == 0 and e["in_mkt_pct"] == 0.0 and e["hold_med_sessions"] is None
    assert e["strat_pts"] == 0.0 and e["ratio"] is None


def test_no_closes_raises():
    with pytest.raises(ValueError):
        X.exposure([row(at(D[0]), at(D[1]))], pd.Series(dtype=float))


def test_result_is_json_safe():
    r = [row(at(D[0]), at(D[3]), 10.0)]
    e = X.exposure(r, closes([100, 102, 101, 105, 110]))
    assert json.loads(json.dumps(e, allow_nan=False)) == e
    for v in e.values():
        assert not (hasattr(v, "dtype"))               # plain Python numbers, no numpy scalars


def test_trades_outside_the_sessions_are_counted_apart_and_unreadable_rows_skipped():
    r = [row(at(D[0]), at(D[2]), 5.0),
         row("2024-06-03 10:00", "2024-06-04 10:00", 100.0),    # entered before the first session
         row("garbage", "2024-07-10", 1.0),
         {"entry_time": at(D[0]), "exit_time": at(D[1]), "pnl_pts": ""}]
    e = X.exposure(r, closes([100, 101, 102, 103, 104]))
    assert e["n_trades"] == 1 and e["strat_pts"] == 5.0
    assert e["n_outside"] == 1 and e["n_skipped"] == 2


def test_closes_may_be_a_dict_and_the_last_stamp_of_a_date_wins():
    stamps = pd.DatetimeIndex(["2024-07-08 09:30", "2024-07-08 15:55", "2024-07-09 09:30", "2024-07-09 15:55"],
                              tz="America/New_York")
    s = pd.Series([1.0, 100.0, 2.0, 110.0], index=stamps)
    e = X.exposure([row(at(D[0]), at(D[1]), 3.0)], s)
    assert e["twin_pts"] == pytest.approx(0.5 * (110.0 - 100.0))      # the LAST bar of each day (100 -> 110); a lot on 1 of 2
    d = {"2024-07-08": 100.0, "2024-07-09": 110.0}
    assert X.exposure([row(at(D[0]), at(D[1]), 3.0)], d)["twin_pts"] == pytest.approx(5.0)


# ── time zones ───────────────────────────────────────────────────────────────────────────────
def test_utc_stamp_after_20h_is_still_the_same_new_york_session():
    # 2024-07-09T00:30Z is 20:30 EDT on Mon 8 Jul: the Jul 8 session, not Jul 9
    assert str(X.session_dates(["2024-07-09T00:30:00Z"])[0]) == "2024-07-08"
    # winter: 2024-01-09T00:30Z is 19:30 EST on Mon 8 Jan
    assert str(X.session_dates(["2024-01-09T00:30:00Z"])[0]) == "2024-01-08"
    # entered 13:35Z (09:35 EDT Jul 8) and exited 00:30Z the next UTC day (20:30 EDT Jul 8): the SAME session
    same_day = [row("2024-07-08T13:35:00Z", "2024-07-09T00:30:00Z", 3.0)]
    e = X.exposure(same_day, closes([100, 101, 102, 103, 104]))
    assert e["in_mkt_pct"] == 0.0 and e["lots_max"] == 0            # read as UTC dates it would count on Jul 8
    # a real swing: in 13:35Z Mon Jul 8, out 01:30Z Wed Jul 10 (= 21:30 EDT Tue Jul 9): held at Monday's close only
    swing = [row("2024-07-08T13:35:00Z", "2024-07-10T01:30:00Z", 3.0)]
    e = X.exposure(swing, closes([100, 101, 102, 103, 104]))
    assert e["in_mkt_pct"] == pytest.approx(20.0) and e["hold_med_sessions"] == 1.0


def test_offset_and_bare_and_aware_stamps_agree():
    a = X.session_dates(["2024-07-08 09:35",                  # bare = New York already, not shifted
                         "2024-07-08 09:35:00-04:00",         # offset (the RSIDIV audit CSV's shape)
                         "2024-07-08T13:35:00+00:00",
                         "2024-07-08 21:00:00-04:00",         # 21:00 New York is still Jul 8
                         pd.Timestamp("2024-07-08 13:35", tz="UTC"),
                         pd.Timestamp("2024-07-08 09:35"),
                         "2024-07-08"])                       # a bare DATE is not a -08 offset
    assert [str(x) for x in a] == ["2024-07-08"] * 7
    # bare late-evening stamps are NOT converted (api/blotter.py writes New York wall-clock time)
    assert str(X.session_dates(["2024-07-08 23:30"])[0]) == "2024-07-08"


def test_unreadable_stamps_are_NaT_not_a_crash():
    out = X.session_dates([None, "", "nope", float("nan"), "2024-07-08 10:00"])
    assert [bool(x) for x in pd.isna(out)] == [True, True, True, True, False]


def test_eth_trade_dates_roll_at_18_00():
    # an overnight-only trade (18:30 Mon -> 09:45 Tue) is one trading day's session: holds no RTH close
    r = [row("2024-07-08 18:30", "2024-07-09 09:45", 2.0)]
    c = closes([100, 101, 102, 103, 104])
    assert X.exposure(r, c)["in_mkt_pct"] == pytest.approx(20.0)                 # plain dates: counted on Mon
    e = X.exposure(r, c, roll_hour=18)
    assert e["in_mkt_pct"] == 0.0 and e["hold_med_sessions"] == 0.0
    # a trade entered Mon 10:00 and exited Tue 09:45 still holds Monday's close
    assert X.exposure([row("2024-07-08 10:00", "2024-07-09 09:45")], c, roll_hour=18)["in_mkt_pct"] == pytest.approx(20.0)


# ── the dashed line ──────────────────────────────────────────────────────────────────────────
def _long_series(n=400):
    days = pd.bdate_range("2020-01-01", periods=n)
    px = pd.Series([100.0 + 0.5 * i + (3 if i % 7 == 0 else 0) for i in range(n)], index=days)
    rows = []
    for k in range(0, n - 30, 25):
        rows.append(row(days[k].strftime("%Y-%m-%d 10:00"), days[k + 20].strftime("%Y-%m-%d 15:55"), 8.5 + k % 3))
    return rows, px


def test_twin_curve_is_downsampled_and_ends_on_the_table_numbers():
    rows, px = _long_series(400)
    e = X.exposure(rows, px)
    cur = X.twin_curve(rows, px, n=120)
    assert 2 <= len(cur) <= 120
    assert cur[0][0] == e["first"] and cur[-1][0] == e["last"]          # first and last session always in
    assert cur[0][1] == 0.0
    assert cur[-1][1] == e["twin_pts"]                                  # the last twin value IS twin_pts
    assert cur[-1][2] == pytest.approx(e["strat_pts"], abs=0.011)
    assert [c[0] for c in cur] == sorted(c[0] for c in cur)
    assert json.loads(json.dumps(cur, allow_nan=False)) == cur


def test_twin_curve_keeps_every_session_when_there_are_fewer_than_n():
    r = [row(at(D[0]), at(D[3]), 10.0), row(at(D[1]), at(D[2]), 4.0)]
    cur = X.twin_curve(r, closes([100, 102, 101, 105, 110]), n=120)
    assert [c[0] for c in cur] == D
    assert [c[1] for c in cur] == pytest.approx([0.8 * (p - 100) for p in (100, 102, 101, 105, 110)])
    # strategy: lot B (4.0) exits on session 3, lot A (10.0) on session 4
    assert [c[2] for c in cur] == [0.0, 0.0, 4.0, 14.0, 14.0]


# ── the CLI against a fake Firestore ─────────────────────────────────────────────────────────
class _Snap:
    def __init__(self, sid, data):
        self.id, self._d = sid, data

    @property
    def exists(self):
        return self._d is not None

    def to_dict(self):
        return copy.deepcopy(self._d) if self._d is not None else None


class _Doc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, name):
        return _Coll(self.db, self.path + (name,))

    def get(self, field_paths=None, transaction=None):
        self.db.read_log.append(self.path)
        data = self.db.store.get(self.path)
        if data is not None and field_paths:
            keep = {p.split(".")[0] for p in field_paths}
            data = {k: v for k, v in data.items() if k in keep}
        return _Snap(self.path[-1], data)

    def set(self, data, merge=False):
        self.db.write_log.append(self.path)
        self.db.store[self.path] = copy.deepcopy(data)


class _Coll:
    def __init__(self, db, path, fields=None):
        self.db, self.path, self.fields = db, path, fields

    def document(self, doc_id):
        return _Doc(self.db, self.path + (str(doc_id),))

    def select(self, fields):
        return _Coll(self.db, self.path, list(fields))

    def stream(self):
        for p, data in sorted(self.db.store.items()):
            if len(p) == len(self.path) + 1 and p[:len(self.path)] == self.path:
                self.db.read_log.append(p)
                keep = {f.split(".")[0] for f in self.fields} if self.fields else None
                yield _Snap(p[-1], {k: v for k, v in data.items() if keep is None or k in keep})


class FakeDb:
    """In-memory Firestore stand-in. No .transaction(), so runboard_watch._apply falls back to get-then-set."""
    def __init__(self):
        self.store, self.read_log, self.write_log = {}, [], []

    def collection(self, name):
        return _Coll(self, (name,))

    def seed_run(self, rid, **kw):
        d = {"id": rid, "strategy": "RSIDIV_1_0.py", "instrument": "NQ", "timeframe": "5m", "session": "rth",
             "best_params": {"a": 1}, "cost_pts": 0.533, "multiplier": 20, "date_from": D[0], "date_to": D[4],
             "data_source": "db_adj_rth", "famKey": "RSIDIV", "huge_unprojected_field": "x" * 1000}
        d.update(kw)
        self.store[("users", rw.UID, "runs", str(rid))] = d

    def meta(self):
        return self.store.get(("users", rw.UID, "meta", rx.DOC_ID))


BLOTTER_FIELDS = ["trade_no", "entry_time", "exit_time", "hold_bars", "entry_px", "exit_px", "pnl_pts", "pnl_usd",
                  "cum_usd", "side"]


def write_blotter(root, rid, trades, inst="NQ", tf="5m"):
    os.makedirs(os.path.join(root, "blotters"), exist_ok=True)
    with open(os.path.join(root, "blotters", "run%s_%s_%s.csv" % (rid, inst, tf)), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BLOTTER_FIELDS)
        w.writeheader()
        for i, (en, ex, pnl) in enumerate(trades, 1):
            w.writerow({"trade_no": i, "entry_time": en, "exit_time": ex, "hold_bars": 1, "entry_px": 1, "exit_px": 1,
                        "pnl_pts": pnl, "pnl_usd": pnl * 20, "cum_usd": 0, "side": "long"})


def fake_closes(vals=(100, 102, 101, 105, 110), master="ADJ_FAKE [db_adj_rth]", rolls=True, calls=None):
    def provider(inst, tf, a, b, src=None):
        if calls is not None:
            calls.append((inst, tf, a, b, src))
        return {"closes": closes(vals), "master": master, "adjusted": True, "rolls": rolls}
    return provider


def parse(*argv):
    return rx.build_parser().parse_args(list(argv))


def go(argv, db, root, provider=None, regen=None):
    lines = []
    code, doc, reads = rx.run(parse(*argv), db, provider or fake_closes(), regen, root=str(root), out=lines.append)
    return code, doc, reads, "\n".join(lines)


def test_dry_run_prints_the_row_reads_two_docs_and_writes_nothing(tmp_path):
    db = FakeDb()
    db.seed_run(7)
    write_blotter(tmp_path, 7, [(at(D[0]), at(D[3]), 10.0), (at(D[1]), at(D[2]), 4.0)])
    code, doc, reads, text = go(["--ids", "7", "--dry"], db, tmp_path)
    assert code == 0 and db.write_log == []                 # --dry writes nothing
    assert db.meta() is None
    assert [r for r in text.splitlines() if r.startswith("7 ")]            # the table row for run 7
    assert "60.0" in text and "ADJ_FAKE [db_adj_rth]" in text and "--dry: wrote nothing" in text
    assert "bytes by Firestore's size rules" in text and "index entries" in text
    assert (reads.runs, reads.meta, reads.total) == (1, 1, 2)
    assert len(db.read_log) == 2                                            # the fake saw exactly those two reads
    assert doc["runs"]["7"]["in_mkt_pct"] == pytest.approx(60.0)            # what WOULD be written, returned for the caller


def test_write_stores_the_entry_and_merges_with_what_is_already_there(tmp_path):
    db = FakeDb()
    db.seed_run(7)
    write_blotter(tmp_path, 7, [(at(D[0]), at(D[3]), 10.0), (at(D[1]), at(D[2]), 4.0)])
    old = {"v": 1, "updated_at": "x", "updated_by": "OLD", "runs": {"99": {"why": "no saved trade list"},
                                                                    "7": {"stale": True, "curve": "stale"}}}
    db.store[("users", rw.UID, "meta", rx.DOC_ID)] = old
    code, doc, reads, text = go(["--ids", "7", "--write", "--from", "MANAGER"], db, tmp_path)
    assert code == 0
    got = db.meta()
    assert got == doc and got["v"] == 1 and got["updated_by"] == "MANAGER" and got["updated_at"]
    assert got["runs"]["99"] == {"why": "no saved trade list"}              # a run not in this pass is kept
    e = got["runs"]["7"]
    assert "stale" not in e and "curve" in e                                # a re-measured run is replaced whole
    for k in ("in_mkt_pct", "lots_mean_all", "lots_mean_in", "lots_max", "hold_med_sessions", "n_trades", "strat_pts",
              "twin_pts", "ratio", "sessions", "first", "last", "window", "master", "inst", "tf", "mult"):
        assert k in e, k
    assert e["window"] == [D[0], D[4]] and e["inst"] == "NQ" and e["tf"] == "5m" and e["mult"] == 20.0
    assert e["master"] == "ADJ_FAKE [db_adj_rth]"
    assert "wrote 1 entr(ies) by MANAGER" in text
    assert db.write_log == [("users", rw.UID, "meta", rx.DOC_ID)]           # one doc, nothing else touched


def test_curve_is_a_json_string_stored_only_when_in_the_market_over_half_the_time(tmp_path):
    db = FakeDb()
    db.seed_run(1)
    db.seed_run(2)
    write_blotter(tmp_path, 1, [(at(D[0]), at(D[4]), 10.0)])                       # in 4 of 5 sessions = 80%
    write_blotter(tmp_path, 2, [(at(D[0]), at(D[2]), 10.0)])                       # in 2 of 5 = 40%
    _, doc, _, _ = go(["--ids", "1", "2", "--dry"], db, tmp_path)
    assert doc["runs"]["1"]["in_mkt_pct"] == pytest.approx(80.0)
    cur = json.loads(doc["runs"]["1"]["curve"])                                    # a TEXT string: no nested arrays
    assert isinstance(doc["runs"]["1"]["curve"], str)
    assert cur[0][0] == D[0] and cur[-1][0] == D[4] and cur[-1][1] == doc["runs"]["1"]["twin_pts"]
    assert "curve" not in doc["runs"]["2"]
    assert not rx._has_nested_array(doc)


def test_intraday_run_reads_zero_and_has_no_curve(tmp_path):
    db = FakeDb()
    db.seed_run(3)
    write_blotter(tmp_path, 3, [(at(D[0], "09:35"), at(D[0], "15:50"), 2.0), (at(D[1], "09:35"), at(D[1], "11:00"), -1.0)])
    _, doc, _, _ = go(["--ids", "3", "--dry"], db, tmp_path)
    e = doc["runs"]["3"]
    assert e["in_mkt_pct"] == 0.0 and e["ratio"] is None and "curve" not in e


def test_missing_blotter_is_a_plain_why_unless_regen_rebuilds_it(tmp_path):
    db = FakeDb()
    db.seed_run(5)
    _, doc, _, text = go(["--ids", "5", "--dry"], db, tmp_path)
    assert doc["runs"]["5"] == {"why": "no saved trade list"}
    assert "no saved trade list" in text
    called = []

    def regen(rid, d):
        called.append((rid, d["strategy"]))
        return [row(at(D[0]), at(D[2]), 6.0)], None

    # --regen WITHOUT a regen function wired (as in a test) still asks it only for a missing list
    _, doc, _, _ = go(["--ids", "5", "--regen", "--dry"], db, tmp_path, regen=regen)
    assert called == [(5, "RSIDIV_1_0.py")] and doc["runs"]["5"]["in_mkt_pct"] == pytest.approx(40.0)
    # without --regen the function is never called, even when one is wired
    called.clear()
    go(["--ids", "5", "--dry"], db, tmp_path, regen=regen)
    assert called == []
    # a failed rebuild says why
    _, doc, _, _ = go(["--ids", "5", "--regen", "--dry"], db, tmp_path, regen=lambda rid, d: (None, "no champion config"))
    assert doc["runs"]["5"]["why"] == "no saved trade list (rebuild failed: no champion config)"
    # a cached list is never rebuilt, --regen or not
    write_blotter(tmp_path, 5, [(at(D[0]), at(D[2]), 6.0)])
    called.clear()
    go(["--ids", "5", "--regen", "--dry"], db, tmp_path, regen=regen)
    assert called == []


def test_regen_blotter_refuses_a_run_that_recorded_no_cost_or_no_config(tmp_path):
    base = {"strategy": "X.py", "best_params": {"a": 1}, "cost_pts": 0.5}
    assert rx.regen_blotter(str(tmp_path), 1, dict(base, cost_pts=None))[0] is None
    assert "no cost" in rx.regen_blotter(str(tmp_path), 1, dict(base, cost_pts=None))[1]
    assert "configuration" in rx.regen_blotter(str(tmp_path), 1, dict(base, best_params={}))[1]
    assert "no strategy" in rx.regen_blotter(str(tmp_path), 1, dict(base, strategy=""))[1]


def test_books_are_skipped_and_said_so(tmp_path):
    db = FakeDb()
    db.seed_run(10, book={"legs": [{"strategy": "A"}]})
    db.seed_run(11, scope="Book of 3")
    db.seed_run(12, strategy="BOOK: 463")
    db.seed_run(13, strategy="COMBINED 2 runs")
    db.seed_run(14)
    write_blotter(tmp_path, 14, [(at(D[0]), at(D[3]), 1.0)])
    for rid in (10, 11, 12, 13):
        write_blotter(tmp_path, rid, [(at(D[0]), at(D[3]), 1.0)])           # even with a trade list on disk
    _, doc, _, text = go(["--all", "--dry"], db, tmp_path)
    assert sorted(doc["runs"]) == ["14"]
    for rid in (10, 11, 12, 13):
        assert "#%d: a book" % rid in text
    assert not rx.is_book({"strategy": "ORB_3_0.py", "scope": "Single strategy"})


def test_all_reads_one_doc_per_run_and_a_missing_id_is_noted(tmp_path):
    db = FakeDb()
    for rid in (1, 2, 3):
        db.seed_run(rid)
        write_blotter(tmp_path, rid, [(at(D[0]), at(D[3]), 1.0)])
    _, _, reads, _ = go(["--all", "--dry"], db, tmp_path)
    assert (reads.runs, reads.meta) == (3, 1)
    _, _, reads, text = go(["--ids", "2", "404", "--dry"], db, tmp_path)
    assert "#404: no such run" in text and (reads.runs, reads.meta) == (2, 1)


def test_only_the_projected_fields_are_requested():
    assert "code_snapshot" not in rx.FIELDS and "validate" not in rx.FIELDS and "equity" not in rx.FIELDS
    assert len(rx.FIELDS) == 13


def test_a_run_with_no_price_master_gets_a_twin_null_and_a_plain_why(tmp_path):
    db = FakeDb()
    db.seed_run(8, instrument="ZZ")
    write_blotter(tmp_path, 8, [(at(D[0]), at(D[3]), 5.0)], inst="ZZ")
    nomaster = lambda *a, **k: {"why": "no RTH price master for ZZ in the registry, so the buy-and-hold twin cannot be built"}  # noqa: E731
    _, doc, _, text = go(["--ids", "8", "--dry"], db, tmp_path, provider=nomaster)
    e = doc["runs"]["8"]
    assert e["twin_pts"] is None and e["ratio"] is None and "no RTH price master for ZZ" in e["ratio_why"]
    assert e["n_trades"] == 1 and e["strat_pts"] == 5.0
    assert "no RTH price master" in text


def test_the_window_comes_from_the_run_doc_and_the_provider_is_asked_for_it(tmp_path):
    db = FakeDb()
    db.seed_run(9, date_from="2010-06-07", date_to="2025-07-15T00:00:00", data_source="tv")
    write_blotter(tmp_path, 9, [(at(D[0]), at(D[3]), 5.0)])
    calls = []
    go(["--ids", "9", "--dry"], db, tmp_path, provider=fake_closes(calls=calls))
    assert calls == [("NQ", "5m", "2010-06-07", "2025-07-15", "tv")]


def test_eth_futures_run_rolls_the_trade_date_at_18h(tmp_path):
    db = FakeDb()
    db.seed_run(20, session="eth")
    db.seed_run(21, session="rth")
    overnight = [("2024-07-08 18:30", "2024-07-09 09:45", 2.0)]
    write_blotter(tmp_path, 20, overnight)
    write_blotter(tmp_path, 21, overnight)
    _, doc, _, _ = go(["--ids", "20", "21", "--dry"], db, tmp_path)
    assert doc["runs"]["20"]["in_mkt_pct"] == 0.0                   # ETH: one trading day's overnight trade
    assert doc["runs"]["21"]["in_mkt_pct"] == pytest.approx(20.0)   # RTH master semantics: the calendar date


# ── the size lines ───────────────────────────────────────────────────────────────────────────
def test_a_doc_over_900_kb_is_refused_and_nothing_is_written(tmp_path):
    db = FakeDb()
    db.seed_run(7)
    write_blotter(tmp_path, 7, [(at(D[0]), at(D[3]), 10.0)])
    db.store[("users", rw.UID, "meta", rx.DOC_ID)] = {"v": 1, "runs": {"1": {"why": "x" * 950_000}}}
    before = copy.deepcopy(db.meta())
    with pytest.raises(rx.ToolError, match="900,000"):
        go(["--ids", "7", "--write", "--from", "MANAGER"], db, tmp_path)
    assert db.meta() == before and db.write_log == []
    with pytest.raises(rx.ToolError):
        go(["--ids", "7", "--dry"], db, tmp_path)               # --dry refuses too: it prints what would be written


def test_check_doc_lines():
    ok = {"v": 1, "runs": {str(i): {"why": "no saved trade list"} for i in range(50)}}
    info = rx.check_doc(ok)
    assert info["bytes"] < rx.SIZE_WARN and not info["warn"]
    assert rx.doc_bytes({"a": 12.5}) == len("a") + 1 + 8 + 232      # a number is 8 bytes, not the 4 json prints
    big = {"runs": {"1": {"why": "x" * (rx.SIZE_WARN + 10)}}}
    assert rx.check_doc(big)["warn"] is True                       # past the soft line: allowed, flagged
    with pytest.raises(rx.ToolError, match="array inside an array"):
        rx.check_doc({"runs": {"1": {"curve": [["2024-01-01", 1.0, 2.0]]}}})
    many = {"runs": {str(i): {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8, "i": 9, "j": 10,
                              "k": 11, "l": 12, "m": 13, "n": 14, "o": 15, "p": 16, "q": 17, "r": 18, "s": 19}
                      for i in range(1000)}}
    assert rx.index_entries(many) > rx.INDEX_REFUSE
    with pytest.raises(rx.ToolError, match="index entries"):
        rx.check_doc(many)


def test_a_realistic_full_pass_stays_far_under_the_lines():
    entry = {"in_mkt_pct": 96.03, "lots_mean_all": 3.6474, "lots_mean_in": 3.7982, "lots_max": 4,
             "hold_med_sessions": 56.0, "n_trades": 247, "strat_pts": 61427.6, "twin_pts": 68617.14, "ratio": 0.8952,
             "sessions": 3880, "first": "2010-06-07", "last": "2025-07-15", "window": ["2010-06-07", "2025-07-15"],
             "master": "NQ 5m RTH - back-adjusted [db_adj_rth]", "inst": "NQ", "tf": "5m", "mult": 20.0}
    cur = X.twin_curve(*_long_series(3880 // 10))
    withcurve = dict(entry, curve=json.dumps(cur, separators=(",", ":")))
    doc = {"v": 1, "updated_at": "2026-10-09T00:00:00+00:00", "updated_by": "MANAGER",
           "runs": {**{str(i): entry for i in range(1, 451)}, **{str(i): withcurve for i in range(451, 491)}}}
    info = rx.check_doc(doc)
    assert info["bytes"] < rx.SIZE_WARN and info["index_entries"] < rx.INDEX_WARN


# ── which master ─────────────────────────────────────────────────────────────────────────────
def _m(name, inst, tf, session, source):
    return {"name": name, "filename": name + ".csv", "instrument": inst, "timeframe": tf, "session": session, "source": source}


REG = [_m("NQ 5m RTH - back-adjusted", "NQ", "5m", "rth", "db_adj_rth"),
       _m("NQ 5m RTH - no-adj", "NQ", "5m", "rth", "db_noadj_rth"),
       _m("NQ 30m RTH - back-adjusted", "NQ", "30m", "rth", "db_adj_rth"),
       _m("NQ 5m ETH - back-adjusted", "NQ", "5m", "eth", "db_adj_eth"),
       _m("QQQ 5m (Alpaca RTH)", "QQQ", "5m", "rth", "alpaca_split_rth"),
       _m("QQQ 5m (NT non-adj RTH)", "QQQ", "5m", "rth", "nt_noadj_rth"),
       _m("QQQ 30m (Alpaca RTH)", "QQQ", "30m", "rth", "alpaca_split_rth"),
       _m("XLK 5m (Alpaca RTH)", "XLK", "5m", "rth", "alpaca_split_rth")]


def test_a_rolling_future_gets_the_back_adjusted_rth_master_at_the_run_timeframe():
    m, why = rx.choose_master(REG, "NQ", "5m", data_source="tv")
    assert why is None and m["source"] == "db_adj_rth" and m["timeframe"] == "5m"
    m, _ = rx.choose_master(REG, "NQ", "30m")
    assert m["timeframe"] == "30m" and m["source"] == "db_adj_rth"
    # no adjusted master at 15m: the nearest adjusted one, never a plain (roll-gapped) master
    m, _ = rx.choose_master(REG, "NQ", "15m")
    assert m["source"] == "db_adj_rth"


def test_an_etf_gets_its_own_master_then_split_adjusted_then_any_plain():
    m, _ = rx.choose_master(REG, "QQQ", "5m", data_source="nt_noadj_rth")
    assert m["name"] == "QQQ 5m (NT non-adj RTH)"                  # the master the run was made on
    m, _ = rx.choose_master(REG, "QQQ", "5m")
    assert m["name"] == "QQQ 5m (Alpaca RTH)"                      # split-adjusted stock bars beat a raw feed
    m, _ = rx.choose_master(REG, "QQQ", "15m")
    assert m["source"] == "alpaca_split_rth"                       # nearest timeframe when the run's is missing
    m, _ = rx.choose_master(REG, "XLK", "1m")
    assert m["name"] == "XLK 5m (Alpaca RTH)"


def test_no_master_at_all_is_a_plain_reason():
    m, why = rx.choose_master(REG, "ZZ", "5m")
    assert m is None and "no RTH price master for ZZ" in why
    m, why = rx.choose_master([_m("ES ETH", "ES", "5m", "eth", "db_adj_eth")], "ES", "5m")   # ETH-only: not usable
    assert m is None


def test_tf_minutes_orders_timeframes():
    assert rx._tf_minutes("5m") < rx._tf_minutes("30m") < rx._tf_minutes("1d") == rx._tf_minutes("1D")
    assert rx._tf_minutes("10s") < rx._tf_minutes("1m")


def test_blotter_paths_use_the_web_blotter_naming(tmp_path):
    p = rx.blotter_paths(str(tmp_path), 163, "NQ", "5m")
    assert p[0] == os.path.join(str(tmp_path), "blotters", "run163_NQ_5m.csv")
    assert p[1].endswith(os.path.join("Trading", "ENGUQ_DB", "blotters", "run163_NQ_5m.csv"))


def test_all_rows_are_read_with_no_web_cap(tmp_path):
    n = 6500
    write_blotter(tmp_path, 42, [(at(D[0]), at(D[1]), 0.5)] * n)
    rows, path = rx.read_blotter_all(str(tmp_path), 42, "NQ", "5m")
    assert len(rows) == n and path.endswith("run42_NQ_5m.csv")
    assert rx.read_blotter_all(str(tmp_path), 43, "NQ", "5m") == (None, None)


def test_cli_demands_a_mode_a_selection_and_a_lane_to_write():
    with pytest.raises(SystemExit):
        rx.build_parser().parse_args(["--ids", "1"])                 # neither --dry nor --write
    with pytest.raises(SystemExit):
        rx.build_parser().parse_args(["--dry"])                      # neither --ids nor --all
    with pytest.raises(SystemExit):
        rx.build_parser().parse_args(["--ids", "1", "--all", "--dry"])
    with pytest.raises(SystemExit):
        rx.build_parser().parse_args(["--ids", "1", "--dry", "--write"])


def test_master_closes_reads_each_master_once_and_slices_the_run_window(monkeypatch):
    import augur_engine.data as data
    stamps = []
    for day in pd.bdate_range("2024-07-08", periods=5):
        for hhmm in ("09:30", "12:00", "15:55"):
            stamps.append(pd.Timestamp("%s %s" % (day.strftime("%Y-%m-%d"), hhmm), tz="America/New_York"))
    closes_ = [float(10 * (i // 3) + (i % 3)) for i in range(len(stamps))]         # last bar of day k = 10k + 2
    loads = []

    def fake_load(master, date_from=None, date_to=None):
        loads.append((master["filename"], date_from, date_to))
        return {"close": closes_, "index": pd.DatetimeIndex(stamps)}

    monkeypatch.setattr(data, "list_masters", lambda: REG)
    monkeypatch.setattr(data, "load_master_arrays", fake_load)
    mc = rx.MasterCloses()
    a = mc("NQ", "5m", "2024-07-09", "2024-07-11", "tv")
    assert [str(d)[:10] for d in a["closes"].index] == ["2024-07-09", "2024-07-10", "2024-07-11"]
    assert list(a["closes"].values) == [12.0, 22.0, 32.0]                         # the LAST bar of each session
    assert a["master"] == "NQ 5m RTH - back-adjusted [db_adj_rth]" and a["adjusted"] and a["rolls"]
    b = mc("NQ", "5m", None, None, None)
    assert len(b["closes"]) == 5 and len(loads) == 1                              # one read for both windows
    assert mc("NQ", "5m", "2030-01-01", "2030-02-01")["why"].endswith("has no sessions in the run's window")
    etf = mc("QQQ", "5m", None, None, "nt_noadj_rth")
    assert etf["master"] == "QQQ 5m (NT non-adj RTH) [nt_noadj_rth]" and not etf["rolls"]
    assert "no RTH price master for ZZ" in mc("ZZ", "5m", None, None)["why"]
