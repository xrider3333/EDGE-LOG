"""tools/fs_usage_report.py -- who used the Firestore quota today (MANAGER 11-18, after the 11-13 429).

Sums the per-process tallies api/fs_usage.py writes (PC: C:/EdgeLog/fs_usage/<day>.jsonl; the box's
/home/ubuntu/edgelog/fs_usage/<day>.jsonl, pulled over ssh unless --no-box) and the web page's own
tally doc users/{uid}/meta/fs_usage_<day> (one read; --no-page skips it), and prints the top readers.
The day is the quota day (US/Pacific midnight reset). Free tier: 50,000 reads and 20,000 writes a day.

Usage: python tools/fs_usage_report.py [--day YYYY-MM-DD] [--days 3] [--no-box] [--no-page] [--top 15]
"""
import argparse
import collections
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PC_DIR = os.environ.get("EDGELOG_FS_USAGE_DIR") or "C:/EdgeLog/fs_usage"
BOX = "ubuntu@163.192.117.12"
BOX_KEY = os.path.expanduser("~/.ssh/edgelog_oracle")
FREE_READS, FREE_WRITES = 50000, 20000


def _rows_from_lines(lines, where):
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        r["where"] = where
        out.append(r)
    return out


def pc_rows(day):
    p = os.path.join(PC_DIR, day + ".jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return _rows_from_lines(f.read().splitlines(), "pc")


def box_rows(day):
    try:
        r = subprocess.run(["ssh", "-i", BOX_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", BOX,
                            f"cat /home/ubuntu/edgelog/fs_usage/{day}.jsonl 2>/dev/null"],
                           capture_output=True, text=True, timeout=40)
        return _rows_from_lines(r.stdout.splitlines(), "box")
    except Exception as e:
        print(f"(box tally not read: {e})")
        return []


def page_rows(day):
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
        db = firestore.client()
        out = []
        for u in db.collection("users").list_documents(page_size=20):
            snap = u.collection("meta").document(f"fs_usage_{day}").get()
            if snap.exists:
                for k, v in (snap.to_dict() or {}).items():
                    if isinstance(v, dict):
                        out.append({"caller": k, "where": "web", "reads": v.get("reads", 0),
                                    "writes": v.get("writes", 0), "listen_reads": v.get("listen_reads", 0)})
        return out
    except Exception as e:
        print(f"(page tally not read: {e})")
        return []


def report(day, rows, top):
    agg = collections.defaultdict(lambda: {"reads": 0, "listen_reads": 0, "writes": 0, "procs": set()})
    for r in rows:
        a = agg[(r.get("where"), r.get("caller"))]
        for k in ("reads", "listen_reads", "writes"):
            a[k] += int(r.get(k) or 0)
        if r.get("pid"):
            a["procs"].add(r["pid"])
    tot_r = sum(a["reads"] + a["listen_reads"] for a in agg.values())
    tot_w = sum(a["writes"] for a in agg.values())
    print(f"== {day} (Pacific quota day): counted reads {tot_r:,} of {FREE_READS:,} free, "
          f"writes {tot_w:,} of {FREE_WRITES:,}")
    print(f"{'where':5} {'caller':38} {'reads':>9} {'listen':>9} {'writes':>8} {'procs':>5} {'pct':>6}")
    rank = sorted(agg.items(), key=lambda kv: -(kv[1]["reads"] + kv[1]["listen_reads"]))
    for (where, caller), a in rank[:top]:
        r = a["reads"] + a["listen_reads"]
        print(f"{where or '?':5} {str(caller)[:38]:38} {a['reads']:>9,} {a['listen_reads']:>9,} {a['writes']:>8,} "
              f"{len(a['procs']) or '-':>5} {100.0 * r / max(1, tot_r):>5.1f}%")
    if len(rank) > top:
        print(f"... {len(rank) - top} more callers")
    print("Not counted: Python processes that never import `api` and tools that import firebase only inside a "
          "function; compare with the Firebase console total for the day.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--no-box", action="store_true")
    ap.add_argument("--no-page", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args(argv)
    from api.fs_usage import _quota_day
    last = dt.date.fromisoformat(a.day) if a.day else dt.date.fromisoformat(_quota_day())
    for i in range(a.days - 1, -1, -1):
        day = (last - dt.timedelta(days=i)).isoformat()
        rows = pc_rows(day) + ([] if a.no_box else box_rows(day)) + ([] if a.no_page else page_rows(day))
        report(day, rows, a.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
