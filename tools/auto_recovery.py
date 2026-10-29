"""auto_recovery.py -- B16 (AUTOMATIONS.md): find detached jobs that died mid-run, each morning.

Reads every launcher C:/EdgeLog/detach/<name>.cmd written by C:/EdgeLog/detach.py in the last
--days days, finds its log, and classifies the job from the log text alone (read-only):
  OK       wt.py ship that printed "pushed (verified on main)", or any job whose last
           "[detach] ... exit N" line says exit 0
  FAILED   last exit line N != 0, or a ship whose log shows ABORT / Traceback / refused with no push
  DIED     no exit line and no push, log untouched for more than --stale-h hours
           (the app quit / PC off killed it: the job object rule)
  RUNNING  no end marker yet, log written recently
  UNKNOWN  a non-ship job with no end marker and no error line (older launchers wrote no exit line)
  SUPERSEDED a dead ship whose worktree landed on a later launch
FAILED and DIED rows carry the exact relaunch line. Nothing is relaunched here: the worktree may have
moved on since the launch, so the owning chat re-launches after reading its log (house rule
"ship logs before a hold").

    python tools/auto_recovery.py [--days 3] [--stale-h 6] [--json]
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

HOME = os.environ.get("EDGELOG_HOME", r"C:\EdgeLog")
DETACH = os.path.join(HOME, "detach")
LOG_RE = re.compile(r'>>\s*"([^"]+)"\s*2>&1\s*$')
CD_RE = re.compile(r'^cd /d "([^"]+)"', re.M)
EXIT_RE = re.compile(r"\[detach\][^\r\n]* exit (-?\d+)\s*$", re.M)
EXIT_BLANK_RE = re.compile(r"^\[detach\].* exit\s*$", re.M)
START_RE = re.compile(r"^\[detach\].* start: ", re.M)
KILLED_AT_SIGNOUT = 1073807364   # 0x40010004: Windows ended the process at logoff / shutdown
SHIP_RE = re.compile(r"wt\.py ship\s+(\S+)")
BAD_RE = re.compile(r"ABORT|Traceback|refus|giving up", re.I)


def parse_cmd(path):
    with open(path, encoding="ascii", errors="replace") as f:
        txt = f.read()
    line = log = None
    for ln in txt.splitlines():
        m = LOG_RE.search(ln)
        if m and not ln.startswith("echo"):
            log, line = m.group(1), ln[:m.start()].strip()
    cd = CD_RE.search(txt)
    return {"name": os.path.splitext(os.path.basename(path))[0], "cmd": line, "log": log,
            "cwd": cd.group(1) if cd else None}


def classify(job, now, stale_h):
    log = job["log"]
    if not log or not os.path.exists(log):
        return "FAILED", "log missing"
    with open(log, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    starts = list(START_RE.finditer(txt))
    tail = txt[starts[-1].start():] if starts else txt          # the newest launch only
    is_ship = "wt.py ship" in (job["cmd"] or "")
    age_h = (now - datetime.datetime.fromtimestamp(os.path.getmtime(log))).total_seconds() / 3600
    ex = EXIT_RE.findall(tail)
    if is_ship and "pushed (verified on main)" in tail:
        return "OK", "landed"
    if not ex and EXIT_BLANK_RE.search(tail):
        if is_ship:
            return "FAILED", "ship ended without a push (exit code not recorded) - last line: %s" % _last(tail)
        bad = BAD_RE.search(tail)
        if bad:
            return "FAILED", "ended, exit code not recorded - " + _line_of(tail, bad.start())
        return "UNKNOWN", "ended, exit code not recorded"
    if not ex and is_ship and age_h > stale_h and BAD_RE.search(tail) is None:
        return "DIED", "ship log stopped before a push, idle %.0f h - last line: %s" % (age_h, _last(tail))
    if ex:
        code = int(ex[-1])
        if code == KILLED_AT_SIGNOUT:
            return "DIED", "killed at sign-out / shutdown (exit 0x40010004)"
        if code == 0 and not (is_ship and BAD_RE.search(tail)):
            return "OK", "exit 0"
        bad = BAD_RE.search(tail)
        return "FAILED", "exit %d%s" % (code, (" - " + _line_of(tail, bad.start())) if bad else "")
    if age_h > stale_h:
        bad = BAD_RE.search(tail)
        if not is_ship and not bad:
            return "UNKNOWN", "no end marker (older launcher or killed), log idle %.0f h - check it if you still need it" % age_h
        return "DIED", "no end marker, log idle %.0f h%s" % (age_h, (" - " + _line_of(tail, bad.start())) if bad else "")
    return "RUNNING", "log written %.1f h ago" % age_h


def _last(txt):
    lines = [l for l in txt.strip().splitlines() if not l.startswith("[detach]")]
    return (lines[-1] if lines else "")[:120]


def _line_of(txt, pos):
    a = txt.rfind("\n", 0, pos) + 1
    b = txt.find("\n", pos)
    return txt[a:b if b >= 0 else None].strip()[:140]


def relaunch_line(job):
    return (r"python C:\EdgeLog\detach.py %s --cwd %s --log %s -- %s"
            % (job["name"], job["cwd"], job["log"], job["cmd"]))


def scan(days=3, stale_h=6, now=None, detach_dir=None):
    now = now or datetime.datetime.now()
    cut = now - datetime.timedelta(days=days)
    rows = []
    for p in sorted(glob.glob(os.path.join(detach_dir or DETACH, "*.cmd"))):
        if datetime.datetime.fromtimestamp(os.path.getmtime(p)) < cut:
            continue
        job = parse_cmd(p)
        state, why = classify(job, now, stale_h)
        job.update(state=state, why=why)
        if state in ("FAILED", "DIED"):
            job["relaunch"] = relaunch_line(job)
        m = SHIP_RE.search(job["cmd"] or "")
        job["ship"] = m.group(1) if m else None
        job["mtime"] = os.path.getmtime(p)
        rows.append(job)
    # a dead ship whose worktree landed on a LATER launch is history, not work
    for r in rows:
        if r["state"] in ("FAILED", "DIED") and r["ship"] and any(
                o is not r and o["ship"] == r["ship"] and o["state"] == "OK" and o["mtime"] >= r["mtime"] for o in rows):
            r["state"], r["why"] = "SUPERSEDED", "a later ship of %s landed" % r["ship"]
            r.pop("relaunch", None)
    return rows


def digest_lines(rows):
    bad = [r for r in rows if r["state"] in ("FAILED", "DIED")]
    run = [r for r in rows if r["state"] == "RUNNING"]
    L = ["## Dead or failed jobs (auto-recovery, last %d launch(es))" % len(rows)]
    if not bad:
        L.append("- none: every detached job landed, exited 0 or is still running")
    for r in bad:
        L.append("- %s **%s**: %s (log %s) - owning chat re-launches after reading the log" % (r["state"], r["name"], r["why"], r["log"]))
    if run:
        L.append("- running: " + ", ".join(r["name"] for r in run))
    unk = [r["name"] for r in rows if r["state"] == "UNKNOWN"]
    if unk:
        L.append("- no end marker (may have finished): " + ", ".join(unk))
    L.append("")
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=3)
    ap.add_argument("--stale-h", type=float, default=6)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = scan(a.days, a.stale_h)
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        print("\n".join(digest_lines(rows)))
        for r in rows:
            if "relaunch" in r:
                print("relaunch %s:\n  %s" % (r["name"], r["relaunch"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
