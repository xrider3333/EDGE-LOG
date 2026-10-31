#!/usr/bin/env python3
"""tools/qqq_bars_publish.py -- one small QQQ bars doc per trading day, for the Webull
paper candle charts on LEDGER > WEBULL PAPER (owner ask via MANAGER 2026-09-28: "OHLC
candles on the Webull paper trades so I can judge the price action behind each one").

WHAT IT WRITES
    users/{uid}/qqq_bars/{YYYY-MM-DD}   -- ONE doc per trading day, about 20-25 KB:
      v             schema version (SCHEMA_VERSION)
      date          the session date (New York)
      bars          {"1m": packed, "5m": packed} -- the REGULAR session only, straight
                    from the box's own settled caches (~/edgelog/ohlc/QQQ_1m.csv and
                    QQQ_5m.csv), i.e. exactly the bars the engine decided on. Packed as
                    one string per timeframe because Firestore rejects arrays of arrays:
                    "off,open,high,low,close,volume;..." where off = minutes after 09:30.
      bar_counts    {"1m": n, "5m": n}
      bars_through  {"1m": "HH:MM", "5m": "HH:MM"} -- the START of the last bar held, so
                    the chart can say "bars as of ..." (the newest bar only lands once it
                    has settled).
      bars_ext      {"1m": packed, "5m": packed} -- the EXTENDED sessions (row 74, 10-31):
                    pre-market 04:00-09:30 and after hours 16:00-20:00 ET, same packing,
                    off NEGATIVE for a pre-market bar (04:00 = -330) and >= 390 for an
                    after-hours bar (16:00 = 390). NOT the engine's cache (which is regular
                    hours only, api/qqq_exec.py prepost=False): pulled by this publisher
                    from yfinance with prepost=True into its own small cache under
                    EDGELOG_HOME/qqq_bars/QQQ_ext_{1m,5m}.csv (refresh_ext_cache; never
                    under --dry-run, --intraday or --no-ext). yfinance serves 1-minute
                    bars for the last EXT_1M_DAYS days and 5-minute bars for EXT_5M_DAYS,
                    so an older day re-published carries 5m extended bars only. A day with
                    nothing pulled yet has "" here; complete / final never depend on it.
      ext_counts    {"1m": n, "5m": n}   ext_through {"1m": "HH:MM", "5m": "HH:MM"}
      complete      True once both timeframes reach the session's last bar.
      final         True when the day can never change again (complete, or old enough),
                    so the browser may keep it forever in IndexedDB.
      marks         one entry per closed trade touching this day, keyed by trade_id,
                    joined here on the box from three ledgers (see build_mark):
                      cloud_signal/signals.csv  -> signal bar + the backtest's intended fill
                      qqq_exec/trades.csv       -> the book's fill and exit
                      qqq_exec/broker_orders.csv-> Webull's fill(s), refused tries, retries,
                                                   and tries the book held back itself
      levels_note   which legs carry stop / target lines (ORB only, row 59) -- said here and on
                    the chart; a mark with none says so instead of drawing a guess.
      marks[].lines [{price, label, dash}] -- "stop" (solid) and "target" (dashed) from the
                    ENTRY signal row's stop_px / target_px (api/cloud_signal.py writes them
                    for ORB), plus one dashed "stop moved HH:MM" per LEVELS row (breakeven
                    moved the stop); absent when the signal file has no level -- never
                    re-derived here.
      marks[].levels the same per trade, as one record for the position box (row 59):
                    {trade_id, side, entry_px, entry_t, exit_px, exit_t (the book's fills,
                    = book_in / book_out), target_px (None when none), stops: [{t, px}, ...]}
                    -- the stop LADDER oldest first: stops[0] is the initial stop, live from
                    the book's entry fill; each later step is a LEVELS row's moved stop,
                    live from the END of the bar whose close armed it (the signal row's own
                    "stop X from the next bar"). Capped at MAX_STOP_STEPS steps. Absent when
                    the signal file logged no stop and no target.
      published_at  when this copy was written -- the browser re-checks a cached final day
                    once per page load and swaps in a newer copy when this differs.

WEBULL ATTEMPTS (wb_in / wb_out, one entry per broker_orders.csv row, oldest first; the
rows of one order are joined on the signal id with its R<n> resend suffix, or the "X" a
partly crossed leg's netted row carries, stripped). `outcome` is what the chart shows --
the ledger's own outcome column (api/qqq_exec.py _broker_row_outcome) wherever the row
has one, else derived from ok / sent / mode the same way:
    OK       sent, filled (px = Webull's own price, None when not captured yet)
    REFUSED  sent, and Webull answered with a definite refusal (a 4xx; why = Webull's own
             first sentence)
    UNKNOWN  sent, but Webull's answer never came back (a hard-timeout send, a 5xx, a
             dropped connection, a pending-resolver record) -- NOT a refusal: the order may
             have landed. `then` = the next attempt on the same side when the ledger has
             one ({t, outcome, px}: what happened after -- a resend filled, refused, ...)
    HELD     not sent: the book held it back itself (why = the book's own reason, e.g.
             "nothing to close ... its OPEN was blocked")
    ERROR    not sent: the order call itself failed before anything went out (mode ERROR,
             why = the error)
    NETTED   not sent, ok: an end-of-day internal cross against another leg (px = the
             cross price) -- no Webull order was needed
    book_only is True only when no attempt was ever SENT and nothing is missing from the
    ledger. broker_orders.csv is trimmed to its newest rows by api/qqq_exec.py, so a trade
    older than the file's first row cannot be judged from it: that side is listed in
    wb_gap ("in" / "out") instead of claiming "no Webull order"; a side whose only rows
    left are resends (the first try was trimmed away) is listed in wb_part. A publish run
    first reads the copy already in Firestore and keeps its Webull rows for those sides (a
    --backfill after a bar-cache repair therefore never erases real fills).

WHY A SEPARATE DOC (and not the status doc users/{uid}/meta/qqq_exec): that doc is
republished on every throttled tick and its trades_all list already grows toward the
1 MiB cap. One doc per DAY (not per trade) because a day's trades share the same bars --
six trades on one day cost the browser one read, not six.

SAFETY
    * Standalone: never imported by api/qqq_exec.py, never runs inside its tick loop or
      order path, so nothing here can stall or change trading.
    * Reads the ledgers only; the files it ever writes are its own: the small state
      (qqq_bars/publish_state.json under EDGELOG_HOME: the intraday throttle and the
      ledgers' last row counts) and its extended-hours bar cache (qqq_bars/QQQ_ext_*.csv,
      row 74 -- never the engine's ohlc/ files), and neither under --dry-run. After its own work, every run
      but --dry-run also refreshes qqq_exec/eod_fill_gap.csv (MANAGER #152: each EOD exit
      beside the engine's 15:55-bar price, tools/eod_fill_gap.py) -- a separate measurement
      log that writes only that file and cannot change this run's docs or exit code
      (run_eod_fill_gap).
    * A ledger read that looks mid-rewrite (api/qqq_exec.py trims trades.csv and
      broker_orders.csv by truncating and rewriting them in place) is read once more a
      second later; if it still looks torn -- no header, a short or over-long row, or far
      fewer rows than the last run saw and not stable -- NOTHING is published this run (a torn read
      would otherwise write false "book only" marks into a day marked final).
    * --dry-run builds every doc, prints it (or a summary) with its size, and writes
      nothing anywhere -- no Firestore client is even created.
    * Size cap DOC_CAP_BYTES (~200 KB, a fifth of Firestore's 1 MiB doc limit): an
      oversize doc drops its 1-minute string first and refuses to publish if it is still
      too big -- checked again on the doc actually written, after the published copy's
      Webull rows are merged back in.
    * Credentials: the SAME path the exec's status publisher uses (api/qqq_exec.py
      main(): firebase_admin with --cred <service-account json>, else Application Default
      Credentials from GOOGLE_APPLICATION_CREDENTIALS). Nothing is embedded here.

MODES
    --dry-run                     print, write nothing (combine with any mode below)
    --date YYYY-MM-DD             one day (repeatable)
    --recent N                    the last N trading days in the bar cache (default 2 when
                                  no other mode is given: the post-close run republishes
                                  today and the previous day, which by then is complete)
    --backfill FROM [--to TO]     every trading day in the cache from FROM (e.g. the
                                  2026-09-03 start) -- also the way to rewrite old docs
                                  after the bar cache is repaired. More than MAX_DAYS
                                  days needs --yes-many (a mistyped FROM would otherwise
                                  write every day back to the cache's start).
    --intraday                    today only, and only when a trade closed (or a Webull
                                  order landed) since the last write, at most once every
                                  INTRADAY_MIN_SEC (no extended-hours pull: those bars
                                  land on the post-close run)
    --no-ext                      skip the extended-hours pull (the cache already on disk
                                  is still published)

SIGNAL-BAR RULE (per leg, never guessed): the chart marks a signal (decision) bar only
when the ledgers say which bar it was --
    "recorded"        any leg: the signal's reason names it ("decided at the close of the
                      10:10 bar", NOISE's decide-at-close since 2026-09-26)
    "fill bar close"  ORB only: ORB decides and prices its entry at the close of the
                      ref_time bar, so the intended price must equal that bar's close
                      exactly (within 0.0001; verified on the 2026-09-28 short, 732.33 =
                      the 10:45 bar's close)
otherwise no signal bar is drawn and the chart says "not recorded for this trade" -- NOISE
before 2026-09-26 (ref_price was the next bar's OPEN, so a price match would be a
coincidence) and ENGU-Q (its resting limit fills inside the ref_time bar some bars after
the signal). A trade row with no trade_id gets no marks at all rather than guessed ones.

BACKTEST FILL TIMES (bt_in / bt_out .t) are stamped at the moment the backtest fills: a
fill at a bar's close is stamped at that bar's END (= the next bar's start), for every
leg -- ORB's ref_time names the bar it closed on, so it is moved one bar on (its entry, and
an exit priced at that bar's close such as the end-of-day flat: a 15:55-bar close fills at
16:00); NOISE's and ENGU-Q's ref_time already is the fill moment. An ORB stop or target
exit (a level inside the bar) keeps the bar's start.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import threading
import time

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9
    ZoneInfo = None

# The ONE broker-id rule (api/trade_id.py broker_signal_base, 2026-10-10, DIP #424 live leg):
# imported so a DIP slot id's one-character slot code can never drift from the executor's.
# api/trade_id.py is stdlib-only (re, datetime) -- no heavier import chain comes with it.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from api import trade_id as _trade_id  # noqa: E402  (stdlib-only, see above)

ET = ZoneInfo("America/New_York") if ZoneInfo else None

SCHEMA_VERSION = 3                  # 2 (10-31, row 59): marks carry stop / target lines
                                    # 3 (10-31, rows 59+74): marks[].levels (stop ladder), bars_ext
COLLECTION = "qqq_bars"
DOC_CAP_BYTES = 200_000
TIMEFRAMES = ("1m", "5m")
TF_MIN = {"1m": 1, "5m": 5}
SESSION_OPEN_MIN = 9 * 60 + 30      # 09:30 ET
SESSION_CLOSE_MIN = 16 * 60         # 16:00 ET (last bar starts before this)
DEFAULT_START = "2026-09-03"        # the Webull paper book's first day
INTRADAY_MIN_SEC = 300
PUBLISH_TIMEOUT_SEC = 20.0
FINAL_AFTER_DAYS = 3                # a day this old is final even if a bar is missing
EXT_OPEN_MIN = 4 * 60               # 04:00 ET: the pre-market's first bar (row 74)
EXT_CLOSE_MIN = 20 * 60             # 20:00 ET: after hours end (the last bar starts before this)
EXT_1M_DAYS = 7                     # yfinance serves 1-minute bars for the last 7 days only ...
EXT_5M_DAYS = 59                    # ... and 5-minute bars for the last 60
MAX_STOP_STEPS = 12                 # a trade's stop ladder is capped here (doc size)
LEVELS_NOTE = "stop and target are not recorded yet"
LEVELS_NOTE_SOME = ("stop and target lines: ORB only (from its signal file, with the stop's "
                    "breakeven moves); other legs not recorded yet")
REASON_MAX = 140
MAX_DAYS = 40                       # --backfill wider than this needs --yes-many
PRICE_EXACT = 0.0001                # "fill bar close" = the bar's close to 4 decimals
LEDGER_RETRY_SEC = 1.0              # a torn ledger read is retried once after this
LEDGER_DROP_FRAC = 0.5              # fewer rows than this x the last run's = suspicious

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")
_RESEND_RE = re.compile(r"R\d+$")
# what is stripped to join a row to its order: a resend's R<n>, or the "X" of a partly
# crossed leg's netted row (api/qqq_exec.py _record_internal_cross: CLOSE id + "X")
_SUFFIX_RE = re.compile(r"(?:R\d+|X)$")
# the SAME pattern as api/webull_orders.py _HTTP_STATUS_RE (a unit test pins the two)
_HTTP_STATUS_RE = re.compile(r"HTTP(?: Status:)?\s*(\d{3})")
_DECIDED_RE = re.compile(r"decided at the close of the (\d{1,2}):(\d{2}) bar")
_REQID_RE = re.compile(r",?\s*RequestID:.*$")
_MSG_RE = re.compile(r"Msg:\s*(.+)$")


# ── paths ──────────────────────────────────────────────────────────────────────────
def edgelog_home():
    h = os.environ.get("EDGELOG_HOME")
    if h:
        return h
    if os.name == "nt":
        return r"C:\EdgeLog"
    return os.path.expanduser("~/edgelog")


def default_paths(home=None, ohlc_dir=None, exec_dir=None, signals=None):
    home = home or edgelog_home()
    ohlc_dir = ohlc_dir or os.path.join(home, "ohlc")
    exec_dir = exec_dir or os.environ.get("EDGELOG_QQQ_EXEC_DIR") or os.path.join(home, "qqq_exec")
    return {
        "home": home,
        "bars": {"1m": os.path.join(ohlc_dir, "QQQ_1m.csv"),
                 "5m": os.path.join(ohlc_dir, "QQQ_5m.csv")},
        "trades": os.path.join(exec_dir, "trades.csv"),
        "broker_orders": os.path.join(exec_dir, "broker_orders.csv"),
        # the executor's open lots (MANAGER #247: a DIP lot held for days had no chart mark
        # until it was sold) -- read only, never written here
        "exec_state": os.path.join(exec_dir, "state.json"),
        "signals": signals or os.path.join(home, "cloud_signal", "signals.csv"),
        "state": os.path.join(home, "qqq_bars", "publish_state.json"),
        # the publisher's OWN extended-hours cache (row 74) -- never the engine's ohlc/ files
        "ext": {"1m": os.path.join(home, "qqq_bars", "QQQ_ext_1m.csv"),
                "5m": os.path.join(home, "qqq_bars", "QQQ_ext_5m.csv")},
        # row 74 follow-up (MANAGER #237): Alpaca SIP pre/post bars, pulled on the PC (the key
        # never leaves it) by tools/push_qqq_ext_alpaca.py and copied here; a day it covers
        # wins over the yfinance cache above, which stays the fallback
        "ext_alpaca": {"1m": os.path.join(home, "qqq_bars", "QQQ_ext_alpaca_1m.csv"),
                       "5m": os.path.join(home, "qqq_bars", "QQQ_ext_alpaca_5m.csv")},
    }


# ── time helpers ─────────────────────────────────────────────────────────────────────
def _fmt_et(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


def to_et_str(ts):
    """Any ledger timestamp -> 'YYYY-MM-DD HH:MM:SS' New York time, or None.
    ISO strings with an offset (signals.csv ref_time) are converted; naive strings
    (trades.csv / broker_orders.csv, written by a TZ=America/New_York host) are ET."""
    s = str(ts or "").strip()
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(ET)
    return _fmt_et(d)


def _minute_of(et_str):
    return int(et_str[11:13]) * 60 + int(et_str[14:16])


def _et_now():
    return dt.datetime.now(ET)


# ── bars ─────────────────────────────────────────────────────────────────────────────
def _in_session(m, session):
    """Is minute-of-day `m` (ET) inside the regular session ("rth") or the extended ones
    ("ext": pre-market 04:00-09:30 and after hours 16:00-20:00)?"""
    if session == "ext":
        return EXT_OPEN_MIN <= m < SESSION_OPEN_MIN or SESSION_CLOSE_MIN <= m < EXT_CLOSE_MIN
    return SESSION_OPEN_MIN <= m < SESSION_CLOSE_MIN


def load_bars(path, session="rth"):
    """{date: [(start_min, o, h, l, c, v), ...]} for regular-session bars only (or, with
    session="ext", the pre-market and after-hours bars only), keyed by the New York
    session date, oldest first, one row per bar start (last wins)."""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                t = int(float(row["time"]))
                vals = [float(row[k]) for k in ("open", "high", "low", "close")]
                vol = float(row.get("volume") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            d = dt.datetime.fromtimestamp(t, ET)
            m = d.hour * 60 + d.minute
            if not _in_session(m, session):
                continue
            day = out.setdefault(d.date().isoformat(), {})
            day[m] = (m, vals[0], vals[1], vals[2], vals[3], vol)
    return {k: [v[m] for m in sorted(v)] for k, v in out.items()}


def _px(x):
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def pack_bars(rows):
    """'off,o,h,l,c,v;...' with off = minutes after 09:30 ET (see the module docstring);
    an extended-hours bar's off is negative (pre-market) or >= 390 (after hours)."""
    return ";".join(f"{m - SESSION_OPEN_MIN},{_px(o)},{_px(h)},{_px(l)},{_px(c)},{int(round(v))}"
                    for (m, o, h, l, c, v) in rows)


def unpack_bars(s, date):
    """Inverse of pack_bars -> [{'t': 'YYYY-MM-DD HH:MM', 'o','h','l','c','v'}]."""
    out = []
    for part in (s or "").split(";"):
        if not part:
            continue
        off, o, h, l, c, v = part.split(",")
        m = SESSION_OPEN_MIN + int(off)
        out.append({"t": f"{date} {m // 60:02d}:{m % 60:02d}", "o": float(o), "h": float(h),
                    "l": float(l), "c": float(c), "v": int(v)})
    return out


def _bar_index(rows):
    return {m: r for r in rows for m in [r[0]]}


def _hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


# ── extended-hours bars (row 74) ─────────────────────────────────────────────────────
def fetch_yf_ext(start_date, end_date, tf):
    """QQQ bars WITH pre/post market from yfinance (the feed the box already pulls its
    regular-hours fallback from, api/cloud_signal.py), start_date..end_date inclusive
    (YYYY-MM-DD), interval `tf` -> [(epoch, o, h, l, c, v), ...], every bar the feed
    returned (the caller keeps the extended-hours ones). Raises on any feed failure."""
    import yfinance as yf  # the box has it (api/cloud_signal.py); the PC may not
    end = dt.date.fromisoformat(end_date) + dt.timedelta(days=1)
    df = yf.Ticker("QQQ").history(start=start_date, end=end.isoformat(), interval=tf,
                                  prepost=True, auto_adjust=False)
    out = []
    if df is None or not len(df):
        return out
    for idx, row in df.iterrows():
        try:
            out.append((int(idx.timestamp()), float(row["Open"]), float(row["High"]),
                        float(row["Low"]), float(row["Close"]), float(row.get("Volume") or 0.0)))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _is_ext_epoch(t):
    d = dt.datetime.fromtimestamp(int(t), ET)
    return _in_session(d.hour * 60 + d.minute, "ext")


def merge_bar_csv(path, rows):
    """Merge [(epoch, o, h, l, c, v), ...] into the epoch-schema CSV at `path` (same
    columns as the engine's caches), one row per bar start, the new value winning,
    oldest first; written whole via a temp file. Returns the row count on disk."""
    have = {}
    for r in _read_csv(path):
        try:
            have[int(float(r["time"]))] = (r["open"], r["high"], r["low"], r["close"], r.get("volume") or "0")
        except (KeyError, TypeError, ValueError):
            continue
    for (t, o, h, l, c, v) in rows:
        have[int(t)] = (_px(o), _px(h), _px(l), _px(c), str(int(round(v))))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for t in sorted(have):
            w.writerow([t, *have[t]])
    os.replace(tmp, path)
    return len(have)


def refresh_ext_cache(paths, days, now=None, fetch=fetch_yf_ext, log=print):
    """Pull the extended-hours bars of `days` (YYYY-MM-DD) and merge them into the
    publisher's own caches (paths["ext"]). The feed's reach is limited (EXT_1M_DAYS /
    EXT_5M_DAYS back from today), so older picked days get what the cache already holds.
    Best effort: a feed failure is logged and the publish goes on without new bars --
    the chart then shows the regular session alone, never a guess. Returns {tf: rows
    merged} (0 when nothing was pulled for that timeframe)."""
    now = now or _et_now()
    merged = {}
    if not days:
        return merged
    hi = max(days)
    for tf, span in (("1m", EXT_1M_DAYS), ("5m", EXT_5M_DAYS)):
        lo = max(min(days), (now.date() - dt.timedelta(days=span)).isoformat())
        if lo > hi:
            log(f"[qqq-bars] ext {tf}: {hi} is older than the feed's {span}-day reach -- cache only")
            merged[tf] = 0
            continue
        try:
            rows = [r for r in fetch(lo, hi, tf) if _is_ext_epoch(r[0])]
            merge_bar_csv(paths["ext"][tf], rows)
            merged[tf] = len(rows)
            log(f"[qqq-bars] ext {tf}: {len(rows)} extended-hours bars {lo}..{hi} merged into "
                f"{paths['ext'][tf]}")
        except Exception as e:  # noqa: BLE001 -- a display feed never fails the publish
            merged[tf] = 0
            log(f"[qqq-bars] ext {tf}: pull failed ({type(e).__name__}: {e}) -- the regular "
                f"session publishes alone")
    return merged


EXT_SRC_ALPACA = "Alpaca SIP 1m/5m (pulled on the PC, tools/push_qqq_ext_alpaca.py)"
EXT_SRC_YF = "yfinance prepost (publisher's own cache, not the engine's)"


def load_ext(paths):
    """{tf: {date: rows}} of extended-hours bars plus "_src": {date: source words}. Per
    day and timeframe, the Alpaca cache (paths["ext_alpaca"]) wins whenever it holds that
    day; the yfinance cache fills the rest."""
    out, src = {}, {}
    alp_paths = paths.get("ext_alpaca") or {}
    for tf in TIMEFRAMES:
        yf_days = load_bars(paths["ext"][tf], session="ext")
        al_days = load_bars(alp_paths.get(tf), session="ext") if alp_paths.get(tf) else {}
        merged = dict(yf_days)
        merged.update(al_days)
        out[tf] = merged
        for d in merged:
            if d in al_days:
                src[d] = EXT_SRC_ALPACA
            else:
                src.setdefault(d, EXT_SRC_YF)
    out["_src"] = src
    return out


# ── ledgers ──────────────────────────────────────────────────────────────────────────
def _read_csv(path):
    if not path or not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class LedgerUnreliable(Exception):
    pass


def _ledger_problem(path, rows, fieldnames, prev_count):
    """Why a ledger read looks torn (see SAFETY), or None. `rows` of a missing file is
    [] with fieldnames None, which is fine: a book that never wrote one has no rows."""
    if not os.path.isfile(path):
        return None
    if os.path.getsize(path) == 0 or not fieldnames:
        return "no header (file empty or mid-rewrite)"
    for r in rows:
        if None in r.values():
            return "a short row (file cut off mid-write)"
        if None in r:
            # csv.DictReader files the extra fields of an over-long row under the key None
            # (two rows run together, or a row written over a half-rewritten one)
            return "an over-long row (file mid-rewrite)"
    if prev_count and len(rows) < prev_count * LEDGER_DROP_FRAC:
        return f"{len(rows)} rows, the last run saw {prev_count}"
    return None


def read_ledger(path, prev_count=None, sleep=time.sleep):
    """Rows of one of the exec's ledgers, read again once LEDGER_RETRY_SEC later when the
    first read looks torn. Raises LedgerUnreliable when the second read is still torn --
    except a row-count drop that holds still across both reads (a real clean-up, not a
    trim caught mid-write), which is accepted."""
    def once():
        if not path or not os.path.isfile(path):
            return [], None
        with open(path, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            rows = list(rd)
            return rows, rd.fieldnames
    rows, fields = once()
    why = _ledger_problem(path, rows, fields, prev_count)
    if why is None:
        return rows
    sleep(LEDGER_RETRY_SEC)
    rows2, fields2 = once()
    why2 = _ledger_problem(path, rows2, fields2, prev_count)
    if why2 is None:
        return rows2
    if why2.endswith(f"saw {prev_count}") and len(rows2) == len(rows) \
            and _ledger_problem(path, rows2, fields2, None) is None:
        return rows2
    raise LedgerUnreliable(f"{os.path.basename(path)}: {why2}")


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def signal_id_base(trade_id, intent):
    """The broker signal id qqq_exec derives from a trade id ("qx" + the id's letters and
    digits + O/C, a DIP mechanism slot as its one-character code) -- api/trade_id.py
    broker_signal_base, the ONE rule api/qqq_exec.py _broker_signal_id also uses (a unit test
    still pins the two together). OPEN / CLOSE only (anything else raises KeyError)."""
    {"OPEN": "O", "CLOSE": "C"}[str(intent).upper()]
    return _trade_id.broker_signal_base(str(trade_id), str(intent).upper())


def broker_by_base(rows):
    """{signal_id without its R<n> resend / X partial-cross suffix: [rows oldest first]}"""
    out = {}
    for r in rows:
        if _truthy(r.get("duplicate")):
            continue    # the adapter's own duplicate refusal, not a real attempt
        sid = str(r.get("signal_id") or "")
        m = _SUFFIX_RE.search(sid)
        out.setdefault(sid[:m.start()] if m else sid, []).append(r)
    return out


def signals_by_trade(rows):
    """{trade_id: {"ENTRY": row, "EXIT": row, "LEVELS": [row, ...]}} -- the LAST row of
    ENTRY / EXIT wins; every LEVELS row (the stop moved, row 59) is kept in file order;
    VOID_ENTRY (a phantom the backtest never takes) and SEED rows are ignored."""
    out = {}
    for r in rows:
        tid = str(r.get("trade_id") or "").strip()
        ev = str(r.get("event") or "").upper()
        if tid and ev in ("ENTRY", "EXIT"):
            out.setdefault(tid, {})[ev] = r
        elif tid and ev == "LEVELS":
            out.setdefault(tid, {}).setdefault("LEVELS", []).append(r)
    return out


def leg_timeframe(leg):
    return "1m" if str(leg or "").upper().startswith("ENGUQ") else "5m"


# ── marks ────────────────────────────────────────────────────────────────────────────
def _bar_start_for(et_str, tf):
    step = TF_MIN[tf]
    m = _minute_of(et_str)
    return m - ((m - SESSION_OPEN_MIN) % step)


def _is_orb(leg):
    return str(leg or "").upper().startswith("ORB")


def signal_bar(sig, tf, bars_by_day, leg=""):
    """(bar start 'YYYY-MM-DD HH:MM', rule) or (None, 'not recorded') -- see the module
    docstring's SIGNAL-BAR RULE. `sig` is one signals.csv row, `leg` its leg name."""
    ref = to_et_str(sig.get("ref_time"))
    px = _num(sig.get("ref_price"))
    if not ref:
        return None, "not recorded"
    day = ref[:10]
    m = _DECIDED_RE.search(str(sig.get("reason") or ""))
    if m:
        return f"{day} {int(m.group(1)):02d}:{m.group(2)}", "recorded"
    # only ORB's ENTRY is known to be decided and priced at one bar's close; its exits
    # (stop / target / end of day) are not, so a price match there proves nothing
    if px is None or not _is_orb(leg or sig.get("leg")) \
            or str(sig.get("event") or "ENTRY").upper() != "ENTRY":
        return None, "not recorded"
    start = _bar_start_for(ref, tf)
    b = _bar_index(bars_by_day.get(tf, {}).get(day, [])).get(start)
    if b is not None and abs(b[4] - px) < PRICE_EXACT:
        return f"{day} {_hhmm(start)}", "fill bar close"
    return None, "not recorded"


def _orb_exit_fill_rule(sig, tf, bars_by_day, leg=""):
    """"fill bar close" for an ORB EXIT priced at its ref_time bar's close (within
    PRICE_EXACT) -- the end-of-day flat, ORB_3_6's sc[-1] -- else None. Only the fill TIME
    uses this: the bar is still not a decision bar, so no exit signal outline is drawn
    (MANAGER build review 2026-09-30: the 09-28 short's 15:55-bar close 736.53 was shown
    as a 15:55 exit, four minutes before the book's 15:59:01 flatten, when it filled at
    16:00)."""
    px = _num(sig.get("ref_price"))
    ref = to_et_str(sig.get("ref_time"))
    if px is None or not ref or not _is_orb(leg or sig.get("leg")):
        return None
    b = _bar_index(bars_by_day.get(tf, {}).get(ref[:10], [])).get(_bar_start_for(ref, tf))
    return "fill bar close" if b is not None and abs(b[4] - px) < PRICE_EXACT else None


def _bt_fill(sig, rule, tf):
    """The backtest's fill as {t, px}, stamped at the fill moment (BACKTEST FILL TIMES):
    a "fill bar close" price moves the ref_time bar's start on to that bar's end."""
    t = to_et_str(sig.get("ref_time"))
    if t and rule == "fill bar close":
        t = _fmt_et(dt.datetime.strptime(t, "%Y-%m-%d %H:%M:%S") + dt.timedelta(minutes=TF_MIN[tf]))
    return {"t": t, "px": _num(sig.get("ref_price"))}


def _short_reason(why):
    """First sentence of a refusal reason, capped at REASON_MAX characters."""
    why = str(why or "").strip()
    first = why.split(". ")[0].rstrip(".")
    if len(first) > REASON_MAX:
        first = first[:REASON_MAX - 3].rstrip() + "..."
    return first


def _definite_4xx(reason):
    """True when a failed send's reason carries a 4xx HTTP status -- Webull answering that
    it refused the order (api/qqq_exec.py _broker_row_ambiguous_send's own test)."""
    m = _HTTP_STATUS_RE.search(str(reason or ""))
    return bool(m) and 400 <= int(m.group(1)) < 500


def row_outcome(r):
    """One broker_orders.csv row -> OK / REFUSED / UNKNOWN / HELD / ERROR / NETTED (see
    WEBULL ATTEMPTS). The ledger's own outcome column wins wherever the row has one; a
    row written before that column existed is read the way api/qqq_exec.py
    _broker_row_outcome would have written it. A blank `sent` reads as sent (the old
    meaning)."""
    sent_raw = str(r.get("sent") or "").strip()
    sent = True if not sent_raw else _truthy(sent_raw)
    ok = _truthy(r.get("ok"))
    col = str(r.get("outcome") or "").strip().upper()
    mode = str(r.get("mode") or "").strip().upper()
    if mode == "BLOCKED" or col == "BLOCKED":
        return "HELD"             # a rail stopped it, whatever the sent field says
    if not sent:
        # never reached Webull, whatever the column calls it (the exec's own column says
        # REFUSED for a failed adapter call and BLOCKED for a rail -- neither is Webull's).
        # Only a real internal cross is NETTED (_record_internal_cross writes the column
        # and "crossed internally"); an ok row logged while orders were OFF is held back.
        if col == "NETTED" or (ok and "crossed internally" in str(r.get("reason") or "")):
            return "NETTED"
        return "ERROR" if mode == "ERROR" else "HELD"
    if col == "UNKNOWN":
        return "UNKNOWN"
    if col in ("OK", "REFUSED"):
        return col
    if col:
        # an outcome this reader does not know (WORKING, ...): never call it a refusal
        return "OK" if ok else "UNKNOWN"
    if ok:
        return "OK"
    return "REFUSED" if _definite_4xx(r.get("reason")) else "UNKNOWN"


def _wb_attempts(rows):
    """broker_orders.csv rows -> attempts (see WEBULL ATTEMPTS in the module docstring)."""
    out = []
    for r in rows or []:
        sent_raw = str(r.get("sent") or "").strip()
        sent = True if not sent_raw else _truthy(sent_raw)
        ok = _truthy(r.get("ok"))
        why = _REQID_RE.sub("", str(r.get("reason") or "")).strip()
        msg = _MSG_RE.search(why) if sent else None
        if msg:     # Webull's own sentence reads better than its HTTP preamble
            why = msg.group(1).strip()
        why = _short_reason(why)
        a = {
            "t": to_et_str(r.get("ts_et")),
            "px": _num(r.get("broker_fill_px")),
            "ok": bool(ok),
            "sent": bool(sent),
            "outcome": row_outcome(r),
            "side": str(r.get("side") or "").upper(),
            "why": why,
        }
        if _RESEND_RE.search(str(r.get("signal_id") or "")):
            a["resend"] = True
        out.append(a)
    # an answer that never came back: what the ledger shows happened next on this side
    for i, a in enumerate(out):
        if a["outcome"] == "UNKNOWN" and i + 1 < len(out):
            n = out[i + 1]
            a["then"] = {"t": n["t"], "outcome": n["outcome"], "px": n["px"]}
    return out


def ledger_from(broker_rows):
    """The oldest ts_et still in broker_orders.csv ('YYYY-MM-DD HH:MM:SS' ET), or None
    when it holds no rows at all -- every older Webull row has been trimmed away."""
    ts = [t for t in (to_et_str(r.get("ts_et")) for r in broker_rows or []) if t]
    return min(ts) if ts else None


def entry_lines(ent):
    """The ENTRY signal row's stop / target as chart lines ([] when it logged none)."""
    out = []
    for key, label, dash in (("stop_px", "stop", False), ("target_px", "target", True)):
        px = _num(ent.get(key))
        if px is not None and px > 0:
            out.append({"price": round(px, 4), "label": label, "dash": dash})
    return out


def _level_px(row, key):
    px = _num((row or {}).get(key))
    return round(px, 4) if px is not None and px > 0 else None


def _bar_end_et(ref_time, tf):
    """A LEVELS row's moved stop is live 'from the next bar': the END of its ref_time bar."""
    t = to_et_str(ref_time)
    if not t:
        return None
    return _fmt_et(dt.datetime.strptime(t, "%Y-%m-%d %H:%M:%S") + dt.timedelta(minutes=TF_MIN[tf]))


def stop_ladder(ent, levels_rows, entry_t, tf):
    """[{t, px}, ...] oldest first (row 59): the ENTRY row's stop, live from the book's
    entry fill `entry_t`, then each LEVELS row's moved stop, live from the end of the bar
    whose close armed it. Rows without a stop are skipped; capped at MAX_STOP_STEPS."""
    steps = []
    px = _level_px(ent, "stop_px")
    if px is not None:
        steps.append({"t": entry_t, "px": px})
    for r in levels_rows or []:
        px = _level_px(r, "stop_px")
        if px is not None:
            steps.append({"t": _bar_end_et(r.get("ref_time"), tf), "px": px})
    return steps[:MAX_STOP_STEPS]


def moved_stop_lines(levels_rows, tf):
    """One dashed chart line per LEVELS row: 'stop moved HH:MM' (the bar end it took)."""
    out = []
    for r in levels_rows or []:
        px = _level_px(r, "stop_px")
        t = _bar_end_et(r.get("ref_time"), tf)
        if px is not None:
            out.append({"price": px, "label": "stop moved" + (f" {t[11:16]}" if t else ""), "dash": True})
    return out


def trade_levels(mark, ent, levels_rows, tf):
    """The per-trade levels record (see the module docstring, marks[].levels), or None
    when the signal file logged neither a stop nor a target for this trade."""
    entry_t = (mark.get("book_in") or {}).get("t")
    stops = stop_ladder(ent, levels_rows, entry_t, tf)
    target = _level_px(ent, "target_px")
    if not stops and target is None:
        return None
    return {"trade_id": mark["trade_id"], "side": mark.get("side"),
            "entry_px": (mark.get("book_in") or {}).get("px"), "entry_t": entry_t,
            "exit_px": (mark.get("book_out") or {}).get("px"),
            "exit_t": (mark.get("book_out") or {}).get("t"),
            "target_px": target, "stops": stops}


def build_mark(trade, sigs, brokers, bars_by_day, shadow=False, wb_from=False):
    """One trade's markers, or None when the row has no trade_id (never guessed).
    `wb_from` = ledger_from(broker_orders.csv): a side with no Webull row that happened
    before it (or any side at all when the file holds no rows: wb_from None) is listed in
    wb_gap instead of being called "no Webull order"; False skips the check."""
    tid = str(trade.get("trade_id") or "").strip()
    if not tid:
        return None
    leg = str(trade.get("leg") or "")
    tf = leg_timeframe(leg)
    sig = sigs.get(tid, {})
    mark = {"trade_id": tid, "leg": leg, "side": str(trade.get("side") or "").lower(), "tf": tf}
    ent = sig.get("ENTRY")
    if ent:
        t, rule = signal_bar(ent, tf, bars_by_day, leg=ent.get("leg") or leg)
        mark["signal"] = {"t": t, "rule": rule}
        mark["bt_in"] = _bt_fill(ent, rule, tf)
        lines = entry_lines(ent) + moved_stop_lines(sig.get("LEVELS"), tf)
        if lines:
            mark["lines"] = lines
    else:
        mark["signal"] = None
        mark["bt_in"] = None
    ex = sig.get("EXIT")
    if ex:
        t, rule = signal_bar(ex, tf, bars_by_day, leg=ex.get("leg") or leg)
        mark["signal_out"] = {"t": t, "rule": rule}
        fill_rule = _orb_exit_fill_rule(ex, tf, bars_by_day, leg=ex.get("leg") or leg) or rule
        mark["bt_out"] = _bt_fill(ex, fill_rule, tf)
    else:
        mark["signal_out"] = None
        mark["bt_out"] = None
    mark["book_in"] = {"t": to_et_str(trade.get("entry_ts")), "px": _num(trade.get("entry_px"))}
    mark["book_out"] = {"t": to_et_str(trade.get("exit_ts")), "px": _num(trade.get("exit_px")),
                        "why": str(trade.get("exit_reason") or "")[:REASON_MAX]}
    if ent:
        lv = trade_levels(mark, ent, sig.get("LEVELS"), tf)
        if lv:
            mark["levels"] = lv
    if shadow:
        mark["shadow"] = True
        mark["wb_in"], mark["wb_out"] = [], []
    else:
        raw = {"wb_in": brokers.get(signal_id_base(tid, "OPEN")) or [],
               "wb_out": brokers.get(signal_id_base(tid, "CLOSE")) or []}
        mark["wb_in"] = _wb_attempts(raw["wb_in"])
        mark["wb_out"] = _wb_attempts(raw["wb_out"])
        gap, part = [], []
        for side, key, ts_key in (("in", "wb_in", "entry_ts"), ("out", "wb_out", "exit_ts")):
            t = to_et_str(trade.get(ts_key))
            if wb_from is not False and not mark[key] and (wb_from is None or (t and t < wb_from)):
                gap.append(side)
            elif wb_from is not False and raw[key] and all(
                    _SUFFIX_RE.search(str(r.get("signal_id") or "")) for r in raw[key]):
                # every row left is a resend (or a partial cross): the first try -- the
                # un-suffixed row, always written before any resend -- was trimmed away
                part.append(side)
        if gap:
            mark["wb_gap"] = gap
        if part:
            mark["wb_part"] = part
    if trade.get("open"):
        mark["open"] = True        # held lot: entry only, no exit yet
        mark.pop("book_out", None)  # the page draws any book_out it finds
    _set_book_only(mark)
    return mark


def _set_book_only(mark):
    """book_only = no attempt was ever SENT to Webull and no side is missing (wb_gap)."""
    sent = any(a.get("sent", True) for a in (mark.get("wb_in") or []) + (mark.get("wb_out") or []))
    mark["book_only"] = bool(mark.get("shadow")) or (not sent and not mark.get("wb_gap"))


def _att_key(a):
    return (a.get("t"), a.get("outcome"), a.get("px"), a.get("sent"), a.get("ok"))


def merge_prior_marks(doc, prior):
    """Keep the Webull rows the copy already in Firestore has for any side this run
    cannot fully see any more (the ledger was trimmed since): a whole side (wb_gap) is
    taken over from that copy; a side cut inside (wb_part: a refused first try gone, its
    resend kept) gets the copy's rows OLDER than the first one still on file put back in
    front. Returns how many sides were filled in. `prior` is that copy (or None)."""
    if not prior:
        return 0
    old = {m.get("trade_id"): m for m in prior.get("marks") or [] if isinstance(m, dict)}
    filled = 0
    for m in doc.get("marks") or []:
        gap = list(m.get("wb_gap") or [])
        part = list(m.get("wb_part") or [])
        p = old.get(m.get("trade_id"))
        if (not gap and not part) or not p:
            continue
        p_gap = set(p.get("wb_gap") or [])
        for side in list(gap):
            key = "wb_" + side
            if side in p_gap:
                continue
            m[key] = list(p.get(key) or [])
            gap.remove(side)
            filled += 1
        for side in list(part):
            key = "wb_" + side
            if side in p_gap:
                continue
            cur = list(m.get(key) or [])
            first = min((a.get("t") or "" for a in cur), default="")
            have = {_att_key(a) for a in cur}
            older = [a for a in (p.get(key) or [])
                     if isinstance(a, dict) and (a.get("t") or "") < first and _att_key(a) not in have]
            if not older:
                continue    # the copy lacks them too: the side stays marked as cut
            older = [dict(a) for a in older]
            if cur and older[-1].get("outcome") == "UNKNOWN" and not older[-1].get("then"):
                # an unanswered try whose "what happened next" is the first row kept
                n = cur[0]
                older[-1]["then"] = {"t": n.get("t"), "outcome": n.get("outcome"), "px": n.get("px")}
            m[key] = older + cur
            part.remove(side)
            filled += 1
        if gap:
            m["wb_gap"] = gap
        else:
            m.pop("wb_gap", None)
        if part:
            m["wb_part"] = part
        else:
            m.pop("wb_part", None)
        _set_book_only(m)
    return filled


def open_trade_rows(state_path):
    """The executor's open lots (state.json legs with shares left) as trades.csv-shaped
    rows with no exit and "open": True, so a held lot gets its entry mark the day it is
    bought instead of the day it is sold. [] when the file is missing or unreadable."""
    try:
        with open(state_path, encoding="utf-8") as f:
            legs = (json.load(f) or {}).get("legs") or {}
    except (OSError, ValueError, TypeError):
        return []
    out = []
    for key, lg in legs.items():
        if not isinstance(lg, dict):
            continue
        tid = str(lg.get("trade_id") or "").strip()
        left = _num(lg.get("shares_remaining"))
        if not tid or not left or left <= 0 or not lg.get("entry_ts"):
            continue
        out.append({"leg": lg.get("leg") or key, "trade_id": tid, "side": lg.get("side") or "",
                    "shares": left, "entry_ts": lg.get("entry_ts"), "entry_px": lg.get("entry_px"),
                    "exit_ts": "", "exit_px": "", "exit_reason": "", "open": True})
    return out


def touches_day(trade, date):
    """True when the book's entry or exit falls on `date` (New York)."""
    e = to_et_str(trade.get("entry_ts")) or ""
    x = to_et_str(trade.get("exit_ts")) or ""
    return e[:10] == date or x[:10] == date


# ── the day doc ──────────────────────────────────────────────────────────────────────
def load_all(paths, shadow_paths=(), prev_counts=None, sleep=time.sleep):
    """Everything one run needs. Raises LedgerUnreliable when trades.csv or
    broker_orders.csv reads torn twice (see SAFETY); `prev_counts` = the row counts the
    last run saw ({"trades": n, "broker_orders": n}), from the state file."""
    prev_counts = prev_counts or {}
    bars = {tf: load_bars(paths["bars"][tf]) for tf in TIMEFRAMES}
    trade_rows = read_ledger(paths["trades"], prev_counts.get("trades"), sleep=sleep)
    broker_rows = read_ledger(paths["broker_orders"], prev_counts.get("broker_orders"), sleep=sleep)
    trades = [(r, False) for r in trade_rows]
    closed_ids = {str(r.get("trade_id") or "").strip() for r in trade_rows}
    trades += [(r, False) for r in open_trade_rows(paths.get("exec_state"))
               if r["trade_id"] not in closed_ids]
    for sp in shadow_paths or ():
        trades += [(r, True) for r in _read_csv(sp)]
    return {
        "bars": bars,
        "bars_ext": load_ext(paths),
        "trades": trades,
        "sigs": signals_by_trade(_read_csv(paths["signals"])),
        "brokers": broker_by_base(broker_rows),
        "wb_from": ledger_from(broker_rows),
        "counts": {"trades": len(trade_rows), "broker_orders": len(broker_rows)},
    }


def trading_days(data):
    days = set()
    for tf in TIMEFRAMES:
        days.update(data["bars"].get(tf, {}).keys())
    return sorted(days)


def _last_bar_min(tf):
    return SESSION_CLOSE_MIN - TF_MIN[tf]


def build_day_doc(date, data, now=None):
    now = now or _et_now()
    bars, counts, through = {}, {}, {}
    complete = True
    for tf in TIMEFRAMES:
        rows = data["bars"].get(tf, {}).get(date, [])
        bars[tf] = pack_bars(rows)
        counts[tf] = len(rows)
        through[tf] = _hhmm(rows[-1][0]) if rows else None
        if not rows or rows[-1][0] < _last_bar_min(tf):
            complete = False
    ext, ext_counts, ext_through = {}, {}, {}
    for tf in TIMEFRAMES:
        rows = (data.get("bars_ext") or {}).get(tf, {}).get(date, [])
        ext[tf] = pack_bars(rows)
        ext_counts[tf] = len(rows)
        ext_through[tf] = _hhmm(rows[-1][0]) if rows else None
    marks = []
    for t, shadow in data["trades"]:
        if touches_day(t, date):
            m = build_mark(t, data["sigs"], data["brokers"], data["bars"], shadow=shadow,
                           wb_from=data.get("wb_from", False))
            if m is not None:
                marks.append(m)
    today = now.date().isoformat()
    old = (now.date() - dt.date.fromisoformat(date)).days >= FINAL_AFTER_DAYS
    final = bool((complete and date < today) or old)
    return {
        "v": SCHEMA_VERSION,
        "date": date,
        "tz": "America/New_York",
        "session": "rth",
        "source": "box settled bar cache",
        "bars": bars,
        "bar_counts": counts,
        "bars_through": through,
        "complete": complete,
        "final": final,
        "bars_ext": ext,
        "ext_counts": ext_counts,
        "ext_through": ext_through,
        "ext_session": "pre-market 04:00-09:30 (off < 0) and after hours 16:00-20:00 (off >= 390) ET",
        "ext_source": ((data.get("bars_ext") or {}).get("_src") or {}).get(date, EXT_SRC_YF),
        "marks": marks,
        "levels_note": LEVELS_NOTE_SOME if any(m.get("lines") for m in marks) else LEVELS_NOTE,
        "published_at": now.isoformat(timespec="seconds"),
    }


class DocTooLarge(Exception):
    pass


def doc_size(doc):
    """Bytes of the doc as compact JSON -- a slight over-estimate of Firestore's own
    size accounting for these string-heavy docs, which is the safe direction."""
    return len(json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def enforce_cap(doc, cap=DOC_CAP_BYTES):
    """Drop, in order, the extended-hours 1-minute string, every extended-hours string,
    then the regular 1-minute string before failing (the 5-minute bars and the marks are
    the small, essential part). Raises DocTooLarge when even that is not enough."""
    if doc_size(doc) <= cap:
        return doc
    doc = dict(doc)
    doc["bars_dropped"] = []
    ext = dict(doc.get("bars_ext") or {})
    if ext.get("1m"):
        doc["bars_ext"] = {k: v for k, v in ext.items() if k != "1m"}
        doc["bars_dropped"].append("ext_1m")
    if doc_size(doc) > cap and any((doc.get("bars_ext") or {}).values()):
        doc["bars_ext"] = {}
        doc["bars_dropped"].append("ext")
    if doc_size(doc) > cap:
        doc["bars"] = {k: v for k, v in doc["bars"].items() if k != "1m"}
        doc["bars_dropped"].append("1m")
        doc["final"] = False
    if doc_size(doc) > cap:
        raise DocTooLarge(f"{doc['date']}: {doc_size(doc)} bytes even without 1-minute bars "
                          f"(cap {cap})")
    return doc


def fingerprint(doc):
    """What the intraday mode compares: which trades are closed and which Webull
    attempts exist -- NOT the bars (they change every minute)."""
    key = [(m["trade_id"], (m.get("book_out") or {}).get("t"),
            len(m.get("wb_in") or []), len(m.get("wb_out") or [])) for m in doc.get("marks", [])]
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()


# ── Firestore (only ever touched without --dry-run) ──────────────────────────────────
def init_firestore(cred_path=None):
    """The SAME client/credentials path api/qqq_exec.py main() uses for the status doc."""
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path) if cred_path else credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return firestore.client()


def _with_timeout(fn, timeout, what):
    """Run fn() on a DAEMON thread and wait at most `timeout` seconds. A hung Firestore
    call then cannot keep the process alive at exit (a ThreadPoolExecutor's worker is
    joined at interpreter exit, so its timeout only stopped the wait, not the process)."""
    box = {}

    def run():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001 -- handed to the caller below
            box["e"] = e
    th = threading.Thread(target=run, name="qqq-bars-" + what, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        raise TimeoutError(f"{what} took longer than {timeout:.0f}s")
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _day_ref(db, uid, date):
    return db.collection("users").document(uid).collection(COLLECTION).document(date)


def publish_doc(db, uid, doc, timeout=PUBLISH_TIMEOUT_SEC):
    """set() the day doc (whole-doc replace) with a hard timeout."""
    ref = _day_ref(db, uid, doc["date"])
    _with_timeout(lambda: ref.set(doc), timeout, "set")


def fetch_doc(db, uid, date, timeout=PUBLISH_TIMEOUT_SEC):
    """The copy of a day doc already in Firestore (dict), or None when there is none."""
    ref = _day_ref(db, uid, date)

    def get():
        snap = ref.get()
        return snap.to_dict() if getattr(snap, "exists", False) else None
    return _with_timeout(get, timeout, "get")


def _load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


# ── CLI ──────────────────────────────────────────────────────────────────────────────
def pick_days(args, data, now):
    days = trading_days(data)
    if args.intraday:
        today = now.date().isoformat()
        return [today] if today in days else []
    picked = set(args.date or [])
    if args.backfill:
        hi = args.to or "9999-12-31"
        picked.update(d for d in days if args.backfill <= d <= hi)
    if args.recent or not picked:
        n = args.recent or 2
        picked.update(days[-n:])
    return sorted(d for d in picked if d in days) + sorted(d for d in picked if d not in days)


def summarize(doc):
    return (f"{doc['date']}  {doc_size(doc):>7,} bytes  bars 1m={doc['bar_counts'].get('1m')} "
            f"5m={doc['bar_counts'].get('5m')} through {doc['bars_through']}  "
            f"ext 1m={(doc.get('ext_counts') or {}).get('1m')} 5m={(doc.get('ext_counts') or {}).get('5m')}  "
            f"marks={len(doc['marks'])}  complete={doc['complete']} final={doc['final']}"
            + (f"  ({'+'.join(doc['bars_dropped'])} DROPPED: over cap)" if doc.get("bars_dropped") else ""))


def run_eod_fill_gap(paths, out, sleep=time.sleep):
    """MANAGER #152 (ORB COSTSTRESS r1): refresh qqq_exec/eod_fill_gap.csv -- every EOD exit
    beside the engine's 15:55-bar price (tools/eod_fill_gap.py). main() calls it AFTER its
    own work on every run that may write (never --dry-run), including one that stopped early
    (no Firestore credentials, no day to publish) -- but not after a torn ledger read, which
    it would only read torn again. It reads the same ledgers and writes only its own file,
    and can never change this run's docs, output lines or exit code: any error is logged
    here and swallowed."""
    try:
        from tools import eod_fill_gap
        eod_fill_gap.write_for_home(paths.get("home"), paths=paths, sleep=sleep,
                                    log=lambda s: print(s, file=out))
    except Exception as e:  # noqa: BLE001 -- a measurement log never fails the publisher
        print(f"[qqq-bars] EOD fill gap log not refreshed ({type(e).__name__}: {e}) -- "
              f"the publish is unaffected", file=out)


def main(argv=None, db_factory=init_firestore, now=None, out=None, sleep=time.sleep,
         ext_fetch=None):
    out = out or sys.stdout
    hook = {"ext_fetch": ext_fetch}   # tests pass a fake feed; None = fetch_yf_ext
    try:
        return _main(argv, db_factory, now, out, sleep, hook)
    finally:
        if hook.get("paths"):
            run_eod_fill_gap(hook["paths"], out, sleep=sleep)


def _main(argv, db_factory, now, out, sleep, hook):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the doc(s), write nothing")
    ap.add_argument("--print-doc", action="store_true", help="with --dry-run: print full JSON")
    ap.add_argument("--date", action="append", help="YYYY-MM-DD (repeatable)")
    ap.add_argument("--recent", type=int, default=0, help="the last N trading days")
    ap.add_argument("--backfill", default=None, help=f"from YYYY-MM-DD (e.g. {DEFAULT_START})")
    ap.add_argument("--to", default=None, help="with --backfill: last day (inclusive)")
    ap.add_argument("--intraday", action="store_true",
                    help="today only, only when a trade closed since the last write")
    ap.add_argument("--uid", default=None, help="publish to users/{uid}/qqq_bars/{date}")
    ap.add_argument("--cred", default=None, help="Firestore service-account json "
                                                  "(else Application Default Credentials)")
    ap.add_argument("--home", default=None, help="EDGELOG_HOME (default: env, else ~/edgelog)")
    ap.add_argument("--ohlc-dir", default=None)
    ap.add_argument("--exec-dir", default=None)
    ap.add_argument("--signals", default=None)
    ap.add_argument("--shadow-trades", action="append", default=[],
                    help="extra trades.csv-shaped ledger(s) of shadow legs (book only)")
    ap.add_argument("--cap", type=int, default=DOC_CAP_BYTES)
    ap.add_argument("--yes-many", action="store_true",
                    help=f"allow a run that would write more than {MAX_DAYS} days")
    ap.add_argument("--no-ext", action="store_true",
                    help="skip the extended-hours pull (the cache on disk still publishes)")
    a = ap.parse_args(argv)
    now = now or _et_now()
    paths = default_paths(a.home, a.ohlc_dir, a.exec_dir, a.signals)
    if not a.dry_run:
        hook["paths"] = paths     # main() runs the EOD fill gap log after this returns
    state = _load_state(paths["state"])
    try:
        data = load_all(paths, a.shadow_trades, prev_counts=state.get("_ledger_rows"), sleep=sleep)
    except LedgerUnreliable as e:
        hook.pop("paths", None)   # the same torn ledger: the EOD fill gap log waits too
        print(f"[qqq-bars] ledger read looks mid-rewrite ({e}) -- nothing published; "
              f"the next run retries", file=out)
        return 1
    days = pick_days(a, data, now)
    if not days:
        print("[qqq-bars] no trading day to publish", file=out)
        return 0
    have = set(trading_days(data))
    n_real = sum(1 for d in days if d in have)
    if n_real > MAX_DAYS and not a.yes_many:
        print(f"[qqq-bars] REFUSED: {n_real} days picked ({days[0]} .. {days[-1]}), more than "
              f"{MAX_DAYS} -- check --backfill FROM, or pass --yes-many", file=out)
        return 2
    db = None
    if not a.dry_run:
        if not a.uid:
            print("[qqq-bars] --uid is required to publish (or pass --dry-run)", file=out)
            return 2
        db = db_factory(a.cred)
        state["_ledger_rows"] = data["counts"]
        _save_state(paths["state"], state)
        if not a.no_ext and not a.intraday:
            # row 74: the extended-hours bars of the picked days, into the publisher's own
            # cache (never under --dry-run: it writes nothing anywhere), then re-read
            refresh_ext_cache(paths, [d for d in days if d in have], now=now,
                              fetch=hook.get("ext_fetch") or fetch_yf_ext,
                              log=lambda s: print(s, file=out))
            data["bars_ext"] = load_ext(paths)
    rc = 0
    for day in days:
        if day not in have:
            print(f"[qqq-bars] {day}: no bars in the cache -- skipped", file=out)
            continue
        try:
            doc = enforce_cap(build_day_doc(day, data, now=now), cap=a.cap)
        except DocTooLarge as e:
            print(f"[qqq-bars] REFUSED {e}", file=out)
            rc = 1
            continue
        fp = fingerprint(doc)     # before any merge below, so the intraday compare is stable
        if a.intraday:
            prev = state.get(day) or {}
            if prev.get("fp") == fp:
                print(f"[qqq-bars] {day}: no trade closed since the last write -- skipped", file=out)
                continue
            if time.time() - float(prev.get("at") or 0) < INTRADAY_MIN_SEC:
                print(f"[qqq-bars] {day}: last write under {INTRADAY_MIN_SEC}s ago -- skipped", file=out)
                continue
        gaps = sum(len(m.get("wb_gap") or []) + len(m.get("wb_part") or []) for m in doc["marks"])
        if gaps and not a.dry_run:
            # the order ledger no longer holds some of this day's Webull rows: keep the
            # ones the published copy has instead of overwriting them with "not on file"
            try:
                kept = merge_prior_marks(doc, fetch_doc(db, a.uid, day))
            except Exception as e:  # noqa: BLE001 -- never overwrite what we cannot read
                print(f"[qqq-bars] {day}: could not read the published copy to keep its "
                      f"Webull rows ({type(e).__name__}: {e}) -- skipped", file=out)
                rc = 1
                continue
            if kept:
                print(f"[qqq-bars] {day}: kept {kept} Webull side(s) from the published copy "
                      f"(the order ledger was trimmed since)", file=out)
                try:
                    # the merged rows add bytes: the cap is checked on what is written
                    doc = enforce_cap(doc, cap=a.cap)
                except DocTooLarge as e:
                    print(f"[qqq-bars] REFUSED {e} (after keeping the published Webull rows)",
                          file=out)
                    rc = 1
                    continue
        elif gaps:
            print(f"[qqq-bars] {day}: {gaps} Webull side(s) predate the order ledger "
                  f"(from {data.get('wb_from')}) -- marked 'not on file'", file=out)
        if a.dry_run:
            print("[qqq-bars] DRY RUN " + summarize(doc), file=out)
            if a.print_doc:
                print(json.dumps(doc, indent=1), file=out)
            continue
        try:
            publish_doc(db, a.uid, doc)
        except Exception as e:  # Firestore trouble: charts go stale, trading is untouched
            print(f"[qqq-bars] {day}: publish failed ({type(e).__name__}: {e})", file=out)
            rc = 1
            continue
        print("[qqq-bars] PUBLISHED " + summarize(doc), file=out)
        if a.intraday:
            state[day] = {"fp": fp, "at": time.time()}
            _save_state(paths["state"], state)
    return rc


if __name__ == "__main__":
    sys.exit(main())
