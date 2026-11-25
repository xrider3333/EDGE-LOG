"""api/cloud_signal_stream.py -- WEBULL_PAPER_TODO.md item 10, "Fire orders at the bar
close from the live price feed" (2026-09-25). Consumer side: everything that reads
api.webull_stream's hand-off file and decides what api/cloud_signal.py should do with
it. The producer side (publishing each completed 5m bar within ~1-2s of its own close)
lives in api/webull_stream.py, which runs in a DIFFERENT OS process (inside
api/qqq_exec.py) -- the only channel between the two is that hand-off file.

WHY A SEPARATE MODULE. api/cloud_signal.py is being edited concurrently by other
sessions right now (the hand-run guard, the NOISE history window). Everything new this
item needs lives here instead, in NEW functions that only ever ADD behaviour around
api.cloud_signal.step() -- see run_stream_aware_step, this module's one integration
point, called from api.cloud_signal.cloud_signal_thread in place of a bare step() call.

THE OWNER'S HONESTY RULE ("live must match the backtest"). A "decision" here is never
reimplemented -- it is always produced by calling api.cloud_signal.closed_arrays /
run_leg_trades / _diff_leg, the EXACT functions step() itself uses, just against a
different OHLC frame. The only way a stream decision and a REST decision can ever
differ is the data they were handed, never the code path. (Since 2026-09-27 the engine
step is api.cloud_signal.leg_decision_trades, which step() calls too, so the history
window, the session_in_progress / vol_prior_ranges pass-throughs and the decide_at_close
probe are shared by construction -- see _dry_run_decision. The one data gap left -- the
QQQ daily cache step() refreshes only AFTER the stream has run on a tick -- is closed by
leaving that bar to step() alone; see _daily_cache_may_still_change.)

SHADOW MODE (design constraint 3 -- the main deliverable). Regardless of the owner
switch below, every 5m leg's stream-implied decision is computed via a DEEP COPY of its
real state (never mutating it) the moment a fresh, safe stream bar is available, and
recorded in <state_dir>/stream_shadow.json. Once the same bar's REST value lands in the
normal on-disk cache, the REST-implied decision is computed the same way (from the SAME
frozen baseline state, so the comparison isolates the OHLC difference) and logged as a
match or a loud disagreement, with how many seconds earlier the stream saw it.

OWNER SWITCH (design constraint 2). <state_dir>/stream_config.json's
`bar_close_from_stream` key (default False, missing-file-safe) -- when true AND the
fresh stream bar clears every safety gate (see stream_bar_is_usable), the stream
decision is additionally COMMITTED for real: the leg's real state advances and its
ENTRY/EXIT rows are appended to signals.csv with bar_source="stream", ahead of REST.
This never invents an exit or reverses a position, and never fires again for a leg
after a same-day disagreement (see _trip_disagreement) -- it only ever changes how SOON
a decision that was going to happen anyway gets recorded.

SCOPE. 5m legs only (ORB_R6, NOISE_382 today) -- api.webull_stream's hand-off is 5m-only
by design (see its HANDOFF_TIMEFRAME_SECONDS); a 1m live leg would be filtered out here
(five_m_legs) and decided by cs.step()'s classic REST path only. NEVER A DIP LEG
(cfg["runner"] == cs.DIP_RUNNER -- the live DIP_424 from 2026-10-13, MANAGER #115), though
it is a 5m leg: it decides on the DAILY close and fills at the next 09:30 open
(api/dip_live.py), so a stream bar could only move its ENTRY rows a few seconds earlier, at
the price of a seven-engine-run probe per dry run (the stream decision AND the REST what-if)
on the 1-CPU box, keyed on a stream-built frame that would evict the probe memo the live and
shadow DIP legs share. Classic cs.step() decides it, on the bar the REST cache holds.
LIVE legs only: `legs` defaults to cs.CROWN_LEGS, never cs.SHADOW_LEGS (OWNER DECISION
2026-09-28 -- ENGUQ_335 (a no-order tracker again since 2026-10-09 ~20:20 MST, OWNER
DECISION), the three NOISE #422 variants and the DIP #424 pair run as shadow legs through
cs.run_shadow_step's classic REST path, never through this module, so no stream decision is
ever committed for a shadow leg).

FAIL-SAFE. run_stream_aware_step wraps every bit of the logic in this module in one
try/except and ALWAYS calls the real api.cloud_signal.step() afterward regardless -- a
bug here can make this feature silently do nothing for a tick, but must never stop a
real signal from being evaluated the classic way.
"""
import copy
import datetime as _dt
import json
import math
import os
import time

from api import cloud_signal as cs                                          # noqa: E402
from api import webull_stream as _wstream                                   # noqa: E402

# How long after each 5m boundary a fresh stream bar is still worth acting on -- design
# constraint 1 ("a fast poll... only in the minute after each 5m boundary").
HANDOFF_WINDOW_SECONDS = 60

# api.cloud_signal.cloud_signal_thread's own sleep-cadence during that window. NOT the
# same constant as api.webull_stream.HANDOFF_POLL_SECONDS (the PRODUCER's ~250ms
# internal publish-check thread, which lives entirely inside api/qqq_exec.py's process
# and answers to nobody else): this one governs how often the LIVE cloud_signal_thread
# loop itself wakes up, and tests/test_cloud_signal.py's existing fake-sleep helper
# (used by test_cloud_signal_thread_writes_ok_true_heartbeat_with_cache_write_failed_note)
# treats any time.sleep(seconds >= 1) as "one iteration finished". Staying at/above 1s
# keeps this feature from disturbing that unrelated timing assumption while still
# cutting the worst-case detection latency from ~30s (the classic cadence) to ~1s -- the
# stream bar itself only changes once every 5 minutes, so sub-second polling of the
# hand-off file buys nothing a real consumer would notice.
HANDOFF_POLL_SECONDS = 0.25   # LATENCY FIX 1b (owner 11-04, MANAGER #266): was 1.0 s

STREAM_CONFIG_FILENAME = "stream_config.json"
SHADOW_FILENAME = "stream_shadow.json"

_DECISION_FIELDS = ("event", "side", "ref_time", "ref_price", "shares", "trade_id",
                    "size", "keel_size")


# ── hand-off file (consumer side -- see api.webull_stream for the producer) ─────────────
def read_closed_bar_handoff(timeframe="5m", home=None):
    """Best-effort read of api.webull_stream's atomically-replaced hand-off file. None
    on anything short of a fully-valid JSON object -- missing file (nothing published
    yet), or any read/parse hiccup. Never raises: the atomic tmp+os.replace write on the
    producer side means a reader only ever sees the previous file or the new one in
    full, never a torn one, but this stays defensive regardless (design constraint 1,
    'never read a half-written file')."""
    path = _wstream.closed_bar_handoff_path(timeframe, home=home)
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def in_handoff_window(now_et, window_seconds=HANDOFF_WINDOW_SECONDS, bar_seconds=300):
    """True only in the `window_seconds` right after a 5m boundary -- outside it there
    is nothing new to fast-poll for (the next bar hasn't closed yet)."""
    return (now_et.timestamp() % bar_seconds) < window_seconds


def _bar_looks_complete(bar):
    """'missing ticks for the minute' (design constraint 4): a bar with no volume or a
    non-finite OHLC value never got real prints and must never be acted on."""
    try:
        vol = float(bar.get("volume"))
        if not math.isfinite(vol) or vol <= 0:
            return False
        for k in ("open", "high", "low", "close"):
            if not math.isfinite(float(bar.get(k))):
                return False
        return True
    except (TypeError, ValueError):
        return False


def stream_bar_is_usable(payload, now_et):
    """The full safety gate (design constraint 4) on a hand-off payload -- pure, so
    'a stale stream never fires' is directly testable with a plain dict, no live
    streamer or thread involved. Returns (ok, reason); reason is always a short,
    loggable string, even on success."""
    if not payload:
        return False, "no handoff payload published yet"
    if not payload.get("connected"):
        return False, "stream not connected"
    if not payload.get("fresh"):
        return False, "stream not fresh"
    # belt-and-braces alongside api.webull_stream.next_handoff_bar's own gate (which
    # never publishes a first-after-connect bar at all) -- a payload written by an
    # older/different producer build is still refused here.
    if int(payload.get("bars_since_connect") or 0) < 2:
        return False, "first bar after the stream (re)connected"
    if not _bar_looks_complete(payload):
        return False, "bar is missing ticks (no volume / non-finite OHLC)"
    if now_et.weekday() >= 5:
        return False, "weekend"
    if not (cs.RTH_OPEN <= now_et.time() <= cs.RTH_CLOSE):
        return False, "outside 09:30-16:00 ET"
    return True, "ok"


# ── owner switch ─────────────────────────────────────────────────────────────────────────
def _stream_config_path(paths):
    return os.path.join(paths["state_dir"], STREAM_CONFIG_FILENAME)


def load_stream_config(paths, log=print):
    """<state_dir>/stream_config.json's `bar_close_from_stream` flag -- default False,
    and a missing file / bad JSON / missing key all resolve to that same safe default.
    Never raises. A separate file from cloud_signal's own state.json on purpose: this
    one is meant to be hand-edited by the owner, and must never collide with the
    idempotency ledger step() reads and rewrites every tick."""
    try:
        with open(_stream_config_path(paths), encoding="utf-8") as f:
            raw = json.load(f)
        return {"bar_close_from_stream": bool(raw.get("bar_close_from_stream", False))}
    except FileNotFoundError:
        return {"bar_close_from_stream": False}
    except Exception as e:
        log(f"[cloud-signal-stream] stream_config.json unreadable, defaulting OFF: "
           f"{type(e).__name__}: {e}")
        return {"bar_close_from_stream": False}


# ── building the stream-augmented bar frame, and running the real engine on it ──────────
def _augment_with_stream_bar(rest_df, bar):
    """The REST-fetched historical 5m frame (or None) with the stream's own newest
    closed bar merged in at the tail -- same 6-column epoch schema, same
    dedupe-by-time/keep-last idiom as api.webull_stream.merge_and_write, so the only
    difference from the REST-only frame is this ONE bar's OHLCV. Never written to disk
    -- purely an in-memory frame for closed_arrays/run_leg_trades to evaluate."""
    import pandas as pd
    cols = ["time", "open", "high", "low", "close", "volume"]
    fresh = pd.DataFrame([{c: bar[c] for c in cols}], columns=cols)
    if rest_df is None or not len(rest_df):
        return fresh
    merged = pd.concat([rest_df[cols], fresh], ignore_index=True)
    return merged.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)


def _effective_now_for_bar(bar_close_epoch, grace_seconds):
    """A synthetic 'now' timestamped just past a bar's own close (+ cloud_signal's own
    CLOSE_GRACE_SECONDS) -- cs.closed_arrays' cutoff test subtracts that same grace, so
    passing this makes it treat THIS bar (and no later one) as the newest closed bar,
    independent of the real wall clock. Using the SAME value for both the stream
    decision and the REST what-if for one bar_epoch is what isolates the comparison to
    the OHLC difference alone (design constraint 2: 'it compares OHLC')."""
    return _dt.datetime.fromtimestamp(bar_close_epoch + grace_seconds, tz=cs._zi(cs.TZ))


def _dry_run_decision(leg_key, cfg, df, now_et, leg_state, bar_source, log, paths=None,
                      not_taken_log=False, arrays_memo=None, stages=None):
    """Runs the exact engine path step() uses (closed_arrays over
    cs.leg_warmup_sessions(cfg) -> cs.leg_decision_trades -> _diff_leg) against a
    throwaway DEEP COPY of `leg_state` -- the real one is never touched here. Returns
    (events, mutated_leg_state_copy); events is None if there is not yet enough history
    to evaluate (closed_arrays returned None, e.g. cold cache).

    leg_decision_trades is the SAME function step() calls, so the history window, the
    session_in_progress / vol_prior_ranges pass-throughs and the decide_at_close probe
    all match it (before 2026-09-27 this path used a flat 60-session window, no `now`
    and no probe). `paths` is the leg's store; the vol_prior_ranges bridge reads its
    daily cache only when it is given (None -- old callers -- skips the bridge, the
    run_leg_trades convention). fetch=False always, to BOTH calls: the stream extras
    never touch the network; step() runs right after on the same tick and refreshes the
    daily cache. In _diff_leg, fetch only gates the scoring-time KEEL fallback ntfy push
    (no event or state depends on it) -- that push is step()'s to send, and its
    once-a-day dedupe would only land on this throwaway copy, so it would repeat.

    `not_taken_log` (2026-10-09): where _diff_leg's "not taken: the market is closed" line
    for this dry run goes -- dropped by default (False), since a throwaway copy's line would
    repeat the one step() logs off the real state; _handle_handoff_window collects it and
    logs it only for a decision it commits (step() never sees that trade as new again).

    `arrays_memo` (FAST NOISE, 2026-11-25): a dict shared by the legs of ONE pass over ONE
    bar (same df, same now_et) -- closed_arrays is a pure function of (df, now_et, "5m",
    warmup), so legs with the same warm-up (the three NOISE legs: 262) build it once; each
    leg still gets its OWN copy (_copy_arrays) so nothing one strategy does to its inputs can
    reach another leg. None (every other caller) = today's path exactly. `stages` (optional
    dict) receives arrays_ms / engine_ms / diff_ms for the own-bar latency line."""
    t0 = time.perf_counter()
    warmup = cs.leg_warmup_sessions(cfg)
    if arrays_memo is None:
        arrays = cs.closed_arrays(df, now_et, "5m", warmup)
    else:
        if warmup not in arrays_memo:
            arrays_memo[warmup] = cs.closed_arrays(df, now_et, "5m", warmup)
        arrays = _copy_arrays(arrays_memo[warmup])
    t1 = time.perf_counter()
    if stages is not None:
        stages["arrays_ms"] = (t1 - t0) * 1000
    if arrays is None:
        return None, None
    trades, diff_arrays = cs.leg_decision_trades(cfg, arrays, leg_key, "5m", now_et, paths,
                                                 False, log=log)
    t2 = time.perf_counter()
    if stages is not None:
        stages["engine_ms"] = (t2 - t1) * 1000
    if trades is None:
        # a live leg the HALF-DAY RULE guard refuses (cs.half_day_rule_refusal): no decision
        # here either -- step() reports it and pages (cs._note_live_leg_not_ready)
        return None, None
    leg_state_copy = copy.deepcopy(leg_state)
    max_age = cfg.get("max_entry_age_sec", 3 * cs.TIMEFRAME_SECONDS["5m"])
    events = cs._diff_leg(leg_key, trades, leg_state_copy, now_et, max_entry_age_sec=max_age,
                          bar_source=bar_source, cfg=cfg, arrays=diff_arrays, fetch=False,
                          log=log, not_taken_log=not_taken_log)
    if stages is not None:
        stages["diff_ms"] = (time.perf_counter() - t2) * 1000
    return events, leg_state_copy


def _copy_arrays(arrays):
    """A private copy of one closed_arrays() result: every numpy array copied, the
    DatetimeIndex (immutable) and the meta dict copied. None stays None."""
    if arrays is None:
        return None
    out = {}
    for k, v in arrays.items():
        if hasattr(v, "copy") and not isinstance(v, dict):
            out[k] = v.copy()
        elif isinstance(v, dict):
            out[k] = copy.deepcopy(v)
        else:
            out[k] = v
    return out


# Last bar_epoch each leg was held back for by _daily_cache_may_still_change -- only so
# that skip is logged once per bar, not once per ~1s hand-off-window tick.
_DAILY_GATE_LOGGED = {}


def _daily_cache_may_still_change(cfg, now, paths):
    """True when this leg reads the vol_prior_ranges bridge AND a fetching step() may
    still rewrite QQQ_1d.csv today (cs._daily_cache_refresh_due -- the SAME test step()'s
    own refresh uses). run_stream_aware_step runs the stream extras BEFORE step() on a
    tick, and step() only refreshes that file when it processes a new bar -- so the first
    bar of each ET day would otherwise be decided off a cache missing D-1 while step() and
    the REST what-if, moments later, read the refreshed one (calibration gains a session:
    a borderline rank can flip -> a false DISAGREEMENT, or with bar_close_from_stream on,
    a committed decision step() would not make). Such a bar is left to classic step()
    alone; the stream resumes as soon as step() has made today's refresh attempt.
    A plain leg is never held back. Any error reads as True: skipping the stream is always
    safe, step() still decides the bar."""
    try:
        strategy = cfg.get("strategy")
        if not cs._leg_accepts_vol_prior_ranges(strategy):
            return False
        if cs.required_lookback_sessions(strategy) is None:
            return False
        return bool(cs._daily_cache_refresh_due(now, paths))
    except Exception:
        return True


# ── comparing two decisions ──────────────────────────────────────────────────────────────
def _canonical_events(events):
    """The decision-relevant fields of an event list, order-preserved -- deliberately
    excludes `emitted_at`/`bar_source` (which always differ between the two sides by
    construction) and `reason` (prose, not decision-bearing)."""
    return [tuple(e.get(f) for f in _DECISION_FIELDS) for e in (events or [])]


# PRICE TOLERANCE (2026-09-28). The stream bar and the REST bar can carry the same close to
# different precision (seen live: NOISE_382 @ 1790604600, the SAME short entry, ref_price
# 735.66 stream vs 735.6599 REST), and an exact compare called that a DISAGREEMENT -- which
# with bar_close_from_stream on trips the day's latch for nothing. ref_price now matches
# within half a cent; every other decision field stays exact.
# FLOAT SLACK (2026-09-28 follow-up): a gap of exactly half a cent is not exactly 0.005 in
# binary floating point -- 735.70 - 735.695 computes to 0.0049999999999955 (in), but
# 730.19 - 730.185 to 0.0050000000001091 (out). REF_PRICE_EPS absorbs that representation
# error (a billionth of a dollar, far below any real price step), so half a cent is always in
# and 0.0051 is always out, whatever the two prices are.
REF_PRICE_TOLERANCE = 0.005
REF_PRICE_EPS = 1e-9
_REF_PRICE_AT = _DECISION_FIELDS.index("ref_price")


def _prices_close(a, b):
    try:
        return abs(float(a) - float(b)) <= REF_PRICE_TOLERANCE + REF_PRICE_EPS
    except (TypeError, ValueError):
        return a == b


def _same_event(ea, eb):
    return all(_prices_close(x, y) if i == _REF_PRICE_AT else x == y
               for i, (x, y) in enumerate(zip(ea, eb)))


def compare_decisions(stream_events, rest_events):
    """(match, detail). `detail` is always a short, loggable string; a match that needed
    the ref_price tolerance names both prices."""
    a, b = _canonical_events(stream_events), _canonical_events(rest_events)
    if a == b:
        return True, f"same decision ({len(a)} event(s))"
    if len(a) == len(b) and all(_same_event(ea, eb) for ea, eb in zip(a, b)):
        prices = ", ".join(f"stream {ea[_REF_PRICE_AT]} vs rest {eb[_REF_PRICE_AT]}"
                           for ea, eb in zip(a, b) if ea[_REF_PRICE_AT] != eb[_REF_PRICE_AT])
        return True, (f"same decision ({len(a)} event(s)); ref_price within "
                      f"{REF_PRICE_TOLERANCE}: {prices}")
    return False, f"stream={a!r} rest={b!r}"


def _ohlc_diff(bar_a, bar_b):
    out = {}
    for k in ("open", "high", "low", "close", "volume"):
        try:
            out[k] = round(float(bar_a.get(k)) - float(bar_b.get(k)), 6)
        except (TypeError, ValueError):
            out[k] = None
    return out


# ── shadow-decision ledger (this module's OWN small file -- never state.json) ───────────
def _shadow_path(paths):
    return os.path.join(paths["state_dir"], SHADOW_FILENAME)


def _load_shadow(paths):
    try:
        with open(_shadow_path(paths), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_shadow(shadow, paths):
    path = _shadow_path(paths)
    os.makedirs(paths["state_dir"], exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(shadow, f, indent=2, default=str)
    # same retry-on-transient-lock helper every other writer in this pipeline uses
    # (api.cloud_signal / tools.qqq_paper) -- this file can be read by a debugging
    # session at the same moment a live tick rewrites it.
    cs.qp._replace_with_retry(tmp, path, log=None, what="[cloud-signal-stream] stream_shadow.json")


def already_shadowed(paths, leg_key, bar_epoch):
    shadow = _load_shadow(paths)
    return str(bar_epoch) in (shadow.get(leg_key) or {})


def _wall_now():
    import time as _t
    return _t.time()


def record_shadow_decision(paths, leg_key, bar_epoch, events, bar, baseline_leg_state,
                           now_epoch, committed_live, log=print, source="stream"):
    shadow = _load_shadow(paths)
    shadow.setdefault(leg_key, {})[str(bar_epoch)] = {
        "events": events, "bar": bar, "baseline_leg_state": baseline_leg_state,
        "decided_epoch": now_epoch,
        "decided_at": _dt.datetime.fromtimestamp(now_epoch, tz=cs._zi(cs.TZ)).isoformat(),
        "committed_live": bool(committed_live),
        "source": source,
    }
    _save_shadow(shadow, paths)


def _is_disagreement_tripped(paths, leg_key, today_iso):
    shadow = _load_shadow(paths)
    rec = (shadow.get("_disagreements") or {}).get(leg_key)
    return bool(rec and rec.get("date") == today_iso)


def _trip_disagreement(shadow, leg_key, today_iso, bar_epoch, now, log):
    """design constraint 2, 'follows the REST decision from then on': once a leg that
    was fired live from the stream disagrees with REST, stop firing THAT leg live for
    the rest of the trading day (shadow logging keeps running). Never reverses or
    cancels anything already sent -- this only prevents a FUTURE live commit.

    Mutates the CALLER's `shadow` dict in place and does not save it -- the only caller
    (_resolve_pending_against_rest) already owns one load/mutate/save cycle for this
    file per call, and an independent save from in here raced it: it would refresh its
    own read AFTER this trip, and its own end-of-call save would silently overwrite (undo)
    the very entry just written, which is exactly the bug the first version of this
    function had (caught by
    test_disagreement_after_a_live_commit_trips_latch_and_blocks_future_live_commits)."""
    shadow.setdefault("_disagreements", {})[leg_key] = {
        "date": today_iso, "at": now.isoformat(), "bar_epoch": bar_epoch,
    }
    log(f"[cloud-signal-stream] {leg_key}: disagreement latch TRIPPED for {today_iso} -- "
       "will not fire live from the stream again today for this leg (shadow continues)")


# ── the two halves of one tick ───────────────────────────────────────────────────────────
def _handle_handoff_window(now, five_m_legs, paths, stream_cfg, log, state=None,
                           payload=None, force_live=False, bar_source="stream", on_commit=None,
                           stage_out=None):
    """Runs only inside the ~1 minute after a 5m boundary. Reads the hand-off file
    once; if it clears every safety gate, computes (and records) each 5m leg's
    stream-implied decision, and -- only when the owner switch is on AND that leg's
    disagreement latch is not tripped for today -- commits it for real.

    `state` (ORDERS FIRST, 2026-11-18): a snapshot of cs state.json taken BEFORE this
    tick's step() -- run_stream_aware_step hands it in when the owner switch is OFF and
    the extras run after step(), so the dry run sees exactly the baseline it saw when it
    ran first. Never written back (state_changed needs want_live, which is off then).

    `stage_out` (FAST NOISE, 2026-11-25): an optional dict; each leg's per-stage timings
    (start_ms = when its own work began after the pass started, arrays_ms / engine_ms /
    diff_ms from _dry_run_decision) land under its key BEFORE on_commit runs, so the own-bar
    log line can say where the time went. Legs of one pass share one closed_arrays build per
    warm-up (arrays_memo -- see _dry_run_decision)."""
    t_pass0 = time.perf_counter()
    if payload is None:
        payload = read_closed_bar_handoff("5m", home=paths.get("home"))
        ok, reason = stream_bar_is_usable(payload, now)
        if not ok:
            return
    bar = {k: payload[k] for k in ("time", "open", "high", "low", "close", "volume")}
    bar_epoch = int(bar["time"])
    rest_df = cs.historical_bars("5m", paths)
    augmented = _augment_with_stream_bar(rest_df, bar)
    effective_now = _effective_now_for_bar(bar_epoch + cs.TIMEFRAME_SECONDS["5m"],
                                           cs.CLOSE_GRACE_SECONDS)
    today = now.date().isoformat()
    want_live = bool(stream_cfg.get("bar_close_from_stream")) or bool(force_live)
    if state is not None:
        # PRE-STEP SNAPSHOT (VERIFIER 11-18): the caller read the switch OFF and step() has
        # already run. A flip to ON between the two reads must never commit from the stale
        # snapshot (would roll state.json back and double-write signals.csv): shadow only.
        want_live = False

    state_changed = False
    keel_events = []          # committed rows for the KEEL entry note, AFTER the loop
    arrays_memo = {}          # one closed_arrays per warm-up for this bar (FAST NOISE)
    for leg_key, cfg in five_m_legs.items():
        if already_shadowed(paths, leg_key, bar_epoch):
            continue
        if state is None:
            state = cs._load_state(paths)
            state.setdefault("legs", {})
        leg_state = state["legs"].setdefault(leg_key, {"trades": {}})
        if leg_state.get("last_bar_epoch") == bar_epoch:
            continue   # this leg already has a real decision for this bar
        if _daily_cache_may_still_change(cfg, now, paths):
            # real `now`, not effective_now: the question is whether step() on THIS tick
            # (or a later one today) may still rewrite QQQ_1d.csv -- see the helper.
            if _DAILY_GATE_LOGGED.get(leg_key) != bar_epoch:
                _DAILY_GATE_LOGGED[leg_key] = bar_epoch
                log(f"[cloud-signal-stream] {leg_key} @ {bar_epoch}: no stream decision -- "
                   "QQQ daily cache not yet refreshed today (vol_prior_ranges); classic "
                   "step() decides this bar")
            continue
        baseline = copy.deepcopy(leg_state)
        not_taken = []        # "not taken: the market is closed" lines -- logged on commit only
        stages = {"start_ms": (time.perf_counter() - t_pass0) * 1000}
        events, mutated = _dry_run_decision(leg_key, cfg, augmented, effective_now, leg_state,
                                            bar_source, log, paths=paths,
                                            not_taken_log=not_taken.append,
                                            arrays_memo=arrays_memo, stages=stages)
        if stage_out is not None:
            stage_out[leg_key] = stages
        if events is None:
            continue
        committed = False
        levels = any(str(e.get("event") or "").upper() == "LEVELS" for e in events)
        if want_live and levels:
            # RESTING LEVELS (2026-09-29 review): a bar that moves a resting stop (a LEVELS
            # row) is never committed from the stream close -- if REST's close for the same
            # bar did not arm breakeven, the live stop would move while the backtest kept
            # its stop, and rec["be_emitted"] would block the correction. REST step()
            # decides this bar (a breakeven move can wait the few seconds).
            log(f"[cloud-signal-stream] {leg_key} @ {bar_epoch}: stream decision carries a "
               f"LEVELS row -- not fired live; classic step() decides this bar")
        elif want_live and not _is_disagreement_tripped(paths, leg_key, today):
            mutated["last_bar_epoch"] = bar_epoch
            state["legs"][leg_key] = mutated
            cs._append_signals(events, paths)
            if on_commit is not None and events:
                try:
                    on_commit(leg_key, events)   # OWN-BAR: wake the executor per leg
                except Exception:
                    pass
            # KEEL ENTRY EXTRAS (MANAGER #76): a committed stream ENTRY is the leg's real
            # entry (step() will not emit it again), so its KEEL log line / size-diff alert
            # goes out from here -- after the loop and the state write, see below
            keel_events.extend(events)
            state_changed = True
            committed = True
            log(f"[cloud-signal-stream] LIVE from the stream: {leg_key} @ {bar_epoch} -- "
               f"{len(events)} event(s), bar_source={bar_source}")
            for line in not_taken:   # this commit IS the leg's real decision (see above)
                log(line)
            # LATE SKIPS ARE NEVER SILENT (owner 2026-10-14): the dry run could not page
            # (fetch=False) and step() never re-diffs this bar -- the commit pages instead
            cs._push_committed_late_skips(leg_key, cfg, baseline, mutated, effective_now,
                                          paths=paths, log=log)
        elif want_live:
            log(f"[cloud-signal-stream] {leg_key}: stream decision computed but not fired "
               f"live -- disagreement latch tripped today ({today})")
        record_shadow_decision(paths, leg_key, bar_epoch, events, bar, baseline,
                               _wall_now() if bar_source == "ownbar" else now.timestamp(),
                               committed, log=log, source=bar_source)
        log(f"[cloud-signal-stream] shadow: {leg_key} stream decision @ {bar_epoch} -> "
           f"{len(events)} event(s)")
    if state_changed:
        state["generated_at"] = now.isoformat()
        cs._write_state(state, paths)
    if keel_events:
        # once, after every leg is committed and state.json is written, and the push on a
        # daemon thread -- a slow ntfy can never delay another leg's row or the state write.
        # The live owner switch only ever commits on the live thread, hence fetch=True.
        cs._note_keel_entries(keel_events, five_m_legs, paths, True, log=log,
                              push=cs._engine_push_background)


def _resolve_pending_against_rest(now, five_m_legs, paths, log):
    """Runs every tick (not just inside the hand-off window -- REST typically lands
    ~30s after close, which is often just past it). For each leg with a pending shadow
    decision whose bar has now appeared in the REST-fed on-disk cache, computes the
    REST-implied decision from the SAME frozen baseline state and compares."""
    shadow = _load_shadow(paths)
    pending_legs = [k for k in shadow if k in five_m_legs]
    if not pending_legs:
        return
    rest_df = cs.historical_bars("5m", paths)
    if rest_df is None or not len(rest_df):
        return
    changed = False
    for leg_key in pending_legs:
        cfg = five_m_legs[leg_key]
        pending = dict(shadow.get(leg_key) or {})
        for bar_epoch_str, rec in list(pending.items()):
            bar_epoch = int(bar_epoch_str)
            row = rest_df[rest_df["time"] == bar_epoch]
            if not len(row):
                continue   # REST has not caught up to this bar yet
            rest_bar = {c: float(row.iloc[0][c]) for c in ("open", "high", "low", "close", "volume")}
            rest_bar["time"] = bar_epoch
            effective_now = _effective_now_for_bar(bar_epoch + cs.TIMEFRAME_SECONDS["5m"],
                                                   cs.CLOSE_GRACE_SECONDS)
            rest_events, _ = _dry_run_decision(leg_key, cfg, rest_df, effective_now,
                                               rec["baseline_leg_state"], "webull", log,
                                               paths=paths)
            rest_events = rest_events or []
            match, detail = compare_decisions(rec["events"], rest_events)
            close_epoch = bar_epoch + cs.TIMEFRAME_SECONDS["5m"]
            stream_latency = max(0.0, rec["decided_epoch"] - close_epoch)
            rest_latency = max(0.0, now.timestamp() - close_epoch)
            if match:
                log(f"[cloud-signal-stream] shadow MATCH {leg_key} @ {bar_epoch}: stream and "
                   f"REST agree ({detail}); stream saw it {stream_latency:.1f}s after close vs "
                   f"REST's {rest_latency:.1f}s (~{max(0.0, rest_latency - stream_latency):.1f}s saved)"
                   + (f"; ohlc_diff(stream-rest)={_ohlc_diff(rec['bar'], rest_bar)}"
                      if "ref_price within" in detail else ""))
            else:
                log(f"[cloud-signal-stream] STREAM/REST DISAGREEMENT {leg_key} @ {bar_epoch}: "
                   f"{detail}; ohlc_diff(stream-rest)={_ohlc_diff(rec['bar'], rest_bar)}")
                if rec.get("committed_live"):
                    _trip_disagreement(shadow, leg_key, now.date().isoformat(), bar_epoch, now, log)
            if rec.get("source") == "ownbar":
                _ownbar_audit(paths, leg_key, bar_epoch, rec, rest_bar, rest_events, match,
                              detail, log)
            del pending[bar_epoch_str]
            changed = True
        if pending:
            shadow[leg_key] = pending
        else:
            shadow.pop(leg_key, None)
    if changed:
        _save_shadow(shadow, paths)


# ── OWN-BAR FAST PATH (owner order 2026-11-21, PAPER only -- see api/ownbar.py) ─────────
# The executor's streamer folds the five stream 1m bars at the boundary and publishes
# ohlc_stream/QQQ_5m_ownbar.json + a UDP wake. Here that bar is committed through the SAME
# _handle_handoff_window commit path item 10 uses (bar_source="ownbar"); a bar the gates
# refuse is simply not committed, so step()'s REST + guard path decides it as today. The
# REST-final bar is still compared afterwards (_resolve_pending_against_rest ->
# _ownbar_audit): logs/ownbar_audit.jsonl + a phone alert on a decision flip. Nothing is
# ever reversed.
OWNBAR_MISSING_AFTER_S = 1.5     # no own-bar file for this boundary by close+1.5 s -> fallback
                                 # (the streamer itself gives up at close + ownbar.CONFIRM_BY_S)
_OWNBAR_ALERTS = None
_OWNBAR_DONE = {"bar_end": None}
_OWNBAR_REFUSAL_LOGGED = {"why": None}


def _ownbar_mod():
    from api import ownbar
    return ownbar


def _alerts():
    global _OWNBAR_ALERTS
    if _OWNBAR_ALERTS is None:
        _OWNBAR_ALERTS = _ownbar_mod().EpisodeAlert()
    return _OWNBAR_ALERTS


def _ownbar_push(msg, paths, log, priority="high"):
    """Phone alert through the engine's own ntfy helper (background thread)."""
    try:
        cs._engine_push_background(msg, "QQQ own bar", priority=priority, paths=paths, log=log)
    except Exception as e:
        log(f"[cloud-signal-stream] own-bar push failed: {type(e).__name__}: {e}")


def ownbar_active(paths, log=print):
    """True when EDGELOG_OWNBAR_DECIDE=1 and the broker config is PAPER. A set flag beside a
    LIVE (or non-PAPER) config is refused, logged and alerted once per reason."""
    ob = _ownbar_mod()
    if not ob.enabled():
        return False
    on, why = ob.active()
    if on:
        _OWNBAR_REFUSAL_LOGGED["why"] = None
        return True
    if _OWNBAR_REFUSAL_LOGGED["why"] != why:
        _OWNBAR_REFUSAL_LOGGED["why"] = why
        log(f"[cloud-signal-stream] own-bar fast path REFUSED: {why}")
        _ownbar_push(f"Own-bar fast path is OFF: {why}. REST bars decide.", paths, log)
    return False


def _ownbar_fallback(paths, bar_end, why, log):
    log(f"[cloud-signal-stream] own bar @ close {bar_end}: FALLBACK to REST -- {why}")
    _ownbar_mod().append_audit(paths.get("home") or cs.edgelog_home(),
                               {"kind": "fallback", "bar_end": bar_end, "why": why})
    _alerts().fail("ownbar", f"Own-bar path fell back to REST bars: {why}. Orders now wait "
                   "for the REST bar (~7 s). One alert per episode.",
                   lambda m: _ownbar_push(m, paths, log))


def _rth_bar(bar_start):
    """True when the 5m bar opening at bar_start is a regular-session bar (09:30..15:55 ET,
    weekday, and before a half day's close)."""
    try:
        et = _dt.datetime.fromtimestamp(bar_start, tz=cs._zi(cs.TZ))
        if et.weekday() >= 5 or not (cs.RTH_OPEN <= et.time() < cs.RTH_CLOSE):
            return False
        close = cs._session_close_dt(et)
        return close is None or et + _dt.timedelta(minutes=5) <= close
    except Exception:
        return False


_OWNBAR_OFF_LOGGED = {}       # last legs_off set logged (once per change, not per bar)


def _stage_text(st, pre_s, total_s):
    """' [stages: wake 372 ms, queue 410, arrays 21, engine 380, diff 6, commit 4]' for the
    own-bar line: wake = bar end -> this pass started (fold + grace + UDP), queue = this leg
    waited behind the legs decided before it (the first leg: the bar prep -- REST cache read,
    own bar spliced on, state.json read), arrays / engine / diff = its own
    _dry_run_decision, commit = the rest (signals.csv row + state copy). '' if unknown."""
    try:
        if not st:
            return ""
        start, arr = float(st.get("start_ms", 0)), float(st.get("arrays_ms", 0))
        eng, dif = float(st.get("engine_ms", 0)), float(st.get("diff_ms", 0))
        commit = max(0.0, total_s * 1000 - start - arr - eng - dif)
        return (f" [stages: wake {pre_s * 1000:.0f} ms, queue {start:.0f}, arrays {arr:.0f}, "
                f"engine {eng:.0f}, diff {dif:.0f}, commit {commit:.0f}]")
    except Exception:
        return ""


def handle_ownbar(now, five_m_legs, paths, log, wall=None):
    """One own-bar pass for the boundary that just closed. Returns True when the bar was
    handled (committed or fallen back), False when there is nothing to do yet."""
    import time as _t
    ob = _ownbar_mod()
    wall = _t.time() if wall is None else wall
    bar_end = int(wall // 300) * 300
    if _OWNBAR_DONE["bar_end"] == bar_end:
        return False
    if wall - bar_end > HANDOFF_WINDOW_SECONDS:
        return False
    if not _rth_bar(bar_end - 300):
        return False          # the 09:25 bar (or any non-RTH bar) has no own bar -- not a fallback
    home = paths.get("home") or cs.edgelog_home()
    payload = ob.read_handoff(home)
    if not payload or int(payload.get("bar_end") or 0) != bar_end:
        if wall - bar_end < OWNBAR_MISSING_AFTER_S:
            return False
        _OWNBAR_DONE["bar_end"] = bar_end
        _ownbar_fallback(paths, bar_end, "no own bar published for this close (stream "
                         "thread down?)", log)
        return True
    _OWNBAR_DONE["bar_end"] = bar_end
    if not payload.get("ok") or not payload.get("bar"):
        _ownbar_fallback(paths, bar_end, str(payload.get("reason") or "own bar unusable"), log)
        return True
    _alerts().ok("ownbar")
    bar = dict(payload["bar"])
    t_dec0 = _t.time()

    stage_out = {}

    def _wake_exec(leg_key, events):
        ob.wake(ob.exec_port(), f"{leg_key}:{bar_end}".encode())
        t_now = _t.time()
        log(f"[cloud-signal-stream] own bar {leg_key} @ close {bar_end}: decided "
            f"{(t_now - bar_end) * 1000:.0f} ms after bar end "
            f"(decision {(t_now - t_dec0) * 1000:.0f} ms), executor woken"
            f"{_stage_text(stage_out.get(leg_key), t_dec0 - bar_end, t_now - t_dec0)}")

    # EXEC LEGS OFF (GO 2026-11-25): a leg the executor has off sends no order -- not decided
    # here; step() decides it on the REST bar (its ledger rows unchanged, just later)
    try:
        off = ob.engine_legs_off(home, list(five_m_legs))
    except Exception:
        off = set()
    if off:
        if _OWNBAR_OFF_LOGGED.get("legs") != sorted(off):
            _OWNBAR_OFF_LOGGED["legs"] = sorted(off)
            log(f"[cloud-signal-stream] own bar: {', '.join(sorted(off))} off at the executor "
                f"(legs_off) -- decided by the REST step, not the own bar")
        five_m_legs = {k: v for k, v in five_m_legs.items() if k not in off}
    _handle_handoff_window(now, five_m_legs, paths, {}, log, payload=bar, force_live=True,
                           bar_source="ownbar", on_commit=_wake_exec, stage_out=stage_out)
    return True


def _ownbar_audit(paths, leg_key, bar_epoch, rec, rest_bar, rest_events, match, detail, log):
    """Own bar vs REST-final: one jsonl row; a decision flip pages (never reversed)."""
    ob = _ownbar_mod()
    flip = not match
    ob.append_audit(paths.get("home") or cs.edgelog_home(), {
        "kind": "audit", "leg": leg_key, "bar_start": bar_epoch,
        "own_bar": rec.get("bar"), "rest_final_bar": rest_bar,
        "ohlc_diff_own_minus_rest": _ohlc_diff(rec.get("bar") or {}, rest_bar),
        "own_decision": _canonical_events(rec.get("events")),
        "rest_decision": _canonical_events(rest_events),
        "committed_live": bool(rec.get("committed_live")),
        "decided_epoch": rec.get("decided_epoch"), "flip": flip, "detail": detail,
    })
    if flip:
        own_n, rest_n = len(rec.get("events") or []), len(rest_events or [])
        _ownbar_push(f"OWN-BAR FLIP {leg_key} bar {bar_epoch}: own bar decided {own_n} "
                     f"event(s), REST-final bar {rest_n}. Order NOT reversed -- check the "
                     f"position. {detail}"[:900], paths, log, priority="urgent")


# ── the one integration point api/cloud_signal.py calls ─────────────────────────────────
def run_stream_aware_step(now=None, legs=None, paths=None, fetch=True, warnings=None, log=print):
    """Drop-in replacement for api.cloud_signal.step() at the ONE live call site
    (cloud_signal_thread): does everything above around the edges, then ALWAYS calls
    the real step() and returns exactly what it returns. `bar_close_from_stream=False`
    (the default) makes every extra in this module read-only shadow logging -- the
    events step() returns, and every file step() itself writes, are byte-for-byte what
    calling step() directly would have produced. See module docstring's FAIL-SAFE note
    for why the extras are wrapped in their own try/except."""
    now = now or _dt.datetime.now(tz=cs._zi(cs.TZ))
    if now.tzinfo is None:
        now = now.replace(tzinfo=cs._zi(cs.TZ))
    legs = legs if legs is not None else cs.CROWN_LEGS
    paths = paths or cs.DEFAULT_PATHS
    # OWN-BAR FAST PATH (2026-11-21): flag on + PAPER -> the own bar is committed first, the
    # item-10 hand-off path is skipped, and step() (REST + guard) decides anything not
    # committed. Flag off -> nothing below this block changes.
    own = False
    try:
        own = ownbar_active(paths, log=log)
    except Exception as e:
        log(f"[cloud-signal-stream] own-bar check failed (classic path): {type(e).__name__}: {e}")
    if own:
        five_m_legs = {k: v for k, v in legs.items()
                       if v.get("timeframe") == "5m" and v.get("runner") != cs.DIP_RUNNER}
        try:
            if five_m_legs and not cs.bar_cache_refusal("5m", paths):
                handle_ownbar(now, five_m_legs, paths, log)
        except Exception as e:
            log(f"[cloud-signal-stream] own-bar pass failed (REST path decides): "
               f"{type(e).__name__}: {e}")
        try:
            if five_m_legs:
                _resolve_pending_against_rest(now, five_m_legs, paths, log)
        except Exception as e:
            log(f"[cloud-signal-stream] own-bar audit failed: {type(e).__name__}: {e}")
        return cs.step(now=now, legs=legs, paths=paths, fetch=fetch, warnings=warnings)
    # ORDERS FIRST (2026-11-18, bar-close-to-order latency): with the owner switch OFF (the
    # box today -- bar_close_from_stream False, no stream row ever committed) every extra
    # below is diagnostic only: deep-copied dry runs (ORB + NOISE incl. KEEL scoring) whose
    # results go to stream_shadow.json and the log, never to state.json or signals.csv. They
    # used to run BEFORE step(), so on the tick the REST bar landed the REST what-if dry
    # runs (and, when the stream bar arrived on the same tick, the stream dry runs) sat in
    # front of the order-placing step(). Now step() runs first and its rows reach
    # signals.csv (api/qqq_exec.py wakes on its mtime) before any of them. The extras get
    # the PRE-step state.json snapshot, so their baseline is what it was. With the switch
    # ON the old order stays: a stream commit must land before step() decides the bar.
    want_live = None
    try:
        if not cs.bar_cache_refusal("5m", paths):
            want_live = bool(load_stream_config(paths, log=log).get("bar_close_from_stream"))
    except Exception:
        want_live = None   # unknown -> keep the old order (extras first), the safe default
    if want_live is False:
        pre_state = None
        try:
            if any(v.get("timeframe") == "5m" and v.get("runner") != cs.DIP_RUNNER
                   for v in legs.values()) and in_handoff_window(now):
                pre_state = cs._load_state(paths)
                pre_state.setdefault("legs", {})
        except Exception as e:
            log(f"[cloud-signal-stream] pre-step state snapshot failed (stream shadow skips "
               f"this tick): {type(e).__name__}: {e}")
            pre_state = False
        events = cs.step(now=now, legs=legs, paths=paths, fetch=fetch, warnings=warnings)
        _run_stream_extras(now, legs, paths, log, pre_state=pre_state)
        return events
    _run_stream_extras(now, legs, paths, log)
    return cs.step(now=now, legs=legs, paths=paths, fetch=fetch, warnings=warnings)


def _run_stream_extras(now, legs, paths, log, pre_state=None):
    """The stream hand-off + REST what-if, wrapped so they can never stop step().
    `pre_state`: None = load state.json when needed (extras run first); a dict = the
    pre-step snapshot (extras run after step()); False = snapshot failed, skip hand-off."""
    # never a DIP leg (cfg["runner"] == cs.DIP_RUNNER) -- see the module docstring's SCOPE: the
    # classic step() below still decides it, like every leg this filter leaves out
    five_m_legs = {k: v for k, v in legs.items()
                   if v.get("timeframe") == "5m" and v.get("runner") != cs.DIP_RUNNER}

    try:
        # 5m CACHE NEVER SHRINKS (api/cloud_signal.py): while the guard refuses QQQ_5m.csv no 5m
        # leg decides -- nor does a stream decision off the stream bar alone
        if five_m_legs and not cs.bar_cache_refusal("5m", paths):
            stream_cfg = load_stream_config(paths, log=log)
            if in_handoff_window(now) and pre_state is not False:
                _handle_handoff_window(now, five_m_legs, paths, stream_cfg, log,
                                       state=pre_state)
            _resolve_pending_against_rest(now, five_m_legs, paths, log)
    except Exception as e:
        log(f"[cloud-signal-stream] stream extras failed (classic step() still runs): "
           f"{type(e).__name__}: {e}")
