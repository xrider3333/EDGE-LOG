#!/usr/bin/env python3
"""
tools/queue_truth.py -- what the runner's job queue REALLY holds, read straight from
Firestore by STATUS, next to what a date-ordered "newest N" read would show.

WHY THIS EXISTS (2026-09-06): the web read the newest 12 job docs by createdAt while
the runner claims the OLDEST queued job first, so a requeued orphan that was RUNNING
sat outside the window - the top-bar chip said "5 WAITING, nothing running" while the
truth was 1 running + 8 waiting. The web was fixed (v73.532, one status-filtered live
listener); this script is the independent check for the next time someone says "the
queue says N". Read-only.

Usage (from anywhere; needs serviceAccount.json in the repo root, never commit it):
  python tools/queue_truth.py                 # live jobs by status + the newest-12 window
  python tools/queue_truth.py --durations     # + elapsed_s stats per job type / timeframe
  python tools/queue_truth.py --uid <uid>     # another allowlisted user
"""
import argparse
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def _ts(x):
    try:
        return x.strftime("%m-%d %H:%M") if x else "-"
    except Exception:
        return str(x)[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--cred", default=os.path.join(ROOT, "serviceAccount.json"))
    ap.add_argument("--window", type=int, default=12, help="the old web window size")
    ap.add_argument("--durations", action="store_true")
    a = ap.parse_args()
    if not os.path.isfile(a.cred):
        print("no credential file at", a.cred)
        return 2

    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter

    firebase_admin.initialize_app(credentials.Certificate(a.cred))
    db = firestore.client()
    col = db.collection("users").document(a.uid).collection("backtests")

    print("== LIVE by status (queued / running / paused), oldest first == (UTC)")
    live = []
    for st in ("queued", "running", "paused"):
        for s in col.where(filter=FieldFilter("status", "==", st)).stream():
            d = s.to_dict() or {}
            live.append((d.get("createdAt"), s.id, st, d.get("strategy"),
                         d.get("type") or d.get("mode"), d.get("progress"),
                         d.get("startedAt"), d.get("orphan_requeued_at"), s.update_time))
    live.sort(key=lambda r: (r[0] is None, r[0]))
    for r in live:
        print(f"{_ts(r[0]):11}  {r[1][:10]:10}  {r[2]:8}  {str(r[3])[:30]:30} {str(r[4]):10} "
              f"prog={r[5]} started={_ts(r[6])} orphan={_ts(r[7])} touched={_ts(r[8])}")
    n_run = sum(1 for r in live if r[2] in ("running", "paused"))
    n_wait = sum(1 for r in live if r[2] == "queued")
    print(f"TRUTH: {n_run} running/paused + {n_wait} waiting = {len(live)} live")

    print(f"== NEWEST {a.window} by createdAt (the pre-v73.532 web window) ==")
    win_live = 0
    for s in col.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(a.window).stream():
        d = s.to_dict() or {}
        st = str(d.get("status"))
        if st in ("queued", "running", "paused"):
            win_live += 1
        print(f"{_ts(d.get('createdAt')):11}  {s.id[:10]:10}  {st:9}  {str(d.get('strategy'))[:30]}")
    print(f"WINDOW sees {win_live} of the {len(live)} live jobs"
          + (" -- the rest were INVISIBLE to a date-ordered read" if win_live < len(live) else ""))

    if a.durations:
        print("== elapsed_s of finished jobs, last 150 by createdAt ==")
        by = collections.defaultdict(list)
        for s in col.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(150).stream():
            d = s.to_dict() or {}
            if d.get("status") != "done" or d.get("elapsed_s") is None:
                continue
            by[(d.get("type") or d.get("mode") or "?", d.get("timeframe"))].append(float(d["elapsed_s"]))
        for k, v in sorted(by.items(), key=lambda kv: -sum(kv[1])):
            v = sorted(v)
            print(f"{str(k[0]):14} tf={str(k[1]):5} n={len(v):3} median={v[len(v)//2]/60:7.1f} min"
                  f"  max={v[-1]/60:7.1f} min  total={sum(v)/3600:6.1f} h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
