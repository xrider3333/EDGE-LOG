r"""NT NIGHT MODE - close NinjaTrader after the end-of-day checks and keep it closed until the morning.

Owner 2026-10-07: "wheres the switch to turn off the nt8 trader. i turn it off at night so it doesnt
pop up. make it so where it does its final checks and then stops automatically after everything is
backfilled after market closes and stops auto starting".

OVERNIGHT TRADING CAVEAT (also the first line of every run in C:\EdgeLog\nt_night_mode.log): with night
mode on, ENGU-Q's NinjaTrader paper leg does NOT trade the evening / overnight session - it already did
not while the PC slept - and the engine paper record (api/paper.py) still tracks it. A paper position
that is open at the close keeps its GTC stop at the broker, but nothing trails it until the morning.

Every time and choice is a named constant at the top of api/nt_night_mode.py (the one config).

COMMANDS
  python tools/nt_night.py eod  [--dry-run] [--force]
        the scheduled run (task "EdgeLog NT night mode", 13:15 and 14:15 Arizona on weekdays). Acts once
        per trading day, from EOD_START_ET (16:15 New York); --force skips those gates (not the safety rules).
  python tools/nt_night.py off  [--dry-run]    desktop switch "NinjaTrader OFF tonight": the same
        sequence right now (one 10s repair pass, no 45-minute wait), then night mode to the next morning.
  python tools/nt_night.py on   [--dry-run]    desktop switch "NinjaTrader ON now": end night mode and
        start the watchdog pass that brings NinjaTrader up (login, Simulation, strategies) exactly as
        every morning.
  python tools/nt_night.py status [--json]     what is set, until when, the last end-of-day result
  python tools/nt_night.py skip                keep NinjaTrader on at the next automatic end of day
                                               (writes C:\EdgeLog\nt_night_mode.SKIP; used once)

THE END-OF-DAY SEQUENCE, in order, each step logged:
  1. backup   today's NinjaTrader snapshot (api/nt_backup.run_nightly - the same call the 14:05 Arizona
              sweep makes; idempotent, and safe while NinjaTrader runs: sqlite backup API).
  2. 10s      tools/repair_10s_from_replay.py (the code MaybeRepair in nt_recover.ps1 runs), then count
              today's 09:30-16:00 New York 10-second bars (api/capture_health). Not complete -> repair and
              count again every BACKFILL_RETRY_MIN, give up after BACKFILL_GIVE_UP_MIN and SAY so. A gap
              never blocks the close (order-flow gaps are api/delta_alarm.py's to push, not this tool's).
  3. fills    there is no Position History reconcile scheduled after the close (that one is done by hand
              from the broker statement). What closing NinjaTrader CAN lose is a fill the add-on has not
              written yet, so every execution NinjaTrader reports for the session must be in
              C:\EdgeLog\fills.csv (wait up to FILLS_WAIT_MIN for the add-on's 60-second sweep; log any miss).
  4. safety + close (C:\EdgeLog\nt_eod_safe.ps1 is the check, and the one that stops strategies):
       REAL account 1810769 shows a position or a working order -> NinjaTrader is NOT closed tonight,
           push "NinjaTrader: left on" (the owner may be managing it by hand). Nothing else happens.
       a paper position WITHOUT a working stop for it -> NOT closed, push "CHECK NOW" (closing would
           leave it naked).
       a paper position WITH its stop -> night mode, then FORCE-close NinjaTrader. Nothing is disabled
           (disabling a strategy cancels its orders, which would strip the stop). The GTC stop stays at
           the broker; the trail stops until the morning, when nt_recover re-adopts ENGU-Q's own trade.
           Push "NinjaTrader: night mode" (the trade keeps its stop, loses its trail).
       flat -> night mode, wait for a quiet second (QUIET_SECONDS), nt_eod_safe.ps1 stops the strategies
           (it only does so when it reads flat itself), re-check flat, then a CLEAN exit (bridge
           /shutdown, saves the workspace; forced after CLEAN_EXIT_WAIT_S).
       NinjaTrader not running -> night mode. Running but not answering for BRIDGE_WAIT_MIN -> hung:
           night mode, force-close (a kill never disables anything).
     Night mode is written BEFORE anything is stopped, and a watchdog pass already running is allowed
     to finish first, so the watchdog can never re-enable a strategy that is being stopped or relaunch
     NinjaTrader mid-close. If a position turns up after the strategies were stopped, night mode is
     cleared at once (the watchdog's next pass re-adopts ENGU-Q's own trade) and a CHECK NOW goes out.
  NEVER: flattens anything, touches the real account, types a credential, disables a strategy while a
  position is open, or closes NinjaTrader cleanly while it holds a position.

THE NIGHT WINDOW. C:\EdgeLog\nt_night_mode.json {"active": {"since", "until", ...}}: nt_recover.ps1 does
nothing until `until` (MORNING_START_LOCAL, 05:45 Arizona, on the next trading day - a Friday close
runs to Monday, a holiday is skipped); the first watchdog pass after that starts NinjaTrader as always,
and the 09:15 / 09:25 New York readiness check still catches a failed start. See api/nt_night_mode.py
for every alerter that treats the window as expected.

PHONE PUSHES come only from the automatic run (the switches answer on screen; PUSH_FROM_SWITCH). A normal
flat night pushes nothing. The desktop switch reads its answer from C:\EdgeLog\nt_night_mode_last.txt.

Exit: 0 = handled (night mode on, or NinjaTrader deliberately left on and reported); 2 = crashed.
"""
import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import nt_night_mode as nm  # noqa: E402

BRIDGE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
EOD_SAFE_PS1 = os.path.join(nm.EL, "nt_eod_safe.ps1")
RECOVER_VBS = os.path.join(nm.EL, "nt_recover_hidden.vbs")
RECOVER_TASK = "EdgeLog NT recover watchdog"
FILLS_CSV = os.path.join(nm.EL, "fills.csv")
BACKUP_ROOT = os.path.join(nm.EL, "_ntbackup")
LOCK_PATH = os.path.join(nm.EL, "state", "nt_night.lock")
AREA = "NinjaTrader"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_LOCK_FD = None


# ---------------------------------------------------------------------------------------------- plumbing
# Every function in this block is a test seam (monkeypatched in tests/test_nt_night.py).
def _now():
    return nm.now_local()


def _mono():
    return time.monotonic()


def _sleep(s):
    time.sleep(s)


def log(msg):
    line = "%s  %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)          # a no-op under pythonw (no console) - the file below is the record
    try:
        os.makedirs(os.path.dirname(nm.LOG_PATH), exist_ok=True)
        with open(nm.LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def bridge_get(path, timeout=8):
    """GET -> parsed JSON, or None on any failure (one quick retry: the bridge is single threaded)."""
    import urllib.request
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(BRIDGE + path, method="GET"), timeout=timeout) as r:
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except Exception:
            if attempt == 0:
                time.sleep(1.0)
    return None


def bridge_post(path, timeout=8):
    import urllib.request
    try:
        req = urllib.request.Request(BRIDGE + path, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _run(cmd, timeout=300, cwd=None):
    """-> (returncode, output lines). Never opens a console window; never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           creationflags=_NO_WINDOW)
        out = (r.stdout or "") + (("\n" + r.stderr) if (r.stderr or "").strip() else "")
        return r.returncode, [ln.rstrip() for ln in out.splitlines() if ln.strip()]
    except Exception as e:
        return -1, ["%s: %s" % (type(e).__name__, e)]


def _ps(command, timeout=60):
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-Command", command], timeout=timeout)


def _py():
    """python.exe next to the running interpreter (pythonw children cannot print to a pipe reliably)."""
    exe = sys.executable or "python"
    base = os.path.basename(exe)
    if base.lower().startswith("pythonw"):
        cand = os.path.join(os.path.dirname(exe), "python" + base[len("pythonw"):])
        if os.path.exists(cand):
            return cand
    return exe


def nt_pids():
    rc, lines = _run(["tasklist", "/FI", "IMAGENAME eq NinjaTrader.exe", "/FO", "CSV", "/NH"], timeout=60)
    pids = []
    for ln in lines:
        parts = [p.strip('"') for p in ln.split('","')]
        if len(parts) > 1 and parts[0].lower().strip('"') == "ninjatrader.exe":
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def kill_nt():
    """Force-close NinjaTrader (TerminateProcess). A kill never runs a clean disable, so it never
    cancels an order - the GTC stop stays at the broker."""
    _ps("Stop-Process -Name NinjaTrader -Force -ErrorAction SilentlyContinue")


def recover_running():
    """True while a watchdog pass (powershell running nt_recover.ps1) is in flight. $PID is excluded:
    this very query's own command line names nt_recover.ps1 too."""
    rc, lines = _ps("@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'powershell.exe' -and "
                    "$_.ProcessId -ne $PID -and $_.CommandLine -like '*nt_recover.ps1*' }).Count")
    try:
        return int(lines[-1]) > 0
    except Exception:
        return False


def run_eod_safe(whatif):
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", EOD_SAFE_PS1]
    if whatif:
        cmd.append("-WhatIf")
    if not os.path.exists(EOD_SAFE_PS1):
        return -2, ["%s is missing" % EOD_SAFE_PS1]
    return _run(cmd, timeout=300)


def run_repair(dry):
    cmd = [_py(), "-u", os.path.join(ROOT, "tools", "repair_10s_from_replay.py")]
    if dry:
        cmd.append("--dry-run")
    return _run(cmd, timeout=900, cwd=ROOT)


def capture(inst, day):
    from api import capture_health
    return capture_health.one_instrument(capture_health.default_path(inst), day)


def backup_done(day):
    return os.path.isdir(os.path.join(BACKUP_ROOT, day.isoformat()))


def run_backup():
    from api import nt_backup
    return nt_backup.run_nightly()


def fills_ids():
    try:
        with open(FILLS_CSV, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
            return {(row[0] or "").strip() for row in csv.reader(fh) if row}
    except Exception:
        return set()


def push(note):
    try:
        from tools.nt_readiness import _load_ntfy_env
        _load_ntfy_env()
        from api import ntfy_push
        return bool(ntfy_push.send(note, log=lambda t: log("[ntfy] " + t)))
    except Exception as e:
        log("push failed: %s: %s" % (type(e).__name__, e))
        return False


def start_recover():
    """Start the watchdog task now (it brings NinjaTrader up exactly as every morning). Falls back to
    the task's own hidden launcher when the task is missing or parked."""
    rc, lines = _ps("Start-ScheduledTask -TaskName '%s' -ErrorAction Stop; 'started'" % RECOVER_TASK)
    if rc == 0 and lines and lines[-1].strip() == "started":
        return "started the watchdog task now"
    try:
        subprocess.Popen(["wscript.exe", RECOVER_VBS], close_fds=True,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        return "watchdog task not startable (%s) - ran %s directly" % ((lines or ["?"])[-1][:80], RECOVER_VBS)
    except Exception as e:
        return "could not start the watchdog: %s: %s" % (type(e).__name__, e)


def take_lock():
    """OS lock on byte 0 of LOCK_PATH, held for the life of this process (the kernel drops it when the
    process exits, so a killed run never wedges the next). -> True when this process holds it."""
    global _LOCK_FD
    try:
        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT)
        try:
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FD = fd
        return True
    except OSError:
        return False


def write_last(text, dry=False):
    """The one-line answer the desktop switch shows (plain ASCII: the VBS reads it as ANSI)."""
    if dry:
        log("switch message would be: " + text)
        return
    try:
        with open(nm.LAST_PATH, "w", encoding="ascii", errors="replace") as fh:
            fh.write(text)
    except Exception:
        pass


# ---------------------------------------------------------------------------------------------- words
def _plain(status, trading, problem, action, priority):
    from api import ntfy_push
    return ntfy_push.plain(AREA, status, trading, problem, action, priority=priority)


def _owner(pos, strategies):
    """'ENGU-Q' for the paper strategy trading this position's instrument, else 'a paper'."""
    from api import ntfy_push
    for s in strategies or []:
        if s.get("account") == pos.get("account") and str(s.get("instrument")) == str(pos.get("instrument")):
            return ntfy_push.strategy_word(s.get("name"))
    return None


def _pos_words(positions, strategies):
    from api import ntfy_push
    out = []
    for p in positions:
        who = _owner(p, strategies)
        out.append("%s%s %s" % ((who + "'s ") if who else "the paper ", ntfy_push.instrument_word(p.get("instrument")),
                                "trade"))
    return out


def _stops_for(pos, orders):
    side = str(pos.get("side") or "")
    want = ("sell",) if side == "Long" else ("buy", "buytocover")
    return [o for o in orders
            if o.get("account") == pos.get("account") and str(o.get("instrument")) == str(pos.get("instrument"))
            and "stop" in str(o.get("type", "")).lower() and str(o.get("action", "")).lower() in want]


def _covered_by_stop(pos, orders):
    try:
        need = int(float(pos.get("qty") or 0))
        have = sum(int(float(o.get("qty") or 0)) for o in _stops_for(pos, orders))
        return need > 0 and have >= need
    except Exception:
        return False


# ---------------------------------------------------------------------------------------------- steps
def step_backup(dry):
    day = _now().date()
    if backup_done(day):
        log("1 backup: today's NinjaTrader snapshot is already taken (%s)" % os.path.join(BACKUP_ROOT, day.isoformat()))
        return "done"
    if dry:
        log("1 backup: would take today's NinjaTrader snapshot now (api/nt_backup.run_nightly)")
        return "would"
    try:
        msg = run_backup()
        log("1 backup: " + str(msg))
        return "taken"
    except Exception as e:
        log("1 backup: FAILED %s: %s (continuing - the 14:05 sweep and the 21:00 runner pass retry)" % (type(e).__name__, e))
        return "failed"


def _judge(rep, session_over):
    ok_all, words = True, []
    for inst in ("NQ", "ES"):
        r = rep.get(inst) or {}
        rth = r.get("rth")
        if not rth:
            ok_all = False
            words.append("%s unreadable (%s)" % (inst, r.get("error") or "no data"))
            continue
        ok = rth["bars_pct"] >= nm.RTH_BARS_MIN_PCT and rth["delta_pct"] >= nm.RTH_FLOW_MIN_PCT
        ok_all = ok_all and ok
        w = "%s %s/%s bars (%.1f%%), buy/sell on %.1f%%" % (inst, format(rth["bars"], ","), format(rth["expected"], ","),
                                                            rth["bars_pct"], rth["delta_pct"])
        if rth.get("longest_gap_min"):
            w += ", longest gap %.1f min from %s New York" % (rth["longest_gap_min"], rth.get("gap_start_et"))
        words.append(w)
    return ok_all, "; ".join(words)


def step_backfill(mode, dry):
    from api import market_calendar as MC
    now_et = _now().astimezone(nm.ET)
    day = now_et.date()
    if not nm.is_trading_day(day):
        log("2 10s data: not a trading day - not checked")
        return {"status": "skip", "words": "not a trading day"}
    hh, mm = (int(x) for x in MC.session_close_et(day).split(":"))
    session_over = now_et >= now_et.replace(hour=hh, minute=mm, second=0, microsecond=0)
    give_up = nm.BACKFILL_GIVE_UP_MIN if mode == "eod" else nm.SWITCH_BACKFILL_GIVE_UP_MIN
    if dry:
        give_up = 0
    t0, n = _mono(), 0
    while True:
        n += 1
        rc, lines = run_repair(dry)
        for ln in lines[-6:]:
            log("    [repair] " + ln)
        if rc not in (0,):
            log("    [repair] exited %s" % rc)
        try:
            rep = {inst: capture(inst, day) for inst in ("NQ", "ES")}
        except Exception as e:
            rep = {"NQ": {"error": type(e).__name__}, "ES": {"error": type(e).__name__}}
        ok, words = _judge(rep, session_over)
        log("2 10s data, pass %d: %s" % (n, words))
        if ok:
            log("2 10s data: today's session is complete")
            return {"status": "complete", "words": words}
        if not session_over:
            log("2 10s data: the session is not over yet - judged as it stands, not waited on")
            return {"status": "partial", "words": words}
        waited = (_mono() - t0) / 60.0
        if waited + nm.BACKFILL_RETRY_MIN > give_up:
            log("2 10s data: GAVE UP after %d min (limit %d) - the gap stays and is logged here: %s"
                % (round(waited), give_up, words))
            return {"status": "gap", "words": words}
        log("2 10s data: not complete - repairing again in %d min (gives up after %d)" % (nm.BACKFILL_RETRY_MIN, give_up))
        _sleep(nm.BACKFILL_RETRY_MIN * 60)


def step_fills(dry):
    ex = bridge_get("/executions")
    if ex is None:
        log("3 fills: NinjaTrader is not answering - not checked")
        return {"status": "skip"}
    ids = [str(e.get("exec_id")) for e in (ex.get("executions") or []) if e.get("exec_id")]
    if not ids:
        log("3 fills: no executions this session")
        return {"status": "ok", "n": 0}
    wait_s = 0 if dry else nm.FILLS_WAIT_MIN * 60
    t0 = _mono()
    while True:
        have = fills_ids()
        missing = [i for i in ids if i not in have]
        if not missing:
            log("3 fills: all %d executions of this session are in fills.csv" % len(ids))
            return {"status": "ok", "n": len(ids)}
        if _mono() - t0 >= wait_s:
            log("3 fills: %d of %d executions are NOT in fills.csv after %d min (%s) - the add-on missed them; "
                "reconcile from the broker statement" % (len(missing), len(ids), wait_s // 60, ", ".join(missing[:5])))
            return {"status": "missing", "missing": missing}
        _sleep(30)


def _wait_quiet_second():
    lo, hi = nm.QUIET_SECONDS
    for _ in range(3):
        s = _now().second
        if lo <= s <= hi:
            return
        _sleep(((lo - s) % 60) + 0.5)


def _wait_recover(dry):
    if not recover_running():
        return
    if dry:
        log("4 a watchdog pass is running right now - a real run would wait for it to finish")
        return
    log("4 a watchdog pass is running - letting it finish before anything is stopped")
    t0 = _mono()
    while _mono() - t0 < nm.RECOVER_WAIT_MIN * 60:
        _sleep(10)
        if not recover_running():
            log("4 the watchdog pass finished")
            return
    log("4 the watchdog pass is still running after %d min - carrying on (night mode is already set, so it "
        "will not relaunch NinjaTrader)" % nm.RECOVER_WAIT_MIN)


def _wait_gone(seconds):
    t0 = _mono()
    while _mono() - t0 < seconds:
        if not nt_pids():
            return True
        _sleep(2)
    return not nt_pids()


def _read():
    """(positions, orders, strategies) from NinjaTrader, or None when any read failed."""
    pos, ords, strats = bridge_get("/positions"), bridge_get("/orders"), bridge_get("/strategies")
    if pos is None or ords is None:
        return None
    return (list(pos.get("positions") or []), list(ords.get("orders") or []),
            list((strats or {}).get("strategies") or []))


def _split(snap):
    positions, orders, strategies = snap
    real_p = [p for p in positions if str(p.get("account")) == nm.LIVE_ACCOUNT]
    real_o = [o for o in orders if str(o.get("account")) == nm.LIVE_ACCOUNT]
    paper_p = [p for p in positions if str(p.get("account")) != nm.LIVE_ACCOUNT]
    paper_o = [o for o in orders if str(o.get("account")) != nm.LIVE_ACCOUNT]
    return real_p, real_o, paper_p, paper_o


class Outcome(dict):
    """{"result", "night" (bool), "last" (switch text), "note" (push or None), "how", "position"}"""


def _left_on(result, last, note=None):
    return Outcome(result=result, night=False, last=last, note=note)


_STARTED = None          # when the running sequence began (the ON switch is honoured from then on)


def _on_pressed_since(started=None):
    """True when the owner pressed "NinjaTrader ON now" after this run started."""
    started = started or _STARTED
    t = nm.to_local((nm.read_state() or {}).get("on_switch"))
    return bool(t and started and t >= started)


def _closing_failed(e):
    """A crash after night mode was set: put things back as they were before night mode (the watchdog
    brings NinjaTrader and its strategies back up on its next pass) rather than leave a half-closed
    NinjaTrader that nothing watches."""
    try:
        st = nm.read_state()
        if isinstance(st.get("active"), dict) and st["active"].get("how") == "closing":
            nm.write_state(nm.clear(st, _now(), "crashed while closing: %s" % type(e).__name__))
            log("4 crashed while closing (%s: %s) - night mode cleared so the watchdog takes over again"
                % (type(e).__name__, e))
    except Exception:
        pass


def step_close(mode, dry, until, started=None, depth=0):
    """Decide and act. Returns an Outcome; writes night mode before anything is stopped."""
    try:
        return _step_close(mode, dry, until, started, depth)
    except Exception as e:
        if not dry:
            _closing_failed(e)
        raise


def _step_close(mode, dry, until, started, depth):
    until_w = nm.hhmm(until, _now())
    health = bridge_get("/health", timeout=4)
    if health is None:
        if not nt_pids():
            log("4 NinjaTrader is not running - nothing to close")
            if not dry:
                _save(lambda st: nm.enter(st, _now(), until, _reason(mode), mode, how="already-closed"))
            return Outcome(result="night-already-closed", night=True, how="already-closed",
                           last="NinjaTrader was not running. Night mode is on until %s." % until_w)
        log("4 NinjaTrader is running but not answering - waiting up to %d min" % nm.BRIDGE_WAIT_MIN)
        t0 = _mono()
        while health is None and _mono() - t0 < (0 if dry else nm.BRIDGE_WAIT_MIN * 60):
            _sleep(15)
            health = bridge_get("/health", timeout=4)
        if health is None:
            log("4 still not answering - it is hung: night mode, then force-close (a kill never disables "
                "anything, so a resting stop stays at the broker)")
            if dry:
                log("4 DRY RUN: would set night mode until %s and force-close NinjaTrader" % until_w)
                return Outcome(result="night-unresponsive", night=True, how="killed-unresponsive",
                               last="DRY RUN: NinjaTrader is hung - it would be force-closed, night mode until %s." % until_w)
            _save(lambda st: nm.enter(st, _now(), until, _reason(mode), mode, how="closing"))
            _wait_recover(dry)
            kill_nt()
            gone = _wait_gone(15)
            _save(lambda st: nm.update_active(st, how="killed-unresponsive", closed_at=nm.iso(_now()) if gone else None))
            log("4 force-closed a hung NinjaTrader" + ("" if gone else " - it is STILL running"))
            return Outcome(result="night-unresponsive", night=True, how="killed-unresponsive",
                           last="NinjaTrader was not responding and was force-closed. Night mode is on until %s." % until_w)

    snap = None
    for i in range(3):
        snap = _read()
        if snap is not None:
            break
        if i < 2:
            _sleep(10)
    if snap is None:
        # NinjaTrader answers but will not say what is open: the real account cannot be checked, so it stays on.
        log("4 NinjaTrader answers but its positions / orders could not be read - NinjaTrader is left ON")
        return _left_on("left-on-error",
                        "NinjaTrader left ON: its positions could not be read. See C:\\EdgeLog\\nt_night_mode.log.",
                        _plain("needs a fix", None,
                               "NinjaTrader did not report its positions at the end of the day, so it stays on tonight.",
                               "ask Claude (PAPER-NT8 chat)", nm.PRIORITY_FAILED))

    real_p, real_o, paper_p, paper_o = _split(snap)
    strategies = snap[2]

    # REAL ACCOUNT: the owner may be trading it by hand - leave NinjaTrader alone tonight.
    if real_p or real_o:
        log("4 your REAL account has %d open position(s) and %d working order(s) - NinjaTrader is NOT closed "
            "tonight" % (len(real_p), len(real_o)))
        return _left_on("left-on-real",
                        "NinjaTrader left ON: your real account has an open position or order. "
                        "Close it, then click NinjaTrader OFF tonight again.",
                        _plain("left on", None,
                               "Your real account has an open position or order, so NinjaTrader stays on tonight.",
                               "close NinjaTrader yourself when you are done, or click NinjaTrader OFF tonight",
                               nm.PRIORITY_LEFT_ON_REAL))

    # PAPER POSITION WITHOUT A STOP: closing would leave it naked.
    naked = [p for p in paper_p if not _covered_by_stop(p, paper_o)]
    if naked:
        log("4 a paper position has NO working stop for it: %s - NinjaTrader is NOT closed (it would be left "
            "unprotected)" % json.dumps(naked))
        return _left_on("left-on-no-stop",
                        "NinjaTrader left ON: a paper position has no stop order. Check it in NinjaTrader.",
                        _plain("CHECK NOW", "a paper position has no stop order",
                               "NinjaTrader stays on tonight: closing it would leave %s unprotected."
                               % _pos_words(naked, strategies)[0],
                               "open NinjaTrader and check the position and its stop",
                               nm.PRIORITY_LEFT_ON_NO_STOP))

    if _on_pressed_since(started):
        log("4 the owner pressed NinjaTrader ON during this run - NinjaTrader stays on")
        return _left_on("left-on-owner", "NinjaTrader stays ON: you pressed NinjaTrader ON while it was closing.")

    # From here NinjaTrader WILL be closed: night mode first, so no watchdog pass can re-enable a
    # strategy that is being stopped, or relaunch NinjaTrader once it is down.
    if dry:
        log("4 DRY RUN: would set night mode until %s now (before anything is stopped)" % until_w)
    else:
        _save(lambda st: nm.enter(st, _now(), until, _reason(mode), mode, how="closing"))
    _wait_recover(dry)
    if not dry and depth == 0:
        fresh = _read()
        if fresh is not None and _split(fresh)[:3] != (real_p, real_o, paper_p):
            log("4 positions changed while waiting - deciding again")
            _save(lambda st: nm.clear(st, _now(), "re-deciding"))
            return _step_close(mode, dry, until, started, depth=1)

    if not paper_p:
        return _close_flat(mode, dry, until, until_w)

    words = _pos_words(paper_p, strategies)
    rc, lines = run_eod_safe(whatif=dry)
    for ln in lines:
        log("    [eod-safe] " + ln)
    if rc == 2:
        if dry:
            log("4 DRY RUN: would force-close NinjaTrader with %s open (its stop stays at the broker)" % words[0])
            return Outcome(result="night-position", night=True, how="killed-with-position", position=words,
                           last="DRY RUN: would close NinjaTrader with %s open, night mode until %s." % (words[0], until_w))
        if _on_pressed_since(started):
            log("4 the owner pressed NinjaTrader ON during this run - NinjaTrader stays on")
            return _left_on("left-on-owner", "NinjaTrader stays ON: you pressed NinjaTrader ON while it was closing.")
        log("4 %s is open with its stop at the broker: FORCE-closing NinjaTrader (nothing disabled, so the "
            "stop stays; the trail stops until %s)" % (", ".join(words), until_w))
        kill_nt()
        gone = _wait_gone(15)
        _save(lambda st: nm.update_active(st, how="killed-with-position", flat=False, position=words,
                                          closed_at=nm.iso(_now()) if gone else None))
        if not gone:
            log("4 NinjaTrader is STILL running after the force-close")
        trade = words[0][0].upper() + words[0][1:]
        return Outcome(result="night-position", night=True, how="killed-with-position", position=words,
                       last="NinjaTrader is OFF until %s. %s stays open with its stop at the broker; nothing "
                            "trails it until then." % (until_w, trade),
                       note=_plain("night mode", "%s keeps its stop, but nothing trails it until %s" % (words[0], until_w),
                                   "NinjaTrader closed for the night with the trade open; it starts again at %s." % until_w,
                                   "nothing - the trade is picked back up at %s" % until_w,
                                   nm.PRIORITY_CLOSED_WITH_POSITION))
    if rc == 0:
        # it read flat itself (the trade closed a moment ago) and stopped the strategies - carry on flat
        log("4 the end-of-day check found the account flat after all and stopped the strategies")
        return _close_flat(mode, dry, until, until_w, already_stopped=True)
    if not dry:
        _save(lambda st: nm.clear(st, _now(), "left on"))
    log("4 the end-of-day check answered %s - NinjaTrader is left ON" % rc)
    if rc == 1:
        return _left_on("left-on-no-stop",
                        "NinjaTrader left ON: a paper position has no stop order. Check it in NinjaTrader.",
                        _plain("CHECK NOW", "a paper position has no stop order",
                               "NinjaTrader stays on tonight: closing it would leave the trade unprotected.",
                               "open NinjaTrader and check the position and its stop", nm.PRIORITY_LEFT_ON_NO_STOP))
    return _left_on("left-on-error",
                    "NinjaTrader left ON: the end-of-day safety check did not finish (code %s). "
                    "See C:\\EdgeLog\\nt_night_mode.log." % rc,
                    _plain("needs a fix", None, "The end-of-day close did not finish, so NinjaTrader stays on tonight.",
                           "ask Claude (PAPER-NT8 chat)", nm.PRIORITY_FAILED))


def _close_flat(mode, dry, until, until_w, already_stopped=False):
    if not already_stopped:
        _wait_quiet_second()
        rc, lines = run_eod_safe(whatif=dry)
        for ln in lines:
            log("    [eod-safe] " + ln)
        if rc != 0:
            if not dry:
                _save(lambda st: nm.clear(st, _now(), "left on"))
            log("4 the end-of-day check answered %s on a flat account - NinjaTrader is left ON" % rc)
            return _left_on("left-on-error",
                            "NinjaTrader left ON: the end-of-day safety check answered %s. See "
                            "C:\\EdgeLog\\nt_night_mode.log." % rc,
                            _plain("needs a fix", None, "The end-of-day close did not finish, so NinjaTrader stays on tonight.",
                                   "ask Claude (PAPER-NT8 chat)", nm.PRIORITY_FAILED))
    if dry:
        log("4 DRY RUN: account flat - would stop the strategies (above), ask NinjaTrader to close cleanly, "
            "night mode until %s" % until_w)
        return Outcome(result="night-clean", night=True, how="clean",
                       last="DRY RUN: flat - would stop the strategies and close NinjaTrader, night mode until %s." % until_w)
    after = _read()
    extra = None
    if after is not None:
        real_p, real_o, paper_p, paper_o = _split(after)
        if paper_p or real_p:
            # A trade opened in the moment the strategies were stopping. Let the watchdog take it straight
            # back (it re-adopts ENGU-Q's own saved trade), and tell the owner.
            _save(lambda st: nm.clear(st, _now(), "a position opened while stopping"))
            log("4 a POSITION appeared while the strategies were stopping: %s - night mode cleared, NinjaTrader "
                "left ON (the watchdog re-adopts ENGU-Q's own trade)" % json.dumps(paper_p + real_p))
            return _left_on("left-on-danger",
                            "NinjaTrader left ON: a trade opened while the strategies were stopping. Check it in NinjaTrader.",
                            _plain("CHECK NOW", "a paper trade opened while the strategies were being stopped",
                                   "NinjaTrader stays on; the trade may have no strategy managing it.",
                                   "open NinjaTrader and check the position and its stop", "high"))
        if paper_o:
            log("4 WARNING: %d order(s) still working on the paper account with no position after the strategies "
                "stopped: %s - they rest at the broker either way" % (len(paper_o), json.dumps(paper_o)))
            extra = _plain("needs a fix", "an order is still working on the paper account with no position",
                           "NinjaTrader closed for the night; the order rests at the broker with nothing managing it.",
                           "open NinjaTrader and cancel it if it is not wanted", nm.PRIORITY_FAILED)
        strat_up = [s.get("name") for s in after[2] if s.get("state") == "Realtime"]
        if strat_up:
            log("4 note: still Realtime after the stop: %s (closing anyway - the account is flat)" % ", ".join(strat_up))
    if _on_pressed_since():
        log("4 the owner pressed NinjaTrader ON while the strategies were stopping - NinjaTrader is not closed "
            "(the watchdog restarts the strategies)")
        return _left_on("left-on-owner", "NinjaTrader stays ON: you pressed NinjaTrader ON while it was closing.")
    log("4 flat - asking NinjaTrader to close cleanly (saves the workspace)")
    asked = bridge_post("/shutdown")
    gone = _wait_gone(nm.CLEAN_EXIT_WAIT_S if asked else 5)
    how = "clean"
    if not gone:
        log("4 NinjaTrader did not exit in %d s - force-closing it (the account is flat)" % nm.CLEAN_EXIT_WAIT_S)
        kill_nt()
        gone = _wait_gone(15)
        how = "clean-then-killed"
    _save(lambda st: nm.update_active(st, how=how, flat=True, position=[], closed_at=nm.iso(_now()) if gone else None))
    if not gone:
        log("4 NinjaTrader is STILL running after the force-close")
        return Outcome(result="night-not-closed", night=True, how=how, extra=extra,
                       last="Night mode is on until %s, but NinjaTrader would not close. Close it by hand." % until_w,
                       note=_plain("needs a fix", None, "NinjaTrader would not close at the end of the day.",
                                   "close NinjaTrader by hand", nm.PRIORITY_FAILED))
    log("4 NinjaTrader is closed")
    return Outcome(result="night-clean", night=True, how=how, extra=extra,
                   last="NinjaTrader is OFF until %s. Final checks done; strategies stopped (nothing was open)." % until_w)


def _reason(mode):
    return "end of day" if mode == "eod" else "owner switch OFF"


def _save(fn):
    st = nm.read_state()
    nm.write_state(fn(st))


# ---------------------------------------------------------------------------------------------- commands
def sequence(mode, dry=False):
    """The whole end-of-day sequence. mode 'eod' (scheduled) or 'switch' (the OFF shortcut)."""
    global _STARTED
    log(nm.CAVEAT)
    now = _now()
    _STARTED = now
    until = nm.next_morning_start(now)
    log("=== night mode %s%s: NinjaTrader to close, back at %s Arizona ==="
        % ("END OF DAY" if mode == "eod" else "OFF SWITCH", " (DRY RUN)" if dry else "", until.strftime("%a %Y-%m-%d %H:%M")))
    step_backup(dry)
    bf = step_backfill(mode, dry)
    fl = step_fills(dry)
    out = step_close(mode, dry, until, started=now)
    extra = ""
    if bf.get("status") == "gap":
        extra = " 10s data has a gap (logged)."
    elif bf.get("status") == "complete":
        extra = " 10s data complete."
    if fl.get("status") == "missing":
        extra += " %d fill(s) not recorded (logged)." % len(fl.get("missing") or [])
    out["last"] = (out.get("last") or "") + (extra if out.get("night") else "")
    out["backfill"], out["fills"] = bf, fl
    log("=== result: %s - %s" % (out["result"], out["last"]))
    return out


def _deliver(out, mode, dry):
    write_last(out.get("last") or "", dry)
    notes = [n for n in (out.get("note"), out.get("extra")) if n]
    if not notes:
        return
    if mode != "eod" and not nm.PUSH_FROM_SWITCH:
        return
    for n in notes:
        if dry:
            log("push: would send [%s] %s / %s" % (n["priority"], n["title"], n["message"].replace("\n", " / ")))
        else:
            ok = push(n)
            log("push: [%s] %s - %s" % (n["priority"], n["title"], "sent" if ok else "NOT delivered"))


def _record_eod(day, result, detail=""):
    def f(st):
        st = dict(st)
        st["eod"] = {"day": day.isoformat(), "result": result, "at": nm.iso(_now()), "detail": detail[:300]}
        return st
    _save(f)


def cmd_eod(dry=False, force=False):
    now = _now()
    now_et = now.astimezone(nm.ET)
    today = now_et.date()
    if not force:
        if not nm.ENABLED:
            log("end of day: night mode is switched OFF in api/nt_night_mode.py (ENABLED = False) - nothing done")
            return 0
        if not nm.is_trading_day(today):
            log("end of day: %s is not a trading day - nothing done" % today)
            return 0
        if (now_et.hour, now_et.minute) < tuple(nm.EOD_START_ET):
            log("end of day: too early (%s New York; runs from %02d:%02d) - nothing done"
                % (now_et.strftime("%H:%M"), nm.EOD_START_ET[0], nm.EOD_START_ET[1]))
            return 0
        st = nm.read_state()
        if (st.get("eod") or {}).get("day") == today.isoformat():
            log("end of day: already ran today (%s) - nothing done" % st["eod"].get("result"))
            return 0
        if nm.active(st, now):
            log("end of day: night mode is already on (until %s) - NinjaTrader is not touched"
                % nm.hhmm(st["active"].get("until"), now))
            if not dry:
                _record_eod(today, "already-night")
            return 0
        skip, note = nm.skip_pending(now)
        if os.path.exists(nm.SKIP_PATH):
            tag = "done" if skip else "stale"
            if skip:
                log("end of day: the owner's skip file is set (%s) - NinjaTrader stays ON tonight" % (note or "no note"))
            else:
                log("end of day: " + note)
            if not dry:
                try:
                    os.replace(nm.SKIP_PATH, "%s.%s-%s" % (nm.SKIP_PATH, tag, now.strftime("%Y%m%d-%H%M%S")))
                except OSError:
                    pass
                if skip:
                    _record_eod(today, "skipped-file", note)
            if skip:
                return 0
    out = sequence("eod", dry)
    if not dry:
        _record_eod(today, out["result"], out.get("last") or "")
    _deliver(out, "eod", dry)
    return 0


def cmd_off(dry=False):
    # Not recorded as the day's end of day: an OFF before 16:15 New York leaves night mode on, which the
    # automatic run reads ("already on"); an OFF that left NinjaTrader on must not stop the automatic
    # run from trying again later.
    out = sequence("switch", dry)
    _deliver(out, "switch", dry)
    return 0


def cmd_on(dry=False):
    now = _now()
    log("=== night mode ON SWITCH%s ===" % (" (DRY RUN)" if dry else ""))
    st = nm.read_state()
    a = nm.active(st, now)
    if a:
        log("ending night mode early (it ran until %s)" % nm.hhmm(a.get("until"), now))
    else:
        log("night mode was not on")
    if not dry:
        # on_switch also stops an end-of-day close that is running right now (it reads this stamp before
        # it sets night mode)
        _save(lambda s: dict(nm.clear(s, _now(), "owner switch ON") if nm.active(s, _now()) else s,
                             on_switch=nm.iso(_now())))
    if dry:
        log("DRY RUN: would start the NinjaTrader watchdog pass now")
    else:
        log(start_recover())
    write_last("Night mode is off. NinjaTrader is starting now - it takes 2 to 4 minutes.", dry)
    return 0


def cmd_status(as_json=False):
    st = nm.read_state()
    now = _now()
    pub = nm.public_state(st, now)
    skip, note = nm.skip_pending(now)
    info = {"now": nm.iso(now), "night_mode": pub, "active": nm.active(st, now), "last_eod": st.get("eod"),
            "skip_file": bool(skip), "skip_note": note, "next_morning_start": nm.iso(nm.next_morning_start(now)),
            "enabled": nm.ENABLED}
    if as_json:
        print(json.dumps(info, indent=1, default=str))
        return 0
    a = info["active"]
    print("night mode: %s" % (("ON until %s (%s, %s)" % (nm.hhmm(a.get("until"), now), a.get("reason"), a.get("how")))
                              if a else "off"))
    print("last end of day: %s" % json.dumps(info["last_eod"]))
    print("skip file: %s" % ("set - " + (note or "") if skip else (note or "none")))
    print("automatic end of day: %s from %02d:%02d New York on trading days; morning start %02d:%02d Arizona"
          % ("ON" if nm.ENABLED else "OFF", nm.EOD_START_ET[0], nm.EOD_START_ET[1],
             nm.MORNING_START_LOCAL[0], nm.MORNING_START_LOCAL[1]))
    return 0


def cmd_skip():
    with open(nm.SKIP_PATH, "w", encoding="utf-8") as fh:
        fh.write("keep NinjaTrader on at the next automatic end of day (set %s)\n" % nm.iso(_now()))
    log("skip file written: %s - the next automatic end of day leaves NinjaTrader on" % nm.SKIP_PATH)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="NinjaTrader night mode (see the module docstring).")
    ap.add_argument("command", choices=("eod", "off", "on", "status", "skip"))
    ap.add_argument("--dry-run", action="store_true", help="report what would happen; change nothing")
    ap.add_argument("--force", action="store_true", help="eod: skip the day/time/once-a-day gates")
    ap.add_argument("--json", action="store_true", help="status: print JSON")
    a = ap.parse_args(argv)
    if a.command == "status":
        return cmd_status(a.json)
    if a.command == "skip":
        return cmd_skip()
    if not a.dry_run and a.command in ("eod", "off") and not take_lock():
        log("another night-mode run is in progress - not starting a second one")
        if a.command == "off":
            write_last("The end-of-day close is already running; it finishes on its own (see C:\\EdgeLog\\nt_night_mode.log).")
        return 0
    try:
        if a.command == "eod":
            return cmd_eod(a.dry_run, a.force)
        if a.command == "off":
            return cmd_off(a.dry_run)
        return cmd_on(a.dry_run)
    except Exception as e:
        log("CRASHED: %s: %s" % (type(e).__name__, e))
        for ln in traceback.format_exc().splitlines():
            log("    " + ln)
        if a.command in ("off", "on"):
            write_last("Night mode %s did not finish (%s). See C:\\EdgeLog\\nt_night_mode.log." % (a.command.upper(), type(e).__name__))
        return 2


if __name__ == "__main__":
    sys.exit(main())
