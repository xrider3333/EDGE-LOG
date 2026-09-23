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

ROSTER SOURCE (2026-09-23). EdgeLogORBV2 was switched off on purpose on 2026-08-17 (its
config was a dead look-ahead-era run) and taken off the NinjaTrader watchdog's roster on
2026-09-09/10 (naming a PAR row to the bridge wedges NinjaTrader, so ORBV2 stayed off the
list -- see tools/nt_recover.ps1 / C:\\EdgeLog\\nt_recover.ps1's $expected line). This
module used to keep its own hardcoded copy of that roster and drifted from the watchdog's
change, reporting "STRATEGY MISSING: EdgeLogORBV2" every morning even though nothing was
wrong. Instead of two hand-maintained copies, the expected roster is now READ from the
watchdog script's own $expected line, so the two cannot drift apart again -- there is only
one list. A missing/unreadable/garbled watchdog script, or one whose $expected line names
nothing, falls back to the last-known-good roster below rather than failing the check.

Everything here is exception-proof: a preflight check must never take down the
watch loop.
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
TIMEOUT_SEC = 3

DEMO_ACCOUNT = "DEMO7240108"
LIVE_ACCOUNT = "1810769"

# Fallback roster -- used only when the watchdog script can't be found, read, decoded, or
# parsed, or when its $expected line names nothing (see _expected_roster). Keep this in
# sync with nt_recover.ps1's $expected BY HAND as a last resort only; the normal path
# never touches this list, so it drifting is a lesser problem than the file it backs up.
BUILTIN_ROSTER = ["EdgeLogNOISE", "EdgeLogENGUQ1m"]

# The watchdog script whose $expected line is the single source of truth for the roster.
# Overridable by the EDGELOG_NT_RECOVER_PS1 env var (ops) or the check()/_expected_roster
# function argument (tests) -- see _expected_roster.
DEFAULT_NT_RECOVER_PS1 = r"C:\EdgeLog\nt_recover.ps1"

# Matches a `$expected = @(...)` assignment, case-insensitively (PowerShell variables are
# case-insensitive), capturing only what is between the parens. Non-greedy so it stops at
# the FIRST `)` -- the real end of a simple string-list literal -- which is what keeps a
# trailing `# comment (that might itself contain quotes and parens)` on the same line from
# ever being scanned for names.
_EXPECTED_ASSIGN_RE = re.compile(r"\$expected\s*=\s*@\((.*?)\)", re.IGNORECASE)
# A single- or double-quoted PowerShell string literal.
_QUOTED_NAME_RE = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def _parse_expected_names(text):
    """Return the names in the LAST uncommented `$expected = @(...)` line found in `text`
    (the watchdog script's source), or [] if there is none. "Last wins" so a script that
    reassigns $expected further down (as this one has done historically) is read the same
    way PowerShell itself would execute it. A line whose first non-space character is `#`
    is a full-line comment and is skipped outright, before the assignment regex ever sees
    it -- that is what makes a commented-out `# $expected = @(...)` line inert."""
    names = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _EXPECTED_ASSIGN_RE.search(line)
        if not m:
            continue
        names = [a or b for a, b in _QUOTED_NAME_RE.findall(m.group(1))]
    return names


def _expected_roster(nt_recover_path=None):
    """Return (names, source): the roster of strategy names to check, and where it came
    from -- "watchdog" or "built-in". The watchdog script path is resolved in order from
    the `nt_recover_path` argument (tests), the EDGELOG_NT_RECOVER_PS1 env var (ops), then
    DEFAULT_NT_RECOVER_PS1. Never raises: a missing file, a permission error, an
    undecodable file, or a file whose last $expected line names nothing, all fall back to
    BUILTIN_ROSTER -- a preflight check must never itself go down over a garbled script."""
    path = (nt_recover_path or os.environ.get("EDGELOG_NT_RECOVER_PS1")
            or DEFAULT_NT_RECOVER_PS1)
    names = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        names = _parse_expected_names(text)
    except Exception:
        names = []
    if names:
        return names, "watchdog"
    return list(BUILTIN_ROSTER), "built-in"


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


def check(nt_recover_path=None):
    """Query the bridge and compare the live roster against the watchdog's expected
    roster (see _expected_roster). Never raises.
    Returns {"checked_at", "ok", "problems": [...], "roster": [...], "expected": [...],
    "roster_source": "watchdog"|"built-in"}. `nt_recover_path` overrides where the
    watchdog script is read from (tests only -- see _expected_roster)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    out = {"checked_at": now, "ok": False, "problems": [], "roster": []}
    try:
        names, source = _expected_roster(nt_recover_path)
        expected = [{"name": nm, "account": DEMO_ACCOUNT} for nm in names]
        out["expected"] = names
        out["roster_source"] = source

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

        for exp in expected:
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
