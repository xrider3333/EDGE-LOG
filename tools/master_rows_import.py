"""Add exported master rows to THIS box's registry (MANAGER GO 11-20). ADD-ONLY.

For each row of tools/master_rows_export.py's JSON:
  * the file must already sit in --uploads with the SAME sha256, else the row is REFUSED;
  * a row whose filename is already registered here is SKIPPED, never updated;
  * otherwise one csv_files row is inserted (new id, same fields).
--dry-run reports and writes nothing. A WAL-safe sqlite backup is taken before any write.
Safety (VERIFIER 11-20): --db is REQUIRED and must already exist (never creates an empty registry);
it runs only on a box whose EDGELOG_HOST_TAG is "desktop" unless --allow-untagged-host is given, so
it can never be pointed at the Razer's shared-checkout registry by accident; each insert is
conditional on the filename still being unregistered.

usage: python tools/master_rows_import.py --json rows.json --db <optimizer_history.db> [--uploads augur_uploads] [--dry-run]
"""
import argparse, json, os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from master_rows_export import COLS, sha256  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _open(db):
    """Open an EXISTING registry read-write; a wrong path raises instead of creating a new file."""
    return sqlite3.connect("file:%s?mode=rw" % os.path.abspath(db).replace("\\", "/"), uri=True)


def plan(doc, db, uploads):
    c = _open(db)
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
    """Returns the number of rows actually inserted."""
    c = _open(db)
    try:
        bak = sqlite3.connect(db + ".bak-masterimport-" + time.strftime("%Y%m%d-%H%M%S"))
        try:
            c.backup(bak)                   # sqlite's own backup: consistent under WAL
        finally:
            bak.close()
        n = 0
        for r in add:
            cur = c.execute("INSERT INTO csv_files (%s) SELECT %s WHERE NOT EXISTS "
                            "(SELECT 1 FROM csv_files WHERE filename=?)"
                            % (",".join(COLS), ",".join("?" * len(COLS))),
                            tuple(r.get(k) for k in COLS) + (r["filename"],))
            n += cur.rowcount
        c.commit()
        return n
    finally:
        c.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--db", required=True, help="this box's optimizer_history.db (must exist)")
    ap.add_argument("--allow-untagged-host", action="store_true",
                    help="run on a box whose EDGELOG_HOST_TAG is not 'desktop'")
    ap.add_argument("--uploads", default=os.path.join(ROOT, "augur_uploads"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    tag = (os.environ.get("EDGELOG_HOST_TAG") or "").strip().lower()
    if tag != "desktop" and not a.allow_untagged_host:
        print("REFUSED: EDGELOG_HOST_TAG is %r, not 'desktop' - this import is for the desktop box "
              "(pass --allow-untagged-host to override)" % (tag or "unset"))
        return 2
    if not os.path.exists(a.db):
        print("REFUSED: no registry at %s" % a.db)
        return 2
    with open(a.json, encoding="utf-8") as f:
        doc = json.load(f)
    add, skip, refuse = plan(doc, a.db, a.uploads)
    for x in refuse:
        print("REFUSED", x)
    print("add %d, already registered %d, refused %d" % (len(add), len(skip), len(refuse)))
    if add and not a.dry_run:
        print("added %d rows" % apply(add, a.db))
    return 1 if refuse else 0


if __name__ == "__main__":
    sys.exit(main())
