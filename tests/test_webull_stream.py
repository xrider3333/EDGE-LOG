"""Unit tests for api.webull_stream -- Webull Level 1 stream -> 1-minute bar builder.

Everything here runs against BarBuilder / merge_and_write / the pure helpers directly.
No network, no MQTT, no webull SDK import is exercised (the SDK only appears inside
WebullBarStreamer._connect_once, which these tests never call).
"""
import logging
import os
import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

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
    def __init__(self, ts_ms, trading_session=None):
        self.timestamp = ts_ms
        self.trading_session = trading_session
    def get_timestmap(self):
        return self.timestamp


class _FakeTick:
    def __init__(self, ts_ms, price, volume, trading_session=None):
        self.basic = _FakeBasic(ts_ms, trading_session=trading_session)
        self.price = price
        self.volume = volume
    def get_basic(self):
        return self.basic
    def get_price(self):
        return self.price
    def get_volume(self):
        return self.volume


class _FakeSnapshot:
    def __init__(self, ts_ms, price, volume, trading_session=None, ext_price=None, ext_volume=None):
        self.basic = _FakeBasic(ts_ms, trading_session=trading_session)
        self.price = price
        self.volume = volume
        self.ext_price = ext_price
        self.ext_volume = ext_volume
    def get_basic(self):
        return self.basic


class _FakeBookLevel:
    """One side's top-of-book entry: .price/.size ATTRIBUTES, confirmed live 2026-09-22
    (not a dict, not a [price, size] pair)."""
    def __init__(self, price, size):
        self.price = price
        self.size = size


class _FakeQuote:
    def __init__(self, ts_ms, bids=None, asks=None, trading_session=None):
        self.basic = _FakeBasic(ts_ms, trading_session=trading_session)
        self.bids = bids or []
        self.asks = asks or []
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


# ── trading_session: carried through, explicit accepted set, clock fallback ────
def test_normalize_tick_trading_session_defaults_none_when_absent():
    u = S.normalize_tick("QQQ", _FakeTick(1_800_000_000_000, 500.25, 12))
    assert u.trading_session is None


def test_normalize_tick_carries_trading_session_when_present():
    u = S.normalize_tick("QQQ", _FakeTick(1_800_000_000_000, 500.25, 12, trading_session="ATH"))
    assert u.trading_session == "ATH"


def test_normalize_snapshot_falls_back_to_ext_fields_when_price_is_none():
    snap = _FakeSnapshot(1_800_000_000_000, price=None, volume=None,
                          ext_price=501.10, ext_volume=2_000_000, trading_session="ATH")
    u = S.normalize_snapshot("QQQ", snap)
    assert u.price == 501.10
    assert u.cum_volume == 2_000_000.0
    assert u.trading_session == "ATH"


def test_normalize_snapshot_price_stays_none_when_ext_also_missing():
    u = S.normalize_snapshot("QQQ", _FakeSnapshot(1_800_000_000_000, price=None, volume=None))
    assert u.price is None   # caller (_on_message) must skip this -- never a hole in a bar


def test_normalize_quote_reads_top_of_book_attributes():
    q = _FakeQuote(1_800_000_000_000,
                    bids=[_FakeBookLevel(499.90, 3), _FakeBookLevel(499.85, 10)],
                    asks=[_FakeBookLevel(500.10, 4)], trading_session="RTH")
    bq = S.normalize_quote("QQQ", q)
    assert (bq.bid, bq.bid_size) == (499.90, 3.0)
    assert (bq.ask, bq.ask_size) == (500.10, 4.0)
    assert bq.trading_session == "RTH"
    assert bq.epoch == 1_800_000_000_000 / 1000.0


def test_normalize_quote_handles_empty_book_side():
    q = _FakeQuote(1_800_000_000_000, bids=[], asks=[_FakeBookLevel(500.10, 4)])
    bq = S.normalize_quote("QQQ", q)
    assert (bq.bid, bq.bid_size) == (None, None)
    assert bq.ask == 500.10


# is_regular_session: the CLOCK is authoritative for inclusion (a whitelist was tried and
# rejected -- see module docstring's TRADING SESSION FILTERING). A label can only REMOVE a
# print (a KNOWN extended label excludes it even inside the window); it can never ADD one
# outside the window, and an unrecognized/missing label never excludes anything either.
def test_known_extended_sessions_is_explicit_blacklist_seeded_with_ath_and_ovn():
    assert "ath" in S.KNOWN_EXTENDED_SESSIONS
    assert "ovn" in S.KNOWN_EXTENDED_SESSIONS
    # not a whitelist: 'rth' (or any regular-session spelling) must NOT be enumerated here
    assert "rth" not in S.KNOWN_EXTENDED_SESSIONS
    assert "reg" not in S.KNOWN_EXTENDED_SESSIONS


def test_is_regular_session_unknown_label_inside_window_is_included():
    epoch = _epoch(2026, 1, 5, 10, 0, 0)   # Monday, inside the RTH window
    # neither 'RTH' nor a made-up label is in the blacklist -- absence must not exclude;
    # the clock alone decides, and the clock says this is regular hours.
    assert S.is_regular_session("RTH", epoch) is True
    assert S.is_regular_session("REG", epoch) is True
    assert S.is_regular_session("NORMAL", epoch) is True
    assert S.is_regular_session("SOMETHING_UNKNOWN", epoch) is True


def test_is_regular_session_known_extended_label_excludes_even_inside_window():
    epoch = _epoch(2026, 1, 5, 10, 0, 0)   # Monday, inside the RTH window
    assert S.is_regular_session("ATH", epoch) is False
    assert S.is_regular_session("OVN", epoch) is False


def test_is_regular_session_label_match_is_case_insensitive():
    epoch = _epoch(2026, 1, 5, 10, 0, 0)
    assert S.is_regular_session("ath", epoch) is False
    assert S.is_regular_session("AtH", epoch) is False
    assert S.is_regular_session("Ovn", epoch) is False


def test_is_regular_session_no_label_ever_beats_the_clock():
    # whatever the label says, OUTSIDE the clock window is always excluded -- the clock is
    # an AND term, never overridden upward by a label that looks like regular hours.
    ath_clock = _epoch(2026, 1, 5, 19, 0, 0)   # Monday, after-hours by the clock
    assert S.is_regular_session("RTH", ath_clock) is False
    assert S.is_regular_session("REG", ath_clock) is False
    assert S.is_regular_session(None, ath_clock) is False


def test_is_regular_session_falls_back_to_clock_when_label_missing():
    rth = _epoch(2026, 1, 5, 10, 0, 0)      # Monday RTH
    ath = _epoch(2026, 1, 5, 19, 0, 0)      # Monday after-hours
    weekend = _epoch(2026, 1, 3, 10, 0, 0)  # Saturday
    assert S.is_regular_session(None, rth) is True
    assert S.is_regular_session(None, ath) is False
    assert S.is_regular_session(None, weekend) is False


# ── item B (2026-09-25): belt-and-braces watchdog window (_in_stream_window) ─────────────
def test_in_stream_window_before_open_is_false():
    assert S._in_stream_window(_epoch(2026, 9, 8, 9, 28, 0)) is False   # Tuesday


def test_in_stream_window_at_open_is_true():
    assert S._in_stream_window(_epoch(2026, 9, 8, 9, 29, 0)) is True


def test_in_stream_window_at_close_boundary_is_true():
    assert S._in_stream_window(_epoch(2026, 9, 8, 16, 2, 0)) is True


def test_in_stream_window_past_close_is_false():
    assert S._in_stream_window(_epoch(2026, 9, 8, 16, 3, 0)) is False


def test_in_stream_window_weekend_is_false():
    assert S._in_stream_window(_epoch(2026, 9, 5, 10, 0, 0)) is False   # Saturday


def test_in_stream_window_has_no_holiday_calendar_by_design():
    """Deliberately simpler than api/qqq_exec.py's own _stream_should_run (see this
    function's own docstring): a weekday holiday still reads as 'in window' by the
    clock alone here -- api/qqq_exec.py's OWN window management is what keeps this
    streamer from ever being started at all on a holiday, so _watchdog never even
    runs that day and this simplification is safe."""
    labor_day = _epoch(2026, 9, 7, 10, 0, 0)   # a Monday, but Labor Day
    assert S._in_stream_window(labor_day) is True


# ── item B: _watchdog_pass -- stale outside the window just waits, never reconnects ──────
def test_watchdog_pass_not_stale_resets_attempt_and_never_reconnects():
    streamer, box = _mk_streamer(stale_after_seconds=90)
    streamer._last_message_epoch = box["t"]   # just heard from it -- not stale
    calls = []
    streamer._connect_once = lambda: (calls.append("connect"), object())[1]

    result = streamer._watchdog_pass(attempt=3)

    assert result == 0
    assert calls == []


def test_watchdog_pass_stale_outside_window_just_waits():
    box_t = _epoch(2026, 9, 8, 20, 0, 0)   # 20:00 ET, well outside 09:29-16:02
    streamer, box = _mk_streamer(now=box_t, stale_after_seconds=10)
    streamer._last_message_epoch = box_t - 100   # comfortably stale
    calls = []
    streamer._connect_once = lambda: (calls.append("connect"), object())[1]
    streamer._teardown_client = lambda: calls.append("teardown")

    result = streamer._watchdog_pass(attempt=2)

    assert result == 0, "outside the window, attempt resets rather than backing off further"
    assert calls == [], "must not reconnect (or even tear down) a stale feed outside the window"


def test_watchdog_pass_stale_inside_window_reconnects():
    box_t = _epoch(2026, 9, 8, 10, 0, 0)   # well inside the window
    streamer, box = _mk_streamer(now=box_t, stale_after_seconds=10, backoff_base=0.01,
                                 backoff_cap=0.01)
    streamer._last_message_epoch = box_t - 100
    calls = []
    fake_client = object()
    streamer._teardown_client = lambda: calls.append("teardown")
    streamer._connect_once = lambda: (calls.append("connect"), fake_client)[1]

    result = streamer._watchdog_pass(attempt=0)

    assert calls == ["teardown", "connect"]
    assert result == 0
    assert streamer._client is fake_client
    assert streamer._reconnect_count == 1


def test_watchdog_pass_stale_inside_window_reconnect_failure_backs_off():
    box_t = _epoch(2026, 9, 8, 10, 0, 0)
    streamer, box = _mk_streamer(now=box_t, stale_after_seconds=10, backoff_base=0.01,
                                 backoff_cap=0.01)
    streamer._last_message_epoch = box_t - 100
    streamer._teardown_client = lambda: None

    def boom():
        raise RuntimeError("simulated: MQTT connect failed")
    streamer._connect_once = boom

    result = streamer._watchdog_pass(attempt=0)

    assert result == 1   # attempt incremented, ready to back off further next pass
    assert streamer._reconnect_count == 0


def test_watchdog_pass_returns_none_when_stop_fires_during_backoff():
    box_t = _epoch(2026, 9, 8, 10, 0, 0)
    streamer, box = _mk_streamer(now=box_t, stale_after_seconds=10, backoff_base=5.0)
    streamer._last_message_epoch = box_t - 100
    streamer._teardown_client = lambda: None
    streamer._stop.set()   # a stop request arrives during the backoff wait

    result = streamer._watchdog_pass(attempt=0)

    assert result is None


# ── WebullBarStreamer: live-read API + session gating (drives _on_message directly --
# no SDK, no network; _connect_once/_watchdog/start/stop are untouched and still
# exercised by nothing here, exactly like the rest of this file) ───────────────────
def _mk_streamer(now=None, **kw):
    box = {"t": now if now is not None else _epoch(2026, 1, 5, 10, 0, 0)}
    streamer = S.WebullBarStreamer(clock=lambda: box["t"], **kw)
    return streamer, box


def test_on_message_tick_updates_last_trade_and_folds_both_timeframes():
    streamer, box = _mk_streamer()
    ts_ms = int(_epoch(2026, 1, 5, 10, 0, 1) * 1000)
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 10, trading_session="RTH"))

    lt = streamer.last_trade()
    assert lt["price"] == 500.0 and lt["size"] == 10.0

    assert streamer.current_bar("1m")["open"] == 500.0
    assert streamer.current_bar("5m")["open"] == 500.0


def test_on_message_ath_tick_updates_last_trade_but_never_folds_a_bar():
    streamer, box = _mk_streamer()
    ts_ms = int(_epoch(2026, 1, 5, 19, 0, 0) * 1000)   # after-hours
    streamer._on_message("tick", _FakeTick(ts_ms, 495.0, 5, trading_session="ATH"))

    assert streamer.last_trade()["price"] == 495.0
    assert streamer.current_bar("1m") is None
    assert streamer.current_bar("5m") is None


def test_on_message_known_extended_label_excludes_even_inside_clock_window():
    streamer, box = _mk_streamer()
    # 10:00 ET is well inside the RTH clock window -- only the label should exclude this,
    # proving the label's exclusion power actually reaches _on_message, not just the pure
    # is_regular_session function.
    ts_ms = int(_epoch(2026, 1, 5, 10, 0, 0) * 1000)
    streamer._on_message("tick", _FakeTick(ts_ms, 495.0, 5, trading_session="ATH"))

    assert streamer.last_trade()["price"] == 495.0   # still observed
    assert streamer.current_bar("1m") is None        # but never folded into a bar
    assert streamer.current_bar("5m") is None


def test_on_message_unknown_label_inside_window_still_folds_a_bar():
    streamer, box = _mk_streamer()
    ts_ms = int(_epoch(2026, 1, 5, 10, 0, 0) * 1000)
    # a label the blacklist has never heard of must NOT block a print the clock says is
    # regular-hours -- this is the exact failure mode a whitelist would have caused.
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 10, trading_session="REG"))

    assert streamer.current_bar("1m")["open"] == 500.0
    assert streamer.current_bar("5m")["open"] == 500.0


def test_on_message_quote_updates_last_quote_only_not_last_trade_or_bars():
    streamer, box = _mk_streamer()
    ts_ms = int(_epoch(2026, 1, 5, 10, 0, 1) * 1000)
    q = _FakeQuote(ts_ms, bids=[_FakeBookLevel(499.90, 3)], asks=[_FakeBookLevel(500.10, 4)])
    streamer._on_message("quote", q)

    lq = streamer.last_quote()
    assert (lq["bid"], lq["ask"]) == (499.90, 500.10)
    assert streamer.last_trade() is None
    assert streamer.current_bar("1m") is None


def test_bar_rollover_produces_closed_bar_on_both_timeframes():
    streamer, box = _mk_streamer()
    t0 = int(_epoch(2026, 1, 5, 9, 34, 59) * 1000)
    t1 = int(_epoch(2026, 1, 5, 9, 35, 0) * 1000)
    streamer._on_message("tick", _FakeTick(t0, 500.0, 1, trading_session="RTH"))
    assert streamer.closed_bar("5m") is None
    streamer._on_message("tick", _FakeTick(t1, 501.0, 1, trading_session="RTH"))

    closed5 = streamer.closed_bar("5m")
    assert closed5 is not None and closed5["close"] == 500.0
    closed1 = streamer.closed_bar("1m")
    assert closed1 is not None and closed1["close"] == 500.0
    assert streamer.current_bar("5m")["open"] == 501.0


def test_accessor_ages_use_injected_clock():
    streamer, box = _mk_streamer()
    ts_ms = int(box["t"] * 1000)
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 1, trading_session="RTH"))
    streamer._on_message("quote", _FakeQuote(ts_ms, bids=[_FakeBookLevel(499.9, 1)],
                                              asks=[_FakeBookLevel(500.1, 1)]))
    box["t"] += 7.5

    assert streamer.last_trade()["age"] == pytest.approx(7.5, abs=1e-6)
    assert streamer.last_quote()["age"] == pytest.approx(7.5, abs=1e-6)
    assert streamer.current_bar("1m")["age"] == pytest.approx(7.5, abs=1e-6)


def test_health_distinguishes_silent_from_down():
    streamer, box = _mk_streamer(stale_after_seconds=10)
    h0 = streamer.health()
    assert h0["connected"] is False and h0["fresh"] is False   # never connected

    streamer._client = object()   # simulate a live connection without touching _connect_once
    ts_ms = int(box["t"] * 1000)
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 1, trading_session="RTH"))
    assert streamer.health()["fresh"] is True

    box["t"] += 11   # past stale_after_seconds, no new message
    h_silent = streamer.health()
    assert h_silent["connected"] is True
    assert h_silent["fresh"] is False       # up but silent
    assert h_silent["last_message_age_s"] == pytest.approx(11.0, abs=1e-6)

    streamer._client = None                 # now simulate it actually going down
    h_down = streamer.health()
    assert h_down["connected"] is False
    assert h_down["fresh"] is False


def test_health_surfaces_reconnect_count():
    streamer, box = _mk_streamer()
    assert streamer.health()["reconnects"] == 0
    streamer._reconnect_count = 3
    assert streamer.health()["reconnects"] == 3


def test_health_messages_per_min_windowed_count():
    streamer, box = _mk_streamer()
    for _ in range(4):
        ts_ms = int(box["t"] * 1000)
        streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 1, trading_session="RTH"))
        box["t"] += 1.0
    assert streamer.health()["messages_per_min"] == pytest.approx(4.0, abs=1e-6)
    box["t"] += 60.0
    assert streamer.health()["messages_per_min"] == pytest.approx(0.0, abs=1e-6)


def test_trading_session_counts_empty_on_fresh_instance():
    streamer, box = _mk_streamer()
    assert streamer.health()["trading_session_counts"] == {}


def test_trading_session_counts_tallies_every_label_seen():
    streamer, box = _mk_streamer()
    ts_ms = int(box["t"] * 1000)
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 1, trading_session="RTH"))
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 1, trading_session="RTH"))
    streamer._on_message("tick", _FakeTick(ts_ms, 495.0, 1, trading_session="ATH"))
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 1))   # no label at all -- counts as None
    streamer._on_message("quote", _FakeQuote(ts_ms, bids=[_FakeBookLevel(499.9, 1)],
                                              asks=[_FakeBookLevel(500.1, 1)],
                                              trading_session="RTH"))

    counts = streamer.health()["trading_session_counts"]
    assert counts["RTH"] == 3      # 2 ticks + 1 quote
    assert counts["ATH"] == 1
    assert counts[None] == 1
    # a single read settles the real regular-hours label instead of guessing again
    assert max(counts, key=counts.get) == "RTH"


def test_reconcile_flags_mismatch_and_confirms_match():
    streamer, box = _mk_streamer()
    t0 = int(_epoch(2026, 1, 5, 10, 0, 1) * 1000)
    t1 = int(_epoch(2026, 1, 5, 10, 0, 30) * 1000)
    streamer._on_message("tick", _FakeTick(t0, 500.0, 100, trading_session="RTH"))
    streamer._on_message("tick", _FakeTick(t1, 501.0, 50, trading_session="RTH"))

    cur = streamer.current_bar("1m")
    matching = {"time": cur["time"], "open": 500.0, "high": 501.0, "low": 500.0,
                "close": 501.0, "volume": 150.0}
    r_ok = streamer.reconcile("1m", matching)
    assert r_ok["ok"] is True and r_ok["mismatch"] is False

    mismatched = dict(matching, close=510.0, volume=999.0)
    r_bad = streamer.reconcile("1m", mismatched)
    assert r_bad["ok"] is True and r_bad["mismatch"] is True
    assert set(r_bad["mismatch_fields"]) >= {"close", "volume"}

    missing = {"time": cur["time"] - 3600, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    r_missing = streamer.reconcile("1m", missing)
    assert r_missing["ok"] is False and r_missing["reason"] == "no_stream_bar"

    assert streamer.reconcile("bogus_tf", matching)["ok"] is False
    assert streamer.reconcile("1m", None)["ok"] is False
    assert streamer.reconcile("1m", {"open": 1})["ok"] is False   # no "time" key


def test_accessors_never_raise_on_fresh_instance():
    streamer, box = _mk_streamer()
    assert streamer.last_trade() is None
    assert streamer.last_quote() is None
    assert streamer.current_bar("1m") is None
    assert streamer.current_bar("bogus") is None
    assert streamer.closed_bar("5m") is None
    h = streamer.health()
    assert h["connected"] is False and h["fresh"] is False
    assert streamer.is_fresh() is False
    r = streamer.reconcile("1m", {"time": 0, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})
    assert r["ok"] is False and r["reason"] == "no_stream_bar"


def test_on_message_never_raises_on_malformed_payloads():
    streamer, box = _mk_streamer()
    ts_ms = int(box["t"] * 1000)
    bad = [
        ("tick", None), ("tick", object()), ("tick", {"nope": 1}),
        ("quote", None), ("quote", object()),
        ("snapshot", None), ("snapshot", object()),
        ("unknown-topic", {"whatever": 1}),
        ("tick", _FakeTick(ts_ms, None, "1")),          # price None -- must be skipped
        ("tick", _FakeTick(ts_ms, "500", "not-a-number")),   # bad volume string
    ]
    for topic, payload in bad:
        streamer._on_message(topic, payload)   # must never raise

    # still fully usable afterward
    streamer._on_message("tick", _FakeTick(ts_ms, 500.0, 1, trading_session="RTH"))
    assert streamer.current_bar("1m")["close"] == 500.0


# ── item A (2026-09-25): SDK log flood mitigation ────────────────────────────────────────
def test_dedup_log_filter_suppresses_within_window_then_tags_repeat_count():
    box = {"t": 1000.0}
    f = S._DedupLogFilter(window_seconds=60.0, clock=lambda: box["t"])

    def _rec(msg):
        return logging.LogRecord("webull.data", logging.ERROR, __file__, 1, msg, None, None)

    r1 = _rec("boom")
    assert f.filter(r1) is True         # first occurrence always allowed
    box["t"] += 1
    assert f.filter(_rec("boom")) is False    # repeat within the window: suppressed
    box["t"] += 1
    assert f.filter(_rec("boom")) is False    # a second repeat: still suppressed

    box["t"] += 61   # past the 60s window
    r4 = _rec("boom")
    assert f.filter(r4) is True
    assert r4.getMessage() == "boom (repeated 2 times)"

    # a fresh message right after must NOT carry the previous message's tag
    r5 = _rec("boom")
    box["t"] += 1
    assert f.filter(r5) is False   # immediately inside r4's own new window
    # a DIFFERENT message is never suppressed by another message's state
    assert f.filter(_rec("something else")) is True


def test_dedup_log_filter_never_raises_on_a_record_with_percent_args():
    box = {"t": 0.0}
    f = S._DedupLogFilter(window_seconds=60.0, clock=lambda: box["t"])
    rec = logging.LogRecord("webull.data", logging.ERROR, __file__, 1,
                            "exception:loop ack code: %s, msg: %s", (1, "Protocol not supported"),
                            None)
    assert f.filter(rec) is True
    assert rec.getMessage() == "exception:loop ack code: 1, msg: Protocol not supported"
    box["t"] += 1
    rec2 = logging.LogRecord("webull.data", logging.ERROR, __file__, 1,
                             "exception:loop ack code: %s, msg: %s", (1, "Protocol not supported"),
                             None)
    assert f.filter(rec2) is False   # same formatted message, still inside the window
    box["t"] += 61
    rec3 = logging.LogRecord("webull.data", logging.ERROR, __file__, 1,
                             "exception:loop ack code: %s, msg: %s", (1, "Protocol not supported"),
                             None)
    assert f.filter(rec3) is True
    # the %-args must still format correctly even after the '(repeated N times)' suffix
    # was appended to record.msg (the raw format string), not to the formatted message
    assert rec3.getMessage() == ("exception:loop ack code: 1, msg: Protocol not supported "
                                 "(repeated 1 times)")


def test_configure_sdk_loggers_is_idempotent():
    logging.getLogger("webull.data").handlers.clear()
    logging.getLogger("webull.core").handlers.clear()
    S._SDK_LOG_SETUP_DONE = False
    try:
        S._configure_sdk_loggers()
        S._configure_sdk_loggers()   # a second call must never add a second handler
        S._configure_sdk_loggers()
        for name in ("webull.data", "webull.core"):
            logger = logging.getLogger(name)
            assert len(logger.handlers) == 1
            assert isinstance(logger.handlers[0], logging.StreamHandler)
            assert logger.level == logging.WARNING
            assert logger.propagate is False
    finally:
        S._SDK_LOG_SETUP_DONE = True   # restore: the first real call already did this


class _FakeSdkStreamingClient:
    """Fake webull.data.data_streaming_client.DataStreamingClient, close enough to
    exercise _connect_once's fix: its OWN _init_logger (unless overridden -- exactly
    the override _connect_once now applies) adds a new handler to 'webull.data' every
    time it is called, mirroring the installed SDK's real quotes_client.py:
    connect_and_loop_forever -> self._init_logger(True, None) -> ADDS a handler (see
    module docstring's item A). connect_and_loop_start also reproduces the exact
    dropped-argument bug (ITS OWN logger_enable argument is ignored; _init_logger is
    always invoked with (True, None) regardless), and calls on_connect_success
    synchronously so the test never waits on the real 20s timeout."""
    instances = []

    def __init__(self, app_key, app_secret, region, session_id, tls_enable=True):
        self.app_key, self.app_secret, self.region = app_key, app_secret, region
        self.session_id = session_id
        self.api_client = object()
        self.on_connect_success = None
        self.on_quotes_message = None
        self.token_dir = None
        _FakeSdkStreamingClient.instances.append(self)

    def _init_logger(self, logger_enable, customer_logger):
        logging.getLogger("webull.data").addHandler(logging.StreamHandler())

    def set_token_dir(self, path):
        self.token_dir = path

    def connect_and_loop_start(self, timeout, logger_enable):
        self._init_logger(True, None)   # the SDK's own dropped-argument bug, reproduced
        if self.on_connect_success:
            self.on_connect_success(self, self.api_client, self.session_id)

    def loop_stop(self):
        pass

    def disconnect(self):
        pass


class _FakeMarketDataStreaming:
    def __init__(self, api_client):
        self.api_client = api_client

    def subscribe(self, session_id, symbols, market, topics):
        return types.SimpleNamespace(status_code=200)


def _install_fake_webull_sdk(monkeypatch, client_cls):
    """Injects a minimal fake 'webull.data.data_streaming_client'/
    'webull.data.quotes.market_streaming_data' package tree into sys.modules so
    _connect_once's real `from webull.data... import ...` statements succeed. The
    real SDK is not importable in this test environment and the network is blocked
    (tests/conftest.py's live-system guard) -- this is the only way to exercise
    _connect_once ITSELF (not a substitute for it)."""
    pkg_webull = types.ModuleType("webull")
    pkg_data = types.ModuleType("webull.data")
    mod_dsc = types.ModuleType("webull.data.data_streaming_client")
    mod_dsc.DataStreamingClient = client_cls
    pkg_quotes = types.ModuleType("webull.data.quotes")
    mod_mds = types.ModuleType("webull.data.quotes.market_streaming_data")
    mod_mds.MarketDataStreaming = _FakeMarketDataStreaming

    for name, mod in (("webull", pkg_webull), ("webull.data", pkg_data),
                     ("webull.data.data_streaming_client", mod_dsc),
                     ("webull.data.quotes", pkg_quotes),
                     ("webull.data.quotes.market_streaming_data", mod_mds)):
        monkeypatch.setitem(sys.modules, name, mod)


def test_connect_once_disables_sdk_logger_setup_and_caps_handlers(tmp_path, monkeypatch):
    logging.getLogger("webull.data").handlers.clear()
    logging.getLogger("webull.core").handlers.clear()
    S._SDK_LOG_SETUP_DONE = False
    _FakeSdkStreamingClient.instances = []

    _install_fake_webull_sdk(monkeypatch, _FakeSdkStreamingClient)
    monkeypatch.setattr(S, "load_keys",
                        lambda path=None: {"app_key": "k", "app_secret": "s", "region": "us"})

    streamer = S.WebullBarStreamer(symbols=["QQQ"], token_dir=str(tmp_path / "token"))
    # our OWN belt-and-braces handler must already be in place right after
    # construction (_configure_sdk_loggers is called from __init__).
    assert len(logging.getLogger("webull.data").handlers) == 1

    clients = [streamer._connect_once() for _ in range(4)]   # simulate several reconnects

    assert len({id(c) for c in clients}) == 4, "expected a genuinely new client each time"
    for c in clients:
        # the override was actually applied to THIS instance (shadowing the class's
        # own _init_logger method), not merely present on the class
        assert "_init_logger" in c.__dict__
    handlers = logging.getLogger("webull.data").handlers
    assert len(handlers) == 1, (
        "the SDK's own _init_logger must never add a handler once _connect_once's "
        "per-instance override is applied -- a regression here would grow this by "
        "one for every reconnect, exactly like the overnight log flood")
    assert isinstance(handlers[0], logging.StreamHandler)


def test_sdk_logger_cap_reasserts_after_later_sdk_handlers():
    """TradeClient/DataClient constructors add their own handlers to 'webull.core' long
    after the streamer's first setup; every later _configure_sdk_loggers call (each
    watchdog pass) must prune them back to our single marked handler."""
    import logging as _logging
    S._configure_sdk_loggers()
    core = _logging.getLogger("webull.core")

    class _Closable(_logging.Handler):
        closed = False
        def emit(self, record):
            pass
        def close(self):
            type(self).closed = True
            super().close()

    extra_stream = _logging.StreamHandler()
    extra_file = _Closable()
    core.addHandler(extra_stream)
    core.addHandler(extra_file)
    assert len(core.handlers) == 3

    S._configure_sdk_loggers()
    assert len(core.handlers) == 1
    assert getattr(core.handlers[0], S._SDK_HANDLER_MARK, False)
    assert _Closable.closed is True
    assert core.level == _logging.WARNING and core.propagate is False

    S._configure_sdk_loggers()           # idempotent: still exactly one of ours
    assert len(core.handlers) == 1


# ── item 10: bar-close hand-off (WEBULL_PAPER_TODO.md item 10, 2026-09-25) ───────────────
# api/cloud_signal.py (a separate OS process) sees these via
# api.webull_stream.read_closed_bar_handoff / stream_bar_is_usable in
# api/cloud_signal_stream.py -- that module's own tests cover the consumer side
# (freshness/market-hours/missing-tick gating, shadow comparison, the owner flag).
# Everything here is the PRODUCER: next_handoff_bar's pure gating, the atomic file
# write, and WebullBarStreamer's own wiring (_handoff_pass, the reconnect reset).
def test_next_handoff_bar_pure_gating():
    grace = 1.5
    assert S.next_handoff_bar(None, 5, None, grace_seconds=grace) == (None, None)

    bar = {"time": 1000, "age": 2.0}
    # bars_since_connect counts THIS bar too -- 1 means it IS the first close after a
    # (re)connect, which must never publish (constraint 4).
    assert S.next_handoff_bar(bar, 1, None, grace_seconds=grace) == (None, None)

    not_yet = {"time": 1300, "age": 0.5}      # closed, but grace hasn't cleared
    assert S.next_handoff_bar(not_yet, 2, None, grace_seconds=grace) == (None, None)

    ready = {"time": 1300, "age": 1.6}        # closed AND settled
    out_bar, last = S.next_handoff_bar(ready, 2, None, grace_seconds=grace)
    assert out_bar == ready and last == 1300

    # the same bar, already published, must never publish again
    assert S.next_handoff_bar(ready, 2, 1300, grace_seconds=grace) == (None, 1300)

    later = {"time": 1600, "age": 1.6}        # a LATER bar publishes again
    out_bar2, last2 = S.next_handoff_bar(later, 3, 1300, grace_seconds=grace)
    assert out_bar2 == later and last2 == 1600


def test_write_closed_bar_handoff_is_atomic_and_leaves_no_tmp_file(tmp_path, monkeypatch):
    import glob
    import json as _json
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    bar = {"time": 1000, "open": 500.0, "high": 501.0, "low": 499.0, "close": 500.5, "volume": 120.0}

    payload = S.write_closed_bar_handoff(bar, timeframe="5m",
                                         extra={"fresh": True, "connected": True})

    path = S.closed_bar_handoff_path("5m", home=str(tmp_path))
    with open(path, encoding="utf-8") as f:
        on_disk = _json.load(f)
    assert on_disk == payload
    assert on_disk["time"] == 1000 and on_disk["close"] == 500.5
    assert on_disk["fresh"] is True and on_disk["connected"] is True
    assert glob.glob(str(tmp_path / "ohlc_stream" / "*.tmp")) == [], (
        "no tmp file should survive a successful publish")

    # a second publish (the next completed bar) must cleanly replace it -- never leave
    # two files or a reader race between them.
    S.write_closed_bar_handoff(dict(bar, time=1300, close=502.0), timeframe="5m",
                               extra={"fresh": True, "connected": True})
    with open(path, encoding="utf-8") as f:
        on_disk2 = _json.load(f)
    assert on_disk2["time"] == 1300 and on_disk2["close"] == 502.0


def test_handoff_pass_never_publishes_the_first_bar_after_connect(tmp_path, monkeypatch):
    """The bar closed right after (re)connecting may be missing the ticks before the
    connection settled -- next_handoff_bar's own test covers the pure gate; this proves
    WebullBarStreamer's _handoff_pass actually wires it (no file appears)."""
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    streamer, box = _mk_streamer()
    streamer._client = object()      # health().connected -- see test_health_distinguishes...
    path = S.closed_bar_handoff_path("5m", home=str(tmp_path))
    t30 = _epoch(2026, 1, 5, 9, 30, 0)
    t35 = _epoch(2026, 1, 5, 9, 35, 0)

    streamer._on_message("tick", _FakeTick(int(t30 * 1000), 500.0, 1, trading_session="RTH"))
    streamer._on_message("tick", _FakeTick(int(t35 * 1000), 510.0, 1, trading_session="RTH"))
    assert streamer.bars_closed_since_connect("5m") == 1

    box["t"] = t35 + 30.0             # comfortably past any grace
    streamer._handoff_pass("5m")

    assert not os.path.exists(path), "the first bar closed after connect must never publish"


def test_handoff_pass_publishes_the_second_bar_only_once_grace_clears(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path))
    streamer, box = _mk_streamer()
    streamer._client = object()
    path = S.closed_bar_handoff_path("5m", home=str(tmp_path))
    t30 = _epoch(2026, 1, 5, 9, 30, 0)
    t35 = _epoch(2026, 1, 5, 9, 35, 0)
    t40 = _epoch(2026, 1, 5, 9, 40, 0)

    streamer._on_message("tick", _FakeTick(int(t30 * 1000), 500.0, 1, trading_session="RTH"))
    streamer._on_message("tick", _FakeTick(int(t35 * 1000), 510.0, 1, trading_session="RTH"))
    streamer._on_message("tick", _FakeTick(int(t40 * 1000), 520.0, 1, trading_session="RTH"))
    assert streamer.bars_closed_since_connect("5m") == 2   # the 9:35 bar just closed, close=510

    box["t"] = t40 + 0.5              # inside the default 1.5s grace
    streamer._handoff_pass("5m")
    assert not os.path.exists(path), "must not publish before grace clears -- 'not read before complete'"

    box["t"] = t40 + 2.0              # past grace
    streamer._handoff_pass("5m")
    assert os.path.exists(path), "must publish within the grace once it clears"

    import json as _json
    with open(path, encoding="utf-8") as f:
        published = _json.load(f)
    assert published["time"] == t35 and published["close"] == 510.0
    assert published["fresh"] is True and published["connected"] is True
    assert published["bars_since_connect"] == 2

    # a repeat pass with nothing new must not rewrite/republish
    mtime_before = os.path.getmtime(path)
    streamer._handoff_pass("5m")
    assert os.path.getmtime(path) == mtime_before


def test_connect_once_resets_bars_closed_since_connect(monkeypatch):
    _install_fake_webull_sdk(monkeypatch, _FakeSdkStreamingClient)
    monkeypatch.setattr(S, "load_keys",
                        lambda path=None: {"app_key": "k", "app_secret": "s", "region": "us"})
    streamer, box = _mk_streamer()
    t30 = _epoch(2026, 1, 5, 9, 30, 0)
    t35 = _epoch(2026, 1, 5, 9, 35, 0)
    streamer._on_message("tick", _FakeTick(int(t30 * 1000), 500.0, 1, trading_session="RTH"))
    streamer._on_message("tick", _FakeTick(int(t35 * 1000), 510.0, 1, trading_session="RTH"))
    assert streamer.bars_closed_since_connect("5m") == 1

    streamer._connect_once()   # simulates a reconnect settling

    assert streamer.bars_closed_since_connect("5m") == 0
    assert streamer.bars_closed_since_connect("1m") == 0
