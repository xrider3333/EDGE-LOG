"""NinjaTrader bridge watchdog — answers "is NinjaTrader even there, and what is it doing?"

WHY THIS EXISTS (2026-08-14). The EdgeLogBridge AddOn (tools/nt/EdgeLogBridge.cs) has
served live NT state on http://127.0.0.1:8391 since 2026-08-14, but only the CLI client
(tools/nt_bridge.py) could see it -- the web app had no idea NinjaTrader existed. The
same day, NT's own auto-update silently deleted every strategy instance, and the only
way anyone found out was by opening NinjaTrader and looking with their own eyes; nobody
noticed for hours because nothing the owner actually looks at (the EDGELOG web app)
showed NT state at all. This module closes that gap the same way api/data_health.py
closed the stale-data gap: poll the bridge, write one small status doc the web app can
subscribe to, and make "NinjaTrader looks wrong" a thing you can see without alt-tabbing
into NT and squinting at a panel.

The bridge itself may be down at any moment -- NT closed, AddOn not compiled, machine
rebooting -- and THAT is signal worth publishing too, not an error to swallow silently.

Everything here is exception-proof: a watchdog must never take down the watch loop.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
TIMEOUT_SEC = 3
MAX_ROWS = 50


def _get(path):
    """One GET to the bridge. Returns parsed JSON dict, or None on any failure."""
    url = BASE.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except Exception:
        return None


def _capped(rows):
    return list(rows or [])[:MAX_ROWS]


def snapshot():
    """Poll the bridge and build the status dict. Never raises."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    out = {
        "checked_at": now,
        "up": False,
        "version": None,
        "strategies": [],
        "positions": [],
        "connections": [],
        "accounts": [],
        "error": None,
    }
    try:
        health = _get("/health")
        if health is None:
            out["error"] = "bridge not reachable (NinjaTrader closed or AddOn not compiled)"
            return out
        out["up"] = True
        out["version"] = health.get("version")

        partial = []

        strategies = _get("/strategies")
        if strategies is None:
            partial.append("strategies")
        else:
            out["strategies"] = _capped(strategies.get("strategies", []))

        positions = _get("/positions")
        if positions is None:
            partial.append("positions")
        else:
            out["positions"] = _capped(positions.get("positions", []))

        connections = _get("/connections")
        if connections is None:
            partial.append("connections")
        else:
            out["connections"] = _capped(connections.get("connections", []))

        accounts = _get("/accounts")
        if accounts is None:
            partial.append("accounts")
        else:
            rows = accounts.get("accounts", [])
            out["accounts"] = _capped([
                {"name": r.get("name"), "cash": r.get("cash"),
                 "realized": r.get("realized"), "live_locked": r.get("live_locked")}
                for r in rows
            ])

        if partial:
            out["partial"] = partial
        return out
    except Exception as e:
        out["up"] = False
        out["error"] = f"{type(e).__name__}: {e}"
        return out


def publish(db, uid):
    """Run snapshot() and write users/{uid}/meta/nt_bridge. Never raises.

    One small doc per call, same quota-cheap pattern as api/data_health.py's
    meta/data_health. Callers should throttle (the runner does, every BRIDGE_SEC)."""
    try:
        rep = snapshot()
    except Exception as e:
        print(f"[nt-bridge] snapshot failed: {type(e).__name__}: {e}")
        return
    try:
        db.collection("users").document(uid).collection("meta").document(
            "nt_bridge").set(rep)
        if rep.get("up"):
            print(f"[nt-bridge] up (v{rep.get('version')}, "
                  f"{len(rep.get('accounts', []))} account(s))")
        else:
            print(f"[nt-bridge] down: {rep.get('error')}")
    except Exception as e:
        print(f"[nt-bridge] publish failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    r = snapshot()
    print(json.dumps(r, indent=2))
