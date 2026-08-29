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
"""
import subprocess

TASK = "EdgeLog NT recover watchdog"
_PS = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
       "-Command"]


def _run(cmd, timeout=30):
    try:
        p = subprocess.run(_PS + [cmd], capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "").strip(), (p.stderr or "").strip(), p.returncode
    except Exception as e:
        return "", "%s: %s" % (type(e).__name__, e), 1


def state():
    """{'ok', 'enabled', 'state', 'task'} — never raises.

    `enabled` is None when the task cannot be read at all, so the UI can show "unknown"
    rather than defaulting to a confident OFF (which would invite someone to "turn it on"
    and be silently ignored).
    """
    out, err, rc = _run(
        "$t = Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue; "
        "if ($t) { $t.State } else { 'MISSING' }" % TASK)
    s = (out or "").strip()
    if rc != 0 or not s:
        return {"ok": False, "enabled": None, "state": "unknown",
                "task": TASK, "error": err or "could not read the task"}
    if s.upper() == "MISSING":
        return {"ok": False, "enabled": None, "state": "missing", "task": TASK,
                "error": "the scheduled task does not exist on this PC"}
    # Ready / Running mean armed; Disabled means parked.
    return {"ok": True, "enabled": (s.lower() != "disabled"), "state": s, "task": TASK}


def set_enabled(enable):
    """Arm or park the watchdog. Returns the state dict AFTER the change.

    Verifies by re-reading rather than trusting the exit code: PowerShell's scheduled-task
    cmdlets can report success on a no-op, and a button that says "off" while the task is
    still firing is worse than one that errors.
    """
    verb = "Enable-ScheduledTask" if enable else "Disable-ScheduledTask"
    out, err, rc = _run("%s -TaskName '%s' | Out-Null; 'done'" % (verb, TASK), timeout=45)
    st = state()
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
        print(json.dumps(state(), indent=1))
