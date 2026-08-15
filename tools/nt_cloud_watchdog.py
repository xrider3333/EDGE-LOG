# nt_cloud_watchdog.py -- runner-INDEPENDENT dead-man's-switch for the NT bridge heartbeat.
#
# WHY THIS EXISTS (2026-08-15). api/nt_heartbeat.py already answers "has the NT bridge
# heartbeat gone stale while something was Realtime" -- but it only ever runs FROM INSIDE
# the same runner loop it is supposed to be watching (api/runner.py, on the owner's PC).
# If the PC crashes, loses power, or Task Scheduler fails to relaunch the runner, the
# runner's own nt_heartbeat.publish() call also stops firing, so users/{uid}/meta/nt_alert
# freezes on whatever it last said (usually "ok") -- nothing ever pages the owner about the
# one failure mode that matters most: the whole watcher is dead.
#
# This script closes that loop by running somewhere that is NOT the owner's PC: a GitHub
# Actions scheduled workflow (.github/workflows/nt-watchdog.yml), on GitHub's own
# infrastructure. It reads users/{uid}/meta/nt_bridge straight from Firestore, feeds it
# through the SAME api.nt_heartbeat.evaluate() the runner uses (imported, never
# re-derived -- see note below), and if the result is severity=='critical' it posts a push
# notification via ntfy.sh. Even if the PC/runner/NinjaTrader are all fully dead, GitHub's
# cron still fires and the owner still gets paged.
#
# WHY evaluate() IS IMPORTED, NOT REWRITTEN: the staleness threshold (STALE_MINUTES) and
# the "was anything Realtime" logic live in exactly one place, api/nt_heartbeat.py. Two
# independent copies of that math WILL drift eventually (one gets tuned, the other
# doesn't) and then the local board and the cloud page disagree about what "stale" means --
# worse than either checker alone. So this script imports api.nt_heartbeat and calls the
# same pure function.
#
# STATE ACROSS RUNS: this script does NOT write meta/nt_alert (that stays the runner's
# job -- api/nt_heartbeat.py's publish() is the only writer, so the local board's stored
# severity keeps meaning what it always meant). Instead every cloud run reads whatever
# meta/nt_alert the runner last wrote and passes it in as `prior_alert`, purely so
# evaluate()'s "last known Realtime roster" carries forward correctly even across a run
# where the bridge doc itself is stale (see nt_heartbeat.py's own docstring on why that
# roster has to be remembered). This script's own paging decision is stateless from GitHub
# Actions' point of view -- every run re-evaluates from scratch and re-pages on every
# critical run, i.e. every 15 minutes while the underlying problem persists. That is a
# deliberate choice: a dead-man's-switch that stops paging after the first alert (because
# some GH-Actions-only "already paged" flag says so) is exactly the kind of state that can
# itself go stale/lost between runs. Repeated pages while something is actually down is the
# safe failure mode; ntfy min-priority/quiet-hours on the phone side is the right place to
# dedupe, not this script.
#
# CREDENTIALS: needs the same service-account JSON shape api/runner.py's --cred flag takes
# (Firebase Admin SDK certificate), delivered via GitHub secret FIREBASE_SERVICE_ACCOUNT_JSON
# and written to a temp file by the workflow, then pointed to via GOOGLE_APPLICATION_CREDENTIALS
# (see .github/workflows/nt-watchdog.yml). The uid to check comes from env var
# EDGELOG_UID / secret EDGELOG_UID -- never hardcoded here, this file is public.
# The ntfy.sh topic comes from env var NTFY_TOPIC / secret NTFY_TOPIC -- also never
# hardcoded, since anyone who learns a public ntfy.sh topic name can read every message
# posted to it.
#
# Exception-proof by the same contract as api/nt_heartbeat.py: this must never blow up the
# GitHub Actions job in a way that silently swallows a real "the PC is dead" condition. On
# any read/eval error it prints a loud message and exits nonzero so the workflow run itself
# shows red in GitHub's UI -- a visible failure, not a silent no-op.
import json
import os
import sys
import urllib.error
import urllib.request

# Make api/ importable when this script is run as `python tools/nt_cloud_watchdog.py` from
# the repo root (matches how other tools/ scripts reach into api/, e.g. tools/nt_bridge.py
# reaching EdgeLogBridge -- here we reach api.nt_heartbeat instead).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import nt_heartbeat  # noqa: E402  (see sys.path insert above)


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


def _ntfy_post(topic, message, title=None, priority=None):
    """POST message to ntfy.sh/<topic>. Returns True on 2xx, False otherwise. Never raises."""
    url = f"https://ntfy.sh/{topic}"
    headers = {}
    if title:
        headers["Title"] = title
    if priority:
        headers["Priority"] = priority
    req = urllib.request.Request(
        url, data=message.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        print(f"[nt-cloud-watchdog] ntfy POST failed: HTTP {e.code}: {e.read()[:300]}")
        return False
    except Exception as e:
        print(f"[nt-cloud-watchdog] ntfy POST failed: {type(e).__name__}: {e}")
        return False


def main():
    uid = os.environ.get("EDGELOG_UID")
    if not uid:
        print("[nt-cloud-watchdog] FATAL: EDGELOG_UID env var not set", file=sys.stderr)
        return 2

    ntfy_topic = os.environ.get("NTFY_TOPIC")
    if not ntfy_topic:
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

    rep = nt_heartbeat.evaluate(bridge_data, prior_alert)
    print(f"[nt-cloud-watchdog] {json.dumps(rep)}")

    severity = rep.get("severity")
    if severity == "critical":
        ok = _ntfy_post(
            ntfy_topic,
            rep.get("message", "NT bridge heartbeat critical"),
            title="EDGELOG: NT bridge DOWN",
            priority="urgent",
        )
        print(f"[nt-cloud-watchdog] paged owner via ntfy: {'ok' if ok else 'FAILED'}")
        if not ok:
            return 1
    elif severity == "warning":
        # Default: log only, don't push -- avoid paging for the lower-risk case (stale
        # heartbeat but nothing was Realtime last we saw the roster, or a doc that's simply
        # missing/malformed). Flip this to also call _ntfy_post(...) if the owner decides
        # warnings should page too.
        print(f"[nt-cloud-watchdog] warning (not paged): {rep.get('message')}")
    else:
        print(f"[nt-cloud-watchdog] ok ({rep.get('stale_minutes')}m)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
