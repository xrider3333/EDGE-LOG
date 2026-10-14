"""WEBULL PAPER annotations: missed signals and trade notes, in ONE Firestore doc (users/{uid}/meta/qb_annot).

Owner 2026-10-14 (via MANAGER #97): "Add the Webull ORB trades, just annotate they were not picked up by Webull."
LEDGER > WEBULL PAPER draws every `missed` row dimmed among the trades with a MISSED chip and its note, and counts
it NOWHERE (not the hero, tiles, chart, calendar, RUNNING, day totals or the CSV export): Webull never held it.
A `notes` row puts a NOTE chip and its words on one real trade, found by strategy family and entry minute.
No code ship is needed to add more; the page reads the doc when the board first draws (REFRESH re-reads it).

  python tools/qb_annot.py import-missed <csv> --leg ORB --leg-id ORB_R6 --note "MISSED - ..." --from <LANE>
      replaces every missed row of that leg with the CSV's rows. CSV columns (ORB's orb_missed_trades.csv):
      date, side, entry_time_et, entry_px, exit_time_et, exit_px, pnl_per_sh, pnl_10sh, reason
  python tools/qb_annot.py note --leg ORB --entry "2026-09-18 15:50" "words" --from <LANE>
  python tools/qb_annot.py list

Credentials: serviceAccount.json at the repo root, else the shared checkout's (same lookup as tools/runboard_watch.py).
Never print, copy or commit the credentials.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
SHARES = 10


def real_client():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred):
        cred = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


def _ref(db):
    return db.collection("users").document(UID).collection("meta").document("qb_annot")


def _read(db):
    snap = _ref(db).get()
    d = snap.to_dict() if snap.exists else None
    d = d or {}
    d.setdefault("missed", [])
    d.setdefault("notes", [])
    return d


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def missed_rows(path, leg, leg_id, note):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            side = str(r.get("side", "")).strip().lower()
            if side not in ("long", "short"):
                raise SystemExit("bad side %r on %s" % (side, r.get("date")))
            en, ex = str(r["entry_time_et"]).strip(), str(r["exit_time_et"]).strip()
            for s in (en, ex):
                dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            ps = _num(r.get("pnl_per_sh"))
            usd = _num(r.get("pnl_10sh"))
            out.append({"leg": leg, "leg_id": leg_id, "side": side, "shares": SHARES,
                        "entry_ts": en, "entry_px": _num(r.get("entry_px")),
                        "exit_ts": ex, "exit_px": _num(r.get("exit_px")),
                        "pnl_ps": ps, "pnl_usd": usd if usd is not None else (round(ps * SHARES, 2) if ps is not None else None),
                        "exit_reason": "EOD (engine)" if "eod" in str(r.get("reason", "")).lower() else "engine exit",
                        "note": note, "why": str(r.get("reason", "")).strip()})
    return out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("import-missed")
    a.add_argument("csv")
    a.add_argument("--leg", required=True, help="the family key the board uses (ORB, NOISE, DIP, ENGUQ)")
    a.add_argument("--leg-id", default="", help="the box's leg id, kept for the record (ORB_R6)")
    a.add_argument("--note", required=True)
    a.add_argument("--from", dest="by", required=True)
    n = sub.add_parser("note")
    n.add_argument("--leg", required=True)
    n.add_argument("--entry", required=True, help="the trade's entry time, ET, to the minute: 'YYYY-MM-DD HH:MM'")
    n.add_argument("text")
    n.add_argument("--from", dest="by", required=True)
    sub.add_parser("list")
    args = ap.parse_args(argv)
    db = real_client()
    d = _read(db)
    if args.cmd == "list":
        print(json.dumps(d, indent=1, default=str))
        return 0
    if args.cmd == "import-missed":
        rows = missed_rows(args.csv, args.leg, args.leg_id, args.note)
        d["missed"] = [m for m in d["missed"] if m.get("leg") != args.leg] + rows
        d["missed"].sort(key=lambda m: str(m.get("entry_ts", "")))
        print("%d missed %s rows, engine net %+.2f at %d sh (counted nowhere)"
              % (len(rows), args.leg, sum(m["pnl_usd"] or 0 for m in rows), SHARES))
    else:
        dt.datetime.strptime(args.entry, "%Y-%m-%d %H:%M")
        d["notes"] = [x for x in d["notes"] if not (x.get("leg") == args.leg and str(x.get("entry_ts", ""))[:16] == args.entry)]
        d["notes"].append({"leg": args.leg, "entry_ts": args.entry, "note": args.text})
        print("note on %s %s" % (args.leg, args.entry))
    d["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    d["by"] = args.by
    _ref(db).set(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
