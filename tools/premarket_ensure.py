r"""Make sure this PC is awake and the forward-test is running BEFORE the opening bell.

WHY THIS EXISTS (2026-09-10, the third invalid day in a row). The shadow book needs ten
valid trading days before any real money is risked, and it had recorded zero. The first two
failures were deploys restarting the runner mid-session, which the standalone adapter fixed.
The third was simpler and worse: **the PC was asleep.** Windows logged sleep at 21:42 and
wake at 10:18 local, so the machine slept straight through the 09:30 ET open and the adapter
did not record its first tick until 13:20 ET -- nearly four hours of the session simply gone.
`keep_awake.ps1` cannot help: it holds a machine that is ALREADY awake and never wakes one.

Nothing on this box was set to wake it. The only EdgeLog task with WakeToRun was disabled
and fired in the evening. So this script exists to be run by a scheduled task whose
"Wake the computer to run this task" box is ticked -- the wake itself is the point, and
everything below is the belt-and-braces check that we came back up whole.

DELIBERATELY NEVER KILLS ANYTHING. It runs before the open, when a long overnight validate
may still be working, and a restart to "make sure things are fresh" would throw that away
for nothing. It only ever starts what is missing.

Run:  python tools/premarket_ensure.py           # ensure, log, exit
      python tools/premarket_ensure.py --check    # report only, start nothing
"""
import argparse
import datetime
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LOG = r"C:\EdgeLog\premarket.log"
FLEET_BAT = r"C:\EdgeLog\_restart_runner_hidden.vbs"


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def runner_pids():
    """Live api.runner processes. Filtered on the image name as well as the command line:
    a PowerShell process running this very query matches '*api.runner*' through its own
    command line, which has cost this repo a shell before now."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
          "$_.CommandLine -like '*api.runner*' } | ForEach-Object { $_.ProcessId }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=90).stdout
        return [p for p in out.split() if p.strip().isdigit()]
    except Exception as e:
        log(f"could not list runner processes: {type(e).__name__}: {e}")
        return []


def repair_capture(check_only=False):
    """Merge the Tick Replay sidecars NinjaTrader wrote at its last start into NQ/ES_10s.csv
    (tools/repair_10s_from_replay.py): bars written with no trade ticks while the PC slept get
    their buy/sell back before the readiness check judges overnight coverage. Separate process,
    never fatal; idempotent (a bar already carrying buy/sell is left alone)."""
    cmd = [sys.executable, "-u", os.path.join(ROOT, "tools", "repair_10s_from_replay.py")]
    if check_only:
        cmd.append("--dry-run")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=ROOT)
        for ln in (r.stdout or "").splitlines():
            if ln.strip():
                log("repair: " + ln.strip())
        if r.returncode != 0:
            log(f"repair exited {r.returncode}: {(r.stderr or '').strip()[-300:]}")
    except Exception as e:
        log(f"repair could not run: {type(e).__name__}: {e}")


def readiness(check_only=False):
    """Run the premarket NinjaTrader readiness check (tools/nt_readiness.py) as a separate process
    so nothing it does can break the wake-up work above. --early: NinjaTrader is probably still
    starting, so start-up-class failures are recorded but not pushed (the 09:15 / 09:25 ET
    scheduled runs push those). Outside 08:00-09:35 ET on a trading day it prints SKIPPED."""
    cmd = [sys.executable, "-u", os.path.join(ROOT, "tools", "nt_readiness.py"), "--early"]
    if check_only:
        cmd.append("--dry-run")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=ROOT)
        for ln in (r.stdout or "").splitlines():
            log("readiness: " + ln)
        if r.returncode not in (0, 1):
            log(f"readiness check crashed (exit {r.returncode}): {(r.stderr or '').strip()[-300:]}")
    except Exception as e:
        log(f"readiness check could not run: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report only, start nothing")
    a = ap.parse_args()

    log("=== pre-market check ===")
    pids = runner_pids()
    log(f"runner processes: {len(pids)}")

    if not pids:
        if a.check:
            log("WOULD launch the runner fleet (none running)")
        elif os.path.exists(FLEET_BAT):
            # Detached, via wscript: a runner started from a console dies with it and
            # orphans into a popup loop (see memory edgelog-runner-launch-detached).
            subprocess.Popen(["wscript.exe", FLEET_BAT], close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            log("launched the runner fleet")
        else:
            log(f"NO fleet launcher at {FLEET_BAT} -- cannot start the runner")

    try:
        from api import qqq_exec as qe
        alive, pid = qe.serving_alive()
        if alive:
            log(f"shadow adapter already serving (pid {pid})")
        elif a.check:
            log("WOULD launch the shadow adapter (not serving)")
        else:
            log(f"shadow adapter not serving -> launching: {qe.ensure_standalone(log=log)}")
    except Exception as e:
        log(f"adapter check failed: {type(e).__name__}: {e}")

    repair_capture(check_only=a.check)
    readiness(check_only=a.check)
    log("=== done ===")


if __name__ == "__main__":
    main()
