"""Intraday drawdown alert — the mid-session ping nothing else provides.

WHY (2026-08-16). Everything else in this project reports on a DAILY cadence: the paper
reconcile and the roster preflight both run once, and the nightly backup once. The
execution reviewer pings per FILL, which tells you a trade happened but never that the
day as a whole is going badly. So the one question with real money on it — "am I down
more than I am comfortable with, right now?" — had no answer between the open and the
close.

This is deliberately NOT a second circuit breaker. The breaker lives inside the bridge
(EdgeLogBridge.cs, L5) because it must be able to act even if this runner is dead; it
flattens and disables. This only WATCHES and TELLS YOU, at a threshold you can set well
below the breaker's, so you hear about a bad day long before anything trips. Two
different jobs, deliberately two different places:

    warn_usd   (here)   -> "you should look at this"     -> ntfy push, no action
    max_daily_loss_usd  -> "stop trading now"            -> bridge flattens + disables

It reads the bridge's own /risk endpoint rather than recomputing P&L, so the number it
alerts on is byte-identical to the number the breaker is judging. If the two disagreed,
the alert would be worse than useless.

STATE. Alerts are latched per (account, day) in a small JSON file so a position sitting
underwater does not push every cycle. The latch clears on a new trading day, and also
clears if the account recovers back above the threshold, so a genuine second breach on
the same day does alert again.

Everything here is exception-proof: an alerter must never take down the watch loop.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
STATE_PATH = os.environ.get("EDGELOG_DD_STATE", r"C:\EdgeLog\dd_alert_state.json")
TIMEOUT_SEC = 4

# Warn WELL BEFORE the bridge's own max_daily_loss_usd so this is an early warning and
# not a duplicate of the breaker firing. Overridable per environment.
WARN_USD = float(os.environ.get("EDGELOG_DD_WARN_USD", "500"))


def _now_et_date():
    """Trading day key. Uses ET so the latch rolls at the right midnight regardless of
    where the box's clock is set (this one runs on Arizona time)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get(path):
    try:
        with urllib.request.urlopen(BASE.rstrip("/") + path, timeout=TIMEOUT_SEC) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st):
    try:
        d = os.path.dirname(STATE_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception as e:
        print(f"[dd-alert] state save failed: {type(e).__name__}: {e}")


def _notify(msg, title, priority="high"):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print(f"[dd-alert] NTFY_TOPIC unset, logging only: {msg}")
        return
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"), method="POST",
            headers={"Title": title, "Priority": priority})
        urllib.request.urlopen(req, timeout=TIMEOUT_SEC)
    except Exception as e:
        print(f"[dd-alert] notify failed: {type(e).__name__}: {e}")


def check():
    """One pass. Never raises — it shares the runner's watch loop."""
    risk = _get("/risk")
    if not risk:
        return  # bridge down; nt_heartbeat already owns that alarm
    try:
        breaker_floor = float((risk.get("limits") or {}).get("max_daily_loss_usd") or 0)
    except Exception:
        breaker_floor = 0.0

    st = _load_state()
    day = _now_et_date()
    if st.get("day") != day:
        st = {"day": day, "alerted": {}}
    alerted = st.setdefault("alerted", {})
    changed = False

    for a in (risk.get("accounts") or []):
        name = a.get("account")
        try:
            real = float(a.get("realized_today") or 0)
        except Exception:
            continue
        if not name:
            continue
        breached = real <= -abs(WARN_USD)
        was = bool(alerted.get(name))
        if breached and not was:
            headroom = abs(breaker_floor) - abs(real) if breaker_floor else None
            msg = (f"{name} realized {real:,.2f} today (warn at -{WARN_USD:,.0f}). "
                   f"Net open: {a.get('net_contracts')} contract(s).")
            if headroom is not None:
                msg += (f" Bridge breaker trips at -{abs(breaker_floor):,.0f} "
                        f"-- {headroom:,.0f} of room left.")
            _notify(msg, "EDGELOG: intraday drawdown")
            print(f"[dd-alert] WARN {msg}")
            alerted[name] = True
            changed = True
        elif was and not breached:
            # Recovered back above the line: clear the latch so a genuine SECOND breach
            # later the same day still gets through.
            alerted[name] = False
            changed = True
            print(f"[dd-alert] {name} recovered to {real:,.2f} — latch cleared")

    if changed:
        st["saved_at"] = time.time()
        _save_state(st)


if __name__ == "__main__":
    check()
    print(json.dumps(_load_state(), indent=2))
