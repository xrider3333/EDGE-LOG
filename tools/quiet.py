"""QUIET MODE (OWNER 10-27, MANAGER #133) - a hold flag for the owner's trading hours.

While quiet, NEW heavy work does not start: the runner claims no queued job, the master refresh
chain (auto-refresh, coarse refresh, build_adjusted_masters) is deferred until quiet ends, and
`tools/wt.py ship` waits before its heavy pre-lock tiers. Running jobs finish. Trades, paper,
gate_live, the NT bridge, heartbeats, the command channel and STOP/pause are NEVER gated.

Quiet = ANY of
  * the web button  users/{uid}/control/quiet = {on, until, auto, reason, set_by, set_at}
    with on=true and `until` (ISO UTC) not passed;
  * the local file  C:\\EdgeLog\\QUIET  (env EDGELOG_QUIET_FILE overrides) - optional JSON body
    {"until": ISO UTC} - written by `python tools/quiet.py on [--until HH:MM]`;
  * the AUTO window 06:25-09:00 MST (America/Phoenix, no DST) on a CME trading day (a holiday
    short session counts), unless the button has auto=false with set_at today (MST).

The runner writes C:\\EdgeLog\\quiet_state.json ({quiet, why, until, at}) every minute and the
status doc users/{uid}/control/quiet_status on every change and at most once a minute. Local
tools read the state file (current_state); when it is stale (runner down) they still compute
the auto window and the local file themselves.

CLI:  python tools/quiet.py status | on [--until HH:MM] | off      (local file only; never
writes Firestore)
"""
import datetime as _dt
import json
import os
import sys
import threading
import time

try:
    from zoneinfo import ZoneInfo
    MST = ZoneInfo("America/Phoenix")
except Exception:                                   # no tzdata: Phoenix has no DST anyway
    MST = _dt.timezone(_dt.timedelta(hours=-7), "MST")
UTC = _dt.timezone.utc
AUTO_START = (6, 25)
AUTO_END = (9, 0)
WHY_BUTTON = "button"
WHY_AUTO = "auto 06:25-09:00 MST"
WHY_LOCAL = "local flag"
STATE_STALE_SEC = 180.0
_HOME = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def quiet_file():
    return os.environ.get("EDGELOG_QUIET_FILE") or os.path.join(_HOME, "QUIET")


def state_file():
    return os.environ.get("EDGELOG_QUIET_STATE") or os.path.join(_HOME, "quiet_state.json")


# ── calendar ────────────────────────────────────────────────────────────────────────────────
_CAL = None


def _calendar():
    """augur_engine/session_calendar.py loaded BY PATH, so wt.py does not pay for the engine
    package's __init__ (it imports the whole engine)."""
    global _CAL
    if _CAL is None:
        try:
            import augur_engine.session_calendar as cal          # already imported in the runner
        except Exception:
            import importlib.util
            p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "augur_engine", "session_calendar.py")
            spec = importlib.util.spec_from_file_location("_quiet_session_calendar", p)
            cal = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cal)
        _CAL = cal
    return _CAL


def is_trading_day(d):
    """CME trading day on ET date `d`. A calendar that cannot load = weekday (the safe side:
    quiet on a holiday costs nothing)."""
    try:
        return bool(_calendar().is_exchange_session(d))
    except Exception:
        return d.weekday() < 5


# ── the pure rule ───────────────────────────────────────────────────────────────────────────
def _aware(now):
    if now is None:
        return _dt.datetime.now(UTC)
    return now if now.tzinfo else now.replace(tzinfo=UTC)


def _parse_ts(v):
    """ISO string / datetime / Firestore timestamp / epoch -> aware UTC datetime, or None."""
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)):
            return _dt.datetime.fromtimestamp(float(v), UTC)
        if isinstance(v, _dt.datetime):
            return v if v.tzinfo else v.replace(tzinfo=UTC)
        s = str(v).strip().replace("Z", "+00:00")
        t = _dt.datetime.fromisoformat(s)
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    except Exception:
        return None


def _iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def auto_window(now):
    """(start, end) of today's auto window as aware datetimes, or None when today (MST) is not
    a trading day. The ET date of 06:25-09:00 MST is the same calendar date."""
    m = _aware(now).astimezone(MST)
    if not is_trading_day(m.date()):
        return None
    start = m.replace(hour=AUTO_START[0], minute=AUTO_START[1], second=0, microsecond=0)
    end = m.replace(hour=AUTO_END[0], minute=AUTO_END[1], second=0, microsecond=0)
    return start, end


def is_quiet(now, button_doc, local_file_exists, local_until=None):
    """-> (quiet, why, until ISO UTC or None). Pure: `now` aware (naive = UTC), `button_doc`
    the users/{uid}/control/quiet dict or None, `local_file_exists` bool, `local_until` the
    local file's optional until."""
    now = _aware(now)
    b = button_doc or {}
    if b.get("on"):
        until = _parse_ts(b.get("until"))
        if until is None or until > now:
            return True, WHY_BUTTON, _iso(until)
    if local_file_exists:
        lu = _parse_ts(local_until)
        if lu is None or lu > now:
            return True, WHY_LOCAL, _iso(lu)
    skip_auto = False
    if b.get("auto") is False:
        sa = _parse_ts(b.get("set_at"))
        skip_auto = sa is not None and sa.astimezone(MST).date() == now.astimezone(MST).date()
    if not skip_auto:
        w = auto_window(now)
        if w and w[0] <= now.astimezone(MST) < w[1]:
            return True, WHY_AUTO, _iso(w[1])
    return False, None, None


# ── local flag + state file ─────────────────────────────────────────────────────────────────
def read_local_flag(path=None):
    """(exists, until) for the local QUIET file."""
    p = path or quiet_file()
    if not os.path.exists(p):
        return False, None
    try:
        with open(p, encoding="utf-8") as f:
            body = f.read().strip()
        return True, (json.loads(body) or {}).get("until") if body else None
    except Exception:
        return True, None


def write_state(state, path=None):
    """Atomic write of {quiet, why, until, at}. Never raises."""
    p = path or state_file()
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


_CACHE = {"t": 0.0, "val": None}
CACHE_SEC = 5.0


def current_state(now=None, path=None, use_cache=True):
    """{quiet, why, until, source} for a local tool. The runner's state file while it is fresh
    (it knows the button), always OR'd with the local file; stale or missing -> the auto window
    and the local file computed here."""
    if use_cache and now is None and _CACHE["val"] is not None \
            and time.monotonic() - _CACHE["t"] < CACHE_SEC:
        return dict(_CACHE["val"])
    nowa = _aware(now)
    exists, lu = read_local_flag()
    out = None
    try:
        with open(path or state_file(), encoding="utf-8") as f:
            st = json.load(f) or {}
        at = _parse_ts(st.get("at"))
        if at is not None and abs((nowa - at).total_seconds()) <= STATE_STALE_SEC:
            out = {"quiet": bool(st.get("quiet")), "why": st.get("why"),
                   "until": st.get("until"), "source": "runner"}
    except Exception:
        pass
    if out is None or not out["quiet"]:
        if out is not None:
            # the runner's view (incl. a button auto=false) holds, except a local file made since
            q, why, until = is_quiet(nowa, {"auto": False, "set_at": _iso(nowa)}, exists, lu)
        else:
            q, why, until = is_quiet(nowa, None, exists, lu)
        if q or out is None:
            out = {"quiet": q, "why": why, "until": until,
                   "source": "local" if out is None else "runner+local"}
    if now is None:
        _CACHE.update(t=time.monotonic(), val=dict(out))
    return out


# ── runner side ─────────────────────────────────────────────────────────────────────────────
class QuietMonitor:
    """The runner's quiet state. PRIMARY (db given): reads each uid's button doc at most every
    POLL_SEC (1 read/min/uid = 1,440/day), fail-open on a read error (keeps the last doc), writes
    the local state file every minute and the status doc on every change and at most once a
    minute. WORKER (db None): no Firestore at all - reads the primary's state file.

    `quiet()` is what a claim / refresh asks; it is cheap (cached state). `defer(name, fn)`
    parks a refresh; it runs once, from tick(), when quiet ends."""

    POLL_SEC = 60.0
    STATUS_SEC = 60.0

    def __init__(self, db=None, uids=(), log=print, clock=time.time, now_fn=None,
                 state_path=None, write_files=True):
        self.db = db
        self.uids = [u for u in (uids or []) if u]
        self.log = log
        self.clock = clock
        self.now_fn = now_fn or (lambda: _dt.datetime.fromtimestamp(self.clock(), UTC))
        self.state_path = state_path
        self.write_files = write_files and db is not None
        self.buttons = {}
        self._last_poll = None
        self._last_state_write = None
        self._last_status_write = None
        self._lock = threading.RLock()
        self.state = (False, None, None)
        self.since = None
        self.held = []
        self._held_logged = False
        self.deferred = {}                   # name -> fn
        self.running = set()                 # job ids this process runs
        self.reads = 0
        self.status_writes = 0
        self._ticked = False

    # -- reads ---------------------------------------------------------------------------------
    def _poll_buttons(self):
        for uid in self.uids:
            try:
                snap = (self.db.collection("users").document(uid)
                        .collection("control").document("quiet").get())
                self.reads += 1
                self.buttons[uid] = (snap.to_dict() or {}) if getattr(snap, "exists", True) else {}
            except Exception as e:           # FAIL OPEN: keep the last doc read
                self.log(f"[quiet] button read failed ({type(e).__name__}: {e}) - keeping the "
                         f"last value")

    def _compute(self, now):
        if self.db is None:
            st = current_state(now=now, path=self.state_path, use_cache=False)
            return st["quiet"], st["why"], st["until"]
        exists, lu = read_local_flag()
        best = (False, None, None)
        docs = list(self.buttons.values()) or [None]
        for d in docs:
            r = is_quiet(now, d, exists, lu)
            if r[0] and (not best[0] or (best[1] != WHY_BUTTON and r[1] == WHY_BUTTON)):
                best = r
        return best

    # -- the tick ------------------------------------------------------------------------------
    def tick(self):
        """Refresh the state; on a change log it, write the status doc, run the deferred work
        when quiet just ended. Safe to call every few seconds."""
        with self._lock:
            t = self.clock()
            now = self.now_fn()
            if self.db is not None and (self._last_poll is None
                                        or t - self._last_poll >= self.POLL_SEC):
                self._last_poll = t
                self._poll_buttons()
            new = self._compute(now)
            changed = (not self._ticked) or new[:2] != self.state[:2] or new[2] != self.state[2]
            was_quiet = self.state[0]
            if changed:
                self.since = _iso(now)
                if new[0]:
                    self.log(f"[quiet] QUIET ON ({new[1]}, until {new[2] or 'turned off'}) - "
                             f"no new jobs claimed, refreshes deferred; running jobs and "
                             f"trading paths untouched")
                elif self._ticked:
                    self.log("[quiet] quiet OFF - claiming resumes")
                self._held_logged = False
                if not new[0]:
                    self.held = []
            self.state = new
            self._ticked = True
            run_now = []
            if was_quiet and not new[0] and self.deferred:
                run_now = list(self.deferred.items())
                self.deferred = {}
            if self.write_files and (changed or self._last_state_write is None
                                     or t - self._last_state_write >= self.POLL_SEC):
                self._last_state_write = t
                write_state({"quiet": new[0], "why": new[1], "until": new[2], "at": _iso(now)},
                            self.state_path)
            if self.db is not None and (changed or self._last_status_write is None
                                        or t - self._last_status_write >= self.STATUS_SEC):
                self._write_status(now)
        for name, fn in run_now:
            self.log(f"[quiet] running deferred {name} now that quiet is over")
            try:
                fn()
            except Exception as e:
                self.log(f"[quiet] deferred {name} failed: {type(e).__name__}: {e}")
        return self.state

    def status_doc(self, now):
        q, why, until = self.state
        return {"quiet": q, "why": why, "until": until, "since": self.since,
                "held_jobs": list(self.held), "deferred": sorted(self.deferred),
                "running_jobs": sorted(self.running), "runner_seen_at": _iso(now)}

    def _write_status(self, now):
        self._last_status_write = self.clock()
        doc = self.status_doc(now)
        for uid in self.uids:
            try:
                (self.db.collection("users").document(uid).collection("control")
                 .document("quiet_status").set(doc))
                self.status_writes += 1
            except Exception as e:
                self.log(f"[quiet] status write failed: {type(e).__name__}: {e}")

    # -- what the runner asks ------------------------------------------------------------------
    def quiet(self):
        if not self._ticked:
            self.tick()
        return self.state[0]

    def hold(self, job_id):
        """True (and the job is recorded as held) while quiet: do not claim it."""
        if not self.quiet():
            return False
        with self._lock:
            if job_id not in self.held:
                self.held.append(job_id)
                if not self._held_logged:
                    self._held_logged = True
                    self.log(f"[quiet] holding queued job(s) ({self.state[1]}, until "
                             f"{self.state[2] or 'turned off'}): {job_id} - not claimed")
                    if self.db is not None:
                        self._write_status(self.now_fn())
        return True

    def defer(self, name, fn):
        """True (fn parked, runs once when quiet ends) while quiet; False = run it now."""
        if not self.quiet():
            return False
        with self._lock:
            first = name not in self.deferred
            self.deferred[name] = fn
        if first:
            self.log(f"[quiet] {name} deferred ({self.state[1]}) - runs once quiet ends")
        return True

    def run_thread(self, stop=None, step=15.0):
        def _loop():
            while stop is None or not stop.is_set():
                try:
                    self.tick()
                except Exception as e:
                    self.log(f"[quiet] tick error: {type(e).__name__}: {e}")
                time.sleep(step)
        th = threading.Thread(target=_loop, daemon=True, name="quiet-monitor")
        th.start()
        return th


# ── wt.py side ──────────────────────────────────────────────────────────────────────────────
def wait_while_quiet(label, log=print, sleep=time.sleep, state_fn=None, poll=60.0, env=None):
    """Block while quiet, one line per state change. EDGELOG_SHIP_IGNORE_QUIET=1 skips it.
    Returns the number of polls waited."""
    env = os.environ if env is None else env
    if str(env.get("EDGELOG_SHIP_IGNORE_QUIET", "")).strip() in ("1", "true", "yes"):
        return 0
    state_fn = state_fn or (lambda: current_state(use_cache=False))
    last = None
    waited = 0
    while True:
        try:
            st = state_fn()
        except Exception:
            return waited                  # never stop a ship over a broken quiet read
        if not st.get("quiet"):
            if waited:
                log("QUIET: over - continuing with %s" % label)
            return waited
        key = (st.get("why"), st.get("until"))
        if key != last:
            log("QUIET: waiting before %s (%s, until %s)"
                % (label, st.get("why"), st.get("until") or "turned off"))
            try:
                sys.stdout.flush()
            except Exception:
                pass
            last = key
        sleep(poll)
        waited += 1


# ── CLI ─────────────────────────────────────────────────────────────────────────────────────
def _until_from_hhmm(hhmm, now=None):
    now = _aware(now).astimezone(MST)
    h, m = (int(x) for x in hhmm.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now:
        t += _dt.timedelta(days=1)
    return _iso(t)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="EDGELOG quiet mode (local flag)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status")
    p_on = sub.add_parser("on")
    p_on.add_argument("--until", help="HH:MM MST (next occurrence)")
    sub.add_parser("off")
    a = ap.parse_args(argv)
    cmd = a.cmd or "status"
    if cmd == "on":
        body = {"until": _until_from_hhmm(a.until)} if a.until else {}
        p = quiet_file()
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(body, f)
        print("local QUIET flag ON (%s)%s" % (p, " until " + body["until"] if body else ""))
    elif cmd == "off":
        p = quiet_file()
        if os.path.exists(p):
            os.remove(p)
        print("local QUIET flag OFF (%s)" % p)
    st = current_state(use_cache=False)
    print("quiet: %s  why: %s  until: %s  (source: %s)"
          % ("YES" if st["quiet"] else "no", st["why"], st["until"], st["source"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
