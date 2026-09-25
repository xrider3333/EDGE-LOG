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
differ is the data they were handed, never the code path.

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
by design (see its HANDOFF_TIMEFRAME_SECONDS), and ENGUQ_335 (1m) is unaffected and
keeps going through step()'s normal REST path exactly as before.

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
HANDOFF_POLL_SECONDS = 1.0

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


def _dry_run_decision(leg_key, cfg, df, now_et, leg_state, bar_source, log):
    """Runs the exact engine path step() uses (closed_arrays -> run_leg_trades ->
    _diff_leg) against a throwaway DEEP COPY of `leg_state` -- the real one is never
    touched here. Returns (events, mutated_leg_state_copy); events is None if there is
    not yet enough history to evaluate (closed_arrays returned None, e.g. cold cache)."""
    warmup = cfg.get("warmup_sessions", cs.DEFAULT_WARMUP_SESSIONS)
    arrays = cs.closed_arrays(df, now_et, "5m", warmup)
    if arrays is None:
        return None, None
    trades = cs.run_leg_trades(cfg, arrays, leg_key=leg_key, log=log)
    leg_state_copy = copy.deepcopy(leg_state)
    max_age = cfg.get("max_entry_age_sec", 3 * cs.TIMEFRAME_SECONDS["5m"])
    events = cs._diff_leg(leg_key, trades, leg_state_copy, now_et, max_entry_age_sec=max_age,
                          bar_source=bar_source, cfg=cfg, arrays=arrays, log=log)
    return events, leg_state_copy


# ── comparing two decisions ──────────────────────────────────────────────────────────────
def _canonical_events(events):
    """The decision-relevant fields of an event list, order-preserved -- deliberately
    excludes `emitted_at`/`bar_source` (which always differ between the two sides by
    construction) and `reason` (prose, not decision-bearing)."""
    return [tuple(e.get(f) for f in _DECISION_FIELDS) for e in (events or [])]


def compare_decisions(stream_events, rest_events):
    """(match, detail). `detail` is always a short, loggable string."""
    a, b = _canonical_events(stream_events), _canonical_events(rest_events)
    if a == b:
        return True, f"same decision ({len(a)} event(s))"
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


def record_shadow_decision(paths, leg_key, bar_epoch, events, bar, baseline_leg_state,
                           now_epoch, committed_live, log=print):
    shadow = _load_shadow(paths)
    shadow.setdefault(leg_key, {})[str(bar_epoch)] = {
        "events": events, "bar": bar, "baseline_leg_state": baseline_leg_state,
        "decided_epoch": now_epoch,
        "decided_at": _dt.datetime.fromtimestamp(now_epoch, tz=cs._zi(cs.TZ)).isoformat(),
        "committed_live": bool(committed_live),
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
def _handle_handoff_window(now, five_m_legs, paths, stream_cfg, log):
    """Runs only inside the ~1 minute after a 5m boundary. Reads the hand-off file
    once; if it clears every safety gate, computes (and records) each 5m leg's
    stream-implied decision, and -- only when the owner switch is on AND that leg's
    disagreement latch is not tripped for today -- commits it for real."""
    payload = read_closed_bar_handoff("5m", home=paths.get("home"))
    ok, reason = stream_bar_is_usable(payload, now)
    if not ok:
        return
    bar = {k: payload[k] for k in ("time", "open", "high", "low", "close", "volume")}
    bar_epoch = int(bar["time"])
    rest_df = cs.load_cached_bars("5m", paths)
    augmented = _augment_with_stream_bar(rest_df, bar)
    effective_now = _effective_now_for_bar(bar_epoch + cs.TIMEFRAME_SECONDS["5m"],
                                           cs.CLOSE_GRACE_SECONDS)
    today = now.date().isoformat()
    want_live = bool(stream_cfg.get("bar_close_from_stream"))

    state = None
    state_changed = False
    for leg_key, cfg in five_m_legs.items():
        if already_shadowed(paths, leg_key, bar_epoch):
            continue
        if state is None:
            state = cs._load_state(paths)
            state.setdefault("legs", {})
        leg_state = state["legs"].setdefault(leg_key, {"trades": {}})
        if leg_state.get("last_bar_epoch") == bar_epoch:
            continue   # this leg already has a real decision for this bar
        baseline = copy.deepcopy(leg_state)
        events, mutated = _dry_run_decision(leg_key, cfg, augmented, effective_now, leg_state,
                                            "stream", log)
        if events is None:
            continue
        committed = False
        if want_live and not _is_disagreement_tripped(paths, leg_key, today):
            mutated["last_bar_epoch"] = bar_epoch
            state["legs"][leg_key] = mutated
            cs._append_signals(events, paths)
            state_changed = True
            committed = True
            log(f"[cloud-signal-stream] LIVE from the stream: {leg_key} @ {bar_epoch} -- "
               f"{len(events)} event(s), bar_source=stream")
        elif want_live:
            log(f"[cloud-signal-stream] {leg_key}: stream decision computed but not fired "
               f"live -- disagreement latch tripped today ({today})")
        record_shadow_decision(paths, leg_key, bar_epoch, events, bar, baseline,
                               now.timestamp(), committed, log=log)
        log(f"[cloud-signal-stream] shadow: {leg_key} stream decision @ {bar_epoch} -> "
           f"{len(events)} event(s)")
    if state_changed:
        state["generated_at"] = now.isoformat()
        cs._write_state(state, paths)


def _resolve_pending_against_rest(now, five_m_legs, paths, log):
    """Runs every tick (not just inside the hand-off window -- REST typically lands
    ~30s after close, which is often just past it). For each leg with a pending shadow
    decision whose bar has now appeared in the REST-fed on-disk cache, computes the
    REST-implied decision from the SAME frozen baseline state and compares."""
    shadow = _load_shadow(paths)
    pending_legs = [k for k in shadow if k in five_m_legs]
    if not pending_legs:
        return
    rest_df = cs.load_cached_bars("5m", paths)
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
                                               rec["baseline_leg_state"], "webull", log)
            rest_events = rest_events or []
            match, detail = compare_decisions(rec["events"], rest_events)
            close_epoch = bar_epoch + cs.TIMEFRAME_SECONDS["5m"]
            stream_latency = max(0.0, rec["decided_epoch"] - close_epoch)
            rest_latency = max(0.0, now.timestamp() - close_epoch)
            if match:
                log(f"[cloud-signal-stream] shadow MATCH {leg_key} @ {bar_epoch}: stream and "
                   f"REST agree ({detail}); stream saw it {stream_latency:.1f}s after close vs "
                   f"REST's {rest_latency:.1f}s (~{max(0.0, rest_latency - stream_latency):.1f}s saved)")
            else:
                log(f"[cloud-signal-stream] STREAM/REST DISAGREEMENT {leg_key} @ {bar_epoch}: "
                   f"{detail}; ohlc_diff(stream-rest)={_ohlc_diff(rec['bar'], rest_bar)}")
                if rec.get("committed_live"):
                    _trip_disagreement(shadow, leg_key, now.date().isoformat(), bar_epoch, now, log)
            del pending[bar_epoch_str]
            changed = True
        if pending:
            shadow[leg_key] = pending
        else:
            shadow.pop(leg_key, None)
    if changed:
        _save_shadow(shadow, paths)


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
    five_m_legs = {k: v for k, v in legs.items() if v.get("timeframe") == "5m"}

    try:
        if five_m_legs:
            stream_cfg = load_stream_config(paths, log=log)
            if in_handoff_window(now):
                _handle_handoff_window(now, five_m_legs, paths, stream_cfg, log)
            _resolve_pending_against_rest(now, five_m_legs, paths, log)
    except Exception as e:
        log(f"[cloud-signal-stream] stream extras failed (classic step() still runs): "
           f"{type(e).__name__}: {e}")

    return cs.step(now=now, legs=legs, paths=paths, fetch=fetch, warnings=warnings)
