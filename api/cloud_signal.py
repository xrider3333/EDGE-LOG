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
this file's existence.

THE THREE CROWN LEGS (as of 2026-09-08, api/paper.py PAPER_LEGS):
  ORB_R6      run #314, ORB_3_6_R6.py, api.paper.ORB_314, 5m RTH, no gate.
  NOISE_SBS_V90  run #243, NOISE_1_0.py, api.paper.NOISE_243_SBS_V90, 5m RTH, no gate.
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
                                                     the NT-vs-QQQ comparison table
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
import sys
import time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.engine import run_backtest as engine_run_backtest          # noqa: E402
from api import market_calendar                                             # noqa: E402
from api.paper import ORB_314, ENGUQ_335, NOISE_243_SBS_V90                 # noqa: E402
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


DEFAULT_PATHS = _paths()

# ── Crown legs (current as of 2026-09-08 — see api/paper.py PAPER_LEGS) ─────────────────
CROWN_LEGS = {
    "ORB_R6": {
        "strategy": "ORB_3_6_R6.py",
        "timeframe": "5m",
        "params": dict(ORB_314),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
    },
    "NOISE_SBS_V90": {
        "strategy": "NOISE_1_0.py",
        "timeframe": "5m",
        "params": dict(NOISE_243_SBS_V90),
        "warmup_sessions": DEFAULT_WARMUP_SESSIONS,
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
    """Pull fresh bars, merge into the cache under EDGELOG_HOME, and return the merged
    epoch-schema frame. Network call — never invoked from --replay or from tests, only
    from a live step().

    Webull first, yfinance as the fallback. Both are consolidated US equity prints for
    the same regular session, so they agree to the cent in normal conditions; the cache
    can therefore hold rows from either without a seam. If that ever stops being true it
    shows up as a price jump exactly at a source change, so the fallback logs when it
    fires rather than switching silently."""
    import pandas as pd
    paths = paths or DEFAULT_PATHS
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    path = _cache_path(timeframe, paths)
    old = load_cached_bars(timeframe, paths)
    if old is None:
        old = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    fresh = _fetch_webull(timeframe, log=log)
    if fresh is None or not len(fresh):
        log(f"[cloud-signal] falling back to yfinance for {timeframe} bars")
        fresh_df = qp._fetch_yf(timeframe)
        fresh = qp._to_epoch_frame(fresh_df)
    merged = pd.concat([old, fresh], ignore_index=True)
    if len(merged):
        merged = merged.drop_duplicates("time", keep="last").sort_values("time")
    # ATOMIC (2026-09-09): to_csv() TRUNCATES then writes, so a reader that opens the file
    # mid-write gets an empty or half-written cache. That is not hypothetical -- this thread
    # rewrites the cache every 30s and it caught the test suite red-handed, which is exactly
    # what a strategy run or a manual replay would have hit instead. Write beside it and
    # rename: os.replace is atomic on Windows and POSIX, so a reader sees the old file or
    # the new one, never a torn one.
    tmp = path + ".tmp"
    merged.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return merged


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
    to a calendar-day window first (generous: warmup_sessions+5 calendar days, to
    absorb weekends/holidays before the exact session-count trim below) bounds that
    cost to roughly the window size regardless of total cache depth."""
    if all_epoch_df is None or not len(all_epoch_df):
        return None
    cutoff = _closed_cutoff_epoch(now, timeframe)
    lower_bound = cutoff - (int(warmup_sessions) + 5) * 86400
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
def run_leg_trades(cfg, arrays):
    """Runs the plugin (or a stub module override) via the shared engine wrapper and
    converts the raw (entry_bar, exit_bar, pnl_pts, side, entry_px) tuples into
    canonical dicts keyed by wall-clock timestamps (not bar indices — those are only
    valid for the exact arrays slice they came from, and the rolling window's start
    shifts every call)."""
    res = engine_run_backtest(cfg["strategy"], arrays=arrays, params=cfg["params"],
                              cost_pts=0.0, return_trades=True)
    if not res or not res.get("trades"):
        return []
    idx = arrays["index"]
    n_bars = len(arrays["close"])
    out = []
    for (entry_bar, exit_bar, pnl_pts, side, entry_px) in sorted(res["trades"], key=lambda t: t[0]):
        entry_bar = int(entry_bar); exit_bar = int(exit_bar)
        entry_px = float(entry_px)
        exit_px = entry_px + pnl_pts * side
        still_open = exit_bar >= n_bars - 1
        shares = int(math.floor(NOTIONAL_PER_LEG / entry_px)) if entry_px > 0 else 0
        out.append({
            "side": "long" if side > 0 else "short",
            "entry_time": idx[entry_bar].isoformat(),
            "entry_px": round(entry_px, 4),
            "shares": max(shares, 0),
            "exit_time": None if still_open else idx[min(exit_bar, n_bars - 1)].isoformat(),
            "exit_px": None if still_open else round(exit_px, 4),
            "still_open": still_open,
        })
    return out


def _entry_key(leg, trade):
    return f"{leg}|{trade['entry_time']}|{trade['side']}|{trade['entry_px']:.4f}"


# ── State I/O ───────────────────────────────────────────────────────────────────────────
def _load_state(paths):
    if not os.path.exists(paths["state_path"]):
        return {"legs": {}}
    with open(paths["state_path"], encoding="utf-8") as f:
        return json.load(f)


def _write_state(state, paths):
    os.makedirs(paths["state_dir"], exist_ok=True)
    tmp = paths["state_path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, paths["state_path"])


SIGNAL_COLS = ["emitted_at", "leg", "event", "side", "ref_time", "ref_price", "shares", "reason"]


def _append_signals(events, paths):
    if not events:
        return
    os.makedirs(paths["state_dir"], exist_ok=True)
    new_file = not os.path.exists(paths["signals_path"])
    import csv
    with open(paths["signals_path"], "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SIGNAL_COLS)
        if new_file:
            w.writeheader()
        for e in events:
            w.writerow({k: e.get(k, "") for k in SIGNAL_COLS})


# ── The core entry point ───────────────────────────────────────────────────────────────
def step(now=None, legs=None, paths=None, fetch=True):
    """One signal-engine tick. For each leg: load cached bars (optionally refreshed
    from yfinance first), restrict to bars CLOSED as of `now`, run the engine over the
    rolling warm-up window, and diff the resulting trade list against what was last
    persisted for that leg. Returns the list of NEW events emitted THIS call (empty on
    a rerun at the same `now` — idempotent by construction: every event is keyed by
    (leg, entry timestamp, side, entry price) and a key already recorded in state.json
    is never re-emitted).

    `legs`: defaults to CROWN_LEGS; pass a different dict (e.g. with a stub strategy
    module as cfg["strategy"]) to test the diff/idempotency machinery in isolation.
    `fetch`: pull fresh bars over the network first. --replay always passes False (it
    must stay fully offline and deterministic); --once/--loop pass True.
    """
    legs = legs if legs is not None else CROWN_LEGS
    paths = paths or DEFAULT_PATHS
    now = now or _dt.datetime.now(tz=_zi(TZ))
    if now.tzinfo is None:
        now = now.replace(tzinfo=_zi(TZ))

    state = _load_state(paths)
    state.setdefault("legs", {})
    all_events = []

    tf_cache = {}
    for key, cfg in legs.items():
        tf = cfg["timeframe"]
        if fetch and tf not in tf_cache:
            tf_cache[tf] = fetch_and_merge(tf, paths)
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
        if leg_state.get("last_bar_epoch") == latest_bar_epoch:
            continue
        leg_state["last_bar_epoch"] = latest_bar_epoch

        arrays = closed_arrays(epoch_df, now, tf, cfg.get("warmup_sessions", DEFAULT_WARMUP_SESSIONS))
        if arrays is None:
            continue

        trades = run_leg_trades(cfg, arrays)
        events = _diff_leg(key, trades, leg_state, now)
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


def _diff_leg(leg_key, trades, leg_state, now):
    """Mutates leg_state['trades'] (entry_key -> record) in place; returns the list of
    NEW ENTRY/EXIT event dicts this call discovered.

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
    """
    events = []
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
            "ref_price": "", "shares": "",
            "reason": (f"cold start: absorbed {len(trades)} historical trade(s) without "
                       f"emitting; open_at_seed={open_at_seed}"),
        })
        return events
    today = now.date().isoformat()
    for t in trades:
        key = _entry_key(leg_key, t)
        rec = recorded.get(key)
        if rec is None:
            fresh = str(t["entry_time"])[:10] == today
            recorded[key] = {"entry_time": t["entry_time"], "side": t["side"],
                             "entry_px": t["entry_px"], "shares": t["shares"],
                             "exit_emitted": not fresh, "exit_time": None,
                             "exit_px": None, "stale": not fresh}
            if not fresh:
                leg_state["stale_skipped"] = int(leg_state.get("stale_skipped", 0)) + 1
                continue
            events.append({
                "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
                "leg": leg_key, "event": "ENTRY", "side": t["side"],
                "ref_time": t["entry_time"], "ref_price": t["entry_px"],
                "shares": t["shares"], "reason": "",
            })
            rec = recorded[key]
        if (not t["still_open"]) and (not rec["exit_emitted"]):
            rec["exit_emitted"] = True
            rec["exit_time"] = t["exit_time"]
            rec["exit_px"] = t["exit_px"]
            events.append({
                "emitted_at": _dt.datetime.now(tz=_zi(TZ)).isoformat(),
                "leg": leg_key, "event": "EXIT", "side": t["side"],
                "ref_time": t["exit_time"], "ref_price": t["exit_px"],
                "shares": t["shares"], "reason": "strategy_exit",
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


def replay(day, legs=None, paths=None, warmup_sessions=None, max_ticks=None):
    """Replay one cached session bar-by-bar (1-minute granularity), calling step() at
    each closed-bar boundary with fetch=False (fully offline — only ever reads the
    on-disk cache). Returns the full ledger of events emitted (across however many
    times replay() has been called for this day against this state store — call it
    twice to see the idempotency guarantee: the second call's return is empty).

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
    ledger = []
    for now in _session_minute_closes(day, max_ticks=max_ticks):
        ledger.extend(step(now=now, legs=legs, paths=paths, fetch=False))
    return ledger


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
def _write_heartbeat(paths, ok=True, note=""):
    os.makedirs(paths["state_dir"], exist_ok=True)
    hb = {"ts": _dt.datetime.now(tz=_zi(TZ)).isoformat(), "ok": ok, "note": note}
    tmp = paths["heartbeat_path"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hb, f, indent=2)
    os.replace(tmp, paths["heartbeat_path"])


# ── CLI ─────────────────────────────────────────────────────────────────────────────────
def cmd_replay(day):
    events = replay(day)
    print(f"cloud_signal replay {day} — {len(events)} new event(s) this call")
    print(_fmt_ledger_table(events))
    nt_rows = nt_comparison(day)
    print(f"\nNT (NinjaTrader NQ) vs QQQ cloud_signal — session {day}")
    print(_fmt_nt_comparison_table(events, nt_rows))


def cmd_once():
    paths = DEFAULT_PATHS
    events = step(fetch=True, paths=paths)
    _write_heartbeat(paths, ok=True, note=f"{len(events)} event(s)")
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
    while stop is None or not stop.is_set():
        in_session = False           # set before the try so a throw still picks a sleep
        try:
            now_et = _dt.datetime.now(tz=_zi(TZ))
            in_session = (market_calendar.is_session(now_et.date())
                         and RTH_OPEN <= now_et.time() <= RTH_CLOSE)
            if in_session:
                events = step(now=now_et, fetch=True, paths=DEFAULT_PATHS)
                _write_heartbeat(DEFAULT_PATHS, ok=True, note=f"{len(events)} event(s)")
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
                events = step(now=now_et, fetch=True, paths=paths)
                _write_heartbeat(paths, ok=True, note=f"{len(events)} event(s)")
                if events:
                    print(_fmt_ledger_table(events))
            except Exception as e:                       # never let the loop die silently
                _write_heartbeat(paths, ok=False, note=str(e))
                print(f"  [warn] step() failed: {e}", file=sys.stderr)
            _time.sleep(20)
        else:
            _write_heartbeat(paths, ok=True, note="outside session hours")
            _time.sleep(60)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", metavar="YYYY-MM-DD", help="replay one cached session")
    ap.add_argument("--once", action="store_true", help="one live step() and exit")
    ap.add_argument("--loop", action="store_true", help="step() every 20s during session hours")
    args = ap.parse_args()
    if args.replay:
        cmd_replay(args.replay)
    elif args.once:
        cmd_once()
    elif args.loop:
        cmd_loop()
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
