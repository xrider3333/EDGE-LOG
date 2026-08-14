"""Print the most recent round-trips in the real journal, newest first.

    python -m tools.show_recent_trades           # last 15
    python -m tools.show_recent_trades --n 40
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_CRED = "serviceAccount.json"
DEFAULT_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", default=DEFAULT_CRED)
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--n", type=int, default=15)
    a = ap.parse_args()

    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(a.cred))
    db = firestore.client()

    col = db.collection("users").document(a.uid).collection("trades")
    rows = [d.to_dict() or {} for d in col.stream()]
    rows.sort(key=lambda t: (str(t.get("date") or ""), str(t.get("entryTime") or "")))

    print(f"{len(rows)} trades in journal — newest {min(a.n, len(rows))}:\n")
    print(f"{'date':<12}{'sym':<7}{'acct':<15}{'entry':>9}{'exit':>9}{'pnl':>11}")
    for t in rows[-a.n:]:
        print(f"{str(t.get('date') or ''):<12}{str(t.get('symbol') or ''):<7}"
              f"{str(t.get('account') or ''):<15}"
              f"{float(t.get('entry') or 0):>9.2f}{float(t.get('exit') or 0):>9.2f}"
              f"{float(t.get('pnl') or 0):>11.2f}")


if __name__ == "__main__":
    main()
