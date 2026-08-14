"""Print every stored field for the most recent journal trades.

Use when a number on screen disagrees with the broker — shows fees, gross vs net,
score fields, and sync provenance for each trade.

    python -m tools.show_trade_detail --n 3
    python -m tools.show_trade_detail --symbol XHG
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_CRED = "serviceAccount.json"
DEFAULT_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", default=DEFAULT_CRED)
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--symbol", default=None)
    a = ap.parse_args()

    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(a.cred))
    db = firestore.client()

    col = db.collection("users").document(a.uid).collection("trades")
    rows = []
    for d in col.stream():
        t = d.to_dict() or {}
        t["_id"] = d.id
        rows.append(t)
    rows.sort(key=lambda t: (str(t.get("date") or ""), str(t.get("entryTime") or "")))

    if a.symbol:
        rows = [t for t in rows if str(t.get("symbol") or "").upper() == a.symbol.upper()]
    else:
        rows = rows[-a.n:]

    for t in rows:
        print("=" * 60)
        for k in sorted(t):
            v = t[k]
            print(f"  {k:<20} {json.dumps(v, default=str)}")


if __name__ == "__main__":
    main()
