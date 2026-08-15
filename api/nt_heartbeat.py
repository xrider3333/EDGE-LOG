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


def publish(db, uid):
    """Read meta/nt_bridge + the prior meta/nt_alert, evaluate(), and write the new
    meta/nt_alert. Never raises -- same exception-proof contract as nt_bridge_pub.publish
    and nt_preflight.publish, since this shares their runner hook."""
    meta = db.collection("users").document(uid).collection("meta")
    bridge_data = None
    try:
        doc = meta.document("nt_bridge").get()
        if doc.exists:
            bridge_data = doc.to_dict()
    except Exception as e:
        print(f"[nt-heartbeat] read nt_bridge failed: {type(e).__name__}: {e}")

    prior_alert = None
    try:
        doc = meta.document("nt_alert").get()
        if doc.exists:
            prior_alert = doc.to_dict()
    except Exception as e:
        print(f"[nt-heartbeat] read nt_alert failed: {type(e).__name__}: {e}")

    try:
        rep = evaluate(bridge_data, prior_alert)
    except Exception as e:
        print(f"[nt-heartbeat] evaluate failed: {type(e).__name__}: {e}")
        return

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


if __name__ == "__main__":
    # Manual smoke test: fabricate a bridge doc and show what evaluate() would write.
    fake_bridge = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "up": True,
        "strategies": [{"name": "EdgeLogNOISE", "state": "Realtime"}],
    }
    print(json.dumps(evaluate(fake_bridge, None), indent=2))
