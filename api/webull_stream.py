"""api/webull_stream.py -- Webull Level 1 STREAMING -> 1-minute/5-minute OHLCV bar builder,
plus a staleness-aware live-read API (last trade, top-of-book quote, in-progress/closed
bars, health) and a REST reconciliation hook.

WHY THIS EXISTS. api/cloud_signal.py already pulls QQQ bars over Webull's HTTP
`get_history_bar` endpoint every ~30s (see `_fetch_webull` there) -- that path is confirmed
entitled on the owner's key (free "Nasdaq Basic non-display" tier, per its own docstring,
2026-09-09). This module is a DIFFERENT, lower-latency path: it opens the Webull OpenAPI's
MQTT **streaming** connection (Level 1 quotes -- the "Free Level 1 Streaming Quotes for U.S.
Market" tier Webull's OpenAPI docs advertise) and builds bars itself from the individual
TICK/SNAPSHOT pushes, instead of waiting on Webull's own minute-bar aggregation and polling
for it. REST stays authoritative for history; this module is a live front-run layer a caller
can trust incrementally -- or fall back from the moment `health()` says it isn't fresh.

FEED CONTENTS (confirmed live, 2026-09-22 -- supersedes the earlier "inferred from decoder
source, unverified" note; the shapes below are what the SDK's decoders actually hand back):
  - TICK: `.basic` (symbol, instrument_id, `.timestamp` = MS EPOCH, `.trading_session`),
    `.price` (Decimal), `.side` ('B'/...), `.time` ('17:37:25' -- a bare wall-clock STRING
    with no date; NOT used as the event time, `basic.timestamp` is), `.volume` (a STRING,
    the print's own size -- INCREMENTAL, sums directly into a bar's volume).
  - QUOTE: `.bids` / `.asks` -- lists of objects with `.price` / `.size` ATTRIBUTES (not
    dicts, not [price, size] pairs), plus the same `.basic`. Bid/ask only, top-of-book (the
    first entry of each list) is all this module reads. Not fed into any bar -- no trade
    occurred -- but is exactly what `last_quote()` needs, so QUOTE is now subscribed to
    alongside TICK/SNAPSHOT (see `_connect_once`).
  - SNAPSHOT: `.price`/`.volume` (CUMULATIVE session volume, per Webull's snapshot
    semantics, matching the HTTP get_snapshot shape) plus `.open`/`.high`/`.low`/`.close`
    (unused here -- this module derives its own OHLC from the price stream, never trusts a
    single snapshot's self-reported range). DURING EXTENDED HOURS, `.price`/`.volume`/
    `.open`/`.high`/`.low`/`.close` are all None and the live data is in `.ext_price` /
    `.ext_volume` / `.ext_high` / `.ext_low` / `.ext_trade_time` instead -- `normalize_snapshot`
    falls back to `.ext_price`/`.ext_volume` when the regular ones are None. `.ext_trade_time`'s
    own format hasn't been observed, so the epoch still comes from `.basic.timestamp` (always
    present) rather than guessing at a new parse path for a field this module doesn't
    otherwise need. A price that's still None after the ext_* fallback is skipped -- see
    `_on_message`'s `update.price is None` guard -- never written as a hole into a bar.
  This module accepts either TICK or SNAPSHOT shape (see `QuoteUpdate`); `_volume_delta()` is
  the single place that decides incremental-vs-cumulative handling, unit-tested for both.

TRADING SESSION FILTERING (revised 2026-09-22, same day it was first written -- a whitelist
was the first design and was REJECTED before shipping). The live dump showed extended-hours
TICKs carrying `basic.trading_session == 'ATH'`; nobody has yet seen what the field says
during the regular session -- and `trading_session` is a free-form protobuf STRING
(message_pb2 Basic field 4) with no enum anywhere constraining its values. A whitelist
(accept only a guessed regular-session label such as 'RTH') fails catastrophically the
moment that guess is wrong: if the real label turns out to be 'REG' or 'NORMAL' or anything
else, the whitelist silently drops every regular-hours tick -- the builder produces zero
bars while the stream itself still reports perfectly healthy. That is the worst failure
shape available here, so `is_regular_session()` makes the US/Eastern wall clock
(09:30-16:00 ET, weekday) AUTHORITATIVE for inclusion, and a label can only ever REMOVE a
print, never add one: a print is in-session when it is inside the clock window AND its
label (if any) is not one of `KNOWN_EXTENDED_SESSIONS` (a small blacklist seeded with
'ath'/'ovn' plus obvious pre/post spellings, matched case-insensitively). An unknown or
missing label changes nothing -- the clock's answer stands either way. This keeps the
label's power exactly where it earns its keep: a print stamped with a KNOWN extended label
is excluded even when its own timestamp happens to fall inside the clock window (a
holiday/early-close session, an extended print right at the window's edge, etc.).
`WebullBarStreamer` also tallies every distinct `trading_session` value it actually sees
(label -> count, `None` counted as its own bucket) via `health()["trading_session_counts"]`
-- one read of that at the open settles what the real regular-hours label is, rather than
guessing again.

BAR STAMPING (deliberately explicit -- EDGELOG has shipped a bar-END stamping bug before,
see memory note "Tag at the SIGNAL bar"): every bar's `time` column is the epoch second of
the bar's OPENING instant, exactly like the existing on-disk cache (`api/cloud_signal.py` /
`tools/qqq_paper.py`, whose `_to_epoch_frame` stamps yfinance's bar-start index the same
way). `bucket_epoch()` floors an event's epoch seconds to the minute (or 5-minute) -- this
lands on the correct US/Eastern boundary without ever converting timezones, because
US/Eastern's UTC offset is always a whole number of hours (no fractional-hour offset, pre-
or post-DST), so a UTC-second boundary and an ET-wall-clock boundary are the same instant.
Tested explicitly in tests/test_webull_stream.py against zoneinfo conversions on both sides
of a DST change, not just asserted. This module builds BOTH a 1-minute and a 5-minute bar
from the same tick stream (`WebullBarStreamer.builders`, keyed by bar-seconds) -- one
`BarBuilder` instance per timeframe, so a caller can act at either boundary.

SCHEMA / ON-DISK PATH. Same 6-column epoch schema api/cloud_signal.py's cache uses
(`time`(UTC epoch s, bar start), `open`, `high`, `low`, `close`, `volume`), so a future
reader can treat this cache exactly like that one -- but written to a SEPARATE path
(`<EDGELOG_HOME>/ohlc_stream/QQQ_<tf>.csv`, not `<EDGELOG_HOME>/ohlc/QQQ_<tf>.csv`) so this
module never races the other agent's writer of the existing cache. `edgelog_home()` is
intentionally duplicated (not imported from api/cloud_signal.py) to keep this module free of
any import-time dependency on a file another session may be editing concurrently.

LIVE-READ API (new, 2026-09-22). `last_trade()`, `last_quote()`, `current_bar(timeframe)`,
`closed_bar(timeframe)` and `health()` -- every one of them reports the AGE of what it hands
back (`current_bar`'s age is time since that bar OPENED, `closed_bar`'s is time since it
CLOSED -- neither needs BarBuilder's own bar dict to carry any new field). `health()`'s
`fresh` flag is the one a caller should gate on: False whenever the stream isn't
DEMONSTRABLY live (never claims fresh off zero messages), so "stream up but silent"
(`connected` True, `fresh` False) reads differently from "stream down" (`connected` False).
`reconcile(timeframe, rest_bar)` diffs a REST-fetched bar against this module's own bar for
the same period and reports the difference -- REST stays authoritative, this never writes
anything back. All of it reads `self._clock()` (defaults to `time.time`, overridable by the
`clock=` constructor arg) rather than `_connect_once`/`_watchdog`'s own `time.time()` calls,
which are untouched -- this is a narrow, additive seam for the new accessors' tests, not a
change to the connect/subscribe/watchdog/teardown sequence itself.

NO ORDER CODE. This module only ever opens a market-data (quotes) streaming session. It
never imports webull.trade.*, never touches an account/order endpoint.

SECRETS. Same convention as api/webull_sync.py: credentials load from
C:\\EdgeLog\\webull_keys.json (EDGELOG_WEBULL_KEYS to override), the SDK's 2FA token caches
in C:\\EdgeLog\\webull_token\\ (EDGELOG_WEBULL_TOKEN_DIR to override). Never printed, logged,
or written anywhere else. The SDK's own credential-dumping loggers ("webull.core.client",
the streaming client's default file/stdout logger) are silenced the same way
api/webull_sync.py already silences them.

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
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

TZ = "US/Eastern"                      # convention only; bucketing itself is tz-free (see module docstring)
SCHEMA_COLUMNS = ["time", "open", "high", "low", "close", "volume"]
DEFAULT_SYMBOLS = ["QQQ"]
DEFAULT_BAR_SECONDS = 60
EXTRA_BAR_SECONDS = (300,)             # 5-minute, built alongside the 1-minute by default

RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
# Blacklist, not a whitelist -- see module docstring's TRADING SESSION FILTERING for why a
# whitelist was tried and rejected. Only 'ath' is actually confirmed (from a live extended-
# hours dump); the rest are obvious vendor spellings for the same concept, kept so the
# clock isn't doing all the work alone. Matched case-insensitively. An UNKNOWN label is
# deliberately NOT enumerated here -- being absent from this set is exactly what lets the
# clock decide for it, rather than the label excluding it by default.
KNOWN_EXTENDED_SESSIONS = frozenset({
    "ath", "ovn", "pre", "post", "premarket", "postmarket", "pre-market", "post-market",
    "extended", "eth",
})

_TF_SECONDS = {"1m": 60, "5m": 300}
_TF_LABELS = {60: "1m", 300: "5m"}

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


def _seconds_of(timeframe):
    """'1m'/'5m' (or a raw seconds number) -> bar-seconds int, or None if unrecognized."""
    if timeframe in _TF_SECONDS:
        return _TF_SECONDS[timeframe]
    if isinstance(timeframe, (int, float)) and not isinstance(timeframe, bool):
        return int(timeframe)
    return None


def _tf_label(bar_seconds):
    return _TF_LABELS.get(bar_seconds, f"{bar_seconds}s")


# ── trading-session filtering (label-first, clock fallback) ─────────────────
def is_regular_session(trading_session, epoch, tz=TZ):
    """True if an update belongs in an RTH bar. THE CLOCK IS AUTHORITATIVE FOR INCLUSION
    (see module docstring's TRADING SESSION FILTERING for why a whitelist was rejected): a
    print must fall inside the US/Eastern 09:30-16:00 weekday window, full stop -- no label
    can make an out-of-window print count. A label can only ever REMOVE a print from that:
    one matching a KNOWN_EXTENDED_SESSIONS entry (case-insensitive) is excluded even though
    its timestamp lands inside the window. An unknown or missing label never excludes
    anything; it just leaves the clock's answer alone."""
    dt_et = datetime.fromtimestamp(epoch, tz=ZoneInfo(tz))
    in_window = dt_et.weekday() < 5 and RTH_OPEN <= dt_et.time() < RTH_CLOSE
    if not in_window:
        return False
    if trading_session is not None:
        try:
            label = str(trading_session).strip().lower()
        except Exception:
            label = None
        if label in KNOWN_EXTENDED_SESSIONS:
            return False
    return True


# ── normalized feed events ───────────────────────────────────────────────────
@dataclass
class QuoteUpdate:
    """One decoded Level 1 TRADE-price push, already reduced to what the bar builder
    needs. (Named QuoteUpdate from this module's earliest version, before this session
    added real bid/ask handling -- see TopOfBook for that. Kept as-is rather than renamed,
    since every existing caller/test already spells it this way.) Exactly one of
    trade_volume / cum_volume should normally be set (TICK gives the former, SNAPSHOT the
    latter); both may be absent (e.g. a QUOTE bid/ask push with no trade -- though QUOTE
    pushes are decoded into TopOfBook now, never into this), in which case the update still
    moves close/high/low via `price` if given, but contributes zero volume."""
    symbol: str
    epoch: float            # exchange event time, UTC epoch seconds (fractional ok)
    price: Optional[float] = None
    trade_volume: Optional[float] = None   # incremental (e.g. TICK print size)
    cum_volume: Optional[float] = None     # cumulative session volume (e.g. SNAPSHOT)
    trading_session: Optional[str] = None  # basic.trading_session ('RTH'/'ATH'/...), or None


@dataclass
class TopOfBook:
    """One decoded QUOTE push -- best bid/ask only. Never fed into BarBuilder (no trade
    occurred); backs `last_quote()` only."""
    symbol: str
    epoch: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    trading_session: Optional[str] = None


# ── decoders: SDK result objects -> normalized events (pure, unit-testable with fakes) ──
def _trading_session_of(basic):
    """basic.trading_session (or .get_trading_session()), tolerant of a basic object that
    doesn't have it at all -- returns None rather than raising, which is exactly what makes
    is_regular_session() fall back to the clock."""
    if hasattr(basic, "get_trading_session"):
        try:
            return basic.get_trading_session()
        except Exception:
            return None
    return getattr(basic, "trading_session", None)


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
                        trade_volume=float(vol) if vol is not None else None,
                        trading_session=_trading_session_of(basic))


def normalize_snapshot(symbol, snapshot_result):
    """webull.data.quotes.subscribe.snapshot_result.SnapshotResult -> QuoteUpdate. During
    extended hours the regular price/volume are None and the live reading is in
    ext_price/ext_volume instead (see module docstring) -- fall back to those rather than
    handing back a price-less update that would silently vanish from a bar."""
    basic = snapshot_result.get_basic() if hasattr(snapshot_result, "get_basic") else snapshot_result.basic
    ts_ms = basic.get_timestmap() if hasattr(basic, "get_timestmap") else basic.timestamp
    price = snapshot_result.price
    vol = snapshot_result.volume
    if price is None:
        price = getattr(snapshot_result, "ext_price", None)
        vol = getattr(snapshot_result, "ext_volume", None)
    return QuoteUpdate(symbol=symbol, epoch=float(ts_ms) / 1000.0,
                        price=float(price) if price is not None else None,
                        cum_volume=float(vol) if vol is not None else None,
                        trading_session=_trading_session_of(basic))


def normalize_quote(symbol, quote_result):
    """webull.data.quotes.subscribe.quote_result-shaped object -> TopOfBook. `.bids`/`.asks`
    are lists of objects with `.price`/`.size` ATTRIBUTES (confirmed live, 2026-09-22) --
    top-of-book (first entry) only, either side may be empty."""
    basic = quote_result.get_basic() if hasattr(quote_result, "get_basic") else quote_result.basic
    ts_ms = basic.get_timestmap() if hasattr(basic, "get_timestmap") else basic.timestamp
    bids = getattr(quote_result, "bids", None) or []
    asks = getattr(quote_result, "asks", None) or []
    bid, ask = (bids[0] if len(bids) else None), (asks[0] if len(asks) else None)

    def _attr(level, name):
        v = getattr(level, name, None) if level is not None else None
        return float(v) if v is not None else None

    return TopOfBook(symbol=symbol, epoch=float(ts_ms) / 1000.0,
                      bid=_attr(bid, "price"), bid_size=_attr(bid, "size"),
                      ask=_attr(ask, "price"), ask_size=_attr(ask, "size"),
                      trading_session=_trading_session_of(basic))


# ── bar builder (pure; no network, no SDK, fully unit-testable) ─────────────
class BarBuilder:
    """Turns a stream of QuoteUpdate into closed OHLCV bars for ONE bar length (seconds).
    A WebullBarStreamer holds one instance per timeframe (see `builders`).

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
    BarBuilder(s), periodically persist closed bars, reconnect with backoff on
    disconnect/staleness, clean shutdown. Kept deliberately thin -- all the logic
    worth unit-testing lives in the pure functions/classes above; this class is
    exercised with the real SDK mocked out (see tests/test_webull_stream.py).

    Builds one BarBuilder per entry of [bar_seconds] + extra_bar_seconds (1-minute and
    5-minute by default) from the SAME tick stream, and additionally exposes a
    staleness-aware live-read API: last_trade(), last_quote(), current_bar(timeframe),
    closed_bar(timeframe), health(), reconcile(timeframe, rest_bar). None of these raise;
    each accessor returns None (or a `fresh`/`ok`-shaped dict) when there is nothing to
    report yet, rather than erroring."""

    def __init__(self, symbols=None, bar_seconds=DEFAULT_BAR_SECONDS,
                 extra_bar_seconds=EXTRA_BAR_SECONDS,
                 keys_path=WEBULL_KEYS, token_dir=WEBULL_TOKEN_DIR,
                 stale_after_seconds=90, backoff_base=1.0, backoff_cap=60.0,
                 flush_every_seconds=10, log=print, clock=None):
        self.symbols = symbols or list(DEFAULT_SYMBOLS)
        self.bar_seconds = bar_seconds
        self.keys_path = keys_path
        self.token_dir = token_dir
        self.stale_after_seconds = stale_after_seconds
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.flush_every_seconds = flush_every_seconds
        self.log = log
        # Only the NEW read-API + the two lines noted in _connect_once/_watchdog use this
        # (defaults to the real wall clock); the rest of the connect/watchdog sequence is
        # untouched. See module docstring's LIVE-READ API paragraph.
        self._clock = clock or time.time

        all_secs = [bar_seconds] + [s for s in extra_bar_seconds if s != bar_seconds]
        self.builders = {secs: BarBuilder(bar_seconds=secs) for secs in all_secs}
        self.builder = self.builders[bar_seconds]     # back-compat alias -- the CLI reads this

        self._pending_rows = {secs: [] for secs in all_secs}
        self._closed_bars = {secs: None for secs in all_secs}   # secs -> most recent closed bar dict
        self._last_trade = None      # QuoteUpdate (TICK/SNAPSHOT-derived; ANY session, not RTH-gated)
        self._last_quote = None      # TopOfBook (QUOTE-derived)
        self._message_times = deque(maxlen=4096)
        self._reconnect_count = 0
        self._session_label_counts = {}   # trading_session value (or None) -> count seen

        self._last_message_epoch = None
        self._stop = threading.Event()
        self._client = None
        self._watchdog_thread = None
        self._lock = threading.Lock()

    # -- decode + feed (called from the SDK's own callback thread) --
    def _on_message(self, topic, payload):
        now = self._clock()
        self._last_message_epoch = now
        with self._lock:
            self._message_times.append(now)

        if topic == "quote" or hasattr(payload, "bids") or hasattr(payload, "asks"):
            try:
                bq = normalize_quote(self.symbols[0], payload)
            except Exception as e:
                self.log(f"[webull-stream] decode failed on topic={topic}: {type(e).__name__}: {e}")
                return
            self._record_session_label(bq.trading_session)
            if bq.bid is None and bq.ask is None:
                return
            with self._lock:
                self._last_quote = bq
            return

        update = None
        try:
            if topic == "tick" or hasattr(payload, "get_volume") and hasattr(payload, "time"):
                update = normalize_tick(self.symbols[0], payload)
            elif topic == "snapshot" or hasattr(payload, "get_last_trade_time"):
                update = normalize_snapshot(self.symbols[0], payload)
        except Exception as e:
            self.log(f"[webull-stream] decode failed on topic={topic}: {type(e).__name__}: {e}")
            return
        if update is None:
            return
        self._record_session_label(update.trading_session)
        if update.price is None:
            return

        with self._lock:
            self._last_trade = update
        if not is_regular_session(update.trading_session, update.epoch):
            return   # extended-hours (or otherwise non-RTH) print: seen in last_trade(),
                     # but must never enter an RTH bar (crowned configs are regular-session only)
        with self._lock:
            for secs, builder in self.builders.items():
                closed = builder.ingest(update)
                if closed:
                    self._pending_rows.setdefault(secs, []).extend(closed)
                    self._closed_bars[secs] = closed[-1]

    def _record_session_label(self, label):
        """Bookkeeping only -- tally every trading_session value actually seen (None
        included), surfaced via health()['trading_session_counts']. This is the mechanism
        that settles what the real regular-hours label is instead of guessing again (see
        module docstring's TRADING SESSION FILTERING)."""
        with self._lock:
            self._session_label_counts[label] = self._session_label_counts.get(label, 0) + 1

    def _flush_pending(self):
        with self._lock:
            pending = self._pending_rows
            self._pending_rows = {secs: [] for secs in self.builders}
        written = []
        for secs, rows in pending.items():
            if rows:
                merge_and_write(rows, timeframe=_tf_label(secs))
                written.extend(rows)
        return written

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
        # QUOTE added alongside the existing TICK/SNAPSHOT so last_quote() has something
        # to read -- the only change to this method's subscribe call.
        resp = mds.subscribe(session_id, self.symbols, "US_STOCK", ["TICK", "SNAPSHOT", "QUOTE"])
        status = getattr(resp, "status_code", None)
        if status != 200:
            try:
                client.loop_stop(); client.disconnect()
            except Exception:
                pass
            raise RuntimeError(f"subscribe rejected, status={status}")

        self._last_message_epoch = self._clock()   # count connect as "alive" for staleness purposes
        return client

    def _watchdog(self):
        attempt = 0
        while not self._stop.is_set():
            self._stop.wait(self.flush_every_seconds)
            if self._stop.is_set():
                break
            self._flush_pending()
            if is_stale(self._last_message_epoch, self._clock(), self.stale_after_seconds):
                self.log(f"[webull-stream] feed stale (> {self.stale_after_seconds}s), reconnecting")
                self._teardown_client()
                delay = next_backoff(attempt, self.backoff_base, self.backoff_cap)
                attempt += 1
                if self._stop.wait(delay):
                    break
                try:
                    self._client = self._connect_once()
                    with self._lock:
                        self._reconnect_count += 1
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
            for secs, builder in self.builders.items():
                closed = builder.flush()
                if closed:
                    self._pending_rows.setdefault(secs, []).extend(closed)
                    self._closed_bars[secs] = closed[-1]
        self._flush_pending()
        self._teardown_client()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=5)

    # ── live-read API -- every accessor reports the AGE of what it returns ─────────────
    def last_trade(self):
        """{price, epoch, size, age} from the most recent TICK/SNAPSHOT print (ANY
        session -- not RTH-gated, unlike the bars), or None if nothing has arrived yet.
        `size` is the tick's own print size when known; a SNAPSHOT-derived update carries
        a cumulative volume, not a per-print size, so `size` is None for those."""
        try:
            with self._lock:
                u = self._last_trade
            if u is None:
                return None
            return {"price": u.price, "epoch": u.epoch, "size": u.trade_volume,
                    "age": max(0.0, self._clock() - u.epoch)}
        except Exception:
            return None

    def last_quote(self):
        """{bid, ask, bid_size, ask_size, epoch, age}, or None if no QUOTE has arrived."""
        try:
            with self._lock:
                q = self._last_quote
            if q is None:
                return None
            return {"bid": q.bid, "ask": q.ask, "bid_size": q.bid_size, "ask_size": q.ask_size,
                    "epoch": q.epoch, "age": max(0.0, self._clock() - q.epoch)}
        except Exception:
            return None

    def current_bar(self, timeframe):
        """The in-progress bar dict for '1m'/'5m' (plus `age` = time since it OPENED),
        or None if none has started yet or `timeframe` isn't built by this instance."""
        try:
            secs = _seconds_of(timeframe)
            if secs is None or secs not in self.builders:
                return None
            with self._lock:
                bar = self.builders[secs]._bars.get(self.symbols[0])
                out = dict(bar) if bar is not None else None
            if out is None:
                return None
            out["age"] = max(0.0, self._clock() - out["time"])
            return out
        except Exception:
            return None

    def closed_bar(self, timeframe):
        """The most recently CLOSED bar dict for '1m'/'5m' (plus `age` = time since it
        CLOSED), or None if none has closed yet."""
        try:
            secs = _seconds_of(timeframe)
            if secs is None:
                return None
            with self._lock:
                bar = self._closed_bars.get(secs)
                out = dict(bar) if bar is not None else None
            if out is None:
                return None
            out["age"] = max(0.0, self._clock() - (out["time"] + secs))
            return out
        except Exception:
            return None

    def health(self):
        """Live verdict on the pipe itself. `fresh` is the field a caller should gate on:
        False whenever the stream is not DEMONSTRABLY live (never true off zero messages
        ever received), so a caller falls back to the REST bar path by default.
        `connected`=True with `fresh`=False is "up but silent"; `connected`=False is
        "down" -- the two read differently. `trading_session_counts` is a label->count
        tally of every distinct basic.trading_session value seen so far (`None` counted
        as its own bucket) -- see module docstring's TRADING SESSION FILTERING for why."""
        try:
            with self._lock:
                last_msg = self._last_message_epoch
                connected = self._client is not None
                reconnects = self._reconnect_count
                msg_times = list(self._message_times)
                session_counts = dict(self._session_label_counts)
            now = self._clock()
            last_message_age = None if last_msg is None else max(0.0, now - last_msg)
            if last_msg is None:
                fresh = False
            else:
                fresh = bool(connected) and not is_stale(last_msg, now, self.stale_after_seconds)
            cutoff = now - 60.0
            msgs_per_min = float(sum(1 for t in msg_times if t >= cutoff))
            return {"connected": bool(connected), "fresh": fresh,
                    "last_message_age_s": last_message_age, "messages_per_min": msgs_per_min,
                    "reconnects": reconnects, "subscribed_symbols": list(self.symbols),
                    "trading_session_counts": session_counts}
        except Exception:
            return {"connected": False, "fresh": False, "last_message_age_s": None,
                    "messages_per_min": 0.0, "reconnects": 0, "subscribed_symbols": [],
                    "trading_session_counts": {}}

    def is_fresh(self):
        return bool(self.health().get("fresh"))

    def reconcile(self, timeframe, rest_bar, price_tol=0.01, vol_tol_pct=0.25):
        """Truth check: compare a REST-fetched bar (api/cloud_signal.py's epoch schema --
        any mapping with time/open/high/low/close/volume) against this module's OWN bar
        for that same `time`, for `timeframe`. REST stays authoritative for history -- this
        never writes anything back, it only reports the difference. Checks both the closed
        bar and the current (still-forming) one, since a REST poll can land while this
        module's own bar for that period is still open."""
        try:
            secs = _seconds_of(timeframe)
            if secs is None or rest_bar is None:
                return {"ok": False, "reason": "bad_input", "timeframe": timeframe}
            try:
                target_time = int(rest_bar["time"])
            except (KeyError, TypeError, ValueError):
                return {"ok": False, "reason": "bad_input", "timeframe": timeframe}

            with self._lock:
                closed = self._closed_bars.get(secs)
                current = self.builders[secs]._bars.get(self.symbols[0]) if secs in self.builders else None
                candidates = [dict(b) for b in (closed, current) if b is not None]
            stream_bar = next((b for b in candidates if int(b["time"]) == target_time), None)
            if stream_bar is None:
                return {"ok": False, "reason": "no_stream_bar", "timeframe": timeframe, "time": target_time}

            diffs, mismatch_fields = {}, []
            for k in ("open", "high", "low", "close", "volume"):
                try:
                    d = float(stream_bar[k]) - float(rest_bar[k])
                except (KeyError, TypeError, ValueError):
                    diffs[k] = None
                    continue
                diffs[k] = d
                if k == "volume":
                    denom = max(abs(float(rest_bar.get(k) or 0.0)), 1e-9)
                    if abs(d) / denom > vol_tol_pct:
                        mismatch_fields.append(k)
                elif abs(d) > price_tol:
                    mismatch_fields.append(k)

            return {"ok": True, "timeframe": timeframe, "time": target_time,
                    "stream_bar": stream_bar, "rest_bar": dict(rest_bar), "diffs": diffs,
                    "mismatch": bool(mismatch_fields), "mismatch_fields": mismatch_fields}
        except Exception as e:
            return {"ok": False, "reason": f"reconcile_error: {type(e).__name__}: {e}",
                    "timeframe": timeframe}


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
        print(json.dumps(streamer.builder.stats))   # primary (1-minute) builder's stats
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
