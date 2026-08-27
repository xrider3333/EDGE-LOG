"""LIVE ML gate service — the bouncer NinjaTrader asks before entering a trade.

WHY (owner, 2026-08-16): the validated ML gates existed only inside Python backtests
(the paper legs). NinjaTrader traded RAW because the random-forest model cannot be
retyped into NinjaScript (100 trees). This closes the gap the way the owner approved:
NinjaTrader keeps placing and managing every order exactly as it does today, but just
before entering it makes ONE local HTTP call here -- "should I take this trade, and how
big?" -- and acts on the answer.

DESIGN RULES, each load-bearing:

  * FAIL-OPEN, both sides. If this service is down, slow, or errors, the answer is
    "take it, normal size" -- NinjaTrader also enforces that with its own timeout.
    A broken bouncer must degrade to the RAW strategy (which is validated on its own),
    never to silently skipped trades: on the board "no trades" and "gate refused
    everything" look identical, and only one of them is a market observation.

  * OWN PROCESS, not a runner thread. The runner regularly saturates every core for
    hours with optimizes; a gate thread inside it would miss NinjaTrader's deadline
    exactly then, and each miss silently un-gates one live entry. This process does
    nothing else, so its latency does not depend on what research is running.

  * SAME MODEL AS THE FORWARD TEST. The nightly artifact fits the same model family,
    features, threshold and frozen size divisor as the paper leg (read from
    api/paper.py's leg configs -- one source of truth). Training set = every completed
    trade of the leg's own backtest through the latest data, which is exactly what the
    walk-forward gate would know at this moment (its refit cadence is every 25 trades,
    so "as of last night" and "as of now" are the same model in practice).

  * ORDERS STAY IN NINJATRADER. This service never places, sizes, or cancels anything.
    All existing rails (kill switch, circuit breaker, the hard-locked real account)
    are untouched because the order path is untouched.

  * THE CALLER SAYS WHICH BAR IT IS ACTING ON. NinjaTrader appends its own last closed
    bar to the request; more than one bar step from ours and we refuse to score and fail
    open loudly (see the bar interlock below). For three days every NOISE and ORB
    decision was scored on ENGU-Q's overnight 1-minute bars and nobody could tell,
    because the two sides of the conversation never compared notes.

Endpoints (127.0.0.1:8392, GET, JSON):
    /gate/health                    service + per-leg artifact status, the git SHA of
                                    the code THIS PROCESS loaded, and per leg when it
                                    last built and last answered
    /gate/check?leg=NOISE_H_RF      the live decision: {take, size, prob, max_contracts, ...}
    /gate/check?leg=X&bar=<ISO8601> the same, with the bar interlock armed. Optional --
                                    a NinjaScript that does not send it still works.

Run:  python -m api.gate_live --serve          (the always-on service)
      python -m api.gate_live --build          (rebuild all artifacts now)
      python -m api.gate_live --build-leg NOISE_H_RF
"""
import argparse
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime

import numpy as np
import pandas as pd

ARTIFACT_DIR = r"C:\EdgeLog\gate_models"
PORT = 8392
LOG_PATH = r"C:\EdgeLog\gate_live.log"
RAILS_PATH = r"C:\EdgeLog\bridge.json"

# Which checkout is this, and since when. A long-lived process caches every module it
# imported, so "the fix is pushed" and "the running bouncer has the fix" are two different
# claims -- the bar-cache defect below sat in a running process for days. Health answers
# both without anyone having to guess from a restart time.
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROC_STARTED = datetime.now().isoformat(timespec="seconds")
_git_sha_memo = []                # one-slot memo; [] = never looked up

# How much history the live feature window needs. Features reach back at most ~100 bars
# (slow ATR) plus one prior session's levels; the slow ATR is an exponential average whose
# memory of anything past ~300 bars is below one part in a billion, so 45 calendar days of
# 5-minute bars reproduces the full-history feature values at the last row to numerical
# noise. Verified by comparison in the smoke test below.
_LIVE_WINDOW_DAYS = 45

_lock = threading.Lock()          # one live-decision at a time (state is shared)
_artifacts = {}                   # leg -> loaded artifact dict (with file mtime)
# ONE CACHE PER BAR SERIES, NOT ONE CACHE (fixed 2026-08-26).
# This was a single dict keyed only on the calendar day. The gated legs do NOT share a
# bar series -- ENGU-Q runs NQ 1-minute on the 24-hour tape, every NOISE and ORB leg runs
# NQ 5-minute regular hours -- but _refresh_live_arrays only consulted `leg` on the FIRST
# call of the day, so whichever leg happened to warm first owned the array for all of them.
# serve() primes with _gated_legs()[0], which is ENGUQ_ER_H, so in practice every NOISE and
# ORB decision of the day was scored on ENGU-Q's overnight 1-minute bars: 20,381 bars at a
# 1-minute step instead of 2,573 at 5 minutes, with a last-closed-bar of 22:15 ET on a leg
# whose session ends at 16:00. 307 such decisions are already in gate_live.log across
# 08-17, 08-24 and 08-26, each one identifiable by a bar stamp outside regular hours.
# Keyed on (instrument, timeframe, session) now -- the three things that pick the master --
# so a leg can only ever be handed its own series.
_live_caches = {}                 # (instrument, timeframe, session) -> cache dict

# What this PROCESS has done for each leg. Not persisted anywhere on purpose: the question
# it answers is "what has the currently-running service done", which is exactly the
# question a restart resets.
_leg_state = {}                   # leg -> {last_build_ok, last_build_ts, last_build_error,
                                  #         last_decide_ts, last_decide_source}


def _state_for(key):
    s = _leg_state.get(key)
    if s is None:
        s = {"last_build_ok": None, "last_build_ts": None, "last_build_error": None,
             "last_decide_ts": None, "last_decide_source": None}
        _leg_state[key] = s
    return s


def _git_sha():
    """The commit this process's code came from, or None. Never raises.

    Resolved once and memoized -- the answer cannot change without restarting the process,
    which is the whole point of asking. None (a missing git, a copied folder, a slow disk)
    is reported as null rather than as a guess."""
    if not _git_sha_memo:
        sha = None
        try:
            r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO_DIR,
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                sha = (r.stdout or "").strip() or None
        except Exception:
            sha = None
        _git_sha_memo.append(sha)
    return _git_sha_memo[0]


def _series_key(leg):
    return (str(leg.get("instrument")), str(leg.get("timeframe")),
            str(leg.get("session", "rth")))


def _cache_for(leg):
    k = _series_key(leg)
    c = _live_caches.get(k)
    if c is None:
        c = {"arrays": None, "loaded_day": None, "tick_offset": 0, "tick_df": None,
             "tick_path": None}
        _live_caches[k] = c
    return c


def _log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _gated_legs():
    """The paper legs that carry a gate -- the single source of truth for what to serve."""
    from api import paper
    return [l for l in paper.PAPER_LEGS if l.get("gate")]


# ── nightly artifact ──────────────────────────────────────────────────────────────
def build_artifact(leg):
    """Fit one leg's artifact, recording the outcome where /gate/health can see it.

    A failed nightly rebuild used to leave no trace except a line in a log nobody reads,
    while the service went on serving yesterday's artifact and reporting "ready" -- true,
    but not the truth anyone wanted. The outcome is recorded whichever way it goes, and
    the exception still propagates so every existing caller behaves as before."""
    st = _state_for(leg["key"])
    try:
        art = _build_artifact(leg)
    except Exception as e:
        st.update({"last_build_ok": False,
                   "last_build_ts": datetime.now().isoformat(timespec="seconds"),
                   "last_build_error": f"{type(e).__name__}: {e}"})
        raise
    st.update({"last_build_ok": True,
               "last_build_ts": datetime.now().isoformat(timespec="seconds"),
               "last_build_error": None})
    return art


def _build_artifact(leg):
    """Fit the as-of-now gate model for one leg and save it to disk.

    Mirrors the paper leg exactly: same base backtest (master + today's fresh bars),
    same causal features, same model family/seed. The fit itself takes seconds -- the
    minutes-long part of the nightly paper run is walking the model through history
    trade by trade, which a live decision never needs.
    """
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from augur_engine.ml_gate import entry_features_causal, _make_model
    from api import paper
    import joblib

    key = leg["key"]
    t0 = time.time()
    master = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"))
    if master is None:
        raise RuntimeError(f"no master for {key}")
    arrays = load_master_arrays(master, date_from=leg.get("history_from"), date_to=None)

    # today's fresh bars, same as the paper run appends
    ticks, _ = paper._load_fresh_ticks()
    if ticks is not None:
        tf_min = 5 if str(leg["timeframe"]).lower().startswith("5") else 1
        bars = paper._resample(ticks, tf_min)
        bars, bars_et = paper._filter_rth(bars)
        last = arrays["index"][-1] if len(arrays["index"]) else None
        if last is not None and len(bars):
            bars = bars[(bars_et > last).values].reset_index(drop=True)
        if len(bars):
            arrays, _n = paper._append_fresh(arrays, bars)

    res = run_backtest(leg["strategy"], arrays=arrays, params=leg["params"],
                       cost_pts=leg.get("cost_pts", 0.0), return_trades=True)
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in (res.get("trades") or [])],
               key=lambda t: t[0])
    if len(T) < 100:
        raise RuntimeError(f"{key}: only {len(T)} trades -- refusing to fit")

    F, names = entry_features_causal(arrays)
    E = np.array([t[0] for t in T])
    P = np.array([t[2] for t in T], float)
    y = (P > 0).astype(int)
    X = F[np.clip(E, 0, len(F) - 1)]

    g = leg["gate"]
    mdl = _make_model(g["model"], int(g.get("seed", 42)))
    mdl.fit(X, y, clf__sample_weight=np.abs(P) + 1e-9)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    path = os.path.join(ARTIFACT_DIR, f"{key}.pkl")
    mode = str(g.get("mode", "cut")).lower()
    # TILT takes every trade, so a threshold is meaningless for it; 0.0 records "nothing
    # is ever refused" rather than inventing a cut-off the paper leg does not apply.
    art = {"leg": key, "model": g["model"], "mode": g.get("mode", "cut"),
           "threshold": (0.0 if mode == "tilt" else float(g["threshold"])),
           "scheme": (str(g.get("scheme") or "tier") if mode == "tilt" else None),
           "size_norm": float(g.get("size_norm") or 1.0),
           "recycle_factor": float(g.get("recycle_factor") or 1.0),
           "feature_names": list(names),
           "strategy": leg["strategy"], "params": dict(leg["params"]),
           "n_trades_trained": len(T),
           "trained_through": str(pd.Timestamp(arrays["index"][-1])),
           "built_at": datetime.now().isoformat(timespec="seconds"),
           "pipe": mdl}
    joblib.dump(art, path)
    _log(f"artifact {key}: fit on {len(T)} trades through {art['trained_through']} "
         f"({time.time()-t0:.1f}s) -> {path}")
    return art


def build_all():
    out = {}
    for leg in _gated_legs():
        try:
            out[leg["key"]] = build_artifact(leg)
        except Exception as e:
            _log(f"artifact {leg['key']} FAILED: {type(e).__name__}: {e}")
    return out


def _load_artifact(key):
    """Load (or reload, if the nightly rebuild replaced it) one leg's artifact."""
    import joblib
    path = os.path.join(ARTIFACT_DIR, f"{key}.pkl")
    if not os.path.exists(path):
        # EVICT, don't merely answer None (fixed 2026-08-26). The decision path fails open
        # either way, but /gate/health and the status page read _artifacts directly, so a
        # deleted or renamed artifact went on reporting "ready" off the copy still in
        # memory: the one screen whose entire job is saying whether the bouncer is armed
        # was the one screen that could not say it had been disarmed.
        if _artifacts.pop(key, None) is not None:
            _log(f"artifact {key} GONE from disk - evicted (health now says NOT LOADED)")
        return None
    mtime = os.path.getmtime(path)
    cur = _artifacts.get(key)
    if cur and cur.get("_mtime") == mtime:
        return cur
    art = joblib.load(path)
    art["_mtime"] = mtime
    _artifacts[key] = art
    _log(f"loaded artifact {key} (trained through {art.get('trained_through')})")
    return art


# ── live bars: cached recent master window + incrementally-read fresh ticks ───────
def _refresh_live_arrays(leg):
    """A 5m bar series ending at the most recent CLOSED bar, cheap enough to call per
    request: the master window is cached per day, and the 10s capture file is read
    incrementally (only bytes appended since the last request)."""
    from augur_engine.data import find_master, load_master_arrays
    from api import paper

    _live_cache = _cache_for(leg)
    today = datetime.now().strftime("%Y-%m-%d")
    if _live_cache["loaded_day"] != today or _live_cache["arrays"] is None:
        master = find_master(leg["instrument"], leg["timeframe"], leg.get("session", "rth"))
        if master is None:
            raise RuntimeError("no master")
        date_from = (pd.Timestamp(today) - pd.Timedelta(days=_LIVE_WINDOW_DAYS)).strftime("%Y-%m-%d")
        _live_cache["arrays"] = load_master_arrays(master, date_from=date_from, date_to=None)
        _live_cache["loaded_day"] = today
        _live_cache["tick_offset"] = 0
        _live_cache["tick_df"] = None
        _live_cache["tick_path"] = paper._ticks_path()
        _log(f"live window reloaded for {'/'.join(_series_key(leg))} "
             f"({date_from} .. master end, {len(_live_cache['arrays']['index'])} bars)")

    # incremental tick read -- append only the new bytes
    path = paper._ticks_path()
    if path != _live_cache["tick_path"]:
        _live_cache["tick_offset"] = 0
        _live_cache["tick_df"] = None
        _live_cache["tick_path"] = path
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if size and size > _live_cache["tick_offset"]:
        import io
        with open(path, "rb") as f:
            if _live_cache["tick_offset"] == 0:
                raw = f.read()
            else:
                f.seek(_live_cache["tick_offset"])
                raw = f.read()
        _live_cache["tick_offset"] = size
        txt = raw.decode("utf-8", "replace")
        try:
            if _live_cache["tick_df"] is None:
                df = pd.read_csv(io.StringIO(txt))
            else:
                df = pd.read_csv(io.StringIO(txt), header=None,
                                 names=list(_live_cache["tick_df"].columns))
            df = df[["time", "open", "high", "low", "close", "volume"]].copy()
            df["time"] = pd.to_numeric(df["time"], errors="coerce")
            df = df.dropna(subset=["time"])
            df["time"] = df["time"].astype("int64")
            if _live_cache["tick_df"] is None:
                _live_cache["tick_df"] = df
            else:
                _live_cache["tick_df"] = pd.concat([_live_cache["tick_df"], df],
                                                   ignore_index=True)
        except Exception as e:
            _log(f"tick parse: {type(e).__name__}: {e}")

    from api import paper as _p
    arrays = _live_cache["arrays"]
    ticks = _live_cache["tick_df"]
    if ticks is not None and len(ticks):
        tf_min = 5 if str(leg["timeframe"]).lower().startswith("5") else 1
        bars = _p._resample(ticks, tf_min)
        bars, bars_et = _p._filter_rth(bars)
        last = arrays["index"][-1] if len(arrays["index"]) else None
        if last is not None and len(bars):
            bars = bars[(bars_et > last).values].reset_index(drop=True)
        if len(bars):
            arrays, _n = _p._append_fresh(arrays, bars)
    return arrays


# ── recycle interlock ─────────────────────────────────────────────────────────────
# The NinjaTrader quantity the served `size` is multiplied by. Kept here so the service
# can reason in the same contracts the breaker counts.
# 3 since 2026-08-16: recycle multiplies size ~3.85x, so base 3 micros lands the live leg
# near one-contract exposure and keeps the untouched $1,500 daily-loss breaker meaning
# roughly what it always meant (~65 adverse points). See tools/nt_reconfig.py.
LIVE_QTY = int(os.environ.get("EDGELOG_LIVE_QTY", "3"))


def _rails():
    """(limit, error) -- the contract ceiling the human set in bridge.json, or (None, why).

    Read on every request and deliberately NOT cached: the bridge monitor re-reads the
    same file every 10 seconds, and _recycle_allowance below promises that raising the
    rails switches recycle on within one request. It is a 1 KB read against a ~60 ms
    decision. Never raises."""
    try:
        with open(RAILS_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return min(int(cfg.get("max_position_contracts") or 0),
                   int(cfg.get("max_qty") or 0)), None
    except Exception as e:
        return None, f"cannot read the risk rails ({type(e).__name__})"


def _max_contracts():
    """The hard contract ceiling this service authorises for ONE entry, right now.

    The NinjaScript used to clamp itself at `Qty * 3`, which at the live Qty=3 made every
    accepted trade exactly 9 micros no matter what the model said -- the size dial was
    dead. That 3x cap was never NinjaTrader's to apply. It belongs to the engine, it is
    ALREADY inside the `size` served below (min(w / size_norm, 3.0), applied BEFORE the
    recycle factor, same order as the backtest), and applying it a second time downstream
    only truncates the recycled sizes this service deliberately served.

    So this is a DIFFERENT limit, not a second copy of that one: the account rail the
    human set in bridge.json (max_position_contracts / max_qty), which is what the
    bridge's circuit breaker actually enforces -- and tripping it FLATTENS AND DISABLES
    every strategy on the account, ENGU-Q included. At LIVE_QTY=3 with rf=3.85 the largest
    size this service can serve is 3.0 * 3.85 = 11.55, i.e. 35 contracts, under the
    current rail of 40, so the clamp normally never binds. It binds when NinjaTrader runs
    a larger Qty than this service assumes, which is the one case nothing else catches.

    Account-level, not book-level: the gated legs share one NinjaTrader account, so this
    bounds a single entry rather than the sum of them. The bridge's own L5 position check
    is what covers the book.

    None means UNKNOWN -- the NinjaScript falls back to its own MaxContracts parameter.
    Never 0: a missing key in bridge.json would otherwise clamp every live order to zero
    contracts, quietly turning a fail-open service into a fail-closed one."""
    limit, _err = _rails()
    if limit is None or limit < 1:
        return None
    return int(limit)


# ── bar interlock ─────────────────────────────────────────────────────────────────
# WHY (2026-08-26): for three days every NOISE and ORB decision was scored on ENGU-Q's
# overnight 1-minute bars because the bar cache was keyed only on the calendar day. The
# probabilities that came back looked entirely ordinary. What let it run for three days is
# that NOTHING COMPARED NOTES -- NinjaTrader knew precisely which bar it was acting on and
# never said so, and this service never asked.
#
# Now it asks. More than one step apart and we refuse to score: fail-open, because a
# silent skip and a market with no signals look identical on the board, but LOUD in the
# log, because a stale or wrong-series score is a plausible number with nothing behind it
# and that is worse than no score at all. One step of tolerance because the two sides may
# stamp a bar at opposite ends of itself; a genuine series mix-up misses by hours.
_ET = "US/Eastern"


def _parse_nt_bar(s):
    """A caller's bar stamp -> Timestamp, or None if it is not one.

    Tolerant and non-raising by design: a caller that sends a stamp we cannot read must
    still get its trade decision. Unreadable is treated as "sent nothing", and the answer
    says so (bar_check=unparseable) so it shows up instead of passing for armed."""
    if s is None:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    # REPAIR A '+' THAT ARRIVED AS A SPACE, and do it BEFORE parsing rather than after.
    # A query string decodes '+' to a space, so an un-escaped UTC offset reaches us as
    # "...T13:35:00 00:00" -- and pandas does not reject that, it quietly returns
    # MIDNIGHT. A silently wrong bar reads as a mismatch on every single request, which
    # is the interlock crying wolf until someone switches it off. The pattern fires only
    # on a full HH:MM:SS followed by a space and an offset-shaped tail, so an ordinary
    # space-separated stamp ("2026-08-26 09:35") is left alone, and the raw text is still
    # tried if the repair turns out not to parse.
    cands = [txt]
    fixed = re.sub(r"^(.*\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s(\d{2}:?\d{2})$", r"\1+\2", txt)
    if fixed != txt:
        cands.insert(0, fixed)
    for cand in cands:
        try:
            ts = pd.Timestamp(cand)
        except Exception:
            continue
        if ts is not pd.NaT and not pd.isna(ts):
            return ts
    return None


def _bar_interlock(nt_bar, svc_bar, step):
    """Compare the caller's last-closed bar against ours.

    Returns (state, delta_seconds); state is absent | unparseable | ok | mismatch, and
    delta_seconds is None unless a comparison actually happened. Pure -- no I/O, no module
    state -- so the comparison is testable without a master CSV in front of it."""
    txt = "" if nt_bar is None else str(nt_bar).strip()
    if not txt:
        return "absent", None
    ts = _parse_nt_bar(txt)
    if ts is None:
        return "unparseable", None
    try:
        if ts.tzinfo is None and svc_bar.tzinfo is not None:
            # No offset = New York wall clock, because that is what every bar index in
            # this repo is and what the NinjaTrader charts are set to.
            ts = ts.tz_localize(_ET)
        elif ts.tzinfo is not None and svc_bar.tzinfo is None:
            ts = ts.tz_convert(_ET).tz_localize(None)
        delta = abs((ts - svc_bar).total_seconds())
    except Exception:
        # A DST-ambiguous wall clock, a mixed type, anything else: unreadable, which is
        # not the same claim as "the two disagree". Say unreadable.
        return "unparseable", None
    return ("ok" if delta <= step.total_seconds() else "mismatch"), int(delta)


def _measured_step(idx):
    """Minutes between the last two bars -- the OBSERVED series step, which is how a
    5-minute leg being scored on 1-minute bars gives itself away."""
    try:
        return int(round((idx[-1] - idx[-2]).total_seconds() / 60.0))
    except Exception:
        return None


def _recycle_allowance(art):
    """How much of the recycle factor this service is ALLOWED to serve right now.

    Recycle multiplies position size (rf on NOISE: 3.85x, peaking near 5.75x). The bridge's
    circuit breaker counts net contracts and, when its limit is exceeded, FLATTENS AND
    DISABLES every strategy on the account. So if the gate served recycled sizes while the
    rails were still set for one-lot trading, the first gated entry on Monday would trip the
    breaker and silently kill the whole forward test -- ENGU-Q included.

    Rather than depend on someone remembering to raise the rails first, the size this
    service is willing to serve is BOUNDED BY THE RAILS THE HUMAN SET. It reads
    bridge.json, works out the worst-case contracts recycle could ask for, and falls back
    to plain hybrid (1.0) if that would not fit. Raising the rails switches recycle on by
    itself, within one request. Never raises.
    """
    rec = float(art.get("recycle_factor") or 1.0)
    if rec == 1.0:
        return 1.0, None
    limit, err = _rails()                 # same reader max_contracts serves from
    if limit is None:
        return 1.0, f"recycle held back: {err}"
    worst = 3.0 * rec * LIVE_QTY          # the per-trade cap is 3x before recycle
    if limit >= worst:
        return rec, None
    note = (f"recycle HELD BACK (serving plain hybrid): worst case {worst:.0f} contracts "
            f"exceeds the risk rail of {limit}. Raise max_position_contracts and max_qty "
            f"to at least {int(worst)} to switch it on.")
    return 1.0, note


def decide(leg_key, nt_bar=None, *, source="internal"):
    """The live decision. NinjaTrader calls this at a bar's CLOSE, about to enter at the
    NEXT bar's open -- the same timing the backtest gate scores at. Features for that
    entry bar are, by the causal rule, the just-closed bar's market state plus the entry
    bar's clock; we append one placeholder bar so the feature builder produces exactly
    that row, and the placeholder's own prices are never read (the causal shift replaces
    them with the closed bar's).

    nt_bar (optional) is the ISO-8601 stamp of the bar the CALLER believes it is acting
    on. If it disagrees with ours by more than one step we refuse to score at all -- see
    _bar_interlock. Absent is fine and means "no interlock", so an older NinjaScript keeps
    working unchanged.

    source is for /gate/health only: it separates "NinjaTrader asked" from the keep-warm
    loop asking, which otherwise make a dead integration look alive.

    Never raises: any failure returns take=True/size=1.0 with the reason attached."""
    t0 = time.time()
    st = _state_for(leg_key)
    # Stamped on ENTRY, not on the way out: decide() never raises, so the moment it was
    # asked and the moment it answered are the same millisecond, and stamping here means
    # even a path that returns early still records that somebody asked.
    st["last_decide_ts"] = datetime.now().isoformat(timespec="seconds")
    st["last_decide_source"] = source
    base = {"leg": leg_key, "take": True, "size": 1.0, "prob": None,
            "ungated_fallback": True,
            # Served even on the fail-open paths: the rail is a property of the account,
            # not of whether this particular decision worked, and the caller clamps to it
            # either way.
            "max_contracts": _max_contracts(),
            "nt_bar": (str(nt_bar).strip() or None) if nt_bar is not None else None,
            "bar_check": None}
    try:
        legs = {l["key"]: l for l in _gated_legs()}
        leg = legs.get(leg_key)
        if leg is None:
            base["error"] = f"unknown leg {leg_key}"
            _log(f"decide {leg_key} FAIL-OPEN: {base['error']}")
            return base
        art = _load_artifact(leg_key)
        if art is None:
            base["error"] = "no artifact - run --build"
            _log(f"decide {leg_key} FAIL-OPEN: {base['error']}")
            return base

        from augur_engine.ml_gate import entry_features_causal
        with _lock:
            arrays = _refresh_live_arrays(leg)
        idx = arrays["index"]
        if len(idx) < 200:
            base["error"] = "too little data"
            _log(f"decide {leg_key} FAIL-OPEN: {base['error']}")
            return base

        # The leg's CONFIGURED step, not the measured one: a session gap makes the
        # measured step look like 17 hours, and the tolerance would swallow anything.
        step = pd.Timedelta(minutes=5 if str(leg["timeframe"]).startswith("5") else 1)
        bar_state, bar_delta = _bar_interlock(nt_bar, idx[-1], step)
        base["bar_check"] = bar_state
        if bar_state == "unparseable":
            _log(f"decide {leg_key}: could not read bar={str(nt_bar).strip()!r} "
                 f"- interlock NOT armed for this request")
        if bar_state == "mismatch":
            out = dict(base)
            out.update({
                "error": f"bar mismatch: nt={str(nt_bar).strip()} svc={idx[-1].isoformat()}",
                "bars": int(len(idx)), "bar_minutes": _measured_step(idx),
                "last_closed_bar": str(idx[-1]), "bar_delta_s": bar_delta,
                "elapsed_ms": int((time.time() - t0) * 1000)})
            _log(f"decide {leg_key} FAIL-OPEN (BAR MISMATCH): {out['error']} "
                 f"off by {bar_delta}s, step {int(step.total_seconds())}s, "
                 f"{len(idx)} bars @ {out['bar_minutes']}m")
            return out

        # one placeholder bar = the entry bar about to open
        nxt = idx[-1] + step
        arr2 = dict(arrays)
        arr2["index"] = idx.append(pd.DatetimeIndex([nxt]))
        for k in ("open", "high", "low", "close"):
            arr2[k] = np.append(np.asarray(arrays[k], float), float(arrays["close"][-1]))
        if arrays.get("volume") is not None:
            arr2["volume"] = np.append(np.asarray(arrays["volume"], float), 0.0)
        arr2["day_id"] = pd.factorize(pd.Series(arr2["index"]).dt.date)[0].astype("int64")

        F, names = entry_features_causal(arr2)
        if list(names) != list(art["feature_names"]):
            base["error"] = "feature names changed - rebuild artifact"
            _log(f"decide {leg_key} FAIL-OPEN: {base['error']}")
            return base
        x = F[-1:].astype(float)
        prob = float(art["pipe"].predict_proba(x)[0, 1])

        _mode = str(art.get("mode") or "cut").lower()
        thr = float(art.get("threshold") or 0.0)
        # TILT never refuses a trade; every other mode refuses below its threshold.
        take = True if _mode == "tilt" else not (prob < thr)
        rec = 1.0            # defined on every path: a SKIP never reaches the sizing branch
        if _mode == "tilt":
            # Same tier rule as api/paper_gate._tilt_weights, byte for byte: 0.5x under
            # 45%, 1x from 45 to 55%, 2x over 55% -- then the frozen normaliser and the
            # same 3x cap the hybrid uses.
            if str(art.get("scheme") or "tier") == "tier":
                w = 0.5 if prob < 0.45 else (1.0 if prob <= 0.55 else 2.0)
            else:
                w = float(np.clip(0.5 + 2.0 * prob, 0.25, 3.0))
            size = float(min(w / (float(art.get("size_norm") or 1.0)), 3.0))
        elif str(art.get("mode")) == "hybrid" and take:
            w = float(np.clip(1.0 + 4.0 * (prob - 0.50), 0.25, 3.0))
            # Same order as the backtest: normalise, cap the per-trade stretch at 3x, THEN
            # apply the book-level recycle factor (spend the capital the gate freed up).
            size = float(min(w / (float(art.get("size_norm") or 1.0)), 3.0))
            rec, rec_note = _recycle_allowance(art)
            size *= rec
            if rec_note:
                base["recycle_note"] = rec_note
        else:
            size = 1.0 if take else 0.0
        _step = _measured_step(idx)
        out = {"leg": leg_key, "take": bool(take), "size": round(size, 3),
               "prob": round(prob, 4), "threshold": thr,
               # The caller clamps its rounded quantity to this instead of to Qty*3 --
               # the 3x cap is already inside `size` above. See _max_contracts.
               "max_contracts": base["max_contracts"],
               "nt_bar": base["nt_bar"], "bar_check": base["bar_check"],
               # WHICH SERIES DID THIS SCORE? Recorded because for three days every NOISE
               # and ORB decision was scored on ENGU-Q's 1-minute overnight bars and
               # nothing said so -- the probability looked perfectly plausible.
               "bars": int(len(idx)), "bar_minutes": _step,
               "model": art.get("model"), "mode": art.get("mode"),
               "trained_through": art.get("trained_through"),
               "last_closed_bar": str(idx[-1]), "entry_bar": str(nxt),
               "ungated_fallback": False,
               "recycle_factor": float(art.get("recycle_factor") or 1.0),
               "recycle_applied": round(rec, 4),
               "recycle_note": base.get("recycle_note"),
               "elapsed_ms": int((time.time() - t0) * 1000)}
        _log(f"decide {leg_key}: prob={prob:.3f} take={take} size={size:.2f} "
             f"({out['elapsed_ms']}ms, bar {idx[-1]}, {len(idx)} bars @ {_step}m)")
        return out
    except Exception as e:
        base["error"] = f"{type(e).__name__}: {e}"
        base["elapsed_ms"] = int((time.time() - t0) * 1000)
        _log(f"decide {leg_key} FAILED (fail-open): {base['error']}")
        return base


# ── nightly self-refresh ──────────────────────────────────────────────────────────
def _refresh_loop():
    """Rebuild artifacts once per evening after the session close (16:15 ET), so the
    model always knows yesterday. Self-contained -- no dependence on the runner."""
    last_built = None
    while True:
        try:
            try:
                from zoneinfo import ZoneInfo
                et = datetime.now(ZoneInfo("America/New_York"))
            except Exception:
                et = datetime.now()
            day = et.strftime("%Y-%m-%d")
            if et.weekday() < 5 and (et.hour, et.minute) >= (16, 15) and last_built != day:
                _log("nightly artifact rebuild starting")
                build_all()
                last_built = day
        except Exception as e:
            _log(f"refresh loop: {type(e).__name__}: {e}")
        # Keep-warm: score each leg every pass so the bar cache never goes cold.
        # The one measured cold call took 351ms against NinjaTrader's 300ms timeout --
        # which silently UN-GATES that trade (fail-open). A warm call is ~50-110ms,
        # and a background decide() every 10 minutes costs nothing anyone will notice.
        for _leg in _gated_legs():
            try:
                decide(_leg["key"])
            except Exception:
                pass
        time.sleep(600)


# ── the HTTP server ───────────────────────────────────────────────────────────────
def serve():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs

    _git_sha()          # resolve once here so the first /gate/health is a pure lookup

    # warm everything BEFORE the first real request so trade-time latency is pure lookup
    for leg in _gated_legs():
        try:
            _load_artifact(leg["key"])
        except Exception as e:
            _log(f"warm load {leg['key']}: {type(e).__name__}: {e}")
    try:
        if _gated_legs():
            decide(_gated_legs()[0]["key"])       # primes the bar cache
    except Exception:
        pass

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):               # our own log instead
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _page(self):
            """Plain-English status page at http://127.0.0.1:8392 -- the answer to
            "how do I know this thing is running?" without a terminal. Deliberately
            self-refreshing and readable at a glance from across the room."""
            rows = ""
            for leg in _gated_legs():
                a = _artifacts.get(leg["key"]) or {}
                ok = bool(a)
                rows += (f"<tr><td>{leg['key']}</td>"
                         f"<td>{a.get('model') or '-'}</td>"
                         f"<td style='color:{'#1d9e75' if ok else '#e24b4a'}'>"
                         f"{'ready' if ok else 'NOT LOADED'}</td>"
                         f"<td>{str(a.get('trained_through') or '-')[:16]}</td></tr>")
            body = f"""<!doctype html><meta charset=utf-8>
<meta http-equiv=refresh content=15>
<title>ML gate status</title>
<style>body{{font:15px system-ui;background:#111;color:#eee;padding:28px}}
h1{{font-size:34px;margin:0 0 4px}}table{{border-collapse:collapse;margin-top:18px}}
td,th{{padding:6px 16px 6px 0;text-align:left;border-bottom:1px solid #333}}
.s{{color:#888;font-size:13px}}</style>
<h1 style="color:#1d9e75">GATE IS UP</h1>
<div class=s>NinjaTrader can ask this service before every trade.<br>
This page re-checks itself every 15 seconds.</div>
<table><tr><th>strategy</th><th>brain</th><th>state</th><th>taught through</th></tr>
{rows}</table>
<div class=s style="margin-top:20px">code {(_git_sha() or 'unknown')[:7]} &middot;
running since {_PROC_STARTED.replace('T', ' ')} &middot; ceiling
{_max_contracts() if _max_contracts() is not None else '&mdash;'} contracts<br>
If this page ever fails to load, the service is
down &mdash; NinjaTrader keeps trading but takes every signal at normal size.<br>
Restart it by running <code>C:\\EdgeLog\\_gate_server.bat</code></div>"""
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/status"):
                self._page()
            elif u.path == "/gate/health":
                legs = {}
                for leg in _gated_legs():
                    a = _artifacts.get(leg["key"]) or {}
                    s = _leg_state.get(leg["key"]) or {}
                    legs[leg["key"]] = {"loaded": bool(a),
                                        "trained_through": a.get("trained_through"),
                                        "model": a.get("model"),
                                        # last_build_ok null = this PROCESS never tried;
                                        # a loaded artifact then came off disk from an
                                        # earlier run. "Loaded" and "built cleanly" are
                                        # different questions, so both get answered.
                                        "last_build_ok": s.get("last_build_ok"),
                                        "last_build_ts": s.get("last_build_ts"),
                                        "last_build_error": s.get("last_build_error"),
                                        "last_decide_ts": s.get("last_decide_ts"),
                                        "last_decide_source": s.get("last_decide_source")}
                self._json({"ok": True,
                            # Which code is actually running, answerable without guessing
                            # from a restart time -- this process cached its modules at
                            # import and will not notice a push until it is restarted.
                            "git_sha": _git_sha(), "code_path": _REPO_DIR,
                            "started_at": _PROC_STARTED,
                            "live_qty": LIVE_QTY, "max_contracts": _max_contracts(),
                            "legs": legs})
            elif u.path == "/gate/check":
                q = parse_qs(u.query)
                key = (q.get("leg") or [""])[0]
                # &bar is OPTIONAL on purpose: a NinjaScript that predates the interlock
                # still gets a normal answer, it just gets no interlock.
                bar = (q.get("bar") or [""])[0]
                self._json(decide(key, bar or None, source="http"))
            else:
                self._json({"error": "unknown path"}, 404)

    threading.Thread(target=_refresh_loop, daemon=True, name="gate-refresh").start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    _log(f"gate service up on 127.0.0.1:{PORT} "
         f"(legs: {', '.join(l['key'] for l in _gated_legs())})")
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--build-leg")
    ap.add_argument("--check", help="one live decision for a leg, printed")
    ap.add_argument("--bar", help="ISO-8601 last-closed bar to send with --check, "
                                  "the way NinjaTrader does -- lets the bar interlock "
                                  "be exercised by hand without NinjaTrader")
    a = ap.parse_args()
    if a.build:
        build_all()
    if a.build_leg:
        build_artifact({l["key"]: l for l in _gated_legs()}[a.build_leg])
    if a.check:
        print(json.dumps(decide(a.check, a.bar), indent=2))
    if a.serve:
        serve()


if __name__ == "__main__":
    main()
