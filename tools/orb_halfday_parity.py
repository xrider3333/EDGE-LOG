"""orb_halfday_parity.py -- WEBULL_PAPER_TODO.md item 15, parity replay.

Root cause (verified by the lead): augur_strategies/ORB_3_6.py's skip_holidays test
flags any session shorter than 70% of the trailing median as a half day. On the LIVE
engine the LAST session in its rolling window is today's own, still being built bar by
bar, so it reads as a false half day until nearly the close -- by which point a morning
entry has already aged past api/cloud_signal.py's 3-bar freshness window and is
silently dropped as "late" (box record: ORB_R6 fired once since 09-09, late_skipped 6).

THIS SCRIPT never touches the box or the live bar cache. It fetches ~60 days of QQQ 5m
RTH bars from yfinance (allowed by spec), writes them to a throwaway scratch home, and
replays the ORB_R6 leg bar-by-bar EXACTLY as api/cloud_signal.step() does (same rolling
warm-up window via leg_warmup_sessions(), same closed-bar cutoff, same 3-bar freshness
rule in _diff_leg) -- once with the fix disabled (monkeypatching
cs._leg_accepts_session_in_progress to always return False, reproducing the pre-fix
code path byte-for-byte since ORB_3_6.py's own default is also False) and once with it
enabled (today's shipped code, unmodified).

GROUND TRUTH: a single, ordinary (non-live, non-tick-by-tick) engine call over the
WHOLE fetched window -- exactly a real backtest -- naming every entry ORB #314 actually
takes. The first replayed session is a cold-start SEED by design (absorbs history
silently, see cloud_signal._diff_leg's own docstring) and is excluded from the
comparison; every ground-truth entry in the remaining sessions must appear as a live
ENTRY event, and no live ENTRY may appear that isn't in the ground truth.

Usage:  python tools/orb_halfday_parity.py
Output: a plain-text report to stdout (also written to the given --out path, default a
        scratch file in this repo's own %TEMP%, never anything under C:\\EdgeLog or the
        shared checkout).
"""
import argparse
import os
import sys
import tempfile
import warnings

# Harmless, expected, and extremely repetitive at a reduced --sessions count: ORB's own
# vpace_filter reference matrix is a 20-prior-session nanmean, so every early session in
# a short replay window has an all-NaN slice until 20 sessions of history accumulate.
# Silenced here only to keep this script's own console/log output readable -- it never
# touches any strategy file's actual arithmetic.
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

import api.cloud_signal as cs  # noqa: E402
import tools.qqq_paper as qp  # noqa: E402
from augur_engine.engine import run_backtest as engine_run_backtest  # noqa: E402


def _fetch_scratch_cache(scratch_home):
    """Pulls yfinance QQQ 5m 60d RTH bars and writes them as the epoch-schema cache
    cloud_signal reads, under `scratch_home` -- never C:\\EdgeLog, never the shared
    checkout."""
    raw = qp._fetch_yf("5m")
    if raw is None or not len(raw):
        raise SystemExit("yfinance returned no QQQ 5m bars -- check network access")
    epoch_df = qp._to_epoch_frame(raw)
    paths = cs._paths(home=scratch_home)
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(cs._cache_path("5m", paths), index=False)
    return paths, epoch_df


def _session_dates(epoch_df):
    dt = pd.to_datetime(epoch_df["time"], unit="s", utc=True).dt.tz_convert(cs.TZ)
    dates = sorted(set(dt.dt.date.tolist()))
    today = pd.Timestamp.now(tz=cs.TZ).date()
    return [d for d in dates if d != today]   # exclude an in-flight partial fetch day


def _ground_truth_entries(epoch_df, cfg, judged_dates):
    """One ordinary (non-live) engine call over the WHOLE window -- a real backtest,
    not a tick-by-tick replay -- naming every entry ORB #314 actually takes. Returns
    {(date, side): [entry_time_iso, ...]} restricted to `judged_dates` (everything
    strictly after the cold-start SEED day)."""
    arrays = qp.build_arrays(epoch_df)
    trades = cs.run_leg_trades(cfg, arrays, leg_key="ORB_R6_GROUND_TRUTH")
    out = {}
    for t in trades:
        d = pd.Timestamp(t["entry_time"]).date()
        if d not in judged_dates:
            continue
        out.setdefault(d, []).append((t["side"], t["entry_time"]))
    return out


def _run_replay(paths_source, legs, session_dates, apply_fix):
    """Replays every session in `session_dates`, IN ORDER, against one persistent
    isolated store -- exactly the continuous live engine, tick by tick. `apply_fix`
    False monkeypatches cs._leg_accepts_session_in_progress to always return False,
    reproducing the PRE-FIX code path (ORB_3_6.py's own session_in_progress default is
    also False, so this is the exact behaviour before this track's change existed)."""
    paths = cs.isolated_paths(legs, source_paths=paths_source)
    orig = cs._leg_accepts_session_in_progress
    if not apply_fix:
        cs._leg_accepts_session_in_progress = lambda strategy: False
    try:
        events = []
        for day in session_dates:
            events.extend(cs.replay(day, legs=legs, paths=paths))
        state = cs._load_state(paths)
        return events, state
    finally:
        cs._leg_accepts_session_in_progress = orig
        import shutil
        shutil.rmtree(paths["home"], ignore_errors=True)


def _compare(ground_truth, events):
    emitted_entries = {}
    for e in events:
        if e["leg"] != "ORB_R6" or e["event"] != "ENTRY":
            continue
        d = pd.Timestamp(e["ref_time"]).date()
        emitted_entries.setdefault(d, []).append((e["side"], e["ref_time"]))

    matched = missed = extra = 0
    missed_detail = []
    for d, gt_list in ground_truth.items():
        live_list = list(emitted_entries.get(d, []))
        for side, t in gt_list:
            if (side, t) in live_list:
                live_list.remove((side, t))
                matched += 1
            else:
                missed += 1
                missed_detail.append((d, side, t))
    for d, live_list in emitted_entries.items():
        gt_list = list(ground_truth.get(d, []))
        for side, t in live_list:
            if (side, t) not in gt_list:
                extra += 1
    return matched, missed, extra, missed_detail


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None, help="report file (default: scratch temp file)")
    ap.add_argument("--sessions", type=int, default=15,
                   help="how many of the most-recently-fetched sessions to actually "
                        "REPLAY tick-by-tick (default 15, not the full ~60 fetched -- "
                        "see SPEED note below); the full fetched window still backs the "
                        "engine's own rolling warm-up and the ground-truth backtest.")
    args = ap.parse_args()

    scratch_home = tempfile.mkdtemp(prefix="orb_halfday_parity_")
    print(f"[orb_halfday_parity] scratch home: {scratch_home}", flush=True)
    paths_source, epoch_df = _fetch_scratch_cache(scratch_home)

    all_session_dates = _session_dates(epoch_df)
    if len(all_session_dates) < 3:
        raise SystemExit(f"only {len(all_session_dates)} session(s) fetched -- need at least a "
                         f"few to replay anything meaningful")
    print(f"[orb_halfday_parity] {len(all_session_dates)} session(s) fetched "
         f"({all_session_dates[0]} .. {all_session_dates[-1]})", flush=True)

    # SPEED (see BACKTEST_SPEED.md): a tick-by-tick replay recomputes the FULL engine
    # over its whole rolling warm-up window on every closed 5m bar (~78 recomputes per
    # session) -- ~60 sessions x 2 runs (before/after) is the exact O(ticks) cost the
    # existing test suite's own TEST_WARMUP_SESSIONS/TEST_MAX_TICKS note warns about,
    # and this machine runs many concurrent backtests/validates. Replaying only the
    # most recent `--sessions` (default 15, ~2340 recomputes total) keeps this a
    # tractable local check while still exercising the exact mechanism end to end: the
    # fetched window still backs the ground-truth backtest AND every replayed session's
    # own rolling warm-up in full, so nothing about the window itself is narrowed --
    # only how many of the sessions we tick through twice.
    keep = min(len(all_session_dates), args.sessions + 1)
    session_dates = all_session_dates[-keep:]
    seed_day, judged_days = session_dates[0], session_dates[1:]

    legs = {"ORB_R6": dict(cs.CROWN_LEGS["ORB_R6"])}
    ground_truth = _ground_truth_entries(epoch_df, legs["ORB_R6"], set(judged_days))
    gt_total = sum(len(v) for v in ground_truth.values())

    lines = []
    lines.append(f"ORB half-day parity replay -- {len(session_dates)} session(s) fetched "
                f"({session_dates[0]} .. {session_dates[-1]})")
    lines.append(f"cold-start SEED day (excluded from comparison): {seed_day}")
    lines.append(f"judged sessions: {len(judged_days)}")
    lines.append(f"ground-truth ORB #314 entries in judged sessions: {gt_total}")
    lines.append("")

    for label, apply_fix in (("BEFORE (session_in_progress disabled)", False),
                             ("AFTER  (session_in_progress as shipped)", True)):
        print(f"[orb_halfday_parity] running {label} ...", flush=True)
        events, state = _run_replay(paths_source, legs, session_dates, apply_fix)
        matched, missed, extra, missed_detail = _compare(ground_truth, events)
        leg_state = state.get("legs", {}).get("ORB_R6", {})
        lines.append(f"-- {label} --")
        lines.append(f"  matched: {matched}/{gt_total}   missed: {missed}   extra: {extra}")
        lines.append(f"  late_skipped: {leg_state.get('late_skipped', 0)}   "
                     f"stale_skipped: {leg_state.get('stale_skipped', 0)}")
        if missed_detail:
            shown = missed_detail[:15]
            lines.append(f"  missed entries (first {len(shown)} of {len(missed_detail)}):")
            for d, side, t in shown:
                lines.append(f"    {d}  {side:<6} {t}")
        lines.append("")

    report = "\n".join(lines)
    print(report)

    out_path = args.out or os.path.join(tempfile.gettempdir(), "orb_halfday_parity_report.txt")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"[orb_halfday_parity] report written to {out_path}")

    import shutil
    shutil.rmtree(scratch_home, ignore_errors=True)


if __name__ == "__main__":
    main()
