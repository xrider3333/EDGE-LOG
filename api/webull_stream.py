"""api/webull_stream.py -- Webull Level 1 STREAMING -> 1-minute OHLCV bar builder.

WHY THIS EXISTS. api/cloud_signal.py already pulls QQQ bars over Webull's HTTP
`get_history_bar` endpoint every ~30s (see `_fetch_webull` there) -- that path is
confirmed entitled on the owner's key (free "Nasdaq Basic non-display" tier, per its
own docstring, 2026-09-09). This module is a DIFFERENT, lower-latency path: it opens
the Webull OpenAPI's MQTT **streaming** connection (Level 1 quotes -- the "Free Level
1 Streaming Quotes for U.S. Market" tier Webull's OpenAPI docs advertise) and builds
1-minute bars itself from the individual TICK/SNAPSHOT pushes, instead of waiting on
Webull's own minute-bar aggregation and polling for it.

ENTITLEMENT (verified 2026-09-13, market closed / Sunday -- see the session report):
MQTT connect succeeded, and the HTTP subscribe ack for QQQ (category US_STOCK,
sub_types [TICK, SNAPSHOT]) returned 200. No live ticks could be observed (market
closed), so the FEED CONTENTS below are inferred from the installed SDK's own decoder
source (webull/data/quotes/subscribe/{tick,snapshot}_result.py), not from an observed
message, and should be re-checked once the market is open Monday.
  - TICK: per-print price + volume (share count of that one print) + side + exchange
    timestamp. Volume here is INCREMENTAL -- each tick is one trade, so tick volumes
    sum directly into a bar's volume.
  - SNAPSHOT: price + open/high/low + a `volume` field that is (per Webull's own
    snapshot semantics, matching the HTTP get_snapshot shape) the day's CUMULATIVE
    session volume, not a per-print size. A bar's volume from snapshot-only pushes has
    to be reconstructed as the DELTA between consecutive cumulative readings.
  - QUOTE: bid/ask (top of book) only -- no last-trade price, not used for bars here.
This module accepts either shape (see `QuoteUpdate`) so it works whichever sub_type
actually arrives once the market re-opens; `_volume_delta()` is the single place that
decides incremental-vs-cumulative handling, and is unit-tested for both.

BAR STAMPING (deliberately explicit -- EDGELOG has shipped a bar-END stamping bug
before, see memory note "Tag at the SIGNAL bar"): every bar's `time` column is the
epoch second of the bar's OPENING instant, exactly like the existing on-disk cache
(`api/cloud_signal.py` / `tools/qqq_paper.py`, whose `_to_epoch_frame` stamps
yfinance's bar-start index the same way). `bucket_epoch()` floors an event's epoch
seconds to the minute -- this lands on the correct US/Eastern minute start without
ever converting timezones, because US/Eastern's UTC offset is always a whole number
of hours (no fractional-hour offset, pre- or post-DST), so a UTC-second minute
boundary and an ET-wall-clock minute boundary are the same instant. Tested explicitly
in tests/test_webull_stream.py against zoneinfo conversions on both sides of a DST
change, not just asserted.

SCHEMA / ON-DISK PATH. Same 6-column epoch schema api/cloud_signal.py's cache uses
(`time`(UTC epoch s, bar start), `open`, `high`, `low`, `close`, `volume`), so a
future reader can treat this cache exactly like that one -- but written to a
SEPARATE path (`<EDGELOG_HOME>/ohlc_stream/QQQ_<tf>.csv`, not
`<EDGELOG_HOME>/ohlc/QQQ_<tf>.csv`) so this module never races the other agent's
writer of the existing cache. `edgelog_home()` is intentionally duplicated (not
imported from api/cloud_signal.py) to keep this module free of any import-time
dependency on a file another session may be editing concurrently.

NO ORDER CODE. This module only ever opens a market-data (quotes) streaming session.
It never imports webull.trade.*, never touches an account/order endpoint.

SECRETS. Same convention as api/webull_sync.py: credentials load from
C:\\EdgeLog\\webull_keys.json (EDGELOG_WEBULL_KEYS to override), the SDK's 2FA token
caches in C:\\EdgeLog\\webull_token\\ (EDGELOG_WEBULL_TOKEN_DIR to override). Never
printed, logged, or written anywhere else. The SDK's own credential-dumping loggers
("webull.core.client", the streaming client's default file/stdout logger) are
silenced the same way api/webull_sync.py already silences them.

CLI
  python -m api.webull_stream --once      one connect/subscribe/idle cycle, print
                                           what came in, exit (manual smoke test)
  python -m api.webull_stream --run       run the resilient streamer until Ctrl+C
"""
import argparse
import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

TZ = "US/Eastern"                      # convention only; bucketing itself is tz-free (see module docstring)
SCHEMA_COLUMNS = ["time", "open", "high", "low", "close", "volume"]
DEFAULT_SYMBOLS = ["QQQ"]
DEFAULT_BAR_SECONDS = 60

WEBULL_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json")
WEBULL_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR", r"C:\EdgeLog\webull_token")
_PLACEHOLDERS = ("", "PASTE_APP_KEY_HERE", "PASTE_APP_SECRET_HERE")

# Same credential-leak mitigation api/webull_sync.py applies: on any API error the SDK's
# client logger dumps the full signed request (x-app-key / x-access-token) at ERROR
# level, and the streaming client's own logger writes to stdout + a local file by
# default. Silence both proactively, at import time, before any request is ever made.
logging.getLogger("webull.core.client").setLevel(logging.CRITICAL)
logging.getLogger("webull.core").addHandler(logging.NullHandler())
logging.getLogger("webull.data").addHandler(logging.NullHandler())


def edgelog_home():
    h = os.environ.get("EDGELOG_HOME")
    if h:
        return h
    if os.name == "nt":
        return r"C:\EdgeLog"
    return os.path.expanduser("~/edgelog")


def stream_cache_path(timeframe="1m", home=None):
    home = home or edgelog_home()
    return os.path.join(home, "ohlc_stream", f"QQQ_{timeframe}.csv")


def load_keys(keys_path=WEBULL_KEYS):
    """Same shape as api/webull_sync.load_keys -- {app_key, app_secret, region} or
    None if unconfigured. Duplicated (not imported) to keep this module standalone."""
    if not os.path.exists(keys_path):
        return None
    try:
        cfg = json.load(open(keys_path, encoding="utf-8"))
    except Exception:
        return None
    ak = (cfg.get("app_key") or "").strip()
    sk = (cfg.get("app_secret") or "").strip()
    if ak in _PLACEHOLDERS or sk in _PLACEHOLDERS:
        return None
    return {"app_key": ak, "app_secret": sk, "region": (cfg.get("region") or "us").strip().lower()}


# ── bucketing ────────────────────────────────────────────────────────────────
def bucket_epoch(event_epoch_seconds, bar_seconds=DEFAULT_BAR_SECONDS):
    """Floor an event's epoch seconds to its bar's START epoch. See module docstring
    for why this needs no timezone conversion to land on the correct US/Eastern
    minute boundary."""
    return int(event_epoch_seconds // bar_seconds) * bar_seconds


# ── normalized feed event ───────────────────────────────────────────────────
@dataclass
class QuoteUpdate:
    """One decoded Level 1 push, already reduced to what the bar builder needs.
    Exactly one of trade_volume / cum_volume should normally be set (TICK gives the
    former, SNAPSHOT the latter); both may be absent (e.g. a QUOTE bid/ask push with
    no trade), in which case the update still moves close/high/low via `price` if
    given, but contributes zero volume."""
    symbol: str
    epoch: float            # exchange event time, UTC epoch seconds (fractional ok)
    price: Optional[float] = None
    trade_volume: Optional[float] = None   # incremental (e.g. TICK print size)
    cum_volume: Optional[float] = None     # cumulative session volume (e.g. SNAPSHOT)


# ── decoders: SDK result objects -> QuoteUpdate (pure, unit-testable with fakes) ──
def normalize_tick(symbol, tick_result):
    """webull.data.quotes.subscribe.tick_result.TickResult -> QuoteUpdate.
    Accepts any object with the same .basic.timestamp/.price/.volume shape (tests
    pass a lightweight fake, not the real protobuf-backed class)."""
    basic = tick_result.get_basic() if hasattr(tick_result, "get_basic") else tick_result.basic
    ts_ms = basic.get_timestmap() if hasattr(basic, "get_timestmap") else basic.timestamp
    price = tick_result.get_price() if hasattr(tick_result, "get_price") else tick_result.price
    vol = tick_result.get_volume() if hasattr(tick_result, "get_volume") else tick_result.volume
    return QuoteUpdate(symbol=symbol, epoch=float(ts_ms) / 1000.0,
                        price=float(price) if price is not None else None,
                        trade_volume=float(vol) if vol is not None else None)


def normalize_snapshot(symbol, snapshot_result):
    """webull.data.quotes.subscribe.snapshot_result.SnapshotResult -> QuoteUpdate."""
    basic = snapshot_result.get_basic() if hasattr(snapshot_result, "get_basic") else snapshot_result.basic
    ts_ms = basic.get_timestmap() if hasattr(basic, "get_timestmap") else basic.timestamp
    price = snapshot_result.price
    vol = snapshot_result.volume
    return QuoteUpdate(symbol=symbol, epoch=float(ts_ms) / 1000.0,
                        price=float(price) if price is not None else None,
                        cum_volume=float(vol) if vol is not None else None)


# ── bar builder (pure; no network, no SDK, fully unit-testable) ─────────────
class BarBuilder:
    """Turns a stream of QuoteUpdate into closed 1-minute OHLCV bars.

    Reconnect-safety: a bucket, once closed (emitted via ingest()'s return value or
    flush()), is remembered in `_closed_buckets` and never re-opened -- a late/replayed
    update for it is dropped and counted in stats, not re-merged in memory. The on-disk
    writer (`merge_and_write`) is the second, independent line of defense (dedupes by
    `time`, keep='last') so a caller that re-feeds a few overlapping updates after a
    reconnect still can't produce duplicate rows on disk.
    """

    def __init__(self, bar_seconds=DEFAULT_BAR_SECONDS):
        self.bar_seconds = bar_seconds
        self._bars = {}              # symbol -> in-progress bar dict
        self._last_cum_volume = {}   # symbol -> last cumulative volume observed
        self._closed_buckets = {}    # symbol -> set of already-emitted bucket epochs
        self.stats = {"updates_seen": 0, "out_of_order_dropped": 0, "bars_closed": 0}

    def _volume_delta(self, symbol, update):
        if update.trade_volume is not None:
            return float(update.trade_volume)
        if update.cum_volume is not None:
            last = self._last_cum_volume.get(symbol)
            self._last_cum_volume[symbol] = update.cum_volume
            if last is None:
                return 0.0   # first observation: no baseline yet, don't count a jump
            delta = update.cum_volume - last
            # a lower cumulative reading than last time means a session/day rollover,
            # not a real negative trade -- clamp instead of corrupting the bar.
            return delta if delta >= 0 else 0.0
        return 0.0

    def _new_bar(self, bucket, price):
        px = price if price is not None else float("nan")
        return {"time": bucket, "open": px, "high": px, "low": px, "close": px, "volume": 0.0}

    def ingest(self, update: QuoteUpdate):
        """Feed one update. Returns a list (0 or 1 normally, but never assume exactly
        one) of newly-CLOSED bar dicts for this symbol."""
        self.stats["updates_seen"] += 1
        symbol = update.symbol
        bucket = bucket_epoch(update.epoch, self.bar_seconds)
        vol_delta = self._volume_delta(symbol, update)
        cur = self._bars.get(symbol)
        closed = []

        if cur is None:
            if bucket in self._closed_buckets.get(symbol, ()):
                # late arrival for a bucket already flushed/closed with no bar
                # currently open (e.g. right after flush()) -- drop, don't reopen it
                self.stats["out_of_order_dropped"] += 1
                return closed
            self._bars[symbol] = self._new_bar(bucket, update.price)
            self._bars[symbol]["volume"] += vol_delta
            return closed

        if bucket == cur["time"]:
            if update.price is not None:
                cur["high"] = max(cur["high"], update.price)
                cur["low"] = min(cur["low"], update.price)
                cur["close"] = update.price
            cur["volume"] += vol_delta
            return closed

        if bucket > cur["time"]:
            # roll the current bar closed (a gap to the new bucket, if any, is left
            # as a gap -- no synthesized empty bars for quiet minutes)
            closed.append(dict(cur))
            self._closed_buckets.setdefault(symbol, set()).add(cur["time"])
            self.stats["bars_closed"] += 1
            self._bars[symbol] = self._new_bar(bucket, update.price)
            self._bars[symbol]["volume"] += vol_delta
            return closed

        # bucket < cur["time"]: late / out-of-order for an earlier minute.
        self.stats["out_of_order_dropped"] += 1
        return closed

    def flush(self, symbol=None):
        """Force-close in-progress bar(s) (clean shutdown / staleness reconnect).
        Returns the list of closed bar dicts. The flushed bucket is marked closed so
        a stray late update for it afterward is dropped, not silently reopened."""
        symbols = [symbol] if symbol else list(self._bars.keys())
        closed = []
        for sym in symbols:
            cur = self._bars.pop(sym, None)
            if cur is not None:
                closed.append(dict(cur))
                self._closed_buckets.setdefault(sym, set()).add(cur["time"])
                self.stats["bars_closed"] += 1
        return closed


# ── on-disk cache: atomic, dedupe-on-merge (same pattern as api/cloud_signal.py) ──
def merge_and_write(bar_rows, timeframe="1m", home=None):
    """Merge new bar dicts into the on-disk stream cache and write atomically.
    Idempotent: writing the same (or an overlapping) set of rows twice never
    produces duplicate `time` rows -- last write wins per bucket, matching
    api/cloud_signal.py's fetch_and_merge / tools/qqq_paper.py's sync_bars."""
    import pandas as pd
    path = stream_cache_path(timeframe, home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=SCHEMA_COLUMNS)
    fresh = pd.DataFrame(bar_rows, columns=SCHEMA_COLUMNS) if bar_rows else pd.DataFrame(columns=SCHEMA_COLUMNS)
    frames = [df for df in (old, fresh) if len(df)]
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SCHEMA_COLUMNS)
    if len(merged):
        merged = merged.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
    tmp = path + ".tmp"
    merged.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return merged


# ── staleness / market-hours helpers (pure) ─────────────────────────────────
def is_stale(last_message_epoch, now_epoch, stale_after_seconds):
    if last_message_epoch is None:
        return False   # never connected yet is a connect problem, not staleness
    return (now_epoch - last_message_epoch) > stale_after_seconds


def next_backoff(attempt, base=1.0, cap=60.0):
    """Exponential backoff, capped -- attempt is 0-indexed retry count."""
    return min(cap, base * (2 ** attempt))


# ── resilient live streamer (thin orchestration; the SDK only shows up here) ──
class WebullBarStreamer:
    """Owns the MQTT connection lifecycle: connect, subscribe, decode pushes into
    BarBuilder, periodically persist closed bars, reconnect with backoff on
    disconnect/staleness, clean shutdown. Kept deliberately thin -- all the logic
    worth unit-testing lives in the pure functions/classes above; this class is
    exercised with the real SDK mocked out (see tests/test_webull_stream.py)."""

    def __init__(self, symbols=None, bar_seconds=DEFAULT_BAR_SECONDS,
                 keys_path=WEBULL_KEYS, token_dir=WEBULL_TOKEN_DIR,
                 stale_after_seconds=90, backoff_base=1.0, backoff_cap=60.0,
                 flush_every_seconds=10, log=print):
        self.symbols = symbols or list(DEFAULT_SYMBOLS)
        self.bar_seconds = bar_seconds
        self.keys_path = keys_path
        self.token_dir = token_dir
        self.stale_after_seconds = stale_after_seconds
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.flush_every_seconds = flush_every_seconds
        self.log = log

        self.builder = BarBuilder(bar_seconds=bar_seconds)
        self._pending_rows = []
        self._last_message_epoch = None
        self._stop = threading.Event()
        self._client = None
        self._watchdog_thread = None
        self._lock = threading.Lock()

    # -- decode + feed (called from the SDK's own callback thread) --
    def _on_message(self, topic, payload):
        self._last_message_epoch = time.time()
        update = None
        try:
            if topic == "tick" or hasattr(payload, "get_volume") and hasattr(payload, "time"):
                update = normalize_tick(self.symbols[0], payload)
            elif topic == "snapshot" or hasattr(payload, "get_last_trade_time"):
                update = normalize_snapshot(self.symbols[0], payload)
        except Exception as e:
            self.log(f"[webull-stream] decode failed on topic={topic}: {type(e).__name__}: {e}")
            return
        if update is None or update.price is None:
            return
        with self._lock:
            closed = self.builder.ingest(update)
            self._pending_rows.extend(closed)

    def _flush_pending(self):
        with self._lock:
            rows = self._pending_rows
            self._pending_rows = []
        if rows:
            merge_and_write(rows, timeframe=f"{self.bar_seconds // 60}m" if self.bar_seconds >= 60 else "1m")
        return rows

    # -- connection lifecycle --
    def _connect_once(self):
        """One connect+subscribe attempt. Returns the live client, or raises."""
        from webull.data.data_streaming_client import DataStreamingClient
        from webull.data.quotes.market_streaming_data import MarketDataStreaming

        keys = load_keys(self.keys_path)
        if not keys:
            raise RuntimeError("webull_keys.json missing/unconfigured -- cannot stream")

        session_id = uuid.uuid4().hex
        connected = threading.Event()

        def on_connect(client, api_client, sess_id):
            connected.set()

        client = DataStreamingClient(keys["app_key"], keys["app_secret"], keys["region"],
                                     session_id, tls_enable=True)
        client.on_connect_success = on_connect
        client.on_quotes_message = lambda c, topic, payload: self._on_message(topic, payload)
        os.makedirs(self.token_dir, exist_ok=True)
        client.set_token_dir(self.token_dir)

        client.connect_and_loop_start(timeout=1, logger_enable=False)
        if not connected.wait(timeout=20):
            try:
                client.loop_stop(); client.disconnect()
            except Exception:
                pass
            raise RuntimeError("MQTT connect timed out")

        mds = MarketDataStreaming(client.api_client)
        resp = mds.subscribe(session_id, self.symbols, "US_STOCK", ["TICK", "SNAPSHOT"])
        status = getattr(resp, "status_code", None)
        if status != 200:
            try:
                client.loop_stop(); client.disconnect()
            except Exception:
                pass
            raise RuntimeError(f"subscribe rejected, status={status}")

        self._last_message_epoch = time.time()   # count connect as "alive" for staleness purposes
        return client

    def _watchdog(self):
        attempt = 0
        while not self._stop.is_set():
            self._stop.wait(self.flush_every_seconds)
            if self._stop.is_set():
                break
            self._flush_pending()
            if is_stale(self._last_message_epoch, time.time(), self.stale_after_seconds):
                self.log(f"[webull-stream] feed stale (> {self.stale_after_seconds}s), reconnecting")
                self._teardown_client()
                delay = next_backoff(attempt, self.backoff_base, self.backoff_cap)
                attempt += 1
                if self._stop.wait(delay):
                    break
                try:
                    self._client = self._connect_once()
                    attempt = 0
                except Exception as e:
                    self.log(f"[webull-stream] reconnect failed: {type(e).__name__}: {e}")
            else:
                attempt = 0

    def _teardown_client(self):
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def start(self):
        self._stop.clear()
        self._client = self._connect_once()
        self._watchdog_thread = threading.Thread(target=self._watchdog, name="webull-stream-watchdog", daemon=True)
        self._watchdog_thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            closed = self.builder.flush()
            self._pending_rows.extend(closed)
        self._flush_pending()
        self._teardown_client()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=5)


def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="connect, subscribe, idle 20s, print stats, exit")
    ap.add_argument("--run", action="store_true", help="run the resilient streamer until Ctrl+C")
    ap.add_argument("--symbol", default="QQQ")
    args = ap.parse_args()

    streamer = WebullBarStreamer(symbols=[args.symbol])
    if args.once:
        streamer.start()
        time.sleep(20)
        streamer.stop()
        print(json.dumps(streamer.builder.stats))
    elif args.run:
        streamer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        streamer.stop()
    else:
        ap.print_help()


if __name__ == "__main__":
    _cli()
