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
the same day does alert again. The latch holds a LEVEL (1 = down past the alert line, 2 =
within 25% of the bridge's automatic stop); a rise to level 2 pushes again at once.

PHONE TEXT (2026-10-07, "make the notifications simpler to understand"). One plain note in the
format of api/ntfy_push.py (see build_note): title "Paper NT8: down $946 today", then
"Trading: not affected (flat)." / "Alert line -$500; automatic stop at -$12,000 ($11,054
away)." / "Do: nothing." Priority low (no buzz) until the loss is within 25% of the automatic
stop; then level 2: "Trading: AFFECTED - the automatic stop is close.", priority high.
The account is named in words ("Paper NT8" / "Real account"), never by its number.

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
    # api/ntfy_push.py owns the topic/token/server plumbing (WEBULL_GO_LIVE.md 1.10) --
    # this module just supplies its own "[dd-alert]" log prefix. Lazy import (not
    # module-level, same as api/nt_heartbeat.py's _page) so `python api/nt_drawdown_alert.py`
    # still works as a manual/debug run -- a top-level `from api import ntfy_push` makes
    # a bare script invocation fail with ModuleNotFoundError: No module named 'api',
    # since the runner is the only caller that imports this as api.nt_drawdown_alert.
    from api import ntfy_push
    ntfy_push.push(msg, title=title, priority=priority, timeout=TIMEOUT_SEC,
                    log=lambda t: print(f"[dd-alert] {t}"))


def build_note(name, real, net, warn_usd, breaker_floor):
    """The plain phone note (api/ntfy_push.plain) for one account's drawdown -> (note, level).
    level 2 = within 25% of the automatic stop (priority high), else 1 (priority low)."""
    from api import ntfy_push as N
    word = N.account_word(name)
    area = {"paper": "Paper NT8", "your real account": "Real account"}.get(word, "Another account")
    floor = abs(breaker_floor or 0)
    room = (floor - abs(real)) if floor else None
    level = 2 if (room is not None and room <= 0.25 * floor) else 1
    try:
        n = abs(int(float(net or 0)))
    except Exception:
        n = 0
    held = "flat" if n == 0 else "holding %d contract%s" % (n, "" if n == 1 else "s")
    line = "Alert line -%s" % N.usd(warn_usd)
    if floor and word == "paper":
        line += "; automatic stop at -%s (%s away)" % (N.usd(floor), N.usd(max(room, 0)))
    if level == 2 and word == "paper":
        trading, action = "the automatic stop is close", "check NinjaTrader now"
    else:
        trading, action = "not affected (%s)" % held, "nothing"
    note = N.plain("%s: down %s today" % (area, N.usd(real)), None, trading, line, action,
                   priority="high" if (level == 2 and word == "paper") else "low")
    return note, (level if word == "paper" else 1)


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
        prior_level = int(alerted.get(name) or 0)          # True (an older latch) reads as level 1
        was = prior_level > 0
        note, level = (None, 0)
        if breached:
            try:
                note, level = build_note(name, real, a.get("net_contracts"), WARN_USD, breaker_floor)
            except Exception as e:                       # never lose the alert over its own wording
                print(f"[dd-alert] plain text failed ({type(e).__name__}: {e}); sending a bare line")
                note, level = {"title": "Drawdown alert", "priority": "default",
                               "message": f"Trading: not affected.\nDown {abs(real):,.0f} today.\nDo: check NinjaTrader."}, 1
        if breached and level > prior_level:
            _notify(note["message"], note["title"], priority=note["priority"])
            print(f"[dd-alert] WARN {name} realized {real:,.2f} today: " + note["message"].replace("\n", " | "))
            alerted[name] = level
            changed = True
        elif breached and level < prior_level:
            alerted[name] = level                           # back out of the near-stop zone: a re-entry pushes again
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
