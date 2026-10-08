# nt_cloud_watchdog.py -- runner-INDEPENDENT dead-man's-switch for the NinjaTrader heartbeat.
#
# WHY THIS EXISTS (2026-08-15). api/nt_heartbeat.py already answers "has the NT bridge
# heartbeat gone stale while something was Realtime" -- but it only ever runs FROM INSIDE
# the same runner loop it is supposed to be watching (api/runner.py, on the owner's PC).
# If the PC crashes, loses power, sleeps, or Task Scheduler fails to relaunch the runner,
# the runner's own nt_heartbeat.publish() call also stops firing, so users/{uid}/meta/nt_alert
# freezes on whatever it last said (usually "ok") -- nothing ever pages the owner about the
# one failure mode that matters most: the whole watcher is dead.
#
# This script closes that loop by running somewhere that is NOT the owner's PC: a GitHub
# Actions scheduled workflow (.github/workflows/nt-watchdog.yml, every 15 minutes), on
# GitHub's own infrastructure -- NOT on the Oracle box, so it ships with a push to main (the
# workflow checks out main on every run) and tools/box_deploy.py never touches it. It reads
# users/{uid}/meta/nt_bridge straight from Firestore, feeds it through the SAME
# api.nt_heartbeat.evaluate() the runner uses (imported, never re-derived -- see below), and
# pushes ONE plain phone note (api/ntfy_push.py's format) when the heartbeat has gone stale.
#
# WHY evaluate() IS IMPORTED, NOT REWRITTEN: the staleness threshold (STALE_MINUTES) and
# the "was anything Realtime" logic live in exactly one place, api/nt_heartbeat.py. Two
# independent copies of that math WILL drift eventually and then the local board and the
# cloud page disagree about what "stale" means.
#
# WHAT IT KNOWS, AND NOTHING MORE (2026-10-07 plain-format rewrite):
#   * when NinjaTrader last reported: meta/nt_bridge "checked_at" (the PC runner's last
#     publish, UTC) -- shown on the owner's clock (America/Phoenix) via ntfy_push.hhmm();
#   * which strategies were running: evaluate()'s last_realtime_strategies (the roster from
#     the last cycle the bridge said up, carried in meta/nt_alert by the runner) -- unless the
#     last doc the PC wrote says NinjaTrader itself was closed (up:false): then nothing was
#     running when the PC went silent (a deliberate "close NinjaTrader, shut the PC down" is not
#     a strategy that stopped; the PC-side sweep owns "a strategy is down" while the PC is on);
#   * whether a position was open: meta/nt_bridge "positions" -- the bridge lists only
#     non-flat positions -- but that list is GROUND TRUTH only when the doc says up:true and
#     "positions" is not in its "partial" list (a doc written while NinjaTrader was closed
#     resets it to []). When the doc cannot say, this script uses the last positions it saw
#     on an up:true doc (remembered in its own state doc, below); if it never saw one, the
#     position is UNKNOWN and is read the safe way: "may be affected" -> high, never urgent.
#
# THE PHONE TEXT (owner GO 2026-10-07, "yes deploy box pings"; MANAGER-approved draft):
#   PC silent, no strategy running, no open position     "NinjaTrader: offline"     low
#       Trading: not affected (no strategy was running).
#       NinjaTrader has been silent since 21:30 - the PC is probably asleep.
#         (or, when the last doc said NinjaTrader was closed:
#          "NinjaTrader was closed and the PC has been silent since 17:45.")
#       Do: nothing.
#   silent while a strategy was running (position flat or unknown), or no strategy and the
#   position unknown                                     "NinjaTrader: CHECK NOW"   high
#       Trading: AFFECTED - ENGU-Q was running and has stopped reporting.
#       NinjaTrader has been silent since 03:12.
#       Do: wake the PC and open NinjaTrader.
#   silent with an open position                         "NinjaTrader: CHECK NOW"   urgent
#       Trading: AFFECTED - ENGU-Q was running with an open NQ position and has stopped reporting.
#   heartbeat fresh again after an episode that sent a high/urgent push
#                                                        "NinjaTrader: OK"          low
#       Back to normal (was: silent since 03:12).
# Before this it sent "EDGELOG: NT bridge DOWN" at URGENT priority on EVERY 15-minute run
# while a strategy was last seen Realtime -- e.g. all night when the PC was simply asleep.
#
# NIGHT MODE (2026-10-07, api/nt_night_mode.py). The PC closes NinjaTrader after the end-of-day
# checks and keeps it closed until the morning start (05:45 Arizona on the next trading day). This
# script runs on GitHub and can only know that through what the PC published: meta/nt_bridge carries
# a "night_mode" block {since, until, grace_until, until_hhmm, position_open}. While now is before
# grace_until (the window end + MORNING_GRACE_MIN, for the PC to wake and log in), a silent PC is
# EXPECTED: kind "night" -> per nt_night_mode.CLOUD_NIGHT_PUSH either no push at all ("silent", the
# default; the episode memory is left exactly as it is) or ONE low note
#       "NinjaTrader: night mode until 05:45"   low
#       Trading: not affected (NinjaTrader is closed for the night on purpose).
#       The PC has been silent since 17:45; NinjaTrader starts again at 05:45.
#       Do: nothing.
# After grace_until the normal rules apply again, so a morning where the PC never came back still
# pages (with the remembered positions: a trade force-closed overnight with its stop reads "position").
#
# REPEATS: ntfy_push.dedupe() -- the same state pushes once, then at most once a day; a
# worse state (offline -> running -> open position) pushes at once. Its memory lives in a
# small doc this script is the ONLY writer of, users/{uid}/meta/nt_watchdog:
#   {"push": <dedupe state>, "since": <epoch of the last heartbeat in the episode>,
#    "positions": {"open": [{"inst": "NQ", "acct": "paper"}, ...]} | None}
# (words only -- never an account number). It is written only when it changes (a push, a
# cleared episode, or a change in the remembered positions), so a quiet run costs one
# Firestore read and no write. This script still never writes meta/nt_alert (that stays the
# runner's job). FAIL-SAFE: a state read that fails is treated as "no memory" (the episode
# pushes again), and a push that fails keeps the old memory and exits 1 (the next run tries
# again) -- a state-store hiccup can cost an extra push, never a missed one.
#
# PUBLIC LOGS: the repo is public, so GitHub Actions logs are world-readable. The run prints
# evaluate()'s report (as before) and each push's title and priority, but never the push
# body or the remembered positions (one bit of information about the owner's book that does
# not belong in a public log -- same rule as tools/qqq_deadman.py).
#
# CREDENTIALS: needs the same service-account JSON shape api/runner.py's --cred flag takes
# (Firebase Admin SDK certificate), delivered via GitHub secret FIREBASE_SERVICE_ACCOUNT_JSON
# and written to a temp file by the workflow, then pointed to via GOOGLE_APPLICATION_CREDENTIALS
# (see .github/workflows/nt-watchdog.yml). The uid to check comes from env var
# EDGELOG_UID / secret EDGELOG_UID -- never hardcoded here, this file is public.
# The ntfy topic comes from env var NTFY_TOPIC / secret NTFY_TOPIC -- also never
# hardcoded or printed, since anyone who learns a public ntfy.sh topic name can read every
# message posted to it.
#
# Exception-proof by the same contract as api/nt_heartbeat.py: this must never blow up the
# GitHub Actions job in a way that silently swallows a real "the PC is dead" condition. On
# a Firestore read error it prints a loud message and exits nonzero so the workflow run
# itself shows red in GitHub's UI -- a visible failure, not a silent no-op.
import json
import os
import sys
import time

# Make api/ importable when this script is run as `python tools/nt_cloud_watchdog.py` from
# the repo root (matches how other tools/ scripts reach into api/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import ntfy_push  # noqa: E402  (see sys.path insert above)
from api import nt_heartbeat  # noqa: E402
from api import nt_night_mode  # noqa: E402

AREA = "NinjaTrader"
STATE_DOC = "nt_watchdog"
TIMEOUT_SEC = 10          # the old _ntfy_post's timeout, not the helper's default (8)
REPEAT_SEC = ntfy_push.DAY_S
WAKE = "wake the PC and open NinjaTrader"
# dedupe problem ids -> ntfy_push.RANK of the push each one causes
KIND_RANK = {"offline": 0, "running": 2, "unknown": 2, "position": 3, "night": 0}


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


def _read_meta_doc(db, uid, doc_name):
    doc = db.collection("users").document(uid).collection("meta").document(doc_name).get()
    return doc.to_dict() if doc.exists else None


def _write_meta_doc(db, uid, doc_name, data):
    db.collection("users").document(uid).collection("meta").document(doc_name).set(data)


# -- facts ------------------------------------------------------------------------------------
def positions_in_doc(bridge_data):
    """{"open": [{"inst", "acct"}]} when the bridge doc is ground truth for positions (up:true and
    "positions" not partial), else None. Words only: instrument_word / account_word."""
    if not isinstance(bridge_data, dict) or bridge_data.get("up") is not True:
        return None
    if "positions" in (bridge_data.get("partial") or []):
        return None
    rows = bridge_data.get("positions")
    if not isinstance(rows, list):
        return None
    out = []
    for r in rows:
        if not isinstance(r, dict) or str(r.get("side") or "").strip().lower() in ("", "flat"):
            continue
        try:
            if float(r.get("qty") or 0) == 0:
                continue
        except (TypeError, ValueError):
            pass                                   # an unreadable qty on a non-flat row: count it
        out.append({"inst": ntfy_push.instrument_word(r.get("instrument")),
                    "acct": ntfy_push.account_word(r.get("account"))})
    return {"open": out}


def strategy_names(rep):
    """evaluate()'s last Realtime roster as plain words, de-duplicated, in order."""
    names = []
    for n in (rep or {}).get("last_realtime_strategies") or []:
        w = ntfy_push.strategy_word(n)
        if w and w not in names:
            names.append(w)
    return names


def _and(words):
    words = list(words)
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _position_phrase(open_rows):
    insts = []
    for r in open_rows:
        if r.get("inst") and r["inst"] not in insts:
            insts.append(r["inst"])
    insts = insts or ["futures"]
    phrase = ("an open %s position" % insts[0]) if len(insts) == 1 else ("open %s positions" % _and(insts))
    if any(r.get("acct") == "your real account" for r in open_rows):
        phrase += " (your real account)"
    return phrase


def _since_epoch(bridge_data):
    t = ntfy_push.to_local((bridge_data or {}).get("checked_at"))
    return t.timestamp() if t is not None else None


# -- the decision -----------------------------------------------------------------------------
def nt_was_closed(bridge_data):
    """True when the last doc the PC wrote says NinjaTrader itself was closed (up:false) -- then no
    strategy was running when the PC went silent, whatever roster was held from earlier."""
    return isinstance(bridge_data, dict) and bridge_data.get("up") is False


def running_names(rep, bridge_data):
    """The strategies that were running when the PC went silent: evaluate()'s last Realtime roster,
    or none when the last doc says NinjaTrader was already closed."""
    return [] if nt_was_closed(bridge_data) else strategy_names(rep)


def night_window(bridge_data, now_ts):
    """The PC's published night-mode block when `now_ts` is before its grace_until (NinjaTrader closed
    on purpose and the morning start not yet overdue), else None. Judged by the doc's own times, never
    by its "active" flag: the doc may be hours old."""
    nmb = (bridge_data or {}).get("night_mode") if isinstance(bridge_data, dict) else None
    if not isinstance(nmb, dict):
        return None
    since = nt_night_mode.to_local(nmb.get("since"))
    grace = nt_night_mode.to_local(nmb.get("grace_until"))
    if since is None or grace is None:
        return None
    return nmb if since.timestamp() <= float(now_ts) < grace.timestamp() else None


def classify(rep, bridge_data, positions, now_ts=None):
    """-> "ok" | "night" | "offline" | "running" | "unknown" | "position" | None (cannot tell this run:
    the bridge doc is missing or has no readable timestamp -- leave the episode exactly as it is)."""
    sev = (rep or {}).get("severity")
    stale = (rep or {}).get("stale_minutes")
    if sev == "ok":
        return "ok"
    if stale is None or float(stale) <= nt_heartbeat.STALE_MINUTES:
        return None
    if now_ts is not None and night_window(bridge_data, now_ts):
        return "night"
    if positions is not None and positions.get("open"):
        return "position"
    if running_names(rep, bridge_data):
        return "running"
    return "offline" if positions is not None else "unknown"


def build_note(kind, rep, bridge_data, positions, since_epoch, now_ts):
    """The plain phone note for one stale state (see the module docstring for the texts)."""
    since = ntfy_push.hhmm(since_epoch, now=now_ts) if since_epoch else "an unknown time"
    names = running_names(rep, bridge_data)
    if kind == "night":
        nmb = (bridge_data or {}).get("night_mode") or {}
        until = nt_night_mode.hhmm(nmb.get("until"), now_ts) if nmb.get("until") else "the morning"
        trading = ("not affected (NinjaTrader is closed for the night on purpose)"
                   if not nmb.get("position_open") else
                   "an open paper trade keeps its stop, but nothing trails it until %s" % until)
        return ntfy_push.plain(AREA, "night mode until %s" % until, trading,
                               "The PC has been silent since %s; NinjaTrader starts again at %s." % (since, until),
                               "nothing", priority="low")
    if kind == "offline":
        problem = (("NinjaTrader was closed and the PC has been silent since %s." % since)
                   if nt_was_closed(bridge_data) else
                   ("NinjaTrader has been silent since %s - the PC is probably asleep." % since))
        return ntfy_push.plain(AREA, "offline", "not affected (no strategy was running)", problem,
                               "nothing", priority="low")
    one = len(names) == 1
    if kind == "position":
        pos = _position_phrase((positions or {}).get("open") or [])
        affects = ("%s %s running with %s and %s stopped reporting"
                   % (_and(names), "was" if one else "were", pos, "has" if one else "have")
                   if names else "NinjaTrader stopped reporting with %s" % pos)
        priority = "urgent"
    elif kind == "running":
        affects = "%s %s running and %s stopped reporting" % (
            _and(names), "was" if one else "were", "has" if one else "have")
        priority = "high"
    else:   # "unknown": no strategy was running, but nothing says whether a position is open
        affects = "a position may be open and NinjaTrader has stopped reporting"
        priority = "high"
    return ntfy_push.plain(AREA, "CHECK NOW", affects, "NinjaTrader has been silent since %s." % since,
                           WAKE, priority=priority)


def decide(rep, bridge_data, prior_state, now_ts):
    """Pure: (evaluate() report, meta/nt_bridge, this script's prior state doc, now) ->
    (action, new_state, note). action is None | "push" | "clear" (see ntfy_push.dedupe);
    note is the plain note to send for it, or None."""
    prior_state = prior_state if isinstance(prior_state, dict) else {}
    state = {"push": dict(prior_state.get("push") or {}), "since": prior_state.get("since"),
             "positions": prior_state.get("positions")}
    seen = positions_in_doc(bridge_data)
    if seen is not None:
        state["positions"] = seen                     # the newest ground truth, remembered
    kind = classify(rep, bridge_data, state["positions"], now_ts)
    if kind is None:
        return None, state, None
    if kind == "night" and nt_night_mode.CLOUD_NIGHT_PUSH != "low":
        return None, state, None                      # expected silence: no push, episode left as it is
    current = {} if kind == "ok" else {kind: KIND_RANK[kind]}
    action, push_state = ntfy_push.dedupe(current, state["push"], now_ts, REPEAT_SEC)
    state["push"] = push_state
    note = None
    if kind == "ok":
        if action == "clear":
            since = state.get("since")
            note = ntfy_push.back_to_normal(
                AREA, "silent since %s" % ntfy_push.hhmm(since, now=now_ts) if since else "")
        state["since"] = None
    else:
        state["since"] = _since_epoch(bridge_data) or state.get("since")
        if action == "push":
            note = build_note(kind, rep, bridge_data, state["positions"], state["since"], now_ts)
    return action, state, note


def main():
    uid = os.environ.get("EDGELOG_UID")
    if not uid:
        print("[nt-cloud-watchdog] FATAL: EDGELOG_UID env var not set", file=sys.stderr)
        return 2

    if not (os.environ.get("NTFY_TOPIC") or "").strip():
        print("[nt-cloud-watchdog] FATAL: NTFY_TOPIC env var not set", file=sys.stderr)
        return 2

    try:
        db = _get_firestore_client()
        bridge_data = _read_meta_doc(db, uid, "nt_bridge")
        prior_alert = _read_meta_doc(db, uid, "nt_alert")
    except Exception as e:
        print(f"[nt-cloud-watchdog] FATAL: Firestore read failed: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2

    try:
        prior_state = _read_meta_doc(db, uid, STATE_DOC) or {}
    except Exception as e:                    # no memory this run: the episode pushes again
        print(f"[nt-cloud-watchdog] state read failed (repeats not limited this run): "
              f"{type(e).__name__}")
        prior_state = {}

    rep = nt_heartbeat.evaluate(bridge_data, prior_alert)
    print(f"[nt-cloud-watchdog] {json.dumps(rep)}")

    action, state, note = decide(rep, bridge_data, prior_state, time.time())
    rc = 0
    if note is not None:
        ok = ntfy_push.send(note, timeout=TIMEOUT_SEC, log=lambda t: print(f"[nt-cloud-watchdog] {t}"))
        print(f"[nt-cloud-watchdog] pushed [{note['priority']}] {note['title']}: "
              f"{'ok' if ok else 'FAILED'}")
        if not ok:
            # not delivered: keep the old repeat memory so the next run tries again
            state = dict(state, push=dict(prior_state.get("push") or {}),
                         since=prior_state.get("since") if action == "clear" else state.get("since"))
            rc = 1
    elif rep.get("severity") == "ok":
        print(f"[nt-cloud-watchdog] ok ({rep.get('stale_minutes')}m)")
    else:
        print(f"[nt-cloud-watchdog] {rep.get('severity')} (no push this run: "
              f"{'already sent' if action is None and state['push'].get('set') else 'nothing to send'})")

    if state != prior_state:
        try:
            _write_meta_doc(db, uid, STATE_DOC, state)
        except Exception as e:
            print(f"[nt-cloud-watchdog] state write failed (the next run may push again): "
                  f"{type(e).__name__}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
