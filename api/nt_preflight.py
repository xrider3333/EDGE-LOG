"""9am NinjaTrader roster preflight — answers "is tonight's dialog mess still there?"

WHY THIS EXISTS (2026-08-14). While hand re-adding the strategies NT's auto-update
wiped, the re-add dialogs put two of them on the LIVE account (1810769) instead of
the DEMO7240108 paper account, and NinjaTrader itself showed no warning about it --
the mistake was only caught by chance. api/nt_bridge_pub.py already polls the
bridge (http://127.0.0.1:8391) and publishes a raw snapshot every 5 minutes, but
nobody reads that doc line by line every morning before the market opens. This
module runs the actual comparison -- expected roster vs live roster, right account
vs wrong account, LIVE-account exposure flagged loudest -- and makes that one bridge
call automatic every trading morning instead of a thing a human has to remember and
manually cross-check.

Everything here is exception-proof: a preflight check must never take down the
watch loop.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
TIMEOUT_SEC = 3

DEMO_ACCOUNT = "DEMO7240108"
LIVE_ACCOUNT = "1810769"

EXPECTED = [
    {"name": "EdgeLogNOISE", "account": DEMO_ACCOUNT},
    {"name": "EdgeLogENGUQ1m", "account": DEMO_ACCOUNT},
    {"name": "EdgeLogORBV2", "account": DEMO_ACCOUNT},
]


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


def check():
    """Query the bridge and compare the live roster against EXPECTED. Never raises.
    Returns {"checked_at", "ok", "problems": [...], "roster": [...]}"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    out = {"checked_at": now, "ok": False, "problems": [], "roster": []}
    try:
        health = _get("/health")
        if health is None:
            out["problems"] = ["bridge unreachable - NinjaTrader closed or AddOn dead"]
            return out

        strategies_resp = _get("/strategies")
        strategies = (strategies_resp or {}).get("strategies", [])
        out["roster"] = strategies
        by_name = {}
        for s in strategies:
            nm = s.get("name") or s.get("Name")
            if nm:
                by_name[nm] = s

        accounts_resp = _get("/accounts")
        accounts = (accounts_resp or {}).get("accounts", [])
        demo_cash = None
        for a in accounts:
            if a.get("name") == DEMO_ACCOUNT:
                demo_cash = a.get("cash")

        problems = []
        live_exposure = []

        for s in strategies:
            nm = s.get("name") or s.get("Name")
            acct = s.get("account") or s.get("Account")
            if acct == LIVE_ACCOUNT:
                live_exposure.append(
                    f"LIVE ACCOUNT EXPOSURE: {nm} on {LIVE_ACCOUNT}")

        for exp in EXPECTED:
            nm = exp["name"]
            row = by_name.get(nm)
            if row is None:
                problems.append(f"STRATEGY MISSING: {nm}")
                continue
            acct = row.get("account") or row.get("Account")
            if acct != exp["account"]:
                problems.append(
                    f"WRONG ACCOUNT: {nm} on {acct} (expected {exp['account']})")

        if demo_cash == 0:
            problems.append("demo connection down (cash reads $0)")

        # LIVE account exposure is the top-severity finding -- it goes first.
        out["problems"] = live_exposure + problems
        out["ok"] = not out["problems"]
        return out
    except Exception as e:
        out["problems"] = [f"preflight check failed: {type(e).__name__}: {e}"]
        return out


def publish(db, uid):
    """Run check() and write users/{uid}/meta/nt_preflight. Never raises."""
    try:
        rep = check()
    except Exception as e:
        print(f"[preflight] check failed: {type(e).__name__}: {e}")
        return
    try:
        db.collection("users").document(uid).collection("meta").document(
            "nt_preflight").set(rep)
    except Exception as e:
        print(f"[preflight] publish failed: {type(e).__name__}: {e}")
        return
    if rep.get("problems"):
        for p in rep["problems"]:
            print(f"[preflight] PROBLEM: {p}")
    else:
        print("[preflight] roster OK")


if __name__ == "__main__":
    r = check()
    print(json.dumps(r, indent=2))
