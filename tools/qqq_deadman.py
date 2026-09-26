# tools/qqq_deadman.py -- runner-INDEPENDENT dead-man's-switch for the Webull QQQ paper
# book (deadman/deadman_keel_guard, 2026-09-26). Modeled on tools/nt_cloud_watchdog.py:
# same shape, same secrets, same "runs on GitHub's own infrastructure so it keeps
# checking even when the box is completely dark" reasoning.
#
# WHY THIS EXISTS. api/qqq_exec.py (the book, edgelog-qqq-exec.service on the Oracle
# ARM box) publishes users/{uid}/meta/qqq_exec every tick -- but that publish is itself
# the thing that would stop if the box died, the systemd service crashed and did not
# restart, or the process wedged. Nothing on the box can page anyone about the box
# itself going dark; something OFF the box has to. This script is that something: a
# GitHub Actions scheduled workflow (.github/workflows/qqq-deadman.yml) that reads the
# published doc straight from Firestore and pages ntfy.sh when it looks wrong.
#
# TWO SEPARATE CONDITIONS, TWO SEPARATE SEVERITIES:
#   1. Book heartbeat stale (doc["updated_at"] or doc["lease"]["leased_at"] older than
#      _heartbeat_stale_threshold(), the LARGER of HEARTBEAT_STALE_SEC or 1.5x the
#      book's own advertised publish cadence -- see that function) -- URGENT. The book
#      itself has stopped publishing, which is the "the whole watcher is dead" failure
#      mode this switch exists for.
#   2. Book holds an open position AND the signal engine looks stale (doc["feed_stale"]
#      is True -- engine mode's own feed check, see api/qqq_exec.py's
#      _check_feed_engine/_build_doc) -- HIGH. Not as urgent as #1 (the book is still
#      publishing, so SOMETHING is alive), but an open lot with no fresh signal behind
#      it is exactly the situation where nobody would notice a stuck position until
#      Monday. `feed_stale` is only checked when the doc actually carries the key --
#      an older doc shape or a book running in a mode that never sets it degrades to
#      "unknown", never to a false alarm.
#
# ONLY DURING THE TRADING WINDOW (09:25-16:10 ET) ON A TRADING DAY -- see
# api/market_calendar.py. Outside that window a quiet book is expected, not a failure;
# checking anyway would page every night and every weekend for nothing. GitHub Actions
# cron is UTC and fires several minutes late under load, so the workflow schedules
# every 5 minutes over a UTC window comfortably wider than the ET window in EITHER
# DST state, and THIS SCRIPT decides (via evaluate()'s _in_window, using the real ET
# clock and api.market_calendar) whether a given run should actually check anything --
# never the cron expression alone.
#
# DEDUPE: "alert on the crossing, then at most every ALERT_REPEAT_SEC" -- see _dedupe.
# State is a small doc, users/{uid}/meta/qqq_deadman, this script itself writes (the
# ONLY writer of that doc -- unlike nt_cloud_watchdog.py, which deliberately never
# writes meta/nt_alert because that stays the runner's own job; there is no local
# process for this state to belong to instead, since the whole point is to keep
# working when nothing local is running). A run that cannot read/write that doc still
# evaluates and can still push -- it just cannot dedupe -- rather than skipping the
# whole check over a state-store hiccup.
#
# CREDENTIALS: same shape as tools/nt_cloud_watchdog.py -- FIREBASE_SERVICE_ACCOUNT_JSON
# (Firebase Admin SDK certificate, written to a temp file by the workflow),
# GOOGLE_APPLICATION_CREDENTIALS pointed at it, EDGELOG_UID (the owner's Firebase uid),
# NTFY_TOPIC (a long random unguessable ntfy.sh topic -- never hardcoded or logged,
# since anyone who knows a public ntfy.sh topic name can read every message on it).
# This script reuses all three of nt-watchdog.yml's existing secret names -- see the
# module-level REQUIRED_SECRETS list below and the report this track returns.
#
# Exception-proof by the same contract as nt_cloud_watchdog.py: this must never blow up
# the GitHub Actions job in a way that silently swallows a real "the box is dead"
# condition. On a read/eval error it prints a loud message and exits nonzero so the
# workflow run itself shows red in GitHub's UI.
import argparse
import datetime as _dt
import json
import os
import sys

# Make api/ importable when this script is run as `python tools/qqq_deadman.py` from the
# repo root -- same convention as tools/nt_cloud_watchdog.py reaching api.nt_heartbeat.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import market_calendar  # noqa: E402  (see sys.path insert above)

# Every GitHub secret this script needs -- printed by --print-secrets and quoted in the
# report this track returns. Named exactly as nt-watchdog.yml already names them
# (.github/workflows/nt-watchdog.yml), so all three are REUSED, not new.
REQUIRED_SECRETS = ["FIREBASE_SERVICE_ACCOUNT_JSON", "EDGELOG_UID", "NTFY_TOPIC"]

ET = "America/New_York"

# Trading-day window this switch is armed for (task spec). Outside it, evaluate()
# returns immediately with no checks and no pushes -- see module docstring.
SESSION_START = (9, 25)
SESSION_END = (16, 10)

# Book heartbeat (doc["updated_at"] or doc["lease"]["leased_at"]) older than this ->
# urgent push. 3x-ish the tick loop's own 5s cadence would be far too tight for a
# dead-man's-switch that only samples every few minutes (see the module-level cron
# comment) -- this is deliberately a "the box has clearly stopped", not a "one slow
# tick", bound. This is a FLOOR, not the whole threshold -- see
# _heartbeat_stale_threshold below for when the book's own publish cadence has
# widened past it.
HEARTBEAT_STALE_SEC = 180

# 1.5x the book's OWN advertised publish cadence (lease["renew_every_sec"]) -- same
# margin, same reasoning, as api/qqq_exec.py's LEASE_STALE_MARGIN/_lease_stale_bound
# (deadman/deadman_keel_guard review fix, 2026-09-26). Outside the broker-armed window
# (qqq_exec's _in_market_window is 09:25-16:05, five minutes NARROWER than this
# script's own SESSION_END=16:10) or whenever the broker is not armed
# (effective_mode not PAPER/LIVE), qqq_exec's publish interval widens from 20-60s to
# 600s -- so a plain HEARTBEAT_STALE_SEC=180 bound reads the LAST in-session publish
# (~16:05) as stale by the time this switch checks at 16:09-16:10, every trading day
# the broker happens to be off. Using whichever is LARGER of the fixed floor or this
# margin means a book publishing slowly ON PURPOSE is never mistaken for a dead one.
HEARTBEAT_STALE_MARGIN = 1.5

# "Alert on the crossing, then at most every 30 minutes" (task spec) while a condition
# stays active. A run more often than this would just repeat the same page for a
# problem the owner already knows about; less often risks looking like it went away.
ALERT_REPEAT_SEC = 1800


def _in_window(now_et):
    """Trading day + 09:25-16:10 ET, per market_calendar.is_session -- see module
    docstring "ONLY DURING THE TRADING WINDOW"."""
    if not market_calendar.is_session(now_et.date()):
        return False
    hhmm = (now_et.hour, now_et.minute)
    return SESSION_START <= hhmm <= SESSION_END


def _heartbeat_age_seconds(book_doc, now_et):
    """Seconds since the book last published, or None if it cannot be determined at
    all (doc missing, or missing both fields it could come from) -- a caller treats
    None exactly like "very stale", never like "fine". Prefers doc["lease"]["leased_at"]
    (a real epoch timestamp, tz-unambiguous -- see api/qqq_exec.py's _build_doc) over
    doc["updated_at"] (an ET-naive "%Y-%m-%d %H:%M:%S" string, same file) since the
    lease field is what a SECOND host already uses to judge this same doc's freshness
    (api/qqq_exec.py's _check_lease) -- reusing it here means this switch and the
    book's own cross-host guard can never disagree about what "fresh" means."""
    if not isinstance(book_doc, dict):
        return None
    lease = book_doc.get("lease") or {}
    leased_at = lease.get("leased_at")
    if isinstance(leased_at, (int, float)) and leased_at > 0:
        return max(0.0, now_et.timestamp() - float(leased_at))
    updated_at = book_doc.get("updated_at")
    if updated_at:
        try:
            from zoneinfo import ZoneInfo
            naive = _dt.datetime.strptime(str(updated_at), "%Y-%m-%d %H:%M:%S")
            ts_et = naive.replace(tzinfo=ZoneInfo(ET))
            return max(0.0, (now_et - ts_et).total_seconds())
        except Exception:
            return None
    return None


def _heartbeat_stale_threshold(book_doc):
    """How old the book's heartbeat may get before it counts as stale -- whichever is
    LARGER of the fixed HEARTBEAT_STALE_SEC floor or HEARTBEAT_STALE_MARGIN (1.5x) times
    the book's own advertised publish cadence, lease["renew_every_sec"] (see that
    constant's own comment; mirrors api/qqq_exec.py's _lease_stale_bound exactly).
    Missing, unreadable or non-positive -- an older doc that predates this field, a
    stray value, or no doc at all -- falls back to HEARTBEAT_STALE_SEC alone, exactly
    the behaviour before this fix."""
    lease = (book_doc or {}).get("lease") if isinstance(book_doc, dict) else None
    lease = lease if isinstance(lease, dict) else {}
    try:
        cadence = float(lease.get("renew_every_sec"))
    except (TypeError, ValueError):
        return HEARTBEAT_STALE_SEC
    if cadence != cadence or cadence <= 0:   # cadence != cadence catches NaN
        return HEARTBEAT_STALE_SEC
    return max(HEARTBEAT_STALE_SEC, HEARTBEAT_STALE_MARGIN * cadence)


def _has_open_position(book_doc):
    """True if any leg in doc["positions"] is currently open -- api/qqq_exec.py's
    _build_doc only ever puts a leg into `positions` while a lot is open (side +
    shares_remaining), so presence with a nonzero side/shares is enough; a leg with no
    open lot is simply absent from the dict, never present-but-flat."""
    if not isinstance(book_doc, dict):
        return False
    positions = book_doc.get("positions")
    if not isinstance(positions, dict):
        return False
    for lot in positions.values():
        if not isinstance(lot, dict):
            continue
        side = lot.get("side")
        shares = lot.get("shares")
        try:
            if side and shares is not None and float(shares) != 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _dedupe(active, rec, now_epoch):
    """One condition's push decision + updated state record. `rec` is the small dict
    this condition owns inside the state doc: {"active": bool, "last_pushed_epoch":
    float|None}. Pushes on the crossing (inactive -> active) and then at most every
    ALERT_REPEAT_SEC while it stays active; going inactive clears the record so the
    NEXT crossing pages immediately rather than waiting out a stale cooldown from a
    problem that already resolved."""
    rec = dict(rec or {})
    if not active:
        return False, {"active": False, "last_pushed_epoch": None}
    last_pushed = rec.get("last_pushed_epoch")
    was_active = bool(rec.get("active"))
    push = (not was_active) or (last_pushed is None) or (
        (now_epoch - float(last_pushed)) >= ALERT_REPEAT_SEC)
    if push:
        last_pushed = now_epoch
    return push, {"active": True, "last_pushed_epoch": last_pushed}


def evaluate(book_doc, now_et, prior_state=None):
    """Pure decision function: given the book's published doc, the current ET time,
    and this switch's own prior state doc, returns
        {"in_window": bool, "checks": {...}, "pushes": [{"severity","title","message"}],
         "state": <new state dict to persist>}
    Never touches Firestore or the network -- main() does that, this is what tests call
    directly (see the module docstring's dead-man's-switch spec, item 1: "Include
    --dry-run and a test with a fake doc")."""
    prior_state = prior_state or {}
    state = {"heartbeat": dict(prior_state.get("heartbeat") or {}),
             "position_signal": dict(prior_state.get("position_signal") or {})}
    result = {"in_window": False, "checks": {}, "pushes": [], "state": state}

    if not _in_window(now_et):
        result["message"] = "outside the 09:25-16:10 ET trading window / not a trading day"
        return result
    result["in_window"] = True
    now_epoch = now_et.timestamp()

    # -- condition 1: book heartbeat stale -> urgent --------------------------------
    hb_age = _heartbeat_age_seconds(book_doc, now_et)
    hb_threshold = _heartbeat_stale_threshold(book_doc)
    hb_active = hb_age is None or hb_age > hb_threshold
    push_hb, state["heartbeat"] = _dedupe(hb_active, state["heartbeat"], now_epoch)
    result["checks"]["heartbeat_age_sec"] = hb_age
    result["checks"]["heartbeat_stale"] = hb_active
    if push_hb:
        age_txt = "unknown (doc missing or has no heartbeat field)" if hb_age is None \
            else f"{hb_age:.0f}s"
        result["pushes"].append({
            "severity": "urgent",
            "title": "EDGELOG QQQ: book heartbeat DOWN",
            "message": f"users/<uid>/meta/qqq_exec heartbeat is {age_txt} old "
                      f"(threshold {hb_threshold:.0f}s) -- the book may have stopped "
                      f"publishing"})

    # -- condition 2: open position + stale signal engine -> high -------------------
    has_open = _has_open_position(book_doc)
    signal_known = isinstance(book_doc, dict) and "feed_stale" in book_doc
    signal_stale = bool(book_doc.get("feed_stale")) if signal_known else False
    position_risk = has_open and signal_known and signal_stale
    push_pos, state["position_signal"] = _dedupe(position_risk, state["position_signal"], now_epoch)
    result["checks"]["open_position"] = has_open
    result["checks"]["signal_engine_known"] = signal_known
    result["checks"]["signal_engine_stale"] = signal_stale
    if push_pos:
        result["pushes"].append({
            "severity": "high",
            "title": "EDGELOG QQQ: open position, stale signal engine",
            "message": "the book holds an open Webull position while the signal engine "
                      "looks stale (feed_stale=true) -- nothing may be watching this "
                      "position right now"})

    return result


def _get_firestore_client():
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path or not os.path.isfile(cred_path):
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS not set or file missing -- the workflow must "
            "write the FIREBASE_SERVICE_ACCOUNT_JSON secret to a temp file first")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    return firestore.client()


def _meta_doc(db, uid, doc_name):
    return db.collection("users").document(uid).collection("meta").document(doc_name)


def _read_meta_doc(db, uid, doc_name):
    doc = _meta_doc(db, uid, doc_name).get()
    return doc.to_dict() if doc.exists else None


def _write_meta_doc(db, uid, doc_name, data):
    _meta_doc(db, uid, doc_name).set(data)


def _ntfy_post(topic, message, title=None, priority=None):
    """POST one push through api/ntfy_push.py (reads NTFY_TOPIC, optional NTFY_TOKEN /
    NTFY_SERVER from the environment; `topic` is kept for the call shape only). Returns
    True on 2xx, False otherwise. Never raises, never logs the topic or token."""
    from api import ntfy_push
    return ntfy_push.push(message, title=title, priority=priority, timeout=10,
                          log=lambda s: print(f"[qqq-deadman] {s}"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="read + evaluate normally, print what would happen, but never "
                    "push to ntfy or write the qqq_deadman state doc")
    ap.add_argument("--print-secrets", action="store_true",
                    help="print the GitHub secret names this script needs and exit "
                    "(no Firestore/network access) -- see REQUIRED_SECRETS")
    a = ap.parse_args(argv)

    if a.print_secrets:
        print("\n".join(REQUIRED_SECRETS))
        return 0

    uid = os.environ.get("EDGELOG_UID")
    if not uid:
        print("[qqq-deadman] FATAL: EDGELOG_UID env var not set", file=sys.stderr)
        return 2
    ntfy_topic = os.environ.get("NTFY_TOPIC")
    if not ntfy_topic and not a.dry_run:
        print("[qqq-deadman] FATAL: NTFY_TOPIC env var not set", file=sys.stderr)
        return 2

    try:
        db = _get_firestore_client()
        book_doc = _read_meta_doc(db, uid, "qqq_exec")
        prior_state = _read_meta_doc(db, uid, "qqq_deadman") or {}
    except Exception as e:
        print(f"[qqq-deadman] FATAL: Firestore read failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2

    from zoneinfo import ZoneInfo
    now_et = _dt.datetime.now(tz=ZoneInfo(ET))
    rep = evaluate(book_doc, now_et, prior_state)
    # This repo is public (see tools/nt_cloud_watchdog.py's own "this file is public"
    # note), so GitHub Actions logs are world-readable. No secret leaks here either
    # way, but "open_position" is one bit of info about the owner's live book that
    # does not need to sit in a public log -- print every OTHER check, drop just that
    # one (2026-09-26 review).
    print_checks = {k: v for k, v in rep.get("checks", {}).items() if k != "open_position"}
    print_rep = {k: (print_checks if k == "checks" else v)
                for k, v in rep.items() if k != "state"}
    print(f"[qqq-deadman] {json.dumps(print_rep)}")

    if not rep["in_window"]:
        print(f"[qqq-deadman] {rep.get('message')}")
        return 0

    any_push_failed = False
    for push in rep["pushes"]:
        if a.dry_run:
            print(f"[qqq-deadman] DRY-RUN would push [{push['severity']}] "
                  f"{push['title']}: {push['message']}")
            continue
        ok = _ntfy_post(ntfy_topic, push["message"], title=push["title"],
                        priority=push["severity"])
        print(f"[qqq-deadman] pushed [{push['severity']}] {push['title']}: "
              f"{'ok' if ok else 'FAILED'}")
        if not ok:
            any_push_failed = True

    if not rep["pushes"]:
        print("[qqq-deadman] ok (heartbeat fresh, no at-risk open position)")

    if not a.dry_run:
        try:
            _write_meta_doc(db, uid, "qqq_deadman", rep["state"])
        except Exception as e:
            # Best-effort: a failed write only costs this run its dedupe memory (the
            # next run re-pages on the crossing again instead of staying quiet) --
            # never worth failing the whole check over, per module docstring.
            print(f"[qqq-deadman] state doc write failed (dedupe may repeat next run): "
                  f"{type(e).__name__}: {e}")

    return 1 if any_push_failed else 0


if __name__ == "__main__":
    sys.exit(main())
