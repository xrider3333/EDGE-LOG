"""Data-freshness watchdog — answers "is anything that feeds this system quietly dead?"

WHY THIS EXISTS (2026-08-13). Two silent failures ran for weeks before anyone noticed:

  * The NinjaTrader 10s capture for NQ stopped on 2026-08-11 17:35 (charts closed in NT).
    ES kept exporting fine, so nothing looked broken. tools/import_nt_ohlc.py DID detect
    it and wrote C:/EdgeLog/ohlc/_STALE.flag - to a file nobody reads.
  * The Yahoo master top-up had not run since 2026-06-30, because the runner is launched
    with --refresh-min 0. Yahoo only serves 7 days of 1m history, so by the time anyone
    looked, 07-01..08-05 was unreachable from any free source. (Recovered from our own
    10s capture - see tools/backfill_1m_from_10s.py - but that was luck, not design.)

Detection was never the problem. SURFACING was. So this module writes one status doc,
users/{uid}/meta/data_health, that the web subscribes to like meta/nt_sync, and prints a
loud line into runner.log when anything is stale.

Everything here is exception-proof: a watchdog must never take down the watch loop.
"""
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from augur_engine.paths import DB_PATH, UPLOADS

NY = "America/New_York"

# Capture files the NinjaTrader indicator writes. Stale = the chart is closed or NT is off.
NT_OHLC_DIR = os.environ.get("EDGELOG_NT_OHLC", r"C:\EdgeLog\ohlc")
NT_WATCH = ["NQ_10s.csv", "NQ_1m.csv", "NQ_1s.csv", "ES_10s.csv"]

# How old a thing may get before it is called stale, in minutes, DURING a weekday.
# The NT capture writes continuously through the overnight session, so a few hours of
# silence is already wrong. The Yahoo top-up is a batch job; a day and a half of slack
# keeps a weekend or a holiday from crying wolf.
STALE_NT_MIN = 180

# Masters are judged in TRADING DAYS behind, not hours: an hours threshold either cries
# wolf every Monday morning (last bar Friday 15:55 = 65h) or has to be loosened so far it
# would have missed the six-week gap entirely. Two weekdays of slack absorbs a holiday.
STALE_MASTER_DAYS = 2

# refresh_noadj_yahoo.py has no Yahoo interval for these, so they can never be topped up
# automatically and would sit permanently "stale". They are reported as no_auto_source
# instead — a real fact worth seeing once, not an alarm worth seeing daily.
NO_AUTO_SOURCE = ("15m", "2m")


def _now_ny():
    return pd.Timestamp.now(tz=NY)


def _weekend(ts):
    """Saturday, or Sunday before the 18:00 ET futures reopen — nothing is expected to
    move, so age checks would fire on every quiet weekend and train everyone to ignore
    this doc. That is exactly how the last two failures stayed invisible."""
    if ts.weekday() == 5:
        return True
    return ts.weekday() == 6 and ts.hour < 18


def _weekdays_between(a, b):
    """Mon-Fri days from a to b. Cheap and good enough — it does not know the CME
    holiday calendar, which is what STALE_MASTER_DAYS' slack is for."""
    d0, d1 = a.date(), b.date()
    if d1 <= d0:
        return 0
    n = 0
    cur = d0
    while cur < d1:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def _age_min(epoch_secs, now=None):
    now = now if now is not None else time.time()
    return None if not epoch_secs else max(0.0, (now - float(epoch_secs)) / 60.0)


def _nt_capture():
    """Age of each NinjaTrader capture file, by mtime."""
    out = []
    for name in NT_WATCH:
        p = os.path.join(NT_OHLC_DIR, name)
        if not os.path.exists(p):
            out.append({"name": name, "present": False, "age_min": None, "stale": True})
            continue
        age = _age_min(os.path.getmtime(p))
        out.append({"name": name, "present": True, "age_min": round(age, 1),
                    "stale": age > STALE_NT_MIN})
    return out


def _masters():
    """Age of the LAST BAR in each Yahoo-fed non-adjusted master. This deliberately reads
    the data, not the file mtime: refresh_noadj_yahoo.py rewrites the CSV on every run
    even when Yahoo returned nothing new, so mtime would report a dead feed as healthy."""
    out = []
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = pd.read_sql(
                "SELECT instrument,timeframe,source,filename FROM csv_files "
                "WHERE is_master=1 AND source LIKE 'db_noadj_%' "
                "ORDER BY instrument,timeframe", conn).to_dict("records")
        finally:
            conn.close()
    except Exception:
        return out
    for r in rows:
        p = os.path.join(UPLOADS, r["filename"])
        if not os.path.exists(p):
            out.append({**r, "present": False, "last_bar": None, "age_min": None,
                        "stale": True})
            continue
        try:
            last = pd.read_csv(p, usecols=[0]).iloc[-1, 0]
            lb = pd.Timestamp(float(last), unit="s", tz="UTC").tz_convert(NY)
            behind = _weekdays_between(lb, _now_ny())
            no_src = str(r.get("timeframe")) in NO_AUTO_SOURCE
            out.append({**r, "present": True,
                        "last_bar": lb.strftime("%Y-%m-%d %H:%M"),
                        "days_behind": behind,
                        "no_auto_source": no_src,
                        "stale": (not no_src) and behind > STALE_MASTER_DAYS})
        except Exception as e:
            out.append({**r, "present": True, "last_bar": None, "days_behind": None,
                        "stale": True, "error": f"{type(e).__name__}: {e}"})
    return out


def check():
    """Full report. Never raises."""
    now = _now_ny()
    quiet = _weekend(now)
    try:
        nt = _nt_capture()
    except Exception:
        nt = []
    try:
        masters = _masters()
    except Exception:
        masters = []
    problems = []
    if not quiet:
        for f in nt:
            if not f["present"]:
                problems.append(f"NT capture missing: {f['name']}")
            elif f["stale"]:
                problems.append(f"NT capture stale: {f['name']} ({f['age_min']:.0f} min old)")
        for m in masters:
            if m.get("stale"):
                problems.append(
                    f"master stale: {m['filename']} last bar "
                    f"{m.get('last_bar') or '?'} ({m.get('days_behind')} weekdays behind)")
    return {"checked_at": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "quiet_period": quiet,
            "ok": not problems,
            "problems": problems,
            "nt_capture": nt,
            "masters": masters}


def publish(db, uid, log=print):
    """Run check() and write users/{uid}/meta/data_health. Returns the report.

    One small doc per call, so this is quota-cheap even on a tight Spark plan (see
    docs on meta/nt_sync for the same pattern). Callers should throttle anyway."""
    rep = check()
    try:
        db.collection("users").document(uid).collection("meta").document(
            "data_health").set(rep)
    except Exception as e:
        log(f"data_health: publish failed: {type(e).__name__}: {e}")
    if rep["problems"]:
        log("DATA HEALTH: " + str(len(rep["problems"])) + " problem(s) -")
        for p in rep["problems"]:
            log("   ! " + p)
    return rep


if __name__ == "__main__":
    r = check()
    print(f"checked {r['checked_at']}  quiet={r['quiet_period']}  ok={r['ok']}")
    for p in r["problems"]:
        print("  ! " + p)
    if not r["problems"]:
        print("  all feeds fresh")
