"""Remove sim/demo/paper-account round-trips from the REAL trade journal.

The NinjaTrader AddOn records fills for EVERY account, including the paper-trading
system's DEMO port target. api/nt_sync.py filters those out at import time
(SIM_ACCOUNT_RE), but that filter landed after some paper fills had already been
written — this cleans up the ones already in Firestore.

    python -m tools.purge_sim_trades --dry-run     # list what would go
    python -m tools.purge_sim_trades               # delete them

Deletes nothing that nt_sync would import today: the match rule is the exact same
SIM_ACCOUNT_RE the importer uses.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.nt_sync import SIM_ACCOUNT_RE  # noqa: E402  — one source of truth

DEFAULT_CRED = "serviceAccount.json"
DEFAULT_UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", default=DEFAULT_CRED)
    ap.add_argument("--uid", default=DEFAULT_UID)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(a.cred))
    db = firestore.client()

    col = db.collection("users").document(a.uid).collection("trades")
    hits = []
    for d in col.stream():
        t = d.to_dict() or {}
        acct = str(t.get("account") or "")
        if SIM_ACCOUNT_RE.match(acct):
            hits.append((d.reference, d.id, acct, t.get("date"),
                         t.get("symbol"), t.get("pnl")))

    if not hits:
        print("clean — no sim/demo trades in the journal")
        return

    total = sum(float(h[5] or 0) for h in hits)
    print(f"{len(hits)} paper trade(s) in the real journal "
          f"(fake P&L {total:+,.2f}):")
    for _, did, acct, date, sym, pnl in sorted(hits, key=lambda h: str(h[3])):
        print(f"   {date}  {sym:<6} {acct:<14} {float(pnl or 0):>10,.2f}   {did}")

    if a.dry_run:
        print("\n--dry-run: nothing deleted")
        return

    for ref, *_ in hits:
        ref.delete()
    print(f"\ndeleted {len(hits)} paper trade(s) from users/{a.uid}/trades")


if __name__ == "__main__":
    main()
