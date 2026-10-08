r"""tools/webull_freshness.py -- the Webull pipeline FRESHNESS MONITOR, box side (one pass).

WHY THIS EXISTS (C:\EdgeLog\manager\webull_sweep_1005\WEBULL_SILENT_FAILURES.md, 2026-10-05).
The executor's Firestore publish wedged from Sat 10-03 17:11 ET to Mon 09:13 ET (about 40 h):
every armed broker send was blocked, systemd showed the unit healthy, and nothing paged. The
sweep found 37 ways a step of the Webull paper pipeline can fail or go stale with nobody told
in time. This is the "single freshness monitor" it proposed: a SEPARATE process from the
executor (api/qqq_exec.py) and the signal engine (api/cloud_signal.py), run by
deploy/cloud/edgelog-freshness.timer every 2 minutes, 24/7, as the box user. It reads LOCAL
FILES ONLY -- no Firestore, no Webull, no broker call of any kind -- so the thing that wedges
the executor cannot wedge the watcher.

WHAT IT CHECKS (finding numbers refer to that file; times are New York, holidays and half days
from api/market_calendar):
  ALWAYS (24/7)
    exec_publish     state.json last_publish_ok_et older than max(15 min, 1.5x the advertised
                     renew cadence) -- #1, #2. URGENT while armed in session, else HIGH.
    exec_suppress    3+ "suppressing broker sends" lines in qqq_exec.log within 15 min -- the
                     lease read failing, every real order blocked (fail-CLOSED) -- #1, #3.
    exec_loop        the tick loop's own heartbeat (SERVING.lock, rewritten every tick, or
                     state.json's mtime) older than 10 min -- process wedged or gone.
    failed_unit:<u>  `systemctl --failed` lists a unit -- #17, #28, #33.
    disk / log_size  / at or above 80 %, any log over 100 MB -- #33.
    nq_master        the NQ master's last bar is older than the latest session whose 18:00 ET
                     has passed, or tools/keel_live_state.py's marker (keel/nq_stale_alert.json)
                     says that session's day is INCOMPLETE in the file -- #10. Checked from
                     18:00 ET (15:00 Arizona) on each session day -- after the PC's 17:20 ET
                     upload plus margin, BEFORE the 18:30 ET KEEL rebuild, so a hand re-run of
                     the upload still lands in time -- and kept open until the data lands.
                     THE ONE PUSHER of "NQ data did not reach the box" (WEBULL PUSH PLAN 10-07,
                     MANAGER #86 section 3): keel_live_state keeps its log line and marker, the
                     PC sweep its JSON and inbox, cloud_signal its state.json; none of them
                     pushes it. Default priority (KEEL still sizes on yesterday's model).
    keel:<leg>       a KEEL summary's data_through older than the latest session whose 19:00 ET
                     has passed (or the session before it when that one was a half day: the
                     builder drops a short final session) -- #11, #12. DEFAULT while the model
                     is 1 to 4 sessions old (sizing still uses it; the pre-open gate too), and
                     QUIET -- folded into the
                     nq_master note -- when it opens while nq_master is failing.
    keel_fallback:<leg>  that model is KEEL_FALLBACK_SESSIONS (5) or more sessions old: from the
                     next session the live leg sizes at base size without it (api/cloud_signal
                     KEEL_MAX_STALE_SESSIONS). HIGH -- the second and last push of a missed-night
                     run; api/cloud_signal records instead of pushing while this is open.
  SESSION (09:30 to the close, 13:00 on half days)
    engine_hb        cloud_signal heartbeat over 3 min old or ok=false, lot or no lot -- #5.
    bar_age          newest CLOSED 5m bar closed more than 660 s ago (from 09:41) -- #6.
                     Also fails when a FRESH engine heartbeat says stalled=true (the
                     engine's own verdict, api/cloud_signal.py FEED HEALTH, 2026-10-05), and
                     names its bars_missing count; a heartbeat without those fields (an
                     older engine) is judged on the bar times alone, as before.
                     ONE PAGER: such an engine pages this episode itself ("QQQ book: prices stopped"),
                     so while its heartbeat is fresh and carries `stalled` the episode opens
                     QUIET here -- tracked in status.json (and relayed to the PC) but never
                     pushed, start or end. With a stale heartbeat (engine_hb pages that) or
                     an older engine, this monitor pages bar_age itself, as before.
    bar_source       the live 5m cache came from yfinance on 2 runs in a row (the engine
                     fetches every 20-60 s, so that is 3+ fetches) -- #15. QUIET (not
                     pushed) while a fresh engine heartbeat carries yf_fallback_streak: the
                     engine pages it ("QQQ book: backup prices") after 3 fetches in a row.
    tick_gap         tick loop silent over 30 s now, or the day's max gap rose past 30 s -- #3.
                     QUIET while the executor's own tick crash episode is open (its
                     tick_crash.json marker beside state.json, written when it pushed the
                     crash, refreshed on every failed tick, newer than the last good tick
                     and at most TICK_CRASH_MARKER_FRESH_SEC old): it already pushed it. A
                     process that has hung or died stops refreshing it -- paged as usual.
    qqq_1d           from 09:40, QQQ_1d's newest bar is not the previous session (the
                     engine refreshes it once a day at ~09:35) -- #14, 2 runs in a row.
    shadow_hb        shadow-legs heartbeat over 10 min old or ok=false -- #25 (MEDIUM).
  EOD (session days, from 16:10 ET)
    eod_summary / webull_flat   eod_summary_done_date and _webull_flat_after_eod (flat) are
                     TODAY -- #7, URGENT. (webull_flat is HIGH, saying so, while the executor's
                     KILL file is present: a halted book skips the flatten, so the check cannot
                     run.) ONE OWNER (WEBULL PUSH PLAN 10-07): the executor pushes the RESULT of
                     its after-close check (Webull not flat / position unreadable) the moment it
                     has it, so an episode that opens on such a result is QUIET here (status.json
                     and the PC inbox relay only); this monitor pushes "the check did not run"
                     (the executor cannot report its own absence) and the KILL case.
    eod_settled      cloud_signal eod_settled has today -- #30. The ONE pusher of "today's close
                     was not settled": the engine only records eod_gave_up[today] (named here
                     when present) and the executor only logs the board event.
  PRE-OPEN GATE (session days; the 08:30 and 09:15 ET slots, each once)
    KEEL current, QQQ_1d newest bar no older than the session BEFORE the previous one (the
    most the cache can hold before the engine's ~09:35 refresh), lease fresh (last publish within
    max(90 s, 2x renew)), not halted (breaker/kill today, KILL files), engine heartbeat fresh,
    Webull token NORMAL with more than 5 days left (#12, #14, #18, #19). The first slot that
    passes pushes "QQQ book: OK" (low, once a day -- which also proves the alert path works,
    #16); a miss pushes "QQQ book: CHECK NOW" (high) -- see PHONE TEXT. A KEEL miss already in
    an open episode that pushed (nq_master, keel:<leg> -- quiet ones were folded into the
    nq_master note -- keel_fallback:<leg>, keel:none) stays in the JSON and status only: the
    morning brings no second buzz for the same missed night.

ALERTS (#16). One push per EPISODE (the run a check first fails -- or its 2nd run in a row for
the debounced ones) and, when it passes again, one "OK" only if that episode's push was high or
urgent; problems that start in the same run go out as ONE push. Every push goes through
api/ntfy_push (token-aware) via a
PERSISTED OUTBOX (<home>/freshness/outbox.json): a push that fails stays queued and is retried
every run for up to 12 h (at most 5 sends a run; the outbox is rewritten after each one), so
a network blip delays a page instead of eating it (a late one says "Sent late - raised at
HH:MM" on its problem line). A windowed
check whose window ends while it is still failing is closed as "no longer checked": logged,
kept in status.json and relayed to the inboxes by the PC half, but NOT pushed again (the
opening push already said what to do; nothing was seen fixed).

PHONE TEXT (2026-10-07, owner GO "yes deploy box pings": the PC side's plain format from v73.1120
brought to the box). Every push is an api/ntfy_push.plain() note -- title "<area>: <status>"
under 40 characters, then "Trading: not affected." or "Trading: AFFECTED - <what>.", ONE plain
problem line ("+N more" when several started together), "Do: ...". Areas: "QQQ book" (the Webull
paper book) and "Cloud box" (disk, logs, a box service the book does not need). Priority by what
the problem does to TRADING: urgent only where the check was already URGENT (orders blocked while
armed in session, the close not run, Webull not confirmed flat); high when trading is affected;
default when it needs a fix today but trading is fine; low for data-only notes and every "OK".
Times are the owner's clock (America/Phoenix, ntfy_push.hhmm), never New York. Each check carries
its own wording as the verdict's "plain" dict ({area, affects, problem, action, priority}); the
verdict's "title"/"detail" -- what status.json, the log and the PC relay show -- are unchanged.
Before: "EDGELOG WB MONITOR: <developer title>" with "[SEVERITY] title: detail" lines, an "OK
again" push for every episode, and "QQQ book ready"/"QQQ book NOT ready" (urgent) from the gate.
  Pre-open gate:  not ready -> "QQQ book: CHECK NOW" (high), "Trading: AFFECTED - the QQQ book may
                  not trade at the open." (or what the lead miss really does: an old KEEL model, a
                  short price history), the lead miss in plain words "+N more", its fix (a miss only
                  the owner can clear -- approve the Webull login, a halt or kill switch -- leads). A
                  token that merely expires within 5 days is "QQQ book: needs a fix" (default,
                  trading not affected today). Repeats by ntfy_push.dedupe inside the day: the 09:15
                  slot pushes only a NEW or WORSE miss; a new day starts fresh. ready -> "QQQ book:
                  OK" (low) "The QQQ paper book passed its 05:31 pre-open check." once a day, or
                  when it turns ready after a miss.
  Episodes:       e.g. "QQQ book: CHECK NOW" (urgent) / "Trading: AFFECTED - the QQQ book cannot send
                  orders." / "The QQQ order program stopped reporting at 07:10 - the board is
                  frozen." / "Do: ask Claude (PAPER-WB chat)."; "Cloud box: needs a fix" (default)
                  for the disk, a big log or a box service the book does not trade through; the
                  shadow legs' heartbeat is a low note (data only).
  Auto-restart:   "QQQ book: restarted" (low) when it worked -- flat, market closed; "QQQ book: CHECK
                  NOW" (high) when the restart command failed.

Outputs, all under <home>/freshness/: status.json (open alerts, this run's verdicts,
outbox depth, restart gate, the last KEEL_DIFFS_IN_STATUS KEEL size diffs -- what
tools/webull_freshness_pc.py reads over ssh),
freshness_heartbeat.json (this monitor's own liveness), state.json (its memory), and a log at
<home>/logs/freshness.log. If EDGELOG_FRESHNESS_PING_URL is set (a healthchecks.io-type
push-heartbeat URL, never logged), each completed run GETs it, so a dead box or timer pages
from outside (#4).

AUTO-RESTART (#2) -- ADOPTED BY THE OWNER 2026-10-05 (MANAGER #69): switched on by the box
config below, still OFF by default in code. When the executor's
publish has been down over 10 min (or 1.5x its advertised publish cadence when that is longer:
an unarmed executor publishes only every 600 s) OR its tick loop has been silent over 10 min,
the rule is:
restart edgelog-qqq-exec (and nothing else -- never cloud-signal or any other unit) ONLY
outside 09:25-16:10 ET on a session day (any time on a non-session day), ONLY while the book
is flat (state.json legs, _broker_resend and _broker_fill_capture all empty), ONLY while
`systemctl is-active` says the unit is active (wedged) or failed -- an inactive unit was
stopped on purpose and is never started -- at most ONCE A DAY (New York date, the owner's
rule) and never twice within an hour across midnight (both saved before the restart is
issued), logged, pushed, and posted to the MANAGER and PAPER-WB inboxes by the PC relay
(tools/webull_freshness_pc.py reads status.json auto_restart.last_restart_et). It acts only when <home>/freshness/config.json says
{"auto_restart_exec": true} (the JSON literal true; any other value, a "true" string included,
is OFF); until then the same gate runs and only logs "would restart"
(once an hour), so the owner can read what it would have done before switching it on.

NEVER READS THE WEBULL TOKEN. token.txt is the SDK's own three-line file (token, expiry in
epoch ms, status); line 1 is read past and discarded, only lines 2-3 are parsed. Nothing here
prints NTFY_TOPIC, NTFY_TOKEN, the ping URL or any account field (the order adapter's
config.json is read for its "mode" key only).

KEEL SIZE DIFFS (2026-10-05, MANAGER #76). api/cloud_signal.py records each LIVE NOISE entry
where KEEL's size and the fixed rule's size differ (cloud_signal/keel_size_diffs.jsonl, once per
date + leg + entry time) and pushes it itself. This monitor only copies the last
KEEL_DIFFS_IN_STATUS records into status.json "keel_diffs" (oldest first) -- no verdict, no push
-- so the PC relay can post each one once to the MANAGER and PAPER-WB inboxes.

Usage (on the box):  venv/bin/python tools/webull_freshness.py [--dry-run] [--home DIR]
  --dry-run   evaluate and print the verdicts; no push, no restart, no file written.
"""
import argparse
import datetime as _dt
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import market_calendar  # noqa: E402  (see sys.path insert above)
from api import ntfy_push  # noqa: E402  (stdlib only; the one plain phone format)

ET = ZoneInfo("America/New_York")

URGENT, HIGH, MEDIUM, INFO = "URGENT", "HIGH", "MEDIUM", "INFO"
_SEV_RANK = {INFO: 0, MEDIUM: 1, HIGH: 2, URGENT: 3}

# -- phone wording (PHONE TEXT in the module docstring) -----------------------------------------
BOOK, BOX = "QQQ book", "Cloud box"
ASK = "ask Claude (PAPER-WB chat)"
NO_ORDERS = "the QQQ book cannot send orders"
MAY_NOT_TRADE = "the QQQ book may not trade at the open"
OLD_MODEL = "the QQQ book sizes NOISE trades on an old model"
MAY_HOLD = "the QQQ book may still hold shares after the close"
SHORT_HISTORY = "NOISE trades on a price history that is a day short"
OWNER_FIXES = ("token_status", "halted", "kill")   # pre-open misses only the owner can clear
FLAT_DO = "check the Webull app is flat and sell by hand if needed"
# box units by plain name, and whether the book trades through them
UNIT_WORDS = {
    "edgelog-qqq-exec.service": ("The QQQ order program", True),
    "edgelog-cloud-signal.service": ("The QQQ signal program", True),
    "edgelog-qqq-bars.service": ("The QQQ chart download", False),
    "edgelog-keel-state.service": ("The KEEL model rebuild", False),
    "edgelog-freshness.service": ("This monitor", False),
    "edgelog-runner.service": ("The job runner", False),
    "edgelog-healthcheck.service": ("The box health check", False),
}


def _plain(problem, action=ASK, affects=None, area=BOOK, priority=None):
    """One check's phone wording -> the verdict's "plain" dict. priority None = urgent/high from
    the verdict's severity when trading is affected, else default (see _rec_priority)."""
    return {"area": area, "affects": affects, "problem": problem, "action": action,
            "priority": priority}


def _plain_age(sec):
    """45 -> '45 seconds', 840 -> '14 min', 9000 -> '2.5 hours'; None -> None."""
    if sec is None:
        return None
    sec = max(0.0, float(sec))
    if sec < 120:
        return "%d seconds" % sec
    if sec < 7200:
        return "%d min" % round(sec / 60)
    return "%.1f hours" % (sec / 3600)

# -- thresholds (seconds unless named otherwise) ---------------------------------------------
PUBLISH_STALE_FLOOR_SEC = 900.0      # 15 min: the off-hours publish cadence is 600 s
PUBLISH_STALE_MARGIN = 1.5           # x lease.renew_every_sec, same margin as the dead-man
SUPPRESS_PHRASE = b"suppressing broker sends"
SUPPRESS_WINDOW_SEC = 900.0
SUPPRESS_MIN_HITS = 3
EXEC_LOOP_SILENT_SEC = 600.0
DISK_PCT_MAX = 80.0
LOG_MAX_BYTES = 100 * 1024 * 1024
ENGINE_HB_STALE_SEC = 180.0          # 2x api/qqq_exec.py's ENGINE_HEARTBEAT_STALE_SEC
SHADOW_HB_STALE_SEC = 600.0
BAR_SEC = 300
BAR_CLOSE_STALE_SEC = 660.0          # two 5m bars + 60 s
BAR_CHECK_AFTER_OPEN_MIN = 11        # 09:30 bar closes 09:35; +660 s = 09:46 at the latest
QQQ_1D_CHECK_FROM = (9, 40)          # the engine refreshes QQQ_1d once a day at ~09:35
TICK_GAP_SESSION_SEC = 30.0
SESSION_OPEN = (9, 30)
EOD_CHECK_FROM = (16, 10)
EVENING_CHECK_FROM = (19, 0)
NQ_CHECK_FROM = (18, 0)              # before the 18:30 ET KEEL rebuild (WEBULL PUSH PLAN 10-07)
KEEL_REBUILD_AT = (18, 30)           # deploy/cloud/edgelog-keel-state.timer, New York time
KEEL_FALLBACK_SESSIONS = 5           # = api/cloud_signal.KEEL_MAX_STALE_SESSIONS (a test pins it)
NQ_MARKER = "nq_stale_alert.json"    # tools/keel_live_state.STALE_MARKER, in the keel dir
PREOPEN_SLOTS = ((8, 30), (9, 15))
PREOPEN_LEASE_FLOOR_SEC = 90.0
PREOPEN_LEASE_MARGIN = 2.0
TOKEN_MIN_DAYS = 5.0
RESTART_PUBLISH_DOWN_SEC = 600.0
RESTART_TICK_GAP_SEC = 600.0
RESTART_COOLDOWN_SEC = 3600.0
RESTART_PROTECTED = ((9, 25), (16, 10))   # session days only
EXEC_UNIT = "edgelog-qqq-exec.service"
OUTBOX_MAX_AGE_SEC = 12 * 3600.0
OUTBOX_MAX_SENDS_PER_RUN = 5         # x 8 s ntfy timeout = 40 s, well inside TimeoutStartSec=100
WINDOW_HOLD_SEC = 0.0                # a windowed check closes the run its window ends
KEEL_DIFFS_IN_STATUS = 20            # status.json "keel_diffs": the last N records

DEFAULT_CONFIG = {"auto_restart_exec": False}


# -- paths ------------------------------------------------------------------------------------
def default_paths(home=None):
    """Every file this monitor reads or writes. With an explicit `home` (tests) nothing comes
    from the environment; without one the same env overrides the services use apply."""
    env = {} if home else os.environ
    home = home or os.environ.get("EDGELOG_HOME") or os.path.expanduser("~/edgelog")
    exec_dir = env.get("EDGELOG_QQQ_EXEC_DIR") or os.path.join(home, "qqq_exec")
    cs_dir = os.path.join(home, "cloud_signal")
    out_dir = os.path.join(home, "freshness")
    return {
        "home": home,
        "exec_state": os.path.join(exec_dir, "state.json"),
        "exec_config": os.path.join(exec_dir, "config.json"),
        "exec_kill": os.path.join(exec_dir, "KILL"),
        "serving_lock": os.path.join(exec_dir, "SERVING.lock"),
        "serving_standby": os.path.join(exec_dir, "SERVING.lock.standby"),
        "exec_tick_crash": os.path.join(exec_dir, "tick_crash.json"),
        "exec_log": os.path.join(home, "logs", "qqq_exec.log"),
        "logs_dir": os.path.join(home, "logs"),
        "orders_config": env.get("EDGELOG_WEBULL_ORDERS_CONFIG")
        or os.path.join(home, "webull_orders", "config.json"),
        "orders_kill": env.get("EDGELOG_WEBULL_ORDERS_KILL")
        or os.path.join(home, "webull_orders", "KILL"),
        "cs_state": os.path.join(cs_dir, "state.json"),
        "cs_heartbeat": os.path.join(cs_dir, "heartbeat.json"),
        "shadow_heartbeat": os.path.join(cs_dir, "shadow", "heartbeat.json"),
        "keel_dir": os.path.join(cs_dir, "keel"),
        "keel_diffs": os.path.join(cs_dir, "keel_size_diffs.jsonl"),
        "qqq_5m": os.path.join(home, "ohlc", "QQQ_5m.csv"),
        "qqq_1d": os.path.join(home, "ohlc", "QQQ_1d.csv"),
        "nq_master": os.path.join(home, "nq", "NOADJ_NQ_5m_RTH.csv"),
        "token_files": [
            os.path.join(env.get("EDGELOG_WEBULL_TOKEN_DIR")
                         or os.path.join(home, "webull_token"), "token.txt"),
            os.path.join(env.get("EDGELOG_WEBULL_PAPER_TOKEN_DIR")
                         or os.path.join(home, "webull_paper_token"), "token.txt"),
        ],
        "out_dir": out_dir,
        "status": os.path.join(out_dir, "status.json"),
        "heartbeat": os.path.join(out_dir, "freshness_heartbeat.json"),
        "monitor_state": os.path.join(out_dir, "state.json"),
        "outbox": os.path.join(out_dir, "outbox.json"),
        "config": os.path.join(out_dir, "config.json"),
        "log": os.path.join(home, "logs", "freshness.log"),
    }


# -- small readers (never raise) --------------------------------------------------------------
def read_json(path):
    """(data, error). Missing file -> (None, "missing"); bad JSON -> (None, "unreadable: ...")."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as e:
        return None, f"unreadable: {type(e).__name__}"


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)
    os.replace(tmp, path)


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def read_keel_diffs(path, last=KEEL_DIFFS_IN_STATUS, max_bytes=256 * 1024):
    """The last `last` KEEL size-diff records (dicts, oldest first) from the engine's
    keel_size_diffs.jsonl (api/cloud_signal.py KEEL ENTRY EXTRAS). Reads the file's tail only;
    a missing file is [], a torn or non-JSON line is skipped. Never raises."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out[-int(last):] if last else out


def last_csv_line(path, nbytes=8192):
    """Last non-empty, non-header line of a (possibly large) CSV, or None."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            chunk = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    for ln in reversed(chunk.splitlines()):
        ln = ln.strip()
        if ln and not ln.lower().startswith("time"):
            return ln
    return None


def last_bar_epoch(path):
    """First field of the CSV's last row as an int epoch, or None."""
    ln = last_csv_line(path)
    if not ln:
        return None
    try:
        return int(float(ln.split(",")[0]))
    except ValueError:
        return None


def epoch_to_et_date(epoch):
    return _dt.datetime.fromtimestamp(epoch, tz=ET).date()


def daily_bar_date(epoch):
    """The trading date a DAILY bar's epoch stands for. Daily bars are stamped at local
    midnight (00:00 ET, or 04:00/05:00 UTC); +6 h keeps a stamp a few hours either side of ET
    midnight on the right calendar day in both DST states."""
    return (_dt.datetime.fromtimestamp(epoch, tz=ET) + _dt.timedelta(hours=6)).date()


def parse_iso(s):
    try:
        d = _dt.datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=ET)


def serving_lock_epoch(path):
    """SERVING.lock holds "<pid> YYYY-MM-DD HH:MM:SS" (ET, rewritten every tick)."""
    try:
        with open(path, encoding="utf-8") as f:
            parts = f.read().split()
        naive = _dt.datetime.strptime(" ".join(parts[1:3]), "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=ET).timestamp()
    except (OSError, ValueError, IndexError):
        return None


def read_token_meta(path):
    """(expires_epoch_sec, status) from the Webull SDK's token.txt, or (None, None) when the
    file is absent. Line 1 is the token itself: it is read past and discarded, never kept,
    parsed, logged or returned. Line 2 is the expiry in epoch ms, line 3 the status."""
    try:
        with open(path, encoding="utf-8") as f:
            f.readline()                     # the token -- skipped on purpose
            exp_line = f.readline().strip()
            status = f.readline().strip() or None
    except OSError:
        return None, None
    expires = None
    if exp_line.isdigit():
        expires = int(exp_line) / (1000.0 if len(exp_line) >= 12 else 1.0)
    return expires, status


def read_mode(path):
    """The order adapter's "mode" (OFF/PAPER/LIVE) -- the only key read from that file."""
    data, _err = read_json(path)
    if isinstance(data, dict):
        return str(data.get("mode") or "OFF").upper()
    return "OFF"


def failed_units(run_cmd=None):
    """(units, error). `systemctl --failed`; error is set when systemctl is unavailable."""
    run_cmd = run_cmd or subprocess.run
    try:
        r = run_cmd(["systemctl", "--failed", "--no-legend", "--plain"],
                    capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"{type(e).__name__}"
    if r.returncode != 0 and not (r.stdout or "").strip():
        return None, f"rc={r.returncode}"
    units = []
    for ln in (r.stdout or "").splitlines():
        parts = ln.replace("\u25cf", " ").split()
        if parts:
            units.append(parts[0])
    return units, None


def scan_log_for(path, phrase, offset, max_bytes=4 * 1024 * 1024):
    """(hits, new_offset) -- occurrences of `phrase` appended since `offset`. offset None ->
    first sight: start at the end, count nothing (old lines are history, not news). A file
    smaller than the offset was truncated by logrotate's copytruncate: start again at 0."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return 0, None
    if offset is None:
        return 0, size
    if size < offset:
        offset = 0
    start = max(offset, size - max_bytes)
    try:
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(size - start)
    except OSError:
        return 0, offset
    return data.count(phrase), size


# -- calendar helpers -------------------------------------------------------------------------
def at(day, hhmm):
    return _dt.datetime(day.year, day.month, day.day, hhmm[0], hhmm[1], tzinfo=ET)


def hhmm(now_et):
    return (now_et.hour, now_et.minute)


def close_hhmm(day):
    h, m = market_calendar.session_close_et(day).split(":")
    return (int(h), int(m))


def prev_session(day):
    d = day - _dt.timedelta(days=1)
    for _ in range(15):
        if market_calendar.is_session(d):
            return d
        d -= _dt.timedelta(days=1)
    return None


def latest_session_due(now_et, hhmm_due):
    """Most recent session day D with D at `hhmm_due` ET <= now, or None."""
    d = now_et.date()
    for _ in range(15):
        if market_calendar.is_session(d) and at(d, hhmm_due) <= now_et:
            return d
        d -= _dt.timedelta(days=1)
    return None


def keel_expected(session_day):
    """KEEL's builder drops a final session with fewer than a full day's bars, so after a
    half day the newest state is trained through the session BEFORE it."""
    if market_calendar.session_close_et(session_day) != "16:00":
        return prev_session(session_day) or session_day
    return session_day


def qqq_1d_day(snap):
    """Trading date of QQQ_1d.csv's newest bar, or None."""
    d1 = snap.get("qqq_1d_last")
    return daily_bar_date(d1) if d1 else None


def in_session(now_et):
    d = now_et.date()
    if not market_calendar.is_session(d):
        return False
    return SESSION_OPEN <= hhmm(now_et) < close_hhmm(d)


def fmt_age(sec):
    if sec is None:
        return "unknown"
    sec = float(sec)
    if sec < 120:
        return f"{sec:.0f}s"
    if sec < 7200:
        return f"{sec / 60:.0f} min"
    return f"{sec / 3600:.1f} h"


# -- snapshot: every input, read once ---------------------------------------------------------
def collect(paths, run_cmd=None):
    snap = {}
    snap["exec_state"], snap["exec_state_err"] = read_json(paths["exec_state"])
    snap["exec_state_mtime"] = mtime(paths["exec_state"])
    snap["serving_epoch"] = serving_lock_epoch(paths["serving_lock"])
    snap["standby_mtime"] = mtime(paths["serving_standby"])
    if paths.get("exec_tick_crash"):
        crash, _err = read_json(paths["exec_tick_crash"])
        snap["tick_crash"] = crash if isinstance(crash, dict) else None
        snap["tick_crash_mtime"] = mtime(paths["exec_tick_crash"])
    exec_cfg, _ = read_json(paths["exec_config"])
    kill_file = (exec_cfg or {}).get("kill_file") if isinstance(exec_cfg, dict) else None
    snap["kill_files"] = [p for p in (kill_file or paths["exec_kill"], paths["orders_kill"])
                          if p and os.path.exists(p)]
    # the EXECUTOR's own KILL file only (not the order adapter's): while it is present the
    # executor skips its flat_by flatten, so its post-close Webull flat check never runs
    snap["exec_kill_files"] = [p for p in (kill_file or paths["exec_kill"],)
                               if p and os.path.exists(p)]
    snap["broker_mode"] = read_mode(paths["orders_config"])
    snap["cs_state"], snap["cs_state_err"] = read_json(paths["cs_state"])
    snap["cs_hb"], snap["cs_hb_err"] = read_json(paths["cs_heartbeat"])
    snap["shadow_hb"], snap["shadow_hb_err"] = read_json(paths["shadow_heartbeat"])
    snap["qqq_5m_last"] = last_bar_epoch(paths["qqq_5m"])
    snap["qqq_1d_last"] = last_bar_epoch(paths["qqq_1d"])
    snap["nq_last"] = last_bar_epoch(paths["nq_master"])
    keel = {}
    for p in sorted(glob.glob(os.path.join(paths["keel_dir"], "*_summary.json"))):
        data, err = read_json(p)
        name = os.path.basename(p)[:-len("_summary.json")]
        # the same rule as api/cloud_signal's staleness check: data_through, else
        # ml_keel's own last_nq_session (an older summary); neither = cloud_signal skips
        # the stale check and keeps using the model
        keel[name] = ((data.get("data_through") or data.get("last_nq_session"))
                      if isinstance(data, dict) else None)
    snap["keel"] = keel
    marker, _err = read_json(os.path.join(paths["keel_dir"], NQ_MARKER))
    snap["nq_marker"] = marker if isinstance(marker, dict) else None
    snap["keel_diffs"] = read_keel_diffs(paths["keel_diffs"]) if paths.get("keel_diffs") else []
    tokens = {}
    for p in paths["token_files"]:
        if os.path.exists(p):
            tokens[os.path.basename(os.path.dirname(p))] = read_token_meta(p)
    snap["tokens"] = tokens
    snap["failed_units"], snap["failed_units_err"] = failed_units(run_cmd)
    try:
        du = shutil.disk_usage(paths["home"])
        snap["disk_pct"] = 100.0 * du.used / du.total if du.total else None
    except OSError:
        snap["disk_pct"] = None
    big = []
    try:
        for e in os.scandir(paths["logs_dir"]):
            if e.is_file() and e.name.endswith(".log") and e.stat().st_size > LOG_MAX_BYTES:
                big.append((e.name, e.stat().st_size))
    except OSError:
        pass
    snap["big_logs"] = big
    return snap


# -- derived executor view --------------------------------------------------------------------
def wall_time_age(t, now_et):
    """Seconds since the most recent moment the ET wall clock read `t` (a dateless time), in
    REAL elapsed time. Every reading of `t` today and yesterday -- both folds, so an hour that
    repeats at the fall-back change is tried both ways -- is turned into a UTC epoch, and the
    newest one not after now (60 s of clock skew allowed) wins. Plain wall-clock subtraction
    misreads a publish seconds before a DST change as an hour (spring) or a day (fall) old."""
    now_epoch = now_et.timestamp()
    best = None
    for days_back in (0, 1):
        day = now_et.date() - _dt.timedelta(days=days_back)
        for fold in (0, 1):
            e = _dt.datetime.combine(day, t, tzinfo=ET).replace(fold=fold).timestamp()
            if e <= now_epoch + 60 and (best is None or e > best):
                best = e
    return None if best is None else now_epoch - best


def exec_view(snap, now_et, mstate):
    """Publish age, tick-loop age, flatness and the cadence the executor advertised."""
    now_epoch = now_et.timestamp()
    st = snap.get("exec_state") if isinstance(snap.get("exec_state"), dict) else None
    v = {"readable": st is not None, "publish_age": None, "loop_age": None, "flat": None,
         "renew": 600.0, "last_ok": None}
    if st is None:
        return v
    try:
        v["renew"] = float(st.get("_lease_renew_every_sec") or 600.0)
    except (TypeError, ValueError):
        pass
    s = st.get("last_publish_ok_et")
    v["last_ok"] = s
    if s:
        # last_publish_ok_et is a bare HH:MM:SS (no date, api/qqq_exec.py
        # _record_publish_result). Read as the most recent such ET time, then floor the age
        # by how long THIS monitor has seen the same value unchanged -- so a wedge longer
        # than a day still reads as long as it really is.
        seen = mstate.setdefault("publish_seen", {})
        if seen.get("value") != s:
            seen.clear()
            seen.update({"value": s, "first_seen_epoch": now_epoch})
        try:
            t = _dt.datetime.strptime(str(s), "%H:%M:%S").time()
            age = wall_time_age(t, now_et)
        except ValueError:
            age = None
        floor = now_epoch - float(seen.get("first_seen_epoch", now_epoch))
        v["publish_age"] = max(age if age is not None else 0.0, floor)
    last_tick = max([x for x in (snap.get("serving_epoch"), snap.get("exec_state_mtime"))
                     if x is not None] or [0.0])
    v["loop_age"] = (now_epoch - last_tick) if last_tick else None
    v["flat"] = (not st.get("legs")) and (not st.get("_broker_resend")) \
        and (not st.get("_broker_fill_capture"))
    return v


def _verdict(key, group, ok, severity, title, detail="", min_runs=1, hold_sec=WINDOW_HOLD_SEC,
             plain=None, quiet=False):
    """ok: True pass, False fail, None unknown this run (no change either way). `title` and
    `detail` are the developer text (status.json, the log, the PC relay); `plain` (a _plain()
    dict) is the phone wording -- see PHONE TEXT. quiet: another sender already pages this
    exact problem -- the episode is tracked (status, board) but neither its start nor its end
    is pushed (decided when the episode opens)."""
    v = {"key": key, "group": group, "ok": None if ok is None else bool(ok),
         "severity": severity, "title": title,
         "detail": detail, "min_runs": min_runs, "hold_sec": hold_sec}
    if plain is not None:
        v["plain"] = plain
    if quiet:
        v["quiet"] = True
    return v


def _exec_pushed_database(st, now_epoch, publish_age):
    """True when the executor's own "cloud database unreachable" note (state.json
    _phone_dedupe.database, api/qqq_exec._maybe_rebuild_firestore) went out DURING this
    outage -- after its last good publish. ONE OWNER (WEBULL PUSH PLAN 10-07, "Book stopped
    publishing"): the executor owns the database outage; exec_publish / exec_suppress then
    track the episode without a second push. A note from an earlier outage (pushed before
    the last good publish) or no note at all: False, and this monitor pushes as before."""
    try:
        rec = ((st or {}).get("_phone_dedupe") or {}).get("database") or {}
        at = float(rec.get("at") or 0)
        if not at or not rec.get("set") or publish_age is None:
            return False
        return at >= now_epoch - float(publish_age)
    except Exception:
        return False


# -- the checks -------------------------------------------------------------------------------
def check_exec(snap, now_et, mstate, ev):
    out = []
    if not ev["readable"]:
        out.append(_verdict("exec_state", "exec", False, HIGH,
                            "cannot read the executor's state.json",
                            f"qqq_exec/state.json is {snap.get('exec_state_err')}", min_runs=2,
                            plain=_plain("The QQQ order program's state file cannot be read.",
                                         affects="the QQQ book may not be trading")))
        # the other executor checks cannot be judged this run: unknown, not recovered
        out += [_verdict(k, "exec", None, HIGH, k)
                for k in ("exec_publish", "exec_suppress", "exec_loop")]
        return out
    out.append(_verdict("exec_state", "exec", True, HIGH, "executor state.json readable"))
    armed = snap.get("broker_mode") in ("PAPER", "LIVE")
    sev_live = URGENT if (armed and in_session(now_et)) else HIGH
    limit = max(PUBLISH_STALE_FLOOR_SEC, PUBLISH_STALE_MARGIN * ev["renew"])
    age = ev["publish_age"]
    stale = age is None or age > limit
    standby = " A standby marker is present (another host holds the lease)." \
        if snap.get("standby_mtime") else ""
    now_epoch = now_et.timestamp()
    last_seen = ("at " + ntfy_push.hhmm(now_epoch - age, now=now_epoch)) if age is not None else None
    exec_paged_db = _exec_pushed_database(snap.get("exec_state"), now_epoch, age)
    out.append(_verdict(
        "exec_publish", "exec", not stale, sev_live,
        "executor Firestore publish DOWN",
        f"last good publish {ev['last_ok'] or 'never'} ET ({fmt_age(age)} ago, limit "
        f"{fmt_age(limit)}). The board is frozen and, while armed, every broker send is "
        f"blocked (fail-CLOSED).{standby}",
        plain=_plain(("The QQQ order program stopped reporting %s - the board is frozen." % last_seen)
                     if last_seen else "The QQQ order program has not reported since it started.",
                     affects=NO_ORDERS if armed else None),
        quiet=exec_paged_db))
    # "suppressing broker sends" -- the lease read failed and a real order was blocked
    log_state = mstate.setdefault("exec_log", {})
    hits, new_off = snap.get("_suppress_hits", 0), snap.get("_suppress_offset")
    if new_off is not None:
        log_state["offset"] = new_off
    now_epoch = now_et.timestamp()
    times = [t for t in log_state.get("hits", []) if now_epoch - t <= SUPPRESS_WINDOW_SEC]
    times.extend([now_epoch] * int(hits))
    log_state["hits"] = times[-200:]
    st = snap["exec_state"]
    cleared = hits == 0 and st.get("_broker_lease_ok") is True
    bad = len(times) >= SUPPRESS_MIN_HITS and not cleared
    out.append(_verdict(
        "exec_suppress", "exec", not bad, sev_live,
        "executor is BLOCKING broker sends",
        f"{len(times)} 'suppressing broker sends' line(s) in qqq_exec.log in the last "
        f"{SUPPRESS_WINDOW_SEC / 60:.0f} min -- the lease read is failing, so no real order "
        f"can go out (reason: {st.get('_broker_lease_reason') or 'n/a'}).",
        plain=_plain("The QQQ order program is blocking its own orders - its safety check "
                     "against a second copy is failing.", affects=NO_ORDERS),
        quiet=exec_paged_db))
    loop_age = ev["loop_age"]
    silent = loop_age is None or loop_age > EXEC_LOOP_SILENT_SEC
    # 10-08 review (plan "Tick loop crashing vs stuck"): while the executor's own crash note is
    # out and its tick_crash.json marker is FRESH (tick_crash_open), the loop is crashing, not
    # stuck -- the executor owns it; exec_loop is tracked (JSON, status) without a push. A
    # stale marker (the crash turned into a hang, or the process died) never silences it.
    out.append(_verdict(
        "exec_loop", "exec", not silent, HIGH, "executor tick loop not running",
        f"no tick for {fmt_age(loop_age)} (SERVING.lock / state.json not rewritten). The "
        f"process is wedged, crash-looping or standing by.{standby}",
        plain=_plain(("The QQQ order program has been stuck for %s." % _plain_age(loop_age))
                     if loop_age is not None else "The QQQ order program is not running.",
                     affects="the QQQ book is not running"),
        quiet=tick_crash_open(snap, now_et, loop_age)))
    return out


def check_systemd(snap):
    units = snap.get("failed_units")
    if units is None:
        return None
    return [_verdict(f"failed_unit:{u}", "systemd", False, HIGH, f"box unit FAILED: {u}",
                     f"systemctl --failed lists {u} (journalctl -u {u} for why)",
                     plain=_unit_plain(u))
            for u in units]


def _unit_plain(unit):
    word, trades = UNIT_WORDS.get(unit, (None, False))
    if word is None:
        name = unit[:-len(".service")] if unit.endswith(".service") else unit
        return _plain("The cloud box service %s failed." % name, area=BOX)
    return _plain("%s failed on the cloud box." % word,
                  affects=("the QQQ book is not running" if trades else None),
                  area=BOOK if trades else BOX)


def check_disk(snap):
    out = []
    pct = snap.get("disk_pct")
    if pct is not None:
        out.append(_verdict("disk", "disk", pct < DISK_PCT_MAX, HIGH, "box disk filling up",
                            f"{pct:.0f}% used (limit {DISK_PCT_MAX:.0f}%)",
                            plain=_plain("The cloud box disk is %.0f%% full." % pct, area=BOX)))
    big = snap.get("big_logs") or []
    out.append(_verdict("log_size", "disk", not big, MEDIUM, "a box log is over 100 MB",
                        ", ".join(f"{n} {s / 1048576:.0f} MB" for n, s in big)
                        + " -- a logger is flooding or logrotate is not running",
                        plain=_plain("A log file on the cloud box is over 100 MB.", area=BOX)))
    return out


def _keel_behind(through, want):
    """Trading sessions between a KEEL summary's data_through and the session it should be
    trained through (0 = current); None when data_through is missing or unreadable."""
    try:
        if not through:
            return None
        start = _dt.date.fromisoformat(str(through)[:10])
        return max(0, len(market_calendar.sessions_between(start, want)) - 1)
    except Exception:
        return None


def _keel_leg_word(name):
    """'NOISE_382_v12' -> 'NOISE'."""
    head = str(name or "NOISE").split("_")[0]
    return {"ENGUQ": "ENGU-Q"}.get(head, head)


def check_evening(snap, now_et, mstate=None):
    """NQ master freshness against the latest session whose 18:00 ET has passed (WEBULL PUSH
    PLAN 10-07: before the 18:30 ET rebuild), KEEL freshness against the latest session whose
    19:00 ET has passed. See the module docstring (nq_master, keel:<leg>,
    keel_fallback:<leg>) for who pushes what."""
    nq_due = latest_session_due(now_et, NQ_CHECK_FROM)
    due = latest_session_due(now_et, EVENING_CHECK_FROM)
    if due is None and nq_due is None:
        return None
    alerts = (mstate or {}).get("alerts") or {}
    out = []
    nq_bad = False
    if nq_due is not None:
        nq = snap.get("nq_last")
        nq_day = epoch_to_et_date(nq) if nq else None
        marker = snap.get("nq_marker") or {}
        cut_short = marker.get("incomplete_day") == nq_due.isoformat()
        nq_bad = nq_day is None or nq_day < nq_due or cut_short
        deadline = ntfy_push.hhmm(at(nq_due, KEEL_REBUILD_AT).timestamp(),
                                  now=now_et.timestamp())
        if now_et < at(nq_due, KEEL_REBUILD_AT):
            act = f"run the upload on the PC before {deadline}, or " + ASK
        else:
            act = "run the upload on the PC (the model rebuilds when it lands), or " + ASK
        out.append(_verdict(
            "nq_master", "evening", not nq_bad, HIGH, "NQ master on the box is behind",
            (f"last bar {nq_day or 'missing'}, expected {nq_due}"
             + (f" -- keel_live_state found {nq_due} INCOMPLETE in the file" if cut_short else "")
             + " -- the PC's 17:20 ET push did not land a current file, so the 18:30 ET KEEL "
               "build trains on old data."),
            plain=_plain(("The PC's after-close NQ data upload reached the cloud box cut short "
                          "(its last day is incomplete).") if cut_short and nq_day is not None
                         and nq_day >= nq_due else
                         "The PC's after-close NQ data upload did not reach the cloud box.",
                         action=act, priority="default")))
    if due is None:
        return out
    # a KEEL miss that opens while the NQ data is missing is the SAME missed night: tracked,
    # folded into the nq_master note (quiet), never a second push
    fold = nq_bad or bool((alerts.get("nq_master") or {}).get("open"))
    want = keel_expected(due)
    keel = snap.get("keel") or {}
    if not keel:
        out.append(_verdict("keel:none", "evening", False, HIGH, "no KEEL summary on the box",
                            "cloud_signal/keel has no *_summary.json",
                            plain=_plain("The KEEL sizing model is missing on the cloud box.",
                                         affects="the QQQ book sizes NOISE trades without its model")))
    for leg, through in sorted(keel.items()):
        ok = bool(through) and str(through) >= want.isoformat()
        behind = _keel_behind(through, want)
        w = _keel_leg_word(leg)
        # an unreadable age (behind None) is NOT a fallback: api/cloud_signal keeps using
        # a model whose summary carries no session date (keel:<leg> names it, at default)
        old_enough = behind is not None and behind >= KEEL_FALLBACK_SESSIONS
        out.append(_verdict(
            f"keel:{leg}", "evening", ok, HIGH, f"KEEL STALE ({leg}), still sizing",
            f"trained through {through or 'unknown'}, expected {want}"
            + (f" ({behind} session(s) behind)" if behind is not None else "")
            + ". The live leg keeps sizing on the stale model until it is rebuilt.",
            plain=_plain(("The KEEL sizing model was not rebuilt after the close (it is %d "
                          "session%s old)." % (behind, "" if behind == 1 else "s")) if behind else
                         "The KEEL sizing model was not rebuilt after the close.",
                         priority="default"),
            quiet=fold and not ok))
        out.append(_verdict(
            f"keel_fallback:{leg}", "evening", ok or not old_enough, HIGH,
            f"KEEL TOO OLD ({leg}): sizing falls back to 1.0",
            f"trained through {through or 'unknown'}, expected {want} -- past "
            f"api/cloud_signal's KEEL_MAX_STALE_SESSIONS from the next session on: the live "
            f"leg sizes at 1.0 (no model) until it is rebuilt.",
            plain=_plain("The KEEL sizing model is %s sessions old, too old to use from the "
                         "next session." % (behind if behind is not None else "too many"),
                         affects=f"{w} trades at base size without its sizing model",
                         priority="high")))
    return out


# the executor refreshes its tick_crash.json marker on every failed tick (every ~5 s): one
# older than this belongs to a process that has since hung or died, not a live crash loop
TICK_CRASH_MARKER_FRESH_SEC = 120.0


def tick_crash_open(snap, now_et, loop_age):
    """True while the executor's tick crash episode is open: its tick_crash.json marker is
    present, was written no earlier than the last good tick (SERVING.lock / state.json), so a
    marker an older process left behind never silences a later stall, and is fresh (at most
    TICK_CRASH_MARKER_FRESH_SEC old), so a crash that turned into a hang -- or a process that
    died mid-crash with nothing after it to remove the marker -- is paged as usual."""
    marker = snap.get("tick_crash")
    if not isinstance(marker, dict):
        return False
    try:
        at = float(marker.get("at_epoch"))
    except (TypeError, ValueError):
        at = snap.get("tick_crash_mtime")
    if at is None:
        return False
    if now_et.timestamp() - float(at) > TICK_CRASH_MARKER_FRESH_SEC:
        return False
    if loop_age is None:
        return True
    last_tick = now_et.timestamp() - float(loop_age)
    return at >= last_tick - 1.0


def check_session(snap, now_et, mstate, ev):
    if not in_session(now_et):
        return None
    out = []
    now_epoch = now_et.timestamp()
    # engine heartbeat (#5)
    hb = snap.get("cs_hb") if isinstance(snap.get("cs_hb"), dict) else {}
    ts = parse_iso(hb.get("ts")) if hb else None
    age = (now_epoch - ts.timestamp()) if ts else None
    bad = age is None or age > ENGINE_HB_STALE_SEC or hb.get("ok") is False
    out.append(_verdict(
        "engine_hb", "session", not bad, HIGH, "signal engine STALLED",
        f"cloud_signal heartbeat {fmt_age(age)} old, ok={hb.get('ok')} "
        f"({hb.get('note') or snap.get('cs_hb_err') or ''}). New entries are blocked while "
        f"it is stale, lot or no lot.", min_runs=2,
        plain=_plain(_engine_problem(age, hb, snap), affects="the QQQ book cannot open new trades")))
    # newest closed 5m bar (#6) and its source (#15)
    cs = snap.get("cs_state") if isinstance(snap.get("cs_state"), dict) else {}
    src = ((cs.get("bar_source") or {}).get("5m") or {}) if cs else {}
    # the engine's own FEED HEALTH fields (api/cloud_signal.py, 2026-10-05), trusted only
    # while its heartbeat is fresh; absent on an older engine -- then nothing changes
    hb_fresh = bool(hb) and age is not None and age <= ENGINE_HB_STALE_SEC
    hb_bar_epoch = hb.get("newest_closed_bar_epoch") if hb_fresh else None
    newest = src.get("newest_epoch") or hb_bar_epoch or snap.get("qqq_5m_last")
    d = now_et.date()
    open_dt = at(d, SESSION_OPEN)
    if now_et >= open_dt + _dt.timedelta(minutes=BAR_CHECK_AFTER_OPEN_MIN):
        bar_age = (now_epoch - (float(newest) + BAR_SEC)) if newest else None
        stale = bar_age is None or bar_age > BAR_CLOSE_STALE_SEC
        engine_says = ""
        engine_paged = False
        if hb_fresh and "stalled" in hb:
            stale = stale or hb.get("stalled") is True
            # an engine that writes these fields pages this same episode itself ("BARS
            # STOPPED", within one step of the same 660 s limit): track it here for the board
            # but do not page it a second time. Not keyed on stalled=true alone: this run can
            # land just before the engine's next step flips it, and would then page as well.
            engine_paged = True
            engine_says = (f" The engine says {hb.get('verdict') or 'n/a'}: "
                           f"{hb.get('bars_missing')} of today's {hb.get('bars_due')} bar(s) "
                           f"missing.")
        out.append(_verdict(
            "bar_age", "session", not stale, HIGH, "5m bars STOPPED arriving",
            f"newest closed 5m bar closed {fmt_age(bar_age)} ago (limit "
            f"{BAR_CLOSE_STALE_SEC:.0f}s); the heartbeat can still say ok while no ENTRY or "
            f"EXIT can be produced.{engine_says}",
            plain=_plain(("The newest QQQ price bar is %s old." % _plain_age(bar_age))
                         if bar_age is not None else "No QQQ price bars are arriving.",
                         affects="the QQQ book cannot enter or exit trades"),
            quiet=engine_paged))
    source = src.get("source")
    out.append(_verdict(
        "bar_source", "session", (source != "yfinance") if source else None, HIGH,
        "live bars falling back to yfinance",
        "the 5m cache is being filled from yfinance, not Webull (bars 30-90 s late); "
        "check the Webull token / REST in cloud_signal.log.", min_runs=2,
        plain=_plain("QQQ prices are coming from the slower backup source, not Webull.",
                     affects="the QQQ book trades on late prices"),
        # an engine that writes yf_fallback_streak pages this itself (feed on backup prices)
        quiet=hb_fresh and "yf_fallback_streak" in hb))
    # the daily cache (#14): the engine's ~09:35 refresh must have added the previous session
    if hhmm(now_et) >= QQQ_1D_CHECK_FROM:
        want = prev_session(d)
        d1_day = qqq_1d_day(snap)
        out.append(_verdict(
            "qqq_1d", "session", d1_day is not None and want is not None and d1_day >= want,
            HIGH, "QQQ daily cache not refreshed",
            f"QQQ_1d newest bar {d1_day or 'missing'}, expected {want} after the engine's "
            f"~09:35 ET refresh -- NOISE's vol look-back is a session short (the refresh is "
            f"tried once a day: see cloud_signal.log 'QQQ daily cache refresh').",
            min_runs=2,
            plain=_plain("The QQQ daily price history was not updated this morning.",
                         affects=SHORT_HISTORY)))
    # tick gaps (#3)
    st = snap.get("exec_state") if isinstance(snap.get("exec_state"), dict) else {}
    seen = mstate.setdefault("tick_gap_seen", {})
    day = st.get("_tick_gap_day")
    try:
        gmax = float(st.get("tick_gap_max_s_today") or 0.0)
    except (TypeError, ValueError):
        gmax = 0.0
    rose = (seen.get("day") == day and gmax > float(seen.get("max") or 0.0)
            and gmax > TICK_GAP_SESSION_SEC)
    seen.update({"day": day, "max": gmax})
    loop_age = ev.get("loop_age")
    gap_now = loop_age is not None and loop_age > TICK_GAP_SESSION_SEC
    # WEBULL PUSH PLAN 10-07 ("Tick loop crashing vs stuck"): while the executor's own tick
    # crash episode is open it owns the problem -- tick_gap is tracked (JSON, status) without
    # a second push. 10-08 review: read from its tick_crash.json marker (api/qqq_exec
    # TICK_CRASH_MARKER), never state.json -- a failed tick never saves state.json
    crash_open = tick_crash_open(snap, now_et, loop_age)
    out.append(_verdict(
        "tick_gap", "session", not (gap_now or rose), HIGH, "executor tick loop STALLING",
        f"current gap {fmt_age(loop_age)}, today's max {gmax:.0f}s (limit "
        f"{TICK_GAP_SESSION_SEC:.0f}s) -- entries, exits and the EOD rails run late.",
        plain=_plain("The QQQ order program stalled for %s." % _plain_age(loop_age if gap_now else gmax),
                     affects="the QQQ book's entries and exits run late"),
        quiet=crash_open))
    # shadow legs heartbeat (#25)
    sh = snap.get("shadow_hb") if isinstance(snap.get("shadow_hb"), dict) else {}
    sts = parse_iso(sh.get("ts")) if sh else None
    sage = (now_epoch - sts.timestamp()) if sts else None
    sbad = sage is None or sage > SHADOW_HB_STALE_SEC or sh.get("ok") is False
    out.append(_verdict(
        "shadow_hb", "session", not sbad, MEDIUM, "shadow legs heartbeat stale",
        f"shadow heartbeat {fmt_age(sage)} old, ok={sh.get('ok')} -- the forward log can "
        f"lose rows.", min_runs=2,
        plain=_plain("The QQQ shadow strategies (not traded) stopped reporting - their forward "
                     "record can miss rows.", priority="low")))
    return out


def _open_lot_words(snap):
    """', with an open NOISE trade' from the executor's state.json legs ('' when flat) -- the
    ONE signal-stall pusher names what rides unmanaged (WEBULL PUSH PLAN 10-07: the executor
    no longer pushes its own stall note)."""
    st = (snap or {}).get("exec_state") if isinstance((snap or {}).get("exec_state"), dict) else {}
    legs = sorted((st.get("legs") or {}).keys()) if isinstance(st.get("legs"), dict) else []
    if not legs:
        return ""
    ws = [{"ENGUQ": "ENGU-Q"}.get(str(x), str(x)) for x in legs]
    return ", with an open %s trade" % (" and ".join(ws) if len(ws) < 3 else ", ".join(ws))


def _engine_problem(age, hb, snap=None):
    lot = _open_lot_words(snap)
    if age is not None and age <= ENGINE_HB_STALE_SEC and hb.get("ok") is False:
        return "The QQQ signal program reports a problem%s." % lot
    if age is None:
        return "The QQQ signal program is not reporting%s." % lot
    return "The QQQ signal program has not reported for %s%s." % (_plain_age(age), lot)


def check_eod(snap, now_et):
    d = now_et.date()
    if not market_calendar.is_session(d) or hhmm(now_et) < EOD_CHECK_FROM:
        return None
    today = d.isoformat()
    st = snap.get("exec_state") if isinstance(snap.get("exec_state"), dict) else {}
    out = []
    done = st.get("eod_summary_done_date") == today
    out.append(_verdict(
        "eod_summary", "eod", done, URGENT, "EOD did not run",
        f"eod_summary_done_date is {st.get('eod_summary_done_date')}, not {today} -- the "
        f"executor was down or stalled at the close: CHECK WEBULL IS FLAT BY HAND.",
        plain=_plain("The QQQ book's end-of-day close did not run.", action=FLAT_DO,
                     affects=MAY_HOLD)))
    flat = st.get("_webull_flat_after_eod") or {}
    flat_ok = flat.get("date") == today and flat.get("flat") is True
    sev = URGENT
    # A KILL file left over from an earlier day: the executor skips its flat_by flatten while
    # it is present (so flat_by_done_date is never today) and kill_flatten_date is stamped only
    # on the day the KILL first fired -- the post-close flat check cannot run, every day the
    # file stays. Still reported (nobody has read Webull's position), but HIGH and saying why,
    # not an URGENT "not flat" page each afternoon for a book the owner halted on purpose.
    kills = snap.get("exec_kill_files")
    if kills is None:
        kills = snap.get("kill_files") or []
    affects = MAY_HOLD
    if flat.get("date") != today and kills:
        sev = HIGH
        why = (f"the book is HALTED by a KILL file "
               f"({', '.join(os.path.basename(p) for p in kills)}), so the executor's "
               f"post-close Webull flat check cannot run (last {flat.get('date')})")
        problem = "The QQQ book is halted, so its after-close Webull position check cannot run."
        affects = "the QQQ book is halted and nobody has confirmed Webull is flat"
    elif flat.get("date") != today:
        why = f"the post-close Webull flat check did not run today (last {flat.get('date')})"
        problem = "The after-close Webull position check did not run today."
    elif flat.get("flat") is False:
        why = f"Webull still holds {flat.get('shares')} QQQ after the close"
        problem = "Webull still holds %s QQQ shares after the close." % flat.get("shares")
    else:
        why = "the post-close Webull position read could not be verified"
        problem = "The after-close Webull position could not be read."
    # ONE OWNER (WEBULL PUSH PLAN 10-07): a RESULT of the executor's own check (not flat /
    # could not read) was already pushed by the executor -- tracked here, not pushed again.
    # Only when the executor stamped that its note went out ("pushed", 10-08 fourth review):
    # a note whose one send failed is pushed here instead of by nobody
    exec_owns = (flat.get("date") == today and flat.get("flat") is not True
                 and flat.get("pushed") is True)
    out.append(_verdict("webull_flat", "eod", flat_ok, sev, "Webull NOT confirmed flat",
                        why + " -- check the Webull app and sell by hand if needed.",
                        plain=_plain(problem, action=FLAT_DO, affects=affects),
                        quiet=exec_owns))
    cs = snap.get("cs_state") if isinstance(snap.get("cs_state"), dict) else {}
    settled = today in ((cs or {}).get("eod_settled") or {})
    # ONE ALERTER PER PROBLEM (api/ntfy_push): this check is the only pusher of "today's close
    # was not settled". The engine records WHY it gave up (eod_gave_up[today]) without pushing,
    # and the executor turns that into a board event without pushing; an engine that was down
    # through the window leaves no record at all -- this check covers both.
    gave = ((cs or {}).get("eod_gave_up") or {}).get(today)
    why = (gave.get("why") if isinstance(gave, dict) else None) or ""
    if not gave:
        problem = ("The signal program did not settle today's close, so today's exits are "
                   "recorded late.")
        dev_why = "no eod_gave_up record either -- the engine may have been down at the close"
    elif why.startswith("the last bar never arrived"):
        problem = "Today's last QQQ price bar never came, so today's exits are recorded late."
        dev_why = f"the engine gave up: {why}"
    else:
        problem = ("The signal program's end-of-day step failed, so today's exits are "
                   "recorded late.")
        dev_why = f"the engine gave up: {why or 'no reason recorded'}"
    out.append(_verdict(
        "eod_settled", "eod", settled, HIGH, "EOD bars never settled",
        f"cloud_signal eod_settled has no {today} ({dev_why}) -- today's exits post tomorrow "
        f"with an old ref_time.",
        plain=_plain(problem)))
    return out


# -- pre-open gate ----------------------------------------------------------------------------
def preopen_slot(now_et):
    d = now_et.date()
    if not market_calendar.is_session(d):
        return None
    hm = hhmm(now_et)
    if PREOPEN_SLOTS[0] <= hm < PREOPEN_SLOTS[1]:
        return "%02d:%02d" % PREOPEN_SLOTS[0]
    if PREOPEN_SLOTS[1] <= hm < SESSION_OPEN:
        return "%02d:%02d" % PREOPEN_SLOTS[1]
    return None


def preopen_checks(snap, now_et, ev):
    """Every pre-open miss as {"id", "text", "problem", "action", "affects", "priority"}: `text` is
    the developer line (status.json slots, the alert detail, the PC relay); the rest is the phone
    wording (PHONE TEXT). An empty list = ready."""
    d = now_et.date()
    now_epoch = now_et.timestamp()
    prev = prev_session(d)
    misses = []

    def miss(mid, text, problem, action=ASK, affects=MAY_NOT_TRADE):
        misses.append({"id": mid, "text": text, "problem": problem, "action": action,
                       "affects": affects, "priority": "high" if affects else "default"})
    want = keel_expected(prev) if prev else None
    keel = snap.get("keel") or {}
    if not keel:
        miss("keel", "no KEEL summary on the box",
             "The KEEL sizing model is missing on the cloud box.",
             affects="the QQQ book sizes NOISE trades without its model")
    for leg, through in sorted(keel.items()):
        if want and (not through or str(through) < want.isoformat()):
            # WEBULL PUSH PLAN 10-07: a model 1-4 sessions old still sizes (default); only
            # at the fallback age (api/cloud_signal sizes at 1.0) is trading affected (high)
            behind = _keel_behind(through, want)
            fallback = behind is not None and behind >= KEEL_FALLBACK_SESSIONS
            miss("keel:" + leg, f"KEEL {leg} trained through {through}, expected {want}",
                 "The KEEL sizing model was not rebuilt after the last close.",
                 affects=OLD_MODEL if fallback else None)
    # QQQ_1d.csv is refreshed by cloud_signal's step(), which only runs in RTH, at most once
    # per calendar day (_maybe_refresh_daily_cache): the previous session's bar first lands
    # at about 09:35 ET. Before the open the most the cache can hold is the session BEFORE
    # the previous one -- anything older is the #14 miss. check_session's qqq_1d verdict
    # then expects the previous session itself from 09:40 ET.
    d1_want = prev_session(prev) if prev else None
    d1_day = qqq_1d_day(snap)
    if d1_want and (d1_day is None or d1_day < d1_want):
        miss("qqq_1d", f"QQQ_1d newest bar {d1_day or 'missing'}, expected {d1_want} or "
                       f"newer (NOISE look-back truncated)",
             "The QQQ daily price history is out of date.", affects=SHORT_HISTORY)
    limit = max(PREOPEN_LEASE_FLOOR_SEC, PREOPEN_LEASE_MARGIN * ev["renew"])
    if not ev["readable"]:
        miss("exec_state", "executor state.json unreadable",
             "The QQQ order program's state file cannot be read.")
    elif ev["publish_age"] is None or ev["publish_age"] > limit:
        miss("lease", f"lease not fresh: last publish {fmt_age(ev['publish_age'])} ago "
                      f"(limit {fmt_age(limit)})",
             ("The QQQ order program has not reported for %s." % _plain_age(ev["publish_age"]))
             if ev["publish_age"] is not None else "The QQQ order program is not reporting.")
    st = snap.get("exec_state") if isinstance(snap.get("exec_state"), dict) else {}
    if st.get("trading_day") == d.isoformat() and (st.get("breaker_tripped")
                                                   or st.get("kill_done")):
        miss("halted", "book HALTED today (breaker or kill)",
             "The QQQ book is halted for today (loss limit or kill switch).",
             action="nothing if it was halted on purpose, else " + ASK)
    for p in snap.get("kill_files") or []:
        where = f"{os.path.basename(os.path.dirname(p))}/{os.path.basename(p)}"
        miss("kill:" + where, f"KILL file present: {where}", "The QQQ book's kill switch is on.",
             action="nothing if it was switched on on purpose, else " + ASK)
    hb = snap.get("cs_hb") if isinstance(snap.get("cs_hb"), dict) else {}
    ts = parse_iso(hb.get("ts")) if hb else None
    age = (now_epoch - ts.timestamp()) if ts else None
    if age is None or age > ENGINE_HB_STALE_SEC or hb.get("ok") is False:
        miss("engine", f"signal engine heartbeat {fmt_age(age)} old, ok={hb.get('ok')}",
             _engine_problem(age, hb))
    tokens = snap.get("tokens") or {}
    if not tokens:
        miss("token", "no Webull token file on the box",
             "The Webull login is missing on the cloud box.")
    for name, (expires, status) in sorted(tokens.items()):
        login = "The Webull paper login" if "paper" in name else "The Webull login"
        if status != "NORMAL":
            miss("token_status:" + name,
                 f"Webull token ({name}) status {status or 'unknown'} -- approve it "
                 f"in the Webull app", login + " needs approval.",
                 action="approve the login in the Webull app")
        if expires is None:
            miss("token_expiry:" + name, f"Webull token ({name}) expiry unreadable",
                 login + "'s expiry date cannot be read.", affects=None)
        elif expires - now_epoch < TOKEN_MIN_DAYS * 86400:
            days = (expires - now_epoch) / 86400
            miss("token_expires:" + name,
                 f"Webull token ({name}) expires in {days:.1f} days",
                 (login + " expires in %.0f days." % days) if days >= 1.5 else
                 (login + " expires within a day." if days > 0 else login + " has expired."),
                 affects=None if days > 0 else MAY_NOT_TRADE)
    return misses


def preopen_misses(snap, now_et, ev):
    """The developer lines of preopen_checks() -- what status.json's slots and the alert detail
    carry ([] = ready)."""
    return [m["text"] for m in preopen_checks(snap, now_et, ev)]


def _keel_miss_pushed(mid, alerts):
    """True for a pre-open KEEL miss ("keel" / "keel:<leg>") whose problem an OPEN episode
    already pushed: nq_master (the missed night), keel:<leg> (a quiet one was folded into
    the nq_master note), keel_fallback:<leg>, or keel:none. Any other miss: False."""
    def is_open(key, loud_only=False):
        r = alerts.get(key) or {}
        return bool(r.get("open")) and not (loud_only and r.get("quiet"))
    if mid == "keel":
        return is_open("keel:none", loud_only=True)
    if not mid.startswith("keel:"):
        return False
    leg = mid[len("keel:"):]
    # a QUIET keel:<leg> was folded into the nq_master note: it counts only while that
    # episode is open (the nq_master test above); once the data landed and nq_master closed,
    # a model still not rebuilt has never been named on the phone, so the gate says it
    return (is_open("nq_master", loud_only=True) or is_open("keel:" + leg, loud_only=True)
            or is_open("keel_fallback:" + leg, loud_only=True))


def preopen_step(snap, now_et, mstate, alerts, ev):
    """Runs the gate once per slot. Returns [(title, message, priority)] to push (PHONE TEXT: a
    miss pushes once a day unless a NEW or WORSE miss shows up at the later slot; the first
    passing slot of the day, or the first after a miss, pushes one low "QQQ book: OK")."""
    slot = preopen_slot(now_et)
    if slot is None:
        return []
    today = now_et.date().isoformat()
    po = mstate.get("preopen") or {}
    if po.get("date") != today:
        po = {"date": today, "slots": {}, "ready_pushed": False}
    mstate["preopen"] = po
    if slot in po["slots"]:
        return []
    checks = preopen_checks(snap, now_et, ev)
    misses = [m["text"] for m in checks]
    po["slots"][slot] = {"at": now_et.strftime("%H:%M"), "misses": misses}
    now_epoch = now_et.timestamp()
    if misses:
        hold = max(0.0, at(now_et.date(), SESSION_OPEN).timestamp() - now_epoch)
        rec = alerts.get("preopen") or {"opened_epoch": now_epoch,
                                         "opened_et": now_et.strftime("%a %m-%d %H:%M ET")}
        rec.update({"key": "preopen", "group": "preopen", "open": True, "severity": URGENT,
                    "title": "QQQ book NOT ready", "detail": "; ".join(misses),
                    "last_bad_epoch": now_epoch, "hold_sec": hold, "quiet_expire": True,
                    "bad_runs": int(rec.get("bad_runs", 0)) + 1})
        alerts["preopen"] = rec
        # a KEEL miss an open episode already pushed (the missed night) stays in the JSON and
        # status only -- no second buzz the next morning (WEBULL PUSH PLAN 10-07)
        loud = [m for m in checks if not _keel_miss_pushed(m["id"], alerts)]
        if len(loud) < len(checks):
            po["keel_already_pushed"] = [m["id"] for m in checks if m not in loud]
        if not loud:
            return []
        # the same misses push once a day (po starts fresh each day); a new or worse one at once
        action, po["push"] = ntfy_push.dedupe(
            {m["id"]: ntfy_push.RANK[m["priority"]] for m in loud}, po.get("push") or {},
            now_epoch, ntfy_push.DAY_S)
        if action != "push":
            return []
        # among equally serious misses, the ones only the owner can fix lead the note
        lead = sorted(loud, key=lambda m: m["id"].split(":")[0] not in OWNER_FIXES)
        note = compose_note([dict(m, area=BOOK, rank=ntfy_push.RANK[m["priority"]])
                             for m in lead])
        return [(note["title"], note["message"], note["priority"])]
    fixed = alerts.pop("preopen", None)
    po["push"] = {}
    if fixed is None and po.get("ready_pushed"):
        return []
    po["ready_pushed"] = True
    note = ntfy_push.plain(BOOK, "OK", None, "The QQQ paper book passed its %s pre-open check."
                           % ntfy_push.hhmm(now_epoch, now=now_epoch), "nothing", priority="low")
    return [(note["title"], note["message"], note["priority"])]


# -- episodes ---------------------------------------------------------------------------------
def apply_verdicts(alerts, verdicts, groups_ran, now_epoch, now_label):
    """Fold this run's verdicts into the persistent `alerts` dict (key -> record).
    Returns (opened, recovered, expired) lists of record copies:
      opened     a check failing for its min_runs-th run in a row (the episode starts: push)
      recovered  an open episode whose check passed, or whose group ran without it (a
                 dynamic key such as a failed unit that is no longer failed)
      expired    an open episode whose check stopped being evaluated (its window ended)
                 for longer than its hold_sec -- closed without proof it recovered
    A verdict with ok=None (could not tell this run) leaves its record exactly as it was.
    Pending (not yet open) records reset whenever their check passes or stops running.
    A verdict marked window_alert (the PC's relay of a box alert that closes when its window
    ends, e.g. the pre-open gate at 09:30) is reported as EXPIRED, not recovered, when its
    group runs without it: it went away, nobody saw it pass."""
    seen = set()
    opened, recovered, expired = [], [], []
    for v in verdicts:
        key = v["key"]
        seen.add(key)
        rec = alerts.get(key)
        if v["ok"] is None:
            continue
        if not v["ok"]:
            if rec is None:
                rec = alerts[key] = {"key": key, "open": False, "bad_runs": 0}
            rec["bad_runs"] = int(rec.get("bad_runs", 0)) + 1
            rec.update({"group": v["group"], "severity": v["severity"], "title": v["title"],
                        "detail": v["detail"], "last_bad_epoch": now_epoch,
                        "last_bad_et": now_label, "hold_sec": v.get("hold_sec", 0.0),
                        "window_alert": bool(v.get("window_alert"))})
            if v.get("plain") is not None:
                rec["plain"] = v["plain"]
            if not rec.get("open") and rec["bad_runs"] >= int(v.get("min_runs", 1)):
                rec.update({"open": True, "opened_epoch": now_epoch, "opened_et": now_label,
                            "quiet": bool(v.get("quiet"))})
                opened.append(dict(rec))
        elif rec is not None:
            if rec.get("open"):
                recovered.append(dict(rec))
            del alerts[key]
    for key, rec in list(alerts.items()):
        if key in seen:
            continue
        if rec.get("group") in groups_ran:
            if rec.get("open"):
                (expired if rec.get("window_alert") else recovered).append(dict(rec))
            del alerts[key]
        elif now_epoch - float(rec.get("last_bad_epoch", 0.0)) > float(rec.get("hold_sec", 0.0)):
            if rec.get("open") and not rec.get("quiet_expire"):
                expired.append(dict(rec))
            del alerts[key]
    return opened, recovered, expired


def _rec_plain(rec):
    """An episode's phone wording; a record saved before PHONE TEXT existed (no "plain") gets a
    generic one, so a deploy in the middle of an episode never pushes developer text."""
    p = rec.get("plain") if isinstance(rec.get("plain"), dict) else None
    return p or _plain("A QQQ book check is failing.")


def _rec_priority(rec):
    """ntfy priority of an episode's push: the check's own when it set one; else urgent / high
    when trading is affected (urgent only where the check's severity is URGENT), default when
    it is not."""
    if not isinstance(rec.get("plain"), dict):     # saved before PHONE TEXT: as it was pushed
        return {URGENT: "urgent", HIGH: "high"}.get(rec.get("severity"), "default")
    p = _rec_plain(rec)
    if p.get("priority") in ntfy_push.RANK:
        return p["priority"]
    if p.get("affects"):
        return "urgent" if rec.get("severity") == URGENT else "high"
    return "default"


def _desc(rec):
    p = _rec_plain(rec)
    prio = _rec_priority(rec)
    return {"area": p.get("area") or BOOK, "affects": p.get("affects"), "problem": p.get("problem"),
            "action": p.get("action") or ASK, "priority": prio, "rank": ntfy_push.RANK[prio]}


def compose_note(descs):
    """ONE plain note for one or more problems ({area, affects, problem, action, priority, rank}):
    the worst leads -- its area, its fix, its priority; the Trading line names the first thing
    that is affected; the problem line is the lead problem "+N more" (repeated sentences, e.g.
    two KEEL legs, count once). Title status: CHECK NOW (trading affected), needs a fix
    (default), heads up (low)."""
    ds = sorted(descs, key=lambda d: -int(d["rank"]))
    lead = ds[0]
    affects = next((d["affects"] for d in ds if d.get("affects")), None)
    problems = list(dict.fromkeys(d["problem"] for d in ds if d.get("problem")))
    status = "CHECK NOW" if affects else ("needs a fix" if lead["rank"] >= 1 else "heads up")
    return ntfy_push.plain(lead["area"], status, affects, ntfy_push.join_problems(problems, limit=1),
                           lead["action"], priority=lead["priority"])


def compose_pushes(opened, recovered, expired):
    """At most two pushes per run, in the plain format (PHONE TEXT): one for every episode that
    started, and one low "OK" for the episodes that ended -- only when one of them had pushed
    high or urgent. Episodes that EXPIRED (window ended, never seen fixed) are not pushed: the
    opening push already said what to do; the log, status.json and the PC relay keep them.
    A QUIET episode (another sender pages it -- see _verdict) is left out of both.
    [(title, message, ntfy priority)]."""
    opened = [r for r in opened if not r.get("quiet")]
    recovered = [r for r in recovered if not r.get("quiet")]
    pushes = []
    if opened:
        note = compose_note([_desc(r) for r in opened])
        pushes.append((note["title"], note["message"], note["priority"]))
    loud = [r for r in recovered if ntfy_push.RANK[_rec_priority(r)] >= ntfy_push.RANK["high"]]
    if loud:
        lead = max(loud, key=lambda r: ntfy_push.RANK[_rec_priority(r)])
        p = _rec_plain(lead)
        what = p.get("problem") or ""
        if what.startswith(("The ", "A ", "One ")):          # "(was: the QQQ signal program ...)"
            what = what[0].lower() + what[1:]
        note = ntfy_push.back_to_normal(p.get("area") or BOOK, what)
        pushes.append((note["title"], note["message"], note["priority"]))
    return pushes


# -- outbox (#16) -----------------------------------------------------------------------------
def _sent_late(msg, created_epoch, now_epoch):
    """A push retried from the outbox says when it was raised, on the owner's clock: appended to
    the problem line of a plain note; an item queued before PHONE TEXT keeps the old prefix."""
    lines = msg.split("\n")
    when = ntfy_push.hhmm(created_epoch, now=now_epoch)
    if len(lines) == 3 and lines[0].startswith("Trading: "):
        lines[1] = "%s (Sent late - raised at %s.)" % (lines[1], when)
        return "\n".join(lines)
    made = _dt.datetime.fromtimestamp(created_epoch, tz=ET)
    return f"(delayed: raised {made.strftime('%a %H:%M')} ET) {msg}"


def outbox_add(outbox, title, message, priority, now_epoch):
    outbox.append({"id": f"{int(now_epoch)}-{len(outbox)}", "title": title,
                   "message": message, "priority": priority, "created_epoch": now_epoch,
                   "attempts": 0})


def outbox_flush(outbox, push_fn, now_epoch, log=print, save=None,
                 max_sends=OUTBOX_MAX_SENDS_PER_RUN):
    """Send what is queued, oldest first. A failed send stays queued (retried next run);
    the first failure in a run stops this run's sends (ntfy is unreachable, no point waiting
    8 s per item). At most `max_sends` go out per run, so a backlog cannot run the pass past
    the unit's TimeoutStartSec; the rest wait for the next run. `save(left)`, when given, is
    called after every delivered push with what is still queued, so a run killed mid-flush
    never re-sends a delivered item. Items older than OUTBOX_MAX_AGE_SEC are dropped with a
    log line. Returns (remaining, sent)."""
    remaining, sent, stop = [], 0, False
    for i, item in enumerate(outbox):
        age = now_epoch - float(item.get("created_epoch", now_epoch))
        if age > OUTBOX_MAX_AGE_SEC:
            log(f"[freshness] outbox: dropped an undeliverable push after {fmt_age(age)}: "
                f"{item.get('title')}")
            continue
        if stop:
            remaining.append(item)
            continue
        msg = item["message"]
        if item.get("attempts"):
            msg = _sent_late(msg, float(item["created_epoch"]), now_epoch)
        ok = False
        try:
            ok = bool(push_fn(msg, item["title"], item["priority"]))
        except Exception as e:   # a push must never take the monitor down
            log(f"[freshness] push raised {type(e).__name__}")
        if ok:
            sent += 1
            log(f"[freshness] pushed: {item['title']}")
            if save is not None:
                try:
                    save(remaining + list(outbox[i + 1:]))
                except OSError as e:
                    log(f"[freshness] outbox save failed: {type(e).__name__}")
            if sent >= max_sends:
                stop = True
            continue
        item["attempts"] = int(item.get("attempts", 0)) + 1
        item["last_try_epoch"] = now_epoch
        remaining.append(item)
        stop = True
        log(f"[freshness] push failed (attempt {item['attempts']}), kept in the outbox: "
            f"{item['title']}")
    return remaining, sent


# -- auto-restart gate (#2) -------------------------------------------------------------------
def restart_decision(now_et, ev, mstate, enabled):
    """{"action": none|blocked|would_restart|restart, "reasons": [...], "why": str}.
    Pure: main() acts on it. See the module docstring, AUTO-RESTART."""
    reasons = []
    # "publish down" uses the same bound exec_publish does: an unarmed executor publishes only
    # every PUBLISH_INTERVAL_OFFHOURS_SEC (600 s), so a healthy one reads 600-610 s old just
    # before each publish -- a flat 600 s line would "restart" it several times a night.
    publish_limit = max(RESTART_PUBLISH_DOWN_SEC,
                        PUBLISH_STALE_MARGIN * float(ev.get("renew") or 0.0))
    if ev.get("publish_age") is not None and ev["publish_age"] > publish_limit:
        reasons.append(f"publish down {fmt_age(ev['publish_age'])}")
    if ev.get("loop_age") is not None and ev["loop_age"] > RESTART_TICK_GAP_SEC:
        reasons.append(f"tick loop silent {fmt_age(ev['loop_age'])}")
    if not reasons:
        return {"action": "none", "reasons": [], "why": "executor healthy"}
    d = now_et.date()
    if market_calendar.is_session(d) and \
            RESTART_PROTECTED[0] <= hhmm(now_et) < RESTART_PROTECTED[1]:
        return {"action": "blocked", "reasons": reasons,
                "why": "inside 09:25-16:10 ET on a session day"}
    if ev.get("flat") is not True:
        return {"action": "blocked", "reasons": reasons,
                "why": "book not confirmed flat (open leg, pending resend/fill capture, or "
                       "state.json unreadable)"}
    rs = mstate.get("restart") or {}
    if enabled and rs.get("last_restart_day") == now_et.date().isoformat():
        return {"action": "blocked", "reasons": reasons,
                "why": "at most once a day (owner rule 2026-10-05)"}
    last = float(rs.get("last_restart_epoch" if enabled else "last_would_epoch") or 0.0)
    if now_et.timestamp() - last < RESTART_COOLDOWN_SEC:
        return {"action": "blocked", "reasons": reasons, "why": "at most once per hour"}
    return {"action": "restart" if enabled else "would_restart", "reasons": reasons,
            "why": "outside the protected window, flat, cooldown passed"}


RESTARTABLE_UNIT_STATES = ("active", "failed")


def exec_unit_state(run_cmd=None):
    """`systemctl is-active` of the executor unit: active / inactive / failed / activating /
    ..., or "unknown" when systemctl cannot be asked. Read-only (no sudo needed)."""
    run_cmd = run_cmd or subprocess.run
    try:
        r = run_cmd(["systemctl", "is-active", EXEC_UNIT],
                    capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    out = (r.stdout or "").strip().splitlines()
    return out[0].strip() if out and out[0].strip() else "unknown"


def restart_note(ok):
    """The phone note for an auto-restart (PHONE TEXT): it only ever runs with the book flat and
    the market closed, so a restart that worked is a low note; one whose command failed leaves
    the order program stuck -> high."""
    if ok:
        return ntfy_push.plain(BOOK, "restarted", "not affected (the book was flat, market closed)",
                               "The QQQ order program was stuck, so this monitor restarted it.",
                               "nothing", priority="low")
    return ntfy_push.plain(BOOK, "CHECK NOW", "the QQQ book may not trade at the next open",
                           "The QQQ order program is stuck and its automatic restart failed.", ASK,
                           priority="high")


def do_restart(run_cmd=None):
    run_cmd = run_cmd or subprocess.run
    try:
        r = run_cmd(["sudo", "-n", "systemctl", "restart", EXEC_UNIT],
                    capture_output=True, text=True, timeout=60)
        return r.returncode == 0, f"rc={r.returncode} {(r.stderr or '').strip()[:200]}"
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}"


# -- one pass ---------------------------------------------------------------------------------
def load_config(paths):
    cfg = dict(DEFAULT_CONFIG)
    data, _err = read_json(paths["config"])
    if isinstance(data, dict):
        cfg.update({k: data[k] for k in DEFAULT_CONFIG if k in data})
    return cfg


def _default_push(log):
    from api import ntfy_push

    def push(message, title, priority):
        return ntfy_push.push(message, title=title, priority=priority, timeout=8,
                              log=lambda t: log(f"[freshness] {t}"))
    return push


def _make_logger(path, echo=True):
    def log(line):
        stamp = _dt.datetime.now(tz=ET).isoformat(timespec="seconds")
        if echo:
            print(f"{stamp} {line}", flush=True)
        if path:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"{stamp} {line}\n")
            except OSError:
                pass
    return log


def evaluate(snap, now_et, mstate):
    """(verdicts, groups_ran, exec view). Pure over `snap`; updates mstate's small memories
    (publish_seen, exec_log hits, tick_gap_seen)."""
    ev = exec_view(snap, now_et, mstate)
    verdicts, groups = [], set()
    checks = [
        ("exec", lambda: check_exec(snap, now_et, mstate, ev)),
        ("systemd", lambda: check_systemd(snap)),
        ("disk", lambda: check_disk(snap)),
        ("evening", lambda: check_evening(snap, now_et, mstate)),
        ("session", lambda: check_session(snap, now_et, mstate, ev)),
        ("eod", lambda: check_eod(snap, now_et)),
    ]
    for group, fn in checks:
        try:
            out = fn()
        except Exception as e:   # one broken check must not blind the others
            out = None
            verdicts.append(_verdict(f"check_error:{group}", "check_error", False, MEDIUM,
                                     f"freshness check '{group}' crashed",
                                     f"{type(e).__name__}: {e}", min_runs=2,
                                     plain=_plain("One of the QQQ book's health checks crashed.",
                                                  area=BOX)))
        if out is not None:
            groups.add(group)
            verdicts.extend(out)
    groups.add("check_error")
    return verdicts, groups, ev


def run_once(paths=None, now=None, cfg=None, push_fn=None, run_cmd=None, dry_run=False,
             log=None):
    """One monitor pass. Returns a summary dict (also what --dry-run prints)."""
    started = time.time()
    paths = paths or default_paths()
    log = log or _make_logger(None if dry_run else paths["log"])
    now_et = (now or _dt.datetime.now(tz=ET)).astimezone(ET)
    now_epoch = now_et.timestamp()
    label = now_et.strftime("%a %m-%d %H:%M ET")
    cfg = cfg if cfg is not None else load_config(paths)
    mstate, _ = read_json(paths["monitor_state"])
    mstate = mstate if isinstance(mstate, dict) else {}
    alerts = mstate.setdefault("alerts", {})

    snap = collect(paths, run_cmd)
    log_state = mstate.setdefault("exec_log", {})
    hits, off = scan_log_for(paths["exec_log"], SUPPRESS_PHRASE, log_state.get("offset"))
    snap["_suppress_hits"], snap["_suppress_offset"] = hits, off

    verdicts, groups, ev = evaluate(snap, now_et, mstate)
    opened, recovered, expired = apply_verdicts(alerts, verdicts, groups, now_epoch, label)
    pushes = compose_pushes(opened, recovered, expired)
    pushes += preopen_step(snap, now_et, mstate, alerts, ev)
    for r in opened:
        log(f"[freshness] ALERT [{r['severity']}] {r['key']}: {r['title']} -- {r['detail']}")
    for r in recovered:
        log(f"[freshness] RECOVERED {r['key']}: {r['title']}")
    for r in expired:
        log(f"[freshness] EXPIRED (window ended, still failing) {r['key']}: {r['title']}")

    # auto-restart gate
    # literally true only: a hand-written "false" / "0" / "off" string must not switch it on
    enabled = cfg.get("auto_restart_exec") is True
    decision = restart_decision(now_et, ev, mstate, enabled)
    if decision["action"] in ("restart", "would_restart"):
        # Only a unit that is running-but-wedged (active) or has died (failed) is restarted.
        # An INACTIVE unit was stopped on purpose (`systemctl stop` for maintenance or a
        # deploy) and `systemctl restart` would START it again -- never do that; nor act when
        # systemctl cannot say (unknown) or the unit is mid start/stop (activating, ...).
        unit_state = exec_unit_state(run_cmd)
        if unit_state not in RESTARTABLE_UNIT_STATES:
            why = (f"{EXEC_UNIT} is {unit_state} -- stopped on purpose, not restarting"
                   if unit_state == "inactive" else
                   f"{EXEC_UNIT} is {unit_state} -- only an active (wedged) or failed unit is "
                   f"restarted")
            decision = dict(decision, action="blocked", why=why)
    rs = mstate.setdefault("restart", {})
    rs["last_decision"] = dict(decision, at=label)
    outbox, _ = read_json(paths["outbox"])
    outbox = outbox if isinstance(outbox, list) else []
    queued = [0]   # how many of `pushes` are already in `outbox`

    def queue_pushes():
        for title, msg, prio in pushes[queued[0]:]:
            outbox_add(outbox, title, msg, prio, now_epoch)
        queued[0] = len(pushes)

    if decision["action"] == "would_restart":
        rs["last_would_epoch"] = now_epoch
        log(f"[freshness] would restart {EXEC_UNIT} ({', '.join(decision['reasons'])}) -- "
            f"auto_restart_exec is OFF, pending the owner's OK; nothing was restarted")
    elif decision["action"] == "restart":
        if dry_run:
            log(f"[freshness] DRY-RUN: would restart {EXEC_UNIT} now")
        else:
            # The hourly cooldown is saved BEFORE the restart (with this run's episodes and
            # their pushes): a pass killed mid-restart (OOM, reboot, TimeoutStartSec -- the
            # restart alone may take 60 s) must not let the next pass, 2 minutes later,
            # restart again.
            rs["last_restart_epoch"] = now_epoch
            rs["last_restart_day"] = now_et.date().isoformat()
            rs["last_restart_et"] = label
            rs["last_restart_result"] = "started; the pass ended before the result was known"
            queue_pushes()
            write_json_atomic(paths["monitor_state"], mstate)
            write_json_atomic(paths["outbox"], outbox)
            ok, note = do_restart(run_cmd)
            rs["last_restart_result"] = note
            log(f"[freshness] RESTARTED {EXEC_UNIT} ({', '.join(decision['reasons'])}): "
                f"{'ok' if ok else 'FAILED'} {note}")
            rn = restart_note(ok)
            pushes.append((rn["title"], rn["message"], rn["priority"]))
    elif decision["action"] == "blocked":
        # logged when the reason changes, else at most every 30 min (a weekend-long wedge
        # would otherwise write the same line every 2 minutes)
        if (rs.get("last_block_why") != decision["why"]
                or now_epoch - float(rs.get("last_block_log_epoch") or 0.0) > 1800):
            log(f"[freshness] restart gate: {', '.join(decision['reasons'])} -- not "
                f"restarting: {decision['why']}")
            rs["last_block_why"] = decision["why"]
            rs["last_block_log_epoch"] = now_epoch

    queue_pushes()
    sent = 0
    if not dry_run:
        # Persist this run's episodes WITH the pushes they queued before sending anything, and
        # the outbox again after every delivered push: a run killed mid-flush (TimeoutStartSec,
        # OOM, reboot) then neither re-opens the same episodes nor re-sends what already went.
        write_json_atomic(paths["monitor_state"], mstate)
        write_json_atomic(paths["outbox"], outbox)
        outbox, sent = outbox_flush(outbox, push_fn or _default_push(log), now_epoch, log=log,
                                    save=lambda left: write_json_atomic(paths["outbox"], left))

    open_alerts = [
        {k: r.get(k) for k in ("key", "group", "severity", "title", "detail", "opened_et",
                               "opened_epoch", "last_bad_et", "quiet_expire", "quiet")}
        for r in sorted(alerts.values(), key=lambda r: (-_SEV_RANK.get(r.get("severity"), 0),
                                                        r.get("key")))
        if r.get("open")]
    status = {
        "version": 1, "host": socket.gethostname(), "last_run_et": now_et.isoformat(),
        "last_run_epoch": now_epoch, "open_alerts": open_alerts,
        "verdicts": {v["key"]: {"ok": v["ok"], "severity": v["severity"], "title": v["title"],
                                "detail": "" if v["ok"] else v["detail"]} for v in verdicts},
        "groups_checked": sorted(groups - {"check_error"}),
        "outbox_pending": len(outbox), "pushes_sent": sent,
        "preopen": mstate.get("preopen"),
        "auto_restart": {"enabled": enabled, **{k: rs.get(k) for k in (
            "last_decision", "last_restart_et", "last_restart_result")}},
        "broker_mode": snap.get("broker_mode"),
        # KEEL size diffs on live NOISE entries (api/cloud_signal.py) -- the PC relays each
        # one once to the inboxes; see KEEL SIZE DIFFS in the docstring
        "keel_diffs": snap.get("keel_diffs") or [],
    }
    summary = {"status": status, "pushes": pushes, "opened": opened, "recovered": recovered,
               "expired": expired, "decision": decision}
    if dry_run:
        return summary
    write_json_atomic(paths["monitor_state"], mstate)
    write_json_atomic(paths["outbox"], outbox)
    write_json_atomic(paths["status"], status)
    write_json_atomic(paths["heartbeat"], {
        "ts": now_et.isoformat(), "epoch": now_epoch, "ok": True,
        "open_alerts": len(open_alerts), "outbox_pending": len(outbox),
        "run_seconds": round(time.time() - started, 2)})
    _ping(log)
    return summary


def _ping(log):
    """GET the optional external push-heartbeat URL (#4). The URL is a secret: never logged."""
    url = (os.environ.get("EDGELOG_FRESHNESS_PING_URL") or "").strip()
    if not url:
        return
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=8) as resp:
            resp.read(64)
    except Exception as e:
        log(f"[freshness] external heartbeat ping failed: {type(e).__name__}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=None, help="EDGELOG_HOME to read (default: env/~/edgelog)")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and print; no push, no restart, no file written")
    a = ap.parse_args(argv)
    paths = default_paths(a.home)
    try:
        summary = run_once(paths, dry_run=a.dry_run)
    except Exception as e:
        print(f"[freshness] FATAL {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if a.dry_run:
        st = summary["status"]
        for key, v in sorted(st["verdicts"].items()):
            print(f"{'ok  ' if v['ok'] else 'FAIL'} {key}: {v['title']}"
                  + ("" if v["ok"] else f" -- {v['detail']}"))
        for title, msg, prio in summary["pushes"]:
            print(f"WOULD PUSH [{prio}] {title}: {msg}")
        print(f"restart gate: {summary['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
