"""Unit tests for api.webull_stream -- Webull Level 1 stream -> 1-minute bar builder.

Everything here runs against BarBuilder / merge_and_write / the pure helpers directly.
No network, no MQTT, no webull SDK import is exercised (the SDK only appears inside
WebullBarStreamer._connect_once, which these tests never call).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from api import webull_stream as S


def _epoch(y, mo, d, h, mi, s=0, tz="US/Eastern"):
    return datetime(y, mo, d, h, mi, s, tzinfo=ZoneInfo(tz)).timestamp()


def _tick(symbol, epoch, price, vol):
    return S.QuoteUpdate(symbol=symbol, epoch=epoch, price=price, trade_volume=vol)


def _snap(symbol, epoch, price, cum_vol):
    return S.QuoteUpdate(symbol=symbol, epoch=epoch, price=price, cum_volume=cum_vol)


# ── bucketing / bar-start stamping ───────────────────────────────────────────
def test_bucket_epoch_floors_to_minute_start():
    e = _epoch(2026, 9, 14, 10, 32, 47)   # RTH, EDT
    b = S.bucket_epoch(e)
    assert b == _epoch(2026, 9, 14, 10, 32, 0)
    assert b % 60 == 0


def test_bucket_lands_on_us_eastern_minute_start_across_dst():
    # one date in EDT (UTC-4), one in EST (UTC-5) -- bucket_epoch never converts
    # timezones, so both must still land exactly on the ET minute boundary.
    for (y, mo, d, h, mi, s) in [(2026, 7, 15, 9, 31, 5), (2026, 12, 15, 9, 31, 5)]:
        e = _epoch(y, mo, d, h, mi, s)
        b = S.bucket_epoch(e)
        dt_et = datetime.fromtimestamp(b, tz=ZoneInfo("US/Eastern"))
        assert dt_et.second == 0
        assert (dt_et.hour, dt_et.minute) == (h, mi)


# ── BarBuilder: single-symbol OHLCV from TICK-shaped (incremental volume) updates ──
def test_ticks_build_one_bar_ohlcv():
    b = S.BarBuilder()
    base = _epoch(2026, 9, 14, 10, 0, 0)
    closed = []
    closed += b.ingest(_tick("QQQ", base + 1, 500.0, 10))
    closed += b.ingest(_tick("QQQ", base + 20, 502.0, 5))
    closed += b.ingest(_tick("QQQ", base + 40, 499.0, 7))
    assert closed == []   # still inside the same minute -- nothing closed yet
    # a tick in the NEXT minute rolls the first bar closed
    closed += b.ingest(_tick("QQQ", base + 61, 501.0, 3))
    assert len(closed) == 1
    bar = closed[0]
    assert bar["time"] == base
    assert (bar["open"], bar["high"], bar["low"], bar["close"]) == (500.0, 502.0, 499.0, 499.0)
    assert bar["volume"] == 22.0   # 10+5+7, incremental sum


def test_flush_closes_in_progress_bar():
    b = S.BarBuilder()
    base = _epoch(2026, 9, 14, 10, 0, 0)
    b.ingest(_tick("QQQ", base + 5, 500.0, 1))
    closed = b.flush()
    assert len(closed) == 1
    assert closed[0]["time"] == base
    assert closed[0]["volume"] == 1.0
    # a stray late update for the flushed bucket must NOT reopen it
    more = b.ingest(_tick("QQQ", base + 6, 999.0, 1))
    assert more == []
    assert b.stats["out_of_order_dropped"] == 1


# ── quiet minutes stay gaps, never synthesized ──────────────────────────────
def test_gap_between_bars_is_not_synthesized():
    b = S.BarBuilder()
    base = _epoch(2026, 9, 14, 10, 0, 0)
    b.ingest(_tick("QQQ", base + 1, 500.0, 1))
    closed = b.ingest(_tick("QQQ", base + 300, 505.0, 2))   # 5 minutes later
    assert len(closed) == 1
    assert closed[0]["time"] == base
    # no bars were fabricated for the 4 silent minutes in between
    assert b._bars["QQQ"]["time"] == base + 300


# ── out-of-order messages ────────────────────────────────────────────────────
def test_late_message_for_already_closed_bucket_is_dropped_not_applied():
    b = S.BarBuilder()
    base = _epoch(2026, 9, 14, 10, 0, 0)
    b.ingest(_tick("QQQ", base + 1, 500.0, 1))
    closed = b.ingest(_tick("QQQ", base + 61, 510.0, 1))   # closes bar #1, opens #2
    assert len(closed) == 1 and closed[0]["close"] == 500.0
    # a straggler timestamped back in bucket #1 arrives after bucket #2 has opened
    more = b.ingest(_tick("QQQ", base + 30, 999.0, 100))
    assert more == []
    assert b.stats["out_of_order_dropped"] == 1
    # bucket #2's own numbers must be untouched by the straggler
    final = b.flush()
    assert final[0]["time"] == base + 60
    assert final[0]["open"] == 510.0
    assert final[0]["volume"] == 1.0


# ── cumulative-volume (SNAPSHOT-shaped) deltas ──────────────────────────────
def test_snapshot_cumulative_volume_becomes_bar_volume_via_delta():
    b = S.BarBuilder()
    base = _epoch(2026, 9, 14, 10, 0, 0)
    b.ingest(_snap("QQQ", base + 1, 500.0, 1_000_000))     # first reading: no baseline, 0 credited
    b.ingest(_snap("QQQ", base + 20, 501.0, 1_000_400))    # +400
    closed = b.ingest(_snap("QQQ", base + 61, 502.0, 1_000_900))   # +500, closes bar #1
    assert len(closed) == 1
    assert closed[0]["volume"] == 400.0   # only the delta AFTER the baseline reading


def test_snapshot_cumulative_rollover_is_clamped_not_negative():
    b = S.BarBuilder()
    base = _epoch(2026, 9, 14, 10, 0, 0)
    b.ingest(_snap("QQQ", base + 1, 500.0, 900_000))
    b.ingest(_snap("QQQ", base + 20, 500.0, 950_000))   # +50,000
    # cumulative counter resets (new session) -- must clamp to 0, not go negative
    closed = b.ingest(_snap("QQQ", base + 61, 500.0, 10))
    assert len(closed) == 1
    assert closed[0]["volume"] == 50_000.0   # the reset reading itself contributes 0


# ── reconnect must not duplicate bars on disk ───────────────────────────────
def test_merge_and_write_is_idempotent_on_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    base = _epoch(2026, 9, 14, 10, 0, 0)
    first_session = [
        {"time": base, "open": 500.0, "high": 501.0, "low": 499.5, "close": 500.5, "volume": 100.0},
        {"time": base + 60, "open": 500.5, "high": 502.0, "low": 500.0, "close": 501.0, "volume": 80.0},
    ]
    S.merge_and_write(first_session, timeframe="1m")

    # simulate a reconnect that replays the tail of the previous session plus new bars,
    # with the boundary bar corrected (this is what "last write wins" should keep)
    second_session = [
        {"time": base + 60, "open": 500.5, "high": 503.0, "low": 500.0, "close": 502.0, "volume": 95.0},
        {"time": base + 120, "open": 502.0, "high": 502.5, "low": 501.5, "close": 502.0, "volume": 40.0},
    ]
    merged = S.merge_and_write(second_session, timeframe="1m")

    on_disk = pd.read_csv(S.stream_cache_path("1m", home=str(tmp_path)))
    assert list(on_disk["time"]) == [base, base + 60, base + 120]   # no duplicate 'time' rows
    row = on_disk[on_disk["time"] == base + 60].iloc[0]
    assert row["high"] == 503.0 and row["volume"] == 95.0   # second session's version won
    assert len(merged) == 3


# ── staleness / backoff (pure helpers used by the watchdog) ─────────────────
def test_is_stale():
    assert S.is_stale(None, 1000, 90) is False       # never connected yet != stale
    assert S.is_stale(100, 100 + 89, 90) is False
    assert S.is_stale(100, 100 + 91, 90) is True


def test_backoff_grows_then_caps():
    seq = [S.next_backoff(i, base=1.0, cap=60.0) for i in range(8)]
    assert seq[:4] == [1.0, 2.0, 4.0, 8.0]
    assert seq[-1] == 60.0
    assert all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))   # monotonic, never decreases


# ── SDK payload decoding (fakes shaped like the real TickResult/SnapshotResult) ──
class _FakeBasic:
    def __init__(self, ts_ms):
        self.timestamp = ts_ms
    def get_timestmap(self):
        return self.timestamp


class _FakeTick:
    def __init__(self, ts_ms, price, volume):
        self.basic = _FakeBasic(ts_ms)
        self.price = price
        self.volume = volume
    def get_basic(self):
        return self.basic
    def get_price(self):
        return self.price
    def get_volume(self):
        return self.volume


class _FakeSnapshot:
    def __init__(self, ts_ms, price, volume):
        self.basic = _FakeBasic(ts_ms)
        self.price = price
        self.volume = volume
    def get_basic(self):
        return self.basic


def test_normalize_tick_is_incremental_volume():
    u = S.normalize_tick("QQQ", _FakeTick(1_800_000_000_000, 500.25, 12))
    assert u.symbol == "QQQ"
    assert u.trade_volume == 12.0
    assert u.cum_volume is None
    assert u.epoch == 1_800_000_000_000 / 1000.0


def test_normalize_snapshot_is_cumulative_volume():
    u = S.normalize_snapshot("QQQ", _FakeSnapshot(1_800_000_000_000, 500.25, 1_234_567))
    assert u.cum_volume == 1_234_567.0
    assert u.trade_volume is None
