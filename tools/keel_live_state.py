"""tools/keel_live_state.py -- builds and saves the KEEL v12 live-scoring STATE for the
LIVE KEEL leg of the Webull paper book (OWNER DECISION 2026-09-23: put KEEL v12 on top of
the live Webull NOISE leg, "train it on the NQ backtest like the validation"). See
augur_engine/ml_keel.py's keel_build_state / keel_score_from_state docstrings for the
build-once/score-many split this script and api/cloud_signal.py both use.

WHICH LEG (2026-09-27, the NOISE #382 -> #422 swap). This script used to carry run #382's
strategy file and cell as its own literals. It now reads them from api/cloud_signal.py's
CROWN_LEGS: by default it builds the ONE leg whose cfg carries a "keel" block (NOISE_422
from the swap on; it was NOISE_382 before), and refuses -- a clear error, nothing written
-- when there is none or more than one, rather than guess. --leg picks one explicitly: a
CROWN_LEGS leg with a "keel" block, or a RETIRED KEEL leg (NOISE_382, see
_retired_keel_legs) so an old leg's state can still be rebuilt or checked by hand. So a
leg swap in CROWN_LEGS moves this nightly build with it and the box's systemd unit
(deploy/cloud/edgelog-keel-state.service, which passes no --leg) needs no edit. A leg
whose "keel" block is mode="fixed" (v12's fixed tilts, no model -- 2026-09-27) has nothing
to build: when that is the only KEEL leg the default run prints so and exits 0, so the
nightly unit stays green (see NothingToBuild). What
stays literal here is what every NOISE KEEL leg shares and CROWN_LEGS does not carry:
instrument NQ, timeframe 5m, source db_noadj_rth, date_from 2010-06-07 (the #304 crown's
own start, used by runs #382 and #422 alike), cost_pts 0.533 (the house NQ cost -- both
size-tilt files refuse any other), multiplier 20.0 (irrelevant here -- KEEL works in raw
points/pnl units, never dollars). No Firestore dependency at build time -- the box that
runs this nightly may have no credentials on it at all.

date_to is DELIBERATELY NOT pinned to a run's own snapshot (run #382's was 2026-07-16) --
it floats to the newest COMPLETE session in whatever NQ file this is pointed at, so
re-running this nightly keeps training the walk forward. "Complete" means a full RTH
session (FULL_SESSION_BARS 5-minute bars); the master file is updated intraday, so its
very last day is usually a partial session and is dropped before the backtest ever sees
it (design doc A: "drop any INCOMPLETE last session").

RUNS NIGHTLY ON THE LINUX BOX (owner: Python 3.12 there, sklearn 1.9.1, vs this PC's
3.13/older sklearn) -- joblib.dump of a fitted StandardScaler/LogisticRegression/
ExtraTreesRegressor is NOT a promise to unpickle cleanly across sklearn versions, so a
state file must never cross machines: build it on (or copy the whole repo + venv to) the
SAME host that will later call keel_score_from_state on it (api/cloud_signal.py, same
box). Give it the NQ master's path explicitly with --nq-file, since augur_uploads/ is a
Windows-dev convention this repo does not promise on every host.

USAGE
  python tools/keel_live_state.py \\
      --nq-file /path/to/NOADJ_NQ_5m_RTH.csv \\
      --out-dir /path/to/cloud_signal/keel
  (Windows dev/testing: both flags have defaults -- see _default_nq_file/_default_out_dir
  below -- so a bare `python tools/keel_live_state.py` works on the owner's PC too, for
  testing only; the shipped nightly invocation on the Linux box always passes --nq-file
  explicitly.)

  --leg KEY         build (or check) this leg instead of the live KEEL leg -- see WHICH
                     LEG above.
  --check-run-doc   READ-ONLY reproduction check, never writes. For a leg whose run doc
                     stores a gate_validate.keel row (run #382 for NOISE_382), read it from
                     Firestore and report whether re-running the walk over the RUN'S OWN
                     PINNED WINDOW (not this script's own open-ended build) reproduces its
                     trade count / total P&L. Skips quietly if firebase_admin or
                     serviceAccount.json are unavailable. When there is no stored row to
                     compare against (NOISE_422: run #422 saved none), or the doc check
                     skipped for any reason, it runs --verify-walk instead, so the flag
                     always checks something.
  --verify-walk     READ-ONLY, local, no Firestore: re-runs the leg's NQ walk and proves
                     keel_build_state + keel_score_from_state give keel_walk's own size at
                     a handful of cut points (--verify-cuts), to 1e-12 -- the same proof
                     tests/test_ml_keel_state.py makes on synthetic data, on the real tape.
                     Slow on the full history (one keel_walk plus one build per cut, a few
                     minutes each), so it is opt-in and never part of the nightly build.

WRITES under --out-dir (nothing else on the filesystem, no Firestore writes, no orders):
  <LEG>_<version>_state.joblib    -- keel_build_state()'s return dict (scaler + fitted
                                     members + ledgers), e.g. NOISE_422_v12_state.joblib.
                                     Only ever read by keel_score_from_state, on the SAME
                                     host that wrote it. The name is exactly what
                                     api/cloud_signal.keel_paths(<LEG>, <version>) reads.
  <LEG>_<version>_summary.json    -- keel_state_summary() plus build metadata
                                     (file hash, timings, dropped-session date,
                                     data_through -- the ET date of the last bar
                                     actually used, added 2026-09-25 item D, see
                                     `build`'s own comment for why this is NOT
                                     the same as keel_state_summary's own
                                     last_nq_session -- versions). Plain JSON --
                                     safe to read from any process/host as a
                                     status field.
"""
import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# -- what every NOISE KEEL leg shares, written out literally -- see module docstring ------
COST_PTS = 0.533                  # the house NQ cost; both NOISE size-tilt files refuse any other
DATE_FROM = "2010-06-07"          # the #304 crown's own start date (runs #382 and #422 alike);
                                  # date_to floats, see above
VERSION = "v12"                   # fallback only -- a CROWN_LEGS "keel" block names its own
FULL_SESSION_BARS = 78            # NQ 5m RTH, 09:30-16:00 ET = 6.5h * 12 bars/h

# --check-run-doc: the run whose Firestore doc a leg's stored gate_validate.keel row lives
# on. Run #422 is listed too although it saved no KEEL row today -- the check then says so
# and falls back to --verify-walk, and would compare for real if a row is ever backfilled.
RUN_ID_FOR_LEG = {"NOISE_382": 382, "NOISE_422": 422}
UID_FOR_CHECK = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


class LegResolutionError(RuntimeError):
    """No single KEEL leg to build -- see resolve_leg. main() turns it into a SystemExit
    with the message, so the nightly unit fails loudly instead of building a guess."""


class NothingToBuild(Exception):
    """The live KEEL leg(s) all use v12's FIXED tilts (a "keel" block with mode="fixed",
    see api/cloud_signal.py's THREE SHAPES comment): no model, so no state to build. Not
    a failure -- main() prints the message and exits 0, so the box's nightly
    edgelog-keel-state.service/.path stay green instead of failing every night. Kept
    apart from LegResolutionError on purpose: that one must stay loud."""


def _retired_keel_legs():
    """KEEL legs that have LEFT api/cloud_signal.CROWN_LEGS but can still be named with
    --leg -- to rebuild an old leg's state by hand or re-run its --check-run-doc against
    its own run. Same shape as a CROWN_LEGS entry. The live system never reads what a
    retired leg's build writes (CROWN_LEGS no longer names its files)."""
    from api import cloud_signal as _cs
    return {
        # the live Webull NOISE leg from 2026-09-24 until the #422 swap (OWNER DECISION
        # 2026-09-27); its cell is still importable from cloud_signal for exactly this.
        "NOISE_382": {"strategy": "NOISE_1_8_CT304.py", "timeframe": "5m",
                      "params": dict(_cs.NOISE_382_PARAMS), "keel": {"version": "v12"}},
    }


def resolve_leg(leg_key=None, crown_legs=None):
    """The KEEL leg to build: {"leg_key", "strategy", "params", "version", "live"}.

    leg_key None (the nightly default): the ONE api/cloud_signal.CROWN_LEGS leg whose cfg
    carries a "keel" block. Zero such legs (KEEL taken off the book) or several (two
    legs would need two builds, and a silent pick of one would leave the other stale)
    both raise LegResolutionError naming what it found -- never a guess.
    FIXED TILTS (2026-09-27): a mode="fixed" block has no model to build. When every KEEL
    leg is fixed this raises NothingToBuild (main() exits 0 with the message); fixed legs
    never count toward the one-leg rule above, and a block with an unknown mode is a
    LegResolutionError.
    leg_key given: that CROWN_LEGS leg (it must carry a learned "keel" block -- this
    script builds KEEL states and nothing else), or else a retired KEEL leg
    (_retired_keel_legs). `crown_legs` is for tests; None reads the real CROWN_LEGS."""
    from api import cloud_signal as _cs
    if crown_legs is None:
        crown_legs = _cs.CROWN_LEGS
    if leg_key is None:
        modes = {k: _cs.keel_mode(cfg.get("keel")) for k, cfg in crown_legs.items()
                 if (cfg or {}).get("keel")}
        odd = {k: m for k, m in modes.items() if m not in (_cs.KEEL_MODE_LEARNED, _cs.KEEL_MODE_FIXED)}
        if odd:
            raise LegResolutionError(
                f"unknown keel mode on {odd} in api/cloud_signal.CROWN_LEGS "
                f"(expected {_cs.KEEL_MODE_LEARNED!r} or {_cs.KEEL_MODE_FIXED!r}). Nothing built.")
        fixed_keys = sorted(k for k, m in modes.items() if m == _cs.KEEL_MODE_FIXED)
        keel_keys = [k for k, m in modes.items() if m == _cs.KEEL_MODE_LEARNED]
        if not keel_keys and fixed_keys:
            raise NothingToBuild(
                f"live KEEL leg {', '.join(fixed_keys)} uses v12's fixed tilts (no model) -- "
                "nothing to build")
        if len(keel_keys) != 1:
            raise LegResolutionError(
                "expected exactly ONE leg with a \"keel\" block in api/cloud_signal.CROWN_LEGS, "
                f"found {len(keel_keys)}: {keel_keys or 'none'} (of {sorted(crown_legs)}). "
                "Nothing built. Pass --leg to pick one by hand.")
        leg_key = keel_keys[0]
    cfg = crown_legs.get(leg_key)
    live = cfg is not None
    if cfg is None:
        cfg = _retired_keel_legs().get(leg_key)
    if cfg is None:
        raise LegResolutionError(
            f"unknown leg {leg_key!r}: not in api/cloud_signal.CROWN_LEGS ({sorted(crown_legs)}) "
            f"and not a retired KEEL leg ({sorted(_retired_keel_legs())})")
    keel = cfg.get("keel")
    if not keel:
        raise LegResolutionError(
            f"leg {leg_key!r} carries no \"keel\" block in api/cloud_signal.CROWN_LEGS -- "
            "there is no KEEL state to build for it")
    if _cs.keel_mode(keel) != _cs.KEEL_MODE_LEARNED:
        raise LegResolutionError(
            f"leg {leg_key!r} uses keel mode {_cs.keel_mode(keel)!r}, not a learned model -- "
            "there is no KEEL state to build for it")
    strategy = cfg.get("strategy")
    if not isinstance(strategy, str) or not strategy:
        raise LegResolutionError(f"leg {leg_key!r} names no strategy file")
    return {"leg_key": leg_key, "strategy": strategy, "params": dict(cfg.get("params") or {}),
            "version": keel.get("version") or VERSION, "live": live}


def _as_leg(leg):
    """resolve_leg()'s dict for `leg` -- a key, an already-resolved dict, or None (the
    live KEEL leg)."""
    return leg if isinstance(leg, dict) else resolve_leg(leg)


# DEFER-IN-SESSION (deadman/deadman_keel_guard, 2026-09-26). edgelog-keel-state.path
# (deploy/cloud/) rebuilds the moment a new NQ 5m RTH master lands -- see that unit's
# own comment, ITEM E. That is exactly right for a late push that lands OUTSIDE market
# hours, but a push that happens to land DURING the session (09:25-16:05 ET on a
# trading day) must NOT trigger a same-session rebuild: KEEL must never rebuild mid-
# session (the whole point of a build-once/score-many split -- see ml_keel.py's own
# docstring -- is that every entry within one session scores off the SAME state; a
# rebuild landing between two entries would silently change what "the state" means
# partway through the day). --defer-in-session makes this script a no-op (exit 0, one
# log line) when called inside that window; the existing 18:30 ET timer (well after the
# window, see edgelog-keel-state.timer) always builds regardless, since it never falls
# inside DEFER_START..DEFER_END.
DEFER_START = (9, 25)
DEFER_END = (16, 5)


def _now_et():
    import datetime as _dt2
    from zoneinfo import ZoneInfo
    return _dt2.datetime.now(ZoneInfo("America/New_York"))


def should_defer_in_session(now_et):
    """True when `now_et` (an America/New_York-aware datetime) falls inside the
    trading session's own KEEL-rebuild blackout window (DEFER_START..DEFER_END,
    inclusive) on a trading day -- see the DEFER-IN-SESSION comment above. Pure
    function of `now_et` alone so tests never need to patch the clock."""
    from api import market_calendar as _mc
    if not _mc.is_session(now_et.date()):
        return False
    hhmm = (now_et.hour, now_et.minute)
    return DEFER_START <= hhmm <= DEFER_END


def _default_nq_file():
    return os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")


def _default_out_dir():
    home = os.environ.get("EDGELOG_HOME") or (r"C:\EdgeLog" if os.name == "nt"
                                               else os.path.expanduser("~/edgelog"))
    return os.path.join(home, "cloud_signal", "keel")


def _file_sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _dt_now_iso():
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def load_nq_arrays(nq_file, date_from=DATE_FROM, date_to=None, drop_incomplete=True, log=print):
    """Read `nq_file` the same way augur_engine.data.load_master_arrays does (epoch
    seconds -> ET tz-aware index, day_id factorized), without requiring it to sit in
    augur_uploads/ or be registered in optimizer_history.db -- neither is guaranteed on
    the box this runs on (a worktree has neither; the nightly Linux box may have neither
    either). Returns (arrays, dropped_session_date_or_None). When `drop_incomplete`,
    a final session with fewer than FULL_SESSION_BARS bars (the file is usually updated
    intraday, so "today" is normally partial) is removed before anything trains on it."""
    import augur_engine.data as _data
    nq_file = os.path.abspath(nq_file)
    master = {"filename": os.path.basename(nq_file)}
    old_uploads = _data.UPLOADS
    _data.UPLOADS = os.path.dirname(nq_file)
    try:
        arr = _data.load_master_arrays(master, date_from=date_from, date_to=date_to)
    finally:
        _data.UPLOADS = old_uploads

    import numpy as np
    import pandas as pd
    day_id = arr.get("day_id")
    if not drop_incomplete or day_id is None or len(day_id) == 0:
        return arr, None
    last_day = day_id[-1]
    last_day_bars = int((day_id == last_day).sum())
    if last_day_bars >= FULL_SESSION_BARS:
        return arr, None
    idx = pd.DatetimeIndex(arr["index"])
    dropped_date = str(idx[-1].date())
    keep = day_id != last_day
    # Only the genuine per-bar arrays get the boolean mask -- augur_engine.data.
    # load_master_arrays also returns "meta" (dict) and "fingerprint" (str, a data-cache
    # key -- see its own docstring), neither of which is indexable by a per-bar mask;
    # anything not in this list passes through unchanged rather than raising, so a
    # future extra field degrades safely instead of crashing this drop-a-session step.
    PER_BAR_KEYS = {"open", "high", "low", "close", "volume", "day_id", "index"}
    arr = {k: (v[keep] if k in PER_BAR_KEYS else v) for k, v in arr.items()}
    log(f"[keel-live-state] dropped incomplete final session {dropped_date} "
       f"({last_day_bars} of {FULL_SESSION_BARS} bars) -- {int(keep.sum())} bars remain")
    return arr, dropped_date


def run_nq_backtest(arr, leg=None, log=print):
    leg = _as_leg(leg)
    from augur_engine.engine import run_backtest
    res = run_backtest(leg["strategy"], arrays=arr, params=leg["params"], cost_pts=COST_PTS,
                       return_trades=True)
    trades = list((res or {}).get("trades") or [])
    log(f"[keel-live-state] {leg['leg_key']}: {len(trades)} NQ trades, total_pnl "
        f"{(res or {}).get('total_pnl', 0):.2f} pts")
    return trades, (res or {})


def build(nq_file, out_dir, version=None, log=print, leg=None):
    """The nightly job. Returns (state, summary_dict); also writes both files. `leg`: a
    leg key, a resolve_leg() dict, or None for the live KEEL leg; `version` None uses
    that leg's own keel version."""
    from augur_engine import ml_keel as K
    leg = _as_leg(leg)
    leg_key = leg["leg_key"]
    version = version or leg["version"]
    log(f"[keel-live-state] leg {leg_key} ({leg['strategy']} {leg['params']}, KEEL {version}"
        f"{'' if leg['live'] else ', RETIRED leg -- the live book does not read this build'})")

    t_start = time.time()
    log(f"[keel-live-state] reading {nq_file}")
    t0 = time.time()
    file_hash = _file_sha256(nq_file)
    hash_s = time.time() - t0

    t0 = time.time()
    arr, dropped_session = load_nq_arrays(nq_file, log=log)
    load_s = time.time() - t0
    n_bars = len(arr["close"])
    log(f"[keel-live-state] {n_bars} bars after load/trim ({load_s:.2f}s)")

    t0 = time.time()
    trades, _res = run_nq_backtest(arr, leg=leg, log=log)
    backtest_s = time.time() - t0

    t0 = time.time()
    state = K.keel_build_state(arr, trades, version=version)
    build_s = time.time() - t0
    log(f"[keel-live-state] keel_build_state: n_fits={state['n_fits']} "
       f"fitted_on={state['fitted_on']} trust_now={state['trust_now']:.3f} "
       f"({build_s:.2f}s)")

    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, f"{leg_key}_{version}_state.joblib")
    summary_path = os.path.join(out_dir, f"{leg_key}_{version}_summary.json")

    import joblib
    t0 = time.time()
    # ATOMIC SWAP (2026-09-24): write both files beside their targets first and rename them
    # into place only once complete -- summary FIRST, state LAST -- because api/cloud_signal
    # reloads the state by its mtime and reads the summary at that moment. A rebuild during
    # market hours (owner 2026-09-24: train right up to the last session before go-live)
    # must never let a live entry read a half-written file or a new state with an old summary.
    state_tmp = state_path + ".tmp"
    joblib.dump(state, state_tmp)
    save_s = time.time() - t0

    total_s = time.time() - t_start
    # DATA_THROUGH (item D, 2026-09-25): the ET calendar date of the LAST BAR actually
    # used, i.e. AFTER load_nq_arrays already dropped an incomplete final session --
    # `arr` here is that post-drop array, so this is simply its last index entry.
    # Deliberately NOT the same thing as keel_state_summary's own "last_nq_session"
    # (the date of the last NQ TRADE the state was fitted on, computed from trade
    # bar indices, untouched by this change): on a quiet day with no trade at all,
    # last_nq_session stays behind even though the DATA (and therefore the state) is
    # fully current through today. See api/cloud_signal.py's staleness check and
    # api/qqq_exec.py's _build_keel_status, both updated to prefer this field.
    data_through = None
    try:
        import pandas as pd
        idx = pd.DatetimeIndex(arr["index"])
        if len(idx):
            data_through = str(idx[-1].date())
    except Exception as e:
        log(f"[keel-live-state] data_through unavailable: {type(e).__name__}: {e}")
    summary = K.keel_state_summary(state, arrays=arr, extra={
        "leg": leg_key,
        "leg_live": bool(leg["live"]),
        "strategy": leg["strategy"],
        "params": leg["params"],
        "cost_pts": COST_PTS,
        "date_from": DATE_FROM,
        "data_through": data_through,
        "dropped_incomplete_session": dropped_session,
        "nq_file": os.path.abspath(nq_file),
        "nq_file_sha256": file_hash,
        "nq_file_bars": n_bars,
        "built_at": _dt_now_iso(),
        "build_seconds": round(total_s, 2),
        "timings_seconds": {"hash": round(hash_s, 2), "load": round(load_s, 2),
                            "backtest": round(backtest_s, 2), "build_state": round(build_s, 2),
                            "save": round(save_s, 2)},
        "state_path": state_path,
    })
    summary_tmp = summary_path + ".tmp"
    with open(summary_tmp, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(summary_tmp, summary_path)
    os.replace(state_tmp, state_path)

    log(f"[keel-live-state] wrote {state_path}")
    log(f"[keel-live-state] wrote {summary_path}")
    log(f"[keel-live-state] TOTAL {total_s:.2f}s")
    return state, summary


def check_against_run_doc(run_id=None, leg=None, log=print):
    """READ-ONLY reproduction check: re-runs the leg's strategy + keel_walk over its run's
    OWN PINNED window (date_from/date_to read from the run doc, not this script's
    open-ended build) and compares trade count / total P&L against the doc's own stored
    gate_validate.keel row. `leg`: key, resolve_leg() dict or None (the live KEEL leg);
    `run_id` None uses RUN_ID_FOR_LEG. Never writes anything, to Firestore or otherwise.
    Returns None (and logs why) if the leg has no run to compare against, firebase_admin
    isn't installed, serviceAccount.json isn't on disk, or the doc stores no KEEL row
    (run #422's case) -- this is a courtesy diagnostic, never a build requirement; main()
    runs check_state_matches_walk instead whenever this returns None."""
    leg = _as_leg(leg)
    if run_id is None:
        run_id = RUN_ID_FOR_LEG.get(leg["leg_key"])
    if run_id is None:
        log(f"[keel-live-state] {leg['leg_key']}: no run doc to compare against -- skipping run-doc check")
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        log("[keel-live-state] firebase_admin not installed -- skipping run-doc check")
        return None
    cred_path = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred_path):
        log(f"[keel-live-state] {cred_path} not found -- skipping run-doc check "
           f"(expected: this only exists in the shared checkout, not a worktree)")
        return None
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
        db = firestore.client()
        ref = db.collection("users").document(UID_FOR_CHECK).collection("runs").document(str(run_id))
        d = ref.get().to_dict()
    except Exception as e:
        log(f"[keel-live-state] run-doc read failed ({type(e).__name__}: {e}) -- skipping check")
        return None
    if not d:
        log(f"[keel-live-state] run #{run_id}: no doc -- skipping check")
        return None
    keel_row = ((d.get("gate_validate") or {}).get("keel")) or {}
    if not isinstance(keel_row, dict) or not keel_row:
        log(f"[keel-live-state] run #{run_id}: no gate_validate.keel row on the doc -- skipping check")
        return None

    strat = d.get("strategy") or leg["strategy"]
    params = (d.get("validate") or {}).get("champion") or d.get("best_params") or leg["params"]
    cost_pts = float(d.get("cost_pts") if d.get("cost_pts") is not None else COST_PTS)
    date_from, date_to = d.get("date_from"), d.get("date_to")
    log(f"[keel-live-state] run #{run_id} pinned window: {strat} {date_from}..{date_to} "
       f"cost_pts={cost_pts} params={params}")

    nq_file = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(nq_file):
        log(f"[keel-live-state] {nq_file} not found -- skipping run-doc check")
        return None
    arr, _dropped = load_nq_arrays(nq_file, date_from=date_from, date_to=date_to,
                                   drop_incomplete=False, log=log)
    from augur_engine.engine import run_backtest
    from augur_engine import ml_keel as K
    res = run_backtest(strat, arrays=arr, params=params, cost_pts=cost_pts, return_trades=True)
    trades = list((res or {}).get("trades") or [])

    kw = K.keel_walk(arr, trades, version=keel_row.get("version") or leg["version"])
    import numpy as np
    tp = kw["P"] * kw["size"]
    n_trades = int(len(tp))
    total_pnl = float(tp.sum())
    doc_n = keel_row.get("n_trades")
    doc_full_pnl = (keel_row.get("full") or {}).get("total_pnl")
    n_match = doc_n is not None and int(doc_n) == n_trades
    pnl_match = (doc_full_pnl is not None
                and abs(total_pnl - float(doc_full_pnl)) <= 0.01 * max(1.0, abs(float(doc_full_pnl))))
    log(f"[keel-live-state] run #{run_id} reproduction: this walk n_trades={n_trades} "
       f"(doc n_trades={doc_n}) {'MATCH' if n_match else 'DIFFERS'}; "
       f"total_pnl(size-weighted)={total_pnl:.2f} (doc full.total_pnl={doc_full_pnl}) "
       f"{'within 1%' if pnl_match else 'DIFFERS'}")
    return {"n_trades_match": n_match, "total_pnl_within_1pct": pnl_match,
           "this_n_trades": n_trades, "doc_n_trades": doc_n,
           "this_total_pnl": total_pnl, "doc_total_pnl": doc_full_pnl}


def walk_cut_points(n, n_cuts=3):
    """Trade indices check_state_matches_walk scores: the last warm-up trade, the first
    trade KEEL sizes, the first refit, and `n_cuts` points spread evenly from there to the
    very last trade (always included -- it is the one the nightly state stands in for).
    Sorted, de-duplicated, all inside 0..n-1."""
    from augur_engine import ml_keel as K
    if n <= 0:
        return []
    first = K.MIN_HISTORY
    pts = {first - 1, first, first + K.REFIT_EVERY, n - 1}
    if n_cuts > 1 and n - 1 > first:
        step = (n - 1 - first) / float(n_cuts - 1)
        pts.update(int(round(first + i * step)) for i in range(n_cuts))
    return sorted(p for p in pts if 0 <= p < n)


def check_state_matches_walk(nq_file, leg=None, n_cuts=3, log=print, arrays=None, trades=None):
    """READ-ONLY, local (no Firestore): the reproduction check for a leg whose run doc
    stores no KEEL row to compare against -- NOISE_422 today. Re-runs the leg's NQ walk
    exactly as build() does (same load, same incomplete-session drop, same backtest), then
    at each walk_cut_points() index k builds keel_build_state from trades[:k] and scores
    trade k with keel_score_from_state(cross_series=False), and requires the result to
    equal keel_walk's own size[k] to 1e-12. That is the property the live overlay rests on
    (a live entry scored against the nightly state gets the size the validated walk would
    have given it), proved in tests/test_ml_keel_state.py on synthetic data; this runs it
    on the real tape for the leg actually traded. Writes nothing.

    Cost: one keel_walk over the whole history plus one keel_build_state per cut, each up
    to a few minutes on the full NQ tape -- opt-in only (--verify-walk, or
    --check-run-doc when the doc check has nothing to compare). `arrays`/`trades` let a
    test hand in a small series instead of reading `nq_file`.
    Returns {"leg", "n_trades", "cuts", "mismatches", "max_abs_diff", "ok"}."""
    import numpy as np
    from augur_engine import ml_keel as K
    leg = _as_leg(leg)
    version = leg["version"]
    if arrays is None:
        arrays, _dropped = load_nq_arrays(nq_file, log=log)
    if trades is None:
        trades, _res = run_nq_backtest(arrays, leg=leg, log=log)
    feats = K.keel_features(arrays)
    t0 = time.time()
    kw = K.keel_walk(arrays, trades, feats=feats, version=version)
    T = kw["trades"]
    n = len(T)
    log(f"[keel-live-state] verify-walk {leg['leg_key']}: keel_walk over {n} trades "
        f"({time.time() - t0:.1f}s)")
    cuts = walk_cut_points(n, n_cuts)
    mismatches, max_diff = [], 0.0
    for k in cuts:
        t0 = time.time()
        state = K.keel_build_state(arrays, T[:k], feats=feats, version=version)
        size, _diag = K.keel_score_from_state(state, arrays, int(T[k][0]), feats=feats,
                                              cross_series=False)
        true_size = float(kw["size"][k])
        diff = abs(float(size) - true_size)
        max_diff = max(max_diff, diff)
        ok_k = bool(np.isfinite(size)) and diff <= 1e-12
        if not ok_k:
            mismatches.append({"k": int(k), "state_size": float(size), "walk_size": true_size})
        log(f"[keel-live-state]   cut k={k}: state {size:.12f} vs walk {true_size:.12f} "
            f"{'MATCH' if ok_k else 'DIFFERS'} ({time.time() - t0:.1f}s)")
    ok = bool(cuts) and not mismatches
    log(f"[keel-live-state] verify-walk {leg['leg_key']}: {len(cuts)} cut points, "
        f"{len(mismatches)} mismatches, max |diff| {max_diff:.3g} -- {'PASS' if ok else 'FAIL'}")
    return {"leg": leg["leg_key"], "n_trades": n, "cuts": cuts, "mismatches": mismatches,
            "max_abs_diff": max_diff, "ok": ok}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nq-file", default=None, help="path to the NQ 5m RTH master CSV "
                    "(default: augur_uploads/NOADJ_NQ_5m_RTH.csv under this repo)")
    ap.add_argument("--out-dir", default=None, help="where to write the state + summary "
                    "(default: <EDGELOG_HOME>/cloud_signal/keel)")
    ap.add_argument("--leg", default=None,
                    help="engine leg key to build (default: the ONE api/cloud_signal.CROWN_LEGS "
                    "leg with a \"keel\" block; a retired KEEL leg such as NOISE_382 may be "
                    "named by hand)")
    ap.add_argument("--version", default=None,
                    help="KEEL version (default: the leg's own keel version)")
    ap.add_argument("--check-run-doc", action="store_true",
                    help="also read (READ-ONLY) the leg's run's own gate_validate.keel row "
                    "from Firestore and report whether this walk reproduces it; with no row "
                    "to compare (NOISE_422), runs --verify-walk instead")
    ap.add_argument("--verify-walk", action="store_true",
                    help="also prove (READ-ONLY, local) that the saved-state scoring gives "
                    "keel_walk's own size at --verify-cuts cut points; slow on full history")
    ap.add_argument("--verify-cuts", type=int, default=3,
                    help="evenly spread cut points for --verify-walk, on top of the fixed "
                    "warm-up/refit boundaries (default 3)")
    ap.add_argument("--no-build", action="store_true",
                    help="run the checks only; write no state or summary")
    ap.add_argument("--defer-in-session", action="store_true",
                    help="exit 0 without building (one log line) if now (ET) falls "
                    "inside a trading day's 09:25-16:05 rebuild blackout window -- see "
                    "the DEFER-IN-SESSION comment above should_defer_in_session; used by "
                    "deploy/cloud/edgelog-keel-state.service so edgelog-keel-state.path's "
                    "on-push rebuild never fires mid-session")
    a = ap.parse_args()

    if a.defer_in_session:
        now = _now_et()
        if should_defer_in_session(now):
            print(f"[keel-live-state] --defer-in-session: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                  f"is inside the trading session -- deferring to the 18:30 ET timer, not "
                  f"building now")
            return

    try:
        leg = resolve_leg(a.leg)
    except NothingToBuild as e:
        print(f"[keel-live-state] {e}. Exiting 0.")
        return
    except LegResolutionError as e:
        raise SystemExit(f"[keel-live-state] {e}")

    nq_file = a.nq_file or _default_nq_file()
    out_dir = a.out_dir or _default_out_dir()
    if not os.path.exists(nq_file):
        raise SystemExit(f"NQ master not found: {nq_file}")

    if a.version:
        leg = dict(leg, version=a.version)
    if not a.no_build:
        build(nq_file, out_dir, version=leg["version"], leg=leg)
    doc = check_against_run_doc(leg=leg) if a.check_run_doc else None
    if a.verify_walk or (a.check_run_doc and doc is None):
        r = check_state_matches_walk(nq_file, leg=leg, n_cuts=a.verify_cuts)
        if not r["ok"]:
            raise SystemExit(f"[keel-live-state] verify-walk FAILED for {leg['leg_key']}: "
                             f"{r['mismatches'][:5]}")


if __name__ == "__main__":
    main()
