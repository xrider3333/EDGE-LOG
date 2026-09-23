"""api/cloud_signal.py — cloud SIGNAL ENGINE for the three crowned NQ strategies,
running on QQQ share bars, meant to eventually feed a Webull execution adapter.

NO ORDER CODE OF ANY KIND. This module never imports a broker SDK, never places an
order, never touches a live/paper account. It reads bars, runs the same engine the
rest of this repo already uses (augur_engine.engine.run_backtest), diffs the
resulting trade list against what it last saw, and writes SIGNAL events (ENTRY /
EXIT) to a CSV ledger. Nothing downstream of this file exists yet — a future
execution module reads signals.csv (or a Firestore mirror of it) and decides what to
do about them. That is a DIFFERENT module, not a flag flip in this one.

WHY THIS EXISTS. tools/qqq_paper.py already replays the three crowned NQ strategies
on QQQ bars and writes a paper blotter — it is the model/backtest half. This module
is the forward-looking SIGNAL half: it is built to run continuously (or be replayed
bar-by-bar) and emit discrete, idempotent, timestamped events an order-placing layer
can consume one at a time, rather than a blotter you re-read start to finish.

PORTABLE PATHS. EDGELOG_HOME (default C:\\EdgeLog on Windows, ~/edgelog elsewhere)
is the root. Bar cache lives under <home>/ohlc/ (QQQ_1m.csv / QQQ_5m.csv — on the
owner's machine, with EDGELOG_HOME unset, this IS tools/qqq_paper.py's own
C:\\EdgeLog\\ohlc cache, same files, no duplication). Engine state lives under
<home>/cloud_signal/ (signals.csv, state.json, heartbeat.json).

DATA REUSE. The yfinance fetch/chunking (`_fetch_yf`) and the epoch-schema /
RTH-array builder (`_to_epoch_frame`, `build_arrays`) are IMPORTED from
tools/qqq_paper.py, not reimplemented — those functions are pure (no path constants
baked in) so reuse is a straight import. Only the on-disk CACHE READ/WRITE path
differs (this module writes under EDGELOG_HOME, qqq_paper.py always writes under
literal C:\\EdgeLog\\ohlc) — qqq_paper.py's own behaviour is completely unchanged by
this file's existence. The rename-into-place retry (`qp._replace_with_retry`, added
2026-09-14) is reused the same way: ONE helper backs every risky `os.replace` in both
files, because both write the very same shared OHLC cache and Windows refuses that
rename outright while any reader -- including the OTHER writer's own read of the same
file -- still has it open.

THE THREE CROWN LEGS (as of 2026-09-24; NOISE swapped by OWNER DECISION 2026-09-23):
  ORB_R6      run #314, ORB_3_6_R6.py, api.paper.ORB_314, 5m RTH, no gate.
  NOISE_382   run #382, NOISE_1_8_CT304.py, params below, 5m RTH, no gate.
              (repointed 2026-09-24 -- run #382 is the #304 crown's own core, written out
              literally inside that file, plus the validated hourly-compression SIZE tilt
              (tilt_mult 2.0, gate_tf_min 30, gate_len 16, gate_ratio 1.15 -- all inside
              that file's own FENCED admissible set). #304 stays in api/qqq_exec.py's
              ENGINE_LEG_MAP (-> the same "NOISE" exec leg) purely so an in-flight trade
              id or an old signals.csv row keeps resolving; it is GONE from CROWN_LEGS
              itself, not kept alongside. api/paper.py's OWN "NOISE_304" leg (the
              NinjaTrader PAPER board, api.paper.NOISE_304_NBHD) is a DIFFERENT book and
              is UNCHANGED and unrelated to this one.)
  ENGUQ_335   run #335, ENGUQ_1M_ETH_R2_1_0.py, api.paper.ENGUQ_335, 1m **ETH**, no gate.

ENGINE LIMITATION, READ BEFORE TRUSTING THE ENGUQ_335 LEG. The ENGU-Q family crown
moved to an ETH (23-hour NQ futures) config on 2026-09-08. yfinance QQQ bars (this
module, exactly like tools/qqq_paper.py, pulls prepost=False) only ever cover the
09:30-16:00 ET regular session — there is no equivalent of NQ's overnight Globex tape
for a cash equity. Running ENGUQ_335's ETH-fit parameters on an RTH-only splice is a
KNOWN mismatch, not a hidden one:
  1. `regime_len` in ENGUQ_1M_ETH_R2_1_0.py's parent file counts regime blocks as
     `regime_len * 390` bars (see that file's own frozen unit-notice comment) — 390
     is the RTH bar count, so on the ETH tape it trained on, regime_len=10 means
     ~3.6 CALENDAR days of history; spliced onto QQQ's RTH-only bars (390 bars really
     IS one session here) the same knob instead reads as 10 SESSIONS. The regime
     filter fires on a different real-world lookback than the one it was validated on.
  2. The strategy file hardcodes an absolute `risk < max(0.25, 0.5): skip trade`
     floor (a flat $0.50 price distance) and an ATR floor of 0.25 inside the breakout
     test — both calibrated against NQ's ~$25,000 price level, where $0.50 is noise.
     Against a ~$700 QQQ share these floors bind far more often, silently gating out
     (or, depending on the local ATR, silently admitting) trades the crown's own
     validate never saw.
  This leg still RUNS (it does not raise) and is included below because the task is
  to signal the current crowns, not to invent a safer substitute unasked — but its
  signals should be read as exploratory, not evidence-backed, until this is fixed
  properly (an ETH-equivalent data source, or a from-scratch RTH re-validation of the
  file). tools/qqq_paper.py made the opposite call for its own ENGUQ leg (it
  deliberately keeps running the older RTH #149 variant rather than the ETH crown,
  for exactly this reason) — see that file's update note, 2026-09-08.

CLI
  python -m api.cloud_signal --replay YYYY-MM-DD   replay one cached session bar-by-
                                                     bar, print the signal ledger +
                                                     the NT-vs-QQQ comparison table.
                                                     ISOLATED: runs in a temp copy of
                                                     the bar cache with a cold state
                                                     and never writes the live ledger
  python -m api.cloud_signal --replay YYYY-MM-DD --live-paths
                                                     explicit opt-in: replay INTO the
                                                     live <home>/cloud_signal ledger +
                                                     state; refused while a live
                                                     writer's heartbeat is fresh
  python -m api.cloud_signal --once                 one live step() and exit
  python -m api.cloud_signal --loop                 step() every 20s during session
                                                     hours, sleep outside them
"""
import argparse
import datetime as _dt
import json
import logging as _logging
import math
import os
import shutil
import sys
import tempfile
import time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.engine import run_backtest as engine_run_backtest          # noqa: E402
from api import market_calendar                                             # noqa: E402
from api import trade_id as _trade_id                                       # noqa: E402
from api.paper import ORB_314, ENGUQ_335                                    # noqa: E402
import tools.qqq_paper as qp                                                # noqa: E402

TZ = qp.TZ                             # "US/Eastern" — same convention everywhere in this repo
RTH_OPEN = qp.RTH_OPEN
RTH_CLOSE = qp.RTH_CLOSE

# Bar must have fully closed at least this long before `now` before we act on it.
CLOSE_GRACE_SECONDS = 5

# Default rolling-window depth: "last N sessions" per the task spec. Actual depth used
# is always min(this, sessions available in the cache) — the cache today only holds
# ~25 sessions of 1m and ~65 of 5m, so this is a ceiling, not a promise of 60 real
# sessions of history.
DEFAULT_WARMUP_SESSIONS = 60

TIMEFRAME_SECONDS = {"1m": 60, "5m": 300}


def edgelog_home():
    h = os.environ.get("EDGELOG_HOME")
    if h:
        return h
    if os.name == "nt":
        return r"C:\EdgeLog"
    return os.path.expanduser("~/edgelog")


def _paths(home=None):
    home = home or edgelog_home()
    ohlc_dir = os.path.join(home, "ohlc")
    state_dir = os.path.join(home, "cloud_signal")
    return {
        "home": home,
        "ohlc_dir": ohlc_dir,
        "state_dir": state_dir,
        "signals_path": os.path.join(state_dir, "signals.csv"),
        "state_path": os.path.join(state_dir, "state.json"),
        "heartbeat_path": os.path.join(state_dir, "heartbeat.json"),
    }


# The LIVE store: the runner's parallel run writes here and api/qqq_exec.py consumes
# signals.csv by row cursor. Only live (fetching) callers may default to it -- an offline
# run gets isolated_paths() or an explicit paths dict (see isolated_paths, 2026-09-14).
DEFAULT_PATHS = _paths()

# ── Crown legs (current as of 2026-09-24 — see api/paper.py PAPER_LEGS) ─────────────────
# NOISE_382 (OWNER DECISION 2026-09-23): run #382's champion cell, read literally from the
# run's own doc. NOISE_1_8_CT304.py is FENCED (_ADMISSIBLE/_in_neighbourhood) -- it REFUSES
# (returns None) a configuration outside its declared neighbourhood rather than clamp one,
# so this dict must carry the exact cell the run picked, never a rounded/nearby guess.
# gate_tf_min in {30, 60}, gate_len in {16, 20}, gate_ratio in {1.0, 1.15},
# tilt_mult in {1.0, 1.5, 2.0} -- every value below sits on one of those points.
NOISE_382_PARAMS = {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15}


# ── KEEL v12 overlay (OWNER DECISION 2026-09-23) ─────────────────────────────────────────
# "Put KEEL v12 on top of run #382 on the live Webull NOISE leg, train it on the NQ
# backtest like the validation." See augur_engine/ml_keel.py's keel_build_state /
# keel_score_from_state (the build-once/score-many split this overlay is built on) and
# tools/keel_live_state.py (the nightly job that writes the files keel_paths() below
# names). AN OVERLAY, NEVER A GATE: every failure path in _keel_size_for_entry returns
# keel_size 1.0 (unsized -- exactly today's un-overlaid behaviour), logged, never raised
# -- see that function's own docstring. KEEL_MAX_STALE_SESSIONS caps how many trading
# sessions a state may lag "now" before it is treated as unavailable rather than trusted.
KEEL_MAX_STALE_SESSIONS = 5


def keel_paths(leg_key, version, home=None):
    """Where tools/keel_live_state.py writes -- and this module reads -- a leg's KEEL
    state (joblib, this-host-only, never copied across machines) and its JSON summary
    (plain-safe, freely readable). Same EDGELOG_HOME convention as _paths() above."""
    home = home or edgelog_home()
    d = os.path.join(home, "cloud_signal", "keel")
    return {"dir": d,
           "state_path": os.path.join(d, f"{leg_key}_{version}_state.joblib"),
           "summary_path": os.path.join(d, f"{leg_key}_{version}_summary.json")}


CROWN_LEGS = {
    "ORB_R6": {
        "strategy": "ORB_3_6_R6.py",
        "timeframe": "5m",
        "params": dict(ORB_314),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
    },
    "NOISE_382": {
        "strategy": "NOISE_1_8_CT304.py",
        "timeframe": "5m",
        "params": dict(NOISE_382_PARAMS),
        # same warm-up as every other crown leg -- the owner's spec calls for no change
        # here, only the strategy file + params under it.
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        # KEEL v12 overlay -- see the block comment above keel_paths(). Any OTHER leg's
        # cfg simply has no "keel" key, and every keel-aware code path below treats a
        # missing key exactly like today's pre-KEEL behaviour (see _diff_leg).
        "keel": dict(version="v12", **keel_paths("NOISE_382", "v12")),
    },
    "ENGUQ_335": {
        "strategy": "ENGUQ_1M_ETH_R2_1_0.py",
        "timeframe": "1m",
        "params": dict(ENGUQ_335),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
        # see module docstring "ENGINE LIMITATION" — flagged, not hidden
        "caveat": "ETH-fit crown running on an RTH-only QQQ tape — exploratory, not evidence-backed",
    },
}

# Sizing: identical convention to tools/qqq_paper.py (shares = floor($ notional / entry px)).
NOTIONAL_PER_LEG = qp.NOTIONAL_PER_LEG
SLIPPAGE_PER_SHARE = qp.SLIPPAGE_PER_SHARE


# ── Bar cache (portable read/write; reuses qp's fetch + array builder) ──────────────────
def _cache_path(timeframe, paths=None):
    paths = paths or DEFAULT_PATHS
    return os.path.join(paths["ohlc_dir"], f"QQQ_{timeframe}.csv")


def load_cached_bars(timeframe, paths=None):
    """Read the on-disk epoch-schema cache. None if nothing cached yet."""
    path = _cache_path(timeframe, paths)
    if not os.path.exists(path):
        return None
    import pandas as pd
    return pd.read_csv(path)


WEBULL_KEYS = os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json")
WEBULL_TOKEN_DIR = os.environ.get("EDGELOG_WEBULL_TOKEN_DIR", r"C:\EdgeLog\webull_token")
WEBULL_TAIL_BARS = 200          # see _fetch_webull


def _fetch_webull(timeframe, count=WEBULL_TAIL_BARS, log=print):
    """Recent QQQ bars from the official Webull OpenAPI, in this module's epoch schema,
    or None if unavailable. PREFERRED over yfinance since 2026-09-09, when the owner
    claimed the free Nasdaq Basic non-display tier: it is the exchange's own consolidated
    Level 1 feed, roughly a second behind the print, against yfinance's ~38s median for
    the newest CLOSED minute (measured, tools/qqq_feed_latency_probe.py).

    Only the TAIL is fetched. The API caps a request at 1200 bars while the rolling
    window wants tens of thousands, so history stays in the on-disk cache and this call
    just tops it up — the same shape the yfinance path always had.

    TOKEN: MarketData(api) does NOT authenticate; only ClientInitializer.initializer()
    attaches the x-access-token, and the SDK runs it inside TradeClient/DataClient but
    never inside MarketData. Omitting it is a silent 401 that reads like "no
    entitlement" — the bug that kept api/qqq_exec.py's quote path dark for the whole
    trial. Do not remove that call.

    RTH ONLY, matching the yfinance path's prepost=False: the crowned configs are
    regular-session configs and a spliced overnight bar would change what a bar means.
    """
    import json as _json
    import pandas as pd
    try:
        with open(WEBULL_KEYS, encoding="utf-8") as fh:
            keys = _json.load(fh)
        ak = (keys.get("app_key") or "").strip()
        sk = (keys.get("app_secret") or "").strip()
        if not ak or not sk or ak.startswith("PASTE_"):
            return None
        from webull.core.client import ApiClient
        from webull.core.http.initializer.client_initializer import ClientInitializer
        from webull.data.quotes.market_data import MarketData
        from webull.data.common.category import Category
        from webull.data.common.timespan import Timespan
        span = {"1m": Timespan.M1, "5m": Timespan.M5}.get(timeframe)
        if span is None:
            return None
        api = ApiClient(ak, sk, (keys.get("region") or "us").strip().lower(),
                        token_check_duration_seconds=15, token_check_interval_seconds=5,
                        connect_timeout=10, timeout=25)
        os.makedirs(WEBULL_TOKEN_DIR, exist_ok=True)
        api.set_token_dir(WEBULL_TOKEN_DIR)
        # the SDK otherwise attaches a rotating file logger on the shared CWD, which the
        # five runner processes fight over every hour (WinError 32)
        api._file_logger_set = True
        _logging.getLogger("webull.core").addHandler(_logging.NullHandler())
        ClientInitializer.initializer(api)
        resp = MarketData(api).get_history_bar("QQQ", Category.US_ETF, span, count=str(count))
        rows = resp.json() if hasattr(resp, "json") else resp
        if not isinstance(rows, list) or not rows:
            return None
        out = []
        for r in rows:
            if str(r.get("trading_session", "RTH")).upper() != "RTH":
                continue
            try:
                ts = int(pd.Timestamp(r["time"]).timestamp())
                out.append({"time": ts, "open": float(r["open"]), "high": float(r["high"]),
                            "low": float(r["low"]), "close": float(r["close"]),
                            "volume": float(r.get("volume") or 0.0)})
            except Exception:
                continue
        if not out:
            return None
        return pd.DataFrame(out).sort_values("time").reset_index(drop=True)
    except Exception as e:
        log(f"[cloud-signal] webull bars unavailable ({timeframe}): {type(e).__name__}: {e}")
        return None


def fetch_and_merge(timeframe, paths=None, log=print):
    """Pull fresh bars, merge into the cache under EDGELOG_HOME, and return
    (merged_epoch_frame, source, cache_ok) where source is "webull" or "yfinance" --
    whichever one actually produced THIS call's fresh rows -- and cache_ok is False
    only when the on-disk rename could not be completed (see RENAME RETRY below).
    Network call — never invoked from --replay or from tests, only from a live step().

    Webull first, yfinance as the fallback. Both are consolidated US equity prints for
    the same regular session, so they agree to the cent in normal conditions; the cache
    can therefore hold rows from either without a seam. If that ever stops being true it
    shows up as a price jump exactly at a source change, so the fallback logs when it
    fires rather than switching silently.

    The returned `source` is what api/qqq_exec.py's engine-mode pricing (and the web
    tab's status panel) report as WEBULL/YAHOO -- see `read_bar_source` below, which
    persists this into state.json so a DIFFERENT process (the standalone qqq_exec
    adapter) can read it without importing this module's live fetch path.

    RENAME RETRY (2026-09-14). `os.replace(tmp, path)` used to be a single unretried
    call: `C:\\EdgeLog\\ohlc\\QQQ_1m.csv`/`QQQ_5m.csv` are read by several other
    short-lived processes (tools/qqq_paper.py's own independent sync of the SAME files
    when EDGELOG_HOME is unset, a replay, a test snapshot), and Windows refuses the
    rename outright -- not a retry-free race, an outright PermissionError -- while any
    of them merely has the destination open for reading. Seen live: `[cloud-signal]
    step failed: PermissionError [WinError 32] ... 'QQQ_1m.csv.tmp' -> 'QQQ_1m.csv'`,
    which aborted the whole step() call (this leg's bars were already fetched and
    merged in memory, but the exception propagated before any leg's signals were
    evaluated) and made cloud_signal_thread mark the heartbeat ok=false -- which
    api/qqq_exec.py's engine-mode feed check reads as "stale", blocking new entries,
    for what was really a few-millisecond reader lock. `qp._replace_with_retry` rides
    that out (see its docstring for the budget); `merged` is already fully computed by
    the time the rename is attempted, so this function returns it regardless of
    whether the rename succeeded -- the caller (step()) can still evaluate signals off
    it even when cache_ok is False, and only the ON-DISK cache is a step behind until
    the next successful fetch."""
    import pandas as pd
    paths = paths or DEFAULT_PATHS
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    path = _cache_path(timeframe, paths)
    old = load_cached_bars(timeframe, paths)
    if old is None:
        old = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    fresh = _fetch_webull(timeframe, log=log)
    source = "webull"
    if fresh is None or not len(fresh):
        log(f"[cloud-signal] falling back to yfinance for {timeframe} bars")
        fresh_df = qp._fetch_yf(timeframe)
        fresh = qp._to_epoch_frame(fresh_df)
        source = "yfinance"
    merged = pd.concat([old, fresh], ignore_index=True)
    if len(merged):
        merged = merged.drop_duplicates("time", keep="last").sort_values("time")
    # ATOMIC (2026-09-09): to_csv() TRUNCATES then writes, so a reader that opens the file
    # mid-write gets an empty or half-written cache. That is not hypothetical -- this thread
    # rewrites the cache every 30s and it caught the test suite red-handed, which is exactly
    # what a strategy run or a manual replay would have hit instead. Write beside it and
    # rename: os.replace is atomic on Windows and POSIX, so a reader sees the old file or
    # the new one, never a torn one. RETRIED (2026-09-14, see docstring above) rather than
    # left to raise on the first transient lock.
    tmp = path + ".tmp"
    merged.to_csv(tmp, index=False)
    cache_ok = qp._replace_with_retry(tmp, path, log=log,
                                      what=f"[cloud-signal] {timeframe} bar cache")
    return merged, source, cache_ok


def read_bar_source(paths=None):
    """Best-effort read of state.json's `bar_source` block: {timeframe: {"source",
    "newest_epoch", "checked_at"}}, written by step() on every FETCHING call (--once /
    --loop / the runner thread; never --replay, which passes fetch=False and touches no
    network). Returns {} if the state file is absent or this process's step() has never
    fetched live yet -- a caller in a different process (api/qqq_exec.py, engine mode)
    reads this instead of importing the live fetch path itself."""
    paths = paths or DEFAULT_PATHS
    try:
        return _load_state(paths).get("bar_source") or {}
    except Exception:
        return {}


build_arrays = qp.build_arrays   # pure transform, reused as-is


# ── Rolling window + "closed bars only" ──────────────────────────────────────────────────
def _closed_cutoff_epoch(now, timeframe):
    """Bars whose CLOSE (bar-open-time + timeframe) is <= now - grace are usable."""
    now_epoch = int(now.timestamp())
    return now_epoch - CLOSE_GRACE_SECONDS - TIMEFRAME_SECONDS[timeframe]


def closed_arrays(all_epoch_df, now, timeframe, warmup_sessions):
    """epoch_df -> RTH arrays (via qp.build_arrays), filtered to bars CLOSED as of
    `now`, then trimmed to the last `warmup_sessions` distinct sessions ending at or
    before `now`'s own session. Returns None if there is nothing usable yet.

    PERFORMANCE: a cheap raw-epoch prefilter runs BEFORE build_arrays (which does the
    tz-aware pandas datetime conversion + day factorize — the actually expensive
    part). Without it, replay()'s per-closed-bar recompute pays that cost against the
    ENTIRE cache every single call (390+ times for a 1m leg), which is what made an
    early version of this function take 80+ seconds per replayed session. Restricting
    to a calendar-day window first bounds that cost to roughly the window size
    regardless of total cache depth.

    BUFFER SIZE (fixed 2026-09-13 — see tools/orb_qqq_warmup_bug.py). The buffer used
    to be a flat `warmup_sessions + 5` calendar days, on the theory that 5 days was
    "generous" slack for weekends/holidays. It is not: `warmup_sessions` counts TRADING
    days, which run only 5/7 of calendar days, so 60 trading sessions span roughly 84
    calendar days, not 65. The undersized buffer silently truncated the raw prefilter
    to whichever sessions fit inside it (measured: 47 sessions instead of the intended
    60 on the real QQQ cache), which is one bug on its own (every trailing filter gets
    less history than its own code asks for) — but the worse half is that `cutoff`
    (and therefore `lower_bound`) advances continuously with `now` throughout a single
    session, so as wall-clock time passes within ONE trading day the oldest session can
    age out of the too-tight buffer mid-afternoon, shrinking the window by exactly one
    session at that instant. Every session's index into the trailing-N-session
    reference (ORB's atr_filter/vpace_filter, and any other plugin doing the same
    pattern) shifts by one at that moment, which can flip a same-day trading decision
    hours after the fact: reproduced on 2026-09-04 (ORB_3_6_R6.py's atr/vpace filters),
    where an entry at the day's 09:55 bar was ABSENT from the engine's trade list at
    every tick through 14:05 and PRESENT from 14:06 onward, with no new bar of ANY
    session boundary involved — purely the raw calendar buffer dropping 2026-07-01 out
    of the window at that exact wall-clock moment. The entry then aged past
    `max_entry_age_sec` and was recorded as "late" (silently suppressed) — this time.
    A smaller shift, or a filter less sensitive to one session's weight in a median,
    would instead have emitted a spurious ENTRY that only exists because of when the
    engine happened to be asked, which is a live correctness bug, not merely a stale
    diagnostic. Fix: size the buffer off the actual 5-trading-days-per-7-calendar-days
    cadence plus real slack for holidays, so the buffer always covers `warmup_sessions`
    sessions and the raw prefilter is a no-op (keeps every session actually available)
    long before `keep_days` needs to trim anything — making the exact-session-count
    trim below the ONLY thing that ever changes the window, and only once a day (when
    the calendar date itself rolls, not mid-session)."""
    if all_epoch_df is None or not len(all_epoch_df):
        return None
    cutoff = _closed_cutoff_epoch(now, timeframe)
    calendar_buffer_days = math.ceil(int(warmup_sessions) * 7 / 5) + 15
    lower_bound = cutoff - calendar_buffer_days * 86400
    df = all_epoch_df[(all_epoch_df["time"] <= cutoff) & (all_epoch_df["time"] >= lower_bound)]
    arrays = build_arrays(df)
    if arrays is None or not len(arrays["close"]):
        return None
    day_id = arrays["day_id"]
    distinct_days = sorted(set(day_id.tolist()))
    keep_days = set(distinct_days[-int(warmup_sessions):])
    mask = [d in keep_days for d in day_id]
    if not any(mask):
        return None
    import numpy as np
    mask = np.array(mask)
    out = {k: (v[mask] if k != "index" else v[mask]) for k, v in arrays.items()}
    return out


# ── One leg's trades -> canonical records ────────────────────────────────────────────────
class _TradeSizeContractError(Exception):
    """Raised by _resolve_trade_sizes when a plugin DECLARES the additive per-trade
    size contract (trade_sizes/size_cost_pts -- see NOISE_1_8_CT304.py's ADDITIVE
    SIZE CONTRACT comment) but the declaration itself is broken. Always caught by
    run_leg_trades, which fails that leg's WHOLE call closed rather than guess."""


def _leg_label(cfg, leg_key):
    """Best-effort human-readable name for a leg in a log line, for a caller (a
    test, or a standalone tool) that did not pass leg_key -- step() always does."""
    if leg_key:
        return str(leg_key)
    strat = cfg.get("strategy")
    if isinstance(strat, str):
        return strat
    return getattr(strat, "STRATEGY_NAME", None) or getattr(strat, "__name__", None) or repr(strat)


def _resolve_trade_sizes(res, n_trades, label):
    """Validates the additive per-trade size contract a sizing plugin's result dict
    may carry (trade_sizes: list of floats, same length/order as `trades`;
    size_cost_pts: the cost constant it folded in -- see NOISE_1_8_CT304.py's
    ADDITIVE SIZE CONTRACT comment). Returns (sizes, cost) -- a list of validated
    floats and a float -- when the contract is present and sound, or (None, None)
    when the plugin simply does not size at all (no `trade_sizes` key: the ordinary,
    unaffected case). Raises _TradeSizeContractError the instant a DECLARED contract
    looks wrong in any way -- caught by run_leg_trades, which fails that whole call
    closed rather than guess. There is no partial-credit path: a badly-declared size
    is exactly as dangerous as an undeclared one, so a broken declaration is never
    quietly treated as "not sizing".
    """
    sizes = res.get("trade_sizes")
    if sizes is None:
        return None, None
    cost = res.get("size_cost_pts")
    if cost is None:
        raise _TradeSizeContractError(
            f"{label}: trade_sizes present ({len(sizes)} value(s)) but size_cost_pts is missing")
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        raise _TradeSizeContractError(f"{label}: size_cost_pts {cost!r} is not a number")
    if not math.isfinite(cost):
        raise _TradeSizeContractError(f"{label}: size_cost_pts {cost!r} is not finite")
    if len(sizes) != n_trades:
        raise _TradeSizeContractError(
            f"{label}: trade_sizes has {len(sizes)} entries for {n_trades} trade(s)")
    out = []
    for idx, s in enumerate(sizes):
        try:
            sf = float(s)
        except (TypeError, ValueError):
            sf = float("nan")
        if not math.isfinite(sf) or sf <= 0:
            raise _TradeSizeContractError(
                f"{label}: trade_sizes[{idx}] = {s!r} is not a finite positive size")
        out.append(sf)
    return out, cost


def run_leg_trades(cfg, arrays, leg_key=None, log=print):
    """Runs the plugin (or a stub module override) via the shared engine wrapper and
    converts the raw (entry_bar, exit_bar, pnl_pts, side, entry_px) tuples into
    canonical dicts keyed by wall-clock timestamps (not bar indices — those are only
    valid for the exact arrays slice they came from, and the rolling window's start
    shifts every call).

    PER-TRADE SIZE (2026-09-23). A sizing plugin (NOISE_1_8_CT304.py today; the KEEL
    overlay later) can additively declare trade_sizes/size_cost_pts in its result dict
    -- see that file's ADDITIVE SIZE CONTRACT comment and this module's
    _resolve_trade_sizes. When declared and valid, every trade dict below carries the
    real per-trade size in "size" and a real, inverted exit_px. A plugin that never
    sizes gets "size": 1.0 on every trade and the exact exit_px arithmetic this
    function has always used -- byte-for-byte unaffected. A plugin whose declaration
    is broken (see _resolve_trade_sizes) fails the WHOLE call closed: this returns []
    and logs why, rather than guess at a price that would mis-size every order
    downstream.
    """
    res = engine_run_backtest(cfg["strategy"], arrays=arrays, params=cfg["params"],
                              cost_pts=0.0, return_trades=True)
    if not res or not res.get("trades"):
        return []
    idx = arrays["index"]
    n_bars = len(arrays["close"])
    last_close = float(arrays["close"][n_bars - 1])

    trades_raw = res["trades"]
    label = _leg_label(cfg, leg_key)
    try:
        leg_sizes, size_cost_pts = _resolve_trade_sizes(res, len(trades_raw), label)
    except _TradeSizeContractError as e:
        log(f"[cloud-signal] {e} -- refusing to emit signals for {label} this call "
           f"(a wrong size inversion would mis-price every order it sends)")
        return []
    sizes_declared = leg_sizes is not None

    # PRICE-BASED "STILL OPEN AT THE BOUNDARY" TEST -- SAFE ONLY WHEN THE LEG PROMISES
    # eod_marks_at_close (default True; see the AMBIGUOUS BOUNDARY comment in the loop
    # below). Two known ways a plugin can break that promise, and what makes each safe
    # (2026-09-22 audit; sizing contract added 2026-09-23):
    #   - ORB_3_6.py:346-350's EOD-flat block does not always mark an unresolved end-of-
    #     data position at a clean last-bar close: whenever a partial exit already fired
    #     (p_done, gated on `partial_exit_R > 0` at ORB_3_6.py:320 and :338), the reported
    #     pnl is a 50/50 blend of the partial fill and the final close (line 348), so the
    #     price test would usually read the still-half-open position as a genuine close.
    #     The live ORB_R6 leg pins partial_exit_R=0.0 (api/paper.py:177-180, ORB_314), so
    #     this is inert today -- but that is a PARAMS fact, not a code fact, and a params
    #     change must not silently arm a mechanism that flattens a live position early.
    #     Checked explicitly below, every call, unrelated to sizing.
    #   - A plugin that folds a per-trade size multiplier into pnl_pts (NOISE_1_8_CT304.py
    #     -- see its ADDITIVE SIZE CONTRACT comment) breaks the exit-price reconstruction
    #     UNLESS it declares trade_sizes/size_cost_pts: `sizes_declared` above is only
    #     True once that declaration has passed _resolve_trade_sizes, at which point the
    #     fold is inverted below and exit_px is real again -- the price test needs no help
    #     from this leg's cfg. The manual escape hatch (cfg["eod_marks_at_close"] = False)
    #     is required ONLY for a plugin that folds size into pnl_pts WITHOUT declaring it:
    #     there is no way to detect that case from the result dict alone, so it stays an
    #     explicit, manual promise on the leg config -- exactly as before this contract
    #     existed.
    # A leg opts out of the price test -- falling back to the OLD, conservative rule that
    # ANY trade still sitting at the boundary reads as open, price notwithstanding -- via
    # an explicit cfg["eod_marks_at_close"] = False (ALWAYS honoured, even when sizes are
    # declared) or automatically the moment its own declared params turn on
    # ORB's partial-exit blend. An explicit True never overrides the partial_exit_R check;
    # only the strategy's own params, or a validated size declaration, can prove the price
    # safe.
    _partial_exit_r = float((cfg.get("params") or {}).get("partial_exit_R") or 0)
    # An explicit eod_marks_at_close=False is ALWAYS honoured, sizes declared or not: the
    # conservative rule can only delay an exit by a bar, never invent one, so a caution a
    # human wrote on a leg must not be overridden by a contract they may not know about.
    # A valid size declaration only removes the NEED for that flag on a size-folding leg.
    _eod_promise = cfg.get("eod_marks_at_close", True)
    eod_marks_at_close = _eod_promise and not (_partial_exit_r > 0)

    if sizes_declared:
        paired = list(zip(trades_raw, leg_sizes))
    else:
        paired = [(t, 1.0) for t in trades_raw]
    paired.sort(key=lambda p: p[0][0])

    out = []
    for (entry_bar, exit_bar, pnl_pts, side, entry_px), size in paired:
        entry_bar = int(entry_bar); exit_bar = int(exit_bar)
        entry_px = float(entry_px)
        if sizes_declared:
            # INVERTED EXIT PRICE (2026-09-23): the plugin folded
            # pts = size*raw - (size-1)*size_cost_pts before handing this trade back
            # (see its ADDITIVE SIZE CONTRACT comment); this is the exact algebraic
            # inverse, recovering the real raw price move, so exit_px below is a real
            # price again -- not a synthetic, cost/size-scaled number.
            raw = (pnl_pts + (size - 1.0) * size_cost_pts) / size
            exit_px = entry_px + raw * side
        else:
            # UNCHANGED: reconstructed from entry_px and the reported pnl_pts alone,
            # which is only ever the real fill price when pnl_pts is a raw price
            # difference -- true for every plugin that does not fold a size multiplier
            # into it.
            exit_px = entry_px + pnl_pts * side
        if exit_bar < n_bars - 1:
            still_open = False
        elif not eod_marks_at_close:
            # OLD, conservative rule for a leg whose boundary price can't be trusted (see
            # above): any trade still sitting at the boundary reads as open, no matter
            # what its (possibly blended or synthetic) reported price says.
            still_open = True
        else:
            # AMBIGUOUS BOUNDARY (2026-09-22): every plugin reachable here with
            # eod_marks_at_close true force-closes a position that is still open when its
            # data runs out by marking it at the newest bar's own CLOSE (NOISE_1_0.py's
            # "STEP E" EOD backstop, ORB_3_6.py's "EOD flat" block when no partial exit
            # has fired, ENGUQ_1M_ETH_R2_1_0.py's end-of-walk fallback and its compiled
            # twin in augur_engine/fastloop.py's _walk_jit all do this). So exit_bar ==
            # n_bars - 1 is produced BOTH by a position that is genuinely still open (the
            # strategy simply ran out of bars) and by one that closed for real exactly on
            # the newest bar — the two are NOT distinguishable by bar index alone, which
            # is what the old `exit_bar >= n_bars - 1` rule assumed, and why every real
            # exit on the newest bar was emitted a bar late and collided with whatever
            # entered next.
            #
            # They ARE distinguishable by price: a genuine close can land anywhere (an
            # open-fill, a stop or band level, ...), but the data-end fallback is ALWAYS
            # the last bar's own close, exactly. So a reported exit price that differs
            # from that close by more than a hair means the position really closed; one
            # that matches it means the plugin never got a chance to do anything but the
            # boilerplate flatten, i.e. it is still open. Relative tolerance, not exact
            # equality: pnl_pts round-trips through a subtraction (close - entry) and
            # back (entry + pnl), which can lose the last ULP even when both sides mean
            # the same price.
            # The inverted size fold above is exact algebraically, so this reasoning
            # holds for a declared-size leg too.
            still_open = abs(exit_px - last_close) <= 1e-6 * abs(last_close) + 1e-9
        shares = int(math.floor(NOTIONAL_PER_LEG / entry_px)) if entry_px > 0 else 0
        out.append({
            "side": "long" if side > 0 else "short",
            "entry_time": idx[entry_bar].isoformat(),
            "entry_px": round(entry_px, 4),
            "shares": max(shares, 0),
            "exit_time": None if still_open else idx[min(exit_bar, n_bars - 1)].isoformat(),
            "exit_px": None if still_open else round(exit_px, 4),
            "still_open": still_open,
            "size": size,
            # additive (2026-09-23, KEEL overlay): the entry's own bar index into THIS
            # call's `arrays` -- needed to slice a feature row for the KEEL overlay (see
            # _keel_size_for_entry) at the exact bar the trade fired on. Nothing before
            # this reads it, so it changes no existing behaviour.
            "entry_bar": entry_bar,
        })
    return out


# ── KEEL v12 overlay -- see the block comment above keel_paths() near CROWN_LEGS ─────────
_KEEL_STATE_CACHE = {}   # state_path -> (mtime, state, summary-or-None)


def _load_keel_state(state_path, summary_path, log=print):
    """Best-effort load of a KEEL state + its JSON summary, cached by the state file's
    OWN mtime so a fresh nightly rebuild is picked up without restarting this process,
    and a repeat call within the same tick never re-reads a multi-MB joblib file twice.
    Returns (state, summary) -- summary may be None even when state loads fine (its
    file missing/unreadable is not fatal, only staleness reporting degrades). NEVER
    raises: every failure returns (None, None), which _keel_size_for_entry turns into
    the safe keel_size 1.0 fallback."""
    try:
        mtime = os.path.getmtime(state_path)
    except OSError:
        return None, None
    cached = _KEEL_STATE_CACHE.get(state_path)
    if cached and cached[0] == mtime:
        return cached[1], cached[2]
    try:
        import joblib
        state = joblib.load(state_path)
    except Exception as e:
        log(f"[cloud-signal] KEEL state unreadable ({state_path}): {type(e).__name__}: {e}")
        return None, None
    summary = None
    try:
        if os.path.exists(summary_path):
            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)
    except Exception as e:
        log(f"[cloud-signal] KEEL summary unreadable ({summary_path}): {type(e).__name__}: {e}")
    _KEEL_STATE_CACHE[state_path] = (mtime, state, summary)
    return state, summary


def _keel_size_for_entry(keel_cfg, arrays, entry_bar, entry_time, log=print):
    """The KEEL multiplier for ONE new entry about to be emitted (design: "compute the
    KEEL size once" -- see _diff_leg, the only caller). Reads the trade's own feature
    row from `keel_features` on `arrays` (the QQQ arrays the leg already uses) at
    `entry_bar`, and scores it against the nightly-built NQ state -- see
    augur_engine.ml_keel.keel_score_from_state.

    ALWAYS returns a finite float > 0 as its first element -- 1.0 (unsized, i.e.
    "behave exactly like no overlay") on ANY failure: the state file missing or
    unreadable, feature columns that do not match what the state was built on, more
    than KEEL_MAX_STALE_SESSIONS trading sessions between the state's last trained NQ
    session and this entry's own session, or an exception anywhere in the scoring
    call. Every failure is logged with a short reason (the second return value) and
    NEVER raised -- KEEL is an OVERLAY, not a gate, so a broken overlay must never
    block or delay the trade it would have merely resized. The second return value is
    a short human-readable reason string on any fallback, or a diagnostics dict
    (z/trust/rho/t_fast) on a real score -- for logging only.
    """
    if not keel_cfg or entry_bar is None:
        return 1.0, None
    state, summary = _load_keel_state(keel_cfg["state_path"], keel_cfg.get("summary_path", ""),
                                      log=log)
    if state is None:
        return 1.0, "keel state unavailable"
    try:
        last_session = (summary or {}).get("last_nq_session")
        if last_session:
            entered = entry_time
            if isinstance(entered, str):
                entered = _dt.datetime.fromisoformat(entered)
            sessions = market_calendar.sessions_between(last_session, entered.date().isoformat())
            n_stale = max(0, len(sessions) - 1)
            if n_stale > KEEL_MAX_STALE_SESSIONS:
                return 1.0, (f"keel state stale: {n_stale} session(s) since {last_session}")
        from augur_engine import ml_keel as _keel
        F, names = _keel.keel_features(arrays)
        if list(names) != list(state.get("feature_names") or []):
            return 1.0, "keel feature columns do not match the state"
        row = int(min(max(int(entry_bar), 0), len(F) - 1))
        size, diag = _keel.keel_score_from_state(state, arrays, row, x_row=F[row:row + 1],
                                                 cross_series=True)
        if not math.isfinite(size) or size <= 0:
            return 1.0, f"keel scoring returned a non-finite/non-positive size ({size!r})"
        return float(size), diag
    except Exception as e:
        log(f"[cloud-signal] KEEL scoring failed: {type(e).__name__}: {e}")
        return 1.0, f"keel scoring error: {type(e).__name__}: {e}"


def _entry_key(leg, trade):
    """The key a leg's emitted-trade memory (leg_state['trades']) is stored under: the
    trade's stable id from api/trade_id.py -- leg + entry bar time + side, and NOT the entry
    price (2026-09-14). The old key carried the price, so the same trade re-priced by a
    cent (Webull vs yfinance bars for one minute can disagree, and the cache keeps
    whichever source wrote last) looked brand new: within a few bars it re-emitted as a
    second ENTRY, and either way the original key dropped out of the trade list, so its
    EXIT was never emitted. The price-bearing form is only a fallback for a trade whose id
    cannot be formed (never the case for a well-formed engine trade); such a trade's rows
    carry an empty trade_id and api/qqq_exec.py refuses to act on them."""
    return _trade_id.make(leg, trade.get("entry_time"), trade.get("side")) or _legacy_entry_key(leg, trade)


def _legacy_entry_key(leg, trade):
    return f"{leg}|{trade['entry_time']}|{trade['side']}|{trade['entry_px']:.4f}"


# leg_state["key_format"] once _rekey_recorded_trades has run for that leg.
TRADE_KEY_FORMAT = "trade_id_v1"


def _merge_rank(rec):
    """Which of two memory records for ONE trade id to keep when re-keying: a record whose
    ENTRY really was emitted beats a skipped/seeded twin (its EXIT may still be owed), and
    among emitted ones a record whose EXIT already went out beats one still waiting (the
    trade is one trade -- a second EXIT would only find no lot)."""
    emitted_entry = not rec.get("skipped") and not rec.get("seeded")
    return (emitted_entry, bool(rec.get("exit_emitted")))


def _rekey_recorded_trades(leg_key, leg_state):
    """One-time, idempotent upgrade of a leg's emitted-trade memory from the pre-2026-09-14
    price-bearing keys to trade ids (see _entry_key). Without it, the first step() after
    the upgrade would find none of its own records: every trade still in the window would
    look new, a trade open across the upgrade would be recorded as LATE with its exit
    marked done, and its real EXIT would never be emitted. Price twins of one trade merge
    via _merge_rank. Returns how many records merged away."""
    if leg_state.get("key_format") == TRADE_KEY_FORMAT:
        return 0
    recorded = leg_state.get("trades") or {}
    out = {}
    for key, rec in recorded.items():
        new_key = _trade_id.make(leg_key, (rec or {}).get("entry_time"), (rec or {}).get("side")) or key
        cur = out.get(new_key)
        out[new_key] = rec if cur is None else max((cur, rec), key=_merge_rank)
    leg_state["trades"] = out
    leg_state["key_format"] = TRADE_KEY_FORMAT
    return len(recorded) - len(out)


# ── State I/O ───────────────────────────────────────────────────────────────────────────
def _load_state(paths):
    if not os.path.exists(paths["state_path"]):
        return {"legs": {}}
    with open(paths["state_path"], encoding="utf-8") as f:
        return json.load(f)


def _write_state(state, paths):
    """state.json is the idempotency ledger (which trades each leg has already emitted),
    read back by the very next step() call -- unlike the bar cache, losing this write
    silently would let the next tick re-diff against stale memory and re-emit ENTRY/EXIT
    rows _append_signals already wrote for THIS call. So the rename retries the same
    transient-lock budget as every other writer here (qp._replace_with_retry -- a reader
    such as a manual `_load_state` call or a debugging read can have this file open for
    the same few milliseconds the OHLC cache readers do), but on final failure it RAISES
    instead of continuing: the caller (step()) must not reach _append_signals having
    silently failed to persist that those events were already recorded."""
    os.makedirs(paths["state_dir"], exist_ok=True)
    tmp = paths["state_path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    if not qp._replace_with_retry(tmp, paths["state_path"], log=print,
                                  what="[cloud-signal] state.json"):
        raise OSError(f"cloud_signal: could not replace {paths['state_path']} after retries")


SIGNAL_COLS = ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares", "reason",
              # appended, never inserted -- api/qqq_exec.py's engine mode and the web tab's
              # status panel read this to attribute a trade's price to WEBULL or YAHOO.
              "bar_source",
              # appended, never inserted (2026-09-14) -- the trade's stable id
              # (api/trade_id.py: leg + entry bar time + side), IDENTICAL on its ENTRY and
              # its EXIT row. An EXIT's ref_time is the exit bar, so without this column an
              # EXIT row cannot say which trade it closes. "" on SEED rows.
              "trade_id",
              # appended, never inserted (2026-09-23) -- the per-trade size multiplier.
              # For a leg with NO "keel" block in CROWN_LEGS this is the plugin's own
              # declared size (run_leg_trades: 1.0 for a leg that does not size at all)
              # -- UNCHANGED by the KEEL overlay below. For a leg WITH a "keel" block
              # (NOISE_382 today) this is the PRODUCT plugin_size * keel_size (see
              # _diff_leg / _keel_size_for_entry) -- the executor's existing
              # size-to-shares multiply (api/qqq_exec.py's _sized_shares) needs no
              # change to pick up KEEL sizing, because it already multiplies by
              # whatever is in this column. "" on SEED rows and on any row written
              # before this column existed -- a blank here means "1.0, unsized", never
              # "unknown".
              "size",
              # appended, never inserted (2026-09-23, KEEL overlay) -- the KEEL
              # multiplier ALONE (this leg's "size" column above is plugin_size x this
              # value), for the trade drawer's breakdown display and for telling apart
              # "no keel overlay on this leg" (blank) from "keel ran and stood down at
              # 1.0" or "keel failed safe to 1.0" (a real 1.0, logged -- see
              # _keel_size_for_entry) -- both real numbers, never blank. Blank on SEED
              # rows, on every non-KEEL leg's rows, and on any row written before this
              # column existed.
              "keel_size"]


def _read_signals_header(path):
    """signals.csv's on-disk header as a list of names; None if missing, empty or unreadable."""
    import csv
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return next(csv.reader(f), None) or None
    except Exception:
        return None


def _migrate_signals_header(path, cols, _retries=20, _sleep=0.05):
    """If `path` already exists under an OLDER header -- a strict prefix of `cols` (e.g.
    before `bar_source` or `trade_id` was added) -- rewrite it under the new header, padding
    every old row's missing fields with "" -- same rationale and pattern as api/qqq_exec.py's
    `_migrate_csv_header`: a code upgrade that appends a column must never desync the
    on-disk header from what DictWriter is about to write next. A no-op when the header
    already matches. Never raises.

    PREFIX ONLY (2026-09-14). Any other header -- longer, because a newer writer appended a
    column this version has never heard of, or different -- is left exactly as it is.
    Rewriting it under `cols` would delete those columns from every row, which is what the
    pre-2026-09-14 copy of this function does to trade_id whenever an old checkout appends
    to the live ledger. _append_signals writes aligned to whatever header is on disk.

    ATOMIC (2026-09-14). This used to truncate signals.csv and rewrite it in place, while
    api/qqq_exec.py reads the same file every 5 s and consumes it by ROW COUNT -- a read
    landing inside the rewrite saw a short or empty ledger. The new file is written beside
    it and renamed over it, so a reader sees the old file or the new one. Windows refuses
    that rename while any reader has the file open, so it is retried (via the shared
    qp._replace_with_retry -- this was the first of this module's writers to retry at
    all, before the OHLC cache write and state.json write gained the same helper); if it
    still fails the file is left untouched (and the next append tries again) -- never
    rewritten in place."""
    import csv
    tmp = None
    try:
        header = _read_signals_header(path)
        cols = list(cols)
        if not header or header == cols:
            return
        if not (len(header) < len(cols) and cols[:len(header)] == header):
            return
        with open(path, encoding="utf-8", newline="") as f:
            old_rows = list(csv.DictReader(f))
        tmp = "%s.%d.migrate.tmp" % (path, os.getpid())
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in old_rows:
                w.writerow({c: r.get(c, "") for c in cols})
        # log=None: this call has always failed silently (the boot-time caller logs its
        # OWN "ledger header check failed" only for a raised exception, never for this
        # already-quiet retry-exhausted path) -- keep that, don't add a new log line here.
        qp._replace_with_retry(tmp, path, log=None,
                               what="[cloud-signal] signals.csv header upgrade",
                               retries=_retries, sleep=_sleep)
        tmp = None   # renamed away on success, or already cleaned up on failure
    except Exception:
        pass
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def _append_signals(events, paths):
    if not events:
        return
    os.makedirs(paths["state_dir"], exist_ok=True)
    path = paths["signals_path"]
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    import csv
    fieldnames = SIGNAL_COLS
    if not new_file:
        _migrate_signals_header(path, SIGNAL_COLS)
        # Rows follow the header that is actually on disk: normally SIGNAL_COLS, but a newer
        # writer's longer header is never rewritten (see _migrate_signals_header), and an old
        # header stays if its upgrade could not swap in this time. Unknown columns stay "".
        fieldnames = _read_signals_header(path) or SIGNAL_COLS
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
        for e in events:
            w.writerow({k: e.get(k, "") for k in fieldnames})


# ── The core entry point ───────────────────────────────────────────────────────────────
def step(now=None, legs=None, paths=None, fetch=True, warnings=None):
    """One signal-engine tick. For each leg: load cached bars (optionally refreshed
    from yfinance first), restrict to bars CLOSED as of `now`, run the engine over the
    rolling warm-up window, and diff the resulting trade list against what was last
    persisted for that leg. Returns the list of NEW events emitted THIS call (empty on
    a rerun at the same `now` — idempotent by construction: every event is keyed by
    the trade id (leg, entry bar time, side -- see _entry_key) and a key already recorded
    in state.json is never re-emitted).

    `legs`: defaults to CROWN_LEGS; pass a different dict (e.g. with a stub strategy
    module as cfg["strategy"]) to test the diff/idempotency machinery in isolation.
    `fetch`: pull fresh bars over the network first. --replay always passes False (it
    must stay fully offline and deterministic); --once/--loop pass True.
    `paths`: the state store. Defaults to the live DEFAULT_PATHS ONLY for a fetching
    (live) call. An offline call (fetch=False) must name its store: it used to fall
    through to the live ledger too, which is how a replay contaminated it twice (see
    isolated_paths), and a lone offline step into a fresh scratch store could only ever
    cold-start, so there is no useful default to give it instead.
    `warnings`: optional dict this call may POPULATE (never reads) with non-fatal
    problems the caller should surface without treating the whole tick as failed.
    Currently only `cache_write_failed` (bool, 2026-09-14): at least one timeframe's
    on-disk bar cache could not be replaced this call even after fetch_and_merge's own
    retries, though the freshly fetched bars were still used from memory for every
    leg's signal evaluation below (they are already in `tf_cache` by the time the
    rename is attempted -- see fetch_and_merge). A caller that writes a heartbeat
    (cloud_signal_thread, cmd_once, cmd_loop) uses this to still report ok=True with a
    note instead of raising, so a transient disk/lock hiccup does not make
    api/qqq_exec.py's engine-mode feed check see a stale heartbeat and block entries
    over something that never affected the signals it will act on.
    """
    legs = legs if legs is not None else CROWN_LEGS
    if paths is None:
        if not fetch:
            raise ValueError("step(fetch=False) needs an explicit `paths`: an offline step must "
                             "not default to the live ledger -- use replay() or "
                             "isolated_paths(), or pass DEFAULT_PATHS on purpose")
        paths = DEFAULT_PATHS
    now = now or _dt.datetime.now(tz=_zi(TZ))
    if now.tzinfo is None:
        now = now.replace(tzinfo=_zi(TZ))

    state = _load_state(paths)
    state.setdefault("legs", {})
    all_events = []

    tf_cache = {}
    # PRICE-SOURCE ATTRIBUTION (feature: engine-mode status panel / api/qqq_exec.py):
    # persisted to state.json below as state["bar_source"][tf], not kept only in this
    # in-process dict -- the standalone qqq_exec adapter is a DIFFERENT process and can
    # only see this via the file (see read_bar_source).
    tf_source = {}
    for key, cfg in legs.items():
        tf = cfg["timeframe"]
        if fetch and tf not in tf_cache:
            tf_cache[tf], tf_source[tf], cache_ok = fetch_and_merge(tf, paths)
            if not cache_ok and warnings is not None:
                warnings["cache_write_failed"] = True
        elif tf not in tf_cache:
            tf_cache[tf] = load_cached_bars(tf, paths)
        epoch_df = tf_cache[tf]
        leg_state = state["legs"].setdefault(key, {"trades": {}})
        if epoch_df is None or not len(epoch_df):
            continue

        # Skip the (expensive) engine recompute unless a NEW bar of THIS leg's own
        # timeframe has closed since the last time we checked. A 5m leg ticked every
        # minute (replay()) or every 20s (--loop) only has real work to do once every
        # 5 real minutes — its trade list literally cannot have changed without a new
        # bar — and recomputing anyway is exactly what made an early version of this
        # function cost O(ticks) instead of O(bars) per replayed session.
        cutoff = _closed_cutoff_epoch(now, tf)
        usable = epoch_df[epoch_df["time"] <= cutoff]
        if not len(usable):
            continue
        latest_bar_epoch = int(usable["time"].max())
        if tf in tf_source:
            state.setdefault("bar_source", {})[tf] = {
                "source": tf_source[tf], "newest_epoch": latest_bar_epoch,
                "checked_at": now.isoformat()}
        if leg_state.get("last_bar_epoch") == latest_bar_epoch:
            continue
        leg_state["last_bar_epoch"] = latest_bar_epoch

        arrays = closed_arrays(epoch_df, now, tf, cfg.get("warmup_sessions", DEFAULT_WARMUP_SESSIONS))
        if arrays is None:
            continue

        trades = run_leg_trades(cfg, arrays, leg_key=key)
        # Three bars of grace by default: a signal may legitimately be discovered a bar or
        # so late, but never hours late (see _diff_leg's LATE ENTRIES note). A leg may set
        # its own `max_entry_age_sec` when its bar size makes three bars the wrong measure.
        events = _diff_leg(key, trades, leg_state, now,
                           max_entry_age_sec=cfg.get("max_entry_age_sec",
                                                     3 * TIMEFRAME_SECONDS[tf]),
                           bar_source=(state.get("bar_source", {}).get(tf, {}).get("source")),
                           cfg=cfg, arrays=arrays)
        all_events.extend(events)
        leg_state["asof"] = arrays["index"][-1].isoformat()

    state["generated_at"] = now.isoformat()
    _write_state(state, paths)
    _append_signals(all_events, paths)
    return all_events


def _zi(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        import pytz
        return pytz.timezone(name)


def _diff_leg(leg_key, trades, leg_state, now, max_entry_age_sec=None, bar_source=None,
             cfg=None, arrays=None, log=print):
    """Mutates leg_state['trades'] (entry_key -> record) in place; returns the list of
    NEW ENTRY/EXIT event dicts this call discovered.

    `cfg`/`arrays` (2026-09-23, KEEL overlay): `cfg` is this leg's own CROWN_LEGS entry
    (step() always passes it; a caller that omits it -- every test written before this
    feature, and any leg with no "keel" block -- gets EXACTLY today's pre-KEEL
    behaviour, see the ENTRY branch below) and `arrays` are the QQQ arrays `trades` was
    computed from, needed to slice the new entry's own feature row. KEEL is scored
    ONCE, only for a leg whose cfg carries a "keel" block, only at the moment an ENTRY
    is about to be emitted (never during SEED -- see the COLD START note below -- and
    never recomputed for that trade's later EXIT, which reuses the value this call
    stores on `rec`).

    `bar_source` ("webull"/"yfinance"/None) is stamped onto every event this call emits
    (including SEED) so a downstream consumer -- api/qqq_exec.py's engine mode, or the
    web tab's status panel -- can show which QQQ feed priced this specific trade, without
    re-deriving it later from a rolling bar_source history that may have moved on.

    STALE ENTRIES ARE NEVER ACTIONABLE. The engine recomputes each leg's trade list
    over a ROLLING warm-up window, and a trade sitting at that window's left edge is
    not identity-stable: strategies warm their indicators from the first bar of the
    array they are handed (ORB_3_6.py's volume-pace reference is a 20-bar nanmean that
    is literally an empty slice at index 0), so as the window slides forward the oldest
    trades can shift entry bar or entry price by a hair -- which changes their
    _entry_key and makes them look brand new. Measured on the real QQQ cache: a
    2026-09-04 replay emitted ENTRY events dated 2026-07-01 for exactly this reason.
    An entry that is not in TODAY's session cannot be acted on at today's price under
    any circumstances, so it is recorded silently (and counted in
    leg_state['stale_skipped']) instead of being emitted. Its exit is suppressed with
    it -- an executor that never entered cannot exit. Exits of trades whose ENTRY *was*
    emitted still fire normally on a later day (an overnight ENGU-Q hold closing the
    next morning is a real, wanted EXIT).

    COLD START (leg never seen before). The engine re-derives each leg's WHOLE trade
    list over the rolling warm-up window on every call, so the very first call for a
    leg legitimately "discovers" every trade the strategy took over the last N
    sessions. Emitting those as ENTRY/EXIT would hand a downstream execution layer
    dozens of actionable orders for trades that closed weeks ago -- the same defect
    api/qqq_exec.py had to fix for NinjaTrader fills on first boot (v73.459, "never
    replay pre-today fills"). So the first call for a leg ABSORBS the history
    silently: every trade is recorded as already-emitted (including one that is still
    open -- an executor that never entered cannot exit) and a single non-actionable
    SEED event is written to the ledger naming what was absorbed. Only trades the
    engine opens AFTER the seed produce ENTRY/EXIT. Consumers must act on ENTRY/EXIT
    only and ignore any other event type.

    TRADE ID (2026-09-14). Every ENTRY and EXIT event carries `trade_id` (api/trade_id.py),
    the same value on both rows of one trade, and it is also the key of this leg's memory
    (see _entry_key; _rekey_recorded_trades upgrades a pre-2026-09-14 memory once). An
    executor closes a position only with the EXIT whose trade_id matches the one it opened.
    """
    events = []
    _rekey_recorded_trades(leg_key, leg_state)
    recorded = leg_state.setdefault("trades", {})
    if not leg_state.get("seeded"):
        open_at_seed = "none"
        for t in trades:
            recorded[_entry_key(leg_key, t)] = {
                "entry_time": t["entry_time"], "side": t["side"],
                "entry_px": t["entry_px"], "shares": t["shares"],
                "exit_emitted": True, "exit_time": t.get("exit_time"),
                "exit_px": t.get("exit_px"), "seeded": True,
            }
            if t["still_open"]:
                open_at_seed = f"{t['side']} @ {t['entry_px']} ({t['entry_time']})"
        leg_state["seeded"] = True
        events.append({
            "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
            "leg": leg_key, "event": "SEED", "side": "", "ref_time": "",
            "ref_price": "", "shares": "", "bar_source": bar_source or "", "trade_id": "", "size": "",
            # KEEL is never scored during a cold-start SEED (design: "the cold-start
            # SEED path must not score or emit anything") -- a batch of dozens of
            # absorbed historical trades is not one live entry, and none of them are
            # ever acted on, so there is nothing meaningful to size.
            "keel_size": "",
            "reason": (f"cold start: absorbed {len(trades)} historical trade(s) without "
                       f"emitting; open_at_seed={open_at_seed}"),
        })
        return events
    # LATE ENTRIES ARE NOT ACTIONABLE EITHER (2026-09-09, seen live). "Entry is from today"
    # was too weak a test. After the 12:44 runner restart this engine re-derived the day and
    # emitted an ENGU-Q ENTRY stamped 10:07 -- two and a half hours old -- because it was
    # still technically today. An executor cannot take a 10:07 price at 12:44; it would open
    # at a different price than the one the signal was justified at, which is precisely the
    # divergence the whole parallel run exists to measure. Being one bar late is normal and
    # fine; being hours late means a gap (restart, data outage) and the trade is gone. So an
    # entry must be within a few bars of `now` to emit, and anything older is recorded
    # silently and counted in `late_skipped` -- visible, but never handed downstream.
    today = now.date().isoformat()
    for t in trades:
        key = _entry_key(leg_key, t)
        tid = key if _trade_id.is_valid(key) else ""
        rec = recorded.get(key)
        if rec is None:
            # One trade, ONE reason. STALE = the entry is not even from today (the rolling
            # window's left edge re-minting an old trade). LATE = today, but discovered too
            # many bars after the fact to act on. They are different failures and counting
            # a trade under both makes each counter a lie.
            skip = None
            if str(t["entry_time"])[:10] != today:
                skip = "stale"
            elif max_entry_age_sec:
                try:
                    entered = _dt.datetime.fromisoformat(str(t["entry_time"]))
                    if entered.tzinfo is None:
                        entered = entered.replace(tzinfo=_zi(TZ))
                    if (now - entered).total_seconds() > max_entry_age_sec:
                        skip = "late"
                except Exception:
                    pass
            recorded[key] = {"entry_time": t["entry_time"], "side": t["side"],
                             "entry_px": t["entry_px"], "shares": t["shares"],
                             "exit_emitted": bool(skip), "exit_time": None,
                             "exit_px": None, "skipped": skip}
            if skip:
                counter = f"{skip}_skipped"
                leg_state[counter] = int(leg_state.get(counter, 0)) + 1
                continue
            # real per-trade size when the leg declares one, else 1.0 -- see
            # run_leg_trades's PER-TRADE SIZE contract and SIGNAL_COLS's "size" column.
            # This is the PLUGIN's own size -- KEEL (below) multiplies IT, never the
            # other way around, and the P&L un-fold inside run_leg_trades already used
            # this same plugin size alone (KEEL is computed after that un-fold, so it
            # cannot touch it).
            plugin_size = t.get("size", 1.0)
            keel_size = ""
            final_size = plugin_size
            keel_cfg = (cfg or {}).get("keel")
            if keel_cfg:
                # KEEL SCORED ONCE, HERE -- exactly when this new entry is about to be
                # emitted (design: "compute the KEEL size once and emit size = plugin
                # size x keel size"). Never recomputed for this trade again -- the
                # EXIT branch below reuses `rec`'s stored values -- and never called
                # during SEED (see that branch, above).
                ks, _diag = _keel_size_for_entry(keel_cfg, arrays, t.get("entry_bar"),
                                                 t["entry_time"], log=log)
                keel_size = ks
                final_size = plugin_size * ks
            rec = recorded[key]
            rec["size"] = final_size
            rec["keel_size"] = keel_size
            events.append({
                "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
                "leg": leg_key, "event": "ENTRY", "side": t["side"],
                "ref_time": t["entry_time"], "ref_price": t["entry_px"],
                "shares": t["shares"], "reason": "", "bar_source": bar_source or "",
                "trade_id": tid,
                "size": final_size,
                "keel_size": keel_size,
            })
        if (not t["still_open"]) and (not rec["exit_emitted"]):
            rec["exit_emitted"] = True
            rec["exit_time"] = t["exit_time"]
            rec["exit_px"] = t["exit_px"]
            # SIZE NEVER CHANGES AFTER ENTRY (design). A keel-scored leg reuses exactly
            # the size/keel_size this SAME trade's ENTRY stored on `rec` above -- never
            # a fresh KEEL score (the ledger/state may have moved on by exit time, and
            # re-scoring would let one trade's order size drift after the fact). A leg
            # with no "keel" block is completely unaffected: same t.get("size", 1.0)
            # this line has always read.
            if (cfg or {}).get("keel"):
                exit_size = rec.get("size", t.get("size", 1.0))
                exit_keel_size = rec.get("keel_size", "")
            else:
                exit_size = t.get("size", 1.0)
                exit_keel_size = ""
            events.append({
                "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
                "leg": leg_key, "event": "EXIT", "side": t["side"],
                "ref_time": t["exit_time"], "ref_price": t["exit_px"],
                "shares": t["shares"], "reason": "strategy_exit",
                "bar_source": bar_source or "",
                # the ENTRY's id, not one built from the exit bar -- see SIGNAL_COLS
                "trade_id": tid,
                # the same per-trade size as the ENTRY event -- see SIGNAL_COLS
                "size": exit_size,
                "keel_size": exit_keel_size,
            })
    return events


# ── Replay ──────────────────────────────────────────────────────────────────────────────
def _session_minute_closes(day, tz_name=TZ, max_ticks=None):
    """Every 1-minute bar-close timestamp inside RTH for `day` (a session day) — the
    finest granularity any leg needs (ENGUQ_335 is 1m). `step()` itself skips the
    actual engine recompute for a 5m leg on the 4 out of 5 ticks where its own latest
    closed bar hasn't advanced, so ticking every minute here costs 5m legs nothing
    extra. `max_ticks` caps how many closes are returned (from the start of the
    session) — see replay()'s docstring."""
    tz = _zi(tz_name)
    d = market_calendar._coerce_date(day)
    start = _dt.datetime.combine(d, RTH_OPEN, tzinfo=tz)
    end = _dt.datetime.combine(d, RTH_CLOSE, tzinfo=tz)
    out = []
    t = start + _dt.timedelta(minutes=1)   # first CLOSE is one minute after open
    while t <= end:
        out.append(t)
        if max_ticks is not None and len(out) >= max_ticks:
            break
        t += _dt.timedelta(minutes=1)
    return out


def isolated_paths(legs=None, source_paths=None, root=None):
    """A throwaway paths dict for an OFFLINE run: a fresh temp home holding a COPY of the
    bar cache for every timeframe `legs` uses (copied from `source_paths`, default the
    live DEFAULT_PATHS) and an empty cloud_signal/ dir, so the run starts cold and every
    file it writes lands in the copy. The caller owns the folder (paths["home"]) --
    replay() removes the one it makes for itself; the CLI keeps its copy for inspection.

    WHY (2026-09-14, the second time). `python -m api.cloud_signal --replay 2026-09-03`
    ran replay(day) -> step(paths=None) -> DEFAULT_PATHS, straight into the live ledger
    the runner's parallel run appends to and api/qqq_exec.py consumes by row cursor. At
    00:55 ET it wrote a NOISE_304 SEED plus 2026-09-03 ENTRY/EXIT rows and left that
    day's 11:00 trade recorded as entered-but-still-open, so at 09:31 ET the LIVE engine
    emitted the EXIT of a trade from eleven days earlier and the shadow adapter consumed
    it (no lot happened to be open). 2026-09-09 was the same mistake by hand. A replay
    row's emitted_at is the real clock, so the adapter cannot tell it from a live
    signal: the only safe replay is one that cannot reach the live files unless someone
    asks for exactly that (--live-paths)."""
    legs = legs if legs is not None else CROWN_LEGS
    source_paths = source_paths or DEFAULT_PATHS
    paths = _paths(home=tempfile.mkdtemp(prefix="cloud_signal_replay_", dir=root))
    try:
        os.makedirs(paths["ohlc_dir"], exist_ok=True)
        for tf in sorted({cfg["timeframe"] for cfg in legs.values()}):
            src = _cache_path(tf, source_paths)
            if os.path.exists(src):
                # one read of a file the live writer only ever os.replace()s -- never torn
                shutil.copyfile(src, _cache_path(tf, paths))
    except BaseException:
        shutil.rmtree(paths["home"], ignore_errors=True)
        raise
    return paths


def replay(day, legs=None, paths=None, warmup_sessions=None, max_ticks=None):
    """Replay one cached session bar-by-bar (1-minute granularity), calling step() at
    each closed-bar boundary with fetch=False (fully offline — only ever reads the
    on-disk cache). Returns the events THIS call emitted. Replay the same day twice
    against one persistent store to see the idempotency guarantee: the second call's
    return is empty.

    `paths`: the store to replay INTO. The default (None) is a throwaway
    isolated_paths() copy, removed when the replay returns, so every default call starts
    cold -- and never the live DEFAULT_PATHS (see isolated_paths for the incident). Pass
    a paths dict you own to keep the ledger/state or rerun against it; pass DEFAULT_PATHS
    only when writing into the live ledger is genuinely the point.

    `warmup_sessions`: overrides every leg's warm-up window for this call only (does
    not mutate CROWN_LEGS/legs). `max_ticks`: replay only the first N 1-minute closes
    of the session instead of the full ~390. Both exist for
    tests/test_cloud_signal.py's speed budget — the rolling-window recompute-on-new-
    bar design costs real wall-clock time per bar (pandas datetime/tz parsing on the
    slice, then the engine call), and the production defaults (60 sessions, the full
    session) are unnecessarily slow for a unit test that is only checking the
    diff/idempotency mechanics, not strategy fidelity or full-day coverage. The CLI
    (`--replay`, used for the real report) always uses the production defaults.
    """
    legs = legs if legs is not None else CROWN_LEGS
    if warmup_sessions is not None:
        legs = {k: dict(v, warmup_sessions=warmup_sessions) for k, v in legs.items()}
    if not market_calendar.is_session(day):
        raise ValueError(f"{day} is not a session day (holiday or weekend)")
    own_scratch = paths is None
    if own_scratch:
        paths = isolated_paths(legs)
    try:
        ledger = []
        for now in _session_minute_closes(day, max_ticks=max_ticks):
            ledger.extend(step(now=now, legs=legs, paths=paths, fetch=False))
        return ledger
    finally:
        if own_scratch:
            shutil.rmtree(paths["home"], ignore_errors=True)


# ── NT-vs-QQQ comparison (diagnostic only — no assertion) ────────────────────────────────
def nt_comparison(day, fills_path=None):
    """Side-by-side NinjaTrader fills vs this session's cloud_signal ledger for `day`.
    Diagnostic only: prints how far QQQ-bar signals diverge from the NQ-bar signals
    NinjaTrader actually took. Returns the row list (also used by --replay's table)."""
    from api import nt_sync
    fills_path = fills_path or nt_sync.DEFAULT_FILLS
    d = market_calendar._coerce_date(day)
    day_str = str(d)
    fills = nt_sync.parse_fills(fills_path)
    trades = nt_sync.build_trades(fills)
    nt_rows = [t for t in trades if t["date"] == day_str]
    return nt_rows


def _fmt_ledger_table(events):
    lines = []
    header = f"{'leg':<14}{'event':<7}{'side':<7}{'ref_time':<30}{'ref_price':>10}{'shares':>8}"
    lines.append(header)
    lines.append("-" * len(header))
    for e in events:
        lines.append(f"{e['leg']:<14}{e['event']:<7}{e['side']:<7}{str(e['ref_time']):<30}"
                     f"{e['ref_price']:>10}{e['shares']:>8}")
    return "\n".join(lines)


def _fmt_nt_comparison_table(events, nt_rows):
    lines = []
    header = (f"{'leg/tag':<16}{'source':<8}{'event':<7}{'time (ET)':<20}{'price':>10}")
    lines.append(header)
    lines.append("-" * len(header))
    for e in events:
        lines.append(f"{e['leg']:<16}{'QQQ':<8}{e['event']:<7}{str(e['ref_time']):<20}{e['ref_price']:>10}")
    for t in nt_rows:
        lines.append(f"{t.get('signal') or '(untagged)':<16}{'NT':<8}{'ENTRY':<7}"
                     f"{t['date']+' '+t['entryTime']:<20}{t['entry']:>10}")
        if t.get("exitTime"):
            lines.append(f"{t.get('signal') or '(untagged)':<16}{'NT':<8}{'EXIT':<7}"
                         f"{t['date']+' '+t['exitTime']:<20}{t['exit']:>10}")
    if not nt_rows:
        lines.append("(no NinjaTrader fills tagged for this session)")
    return "\n".join(lines)


# ── Heartbeat ───────────────────────────────────────────────────────────────────────────
def _write_heartbeat(paths, ok=True, note="", cache_write_failed=False):
    """`cache_write_failed` (2026-09-14): set by a caller that saw step()'s `warnings`
    dict carry it -- the on-disk bar cache rename failed even after retries, but the
    step still ran off the freshly fetched bars in memory (see step()'s docstring). It
    is recorded here (only when True, keeping the common heartbeat's shape unchanged)
    as a visible warning alongside ok=True -- never as a reason to flip ok to False,
    which is exactly the behaviour that used to make api/qqq_exec.py's engine-mode
    feed check block new entries over a transient disk/lock hiccup instead of a real
    outage.

    The rename retries the same transient-lock budget as every other writer here
    (qp._replace_with_retry): api/qqq_exec.py's `_check_feed_engine` opens this exact
    file every tick, so a reader can hold it for the same few milliseconds the OHLC
    cache readers do. On final failure this raises (see _write_state for why a writer
    in this module treats an exhausted retry as fatal rather than silently moving on)
    -- callers already wrap their heartbeat writes in a try/except for exactly this."""
    os.makedirs(paths["state_dir"], exist_ok=True)
    hb = {"ts": _dt.datetime.now(tz=_zi(TZ)).isoformat(), "ok": ok, "note": note}
    if cache_write_failed:
        hb["cache_write_failed"] = True
    tmp = paths["heartbeat_path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hb, f, indent=2)
    if not qp._replace_with_retry(tmp, paths["heartbeat_path"], log=print,
                                  what="[cloud-signal] heartbeat.json"):
        raise OSError(f"cloud_signal: could not replace {paths['heartbeat_path']} after retries")


# ── CLI ─────────────────────────────────────────────────────────────────────────────────
# The runner thread stamps its heartbeat every 30s in session and every 60s outside it, so
# three of the slow beats without one is the least that can mean "no live writer".
LIVE_WRITER_FRESH_SEC = 180.0


def _live_writer_age_sec(paths):
    """Seconds since a live writer (the runner thread, --loop, --once) last stamped the
    heartbeat under `paths`; None when there is no heartbeat file at all. A heartbeat that
    exists but cannot be read reads as 0.0 -- "can't tell" must refuse a live write, not
    wave it through."""
    hb = paths["heartbeat_path"]
    if not os.path.exists(hb):
        return None
    try:
        with open(hb, encoding="utf-8") as f:
            ts = _dt.datetime.fromisoformat(str(json.load(f).get("ts")))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_zi(TZ))
        return (_dt.datetime.now(tz=_zi(TZ)) - ts).total_seconds()
    except Exception:
        return 0.0


def cmd_replay(day, live_paths=False):
    """--replay. Isolated by default: the session replays in an isolated_paths() copy that
    is kept and named on screen, so its state.json/signals.csv can be read afterwards,
    and the live ledger is never opened for writing.

    --live-paths is the explicit opt-in to replay INTO DEFAULT_PATHS, and it is refused
    while a live writer's heartbeat is fresh: the runner thread rewrites state.json every
    30s (two writers lose each other's records and re-emit), and api/qqq_exec.py acts on
    any new ENTRY/EXIT row whose emitted_at looks recent -- which every replay row's does.
    Stop the thread first, and mind the adapter. Returns a process exit code."""
    if live_paths:
        paths = DEFAULT_PATHS
        age = _live_writer_age_sec(paths)
        if age is not None and age < LIVE_WRITER_FRESH_SEC:
            print(f"cloud_signal replay {day}: REFUSED --live-paths -- a live writer stamped "
                  f"{paths['heartbeat_path']} {age:.0f}s ago. Stop the runner's cloud_signal "
                  f"thread (or --loop) first, or drop --live-paths to replay in isolation.")
            return 2
        print(f"cloud_signal replay {day}: --live-paths -- writing into the LIVE ledger and "
              f"state in {paths['state_dir']}")
    else:
        paths = isolated_paths()
        print(f"cloud_signal replay {day}: isolated copy in {paths['home']} "
              f"(live ledger untouched; delete the folder when done)")
    events = replay(day, paths=paths)
    print(f"cloud_signal replay {day} — {len(events)} new event(s) this call")
    print(_fmt_ledger_table(events))
    nt_rows = nt_comparison(day)
    print(f"\nNT (NinjaTrader NQ) vs QQQ cloud_signal — session {day}")
    print(_fmt_nt_comparison_table(events, nt_rows))
    return 0


def cmd_once():
    paths = DEFAULT_PATHS
    warnings = {}
    events = step(fetch=True, paths=paths, warnings=warnings)
    cache_failed = bool(warnings.get("cache_write_failed"))
    note = f"{len(events)} event(s)" + (" (cache_write_failed)" if cache_failed else "")
    _write_heartbeat(paths, ok=True, note=note, cache_write_failed=cache_failed)
    print(f"cloud_signal --once: {len(events)} new event(s)")
    print(_fmt_ledger_table(events))


THREAD_STEP_SEC = 30.0   # see cloud_signal_thread


def cloud_signal_thread(stop=None, log=print):
    """Runner-hosted PARALLEL RUN. Steps the signal engine through every session so the
    QQQ-bar signals accumulate beside the NinjaTrader-mirrored shadow book, which is the
    evidence the "drop NinjaTrader" decision needs: two ledgers over the same sessions,
    one derived from NQ futures fills and one from QQQ bars alone.

    Signals only -- this thread cannot place an order, and nothing downstream of
    signals.csv exists. It never raises into the runner and never blocks its main loop.

    30s rather than cmd_loop's 20s: every step may hit yfinance once per timeframe before
    the cheap "no new bar closed" short-circuit in step() can skip the engine, and a 1m leg
    cannot gain a bar faster than once a minute anyway. Two fetches a minute per timeframe
    is enough to see a bar the moment it closes without leaning on a free endpoint."""
    log("[cloud-signal] parallel run: ON (signals only, no order path)")
    # Bring the live ledger's header up to SIGNAL_COLS at boot rather than at the first
    # emitted event, which is always mid-session with api/qqq_exec.py reading the file (a
    # runner restart after the close then upgrades it while nobody is consuming). Atomic
    # either way -- see _migrate_signals_header.
    try:
        if os.path.exists(DEFAULT_PATHS["signals_path"]):
            _migrate_signals_header(DEFAULT_PATHS["signals_path"], SIGNAL_COLS)
    except Exception as e:
        log(f"[cloud-signal] ledger header check failed (next append retries): {type(e).__name__}: {e}")
    while stop is None or not stop.is_set():
        in_session = False           # set before the try so a throw still picks a sleep
        try:
            now_et = _dt.datetime.now(tz=_zi(TZ))
            in_session = (market_calendar.is_session(now_et.date())
                         and RTH_OPEN <= now_et.time() <= RTH_CLOSE)
            if in_session:
                warnings = {}
                events = step(now=now_et, fetch=True, paths=DEFAULT_PATHS, warnings=warnings)
                cache_failed = bool(warnings.get("cache_write_failed"))
                note = f"{len(events)} event(s)" + (" (cache_write_failed)" if cache_failed else "")
                _write_heartbeat(DEFAULT_PATHS, ok=True, note=note, cache_write_failed=cache_failed)
                for e in events:
                    log(f"[cloud-signal] {e['event']} {e['leg']} {e.get('side','')} "
                        f"@ {e.get('ref_price','')} ({e.get('ref_time','')}) {e.get('reason','')}")
            else:
                _write_heartbeat(DEFAULT_PATHS, ok=True, note="outside session hours")
        except Exception as e:                            # a bad step must never kill the run
            try:
                _write_heartbeat(DEFAULT_PATHS, ok=False, note=f"{type(e).__name__}: {e}")
            except Exception:
                pass
            log(f"[cloud-signal] step failed: {type(e).__name__}: {e}")
        _time.sleep(THREAD_STEP_SEC if in_session else 60.0)


def cmd_loop():
    paths = DEFAULT_PATHS
    print("cloud_signal --loop: stepping every 20s during session hours (Ctrl+C to stop)")
    while True:
        now_et = _dt.datetime.now(tz=_zi(TZ))
        in_session = (market_calendar.is_session(now_et.date())
                     and RTH_OPEN <= now_et.time() <= RTH_CLOSE)
        if in_session:
            try:
                warnings = {}
                events = step(now=now_et, fetch=True, paths=paths, warnings=warnings)
                cache_failed = bool(warnings.get("cache_write_failed"))
                note = f"{len(events)} event(s)" + (" (cache_write_failed)" if cache_failed else "")
                _write_heartbeat(paths, ok=True, note=note, cache_write_failed=cache_failed)
                if events:
                    print(_fmt_ledger_table(events))
            except Exception as e:                       # never let the loop die silently
                _write_heartbeat(paths, ok=False, note=str(e))
                print(f"  [warn] step() failed: {e}", file=sys.stderr)
            _time.sleep(20)
        else:
            _write_heartbeat(paths, ok=True, note="outside session hours")
            _time.sleep(60)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", metavar="YYYY-MM-DD",
                    help="replay one cached session in an isolated copy")
    ap.add_argument("--live-paths", action="store_true",
                    help="with --replay: write INTO the live ledger/state instead of a copy "
                         "(refused while a live writer's heartbeat is fresh)")
    ap.add_argument("--once", action="store_true", help="one live step() and exit")
    ap.add_argument("--loop", action="store_true", help="step() every 20s during session hours")
    args = ap.parse_args(argv)
    if args.live_paths and not args.replay:
        ap.error("--live-paths only applies to --replay")
    if args.replay:
        rc = cmd_replay(args.replay, live_paths=args.live_paths)
        if rc:
            sys.exit(rc)
    elif args.once:
        cmd_once()
    elif args.loop:
        cmd_loop()
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
