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

PHONE TEXT (2026-10-07, "make the notifications simpler to understand"). Fills are written in
the one plain format of api/ntfy_push.py (see build_note), in the owner's local time and with
words instead of codes:
  paper account   title "Paper fill: ENGU-Q bought 1 NQ", body "Trading: not affected. / Price
                  31,477.75 at 21:11. / Do: nothing." (strategy from the account + instrument
                  roster; a signal name containing "stop" in C:\\EdgeLog\\fills.csv, found by
                  exec_id, makes it "Paper fill: NOISE stop hit"). Priority low (no buzz).
  real account    title "Real account fill", body "You sold 1 MNQ @ 31,172.25 at 06:40 (not an EdgeLog
                  strategy)." -- the owner trades 1810769 by hand; the push stays because it is the
                  guard that no strategy ever touches it. Priority low.
  a paper fill outside its fingerprint (size over the limit, wrong instrument) is the one fill
  that says "AFFECTED" (priority default: look today, not an emergency).
The console log lines (runner.log) keep the old one-line "fill: ..." format.

Everything here is exception-proof: a fill reviewer must never take down the watch loop.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

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
# see tools/nt/EdgeLogBridge.cs Executions()). Account confirmed against
# C:\EdgeLog\bridge.json's allowed accounts (DEMO7240108-only, LIVE 1810769 refused at the
# bridge's L1 regardless). The roster itself now lives in one place, the NinjaTrader
# watchdog's $expected line (see api/nt_preflight.py's _expected_roster, which reads the
# same C:\EdgeLog\nt_recover.ps1) -- this dict's keys should track that list so the two
# cannot drift the way this file's EdgeLogORBV2 entry did (removed 2026-09-23: ORBV2 was
# switched off 2026-08-17 and taken off the watchdog roster 2026-09-09/10, but this
# fingerprint dict still had it -- and _match_strategy only checked account, so it never
# actually mattered which fingerprint matched; every demo fill silently landed on
# whichever dict entry the iteration reached first, which happened to be EdgeLogNOISE).
#
# Max qty + instrument, CONFIRMED against the live bridge on 2026-09-23 (replaces the old
# "1 contract/strategy is a reasonable assumption" guess -- the .cs strategy files'
# [Display] Quantity property has no compiled-in default, so it can only be read from
# actual fills, not from code). Today's fills: EdgeLogNOISE traded MNQ, 5 fills of qty 3;
# the NQ fills were qty 1 (EdgeLogENGUQ1m enters 1 NQ -- its leftover long 1 was flattened
# by hand through the bridge at 10:10 ET, which is one of today's two NQ fills). Both on
# DEMO7240108. Update these numbers (and retest) if the owner changes either strategy's size
# in the NT Strategies dialog.
EXPECTED = {
    "EdgeLogNOISE":   {"instrument_prefix": "MNQ", "account": "DEMO7240108", "max_qty": 3},
    "EdgeLogENGUQ1m": {"instrument_prefix": "NQ",  "account": "DEMO7240108", "max_qty": 1},
}


def _safe_print(msg):
    """print(), but tolerant of a console stdout that can't encode everything (this runs
    under the Windows runner, where stdout is cp1252). A flagged fill's message contains
    \u26a0, which cp1252 cannot encode -- printing it directly raised AFTER the phone alert
    had already gone out (see _respond_to_flagged_fill), so the crash's own log line
    ("respond failed: UnicodeEncodeError...") hid a successful notify behind what looked
    like a failure. Fall back to the stream's own encoding with unencodable characters
    replaced, so the console always shows something instead of raising."""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


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
        _safe_print(f"[exec-review] state save failed: {type(e).__name__}: {e}")


def _notify(message, title=None, priority=None):
    """Push one ntfy.sh notification via api/ntfy_push.py (WEBULL_GO_LIVE.md 1.10) --
    the topic/token/server plumbing lives there now, never hardcoded here. Logs instead
    of raising if the env var is unset or the send fails; this runs inside the local
    runner loop, which must never go down over a missing notification channel.

    Lazy import (not module-level, same as api/nt_heartbeat.py's _page) so
    `python api/nt_exec_review.py` still works as a manual/debug run -- a top-level
    `from api import ntfy_push` makes a bare script invocation fail with
    ModuleNotFoundError: No module named 'api', since the runner is the only caller
    that imports this as api.nt_exec_review."""
    from api import ntfy_push
    ntfy_push.push(message, title=title, priority=priority, timeout=TIMEOUT_SEC,
                    log=lambda t: _safe_print(f"[exec-review] {t}"))


def _signal_name(fill):
    """The strategy's own name for the order behind this fill ("EQ", "NZstop", ...), "" when it
    cannot be found. The bridge's /executions row has none, so it is looked up in the AddOn's
    fills.csv (same exec ids), tail only. Never raises."""
    for k in ("signal_name", "signalName", "order_name", "orderName"):
        if fill.get(k):
            return str(fill.get(k))
    eid = str(fill.get("exec_id") or "")
    if not eid:
        return ""
    try:
        import csv
        path = os.environ.get("EDGELOG_FILLS_CSV") or os.path.join(os.path.dirname(STATE_PATH) or ".", "fills.csv")
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 65536))
            lines = fh.read().decode("utf-8", "replace").splitlines()
        for row in reversed(list(csv.reader(lines))):
            if len(row) >= 10 and row[0] == eid:
                return row[9].strip()
    except Exception:
        pass
    return ""


def build_note(fill, reason=None, now=None):
    """The plain phone note for one fill (api/ntfy_push.plain) -> {"title", "message", "priority"}.
    `reason` is evaluate()'s flag text for a fill outside its strategy's fingerprint."""
    from api import ntfy_push as N
    acct = fill.get("account")
    inst = N.instrument_word(fill.get("instrument"))
    side = str(fill.get("side") or "").lower()
    verb = {"long": "bought", "short": "sold"}.get(side, side or "traded")
    try:
        qty = f"{abs(float(fill.get('qty') or 0)):g}"
    except Exception:
        qty = "?"
    try:
        px = N.price(fill.get("price"))
    except Exception:
        px = "?"
    when = N.hhmm(fill.get("time_utc"), now=now)
    word = N.account_word(acct)
    name, exp = _match_strategy(fill)
    strat = N.strategy_word(name) if name else None

    if word == "your real account":
        return N.plain("Real account fill", None, None,
                       f"You {verb} {qty} {inst} @ {px} at {when} (not an EdgeLog strategy).",
                       "nothing if this was you; if not, check your broker")
    if word != "paper":
        return N.plain("Other account fill", None, None,
                       f"Another account {verb} {qty} {inst} @ {px} at {when} (not an EdgeLog strategy).",
                       "nothing unless you did not do this")
    if reason:
        if str(reason).startswith("qty") and strat:
            return N.plain(f"Paper fill: {strat} too big", None,
                           f"{strat} traded more than its size limit of {exp['max_qty']}.",
                           f"{verb.capitalize()} {qty} {inst} @ {px} at {when}.",
                           "check the strategy's size in NinjaTrader", priority="default")
        return N.plain("Paper fill: unexpected", None,
                       "a paper strategy traded something it should not.",
                       f"{verb.capitalize()} {qty} {inst} @ {px} at {when}.",
                       "check the strategies in NinjaTrader", priority="default")
    who = strat or inst
    if "stop" in _signal_name(fill).lower():
        return N.plain(f"Paper fill: {who} stop hit", None, None,
                       f"{verb.capitalize()} {qty} {inst} @ {px} at {when}.", "nothing")
    return N.plain(f"Paper fill: {who} {verb} {qty} {inst}", None, None,
                   f"Price {px} at {when}.", "nothing")


def _safe_note(fill, reason=None):
    """build_note(), but a bug in the plain text must never lose the alert (the REVIEW push is the guard that no
    strategy touches the real account): fall back to the old one-line text."""
    try:
        return build_note(fill, reason)
    except Exception as e:
        _safe_print(f"[exec-review] plain text failed ({type(e).__name__}: {e}); sending the old text")
        return {"title": None, "message": _format_message(fill, reason), "priority": None}


def _push_note(note):
    _notify(note["message"], note["title"], note["priority"])


def _respond_to_flagged_fill(fill, reason):
    """Single call site for everything a flagged fill triggers. Escalating RESPONSE_TIER
    later is meant to mean: add an elif branch here that also calls nt_bridge.py's
    strategy-disable / /flatten / /killswitch -- no new plumbing anywhere else."""
    msg = _safe_note(fill, reason)
    if RESPONSE_TIER == "notify":
        _push_note(msg)
    # elif RESPONSE_TIER == "disable":
    #     _notify(msg); <call nt_bridge.py strategy disable on fill's strategy>
    # elif RESPONSE_TIER == "flatten":
    #     _notify(msg); <call bridge /flatten for fill's account/instrument>
    # elif RESPONSE_TIER == "killswitch":
    #     _notify(msg); <call bridge /killswitch>
    else:
        _push_note(msg)


def _format_message(fill, reason=None):
    base = (f"{fill.get('account')} {fill.get('instrument')} {fill.get('side')} "
            f"{fill.get('qty')} @ {fill.get('price')} ({fill.get('time_utc')})")
    if reason:
        return f"\u26a0 REVIEW fill: {base} -- {reason}"
    return f"fill: {base}"


def _match_strategy(fill):
    """The (name, fingerprint) EXPECTED entry whose account AND instrument prefix both
    match this fill, or (None, None). Matching by account alone (the previous behavior)
    silently paired EVERY DEMO7240108 fill with whichever fingerprint the dict iteration
    reached first -- always "EdgeLogNOISE", since both strategies share that account and
    Python dicts preserve insertion order -- so a genuine mismatch on that account (wrong
    instrument, e.g.) could never be detected, and every NOISE fill on MNQ was judged
    against the NOISE entry, which expected NQ, and marked REVIEW every time. The instrument
    prefix is what actually distinguishes NOISE's MNQ fills from ENGU-Q's NQ fills sharing
    the same demo account; plain str.startswith is naturally exact here -- "MNQ 12-26"
    does not start with "NQ", and "NQ 12-26" does not start with "MNQ"."""
    acct = fill.get("account")
    instrument = str(fill.get("instrument") or "")
    for name, exp in EXPECTED.items():
        if exp.get("account") == acct and instrument.startswith(exp["instrument_prefix"]):
            return name, exp
    return None, None


def evaluate(fill):
    """Pure function: fill dict -> (is_flagged: bool, reason: str or None). No I/O --
    kept separate from publish() so it's trivially testable."""
    acct = fill.get("account")
    instrument = str(fill.get("instrument") or "")

    known_accounts = {exp["account"] for exp in EXPECTED.values()}
    if acct not in known_accounts:
        return True, f"no known strategy trades account {acct!r}"

    name, exp = _match_strategy(fill)
    if exp is None:
        return True, (f"no known strategy on account {acct!r} trades instrument "
                       f"{instrument!r}")

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
        _safe_print(f"[exec-review] poll failed: {type(e).__name__}: {e}")
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
            _safe_print(f"[exec-review] evaluate failed: {type(e).__name__}: {e}")
            flagged, reason = True, f"evaluate() raised {type(e).__name__}"
        try:
            if flagged:
                _respond_to_flagged_fill(fill, reason)
                _safe_print(f"[exec-review] REVIEW: {_format_message(fill, reason)}")
            else:
                _push_note(_safe_note(fill))
                _safe_print(f"[exec-review] {_format_message(fill)}")
        except Exception as e:
            _safe_print(f"[exec-review] respond failed: {type(e).__name__}: {e}")

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
