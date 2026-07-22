"""Golden tests for augur_engine.data's PR3 data-prep memoization
(docs/INCREMENTAL_BACKTEST_REUSE.md §2(b)).

The memo sits behind trial_cache.is_enabled() -- the SAME single switch as the
rest of the caching subsystem -- so every test here explicitly sets/unsets
AUGUR_TRIAL_CACHE (never relies on ambient state) and always starts from an
empty in-process memo (the `_isolated_memo` autouse fixture below), mirroring
test_trial_cache.py's own isolation discipline. Nothing here touches the real
repo's augur_uploads/ -- UPLOADS is monkeypatched to a temp dir per test.

The two required proofs (docs' own wording):
  1. Golden equality: memo ON (two calls) returns arrays byte-identical to a
     memo-OFF load -- np.array_equal on every array, plus day_id and
     fingerprint.
  2. Invalidation: a changed file on disk (different mtime/size) is ALWAYS a
     fresh re-read, never a stale hit.
"""
import os

import numpy as np
import pandas as pd
import pytest

import augur_engine.data as D


@pytest.fixture(autouse=True)
def _isolated_memo(monkeypatch):
    """Every test starts with the memo OFF and EMPTY -- a test that wants it
    on sets AUGUR_TRIAL_CACHE itself. Cleared again on teardown so no test can
    leak a memo entry into the next one."""
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    D._memo_clear()
    yield
    D._memo_clear()


# 3 bars on ET 2026-03-02, 2 bars on 2026-03-03 (same shape as
# tests/test_data_loading.py, so this exercises the identical day_id /
# date-slice path the memo sits in front of).
_ROWS = [
    ("2026-03-02 10:00", 1.0, 2.0, 0.5, 1.5, 10),
    ("2026-03-02 10:05", 1.0, 2.0, 0.5, 1.5, 11),
    ("2026-03-02 10:10", 1.0, 2.0, 0.5, 1.5, 12),
    ("2026-03-03 10:00", 1.0, 2.0, 0.5, 1.5, 20),
    ("2026-03-03 10:05", 1.0, 2.0, 0.5, 1.5, 21),
]


def _write_csv(path, rows=_ROWS):
    cols = ["time", "open", "high", "low", "close", "volume"]
    data = [(int(pd.Timestamp(t, tz="US/Eastern").timestamp()), o, h, l, c, v)
            for (t, o, h, l, c, v) in rows]
    pd.DataFrame(data, columns=cols).to_csv(path, index=False)


@pytest.fixture
def master(tmp_path, monkeypatch):
    """A synthetic master CSV + registry row with a FULL identity (instrument/
    timeframe/source) -- PR3's memo key wants these to build a realistic
    identity tuple (test_data_loading.py's minimal fixture omits them since
    load_master_arrays itself never reads them)."""
    name = "m.csv"
    _write_csv(tmp_path / name)
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    return {"filename": name, "name": "TEST", "instrument": "SYNI",
            "timeframe": "5m", "source": "test"}


# ─────────────────────────────────────────────────────────────────────────
# 1. GOLDEN EQUALITY -- memo ON must never change what's returned
# ─────────────────────────────────────────────────────────────────────────

def test_memo_on_byte_identical_to_memo_off(master, monkeypatch):
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    r_off = D.load_master_arrays(master)

    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    D._memo_clear()
    r_on1 = D.load_master_arrays(master)   # memo empty -> fresh read, populates
    r_on2 = D.load_master_arrays(master)   # memo populated -> should be a HIT

    for a, b, label in ((r_off, r_on1, "off vs on-empty"),
                        (r_on1, r_on2, "on-empty vs on-populated")):
        for k in ("open", "high", "low", "close", "day_id"):
            assert np.array_equal(a[k], b[k]), f"{label}: {k}"
        assert np.array_equal(a["volume"], b["volume"]), f"{label}: volume"
        assert a["fingerprint"] == b["fingerprint"], f"{label}: fingerprint"
        assert list(a["index"]) == list(b["index"]), f"{label}: index"


def test_memo_hit_reuses_the_same_array_objects(master, monkeypatch):
    """Stronger than value-equality: proves the SECOND call actually skipped
    the CSV read/factorize (genuine reuse), not just a coincidentally-equal
    fresh read -- the entire point of PR3."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    r1 = D.load_master_arrays(master)
    r2 = D.load_master_arrays(master)
    assert r1 is not r2                          # distinct outer dicts (safe to rebind keys)
    for k in ("open", "high", "low", "close", "volume", "day_id"):
        assert r1[k] is r2[k], f"{k} was not reused"
    assert r1["index"] is r2["index"]


def test_memo_off_never_reuses_arrays(master, monkeypatch):
    """The control case -- confirms the memo genuinely gates on is_enabled()
    rather than always caching, and never even touches _MEMO when off."""
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    r1 = D.load_master_arrays(master)
    r2 = D.load_master_arrays(master)
    assert r1["close"] is not r2["close"]
    assert np.array_equal(r1["close"], r2["close"])   # still numerically equal
    assert D._MEMO == []                              # OFF never writes to the memo


# ─────────────────────────────────────────────────────────────────────────
# 2. INVALIDATION -- a changed file is ALWAYS a miss
# ─────────────────────────────────────────────────────────────────────────

def test_file_mtime_change_forces_reload(master, monkeypatch, tmp_path):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    r1 = D.load_master_arrays(master)

    path = tmp_path / master["filename"]
    st = os.stat(path)
    os.utime(path, (st.st_mtime + 5.0, st.st_mtime + 5.0))   # same bytes, different mtime (no sleep needed)

    r2 = D.load_master_arrays(master)
    assert r2["close"] is not r1["close"]             # a genuine re-read, not a stale hit
    assert np.array_equal(r1["close"], r2["close"])   # (content happens to be unchanged here)


def test_file_content_change_forces_reload_and_is_reflected(master, monkeypatch, tmp_path):
    """The realistic case (a master auto-synced new bars): content AND
    mtime/size all change -- the memo must reflect the NEW data, never serve
    the stale array. This is the exact 'silent window slide' hazard class
    CLAUDE.md's comparison-rerun hard rule warns about, one layer earlier."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    r1 = D.load_master_arrays(master)
    assert len(r1["close"]) == 5

    path = tmp_path / master["filename"]
    _write_csv(path, _ROWS + [("2026-03-04 10:00", 9.0, 9.0, 9.0, 9.0, 99)])
    st = os.stat(path)
    os.utime(path, (st.st_mtime + 5.0, st.st_mtime + 5.0))   # force a distinct mtime even if the OS's mtime resolution is coarse

    r2 = D.load_master_arrays(master)
    assert len(r2["close"]) == 6              # picked up the new bar
    assert r2["close"][-1] == 9.0
    assert r2["fingerprint"] != r1["fingerprint"]


def test_different_date_window_is_an_independent_memo_entry(master, monkeypatch):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    r_full = D.load_master_arrays(master)
    r_sliced = D.load_master_arrays(master, date_from="2026-03-03")
    assert len(r_full["close"]) == 5
    assert len(r_sliced["close"]) == 2
    # each window keeps its own independently-keyed, correctly-scoped entry
    r_full2 = D.load_master_arrays(master)
    r_sliced2 = D.load_master_arrays(master, date_from="2026-03-03")
    assert r_full["close"] is r_full2["close"]
    assert r_sliced["close"] is r_sliced2["close"]


# ─────────────────────────────────────────────────────────────────────────
# 3. Hardening
# ─────────────────────────────────────────────────────────────────────────

def test_memo_arrays_are_read_only_once_memoized(master, monkeypatch):
    """Read-only from the moment an entry is created -- including the very
    FIRST (populating) call, not just later hits -- so no caller (first or
    Nth) can silently corrupt a shared entry for every future reader."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    r1 = D.load_master_arrays(master)             # populates
    r2 = D.load_master_arrays(master)              # hit
    for r, label in ((r1, "populating call"), (r2, "hit")):
        assert r["close"].flags.writeable is False, label
        with pytest.raises(ValueError):
            r["close"][0] = 999.0


def test_memo_bounded_lru_evicts_oldest(tmp_path, monkeypatch):
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    cap = D._MEMO_MAX_ENTRIES
    masters = []
    for i in range(cap + 1):
        name = f"m{i}.csv"
        _write_csv(tmp_path / name)
        masters.append({"filename": name, "name": f"T{i}", "instrument": "SYNI",
                        "timeframe": "5m", "source": f"src{i}"})

    first = D.load_master_arrays(masters[0])
    for m in masters[1:]:
        D.load_master_arrays(m)                    # `cap` more distinct entries -> evicts masters[0]
    assert len(D._MEMO) == cap                      # never grows past the bound

    # masters[0] was the least-recently-used -> evicted -> reloading it is a
    # genuine fresh read (a NEW array object), never a stale/phantom hit
    reloaded = D.load_master_arrays(masters[0])
    assert reloaded["close"] is not first["close"]
    assert np.array_equal(reloaded["close"], first["close"])


def test_disabled_memo_never_grows(master, monkeypatch):
    monkeypatch.delenv("AUGUR_TRIAL_CACHE", raising=False)
    for _ in range(3):
        D.load_master_arrays(master)
    assert D._MEMO == []


def test_missing_master_identity_fields_still_memoizes_safely(tmp_path, monkeypatch):
    """A caller whose master row lacks instrument/timeframe/source (e.g. a
    minimal test double) must not crash the memo -- it just falls back to a
    key built from the remaining fields (filename/window/mtime/size)."""
    monkeypatch.setenv("AUGUR_TRIAL_CACHE", "1")
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    _write_csv(tmp_path / "bare.csv")
    m = {"filename": "bare.csv", "name": "BARE"}   # no instrument/timeframe/source
    r1 = D.load_master_arrays(m)
    r2 = D.load_master_arrays(m)
    assert r1["close"] is r2["close"]
