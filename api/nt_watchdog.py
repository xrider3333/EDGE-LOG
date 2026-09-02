"""Read and flip the "EdgeLog NT recover watchdog" scheduled task from the web app.

WHY (owner 2026-08-29: "i just want a button on el to turn it off dawg"). The watchdog task
runs nt_recover.ps1 on a repeating trigger: it relaunches NinjaTrader, logs it in, dials the
Simulation connection and re-enables the strategy roster. That is exactly what you want on a
Tuesday morning and exactly what you do not want on a Saturday, when the futures session is
closed and the only thing it can accomplish is reconnecting a platform nobody is trading.

Until now the only way to stop it was a PowerShell command on the machine itself. This makes
it a button: the web app queues an `nt_watchdog` command, the runner calls in here, and the
task is disabled or enabled. Nothing is deleted -- a disabled scheduled task keeps its
triggers and actions and comes back exactly as it was.

NO ELEVATION NEEDED. The task runs as the logged-in user and is owned by them, so
Disable-ScheduledTask / Enable-ScheduledTask succeed without a UAC prompt (verified
2026-08-26 from an unelevated shell). That matters: a button that pops a UAC dialog on the
owner's 49" screen is not a button, it is an interruption.

DISABLING THE WATCHDOG DOES NOT STOP NINJATRADER. Anything already running keeps running and
any strategy already enabled keeps trading. All this stops is the automatic REPAIR. If
NinjaTrader then dies over the weekend, nothing puts it back until this is switched on again
-- which is the entire point, but it is also why the UI has to say so plainly.

ORPHANED-CONSOLE FAILURE MODE (2026-09-01). api/nt_bridge_pub.py::publish() calls state()
every BRIDGE_SEC (~300s) from the always-on runner. If the runner is itself an ORPHANED
child process -- its own console/parent went away (e.g. launched from a Claude tool shell
that was later closed) rather than being started detached via the hidden VBS launcher -- then
every child `powershell.exe` this module spawns fails to initialize with exit code
0xC0000142 and Windows pops an "Application Error" modal on the owner's screen, roughly once
per cycle. The SetErrorMode() call below suppresses that modal (children inherit the
caller's error mode) so the failure surfaces through returncode/stderr instead of a popup,
and the cache below keeps a bad run from repeating every 5 minutes. DO NOT REMOVE either
guard as a "cleanup" -- the real fix for the underlying condition is launching the runner
detached (C:\\EdgeLog\\_restart_runner_hidden.vbs), not deleting the guard that protects
against it recurring.
"""
import subprocess
import time

TASK = "EdgeLog NT recover watchdog"
_PS = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
       "-Command"]

# 0xC0000142 (STATUS_DLL_INIT_FAILED) as a signed 32-bit int -- what subprocess reports
# when the child process could not start correctly. This is the exact symptom an orphaned
# runner process produces for every powershell.exe it spawns.
_STATUS_DLL_INIT_FAILED = -1073741502

# Suppress the OS "Application Error" popup for child processes we spawn. Must run once,
# at import time, before any _run() call -- SetErrorMode is process-wide and children
# inherit the caller's error mode, so this is what actually stops the modal (CREATE_NO_WINDOW
# alone only hides a console window, it does not suppress the loader-failure dialog).
# Windows-only and best-effort: never let this block import on any other platform or if
# ctypes/kernel32 is unavailable for any reason.
try:
    import ctypes
    SEM_FAILCRITICALERRORS = 0x0001
    SEM_NOGPFAULTERRORBOX = 0x0002
    SEM_NOOPENFILEERRORBOX = 0x8000
    ctypes.windll.kernel32.SetErrorMode(
        SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX)
except Exception:
    pass

# Last-known-good (or last-known-failure) state, cached so the every-5-minute publish loop
# doesn't spawn a fresh powershell each cycle -- the task's state only ever changes when
# someone presses the button. {"ts": float, "state": dict}
_CACHE = {"ts": 0.0, "state": None}
# Separate cache slot for a 0xC0000142 failure: backed off for the same window so the log
# prints ONE warning per half hour instead of one per publish cycle.
_FAIL_CACHE = {"ts": 0.0, "state": None}
_DEFAULT_MAX_AGE_SEC = 1800


def _run(cmd, timeout=30):
    kwargs = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        p = subprocess.run(_PS + [cmd], capture_output=True, text=True, timeout=timeout,
                           **kwargs)
        return (p.stdout or "").strip(), (p.stderr or "").strip(), p.returncode
    except Exception as e:
        return "", "%s: %s" % (type(e).__name__, e), 1


def _orphaned_console_error():
    return ("powershell cannot start from this runner process (0xC0000142) - restart the "
            "runner detached via C:\\EdgeLog\\_restart_runner_hidden.vbs")


def _read_state():
    """Do the actual `Get-ScheduledTask` read. No caching -- callers of state() cache."""
    out, err, rc = _run(
        "$t = Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue; "
        "if ($t) { $t.State } else { 'MISSING' }" % TASK)
    if rc in (_STATUS_DLL_INIT_FAILED, 3221225794):
        return {"ok": False, "enabled": None, "state": "unknown",
                "task": TASK, "error": _orphaned_console_error()}
    s = (out or "").strip()
    if rc != 0 or not s:
        return {"ok": False, "enabled": None, "state": "unknown",
                "task": TASK, "error": err or "could not read the task"}
    if s.upper() == "MISSING":
        return {"ok": False, "enabled": None, "state": "missing", "task": TASK,
                "error": "the scheduled task does not exist on this PC"}
    # Ready / Running mean armed; Disabled means parked.
    return {"ok": True, "enabled": (s.lower() != "disabled"), "state": s, "task": TASK}


def state(max_age_sec=_DEFAULT_MAX_AGE_SEC):
    """{'ok', 'enabled', 'state', 'task'} — never raises.

    `enabled` is None when the task cannot be read at all, so the UI can show "unknown"
    rather than defaulting to a confident OFF (which would invite someone to "turn it on"
    and be silently ignored).

    Cached for `max_age_sec` (default 1800s / 30min): the task's state only changes when
    someone presses the button, so the runner's every-5-minute bridge publish (which calls
    this with no argument) should not spawn a fresh powershell every cycle. Pass
    `max_age_sec=0` to force a fresh read (set_enabled() and the explicit UI-button command
    path both do this). A served-from-cache response carries `cached: True` so callers can
    tell.

    A 0xC0000142 (orphaned-console) failure is cached separately for the same window, so
    the runner log prints one warning per half hour instead of one per publish cycle.
    """
    now = time.time()
    if max_age_sec > 0:
        if _FAIL_CACHE["state"] is not None and (now - _FAIL_CACHE["ts"]) < max_age_sec:
            st = dict(_FAIL_CACHE["state"])
            st["cached"] = True
            return st
        if _CACHE["state"] is not None and (now - _CACHE["ts"]) < max_age_sec:
            st = dict(_CACHE["state"])
            st["cached"] = True
            return st

    st = _read_state()
    if st.get("error") == _orphaned_console_error():
        already_warned = (_FAIL_CACHE["state"] is not None
                          and (now - _FAIL_CACHE["ts"]) < _DEFAULT_MAX_AGE_SEC)
        _FAIL_CACHE["ts"] = now
        _FAIL_CACHE["state"] = st
        if not already_warned:
            print("[nt-bridge] WARNING: %s" % st["error"], flush=True)
    else:
        _FAIL_CACHE["ts"] = 0.0
        _FAIL_CACHE["state"] = None
        _CACHE["ts"] = now
        _CACHE["state"] = st
    return dict(st)


def set_enabled(enable):
    """Arm or park the watchdog. Returns the state dict AFTER the change.

    Verifies by re-reading rather than trusting the exit code: PowerShell's scheduled-task
    cmdlets can report success on a no-op, and a button that says "off" while the task is
    still firing is worse than one that errors. Always bypasses the cache (a change just
    happened, the cache would be reading stale data by definition).
    """
    verb = "Enable-ScheduledTask" if enable else "Disable-ScheduledTask"
    out, err, rc = _run("%s -TaskName '%s' | Out-Null; 'done'" % (verb, TASK), timeout=45)
    st = state(max_age_sec=0)
    st["requested"] = bool(enable)
    if st.get("enabled") is not None and st["enabled"] != bool(enable):
        st["ok"] = False
        st["error"] = ("the task is still %s after %s%s"
                       % (st["state"], verb, (" -- " + err) if err else ""))
    elif rc != 0 and err:
        st["warning"] = err
    return st


if __name__ == "__main__":
    import json
    import sys
    a = (sys.argv[1].lower() if len(sys.argv) > 1 else "status")
    if a in ("on", "off"):
        print(json.dumps(set_enabled(a == "on"), indent=1))
    else:
        print(json.dumps(state(max_age_sec=0), indent=1))
