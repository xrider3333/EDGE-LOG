"""Publish EL's own per-trade candles for the REAL journal (api/trade_bars.py) by hand.

The runner does this on its own after every trade sync; this is for the one-off backfill
and for checking a single trade.

  python tools/trade_bars_publish.py --all            # every real trade (skips published ones)
  python tools/trade_bars_publish.py --id nt_198786494464 --force
  python tools/trade_bars_publish.py --all --dry-run  # build only, write nothing

Run from the SHARED checkout (serviceAccount.json and the masters live there).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--id", action="append", default=[])
    ap.add_argument("--force", action="store_true", help="rebuild even if already published")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uid", default=UID)
    a = ap.parse_args()
    if not (a.all or a.id):
        ap.error("pass --all or --id")
    import firebase_admin
    from firebase_admin import credentials, firestore
    from api import trade_bars
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    firebase_admin.initialize_app(credentials.Certificate(os.path.join(root, "serviceAccount.json")))
    db = firestore.client()
    coll = db.collection("users").document(a.uid).collection("trades")
    if a.id:
        docs = [(i, (coll.document(i).get().to_dict() or {})) for i in a.id]
    else:
        docs = [(s.id, s.to_dict() or {}) for s in coll.stream()]
    n = trade_bars.publish(db, a.uid, docs, dry_run=a.dry_run, force=a.force)
    print(f"{'built' if a.dry_run else 'published'} {n} of {len(docs)} trade(s)")


if __name__ == "__main__":
    main()
