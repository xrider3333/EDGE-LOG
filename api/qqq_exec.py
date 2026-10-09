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
      every open lot is closed and tagged "EOD" -- except a leg in
      session.hold_overnight_legs (ENGU-Q by default, engine mode only), whose lot holds
      overnight like its backtest and sells on its own strategy exit (HOLD OVERNIGHT,
      owner GO 2026-10-09 -- see the section of that name).
  (d) kill file present -> no new lots; close every open lot, tagged "KILL".
  (e) feed staleness (NinjaTrader AddOn heartbeat older than 90s, via
      api.nt_sync._addon_heartbeat) blocks new entries and logs at most one line per
      30 minutes while it persists (no phone push since the WEBULL PUSH PLAN 10-07: the
      box runs signal_source "engine", so this check never runs there).

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
import urllib.request  # noqa: F401 -- api/ntfy_push posts through it; tests patch qe.urllib.request
from datetime import datetime, timedelta, timezone

from . import market_calendar
from . import nt_sync
from . import ntfy_push
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
# HOLD OVERNIGHT (OWNER GO 2026-10-09, MANAGER #106): the exec legs whose lot is NOT sold at
# session.flat_by -- it holds overnight like its backtest and sells on its own engine EXIT
# on a later day, as a normal market order in regular hours. Code default only:
# config.json's session.hold_overnight_legs (a list of LEGS) overrides it, read at call
# time by _hold_legs (never baked into DEFAULT_CONFIG). Engine mode only. See the
# HOLD OVERNIGHT section near _close_all for the lot's "hold" block, the mark-to-open daily
# loss rail and the deferred (after-hours) closes.
HOLD_OVERNIGHT_LEGS = ("ENGUQ",)
# ENGINE MODE (2026-09-13): maps api/cloud_signal.py's own CROWN_LEGS keys onto this
# module's short leg keys. Kept explicit (not derived) so a cloud_signal rename never
# silently breaks this mapping -- update BOTH sides in the same commit. See
# api/cloud_signal.py's "THE CROWN (LIVE) LEGS" docstring for the current crown/run per key.
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
#
# ENGUQ_335 IS LIVE AGAIN SINCE 2026-10-09 (OWNER DECISION via MANAGER #102, reversing the
# 2026-09-28 decision that made it a no-order shadow leg -- cloud_signal.SHADOW_LEGS, whose
# <state_dir>/shadow/signals.csv this module never reads). It is back in
# cloud_signal.CROWN_LEGS with its pre-09-28 cfg, so its ENTRY/EXIT rows are in the live
# ledger again and map to the "ENGUQ" exec leg here: config shares["ENGUQ"] (10 on the box),
# max_shares_per_leg and the session window [open, last_entry] (_late_entry_reason) exactly
# as for ORB/NOISE. Unlike them it HOLDS OVERNIGHT (owner GO 2026-10-09, MANAGER #106): the
# flat_by flatten (15:59) sells ORB/NOISE but keeps the ENGU-Q lot (HOLD_OVERNIGHT_LEGS above),
# which sells on its own engine EXIT on a later day (cloud_signal ENGUQ_335 has no eod_flat).
# It STARTS FLAT: the engine cold-starts the leg (cloud_signal LIVE SINCE), so no catch-up
# order is ever sent.
# Since 2026-10-09 (MANAGER #87 (d)) this module also READS the shadow ledger in exactly one
# place -- _build_shadow_trades, the status doc's separate, display-only "shadow_trades"
# block for the board's "Shadow - not counted" fold. That read never reaches an order, a
# lot, a rail, P&L, trades_all, readiness or the export (see SHADOW TRADES).
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
# broker_orders.csv keeps far more than orders.csv (2026-09-28, P&L of record): each
# closed trade's P&L of record reads its Webull fills from here, so the file must
# outlive a week of trading (100 rows did not). The nightly re-price also persists each
# captured fill in reprice.csv (entry_px_source/exit_px_source == "webull_fill"), which
# covers anything older than this.
BROKER_ORDERS_KEEP = 2000
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
    # RESTING ORB STOP (2026-09-29, owner GO via MANAGER -- see _maybe_manage_resting):
    # "off" = today's behaviour exactly; "log_only" (DEFAULT) = every arm / cancel /
    # re-arm / crossing decision is logged and published, and NO resting order is sent;
    # "stop" = ORB #314's stop rests at Webull; "stop_target" = the stop plus the 5R
    # target inside ONE native OCO. The last two are opt-in. "stop_target" also needs
    # "oco_verified": true -- set only after a REAL-fill paper probe has shown a filled OCO
    # leg cancels its sibling and how partial fills behave (untested 09-29: a partial
    # target fill then a stop trigger before the book's own cancel lands could sell the
    # account past zero); without it the mode runs as "stop", with one warning. Known
    # limit: Webull fills whichever OCO leg its tape reaches first, while the backtest
    # checks the stop first inside a bar -- a 5m bar touching both is a stop in the
    # backtest and may be a target fill at Webull (flagged afterwards as "diverged").
    "orb_resting": {"mode": "log_only"},
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


def _hhmm_minus(hhmm, minutes):
    """'HH:MM' minus `minutes` minutes, clamped at 00:00 -- never crosses midnight
    (session times never need to). Used by the half-day clamp (EXIT SAFETY item 5,
    2026-09-26) to derive flat_by/last_entry from the recognised early close."""
    h, m = _hhmm(hhmm)
    total = max(0, h * 60 + m - int(minutes))
    return f"{total // 60:02d}:{total % 60:02d}"


# EXIT SAFETY (2026-09-26), item 2/6: how long a CLOSE re-send keeps trying, and how far
# apart the tries are. A flat-out backoff, not BROKER_RESEND_MIN_GAP_SEC/MAX_TRIES above --
# those govern an OPEN blocked by a reconcile halt or a same-instant duplicate, which are
# timing glitches expected to clear in seconds; a CLOSE that keeps failing (refused,
# exception/timeout, BLOCKED) may be a real outage, and giving up on an EXIT after 3 tries
# risks leaving real shares open with nobody trying any more.
BROKER_CLOSE_RESEND_BACKOFF_SEC = (5.0, 10.0, 20.0, 30.0)   # then 30s per further try
SESSION_FLATTEN_DEADLINE_MARGIN_SEC = 10.0   # a CLOSE re-send never tries past close - 10s


def _close_resend_backoff(tries):
    """Seconds to wait before the next CLOSE re-send attempt, given `tries` already
    made -- about 5, 10, 20, 30s, then every 30s after that (BROKER_CLOSE_RESEND_BACKOFF_SEC)."""
    idx = min(max(int(tries), 0), len(BROKER_CLOSE_RESEND_BACKOFF_SEC) - 1)
    return BROKER_CLOSE_RESEND_BACKOFF_SEC[idx]


def _session_flatten_deadline(nowdt):
    """Today's session close (market_calendar.session_close_et -- 16:00 normally, 13:00
    on a recognised half day) minus SESSION_FLATTEN_DEADLINE_MARGIN_SEC -- the hard stop
    for a CLOSE re-send (EXIT SAFETY item 2, 2026-09-26): Webull refuses a market order
    once the venue itself has closed (see _maybe_flatten_orphan_broker's own docstring
    on the 2026-09-17/18 incident), so retrying past this instant can only ever fail.
    Never raises -- an unreadable session-close string falls back to 16:00."""
    try:
        h, m = _hhmm(market_calendar.session_close_et(nowdt) or "16:00")
    except Exception:
        h, m = 16, 0
    close_dt = nowdt.replace(hour=h, minute=m, second=0, microsecond=0)
    return close_dt - timedelta(seconds=SESSION_FLATTEN_DEADLINE_MARGIN_SEC)


class _MarketClosed(Exception):
    """_mirror_to_broker's own signal that its AFTER-CLOSE GUARD refused the send."""


def _market_closed_for_orders(nowdt):
    """True from today's session close (16:00, or 13:00 on a recognised half day) onward,
    on a session day -- AFTER-CLOSE GUARD (2026-09-28): no broker order of any kind goes
    out then (Webull refuses market orders after the bell -- 2026-09-17/18, 417
    OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_READY_MARKET -- and an OPEN it did take would
    stay open overnight). Seconds precision: 16:00:00 is already closed. Never raises
    (any doubt reads as not closed, today's behaviour)."""
    try:
        if nowdt is None or not market_calendar.is_session(nowdt):
            return False
        close_dt = _session_flatten_deadline(nowdt) + timedelta(
            seconds=SESSION_FLATTEN_DEADLINE_MARGIN_SEC)
        return nowdt >= close_dt
    except Exception:
        return False


def _outside_regular_hours(nowdt):
    """True when no market order may go out at `nowdt` (HOLD OVERNIGHT, 2026-10-09): not a
    session day (a weekend or a holiday), before 09:30:00 New York, or from today's session
    close on (_market_closed_for_orders -- 13:00 on a half day). A held lot's close that
    falls here is deferred to the next open (lot["close_pending"], see
    _defer_held_close). Deliberately separate from _market_closed_for_orders, which stays
    False before the open and on a weekend (its after-close guard is pinned to the
    second). None or any doubt reads as inside -- the old behaviour. Never raises."""
    try:
        if nowdt is None:
            return False
        if not market_calendar.is_session(nowdt):
            return True
        if _et_hhmm(nowdt) < (9, 30):
            return True
        return _market_closed_for_orders(nowdt)
    except Exception:
        return False


def _hold_legs(cfg):
    """The exec legs whose lot holds overnight (HOLD OVERNIGHT): config
    session.hold_overnight_legs when it is a list of known LEGS ([] = none), else the code
    default HOLD_OVERNIGHT_LEGS. () in ninjatrader mode: a fill dated before today is
    never replayed there, so an overnight exit would be lost -- that fallback keeps
    flat-at-close. Read at call time from the tick's own cfg. Never raises."""
    try:
        cfg = cfg or {}
        if str(cfg.get("signal_source") or "engine").strip().lower() != "engine":
            return ()
        sess = cfg.get("session")
        raw = sess.get("hold_overnight_legs") if isinstance(sess, dict) else None
        if raw is None:
            return HOLD_OVERNIGHT_LEGS
        if isinstance(raw, (list, tuple)) and all(isinstance(x, str) and x in LEGS for x in raw):
            return tuple(raw)
        return HOLD_OVERNIGHT_LEGS
    except Exception:
        return HOLD_OVERNIGHT_LEGS


# -- config / state I/O -------------------------------------------------------------
def _read_config_for_gate(path=None, log=print):
    """Read-only counterpart to load_config, for the SERVING_HOSTS GATE ONLY (major
    review finding, 2026-09-26): load_config() CREATES config.json with defaults when
    it is missing, and every call site of the gate (qqq_exec_thread, ensure_standalone,
    run_once, serve) used to run BEFORE the host-slot/lease checks that today's tests
    never isolate from the real EDGELOG_HOME -- so a fresh box wrote a live config.json
    the live-system guard then blocked, and a box that HAS the recommended
    serving_hosts key made unrelated tests fail by actually refusing on that host. This
    never writes, never merges DEFAULT_CONFIG, never touches `mode`/`signal_source` --
    it only needs the raw "serving_hosts" key, and returning {} for "missing or
    unreadable" is exactly the fail-open a caller needs to decide nothing has changed.

    `path` defaults to None the same way load_config does: read the CURRENT module
    global, not one bound at def-time, so a caller (or a test) that reassigns
    qqq_exec.CONFIG_PATH still gets the right file."""
    path = path if path is not None else CONFIG_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"[qqq-exec] WARNING: {path} exists but could not be read/parsed "
            f"({type(e).__name__}: {e}) -- serving_hosts gate fails OPEN (every host may "
            "still serve), same as a missing file; fix the file to restore the gate")
        return {}


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
    # HOLD OVERNIGHT: session.hold_overnight_legs must be a list of known legs ([] turns the
    # hold off); anything else is dropped so _hold_legs falls back to the code default
    sess = merged.get("session")
    if isinstance(sess, dict) and "hold_overnight_legs" in sess:
        raw = sess.get("hold_overnight_legs")
        if not (isinstance(raw, list) and all(isinstance(x, str) and x in LEGS for x in raw)):
            log(f"[qqq-exec] invalid session.hold_overnight_legs={raw!r} -- using the code "
                f"default {list(HOLD_OVERNIGHT_LEGS)}")
            sess.pop("hold_overnight_legs", None)
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
        "kill_flatten_date": None,  # ET date a KILL flatten last fired -- EXIT SAFETY item 4
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
    # HOLD OVERNIGHT: never touches state["legs"] -- a held lot (its "hold" block and any
    # close_pending decided after the bell) rides through midnight, a weekend and a holiday
    # unchanged; the new day's open mark is taken by _refresh_held_marks from 09:30
    # (lot["hold"]["open_mark_day"] says which day a mark belongs to, so nothing is reset)
    if state.get("trading_day") != today:
        state["trading_day"] = today
        state["realized_pnl_today"] = 0.0
        state["breaker_tripped"] = False
        state["flat_by_done_date"] = None
        state["kill_done"] = False


# -- ntfy push (best-effort, non-fatal -- same shape as api.nt_drawdown_alert) ------
def _notify(msg, title, log=print, priority=None):
    """`priority` (EXIT SAFETY, 2026-09-26, item 7): an optional ntfy Priority header
    override -- 'high' for a safety push (a broker record that came back not ok, an
    exit re-send queue giving up), 'urgent' for the one case worse than that (Webull
    still holds shares after the close). Omitted (the default) keeps the original
    'default' priority for every routine fill/summary ping -- every call site from
    before this date passes nothing and is unaffected.

    Returns True when the POST went out, False when it was tried and failed, None when no
    topic is set (nothing to retry). Callers that ignore the result are unaffected.

    PERSISTED OUTBOX (sweep 2026-10-05, finding 16). A 'high' or 'urgent' push goes through
    api/ntfy_push.Outbox (file: NTFY_OUTBOX_PATH, beside state.json): one try right away as
    before, and if that fails it is kept on disk and retried by a background thread (30 s,
    1 min, 2 min, 5 min, then every 10 min, for up to 12 h, at most 50 waiting) -- the 5 s
    tick never waits on a retry, and while earlier pushes are still waiting a new one is
    queued without a try at all. Each such push logs one line when it is sent, delivered
    late or dropped. Returns "queued" (not False) when it was kept for retry: the outbox
    now owns delivery, so a caller must not retry it itself. Routine pushes (no priority,
    'default', 'low') stay one fire-and-forget try."""
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic:
        log(f"[qqq-exec] NTFY_TOPIC unset, push skipped: {title}: {msg}")
        return None
    if ntfy_push.is_durable(priority):
        try:
            r = _ntfy_outbox(log).send(msg, title, priority)
            if r is not False:
                return r
            # False: the outbox itself broke before any network try -- still make one
            log("[qqq-exec] ntfy outbox could not take the push -- one plain try")
        except Exception as e:     # the outbox itself broke: still make the one plain try
            log(f"[qqq-exec] ntfy outbox unavailable ({type(e).__name__}: {e}) -- one plain try")
    ok, detail = _ntfy_post(msg, title, priority)
    if not ok:
        log(f"[qqq-exec] ntfy push failed: {detail}")
        return False
    return True


def _ntfy_post(msg, title, priority=None):
    """ONE ntfy POST, (ok, detail): ok True/False, None when NTFY_TOPIC is unset. Never
    raises, never logs (the caller -- _notify or the outbox -- logs the outcome).

    WEBULL PUSH PLAN 10-07 (MANAGER #86, section 2): this used to be a second private copy
    of api/ntfy_push's POST. It now IS api/ntfy_push.push_result -- the one place the topic,
    NTFY_TOKEN and NTFY_SERVER are read -- so a private topic reaches this sender the day it
    is turned on. No priority still sends the "default" header, as before."""
    try:
        ok, detail = ntfy_push.push_result(msg, title=title, priority=priority or "default",
                                           timeout=4)
    except Exception as e:      # push_result never raises; belt and braces
        return False, f"{type(e).__name__}: {e}"
    return ok, detail


# -- THE PLAIN PHONE FORMAT for EVERY executor push (WEBULL PUSH PLAN 10-07, MANAGER #86) --------
# C:\EdgeLog\manager\paperwb_1007\WEBULL_PUSH_PLAN_1007.md section 1: the executor's ~38 push
# sites cover 9 problems. Each push now builds its text with ntfy_push.plain() -- title
# "QQQ book: <status>" (or "QQQ fill: <leg> <what>"), "Trading: ...", ONE plain problem line
# with at most one number, "Do: ...", times on the owner's clock (ntfy_push.hhmm, Arizona),
# strategies as words (ORB / ENGU-Q / NOISE) -- and goes through _say(), which runs the shared
# repeat rule (ntfy_push.dedupe) per problem key on state["_phone_dedupe"] (saved with
# state.json): a problem pushes once, again at once only when it gets WORSE (high -> urgent),
# else at most once a day while it stands. Problem ids carry the ET date, so "once per
# strategy per day" (a missed entry) and "once per day" fall out of the same rule. The
# developer text is unchanged in the log line and the timeline event. Priority (plan table):
#   A exit (sell) did not go through   first failure high; give-up / stall / after the bell /
#                                       repair gave up urgent             key exit:<leg>
#                                       (10-08: an accepted sell Webull later killed with
#                                       shares unsold is this group's high -- _say_order_outcome)
#   B entry (buy) did not go through   high, once per strategy per day; a give-up or a failed
#                                       remainder folds into that note    key entry:<leg>
#                                       (10-08: an accepted buy Webull later rejected or only
#                                       part-filled is this group too; a split buy's refused
#                                       rest waits for its one re-send before any push)
#   C orders on hold                   high, one note per hold episode     key hold:<cause>;
#                                       the reconcile hold at most once per New York day
#   D book and Webull disagree         default; high only for "sell by hand"
#   E fixed itself / benign            NO PUSH (log + timeline only)
#   F fills                            low; one note per exit (none when the resting stop
#                                       already reported it); an inferred stop fill default
#   G end of day                       not flat urgent, unread high, the day summary low
#   H safety stops                     daily stop high (one note, lots or flat); kill low;
#                                       ORB stop not placed default
#   I program health                   tick crashes / database / stood down high; the signal
#                                       stall and the NinjaTrader feed: NO PUSH (the box
#                                       monitor owns the stall; the feed is dead on the box)
PHONE_AREA = "QQQ book"
PHONE_ASK = "ask Claude (PAPER-WB chat)"
PHONE_LEG_WORDS = {"ENGUQ": "ENGU-Q", "ORB": "ORB", "NOISE": "NOISE"}
# a call with no state (start-up: the resting boot sweep) dedupes in process memory
_PHONE_PROCESS_STORE = {}


def _leg_word(leg):
    """'ENGUQ' -> 'ENGU-Q'; 'ORB' / 'NOISE' as they are; anything else -> 'a strategy'."""
    s = str(leg or "").strip()
    return PHONE_LEG_WORDS.get(s.upper(), s) or "a strategy"


def _a_leg_word(leg):
    """The strategy word with its article, capitalised to start a sentence: 'An ORB',
    'A NOISE', 'A strategy' (10-08 review: never 'A ORB')."""
    w = ntfy_push.with_article(_leg_word(leg))
    return w[:1].upper() + w[1:]


def _legs_words(legs):
    """['NOISE', 'ORB'] -> 'NOISE and ORB'."""
    ws = [_leg_word(x) for x in legs if x]
    return " and ".join([", ".join(ws[:-1]), ws[-1]]) if len(ws) > 1 else (ws[0] if ws else "a strategy")


def _phone_epoch(when=None):
    """Epoch seconds of `when` (None = now; a naive datetime is New York wall time, as every
    nowdt in this module)."""
    if when is None:
        return time.time()
    if isinstance(when, (int, float)):
        return float(when)
    try:
        if when.tzinfo is None:
            when = when.replace(tzinfo=_NY) if _NY else when.replace(tzinfo=timezone.utc)
        return when.timestamp()
    except Exception:
        return time.time()


def _phone_clock(when=None):
    """'12:59' -- `when` on the owner's clock (Arizona), never New York."""
    e = _phone_epoch(when)
    return ntfy_push.hhmm(e, now=e)


def _phone_day(nowdt=None):
    """The ET trading date a problem id carries ('2026-10-08')."""
    return (nowdt or _now_et()).strftime("%Y-%m-%d")


def _phone_close(nowdt=None):
    """Today's flatten deadline (15:59 New York on a full day) on the owner's clock."""
    try:
        return _phone_clock(_session_flatten_deadline(nowdt or _now_et()))
    except Exception:
        return "the close"


def _phone_why(reason):
    """A broker reason in a few plain words for the phone (no codes, ids or numbers); the
    raw text stays in the log line and the timeline event."""
    s = str(reason or "")
    low = s.lower()
    m = _WEBULL_ERROR_CODE_RE.search(s)
    if m and "SIDE_NOT_MATCH" in m.group(1):
        return "Webull says the account holds the other side of QQQ"
    if m and "SHORT" in m.group(1):
        return "this account cannot short"
    if "insufficient" in low or "not enough" in low:
        return "not enough shares to sell"
    if "timed out" in low or "timeout" in low or "unknown" in low:
        return "Webull did not answer in time"
    if "halt" in low:
        return "orders were on hold"
    if "lease" in low:
        return "another computer holds the QQQ book"
    if "kill" in low:
        return "the kill switch is on"
    if "in flight" in low or "in-flight" in low or "busy" in low:
        return "an earlier order was still being sent"
    return "Webull did not accept it"


def _phone_host_word():
    """'the cloud box' on the box (EDGELOG_HOST_ROLE=cloud), else 'the PC'."""
    role = str(os.environ.get("EDGELOG_HOST_ROLE") or "").strip().lower()
    return "the cloud box" if role == "cloud" else "the PC"


def _say(state, key, problem_id, note, log=print):
    """Send one plain() note through the shared repeat rule -> (action, sent).

    `key` names the problem (one dedupe slot in state["_phone_dedupe"], saved with
    state.json); `problem_id` is this occurrence ("2026-10-08"); the note's priority is its
    rank, so the same id pushes again only when it gets worse. action is ntfy_push.dedupe's
    (None held / "push"); sent is what _notify returned (True, "queued", None = no topic
    set, False = the send failed) or None when held. A push whose send FAILED (False) does
    not count: the dedupe slot is put back, so the next call tries again -- while None (no
    topic set) counts as done, so a box with no topic never loops. lint() problems are
    logged. `state` None (start-up, no state.json yet) dedupes in process memory. Never
    raises."""
    try:
        for p in ntfy_push.lint(note):
            log(f"[qqq-exec] phone note lint: {p}: {note.get('title')}")
        store = (state.setdefault("_phone_dedupe", {}) if isinstance(state, dict)
                 else _PHONE_PROCESS_STORE)
        before = json.loads(json.dumps(store.get(key))) if key in store else None
        rank = ntfy_push.RANK.get(note.get("priority"), 0)
        # 10-08 review: a held call at a LOWER rank (a "sell is late" high after the same
        # day's urgent) must not lower the stored rank -- else the next urgent for the same
        # fact would count as "worse" and buzz a second time
        try:
            prior = ((before or {}).get("set") or {}).get(str(problem_id))
            if prior is not None:
                rank = max(rank, int(prior))
        except Exception:
            pass
        action = ntfy_push.dedupe_in(store, key, {str(problem_id): rank}, time.time())
        if action != "push":
            log(f"[qqq-exec] phone note held by the repeat rule: {note.get('title')}")
            return action, None
        sent = _notify(note["message"], note["title"], log, priority=note["priority"])
        if sent is False:
            if before is None:
                store.pop(key, None)
            else:
                store[key] = before
        return action, sent
    except Exception as e:
        log(f"[qqq-exec] phone note failed ({type(e).__name__}: {e})")
        return None, False


def _say_clear(state, key, log=print):
    """The problem `key` is over: end its episode quietly (no push), so the next occurrence
    -- even the same day -- pushes again. Never raises."""
    try:
        store = (state.get("_phone_dedupe") if isinstance(state, dict)
                 else _PHONE_PROCESS_STORE)
        if isinstance(store, dict):
            store.pop(key, None)
    except Exception as e:
        log(f"[qqq-exec] phone note clear failed ({type(e).__name__}: {e})")


def _fill_note(leg, what, problem):
    """A fill (plan group F): low, no buzz -- "QQQ fill: NOISE bought"."""
    return ntfy_push.plain("QQQ fill", f"{_leg_word(leg)} {what}", None, problem, "nothing",
                           priority="low")


def _exit_reason_words(reason):
    """'EOD (px: live_stream)' -> 'end-of-day close'; 'signal exit' -> 'strategy exit'."""
    r = str(reason or "").strip().upper()
    if r.startswith("EOD SETTLE"):
        return "end-of-day settle"
    if r.startswith("EOD"):
        return "end-of-day close"
    if r.startswith("KILL"):
        return "kill switch"
    if r.startswith("BREAKER"):
        return "daily stop"
    if "HELD" in r:
        return "strategy exit, held overnight"
    return "strategy exit"


def _kill_note(deferred=()):
    """The kill switch (plan group H): low -- the owner switched it on. `deferred`: held
    overnight legs whose sell waits for the open (HOLD OVERNIGHT -- nothing is sent outside
    regular hours)."""
    if deferred:
        return ntfy_push.plain(
            PHONE_AREA, "kill switch on", "the kill switch closes every QQQ trade",
            f"The kill switch is on; {_legs_words(deferred)}'s held shares sell when the "
            f"market opens",
            "nothing if you switched it on, else " + PHONE_ASK, priority="low")
    return ntfy_push.plain(
        PHONE_AREA, "kill switch on", "the kill switch closed every QQQ trade",
        "The kill switch is on: QQQ trades were closed and new ones are blocked",
        "nothing if you switched it on, else " + PHONE_ASK, priority="low")


def _held_note(leg, shares):
    """HOLD OVERNIGHT: the planned overnight hold, one low note a day ("QQQ book: held
    overnight") -- never an alarm."""
    return ntfy_push.plain(
        PHONE_AREA, "held overnight", "not affected (planned)",
        f"{_leg_word(leg)} keeps its {int(shares)} QQQ shares overnight, as its backtest does",
        "nothing - it sells on its own exit", priority="low")


def _stood_down_note():
    """This host stood down (plan group I): high -- trading on this machine stopped."""
    return ntfy_push.plain(
        PHONE_AREA, "stopped here", f"{_phone_host_word()} stopped running the QQQ book",
        "Another computer holds the QQQ book",
        PHONE_ASK + " which computer should run it", priority="high")


def _repair_gave_up_note(legs):
    """The Webull-only repair gave up (plan group A): urgent -- shares are still held."""
    return ntfy_push.plain(
        PHONE_AREA, "CHECK NOW", "Webull still holds shares the book does not",
        f"The repair could not sell the {_legs_words(legs)} shares Webull still holds",
        "sell them by hand in the Webull app", priority="urgent")


def _say_daily_stop(state, total, what, nowdt=None, log=print):
    """The daily stop (plan group H): ONE high note a day, lots or flat."""
    return _say(state, "daily_stop", _phone_day(nowdt), ntfy_push.plain(
        PHONE_AREA, "daily stop hit", "no new QQQ trades today",
        f"Today's loss reached {ntfy_push.usd(total)}, past the daily limit; {what}",
        "nothing - it resets tomorrow", priority="high"), log=log)


def _phone_note(state, key, problem_id, note, log=print):
    """_say() returning only the dedupe action (the re-price alert's original helper).
    Never raises."""
    return _say(state, key, problem_id, note, log=log)[0]


# The executor's ntfy outbox (finding 16) -- see _notify. None: ntfy_outbox.json in the same
# folder as STATE_PATH. NTFY_OUTBOX_BACKGROUND=False (tests) never starts the retry thread.
NTFY_OUTBOX_PATH = None
NTFY_OUTBOX_BACKGROUND = True
_NTFY_OUTBOX = {"box": None}
_ntfy_outbox_lock = threading.Lock()


def _ntfy_outbox(log=None):
    path = NTFY_OUTBOX_PATH or os.path.join(os.path.dirname(STATE_PATH), "ntfy_outbox.json")
    with _ntfy_outbox_lock:
        box = _NTFY_OUTBOX.get("box")
        if box is None or box.path != path or box.background != bool(NTFY_OUTBOX_BACKGROUND):
            box = ntfy_push.Outbox(path, sender=lambda m, t, p: _ntfy_post(m, t, p),
                                   tag="qqq-exec", background=NTFY_OUTBOX_BACKGROUND)
            _NTFY_OUTBOX["box"] = box
    box.set_log(log)
    return box


def _ntfy_outbox_resume(log=print):
    """Serving start-up: retry any HIGH/URGENT push a previous process could not deliver.
    Never raises."""
    try:
        return _ntfy_outbox(log).resume(log)
    except Exception as e:
        log(f"[qqq-exec] ntfy outbox resume failed (non-fatal): {type(e).__name__}: {e}")
        return 0


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
              + ["keel_size"]
              # HOLD OVERNIGHT (2026-10-09): appended, never inserted -- a held trade's
              # overnight gaps added up (shares x (open - prior close) x side, every night)
              # and the session opens it was carried into. Inside `pnl` (the P&L of record
              # is exit - entry), kept out of the daily loss limit. "" for a same-day trade.
              + ["overnight_gap_usd", "nights_held"])


def _record_order(leg, action, side, shares, nq_px, qqq_px, px_source, reason, log=print,
                  fill_dt=None, signal_source=None, size=None, shares_wanted=None,
                  decided_at_ref=False, quiet=False):
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
    resolvable leg timeframe.

    `decided_at_ref` (2026-09-26, WEBULL_PAPER_TODO item 16): the signal came from
    cloud_signal's decide_at_close probe -- its ref_time is the bar that was only just
    STARTING when the decision was made at the previous bar's close, so that close IS
    ref_time and after_close_s = latency_s (subtracting the bar width would read ~-270s).

    `quiet` (2026-10-09): write the row but not this function's own one-line summary -- for a
    caller that logs its own plainer line for the same order (the late-entry refusal, see
    _entry_not_taken_line), so the log carries ONE line for it, not two."""
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
            after_close_s = round(latency_s - (0 if decided_at_ref else tf_sec), 3)
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
    if not quiet:
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
    # HOLD OVERNIGHT: "" unless the lot was carried into at least one later session
    hold = lot.get("hold") if isinstance(lot.get("hold"), dict) else {}
    nights = int(hold.get("nights") or 0) if hold else 0
    row["overnight_gap_usd"] = round(float(hold.get("gap_usd") or 0.0), 2) if nights else ""
    row["nights_held"] = nights if nights else ""
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
                     "host_id",
                     # EXIT SAFETY item 5 (2026-09-26 minor review): appended at the END,
                     # same backward-compat convention as host_id above -- a genuinely
                     # UNKNOWN outcome (a hard-timeout send, or a PENDING-resolver record
                     # from api/webull_orders.py's own side) used to be indistinguishable
                     # from an ordinary refusal in this CSV's own "ok"/"sent" columns
                     # (both read ok=False, sent=True) -- see _broker_row_outcome. One of
                     # OK / REFUSED / BLOCKED / UNKNOWN, always derivable from the same
                     # `rec` this row's other fields already came from. Every reader of
                     # this file (api/qqq_exec.py's own _best_broker_row/_broker_realized_
                     # today/_all_broker_orders_from_csv/_update_broker_order_row, tools/
                     # qqq_exec_smoke.py, tools/qqq_failover_sim.py) reads by column NAME
                     # (csv.DictReader), never by position, so an appended column is safe
                     # for every one of them; index.html has no broker_orders.csv reader
                     # at all (checked by grep).
                     "outcome"]

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
        cfg_leg = _engine_leg_cfg(cs, cs_key)
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
            # HOLD OVERNIGHT: held flag, gap and marks (the board shows it as planned)
            legs_out[-1].update(_held_position_fields(
                lot, state.get("trading_day"),
                (state.get("_rail_unrl_by_leg") or {}).get(leg)))
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


def _query_broker_fill(adapter, signal_id, account_id=None, log=print, outcome=None):
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
    guessing.

    ACK IS NOT A FILL (2026-09-26): with an `outcome` dict, status + filled qty also go
    to adapter.apply_order_outcome and `outcome` gets its answer when the books moved.
    A still-working order (PENDING/SUBMITTED/PARTIAL_FILLED) never returns a price --
    a partial's average is not the fill -- and sets outcome["working"] when the adapter
    tracks it, so the capture job stays open until a terminal status."""
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
        coid = result.get("client_order_id") or signal_id
        # order_status_fields falls back to orders[0]: never read (or book) another order
        item_coid = webull_orders._field(webull_orders._order_item(result.get("response"), coid),
                                         "client_order_id", "clientOrderId")
        if item_coid is not None and str(item_coid) != str(coid):
            return None, "record is about another order"
        fields = webull_orders.order_status_fields(result.get("response"), coid)
        apply = getattr(adapter, "apply_order_outcome", None) if outcome is not None else None
        if callable(apply):
            res = apply(coid, fields.get("status"),
                        fields.get("filled_quantity"))
            if isinstance(res, dict) and res.get("deferred"):
                return None, "adapter books busy (a send is in flight) -- will ask again"
            if isinstance(res, dict):
                outcome.update(res)
        st = webull_orders._norm_status(fields.get("status"))
        if callable(apply) and st:
            outcome["working"] = st in webull_orders.LIVE_STATUSES   # a clear answer only
        if st in webull_orders.LIVE_STATUSES:
            return None, (f"still working at Webull (status={st}, "
                          f"{fields.get('filled_quantity') or 0} filled)")
        px = fields.get("filled_price")
        if px in (None, ""):
            return None, f"no fill price yet (status={fields.get('status') or 'unknown'})"
        try:
            return float(px), None
        except (TypeError, ValueError):
            return None, f"unparseable filled_price {px!r}"
    except Exception as e:
        return None, f"order-status parse failed: {type(e).__name__}: {e}"


# -- EXIT SAFETY (2026-09-26) shared helpers -----------------------------------------
def _is_serving_standalone():
    """True only while THIS process itself holds the LOCAL serving lock -- the exact
    same file (SERVING_LOCK) serving_alive() reads for the runner/premarket_ensure, and
    the same guarantee serve()'s own 'SERVING standalone' log line describes: on one
    machine, at most one process runs the book at a time, entirely independent of the
    Firestore lease. Used by the item-3 CLOSE lease-gate exemption below -- a caller/
    test that never wrote this lock (every pre-2026-09-14 test, a bare --once run) reads
    False, so the exemption can never fire for them. Never raises."""
    try:
        alive, pid = serving_alive()
        return bool(alive) and pid == os.getpid()
    except Exception:
        return False


# EXIT SAFETY item 3 (2026-09-26, LEAD DECISION on the "alerts in book" review): a CLOSE
# that keeps failing across many backoff retries used to page on EVERY one of them (each
# not-ok _mirror_to_broker call fires its own alert, and a close_retry can retry every
# 5-30s for hours). WEBULL PUSH PLAN 10-07 (MANAGER #86): the per-site throttles (this
# 5-minute CLOSE gap, the once-a-day OPEN stamp, the 30-minute reconcile gap) are replaced
# by the ONE shared repeat rule, _say() / ntfy_push.dedupe, per problem key: a failing
# CLOSE (key exit:<leg>) pushes on its FIRST failure (high), again only when it gets worse
# -- the give-up, a stalled retry, a sell after the bell (urgent) -- and otherwise at most
# once a day while it stands. NOT one push per retry, and no longer one every 5 minutes.
def _exit_key(leg):
    return f"exit:{leg}"


def _entry_key(leg):
    return f"entry:{leg}"


def _close_fail_alert_reset(state, leg):
    """A leg's CLOSE-failure episode is resolved (a retry finally lands, the retry queue
    gives up, or the position is confirmed already closed some other way): end its phone
    episode (key exit:<leg>), so the NEXT failure for this leg -- a different trade, later
    the same day -- pushes at once again rather than inheriting the old episode. Never
    raises."""
    try:
        state.pop("_close_fail_alert", None)      # the retired 5-minute throttle's memory
        _say_clear(state, _exit_key(leg))
    except Exception:
        pass


def _open_word(side):
    return "short sale" if str(side or "").upper() in ("SHORT", "SELL_SHORT") else "buy"


def _close_word(side):
    """Closing words for either vocabulary: the broker side ('BUY' closes a short) or the
    lot side ('short' -- 10-08 review: fill capture and the PENDING pass pass the lot's)."""
    return "buy-back" if str(side or "").upper() in ("BUY", "SHORT") else "sell"


def _say_exit_late(state, leg, why, side=None, log=print, problem=None):
    """A first exit failure (plan group A, high): the sell keeps retrying. `problem`
    overrides the problem line (an UNKNOWN outcome must not say the sell did not go
    through -- it may have)."""
    w, act = _leg_word(leg), _close_word(side)
    return _say(state, _exit_key(leg), _phone_day(), ntfy_push.plain(
        PHONE_AREA, "CHECK NOW", f"the {w} {act} is late",
        problem or f"The {w} {act} did not go through ({why})",
        "nothing yet - it keeps retrying; a second note comes only if it gives up",
        priority="high"), log=log)


def _say_exit_stuck(state, leg, problem, problem_id=None, log=print):
    """An exit nobody is retrying any more (plan group A, urgent): Webull may still hold
    the shares. `problem_id` (default the ET date) names a distinct fact -- the after-the-bell
    block has its own, so it is not held behind an earlier same-day "sell is stuck"."""
    w = _leg_word(leg)
    return _say(state, _exit_key(leg), problem_id or _phone_day(), ntfy_push.plain(
        PHONE_AREA, "CHECK NOW", f"Webull may still hold {w} shares", problem,
        f"check the Webull app and sell {w} by hand if it is still held",
        priority="urgent"), log=log)


def _say_entry_missed(state, leg, problem, side=None, log=print, trading=None):
    """An entry that did not reach Webull (plan group B, high): ONCE per strategy per day --
    a give-up or a failed split remainder for the same strategy folds into this note.
    `trading` overrides the Trading line's text (an UNKNOWN outcome says the buy "may not"
    be at Webull, matching its problem line)."""
    w = _leg_word(leg)
    return _say(state, _entry_key(leg), _phone_day(), ntfy_push.plain(
        PHONE_AREA, "entry missed", trading or f"the {w} {_open_word(side)} is not at Webull",
        problem.rstrip(".") + "; the book still counts the trade",
        "nothing - " + PHONE_ASK + " if it happens again tomorrow", priority="high"), log=log)


def _alert_broker_not_ok(state, *, leg, intent, side, shares, reason, log=print):
    """Phone alert for a broker record that came back NOT ok (refused, exception/
    timeout, BLOCKED) -- EXIT SAFETY item 1, right after the 'NOT ok' log line at this
    function's own call site. WEBULL PUSH PLAN 10-07: an OPEN is plan group B ("entry
    missed", high, once per strategy per day -- a leg blocked all morning by the same stale
    lease pushes once); a CLOSE is group A (first failure high, then nothing more until it
    gets worse or a day passes -- NOT once per retry). The timeline event is logged with
    each push. Never raises.

    The raw ServerException text (HTTP status, Webull code, RequestID) stays in the "NOT
    ok" log line at the call site and, translated by _plain_broker_error, in the timeline
    event; the phone gets a few plain words (_phone_why)."""
    try:
        plain_reason = _plain_broker_error(reason) or reason or "no reason given"
        msg = f"QQQ BROKER {intent} NOT OK: {leg} {side} {shares}sh -- {plain_reason}"
        why = _phone_why(reason)
        if intent == "OPEN":
            action, _sent = _say_entry_missed(
                state, leg, f"The {_leg_word(leg)} {_open_word(side)} did not reach Webull ({why})",
                side=side, log=log)
        else:
            action, _sent = _say_exit_late(state, leg, why, side=side, log=log)
        if action == "push":
            _log_event(state, "broker", msg, log=log)
    except Exception as e:
        log(f"[qqq-exec] broker-not-ok alert failed (non-fatal): {type(e).__name__}: {e}")


def _alert_broker_send_unknown(state, *, leg, intent, side, shares, reason,
                               client_order_id, log=print):
    """Phone alert for a broker send whose outcome is UNKNOWN (item 4, 2026-09-26 --
    see _place_stock_order_with_timeout). The timeline event is logged always for an OPEN
    (one per real hang: an OPEN is never retried); for a CLOSE once per pushed note. WEBULL PUSH PLAN 10-07: an OPEN is plan group B (the
    strategy's one "entry missed" note of the day); a CLOSE is group A, sharing the leg's
    exit:<leg> episode with _alert_broker_not_ok -- a repeated timeout across many
    close_retry attempts is "a CLOSE that keeps failing", not a fresh emergency each time.
    Never raises."""
    try:
        msg = (f"QQQ BROKER {intent} OUTCOME UNKNOWN: {leg} {side} {shares}sh (order id "
              f"{client_order_id}) -- {reason}")
        w = _leg_word(leg)
        if intent == "OPEN":
            action, _sent = _say_entry_missed(
                state, leg, f"Webull did not answer the {w} {_open_word(side)} in time (it may "
                f"or may not have landed)", side=side, log=log,
                trading=f"the {w} {_open_word(side)} may not be at Webull")
        else:
            action, _sent = _say_exit_late(
                state, leg, "Webull did not answer in time", side=side, log=log,
                problem=(f"Webull did not answer the {w} {_close_word(side)} in time (it may "
                         f"or may not have gone through)"))
        if intent == "OPEN" or action == "push":
            _log_event(state, "broker", msg, log=log)
    except Exception as e:
        log(f"[qqq-exec] broker-unknown alert failed (non-fatal): {type(e).__name__}: {e}")


def _believed_qty_for_leg(leg, log=print, larger=False):
    """Current believed QQQ position (whole shares, unsigned) the broker adapter's OWN
    order-history records say `leg` holds -- the SMALLER of believed_positions and
    broker_sent_positions (EXIT SAFETY item 2 minor, 2026-09-26: the adapter's own
    NOTHING TO CLOSE guard and reconcile() trust broker_sent_positions, not
    believed_positions alone; after an OFF-to-PAPER mode switch mid-session -- or any
    other path that updates one without the other -- the two can briefly disagree, and
    the smaller of the two is always the safer number for a re-send to trust: it can
    never send more than either source believes is actually held). 0 for a leg with no
    belief on record in EITHER, None if the adapter cannot be read at all. Used by the
    CLOSE re-send loop (item 2) to re-check before every retry -- a retry must never
    double-sell. `larger=True` (2026-09-26) returns the LARGER of the two instead -- for
    sizing an OPEN re-buy as "what the lot lacks", where disagreeing books must shrink
    the buy, never grow it. Never raises."""
    try:
        status = _get_broker_adapter(log=log).status()
        believed = (status.get("believed_positions") or {}).get(leg)
        sent = (status.get("broker_sent_positions") or {}).get(leg)

        def _qty(p):
            if not p:
                return 0
            return int(round(abs(float(p.get("qty") or 0))))

        return (max if larger else min)(_qty(believed), _qty(sent))
    except Exception as e:
        log(f"[qqq-exec] believed-position read failed for {leg} (non-fatal): "
            f"{type(e).__name__}: {e}")
        return None


_positions_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="qqq-positions")


def _positions_with_timeout(adapter, log=print):
    """adapter.positions() (the Webull get_account_position() call) bounded to
    RECONCILE_HARD_TIMEOUT_SEC wall-clock -- EXIT SAFETY item 4 major (2026-09-26): this
    was called inline on the 5s tick thread with no time limit at all. Same precaution as
    _reconcile_with_timeout: this SDK's own connect/read timeouts are not reliably
    honoured on every call path (the runner's shadow thread once hung 10 hours inside
    get_snapshot) -- if this particular read hung at ~15:58, the whole tick loop would
    stop dead (no CLOSE retries, no heartbeat/publish, no EOD summary).

    Runs on its OWN single-worker executor, never _reconcile_executor: if reconcile()
    itself is the thing hung, sharing that executor would queue this call behind it
    forever, defeating the point.

    A timeout (or any other exception escaping the call) is folded into the SAME shape
    adapter.positions() itself returns for a read failure -- {"broker": None, "error":
    <reason>} -- so the caller's existing 'could not read' branch below handles it with
    no separate code path to keep in sync. Never raises."""
    fut = _positions_executor.submit(adapter.positions)
    try:
        return fut.result(timeout=RECONCILE_HARD_TIMEOUT_SEC)
    except concurrent.futures.TimeoutError:
        return {"broker": None,
               "error": f"position read timed out after {RECONCILE_HARD_TIMEOUT_SEC:g}s"}
    except Exception as e:
        return {"broker": None, "error": f"{type(e).__name__}: {e}"}


def _check_webull_flat_after_eod(state, log=print):
    """EXIT SAFETY item 4: read Webull's OWN account QQQ position through the broker
    adapter's own position read (adapter.positions()['broker'] -- the same
    get_account_position() call reconcile() itself uses, see api/webull_orders.py),
    bounded via _positions_with_timeout so a hung SDK call can never stall this or the
    tick loop it runs on. Push URGENT and log an event when it is not flat; log+push
    (high, not urgent -- unverified is not the same as confirmed-not-flat) when the read
    itself fails or times out. Returns (flat, shares) for the end-of-day summary's own
    line: (True, 0) flat, (False, N) N shares still held, (None, None) unverifiable,
    (True, None) nothing real was ever armed (mode OFF) so there is nothing to check.
    Never raises."""
    try:
        adapter = _get_broker_adapter(log=log)
        mode, _reason = adapter.effective_mode()
        if mode not in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
            return True, None
        info = _positions_with_timeout(adapter, log=log)
        broker = info.get("broker")
        if broker is None:
            msg = ("QQQ BROKER: could not read Webull's own position after the "
                  "end-of-day flatten (" + str(info.get("error") or "no client") +
                  ") -- check the Webull app by hand")
            log(f"[qqq-exec] {msg}")
            _log_event(state, "broker", msg, log=log)
            state["_eod_flat_pushed"] = _say_eod_unread(state, log=log)
            return None, None
        qty = float(broker.get(BROKER_SYMBOL, 0.0) or 0.0)
        # HOLD OVERNIGHT: "flat except held legs" -- Webull should hold exactly the lots the
        # book holds overnight (signed); only a difference is a problem
        held = _held_shares_by_leg(state)
        expected = float(sum(held.values()))
        if abs(qty - expected) > 1e-9 and held:
            # `shares` stays what Webull holds (as before); how far that is from the held
            # lots rides beside it ("off" on the verdict, see the scheduler)
            off = int(round(abs(qty - expected)))
            shares = int(round(abs(qty)))
            msg = (f"Webull holds {qty:g} QQQ after the close but the book holds "
                   f"{_held_words(held)} overnight -- {off} share(s) off; check the Webull "
                   f"app by hand")
            log(f"[qqq-exec] {msg}")
            _log_event(state, "broker", msg, log=log)
            _action, sent = _say(state, "eod_flat", _phone_day(), ntfy_push.plain(
                PHONE_AREA, "CHECK NOW", "Webull's QQQ does not match the held trade",
                f"Webull's QQQ is {off} shares off the {_legs_words(sorted(held))} trade "
                f"held overnight",
                "check the Webull app, then " + PHONE_ASK, priority="urgent"), log=log)
            state["_eod_flat_pushed"] = sent is not False
            state["_eod_flat_off"] = off
            return False, shares
        if abs(qty) > 1e-9 and not held:
            shares = int(round(abs(qty)))
            msg = (f"Webull still holds {shares} QQQ after the close -- sell by hand in "
                  f"the Webull app")
            log(f"[qqq-exec] {msg}")
            _log_event(state, "broker", msg, log=log)
            _action, sent = _say(state, "eod_flat", _phone_day(), ntfy_push.plain(
                PHONE_AREA, "CHECK NOW", "Webull still holds shares after the close",
                f"Webull still holds {shares} QQQ shares",
                "sell them by hand in the Webull app", priority="urgent"), log=log)
            state["_eod_flat_pushed"] = sent is not False
            return False, shares
        if held:
            log(f"[qqq-exec] Webull after the close: {qty:g} QQQ = the book's held overnight "
                f"lots ({_held_words(held)}) -- flat except held legs")
        return True, 0
    except Exception as e:
        log(f"[qqq-exec] Webull flat-check after EOD failed (non-fatal): "
            f"{type(e).__name__}: {e}")
        # the result (None = unverified) is stamped as this executor's own, so the box
        # monitor stays quiet on it: the executor must push it here too
        try:
            state["_eod_flat_pushed"] = _say_eod_unread(state, log=log)
        except Exception:
            pass
        return None, None


def _say_eod_unread(state, log=print):
    """WEBULL PUSH PLAN 10-07, group G: the executor owns the RESULT of the after-close
    check (high when unread, urgent when not flat -- same key, so "not flat" after "unread"
    still pushes); the box monitor owns "the check did not run". Returns False only when the
    note did not go out (the send failed -- then the monitor pushes it: see the "pushed" stamp
    on state['_webull_flat_after_eod']), else True (sent, queued, no topic, or already sent
    today). Never raises."""
    try:
        _action, sent = _say(state, "eod_flat", _phone_day(), ntfy_push.plain(
            PHONE_AREA, "CHECK NOW", "nobody has confirmed Webull is flat after the close",
            "Webull's QQQ position could not be read after the close",
            "check the Webull app is flat and sell by hand if needed",
            priority="high"), log=log)
        return sent is not False
    except Exception as e:
        log(f"[qqq-exec] after-close unread push failed (non-fatal): {type(e).__name__}: {e}")
        return False


def _maybe_check_webull_flat_after_eod(state, cfg, nowdt, log=print):
    """Runs the item-4 check above once PER FLATTEN KIND per trading day (see the
    REVIEW FIX note below), and only once ALL of:
      * a flatten has genuinely fired today -- either the ordinary end-of-day flat_by
        (state['flat_by_done_date'] == today) or a same-day KILL flatten
        (state['kill_flatten_date'] == today -- EXIT SAFETY item 4 major, 2026-09-26: a
        kill-file day used to never set flat_by_done_date at all, so this check never
        ran on one and the EOD summary defaulted to a false 'yes' every kill day);
      * BEFORE the session flatten deadline only: no leg is still open in the book
        (state['legs'] empty) -- the flatten's own CLOSEs have not even reached the
        book yet otherwise -- AND BROKER_RECONCILE_POST_ORDER_GRACE_SEC has passed
        since the last broker send (state['_last_broker_send_at']), AND no CLOSE of ANY
        kind -- any queue entry whose intent is CLOSE, whatever its `why` -- is still
        left in _broker_resend (EXIT SAFETY item 4 major, 2026-09-26: this used to check
        only why=='close_retry' and nothing else, so (a) the flatten's own CLOSEs sent
        THIS SAME tick had not had a chance to land before this ran right after them --
        reading Webull's position milliseconds later could still show the shares and
        fire a false URGENT 'sell by hand' that then never re-checked -- and (b) a CLOSE
        still queued as why=='duplicate' (two legs flattening in the same instant) was
        ignored entirely);
      * OR the session flatten deadline has passed regardless, so a re-send that is
        itself stuck, a lot that could never be priced and stays in state['legs']
        forever (_close_all logs "lot left open" and skips it -- REVIEW FIX, 2026-09-26
        review, minor: the legs-still-open wait used to apply even past the deadline,
        so exactly the day a lot could not be flattened was the day this check never
        ran and the EOD summary silently showed "not checked" instead of an urgent
        push), or a send that never even landed a timestamp can never block this check
        forever.

    REVIEW FIX (2026-09-26 review, minor): keyed on WHICH flatten kind(s) have fired
    today (state['_eod_flat_checked_for']), not just the calendar date -- a kill
    flatten checked at 11:00 must not suppress a SEPARATE check after the ordinary
    15:58 flat_by flatten fires later the SAME day (or vice versa): before this fix, a
    kill-then-clear day stamped the date after the morning check and the 15:58 flatten
    was never checked at all, so the 16:05 EOD summary showed the morning's stale
    "Webull flat: yes" even if the end-of-day CLOSE itself failed.

    Stashes the result -- WITH today's date, so a stale prior day's verdict can never be
    read as current (EXIT SAFETY item 4 major, 2026-09-26) -- on
    state['_webull_flat_after_eod'] for _maybe_send_eod_summary's own line. Never
    raises."""
    try:
        today = nowdt.strftime("%Y-%m-%d")
        have_flat_by = state.get("flat_by_done_date") == today
        have_kill = state.get("kill_flatten_date") == today
        if not (have_flat_by or have_kill):
            return
        checked = state.get("_eod_flat_checked_for") or {}
        already_covered = (checked.get("date") == today
                          and (not have_flat_by or checked.get("flat_by"))
                          and (not have_kill or checked.get("kill")))
        if already_covered:
            return
        # HOLD OVERNIGHT: with a lot held overnight (or a close waiting for the open) still in
        # the book, Webull is judged only from the session close on. Before it the held lot
        # can still sell -- on its own exit between the flatten and the bell, or at 09:30 on a
        # KILL decided before the open -- and a verdict stamped earlier would stand for the
        # day (already_covered), saying "flat except the held lot" after the lot is gone.
        if any(isinstance((lot or {}).get("hold"), dict)
               or isinstance((lot or {}).get("close_pending"), dict)
               for lot in (state.get("legs") or {}).values()) \
                and not _market_closed_for_orders(nowdt):
            return
        deadline_passed = nowdt >= _session_flatten_deadline(nowdt)
        if not deadline_passed:
            # HOLD OVERNIGHT: a lot held overnight is not waited for -- it is expected to stay
            if any(not isinstance((lot or {}).get("hold"), dict)
                   for lot in (state.get("legs") or {}).values()):
                return
            grace = max(0.0, _cfg_num(cfg, "broker_reconcile_post_order_grace_sec",
                                      BROKER_RECONCILE_POST_ORDER_GRACE_SEC))
            sent_at = float(state.get("_last_broker_send_at", 0) or 0)
            if time.time() - sent_at < grace:
                return
            still_retrying = any(v.get("intent") == "CLOSE"
                                 for v in (state.get("_broker_resend") or {}).values())
            if still_retrying:
                return
        state.pop("_eod_flat_pushed", None)
        state.pop("_eod_flat_off", None)
        flat, qty = _check_webull_flat_after_eod(state, log=log)
        state["eod_flat_check_date"] = today
        state["_eod_flat_checked_for"] = {"date": today, "flat_by": have_flat_by,
                                          "kill": have_kill}
        # "pushed": the executor's own note for a not-flat / unread result went out (10-08
        # fourth review) -- the box monitor stays quiet on that result only when it did
        pushed = bool(state.pop("_eod_flat_pushed", False))
        off = state.pop("_eod_flat_off", None)
        state["_webull_flat_after_eod"] = {"date": today, "flat": flat, "shares": qty}
        held = _held_shares_by_leg(state)
        if held:
            # HOLD OVERNIGHT: flat True here means "flat except these held legs"; "shares"
            # is what Webull holds, "off" how far that is from the held lots
            state["_webull_flat_after_eod"]["held"] = held
            if off is not None:
                state["_webull_flat_after_eod"]["off"] = off
        if flat is not True:
            state["_webull_flat_after_eod"]["pushed"] = pushed
    except Exception as e:
        log(f"[qqq-exec] EOD Webull flat-check scheduling failed (non-fatal): "
            f"{type(e).__name__}: {e}")


# -- BROKER SEND HARD TIMEOUT (2026-09-26, "alerts in book" item 4) ------------------
# A hung SDK call inside adapter.place_stock_order() (client.order_v3.place_order --
# the same underlying kind of call default_webull_quote/order_status/reconcile have
# each already needed their own hard timeout for, see QUOTE_HARD_TIMEOUT_SEC /
# ORDER_STATUS_HARD_TIMEOUT_SEC / RECONCILE_HARD_TIMEOUT_SEC above) would otherwise
# freeze the whole 5s tick loop -- no other leg's send, no exits, no publish -- for as
# long as the SDK's own connect/read timeouts fail to fire. Run the call on its own
# single worker thread, bounded to BROKER_SEND_HARD_TIMEOUT_SEC; OrderAdapter is
# documented thread-safe (its own lock, see place_stock_order's own docstring) so the
# tick thread giving up on this call while it may still be running in the background is
# safe the same way _reconcile_with_timeout already relies on.
#
# ON TIMEOUT THE OUTCOME IS UNKNOWN, NEVER "NOT PLACED": client.order_v3.place_order may
# already have reached Webull before the timeout fired (a slow response, not a
# refusal), so this never returns ok=True/sent=False (that shape means "we know it was
# never sent" -- see place_stock_order's OFF/BLOCKED paths) and never fabricates a
# fill. It returns sent=True, ok=False, the real armed mode (so the existing PAPER/LIVE
# branches right below -- fill-price capture queueing, reconcile-due -- run exactly as
# they would for a normal send, which is exactly right: a reconcile is the thing that
# can actually resolve whether this order landed), plus outcome="UNKNOWN" and the
# client_order_id computed the same deterministic way place_stock_order itself would
# have (_sanitize_client_order_id(signal_id) is pure, no network -- safe to compute here
# even though the real call never returned).
#
# Downstream, unchanged by this: an UNKNOWN OPEN is never queued for auto-resend
# (_queue_broker_resend only ever queues an OPEN for why="halt"/"duplicate"/"busy"/
# "box_order", and this record matches none of them). An UNKNOWN CLOSE queues as
# why="close_retry"
# with needs_verify=True (no parseable 4xx in the reason -- see _queue_broker_resend),
# so _maybe_resend_broker_orders only retries it once _order_known_at_broker finds
# Webull's own record of the previous attempt DEAD (REJECTED/CANCELLED/FAILED with an
# explicit filled quantity -- then only the unfilled remainder goes; FINAL CLOSE
# RE-SEND RULE, 2026-09-26) -- exactly the path a genuine mid-send timeout inside
# place_stock_order's own per-part try/except already takes.
#
# ANOTHER TRACK (2026-09-26) is adding a genuine "UNKNOWN" outcome plus a PENDING-record
# resolver inside api/webull_orders.py itself. This side only needs to keep treating
# that shape the same way once it lands -- _is_unknown_outcome reads rec["outcome"]
# regardless of which side set it (or rec["parts"][i]["outcome"] for that track's own
# part shape -- see _is_unknown_outcome's item-4-minor review note).
#
# NOT FIXED HERE, FLAGGED FOR THE LEAD AT INTEGRATION (minor, 2026-09-26 review): this
# 40s bound is tighter than the worst case the OTHER track's own place_stock_order can
# legitimately spend while holding OrderAdapter._lock once its constants land (its own
# 25s SDK read timeout, plus its UNKNOWN_RESOLVE_WINDOW_SEC and
# SPLIT_PART_FILL_TIMEOUT_SEC, plus a part-2 place -- the other track's own numbers,
# not read here, so guessing a new bound from this side would be worse than leaving it
# for the lead to set once both tracks are actually merged). A slow send that would
# have completed could be declared UNKNOWN early, which pages and (via
# _skip_broker_housekeeping_for_inflight_send) blocks every other leg's sends until it
# finishes. Separately, and already true before this change: a reconcile() that hangs
# holding the same lock makes a send wait on it past this bound too (_reconcile_with_
# timeout's fail_closed on the tick thread can also block on it) -- the in-flight skip
# above only covers a hung SEND, never a hung reconcile.
BROKER_SEND_HARD_TIMEOUT_SEC = 40.0
_place_order_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="qqq-broker-send")


# MAJOR REVIEW FIXES (2026-09-26, "alerts in book" review of item 4 above):
#
# #1 -- a still-hung send keeps holding OrderAdapter._lock (place_stock_order takes it
# for the WHOLE SDK call, see api/webull_orders.py) for as long as it keeps running in
# the background after this side gives up waiting on it. The tick thread's OWN later
# calls into update_daily_pnl/reset_daily_pnl (_sync_broker_daily_pnl) and reconcile()/
# fail_closed (_reconcile_with_timeout, via _maybe_run_broker_reconcile) take that same
# lock, so the FIRST of those after the timeout blocks too -- freezing the whole 5s tick
# loop one tick later, not just the send itself (repro'd offline with a real
# OrderAdapter + a place_order that waits on an Event -- scratchpad lockprobe.py: 1.5s
# after the UNKNOWN return, update_daily_pnl was still blocked). While frozen, neither
# this module's own stall/tick-failure pushes above can fire either -- the loop is stuck,
# not raising.
#
# #2 -- the shared worker has exactly ONE thread (_place_order_executor above), so a
# second send queued while the first is still hung does not run now: it sits behind the
# hang and only really executes once the hang clears, at some arbitrary later time,
# against believed-position/price state that has moved on since. That includes another
# leg's flatten and every close_retry re-send -- each would itself queue, block the tick
# for BROKER_SEND_HARD_TIMEOUT_SEC, come back UNKNOWN without ever having started, and
# only really reach Webull later out of context (repro: lockprobe.py's second send came
# back UNKNOWN, then place_order ran twice once the hang released).
#
# Both fixes key off the SAME piece of state: which future (if any) this module last
# handed to that one worker thread is still running. _place_stock_order_with_timeout
# refuses to submit a new send at all while the previous one has not resolved (#2,
# below); _run_broker_housekeeping checks the same thing before touching any
# lock-taking adapter method and skips itself for the tick, resuming once it clears (#1,
# see that function).
_inflight_send = {"future": None, "leg": None, "intent": None}
_send_stall_logged = {"active": False}   # housekeeping-skip log: once per episode, not per tick


def _send_inflight_future():
    """The in-flight broker-send future, or None once it has actually finished --
    clears `_inflight_send` the first time anyone notices it is done. Never raises."""
    fut = _inflight_send.get("future")
    if fut is None:
        return None
    try:
        done = fut.done()
    except Exception:
        done = True
    if done:
        _inflight_send["future"] = None
        _inflight_send["leg"] = None
        _inflight_send["intent"] = None
        return None
    return fut


def _skip_broker_housekeeping_for_inflight_send(log=print):
    """True (skip this tick's housekeeping) while a previous broker send is still
    running on the shared single worker thread and therefore still holding
    OrderAdapter._lock (major finding #1 above) -- logs ONCE per stall episode rather
    than every tick, then once more when it clears. Never raises."""
    fut = _send_inflight_future()
    if fut is not None:
        if not _send_stall_logged["active"]:
            _send_stall_logged["active"] = True
            log(f"[qqq-exec] broker housekeeping (daily P&L / reconcile) skipped this tick "
                f"-- a broker send for {_inflight_send.get('leg')} "
                f"{_inflight_send.get('intent')} is still in flight and holds the adapter "
                f"lock; resuming once it resolves")
        return True
    if _send_stall_logged["active"]:
        _send_stall_logged["active"] = False
        log("[qqq-exec] broker housekeeping resumed -- the in-flight broker send resolved")
    return False


def _is_unknown_outcome(rec):
    """True for a broker record whose outcome is genuinely unresolved -- this
    process's own hard-timeout record (below), a PENDING-resolver record from
    api/webull_orders.py's own side with outcome on the TOP-LEVEL record (see the
    module comment above), OR one of the other track's PART-shaped records (item 4
    minor, 2026-09-26 review): that side puts outcome="UNKNOWN" on
    rec["parts"][i]["outcome"] for a netted order, never on the top-level record, so a
    top-level-only check misses it and an UNKNOWN OPEN pages on the ordinary once-per-
    leg-per-day throttle instead of every time (the money-path re-send gating is
    unaffected either way -- sent=True with no 4xx already sets needs_verify=True, and
    an OPEN is never auto-resent regardless of this check). Never raises."""
    try:
        r = rec or {}
        if str(r.get("outcome") or "").upper() == "UNKNOWN":
            return True
        return any(str((p or {}).get("outcome") or "").upper() == "UNKNOWN"
                  for p in r.get("parts") or [])
    except Exception:
        return False


def _broker_row_ambiguous_send(sent, ok, reason, http_status=None):
    """True when a single send (the top-level record, or one netted part of it) reached
    the send path (`sent`) but came back not ok with NO definite 4xx of its own --
    exactly the "outcome genuinely unknown" case _queue_broker_resend's own
    `needs_verify` judgment already gates the next retry on (a 5xx, a timeout, or a
    dropped connection may have reached Webull's book before the failure happened; a 4xx
    is Webull answering SYNCHRONOUSLY that it refused the order outright -- a definite,
    already-known outcome). Never raises."""
    try:
        if not sent or ok:
            return False
        code = _broker_send_status_code(reason, http_status)
        return not (code is not None and 400 <= code < 500)
    except Exception:
        return False


def _broker_row_outcome(rec):
    """EXIT SAFETY item 5 (2026-09-26 minor review, THIRD REVIEW FIX): the
    BROKER_ORDER_COLS 'outcome' column -- one of OK / REFUSED / BLOCKED / UNKNOWN,
    always derivable from the same `rec` this row's other fields (ok/sent/mode/reason)
    already come from, so a reader of broker_orders.csv no longer has to reconstruct
    "was this genuinely unresolved" by re-deriving the logic from the raw reason text.
    UNKNOWN takes priority over ok/not-ok -- this process's own hard-timeout record, or
    a PENDING-resolver record from api/webull_orders.py's own side, can carry
    sent=True/ok=False exactly like an ordinary refusal, but its outcome is genuinely
    unresolved, not a known refusal.

    THIRD REVIEW FIX (2026-09-26, minor): this used to check _is_unknown_outcome alone
    -- which only fires when something upstream had ALREADY tagged the record
    outcome="UNKNOWN" explicitly. An ordinary exception, 5xx, or dropped connection
    (sent=True, ok=False, no parseable 4xx) never gets that tag; it was written to this
    CSV as REFUSED even though _queue_broker_resend's own needs_verify judgment (right
    below, on the very same `rec`) treats it as genuinely ambiguous and re-verifies
    before ever re-sending -- misreporting exactly the rows this column exists to flag.
    Now _broker_row_ambiguous_send re-derives that SAME judgment here: a plain send is
    ambiguous when sent=True/ok=False with no definite 4xx; a SPLIT send (rec["parts"]
    has more than one entry) is ambiguous when ANY part is sent/not-ok with no definite
    4xx of its own, mirroring _queue_broker_resend's own per-part reasoning for a netted
    CLOSE (a 417 on one part must never hide a same-record part that timed out with no
    status at all). Never raises (falls back to UNKNOWN, the safest reading of a row
    this function itself could not classify)."""
    try:
        r = rec or {}
        if _is_unknown_outcome(r):
            return "UNKNOWN"
        parts = r.get("parts") or []
        if len(parts) > 1:
            ambiguous = any(
                _broker_row_ambiguous_send(p.get("sent"), p.get("ok"),
                                          p.get("reason") or p.get("error"),
                                          p.get("http_status"))
                for p in parts if isinstance(p, dict))
        else:
            ambiguous = _broker_row_ambiguous_send(
                r.get("sent"), r.get("ok"), r.get("reason") or r.get("error"),
                r.get("http_status"))
        if ambiguous:
            return "UNKNOWN"
        if r.get("ok"):
            return "OK"
        if r.get("mode") == "BLOCKED":
            return "BLOCKED"
        return "REFUSED"
    except Exception:
        return "UNKNOWN"


def _place_stock_order_with_timeout(adapter, *, leg, signal_id, symbol, side, qty,
                                    intent, mode, log=print, remainder=False):
    """adapter.place_stock_order(...) bounded to BROKER_SEND_HARD_TIMEOUT_SEC wall-clock
    on its own worker thread -- see the module comment above this function for why and
    what a timeout returns. Never raises (an unexpected exception from the executor
    itself is left to propagate to _mirror_to_broker's own outer except, same as before
    this function existed).

    MAJOR REVIEW FIX #2 (2026-09-26): refuses to submit at all while a previous send is
    still running on the shared single worker (_send_inflight_future) -- see the module
    comment above _inflight_send for why queuing behind a hung send is unsafe. Returns a
    definite, immediate not-sent record instead (mode="BLOCKED", sent=False,
    inflight_blocked=True), which _queue_broker_resend already routes exactly like any
    other not-ok CLOSE (why="close_retry"; sent=False on its OWN never sets needs_verify
    -- but a still-unresolved EARLIER attempt's needs_verify/last_signal_id survives
    this one untouched, see _queue_broker_resend's item-1-critical review note --
    retried only once the hung call resolves and either the adapter's believed position
    or _order_known_at_broker reflects its real outcome) and never auto-resends for an
    OPEN (no "halted:"-prefixed BLOCKED reason -> no why at all). `inflight_blocked`
    (minor, 2026-09-26 review) also tells _mirror_to_broker to skip the phone push for
    THIS record -- the still-unresolved earlier attempt already paged once for the same
    episode (an UNKNOWN timeout alert, or its own prior not-ok push), and every 5-10-
    20-30s retry coming back BLOCKED while the hang persists would otherwise re-page on
    its own backoff for as long as the hang lasts."""
    prior = _send_inflight_future()
    if prior is not None:
        coid = webull_orders._sanitize_client_order_id(signal_id)
        reason = ("previous broker send still in flight (hung) -- not queuing another "
                 "send behind it")
        log(f"[qqq-exec] {reason} (leg {leg} {intent}, signal {signal_id})")
        return {"leg": leg, "symbol": symbol, "side": side, "qty": qty, "intent": intent,
               "signal_id": signal_id, "client_order_id": coid, "mode": "BLOCKED",
               "ok": False, "sent": False, "duplicate": False, "reason": reason,
               "inflight_blocked": True}
    fut = _place_order_executor.submit(
        adapter.place_stock_order, leg=leg, signal_id=signal_id, symbol=symbol,
        side=side, qty=qty, intent=intent, **({"remainder": True} if remainder else {}))
    _inflight_send["future"] = fut
    _inflight_send["leg"] = leg
    _inflight_send["intent"] = intent
    try:
        result = fut.result(timeout=BROKER_SEND_HARD_TIMEOUT_SEC)
        _inflight_send["future"] = None
        return result
    except concurrent.futures.TimeoutError:
        fut.cancel()   # no-op once the worker has started it; drops it if it had not
        coid = webull_orders._sanitize_client_order_id(signal_id)
        reason = (f"broker send timed out after {BROKER_SEND_HARD_TIMEOUT_SEC:g}s -- "
                 f"Webull may or may not have received this order, outcome unknown")
        log(f"[qqq-exec] {reason} (leg {leg} {intent}, signal {signal_id})")
        # deliberately NOT clearing _inflight_send here -- the worker thread is still
        # running this call in the background (that is the whole reason the outcome is
        # UNKNOWN, not "not placed"), so it must keep reading as in-flight until
        # _send_inflight_future() next observes fut.done().
        return {"leg": leg, "symbol": symbol, "side": side, "qty": qty, "intent": intent,
               "signal_id": signal_id, "client_order_id": coid, "mode": mode,
               "ok": False, "sent": True, "duplicate": False, "outcome": "UNKNOWN",
               "reason": reason}
    except Exception:
        _inflight_send["future"] = None
        raise


def _mirror_to_broker(state, *, leg, side, shares, shadow_px, intent, ts=None, seq=0,
                      trade_id=None, resend=0, requeue=True, nowdt=None, log=print,
                      remainder=False):
    """Call after the shadow's own order/trade row is already recorded. Never raises.

    `nowdt` (EXIT SAFETY item 4 minor, 2026-09-26 review): the calling tick's OWN
    notion of "now" (tick()'s own `nowdt`, threaded down through _open_lot/_reduce_lot/
    _close_all/_route_fills/_mark_and_check_breaker) -- passed straight through to
    _queue_broker_resend so a close_retry item's session_date is stamped from the SAME
    clock _maybe_resend_broker_orders later compares it against, never the real wall
    clock (_now_et()), which a test's simulated `nowdt` (or a real clock drifting across
    midnight mid-tick) could otherwise disagree with. None (every caller with no tick of
    its own -- a direct call, a test, the orphan-broker repair's requeue=False path
    which never reaches _queue_broker_resend anyway) falls back to _now_et() exactly as
    before this parameter existed.

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
    # AFTER-CLOSE GUARD (2026-09-28, see _market_closed_for_orders): judged on the calling
    # tick's own clock, so only when the caller passes one (every tick() path does, the
    # FLATTEN_BROKER orphan repair included). No order call, no re-send queue. A CLOSE
    # blocked here while the adapter's books still hold shares for the leg pushes once
    # (_alert_close_blocked_after_close); _maybe_check_webull_flat_after_eod still pages
    # if Webull is left holding shares.
    market_closed = nowdt is not None and _market_closed_for_orders(nowdt)
    requeue_asked = requeue
    if market_closed:
        requeue = False
    try:
        if market_closed:
            raise _MarketClosed()
        adapter = _get_broker_adapter(log=log)
        mode, _mode_reason = adapter.effective_mode()
        armed = mode in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE)
        at_send = _LEASE.send_gate(_LEASE.uid) if armed else None
        lease_reason = None
        if armed:
            if not state.get("_broker_lease_ok", True):
                lease_reason = state.get("_broker_lease_reason") or "lease unverifiable"
            elif at_send is not None and not at_send[0]:
                lease_reason = at_send[1]
        # EXIT SAFETY item 3 (2026-09-26; NARROWED 2026-09-26 review -- see the finding
        # this fixed): a CLOSE must never be the thing an OUTAGE-unverifiable Firestore
        # lease blocks while THIS process is the serving host. A genuine hand-off to
        # another host already makes THIS process stand down entirely (_stand_down stops
        # ticking/publishing/sending outright) -- so by the time this line runs, a
        # genuinely UNVERIFIABLE lease (a Firestore read failing/timing out, or this
        # process's own stamp not landing) means an OUTAGE, not a real second host about
        # to send the same order.
        #
        # This must NEVER exempt (a) a CONFIRMED fresh foreign lease -- reason text
        # "host 'X' holds a fresh lease (...)" from _check_lease_for_broker means another
        # host has POSITIVELY taken over and may send the identical CLOSE right now, or
        # (b) this process's own _LEASE genuinely having been marked lost mid-tick --
        # send_gate's "lease lost: ..." (held=False is this process's own confirmed
        # stand-down, not an outage). Exempting either risks the exact cross-host
        # double-sell this gate exists to prevent -- the local SERVING_LOCK only
        # arbitrates between two processes on ONE machine, never between the PC and the
        # cloud VM. So the exemption fires only when the actual reason text starts with
        # "lease unverifiable" AND this process's own _LEASE (if it is lease-managed at
        # all -- a direct call/test with no lease loop has uid=None) still believes it
        # holds the lease. _is_serving_standalone() is true only while THIS process
        # itself holds the LOCAL SERVING_LOCK (single process per machine, enforced by
        # serve()/_acquire_host_slot regardless of Firestore) -- so this can never widen
        # the gate for a caller/test with no such lock. The gate is UNCHANGED for an OPEN.
        #
        # REVIEW FIX (2026-09-26 review, minor, flagged for the lead as a residual risk):
        # two of _check_lease_for_broker's OWN "lease unverifiable"-prefixed reasons are
        # actually a FOREIGN claim, not an outage on our side -- "host 'X' claims the
        # lease but its timestamp is missing/unreadable" (that host's leased_at could not
        # be parsed, so its age could not be judged stale-or-fresh). That is a positive
        # sign another host may genuinely hold the lease right now, so it must be
        # excluded from the exemption exactly like the CONFIRMED-fresh-foreign-lease
        # reason already is above -- both name another host ("claims the lease"), so a
        # single substring check keeps them out.
        reason_text = str(lease_reason or "")
        close_lease_exempt = (
            intent == "CLOSE" and lease_reason is not None
            and reason_text.startswith("lease unverifiable")
            and "claims the lease" not in reason_text
            and (_LEASE.uid is None or _LEASE.held)
            and _is_serving_standalone())
        if armed and lease_reason is not None and not close_lease_exempt:
            log(f"[qqq-exec] broker {intent} for {leg} BLOCKED before send (mode={mode}): "
                f"{lease_reason} -- shadow record above stands, broker mirror suppressed")
            rec = {"ok": False, "sent": False, "mode": "BLOCKED", "reason": lease_reason,
                  "side": _broker_side(side, intent), "client_order_id": "",
                  "duplicate": False}
        else:
            rec = _place_stock_order_with_timeout(
                adapter, leg=leg, signal_id=signal_id, symbol=BROKER_SYMBOL,
                side=_broker_side(side, intent), qty=int(round(shares)), intent=intent,
                mode=mode, log=log, **({"remainder": True} if remainder else {}))
    except _MarketClosed:
        reason = (f"market closed: after today's session close, no broker order is sent "
                  f"(tick {nowdt.strftime('%H:%M:%S')} ET)")
        log(f"[qqq-exec] broker {intent} for {leg} BLOCKED before send: {reason} -- shadow "
            f"record above stands, broker mirror suppressed")
        rec = {"ok": False, "sent": False, "mode": "BLOCKED", "reason": reason,
               "side": _broker_side(side, intent), "client_order_id": "", "duplicate": False,
               "market_closed": True}
        if intent == "CLOSE" and requeue_asked:
            _alert_close_blocked_after_close(state, leg, nowdt, log=log)
    except Exception as e:
        rec = {"ok": False, "sent": False, "mode": "ERROR", "error": f"{type(e).__name__}: {e}"}
        log(f"[qqq-exec] broker adapter call failed for {leg} {intent} (non-fatal -- the "
            f"shadow record above stands): {type(e).__name__}: {e}")
    if rec.get("closed_by_resting"):
        # RESTING ORB STOP (2026-09-29): the gateway (or an earlier lookup) found the leg's
        # resting stop/target already FILLED at Webull, so nothing was sent. That fill is
        # the leg's CLOSE row (_book_resting_fills writes it, signal id qx<tid>C) -- no
        # second row here, no "Webull never held it" push, no re-send.
        cbr = rec["closed_by_resting"] or {}
        msg = (f"{leg} {intent}: already closed at Webull by the resting {cbr.get('kind') or 'stop'} "
               f"{cbr.get('client_order_id') or ''} ({cbr.get('filled') or '?'} share(s)"
               + (f" @ {float(cbr['filled_price']):.2f}" if _finite_or_none(cbr.get("filled_price"))
                  is not None else "") + ") -- no market close sent")
        log(f"[qqq-exec] {msg}")
        _log_event(state, "broker", msg, log=log)
        state["_broker_last"] = {"leg": leg, "intent": intent, "mode": rec.get("mode"),
                                 "ok": True, "reason": rec.get("reason") or msg,
                                 "closed_by_resting": True}
        if requeue:
            _queue_broker_resend(state, rec, leg=leg, side=side, shares=shares,
                                 shadow_px=shadow_px, intent=intent, ts=ts, seq=seq,
                                 trade_id=trade_id, resend=resend, signal_id=signal_id,
                                 nowdt=nowdt, log=log)
        return
    if (state.get("orb_resting") or {}).get("live_seen") and \
            rec.get("mode") in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
        # RESTING ORB STOP (2026-09-29 second review): a resting fill this send's gateway
        # found (say a PARTIAL stop fill, the market close clamped to what was left) gets
        # its row BEFORE this send's row -- the fill ledger's FIFO pairing (parity, the
        # Webull P&L of record, the daily-loss rail) caps a trade's closes at its OPEN's
        # shares in file order, so the market row written first would take them all.
        # Only once a stop mode has run (live_seen) -- "off" and log_only never rest
        # anything; no network.
        try:
            _book_resting_fills(state, _get_broker_adapter(log=log), nowdt or _now_et(), log=log)
        except Exception as e:
            log(f"[qqq-exec] resting fill booking before the {leg} {intent} row failed "
                f"(non-fatal -- the next tick books it): {type(e).__name__}: {e}")
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
        # EXIT SAFETY item 5 (2026-09-26 minor review): see BROKER_ORDER_COLS.
        "outcome": _broker_row_outcome(rec),
    }
    _append_csv(BROKER_ORDERS_CSV, BROKER_ORDER_COLS, row, BROKER_ORDERS_KEEP)
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
                                   log=log, side=side,
                                   # for _requeue_close_unfilled
                                   retry=({"side": side, "ts": None if ts is None else str(ts),
                                           "seq": seq, "trade_id": trade_id,
                                           "resend": int(resend or 0)}
                                          if intent == "CLOSE" and trade_id else None))
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
        # EXIT SAFETY item 1 (2026-09-26): scoped to `requeue` (the normal shadow-book
        # entry/exit path -- _open_lot/_reduce_lot/_close_all) so the orphan-broker
        # repair's own retries (requeue=False, _maybe_flatten_orphan_broker) do not also
        # page on every one of its own attempts -- that repair already escalates on its
        # own after FLATTEN_MAX_TRIES with its own phone alert. "nothing to close" is
        # excluded too: the notify right below this handles that confirmed-benign case
        # on its own terms (nothing real failed to exit).
        if requeue and _is_unknown_outcome(rec):
            # item 4 (2026-09-26): an UNKNOWN outcome is rarer and more dangerous than
            # an ordinary "not ok" (Webull may genuinely hold the order) -- always push,
            # never folded into _alert_broker_not_ok's once-per-day-per-leg OPEN
            # throttle, which exists for the much more common "refused/blocked" case.
            _alert_broker_send_unknown(state, leg=leg, intent=intent, side=row["side"],
                                       shares=shares, reason=row["reason"],
                                       client_order_id=row["client_order_id"], log=log)
        elif (requeue and intent == "OPEN" and trade_id and not rec.get("nothing_to_close")
              and sum(int(p.get("qty") or 0) for p in rec.get("unsent_parts") or [])):
            # 10-08 review (plan group B / E): part of a split OPEN landed and its refused
            # rest is queued below for ONE re-send a few seconds from now -- no push yet. The
            # re-send decides: accepted is group E (timeline only), refused or never sent
            # pushes the strategy's one "entry missed" note then.
            _log_event(state, "broker",
                       f"QQQ BROKER OPEN NOT OK: {leg} {row['side']} {shares}sh -- part of the "
                       f"split order was refused ({_plain_broker_error(row['reason']) or row['reason']}); "
                       f"the rest is re-sent once", log=log)
        elif requeue and intent == "OPEN" and trade_id and "HAS_BOX_ORDER" in row["reason"]:
            # 2026-10-09 (MANAGER GO): refused only because another leg's opposite opening
            # order was still working -- _queue_broker_resend queues it (why="box_order") for
            # a re-send a few seconds from now, so no push yet. The re-send decides: accepted
            # is group E (timeline only); the give-up pushes the one "entry missed" note.
            _log_event(state, "broker",
                       f"QQQ BROKER OPEN NOT OK: {leg} {row['side']} {shares}sh -- Webull still "
                       f"had an opposite order working; re-sent in a few seconds", log=log)
        elif requeue and not rec.get("nothing_to_close") and not rec.get("inflight_blocked"):
            # PAGING STORM (minor, 2026-09-26 review): `inflight_blocked` (see
            # _place_stock_order_with_timeout) means this specific record is just this
            # tick's re-send bouncing off a STILL-hung earlier send, not a new failure of
            # its own -- the UNKNOWN alert already paged once for that earlier send's own
            # timeout, and the queue's own not-ok log line just above still runs, so
            # nothing here is silently lost, only the repeat phone push for the same
            # episode on every 5-10-20-30s retry while the hang persists.
            _alert_broker_not_ok(state, leg=leg, intent=intent, side=row["side"],
                                 shares=shares, reason=row["reason"], log=log)
    if rec.get("nothing_to_close"):
        # WEBULL PUSH PLAN 10-07, group E (the safe outcome): timeline + log only, no push
        msg = (f"QQQ BROKER: {leg} closed in the book, but Webull never held it (its buy "
               f"never went through) -- no sell sent, Webull stays flat for {leg}")
        log(f"[qqq-exec] {msg}")
        _log_event(state, "broker", msg, log=log)
    unsent_qty = sum(int(p.get("qty") or 0) for p in rec.get("unsent_parts") or [])
    open_rest = (unsent_qty and intent == "OPEN" and requeue and trade_id
                 and not _is_unknown_outcome(rec))
    if rec.get("partial") and not open_rest:
        # ORDER NETTING (2026-09-24): one or more of this leg event's broker parts (see
        # api.webull_orders.place_stock_order's `parts`) was refused while at least one
        # other part landed -- broker_sent_positions[leg] only moved by the accepted
        # share of it (see that function's own docstring), so this leg's book and
        # Webull's real position for it are now off by the refused remainder. Worth a
        # push the same way "nothing to close" is -- both are "the book and the broker
        # disagree" situations the owner needs to look at, not something later ticks
        # self-heal.
        # WEBULL PUSH PLAN 10-07: an OPEN is group B (the strategy's one "entry missed"
        # note of the day), a CLOSE group A (the close_retry re-sends the rest)
        msg = (f"QQQ BROKER: {leg} {intent} only PARTIALLY reached Webull: {row['reason']}")
        _log_event(state, "broker", msg, log=log)
        if intent == "OPEN":
            _say_entry_missed(state, leg, f"Only part of the {_leg_word(leg)} "
                              f"{_open_word(row['side'])} reached Webull", side=row["side"], log=log)
        else:
            _say_exit_late(state, leg, "only part of it reached Webull", side=row["side"],
                           log=log)
    if unsent_qty and intent == "OPEN" and requeue and trade_id and not open_rest:
        # part 1 is UNKNOWN: the rest could stack on shares that landed -- not re-sent
        log(f"[qqq-exec] broker OPEN for {leg}: {unsent_qty} share(s) of a split order not "
            f"sent and part 1's outcome is UNKNOWN -- not re-sent")
    elif open_rest:
        # SPLIT REMAINDER (2026-09-26): a split OPEN's unsent rest goes ONCE (why=
        # "remainder"); a split CLOSE's rest is re-sent by close_retry instead.
        now = time.time()
        state.setdefault("_broker_resend", {})[f"{leg}:{intent}"] = {
            "leg": leg, "intent": intent, "side": side, "shares": unsent_qty,
            "shadow_px": shadow_px, "ts": None if ts is None else str(ts), "seq": seq,
            "trade_id": trade_id, "why": "remainder", "tries": int(resend or 0),
            "first_at": now, "last_at": now,
            "session_date": (nowdt or _now_et()).strftime("%Y-%m-%d")}
        log(f"[qqq-exec] broker OPEN for {leg}: {unsent_qty} share(s) of a split order not "
            f"sent (held back or refused) -- queued for one re-send")
    if requeue:
        _queue_broker_resend(state, rec, leg=leg, side=side, shares=shares,
                             shadow_px=shadow_px, intent=intent, ts=ts, seq=seq,
                             trade_id=trade_id, resend=resend, signal_id=signal_id,
                             nowdt=nowdt, log=log)


# -- broker RE-SEND (2026-09-21) ---------------------------------------------------------
def _broker_halt_source(log=print):
    """The adapter's halt source while it is halted ("reconcile" / "kill_file"), else
    None. Never raises; an adapter without halt_state() (a test fake) reads as not halted."""
    try:
        halted, source, _reason = _get_broker_adapter(log=log).halt_state()
        return (source or "unknown") if halted else None
    except Exception:
        return None


# EXIT SAFETY item 2 major (2026-09-26 review): api.webull_orders.OrderAdapter records a
# raw Webull ServerException verbatim (see _plain_broker_error's own module note below),
# e.g. "ServerException: HTTP Status: 417, Code: OPENAPI_CAN_NOT_TRADING_FOR_FIXGW_NOT_
# READY_MARKET, ...". A 4xx status means Webull answered SYNCHRONOUSLY that it refused
# the order outright -- a definite, already-known outcome, not an ambiguous one. A 5xx,
# a timeout, or a connection error carries no such answer: the request may have reached
# Webull's book before the failure happened, so the outcome is genuinely unknown.
# 2026-09-26: the SAME parser as the adapter's _definite_refusal ("HTTP NNN" too), and
# the code the adapter parsed itself (rec/part "http_status") wins when present.
_HTTP_STATUS_RE = webull_orders._HTTP_STATUS_RE


def _broker_send_status_code(text, code=None):
    """The numeric HTTP status of a failed send: `code` (the adapter's own parsed
    record["http_status"] / part["http_status"]) when it is a number, else the one a
    Webull ServerException string carries, or None when neither says (a non-Webull
    exception, a rail refusal already written in plain English, a bare timeout/
    connection message, ...). Never raises."""
    try:
        if code is not None:
            return int(code)
    except (TypeError, ValueError):
        pass
    try:
        m = _HTTP_STATUS_RE.search(str(text or ""))
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _whole_qty(v):
    """A share count as a non-negative whole int, or None when `v` is missing, not a
    number, negative, not finite or not a whole number. Used for the sizes the CLOSE
    re-send verify step subtracts from -- a size it cannot read makes it hold, never
    guess. Never raises."""
    try:
        if v is None or isinstance(v, bool) or (isinstance(v, str) and not v.strip()):
            return None
        f = float(v)
        if not math.isfinite(f) or f < 0 or abs(f - round(f)) > 1e-9:
            return None
        return int(round(f))
    except (TypeError, ValueError):
        return None


def _queue_broker_resend(state, rec, *, leg, side, shares, shadow_px, intent, ts, seq,
                         trade_id, resend, signal_id=None, nowdt=None, log=print):
    """Queue a broker order that did not go through for another try later
    (state["_broker_resend"]), or drop it from the queue once it has gone through. Never
    raises.

    `nowdt` (EXIT SAFETY item 4 minor, 2026-09-26 review): see _mirror_to_broker's own
    docstring -- used only to stamp a brand-new item's own "session_date" (below) from
    the calling tick's own notion of "now", never the wall clock.

    KEYED "<leg>:<intent>" (unchanged) for an OPEN, a "duplicate" or a "halt" CLOSE --
    at most one of each can ever be genuinely pending for a leg (a leg holds one open
    lot at a time). A "close_retry" CLOSE (EXIT SAFETY item 2 minor, 2026-09-26) is
    instead keyed "<leg>:<intent>:<trade_id>": re-entering a leg while an earlier failed
    CLOSE for the PREVIOUS trade is still retrying used to overwrite that older entry
    under the same plain "<leg>:CLOSE" key -- clamped to the newer trade's size and
    silently dropping the older lot's own retry. Keying by trade_id lets both coexist;
    a resolution (rec.get("ok")) checks both key shapes so it cleans up whichever one is
    actually queued regardless of which `why` queued it.

    Failures worth another try:
      * an OPEN the adapter BLOCKED because of its OWN reconcile halt. 2026-09-21: a false
        post-order mismatch halted entries at 09:42, NOISE entered at 09:45:12, its buy
        was blocked, the halt cleared seconds later -- and nothing ever sent the buy, so
        the book held NOISE all day and Webull did not;
      * ANY order Webull rejected as a duplicate of one still in its book (417
        OPENAPI_ORDER_RISK_RULE_DUPLICATE_ORDER_CHECK). Webull compares the ORDER, not our
        id, so two legs sending the identical SELL/BUY 10 QQQ in one instant collide: the
        09:31 orphan repair, an end-of-day flatten with two legs open, two legs entering
        on the same bar. That order was never placed, so it goes again a tick later,
        after the one it collided with has filled;
      * 2026-10-09 (MANAGER GO): an OPEN Webull refused because an opposite OPENING order
        was still working on the symbol (417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER -- a pending
        buy-opening and sell-opening order may not coexist) -- why="box_order". ENGU-Q's
        BUY 10 still working when NOISE's short arrives in the same tick: never placed, so
        it goes again exactly like a same-instant duplicate, bounded the same way;
      * EXIT SAFETY item 2 (2026-09-26): ANY CLOSE that came back not ok for ANY reason
        (refused, exception/timeout, BLOCKED by the lease gate, a kill-file halt, ...) --
        why="close_retry" -- EXCEPT the confirmed "nothing to close" case (the book closed
        a lot the broker never actually held; nothing needs to reach Webull). Unlike the
        two cases above this is not bounded by BROKER_RESEND_MAX_TRIES/BROKER_OPEN_
        RESEND_WINDOW_MIN -- see _maybe_resend_broker_orders, which instead retries with
        backoff until the session flatten deadline: an EXIT that keeps failing is worse
        left un-retried than an OPEN is, and a real broker/network outage can outlast 3
        tries in seconds.
    A kill-file halt on an OPEN, a lease block on an OPEN, a rails refusal, "nothing to
    close" and an OFF / ERROR record on an OPEN are never re-sent: those are decisions (or
    a broken adapter) -- only a CLOSE gets the catch-all above."""
    try:
        q = state.setdefault("_broker_resend", {})
        plain_key = f"{leg}:{intent}"
        # trade-scoped key only ever used for a CLOSE's close_retry entries (see the
        # docstring above) -- None for an OPEN, so its lookups below fall through to
        # plain_key exactly as before this feature existed.
        trade_key = f"{leg}:{intent}:{trade_id}" if intent == "CLOSE" and trade_id else None
        existing, existing_key = None, None
        for k in (trade_key, plain_key):
            if k is None:
                continue
            e = q.get(k)
            if e and trade_id and e.get("trade_id") == trade_id:
                existing, existing_key = e, k
                break
        if rec.get("ok"):
            if existing_key:
                q.pop(existing_key, None)
            if intent == "CLOSE":
                # item 3 (2026-09-26 lead decision): this CLOSE-failure episode is over
                # -- the NEXT failure for this leg (a different trade) should page
                # immediately again, not inherit this episode's cooldown.
                _close_fail_alert_reset(state, leg)
            return
        if intent == "OPEN" and rec.get("unsent_parts"):
            # its rest is _mirror_to_broker's "remainder" item -- never overwrite it
            return
        text = str(rec.get("reason") or rec.get("error") or "")
        why = None
        if "DUPLICATE_ORDER_CHECK" in text:
            why = "duplicate"
        elif intent == "OPEN" and "HAS_BOX_ORDER" in text:
            why = "box_order"
        elif (intent == "OPEN" and rec.get("mode") == "BLOCKED" and text.startswith("halted:")
              and _broker_halt_source(log=log) == "reconcile"):
            why = "halt"
        elif intent == "OPEN" and rec.get("busy") and not rec.get("sent"):
            # RESTING ORB STOP (2026-09-29): the order gateway held it back -- a resting
            # order not yet confirmed cancelled, or an earlier part still working at
            # Webull. Nothing reached Webull; it goes again like a same-instant duplicate.
            why = "busy"
        elif intent == "CLOSE" and not rec.get("nothing_to_close"):
            why = "close_retry"
        if not why or not trade_id:
            return
        key = trade_key if (why == "close_retry" and trade_key) else plain_key
        if existing_key and existing_key != key:
            # `why` changed shape between retries (e.g. a same-instant duplicate on the
            # first try, a generic failure on the next) -- move the entry rather than
            # leaving a stale copy behind under the old key.
            q.pop(existing_key, None)
        now = time.time()
        sent = bool(rec.get("sent"))
        # EXIT SAFETY item 2 major (2026-09-26 review): a 4xx ServerException (see
        # _broker_send_status_code) means Webull answered SYNCHRONOUSLY that it refused
        # this specific order -- e.g. the four live "417 ... OPENAPI_CAN_NOT_TRADING_
        # FOR_FIXGW_NOT_READY_MARKET" refusals this fix is responding to. That is a
        # definite, already-known "never landed" outcome, not an ambiguous one, so no
        # order_status verification is needed before the next retry (see
        # _maybe_resend_broker_orders). Only a send with NO parseable HTTP status at all
        # (a 5xx, a timeout, a dropped connection, the adapter's own outer except around
        # e.g. an account-id read) still needs verifying: place_stock_order may have
        # reached Webull's book before the failure happened.
        #
        # SPLIT ORDERS (item 2 major, SECOND 2026-09-26 review, of a NETTED close --
        # rec["parts"] has more than one entry, see api.webull_orders.place_stock_order's
        # own docstring): the combined `text` above can hide one part's real outcome
        # behind another's -- a 417 on part 1 matches _HTTP_STATUS_RE first even when
        # part 2 timed out with no status at all -- and _order_known_at_broker would ask
        # about the BASE client_order_id, which Webull never saw (each part went out
        # under its OWN id, see _part_client_order_id): a "not found" answer for the base
        # id is not a positive "never landed" for a part that actually reached Webull, so
        # base-id verification is wrong for a split record either way. Judge PER PART
        # instead: a part needs verifying when it is not ok and carries no definite 4xx
        # of its own; `unresolved_part_ids` (checked by _order_known_at_broker_any) is
        # what the next retry actually verifies against -- never the base id -- for a
        # split record.
        #
        # FINAL CLOSE RE-SEND RULE (2026-09-26 lead decision): the verify step can now
        # answer "dead with N filled" and re-send only the unfilled remainder, so the
        # queue also records the SIZE of what is being verified -- `verify_qty` (this
        # attempt's whole size: the single order's qty, or the sum of every part of a
        # split), `unresolved_part_qty` (each unresolved part's own qty, split only) and
        # `verify_landed_qty` (the parts Webull already accepted outright, split only).
        # Any size that cannot be read is stored as None, and the verify step then holds
        # rather than guess a remainder.
        parts = rec.get("parts") or []
        if len(parts) > 1:
            # 2026-09-26: a held-back part (sent=False) is just remainder; only a 4xx on a
            # part not UNKNOWN/WORKING is "never placed" -- a 5xx/504 may have landed
            unresolved = [p for p in parts
                          if not p.get("ok") and p.get("sent", True)
                          and (p.get("outcome") in ("UNKNOWN", "WORKING")
                               or not 400 <= (_broker_send_status_code(
                                   p.get("reason"), p.get("http_status")) or 0) < 500)]
            unresolved_part_ids = [p.get("client_order_id") for p in unresolved]
            needs_verify = sent and bool(unresolved_part_ids)
            unresolved_part_qty = {p.get("client_order_id"): _whole_qty(p.get("qty"))
                                   for p in unresolved}
            part_qtys = [_whole_qty(p.get("qty")) for p in parts]
            verify_qty = None if None in part_qtys else sum(part_qtys)
            landed_qtys = [_whole_qty(p.get("qty")) for p in parts if p.get("ok")]
            verify_landed_qty = None if None in landed_qtys else sum(landed_qtys)
        else:
            status_code = _broker_send_status_code(text, rec.get("http_status"))
            needs_verify = sent and not (status_code is not None and 400 <= status_code < 500)
            unresolved_part_ids = None
            unresolved_part_qty = None
            # the size that actually went out: the one part's own qty when the adapter
            # reported parts, else the record's qty, else what was asked for
            verify_qty = (_whole_qty(parts[0].get("qty"))
                          if len(parts) == 1 and isinstance(parts[0], dict) else None)
            if verify_qty is None:
                verify_qty = _whole_qty(rec.get("qty"))
                if verify_qty is None:
                    verify_qty = _whole_qty(shares)
                # MAJOR (2026-09-26 review): with no parts on the record (the hard
                # timeout path of _place_stock_order_with_timeout, an adapter exception
                # before any part was planned) `qty` is what was ASKED, but the adapter
                # clamps a CLOSE to what it holds for the leg (broker_sent_positions --
                # "clamped to ... only that much of this leg reached the broker"). A
                # failed or hung send never moves the adapter's books, so the leg's
                # believed qty read NOW is that pre-attempt clamp: cap at it, or a later
                # "dead with N filled" remainder is computed against shares that never
                # went out (book 10, adapter 6, 4 filled -> re-send 6, not 2).
                if intent == "CLOSE" and verify_qty is not None:
                    held_now = _believed_qty_for_leg(leg, log=log)
                    if held_now is not None:
                        verify_qty = min(verify_qty, held_now)
            verify_landed_qty = 0
        # EXIT SAFETY item 1 critical (2026-09-26 review of item 4's "alerts in book"):
        # THIS attempt may itself never have reached the send path at all -- e.g. the
        # definite, immediate mode="BLOCKED"/sent=False record _place_stock_order_with_
        # timeout returns while a PREVIOUS send for this same key is still hung in the
        # background (see that function's own docstring). That record says nothing at
        # all about the still-unresolved earlier attempt -- rebuilding needs_verify/
        # last_signal_id from it alone would silently drop the fact that THAT attempt
        # (not this refusal) still needs _order_known_at_broker's say-so, letting the
        # very next retry re-send blind once the hang clears. Only a THIS-attempt that
        # actually reached the send path (sent=True) may replace an unresolved earlier
        # one; a not-sent attempt on top of an unresolved needs_verify entry leaves that
        # entry's own last_signal_id/unresolved_part_ids exactly as they were.
        if not sent and existing and existing.get("needs_verify"):
            needs_verify = True
            last_signal_id = existing.get("last_signal_id")
            unresolved_part_ids = existing.get("unresolved_part_ids")
            # the SIZE of that earlier attempt travels with its ids (FINAL CLOSE
            # RE-SEND RULE) -- a remainder is always computed against the attempt
            # actually being verified, never this not-sent requeue's own size.
            unresolved_part_qty = existing.get("unresolved_part_qty")
            verify_qty = existing.get("verify_qty")
            verify_landed_qty = existing.get("verify_landed_qty")
        else:
            last_signal_id = signal_id
        q[key] = {"leg": leg, "intent": intent, "side": side, "shares": shares,
                  "shadow_px": shadow_px, "ts": None if ts is None else str(ts),
                  "seq": seq, "trade_id": trade_id, "why": why,
                  "tries": int(resend or 0),
                  "first_at": (existing.get("first_at") if existing else None) or now,
                  "last_at": now,
                  # EXIT SAFETY item 4 minor (2026-09-26 review): the ET date this item
                  # was first queued, preserved across retries like first_at -- lets
                  # _maybe_resend_broker_orders give up on a close_retry left over from
                  # an earlier trading day (the process was down overnight) instead of
                  # firing a stale sell into the next day's pre-open/open. Stamped from
                  # the TICK'S OWN `nowdt` (falling back to the wall clock only when no
                  # caller supplied one), never the wall clock alone -- that check later
                  # compares this against _maybe_resend_broker_orders' own `nowdt`
                  # argument, and the two must agree even when a test (or a real clock
                  # ticking across midnight mid-tick) makes them differ.
                  "session_date": (existing.get("session_date") if existing else None)
                                 or (nowdt or _now_et()).strftime("%Y-%m-%d"),
                  # EXIT SAFETY item 1 critical (2026-09-26): whether THIS attempt's
                  # place_stock_order call actually reached the adapter's send path
                  # (rec['sent']) and under which signal_id -- see
                  # _order_known_at_broker / _maybe_resend_broker_orders. A CLOSE whose
                  # outcome is genuinely unknown (sent=True, ok=False -- a timeout, or a
                  # dropped connection after Webull already took the order) must be
                  # verified against Webull's own order record before ever re-sending
                  # blind, because api.webull_orders.place_stock_order does NOT update
                  # believed_positions/broker_sent_positions on that path -- so
                  # _believed_qty_for_leg alone cannot tell "genuinely never sent" apart
                  # from "sent, outcome unknown". `sent` is kept verbatim for anything
                  # still reading it; `needs_verify` (EXIT SAFETY item 2 major, 2026-09-26
                  # review) is the one _maybe_resend_broker_orders actually gates on --
                  # see the note on status_code just above -- and, for a split record,
                  # `unresolved_part_ids` is what it verifies against, never
                  # `last_signal_id` (the base id a split order never actually used).
                  "sent": sent,
                  "needs_verify": needs_verify,
                  "last_signal_id": last_signal_id,
                  "unresolved_part_ids": unresolved_part_ids,
                  # FINAL CLOSE RE-SEND RULE (2026-09-26): the size of the attempt
                  # under verification -- see the note above `parts` for each field.
                  "verify_qty": verify_qty,
                  "unresolved_part_qty": unresolved_part_qty,
                  "verify_landed_qty": verify_landed_qty}
        why_txt = {"duplicate": "Webull saw a same-instant duplicate",
                  "box_order": "Webull still had an opposite order working",
                  "halt": "blocked by a reconcile halt",
                  "busy": "held back by the order gateway",
                  "close_retry": f"broker record not ok ({text or 'see the broker log'})"}[why]
        tries_txt = (f"{int(resend or 0)} re-sends so far" if why == "close_retry"
                    else f"{int(resend or 0)} of {BROKER_RESEND_MAX_TRIES} re-sends used")
        log(f"[qqq-exec] broker {intent} for {leg} queued for a re-send ({why_txt}; "
            f"{tries_txt})")
    except Exception as e:
        log(f"[qqq-exec] broker re-send bookkeeping failed (non-fatal): {type(e).__name__}: {e}")


# FINAL CLOSE RE-SEND RULE (2026-09-26, lead decision after four review rounds): one
# Webull margin account nets every leg, so an ACCOUNT position read can never say which
# leg's shares are still out -- a CLOSE whose previous attempt is ambiguous is never
# re-sent on position arithmetic. Only Webull's own record of THAT order (looked up by
# its client_order_id) may release a re-send, and only when it says the order is dead:
#   FILLED                                   -> known; drop the retry, never re-send
#   a DOCUMENTED live status (PENDING/
#     SUBMITTED/PARTIAL_FILLED)              -> known; keep waiting, never re-send
#   REJECTED/CANCELLED/FAILED with an
#     EXPLICIT filled quantity               -> dead; re-send only what did not fill
#   anything else (lookup error/timeout,
#     not found/404, no status, a status
#     this code does not recognise such as
#     EXPIRED or garbage, a dead status with
#     no readable filled qty, a record for a
#     different order id)                    -> unverifiable; hold and page
# The live list is a WHITELIST (minor, 2026-09-26 review): an unrecognised status used to
# read as "working", which never pages -- a close whose order was actually dead under an
# unexpected status then sat silently until the flatten deadline. Statuses come from
# Webull's Get Order Detail schema (see api.webull_orders.order_status_fields) and the
# SDK's own webull.trade.common.order_status.OrderStatus ("PARTIAL FILLED" with a space
# there, so spaces/hyphens are normalised to "_" before matching).
_ORDER_DEAD_STATUSES = ("REJECTED", "CANCELLED", "CANCELED", "FAILED")
_ORDER_LIVE_STATUSES = ("PENDING", "SUBMITTED", "PARTIAL_FILLED")

# The order lookup below runs on _order_status_executor's ONE worker. A lookup that hit
# ORDER_STATUS_HARD_TIMEOUT_SEC may still be running there; every further submit would
# only queue behind it and pile up stale calls against an already-struggling endpoint
# (minor, 2026-09-26 review). So a timed-out future is cancelled (a no-op once started)
# and remembered here, and while it is still not done the next lookup is not submitted
# at all -- that step simply reads as unverifiable (hold and page, as for a timeout).
_order_lookup_inflight = {"future": None}
# Set when a lookup timed out; further lookups within ORDER_LOOKUP_COOLDOWN_SEC are
# skipped as unverifiable, so a worker stuck on another call (fill capture shares it)
# costs one ORDER_STATUS_HARD_TIMEOUT_SEC wait per tick, not one per held item.
_order_lookup_timeout_at = {"t": 0.0}
ORDER_LOOKUP_COOLDOWN_SEC = 10.0


def _order_lookup_busy():
    """True while an order lookup is still hung or one timed out within
    ORDER_LOOKUP_COOLDOWN_SEC (the same test _order_known_at_broker skips on). Never raises."""
    try:
        prior = _order_lookup_inflight.get("future")
        if prior is not None and not prior.done():
            return True
        return (time.time() - float(_order_lookup_timeout_at.get("t") or 0.0)
                < ORDER_LOOKUP_COOLDOWN_SEC)
    except Exception:
        return False


def _order_known_at_broker(adapter, signal_id, log=print):
    """Webull's own verdict on ONE earlier CLOSE attempt, looked up by its client order
    id via adapter.order_status(signal_id), bounded to ORDER_STATUS_HARD_TIMEOUT_SEC on
    its own worker thread (the same precaution as _query_broker_fill -- this SDK's own
    timeouts are not reliably honoured on every call path).

    Why a lookup at all (EXIT SAFETY item 1 critical, 2026-09-26): a send that reached
    the adapter's send path but came back not ok with no definite 4xx (a timeout, a 5xx,
    a dropped connection after Webull already took the order) leaves believed_positions/
    broker_sent_positions untouched (see api.webull_orders.place_stock_order's own
    per-part try/except), so the adapter's own books cannot tell "never reached Webull"
    apart from "reached Webull, outcome unknown".

    Returns (FINAL CLOSE RE-SEND RULE -- see the table just above):
      {"verdict": "filled", "status": s}               -- the order filled;
      {"verdict": "working", "status": s}              -- a DOCUMENTED live status
          (_ORDER_LIVE_STATUSES); any other status is unverifiable (None);
      {"verdict": "dead", "status": s, "filled": n}    -- REJECTED/CANCELLED/FAILED
          with an EXPLICIT whole filled quantity n >= 0 (0 = nothing landed);
      None                                             -- unverifiable.
    A "not found"/404 answer is never read as "dead": a just-placed order may not be
    visible yet, and a 404 can be a routing error (SECOND 2026-09-26 review). Never
    raises."""
    if not signal_id:
        return None
    try:
        prior = _order_lookup_inflight.get("future")
        if prior is not None:
            if not prior.done():
                log(f"[qqq-exec] order lookup for {signal_id} skipped: an earlier lookup "
                    f"is still hung on the order-status worker -- unverifiable this step")
                return None
            _order_lookup_inflight["future"] = None
    except Exception:
        _order_lookup_inflight["future"] = None
    if time.time() - float(_order_lookup_timeout_at.get("t") or 0.0) < ORDER_LOOKUP_COOLDOWN_SEC:
        log(f"[qqq-exec] order lookup for {signal_id} skipped: a lookup timed out moments "
            f"ago -- unverifiable this step")
        return None
    try:
        fut = _order_status_executor.submit(adapter.order_status, signal_id, None)
    except Exception:
        return None
    try:
        result = fut.result(timeout=ORDER_STATUS_HARD_TIMEOUT_SEC)
    except concurrent.futures.TimeoutError:
        fut.cancel()   # drops it if the worker had not started it yet
        _order_lookup_timeout_at["t"] = time.time()
        if not fut.done():
            _order_lookup_inflight["future"] = fut
        return None
    except Exception:
        return None
    try:
        if not isinstance(result, dict) or not result.get("ok"):
            return None   # the lookup did not positively resolve -- unverifiable,
                          # regardless of whether the reason text says "not found"/404
        coid = result.get("client_order_id") or signal_id
        response = result.get("response")
        item = webull_orders._order_item(response, coid)
        item_coid = (webull_orders._field(item, "client_order_id", "clientOrderId")
                     if isinstance(item, dict) else None)
        if item_coid is not None and str(item_coid) != str(coid):
            return None   # the record is about some other order -- never judge ours by it
        fields = webull_orders.order_status_fields(response, coid)
        raw_status = fields.get("status")
        if not isinstance(raw_status, str):
            return None   # a numeric/garbage status (e.g. a fallback payload) -- unverifiable
        status = re.sub(r"[\s\-]+", "_", raw_status.strip().upper())
        if not status:
            return None
        if status == "FILLED":
            return {"verdict": "filled", "status": status}
        if status in _ORDER_DEAD_STATUSES:
            filled = _whole_qty(fields.get("filled_quantity"))
            if filled is None:
                return None   # dead, but how much landed first is not on the record
            return {"verdict": "dead", "status": status, "filled": filled}
        if status in _ORDER_LIVE_STATUSES:
            return {"verdict": "working", "status": status}
        log(f"[qqq-exec] order lookup for {signal_id}: unrecognised status {raw_status!r} "
            f"-- unverifiable, holding")
        return None
    except Exception:
        return None


def _order_known_at_broker_any(adapter, signal_ids, log=print):
    """Split (netted) CLOSE form of _order_known_at_broker: each unresolved part went
    out under its OWN client_order_id (api.webull_orders._part_client_order_id), never
    the base id, so each one is looked up directly (EXIT SAFETY item 2 major, SECOND
    2026-09-26 review).

    Returns {"verdict": v, "parts": {part_id: that part's own verdict dict}}, where v is
      "working" -- at least one part is still live at Webull (wait; never re-send);
      "filled"  -- every part filled;
      "dead"    -- no part live, at least one dead (the caller re-sends only what did
                   not fill, part by part);
    or None (unverifiable -- hold) as soon as ANY part's own lookup is unverifiable (the
    remaining parts are then not asked about this step), or when `signal_ids` is
    empty/None. Never raises."""
    try:
        ids = [s for s in (signal_ids or []) if s]
        if not ids:
            return None
        per = {}
        for sid in ids:
            v = _order_known_at_broker(adapter, sid, log=log)
            if not isinstance(v, dict) or v.get("verdict") not in ("filled", "working", "dead"):
                return None
            per[sid] = v
        verdicts = {v["verdict"] for v in per.values()}
        if "working" in verdicts:
            agg = "working"
        elif verdicts == {"filled"}:
            agg = "filled"
        else:
            agg = "dead"
        return {"verdict": agg, "parts": per}
    except Exception:
        return None


def _close_resend_sizes(item, verdict, believed=None):
    """(remaining, unacked_landed) for a queued CLOSE once Webull's own order record
    says the attempt under verification is over (verdict "filled" or "dead" -- see
    _order_known_at_broker / _order_known_at_broker_any), or (None, None) when a size it
    needs is missing (the caller then holds, never guesses).

    remaining -- how many shares of this close are still unsold:
      single order: min(verify_qty, believed) - (that size if FILLED else its filled
                    qty). `believed` is the adapter's own qty for the leg read at this
                    verify step plus OrderAdapter.booked_shares of the verified
                    attempt, i.e. the pre-attempt clamp (MAJOR, 2026-09-26) -- an item
                    queued before verify_qty was capped at queue time, or a legacy entry
                    with no verify_qty at all (falls back to item["shares"], the ASKED
                    size), can then never re-send shares that never went out;
      split order:  verify_qty - verify_landed_qty (parts Webull accepted outright)
                    - each unresolved part's landed shares (its whole qty if FILLED,
                      else its filled qty); a part refused with its own definite 4xx
                      landed nothing and is simply part of the remainder
      then clamped to item["shares"] (a re-send never exceeds what this close asked
      for) and floored at 0. The caller still clamps by the believed qty on top.
    unacked_landed -- the shares that filled on parts whose send came back NOT ok (the
      single order itself, or the unresolved parts of a split). The adapter never booked
      those (place_stock_order only moves its books for an accepted part), so the caller
      applies them to the adapter's books (minor, 2026-09-26 review). Never raises."""
    try:
        attempt = _whole_qty(item.get("verify_qty"))
        if attempt is None:
            attempt = _whole_qty(item.get("shares"))   # an item queued before these
                                                       # fields existed
        if attempt is None:
            return None, None
        part_ids = item.get("unresolved_part_ids")
        if part_ids:
            landed = _whole_qty(item.get("verify_landed_qty"))
            part_qty = item.get("unresolved_part_qty") or {}
            parts = (verdict or {}).get("parts") or {}
            if landed is None:
                return None, None
            unacked = 0
            for pid in part_ids:
                pv = parts.get(pid)
                if not isinstance(pv, dict):
                    return None, None
                if pv.get("verdict") == "filled":
                    q = _whole_qty(part_qty.get(pid))
                    if q is None:
                        return None, None
                    unacked += q
                elif pv.get("verdict") == "dead":
                    unacked += int(pv.get("filled") or 0)
                else:
                    return None, None
            landed += unacked
        else:
            held = _whole_qty(believed)
            if held is not None:
                attempt = min(attempt, held)
            v = (verdict or {}).get("verdict")
            if v == "filled":
                landed = attempt
            elif v == "dead":
                landed = int((verdict or {}).get("filled") or 0)
            else:
                return None, None
            unacked = landed
        remaining = attempt - landed
        cap = _whole_qty(item.get("shares"))
        if cap is not None:
            remaining = min(remaining, cap)
        return max(0, int(remaining)), max(0, int(unacked))
    except Exception:
        return None, None


def _close_resend_remainder(item, verdict, believed=None):
    """The `remaining` half of _close_resend_sizes (see there). Never raises."""
    return _close_resend_sizes(item, verdict, believed=believed)[0]


def _apply_unacked_close_fill(state, leg, qty, log=print, part_outcomes=None):
    """Books `qty` shares that filled at Webull on a CLOSE send that came back not ok
    onto the adapter's own sent/believed books for `leg` (OrderAdapter.apply_unacked_
    close_fill) -- minor, 2026-09-26 review: without this the adapter keeps believing
    the leg holds shares already sold, which can raise a false reconcile halt, block
    the leg's next entry, and offer phantom shares to a manually triggered
    FLATTEN_BROKER orphan repair (which would sell shares already sold).

    Skipped (never forced) while ANY broker send is still hung on the send worker: that
    send holds the adapter lock, and if it is THIS leg's ambiguous send it may yet
    return ok and book the same shares itself. When skipped or when the adapter cannot
    do it, logs, records a timeline event and pushes, saying the adapter's books are off
    by N shares until reconcile and that FLATTEN_BROKER must not be dropped for this leg
    until they are corrected. Never raises."""
    try:
        qty = int(qty or 0)
        if qty <= 0 and not part_outcomes:
            return
        applied = None
        why = "the adapter could not update its books"
        if _send_inflight_future() is not None:
            why = "a broker send is still in flight"
        else:
            fn = getattr(_get_broker_adapter(log=log), "apply_unacked_close_fill", None)
            if callable(fn):
                # Webull's verified answer per id sets those parts exactly (2026-09-26)
                applied = (fn(leg, qty, part_outcomes=part_outcomes)
                           if part_outcomes else fn(leg, qty))
        if isinstance(applied, dict):
            log(f"[qqq-exec] broker books for {leg}: booked {qty} share(s) that filled at "
                f"Webull on a not-ok CLOSE send (sent -{applied.get('sent')}, believed "
                f"-{applied.get('believed')})")
            return
        if qty <= 0:
            return
        msg = (f"QQQ BROKER: {leg}'s adapter books still count {qty} share(s) that already "
               f"sold at Webull ({why}) -- off until reconcile; do not use FLATTEN_BROKER "
               f"for {leg} until they are corrected")
        log(f"[qqq-exec] {msg}")
        _log_event(state, "broker", msg, log=log)
        # WEBULL PUSH PLAN 10-07, group D: the books and Webull disagree, orders still flow
        w = _leg_word(leg)
        _say(state, f"books:{leg}", _phone_day(), ntfy_push.plain(
            PHONE_AREA, "needs a fix", None,
            f"The book counts {qty} more {w} shares than Webull holds",
            PHONE_ASK + " - and do not use the Webull-only repair for " + w + " until it is fixed",
            priority="default"), log=log)
    except Exception as e:
        log(f"[qqq-exec] booking an unacked close fill failed (non-fatal): "
            f"{type(e).__name__}: {e}")


def _maybe_resend_broker_orders(state, cfg, nowdt, active, log=print):
    """Send ONE queued order (see _queue_broker_resend) per tick, when it is safe to.
    Never raises.
      * one per tick, oldest first, never in the tick right after its failure -- so a
        re-send cannot itself collide with another order;
      * an OPEN goes only while the book still holds that very trade (same trade id),
        at or before session.last_entry and within broker_open_resend_window_min of its
        first try (a late entry at a stale price is worse than none); one blocked by a
        halt also waits until the adapter is no longer halted (the halted re-check in
        _maybe_run_broker_reconcile looks every 30 s, so a false halt clears fast); at
        most BROKER_RESEND_MAX_TRIES re-sends, each under a fresh id;
      * a CLOSE queued as why="close_retry" (EXIT SAFETY item 2, 2026-09-26) goes
        whatever the book says, with backoff (_close_resend_backoff -- about 5, 10, 20,
        30s, then 30s), re-checked against the adapter's OWN believed position right
        before every attempt (never double-sell: if it already reads flat for this leg,
        the close has already reached Webull some other way -- drop the retry, no
        further send), until SESSION FLATTEN DEADLINE (_session_flatten_deadline --
        session close minus 10s), not bounded by BROKER_RESEND_MAX_TRIES, and given up
        on outright if it is left over from an earlier trading day (item["session_date"]
        -- EXIT SAFETY item 4 minor, 2026-09-26 review);
      * a close_retry whose previous attempt needs verifying (item["needs_verify"] --
        EXIT SAFETY item 2 major, 2026-09-26 review: only a send with no definite 4xx
        refusal does; see _queue_broker_resend) is checked against Webull's own order
        record (_order_known_at_broker / _order_known_at_broker_any, by order id --
        per unresolved part id for a split) at every backoff step, before ever
        re-sending. FINAL CLOSE RE-SEND RULE (2026-09-26 lead decision): FILLED -> drop,
        never re-send; still live at Webull -> keep waiting, never re-send; REJECTED/
        CANCELLED/FAILED with an explicit filled quantity -> re-send only the unfilled
        remainder (_close_resend_remainder), right away; anything unverifiable (lookup
        error, not found, missing filled quantity) -> hold. An ACCOUNT position read is
        NEVER used to release a re-send: one margin account nets every leg, so it cannot
        say which leg's shares are still out. Two or more unverifiable holds (a working answer
        in between does not reset the count)
        push urgently (the leg's own exit:<leg> phone episode -- the first failure was
        high, the stall is worse, so it goes out once; WEBULL PUSH PLAN 10-07) telling the
        owner to check Webull and sell by hand; the hold ends at the flatten deadline with
        the urgent give-up push, and the after-close Webull-flat check is the backstop.
    Giving up, or running out of window/market/deadline, logs an event and sends a phone
    alert."""
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
            close_retry = why == "close_retry"
            lot = (state.get("legs") or {}).get(leg)
            if intent == "OPEN" and (not lot or lot.get("trade_id") != item.get("trade_id")):
                q.pop(key, None)
                msg = (f"Re-send of the {leg} buy dropped: the book closed that trade before "
                       f"Webull could get it")
                log(f"[qqq-exec] {msg}")
                _log_event(state, "broker", msg, log=log)
                continue
            late = intent == "OPEN" and not close_retry and (
                (now - float(item.get("first_at") or now)) / 60.0 > window_min
                or _et_hhmm(nowdt) > _hhmm(sess.get("last_entry", "15:55")))
            deadline_passed = close_retry and nowdt >= _session_flatten_deadline(nowdt)
            # EXIT SAFETY item 4 minor (2026-09-26 review): a close_retry item left over
            # from an earlier trading day (the process was down from before the prior
            # day's deadline until after this morning's session start, so no tick ever
            # saw active=False or the deadline fire) must never run today -- it would
            # start pre-open (Webull refuses a market order then) and could keep going
            # into today's session. per-leg broker_sent_positions already caps the sell
            # itself so this was never a double-sell, just an unplanned stale exit.
            stale_day = close_retry and item.get("session_date") not in (
                None, nowdt.strftime("%Y-%m-%d"))
            give_up = (late or not active or deadline_passed or stale_day
                      or (not close_retry and tries >= BROKER_RESEND_MAX_TRIES))
            if give_up:
                q.pop(key, None)
                cause = ("its window passed" if late
                         else "it is from an earlier trading day" if stale_day
                         else "the session flatten deadline passed" if deadline_passed
                         else "the market window closed" if not active
                         else f"{tries} re-sends failed")
                why_txt = ("blocked by a reconcile halt" if why == "halt"
                          else "rejected by Webull as a duplicate" if why == "duplicate"
                          else "refused while an opposite order was still working"
                          if why == "box_order"
                          else "held back by the order gateway" if why == "busy"
                          else "not ok at the broker")
                msg = (f"QQQ BROKER: gave up re-sending the {leg} {what} ({cause}; first try "
                       f"{why_txt}). "
                       + (f"The book holds {leg} but Webull does not." if intent == "OPEN"
                          else f"Webull may still hold {leg}'s shares -- check and sell by hand."))
                log(f"[qqq-exec] {msg}")
                _log_event(state, "broker", msg, log=log)
                # WEBULL PUSH PLAN 10-07: a CLOSE give-up is group A at URGENT -- Webull may
                # still hold real shares with nobody retrying any more; an OPEN give-up folds
                # into the strategy's one "entry missed" note of the day (group B)
                if intent == "CLOSE":
                    # 10-08 review: the give-up runs through the leg's exit:<leg> episode
                    # FIRST -- after a same-day urgent "sell is stuck" for this trade it is
                    # the same fact and is held (one urgent, not two) -- and only THEN
                    # ends that episode, so this leg's NEXT CLOSE failure (a new trade,
                    # later the same day) pushes at once again instead of being held
                    # behind this give-up's urgent until its own give-up.
                    _say_exit_stuck(state, leg, f"The {_leg_word(leg)} sell gave up at "
                                    f"{_phone_clock(nowdt)} (still not sent)", log=log)
                    _close_fail_alert_reset(state, leg)
                else:
                    _say_entry_missed(state, leg, f"The {_leg_word(leg)} buy never reached "
                                      f"Webull (the re-sends gave up)",
                                      side=item.get("side"), log=log)
                continue
            if why == "halt" and _broker_halt_source(log=log) is not None:
                continue  # still halted -- the 30 s halted re-check clears a false one
            gap = _close_resend_backoff(tries) if close_retry else BROKER_RESEND_MIN_GAP_SEC
            if now - float(item.get("last_at") or 0) < gap:
                continue
            shares = (lot.get("shares_remaining") if intent == "OPEN" and why != "remainder"
                      else item.get("shares"))
            if why == "remainder":
                # SPLIT REMAINDER (2026-09-26): ONCE, capped at what the lot still lacks
                q.pop(key, None)
                held = _believed_qty_for_leg(leg, log=log, larger=True)   # never over-buy
                shares = min(int(shares or 0), int(round(float(lot.get("shares_remaining")
                                                               or 0))) - (held or 0))
                if held is None or shares <= 0:
                    msg = (f"QQQ BROKER: the rest of {leg}'s split entry not re-sent -- " + (
                        "Webull already holds what the lot needs" if held is not None else
                        f"the adapter's books could not be read; the book may hold more {leg}"))
                    log(f"[qqq-exec] {msg}")
                    _log_event(state, "broker", msg, log=log)
                    if held is None:
                        # group B: folds into the strategy's one "entry missed" note
                        _say_entry_missed(state, leg, f"The rest of the {_leg_word(leg)} buy "
                                          f"was not sent (the books could not be read)",
                                          side=item.get("side"), log=log)
                    continue
                _mirror_to_broker(state, leg=leg, side=item.get("side"), shares=shares,
                                  shadow_px=item.get("shadow_px"), intent=intent,
                                  ts=item.get("ts"), seq=item.get("seq") or 0,
                                  trade_id=item.get("trade_id"), resend=tries + 1,
                                  requeue=False, nowdt=nowdt, log=log, remainder=True)
                last = state.get("_broker_last") or {}
                ok = bool(last.get("ok")) and last.get("leg") == leg
                msg = (f"QQQ BROKER: the unsent {shares} of {leg}'s split entry "
                       + ("re-sent and accepted" if ok else
                          f"could not be sent either ({last.get('reason') or 'see the broker log'}) "
                          f"-- the book holds more {leg} than Webull; no further tries"))
                log(f"[qqq-exec] {msg}")
                _log_event(state, "broker", msg, log=log)
                if not ok:
                    # group B (folds into the "entry missed" note); re-sent OK is group E:
                    # timeline + log only
                    _say_entry_missed(state, leg, f"The rest of the {_leg_word(leg)} buy could "
                                      f"not be sent", side=item.get("side"), log=log)
                return  # ONE re-send per tick
            if close_retry:
                # NEVER DOUBLE-SELL (item 2): re-check the adapter's own believed
                # position right before this attempt -- if it already reads flat, some
                # other path (a prior try Webull actually accepted despite the record
                # we got back, the orphan repair, a manual sell) already closed it.
                believed = _believed_qty_for_leg(leg, log=log)
                if believed == 0:
                    q.pop(key, None)
                    _close_fail_alert_reset(state, leg)
                    msg = (f"Re-send of the {leg} sell dropped: Webull's own position "
                          f"already reads flat for {leg} -- no send")
                    # WEBULL PUSH PLAN 10-07, group E: the safe outcome -- log + timeline only
                    log(f"[qqq-exec] {msg}")
                    _log_event(state, "broker", msg, log=log)
                    continue
                if item.get("needs_verify"):
                    # EXIT SAFETY item 1 critical (2026-09-26), NARROWED item 2 major
                    # (2026-09-26 review): the PREVIOUS attempt's place_stock_order call
                    # actually reached the send path but came back not ok with no
                    # definite 4xx refusal (_queue_broker_resend already ruled that case
                    # out) -- a 5xx, a timeout, or a dropped connection after Webull may
                    # already have taken the order. That path never updates
                    # believed_positions/broker_sent_positions (see
                    # api.webull_orders.place_stock_order's own per-part try/except),
                    # so the believed-flat check just above cannot catch this case: it
                    # can still read the shares as held even though the order already
                    # landed at Webull. Ask Webull directly before ever re-sending
                    # blind under a fresh id.
                    #
                    # SPLIT ORDERS (item 2 major, SECOND 2026-09-26 review): a netted
                    # CLOSE's unresolved parts each went out under their OWN
                    # client_order_id, never the base id (see _queue_broker_resend's own
                    # note on `unresolved_part_ids`) -- verify each of THOSE when
                    # present, never the base last_signal_id, which a split order never
                    # actually sent to Webull.
                    part_ids = item.get("unresolved_part_ids")
                    prev_id = item.get("last_signal_id")
                    ids_desc = ", ".join(part_ids) if part_ids else prev_id
                    if part_ids:
                        known = _order_known_at_broker_any(_get_broker_adapter(log=log),
                                                           part_ids, log=log)
                    else:
                        known = _order_known_at_broker(_get_broker_adapter(log=log), prev_id,
                                                       log=log)
                    # FINAL CLOSE RE-SEND RULE (2026-09-26 lead decision, after four
                    # review rounds): only Webull's own record of THAT order decides --
                    # never an account position read (one margin account nets every
                    # leg, so no position read can say which leg's shares are still
                    # out, and a wrong guess is a double sell).
                    v = known.get("verdict") if isinstance(known, dict) else None
                    released = False
                    if v == "working":
                        # Webull holds the order and it is still live -- a re-send now
                        # would be a second sell on top of it. Wait, ask again next
                        # backoff step. Not an unverifiable hold: this is a known answer.
                        # verify_holds is deliberately NOT reset here (minor, 2026-09-26
                        # review): a lookup alternating working/unverifiable would
                        # otherwise never reach the 2-hold urgent page.
                        item["last_at"] = now
                        log(f"[qqq-exec] broker CLOSE re-send for {leg} waiting: the "
                            f"previous attempt ({ids_desc}) is still working at Webull "
                            f"-- no re-send while it is live")
                        continue
                    if v == "dead" and believed is None and not part_ids:
                        v = None   # cannot cap the remainder by what the adapter sent -- hold
                    if v in ("filled", "dead"):
                        # 2026-09-26: add back what the adapter already counts of this
                        # attempt, so `believed` is the pre-attempt qty (never twice)
                        ids = part_ids or [prev_id]
                        booked_fn = getattr(_get_broker_adapter(log=log), "booked_shares", None)
                        booked = booked_fn(ids) if callable(booked_fn) else 0
                        if believed is not None and type(booked) is int and booked > 0:
                            believed += booked
                        remaining, unacked = _close_resend_sizes(item, known,
                                                                 believed=believed)
                        extra = _whole_qty(item.get("pending_add")) or 0
                        if remaining is not None and extra:
                            # another dead order's unsold shares (_requeue_close_unfilled)
                            remaining += extra
                            item["pending_add"] = 0
                        if remaining is not None:
                            # books = what Webull says landed for the verified order(s)
                            _apply_unacked_close_fill(
                                state, leg, unacked, log=log,
                                part_outcomes=(known.get("parts") if part_ids
                                               else {prev_id: known}))
                            if believed is not None:
                                believed = max(0, believed - (unacked or 0))
                        if remaining is not None and remaining <= 0:
                            # everything this close asked for already landed
                            q.pop(key, None)
                            _close_fail_alert_reset(state, leg)
                            msg = (f"Re-send of the {leg} sell dropped: Webull's own "
                                  f"order record shows the previous attempt ({ids_desc}) "
                                  f"reached the book -- not re-sending to avoid a "
                                  f"double-sell; check Webull and the book by hand")
                            log(f"[qqq-exec] {msg}")
                            _log_event(state, "broker", msg, log=log)
                            # WEBULL PUSH PLAN 10-07, group D (orders still flow)
                            _say(state, f"resend_landed:{leg}", _phone_day(nowdt),
                                 ntfy_push.plain(
                                     PHONE_AREA, "needs a fix", None,
                                     f"{_a_leg_word(leg)} sell re-send was dropped: Webull "
                                     f"shows the earlier try landed",
                                     f"check the board and Webull agree on {_leg_word(leg)}, "
                                     f"or {PHONE_ASK}", priority="default"), log=log)
                            continue
                        if remaining is not None:
                            # the attempt is DEAD at Webull (REJECTED/CANCELLED/FAILED
                            # with an explicit filled quantity) -- re-send only what did
                            # not fill, now. The attempt under verification is resolved:
                            # clear it so a not-sent requeue of THIS re-send (e.g. an
                            # in-flight block) never carries it forward and re-subtracts
                            # its fills from the already-reduced size.
                            log(f"[qqq-exec] broker CLOSE for {leg}: Webull's own order "
                                f"record shows the previous attempt ({ids_desc}) is {v} "
                                f"-- re-sending the unsold {remaining}")
                            item["shares"] = remaining
                            item["needs_verify"] = False
                            item["unresolved_part_ids"] = None
                            item["unresolved_part_qty"] = None
                            item["verify_qty"] = remaining
                            item["verify_landed_qty"] = 0
                            item["verify_holds"] = 0
                            shares = remaining
                            released = True
                    if not released:
                        # UNVERIFIABLE (lookup error/timeout, not found/404, no status,
                        # a dead status with no readable filled quantity, or a size
                        # needed for the remainder missing) -- hold, bump last_at so the
                        # same backoff gap applies, ask again next time it is due.
                        holds = int(item.get("verify_holds") or 0) + 1
                        item["verify_holds"] = holds
                        item["last_at"] = now
                        log(f"[qqq-exec] broker CLOSE re-send for {leg} held ({holds}x): "
                            f"could not verify whether the previous attempt ({ids_desc}) "
                            f"reached Webull -- will check again")
                        if holds >= 2:
                            # 2+ unverifiable holds: the order lookup itself is not
                            # answering (an outage, not a blip). Push urgently in the
                            # leg's own exit:<leg> episode (WEBULL PUSH PLAN 10-07: worse
                            # than the first failure, so once; never a second independent
                            # stream -- THIRD/FOURTH 2026-09-26 reviews). The item stays
                            # held until the flatten deadline gives up with its own urgent
                            # push; the after-close Webull-flat check reads the real
                            # position.
                            stall_msg = (f"CLOSE retry for {leg} stalled: cannot "
                                        f"verify the previous attempt -- check Webull")
                            action, _sent = _say_exit_stuck(
                                state, leg, f"The {_leg_word(leg)} sell is stuck: Webull "
                                f"cannot confirm the last try", log=log)
                            if action == "push":
                                _log_event(state, "broker", stall_msg, log=log)
                        continue
                if believed is not None and shares is not None:
                    shares = int(min(float(shares), float(believed)))
            log(f"[qqq-exec] broker RE-SEND {intent} for {leg} (re-send {tries + 1}"
                + (f" of {BROKER_RESEND_MAX_TRIES}" if not close_retry else "")
                + f"; first try {why})")
            _mirror_to_broker(state, leg=leg, side=item.get("side"), shares=shares,
                              shadow_px=item.get("shadow_px"), intent=intent,
                              ts=item.get("ts"), seq=item.get("seq") or 0,
                              trade_id=item.get("trade_id"), resend=tries + 1,
                              nowdt=nowdt, log=log)
            last = state.get("_broker_last") or {}
            if last.get("ok") and last.get("leg") == leg and last.get("closed_by_resting"):
                # RESTING ORB STOP: nothing was re-sent -- the resting order had already
                # closed the leg at Webull (_mirror_to_broker logged and put it on the
                # timeline); no "re-sent and accepted" push for an order never sent
                pass
            elif last.get("ok") and last.get("leg") == leg:
                msg = (f"QQQ BROKER: {leg} {what} re-sent and accepted ("
                       + ("after the reconcile halt cleared" if why == "halt"
                          else "after a same-instant duplicate" if why == "duplicate"
                          else "after the opposite order finished" if why == "box_order"
                          else "after the order gateway held it back" if why == "busy"
                          else "after a retry") + ")")
                # WEBULL PUSH PLAN 10-07, group E (fixed itself): log + timeline only
                log(f"[qqq-exec] {msg}")
                _log_event(state, "broker", msg, log=log)
            elif close_retry and key in q and int(q[key].get("tries") or 0) == tries + 1:
                # still not ok -- stays queued (see _queue_broker_resend); the per-record
                # "NOT ok" alert from _mirror_to_broker's own call above already paged
                pass
            elif key in q and int(q[key].get("tries") or 0) == tries:
                # failed for a reason that is not worth another try (kill file, rails,
                # nothing held at Webull) -- _mirror_to_broker already logged why
                q.pop(key, None)
                if intent == "CLOSE":
                    # the retry queue is done with this sell: end its phone episode, so a
                    # later trade's first CLOSE failure on this leg today pushes at once
                    # (10-08 fourth review)
                    _close_fail_alert_reset(state, leg)
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
                               parts=None, log=print, retry=None, side=None):
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
        if side is not None:
            job["side"] = side     # for the phone note's "buy" / "short sale" (10-08 review)
        if parts and len(parts) > 1:
            job["parts"] = [
                {"client_order_id": p.get("client_order_id"), "qty": p.get("qty"),
                 "resolved": False, "price": None, "tries": 0, "last_at": 0.0,
                 "last_note": None}
                for p in parts if p.get("client_order_id")
            ]
        if retry:
            job["retry"] = retry   # a CLOSE's trade, see _requeue_close_unfilled
            # kept past this job's give-up: reconcile's PENDING pass may settle a part
            # later (_push_pending_changes), keyed by every order id of this send
            ctxs = state.setdefault("_broker_close_ctx", {})
            for k in [k for k, v in ctxs.items() if now - float(v.get("at") or 0) > 86400]:
                ctxs.pop(k, None)
            for oid in [signal_id] + [p.get("client_order_id") for p in job.get("parts") or []]:
                if oid:
                    ctxs[webull_orders._sanitize_client_order_id(oid)] = {
                        "leg": leg, "shadow_px": shadow_px, "retry": retry, "at": now}
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
        # RESTING ORB STOP (2026-09-29 review): a resting fill row shares its trade's CLOSE
        # signal id (qx<tid>C) but is written complete by _book_resting_fills and never
        # has a capture of its own -- a later market close's capture must land on ITS
        # row, never overwrite Webull's stop/target price on the resting one
        if row.get("signal_id") == signal_id and not _is_resting_fill_row(row):
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


def _requeue_close_unfilled(state, item, order_id, unsold, nowdt=None, log=print):
    """ACK IS NOT A FILL, CLOSE side (2026-09-26): an acked CLOSE Webull later killed
    left `unsold` shares; queue them through close_retry (grown onto this trade's item --
    held as its pending_add while it verifies another attempt -- or a new one), unless a
    queued item is already verifying `order_id`. True when
    queued. Never raises."""
    try:
        ctx = (item or {}).get("retry") or {}
        leg, trade_id, unsold = item.get("leg"), ctx.get("trade_id"), int(unsold or 0)
        if unsold <= 0 or not trade_id:
            return False
        q = state.setdefault("_broker_resend", {})
        existing = next((e for k, e in q.items() if e.get("leg") == leg
                         and e.get("intent") == "CLOSE" and e.get("trade_id") == trade_id), None)
        if existing is not None:
            ids = list(existing.get("unresolved_part_ids") or []) + [existing.get("last_signal_id")]
            if existing.get("needs_verify") and order_id in [
                    webull_orders._sanitize_client_order_id(i) for i in ids if i]:
                return False
            if existing.get("needs_verify"):
                # verifying ANOTHER attempt: never grow that attempt's size (a "filled"
                # verdict would then drop the item with these shares unsold) -- they
                # are added once the verify resolves (see "pending_add")
                existing["pending_add"] = int(existing.get("pending_add") or 0) + unsold
                return True
            existing["shares"] = int(existing.get("shares") or 0) + unsold
            if _whole_qty(existing.get("verify_qty")) is not None:
                existing["verify_qty"] = int(existing["verify_qty"]) + unsold
            return True
        now = time.time()
        q[f"{leg}:CLOSE:{trade_id}"] = {
            "leg": leg, "intent": "CLOSE", "side": ctx.get("side"), "shares": unsold,
            "shadow_px": item.get("shadow_px"), "ts": ctx.get("ts"), "seq": ctx.get("seq") or 0,
            "trade_id": trade_id, "why": "close_retry", "tries": int(ctx.get("resend") or 0),
            "first_at": now, "last_at": now,
            "session_date": (nowdt or _now_et()).strftime("%Y-%m-%d"),
            "sent": False, "needs_verify": False, "last_signal_id": None,
            "unresolved_part_ids": None, "verify_qty": unsold,
            "unresolved_part_qty": None, "verify_landed_qty": 0}
        return True
    except Exception as e:
        log(f"[qqq-exec] close re-queue after a dead order failed (non-fatal): "
            f"{type(e).__name__}: {e}")
        return False


def _push_fill_outcome(state, item, order_id, outcome, log=print, nowdt=None):
    """ACK IS NOT A FILL (2026-09-26): one high push when fill capture moved the books
    for an acked order that did not fully fill; a CLOSE's unsold shares are re-queued
    first. apply_order_outcome reports a change once, so never twice. Never raises."""
    try:
        if not outcome or outcome.get("status") in (None, "FILLED"):
            return
        unsold = -int(outcome.get("change") or 0)
        requeued = (item.get("intent") == "CLOSE" and unsold > 0 and _requeue_close_unfilled(
            state, item, webull_orders._sanitize_client_order_id(order_id), unsold,
            nowdt=nowdt, log=log))
        msg = (f"QQQ BROKER {item.get('intent')} {item.get('leg')}: Webull reports "
               f"{outcome['status']} for order {order_id} -- {outcome.get('filled')} of "
               f"{outcome.get('qty')} share(s) filled; the adapter's books now count only "
               f"the filled shares"
               + (f"; re-sending the unsold {unsold}" if requeued else ""))
        _log_event(state, "broker", msg, log=log)
        _say_order_outcome(state, item.get("leg"), item.get("intent"),
                           item.get("side") or ((item.get("retry") or {}).get("side")),
                           outcome.get("status"), _whole_qty(outcome.get("filled")) or 0,
                           unsold, requeued, bool((item.get("retry") or {}).get("trade_id")),
                           nowdt=nowdt, log=log,
                           book_holds=(item.get("intent") != "OPEN" or _book_holds_open(
                               state, item.get("leg"), item.get("signal_id") or order_id)))
    except Exception as e:
        log(f"[qqq-exec] fill-outcome push failed (non-fatal): {type(e).__name__}: {e}")


def _phone_dead_verb(status):
    """Webull's dead status as the verb the phone uses: 'rejected' / 'cancelled' / 'did not
    fill'."""
    s = str(status or "").upper()
    if s == "REJECTED":
        return "rejected"
    if s in ("CANCELLED", "CANCELED"):
        return "cancelled"
    return "did not fill"


def _book_holds_open(state, leg, order_id):
    """True when state["legs"][leg] is the trade whose OPEN went out as `order_id` (the
    signal id, a netting part id or a seq'd re-send of it). A lot with no trade id, or no
    order id to match, counts as held (the old wording). Never raises."""
    try:
        lot = (state.get("legs") or {}).get(leg)
        if not lot:
            return False
        tid, oid = lot.get("trade_id"), str(order_id or "")
        if not tid or not oid:
            return True
        base = webull_orders._sanitize_client_order_id(
            _broker_signal_id(leg, None, "OPEN", trade_id=tid))
        if base.startswith("sig"):
            return True    # a hashed id (too long) has no prefix to match: the old wording
        core = re.sub(r"-\d+$", "", webull_orders._sanitize_client_order_id(oid))
        return bool(core) and (core.startswith(base) or base.startswith(core))
    except Exception:
        return True


def _say_order_outcome(state, leg, intent, side, status, filled, unsold, requeued,
                       has_trade, nowdt=None, log=print, book_holds=True):
    """The phone note for an order Webull ACCEPTED and later killed or only part-filled
    (fill capture, plan groups A / B -- 10-08 review). The strategy's trade did not (fully)
    happen at Webull, so trading IS affected:
      OPEN   group B, high, the strategy's one "entry missed" note of the day: "Webull
             rejected the ORB buy" / "Webull filled only 4 shares of the ORB buy".
      CLOSE  group A: unsold shares re-sent (or already being re-sent) -> the first-failure
             high "sell is late"; unsold shares nothing re-sends (no trade to retry) ->
             urgent "sell by hand".
    Anything else (a close with nothing unsold, or an OPEN whose trade the book no longer
    holds -- `book_holds` False, 10-08 review: "the book still counts the trade" would be
    wrong) is group D, default. Never raises."""
    try:
        w = _leg_word(leg)
        verb = _phone_dead_verb(status)
        if intent == "OPEN" and not book_holds:
            what = (f"Webull filled only {filled} shares of the {w} {_open_word(side)}"
                    if filled > 0 else f"Webull {verb} the {w} {_open_word(side)}")
            return _say(state, f"part_fill:{leg}", _phone_day(nowdt), ntfy_push.plain(
                PHONE_AREA, "needs a fix", None,
                f"{what} after the book closed that trade; the books now match Webull",
                PHONE_ASK, priority="default"), log=log)
        if intent == "OPEN":
            act = _open_word(side)
            if filled > 0:
                return _say_entry_missed(
                    state, leg, f"Webull filled only {filled} shares of the {w} {act}",
                    side=side, log=log, trading=f"only part of the {w} {act} is at Webull")
            return _say_entry_missed(state, leg, f"Webull {verb} the {w} {act}", side=side,
                                     log=log)
        act = _close_word(side)
        if unsold > 0:
            what = (f"Webull {verb} the {w} {act}" if filled <= 0
                    else f"Webull did not fill {unsold} shares of the {w} {act}")
            if requeued or has_trade:
                rest = (("it is re-sent" if filled <= 0 else "they are re-sent") if requeued
                        else "the queued re-send is checking it")
                return _say_exit_late(state, leg, verb, side=side, log=log,
                                      problem=f"{what}; {rest}")
            return _say_exit_stuck(state, leg, f"{what} and nothing re-sends them", log=log)
        return _say(state, f"part_fill:{leg}", _phone_day(nowdt), ntfy_push.plain(
            PHONE_AREA, "needs a fix", None,
            f"Webull's answer on the {w} {act} changed the books; they now match Webull",
            PHONE_ASK, priority="default"), log=log)
    except Exception as e:
        log(f"[qqq-exec] order-outcome note failed (non-fatal): {type(e).__name__}: {e}")
        return None, False


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
                if age > BROKER_FILL_CAPTURE_MAX_AGE_SEC and not any(
                        p.get("working") and not p.get("resolved") for p in parts):
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
                outcome = {}
                px, note = _query_broker_fill(adapter, target["client_order_id"],
                                              account_id=item.get("account_id"), log=log,
                                              outcome=outcome)
                _push_fill_outcome(state, item, target["client_order_id"], outcome, log=log,
                                   nowdt=nowdt)
                if px is not None:
                    target["resolved"] = True
                    target["price"] = px
                elif outcome.get("final"):
                    target["resolved"] = True   # dead at Webull: no price will ever come
                    target["last_note"] = f"{outcome.get('status')} at Webull"
                else:
                    target["working"] = outcome.get("working", target.get("working"))
                    target["last_note"] = note
                    log(f"[qqq-exec] fill-capture retry {target['tries']} for {item.get('leg')} "
                        f"{item.get('intent')} part {target['client_order_id']}: {note}")
                if all(p.get("resolved") for p in parts):
                    q.pop(key, None)
                    _finish_fill_capture_parts(item, log=log)
                return  # ONE order_status() SDK call per tick
            # -- ordinary, single-order job: unchanged from before ORDER NETTING --
            # (except: a job Webull last reported still working never ages out)
            if age > BROKER_FILL_CAPTURE_MAX_AGE_SEC and not item.get("working"):
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
            outcome = {}
            px, note = _query_broker_fill(adapter, item.get("signal_id"),
                                          account_id=item.get("account_id"), log=log,
                                          outcome=outcome)
            _push_fill_outcome(state, item, item.get("signal_id"), outcome, log=log,
                               nowdt=nowdt)
            if px is not None:
                q.pop(key, None)
                _finish_fill_capture(item, px, None, log=log)
            elif outcome.get("final"):
                q.pop(key, None)   # dead at Webull: no price will ever come
                _finish_fill_capture(item, None, f"{outcome.get('status')} at Webull", log=log)
            else:
                item["working"] = outcome.get("working", item.get("working"))
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
def _broker_realized_today(today, log=print, held_seeds=None):
    """(realized_total, any_broker_priced) from today's BROKER_ORDERS_CSV rows for
    mode PAPER/LIVE with ok truthy -- FIFO pairs each leg's OPEN with its next CLOSE
    using the row's own broker_fill_px (the documented `filled_price`, see
    api.webull_orders.order_status_fields()/1ed627e) when present, falling back to
    shadow_px for that one row when the broker didn't echo a fill price back yet.
    `any_broker_priced` is True only if at least one row actually had a real
    broker_fill_px -- see _compute_broker_daily_pnl for why that distinction decides
    the reported source. Never raises; a CSV read problem returns (0.0, False).

    `held_seeds` (HOLD OVERNIGHT, 2026-10-09): {leg: {"px", "side", "shares"}} for each lot
    carried into today -- its OPEN row is an earlier day's, so the pairing starts from its
    open mark (today's first price) instead: its CLOSE today counts exit - open mark, the
    daily loss limit's mark-to-open (the overnight gap stays out). "at_fill": True (the lot
    closed before today's first bar was in, so its exit was today's first price) pairs that
    first CLOSE at its own price -- nothing on the rail."""
    realized = 0.0
    any_broker_priced = False
    open_px_by_leg = {leg: dict(v) for leg, v in (held_seeds or {}).items()
                      if isinstance(v, dict) and v.get("px") is not None}
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
            if opened.pop("at_fill", False):
                opened["px"] = px     # HOLD OVERNIGHT: the held lot's first price today
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
    # HOLD OVERNIGHT: the rail's marks -- mark-to-open for a lot carried into today, the
    # record mark for every other lot (a state from before they existed: the record marks)
    rail_marks = state.get("_rail_unrl_by_leg")
    if not isinstance(rail_marks, dict):
        rail_marks = state.get("_unrl_by_leg") or {}
    try:
        today = _now_et().strftime("%Y-%m-%d")
        ht = state.get("held_today")
        seeds = {}
        if isinstance(ht, dict) and ht.get("day") == today:
            for leg, v in (ht.get("legs") or {}).items():
                if (v or {}).get("open_mark_px") is not None:
                    seeds[leg] = {"px": float(v["open_mark_px"]),
                                  "side": _broker_side(v.get("side"), "OPEN"),
                                  "shares": float(v.get("shares") or 0),
                                  # closed before today's first bar: its fill IS today's
                                  # first price, so it adds nothing to the rail
                                  "at_fill": v.get("open_mark_src") == "exit"}
        realized, any_broker_priced = _broker_realized_today(today, log=log, held_seeds=seeds)
        if any_broker_priced:
            open_legs = adapter.status().get("open_legs") or []
            unrealized = sum(float(rail_marks.get(leg, 0.0) or 0.0) for leg in open_legs)
            return round(realized + unrealized, 2), "broker_fills"
    except Exception as e:
        log(f"[qqq-exec] broker-fill P&L calc failed ({type(e).__name__}: {e}) -- "
            "falling back to the shadow book's own today figures")
    shadow_realized = _rail_realized_today(state)
    shadow_unrealized = sum(float(v or 0.0) for v in rail_marks.values())
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
    the background after this function gives up waiting on it.

    2026-09-26: while an order lookup is hung or timed out within ORDER_LOOKUP_COOLDOWN_SEC,
    reconcile() skips its PENDING pass (resolve_pending=False) -- that lookup runs before
    the positions read, inside this same 12 s budget. RESTING ORB STOP (2026-09-29 second
    review): the same while a resting call to Webull is hung or just timed out
    (_resting_busy) -- its lookups would hang the reconcile into a false read-failure halt;
    reconcile() then reads a difference a live resting order's fill would explain as
    "undecided" instead of a mismatch."""
    skip = _order_lookup_busy() or _resting_busy()
    fut = (_reconcile_executor.submit(adapter.reconcile, resolve_pending=False)
           if skip else _reconcile_executor.submit(adapter.reconcile))
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


def _push_pending_changes(state, adapter, log=print, nowdt=None):
    """One high push per book change reconcile()'s PENDING pass made (take_part_events):
    the books then match Webull, so nothing else would page. A dead CLOSE's unsold
    shares (Webull's explicit dead record with a filled qty) are re-queued through
    close_retry like fill capture does, unless a queued close re-send already verifies
    that order; with no trade context the push says to sell by hand. Never raises."""
    try:
        take = getattr(adapter, "take_part_events", None)
        events = take(lock_timeout=0.2) if callable(take) else []
        for ev in events if isinstance(events, list) else []:
            leg = ev.get("leg")
            msg = (f"QQQ BROKER {ev.get('intent')} {leg}: Webull's record of order "
                   f"{ev.get('client_order_id')} (outcome was not known) came back "
                   f"{ev.get('status')} -- the adapter's books now count {ev.get('booked')} "
                   f"of {ev.get('qty')} share(s)")
            sell_by_hand = 0
            unsold = -int(ev.get("change") or 0)
            if (ev.get("intent") == "CLOSE" and unsold > 0
                    and ev.get("status") in webull_orders.DEAD_STATUSES):
                oid = webull_orders._sanitize_client_order_id(ev.get("client_order_id"))
                verifying = any(
                    e.get("leg") == leg and e.get("intent") == "CLOSE" and e.get("needs_verify")
                    and oid in [webull_orders._sanitize_client_order_id(i) for i in
                                list(e.get("unresolved_part_ids") or [])
                                + [e.get("last_signal_id")] if i]
                    for e in (state.get("_broker_resend") or {}).values())
                ctx = (state.get("_broker_close_ctx") or {}).get(oid)
                if verifying:
                    msg += "; the queued close re-send is verifying it"
                elif ctx and _requeue_close_unfilled(state, ctx, oid, unsold, nowdt=nowdt,
                                                     log=log):
                    msg += f"; re-sending the unsold {unsold}"
                else:
                    msg += (f"; Webull still holds {unsold} {leg} share(s) -- sell them "
                            f"by hand")
                    sell_by_hand = unsold
            orphan_buy = (ev.get("intent") == "OPEN" and int(ev.get("booked") or 0) > 0
                          and not (state.get("legs") or {}).get(leg))
            if orphan_buy:
                msg += (f"; the book holds no {leg}, so Webull may hold shares the book "
                        f"does not -- check Webull")
            _log_event(state, "broker", msg, log=log)
            # WEBULL PUSH PLAN 10-07, group D: the books now match Webull (default); HIGH only
            # when the text says "sell by hand" (no trade context to re-send the rest).
            # 10-08 review: a dead CLOSE whose unsold shares are re-sent is group A (the
            # sell is late, high); a dead / part-filled OPEN the book still holds is group B
            # (the strategy's one "entry missed" note, high); an unclear buy that landed
            # after the book closed that trade leaves shares nobody will sell (high).
            w = _leg_word(leg)
            act = "buy" if ev.get("intent") == "OPEN" else "sell"
            status_w = str(ev.get("status") or "with an answer").replace("_", " ").lower()
            dead = ev.get("status") in webull_orders.DEAD_STATUSES
            lot = (state.get("legs") or {}).get(leg) or {}
            if ev.get("intent") == "CLOSE" and dead and unsold > 0 and not sell_by_hand:
                booked = _whole_qty(ev.get("booked")) or 0
                _say_order_outcome(state, leg, "CLOSE", lot.get("side"), ev.get("status"),
                                   booked, unsold, not verifying, True, nowdt=nowdt, log=log)
                continue
            booked = _whole_qty(ev.get("booked"))
            qty = _whole_qty(ev.get("qty"))
            if (ev.get("intent") == "OPEN" and lot and dead and booked is not None
                    and qty is not None and booked < qty):
                _say_order_outcome(state, leg, "OPEN", lot.get("side"), ev.get("status"),
                                   booked, 0, False, False, nowdt=nowdt, log=log,
                                   book_holds=_book_holds_open(state, leg,
                                                               ev.get("client_order_id")))
                continue
            if sell_by_hand:
                note = ntfy_push.plain(
                    PHONE_AREA, "CHECK NOW", f"Webull still holds {w} shares nobody will sell",
                    f"Webull still holds {sell_by_hand} {w} shares after an unclear sell",
                    "sell them by hand in the Webull app", priority="high")
            elif orphan_buy:
                note = ntfy_push.plain(
                    PHONE_AREA, "CHECK NOW", f"Webull may hold {w} shares the book does not",
                    f"An unclear {w} buy landed at Webull after the book closed that trade",
                    f"check the Webull app and sell any {w} shares the book does not hold "
                    f"by hand, or {PHONE_ASK}", priority="high")
            else:
                note = ntfy_push.plain(
                    PHONE_AREA, "needs a fix", None,
                    f"An unclear {w} {act} order came back {status_w}; the books now match "
                    f"Webull", PHONE_ASK, priority="default")
            # 10-08 review: a "sell by hand" is a distinct fact per order (each one is real
            # shares nobody will sell) -- its own id, so a second order's unsold shares the
            # same day are not held behind the first (its own slot, so the default notes
            # keep their once-a-day slot unclear:<leg>)
            if sell_by_hand or orphan_buy:
                _say(state, f"unclear_hand:{leg}",
                     f"{_phone_day(nowdt)} {ev.get('client_order_id')}", note, log=log)
            else:
                _say(state, f"unclear:{leg}", _phone_day(nowdt), note, log=log)
    except Exception as e:
        log(f"[qqq-exec] pending-order push failed (non-fatal): {type(e).__name__}: {e}")


# WEBULL PUSH PLAN 10-07, group C ("orders on hold"): high, ONE note per hold EPISODE. Each
# cause of a hold is its own problem (its own dedupe slot, hold:<cause>), so a hold that
# starts later the same day for a DIFFERENT reason -- above all one that blocks the close --
# still pushes even after an earlier, unrelated hold:
#   hold:reconcile          the book and Webull disagree / Webull unreadable (new entries
#                           wait); id = the ET date. The episode ends only after
#                           RECONCILE_HOLD_CLEAR_OKS agreeing reconciles in a row (the halt
#                           lifts at the first; the next look is the 5-minute periodic one),
#                           so a reconcile that flaps in and out of MISMATCH pages once, while
#                           a separate hold later the same day pages again (10-08 review)
#   hold:resting_hang       a resting call to Webull that does not answer (EVERY order waits,
#                           the close included); id = the hung call, one note per hung call
#   hold:resting_undecided  a resting stop Webull no longer lists and nobody can settle
#                           (every order waits); id = that order
#   hold:boot               unknown orders cancelled at start-up (no state.json yet: process
#                           memory); id = the ET date
HOLD_KEY = "hold"            # the prefix; hold_key(cause) is the slot


def hold_key(cause):
    return f"{HOLD_KEY}:{cause}"


def _say_hold(state, trading, problem, action, cause="reconcile", problem_id=None,
              log=print):
    return _say(state, hold_key(cause), problem_id or _phone_day(), ntfy_push.plain(
        PHONE_AREA, "orders on hold", trading, problem, action, priority="high"), log=log)


RECONCILE_HOLD_CLEAR_OKS = 2   # agreeing reconciles in a row that end hold:reconcile
# 10-08 review: the episode ending after RECONCILE_HOLD_CLEAR_OKS agreeing looks let a reconcile
# that flaps all day push once per flap. The plan's "at most once a day": a hold CAUSE whose
# note already went out this New York day stays quiet (log + timeline only) for the rest of
# that day, even after its episode ended. state["_hold_pushed_day"] = {cause: "YYYY-MM-DD"},
# saved with state.json. Only the reconcile hold is capped: a hung resting call or an
# undecided resting stop blocks every order, the close included, and keeps one note per call
# / per order.
HOLD_DAILY_CAP_CAUSES = ("reconcile",)


def _hold_ny_day():
    """Today's New York date from time.time() (the clock tests move)."""
    try:
        return datetime.fromtimestamp(time.time(), _NY or timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return _phone_day()


def _say_hold_capped(state, trading, problem, action, cause="reconcile", log=print):
    """_say_hold, at most once per `cause` per New York day (HOLD_DAILY_CAP_CAUSES). A push
    whose send failed (False) does not count. Never raises."""
    try:
        day = _hold_ny_day()
        pushed = state.setdefault("_hold_pushed_day", {}) if isinstance(state, dict) else {}
        if cause in HOLD_DAILY_CAP_CAUSES and pushed.get(cause) == day:
            log(f"[qqq-exec] orders-on-hold note ({cause}) already pushed today -- held")
            return None, None
        action_, sent = _say_hold(state, trading, problem, action, cause=cause,
                                  problem_id=day, log=log)
        if action_ == "push" and sent is not False:
            pushed[cause] = day
        return action_, sent
    except Exception as e:
        log(f"[qqq-exec] orders-on-hold note failed ({type(e).__name__}: {e})")
        return None, False


def _note_reconcile_agreed(state, log=print):
    """A reconcile agreed: count it, and once RECONCILE_HOLD_CLEAR_OKS have agreed in a row
    end the open hold:reconcile episode quietly (no push), so the next, separate hold pushes
    again even the same day (plan group C, "one note per hold episode"). Never raises."""
    try:
        n = int(state.get("_reconcile_ok_streak") or 0) + 1
        state["_reconcile_ok_streak"] = n
        key = hold_key("reconcile")
        if n >= RECONCILE_HOLD_CLEAR_OKS and key in (state.get("_phone_dedupe") or {}):
            _say_clear(state, key, log=log)
            log(f"[qqq-exec] broker reconcile agreed {n} times in a row -- the orders-on-hold "
                f"episode is over; a new hold pushes again")
    except Exception as e:
        log(f"[qqq-exec] reconcile-agreed bookkeeping failed (non-fatal): "
            f"{type(e).__name__}: {e}")


def _maybe_notify_reconcile_halt(state, kind, reason, log=print):
    """Phone push for a broker reconcile MISMATCH or READ FAILURE (item 2, 2026-09-26,
    "alerts in book") -- called from _maybe_run_broker_reconcile's own failure branch,
    right after its log line and timeline event. WEBULL PUSH PLAN 10-07, group C: one
    "orders on hold" note per hold episode for this cause (hold:reconcile, see HOLD_KEY;
    the episode ends in _note_reconcile_agreed) -- this function is re-entered every 30 s
    while halted, and the repeat rule holds every one of those; a different hold (a hung
    resting call) keeps its own note. The reason stays
    in the log line and the timeline event. Never raises."""
    try:
        problem = ("Webull's QQQ position could not be read, so new QQQ entries wait"
                   if kind == "READ FAILURE" else
                   "The book and Webull disagree on QQQ shares, so new QQQ entries wait")
        _say_hold_capped(state, "new QQQ entries wait until the book and Webull agree",
                         problem, "nothing yet - it checks again every 30 seconds; " + PHONE_ASK
                         + " if it lasts", log=log)
    except Exception as e:
        log(f"[qqq-exec] reconcile-halt alert failed (non-fatal): {type(e).__name__}: {e}")


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
    _push_pending_changes(state, adapter, log=log, nowdt=nowdt)
    if result.get("undecided"):
        # RESTING ORB STOP (2026-09-29 second review): the difference is what a live resting
        # order's own fill would make, and that order had no clear lookup this pass -- it is
        # looked up first (the adapter marked it due), and the check runs again after the
        # post-order grace; no halt, no push. The adapter halts after a few in a row.
        log(f"[qqq-exec] broker reconcile UNDECIDED ({why}): {result.get('reason')} -- the "
            f"resting order is looked up first, then checked again")
        state["_reconcile_due"] = True
        state["_last_broker_send_at"] = time.time()
        return
    if result.get("ok"):
        log(f"[qqq-exec] broker reconcile OK ({why})")
        _note_reconcile_agreed(state, log=log)
    else:
        state["_reconcile_ok_streak"] = 0
        reason = result.get("error") or result.get("mismatches")
        kind = "READ FAILURE" if result.get("error") else "MISMATCH"
        log(f"[qqq-exec] BROKER RECONCILE {kind} ({why}) -- new broker entries "
            f"halted: {reason}")
        _log_event(state, "broker_reconcile_halt",
                  f"Broker reconcile {kind.lower()} -- new broker entries halted: {reason}",
                  log=log)
        # item 2 (2026-09-26, "alerts in book"): a reconcile that cannot confirm the
        # book and Webull agree is exactly the "may be silently wrong" case a phone
        # push exists for, but while it is halted this same function is re-entered
        # every broker_reconcile_halted_recheck_sec (30s, see the "halted re-check"
        # branch above) -- pushing every one of those would page every 30s all day.
        _maybe_notify_reconcile_halt(state, kind, reason, log=log)


def _run_broker_housekeeping(state, cfg, nowdt, active, log=print):
    """ONE consolidated _get_broker_adapter() call per tick feeding both the daily P&L
    wiring and the reconcile scheduler above -- kept as a single call site so adding
    these two independent, Firestore-free concerns doesn't multiply how many times
    tick() touches the broker adapter singleton. Never raises.

    MAJOR REVIEW FIX #1 (2026-09-26): both callees below take OrderAdapter._lock
    (update_daily_pnl/reset_daily_pnl directly, reconcile()/fail_closed via
    _reconcile_with_timeout) -- the same lock a still-hung broker send
    (_place_stock_order_with_timeout) keeps holding for as long as it keeps running in
    the background after this process gives up waiting on it. Calling into either while
    that is true would block THIS tick thread on that lock too, freezing the whole tick
    loop rather than just the send -- see _skip_broker_housekeeping_for_inflight_send's
    own module comment. Skip this tick's housekeeping entirely rather than block; the
    reconcile scheduler's own due/interval bookkeeping is untouched, so nothing here is
    lost, only delayed until the send resolves."""
    try:
        adapter = _get_broker_adapter(log=log)
    except Exception as e:
        log(f"[qqq-exec] broker housekeeping skipped (adapter unavailable): "
            f"{type(e).__name__}: {e}")
        return
    if _skip_broker_housekeeping_for_inflight_send(log=log):
        return
    _sync_broker_daily_pnl(state, adapter, nowdt, log=log)
    _maybe_run_broker_reconcile(state, cfg, adapter, nowdt, active, log=log)


# -- RESTING ORB STOP (2026-09-29, owner GO via MANAGER) -------------------------------------
# ORB #314's stop -- and, opt-in, its 5R target inside ONE native OCO -- rests at Webull on
# the ONE netted QQQ account the NOISE and ORB legs share, armed from the bar AFTER the
# entry fill exactly as the backtest's stop is live from the next bar. The levels come from
# the engine (api/cloud_signal.py writes stop_px / target_px on ORB's ENTRY row and a LEVELS
# row when breakeven moves the stop), so the book never re-derives them. Netting-safe by
# construction: api/webull_orders.py's order gateway cancels and confirms every resting
# order before ANY other QQQ order is planned (and, in the stop modes, waits for an earlier
# part to be FILLED or dead), and every resting order is re-planned from the confirmed
# account net as ONE part -- never one that would cross zero.
#
# config orb_resting.mode:
#   "off"         -- today's behaviour byte for byte: no LEVELS row consumed, no level on
#                    a lot, no status block, no adapter call from this section;
#   "log_only"    -- DEFAULT: every arm / cancel / re-arm / crossing decision is logged and
#                    published (doc["orb_resting"]); no resting order is ever sent. Its
#                    one Webull call is the process-start boot sweep's single read-only
#                    get_order_open (_resting_boot_sweep: a crashed stop-mode host's
#                    resting order is cancelled, a hand-placed one only listed);
#   "stop"        -- the stop rests (STOP_LOSS, DAY, CORE);
#   "stop_target" -- the stop and the 5R target rest as ONE native OCO. Runs only with
#                    orb_resting.oco_verified = true (a real-fill paper probe of the OCO
#                    sibling cancel and partial fills), else as "stop". Webull fills the
#                    OCO leg its tape reaches first; the backtest checks the stop first
#                    inside a bar, so a bar touching both can be a stop in the backtest
#                    and a target fill at Webull (the fill parity then says "diverged").
#
# ARMING RULE (_resting_arm_gate): the lot has engine levels; ORB's OPEN is confirmed
# FILLED at Webull (a part-filled entry rests the filled shares, a book-only lot nothing);
# qty = ORB's confirmed broker quantity; no broker send in flight and nothing in the
# re-send queue (the adapter itself refuses while any QQQ part is not yet terminal);
# 09:30 <= now < flat_by - 1 min; no book KILL, breaker not tripped, adapter not halted by
# reconcile, lease ok; the live stream's last trade still on the right side of the level --
# else the stop is already hit and ORB's market close goes out now. Side from the account
# net (webull_orders.plan_resting_side): SELL closing when n >= q, SHORT opening when
# n <= 0, NOT rested when 0 < n < q (ORB then exits on the engine's bar close, one event
# per trade); BUY is the mirror. At most one placement per tick; at most
# RESTING_MAX_TRIES failed tries per trade and level, with backoff, then one push and the
# engine-exit fallback.
#
# A RESTING FILL is ONE broker_orders.csv CLOSE row (signal_id qx<tid>C -- so the fill
# parity and the Webull P&L of record find it unchanged -- client_order_id = the resting
# id, shadow_px = the engine level, broker_fill_px = Webull's price) and sets
# lot["broker_closed"]: the shadow lot stays engine-driven and its later EXIT (or the
# day's flatten) closes it at the engine price with no second broker order.
RESTING_LEG = "ORB"
RESTING_QTY_UNREADABLE = "ORB's broker quantity is not readable now"
ORB_RESTING_MODES = ("off", "log_only", "stop", "stop_target")
RESTING_STOP_MODES = ("stop", "stop_target")
RESTING_MAX_TRIES = 3
RESTING_TRY_BACKOFF_SEC = (5.0, 10.0, 20.0)
# Webull's rate limit (HTTP 429, outcome RATE_LIMITED) is waited out this long and never
# counts as a failed try (2026-09-29 second review: a ~35 s 429 streak used to use up all
# RESTING_MAX_TRIES and leave ORB without its stop for the trade).
RESTING_RATE_LIMIT_WAIT_SEC = 60.0
RESTING_ARM_FROM = (9, 30)
_RESTING_PROCESS = {"prev_terminal": False, "bad_mode_warned": None}
# A healthy resting order is looked up at most this often in the background; at once when
# the live stream prints through a level, a leg is due a cancel or a look, or another
# order went out on the symbol since the last look (2026-09-29 review: one lookup every
# 5 s tick is ~4,000 get_order_detail calls a day against an unverified rate limit).
RESTING_LOOKUP_EVERY_SEC = 30.0

# BOUNDED RESTING CALLS (2026-09-29 review, major): every resting adapter call that can
# reach Webull (place, replace, cancel-and-confirm, resolve, boot sweep) runs on ITS OWN
# single worker with a hard wall-clock timeout, like _order_status_executor and
# _positions_executor -- this SDK's own timeouts are not reliably honoured (the 09-03
# 10-hour hang). A call that times out keeps running in the background; until it
# finishes (and for RESTING_CALL_COOLDOWN_SEC after a timeout) the resting step skips
# itself and the flatten's step 1 falls through to the closes, whose own gateway runs on
# the bounded send worker. The adapter lets its lock go for every one of these network
# calls, so a hung one never freezes the tick's other adapter reads either.
RESTING_RESOLVE_HARD_TIMEOUT_SEC = 8.0     # one cancel_order + one get_order_detail (+ a
                                           # get_order_open read for a stuck record)
RESTING_PLACE_HARD_TIMEOUT_SEC = webull_orders.SEND_LOOKUP_BUDGET_SEC + 4.0
RESTING_CANCEL_HARD_TIMEOUT_SEC = webull_orders.RESTING_GATEWAY_BUDGET_SEC + 4.0
RESTING_REPLACE_HARD_TIMEOUT_SEC = webull_orders.RESTING_GATEWAY_BUDGET_SEC + 4.0
RESTING_CALL_COOLDOWN_SEC = 10.0
# A resting call still on the wire this long gets ONE high push (2026-09-29 review): a hung
# place keeps its ids "sending", and the gateway then holds EVERY QQQ order -- NOISE's
# exits and the 15:59 flatten included -- until it returns (fail-closed and netting-safe:
# settling it could leave an unrecorded live stop if the send lands later). The owner
# checks Webull's open orders by hand before 15:59.
RESTING_HANG_ALERT_SEC = 60.0
_resting_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="qqq-resting")
_resting_inflight = {"future": None, "what": None, "timed_out_at": 0.0}


class _RestingCallPending(Exception):
    """A resting adapter call did not answer inside its hard timeout (it may still land),
    or an earlier one is still running: its outcome is unknown this tick."""


def _resting_busy():
    """True while a resting call is still running on the resting worker, or one timed out
    within RESTING_CALL_COOLDOWN_SEC. Never raises."""
    try:
        fut = _resting_inflight.get("future")
        if fut is not None:
            if not fut.done():
                return True
            _resting_inflight["future"] = None
        return time.time() - float(_resting_inflight.get("timed_out_at") or 0.0) \
            < RESTING_CALL_COOLDOWN_SEC
    except Exception:
        return False


def _resting_call(what, timeout, fn, *args, log=print, **kwargs):
    """fn(*args, **kwargs) on the resting worker, bounded to `timeout` wall-clock seconds.
    Raises _RestingCallPending when a previous call is still running or this one timed out
    (logged once); re-raises fn's own exception. Returns fn's result."""
    prior = _resting_inflight.get("future")
    if prior is not None and not prior.done():
        raise _RestingCallPending(f"an earlier resting call ({_resting_inflight.get('what')}) "
                                  f"is still running")
    fut = _resting_executor.submit(fn, *args, **kwargs)
    _resting_inflight.update(future=fut, what=what, started_at=time.time(), hang_alerted=False)
    try:
        return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        fut.cancel()   # a no-op once started
        _resting_inflight["timed_out_at"] = time.time()
        log(f"[qqq-exec] resting {what} did not answer in {timeout:g}s -- its outcome is "
            f"unknown; the resting step pauses until it finishes (the order gateway cancels "
            f"first before any other QQQ order)")
        raise _RestingCallPending(f"resting {what} timed out after {timeout:g}s")


def _resting_hang_alert(state, log=print):
    """ONE high push per resting call still running after RESTING_HANG_ALERT_SEC (see
    there). Never raises."""
    try:
        fut = _resting_inflight.get("future")
        if fut is None or fut.done() or _resting_inflight.get("hang_alerted"):
            return
        age = time.time() - float(_resting_inflight.get("started_at") or time.time())
        if age < RESTING_HANG_ALERT_SEC:
            return
        _resting_inflight["hang_alerted"] = True
        msg = (f"QQQ BROKER: the resting {_resting_inflight.get('what')} call to Webull has not "
               f"answered for {age:.0f}s -- every QQQ order (NOISE's exits and the 15:59 "
               f"flatten included) waits for it. Check Webull's open QQQ orders by hand "
               f"before 15:59")
        log(f"[qqq-exec] {msg}")
        _log_event(state, "broker", msg, log=log)
        close = _phone_close()
        started = float(_resting_inflight.get("started_at") or 0.0)
        _say_hold(state, f"every QQQ order waits, the {close} close included",
                  f"Webull has not answered the {_leg_word(RESTING_LEG)} stop order for "
                  f"{max(1, int(round(age / 60.0)))} min",
                  f"check Webull's open QQQ orders before {close}", cause="resting_hang",
                  problem_id=f"{_phone_day()} {started:.0f}", log=log)
    except Exception as e:
        log(f"[qqq-exec] resting hang alert failed (non-fatal): {type(e).__name__}: {e}")


def _orb_resting_mode(cfg):
    """config orb_resting.mode, normalised to one of ORB_RESTING_MODES. A missing block
    reads as the default "log_only"; an unreadable value too (sends nothing), warned once
    per process. "stop_target" without orb_resting.oco_verified = true runs as "stop"
    (2026-09-29 review: the OCO's filled-leg sibling cancel and its partial fills are not
    yet proven on a real fill), warned once per process. Never raises."""
    try:
        blk = (cfg or {}).get("orb_resting")
        raw = blk.get("mode", "log_only") if isinstance(blk, dict) else (blk or "log_only")
        mode = str(raw).strip().lower()
        verified = isinstance(blk, dict) and blk.get("oco_verified") is True
    except Exception:
        mode, verified = None, False
    if mode == "stop_target" and not verified:
        if not _RESTING_PROCESS.get("oco_unverified_warned"):
            _RESTING_PROCESS["oco_unverified_warned"] = True
            print("[qqq-exec] WARNING: orb_resting.mode='stop_target' needs "
                  "orb_resting.oco_verified=true (a real-fill paper probe of the OCO) -- "
                  "running 'stop': the 5R target stays on the engine exit")
        return "stop"
    if mode in ORB_RESTING_MODES:
        return mode
    if _RESTING_PROCESS["bad_mode_warned"] != mode:
        _RESTING_PROCESS["bad_mode_warned"] = mode
        print(f"[qqq-exec] WARNING: orb_resting.mode={mode!r} is not one of "
              f"{ORB_RESTING_MODES} -- running 'log_only' (nothing rests)")
    return "log_only"


def _resting_gateway_step(cfg, log=print):
    """The adapter gateway's previous-order-terminal rule is on in the stop modes only
    (OrderAdapter.set_prev_terminal(True)); leaving them hands it back to the adapter's
    own config (None). "off" / "log_only" with nothing ever switched never touch the
    adapter. Never raises."""
    want = _orb_resting_mode(cfg) in RESTING_STOP_MODES
    if not want and not _RESTING_PROCESS["prev_terminal"]:
        return
    try:
        fn = getattr(_get_broker_adapter(log=log), "set_prev_terminal", None)
        if callable(fn):
            fn(True if want else None)
        _RESTING_PROCESS["prev_terminal"] = want
    except Exception as e:
        log(f"[qqq-exec] resting gateway mode not set (non-fatal): {type(e).__name__}: {e}")


def _resting_block(state, mode, nowdt):
    """state["orb_resting"] -- this section's own memory, reset per ET day (counts, tries,
    per-trade notes). Created only outside "off"."""
    blk = state.setdefault("orb_resting", {})
    day = nowdt.strftime("%Y-%m-%d")
    if blk.get("day") != day:
        live_seen = blk.get("live_seen")   # survives the day reset: see _maybe_manage_resting
        blk.clear()
        if live_seen:
            blk["live_seen"] = live_seen
        blk.update({"day": day, "resting": None, "last": None, "tries": {}, "noted": {},
                    "counts": {k: 0 for k in ("armed", "rearmed", "replaced", "cancelled",
                                              "crossing", "crossed", "filled", "fallback")}})
    blk["mode"] = mode
    return blk


def _resting_count(blk, kind, n=1):
    counts = blk.setdefault("counts", {})
    counts[kind] = int(counts.get(kind, 0) or 0) + n


_RESTING_VOLATILE_RE = re.compile(r"\b\d+(?:\.\d+)?s\b")


def _resting_note_key(text):
    """A note's text with its running ages ("... landed in 123s") masked, so a reason that
    only counts seconds up is ONE decision, not a new line every tick."""
    return _RESTING_VOLATILE_RE.sub("#s", str(text or ""))


def _resting_note(state, blk, kind, text, nowdt, log=print, event=True):
    """Record the section's latest decision. Logged (and put on the event timeline) only
    when it CHANGES -- ages in seconds masked (_resting_note_key, 2026-09-29 second review:
    the lease's "no stamp ... in 123s" reason wrote a line every 5 s tick) -- so a waiting
    state is one line, not one per 5 s tick. A "wait" note never goes on the timeline
    (2026-09-29 review: each NOISE order while ORB holds would add two or three, some
    naming an order id) -- it is logged and published as the status block's "last" only.
    Returns True when it changed."""
    last = blk.get("last") or {}
    if last.get("kind") == kind and _resting_note_key(last.get("text")) == _resting_note_key(text):
        return False
    blk["last"] = {"at": nowdt.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "text": text}
    log(f"[qqq-exec] ORB resting ({blk.get('mode')}): {text}")
    if event and kind != "wait":
        _log_event(state, "orb_resting", f"ORB resting ({blk.get('mode')}): {text}", log=log)
    return True


def _resting_note_once(state, blk, key, text, nowdt, log=print):
    """One timeline event per trade and `key` (e.g. the crossing case). True the first time."""
    noted = blk.setdefault("noted", {})
    if noted.get(key):
        return False
    noted[key] = nowdt.strftime("%H:%M:%S")
    _log_event(state, "orb_resting", f"ORB resting ({blk.get('mode')}): {text}", log=log)
    return True


def _resting_stream_price(log=print):
    """The live Webull stream's last QQQ trade while the stream is fresh, else None (the
    bar close is too old to judge "already through the level"). Never raises."""
    streamer = _qqq_stream_instance()
    if streamer is None:
        return None
    try:
        if streamer.is_fresh():
            t = streamer.last_trade()
            if t and t.get("price") is not None:
                return float(t["price"])
    except Exception as e:
        log(f"[qqq-exec] live stream read for the resting stop failed: {type(e).__name__}: {e}")
    return None


def _resting_live(adapter, symbol=BROKER_SYMBOL, strict=False):
    """The adapter's live resting records on `symbol` ([] when none). When they cannot be
    read now -- a send in flight, the adapter lock busy past 0.5 s, an error -- [] or, with
    `strict`, None (the caller then skips rather than reading "nothing rests"). No network."""
    fn = getattr(adapter, "resting_orders", None)
    if not callable(fn):
        return []
    if _send_inflight_future() is not None:
        return None if strict else []
    try:
        recs = fn(symbol, lock_timeout=0.5)
    except Exception:
        return None if strict else []
    if not isinstance(recs, list):
        return None if strict else []
    return [r for r in recs if isinstance(r, dict)]


def _resting_broker_qty(adapter, leg):
    """The leg's SIGNED quantity in the adapter's broker_sent_positions (what reached
    Webull and is confirmed or counted), or None when unreadable."""
    try:
        p = ((adapter.status() or {}).get("broker_sent_positions") or {}).get(leg) or {}
        if p and str(p.get("symbol") or BROKER_SYMBOL).upper() != BROKER_SYMBOL:
            return 0.0
        return float(p.get("qty", 0) or 0)
    except Exception:
        return None


def _resting_entry_confirmed(adapter, lot):
    """(True, None) once ORB's OPEN is confirmed at Webull -- every order part of it
    settled (FILLED, or dead after a partial fill: the filled shares rest) -- else
    (False, why). A book-only lot (no part at all) never is."""
    tid = (lot or {}).get("trade_id")
    if not tid:
        return False, "the ORB trade has no trade id"
    prefix = webull_orders._sanitize_client_order_id(
        _broker_signal_id(RESTING_LEG, None, "OPEN", trade_id=tid))
    fn = getattr(adapter, "order_parts", None)
    parts = fn(leg=RESTING_LEG, intent="OPEN") if callable(fn) else []
    # a part refused outright (4xx: booked 0, nothing pending) never reached Webull's book
    parts = [p for p in (parts if isinstance(parts, list) else [])
             if not p.get("resting") and str(p.get("client_order_id") or "").startswith(prefix)
             and (p.get("pending") or int(p.get("booked") or 0) > 0 or p.get("final_status"))]
    if not parts:
        return False, "ORB's entry has no order at Webull (a book-only trade rests nothing)"
    if any(p.get("pending") for p in parts):
        return False, "ORB's entry order outcome is not settled at Webull yet"
    if any(not p.get("final_status") for p in parts):
        return False, "ORB's entry is not confirmed FILLED at Webull yet"
    if not any(int(p.get("booked") or 0) > 0 for p in parts):
        return False, "ORB's entry never filled at Webull"
    return True, None


def _resting_want(lot, mode, adapter):
    """What should rest for `lot` now: {direction, qty (ORB's confirmed broker shares),
    stop, target (stop_target mode only), trade_id} -- or (None, why)."""
    lv = (lot or {}).get("levels") or {}
    stop = _finite_or_none(lv.get("stop_px"))
    if stop is None:
        return None, "the ORB trade carries no engine levels (entered before this build)"
    long_lot = lot.get("side") == "long"
    direction = "SELL" if long_lot else "BUY"
    target = _finite_or_none(lv.get("target_px")) if mode == "stop_target" else None
    if target is not None and ((long_lot and target <= stop) or (not long_lot and target >= stop)):
        target = None
    held = _resting_broker_qty(adapter, RESTING_LEG)
    if held is None:
        # unreadable now (e.g. status() racing a timed-out reconcile thread) is NOT "ORB
        # holds 0": the caller skips the tick instead of cancelling a healthy stop
        return None, RESTING_QTY_UNREADABLE
    qty = int(round(abs(held))) if (held > 0) == long_lot else 0
    return {"direction": direction, "qty": qty, "stop": round(stop, 2),
            "target": None if target is None else round(target, 2),
            "trade_id": lot.get("trade_id")}, None


def _resting_crossed(direction, px, stop, target=None):
    """"stop" / "target" when the live price `px` is already through that level, else None."""
    if px is None:
        return None
    if (px <= stop) if direction == "SELL" else (px >= stop):
        return "stop"
    if target is not None and ((px >= target) if direction == "SELL" else (px <= target)):
        return "target"
    return None


def _resting_arm_gate(state, cfg, adapter, lot, nowdt, active):
    """None when every arming condition except the account side holds (see the section
    comment), else the plain-English reason nothing may rest now. No network."""
    sess = cfg.get("session") or {}
    last_arm = _hhmm_minus(sess.get("flat_by", "15:58"), 1)
    if (not active or not _is_weekday(nowdt) or _market_closed_for_orders(nowdt)
            or _et_hhmm(nowdt) < RESTING_ARM_FROM or _et_hhmm(nowdt) >= _hhmm(last_arm)):
        return f"outside the arming window (09:30 to {last_arm} ET)"
    if state.get("kill_done") or os.path.exists(cfg.get("kill_file") or ""):
        return "the book KILL file is present"
    if state.get("breaker_tripped"):
        return "the daily-loss breaker has tripped"
    if not state.get("_broker_lease_ok", True):
        return f"the cross-host lease is not verified ({state.get('_broker_lease_reason')})"
    at_send = _LEASE.send_gate(_LEASE.uid)
    if at_send is not None and not at_send[0]:
        return f"the cross-host lease is not held ({at_send[1]})"
    if _broker_halt_source(log=lambda *_: None) == "reconcile":
        return "the broker adapter is halted by a reconcile"
    if state.get("_broker_resend"):
        return "a broker re-send is queued -- rest after it"
    if _send_inflight_future() is not None:
        return "a broker send is still in flight"
    try:
        mode, _why = adapter.effective_mode()
    except Exception:
        mode = None
    if mode not in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
        return f"the broker adapter is {mode or 'unreadable'}, not PAPER or LIVE"
    ok, why = _resting_entry_confirmed(adapter, lot)
    return None if ok else why


def _resting_desc(want, side=None):
    """'SELL 10 stop 725.53' (+ ' / target 757.03 (OCO)')."""
    s = f"{side or want['direction']} {want['qty']} QQQ stop {want['stop']:.2f}"
    if want.get("target") is not None:
        s += f" / target {want['target']:.2f} (OCO)"
    return s


def _resting_summary(recs):
    """The published view of live resting records (small, JSON-plain)."""
    return [{"id": r.get("client_order_id"), "kind": r.get("kind"), "side": r.get("side"),
             "qty": r.get("qty"), "stop": r.get("stop_price"), "target": r.get("limit_price"),
             "status": r.get("status"), "trade_id": r.get("trade_id")} for r in recs]


RESTING_EVENT_MAX_REQUEUES = 5


def _book_resting_escape(state, ev, nowdt, log=print):
    """A resting record the adapter settled WITHOUT Webull's own terminal record (see
    webull_orders' STUCK-RECORD ESCAPE: a previous session's DAY order Webull no longer
    finds, or one no lookup could settle and get_order_open does not list -- settled
    unfilled only because Webull's position showed it unfilled): no row (no shares moved
    in the books), one timeline event, one high push, and a reconcile asked for. The
    adapter blocks re-arming until a reconcile agrees and still does not find it open."""
    state["_reconcile_due"] = True
    state["_last_broker_send_at"] = time.time()
    msg = (f"QQQ BROKER: {ev.get('leg') or RESTING_LEG}'s resting {ev.get('kind') or 'stop'} "
           f"{ev.get('client_order_id')} settled {ev.get('status')} with nothing filled "
           f"without a final answer from Webull ({ev.get('reason')}) -- the books count it "
           f"unfilled; no stop re-arms until a reconcile agrees")
    _log_event(state, "broker", msg, log=log)
    # WEBULL PUSH PLAN 10-07, group D: orders still flow (the engine exit still closes ORB)
    w = _leg_word(ev.get("leg") or RESTING_LEG)
    _say(state, "resting_escape", _phone_day(nowdt), ntfy_push.plain(
        PHONE_AREA, "needs a fix", None,
        f"The {w} stop order ended at Webull without a final answer; no new stop until the "
        f"books agree", PHONE_ASK, priority="default"), log=log)


def _book_resting_undecided(state, ev, nowdt, log=print):
    """A resting record Webull does not list as open and whose fill the adapter could NOT
    decide from Webull's position (webull_orders._settle_absent, 2026-09-29 second review):
    it stays live in the books, so the order gateway keeps every QQQ order -- ORB's close
    and the flatten included -- back until it is settled; never a second close on a stop
    that may have filled. One timeline event, one high push, a reconcile asked for."""
    state["_reconcile_due"] = True
    state["_last_broker_send_at"] = time.time()
    msg = (f"QQQ BROKER: {ev.get('leg') or RESTING_LEG}'s resting {ev.get('kind') or 'stop'} "
           f"{ev.get('client_order_id')} is not among Webull's open orders, and whether it "
           f"FILLED cannot be told yet ({ev.get('reason')}) -- it stays open in the books and "
           f"every QQQ order waits until it is settled; check Webull if this lasts")
    _log_event(state, "broker", msg, log=log)
    close = _phone_close(nowdt)
    _say_hold(state, f"every QQQ order waits, the {close} close included",
              f"Webull no longer lists the {_leg_word(ev.get('leg') or RESTING_LEG)} stop order "
              f"and cannot say yet if it filled",
              f"check Webull's open QQQ orders if this lasts past {close}",
              cause="resting_undecided",
              problem_id=f"{_phone_day(nowdt)} {ev.get('client_order_id') or ''}".strip(),
              log=log)


def _resting_fill_stamp(ev, now_et):
    """(ts_et text, note) for a resting fill row: now -- unless the order was placed on an
    EARLIER ET session (a DAY order that filled while the book was down, booked by the next
    boot sweep): then that session's date at 16:00, so the day's broker-realized P&L pairs
    it with that day's OPEN (2026-09-29 second review)."""
    stamp = now_et.strftime("%Y-%m-%d %H:%M:%S")
    placed = _finite_or_none(ev.get("placed_at"))
    if placed is None or _NY is None:
        return stamp, ""
    try:
        day = datetime.fromtimestamp(placed, _NY).date()
    except Exception:
        return stamp, ""
    if day >= now_et.date():
        return stamp, ""
    return (f"{day.isoformat()} 16:00:00",
            f" (filled on {day.isoformat()} while the book was down; booked "
            f"{now_et.strftime('%Y-%m-%d %H:%M')})")


def _book_one_resting_fill(state, adapter, ev, mode, nowdt, log=print):
    """ONE resting fill event -> its broker_orders.csv CLOSE row (written FIRST: an
    exception before it leaves the event unbooked, and the caller hands it back to the
    adapter), then the lot flag, the timeline event and the push (their own failures are
    only logged -- the row is the record). Returns 1 when a row was written, else 0."""
    change = int(ev.get("change") or 0)
    if ev.get("undecided"):
        _book_resting_undecided(state, ev, nowdt, log=log)
        return 0
    if ev.get("escaped"):
        _book_resting_escape(state, ev, nowdt, log=log)
        return 0
    if change <= 0:
        return 0
    leg = ev.get("leg") or RESTING_LEG
    tid = ev.get("trade_id")
    kind = ev.get("kind") or "stop"
    level = _finite_or_none(ev.get("stop_price") if kind == "stop" else ev.get("limit_price"))
    lot = (state.get("legs") or {}).get(leg)
    lot = lot if lot and lot.get("trade_id") == tid else None
    if level is None and lot is not None:
        lv = lot.get("levels") or {}
        level = _finite_or_none(lv.get("stop_px" if kind == "stop" else "target_px"))
    fill_px = _finite_or_none(ev.get("filled_price"))
    stamp, late_note = _resting_fill_stamp(ev, _now_et())
    inferred = bool(ev.get("inferred"))
    row = {
        "ts_et": stamp, "leg": leg, "intent": "CLOSE",
        "side": ev.get("side") or "", "shares": change,
        "signal_id": _broker_signal_id(leg, None, "CLOSE", trade_id=tid) if tid else "",
        "client_order_id": ev.get("client_order_id") or "", "mode": mode,
        "ok": True, "sent": True,
        "shadow_px": round(level, 4) if level is not None else "",
        "broker_fill_px": round(fill_px, 4) if fill_px is not None else "",
        "slippage": (round(fill_px - level, 4)
                     if fill_px is not None and level is not None else ""),
        "reason": f"resting {kind} filled at Webull"
                  + ("" if ev.get("final", True) else " (partial)")
                  + (" (inferred from Webull's position -- fill price unknown)" if inferred else "")
                  + late_note,
        "duplicate": False, "host_id": _lease_host_id(), "outcome": "OK",
    }
    _append_csv(BROKER_ORDERS_CSV, BROKER_ORDER_COLS, row, BROKER_ORDERS_KEEP)
    try:
        # the books moved at Webull: confirm after the post-order grace, as for a send
        state["_reconcile_due"] = True
        state["_last_broker_send_at"] = time.time()
        held = _resting_broker_qty(adapter, leg)
        px_txt = f" @ {fill_px:.2f}" if fill_px is not None else ""
        lvl_txt = f" ({kind} {level:.2f})" if level is not None else ""
        if lot is not None:
            if held is not None and abs(held) < 1e-9:
                lot["broker_closed"] = {
                    "by": f"resting {kind}", "ok": True, "px": fill_px,
                    "id": ev.get("client_order_id"),
                    "at": nowdt.strftime("%Y-%m-%d %H:%M:%S"),
                    "note": f"already closed at Webull by the resting {kind} "
                            f"{ev.get('client_order_id')}{px_txt}"}
            else:
                lot["broker_partial"] = {"id": ev.get("client_order_id"),
                                         "filled": int(ev.get("filled") or 0), "px": fill_px}
        blk = state.get("orb_resting")
        if isinstance(blk, dict):
            _resting_count(blk, "filled")
        msg = (f"QQQ BROKER: {leg}'s resting {kind} filled at Webull: {ev.get('side')} "
               f"{change}{px_txt}{lvl_txt}"
               + ("" if ev.get("final", True) else " -- a PARTIAL fill; the rest of the "
                  "group is cancelled and the engine exit closes what is left")
               + (" -- the book's trade stays open until the strategy's own exit"
                  if lot is not None else "")
               + (f" -- INFERRED: Webull no longer lists the order and its position shows the "
                  f"fill ({ev.get('reason')}); Webull's fill price is not known"
                  if inferred else "") + late_note)
        _log_event(state, "broker", msg, log=log)
        # WEBULL PUSH PLAN 10-07, group F: a fill is low (no buzz); an INFERRED one (fill price
        # unknown) needs a fix today (default). The strategy's own exit, when it comes, sends
        # no second fill note for this lot (lot["broker_closed"] -- see _reduce_lot).
        w = _leg_word(leg)
        part = "" if ev.get("final", True) else " (part of it)"
        if inferred:
            note = ntfy_push.plain(
                PHONE_AREA, "needs a fix", None,
                f"The {w} {kind} order filled at Webull{part}, but its price is not known",
                PHONE_ASK, priority="default")
        else:
            note = ntfy_push.plain(
                "QQQ fill", f"{w} {kind} filled", None,
                (f"The {w} {kind} order filled at Webull at {ntfy_push.price(fill_px)}{part}"
                 if fill_px is not None else f"The {w} {kind} order filled at Webull{part}"),
                "nothing", priority="low")
        _say(state, f"fill:{leg}", f"stop {ev.get('client_order_id')} {change}", note, log=log)
    except Exception as e:
        log(f"[qqq-exec] resting fill {ev.get('client_order_id')} booked, but its follow-up "
            f"failed (non-fatal): {type(e).__name__}: {e}")
    return 1


def _book_resting_fills(state, adapter, nowdt, log=print):
    """Turn every resting fill the adapter booked (gateway, resolve, reconcile, boot sweep,
    a cancel or a replace -- take_resting_events) into ONE broker_orders.csv CLOSE row per
    event and the lot's broker_closed flag; one timeline event and one push each. An
    escape event (a record settled with no final answer from Webull) pushes and asks for a
    reconcile. An event that could not be booked -- and every one after it -- goes back
    to the adapter's queue for the next tick (at most RESTING_EVENT_MAX_REQUEUES times,
    then a loud log and push: broker_orders.csv, parity and the P&L of record would miss
    that fill). Returns the number of rows written. Never raises."""
    try:
        take = getattr(adapter, "take_resting_events", None)
        events = take(lock_timeout=0.5) if callable(take) else []
        if not isinstance(events, list) or not events:
            return 0
    except Exception as e:
        log(f"[qqq-exec] resting fill booking failed (non-fatal): {type(e).__name__}: {e}")
        return 0
    try:
        mode, _ = adapter.effective_mode()
    except Exception:
        mode = ""
    booked = 0
    for i, ev in enumerate(events):
        try:
            booked += _book_one_resting_fill(state, adapter, ev, mode, nowdt, log=log)
        except Exception as e:
            rest = []
            for r in events[i:]:
                if not isinstance(r, dict):
                    continue
                r = dict(r, requeued=int(r.get("requeued") or 0) + (1 if r is ev else 0))
                if r["requeued"] > RESTING_EVENT_MAX_REQUEUES:
                    msg = (f"QQQ BROKER: the resting {r.get('kind')} fill "
                           f"{r.get('client_order_id')} ({r.get('side')} {r.get('change')}) "
                           f"could not be written to broker_orders.csv after "
                           f"{RESTING_EVENT_MAX_REQUEUES} tries ({type(e).__name__}: {e}) -- "
                           f"dropped; the books count it, the fill ledger does not")
                    log(f"[qqq-exec] {msg}")
                    _log_event(state, "broker", msg, log=log)
                    # WEBULL PUSH PLAN 10-07, group D
                    _say(state, "fill_ledger", _phone_day(nowdt), ntfy_push.plain(
                        PHONE_AREA, "needs a fix", None,
                        f"{_a_leg_word(r.get('leg') or RESTING_LEG)} stop fill could not be "
                        f"written to the fill record (the books count it)",
                        PHONE_ASK, priority="default"), log=log)
                    continue
                rest.append(r)
            put = getattr(adapter, "requeue_resting_events", None)
            back = bool(callable(put) and put(rest))
            log(f"[qqq-exec] resting fill booking failed at {ev.get('client_order_id')} "
                f"({type(e).__name__}: {e}) -- {len(rest)} event(s) "
                + ("handed back for the next tick" if back else
                   "LOST (the adapter would not take them back): "
                   + ", ".join(f"{r.get('client_order_id')} {r.get('side')} {r.get('change')}"
                               for r in rest)))
            break
    return booked


def _resting_market_close(state, lot, qty, level, why, nowdt, log=print):
    """The live price is already through ORB's level: send ORB's market close now (the
    backtest's bar will show the stop hit). A broker-only close -- the shadow lot waits for
    the engine's EXIT, which then sends nothing when this close was accepted
    (lot["broker_closed"]["ok"]); one that was not stays with the close re-send queue, and
    the engine EXIT / flatten still send ORB's close (see _reduce_lot)."""
    tid = lot.get("trade_id")
    _mirror_to_broker(state, leg=RESTING_LEG, side=lot["side"], shares=qty, shadow_px=level,
                      intent="CLOSE", ts=lot.get("entry_ts"), trade_id=tid, nowdt=nowdt, log=log)
    last = state.get("_broker_last") or {}
    ok = bool(last.get("ok")) and last.get("leg") == RESTING_LEG
    if not lot.get("broker_closed"):
        lot["broker_closed"] = {
            "by": "market", "ok": ok, "px": None,
            "id": _broker_signal_id(RESTING_LEG, None, "CLOSE", trade_id=tid),
            "at": nowdt.strftime("%Y-%m-%d %H:%M:%S"),
            "note": ("already closed at Webull by a market close sent when " + why if ok else
                     "its broker close already went out when " + why
                     + " (the close re-send queue owns it)")}
    return ok


def _resting_try_key(want):
    return f"{want['trade_id']}|{want['stop']:.2f}|{want.get('target')}"


def _resting_tries_ok(blk, key, now_wall):
    """False while a failed try's backoff runs, or once this trade and level gave up."""
    t = (blk.get("tries") or {}).get(key) or {}
    return not t.get("gave_up") and now_wall >= float(t.get("next_at") or 0)


def _resting_try_failed(state, blk, key, text, nowdt, log=print):
    """Count one failed arm/replace try for `key`; the RESTING_MAX_TRIES-th pushes once
    and hands ORB back to the engine exit for this level."""
    tries = blk.setdefault("tries", {})
    t = tries.setdefault(key, {"n": 0})
    t["n"] = int(t.get("n") or 0) + 1
    t["next_at"] = time.time() + RESTING_TRY_BACKOFF_SEC[min(t["n"], len(RESTING_TRY_BACKOFF_SEC)) - 1]
    t["last"] = text
    if t["n"] >= RESTING_MAX_TRIES and not t.get("gave_up"):
        t["gave_up"] = True
        _resting_count(blk, "fallback")
        msg = (f"QQQ BROKER: ORB's resting stop could not be placed after {t['n']} tries "
               f"({text}) -- ORB exits on the engine's bar close for this trade")
        _resting_note(state, blk, "fallback", msg, nowdt, log=log)
        # WEBULL PUSH PLAN 10-07, group H: default -- ORB still exits, on the bar close
        _say(state, "resting_place", _phone_day(nowdt), ntfy_push.plain(
            PHONE_AREA, "needs a fix", None,
            "ORB's stop order could not be placed at Webull; ORB exits on the bar close "
            "instead", PHONE_ASK, priority="default"), log=log)
    else:
        _resting_note(state, blk, "retry", f"try {t['n']} of {RESTING_MAX_TRIES} failed: {text}",
                      nowdt, log=log)


def _resting_rate_limited(state, blk, key, text, nowdt, log=print):
    """Webull's rate limit (429) on a place or replace: wait RESTING_RATE_LIMIT_WAIT_SEC, and
    never count it as one of the RESTING_MAX_TRIES failed tries."""
    t = blk.setdefault("tries", {}).setdefault(key, {"n": 0})
    t["next_at"] = time.time() + RESTING_RATE_LIMIT_WAIT_SEC
    t["last"] = text
    _resting_note(state, blk, "wait", f"Webull's rate limit -- tried again in "
                  f"{RESTING_RATE_LIMIT_WAIT_SEC:g} s, not counted as a failed try ({text})",
                  nowdt, log=log)


def _resting_cancel(state, blk, adapter, why, nowdt, log=print, confirm=True, **filters):
    """Cancel and confirm live resting orders (always whole groups), book any fill found
    (confirm=False only sends the cancels: the next gateway / lookup confirms them).
    Bounded (RESTING_CANCEL_HARD_TIMEOUT_SEC); raises _RestingCallPending on a timeout."""
    res = _resting_call("cancel", RESTING_CANCEL_HARD_TIMEOUT_SEC, adapter.cancel_resting,
                        log=log, symbol=BROKER_SYMBOL, confirm=confirm, **filters) or {}
    _book_resting_fills(state, adapter, nowdt, log=log)
    if res.get("cancelled"):
        _resting_count(blk, "cancelled", len(res["cancelled"]))
    text = (f"cancelled {', '.join(res.get('cancelled') or []) or 'nothing'} ({why})"
            + (f"; filled first: {', '.join(res['filled'])}" if res.get("filled") else "")
            + (f"; NOT confirmed yet: {', '.join(res['unresolved'])} -- asked again next tick"
               if res.get("unresolved") else ""))
    _resting_note(state, blk, "cancel", text, nowdt, log=log)
    return res


# WORST CASE NEAR THE CLOSE (2026-09-29 review): with Webull slow or hung, one tick can
# block for RESTING_PLACE_HARD_TIMEOUT_SEC (~19 s), RESTING_CANCEL_HARD_TIMEOUT_SEC (12 s)
# or the flatten's step 1 (12 s), on top of the reconcile's 12 s and each close's 8 s
# gateway. With under this many seconds left before the session close the flatten's step 1
# only SENDS the cancels (no confirm wait): each close's own gateway cancels and confirms
# first anyway, and the after-close guard would block closes that start past 16:00. 30 s,
# not 60: the box's flat_by is 15:59, so an on-time flatten (~55-59 s left) still confirms
# first and keeps ORB in the internal cross; only a late one takes the short path.
RESTING_FLATTEN_CONFIRM_MIN_LEFT_SEC = 30.0


def _resting_seconds_to_close(nowdt):
    """Seconds from `nowdt` to today's session close (the after-close guard's own
    moment), or None when unknown. Never raises."""
    try:
        if nowdt is None or not market_calendar.is_session(nowdt):
            return None
        close_dt = _session_flatten_deadline(nowdt) + timedelta(
            seconds=SESSION_FLATTEN_DEADLINE_MARGIN_SEC)
        return (close_dt - nowdt).total_seconds()
    except Exception:
        return None


def _cancel_resting_for_flatten(state, cfg, reason, nowdt=None, log=print):
    """Step 1 of the EOD / KILL / BREAKER flatten (_close_all): cancel every resting order
    and wait for Webull to report it CANCELLED or FILLED (a fill is booked, so its leg's
    close below sends nothing). A cancel that cannot be confirmed leaves that leg out of
    the internal cross; its own close goes through the gateway, which tries again. In
    log_only it records what would have been cancelled. Outside the stop modes the adapter
    is only asked while a stop mode's order may still rest ("off" from the start never
    touches it). Bounded: while an earlier resting call is still running, or this cancel
    does not answer in RESTING_CANCEL_HARD_TIMEOUT_SEC, the flatten goes straight on to
    the closes (their gateway cancels first, on the bounded send worker). Never raises."""
    mode = _orb_resting_mode(cfg)
    blk = state.get("orb_resting")
    blk = blk if isinstance(blk, dict) else None
    if mode not in RESTING_STOP_MODES and not (blk and (blk.get("resting") or blk.get("live_seen"))):
        return
    try:
        nowdt = nowdt or _now_et()
        if mode != "off":
            blk = _resting_block(state, mode, nowdt)
        if mode == "log_only" and isinstance(blk.get("resting"), dict):
            _resting_count(blk, "cancelled")
            _resting_note(state, blk, "cancel", f"log only: would cancel and confirm the resting "
                          f"{blk['resting'].get('desc')} before the {reason} flatten", nowdt, log=log)
            blk["resting"] = None
        if mode not in RESTING_STOP_MODES and not blk.get("live_seen"):
            return
        adapter = _get_broker_adapter(log=log)
        if _resting_busy():
            log(f"[qqq-exec] {reason} flatten: step 1 skipped -- a resting call to Webull is "
                f"still running; each close's gateway cancels first")
            return
        live = _resting_live(adapter, symbol=None, strict=True)
        if live is None:
            log(f"[qqq-exec] {reason} flatten: step 1 skipped -- the resting records are not "
                f"readable now; each close's gateway cancels first")
            return
        if not live:
            _book_resting_fills(state, adapter, nowdt, log=log)
            return
        if _market_closed_for_orders(nowdt):
            return   # no broker call after the close; the DAY orders expire at 16:00
        left = _resting_seconds_to_close(nowdt)
        quick = left is not None and left < RESTING_FLATTEN_CONFIRM_MIN_LEFT_SEC
        _resting_cancel(state, blk, adapter, f"{reason} flatten, step 1"
                        + (f" -- {left:.0f}s to the close: cancels sent, each close's gateway "
                           f"confirms" if quick else ""), nowdt, log=log, confirm=not quick)
    except Exception as e:
        log(f"[qqq-exec] {reason} flatten: resting cancel failed (non-fatal -- the gateway "
            f"cancels before each close): {type(e).__name__}: {e}")


def _resting_boot_sweep(adapter, log=print):
    """Process start (_reconcile_broker_at_boot, before the reconcile): whenever
    orb_resting.mode is not "off" (log_only included -- design section 10: a PC <-> box
    hand-over must also catch the OTHER host's resting orders), or the adapter still
    records a live resting order, run OrderAdapter.boot_sweep -- fills booked, stuck
    records settled, and open QQQ orders this state does not know listed. They are
    CANCELLED (and entries halted until a reconcile agrees, one high push) only in the stop
    modes or while this state still records a resting order, and only while this host
    holds the cross-host lease. In log_only with nothing resting they are only listed and
    pushed (2026-09-29 second review: log_only was promised to send nothing, and a
    hand-placed paper order must not be cancelled by a restart) -- except an order whose id
    is a RESTING id (webull_orders.RESTING_ID_RE, third review): certainly this book's own
    stop, left by a stop-mode host that crashed without standing down (or a PC / box config
    mismatch); left working it would trip the 417 box rule on this host's next QQQ order or
    fill unbooked, so with the lease it is cancelled in every mode but "off" (one high push).
    Without the lease nothing is cancelled. A listed-only order is pushed ONCE per id, not
    at every restart (the adapter remembers it, state["boot_listed"]). With nothing
    resting that is ONE read-only get_order_open call per process start -- log_only's only
    Webull call. Bounded to RECONCILE_HARD_TIMEOUT_SEC on the resting worker (the sweep's
    own budget is 2 s less). The first tick re-verifies what is still live against the
    lot. Never raises."""
    try:
        mode = _orb_resting_mode(_read_config_for_gate(log=log))
        resting_now = bool(_resting_live(adapter, symbol=None))
        if mode == "off" and not resting_now:
            return
        sweep = getattr(adapter, "boot_sweep", None)
        if not callable(sweep):
            return
        at_send = _LEASE.send_gate(_LEASE.uid)
        lease_ok = at_send is None or bool(at_send[0])
        stop_side = mode in RESTING_STOP_MODES or resting_now
        why_not = ("this host does not hold the lease" if not lease_ok else
                   f"orb_resting.mode is {mode!r} and nothing of this book rests -- listed only")
        res = _resting_call("boot sweep", RECONCILE_HARD_TIMEOUT_SEC, sweep, log=log,
                            symbols=(BROKER_SYMBOL,), cancel_unknown=lease_ok and stop_side,
                            budget_sec=max(1.0, RECONCILE_HARD_TIMEOUT_SEC - 2.0),
                            no_cancel_reason=why_not, cancel_resting_pattern=lease_ok)
        if not isinstance(res, dict):
            return
        log(f"[qqq-exec] resting boot sweep: resolved {res.get('resolved') or {}}, still live "
            f"{res.get('live') or []}" + (f" -- {res.get('reason')}" if res.get("reason") else ""))
        if res.get("unknown"):
            cancelled = res.get("cancelled_unknown", True)
            n_cx = len(res.get("unknown_cancelled") or ([] if not cancelled else res["unknown"]))
            if not cancelled and lease_ok and "unknown_new" in res and not res["unknown_new"]:
                # listed only, and every one already pushed at an earlier start: log, no push
                log(f"[qqq-exec] resting boot sweep: open QQQ order(s) this book did not know, "
                    f"already reported: {', '.join(o.get('client_order_id') or '' for o in res['unknown'])}")
                return
            msg = (f"QQQ BROKER: at start-up Webull held {len(res['unknown'])} open QQQ order(s) "
                   f"this book did not know -- "
                   + ("cancelled" + (f" ({n_cx} of them)" if n_cx < len(res["unknown"]) else "")
                      + ", and new entries halted until a reconcile agrees"
                      if cancelled else f"NOT cancelled: {why_not}")
                   + f" ({res.get('reason')})")
            log(f"[qqq-exec] {msg}")
            # WEBULL PUSH PLAN 10-07: cancelled + entries halted is group C (a hold, high);
            # listed and left in place is group D (default). No state.json here (start-up):
            # _say dedupes in process memory; the adapter already lists an id only once.
            n = len(res["unknown"])
            if cancelled:
                _say_hold(None, "new QQQ entries wait until the book and Webull agree",
                          f"At start-up Webull held {n} QQQ orders the book did not know; "
                          f"they were cancelled",
                          "check Webull's open QQQ orders, or " + PHONE_ASK, cause="boot",
                          log=log)
            else:
                _say(None, "boot_unknown", _phone_day(), ntfy_push.plain(
                    PHONE_AREA, "needs a fix", None,
                    f"At start-up Webull held {n} QQQ orders the book did not know (left in "
                    f"place)", PHONE_ASK, priority="default"), log=log)
    except Exception as e:
        log(f"[qqq-exec] resting boot sweep failed (non-fatal): {type(e).__name__}: {e}")


def _apply_engine_levels(state, cfg, leg, e, row_tid, lot, log=print):
    """A LEVELS row (api/cloud_signal.py: breakeven armed at a bar's close; the new stop
    is in force from the next bar): move the open lot's engine stop. The resting stop
    follows in _maybe_manage_resting (replace in place, cancel + new as the fallback)."""
    if leg != RESTING_LEG:
        return
    if not lot or not row_tid or lot.get("trade_id") != row_tid:
        log(f"[qqq-exec] {leg} LEVELS row for {row_tid or 'a trade with no id'} ignored -- "
            f"not the open trade ({(lot or {}).get('trade_id')})")
        return
    stop = e.get("stop_px") if e.get("stop_px") is not None else _finite_or_none(e.get("ref_price"))
    if stop is None:
        return
    lv = lot.setdefault("levels", {"stop_px": None, "target_px": None,
                                   "initial_stop_px": None, "be_armed_at": None})
    old = _finite_or_none(lv.get("stop_px"))
    lv["stop_px"] = float(stop)
    if e.get("target_px") is not None:
        lv["target_px"] = e["target_px"]
    lv["be_armed_at"] = str(e.get("ref_time") or "")
    mode = _orb_resting_mode(cfg)
    follow = ("log only: a resting stop would be moved to it" if mode == "log_only"
              else "the resting stop is moved to it this tick")
    _log_event(state, "orb_resting",
               f"ORB breakeven: the engine moved the stop "
               f"{'from ' + format(old, '.2f') + ' ' if old is not None else ''}to "
               f"{float(stop):.2f} (armed at the close of the bar {e.get('ref_time')}) -- {follow}",
               log=log)


def _resting_disarm(state, cfg, mode, nowdt, log=print):
    """Leaving the stop modes: cancel whatever still rests (booking any fill), and, in
    "off", drop this section's state once nothing is left. Returns True when done."""
    adapter = _get_broker_adapter(log=log)
    if _resting_busy():
        return False
    live = _resting_live(adapter, symbol=None, strict=True)
    if live is None:
        return False
    blk = state.get("orb_resting") if isinstance(state.get("orb_resting"), dict) else {}
    if live and not _market_closed_for_orders(nowdt):
        res = _resting_call("cancel", RESTING_CANCEL_HARD_TIMEOUT_SEC, adapter.cancel_resting,
                            log=log, confirm=True) or {}
        _book_resting_fills(state, adapter, nowdt, log=log)
        msg = (f"orb_resting.mode is {mode!r}: cancelled the resting order(s) "
               f"{', '.join(res.get('cancelled') or []) or '(none)'}"
               + (f"; NOT confirmed yet: {', '.join(res['unresolved'])}" if res.get("unresolved") else ""))
        log(f"[qqq-exec] {msg}")
        _log_event(state, "orb_resting", msg, log=log)
        if res.get("unresolved"):
            return False
    else:
        _book_resting_fills(state, adapter, nowdt, log=log)
    if blk:
        blk["resting"] = None
    return True


def _resting_log_only(state, cfg, adapter, blk, nowdt, active, log=print):
    """log_only: decide exactly as the stop modes would and log / publish it; send nothing."""
    lot = (state.get("legs") or {}).get(RESTING_LEG)
    prev = blk.get("resting")
    if not lot:
        blk["resting"] = None
        _resting_note(state, blk, "idle", "no ORB trade open", nowdt, log=log, event=False)
        return
    want, why = _resting_want(lot, "stop", adapter)
    if want is None and why == RESTING_QTY_UNREADABLE:
        _resting_note(state, blk, "wait", f"log only: {why} -- decided next tick", nowdt, log=log)
        return
    if want is None:
        blk["resting"] = None
        _resting_note(state, blk, "idle", why, nowdt, log=log, event=False)
        return
    if prev and prev.get("trade_id") != want["trade_id"]:
        prev = None
    target = _finite_or_none((lot.get("levels") or {}).get("target_px"))
    gate = _resting_arm_gate(state, cfg, adapter, lot, nowdt, active)
    if gate and prev and gate.startswith("outside"):
        # the last minute before flat_by: nothing arms or moves, but what rests stays
        # until the flatten cancels it (_cancel_resting_for_flatten)
        _resting_note(state, blk, "wait", f"log only: the resting {prev.get('desc')} would "
                      f"stay until the flatten ({gate})", nowdt, log=log)
        return
    if gate:
        if prev:
            # something moved under a resting stop that would have been live: the gateway
            # would have cancelled it (another leg's order) -- counted, re-armed when clear.
            # A transient gate (a lease blip, a queued re-send) is counted and logged but
            # kept off the timeline, and so is the re-arm that follows it (2026-09-29
            # second review)
            _resting_count(blk, "cancelled")
            _resting_note(state, blk, "cancel", f"log only: would cancel the resting "
                          f"{prev.get('desc')} ({gate})", nowdt, log=log, event=False)
            blk["resting"] = None
            blk["gated"] = {k: prev.get(k) for k in ("trade_id", "side", "stop")}
            return
        _resting_note(state, blk, "wait", f"log only: nothing would rest -- {gate}", nowdt, log=log)
        return
    if want["qty"] <= 0:
        _resting_note(state, blk, "wait", "log only: nothing would rest -- ORB holds no confirmed "
                      "shares at Webull", nowdt, log=log)
        return
    px = _resting_stream_price(log=log)
    crossed = _resting_crossed(want["direction"], px, want["stop"])
    if crossed:
        _resting_count(blk, "crossed")
        _resting_note_once(state, blk, f"crossed:{want['trade_id']}:{want['stop']:.2f}",
                           f"log only: the live price {px:.2f} is already through ORB's stop "
                           f"{want['stop']:.2f} -- would send ORB's market close now", nowdt, log=log)
        blk["resting"] = None
        return
    plan = adapter.resting_plan(BROKER_SYMBOL, want["direction"], want["qty"], leg=RESTING_LEG)
    if not isinstance(plan, dict) or plan.get("error"):
        return
    last_send = float(state.get("_last_broker_send_at", 0) or 0)
    if plan.get("side") is None:
        if _resting_note_once(
                state, blk, f"crossing:{want['trade_id']}",
                f"log only: would NOT rest ORB's stop -- the account net {plan.get('net'):g} "
                f"sits between 0 and {want['qty']} on the closing side (a resting order would "
                f"cross zero); ORB exits on the engine's bar close", nowdt, log=log):
            _resting_count(blk, "crossing")
        blk["resting"] = None
        return
    refusal = plan.get("refusal")
    if refusal:
        _resting_note(state, blk, "wait", f"log only: nothing would rest yet -- {refusal[1]}",
                      nowdt, log=log)
        return
    snap = {"trade_id": want["trade_id"], "side": plan["side"], "qty": want["qty"],
            "stop": want["stop"], "target": target, "net": plan.get("net"),
            "desc": _resting_desc(want, plan["side"]), "since_send": last_send}
    if prev is None:
        _resting_count(blk, "armed" if not blk.get("noted", {}).get(f"armed:{want['trade_id']}")
                       else "rearmed")
        blk.setdefault("noted", {})[f"armed:{want['trade_id']}"] = True
        gated = blk.pop("gated", None) or {}
        same = (gated.get("trade_id") == snap["trade_id"] and gated.get("side") == snap["side"]
                and gated.get("stop") == snap["stop"])
        _resting_note(state, blk, "arm", f"log only: would rest {snap['desc']} (account net "
                      f"{plan.get('net'):g})" + (f"; the {target:.2f} target stays on the engine "
                                                 f"exit in 'stop' mode, OCO in 'stop_target'"
                                                 if target is not None else ""), nowdt, log=log,
                      event=not same)
    elif last_send > float(prev.get("since_send") or 0):
        # another order went out while the stop would have rested: cancel-first, re-arm
        _resting_count(blk, "cancelled")
        _resting_count(blk, "rearmed")
        _resting_note(state, blk, "rearm", f"log only: the gateway would have cancelled the "
                      f"resting {prev.get('desc')} before that order, then re-armed as "
                      f"{snap['desc']} (account net {plan.get('net'):g})", nowdt, log=log)
    elif abs(float(prev.get("stop") or 0) - want["stop"]) >= 0.005:
        _resting_count(blk, "replaced")
        _resting_note(state, blk, "replace", f"log only: would move the resting stop "
                      f"{float(prev.get('stop')):.2f} -> {want['stop']:.2f} (replace in place)",
                      nowdt, log=log)
    blk["resting"] = snap


def _resting_lease_lost(state):
    """The reason this host must not keep a resting order working at Webull -- its own lease
    is lost, or another host positively holds (or claims) it -- else None. That host's
    gateway does not know this host's resting order (2026-09-29 second review): left live,
    it would trip the 417 box rule on that host's orders, reserve its shares, or fill
    unbooked. A lease that is merely UNVERIFIABLE (a Firestore outage) keeps the stop: that
    is when protection matters most, and closes stay exempt from the gate then too. Stable
    text (no running ages). No network."""
    at_send = _LEASE.send_gate(_LEASE.uid)
    if at_send is not None and not at_send[0] and str(at_send[1] or "").startswith("lease lost"):
        return "this host no longer holds the cross-host lease"
    if not state.get("_broker_lease_ok", True):
        why = str(state.get("_broker_lease_reason") or "")
        if not why.startswith("lease unverifiable") or "claims the lease" in why:
            return "another host holds the cross-host lease"
    return None


def _cancel_resting_on_stand_down(state, log=print):
    """_stand_down (another host took the lease): cancel and confirm every resting order this
    host still records, bounded like every resting call -- the new lease holder's gateway
    and boot sweep do not know them. A cancel can only take protection away, never open a
    position, so it is the one Webull call made after the lease is gone. Only when a stop
    mode ever ran here (live_seen); "off" and log_only never reach the adapter. Never raises."""
    try:
        blk = state.get("orb_resting")
        if not (isinstance(blk, dict) and blk.get("live_seen")):
            return
        adapter = _get_broker_adapter(log=log)
        if _resting_busy():
            log("[qqq-exec] stand-down: a resting call to Webull is still running -- the "
                "resting orders are left to the next boot sweep")
            return
        live = _resting_live(adapter, symbol=None, strict=True)
        if not live:
            return
        res = _resting_call("cancel", RESTING_CANCEL_HARD_TIMEOUT_SEC, adapter.cancel_resting,
                            log=log, confirm=True) or {}
        _book_resting_fills(state, adapter, _now_et(), log=log)
        log(f"[qqq-exec] stand-down: cancelled the resting order(s) "
            f"{', '.join(res.get('cancelled') or []) or '(none)'}"
            + (f"; filled first: {', '.join(res['filled'])}" if res.get("filled") else "")
            + (f"; NOT confirmed: {', '.join(res['unresolved'])}" if res.get("unresolved") else ""))
    except Exception as e:
        log(f"[qqq-exec] stand-down: resting cancel failed (non-fatal): {type(e).__name__}: {e}")


def _resting_reconcile_doubt(adapter):
    """The reason no resting order may stand while a reconcile disagrees with Webull (the
    books every resting order is sized from are wrong), else None. Only a REAL mismatch
    counts (2026-09-29 review): the adapter's resting_blocked, or a reconcile halt whose
    last result lists mismatches. A halt from a positions READ failure or a reconcile hard
    timeout (fail_closed) keeps a working stop -- during a Webull blip the cancel would
    most likely fail too, and the stop is the protection -- while the arm gate still
    blocks any re-arm until a reconcile succeeds. No network."""
    try:
        st = adapter.status() or {}
    except Exception:
        st = {}
    blocked = st.get("resting_blocked")
    if blocked:
        return f"re-arming is blocked until a reconcile agrees ({blocked})"
    if _broker_halt_source(log=lambda *_: None) == "reconcile" and \
            ((st.get("last_reconcile_result") or {}).get("mismatches")):
        return "the broker adapter is halted by a reconcile mismatch"
    return None


def _resting_lookup_due(state, blk, live, pick):
    """One background lookup per RESTING_LOOKUP_EVERY_SEC for a healthy resting group; at
    once when the stream printed through a level (`pick`), a leg is due a cancel or a
    look, a send's answer is still unknown, or another order went out since the last one."""
    if pick is not None:
        return True
    if any(r.get("cancel_due") or r.get("check_due") or r.get("pending") for r in live):
        return True
    looked = float(blk.get("looked_at") or 0)
    if float(state.get("_last_broker_send_at", 0) or 0) > looked:
        return True
    return time.time() - looked >= RESTING_LOOKUP_EVERY_SEC


def _resting_live_step(state, cfg, adapter, blk, nowdt, active, mode, log=print):
    """The stop modes: at most ONE placement, replace or cancel per tick (see the section
    comment); otherwise one status lookup of the live order (_resting_lookup_due). Every
    call that can reach Webull is bounded (_resting_call)."""
    lot = (state.get("legs") or {}).get(RESTING_LEG)
    live = _resting_live(adapter, strict=True)
    if live is None:
        return   # not readable now (a send in flight, the lock busy): next tick
    blk["resting"] = _resting_summary(live) or None
    want, want_why = (_resting_want(lot, mode, adapter) if lot else (None, "no ORB trade open"))
    if want is None and want_why == RESTING_QTY_UNREADABLE:
        _resting_note(state, blk, "wait", f"{want_why} -- nothing changes this tick", nowdt,
                      log=log)
        return   # never read as "ORB holds 0": that would cancel a healthy stop
    px = _resting_stream_price(log=log)
    if live and _market_closed_for_orders(nowdt):
        return   # no broker call after the close: the DAY orders expire at 16:00 and the
        #          next gateway, reconcile or boot sweep settles their records
    if live:
        groups = {r.get("group") for r in live}
        stop_rec = next((r for r in live if r.get("kind") == "stop"), None)
        tgt_rec = next((r for r in live if r.get("kind") == "target"), None)
        doubt = None
        if len(groups) > 1 or stop_rec is None:
            doubt = "more than one resting group, or a group without its stop"
        elif not lot or want is None:
            doubt = want_why if lot else "no ORB trade is open"
        elif stop_rec.get("trade_id") != lot.get("trade_id"):
            doubt = f"it belongs to another trade ({stop_rec.get('trade_id')})"
        elif lot.get("broker_closed"):
            doubt = "ORB is already closed at Webull"
        elif _resting_lease_lost(state):
            doubt = _resting_lease_lost(state)
        elif state.get("kill_done") or os.path.exists(cfg.get("kill_file") or ""):
            doubt = "the book KILL file is present"
        elif state.get("breaker_tripped"):
            doubt = "the daily-loss breaker has tripped"
        elif _resting_reconcile_doubt(adapter):
            doubt = _resting_reconcile_doubt(adapter)
        elif int(stop_rec.get("qty") or 0) != want["qty"]:
            doubt = f"it is for {stop_rec.get('qty')} shares, ORB holds {want['qty']} at Webull"
        elif (mode == "stop" and tgt_rec is not None) or (
                mode == "stop_target" and tgt_rec is None and want.get("target") is not None):
            doubt = f"orb_resting.mode is {mode!r}"
        elif tgt_rec is not None and want.get("target") is not None and \
                abs(float(tgt_rec.get("limit_price") or 0) - want["target"]) >= 0.005:
            doubt = f"its target is not the engine's {want['target']:.2f}"
        else:
            plan = adapter.resting_plan(BROKER_SYMBOL, want["direction"], want["qty"])
            side = (plan or {}).get("side") if isinstance(plan, dict) else None
            if isinstance(plan, dict) and not plan.get("error") and side != stop_rec.get("side"):
                doubt = f"its side {stop_rec.get('side')} no longer fits the account net {plan.get('net')}"
        if doubt:
            if _market_closed_for_orders(nowdt):
                return
            _resting_cancel(state, blk, adapter, doubt, nowdt, log=log)
            blk["resting"] = _resting_summary(_resting_live(adapter)) or None
            return
        if abs(float(stop_rec.get("stop_price") or 0) - want["stop"]) >= 0.005:
            gate = _resting_arm_gate(state, cfg, adapter, lot, nowdt, active)
            key = _resting_try_key(want)
            if gate and gate.startswith("outside"):
                _resting_note(state, blk, "wait", f"the engine stop moved to {want['stop']:.2f} but "
                              f"{gate}; the resting stop stays at {stop_rec.get('stop_price')}",
                              nowdt, log=log)
            elif _resting_tries_ok(blk, key, time.time()):
                res = _resting_call("replace", RESTING_REPLACE_HARD_TIMEOUT_SEC,
                                    adapter.replace_resting, stop_rec.get("group"), log=log,
                                    stop_price=want["stop"], last_price=px) or {}
                _book_resting_fills(state, adapter, nowdt, log=log)
                out = res.get("outcome")
                if out in ("REPLACED", "REARMED"):
                    _resting_count(blk, "replaced" if out == "REPLACED" else "rearmed")
                    (blk.get("tries") or {}).pop(key, None)
                    _resting_note(state, blk, "replace", f"stop moved to {want['stop']:.2f} "
                                  f"({out.lower()}: {res.get('reason')})", nowdt, log=log)
                elif out == "CROSSED":
                    _resting_count(blk, "crossed")
                    _resting_market_close(state, lot, want["qty"], want["stop"],
                                          f"the live price {px} was already through the new stop "
                                          f"{want['stop']:.2f}", nowdt, log=log)
                    _resting_note(state, blk, "crossed", f"the live price {px} is already through "
                                  f"the new stop {want['stop']:.2f} -- sent ORB's market close",
                                  nowdt, log=log)
                elif out in ("FILLED", "NOT_LIVE"):
                    _resting_note(state, blk, "replace", f"stop move: {res.get('reason')}",
                                  nowdt, log=log)
                elif out == "BUSY":
                    _resting_note(state, blk, "wait", f"stop move waits: {res.get('reason')}",
                                  nowdt, log=log)
                elif out == "RATE_LIMITED":
                    _resting_rate_limited(state, blk, key, f"stop move: {res.get('reason')}",
                                          nowdt, log=log)
                else:
                    _resting_try_failed(state, blk, key, f"stop move {out}: {res.get('reason')}",
                                        nowdt, log=log)
            blk["resting"] = _resting_summary(_resting_live(adapter)) or None
            return
        # healthy: one lookup (the leg the live price is through first -- a likely fill)
        through = _resting_crossed(want["direction"], px, float(stop_rec.get("stop_price") or 0),
                                   float(tgt_rec["limit_price"]) if tgt_rec else None)
        pick = (stop_rec if through == "stop" else tgt_rec if through == "target" else None)
        if _resting_lookup_due(state, blk, live, pick):
            blk["looked_at"] = time.time()
            _resting_call("lookup", RESTING_RESOLVE_HARD_TIMEOUT_SEC, adapter.resolve_resting,
                          pick.get("client_order_id") if pick else None, log=log)
        _book_resting_fills(state, adapter, nowdt, log=log)
        blk["resting"] = _resting_summary(_resting_live(adapter)) or None
        if blk["resting"]:
            _resting_note(state, blk, "resting", f"resting {_resting_desc(want, stop_rec.get('side'))}",
                          nowdt, log=log, event=False)
        return
    # nothing live: arm when every condition holds
    if not lot:
        _resting_note(state, blk, "idle", "no ORB trade open", nowdt, log=log, event=False)
        return
    if want is None or lot.get("broker_closed"):
        _resting_note(state, blk, "idle", want_why if want is None else
                      "ORB is already closed at Webull", nowdt, log=log, event=False)
        return
    gate = _resting_arm_gate(state, cfg, adapter, lot, nowdt, active)
    if gate:
        _resting_note(state, blk, "wait", f"nothing rests -- {gate}", nowdt, log=log)
        return
    if want["qty"] <= 0:
        _resting_note(state, blk, "wait", "nothing rests -- ORB holds no confirmed shares at "
                      "Webull", nowdt, log=log)
        return
    key = _resting_try_key(want)
    if not _resting_tries_ok(blk, key, time.time()):
        return
    crossed = _resting_crossed(want["direction"], px, want["stop"], want.get("target"))
    if crossed:
        _resting_count(blk, "crossed")
        level = want["stop"] if crossed == "stop" else want["target"]
        _resting_market_close(state, lot, want["qty"], level,
                              f"the live price {px:.2f} was already through the {crossed} "
                              f"{level:.2f}", nowdt, log=log)
        _resting_note(state, blk, "crossed", f"the live price {px:.2f} is already through ORB's "
                      f"{crossed} {level:.2f} -- sent ORB's market close", nowdt, log=log)
        return
    blk["looked_at"] = time.time()
    res = _resting_call("place", RESTING_PLACE_HARD_TIMEOUT_SEC, adapter.place_resting, log=log,
                        leg=RESTING_LEG, trade_id=want["trade_id"], symbol=BROKER_SYMBOL,
                        direction=want["direction"], qty=want["qty"],
                        stop_price=want["stop"], limit_price=want.get("target"),
                        last_price=px) or {}
    out = res.get("outcome")
    _book_resting_fills(state, adapter, nowdt, log=log)
    if out == "RESTING":
        first = int(res.get("n") or 1) <= 1
        _resting_count(blk, "armed" if first else "rearmed")
        (blk.get("tries") or {}).pop(key, None)
        _resting_note(state, blk, "arm" if first else "rearm",
                      f"{'armed' if first else 're-armed'} {_resting_desc(want, res.get('side'))} "
                      f"(account net {res.get('net'):g}, id {res.get('group')})", nowdt, log=log)
    elif out == "CROSSED":
        _resting_count(blk, "crossed")
        level = want["stop"] if res.get("crossed") != "target" else want["target"]
        _resting_market_close(state, lot, want["qty"], level, res.get("reason") or "crossed",
                              nowdt, log=log)
        _resting_note(state, blk, "crossed", f"{res.get('reason')} -- sent ORB's market close",
                      nowdt, log=log)
    elif out == "CROSSING":
        if _resting_note_once(state, blk, f"crossing:{want['trade_id']}",
                              f"ORB's stop NOT rested -- {res.get('reason')}; ORB exits on the "
                              f"engine's bar close", nowdt, log=log):
            _resting_count(blk, "crossing")
        _resting_note(state, blk, "wait", f"nothing rests -- {res.get('reason')}", nowdt, log=log,
                      event=False)
    elif out in ("BUSY", "BLOCKED"):
        _resting_note(state, blk, "wait", f"nothing rests yet -- {res.get('reason')}", nowdt,
                      log=log)
    elif out in ("FILLED", "DEAD"):
        _resting_note(state, blk, "arm", f"resting send settled {out}: {res.get('reason')}",
                      nowdt, log=log)
    elif out == "RATE_LIMITED":
        _resting_rate_limited(state, blk, key, res.get("reason"), nowdt, log=log)
    else:
        _resting_try_failed(state, blk, key, f"{out}: {res.get('reason')}", nowdt, log=log)
    blk["resting"] = _resting_summary(_resting_live(adapter)) or None


def _maybe_manage_resting(state, cfg, nowdt, active, log=print):
    """RESTING ORB STOP, once per tick after fill capture -- see the section comment.
    "off" does nothing at all (after cancelling anything a stop mode left resting);
    "log_only" decides and publishes, sending nothing; the stop modes arm, move, re-arm or
    cancel ORB's resting order and book its fills. While an earlier resting call to Webull
    is still running (or one timed out moments ago -- _resting_busy) the step skips itself,
    so a hung SDK call can never freeze the tick. Never raises."""
    mode = _orb_resting_mode(cfg)
    try:
        if mode == "off":
            if "orb_resting" in state and _send_inflight_future() is None:
                if _resting_disarm(state, cfg, mode, nowdt, log=log):
                    state.pop("orb_resting", None)
            return
        blk = _resting_block(state, mode, nowdt)
        _resting_hang_alert(state, log=log)
        if _send_inflight_future() is not None:
            return   # the adapter lock is held by a send; next tick
        if _resting_busy() and (mode in RESTING_STOP_MODES or blk.get("live_seen")):
            return   # an earlier resting call is still out; its outcome is read next tick
        if mode not in RESTING_STOP_MODES:
            # log_only touches the adapter only while ORB holds a trade, or while a stop
            # mode's resting order may still be live (live_seen) -- an idle tick costs nothing
            if not (state.get("legs") or {}).get(RESTING_LEG) and not blk.get("live_seen"):
                blk["resting"] = None
                _resting_note(state, blk, "idle", "no ORB trade open", nowdt, log=log, event=False)
                return
            adapter = _get_broker_adapter(log=log)
            if blk.get("live_seen") and _resting_disarm(state, cfg, mode, nowdt, log=log):
                blk.pop("live_seen", None)
            _resting_log_only(state, cfg, adapter, blk, nowdt, active, log=log)
            return
        adapter = _get_broker_adapter(log=log)
        blk["live_seen"] = True
        _book_resting_fills(state, adapter, nowdt, log=log)
        _resting_live_step(state, cfg, adapter, blk, nowdt, active, mode, log=log)
    except _RestingCallPending as e:
        log(f"[qqq-exec] resting ORB stop step paused (non-fatal -- ORB keeps its engine "
            f"exit): {e}")
    except Exception as e:
        log(f"[qqq-exec] resting ORB stop step failed (non-fatal -- ORB keeps its engine "
            f"exit): {type(e).__name__}: {e}")


def _build_resting_status(cfg, state):
    """doc["orb_resting"]: {mode, day, resting (live orders in the stop modes / what would
    rest in log_only), last {at, kind, text}, counts}; None in "off". Never raises."""
    try:
        mode = _orb_resting_mode(cfg)
        if mode == "off":
            return None
        blk = state.get("orb_resting") or {}
        resting = blk.get("resting")
        if isinstance(resting, dict):
            resting = {k: resting.get(k) for k in ("trade_id", "side", "qty", "stop", "target",
                                                   "net", "desc")}
        return {"mode": mode, "day": blk.get("day"), "resting": resting,
                "last": blk.get("last"), "counts": dict(blk.get("counts") or {})}
    except Exception:
        return None


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
    NinjaTrader mode's two independent feeds.

    FEED HEALTH (2026-10-05, sweep findings 6 + 15) -- DECIDED: this gate still reads only
    the heartbeat's age and `ok`. The engine now also writes `stalled` / `verdict` (no new
    closed bar for two bars + 60 s when one was due), bar_age_s and bars_missing, and pushes
    that itself, once per episode. `ok` deliberately keeps its old meaning ("the step ran"):
    turning a frozen bar tail into ok=false here would block every new entry and count the
    minutes as feed downtime off a heuristic, when a frozen tail produces no entry anyway,
    and would double the page this function already sends for an open lot."""
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
        # item 1 (2026-09-26, "alerts in book"): a stall while the book holds an open
        # lot is the dangerous case -- neither a fresh ENTRY nor a SIGNAL-DRIVEN exit can
        # reach this adapter until the heartbeat recovers. The end-of-day flatten, KILL
        # file and daily-loss breaker are rail-driven, not signal-driven, and keep working
        # the whole time; the wording below (item 6, 2026-09-26 minor review) must never
        # claim otherwise. WEBULL PUSH PLAN 10-07 (MANAGER #86, group I): NO PUSH from here
        # -- ONE ALERTER PER PROBLEM: the box monitor (tools/webull_freshness.py engine_hb, a
        # separate process that pages a stall lot or no lot, and its one "OK" after) owns
        # the phone. This keeps the log line and a timeline event naming the open lots.
        if state.get("legs"):
            legs_txt = ", ".join(sorted(state["legs"].keys()))
            held_txt = ", ".join(sorted(leg for leg, lot in state["legs"].items()
                                        if isinstance((lot or {}).get("hold"), dict)
                                        or leg in HOLD_OVERNIGHT_LEGS))
            msg = (f"QQQ SIGNAL ENGINE STALLED with an open lot held ({legs_txt}) -- "
                  f"new entries and signal-driven exits are blocked until the heartbeat "
                  f"recovers; the end-of-day flatten, KILL and breaker still work"
                  + (f" (the end-of-day flatten does not close {held_txt}: it holds "
                     f"overnight until its own exit)" if held_txt else ""))
            log(f"[qqq-exec] {msg}")
            _log_event(state, "signal_stall", msg, log=log)
    elif was and not stale:
        log("[qqq-exec] engine heartbeat recovered")
        state["relaunch_at"] = _now_et().strftime("%Y-%m-%d %H:%M:%S")
        _log_event(state, "feed_up", "cloud_signal engine heartbeat recovered", log=log)
        state.pop("_signal_stall_alerted", None)      # the retired push's memory
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


def _engine_leg_cfg(cs, cs_key):
    """cloud_signal's cfg for an engine key -- CROWN_LEGS first, then SHADOW_LEGS. Used ONLY
    for the key's timeframe (its bar cache, its bar width). ENGUQ_335 resolves from
    CROWN_LEGS again since 2026-10-09 (live again, OWNER DECISION); the SHADOW_LEGS fallback
    -- added 2026-09-28 while it was a shadow leg -- only matters for an exec leg whose every
    engine key is off the live book, so a leftover lot can still be marked and flattened and
    an old order row keeps its after-close latency. It never makes a shadow leg's signals
    reach this module -- those live in a ledger this module never reads for orders (its one
    read is the display-only shadow_trades block, _build_shadow_trades). None for no key."""
    if not cs_key:
        return None
    return cs.CROWN_LEGS.get(cs_key) or (getattr(cs, "SHADOW_LEGS", None) or {}).get(cs_key)


def _engine_mark_price(leg, log=print):
    """(qqq_px, source) for marking/closing an OPEN leg when signal_source == 'engine' --
    the newest CLOSED bar close from api.cloud_signal's own on-disk cache (Webull bar if
    that is what produced it, else yfinance -- see cloud_signal.read_bar_source), never
    NQ. (None, None) if that leg's cache is empty -- callers then leave the lot
    unmarked/unclosed, exactly like NinjaTrader mode's 'no quote/ratio available' case."""
    try:
        cs = _cs_module()
        cs_key = _engine_key_for_leg(leg, cs)
        cfg_leg = _engine_leg_cfg(cs, cs_key)
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


# EXIT SAFETY item 6 (2026-09-26): an EOD/forced (flat_by, KILL, BREAKER) exit in
# engine mode used to price ONLY off the newest closed engine bar (_engine_mark_price),
# which can be stale by several minutes on a 5m leg -- 2026-09-25's NOISE EOD exit was
# booked at the 15:55 bar close (744.92) at 15:59:03 while Webull actually filled
# 744.60 and the 1m tape read 744.45. Prefer the live Webull stream's own last trade
# print when it is genuinely fresh; otherwise fall back to the bar close exactly as
# before.
EXIT_LIVE_PRICE_MAX_AGE_SEC = 15.0


def _exit_price_for_leg(leg, log=print):
    """(qqq_px, source) for an END-OF-DAY/forced exit in engine mode -- see
    EXIT_LIVE_PRICE_MAX_AGE_SEC's own comment. `source` is 'live_stream' when the live
    print was used, else whatever _engine_mark_price itself returns ('engine_cache'/
    'engine_yfinance'/...) -- carried through to the closed trade's own exit_reason
    (TRADE_COLS has no dedicated price-source column, see _close_all) so a forced exit
    always says which price closed it. Never raises; falls back to _engine_mark_price
    on any stream error."""
    try:
        streamer = _qqq_stream_instance()
        if streamer is not None and streamer.is_fresh():
            t = streamer.last_trade()
            if t and t.get("price") is not None:
                age = float(t.get("age") or 0.0)
                if age <= EXIT_LIVE_PRICE_MAX_AGE_SEC:
                    return float(t["price"]), "live_stream"
    except Exception as e:
        log(f"[qqq-exec] live-stream exit price read failed for {leg} (falling back to "
            f"the bar close): {type(e).__name__}: {e}")
    return _engine_mark_price(leg, log=log)


def _leg_timeframe_seconds(leg, log=print):
    """Seconds in ONE bar of this EXEC leg's own LIVE engine timeframe (ORB/NOISE 5m,
    ENGUQ 1m today) -- read from api.cloud_signal.CROWN_LEGS via _engine_key_for_leg/
    ENGINE_LEG_MAP, never hard-coded, so a future leg swapped onto a different
    timeframe (like the 2026-09-24 NOISE_304 -> NOISE_382 swap) is picked up here
    automatically. None for a leg with no live engine mapping."""
    try:
        cs = _cs_module()
        cs_key = _engine_key_for_leg(leg, cs)
        cfg_leg = _engine_leg_cfg(cs, cs_key)
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
    # RESTING ORB STOP (2026-09-29): LEVELS rows (the engine's breakeven move) are only
    # consumed while orb_resting.mode is not "off" -- "off" skips them exactly as before.
    actionable = ("ENTRY", "EXIT") + (("LEVELS",) if _orb_resting_mode(cfg) != "off" else ())
    for r in new_rows:
        ev = str(r.get("event") or "").strip().upper()
        if ev not in actionable:
            continue  # SEED and any future non-actionable event types
        age = None
        try:
            emitted = datetime.fromisoformat(str(r["emitted_at"]))
            now_cmp = now.replace(tzinfo=None) if now.tzinfo else now
            emitted_cmp = emitted.replace(tzinfo=None) if emitted.tzinfo else emitted
            age = (now_cmp - emitted_cmp).total_seconds()
        except Exception:
            age = None
        # a LEVELS row (the breakeven move) is a state update, not a trade decision: it
        # still applies late (a restart) -- _apply_engine_levels only takes it for the
        # open trade with the same trade id, and the resting stop then follows it
        # HOLD OVERNIGHT: the EXIT of an open lot on a leg that holds overnight is never too
        # old -- held already or not yet (a same-day exit consumed late): the flat_by flatten
        # keeps that lot, so its own exit is the only thing that can close it (and free its
        # leg for new entries). A late one is tagged "late": _route_engine_events then sells
        # it at a price from now, never at the row's own old price.
        late = age is not None and age > ENGINE_CONSUME_STALE_SEC and ev != "LEVELS"
        held_exit = False
        if ev == "EXIT":
            xleg = ENGINE_LEG_MAP.get(r.get("leg"))
            hl = (state.get("legs") or {}).get(xleg)
            xtid = str(r.get("trade_id") or "").strip()
            held_exit = bool(hl and xtid and xtid == hl.get("trade_id")
                             and (isinstance(hl.get("hold"), dict) or xleg in _hold_legs(cfg)))
        if late and not held_exit:
            log(f"[qqq-exec] engine {ev} {r.get('leg')} consumed {age/60:.0f} min after "
                f"it was emitted -- too stale to act on, recorded only")
            _log_event(state, "engine_stale_skip",
                      f"{r.get('leg')} {ev} skipped -- consumed {age/60:.0f} min late", log=log)
            continue
        try:
            # The ledger's own `shares` column is NOTIONAL ($100k / price, ~135 QQQ
            # shares -- parity audit 2026-09-28) and deliberately NOT carried: the book
            # trades cfg shares x size (see _open_lot / _sized_shares), and nothing
            # downstream of this -- the order path, the published doc, the web tab --
            # may read it as a live size.
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
                       "size": r.get("size"),
                       # KEEL OVERLAY (2026-09-25 fix): raw signals.csv value, unparsed --
                       # this was missing here, so an engine ENTRY's own keel_size never
                       # reached _route_engine_events (which already forwards it to
                       # _open_lot) or the trade row (TRADE_COLS' "keel_size" -- the web
                       # drawer's "#382 x KEEL" display). DISPLAY ONLY: never fed into an
                       # order quantity -- see _resolve_keel_size vs _resolve_entry_size.
                       "keel_size": r.get("keel_size"),
                       # decide_at_close probe rows say so here (see _route_engine_events)
                       "reason": r.get("reason") or ""})
            # RESTING ORB STOP (2026-09-29): the engine's cent levels (api/cloud_signal.py
            # writes them on the resting leg's ENTRY and LEVELS rows only) -- carried only
            # when present, so every other row's event dict is unchanged.
            for k in ("stop_px", "target_px"):
                v = _finite_or_none(r.get(k))
                if v is not None:
                    out[-1][k] = v
            if late:
                out[-1]["late"] = True   # HOLD OVERNIGHT: a hold leg's exit consumed late
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


def _late_entry_reason(nowdt, sig_dt, sess):
    """None, or why an engine ENTRY is too late to open (LATE-ENTRY GUARD, 2026-09-28).
    Engine mode had no entry-window check at all (only ninjatrader mode's
    _in_entry_window): a row consumed after the day's flatten opened a lot nothing would
    close that day, and one consumed after the bell mirrored an OPEN Webull refuses.
    Judged by the signal's OWN bar: refused when that bar starts after
    session.last_entry. The consumption time only has hard stops -- at/after the session
    close, past flat_by, or inside the last minute before flat_by (so the entry's market
    order has filled before the flatten's close goes out). 2026-09-28 review: the first
    version also refused by the consumption minute (> last_entry), which dropped an
    entry decided at the 15:50 bar's close whenever the fetch throttle plus REST latency
    (or one failed fetch) pushed its consumption past 15:55:59 -- the backtest takes it.
    Never raises (any doubt reads as not late)."""
    try:
        last_entry = sess.get("last_entry", "15:55")
        flat_by = sess.get("flat_by", "15:58")
        if _market_closed_for_orders(nowdt):
            return "consumed after the session close"
        if _past_flat_by(nowdt, sess):
            return f"consumed past flat_by {flat_by}"
        if _et_hhmm(nowdt) >= _hhmm(_hhmm_minus(flat_by, 1)):
            return f"consumed inside the last minute before flat_by {flat_by}"
        if sig_dt is not None:
            bar = sig_dt.astimezone(_NY) if (sig_dt.tzinfo is not None and _NY is not None) else sig_dt
            if _et_hhmm(bar) > _hhmm(last_entry):
                return f"its bar ({bar.strftime('%H:%M')}) is after last_entry {last_entry}"
    except Exception:
        return None
    return None


def _entry_not_taken_line(leg, side, sig_dt, ref_time, why, trade_id=""):
    """The ONE plain log line for an engine ENTRY the session window refused
    (_late_entry_reason -- the market is closed for new entries): which strategy, which
    side, the signal's own bar time, and why, e.g.
    "[qqq-exec] ENGU-Q long signal at 15:57 ET on 2026-10-09 not taken: the market is
    closed for new entries -- its bar (15:57) is after last_entry 15:55. No order sent."
    Never raises."""
    try:
        if sig_dt is not None:
            bar = sig_dt.astimezone(_NY) if (sig_dt.tzinfo is not None and _NY is not None) else sig_dt
            at = f"{bar.strftime('%H:%M')} ET on {bar.strftime('%Y-%m-%d')}"
        else:
            at = f"bar {ref_time or '?'}"
        return (f"[qqq-exec] {_leg_word(leg)} {side} signal at {at} not taken: the market is "
                f"closed for new entries -- {why}. No order sent."
                + (f" ({trade_id})" if trade_id else ""))
    except Exception:
        return f"[qqq-exec] {leg} {side} signal ({ref_time}) not taken -- {why}. No order sent."


BACKTEST_EOD_EXITS_KEEP = 60


def _note_backtest_eod_exit(state, leg, trade_id, e, nowdt, log=print):
    """EOD SETTLE (2026-09-28): api/cloud_signal.py now emits the backtest's end-of-day
    EXIT right after the close. For a trade the day's flatten already closed there is
    nothing to do at the broker -- the engine's exit price is kept (state
    "backtest_eod_exits", merged onto that trade's published row by
    _merge_backtest_exits) so the book's flatten fill can be compared with the backtest's
    own close. No order, no warning. Never raises."""
    try:
        book = state.setdefault("backtest_eod_exits", {})
        book[trade_id] = {"leg": leg, "px": float(e["ref_price"]),
                          "ts": str(e.get("ref_time") or ""),
                          "at": nowdt.strftime("%Y-%m-%d %H:%M:%S")}
        for old in list(book)[:-BACKTEST_EOD_EXITS_KEEP]:
            book.pop(old, None)
        log(f"[qqq-exec] {leg} backtest end-of-day exit for {_trade_id.describe(trade_id, _NY)} "
            f"@ {float(e['ref_price']):.2f} (bar {e.get('ref_time')}) -- the day's flatten "
            f"already closed it; recorded for comparison, nothing sent")
    except Exception as ex:
        log(f"[qqq-exec] backtest end-of-day exit not recorded for {leg}: "
            f"{type(ex).__name__}: {ex}")


def _merge_backtest_exits(trades_all, state):
    """Adds backtest_exit_px / backtest_exit_ts to each published trade row whose trade id
    has a _note_backtest_eod_exit record. Additive fields only. Never raises."""
    try:
        book = (state or {}).get("backtest_eod_exits") or {}
        if not book:
            return
        for row in trades_all:
            rec = book.get(str(row.get("trade_id") or "").strip())
            if rec:
                row["backtest_exit_px"] = rec.get("px")
                row["backtest_exit_ts"] = rec.get("ts")
    except Exception:
        pass


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
        # api/cloud_signal.py's DECIDE_AT_CLOSE_TAG: decided at the close of the bar before
        # ref_time -- latency only (see _record_order); nothing is priced or refused on it.
        decided_at_ref = "decide_at_close" in str(e.get("reason") or "")
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
                    if (leg in _hold_legs(cfg) or isinstance(open_lot.get("hold"), dict)) \
                            and not isinstance(open_lot.get("close_pending"), dict):
                        # HOLD OVERNIGHT: the strategy holds one trade at a time, so a new
                        # entry while the book still holds its lot means that trade's exit
                        # was missed -- the flatten no longer closes it, so say so (not when
                        # its exit is known and only waits for a price or the open)
                        _say_held_exit_missed(state, leg, open_lot, today, log=log)
                continue
            shares = int(cfg["shares"].get(leg, 0))
            too_late = _late_entry_reason(nowdt, sig_dt, cfg.get("session") or {})
            if too_late:
                # LATE-ENTRY GUARD (2026-09-28): an entry opened now could only be flattened
                # by nothing (flat_by has run) or sent after the bell -- never opened.
                # 2026-10-09 (ENGU-Q live again): the orders.csv row is unchanged; the log
                # gets ONE plain line naming the strategy, side, signal time and why
                # (_entry_not_taken_line) instead of the row's generic "ENTER ... @ None".
                _record_order(leg, "ENTER", e["side"], shares, None, None, None,
                             f"REFUSED -- {too_late}", log, fill_dt=sig_dt,
                             signal_source=cfg.get("signal_source"), decided_at_ref=decided_at_ref,
                             quiet=True)
                log(_entry_not_taken_line(leg, e["side"], sig_dt, e.get("ref_time"), too_late,
                                          row_tid))
                _accumulate_signal(state, sig_dt or _now_et(), leg, "fired", log=log)
                _accumulate_signal(state, sig_dt or _now_et(), leg, "refused", log=log)
                _log_event(state, "entry_too_late",
                           f"{leg} entry signal ({_trade_id.describe(row_tid, _NY)}) not taken "
                           f"-- {too_late}", log=log)
                continue
            if entries_blocked:
                _record_order(leg, "ENTER", e["side"], shares, None, None, None,
                             "REFUSED -- breaker/feed/kill blocked", log, fill_dt=sig_dt,
                             signal_source=cfg.get("signal_source"), decided_at_ref=decided_at_ref)
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
                               size=e.get("size"), keel_size=e.get("keel_size"), nowdt=nowdt,
                               decided_at_ref=decided_at_ref)
            if opened and leg == RESTING_LEG and e.get("stop_px") is not None \
                    and _orb_resting_mode(cfg) != "off":
                # RESTING ORB STOP (2026-09-29): the engine's own levels ride on the lot --
                # _maybe_manage_resting arms from them once the entry is FILLED at Webull
                state["legs"][leg]["levels"] = {
                    "stop_px": e["stop_px"], "target_px": e.get("target_px"),
                    "initial_stop_px": e["stop_px"], "be_armed_at": None}
            _accumulate_signal(state, sig_dt or _now_et(), leg, "fired", log=log)
            _accumulate_signal(state, sig_dt or _now_et(), leg, "taken" if opened else "refused", log=log)
        elif e["event"] == "LEVELS":
            _apply_engine_levels(state, cfg, leg, e, row_tid, open_lot, log=log)
        elif e["event"] == "EXIT":
            lot = open_lot
            exit_of = (_trade_id.describe(row_tid, _NY) if row_tid
                       else f"a trade with no id (exit bar {e.get('ref_time')})")
            if not lot:
                if row_tid and state.get("flat_by_done_date") == today \
                        and _past_flat_by(nowdt, cfg.get("session") or {}):
                    # EOD SETTLE (2026-09-28): the backtest's own end-of-day exit of a trade
                    # the day's flatten already closed -- expected, not an identity problem.
                    _note_backtest_eod_exit(state, leg, row_tid, e, nowdt, log=log)
                    continue
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
            hold_lot = isinstance(lot.get("hold"), dict) or leg in _hold_legs(cfg)
            if hold_lot and _outside_regular_hours(nowdt):
                # HOLD OVERNIGHT: a held lot's exit outside regular hours (the end-of-day
                # settle row after the bell, a late row consumed before 09:30) keeps the
                # lot; the first tick from the next open sells it at market
                _defer_held_close(state, cfg, leg, "signal exit", nowdt, log=log,
                                  px=float(e["ref_price"]), trade_id=row_tid)
                continue
            if hold_lot and _held_exit_px_is_old(lot, e, sig_dt, today):
                # HOLD OVERNIGHT: the exit's own price is not a price from now -- the row was
                # consumed late (a same-day exit after a restart or a wedge), or a carried
                # lot's exit is stamped with an earlier session's bar (a settle row written at
                # the next morning's first step, a restart that consumed yesterday's
                # after-bell exit after 09:30). Booked at that price, the overnight gap would
                # land on the daily loss rail and the trade would record a P&L Webull never
                # had: the next tick sells it at market at a price from today
                # (_run_deferred_held_closes, which waits for one until 09:35 at most).
                _defer_held_close(state, cfg, leg, "signal exit", nowdt, log=log,
                                  px=float(e["ref_price"]), trade_id=row_tid, late=True)
                continue
            state["_px_source"] = px_source
            # an EOD SETTLE row (api/cloud_signal.py, after the close) closing a lot the
            # flatten could not price: the shadow closes at the backtest's own price; the
            # broker mirror is refused by _mirror_to_broker's AFTER-CLOSE GUARD
            exit_reason = ("EOD settle (backtest)" if "eod_settle" in str(e.get("reason") or "")
                           else "signal exit")
            _reduce_lot(state, cfg, leg, lot["nq_qty_total"], None, float(e["ref_price"]),
                       cfg.get("slippage_per_share", 0.0), exit_reason, f=None, log=log,
                       sig_dt=sig_dt, signal_source=cfg.get("signal_source"), nowdt=nowdt,
                       decided_at_ref=decided_at_ref)


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
              keel_size=None, nowdt=None, decided_at_ref=False):
    """Returns True if a shadow lot opened, False if refused/skipped (feature #55 needs
    to know this to tell TAKEN from REFUSED).

    `nowdt` (EXIT SAFETY item 4 minor, 2026-09-26 review): the calling tick's own
    notion of "now", threaded straight through to _mirror_to_broker -- see that
    function's own docstring.

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
                              fill_dt=(f.get("dt") if f else sig_dt), signal_source=signal_source,
                              decided_at_ref=decided_at_ref)
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
                 signal_source=signal_source, shares_wanted=wanted_shares, size=sized,
                 decided_at_ref=decided_at_ref)
    # WEBULL PUSH PLAN 10-07, group F: a fill is a low note (no buzz)
    _say(state, f"fill:{leg}", f"open {lot.get('trade_id') or lot.get('entry_ts')}",
         _fill_note(leg, "bought" if side == "long" else "sold short",
                    f"{'Bought' if side == 'long' else 'Sold short'} QQQ at "
                    f"{ntfy_push.price(fill_px)} (share count stays on the board)"), log=log)
    # BROKER MIRROR: after the shadow's own order is already recorded above -- see the
    # "broker mirror" section docstring near _mirror_to_broker. A broker error here
    # never unwinds the shadow lot just opened.
    _mirror_to_broker(state, leg=leg, side=side, shares=shares, shadow_px=fill_px,
                      intent="OPEN", ts=lot["entry_ts"], trade_id=lot["trade_id"],
                      nowdt=nowdt, log=log)
    return True


def _reduce_lot(state, cfg, leg, nq_qty_closed, nq_px, qqq_px_raw, slip, reason, f=None, log=print,
                sig_dt=None, signal_source=None, nowdt=None, decided_at_ref=False,
                broker_cross=None):
    """`nowdt` (EXIT SAFETY item 4 minor, 2026-09-26 review): the calling tick's own
    notion of "now", threaded straight through to _mirror_to_broker -- see that
    function's own docstring.

    `broker_cross` (2026-09-28, END-OF-DAY INTERNAL CROSS -- only _close_all passes it):
    {"crossed": n, "left": signed broker qty after the cross, "px", "id", "against"} for
    a leg whose n broker shares were already offset against another leg's (no order).
    Those shares get an allocation row (_record_internal_cross); only the rest -- at
    most what the broker still holds for this leg -- is mirrored as a CLOSE order."""
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
                 size=lot.get("size"), decided_at_ref=decided_at_ref)
    # WEBULL PUSH PLAN 10-07, group F: ONE fill note per exit -- none when the resting stop
    # already closed this lot at Webull and sent its own (lot["broker_closed"])
    if not lot.get("broker_closed"):
        long_ = lot.get("side") == "long"
        _say(state, f"fill:{leg}",
             f"close {lot.get('trade_id') or lot.get('entry_ts')} {lot['shares_remaining']}",
             _fill_note(leg, "sold" if long_ else "bought back",
                        f"{'Sold' if long_ else 'Bought back'} QQQ at "
                        f"{ntfy_push.price(fill_px)} ({_exit_reason_words(reason)})"), log=log)
    else:
        log(f"[qqq-exec] {leg} exit: no fill note -- the resting stop already reported it")
    # BROKER MIRROR: mirrors every reduce, not just a full close -- a ninjatrader-mode
    # partial exit closes only part of the broker position too. `seq` disambiguates more
    # than one reduce against the SAME lot (engine mode never needs it -- see module
    # docstring, entries/exits are single-shot there). Flat-by/EOD/KILL route through
    # here too (_close_all calls _reduce_lot), so this is also what keeps a broker
    # position from surviving past flat-by.
    lot["_broker_close_seq"] = lot.get("_broker_close_seq", 0) + 1
    broker_shares = shares_close
    crossed = int((broker_cross or {}).get("crossed") or 0)
    if crossed > 0:
        broker_shares = max(0, min(shares_close - crossed,
                                   int(round(abs(float(broker_cross.get("left") or 0))))))
        if not broker_cross.get("row_done"):   # a re-run after a crash, see _replay_internal_cross
            _record_internal_cross(state, leg=leg, side=lot["side"], shares=crossed,
                                   shadow_px=fill_px, cross=broker_cross, ts=lot["entry_ts"],
                                   seq=lot["_broker_close_seq"], trade_id=lot.get("trade_id"),
                                   partial=broker_shares > 0, log=log)
    closed_at_broker = lot.get("broker_closed")   # RESTING ORB STOP, see _book_resting_fills
    # only an ACCEPTED close skips (2026-09-29 review): a market close that was not ok
    # belongs to the close re-send queue, and if that queue gives up or drops it the
    # engine EXIT / flatten must still send ORB's close -- the adapter's nothing-to-close
    # and closed-by-resting guards already stop a double close
    if broker_shares > 0 and closed_at_broker and closed_at_broker.get("ok"):
        msg = (f"{leg} closed in the book ({reason}); "
               f"{closed_at_broker.get('note') or 'already closed at Webull by the resting stop'}"
               f" -- no market close sent")
        log(f"[qqq-exec] {msg}")
        _log_event(state, "broker", msg, log=log)
    elif broker_shares > 0:
        _mirror_to_broker(state, leg=leg, side=lot["side"], shares=broker_shares,
                          shadow_px=fill_px, intent="CLOSE", ts=lot["entry_ts"],
                          seq=lot["_broker_close_seq"], trade_id=lot.get("trade_id"),
                          nowdt=nowdt, log=log)
    pnl = None
    if lot["shares_remaining"] <= 0:
        # HOLD OVERNIGHT: a lot carried into today gets its open mark now if today's first
        # bar was not in yet (the exit price is then today's first price) and its daily
        # loss rail adjustment -- before _record_trade, which writes its overnight gap.
        # realized_pnl_today below stays the P&L of record (exit - entry).
        _finish_held_close(state, leg, lot, fill_px, nowdt=nowdt, log=log)
        # close the round-trip on the full lot's entry (weighted avg exit unnecessary
        # for a single-entry lot -- see module docstring: entries are treated single-shot)
        pnl = _record_trade(lot, fill_px, reason, log=log)
        state["realized_pnl_today"] = round(state.get("realized_pnl_today", 0.0) + pnl, 2)
        del state["legs"][leg]
    return pnl


# -- HOLD OVERNIGHT (OWNER GO 2026-10-09, MANAGER #106) -------------------------------------
# ENGU-Q (#335) holds its trade overnight, like its backtest. The flat_by flatten skips a leg
# in _hold_legs(cfg) (session.hold_overnight_legs, code default HOLD_OVERNIGHT_LEGS, engine
# mode only): its lot stays in state["legs"] -- and in the adapter's broker_sent_positions,
# which have no daily reset -- until the engine's own EXIT on a later day (api/cloud_signal.py
# emits the exit of an emitted entry on any later day), sent as an ordinary market order in
# regular hours. The lot carries a "hold" block (state.json, so a restart keeps it):
#   since           ET day the lot was first kept at the flatten
#   flat_by_day     the last flatten that kept it
#   nights          session opens it was carried into
#   close_mark_px   the prior session's last 1m bar close (where the overnight gap starts)
#   open_mark_px / open_mark_day / open_mark_src
#                   today's first price: the open of today's first 1m bar in
#                   api/cloud_signal.py's own bar cache, or the exit price when the lot
#                   closed before that bar was in
#   gap_today_usd   shares x (open - prior close) x side -- today's overnight gap
#   gap_usd         every night's gap added up (the trade's overnight_gap_usd column)
#   rail_px         today's newest 1m bar close, the daily loss rail's mark (None pre-open)
# MARK-TO-OPEN DAILY LOSS RAIL: a lot carried into today counts on the rail from today's open
# mark only -- 0 before it exists, then (mark - open) x shares x side; closed today it adds
# (exit - open). The overnight gap never reaches the rail but stays in the P&L of record
# (trades.csv pnl = exit - entry, realized_pnl_today) and is published as its own field
# (today.overnight_gap_usd, positions[leg].gap_usd). Both rail sites read the same figures:
# the book breaker (_mark_and_check_breaker, via _rail_realized_today and
# state["_rail_unrl_by_leg"]) and the adapter's daily_pnl (_compute_broker_daily_pnl, whose
# broker_orders.csv pairing is seeded with the held lot's open mark from state["held_today"]).
# HARD STOPS STAY HARD: KILL and the daily loss breaker close a held lot too -- at once inside
# regular hours. Outside them (after the bell, before 09:30, a weekend) nothing is ever sent:
# the lot stays in the book with lot["close_pending"] and the first tick from the next open
# sells it at market (_run_deferred_held_closes). A strategy EXIT for a held lot outside
# regular hours (an end-of-day settle row after the bell, or a late one consumed before
# 09:30) waits the same way. A pending KILL close is cancelled if the kill file is gone by
# the open; a pending BREAKER close still runs although breaker_tripped resets at midnight.
# The flatten's internal cross never offsets a closing leg against a held lot (the held leg
# is not in the flatten's legs at all), and next morning's netting sees the held lot through
# the account net (webull_orders._account_net), like any open leg.
_PENDING_RANK = {"KILL": 3, "BREAKER": 2, "signal exit": 1}
HELD_EXIT_REASON = "signal exit (held overnight, sold at the open)"
# A hold leg's strategy exit whose own price is not from now (consumed late, inside regular
# hours, for a lot not carried in from an earlier day) -- sold at market at a price from now.
LATE_EXIT_REASON = "signal exit (late, at market)"
_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# A close waiting for the open goes out once the book has a price from TODAY to book it at
# (the live stream, or today's first 1m bar in the engine cache) -- else the book would
# record the exit at yesterday's close and the overnight gap would leak into the rail
# through the fill shortfall. Never later than this: the market order itself needs no price.
HELD_OPEN_PRICE_WAIT_UNTIL = (9, 35)


def _held_session_marks(leg, nowdt, log=print):
    """{"prior_close", "today_open", "today_last", "src"} for a held lot at `nowdt`, read from
    api.cloud_signal's own 1m QQQ bar cache (RTH bars only; `time` = the bar's START epoch):
    prior_close = the close of the last bar before today (the prior session's last bar),
    today_open = the open of today's first bar from 09:30, today_last = the close of today's
    newest bar (the daily loss rail's mark). A value is None when the cache has no such bar;
    the whole result is None when the cache is empty or unreadable. `leg` is not used to
    pick a file (one QQQ tape for every leg) -- it is there so a test can stub per leg.
    Never raises."""
    try:
        cs = _cs_module()
        df = cs.load_cached_bars("1m", cs.DEFAULT_PATHS)
        if df is None or not len(df):
            return None
        d = nowdt.date()
        tz = _NY or timezone.utc
        day_start = datetime(d.year, d.month, d.day, tzinfo=tz).timestamp()
        open_ep = datetime(d.year, d.month, d.day, 9, 30, tzinfo=tz).timestamp()
        import pandas as pd
        t = pd.to_numeric(df["time"], errors="coerce")   # a torn row reads NaN, never raises
        prior = df[t < day_start].sort_values("time")
        today = df[(t >= open_ep) & (t < day_start + 86400)].sort_values("time")
        return {"prior_close": float(prior.iloc[-1]["close"]) if len(prior) else None,
                "today_open": float(today.iloc[0]["open"]) if len(today) else None,
                "today_last": float(today.iloc[-1]["close"]) if len(today) else None,
                "src": "engine_1m_bar"}
    except Exception as e:
        log(f"[qqq-exec] held lot marks unreadable for {leg} (rail counts it as 0 until "
            f"they are): {type(e).__name__}: {e}")
        return None


def _carried_into(lot, day):
    """True when `lot` was held at an earlier day's flatten -- carried into `day` (an ET date
    string). Never raises."""
    try:
        h = (lot or {}).get("hold")
        since = str((h or {}).get("since") or "") if isinstance(h, dict) else ""
        return bool(since and day and since < str(day))
    except Exception:
        return False


def _held_exit_px_is_old(lot, e, sig_dt, today):
    """True when a hold leg's strategy EXIT must not be booked at its own engine price: the row
    was consumed late (_consume_engine_signals tags it "late"), or the lot was carried into
    `today` and the exit's bar is from an earlier session. Never raises."""
    try:
        if e.get("late"):
            return True
        if sig_dt is None or not _carried_into(lot, today):
            return False
        d = sig_dt.astimezone(_NY) if (_NY is not None and sig_dt.tzinfo is not None) else sig_dt
        return d.strftime("%Y-%m-%d") < str(today)
    except Exception:
        return False


def _say_held_exit_missed(state, leg, lot, day, log=print):
    """A new ENTRY on a hold leg while the book still holds that leg's earlier lot: the
    strategy trades one position at a time, so that lot's own exit was missed -- and the
    flat_by flatten no longer closes a held lot. A timeline event, and one plain high note a
    day per leg ("QQQ book: CHECK NOW"). Never raises."""
    try:
        n = int(round(float((lot or {}).get("shares_remaining") or 0)))
        msg = (f"{_leg_word(leg)}'s strategy opened a new trade while the book still holds its "
               f"earlier trade {_lot_label(lot)} -- that trade's exit was missed, and the "
               f"end-of-day flatten does not close a held lot")
        log(f"[qqq-exec] WARNING: {msg}")
        _log_event(state, "held_exit_missed", msg, log=log)
        _say(state, f"held_missed:{leg}", day, ntfy_push.plain(
            PHONE_AREA, "CHECK NOW", f"{_leg_word(leg)} cannot take new trades",
            f"{_leg_word(leg)}'s strategy started a new trade, but the book still holds its "
            f"earlier {n} shares",
            "check the Webull app, then " + PHONE_ASK, priority="high"), log=log)
    except Exception as e:
        log(f"[qqq-exec] held exit-missed note failed for {leg}: {type(e).__name__}: {e}")


def _held_today(state, day):
    """state["held_today"] for `day` -- {leg: the carried lot's open mark, gap and, once it
    closed today, its rail adjustment} -- started fresh when the day changes."""
    ht = state.get("held_today")
    if not isinstance(ht, dict) or ht.get("day") != day:
        ht = state["held_today"] = {"day": day, "legs": {}}
    if not isinstance(ht.get("legs"), dict):
        ht["legs"] = {}
    return ht


def _held_shares_by_leg(state):
    """{leg: signed shares} for every lot the book holds overnight (lot["hold"] set) --
    what Webull should still hold after the close. Never raises."""
    out = {}
    try:
        for leg, lot in (state.get("legs") or {}).items():
            if isinstance((lot or {}).get("hold"), dict):
                n = int(round(float(lot.get("shares_remaining") or 0)))
                out[leg] = n if lot.get("side") == "long" else -n
    except Exception:
        pass
    return out


def _held_words(held):
    """{"ENGUQ": 10} -> "ENGU-Q long 10"."""
    return ", ".join(f"{_leg_word(leg)} {'long' if q > 0 else 'short'} {abs(int(q))}"
                     for leg, q in sorted((held or {}).items())) or "none"


def _set_open_mark(state, leg, lot, day, open_px, prior_close, src, shares=None, log=print):
    """Stamp today's open mark on a carried lot: the open mark, the prior close it is
    compared with (the last record mark when the cache had none), today's gap, the gap
    total and the nights count; noted in state["held_today"] and on the timeline. Never
    raises."""
    try:
        h = lot["hold"]
        side_mult = 1 if lot.get("side") == "long" else -1
        n = float(shares if shares is not None else (lot.get("shares_remaining") or 0))
        close_px = _finite_or_none(prior_close)
        if close_px is None:
            close_px = _finite_or_none(lot.get("mark_px"))
        op = float(open_px)
        gap = round((op - close_px) * side_mult * n, 2) if close_px is not None else 0.0
        h.update({"open_mark_px": round(op, 4), "open_mark_day": day, "open_mark_src": src,
                  "close_mark_px": round(close_px, 4) if close_px is not None else None,
                  "gap_today_usd": gap, "gap_usd": round(float(h.get("gap_usd") or 0.0) + gap, 2),
                  "nights": int(h.get("nights") or 0) + 1, "rail_px": None})
        _held_today(state, day)["legs"][leg] = {
            "trade_id": lot.get("trade_id"), "side": lot.get("side"), "shares": n,
            "open_mark_px": h["open_mark_px"], "open_mark_src": src,
            "close_mark_px": h["close_mark_px"],
            "gap_usd": gap, "closed": False, "rail_adj": 0.0}
        msg = (f"{_leg_word(leg)} held overnight: today's open mark {op:.2f}"
               + (f" (prior close {close_px:.2f}, overnight gap {ntfy_push.usd(gap)})"
                  if close_px is not None else " (prior close unknown)")
               + " -- the daily loss limit counts it from the open; the gap stays in its P&L")
        log(f"[qqq-exec] {msg}")
        _log_event(state, "held_open_mark", msg, log=log)
    except Exception as e:
        log(f"[qqq-exec] held lot open mark not set for {leg}: {type(e).__name__}: {e}")


def _refresh_held_marks(state, nowdt, log=print):
    """Each tick: for every lot carried into today, from 09:30 on a session day, take today's
    open mark once (_set_open_mark) and today's newest 1m bar close as the rail's mark
    (hold["rail_px"]). Before the open, on a weekend or a holiday the rail mark is None --
    the lot counts 0 on the daily loss rail. Reads the bar cache at most once per lot per
    tick. Never raises."""
    try:
        if nowdt is None:
            return
        day = nowdt.strftime("%Y-%m-%d")
        carried = [(leg, lot) for leg, lot in (state.get("legs") or {}).items()
                   if _carried_into(lot, day)]
        if not carried:
            return
        open_now = market_calendar.is_session(nowdt) and _et_hhmm(nowdt) >= (9, 30)
        stamp = nowdt.strftime("%Y-%m-%d %H:%M:%S")
        for leg, lot in carried:
            h = lot["hold"]
            if not open_now:
                if h.get("open_mark_day") != day:
                    h["rail_px"] = None
                continue
            if h.get("_marks_at") == stamp:
                continue
            h["_marks_at"] = stamp
            marks = _held_session_marks(leg, nowdt, log=log)
            if not marks:
                continue
            if h.get("open_mark_day") != day and marks.get("today_open") is not None:
                _set_open_mark(state, leg, lot, day, marks["today_open"],
                               marks.get("prior_close"), marks.get("src") or "engine_1m_bar",
                               log=log)
            if h.get("open_mark_day") == day and marks.get("today_last") is not None:
                h["rail_px"] = round(float(marks["today_last"]), 4)
    except Exception as e:
        log(f"[qqq-exec] held lot marks refresh failed (non-fatal): {type(e).__name__}: {e}")


def _rail_unrl_for_lot(lot, day, record_unrl):
    """The daily loss rail's open P&L for one lot: the record mark (`record_unrl`, from the
    entry) for a lot opened today; for a lot carried into `day`, (rail mark - open mark) x
    shares x side once today's open mark exists, else 0.0. Never raises."""
    try:
        if not _carried_into(lot, day):
            return record_unrl
        h = lot["hold"]
        if h.get("open_mark_day") != day:
            return 0.0
        op, px = _finite_or_none(h.get("open_mark_px")), _finite_or_none(h.get("rail_px"))
        if op is None or px is None:
            return 0.0
        side_mult = 1 if lot.get("side") == "long" else -1
        return (px - op) * side_mult * float(lot.get("shares_remaining") or 0)
    except Exception:
        return record_unrl


def _rail_realized_today(state):
    """Today's realized P&L as the daily loss rail counts it: realized_pnl_today (the P&L of
    record) plus, for each lot carried into today that closed today, its rail adjustment
    (entry - open mark) x shares x side -- so that trade counts exit - open mark. NaN stays
    NaN (see the breaker's published figure). Never raises."""
    try:
        r = state.get("realized_pnl_today", 0.0)
        r = float(r if r is not None else 0.0)
    except (TypeError, ValueError):
        r = 0.0
    try:
        ht = state.get("held_today")
        if isinstance(ht, dict) and ht.get("day") == state.get("trading_day"):
            r += sum(float((v or {}).get("rail_adj") or 0.0)
                     for v in (ht.get("legs") or {}).values() if (v or {}).get("closed"))
    except Exception:
        pass
    return r


def _overnight_gap_today(state, day):
    """Today's overnight gap over every lot carried into today (open or closed since). Never
    raises."""
    try:
        ht = state.get("held_today")
        if isinstance(ht, dict) and ht.get("day") == day:
            return round(sum(float((v or {}).get("gap_usd") or 0.0)
                             for v in (ht.get("legs") or {}).values()), 2)
    except Exception:
        pass
    return 0.0


def _held_carry_closed_today(state, day):
    """For each lot carried into `day` that closed today: what it had made by the prior close,
    (close mark - entry) x shares x side, added up -- the part of today's P&L of record that
    belongs to earlier days (today.held_carry_usd; the board's today line leaves it out, as it
    does for a carried lot still open). Never raises."""
    try:
        ht = state.get("held_today")
        if not (isinstance(ht, dict) and ht.get("day") == day):
            return 0.0
        tot = 0.0
        for v in (ht.get("legs") or {}).values():
            v = v or {}
            if not v.get("closed"):
                continue
            cm, ep = _finite_or_none(v.get("close_mark_px")), _finite_or_none(v.get("entry_px"))
            if cm is None or ep is None:
                continue
            side_mult = 1 if v.get("side") == "long" else -1
            tot += (cm - ep) * side_mult * float(v.get("shares") or 0)
        return round(tot, 2)
    except Exception:
        return 0.0


def _finish_held_close(state, leg, lot, fill_px, nowdt=None, log=print):
    """_reduce_lot's last close of a lot carried into today: takes today's open mark from
    the exit price when today's first bar was not in yet (gap = exit - prior close), then
    notes the rail adjustment in state["held_today"]. Never raises."""
    try:
        day = state.get("trading_day")
        if not _carried_into(lot, day):
            return
        h = lot["hold"]
        n = float(lot.get("shares_total") or 0)
        if h.get("open_mark_day") != day or _finite_or_none(h.get("open_mark_px")) is None:
            marks = _held_session_marks(leg, nowdt or _now_et(), log=log)
            _set_open_mark(state, leg, lot, day, fill_px, (marks or {}).get("prior_close"),
                           "exit", shares=n, log=log)
        op = float(h["open_mark_px"])
        side_mult = 1 if lot.get("side") == "long" else -1
        rec = _held_today(state, day)["legs"].setdefault(leg, {
            "trade_id": lot.get("trade_id"), "side": lot.get("side"), "shares": n,
            "open_mark_px": h.get("open_mark_px"), "close_mark_px": h.get("close_mark_px"),
            "gap_usd": h.get("gap_today_usd") or 0.0})
        rec.update({"closed": True, "exit_px": round(float(fill_px), 4),
                    "entry_px": round(float(lot["entry_px"]), 4),
                    "close_mark_px": rec.get("close_mark_px") if rec.get("close_mark_px") is not None
                    else h.get("close_mark_px"),
                    "rail_adj": round((float(lot["entry_px"]) - op) * side_mult * n, 2)})
    except Exception as e:
        log(f"[qqq-exec] held lot close bookkeeping failed for {leg} (the rail counts the "
            f"whole trade): {type(e).__name__}: {e}")


def _mark_held_overnight(state, cfg, leg, nowdt, log=print, push=True):
    """The flat_by flatten keeps `leg`'s lot: start (or keep) its "hold" block, log a
    held_overnight event and one low phone note a day. Never raises."""
    try:
        lot = (state.get("legs") or {}).get(leg)
        if not lot:
            return
        day = nowdt.strftime("%Y-%m-%d")
        h = lot.get("hold")
        if not isinstance(h, dict):
            # "since" is the lot's entry day when that is earlier (a lot whose flatten was
            # missed and that is first marked on a later day is still carried into today)
            entry_day = str(lot.get("entry_ts") or "")[:10]
            since = entry_day if (_DAY_RE.fullmatch(entry_day) and entry_day < day) else day
            h = lot["hold"] = {"since": since, "held_at": nowdt.strftime("%Y-%m-%d %H:%M:%S"),
                               "nights": 0, "gap_usd": 0.0, "gap_today_usd": 0.0,
                               "close_mark_px": None, "open_mark_px": None,
                               "open_mark_day": None, "open_mark_src": None, "rail_px": None}
        h["flat_by_day"] = day
        if not push:
            return
        n = int(round(float(lot.get("shares_remaining") or 0)))
        msg = (f"{_leg_word(leg)} {lot.get('side')} {n} held overnight -- the end-of-day "
               f"flatten skips it (it holds like its backtest); it sells on its own strategy "
               f"exit, at market in regular hours")
        log(f"[qqq-exec] {msg}")
        _log_event(state, "held_overnight", msg, log=log)
        _say(state, f"held:{leg}", day, _held_note(leg, n), log=log)
    except Exception as e:
        log(f"[qqq-exec] held-overnight bookkeeping failed for {leg}: {type(e).__name__}: {e}")


def _adopt_missed_holds(state, cfg, nowdt, log=print):
    """Each tick: a lot on a hold leg opened on an EARLIER day that has no "hold" block -- the
    executor was down or wedged through that day's flat_by window (the flatten that marks the
    hold only runs 15:59-16:05) and came back after it, so the lot rode the night unmarked. It
    is carried all the same: start its hold block now (since = its entry day, no phone note),
    so mark-to-open on both rail sites, its gap and nights, the never-stale exit and the
    after-close expectation all apply. Never raises."""
    try:
        hold = set(_hold_legs(cfg))
        if not hold or nowdt is None:
            return
        today = nowdt.strftime("%Y-%m-%d")
        for leg, lot in list((state.get("legs") or {}).items()):
            if leg not in hold or not isinstance(lot, dict) or isinstance(lot.get("hold"), dict):
                continue
            entry_day = str(lot.get("entry_ts") or "")[:10]
            if not _DAY_RE.fullmatch(entry_day) or entry_day >= today:
                continue
            _mark_held_overnight(state, cfg, leg, nowdt, log=log, push=False)
            h = lot.get("hold")
            if not isinstance(h, dict):
                continue
            h["since"] = h["flat_by_day"] = entry_day
            n = int(round(float(lot.get("shares_remaining") or 0)))
            msg = (f"{_leg_word(leg)} {lot.get('side')} {n} was carried from {entry_day} without "
                   f"its end-of-day hold mark (the book was not running at that flatten) -- held "
                   f"overnight from its entry day; the daily loss limit counts it from today's open")
            log(f"[qqq-exec] {msg}")
            _log_event(state, "held_overnight", msg, log=log)
    except Exception as e:
        log(f"[qqq-exec] missed-hold check failed (non-fatal): {type(e).__name__}: {e}")


def _held_legs_to_defer(state, cfg, nowdt):
    """The legs whose close must wait for the next open: outside regular hours, every lot
    the book holds overnight (a "hold" block, or a leg in _hold_legs(cfg) -- an after-bell
    flatten that has not marked it yet); inside them, none. Never raises."""
    try:
        if not _outside_regular_hours(nowdt):
            return []
        hold = set(_hold_legs(cfg))
        return [leg for leg, lot in (state.get("legs") or {}).items()
                if isinstance((lot or {}).get("hold"), dict) or leg in hold]
    except Exception:
        return []


def _defer_held_close(state, cfg, leg, reason, nowdt, log=print, px=None, trade_id=None,
                      late=False):
    """Keep a held lot open and mark it to be sold at market by the first tick from the next
    open (lot["close_pending"]: the top reason -- KILL over BREAKER over a strategy exit --
    when it was decided, the engine's price for a strategy exit, the trade id, and every
    reason still pending). Nothing is sent now. Returns True when the lot is marked. Never
    raises.

    `late` (inside regular hours): a hold leg's strategy exit whose own price is not from now
    (_held_exit_px_is_old) -- the next tick sells it at a price from today; no hold block is
    started for it (close_pending["late"])."""
    try:
        lot = (state.get("legs") or {}).get(leg)
        if not lot:
            return False
        if not isinstance(lot.get("hold"), dict) and not late:
            _mark_held_overnight(state, cfg, leg, nowdt, log=log, push=False)
        cp = lot.get("close_pending") if isinstance(lot.get("close_pending"), dict) else {}
        reasons = dict(cp.get("reasons") or ({cp["reason"]: cp.get("at")} if cp.get("reason") else {}))
        at = nowdt.strftime("%Y-%m-%d %H:%M:%S")
        new = reason not in reasons
        reasons.setdefault(reason, at)
        top = max(reasons, key=lambda r: _PENDING_RANK.get(r, 0))
        lot["close_pending"] = {"reason": top, "at": cp.get("at") or at,
                                "px": px if px is not None else cp.get("px"),
                                "trade_id": trade_id or cp.get("trade_id") or lot.get("trade_id"),
                                "reasons": reasons}
        if late or cp.get("late"):
            lot["close_pending"]["late"] = True
        if new and late:
            msg = (f"{_leg_word(leg)}'s strategy exit came with a price that is not from now "
                   f"({nowdt.strftime('%a %H:%M:%S')} New York) -- it sells at market at a "
                   f"price from today on the next tick, never at that old price")
            log(f"[qqq-exec] {msg}")
            _log_event(state, "held_close_deferred", msg, log=log)
        elif new:
            msg = (f"{_leg_word(leg)}'s held lot: {reason} close came outside regular hours "
                   f"({nowdt.strftime('%a %H:%M:%S')} New York) -- kept, nothing sent; it "
                   f"sells at market when the market opens")
            log(f"[qqq-exec] {msg}")
            _log_event(state, "held_close_deferred", msg, log=log)
        return True
    except Exception as e:
        log(f"[qqq-exec] could not defer {leg}'s held close: {type(e).__name__}: {e}")
        return False


def _held_open_price_ready(leg, nowdt, log=print):
    """True when a held lot's close at the open can be booked at a price from today: the
    live stream is fresh (_exit_price_for_leg's own "live_stream"), or today's first 1m bar
    is in the engine cache, or it is already HELD_OPEN_PRICE_WAIT_UNTIL (the close never
    waits longer). Never raises."""
    try:
        _px, src = _exit_price_for_leg(leg, log=log)
        if src == "live_stream":
            return True
        if ((_held_session_marks(leg, nowdt, log=log) or {}).get("today_last")) is not None:
            return True
        return _et_hhmm(nowdt) >= HELD_OPEN_PRICE_WAIT_UNTIL
    except Exception:
        return True


def _run_deferred_held_closes(state, cfg, nowdt, quote_fn, ratio_fn, kill_present, log=print):
    """Each tick: a pending KILL close whose kill file is gone is cancelled (any time);
    inside regular hours every lot with close_pending is sold at market -- KILL / BREAKER
    through _close_all (its own reason, priced like any forced close), a strategy exit
    through _reduce_lot at the live price (HELD_EXIT_REASON) -- each once the book has a
    price from today (_held_open_price_ready, at most until HELD_OPEN_PRICE_WAIT_UNTIL). A
    lot that cannot be priced keeps its close_pending for the next tick. Never raises."""
    for leg in list((state.get("legs") or {}).keys()):
        saved = None
        try:
            lot = state["legs"].get(leg)
            cp = (lot or {}).get("close_pending")
            if not isinstance(cp, dict):
                continue
            reasons = dict(cp.get("reasons") or ({cp.get("reason"): cp.get("at")}
                                                 if cp.get("reason") else {}))
            if "KILL" in reasons and not kill_present:
                reasons.pop("KILL", None)
                msg = (f"{_leg_word(leg)}'s held lot: the kill-switch close was cancelled -- "
                       f"the kill file is gone" + ("" if reasons else "; the lot stays held"))
                log(f"[qqq-exec] {msg}")
                _log_event(state, "held_close_cancelled", msg, log=log)
                if not reasons:
                    lot.pop("close_pending", None)
                    continue
                cp["reasons"] = reasons
                cp["reason"] = max(reasons, key=lambda r: _PENDING_RANK.get(r, 0))
            if _outside_regular_hours(nowdt):
                continue
            if not _held_open_price_ready(leg, nowdt, log=log):
                if not cp.get("_waiting_logged"):
                    cp["_waiting_logged"] = True
                    log(f"[qqq-exec] {leg}'s held lot: waiting for a price from today before "
                        f"its sell at the open (at most until "
                        f"{HELD_OPEN_PRICE_WAIT_UNTIL[0]:02d}:{HELD_OPEN_PRICE_WAIT_UNTIL[1]:02d})")
                continue
            top = cp.get("reason")
            # a late in-session exit of a lot opened today is not a sell at the open
            late_now = bool(cp.get("late")) and not _carried_into(lot, nowdt.strftime("%Y-%m-%d"))
            saved = lot.pop("close_pending")
            saved.pop("_waiting_logged", None)
            if top in ("KILL", "BREAKER"):
                _close_all(state, cfg, top, quote_fn, ratio_fn, log=log, nowdt=nowdt, legs=[leg])
            else:
                px, src = _exit_price_for_leg(leg, log=log)
                if px is None:
                    lot["close_pending"] = saved
                    log(f"[qqq-exec] {leg}'s held lot: no price yet for its sell at the open "
                        f"-- tried again next tick")
                    continue
                state["_px_source"] = src
                _reduce_lot(state, cfg, leg, lot["nq_qty_total"], None, px,
                            cfg.get("slippage_per_share", 0.0),
                            LATE_EXIT_REASON if late_now else HELD_EXIT_REASON, f=None,
                            log=log, signal_source=cfg.get("signal_source"), nowdt=nowdt)
            if leg in state["legs"]:
                state["legs"][leg]["close_pending"] = saved
                continue
            if late_now:
                msg = (f"{_leg_word(leg)}'s late strategy exit sold at market at a price from "
                       f"now (decided {saved.get('at')})")
            else:
                msg = (f"{_leg_word(leg)}'s held lot sold at market at the open ({top} decided "
                       f"{saved.get('at')})")
            log(f"[qqq-exec] {msg}")
            _log_event(state, "held_close_at_open", msg, log=log)
        except Exception as e:
            log(f"[qqq-exec] deferred held close failed for {leg} (tried again next tick): "
                f"{type(e).__name__}: {e}")
            try:   # a lot still open never loses its pending close
                held = (state.get("legs") or {}).get(leg)
                if saved and held and not isinstance(held.get("close_pending"), dict):
                    held["close_pending"] = saved
            except Exception:
                pass


def _close_all(state, cfg, reason, quote_fn, ratio_fn, log=print, nowdt=None, legs=None):
    """BREAKER/EOD/KILL flatten -- branches on signal_source exactly like
    _mark_and_check_breaker: engine mode prices the close off the live Webull stream
    when it is fresh, else api.cloud_signal's own QQQ bar cache (_exit_price_for_leg,
    EXIT SAFETY item 6, 2026-09-26), never the NQ feed/ratio/Webull quote.

    `nowdt` (EXIT SAFETY item 4 minor, 2026-09-26 review): the calling tick's own
    notion of "now", threaded straight through to _reduce_lot -- see
    _mirror_to_broker's own docstring.

    END-OF-DAY INTERNAL CROSS (2026-09-28): every lot is priced FIRST, then legs holding
    opposite sides at the broker are crossed against each other with no order
    (_internal_cross_for_flatten / OrderAdapter.cross_legs_internally), and only each
    leg's remainder -- all on the account's own side, so each is a plain closing order
    -- is sent. The 09-28 15:59 pair (ORB short 10, ENGUQ long 10, account flat) now
    sends nothing instead of a BUY that Webull held pending and a SELL it refused with
    417 OPENAPI_OPEN_ORDER_HAS_BOX_ORDER. The shadow book is unchanged: every lot still
    closes at its own end-of-day price.

    `legs` (HOLD OVERNIGHT, 2026-10-09): only these legs are priced, crossed and closed
    (None = every open lot, as before). The flat_by flatten passes the legs that do NOT
    hold overnight, so a closing leg is never crossed against a held lot (that would close
    the held lot in the broker books with no order); KILL / BREAKER inside regular hours
    still pass None and close held lots too."""
    want = None if legs is None else set(legs)
    if want is not None and not (want & set(state["legs"].keys())):
        return
    # RESTING ORB STOP (2026-09-29), step 1 of every flatten: cancel and confirm each
    # resting order first (a fill found is booked, so its leg is not closed twice) --
    # before the internal cross, which leaves out a leg whose resting order is still live.
    if want is None or RESTING_LEG in want:
        _cancel_resting_for_flatten(state, cfg, reason, nowdt=nowdt, log=log)
    engine_mode = str(cfg.get("signal_source") or "engine").strip().lower() == "engine"
    nq_now = None
    if not engine_mode:
        nq_now, _ts = _latest_nq_px()
    priced = []
    for leg in list(state["legs"].keys()):
        if want is not None and leg not in want:
            continue
        lot = state["legs"][leg]
        if engine_mode:
            exit_nq = None
            qqq_px, src = _exit_price_for_leg(leg, log=log)
        else:
            # flatten at the LIVE NQ price (fallback: last known) -- never at the entry price
            exit_nq = nq_now if nq_now is not None else (lot.get("last_nq_px") or lot["nq_entry_px"])
            qqq_px, src = resolve_price(cfg, state, exit_nq, quote_fn, ratio_fn, log=log)
        if qqq_px is None:
            log(f"[qqq-exec] cannot price {leg} for {reason} close -- no quote/ratio "
                f"available, lot left open")
            continue
        priced.append((leg, exit_nq, qqq_px, src))
    crosses = _internal_cross_for_flatten(state, priced, reason, nowdt=nowdt, log=log)
    for leg, exit_nq, qqq_px, src in priced:
        lot = state["legs"].get(leg)
        if not lot:
            continue
        state["_px_source"] = src
        # EXIT SAFETY item 6 (engine mode only -- the live-stream-vs-bar choice above
        # only exists for engine/QQQ pricing): trades.csv has no dedicated
        # price-source column, so it travels in the exit note instead (exit_reason,
        # e.g. "EOD (px: live_stream)" vs "EOD (px: engine_cache)") -- the base reason
        # ("EOD"/"KILL"/"BREAKER") stays the FIRST word, unchanged, for anything
        # reading it as a tag.
        exit_reason = f"{reason} (px: {src or 'n/a'})" if engine_mode else reason
        _reduce_lot(state, cfg, leg, lot["nq_qty_remaining"], exit_nq,
                   qqq_px, cfg.get("slippage_per_share", 0.0), exit_reason, log=log,
                   signal_source=cfg.get("signal_source"), nowdt=nowdt,
                   broker_cross=crosses.get(leg))


def _internal_cross_for_flatten(state, priced, reason, nowdt=None, log=print):
    """{leg: broker_cross} for _close_all -- see its END-OF-DAY INTERNAL CROSS note and
    OrderAdapter.cross_legs_internally. {} (every leg closes one by one, as before)
    unless the broker mirror would really send right now: adapter PAPER/LIVE, the
    cross-host lease good (the same gate _mirror_to_broker applies -- a host that may not
    send must not rewrite the books either), no broker send still in flight, and not
    after the session close. A leg with anything in the re-send queue keeps its own
    verify-gated path and is left out. Only priced lots with at least one long and one
    short take part -- and only the legs _close_all is closing: a lot held overnight is
    never in `priced` at the flat_by flatten (HOLD OVERNIGHT), so nothing is ever crossed
    against it. Never raises."""
    try:
        sides = {leg: (1 if (state["legs"].get(leg) or {}).get("side") == "long" else -1)
                 for leg, _nq, _px, _src in priced if state["legs"].get(leg)}
        busy = {str((item or {}).get("leg") or "")
                for item in (state.get("_broker_resend") or {}).values()}
        sides = {leg: s for leg, s in sides.items() if leg not in busy}
        if len({s for s in sides.values()}) < 2:
            return {}
        if nowdt is not None and _market_closed_for_orders(nowdt):
            return {}
        if _send_inflight_future() is not None:
            return {}
        adapter = _get_broker_adapter(log=log)
        mode, _mode_reason = adapter.effective_mode()
        if mode not in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
            return {}
        if not state.get("_broker_lease_ok", True):
            return {}
        at_send = _LEASE.send_gate(_LEASE.uid)
        if at_send is not None and not at_send[0]:
            return {}
        cross = getattr(adapter, "cross_legs_internally", None)
        trade_ids = {leg: str((state["legs"].get(leg) or {}).get("trade_id") or "")
                     for leg in sides}
        res = cross(BROKER_SYMBOL, sides, trade_ids=trade_ids) if callable(cross) else None
        crossed = (res or {}).get("crossed") or {}
        replay = None
        if not crossed:
            replay = _replay_internal_cross(state, adapter, sides, trade_ids, log=log)
            res = replay
            crossed = (res or {}).get("crossed") or {}
        if not crossed:
            return {}
        # ONE price for every crossed share, so the legs' broker P&L sums to the
        # account's: the live print when a lot was priced off it, else the newest bar
        # (the finest timeframe) among the crossed legs.
        px_by_leg = {leg: (px, src) for leg, _nq, px, src in priced}
        live = [px for leg, (px, src) in px_by_leg.items() if leg in crossed and src == "live_stream"]
        if live:
            cross_px = live[0]
        else:
            cross_px = sorted(
                ((_leg_timeframe_seconds(leg, log=log) or 10 ** 9, leg, px)
                 for leg, (px, _src) in px_by_leg.items() if leg in crossed))[0][2]
        out = {}
        rows_done = (replay or {}).get("rows_done") or set()
        for leg, n in crossed.items():
            others = [f"{o} {'long' if sides[o] > 0 else 'short'}" for o in sorted(crossed)
                      if sides[o] != sides[leg]]
            out[leg] = {"crossed": int(n), "left": (res.get("left") or {}).get(leg, 0),
                        "px": float(cross_px), "id": res.get("id"),
                        "against": ", ".join(others), "reason": reason,
                        "row_done": leg in rows_done}
        booked = state.setdefault("_crosses_booked", [])
        if res.get("id") and res.get("id") not in booked:
            booked.append(res.get("id"))
            del booked[:-CROSSES_BOOKED_KEEP]
        state["_reconcile_due"] = True        # confirm Webull agrees on the next tick
        _log_event(state, "broker",
                   f"{reason} flatten: " + (f"re-run after a restart, cross {res.get('id')} "
                                            f"already booked at the adapter: "
                                            if replay else "crossed ") + ", ".join(
                       f"{leg} {'long' if sides[leg] > 0 else 'short'} {n}"
                       for leg, n in sorted(crossed.items()))
                   + f" against each other at {cross_px:.2f} -- already flat at Webull, "
                     f"no order sent for those shares", log=log)
        return out
    except Exception as e:
        log(f"[qqq-exec] {reason} internal cross skipped (legs close one by one): "
            f"{type(e).__name__}: {e}")
        return {}


CROSSES_BOOKED_KEEP = 20
INTERNAL_CROSS_REPLAY_MAX_AGE_SEC = 600.0


def _replay_internal_cross(state, adapter, sides, trade_ids, log=print):
    """A cross the adapter already booked for THESE lots on an earlier run whose
    qqq_exec state was never saved (2026-09-28 review: a crash between the adapter's
    save and ours). The re-run's cross finds the crossed legs flat at the broker, so
    without this each would be closed one by one, refused "nothing to close", push the
    misleading "Webull never held it" message and lose its NETTED row. Matched only on
    a record younger than INTERNAL_CROSS_REPLAY_MAX_AGE_SEC, not in
    state["_crosses_booked"], whose every leg is still open here on the same side with
    the same trade id. Returns cross_legs_internally's shape with "left" = what the
    adapter holds now (so a remainder already sent before the crash is never re-sent)
    and "rows_done" = legs whose NETTED row for it is already on file; else None.
    Never raises."""
    try:
        fn = getattr(adapter, "recent_internal_crosses", None)
        if not callable(fn):
            return None
        records = fn(max_age_sec=INTERNAL_CROSS_REPLAY_MAX_AGE_SEC)
        if not isinstance(records, list):
            return None
        booked = set(state.get("_crosses_booked") or [])
        for rec in reversed(records):
            cid = str((rec or {}).get("id") or "")
            legs = (rec or {}).get("legs") or {}
            rec_tids = (rec or {}).get("trade_ids") or {}
            if not cid or cid in booked or not legs:
                continue
            if not all(leg in sides and (float(q) > 0) == (sides[leg] > 0)
                       and trade_ids.get(leg) and rec_tids.get(leg) == trade_ids[leg]
                       for leg, q in legs.items()):
                continue
            rows_done = {r.get("leg") for r in _all_broker_orders_from_csv()
                         if r.get("outcome") == "NETTED" and f"({cid})" in (r.get("reason") or "")}
            log(f"[qqq-exec] internal cross {cid} was booked at the adapter by an earlier run "
                f"that never saved its state -- re-using it (no order, no second cross)")
            return {"crossed": {leg: int(round(abs(float(q)))) for leg, q in legs.items()},
                    "left": dict((rec or {}).get("sent_now") or {}), "id": cid,
                    "rows_done": rows_done}
        return None
    except Exception as e:
        log(f"[qqq-exec] internal cross re-run check failed (legs close one by one): "
            f"{type(e).__name__}: {e}")
        return None


def _alert_close_blocked_after_close(state, leg, nowdt, log=print):
    """One high-priority push per leg per day when the AFTER-CLOSE GUARD blocks a CLOSE
    while the adapter's books (PAPER/LIVE) still hold shares for `leg` (2026-09-28
    review): a flatten or settle EXIT that ran after the bell -- a stalled tick -- used
    to depend entirely on _maybe_check_webull_flat_after_eod running in a later tick.
    Reads the adapter's status only; sends nothing. Never raises."""
    try:
        status = _get_broker_adapter(log=log).status()
        if status.get("effective_mode") not in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE):
            return

        def _qty(book):
            p = (status.get(book) or {}).get(leg)
            return int(round(abs(float((p or {}).get("qty") or 0))))

        held = min(_qty("believed_positions"), _qty("broker_sent_positions"))
        if held <= 0:
            return
        day = nowdt.strftime("%Y-%m-%d")
        sent = state.setdefault("_after_close_blocked_alerted", {})
        for k in [k for k in sent if not str(k).startswith(day)]:
            sent.pop(k, None)
        key = f"{day}:{leg}"
        if sent.get(key):
            return
        sent[key] = True
        msg = (f"QQQ BROKER: {leg}'s CLOSE came after the bell ({nowdt.strftime('%H:%M:%S')} "
               f"ET) and was NOT sent -- Webull may still hold {held} share(s) for {leg}; "
               f"check the account and flatten by hand")
        _log_event(state, "broker", msg, log=log)
        # WEBULL PUSH PLAN 10-07, group A: urgent (nobody will send this sell any more)
        _say_exit_stuck(state, leg, f"The {_leg_word(leg)} sell came after the close at "
                        f"{_phone_clock(nowdt)} and was not sent",
                        problem_id=f"{day} after-bell", log=log)
    except Exception as e:
        log(f"[qqq-exec] after-close blocked-CLOSE alert failed (non-fatal): "
            f"{type(e).__name__}: {e}")


def _record_internal_cross(state, *, leg, side, shares, shadow_px, cross, ts, seq, trade_id,
                           partial, log=print):
    """broker_orders.csv's row for a leg's crossed shares (see _close_all's END-OF-DAY
    INTERNAL CROSS): intent CLOSE, sent False, ok True, outcome NETTED, priced at the
    cross price -- so _broker_realized_today pairs it with the leg's OPEN and the legs'
    realized P&L still sums to the account's. A fully crossed leg's row carries its
    ordinary CLOSE signal id (the parity check finds it); a partly crossed one's gets an
    "X" suffix, so fill capture of the leg's real CLOSE order (same base id) updates that
    order's own row, never this one. Never raises."""
    try:
        base = _broker_signal_id(leg, ts, "CLOSE", seq=seq, trade_id=trade_id)
        cross_px = float(cross.get("px"))
        slippage = round(cross_px - float(shadow_px), 4) if shadow_px is not None else ""
        try:
            mode, _ = _get_broker_adapter(log=log).effective_mode()
        except Exception:
            mode = ""
        row = {
            "ts_et": _now_et().strftime("%Y-%m-%d %H:%M:%S"), "leg": leg, "intent": "CLOSE",
            "side": _broker_side(side, "CLOSE"), "shares": shares,
            "signal_id": base + ("X" if partial else ""), "client_order_id": "",
            "mode": mode, "ok": True, "sent": False,
            "shadow_px": round(shadow_px, 4) if shadow_px is not None else "",
            "broker_fill_px": round(cross_px, 4), "slippage": slippage,
            "reason": (f"{cross.get('reason') or 'flatten'}: crossed internally against "
                       f"{cross.get('against') or 'another leg'} ({cross.get('id')}) -- "
                       f"already flat at Webull, no order sent"),
            "duplicate": False, "host_id": _lease_host_id(), "outcome": "NETTED",
        }
        _append_csv(BROKER_ORDERS_CSV, BROKER_ORDER_COLS, row, BROKER_ORDERS_KEEP)
        log(f"[qqq-exec] broker CLOSE for {leg}: {shares} share(s) crossed internally against "
            f"{cross.get('against')} @ {cross_px:.2f} -- no order sent")
    except Exception as e:
        log(f"[qqq-exec] internal-cross row not written for {leg}: {type(e).__name__}: {e}")


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
        # HOLD OVERNIGHT: a lot held overnight is in state["legs"] like any open lot, so its
        # shares are never an orphan -- this repair can never sell a held lot
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
            # WEBULL PUSH PLAN 10-07, group A: urgent -- Webull still holds these shares
            _say(state, "exit:repair", _phone_day(nowdt),
                 _repair_gave_up_note([leg for leg, _qty in orphans]), log=log)
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
                             trade_id=f"FIX-{leg}-{nowdt:%Y%m%d%H%M%S}", nowdt=nowdt,
                             log=log)
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
def _route_fills(state, cfg, fills, quote_fn, ratio_fn, entries_blocked, log=print,
                 nowdt=None):
    """Walk NEW fills in file order, updating per-group position and opening/reducing
    shadow lots. Mirrors api.nt_sync.build_trades' adding/reducing FIFO logic.

    `entries_blocked` covers the reasons that depend on the ADAPTER'S current state
    (breaker tripped / feed stale / kill file) rather than the fill's own time --
    those apply to every fill regardless of when it happened. The session-window
    check (open/last_entry) is evaluated against the FILL'S OWN timestamp
    (f["dt"], NY-local per fills.csv), which is what a real 5s-tick adapter is
    equivalent to: by the time a fill shows up in the file it IS "now".

    `nowdt` (EXIT SAFETY item 4 minor, 2026-09-26 review): the calling tick's own
    notion of "now", threaded straight through to _open_lot/_reduce_lot -- see
    _mirror_to_broker's own docstring."""
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
                                   signal_source=cfg.get("signal_source"), nowdt=nowdt)
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
                           signal_source=cfg.get("signal_source"), nowdt=nowdt)
                if leg not in state["legs"]:
                    state["group_leg"].pop(gk, None)


# -- mark-to-market + breaker ------------------------------------------------------------
def _mark_and_check_breaker(state, cfg, quote_fn, ratio_fn, log=print, nowdt=None):
    # stashes the per-leg breakdown on state["_unrl_by_leg"] (leg -> unrealized $) so
    # _build_doc can show each leg card its own unrealized figure, not just the total --
    # cheap, since the marks are already computed here for the breaker check.
    # `nowdt` (EXIT SAFETY item 4 minor, 2026-09-26 review): the calling tick's own
    # notion of "now", threaded straight through to _close_all -- see
    # _mirror_to_broker's own docstring.
    # HOLD OVERNIGHT: today's open mark and rail mark for every lot carried into today
    _refresh_held_marks(state, nowdt, log=log)
    if not state.get("legs"):
        state["_unrl_by_leg"] = {}
        state["_rail_unrl_by_leg"] = {}
        # FLAT (review 2026-09-28): nothing to mark or close, but today's realized total
        # (plus the fill shortfall) can already be past the limit -- trip now, which
        # blocks new entries (entries_blocked), instead of letting the next entry open
        # and be flattened at once. Never calls _close_all: there is nothing to close.
        _check_breaker_while_flat(state, cfg, log=log, nowdt=nowdt)
        return 0.0  # nothing open: no quote/ratio work, unrealized is zero
    unrl = 0.0
    unrl_by_leg = {}
    # HOLD OVERNIGHT: the daily loss rail's own open P&L per leg -- the record mark for a lot
    # opened today, mark-to-open for a lot carried into today (see _rail_unrl_for_lot)
    rail_raw, rail_by_leg = 0.0, {}
    day = state.get("trading_day")
    engine_mode = str(cfg.get("signal_source") or "engine").strip().lower() == "engine"
    nq_now = nq_ts = None
    if not engine_mode:
        nq_now, nq_ts = _latest_nq_px()
    for leg, lot in state["legs"].items():
        if _carried_into(lot, day):
            r = _rail_unrl_for_lot(lot, day, None)
            rail_by_leg[leg] = round(r, 2)
            rail_raw += r
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
        if not _carried_into(lot, day):
            rail_by_leg[leg] = round(leg_unrl, 2)
            rail_raw += leg_unrl
    state["_unrl_by_leg"] = unrl_by_leg
    state["_rail_unrl_by_leg"] = rail_by_leg
    # P&L OF RECORD on the breaker (2026-09-28 (B), FAIL-SAFE): Webull's fills can only
    # make this input MORE negative, never less -- each closed trade and open lot adds
    # min(0, fill-based - book) (see _breaker_fill_shortfall); a side with no captured
    # fill keeps the book's value, exactly as before.
    adj = _breaker_fill_shortfall(state, log=log)
    state["_breaker_fill_adj"] = adj
    # HOLD OVERNIGHT: MARK-TO-OPEN -- realized and open marks as the rail counts them (a lot
    # carried into today from today's open mark; identical to the record for every other lot)
    total = _rail_realized_today(state) + adj + rail_raw
    _note_breaker_input(state, total)
    limit = float(cfg.get("daily_loss_limit_usd", 0) or 0)
    if limit and total <= -abs(limit) and not state.get("breaker_tripped"):
        log(f"[qqq-exec] BREAKER TRIPPED: today's shadow P&L {total:.2f} <= "
            f"-{limit:.2f} -- closing all lots")
        # a held lot outside regular hours is sold at the next open, never now
        deferred = _held_legs_to_defer(state, cfg, nowdt)
        if deferred:
            closing = [leg for leg in state["legs"] if leg not in deferred]
            if closing:
                _close_all(state, cfg, "BREAKER", quote_fn, ratio_fn, log=log, nowdt=nowdt,
                           legs=closing)
            for leg in deferred:
                _defer_held_close(state, cfg, leg, "BREAKER", nowdt, log=log)
        else:
            _close_all(state, cfg, "BREAKER", quote_fn, ratio_fn, log=log, nowdt=nowdt)
        state["breaker_tripped"] = True
        what = "open trades were closed"
        if deferred:
            what = (f"open trades were closed; {_legs_words(deferred)}'s held shares sell when "
                    f"the market opens")
        _say_daily_stop(state, total, what, nowdt, log=log)
        _log_event(state, "breaker",
                  f"Daily loss breaker tripped at ${total:.2f} (limit -${limit:.2f}) -- "
                  f"all shadow lots closed"
                  + (f" (held overnight, sold at the open: {', '.join(deferred)})"
                     if deferred else ""), log=log)
    return unrl


def _note_breaker_input(state, total):
    """DAILY-STOP BAR (Ledger unify 13, 2026-10-05): keeps the exact figure the daily
    loss breaker just compared with the limit -- today's realized + the fill shortfall
    (+ the open marks when lots are open) -- so _build_doc can publish the breaker's own
    number (today.breaker_input) instead of the tab re-deriving one that can read better
    than the breaker sees. Stamped with the trading day so a figure from an earlier day
    is never published. Bookkeeping only: never feeds back into any check. Never raises."""
    try:
        state["_breaker_input"] = {"day": state.get("trading_day"),
                                   "pnl": round(float(total), 2)}
    except Exception:
        pass


def _published_breaker_input(state, day):
    """today.breaker_input: the figure _note_breaker_input kept, when it was kept on
    `day`; else None (the breaker has not checked today, so there is no number of its
    own to show). Never raises."""
    try:
        bi = state.get("_breaker_input") or {}
        if bi.get("day") != day:
            return None
        v = _finite_or_none(bi.get("pnl"))
        return None if v is None else round(v, 2)
    except Exception:
        return None


def _refresh_breaker_input(state, log=print, only_worse=False):
    """DAILY-STOP BAR bookkeeping when the breaker makes no check of its own (already
    tripped today, no limit set, or the KILL file present), and once more after the
    tick's broker fill capture: re-notes today's realized + the fill shortfall -- the sum
    _check_breaker_while_flat compares -- plus, while lots are still open, the LAST
    per-leg marks the breaker took (state['_unrl_by_leg'], open legs only; this tick's on
    a normal tick, the last check before the kill on a kill day whose close-out failed or
    is partial), so today.breaker_input keeps up with a close-out that booked more loss
    after the trip or the kill flatten (review 2026-10-05).

    only_worse (the after-capture call, review 2026-10-05): a fill Webull reports after
    the breaker's check can make the figure worse, never better (_breaker_fill_shortfall
    is never positive) -- the bar takes the new figure only when it is worse than the one
    already noted today, so it can never read better than the breaker's own check.
    Never trips, never closes, never raises."""
    try:
        adj = _breaker_fill_shortfall(state, log=log)
        legs = state.get("legs") or {}
        # HOLD OVERNIGHT: the rail's own marks (mark-to-open for a carried lot); a state
        # saved before they existed falls back to the record marks
        marks = state.get("_rail_unrl_by_leg")
        if not isinstance(marks, dict):
            marks = state.get("_unrl_by_leg") or {}
        unrl = sum(float(marks[k]) for k in legs if marks.get(k) is not None)
        total = _rail_realized_today(state) + adj + unrl
        if only_worse:
            prev = state.get("_breaker_input") or {}
            pv = _finite_or_none(prev.get("pnl")) if prev.get("day") == state.get("trading_day") else None
            if pv is not None and not (round(total, 2) < pv):
                return
        state["_breaker_fill_adj"] = adj
        _note_breaker_input(state, total)
    except Exception:
        pass


def _check_breaker_while_flat(state, cfg, log=print, nowdt=None):
    """The daily loss breaker's check for a FLAT book (see _mark_and_check_breaker):
    realized today + the fill shortfall against the limit; trips (breaker_tripped, the
    push and the event) without closing anything. The phone push only goes out 09:30-
    16:00 ET (review 2026-09-28: a 15:59 flatten that realizes a loss past the limit
    would otherwise push "tripped while flat" after the bell); the trip, log line and
    event happen either way. Never raises."""
    try:
        limit = float(cfg.get("daily_loss_limit_usd", 0) or 0)
        if not limit or state.get("breaker_tripped"):
            # no check to make, but keep the published figure current (review 2026-10-05:
            # after a trip the close-out and any later close by a resting stop book more
            # loss, and the daily-stop bar must not read better than that). Bookkeeping
            # only -- the trip decision is unchanged.
            _refresh_breaker_input(state, log=log)
            return
        adj = _breaker_fill_shortfall(state, log=log)
        state["_breaker_fill_adj"] = adj
        total = _rail_realized_today(state) + adj    # HOLD OVERNIGHT: mark-to-open realized
        _note_breaker_input(state, total)
        if total <= -abs(limit):
            state["breaker_tripped"] = True
            log(f"[qqq-exec] BREAKER TRIPPED while flat: today's shadow P&L {total:.2f} <= "
                f"-{limit:.2f} -- new entries blocked for the day")
            now = nowdt or _now_et()
            if (9, 30) <= _et_hhmm(now) < (16, 0):
                _say_daily_stop(state, total, "no trades were open", now, log=log)
            _log_event(state, "breaker",
                       f"Daily loss breaker tripped at ${total:.2f} (limit -${limit:.2f}) "
                       f"with no lots open -- new entries blocked for the day", log=log)
    except Exception as e:
        log(f"[qqq-exec] flat breaker check failed: {type(e).__name__}: {e}")


_BREAKER_ADJ_CACHE = {"key": None, "val": 0.0}


def _breaker_fill_shortfall(state, log=print):
    """<= 0.0 -- how much WORSE today's book reads at Webull's own fills than at the
    book's prices: for EACH SIDE of each trade closed today, min(0, (Webull fill - book
    price) a share, signed, x shares) -- per fill, so a helpful capture on one side can
    never cancel a bad fill on the other (review 2026-09-28); for each open lot,
    min(0, what its captured entry fill does to the open P&L). Never
    positive, so feeding it to the daily loss breaker can only make the breaker trip
    sooner, never later (owner 2026-09-28: stay fail-safe; a side with no fill keeps the
    book's value). Cached on both ledgers' size/mtime and the open lots. Never raises:
    0.0 (the old behaviour) on any error."""
    try:
        day = state.get("trading_day") or _now_et().strftime("%Y-%m-%d")
        lots = state.get("legs") or {}
        sig = []
        for p in (TRADES_CSV, BROKER_ORDERS_CSV):
            try:
                st = os.stat(p)
                sig.append((st.st_mtime_ns, st.st_size))
            except OSError:
                sig.append(None)
        lot_sig = tuple(sorted((k, str(v.get("trade_id")), v.get("entry_px"),
                                v.get("shares_remaining"), v.get("side"),
                                _carried_into(v, day))
                               for k, v in lots.items()))
        key = (day, tuple(sig), lot_sig)
        if _BREAKER_ADJ_CACHE["key"] == key:
            return _BREAKER_ADJ_CACHE["val"]
        by_base = _broker_orders_by_base(_all_broker_orders_from_csv())
        adj = 0.0
        for t in _all_trades_from_csv(cap=200):
            if str(t.get("exit_ts") or "")[:10] != day:
                continue
            sh = _finite_or_none(t.get("shares")) or 0.0
            entry_day = str(t.get("entry_ts") or "")[:10]
            for intent in ("OPEN", "CLOSE"):
                if intent == "OPEN" and entry_day and entry_day != day:
                    continue   # HOLD OVERNIGHT: a carried trade's entry fill was its entry day's
                s = _side_parity(t, intent, by_base, None)
                if s.get("fs") != "ok" or s.get("wb") is None or s.get("bk") is None:
                    continue
                adj += min(0.0, _edge_ps(s["bk"], s["wb"], _is_buy(t.get("side"), intent)) * sh)
        for leg, lot in lots.items():
            tid = str(lot.get("trade_id") or "").strip()
            if not tid or _carried_into(lot, day):
                continue   # HOLD OVERNIGHT: a carried lot's entry fill counted on its entry day
            brow = _broker_order_for(tid, "OPEN", by_base)
            if brow is None or str(brow.get("ok")).strip().lower() not in ("true", "1"):
                continue
            fill = _finite_or_none(brow.get("broker_fill_px"))
            book_entry = _finite_or_none(lot.get("entry_px"))
            if fill is None or book_entry is None:
                continue
            base = _broker_signal_id(None, None, "OPEN", trade_id=tid)
            if base in SUSPECT_BROKER_FILLS:
                continue
            dir_mult = 1 if lot.get("side") == "long" else -1
            sh = float(lot.get("shares_remaining") or 0)
            adj += min(0.0, (book_entry - fill) * dir_mult * sh)
        adj = round(min(0.0, adj), 2)
        _BREAKER_ADJ_CACHE["key"] = key
        _BREAKER_ADJ_CACHE["val"] = adj
        return adj
    except Exception as e:
        log(f"[qqq-exec] breaker fill shortfall failed (book value kept): {type(e).__name__}: {e}")
        return 0.0


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
    Returns the gap in seconds, or None on the first tick of a fresh state. Never raises.

    OVERNIGHT / CROSS-SESSION GAP (2026-09-25 fix). This is only ever called `if active`
    (see tick()'s caller), so "the previous active tick" is normally a few seconds ago --
    except for the FIRST active tick of a session, whose previous active tick was the
    prior session's close. The adapter is inactive outside market hours, so that gap is
    routinely ~62,000s (overnight) or a full weekend, and is not a stall: it fired the
    WARN log, a `tick_gap` event, and tick_gap_max_s_today every single morning before
    this fix, polluting the day's health figures with a number that says nothing about
    today. Detected by ET CALENDAR DATE (nowdt), not by the gap's size -- a size threshold
    cannot tell a real multi-hour stall from an overnight one. When the previous active
    tick's ET date differs from this tick's, this call is treated exactly like the first
    tick of a brand new state: return None, no warn, no event, just store the new
    baseline (the day-rollover block below already zeroes tick_gap_max_s_today). A real
    intraday stall -- previous active tick on the SAME ET day -- still warns exactly as
    before."""
    try:
        wall = now_wall if now_wall is not None else time.time()
        day = nowdt.strftime("%Y-%m-%d")
        prev_day = state.get("_tick_gap_day")
        new_day = prev_day != day
        if new_day:
            state["_tick_gap_day"] = day
            state["tick_gap_max_s_today"] = 0.0
        last = state.get("_last_tick_wall")
        state["_last_tick_wall"] = wall
        if last is None:
            return None
        if prev_day is not None and new_day:
            # first active tick of a new ET session -- see OVERNIGHT / CROSS-SESSION GAP
            # above; tick_gap_max_s_today was already reset to 0.0 just above.
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
        # WEBULL PUSH PLAN 10-07, group I: NO PUSH -- this check only runs for
        # signal_source "ninjatrader" (never on the box, which runs "engine"); the log line
        # keeps its 30-minute rhythm
        log(f"[qqq-exec] NinjaTrader fill feed stale "
            f"({('%.0fs' % age) if age is not None else 'no heartbeat'}) -- QQQ SHADOW is not "
            f"opening new lots")
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
# This section is the comparison the owner asked for instead. REBUILT 2026-09-28 (owner
# decisions after the 09-28 parity audit -- see FILL PARITY below): each Webull fill
# (broker_orders.csv's broker_fill_px, captured by _query_broker_fill above) is compared
# with the BACKTEST's own price for that side, signed, per share, split into design gap
# / slippage / unexplained -- never with the book's send-time price, and never with the
# re-price minute close.
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
    aged out of broker_orders.csv's own BROKER_ORDERS_KEEP trim -- see BROKER_ORDER_COLS)."""
    if not trade_id:
        return None
    sig_id = _broker_signal_id(None, None, intent, trade_id=trade_id)
    return _best_broker_row(by_base.get(sig_id))


def _all_broker_orders_from_csv(cap=BROKER_ORDERS_KEEP):
    """Every broker_orders.csv row on file (oldest-first, as the CSV stores them),
    capped defensively to the newest `cap` -- mirrors _all_trades_from_csv. The file
    itself never holds more than BROKER_ORDERS_KEEP rows (trimmed at write time), so this cap
    is a second, independent ceiling, not the normal limiter. Never raises."""
    try:
        with open(BROKER_ORDERS_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return []
    return rows[-cap:]


# -- FILL PARITY: Webull's fills vs the BACKTEST's own price (owner decisions 2026-09-28) --
# The PARITY NOTE used to compare each Webull fill with the BOOK's send-time price (the
# signal price plus or minus the configured 1-cent charge, or the live quote at the 15:59
# flatten) and called that "engine booked"; it judged the gap against 2% of the trade's
# own P&L (about a cent a share), ignored direction, and fell back to the re-price minute
# close when no fill was captured -- so it read "36 of 36 trades miss" on a day Webull
# did better than the backtest (parity audit 2026-09-28). Owner decisions 2026-09-28 (A):
#   * each Webull fill is compared with the BACKTEST's own fill price for that side
#     (owner, 2026-09-28: "fill price vs the backtest's assumed fill") -- the engine's
#     ref_price on its ENTRY/EXIT signal row (api/cloud_signal.py's signals.csv, joined
#     by trade id, see _engine_prices_by_trade), except on NOISE's decide-at-close rows,
#     whose ref_price is the DECISION close while the backtest fills at the OPEN of the
#     next bar: there it is that open, from the engine's own bar file (older NOISE rows
#     already carry the fill-bar open). ORB: its signal-bar close and its stop / target
#     / day-end exit; ENGU-Q: its limit and its own exit -- including an exit the engine
#     emits AFTER the book already flattened (the next-morning day-end exit, a
#     multi-day ENGU-Q stop);
#   * signed by side: + means Webull did BETTER than the backtest, - worse;
#   * cents a share and dollars at the trade's actual shares;
#   * each gap is split into DESIGN (a known, intended difference: the 15:59 flatten,
#     limit vs market, a level exit vs a market order after the bar, NOISE acting one
#     bar late before decide-at-close), SLIPPAGE (the market moving while a market order
#     goes out) and UNEXPLAINED (a fill that does not fit the tape -- a suspect capture);
#   * a trade is FLAGGED when any ONE of its fills is more than PARITY_TRADE_TOL_PS a
#     share WORSE than the backtest once the design gap is taken out (adverse only, per
#     fill -- a fill that beat the backtest is shown, never flagged), or when a fill does
#     not fit the tape at all (unexplained, a suspect capture);
#   * a leg / the board is FLAGGED when the signed average SLIPPAGE per fill over its
#     last PARITY_ROLL_N compared trades is worse than -PARITY_ROLL_TOL_PS (adverse
#     only). That average counts only fills that have a slippage part: a suspect
#     capture (its trade already carries its own CHECK FILL flag) and an all-design
#     side (limit / level / late, slippage 0 by construction) are left out of it -- see
#     _roll_block;
#   * no fallback to the re-price minute close: a side with no Webull fill is simply not
#     compared, and says so.
PARITY_TRADE_TOL_PS = 0.15
# ROUND TRIP reading of the 15-cent band (review 2026-09-28, OWNER CALL, off until the
# owner says yes): also flag a trade whose two fills TOGETHER are more than the band
# worse (14c worse in + 14c worse out = 28c lost, which the per-fill reading passes).
# On the 09-28 rows it would add one flag (NOISE 11:45 short, 8.4c + 9.0c = 17.4c).
PARITY_ROUND_TRIP = False
PARITY_ROLL_N = 20
PARITY_ROLL_TOL_PS = 0.05
# Legs whose backtest ENTRY rests a limit order (live sends a market order once the
# engine reports the fill bar) -- the whole entry gap is design.
LIMIT_ENTRY_LEGS = ("ENGUQ",)
# Legs whose backtest EXITS fill at a stop / target / trail level inside the bar (live
# sends a market order once the engine sees the finished bar) -- the whole gap on an
# engine-signalled exit is design. NOISE exits are decided at a bar close, so theirs is
# slippage.
LEVEL_EXIT_LEGS = ("ORB", "ENGUQ")
# The book's own rails close a trade at a moment the backtest does not -- the gap
# between the backtest's exit and the book's price at that moment is design; only the
# book-price-to-Webull-fill part is slippage.
RAIL_EXIT_WHY = {"EOD": "eod", "KILL": "kill", "BREAKER": "breaker"}
# Every side's `why` is one of these short codes (the published doc carries up to 500
# trades under Firestore's 1 MiB cap, so each row keeps codes, not sentences); the plain
# words ride ONCE on the summary as broker_parity.why_text, which the web tab reads.
FP_WHY = {
    "nofill": "no Webull fill",
    "nobt": "backtest price not on record",
    "noexit": "the backtest has not exited this trade yet",
    "void": "the backtest never took this trade (the engine withdrew the entry)",
    "limit": "the backtest enters at its resting limit; live sends a market order after the fill bar",
    "late": "before 09-26 the book acted one bar after the backtest's fill",
    "nodac": "the bar-close decision did not run for this bar, so the book acted one bar "
             "after the backtest's fill",
    "level": "the backtest exits at its stop or target level; live sends a market order after the bar",
    "eod": "the book flattens at 15:59; the backtest exits on its own bar",
    "kill": "the kill switch closed the book; the backtest exits on its own bar",
    "breaker": "the daily loss breaker closed the book; the backtest exits on its own bar",
    "suspect": "the Webull fill is outside the prices traded in that minute",
}
# RESTING ORB STOP codes: kept out of FP_WHY (published whole as the parity block's
# why_text) and added to why_text only when a published side carries one, so a book that
# never rests an order publishes exactly what it did before.
FP_WHY_RESTING = {
    "diverged": "the resting order filled at Webull at a level where the backtest did not exit",
}
# RESTING ORB STOP (2026-09-29 second review): a resting fill whose level is farther than
# this many R from the backtest's own exit is "diverged" (its gap unexplained), not
# slippage. 1R = |backtest entry - the engine's initial stop|; unknown R -> any gap past a
# cent.
PARITY_RESTING_DIVERGE_R = 0.25
# (E) 2026-09-28: a fill captured before the 09-26 order-status guard (a0d7165e: never
# read another order's record, never take a price from a still-working order) that does
# not fit the tape. Marked here, never rewritten in broker_orders.csv. Keyed by the
# side's base signal id (_broker_signal_id).
SUSPECT_BROKER_FILLS = {
    "qxENGUQ33520260924T161700ZLO": (
        "Webull fill 737.88 is below that minute's low (739.45) -- captured on 09-24, "
        "before the 09-26 check that the record is this order's and that it has filled"),
}
_ENGINE_PX_CACHE = {"key": None, "val": {}}
# NOISE decides at a bar's close from this ET day on (WEBULL_PAPER_TODO.md item 16, owner
# GO 2026-09-26). Before it every NOISE side acted one bar late ("late"); from it a NOISE
# side WITHOUT the decide-at-close tag is a stop exit filled at its level inside the bar
# ("level") or, on an entry, a bar whose close decision did not run ("nodac").
NOISE_DAC_FROM = "2026-09-26"
# api/cloud_signal.py's DECIDE_AT_CLOSE_TAG -- the reason tag on a decide-at-close row.
_DAC_TAG = "decide_at_close"
# The engine's own QQQ bar files (api/cloud_signal.py's _cache_path), searched in this
# order for a bar's open: a bar's open is the open of its first minute either way.
_ENGINE_BAR_FILES = ("QQQ_5m.csv", "QQQ_1m.csv")


def _ref_epoch(ref_time):
    """Epoch seconds of an ISO ref_time carrying its offset ('2026-09-28T12:05:00-04:00'),
    else None."""
    try:
        dt = datetime.fromisoformat(str(ref_time or "").strip())
        return int(dt.timestamp()) if dt.tzinfo is not None else None
    except Exception:
        return None


def _bar_opens_at(epochs, bars_dir):
    """{epoch: open} for the bars STARTING at each of `epochs`, from the engine's own QQQ
    bar files in `bars_dir` (_ENGINE_BAR_FILES, first hit wins; their `time` column is
    the bar's start in epoch seconds). Only the wanted rows are kept. Never raises: {}
    when nothing can be read."""
    want = {int(e) for e in epochs if e is not None}
    out = {}
    if not want or not bars_dir:
        return out
    for name in _ENGINE_BAR_FILES:
        left = want - set(out)
        if not left:
            break
        try:
            with open(os.path.join(bars_dir, name), encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    try:
                        t = int(float(r.get("time") or ""))
                    except (TypeError, ValueError):
                        continue
                    if t in left and t not in out:
                        px = _finite_or_none(r.get("open"))
                        if px is not None and px > 0:
                            out[t] = px
        except Exception:
            continue
    return out


def _engine_prices_by_trade(path=None, bars_dir=None, log=print):
    """{trade_id: {"ENTRY": {px, dec_px, ref_time, reason}, "EXIT": {...}}} -- the
    BACKTEST's own fill price for each side of each trade, from the engine's own signal
    ledger (api/cloud_signal.py's signals.csv). The first row per trade id and event
    wins; SEED rows and rows without a trade id or price are skipped (VOID_ENTRY is kept
    as "VOID": the engine withdrew that entry).

    DECIDE-AT-CLOSE rows (reason tagged _DAC_TAG, NOISE since 09-26): the engine emits
    the decision at the CLOSE of bar D and its ref_price is that close, but the
    backtest FILLS at the OPEN of bar D+1 -- the bar starting at the row's ref_time (see
    api/cloud_signal.py's decide-at-close block). px is that open, read from the
    engine's own bar files in `bars_dir` (default: the ohlc folder beside the ledger's
    cloud_signal folder -- the bars the backtest itself runs on); dec_px keeps the
    decision close. Until D+1's bar is on file (or after it has aged out of the file) px
    falls back to the decision close. Every other row's ref_price already IS the
    backtest's fill (older NOISE rows: the fill-bar open), dec_px None.

    Cached on the ledger's and the bar files' size and mtime. Never raises: {} when the
    ledger cannot be read."""
    try:
        if path is None:
            path = _cs_module().DEFAULT_PATHS["signals_path"]
        st = os.stat(path)
    except Exception:
        return {}
    if bars_dir is None:
        bars_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), "ohlc")
    bar_sig = []
    for name in _ENGINE_BAR_FILES:
        try:
            bst = os.stat(os.path.join(bars_dir, name))
            bar_sig.append((bst.st_mtime_ns, bst.st_size))
        except OSError:
            bar_sig.append(None)
    key = (path, st.st_mtime_ns, st.st_size, bars_dir, tuple(bar_sig))
    if _ENGINE_PX_CACHE["key"] == key:
        return _ENGINE_PX_CACHE["val"]
    out = {}
    dac = []
    try:
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                ev = str(r.get("event") or "").strip().upper()
                if ev == "VOID_ENTRY":
                    ev = "VOID"   # the engine withdrew this entry: the backtest never took it
                if ev not in ("ENTRY", "EXIT", "VOID"):
                    continue
                tid = str(r.get("trade_id") or "").strip()
                px = _f_or_none(r.get("ref_price"))
                if not tid or px is None or not math.isfinite(px):
                    continue
                slot = out.setdefault(tid, {})
                if ev not in slot:
                    slot[ev] = {"px": px, "dec_px": None,
                                "ref_time": str(r.get("ref_time") or ""),
                                "reason": str(r.get("reason") or "")}
                    # RESTING ORB STOP: the engine's initial stop on an ENTRY row (1R for
                    # fill parity's divergence test); only when the row carries one
                    stop_px = _f_or_none(r.get("stop_px")) if ev == "ENTRY" else None
                    if stop_px is not None and math.isfinite(stop_px):
                        slot[ev]["stop_px"] = stop_px
                    if ev != "VOID" and _DAC_TAG in slot[ev]["reason"]:
                        dac.append(slot[ev])
    except Exception as e:
        log(f"[qqq-exec] engine signal ledger read failed (fill parity): {type(e).__name__}: {e}")
        return {}
    if dac:
        opens = _bar_opens_at([_ref_epoch(s["ref_time"]) for s in dac], bars_dir)
        for s in dac:
            o = opens.get(_ref_epoch(s["ref_time"]))
            if o is not None:
                s["dec_px"], s["px"] = s["px"], o
    _ENGINE_PX_CACHE["key"] = key
    _ENGINE_PX_CACHE["val"] = out
    return out


def _r4(v):
    return None if v is None else round(float(v), 4)


def _is_buy(side, intent):
    """True when this side of the round trip is a BUY: opening a long, closing a short."""
    return (str(side or "long").strip().lower() == "long") == (intent == "OPEN")


def _edge_ps(backtest_px, px, buy):
    """Signed $/share, + = `px` is BETTER for us than the backtest's price (paid less on a
    buy, got more on a sell)."""
    return (backtest_px - px) if buy else (px - backtest_px)


def _rail_word(exit_reason):
    w = str(exit_reason or "").strip().split(" ")[0].strip().upper()
    return w if w in RAIL_EXIT_WHY else None


def _finite_or_none(v):
    x = _f_or_none(v)
    return x if (x is not None and math.isfinite(x)) else None


def _is_resting_fill_row(brow):
    """True for a broker_orders.csv row _book_resting_fills wrote (a resting stop/target
    fill at Webull)."""
    return str((brow or {}).get("reason") or "").startswith("resting ")


def _resting_close_fill(rows, total=None):
    """(share-weighted fill px, cent level of the resting row, True) when a trade's CLOSE
    rows include a resting fill: every ok row counts by its shares, in file order, capped
    at `total` (the trade's OPEN shares -- a market close row carries the lot's shares
    even when the adapter sent only what was left after a PARTIAL resting fill). px is
    None when a row that counts has no fill price yet. (None, None, False) when no
    resting row is among them -- every other trade reads _best_broker_row as before."""
    rows = rows or []
    rest = [r for r in rows if _is_resting_fill_row(r)
            and str(r.get("ok")).strip().lower() in ("true", "1")]
    if not rest:
        return None, None, False
    left = float(total) if total and total > 0 else float("inf")
    tot_sh, tot_px, unpriced = 0.0, 0.0, False
    for r in rows:
        if left <= 1e-9:
            break
        if str(r.get("ok")).strip().lower() not in ("true", "1"):
            continue
        sh = _finite_or_none(r.get("shares"))
        if not sh or sh <= 0:
            continue
        sh = min(sh, left)
        left -= sh
        px = _finite_or_none(r.get("broker_fill_px"))
        if px is None:
            unpriced = True
            continue
        tot_sh += sh
        tot_px += px * sh
    level = _finite_or_none(rest[-1].get("shadow_px"))
    return (None if unpriced or not tot_sh else round(tot_px / tot_sh, 4)), level, True


def _webull_fill_for_side(row, intent, by_base):
    """(px, state, note) -- Webull's own fill for one side of a trade. state is "ok",
    "suspect" (captured, but it does not fit the tape -- see SUSPECT_BROKER_FILLS and
    the nightly re-price's own range check) or "none". The captured broker_orders.csv
    fill wins; failing that, the nightly re-price's persisted copy of that same fill
    (entry_px_source / exit_px_source == "webull_fill"), which survives
    broker_orders.csv's own row trim. Never the re-price minute close."""
    trade_id = str(row.get("trade_id") or "").strip()
    px = None
    brow = _broker_order_for(trade_id, intent, by_base) if trade_id else None
    if brow is not None and str(brow.get("ok")).strip().lower() in ("true", "1"):
        px = _finite_or_none(brow.get("broker_fill_px"))
    if trade_id and intent == "CLOSE":
        # a resting fill (maybe partial, then a market close of the rest): share-weighted
        opened = _broker_order_for(trade_id, "OPEN", by_base)
        rpx, _lvl, resting = _resting_close_fill(
            by_base.get(_broker_signal_id(None, None, "CLOSE", trade_id=trade_id)),
            total=_finite_or_none((opened or {}).get("shares")))
        if resting:
            px = rpx
    pfx = "entry" if intent == "OPEN" else "exit"
    if px is None and str(row.get(f"{pfx}_px_source") or "").strip() == "webull_fill":
        px = _finite_or_none(row.get(f"real_{pfx}_px"))
    if px is None:
        return None, "none", ""
    if trade_id:
        base = _broker_signal_id(None, None, intent, trade_id=trade_id)
        if base in SUSPECT_BROKER_FILLS:
            return px, "suspect", SUSPECT_BROKER_FILLS[base]
    if str(row.get(f"{pfx}_fill_check") or "").strip().lower() == "suspect":
        return px, "suspect", FP_WHY["suspect"]
    return px, "ok", ""


def _side_parity(row, intent, by_base, eng):
    """One side (OPEN/CLOSE) of a trade, compared: {bt, wb, bk, fs, edge, dsg, slp, unx,
    why} -- bt = the backtest's price, wb = Webull's fill, bk = the book's price, fs =
    fill state; edge/dsg/slp/unx are signed $/share (+ = Webull better), None when the
    side cannot be compared (no Webull fill, or no backtest price on record yet); why is
    an FP_WHY code ("" when the whole gap is slippage)."""
    leg = str(row.get("leg") or "").strip().upper()
    buy = _is_buy(row.get("side"), intent)
    ev = (eng or {}).get("ENTRY" if intent == "OPEN" else "EXIT")
    bt = ev["px"] if ev else None
    book = _finite_or_none(row.get("entry_px" if intent == "OPEN" else "exit_px"))
    fill, fstate, _fnote = _webull_fill_for_side(row, intent, by_base)
    out = {"bt": _r4(bt), "wb": _r4(fill), "bk": _r4(book), "fs": fstate,
           "edge": None, "dsg": None, "slp": None, "unx": None, "why": ""}
    if fill is None:
        out["why"] = "nofill"
        return out
    if bt is None:
        if (eng or {}).get("VOID") and not (eng or {}).get("ENTRY"):
            out["why"] = "void"
        elif intent == "OPEN" or not (eng or {}).get("ENTRY"):
            out["why"] = "nobt"
        else:
            out["why"] = "noexit"
        return out
    edge = _edge_ps(bt, fill, buy)
    design, unexpl, why = 0.0, 0.0, ""
    dac = "decide_at_close" in str((ev or {}).get("reason") or "")
    if fstate == "suspect":
        unexpl, why = edge, "suspect"
    elif intent == "OPEN":
        if leg in LIMIT_ENTRY_LEGS:
            design, why = edge, "limit"
        elif leg == "NOISE" and not dac:
            design, why = edge, ("late" if _before_noise_dac(ev, row, intent) else "nodac")
    else:
        rail = _rail_word(row.get("exit_reason"))
        tid = str(row.get("trade_id") or "").strip()
        level, resting = None, False
        if tid and leg in LEVEL_EXIT_LEGS:
            _rpx, level, resting = _resting_close_fill(
                by_base.get(_broker_signal_id(None, None, "CLOSE", trade_id=tid)))
        if resting and level is not None:
            # RESTING ORB STOP (2026-09-29 review; second review): the stop rested at
            # Webull and filled at market from its level. Only when the backtest exited
            # AT that level (within a cent) is the backtest -> cent level gap design and
            # the level -> fill gap slippage. Otherwise design is 0: a gap-through (the
            # backtest filled at the open beyond the level) is all slippage, and a fill
            # where the backtest did not exit at all (a print the 5m bars never show,
            # then the engine left at its target or breakeven) is "diverged" -- the
            # level-vs-backtest gap unexplained, so parity flags that trade. This wins
            # over the book's own rail (third review): a resting fill closed Webull's
            # side, so an EOD / KILL / BREAKER exit_reason on the book's trade -- or a
            # fill between the engine's last EXIT and the flatten -- must not book the
            # level-vs-backtest gap as slippage (it would skew the rolling average).
            if abs(bt - level) < 0.01:
                design, why = _edge_ps(bt, level, buy), ""
            else:
                en = (eng or {}).get("ENTRY") or {}
                one_r = (abs(float(en["px"]) - float(en["stop_px"]))
                         if en.get("px") is not None and en.get("stop_px") is not None
                         else None)
                gap = _edge_ps(bt, level, buy)
                far = (abs(gap) > PARITY_RESTING_DIVERGE_R * one_r if one_r
                       else abs(gap) >= 0.01)
                if far:
                    design, unexpl, why = 0.0, gap, "diverged"
                else:
                    design, why = 0.0, ""
        elif rail:
            design = _edge_ps(bt, book, buy) if book is not None else edge
            why = RAIL_EXIT_WHY[rail]
        elif leg in LEVEL_EXIT_LEGS:
            design, why = edge, "level"
        elif leg == "NOISE" and not dac:
            # review 2026-09-28: from 09-26 an untagged NOISE exit is its protective stop
            # (the bandwidth stop in augur_strategies/NOISE_1_0.py), filled at its level
            # inside the bar -- never the pre-09-26 "one bar late" reason on a 09-28 trade.
            design, why = edge, ("late" if _before_noise_dac(ev, row, intent) else "level")
    slip = edge - design - unexpl
    out.update({"edge": _r4(edge), "dsg": _r4(design), "slp": _r4(slip), "unx": _r4(unexpl),
                "why": why})
    return out


def _before_noise_dac(ev, row, intent):
    """True when this NOISE side's bar is before NOISE_DAC_FROM: the engine row's own
    ref_time, else the trade row's entry_ts / exit_ts. Unknown -> False."""
    d = str((ev or {}).get("ref_time") or "")[:10]
    if not d:
        d = str(row.get("entry_ts" if intent == "OPEN" else "exit_ts") or "")[:10]
    return bool(d) and d < NOISE_DAC_FROM


def _cents(ps):
    """Plain words for a signed $/share figure: '12.5 cents a share better'."""
    c = abs(ps) * 100.0
    if c < 0.05:
        return "level with the backtest"
    return f"{c:.1f} cents a share {'better' if ps > 0 else 'worse'}"


def _cents_than(ps):
    """'12.5 cents a share worse than the backtest', or 'level with the backtest' -- never
    'level with the backtest than the backtest' (review 2026-09-28)."""
    c = abs(ps) * 100.0
    return _cents(ps) if c < 0.05 else f"{_cents(ps)} than the backtest"


def _pnl_of_record(row, en, ex):
    """P&L OF RECORD (owner decision 2026-09-28 (B)): Webull's real fill for each side
    when one was captured (and does not look wrong), else the book's own price for that
    side -- labelled "book price, no Webull fill". The backtest's own P&L for the same
    trade rides alongside. Stored ledgers are never rewritten: `pnl` stays the book's
    figure, these are published next to it. {pnl_record, pnl_record_src
    ("webull"/"part"/"book"), pnl_record_note, pnl_backtest}."""
    try:
        shares = _finite_or_none(row.get("shares")) or 0.0
        dir_mult = 1 if str(row.get("side") or "long").strip().lower() == "long" else -1
        notes = []

        def _px(s, pfx):
            if s.get("fs") == "ok" and s.get("wb") is not None:
                return s["wb"], True
            book = _finite_or_none(row.get(f"{pfx}_px"))
            if book is None and pfx == "exit":
                real = _finite_or_none(row.get("real_exit_px"))
                if real is not None:
                    notes.append("exit at the re-price minute close, no Webull fill")
                    return real, False
            if s.get("fs") == "suspect":
                notes.append(f"Webull {pfx} fill looks wrong, book price used")
            elif book is not None:
                notes.append(f"{pfx} at the book price, no Webull fill")
            return book, False

        en_px, en_wb = _px(en, "entry")
        ex_px, ex_wb = _px(ex, "exit")
        bt_pnl = None
        if en.get("bt") is not None and ex.get("bt") is not None:
            bt_pnl = round((ex["bt"] - en["bt"]) * dir_mult * shares, 2)
        if en_px is None or ex_px is None:
            return {"pnl_record": _curve_pnl_book(row), "pnl_record_src": "book",
                    "pnl_record_note": "book price, no Webull fill", "pnl_backtest": bt_pnl}
        rec = round((ex_px - en_px) * dir_mult * shares, 2)
        src = "webull" if (en_wb and ex_wb) else ("part" if (en_wb or ex_wb) else "book")
        note = "book price, no Webull fill" if src == "book" and not any(
            "looks wrong" in n or "minute close" in n for n in notes) else "; ".join(notes)
        return {"pnl_record": rec, "pnl_record_src": src, "pnl_record_note": note,
                "pnl_backtest": bt_pnl}
    except Exception:
        return {"pnl_record": _curve_pnl_book(row), "pnl_record_src": "book",
                "pnl_record_note": "book price, no Webull fill", "pnl_backtest": None}


def _cents_short(ps):
    """Compact signed cents for the per-trade note: '16.0c worse', '12.5c better'."""
    c = abs(ps) * 100.0
    if c < 0.05:
        return "level"
    return f"{c:.1f}c {'better' if ps > 0 else 'worse'}"


def _broker_trade_parity(row, by_base, engine_px=None, log=print):
    """FILL PARITY for one trades.csv row (a dict of strings as csv.DictReader reads it,
    with the re-price sidecar's fields already merged by _merge_reprice): each Webull
    fill against the backtest's own price -- see the section comment above. Returns
    broker_parity_ok (None = not compared yet, never an error; False = FLAGGED;
    True = within the band), broker_parity_note (a short plain line, the chip's hover
    text), and `fp` -- the breakdown the web tab draws: {st, en, ex, exec_ps, gap_usd,
    dsg_usd, exec_usd, flag}, en/ex being _side_parity's per-side dicts. Plus the P&L of
    record fields (_pnl_of_record). Compact on purpose: up to 500 of these ride in one
    Firestore doc. Never raises."""
    try:
        trade_id = str(row.get("trade_id") or "").strip()
        shares = _finite_or_none(row.get("shares")) or 0.0
        eng = (engine_px or {}).get(trade_id) if trade_id else None
        en = _side_parity(row, "OPEN", by_base, eng)
        ex = _side_parity(row, "CLOSE", by_base, eng)
        out = dict(_pnl_of_record(row, en, ex))
        comp = [s for s in (en, ex) if s.get("edge") is not None]
        if not comp:
            if not trade_id:
                note = "not compared: no trade id (closed before 09-22)"
            else:
                whys = [s["why"] for s in (en, ex) if s.get("why")]
                real = [w for w in whys if w != "nofill"]
                code = (real or whys or ["nofill"])[0]
                note = "not compared: " + FP_WHY.get(code, FP_WHY_RESTING.get(code, code))
            out.update({"broker_parity_ok": None, "broker_parity_note": note,
                        "fp": {"st": "not compared", "en": en, "ex": ex, "exec_ps": None,
                               "gap_usd": None, "dsg_usd": None, "exec_usd": None,
                               "flag": False}})
            return out
        gap = sum(s["edge"] for s in comp)
        dsg = sum(s["dsg"] for s in comp)
        exe = sum(s["slp"] + s["unx"] for s in comp)
        # PER FILL (the band is cents a share on ONE fill, like the audit's "11.6-cent
        # average gap" -- never the round trip's sum): a trade is FLAGGED when any one
        # of its fills is more than PARITY_TRADE_TOL_PS WORSE than the backtest once the
        # known design gap is taken out, or when a fill does not fit the tape at all
        # (unexplained). A fill that beat the backtest is shown, never flagged -- that
        # was the old note's "36 of 36 miss" failure.
        worse = [s for s in comp if (s["slp"] + s["unx"]) < -PARITY_TRADE_TOL_PS - 1e-9]
        odd = [s for s in comp if abs(s["unx"]) >= 0.00005]
        # ROUND TRIP (PARITY_ROUND_TRIP, off until the owner says yes): a trade whose two
        # fills TOGETHER are more than the band worse. Only adds flags, never removes.
        rt_worse = bool(PARITY_ROUND_TRIP and len(comp) == 2
                        and exe < -PARITY_TRADE_TOL_PS - 1e-9)
        flag = bool(worse or odd or rt_worse)
        st = ("entry and exit" if len(comp) == 2 else
              ("entry only" if en["edge"] is not None else "exit only"))
        side_txt = []
        for nm, s in (("entry", en), ("exit", ex)):
            if s["edge"] is None:
                side_txt.append(f"{nm} not compared ({FP_WHY.get(s['why'], s['why'])})")
                continue
            t = f"{nm} {_cents_short(s['edge'])}"
            if abs(s["unx"]) >= 0.00005:
                t += (" (the resting fill and the backtest's exit differ)"
                      if s.get("why") == "diverged" else " (fill does not fit the tape)")
            elif abs(s["dsg"]) >= 0.00005:
                t += f" (design {_cents_short(s['dsg'])}, slippage {_cents_short(s['slp'])})"
            side_txt.append(t)
        usd = gap * shares
        note = (f"Webull vs backtest a share: {', '.join(side_txt)}; "
                f"{'+' if usd >= 0 else '-'}${abs(usd):.2f} at {shares:g} sh")
        if worse:
            note = f"FLAGGED, a fill over {PARITY_TRADE_TOL_PS * 100:.0f}c a share worse -- " + note
        elif rt_worse:
            note = (f"FLAGGED, the two fills together over {PARITY_TRADE_TOL_PS * 100:.0f}c a "
                    f"share worse -- " + note)
        elif odd:
            note = ("FLAGGED, the resting order filled where the backtest did not exit -- "
                    if all(s.get("why") == "diverged" for s in odd) else
                    "FLAGGED, a Webull fill does not fit the tape -- ") + note
        out.update({"broker_parity_ok": not flag, "broker_parity_note": note,
                    "fp": {"st": st, "en": en, "ex": ex, "exec_ps": _r4(exe),
                           "gap_usd": round(gap * shares, 2),
                           "dsg_usd": round(dsg * shares, 2),
                           "exec_usd": round(exe * shares, 2), "flag": flag}})
        return out
    except Exception as e:
        log(f"[qqq-exec] fill parity calc failed for a trade row: {type(e).__name__}: {e}")
        return {"broker_parity_ok": None,
                "broker_parity_note": f"parity calc failed: {type(e).__name__}",
                "fp": None, "pnl_record": _curve_pnl_book(row), "pnl_record_src": "book",
                "pnl_record_note": "book price, no Webull fill", "pnl_backtest": None}


_NT_MIRROR_NOTE = "n/a -- this trade mirrors NinjaTrader, see NT parity"


# A side whose whole gap is design by construction (slippage fixed at 0) -- see
# _side_parity. Left out of the running slippage average (_roll_block).
DESIGN_ONLY_WHY = ("limit", "level", "late", "nodac")
# Every side whose gap has a design part: the all-design codes plus the book's own rails.
DESIGN_WHY = DESIGN_ONLY_WHY + tuple(RAIL_EXIT_WHY.values())


def _side_is_suspect(s):
    """True for a compared side whose Webull fill does not fit the tape (fs "suspect",
    or any unexplained part)."""
    return (s.get("fs") == "suspect" or s.get("why") == "suspect"
            or abs(s.get("unx") or 0.0) >= 0.00005)


def _roll_block(rows):
    """{n, fills, fills_compared, suspect_fills, design_only_fills, avg_exec_ps,
    avg_gap_ps, avg_dsg_ps, flagged, flag} over the last PARITY_ROLL_N compared trades
    (an oldest-first list of fp dicts). Averages are PER FILL, signed, + better.

    avg_exec_ps is the running SLIPPAGE average the 5-cent flag reads, over `fills` --
    only the fills that have a slippage part. Left out of it (review 2026-09-28):
      * a SUSPECT capture (a fill that does not fit the tape): its trade already carries
        its own CHECK FILL flag, and its unexplained part must never average in -- on
        the 09-28 rows one bad 09-24 ENGU-Q capture (+1.49/sh in the helpful direction)
        made up nearly all of an "8.6 cents a share better" board read and would offset
        about 30 fills running 5 cents worse; counted in `suspect_fills`;
      * an ALL-DESIGN side (limit / level / late, DESIGN_ONLY_WHY): its slippage is 0 by
        construction, so it would only pull the average toward zero; counted in
        `design_only_fills`.
    None (never 0) when no fill in the window has a slippage part yet.
    avg_gap_ps / avg_dsg_ps are the whole gap and the design gap alone over every
    compared fill that is not suspect (`fills_compared`). med_dsg_ps is the MIDDLE design
    gap over the `dsg_fills` fills that carry one (DESIGN_WHY) -- the typical figure the
    board shows (review 2026-09-28: one multi-day ENGU-Q rail exit, 671.5 cents, swamped
    the average).
    flag = avg_exec_ps worse than -PARITY_ROLL_TOL_PS (adverse only)."""
    win = rows[-PARITY_ROLL_N:]
    sides = [s for f in win for s in (f.get("en") or {}, f.get("ex") or {})
             if s.get("edge") is not None]
    good = [s for s in sides if not _side_is_suspect(s)]
    slip = [s for s in good if s.get("why") not in DESIGN_ONLY_WHY]
    out = {"n": len(win), "fills": len(slip), "fills_compared": len(good),
           "suspect_fills": len(sides) - len(good),
           "design_only_fills": len(good) - len(slip),
           "avg_exec_ps": None, "avg_gap_ps": None, "avg_dsg_ps": None,
           "med_dsg_ps": None, "dsg_fills": 0,
           "flagged": sum(1 for f in win if f.get("flag")), "flag": False}
    if good:
        out["avg_gap_ps"] = _r4(sum(s["edge"] for s in good) / len(good))
        out["avg_dsg_ps"] = _r4(sum(s["dsg"] for s in good) / len(good))
    dsg = sorted(float(s.get("dsg") or 0.0) for s in good if s.get("why") in DESIGN_WHY)
    if dsg:
        mid = len(dsg) // 2
        out["med_dsg_ps"] = _r4(dsg[mid] if len(dsg) % 2 else (dsg[mid - 1] + dsg[mid]) / 2)
        out["dsg_fills"] = len(dsg)
    if slip:
        avg = sum(s["slp"] for s in slip) / len(slip)
        out["avg_exec_ps"] = _r4(avg)
        out["flag"] = bool(avg < -PARITY_ROLL_TOL_PS - 1e-9)
    return out


def _parity_why_text(rows):
    """FP_WHY, plus the FP_WHY_RESTING codes some published side actually carries."""
    out = dict(FP_WHY)
    used = {((t.get("fp") or {}).get(k) or {}).get("why") for t in rows or []
            for k in ("en", "ex")}
    out.update({k: v for k, v in FP_WHY_RESTING.items() if k in used})
    return out


def _broker_parity_summary(trades_all):
    """Headline FILL PARITY read -- see _broker_trade_parity. NinjaTrader-mirrored rows
    never count here. The window is the last PARITY_ROLL_N compared trades (by exit
    time): `checked`/`failed`/`ok` count inside it (so one old bad trade ages out, and
    _build_readiness reads the same window), `board`/`legs` carry the signed rolling
    averages and their flags, `checked_all`/`flagged_all` the whole history.
    `webull_usd`/`backtest_usd` add up the P&L of record and the backtest's P&L over the
    trades where both are known (`n_both`)."""
    def _ts(t):
        return str(t.get("exit_ts") or t.get("entry_ts") or "")
    rows = [t for t in trades_all
            if str(t.get("signal_source") or "").strip().lower() != "ninjatrader"]
    rows = sorted(rows, key=_ts)
    comp, not_checked = [], 0
    by_leg = {}
    worst = None
    webull_usd = backtest_usd = 0.0
    n_both = 0
    for t in rows:
        fp = t.get("fp") or {}
        rec, bt = _finite_or_none(t.get("pnl_record")), _finite_or_none(t.get("pnl_backtest"))
        if rec is not None and bt is not None and t.get("pnl_record_src") == "webull":
            webull_usd += rec
            backtest_usd += bt
            n_both += 1
        if t.get("broker_parity_ok") is None or fp.get("exec_ps") is None:
            not_checked += 1
            continue
        comp.append(fp)
        by_leg.setdefault(str(t.get("leg") or "?"), []).append(fp)
        if fp.get("flag") and (worst is None or fp["exec_ps"] < worst[0]):
            worst = (fp["exec_ps"], t.get("broker_parity_note") or "")
    board = _roll_block(comp)
    legs = {leg: _roll_block(v) for leg, v in by_leg.items()}
    checked = board["n"]
    failed = board["flagged"]
    tol_c = PARITY_TRADE_TOL_PS * 100
    roll_c = PARITY_ROLL_TOL_PS * 100
    if not comp:
        note = (f"{not_checked} trade(s) have no Webull fill or no backtest price to compare "
                f"yet -- not an error, just not compared yet" if not_checked else
                "no engine-signal trades recorded yet")
    else:
        if board["avg_exec_ps"] is None:
            note = (f"last {checked} compared trade(s): no Webull fill with slippage to "
                    f"compare yet (limit entries, stop or target exits and NOISE before "
                    f"09-26 are all design gap)")
        else:
            ax = board["avg_exec_ps"]
            note = (f"last {checked} compared trade(s): Webull fills "
                    f"{'were' if abs(ax) * 100 < 0.05 else 'averaged'} {_cents_than(ax)} "
                    f"on slippage over {board['fills']} fill(s), known design gaps left out "
                    f"(flag at {roll_c:.0f} cents worse)")
        if board["suspect_fills"]:
            note += (f"; {board['suspect_fills']} fill(s) that do not fit the tape left out "
                     f"of the average")
        if board["med_dsg_ps"] is not None:
            note += (f"; the typical design gap (middle of {board['dsg_fills']} fill(s)) was "
                     f"{_cents_than(board['med_dsg_ps'])}")
        rt_txt = ", or a trade's two fills together," if PARITY_ROUND_TRIP else ""
        note += (f"; {failed} trade(s) flagged (a fill{rt_txt} more than {tol_c:.0f} cents "
                 f"a share worse, or a fill that does not fit the tape)"
                 if failed else f"; no fill more than {tol_c:.0f} cents a share worse")
        flagged_legs = [k for k, v in legs.items() if v["flag"]]
        if board["flag"] or flagged_legs:
            note += (" -- running average too far worse than the backtest"
                     + (f" on {', '.join(sorted(flagged_legs))}" if flagged_legs else ""))
    return {"checked": checked, "ok": checked - failed, "failed": failed,
            "not_checked": not_checked, "checked_all": len(comp),
            "flagged_all": sum(1 for f in comp if f.get("flag")),
            "board": board, "legs": legs,
            "board_flag": bool(board["flag"] or any(v["flag"] for v in legs.values())),
            "worst_exec_ps": worst[0] if worst else None,
            "worst_note": worst[1] if worst else "",
            "tol_trade_ps": PARITY_TRADE_TOL_PS, "tol_roll_ps": PARITY_ROLL_TOL_PS,
            "round_trip_check": PARITY_ROUND_TRIP,
            "roll_n": PARITY_ROLL_N, "why_text": _parity_why_text(rows),
            "webull_usd": round(webull_usd, 2), "backtest_usd": round(backtest_usd, 2),
            "n_both": n_both, "note": note}


def _apply_broker_parity(trades_all, broker_by_base, engine_px=None, log=print):
    """Updates every row of trades_all IN PLACE with its fill-parity and P&L-of-record
    fields (see _broker_trade_parity) -- factored out of _build_doc so the dispatch rule
    itself ("which rows get the check") is unit-testable on its own. A row whose
    signal_source is "ninjatrader" (a genuine NinjaTrader-mirrored trade, see module
    docstring) is left with a clear placeholder instead: _trade_parity's OWN NT-parity
    fields on that row (parity_ok/parity_note, computed separately in _build_doc,
    BEFORE this runs) are exactly what applied to it before feature #56 existed, and
    this function never reads or writes them. Never raises."""
    for row in trades_all:
        if str(row.get("signal_source") or "").strip().lower() == "ninjatrader":
            row.update({"broker_parity_ok": None, "broker_parity_note": _NT_MIRROR_NOTE,
                        "fp": None, "pnl_record": _curve_pnl_book(row),
                        "pnl_record_src": "book", "pnl_record_note": "",
                        "pnl_backtest": None})
        else:
            row.update(_broker_trade_parity(row, broker_by_base, engine_px=engine_px, log=log))


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
        BROKER_ORDERS_KEEP trim (see BROKER_ORDER_COLS). There is no record either way, so
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
    """Book vs broker headline totals over every closed trade in trades_all.
    `book_net` is the BOOK's own figure (_curve_pnl_book: pnl, else the re-priced
    real_pnl). `record_net` is the P&L OF RECORD (_curve_pnl: Webull's fills, the book
    price per side where none was captured -- what the equity curve, the closed-trades
    table and the calendar add up since 2026-09-28). `broker_net` is record_net with
    every book_only trade left out -- what Webull's own side actually made (the tab's
    "broker made ... of that" line). Never raises -- a trade whose own pnl fields are
    unusable contributes 0.0, the same as the curve."""
    book_net = 0.0
    record_net = 0.0
    broker_net = 0.0
    book_only_n = 0
    for t in trades_all:
        book_net += _curve_pnl_book(t)
        pnl = _curve_pnl(t)
        record_net += pnl
        if t.get("book_only"):
            book_only_n += 1
        else:
            broker_net += pnl
    return {"book_net": round(book_net, 2), "record_net": round(record_net, 2),
            "broker_net": round(broker_net, 2), "book_only_count": book_only_n}


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
    """What one closed trade adds to the curve (P&L OF RECORD, owner decision 2026-09-28
    (B)): `pnl_record` -- Webull's real fills, else the book price per side, see
    _pnl_of_record -- when _apply_broker_parity has put one on the row, else the book's
    own figure (_curve_pnl_book). The web tab's qePnlOf applies the same rule."""
    v = _finite_or_none(t.get("pnl_record")) if isinstance(t, dict) else None
    if v is not None:
        return v
    return _curve_pnl_book(t)


def _legs_record_today(trades_all, day):
    """{leg: {pnl, n, book}} -- each strategy's TODAY figure at the P&L of record (Ledger
    unify 13, 2026-10-05): the trades that CLOSED on `day` (the New York close day,
    exit_ts -- a trade opened yesterday and closed today counts today), each at
    _curve_pnl, the exact rule today.realized_pnl_record sums, so the strategy rows add
    up to the hero's today figure. `book` = how many of those trades are not at Webull's
    fills on both sides (a missing or suspect fill, or a book-only trade whose open
    Webull refused) -- the tab labels them. Open lots are not trades yet and never
    count. One small map per leg, never per trade. Never raises."""
    out = {}
    try:
        for t in trades_all or []:
            if str(t.get("exit_ts") or "")[:10] != day:
                continue
            leg = str(t.get("leg") or "").strip() or "?"
            b = out.setdefault(leg, {"pnl": 0.0, "n": 0, "book": 0})
            b["pnl"] += _curve_pnl(t)
            b["n"] += 1
            if str(t.get("pnl_record_src") or "") != "webull":
                b["book"] += 1
        for b in out.values():
            b["pnl"] = round(b["pnl"], 2)
    except Exception:
        return {}
    return out


def _curve_pnl_book(t):
    """The BOOK's own figure for one closed trade: `pnl` when it is a real number, else
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
# "price_source" (item 11, 2026-09-25): tools/qqq_reprice.py now records which of
# webull_stream_1m/webull_rest_1m/yfinance_1m actually priced each trade. Purely
# additive -- nothing in index.html reads it yet, and "source" (kept for backward
# compatibility, now carrying the same value) is unaffected.
REPRICE_MERGE_FIELDS = ["real_entry_px", "real_exit_px", "real_pnl", "slip_entry_ps",
                        "slip_exit_ps", "repriced_at", "source", "price_source", "note",
                        # 2026-09-28 (C/E): which price each side used ("webull_fill" or
                        # the minute-close source) and the fill-vs-tape range check --
                        # read by _webull_fill_for_side.
                        "entry_px_source", "exit_px_source", "entry_fill_check",
                        "exit_fill_check"]


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


REPRICE_FROM_HHMM = (16, 20)          # first try, ET
REPRICE_RETRY_FROM_HHMM = (19, 0)     # the one evening retry, ET
REPRICE_RETRY_MIN_GAP_SEC = 1800.0    # and never within 30 min of the failed try
REPRICE_MAX_TRIES = 2
REPRICE_TIMEOUT_SEC = 120


def _run_reprice_tool(script, log=print):
    """Run tools/qqq_reprice.py --apply once: (ok, detail). ok only on exit code 0 -- the
    tool exits non-zero on an error (finding 27). Its own output still goes to this
    process's log, as before. Never raises."""
    try:
        r = subprocess.run([sys.executable, script, "--apply"], timeout=REPRICE_TIMEOUT_SEC,
                           check=False)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {REPRICE_TIMEOUT_SEC}s"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    rc = getattr(r, "returncode", None)
    if rc != 0:
        return False, f"exit code {rc}"
    return True, "exit code 0"


def _maybe_run_reprice(state, nowdt, log=print):
    """Once per ET weekday, after 16:20 ET, shells out to tools/qqq_reprice.py --apply
    (the sidecar-writing tool owned by a different agent). Non-fatal if the tool
    doesn't exist yet, times out, or errors -- this adapter's own trading logic must
    never depend on it.

    FAILURES ARE NOT "DONE" (sweep 2026-10-05, finding 27). reprice_done_date used to be
    stamped BEFORE the run and the exit code ignored, so a failed or crashed run left the
    day's real-price P&L and slippage missing with no retry and nothing said. Now:
      * reprice_done_date is stamped only after a run that exits 0;
      * a failed run (non-zero exit, timeout, tool missing) is kept in
        state["reprice_fail"] = {date, tries, last_try_epoch, last_error, alerted} plus a
        'reprice_failed' event, and is tried ONCE more from 19:00 ET (and at least 30 min
        after the failed try, for a first try that itself ran late);
      * if that retry fails too: one push and one more event, then nothing more that day.
        A first try that fails too late for the retry to fit before midnight ET (after
        about 23:30) pushes at once instead;
      * a MISSING tools/qqq_reprice.py now counts as a failure and pushes (it used to be a
        quiet skip): the box should always have it.
    The next weekday starts clean (the tool re-prices every trade still missing a row)."""
    try:
        if not _is_weekday(nowdt):
            return
        if _et_hhmm(nowdt) < REPRICE_FROM_HHMM:
            return
        today = nowdt.strftime("%Y-%m-%d")
        if state.get("reprice_done_date") == today:
            return
        fail = state.get("reprice_fail")
        if not isinstance(fail, dict) or fail.get("date") != today:
            if fail is not None:
                state.pop("reprice_fail", None)
            fail = None
        now_epoch = nowdt.timestamp()
        if fail is not None:
            if fail.get("alerted") or int(fail.get("tries") or 0) >= REPRICE_MAX_TRIES:
                return
            if _et_hhmm(nowdt) < REPRICE_RETRY_FROM_HHMM:
                return
            if now_epoch - float(fail.get("last_try_epoch") or 0.0) < REPRICE_RETRY_MIN_GAP_SEC:
                return
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(repo_root, "tools", "qqq_reprice.py")
        if not os.path.exists(script):
            ok, detail = False, f"tool not found at {script}"
        else:
            ok, detail = _run_reprice_tool(script, log=log)
        tries = int((fail or {}).get("tries") or 0) + 1
        if ok:
            state["reprice_done_date"] = today
            state.pop("reprice_fail", None)
            _log_event(state, "reprice", "Daily broker reprice reconciliation ran"
                       + (f" (on try {tries})" if tries > 1 else ""), log=log)
            return
        fail = {"date": today, "tries": tries, "last_try_epoch": now_epoch,
                "last_error": detail, "alerted": False}
        state["reprice_fail"] = fail
        # the retry must fit before midnight ET (the record is per ET date): a first try that
        # failed too late for one (after ~23:30 ET) alerts now instead of being forgotten
        day0 = nowdt.replace(hour=0, minute=0, second=0, microsecond=0)
        retry_at = max(now_epoch + REPRICE_RETRY_MIN_GAP_SEC,
                       day0.replace(hour=REPRICE_RETRY_FROM_HHMM[0],
                                    minute=REPRICE_RETRY_FROM_HHMM[1]).timestamp())
        room = retry_at < (day0 + timedelta(days=1)).timestamp()
        if tries < REPRICE_MAX_TRIES and room:
            line = (f"Nightly re-price failed ({detail}) -- trying once more after "
                    f"{REPRICE_RETRY_FROM_HHMM[0]:02d}:{REPRICE_RETRY_FROM_HHMM[1]:02d} ET")
            log(f"[qqq-exec] {line}")
            _log_event(state, "reprice_failed", line, log=log)
            return
        how = "twice today" if tries >= REPRICE_MAX_TRIES else "too late tonight to try again"
        line = (f"Nightly re-price failed {how} ({detail}). Today's trades have no "
                f"real-price P&L or slippage yet -- run tools/qqq_reprice.py --apply on the "
                f"box by hand, or it catches up after tomorrow's close.")
        log(f"[qqq-exec] {line}")
        _log_event(state, "reprice_failed", line, log=log)
        fail["alerted"] = True
        _phone_note(state, "reprice_failed", today, ntfy_push.plain(
            "QQQ book", "re-price failed", None,
            "Today's real-price P&L and slippage are missing: the nightly re-price failed "
            + ("twice." if tries >= REPRICE_MAX_TRIES else "too late to try again."),
            "nothing - it catches up after tomorrow's close; ask Claude (PAPER-WB chat) to "
            "run it sooner", priority="low"), log=log)      # Do: nothing -> information
    except Exception as e:
        log(f"[qqq-exec] reprice scheduling failed: {type(e).__name__}: {e}")


EOD_GAVE_UP_LOOK_AFTER_CLOSE_SEC = 300.0      # the engine gives up at close + 5 min
EOD_GAVE_UP_LOOK_FOR_SEC = 3 * 3600.0
EOD_GAVE_UP_CHECK_EVERY_SEC = 60.0
EOD_NOT_SETTLED_AFTER_CLOSE_SEC = 600.0       # no settle and no give-up by then: engine down


def _eod_gave_up_order_words(state):
    """The last sentence of the give-up event: no order depends on a late settle -- unless a
    lot is held overnight (HOLD OVERNIGHT), whose exit may then come with tomorrow's first
    step and is sold at the open."""
    held = _held_shares_by_leg(state)
    if held:
        return (f"{_legs_words(sorted(held))} is held overnight: its exit may come with "
                f"tomorrow's first step and is sold at market when the market opens.")
    return "No order depends on it."


def _maybe_note_eod_gave_up(state, nowdt, log=print, read_cs_state=None):
    """EOD SETTLE GAVE UP (sweep 2026-10-05, finding 30). When api/cloud_signal.py could not
    settle the day (its last bar never arrived by close + 5 min) it records
    state["eod_gave_up"][date] in ITS state.json. This turns that record into ONE event on
    this book's timeline -- what the board shows -- so the morning's late exits (old
    ref_time) are explained where the owner looks. Reads the engine's state at most once a
    minute, from close + 5 min for three hours, until noted. ENGINE DOWN THROUGH THE WINDOW:
    when the engine stepped earlier today but by close + 10 min holds neither
    eod_settled[today] nor eod_gave_up[today] (its thread was down or stuck), this logs the
    same event. NO PUSH from here (ONE ALERTER PER PROBLEM, api/ntfy_push): the phone push
    for "today's close was not settled" is tools/webull_freshness.py's eod_settled check,
    which sees both cases. Returns True when it logged the event. Never raises."""
    try:
        d = nowdt.date()
        if not market_calendar.is_session(d):
            return False
        today = d.isoformat()
        if state.get("_eod_gave_up_noted") == today:
            return False
        hh, mm = _hhmm(market_calendar.session_close_et(d))
        close_dt = nowdt.replace(hour=hh, minute=mm, second=0, microsecond=0)
        since = (nowdt - close_dt).total_seconds()
        if since < EOD_GAVE_UP_LOOK_AFTER_CLOSE_SEC or \
                since > EOD_GAVE_UP_LOOK_AFTER_CLOSE_SEC + EOD_GAVE_UP_LOOK_FOR_SEC:
            return False
        now_epoch = nowdt.timestamp()
        if now_epoch - float(state.get("_eod_gave_up_checked_at") or 0.0) < \
                EOD_GAVE_UP_CHECK_EVERY_SEC:
            return False
        state["_eod_gave_up_checked_at"] = now_epoch
        if read_cs_state is None:
            cs = _cs_module()
            cs_state = cs._load_state(cs.DEFAULT_PATHS)
        else:
            cs_state = read_cs_state()
        cs_state = cs_state if isinstance(cs_state, dict) else {}
        rec = (cs_state.get("eod_gave_up") or {}).get(today)
        if not rec:
            if (cs_state.get("eod_settled") or {}).get(today):
                state["_eod_gave_up_noted"] = today        # settled: nothing more to look for
                return False
            # ENGINE NEVER SETTLED (no settle, no give-up record) by close + 10 min: its thread
            # was down or stuck through the whole window, so it could not record either. Only
            # when the engine stepped earlier today ON THIS HOST (generated_at today): a host
            # whose engine does not write here is the feed check's business, not this one.
            gen = str(cs_state.get("generated_at") or "")[:10]
            if since < EOD_NOT_SETTLED_AFTER_CLOSE_SEC or gen != today:
                return False
            last_at = str(cs_state.get("generated_at"))[11:16]
            text = (f"The signal engine never settled today: no record of the last bar "
                    f"{(since / 60):.0f} min after the close (its last step was {last_at} ET -- "
                    f"it may be stopped or stuck). Today's end-of-day exits will be written "
                    f"tomorrow morning, stamped with today's last-bar time, so today's signal "
                    f"ledger and parity are off until then. {_eod_gave_up_order_words(state)}")
            _log_event(state, "eod_settle_gave_up", text, log=log)
            log(f"[qqq-exec] {text}")
            state["_eod_gave_up_noted"] = today
            return True
        why = (rec.get("why") if isinstance(rec, dict) else None) or "the last bar never arrived"
        text = (f"The signal engine could not settle today ({why}): today's end-of-day exits "
                f"will be written tomorrow morning, stamped with today's last-bar time, so "
                f"today's signal ledger and parity are off until then. "
                f"{_eod_gave_up_order_words(state)}")
        _log_event(state, "eod_settle_gave_up", text, log=log)
        log(f"[qqq-exec] {text}")
        state["_eod_gave_up_noted"] = today
        return True
    except Exception as e:
        log(f"[qqq-exec] eod settle give-up check failed (non-fatal): {type(e).__name__}: {e}")
        return False


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
            missing.append(f"{live_parity_failed} of the last {live_parity_checked} "
                           f"compared trade(s) are past the per-trade Webull fill limit")
        # the window above drops a flagged trade after PARITY_ROLL_N more; the whole
        # history's count rides beside it so an old flag is never silently forgotten
        # (display only -- it does not change `ready`)
        flagged_all = int(parity.get("flagged_all") or 0)
        if flagged_all > live_parity_failed:
            missing.append(f"{flagged_all - live_parity_failed} older flagged trade(s) "
                           f"before the last {live_parity_checked} (still on record)")
        if parity.get("board_flag"):
            ready = False
            missing.append("the running average of Webull fills is too far worse than "
                           "the backtest")
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
               "live_parity_flagged_all": flagged_all,
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
        # P&L OF RECORD (2026-09-28): Webull's fills (book price where none was captured),
        # the book's own figure beside it; an older doc without it reads the book's.
        book_pnl = doc["today"]["realized_pnl"]
        rec_pnl = doc["today"].get("realized_pnl_record")
        pnl_txt = (f"P&L ${rec_pnl:.2f} at Webull fills (book ${book_pnl:.2f})"
                   if isinstance(rec_pnl, (int, float)) else f"P&L ${book_pnl:.2f}")
        # FILL PARITY (2026-09-28): this book's own check (Webull fills vs the backtest)
        # when published, else the old summary
        parity = doc.get("broker_parity") or doc["parity"]
        today_feed = next((d for d in doc["feed_days"] if d["date"] == today), None)
        uptime_txt = f"{today_feed['uptime_pct'] * 100:.1f}%" if today_feed else "n/a"
        rail_trips = 1 if doc.get("breaker_tripped") else 0
        # EXIT SAFETY item 4 (2026-09-26; narrowed 2026-09-26 review): the item-4 check
        # (_maybe_check_webull_flat_after_eod, run earlier in the same tick loop once the
        # flatten/re-sends have had their window) stashes its verdict on state, dated. A
        # result whose date is not TODAY -- absent entirely (never checked), or left over
        # from a prior day (a crash/restart around the flatten, or a kill day before this
        # fix ran the check at all) -- must never be shown as today's answer: this is
        # exactly the false reassurance item 4 exists to prevent, so it prints
        # 'not checked' instead of silently defaulting to 'yes'.
        flat_info = state.get("_webull_flat_after_eod") or {}
        held = flat_info.get("held") if isinstance(flat_info.get("held"), dict) else {}
        if flat_info.get("date") != today:
            flat_txt = "Webull flat: not checked"
        elif flat_info.get("flat") is False and held:
            flat_txt = (f"Webull flat: NO ({flat_info.get('shares')} shares; held overnight "
                        f"{_held_words(held)}, {flat_info.get('off', '?')} off)")
        elif flat_info.get("flat") is False:
            flat_txt = f"Webull flat: NO ({flat_info.get('shares')} shares)"
        elif flat_info.get("flat") is None:
            flat_txt = "Webull flat: could not verify"
        elif held:
            flat_txt = f"Webull flat: yes, except held overnight ({_held_words(held)})"
        else:
            flat_txt = "Webull flat: yes"
        roll_txt = " (running average worse)" if parity.get("board_flag") else ""
        all_txt = (f", all {parity['checked_all']}/{parity['flagged_all']}"
                   if "checked_all" in parity else "")
        msg = (f"Trades {n} | {pnl_txt} | fills vs backtest checked/flagged last "
              f"{parity['checked']}/{parity['failed']}{all_txt}{roll_txt} | feed uptime {uptime_txt} | "
              f"rail trips {rail_trips} | {flat_txt}")
        log(f"[qqq-exec] EOD summary: {msg}")
        # WEBULL PUSH PLAN 10-07, group G: the day summary is a low note; the full line stays
        # in the log and the timeline event
        pnl = rec_pnl if isinstance(rec_pnl, (int, float)) else book_pnl
        where = "at Webull prices" if isinstance(rec_pnl, (int, float)) else "in the book"
        held_n = int(sum(abs(int(q)) for q in held.values())) if held else 0
        flat_words = ("Webull's position was not checked" if flat_info.get("date") != today
                      else "Webull is NOT flat" if flat_info.get("flat") is False
                      else "Webull's position could not be read" if flat_info.get("flat") is None
                      else (f"Webull holds only {_legs_words(sorted(held))}'s {held_n} shares "
                            f"held overnight") if held
                      else "Webull is flat")
        if not n:
            problem = f"No trades today; {flat_words}"
        else:
            problem = (f"{'Made' if float(pnl or 0) >= 0 else 'Lost'} {ntfy_push.usd(pnl or 0)} "
                       f"today {where}; {flat_words}")
        _say(state, "day_summary", today, ntfy_push.plain(
            PHONE_AREA, "day done", None, problem, "nothing", priority="low"), log=log)
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

# -- SHADOW TRADES (2026-10-09, MANAGER #87 (d)) -------------------------------------------
# The WEBULL PAPER board's "Shadow - not counted" fold reads ONE separate top-level key of
# the status doc, "shadow_trades": the SHADOW LEGS' would-be trades (api/cloud_signal.py
# SHADOW_LEGS -- ENGUQ_335, NOISE_422_PLAIN/FIXED/KEEL), read from their own ledger
# <cloud_signal state_dir>/shadow/signals.csv and paired by tools/shadow_legs_report.py's own
# read_rows/pair_trades, so the board and that report agree on what a trade is.
#   {"as_of", "source", "base_shares", "legs": [...], "capped": N, "trades": [newest entry
#    first: {leg, trade_id, side, entry_time, entry_px, exit_time, exit_px, size, shares,
#    seeded, pnl_usd, mark_px, unreal_usd}], "error": only when the ledger could not be read}
# DISPLAY ONLY, READ ONLY. Nothing here reaches an order, a lot, a rail, the breaker,
# readiness, trades_all, cum_pnl, any today/P&L figure or the export: it is built from its
# own file into its own key, and fitted into the Firestore budget AFTER trades_all has been
# (_fit_shadow_trades), so it can never cost trades_all a row. Any failure publishes
# {"error": ..., "trades": []} and the rest of the doc builds exactly as before. The parsed
# ledger is cached by the file's (mtime, size), so the tick never re-reads an unchanged file.
# OPEN TRADES ARE NEVER CUT while a closed one is left: the count cap and the budget fit drop
# the oldest CLOSED trades. Newest-entry-first puts a long hold (ENGU-Q's multi-day hold) LAST,
# so a plain tail cut would drop exactly the trade a leg still holds and the board would show
# that leg flat (_cap_shadow_trades, _fit_shadow_trades).
# SIZE: ~300 bytes and 15 counted index entries a trade, so the 300-trade cap is ~90 KB and
# ~4,500 entries at most (~70 trades on 2026-10-08) -- and whatever the doc has left under
# FS_DOC_BUDGET_* bounds it again.
SHADOW_TRADES_CAP = 300
SHADOW_TRADES_SOURCE = "cloud_signal/shadow/signals.csv"
SHADOW_BASE_SHARES_FALLBACK = 10   # tools/shadow_legs_report.BASE_SHARES, if that cannot import
_SHADOW_LEDGER_COLS = ("leg", "event", "side", "ref_time", "ref_price", "trade_id")
# key (path, mtime_ns, size) -> value (trades, legs, error); "logged": the last error logged
_SHADOW_TRADES_CACHE = {"key": None, "value": None, "logged": None}
# timeframe -> ((path, mtime_ns, size), (bar_time, close) or None)
_SHADOW_MARK_CACHE = {}


def _shadow_report():
    """tools/shadow_legs_report.py, imported lazily (like _cs_module) so a broken report
    module can only ever cost the shadow block, never this module's import."""
    import tools.shadow_legs_report as slr
    return slr


def _shadow_stat_key(path):
    st = os.stat(path)
    return (path, st.st_mtime_ns, st.st_size)


def _parse_shadow_ledger(path, slr, cs):
    """(trades, legs, error) from the shadow ledger at `path`: every trade
    tools/shadow_legs_report.pair_trades makes of it, each with its "leg", newest ENTRY
    first; `legs` in api/cloud_signal.SHADOW_LEGS order, then any other leg found."""
    try:
        rows = slr.read_rows(path, strict=True)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        return [], [], f"shadow ledger unreadable ({type(e).__name__})"
    if rows:
        missing = [c for c in _SHADOW_LEDGER_COLS if c not in rows[0]]
        if missing:
            return [], [], "shadow ledger header not recognised (no " + ", ".join(missing) + ")"
    by_leg = slr.pair_trades(rows)
    order = list(getattr(cs, "SHADOW_LEGS", None) or {})
    legs = [k for k in order if k in by_leg] + sorted(k for k in by_leg if k not in order)
    trades = [dict(t, leg=leg) for leg in legs for t in by_leg[leg]]
    trades.sort(key=lambda t: (str(t.get("entry_time") or ""), str(t["leg"]),
                               str(t.get("trade_id") or "")), reverse=True)
    return trades, legs, None


def _shadow_ledger_trades(path, slr, cs):
    """_parse_shadow_ledger, cached by the file's (mtime, size): an unchanged ledger is
    never re-read. A file that changed while it was being read is not cached (the next
    build reads it again)."""
    try:
        key = _shadow_stat_key(path)
    except FileNotFoundError:
        return [], [], "shadow ledger not found"
    except OSError as e:
        return [], [], f"shadow ledger unreadable ({type(e).__name__})"
    if _SHADOW_TRADES_CACHE.get("key") == key and _SHADOW_TRADES_CACHE.get("value") is not None:
        return _SHADOW_TRADES_CACHE["value"]
    value = _parse_shadow_ledger(path, slr, cs)
    try:
        if _shadow_stat_key(path) == key:
            _SHADOW_TRADES_CACHE["key"], _SHADOW_TRADES_CACHE["value"] = key, value
    except OSError:
        pass
    return value


def _shadow_base_shares(cfg, default):
    """The shadow trades' base unit: this book's own configured shares for ENGU-Q (the base
    its live leg traded, config.json shares.ENGUQ = 10), else NOISE's, else `default`
    (tools/shadow_legs_report.BASE_SHARES)."""
    shares = (cfg or {}).get("shares")
    if isinstance(shares, dict):
        for leg in ("ENGUQ", "NOISE"):
            v = _finite_or_none(shares.get(leg))
            if v is not None and v > 0:
                return int(round(v))
    return int(default)


def _shadow_bar_mark(cs):
    """The newest closed bar close in api.cloud_signal's own bar cache over the timeframes
    the shadow legs read (the newer bar wins), each file cached by its (mtime, size). None
    when there is none. The live legs' timeframes count too: since 2026-10-09 ENGUQ_335 is a
    CROWN_LEGS leg again (1m) while its old shadow hold stays in the shadow ledger, and that
    open trade is still marked from the newest bar (1m), not the shadow legs' older 5m one."""
    best = None
    tfs = sorted({str(c.get("timeframe"))
                  for legs in ((getattr(cs, "SHADOW_LEGS", None) or {}), (getattr(cs, "CROWN_LEGS", None) or {}))
                  for c in legs.values() if (c or {}).get("timeframe")})
    for tf in tfs:
        try:
            path = cs._cache_path(tf, cs.DEFAULT_PATHS)
            key = _shadow_stat_key(path)
            hit = _SHADOW_MARK_CACHE.get(tf)
            if hit and hit[0] == key:
                bar = hit[1]
            else:
                bar = None
                df = cs.load_cached_bars(tf, cs.DEFAULT_PATHS)
                if df is not None and len(df):
                    df = df.dropna(subset=["time", "close"])
                    if len(df):
                        last = df.sort_values("time").iloc[-1]
                        bar = (float(last["time"]), float(last["close"]))
                _SHADOW_MARK_CACHE[tf] = (key, bar)
        except Exception:
            continue
        if bar and _finite_or_none(bar[1]) is not None and (best is None or bar[0] > best[0]):
            best = bar
    return best[1] if best else None


def _shadow_mark_px(positions_live, cs, log=print):
    """The doc's own latest QQQ price, to mark an OPEN shadow trade: a live price this very
    doc already carries (positions_live), else the live Webull stream's last print when it
    is fresh, else the newest closed bar close (_shadow_bar_mark). None if none of them has
    one. Read only; never raises."""
    try:
        for lg in (positions_live or {}).get("legs") or []:
            px = _finite_or_none((lg or {}).get("live_px"))
            if px is not None:
                return px
    except Exception:
        pass
    try:
        streamer = _qqq_stream_instance()
        if streamer is not None and streamer.is_fresh():
            px = _finite_or_none((streamer.last_trade() or {}).get("price"))
            if px is not None:
                return px
    except Exception as e:
        log(f"[qqq-exec] shadow_trades: live stream read failed ({type(e).__name__}: {e})")
    try:
        return _shadow_bar_mark(cs)
    except Exception:
        return None


def _round2(v):
    return round(v, 2) if v is not None and math.isfinite(v) else None


def _shadow_trade_row(t, base_shares, mark_px, slr):
    """One published shadow trade. Priced at round(base_shares x size) whole shares, by
    tools/shadow_legs_report.trade_dollars' own sign rule. Open (no EXIT row yet): exit_*
    and pnl_usd None, mark_px/unreal_usd off `mark_px`. Closed: mark_px/unreal_usd None."""
    size = _finite_or_none(t.get("size"))
    size = 1.0 if size is None else size
    shares = int(round(base_shares * size))
    is_open = t.get("exit_time") is None
    priced = dict(t, entry_px=_finite_or_none(t.get("entry_px")),
                  exit_px=_finite_or_none(t.get("exit_px")))
    pnl = mark = unreal = None
    if is_open:
        mark = _finite_or_none(mark_px)
        if mark is not None:
            unreal = slr.trade_dollars(dict(priced, exit_px=mark), base_shares=shares, size=1.0)
    else:
        pnl = slr.trade_dollars(priced, base_shares=shares, size=1.0)
    return {"leg": t.get("leg"), "trade_id": t.get("trade_id"), "side": t.get("side") or "long",
            "entry_time": t.get("entry_time"), "entry_px": priced["entry_px"],
            "exit_time": None if is_open else t.get("exit_time"),
            "exit_px": None if is_open else priced["exit_px"],
            "size": float(size), "shares": shares, "seeded": bool(t.get("seeded")),
            "pnl_usd": _round2(pnl), "mark_px": mark, "unreal_usd": _round2(unreal)}


def _cap_shadow_trades(trades, cap):
    """At most `cap` of `trades` (newest ENTRY first), kept in their own order: every OPEN
    trade (no exit_time) -- the newest `cap` of them in the odd case there are more -- plus the
    newest CLOSED trades in the room that is left. A long hold has the oldest entry, so a plain
    trades[:cap] would cut exactly the trade its leg still holds."""
    open_left = cap
    closed_left = max(0, cap - sum(1 for t in trades if t.get("exit_time") is None))
    kept = []
    for t in trades:
        if t.get("exit_time") is None:
            if open_left > 0:
                kept.append(t)
                open_left -= 1
        elif closed_left > 0:
            kept.append(t)
            closed_left -= 1
    return kept


def _build_shadow_trades(cfg, positions_live=None, log=print):
    """The doc's "shadow_trades" block -- see SHADOW TRADES above. Never raises: any
    failure is {"error": "...", "trades": []} with the rest of the block's keys."""
    block = {"as_of": _now_et().isoformat(timespec="seconds"), "source": SHADOW_TRADES_SOURCE,
             "base_shares": SHADOW_BASE_SHARES_FALLBACK, "legs": [], "capped": 0, "trades": []}
    err = None
    try:
        slr = _shadow_report()
        base = _shadow_base_shares(cfg, getattr(slr, "BASE_SHARES", SHADOW_BASE_SHARES_FALLBACK))
        block["base_shares"] = base
        cs = _cs_module()
        path = cs.shadow_paths(cs.DEFAULT_PATHS)["signals_path"]
        trades, legs, err = _shadow_ledger_trades(path, slr, cs)
        block["legs"] = list(legs)
        if not err:
            kept = _cap_shadow_trades(trades, SHADOW_TRADES_CAP)
            block["capped"] = len(trades) - len(kept)
            mark = (_shadow_mark_px(positions_live, cs, log=log)
                    if any(t.get("exit_time") is None for t in kept) else None)
            block["trades"] = [_shadow_trade_row(t, base, mark, slr) for t in kept]
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:160]}"
        block["trades"] = []
    if err:
        block["error"] = err
        if err != _SHADOW_TRADES_CACHE.get("logged") and err != "shadow ledger not found":
            log(f"[qqq-exec] shadow_trades block empty: {err} (display only -- nothing else changes)")
    _SHADOW_TRADES_CACHE["logged"] = err
    return block


def _fit_shadow_trades(doc, block, log=print):
    """Puts the shadow block on the doc as doc["shadow_trades"], AFTER _fit_doc_budget has
    settled trades_all: when the doc plus the block would pass FS_DOC_BUDGET_BYTES/_LEAVES
    it drops the block's OWN oldest CLOSED trades (added to "capped"; an open trade only once
    no closed one is left), never a trades_all row.
    Never raises; a failure here publishes the block's error form instead."""
    try:
        trades = block.get("trades") or []
        size = _fs_size(doc) + 232 + len("shadow_trades") + 1 + _fs_size(block)
        leaves = _fs_leaves(doc) + _fs_leaves(block)
        dropped = 0
        while trades and (size > FS_DOC_BUDGET_BYTES or leaves > FS_DOC_BUDGET_LEAVES):
            # the oldest CLOSED trade (rows are newest entry first); an open one only as a last resort
            i = next((j for j in range(len(trades) - 1, -1, -1)
                      if trades[j].get("exit_time") is not None), len(trades) - 1)
            r = trades.pop(i)
            size -= _fs_size(r)
            leaves -= 1 + _fs_leaves(r)
            dropped += 1
        if dropped:
            block["capped"] = int(block.get("capped") or 0) + dropped
            log(f"[qqq-exec] shadow_trades: dropped the {dropped} oldest shadow trade(s) to keep "
                f"the status doc under its Firestore budget (trades_all untouched)")
        doc["shadow_trades"] = block
    except Exception as e:
        doc["shadow_trades"] = {"as_of": (block or {}).get("as_of"), "source": SHADOW_TRADES_SOURCE,
                                "base_shares": (block or {}).get("base_shares"), "legs": [],
                                "capped": 0, "trades": [],
                                "error": f"{type(e).__name__}: {str(e)[:160]}"}


def _round_or_none(v, nd=2):
    """round(v, nd), or None for a value that is not a finite number."""
    x = _finite_or_none(v)
    return None if x is None else round(x, nd)


def _held_position_fields(lot, day, rail_unrl=None):
    """HOLD OVERNIGHT fields for one published position: held_overnight always; for a held
    lot also since when, the nights carried, the gap (total and today's), the prior close
    and today's open marks, the rail's own open P&L and any close waiting for the open.
    Never raises."""
    h = (lot or {}).get("hold")
    if not isinstance(h, dict):
        return {"held_overnight": False}
    try:
        today_mark = h.get("open_mark_day") == day
        cp = lot.get("close_pending") if isinstance(lot.get("close_pending"), dict) else None
        return {"held_overnight": True, "held_since": h.get("since"),
                "nights_held": int(h.get("nights") or 0),
                "gap_usd": _round_or_none(h.get("gap_usd") or 0.0),
                "gap_today_usd": _round_or_none(h.get("gap_today_usd") or 0.0) if today_mark else 0.0,
                "close_mark_px": h.get("close_mark_px") if today_mark else None,
                "open_mark_px": h.get("open_mark_px") if today_mark else None,
                "unrealized_rail": _round_or_none(rail_unrl),
                "close_pending": ({"reason": cp.get("reason"), "at": cp.get("at")} if cp else None)}
    except Exception:
        return {"held_overnight": True}


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
    _merge_backtest_exits(trades_all, state)   # EOD SETTLE (2026-09-28)

    # ENGINE-VS-BROKER PARITY (feature #56): a SEPARATE read from the NT parity above,
    # for every row that never had a NinjaTrader fill to mirror (signal_source !=
    # "ninjatrader") -- must run AFTER the reprice merge just above, since it falls back
    # to real_entry_px/real_exit_px when there is no captured Webull fill. A row that
    # genuinely mirrors NinjaTrader is left exactly as _trade_parity already computed it
    # -- see _apply_broker_parity/_broker_trade_parity's own docstrings for why.
    broker_by_base = _broker_orders_by_base(_all_broker_orders_from_csv())
    # FILL PARITY (owner decisions 2026-09-28): the backtest's own price per side comes
    # from the engine's signal ledger, joined by trade id -- see _engine_prices_by_trade.
    engine_px = _engine_prices_by_trade(log=log)
    _apply_broker_parity(trades_all, broker_by_base, engine_px=engine_px, log=log)
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
    rail_by_leg = state.get("_rail_unrl_by_leg")
    if not isinstance(rail_by_leg, dict):
        rail_by_leg = unrl_by_leg
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
        # HOLD OVERNIGHT: a held lot is a planned position, never a stuck one
        positions[leg].update(_held_position_fields(lot, day, rail_by_leg.get(leg)))

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
    # SHADOW TRADES (2026-10-09, MANAGER #87 (d)): display only, its own key, never inside
    # trades_all and never counted -- see SHADOW TRADES above _build_doc. Placed on the doc
    # by _fit_shadow_trades below, after trades_all's own budget fit.
    shadow_trades = _build_shadow_trades(cfg, positions_live, log=log)

    doc = {
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
                  # P&L OF RECORD (2026-09-28 (B)): today's closed trades at Webull's
                  # fills (book price per side where none was captured) -- the tab's
                  # TODAY figure reads realized_pnl_record; realized_pnl stays the
                  # book's own. breaker_fill_adj: what the fills took off the daily
                  # loss breaker's input (never positive, see _breaker_fill_shortfall).
                  "realized_pnl_record": round(sum(
                      _curve_pnl(t) for t in trades_all
                      if str(t.get("exit_ts") or "")[:10] == day), 2),
                  "breaker_fill_adj": state.get("_breaker_fill_adj", 0.0),
                  # LEDGER UNIFY 13 (2026-10-05): the daily-stop bar shows the
                  # breaker's OWN number -- the exact figure it last compared with the
                  # limit today (see _note_breaker_input), None until it has checked
                  # today -- and each strategy's TODAY figure is at the P&L of record
                  # (_legs_record_today), never the raw book rows above.
                  "breaker_input": _published_breaker_input(state, day),
                  "legs_record": _legs_record_today(trades_all, day),
                  "unrealized_pnl": round(unrealized, 2),
                  # HOLD OVERNIGHT (2026-10-09): the daily loss rail's own parts --
                  # breaker_input = realized_pnl_rail + breaker_fill_adj + unrealized_rail
                  # (a lot carried into today counts from today's open mark) -- and today's
                  # overnight gap, kept out of the rail, inside the P&L of record
                  "realized_pnl_rail": _round_or_none(_rail_realized_today(state)),
                  "unrealized_rail": round(sum(float(rail_by_leg.get(k) or 0.0)
                                               for k in (state.get("legs") or {})), 2),
                  "overnight_gap_usd": _overnight_gap_today(state, day),
                  # what carried lots that closed today had made by the prior close: in
                  # realized_pnl_record (exit - entry), not today's own move
                  "held_carry_usd": _held_carry_closed_today(state, day)},
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
                  # HOLD OVERNIGHT: the session block carries the EFFECTIVE hold list (the
                  # code default when config.json does not set one), read by the board
                  "session": dict(cfg.get("session") or {},
                                  hold_overnight_legs=list(_hold_legs(cfg))),
                  "slippage_per_share": cfg.get("slippage_per_share"),
                  "kill_file": cfg.get("kill_file"), "size_mode": cfg.get("size_mode"),
                  "size_fraction": cfg.get("size_fraction"),
                  "hold_overnight_legs": list(_hold_legs(cfg))},
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
    # RESTING ORB STOP (2026-09-29): a small status block (mode, what rests -- or would
    # rest in log_only -- and the last decision), never on trades_all rows; absent in "off".
    resting_status = _build_resting_status(cfg, state)
    if resting_status is not None:
        doc["orb_resting"] = resting_status
    # FIRESTORE CAPS (review 2026-09-28): every summary above has read the full rows --
    # now pack what rides on each published trade row, then make sure the doc fits.
    _compact_published_trades(doc["trades_all"])
    _fit_doc_budget(doc, log=log)
    # SHADOW TRADES: added only now, so trades_all's budget fit above is exactly what it was
    # without it -- the block fits itself into what is left (drops its own oldest trades).
    _fit_shadow_trades(doc, shadow_trades, log=log)
    return doc


# -- published doc: compact trade rows + Firestore size / index-entry guard ----------------
# The status doc carries up to 500 trades. Firestore caps a document at 1 MiB AND at
# 40,000 index entries, and project memory says it indexes the leaves of maps inside
# arrays (a candle reply once failed on the index cap, not on bytes). The fill-parity
# fields added 2026-09-28 took a row from ~57 to ~79 counted entries (_fs_leaves, which
# also counts every map and array element, so it over-counts); packing each fp side
# into one string brings it back to ~60 (~1.13 KB a row, ~565 KB at 500 rows). A doc
# still over budget drops its OLDEST trades (the server curve cum_pnl is built before
# this and keeps them) and says how many.
FS_DOC_BUDGET_BYTES = 900_000
FS_DOC_BUDGET_LEAVES = 36_000


def _pack_num(v):
    if v is None:
        return ""
    return ("%.4f" % float(v)).rstrip("0").rstrip(".") or "0"


def _pack_side(s):
    """One fp side as a compact string for the published doc:
    'bt|wb|fs|edge|dsg|slp|unx|why' (fs: o = ok, s = suspect, n = no fill; an empty
    field = None) -- one index entry and ~40 bytes where the dict was 9 leaves and ~120
    bytes. The book's own price (bk) is left out: it is the row's own entry_px /
    exit_px. The web tab's qeFpSide unpacks it. Anything that is not a dict passes
    through unchanged."""
    if not isinstance(s, dict):
        return s
    fs = {"ok": "o", "suspect": "s"}.get(s.get("fs"), "n")
    return "|".join([_pack_num(s.get("bt")), _pack_num(s.get("wb")), fs,
                     _pack_num(s.get("edge")), _pack_num(s.get("dsg")),
                     _pack_num(s.get("slp")), _pack_num(s.get("unx")),
                     str(s.get("why") or "")])


_NT_ONLY_COLS = tuple(NT_PARITY_COLS) + tuple(SIZING_COLS)


def _compact_published_trades(trades_all):
    """IN PLACE on the doc's own trades_all, AFTER every summary has read the full rows:
    packs each fp side (_pack_side) and drops broker_parity_note on a row within the
    band (broker_parity_ok True: the tab shows no chip for it and draws the drawer's
    FILLS vs BACKTEST lines from fp). A flagged or not-compared row keeps its note (the
    chip's hover text). Never raises."""
    for t in trades_all or []:
        try:
            fp = t.get("fp")
            if isinstance(fp, dict):
                fp = dict(fp)
                fp["en"] = _pack_side(fp.get("en"))
                fp["ex"] = _pack_side(fp.get("ex"))
                t["fp"] = fp
            if t.get("broker_parity_ok") is True:
                t.pop("broker_parity_note", None)
            if t.get("pnl_record_note") == "":
                t.pop("pnl_record_note", None)   # the tab only reads it off a non-Webull row
            # an engine row never mirrors NinjaTrader: its empty NT columns are dead
            # weight toward the doc caps (review 2026-09-28) -- the tab reads a missing
            # field and an empty one alike.
            if str(t.get("signal_source") or "").strip().lower() != "ninjatrader":
                for c in _NT_ONLY_COLS:
                    if t.get(c) in ("", None):
                        t.pop(c, None)
            # HOLD OVERNIGHT: blank on every same-day trade -- published only when held
            for c in ("overnight_gap_usd", "nights_held"):
                if t.get(c) in ("", None):
                    t.pop(c, None)
        except Exception:
            continue


def _fs_size(v):
    """Firestore's storage size of one value (api/runner.py's _fs_value_size rules)."""
    if v is None or isinstance(v, bool):
        return 1
    if isinstance(v, (int, float)):
        return 8
    if isinstance(v, str):
        return len(v.encode("utf-8", "replace")) + 1
    if isinstance(v, dict):
        return sum(len(str(k).encode("utf-8", "replace")) + 1 + _fs_size(x) for k, x in v.items())
    if isinstance(v, (list, tuple)):
        return sum(_fs_size(x) for x in v)
    return len(str(v).encode("utf-8", "replace")) + 1


def _fs_leaves(v):
    """Index entries a value can cost, counted conservatively: one per leaf, one per
    array element, one per map."""
    if isinstance(v, dict):
        return 1 + sum(_fs_leaves(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return sum(1 + _fs_leaves(x) for x in v)
    return 1


def _fit_doc_budget(doc, log=print):
    """Keeps the status doc under FS_DOC_BUDGET_BYTES and FS_DOC_BUDGET_LEAVES by dropping
    the OLDEST trades_all rows (the list is newest-first) -- a rejected status write
    would also fail to renew the lease, which blocks broker sends. Publishes
    `trades_all_trimmed` (0 normally) and logs when it trims. Never raises."""
    try:
        doc["trades_all_trimmed"] = 0
        rows = doc.get("trades_all") or []
        size, leaves = _fs_size(doc) + 232, _fs_leaves(doc)
        if size <= FS_DOC_BUDGET_BYTES and leaves <= FS_DOC_BUDGET_LEAVES:
            return
        dropped = 0
        while rows and (size > FS_DOC_BUDGET_BYTES or leaves > FS_DOC_BUDGET_LEAVES):
            r = rows.pop()
            size -= _fs_size(r)
            leaves -= 1 + _fs_leaves(r)
            dropped += 1
        doc["trades_all_trimmed"] = dropped
        log(f"[qqq-exec] status doc over its Firestore budget -- dropped the {dropped} "
            f"oldest trade row(s) from trades_all (now ~{size} bytes, ~{leaves} index entries)")
    except Exception as e:
        log(f"[qqq-exec] doc budget check failed: {type(e).__name__}: {e}")


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
        # ADVERTISED CADENCE (2026-09-25, LEASE PROTOCOL step 3.1): the interval THIS
        # publish was throttled to (see publish_async/publish_now, which stash it here
        # right after calling _should_publish) rides along so _do_set can tell a claimer
        # how often this host promises to renew -- see _lease_stale_bound. None (a caller
        # that never set it, e.g. a test driving write_one directly) reproduces the
        # pre-fix lease shape exactly: _do_set omits the field entirely.
        renew = state.get("_lease_renew_every_sec")
        # The check, the submit and the bookkeeping happen under _lock, the same lock
        # reset_worker takes: a rebuild on the loop thread can then never land between
        # them and have this thread put the OLD worker's write back as the one in flight.
        with self._lock:
            prev = self._inflight
            busy = prev is not None and not prev.done()
            if not busy:
                fut = self._ex.submit(self._do_set, db, uid, doc, renew)
                self._inflight = fut
        if busy:
            _FS_HEALTH.note_fail("previous publish still running")
            _record_publish_result(state, False, err="previous publish still running", log=log)
            return
        # FIRESTORE WEDGE RECOVERY (2026-10-05): every outcome reports to _FS_HEALTH. A
        # publish refused because we no longer hold the lease never reached Firestore, so
        # it is neither a failure nor proof the connection works.
        try:
            fut.result(timeout=PUBLISH_TIMEOUT_SEC)
            _FS_HEALTH.note_ok(log=log)
            _record_publish_result(state, True, log=log)
        except concurrent.futures.TimeoutError:
            err = f"timed out after {PUBLISH_TIMEOUT_SEC:g}s"
            _FS_HEALTH.note_fail(err)
            _record_publish_result(state, False, err=err, log=log)
        except Exception as e:
            if not isinstance(e, _LeaseNotHeld):
                _FS_HEALTH.note_fail(e)
            _record_publish_result(state, False, err=f"{type(e).__name__}: {e}", log=log)

    def reset_worker(self):
        """FIRESTORE WEDGE RECOVERY (2026-10-05): after a rebuild, a write still hung on
        the OLD connection would hold this publisher's one worker -- and fail every new
        write as "previous publish still running" -- until it gave up. Give the next
        write a fresh worker. The old one is abandoned, not shut down (a shutdown could
        race write_one's submit on the publisher thread); its call fails once the old
        channel is closed, or runs out its own PUBLISH_TIMEOUT_SEC. Under _lock, like
        write_one's submit (see there).

        KNOWN, BOUNDED GAP: in the runner's fallback thread (owns_client=False) the old
        channel is dropped, not closed, so the abandoned renewal can still be in flight
        when the new worker sends the next one, and the two may commit out of order. The
        server's leased_at can then sit up to one PUBLISH_TIMEOUT_SEC behind our local
        committed_at (note_committed keeps the max). It never loosens a send: both writes
        are single attempts with their own deadline, it can only happen right after a
        rebuild, and the broker gate still needs a fresh server read
        (_check_lease_for_broker) as well as send_gate."""
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1,
                                                   thread_name_prefix="qqq-publish")
        with self._lock:
            self._ex = ex
            self._inflight = None

    @staticmethod
    def _do_set(db, uid, doc, renew_every_sec=None):
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
        lease = {"host_id": _lease_host_id(), "leased_at": stamp}
        # ADVERTISED CADENCE (2026-09-25, LEASE PROTOCOL step 3.1, see LEASE_STALE_MARGIN):
        # tell a claimer how often we actually promise to renew, so _lease_stale_bound can
        # give a healthy, off-hours-throttled holder more than the fixed LEASE_STALE_SEC
        # grace. `renew_every_sec` is None whenever the caller does not know it (write_one
        # reads state["_lease_renew_every_sec"], which is only set by publish_async/
        # publish_now -- see those); omitting the key entirely (never a guessed number)
        # makes _lease_stale_bound fall back to LEASE_STALE_SEC alone, identical to the
        # pre-fix shape, so every direct _do_set caller (this module's own tests included)
        # is unaffected.
        try:
            cadence = float(renew_every_sec)
        except (TypeError, ValueError):
            cadence = None
        if cadence is not None and math.isfinite(cadence) and cadence > 0:
            lease["renew_every_sec"] = round(cadence, 1)
        doc["lease"] = lease
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


def _publish_interval_for(doc, cfg=None):
    """The BASELINE publish interval _should_publish is using for `doc`/`cfg` right now
    -- armed/session/off-hours selection only, pulled out on its own (2026-09-25, LEASE
    PROTOCOL step 3.1) so a host can ADVERTISE this same number as
    lease["renew_every_sec"] (see _lease_stale_bound) from publish_async/publish_now,
    without _should_publish's own return signature changing under its many existing
    callers and tests (all unpack a fixed 3-tuple).

    Deliberately excludes _should_publish's LIVE POSITIONS CEILING tightening (the
    publish_interval_position_open_sec floor while a position is open in-session): that
    ceiling only ever SHORTENS one publish's own interval, so a claimer told the longer
    baseline number is always given an EQUAL-OR-SAFER (never looser) bound -- an actual
    publish that arrives sooner than promised is never a problem, only one that arrives
    later would be. Advertising the shorter, more volatile ceiling instead would make
    two adjacent off-hours ticks claim different cadences for no safety benefit."""
    broker_mode = (doc.get("broker") or {}).get("effective_mode")
    armed = broker_mode in (webull_orders.MODE_PAPER, webull_orders.MODE_LIVE)
    if armed:
        return _cfg_num(cfg, "publish_interval_armed_sec", PUBLISH_INTERVAL_ARMED_SEC)
    in_session = _in_market_window(_now_et())
    return (_cfg_num(cfg, "publish_interval_session_sec", PUBLISH_INTERVAL_SESSION_SEC) if in_session
            else _cfg_num(cfg, "publish_interval_offhours_sec", PUBLISH_INTERVAL_OFFHOURS_SEC))


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
    in_session = _in_market_window(_now_et())
    interval = _publish_interval_for(doc, cfg=cfg)
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
        # ADVERTISED CADENCE (2026-09-25, LEASE PROTOCOL step 3.1): the SAME baseline
        # interval _should_publish just used, stashed on `state` so write_one/_do_set can
        # attach it to the lease field as lease["renew_every_sec"] -- see _lease_stale_bound
        # and _publish_interval_for's own docstring for why this rides on `state` rather
        # than changing _should_publish's return arity.
        state["_lease_renew_every_sec"] = _publish_interval_for(doc, cfg=cfg)
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
    state["_lease_renew_every_sec"] = _publish_interval_for(doc, cfg=cfg)   # see publish_async
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

    # RESTING ORB STOP (2026-09-29): the gateway's previous-order-terminal rule is on in
    # the "stop" modes only, before this tick can send anything -- see _resting_gateway_step.
    _resting_gateway_step(cfg, log=log)

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
    # Dec 24) -- clamp flat_by/last_entry to the EARLIER of the configured value and a
    # margin BEFORE the recognised early close, in memory only, for this tick's session
    # dict. Never edits config.json.
    #
    # EXIT SAFETY item 5 (2026-09-26): this used to clamp flat_by to the bell itself
    # (sess_close, e.g. "13:00") -- the 5s tick then fires the flatten at
    # 13:00:00-13:00:05 ET, AFTER the early close, and Webull refuses the market sell
    # exactly like the 2026-09-17/18 16:00 incident (see _maybe_flatten_orphan_broker's
    # own docstring). Now flat_by clamps to early-close-minus-3-minutes (12:57 for a
    # 13:00 close) and last_entry to early-close-minus-10-minutes, so the flatten fires
    # comfortably inside the half-day session and the day's last new entry is not still
    # open at the bell.
    sess_close = market_calendar.session_close_et(nowdt)
    if sess_close != "16:00":
        half_day_flat = _hhmm_minus(sess_close, 3)
        half_day_last_entry = _hhmm_minus(sess_close, 10)
        sess_before = cfg.get("session") or {}
        configured_flat = sess_before.get("flat_by", "15:58")
        configured_last_entry = sess_before.get("last_entry", "15:55")
        clamp_flat = half_day_flat < configured_flat
        clamp_entry = half_day_last_entry < configured_last_entry
        if clamp_flat or clamp_entry:
            cfg = dict(cfg)
            cfg["session"] = dict(sess_before)
            if clamp_flat:
                cfg["session"]["flat_by"] = half_day_flat
            if clamp_entry:
                cfg["session"]["last_entry"] = half_day_last_entry
            if state.get("half_day_logged_date") != today:
                log(f"[qqq-exec] {today} is a recognised early close ({sess_close} ET) -- "
                    f"flat_by clamped from {configured_flat} to {half_day_flat}, last_entry "
                    f"from {configured_last_entry} to {half_day_last_entry}")
                _log_event(state, "half_day",
                          f"{today} early close ({sess_close} ET) -- flat_by clamped from "
                          f"{configured_flat} to {half_day_flat}, last_entry from "
                          f"{configured_last_entry} to {half_day_last_entry}", log=log)
                state["half_day_logged_date"] = today

    # HOLD OVERNIGHT: a hold leg's lot carried from an earlier day without its flatten's hold
    # mark (the book was down at that flat_by) is adopted as held first; then today's open
    # mark / rail mark for a lot carried into today, before anything below can close it (a
    # close before today's first bar uses its exit price)
    _adopt_missed_holds(state, cfg, nowdt, log=log)
    _refresh_held_marks(state, nowdt, log=log)

    kill_present = os.path.exists(cfg.get("kill_file") or "")
    if kill_present and not state.get("kill_done"):
        # HOLD OVERNIGHT: hard stops stay hard, but nothing is sent outside regular hours --
        # a held lot then waits for the next open (close_pending)
        deferred = _held_legs_to_defer(state, cfg, nowdt)
        if deferred:
            log(f"[qqq-exec] KILL file present -- closing all shadow lots; held overnight, "
                f"sold at the open: {', '.join(deferred)}")
            closing = [leg for leg in state["legs"] if leg not in deferred]
            if closing:
                _close_all(state, cfg, "KILL", quote_fn, ratio_fn, log=log, nowdt=nowdt,
                           legs=closing)
            for leg in deferred:
                _defer_held_close(state, cfg, leg, "KILL", nowdt, log=log)
        else:
            log("[qqq-exec] KILL file present -- closing all shadow lots")
            _close_all(state, cfg, "KILL", quote_fn, ratio_fn, log=log, nowdt=nowdt)
        state["kill_done"] = True
        # EXIT SAFETY item 4 (2026-09-26): dated, like flat_by_done_date -- lets
        # _maybe_check_webull_flat_after_eod run its Webull-flat check on a kill day too
        # (kill_done itself is a sticky boolean, not a per-day marker: it stays True for
        # as long as the kill file is present, which can span more than one day).
        state["kill_flatten_date"] = today
        # WEBULL PUSH PLAN 10-07, group H: low -- the owner switched it on
        _say(state, "kill", today, _kill_note(deferred), log=log)
        _log_event(state, "kill", "Kill file present -- all shadow lots closed, new entries blocked"
                  + (f" (held overnight, sold at the open: {', '.join(deferred)})"
                     if deferred else ""), log=log)
    elif not kill_present and state.get("kill_done"):
        state["kill_done"] = False
        log("[qqq-exec] kill file cleared")
        _log_event(state, "kill_clear", "Kill file cleared -- adapter resuming normal operation",
                  log=log)

    # HOLD OVERNIGHT: a held lot's KILL / BREAKER / strategy-exit close decided outside
    # regular hours goes out now if the market is open (a KILL whose file is gone is
    # cancelled) -- see _run_deferred_held_closes
    _run_deferred_held_closes(state, cfg, nowdt, quote_fn, ratio_fn, kill_present, log=log)

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
                _route_fills(state, cfg, new_fills, quote_fn, ratio_fn, entries_blocked,
                            log=log, nowdt=nowdt)
                for f in new_fills:
                    processed.add(f["exec_id"])
                # cap the processed-id memory so state.json stays small
                state["processed_ids"] = list(processed)[-5000:]

        if _past_flat_by(nowdt, cfg["session"]) and state.get("flat_by_done_date") != today:
            if state.get("legs"):
                # HOLD OVERNIGHT: a leg in _hold_legs(cfg) keeps its lot (it sells on its own
                # strategy exit); only the rest are priced, crossed and closed -- so a closing
                # leg is never crossed against a held lot. Not on a day the daily loss breaker
                # tripped: a lot still open then is one the stop failed to close (it could not
                # be priced on the trip tick, and the breaker never retries) -- this flatten
                # closes it, as before the hold (hard stops stay hard)
                hold = set() if state.get("breaker_tripped") else set(_hold_legs(cfg))
                legs_open = [leg for leg in state["legs"] if leg not in hold]
                legs_held = [leg for leg in state["legs"] if leg in hold]
                if legs_open:
                    log("[qqq-exec] past flat_by -- closing remaining open lots")
                    _close_all(state, cfg, "EOD", quote_fn, ratio_fn, log=log, nowdt=nowdt,
                               legs=legs_open)
                    _log_event(state, "eod_flatten",
                              f"End-of-day flatten closed: {', '.join(legs_open)}", log=log)
                for leg in legs_held:
                    _mark_held_overnight(state, cfg, leg, nowdt, log=log)
            state["flat_by_done_date"] = today

    unrealized = 0.0
    tripped_before_check = bool(state.get("breaker_tripped"))
    if not kill_present:
        unrealized = _mark_and_check_breaker(state, cfg, quote_fn, ratio_fn, log=log, nowdt=nowdt)
    else:
        # the breaker makes no check on a kill day; keep the daily-stop figure it would
        # count current after the kill flatten (bookkeeping only, see the helper)
        _refresh_breaker_input(state, log=log)

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
    # EXIT SAFETY item 4 (2026-09-26): after the flatten and its CLOSE re-sends above have
    # had their full window, read Webull's own position once and push urgently if it is
    # not flat -- see _maybe_check_webull_flat_after_eod.
    _maybe_check_webull_flat_after_eod(state, cfg, nowdt, log=log)
    # BROKER FILL CAPTURE (feature #57, DEFERRED 2026-09-22): queued by _mirror_to_broker,
    # serviced here -- see _maybe_capture_broker_fills for why this is off the order path.
    _maybe_capture_broker_fills(state, cfg, nowdt, active, log=log)
    # DAILY-STOP BAR (review 2026-10-05): a fill captured just now can only make the
    # breaker's figure worse; take it now rather than one tick late, so the bar never
    # reads better than the hero's today line for that tick. Not on the tick the breaker
    # tripped -- that tick publishes the figure it tripped on. Bookkeeping only.
    if not (state.get("breaker_tripped") and not tripped_before_check):
        _refresh_breaker_input(state, log=log, only_worse=True)
    # RESTING ORB STOP (2026-09-29): after fill capture, so ORB's entry reads FILLED at
    # Webull as soon as it is -- see _maybe_manage_resting.
    _maybe_manage_resting(state, cfg, nowdt, active, log=log)
    # ACCOUNT EQUITY (2026-09-23, item 3): self-gated (at boot, then ~once/min while the
    # market is open) -- see _maybe_read_account_equity's own docstring.
    _maybe_read_account_equity(state, cfg, nowdt, log=log)

    # REPRICE MERGE (feature #48 half) + EOD PHONE SUMMARY (feature #55): both are
    # once-per-ET-day, time-gated jobs that must never block or crash a tick -- see
    # _maybe_run_reprice / _maybe_send_eod_summary for the schedule.
    _maybe_run_reprice(state, nowdt, log=log)
    # EOD SETTLE GAVE UP (finding 30): the engine's own record -> one board event
    if src_mode == "engine":
        _maybe_note_eod_gave_up(state, nowdt, log=log)

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
    another host's lease on publish nor send a broker order. Returns None when refused.

    SERVING_HOSTS GATE (2026-09-26, MAJOR review fix): checked FIRST, before the host
    slot -- `--once` used to be the one path this gate missed entirely. With no --uid,
    db is None, so tick() skips the broker-lease block and _LEASE.send_gate returns
    None -- an excluded PC's manual `python -m api.qqq_exec --once` could still mirror a
    real Webull paper order, exactly the "PC takes over the book" case this gate exists
    to close. Refused here, this never enters the host slot, never ticks, never mirrors
    to the broker."""
    hosts_ok, hosts_reason = _serving_hosts_ok(_read_config_for_gate(log=log), log=log)
    if not hosts_ok:
        log(f"[qqq-exec] REFUSING --once: {hosts_reason} -- never entering the host slot, "
            "never ticking, never sending")
        return None
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
        # RESTING ORB STOP (2026-09-29): the resting orders' boot sweep runs first, so a
        # stop that filled while this process was down is booked before positions are read.
        _resting_boot_sweep(adapter, log=log)
        result = _reconcile_with_timeout(adapter, log=log)
        if result is None:
            return  # OFF mode, or no broker client -- nothing to reconcile against
        if result.get("ok"):
            log("[qqq-exec] broker reconcile OK at boot")
        elif result.get("undecided"):
            log(f"[qqq-exec] broker reconcile UNDECIDED at boot: {result.get('reason')} -- a "
                f"resting order is looked up first")
        elif result.get("error"):
            log(f"[qqq-exec] BROKER RECONCILE READ FAILURE at boot -- the broker order "
                f"adapter halts new entries until a later reconcile succeeds: "
                f"{result.get('error')}")
        else:
            log(f"[qqq-exec] BROKER RECONCILE MISMATCH at boot -- the broker order "
                f"adapter halts new entries until a later reconcile succeeds: "
                f"{result.get('mismatches')}")
        _check_book_holds_broker_lots_at_boot(adapter, log=log)
    except Exception as e:
        log(f"[qqq-exec] broker reconcile at boot failed (non-fatal): {type(e).__name__}: {e}")


def _check_book_holds_broker_lots_at_boot(adapter, log=print):
    """HOLD OVERNIGHT: the adapter's reconcile above compares only its own per-leg broker
    positions with Webull -- never the book's own lots (state.json). Before the hold the book
    was flat overnight, so a state.json that was missing or unreadable at a restart (load_state
    then starts empty) lost nothing; now a held lot would vanish from the book while the
    adapter and Webull still hold it, its exit would land as exit_no_lot and nothing would
    ever sell it. So: a leg that holds overnight on which the adapter still believes a
    position the book has no lot for (and no CLOSE waiting in the book's re-send queue) is
    logged and pushed urgently, in plain words. Read-only (state.json is not written here).
    Never raises."""
    try:
        hold = set(_hold_legs(_read_config_for_gate(log=log)))
        if not hold:
            return
        sent = (adapter.status() or {}).get("broker_sent_positions") or {}
        state = load_state(log=log)
        legs = state.get("legs") or {}
        closing = {str((v or {}).get("leg") or "") for v in (state.get("_broker_resend") or {}).values()
                   if (v or {}).get("intent") == "CLOSE"}
        lost = {}
        for leg, p in sent.items():
            try:
                q = int(round(float((p or {}).get("qty") or 0)))
            except (TypeError, ValueError):
                continue
            if q and leg in hold and leg not in legs and leg not in closing:
                lost[leg] = q
        if not lost:
            return
        words = _held_words(lost)
        log(f"[qqq-exec] BOOK LOST A HELD LOT at boot: the broker adapter still holds {words} "
            f"that state.json has no lot for -- its exit can never sell it; check Webull")
        _say(None, "boot:held_lost", _phone_day(), ntfy_push.plain(
            PHONE_AREA, "CHECK NOW", f"{_legs_words(sorted(lost))} may stay open",
            f"After a restart the book lost {_legs_words(sorted(lost))}'s held shares, "
            f"which Webull still holds",
            "check the Webull app, then " + PHONE_ASK, priority="urgent"), log=log)
    except Exception as e:
        log(f"[qqq-exec] held-lot check at boot failed (non-fatal): {type(e).__name__}: {e}")


TICK_FAILURE_ALERT_THRESHOLD = 3  # item 3 (2026-09-26): consecutive failed ticks -> push

# TICK CRASH MARKER (10-08 review, WEBULL PUSH PLAN "Tick loop crashing vs stuck"): the box
# monitor (tools/webull_freshness.py tick_gap) stays quiet while THIS process's own crash
# episode is open -- but a failed tick never reaches save_state (a half-mutated state must not
# be saved), so state.json cannot carry that fact. The episode lives in this small file beside
# state.json instead: written atomically (tmp + os.replace) the moment the crash note goes
# out, REFRESHED (at_epoch) on every failed tick after it, removed on the first good tick after
# it (and once by each new process's first good tick). The monitor trusts it only while it is
# fresh (tools/webull_freshness.py TICK_CRASH_MARKER_FRESH_SEC): a process that has since hung
# or died stops refreshing it, so its stall is paged in the normal window even when no later
# process ever reaches a good tick to remove it. It also carries the ET day the note went out:
# a NEW process that starts into the same crash loop (no good tick in between -- the repeat
# memory in state.json is never saved by a failed tick) does not push the same note again
# that day (10-08 fourth review).
TICK_CRASH_MARKER = os.path.join(OUT_DIR, "tick_crash.json")
_TICK_CRASH_MARKER_SWEPT = {"done": False}


def _read_tick_crash_marker():
    """The open crash episode's marker (a dict), or None when there is none / unreadable."""
    try:
        with open(TICK_CRASH_MARKER, "r", encoding="utf-8") as fh:
            body = json.load(fh)
        return body if isinstance(body, dict) else None
    except Exception:
        return None


def _write_tick_crash_marker(streak, exc=None, log=print, prior=None):
    """The crash episode is open: {at_epoch (this failed tick), at_utc, streak, error, pid,
    day + pushed_epoch (when the crash note went out -- kept from `prior` on a refresh)}.
    Never raises."""
    try:
        path = TICK_CRASH_MARKER
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        now = time.time()
        prior = prior if isinstance(prior, dict) else {}
        body = {"at_epoch": now,
                "at_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
                "streak": int(streak), "pid": os.getpid(),
                "error": type(exc).__name__ if exc is not None else None,
                "day": prior.get("day") or _phone_day(),
                "pushed_epoch": prior.get("pushed_epoch") or now}
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(body, fh)
        _replace_with_retry(tmp, path, log=log, what="tick_crash.json")
    except Exception as e:
        log(f"[qqq-exec] tick crash marker write failed (non-fatal): {type(e).__name__}: {e}")


def _clear_tick_crash_marker(log=print):
    """The crash episode is over (or belonged to an earlier process). Never raises."""
    try:
        if os.path.exists(TICK_CRASH_MARKER):
            os.remove(TICK_CRASH_MARKER)
    except OSError as e:
        log(f"[qqq-exec] tick crash marker remove failed (non-fatal): {type(e).__name__}: {e}")


def _drop_crash_from_tick_gap(state):
    """A crash episode whose note went out is not a STALL: forget the last tick's wall time,
    so the first good tick after it starts a fresh baseline (_track_tick_gap returns None)
    instead of recording the whole crash as tick_gap_max_s_today -- which the box monitor's
    tick_gap 'rose' check would push after the marker is gone, a second push for one crash
    (10-08 fourth review). Needed because a tick that crashes before _track_tick_gap (or in
    load_config / the stream step) never advances it. In memory only, like the streak."""
    try:
        state["_last_tick_wall"] = None
    except Exception:
        pass


def _note_tick_result(state, ok, exc=None, log=print):
    """Tracks CONSECUTIVE tick() failures across iterations of qqq_exec_thread's own
    while loop (item 3, 2026-09-26, "alerts in book") and pushes ONE high-priority
    alert per episode, the moment the streak first reaches TICK_FAILURE_ALERT_THRESHOLD
    -- never again for the rest of that same episode (an outage can run for a while;
    paging every 5s would be useless noise), and never for one or two isolated
    failures, which this adapter has always shrugged off and retried.

    `state` carries the streak (state["_tick_fail_streak"] / state["_tick_fail_alerted"])
    the same way every other piece of this loop's own bookkeeping does -- and it is
    exactly the right place for it: a failed tick's `except` branch never reaches
    save_state (see qqq_exec_thread's own try body), so this in-memory counter lives
    only for the life of the process, which is what makes it a per-EPISODE signal
    rather than a per-day one. A single call covers both directions: ok=True resets
    the streak (and logs a plain recovery line once one was ever counted, no push --
    the episode already got its one alert going in). The open episode is ALSO written to
    TICK_CRASH_MARKER beside state.json (see there) -- the one place the box monitor can see
    it, since this branch never saves state.json. Never raises."""
    try:
        if ok:
            streak = int(state.get("_tick_fail_streak") or 0)
            if streak:
                log(f"[qqq-exec] tick loop recovered after {streak} consecutive failure(s)")
            was_alerted = bool(state.get("_tick_fail_alerted"))
            state["_tick_fail_streak"] = 0
            state["_tick_fail_alerted"] = False
            _say_clear(state, "tick_crash")     # a fresh episode may push again
            if was_alerted or not _TICK_CRASH_MARKER_SWEPT["done"]:
                _TICK_CRASH_MARKER_SWEPT["done"] = True
                _clear_tick_crash_marker(log=log)
            return
        streak = int(state.get("_tick_fail_streak") or 0) + 1
        state["_tick_fail_streak"] = streak
        if state.get("_tick_fail_alerted"):
            # the episode's note already went out: keep its marker fresh for the monitor, and
            # keep the crash out of today's tick gap (see _drop_crash_from_tick_gap)
            _drop_crash_from_tick_gap(state)
            _write_tick_crash_marker(streak, exc=exc, log=log, prior=_read_tick_crash_marker())
            return
        if streak >= TICK_FAILURE_ALERT_THRESHOLD:
            state["_tick_fail_alerted"] = True
            msg = (f"QQQ EXEC: {streak} consecutive tick failures -- latest: "
                  f"{type(exc).__name__ if exc is not None else 'unknown'}: {exc}")
            _log_event(state, "tick_failures", msg, log=log)
            prior = _read_tick_crash_marker()
            if prior is not None and prior.get("day") == _phone_day():
                # an earlier process pushed this same crash loop today and no good tick has
                # run since (its marker is still here): once a day, not once per restart
                log("[qqq-exec] crash note already pushed today by an earlier process "
                    "(tick_crash.json) -- not pushed again")
                sent = True
            else:
                prior = None
                # WEBULL PUSH PLAN 10-07, group I: high, once an episode (and at most once a day)
                _action, sent = _say(state, "tick_crash", _phone_day(), ntfy_push.plain(
                    PHONE_AREA, "CHECK NOW", "the QQQ order program keeps crashing",
                    f"Its last {streak} checks crashed in a row", PHONE_ASK,
                    priority="high"), log=log)
            if sent is False:
                # the note did not go out (not even queued): try again on the next failed
                # tick, and leave the box monitor's stall push free meanwhile
                state["_tick_fail_alerted"] = False
            else:
                _drop_crash_from_tick_gap(state)
                _write_tick_crash_marker(streak, exc=exc, log=log, prior=prior)
    except Exception as e:
        log(f"[qqq-exec] tick-failure alert bookkeeping failed (non-fatal): {type(e).__name__}: {e}")


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
    runs unmanaged, exactly as before.

    SERVING_HOSTS GATE (2026-09-26): checked FIRST, before the host slot or the lease --
    see _serving_hosts_ok. A host config.json excludes never claims the lease, never
    takes the host slot, never ticks and never sends, regardless of db/managed. Reads
    config.json through _read_config_for_gate, NOT load_config (major review fix,
    2026-09-26): load_config writes a default file when one is missing, a side effect
    this gate must never trigger just to decide whether this host may even touch the
    book."""
    hosts_ok, hosts_reason = _serving_hosts_ok(_read_config_for_gate(log=log), log=log)
    if not hosts_ok:
        log(f"[qqq-exec] REFUSING to run the shadow book: {hosts_reason} -- never "
            "claiming the lease, never ticking, never sending")
        return
    lease_uid = uids[0] if uids else None
    # FIRESTORE WEDGE RECOVERY (2026-10-05): one handle for every Firestore holder below
    # (tick's lease reads, the claim, the publisher), so a rebuild reaches all of them
    db = _as_firestore_handle(db)
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
        # NTFY OUTBOX (finding 16): a high/urgent push the last process could not deliver
        # is retried now, off the tick (background thread) -- see _notify.
        _ntfy_outbox_resume(log=log)
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
                # FIRESTORE WEDGE RECOVERY (2026-10-05): a client stuck on a dead channel
                # is rebuilt here, in-process, instead of blocking every order until a
                # restart -- see _maybe_rebuild_firestore. Never raises.
                _maybe_rebuild_firestore(db, state, log=log)
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
                # MINOR REVIEW FIX (2026-09-26, item 3): _note_tick_result before
                # save_state -- it used to run after, so the FIRST successful tick after
                # an alerted episode persisted the stale _tick_fail_streak/
                # _tick_fail_alerted to state.json a moment before this call would have
                # reset them. A restart landing in that instant loaded
                # _tick_fail_alerted=True and suppressed the page for a genuinely NEW
                # episode.
                _note_tick_result(state, True, log=log)
                save_state(state, log=log)
                _touch_serving_lock(log=log)
                if on_tick is not None:
                    on_tick(log=log)
            except Exception as e:
                log(f"[qqq-exec] tick failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
                _note_tick_result(state, False, exc=e, log=log)
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

# LEASE PROTOCOL step 3.1 -- ADVERTISED CADENCE (2026-09-25, WEBULL_PAPER_TODO.md item 3,
# "keep the QQQ lease fresh when status publishes are throttled"). THE GAP: FIX 1
# (_should_publish, 2026-09-14) backs the publish interval off to
# publish_interval_offhours_sec (default 600s) whenever the broker is OFF, to save the
# daily Firestore write quota -- but every publish is also this host's lease renewal, so
# a perfectly healthy off-hours holder's stamp is OLDER than the fixed LEASE_STALE_SEC
# (90s) for most of each cycle (observed live 2026-09-14: stamp age 89.8s at 16:48:31 ET,
# last publish 16:47:02). Judging staleness against LEASE_STALE_SEC alone -- as every
# reader used to -- means a second host (the planned Oracle Cloud VM) can claim the lease
# out from under a healthy PC while it is merely being quiet on purpose, and worse, a
# relaunched copy on the ORIGINAL host (a runner restart, tools/premarket_ensure.py at
# 06:05) can then claim it BACK overnight, defeating deploy/cloud/README.md's "a
# relaunched copy is refused for as long as the VM holds the lease" promise.
#
# THE FIX (design (a) of the two the spec offered, "advertised cadence" -- picked over
# "(b) lease-only renewal" because it costs ZERO extra Firestore writes: (b)'s small
# merge write, sent whenever the throttled publish would otherwise leave the stamp older
# than ~45s, would need to fire roughly every 45s around the clock -- ~13x MORE writes
# than today's 600s off-hours cadence, undoing most of the very quota savings FIX 1 was
# for. This is the CONSERVATIVE choice the spec asked for when a design decision is
# left open). A publishing host advertises its own cadence on every lease write
# (lease["renew_every_sec"], set in _Publisher._do_set from the SAME interval
# _should_publish/_publish_interval_for just computed for THIS publish -- see
# publish_async/publish_now). A claimer then judges staleness against whichever is
# LARGER: the fixed LEASE_STALE_SEC (still the FLOOR -- an armed host renewing every 20s
# must not suddenly get a multi-minute grace from a stale or bogus cadence value) or
# LEASE_STALE_MARGIN (1.5x, one missed renewal's worth, the same sizing logic
# LEASE_STALE_SEC itself already used against the fastest/armed cadence) times that
# advertised cadence. See _lease_stale_bound.
#
# EVERY READER CHECKED, per the spec:
#   - _lease_claimable (and so _check_lease, _claim_lease, _cas_publish, which all call
#     it) and _check_lease_for_broker's OTHER-HOST branch: UPDATED to _lease_stale_bound
#     -- both are exactly "is a foreign claim's stamp too old to trust", the question
#     this fix answers.
#   - _check_lease_for_broker's OWN-stale branch (own_age > LEASE_HOLD_SEC) is
#     UNCHANGED: it only runs once armed (see that function's own comment; OFF never
#     reaches it), and while armed _should_publish always uses the fast, constant
#     publish_interval_armed_sec (20s, comfortably under LEASE_HOLD_SEC's 60s) --
#     never the throttled session/off-hours interval this fix targets, so there is no
#     gap there to close.
#   - _LeaseHolder.write_mode / within_hold / send_gate are UNCHANGED: all three judge
#     THIS process's own last commit, not a foreign advertised cadence. write_mode
#     already falls to "cas" (never wrong, just an extra transaction) once our own gap
#     exceeds LEASE_HOLD_SEC/LEASE_RECHECK_SEC -- which off-hours it always will, cheaply,
#     at that slow cadence. within_hold's conservative "not provably still safe" default
#     on a CAS error is the right answer regardless of cadence. send_gate's 30s bound
#     only matters once armed, same as the own-stale branch above.
#   - The suspended-loop re-claim (qqq_exec_thread, `gap > LEASE_STALE_SEC and
#     _LEASE.held`) is UNCHANGED: `gap` there is wall-clock time since THIS process's
#     OWN previous pass through its TICK_SEC (5s)-paced while-loop -- a signal that the
#     process itself stalled (machine sleep, thread starvation), completely independent
#     of the publish throttle this fix is about. A healthy loop updates it every ~5s
#     regardless of whether that tick happened to publish.
LEASE_STALE_MARGIN = 1.5


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
    (see qqq_exec_thread).

    SERVING_HOSTS GATE (2026-09-26): checked FIRST, before any of the above -- see
    _serving_hosts_ok. A host config.json excludes is not just refused the standalone
    slot, it is never OFFERED one: this returns True (nothing else to do here) WITHOUT
    ever launching the VBS, so an excluded PC does not spawn a fresh detached
    wscript/python pair on every fleet restart (this function is called once per boot,
    but the runner fleet restarts many times a day -- see _run_qqq_exec.vbs's own
    docstring on the 2026-09-09 incident that made this a standalone launcher in the
    first place). Returning True also skips the in-runner fallback thread below, which
    would otherwise start and immediately self-refuse via the same gate in
    qqq_exec_thread every single boot -- harmless, but pure churn."""
    hosts_ok, hosts_reason = _serving_hosts_ok(_read_config_for_gate(log=log), log=log)
    if not hosts_ok:
        log(f"[qqq-exec] {hosts_reason} -- never launching the standalone adapter on this "
            "host, no fallback thread either")
        return True
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


def _serving_hosts_ok(cfg, log=print):
    """(ok, reason) -- SERVING_HOSTS GATE (2026-09-26, "the owner's PC can never take
    over the book"): a STATIC allow-list, config.json's optional "serving_hosts" list of
    _lease_host_id() names, checked BEFORE the LEASE PROTOCOL above ever runs.

    Why this is a separate gate and not just the lease: the lease only ever lets ONE
    host serve at a time, but does not care WHICH one -- it fails OPEN on every read
    problem (_check_lease, _claim_lease) precisely so the very first host to boot can
    always start. That is exactly wrong for "the PC must never serve again": a stale
    Firestore read, a blip, or simply booting first would let it win the race like any
    other host. serving_hosts is judged with no such fail-open -- it never touches
    Firestore at all, so it works identically whether the lease is healthy, stale, or
    unreachable.

    Absent, or present but not a (non-empty) list -- today's behaviour, every host may
    still compete for the lease exactly as before this gate existed. Present as a list
    -- this host may proceed only if _lease_host_id() is one of the names in it; every
    other host is refused here, before it ever calls _claim_lease or _enter_host_slot,
    so it can truthfully log that it never claimed the lease, ticked or sent."""
    if not isinstance(cfg, dict):
        return True, None
    hosts = cfg.get("serving_hosts")
    if hosts is None:
        return True, None
    if not isinstance(hosts, list) or not hosts:
        log(f"[qqq-exec] config.json serving_hosts={hosts!r} is not a non-empty list -- "
            "ignoring (every host may still serve, today's behaviour)")
        return True, None
    allowed = {str(h).strip() for h in hosts if str(h).strip()}
    me = _lease_host_id()
    if me in allowed:
        return True, None
    return False, (f"this host {me!r} is not in config.json's serving_hosts {sorted(allowed)} "
                   "-- refusing to serve")


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
        # FIRESTORE WEDGE RECOVERY (2026-10-05): under a hard wall-clock limit -- a
        # timeout is a failed read like any other (still fail-open here)
        d = _read_lease_doc(db, uid)
    except Exception as e:
        _FS_HEALTH.note_fail(e)
        log(f"[qqq-exec] lease check could not read Firestore ({type(e).__name__}: {e}) -- "
            "proceeding (fail-open)")
        return True, "lease read failed -- fail-open"
    _FS_HEALTH.note_ok(log=log)
    return _lease_claimable(d, _lease_host_id(), time.time())


def _lease_of(doc):
    lease = (doc or {}).get("lease") if isinstance(doc, dict) else None
    return lease if isinstance(lease, dict) else {}


def _lease_stale_bound(lease):
    """How old another host's lease stamp may get before it is claimable -- LEASE
    PROTOCOL step 3.1, "advertised cadence" (2026-09-25, see LEASE_STALE_MARGIN's own
    comment for the full why). `lease` is the "lease" sub-dict already read off the doc
    (e.g. via _lease_of).

    The holder's own last publish stamped lease["renew_every_sec"] with the interval it
    is currently throttled to (see _Publisher._do_set / _publish_interval_for); this
    returns whichever is LARGER of the fixed LEASE_STALE_SEC floor or LEASE_STALE_MARGIN
    (1.5x) times that cadence, so a healthy host publishing slowly on purpose (off-hours,
    broker OFF, to save the daily write quota) is never mistaken for dead.

    Missing, unreadable or non-positive -- an older host that predates this field, a
    stray/malformed value, or this process's own never-yet-published claim doc -- falls
    back to LEASE_STALE_SEC alone: exactly the behaviour before this fix, never LESS
    safe than it was."""
    try:
        cadence = float(lease.get("renew_every_sec"))
    except (TypeError, ValueError, AttributeError):
        return LEASE_STALE_SEC
    if not math.isfinite(cadence) or cadence <= 0:
        return LEASE_STALE_SEC
    return max(LEASE_STALE_SEC, LEASE_STALE_MARGIN * cadence)


def _lease_claimable(doc, my_host, now):
    """(ok, reason) -- _check_lease's rule on an already-read doc, shared with _claim_lease
    and _cas_publish so the plain read and the compare-and-set can never disagree: only a
    DIFFERENT host's positively fresh stamp refuses; free, ours, stale, or a timestamp that
    is missing/unreadable (fail-open, see _check_lease) is claimable.

    "Fresh" is judged against _lease_stale_bound, not a bare LEASE_STALE_SEC (2026-09-25,
    LEASE PROTOCOL step 3.1) -- see that helper and LEASE_STALE_MARGIN's comment."""
    lease = _lease_of(doc)
    other_host = lease.get("host_id")
    leased_at = lease.get("leased_at")
    if not other_host or other_host == my_host or leased_at is None:
        return True, "lease free or already ours"
    try:
        age = now - float(leased_at)
    except (TypeError, ValueError):
        return True, "lease timestamp unreadable -- treating as free"
    if age > _lease_stale_bound(lease):
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
    rule let BOTH pass, the last writer reading "ours" and the other host reading "stale".

    OUR OWN branch's LEASE_HOLD_SEC bound is deliberately NOT widened by LEASE PROTOCOL
    step 3.1's advertised cadence (2026-09-25): this function is only ever consulted once
    the broker mirror is ARMED (see _mirror_to_broker), and while armed _should_publish
    always uses the fast, constant publish_interval_armed_sec (20s, well under this 60s
    bound) -- never the throttled session/off-hours interval step 3.1 targets. The OTHER
    HOST branch below judges a foreign claim exactly like _lease_claimable does, so it
    DOES need that widening: the other host may be a different, off-hours-throttled
    machine (see _lease_stale_bound)."""
    if db is None or not uid:
        return False, "lease unverifiable: no Firestore/uid configured"
    try:
        # FIRESTORE WEDGE RECOVERY (2026-10-05): this read once held the loop for the
        # client's 300s default retry on a dead channel -- now a hard wall-clock limit,
        # and a timeout fails CLOSED exactly like any other read failure
        d = _read_lease_doc(db, uid)
    except Exception as e:
        _FS_HEALTH.note_fail(e)
        log(f"[qqq-exec] broker lease check could not read Firestore ({type(e).__name__}: "
            f"{e}) -- suppressing broker sends this tick (fail-CLOSED for real orders)")
        return False, f"lease unverifiable: Firestore read failed ({type(e).__name__}: {e})"
    _FS_HEALTH.note_ok(log=log)
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
    if age > _lease_stale_bound(lease):
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


# -- FIRESTORE WEDGE RECOVERY (2026-10-05) ----------------------------------------------
# THE INCIDENT. From the 2026-10-02 close until a manual restart on Monday 10-05 09:13 ET
# the box's executor logged the same four lines every ~5 minutes: the broker lease read
# hung for its client's whole 300s default retry ("RetryError: Timeout of 300.0s exceeded,
# last exception: 503 failed to connect to all addresses ... FD Shutdown"), every publish
# timed out after 8s, and the loop then saw a ~280s gap and re-claimed the lease -- which
# timed out after 15s too. Plain HTTPS to firestore.googleapis.com worked from the box the
# whole time (DNS had moved it to IPv6) and the restart fixed it at once: the process's
# ONE long-lived gRPC client was stuck on a dead channel. While the lease cannot be read
# every Webull order is blocked (fail closed, correctly), so one stuck client blocked the
# book -- and no tick finished on time -- for 2.5 days with nobody told.
#
# THE FIX, three parts:
#   1. A HARD WALL-CLOCK LIMIT on the lease read (_read_lease_doc, LEASE_READ_TIMEOUT_SEC),
#      the same throwaway-worker pattern as _reconcile_with_timeout, and only one read in
#      flight at a time: a stuck read can no longer hold the 5s loop for ~5 minutes. Its
#      own retry is bounded to the same limit (_lease_read_retry), so a one-off 503 is
#      still retried instead of blocking new entries for a whole verify interval.
#   2. A HEALTH COUNT (_FS_HEALTH): every Firestore call this adapter makes -- the lease
#      reads, the claim, every publish -- reports in. Connection-class failures (503,
#      UNAVAILABLE, "failed to connect", deadline, our own hard timeouts) count; any call
#      that works resets it (the count -- see the episode rule below); anything else (quota, permission, a lease we no longer hold)
#      is neither -- a rebuild would not help those, and they must not hide a wedge.
#   3. AN IN-PROCESS REBUILD (_FirestoreHandle, _maybe_rebuild_firestore): once the count
#      reaches FS_REBUILD_AFTER_FAILS in a row, or failures have run FS_REBUILD_AFTER_SEC,
#      the loop builds a new client and closes the old one -- only when this adapter owns
#      it: the runner's fallback thread hands in the runner's SHARED client, which is
#      dropped here, never closed (_FirestoreHandle, owns_client). Every holder sees the new one
#      at once -- the tick's lease reads, the claim and the publisher all go through the
#      same handle -- and the publisher's worker and the lease-read slot (which may still
#      be stuck on the old channel) are replaced too. Rebuilds back off (FS_REBUILD_
#      BACKOFF_SEC doubling to FS_REBUILD_BACKOFF_MAX_SEC). Still failing after a rebuild:
#      one log line and ONE high push per episode (a push that fails to send is tried
#      again every FS_ALERT_RETRY_SEC until one goes out). A process that cannot rebuild (no way
#      to make a new client, e.g. the runner given a test double) pushes the same once.
#      AN EPISODE ENDS only after SUSTAINED health -- FS_HEALTHY_AFTER_OKS working calls in
#      a row AND FS_HEALTHY_AFTER_SEC with no connection failure -- so a flapping
#      connection (many 503s, the odd success) keeps its backoff and its one push.
# LEASE SEMANTICS ARE UNCHANGED: a read that times out is a read that failed, so broker
# sends stay blocked (fail closed) exactly as before; the shadow book's own checks stay
# fail-open; a rebuild never marks the lease held -- sends open again only once a stamp of
# ours lands through the new client and a fresh read confirms it (send_gate +
# _check_lease_for_broker, both untouched).
LEASE_READ_TIMEOUT_SEC = 10.0
FS_REBUILD_AFTER_FAILS = 8
FS_REBUILD_AFTER_SEC = 5 * 60.0
FS_REBUILD_BACKOFF_SEC = 2 * 60.0
FS_REBUILD_BACKOFF_MAX_SEC = 30 * 60.0
FS_HEALTHY_AFTER_OKS = 5
FS_HEALTHY_AFTER_SEC = 2 * 60.0
FS_ALERT_RETRY_SEC = 2 * 60.0

_FS_CONN_MARKERS = ("503", "unavailable", "failed to connect", "deadline", "timed out",
                    "timeout", "retryerror", "connection", "fd shutdown", "socket closed",
                    "still running", "unreachable")


class _FsCallTimeout(TimeoutError):
    """A Firestore call this adapter gave up waiting on (its own hard wall-clock limit)."""


def _fs_conn_error(err):
    """True when `err` (an exception, or the text a caller already made of one) reads as
    "could not reach Firestore" -- the failures a rebuilt connection can fix. A quota,
    permission or bad-request error means the server answered: False."""
    if isinstance(err, (TimeoutError, concurrent.futures.TimeoutError, ConnectionError)):
        return True
    if isinstance(err, BaseException):
        text = f"{type(err).__name__}: {err}"
    else:
        text = str(err or "")
    text = text.lower()
    return any(m in text for m in _FS_CONN_MARKERS)


class _FsHealth:
    """Consecutive connection-class Firestore failures for this process -- see FIRESTORE
    WEDGE RECOVERY above. Thread-safe: the loop, the publisher thread and the lease-read
    workers all report here. In memory only: a fresh process starts healthy."""

    def __init__(self):
        self._lock = threading.Lock()
        self.streak = 0
        self.first_fail_at = None
        self.last_err = None
        self.rebuilds = 0           # rebuilds during the current episode
        self.alerted = False        # the episode's one push already went out
        self.alert_tries = 0        # pushes tried this episode (the first logs + files an event)
        self.next_alert_at = 0.0    # a push that failed to send is tried again after this
        self.next_rebuild_at = 0.0
        self.backoff = None         # None = FS_REBUILD_BACKOFF_SEC (read when used)
        self.oks = 0                # working calls in a row
        self.last_fail_at = None    # the latest connection-class failure
        self.phone_clear = False    # an episode ended: clear the "database" phone slot

    def note_ok(self, log=print, now=None):
        """A call that worked. Resets the in-a-row failure count at once; ENDS the episode
        (rebuild count, backoff, the one-push flag) only after sustained health -- see
        FS_HEALTHY_AFTER_OKS / FS_HEALTHY_AFTER_SEC -- so one lucky call in a flapping run
        does not start the next run of failures from scratch."""
        now = time.time() if now is None else now
        with self._lock:
            self.streak, self.first_fail_at, self.last_err = 0, None, None
            self.oks += 1
            in_episode = bool(self.rebuilds or self.alerted or self.alert_tries
                              or self.backoff is not None)
            if not in_episode:
                return
            if self.oks < FS_HEALTHY_AFTER_OKS or (
                    self.last_fail_at is not None
                    and now - self.last_fail_at < FS_HEALTHY_AFTER_SEC):
                return
            rebuilds, alerted = self.rebuilds, self.alerted
            self.rebuilds, self.alerted = 0, False
            self.alert_tries, self.next_alert_at = 0, 0.0
            self.next_rebuild_at, self.backoff = 0.0, None
            # the outage is over: its phone note ("database") ends too, so a NEW outage --
            # even the same day -- pushes again (WEBULL PUSH PLAN 10-07 repeat rule). The
            # process store is cleared here; state.json's slot by _maybe_rebuild_firestore,
            # which holds the state, on its next pass.
            self.phone_clear = True
        _say_clear(None, "database", log=log)
        try:
            log("[qqq-exec] Firestore reachable again"
                + (f" after rebuilding the connection {rebuilds} time(s)" if rebuilds else "")
                + (" (the outage push went out)" if alerted else ""))
        except Exception:
            pass

    def note_fail(self, err, now=None):
        """Count `err` if it is connection-class; anything else changes nothing."""
        if not _fs_conn_error(err):
            return
        now = time.time() if now is None else now
        text = f"{type(err).__name__}: {err}" if isinstance(err, BaseException) else str(err)
        with self._lock:
            self.streak += 1
            self.oks = 0
            self.last_fail_at = now
            if self.first_fail_at is None:
                self.first_fail_at = now
            self.last_err = text[:300]

    def tripped(self, now):
        """Caller holds _lock."""
        if self.streak >= FS_REBUILD_AFTER_FAILS:
            return True
        return (self.first_fail_at is not None and self.streak >= 2
                and now - self.first_fail_at >= FS_REBUILD_AFTER_SEC)


_FS_HEALTH = _FsHealth()


def _close_firestore_client(client, log=print):
    """Best-effort close of a Firestore client we are replacing, on a daemon thread that
    nobody waits for -- closing a channel that is itself stuck must not stall the loop.
    The gRPC channel (the part that wedged) is closed through the client's transport; any
    call still running on it then fails instead of hanging on."""
    def _close():
        try:
            transport = getattr(client, "_transport", None)
            if transport is None:
                api = getattr(client, "_firestore_api_internal", None)
                transport = getattr(api, "transport", None) if api is not None else None
            if transport is not None and callable(getattr(transport, "close", None)):
                transport.close()
        except Exception as e:
            log(f"[qqq-exec] closing the old Firestore connection failed (ignored): "
                f"{type(e).__name__}: {e}")
        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        except Exception:
            pass
    threading.Thread(target=_close, name="qqq-fs-close", daemon=True).start()


def _new_firestore_client():
    """A brand-new Firestore client for the firebase_admin app this process already
    initialised. Built directly rather than through firebase_admin.firestore.client(),
    which hands back the SAME cached (stuck) client every time. No network here -- the
    client connects lazily on its first call."""
    import firebase_admin
    from google.cloud import firestore as _gcf
    app = firebase_admin.get_app()
    return _gcf.Client(credentials=app.credential.get_credential(), project=app.project_id)


class _FirestoreHandle:
    """Stands in for the Firestore client everywhere this adapter uses one, forwarding
    every attribute to the CURRENT client, so rebuild() swaps the connection under every
    holder at once (see FIRESTORE WEDGE RECOVERY). `factory` builds a replacement; None
    means this process has no way to (rebuild() then refuses, and the health check only
    alerts).

    `owns_client`: may rebuild() CLOSE the client it replaces? False for a client a caller
    handed in that other code in the process still uses -- api/runner.py's shared `self.db`,
    which is also firebase_admin's cached firestore.client(): closing its channel would
    kill the runner's queue listener, job writes and command channel, and every later
    firestore.client() call in that process. A client this handle built itself is always
    its own, so every rebuild after the first closes the one it replaces."""

    def __init__(self, client, factory=None, owns_client=True):
        self._client = client
        self._factory = factory
        self._owns_client = bool(owns_client)
        self._lock = threading.Lock()
        self.generation = 0

    @property
    def client(self):
        return self._client

    @property
    def can_rebuild(self):
        return self._factory is not None

    def __getattr__(self, name):
        client = self.__dict__.get("_client")
        if client is None:
            raise AttributeError(name)
        return getattr(client, name)

    def rebuild(self, log=print):
        """(ok, why). Builds the new client FIRST and only then swaps and closes the old
        one, so a factory that fails leaves the old client in place. The old client is
        closed only if this handle owns it (see `owns_client`); one it does not own is
        just dropped from this adapter, and its other users keep it."""
        if self._factory is None:
            return False, "this process has no way to build a new Firestore client"
        try:
            new = self._factory()
        except Exception as e:
            return False, f"building a new Firestore client failed ({type(e).__name__}: {e})"
        if new is None:
            return False, "building a new Firestore client returned nothing"
        with self._lock:
            old, self._client = self._client, new
            close_old, self._owns_client = self._owns_client, True
            self.generation += 1
        if close_old:
            _close_firestore_client(old, log=log)
        return True, None


def _as_firestore_handle(db):
    """`db` as a _FirestoreHandle (unchanged if it already is one; None stays None). A real
    google-cloud-firestore client handed in raw (api/runner.py's fallback thread) gets the
    firebase_admin factory; anything else (a test double) gets none. A client handed in
    raw is never this adapter's to close: the runner's is its shared `self.db` (see
    _FirestoreHandle, `owns_client`)."""
    if db is None or isinstance(db, _FirestoreHandle):
        return db
    real = type(db).__module__.startswith("google.cloud.firestore")
    return _FirestoreHandle(db, factory=_new_firestore_client if real else None,
                            owns_client=False)


def _bounded_call(fn, name):
    """fn() on a fresh daemon thread; returns a Future. The caller decides how long to
    wait. Daemon, so a call that never returns cannot keep the process from exiting."""
    fut = concurrent.futures.Future()

    def _run():
        if not fut.set_running_or_notify_cancel():
            return
        try:
            fut.set_result(fn())
        except BaseException as e:
            fut.set_exception(e)
    threading.Thread(target=_run, name=name, daemon=True).start()
    return fut


_lease_read_lock = threading.Lock()
_lease_read_inflight = {"future": None}


def _reset_lease_read():
    """Forget a lease read still stuck on the old connection (after a rebuild), so the
    next read goes out through the new one instead of failing as "still running"."""
    with _lease_read_lock:
        _lease_read_inflight["future"] = None


def _lease_read_retry(timeout):
    """The lease read's retry: the client default's quick retry of a one-off 503 /
    deadline / internal error -- the routine blip when Google's front end resets a
    long-lived gRPC connection -- but ending at `timeout` instead of the default's five
    minutes. With NO retry, one such blip failed the broker check closed and the cached
    verdict then blocked every OPEN for lease_verify_interval_sec (the real Webull entry
    lost while the shadow book took it); with the default retry, a read abandoned by
    _read_lease_doc kept retrying in the background for up to five minutes, holding the
    one lease-read slot. None when google-api-core is not installed."""
    try:
        from google.api_core import exceptions as _gex
        from google.api_core import retry as _gretry
    except Exception:
        return None
    kw = dict(initial=0.1, maximum=1.0, multiplier=1.3,
              predicate=_gretry.if_exception_type(_gex.ServiceUnavailable,
                                                  _gex.DeadlineExceeded,
                                                  _gex.InternalServerError))
    try:
        return _gretry.Retry(timeout=timeout, **kw)
    except TypeError:
        return _gretry.Retry(deadline=timeout, **kw)   # older google-api-core


def _get_lease_doc(db, uid, timeout):
    ref = _lease_ref(db, uid)
    # A bounded retry (see _lease_read_retry): a single blip is retried, and the whole
    # read still ends near its wall-clock limit.
    try:
        snap = ref.get(retry=_lease_read_retry(timeout), timeout=timeout)
    except TypeError:
        if type(ref).__module__.startswith("google.cloud.firestore"):
            # A real client: never drop to the bare get(), whose default retry runs for
            # up to five minutes and would hold the one lease-read slot that long. One
            # more single attempt, still bounded by `timeout`; a second TypeError is a
            # failed read (broker sends fail closed).
            snap = ref.get(retry=None, timeout=timeout)
        else:
            snap = ref.get()   # test doubles whose get() takes no keyword arguments
    return snap.to_dict() if getattr(snap, "exists", True) else None


def _read_lease_doc(db, uid, timeout=None):
    """The status doc (dict or None) read under a HARD wall-clock limit -- FIRESTORE WEDGE
    RECOVERY part 1. Raises the read's own error, or _FsCallTimeout when it ran past
    `timeout` (default LEASE_READ_TIMEOUT_SEC) or the previous read is still stuck."""
    timeout = LEASE_READ_TIMEOUT_SEC if timeout is None else float(timeout)
    with _lease_read_lock:
        prev = _lease_read_inflight.get("future")
        if prev is not None and not prev.done():
            raise _FsCallTimeout("the previous lease read is still running "
                                 f"(stuck past {timeout:g}s)")
        fut = _bounded_call(lambda: _get_lease_doc(db, uid, timeout), "qqq-lease-read")
        _lease_read_inflight["future"] = fut
    try:
        return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise _FsCallTimeout(f"lease read timed out after {timeout:g}s") from None


def _maybe_rebuild_firestore(db, state=None, log=print, now=None):
    """FIRESTORE WEDGE RECOVERY part 3, called once per loop pass. Does nothing until
    _FS_HEALTH trips; then rebuilds the connection (on backoff) and, if it is still
    failing after a rebuild -- or this process cannot rebuild at all -- says so ONCE per
    episode: a log line, an event and a high push. Returns "rebuilt", "alerted",
    "alerted+rebuilt" or None. Never raises."""
    try:
        now = time.time() if now is None else now
        h = _FS_HEALTH
        can = isinstance(db, _FirestoreHandle) and db.can_rebuild
        with h._lock:
            clear_phone, h.phone_clear = bool(getattr(h, "phone_clear", False)), False
        if clear_phone:
            _say_clear(state, "database", log=log)
        with h._lock:
            if not h.tripped(now):
                # 10-08 review: a "database" slot left in state.json by an outage BEFORE a
                # restart is never ended by note_ok (this fresh process never entered that
                # episode). Firestore calls working with no episode open = that outage is
                # over: end its slot, so a new outage the same day pushes again.
                stale_slot = (h.streak == 0 and h.oks > 0
                              and not (h.rebuilds or h.alerted or h.alert_tries
                                       or h.backoff is not None)
                              and isinstance(state, dict)
                              and "database" in (state.get("_phone_dedupe") or {}))
            else:
                stale_slot = None
        if stale_slot is not None:
            if stale_slot:
                _say_clear(state, "database", log=log)
            return None
        with h._lock:
            if not h.tripped(now):
                return None
            streak, since, err, rebuilds = h.streak, h.first_fail_at, h.last_err, h.rebuilds
            do_alert = ((not h.alerted) and (rebuilds >= 1 or not can)
                        and now >= h.next_alert_at)
            do_rebuild = can and now >= h.next_rebuild_at
            first_alert = do_alert and h.alert_tries == 0
            if do_alert:
                h.alert_tries += 1
            if do_rebuild:
                backoff = h.backoff if h.backoff is not None else FS_REBUILD_BACKOFF_SEC
                h.rebuilds += 1
                h.streak, h.first_fail_at = 0, None
                h.next_rebuild_at = now + backoff
                h.backoff = min(backoff * 2.0, FS_REBUILD_BACKOFF_MAX_SEC)
        mins = max(0.0, (now - since) / 60.0) if since else 0.0
        did = []
        if do_alert:
            if can:
                msg = (f"QQQ EXEC: Firestore is still unreachable after rebuilding the "
                       f"connection {rebuilds} time(s) -- {streak} failed call(s) in a row "
                       f"over {mins:.0f} min (latest: {err}). Webull orders stay blocked "
                       "until this host's lease can be confirmed; it keeps retrying, or "
                       "restart edgelog-qqq-exec.")
            else:
                msg = (f"QQQ EXEC: Firestore unreachable -- {streak} failed call(s) in a "
                       f"row over {mins:.0f} min (latest: {err}). This process cannot "
                       "rebuild its Firestore connection; Webull orders stay blocked until "
                       "the lease can be confirmed -- restart the executor.")
            if first_alert:
                # the log line and the event once per episode; only the push is retried
                log(f"[qqq-exec] {msg}")
                if state is not None:
                    _log_event(state, "firestore_down", msg, log=log)
            try:
                # WEBULL PUSH PLAN 10-07, group I: the executor OWNS "cloud database
                # unreachable" (it sees it first and knows the cause). Plain text through
                # _say (once a day); a send that FAILED (False) is put back by _say, so the
                # retry below goes out; None (no topic) / True / "queued" / held end it.
                _action, sent = _say(state, "database", _phone_day(), ntfy_push.plain(
                    PHONE_AREA, "CHECK NOW", "the QQQ book cannot send orders",
                    f"The cloud database has been unreachable for {max(1, round(mins))} min",
                    ("nothing yet - it keeps reconnecting; " + PHONE_ASK + " if it lasts")
                    if can else PHONE_ASK + " - the QQQ order program needs a restart",
                    priority="high"), log=log)
            except Exception as e:
                log(f"[qqq-exec] Firestore alert push failed: {type(e).__name__}: {e}")
                sent = False
            # The episode's one push counts only once it went out: False (tried, failed --
            # the network may be down too) tries again after FS_ALERT_RETRY_SEC. None (no
            # topic set), True, or "queued" (the ntfy outbox keeps retrying it -- see
            # _notify) ends it.
            with h._lock:
                if sent is False:
                    h.next_alert_at = now + FS_ALERT_RETRY_SEC
                else:
                    h.alerted = True
            if sent is False:
                log(f"[qqq-exec] the Firestore outage push did not go out -- trying again in "
                    f"{FS_ALERT_RETRY_SEC:.0f}s")
            did.append("alerted")
        if do_rebuild:
            ok, why = db.rebuild(log=log)
            if ok:
                _publisher.reset_worker()
                _reset_lease_read()
                if state is not None:
                    # re-read the lease on the next tick, through the new connection --
                    # dropping a cached "blocked" verdict early never loosens the gate
                    state.pop("_lease_verify_at", None)
                line = (f"Firestore calls failing ({streak} in a row over {mins:.0f} min, "
                        f"latest: {err}) -- rebuilt the Firestore connection in-process "
                        f"(rebuild {rebuilds + 1} this episode)")
            else:
                line = f"Firestore calls failing ({streak} in a row) -- rebuild failed: {why}"
            log(f"[qqq-exec] {line}")
            if state is not None:
                _log_event(state, "firestore_rebuild", line, log=log)
            did.append("rebuilt")
        return "+".join(did) or None
    except Exception as e:
        log(f"[qqq-exec] Firestore rebuild check failed (non-fatal): {type(e).__name__}: {e}")
        return None


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
        result = fut.result(timeout=timeout)
        _FS_HEALTH.note_ok(log=log)   # claimed or refused, Firestore answered
        return result
    except concurrent.futures.TimeoutError:
        why = f"lease claim timed out after {timeout:g}s"
        _FS_HEALTH.note_fail(why)
    except Exception as e:
        why = f"lease claim failed ({type(e).__name__}: {e})"
        _FS_HEALTH.note_fail(e)
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
    # RESTING ORB STOP (2026-09-29 second review): this host's resting orders go with it
    _cancel_resting_on_stand_down(state, log=log)
    # Already standing by within the last few minutes means this host never really held the
    # lease (a claim that failed open on flaky reads, then found the other host): one phone
    # alert per real loss, not one per systemd restart while reads keep flapping.
    repeat, _note = standby_fresh()
    _note_standby(reason, log=log)
    if not repeat:
        # WEBULL PUSH PLAN 10-07, group I: high -- trading on this machine stopped (before
        # the save below, so the repeat rule's memory is saved with it). Accepted cost (10-08
        # review): the outbox makes one synchronous try first (up to its POST timeout, ~4 s)
        # before it queues, so on a slow network this save can wait that long -- this is the
        # terminal stand-down path; this host has already stopped trading.
        _say(state, "stood_down", _phone_day(), _stood_down_note(), log=log)
    try:
        _log_event(state, "lease_lost", f"Stood down on {host}: {reason}", log=log)
        save_state(state, log=log)
    except Exception as e:
        log(f"[qqq-exec] could not record the stand-down: {type(e).__name__}: {e}")


def serve(db, uids, log=print):
    """Run the adapter in THIS process until killed, or until it loses the cross-host
    lease. qqq_exec_thread holds the serving slot and the heartbeat and runs the LEASE
    PROTOCOL; this is the standalone's front door. Returns at once while another host's
    lease is fresh, leaving a STANDBY marker -- on the VM systemd restarts the unit, which
    is how a refused standalone keeps re-checking.

    SERVING_HOSTS GATE (2026-09-26, MINOR review fix): checked FIRST, before
    serving_alive/_check_lease -- an excluded host used to reach _check_lease (a
    Firestore read, and possibly _note_standby) and log a misleading "SERVING" line
    before qqq_exec_thread's OWN copy of this gate ever refused it. If the box ever
    excludes itself (a hostname typo in serving_hosts), systemd's Restart=always /
    RestartSec=15 turned that into a Firestore read plus a misleading SERVING line every
    15s. Refused here, this never reads the lease and never logs SERVING at all."""
    hosts_ok, hosts_reason = _serving_hosts_ok(_read_config_for_gate(log=log), log=log)
    if not hosts_ok:
        log(f"[qqq-exec] REFUSING to serve: {hosts_reason} -- no lease read, no SERVING "
            "line")
        return
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
            # FIRESTORE WEDGE RECOVERY (2026-10-05): a handle the loop can rebuild in-process
            # -- the process's only Firestore user, so it owns (and may close) the client
            db = _FirestoreHandle(firestore.client(), factory=_new_firestore_client,
                                  owns_client=True)
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
