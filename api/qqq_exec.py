"""QQQ SHADOW execution adapter -- Stage 1 of "trade the crowned NQ strategies as QQQ
shares on Webull".

SHADOW ONLY. No order is ever sent anywhere, to any broker, by this module. There is
no Webull *order* code in this file at all -- only a market-DATA quote lookup (read-only)
and a `mode` config field that accepts exactly "SHADOW" and refuses (logged, no-op)
anything else. Adding a LIVE path is a deliberate future change to a DIFFERENT module,
not a flag flip in this one.

SIGNAL SOURCE. This never re-implements fill parsing. It reuses api.nt_sync.parse_fills
(the same CSV reader the real-money journal sync uses) to read C:\\EdgeLog\\fills.csv --
the file the NinjaScript AddOn appends to on every live fill from the three strategies
already running on real-time data in NinjaTrader (EdgeLogORB..., EdgeLogENGUQ1m,
EdgeLogNOISE). This module mirrors those fills into paper QQQ SHARE lots; it never
computes its own trading signal.

LEG ATTRIBUTION. A fill's `SignalName` column is the entry tag NinjaTrader stamped on
the order ("ORB", "ENGUQ", "NOISE" -- case-insensitive substring match, see
_leg_from_signal). Exit fills carry a generic tag ("Close", "EOD", ...) with no leg
name, so exits are attributed by POSITION: each (account, instrument) group is tracked
FIFO exactly like api.nt_sync.build_trades (same adding/reducing logic), and the leg
resolved on the fill that opened the position rides along for every fill that reduces
it, until it returns flat. A reducing fill on a group with no open leg (unrecognized
opening signal, e.g. legacy fills written before SignalName existed) is skipped with a
WARN -- never guessed at.

PRICING. Three-way fallback per fill, recorded as `px_source`:
  1. webull_quote -- official Webull OpenAPI QQQ snapshot, ONLY if its own timestamp is
     under 60s old (older = the account's data plan is delayed/refused; treated as
     unavailable, never trusted silently stale).
  2. nq_ratio -- NQ fill price / a QQQ:NQ ratio calibrated at 09:30 ET each day from
     yfinance's QQQ 1m close and the NQ price at the same minute (from
     C:\\EdgeLog\\ohlc_addon\\NQ_10s.csv, falling back to C:\\EdgeLog\\ohlc\\NQ_10s.csv),
     re-calibrated every 30 minutes.
  3. none -- if neither source can price the fill, it is logged and skipped rather than
     recorded with a fabricated price.

RAILS (identical logic shadow and, eventually, live):
  (a) shares > max_shares_per_leg -> refuse the lot (WARN, no lot opened).
  (b) daily shadow loss (realized + open marks) beyond daily_loss_limit_usd -> close
      every open lot, set breaker_tripped for the rest of the (ET) trading day, ignore
      further entries.
  (c) entries only inside [session.open, session.last_entry] ET; at session.flat_by,
      every open lot is closed and tagged "EOD".
  (d) kill file present -> no new lots; close every open lot, tagged "KILL".
  (e) feed staleness (NinjaTrader AddOn heartbeat older than 90s, via
      api.nt_sync._addon_heartbeat) blocks new entries and pushes at most one ntfy
      alert per 30 minutes while it persists.

RECORDS: C:\\EdgeLog\\qqq_exec\\orders.csv (every shadow order), \\trades.csv (every
closed round-trip), \\state.json (cursor + open lots + rail state -- this IS the
adapter's memory across ticks/restarts), \\config.json (owner-editable, reloaded every
tick). Firestore doc users/{uid}/meta/qqq_exec mirrors the current state for the web
SHADOW EXECUTION panel, written by a single dedicated background thread (see
_Publisher/publish_async) so a slow or failing Firestore call can never stall the 5s
tick loop -- see feature (2) below.

CLI: `python -m api.qqq_exec --once [--uid UID]` runs a single tick and exits -- used by
`api/runner.py`'s watch loop (own thread, ticking every ~5s during the session, exactly
like the nt-bridge watchdog thread) and by hand for verification.
"""
import argparse
import concurrent.futures
import re
import csv
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from . import market_calendar
from . import nt_sync

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover -- zoneinfo ships with 3.9+, this repo runs 3.13
    _NY = None

# -- paths -----------------------------------------------------------------------
OUT_DIR = os.environ.get("EDGELOG_QQQ_EXEC_DIR", r"C:\EdgeLog\qqq_exec")
CONFIG_PATH = os.path.join(OUT_DIR, "config.json")
STATE_PATH = os.path.join(OUT_DIR, "state.json")
ORDERS_CSV = os.path.join(OUT_DIR, "orders.csv")
TRADES_CSV = os.path.join(OUT_DIR, "trades.csv")
DEFAULT_FILLS = nt_sync.DEFAULT_FILLS
NQ_10S_PRIMARY = r"C:\EdgeLog\ohlc_addon\NQ_10s.csv"
NQ_10S_FALLBACK = r"C:\EdgeLog\ohlc\NQ_10s.csv"
WEBULL_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json")
_WEBULL_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR", r"C:\EdgeLog\webull_token")

LEGS = ("ORB", "ENGUQ", "NOISE")
# The ET calendar date shadow trading actually began (first tick of api/qqq_exec.py in
# production). Published in every doc as `live_from` so the web tab can show a
# "since start" figure without hardcoding the date client-side.
LIVE_FROM = "2026-09-03"
TICK_SEC = 5.0
FEED_STALE_SEC = 90.0
FEED_ALERT_COOLDOWN_SEC = 30 * 60
QUOTE_MAX_AGE_SEC = 60.0
CALIB_REFRESH_SEC = 30 * 60
ORDERS_KEEP = 100
# 500: matches the `trades_all` cap in the published doc, so the on-disk trades.csv
# never trims history the web tab is still allowed to show.
TRADES_KEEP = 500

DEFAULT_CONFIG = {
    "mode": "SHADOW",
    "shares": {"ORB": 5, "ENGUQ": 5, "NOISE": 5},
    "max_shares_per_leg": 10,
    "daily_loss_limit_usd": 150,
    "session": {"open": "09:31", "last_entry": "15:55", "flat_by": "15:58"},
    "kill_file": r"C:\EdgeLog\qqq_exec\KILL",
    "slippage_per_share": 0.01,
    # NT SIZING GAP (feature #50): "fixed" (default, unchanged behaviour) uses the
    # `shares` table above verbatim. "nt_notional" instead sizes each lot off the $
    # notional of the NT futures fill it mirrors: shares = round(nt_notional_usd *
    # size_fraction / qqq_px), still clamped to max_shares_per_leg.
    "size_mode": "fixed",
    "size_fraction": 0.01,
}

# NT SIZING GAP (feature #50): $ per 1.00-point move of the underlying futures contract
# (NOT the tick value -- a full point), keyed by the contract root from nt_sync.get_base.
# NQ = $20/point (tick $5 / tick size 0.25), MNQ = $2/point (tick $0.50 / tick size 0.25).
NT_MULT_BY_BASE = {"NQ": 20.0, "MNQ": 2.0}

# READINESS (feature #53): trading days of clean evidence required before the shadow
# adapter is declared ready to inform a real live-sizing decision.
DAYS_REQUIRED = 10

# COVERAGE-BASED UPTIME + NON-BLOCKING PUBLISH (2026-09-08 fix -- see module docstring
# feature (2) and _Publisher below). PUBLISH_TIMEOUT_SEC bounds every Firestore set() so
# a 503 can never again stall the tick loop; PUBLISH_FAIL_LOG_COOLDOWN_SEC caps how often
# a failing publish spams runner.log; TICK_GAP_WARN_SEC is the real wall-clock gap between
# ticks that counts as a stall worth an event (independent of TICK_SEC's target cadence).
PUBLISH_TIMEOUT_SEC = 8.0
PUBLISH_FAIL_LOG_COOLDOWN_SEC = 10 * 60
TICK_GAP_WARN_SEC = 120.0


# -- small time helpers ------------------------------------------------------------
def _now_et():
    return datetime.now(_NY) if _NY else datetime.utcnow()


def _hhmm(s):
    h, m = str(s).split(":")
    return int(h), int(m)


def _et_hhmm(dt):
    return dt.hour, dt.minute


def _is_weekday(dt):
    return dt.weekday() < 5


def _in_market_window(dt):
    """09:25-16:05 ET Mon-Fri -- the tick-loop's active window (broader than the
    entry window so EOD-flatten / breaker / heartbeat logic all still run)."""
    if not _is_weekday(dt):
        return False
    return (9, 25) <= _et_hhmm(dt) <= (16, 5)


def _in_entry_window(dt, sess):
    o = _hhmm(sess.get("open", "09:31"))
    le = _hhmm(sess.get("last_entry", "15:55"))
    return _is_weekday(dt) and o <= _et_hhmm(dt) <= le


def _past_flat_by(dt, sess):
    fb = _hhmm(sess.get("flat_by", "15:58"))
    return _et_hhmm(dt) >= fb


# -- config / state I/O -------------------------------------------------------------
def load_config(path=None, log=print):
    """Reloaded every tick so the owner can edit rails live. Creates the file with
    defaults if missing. A `mode` other than "SHADOW" is refused (logged) and the
    adapter falls back to SHADOW rather than doing nothing silently -- there is no
    other mode this build knows how to run.

    `path` defaults to None rather than the module constant CONFIG_PATH directly:
    a caller (the smoke test) that reassigns qqq_exec.CONFIG_PATH to a temp dir must
    have that take effect here too, and a default bound at def-time to the ORIGINAL
    constant would silently ignore it -- read the current module global instead."""
    path = path if path is not None else CONFIG_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        log(f"[qqq-exec] wrote default config -> {path}")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        log(f"[qqq-exec] config read failed ({type(e).__name__}: {e}) -- using defaults")
        cfg = {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    for k, v in (cfg or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    mode = str(merged.get("mode") or "").strip().upper()
    if mode != "SHADOW":
        log(f"[qqq-exec] REFUSED mode={merged.get('mode')!r} -- this build only runs "
            f"SHADOW (no live-order code exists). Forcing SHADOW.")
        merged["mode"] = "SHADOW"
    return merged


def _default_state():
    return {
        "processed_ids": [],       # capped list of fill exec_ids already handled
        "group_leg": {},           # "account|instrument" -> leg currently open there
        "legs": {},                # leg -> open lot dict, or absent when flat
        "realized_pnl_today": 0.0,
        "trading_day": None,       # ET date string the realized/breaker figures belong to
        "breaker_tripped": False,
        "flat_by_done_date": None,
        "kill_done": False,
        "last_feed_alert": 0.0,
        "feed_stale": False,
        "calib": None,             # {"ratio","source","at"}
        "last_publish": 0.0,
        "last_doc_hash": None,
        # feature (2) FEED UPTIME PER DAY: {"YYYY-MM-DD": {"ticks","stale_ticks",
        # "first_tick_et","last_tick_et","note"}} -- rolling 60 days, see _build_feed_days.
        "feed_days": {},
        # feature (3) RATIO HEALTH: capped rolling history of every successful
        # calibration, [{"at","ratio","source"}], see _maybe_calibrate / _build_ratio_health.
        "ratio_hist": [],
        # SIGNALS FIRED VS TAKEN (#55): {"YYYY-MM-DD": {leg: {"fired","taken","refused",
        # "oos"}}} -- rolling 60 days, see _accumulate_signal / _build_signals_day.
        "signals_days": {},
        # EVENT TIMELINE (#52): rolling 200-event list, oldest-first in storage
        # (published newest-first), see _log_event.
        "events": [],
        # REPRICE MERGE (#48 half): ET date the daily broker-reprice subprocess last ran.
        "reprice_done_date": None,
        # EOD PHONE SUMMARY (#55): ET date the end-of-day ntfy push last went out.
        "eod_summary_done_date": None,
        # MARKET CALENDAR: ET date the "market closed" holiday note was last logged
        # (so a holiday logs at most once/day, not once per 5s tick) and the ET date
        # the half-day early-close clamp was last logged, same reason.
        "holiday_logged_date": None,
        "half_day_logged_date": None,
        # NON-BLOCKING PUBLISH (2026-09-08 fix): rolling count of failed Firestore
        # publishes today + when the last one SUCCEEDED, see _record_publish_result and
        # module docstring feature (2). "_publish_fail_day" / "_last_publish_fail_log"
        # are private bookkeeping for the daily reset and the 10-min log cooldown.
        "publish_fail_today": 0,
        "last_publish_ok_et": None,
        "_publish_fail_day": None,
        "_last_publish_fail_log": 0.0,
        # TICK GAP (2026-09-08 fix): largest REAL wall-clock gap between two active
        # ticks today, independent of whatever `now` a caller injects for ET-market-hours
        # logic -- see _track_tick_gap. "_tick_gap_day" / "_last_tick_wall" are private.
        "tick_gap_max_s_today": 0.0,
        "_tick_gap_day": None,
        "_last_tick_wall": None,
    }


def _prune_non_session_feed_days(state, log=print):
    """MARKET CALENDAR: a bug before this fix accumulated a `feed_days` entry for
    every WEEKDAY, holidays included (e.g. 2026-09-07 Labor Day got a bogus
    valid:false, 53% row that dragged the readiness uptime mean down). Non-session
    days are never written going forward (see tick()'s holiday short-circuit and
    _accumulate_feed_uptime only being called when market_calendar.is_session), but
    an on-disk state.json from before the fix can still carry old bad rows -- strip
    them here, once, on every load. Never raises."""
    try:
        days = state.get("feed_days") or {}
        bad = [d for d in days if not market_calendar.is_session(d)]
        if bad:
            for d in bad:
                days.pop(d, None)
            log(f"[qqq-exec] pruned {len(bad)} non-session feed_days entr"
                f"{'y' if len(bad) == 1 else 'ies'} from state.json: {sorted(bad)}")
    except Exception as e:
        log(f"[qqq-exec] feed_days prune failed: {type(e).__name__}: {e}")


def load_state(path=None, log=print):
    path = path if path is not None else STATE_PATH
    if not os.path.exists(path):
        return _default_state()
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return _default_state()
    base = _default_state()
    base.update(st or {})
    _prune_non_session_feed_days(base, log=log)
    return base


def save_state(state, path=None, _retries=12, _sleep=0.05, log=None):
    """Atomically replace the state file, surviving a Windows reader lock.

    THE BUG THIS FIXES (2026-09-05): this function had thrown
    `PermissionError [WinError 32] ... state.json.tmp -> state.json` **100,570 times**
    into runner.log. Two causes, both Windows-specific:

      * `os.replace` fails outright if ANOTHER PROCESS has the destination open, even
        just for reading. `qqq_paper_publish.py` reads this exact file, and so does
        anything the owner has open; on POSIX the rename would simply succeed.
      * the temp file had a FIXED name, so two writers -- the tick loop and a `run_once`,
        or two ticks overlapping -- raced on the same `state.json.tmp`.

    The failure was not cosmetic: the tick loop catches the exception and logs it, so
    every failed save DROPPED the state write for that tick, and state.json is the
    source of truth for the cursor, the open lots and the rail state.

    So: a unique temp name per writer, fsync before the swap, and retry the swap for
    about a second, because a reader lock lasts milliseconds. If it still cannot swap,
    the temp file is LEFT ON DISK rather than deleted -- losing the write silently is
    worse than leaving a recoverable copy -- and the caller is told.
    """
    path = path if path is not None else STATE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), int(time.time() * 1000) % 100000)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    last = None
    for i in range(_retries):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError as e:          # WinError 32: someone has it open
            last = e
            time.sleep(_sleep * (i + 1))
        except OSError as e:
            last = e
            break
    if log:
        log("[qqq-exec] state write could not swap into place after %d tries (%s); the new "
            "state is kept at %s -- rename it over %s once whatever holds it lets go."
            % (_retries, last, tmp, path))
    return False


def _roll_day(state, today):
    if state.get("trading_day") != today:
        state["trading_day"] = today
        state["realized_pnl_today"] = 0.0
        state["breaker_tripped"] = False
        state["flat_by_done_date"] = None
        state["kill_done"] = False


# -- ntfy push (best-effort, non-fatal -- same shape as api.nt_drawdown_alert) ------
def _notify(msg, title, log=print):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log(f"[qqq-exec] NTFY_TOPIC unset, push skipped: {title}: {msg}")
        return
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"), method="POST",
            headers={"Title": title, "Priority": "default"})
        urllib.request.urlopen(req, timeout=4)
    except Exception as e:
        log(f"[qqq-exec] ntfy push failed: {type(e).__name__}: {e}")


# -- event timeline (feature #52) ---------------------------------------------------
# In-process flag (NOT persisted in state.json): a fresh process is a fresh "boot" --
# a state.json booted-flag would only fire once ever, across every restart.
_PROCESS = {"booted": False}
EVENTS_KEEP = 200


def _log_event(state, kind, text, log=print):
    """Append one event to the rolling, capped timeline. Never raises -- a failure here
    must not affect trading logic, only the historical event record."""
    try:
        events = state.setdefault("events", [])
        events.append({"ts_et": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "kind": kind,
                       "text": text})
        state["events"] = events[-EVENTS_KEEP:]
    except Exception as e:
        log(f"[qqq-exec] event log failed: {type(e).__name__}: {e}")


# -- NT sizing gap (feature #50) -----------------------------------------------------
def _nt_mult(instrument, log=print):
    """$ per 1.00-point move of `instrument`'s underlying futures contract, or None if
    the contract root is unrecognised. Never raises."""
    try:
        base = nt_sync.get_base(instrument)
        if base in NT_MULT_BY_BASE:
            return NT_MULT_BY_BASE[base]
        preset = nt_sync.PRESETS.get(base)
        if preset:
            tv, ts = preset
            if ts:
                return round(tv / ts, 4)
    except Exception as e:
        log(f"[qqq-exec] nt_mult lookup failed for {instrument!r}: {type(e).__name__}: {e}")
    return None


# -- signals fired vs taken (feature #55) --------------------------------------------
def _accumulate_signal(state, dt, leg, kind, log=print):
    """Bump one (leg, kind) counter for dt's ET calendar date. kind is one of
    fired/taken/refused/oos. Rolling 60-day cap, mirrors _accumulate_feed_uptime."""
    try:
        day = dt.strftime("%Y-%m-%d")
        days = state.setdefault("signals_days", {})
        d = days.setdefault(day, {})
        leg_d = d.setdefault(leg, {"fired": 0, "taken": 0, "refused": 0, "oos": 0})
        if kind in leg_d:
            leg_d[kind] = int(leg_d.get(kind, 0)) + 1
        if len(days) > 60:
            for k in sorted(days.keys())[:-60]:
                days.pop(k, None)
    except Exception as e:
        log(f"[qqq-exec] signal accumulate failed: {type(e).__name__}: {e}")


def _ensure_signals_day(state, day, log=print):
    """EXPLICIT ZERO DAYS (2026-09-08 fix, module docstring feature (3)): guarantees a
    signals_days row exists for `day` even when no signal fires at all -- otherwise a
    genuine "no signals today" session is indistinguishable, on the record, from a day
    the adapter never ran. _build_signals_day already defaults every leg's counters to
    zero for an empty {} row, so this only needs to make the key exist. Never raises."""
    try:
        days = state.setdefault("signals_days", {})
        days.setdefault(day, {})
        if len(days) > 60:
            for k in sorted(days.keys())[:-60]:
                days.pop(k, None)
    except Exception as e:
        log(f"[qqq-exec] signals_day ensure failed: {type(e).__name__}: {e}")


def _build_signals_day(state):
    """[{date,fired,taken,refused,oos,by_leg:{ORB:{...},ENGUQ:{...},NOISE:{...}}}, ...]
    oldest-first, last 60 days -- see module docstring feature (4)."""
    out = []
    days = state.get("signals_days") or {}
    for day in sorted(days.keys()):
        try:
            raw = days[day] or {}
            totals = {"fired": 0, "taken": 0, "refused": 0, "oos": 0}
            by_leg_out = {}
            for leg in LEGS:
                d = raw.get(leg) or {}
                row = {"fired": int(d.get("fired", 0) or 0), "taken": int(d.get("taken", 0) or 0),
                      "refused": int(d.get("refused", 0) or 0), "oos": int(d.get("oos", 0) or 0)}
                by_leg_out[leg] = row
                for k in totals:
                    totals[k] += row[k]
            out.append({"date": day, "fired": totals["fired"], "taken": totals["taken"],
                       "refused": totals["refused"], "oos": totals["oos"],
                       "by_leg": by_leg_out})
        except Exception:
            continue
    return out[-60:]


# -- leg attribution -----------------------------------------------------------------
# NinjaTrader stamps the ENTRY signal name per strategy (see bin/Custom/Strategies):
#   EdgeLogORB230.cs -> "ORB", EdgeLogENGUQ1m.cs -> "EQ", EdgeLogNOISE.cs -> "NZ".
#   EdgeLogORBV2.cs -> "V2" is NOT a crowned leg and is deliberately left unmapped.
SIGNAL_TO_LEG = {"ORB": "ORB", "EQ": "ENGUQ", "ENGUQ": "ENGUQ", "NZ": "NOISE", "NOISE": "NOISE"}


def _leg_from_signal(sig):
    s = str(sig or "").strip().upper()
    if not s:
        return None
    if s in SIGNAL_TO_LEG:
        return SIGNAL_TO_LEG[s]
    for tag, leg in SIGNAL_TO_LEG.items():
        if re.fullmatch(r"[A-Z0-9]*" + tag + r"[A-Z0-9]*", s) and tag in ("ORB", "ENGUQ", "NOISE"):
            return leg
    return None


def _group_key(account, instrument):
    return f"{account}|{instrument}"


# -- CSV writers ---------------------------------------------------------------------
def _migrate_csv_header(path, cols, log=print):
    """If `path` already exists with an OLDER/different header than `cols`, rewrite the
    file under the new header, padding every row's missing fields with "" so old data
    keeps parsing (DictReader-safe) once new columns are appended going forward. A
    no-op when the header already matches. Never raises -- called defensively before
    every append so a code upgrade that adds columns (e.g. the NT-parity fields) can't
    desync the on-disk header from what _append_csv is about to write."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            header_line = f.readline().rstrip("\r\n")
        if not header_line or header_line == ",".join(cols):
            return
        with open(path, encoding="utf-8", newline="") as f:
            old_rows = list(csv.DictReader(f))
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in old_rows:
                w.writerow({c: r.get(c, "") for c in cols})
        log(f"[qqq-exec] migrated {path} header -> {len(cols)} columns "
            f"({len(old_rows)} existing row(s) preserved)")
    except Exception as e:
        log(f"[qqq-exec] CSV header migration failed for {path}: {type(e).__name__}: {e}")


def _append_csv(path, cols, row, keep):
    """Append one row; keep the file trimmed to the last `keep` data rows so it never
    grows without bound. Cheap: rewritten only when the cap is exceeded."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    is_new = not os.path.exists(path)
    if not is_new:
        _migrate_csv_header(path, cols)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if is_new:
            w.writeheader()
        w.writerow(row)
    try:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) > keep:
            rows = rows[-keep:]
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
    except Exception:
        pass


ORDER_COLS = ["ts_et", "leg", "action", "side", "shares", "nq_px", "qqq_px",
              "px_source", "reason", "latency_s"]
# NT PARITY (feature 1): columns appended to the END so pre-existing trades.csv rows
# (written before this feature shipped) still parse -- missing values read back as "".
# ratio_at_entry/ratio_at_exit and nt_reconstructed are this adapter's own bookkeeping
# (not literally NT fill fields) but travel with the trade for the same reason: they're
# what _trade_parity needs to reproduce the parity numbers from the CSV alone, without
# re-deriving them from live state. See module docstring feature (1) and _trade_parity.
NT_PARITY_COLS = ["nt_entry_exec_id", "nt_entry_ts", "nt_entry_px",
                  "nt_exit_exec_id", "nt_exit_ts", "nt_exit_px", "nt_qty",
                  "ratio_at_entry", "ratio_at_exit", "nt_reconstructed"]
# NT SIZING GAP (feature #50): captured on the lot at open (_open_lot), travels onto
# the closed-trade row exactly like NT_PARITY_COLS above -- missing values (unrecognised
# instrument) read back as "".
SIZING_COLS = ["nt_mult", "nt_notional_usd", "shadow_notional_usd", "notional_ratio"]
TRADE_COLS = ["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px",
              "pnl", "nq_pnl_points", "exit_reason"] + NT_PARITY_COLS + SIZING_COLS


def _record_order(leg, action, side, shares, nq_px, qqq_px, px_source, reason, log=print,
                  fill_dt=None):
    """`fill_dt` (feature #51 LATENCY): the ET timestamp of the NT fill this order
    mirrors, when one exists -- absent for rail-driven closes (BREAKER/EOD/KILL flatten
    has no single triggering fill). latency_s = now (adapter order time) - fill_dt."""
    latency_s = None
    if fill_dt is not None:
        try:
            latency_s = round((_now_et() - fill_dt).total_seconds(), 3)
        except Exception as e:
            log(f"[qqq-exec] latency calc failed: {type(e).__name__}: {e}")
    row = {"ts_et": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "leg": leg, "action": action,
           "side": side, "shares": shares,
           "nq_px": round(nq_px, 4) if nq_px is not None else "",
           "qqq_px": round(qqq_px, 4) if qqq_px is not None else "",
           "px_source": px_source or "", "reason": reason or "",
           "latency_s": latency_s if latency_s is not None else ""}
    _append_csv(ORDERS_CSV, ORDER_COLS, row, ORDERS_KEEP)
    log(f"[qqq-exec] {action} {leg} {side} {shares}sh @ {qqq_px} "
        f"({px_source}) -- {reason}")


def _record_trade(lot, exit_px, exit_reason, log=print):
    entry_px = lot["entry_px"]
    side_mult = 1 if lot["side"] == "long" else -1
    pnl = round((exit_px - entry_px) * side_mult * lot["shares_total"], 2)
    nq_pts = None
    if lot.get("nq_entry_px") is not None and lot.get("last_nq_px") is not None:
        nq_pts = round((lot["last_nq_px"] - lot["nq_entry_px"]) * side_mult, 4)
    row = {"leg": lot["leg"], "entry_ts": lot["entry_ts"],
           "exit_ts": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "side": lot["side"],
           "shares": lot["shares_total"], "entry_px": round(entry_px, 4),
           "exit_px": round(exit_px, 4), "pnl": pnl,
           "nq_pnl_points": nq_pts if nq_pts is not None else "",
           "exit_reason": exit_reason}
    # NT PARITY (feature 1): identity fields captured on the lot at open (_open_lot) and
    # on every reduce (_reduce_lot) -- non-fatal, a lot missing this bookkeeping (should
    # never happen going forward) just publishes as "insufficient NT fill data".
    try:
        row.update({
            "nt_entry_exec_id": lot.get("nt_entry_exec_id") or "",
            "nt_entry_ts": lot.get("nt_entry_ts") or "",
            "nt_entry_px": lot.get("nt_entry_px") if lot.get("nt_entry_px") is not None else "",
            "nt_exit_exec_id": lot.get("_nt_exit_exec_id") or "",
            "nt_exit_ts": lot.get("_nt_exit_ts") or "",
            "nt_exit_px": lot.get("_nt_exit_px") if lot.get("_nt_exit_px") is not None else "",
            "nt_qty": lot.get("_nt_exit_qty") if lot.get("_nt_exit_qty") is not None else "",
            "ratio_at_entry": lot.get("ratio_at_entry") if lot.get("ratio_at_entry") else "",
            "ratio_at_exit": lot.get("_ratio_at_exit") if lot.get("_ratio_at_exit") else "",
            "nt_reconstructed": "",
        })
    except Exception as e:
        log(f"[qqq-exec] NT parity fields dropped from trade row: {type(e).__name__}: {e}")
    # NT SIZING GAP (feature #50): captured on the lot at open -- non-fatal, a lot
    # missing this bookkeeping just publishes as "" (unrecognised instrument, or a lot
    # opened before this feature shipped).
    try:
        row.update({
            "nt_mult": lot.get("nt_mult") if lot.get("nt_mult") is not None else "",
            "nt_notional_usd": lot.get("nt_notional_usd") if lot.get("nt_notional_usd") is not None else "",
            "shadow_notional_usd": lot.get("shadow_notional_usd") if lot.get("shadow_notional_usd") is not None else "",
            "notional_ratio": lot.get("notional_ratio") if lot.get("notional_ratio") is not None else "",
        })
    except Exception as e:
        log(f"[qqq-exec] sizing-gap fields dropped from trade row: {type(e).__name__}: {e}")
    _append_csv(TRADES_CSV, TRADE_COLS, row, TRADES_KEEP)
    return pnl


# -- pricing ---------------------------------------------------------------------------
# -- quote time-box + circuit breaker ------------------------------------------------------
# 2026-09-03: the runner's shadow thread hung for 10 hours inside get_snapshot's SSL
# handshake (py-spy: ssl_wrap_socket <- webull get_snapshot <- default_webull_quote).
# The SDK's connect/read timeouts are not honoured on that path, so the call is now run in
# a throw-away worker thread with a hard wall-clock limit, and any failure (timeout, 401,
# stale quote) disables the quote path for QUOTE_BACKOFF_SEC. Between calls the last good
# quote is reused for QUOTE_CACHE_SEC so a 5 s tick never does a network call per tick.
QUOTE_HARD_TIMEOUT_SEC = 6.0
QUOTE_BACKOFF_SEC = 1800.0
QUOTE_CACHE_SEC = 20.0
_quote_state = {"disabled_until": 0.0, "last": None, "last_at": 0.0, "warned": False}


def default_webull_quote(symbol="QQQ", log=print):
    """Time-boxed, circuit-broken wrapper around _webull_quote_raw. Never raises, never
    blocks longer than QUOTE_HARD_TIMEOUT_SEC. Returns (price, age_secs) or None."""
    now = time.time()
    qs = _quote_state
    if qs["last"] is not None and now - qs["last_at"] < QUOTE_CACHE_SEC:
        return qs["last"]
    if now < qs["disabled_until"]:
        return None
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1,
                                               thread_name_prefix="qqq-quote")
    fut = ex.submit(_webull_quote_raw, symbol, log)
    ex.shutdown(wait=False)
    try:
        res = fut.result(timeout=QUOTE_HARD_TIMEOUT_SEC)
    except concurrent.futures.TimeoutError:
        res = None
        log(f"[qqq-exec] Webull quote timed out after {QUOTE_HARD_TIMEOUT_SEC:g}s -- "
            f"quote path disabled for {QUOTE_BACKOFF_SEC/60:g} min (nq_ratio pricing)")
    except Exception as e:
        res = None
        log(f"[qqq-exec] Webull quote failed: {type(e).__name__}: {e} -- disabled "
            f"{QUOTE_BACKOFF_SEC/60:g} min")
    if res is None:
        qs["disabled_until"] = now + QUOTE_BACKOFF_SEC
        if not qs["warned"]:
            log("[qqq-exec] Webull quote unavailable (no entitlement / timeout) -- pricing "
                "shadow fills from the NQ ratio; will retry the quote every 30 min")
            qs["warned"] = True
        return None
    qs["last"], qs["last_at"] = res, now
    return res


def _webull_quote_raw(symbol="QQQ", log=print):
    """Try the official Webull OpenAPI market-data snapshot. Returns (price, age_secs)
    or None on any failure/unavailability (missing SDK, missing keys, no subscription,
    a quote timestamp too old to trust). Never raises -- read-only, no order call of
    any kind exists anywhere in this module."""
    try:
        if not os.path.exists(WEBULL_KEYS):
            return None
        with open(WEBULL_KEYS, encoding="utf-8") as f:
            keys = json.load(f)
        ak = (keys.get("app_key") or "").strip()
        sk = (keys.get("app_secret") or "").strip()
        if not ak or not sk or ak.startswith("PASTE_"):
            return None
        from webull.core.client import ApiClient
        from webull.data.quotes.market_data import MarketData
        from webull.data.common.category import Category
        api = ApiClient(ak, sk, (keys.get("region") or "us").strip().lower(),
                        token_check_duration_seconds=10, token_check_interval_seconds=3,
                        connect_timeout=8, timeout=15)
        # Reuse the SDK's persisted 2FA/access token, same directory api.webull_sync's
        # TradeClient uses -- an ApiClient built without this errors 401 INVALID_TOKEN
        # on every call even with a valid app key/secret (confirmed 2026-09-02: still
        # 401 after this fix too, which is the SDK's own signal that this account has
        # no market-data subscription entitlement -- see module docstring's px_source
        # fallback, this is exactly the "refused" case it is designed to detect).
        try:
            os.makedirs(_WEBULL_TOKEN_DIR, exist_ok=True)
            api.set_token_dir(_WEBULL_TOKEN_DIR)
        except Exception:
            pass
        # The SDK attaches a TimedRotatingFileHandler on ./webull_trade_sdk.log unless a logger is
        # already marked as set. Five runner processes (primary + 4 workers) share this CWD, so the
        # hourly rotation's os.rename hit WinError 32 (file held by the other four) and dumped a
        # traceback into runner.log every hour (seen 2026-09-08). Mark it set and log to nothing.
        api._file_logger_set = True
        import logging as _lg; _lg.getLogger('webull.core').addHandler(_lg.NullHandler())
        md = MarketData(api)
        for cat in (Category.US_ETF, Category.US_STOCK):
            try:
                resp = md.get_snapshot([symbol], cat)
            except Exception:
                resp = None
            if not resp:
                continue
            item = resp[0] if isinstance(resp, list) else resp
            price = (getattr(item, "close", None) or getattr(item, "price", None)
                     or getattr(item, "last_price", None))
            ts = (getattr(item, "trade_time", None) or getattr(item, "timestamp", None)
                  or getattr(item, "mktradetime", None))
            if price is None:
                continue
            age = None
            try:
                tsf = float(ts)
                if tsf > 1e12:
                    tsf /= 1000.0
                age = max(0.0, time.time() - tsf)
            except Exception:
                age = None
            if age is not None and age > QUOTE_MAX_AGE_SEC:
                log(f"[qqq-exec] webull quote too old ({age:.0f}s) -- treating as unavailable")
                return None
            return float(price), age
        return None
    except Exception as e:
        log(f"[qqq-exec] webull quote unavailable: {type(e).__name__}: {e}")
        return None


def _last_nq_close(before_ts=None):
    """Latest NQ 10s close at/just before `before_ts` (unix seconds), from the addon
    file with fallback to the legacy one. Returns (price, ts) or (None, None)."""
    for path in (NQ_10S_PRIMARY, NQ_10S_FALLBACK):
        if not os.path.exists(path):
            continue
        try:
            best = None
            with open(path, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        t = float(row["time"])
                        c = float(row["close"])
                    except Exception:
                        continue
                    if before_ts is not None and t > before_ts:
                        continue
                    if best is None or t > best[1]:
                        best = (c, t)
            if best is not None:
                return best
        except Exception:
            continue
    return None, None


_nq_latest_cache = {"px": None, "ts": 0.0, "read_at": 0.0}


def _latest_nq_px(max_age_sec=180.0, cache_sec=10.0):
    """Most recent NQ 10s close from the live addon feed, read from the file TAIL (the
    file is weeks of 10s bars; a full scan per 5s tick is not acceptable). Cached for
    cache_sec. Returns (price, bar_ts) or (None, None) when the newest bar is older
    than max_age_sec -- callers then fall back to the lot's last known NQ price, so a
    dead feed can never mark a position at a stale-but-plausible number silently."""
    now = time.time()
    c = _nq_latest_cache
    if now - c["read_at"] < cache_sec:
        px, ts = c["px"], c["ts"]
    else:
        px, ts = None, 0.0
        for path in (NQ_10S_PRIMARY, NQ_10S_FALLBACK):
            if not os.path.exists(path):
                continue
            try:
                with open(path, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - 65536))
                    chunk = f.read().decode("utf-8", "replace")
                lines = [ln for ln in chunk.splitlines() if ln.strip()]
                with open(path, encoding="utf-8", newline="") as f:
                    header = f.readline().strip().split(",")
                ti = header.index("time") if "time" in header else 0
                ci = header.index("close") if "close" in header else 4
                for ln in reversed(lines):
                    parts = ln.split(",")
                    try:
                        t = float(parts[ti]); cpx = float(parts[ci])
                    except Exception:
                        continue
                    px, ts = cpx, t
                    break
            except Exception:
                continue
            if px is not None:
                break
        c.update({"px": px, "ts": ts, "read_at": now})
    if px is None or (now - ts) > max_age_sec:
        return None, None
    return px, ts


def default_ratio_calibration(log=print):
    """QQQ:NQ ratio at 09:30 ET today, from yfinance's last QQQ 1m close and the NQ
    close at the same minute in the 10s master. Returns {"ratio","source","at"} or
    None. Best-effort only -- a failed calibration falls back to whatever ratio the
    caller already has cached."""
    try:
        import yfinance as yf
        now = _now_et()
        anchor = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if now < anchor:
            anchor -= timedelta(days=1)
        tkr = yf.Ticker("QQQ")
        df = tkr.history(start=anchor - timedelta(minutes=5), end=anchor + timedelta(minutes=10),
                         interval="1m", prepost=False, auto_adjust=False)
        if df is None or not len(df):
            return None
        idx = df.index
        anchor_cmp = anchor.astimezone(idx.tz) if idx.tz else anchor
        after = df[idx >= anchor_cmp]
        row = after.iloc[0] if len(after) else df.iloc[-1]
        qqq_px = float(row["Close"])
        bar_ts = row.name
        bar_epoch = bar_ts.timestamp() if hasattr(bar_ts, "timestamp") else time.time()
        nq_px, nq_ts = _last_nq_close(before_ts=bar_epoch + 65)
        if nq_px is None or qqq_px <= 0:
            return None
        ratio = nq_px / qqq_px
        return {"ratio": ratio, "source": "yfinance+NQ_10s",
                "at": _now_et().strftime("%Y-%m-%d %H:%M:%S")}
    except Exception as e:
        log(f"[qqq-exec] ratio calibration failed: {type(e).__name__}: {e}")
        return None


def _maybe_calibrate(state, ratio_fn, log=print):
    calib = state.get("calib")
    stale = calib is None
    if calib and calib.get("at"):
        try:
            at = datetime.strptime(calib["at"], "%Y-%m-%d %H:%M:%S")
            stale = (datetime.now() - at).total_seconds() > CALIB_REFRESH_SEC
        except Exception:
            stale = True
    if stale:
        fresh = ratio_fn(log=log)
        if fresh:
            state["calib"] = fresh
            log(f"[qqq-exec] ratio calibrated: {fresh['ratio']:.3f} ({fresh['source']})")
            # RATIO HEALTH (feature 3): every successful calibration joins a rolling,
            # capped history -- this is what lets the web tab (and _build_ratio_health)
            # show drift over time instead of just the single current value.
            try:
                hist = state.setdefault("ratio_hist", [])
                hist.append({"at": fresh.get("at"), "ratio": fresh.get("ratio"),
                            "source": fresh.get("source")})
                state["ratio_hist"] = hist[-500:]
            except Exception as e:
                log(f"[qqq-exec] ratio_hist append failed: {type(e).__name__}: {e}")
            _log_event(state, "calib",
                      f"QQQ:NQ ratio recalibrated to {fresh['ratio']:.3f} ({fresh['source']})",
                      log=log)
        elif calib is None:
            log("[qqq-exec] no ratio calibration available yet -- nq_ratio pricing "
                "unavailable until one succeeds")
    return state.get("calib")


def _build_ratio_health(state, nowdt, log=print):
    """{current,at,source,age_min,mean_20,drift_pct,band_lo,band_hi,warn,note} -- see
    module docstring feature (3). Every shadow fill priced off the nq_ratio path is
    biased by however stale/drifted this ratio is, so this block is what lets the owner
    (and the web tab) tell a healthy calibration from one quietly going bad."""
    try:
        calib = state.get("calib") or {}
        hist = state.get("ratio_hist") or []
        current = calib.get("ratio")
        at = calib.get("at")
        source = calib.get("source")
        age_min = None
        if at:
            try:
                at_dt = datetime.strptime(at, "%Y-%m-%d %H:%M:%S")
                age_min = round((nowdt.replace(tzinfo=None) - at_dt).total_seconds() / 60.0, 1)
            except Exception:
                age_min = None
        last20 = [h for h in hist[-20:] if h.get("ratio")]
        vals = [float(h["ratio"]) for h in last20]
        mean_20 = round(sum(vals) / len(vals), 5) if vals else (round(current, 5) if current else None)
        drift_pct = None
        if current and mean_20:
            drift_pct = round((float(current) - mean_20) / mean_20 * 100.0, 3)
        band_lo = round(mean_20 * 0.99, 5) if mean_20 else None
        band_hi = round(mean_20 * 1.01, 5) if mean_20 else None
        active = _in_market_window(nowdt)
        warn = False
        notes = []
        if current is None:
            notes.append("no ratio calibrated yet -- nq_ratio pricing is unavailable")
        else:
            if active and age_min is not None and age_min > 45:
                warn = True
                notes.append(f"ratio hasn't refreshed in {age_min:.0f} min -- fills may be "
                            f"priced off a stale QQQ:NQ ratio")
            if drift_pct is not None and abs(drift_pct) > 1.0:
                warn = True
                notes.append(f"ratio has drifted {drift_pct:.2f}% from its last-20 average -- "
                            f"fills may be biased")
        if not notes:
            # Outside the session a day-old ratio is expected, not healthy -- saying
            # "healthy" beside an age of 1775 min read as a contradiction.
            if not active and age_min is not None and age_min > 120:
                notes.append("market is closed -- this ratio is from the last session and "
                            "recalibrates at the next open")
            else:
                notes.append("ratio looks healthy -- fills should track NT closely")
        return {"current": current, "at": at, "source": source, "age_min": age_min,
               "mean_20": mean_20, "drift_pct": drift_pct, "band_lo": band_lo,
               "band_hi": band_hi, "warn": bool(warn), "note": "; ".join(notes)}
    except Exception as e:
        log(f"[qqq-exec] ratio_health build failed: {type(e).__name__}: {e}")
        return {"current": None, "at": None, "source": None, "age_min": None,
               "mean_20": None, "drift_pct": None, "band_lo": None, "band_hi": None,
               "warn": False, "note": f"ratio_health unavailable: {type(e).__name__}"}


def resolve_price(cfg, state, nq_px, quote_fn, ratio_fn, log=print):
    """(qqq_px, source) for one fill/mark, or (None, None) if nothing can price it."""
    q = quote_fn(log=log) if quote_fn else None
    if q is not None:
        price, _age = q
        return float(price), "webull_quote"
    calib = _maybe_calibrate(state, ratio_fn, log=log)
    if calib and calib.get("ratio"):
        return float(nq_px) / float(calib["ratio"]), "nq_ratio"
    return None, None


def _apply_slippage(px, side, entering, slip):
    """slippage always moves the fill AGAINST us: worse price on entry, worse on exit."""
    buying = (side == "long") == entering  # buying to open long, or buying to cover short
    return px + slip if buying else px - slip


# -- lot lifecycle ---------------------------------------------------------------------
def _open_lot(state, cfg, leg, side, nq_qty, nq_px, qqq_px_raw, slip, f=None, log=print):
    """Returns True if a shadow lot opened, False if refused/skipped (feature #55 needs
    to know this to tell TAKEN from REFUSED)."""
    max_shares = int(cfg.get("max_shares_per_leg", 0) or 0)
    size_mode = str(cfg.get("size_mode") or "fixed").strip().lower()
    instrument = (f.get("instrument") if f else "") or ""
    nt_mult = _nt_mult(instrument, log=log)

    if size_mode == "nt_notional" and nt_mult and qqq_px_raw:
        # NT SIZING GAP (feature #50): size the shadow lot off the $ notional of the NT
        # futures fill it mirrors, instead of the fixed shares table. Still CLAMPED (not
        # refused) to max_shares_per_leg -- a dynamically computed size can overshoot the
        # cap easily and refusing every overshoot would defeat the point of the mode.
        nt_notional_usd = round(nq_qty * nt_mult * nq_px, 2)
        size_fraction = float(cfg.get("size_fraction", 0.01) or 0.01)
        shares = int(round(nt_notional_usd * size_fraction / qqq_px_raw))
        if max_shares:
            shares = min(shares, max_shares)
    else:
        # Default behaviour (size_mode == "fixed"): unchanged from before this feature.
        shares = int(cfg["shares"].get(leg, 0))
        if shares > max_shares:
            _record_order(leg, "ENTER", side, shares, nq_px, None, None,
                          f"REFUSED shares {shares} > max_shares_per_leg {max_shares}", log,
                          fill_dt=(f.get("dt") if f else None))
            return False

    if shares <= 0:
        return False

    fill_px = _apply_slippage(qqq_px_raw, side, True, slip)
    lot = {
        "leg": leg, "side": side, "shares_total": shares, "shares_remaining": shares,
        "nq_qty_total": nq_qty, "nq_qty_remaining": nq_qty,
        "entry_px": fill_px, "nq_entry_px": nq_px, "last_nq_px": nq_px,
        "entry_ts": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
    }
    state["legs"][leg] = lot
    # NT PARITY (feature 1): the fill that opened this lot IS the NT trade being
    # mirrored -- persist its identity + the ratio in force right now so a closed trade
    # can later prove/disprove it tracked that exact NT round-trip. Best-effort: a
    # missing `f` or calib (should not happen -- every open comes from a routed fill)
    # just leaves these blank rather than raising.
    try:
        lot["nt_entry_exec_id"] = f.get("exec_id") if f else ""
        lot["nt_entry_ts"] = f["dt"].strftime("%Y-%m-%d %H:%M:%S") if f and f.get("dt") else ""
        lot["nt_entry_px"] = f.get("price") if f else nq_px
        calib = state.get("calib") or {}
        lot["ratio_at_entry"] = calib.get("ratio") or ""
    except Exception as e:
        log(f"[qqq-exec] NT parity entry fields not captured for {leg}: {type(e).__name__}: {e}")
    # NT SIZING GAP (feature #50): the $ size of the NT futures fill this lot mirrors,
    # vs the $ size of the shadow shares -- lets the owner see how far the shadow lot is
    # from actually matching the real NT position. Best-effort: an unrecognised
    # instrument (nt_mult None) just leaves the notional fields blank.
    try:
        lot["nt_mult"] = nt_mult
        lot["shadow_notional_usd"] = round(shares * fill_px, 2)
        if nt_mult:
            lot["nt_notional_usd"] = round(nq_qty * nt_mult * nq_px, 2)
            lot["notional_ratio"] = (round(lot["shadow_notional_usd"] / lot["nt_notional_usd"], 4)
                                     if lot["nt_notional_usd"] else None)
        else:
            lot["nt_notional_usd"] = None
            lot["notional_ratio"] = None
    except Exception as e:
        log(f"[qqq-exec] sizing-gap fields not captured for {leg}: {type(e).__name__}: {e}")
    _record_order(leg, "ENTER", side, shares, nq_px, fill_px, state["_px_source"],
                 "signal entry", log, fill_dt=(f.get("dt") if f else None))
    _notify(f"QQQ SHADOW {leg} {side} {shares} @ {fill_px:.2f}", "EDGELOG QQQ SHADOW", log)
    return True


def _reduce_lot(state, cfg, leg, nq_qty_closed, nq_px, qqq_px_raw, slip, reason, f=None, log=print):
    lot = state["legs"].get(leg)
    if not lot:
        log(f"[qqq-exec] WARN exit fill for {leg} with no open shadow lot -- skipped")
        return None
    lot["last_nq_px"] = nq_px
    frac = min(1.0, nq_qty_closed / lot["nq_qty_total"]) if lot["nq_qty_total"] else 1.0
    shares_close = round(lot["shares_total"] * frac)
    shares_close = min(shares_close, lot["shares_remaining"])
    lot["nq_qty_remaining"] = max(0, lot["nq_qty_remaining"] - nq_qty_closed)
    if lot["nq_qty_remaining"] <= 0:
        shares_close = lot["shares_remaining"]  # close any rounding dust on the final leg
    if shares_close <= 0:
        return None
    fill_px = _apply_slippage(qqq_px_raw, lot["side"], False, slip)
    lot["shares_remaining"] -= shares_close
    # NT PARITY (feature 1): remember the identity of the LAST reduce call -- that is
    # what "closed" the round-trip. When `f` is None (this reduce came from a RAIL --
    # _close_all's BREAKER/EOD/KILL flatten -- not a routed NT fill), deliberately CLEAR
    # the exit identity rather than leaving a stale earlier partial-exit's exec id
    # attached to a close it didn't actually cause; _trade_parity then reports "no NT
    # exit fill matched" instead of a misleading match.
    try:
        if f is not None:
            lot["_nt_exit_exec_id"] = f.get("exec_id") or ""
            lot["_nt_exit_ts"] = f["dt"].strftime("%Y-%m-%d %H:%M:%S") if f.get("dt") else ""
            lot["_nt_exit_px"] = f.get("price")
            lot["_nt_exit_qty"] = nq_qty_closed
        else:
            lot["_nt_exit_exec_id"] = ""
            lot["_nt_exit_ts"] = ""
            lot["_nt_exit_px"] = ""
            lot["_nt_exit_qty"] = ""
        calib = state.get("calib") or {}
        lot["_ratio_at_exit"] = calib.get("ratio") or ""
    except Exception as e:
        log(f"[qqq-exec] NT parity exit fields not captured for {leg}: {type(e).__name__}: {e}")
    _record_order(leg, "EXIT", lot["side"], shares_close, nq_px, fill_px,
                 state["_px_source"], reason, log, fill_dt=(f.get("dt") if f else None))
    _notify(f"QQQ SHADOW {leg} {reason.lower()} {shares_close} @ {fill_px:.2f}",
           "EDGELOG QQQ SHADOW", log)
    pnl = None
    if lot["shares_remaining"] <= 0:
        # close the round-trip on the full lot's entry (weighted avg exit unnecessary
        # for a single-entry lot -- see module docstring: entries are treated single-shot)
        pnl = _record_trade(lot, fill_px, reason, log=log)
        state["realized_pnl_today"] = round(state.get("realized_pnl_today", 0.0) + pnl, 2)
        del state["legs"][leg]
    return pnl


def _close_all(state, cfg, reason, quote_fn, ratio_fn, log=print):
    nq_now, _ts = _latest_nq_px()
    for leg in list(state["legs"].keys()):
        lot = state["legs"][leg]
        # flatten at the LIVE NQ price (fallback: last known) -- never at the entry price
        exit_nq = nq_now if nq_now is not None else (lot.get("last_nq_px") or lot["nq_entry_px"])
        qqq_px, src = resolve_price(cfg, state, exit_nq, quote_fn, ratio_fn, log=log)
        state["_px_source"] = src
        if qqq_px is None:
            log(f"[qqq-exec] cannot price {leg} for {reason} close -- no quote/ratio "
                f"available, lot left open")
            continue
        _reduce_lot(state, cfg, leg, lot["nq_qty_remaining"], exit_nq,
                   qqq_px, cfg.get("slippage_per_share", 0.0), reason, log=log)


# -- fill routing ------------------------------------------------------------------------
def _route_fills(state, cfg, fills, quote_fn, ratio_fn, entries_blocked, log=print):
    """Walk NEW fills in file order, updating per-group position and opening/reducing
    shadow lots. Mirrors api.nt_sync.build_trades' adding/reducing FIFO logic.

    `entries_blocked` covers the reasons that depend on the ADAPTER'S current state
    (breaker tripped / feed stale / kill file) rather than the fill's own time --
    those apply to every fill regardless of when it happened. The session-window
    check (open/last_entry) is evaluated against the FILL'S OWN timestamp
    (f["dt"], NY-local per fills.csv), which is what a real 5s-tick adapter is
    equivalent to: by the time a fill shows up in the file it IS "now"."""
    groups = {}
    for f in fills:
        groups.setdefault((f["account"], f["instrument"]), []).append(f)
    for (account, instrument), grp in groups.items():
        grp.sort(key=lambda f: (f["dt"], f["_i"]))
        gk = _group_key(account, instrument)
        for f in grp:
            delta = f["qty"] if f["action"] == "BUY" else -f["qty"]
            side_of_fill = "long" if f["action"] == "BUY" else "short"
            leg_open = state["group_leg"].get(gk)
            opening = leg_open is None
            if opening:
                leg = _leg_from_signal(f.get("signal"))
                if leg is None:
                    log(f"[qqq-exec] WARN unattributable opening fill on {gk} "
                        f"(signal={f.get('signal')!r}) -- skipped")
                    continue
                if leg in state["legs"]:
                    log(f"[qqq-exec] WARN {leg} already has an open shadow lot -- "
                        f"second entry on {gk} ignored")
                    state["group_leg"][gk] = leg  # still track so exits route correctly
                    _accumulate_signal(state, f["dt"], leg, "fired", log=log)
                    _accumulate_signal(state, f["dt"], leg, "refused", log=log)
                    continue
                in_window = _in_entry_window(f["dt"], cfg["session"])
                if entries_blocked or not in_window:
                    # ENGU-Q OUT-OF-SESSION (feature #49): NT runs ENGU-Q (and every
                    # leg) on the 24h tape; the shadow only ever trades the QQQ session
                    # (the session-window rule itself is unchanged). A fill refused for
                    # being outside that window is tagged OOS, not a generic REFUSED, so
                    # it is never mistaken for a rail block and is always counted, never
                    # silently dropped.
                    kind = "oos" if not in_window else "refused"
                    reason = ("OOS -- outside QQQ session (not mirrored)" if not in_window
                              else "REFUSED -- breaker/feed/kill blocked")
                    _record_order(leg, "ENTER", side_of_fill, cfg["shares"].get(leg, 0),
                                 f["price"], None, None, reason, log, fill_dt=f["dt"])
                    state["group_leg"][gk] = leg
                    _accumulate_signal(state, f["dt"], leg, "fired", log=log)
                    _accumulate_signal(state, f["dt"], leg, kind, log=log)
                    _log_event(state, kind,
                              f"{leg} signal fired {'outside the QQQ session' if kind == 'oos' else 'while blocked (breaker/feed/kill)'} -- not mirrored",
                              log=log)
                    continue
                qqq_px, src = resolve_price(cfg, state, f["price"], quote_fn, ratio_fn, log=log)
                state["_px_source"] = src
                if qqq_px is None:
                    log(f"[qqq-exec] cannot price {leg} entry -- no quote/ratio available, "
                        f"fill skipped")
                    _accumulate_signal(state, f["dt"], leg, "fired", log=log)
                    _accumulate_signal(state, f["dt"], leg, "refused", log=log)
                    continue
                opened = _open_lot(state, cfg, leg, side_of_fill, abs(delta), f["price"], qqq_px,
                                   cfg.get("slippage_per_share", 0.0), f=f, log=log)
                state["group_leg"][gk] = leg
                _accumulate_signal(state, f["dt"], leg, "fired", log=log)
                _accumulate_signal(state, f["dt"], leg, "taken" if opened else "refused", log=log)
            else:
                leg = leg_open
                qqq_px, src = resolve_price(cfg, state, f["price"], quote_fn, ratio_fn, log=log)
                state["_px_source"] = src
                if qqq_px is None:
                    log(f"[qqq-exec] cannot price {leg} exit -- no quote/ratio available, "
                        f"fill skipped (lot stays open)")
                    continue
                reason = "signal exit" if str(f.get("signal") or "").strip() else "close"
                _reduce_lot(state, cfg, leg, abs(delta), f["price"], qqq_px,
                           cfg.get("slippage_per_share", 0.0), reason, f=f, log=log)
                if leg not in state["legs"]:
                    state["group_leg"].pop(gk, None)


# -- mark-to-market + breaker ------------------------------------------------------------
def _mark_and_check_breaker(state, cfg, quote_fn, ratio_fn, log=print):
    # stashes the per-leg breakdown on state["_unrl_by_leg"] (leg -> unrealized $) so
    # _build_doc can show each leg card its own unrealized figure, not just the total --
    # cheap, since the marks are already computed here for the breaker check.
    if not state.get("legs"):
        state["_unrl_by_leg"] = {}
        return 0.0  # nothing open: no quote/ratio work, unrealized is zero
    unrl = 0.0
    unrl_by_leg = {}
    nq_now, nq_ts = _latest_nq_px()
    for leg, lot in state["legs"].items():
        # Mark at the LIVE NQ price (2026-09-03 fix: marking at the entry price left
        # unrealized pinned at $0 and blinded the daily-loss breaker). Fall back to the
        # last known NQ price only when the feed is stale.
        mark_nq = nq_now if nq_now is not None else (lot.get("last_nq_px") or lot["nq_entry_px"])
        lot["mark_nq_px"] = mark_nq
        lot["mark_fresh"] = nq_now is not None
        qqq_px, src = resolve_price(cfg, state, mark_nq, quote_fn, ratio_fn, log=log)
        if qqq_px is None:
            continue
        lot["mark_px"] = round(qqq_px, 4)
        side_mult = 1 if lot["side"] == "long" else -1
        leg_unrl = (qqq_px - lot["entry_px"]) * side_mult * lot["shares_remaining"]
        unrl_by_leg[leg] = round(leg_unrl, 2)
        unrl += leg_unrl
    state["_unrl_by_leg"] = unrl_by_leg
    total = state.get("realized_pnl_today", 0.0) + unrl
    limit = float(cfg.get("daily_loss_limit_usd", 0) or 0)
    if limit and total <= -abs(limit) and not state.get("breaker_tripped"):
        log(f"[qqq-exec] BREAKER TRIPPED: today's shadow P&L {total:.2f} <= "
            f"-{limit:.2f} -- closing all lots")
        _close_all(state, cfg, "BREAKER", quote_fn, ratio_fn, log=log)
        state["breaker_tripped"] = True
        _notify(f"QQQ SHADOW breaker tripped: {total:.2f} (limit -{limit:.2f})",
               "EDGELOG QQQ SHADOW BREAKER", log)
        _log_event(state, "breaker",
                  f"Daily loss breaker tripped at ${total:.2f} (limit -${limit:.2f}) -- "
                  f"all shadow lots closed", log=log)
    return unrl


# -- feed uptime per day (feature 2) --------------------------------------------------------
def _accumulate_feed_uptime(state, nowdt, stale, log=print):
    """Called once per tick while inside the market window. Accumulates raw tick/stale
    counts per ET calendar date so a dead-feed morning (2026-09-03) can never again go
    unrecorded. Rolling 60-day cap. Never raises -- a failure here must not affect
    trading logic, only the historical uptime record."""
    try:
        day = nowdt.strftime("%Y-%m-%d")
        hhmm = nowdt.strftime("%H:%M")
        days = state.setdefault("feed_days", {})
        d = days.setdefault(day, {"ticks": 0, "stale_ticks": 0,
                                  "first_tick_et": hhmm, "last_tick_et": hhmm})
        d["ticks"] = int(d.get("ticks", 0)) + 1
        if stale:
            d["stale_ticks"] = int(d.get("stale_ticks", 0)) + 1
        if not d.get("first_tick_et") or hhmm < d["first_tick_et"]:
            d["first_tick_et"] = hhmm
        if not d.get("last_tick_et") or hhmm > d["last_tick_et"]:
            d["last_tick_et"] = hhmm
        if len(days) > 60:
            for k in sorted(days.keys())[:-60]:
                days.pop(k, None)
    except Exception as e:
        log(f"[qqq-exec] feed uptime accumulate failed: {type(e).__name__}: {e}")


def _expected_ticks(day):
    """Expected tick count for one ET calendar date's active window: 09:25 ET to
    min(16:05, that date's market_calendar session close), at TICK_SEC intervals.

    COVERAGE-BASED UPTIME (2026-09-08 fix): the old uptime formula (1 - stale_ticks /
    ticks) only ever looked at ticks that DID happen, so a day the adapter's tick thread
    was simply ABSENT (runner restarts, a hung process) published as a perfect 100%
    uptime -- `ticks` was small, but `stale_ticks` was 0 for every tick that DID fire, so
    the ratio still read 1.0. This is the missing denominator: how many ticks the day
    SHOULD have produced, so a day with only half its ticks reads as ~50% coverage no
    matter how healthy each individual tick that did land was. `day` accepts a date
    string or datetime/date -- forwarded to market_calendar as-is."""
    try:
        if not market_calendar.is_session(day):
            return 0
        close = market_calendar.session_close_et(day)  # "16:00" normally, "13:00" half-day
        ch, cm = _hhmm(close)
        window_start_min = 9 * 60 + 25
        window_end_min = min(16 * 60 + 5, ch * 60 + cm)
        secs = max(0, (window_end_min - window_start_min) * 60)
        return int(secs / TICK_SEC)
    except Exception:
        return 0


def _build_feed_days(state):
    """[{date,ticks,expected_ticks,coverage_pct,uptime_pct,stale_min,first_tick,
    last_tick,valid,note}, ...] oldest-first, derived from the raw per-day tick/stale
    counts in state['feed_days'].

    COVERAGE-BASED UPTIME (2026-09-08 fix -- see module docstring feature (2)):
    `coverage_pct` = ticks actually recorded / ticks the session SHOULD have produced
    (_expected_ticks) -- this is what makes an adapter that was simply ABSENT for part
    of the day (not running at all, vs. running but stale) show up as reduced uptime.
    `uptime_pct` = coverage_pct * (1 - stale_ticks/ticks) folds BOTH failure modes (never
    ticked, and ticked-but-stale) into one number. A day is `valid` evidence only if
    uptime_pct >= 95% AND the adapter was watching by 09:35 ET AND stayed watching
    through 15:55 ET."""
    out = []
    days = state.get("feed_days") or {}
    for day in sorted(days.keys()):
        try:
            d = days[day] or {}
            ticks = int(d.get("ticks") or 0)
            stale_ticks = int(d.get("stale_ticks") or 0)
            expected_ticks = _expected_ticks(day)
            # Capped at 1.0: the tick loop's active window (09:25-16:05) runs a few
            # minutes longer than _expected_ticks' denominator (09:25-session close), so
            # a perfectly healthy day can otherwise read as slightly OVER 100% coverage.
            coverage_pct = min(1.0, round(ticks / expected_ticks, 4)) if expected_ticks else 0.0
            uptime_within_ticks = (1.0 - (stale_ticks / ticks)) if ticks else 0.0
            uptime_pct = round(coverage_pct * uptime_within_ticks, 4)
            stale_min = round(stale_ticks * TICK_SEC / 60.0, 1)
            first_tick = d.get("first_tick_et")
            last_tick = d.get("last_tick_et")
            valid = bool(ticks > 0 and uptime_pct >= 0.95
                        and first_tick and first_tick <= "09:35"
                        and last_tick and last_tick >= "15:55")
            note = d.get("note") or ""
            if not valid and not note:
                reasons = []
                if ticks == 0:
                    reasons.append("adapter never ticked this session")
                else:
                    missing_ticks = max(0, expected_ticks - ticks)
                    missing_min = missing_ticks * TICK_SEC / 60.0
                    if missing_min >= 1:
                        reasons.append(f"adapter absent ~{missing_min:.0f} min (restarts "
                                      f"or publish stalls)")
                    if stale_min > 0:
                        reasons.append(f"feed stale ~{stale_min:.0f} min while ticking")
                    if first_tick and first_tick > "09:35":
                        reasons.append(f"didn't start watching until {first_tick} ET")
                    if last_tick and last_tick < "15:55":
                        reasons.append(f"stopped watching by {last_tick} ET")
                note = ("; ".join(reasons) + " -- day not valid evidence") if reasons \
                    else "day not valid evidence"
            out.append({"date": day, "ticks": ticks, "expected_ticks": expected_ticks,
                       "coverage_pct": coverage_pct, "uptime_pct": uptime_pct,
                       "stale_min": stale_min, "first_tick": first_tick, "last_tick": last_tick,
                       "valid": valid, "note": note})
        except Exception:
            continue
    return out[-60:]


# -- tick gap (2026-09-08 fix) --------------------------------------------------------------
def _track_tick_gap(state, nowdt, now_wall=None, log=print):
    """Real WALL-CLOCK gap since the previous active tick -- deliberately independent of
    the `now` ET timestamp callers may inject for market-hours simulation, because a
    stall in the tick loop itself (a hung publish, a GC pause, thread scheduling, a
    runner restart) is a real-time phenomenon that must show up even when the adapter is
    fed a fixed/simulated `now`. THE BUG THIS FIXES (2026-09-08): the old synchronous
    Firestore publish blocked this exact loop for up to 60s per failure and there was no
    record of it at all -- see module docstring feature (2) and _Publisher below.

    Rolling per-ET-day max in state['tick_gap_max_s_today']; logs a `tick_gap` event each
    time a gap exceeds TICK_GAP_WARN_SEC (no cooldown -- each is a distinct real stall).
    Returns the gap in seconds, or None on the first tick of a fresh state. Never raises."""
    try:
        wall = now_wall if now_wall is not None else time.time()
        day = nowdt.strftime("%Y-%m-%d")
        if state.get("_tick_gap_day") != day:
            state["_tick_gap_day"] = day
            state["tick_gap_max_s_today"] = 0.0
        last = state.get("_last_tick_wall")
        state["_last_tick_wall"] = wall
        if last is None:
            return None
        gap = round(wall - last, 2)
        if gap > float(state.get("tick_gap_max_s_today", 0.0) or 0.0):
            state["tick_gap_max_s_today"] = gap
        if gap > TICK_GAP_WARN_SEC:
            log(f"[qqq-exec] WARN tick loop gap {gap:.0f}s (expected ~{TICK_SEC:g}s)")
            _log_event(state, "tick_gap",
                      f"tick loop gap of {gap:.0f}s detected (expected ~{TICK_SEC:g}s) -- "
                      f"a stall between ticks, not a feed/publish problem by itself",
                      log=log)
        return gap
    except Exception as e:
        log(f"[qqq-exec] tick gap tracking failed: {type(e).__name__}: {e}")
        return None


# -- feed staleness ------------------------------------------------------------------------
def _check_feed(state, fills_path, log=print):
    age, _version, _accts = nt_sync._addon_heartbeat(fills_path)
    stale = age is None or age > FEED_STALE_SEC
    was = state.get("feed_stale", False)
    state["feed_stale"] = stale
    if stale and not was:
        _log_event(state, "feed_down",
                  f"NinjaTrader fill feed went stale ({('%.0fs' % age) if age is not None else 'no heartbeat'}) "
                  f"-- new entries blocked", log=log)
    if stale and (time.time() - float(state.get("last_feed_alert", 0) or 0)
                 > FEED_ALERT_COOLDOWN_SEC):
        _notify(f"NinjaTrader fill feed stale ({('%.0fs' % age) if age is not None else 'no heartbeat'}) "
               f"-- QQQ SHADOW is not opening new lots", "EDGELOG QQQ SHADOW: feed stale", log)
        state["last_feed_alert"] = time.time()
    elif not stale and was:
        log("[qqq-exec] feed heartbeat recovered")
        _log_event(state, "feed_up", "NinjaTrader fill feed heartbeat recovered", log=log)
    return stale


# -- NT parity (feature 1) -------------------------------------------------------------------
def _f_or_none(v):
    try:
        return float(v) if v not in (None, "") else None
    except Exception:
        return None


def _trade_parity(row, log=print):
    """Compute the NT-mirror parity block for one trades.csv row (a dict of strings, as
    read back by csv.DictReader). Returns a dict with nt_points/expected_usd/
    track_err_usd/parity_ok/parity_note -- parity_ok is None ("not checked") when the
    row doesn't carry enough NT fill data (pre-feature rows not yet backfilled, or a
    lot whose parity fields failed to capture). Never raises."""
    try:
        entry_px = _f_or_none(row.get("nt_entry_px"))
        exit_px = _f_or_none(row.get("nt_exit_px"))
        ratio = _f_or_none(row.get("ratio_at_entry"))
        side = row.get("side")
        shares = _f_or_none(row.get("shares")) or 0.0
        pnl = _f_or_none(row.get("pnl")) or 0.0
        exit_matched = bool(str(row.get("nt_exit_exec_id") or "").strip())
        reconstructed = str(row.get("nt_reconstructed") or "").strip() not in ("", "0", "False", "false")

        if entry_px is None or exit_px is None or not ratio:
            return {"nt_points": None, "expected_usd": None, "track_err_usd": None,
                   "parity_ok": None,
                   "parity_note": "reconstructed" if reconstructed else
                                  "insufficient NT fill data to check parity"}

        dir_mult = 1 if side == "long" else -1
        nt_points = round((exit_px - entry_px) * dir_mult, 4)
        expected_usd = round((nt_points / ratio) * shares, 2)
        track_err = round(pnl - expected_usd, 2)
        tol = max(0.05, 0.02 * abs(expected_usd))
        ok = abs(track_err) <= tol
        note = ""
        if not ok:
            if not exit_matched:
                note = "no NT exit fill matched -- closed by the EOD rail"
            else:
                ratio_exit = _f_or_none(row.get("ratio_at_exit"))
                if ratio_exit and ratio:
                    drift = (ratio_exit - ratio) / ratio * 100.0
                    if abs(drift) > 0.3:
                        note = f"ratio drifted {drift:.2f}% between entry and exit"
                if not note:
                    note = f"tracking error ${track_err:.2f} exceeds tolerance ${tol:.2f}"
        if reconstructed:
            note = "reconstructed"
        return {"nt_points": nt_points, "expected_usd": expected_usd,
               "track_err_usd": track_err, "parity_ok": bool(ok), "parity_note": note}
    except Exception as e:
        log(f"[qqq-exec] parity calc failed for a trade row: {type(e).__name__}: {e}")
        return {"nt_points": None, "expected_usd": None, "track_err_usd": None,
               "parity_ok": None, "parity_note": f"parity calc failed: {type(e).__name__}"}


def _parity_summary(trades_all):
    """Headline parity read.

    RECONSTRUCTED rows are counted SEPARATELY and never fail the headline. They were
    back-filled from the fill log after the fact (tools/qqq_exec_backfill_parity.py),
    so their tracking error is an estimate, not a measurement -- and the two seeded on
    2026-09-03 miss by design, because the shadow flattened at its old 15:58 rail while
    NinjaTrader exited at 15:59:31/15:59:51, i.e. at a different NQ price. Counting them
    as live failures painted the board red and read as "the mirror is broken" when no
    live-captured trade had been checked at all.
    """
    checked = ok = failed = reconstructed = 0
    worst = 0.0
    worst_note = ""
    recon_worst = 0.0
    for t in trades_all:
        pok = t.get("parity_ok")
        if pok is None:
            continue
        te = t.get("track_err_usd")
        if str(t.get("parity_note") or "").strip().lower() == "reconstructed":
            reconstructed += 1
            if te is not None and abs(te) > abs(recon_worst):
                recon_worst = te
            continue
        checked += 1
        if pok:
            ok += 1
        else:
            failed += 1
        if te is not None and abs(te) > abs(worst):
            worst = te
            worst_note = t.get("parity_note") or ""
    if checked == 0:
        if reconstructed:
            note = (f"no live-captured trade has been checked yet -- the {reconstructed} row(s) "
                    f"on the board were reconstructed from the fill log after the fact and are "
                    f"reference only")
        else:
            note = "no trades have enough NT fill data to check parity yet"
    elif failed == 0:
        note = "every checked trade reconciles with its NinjaTrader fill"
    else:
        note = f"{failed} of {checked} live-captured trade(s) miss their NinjaTrader fill"
        if worst_note and worst_note.lower() != "reconstructed":
            note += f" -- worst: {worst_note}"
    return {"checked": checked, "ok": ok, "failed": failed,
           "reconstructed": reconstructed,
           "reconstructed_worst_err_usd": round(recon_worst, 2),
           "worst_err_usd": round(worst, 2), "note": note}

def _all_trades_from_csv(cap=500):
    """Every closed shadow trade recorded since inception, oldest-first as the CSV
    stores them (trades.csv is append-only, trimmed to TRADES_KEEP by _append_csv).
    Returns at most `cap` rows -- the newest `cap`, so a long history never silently
    drops recent trades in favour of old ones."""
    try:
        with open(TRADES_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return []
    return rows[-cap:]


def _cum_pnl_by_leg(all_trades):
    """{leg: [{"date","cum_pnl"}, ...], total: [...]} -- one point per
    calendar date (ET, off exit_ts) a leg had at least one close, cumulative sum of
    `pnl` in chronological order. Powers the equity-curve chart and the per-leg
    since-start KPI without the client re-deriving it from trades_all."""
    out = {leg: [] for leg in LEGS}
    running = {leg: 0.0 for leg in LEGS}
    by_leg_date = {leg: {} for leg in LEGS}
    for t in sorted(all_trades, key=lambda r: (r.get("exit_ts") or r.get("entry_ts") or "")):
        leg = t.get("leg")
        if leg not in by_leg_date:
            continue
        date = str(t.get("exit_ts") or t.get("entry_ts") or "")[:10]
        if not date:
            continue
        try:
            pnl = float(t.get("pnl") or 0)
        except Exception:
            pnl = 0.0
        running[leg] = round(running[leg] + pnl, 2)
        by_leg_date[leg][date] = running[leg]  # last value wins for that date
    for leg in LEGS:
        out[leg] = [{"date": d, "cum_pnl": v} for d, v in sorted(by_leg_date[leg].items())]
    # total: merge all legs onto the union of dates, carrying each leg's last-known value
    all_dates = sorted({p["date"] for leg in LEGS for p in out[leg]})
    last = {leg: 0.0 for leg in LEGS}
    idx = {leg: 0 for leg in LEGS}
    total_pts = []
    for d in all_dates:
        for leg in LEGS:
            series = out[leg]
            while idx[leg] < len(series) and series[idx[leg]]["date"] <= d:
                last[leg] = series[idx[leg]]["cum_pnl"]
                idx[leg] += 1
        total_pts.append({"date": d, "cum_pnl": round(sum(last.values()), 2)})
    out["total"] = total_pts
    return out


# -- latency (feature #51) -----------------------------------------------------------
def _build_latency(orders, log=print):
    """{n,median_s,p95_s,max_s,last_s} over today's orders that carry a latency_s
    (adapter order time - NT fill time, ET). `orders` is assumed in file order
    (ascending by append time), so the last value seen is the most recent order's."""
    try:
        vals = []
        last = None
        for o in orders:
            v = o.get("latency_s")
            if v in (None, ""):
                continue
            try:
                fv = float(v)
            except Exception:
                continue
            vals.append(fv)
            last = fv
        if not vals:
            return {"n": 0, "median_s": None, "p95_s": None, "max_s": None, "last_s": None}
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        idx95 = min(n - 1, int(round(0.95 * (n - 1))))
        return {"n": n, "median_s": round(statistics.median(vals_sorted), 3),
               "p95_s": round(vals_sorted[idx95], 3), "max_s": round(vals_sorted[-1], 3),
               "last_s": round(last, 3)}
    except Exception as e:
        log(f"[qqq-exec] latency build failed: {type(e).__name__}: {e}")
        return {"n": 0, "median_s": None, "p95_s": None, "max_s": None, "last_s": None}


# -- reprice merge (feature #48 half) -------------------------------------------------
REPRICE_MERGE_FIELDS = ["real_entry_px", "real_exit_px", "real_pnl", "slip_entry_ps",
                        "slip_exit_ps", "repriced_at", "source", "note"]


def _load_reprice_sidecar(log=print):
    """key (leg, entry_ts) -> sidecar row, from C:\\EdgeLog\\qqq_exec\\reprice.csv
    (written by the sibling tools/qqq_reprice.py). Missing/unreadable -> {}, never
    raises -- this file is owned by a different tool and may not exist yet."""
    path = os.path.join(os.path.dirname(TRADES_CSV) or OUT_DIR, "reprice.csv")
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                out[(row.get("leg"), row.get("entry_ts"))] = row
    except Exception as e:
        log(f"[qqq-exec] reprice sidecar read failed: {type(e).__name__}: {e}")
    return out


def _merge_reprice(trades_all, log=print):
    """Merges matching sidecar fields onto trades_all rows IN PLACE (absent when no
    sidecar row matches (leg, entry_ts)) and returns the reprice summary block."""
    try:
        sidecar = _load_reprice_sidecar(log=log)
        covered = 0
        slips = []
        last_run = None
        for row in trades_all:
            src = sidecar.get((row.get("leg"), row.get("entry_ts")))
            if not src:
                continue
            covered += 1
            for fld in REPRICE_MERGE_FIELDS:
                v = src.get(fld)
                if v not in (None, ""):
                    row[fld] = v
            for fld in ("slip_entry_ps", "slip_exit_ps"):
                v = _f_or_none(src.get(fld))
                if v is not None:
                    slips.append(v)
            rat = src.get("repriced_at")
            if rat and (last_run is None or rat > last_run):
                last_run = rat
        total = len(trades_all)
        coverage_pct = round(covered / total, 4) if total else 1.0
        mean_slip_ps = round(sum(slips) / len(slips), 4) if slips else None
        return {"covered": covered, "total": total, "coverage_pct": coverage_pct,
               "mean_slip_ps": mean_slip_ps, "last_run": last_run}
    except Exception as e:
        log(f"[qqq-exec] reprice merge failed: {type(e).__name__}: {e}")
        return {"covered": 0, "total": len(trades_all), "coverage_pct": 0.0,
               "mean_slip_ps": None, "last_run": None}


def _maybe_run_reprice(state, nowdt, log=print):
    """Once per ET weekday, after 16:20 ET, shells out to tools/qqq_reprice.py --apply
    (the sidecar-writing tool owned by a different agent). Non-fatal if the tool
    doesn't exist yet, times out, or errors -- this adapter's own trading logic must
    never depend on it."""
    try:
        if not _is_weekday(nowdt):
            return
        if _et_hhmm(nowdt) < (16, 20):
            return
        today = nowdt.strftime("%Y-%m-%d")
        if state.get("reprice_done_date") == today:
            return
        state["reprice_done_date"] = today  # mark attempted even if the tool is missing/fails
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(repo_root, "tools", "qqq_reprice.py")
        if not os.path.exists(script):
            log(f"[qqq-exec] reprice tool not found at {script} -- skipping (non-fatal)")
            return
        try:
            subprocess.run([sys.executable, script, "--apply"], timeout=120, check=False)
        except Exception as e:
            log(f"[qqq-exec] reprice subprocess failed: {type(e).__name__}: {e}")
        _log_event(state, "reprice", "Daily broker reprice reconciliation ran", log=log)
    except Exception as e:
        log(f"[qqq-exec] reprice scheduling failed: {type(e).__name__}: {e}")


# -- readiness (feature #53) -----------------------------------------------------------
def _build_readiness(feed_days, parity, reprice, state, log=print):
    """{ready,days_valid,days_required,live_parity_checked,live_parity_failed,
    uptime_mean_10,rail_trips_unexplained,reprice_coverage_pct,missing,note} -- the
    single go/no-go read for "is the shadow book real evidence yet". Reconstructed
    rows never count toward live_parity_* because _parity_summary already excludes
    them from checked/failed."""
    try:
        days_valid = sum(1 for d in feed_days if d.get("valid"))
        live_parity_checked = int(parity.get("checked") or 0)
        live_parity_failed = int(parity.get("failed") or 0)
        last10 = feed_days[-10:]
        uptime_vals = [d.get("uptime_pct") for d in last10 if d.get("uptime_pct") is not None]
        uptime_mean_10 = round(sum(uptime_vals) / len(uptime_vals), 4) if uptime_vals else 0.0
        # No "explained trip" bookkeeping exists yet -- every breaker trip on the rolling
        # event timeline counts as unexplained until that mechanism exists, which is the
        # conservative (safe) default for a live-sizing gate.
        rail_trips_unexplained = sum(1 for e in (state.get("events") or [])
                                     if e.get("kind") == "breaker")
        reprice_total = int(reprice.get("total") or 0)
        reprice_coverage_pct = float(reprice.get("coverage_pct")) if reprice_total else 1.0
        ready = (days_valid >= DAYS_REQUIRED and live_parity_checked >= DAYS_REQUIRED and
                live_parity_failed == 0 and uptime_mean_10 >= 0.95 and
                rail_trips_unexplained == 0 and reprice_coverage_pct >= 0.9)
        missing = []
        if days_valid < DAYS_REQUIRED:
            missing.append(f"only {days_valid} of {DAYS_REQUIRED} valid trading days recorded so far")
        if live_parity_checked < DAYS_REQUIRED:
            missing.append(f"only {live_parity_checked} live-captured trade(s) have been "
                           f"parity-checked against NinjaTrader (need {DAYS_REQUIRED})")
        if live_parity_failed > 0:
            missing.append(f"{live_parity_failed} live-captured trade(s) failed the "
                           f"NinjaTrader parity check")
        if uptime_mean_10 < 0.95:
            missing.append(f"average feed uptime over the last {len(last10)} day(s) is "
                           f"{uptime_mean_10 * 100:.1f}% (need at least 95%)")
        if rail_trips_unexplained > 0:
            missing.append(f"{rail_trips_unexplained} breaker trip(s) on record, none yet "
                           f"marked explained")
        if reprice_coverage_pct < 0.9:
            missing.append(f"only {reprice_coverage_pct * 100:.0f}% of closed trades have a "
                           f"broker-verified reprice (need at least 90%)")
        note = "ready for a live-sizing decision" if ready else "; ".join(missing)
        return {"ready": bool(ready), "days_valid": days_valid, "days_required": DAYS_REQUIRED,
               "live_parity_checked": live_parity_checked, "live_parity_failed": live_parity_failed,
               "uptime_mean_10": uptime_mean_10, "rail_trips_unexplained": rail_trips_unexplained,
               "reprice_coverage_pct": round(reprice_coverage_pct, 4), "missing": missing,
               "note": note}
    except Exception as e:
        log(f"[qqq-exec] readiness build failed: {type(e).__name__}: {e}")
        return {"ready": False, "days_valid": 0, "days_required": DAYS_REQUIRED,
               "live_parity_checked": 0, "live_parity_failed": 0, "uptime_mean_10": 0.0,
               "rail_trips_unexplained": 0, "reprice_coverage_pct": 0.0,
               "missing": [f"readiness unavailable: {type(e).__name__}"],
               "note": "readiness calc failed"}


# -- EOD phone summary (feature #55) --------------------------------------------------
def _maybe_send_eod_summary(state, doc, nowdt, log=print):
    """Once per ET weekday, at/after 16:05 ET, pushes one ntfy summary of the day."""
    try:
        if not _is_weekday(nowdt):
            return
        if _et_hhmm(nowdt) < (16, 5):
            return
        today = nowdt.strftime("%Y-%m-%d")
        if state.get("eod_summary_done_date") == today:
            return
        n = len(doc["today"]["trades"])
        pnl = doc["today"]["realized_pnl"]
        parity = doc["parity"]
        today_feed = next((d for d in doc["feed_days"] if d["date"] == today), None)
        uptime_txt = f"{today_feed['uptime_pct'] * 100:.1f}%" if today_feed else "n/a"
        rail_trips = 1 if doc.get("breaker_tripped") else 0
        msg = (f"Trades {n} | P&L ${pnl:.2f} | parity checked/failed "
              f"{parity['checked']}/{parity['failed']} | feed uptime {uptime_txt} | "
              f"rail trips {rail_trips}")
        _notify(msg, "EDGELOG QQQ SHADOW: EOD summary", log)
        state["eod_summary_done_date"] = today
        _log_event(state, "eod_summary", msg, log=log)
    except Exception as e:
        log(f"[qqq-exec] EOD summary failed: {type(e).__name__}: {e}")


def _build_doc(cfg, state, feed_stale, unrealized, log=print):
    orders = []
    try:
        with open(ORDERS_CSV, encoding="utf-8", newline="") as f:
            orders = list(csv.DictReader(f))[-100:]
    except Exception:
        orders = []
    trades = []
    try:
        with open(TRADES_CSV, encoding="utf-8", newline="") as f:
            trades = list(csv.DictReader(f))[-100:]
    except Exception:
        trades = []

    # TODAY means today. Both lists above are only the CSV tails, so before this filter
    # the tab's "TODAY'S ORDERS" panel and every leg card's TODAY figure kept showing the
    # previous session (2026-09-05: Sep 3's four orders labelled as today's, and leg cards
    # reading $2.89 TODAY against a $0.00 TODAY KPI). Full history still ships in
    # trades_all / cum_pnl, which is what the closed-trades table and the curve read.
    day = state.get("trading_day") or _now_et().strftime("%Y-%m-%d")
    orders = [o for o in orders if str(o.get("ts_et") or "")[:10] == day]
    trades = [t for t in trades if str(t.get("exit_ts") or "")[:10] == day]
    # trades_all / cum_pnl: the full (capped) history, independent of the `today`
    # block above -- the equity curve and since-start KPIs need every closed trade
    # since LIVE_FROM, not just the last 100 kept for the TODAY'S ORDERS panel.
    all_trades = _all_trades_from_csv(cap=500)
    trades_all_raw = list(reversed(all_trades))  # newest first, per the web tab's table convention
    cum_pnl = _cum_pnl_by_leg(all_trades)

    # NT PARITY (feature 1): every row of trades_all carries the parity fields computed
    # fresh from its own CSV columns (works identically for a trade just closed this
    # tick and for the two 2026-09-03 rows the backfill script rewrote) -- non-fatal,
    # a row that fails to price just publishes as "not checked".
    trades_all = []
    for r in trades_all_raw:
        row = dict(r)
        row.update(_trade_parity(r, log=log))
        trades_all.append(row)
    parity = _parity_summary(trades_all)

    # REPRICE MERGE (feature #48 half): merges broker-verified fields onto trades_all
    # IN PLACE and returns the coverage summary.
    reprice = _merge_reprice(trades_all, log=log)

    feed_days = _build_feed_days(state)
    ratio_hist = (state.get("ratio_hist") or [])[-500:]
    ratio_health = _build_ratio_health(state, _now_et(), log=log)
    unrl_by_leg = state.get("_unrl_by_leg") or {}
    positions = {}
    for leg, lot in state.get("legs", {}).items():
        positions[leg] = {"side": lot["side"], "shares": lot["shares_remaining"],
                          "entry_px": lot["entry_px"], "entry_ts": lot["entry_ts"],
                          "unrealized": unrl_by_leg.get(leg, 0.0),
                          # NT SIZING GAP (feature #50): live view of the open lot's
                          # sizing vs. the NT position it mirrors.
                          "nt_mult": lot.get("nt_mult"),
                          "nt_notional_usd": lot.get("nt_notional_usd"),
                          "shadow_notional_usd": lot.get("shadow_notional_usd"),
                          "notional_ratio": lot.get("notional_ratio")}

    # LATENCY (feature #51): today's orders only, per module docstring.
    latency = _build_latency(orders, log=log)
    # SIGNALS FIRED VS TAKEN (feature #55) + EVENT TIMELINE (feature #52).
    signals_day = _build_signals_day(state)
    events = list(reversed((state.get("events") or [])))[:EVENTS_KEEP]
    # READINESS (feature #53): the single go/no-go read, built off everything above.
    readiness = _build_readiness(feed_days, parity, reprice, state, log=log)
    # HEALTH (2026-09-08 fix): the adapter's own operational vitals -- publish failures
    # and the largest tick-loop stall today -- independent of trading/feed logic, so a
    # silent infrastructure problem (Firestore down, the loop stalling) is visible on the
    # web tab even on a day nothing else went wrong. See _record_publish_result /
    # _track_tick_gap and module docstring feature (2).
    health = {"publish_fail_today": int(state.get("publish_fail_today", 0) or 0),
             "last_publish_ok_et": state.get("last_publish_ok_et"),
             "tick_gap_max_s_today": float(state.get("tick_gap_max_s_today", 0.0) or 0.0)}

    return {
        "mode": cfg.get("mode"), "updated_at": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
        "live_from": LIVE_FROM,
        "feed_stale": bool(feed_stale), "breaker_tripped": bool(state.get("breaker_tripped")),
        "kill": bool(state.get("kill_done")), "calib": state.get("calib"),
        "positions": positions,
        "today": {"orders": orders, "trades": trades,
                  "realized_pnl": state.get("realized_pnl_today", 0.0),
                  "unrealized_pnl": round(unrealized, 2)},
        "trades_all": trades_all,
        "parity": parity,
        "feed_days": feed_days,
        "ratio_hist": ratio_hist,
        "ratio_health": ratio_health,
        "cum_pnl": cum_pnl,
        "latency": latency,
        "signals_day": signals_day,
        "events": events,
        "readiness": readiness,
        "health": health,
        "reprice": reprice,
        "rails": {"shares": cfg.get("shares"), "max_shares_per_leg": cfg.get("max_shares_per_leg"),
                  "daily_loss_limit_usd": cfg.get("daily_loss_limit_usd"),
                  "session": cfg.get("session"), "slippage_per_share": cfg.get("slippage_per_share"),
                  "kill_file": cfg.get("kill_file"), "size_mode": cfg.get("size_mode"),
                  "size_fraction": cfg.get("size_fraction")},
    }


def _record_publish_result(state, ok, err=None, log=print):
    """Folds one publish attempt's outcome into `state` -- publish_fail_today /
    last_publish_ok_et (published under doc['health'], see _build_doc), a runner.log
    line at most once per PUBLISH_FAIL_LOG_COOLDOWN_SEC, and a `publish_down` event on
    the same cooldown. Shared by both the synchronous (--once) and background-thread
    publish paths so the health numbers mean the same thing either way. Never raises."""
    try:
        today = _now_et().strftime("%Y-%m-%d")
        if state.get("_publish_fail_day") != today:
            state["_publish_fail_day"] = today
            state["publish_fail_today"] = 0
        if ok:
            state["last_publish_ok_et"] = _now_et().strftime("%H:%M:%S")
            return
        state["publish_fail_today"] = int(state.get("publish_fail_today", 0) or 0) + 1
        now = time.time()
        last_log = float(state.get("_last_publish_fail_log", 0) or 0)
        if now - last_log > PUBLISH_FAIL_LOG_COOLDOWN_SEC:
            n = state["publish_fail_today"]
            log(f"[qqq-exec] publish failing ({err}) -- shadow keeps ticking; "
                f"{n} failure(s) since {_now_et().strftime('%H:%M')}")
            _log_event(state, "publish_down",
                      f"Firestore publish failing ({err}) -- shadow keeps ticking, "
                      f"{n} failure(s) today", log=log)
            state["_last_publish_fail_log"] = now
    except Exception as e:
        log(f"[qqq-exec] publish result tracking failed: {type(e).__name__}: {e}")


class _Publisher:
    """Owns every Firestore write this adapter makes, on a SINGLE dedicated background
    thread, so a slow or failing publish can never again stall the 5s tick loop.

    THE BUG THIS FIXES (2026-09-08, second live shadow day): the old `_publish` called
    `set()` inline in the tick loop. 2,245 Firestore "503 failed to connect to all
    addresses" errors that day each retried for up to 60s before giving up, and every one
    of those 60s windows was NinjaTrader fills the adapter was not watching for -- with
    nothing on the record to show it happened (the old uptime formula only ever counted
    ticks that DID fire).

    `submit` is the only thing the tick loop calls, and it never blocks: it just replaces
    whatever doc is currently pending for that uid (older pending docs are DROPPED, not
    queued -- only the newest state matters to the web tab) and wakes the writer thread.
    The writer thread bounds every actual `set()` to PUBLISH_TIMEOUT_SEC via a throwaway
    worker + `future.result(timeout=...)`, the same hard-timeout pattern already used for
    the Webull quote call (see default_webull_quote) -- a `timeout=` kwarg passed to
    `set()` itself is a soft/best-effort hint on some client versions, not a guarantee."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}          # uid -> (db, doc, state, log)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._ex = concurrent.futures.ThreadPoolExecutor(max_workers=1,
                                                          thread_name_prefix="qqq-publish")

    def start(self, log=print):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="qqq-publisher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def submit(self, db, uid, doc, state, log=print):
        """Non-blocking: enqueue/replace the pending doc for `uid` and return immediately.
        Safe to call from the tick loop on every tick."""
        with self._lock:
            self._pending[uid] = (db, doc, state, log)
        self._wake.set()

    def _run(self):
        while not self._stop.is_set():
            fired = self._wake.wait(timeout=5.0)
            if self._stop.is_set():
                return
            if not fired:
                continue
            self._wake.clear()
            with self._lock:
                batch = list(self._pending.items())
                self._pending.clear()
            for uid, (db, doc, state, log) in batch:
                self.write_one(db, uid, doc, state, log=log)

    def write_one(self, db, uid, doc, state, log=print):
        """The actual write, bounded to PUBLISH_TIMEOUT_SEC. Called from the background
        writer thread for the live loop, and called DIRECTLY (synchronously, on the
        caller's own thread) by publish_now for --once, where the process exits right
        after and there is no later tick for a background thread to flush to. Either way
        this never raises -- failure is recorded via _record_publish_result, not thrown."""
        fut = self._ex.submit(self._do_set, db, uid, doc)
        try:
            fut.result(timeout=PUBLISH_TIMEOUT_SEC)
            _record_publish_result(state, True, log=log)
        except concurrent.futures.TimeoutError:
            _record_publish_result(state, False,
                                   err=f"timed out after {PUBLISH_TIMEOUT_SEC:g}s", log=log)
        except Exception as e:
            _record_publish_result(state, False, err=f"{type(e).__name__}: {e}", log=log)

    @staticmethod
    def _do_set(db, uid, doc):
        ref = db.collection("users").document(uid).collection("meta").document("qqq_exec")
        try:
            ref.set(doc, timeout=PUBLISH_TIMEOUT_SEC)
        except TypeError:
            # Some client stubs (and the smoke test's stub db) don't accept a `timeout`
            # kwarg on set() -- the ThreadPoolExecutor future above is the real hard
            # timeout backstop regardless, this is just for compatibility.
            ref.set(doc)


_publisher = _Publisher()


def _should_publish(state, doc, force=False):
    """True if `doc` differs from the last-published hash, or `force`, or 60s have
    passed since the last publish -- unchanged throttle logic from the old `_publish`,
    just factored out so both the sync and async publish paths share it."""
    payload = json.dumps(doc, sort_keys=True, default=str)
    h = str(hash(payload))
    now = time.time()
    should = force or h != state.get("last_doc_hash") or now - state.get("last_publish", 0) >= 60
    return should, h, now


def publish_async(db, uid, doc, state, force=False, log=print):
    """Non-blocking publish for the live tick loop -- enqueues on the background
    _Publisher thread and returns immediately regardless of Firestore's health. Never
    raises."""
    try:
        should, h, now = _should_publish(state, doc, force=force)
        if not should:
            return
        state["last_doc_hash"] = h
        state["last_publish"] = now
        _publisher.start(log=log)
        _publisher.submit(db, uid, doc, state, log=log)
    except Exception as e:
        log(f"[qqq-exec] publish enqueue failed: {type(e).__name__}: {e}")


def publish_now(db, uid, doc, state, force=True, log=print):
    """Synchronous publish for --once: the CLI process exits right after this call, so
    there is no later tick for the async publisher thread to flush a queued doc to. Still
    bounded to PUBLISH_TIMEOUT_SEC (via the same _Publisher.write_one path) so a dead
    Firestore endpoint can't hang the CLI either."""
    should, h, now = _should_publish(state, doc, force=force)
    if not should:
        return
    state["last_doc_hash"] = h
    state["last_publish"] = now
    _publisher.write_one(db, uid, doc, state, log=log)


# -- one tick --------------------------------------------------------------------------------
def tick(*, fills_path=DEFAULT_FILLS, now=None, quote_fn=default_webull_quote,
         ratio_fn=default_ratio_calibration, cfg=None, state=None, force_calib=False,
         _now_wall=None, log=print):
    """Run one adapter pass. Returns (cfg, state, doc) for callers/tests. Loads/saves
    config+state from disk unless the caller supplies them (tests inject fixed state).

    `force_calib`: attempt the ratio calibration even outside the market window. The
    live thread leaves this False (outside 09:25-16:05 ET it must stay a cheap no-op,
    not a yfinance call every TICK_SEC all night) but `--once` verification runs pass
    True so a dry run away from market hours still demonstrates/exercises pricing.

    `_now_wall`: real wall-clock seconds (time.time()-shaped) to use for tick-gap
    tracking (see _track_tick_gap), separate from `now` (which simulates ET market-hours
    logic and is often a fixed historical datetime in tests). Defaults to time.time()."""
    cfg = cfg if cfg is not None else load_config(log=log)
    state = state if state is not None else load_state(log=log)
    nowdt = now or _now_et()
    today = nowdt.strftime("%Y-%m-%d")
    _roll_day(state, today)
    state["_px_source"] = None

    # EVENT TIMELINE (feature #52): "boot" fires once per PROCESS start (a state.json
    # flag would only ever fire once across every future restart).
    if not _PROCESS["booted"]:
        _log_event(state, "boot", "QQQ SHADOW adapter started", log=log)
        _PROCESS["booted"] = True

    # MARKET CALENDAR: a holiday is not a trading day at all -- no market-window work,
    # no feed_days accumulation, no signals_day row, no EOD flatten/summary. Weekends
    # already fall out of _is_weekday/_in_market_window further down without needing
    # the calendar; this short-circuit only fires for a weekday NYSE/Nasdaq holiday
    # (e.g. Labor Day), which _in_market_window alone cannot tell from a normal Monday.
    if _is_weekday(nowdt) and not market_calendar.is_session(nowdt):
        if state.get("holiday_logged_date") != today:
            hname = market_calendar.holiday_name(nowdt) or "market holiday"
            log(f"[qqq-exec] {today} skipped -- {hname}, market closed")
            _log_event(state, "holiday", f"{today} skipped -- {hname}, market closed", log=log)
            state["holiday_logged_date"] = today
        doc = _build_doc(cfg, state, state.get("feed_stale", False), 0.0, log=log)
        save_state(state, log=log)
        return cfg, state, doc

    # MARKET CALENDAR: half-day early close (day after Thanksgiving, certain Jul 3 /
    # Dec 24) -- clamp flat_by to the EARLIER of the configured value and the
    # recognised early close, in memory only, for this tick's session dict. Never
    # edits config.json.
    sess_close = market_calendar.session_close_et(nowdt)
    if sess_close != "16:00":
        configured_flat = (cfg.get("session") or {}).get("flat_by", "15:58")
        if sess_close < configured_flat:
            cfg = dict(cfg)
            cfg["session"] = dict(cfg.get("session") or {})
            cfg["session"]["flat_by"] = sess_close
            if state.get("half_day_logged_date") != today:
                log(f"[qqq-exec] {today} is a recognised early close ({sess_close} ET) -- "
                    f"flat_by clamped from {configured_flat} to {sess_close}")
                _log_event(state, "half_day",
                          f"{today} early close ({sess_close} ET) -- flat_by clamped from "
                          f"{configured_flat} to {sess_close}", log=log)
                state["half_day_logged_date"] = today

    kill_present = os.path.exists(cfg.get("kill_file") or "")
    if kill_present and not state.get("kill_done"):
        log("[qqq-exec] KILL file present -- closing all shadow lots")
        _close_all(state, cfg, "KILL", quote_fn, ratio_fn, log=log)
        state["kill_done"] = True
        _notify("QQQ SHADOW: kill file present, all lots closed", "EDGELOG QQQ SHADOW KILL", log)
        _log_event(state, "kill", "Kill file present -- all shadow lots closed, new entries blocked",
                  log=log)
    elif not kill_present and state.get("kill_done"):
        state["kill_done"] = False
        log("[qqq-exec] kill file cleared")
        _log_event(state, "kill_clear", "Kill file cleared -- adapter resuming normal operation",
                  log=log)

    active = _in_market_window(nowdt)
    feed_stale = _check_feed(state, fills_path, log=log) if active else state.get("feed_stale", False)
    if active:
        _accumulate_feed_uptime(state, nowdt, feed_stale, log=log)
        _track_tick_gap(state, nowdt, now_wall=_now_wall, log=log)
        # EXPLICIT ZERO DAYS (feature #3): every active day gets a signals_days row even
        # if no signal ever fires, so "no signals today" is on the record rather than
        # indistinguishable from "the adapter never ran".
        _ensure_signals_day(state, today, log=log)

    if (active or force_calib) and not kill_present:
        _maybe_calibrate(state, ratio_fn, log=log)

    if active and not kill_present:
        fills = nt_sync.parse_fills(fills_path)
        # fills.csv "Time" is UTC (EdgeLogExport.cs: ex.Time.ToUniversalTime()). Convert to
        # New York once here so every rail below judges the fill on ET wall-clock time.
        for f in fills:
            f["dt"] = nt_sync._to_ny(f["dt"])
        base_ok = lambda inst: nt_sync.get_base(inst) in ("NQ", "MNQ")
        processed = set(state.get("processed_ids") or [])
        candidates = [f for f in fills if base_ok(f["instrument"]) and f["exec_id"] not in processed]
        # Never replay history: anything from before today's ET trading day is marked as
        # processed without routing (first boot would otherwise re-trade weeks of fills).
        stale_hist = [f for f in candidates if f["dt"].strftime("%Y-%m-%d") < today]
        if stale_hist:
            for f in stale_hist:
                processed.add(f["exec_id"])
            state["processed_ids"] = list(processed)[-5000:]
            log(f"[qqq-exec] skipped {len(stale_hist)} fill(s) from before {today} (history, not replayed)")
        new_fills = [f for f in candidates if f["dt"].strftime("%Y-%m-%d") >= today]
        new_fills.sort(key=lambda f: (f["dt"], f["_i"]))

        entries_blocked = (state.get("breaker_tripped") or feed_stale or kill_present)
        if new_fills:
            _route_fills(state, cfg, new_fills, quote_fn, ratio_fn, entries_blocked, log=log)
            for f in new_fills:
                processed.add(f["exec_id"])
            # cap the processed-id memory so state.json stays small
            state["processed_ids"] = list(processed)[-5000:]

        if _past_flat_by(nowdt, cfg["session"]) and state.get("flat_by_done_date") != today:
            if state.get("legs"):
                legs_open = list(state["legs"].keys())
                log("[qqq-exec] past flat_by -- closing remaining open lots")
                _close_all(state, cfg, "EOD", quote_fn, ratio_fn, log=log)
                _log_event(state, "eod_flatten",
                          f"End-of-day flatten closed: {', '.join(legs_open)}", log=log)
            state["flat_by_done_date"] = today

    unrealized = 0.0
    if not kill_present:
        unrealized = _mark_and_check_breaker(state, cfg, quote_fn, ratio_fn, log=log)

    # REPRICE MERGE (feature #48 half) + EOD PHONE SUMMARY (feature #55): both are
    # once-per-ET-day, time-gated jobs that must never block or crash a tick -- see
    # _maybe_run_reprice / _maybe_send_eod_summary for the schedule.
    _maybe_run_reprice(state, nowdt, log=log)

    doc = _build_doc(cfg, state, feed_stale, unrealized, log=log)
    _maybe_send_eod_summary(state, doc, nowdt, log=log)
    save_state(state, log=log)
    return cfg, state, doc


def run_once(uid=None, fills_path=DEFAULT_FILLS, db=None, log=print):
    cfg, state, doc = tick(fills_path=fills_path, force_calib=True, log=log)
    log(f"[qqq-exec] tick complete: mode={cfg.get('mode')} feed_stale={doc['feed_stale']} "
        f"breaker={doc['breaker_tripped']} positions={list(doc['positions'].keys())} "
        f"realized={doc['today']['realized_pnl']} unrealized={doc['today']['unrealized_pnl']} "
        f"calib={doc.get('calib')}")
    if db is not None and uid:
        publish_now(db, uid, doc, state, force=True, log=log)
        log(f"[qqq-exec] published users/{uid}/meta/qqq_exec "
            f"(publish_fail_today={state.get('publish_fail_today', 0)})")
    return doc


# -- runner thread hook (mirrors api.runner._bridge_watchdog_thread) ---------------------
def qqq_exec_thread(db, uids, stop=None, log=print):
    """Own thread, ticking every TICK_SEC -- never blocks the runner's main loop and
    never takes it down. Publishes to every allow-listed uid each tick that changed,
    at least once a minute regardless (see _publish's force/throttle logic)."""
    state = load_state(log=log)
    while stop is None or not stop.is_set():
        try:
            cfg = load_config(log=log)
            cfg2, state, doc = tick(cfg=cfg, state=state, log=log)
            for uid in uids:
                publish_async(db, uid, doc, state, log=log)
            save_state(state, log=log)
        except Exception as e:
            log(f"[qqq-exec] tick failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        (stop.wait(TICK_SEC) if stop is not None else time.sleep(TICK_SEC))


# -- CLI ---------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run a single tick and exit")
    ap.add_argument("--uid", default=None, help="publish to users/{uid}/meta/qqq_exec")
    ap.add_argument("--fills", default=DEFAULT_FILLS)
    ap.add_argument("--cred", default=None, help="Firestore service-account json "
                                                  "(needed with --uid)")
    a = ap.parse_args()
    if not a.once:
        ap.print_help()
        return
    db = None
    if a.uid:
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            if not firebase_admin._apps:
                cred = credentials.Certificate(a.cred) if a.cred else credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred)
            db = firestore.client()
        except Exception as e:
            print(f"[qqq-exec] Firestore unavailable ({type(e).__name__}: {e}) -- "
                 f"running --once without publish")
    run_once(uid=a.uid, fills_path=a.fills, db=db)


if __name__ == "__main__":
    main()
