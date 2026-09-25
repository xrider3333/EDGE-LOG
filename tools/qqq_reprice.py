#!/usr/bin/env python3
"""
tools/qqq_reprice.py -- re-price QQQ SHADOW round-trips at REAL QQQ prices.

WHY. api/qqq_exec.py records every shadow trade's entry_px/exit_px using a three-way
pricing fallback (see its module docstring): a live Webull quote when available, else
an NQ-fill-price / (QQQ:NQ ratio) synthetic price, else skipped. In practice the
Webull quote path has no market-data entitlement (confirmed 2026-09-02), so every fill
today is priced off the NQ ratio -- never a real QQQ print. This tool answers "what
would this trade actually have filled at on QQQ" by comparing against a REAL QQQ tape.

SOURCE PREFERENCE (WEBULL_PAPER_TODO.md item 11, 2026-09-25). A trade's round trip is
priced from the FIRST of these three sources that covers BOTH its entry and exit
minute (never split across two sources -- see SLIPPAGE CONVENTION below for why):
  (a) api/webull_stream.py's own live-feed bar cache for that session
      (<EDGELOG_HOME>/ohlc_stream/QQQ_1m.csv) -- the actual tape the order traded on,
      built from Webull's own Level 1 streaming ticks. Free, local, no network. Only
      covers sessions the stream was actually up for (it now runs 09:29-16:02 ET), and
      only as far back as that file's on-disk history reaches.
  (b) Webull's own REST 1-minute history (get_history_bar), the same read-only
      MarketData endpoint api/cloud_signal.py's `_fetch_webull` already calls (gated
      the same way that helper is: webull_keys.json must exist and carry a real
      app_key/app_secret). Duplicated here rather than imported -- api/cloud_signal.py
      pulls in augur_engine.engine and is under active same-day development, and this
      tool must stay a standalone, always-safe-to-run analysis aid (see below) that
      never breaks because a sibling module's import chain did. NEVER imports
      webull.trade.* or anything order-related, and never places or touches an order --
      the only SDK call made anywhere in this file is the read-only get_history_bar.
      This endpoint has no start/end date parameter -- only the most recent `count`
      bars (Webull's own cap is 1200) -- so it can only reach back a few sessions, the
      same ceiling the live stream itself has.
  (c) yfinance 1-minute bars (the ORIGINAL and, until now, only source), free delayed
      data for the real symbol, going back ~30 days. Last resort: no key/network
      dependency on Webull at all, so it is what keeps this tool useful even on a box
      with no Webull entitlement configured.
Each source is tried in order and is entirely best-effort -- a source that can't cover
a trade (file missing, day not on disk, minute out of the tail, keys unconfigured,
any SDK/network error) is skipped for that trade, never an error, and the trade falls
through to the next source. The source that actually priced a trade is recorded in the
new `price_source` column (see HEADER MIGRATION below); `source` (kept for backward
compatibility -- see that section) now carries the same value instead of the literal
"yfinance_1m" it used to hardcode for every row regardless of what actually happened.

This is a READ-ONLY analysis tool. It never touches C:\\EdgeLog\\qqq_exec\\trades.csv
(the adapter appends to that file live, from a different process, on its own tick
loop -- writing to it here would race that writer and corrupt a live-owned file), and
it never places, modifies, or cancels a Webull order of any kind. It writes only to a
SIDECAR, C:\\EdgeLog\\qqq_exec\\reprice.csv, keyed by (leg, entry_ts), so it can be
re-run any time without duplicating work.

BAR-CLOSE CONVENTION (read this before changing the pricing logic). A shadow fill has
a wall-clock timestamp with seconds, e.g. entry_ts "2026-09-03 12:30:16". A 1-minute
bar (from any of the three sources above) is labelled by the bar's OPEN time and spans
[label, label+1min), e.g. the bar labelled "12:30:00" covers 12:30:00-12:30:59. We do
NOT know at what second within that bar a real retail order would actually have
printed -- the adapter's own fill (on NQ) landed somewhere inside it too. Rather than
guess an intra-bar fill price (which would silently assume execution quality we can't
back up), we conservatively price BOTH the entry and the exit at that bar's CLOSE.
This is deliberately the same convention for entry and exit (no directional bias from
"entry uses open, exit uses close" or similar), and it is a real, tradeable price the
market actually printed in that minute -- just not necessarily the exact second of the
fill. If the exact minute is missing from a source (a gap in that source's own
coverage), we fall back to the nearest bar within 3 minutes IN THAT SAME SOURCE and
note it; beyond 3 minutes that source cannot price this trade and the next source in
the preference order is tried instead (see SOURCE PREFERENCE above).

SLIPPAGE CONVENTION. The re-priced P&L is not simply (real_exit - real_entry) * dir *
shares -- that would price a fill with ZERO execution cost, which the real adapter
(and any real broker) never gets. We charge the adapter's own configured
slippage_per_share (config.json) once per side of the round trip (entry AND exit),
against the trader always -- a round trip always crosses the spread twice, regardless
of side:
    slippage_total = 2 * slippage_per_share * shares
    real_pnl = (real_exit_px - real_entry_px) * dir * shares - slippage_total
where dir = +1 for a long lot, -1 for a short lot (mirrors _record_trade in
api/qqq_exec.py). This is separate from slip_entry_ps/slip_exit_ps below, which
measure something else: how far the adapter's ALREADY-RECORDED (ratio-derived)
entry_px/exit_px sat from the real market price -- i.e. how much the synthetic pricing
itself was off, not a hypothetical execution cost. A round trip is always priced
ENTRY AND EXIT FROM THE SAME SOURCE (never entry from the stream and exit from
yfinance) so this comparison is never contaminated by two different feeds' own quirks:
    slip_entry_ps = real_entry_px - entry_px      (signed, $/share)
    slip_exit_ps  = real_exit_px  - exit_px       (signed, $/share)

HEADER MIGRATION. `price_source` is a new sidecar column (2026-09-25, item 11). An
existing reprice.csv written by the old, yfinance-only code has no such column;
csv.DictReader simply hands back rows without that key, and write_sidecar's
`row.get(c, "")` already fills in "" for any old row that gets rewritten (a
--apply run that has at least one NEW row to add rewrites the whole file under the
CURRENT SIDECAR_COLS, migrating every old row's header for free) -- no separate
migration step needed. An old row that is never touched again (nothing new to write)
simply stays on disk in its old shape until the next row is written.

CLI:
    python tools/qqq_reprice.py                 dry run (default) -- prints the table,
                                                  writes nothing
    python tools/qqq_reprice.py --apply         writes new sidecar rows
    python tools/qqq_reprice.py --apply --force re-computes + overwrites rows that are
                                                  already in the sidecar
    python tools/qqq_reprice.py --summary-json  prints a one-line JSON summary (see
                                                  summary_json()) after the normal output
    python tools/qqq_reprice.py --selftest      offline arithmetic/sign self-test
                                                  against a synthetic trades.csv + fake
                                                  bars -- no network, no real files
"""
import argparse
import csv
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _NY = None

OUT_DIR = os.environ.get("EDGELOG_QQQ_EXEC_DIR", r"C:\EdgeLog\qqq_exec")
TRADES_CSV = os.path.join(OUT_DIR, "trades.csv")
SIDECAR_CSV = os.path.join(OUT_DIR, "reprice.csv")
CONFIG_PATH = os.path.join(OUT_DIR, "config.json")

# "source" is kept, unrenamed, for backward compatibility (nothing in index.html reads
# it today, but this file must never assume that stays true); "price_source" is the
# new column item 11 asked for. Both carry the SAME value on every row this tool
# writes from here on -- see module docstring's SOURCE PREFERENCE section.
SIDECAR_COLS = ["leg", "entry_ts", "exit_ts", "real_entry_px", "real_exit_px",
                "real_pnl", "slip_entry_ps", "slip_exit_ps", "repriced_at",
                "source", "price_source", "note"]

DEFAULT_SLIPPAGE_PER_SHARE = 0.01
NEAREST_BAR_TOLERANCE_MIN = 3
# yfinance only carries 1m bars for roughly the trailing 30 days; used only to print a
# clearer note before even attempting the network call, not to enforce a hard cutoff
# (Yahoo's own response is the actual authority -- an empty frame is still handled).
YF_1M_LOOKBACK_DAYS = 30

# Webull's own per-request cap on get_history_bar (see api/cloud_signal.py's
# _fetch_webull docstring) -- there is no start/end date parameter on this endpoint,
# only a bar COUNT counting back from now, so this is also the practical ceiling on
# how far back source (b) below can ever reach.
WEBULL_REST_1M_TAIL = 1200
WEBULL_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json")
WEBULL_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR", r"C:\EdgeLog\webull_token")

SOURCE_STREAM = "webull_stream_1m"
SOURCE_REST = "webull_rest_1m"
SOURCE_YFINANCE = "yfinance_1m"


def _now_et():
    return datetime.now(_NY) if _NY else datetime.utcnow()


def _parse_ts(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")


def _epoch_to_et_minute(epoch):
    """UTC epoch seconds -> naive ET wall-clock datetime, floored to the minute --
    the same shape entry_ts/exit_ts parse to (via _parse_ts) and the same shape
    fetch_day_bars already builds from yfinance's tz-aware index. Falls back to naive
    UTC if zoneinfo is unavailable (matches _now_et's own fallback)."""
    dt = datetime.fromtimestamp(epoch, tz=_NY) if _NY else datetime.utcfromtimestamp(epoch)
    return dt.replace(tzinfo=None, second=0, microsecond=0)


def _fmt(x, nd=4):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else str(x)


# -- config --------------------------------------------------------------------------
def load_slippage_per_share(config_path=None, log=print):
    path = config_path or CONFIG_PATH
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        val = cfg.get("slippage_per_share", DEFAULT_SLIPPAGE_PER_SHARE)
        return float(val)
    except Exception as e:
        log(f"[qqq-reprice] could not read slippage_per_share from {path} "
            f"({type(e).__name__}: {e}) -- using default {DEFAULT_SLIPPAGE_PER_SHARE}")
        return DEFAULT_SLIPPAGE_PER_SHARE


# -- trades.csv / sidecar I/O ---------------------------------------------------------
def read_trades(trades_csv=None):
    path = trades_csv or TRADES_CSV
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    # every row in trades.csv is a CLOSED round trip -- the adapter only appends here
    # from _record_trade, which runs at exit time.
    return [r for r in rows if (r.get("entry_ts") or "").strip() and
            (r.get("exit_ts") or "").strip()]


def read_sidecar(sidecar_csv=None):
    path = sidecar_csv or SIDECAR_CSV
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {(r["leg"], r["entry_ts"]): r for r in rows}


def write_sidecar(existing, new_or_updated, sidecar_csv=None, log=print):
    """existing: dict key -> row (already on disk, in original order-ish).
    new_or_updated: dict key -> row to add/overwrite.
    Rewrites the whole file (small, capped by trade volume) so overwritten keys
    (via --force) land in place rather than duplicating. An old row that predates the
    `price_source` column (see module docstring's HEADER MIGRATION) simply has no such
    key, and `row.get(c, "")` below fills in "" for it -- this is the entire migration,
    triggered the next time this function runs at all."""
    path = sidecar_csv or SIDECAR_CSV
    merged = dict(existing)
    merged.update(new_or_updated)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SIDECAR_COLS)
        w.writeheader()
        for row in merged.values():
            w.writerow({c: row.get(c, "") for c in SIDECAR_COLS})
    os.replace(tmp, path)
    log(f"[qqq-reprice] wrote {len(merged)} row(s) -> {path}")


# -- bar fetch: (a) the live feed's own on-disk cache ---------------------------------
def _edgelog_home():
    """Same env var / default api/webull_stream.py's edgelog_home() uses, deliberately
    DUPLICATED rather than imported -- see module docstring's SOURCE PREFERENCE (a) for
    why: this tool must stay free of an import-time dependency on a sibling module a
    different session may be mid-edit on (that module carries a 2026-09-25-dated
    change as of this writing)."""
    h = os.environ.get("EDGELOG_HOME")
    if h:
        return h
    if os.name == "nt":
        return r"C:\EdgeLog"
    return os.path.expanduser("~/edgelog")


def _stream_bar_path(timeframe="1m", home=None):
    """Same path api/webull_stream.py's stream_cache_path() computes:
    <home>/ohlc_stream/QQQ_<timeframe>.csv -- six-column epoch schema
    (time,open,high,low,close,volume), `time` = UTC epoch seconds of the bar's OPEN
    instant. Written by WebullBarStreamer every ~10s while the stream is running
    (09:29-16:02 ET)."""
    return os.path.join(home or _edgelog_home(), "ohlc_stream", f"QQQ_{timeframe}.csv")


def load_stream_bars(days_needed, timeframe="1m", home=None, log=print):
    """{day_str -> {datetime naive ET minute -> close}}, restricted to `days_needed`,
    read from the live feed's own on-disk cache (see _stream_bar_path). Returns {} --
    i.e. "this source covers nothing" -- if the file is missing, empty, unreadable, or
    simply has no rows for any requested day (a normal, non-error state: the stream
    hadn't started yet, was down that day, or is a bonus source that just doesn't
    reach back that far). Never raises -- this is always a best-effort source, never a
    hard dependency, exactly like the yfinance path below."""
    path = _stream_bar_path(timeframe, home)
    if not os.path.exists(path):
        return {}
    try:
        out = {}
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    epoch = float(row["time"])
                    close = float(row["close"])
                except (KeyError, TypeError, ValueError):
                    continue
                dt = _epoch_to_et_minute(epoch)
                day = dt.strftime("%Y-%m-%d")
                if day not in days_needed:
                    continue
                out.setdefault(day, {})[dt] = close
        return out
    except Exception as e:
        log(f"[qqq-reprice] stream cache read failed ({path}): {type(e).__name__}: {e}")
        return {}


# -- bar fetch: (b) Webull REST 1-minute history --------------------------------------
def _webull_rest_keys(keys_path=None):
    """Same placeholder/empty checks api/webull_stream.py's load_keys and
    api/qqq_exec.py's _webull_quote_raw use before ever importing the SDK -- a
    read-only, no-network gate. Returns {app_key, app_secret, region} or None if
    unconfigured (missing file, blank, or still the PASTE_... placeholder)."""
    path = keys_path or WEBULL_KEYS
    try:
        with open(path, encoding="utf-8") as f:
            keys = json.load(f)
    except Exception:
        return None
    ak = (keys.get("app_key") or "").strip()
    sk = (keys.get("app_secret") or "").strip()
    if not ak or not sk or ak.startswith("PASTE_"):
        return None
    return {"app_key": ak, "app_secret": sk, "region": (keys.get("region") or "us").strip().lower()}


def fetch_webull_rest_1m(count=WEBULL_REST_1M_TAIL, keys_path=None, token_dir=None, log=print):
    """QQQ 1-minute bars via the Webull OpenAPI's READ-ONLY get_history_bar endpoint --
    the same call api/cloud_signal.py's `_fetch_webull` makes, duplicated here rather
    than imported (see module docstring's SOURCE PREFERENCE (b) for why). NEVER
    imports webull.trade.* or anything order-related: the only SDK classes touched are
    ApiClient / ClientInitializer / MarketData / Category / Timespan, and the only call
    made anywhere in this function is the read-only get_history_bar -- no order of any
    kind is placed, modified, or cancelled by this file, ever.

    Only the TAIL (most recent `count` bars; Webull's own request cap is 1200) is
    available -- there is no start/end date parameter -- so in practice this can only
    cover roughly the last few sessions, the same ceiling the live stream itself has.
    Returns {day_str -> {datetime naive ET minute -> close}} -- SAME shape
    load_stream_bars returns, grouped by ET calendar day -- spanning whatever days the
    tail happens to reach, or {} if keys aren't configured/valid or the call fails for
    ANY reason (never raises -- a bonus source, not a hard dependency, exactly like (a))."""
    keys = _webull_rest_keys(keys_path)
    if not keys:
        return {}
    try:
        from webull.core.client import ApiClient
        from webull.core.http.initializer.client_initializer import ClientInitializer
        from webull.data.quotes.market_data import MarketData
        from webull.data.common.category import Category
        from webull.data.common.timespan import Timespan
        import pandas as pd

        api = ApiClient(keys["app_key"], keys["app_secret"], keys["region"],
                        token_check_duration_seconds=15, token_check_interval_seconds=5,
                        connect_timeout=10, timeout=25)
        os.makedirs(token_dir or WEBULL_TOKEN_DIR, exist_ok=True)
        api.set_token_dir(token_dir or WEBULL_TOKEN_DIR)
        # same rotating-file-logger / credential-leak mitigation api/webull_stream.py
        # and api/cloud_signal.py's own Webull calls already apply.
        api._file_logger_set = True
        import logging as _lg
        _lg.getLogger("webull.core").addHandler(_lg.NullHandler())
        # TOKEN: MarketData(api) does NOT authenticate the client by itself -- only
        # ClientInitializer.initializer() attaches the x-access-token (see
        # api/qqq_exec.py's _webull_quote_raw and api/webull_stream.py's _fetch_webull
        # docstrings for the full history of this gotcha). Do not remove this call.
        ClientInitializer.initializer(api)
        resp = MarketData(api).get_history_bar("QQQ", Category.US_ETF, Timespan.M1,
                                                count=str(count))
        rows = resp.json() if hasattr(resp, "json") else resp
        if not isinstance(rows, list) or not rows:
            return {}
        out = {}
        for r in rows:
            if str(r.get("trading_session", "RTH")).upper() != "RTH":
                continue
            try:
                epoch = pd.Timestamp(r["time"]).timestamp()
                close = float(r["close"])
            except Exception:
                continue
            dt = _epoch_to_et_minute(epoch)
            out.setdefault(dt.strftime("%Y-%m-%d"), {})[dt] = close
        return out
    except Exception as e:
        log(f"[qqq-reprice] webull REST 1m history unavailable: {type(e).__name__}: {e}")
        return {}


# -- bar fetch: (c) yfinance (original, last-resort fallback) -------------------------
class NetworkUnavailable(Exception):
    pass


def fetch_day_bars(day_str, log=print):
    """Return a dict {datetime (naive, ET wall-clock, minute-floored): close_price} for
    QQQ 1m bars on the given ET calendar date ("YYYY-MM-DD"), or None if Yahoo simply
    has no bars for that date (holiday/weekend/beyond its 1m window -- NOT an error).
    Raises NetworkUnavailable if the fetch itself could not be attempted/completed."""
    try:
        import yfinance as yf
    except Exception as e:
        raise NetworkUnavailable(f"yfinance not importable: {type(e).__name__}: {e}")

    start = day_str
    end_dt = datetime.strptime(day_str, "%Y-%m-%d") + timedelta(days=1)
    end = end_dt.strftime("%Y-%m-%d")
    try:
        df = yf.Ticker("QQQ").history(start=start, end=end, interval="1m",
                                       prepost=False)
    except Exception as e:
        # yfinance wraps requests/urllib errors in its own exception types depending on
        # version; treat ANY failure to fetch as "network unavailable" per spec --
        # there is no other reason a single-day 1m request would raise.
        raise NetworkUnavailable(f"{type(e).__name__}: {e}")

    if df is None or df.empty:
        return None

    idx = df.index
    try:
        if idx.tz is not None:
            if _NY is not None:
                idx = idx.tz_convert(_NY)
        # else: naive index, already ET (older yfinance) -- leave as-is.
    except Exception:
        pass

    out = {}
    for ts, close in zip(idx, df["Close"].tolist()):
        naive = ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts
        out[naive.replace(second=0, microsecond=0)] = float(close)
    return out


def _nearest_bar_close(bars, ts, tolerance_min=NEAREST_BAR_TOLERANCE_MIN):
    """bars: dict of minute-floored datetime -> close. ts: exact datetime (with
    seconds) to locate. Returns (close_px, note) or (None, note) if nothing within
    tolerance. note is "" for an exact-bar hit, else describes the fallback."""
    minute = ts.replace(second=0, microsecond=0)
    if minute in bars:
        return bars[minute], ""
    best_dt, best_diff = None, None
    for bar_dt in bars:
        diff = abs((bar_dt - minute).total_seconds())
        if best_diff is None or diff < best_diff:
            best_dt, best_diff = bar_dt, diff
    if best_dt is not None and best_diff <= tolerance_min * 60:
        mins = best_diff / 60.0
        return bars[best_dt], f"nearest bar {mins:.1f} min away"
    return None, f"no bar within {tolerance_min} min -- skipped"


# -- core repricing ---------------------------------------------------------------------
def _try_source(bars_by_day, entry_ts, exit_ts, entry_day, exit_day, day_notes=None):
    """Try to price ONE trade's entry+exit from a SINGLE source's per-day bars dict
    (as returned by load_stream_bars / fetch_webull_rest_1m-grouped-by-day /
    fetch_day_bars-collected-by-day). Returns (real_entry_px, real_exit_px, notes) if
    BOTH legs resolve (within the nearest-bar tolerance); (None, None, notes)
    otherwise, with notes explaining why not (a missing day uses day_notes[day] when
    given -- e.g. yfinance's own "beyond 30-day window" -- else a generic message).
    Pure/local, no I/O of its own -- source-agnostic, so the SAME tolerance/CLOSE
    convention applies no matter which source is being tried."""
    day_notes = day_notes or {}
    notes = []
    bars_entry = bars_by_day.get(entry_day)
    bars_exit = bars_by_day.get(exit_day)
    if not bars_entry:
        notes.append(day_notes.get(entry_day, f"no bars for {entry_day}"))
    if not bars_exit and exit_day != entry_day:
        notes.append(day_notes.get(exit_day, f"no bars for {exit_day}"))
    if not bars_entry or not bars_exit:
        return None, None, notes

    real_entry_px, note_e = _nearest_bar_close(bars_entry, entry_ts)
    real_exit_px, note_x = _nearest_bar_close(bars_exit, exit_ts)
    if note_e:
        notes.append(f"entry: {note_e}")
    if note_x:
        notes.append(f"exit: {note_x}")
    if real_entry_px is None or real_exit_px is None:
        return None, None, notes
    return real_entry_px, real_exit_px, notes


def reprice_one(trade, tiered_sources, slippage_per_share, log=print):
    """tiered_sources: ordered list of (source_name, bars_by_day[, day_notes]) tuples,
    HIGHEST PREFERENCE FIRST (see module docstring's SOURCE PREFERENCE). The first
    source that can price BOTH legs of the round trip wins -- a round trip is never
    split across two sources (see SLIPPAGE CONVENTION). Returns a sidecar row dict, or
    a skip row (via _skip_row) citing every source's reason if none could price it."""
    leg = trade["leg"]
    entry_ts = _parse_ts(trade["entry_ts"])
    exit_ts = _parse_ts(trade["exit_ts"])
    entry_px = float(trade["entry_px"])
    exit_px = float(trade["exit_px"])
    side = (trade.get("side") or "long").strip().lower()
    shares = float(trade["shares"])
    dir_mult = 1 if side == "long" else -1

    entry_day = entry_ts.strftime("%Y-%m-%d")
    exit_day = exit_ts.strftime("%Y-%m-%d")

    all_notes = []
    for spec in tiered_sources:
        source_name, bars_by_day = spec[0], spec[1]
        day_notes = spec[2] if len(spec) > 2 else None
        real_entry_px, real_exit_px, notes = _try_source(
            bars_by_day, entry_ts, exit_ts, entry_day, exit_day, day_notes)
        if real_entry_px is None:
            if notes:
                all_notes.append(f"{source_name}: " + "; ".join(notes))
            continue

        slippage_total = 2.0 * slippage_per_share * shares
        real_pnl = round((real_exit_px - real_entry_px) * dir_mult * shares - slippage_total, 2)
        slip_entry_ps = round(real_entry_px - entry_px, 4)
        slip_exit_ps = round(real_exit_px - exit_px, 4)

        return {
            "leg": leg,
            "entry_ts": trade["entry_ts"],
            "exit_ts": trade["exit_ts"],
            "real_entry_px": round(real_entry_px, 4),
            "real_exit_px": round(real_exit_px, 4),
            "real_pnl": real_pnl,
            "slip_entry_ps": slip_entry_ps,
            "slip_exit_ps": slip_exit_ps,
            "repriced_at": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
            "source": source_name,
            "price_source": source_name,
            "note": "; ".join(notes),
            # not written to sidecar, kept for the printed table only:
            "_ratio_entry_px": entry_px, "_ratio_exit_px": exit_px,
            "_ratio_pnl": float(trade.get("pnl") or 0.0), "_skipped": False,
        }

    reason = "; ".join(all_notes) if all_notes else "no source had bars for this trade"
    return _skip_row(trade, reason)


def _skip_row(trade, note):
    return {
        "leg": trade["leg"], "entry_ts": trade["entry_ts"], "exit_ts": trade["exit_ts"],
        "real_entry_px": "", "real_exit_px": "", "real_pnl": "",
        "slip_entry_ps": "", "slip_exit_ps": "",
        "repriced_at": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "", "price_source": "", "note": note,
        "_ratio_entry_px": float(trade.get("entry_px") or 0.0),
        "_ratio_exit_px": float(trade.get("exit_px") or 0.0),
        "_ratio_pnl": float(trade.get("pnl") or 0.0), "_skipped": True,
    }


# -- reporting ---------------------------------------------------------------------------
def print_table(rows, log=print):
    if not rows:
        log("[qqq-reprice] nothing to report.")
        return
    hdr = (f"{'leg':<7}{'entry_ts':<21}{'ratio px (en/ex)':<20}{'real px (en/ex)':<20}"
           f"{'slip en/ex ps':<16}{'ratio pnl':>10}{'real pnl':>10}  {'source':<16}note")
    log(hdr)
    log("-" * len(hdr))
    for r in rows:
        if r["_skipped"]:
            log(f"{r['leg']:<7}{r['entry_ts']:<21}{'--':<20}{'--':<20}{'--':<16}"
                f"{r['_ratio_pnl']:>10.2f}{'--':>10}  {'--':<16}{r['note']}")
            continue
        ratio_px = f"{r['_ratio_entry_px']:.4f}/{r['_ratio_exit_px']:.4f}"
        real_px = f"{r['real_entry_px']:.4f}/{r['real_exit_px']:.4f}"
        slip_px = f"{r['slip_entry_ps']:+.4f}/{r['slip_exit_ps']:+.4f}"
        log(f"{r['leg']:<7}{r['entry_ts']:<21}{ratio_px:<20}{real_px:<20}{slip_px:<16}"
            f"{r['_ratio_pnl']:>10.2f}{r['real_pnl']:>10.2f}  "
            f"{r.get('price_source', '') or '--':<16}{r['note']}")

    priced = [r for r in rows if not r["_skipped"]]
    if priced:
        slips = [abs(r["slip_entry_ps"]) for r in priced] + \
                [abs(r["slip_exit_ps"]) for r in priced]
        mean_slip = sum(slips) / len(slips)
        max_slip = max(slips)
        ratio_pnl_total = sum(r["_ratio_pnl"] for r in priced)
        real_pnl_total = sum(r["real_pnl"] for r in priced)
        log("-" * len(hdr))
        log(f"priced {len(priced)}/{len(rows)}  mean |slip|/share={mean_slip:.4f}  "
            f"max |slip|/share={max_slip:.4f}  ratio-pnl total={ratio_pnl_total:.2f}  "
            f"real-pnl total={real_pnl_total:.2f}  diff={real_pnl_total - ratio_pnl_total:+.2f}")
    else:
        log(f"priced 0/{len(rows)} -- nothing successfully repriced this run.")


def summary_json(all_trades, sidecar_after, log=print):
    total = len(all_trades)
    priced_rows = [r for r in sidecar_after.values() if (r.get("real_pnl") or "") != ""]
    covered = len(priced_rows)
    slips = []
    for r in priced_rows:
        for k in ("slip_entry_ps", "slip_exit_ps"):
            try:
                slips.append(abs(float(r[k])))
            except Exception:
                pass
    out = {
        "covered": covered,
        "total": total,
        "coverage_pct": round(100.0 * covered / total, 2) if total else 0.0,
        "mean_slip_ps": round(sum(slips) / len(slips), 4) if slips else None,
        "last_run": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
    }
    log(json.dumps(out))
    return out


# -- main ---------------------------------------------------------------------------------
def run(trades_csv=None, sidecar_csv=None, config_path=None, apply=False, force=False,
        do_summary_json=False, stream_home=None, webull_keys_path=None,
        webull_token_dir=None, log=print):
    trades = read_trades(trades_csv)
    if not trades:
        log(f"[qqq-reprice] no closed trades found in "
            f"{trades_csv or TRADES_CSV} -- nothing to do.")
        if do_summary_json:
            summary_json([], {}, log=log)
        return 0

    existing = read_sidecar(sidecar_csv)
    slippage_per_share = load_slippage_per_share(config_path, log=log)

    cutoff_date = (_now_et() - timedelta(days=YF_1M_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    to_process = []
    for t in trades:
        key = (t["leg"], t["entry_ts"])
        if key in existing and not force:
            continue
        to_process.append(t)

    if not to_process:
        log(f"[qqq-reprice] {len(trades)} closed trade(s), all already in "
            f"{sidecar_csv or SIDECAR_CSV} -- nothing new (pass --force to redo).")
        if do_summary_json:
            summary_json(trades, existing, log=log)
        return 0

    days_needed = set()
    for t in to_process:
        days_needed.add(_parse_ts(t["entry_ts"]).strftime("%Y-%m-%d"))
        days_needed.add(_parse_ts(t["exit_ts"]).strftime("%Y-%m-%d"))

    def _covered(bars_by_day, t):
        entry_ts = _parse_ts(t["entry_ts"])
        exit_ts = _parse_ts(t["exit_ts"])
        px_e, _px_x, _notes = _try_source(bars_by_day, entry_ts, exit_ts,
                                          entry_ts.strftime("%Y-%m-%d"),
                                          exit_ts.strftime("%Y-%m-%d"))
        return px_e is not None

    # -- (a) the live feed's own bars for the session: local file, always tried first,
    # never a network call. --
    stream_bars_by_day = load_stream_bars(days_needed, home=stream_home, log=log)
    remaining = [t for t in to_process if not _covered(stream_bars_by_day, t)]

    # -- (b) Webull REST 1m history: only attempted if the stream didn't cover
    # everything, and only ever ONE call for the whole run (not once per trade). --
    rest_bars_by_day = {}
    if remaining:
        rest_bars_by_day = fetch_webull_rest_1m(keys_path=webull_keys_path,
                                                 token_dir=webull_token_dir, log=log)
        remaining = [t for t in remaining if not _covered(rest_bars_by_day, t)]

    # -- (c) yfinance: last resort, exactly the tool's original (and until now only)
    # behaviour -- only for the days still needed by whatever's left uncovered. --
    yf_days_needed = set()
    for t in remaining:
        yf_days_needed.add(_parse_ts(t["entry_ts"]).strftime("%Y-%m-%d"))
        yf_days_needed.add(_parse_ts(t["exit_ts"]).strftime("%Y-%m-%d"))

    yf_bars_by_day = {}
    fetch_errors = {}
    for day in sorted(yf_days_needed):
        if day < cutoff_date:
            fetch_errors[day] = "beyond 30-day window"
            continue
        try:
            bars = fetch_day_bars(day, log=log)
            if bars is None:
                fetch_errors[day] = "no bars returned for that day (holiday/weekend/gap)"
            else:
                yf_bars_by_day[day] = bars
        except NetworkUnavailable as e:
            log(f"[qqq-reprice] network/data source unavailable ({e}) -- "
                f"sidecar left untouched, exiting cleanly.")
            return 0

    computed = {}
    report_rows = []
    for t in to_process:
        row = reprice_one(t, [
            (SOURCE_STREAM, stream_bars_by_day),
            (SOURCE_REST, rest_bars_by_day),
            (SOURCE_YFINANCE, yf_bars_by_day, fetch_errors),
        ], slippage_per_share, log=log)
        report_rows.append(row)
        if not row["_skipped"]:
            computed[(row["leg"], row["entry_ts"])] = row

    print_table(report_rows, log=log)

    if apply and computed:
        write_sidecar(existing, computed, sidecar_csv, log=log)
        merged = dict(existing)
        merged.update(computed)
    elif apply:
        log("[qqq-reprice] --apply given but nothing new could be priced -- "
            "sidecar untouched.")
        merged = existing
    else:
        log(f"[qqq-reprice] DRY RUN -- would write {len(computed)} row(s) to "
            f"{sidecar_csv or SIDECAR_CSV} (pass --apply to write).")
        merged = dict(existing)
        merged.update(computed)

    if do_summary_json:
        summary_json(trades, merged, log=log)
    return 0


# -- self-test ------------------------------------------------------------------------------
def _selftest():
    """Fully offline: builds a temp trades.csv, fake bars_by_day dicts per source
    (bypassing every network/file fetch entirely), and checks the arithmetic +
    slippage sign directly against reprice_one(), plus the new source-preference
    order. Also checks idempotency (second call with same key already in sidecar is
    skipped) and the --force override path at the run() level using monkeypatched
    fetches. tests/test_qqq_reprice.py is the primary (pytest) coverage for the
    source-preference/fallback/header-migration behaviour -- this is the quick
    no-dependencies CLI check."""
    ok = True

    def check(name, cond):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"[selftest] {status}: {name}")

    # -- 1. direct arithmetic on reprice_one, long side, single source ----------------
    # Dates are deliberately computed relative to "now" (a few days back) rather than
    # hardcoded, so this test keeps passing regardless of when it's run.
    recent_day = (_now_et() - timedelta(days=3)).strftime("%Y-%m-%d")
    trade_long = {"leg": "NOISE", "entry_ts": f"{recent_day} 12:30:16",
                  "exit_ts": f"{recent_day} 15:58:05", "side": "long", "shares": "5",
                  "entry_px": "719.2731", "exit_px": "719.8505", "pnl": "2.89"}
    recent_dt = datetime.strptime(recent_day, "%Y-%m-%d")
    bars_by_day = {
        recent_day: {recent_dt.replace(hour=12, minute=30): 720.00,
                     recent_dt.replace(hour=15, minute=58): 721.00},
    }
    sources_yf_only = [(SOURCE_YFINANCE, bars_by_day)]
    row = reprice_one(trade_long, sources_yf_only, slippage_per_share=0.01,
                       log=lambda *a: None)
    check("long: not skipped", row["_skipped"] is False)
    check("long: real_entry_px == bar close (720.00)", row["real_entry_px"] == 720.00)
    check("long: real_exit_px == bar close (721.00)", row["real_exit_px"] == 721.00)
    check("long: price_source recorded", row["price_source"] == SOURCE_YFINANCE)
    check("long: source mirrors price_source", row["source"] == row["price_source"])
    # slip_entry_ps = real(720.00) - recorded(719.2731) = 0.7269
    check("long: slip_entry_ps sign/value",
          abs(row["slip_entry_ps"] - 0.7269) < 1e-6)
    check("long: slip_exit_ps sign/value",
          abs(row["slip_exit_ps"] - (721.00 - 719.8505)) < 1e-6)
    # real_pnl = (721.00-720.00)*1*5 - 2*0.01*5 = 5.0 - 0.1 = 4.90
    check("long: real_pnl arithmetic + slippage subtracted",
          abs(row["real_pnl"] - 4.90) < 1e-9)

    # -- 2. short side flips the direction multiplier --------------------------------
    trade_short = dict(trade_long, side="short")
    row_s = reprice_one(trade_short, sources_yf_only, slippage_per_share=0.01,
                         log=lambda *a: None)
    # real_pnl = (721.00-720.00)*(-1)*5 - 0.1 = -5.0 - 0.1 = -5.10
    check("short: direction multiplier flips sign of price pnl",
          abs(row_s["real_pnl"] - (-5.10)) < 1e-9)
    # slip_entry_ps / slip_exit_ps are direction-agnostic (pure price differences)
    check("short: slip_entry_ps unaffected by side",
          row_s["slip_entry_ps"] == row["slip_entry_ps"])

    # -- 3. slippage always REDUCES pnl regardless of direction ----------------------
    row_noslip = reprice_one(trade_long, sources_yf_only, slippage_per_share=0.0,
                              log=lambda *a: None)
    check("slippage strictly reduces long real_pnl vs zero-slippage",
          row["real_pnl"] < row_noslip["real_pnl"])
    row_s_noslip = reprice_one(trade_short, sources_yf_only, slippage_per_share=0.0,
                                log=lambda *a: None)
    check("slippage strictly reduces short real_pnl vs zero-slippage",
          row_s["real_pnl"] < row_s_noslip["real_pnl"])

    # -- 4. nearest-bar fallback within tolerance, and beyond it ----------------------
    bars_gap = {recent_day: {recent_dt.replace(hour=12, minute=32): 722.0,
                              recent_dt.replace(hour=15, minute=58): 721.0}}
    row_fb = reprice_one(trade_long, [(SOURCE_YFINANCE, bars_gap)],
                          slippage_per_share=0.01, log=lambda *a: None)
    check("nearest-bar fallback (2 min away, within 3 min tolerance) used",
          row_fb["_skipped"] is False and row_fb["real_entry_px"] == 722.0)
    check("fallback noted", "nearest bar" in row_fb["note"])

    bars_far = {recent_day: {recent_dt.replace(hour=12, minute=40): 723.0,
                              recent_dt.replace(hour=15, minute=58): 721.0}}
    row_far = reprice_one(trade_long, [(SOURCE_YFINANCE, bars_far)],
                           slippage_per_share=0.01, log=lambda *a: None)
    check("beyond 3-min tolerance -> skipped", row_far["_skipped"] is True)
    check("beyond-tolerance note text", "no bar within" in row_far["note"])

    # -- 5. source preference: stream (a) wins over yfinance (c) when both cover it --
    stream_bars = {recent_day: {recent_dt.replace(hour=12, minute=30): 999.0,
                                 recent_dt.replace(hour=15, minute=58): 999.0}}
    row_pref = reprice_one(trade_long,
                            [(SOURCE_STREAM, stream_bars), (SOURCE_YFINANCE, bars_by_day)],
                            slippage_per_share=0.01, log=lambda *a: None)
    check("higher-preference source wins when it covers the trade",
          row_pref["price_source"] == SOURCE_STREAM and row_pref["real_entry_px"] == 999.0)

    # -- 6. source preference: falls through to the NEXT source when the first one
    # can't cover this trade (empty dict -- e.g. file missing / keys unconfigured) ----
    row_fall = reprice_one(trade_long,
                            [(SOURCE_STREAM, {}), (SOURCE_REST, {}),
                             (SOURCE_YFINANCE, bars_by_day)],
                            slippage_per_share=0.01, log=lambda *a: None)
    check("falls through empty higher-preference sources to yfinance",
          row_fall["_skipped"] is False and row_fall["price_source"] == SOURCE_YFINANCE)

    # -- 7. no source at all -> skip row cites every source tried ---------------------
    row_none = reprice_one(trade_long, [(SOURCE_STREAM, {}), (SOURCE_REST, {})],
                            slippage_per_share=0.01, log=lambda *a: None)
    check("skip row when no source covers it", row_none["_skipped"] is True)
    check("skip note mentions both sources tried",
          SOURCE_STREAM in row_none["note"] and SOURCE_REST in row_none["note"])
    check("skip row's price_source is blank", row_none["price_source"] == "")

    # -- 8. end-to-end run() idempotency using a temp trades.csv + monkeypatched
    # fetches for every source (no stream file, no webull keys, fake yfinance) -------
    with tempfile.TemporaryDirectory() as td:
        trades_csv = os.path.join(td, "trades.csv")
        sidecar_csv = os.path.join(td, "reprice.csv")
        config_path = os.path.join(td, "config.json")
        stream_home = os.path.join(td, "no_such_home")   # no ohlc_stream dir here
        # NEVER omit this: fetch_webull_rest_1m's keys_path defaults to the REAL
        # C:\EdgeLog\webull_keys.json (by design -- see its docstring / production use
        # from _maybe_run_reprice), and this box has real, valid keys configured. Every
        # run() call below must pass a keys_path that provably does not exist, or this
        # self-test would make a genuine read-only network call to Webull using the
        # owner's live credentials -- exactly what this repo's instructions forbid.
        no_such_keys = os.path.join(td, "no_such_webull_keys.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"slippage_per_share": 0.01}, f)
        with open(trades_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["leg", "entry_ts", "exit_ts", "side",
                                               "shares", "entry_px", "exit_px", "pnl"])
            w.writeheader()
            w.writerow({"leg": "NOISE", "entry_ts": f"{recent_day} 12:30:16",
                        "exit_ts": f"{recent_day} 15:58:05", "side": "long", "shares": "5",
                        "entry_px": "719.2731", "exit_px": "719.8505", "pnl": "2.89"})

        real_fetch = fetch_day_bars

        def fake_fetch(day, log=print):
            return bars_by_day.get(day)

        globals()["fetch_day_bars"] = fake_fetch
        try:
            silent = lambda *a: None
            run(trades_csv, sidecar_csv, config_path, apply=True, force=False,
                do_summary_json=False, stream_home=stream_home,
                webull_keys_path=no_such_keys, log=silent)
            after_first = read_sidecar(sidecar_csv)
            check("apply wrote exactly 1 sidecar row", len(after_first) == 1)
            check("row priced from yfinance (no stream file, no webull keys)",
                  after_first[("NOISE", f"{recent_day} 12:30:16")]["price_source"]
                  == SOURCE_YFINANCE)

            mtime_before = os.path.getmtime(sidecar_csv)
            run(trades_csv, sidecar_csv, config_path, apply=True, force=False,
                do_summary_json=False, stream_home=stream_home,
                webull_keys_path=no_such_keys, log=silent)
            mtime_after = os.path.getmtime(sidecar_csv)
            check("second --apply run is a no-op (idempotent, no rewrite)",
                  mtime_before == mtime_after)

            run(trades_csv, sidecar_csv, config_path, apply=True, force=True,
                do_summary_json=False, stream_home=stream_home,
                webull_keys_path=no_such_keys, log=silent)
            after_force = read_sidecar(sidecar_csv)
            check("--force overwrites the same key rather than duplicating",
                  len(after_force) == 1)
        finally:
            globals()["fetch_day_bars"] = real_fetch

    print(f"[selftest] {'ALL PASS' if ok else 'SOME FAILED'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the sidecar (default: dry run)")
    ap.add_argument("--force", action="store_true",
                     help="re-price + overwrite trades already in the sidecar")
    ap.add_argument("--summary-json", action="store_true", dest="summary_json",
                     help="print a one-line JSON summary after the table")
    ap.add_argument("--trades-csv", default=None, help="override trades.csv path")
    ap.add_argument("--sidecar", default=None, help="override reprice.csv path")
    ap.add_argument("--config", default=None, help="override config.json path")
    ap.add_argument("--selftest", action="store_true",
                     help="offline arithmetic/idempotency self-test, no network/real files")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    try:
        sys.exit(run(args.trades_csv, args.sidecar, args.config, apply=args.apply,
                      force=args.force, do_summary_json=args.summary_json))
    except Exception as e:
        print(f"[qqq-reprice] unexpected error: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(0)  # never crash noisily; this is a read-only analysis aid


if __name__ == "__main__":
    main()
