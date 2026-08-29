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
# The live ML gate service (api/gate_live.py) -- the "bouncer" NinjaTrader asks before
# each entry. Published alongside the bridge for exactly the reason this module exists:
# it went live 2026-08-16 with NO indicator anywhere, and because it is FAIL-OPEN a dead
# bouncer looks identical to a working one from the outside -- NOISE just quietly trades
# ungated and the forward test stops being the experiment it claims to be.
GATE_BASE = os.environ.get("EDGELOG_GATE_URL", "http://127.0.0.1:8392")
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


def gate_snapshot():
    """Is the live ML gate service answering, and is its model current? Never raises.

    `stale_days` is what actually matters day to day: the service re-fits itself each
    evening, so a model trained more than a few days back means the nightly refresh has
    been failing even though the service still answers every request.
    """
    out = {"up": False, "legs": [], "error": None, "latency_ms": None,
           "trained_through": None, "stale_days": None}
    t0 = time.time()
    try:
        req = urllib.request.Request(GATE_BASE.rstrip("/") + "/gate/health", method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as e:
        out["error"] = f"gate service not reachable ({type(e).__name__}) - NinjaTrader will trade UNGATED"
        return out
    out["up"] = True
    out["latency_ms"] = int((time.time() - t0) * 1000)
    legs = (data.get("legs") or {})
    rows, newest = [], None
    for k, v in legs.items():
        tt = (v or {}).get("trained_through")
        rows.append({"leg": k, "loaded": bool((v or {}).get("loaded")),
                     "model": (v or {}).get("model"), "trained_through": tt})
        if tt and (newest is None or str(tt) > str(newest)):
            newest = tt
    out["legs"] = rows
    out["trained_through"] = newest
    if not rows or not all(r["loaded"] for r in rows):
        out["error"] = "gate service is up but a model failed to load - those legs trade UNGATED"
    try:
        if newest:
            d = datetime.strptime(str(newest)[:10], "%Y-%m-%d").date()
            out["stale_days"] = (datetime.now(timezone.utc).date() - d).days
    except Exception:
        pass
    return out


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
        # Independent of the bridge on purpose: NinjaTrader can be perfectly healthy
        # while the gate is dead, and that combination is the dangerous one.
        "gate": gate_snapshot(),
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
    # The recover watchdog's armed/parked state rides along in the same doc the web
    # already reads for NinjaTrader status, so the button can show the truth from the PC
    # instead of remembering what it last clicked. Never fatal: a snapshot that reaches
    # the owner without this field is still worth publishing.
    try:
        from api import nt_watchdog
        rep["watchdog"] = nt_watchdog.state()
    except Exception as e:
        rep["watchdog"] = {"ok": False, "enabled": None, "state": "unknown",
                           "error": f"{type(e).__name__}: {e}"}
    try:
        db.collection("users").document(uid).collection("meta").document(
            "nt_bridge").set(rep)
        if rep.get("up"):
            print(f"[nt-bridge] up (v{rep.get('version')}, "
                  f"{len(rep.get('accounts', []))} account(s))")
        else:
            print(f"[nt-bridge] down: {rep.get('error')}")
        g = rep.get("gate") or {}
        if g.get("up") and not g.get("error"):
            print(f"[ml-gate] up ({len(g.get('legs') or [])} model(s), "
                  f"{g.get('latency_ms')}ms, trained {g.get('trained_through')})")
        else:
            print(f"[ml-gate] DOWN: {g.get('error')}")
    except Exception as e:
        print(f"[nt-bridge] publish failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    r = snapshot()
    print(json.dumps(r, indent=2))
