"""Tests for api/cloud_signal.py's small "alpaca backfill splice" addition
(tools/backfill_qqq_5m_alpaca.py, WEBULL go-live "alpaca" task, 2026-09-26):
_load_backfill_bars / _prepend_backfill / historical_bars.

Everything here is local-filesystem only (tmp_path) -- no network, no ssh, and nothing
touches the real C:\\EdgeLog cache. The tool that actually WRITES a QQQ_{tf}_backfill.csv
(tools/backfill_qqq_5m_alpaca.py) is covered separately in
tests/test_backfill_qqq_5m_alpaca.py; this file only exercises the READ side.
"""
import os

import pandas as pd
import pytest

import api.cloud_signal as cs


def _bars(times, price=100.0, volume=1000.0):
    return pd.DataFrame({
        "time": list(times),
        "open": [price] * len(times), "high": [price] * len(times),
        "low": [price] * len(times), "close": [price] * len(times),
        "volume": [volume] * len(times),
    })


@pytest.fixture(autouse=True)
def _clear_backfill_cache():
    # Every test gets a clean slate: the module-level mtime cache/warned-set must never
    # leak a result (or a "already logged" flag) from one test's tmp_path into another's.
    cs._BACKFILL_CACHE.clear()
    cs._BACKFILL_WARNED.clear()
    yield
    cs._BACKFILL_CACHE.clear()
    cs._BACKFILL_WARNED.clear()


def _home(tmp_path, name):
    paths = cs._paths(home=str(tmp_path / name))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    return paths


def test_load_backfill_bars_returns_none_when_file_absent(tmp_path):
    paths = _home(tmp_path, "no_backfill")
    assert cs._load_backfill_bars("5m", paths) is None


def test_load_backfill_bars_reads_the_file_and_caches_by_mtime(tmp_path, monkeypatch):
    paths = _home(tmp_path, "cached_by_mtime")
    bpath = cs._backfill_path("5m", paths)
    _bars([100, 200]).to_csv(bpath, index=False)

    real_read_csv = pd.read_csv
    calls = []

    def spy(path, *a, **k):
        calls.append(path)
        return real_read_csv(path, *a, **k)

    monkeypatch.setattr(pd, "read_csv", spy)

    df1 = cs._load_backfill_bars("5m", paths)
    df2 = cs._load_backfill_bars("5m", paths)
    assert len(df1) == 2
    assert df1 is df2, "same mtime must return the CACHED frame, not re-read the file"
    assert len(calls) == 1, "the file must be parsed exactly once while its mtime is unchanged"

    # touching the file (new mtime) must trigger exactly one more real read
    _bars([100, 200, 300]).to_csv(bpath, index=False)
    os.utime(bpath, None)
    df3 = cs._load_backfill_bars("5m", paths)
    assert len(df3) == 3
    assert len(calls) == 2


def test_load_backfill_bars_is_fail_safe_and_logs_once(tmp_path, capsys):
    paths = _home(tmp_path, "corrupt_backfill")
    bpath = cs._backfill_path("5m", paths)
    with open(bpath, "wb") as fh:
        fh.write(b"\x00\x01not,a,valid\ncsv\x02\x03")

    # A file this broken may or may not raise inside pandas depending on version, but
    # this test only needs SOME read failure -- force it by making the "columns" wrong
    # in a way that still parses as a DataFrame is not guaranteed to fail, so instead
    # patch read_csv itself to raise, which is the actual contract under test: any
    # exception is swallowed, logged once, and the file is treated as absent.
    import api.cloud_signal as cs_mod

    def boom(*a, **k):
        raise ValueError("corrupt csv")

    orig = pd.read_csv
    pd.read_csv = boom
    try:
        r1 = cs_mod._load_backfill_bars("5m", paths)
        r2 = cs_mod._load_backfill_bars("5m", paths)
    finally:
        pd.read_csv = orig

    assert r1 is None and r2 is None
    out = capsys.readouterr().out
    assert out.count("backfill file unreadable") == 1, (
        "a broken backfill file must be logged exactly ONCE, not once per call")


def test_prepend_backfill_splices_only_strictly_older_rows(tmp_path):
    paths = _home(tmp_path, "splice_home")
    bpath = cs._backfill_path("5m", paths)
    # backfill holds: 700, 850 (both older than the cache's first bar 1000), PLUS a row
    # AT 1000 itself with a DIFFERENT price -- this must be dropped entirely, never used
    # to override the cache's own row.
    backfill = pd.DataFrame({
        "time": [700, 850, 1000],
        "open": [1.0, 2.0, 999.0], "high": [1.0, 2.0, 999.0],
        "low": [1.0, 2.0, 999.0], "close": [1.0, 2.0, 999.0],
        "volume": [1.0, 1.0, 1.0],
    })
    backfill.to_csv(bpath, index=False)

    cache = _bars([1000, 1300, 1600], price=50.0)

    out = cs._prepend_backfill(cache, "5m", paths)

    assert list(out["time"]) == [700, 850, 1000, 1300, 1600]
    row_1000 = out[out["time"] == 1000].iloc[0]
    assert row_1000["open"] == 50.0, "the cache's own bar at 1000 must win, never the backfill row"


def test_prepend_backfill_is_noop_without_a_backfill_file(tmp_path):
    paths = _home(tmp_path, "no_backfill_2")
    cache = _bars([1000, 1300])
    out = cs._prepend_backfill(cache, "5m", paths)
    assert out is cache


def test_prepend_backfill_is_noop_when_backfill_has_no_older_rows(tmp_path):
    paths = _home(tmp_path, "no_older_rows")
    bpath = cs._backfill_path("5m", paths)
    pd.DataFrame({"time": [1300, 1600], "open": [1.0, 1.0], "high": [1.0, 1.0],
                 "low": [1.0, 1.0], "close": [1.0, 1.0], "volume": [1.0, 1.0]}
                ).to_csv(bpath, index=False)
    cache = _bars([1000, 1300])
    out = cs._prepend_backfill(cache, "5m", paths)
    assert list(out["time"]) == [1000, 1300]


def test_prepend_backfill_leaves_a_missing_or_empty_cache_unchanged(tmp_path):
    """A None/empty live cache must stay None/empty -- signal computation should skip the
    leg the same way it would with no cache at all, never run off backfill-only history
    that step()'s cold-cache check was never designed to see."""
    paths = _home(tmp_path, "empty_cache")
    bpath = cs._backfill_path("5m", paths)
    _bars([100, 200]).to_csv(bpath, index=False)
    empty = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    out = cs._prepend_backfill(empty, "5m", paths)
    assert len(out) == 0
    out_none = cs._prepend_backfill(None, "5m", paths)
    assert out_none is None


def test_historical_bars_matches_load_cached_bars_when_no_backfill_present(tmp_path):
    paths = _home(tmp_path, "plain_home")
    cache = _bars([1000, 1300])
    cache.to_csv(cs._cache_path("5m", paths), index=False)
    plain = cs.load_cached_bars("5m", paths)
    widened = cs.historical_bars("5m", paths)
    assert list(widened["time"]) == list(plain["time"])


def test_historical_bars_widens_the_window_end_to_end(tmp_path):
    """The same integration path _cache_session_count / log_history_windows and step()'s
    offline (fetch=False) branch use: writing a QQQ_5m_backfill.csv next to a cache with
    fewer sessions than NOISE's real REQUIRED_LOOKBACK_SESSIONS must make historical_bars
    report MORE distinct sessions than load_cached_bars alone."""
    paths = _home(tmp_path, "widen_home")
    n_cache_sessions, n_backfill_sessions, bars_per_session = 10, 20, 3
    days = pd.bdate_range("2026-06-01", periods=n_backfill_sessions + n_cache_sessions, tz=cs.TZ)

    def _session_bars(day):
        day_open = day + pd.Timedelta(hours=9, minutes=30)
        times = [day_open + pd.Timedelta(minutes=5 * k) for k in range(bars_per_session)]
        return [int(t.tz_convert("UTC").timestamp()) for t in times]

    cache_times = []
    for day in days[n_backfill_sessions:]:
        cache_times.extend(_session_bars(day))
    backfill_times = []
    for day in days[:n_backfill_sessions]:
        backfill_times.extend(_session_bars(day))

    _bars(cache_times).to_csv(cs._cache_path("5m", paths), index=False)
    _bars(backfill_times).to_csv(cs._backfill_path("5m", paths), index=False)

    before = cs._cache_session_count("5m", paths)
    # sanity: before backfill existed as far as load_cached_bars is concerned
    plain_only = cs.build_arrays(cs.load_cached_bars("5m", paths))
    assert len(set(plain_only["day_id"].tolist())) == n_cache_sessions

    after_arrays = cs.build_arrays(cs.historical_bars("5m", paths))
    assert len(set(after_arrays["day_id"].tolist())) == n_cache_sessions + n_backfill_sessions
    assert before == n_cache_sessions + n_backfill_sessions, (
        "_cache_session_count must read historical_bars (backfill included), "
        "not the plain on-disk cache alone")


def test_fetch_and_merge_never_writes_backfill_rows_to_the_live_cache(tmp_path, monkeypatch):
    """The core "never race the live cache writer" guarantee: fetch_and_merge's RETURN
    value may include spliced backfill history, but the file it writes to disk
    (QQQ_5m.csv) must be byte-identical to what it would have written with no backfill
    file present at all."""
    paths = _home(tmp_path, "fetch_merge_home")
    cache = _bars([2000, 2300])
    cache.to_csv(cs._cache_path("5m", paths), index=False)
    backfill = _bars([500, 800])
    backfill.to_csv(cs._backfill_path("5m", paths), index=False)

    fresh = _bars([2600])
    monkeypatch.setattr(cs, "_fetch_webull", lambda tf, log=print: fresh)

    merged, source, cache_ok = cs.fetch_and_merge("5m", paths)

    # the RETURNED frame includes the older backfill rows
    assert 500 in set(merged["time"].tolist())
    assert 800 in set(merged["time"].tolist())

    # but the ON-DISK cache does not
    on_disk = pd.read_csv(cs._cache_path("5m", paths))
    assert 500 not in set(on_disk["time"].tolist())
    assert 800 not in set(on_disk["time"].tolist())
    assert set(on_disk["time"].tolist()) == {2000, 2300, 2600}
