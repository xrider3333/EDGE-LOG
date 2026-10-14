"""rolls.epoch_seconds: same answer for every input shape, without boxing a tz-aware index bar by bar."""
import time

import numpy as np
import pandas as pd

from augur_engine.rolls import epoch_seconds


def _ref(stamps):
    """The pre-2026-10-14 body, kept here as the reference."""
    if stamps is None:
        return np.zeros(0, dtype="int64")
    a = np.asarray(stamps)
    if a.dtype.kind in "iuf":
        a = a.astype("int64")
        return a // 1000 if len(a) and a.max() > 10 ** 11 else a
    idx = pd.DatetimeIndex(stamps)
    if idx.tz is None:
        idx = idx.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    return (idx.tz_convert("UTC").asi8 // 10 ** 9).astype("int64")


def _cases():
    naive = pd.date_range("2024-03-08 09:30", periods=3000, freq="min")      # crosses the DST switch day
    aware = naive.tz_localize("America/New_York", nonexistent="shift_forward")
    utc = aware.tz_convert("UTC")
    secs = utc.asi8 // 10 ** 9
    return [naive, aware, utc, pd.Series(aware), pd.Series(naive), naive.values, secs, secs * 1000,
            secs.astype(float), pd.Series(secs), list(aware[:5]), [str(x) for x in naive[:5]], ["2024-01-02"],
            [int(s) for s in secs[:5]], [], np.zeros(0, "int64"), pd.DatetimeIndex([])]


def test_same_as_reference_on_every_shape():
    for s in _cases():
        got, ref = epoch_seconds(s), _ref(s)
        assert got.dtype == np.int64
        assert np.array_equal(got, ref), type(s)
    assert len(epoch_seconds(None)) == 0


def test_tz_aware_index_is_not_boxed():
    idx = pd.date_range("2016-07-01", periods=355_000, freq="min", tz="America/New_York")
    t = time.perf_counter()
    epoch_seconds(idx)
    assert time.perf_counter() - t < 0.5        # the boxed path took ~2.3 s for this many bars
