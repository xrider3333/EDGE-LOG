"""NT8 paper pipeline - SILENT-FAILURE SWEEP (owner standing-order addendum, 2026-10-05).

Every scheduled push, pull, rebuild and readiness step of the NinjaTrader paper pipeline gets a freshness check
here, and a failure becomes an inbox line (PAPER-NT8, which reads its inbox at the start and end of every task)
plus a plain phone push for anything FAIL that is not order flow (see PHONE TEXT below). The model is the KEEL miss: the NQ master push to the box failed four
nights running (09-30..10-03) and nothing said so.

Checks (each PASS / WARN / FAIL with a plain reason):
  tasks        every enabled 'EdgeLog *' scheduled task: last result 0 and last run within its expected age
  box_push     C:\\EdgeLog\\logs\\push_nq_master.log: newest line OK and within 2 trading days
  nt_backup    newest C:\\EdgeLog\\_ntbackup\\<date> snapshot within 3 days AND it holds BOTH roster strategy rows
               (10-03's snapshot was taken after NOISE had been purged - a restore from it would lose NOISE)
  roster       watchdog log: no run of STOP / INCOMPLETE lines for 15+ minutes (a strategy down with nobody told)
  capture      during CME hours: newest 10s bar < 5 min old and >= 80% of the last hour's traded bars carry buy/sell
  repair       no-tick (rt=3) bars from the last 3 days left unrepaired while a replay file exists
  readiness    on a trading day after 09:30 ET: today's readiness result exists (READY or not - its own push covers NOT READY)
  report       newest nightly paper report = the last completed trading day (after 16:40 ET) - Firestore, 1-2 reads
  bundle       the board's trade bundle was rebuilt within 30 hours of the newest report

Daytime backup: from 14:05 Arizona (17:05 ET, the CME daily halt) the sweep takes the day's NinjaTrader
snapshot itself (api/nt_backup.run_nightly, once per day - it skips when today's folder exists), because the
runner's 21:00 window falls after the PC's normal 17:45 shutdown. Not in --dry-run.

De-dupe: an INBOX alert is posted when the failing set CHANGES, and repeated at most every 6 hours while it stands.

NIGHT MODE (2026-10-07, api/nt_night_mode.py): from the end-of-day close until the morning start (+ MORNING_GRACE_MIN
for the PC to wake and log in) NinjaTrader is closed ON PURPOSE, so `capture` and `roster` PASS with "night mode
until HH:MM" instead of failing, and `repair` does not count no-tick bars inside a window (+ BAR_GRACE_MIN). The
end-of-day task itself ("EdgeLog NT night mode") is watched like the others.

PHONE TEXT, ECHOES AND REPEATS (2026-10-07, "make the notifications simpler to understand"). The inbox post
(PAPER-NT8) and C:\\EdgeLog\\nt8_sweep.json are unchanged. The phone push is separate:
  * Plain format (api/ntfy_push.py): title "Paper NT8: needs a fix" / "Paper NT8: CHECK NOW" / "Paper NT8: OK", then
    "Trading: not affected." or "Trading: AFFECTED - ...", the problem, "Do: ...". High priority ONLY when trading is
    affected (a strategy down); a failed backup or upload is default; a stopped 10-second feed is low.
  * Only FAIL items are pushed, and never order flow (is_orderflow: the capture buy/sell coverage and the repair
    warnings). Those stay in the inbox post and the JSON; api/delta_alarm.py is the one phone owner of that problem.
  * The readiness task's exit code 1 is its documented "ran and found problems" result (it pushes those itself), so
    it is NOT a task failure here (REPORTING_EXIT_CODES). The sweep alerts on the readiness task only when it did not
    run when due, is stale, or ended with any OTHER non-zero code (a crash).
  * Repeats (api/ntfy_push.dedupe, state under "push" in nt8_sweep_state.json): the same problem set pushes once, then
    at most once a day; a NEW or WORSE problem pushes at once; when the set clears ONE low-priority "back to normal"
    goes out, but only if the episode had a high push.

Run:  python tools/nt8_freshness_sweep.py [--dry-run] [--json] [--no-firestore]
Exit: 0 = all pass/warn-only, 1 = at least one FAIL.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:               # run as a script, sys.path holds tools/, not the repo (the phone text imports api.ntfy_push)
    sys.path.insert(0, ROOT)
EL = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
ET = ZoneInfo("America/New_York")
STATE_PATH = os.path.join(EL, "nt8_sweep_state.json")
RESULT_PATH = os.path.join(EL, "nt8_sweep.json")
ROSTER_IDS = {386606468: "EdgeLogNOISE", 386606474: "EdgeLogENGUQ1m"}
REPEAT_SEC = 6 * 3600                # inbox repeat
PUSH_REPEAT_SEC = 24 * 3600          # phone repeat: once a day while unchanged
AREA = "Paper NT8"
BACKUP_FROM_HHMM = (14, 5)

# expected maximum age of each scheduled task's LAST RUN, in hours (None = event-driven, result only)
TASK_MAX_AGE_H = {
    "EdgeLog NT recover watchdog": 0.5,
    "EdgeLog NT 10s import": 2,
    "EdgeLog NT futures rollover": 30,
    "EdgeLog premarket wake": 80,        # weekdays only; covers a weekend
    "EdgeLog NT readiness": 80,
    "EdgeLog pull box ledgers": 80,
    "EdgeLog push NQ master to box": 80,
    "EdgeLog nightly backup": 80,
    "EdgeLog NT night mode": 80,         # weekdays only; covers a weekend
}
# LastTaskResult codes that are not failures: 0 ok, 267009 running, 267011 never run, 267014 terminated by us
OK_RESULTS = {0, 267009, 267011, 267014}
# Exit codes that mean "ran and reported", per task. tools/nt_readiness.py exits 1 when it FOUND problems (and has
# already pushed them itself) - that is its documented result, not a failure of the task. Staleness still applies.
REPORTING_EXIT_CODES = {"EdgeLog NT readiness": {1}}


def _item(cid, status, label, detail):
    return {"id": cid, "status": status, "label": label, "detail": detail}


def _trading_day(d):
    return d.weekday() < 5


def _prev_trading_day(d):
    d -= dt.timedelta(days=1)
    while not _trading_day(d):
        d -= dt.timedelta(days=1)
    return d


def cme_open(now_et):
    wd, m = now_et.weekday(), now_et.hour * 60 + now_et.minute
    if wd == 5:
        return False
    if wd == 6:
        return m >= 18 * 60 + 15
    if wd == 4 and m >= 17 * 60:
        return False
    return not (17 * 60 <= m < 18 * 60 + 15)


# ---------------------------------------------------------------------------------------------- checks
def check_tasks(now_local, tasks=None):
    """tasks: list of dicts {name, enabled, last (datetime or None), result} - read from Task Scheduler when None."""
    if tasks is None:
        tasks = read_tasks()
    out = []
    for t in tasks:
        if not t.get("enabled") or t["name"] not in TASK_MAX_AGE_H:
            continue
        res = t.get("result")
        if res not in OK_RESULTS and res not in REPORTING_EXIT_CODES.get(t["name"], ()):
            out.append(_item("task:" + t["name"], "fail", t["name"],
                             f"last run ended with code {res} (not 0)"))
            continue
        last, max_h = t.get("last"), TASK_MAX_AGE_H[t["name"]]
        if last is None or last.year < 2000:
            out.append(_item("task:" + t["name"], "warn", t["name"], "has never run"))
        elif max_h and (now_local - last).total_seconds() > max_h * 3600:
            out.append(_item("task:" + t["name"], "fail", t["name"],
                             f"last ran {last:%m-%d %H:%M}, more than {max_h:g} h ago"))
    if not out:
        out.append(_item("tasks", "pass", "Scheduled tasks", "every EdgeLog task ran on time and ended OK"))
    return out


def read_tasks():
    ps = ("Get-ScheduledTask | ? { $_.TaskName -like 'EdgeLog*' } | % { $i = $_ | Get-ScheduledTaskInfo; "
          "[pscustomobject]@{name=$_.TaskName; enabled=($_.State -ne 'Disabled'); "
          "last=$(if($i.LastRunTime){$i.LastRunTime.ToString('s')}else{''}); result=$i.LastTaskResult} } "
          "| ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
    rows = json.loads(r.stdout or "[]")
    rows = rows if isinstance(rows, list) else [rows]
    for x in rows:
        x["last"] = dt.datetime.fromisoformat(x["last"]) if x.get("last") else None
        x["result"] = int(x["result"]) if x.get("result") is not None else None
    return rows


def check_box_push(now_local, log_path=None):
    p = log_path or os.path.join(EL, "logs", "push_nq_master.log")
    try:
        lines = [ln.strip() for ln in open(p, encoding="utf-8", errors="replace") if ln.strip()]
    except OSError:
        return [_item("box_push", "fail", "NQ master push to the box", f"log missing: {p}")]
    last = lines[-1] if lines else ""
    try:
        when = dt.datetime.fromisoformat(last[:19])
    except ValueError:
        when = None
    if " FAIL " in f" {last} " or last[20:].startswith("FAIL"):
        return [_item("box_push", "fail", "NQ master push to the box",
                      f"newest run FAILED ({last[20:110]}) - the box's KEEL refresh reads stale NQ data")]
    if when is None or (now_local - when).days >= 3:
        return [_item("box_push", "fail", "NQ master push to the box",
                      f"no successful push since {when:%m-%d %H:%M}" if when else "no dated line")]
    return [_item("box_push", "pass", "NQ master push to the box", f"last OK {when:%m-%d %H:%M}")]


def check_nt_backup(now_local, root=None):
    root = root or os.path.join(EL, "_ntbackup")
    dated = sorted(d for d in glob.glob(os.path.join(root, "20??-??-??")) if os.path.isdir(d))
    if not dated:
        return [_item("nt_backup", "fail", "NinjaTrader nightly backup", "no dated snapshot at all")]
    newest = dated[-1]
    day = dt.date.fromisoformat(os.path.basename(newest))
    items = []
    if (now_local.date() - day).days > 3:
        items.append(_item("nt_backup_age", "fail", "NinjaTrader nightly backup",
                           f"newest snapshot is {day} - the sweep takes one from 14:05 Arizona and the runner at 21:00; neither ran"))
    try:
        rows = json.load(open(os.path.join(newest, "edgelog_strategy_rows.json"), encoding="utf-8"))
        rows = rows if isinstance(rows, list) else rows.get("rows", [])
        ids = {int(r.get("Id")) for r in rows if r.get("Id") is not None}
        missing = [n for i, n in ROSTER_IDS.items() if i not in ids]
    except Exception as e:
        missing = [f"(unreadable: {type(e).__name__})"]
    if missing:
        good = None
        for d in reversed(dated):
            try:
                rr = json.load(open(os.path.join(d, "edgelog_strategy_rows.json"), encoding="utf-8"))
                rr = rr if isinstance(rr, list) else rr.get("rows", [])
                if set(ROSTER_IDS) <= {int(r.get("Id")) for r in rr if r.get("Id") is not None}:
                    good = os.path.basename(d); break
            except Exception:
                continue
        items.append(_item("nt_backup_rows", "fail", "NinjaTrader nightly backup",
                           f"newest snapshot {day} is missing {', '.join(missing)} - a restore from it would lose them; "
                           f"last complete snapshot: {good or 'none'}"))
    if not items:
        items.append(_item("nt_backup", "pass", "NinjaTrader nightly backup", f"{day}, both strategies present"))
    return items


def _night(now_ts, grace=True):
    """The night-mode window now falls in (api/nt_night_mode.quiet: + MORNING_GRACE_MIN when `grace`),
    or None. Never raises."""
    try:
        from api import nt_night_mode
        return nt_night_mode.quiet(now=now_ts, grace_min=None if grace else 0)
    except Exception:
        return None


def _night_words(win):
    return "NinjaTrader is closed for night mode until %s (on purpose)" % win["end"].strftime("%H:%M")


def check_roster(now_local, log_path=None):
    win = _night(now_local.timestamp(), grace=False)
    if win:
        return [_item("roster", "pass", "Strategies running", _night_words(win))]
    p = log_path or os.path.join(EL, "nt_recover.log")
    try:
        tail = open(p, encoding="utf-8", errors="replace").readlines()[-400:]
    except OSError:
        return [_item("roster", "warn", "Strategies running", "watchdog log missing")]
    bad_since = None
    for ln in tail:
        try:
            t = dt.datetime.strptime(ln[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if "healthy:" in ln or "RECOVERED" in ln:
            bad_since = None
        elif ("STOP:" in ln or "INCOMPLETE" in ln) and bad_since is None:
            bad_since = t
    if bad_since and (now_local - bad_since).total_seconds() > 15 * 60:
        return [_item("roster", "fail", "Strategies running",
                      f"the watchdog has not reported healthy since {bad_since:%m-%d %H:%M} (STOP / INCOMPLETE) - a strategy is down")]
    return [_item("roster", "pass", "Strategies running", "watchdog healthy")]


def _tail_rows(path, n=400):
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 120 * n))
        data = f.read().decode("utf-8", "replace").splitlines()[1:]
    rows = []
    for ln in data:
        c = ln.split(",")
        if len(c) < 11:
            continue
        try:
            rows.append((int(float(c[0])), float(c[5]), float(c[7] or 0) + float(c[8] or 0), c[10].strip()))
        except ValueError:
            continue
    return rows


def check_capture(now_ts, ohlc_dir=None):
    ohlc_dir = ohlc_dir or os.path.join(EL, "ohlc")
    now_et = dt.datetime.fromtimestamp(now_ts, ET)
    if not cme_open(now_et):
        return [_item("capture", "pass", "10s capture", "market closed - not checked")]
    win = _night(now_ts)
    if win:
        return [_item("capture", "pass", "10s capture", _night_words(win) + " - not checked")]
    out = []
    for sym in ("NQ", "ES"):
        p = os.path.join(ohlc_dir, f"{sym}_10s.csv")
        try:
            rows = _tail_rows(p, 420)
        except OSError:
            out.append(_item(f"capture_{sym}", "fail", f"10s capture {sym}", "file missing")); continue
        if not rows:
            out.append(_item(f"capture_{sym}", "fail", f"10s capture {sym}", "no rows")); continue
        age = (now_ts - rows[-1][0]) / 60
        if age > 5:
            out.append(_item(f"capture_{sym}", "fail", f"10s capture {sym}", f"newest bar is {age:.0f} min old"))
            continue
        hour = [r for r in rows if r[0] >= now_ts - 3600 and r[1] > 0]
        cov = (sum(1 for r in hour if r[2] > 0 and r[3] != "3") / len(hour)) if len(hour) >= 30 else 1.0
        if cov < 0.8:
            out.append(_item(f"capture_{sym}", "fail", f"10s capture {sym}",
                             f"only {cov:.0%} of the last hour's traded bars carry buy/sell"))
        else:
            out.append(_item(f"capture_{sym}", "pass", f"10s capture {sym}", f"fresh, {cov:.0%} with buy/sell"))
    return out


def check_repair(now_ts, ohlc_dir=None):
    ohlc_dir = ohlc_dir or os.path.join(EL, "ohlc")
    out = []
    try:
        from api import nt_night_mode
        cov = nt_night_mode.covered_fn()          # night-mode windows: closed on purpose, not a hole to rebuild
    except Exception:
        cov = lambda t: False                     # noqa: E731
    for sym in ("NQ", "ES"):
        try:
            rows = _tail_rows(os.path.join(ohlc_dir, f"{sym}_10s.csv"), 26000)
        except OSError:
            continue
        blind = [r for r in rows if r[0] >= now_ts - 3 * 86400 and r[1] > 0 and r[3] == "3" and not cov(r[0])]
        if len(blind) >= 360:            # an hour or more of no-tick bars still in the 3-day replay reach
            first = dt.datetime.fromtimestamp(blind[0][0], ET)
            if os.path.exists(os.path.join(EL, "nt_replay_retry.OFF")):
                why = ("prices and volume are complete, only the buy/sell split is missing; the empty-replay retry "
                       "is OFF because fresh NinjaTrader starts load no Tick Replay history since 10-04")
            else:
                why = "the next empty-replay retry or NinjaTrader restart outside the cash session rebuilds them"
            out.append(_item(f"repair_{sym}", "warn", f"10s repair {sym}",
                             f"{len(blind)} no-tick bars since {first:%m-%d %H:%M} ET are not yet rebuilt ({why})"))
    return out or [_item("repair", "pass", "10s repair", "no unrepaired no-tick hour in the last 3 days")]


# DECEMBER ROLL WATCH (owner decision 2026-10-05): the ENGU-Q #335 paper legs run on the roll-corrected
# master from 10-05. At the first roll after that (NQ Dec, about 12-10) someone must confirm the legs still
# rebuild with the live 10s tail (no "different contract" refusal in the nightly report) and that their
# trades did not jump. The sweep warns from 12-07 until C:\\EdgeLog\\enguq_dec_roll_checked exists.
ROLL_WATCH = (dt.date(2026, 12, 7), dt.date(2026, 12, 31))


def check_roll_watch(now_local, flag=None):
    flag = flag or os.path.join(EL, "enguq_dec_roll_checked")
    d = now_local.date()
    if not (ROLL_WATCH[0] <= d <= ROLL_WATCH[1]) or os.path.exists(flag):
        return []
    return [_item("roll_watch", "warn", "ENGU-Q December roll check",
                  "first roll on the roll-corrected master: confirm the nightly report rebuilt the ENGU-Q #335 "
                  "legs with no contract refusal and no trade jump, then create " + flag)]


def check_readiness(now_ts, path=None):
    p = path or os.path.join(EL, "nt_readiness.json")
    now_et = dt.datetime.fromtimestamp(now_ts, ET)
    if not _trading_day(now_et.date()) or now_et.time() < dt.time(9, 30):
        return [_item("readiness", "pass", "Premarket readiness", "not due yet")]
    try:
        j = json.load(open(p, encoding="utf-8"))
        day = str(j.get("checked_at_et", ""))[:10]
    except Exception:
        day = ""
    if day != now_et.date().isoformat():
        return [_item("readiness", "fail", "Premarket readiness",
                      f"no readiness result for today (newest: {day or 'none'}) - the 09:15 / 09:25 ET check did not run")]
    return [_item("readiness", "pass", "Premarket readiness", f"ran today ({'READY' if j.get('ok') else 'NOT READY - it pushed its own alert'})")]


def check_report_and_bundle(now_ts, db=None, uid=None):
    now_et = dt.datetime.fromtimestamp(now_ts, ET)
    want = now_et.date() if (_trading_day(now_et.date()) and now_et.time() >= dt.time(16, 40)) else _prev_trading_day(now_et.date())
    out = []
    try:
        if db is None:
            sys.path.insert(0, ROOT)
            import firebase_admin
            from firebase_admin import credentials, firestore
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
            db = firestore.client()
            from tools.paper_review_routine import UID
            uid = UID
        u = db.collection("users").document(uid)
        snap = u.collection("paper_reports").document(want.isoformat()).get()
        if not snap.exists:
            out.append(_item("report", "fail", "Nightly paper report",
                             f"no report for {want} (the 16:10 ET runner pass did not write it)"))
        else:
            out.append(_item("report", "pass", "Nightly paper report", f"{want} present"))
        meta = u.collection("paper_bundle").document("0").get()        # part 0 carries gen / parts / n_total
        gen = (meta.to_dict() or {}).get("gen") if meta.exists else None
        if not gen:
            out.append(_item("bundle", "warn", "Board trade bundle", "no bundle - the board shows the newest 500 only"))
        elif now_ts - int(gen) > 30 * 3600 + (86400 * 2 if now_et.weekday() in (5, 6, 0) else 0):
            out.append(_item("bundle", "fail", "Board trade bundle",
                             f"last rebuilt {dt.datetime.fromtimestamp(int(gen), ET):%m-%d %H:%M} ET"))
        else:
            out.append(_item("bundle", "pass", "Board trade bundle", "fresh"))
    except Exception as e:
        out.append(_item("report", "warn", "Nightly paper report", f"could not check: {type(e).__name__}: {e}"))
    return out


def maybe_backup(now_local, run=None):
    """Take today's NinjaTrader snapshot once the CME daily halt starts (see the module doc). Returns a
    one-line summary, or None when it is not time yet or today's folder already exists."""
    if (now_local.hour, now_local.minute) < BACKUP_FROM_HHMM:
        return None
    if os.path.isdir(os.path.join(EL, "_ntbackup", now_local.date().isoformat())):
        return None
    if run is None:
        sys.path.insert(0, ROOT)
        from api import nt_backup
        run = nt_backup.run_nightly
    return run()


# ---------------------------------------------------------------------------------------------- alerting
def decide_alert(items, state, now_ts):
    bad = sorted(i["id"] for i in items if i["status"] in ("fail", "warn"))
    last_set, last_at = state.get("set", []), int(state.get("at", 0))
    if not bad:
        return False, {"set": [], "at": 0}
    if bad != last_set or now_ts - last_at >= REPEAT_SEC:
        return True, {"set": bad, "at": now_ts}
    return False, state


def build_message(items):
    bad = [i for i in items if i["status"] in ("fail", "warn")]
    return "NT8 PIPELINE SWEEP: " + "; ".join(f"{i['status'].upper()} {i['label']}: {i['detail']}" for i in bad)


def _post_inbox(msg):
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "chat_inbox.py"), "post", "PAPER-NT8",
                    "--from", "NT8-SWEEP", msg], capture_output=True, text=True, timeout=60)


TASK_WORDS = {
    "EdgeLog NT recover watchdog": "the NinjaTrader auto-restart job",
    "EdgeLog NT 10s import": "the 10-second data import",
    "EdgeLog NT futures rollover": "the futures contract roll job",
    "EdgeLog premarket wake": "the morning wake-up job",
    "EdgeLog NT readiness": "the morning check",
    "EdgeLog pull box ledgers": "the cloud trade-record download",
    "EdgeLog push NQ master to box": "the NQ data upload to the cloud box",
    "EdgeLog nightly backup": "the nightly backup",
    "EdgeLog NT night mode": "the NinjaTrader end-of-day close",
}
ASK = "ask Claude (PAPER-NT8 chat)"


def is_orderflow(it):
    """True for what api/delta_alarm.py owns on the phone: the 10-second capture's buy/sell coverage failure and the
    no-tick repair warnings. A stale or missing capture is NOT order flow."""
    iid = str(it.get("id", ""))
    return iid.startswith("repair") or (iid.startswith("capture_") and "buy/sell" in str(it.get("detail", "")))


def push_items(items):
    """The items worth a phone push: FAIL only, never order flow."""
    return [i for i in items if i["status"] == "fail" and not is_orderflow(i)]


def _local_clock(text, now_local):
    """'10-07 09:12' (the PC's own clock, no year) -> '09:12' / 'yesterday 09:12' in plain words."""
    from api import ntfy_push
    try:
        t = dt.datetime.strptime("%d-%s" % (now_local.year, text), "%Y-%m-%d %H:%M")
        return ntfy_push.hhmm(t, now=now_local, naive_is="local")
    except Exception:
        return text


def _describe(it, now_local=None):
    """One failed item in plain words -> {"affects", "problem", "action", "rank"} (see api/ntfy_push.compose)."""
    now_local = now_local or dt.datetime.now()
    iid, detail = str(it["id"]), str(it.get("detail") or "")
    if iid.startswith("task:"):
        name = TASK_WORDS.get(iid[5:], iid[5:])
        stale = "more than" in detail
        return {"affects": None, "rank": 1, "action": ASK,
                "problem": (name[:1].upper() + name[1:]) + (" has not run on time." if stale else " failed on its last run.")}
    if iid == "roster":
        m = re.search(r"since (\d\d-\d\d \d\d:\d\d)", detail)
        return {"affects": "a strategy is down", "rank": 2, "action": "open NinjaTrader and check the strategies",
                "problem": "A strategy has been down" + (" since %s." % _local_clock(m.group(1), now_local) if m else ".")}
    if iid == "box_push":
        return {"affects": None, "rank": 1, "action": ASK, "problem": "The NQ data upload to the cloud box failed."}
    if iid.startswith("nt_backup"):
        return {"affects": None, "rank": 1, "action": ASK,
                "problem": ("The newest NinjaTrader backup is missing a strategy." if iid == "nt_backup_rows"
                            else "The NinjaTrader backup is out of date.")}
    if iid.startswith("capture_"):
        return {"affects": None, "rank": 0, "action": "check the 10-second chart in NinjaTrader",
                "problem": "%s 10-second data stopped updating." % iid[8:]}
    if iid == "readiness":
        return {"affects": None, "rank": 1, "action": ASK, "problem": "The morning check did not run today."}
    if iid == "report":
        m = re.search(r"no report for (\d{4})-(\d\d-\d\d)", detail)
        return {"affects": None, "rank": 1, "action": ASK,
                "problem": "The nightly paper report was not written" + (" for %s." % m.group(2) if m else ".")}
    if iid == "bundle":
        return {"affects": None, "rank": 1, "action": ASK, "problem": "The paper board's trade list was not rebuilt."}
    return {"affects": None, "rank": 1, "action": ASK, "problem": "%s needs a look." % (it.get("label") or iid)}


def build_note(items, now_local=None):
    """The plain phone note for the push-worthy failures."""
    from api import ntfy_push
    return ntfy_push.compose(AREA, [_describe(i, now_local) for i in push_items(items)])


def decide_push(items, push_state, now_ts, now_local=None):
    """-> (action, new_push_state, note). action "push" | "clear" | None; see the module doc."""
    from api import ntfy_push
    cur = push_items(items)
    action, st = ntfy_push.dedupe({i["id"]: _describe(i, now_local)["rank"] for i in cur}, push_state or {}, now_ts,
                                  PUSH_REPEAT_SEC)
    note = None
    if action == "push":
        st["what"] = min((_describe(i, now_local) for i in cur), key=lambda d: -d["rank"])["problem"]   # the worst, for "was: ..."
        note = build_note(items, now_local)
    elif action == "clear":
        note = ntfy_push.back_to_normal(AREA, (push_state or {}).get("what", ""))
        st["what"] = ""
    else:
        st["what"] = (push_state or {}).get("what", "")
    return action, st, note


def _push_note(note):
    """Send one plain note. -> True when delivered."""
    try:
        sys.path.insert(0, ROOT)
        from tools.nt_readiness import _load_ntfy_env
        _load_ntfy_env()
        from api import ntfy_push
        return bool(ntfy_push.send(note, log=lambda t: print("[ntfy] " + t)))
    except Exception as e:
        print(f"push failed: {type(e).__name__}: {e}")
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="NT8 paper pipeline silent-failure sweep")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-firestore", action="store_true")
    a = ap.parse_args(argv)
    now_ts = int(time.time())
    now_local = dt.datetime.now()
    items = []
    if not a.dry_run:
        try:
            msg = maybe_backup(now_local)
            if msg:
                print(msg)
        except Exception as e:
            items.append(_item("nt_backup_run", "warn", "NinjaTrader nightly backup",
                               f"the daytime snapshot crashed: {type(e).__name__}: {e}"))
    for fn in (lambda: check_tasks(now_local), lambda: check_box_push(now_local), lambda: check_nt_backup(now_local),
               lambda: check_roster(now_local), lambda: check_capture(now_ts), lambda: check_repair(now_ts),
               lambda: check_readiness(now_ts), lambda: check_roll_watch(now_local)):
        try:
            items += fn()
        except Exception as e:
            items.append(_item("sweep_error", "warn", "Sweep", f"a check crashed: {type(e).__name__}: {e}"))
    if not a.no_firestore:
        items += check_report_and_bundle(now_ts)
    if a.json:
        print(json.dumps(items, indent=1))
    else:
        for i in items:
            print("%-5s %-30s %s" % (i["status"].upper(), i["label"], i["detail"]))
    try:
        state = json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception:
        state = {}
    alert, new_state = decide_alert(items, state, now_ts)
    if alert:
        msg = build_message(items)
        print("alert: " + ("would post" if a.dry_run else "posting"))
        if not a.dry_run:
            _post_inbox(msg)
    # the phone push has its own rule (module doc): plain text, no order flow, once a day, back-to-normal
    action, push_state, note = decide_push(items, state.get("push"), now_ts, now_local)
    if note:
        print("push: " + ("would send" if a.dry_run else "sending"))
        if a.dry_run:
            print("  title: %s\n  priority: %s\n  %s" % (note["title"], note["priority"], note["message"].replace("\n", "\n  ")))
        elif not _push_note(note):
            push_state = state.get("push") or {}          # not delivered: try again on the next run
    new_state = dict(new_state, push=push_state)
    if not a.dry_run:
        for path, obj in ((STATE_PATH, new_state), (RESULT_PATH, {"at": now_ts, "items": items})):
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=1, default=str)
            os.replace(tmp, path)
    return 1 if any(i["status"] == "fail" for i in items) else 0


if __name__ == "__main__":
    sys.exit(main())
