"""tools/keel_live_state.py -- builds and saves the KEEL v12 live-scoring STATE for
EVERY learned-KEEL leg of the Webull paper book: the live NOISE_382 leg (OWNER DECISION
2026-09-23: put KEEL v12 on top of the live Webull NOISE leg, "train it on the NQ backtest
like the validation") and, since 2026-09-28, the NOISE_422_KEEL shadow leg. See
augur_engine/ml_keel.py's keel_build_state / keel_score_from_state docstrings for the
build-once/score-many split this script and api/cloud_signal.py both use.

WHICH LEGS (2026-09-28, the shadow legs; 2026-10-09, DIP #424). This script used to carry
run #382's strategy file and cell as its own literals. It now reads every leg from
api/cloud_signal.py's CROWN_LEGS and SHADOW_LEGS: by default (the box's nightly unit,
deploy/cloud/edgelog-keel-state.service, passes no --leg) it builds EVERY leg whose "keel"
block is a learned model -- live legs first (NOISE_382), then shadow legs in SHADOW_LEGS
order (NOISE_422_KEEL, DIP_424K) -- each under its own <LEG>_<version>_* names (so
NOISE_382's files are exactly what they always were). A leg with a mode="fixed" block (v12's
fixed tilts, no model -- NOISE_422_FIXED), a mode="const" block (one constant size, no model
-- DIP_424F at 1.245) or no "keel" block (NOISE_422_PLAIN, ORB_R6, ENGUQ_335) has nothing to
build. A shadow leg's build failing never fails the run (the live legs' states are what
trade; the shadow leg just scores 1.0 until its next good build); a live leg's failure does,
after every other leg has still been tried. --leg picks one learned leg explicitly. Zero
learned legs is loud (LegResolutionError) unless every KEEL leg is fixed or constant
(NothingToBuild, exit 0). What stays literal here is what every NOISE KEEL leg shares and
neither dict carries: instrument NQ, timeframe 5m, source db_noadj_rth, date_from 2010-06-07
(the #304 crown's own start, used by runs #382 and #422 alike), cost_pts 0.533 (the house NQ
cost -- both size-tilt files refuse any other), multiplier 20.0 (irrelevant here -- KEEL
works in raw points/pnl units, never dollars). No Firestore dependency at build time -- the
box that runs this nightly may have no credentials on it at all. The first three are also
what load_nq_arrays writes into the arrays' meta (NQ_MASTER_META, main's ENGINE ROLL GUARD).

PER-LEG TRAINING SETTINGS (2026-10-09, DIP #424, MANAGER #108). A learned leg whose "keel"
block carries a "train" dict trains on ITS OWN run's NQ walk instead of the literals above:
  train["params"]     replace the leg's LIVE params for the NQ backtest. DIP_424K: run #424's
                      champion with NO asset key, so NQDIP_1_1.py's auto mode picks its NQ
                      cost and roll-seam model on the 5m master -- while the live QQQ leg runs
                      the same cell with asset="ETF".
  train["cost_pts"]   replaces the house 0.533. 0.0 for #424: the file charges its own costs,
                      and its P&L is in DOLLARS (the file's PNL_UNITS = "usd"; the summary then
                      records pnl_units "usd"). KEEL's walk is scale-free in P&L units.
  train["date_from"]  replaces 2010-06-07 (also 2010-06-07 for #424).
Same NQ master for every leg (#424's db_noadj_rth source is this NOADJ_NQ_5m_RTH.csv); it is
read once per distinct date_from -- once a night today. A leg with no "train" block (every
NOISE leg) builds exactly as before; its summary carries the same cost_pts/date_from values
it always did. A "train" block this script cannot read drops a SHADOW leg with a log line (the
live legs still build) and stays loud on a live one, like an unknown mode.

date_to is DELIBERATELY NOT pinned to a run's own snapshot (run #382's was 2026-07-16) --
it floats to the newest COMPLETE session in whatever NQ file this is pointed at, so
re-running this nightly keeps training the walk forward. "Complete" means a full RTH
session (FULL_SESSION_BARS 5-minute bars); the master file is updated intraday, so its
very last day is usually a partial session and is dropped before the backtest ever sees
it (design doc A: "drop any INCOMPLETE last session"). The master is read and hashed ONCE
per run and shared by every leg's build.

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

  --leg KEY         build (or check) only this learned-KEEL leg (a CROWN_LEGS or
                     SHADOW_LEGS key, e.g. NOISE_382 or NOISE_422_KEEL) -- see WHICH LEGS.
  --check-run-doc   READ-ONLY reproduction check, never writes. For a leg whose run doc
                     stores a gate_validate.keel row (run #382 for NOISE_382), read it from
                     Firestore and report whether re-running the walk over the RUN'S OWN
                     PINNED WINDOW (not this script's own open-ended build) reproduces its
                     trade count / total P&L. Skips quietly if firebase_admin or
                     serviceAccount.json are unavailable. When there is no stored row to
                     compare against (NOISE_422_KEEL: run #422 saved none), or the doc check
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
                                     members + ledgers), e.g. NOISE_382_v12_state.joblib,
                                     NOISE_422_KEEL_v12_state.joblib.
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
  nq_stale_alert.json             -- the NQ FRESHNESS check's marker: which day the
                                     master is behind on, and whether its last day
                                     was incomplete (see check_nq_freshness) -- what
                                     the box monitor tools/webull_freshness.py reads
                                     for its nq_master note; removed again once the
                                     data is current.

NQ FRESHNESS ALERT (2026-10-05). The PC's nightly push (tools/push_nq_master_to_box.py)
failed 09-30, 10-01 and 10-03 and did not run 10-02, so the box's master stayed at 09-29 and
this script rebuilt KEEL on stale data every night without a word. Every run that loads
the master now compares the newest COMPLETE NQ session in it with the last completed
trading day (api/market_calendar, counting a session as completed STALE_AFTER_CLOSE_MIN
after its close -- the push lands ~17:20 ET). Behind: one log line every run and the marker
above. Never fails the build -- KEEL still trains on what it has.

NO PUSH FROM HERE (WEBULL PUSH PLAN 10-07, MANAGER #86, section 3: "NQ data did not reach the
box" has ONE owner). The box monitor tools/webull_freshness.py (its nq_master check, from
18:00 ET -- before this 18:30 ET build, so a hand re-run of the upload can still land) is the
one pusher: it runs every 2 minutes around the clock, keeps a persisted outbox and pushes once
per episode. This script's one unique view -- "the last day in the file is INCOMPLETE" (a
cut-short upload passes the monitor's newest-bar test) -- reaches the owner through the marker:
the monitor reads nq_stale_alert.json and names the incomplete day in its note. Until 10-08
this pushed "QQQ book: needs a fix" itself, once per stale trading day.
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
# ENGINE ROLL GUARD (main 17279c26, augur_engine/rolls.py). What the NQ master IS, said in the
# arrays' meta. With no instrument there the engine runs a walk "not roll-checked" and
# rolls.seam_days answers [] -- so NQDIP_1_1.py's NQ model (DIP_424K's walk) skips no roll
# session and books every quarterly roll gap as P&L (3,503 trades on the 2026-10-09 master;
# 3,459 declared). Declared, this script stays what rolls.REPORT_ONLY_TOOLS makes it (raw
# prices, never refused or re-planned -- MANAGER D2), and a file that asks for the seam
# calendar gets the roll table's true switch sessions. The NOISE files never ask: their walks
# are identical either way (4,873 trades each on the same master).
NQ_MASTER_META = {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_noadj_rth"}

# --check-run-doc: the run whose Firestore doc a leg's stored gate_validate.keel row lives
# on. Run #422 (the NOISE_422_KEEL shadow leg's) is listed too although it saved no KEEL row
# today -- the check then says so and falls back to --verify-walk. DIP_424K is deliberately
# NOT listed: run #424's stored KEEL row came from an older (09-24) master build and does not
# reproduce on today's file (trade count matches, size-weighted total -4.3% -- "a figure, not a
# parity target", keel_decomp_424.json), so --check-run-doc goes straight to --verify-walk.
RUN_ID_FOR_LEG = {"NOISE_382": 382, "NOISE_422_KEEL": 422}
UID_FOR_CHECK = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


class LegResolutionError(RuntimeError):
    """No KEEL leg to build, or a KEEL block this script cannot read -- see resolve_legs /
    resolve_leg. main() turns it into a SystemExit with the message, so the nightly unit
    fails loudly instead of building a guess."""


class NothingToBuild(Exception):
    """Every KEEL leg uses v12's FIXED tilts (a "keel" block with mode="fixed") or a
    CONSTANT size (mode="const"), see api/cloud_signal.py's FOUR SHAPES comment: no model,
    so no state to build. Not a failure -- main() prints the message and exits 0, so the
    box's nightly edgelog-keel-state.service/.path stay green. Kept apart from
    LegResolutionError on purpose: that one must stay loud."""


def _leg_rows(crown_legs=None, shadow_legs=None):
    """[(key, cfg, live)] over api/cloud_signal.CROWN_LEGS (live=True) then SHADOW_LEGS
    (live=False), in that order. The arguments are for tests; None reads the real dicts."""
    from api import cloud_signal as _cs
    crown_legs = _cs.CROWN_LEGS if crown_legs is None else crown_legs
    shadow_legs = getattr(_cs, "SHADOW_LEGS", {}) if shadow_legs is None else shadow_legs
    return ([(k, cfg, True) for k, cfg in crown_legs.items()]
            + [(k, cfg, False) for k, cfg in shadow_legs.items() if k not in crown_legs])


def _leg_from_cfg(leg_key, cfg, live):
    """resolve_leg()'s dict for one learned leg: {"leg_key", "strategy", "params", "version",
    "live"} -- plus "cost_pts" and "date_from" ONLY when its keel block carries a "train"
    dict (see PER-LEG TRAINING SETTINGS), whose "params" then replace the live ones. A leg
    without "train" gets exactly the dict it always did."""
    from api import cloud_signal as _cs
    keel = (cfg or {}).get("keel")
    if not keel:
        raise LegResolutionError(
            f"leg {leg_key!r} carries no \"keel\" block -- there is no KEEL state to build for it")
    if _cs.keel_mode(keel) != _cs.KEEL_MODE_LEARNED:
        raise LegResolutionError(
            f"leg {leg_key!r} uses keel mode {_cs.keel_mode(keel)!r}, not a learned model -- "
            "there is no KEEL state to build for it")
    strategy = cfg.get("strategy")
    if not isinstance(strategy, str) or not strategy:
        raise LegResolutionError(f"leg {leg_key!r} names no strategy file")
    leg = {"leg_key": leg_key, "strategy": strategy, "params": dict(cfg.get("params") or {}),
           "version": keel.get("version") or VERSION, "live": bool(live)}
    train = keel.get("train")
    if train is None:
        return leg
    try:
        if not isinstance(train, dict) or not isinstance(train.get("params"), dict):
            raise TypeError("it must be a dict with a \"params\" dict")
        cost_pts = float(train["cost_pts"]) if train.get("cost_pts") is not None else COST_PTS
        if cost_pts != cost_pts or cost_pts < 0:
            raise ValueError(f"cost_pts {train.get('cost_pts')!r} is not a cost")
        date_from = str(train.get("date_from") or DATE_FROM)
        import datetime as _dt2
        _dt2.date.fromisoformat(date_from)
    except (TypeError, ValueError) as e:
        raise LegResolutionError(f"leg {leg_key!r}: its keel \"train\" block is unreadable ({e})")
    leg.update(params=dict(train["params"]), cost_pts=cost_pts, date_from=date_from)
    return leg


def _no_model_modes(_cs):
    """The keel modes with nothing to build: (v12's fixed tilts, a constant size)."""
    return (_cs.KEEL_MODE_FIXED, _cs.KEEL_MODE_CONST)


def resolve_legs(crown_legs=None, shadow_legs=None):
    """EVERY learned-KEEL leg to build (the nightly default), live legs first: a list of
    _leg_from_cfg() dicts (live = a CROWN_LEGS leg, False for a SHADOW_LEGS one). Fixed-tilt,
    constant-size and no-KEEL legs are skipped (nothing to build). An unknown mode -- or an
    unreadable "train" block -- on a LIVE leg raises LegResolutionError; on a SHADOW leg only,
    that leg is logged and dropped so the live build still runs (a shadow slip must never
    block the live state). No learned leg at all raises NothingToBuild when some KEEL leg is
    fixed or constant, else LegResolutionError ("found 0") -- never a silent empty run."""
    from api import cloud_signal as _cs
    rows = _leg_rows(crown_legs, shadow_legs)
    modes = {k: _cs.keel_mode((cfg or {}).get("keel")) for k, cfg, _live in rows
             if (cfg or {}).get("keel")}
    known = (_cs.KEEL_MODE_LEARNED,) + _no_model_modes(_cs)
    expected = ", ".join(repr(m) for m in known[:-1]) + f" or {known[-1]!r}"
    odd = {k: m for k, m in modes.items() if m not in known}
    live_keys = {k for k, _cfg, live in rows if live}
    odd_live = {k: m for k, m in odd.items() if k in live_keys}
    if odd_live:
        raise LegResolutionError(
            f"unknown keel mode on {odd_live} in api/cloud_signal (expected "
            f"{expected}). Nothing built.")
    if odd:
        print(f"[keel-live-state] shadow leg(s) with an unknown keel mode skipped: {odd} "
              f"(expected {expected}) -- the live legs still build")
    out = []
    for k, cfg, live in rows:
        if modes.get(k) != _cs.KEEL_MODE_LEARNED:
            continue
        try:
            out.append(_leg_from_cfg(k, cfg, live))
        except LegResolutionError as e:
            if live:
                raise
            print(f"[keel-live-state] shadow leg {k} skipped: {e} -- the live legs still build")
    if out:
        return out
    fixed_mode, const_mode = _no_model_modes(_cs)
    fixed_keys = sorted(k for k, m in modes.items() if m == fixed_mode)
    const_keys = sorted(k for k, m in modes.items() if m == const_mode)
    if fixed_keys or const_keys:
        why = ([f"KEEL leg(s) {', '.join(fixed_keys)} use v12's fixed tilts (no model)"]
               if fixed_keys else [])
        why += ([f"KEEL leg(s) {', '.join(const_keys)} use a constant size (no model)"]
                if const_keys else [])
        raise NothingToBuild("; ".join(why) + " -- nothing to build")
    raise LegResolutionError(
        "expected at least one leg with a learned \"keel\" block in api/cloud_signal, "
        f"found 0 (of {sorted(k for k, _c, _l in rows)}). Nothing built.")


def resolve_leg(leg_key=None, crown_legs=None, shadow_legs=None):
    """ONE learned-KEEL leg: `leg_key` names it (a CROWN_LEGS or SHADOW_LEGS key); None
    means THE live KEEL leg -- the one CROWN_LEGS leg with a learned "keel" block
    (NOISE_382) -- and raises LegResolutionError when there is none or several. Used by
    --leg and as build()'s default."""
    from api import cloud_signal as _cs
    rows = _leg_rows(crown_legs, shadow_legs)
    if leg_key is None:
        live = [k for k, cfg, is_live in rows if is_live
                and _cs.keel_mode((cfg or {}).get("keel")) == _cs.KEEL_MODE_LEARNED]
        if len(live) != 1:
            raise LegResolutionError(
                "expected exactly ONE live leg with a learned \"keel\" block in "
                f"api/cloud_signal.CROWN_LEGS, found {len(live)}: {live or 'none'}. Pass --leg.")
        leg_key = live[0]
    for k, cfg, live in rows:
        if k == leg_key:
            return _leg_from_cfg(k, cfg, live)
    raise LegResolutionError(
        f"unknown leg {leg_key!r}: not in api/cloud_signal.CROWN_LEGS or SHADOW_LEGS "
        f"({sorted(k for k, _c, _l in rows)})")


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


# -- NQ FRESHNESS ALERT (2026-10-05) -- see the module docstring --------------------------
STALE_AFTER_CLOSE_MIN = 120          # 16:00 close + 2h = 18:00 ET, after the 17:20 ET push
STALE_MARKER = "nq_stale_alert.json"


def last_completed_session(now_et):
    """The newest trading day whose session counts as completed at `now_et` (an
    America/New_York-aware datetime): today once STALE_AFTER_CLOSE_MIN have passed since
    its close (13:00 on a recognised half day), else the trading day before. Pure."""
    import datetime as _dt2
    from api import market_calendar as _mc
    d = now_et.date()
    if _mc.is_session(d):
        hh, mm = (int(x) for x in _mc.session_close_et(d).split(":"))
        cutoff = (now_et.replace(hour=hh, minute=mm, second=0, microsecond=0)
                  + _dt2.timedelta(minutes=STALE_AFTER_CLOSE_MIN))
        if now_et >= cutoff:
            return d
    d -= _dt2.timedelta(days=1)
    while not _mc.is_session(d):
        d -= _dt2.timedelta(days=1)
    return d


def check_nq_freshness(master, out_dir, nq_file=None, now_et=None, log=print):
    """NQ FRESHNESS CHECK: is the newest complete session in `master` (a load_master()
    dict) at least the last completed trading day? Logs a line every stale run and writes
    the marker (out_dir/STALE_MARKER: {"newest", "expected", "incomplete_day", "noted_at"})
    -- rewritten when the facts change, kept while they stand, removed once current. A last
    session the build dropped as incomplete counts as stale too -- KEEL then trains one day
    behind -- except on a recognised half day, whose shorter session this build always drops
    (that is the build's own rule, not a missing upload). NO PUSH (WEBULL PUSH PLAN 10-07):
    tools/webull_freshness.py's nq_master check owns the phone and reads this marker.
    Returns {"stale", "newest", "expected", "incomplete_day", "noted"} ("noted": the marker
    was (re)written this run). Never raises."""
    out = {"stale": False, "newest": None, "expected": None, "incomplete_day": None,
           "noted": False}
    try:
        import pandas as pd
        from api import market_calendar as _mc
        now_et = now_et or _now_et()
        expected = last_completed_session(now_et)
        idx = pd.DatetimeIndex(master["arr"]["index"])
        newest = idx[-1].date() if len(idx) else None
        dropped = master.get("dropped_session")
        out["newest"] = newest.isoformat() if newest else None
        out["expected"] = expected.isoformat()
        marker = os.path.join(out_dir, STALE_MARKER)
        half_day_dropped = (dropped == expected.isoformat()
                            and _mc.session_close_et(expected) != "16:00")
        if (newest is not None and newest >= expected) or half_day_dropped:
            if os.path.exists(marker):
                os.remove(marker)
                log(f"[keel-live-state] NQ data current again (through {out['newest']}, "
                    f"last completed trading day {out['expected']})")
            return out
        out["stale"] = True
        where = nq_file or "the NQ master"
        incomplete = dropped if dropped == expected.isoformat() else None
        out["incomplete_day"] = incomplete
        if incomplete:
            why = (f"its last session ({dropped}) is incomplete, so the newest complete one is "
                   f"{out['newest']}")
        else:
            why = f"its newest complete session is {out['newest']}"
        msg = (f"KEEL NQ data is STALE: {why}, but the last completed trading day is "
               f"{out['expected']}. The PC's nightly push to the box "
               "(tools/push_nq_master_to_box.py, 17:20 ET) did not land a current file -- "
               f"KEEL v12 is training on old data ({where}). No push from here: the box "
               "monitor's nq_master check owns it.")
        log(f"[keel-live-state] {msg}")
        key = {"newest": out["newest"], "expected": out["expected"], "incomplete_day": incomplete}
        prev = None
        try:
            with open(marker, encoding="utf-8") as f:
                prev = json.load(f)
        except (OSError, ValueError):
            prev = None
        if isinstance(prev, dict) and all(prev.get(k) == v for k, v in key.items()):
            log("[keel-live-state] (stale file already noted in the marker)")
            return out
        os.makedirs(out_dir, exist_ok=True)
        tmp = marker + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(key, noted_at=_dt_now_iso()), f)
        os.replace(tmp, marker)
        out["noted"] = True
    except Exception as e:
        log(f"[keel-live-state] NQ freshness check failed (non-fatal): {type(e).__name__}: {e}")
    return out


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


def _pnl_units(strategy):
    """The strategy file's own PNL_UNITS, lower-cased -- "points" unless the file declares
    otherwise (NQDIP_1_1.py: "usd") -- the same read augur_engine/book.py makes. "points"
    when the file cannot be loaded here (the backtest itself then fails, loudly)."""
    try:
        from augur_engine.strategies import load_strategy
        mod = load_strategy(strategy) if isinstance(strategy, str) else strategy
        return str(getattr(mod, "PNL_UNITS", "points") or "points").lower()
    except Exception:
        return "points"


def _leg_date_from(leg):
    """The first NQ date a leg trains on: its "train" date_from, else the shared DATE_FROM."""
    return (leg or {}).get("date_from") or DATE_FROM


def load_nq_arrays(nq_file, date_from=DATE_FROM, date_to=None, drop_incomplete=True, log=print):
    """Read `nq_file` the same way augur_engine.data.load_master_arrays does (epoch
    seconds -> ET tz-aware index, day_id factorized), without requiring it to sit in
    augur_uploads/ or be registered in optimizer_history.db -- neither is guaranteed on
    the box this runs on (a worktree has neither; the nightly Linux box may have neither
    either). The arrays' meta says what the master is (NQ_MASTER_META + its file name) --
    the engine roll guard reads it. Returns (arrays, dropped_session_date_or_None). When
    `drop_incomplete`, a final session with fewer than FULL_SESSION_BARS bars (the file is
    usually updated intraday, so "today" is normally partial) is removed before anything
    trains on it."""
    import augur_engine.data as _data
    nq_file = os.path.abspath(nq_file)
    master = dict(NQ_MASTER_META, filename=os.path.basename(nq_file))
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
    """The leg's NQ walk: its strategy with its (training) params at its own cost_pts -- the
    house COST_PTS unless the leg's "train" block names one (DIP_424K: 0.0, the file charges
    its own costs). The log names the P&L units (pts, or the file's own -- usd for DIP)."""
    leg = _as_leg(leg)
    from augur_engine.engine import run_backtest
    cost_pts = leg.get("cost_pts", COST_PTS)
    res = run_backtest(leg["strategy"], arrays=arr, params=leg["params"], cost_pts=cost_pts,
                       return_trades=True)
    trades = list((res or {}).get("trades") or [])
    units = _pnl_units(leg["strategy"])
    log(f"[keel-live-state] {leg['leg_key']}: {len(trades)} NQ trades, total_pnl "
        f"{(res or {}).get('total_pnl', 0):.2f} {'pts' if units == 'points' else units}"
        + ("" if "cost_pts" not in leg else f" (cost_pts {cost_pts:g}, from "
           f"{_leg_date_from(leg)})"))
    return trades, (res or {})


def load_master(nq_file, log=print, date_from=DATE_FROM):
    """The NQ master from `date_from` on, read and hashed ONCE for every leg a run builds
    that trains from that date (see build's `master`; main() keeps one per distinct
    date_from): {"arr", "dropped_session", "file_hash", "hash_s", "load_s", "date_from"}."""
    log(f"[keel-live-state] reading {nq_file}")
    t0 = time.time()
    file_hash = _file_sha256(nq_file)
    hash_s = time.time() - t0
    t0 = time.time()
    arr, dropped_session = load_nq_arrays(nq_file, date_from=date_from, log=log)
    load_s = time.time() - t0
    log(f"[keel-live-state] {len(arr['close'])} bars after load/trim ({load_s:.2f}s)")
    return {"arr": arr, "dropped_session": dropped_session, "file_hash": file_hash,
            "hash_s": hash_s, "load_s": load_s, "date_from": date_from}


def build(nq_file, out_dir, version=None, log=print, leg=None, master=None):
    """The nightly job for ONE leg. Returns (state, summary_dict); also writes both files.
    `leg`: a leg key, a resolve_leg() dict, or None for the live KEEL leg; `version` None
    uses that leg's own keel version. `master`: a load_master() dict to reuse (main()
    loads the NQ file once per distinct date_from); None reads `nq_file` here, from the
    leg's own date_from. A master read from another date_from is refused (ValueError)."""
    from augur_engine import ml_keel as K
    leg = _as_leg(leg)
    leg_key = leg["leg_key"]
    version = version or leg["version"]
    date_from = _leg_date_from(leg)
    log(f"[keel-live-state] leg {leg_key} ({leg['strategy']} {leg['params']}, KEEL {version}"
        f"{'' if leg['live'] else ', SHADOW leg -- scored by the shadow ledger only, never an order'})")

    t_start = time.time()
    if master is None:
        master = load_master(nq_file, log=log, date_from=date_from)
    elif (master.get("date_from") or DATE_FROM) != date_from:
        raise ValueError(f"{leg_key} trains from {date_from} but was handed a master read from "
                         f"{master.get('date_from') or DATE_FROM}")
    arr, dropped_session = master["arr"], master["dropped_session"]
    file_hash, hash_s, load_s = master["file_hash"], master["hash_s"], master["load_s"]
    n_bars = len(arr["close"])

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
    units = _pnl_units(leg["strategy"])
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
        # a SHADOW leg's summary says so; a live leg's (NOISE_382) carries no leg_live key,
        # as before
        **({} if leg["live"] else {"leg_live": False}),
        "strategy": leg["strategy"],
        "params": leg["params"],
        # the model's seed (ml_keel.SEED unless a caller passed another) -- read by the NOISE
        # forward log (api/noise_forward.py keel_meta), which never loads the state itself
        "seed": state.get("seed"),
        # the leg's own training cost / start (PER-LEG TRAINING SETTINGS) -- the house
        # literals for every NOISE leg, as before
        "cost_pts": leg.get("cost_pts", COST_PTS),
        "date_from": date_from,
        # a file whose P&L is not in points says so (DIP_424K: "usd"); NOISE summaries keep
        # exactly their old keys
        **({} if units == "points" else {"pnl_units": units}),
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
    stores no KEEL row to compare against -- NOISE_422_KEEL today. Re-runs the leg's NQ walk
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
        arrays, _dropped = load_nq_arrays(nq_file, date_from=_leg_date_from(leg), log=log)
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
                    help="build only this learned-KEEL leg (a CROWN_LEGS or SHADOW_LEGS key, "
                    "e.g. NOISE_382 or NOISE_422_KEEL; default: every learned-KEEL leg, live "
                    "legs first)")
    ap.add_argument("--version", default=None,
                    help="KEEL version (default: the leg's own keel version)")
    ap.add_argument("--check-run-doc", action="store_true",
                    help="also read (READ-ONLY) the leg's run's own gate_validate.keel row "
                    "from Firestore and report whether this walk reproduces it; with no row "
                    "to compare (NOISE_422_KEEL), runs --verify-walk instead")
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
        legs = [resolve_leg(a.leg)] if a.leg else resolve_legs()
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
        legs = [dict(leg, version=a.version) for leg in legs]
    print(f"[keel-live-state] building {len(legs)} leg(s): "
          + ", ".join(f"{leg['leg_key']} ({'live' if leg['live'] else 'shadow'})" for leg in legs))
    failed_live, failed_shadow = [], []
    # one master per distinct training start (PER-LEG TRAINING SETTINGS) -- every leg trains
    # from 2010-06-07 today, so still ONE read and ONE freshness check a night
    masters, freshness_checked = {}, False
    for leg in legs:
        # Re-check the blackout before EACH shadow leg: with two legs a build can start
        # just before 09:25 and run into the session, and a shadow leg's state must not
        # change mid-session either. The live legs are built first, as before.
        if a.defer_in_session and not leg["live"] and not a.no_build:
            now = _now_et()
            if should_defer_in_session(now):
                print(f"[keel-live-state] --defer-in-session: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                      f"is inside the trading session -- {leg['leg_key']} (shadow) deferred to "
                      "the 18:30 ET timer, not building now")
                continue
        try:
            if not a.no_build:
                date_from = _leg_date_from(leg)
                master = masters.get(date_from)
                if master is None:
                    master = masters[date_from] = load_master(nq_file, date_from=date_from)
                    if not freshness_checked:
                        freshness_checked = True
                        check_nq_freshness(master, out_dir, nq_file=nq_file)
                build(nq_file, out_dir, version=leg["version"], leg=leg, master=master)
            doc = check_against_run_doc(leg=leg) if a.check_run_doc else None
            if a.verify_walk or (a.check_run_doc and doc is None):
                r = check_state_matches_walk(nq_file, leg=leg, n_cuts=a.verify_cuts)
                if not r["ok"]:
                    raise RuntimeError(f"verify-walk FAILED: {r['mismatches'][:5]}")
        except Exception as e:
            # One leg's failure never stops the next leg's build (a shadow leg is built
            # AFTER every live one, and a live leg's state must not wait on it).
            (failed_live if leg["live"] else failed_shadow).append(leg["leg_key"])
            print(f"[keel-live-state] {leg['leg_key']} FAILED ({'live' if leg['live'] else 'shadow'} "
                  f"leg): {type(e).__name__}: {e}")
    if failed_shadow:
        print(f"[keel-live-state] shadow leg(s) not built this run: {', '.join(failed_shadow)} "
              "-- they score 1.0 until a later build succeeds; the live legs are unaffected")
    if failed_live:
        raise SystemExit(f"[keel-live-state] live leg(s) FAILED: {', '.join(failed_live)}")


if __name__ == "__main__":
    main()
