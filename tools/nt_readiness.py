r"""Premarket READINESS check for the EDGE-LOG NinjaTrader 8 paper system (demo account only).

WHY THIS EXISTS (2026-10-02). The owner turns the PC off at night on purpose and turns it on
in premarket. Every morning something different can be wrong by 09:30 ET and nobody looks at
all of it together: NinjaTrader may be up with a strategy missing, a position may be held with
no stop, the 10-second capture may have back-filled the overnight session with bars that carry
no buy/sell split (10-02: every NQ bar from 00:05 to 12:30 ET), or the ML gate may be down.
This script asks every one of those questions in one pass and sends ONE phone push naming
what failed, in plain words.

IT ONLY READS AND ALERTS. It never enables or disables a strategy, never flattens, never
restarts NinjaTrader, never types a credential. The bridge is touched with GET requests only.

CHECKS (one PASS / FAIL / SKIP line each)
  1. NinjaTrader bridge answers, and the demo account is connected.
  2. Roster: every strategy the watchdog expects (api.nt_preflight reads the $expected line of
     C:\EdgeLog\nt_recover.ps1) exists on DEMO7240108 and is Realtime; nothing runs on the live
     account.
  3. Positions: a held position is "managed" only if ENGU-Q is Realtime, its own position matches
     the account, C:\EdgeLog\enguq_state.json says inPos for the SAME instrument and size, and
     EXACTLY ONE working exit stop of that size exists. Anything else held = FAIL. A working order
     with no position behind it, or a state file claiming a trade the account does not hold, is
     a FAIL too.
  4. 10-second capture (NQ and ES): last bar within 3 minutes while CME is open; buy/sell split on
     at least 80% of traded bars over the last 30 minutes; and the same 80% over the whole
     overnight session since 18:00 ET (bars with volume where buy_vol+sell_vol > 0).
  5. Live ML gate on 127.0.0.1:8392 answers /gate/health. It is fail-open, so this is a
     WARNING-level item, but it still pushes.

WHEN IT RUNS. Weekdays that are trading sessions, 08:00-09:35 ET only (else it prints SKIPPED and
exits 0) unless --force. The PC may be off at the scheduled minute, so it is hooked in three
ways: the end of tools/premarket_ensure.py (wake, --early), and two scheduled tasks at 09:15 and
09:25 ET with "run as soon as possible after a missed start" (see the registration command in the
commit report / docs). Re-running is cheap and safe: the same failure set is pushed at most once
per 20 minutes (C:\EdgeLog\nt_readiness_state.json).

--early (used by premarket_ensure, minutes after the PC wakes; implied for any run before 09:10 ET):
NinjaTrader is probably still
starting, so START-UP class failures (bridge down, strategy not Realtime yet, capture not caught
up, gate not up) are recorded but NOT pushed. Safety failures (unmanaged position, wrong stop
count, live-account exposure) always push.

REGISTER THE SCHEDULED TASK (owner runs this once in PowerShell; this repo never creates tasks).
Arizona local is UTC-7 all year and ET is local+3 in summer, local+2 in winter, so four triggers
cover both seasons; the tool's own 08:00-09:35 ET window skips the two that do not apply:
    $a = New-ScheduledTaskAction -Execute "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe" `
         -Argument "-u tools\nt_readiness.py --repair" -WorkingDirectory "C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
    $t = foreach ($h in "06:15","06:25","07:15","07:25") {
           New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $h }
    $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
         -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName "EdgeLog NT readiness" -Action $a -Trigger $t -Settings $s `
         -Description "Premarket NinjaTrader readiness check (read only, pushes on failure)"
StartWhenAvailable = run as soon as possible after a missed start (the PC was off at the trigger).

Run:  python tools/nt_readiness.py                # in window only
      python tools/nt_readiness.py --force --dry-run --json
Exit: 0 = pass (or skipped), 1 = at least one FAIL.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

ET = ZoneInfo("America/New_York")

BRIDGE_URL = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
GATE_URL = "http://127.0.0.1:8392/gate/health"
RESULT_PATH = r"C:\EdgeLog\nt_readiness.json"
STATE_PATH = r"C:\EdgeLog\nt_readiness_state.json"
ENGUQ_STATE_PATH = r"C:\EdgeLog\enguq_state.json"
NTFY_ENV_PATH = r"C:\EdgeLog\secrets\ntfy.env"
CAPTURE_PATHS = None          # tests: {"NQ": path, "ES": path}; None = freshest real copy

DEMO_ACCOUNT = "DEMO7240108"
LIVE_ACCOUNT = "1810769"
ENGUQ_NAME = "EdgeLogENGUQ1m"
FRIENDLY = {"EdgeLogNOISE": "NOISE", "EdgeLogENGUQ1m": "ENGU-Q"}

WINDOW_START = dt.time(8, 0)
WINDOW_END = dt.time(9, 35)
PUSH_STARTUP_FROM = dt.time(9, 10)   # before this ET minute a run is treated as --early (see main)
DEDUPE_S = 20 * 60
STALE_S = 180
COVERAGE_MIN_PCT = 80.0
COVERAGE_WINDOW_S = 30 * 60
MIN_TRADED_BARS_30 = 18       # fewer than this in 30 open minutes = the feed is effectively dead
TITLE = "EDGELOG NT READINESS"


# --------------------------------------------------------------------------------------------
# clock helpers
# --------------------------------------------------------------------------------------------
def to_et(ts):
    return dt.datetime.fromtimestamp(ts, ET)


def cme_open(now_et):
    """CME equity-index futures: closed Saturday, Fri 17:00 ET to Sun 18:00 ET, and 17:00-18:00 ET
    every day. Exchange holidays are not modelled (this only gates the staleness check)."""
    wd, t = now_et.weekday(), now_et.time()
    if wd == 5:
        return False
    if wd == 6:
        return t >= dt.time(18, 0)
    if wd == 4 and t >= dt.time(17, 0):
        return False
    return not (dt.time(17, 0) <= t < dt.time(18, 0))


def overnight_start_ts(now_et):
    """Epoch of the most recent 18:00 ET at or before now (premarket: yesterday's 18:00, Sunday's
    on a Monday)."""
    anchor = now_et.replace(hour=18, minute=0, second=0, microsecond=0)
    if anchor > now_et:
        anchor -= dt.timedelta(days=1)
    return int(anchor.timestamp())


def window_verdict(now_et):
    """(run?, reason). Weekdays that are trading sessions, 08:00-09:35 ET."""
    from api import market_calendar
    if now_et.weekday() >= 5:
        return False, "weekend"
    if not market_calendar.is_session(now_et.date()):
        return False, "not a trading day (%s)" % (market_calendar.holiday_name(now_et.date()) or "closed")
    if not (WINDOW_START <= now_et.time() <= WINDOW_END):
        return False, "outside 08:00-09:35 ET (it is %s ET)" % now_et.strftime("%H:%M")
    return True, ""


# --------------------------------------------------------------------------------------------
# small I/O helpers (all monkeypatch targets in tests)
# --------------------------------------------------------------------------------------------
def _http_get_json(url, timeout=4):
    """GET -> parsed JSON, or None on any failure. One quick retry: the bridge is single threaded
    and can drop a request while NinjaTrader is busy."""
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as r:
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except Exception:
            if attempt == 0:
                time.sleep(1.0)
    return None


def _bridge(path):
    return _http_get_json(BRIDGE_URL.rstrip("/") + path)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:
        return None


def _write_json_atomic(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)


def _roster():
    from api import nt_preflight
    return nt_preflight._expected_roster()


def _capture_path(inst):
    if CAPTURE_PATHS and inst in CAPTURE_PATHS:
        return CAPTURE_PATHS[inst]
    from api import capture_health
    return capture_health.default_path(inst)


def _load_ntfy_env():
    """The scheduled task has no NTFY_TOPIC in its environment; the topic lives in the untracked
    C:\\EdgeLog\\secrets\\ntfy.env (one KEY=VALUE per line). Load it WITHOUT overriding what is
    already set, and never print it."""
    if (os.environ.get("NTFY_TOPIC") or "").strip():
        return
    try:
        with open(NTFY_ENV_PATH, "r", encoding="utf-8-sig") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                if k.strip().upper() in ("NTFY_TOPIC", "NTFY_TOKEN", "NTFY_SERVER") and v.strip():
                    os.environ.setdefault(k.strip().upper(), v.strip())
    except Exception:
        pass


# --------------------------------------------------------------------------------------------
# items
# --------------------------------------------------------------------------------------------
def item(id_, label, status, detail, words=None, level="fail", startup=False):
    """status: pass | fail | skip. `words` = the plain phrase used in the push (fail only).
    level: fail | warn (the gate is fail-open). startup: a start-up-class failure that --early
    does not push (NinjaTrader / feeds may still be coming up)."""
    return {"id": id_, "label": label, "status": status, "detail": detail,
            "words": words or detail, "level": level, "startup": startup}


def _fname(name):
    return FRIENDLY.get(name, name)


def _parse_side_qty(text):
    """'Long 1' -> ('Long', 1); 'Flat 0' -> ('Flat', 0); '' -> (None, 0)."""
    parts = str(text or "").split()
    try:
        return (parts[0] if parts else None), (int(float(parts[1])) if len(parts) > 1 else 0)
    except ValueError:
        return (parts[0] if parts else None), 0


def _norm_inst(s):
    return " ".join(str(s or "").upper().split())


def check_bridge(data):
    """Returns (item, up). `data` = dict of bridge payloads (None where a call failed)."""
    health, accts = data.get("health"), data.get("accounts")
    if health is None:
        return item("bridge", "NinjaTrader bridge", "fail",
                    "bridge 127.0.0.1:8391 did not answer - NinjaTrader is closed or the bridge add-on is dead",
                    "NinjaTrader is not responding (it is closed or its bridge is dead)", startup=True), False
    demo = next((a for a in (accts or {}).get("accounts", []) if a.get("name") == DEMO_ACCOUNT), None)
    if demo is None or not demo.get("connected"):
        return item("bridge", "NinjaTrader bridge", "fail",
                    "bridge is up but the demo account %s is not connected" % DEMO_ACCOUNT,
                    "the demo account is not connected in NinjaTrader", startup=True), True
    return item("bridge", "NinjaTrader bridge", "pass",
                "answers; demo account %s connected" % DEMO_ACCOUNT), True


def check_roster(data):
    strategies = (data.get("strategies") or {}).get("strategies", [])
    try:
        names, source = _roster()
    except Exception:
        names, source = ["EdgeLogNOISE", "EdgeLogENGUQ1m"], "built-in"
    problems, words, live = [], [], []
    by_name = {}
    for s in strategies:
        by_name.setdefault(s.get("name"), []).append(s)
        if s.get("account") == LIVE_ACCOUNT:
            live.append(s.get("name"))
    for nm in names:
        rows = by_name.get(nm) or []
        demo_rows = [r for r in rows if r.get("account") == DEMO_ACCOUNT]
        if not rows:
            problems.append("%s is missing from the Strategies list" % nm)
            words.append("%s is missing from NinjaTrader" % _fname(nm))
        elif not demo_rows:
            problems.append("%s is on account %s, not %s" % (nm, rows[0].get("account"), DEMO_ACCOUNT))
            words.append("%s is on the wrong account" % _fname(nm))
        elif demo_rows[0].get("state") != "Realtime":
            problems.append("%s state is %s, not Realtime" % (nm, demo_rows[0].get("state")))
            words.append("%s is not running live (state %s)" % (_fname(nm), demo_rows[0].get("state")))
    if live:
        problems.insert(0, "LIVE ACCOUNT %s has strategies: %s" % (LIVE_ACCOUNT, ", ".join(live)))
        words.insert(0, "a strategy is attached to the LIVE account")
    if problems:
        return item("roster", "Strategy roster", "fail", "; ".join(problems), "; ".join(words),
                    startup=not live)
    return item("roster", "Strategy roster", "pass",
                "%s all Realtime on %s (roster from %s)" % (", ".join(names), DEMO_ACCOUNT, source))


def _stops_for(orders, inst, side):
    """Working exit stops on `inst` for a position of `side` (Long exits by Sell, Short by Buy)."""
    out = []
    for o in orders:
        if o.get("account") != DEMO_ACCOUNT or _norm_inst(o.get("instrument")) != _norm_inst(inst):
            continue
        if "stop" not in str(o.get("type", "")).lower():
            continue
        act = str(o.get("action", "")).lower()
        if side == "Long" and act != "sell":
            continue
        if side == "Short" and act not in ("buy", "buytocover"):
            continue
        out.append(o)
    return out


def check_positions(data, enguq_state):
    positions = (data.get("positions") or {}).get("positions", [])
    orders = (data.get("orders") or {}).get("orders", [])
    strategies = (data.get("strategies") or {}).get("strategies", [])
    eq = next((s for s in strategies if s.get("name") == ENGUQ_NAME and s.get("account") == DEMO_ACCOUNT), None)
    problems, words, held = [], [], []

    live_pos = [p for p in positions if p.get("account") == LIVE_ACCOUNT]
    for p in live_pos:
        problems.append("LIVE account %s holds %s %s %s" % (LIVE_ACCOUNT, p.get("side"), p.get("qty"), p.get("instrument")))
        words.append("the LIVE account holds a position")

    demo_pos = [p for p in positions if p.get("account") == DEMO_ACCOUNT]
    for p in demo_pos:
        inst, side, qty = p.get("instrument"), p.get("side"), int(float(p.get("qty") or 0))
        tag = "%s %s %d" % (inst, side, qty)
        held.append(tag)
        why = None
        eq_side, eq_qty = _parse_side_qty((eq or {}).get("position"))
        if eq is None or eq.get("state") != "Realtime":
            why = ("ENGU-Q is not running live", "%s held while ENGU-Q is not Realtime" % tag)
        elif _norm_inst(eq.get("instrument")) != _norm_inst(inst):
            why = ("a position that no strategy owns", "%s is not ENGU-Q's instrument (%s)" % (tag, eq.get("instrument")))
        elif eq_side != side or eq_qty != qty:
            why = ("ENGU-Q's position does not match the account",
                   "%s held but ENGU-Q's own position reads %s %d" % (tag, eq_side, eq_qty))
        elif not enguq_state:
            why = ("ENGU-Q's saved trade file is unreadable", "%s held but enguq_state.json is unreadable" % tag)
        elif not enguq_state.get("inPos") or _norm_inst(enguq_state.get("instrument")) != _norm_inst(inst) \
                or int(float(enguq_state.get("qty") or 0)) != qty:
            why = ("ENGU-Q's saved trade does not match the account",
                   "%s held but the state file says inPos=%s %s x%s"
                   % (tag, enguq_state.get("inPos"), enguq_state.get("instrument"), enguq_state.get("qty")))
        else:
            stops = _stops_for(orders, inst, side)
            if len(stops) != 1:
                why = ("the %s position has %d exit stops instead of one" % (inst, len(stops)),
                       "%s has %d working exit stops (needs exactly 1)" % (tag, len(stops)))
            elif int(float(stops[0].get("qty") or 0)) != qty:
                why = ("the exit stop does not cover the whole %s position" % inst,
                       "%s but its stop is for %s contracts" % (tag, stops[0].get("qty")))
        if why:
            words.append(why[0])
            problems.append(why[1])

    held_insts = {_norm_inst(p.get("instrument")) for p in demo_pos}
    orphan = [o for o in orders if o.get("account") == DEMO_ACCOUNT and _norm_inst(o.get("instrument")) not in held_insts]
    for o in orphan:
        problems.append("working %s %s order on %s with no position behind it" % (o.get("action"), o.get("type"), o.get("instrument")))
        words.append("an order is sitting on %s with no position" % o.get("instrument"))
    if enguq_state and enguq_state.get("inPos") and not any(
            _norm_inst(enguq_state.get("instrument")) == h for h in held_insts):
        problems.append("state file says ENGU-Q holds %s but the account is flat there" % enguq_state.get("instrument"))
        words.append("ENGU-Q thinks it holds a trade the account does not have")

    if problems:
        return item("positions", "Positions", "fail", "; ".join(problems), "; ".join(dict.fromkeys(words)))
    if held:
        return item("positions", "Positions", "pass",
                    "managed: %s, ENGU-Q Realtime, state matches, one exit stop" % ", ".join(held))
    return item("positions", "Positions", "pass", "flat on %s, no working orders" % DEMO_ACCOUNT)


def _last_bar_ts(path):
    """Newest bar time in the file, from its last 8 KB (None if unreadable)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 8192))
            lines = fh.read().decode("utf-8", "replace").splitlines()
        for ln in reversed(lines):
            try:
                return int(float(ln.split(",", 1)[0]))
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _coverage(df):
    """(traded bars, classified bars) - a bar is traded when volume > 0, classified when
    buy_vol + sell_vol > 0."""
    import pandas as pd
    if df is None or df.empty:
        return 0, 0
    vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0) > 0
    cls = (pd.to_numeric(df["buy_vol"], errors="coerce").fillna(0)
           + pd.to_numeric(df["sell_vol"], errors="coerce").fillna(0)) > 0
    return int(vol.sum()), int((vol & cls).sum())


def check_capture(inst, now_ts):
    """Three items for one instrument: fresh, 30-minute coverage, overnight coverage."""
    from api import capture_health
    now_et = to_et(now_ts)
    path = _capture_path(inst)
    fid, cid, oid = "capture_fresh_" + inst, "capture_30m_" + inst, "capture_overnight_" + inst
    fl, cl, ol = "10s capture %s: fresh" % inst, "10s capture %s: buy/sell last 30 min" % inst, \
        "10s capture %s: buy/sell overnight" % inst
    if not os.path.exists(path):
        msg = "%s 10s file not found" % inst
        return [item(fid, fl, "fail", msg, "the %s 10-second capture file is missing" % inst, startup=True),
                item(cid, cl, "skip", "no file"), item(oid, ol, "skip", "no file")]
    try:
        start = overnight_start_ts(now_et)
        df = capture_health._read_window(path, start, now_ts + 60)
    except Exception as e:
        msg = "could not read %s 10s file: %s" % (inst, type(e).__name__)
        return [item(fid, fl, "fail", msg, "the %s 10-second capture file cannot be read" % inst, startup=True),
                item(cid, cl, "skip", "no data"), item(oid, ol, "skip", "no data")]

    items = []
    is_open = cme_open(now_et)
    last = int(df["time"].max()) if not df.empty else _last_bar_ts(path)
    stale = False
    if last is None:
        items.append(item(fid, fl, "fail", "no bars in the file", "the %s 10-second capture has no bars" % inst, startup=True))
        stale = True
    else:
        age = now_ts - last
        stamp = to_et(last).strftime("%a %H:%M:%S")
        if not is_open:
            items.append(item(fid, fl, "pass", "market closed - not checked (last bar %s ET)" % stamp))
        elif age > STALE_S:
            stale = True
            items.append(item(fid, fl, "fail", "last bar is %d min old (%s ET), limit 3 min" % (age // 60, stamp),
                              "the %s 10-second capture stopped (last bar %d minutes old)" % (inst, age // 60), startup=True))
        else:
            items.append(item(fid, fl, "pass", "last bar %d s old (%s ET)" % (max(age, 0), stamp)))

    # 30-minute coverage
    if not is_open:
        items.append(item(cid, cl, "skip", "market closed"))
    elif stale:
        items.append(item(cid, cl, "skip", "not judged: the feed is stale"))
    else:
        w = df[df["time"] > now_ts - COVERAGE_WINDOW_S]
        n, ok = _coverage(w)
        if n < MIN_TRADED_BARS_30:
            items.append(item(cid, cl, "fail", "only %d bars with volume in the last 30 min" % n,
                              "the %s 10-second capture has almost no bars in the last 30 minutes" % inst, startup=True))
        else:
            pct = 100.0 * ok / n
            if pct < COVERAGE_MIN_PCT:
                items.append(item(cid, cl, "fail", "%.0f%% of %d traded bars have buy/sell (needs %d%%)" % (pct, n, COVERAGE_MIN_PCT),
                                  "%s buy/sell volume is missing on %.0f%% of the last 30 minutes" % (inst, 100 - pct), startup=True))
            else:
                items.append(item(cid, cl, "pass", "%.0f%% of %d traded bars have buy/sell" % (pct, n)))

    # overnight coverage since 18:00 ET
    n, ok = _coverage(df)
    since = to_et(overnight_start_ts(now_et)).strftime("%a %H:%M")
    if n == 0:
        items.append(item(oid, ol, "fail", "no traded bars since %s ET" % since,
                          "there are no %s overnight 10-second bars since %s ET" % (inst, since), startup=True))
    else:
        pct = 100.0 * ok / n
        if pct < COVERAGE_MIN_PCT:
            items.append(item(oid, ol, "fail", "%.1f%% of %d traded bars since %s ET have buy/sell (needs %d%%)" % (pct, n, since, COVERAGE_MIN_PCT),
                              "%s overnight buy/sell volume is only %.0f%% filled since %s ET" % (inst, pct, since), startup=True))
        else:
            items.append(item(oid, ol, "pass", "%.1f%% of %d traded bars since %s ET have buy/sell" % (pct, n, since)))
    return items


def check_gate():
    h = _http_get_json(GATE_URL, timeout=3)
    if h is None:
        return item("gate", "Live ML gate", "fail", "127.0.0.1:8392 did not answer (fail-open: trades still pass)",
                    "the live ML gate is not answering (warning only, trades still go through)", level="warn", startup=True)
    if not h.get("ok"):
        return item("gate", "Live ML gate", "fail", "/gate/health says not ok (fail-open: trades still pass)",
                    "the live ML gate reports unhealthy (warning only, trades still go through)", level="warn", startup=True)
    return item("gate", "Live ML gate", "pass", "healthy")


# --------------------------------------------------------------------------------------------
# run + push
# --------------------------------------------------------------------------------------------
def run_checks(now_ts):
    """Every check -> list of items. Never raises: a crash in one check is itself a FAIL item."""
    items = []
    data = {}
    for key, path in (("health", "/health"), ("accounts", "/accounts"), ("strategies", "/strategies"),
                      ("positions", "/positions"), ("orders", "/orders")):
        data[key] = _bridge(path)
        if key == "health" and data[key] is None:
            break                                     # bridge down: stop hammering it
    br, up = check_bridge(data)
    items.append(br)
    if up and all(data.get(k) is not None for k in ("strategies", "positions", "orders")):
        for fn, args in ((check_roster, (data,)), (check_positions, (data, _read_json(ENGUQ_STATE_PATH)))):
            try:
                items.append(fn(*args))
            except Exception as e:
                items.append(item(fn.__name__, fn.__name__, "fail", "check crashed: %s: %s" % (type(e).__name__, e),
                                  "the %s check crashed" % fn.__name__.replace("check_", "")))
    else:
        why = "not checked: bridge unreachable" if not up else "not checked: the bridge returned no data"
        if up:
            items.append(item("bridge_data", "Bridge data", "fail", why, "NinjaTrader's bridge returned no strategy or position data", startup=True))
        items.append(item("roster", "Strategy roster", "skip", why))
        items.append(item("positions", "Positions", "skip", why))
    for inst in ("NQ", "ES"):
        try:
            items.extend(check_capture(inst, now_ts))
        except Exception as e:
            items.append(item("capture_" + inst, "10s capture " + inst, "fail",
                              "check crashed: %s: %s" % (type(e).__name__, e), "the %s capture check crashed" % inst, startup=True))
    try:
        items.append(check_gate())
    except Exception as e:
        items.append(item("gate", "Live ML gate", "fail", "check crashed: %s" % type(e).__name__,
                          "the live ML gate check crashed", level="warn", startup=True))
    return items


def build_message(failed, now_et):
    """One plain-language push body naming every failed item."""
    lines = ["NinjaTrader premarket check at %s ET found %d problem%s:" % (
        now_et.strftime("%H:%M"), len(failed), "" if len(failed) == 1 else "s")]
    lines += ["- " + f["words"][0].upper() + f["words"][1:] for f in failed]
    lines.append("Nothing was changed; this check only reads.")
    return "\n".join(lines)


def decide_push(failed, state, now_ts, early):
    """-> (push?, reason). De-dupe: the same failure set at most once per 20 minutes. --early
    drops the start-up-class failures from consideration."""
    cand = [f for f in failed if not (early and f["startup"])]
    if not cand:
        return False, ("only start-up failures during the early run" if failed else "no failures"), []
    ids = sorted(f["id"] for f in cand)
    if state.get("last_set") == ids and now_ts - float(state.get("last_push") or 0) < DEDUPE_S:
        return False, "same failure set already pushed %d min ago" % ((now_ts - state["last_push"]) // 60), cand
    return True, "", cand


def main(argv=None, now_ts=None):
    ap = argparse.ArgumentParser(description="Premarket NinjaTrader readiness check (read only).")
    ap.add_argument("--dry-run", action="store_true", help="no push, no file or state writes")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--force", action="store_true", help="run outside the weekday 08:00-09:35 ET window")
    ap.add_argument("--early", action="store_true", help="wake-time run: do not push start-up failures")
    ap.add_argument("--repair", action="store_true",
                    help="first merge the Tick Replay sidecars into the 10s files (tools/repair_10s_from_replay.py)")
    a = ap.parse_args(argv)

    now_ts = int(now_ts if now_ts is not None else time.time())
    now_et = to_et(now_ts)
    run, why = window_verdict(now_et)
    if not run and not a.force:
        print("SKIPPED: %s" % why)
        return 0

    if a.repair:
        # Bars written with no trade ticks while the PC slept get their buy/sell back from the
        # replay NinjaTrader did at its last start, BEFORE overnight coverage is judged. Never fatal.
        import subprocess
        cmd = [sys.executable, "-u", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "repair_10s_from_replay.py")]
        if a.dry_run:
            cmd.append("--dry-run")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            for ln in (r.stdout or "").splitlines():
                if ln.strip():
                    print("repair: " + ln.strip())
        except Exception as e:
            print("repair could not run: %s: %s" % (type(e).__name__, e))

    items = run_checks(now_ts)
    failed = [i for i in items if i["status"] == "fail"]
    result = {"checked_at_utc": dt.datetime.fromtimestamp(now_ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
              "checked_at_et": now_et.strftime("%Y-%m-%d %H:%M:%S"), "ok": not failed,
              "forced": bool(a.force and not run), "early": a.early or now_et.time() < PUSH_STARTUP_FROM, "items": items,
              "failed": [f["id"] for f in failed], "pushed": False}

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        for i in items:
            print("%-5s %-38s %s" % (i["status"].upper(), i["label"], i["detail"]))
        print("READY" if not failed else "NOT READY: %d problem%s" % (len(failed), "" if len(failed) == 1 else "s"))

    state = _read_json(STATE_PATH) or {}
    # Before 09:10 ET NinjaTrader and the feeds may still be starting (the wake task runs 09:05 ET, and
    # after the November clock change the 06:15 local trigger lands at 08:15 ET), so any run that early
    # holds back start-up-class failures exactly like --early. The 09:15 / 09:25 ET runs push them.
    early = a.early or now_et.time() < PUSH_STARTUP_FROM
    push, reason, cand = decide_push(failed, state, now_ts, early)
    if failed and not a.json:
        print("push: %s" % ("would send" if push and a.dry_run else "sending" if push else "not sent (%s)" % reason))
    if push and not a.dry_run:
        _load_ntfy_env()
        from api import ntfy_push
        high = any(f["level"] != "warn" for f in cand)
        ok = ntfy_push.push(build_message(cand, now_et), title=TITLE, priority="high" if high else "default",
                            log=lambda t: print("[ntfy] " + t))
        result["pushed"] = bool(ok)
        if ok:                                         # only a delivered push starts the 20-minute quiet period
            _write_json_atomic(STATE_PATH, {"last_push": now_ts, "last_set": sorted(f["id"] for f in cand)})
    if not failed and not a.dry_run and state.get("last_set"):
        _write_json_atomic(STATE_PATH, {"last_push": 0, "last_set": []})   # a clean pass re-arms the alert
    if not a.dry_run:
        try:
            _write_json_atomic(RESULT_PATH, result)
        except Exception as e:
            print("could not write %s: %s" % (RESULT_PATH, type(e).__name__))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
