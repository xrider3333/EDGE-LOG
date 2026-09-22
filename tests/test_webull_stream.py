"""Unit tests for api.webull_stream -- Webull Level 1 stream -> 1-minute bar builder.

Everything here runs against BarBuilder / merge_and_write / the pure helpers directly.
No network, no MQTT, no webull SDK import is exercised (the SDK only appears inside
WebullBarStreamer._connect_once, which these tests never call).
"""
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
