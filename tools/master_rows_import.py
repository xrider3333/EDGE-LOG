"""Add exported master rows to THIS box's registry (MANAGER GO 11-20). ADD-ONLY.

For each row of tools/master_rows_export.py's JSON:
  * the file must already sit in --uploads with the SAME sha256, else the row is REFUSED;
  * a row whose filename is already registered here is SKIPPED, never updated;
  * otherwise one csv_files row is inserted (new id, same fields).
--dry-run reports and writes nothing. A backup copy of the registry is taken before any write.

usage: python tools/master_rows_import.py --json rows.json [--db optimizer_history.db] [--uploads augur_uploads] [--dry-run]
"""
import argparse, json, os, shutil, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from master_rows_export import COLS, sha256  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def plan(doc, db, uploads):
    c = sqlite3.connect(db)
    try:
        have = {r[0] for r in c.execute("SELECT filename FROM csv_files")}
    finally:
        c.close()
    add, skip, refuse = [], [], []
    for r in doc.get("rows", []):
        fn = r["filename"]
        p = os.path.join(uploads, fn)
        if fn in have:
            skip.append(fn)
        elif not os.path.exists(p):
            refuse.append("%s: file not in %s" % (fn, uploads))
        elif sha256(p) != r["sha256"]:
            refuse.append("%s: sha256 differs from the export (copy again)" % fn)
        else:
            add.append(r)
    return add, skip, refuse


def apply(add, db):
    shutil.copy2(db, db + ".bak-masterimport-" + time.strftime("%Y%m%d-%H%M%S"))
    c = sqlite3.connect(db)
    try:
        for r in add:
            c.execute("INSERT INTO csv_files (%s) VALUES (%s)" % (",".join(COLS), ",".join("?" * len(COLS))),
                      tuple(r.get(k) for k in COLS))
        c.commit()
    finally:
        c.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--db", default=os.path.join(ROOT, "optimizer_history.db"))
    ap.add_argument("--uploads", default=os.path.join(ROOT, "augur_uploads"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    with open(a.json, encoding="utf-8") as f:
        doc = json.load(f)
    add, skip, refuse = plan(doc, a.db, a.uploads)
    for x in refuse:
        print("REFUSED", x)
    print("add %d, already registered %d, refused %d" % (len(add), len(skip), len(refuse)))
    if add and not a.dry_run:
        apply(add, a.db)
        print("added %d rows" % len(add))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
