"""PC LOAD (board item 12, owner approved 2026-11-18 via MANAGER): how busy the PC is, on screen.

WHY THIS EXISTS. The owner works on the same machine the fleet runs on. When a validate
tier, several ships and the builders all run at once the box slows to a crawl, and the only
way to find out was to open Task Manager or ask a chat to run tools/queue_truth.py. On
2026-11-14 six ships plus a workflow ran the PC out of RAM and MANAGER had to kill
everything. A number on screen turns that into a glance.

ALWAYS ON (owner's pick over trading-hours only). One small document per publish,
users/{uid}/meta/pc_load, written by the PRIMARY runner on a throttle and read by the top
bar - the same pattern as meta/nt_sync and meta/data_health, so it is quota-cheap.

Everything here is exception-proof and psutil-optional: a load meter must never be able to
take down the runner, and a box without psutil simply shows nothing rather than a zero
(a zero would read as "idle", which is the opposite of unknown).
"""
import os
import time

try:
    import psutil as _ps
except Exception:                                    # pragma: no cover - box without psutil
    _ps = None

# One sample costs this much wall clock. cpu_percent needs a non-zero interval or it
# returns the average since the process started, which on a long-lived runner is a
# meaningless flat line.
SAMPLE_SEC = 0.4

# Published no more often than this. The top bar is a glance, not a monitor.
PUBLISH_SEC = 60.0

# QUIET UNLESS SOMETHING MOVED (MANAGER 2026-11-19, after the 11-18 quota night). A write a
# minute is 1,440 writes a day - about 7 per cent of the free write cap - and every one of
# them is also a READ for each open tab holding the listener. The numbers barely move while
# the box sits idle, so a publish now needs a real change, or this much time to have passed.
IDLE_PUBLISH_SEC = 300.0
MOVE_PCT = 5.0        # cpu or memory moved at least this many points
MOVE_RUNNERS = True   # the runner count changed at all


def check(sample_sec=SAMPLE_SEC):
    """A small dict: cpu %, memory %, free GB, how many runners are up. Never raises."""
    rep = {"checked_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
           "host": os.environ.get("COMPUTERNAME") or "", "ok": False}
    if _ps is None:
        rep["note"] = "psutil not installed on this box"
        return rep
    try:
        rep["cpu_pct"] = round(float(_ps.cpu_percent(interval=sample_sec)), 1)
        vm = _ps.virtual_memory()
        rep["mem_pct"] = round(float(vm.percent), 1)
        rep["free_gb"] = round(vm.available / (1024.0 ** 3), 1)
        rep["total_gb"] = round(vm.total / (1024.0 ** 3), 1)
        rep["runners"] = _runners()
        rep["ok"] = True
    except Exception as e:
        rep["note"] = "%s: %s" % (type(e).__name__, e)
    return rep


def _runners():
    """How many api.runner processes are up on this box. 0 is a real answer; None is not
    knowing, and the chip must be able to tell those apart.

    The name check is not decoration. Each worker is launched through a `cmd /c "set
    EDGELOG_WORKER=N && ... python -m api.runner ..."` wrapper, so the cmd.exe shell also
    carries 'api.runner' in its command line - and so does any process inspecting them,
    this module's own caller included. Matching on the text alone counted 9 runners on a
    box running 5 (seen while building this).

    So the test is on the ARGUMENT LIST, not the joined string: a python process whose argv
    says `-m api.runner` as two adjacent arguments. `python -c "...-m api.runner..."` carries
    the same characters inside ONE argument and is not a runner - that is what this module's
    own probe looked like."""
    try:
        n = 0
        for p in _ps.process_iter(["name", "cmdline"]):
            try:
                if not str(p.info.get("name") or "").lower().startswith("python"):
                    continue
                argv = [str(x) for x in (p.info.get("cmdline") or [])]
                if any(argv[i] == "-m" and argv[i + 1] == "api.runner"
                       for i in range(len(argv) - 1)):
                    n += 1
            except Exception:
                continue
        return n
    except Exception:
        return None


def moved(rep, last):
    """Is this reading worth a write yet? True on a real change, on the idle timer, and
    whenever we cannot tell - a first reading, a reading that failed, a state flip. It never
    guesses that nothing happened."""
    if not last or not isinstance(last, dict):
        return True
    if bool(rep.get("ok")) != bool(last.get("ok")):
        return True
    if not rep.get("ok"):
        return (rep.get("_at", 0) - last.get("_at", 0)) >= IDLE_PUBLISH_SEC
    for k in ("cpu_pct", "mem_pct"):
        try:
            if abs(float(rep.get(k)) - float(last.get(k))) >= MOVE_PCT:
                return True
        except Exception:
            return True
    if MOVE_RUNNERS and rep.get("runners") != last.get("runners"):
        return True
    return (rep.get("_at", 0) - last.get("_at", 0)) >= IDLE_PUBLISH_SEC


def publish(db, uid, log=print, sample_sec=SAMPLE_SEC, last=None):
    """Write users/{uid}/meta/pc_load. Returns the report, or None if nothing was written.

    `last` is the report this function returned the time before. Pass it and a reading that
    has not moved is SKIPPED: the chip keeps showing the one already in Firestore, and its
    own staleness mark only appears after 10 minutes, well past the idle timer. A skipped
    publish returns None, so a caller must keep the LAST RETURNED report, not the last call."""
    rep = check(sample_sec=sample_sec)
    rep["_at"] = time.time()
    if not moved(rep, last):
        return None
    try:
        # _at is this module's own bookkeeping for the throttle - it never goes to the page.
        body = {k: v for k, v in rep.items() if k != "_at"}
        db.collection("users").document(uid).collection("meta").document("pc_load").set(body)
    except Exception as e:
        log("pc_load: publish failed: %s: %s" % (type(e).__name__, e))
        return None
    return rep


if __name__ == "__main__":
    r = check()
    if r.get("ok"):
        print("cpu %s%%  mem %s%% (%s of %s GB free)  runners %s" % (
            r["cpu_pct"], r["mem_pct"], r["free_gb"], r["total_gb"], r["runners"]))
    else:
        print("unavailable:", r.get("note"))
