"""Tier-1 execution reviewer — answers "did that fill just happen look right?"

WHY THIS EXISTS (2026-08-15). tools/nt_bridge.py's `executions` command and the bridge's
GET /executions endpoint (tools/nt/EdgeLogBridge.cs Executions()) already return today's
fills, but nothing looks at them in real time -- the owner has to notice a fill happened
by going and checking. This module closes that gap the same way api/nt_bridge_pub.py and
api/nt_preflight.py closed theirs: poll the bridge, and this time push a notification
immediately on every NEW fill (an exec_id not seen before), so the owner has a live feed
of what's actually trading instead of finding out later.

SCOPE (owner-approved, exact -- do not exceed without asking):
  1. Every new fill gets a push notification, flagged or not -- "here's what just traded."
  2. Separately, each fill is checked against a small static per-strategy fingerprint
     (expected instrument prefix, expected account, max reasonable qty). A mismatch gets
     a distinctly-marked "REVIEW" notification instead of a plain "fill" one.
  3. NOTIFY ONLY. No disable, no flatten, no killswitch call -- the owner explicitly chose
     to start here and escalate later after watching it run for a while. The escalation
     path is intentionally a ONE-LINE change: see RESPONSE_TIER and _respond_to_flagged_fill
     below. REVIEW_WINDOW_MINUTES is the escalation timer the owner specified (15 min) --
     defined now, unused by tier "notify", ready to wire in when a later tier needs it.
  4. Deliberately NOT implemented: "is the fill price far from the market" checks. The
     bridge has no live quote/market-data endpoint today -- only fills, positions, orders,
     accounts (see tools/nt/EdgeLogBridge.cs). Faking this from stale data would be worse
     than not having it. This needs a new bridge endpoint (something like an
     Instrument.MarketData exposure) before it can be built honestly.

RESPONSE_TIER escalation path -- future tiers named, only "notify" implemented:
  "notify"     -- current: push a notification, take no other action.
  "disable"    -- future: also call `nt_bridge.py strategy disable <name>` on the strategy
                  that produced the flagged fill.
  "flatten"    -- future: also flatten the position via the bridge's /flatten.
  "killswitch" -- future: also trip the bridge's /killswitch.
Escalating is meant to be a one-line change to RESPONSE_TIER plus filling in the matching
branch inside _respond_to_flagged_fill -- no new plumbing, since every flagged fill already
funnels through that single call site.

STATE. Seen exec_ids are persisted locally (same directory/JSON-dict pattern as
tools/nt_bridge.py's other local state files, e.g. C:\\EdgeLog\\.edgelog_sync_state.json)
so a runner restart does not re-notify on every fill already seen earlier today.

Everything here is exception-proof: a fill reviewer must never take down the watch loop.
"""
import json
import os
import time
import urllib.error
import urllib.request

try:
    import requests
except Exception:
    requests = None

BASE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")
TIMEOUT_SEC = 3

# Poll /executions on its own tighter cadence than BRIDGE_SEC (300s) -- fills need to
# feel "immediate," and hitting a localhost endpoint every 30-60s is cheap. Simple
# always-on poll, no market-hours guessing (deliberately simple per owner's ask).
EXEC_POLL_SEC = 45.0

# Local seen-exec_id memory, same C:\EdgeLog local-state convention as
# tools/nt_bridge.py's other *_sync_state.json files.
STATE_PATH = os.environ.get(
    "EDGELOG_EXEC_REVIEW_STATE", r"C:\EdgeLog\seen_executions.json")

# ---- escalation path (see module docstring) --------------------------------------
# "notify" | "disable" | "flatten" | "killswitch" -- only "notify" is implemented.
# Changing tiers later is meant to be exactly this one line plus a branch body in
# _respond_to_flagged_fill(), never new plumbing.
RESPONSE_TIER = "notify"

# Future-tier timer (owner specified 15 min) -- unused while RESPONSE_TIER == "notify".
REVIEW_WINDOW_MINUTES = 15

# ---- per-strategy expected fingerprint --------------------------------------------
# Static, small, hand-maintained. Instrument is matched by PREFIX (bridge fill rows carry
# NinjaTrader's Instrument.FullName, e.g. "NQ 09-25", which includes the contract month --
# see tools/nt/EdgeLogBridge.cs Executions()). Account + roster confirmed against
# api/nt_preflight.py's EXPECTED list and C:\EdgeLog\bridge.json's allowed accounts
# (both DEMO7240108-only, LIVE 1810769 refused at the bridge's L1 regardless).
#
# Max qty: NOT found anywhere in the repo or in the .cs strategy files' [Display] Quantity
# property (tools/nt/EdgeLog{NOISE,ORBV2,ENGUQ1m}.cs each just declare `public int Qty`
# with no compiled-in default -- it's set live in the NT Strategies dialog, not in code).
# 1 contract/strategy is a reasonable assumption for these DEMO-account single-lot
# strategies, not a confirmed number -- tighten this if the owner runs multi-lot.
EXPECTED = {
    "EdgeLogNOISE":   {"instrument_prefix": "NQ", "account": "DEMO7240108", "max_qty": 1},
    "EdgeLogORBV2":   {"instrument_prefix": "NQ", "account": "DEMO7240108", "max_qty": 1},
    "EdgeLogENGUQ1m": {"instrument_prefix": "NQ", "account": "DEMO7240108", "max_qty": 1},
}


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


def _load_seen():
    """Read the local seen-exec_id state file. Never raises -- missing/corrupt -> empty."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        seen = data.get("seen")
        return set(seen) if isinstance(seen, list) else set()
    except Exception:
        return set()


def _save_seen(seen_set):
    """Write the local seen-exec_id state file. Never raises."""
    try:
        d = os.path.dirname(STATE_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        # Cap growth -- keep the file small, exec_ids are unordered so just trim size.
        rows = list(seen_set)[-5000:]
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"seen": rows, "saved_at": time.time()}, f)
    except Exception as e:
        print(f"[exec-review] state save failed: {type(e).__name__}: {e}")


def _notify(message):
    """Push one ntfy.sh notification. Reads the topic from NTFY_TOPIC (same env var the
    parallel cloud-watchdog work is expected to use) -- never hardcode a topic name.
    Logs instead of raising if the env var is unset or the send fails; this runs inside
    the local runner loop, which must never go down over a missing notification channel."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print(f"[exec-review] NTFY_TOPIC not set, logging only: {message}")
        return
    try:
        if requests is not None:
            requests.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                           timeout=TIMEOUT_SEC)
        else:
            req = urllib.request.Request(
                f"https://ntfy.sh/{topic}", data=message.encode("utf-8"), method="POST")
            urllib.request.urlopen(req, timeout=TIMEOUT_SEC)
    except Exception as e:
        print(f"[exec-review] notify failed: {type(e).__name__}: {e}")


def _respond_to_flagged_fill(fill, reason):
    """Single call site for everything a flagged fill triggers. Escalating RESPONSE_TIER
    later is meant to mean: add an elif branch here that also calls nt_bridge.py's
    strategy-disable / /flatten / /killswitch -- no new plumbing anywhere else."""
    msg = _format_message(fill, reason)
    if RESPONSE_TIER == "notify":
        _notify(msg)
    # elif RESPONSE_TIER == "disable":
    #     _notify(msg); <call nt_bridge.py strategy disable on fill's strategy>
    # elif RESPONSE_TIER == "flatten":
    #     _notify(msg); <call bridge /flatten for fill's account/instrument>
    # elif RESPONSE_TIER == "killswitch":
    #     _notify(msg); <call bridge /killswitch>
    else:
        _notify(msg)


def _format_message(fill, reason=None):
    base = (f"{fill.get('account')} {fill.get('instrument')} {fill.get('side')} "
            f"{fill.get('qty')} @ {fill.get('price')} ({fill.get('time_utc')})")
    if reason:
        return f"\u26a0 REVIEW fill: {base} -- {reason}"
    return f"fill: {base}"


def _match_strategy(fill):
    """Best-effort guess at which EXPECTED entry this fill belongs to. The /executions
    endpoint doesn't carry a strategy name (see EdgeLogBridge.cs Executions() -- account,
    exec_id, time_utc, instrument, side, qty, price only), so match by account: every
    strategy here trades the same DEMO account, so an account match is the only signal
    available without a bridge change. Returns None if nothing matches."""
    acct = fill.get("account")
    for name, exp in EXPECTED.items():
        if exp.get("account") == acct:
            return name, exp
    return None, None


def evaluate(fill):
    """Pure function: fill dict -> (is_flagged: bool, reason: str or None). No I/O --
    kept separate from publish() so it's trivially testable."""
    name, exp = _match_strategy(fill)
    if exp is None:
        return True, f"no known strategy trades account {fill.get('account')!r}"

    instrument = str(fill.get("instrument") or "")
    if not instrument.startswith(exp["instrument_prefix"]):
        return True, (f"instrument {instrument!r} does not match {name}'s expected "
                       f"prefix {exp['instrument_prefix']!r}")

    try:
        qty = abs(float(fill.get("qty") or 0))
    except Exception:
        qty = None
    if qty is not None and qty > exp["max_qty"]:
        return True, f"qty {qty:g} exceeds {name}'s configured max {exp['max_qty']}"

    # NOTE: deliberately no "price far from market" check -- the bridge has no live
    # quote/market-data endpoint today. See module docstring point 4.
    return False, None


def publish():
    """Poll /executions, notify on every new exec_id, flag mismatches. Never raises --
    same exception-proof contract as nt_bridge_pub.publish and nt_preflight.publish,
    since this shares their runner hook. No Firestore write -- this is push-only."""
    try:
        data = _get("/executions")
    except Exception as e:
        print(f"[exec-review] poll failed: {type(e).__name__}: {e}")
        return
    if data is None:
        return  # bridge down -- nt_bridge_pub/nt_heartbeat already cover that alarm

    rows = data.get("executions", []) or []
    seen = _load_seen()
    new_count = 0

    for fill in rows:
        exec_id = fill.get("exec_id")
        if not exec_id or exec_id in seen:
            continue
        seen.add(exec_id)
        new_count += 1
        try:
            flagged, reason = evaluate(fill)
        except Exception as e:
            print(f"[exec-review] evaluate failed: {type(e).__name__}: {e}")
            flagged, reason = True, f"evaluate() raised {type(e).__name__}"
        try:
            if flagged:
                _respond_to_flagged_fill(fill, reason)
                print(f"[exec-review] REVIEW: {_format_message(fill, reason)}")
            else:
                _notify(_format_message(fill))
                print(f"[exec-review] {_format_message(fill)}")
        except Exception as e:
            print(f"[exec-review] respond failed: {type(e).__name__}: {e}")

    if new_count:
        _save_seen(seen)


if __name__ == "__main__":
    # Manual smoke test: evaluate a couple of fabricated fills without hitting the bridge.
    ok_fill = {"account": "DEMO7240108", "exec_id": "test1", "time_utc": "now",
               "instrument": "NQ 09-25", "side": "Long", "qty": 1, "price": 20000.0}
    bad_fill = {"account": "DEMO7240108", "exec_id": "test2", "time_utc": "now",
                "instrument": "ES 09-25", "side": "Long", "qty": 5, "price": 5000.0}
    print(evaluate(ok_fill))
    print(evaluate(bad_fill))
