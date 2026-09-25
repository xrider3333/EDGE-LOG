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
import math
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
from . import trade_id as _trade_id
from . import webull_orders

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover -- zoneinfo ships with 3.9+, this repo runs 3.13
    _NY = None


# -- EDGELOG_HOME (2026-09-13, "fill-in-the-blanks Oracle Cloud move") ------------------
# Every path below used to be a bare C:\EdgeLog\... literal. EDGELOG_HOME is the one base
# directory a Linux VM sets differently; every specific-path env var below still overrides
# its own default individually, exactly as before -- this only changes what the DEFAULT is
# when none of those are set. On Windows with EDGELOG_HOME unset, every path is
# byte-identical to the old hardcoded literal (os.path.join with "C:\\EdgeLog" reproduces
# the same backslashed string).
def _default_edgelog_home():
    return r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog"


EDGELOG_HOME = os.environ.get("EDGELOG_HOME") or _default_edgelog_home()

# -- paths -----------------------------------------------------------------------
OUT_DIR = os.environ.get("EDGELOG_QQQ_EXEC_DIR", os.path.join(EDGELOG_HOME, "qqq_exec"))
CONFIG_PATH = os.path.join(OUT_DIR, "config.json")
STATE_PATH = os.path.join(OUT_DIR, "state.json")
ORDERS_CSV = os.path.join(OUT_DIR, "orders.csv")
TRADES_CSV = os.path.join(OUT_DIR, "trades.csv")
# BROKER MIRROR (2026-09-13): a SEPARATE file, never new columns on orders.csv/trades.csv
# above -- those are read by existing consumers (the web tab, backfill/reprice scripts)
# that depend on the header staying exactly what it is today. See _mirror_to_broker.
BROKER_ORDERS_CSV = os.path.join(OUT_DIR, "broker_orders.csv")
DEFAULT_FILLS = nt_sync.DEFAULT_FILLS
NQ_10S_PRIMARY = os.environ.get("EDGELOG_NQ_10S_PRIMARY",
                                os.path.join(EDGELOG_HOME, "ohlc_addon", "NQ_10s.csv"))
NQ_10S_FALLBACK = os.environ.get("EDGELOG_NQ_10S_FALLBACK",
                                 os.path.join(EDGELOG_HOME, "ohlc", "NQ_10s.csv"))
WEBULL_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", os.path.join(EDGELOG_HOME, "webull_keys.json"))
_WEBULL_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR", os.path.join(EDGELOG_HOME, "webull_token"))
# The symbol this module's shadow lots (and now the broker mirror) always trade.
BROKER_SYMBOL = "QQQ"

LEGS = ("ORB", "ENGUQ", "NOISE")
# ENGINE MODE (2026-09-13): maps api/cloud_signal.py's own CROWN_LEGS keys onto this
# module's short leg keys. Kept explicit (not derived) so a cloud_signal rename never
# silently breaks this mapping -- update BOTH sides in the same commit. See
# api/cloud_signal.py's "THE THREE CROWN LEGS" docstring for the current crown/run per key.
#
# TWO KEYS CAN MAP TO ONE EXEC LEG (2026-09-24, the NOISE #304 -> #382 swap): NOISE_304 is
# GONE from cloud_signal.CROWN_LEGS (replaced, not kept alongside -- see that module), but
# it is kept HERE, still pointing at "NOISE", purely so an EXIT row cloud_signal already
# wrote under the old key, or a trade id already embedded in an open lot/broker order,
# keeps resolving after the swap. NOISE_382 is the live key. Everything downstream of this
# map (state["legs"][leg], cfg["shares"][leg], the resend queue, deferred fill capture,
# book-only -- see _open_lot's own SIZE ORDERS comment) keys on the EXEC leg ("NOISE")
# string, never on the engine key, so both mapped keys already carry straight through
# there with NO further change. The two spots that go the OTHER way -- EXEC leg back to
# an engine key, to consult cloud_signal.CROWN_LEGS or filter its signals.csv by leg --
# are _engine_mark_price and _engine_confirms_entry below; see _engine_key_for_leg's own
# docstring for why a naive "first mapped key" reverse lookup is not safe once two engine
# keys share one EXEC leg.
ENGINE_LEG_MAP = {"ORB_R6": "ORB", "ENGUQ_335": "ENGUQ", "NOISE_382": "NOISE", "NOISE_304": "NOISE"}
ENGINE_HEARTBEAT_STALE_SEC = 90.0     # mirrors FEED_STALE_SEC's role, for cloud_signal's own heartbeat
ENGINE_CONSUME_STALE_SEC = 30 * 60.0  # this adapter was down too long to act on a queued signal
ENGINE_SHORT_READ_TICKS = 3           # consecutive short ledger reads before accepting a replaced file
FLATTEN_MAX_TRIES = 3                 # orphan-repair attempts per leg per day (_maybe_flatten_orphan_broker)
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
    "kill_file": os.path.join(OUT_DIR, "KILL"),
    # NOTE: "flatten_broker_file" is deliberately NOT defaulted here. load_config deep-
    # copies this dict, so any path baked in at import time would survive a test's
    # monkeypatch of OUT_DIR and point tick() at the REAL C:\EdgeLog trigger -- which
    # tests/test_live_system_guard.py caught doing an os.rename on the live file. The
    # path is resolved against the CURRENT OUT_DIR inside _maybe_flatten_orphan_broker;
    # set the key by hand in config.json only to override it.
    "slippage_per_share": 0.01,
    # NT SIZING GAP (feature #50): "fixed" (default, unchanged behaviour) uses the
    # `shares` table above verbatim. "nt_notional" instead sizes each lot off the $
    # notional of the NT futures fill it mirrors: shares = round(nt_notional_usd *
    # size_fraction / qqq_px), still clamped to max_shares_per_leg.
    "size_mode": "fixed",
    "size_fraction": 0.01,
    # SIGNAL SOURCE (2026-09-13, "move QQQ shadow off NinjaTrader"): "engine" (new
    # default) takes entries/exits from api/cloud_signal.py's own QQQ-bar signal engine
    # -- no NinjaTrader file, no NQ ratio, ever. "ninjatrader" is the old mirror
    # (fills.csv + NQ ratio/Webull-quote pricing), kept only as a fallback. See
    # api/cloud_signal.py and the ENGINE MODE section of this module's docstring.
    "signal_source": "engine",
    # STARTUP GUARD (ninjatrader mode only): a NinjaTrader strategy re-enable/relaunch
    # can fire a startup entry that matches no real engine signal (observed
    # 2026-09-03, two such entries at 12:30). Fills within this many minutes of a
    # relaunch that the engine does not confirm are ignored (marked STARTUP-SUSPECT in
    # orders.csv, never silently dropped) -- see _relaunch_recently/_engine_confirms_entry.
    "startup_guard_minutes": 5,
    # FIRESTORE THROTTLE (2026-09-14, FIX 1 -- see _publish_fingerprint/_should_publish):
    # the FULL doc is published immediately on a meaningful change, otherwise at most
    # once per interval. Two DIFFERENT regimes, chosen by whether the broker is armed:
    # while OFF (no send-gate risk, see _should_publish), shorter during the trading
    # session, much longer outside it; once PAPER/LIVE, publish_interval_armed_sec
    # applies instead of BOTH of those, because every publish also renews this
    # process's cross-host lease and a real broker send self-blocks once that renewal
    # goes stale beyond LEASE_SEND_MAX_AGE_SEC (30s) -- see _should_publish's docstring.
    "publish_interval_session_sec": 60,
    "publish_interval_offhours_sec": 600,
    "publish_interval_armed_sec": 20,
    # LEASE VERIFY CACHE (2026-09-14): _check_lease_for_broker's Firestore READ is
    # cached for this many seconds instead of being re-read every 5s tick.
    "lease_verify_interval_sec": 30,
    # BROKER RECONCILE (2026-09-14, FIX 2 -- see _maybe_run_broker_reconcile): how
    # often, at most, the periodic (non-event-triggered) reconcile runs while the
    # tick loop is in its active market window. Always ALSO runs at boot and right
    # after any broker order this tick attempted to send, regardless of this value.
    "broker_reconcile_interval_min": 5,
    # LIVE WEBULL STREAM (2026-09-23, item 3): owner-editable kill switch for the
    # background WebullBarStreamer qqq_exec_thread starts once SERVING -- see
    # _start_qqq_stream. False falls back to bar-close pricing everywhere (exactly
    # like a failed/never-attempted connect), never a crash.
    "live_stream_enabled": True,
}


def _cfg_num(cfg, key, default):
    """float(cfg[key]) with a safe fallback to `default` -- every throttle/interval
    knob added 2026-09-14 is owner-editable in config.json but must never be able to
    crash a tick over a typo (a string, a blank, a negative)."""
    try:
        v = float((cfg or {}).get(key, default))
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default

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

# FIRESTORE WRITE/READ THROTTLE (2026-09-14, FIX 1). Module-level defaults for every
# cfg override above (_cfg_num reads cfg first, falls back to these) -- kept as real
# constants (not just dict literals) so tests and tools can reference them by name,
# same convention as LEASE_STALE_SEC below.
PUBLISH_INTERVAL_SESSION_SEC = 60.0
PUBLISH_INTERVAL_OFFHOURS_SEC = 600.0
# Applies instead of the two above once the broker is armed (PAPER/LIVE) -- see
# _should_publish's docstring: every publish also renews this process's cross-host
# lease (aaca82b's _LeaseHolder), and a real order self-blocks once that renewal is
# older than LEASE_SEND_MAX_AGE_SEC (30s), so this must stay safely under that.
PUBLISH_INTERVAL_ARMED_SEC = 20.0
# LIVE POSITIONS (2026-09-23, item 3's Firestore-quota rule): "live marks may republish
# at most every 10s, only during market hours and only while a position is open" -- a
# CEILING on how often the open-leg live price/P&L marks refresh, applied ONLY in that
# narrow window (session hours + an open position) since positions_live/equity are
# deliberately excluded from _publish_fingerprint (see that function's own docstring on
# why per-tick price noise must never itself force a publish) -- without a tightened
# heartbeat here they would otherwise sit as stale as the OTHER applicable interval
# (up to 600s off-session, or 20s once armed) between meaningful events. See
# _should_publish's own docstring for the worst-case publish count this adds.
PUBLISH_INTERVAL_POSITION_OPEN_SEC = 10.0
LEASE_VERIFY_INTERVAL_SEC = 30.0
# Hourly Firestore usage line (writes/reads this adapter issued) -- see
# _track_fs_write/_track_fs_read/_maybe_log_fs_usage.
FS_USAGE_LOG_INTERVAL_SEC = 60 * 60.0
# BROKER RECONCILE (FIX 2). RECONCILE_HARD_TIMEOUT_SEC bounds the ENTIRE
# adapter.reconcile() call to a wall-clock limit on its own worker thread -- same
# precaution as QUOTE_HARD_TIMEOUT_SEC above for Webull quote calls (2026-09-03
# postmortem: this SDK's own connect/read timeouts are not reliably honoured on every
# call path; the runner's shadow thread once hung 10 hours inside get_snapshot).
RECONCILE_HARD_TIMEOUT_SEC = 12.0
BROKER_RECONCILE_INTERVAL_MIN = 5.0
# POST-ORDER GRACE (2026-09-21, owner: "wait 30 seconds and look again before panicking").
# Webull paper's POSITIONS lag a FILL by more than one 5 s tick, so a reconcile on the
# next tick read the pre-fill position and HALTED new entries on every leg until the
# 5-minute periodic check cleared it -- twice on 2026-09-21 (broker 20 vs sent 10 at
# 09:31, broker 10 vs sent 0 at 09:42), both false. See _maybe_run_broker_reconcile.
BROKER_RECONCILE_POST_ORDER_GRACE_SEC = 30.0
# HALTED RE-CHECK + RE-SEND (2026-09-21, NOISE's buy never reached Webull). While this
# adapter's own reconcile halt is on, look again every 30 s instead of every 5 min, and
# once it clears re-send the OPEN it blocked (see _maybe_resend_broker_orders). The same
# queue re-sends an order Webull rejected as a same-instant DUPLICATE of another leg's.
BROKER_RECONCILE_HALTED_RECHECK_SEC = 30.0
BROKER_OPEN_RESEND_WINDOW_MIN = 10.0    # an OPEN later than this after its first try is dropped
BROKER_RESEND_MAX_TRIES = 3             # re-sends per order, each under a fresh client_order_id
BROKER_RESEND_MIN_GAP_SEC = 4.0         # never in the tick right after the failure


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


# Item B (2026-09-25): the live Webull stream's own, NARROWER window -- see
# _stream_should_run. Not the same constants as _in_market_window above (that one is
# broader on purpose, for flatten/breaker/heartbeat logic unrelated to the stream).
_STREAM_WINDOW_OPEN = (9, 29)
_STREAM_WINDOW_CLOSE = (16, 2)
_STREAM_HALF_DAY_CLOSE = (13, 2)


def _stream_should_run(now_et):
    """Pure decision (item B, 2026-09-25): should the live Webull MQTT stream
    (api/webull_stream.py's WebullBarStreamer) be running at this US/Eastern instant?

    Before this, the stream started once when the process entered SERVING and ran all
    night regardless -- root cause of the overnight SDK log flood (see
    api/webull_stream.py's item A docstring: the stream stayed connected while the
    venue was closed, so our own watchdog kept reconnecting against a server that
    replies "Protocol not supported" after hours). Now it only runs on a trading day,
    09:29-16:02 ET -- one minute before the 09:30 entry window opens (so the very
    first bar builds cleanly from the first tick) to two minutes past the 16:00 close
    (for a final flush) -- narrowed to 13:02 ET on a recognised half day
    (market_calendar.session_close_et != '16:00'; the OPEN side never moves).

    Trading-day-ness is market_calendar.is_session (weekday AND not a NYSE/Nasdaq
    holiday) -- the same calendar tick()'s own holiday short-circuit and half-day
    flat_by clamp already use, just consulted here for a narrower purpose. Tuple-based
    time comparison mirrors _in_market_window's own (h, m) <= (h, m) style."""
    if not market_calendar.is_session(now_et):
        return False
    close = (_STREAM_HALF_DAY_CLOSE if market_calendar.session_close_et(now_et) != "16:00"
             else _STREAM_WINDOW_CLOSE)
    return _STREAM_WINDOW_OPEN <= _et_hhmm(now_et) <= close


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
    src = str(merged.get("signal_source") or "").strip().lower()
    if src not in ("engine", "ninjatrader"):
        log(f"[qqq-exec] invalid signal_source={merged.get('signal_source')!r} -- "
            f"defaulting to 'engine'")
        src = "engine"
    merged["signal_source"] = src
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
        # FIRESTORE THROTTLE (2026-09-14, FIX 1): _check_lease_for_broker's own
        # Firestore READ is cached here instead of re-read every 5s tick -- see
        # _lease_verify_cached.
        "_lease_verify_at": 0.0,
        "_lease_verify_ok": True,
        "_lease_verify_reason": None,
        # FIRESTORE USAGE COUNTERS (2026-09-14): logged once/hour, see
        # _maybe_log_fs_usage. "_today"/"_day" reset at the ET day boundary exactly
        # like publish_fail_today above; "_hour" resets every FS_USAGE_LOG_INTERVAL_SEC.
        "_fs_writes_today": 0, "_fs_reads_today": 0, "_fs_usage_day": None,
        "_fs_writes_hour": 0, "_fs_reads_hour": 0, "_fs_usage_hour_at": None,
        # BROKER RECONCILE (2026-09-14, FIX 2): _reconcile_due is set True the moment
        # any broker order this tick attempted to send (PAPER/LIVE) -- see
        # _mirror_to_broker -- so the NEXT tick runs reconcile immediately rather than
        # waiting for the periodic interval. _last_broker_reconcile_at tracks that
        # periodic cadence, see _maybe_run_broker_reconcile.
        "_reconcile_due": False,
        "_last_broker_reconcile_at": 0.0,
        # BROKER DAILY P&L WIRING (2026-09-14): feeds webull_orders.OrderAdapter's own
        # (previously dead) update_daily_pnl() -- see _sync_broker_daily_pnl.
        "_broker_pnl_day": None,
        "_broker_pnl_tracked": 0.0,
        "_broker_pnl_source": None,
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


def _replace_with_retry(tmp, dst, log=None, what=None, retries=12, sleep=0.05,
                        keep_tmp_on_failure=False):
    """os.replace(tmp, dst), retrying briefly on Windows' transient PermissionError
    [WinError 32]: `os.replace` fails outright there if ANY OTHER PROCESS merely has
    `dst` open, even just for reading (POSIX would simply rename under the reader).

    THE ONE retry-replace helper for every risky rename in THIS module -- the same
    shared-helper convention tools/qqq_paper.py and api/cloud_signal.py already use
    for the QQQ bar caches (that module's own `_replace_with_retry`, pinned by
    tests/test_qqq_cache_atomic.py: "neither writer may grow its OWN retry loop").
    save_state and _update_broker_order_row both call THIS one instead of each
    growing their own -- see save_state's docstring for the incident (100,570 dropped
    state writes) that made the first version of this necessary, and
    _update_broker_order_row's for why a plain `open(path, "w")` over a live CSV is
    exactly the failure class that once garbled the QQQ bar cache and blocked every
    push gate.

    `keep_tmp_on_failure` differs per caller ON PURPOSE: save_state passes True --
    state.json is the SOLE record of open positions, so losing the write silently is
    worse than leaving a recoverable `.tmp` copy on disk for a human to rename by
    hand. _update_broker_order_row passes False -- that rewrite is safely re-derivable
    (the fill-capture job that produced it just tries again later), so an abandoned
    `.tmp` beside the live ledger forever would be pure clutter, never a rescue.

    NEVER RAISES. Returns True once `os.replace` actually lands, False after
    exhausting `retries` or hitting a non-retryable OSError -- `dst` is UNTOUCHED on a
    False return, exactly as it was before this call (os.replace either fully
    replaces the destination or does not touch it at all -- there is no partial
    state), and a persistent failure is logged at most ONCE, never once per retry."""
    last = None
    for i in range(retries):
        try:
            os.replace(tmp, dst)
            return True
        except PermissionError as e:          # WinError 32: someone has it open
            last = e
            time.sleep(sleep * (i + 1))
        except OSError as e:
            last = e
            break
    if not keep_tmp_on_failure:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if log:
        label = what or os.path.basename(dst)
        if keep_tmp_on_failure:
            log(f"[qqq-exec] {label} could not swap into place after {retries} tries "
                f"({last}); the new content is kept at {tmp} -- rename it over {dst} "
                f"once whatever holds it lets go.")
        else:
            log(f"[qqq-exec] {label} replace failed after {retries} attempt(s), "
                f"giving up: {type(last).__name__}: {last}")
    return False


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

    So: a unique temp name per writer, fsync before the swap, and retry the swap
    (_replace_with_retry, SHARED -- see its own docstring) for about a second, because
    a reader lock lasts milliseconds. If it still cannot swap, the temp file is LEFT ON
    DISK rather than deleted -- losing the write silently is worse than leaving a
    recoverable copy -- and the caller is told.
    """
    path = path if path is not None else STATE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), int(time.time() * 1000) % 100000)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    return _replace_with_retry(tmp, path, log=log, what="state write",
                               retries=_retries, sleep=_sleep, keep_tmp_on_failure=True)


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
              "px_source", "reason", "latency_s",
              # appended, never inserted (existing readers/consumers index by position
              # via csv.DictReader's header, which stays stable) -- "engine" or
              # "ninjatrader", see DEFAULT_CONFIG["signal_source"].
              "signal_source",
              # SIZE ORDERS (2026-09-23): appended, never inserted -- same backward-
              # compat convention as signal_source above ("" on every row written
              # before this shipped). "size" is the resolved per-trade multiplier
              # (_resolve_entry_size -- 1.0 for a leg/mode that does not size); "shares"
              # (existing column, above) is what was actually SENT after the
              # max_shares_per_leg clamp, "shares_wanted" is what sizing asked for
              # before that clamp -- equal to "shares" whenever the rail did not bite.
              # See _open_lot's SIZED branch for when they diverge.
              "size", "shares_wanted",
              # AFTER-CLOSE LATENCY (2026-09-23, "HONEST WARNINGS" item 1b): appended,
              # never inserted -- same backward-compat convention as every column
              # above ("" on every row written before this shipped, and on every
              # ninjatrader-mode row, which has no bar to measure against). See
              # _record_order's own docstring for what this measures and why
              # latency_s alone reads engine-mode orders as ~5x too slow.
              "after_close_s"]
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
TRADE_COLS = (["leg", "entry_ts", "exit_ts", "side", "shares", "entry_px", "exit_px",
              "pnl", "nq_pnl_points", "exit_reason"] + NT_PARITY_COLS + SIZING_COLS
              # appended, never inserted -- see ORDER_COLS's signal_source note.
              + ["signal_source"]
              # ENGINE-VS-BROKER PARITY (feature #56, 2026-09-22): the lot's own trade
              # id (api/trade_id.py), so _broker_trade_parity can re-derive the EXACT
              # client_order_id _broker_signal_id gave this trade's OPEN/CLOSE and look
              # them up in broker_orders.csv -- a trades.csv row closed before this
              # shipped reads back "", which _broker_trade_parity treats as "not
              # checked" (never an error, see its own docstring).
              + ["trade_id"]
              # SIZE ORDERS (2026-09-23): appended, never inserted -- see ORDER_COLS'
              # own size/shares_wanted comment; same meaning here, captured on the lot
              # at open (_open_lot) and carried onto the closed-trade row unchanged --
              # a CLOSE never re-sizes (see _reduce_lot).
              + ["size", "shares_wanted"]
              # KEEL OVERLAY (2026-09-23): appended, never inserted -- the KEEL
              # multiplier ALONE that "size" above already includes (size =
              # plugin_size * keel_size for a keel-scored entry -- see
              # api/cloud_signal.py's SIGNAL_COLS "keel_size" comment). "" for a lot
              # with no keel_size on its ENTRY signal -- no overlay on that leg, or a
              # trade opened before this column existed -- never a guess. The web tab's
              # trade drawer uses this to show the plugin_size x keel_size breakdown.
              + ["keel_size"])


def _record_order(leg, action, side, shares, nq_px, qqq_px, px_source, reason, log=print,
                  fill_dt=None, signal_source=None, size=None, shares_wanted=None):
    """`fill_dt` (feature #51 LATENCY): the ET timestamp of the NT fill this order
    mirrors, when one exists -- absent for rail-driven closes (BREAKER/EOD/KILL flatten
    has no single triggering fill). latency_s = now (adapter order time) - fill_dt.

    `size`/`shares_wanted` (2026-09-23): default to 1.0 / `shares` when the caller
    does not pass them -- every call site that predates sizing (ninjatrader-mode
    entries, rail-driven closes, the REFUSED/blocked logs) gets exactly the values it
    always implied (unsized, wanted == sent), so their rows are unchanged in meaning
    even though the CSV header now carries two more columns.

    AFTER-CLOSE LATENCY (2026-09-23, "HONEST WARNINGS" item 1b). In engine mode,
    `fill_dt` is the SIGNAL BAR'S OWN START stamp (_route_engine_events passes
    `sig_dt` = the ENTRY/EXIT row's `ref_time`, see that function and _open_lot/
    _reduce_lot) -- not a real fill time the way ninjatrader mode's is. So latency_s
    there is "now minus when the bar OPENED", which reads a perfectly-timed order on
    every 5-minute bar as ~300s+ "late" and every 1-minute ENGUQ bar as ~60s+ "late"
    -- not a reaction-time measurement at all. after_close_s is the real one: now
    minus when that bar actually CLOSED (start + this leg's own timeframe, read from
    api.cloud_signal.CROWN_LEGS via ENGINE_LEG_MAP -- never hard-coded, so a future
    leg swapped onto a different timeframe is picked up automatically). Left blank
    ("") for ninjatrader-mode rows (fill_dt there already IS a real fill time --
    latency_s already answers this question for them) and for any row with no
    resolvable leg timeframe."""
    latency_s = None
    if fill_dt is not None:
        try:
            latency_s = round((_now_et() - fill_dt).total_seconds(), 3)
        except Exception as e:
            log(f"[qqq-exec] latency calc failed: {type(e).__name__}: {e}")
    after_close_s = None
    if (fill_dt is not None and latency_s is not None
            and str(signal_source or "").strip().lower() == "engine"):
        tf_sec = _leg_timeframe_seconds(leg, log=log)
        if tf_sec is not None:
            after_close_s = round(latency_s - tf_sec, 3)
    row = {"ts_et": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "leg": leg, "action": action,
           "side": side, "shares": shares,
           "nq_px": round(nq_px, 4) if nq_px is not None else "",
           "qqq_px": round(qqq_px, 4) if qqq_px is not None else "",
           "px_source": px_source or "", "reason": reason or "",
           "latency_s": latency_s if latency_s is not None else "",
           "signal_source": signal_source or "",
           "size": size if size is not None else 1.0,
           "shares_wanted": shares_wanted if shares_wanted is not None else shares,
           "after_close_s": after_close_s if after_close_s is not None else ""}
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
    row["signal_source"] = lot.get("signal_source") or ""
    # ENGINE-VS-BROKER PARITY (feature #56): see TRADE_COLS -- the join key
    # _broker_trade_parity uses to find this trade's broker_orders.csv rows.
    row["trade_id"] = lot.get("trade_id") or ""
    # SIZE ORDERS (2026-09-23): captured on the lot at open -- a lot opened before this
    # feature shipped (an in-flight position carried across the upgrade) has neither
    # key, so it publishes as wanted == sent (shares_total, the only quantity such a
    # lot ever had) and size 1.0, never a blank -- there is no "wanted vs sent" story
    # to tell for a lot this code never sized, so the honest default is "no clamp".
    row["size"] = lot.get("size") if lot.get("size") is not None else 1.0
    row["shares_wanted"] = (lot.get("shares_wanted") if lot.get("shares_wanted") is not None
                            else lot["shares_total"])
    # KEEL OVERLAY (2026-09-23): "" (never a guessed number) for a lot with no
    # keel_size -- no overlay on that leg, or a lot opened before this column existed.
    row["keel_size"] = lot.get("keel_size") if lot.get("keel_size") is not None else ""
    _append_csv(TRADES_CSV, TRADE_COLS, row, TRADES_KEEP)
    return pnl


# -- broker mirror (2026-09-13, "flip Webull paper orders on with a one-line config
# change") -------------------------------------------------------------------------------
# Every shadow OPEN/CLOSE below also hands the same intent to api.webull_orders, in
# whatever mode ITS OWN config file says (default OFF -- see that module's docstring).
# The shadow book stays the source of truth for the simulated record: _open_lot/
# _reduce_lot already recorded their shadow order/trade rows BEFORE calling
# _mirror_to_broker, and a broker rejection/exception here is caught, logged, and folded
# into the doc's "broker" status block -- it never unwinds or blocks the shadow trade.
BROKER_ORDER_COLS = ["ts_et", "leg", "intent", "side", "shares", "signal_id",
                     "client_order_id", "mode", "ok", "sent", "shadow_px",
                     "broker_fill_px", "slippage", "reason", "duplicate",
                     # CROSS-HOST LEASE (2026-09-14): appended, never inserted -- same
                     # backward-compat convention as ORDER_COLS/TRADE_COLS' trailing
                     # signal_source column (_migrate_csv_header rewrites the on-disk
                     # header and pads old rows with ""). Which host actually sent (or
                     # was blocked from sending) this row -- see _lease_host_id and the
                     # lease-unverifiable gate in _mirror_to_broker.
                     "host_id"]

_ORDER_ADAPTER = None


def _get_broker_adapter(log=print):
    """One OrderAdapter per process (it owns its own on-disk state file, reloaded once
    at construction) -- module-level so every OPEN/CLOSE in this process shares the same
    idempotency/rails/reconcile state. Tests should monkeypatch this function directly
    rather than relying on the singleton."""
    global _ORDER_ADAPTER
    if _ORDER_ADAPTER is None:
        _ORDER_ADAPTER = webull_orders.OrderAdapter(log=log)
    return _ORDER_ADAPTER


# -- LIVE WEBULL STREAM (2026-09-23, "LIVE POSITIONS + ACCOUNT EQUITY", item 3) ---------
# The owner: "since we are live with live pricing, can you show the positions live? and
# potentially equity as well." api.webull_stream.WebullBarStreamer already exists (a
# Level-1 MQTT stream -> live trade/bar reader) but nothing runs it -- this wires ONE
# instance in, on its own guarded background thread, only while THIS process is actually
# SERVING (see qqq_exec_thread): the standby host must never hold a second live session
# on the same Webull key, which can kick the serving host's own connection.
_QQQ_STREAM_SYMBOL = "QQQ"
_qqq_stream_lock = threading.Lock()
_qqq_stream_state = {"streamer": None, "starting": False, "stop_requested": False}


def _webull_stream_factory():
    """Returns the WebullBarStreamer CLASS this module should instantiate -- indirected
    through a function, never imported and constructed directly at the call site,
    purely so tests can swap in a fake that touches neither a thread nor the network
    (see tests/conftest.py's autouse _isolate_qqq_stream, which does exactly that for
    every test in this repo -- belt-and-suspenders alongside that fixture, never a
    substitute for it). Production always returns the real class. Lazy import so a
    broken/missing api.webull_stream can never break THIS module's own import."""
    from . import webull_stream
    return webull_stream.WebullBarStreamer


def _qqq_stream_instance():
    """The currently-running streamer, or None if one was never started (a standby
    host, an unmanaged/offline caller, --once, a start still connecting, or one that
    failed) -- every reader (_live_price_for_leg, _build_price_status) already treats
    None as 'no live price yet, fall back to the bar cache'."""
    with _qqq_stream_lock:
        return _qqq_stream_state.get("streamer")


def _start_qqq_stream(cfg, log=print):
    """Best-effort: start WebullBarStreamer for QQQ on its OWN daemon thread. Called
    once this process has actually entered SERVING (holds the host slot and, cross-
    host, the lease) -- never call this from a process that only MIGHT end up serving.
    `cfg["live_stream_enabled"]` (default True) is an owner-editable kill switch,
    checked once here, each call.

    NEVER BLOCKS OR CRASHES THE TICK LOOP: construction and .start() (which itself
    blocks up to ~20s connecting -- see WebullBarStreamer._connect_once) run on a NEW
    daemon thread, never the caller's, so even a slow/hanging connect only delays this
    helper's OWN background thread. Every exception (missing module, missing/bad keys,
    an SDK error, a raised PermissionError from a test's own network guard, ...) is
    caught here and logged -- the tick loop's own price/positions code already has the
    closed-bar fallback (_live_price_for_leg) regardless of whether this ever
    succeeds. Idempotent: a second call while a streamer is already starting/running
    is a no-op.

    THE STOP-WHILE-CONNECTING RACE: if _stop_qqq_stream runs while this thread is still
    inside .start() (this host lost the lease moments after claiming it), the streamer
    must never be published into _qqq_stream_state and left running -- `stop_requested`
    is re-checked right after .start() returns, and a torn-down streamer is stopped
    again immediately rather than handed to the rest of this process."""
    try:
        if not bool((cfg or {}).get("live_stream_enabled", True)):
            return
        with _qqq_stream_lock:
            if _qqq_stream_state.get("streamer") is not None or _qqq_stream_state.get("starting"):
                return
            _qqq_stream_state["starting"] = True
            _qqq_stream_state["stop_requested"] = False

        def _run():
            streamer = None
            try:
                cls = _webull_stream_factory()
                streamer = cls(symbols=[_QQQ_STREAM_SYMBOL], log=log)
                streamer.start()
                with _qqq_stream_lock:
                    stood_down = bool(_qqq_stream_state.get("stop_requested"))
                    if not stood_down:
                        _qqq_stream_state["streamer"] = streamer
                if stood_down:
                    streamer.stop()
                    log(f"[qqq-exec] Webull live stream connected but this host had "
                        f"already stood down -- stopped immediately")
                else:
                    log(f"[qqq-exec] Webull live stream started for {_QQQ_STREAM_SYMBOL}")
            except Exception as e:
                log(f"[qqq-exec] Webull live stream failed to start (non-fatal -- "
                    f"positions/price fall back to the bar cache): {type(e).__name__}: {e}")
            finally:
                with _qqq_stream_lock:
                    _qqq_stream_state["starting"] = False

        threading.Thread(target=_run, name="qqq-webull-stream", daemon=True).start()
    except Exception as e:
        log(f"[qqq-exec] could not launch the Webull live stream thread (non-fatal): "
            f"{type(e).__name__}: {e}")
        with _qqq_stream_lock:
            _qqq_stream_state["starting"] = False


def _stop_qqq_stream(log=print):
    """Best-effort teardown, called whenever this process is no longer serving (normal
    loop exit, mid-loop stand-down, an exception -- see qqq_exec_thread's `finally`, so
    this always runs) so the standby/former host never holds a second live session
    against the same Webull key. Safe to call even when nothing was ever started or one
    is still connecting (see _start_qqq_stream's stop-while-connecting handling).
    Never raises."""
    with _qqq_stream_lock:
        streamer = _qqq_stream_state.get("streamer")
        _qqq_stream_state["streamer"] = None
        _qqq_stream_state["stop_requested"] = True
    if streamer is not None:
        try:
            streamer.stop()
        except Exception as e:
            log(f"[qqq-exec] Webull live stream stop failed (non-fatal): {type(e).__name__}: {e}")


# Item B (2026-09-25): at most one START ATTEMPT per this many seconds -- see
# _qqq_stream_window_step's own docstring for why this gate exists.
_QQQ_STREAM_START_RETRY_SEC = 120.0


def _qqq_stream_window_step(cfg, last_start_attempt, now_et=None, now_wall=None, log=print):
    """Called once per tick from qqq_exec_thread's loop (item B, 2026-09-25): starts or
    stops the live Webull stream to keep it running only inside _stream_should_run's
    market-hours window, replacing the old behaviour of starting it once at boot and
    running it all night regardless (root cause of api/webull_stream.py's overnight
    SDK log flood -- see that module's item A docstring).

    RULES:
      - inside the window, no streamer running or starting -> _start_qqq_stream (still
        subject to cfg['live_stream_enabled'], the owner kill switch, enforced inside
        _start_qqq_stream itself -- unchanged by this function);
      - outside the window, a streamer running -> _stop_qqq_stream, logged once here
        (unlike the routine per-tick case, this is a state change worth a line);
      - outside the window, NO streamer running -> do nothing, log nothing -- calling
        _stop_qqq_stream every tick all night (it's a safe no-op, but a noisy one)
        would just reintroduce a smaller version of the exact log-spam problem item A
        fixes.

    RETRY SPACING: _start_qqq_stream is already idempotent while a streamer is running
    or mid-connect ('starting'), but a FAILED start (bad keys, an SDK import error, a
    raised exception anywhere in connect/subscribe) clears 'starting' immediately --
    see its own docstring -- so calling this every TICK_SEC (5s) with no gate would
    retry a hard failure 12 times a minute all day. Only attempt a (re)start at most
    once every _QQQ_STREAM_START_RETRY_SEC; `last_start_attempt` (0.0 the first time a
    caller has never attempted one) is the caller's own fold/accumulator, returned
    here rather than stored on _qqq_stream_state, since it's a per-loop retry timer,
    not shared streamer state -- a process restart naturally re-arms it, which is
    fine. `_stop_qqq_stream` sets stop_requested=True, but `_start_qqq_stream` resets
    it on every call (see that function), so a later window's start always works
    again after an earlier window's stop.

    `now_et`/`now_wall` are both injectable (default to the real ET wall clock /
    time.time()) purely so this can be unit-tested deterministically regardless of
    when the test actually runs. Never raises -- any failure here must not take down
    qqq_exec_thread's own tick loop, exactly like every other best-effort helper it
    calls."""
    try:
        now_et = now_et if now_et is not None else _now_et()
        now_wall = now_wall if now_wall is not None else time.time()
        should_run = _stream_should_run(now_et)
        streamer = _qqq_stream_instance()
        with _qqq_stream_lock:
            starting = bool(_qqq_stream_state.get("starting"))
        if should_run:
            if (streamer is None and not starting
                    and (now_wall - last_start_attempt) >= _QQQ_STREAM_START_RETRY_SEC):
                last_start_attempt = now_wall
                _start_qqq_stream(cfg, log=log)
        elif streamer is not None:
            log(f"[qqq-exec] {now_et.strftime('%H:%M')} ET is outside the live-stream "
                f"window -- stopping the Webull stream")
            _stop_qqq_stream(log=log)
    except Exception as e:
        log(f"[qqq-exec] stream window step failed (non-fatal): {type(e).__name__}: {e}")
    return last_start_attempt


def _live_price_for_leg(leg, log=print):
    """(price, age_seconds, source) for the POSITIONS-LIVE card. 'source' is 'stream'
    (api.webull_stream's own live tick, only when its health().fresh is True) or 'bar'
    (the newest CLOSED engine bar -- _engine_mark_price, exactly what already marks
    unrealized P&L / the daily-loss breaker). (None, None, None) if neither is
    available yet. Never raises.

    ONE STREAM FOR THREE LEGS: the live tick is QQQ-wide (one Webull symbol), not
    per-leg, so every open leg reads the SAME price -- 'source'/'age' still travel
    per-leg on the published doc so a caller reading one leg's card never has to
    cross-reference a separate top-level field to know how fresh ITS OWN price is."""
    streamer = _qqq_stream_instance()
    if streamer is not None:
        try:
            if streamer.is_fresh():
                t = streamer.last_trade()
                if t and t.get("price") is not None:
                    return float(t["price"]), float(t.get("age") or 0.0), "stream"
        except Exception as e:
            log(f"[qqq-exec] live stream read failed for {leg} (falling back to the bar "
                f"cache): {type(e).__name__}: {e}")
    px, _src = _engine_mark_price(leg, log=log)
    if px is None:
        return None, None, None
    age = _leg_timeframe_bar_close_age(leg, log=log)
    return float(px), age, "bar"


def _leg_timeframe_bar_close_age(leg, log=print):
    """Seconds since the newest CLOSED bar backing this leg's engine price actually
    closed -- the SAME fix as _build_price_status/_bar_close_age (item 1c), applied
    per-leg for the positions-live card's 'bar' fallback age. None if unavailable."""
    try:
        cs = _cs_module()
        cs_key = _engine_key_for_leg(leg, cs)
        cfg_leg = cs.CROWN_LEGS.get(cs_key) if cs_key else None
        if not cfg_leg:
            return None
        return _bar_close_age(cfg_leg["timeframe"], log=log)
    except Exception as e:
        log(f"[qqq-exec] bar close age lookup failed for {leg}: {type(e).__name__}: {e}")
        return None


def _build_positions_live(state, cfg, log=print):
    """Per-open-leg LIVE read for the web tab's 'POSITIONS - LIVE' card: leg, side,
    shares, entry price, a LIVE price (+ its own age/source), this leg's own open P&L
    off THAT live price, and time in trade -- plus the book's total open P&L and a
    broker-vs-book net-QQQ cross-check. Never raises; a flat book returns an empty
    'legs' list and the tab shows 'flat'.

    DELIBERATELY A SEPARATE NUMBER FROM state['_unrl_by_leg'] (2026-09-23): that field
    is the bar-close mark _mark_and_check_breaker uses for the daily-loss RAIL -- a
    risk-critical figure this change does not touch, on this book's existing bar
    cadence, on purpose. This card's own open P&L is instead computed off the SAME live
    price shown right next to it (self-consistent for a reader looking at one card),
    which is why the two numbers can differ by a few cents intraday -- expected, not a
    bug, given they are honestly two different price sources.

    BROKER-VS-BOOK CROSS-CHECK: broker_sent_positions (api.webull_orders.OrderAdapter's
    own record of orders that actually reached Webull with a successful ack -- see that
    module's docstring, and its nothing-to-close guard, which is built on the exact
    same figure) is what the adapter BELIEVES is really at the broker; legs_net_qty is
    this shadow book's own tally, entirely independent of the broker adapter. The two
    should always agree while every OPEN/CLOSE has gone through cleanly -- 'mismatch'
    is the one-line amber check on the web tab ('Webull holds long 10 - legs sum to
    long 10')."""
    try:
        legs_out = []
        total_open_pnl = 0.0
        nowdt = _now_et()
        for leg, lot in (state.get("legs") or {}).items():
            side = lot.get("side")
            shares = lot.get("shares_remaining")
            entry_px = lot.get("entry_px")
            live_px, live_age, live_src = _live_price_for_leg(leg, log=log)
            open_pnl = None
            if live_px is not None and entry_px is not None and shares is not None:
                side_mult = 1 if side == "long" else -1
                open_pnl = round((live_px - entry_px) * side_mult * shares, 2)
                total_open_pnl += open_pnl
            time_in_trade_min = None
            try:
                entry_dt = datetime.strptime(lot["entry_ts"], "%Y-%m-%d %H:%M:%S")
                time_in_trade_min = round(
                    (nowdt.replace(tzinfo=None) - entry_dt).total_seconds() / 60.0, 1)
            except Exception:
                time_in_trade_min = None
            legs_out.append({
                "leg": leg, "side": side, "shares": shares, "entry_px": entry_px,
                "trade_id": lot.get("trade_id"),
                "live_px": live_px,
                "live_age_s": round(live_age, 1) if live_age is not None else None,
                "live_source": live_src,
                "open_pnl": open_pnl, "time_in_trade_min": time_in_trade_min,
            })
        legs_net = sum((lot.get("shares_remaining") or 0) * (1 if lot.get("side") == "long" else -1)
                       for lot in (state.get("legs") or {}).values())
        broker_net = None
        try:
            adapter = _get_broker_adapter(log=log)
            sent = adapter.status().get("broker_sent_positions") or {}
            broker_net = sum(float(p.get("qty", 0) or 0) for p in sent.values())
        except Exception as e:
            log(f"[qqq-exec] positions_live broker cross-check failed: {type(e).__name__}: {e}")
        mismatch = bool(broker_net is not None and abs(broker_net - legs_net) > 1e-9)
        return {"legs": legs_out, "total_open_pnl": round(total_open_pnl, 2) if legs_out else 0.0,
               "legs_net_qty": legs_net, "broker_net_qty": broker_net, "mismatch": mismatch}
    except Exception as e:
        log(f"[qqq-exec] positions_live build failed: {type(e).__name__}: {e}")
        return {"legs": [], "total_open_pnl": 0.0, "legs_net_qty": 0, "broker_net_qty": None,
               "mismatch": False}


# -- ACCOUNT EQUITY (2026-09-23, item 3) ------------------------------------------------
# Same account_v2.get_account_balance(account_id) call api/webull_sync.py's fetch_balance
# uses -- but for the ONE stock-purpose account this adapter itself trades through (the
# paper MARGIN account since 2026-09-23, DEFAULT_ACCOUNT_SELECT), not fetch_balance's own
# summed-across-every-stock-account figure (a different, broader read used by the
# journal's "Webull" pill). See api.webull_orders.OrderAdapter.get_stock_account_balance,
# the one new (read-only) method added there for this.
ACCOUNT_EQUITY_REFRESH_SEC = 60.0
_EQUITY_BOOT_READ_DONE = False   # set by the first _maybe_read_account_equity call of this process


def _maybe_read_account_equity(state, cfg, nowdt, log=print):
    """Refreshes state['equity'] at BOOT (the very first call this process ever makes,
    regardless of session) and about once a minute WHILE THE MARKET IS OPEN thereafter
    -- never more often, since each read is a real Webull HTTP round trip. A failed or
    skipped read leaves the PREVIOUS reading in place (see _build_equity_status, which
    is what actually decides 'stale' for the published doc off its own age). Never
    raises -- an equity probe must not be able to stop the tick loop.

    first_net_liq_today/day PERSIST ACROSS RESTARTS for free: state['equity'] rides
    inside the SAME state dict save_state()/load_state() round-trips as a whole (see
    e.g. the broker resend/fill-capture queues' own docstrings for this same
    convention) -- no extra plumbing needed."""
    try:
        global _EQUITY_BOOT_READ_DONE
        eq = state.setdefault("equity", {})
        last_epoch = eq.get("_epoch")
        # Every PROCESS reads once at boot, even off-hours: the persisted reading can be
        # hours old after a restart (2026-09-23 17:00 ET showed a 16:49 value as STALE).
        boot_read = not _EQUITY_BOOT_READ_DONE
        _EQUITY_BOOT_READ_DONE = True
        due = last_epoch is None or boot_read
        if not due:
            due = (time.time() - float(last_epoch)) >= ACCOUNT_EQUITY_REFRESH_SEC
        if not due:
            return
        if last_epoch is not None and not boot_read and not _in_market_window(nowdt):
            return   # already have at least one reading and the market is shut
        adapter = _get_broker_adapter(log=log)
        bal = adapter.get_stock_account_balance()
        eq["_epoch"] = time.time()
        if not bal or bal.get("net_liq") is None:
            return   # keep whatever was read before; _build_equity_status ages it out
        today = nowdt.strftime("%Y-%m-%d")
        if eq.get("day") != today or "first_net_liq_today" not in eq:
            eq["first_net_liq_today"] = bal["net_liq"]
            eq["day"] = today
        eq["net_liq"] = bal["net_liq"]
        eq["cash"] = bal.get("cash")
        eq["account_id"] = bal.get("account_id")
        eq["as_of_et"] = nowdt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        log(f"[qqq-exec] account equity read failed (non-fatal): {type(e).__name__}: {e}")


def _build_equity_status(state, nowdt, log=print):
    """{net_liq,cash,change_today,change_today_pct,as_of_et,age_min,stale,note} for the
    web tab's account-equity card. `stale` trips past 3 missed refreshes worth of age
    (a single skipped minute during a network blip should not paint the whole card
    broken) rather than exactly ACCOUNT_EQUITY_REFRESH_SEC. Never raises."""
    try:
        eq = state.get("equity") or {}
        net_liq = eq.get("net_liq")
        if net_liq is None:
            return {"net_liq": None, "cash": None, "change_today": None,
                   "change_today_pct": None, "as_of_et": None, "age_min": None,
                   "stale": True, "note": "account balance not read yet"}
        as_of = eq.get("as_of_et")
        age_min = None
        if as_of:
            try:
                age_min = round((nowdt.replace(tzinfo=None)
                                 - datetime.strptime(as_of, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60.0, 1)
            except Exception:
                age_min = None
        # Off-hours the balance is deliberately not re-read (it cannot move while the book
        # is flat), so an old reading then is expected, not a fault -- STALE only while the
        # market window is open and refreshes are actually due.
        stale = _in_market_window(nowdt) and (age_min is None
                                              or (age_min * 60.0) > (ACCOUNT_EQUITY_REFRESH_SEC * 3))
        first = eq.get("first_net_liq_today")
        change_today = round(net_liq - first, 2) if first is not None else None
        change_today_pct = (round((net_liq - first) / first * 100.0, 3)
                            if first else None)
        return {"net_liq": net_liq, "cash": eq.get("cash"), "change_today": change_today,
               "change_today_pct": change_today_pct, "as_of_et": as_of, "age_min": age_min,
               "stale": bool(stale),
               "note": ("last successful balance read is aging -- showing the most "
                        "recent value" if stale else None)}
    except Exception as e:
        log(f"[qqq-exec] equity status build failed: {type(e).__name__}: {e}")
        return {"net_liq": None, "cash": None, "change_today": None, "change_today_pct": None,
               "as_of_et": None, "age_min": None, "stale": True,
               "note": f"equity status unavailable: {type(e).__name__}"}


def _broker_side(side, intent):
    """This module's own vocabulary is side in {"long","short"}; the installed Webull
    SDK's OrderSide enum is BUY/SELL/SHORT only -- there is no COVER member -- so closing
    a short is sent as BUY, which nets against the existing short position. See
    api/webull_orders.py's module docstring, ORDER SIDE CAVEAT: unverified against a live
    sandbox fill since no paper credentials exist on this machine."""
    if str(intent).upper() == "OPEN":
        return "BUY" if side == "long" else "SHORT"
    return "SELL" if side == "long" else "BUY"


_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


def _broker_signal_id(leg, ts, intent, seq=0, trade_id=None):
    """The broker signal_id (-> webull_orders' client_order_id) for one lot's OPEN/CLOSE.

    FROM THE TRADE ID (2026-09-14): "qx" + the trade id with its separators removed + O/C,
    plus the reduce number only for a second or later reduce of one lot (ninjatrader-mode
    partial exits; engine mode is single-shot) -- e.g. trade NOISE_304-20260915T135500Z-L
    opens as qxNOISE30420260915T135500ZLO and closes as qxNOISE30420260915T135500ZLC.
    The trade id is the same on every host and in every process that sees the trade, so a
    restart, a second process or another host derives the SAME client_order_id for the same
    order -- the only way an order id can ever catch a duplicate. The old form was built
    from the lot's entry_ts, the LOCAL wall clock when this process opened it, so two hosts
    (tools/qqq_failover_sim.py scenario C) sent one trade under two different ids.

    COMPACT AND ALPHANUMERIC ON PURPOSE. Webull's US stock order reference documents
    client_order_id as "max 32 chars, must be unique per account", and its own sample
    generates uuid4().hex. Every current leg fits in 32 with letters and digits only (28
    characters for NOISE_304 / ENGUQ_335), so webull_orders._sanitize_client_order_id
    passes it through verbatim; a longer one becomes that function's stable hash, still the
    same on every host. Dropping "_" from a leg cannot merge two legs here (no two leg keys
    differ only by underscores), and the fixed-width UTC stamp keeps the parts unambiguous.

    `ts` (the lot's entry_ts) is used ONLY when there is no trade id: a lot opened by code
    that predates trade ids and is still open in state.json, or a direct caller/test. No
    production open path creates a lot without one any more (see _open_lot)."""
    if trade_id:
        code = {"OPEN": "O", "CLOSE": "C"}.get(str(intent).upper(), str(intent)[:1].upper())
        base = "qx" + _NON_ALNUM.sub("", str(trade_id)) + code
        return base if not seq or int(seq) <= 1 else f"{base}{int(seq)}"
    base = f"qqqexec-{leg}-{ts}-{intent}"
    return base if not seq else f"{base}-{seq}"


def _extract_broker_fill_price(record):
    """Best-effort fill price off a place_stock_order()/order_status() record's own
    "response" payload and "client_order_id". Returns None (never raises) when no
    recognisable field is present, which is the normal case for OFF/BLOCKED and for a
    LIMIT order-ack that reports status, not a fill, at placement time.

    Delegates the actual field lookup to api.webull_orders.order_status_fields(), which
    knows Webull's v3 nesting (per-order fields live under response["orders"][], see
    that function's docstring) -- this used to hand-roll its own candidate-key scan
    directly against `resp`/`resp["orders"][0]`/etc., and that scan's price-field
    candidate list never actually included "filled_price" (only "fill_price" and
    "filledPrice" -- neither matches the documented snake_case field), so a real filled
    v3 response's price would have been missed. Verified 2026-09-14 against
    developer.webull.com/apis/docs/reference/order-detail/ -- see order_status_fields()
    for the full field-name writeup."""
    if not isinstance(record, dict):
        return None
    resp = record.get("response")
    if not isinstance(resp, dict):
        return None
    fields = webull_orders.order_status_fields(resp, record.get("client_order_id"))
    v = fields.get("filled_price")
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# -- broker fill-price CAPTURE (feature #57, 2026-09-22; DEFERRED 2026-09-22) --------
# WHY THIS EXISTS: _extract_broker_fill_price above only ever reads the place_order()
# ACK -- the response captured at the instant the order was submitted. Webull documents
# filled_price on that endpoint as "may be zero or null" before the order has actually
# executed, and nothing previously asked again later, so broker_fill_px/slippage in
# broker_orders.csv were ALWAYS blank for a real send (confirmed by reading this file
# and api/webull_orders.py -- there is no other code path that ever wrote a non-empty
# broker_fill_px). This is the "ask again" -- a bounded order_status() query, tried a
# few times over about a minute from a DEFERRED queue (_maybe_capture_broker_fills),
# never from the order path itself.
#
# WHY DEFERRED, NOT INLINE (2026-09-22 review): the first cut called this function
# directly from _mirror_to_broker, once, right after the send. Two problems: (a) a
# market order is rarely filled in the milliseconds between the place_order ack and the
# very next call, so the common outcome was "no fill price yet", recorded once and never
# asked again -- the column stayed blank and the feature did nothing; (b) when two legs
# act on the same tick (this book's own trades do -- an exit and an entry landing in the
# same second), leg A's query delayed leg B's send by up to ORDER_STATUS_HARD_TIMEOUT_SEC,
# unacceptable while a 5-minute lag is being taken out of this exact path. So capture is
# now QUEUED (_queue_broker_fill_capture, called from _mirror_to_broker -- a pure state
# write, no network, cannot block or raise) and serviced from tick() the same way a
# broker re-send is (_maybe_capture_broker_fills, modelled directly on
# _queue_broker_resend / _maybe_resend_broker_orders): first attempt at least
# BROKER_FILL_CAPTURE_FIRST_DELAY_SEC after the send, a few retries spaced
# BROKER_FILL_CAPTURE_RETRY_GAP_SEC apart, giving up after
# BROKER_FILL_CAPTURE_MAX_AGE_SEC and recording why. This function's OWN bounded
# worker-thread timeout stays -- a hung SDK call still cannot wedge the tick that
# happens to service it, it can only delay that one job's own next retry.
#
# PAPER FILL-PRICE REALITY (verified from the installed SDK's own source and Webull's
# documented schema, per api/webull_orders.py's ORDER STATUS section and
# order_status_fields()'s docstring -- NOT from a live sandbox call, per this task's own
# offline-only rule and because no paper credentials exist on this machine anyway): a v3
# get_order_detail response nests status/filled_quantity/filled_price one level down in
# response["orders"][], and filled_price is documented to read zero/null only BEFORE the
# order executes -- nothing in the SDK or Webull's docs says the PAPER/sandbox
# environment specifically withholds a fill price once an order actually fills (unlike,
# say, a market-data entitlement gate elsewhere in this SDK). The SDK also exposes a
# push channel (webull.trade.trade_events_client.TradeEventsClient) that would report a
# fill the instant it happens instead of polling -- not wired here, same call already
# made for reconcile()'s own position reads (see api/webull_orders.py's ORDER STATUS
# note) -- so this bounded, retried poll is the adequate first cut; a fill that never
# lands inside the give-up window stays "not checked" and falls back to the
# tape-repriced price the next day (see _broker_trade_parity).
ORDER_STATUS_HARD_TIMEOUT_SEC = 4.0
_order_status_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="qqq-orderstatus")


def _query_broker_fill(adapter, signal_id, account_id=None, log=print):
    """(filled_price_or_None, note_or_None) -- asks Webull for this order's CURRENT
    status, bounded to ORDER_STATUS_HARD_TIMEOUT_SEC wall-clock on its own worker
    thread: the same precaution as _reconcile_with_timeout / default_webull_quote's
    QUOTE_HARD_TIMEOUT_SEC (this SDK's own connect/read timeouts are not reliably
    honoured on every call path). Called once per attempt of a deferred fill-capture
    job -- see _maybe_capture_broker_fills -- never from the order path itself.

    STRICTLY ADDITIVE, NEVER RAISES, NEVER BLOCKS THE CALLER LONGER THAN THE TIMEOUT: a
    slow call, a timeout, a stub/fake adapter with no order_status method, an SDK
    exception, or a response with no parseable filled_price all come back (None,
    <reason>) -- the broker/shadow order rows were already recorded before this job was
    even queued, and this never undoes, retries-inline or stalls anything off its
    result. The caller (the capture job) only fills in broker_fill_px/slippage when a
    real price comes back, and otherwise keeps <reason> for its own give-up path (see
    _finish_fill_capture) so a human can see WHY it is still blank instead of just
    guessing."""
    try:
        fut = _order_status_executor.submit(adapter.order_status, signal_id, account_id)
        result = fut.result(timeout=ORDER_STATUS_HARD_TIMEOUT_SEC)
    except concurrent.futures.TimeoutError:
        return None, f"order-status query timed out after {ORDER_STATUS_HARD_TIMEOUT_SEC:g}s"
    except Exception as e:
        return None, f"order-status query failed: {type(e).__name__}: {e}"
    try:
        if not isinstance(result, dict) or not result.get("ok"):
            reason = (result or {}).get("reason") or "order-status query returned not-ok"
            return None, reason
        fields = webull_orders.order_status_fields(
            result.get("response"), result.get("client_order_id") or signal_id)
        px = fields.get("filled_price")
        if px in (None, ""):
            return None, f"no fill price yet (status={fields.get('status') or 'unknown'})"
        try:
            return float(px), None
        except (TypeError, ValueError):
            return None, f"unparseable filled_price {px!r}"
    except Exception as e:
        return None, f"order-status parse failed: {type(e).__name__}: {e}"


def _mirror_to_broker(state, *, leg, side, shares, shadow_px, intent, ts=None, seq=0,
                      trade_id=None, resend=0, requeue=True, log=print):
    """Call after the shadow's own order/trade row is already recorded. Never raises.

    ORDER NETTING (2026-09-24): the three legs share ONE Webull account, and
    webull_orders.OrderAdapter.place_stock_order plans the real broker order(s) for
    `side`/`shares` from the ACCOUNT's current net position, not this leg's own literal
    side -- see that function's own docstring. This function still only ever sees ONE
    record back (`rec`) whatever that took, and still writes ONE broker_orders.csv row
    per call, keyed by `signal_id` exactly as before: `rec["parts"]` (when there is more
    than one -- the ordinary case is exactly one) is what actually reached Webull, and
    is passed through to _queue_broker_fill_capture so a colliding leg event still ends
    up with a single, quantity-weighted broker_fill_px on its own row.

    CROSS-HOST LEASE GATE (2026-09-14, "fail CLOSED once real orders can flow"): before
    actually sending, checks state["_broker_lease_ok"] -- set ONCE PER TICK by tick()'s
    call into _check_lease_for_broker (see that function's docstring for what "ok" means)
    -- whenever the broker adapter's effective mode is PAPER or LIVE. OFF mode is never
    gated: it sends nothing over the network regardless of the lease (mode="OFF" is a
    pure local record, see webull_orders.OrderAdapter.place_stock_order), so there is no
    order-collision risk to protect against there. `state` may not carry the key at all
    (e.g. a caller/test that invokes this directly rather than through tick()) -- default
    True preserves the exact pre-2026-09-14 behaviour (always attempt the send) for every
    such caller.

    A lease that cannot be verified suppresses the SEND only, recorded as mode="BLOCKED"
    exactly like an existing webull_orders rail refusal (halted/max_shares/etc) -- the
    shadow's own order/trade rows (written by the caller, above, BEFORE this function
    runs) are untouched, so the shadow book keeps recording simulated trades as if
    nothing happened. Nothing here is retried automatically once the lease recovers,
    same as every other BLOCKED reason in this module -- the next real shadow event
    mirrors normally. The two exceptions (2026-09-21) are an OPEN blocked by the
    adapter's own RECONCILE halt and any order Webull rejected as a same-instant
    DUPLICATE: those are queued and re-sent by _maybe_resend_broker_orders (`resend` is
    that re-send's number -- it suffixes the id with R<n>, because Webull and the
    adapter's idempotency cache both refuse a reused client_order_id). `requeue=False`
    opts a caller out (the orphan repair runs its own retries).

    PER ORDER, NOT ONLY PER TICK (2026-09-14): the verdict above is taken when the tick
    starts, and a tick can outlast it -- a slow order call before the next leg's, or the PC
    sleeping mid-tick while another host takes over. So a lease-managed process also re-checks
    its OWN latest landed stamp right before each send (_LeaseHolder.send_gate); a process that
    is not lease-managed (a direct call, a test) has no such state and is unaffected."""
    if not shares or shares <= 0:
        return
    signal_id = _broker_signal_id(leg, ts, intent, seq=seq, trade_id=trade_id)
    if resend:
        signal_id = f"{signal_id}R{int(resend)}"   # 28 + 2 chars for NOISE/ENGUQ, inside 32
    try:
        adapter = _get_broker_adapter(log=log)
        mode, _mode_reason = adapter.effective_mode()
        armed = mode in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE)
        at_send = _LEASE.send_gate(_LEASE.uid) if armed else None
        if armed and (not state.get("_broker_lease_ok", True)
                      or (at_send is not None and not at_send[0])):
            if not state.get("_broker_lease_ok", True):
                reason = state.get("_broker_lease_reason") or "lease unverifiable"
            else:
                reason = at_send[1]
            log(f"[qqq-exec] broker {intent} for {leg} BLOCKED before send (mode={mode}): "
                f"{reason} -- shadow record above stands, broker mirror suppressed")
            rec = {"ok": False, "sent": False, "mode": "BLOCKED", "reason": reason,
                  "side": _broker_side(side, intent), "client_order_id": "",
                  "duplicate": False}
        else:
            rec = adapter.place_stock_order(leg=leg, signal_id=signal_id, symbol=BROKER_SYMBOL,
                                            side=_broker_side(side, intent),
                                            qty=int(round(shares)), intent=intent)
    except Exception as e:
        rec = {"ok": False, "sent": False, "mode": "ERROR", "error": f"{type(e).__name__}: {e}"}
        log(f"[qqq-exec] broker adapter call failed for {leg} {intent} (non-fatal -- the "
            f"shadow record above stands): {type(e).__name__}: {e}")
    broker_px = _extract_broker_fill_price(rec)
    slippage = None
    if broker_px is not None and shadow_px is not None:
        try:
            slippage = round(float(broker_px) - float(shadow_px), 4)
        except (TypeError, ValueError):
            slippage = None
    row = {
        "ts_et": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "leg": leg, "intent": intent,
        "side": rec.get("side") or _broker_side(side, intent), "shares": shares,
        "signal_id": signal_id, "client_order_id": rec.get("client_order_id") or "",
        "mode": rec.get("mode") or "", "ok": rec.get("ok"), "sent": rec.get("sent"),
        "shadow_px": round(shadow_px, 4) if shadow_px is not None else "",
        "broker_fill_px": broker_px if broker_px is not None else "",
        "slippage": slippage if slippage is not None else "",
        "reason": rec.get("reason") or rec.get("error") or "",
        "duplicate": bool(rec.get("duplicate", False)),
        # CROSS-HOST LEASE (2026-09-14): which host attempted (or was blocked from) this
        # send -- see BROKER_ORDER_COLS. Recorded on every row, not just blocked ones, so
        # a handoff between the owner's PC and the cloud VM is visible in the CSV itself.
        "host_id": _lease_host_id(),
    }
    _append_csv(BROKER_ORDERS_CSV, BROKER_ORDER_COLS, row, ORDERS_KEEP)
    state["_broker_last"] = {"leg": leg, "intent": intent, "mode": rec.get("mode"),
                             "ok": rec.get("ok"), "reason": row["reason"]}
    if rec.get("mode") in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE) \
            and rec.get("ok") and rec.get("sent"):
        # FILL-PRICE CAPTURE (feature #57, DEFERRED 2026-09-22): queued for a LATER
        # tick, never attempted here -- see _maybe_capture_broker_fills for why an
        # inline query at this exact call site was wrong (asked before a fill existed,
        # and risked stalling the next leg's send). This call only writes into
        # state -- no network, cannot block or raise into this tick.
        # ORDER NETTING (2026-09-24): a leg event that collided with another leg's
        # position may have gone out as more than one broker order (see
        # api.webull_orders.place_stock_order's own docstring, `record["parts"]`) --
        # only pass `parts` through when there is genuinely more than one, so a plain
        # (non-colliding, still the overwhelming majority) send keeps queuing a job
        # shaped exactly like it always has (see _queue_broker_fill_capture's own
        # backward-compatibility note).
        rec_parts = rec.get("parts")
        _queue_broker_fill_capture(state, leg=leg, intent=intent, signal_id=signal_id,
                                   account_id=rec.get("account_id"), shadow_px=shadow_px,
                                   parts=rec_parts if rec_parts and len(rec_parts) > 1 else None,
                                   log=log)
    if rec.get("mode") in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
        # BROKER RECONCILE (2026-09-14, FIX 2): a real send was just attempted (ok or
        # not) -- have _maybe_run_broker_reconcile run reconcile() on the VERY NEXT
        # tick rather than waiting for the periodic interval. Set here (not read here)
        # so this never depends on _mirror_to_broker's own call order relative to the
        # housekeeping block later in tick().
        state["_reconcile_due"] = True
        # the post-order check waits out BROKER_RECONCILE_POST_ORDER_GRACE_SEC from the
        # LAST send, so a burst of orders is checked once, after every fill has landed
        state["_last_broker_send_at"] = time.time()
    if rec.get("mode") not in (None, "OFF") and not rec.get("ok", False):
        log(f"[qqq-exec] broker {intent} for {leg} NOT ok (mode={rec.get('mode')}): "
            f"{row['reason']}")
    if rec.get("nothing_to_close"):
        msg = (f"QQQ BROKER: {leg} closed in the book, but Webull never held it (its buy "
               f"never went through) -- no sell sent, Webull stays flat for {leg}")
        _log_event(state, "broker", msg, log=log)
        _notify(msg, "EDGELOG QQQ BROKER", log)
    if rec.get("partial"):
        # ORDER NETTING (2026-09-24): one or more of this leg event's broker parts (see
        # api.webull_orders.place_stock_order's `parts`) was refused while at least one
        # other part landed -- broker_sent_positions[leg] only moved by the accepted
        # share of it (see that function's own docstring), so this leg's book and
        # Webull's real position for it are now off by the refused remainder. Worth a
        # push the same way "nothing to close" is -- both are "the book and the broker
        # disagree" situations the owner needs to look at, not something later ticks
        # self-heal.
        msg = (f"QQQ BROKER: {leg} {intent} only PARTIALLY reached Webull: {row['reason']}")
        _log_event(state, "broker", msg, log=log)
        _notify(msg, "EDGELOG QQQ BROKER", log)
    if requeue:
        _queue_broker_resend(state, rec, leg=leg, side=side, shares=shares,
                             shadow_px=shadow_px, intent=intent, ts=ts, seq=seq,
                             trade_id=trade_id, resend=resend, log=log)


# -- broker RE-SEND (2026-09-21) ---------------------------------------------------------
def _broker_halt_source(log=print):
    """The adapter's halt source while it is halted ("reconcile" / "kill_file"), else
    None. Never raises; an adapter without halt_state() (a test fake) reads as not halted."""
    try:
        halted, source, _reason = _get_broker_adapter(log=log).halt_state()
        return (source or "unknown") if halted else None
    except Exception:
        return None


def _queue_broker_resend(state, rec, *, leg, side, shares, shadow_px, intent, ts, seq,
                         trade_id, resend, log=print):
    """Queue a broker order that did not go through for another try later
    (state["_broker_resend"], keyed "<leg>:<intent>"), or drop it from the queue once it
    has gone through. Never raises.

    Only two failures are worth another try -- both are timing glitches, not decisions:
      * an OPEN the adapter BLOCKED because of its OWN reconcile halt. 2026-09-21: a false
        post-order mismatch halted entries at 09:42, NOISE entered at 09:45:12, its buy
        was blocked, the halt cleared seconds later -- and nothing ever sent the buy, so
        the book held NOISE all day and Webull did not;
      * ANY order Webull rejected as a duplicate of one still in its book (417
        OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK). Webull compares the ORDER, not our
        id, so two legs sending the identical SELL/BUY 10 QQQ in one instant collide: the
        09:31 orphan repair, an end-of-day flatten with two legs open, two legs entering
        on the same bar. That order was never placed, so it goes again a tick later,
        after the one it collided with has filled.
    A kill-file halt, a lease block, a rails refusal, "nothing to close" and an OFF /
    ERROR record are never re-sent: those are decisions (or a broken adapter)."""
    try:
        q = state.setdefault("_broker_resend", {})
        key = f"{leg}:{intent}"
        mine = bool(trade_id) and (q.get(key) or {}).get("trade_id") == trade_id
        if rec.get("ok"):
            if mine:
                q.pop(key, None)
            return
        text = str(rec.get("reason") or rec.get("error") or "")
        why = None
        if "DUPLICATE_ORDER_CHECK" in text:
            why = "duplicate"
        elif (intent == "OPEN" and rec.get("mode") == "BLOCKED" and text.startswith("halted:")
              and _broker_halt_source(log=log) == "reconcile"):
            why = "halt"
        if not why or not trade_id:
            return
        now = time.time()
        q[key] = {"leg": leg, "intent": intent, "side": side, "shares": shares,
                  "shadow_px": shadow_px, "ts": None if ts is None else str(ts),
                  "seq": seq, "trade_id": trade_id, "why": why,
                  "tries": int(resend or 0),
                  "first_at": (q[key].get("first_at") if mine else None) or now,
                  "last_at": now}
        log(f"[qqq-exec] broker {intent} for {leg} queued for a re-send ("
            + ("Webull saw a same-instant duplicate" if why == "duplicate"
               else "blocked by a reconcile halt")
            + f"; {int(resend or 0)} of {BROKER_RESEND_MAX_TRIES} re-sends used)")
    except Exception as e:
        log(f"[qqq-exec] broker re-send bookkeeping failed (non-fatal): {type(e).__name__}: {e}")


def _maybe_resend_broker_orders(state, cfg, nowdt, active, log=print):
    """Send ONE queued order (see _queue_broker_resend) per tick, when it is safe to.
    Never raises.
      * one per tick, oldest first, never in the tick right after its failure -- so a
        re-send cannot itself collide with another order;
      * an OPEN goes only while the book still holds that very trade (same trade id),
        at or before session.last_entry and within broker_open_resend_window_min of its
        first try (a late entry at a stale price is worse than none); one blocked by a
        halt also waits until the adapter is no longer halted (the halted re-check in
        _maybe_run_broker_reconcile looks every 30 s, so a false halt clears fast);
      * a CLOSE goes whatever the book says (the book already closed the lot, the shares
        are still at Webull); webull_orders refuses it if nothing is held there;
      * at most BROKER_RESEND_MAX_TRIES re-sends, each under a fresh id. Giving up, or
        running out of window or market, logs an event and sends a phone alert."""
    q = state.get("_broker_resend") or {}
    if not q:
        return
    try:
        now = time.time()
        sess = cfg.get("session") or {}
        window_min = _cfg_num(cfg, "broker_open_resend_window_min", BROKER_OPEN_RESEND_WINDOW_MIN)
        for key in sorted(q, key=lambda k: float(q[k].get("first_at") or 0)):
            item = q[key]
            leg, intent, why = item.get("leg"), item.get("intent"), item.get("why")
            tries = int(item.get("tries") or 0)
            what = "buy" if intent == "OPEN" else "sell"
            lot = (state.get("legs") or {}).get(leg)
            if intent == "OPEN" and (not lot or lot.get("trade_id") != item.get("trade_id")):
                q.pop(key, None)
                msg = (f"Re-send of the {leg} buy dropped: the book closed that trade before "
                       f"Webull could get it")
                log(f"[qqq-exec] {msg}")
                _log_event(state, "broker", msg, log=log)
                continue
            late = intent == "OPEN" and (
                (now - float(item.get("first_at") or now)) / 60.0 > window_min
                or _et_hhmm(nowdt) > _hhmm(sess.get("last_entry", "15:55")))
            if tries >= BROKER_RESEND_MAX_TRIES or late or not active:
                q.pop(key, None)
                cause = ("its window passed" if late else "the market window closed" if not active
                         else f"{tries} re-sends failed")
                msg = (f"QQQ BROKER: gave up re-sending the {leg} {what} ({cause}; first try "
                       + ("blocked by a reconcile halt" if why == "halt"
                          else "rejected by Webull as a duplicate") + "). "
                       + (f"The book holds {leg} but Webull does not." if intent == "OPEN"
                          else f"Webull may still hold {leg}'s shares -- check and sell by hand."))
                log(f"[qqq-exec] {msg}")
                _log_event(state, "broker", msg, log=log)
                _notify(msg, "EDGELOG QQQ BROKER", log)
                continue
            if why == "halt" and _broker_halt_source(log=log) is not None:
                continue  # still halted -- the 30 s halted re-check clears a false one
            if now - float(item.get("last_at") or 0) < BROKER_RESEND_MIN_GAP_SEC:
                continue
            shares = lot.get("shares_remaining") if intent == "OPEN" else item.get("shares")
            log(f"[qqq-exec] broker RE-SEND {intent} for {leg} (re-send {tries + 1} of "
                f"{BROKER_RESEND_MAX_TRIES}; first try {why})")
            _mirror_to_broker(state, leg=leg, side=item.get("side"), shares=shares,
                              shadow_px=item.get("shadow_px"), intent=intent,
                              ts=item.get("ts"), seq=item.get("seq") or 0,
                              trade_id=item.get("trade_id"), resend=tries + 1, log=log)
            last = state.get("_broker_last") or {}
            if last.get("ok") and last.get("leg") == leg:
                msg = (f"QQQ BROKER: {leg} {what} re-sent and accepted ("
                       + ("after the reconcile halt cleared" if why == "halt"
                          else "after a same-instant duplicate") + ")")
                _log_event(state, "broker", msg, log=log)
                _notify(msg, "EDGELOG QQQ BROKER", log)
            elif key in q and int(q[key].get("tries") or 0) == tries:
                # failed for a reason that is not worth another try (kill file, rails,
                # nothing held at Webull) -- _mirror_to_broker already logged why
                q.pop(key, None)
                _log_event(state, "broker", f"Re-send of the {leg} {what} refused: "
                          f"{last.get('reason') or 'see the broker log'}", log=log)
            return  # ONE re-send per tick
    except Exception as e:
        log(f"[qqq-exec] broker re-send failed (non-fatal): {type(e).__name__}: {e}")


# -- PLAIN-ENGLISH BROKER ERRORS (2026-09-23, "HONEST WARNINGS" item 2) ----------------
# api.webull_orders.OrderAdapter records a raw Webull ServerException verbatim into
# record["error"]/self._last_error (that module is NOT changed here -- see its own
# place_stock_order -- this only reads the text it already produces), e.g.:
#   "ServerException: HTTP Status: 417, Code: OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION,
#    Msg: ..., RequestID: ..."
# That is exactly what the owner's screenshot showed twice (once as "Last order", once
# as "Last error") with a large empty gap left over from nothing but that raw text. One
# sentence per KNOWN code below; an unrecognised Webull code still gets a short, honest
# fallback instead of the raw dump, and the raw text always still travels alongside (see
# _build_broker_status) for a click-to-expand "details" on the web tab -- never lost,
# never the FIRST thing shown.
_WEBULL_ERROR_CODE_RE = re.compile(r"Code:\s*([A-Za-z0-9_]+)")

WEBULL_ERROR_SENTENCES = {
    "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION":
        "Webull refused: the account already holds the opposite side of QQQ from another strategy",
    "OPENAPI_GENERATE_NEW_SHORT_POSITION":
        "Webull refused: this account type cannot short",
}


def _plain_broker_error(raw):
    """One-sentence, human-readable rewrite of a raw broker/adapter error or reason
    string, or None if `raw` is empty. A recognised `Code: OPENAPI_...` token (see
    WEBULL_ERROR_SENTENCES) gets its own hand-written sentence; a Code: token this
    dict does not know yet gets a generic-but-honest fallback ("Webull refused the
    order (code X)") instead of the raw SDK dump; a string with no Code: token at all
    (a rail refusal already written in plain English, a non-Webull exception, ...) is
    returned UNCHANGED -- there is nothing to translate, and this must never mangle an
    already-readable reason. Never raises."""
    try:
        s = str(raw or "").strip()
        if not s:
            return None
        m = _WEBULL_ERROR_CODE_RE.search(s)
        if not m:
            return s
        code = m.group(1)
        # Webull suffixes some codes by order intent -- the live 2026-09-23 refusal read
        # OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION_OPEN -- so a known code also matches
        # as a prefix followed by "_".
        for known, sentence in WEBULL_ERROR_SENTENCES.items():
            if code == known or code.startswith(known + "_"):
                return sentence
        return f"Webull refused the order (code {code})"
    except Exception:
        return str(raw) if raw else None


def _build_broker_status(state=None, log=print):
    """Small, flat summary of api.webull_orders' own status() for the "broker" key in
    the published doc (see _build_doc) -- trimmed so the phone tab's future broker card
    has what it needs without growing the doc (Firestore 1 MiB cap) or nesting arrays
    (Firestore rejects array-of-arrays; every value here is a scalar or a flat dict).

    `state` is optional (default None -> lease fields report as verified/no reason) so
    every pre-2026-09-14 caller/test that calls this with no state argument keeps working
    unchanged."""
    try:
        adapter = _get_broker_adapter(log=log)
        st = adapter.status()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    last_order = st.get("last_order") or {}
    state = state or {}
    last_order_ts = last_order.get("ts")
    last_order_ts_et = None
    if last_order_ts is not None:
        try:
            last_order_ts_et = (datetime.fromtimestamp(float(last_order_ts), _NY) if _NY
                                else datetime.utcfromtimestamp(float(last_order_ts))).isoformat()
        except (TypeError, ValueError, OSError):
            last_order_ts_et = None
    return {
        "requested_mode": st.get("requested_mode"),
        "effective_mode": st.get("effective_mode"),
        "mode_reason": st.get("mode_reason"),
        "environment": st.get("environment"),
        "paper_credentials_present": st.get("paper_credentials_present"),
        "live_credentials_present": st.get("live_credentials_present"),
        "live_armed": st.get("live_armed"),
        "kill_file_present": st.get("kill_file_present"),
        "halted": st.get("halted"),
        "halt_reason": st.get("halt_reason"),
        "last_error": st.get("last_error"),
        # PLAIN-ENGLISH BROKER ERRORS (2026-09-23, item 2): the raw text above stays
        # exactly as before (a details toggle on the web tab can still show it); this
        # is the one-sentence rewrite for the primary display -- see
        # _plain_broker_error. None when there is no last_error at all.
        "last_error_plain": _plain_broker_error(st.get("last_error")),
        "last_order": {
            "leg": last_order.get("leg"), "symbol": last_order.get("symbol"),
            "side": last_order.get("side"), "qty": last_order.get("qty"),
            "intent": last_order.get("intent"), "mode": last_order.get("mode"),
            "ok": last_order.get("ok"), "sent": last_order.get("sent"),
            "reason": last_order.get("reason") or last_order.get("error"),
            # PLAIN-ENGLISH BROKER ERRORS (2026-09-23, item 2): same rewrite as
            # last_error_plain above, applied to THIS order's own raw reason/error.
            "reason_plain": _plain_broker_error(last_order.get("reason") or last_order.get("error")),
            # NEW (2026-09-14): ISO-8601 US/Eastern timestamp of the last order --
            # see coordinator's field list; every existing last_order.* key above is
            # untouched.
            "ts_et": last_order_ts_et,
        },
        "daily_pnl": st.get("daily_pnl"),
        "open_legs": st.get("open_legs"),
        # CROSS-HOST LEASE (2026-09-14): loud, phone-visible record of whether THIS
        # host's broker sends are currently gated by an unverifiable/lost lease -- set
        # once per tick by tick() (see _check_lease_for_broker). Only meaningful in
        # PAPER/LIVE (see _mirror_to_broker); stays True/None in OFF, where nothing is
        # ever gated.
        "lease_ok_to_send": bool(state.get("_broker_lease_ok", True)),
        "lease_block_reason": state.get("_broker_lease_reason"),
        # RECONCILE HARDENING (2026-09-14, FIX 2) -- new, additive fields only:
        "last_reconcile_at": st.get("last_reconcile_at"),
        "last_reconcile_result": st.get("last_reconcile_result"),
        # DAILY P&L WIRING (2026-09-14) -- which source fed update_daily_pnl() this
        # tick, see _sync_broker_daily_pnl.
        "daily_pnl_source": state.get("_broker_pnl_source"),
    }


# -- broker FILL CAPTURE, deferred (feature #57, DEFERRED 2026-09-22) ----------------
# See the "broker fill-price CAPTURE" section far above (_query_broker_fill) for WHY
# this exists and why it does not run inline from _mirror_to_broker any more. Modelled
# directly on the broker RE-SEND section above (_queue_broker_resend /
# _maybe_resend_broker_orders): state["_broker_fill_capture"] is a queue of jobs, one
# per "<leg>:<intent>", keyed and serviced the same way.
#
# RESTART SURVIVAL: this queue lives in the SAME `state` dict that load_state()/
# save_state() already round-trip through state.json AS A WHOLE (json.dump(state,...)/
# base.update(json.load(...))) -- neither this queue nor the resend one is special-
# cased in _default_state(), both are created on first use via state.setdefault and
# read back with state.get(...) or {}. So this queue survives a restart exactly like
# the resend queue does, for the identical reason -- no separate persistence code
# needed or written.
BROKER_FILL_CAPTURE_FIRST_DELAY_SEC = 3.0    # a market order is rarely filled sooner
BROKER_FILL_CAPTURE_RETRY_GAP_SEC = 10.0     # never two attempts at one job back to back
BROKER_FILL_CAPTURE_MAX_AGE_SEC = 60.0       # give up "after about a minute"


def _queue_broker_fill_capture(state, *, leg, intent, signal_id, account_id, shadow_px,
                               parts=None, log=print):
    """Queue a deferred order_status() query for a just-accepted real send -- serviced
    later by _maybe_capture_broker_fills, from tick(). A pure `state` write: no network
    call, cannot block or raise into the order path. Never raises.

    KEYED EXACTLY LIKE _queue_broker_resend's OWN QUEUE ("<leg>:<intent>"): a second
    real send for the same leg+intent before the first job resolves overwrites it --
    the same tradeoff the resend queue already accepts (see its own docstring). Engine-
    mode trades are single-shot per leg (module docstring), so in practice this only
    bites a rapid ninjatrader-mode reduce sequence, and those rows never reach
    _broker_trade_parity anyway (see _apply_broker_parity) -- their own NT parity is
    unaffected either way.

    `parts` (ORDER NETTING, 2026-09-24): the caller's own list of ACCEPTED broker parts
    (api.webull_orders.place_stock_order's `record["parts"]`) when a leg event was
    split into more than one broker order -- omit (the default) for the ordinary,
    non-colliding case, which queues a job shaped EXACTLY as it always has (this
    parameter and the "parts" key below did not exist before this feature; every
    pre-existing caller/test that never passes it gets the identical job dict as
    before, `signal_id` included, serviced by the unchanged single-id path in
    _maybe_capture_broker_fills). When given with more than one entry, each part gets
    its OWN client_order_id/qty/resolved-tracking so the eventual capture can query
    every part and combine their fill prices (see _finish_fill_capture_parts) --
    `signal_id` is still stored and still the one _finish_fill_capture writes back to
    broker_orders.csv under (the row is keyed by the LEG EVENT's signal_id, never by a
    part's own id -- see _update_broker_order_row)."""
    try:
        key = f"{leg}:{intent}"
        now = time.time()
        job = {
            "leg": leg, "intent": intent, "signal_id": signal_id,
            "account_id": account_id, "shadow_px": shadow_px,
            "tries": 0, "first_at": now, "last_at": 0.0, "last_note": None,
        }
        if parts and len(parts) > 1:
            job["parts"] = [
                {"client_order_id": p.get("client_order_id"), "qty": p.get("qty"),
                 "resolved": False, "price": None, "tries": 0, "last_at": 0.0,
                 "last_note": None}
                for p in parts if p.get("client_order_id")
            ]
        state.setdefault("_broker_fill_capture", {})[key] = job
    except Exception as e:
        log(f"[qqq-exec] fill-capture queueing failed (non-fatal): {type(e).__name__}: {e}")


def _update_broker_order_row(signal_id, updates, log=print):
    """Rewrites broker_orders.csv's own row for `signal_id`, merging `updates` in --
    the ONLY place this file's already-written history is ever mutated (every other
    writer only appends, see _append_csv). Used solely by _finish_fill_capture, to fill
    in broker_fill_px/slippage/reason once a deferred capture attempt resolves, on the
    row _mirror_to_broker already wrote at send time. Preserves whatever columns are
    ACTUALLY on disk (not necessarily today's BROKER_ORDER_COLS -- an old file migrates
    lazily, on its next _append_csv, not here).

    ATOMIC (2026-09-22 review): the rewritten rows are written to a private temp file
    beside the real one, fsynced, then swapped in with _replace_with_retry -- the SAME
    shared helper save_state uses -- rather than truncating the live ledger in place
    with a plain `open(path, "w")`. That plain-overwrite shape is exactly the failure
    class that once garbled the QQQ bar cache and blocked every push gate (see
    tests/test_qqq_cache_atomic.py): a crash, a kill, a disk hiccup or a reader holding
    the file mid-write would otherwise truncate broker_orders.csv -- this book's own
    record of what it sent to Webull -- not just skip one field update. `os.replace` is
    atomic on both Windows and POSIX, so a concurrent reader only ever sees the OLD
    file or the fully-written NEW one, never a half-written one -- the same property
    tests/test_qqq_cache_atomic.py pins for the other shared CSV writers in this repo.

    NEVER RAISES. Returns True if a row was found and rewritten -- False when the row
    is missing (aged out of the file's own ORDERS_KEEP trim), the file cannot be read,
    the temp file cannot be written, or the swap itself fails -- and on EVERY False
    path the original file is left completely untouched and no `.tmp` is left behind
    (keep_tmp_on_failure=False -- see _replace_with_retry's own docstring for why that
    differs from save_state)."""
    try:
        with open(BROKER_ORDERS_CSV, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
    except Exception as e:
        log(f"[qqq-exec] fill-capture row update failed (read): {type(e).__name__}: {e}")
        return False
    if not fieldnames:
        return False
    found = False
    for row in rows:
        if row.get("signal_id") == signal_id:
            row.update(updates)
            found = True
            break
    if not found:
        return False
    tmp = "%s.%d.%d.tmp" % (BROKER_ORDERS_CSV, os.getpid(), int(time.time() * 1000) % 100000)
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        log(f"[qqq-exec] fill-capture row update failed (write): {type(e).__name__}: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    return _replace_with_retry(tmp, BROKER_ORDERS_CSV, log=log,
                               what="broker_orders.csv row update",
                               keep_tmp_on_failure=False)


def _finish_fill_capture(item, px, note, log=print):
    """Terminal step for one fill-capture job -- either a captured price or a final
    give-up. Updates broker_orders.csv's own row for this order (see
    _update_broker_order_row) and logs the outcome. Never raises."""
    try:
        updates = {}
        if px is not None:
            shadow_px = item.get("shadow_px")
            slippage = None
            if shadow_px is not None:
                try:
                    slippage = round(float(px) - float(shadow_px), 4)
                except (TypeError, ValueError):
                    slippage = None
            updates["broker_fill_px"] = px
            updates["slippage"] = slippage if slippage is not None else ""
        elif note:
            # only ever fills an otherwise-blank reason cell -- a capture job exists
            # only for a row that was already ok+sent (see _queue_broker_fill_capture),
            # so there is never a real block/error reason here to overwrite.
            updates["reason"] = note
        if updates and not _update_broker_order_row(item.get("signal_id"), updates, log=log):
            log(f"[qqq-exec] fill-capture: broker_orders.csv row for signal "
                f"{item.get('signal_id')} not found (aged out of ORDERS_KEEP) -- "
                f"capture result dropped")
        if px is not None:
            log(f"[qqq-exec] fill-capture CAPTURED {item.get('leg')} {item.get('intent')} "
                f"(signal {item.get('signal_id')}): broker_fill_px={px}")
        else:
            log(f"[qqq-exec] fill-capture GAVE UP for {item.get('leg')} {item.get('intent')} "
                f"(signal {item.get('signal_id')}) after {item.get('tries', 0)} "
                f"attempt(s): {note}")
    except Exception as e:
        log(f"[qqq-exec] fill-capture finish failed (non-fatal): {type(e).__name__}: {e}")


def _finish_fill_capture_parts(item, log=print):
    """Terminal step for a MULTI-part fill-capture job (ORDER NETTING, 2026-09-24 --
    see _queue_broker_fill_capture's `parts`). Combines whichever parts actually
    resolved a price into ONE quantity-weighted fill price for the leg event -- a part
    that never got a price (refused at the broker, or its own query gave up) is left
    out of the weighting entirely, not treated as a zero -- and hands that single
    number to _finish_fill_capture exactly like the single-order path would, so the
    broker_orders.csv row (keyed by the leg event's own signal_id, never a part's id)
    and the log line are identical in shape either way. If NOT ONE part ever priced,
    this is a full give-up, same as the single-order path's own give-up. Never raises
    (delegates the actual work to _finish_fill_capture, which already never raises)."""
    parts = item.get("parts") or []
    priced = [(p.get("qty") or 0, p["price"]) for p in parts if p.get("price") is not None]
    total_qty = sum(q for q, _ in priced)
    if priced and total_qty:
        px = round(sum(q * p for q, p in priced) / total_qty, 4)
        note = None
    else:
        px = None
        notes = [p.get("last_note") for p in parts if p.get("last_note")]
        note = "; ".join(dict.fromkeys(notes)) or "gave up waiting for a fill price"
    _finish_fill_capture(item, px, note, log=log)


def _maybe_capture_broker_fills(state, cfg, nowdt, active, log=print):
    """Service the queued fill-price jobs (see _queue_broker_fill_capture) -- modelled
    on _maybe_resend_broker_orders: giving up on a stale job is cheap local bookkeeping
    (no network) and every overdue one is cleared in the same tick, but at most ONE
    job's actual order_status() SDK call happens per tick, oldest first -- so a burst of
    queued jobs can never itself stack network calls onto one tick the way the ORIGINAL
    inline design effectively could. Never raises.

    A job waits BROKER_FILL_CAPTURE_FIRST_DELAY_SEC before its first attempt (a market
    order is rarely filled in the same instant it was sent), tries again at most once
    every BROKER_FILL_CAPTURE_RETRY_GAP_SEC, and gives up (recording why, via
    _finish_fill_capture) once it has been queued longer than
    BROKER_FILL_CAPTURE_MAX_AGE_SEC -- "a few retries over about a minute". The
    underlying SDK call is still bounded by ORDER_STATUS_HARD_TIMEOUT_SEC on its own
    worker thread (_query_broker_fill), so a hung call can delay only THIS job's own
    next retry, never another leg's send on this or a later tick.

    `cfg` is accepted (unused today) for the same call shape as
    _maybe_resend_broker_orders/_maybe_run_broker_reconcile, in case a future knob
    needs it. Runs regardless of `active` -- a status READ is not a trading action, and
    a job still has to age out on its own clock even if the session window has closed
    (a CLOSE from 15:59 must not be left uncaptured forever just because it is now
    after hours)."""
    q = state.get("_broker_fill_capture") or {}
    if not q:
        return
    try:
        adapter = _get_broker_adapter(log=log)
    except Exception as e:
        log(f"[qqq-exec] fill-capture skipped (adapter unavailable): {type(e).__name__}: {e}")
        return
    try:
        now = time.time()
        for key in sorted(q, key=lambda k: float(q[k].get("first_at") or 0)):
            item = q[key]
            age = now - float(item.get("first_at") or now)
            parts = item.get("parts")
            if parts:
                # ORDER NETTING (2026-09-24): a job with more than one broker part --
                # see _queue_broker_fill_capture's `parts` and _finish_fill_capture_parts
                # for the quantity-weighted combine. The whole job still ages out on ONE
                # shared clock (`first_at`, set once at queue time) so a part that never
                # resolves cannot keep the job alive past the ordinary give-up window;
                # each part gets its OWN retry-gap/tries so one already-priced part is
                # never re-queried while a sibling still waits.
                if age > BROKER_FILL_CAPTURE_MAX_AGE_SEC:
                    q.pop(key, None)
                    _finish_fill_capture_parts(item, log=log)
                    continue
                if age < BROKER_FILL_CAPTURE_FIRST_DELAY_SEC:
                    continue
                target = None
                for p in parts:
                    if p.get("resolved"):
                        continue
                    if now - float(p.get("last_at") or 0) < BROKER_FILL_CAPTURE_RETRY_GAP_SEC:
                        continue
                    target = p
                    break
                if target is None:
                    continue  # every part is either resolved or in its own retry cooldown
                target["tries"] = int(target.get("tries") or 0) + 1
                target["last_at"] = now
                px, note = _query_broker_fill(adapter, target["client_order_id"],
                                              account_id=item.get("account_id"), log=log)
                if px is not None:
                    target["resolved"] = True
                    target["price"] = px
                else:
                    target["last_note"] = note
                    log(f"[qqq-exec] fill-capture retry {target['tries']} for {item.get('leg')} "
                        f"{item.get('intent')} part {target['client_order_id']}: {note}")
                if all(p.get("resolved") for p in parts):
                    q.pop(key, None)
                    _finish_fill_capture_parts(item, log=log)
                return  # ONE order_status() SDK call per tick
            # -- ordinary, single-order job: unchanged from before ORDER NETTING --
            if age > BROKER_FILL_CAPTURE_MAX_AGE_SEC:
                q.pop(key, None)
                _finish_fill_capture(
                    item, None, item.get("last_note") or "gave up waiting for a fill price",
                    log=log)
                continue
            if age < BROKER_FILL_CAPTURE_FIRST_DELAY_SEC:
                continue
            if now - float(item.get("last_at") or 0) < BROKER_FILL_CAPTURE_RETRY_GAP_SEC:
                continue
            item["tries"] = int(item.get("tries") or 0) + 1
            item["last_at"] = now
            px, note = _query_broker_fill(adapter, item.get("signal_id"),
                                          account_id=item.get("account_id"), log=log)
            if px is not None:
                q.pop(key, None)
                _finish_fill_capture(item, px, None, log=log)
            else:
                item["last_note"] = note
                log(f"[qqq-exec] fill-capture retry {item['tries']} for {item.get('leg')} "
                    f"{item.get('intent')} (signal {item.get('signal_id')}): {note}")
            return  # ONE order_status() SDK call per tick
    except Exception as e:
        log(f"[qqq-exec] fill-capture housekeeping failed (non-fatal): {type(e).__name__}: {e}")


# -- broker daily P&L wiring (2026-09-14) --------------------------------------------
# api.webull_orders.OrderAdapter.update_daily_pnl() existed since the rail was built
# but nothing ever called it, so daily_loss_limit_usd could never trip. Fed here, once
# per tick, from whichever source is actually available -- see _compute_broker_daily_pnl.
def _broker_realized_today(today, log=print):
    """(realized_total, any_broker_priced) from today's BROKER_ORDERS_CSV rows for
    mode PAPER/LIVE with ok truthy -- FIFO pairs each leg's OPEN with its next CLOSE
    using the row's own broker_fill_px (the documented `filled_price`, see
    api.webull_orders.order_status_fields()/1ed627e) when present, falling back to
    shadow_px for that one row when the broker didn't echo a fill price back yet.
    `any_broker_priced` is True only if at least one row actually had a real
    broker_fill_px -- see _compute_broker_daily_pnl for why that distinction decides
    the reported source. Never raises; a CSV read problem returns (0.0, False)."""
    realized = 0.0
    any_broker_priced = False
    open_px_by_leg = {}
    try:
        with open(BROKER_ORDERS_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return 0.0, False
    for row in rows:
        if str(row.get("ts_et") or "")[:10] != today:
            continue
        if row.get("mode") not in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
            continue
        if str(row.get("ok")) != "True":
            continue
        try:
            shares = float(row.get("shares") or 0)
        except (TypeError, ValueError):
            continue
        if shares <= 0:
            continue
        px_raw = row.get("broker_fill_px")
        if px_raw not in (None, ""):
            any_broker_priced = True
        else:
            px_raw = row.get("shadow_px")
        try:
            px = float(px_raw)
        except (TypeError, ValueError):
            continue
        leg = row.get("leg")
        if row.get("intent") == "OPEN":
            existing = open_px_by_leg.get(leg)
            if existing and existing.get("side") == row.get("side"):
                # A second OPEN mirror on the same leg before any CLOSE (should not
                # happen under one_open_position_per_leg, but average defensively
                # rather than silently overwrite the earlier fill's price).
                tot = existing["shares"] + shares
                existing["px"] = (existing["px"] * existing["shares"] + px * shares) / tot
                existing["shares"] = tot
            else:
                open_px_by_leg[leg] = {"px": px, "side": row.get("side"), "shares": shares}
        elif row.get("intent") == "CLOSE" and leg in open_px_by_leg:
            # Decrement rather than pop-on-first-row: a leg can be closed across
            # MULTIPLE partial CLOSE mirrors (ninjatrader signal_source mode's partial
            # exits) -- each one closes only part of what's still recorded open here.
            opened = open_px_by_leg[leg]
            side_mult = 1 if opened["side"] == "BUY" else -1
            closed_shares = min(shares, opened["shares"])
            realized += (px - opened["px"]) * side_mult * closed_shares
            opened["shares"] -= closed_shares
            if opened["shares"] <= 1e-9:
                open_px_by_leg.pop(leg, None)
    return round(realized, 2), any_broker_priced


def _compute_broker_daily_pnl(state, adapter, log=print):
    """(pnl, source). PREFERRED source="broker_fills": today's realized P&L computed
    from broker_orders.csv's own recorded fills (see _broker_realized_today) plus an
    unrealized mark, for whatever legs the broker still holds open, taken from the
    shadow book's own per-leg mark (state["_unrl_by_leg"]) -- both sides trade the
    identical QQQ position 1:1 (see _mirror_to_broker), so this is a network-free,
    reasonable proxy for a live broker quote rather than a second Webull call every
    tick. FALLBACK source="shadow_fallback" (no PAPER/LIVE broker activity recorded
    today at all, so there is nothing broker-side to compute from yet): the shadow
    book's own today realized+unrealized across every leg. Never raises."""
    try:
        today = _now_et().strftime("%Y-%m-%d")
        realized, any_broker_priced = _broker_realized_today(today, log=log)
        if any_broker_priced:
            unrl_by_leg = state.get("_unrl_by_leg") or {}
            open_legs = adapter.status().get("open_legs") or []
            unrealized = sum(float(unrl_by_leg.get(leg, 0.0) or 0.0) for leg in open_legs)
            return round(realized + unrealized, 2), "broker_fills"
    except Exception as e:
        log(f"[qqq-exec] broker-fill P&L calc failed ({type(e).__name__}: {e}) -- "
            "falling back to the shadow book's own today figures")
    shadow_realized = float(state.get("realized_pnl_today", 0.0) or 0.0)
    shadow_unrealized = sum((state.get("_unrl_by_leg") or {}).values())
    return round(shadow_realized + shadow_unrealized, 2), "shadow_fallback"


def _sync_broker_daily_pnl(state, adapter, nowdt, log=print):
    """Feeds api.webull_orders.OrderAdapter.update_daily_pnl() so its
    daily_loss_limit_usd rail (previously DEAD -- nothing ever called this) can
    actually trip. Resets once per ET trading day (adapter.reset_daily_pnl()), same
    boundary as the shadow book's own realized_pnl_today (_roll_day). Records the
    figure as an absolute "today's total" by pushing update_daily_pnl() a DELTA from
    the last value it pushed (tracked in state["_broker_pnl_tracked"]) -- update_daily_pnl
    only knows how to accumulate a delta, so this converges it to the freshly
    recomputed absolute total every tick rather than double-counting. Never raises."""
    try:
        today = nowdt.strftime("%Y-%m-%d")
        if state.get("_broker_pnl_day") != today:
            adapter.reset_daily_pnl()
            state["_broker_pnl_day"] = today
            state["_broker_pnl_tracked"] = 0.0
        pnl, source = _compute_broker_daily_pnl(state, adapter, log=log)
        prev = float(state.get("_broker_pnl_tracked", 0.0) or 0.0)
        delta = pnl - prev
        if abs(delta) > 1e-9:
            adapter.update_daily_pnl(delta)
        state["_broker_pnl_tracked"] = pnl
        state["_broker_pnl_source"] = source
    except Exception as e:
        log(f"[qqq-exec] broker daily P&L sync failed (non-fatal): {type(e).__name__}: {e}")


# -- broker reconcile scheduling (2026-09-14, FIX 2) ---------------------------------
_reconcile_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1,
                                                             thread_name_prefix="qqq-reconcile")


def _reconcile_with_timeout(adapter, log=print):
    """adapter.reconcile() bounded to RECONCILE_HARD_TIMEOUT_SEC wall-clock, same
    precaution as default_webull_quote's QUOTE_HARD_TIMEOUT_SEC (2026-09-03: this
    SDK's own connect/read timeouts are not reliably honoured on every call path --
    the runner's shadow thread once hung 10 hours inside get_snapshot). A timeout (or
    any other unexpected crash escaping reconcile()'s own guarded fetch) is treated
    exactly like reconcile()'s documented read-failure path: fail closed via
    adapter.fail_closed(), because reconcile() itself is guaranteed thread-safe (see
    OrderAdapter's own lock) even if the underlying network call is still running in
    the background after this function gives up waiting on it."""
    fut = _reconcile_executor.submit(adapter.reconcile)
    try:
        return fut.result(timeout=RECONCILE_HARD_TIMEOUT_SEC)
    except concurrent.futures.TimeoutError:
        reason = f"can't read positions at Webull: reconcile timed out after {RECONCILE_HARD_TIMEOUT_SEC:g}s"
        log(f"[qqq-exec] {reason} -- halting new broker entries")
        return adapter.fail_closed(reason)
    except Exception as e:
        reason = f"can't read positions at Webull: reconcile crashed ({type(e).__name__}: {e})"
        log(f"[qqq-exec] {reason} -- halting new broker entries")
        return adapter.fail_closed(reason)


def _maybe_run_broker_reconcile(state, cfg, adapter, nowdt, active, log=print):
    """Runs adapter.reconcile() (see api.webull_orders.OrderAdapter.reconcile's own
    docstring for what it checks and how it fails closed) -- at boot (see
    _reconcile_broker_at_boot, called once before the tick loop starts, independently
    of this scheduler), BROKER_RECONCILE_POST_ORDER_GRACE_SEC after the last broker
    order this process sent (state["_reconcile_due"] + ["_last_broker_send_at"], set by
    _mirror_to_broker below -- see the grace comment inline), and otherwise at most
    once every broker_reconcile_interval_min minutes while `active` (the tick loop's
    own 09:25-16:05 ET market window) -- never on the 5s tick cadence, to stay
    cache-friendly with Webull's rate limits. A pure no-op (no Webull call at all, see
    reconcile()'s own OFF-mode short-circuit) once effective_mode() is OFF."""
    try:
        mode, _ = adapter.effective_mode()
    except Exception as e:
        log(f"[qqq-exec] broker reconcile scheduling skipped (effective_mode failed): "
            f"{type(e).__name__}: {e}")
        return
    if mode not in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
        return  # OFF -- no broker to reconcile against, no network call, ever.

    due, why = False, None
    if state.get("_reconcile_due"):
        # LOOK AGAIN BEFORE PANICKING (2026-09-21): a fill that has not reached Webull's
        # positions yet reads as a mismatch, and reconcile() halts on a mismatch. So the
        # post-order look waits until the grace has passed since the LAST send -- and
        # returning here also holds the PERIODIC look off for that window, since a
        # periodic check landing mid-fill would false-halt exactly the same way. A
        # mismatch still there after the grace is real and halts as before. State
        # written before this field existed has no send time and runs at once.
        grace = max(0.0, _cfg_num(cfg, "broker_reconcile_post_order_grace_sec",
                                  BROKER_RECONCILE_POST_ORDER_GRACE_SEC))
        sent_at = float(state.get("_last_broker_send_at", 0) or 0)
        if time.time() - sent_at < grace:
            return
        due, why = True, "post-order"
    else:
        interval_sec = max(30.0, _cfg_num(cfg, "broker_reconcile_interval_min",
                                          BROKER_RECONCILE_INTERVAL_MIN) * 60.0)
        # HALTED RE-CHECK (2026-09-21): a reconcile halt blocks every leg's entries until
        # a later look agrees, and the next look used to be the 5-minute periodic one --
        # so a FALSE halt (Webull's positions lagging a fill) froze entries for up to 5
        # minutes, long enough to swallow NOISE's 09:45 buy. While this adapter's OWN
        # reconcile halt is on, look every broker_reconcile_halted_recheck_sec instead;
        # a kill-file halt is the owner's and waits for the file to go.
        try:
            halted, source, _reason = adapter.halt_state()
        except Exception:
            halted, source = False, None
        rechecking = bool(halted) and source == "reconcile"
        if rechecking:
            interval_sec = min(interval_sec, max(10.0, _cfg_num(
                cfg, "broker_reconcile_halted_recheck_sec", BROKER_RECONCILE_HALTED_RECHECK_SEC)))
        last = float(state.get("_last_broker_reconcile_at", 0) or 0)
        if active and time.time() - last >= interval_sec:
            due, why = True, ("halted re-check" if rechecking else "periodic")
    if not due:
        return

    state["_reconcile_due"] = False
    state["_last_broker_reconcile_at"] = time.time()
    result = _reconcile_with_timeout(adapter, log=log)
    if result is None:
        return
    if result.get("ok"):
        log(f"[qqq-exec] broker reconcile OK ({why})")
    else:
        reason = result.get("error") or result.get("mismatches")
        kind = "READ FAILURE" if result.get("error") else "MISMATCH"
        log(f"[qqq-exec] BROKER RECONCILE {kind} ({why}) -- new broker entries "
            f"halted: {reason}")
        _log_event(state, "broker_reconcile_halt",
                  f"Broker reconcile {kind.lower()} -- new broker entries halted: {reason}",
                  log=log)


def _run_broker_housekeeping(state, cfg, nowdt, active, log=print):
    """ONE consolidated _get_broker_adapter() call per tick feeding both the daily P&L
    wiring and the reconcile scheduler above -- kept as a single call site so adding
    these two independent, Firestore-free concerns doesn't multiply how many times
    tick() touches the broker adapter singleton. Never raises."""
    try:
        adapter = _get_broker_adapter(log=log)
    except Exception as e:
        log(f"[qqq-exec] broker housekeeping skipped (adapter unavailable): "
            f"{type(e).__name__}: {e}")
        return
    _sync_broker_daily_pnl(state, adapter, nowdt, log=log)
    _maybe_run_broker_reconcile(state, cfg, adapter, nowdt, active, log=log)


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


# A quote CALL that worked but whose newest print is older than QUOTE_MAX_AGE_SEC. This is
# NOT a failure -- it is the normal state before the opening auction and in any thin patch --
# so it must never trip the failure breaker (see default_webull_quote).
QUOTE_STALE = "stale"


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
    if res is QUOTE_STALE:
        # No usable price this tick, but the path is healthy: do not disable it, and do not
        # cache it as a quote. Logged once per market-state change rather than every tick.
        if not qs.get("stale_warned"):
            log("[qqq-exec] Webull quote is live but its newest print is older than "
                f"{QUOTE_MAX_AGE_SEC:g}s (normal before the open) -- no quote pricing yet")
            qs["stale_warned"] = True
        return None
    qs["stale_warned"] = False
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
        # TOKEN (2026-09-09): MarketData(api) does NOT authenticate the client. Only
        # ClientInitializer.initializer() mints and attaches the x-access-token, and the
        # SDK runs it inside TradeClient/DataClient constructors -- never inside
        # MarketData. Building MarketData on a bare ApiClient therefore sent every
        # market-data request with NO token and got back
        #   401 INVALID_TOKEN "Header x-access-token is missing or invalid"
        # which this function swallowed as "no entitlement" and fell back to the NQ ratio.
        # So this path had NEVER worked. (The 403 MARKET_DATA_NOT_SUBSCRIBED seen while
        # spiking was a red herring: that script happened to build a TradeClient on the
        # same ApiClient first, which initialised it.) Initialise explicitly here.
        from webull.core.http.initializer.client_initializer import ClientInitializer
        ClientInitializer.initializer(api)
        md = MarketData(api)
        for cat in (Category.US_ETF, Category.US_STOCK):
            try:
                resp = md.get_snapshot([symbol], cat)
            except Exception:
                resp = None
            if not resp:
                continue
            # SHAPE (2026-09-09): get_snapshot returns an HTTP RESPONSE, not a model --
            # the payload is a JSON list of plain dicts. The old getattr() reads returned
            # None against a dict even when a perfectly good quote was in hand, so this
            # was a second, independent reason the path could never price a fill.
            try:
                body = resp.json() if hasattr(resp, "json") else resp
            except Exception:
                continue
            item = body[0] if isinstance(body, list) and body else body
            if not isinstance(item, dict):
                continue
            price = item.get("close") or item.get("price") or item.get("last_price")
            # epoch MILLISECONDS on this feed; last_trade_time is the print we care about
            ts = (item.get("last_trade_time") or item.get("quote_time")
                  or item.get("trade_time") or item.get("timestamp"))
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
                # STALE, NOT BROKEN (2026-09-11). Returning None here put this down as a
                # failure and disabled the whole quote path for 30 minutes. Before the open
                # the newest print is always hours old, so the adapter tripped its own
                # breaker pre-market and then refused to even ASK for a quote until 30
                # minutes into the session -- which, with the NinjaTrader feed also dead,
                # left the price rail blocking entries on the first clean-coverage day.
                return QUOTE_STALE
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


def _build_ratio_health(state, nowdt, cfg=None, log=print):
    """{current,at,source,age_min,mean_20,drift_pct,band_lo,band_hi,warn,used,note} --
    see module docstring feature (3). Every shadow fill priced off the nq_ratio path is
    biased by however stale/drifted this ratio is, so this block is what lets the owner
    (and the web tab) tell a healthy calibration from one quietly going bad.

    NOT USED IN ENGINE MODE (2026-09-23, "HONEST WARNINGS" item 1a). resolve_price/
    the nq_ratio px_source are NinjaTrader-mode-only (see that function's own docstring
    and _engine_mark_price, which never touches the ratio at all -- in engine mode "no
    price uses that ratio" is not a special case to detect, it is simply true by
    construction every tick). A calibration can therefore sit there stale/drifted
    forever in engine mode and it would never bias a single real price, so warning on
    it (the RATIO DRIFT chip) was a false alarm. `used` is False whenever
    `cfg["signal_source"]` is "engine" (same default as _build_price_status) --
    unconditionally, no drift/staleness math even attempted -- and this returns
    `warn=False` plus a plain "not used" note instead. NinjaTrader mode keeps EXACTLY
    today's behaviour, unconditionally -- this function does not change its read for
    that mode at all."""
    try:
        engine_mode = str((cfg or {}).get("signal_source") or "engine").strip().lower() == "engine"
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
        base = {"current": current, "at": at, "source": source, "age_min": age_min,
               "mean_20": mean_20, "drift_pct": drift_pct, "band_lo": band_lo, "band_hi": band_hi}
        if engine_mode:
            base.update(warn=False, used=False,
                       note="not used -- prices come straight from Webull")
            return base
        # NinjaTrader mode below -- unchanged from before this fix.
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
        base.update(warn=bool(warn), used=True, note="; ".join(notes))
        return base
    except Exception as e:
        log(f"[qqq-exec] ratio_health build failed: {type(e).__name__}: {e}")
        return {"current": None, "at": None, "source": None, "age_min": None,
               "mean_20": None, "drift_pct": None, "band_lo": None, "band_hi": None,
               "warn": False, "used": None, "note": f"ratio_health unavailable: {type(e).__name__}"}


def resolve_price(cfg, state, nq_px, quote_fn, ratio_fn, log=print):
    """(qqq_px, source) for one fill/mark, or (None, None) if nothing can price it.
    NinjaTrader-mode pricing only -- see _engine_mark_price for signal_source='engine'."""
    q = quote_fn(log=log) if quote_fn else None
    if q is not None:
        price, _age = q
        return float(price), "webull_quote"
    calib = _maybe_calibrate(state, ratio_fn, log=log)
    if calib and calib.get("ratio"):
        return float(nq_px) / float(calib["ratio"]), "nq_ratio"
    return None, None


# -- ENGINE MODE (2026-09-13) ---------------------------------------------------------
# Everything below reads ONLY api/cloud_signal.py's own on-disk cache/signals.csv/
# state.json/heartbeat.json -- never fills.csv, never the NQ 10s export, never
# default_webull_quote/default_ratio_calibration. That is the whole point of this mode.
def _cs_module():
    """Lazy import of api.cloud_signal -- avoids paying its heavier import chain
    (augur_engine.engine, tools.qqq_paper) for every ninjatrader-mode run that never
    touches it, and keeps this module importable even if cloud_signal briefly breaks."""
    from . import cloud_signal as cs
    return cs


def _check_feed_engine(state, log=print):
    """engine mode's equivalent of _check_feed: staleness of api.cloud_signal's OWN
    heartbeat (its parallel-run thread inside api/runner.py) -- never opens fills.csv
    or addon_heartbeat.json. One heartbeat covers both signal and price freshness in
    this mode (cloud_signal ticks its bar fetch and its signal diff together), unlike
    NinjaTrader mode's two independent feeds."""
    stale = True
    try:
        cs = _cs_module()
        hb_path = cs.DEFAULT_PATHS["heartbeat_path"]
        if os.path.exists(hb_path):
            with open(hb_path, encoding="utf-8") as f:
                hb = json.load(f)
            ts = datetime.fromisoformat(str(hb.get("ts")))
            now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
            age = (now - ts).total_seconds()
            stale = age > ENGINE_HEARTBEAT_STALE_SEC or not hb.get("ok", True)
        else:
            log("[qqq-exec] engine heartbeat not published yet -- treating feed as stale")
    except Exception as e:
        log(f"[qqq-exec] engine heartbeat check failed: {type(e).__name__}: {e}")
        stale = True
    was = state.get("feed_stale", False)
    state["feed_stale"] = stale
    if stale and not was:
        _log_event(state, "feed_down",
                  "cloud_signal engine heartbeat stale/missing -- new entries blocked", log=log)
    elif was and not stale:
        log("[qqq-exec] engine heartbeat recovered")
        state["relaunch_at"] = _now_et().strftime("%Y-%m-%d %H:%M:%S")
        _log_event(state, "feed_up", "cloud_signal engine heartbeat recovered", log=log)
    return stale


def _engine_key_for_leg(leg, cs=None):
    """Reverse ENGINE_LEG_MAP: which cloud_signal engine key currently backs this EXEC
    leg, for the two call sites (_engine_mark_price, _engine_confirms_entry) that need to
    go from the EXEC leg BACK to an engine key rather than forward.

    WHY THIS CANNOT BE A PLAIN next(...) OVER ENGINE_LEG_MAP.items() (2026-09-24). A leg
    swap keeps the RETIRED engine key in ENGINE_LEG_MAP (see its own comment -- an old
    ledger row or in-flight trade id must keep resolving), so by design more than one
    engine key can map to the same EXEC leg at once ("NOISE_304" and "NOISE_382" both ->
    "NOISE" today). cloud_signal.CROWN_LEGS, though, holds only the LIVE key -- the
    retired one is REPLACED there, not kept alongside -- so whichever mapped key a naive
    first-match lookup happens to hit first can easily be the retired one, find nothing in
    CROWN_LEGS, and silently read as "this leg's cache is empty". That is not hypothetical:
    it is exactly what plain dict-order iteration would have hit here the day NOISE_304
    was replaced by NOISE_382, and it would have zeroed the live NOISE leg's mark price
    (unrealized P&L, EOD/breaker flatten, orphan-broker repair all call _engine_mark_price).

    So this prefers a mapped key that IS present in CROWN_LEGS (the live one) and only
    falls back to the first mapped key at all when NONE of them are (every mapped key for
    this leg has been retired -- callers already treat a missing CROWN_LEGS entry as "no
    price available", so this never raises)."""
    cs = cs or _cs_module()
    keys = [k for k, short in ENGINE_LEG_MAP.items() if short == leg]
    for k in keys:
        if k in cs.CROWN_LEGS:
            return k
    return keys[0] if keys else None


def _engine_mark_price(leg, log=print):
    """(qqq_px, source) for marking/closing an OPEN leg when signal_source == 'engine' --
    the newest CLOSED bar close from api.cloud_signal's own on-disk cache (Webull bar if
    that is what produced it, else yfinance -- see cloud_signal.read_bar_source), never
    NQ. (None, None) if that leg's cache is empty -- callers then leave the lot
    unmarked/unclosed, exactly like NinjaTrader mode's 'no quote/ratio available' case."""
    try:
        cs = _cs_module()
        cs_key = _engine_key_for_leg(leg, cs)
        cfg_leg = cs.CROWN_LEGS.get(cs_key) if cs_key else None
        if not cfg_leg:
            return None, None
        tf = cfg_leg["timeframe"]
        df = cs.load_cached_bars(tf, cs.DEFAULT_PATHS)
        if df is None or not len(df):
            return None, None
        last = df.sort_values("time").iloc[-1]
        px = float(last["close"])
        src_info = (cs.read_bar_source(cs.DEFAULT_PATHS) or {}).get(tf) or {}
        src = "engine_" + (src_info.get("source") or "cache")
        return px, src
    except Exception as e:
        log(f"[qqq-exec] engine mark price failed for {leg}: {type(e).__name__}: {e}")
        return None, None


def _leg_timeframe_seconds(leg, log=print):
    """Seconds in ONE bar of this EXEC leg's own LIVE engine timeframe (ORB/NOISE 5m,
    ENGUQ 1m today) -- read from api.cloud_signal.CROWN_LEGS via _engine_key_for_leg/
    ENGINE_LEG_MAP, never hard-coded, so a future leg swapped onto a different
    timeframe (like the 2026-09-24 NOISE_304 -> NOISE_382 swap) is picked up here
    automatically. None for a leg with no live engine mapping."""
    try:
        cs = _cs_module()
        cs_key = _engine_key_for_leg(leg, cs)
        cfg_leg = cs.CROWN_LEGS.get(cs_key) if cs_key else None
        if not cfg_leg:
            return None
        return cs.TIMEFRAME_SECONDS.get(cfg_leg["timeframe"])
    except Exception as e:
        log(f"[qqq-exec] leg timeframe lookup failed for {leg}: {type(e).__name__}: {e}")
        return None


def _bar_close_age(timeframe, bar_source=None, log=print):
    """Seconds since the newest bar of `timeframe` ('1m'/'5m') actually CLOSED, or
    None if no bar has been attributed for that timeframe yet.

    THE BAR-START BUG (2026-09-23, "HONEST WARNINGS" items 1b/1c). api.cloud_signal.
    read_bar_source()'s own `newest_epoch` is the bar's OPENING instant (see that
    module's _closed_cutoff_epoch: bars are filtered on `time <= now - grace -
    timeframe`, i.e. `time` is the bar START) -- ageing a status line directly off it
    reads a bar that just closed as still "~300s behind" for the next 5 minutes, which
    is exactly the "PRICE SOURCE WEBULL 389s behind" reading the owner saw on a feed
    that was, in fact, current. This adds back that leg's own timeframe before ageing.

    `bar_source`: a caller that already has a read_bar_source() dict this tick (e.g.
    _build_price_status, scanning every timeframe for the freshest one) passes it
    straight through instead of triggering a second state.json read; omitted, this
    reads it itself."""
    try:
        cs = _cs_module()
        bs = bar_source if bar_source is not None else (cs.read_bar_source(cs.DEFAULT_PATHS) or {})
        info = bs.get(timeframe)
        if not info or info.get("newest_epoch") is None:
            return None
        tf_sec = cs.TIMEFRAME_SECONDS.get(timeframe, 0)
        return max(0.0, time.time() - (float(info["newest_epoch"]) + tf_sec))
    except Exception as e:
        log(f"[qqq-exec] bar close age calc failed for {timeframe}: {type(e).__name__}: {e}")
        return None


def _relaunch_recently(state, cfg, f_dt):
    """True if `f_dt` falls within startup_guard_minutes of the last recorded relaunch
    (adapter process boot, or the NinjaTrader fill-feed heartbeat recovering after a
    stale spell -- see tick()'s boot handling and _check_feed's feed_up branch, both of
    which stamp state['relaunch_at'])."""
    at = state.get("relaunch_at")
    if not at:
        return False
    try:
        at_dt = datetime.strptime(at, "%Y-%m-%d %H:%M:%S")
        f_cmp = f_dt.replace(tzinfo=None) if f_dt.tzinfo else f_dt
        guard_sec = float(cfg.get("startup_guard_minutes", 5) or 5) * 60.0
        delta = (f_cmp - at_dt).total_seconds()
        return 0 <= delta <= guard_sec
    except Exception:
        return False


def _engine_confirms_entry(leg, f_dt, tolerance_sec=180):
    """Best-effort: does api.cloud_signal's OWN signal ledger show an ENTRY for the
    mapped engine leg within `tolerance_sec` of this NinjaTrader fill's timestamp? Used
    only to decide whether a startup-window fill (_relaunch_recently) is a real signal
    or relaunch noise. An unmapped leg or an unreadable ledger both read as 'not
    confirmed' -- conservative, matching the task: ignore what the engine doesn't back."""
    try:
        cs = _cs_module()
        cs_key = _engine_key_for_leg(leg, cs)
        if cs_key is None:
            return False
        sig_path = cs.DEFAULT_PATHS["signals_path"]
        if not os.path.exists(sig_path):
            return False
        with open(sig_path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        f_cmp = f_dt.replace(tzinfo=None) if f_dt.tzinfo else f_dt
        for r in rows:
            if r.get("leg") != cs_key or str(r.get("event") or "").upper() != "ENTRY":
                continue
            rt = datetime.fromisoformat(str(r["ref_time"]))
            rt_cmp = rt.replace(tzinfo=None) if rt.tzinfo else rt
            if abs((rt_cmp - f_cmp).total_seconds()) <= tolerance_sec:
                return True
    except Exception:
        return False
    return False


def _consume_engine_signals(state, cfg, now, log=print):
    """engine mode's fill source: NEW rows appended to api.cloud_signal's own
    signals.csv since the last tick, consumed via a row-count CURSOR persisted in THIS
    adapter's OWN state.json (state['engine_cursor']) -- never cloud_signal's own
    idempotency state, which belongs to a different process (the runner's parallel-run
    thread) and must not gain a second writer.

    COLD START / FIRST ACTIVATION: if this adapter has never run in engine mode before
    (no cursor yet), the cursor is set to the CURRENT end of signals.csv and nothing is
    processed this call -- exactly cloud_signal's own SEED rule, so flipping
    signal_source to 'engine' never replays days of accumulated history as fresh
    trades. A normal restart resumes from the saved cursor, so it never re-enters or
    re-exits anything already consumed either.

    STALE BY CONSUMPTION LAG: a row consumed long after it was emitted (this adapter,
    or cloud_signal, was down) is recorded -- the cursor still advances, it is never
    reprocessed -- but not acted on if `emitted_at` is more than
    ENGINE_CONSUME_STALE_SEC old. This is a DIFFERENT guard from cloud_signal's own
    'never emit an hours-late entry' rule (that one already keeps a signal from being
    emitted hours after the bar that justified it); this one covers the adapter itself
    having been offline when an otherwise-timely signal was emitted.

    Returns the ENTRY/EXIT event dicts to route this tick (SEED and any other
    non-actionable event types are skipped). Each carries the row's `trade_id` ("" on a
    row written before the column existed).

    CURSOR KEPT (2026-09-14). Trade ids did NOT replace this row cursor: which rows are new
    is still decided by row number in THIS host's own ledger. The ids decide what a row may
    do once consumed (see _route_engine_events). A consumed-trade-id set -- the piece a
    two-host takeover needs, since each host's ledger has its own row numbers -- is a
    separate change."""
    cs = _cs_module()
    sig_path = cs.DEFAULT_PATHS["signals_path"]
    try:
        if not os.path.exists(sig_path):
            # cloud_signal hasn't ticked even once yet (a startup race, not the normal
            # case -- it already runs as its own runner thread). Arm the cursor at 0
            # rather than leaving it unset, so once the ledger DOES appear its rows are
            # treated as genuinely new instead of being cold-start-absorbed a second time.
            if state.get("engine_cursor") is None:
                state["engine_cursor"] = 0
            return []
        with open(sig_path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log(f"[qqq-exec] engine signals read failed: {type(e).__name__}: {e}")
        return []

    cursor = state.get("engine_cursor")
    if cursor is None:
        state["engine_cursor"] = len(rows)
        log(f"[qqq-exec] signal_source=engine activated -- seeded cursor at {len(rows)} "
            f"existing row(s), nothing replayed")
        _log_event(state, "engine_seed",
                  f"signal_source=engine activated; {len(rows)} pre-existing signal "
                  f"row(s) absorbed without acting on them", log=log)
        return []

    if len(rows) < int(cursor):
        # SHORT READ (2026-09-14): fewer rows than this adapter already consumed. Either the
        # read landed inside another process's in-place rewrite of the ledger (a pre-trade-id
        # cloud_signal still rewrites its header that way) or the ledger really was replaced
        # by a shorter one. Dropping the cursor to a torn read's row count would re-consume up
        # to ENGINE_CONSUME_STALE_SEC of signals on the next tick, so the cursor holds; only a
        # shortage seen on ENGINE_SHORT_READ_TICKS consecutive reads is taken as a replaced
        # ledger and re-armed at its end, with nothing replayed.
        n = int(state.get("_engine_short_reads", 0) or 0) + 1
        state["_engine_short_reads"] = n
        if n < ENGINE_SHORT_READ_TICKS:
            log(f"[qqq-exec] signals.csv read {len(rows)} row(s), fewer than the {cursor} already "
                f"consumed -- cursor held (short read {n} of {ENGINE_SHORT_READ_TICKS})")
            return []
        _log_event(state, "engine_reseed",
                   f"signal ledger shrank from {cursor} to {len(rows)} rows for {n} reads in a row "
                   f"-- treated as replaced; cursor re-armed at its end, nothing replayed", log=log)
        state["engine_cursor"] = len(rows)
        state["_engine_short_reads"] = 0
        return []
    state["_engine_short_reads"] = 0

    new_rows = rows[int(cursor):]
    state["engine_cursor"] = len(rows)
    if not new_rows:
        return []

    out = []
    for r in new_rows:
        ev = str(r.get("event") or "").strip().upper()
        if ev not in ("ENTRY", "EXIT"):
            continue  # SEED and any future non-actionable event types
        age = None
        try:
            emitted = datetime.fromisoformat(str(r["emitted_at"]))
            now_cmp = now.replace(tzinfo=None) if now.tzinfo else now
            emitted_cmp = emitted.replace(tzinfo=None) if emitted.tzinfo else emitted
            age = (now_cmp - emitted_cmp).total_seconds()
        except Exception:
            age = None
        if age is not None and age > ENGINE_CONSUME_STALE_SEC:
            log(f"[qqq-exec] engine {ev} {r.get('leg')} consumed {age/60:.0f} min after "
                f"it was emitted -- too stale to act on, recorded only")
            _log_event(state, "engine_stale_skip",
                      f"{r.get('leg')} {ev} skipped -- consumed {age/60:.0f} min late", log=log)
            continue
        try:
            out.append({"leg": r["leg"], "event": ev, "side": r.get("side") or "long",
                       "ref_time": r["ref_time"], "ref_price": float(r["ref_price"]),
                       "bar_source": r.get("bar_source") or "",
                       # "" for a row written before cloud_signal wrote trade ids -- see
                       # _route_engine_events' OLD ROWS rule for what that means
                       "trade_id": str(r.get("trade_id") or "").strip(),
                       # SIZE ORDERS (2026-09-23): raw signals.csv value, unparsed --
                       # "" on SEED rows, on any row written before the "size" column
                       # existed, and on an EXIT (cloud_signal writes the entry's size
                       # there too, but only an ENTRY's size ever reaches _open_lot;
                       # see _route_engine_events). _resolve_entry_size (api/qqq_exec.py)
                       # is the one place this is turned into a number, at the point of
                       # use, exactly like ref_price is parsed above.
                       "size": r.get("size")})
        except Exception as e:
            log(f"[qqq-exec] engine event row malformed, skipped: {type(e).__name__}: {e}")
    return out


# -- TRADE IDENTITY (2026-09-14) -----------------------------------------------------------
# Everything _route_engine_events declines to act on because a row's trade identity did not
# check out, by kind. Counted today + all time in state["trade_id_checks"] and published
# whole (zeros included) under doc["trade_ids"]; each one is also a runner.log WARN line and
# an event-timeline entry of the same kind.
TRADE_ID_ISSUES = (
    "exit_id_mismatch",     # EXIT's trade id is not the open lot's (or the lot has none): nothing closed
    "exit_no_id",           # EXIT row with no trade id while a lot is open: nothing closed
    "exit_no_lot",          # EXIT with no open lot on that leg: nothing to close
    "entry_no_id",          # ENTRY row with no trade id: not taken
    "entry_id_conflict",    # ENTRY row's trade id disagrees with its own leg/bar time/side: not taken
    "entry_other_session",  # ENTRY bar is not from today's session (replay leftovers): not taken
    "entry_duplicate",      # ENTRY for the very trade already open: ignored
    "entry_leg_busy",       # ENTRY for a different trade while a lot is open on the leg: not taken
)
# Bookkeeping rather than a refused signal -- left out of the published refused_today sum.
_TRADE_ID_INFO_ONLY = ("exit_no_lot", "entry_duplicate")


def _record_trade_id_issue(state, kind, text, nowdt=None, detail=None, log=print):
    """Count one identity problem (today + all time), keep the latest one's details, and
    write the runner.log line and the timeline event. Never raises."""
    try:
        blk = state.setdefault("trade_id_checks", {})
        day = (nowdt or _now_et()).strftime("%Y-%m-%d")
        if blk.get("day") != day:
            blk["day"] = day
            blk["today"] = {}
        today = blk.setdefault("today", {})
        today[kind] = int(today.get(kind, 0) or 0) + 1
        total = blk.setdefault("total", {})
        total[kind] = int(total.get(kind, 0) or 0) + 1
        last = {"kind": kind, "ts_et": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "text": text}
        for k, v in (detail or {}).items():
            last[k] = v if (v is None or isinstance(v, (str, int, float, bool))) else str(v)
        blk["last"] = last
    except Exception as e:
        log(f"[qqq-exec] trade-id issue count failed: {type(e).__name__}: {e}")
    log(f"[qqq-exec] WARN {kind}: {text}")
    _log_event(state, kind, text, log=log)


def _build_trade_id_status(state, day=None):
    """doc["trade_ids"]: flat per-kind counters for `day` (the adapter's trading_day) and
    for all time, the refused-today total, and the latest issue."""
    blk = state.get("trade_id_checks") or {}
    day = day or _now_et().strftime("%Y-%m-%d")
    today_raw = (blk.get("today") or {}) if blk.get("day") == day else {}
    today = {k: int(today_raw.get(k, 0) or 0) for k in TRADE_ID_ISSUES}
    total = {k: int((blk.get("total") or {}).get(k, 0) or 0) for k in TRADE_ID_ISSUES}
    return {"day": day, "today": today, "total": total,
            "refused_today": sum(v for k, v in today.items() if k not in _TRADE_ID_INFO_ONLY),
            "last": blk.get("last")}


def _lot_label(lot):
    tid = (lot or {}).get("trade_id")
    if tid:
        return _trade_id.describe(tid, _NY)
    return f"opened {(lot or {}).get('entry_ts')} (no trade id -- predates trade ids)"


def _route_engine_events(state, cfg, events, entries_blocked, log=print, now=None):
    """engine mode's equivalent of _route_fills: consumes api.cloud_signal ENTRY/EXIT
    events (already idempotent and de-duplicated by _consume_engine_signals' cursor)
    and opens/closes shadow lots directly from the engine's own signal price -- no
    NinjaTrader fill, no NQ ratio, no Webull quote call. Each cloud_signal trade is
    single-shot (one ENTRY, one EXIT, no partials -- see run_leg_trades), so an EXIT
    always closes the WHOLE lot.

    TRADE IDENTITY (2026-09-14, tools/qqq_failover_sim.py scenario F). A lot carries the
    trade id (api/trade_id.py: leg + entry bar time + side) of the ENTRY row that opened it,
    and an EXIT closes a lot ONLY when the EXIT row carries that same id. It used to close
    whatever lot was open on the leg, because EXIT rows had no entry identity: on
    2026-09-14 at 09:31 ET the live ledger delivered an EXIT for a 2026-09-03 NOISE trade
    (left behind by a replay that wrote into the live ledger). No lot was open; had one
    been, today's lot would have closed at the old trade's price -- and mirrored a real
    SELL once the broker is armed. A row whose identity does not check out is NOT applied:
    it is counted, logged and published -- see TRADE_ID_ISSUES.

    OLD ROWS (no trade_id: written by a cloud_signal that predates the column -- a runner
    not yet restarted onto this code, or a replay run from a stale checkout) are never
    acted on. An id-less EXIT closes nothing: the lot waits for its own EXIT or for the
    flat-by / breaker / kill close. An id-less ENTRY opens nothing either: its EXIT could
    not be matched, so the lot could only ever close on those rails. Deliberately stricter
    than pairing by leg: a refused signal is a visible, explainable gap, while a lot closed
    by another trade's exit is a wrong trade. Restart the runner (cloud_signal) together
    with this adapter.

    An ENTRY whose bar is not from today's session is refused as well. cloud_signal's live
    run never emits one (its STALE rule), so such a row is replay debris -- the same replay
    also left 2026-09-03 ENTRY rows in the live ledger.

    A lot opened before trade ids existed (state.json lot without trade_id) cannot be
    matched by any EXIT and closes only on the flat-by / breaker / kill rails -- and while it
    is open, every new ENTRY on that leg is refused as leg-busy. So switch a running adapter
    onto this code (or switch signal_source from ninjatrader to engine) only while it is flat.

    Identity refusals are not added to the fired/refused signal counters: this adapter cannot
    show such a row is one of today's strategy signals, only that it cannot be attributed."""
    nowdt = now or _now_et()
    today = nowdt.strftime("%Y-%m-%d")
    for e in events:
        leg = ENGINE_LEG_MAP.get(e["leg"])
        if leg is None:
            continue  # a cloud_signal leg this module doesn't (yet) mirror
        try:
            sig_dt = datetime.fromisoformat(str(e["ref_time"]))
            if sig_dt.tzinfo is None and _NY is not None:
                sig_dt = sig_dt.replace(tzinfo=_NY)
        except Exception:
            sig_dt = None
        px_source = "engine_" + (str(e.get("bar_source") or "cache"))
        row_tid = str(e.get("trade_id") or "").strip()
        open_lot = state["legs"].get(leg)
        detail = {"leg": leg, "event": e["event"], "row_trade_id": row_tid,
                  "ref_time": str(e.get("ref_time") or ""),
                  "lot_trade_id": (open_lot or {}).get("trade_id")}
        if e["event"] == "ENTRY":
            if not row_tid:
                _record_trade_id_issue(
                    state, "entry_no_id",
                    f"{leg} entry signal ({e.get('side')}, bar {e.get('ref_time')}) has no trade id "
                    f"-- written by a signal engine that predates trade ids; not taken",
                    nowdt, detail, log=log)
                continue
            own_tid = _trade_id.make(e["leg"], e.get("ref_time"), e.get("side"), default_tz=_NY)
            if own_tid != row_tid:
                _record_trade_id_issue(
                    state, "entry_id_conflict",
                    f"{leg} entry signal's trade id {row_tid} does not match its own bar time and "
                    f"side ({own_tid or 'unreadable'}); not taken", nowdt, detail, log=log)
                continue
            entry_day = None
            if sig_dt is not None:
                entry_day = (sig_dt.astimezone(_NY) if _NY is not None else sig_dt).strftime("%Y-%m-%d")
            if entry_day != today:
                _record_trade_id_issue(
                    state, "entry_other_session",
                    f"{leg} entry signal is for {_trade_id.describe(row_tid, _NY)}, not today's "
                    f"session ({today}) -- replay leftovers, not taken", nowdt, detail, log=log)
                continue
            if open_lot:
                if open_lot.get("trade_id") == row_tid:
                    _record_trade_id_issue(
                        state, "entry_duplicate",
                        f"{leg} entry signal repeats the trade already open "
                        f"({_trade_id.describe(row_tid, _NY)}); ignored", nowdt, detail, log=log)
                else:
                    _record_trade_id_issue(
                        state, "entry_leg_busy",
                        f"{leg} entry signal for {_trade_id.describe(row_tid, _NY)} while the "
                        f"shadow trade {_lot_label(open_lot)} is still open; not taken",
                        nowdt, detail, log=log)
                continue
            shares = int(cfg["shares"].get(leg, 0))
            if entries_blocked:
                _record_order(leg, "ENTER", e["side"], shares, None, None, None,
                             "REFUSED -- breaker/feed/kill blocked", log, fill_dt=sig_dt,
                             signal_source=cfg.get("signal_source"))
                _accumulate_signal(state, sig_dt or _now_et(), leg, "fired", log=log)
                _accumulate_signal(state, sig_dt or _now_et(), leg, "refused", log=log)
                continue
            if shares <= 0:
                continue
            state["_px_source"] = px_source
            opened = _open_lot(state, cfg, leg, e["side"], shares, None, float(e["ref_price"]),
                               cfg.get("slippage_per_share", 0.0), f=None, log=log,
                               sig_dt=sig_dt, signal_source=cfg.get("signal_source"),
                               trade_id=row_tid, entry_ref_time=str(e.get("ref_time") or ""),
                               size=e.get("size"), keel_size=e.get("keel_size"))
            _accumulate_signal(state, sig_dt or _now_et(), leg, "fired", log=log)
            _accumulate_signal(state, sig_dt or _now_et(), leg, "taken" if opened else "refused", log=log)
        elif e["event"] == "EXIT":
            lot = open_lot
            exit_of = (_trade_id.describe(row_tid, _NY) if row_tid
                       else f"a trade with no id (exit bar {e.get('ref_time')})")
            if not lot:
                # Starts with the pre-2026-09-14 wording verbatim: tools/qqq_failover_sim.py
                # and docs/CLOUD_SIGNAL_REPAIR_20260914.md's verification grep for it.
                _record_trade_id_issue(
                    state, "exit_no_lot",
                    f"engine EXIT for {leg} with no open shadow lot -- skipped ({exit_of}; "
                    f"nothing to close)", nowdt, detail, log=log)
                continue
            if not row_tid:
                _record_trade_id_issue(
                    state, "exit_no_id",
                    f"{leg} strategy exit (bar {e.get('ref_time')}) has no trade id, so it cannot be "
                    f"matched to the open shadow trade {_lot_label(lot)}; nothing closed -- that "
                    f"trade waits for its own exit or the end-of-day close", nowdt, detail, log=log)
                continue
            if row_tid != lot.get("trade_id"):
                _record_trade_id_issue(
                    state, "exit_id_mismatch",
                    f"{leg} strategy exit belongs to {exit_of}, but the open shadow trade is "
                    f"{_lot_label(lot)}; nothing closed", nowdt, detail, log=log)
                continue
            state["_px_source"] = px_source
            _reduce_lot(state, cfg, leg, lot["nq_qty_total"], None, float(e["ref_price"]),
                       cfg.get("slippage_per_share", 0.0), "signal exit", f=None, log=log,
                       sig_dt=sig_dt, signal_source=cfg.get("signal_source"))


def _apply_slippage(px, side, entering, slip):
    """slippage always moves the fill AGAINST us: worse price on entry, worse on exit."""
    buying = (side == "long") == entering  # buying to open long, or buying to cover short
    return px + slip if buying else px - slip


# -- lot lifecycle ---------------------------------------------------------------------
# SIZE ORDERS (2026-09-23, the order-side half of the run #382 NOISE_1_8_CT304 / later
# KEEL prerequisite -- see api/cloud_signal.py's per-trade size contract and SIGNAL_COLS'
# "size" column). These two helpers are the ONLY place a signal's size becomes an order
# quantity; everything downstream of _open_lot (the lot dict, _reduce_lot, _mirror_to_broker,
# the resend queue, deferred fill capture, book-only) reads shares_total/shares_remaining
# off the lot itself and never recomputes from cfg or size again.
def _resolve_entry_size(raw):
    """The per-trade size multiplier an engine ENTRY signal may carry. None, an empty/
    blank string, anything that does not parse as a number, and any non-positive or
    non-finite value all resolve to 1.0 -- unsized, exactly an old ledger row written
    before signals.csv grew its "size" column. This is the ONLY input that can move the
    OPEN quantity away from the leg's plain configured share count (see
    _sized_shares), so a value that cannot be trusted must fall back to "unsized",
    never to a guess."""
    if raw is None:
        return 1.0
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return 1.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(v) or v <= 0:
        return 1.0
    return v


def _resolve_keel_size(raw):
    """The KEEL multiplier ALONE, for DISPLAY only (see _open_lot's docstring and
    TRADE_COLS' own comment) -- unlike _resolve_entry_size above, this never affects an
    order quantity, so a value that cannot be trusted degrades to None (rendered as ""
    on the trade row) rather than a guessed number: None/blank/unparseable/non-finite
    all mean "nothing meaningful to show", never "1.0" (a real 1.0 is a real KEEL
    result -- overlay ran and stood down -- and must stay visibly different from "no
    overlay data")."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _sized_shares(base_shares, size):
    """The WANTED order quantity: `base_shares` (the leg's configured share count,
    cfg["shares"][leg]) scaled by `size` (see _resolve_entry_size), rounded to the
    nearest share and floored at 1 -- never at 0, so a valid size that happens to round
    down does not silently vanish the trade. A leg configured at 0 shares (owner-
    disabled) is left at 0: zero times any size is still zero, and the caller's own
    pre-existing `shares <= 0` skip must still see a real zero, not a phantom 1-share
    order for a leg the owner turned off."""
    if base_shares <= 0:
        return 0
    return max(1, int(round(base_shares * size)))


def _open_lot(state, cfg, leg, side, nq_qty, nq_px, qqq_px_raw, slip, f=None, log=print,
              sig_dt=None, signal_source=None, trade_id=None, entry_ref_time=None, size=None,
              keel_size=None):
    """Returns True if a shadow lot opened, False if refused/skipped (feature #55 needs
    to know this to tell TAKEN from REFUSED).

    `keel_size` (2026-09-23): the KEEL multiplier ALONE from the ENTRY signal's own
    "keel_size" column (blank/None for a leg with no KEEL overlay, or an older row) --
    stored on the lot purely for display (see TRADE_COLS's own comment); it plays no
    part in sizing the order, which is already folded into `size` above.

    `f` is a NinjaTrader-fill-shaped dict (ninjatrader mode) or None (engine mode --
    there is no NT fill to mirror, exactly like a rail-driven BREAKER/EOD/KILL close
    already leaves NT parity fields blank). `sig_dt`/`signal_source` carry the engine
    signal's own timestamp/attribution when `f` is None so latency and the
    orders/trades CSVs still record something real instead of blank.

    `trade_id`/`entry_ref_time` (2026-09-14): the ENTRY row's trade id and entry bar time,
    stored on the lot -- only an EXIT with the same id closes it (_route_engine_events) and
    the broker order ids derive from it (_broker_signal_id). With no id given but an NT
    fill, the id is derived from that fill (leg "NT_<leg>", the fill's own timestamp, side),
    never from this process's clock.

    `size` (2026-09-23): the per-trade multiplier an engine ENTRY signal may carry --
    see _resolve_entry_size/_sized_shares just above. Never given by a NinjaTrader-
    mirrored fill (`f` set): fills.csv has no size column, and _route_fills passes none."""
    max_shares = int(cfg.get("max_shares_per_leg", 0) or 0)
    size_mode = str(cfg.get("size_mode") or "fixed").strip().lower()
    instrument = (f.get("instrument") if f else "") or ""
    nt_mult = _nt_mult(instrument, log=log)

    if size_mode == "nt_notional" and nt_mult and qqq_px_raw and nq_px is not None:
        # NT SIZING GAP (feature #50): size the shadow lot off the $ notional of the NT
        # futures fill it mirrors, instead of the fixed shares table. Still CLAMPED (not
        # refused) to max_shares_per_leg -- a dynamically computed size can overshoot the
        # cap easily and refusing every overshoot would defeat the point of the mode.
        nt_notional_usd = round(nq_qty * nt_mult * nq_px, 2)
        size_fraction = float(cfg.get("size_fraction", 0.01) or 0.01)
        wanted_shares = int(round(nt_notional_usd * size_fraction / qqq_px_raw))
        shares = wanted_shares
        if max_shares:
            shares = min(shares, max_shares)
        # Not the engine per-trade SIZE contract above (this mode's own $ notional sizing
        # is unrelated to a signal's "size" field) -- shares_wanted still records what
        # this mode wanted before the SAME rail clamped it, same as the branch below.
        sized = 1.0
    else:
        # Default behaviour (size_mode == "fixed").
        base_shares = int(cfg["shares"].get(leg, 0))
        sized = _resolve_entry_size(size)
        wanted_shares = _sized_shares(base_shares, sized)
        if sized == 1.0:
            # UNCHANGED: no signal size in play -- an old ledger row written before the
            # "size" column existed, a blank/unparseable value, or a literal 1.0, so
            # wanted_shares == base_shares exactly (see _sized_shares) and this is BYTE
            # FOR BYTE the original rail: refuse the WHOLE lot rather than silently send
            # a different count than configured.
            shares = wanted_shares
            if shares > max_shares:
                _record_order(leg, "ENTER", side, shares, nq_px, None, None,
                              f"REFUSED shares {shares} > max_shares_per_leg {max_shares}", log,
                              fill_dt=(f.get("dt") if f else sig_dt), signal_source=signal_source)
                return False
        else:
            # SIZED (2026-09-23): an engine ENTRY signal declared a per-trade size (run
            # #382 NOISE_1_8_CT304 today, KEEL later). RAILS STAY THE OWNER'S DECISION:
            # clamp to max_shares_per_leg instead of refusing the whole trade, exactly
            # like the nt_notional branch above already does for its own dynamically
            # computed size (see its comment) -- a size this module did not choose can
            # overshoot the cap easily, and refusing every overshoot would silently drop
            # a trade the sizing strategy is relying on the rail to cap, not cancel.
            shares = min(wanted_shares, max_shares) if max_shares else wanted_shares
            if shares < wanted_shares:
                log(f"[qqq-exec] {leg} entry sized {base_shares} x {sized:g} = "
                    f"{wanted_shares} wanted, clamped to max_shares_per_leg {max_shares}")
                _log_event(state, "size_clamped",
                          f"{leg} entry wanted {wanted_shares} shares ({base_shares} "
                          f"configured x {sized:g} size), clamped to {shares} by "
                          f"max_shares_per_leg {max_shares}", log=log)

    if shares <= 0:
        return False

    fill_px = _apply_slippage(qqq_px_raw, side, True, slip)
    lot = {
        "leg": leg, "side": side, "shares_total": shares, "shares_remaining": shares,
        "nq_qty_total": nq_qty, "nq_qty_remaining": nq_qty,
        "entry_px": fill_px, "nq_entry_px": nq_px, "last_nq_px": nq_px,
        "entry_ts": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
        # SIZE ORDERS: the pre-clamp wanted quantity and the resolved size multiplier
        # that produced it -- travels onto the closed-trade row (_record_trade) exactly
        # like the NT sizing-gap fields below. _reduce_lot never reads either one; it
        # only ever closes shares_total/shares_remaining, see its own docstring.
        "shares_wanted": wanted_shares, "size": sized,
        # KEEL OVERLAY: display-only (see this function's own docstring) -- never
        # affects shares_total/wanted_shares above, which are already final by here.
        "keel_size": _resolve_keel_size(keel_size),
    }
    if not trade_id and f is not None and f.get("dt") is not None:
        trade_id = _trade_id.make(f"NT_{leg}", f["dt"], side, default_tz=_NY)
        if not entry_ref_time and hasattr(f["dt"], "isoformat"):
            entry_ref_time = f["dt"].isoformat()
    lot["trade_id"] = trade_id or None
    lot["entry_ref_time"] = entry_ref_time or None
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
    lot["signal_source"] = signal_source or ""
    _record_order(leg, "ENTER", side, shares, nq_px, fill_px, state["_px_source"],
                 "signal entry", log, fill_dt=(f.get("dt") if f else sig_dt),
                 signal_source=signal_source, shares_wanted=wanted_shares, size=sized)
    _notify(f"QQQ SHADOW {leg} {side} {shares} @ {fill_px:.2f}", "EDGELOG QQQ SHADOW", log)
    # BROKER MIRROR: after the shadow's own order is already recorded above -- see the
    # "broker mirror" section docstring near _mirror_to_broker. A broker error here
    # never unwinds the shadow lot just opened.
    _mirror_to_broker(state, leg=leg, side=side, shares=shares, shadow_px=fill_px,
                      intent="OPEN", ts=lot["entry_ts"], trade_id=lot["trade_id"], log=log)
    return True


def _reduce_lot(state, cfg, leg, nq_qty_closed, nq_px, qqq_px_raw, slip, reason, f=None, log=print,
                sig_dt=None, signal_source=None):
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
                 state["_px_source"], reason, log, fill_dt=(f.get("dt") if f else sig_dt),
                 signal_source=(signal_source or lot.get("signal_source")),
                 size=lot.get("size"))
    _notify(f"QQQ SHADOW {leg} {reason.lower()} {shares_close} @ {fill_px:.2f}",
           "EDGELOG QQQ SHADOW", log)
    # BROKER MIRROR: mirrors every reduce, not just a full close -- a ninjatrader-mode
    # partial exit closes only part of the broker position too. `seq` disambiguates more
    # than one reduce against the SAME lot (engine mode never needs it -- see module
    # docstring, entries/exits are single-shot there). Flat-by/EOD/KILL route through
    # here too (_close_all calls _reduce_lot), so this is also what keeps a broker
    # position from surviving past flat-by.
    lot["_broker_close_seq"] = lot.get("_broker_close_seq", 0) + 1
    _mirror_to_broker(state, leg=leg, side=lot["side"], shares=shares_close,
                      shadow_px=fill_px, intent="CLOSE", ts=lot["entry_ts"],
                      seq=lot["_broker_close_seq"], trade_id=lot.get("trade_id"), log=log)
    pnl = None
    if lot["shares_remaining"] <= 0:
        # close the round-trip on the full lot's entry (weighted avg exit unnecessary
        # for a single-entry lot -- see module docstring: entries are treated single-shot)
        pnl = _record_trade(lot, fill_px, reason, log=log)
        state["realized_pnl_today"] = round(state.get("realized_pnl_today", 0.0) + pnl, 2)
        del state["legs"][leg]
    return pnl


def _close_all(state, cfg, reason, quote_fn, ratio_fn, log=print):
    """BREAKER/EOD/KILL flatten -- branches on signal_source exactly like
    _mark_and_check_breaker: engine mode prices the close off api.cloud_signal's own
    QQQ bar cache (_engine_mark_price), never the NQ feed/ratio/Webull quote."""
    engine_mode = str(cfg.get("signal_source") or "engine").strip().lower() == "engine"
    nq_now = None
    if not engine_mode:
        nq_now, _ts = _latest_nq_px()
    for leg in list(state["legs"].keys()):
        lot = state["legs"][leg]
        if engine_mode:
            exit_nq = None
            qqq_px, src = _engine_mark_price(leg, log=log)
        else:
            # flatten at the LIVE NQ price (fallback: last known) -- never at the entry price
            exit_nq = nq_now if nq_now is not None else (lot.get("last_nq_px") or lot["nq_entry_px"])
            qqq_px, src = resolve_price(cfg, state, exit_nq, quote_fn, ratio_fn, log=log)
        state["_px_source"] = src
        if qqq_px is None:
            log(f"[qqq-exec] cannot price {leg} for {reason} close -- no quote/ratio "
                f"available, lot left open")
            continue
        _reduce_lot(state, cfg, leg, lot["nq_qty_remaining"], exit_nq,
                   qqq_px, cfg.get("slippage_per_share", 0.0), reason, log=log,
                   signal_source=cfg.get("signal_source"))


# -- orphan broker repair ------------------------------------------------------------------
# WHY THIS EXISTS (2026-09-20). The broker mirror can end up holding a position the shadow
# book does not: _close_all writes the shadow exit unconditionally, but the matching broker
# CLOSE is a best-effort mirror that can be rejected. It happened for real on 2026-09-17 and
# 2026-09-18, when session.flat_by was set to "16:00": the 5s tick fires the flatten at
# 16:00:02-16:00:05 ET, i.e. AFTER the regular close, so Webull answers every market sell
# with "only limit orders are supported for extended-hours trading" (HTTP 417
# OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET). The shadow book then reads flat while
# 20 real paper shares stayed open, and the adapter's own one-open-position-per-leg rail
# BLOCKED the next day's entry for those legs. flat_by is back inside the session, but an
# orphan that already exists needs an explicit, in-session, market-hours repair -- and it has
# to run INSIDE this process, because the OrderAdapter loads its state file once at
# construction (see _get_broker_adapter) and a second process writing that file would race.
def _maybe_flatten_orphan_broker(state, cfg, nowdt, log=print):
    """Close broker legs this book has no open lot for, ONE PER TICK, until none are left.
    No-op unless the trigger file exists AND we are inside regular trading hours (a market
    order outside 09:30-16:00 ET is exactly what created the orphan). Never raises -- a
    failure here must not stop the tick.

    WHY ONE PER TICK, AND A FRESH ID EVERY ATTEMPT (2026-09-21, the first live run). The
    first version sent every orphan's CLOSE in the same instant and named each repair
    FIX-<leg>-<YYYYMMDD>. At 09:31:00 it sent SELL 10 QQQ for ENGUQ and SELL 10 QQQ for ORB
    back to back; Webull filled the first and REJECTED the second with 417
    OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK ("You already have an existing order
    with the exact same order details") -- its risk rule compares the ORDER, not our
    client_order_id, and two legs holding the same symbol produce identical orders. Worse,
    a same-day retry would have rebuilt the SAME id, and OrderAdapter.place_stock_order
    returns an already-recorded id from its idempotency cache without sending anything,
    so re-arming the trigger would have silently done nothing. Now: one leg per tick (the
    next goes 5 s later, after the first has filled and left Webull's open-order book),
    an id stamped to the second so every attempt is new (qxFIXORB20260921093105C, 23-25
    chars, inside Webull's 32), at most FLATTEN_MAX_TRIES attempts per leg per day, and
    the trigger is consumed only once no orphan is left (or every one has given up)."""
    # Resolved against the CURRENT OUT_DIR, never a value baked in at import time --
    # see the note in DEFAULT_CONFIG. A test that repoints OUT_DIR is then fully isolated
    # from the live trigger file, including the os.replace that consumes it.
    path = cfg.get("flatten_broker_file") or os.path.join(OUT_DIR, "FLATTEN_BROKER")
    if not os.path.exists(path):
        return
    sess = cfg.get("session") or {}
    # Strictly inside the session: after `open` so the order is a regular-hours market
    # order, and at/before `last_entry` so a repair can never collide with the flat_by
    # rail closing a lot opened the same day. OUTSIDE those hours the trigger is LEFT IN
    # PLACE, not consumed -- dropping the file on a Sunday has to survive until Monday's
    # open, which is the whole point of a trigger rather than a one-off script.
    if not (_is_weekday(nowdt)
            and _hhmm(sess.get("open", "09:31")) <= _et_hhmm(nowdt)
            <= _hhmm(sess.get("last_entry", "15:55"))):
        return
    consume = False
    try:
        adapter = _get_broker_adapter(log=log)
        believed = adapter.status().get("believed_positions") or {}
        shadow_open = set((state.get("legs") or {}).keys())
        orphans = sorted((leg, int(abs(p.get("qty") or 0))) for leg, p in believed.items()
                         if int(abs(p.get("qty") or 0)) > 0 and leg not in shadow_open)
        tries = state.setdefault("_flatten_tries", {})
        day = nowdt.strftime("%Y%m%d")
        live = [(leg, qty) for leg, qty in orphans
                if int(tries.get(f"{day}:{leg}", 0)) < FLATTEN_MAX_TRIES]
        if not orphans:
            log("[qqq-exec] FLATTEN_BROKER: no orphan broker lot left -- trigger consumed")
            _log_event(state, "broker", "Flatten-broker repair complete -- no orphan left",
                      log=log)
            consume = True
        elif not live:
            gave_up = ", ".join(f"{leg} {qty}sh" for leg, qty in orphans)
            log(f"[qqq-exec] FLATTEN_BROKER: GAVE UP after {FLATTEN_MAX_TRIES} attempts each "
                f"on {gave_up} -- still held at the broker, trigger consumed")
            _log_event(state, "broker", f"Flatten-broker repair gave up -- still held: {gave_up}",
                      log=log)
            _notify(f"QQQ SHADOW: could NOT flatten {gave_up} after {FLATTEN_MAX_TRIES} "
                    f"tries each -- sell by hand", "EDGELOG QQQ BROKER REPAIR FAILED", log)
            consume = True
        else:
            leg, qty = live[0]
            key = f"{day}:{leg}"
            tries[key] = int(tries.get(key, 0)) + 1
            qqq_px, src = _engine_mark_price(leg, log=log)
            log(f"[qqq-exec] FLATTEN_BROKER: closing orphan broker lot {leg} {qty} sh "
                f"(attempt {tries[key]} of {FLATTEN_MAX_TRIES}; shadow book holds no lot for it)")
            _mirror_to_broker(state, leg=leg, side="long", shares=qty, shadow_px=qqq_px,
                             intent="CLOSE", ts=nowdt, requeue=False,
                             trade_id=f"FIX-{leg}-{nowdt:%Y%m%d%H%M%S}", log=log)
            _log_event(state, "broker",
                      f"Flatten-broker repair: sent CLOSE for orphan {leg} {qty} sh "
                      f"(attempt {tries[key]}, mark {qqq_px if qqq_px is not None else 'n/a'}, "
                      f"source {src or 'n/a'})", log=log)
    except Exception as e:
        log(f"[qqq-exec] flatten-broker repair failed (non-fatal): {type(e).__name__}: {e}")
        # a file that re-fires every 5 s on an exception would be worse than one that has
        # to be dropped again on purpose
        consume = True
    if consume:
        try:
            if os.path.exists(path):
                os.replace(path, f"{path}.done-{_now_et():%Y%m%d-%H%M%S}")
        except Exception as e:
            log(f"[qqq-exec] could not consume the FLATTEN_BROKER trigger at {path}: "
                f"{type(e).__name__}: {e}")


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
                # STARTUP GUARD (2026-09-13, ninjatrader mode only): a strategy
                # re-enable/relaunch can fire a fill NinjaTrader itself never intended
                # as a real signal (observed 2026-09-03, 12:30, two such entries). Ignore
                # it -- mark it, never silently drop it -- unless api/cloud_signal.py's
                # own engine ledger independently confirms the same entry.
                if (str(cfg.get("signal_source") or "engine").strip().lower() == "ninjatrader"
                        and _relaunch_recently(state, cfg, f["dt"])
                        and not _engine_confirms_entry(leg, f["dt"])):
                    guard_min = cfg.get("startup_guard_minutes", 5)
                    _record_order(leg, "ENTER", side_of_fill, cfg["shares"].get(leg, 0),
                                 f["price"], None, None,
                                 f"STARTUP-SUSPECT -- within {guard_min}min of a relaunch "
                                 f"with no matching engine signal (not mirrored)", log,
                                 fill_dt=f["dt"], signal_source=cfg.get("signal_source"))
                    state["group_leg"][gk] = leg
                    _accumulate_signal(state, f["dt"], leg, "fired", log=log)
                    _accumulate_signal(state, f["dt"], leg, "refused", log=log)
                    _log_event(state, "startup_suspect",
                              f"{leg} entry ignored -- within {guard_min}min of a relaunch, "
                              f"no engine confirmation", log=log)
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
                              else "REFUSED -- breaker/fill-feed/price-feed/kill blocked")
                    _record_order(leg, "ENTER", side_of_fill, cfg["shares"].get(leg, 0),
                                 f["price"], None, None, reason, log, fill_dt=f["dt"],
                                 signal_source=cfg.get("signal_source"))
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
                                   cfg.get("slippage_per_share", 0.0), f=f, log=log,
                                   signal_source=cfg.get("signal_source"))
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
                           cfg.get("slippage_per_share", 0.0), reason, f=f, log=log,
                           signal_source=cfg.get("signal_source"))
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
    engine_mode = str(cfg.get("signal_source") or "engine").strip().lower() == "engine"
    nq_now = nq_ts = None
    if not engine_mode:
        nq_now, nq_ts = _latest_nq_px()
    for leg, lot in state["legs"].items():
        if engine_mode:
            # ENGINE MODE: mark off api.cloud_signal's own QQQ bar cache -- never NQ.
            lot["mark_nq_px"] = None
            qqq_px, src = _engine_mark_price(leg, log=log)
            lot["mark_fresh"] = qqq_px is not None
        else:
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
_PX_RAIL_QUOTE_CACHE = {"at": 0.0, "ok": False}   # see _check_px_feed


def _check_px_feed(state, quote_fn=None, log=print):
    """True when we cannot obtain a LIVE price to mark or exit a lot with.

    WHY THIS IS ITS OWN RAIL (2026-09-09). `_check_feed` below watches the FILL feed --
    whether NinjaTrader is still writing fills.csv. It says nothing about the PRICE feed
    (the NQ 10s bars), and the two die independently: on 2026-09-09 NinjaTrader was
    perfectly healthy, all three strategies Realtime, fills.csv fresh -- while the 10s
    chart export stopped 40 seconds after the strategies were enabled and stayed dead all
    session. With no live NQ price, `_close_all` falls back to `lot["nq_entry_px"]`, so an
    EOD flatten writes an exit AT THE ENTRY PRICE: a fabricated round trip that shows a
    plausible P&L, fails NT parity, and quietly poisons the readiness evidence the go-live
    decision rests on. That is exactly the 2026-09-03 corruption v73.469 was written to
    end, reached by a different road.

    So: a lot we cannot honestly manage is a lot we must not open. A refused signal is
    recorded, explainable evidence ("we could not mirror this one"); a mispriced trade is
    corrupt evidence, which is worse than none. Exits are deliberately NOT blocked -- an
    already-open lot still gets every chance to close.

    RELAXED 2026-09-09, exactly as this docstring anticipated. The owner claimed the free
    Nasdaq Basic non-display tier, so `quote_fn` now returns a real-time QQQ print about a
    second old. `resolve_price` consults that quote FIRST, and both `_mark_and_check_breaker`
    and `_close_all` go through it -- so with a working quote a dead NQ feed no longer
    blinds anything, and blocking entries on it would refuse trades we can price perfectly
    well. The rail therefore fires only when BOTH sources are gone. The quote probe is
    cached for 60s and only ever runs when the NQ feed is already stale, so the healthy
    path stays a cheap file read and a dead-feed day costs one API call a minute."""
    px, _ts = _latest_nq_px()
    stale = px is None
    if stale and quote_fn is not None:
        now = time.time()
        if now - _PX_RAIL_QUOTE_CACHE["at"] >= 60.0:
            _PX_RAIL_QUOTE_CACHE["at"] = now
            try:
                _PX_RAIL_QUOTE_CACHE["ok"] = quote_fn(log=log) is not None
            except Exception:
                _PX_RAIL_QUOTE_CACHE["ok"] = False
        if _PX_RAIL_QUOTE_CACHE["ok"]:
            stale = False
    was = state.get("px_feed_stale", False)
    state["px_feed_stale"] = stale
    if stale and not was:
        _log_event(state, "px_feed_down",
                  "No live price from EITHER the Webull quote or the NQ feed -- open lots "
                  "cannot be marked, so new entries are blocked (an exit would otherwise "
                  "be priced at the entry price)", log=log)
    elif was and not stale:
        _log_event(state, "px_feed_up", "Live pricing is back -- entries re-enabled", log=log)
    return stale


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
        # STARTUP GUARD (2026-09-13): the fill feed coming back after a stale spell is
        # this module's best available proxy for "a NinjaTrader strategy was just
        # re-enabled" -- see _relaunch_recently, which uses this timestamp to ignore a
        # startup entry that matches no real engine signal.
        state["relaunch_at"] = _now_et().strftime("%Y-%m-%d %H:%M:%S")
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


# -- engine-vs-broker parity (feature #56, 2026-09-22) -------------------------------
# OWNER (2026-09-22), on this book's PARITY NOTE chip painting red on every single
# closed trade: "why are we comparing to NT... for parity shouldn't it just be EL OHLC
# values to Webull?" -- exactly right: this book's config runs signal_source="engine"
# (see DEFAULT_CONFIG), so there never WAS a NinjaTrader fill for _trade_parity above to
# compare against -- every row was structurally guaranteed to read "insufficient NT fill
# data to check parity", and index.html's parityChip painted that non-empty NOTE text
# red regardless of parity_ok being None ("not checked"), not False ("failed"). See
# RESEARCH.md-style framing: _trade_parity/_parity_summary above are UNTOUCHED by this
# section and still run for every row (a row that genuinely mirrors NinjaTrader,
# signal_source=="ninjatrader", keeps exactly that read -- see _build_doc).
#
# This section is the comparison the owner asked for instead: the engine's own booked
# entry_px/exit_px (computed off OHLC bars, see module docstring PRICING) against the
# best BROKER-side truth available for that fill -- Webull's own reported fill price
# (broker_orders.csv's broker_fill_px, captured by _query_broker_fill above) when we
# have it, else the tape-repriced price (reprice.csv via _merge_reprice,
# real_entry_px/real_exit_px) as a fallback -- independently per LEG of the round trip,
# so a trade can have a Webull fill on one leg and only a repriced price on the other.
_RESEND_SUFFIX_RE = re.compile(r"R\d+$")


def _signal_id_base(signal_id):
    """Strips a resend suffix ("R<n>", see _mirror_to_broker's `resend` param) off a
    broker_orders.csv signal_id so an original attempt and its resends group under one
    key. The base _broker_signal_id builds always ends in a letter (the O/C intent code,
    or the pre-trade-id fallback form's "OPEN"/"CLOSE") -- never a digit -- so this is
    unambiguous against the OTHER numeric suffix _broker_signal_id can append (`seq`, a
    ninjatrader-mode reduce count): a bare digit suffix is left alone, only a
    trailing-R-then-digits one is stripped."""
    s = str(signal_id or "")
    m = _RESEND_SUFFIX_RE.search(s)
    return s[:m.start()] if m else s


def _broker_orders_by_base(rows):
    """{signal_id_base: [row, ...]} in file order (oldest first) -- see
    _signal_id_base / _best_broker_row / _broker_order_for."""
    out = {}
    for row in rows:
        out.setdefault(_signal_id_base(row.get("signal_id")), []).append(row)
    return out


def _best_broker_row(rows):
    """Among every attempt sharing one signal-id base (an original try plus any
    resends, oldest first), the most authoritative: the LAST one that actually reached
    the broker OK, else the last attempt on file at all (so its reason/mode still
    explains why there is no fill price). None for an empty/absent list."""
    if not rows:
        return None
    for row in reversed(rows):
        if str(row.get("ok")).strip().lower() in ("true", "1"):
            return row
    return rows[-1]


def _broker_order_for(trade_id, intent, by_base):
    """The broker_orders.csv row (see _best_broker_row) for one leg (OPEN/CLOSE) of a
    trade id, or None when there is no trade id (a trades.csv row closed before feature
    #56 shipped, or a lot that lost its id) or no matching row at all (this leg's order
    aged out of broker_orders.csv's own ORDERS_KEEP trim -- see BROKER_ORDER_COLS)."""
    if not trade_id:
        return None
    sig_id = _broker_signal_id(None, None, intent, trade_id=trade_id)
    return _best_broker_row(by_base.get(sig_id))


def _all_broker_orders_from_csv(cap=1000):
    """Every broker_orders.csv row on file (oldest-first, as the CSV stores them),
    capped defensively to the newest `cap` -- mirrors _all_trades_from_csv. The file
    itself never holds more than ORDERS_KEEP rows (trimmed at write time), so this cap
    is a second, independent ceiling, not the normal limiter. Never raises."""
    try:
        with open(BROKER_ORDERS_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return []
    return rows[-cap:]


def _broker_trade_parity(row, by_base, log=print):
    """Compute the ENGINE-vs-BROKER parity block for one trades.csv row (a dict of
    strings, as read back by csv.DictReader, already carrying reprice fields merged in
    by _merge_reprice -- this must run AFTER that merge). Returns broker_* fields;
    broker_parity_ok is None ("not checked" -- NOT an error, see module docstring) when
    neither a Webull fill nor a repriced tape price is available for BOTH legs yet (the
    normal state for a trade closed before feature #56/#57 shipped, or one still waiting
    on tonight's reprice run). Never raises."""
    try:
        trade_id = str(row.get("trade_id") or "").strip()
        shares = _f_or_none(row.get("shares")) or 0.0
        side = row.get("side")
        dir_mult = 1 if side == "long" else -1
        engine_entry = _f_or_none(row.get("entry_px"))
        engine_exit = _f_or_none(row.get("exit_px"))

        def _leg_price(intent, real_field):
            """(price, source) for one leg of the round trip -- a real Webull fill
            beats the repriced tape price, which beats nothing."""
            brow = _broker_order_for(trade_id, intent, by_base)
            if brow is not None and str(brow.get("ok")).strip().lower() in ("true", "1"):
                px = _f_or_none(brow.get("broker_fill_px"))
                if px is not None:
                    return px, "webull_fill"
            real_px = _f_or_none(row.get(real_field))
            if real_px is not None:
                return real_px, "repriced_tape"
            return None, None

        entry_px, entry_src = _leg_price("OPEN", "real_entry_px")
        exit_px, exit_src = _leg_price("CLOSE", "real_exit_px")

        if entry_px is None or exit_px is None or engine_entry is None or engine_exit is None:
            return {"broker_entry_px": entry_px, "broker_exit_px": exit_px,
                   "broker_entry_source": entry_src, "broker_exit_source": exit_src,
                   "broker_slip_entry_ps": None, "broker_slip_exit_ps": None,
                   "broker_expected_usd": None, "broker_track_err_usd": None,
                   "broker_parity_ok": None, "broker_parity_source": None,
                   "broker_parity_note": "not checked -- no Webull fill or repriced tape "
                                         "price for this trade yet"}

        slip_entry_ps = round(entry_px - engine_entry, 4)
        slip_exit_ps = round(exit_px - engine_exit, 4)
        broker_points = round((exit_px - entry_px) * dir_mult, 4)
        expected_usd = round(broker_points * shares, 2)
        pnl = _f_or_none(row.get("pnl")) or 0.0
        track_err = round(pnl - expected_usd, 2)
        tol = max(0.05, 0.02 * abs(expected_usd))
        ok = abs(track_err) <= tol
        source = entry_src if entry_src == exit_src else "mixed"
        note = ""
        if not ok:
            note = (f"engine booked ${pnl:.2f} but {source.replace('_', ' ')} price(s) "
                    f"imply ${expected_usd:.2f} -- tracking error ${track_err:.2f} "
                    f"exceeds tolerance ${tol:.2f}")
        return {"broker_entry_px": entry_px, "broker_exit_px": exit_px,
               "broker_entry_source": entry_src, "broker_exit_source": exit_src,
               "broker_slip_entry_ps": slip_entry_ps, "broker_slip_exit_ps": slip_exit_ps,
               "broker_expected_usd": expected_usd, "broker_track_err_usd": track_err,
               "broker_parity_ok": bool(ok), "broker_parity_source": source,
               "broker_parity_note": note}
    except Exception as e:
        log(f"[qqq-exec] broker parity calc failed for a trade row: {type(e).__name__}: {e}")
        return {"broker_entry_px": None, "broker_exit_px": None,
               "broker_entry_source": None, "broker_exit_source": None,
               "broker_slip_entry_ps": None, "broker_slip_exit_ps": None,
               "broker_expected_usd": None, "broker_track_err_usd": None,
               "broker_parity_ok": None, "broker_parity_source": None,
               "broker_parity_note": f"parity calc failed: {type(e).__name__}"}


_NT_MIRROR_NOTE = "n/a -- this trade mirrors NinjaTrader, see NT parity"


def _broker_parity_summary(trades_all):
    """Headline ENGINE-vs-BROKER parity read -- see _broker_trade_parity. Counts only
    rows this check actually applies to (signal_source != "ninjatrader"); a
    NinjaTrader-mirrored row keeps its own NT parity (_parity_summary above) and never
    counts here, matching how those rows are computed in _build_doc."""
    checked = ok = failed = not_checked = 0
    worst = 0.0
    worst_note = ""
    for t in trades_all:
        if str(t.get("signal_source") or "").strip().lower() == "ninjatrader":
            continue
        pok = t.get("broker_parity_ok")
        if pok is None:
            not_checked += 1
            continue
        checked += 1
        te = t.get("broker_track_err_usd")
        if pok:
            ok += 1
        else:
            failed += 1
        if te is not None and abs(te) > abs(worst):
            worst = te
            worst_note = t.get("broker_parity_note") or ""
    if checked == 0:
        note = (f"{not_checked} trade(s) awaiting a Webull fill price or a repriced tape "
                f"price -- not an error, just not checked yet" if not_checked else
                "no engine-signal trades recorded yet")
    elif failed == 0:
        note = "every checked trade tracks its broker-side price within tolerance"
        if not_checked:
            note += f" ({not_checked} more not yet checked)"
    else:
        note = f"{failed} of {checked} trade(s) miss their broker-side price"
        if worst_note:
            note += f" -- worst: {worst_note}"
    return {"checked": checked, "ok": ok, "failed": failed, "not_checked": not_checked,
           "worst_err_usd": round(worst, 2), "note": note}


def _apply_broker_parity(trades_all, broker_by_base, log=print):
    """Updates every row of trades_all IN PLACE with its broker_* fields (see
    _broker_trade_parity) -- factored out of _build_doc so the dispatch rule itself
    ("which rows get the new check") is unit-testable on its own. A row whose
    signal_source is "ninjatrader" (a genuine NinjaTrader-mirrored trade, see module
    docstring) is left with a clear placeholder instead: _trade_parity's OWN NT-parity
    fields on that row (parity_ok/parity_note, computed separately in _build_doc,
    BEFORE this runs) are exactly what applied to it before feature #56 existed, and
    this function never reads or writes them. Never raises."""
    for row in trades_all:
        if str(row.get("signal_source") or "").strip().lower() == "ninjatrader":
            row.update({"broker_entry_px": None, "broker_exit_px": None,
                       "broker_entry_source": None, "broker_exit_source": None,
                       "broker_slip_entry_ps": None, "broker_slip_exit_ps": None,
                       "broker_expected_usd": None, "broker_track_err_usd": None,
                       "broker_parity_ok": None, "broker_parity_source": None,
                       "broker_parity_note": _NT_MIRROR_NOTE})
        else:
            row.update(_broker_trade_parity(row, broker_by_base, log=log))


def _book_only_status(row, by_base, log=print):
    """Whether this trade's OPEN ever reached the broker at all -- a DIFFERENT question
    from _broker_trade_parity's above (which asks "did the price match", never "did
    Webull ever hold this"). Reuses the SAME join (_broker_order_for / by_base, the
    dict _broker_orders_by_base built once in _build_doc) rather than a second reader
    of broker_orders.csv -- see module docstring PRICING for why that join is the one
    source of truth for "what did the broker actually do with this trade id".

    Looks ONLY at the trade's OWN OPEN leg (never the CLOSE -- see PARTIAL MIRRORS
    below) and reads off that one broker_orders.csv row:

      UNKNOWN (book_only False, "" reason) --
      * no trade_id, or _broker_order_for finds no matching row at all: either this
        trade predates trade ids, or its OPEN order aged out of broker_orders.csv's own
        ORDERS_KEEP trim (see BROKER_ORDER_COLS). There is no record either way, so
        this is NOT marked book-only -- that would claim more than the data supports.
      * mode == "OFF": the broker adapter was not mirroring AT ALL when this OPEN
        happened (webull_orders.MODE_OFF, a deliberate config-level no-op -- see
        place_stock_order, which always records ok=True/sent=False for OFF). ok is
        already True on every OFF row, so this branch never changes the verdict below;
        it exists so a reader (and a future change to OFF's own ok/sent values) cannot
        mistake "not mirroring" for "reached the broker and succeeded". Also UNKNOWN,
        not book-only: whether Webull would have accepted or refused this OPEN is
        something this book chose not to find out that day.

      BOOK ONLY (book_only True, reason = the broker's own words) --
      * ok is False for every other mode: BLOCKED (this module's pre-send lease gate,
        or webull_orders' own rails -- max_shares/session/etc, or the "nothing to
        close" guard on a CLOSE, though that never applies to an OPEN), ERROR (an
        exception before any network call), or a genuine PAPER/LIVE send Webull itself
        refused -- e.g. 2026-09-23's HTTP 417 OPENAPI_GENERATE_NEW_SHORT_POSITION
        short-sale rejection, ok=False/sent=True. No shares were ever held at the
        broker in any of these, so the book's own pnl for this trade is fiction as far
        as Webull is concerned. `reason` is read straight off the row's own "reason"
        column -- _mirror_to_broker already folds rec["reason"] or rec["error"] into
        that column at write time (see its own docstring), so this is genuinely the
        broker/rail's own words, never re-derived.

      NOT BOOK ONLY (book_only False, "" reason) --
      * ok is True: the OPEN reached the broker and Webull accepted it, so shares WERE
        held there (mode is PAPER or LIVE whenever ok is True and mode != OFF).

    PARTIAL MIRRORS (owner ask, 2026-09-23): a trade whose OPEN succeeded but whose
    CLOSE later failed, was blocked, or never mirrored is deliberately left NOT
    book_only by this function -- it only ever reads the OPEN leg. Flipping it to
    book_only because the EXIT didn't mirror would UNDERSTATE what happened (shares
    really were held at the broker at some point) and would conflate two different
    failures: "the broker never had this trade" (what this flag means) versus "the
    broker still holds a position this book's own record shows flat" (a real but
    separate position-reconciliation problem, not built here). A CLOSE that failed
    after a successful OPEN still shows up in its own right -- broker_parity_ok either
    stays unchecked or fails outright, and the adapter's own "nothing to close" log
    line already warns operationally. This function's silence on that case is
    intentional, not an oversight -- see the docstring above.

    Never raises: any lookup failure degrades to UNKNOWN, the same as a missing row."""
    try:
        trade_id = str(row.get("trade_id") or "").strip()
        open_row = _broker_order_for(trade_id, "OPEN", by_base)
        if open_row is None:
            return {"book_only": False, "book_only_reason": ""}
        mode = str(open_row.get("mode") or "").strip().upper()
        if mode == "OFF":
            return {"book_only": False, "book_only_reason": ""}
        ok = str(open_row.get("ok")).strip().lower() in ("true", "1")
        if ok:
            return {"book_only": False, "book_only_reason": ""}
        reason = str(open_row.get("reason") or "").strip()
        if not reason:
            reason = f"broker OPEN did not go through (mode={mode or 'unknown'})"
        return {"book_only": True, "book_only_reason": reason}
    except Exception as e:
        log(f"[qqq-exec] book-only calc failed for a trade row: {type(e).__name__}: {e}")
        return {"book_only": False, "book_only_reason": ""}


def _apply_book_only(trades_all, broker_by_base, log=print):
    """Updates every row of trades_all IN PLACE with book_only/book_only_reason (see
    _book_only_status) -- same shape and dispatch rule as _apply_broker_parity just
    above: a genuinely NinjaTrader-mirrored row (signal_source == "ninjatrader") is
    left NOT book-only unconditionally, never looked up. broker_orders.csv's signal-id
    space belongs to THIS book's own Webull mirror attempts; an NT-mirrored row's
    trade is settled by NinjaTrader, so whatever this module's Webull adapter did or
    did not do under that same trade id is not what "book only" is asking about for
    that row. Never raises."""
    for row in trades_all:
        if str(row.get("signal_source") or "").strip().lower() == "ninjatrader":
            row["book_only"] = False
            row["book_only_reason"] = ""
        else:
            row.update(_book_only_status(row, broker_by_base, log=log))


def _book_only_summary(trades_all):
    """Book vs broker headline totals over trades_all's own pnl (_curve_pnl -- the SAME
    fallback pnl/real_pnl rule the equity curve, the closed-trades table and the
    calendar all use, so this total always agrees with what the tab already shows
    elsewhere). `book_net` is every closed trade, exactly what the tab has always
    summed; `broker_net` is the same sum with every book_only trade left out -- what
    Webull's own side actually made. Equal whenever nothing is book-only. Never
    raises -- a trade whose own pnl fields are unusable contributes 0.0 either way,
    the same as _curve_pnl already does for the curve."""
    book_net = 0.0
    broker_net = 0.0
    book_only_n = 0
    for t in trades_all:
        pnl = _curve_pnl(t)
        book_net += pnl
        if t.get("book_only"):
            book_only_n += 1
        else:
            broker_net += pnl
    return {"book_net": round(book_net, 2), "broker_net": round(broker_net, 2),
           "book_only_count": book_only_n}


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


def _curve_pnl(t):
    """What one closed trade adds to the curve: `pnl` when it is a real number, else
    the tape-repriced `real_pnl` (merged onto the row by _merge_reprice), else 0 -- the
    same fallback the web tab uses for its table, calendar and KPIs (qePnlOf).

    2026-09-21 (owner: "webull paper chart doesnt show all the trades"): an exit the
    adapter could not mark is written as pnl "nan", and float("nan") does not raise --
    so the old float(pnl) added NaN to the running total, and every later point of that
    leg and of TOTAL was NaN. The 09-17 / 09-18 after-the-bell exits did exactly that."""
    for fld in ("pnl", "real_pnl"):
        try:
            v = float(t.get(fld))
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            return v
    return 0.0


def _cum_pnl_by_leg(all_trades):
    """{leg: [{"date","cum_pnl"}, ...], total: [...]} -- one point per
    calendar date (ET, off exit_ts) a leg had at least one close, cumulative sum of
    each trade's _curve_pnl in chronological order. The web tab now draws its curve
    from trades_all itself (2026-09-21); this published copy stays for other readers
    and must never carry a NaN."""
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
        running[leg] = round(running[leg] + _curve_pnl(t), 2)
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
# AFTER-CLOSE LATENCY chip threshold (2026-09-23, "HONEST WARNINGS" item 1b): the
# engine-mode reaction-time measure (order time - the signal bar's own CLOSE, see
# _record_order) is expected to read ~30s in a healthy book -- this is the bar past
# which the SLOW LATENCY chip should actually fire for it, replacing the old raw
# latency_s > 10s check that engine mode could never pass (every 5m bar reads >=300s
# on that measure by construction, an honest-warnings false alarm in its own right).
AFTER_CLOSE_WARN_SEC = 60.0


def _latency_stats(vals):
    """{n,median_s,p95_s,max_s,last_s} over a plain list of floats, `vals[-1]` taken
    as the most recent (caller passes them in file/append order). Shared by
    _build_latency's two measures (latency_s and after_close_s) so both are computed
    identically."""
    if not vals:
        return {"n": 0, "median_s": None, "p95_s": None, "max_s": None, "last_s": None}
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    idx95 = min(n - 1, int(round(0.95 * (n - 1))))
    return {"n": n, "median_s": round(statistics.median(vals_sorted), 3),
           "p95_s": round(vals_sorted[idx95], 3), "max_s": round(vals_sorted[-1], 3),
           "last_s": round(vals[-1], 3)}


def _derived_after_close(o, log=print):
    """after_close_s for an orders.csv row that predates the column: latency_s minus the
    leg's own timeframe, for engine-mode rows only (the same rule _record_order applies
    when it writes the column). None when the row is not engine-mode, has no numeric
    latency_s, or the leg has no live timeframe. Never raises."""
    try:
        if str(o.get("signal_source") or "").strip().lower() != "engine":
            return None
        lat = o.get("latency_s")
        if lat in (None, ""):
            return None
        tf_sec = _leg_timeframe_seconds(o.get("leg"), log=log)
        if tf_sec is None:
            return None
        return round(float(lat) - tf_sec, 3)
    except Exception:
        return None


def _build_latency(orders, log=print):
    """{n,median_s,p95_s,max_s,last_s,after_close:{...,warn}} over today's orders.

    The top-level fields are latency_s (adapter order time - NT fill time, ET) --
    unchanged from before this fix, meaningful for ninjatrader-mode rows. `after_close`
    is the SEPARATE engine-mode reaction-time measure (order time - the signal bar's
    own CLOSE; see _record_order's own docstring for why latency_s reads an
    on-time engine order as ~5m/~1m "late") over whichever rows carry a numeric
    after_close_s -- empty (n=0, every stat None) on a book with no engine-mode orders
    today, e.g. a pure ninjatrader-mode day. `after_close.warn` is the ONE new
    HONEST-WARNINGS threshold: p95 after-close past AFTER_CLOSE_WARN_SEC (60s; a
    healthy book reads ~30s) -- see the web tab's SLOW LATENCY chip, which now reads
    this instead of the old raw-latency_s>10s check in engine mode.

    `orders` is assumed in file order (ascending by append time)."""
    try:
        vals, ac_vals = [], []
        for o in orders:
            v = o.get("latency_s")
            if v not in (None, ""):
                try:
                    vals.append(float(v))
                except Exception:
                    pass
            av = o.get("after_close_s")
            if av in (None, ""):
                # A row written BEFORE the after_close_s column existed (2026-09-23 and
                # earlier): derive it exactly as _record_order would have -- engine-mode
                # rows only, latency_s minus that leg's own bar length -- so the first
                # evening after the upgrade does not fall back to the bar-START reading
                # and raise SLOW LATENCY for orders that were in fact on time.
                av = _derived_after_close(o, log=log)
            if av not in (None, ""):
                try:
                    ac_vals.append(float(av))
                except Exception:
                    pass
        out = _latency_stats(vals)
        ac = _latency_stats(ac_vals)
        ac["warn"] = bool(ac["n"] and ac["p95_s"] is not None and ac["p95_s"] > AFTER_CLOSE_WARN_SEC)
        out["after_close"] = ac
        return out
    except Exception as e:
        log(f"[qqq-exec] latency build failed: {type(e).__name__}: {e}")
        return {"n": 0, "median_s": None, "p95_s": None, "max_s": None, "last_s": None,
               "after_close": {"n": 0, "median_s": None, "p95_s": None, "max_s": None,
                              "last_s": None, "warn": False}}


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
    them from checked/failed.

    RE-BASED ON WEBULL PARITY (2026-09-23, "HONEST WARNINGS" item 1d). `parity` is
    whichever summary actually applies to THIS book's own signal source: _build_doc
    now passes broker_parity (_broker_parity_summary -- engine-signal entries/exits vs
    Webull's own fill price or a tape reprice, see that function's docstring) instead
    of the old NinjaTrader-mirror summary (_parity_summary), because this book runs
    signal_source="engine" and therefore never had a NinjaTrader fill for the OLD
    summary to check anything against -- "0 live-captured trades parity-checked
    against NinjaTrader (need 10)" was permanently, structurally stale, never a real
    reading of this book's own health. Both summaries share the exact same
    checked/failed field names (see _parity_summary/_broker_parity_summary), so this
    function's own arithmetic is unchanged -- only which summary the caller hands it,
    and the wording below, moved. Every OTHER check here (feed uptime, rail trips,
    reprice coverage, days valid) is untouched."""
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
                           f"parity-checked against Webull (need {DAYS_REQUIRED})")
        if live_parity_failed > 0:
            missing.append(f"{live_parity_failed} live-captured trade(s) failed the "
                           f"Webull parity check")
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


def _build_price_status(cfg, state, log=print):
    """{"source": "WEBULL"/"YAHOO"/None, "age_sec": int|None} for the web tab's status
    panel. Engine mode prefers api.webull_stream's own LIVE tick (item 3) when it is
    demonstrably fresh -- genuinely near-real-time, unlike anything below -- else falls
    back to api.cloud_signal's own bar-source attribution (never a live call itself --
    a plain state.json read); NinjaTrader mode reports the source of the LAST fill/mark
    this tick actually priced (state['_px_source'], best-effort -- a tick with no fill
    and no open lot to mark has nothing to report).

    THE BAR-START BUG (2026-09-23, "HONEST WARNINGS" item 1c, same root cause as item
    1b's latency fix): the bar-source branch used to age off `newest_epoch` directly,
    which is the newest usable bar's OPENING instant (see _bar_close_age's own
    docstring) -- a 5-minute bar that just closed read as "~300s behind" for the next
    five minutes even though the feed was completely current. This now ages off that
    bar's CLOSE (start + its own timeframe, via _bar_close_age) instead -- what the
    owner's screenshot ("PRICE SOURCE WEBULL 389s behind") should have read as roughly
    the fetch/processing delay alone, not the bar's own width on top of it."""
    try:
        engine_mode = str(cfg.get("signal_source") or "engine").strip().lower() == "engine"
        if engine_mode:
            streamer = _qqq_stream_instance()
            if streamer is not None:
                try:
                    if streamer.is_fresh():
                        t = streamer.last_trade()
                        if t and t.get("price") is not None:
                            return {"source": "WEBULL", "age_sec": int(round(t.get("age") or 0.0))}
                except Exception as e:
                    log(f"[qqq-exec] price_status live stream read failed (falling back to "
                        f"the bar cache): {type(e).__name__}: {e}")
            cs = _cs_module()
            bs = cs.read_bar_source(cs.DEFAULT_PATHS) or {}
            best_tf, best = None, None
            for tf, info in bs.items():
                if info and (best is None or (info.get("checked_at") or "") > (best.get("checked_at") or "")):
                    best, best_tf = info, tf
            if not best:
                return {"source": None, "age_sec": None}
            age = _bar_close_age(best_tf, bar_source=bs, log=log)
            if age is None:
                # unknown timeframe (no TIMEFRAME_SECONDS entry) -- degrade to the old
                # bar-START measure rather than publish nothing at all.
                try:
                    age = max(0.0, time.time() - float(best.get("newest_epoch") or 0))
                except Exception:
                    age = None
            return {"source": (best.get("source") or "").upper() or None,
                   "age_sec": int(round(age)) if age is not None else None}
        src = state.get("_px_source")
        label = "WEBULL" if src == "webull_quote" else "NQ_RATIO" if src == "nq_ratio" else None
        return {"source": label, "age_sec": None}
    except Exception as e:
        log(f"[qqq-exec] price_status build failed: {type(e).__name__}: {e}")
        return {"source": None, "age_sec": None}


def _build_run_location():
    """{"label": "CLOUD"/"THIS PC", "host": ...} for the web tab's status panel.
    EDGELOG_RUN_LOCATION ("cloud"/"pc") is the original explicit opt-in; EDGELOG_HOST_ROLE
    ("cloud"/"pc", 2026-09-13 Oracle-VM staging) is the deploy/cloud/edgelog.env.example
    name for the same switch -- either sets CLOUD, so the systemd unit's .env only needs
    to set one. Absent both, the hostname is shown but always labelled THIS PC -- there
    is no reliable host-only signal for "running in the cloud"."""
    host = None
    try:
        import platform as _platform
        host = _platform.node() or None
    except Exception:
        host = None
    loc_env = str(os.environ.get("EDGELOG_RUN_LOCATION") or "").strip().lower()
    role_env = str(os.environ.get("EDGELOG_HOST_ROLE") or "").strip().lower()
    label = "CLOUD" if "cloud" in (loc_env, role_env) else "THIS PC"
    return {"label": label, "host": host}


def _build_keel_status(log=print):
    """Best-effort read of every KEEL-overlaid leg's small JSON summary (see
    api/cloud_signal.py's keel_paths and tools/keel_live_state.py, the nightly builder)
    for the web tab's NOISE LEGS row (design doc G: "the state's freshness"). Returns
    {exec_leg_key: {"version", "trained_through", "n_trades"}} -- keyed by THIS
    module's own exec leg names (ENGINE_LEG_MAP's values, e.g. "NOISE"), not
    cloud_signal's engine keys (e.g. "NOISE_382"), since that is what the published doc's
    other per-leg fields (positions, cum_pnl, ...) are already keyed by. Never raises,
    never touches the (potentially large) pickled state file itself -- only the small
    JSON sidecar. Returns {} on any import/read failure, which the web tab already
    treats as "no freshness data" (same null-safety as every other optional field on
    this doc)."""
    out = {}
    try:
        from . import cloud_signal as _cs
    except Exception as e:
        log(f"[qqq-exec] KEEL status: cloud_signal unavailable ({type(e).__name__}: {e})")
        return out
    for engine_key, leg_cfg in (getattr(_cs, "CROWN_LEGS", None) or {}).items():
        keel_cfg = (leg_cfg or {}).get("keel")
        if not keel_cfg:
            continue
        exec_key = ENGINE_LEG_MAP.get(engine_key, engine_key)
        summary_path = keel_cfg.get("summary_path", "")
        if not summary_path or not os.path.exists(summary_path):
            continue
        try:
            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)
            # ITEM D (2026-09-25): "trained through" means the DATA, not the last
            # trade -- "data_through" (the ET date of the last BAR used, see
            # tools/keel_live_state.py's build()) stays current even on a quiet day
            # with no NQ #382 trade, when "last_nq_session" (the last TRADE's date,
            # ml_keel.py's own field, untouched by this change) would otherwise sit
            # behind and make the web tab show a stale-looking date. Fall back to
            # last_nq_session for a summary written before data_through existed.
            # last_trade_session is published separately (never dropped) since it is
            # still meaningful on its own -- "when did NOISE_382 last actually trade".
            out[exec_key] = {
                "version": summary.get("version") or keel_cfg.get("version"),
                "trained_through": summary.get("data_through") or summary.get("last_nq_session"),
                "last_trade_session": summary.get("last_nq_session"),
                "n_trades": summary.get("n_trades"),
            }
        except Exception as e:
            log(f"[qqq-exec] KEEL status unreadable for {engine_key}: {type(e).__name__}: {e}")
    return out


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

    # ENGINE-VS-BROKER PARITY (feature #56): a SEPARATE read from the NT parity above,
    # for every row that never had a NinjaTrader fill to mirror (signal_source !=
    # "ninjatrader") -- must run AFTER the reprice merge just above, since it falls back
    # to real_entry_px/real_exit_px when there is no captured Webull fill. A row that
    # genuinely mirrors NinjaTrader is left exactly as _trade_parity already computed it
    # -- see _apply_broker_parity/_broker_trade_parity's own docstrings for why.
    broker_by_base = _broker_orders_by_base(_all_broker_orders_from_csv())
    _apply_broker_parity(trades_all, broker_by_base, log=log)
    broker_parity = _broker_parity_summary(trades_all)

    # BOOK-ONLY MARKING (2026-09-23, owner: "mark the book only trades" -- Webull
    # refused NOISE's 10:10 ET short, HTTP 417 OPENAPI_GENERATE_NEW_SHORT_POSITION,
    # and the book still counted +$4.90 for it as though Webull had made it too).
    # A SEPARATE read from the parity check above -- "did any shares ever reach the
    # broker" rather than "did the price match" -- reusing the SAME broker_by_base
    # join, never a second one. See _apply_book_only/_book_only_status.
    _apply_book_only(trades_all, broker_by_base, log=log)
    book_only_summary = _book_only_summary(trades_all)

    # The curve is built AFTER the merge, so an exit the adapter could not mark counts at
    # its tape-repriced real_pnl -- exactly as the web tab counts it (see _curve_pnl).
    cum_pnl = _cum_pnl_by_leg(trades_all)

    feed_days = _build_feed_days(state)
    ratio_hist = (state.get("ratio_hist") or [])[-500:]
    ratio_health = _build_ratio_health(state, _now_et(), cfg=cfg, log=log)
    unrl_by_leg = state.get("_unrl_by_leg") or {}
    positions = {}
    for leg, lot in state.get("legs", {}).items():
        positions[leg] = {"side": lot["side"], "shares": lot["shares_remaining"],
                          "entry_px": lot["entry_px"], "entry_ts": lot["entry_ts"],
                          "unrealized": unrl_by_leg.get(leg, 0.0),
                          # TRADE IDENTITY (2026-09-14): which strategy trade this lot
                          # is -- the only EXIT that may close it carries this id.
                          "trade_id": lot.get("trade_id"),
                          "entry_ref_time": lot.get("entry_ref_time"),
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
    # HONEST WARNINGS item 1d (2026-09-23): broker_parity (engine-vs-Webull), not the
    # NinjaTrader-mirror `parity` -- see _build_readiness's own docstring for why.
    readiness = _build_readiness(feed_days, broker_parity, reprice, state, log=log)
    # HEALTH (2026-09-08 fix): the adapter's own operational vitals -- publish failures
    # and the largest tick-loop stall today -- independent of trading/feed logic, so a
    # silent infrastructure problem (Firestore down, the loop stalling) is visible on the
    # web tab even on a day nothing else went wrong. See _record_publish_result /
    # _track_tick_gap and module docstring feature (2).
    health = {"publish_fail_today": int(state.get("publish_fail_today", 0) or 0),
             "last_publish_ok_et": state.get("last_publish_ok_et"),
             "tick_gap_max_s_today": float(state.get("tick_gap_max_s_today", 0.0) or 0.0)}

    # STATUS FOR THE PHONE (2026-09-13): plain-language read of what is currently
    # driving the shadow book, for the web tab's top-of-tab status panel. Never
    # touches NinjaTrader/NQ files to build the engine-mode branch (see
    # _build_price_status / _build_run_location).
    price_status = _build_price_status(cfg, state, log=log)
    run_location = _build_run_location()
    # LIVE POSITIONS + ACCOUNT EQUITY (2026-09-23, item 3).
    positions_live = _build_positions_live(state, cfg, log=log)
    equity = _build_equity_status(state, _now_et(), log=log)
    keel_status = _build_keel_status(log=log)

    return {
        "mode": cfg.get("mode"), "updated_at": _now_et().strftime("%Y-%m-%d %H:%M:%S"),
        "live_from": LIVE_FROM,
        "signal_source": cfg.get("signal_source"),
        "price_status": price_status,
        "run_location": run_location,
        # KEEL OVERLAY (2026-09-23, design doc G): {exec_leg_key: {version,
        # trained_through, n_trades}} for every engine leg that declares a "keel"
        # block in api/cloud_signal.py's CROWN_LEGS -- see _build_keel_status. {} (the
        # web tab already degrades cleanly) when cloud_signal cannot be imported or no
        # leg has one.
        "keel": keel_status,
        "feed_stale": bool(feed_stale), "breaker_tripped": bool(state.get("breaker_tripped")),
        "px_feed_stale": bool(state.get("px_feed_stale")),
        "kill": bool(state.get("kill_done")), "calib": state.get("calib"),
        "positions": positions,
        # LIVE POSITIONS + ACCOUNT EQUITY (2026-09-23, item 3, owner: "since we are
        # live with live pricing, can you show the positions live? and potentially
        # equity as well"). Sibling to "positions" above, not a replacement -- see
        # _build_positions_live/_build_equity_status for why the P&L figure here can
        # differ slightly from state['_unrl_by_leg']'s bar-close mark.
        "positions_live": positions_live,
        "equity": equity,
        "today": {"orders": orders, "trades": trades,
                  "realized_pnl": state.get("realized_pnl_today", 0.0),
                  "unrealized_pnl": round(unrealized, 2)},
        "trades_all": trades_all,
        "parity": parity,
        # ENGINE-VS-BROKER PARITY (feature #56): sibling summary to "parity" above --
        # see _broker_parity_summary. Untouched NT rows never contribute to this one.
        "broker_parity": broker_parity,
        # BOOK-ONLY (2026-09-23): sibling summary to "broker_parity" above -- book
        # vs broker totals, see _book_only_summary. Each trade in trades_all also
        # carries its own book_only/book_only_reason (see _apply_book_only).
        "book_only_summary": book_only_summary,
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
        # BROKER MIRROR (2026-09-13): api.webull_orders' own status, trimmed flat -- see
        # _build_broker_status. Lets the phone tab eventually show mode/creds/last
        # order/last error without a separate endpoint.
        "broker": _build_broker_status(state, log=log),
        # TRADE IDENTITY (2026-09-14): signals NOT applied because their trade id did not
        # check out (stale/foreign EXITs, id-less rows, ...) -- see TRADE_ID_ISSUES.
        "trade_ids": _build_trade_id_status(state, day),
        # LEASE (2026-09-13): this host's heartbeat for the cross-host guard (see
        # _check_lease) -- a second host reads THIS field to decide whether the shadow
        # book (and its broker mirror) is already running elsewhere.
        "lease": {"host_id": _lease_host_id(), "leased_at": time.time()},
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


# -- FIRESTORE USAGE COUNTERS (2026-09-14, FIX 1) ------------------------------------
# Plain attempt counts (not a Firestore-side audit) -- cheap, in-state bookkeeping so
# the owner can see roughly how many writes/reads this host is issuing per hour/day
# without opening the Firebase console. Logged once/hour by _maybe_log_fs_usage,
# called once per tick from tick() itself.
def _track_fs_write(state, n=1):
    try:
        state["_fs_writes_today"] = int(state.get("_fs_writes_today", 0) or 0) + n
        state["_fs_writes_hour"] = int(state.get("_fs_writes_hour", 0) or 0) + n
    except Exception:
        pass


def _track_fs_read(state, n=1):
    try:
        state["_fs_reads_today"] = int(state.get("_fs_reads_today", 0) or 0) + n
        state["_fs_reads_hour"] = int(state.get("_fs_reads_hour", 0) or 0) + n
    except Exception:
        pass


def _maybe_log_fs_usage(state, log=print):
    """Once per FS_USAGE_LOG_INTERVAL_SEC (~hourly), print + reset the hour bucket;
    the day bucket rolls at the ET calendar day like publish_fail_today. The FIRST
    call ever only SEEDS the hour clock (no log line, no reset) -- state["_fs_usage_
    day"]/["_fs_usage_hour_at"] start unset (None), which is distinguishable from a
    genuine prior day/hour, unlike testing a numeric bucket for truthiness (0 is a
    legitimate count, not "never happened"). Never raises -- a usage-counter bug must
    never affect trading logic."""
    try:
        today = _now_et().strftime("%Y-%m-%d")
        prior_day = state.get("_fs_usage_day")
        if prior_day is not None and prior_day != today:
            state["_fs_writes_today"] = 0
            state["_fs_reads_today"] = 0
        state["_fs_usage_day"] = today

        now = time.time()
        last = state.get("_fs_usage_hour_at")
        if last is None:
            state["_fs_usage_hour_at"] = now   # first call ever -- seed only
            return
        if now - float(last) < FS_USAGE_LOG_INTERVAL_SEC:
            return
        w_hr = int(state.get("_fs_writes_hour", 0) or 0)
        r_hr = int(state.get("_fs_reads_hour", 0) or 0)
        w_day = int(state.get("_fs_writes_today", 0) or 0)
        r_day = int(state.get("_fs_reads_today", 0) or 0)
        log(f"[qqq-exec] Firestore usage last hour: writes={w_hr} reads={r_hr} "
            f"(today so far: writes={w_day} reads={r_day})")
        state["_fs_usage_hour_at"] = now
        state["_fs_writes_hour"] = 0
        state["_fs_reads_hour"] = 0
    except Exception as e:
        log(f"[qqq-exec] Firestore usage tracking failed: {type(e).__name__}: {e}")


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
        self._inflight = None       # the write currently on the worker, if any

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

    def drop(self, uid):
        """Forget the pending doc for `uid` -- a loop that stood down must not publish the
        doc it queued just before (see qqq_exec_thread). _do_set refuses it anyway."""
        with self._lock:
            self._pending.pop(uid, None)

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
        this never raises -- failure is recorded via _record_publish_result, not thrown.

        ONE WRITE AT A TIME (2026-09-14): a write still running past its wait (a hung
        Firestore call) makes this one fail at once instead of queueing behind it. The next
        tick carries a newer doc anyway, and a backlog of stale docs -- each possibly a
        compare-and-set transaction -- would otherwise all go out when the hang clears."""
        prev = self._inflight
        if prev is not None and not prev.done():
            _record_publish_result(state, False, err="previous publish still running", log=log)
            return
        fut = self._ex.submit(self._do_set, db, uid, doc)
        self._inflight = fut
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
        # LEASE PROTOCOL step 3 (2026-09-14): a lease-managed process's publish IS its lease
        # renewal, so it decides HERE, at the moment the write actually goes out (a doc can
        # wait behind a slow write), whether a plain overwrite is still safe -- see
        # _LeaseHolder.write_mode. mode None = not lease-managed: exactly the old publish.
        mode = _LEASE.write_mode(uid)
        if mode is None:
            _plain_set(ref, doc)
            return
        if mode == "skip":
            raise _LeaseNotHeld(f"not published -- this process no longer holds the lease "
                                f"({_LEASE.lost_reason})")
        stamp = time.time()
        doc = dict(doc)
        doc["lease"] = {"host_id": _lease_host_id(), "leased_at": stamp}
        if mode == "cas":
            try:
                ok, reason = _cas_publish(db, ref, doc)
            except Exception as e:
                # Firestore TROUBLE, not a refusal -- e.g. the daily read quota is spent while
                # writes still work, which has happened twice. Giving up here would freeze the
                # phone tab. Inside the hold bound a plain renewal is exactly as safe as ever;
                # past it, publish the status WITHOUT the lease field, which cannot overwrite
                # another host's claim (and renews nothing, so broker sends stay blocked).
                if not _LEASE.within_hold():
                    _plain_set(ref, {k: v for k, v in doc.items() if k != "lease"},
                               single_attempt=True, top_level_merge=True)
                    raise _LeaseNotRenewed(f"published WITHOUT renewing the lease -- lease "
                                           f"check failed ({type(e).__name__}: {e})")
            else:
                if not ok:
                    _LEASE.mark_lost(reason)
                    raise _LeaseNotHeld(f"not published -- {reason}")
                _LEASE.note_committed(stamp, checked=True)
                return
        # A plain renewal: ONE attempt bounded by its deadline (see _plain_set), which is
        # what write_mode's timing bound assumes.
        _plain_set(ref, doc, single_attempt=True)
        _LEASE.note_committed(stamp)


def _plain_set(ref, doc, single_attempt=False, top_level_merge=False):
    """set() the status doc. `single_attempt`: retry=None, so the write lands within its
    PUBLISH_TIMEOUT_SEC deadline or not at all -- the client's default commit retry re-sends
    for up to a minute. `top_level_merge`: replace only the top-level fields present, leaving
    the rest of the doc (the lease) as it is."""
    kwargs = {"timeout": PUBLISH_TIMEOUT_SEC}
    if single_attempt:
        kwargs["retry"] = None
    if top_level_merge:
        kwargs["merge"] = list(doc)
    try:
        ref.set(doc, **kwargs)
    except TypeError:
        # Some client stubs (and the smoke test's stub db) don't accept a `timeout`
        # kwarg on set() -- the ThreadPoolExecutor future in write_one is the real hard
        # timeout backstop regardless, this is just for compatibility.
        if top_level_merge:
            ref.set(doc, merge=list(doc))
        else:
            ref.set(doc)


_publisher = _Publisher()


def _publish_fingerprint(doc):
    """A stable content signature of `doc`, used by _should_publish to decide whether
    THIS tick's publish is a MEANINGFUL CHANGE worth sending immediately (2026-09-14,
    FIX 1).

    THE BUG THIS FIXES: hashing the WHOLE doc (the old approach) never actually
    throttled anything, because doc["updated_at"] and doc["lease"]["leased_at"] are
    reassigned to the current wall-clock time on EVERY tick -- so the hash differed
    every single tick regardless of whether anything real happened, at up to 17,280
    ticks/day. Simply excluding those two timestamp fields is not enough either: several
    OTHER fields legitimately change nearly every tick too (feed_days' per-tick
    counters, live-quote-derived price_status, per-leg unrealized marks, the health/
    tick-gap counters, ratio history) and would silently re-defeat the throttle the
    same way. So this is a deliberate ALLOWLIST of discrete/structural fields, not
    "whole doc minus a blocklist" -- exactly the "meaningful change" list from the fix
    spec: a lot opened/closed, an order sent/filled/rejected, a rail tripped, a
    halt/block toggled, mode change, a new signal consumed, staleness state flip.
    Everything else rides the periodic interval instead (see _should_publish)."""
    positions = {leg: {"side": p.get("side"), "shares": p.get("shares")}
                for leg, p in (doc.get("positions") or {}).items()}
    broker = doc.get("broker") or {}
    last_order = broker.get("last_order") or {}
    last_reconcile = broker.get("last_reconcile_result") or {}
    today = doc.get("today") or {}
    return {
        "mode": doc.get("mode"),
        "signal_source": doc.get("signal_source"),
        "feed_stale": doc.get("feed_stale"),
        "px_feed_stale": doc.get("px_feed_stale"),
        "breaker_tripped": doc.get("breaker_tripped"),
        "kill": doc.get("kill"),
        "positions": positions,
        "orders_count_today": len(today.get("orders") or []),
        "trades_count_today": len(today.get("trades") or []),
        "events_count": len(doc.get("events") or []),
        "broker_requested_mode": broker.get("requested_mode"),
        "broker_effective_mode": broker.get("effective_mode"),
        "broker_halted": broker.get("halted"),
        "broker_halt_reason": broker.get("halt_reason"),
        "broker_last_order": {"leg": last_order.get("leg"), "side": last_order.get("side"),
                              "qty": last_order.get("qty"), "intent": last_order.get("intent"),
                              "mode": last_order.get("mode"), "ok": last_order.get("ok"),
                              "sent": last_order.get("sent")},
        "broker_lease_ok_to_send": broker.get("lease_ok_to_send"),
        "broker_last_reconcile_ok": last_reconcile.get("ok"),
    }


def _should_publish(state, doc, force=False, cfg=None):
    """(should, hash, now). `should` is True if the doc's FINGERPRINT (see
    _publish_fingerprint -- deliberately not the whole doc) differs from the
    last-published one, or `force`, or the applicable interval has elapsed since the
    last publish. Signature unchanged from before this fix (state, doc, force=) other
    than the new OPTIONAL `cfg` -- every existing caller that doesn't pass it keeps
    working off the module-level defaults.

    INTERVAL DEPENDS ON WHETHER THE BROKER IS ARMED (2026-09-14, FIX 1, revised after
    aaca82b's lease-renewal protocol landed): every ACTUAL publish is also this
    process's lease renewal (_Publisher._do_set / _LeaseHolder) -- once broker mode is
    PAPER/LIVE, api.webull_orders' own send gate (_LeaseHolder.send_gate) blocks a real
    order the moment this host's last COMMITTED stamp is older than
    LEASE_SEND_MAX_AGE_SEC (30s). So while armed, this ignores the configured session/
    off-session intervals entirely (they would starve that renewal and self-block every
    order) and instead publishes at least every publish_interval_armed_sec (default
    20s, comfortably under that 30s bound). While NOT armed (OFF -- today's actual
    setting, and the state at any point before the owner flips the switch), there is no
    send-gate risk, so the original, more relaxed session(60s)/off-session(600s)
    interval applies, both owner-configurable via cfg (see DEFAULT_CONFIG).

    LIVE POSITIONS CEILING (2026-09-23, item 3's Firestore-quota rule): "live marks may
    republish at most every 10s, only during market hours and only while a position is
    open". positions_live/equity are deliberately NOT in _publish_fingerprint's
    allowlist (a live price/mark tick must never itself force an immediate publish --
    same reasoning as unrealized_pnl/price_status already being excluded there), so
    without this they would only ever refresh on whatever OTHER interval applied (up
    to 600s off-session, or 20s once armed) -- stale for a card whose whole point is to
    look live. Whenever the book is in-session AND doc["positions"] is non-empty, the
    interval computed above is tightened to publish_interval_position_open_sec
    (default 10s) if that would be SHORTER -- never longer, and never outside that
    narrow window (flat, or off-hours, keep whichever interval already applied)."""
    h = str(hash(json.dumps(_publish_fingerprint(doc), sort_keys=True, default=str)))
    now = time.time()
    broker_mode = (doc.get("broker") or {}).get("effective_mode")
    armed = broker_mode in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE)
    in_session = _in_market_window(_now_et())
    if armed:
        interval = _cfg_num(cfg, "publish_interval_armed_sec", PUBLISH_INTERVAL_ARMED_SEC)
    else:
        interval = _cfg_num(cfg, "publish_interval_session_sec", PUBLISH_INTERVAL_SESSION_SEC) if in_session \
            else _cfg_num(cfg, "publish_interval_offhours_sec", PUBLISH_INTERVAL_OFFHOURS_SEC)
    if in_session and doc.get("positions"):
        position_open_interval = _cfg_num(cfg, "publish_interval_position_open_sec",
                                          PUBLISH_INTERVAL_POSITION_OPEN_SEC)
        interval = min(interval, position_open_interval)
    should = force or h != state.get("last_doc_hash") or now - state.get("last_publish", 0) >= interval
    return should, h, now


def publish_async(db, uid, doc, state, force=False, log=print, cfg=None):
    """Non-blocking publish for the live tick loop -- enqueues on the background
    _Publisher thread and returns immediately regardless of Firestore's health. Never
    raises. See _should_publish for the (2026-09-14, FIX 1) throttle this rides on --
    every write that actually goes out still flows through the existing _Publisher /
    _LeaseHolder machinery unchanged (this never bypasses it with a side-channel
    write), so lease renewal semantics are exactly as before this fix."""
    try:
        should, h, now = _should_publish(state, doc, force=force, cfg=cfg)
        if not should:
            return
        state["last_doc_hash"] = h
        state["last_publish"] = now
        _publisher.start(log=log)
        _publisher.submit(db, uid, doc, state, log=log)
        _track_fs_write(state)
    except Exception as e:
        log(f"[qqq-exec] publish enqueue failed: {type(e).__name__}: {e}")


def publish_now(db, uid, doc, state, force=True, log=print, cfg=None):
    """Synchronous publish for --once: the CLI process exits right after this call, so
    there is no later tick for the async publisher thread to flush a queued doc to. Still
    bounded to PUBLISH_TIMEOUT_SEC (via the same _Publisher.write_one path) so a dead
    Firestore endpoint can't hang the CLI either. `force=True` by default (a manual
    verification run should always publish), so this normally skips _should_publish's
    interval logic entirely."""
    should, h, now = _should_publish(state, doc, force=force, cfg=cfg)
    if not should:
        return
    state["last_doc_hash"] = h
    state["last_publish"] = now
    _publisher.write_one(db, uid, doc, state, log=log)
    _track_fs_write(state)


# -- one tick --------------------------------------------------------------------------------
def _lease_verify_cached(db, uid, state, cfg, log=print):
    """(ok, reason) -- same contract as _check_lease_for_broker, but the actual
    Firestore READ only happens when the cached verdict (state["_lease_verify_*"])
    is older than lease_verify_interval_sec (2026-09-14, FIX 1: default 30s, was
    every single 5s tick, ~17k reads/day). A cache MISS (no prior verdict, or stale)
    performs a fresh read and tracks it via _track_fs_read; a cache HIT reuses the
    last verdict and reads nothing. Never raises -- a crash inside the cached check
    fails CLOSED, exactly like _check_lease_for_broker's own contract."""
    now = time.time()
    age = now - float(state.get("_lease_verify_at", 0) or 0)
    interval = _cfg_num(cfg, "lease_verify_interval_sec", LEASE_VERIFY_INTERVAL_SEC)
    if state.get("_lease_verify_at") and age < interval:
        return state.get("_lease_verify_ok", False), state.get("_lease_verify_reason")
    try:
        ok, reason = _check_lease_for_broker(db, uid, log=log)
    except Exception as e:
        ok, reason = False, f"lease unverifiable: check crashed ({type(e).__name__}: {e})"
        log(f"[qqq-exec] broker lease check crashed ({type(e).__name__}: {e}) -- "
            "failing CLOSED for broker sends this tick")
    _track_fs_read(state)
    state["_lease_verify_at"] = now
    state["_lease_verify_ok"] = ok
    state["_lease_verify_reason"] = reason
    return ok, reason


def tick(*, fills_path=DEFAULT_FILLS, now=None, quote_fn=default_webull_quote,
         ratio_fn=default_ratio_calibration, cfg=None, state=None, force_calib=False,
         _now_wall=None, db=None, uid=None, log=print):
    """Run one adapter pass. Returns (cfg, state, doc) for callers/tests. Loads/saves
    config+state from disk unless the caller supplies them (tests inject fixed state).

    `force_calib`: attempt the ratio calibration even outside the market window. The
    live thread leaves this False (outside 09:25-16:05 ET it must stay a cheap no-op,
    not a yfinance call every TICK_SEC all night) but `--once` verification runs pass
    True so a dry run away from market hours still demonstrates/exercises pricing.

    `_now_wall`: real wall-clock seconds (time.time()-shaped) to use for tick-gap
    tracking (see _track_tick_gap), separate from `now` (which simulates ET market-hours
    logic and is often a fixed historical datetime in tests). Defaults to time.time().

    `db`/`uid` (2026-09-14): ONLY used to re-verify the cross-host lease for the broker
    mirror, every tick -- see _check_lease_for_broker. Both default to None (skips the
    check, same as "no Firestore configured") so every pre-2026-09-14 caller/test that
    builds cfg/state by hand and calls tick() directly keeps working unchanged. Neither
    is threaded any further than this -- publishing still happens in run_once/
    qqq_exec_thread exactly as before."""
    cfg = cfg if cfg is not None else load_config(log=log)
    state = state if state is not None else load_state(log=log)
    nowdt = now or _now_et()
    today = nowdt.strftime("%Y-%m-%d")
    _roll_day(state, today)
    state["_px_source"] = None

    # CROSS-HOST LEASE (2026-09-14): computed ONCE per tick, read later by every
    # _mirror_to_broker call this tick makes (via _open_lot/_reduce_lot/_close_all,
    # below and inside _mark_and_check_breaker) -- "check continuously, not only at
    # start" means re-derived fresh every time tick() runs, not cached across ticks.
    #
    # Only touches the broker adapter / Firestore AT ALL when this call actually carries
    # BOTH db and uid. The continuous production loop always does -- qqq_exec_thread and
    # run_once both pass theirs straight through (see their own docstrings) -- so this
    # cannot weaken the safety guarantee there. Every caller/test that builds cfg/state
    # by hand and calls tick() with neither (every pre-2026-09-14 test does exactly this,
    # and there are dozens) skips this block entirely: _get_broker_adapter() is NOT
    # constructed, no local webull_orders file is read, and state["_broker_lease_ok"]
    # stays unset, which _mirror_to_broker's own state.get(..., True) default already
    # reads as "proceed" -- the exact pre-2026-09-14 behaviour. Skipping this for a bare
    # manual `--once` run with no --uid is an accepted, narrow gap (a deliberate,
    # supervised one-off, not the unattended multi-hour double-run this fix targets).
    if db is not None and uid:
        try:
            broker_mode, _broker_mode_reason = _get_broker_adapter(log=log).effective_mode()
        except Exception as e:
            log(f"[qqq-exec] could not read broker effective_mode ({type(e).__name__}: {e}) -- "
                "treating as armed and failing CLOSED for broker sends this tick")
            broker_mode = webull_orders.MODE_PAPER   # unknown -- assume the stricter case
        if broker_mode in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
            # LEASE VERIFY CACHE (2026-09-14, FIX 1): re-reads Firestore at most every
            # lease_verify_interval_sec instead of every 5s tick -- see
            # _lease_verify_cached's own docstring.
            lease_ok, lease_reason = _lease_verify_cached(db, uid, state, cfg, log=log)
            # LEASE PROTOCOL step 5 (2026-09-14, aaca82b): the doc not naming another
            # host is not enough for a lease-managed loop -- its OWN last committed
            # stamp must be fresh too, or a host whose claim never landed could send.
            # None = not lease-managed (a direct tick() call), which keeps the cached
            # check above as the whole gate. Always checked FRESH (cheap, local, no
            # Firestore read) regardless of the cache above, so caching the doc-level
            # check can never widen this tighter, always-current guard.
            local_gate = _LEASE.send_gate(uid)
            if lease_ok and local_gate is not None and not local_gate[0]:
                lease_ok, lease_reason = local_gate
        else:
            lease_ok, lease_reason = True, None
        state["_broker_lease_ok"] = lease_ok
        state["_broker_lease_reason"] = lease_reason

    # EVENT TIMELINE (feature #52): "boot" fires once per PROCESS start (a state.json
    # flag would only ever fire once across every future restart).
    if not _PROCESS["booted"]:
        _log_event(state, "boot", "QQQ SHADOW adapter started", log=log)
        # STARTUP GUARD (2026-09-13): a process restart is also when NinjaTrader
        # strategies typically get re-enabled by hand -- see _relaunch_recently.
        state["relaunch_at"] = nowdt.strftime("%Y-%m-%d %H:%M:%S")
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

    # Runs right after KILL so a flatten trigger is honoured even on a killed adapter --
    # webull_orders._check_rails lets a CLOSE through unconditionally for exactly this
    # reason ("a halted adapter must still be able to flatten").
    _maybe_flatten_orphan_broker(state, cfg, nowdt, log=log)

    src_mode = str(cfg.get("signal_source") or "engine").strip().lower()
    if src_mode not in ("engine", "ninjatrader"):
        src_mode = "engine"

    active = _in_market_window(nowdt)
    if src_mode == "engine":
        # ENGINE MODE: neither the fill feed nor the price feed check ever opens
        # fills.csv or the NQ 10s export here -- see _check_feed_engine/_engine_mark_price.
        feed_stale = _check_feed_engine(state, log=log) if active else state.get("feed_stale", False)
        px_feed_stale = feed_stale  # one heartbeat covers both signal and price freshness
        state["px_feed_stale"] = px_feed_stale
    else:
        feed_stale = _check_feed(state, fills_path, log=log) if active else state.get("feed_stale", False)
        px_feed_stale = (_check_px_feed(state, quote_fn=quote_fn, log=log) if active
                         else state.get("px_feed_stale", False))
    if active:
        _accumulate_feed_uptime(state, nowdt, feed_stale, log=log)
        _track_tick_gap(state, nowdt, now_wall=_now_wall, log=log)
        # EXPLICIT ZERO DAYS (feature #3): every active day gets a signals_days row even
        # if no signal ever fires, so "no signals today" is on the record rather than
        # indistinguishable from "the adapter never ran".
        _ensure_signals_day(state, today, log=log)

    if (active or force_calib) and not kill_present and src_mode == "ninjatrader":
        _maybe_calibrate(state, ratio_fn, log=log)   # engine mode never needs the NQ:QQQ ratio

    if active and not kill_present:
        entries_blocked = (state.get("breaker_tripped") or feed_stale or px_feed_stale
                          or kill_present)
        if src_mode == "engine":
            events = _consume_engine_signals(state, cfg, nowdt, log=log)
            if events:
                _route_engine_events(state, cfg, events, entries_blocked, log=log, now=nowdt)
        else:
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

    # BROKER HOUSEKEEPING (2026-09-14): daily P&L wiring for webull_orders' own
    # (previously dead) loss rail + FIX 2's reconcile scheduling. ONE
    # _get_broker_adapter() call feeds both -- see _run_broker_housekeeping's own
    # docstring for why this is consolidated into a single call site (keeping the
    # broker adapter untouched when tick() is exercised with no db/uid at all is a
    # SEPARATE, older guarantee -- see the CROSS-HOST LEASE block above -- this one is
    # independent of Firestore entirely and always runs).
    _run_broker_housekeeping(state, cfg, nowdt, active, log=log)
    # BROKER RE-SEND (2026-09-21): after housekeeping, so a reconcile that just cleared a
    # halt lets the OPEN it blocked go out in the same tick -- see _maybe_resend_broker_orders.
    _maybe_resend_broker_orders(state, cfg, nowdt, active, log=log)
    # BROKER FILL CAPTURE (feature #57, DEFERRED 2026-09-22): queued by _mirror_to_broker,
    # serviced here -- see _maybe_capture_broker_fills for why this is off the order path.
    _maybe_capture_broker_fills(state, cfg, nowdt, active, log=log)
    # ACCOUNT EQUITY (2026-09-23, item 3): self-gated (at boot, then ~once/min while the
    # market is open) -- see _maybe_read_account_equity's own docstring.
    _maybe_read_account_equity(state, cfg, nowdt, log=log)

    # REPRICE MERGE (feature #48 half) + EOD PHONE SUMMARY (feature #55): both are
    # once-per-ET-day, time-gated jobs that must never block or crash a tick -- see
    # _maybe_run_reprice / _maybe_send_eod_summary for the schedule.
    _maybe_run_reprice(state, nowdt, log=log)

    doc = _build_doc(cfg, state, feed_stale, unrealized, log=log)
    _maybe_send_eod_summary(state, doc, nowdt, log=log)
    _maybe_log_fs_usage(state, log=log)
    save_state(state, log=log)
    return cfg, state, doc


def run_once(uid=None, fills_path=DEFAULT_FILLS, db=None, log=print):
    """One tick (`--once`). Runs the book like any other path, so it obeys the same LEASE
    PROTOCOL (2026-09-14): refused while an adapter is serving on this host (a second copy
    would tick the same book with its own memory -- and mirror its own broker orders), and,
    when it publishes, refused while another host holds a fresh lease. While publishing it
    is lease-managed like the loop, so a claim that only failed open can neither overwrite
    another host's lease on publish nor send a broker order. Returns None when refused."""
    slot, why = _enter_host_slot(log=log)
    if slot is None:
        log(f"[qqq-exec] REFUSING --once: {why} -- a second copy of the book on one host "
            "would tick with its own memory")
        return None
    began = False
    try:
        if db is not None and uid:
            ok, reason, stamp = _claim_lease(db, uid, log=log)
            if not ok:
                log(f"[qqq-exec] REFUSING --once for {uid}: {reason}")
                return None
            _LEASE.begin(uid, stamp)
            began = True
        cfg, state, doc = tick(fills_path=fills_path, force_calib=True, db=db, uid=uid, log=log)
        log(f"[qqq-exec] tick complete: mode={cfg.get('mode')} feed_stale={doc['feed_stale']} "
            f"breaker={doc['breaker_tripped']} positions={list(doc['positions'].keys())} "
            f"realized={doc['today']['realized_pnl']} unrealized={doc['today']['unrealized_pnl']} "
            f"calib={doc.get('calib')}")
        if db is not None and uid:
            publish_now(db, uid, doc, state, force=True, log=log, cfg=cfg)
            log(f"[qqq-exec] published users/{uid}/meta/qqq_exec "
                f"(publish_fail_today={state.get('publish_fail_today', 0)})")
        return doc
    finally:
        if began:
            _LEASE.end("--once finished")
        _leave_host_slot(slot)


def _reconcile_broker_at_boot(log=print):
    """Called once per process start (both the standalone serve() path and the
    in-runner-thread fallback share this function, since both are "startup" from the
    broker adapter's point of view). Compares the broker's live position against the
    sum of this adapter's own lots that actually reached the broker (see
    api.webull_orders.OrderAdapter.reconcile()'s own docstring) and halts new broker
    OPEN intents on a mismatch OR a read failure/timeout (2026-09-14, FIX 2 -- this
    used to only halt on a mismatch, silently doing nothing if the broker simply could
    not be reached). See _maybe_run_broker_reconcile for the PERIODIC (not just boot)
    half of this fix, run every tick thereafter. Never raises: a reconcile problem must
    not stop the shadow book itself from ticking."""
    try:
        adapter = _get_broker_adapter(log=log)
        result = _reconcile_with_timeout(adapter, log=log)
        if result is None:
            return  # OFF mode, or no broker client -- nothing to reconcile against
        if result.get("ok"):
            log("[qqq-exec] broker reconcile OK at boot")
        elif result.get("error"):
            log(f"[qqq-exec] BROKER RECONCILE READ FAILURE at boot -- the broker order "
                f"adapter halts new entries until a later reconcile succeeds: "
                f"{result.get('error')}")
        else:
            log(f"[qqq-exec] BROKER RECONCILE MISMATCH at boot -- the broker order "
                f"adapter halts new entries until a later reconcile succeeds: "
                f"{result.get('mismatches')}")
    except Exception as e:
        log(f"[qqq-exec] broker reconcile at boot failed (non-fatal): {type(e).__name__}: {e}")


# -- runner thread hook (mirrors api.runner._bridge_watchdog_thread) ---------------------
def qqq_exec_thread(db, uids, stop=None, log=print, on_tick=None):
    """Own thread, ticking every TICK_SEC -- never blocks the runner's main loop and
    never takes it down. Publishes to every allow-listed uid each tick that changed,
    at least once a minute regardless (see _publish's force/throttle logic).

    THE ONLY LOOP THAT RUNS THE BOOK (2026-09-14): serve() runs it in the standalone
    process and api/runner.py runs it as the in-process fallback, so the LEASE PROTOCOL
    lives here, where neither can skip it (tools/qqq_failover_sim.py scenario D was the
    fallback ticking, publishing and then reading itself as the lease holder). Before the
    first tick: take this host's serving slot, then claim the cross-host lease by
    compare-and-set; a refused claim returns without ticking and leaves a STANDBY marker.
    Every tick after that: stop at once if the lease was lost (the publisher discovers that
    when a compare-and-set finds another host's fresh lease), see _stand_down.

    `state` here is one shared adapter state across every uid in `uids` (same as every
    other field on it, e.g. open lots/legs), so the lease is claimed and checked against
    the FIRST uid only; in practice this list is always exactly the one owner uid
    (api/runner.py builds it from --allow-uid), never a genuine multi-tenant fan-out.
    With no db (tests, offline tools) there is nothing to hold a lease in and the loop
    runs unmanaged, exactly as before."""
    lease_uid = uids[0] if uids else None
    managed = db is not None and bool(lease_uid)
    slot, why = _enter_host_slot(log=log)
    if slot is None:
        log(f"[qqq-exec] REFUSING to run the shadow book: {why} -- one copy per host")
        return
    began = False
    try:
        if managed:
            ok, reason, stamp = _claim_lease(db, lease_uid, log=log)
            if not ok:
                log(f"[qqq-exec] REFUSING to run the shadow book for {lease_uid}: {reason} -- "
                    "standing by; this process will not tick, publish or send while another "
                    "host holds the lease")
                _note_standby(reason, log=log)
                return
            _LEASE.begin(lease_uid, stamp)
            began = True
            if stamp:
                _clear_standby()   # a claim that only failed open proves nothing yet
            log(f"[qqq-exec] lease {'claimed' if stamp else 'NOT confirmed yet (fail-open)'} "
                f"for host {_lease_host_id()!r}: {reason}")
        state = load_state(log=log)
        _reconcile_broker_at_boot(log=log)
        # LIVE WEBULL STREAM (2026-09-23, item 3; WINDOWED 2026-09-25, item B): only
        # from here on is this process actually SERVING (past the standby return
        # above) -- see _start_qqq_stream's own docstring for why the standby host
        # must never reach this line. No unconditional start here any more: the first
        # tick below (like every tick after it) starts/stops the stream through
        # _qqq_stream_window_step, kept in step with _stream_should_run's market-hours
        # window instead of running all night regardless of the clock (root cause of
        # the overnight SDK log flood -- see api/webull_stream.py's item A docstring).
        last_stream_start_attempt = 0.0
        last_pass = time.time()
        while stop is None or not stop.is_set():
            if managed:
                gap = time.time() - last_pass
                if gap > LEASE_STALE_SEC and _LEASE.held:
                    # SUSPENDED -- e.g. the PC slept with this process alive (2026-09-10: 21 h).
                    # Long enough for another host to have claimed legitimately, and nothing
                    # this process remembers says otherwise: re-claim BEFORE the next tick.
                    ok, reason, stamp = _claim_lease(db, lease_uid, log=log)
                    log(f"[qqq-exec] loop resumed after {gap:.0f}s -- re-claimed the lease "
                        f"before ticking: {reason}")
                    if not ok:
                        _LEASE.mark_lost(reason)
                    elif stamp:
                        _LEASE.note_committed(stamp, checked=True)
                if not _LEASE.held:
                    _stand_down(state, lease_uid, _LEASE.lost_reason, log=log)
                    return
            last_pass = time.time()
            try:
                cfg = load_config(log=log)
                # WINDOWED LIVE STREAM (item B, 2026-09-25) -- see
                # _qqq_stream_window_step's own docstring. Every tick, not just once at
                # boot, so the stream comes up/down with the market-hours window
                # (and the owner's live_stream_enabled kill switch) without needing a
                # restart.
                last_stream_start_attempt = _qqq_stream_window_step(
                    cfg, last_stream_start_attempt, log=log)
                cfg2, state, doc = tick(cfg=cfg, state=state, db=db, uid=lease_uid, log=log)
                for uid in uids:
                    publish_async(db, uid, doc, state, log=log, cfg=cfg2)
                save_state(state, log=log)
                _touch_serving_lock(log=log)
                if on_tick is not None:
                    on_tick(log=log)
            except Exception as e:
                log(f"[qqq-exec] tick failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            (stop.wait(TICK_SEC) if stop is not None else time.sleep(TICK_SEC))
    finally:
        # LIVE WEBULL STREAM (2026-09-23, item 3): unconditional and first -- covers a
        # normal loop exit, a mid-loop stand-down (_stand_down above returns through
        # this SAME try/finally) and any exception, so the stream is never left running
        # once this process is no longer serving. Safe even when nothing was started
        # (e.g. this call never got past the standby check above).
        _stop_qqq_stream(log=log)
        if began:
            _LEASE.end("the adapter loop exited")
            _publisher.drop(lease_uid)
        _leave_host_slot(slot)


# -- CLI ---------------------------------------------------------------------------------------
# -- STANDALONE SERVING (2026-09-09) -----------------------------------------------------
# WHY THIS EXISTS. The adapter used to ride as a thread inside the job runner, so its
# uptime was tied to a process that ~30 concurrent sessions restart all day to pick up
# code. On 2026-09-09 the adapter booted EIGHT times between 09:47 and 13:49 and the day
# recorded ~94% coverage against a 95% readiness bar -- the trial was being failed by
# deploys, not by anything wrong with the adapter. Uptime cannot be a property of the
# busiest process on the box.
#
# So the adapter runs as its OWN detached process. A runner boot no longer interrupts it;
# instead the runner calls ensure_standalone(), which starts one only if none is alive.
# That makes every fleet restart a no-op for the shadow book while still auto-reviving the
# adapter if it ever dies.
#
# LIVENESS is a heartbeat file, not a pid: a pid can be reused and a hard kill never gets
# to clean up. The serving process rewrites SERVING_LOCK every tick; anyone who sees a lock
# older than SERVING_STALE_SEC treats the slot as free. The heartbeat is only what OTHER
# processes read: the slot itself is an OS file lock (see _acquire_host_slot), because a
# race between two check-then-write heartbeats is two tickers with separate memory, and
# once the broker mirror is armed each would place its own orders.
SERVING_LOCK = os.path.join(OUT_DIR, "SERVING.lock")
SERVING_STALE_SEC = 120.0
QQQ_EXEC_VBS = os.path.join(EDGELOG_HOME, "_run_qqq_exec.vbs")  # Windows launcher only

# LEASE (2026-09-13, "PC and cloud can never both run"): a cross-HOST guard, unlike
# SERVING_LOCK above which only arbitrates between processes on the SAME machine. Two
# machines (the owner's PC and the future Oracle Cloud VM) could each pass their own
# local serving_alive() check while both believing they own the account -- the shared
# signal that actually spans hosts is the heartbeat this adapter publishes to Firestore
# (users/{uid}/meta/qqq_exec). See _check_lease / _build_doc's "lease" field.
#
# THIS VALUE is left exactly as aaca82b tuned it (do not bump for FIX 1's Firestore
# throttle, 2026-09-14): its whole renewal-timing bound (68s < 90s) already assumes
# it. FIX 1 DOES widen how long this host can go quiet while the broker is OFF
# (_should_publish backs the CONTENT interval off to publish_interval_offhours_sec,
# default 600s) -- meaning another host COULD legitimately claim the lease and start
# serving the shadow book within that window, sooner than the old ~5s-heartbeat
# behaviour allowed. Accepted as safe because nothing real is at stake while OFF: no
# broker order is ever gated on this doc's lease field in that mode (see
# _mirror_to_broker/_check_lease_for_broker, both only consulted once armed), so the
# worst case is a shadow-book bookkeeping handoff, not a duplicate real order. Once
# armed (PAPER/LIVE), _should_publish switches to publish_interval_armed_sec (default
# 20s, comfortably under LEASE_SEND_MAX_AGE_SEC) specifically so real publishes -- and
# therefore lease renewals -- keep landing often enough that this bound is never
# actually exercised while it would matter.
LEASE_STALE_SEC = 90.0

# LEASE PROTOCOL (2026-09-14). Until now the lease was advisory: serve() read it once, the
# runner's fallback thread never read it, nothing re-read it while serving, and every
# publish blind-wrote "lease: this host" -- so any process that published once became the
# holder and read "ours" from then on (tools/qqq_failover_sim.py scenarios D and E). The
# rules now, for every path that runs the book (serve(), the runner's fallback thread and
# --once all go through qqq_exec_thread / run_once):
#   1. ONE PROCESS PER HOST. Take this host's serving slot (_enter_host_slot) before touching
#      the lease, so only one process per host ever competes for it.
#   2. CLAIM BY COMPARE-AND-SET. The first stamp of ours is a Firestore transaction that
#      re-reads the lease and writes only if it is free, ours or stale (_claim_lease). A
#      refused process never ticks, and leaves a STANDBY marker so the runner on the same
#      host does not start a fallback copy either (standby_fresh, ensure_standalone).
#   3. RENEW WITHOUT CLOBBERING. Each publish still carries the lease (no extra Firestore
#      writes), but a plain overwrite is allowed only while our last COMMITTED stamp is
#      younger than LEASE_HOLD_SEC and a compare-and-set checked within LEASE_RECHECK_SEC;
#      otherwise the publish is itself a compare-and-set (_Publisher._do_set). The bound:
#      another host may claim only once our newest stamp is LEASE_STALE_SEC old, and a
#      plain write sent before LEASE_HOLD_SEC is a single attempt that lands within
#      PUBLISH_TIMEOUT_SEC -- 60 + 8 = 68 s < 90 s, the rest is clock-skew margin (keep the
#      hosts on NTP; beyond ~20 s of skew this bound no longer holds). A compare-and-set that
#      ERRORS (not refuses -- e.g. the read quota is spent) never freezes the phone tab: it
#      falls back to a plain renewal inside that bound, and past it to publishing the status
#      without the lease field.
#   4. STAND DOWN. When a compare-and-set finds another host's lease fresh, the loop stops
#      ticking and publishing at once and says so (log, event, ntfy) -- see _stand_down.
#   5. BROKER SENDS need this process's OWN latest landed stamp to be under
#      LEASE_SEND_MAX_AGE_SEC old, checked at tick start AND again right before each order
#      (_LeaseHolder.send_gate), on top of _check_lease_for_broker's per-tick read of the doc.
#      30 s leaves room for a worst-case first order (client build + account lookup +
#      connect, ~60 s of SDK timeouts) to reach Webull before another host may claim at 90 s.
# The fail-open / fail-closed split is unchanged: a Firestore problem never stops the shadow
# book from ticking (_check_lease, _claim_lease), and always blocks real broker sends
# (_check_lease_for_broker, send_gate). What this does NOT make safe is a TAKEOVER: open
# lots, the signal cursor and the order adapter's memory are still per-host files
# (scenarios A, B, C and F of the simulation). Known residual, needing both hosts armed:
# a process SUSPENDED between deciding on a plain renewal and sending it (a PC going to
# sleep in that instant) can overwrite a claim made while it slept; both hosts then renew
# until the next compare-and-set (<= LEASE_RECHECK_SEC). The durable fix is a server-side
# precondition on each renewal (update() with last_update_time) instead of the timing bound.
LEASE_HOLD_SEC = 60.0
LEASE_RECHECK_SEC = 30.0
LEASE_SEND_MAX_AGE_SEC = 30.0
LEASE_CLAIM_TIMEOUT_SEC = 15.0
HOST_SLOT_WAIT_SEC = 5.0


def _pid_alive(pid):
    """Is this process id running? Conservative: if we cannot tell, say YES, because the
    heartbeat age below is the real backstop and a false 'dead' would let two adapters run."""
    if not pid:
        return False
    try:
        if os.name == "nt":
            import ctypes
            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        # POSIX "no such process" is the one certain answer. Treating it as "cannot tell"
        # made a hard-killed unit's fresh heartbeat block its own systemd restart on Linux
        # for up to SERVING_STALE_SEC -- the 2026-09-11 Windows failure, on the VM.
        return False
    except Exception:
        return True


def serving_alive(path=None):
    """(alive, pid) for the current standalone serving process.

    TWO tests, because each covers the other's blind spot. The HEARTBEAT age catches a
    process that died without cleaning up, and it is what makes a reused pid harmless. The
    PID check catches the case that actually bit on 2026-09-11: a hard Stop-Process skips
    serve()'s cleanup, so the lock sits there FRESH for up to two minutes -- and the
    replacement launched five seconds later read that fresh lock, concluded another adapter
    was serving, and exited. The adapter was then simply absent, with nothing due to revive
    it until the next runner boot. A lock whose process is gone frees the slot immediately."""
    path = path or SERVING_LOCK
    try:
        age = time.time() - os.path.getmtime(path)
        if age > SERVING_STALE_SEC:
            return False, None
        with open(path, encoding="utf-8") as fh:
            pid = int((fh.read().strip().split() or ["0"])[0])
        if not _pid_alive(pid):
            return False, None
        return True, pid
    except Exception:
        return False, None


def _touch_serving_lock(log=print):
    try:
        os.makedirs(os.path.dirname(SERVING_LOCK) or ".", exist_ok=True)
        with open(SERVING_LOCK, "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()} {_now_et().strftime('%Y-%m-%d %H:%M:%S')}\n")
    except Exception as e:
        log(f"[qqq-exec] could not write serving lock: {type(e).__name__}: {e}")


# -- same-host serving slot (LEASE PROTOCOL step 1) -----------------------------------------
def _acquire_host_slot(log=print):
    """Open file handle holding THIS host's serving slot, or None if another holder has it.

    An exclusive, non-blocking OS lock on a file next to SERVING_LOCK -- msvcrt on Windows,
    flock on Linux -- kept for as long as the handle stays open. Unlike the heartbeat there
    is nothing stale to reason about: the OS drops the lock the moment the holder exits,
    hard kill included. Not re-entrant, on purpose: a second loop in the SAME process is a
    second copy of the book too. The lock is on its own file because a locked byte range
    cannot be read on Windows, and SERVING_LOCK is read by the runner and by
    tools/premarket_ensure.py."""
    path = SERVING_LOCK + ".mutex"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fh = open(path, "a+b")
    except Exception as e:
        log(f"[qqq-exec] could not open the serving slot {path}: {type(e).__name__}: {e}")
        return None
    try:
        try:
            import msvcrt
        except ImportError:
            msvcrt = None
        if msvcrt is not None:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        fh.close()
        return None


def _enter_host_slot(log=print):
    """(slot, reason) -- slot is the handle to pass to _leave_host_slot, or None with the
    reason this process may not run the book here. Checks the HEARTBEAT first, which is the
    only thing a pre-2026-09-14 adapter process writes (it takes no OS lock), then the lock,
    then starts this process's own heartbeat."""
    alive, pid = serving_alive()
    if alive and pid != os.getpid():
        return None, f"another adapter process (pid {pid}) is already serving on this host"
    # No live heartbeat, so a held lock is either a holder that has not written its first
    # heartbeat yet, or one that has just died -- and Windows can release a dead process's
    # lock a moment late. A relaunch right after a hard kill (2026-09-11 was exactly that)
    # must not give up on the first try and leave no adapter at all.
    deadline = time.time() + HOST_SLOT_WAIT_SEC
    slot = _acquire_host_slot(log=log)
    while slot is None and time.time() < deadline:
        time.sleep(0.25)
        slot = _acquire_host_slot(log=log)
    if slot is None:
        return None, "another adapter process on this host holds the serving slot"
    _touch_serving_lock(log=log)
    return slot, None


def _leave_host_slot(slot):
    """Remove our heartbeat (only if it still names this process) and release the slot."""
    if slot is None:
        return
    try:
        with open(SERVING_LOCK, encoding="utf-8") as fh:
            owner = int((fh.read().strip().split() or ["0"])[0])
        if owner == os.getpid():
            os.remove(SERVING_LOCK)
    except Exception:
        pass
    try:
        # Unlock explicitly before closing: on Linux a child forked while we held the lock
        # (the runner's process pools) shares it, and closing only OUR descriptor would leave
        # it locked until that child exits.
        try:
            import msvcrt
        except ImportError:
            msvcrt = None
        if msvcrt is not None:
            slot.seek(0)
            msvcrt.locking(slot.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(slot.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        slot.close()
    except Exception:
        pass


# -- STANDBY marker (LEASE PROTOCOL step 2) ---------------------------------------------------
# A process that is refused the cross-host lease exits without ticking (on the VM systemd
# restarts it every ~15 s, which is how it keeps re-checking), so between refusals nothing
# on this host is "serving" -- and ensure_standalone() used to read exactly that as "start
# the runner's own copy" (simulation scenario D). The marker is how a refused adapter says
# "someone here is already waiting for the lease". Freshness is by age alone: the process
# that wrote it has usually exited by design.
def _standby_path():
    return SERVING_LOCK + ".standby"


def _note_standby(reason, log=print):
    try:
        path = _standby_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()} {_now_et().strftime('%Y-%m-%d %H:%M:%S')} {reason}\n")
    except Exception as e:
        log(f"[qqq-exec] could not write the standby marker: {type(e).__name__}: {e}")


def _clear_standby():
    try:
        os.remove(_standby_path())
    except Exception:
        pass


def standby_fresh(path=None):
    """(fresh, text): did an adapter on this host get refused the lease within the last
    SERVING_STALE_SEC? Never raises."""
    path = path or _standby_path()
    try:
        if time.time() - os.path.getmtime(path) > SERVING_STALE_SEC:
            return False, None
        with open(path, encoding="utf-8") as fh:
            return True, fh.read().strip()
    except Exception:
        return False, None


def ensure_standalone(log=print, vbs=None):
    """Called by the runner at boot. Returns True when a standalone is serving (already
    running, or just launched), meaning the runner must NOT start its own thread.

    Launch is DETACHED via wscript, never a direct child: a process started from a session's
    console dies with that console and, worse, orphans into the 0xC0000142 popup loop that
    cost a day in 2026-09-01 (see memory edgelog-runner-launch-detached).

    LINUX (the Oracle Cloud VM): there is no wscript.exe and a bare detached subprocess()
    has no supervisor to restart it if it dies or the host reboots, so the chosen approach
    on Linux is a dedicated systemd unit (edgelog-qqq-exec.service -- see
    deploy/cloud/README.md and deploy/cloud/install.sh) that is always enabled, not a
    process this function launches. This function only checks the heartbeat there; if the
    unit is not yet up, it falls back to the in-runner thread exactly like the
    "no launcher" case below, and stops falling back once the unit's own heartbeat goes
    fresh.

    A unit REFUSED the cross-host lease (2026-09-14) counts as present: it exits without a
    heartbeat, and falling back here used to start a copy of the book in the runner that
    never checked the lease (tools/qqq_failover_sim.py scenario D). Its STANDBY marker keeps
    the runner's thread off, and on Windows keeps the runner from relaunching a standalone
    that would only be refused again. The fallback thread obeys the lease itself regardless
    (see qqq_exec_thread)."""
    alive, pid = serving_alive()
    if alive:
        log(f"[qqq-exec] standalone already serving (pid {pid}) -- runner thread stays off")
        return True
    standby, note = standby_fresh()
    if standby:
        log(f"[qqq-exec] a standalone on this host is STANDING BY for the cross-host lease "
            f"({note}) -- runner thread stays off")
        return True
    if os.name != "nt":
        log("[qqq-exec] not serving and this is not Windows -- on Linux the standalone "
            "adapter is supervised by systemd (edgelog-qqq-exec.service, see "
            "deploy/cloud/README.md), not launched from here; falling back to the "
            "in-runner thread until that unit is up")
        return False
    vbs = vbs or QQQ_EXEC_VBS
    if not os.path.exists(vbs):
        log(f"[qqq-exec] no launcher at {vbs} -- falling back to the in-runner thread")
        return False
    try:
        subprocess.Popen(["wscript.exe", vbs], close_fds=True,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        log(f"[qqq-exec] launched the standalone adapter via {vbs}")
        return True
    except Exception as e:
        log(f"[qqq-exec] standalone launch failed ({type(e).__name__}: {e}) -- "
            f"falling back to the in-runner thread")
        return False


def _lease_host_id():
    """This host's identity for the cross-host lease (see LEASE_STALE_SEC above).
    EDGELOG_HOST_ID lets the owner name a host explicitly (handy if two VMs ever share a
    hostname); absent that, the OS hostname is enough to tell "the PC" from "the cloud
    VM" -- there are only ever two candidates."""
    override = os.environ.get("EDGELOG_HOST_ID")
    if override and override.strip():
        return override.strip()
    try:
        import platform as _platform
        return _platform.node() or "unknown-host"
    except Exception:
        return "unknown-host"


def _check_lease(db, uid, log=print):
    """(ok, reason). ok=False means a DIFFERENT host's heartbeat is still fresh in the
    published users/{uid}/meta/qqq_exec doc's "lease" field -- refuse to serve so the
    owner's PC and the cloud VM can never both run the shadow book (and its broker
    mirror) against the same account at once.

    Fail-OPEN on any read problem (missing doc, missing lease field, unreadable
    timestamp, a Firestore read error): none of those may stop the host that already
    legitimately owns the lease, or the very first host ever to serve, from starting."""
    if db is None or not uid:
        return True, "no Firestore/uid configured -- lease check skipped"
    try:
        snap = db.collection("users").document(uid).collection("meta").document("qqq_exec").get()
        d = snap.to_dict() if getattr(snap, "exists", True) else None
    except Exception as e:
        log(f"[qqq-exec] lease check could not read Firestore ({type(e).__name__}: {e}) -- "
            "proceeding (fail-open)")
        return True, "lease read failed -- fail-open"
    return _lease_claimable(d, _lease_host_id(), time.time())


def _lease_of(doc):
    lease = (doc or {}).get("lease") if isinstance(doc, dict) else None
    return lease if isinstance(lease, dict) else {}


def _lease_claimable(doc, my_host, now):
    """(ok, reason) -- _check_lease's rule on an already-read doc, shared with _claim_lease
    and _cas_publish so the plain read and the compare-and-set can never disagree: only a
    DIFFERENT host's positively fresh stamp refuses; free, ours, stale, or a timestamp that
    is missing/unreadable (fail-open, see _check_lease) is claimable."""
    lease = _lease_of(doc)
    other_host = lease.get("host_id")
    leased_at = lease.get("leased_at")
    if not other_host or other_host == my_host or leased_at is None:
        return True, "lease free or already ours"
    try:
        age = now - float(leased_at)
    except (TypeError, ValueError):
        return True, "lease timestamp unreadable -- treating as free"
    if age > LEASE_STALE_SEC:
        return True, f"other host's lease is stale ({age:.0f}s old)"
    return False, f"host {other_host!r} holds a fresh lease ({age:.0f}s old)"


def _check_lease_for_broker(db, uid, log=print):
    """(ok, reason) -- gates whether THIS host's broker mirror may actually SEND an
    order this tick (see _mirror_to_broker). Re-checked every tick by tick(), never only
    at start (see that function's call into this).

    THIS IS DELIBERATELY THE OPPOSITE DEFAULT FROM _check_lease ABOVE. _check_lease
    fail-OPENs on any read problem because it only ever gates the harmless shadow book
    (SHADOW mode places no real order, so the worst case of a wrong "proceed" is a
    duplicate LOG). This function instead gates REAL broker orders once the broker mirror
    is armed (PAPER/LIVE) -- and this owner's Firestore free tier (50k reads/day) has
    already been exhausted twice, so a read failure here is not a hypothetical. Fail-OPEN
    in that world would let two hosts' broker mirrors both believe they own the account
    and both send. So: ok=True only when the lease is POSITIVELY verified safe (ours,
    genuinely free/never claimed, or another host's claim is provably stale); everything
    else -- a Firestore read error/timeout/exception, no db/uid configured at all (nothing
    to verify against), or a foreign claim whose leased_at is missing/unparseable (we can
    see someone else claims it but cannot tell if that claim is stale) -- returns
    ok=False with a "lease unverifiable" reason. A different host's lease that IS
    positively confirmed fresh also returns ok=False (they own it, not us), with its own,
    more specific reason. Never raises.

    OUR OWN lease counts only while it is fresh (2026-09-14, simulation scenario E): a stamp
    of ours older than LEASE_HOLD_SEC means our renewals stopped landing, and from
    LEASE_STALE_SEC another host may legitimately claim -- which is exactly when the old
    rule let BOTH pass, the last writer reading "ours" and the other host reading "stale"."""
    if db is None or not uid:
        return False, "lease unverifiable: no Firestore/uid configured"
    try:
        snap = db.collection("users").document(uid).collection("meta").document("qqq_exec").get()
        d = snap.to_dict() if getattr(snap, "exists", True) else None
    except Exception as e:
        log(f"[qqq-exec] broker lease check could not read Firestore ({type(e).__name__}: "
            f"{e}) -- suppressing broker sends this tick (fail-CLOSED for real orders)")
        return False, f"lease unverifiable: Firestore read failed ({type(e).__name__}: {e})"
    lease = _lease_of(d)
    other_host = lease.get("host_id")
    leased_at = lease.get("leased_at")
    my_host = _lease_host_id()
    if not other_host:
        return True, "lease ok (free or already ours)"
    if other_host == my_host:
        try:
            own_age = time.time() - float(leased_at)
        except (TypeError, ValueError):
            return False, "lease unverifiable: this host's own lease timestamp is missing or unreadable"
        if own_age > LEASE_HOLD_SEC:
            return False, (f"lease unverifiable: this host's own lease is {own_age:.0f}s old -- "
                           "its renewals are not landing, so another host may already have "
                           "taken over; broker sends blocked")
        return True, "lease ok (free or already ours)"
    if leased_at is None:
        return False, (f"lease unverifiable: host {other_host!r} claims the lease but its "
                       "timestamp is missing")
    try:
        age = time.time() - float(leased_at)
    except (TypeError, ValueError):
        return False, (f"lease unverifiable: host {other_host!r} claims the lease but its "
                       "timestamp is unreadable")
    if age > LEASE_STALE_SEC:
        return True, f"lease ok (other host {other_host!r}'s lease is stale, {age:.0f}s old)"
    return False, (f"host {other_host!r} holds a fresh lease ({age:.0f}s old) -- broker "
                   "sends blocked")


class _LeaseNotHeld(RuntimeError):
    """A publish this process must not make: it does not hold the lease (LEASE PROTOCOL)."""


class _LeaseNotRenewed(RuntimeError):
    """The status went out but the lease could not be renewed (see _Publisher._do_set)."""


class _LeaseHolder:
    """This process's own view of the cross-host lease -- see LEASE PROTOCOL above. Only a
    lease-managed loop (qqq_exec_thread with a db and a uid) calls begin(); until then every
    query answers None and callers behave exactly as they did before this existed (tests
    that drive tick() or the publisher directly, tools/qqq_failover_sim.py's hosts).

    Times are this host's wall clock, because the stamps other hosts judge are too."""

    def __init__(self):
        self._lock = threading.Lock()
        self.uid = None             # the uid whose lease this process manages
        self.held = False
        self.committed_at = 0.0     # leased_at of our newest stamp known to have landed
        self.checked_at = 0.0       # when a compare-and-set last confirmed the lease
        self.lost_reason = None

    def begin(self, uid, stamp=None):
        with self._lock:
            self.uid, self.held, self.lost_reason = uid, True, None
            self.committed_at = self.checked_at = float(stamp or 0.0)

    def end(self, reason):
        with self._lock:
            if self.held:
                self.held, self.lost_reason = False, reason

    mark_lost = end

    def note_committed(self, stamp, checked=False):
        with self._lock:
            if self.held:
                self.committed_at = max(self.committed_at, float(stamp))
                if checked:
                    self.checked_at = max(self.checked_at, float(stamp))

    def write_mode(self, uid):
        """How a publish to `uid` may go out right now: None = not lease-managed (publish
        as always), "skip" = we do not hold the lease, "blind" = a plain set() is still
        inside the timing bound, "cas" = compare-and-set only."""
        with self._lock:
            if self.uid is None or uid != self.uid:
                return None
            if not self.held:
                return "skip"
            now = time.time()
            if now - self.committed_at < LEASE_HOLD_SEC and now - self.checked_at < LEASE_RECHECK_SEC:
                return "blind"
            return "cas"

    def within_hold(self):
        """Is a plain renewal still inside the timing bound (LEASE PROTOCOL step 3)?"""
        with self._lock:
            return self.held and time.time() - self.committed_at < LEASE_HOLD_SEC

    def send_gate(self, uid):
        """None when not lease-managed for `uid`; else (ok, reason) for a real broker send."""
        with self._lock:
            if self.uid is None or uid != self.uid:
                return None
            if not self.held:
                return False, f"lease lost: {self.lost_reason}"
            age = time.time() - self.committed_at
            if age > LEASE_SEND_MAX_AGE_SEC:
                return False, ("lease unverifiable: no stamp of this host's has landed in "
                               f"{age:.0f}s -- broker sends blocked until a renewal lands")
            return True, None


_LEASE = _LeaseHolder()


def _lease_ref(db, uid):
    return db.collection("users").document(uid).collection("meta").document("qqq_exec")


def _lease_txn(db, ref, decide, merge):
    """Run decide(current_doc) -> (doc_to_write or None, result) as ONE compare-and-set on
    `ref` and return `result`. On a real Firestore client that is a transaction: the read
    and the write commit together or not at all, and a concurrent writer makes it retry
    with a fresh read. A client with no .transaction() -- only the offline fakes in tests/
    and tools/qqq_failover_sim.py, driven from one thread -- gets a plain read-then-write."""
    make_txn = getattr(db, "transaction", None)
    if make_txn is None:
        snap = ref.get()
        write, result = decide(snap.to_dict() if getattr(snap, "exists", True) else None)
        if write is not None:
            ref.set(write, merge=merge)
        return result
    from google.cloud import firestore as _gcf

    @_gcf.transactional
    def _in_txn(transaction):
        # One bounded attempt: the client's default read retry runs for up to five minutes,
        # and this runs on the publisher's single worker.
        snap = ref.get(transaction=transaction, retry=None, timeout=PUBLISH_TIMEOUT_SEC)
        write, result = decide(snap.to_dict() if snap.exists else None)
        if write is not None:
            transaction.set(ref, write, merge=merge)
        return result

    try:
        return _in_txn(make_txn())
    except ValueError as e:
        # The decorator reports the real Firestore error only as the CAUSE of "failed to
        # commit in N attempts", and a BeginTransaction that fails surfaces as "has no
        # transaction ID, so it cannot be rolled back" -- raise the error that matters.
        inner = e.__cause__ or e.__context__
        if inner is not None:
            raise inner from None
        raise


def _claim_lease(db, uid, log=print, timeout=LEASE_CLAIM_TIMEOUT_SEC):
    """(ok, reason, stamp) -- LEASE PROTOCOL step 2: write our lease by compare-and-set
    before running the book. `stamp` is the leased_at we committed, None if nothing was.

    ok=False ONLY when a different host's lease is positively fresh; nothing is written
    then. Any Firestore trouble (error, timeout, a transaction that will not commit) is
    ok=True with stamp=None -- fail-OPEN, the same rule as _check_lease, because this only
    decides whether the shadow book may tick. Real broker sends stay blocked until a stamp
    of ours actually lands (_LeaseHolder.send_gate), and the first publish after that is a
    compare-and-set that stands this process down if another host got there first."""
    if db is None or not uid:
        return True, "no Firestore/uid configured -- lease not enforced", None
    me = _lease_host_id()

    def decide(cur):
        now = time.time()
        ok, reason = _lease_claimable(cur, me, now)
        if not ok:
            return None, (False, reason, None)
        return {"lease": {"host_id": me, "leased_at": now}}, (True, reason, now)

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="qqq-lease")
    fut = ex.submit(lambda: _lease_txn(db, _lease_ref(db, uid), decide, True))
    ex.shutdown(wait=False)
    try:
        return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        why = f"lease claim timed out after {timeout:g}s"
    except Exception as e:
        why = f"lease claim failed ({type(e).__name__}: {e})"
    log(f"[qqq-exec] {why} -- proceeding (fail-open for the shadow book; broker sends stay "
        "blocked until this host's lease lands)")
    return True, f"{why} -- fail-open", None


def _cas_publish(db, ref, doc):
    """(ok, reason): write the whole status doc only if the lease in Firestore is still
    claimable by this host -- the compare-and-set form of a publish (_Publisher._do_set).
    Raises on Firestore trouble, which the publisher records like any failed publish."""
    me = _lease_host_id()

    def decide(cur):
        ok, reason = _lease_claimable(cur, me, time.time())
        return (doc if ok else None), (ok, reason)

    return _lease_txn(db, ref, decide, False)


def _stand_down(state, uid, reason, log=print):
    """LEASE PROTOCOL step 4: another host holds the lease, so this process stops running
    the book NOW -- no more ticks, publishes or broker sends -- and says so loudly. It does
    not fight for the lease back; a restarted process starts again from the claim."""
    host = _lease_host_id()
    log(f"[qqq-exec] STANDING DOWN on host {host!r}: {reason} -- this process has stopped "
        "ticking, publishing and sending")
    _publisher.drop(uid)
    # Already standing by within the last few minutes means this host never really held the
    # lease (a claim that failed open on flaky reads, then found the other host): one phone
    # alert per real loss, not one per systemd restart while reads keep flapping.
    repeat, _note = standby_fresh()
    _note_standby(reason, log=log)
    try:
        _log_event(state, "lease_lost", f"Stood down on {host}: {reason}", log=log)
        save_state(state, log=log)
    except Exception as e:
        log(f"[qqq-exec] could not record the stand-down: {type(e).__name__}: {e}")
    if not repeat:
        _notify(f"QQQ SHADOW on {host} stood down: {reason}", "EDGELOG QQQ SHADOW STOOD DOWN",
                log)


def serve(db, uids, log=print):
    """Run the adapter in THIS process until killed, or until it loses the cross-host
    lease. qqq_exec_thread holds the serving slot and the heartbeat and runs the LEASE
    PROTOCOL; this is the standalone's front door. Returns at once while another host's
    lease is fresh, leaving a STANDBY marker -- on the VM systemd restarts the unit, which
    is how a refused standalone keeps re-checking."""
    alive, pid = serving_alive()
    if alive and pid != os.getpid():
        log(f"[qqq-exec] another standalone is already serving (pid {pid}) -- exiting")
        return
    for uid in uids:
        ok, reason = _check_lease(db, uid, log=log)
        if not ok:
            log(f"[qqq-exec] REFUSING to serve for {uid}: {reason} -- the owner's PC and "
                f"the cloud VM must never run the shadow book at the same time")
            _note_standby(reason, log=log)
            return
    log(f"[qqq-exec] SERVING standalone (pid {os.getpid()}, host {_lease_host_id()!r}), "
        f"tick {TICK_SEC:g}s")
    qqq_exec_thread(db, uids, log=log)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run a single tick and exit")
    ap.add_argument("--serve", action="store_true",
                    help="run forever as the standalone adapter (see STANDALONE SERVING)")
    ap.add_argument("--uid", default=None, help="publish to users/{uid}/meta/qqq_exec")
    ap.add_argument("--fills", default=DEFAULT_FILLS)
    ap.add_argument("--cred", default=None, help="Firestore service-account json "
                                                  "(needed with --uid)")
    a = ap.parse_args()
    if not (a.once or a.serve):
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
    if a.serve:
        if db is None or not a.uid:
            print("[qqq-exec] --serve needs --uid and a reachable Firestore; refusing to "
                  "serve blind (the published doc IS the record)")
            return
        serve(db, [a.uid])
        return
    run_once(uid=a.uid, fills_path=a.fills, db=db)


if __name__ == "__main__":
    main()
