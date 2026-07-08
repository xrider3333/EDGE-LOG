"""Unit tests for augur_engine.data.load_master_arrays — master-CSV -> OHLCV arrays.

The date-slice + day_id factorization is look-ahead-critical: day_id must be
re-derived AFTER any date slice so it stays 0-based and contiguous, or every
day_id-aware strategy would silently key off shifted day boundaries. These tests use
a tiny synthetic CSV (no real data, no sqlite) with monkeypatched UPLOADS to pin:
  * day_id groups ET calendar days as 0,0,0,1,1
  * date_from / date_to slice correctly (date_to is inclusive of the whole day)
  * day_id is re-factorized to 0-based after a slice (the look-ahead-safety property)
  * a missing volume column yields volume=None
"""
import numpy as np
import pandas as pd
import pytest

import augur_engine.data as D

# 3 bars on ET 2026-03-02, 2 bars on 2026-03-03 (EST, UTC-5).
_ROWS = [
    ("2026-03-02 10:00", 1.0, 2.0, 0.5, 1.5, 10),
    ("2026-03-02 10:05", 1.0, 2.0, 0.5, 1.5, 11),
    ("2026-03-02 10:10", 1.0, 2.0, 0.5, 1.5, 12),
    ("2026-03-03 10:00", 1.0, 2.0, 0.5, 1.5, 20),
    ("2026-03-03 10:05", 1.0, 2.0, 0.5, 1.5, 21),
]


@pytest.fixture
def master(tmp_path, monkeypatch):
    """Write the synthetic master CSV into a temp UPLOADS dir and return a master row.
    Returns a factory so a test can also request the no-volume variant."""
    def _make(with_volume=True):
        cols = ["time", "open", "high", "low", "close", "volume"]
        rows = [(int(pd.Timestamp(t, tz="US/Eastern").timestamp()), o, h, l, c, v)
                for (t, o, h, l, c, v) in _ROWS]
        df = pd.DataFrame(rows, columns=cols)
        if not with_volume:
            df = df.drop(columns=["volume"])
        name = "m.csv" if with_volume else "nv.csv"
        df.to_csv(tmp_path / name, index=False)
        monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
        return {"filename": name, "name": "TEST"}
    return _make


def test_day_id_groups_calendar_days(master):
    a = D.load_master_arrays(master())
    assert a["day_id"].tolist() == [0, 0, 0, 1, 1]
    assert len(a["close"]) == 5
    assert a["close"].dtype == np.float64


def test_arrays_and_meta_present(master):
    m = master()
    a = D.load_master_arrays(m)
    assert set(["open", "high", "low", "close", "volume", "day_id", "index", "meta"]) <= set(a)
    assert a["meta"] is m
    assert a["volume"][0] == 10.0


def test_date_from_slices_and_refactorizes_day_id(master):
    a = D.load_master_arrays(master(), date_from="2026-03-03")
    # only the 03-03 bars survive, and day_id restarts at 0 (NOT 1)
    assert len(a["close"]) == 2
    assert a["day_id"].tolist() == [0, 0]


def test_date_to_is_inclusive_of_whole_day(master):
    a = D.load_master_arrays(master(), date_to="2026-03-02")
    assert len(a["close"]) == 3
    assert a["day_id"].tolist() == [0, 0, 0]


def test_date_window_both_ends(master):
    a = D.load_master_arrays(master(), date_from="2026-03-02", date_to="2026-03-02")
    assert len(a["close"]) == 3


def test_missing_volume_column_is_none(master):
    a = D.load_master_arrays(master(with_volume=False))
    assert a["volume"] is None
