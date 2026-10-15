# nt_daily_splice.py - every trading day, put NinjaTrader's NQ day-session prices into the NQ RTH no-adjust masters
# before the 17:25 ET box push (MANAGER #68 D, 2026-10-14).
#
# WHY. Yahoo's NQ=F 5m bars agree with NinjaTrader on highs, lows and volume but put opens/closes on the other side
# of the bar boundary on ~70% of bars (10-05..10-14, up to 2.25 points). The order-flow forward gates (CUSTOM-ML,
# NOISE) read the masters against the NT 10s capture and need >= 80% exact, and the box's KEEL build reads the
# pushed NQ 5m RTH master. So the day is taken from NinjaTrader, and Yahoo only fills in when NT is missing.
#
# HOW. PAPER-NT8's scheduler drops one EdgeLogHistFetch request right after the 16:00 ET close for the previous and
# the current session (NQ front month, 1m, day session) -> C:\EdgeLog\nt_hist\out\NQ_daily_<YYYYMMDD>.csv. This
# script (Task Scheduler, before 16:15 ET) waits until 16:15 ET, waits for that file (until 17:15 ET), then runs
# the house splice (tools/splice_nt_sessions.py run_window, hlv acceptance) with --replace-from today: the previous
# session is the level anchor, today is written whole from NT - whether the master is missing it or holds Yahoo
# bars for it. Then it rebuilds the ADJ/FADJ twins of the masters it wrote. Everything goes through the master-write
# guard and lands in each master's provenance. On a refusal or no file it says so in the TBIS inbox and one plain
# low-priority phone note; the 17:25 ET push then tops the day up from Yahoo as before (nothing is lost).
#
# Run:  python tools/nt_daily_splice.py --commit            (the scheduled form)
#       python tools/nt_daily_splice.py --date 2026-10-15    (dry run for a given day, no waiting)
import argparse
import importlib.util
import os
import subprocess
import sys
import time
from datetime import datetime

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
_spec = importlib.util.spec_from_file_location("splice_nt_sessions", os.path.join(HERE, "splice_nt_sessions.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

ET = "US/Eastern"
NT_OUT = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "nt_hist", "out")
LOG = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "logs", "nt_daily_splice.log")
START_ET, DEADLINE_ET = "16:15", "17:15"      # the box push tops up from Yahoo at 17:25 ET
SOURCES = ("db_noadj_rth",)


def nt_file(day):
    return os.path.join(NT_OUT, "NQ_daily_%s.csv" % pd.Timestamp(day).strftime("%Y%m%d"))


def previous_session(nt_1m, day):
    """The last RTH session before `day` that the NT file holds - the level anchor."""
    days = [d for d in S.nt_sessions(nt_1m, "rth", (pd.Timestamp(day) - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                                     day) if d < day]
    if not days:
        raise S.Refused(f"{day}: the NT file holds no session before {day} to check the level on")
    return days[-1]


def _log(msg, log=None):
    line = "%s %s" % (datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), msg)
    print(line, flush=True)
    if log:
        try:
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def _wait_until(hhmm, clock=time.time, sleep=time.sleep):
    while pd.Timestamp(clock(), unit="s", tz="UTC").tz_convert(ET).strftime("%H:%M") < hhmm:
        sleep(30)


def _wait_for_file(path, deadline, clock=time.time, sleep=time.sleep):
    """True once `path` exists and its size has held still for a poll; False at the ET deadline."""
    size = -1
    while pd.Timestamp(clock(), unit="s", tz="UTC").tz_convert(ET).strftime("%H:%M") < deadline:
        if os.path.exists(path):
            now = os.path.getsize(path)
            if now == size and now > 0:
                return True
            size = now
        sleep(30)
    return os.path.exists(path) and os.path.getsize(path) > 0


def _alert(problem):
    """Inbox (TBIS) always; one plain low-priority phone note. Never raises."""
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "chat_inbox.py"), "post", "TBIS", "--from",
                        "nt_daily_splice", "NQ daily NT splice: " + problem], cwd=ROOT, timeout=60,
                       capture_output=True)
    except Exception:
        pass
    try:
        sys.path.insert(0, os.path.join(ROOT, "api"))
        import ntfy_push
        ntfy_push.send(ntfy_push.plain("NQ prices", "Yahoo today", problem=problem,
                                       action="nothing - TBIS re-runs it tomorrow", priority="low"))
    except Exception:
        pass


def run(day, commit=False, path=None, db=None, uploads=None, log=print):
    """Splice `day` from the NT daily file into every NQ RTH no-adjust master -> (written master ids, refused)."""
    path = path or nt_file(day)
    nt = S.load_nt(path)
    prev = previous_session(nt, day)
    res = S.run_window("NQ", prev, day, path, commit=commit, accept="hlv", db=db, uploads=uploads, log=log,
                       sources=SOURCES, replace_from=day)
    written = [r[0] for r in res if r[2] == "spliced" and r[3].get("sessions_written")]
    refused = [(r[1], r[3]) for r in res if r[2] == "refused"]
    return written, refused


def main(argv=None):
    ap = argparse.ArgumentParser(description="Daily NinjaTrader splice of the NQ day session (before the 17:25 ET push).")
    ap.add_argument("--date", help="trade date YYYY-MM-DD (default: today ET; given = no waiting)")
    ap.add_argument("--commit", action="store_true", help="write; the default is a dry run")
    a = ap.parse_args(argv)
    now_et = pd.Timestamp.now(tz=ET)
    day = a.date or now_et.strftime("%Y-%m-%d")
    if pd.Timestamp(day).weekday() >= 5:
        _log(f"{day}: weekend - nothing to do", LOG); return 0
    path = nt_file(day)
    if not a.date:
        _wait_until(START_ET)
        if not _wait_for_file(path, DEADLINE_ET):
            _log(f"{day}: no NT file by {DEADLINE_ET} ET ({os.path.basename(path)}) - Yahoo fills the day at 17:25", LOG)
            _alert(f"no NinjaTrader file for {day} by {DEADLINE_ET} ET, so today's NQ prices stay Yahoo")
            return 1
    try:
        written, refused = run(day, a.commit, path, log=lambda s: _log(s, LOG))
    except Exception as e:                       # a refusal, a malformed file - never silent
        _log(f"{day}: REFUSED - {type(e).__name__}: {e}", LOG)
        _alert(f"{day} not spliced: {e}")
        return 1
    if refused:
        _alert(f"{day}: {len(refused)} master(s) refused, e.g. {refused[0][0]}: {str(refused[0][1])[:120]}")
    if a.commit and written:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_adjusted_masters.py"), "--apply",
                            "--no-refresh", "--only", ",".join(_filenames(written))], cwd=ROOT,
                           capture_output=True, text=True, timeout=3600)
        _log(f"{day}: ADJ/FADJ rebuild exit {r.returncode}", LOG)
    _log(f"{day}: {'wrote' if a.commit else 'would write'} {len(written)} master(s), {len(refused)} refused", LOG)
    return 1 if refused else 0


def _filenames(ids, db=None):
    con = S._connect(db or os.path.join(ROOT, "optimizer_history.db"))
    out = [r[0] for r in con.execute("select filename from csv_files where id in (%s)" % ",".join("?" * len(ids)),
                                     list(ids)).fetchall()]
    con.close()
    return out


if __name__ == "__main__":
    sys.exit(main())
