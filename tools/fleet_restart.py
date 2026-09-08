"""Keep-aware restart of the EdgeLog runner set (primary + drain-only workers).

WHY (2026-09-08): every runner restart went through C:\\EdgeLog\\_restart_runner.bat, which
kills EVERY api.runner python and relaunches the whole set. Sibling sessions ship runner
code several times a day and restart to pick it up, so a long Auto-Validate never got to
finish: the ENGU-Q R2 validate (a ~6 hour job) was killed FOUR times in one day, the last
time at 89 percent, and each time restarted from zero on the next claim. A restart that
only exists to load new code has no reason to kill a worker that is mid-job.

WHAT: the bat now delegates its kill + worker-relaunch step to this file (`--helper`) and
honours EDGELOG_KEEP, a comma list of worker numbers and/or the word `primary` that must be
left running. Everything else is killed and relaunched exactly as before.

    python tools/fleet_restart.py --list            # who is running, with role and pid
    python tools/fleet_restart.py --keep 2          # restart the set, leave worker 2 alone
    python tools/fleet_restart.py --keep 2 3 primary
    python tools/fleet_restart.py                   # full restart, same as before

`--keep` sets EDGELOG_KEEP and launches C:\\EdgeLog\\_restart_runner_hidden.vbs, so the
restart still runs DETACHED (hard rule: a runner started from a tool shell orphans when the
desktop app restarts - see memory `edgelog-runner-launch-detached`). The environment is
inherited wscript -> cmd -> bat -> `--helper`, which is where the kill list is applied.

A kept number whose worker is NOT running is simply launched - keep protects a live
process, it never leaves a slot empty. A kept `primary` makes the bat skip its own primary
launch (helper exit code 3), so no second primary is ever stacked on the first.

ROLE DETECTION: a worker's role lives only in its environment (EDGELOG_WORKER=N, set by
_run_worker.vbs inside a `cmd /c "set EDGELOG_WORKER=N && ..."` wrapper) - it is NOT on
the python's own command line. The wrapper cmd's command line does carry it, so the role
comes from the PARENT process; a python api.runner whose parent carries no EDGELOG_WORKER
is the primary (it also carries --refresh-min 240 on its own line, used as a fallback).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

EDGELOG_DIR = r"C:\EdgeLog"
WORKER_VBS = os.path.join(EDGELOG_DIR, "_run_worker.vbs")
HIDDEN_VBS = os.path.join(EDGELOG_DIR, "_restart_runner_hidden.vbs")
LOG_PATH = os.path.join(EDGELOG_DIR, "fleet_restart.log")
WORKER_RE = re.compile(r"EDGELOG_WORKER=(\d+)")
RUNNER_RE = re.compile(r"api\.runner")


# ── pure helpers (unit-tested with fake process rows, no live processes) ─────────────
def parse_keep(text):
    """'2, 3,primary' -> {'2', '3', 'primary'}; blank/None -> empty set."""
    out = set()
    for tok in re.split(r"[,\s]+", (text or "").strip()):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok == "primary" or tok.isdigit():
            out.add(tok)
        else:
            raise SystemExit("bad --keep token %r (worker number or 'primary')" % tok)
    return out


def classify(rows):
    """rows: iterable of dicts {pid, ppid, name, cmd}. Returns the runner inventory as a
    list of {pid, role, cmd} where role is 'primary' or 'worker <N>'. A row is a runner
    when its NAME starts with python and its command line mentions api.runner; a shell
    whose command line merely mentions api.runner is never a runner (the bat's own rule)."""
    by_pid = {int(r["pid"]): r for r in rows}
    inv = []
    for r in rows:
        name = (r.get("name") or "").lower()
        cmd = r.get("cmd") or ""
        if not name.startswith("python") or not RUNNER_RE.search(cmd):
            continue
        parent = by_pid.get(int(r.get("ppid") or 0)) or {}
        m = WORKER_RE.search(parent.get("cmd") or "") or WORKER_RE.search(cmd)
        role = ("worker " + m.group(1)) if m else "primary"
        inv.append({"pid": int(r["pid"]), "role": role, "cmd": cmd})
    inv.sort(key=lambda x: (x["role"] != "primary", x["role"], x["pid"]))
    return inv


def plan(inventory, keep, n_workers):
    """Decide what to kill and what to launch.

    Returns dict(kill=[pids], launch=[worker numbers], keep_primary=bool).
    - a runner is killed unless its role is kept ('primary' or its worker number)
    - every worker number 2..1+n_workers is launched unless a KEPT worker with that number
      is alive right now (a kept number with no live process gets launched anyway)
    - keep_primary is True only when 'primary' is in keep AND a primary is alive
    """
    kill, alive_kept = [], set()
    for r in inventory:
        role = r["role"]
        key = "primary" if role == "primary" else role.split()[1]
        if key in keep:
            alive_kept.add(key)
        else:
            kill.append(r["pid"])
    launch = [n for n in range(2, 2 + int(n_workers)) if str(n) not in alive_kept]
    return {"kill": kill, "launch": launch, "keep_primary": "primary" in alive_kept}


# ── live process access (Windows) ──────────────────────────────────────────────────
def live_rows():
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|cmd)' } "
          "| Select-Object @{n='pid';e={$_.ProcessId}},@{n='ppid';e={$_.ParentProcessId}},"
          "@{n='name';e={$_.Name}},@{n='cmd';e={$_.CommandLine}} | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def kill_pid(pid):
    try:
        os.kill(pid, 9)
        return True
    except OSError:
        r = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
        return r.returncode == 0


def launch_worker(n):
    subprocess.Popen(["wscript", WORKER_VBS, str(n)], close_fds=True)


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def fmt_inventory(inv):
    if not inv:
        return "  (no api.runner python running)"
    return "\n".join("  %-10s pid %d" % (r["role"], r["pid"]) for r in inv)


# ── entry points ───────────────────────────────────────────────────────────────────
def run_helper(keep, n_workers):
    """The step the bat calls: kill everything not kept, relaunch the workers not kept.
    Exit 3 tells the bat the primary is kept and it must NOT launch another one."""
    inv = classify(live_rows())
    p = plan(inv, keep, n_workers)
    log("helper: keep=%s  running before:\n%s" % (sorted(keep) or "-", fmt_inventory(inv)))
    for pid in p["kill"]:
        ok = kill_pid(pid)
        log("  killed pid %d%s" % (pid, "" if ok else "  (kill FAILED)"))
    if p["kill"]:
        time.sleep(4)
    for n in p["launch"]:
        launch_worker(n)
        log("  launched worker %d" % n)
        time.sleep(2)
    if p["keep_primary"]:
        log("  primary kept - the bat will not launch another")
        return 3
    return 0


def run_keep(keep):
    """User-facing: hand the keep list to the detached launcher and return."""
    env = dict(os.environ)
    env["EDGELOG_KEEP"] = ",".join(sorted(keep))
    log("restart requested keep=%s via %s" % (sorted(keep) or "-", HIDDEN_VBS))
    subprocess.Popen(["wscript", HIDDEN_VBS], env=env, close_fds=True)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the running runner set")
    ap.add_argument("--keep", nargs="*", default=None,
                    help="worker numbers and/or 'primary' to leave running")
    ap.add_argument("--helper", action="store_true",
                    help="(called by _restart_runner.bat) apply EDGELOG_KEEP: kill + relaunch")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("EDGELOG_WORKERS") or 4),
                    help="number of drain-only workers in the set (default EDGELOG_WORKERS or 4)")
    a = ap.parse_args(argv)

    if a.helper:
        return run_helper(parse_keep(os.environ.get("EDGELOG_KEEP")), a.workers)
    if a.list:
        print(fmt_inventory(classify(live_rows())))
        return 0
    keep = parse_keep(" ".join(a.keep)) if a.keep is not None else set()
    if a.keep is None:
        print("full restart (nothing kept) - same as running _restart_runner_hidden.vbs")
    return run_keep(keep)


if __name__ == "__main__":
    sys.exit(main())
