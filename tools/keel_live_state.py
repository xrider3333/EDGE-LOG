"""tools/keel_live_state.py -- builds and saves the KEEL v12 live-scoring STATE for the
NOISE_382 leg (OWNER DECISION 2026-09-23: put KEEL v12 on top of run #382's live Webull
NOISE leg, "train it on the NQ backtest like the validation"). See
augur_engine/ml_keel.py's keel_build_state / keel_score_from_state docstrings for the
build-once/score-many split this script and api/cloud_signal.py both use.

TRAINING = run #382's OWN walk. NOISE_1_8_CT304.py's champion cell, read literally from
the run #382 Firestore doc on 2026-09-23 and written out below (STRATEGY_FILE /
STRATEGY_PARAMS / COST_PTS / DATE_FROM) so this script has NO Firestore dependency at
build time -- the box that runs this nightly may have no credentials on it at all. The
SAME literal values live in api/cloud_signal.py's CROWN_LEGS["NOISE_382"]["params"];
tests/test_keel_live_state.py asserts the two never drift apart. Per the run doc: strategy
NOISE_1_8_CT304.py, instrument NQ, timeframe 5m, source db_noadj_rth, date_from
2010-06-07, cost_pts 0.533, multiplier 20.0 (irrelevant here -- KEEL works in raw points/
pnl units, never dollars).

date_to is DELIBERATELY NOT pinned to the run's own snapshot (2026-07-16) -- it floats to
the newest COMPLETE session in whatever NQ file this is pointed at, so re-running this
nightly keeps training the walk forward. "Complete" means a full RTH session
(FULL_SESSION_BARS 5-minute bars); the master file is updated intraday, so its very last
day is usually a partial session and is dropped before the backtest ever sees it (design
doc A: "drop any INCOMPLETE last session").

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

  --check-run-doc   ALSO read (READ-ONLY; never writes) run #382's own doc from
                     Firestore and its stored gate_validate.keel row, and report whether
                     re-running the walk over the RUN'S OWN PINNED WINDOW (not this
                     script's own open-ended build) reproduces its trade count / total
                     P&L. Skips quietly if firebase_admin or serviceAccount.json are
                     unavailable -- a courtesy diagnostic, never required for the state
                     build itself to succeed.

WRITES under --out-dir (nothing else on the filesystem, no Firestore writes, no orders):
  NOISE_382_<version>_state.joblib    -- keel_build_state()'s return dict (scaler +
                                          fitted members + ledgers). Only ever read by
                                          keel_score_from_state, on the SAME host that
                                          wrote it.
  NOISE_382_<version>_summary.json    -- keel_state_summary() plus build metadata
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

# -- run #382's own facts, written out literally -- see module docstring ------------------
LEG_KEY = "NOISE_382"
STRATEGY_FILE = "NOISE_1_8_CT304.py"
STRATEGY_PARAMS = {"tilt_mult": 2.0, "gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15}
COST_PTS = 0.533
DATE_FROM = "2010-06-07"          # run #382's own start date; date_to floats, see above
VERSION = "v12"
FULL_SESSION_BARS = 78            # NQ 5m RTH, 09:30-16:00 ET = 6.5h * 12 bars/h

RUN_ID_FOR_CHECK = 382
UID_FOR_CHECK = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


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


def run_nq_backtest(arr, log=print):
    from augur_engine.engine import run_backtest
    res = run_backtest(STRATEGY_FILE, arrays=arr, params=STRATEGY_PARAMS, cost_pts=COST_PTS,
                       return_trades=True)
    trades = list((res or {}).get("trades") or [])
    log(f"[keel-live-state] {len(trades)} NQ trades, total_pnl {(res or {}).get('total_pnl', 0):.2f} "
       f"pts")
    return trades, (res or {})


def build(nq_file, out_dir, version=VERSION, log=print):
    """The nightly job. Returns (state, summary_dict); also writes both files."""
    from augur_engine import ml_keel as K

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
    trades, _res = run_nq_backtest(arr, log=log)
    backtest_s = time.time() - t0

    t0 = time.time()
    state = K.keel_build_state(arr, trades, version=version)
    build_s = time.time() - t0
    log(f"[keel-live-state] keel_build_state: n_fits={state['n_fits']} "
       f"fitted_on={state['fitted_on']} trust_now={state['trust_now']:.3f} "
       f"({build_s:.2f}s)")

    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, f"{LEG_KEY}_{version}_state.joblib")
    summary_path = os.path.join(out_dir, f"{LEG_KEY}_{version}_summary.json")

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
    # (the date of the last NQ #382 TRADE the state was fitted on, computed from trade
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
        "leg": LEG_KEY,
        "strategy": STRATEGY_FILE,
        "params": STRATEGY_PARAMS,
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


def check_against_run_doc(run_id=RUN_ID_FOR_CHECK, log=print):
    """READ-ONLY reproduction check: re-runs NOISE_1_8_CT304.py + keel_walk v12 over run
    #382's OWN PINNED window (date_from/date_to read from its doc, not this script's
    open-ended build) and compares trade count / total P&L against the doc's own stored
    gate_validate.keel row. Never writes anything, to Firestore or otherwise. Returns
    None (and logs why) if firebase_admin isn't installed or serviceAccount.json isn't
    on disk -- this is a courtesy diagnostic, never a build requirement."""
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

    strat = d.get("strategy") or STRATEGY_FILE
    params = (d.get("validate") or {}).get("champion") or d.get("best_params") or STRATEGY_PARAMS
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

    kw = K.keel_walk(arr, trades, version=keel_row.get("version") or VERSION)
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nq-file", default=None, help="path to the NQ 5m RTH master CSV "
                    "(default: augur_uploads/NOADJ_NQ_5m_RTH.csv under this repo)")
    ap.add_argument("--out-dir", default=None, help="where to write the state + summary "
                    "(default: <EDGELOG_HOME>/cloud_signal/keel)")
    ap.add_argument("--version", default=VERSION)
    ap.add_argument("--check-run-doc", action="store_true",
                    help="also read (READ-ONLY) run #382's own gate_validate.keel row "
                    "from Firestore and report whether this walk reproduces it")
    a = ap.parse_args()

    nq_file = a.nq_file or _default_nq_file()
    out_dir = a.out_dir or _default_out_dir()
    if not os.path.exists(nq_file):
        raise SystemExit(f"NQ master not found: {nq_file}")

    build(nq_file, out_dir, version=a.version)
    if a.check_run_doc:
        check_against_run_doc()


if __name__ == "__main__":
    main()
