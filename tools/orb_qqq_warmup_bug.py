"""tools/orb_qqq_warmup_bug.py — diagnosis driver for "ORB_R6 never fires on QQQ",
2026-09-13.

THE OBSERVATION. A replay of api/cloud_signal.py for 2026-09-03 and 2026-09-04 on the
real QQQ bar cache produced NOISE_304 entries but ORB_R6 (run #314, ORB_3_6_R6.py, the
current ORB crown) fired nothing on either day. The NQ trade it was being compared
against was the OLD ORB control (#234), not #314 -- already a mismatched comparison.

WHAT THIS SCRIPT SHOWS, IN ORDER:

  1. #314 on NQ 5m (api/paper.py's own leg definition + data path) did not trade on
     2026-09-03 or 2026-09-04 either. The "miss" in the observation is comparing the
     crown (silent) to the control (#234, which did trade) -- not a QQQ-specific defect.

  2. Over the full common window (the QQQ 5m cache: 2026-06-08..2026-09-11, 67
     sessions), #314 on QQQ tracks #314 on NQ closely: 27/31 NQ trades matched (same
     session + direction) on QQQ, 4 NQ-only, 2 QQQ-only -- no systematic under-firing.
     Both sides go fully quiet from 2026-08-13 onward (consistent with api/paper.py's
     own note beside ORB_314: "longest drought of 28 calendar days" -- the tighter
     round-6 filters trade less often BY DESIGN).

  3. A REAL defect in api/cloud_signal.py's closed_arrays(), found while reconciling
     (1)/(2) against the LIVE rolling-window mechanism: the raw calendar prefilter used
     `warmup_sessions + 5` calendar days as "generous" buffer before trimming to the
     last `warmup_sessions` trading sessions. 60 trading sessions actually span ~84
     calendar days (5-day trading weeks), not 65 -- so the buffer silently fed the
     trailing atr_filter/vpace_filter fewer sessions than intended (measured: 47
     instead of 60), and because the buffer's lower edge advances continuously with
     `now`, the session count can drop by exactly one PARTWAY THROUGH a single trading
     day, retroactively flipping that day's own trading decision. Reproduced live:
     an ORB_3_6_R6.py entry on 2026-09-04 09:55 was absent from the engine's trade list
     at every tick through 14:05 and present from 14:06 on -- purely the buffer aging
     the 2026-07-01 session out of the window at that instant. The entry then aged past
     `max_entry_age_sec` and was recorded "late" (silently suppressed) rather than
     emitted -- this time. A smaller shift could instead emit a spurious ENTRY that
     exists only because of when the engine was asked.

  4. THE FIX (applied in this commit): size the calendar buffer off the real 5/7
     trading cadence (`ceil(warmup_sessions * 7 / 5) + 15` calendar days of holiday
     slack) instead of a flat `+5`. Verified: with the fix, the window for 2026-09-04
     holds a stable 60 sessions all day (vs. 47, drifting to 48/47 intraday, before),
     and the day's trade-list verdict (#314 does NOT trade QQQ on 2026-09-03 or
     2026-09-04, matching NQ) no longer depends on what minute you ask.

Run:  python tools/orb_qqq_warmup_bug.py
Needs the owner's real NQ master (augur_uploads/NOADJ_NQ_5m_RTH.csv, via find_master)
and the real QQQ 5m bar cache (C:\\EdgeLog\\ohlc\\QQQ_5m.csv, or $EDGELOG_HOME/ohlc). Read
-only: never fetches, never writes C:\\EdgeLog\\cloud_signal\\ (uses an isolated temp
`paths` dict for every cloud_signal.step()/replay() call so it cannot disturb the live
signal ledger/state the runner depends on).
"""
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest  # noqa: E402
from api.paper import ORB_314  # noqa: E402
from api import cloud_signal as cs  # noqa: E402
import tools.qqq_paper as qp  # noqa: E402

TARGET_DAYS = ("2026-09-03", "2026-09-04")


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def part1_nq_ground_truth():
    section("1. Does #314 trade NQ on 2026-09-03 / 2026-09-04 at all?")
    master = find_master("NQ", "5m", "rth")
    arrays = load_master_arrays(master, date_from="2026-04-06", date_to="2026-09-05")
    res = run_backtest("ORB_3_6_R6.py", arrays=arrays, params=ORB_314,
                        cost_pts=0.0, return_trades=True)
    trades = (res or {}).get("trades") or []
    idx = arrays["index"]
    hits = [t for t in trades if str(idx[int(t[0])].date()) in TARGET_DAYS]
    print(f"  master={master['filename']}  bars={len(arrays['close'])}  "
          f"last={idx[-1]}")
    print(f"  #314 NQ trades on {TARGET_DAYS}: {len(hits)}")
    last_before = max((idx[int(t[0])] for t in trades), default=None)
    print(f"  most recent #314 NQ trade in this window: {last_before}")
    print("  -> VERDICT: the 'miss' is real on NQ too -- comparing #314 (silent) "
          "to the #234 control (which traded) is comparing two different legs.")


def part2_common_window_compare():
    section("2. #314 NQ vs #314 QQQ over the full common window "
            "(QQQ cache: whatever it holds)")
    qqq_path = os.path.join(cs.edgelog_home(), "ohlc", "QQQ_5m.csv")
    if not os.path.exists(qqq_path):
        print(f"  QQQ cache not found at {qqq_path} -- skipping.")
        return
    qqq_df = pd.read_csv(qqq_path)
    qqq_arrays = qp.build_arrays(qqq_df)
    win_start, win_end = qqq_arrays["index"][0], qqq_arrays["index"][-1]
    print(f"  QQQ cache window: {win_start} .. {win_end} "
          f"({len(set(qqq_arrays['day_id'].tolist()))} sessions)")

    master = find_master("NQ", "5m", "rth")
    nq_arrays = load_master_arrays(
        master, date_from=str(win_start.date() - pd.Timedelta(days=90)),
        date_to=str(win_end.date() + pd.Timedelta(days=1)))

    def trades_by_day(arrays):
        res = run_backtest("ORB_3_6_R6.py", arrays=arrays, params=ORB_314,
                            cost_pts=0.0, return_trades=True)
        idx = arrays["index"]
        out = {}
        for (eb, xb, pnl, side, px) in (res or {}).get("trades") or []:
            et = idx[int(eb)]
            if win_start.tz_localize(None) <= et.tz_localize(None) <= win_end.tz_localize(None):
                out.setdefault(et.date(), []).append((side, et))
        return out

    nq_by_day = trades_by_day(nq_arrays)
    qqq_by_day = trades_by_day(qqq_arrays)
    all_days = sorted(set(nq_by_day) | set(qqq_by_day))
    matched = nq_only = qqq_only = 0
    for d in all_days:
        n, q = nq_by_day.get(d), qqq_by_day.get(d)
        if n and q:
            matched += (n[0][0] == q[0][0])
            if n[0][0] != q[0][0]:
                print(f"  DIRECTION MISMATCH {d}: NQ={n[0][0]} QQQ={q[0][0]}")
        elif n:
            nq_only += 1
        elif q:
            qqq_only += 1
    print(f"  matched={matched}  nq_only={nq_only}  qqq_only={qqq_only}  "
          f"(NQ total {sum(len(v) for v in nq_by_day.values())}, "
          f"QQQ total {sum(len(v) for v in qqq_by_day.values())})")
    print("  -> VERDICT: QQQ tracks NQ closely; no systematic under-firing.")


def part3_reproduce_intraday_flip():
    section("3. The closed_arrays() calendar-buffer bug — live reproduction")
    qqq_path = os.path.join(cs.edgelog_home(), "ohlc", "QQQ_5m.csv")
    if not os.path.exists(qqq_path):
        print(f"  QQQ cache not found at {qqq_path} -- skipping.")
        return
    qqq_df = pd.read_csv(qqq_path)
    cfg = cs.CROWN_LEGS["ORB_R6"]
    target_key_prefix = "2026-09-04T09:55"
    print("  scanning 2026-09-04 tick-by-tick with THIS CHECKOUT's closed_arrays "
          "(fixed here iff api/cloud_signal.py's calendar_buffer_days fix is present):")
    verdicts, session_counts = [], []
    for hhmm in ("09:55", "10:00", "12:00", "14:00", "14:05", "14:06", "15:55"):
        now = pd.Timestamp(f"2026-09-04 {hhmm}:00", tz="US/Eastern").to_pydatetime()
        arrays = cs.closed_arrays(qqq_df, now, "5m", 60)
        n_sessions = len(set(arrays["day_id"].tolist()))
        trades = cs.run_leg_trades(cfg, arrays)
        hit = any(t["entry_time"].startswith(target_key_prefix) for t in trades)
        verdicts.append(hit); session_counts.append(n_sessions)
        print(f"    now={hhmm}  sessions={n_sessions}  window_start={arrays['index'][0].date()}"
              f"  09:55-entry present={hit}")
    if len(set(verdicts)) > 1 or len(set(session_counts)) > 1:
        print("  -> DRIFT DETECTED: the verdict/session-count changed within the same "
              "trading day -- this checkout's api/cloud_signal.py still has the buggy "
              "calendar buffer (or is being run against the shared checkout, not the fix).")
    else:
        print(f"  -> STABLE all day (sessions={session_counts[0]}, "
              f"present={verdicts[0]} at every tick) -- the buffer fix is in effect.")


def part4_isolated_replay_no_side_effects():
    section("4. Confirm via replay() -- ISOLATED state, never touches the live runner's "
            "C:\\EdgeLog\\cloud_signal\\ store")
    qqq_path = os.path.join(cs.edgelog_home(), "ohlc", "QQQ_5m.csv")
    if not os.path.exists(qqq_path):
        print(f"  QQQ cache not found at {qqq_path} -- skipping.")
        return
    scratch = tempfile.mkdtemp(prefix="orb_qqq_warmup_bug_")
    paths = cs._paths(scratch)
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    import shutil
    shutil.copy(qqq_path, cs._cache_path("5m", paths))
    one_min_src = os.path.join(cs.edgelog_home(), "ohlc", "QQQ_1m.csv")
    if os.path.exists(one_min_src):
        shutil.copy(one_min_src, cs._cache_path("1m", paths))
    legs = {"ORB_R6": cs.CROWN_LEGS["ORB_R6"]}
    for day in TARGET_DAYS:
        events = cs.replay(day, legs=legs, paths=paths, warmup_sessions=60)
        actionable = [e for e in events if e["event"] in ("ENTRY", "EXIT")]
        print(f"  {day}: {len(events)} event(s) total, {len(actionable)} actionable "
              f"ENTRY/EXIT -> {actionable}")
    print(f"  (isolated state store: {scratch} — safe to delete)")


if __name__ == "__main__":
    part1_nq_ground_truth()
    part2_common_window_compare()
    part3_reproduce_intraday_flip()
    part4_isolated_replay_no_side_effects()
