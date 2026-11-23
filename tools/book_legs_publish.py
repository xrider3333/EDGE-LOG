"""Publish the book legs table to the paper page's BOOKS card (owner 11-19).

Reads C:/EdgeLog/manager/open_board/book_legs.json and writes it to Firestore doc
users/{uid}/meta/book_legs, with each leg's classification from api/books_toggle.py
(BOOK_LEG_CLASS) attached as leg["cls"], so the page and the box read one table.

    python tools/book_legs_publish.py --dry-run
    python tools/book_legs_publish.py

Credentials: firebase_admin, serviceAccount.json (same lookup as tools/runboard_watch.py).
Never print, copy or commit the credentials.
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from api import books_toggle  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
SRC = r"C:/EdgeLog/manager/open_board/book_legs.json"


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred):
        cred = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


# owner 11-22: NO GOLD BOOKS - the owner will not use them. A book with a '<key>_nogold' twin, or one that holds a gold leg, is left
# out; the no-gold books that stay lose the words 'no gold' ('20 no gold' -> '20'). The page filters an older doc the same way.
GOLD_LEGS = {"GLDNIGHT"}


def is_gold_book(books, key):
    b = books.get(key) or {}
    if str(key).endswith("_nogold"):
        return False
    if str(key) + "_nogold" in books:
        return True
    return any((l or {}).get("id") in GOLD_LEGS or re.search(r"\bGLD\b", str((l or {}).get("instrument") or ""), re.I)
               for l in b.get("legs") or [])


def drop_gold_books(books):
    out = {}
    for k, b in books.items():
        if is_gold_book(books, k):
            continue
        b = dict(b)
        if isinstance(b.get("row"), str):
            b["row"] = re.sub(r",?\s*no gold\b.*$", "", b["row"], flags=re.I).strip()
        if isinstance(b.get("label"), str):
            b["label"] = re.sub(r"^no gold\s*-\s*", "", b["label"], flags=re.I)
        out[k] = b
    return out


# owner GO board 154 (11-22): NO DUPLICATE BOOKS. Publish ONE book per DD limit (the best raw+ML mix, key '<lim>_nogold_ml';
# where ML does not help the raw no-gold row IS the best mix and is published under that key), ONE '#463 today', and the
# single-leg ML shadow books. Raw-only twins, *_prov*, 35_cons* and 463_nogold are no longer published.
LIMITS = (20, 25, 30, 35, 40, 50)
SHADOW_BOOKS = ("382_keel", "234_gate", "314_gate", "555_keel", "545_keel", "525_hybrid")


def pick_books(books):
    out = {}
    for lim in LIMITS:
        b = books.get("%d_nogold_ml" % lim) or books.get("%d_nogold" % lim)
        if b:
            out["%d_nogold_ml" % lim] = b
    if "463" in books:
        out["463"] = books["463"]
    for k in SHADOW_BOOKS:
        if k in books:
            out[k] = books[k]
    return out


def build(src):
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    books = d.get("books")
    if not isinstance(books, dict) or not books:
        raise ValueError("book_legs.json has no books")
    books = drop_gold_books(pick_books(books))
    unknown = set()
    for key, b in books.items():
        for leg in b.get("legs") or []:
            c = books_toggle.BOOK_LEG_CLASS.get(leg.get("id"))
            if c is None:
                unknown.add(leg.get("id"))
            leg["cls"] = dict(c) if c else {"cls": "grey", "max": "OFF", "reason": "not classified yet"}
    return {"basis": d.get("basis"), "books": books, "gates": dict(books_toggle.GATES),
            "box_version": dict(books_toggle.BOX_VERSION),
            "published_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unknown_legs": sorted(x for x in unknown if x)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--uid", default=UID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="write even when nothing changed")
    a = ap.parse_args(argv)
    doc = build(a.src)
    n = sum(len(b.get("legs") or []) for b in doc["books"].values())
    print(f"book_legs: {len(doc['books'])} books, {n} leg rows, unknown legs: {doc['unknown_legs'] or 'none'}")
    if a.dry_run:
        print(f"DRY RUN -- would write users/{a.uid}/meta/book_legs ({len(json.dumps(doc))} bytes)")
        return 0
    # Firestore Spark caps: write only when the content changed (published_at left out of the hash)
    import hashlib
    h = hashlib.sha256(json.dumps({k: v for k, v in doc.items() if k != "published_at"}, sort_keys=True).encode()).hexdigest()
    hp = os.path.join(r"C:/EdgeLog/shadow_asif", "book_legs_publish.sha")
    old = open(hp).read().strip() if os.path.exists(hp) else ""
    if h == old and not a.force:
        print("book_legs unchanged - nothing written")
        return 0
    _db().collection("users").document(a.uid).collection("meta").document("book_legs").set(doc)
    os.makedirs(os.path.dirname(hp), exist_ok=True)
    open(hp, "w").write(h)
    print(f"wrote users/{a.uid}/meta/book_legs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
