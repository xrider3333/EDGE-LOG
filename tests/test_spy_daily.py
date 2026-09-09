"""Contract tests for the SPY daily-close benchmark pipeline (api/spy_daily.py).

No live Alpaca call is possible in this checkout (no key is configured on this
machine, by design -- see the module docstring), so every test replaces
api.spy_daily.fetch_bars with a fixture DataFrame shaped exactly like the real one
(time = POSIX seconds UTC, close = float) and drives the merge/publish logic against
a tiny in-memory fake of the Firestore client. What's actually pinned:

  1. The whole 2015-present series serializes to well under Firestore's 1 MiB/doc cap.
  2. An incremental run appends ONLY the new date(s) -- no duplicates, no rewrite of
     unrelated history.
  3. Re-running the exact same fetch (Alpaca resending an overlapping window, or the
     runner's guard firing twice) is idempotent: the second run adds/changes nothing.
  4. No code path in this module ever prints, logs, or otherwise surfaces the Alpaca
     key/secret.
"""
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.spy_daily as SD


# ── fixture data ─────────────────────────────────────────────────────────────────────
def _fixture_df(dates):
    """Build a DataFrame shaped like tools.import_alpaca_stocks.fetch_bars()'s output
    for a list of python date objects. Each timestamp is midnight America/New_York on
    that date (converted to its UTC epoch), so build_merged_doc's ET-date recovery
    round-trips to exactly the date given, regardless of DST."""
    if not dates:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    rows = []
    for d in dates:
        ts = pd.Timestamp(d, tz="America/New_York").tz_convert("UTC")
        # Deterministic function of the CALENDAR DATE (not the row's position in this
        # particular slice) so the same date always fixtures to the same close, no
        # matter which sub-range of dates a given call is asked to build -- otherwise
        # an "overlap" test would fabricate a fake price disagreement that has nothing
        # to do with the module under test.
        px = 400.0 + (d.toordinal() % 37) - (d.toordinal() % 5) * 0.5
        rows.append({"time": int(ts.timestamp()), "open": px - 1, "high": px + 1,
                     "low": px - 2, "close": round(px, 2), "volume": 50_000_000})
    return pd.DataFrame(rows)


def _bdates(start, end):
    return list(pd.bdate_range(start, end).date)


FULL_RANGE = _bdates(SD.BACKFILL_START, "2026-09-09")   # ~2,900 trading-day-shaped rows


# ── fake Firestore ───────────────────────────────────────────────────────────────────
class _FakeSnap:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class _FakeRef:
    """One object plays both 'collection' and 'document' role, keyed by the full path
    tuple -- enough to satisfy db.collection(x).document(y).collection(z).document(w)
    chains without modelling real Firestore semantics."""
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def collection(self, name):
        return _FakeRef(self._store, self._path + (name,))

    def document(self, name):
        return _FakeRef(self._store, self._path + (name,))

    def get(self):
        return _FakeSnap(self._store.get(self._path))

    def set(self, data):
        self._store[self._path] = data


class _FakeDB:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _FakeRef(self.store, (name,))


# ── 1. document size ─────────────────────────────────────────────────────────────────
def test_full_backfill_serializes_well_under_1mib():
    doc, added, changed = SD.build_merged_doc({}, _fixture_df(FULL_RANGE))
    assert added == len(FULL_RANGE)
    assert changed == 0
    assert doc["from"] == FULL_RANGE[0].isoformat()
    assert doc["to"] == FULL_RANGE[-1].isoformat()
    size = len(json.dumps(doc).encode("utf-8"))
    print(f"\n[size] {len(doc['bars'])} bars -> {size:,} bytes serialized")
    # 1 MiB cap; assert comfortably under it (10x headroom) rather than just barely.
    assert size < 200_000, f"doc unexpectedly large: {size:,} bytes"


# ── 2. incremental append is additive, never duplicates, never touches old rows ──────
def test_incremental_run_appends_only_the_new_date():
    base_dates = FULL_RANGE[:-1]          # everything except the last trading day
    doc1, _, _ = SD.build_merged_doc({}, _fixture_df(base_dates))
    existing = {d: c for d, c in doc1["bars"]}

    new_day = [FULL_RANGE[-1]]
    doc2, added, changed = SD.build_merged_doc(existing, _fixture_df(new_day))

    assert added == 1
    assert changed == 0
    assert len(doc2["bars"]) == len(doc1["bars"]) + 1
    # every old row is byte-for-byte untouched
    old_map = dict(doc1["bars"])
    new_map = dict(doc2["bars"])
    for d, c in old_map.items():
        assert new_map[d] == c
    # no duplicate dates
    all_dates = [row[0] for row in doc2["bars"]]
    assert len(all_dates) == len(set(all_dates))


def test_rerun_with_same_new_bars_is_idempotent():
    doc1, _, _ = SD.build_merged_doc({}, _fixture_df(FULL_RANGE[:-1]))
    existing = {d: c for d, c in doc1["bars"]}
    new_day_df = _fixture_df([FULL_RANGE[-1]])

    doc2, added1, changed1 = SD.build_merged_doc(existing, new_day_df)
    existing2 = {d: c for d, c in doc2["bars"]}
    doc3, added2, changed2 = SD.build_merged_doc(existing2, new_day_df)

    assert added1 == 1 and changed1 == 0
    assert added2 == 0 and changed2 == 0            # re-running adds/changes nothing
    assert doc2["bars"] == doc3["bars"]


def test_overlapping_fetch_window_does_not_duplicate():
    """fetch_and_merge always re-asks for the last stored date onward (in case Alpaca
    restates it), so the merge must treat that overlap as a no-op, not a duplicate."""
    doc1, _, _ = SD.build_merged_doc({}, _fixture_df(FULL_RANGE[:-3]))
    existing = {d: c for d, c in doc1["bars"]}
    overlap_plus_new = _fixture_df(FULL_RANGE[-4:])   # re-sends 1 old date + 3 new ones

    doc2, added, changed = SD.build_merged_doc(existing, overlap_plus_new)
    assert added == 3
    assert changed == 0                                # same close on the overlap day
    dates = [row[0] for row in doc2["bars"]]
    assert len(dates) == len(set(dates))
    assert len(doc2["bars"]) == len(doc1["bars"]) + 3


# ── 3. full round-trip through the fake Firestore doc ────────────────────────────────
def test_fetch_and_merge_round_trips_through_the_store(monkeypatch):
    db = _FakeDB()
    uid = "test-uid-1"
    calls = []

    def _fake_fetch_bars(sym, tf, start, end, key, secret, feed="sip", adjustment="split"):
        calls.append(start)
        # first call: no existing doc -> full backfill; second call: incremental
        if len(calls) == 1:
            return _fixture_df(FULL_RANGE[:-1])
        return _fixture_df([FULL_RANGE[-1]])

    monkeypatch.setattr(SD, "fetch_bars", _fake_fetch_bars)

    r1 = SD.fetch_and_merge(db, uid, "K", "S")
    assert r1["ok"] is True
    assert r1["n_bars"] == len(FULL_RANGE) - 1

    r2 = SD.fetch_and_merge(db, uid, "K", "S")
    assert r2["ok"] is True
    assert r2["added"] == 1
    assert r2["n_bars"] == len(FULL_RANGE)

    stored = db.store[("users", uid, "meta", "spy_daily")]
    dates = [row[0] for row in stored["bars"]]
    assert len(dates) == len(set(dates))
    assert stored["adjustment"] == "split"

    # re-running the identical incremental fetch again must not grow the doc further
    r3 = SD.fetch_and_merge(db, uid, "K", "S")
    assert r3["added"] == 0 and r3["changed"] == 0
    assert r3["n_bars"] == len(FULL_RANGE)


# ── 4. missing-key path: clean, one-time log, no crash, no retry storm ────────────────
def test_maybe_run_missing_keys_logs_once_and_noops(monkeypatch, capsys):
    monkeypatch.setattr(SD, "_warned_missing_keys", False)
    monkeypatch.setattr(SD, "_last_run_date", None)
    monkeypatch.setattr(SD, "load_keys", lambda: (None, None))

    def _boom(*a, **k):
        raise AssertionError("fetch_and_merge must never be called with no keys")
    monkeypatch.setattr(SD, "fetch_and_merge", _boom)

    class _Q:
        db = None
        allow = ["u1"]

    r1 = SD.maybe_run(_Q(), force=True)
    r2 = SD.maybe_run(_Q(), force=True)
    assert r1 is None and r2 is None

    out = capsys.readouterr().out
    assert out.count("no Alpaca key configured") == 1


# ── 5. the key/secret never appear in anything this module prints ───────────────────
def test_key_and_secret_never_logged(monkeypatch, capsys):
    db = _FakeDB()
    secret_key, secret_val = "AKFAKE_TEST_KEY_998", "SECRETFAKE_TEST_VAL_776"

    def _fake_fetch_bars(sym, tf, start, end, key, secret, feed="sip", adjustment="split"):
        assert key == secret_key and secret == secret_val
        return _fixture_df(FULL_RANGE[-5:])

    monkeypatch.setattr(SD, "fetch_bars", _fake_fetch_bars)
    SD.fetch_and_merge(db, "uid-x", secret_key, secret_val)

    out = capsys.readouterr().out
    assert secret_key not in out
    assert secret_val not in out
