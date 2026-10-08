r"""NinjaTrader NIGHT MODE - the one config and the shared state reader (owner 2026-10-07).

Owner: "wheres the switch to turn off the nt8 trader. i turn it off at night so it doesnt pop up.
make it so where it does its final checks and then stops automatically after everything is
backfilled after market closes and stops auto starting".

WHY. C:\EdgeLog\nt_recover.ps1 runs every 3 minutes (scheduled task "EdgeLog NT recover watchdog")
and relaunches NinjaTrader whenever it is not running, so closing it at night only lasted until the
next pass. The only off switch was C:\EdgeLog\nt_recover.PAUSE, which expires after 30 minutes (it
exists for tools/nt_rollover.py). Night mode is a window with an END: from the end-of-day close until
the morning start (MORNING_START_LOCAL on the next trading day) the watchdog leaves NinjaTrader shut,
and every alerter that would complain about NinjaTrader being down, or about the overnight 10-second /
order-flow hole, reads the same window and stays quiet.

OVERNIGHT TRADING CAVEAT (written here, in tools/nt_night_mode.py and in the first line of every run's
log): with night mode on, ENGU-Q's NinjaTrader paper leg does NOT trade the evening / overnight session
(it already did not while the PC slept); the engine paper record (api/paper.py, ENGU-Q #335 on the
24-hour master) still tracks it. A paper position open at the close keeps its broker-side GTC stop but
nothing trails it until the morning start.

WHO READS WHAT
  tools/nt_night_mode.py         the end-of-day sequence (scheduled) and the two desktop switches
  C:\EdgeLog\nt_recover.ps1      reads STATE_PATH directly ("active.until" in the future = do nothing)
  tools/nt_readiness.py          active window: NinjaTrader checks are skipped, not failed; the
                                 overnight coverage is judged only from the window's end
  tools/nt8_freshness_sweep.py   capture freshness / roster quiet in the window (+ MORNING_GRACE_MIN);
                                 the no-tick repair count ignores bars inside a window
  api/delta_alarm.py             bars inside a window (+ ORDERFLOW_GRACE_MIN) are not judged
  api/nt_heartbeat.py            the 10s-feed page says "night" instead of "stale"
  api/nt_bridge_pub.py           publishes public_state() in users/{uid}/meta/nt_bridge as "night_mode"
  tools/nt_cloud_watchdog.py     (GitHub Actions) reads that field: a silent PC inside the window is
                                 expected (CLOUD_NIGHT_PUSH)
  tools/nt_rollover.py           a roll that falls inside a clean (flat) night is made offline

STATE FILE (STATE_PATH, written only by tools/nt_night_mode.py):
  {"active":  {"since", "until", "reason", "how", "by", "flat", "position"} | null,
   "history": [{"since", "until", "ended", "reason", "how"}, ...]   newest last, HISTORY_KEEP kept
   "eod":     {"day", "result", "at", "detail"}                       the last automatic run
   "pushed":  {...}}                                                   one-a-day push memory
Times are ISO 8601 with the UTC offset. An unreadable file means "no night mode": the watchdog then
keeps working instead of staying off by accident.

Stdlib only at import (the cloud watchdog imports this on GitHub's Linux runner).
"""
import datetime as dt
import json
import os

try:
    from zoneinfo import ZoneInfo
    LOCAL = ZoneInfo("America/Phoenix")             # the owner's clock: MST all year
    ET = ZoneInfo("America/New_York")
except Exception:                                    # tzdata missing (never on the PC)
    LOCAL = dt.timezone(dt.timedelta(hours=-7))
    ET = dt.timezone(dt.timedelta(hours=-4))

# =================================== OWNER SETTINGS ===================================
# Every time and choice night mode makes lives here. Change a value, save, done: the scheduled task
# and the switches read this file on every run (the cloud watchdog after the next push to main).
ENABLED = True                    # False = the automatic end-of-day never closes NinjaTrader
                                  # (the desktop switches still work)
EOD_START_ET = (16, 15)           # earliest automatic end-of-day run, New York time
                                  # (= 13:15 Arizona in summer, 14:15 in winter; the task fires at both)
MORNING_START_LOCAL = (5, 45)     # night mode ends at this Arizona time on the next trading day;
                                  # the watchdog's next pass then starts NinjaTrader as it always has
BACKFILL_GIVE_UP_MIN = 45         # end of day: keep re-running the 10s repair until today's session
                                  # is complete, but give up (and say so) after this many minutes
BACKFILL_RETRY_MIN = 5            # minutes between those repair passes
SWITCH_BACKFILL_GIVE_UP_MIN = 0   # the OFF switch does ONE repair pass and does not wait
RTH_BARS_MIN_PCT = 99.0           # "complete" = at least this share of the 09:30-16:00 New York
RTH_FLOW_MIN_PCT = 95.0           #   10-second bars exist, and this share of them carry buy/sell
FILLS_WAIT_MIN = 3                # wait up to this long for the fills add-on to record the session's
                                  # last executions in C:\EdgeLog\fills.csv (it sweeps every 60 s)
BRIDGE_WAIT_MIN = 5               # NinjaTrader running but not answering: wait this long, then force-close
RECOVER_WAIT_MIN = 6              # let a watchdog pass that is already running finish first
CLEAN_EXIT_WAIT_S = 90            # after asking NinjaTrader to close, force it after this many seconds
QUIET_SECONDS = (15, 40)          # strategies are stopped only between these seconds of a minute
                                  # (ENGU-Q acts on 1-minute bar closes, which land on :00)
MORNING_GRACE_MIN = 45            # "NinjaTrader / the PC is down" alerts stay quiet this long after the
                                  # window ends (PC wake + login). The 09:15 / 09:25 New York readiness
                                  # check does NOT use this grace: it still catches a failed start.
BAR_GRACE_MIN = 10                # coverage judges (readiness, sweep) skip the first minutes of bars after
                                  # the window
ORDERFLOW_GRACE_MIN = 45          # the order-flow alarm (api/delta_alarm.py) skips bars this long after the
                                  # window: the PC wakes and NinjaTrader back-fills that stretch with no-tick
                                  # bars, which is not a live gap (a real one is still caught after this)
SKIP_MAX_AGE_H = 36               # C:\EdgeLog\nt_night_mode.SKIP keeps NinjaTrader on for the next
                                  # automatic end of day only; a file older than this is ignored
PUSH_FROM_SWITCH = False          # the desktop switches answer with an on-screen message, not a push
CLOUD_NIGHT_PUSH = "silent"       # GitHub watchdog while the PC is silent inside the window:
                                  # "silent" = no push, "low" = one low "NinjaTrader: night mode until 05:45"
PRIORITY_CLOSED_WITH_POSITION = "default"   # "closed for the night with a paper trade open"
PRIORITY_LEFT_ON_REAL = "default"           # "left on: your real account has a position / order"
PRIORITY_LEFT_ON_NO_STOP = "high"           # "left on: a paper position has no stop"
PRIORITY_FAILED = "default"                 # "the end-of-day close did not finish"
HISTORY_KEEP = 20                 # past windows remembered (the gap checks look back 3 days)
# ======================================================================================

LIVE_ACCOUNT = "1810769"          # the owner's REAL account: never touched, never closed under
DEMO_ACCOUNT = "DEMO7240108"

EL = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
STATE_PATH = os.path.join(EL, "nt_night_mode.json")
SKIP_PATH = os.path.join(EL, "nt_night_mode.SKIP")
LOG_PATH = os.path.join(EL, "nt_night_mode.log")
LAST_PATH = os.path.join(EL, "nt_night_mode_last.txt")   # the one-line answer the desktop switch shows

CAVEAT = ("NIGHT MODE: with NinjaTrader closed, ENGU-Q's NinjaTrader paper leg does not trade the "
          "evening/overnight session (it already did not while the PC slept); the engine paper record "
          "still tracks it.")


# ---------------------------------------------------------------------------------------------- time
def now_local():
    return dt.datetime.now(LOCAL)


def to_local(when):
    """datetime / ISO text / epoch -> aware datetime on the owner's clock, or None."""
    try:
        if when is None or when == "":
            return None
        if isinstance(when, (int, float)):
            return dt.datetime.fromtimestamp(float(when), LOCAL)
        if isinstance(when, str):
            when = dt.datetime.fromisoformat(when.strip().replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=LOCAL)
        return when.astimezone(LOCAL)
    except Exception:
        return None


def iso(when):
    t = to_local(when)
    return t.isoformat(timespec="seconds") if t else None


def is_trading_day(d):
    """US equity session day (api/market_calendar: weekends and NYSE/Nasdaq holidays are not)."""
    try:
        from api import market_calendar
        return market_calendar.is_session(d)
    except Exception:
        return d.weekday() < 5


def next_morning_start(now=None):
    """The first MORNING_START_LOCAL (Arizona) on a trading day strictly after `now`. A Friday close
    -> Monday 05:45; the night before a holiday -> the morning after it."""
    now = to_local(now) or now_local()
    h, m = MORNING_START_LOCAL
    for i in range(0, 15):
        day = now.date() + dt.timedelta(days=i)
        cand = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=LOCAL)
        if cand > now and is_trading_day(day):
            return cand
    return now + dt.timedelta(days=1)


def hhmm(when, now=None):
    """'05:45', or 'Mon 05:45' when the moment is not today/tomorrow-morning on the owner's clock."""
    t = to_local(when)
    if t is None:
        return "??:??"
    n = to_local(now) or now_local()
    if t.date() == n.date() or (t.date() - n.date()).days == 1 and t.hour < 12:
        return t.strftime("%H:%M")
    return t.strftime("%a %H:%M")


# ---------------------------------------------------------------------------------------------- state
def read_state(path=None):
    try:
        with open(path or STATE_PATH, "r", encoding="utf-8-sig") as fh:
            st = json.load(fh)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def write_state(state, path=None):
    p = path or STATE_PATH
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, p)


def active(state=None, now=None):
    """The active window dict when `now` is before its `until`, else None. No grace."""
    state = read_state() if state is None else state
    a = (state or {}).get("active")
    if not isinstance(a, dict):
        return None
    until = to_local(a.get("until"))
    now = to_local(now) or now_local()
    if until is None or now >= until:
        return None
    return a


def _windows_full(state):
    """[(since, end, source dict)] of every remembered window, oldest first."""
    out = []
    rows = list((state or {}).get("history") or [])
    if isinstance((state or {}).get("active"), dict):
        rows.append(state["active"])
    for w in rows:
        if not isinstance(w, dict):
            continue
        s, u, e = to_local(w.get("since")), to_local(w.get("until")), to_local(w.get("ended"))
        end = e or u
        if s is None or end is None:
            continue
        if u is not None and e is not None:
            end = min(e, u)
        if end > s:
            out.append((s, end, w))
    return sorted(out, key=lambda x: (x[0], x[1]))


def windows(state=None):
    """[(since, end)] aware datetimes of every remembered window, oldest first. `end` is when the
    window really ended: its `ended` stamp (the ON switch ends one early) or its `until`."""
    state = read_state() if state is None else state
    return [(s, e) for s, e, _ in _windows_full(state)]


def quiet(state=None, now=None, grace_min=None):
    """The window `now` falls in, extended by `grace_min` after its end (default MORNING_GRACE_MIN):
    {"since", "end", "grace_until", "active"} or None. For the "NinjaTrader / PC is down" alerters."""
    state = read_state() if state is None else state
    now = to_local(now) or now_local()
    g = dt.timedelta(minutes=MORNING_GRACE_MIN if grace_min is None else grace_min)
    hit = None
    for s, e in windows(state):
        if s <= now < e + g:
            hit = {"since": s, "end": e, "grace_until": e + g, "active": now < e}
    return hit


def covered_fn(state=None, grace_min=None):
    """-> f(epoch) True when a bar time lies inside a window (+ `grace_min`, default BAR_GRACE_MIN).
    Built once so a judge can filter thousands of rows. Never raises; no state = always False."""
    try:
        g = 60.0 * (BAR_GRACE_MIN if grace_min is None else grace_min)
        spans = [(s.timestamp(), e.timestamp() + g) for s, e in windows(state)]
    except Exception:
        spans = []
    if not spans:
        return lambda ts: False

    def f(ts):
        try:
            t = float(ts)
        except (TypeError, ValueError):
            return False
        return any(a <= t < b for a, b in spans)
    return f


def judge_from(start_ts, now_ts, state=None, grace_min=None):
    """For a coverage check over (start_ts, now_ts]: None when `now_ts` is inside a window (nothing to
    judge), else the epoch to judge from - start_ts, or the end (+ BAR_GRACE_MIN) of the latest window
    that ended inside the span."""
    g = 60.0 * (BAR_GRACE_MIN if grace_min is None else grace_min)
    out = float(start_ts)
    for s, e in windows(state):
        a, b = s.timestamp(), e.timestamp()
        if a <= now_ts < b:
            return None                                # inside the window: nothing to judge
        if start_ts < b <= now_ts:                     # a window ended inside the span
            out = max(out, min(b + g, float(now_ts)))
    return int(out)


def public_state(state=None, now=None):
    """The small block published in users/{uid}/meta/nt_bridge as "night_mode" (and printed by
    `status`). The cloud watchdog judges by grace_until, never by `active` - the doc can be hours old."""
    state = read_state() if state is None else state
    now = to_local(now) or now_local()
    wins = _windows_full(state)
    if not wins:
        return {"active": False}
    s, e, src = wins[-1]
    return {"active": bool(s <= now < e), "since": iso(s), "until": iso(e),
            "grace_until": iso(e + dt.timedelta(minutes=MORNING_GRACE_MIN)),
            "until_hhmm": e.strftime("%H:%M"), "reason": src.get("reason"), "how": src.get("how"),
            "position_open": bool(src.get("position"))}


# ---------------------------------------------------------------------------------------------- changes
def _retire(state, a, ended):
    hist = list(state.get("history") or [])
    hist.append({"since": a.get("since"), "until": a.get("until"), "ended": iso(ended),
                 "reason": a.get("reason"), "how": a.get("how"), "position": a.get("position")})
    state["history"] = hist[-HISTORY_KEEP:]


def enter(state, now, until, reason, by, how="closing", flat=None, position=None):
    """-> new state with an active window [now, until). An earlier window is retired first."""
    st = dict(state or {})
    old = st.get("active")
    if isinstance(old, dict):
        u = to_local(old.get("until"))
        _retire(st, old, min(to_local(now), u) if u else to_local(now))
    st["active"] = {"since": iso(now), "until": iso(until), "reason": reason, "by": by, "how": how,
                    "flat": flat, "position": position}
    return st


def update_active(state, **fields):
    st = dict(state or {})
    if isinstance(st.get("active"), dict):
        st["active"] = dict(st["active"], **fields)
    return st


def clear(state, now, why="cleared"):
    """-> new state with no active window (the current one, if any, moves to history ended `now`)."""
    st = dict(state or {})
    a = st.get("active")
    if isinstance(a, dict):
        u = to_local(a.get("until"))
        n = to_local(now)
        _retire(st, dict(a, how=(a.get("how") or "") + ("; " + why if why else "")), min(n, u) if u else n)
    st["active"] = None
    return st


def skip_pending(now=None, path=None):
    """(True, note) when the owner's skip file asks to keep NinjaTrader on tonight."""
    p = path or SKIP_PATH
    try:
        if not os.path.exists(p):
            return False, ""
        age_h = ((to_local(now) or now_local()).timestamp() - os.path.getmtime(p)) / 3600.0
        if age_h > SKIP_MAX_AGE_H:
            return False, "stale skip file (%.0f h old) ignored" % age_h
        try:
            note = open(p, encoding="utf-8", errors="replace").read().strip()[:200]
        except Exception:
            note = ""
        return True, note
    except Exception:
        return False, ""
