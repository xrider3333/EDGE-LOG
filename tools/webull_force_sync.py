"""Force an immediate Webull pull into the journal, ignoring the daily gate.

Same code path as the web app's "Sync now" button — useful from the shell when the
runner is between passes.

    python -m tools.webull_force_sync
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import webull_sync as W  # noqa: E402

DEFAULT_CRED = "serviceAccount.json"
DEFAULT_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", default=DEFAULT_CRED)
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--keys", default=W.DEFAULT_KEYS)
    a = ap.parse_args()

    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(a.cred))
    db = firestore.client()

    print(f"NY now {W._ny_now():%Y-%m-%d %H:%M}  post-close={W._is_final_time()}")
    r = W.sync_trades(db, a.uid, a.keys, print, force=True)
    print("RESULT", r)


if __name__ == "__main__":
    main()
