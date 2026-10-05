r"""tools/webull_freshness_pc.py -- the Webull pipeline FRESHNESS MONITOR, PC side (one pass).

The box half (tools/webull_freshness.py on edgelog-freshness.timer) pages the owner's phone over
ntfy around the clock. This half runs on the owner's PC as the scheduled task "EdgeLog Webull
freshness" (deploy/windows/EdgeLog_Webull_freshness.xml), every 10 minutes while the PC is on,
and does two things the box cannot (C:\EdgeLog\manager\webull_sweep_1005\
WEBULL_SILENT_FAILURES.md, "Proposed single freshness monitor", part 2):

  1. WATCHES THE WATCHER. One read-only ssh call reads the box monitor's status.json and
     freshness_heartbeat.json. ssh failing on 2 runs in a row (20 min) is an alert; the box
     monitor's heartbeat older than 10 min is an alert (its timer, the box or its network is
     dead); every alert the box still has OPEN when this runs is relayed here too, so the
     lanes see a problem ntfy paged at night that is still open when the PC wakes. An
     episode that opened AND closed while the PC was off or asleep is not relayed -- ntfy (the
     phone) and the box's freshness.log carry it. A box alert that closes because its window
     ended (the pre-open gate at 09:30) is relayed as CLOSED, not CLEARED: nothing was fixed.
  2. READS PC-ONLY LOGS that nothing on the box can see:
       push_nq_master.log    on session days, an OK (or SKIP: already current) line stamped
                             from 10 min after the close (the task fires at 14:20 Arizona
                             time = 17:20 EDT / 16:20 EST), judged from 17:35 ET (#10); stays
                             open until a later push lands, so a missed night is still open
                             the next morning.
       pull_box_ledgers.log  last result FAIL, or no OK in 36 h (#26).
       backup_repos.log      no "=== nightly backup ok ===" in 36 h (#35).

ALERTS go to the MANAGER and PAPER-WB chat inboxes (tools/chat_inbox.py, from
PAPER-WB-MONITOR): one post per inbox per run, and only for NEW episodes and for episodes that
CLEARED -- the same once-per-episode + recovery rule the box uses (its apply_verdicts is
reused). Delivery is tracked PER INBOX: each run's text is queued once for each inbox in
state.json ("pending_posts") and an entry leaves the queue only when that inbox was written,
so an inbox that could not be written is retried next run on its own (the other one never
gets a duplicate) and a cleared notice is retried too; entries older than 3 days are dropped
with a log line. state.json (episodes + the queue) is saved BEFORE the first post and again
after every post that lands, so delivery is AT-LEAST-ONCE with a one-post window: only a
process killed between an inbox write and the save right after it posts that text twice. Memory lives in <EDGELOG_HOME>\freshness_pc\state.json, a log in
<EDGELOG_HOME>\logs\webull_freshness_pc.log.

RUNS UNDER pythonw / TASK SCHEDULER: no console is needed or opened. ssh is called by its
explicit path (C:\Windows\System32\OpenSSH\ssh.exe when present) with BatchMode, stdin closed
and CREATE_NO_WINDOW, so it can never prompt or flash a window. Never writes on the box, never
touches Webull, never prints a secret.

Usage:  pythonw tools\webull_freshness_pc.py         (the scheduled task)
        python  tools\webull_freshness_pc.py --dry-run   (print what it would post; no writes)
"""
import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _log_import_fatal(e):
    """Under pythonw a failed import has no console: leave ONE line in the task's log, so a
    broken install does not look the same as a task that never ran."""
    home = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
    path = os.path.join(home, "logs", "webull_freshness_pc.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} [freshness-pc] FATAL "
                    f"import failed: {type(e).__name__}: {e}\n")
    except OSError:
        pass


try:
    from tools import webull_freshness as wf  # noqa: E402  (shared episode logic + calendar)
except Exception as _e:   # ImportError, or anything the import chain raises
    if __name__ == "__main__":
        _log_import_fatal(_e)
        sys.exit(1)
    raise

HOST = "ubuntu@163.192.117.12"
SSH_KEY = os.path.expanduser(os.path.join("~", ".ssh", "edgelog_oracle"))
REMOTE_DIR = "/home/ubuntu/edgelog/freshness"
SPLIT = "@@EDGELOG-FRESHNESS-SPLIT@@"
INBOXES = ("MANAGER", "PAPER-WB")
POST_FROM = "PAPER-WB-MONITOR"

BOX_SILENT_SEC = 600.0
SSH_FAIL_MIN_RUNS = 2
SSH_TIMEOUT_SEC = 60
# The PC task fires at 14:20 PC time (Arizona, no DST): 17:20 ET under EDT but 16:20 ET under
# EST. So a push counts when it is stamped from NQ_PUSH_AFTER_CLOSE_MIN after the due session's
# close (the master needs the whole session), never from a fixed ET clock time, and it is
# judged from NQ_PUSH_DUE ET, which is after the task in both DST states.
NQ_PUSH_AFTER_CLOSE_MIN = 10
NQ_PUSH_DUE = (17, 35)
LEDGER_MAX_AGE_SEC = 36 * 3600.0
BACKUP_MAX_AGE_SEC = 36 * 3600.0
BOX_ALERT_HOLD_SEC = 7 * 86400.0   # a relayed box alert stays as-is while the box is unreadable
POST_MAX_CHARS = 1800
PENDING_MAX_AGE_SEC = 3 * 86400.0

_STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})\s+(.*)$")


def default_paths(home=None):
    home = home or os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
    return {
        "home": home,
        "state": os.path.join(home, "freshness_pc", "state.json"),
        "log": os.path.join(home, "logs", "webull_freshness_pc.log"),
        "push_nq_log": os.path.join(home, "logs", "push_nq_master.log"),
        "pull_ledgers_log": os.path.join(home, "logs", "pull_box_ledgers.log"),
        "backup_log": os.path.join(home, "backup_repos.log"),
    }


def ssh_exe(is_nt=None):
    """Explicit ssh path: Task Scheduler's environment can lack the user's PATH."""
    is_nt = (os.name == "nt") if is_nt is None else is_nt
    win = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH",
                       "ssh.exe")
    if is_nt and os.path.exists(win):
        return win
    return shutil.which("ssh") or "ssh"


def fetch_box(run_cmd=None):
    """{"ok", "status", "heartbeat", "error"} from ONE read-only ssh call (two `cat`s)."""
    run_cmd = run_cmd or subprocess.run
    remote = (f"cat {REMOTE_DIR}/status.json 2>/dev/null; echo; echo {SPLIT}; "
              f"cat {REMOTE_DIR}/freshness_heartbeat.json 2>/dev/null; true")
    kw = {"capture_output": True, "text": True, "timeout": SSH_TIMEOUT_SEC,
          "stdin": subprocess.DEVNULL, "encoding": "utf-8", "errors": "replace"}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    cmd = [ssh_exe(), "-i", SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", HOST,
           remote]
    try:
        r = run_cmd(cmd, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "status": None, "heartbeat": None,
                "error": f"{type(e).__name__}"}
    out = r.stdout or ""
    if r.returncode != 0 or SPLIT not in out:
        err = (r.stderr or "").strip().splitlines()
        return {"ok": False, "status": None, "heartbeat": None,
                "error": f"ssh rc={r.returncode}: {err[-1][:160] if err else 'no output'}"}
    a, b = out.split(SPLIT, 1)

    def _parse(text):
        text = text.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None
    return {"ok": True, "status": _parse(a), "heartbeat": _parse(b), "error": None}


# -- PC log readers ---------------------------------------------------------------------------
def read_stamped_lines(path, local_tz=None, max_bytes=256 * 1024):
    """[(aware datetime, rest of line)] for every 'YYYY-MM-DD[T ]HH:MM:SS rest' line in the
    tail of `path` (PC local time). Missing file -> None."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    out = []
    for ln in text.splitlines():
        m = _STAMP_RE.match(ln.strip())
        if not m:
            continue
        try:
            naive = _dt.datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        stamp = naive.replace(tzinfo=local_tz) if local_tz else naive.astimezone()
        out.append((stamp, m.group(3).strip()))
    return out


def _status_word(rest):
    return (rest.split() or [""])[0].upper()


def check_push_nq(path, now_et, local_tz=None):
    due = wf.latest_session_due(now_et, NQ_PUSH_DUE)
    if due is None:
        return None
    since = wf.at(due, wf.close_hhmm(due)) + _dt.timedelta(minutes=NQ_PUSH_AFTER_CLOSE_MIN)
    lines = read_stamped_lines(path, local_tz)
    if lines is None:
        return [wf._verdict("nq_push", "pc", False, wf.HIGH, "NQ master push log missing",
                            f"{path} does not exist")]
    good = [t for t, rest in lines if _status_word(rest) in ("OK", "SKIP") and t >= since]
    status_lines = [(t, rest) for t, rest in lines if _status_word(rest) in ("OK", "SKIP", "FAIL")]
    last = status_lines[-1] if status_lines else None
    last_txt = (f"last result {last[0].astimezone(wf.ET).strftime('%a %m-%d %H:%M ET')}: "
                f"{last[1][:160]}") if last else "no result line"
    return [wf._verdict(
        "nq_push", "pc", bool(good), wf.HIGH, "NQ master push to the box MISSED",
        f"no OK push since {since.strftime('%Y-%m-%d %H:%M')} ET ({last_txt}). Run "
        f"`python tools/push_nq_master_to_box.py` on the PC; KEEL trains on the old copy "
        f"until it lands.")]


def check_ledger_pull(path, now_et, local_tz=None):
    lines = read_stamped_lines(path, local_tz)
    if lines is None:
        return [wf._verdict("ledger_pull", "pc", False, wf.MEDIUM, "box ledger pull log missing",
                            f"{path} does not exist")]
    results = [(t, rest) for t, rest in lines if _status_word(rest) in ("OK", "FAIL")]
    oks = [t for t, rest in results if _status_word(rest) == "OK"]
    newest_ok = max(oks) if oks else None
    age = (now_et - newest_ok).total_seconds() if newest_ok else None
    last_fail = bool(results) and _status_word(results[-1][1]) == "FAIL"
    bad = last_fail or age is None or age > LEDGER_MAX_AGE_SEC
    return [wf._verdict(
        "ledger_pull", "pc", not bad, wf.MEDIUM, "box ledger backup to the PC failing",
        f"last result {'FAIL' if last_fail else 'OK'}; newest OK {wf.fmt_age(age)} ago "
        f"(limit 36 h) -- the only off-box copy of the book's ledgers is going stale.")]


def check_backup(path, now_et, local_tz=None):
    lines = read_stamped_lines(path, local_tz)
    if lines is None:
        return [wf._verdict("nightly_backup", "pc", False, wf.MEDIUM,
                            "nightly backup log missing", f"{path} does not exist")]
    oks = [t for t, rest in lines if "=== nightly backup ok ===" in rest]
    newest = max(oks) if oks else None
    age = (now_et - newest).total_seconds() if newest else None
    return [wf._verdict(
        "nightly_backup", "pc", age is not None and age <= BACKUP_MAX_AGE_SEC, wf.MEDIUM,
        "nightly backup has not completed",
        f"newest 'nightly backup ok' {wf.fmt_age(age)} ago (limit 36 h).")]


def check_box(box, now_et):
    """Verdicts for the ssh link, the box monitor's own heartbeat and every alert it has
    open. Returns (verdicts, groups_ran): the "box" group only runs when the box answered, so
    relayed alerts are neither cleared nor expired by an ssh outage."""
    verdicts = [wf._verdict("box_ssh", "ssh", box["ok"], wf.HIGH,
                            "cannot reach the box over ssh",
                            f"{box.get('error')} -- the PC cannot see the box monitor; the "
                            f"box still pages ntfy on its own.", min_runs=SSH_FAIL_MIN_RUNS)]
    groups = {"ssh"}
    if not box["ok"]:
        return verdicts, groups
    hb = box.get("heartbeat") if isinstance(box.get("heartbeat"), dict) else None
    status = box.get("status") if isinstance(box.get("status"), dict) else None
    # The relayed alerts (and the outbox depth) come from status.json: only a status that
    # parsed as a dict may clear them. A missing or half-written one leaves every relayed
    # episode exactly as it was (the "box" group does not run, so nothing is swept as CLEARED
    # and re-posted as NEW on the next good read) and is its own alert after 2 runs.
    verdicts.append(wf._verdict(
        "box_status", "ssh", status is not None, wf.HIGH, "box monitor status.json unreadable",
        "status.json on the box is missing or not valid JSON -- the PC cannot see the box's "
        "open alerts (the box still pages ntfy on its own).", min_runs=SSH_FAIL_MIN_RUNS))
    if status is not None:
        groups.add("box")
    try:
        hb_age = now_et.timestamp() - float(hb.get("epoch")) if hb else None
    except (TypeError, ValueError):
        hb_age = None
    verdicts.append(wf._verdict(
        "box_monitor", "box", hb_age is not None and hb_age <= BOX_SILENT_SEC, wf.HIGH,
        "box freshness monitor is SILENT",
        (f"its heartbeat is {wf.fmt_age(hb_age)} old (limit 10 min)" if hb else
         "its heartbeat file is missing (never ran, or not installed)")
        + " -- edgelog-freshness.timer, the box or its network is down, so nothing is "
          "paging. `systemctl status edgelog-freshness.timer` on the box."))
    relayed = set()
    for a in (status or {}).get("open_alerts") or []:
        if not isinstance(a, dict) or not a.get("key"):
            continue
        v = wf._verdict(
            f"box:{a['key']}", "box", False, a.get("severity") or wf.HIGH,
            f"box: {a.get('title')}",
            f"{a.get('detail') or ''} (box: open since {a.get('opened_et')})")
        if a.get("quiet_expire"):
            # closes on the box when its window ends (pre-open gate at 09:30): when it goes
            # away the PC says CLOSED, not CLEARED (apply_verdicts' window_alert)
            v["window_alert"] = True
        verdicts.append(v)
        relayed.add(a["key"])
    po = (status or {}).get("preopen")
    slots = po.get("slots") if isinstance(po, dict) else None
    if (isinstance(slots, dict) and slots and "preopen" not in relayed
            and po.get("date") == now_et.date().isoformat()):
        last_slot = slots[max(slots)]
        if isinstance(last_slot, dict) and last_slot.get("misses") == []:
            # today's latest pre-open slot PASSED ("QQQ book ready (fixed since ...)"): that
            # one really is cleared, so say so before the window rule can call it closed
            verdicts.append(wf._verdict("box:preopen", "box", True, wf.URGENT,
                                        "box: QQQ book NOT ready"))
    pending = int((status or {}).get("outbox_pending") or 0)
    verdicts.append(wf._verdict(
        "box_outbox", "box", (pending == 0) if status is not None else None, wf.MEDIUM,
        "box cannot deliver phone alerts",
        f"{pending} ntfy push(es) queued in the box monitor's outbox -- the phone is not "
        f"getting them (ntfy unreachable, or NTFY_TOPIC/NTFY_TOKEN wrong)."))
    for v in verdicts:
        if v["group"] == "box":
            v["hold_sec"] = BOX_ALERT_HOLD_SEC
    return verdicts, groups


def compose_post(opened, recovered, expired):
    """One inbox text for this run's new and cleared episodes, or None."""
    if not (opened or recovered or expired):
        return None
    parts = []
    for r in opened:
        parts.append(f"NEW [{r['severity']}] {r['title']}: {r['detail']}")
    for r in recovered:
        parts.append(f"CLEARED {r['title']} (open since {r.get('opened_et')})")
    for r in expired:
        parts.append(f"CLOSED (no longer checked, never seen OK) {r['title']}")
    text = "WEBULL FRESHNESS MONITOR: " + " | ".join(parts)
    if len(text) > POST_MAX_CHARS:
        text = text[:POST_MAX_CHARS - 40] + " ... (more in webull_freshness_pc.log)"
    return text


def _make_logger(path):
    def log(line):
        stamp = _dt.datetime.now().isoformat(timespec="seconds")
        try:
            print(f"{stamp} {line}", flush=True)   # a no-op under pythonw (no stdout)
        except (OSError, ValueError, AttributeError):
            pass
        if path:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"{stamp} {line}\n")
            except OSError:
                pass
    return log


def _default_post(chat, text, frm):
    from tools import chat_inbox
    return chat_inbox.post(chat, text, frm)


def flush_posts(pending, post_fn, now_epoch, log, save=None):
    """Write each queued (inbox, text) entry, oldest first. Returns (still pending, [inboxes
    written this run]). A failed entry stays queued for next run, and later entries for the
    SAME inbox wait behind it so that inbox keeps its order; other inboxes go ahead.
    `save(still_queued)`, when given, is called after every entry that was written, so a run
    killed later in the flush never posts that entry again."""
    left, posted, blocked = [], [], set()
    for i, item in enumerate(pending):
        if not isinstance(item, dict) or not item.get("chat") or not item.get("text"):
            continue
        chat = item["chat"]
        created = item.get("created_epoch")
        if created is not None and now_epoch - float(created) > PENDING_MAX_AGE_SEC:
            log(f"[freshness-pc] dropped an inbox post to {chat} undeliverable for 3 days")
            continue
        if chat in blocked:
            left.append(item)
            continue
        text = item["text"]
        if item.get("attempts"):
            text = f"(delayed: raised {item.get('created_et')}) {text}"
        try:
            post_fn(chat, text, POST_FROM)
        except Exception as e:
            item["attempts"] = int(item.get("attempts") or 0) + 1
            left.append(item)
            blocked.add(chat)
            log(f"[freshness-pc] inbox post to {chat} failed (kept for next run): "
                f"{type(e).__name__}: {e}")
            continue
        posted.append(chat)
        if save is not None:
            try:
                save(left + list(pending[i + 1:]))
            except OSError as e:
                log(f"[freshness-pc] state save after a post failed: {type(e).__name__}")
    return left, posted


def run_once(paths=None, now=None, run_cmd=None, post_fn=None, dry_run=False, local_tz=None,
             log=None):
    paths = paths or default_paths()
    log = log or _make_logger(None if dry_run else paths["log"])
    now_et = (now or _dt.datetime.now(tz=wf.ET)).astimezone(wf.ET)
    now_epoch = now_et.timestamp()
    label = now_et.strftime("%a %m-%d %H:%M ET")
    state, _ = wf.read_json(paths["state"])
    state = state if isinstance(state, dict) else {}
    alerts = state.setdefault("alerts", {})

    box = fetch_box(run_cmd)
    verdicts, groups = check_box(box, now_et)
    try:
        verdicts += ((check_push_nq(paths["push_nq_log"], now_et, local_tz) or [])
                     + check_ledger_pull(paths["pull_ledgers_log"], now_et, local_tz)
                     + check_backup(paths["backup_log"], now_et, local_tz))
        groups.add("pc")
    except Exception as e:   # PC-log checks must never stop the box relay
        log(f"[freshness-pc] PC log checks failed: {type(e).__name__}: {e}")
    opened, recovered, expired = wf.apply_verdicts(alerts, verdicts, groups, now_epoch, label)
    text = compose_post(opened, recovered, expired)
    posted = []
    if text:
        log(f"[freshness-pc] {text}")
    state["last_run_et"] = now_et.isoformat()
    state["box_ok"] = box["ok"]
    if not dry_run:
        pending = state.get("pending_posts")
        pending = pending if isinstance(pending, list) else []
        if text:
            pending += [{"chat": chat, "text": text, "created_epoch": now_epoch,
                         "created_et": label} for chat in INBOXES]
        # this run's episodes WITH the posts they queued are saved before anything is posted,
        # and again after each post that lands (see the docstring: at-least-once, one-post
        # window)
        state["pending_posts"] = pending
        wf.write_json_atomic(paths["state"], state)

        def _save(left):
            state["pending_posts"] = left
            wf.write_json_atomic(paths["state"], state)
        state["pending_posts"], posted = flush_posts(pending, post_fn or _default_post,
                                                     now_epoch, log, save=_save)
        wf.write_json_atomic(paths["state"], state)
    return {"verdicts": verdicts, "opened": opened, "recovered": recovered,
            "expired": expired, "text": text, "posted": posted, "box": box,
            "pending_posts": len(state.get("pending_posts") or [])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and print; no inbox post, no state written")
    a = ap.parse_args(argv)
    try:
        out = run_once(dry_run=a.dry_run)
    except Exception as e:
        _make_logger(None if a.dry_run else default_paths()["log"])(
            f"[freshness-pc] FATAL {type(e).__name__}: {e}")
        return 1
    if a.dry_run:
        for v in out["verdicts"]:
            ok = {True: "ok  ", False: "FAIL", None: "?   "}[v["ok"]]
            print(f"{ok} {v['key']}: {v['title']}" + ("" if v["ok"] else f" -- {v['detail']}"))
        print(f"WOULD POST: {out['text']}" if out["text"] else "nothing new to post")
    return 0


if __name__ == "__main__":
    sys.exit(main())
