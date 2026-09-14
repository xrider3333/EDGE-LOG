"""NinjaTrader dead-man's-switch — answers "did the watchdog itself stop watching?"

WHY THIS EXISTS (2026-08-15). api/nt_bridge_pub.py already polls the local
EdgeLogBridge AddOn every BRIDGE_SEC and republishes users/{uid}/meta/nt_bridge, and
the PAPER tab's NT BRIDGE tile already shows that doc's `up` flag live -- so "NinjaTrader
says it's closed" is already visible on the board. What is NOT covered is the case where
the whole watcher stops: the runner process crashes, the PC reboots, the machine loses
power, OneDrive/Task Scheduler fails to relaunch it. In that failure mode nt_bridge_pub
never runs again, meta/nt_bridge just stops updating, and the board goes quietly stale --
nothing pages anyone, because nothing is left to publish "something is wrong."

This module is the dead-man's switch for that: it never talks to the bridge itself (by
design -- it has to keep working even when NinjaTrader/the bridge/the whole PC is dead),
it only reads the timestamp nt_bridge_pub already wrote and asks "is this heartbeat still
ticking?" If the heartbeat goes stale AND the last roster we ever saw had a strategy in
Realtime (i.e. something was supposed to be live-trading when the lights went out), that
is the loud alarm. If the heartbeat is stale but nothing was Realtime last we looked, nothing
was at risk when it died -- worth a note, not a page. A fresh, ticking heartbeat clears any
open alert on its own; nobody has to dismiss a transient blip that self-healed.

Because meta/nt_bridge's `up:false` snapshots reset its `strategies` list to empty (see
nt_bridge_pub.snapshot()), the current bridge doc alone can't answer "was anything Realtime
last time we actually saw the roster" once the bridge has been down for one cycle. So this
module keeps its own memory of the last known Realtime roster, carried forward in the
meta/nt_alert doc it writes -- refreshed only on cycles where the bridge doc says `up: true`
(the only moments the roster is ground truth), held over on every other cycle.

Everything here is exception-proof: a watchdog must never take down the watch loop.
"""
import json
from datetime import datetime, timezone

# 3x the runner's BRIDGE_SEC (300s) poll interval -- generous enough to ride out one
# missed cycle without paging, tight enough to catch a dead process quickly.
STALE_MINUTES = 15.0


def _parse_utc(ts):
    """Parse nt_bridge_pub's 'YYYY-MM-DD HH:MM:SS' (naive, always UTC) timestamp."""
    if not ts:
        return None
    try:
        return datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


# -- 10-SECOND NQ FEED (added 2026-09-09) -----------------------------------------------
# THE BLIND SPOT THIS CLOSES. On 2026-09-09 NinjaTrader was perfectly healthy all session
# -- bridge up, all three strategies Realtime, fills.csv fresh, this heartbeat green -- and
# yet its 10-second NQ chart export was dead from 08:39:40 ET. Of that morning's 3,087
# exported bars, 3,075 were the chart's historical backfill and only 12 were live prints:
# the indicator lost its tick subscription 24 seconds after the strategies were enabled and
# never re-subscribed. NOTHING NOTICED. nt_recover.ps1 only inspects STRATEGY state, the
# bridge only answers "is NinjaTrader running", and this module only asked "is the bridge
# still publishing" -- a chart indicator that quietly stops writing is invisible to all
# three. The cost is real: with no live NQ price the NQ paper-trading board (api/paper.py,
# api/bars.py) cannot mark an open lot, so an end-of-day flatten would price the exit at
# the ENTRY price and write a fabricated round trip into the forward record. Same file also
# feeds the live ML gate bouncer (api/gate_live.py) that NinjaTrader asks before every entry.
#
# CORRECTED 2026-09-14: this paragraph used to also name "the QQQ shadow" as a casualty.
# That was true when written, but api/qqq_exec.py's signal_source default changed to
# "engine" in v73.770 -- in that mode it never opens this file at all (see that module's
# ENGINE MODE docstring), so a dead export no longer touches it. evaluate_tick_feed() below
# now checks the shadow's OWN effective config before naming it, instead of assuming
# "ninjatrader" mode -- a real page on 2026-09-14 said the QQQ shadow was refusing entries
# while its own state showed feed_stale=false and orders flowing, which only confused the
# owner ("I thought we were off NT"). See _qqq_signal_source/_tick_feed_impact_clause.
#
# WHY ONLY REGULAR HOURS. NQ trades nearly 24/5, but the harm is concentrated in the window
# the shadow book actually mirrors, and a page at 03:00 for a feed nobody is trading off
# teaches people to ignore pages. Outside 09:30-16:00 ET on a session day this reports
# "idle" and never alerts.
TICK_FEED_PATHS = (r"C:\EdgeLog\ohlc_addon\NQ_10s.csv", r"C:\EdgeLog\ohlc\NQ_10s.csv")
TICK_FEED_STALE_MINUTES = 10.0     # a live chart writes a bar every 10 seconds


def newest_tick_bar_epoch(paths=TICK_FEED_PATHS):
    """Newest bar timestamp across the 10s feed files, or None. Tail-read: these files
    reach 25+ MB and this runs on a timer. Never raises."""
    newest = None
    for path in paths:
        try:
            with open(path, "rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 4096))
                tail = fh.read().decode("utf-8", "replace")
            for line in reversed([ln for ln in tail.splitlines() if ln.strip()]):
                try:
                    ts = float(line.split(",")[0])
                except (ValueError, IndexError):
                    continue                      # header or a torn final line
                newest = ts if newest is None else max(newest, ts)
                break
        except Exception:
            continue
    return newest


def _tick_feed_impact_clause(qqq_signal_source):
    """Plain-language, VERIFIED list of what actually reads the 10s NQ export, for the
    stale/missing alert message.

    Read the code, don't assume: api/paper.py's run_shadow (_load_fresh_ticks) and
    api/bars.py's candle window (_fresh_tail) always read this file for the NQ
    paper-trading board's live price, and api/gate_live.py's decide()/_refresh_live_arrays
    (the live ML gate NinjaTrader calls before every entry, plus its nightly artifact
    refit) always reads it too -- those three are named unconditionally.

    The QQQ shadow (api/qqq_exec.py, "Webull paper trading") is DIFFERENT: it only opens
    this file when its own config's effective signal_source is "ninjatrader" (the old
    NT-mirror mode). Since v73.770 the default is "engine", which never touches this file
    (see that module's own "ENGINE MODE" docstring: "never fills.csv, never the NQ 10s
    export"). So it is named here ONLY when the caller resolved signal_source=="ninjatrader"
    -- naming it unconditionally is exactly the false alarm this function was rewritten to
    stop (2026-09-14: a page said the QQQ shadow was "refusing new entries" while its own
    published state showed feed_stale=false and orders still flowing)."""
    clause = ("This affects the NQ paper-trading board's live price and the live "
              "trade-approval check NinjaTrader uses before every order")
    if str(qqq_signal_source or "").strip().lower() == "ninjatrader":
        clause += ("; it also affects the QQQ shadow (Webull paper trading), which cannot "
                   "mark open lots and is refusing new entries")
    return clause + "."


def evaluate_tick_feed(newest_epoch, now_et, is_session_day, prior_tick=None,
                       qqq_signal_source=None):
    """Pure function: (newest bar epoch or None, ET-aware now, is this a session day,
    prior tick_feed block, the QQQ shadow's effective signal_source or None if unknown)
    -> new tick_feed block. `alerted` latches so a single outage pages once rather than
    every cycle, and clears itself when bars resume.

    `qqq_signal_source` drives whether the message mentions the QQQ shadow at all --
    see _tick_feed_impact_clause. Left at its default (None/unknown) it stays silent
    about the QQQ shadow, the same as "engine" -- the safe default, since claiming it is
    affected when it might not be is the false alarm this exists to prevent; the caller
    (publish(), via _qqq_signal_source) is the one that actually resolves it."""
    prior_tick = prior_tick or {}
    in_window = bool(is_session_day) and (9, 30) <= (now_et.hour, now_et.minute) < (16, 0)
    age_min = None
    if newest_epoch is not None:
        age_min = round(max(0.0, now_et.timestamp() - float(newest_epoch)) / 60.0, 1)

    if not in_window:
        return {"state": "idle", "age_minutes": age_min, "alerted": False,
                "message": "outside 09:30-16:00 ET -- the 10s feed is not watched here"}
    if age_min is None:
        return {"state": "missing", "age_minutes": None,
                "alerted": bool(prior_tick.get("alerted")),
                "message": ("no 10s NQ feed file could be read at all. " +
                           _tick_feed_impact_clause(qqq_signal_source))}
    if age_min > TICK_FEED_STALE_MINUTES:
        return {"state": "stale", "age_minutes": age_min,
                "alerted": bool(prior_tick.get("alerted")),
                "message": (f"10s NQ feed has not written for {age_min:.0f} min -- the "
                            f"NinjaTrader chart export has stopped. " +
                            _tick_feed_impact_clause(qqq_signal_source))}
    return {"state": "ok", "age_minutes": age_min, "alerted": False,
            "message": f"10s NQ feed live ({age_min:.1f} min old)"}


def evaluate(bridge_data, prior_alert):
    """Pure function: (meta/nt_bridge dict or None, meta/nt_alert dict or None) -> new
    meta/nt_alert dict. No I/O -- kept separate from publish() so it's trivially testable."""
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    prior_alert = prior_alert or {}
    last_realtime = list(prior_alert.get("last_realtime_strategies") or [])

    if not bridge_data:
        return {
            "severity": "warning",
            "message": "no NT bridge heartbeat has ever been recorded "
                       "(meta/nt_bridge missing) -- nt_bridge_pub may never have run",
            "last_realtime_strategies": last_realtime,
            "stale_minutes": None,
            "checked_utc": now_str,
        }

    checked_at = _parse_utc(bridge_data.get("checked_at"))
    stale_minutes = None
    if checked_at is not None:
        stale_minutes = (now - checked_at).total_seconds() / 60.0

    # Refresh the remembered roster only when the bridge itself reported up -- that is
    # the only moment its `strategies` list is ground truth (a down snapshot zeroes it).
    if bridge_data.get("up") is True:
        strategies = bridge_data.get("strategies") or []
        last_realtime = [
            s.get("name") for s in strategies
            if s.get("name") and str(s.get("state", "")).strip().lower() == "realtime"
        ]

    if stale_minutes is None:
        severity = "warning"
        message = "meta/nt_bridge has no parseable checked_at timestamp"
    elif stale_minutes <= STALE_MINUTES:
        severity = "ok"
        message = f"NT bridge heartbeat healthy ({stale_minutes:.1f}m old)"
    elif last_realtime:
        severity = "critical"
        message = (
            f"NT bridge heartbeat stale {stale_minutes:.0f}m (> {STALE_MINUTES:.0f}m "
            f"threshold) -- last known roster had {len(last_realtime)} strategy(ies) in "
            f"Realtime: {', '.join(last_realtime)}. NinjaTrader/bridge/PC may be down "
            f"while a strategy is supposed to be trading live.")
    else:
        severity = "warning"
        message = (
            f"NT bridge heartbeat stale {stale_minutes:.0f}m (> {STALE_MINUTES:.0f}m "
            f"threshold), but nothing was Realtime last we saw the roster -- lower risk, "
            f"still worth a look.")

    return {
        "severity": severity,
        "message": message,
        "last_realtime_strategies": last_realtime,
        "stale_minutes": round(stale_minutes, 1) if stale_minutes is not None else None,
        "checked_utc": now_str,
    }


def _page(msg, title):
    """Best-effort ntfy push. A watchdog must never take down the watch loop, so every
    failure here is swallowed -- the printed log line is the durable record."""
    try:
        import os
        import urllib.request
        topic = os.environ.get("NTFY_TOPIC")
        if not topic:
            print(f"[nt-heartbeat] NTFY_TOPIC unset, push skipped: {title}: {msg}")
            return
        req = urllib.request.Request(f"https://ntfy.sh/{topic}",
                                     data=msg.encode("utf-8"),
                                     headers={"Title": title, "Priority": "high"})
        urllib.request.urlopen(req, timeout=8).read()
    except Exception as e:
        print(f"[nt-heartbeat] push failed: {type(e).__name__}: {e}")


def _note_read():
    """Account this module's one Firestore .get() under runner.py's read-quota meter,
    bucket 'other' (2026-09-08 -- this call runs every BRIDGE_SEC on the runner's
    nt-bridge-watchdog thread, so it is a timer-driven read, not a one-shot boot read,
    and was invisible to the meter before this). A plain document .get() always costs
    exactly 1 read whether or not the document exists, so no max(1, n) is needed here
    -- see api/runner.py's _note_reads docstring for the general minimum-charge rule
    this is a special case of. Lazy import (not module-level) because api.runner
    imports this module, not the other way around; never raises if runner.py isn't
    importable (e.g. under a test that stubs this module out standalone)."""
    fn = _runner_note_reads()
    if fn is not None:
        try:
            fn("other", 1)
        except Exception:
            pass


def _runner_note_reads():
    """Find the LIVE runner module's _note_reads without importing api.runner afresh.
    The runner is launched as `python -m api.runner`, so its module lives in
    sys.modules as '__main__' -- a bare `from api.runner import _note_reads` here
    would load a SECOND copy of runner.py with its own _ReadMeter, and these reads
    would be counted into a meter nobody prints (caught in review 2026-09-08). So:
    look at '__main__' first, then an already-imported 'api.runner'; never import."""
    import sys
    for name in ("__main__", "api.runner"):
        m = sys.modules.get(name)
        fn = getattr(m, "_note_reads", None) if m is not None else None
        if callable(fn):
            return fn
    return None


def _qqq_signal_source():
    """Read-only peek at the QQQ shadow's EFFECTIVE signal_source (its config.json
    merged with the code default), reusing api.qqq_exec's OWN load_config() rather than
    re-implementing that merge/validation here. Returns (source_or_None, error_or_None);
    never raises.

    READ-ONLY, on purpose: api.qqq_exec.load_config() writes a fresh default config.json
    the first time it sees a missing file, and this heartbeat must never create or touch
    anything under C:\\EdgeLog (this repo's own hard rule, doubly true while the market is
    open and that adapter is live). So a missing file is answered straight from
    qqq_exec.DEFAULT_CONFIG in memory -- which load_config would report anyway -- and
    load_config() itself is only called once the file is already known to exist.

    Lazy-imports api.qqq_exec (not at module load) so this watchdog keeps working even if
    that module (or one of ITS imports, e.g. the webull SDK) is broken -- same reasoning
    as _runner_note_reads' lazy '__main__'/'api.runner' lookup above."""
    try:
        from api import qqq_exec
    except Exception as e:
        return None, f"qqq_exec unavailable ({type(e).__name__}: {e})"
    try:
        import os
        path = qqq_exec.CONFIG_PATH
        if not os.path.exists(path):
            return str(qqq_exec.DEFAULT_CONFIG.get("signal_source") or "engine"), None
        cfg = qqq_exec.load_config(path=path, log=lambda *a, **k: None)
        return cfg.get("signal_source"), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def publish(db, uid):
    """Read meta/nt_bridge + the prior meta/nt_alert, evaluate(), and write the new
    meta/nt_alert. Never raises -- same exception-proof contract as nt_bridge_pub.publish
    and nt_preflight.publish, since this shares their runner hook."""
    meta = db.collection("users").document(uid).collection("meta")
    bridge_data = None
    try:
        doc = meta.document("nt_bridge").get()
        _note_read()
        if doc.exists:
            bridge_data = doc.to_dict()
    except Exception as e:
        print(f"[nt-heartbeat] read nt_bridge failed: {type(e).__name__}: {e}")

    prior_alert = None
    try:
        doc = meta.document("nt_alert").get()
        _note_read()
        if doc.exists:
            prior_alert = doc.to_dict()
    except Exception as e:
        print(f"[nt-heartbeat] read nt_alert failed: {type(e).__name__}: {e}")

    try:
        rep = evaluate(bridge_data, prior_alert)
    except Exception as e:
        print(f"[nt-heartbeat] evaluate failed: {type(e).__name__}: {e}")
        return

    # 10s feed check rides along on the same timer (see the block above evaluate()).
    try:
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
        try:
            from api import market_calendar
            session_day = market_calendar.is_session(now_et.date())
        except Exception:
            session_day = now_et.weekday() < 5
        qqq_signal_source, qqq_err = _qqq_signal_source()
        if qqq_err:
            print(f"[nt-heartbeat] QQQ shadow signal_source check failed (message will "
                 f"stay silent on the QQQ shadow, same as 'engine'): {qqq_err}")
        tick = evaluate_tick_feed(newest_tick_bar_epoch(), now_et, session_day,
                                  (prior_alert or {}).get("tick_feed"),
                                  qqq_signal_source=qqq_signal_source)
        if tick["state"] in ("stale", "missing") and not tick["alerted"]:
            _page(f"NT 10s NQ feed stopped: {tick['message']}", "EDGELOG NT FEED")
            tick["alerted"] = True
        rep["tick_feed"] = tick
    except Exception as e:
        print(f"[nt-heartbeat] tick-feed check failed: {type(e).__name__}: {e}")

    try:
        meta.document("nt_alert").set(rep)
    except Exception as e:
        print(f"[nt-heartbeat] publish failed: {type(e).__name__}: {e}")
        return

    if rep["severity"] == "critical":
        print(f"[nt-heartbeat] CRITICAL: {rep['message']}")
    elif rep["severity"] == "warning":
        print(f"[nt-heartbeat] warning: {rep['message']}")
    else:
        print(f"[nt-heartbeat] ok ({rep['stale_minutes']}m)")
    tick = rep.get("tick_feed") or {}
    if tick.get("state") in ("stale", "missing"):
        print(f"[nt-heartbeat] TICK FEED: {tick.get('message')}")


if __name__ == "__main__":
    # Manual smoke test: fabricate a bridge doc and show what evaluate() would write.
    fake_bridge = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "up": True,
        "strategies": [{"name": "EdgeLogNOISE", "state": "Realtime"}],
    }
    print(json.dumps(evaluate(fake_bridge, None), indent=2))
