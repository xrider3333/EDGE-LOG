"""missed_pull.py - pull the owner's SHOULD HAVE TRADED entries from EDGELOG (read only) into a local labelled set.

The owner logs setups he saw and did not take on LEDGER > REAL > SHOULD HAVE TRADED. The web stores each one at
users/{uid}/missed_trades/{id} (fields agreed with TRADING-LOG, 2026-10-02): url, setup, symbol (root, e.g. MNQ),
date YYYY-MM-DD, entryTime HH:MM ET (the bar he would have entered on; the signal candle is the minute before),
type LONG|SHORT, entry / stop / target, note, source, createdAt, updatedAt, and the PC's pointScore (ps1.1).

This tool only READS Firestore. It merges new and changed entries (updatedAt >= the last pull) into
C:\\EdgeLog\\missed_trades\\missed.json (outside git), keyed by id, and remembers the pull time. The CBU alert check
(tools/cbu_v1_alerts.py) reads that file: every CBU entry not in its in-sample list is OUT-OF-SAMPLE recall for the
pre-registered rules (SETUPS_PREREG_R3_CBU_V1.md section 3). These entries are a labelled set - never lockbox data,
never outcome evidence.

    python tools/missed_pull.py            # pull new/changed entries, list them
    python tools/missed_pull.py --all      # re-pull everything
"""
import argparse
import datetime as dt
import io
import json
import os
import sys

CACHE_DIR = r"C:\EdgeLog\missed_trades"
CACHE = os.path.join(CACHE_DIR, "missed.json")
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = ("url", "setup", "symbol", "date", "entryTime", "type", "entry", "stop", "target", "note", "source",
        "createdAt", "updatedAt")


def signal_candle(entry_time):
    """HH:MM of the candle that closed before the entry bar (the point score's signal bar)."""
    h, m = (int(x) for x in str(entry_time).split(":")[:2])
    t = h * 60 + m - 1
    return "%02d:%02d" % (t // 60, t % 60)


def to_record(doc_id, x):
    """One Firestore doc -> the cached record (plain JSON; timestamps as ISO strings)."""
    r = {k: (x.get(k).isoformat() if hasattr(x.get(k), "isoformat") else x.get(k)) for k in KEEP if k in x}
    r["id"] = doc_id
    if r.get("entryTime"):
        r["signal_candle"] = signal_candle(r["entryTime"])
    ps = x.get("pointScore") or {}
    if ps:
        r["point_score"] = {"v": ps.get("v"), "total": ps.get("total"), "max": ps.get("max"),
                            "signal_bar": ps.get("signal_bar")}
    return r


def load_cache(path=CACHE):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"pulled_at": None, "entries": {}}


def save_cache(c, path=CACHE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(c, indent=1, ensure_ascii=False, sort_keys=True))
    os.replace(tmp, path)


def pull(all_=False):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO if os.path.exists(
            os.path.join(REPO, "serviceAccount.json")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG",
            "serviceAccount.json")))
    col = firestore.client().collection("users").document(UID).collection("missed_trades")
    c = load_cache()
    started = dt.datetime.now(dt.timezone.utc)
    q = col
    if c.get("pulled_at") and not all_:
        since = dt.datetime.fromisoformat(c["pulled_at"]) - dt.timedelta(minutes=5)   # overlap: clock skew
        q = col.where(filter=firestore.FieldFilter("updatedAt", ">=", since))
    changed = []
    for d in q.stream():
        rec = to_record(d.id, d.to_dict() or {})
        if c["entries"].get(d.id) != rec:
            changed.append(rec)
        c["entries"][d.id] = rec
    c["pulled_at"] = started.isoformat()
    save_cache(c)
    return c, changed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-pull every entry, not just new/changed ones")
    a = ap.parse_args(argv)
    c, changed = pull(a.all)
    print("SHOULD HAVE TRADED: %d entries cached in %s; %d new or changed this pull"
          % (len(c["entries"]), CACHE, len(changed)))
    for r in sorted(changed, key=lambda r: (r.get("date") or "", r.get("entryTime") or "")):
        ps = r.get("point_score") or {}
        print("  %s %s %s %s %s entry bar %s (signal %s) entry %s stop %s target %s point score %s"
              % (r["id"], r.get("date"), r.get("symbol"), r.get("type"), r.get("setup"), r.get("entryTime"),
                 r.get("signal_candle"), r.get("entry"), r.get("stop"), r.get("target"),
                 ("%s/%s" % (ps.get("total"), ps.get("max"))) if ps else "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
