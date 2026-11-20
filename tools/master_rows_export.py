"""Export master-registry rows + file sha256 for copying masters to another box (MANAGER GO 11-20).

READ-ONLY on the source registry (sqlite opened mode=ro). Writes one JSON: every csv_files row with
is_master=1 whose instrument is not in --skip (default NQ,ES,MNQ,MES - the desktop has those) and
whose file is in --uploads, with the file's sha256 and bytes. The owner carries the files himself
(USB / home network - licensed data, never a cloud link); tools/master_rows_import.py adds the rows
on the other box.

usage: python tools/master_rows_export.py --db <optimizer_history.db> --uploads <augur_uploads> --out rows.json
"""
import argparse, hashlib, json, os, sqlite3

COLS = ("name", "filename", "instrument", "rows", "date_from", "date_to", "created_at", "timeframe",
        "is_master", "source", "provenance", "session")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def export(db, uploads, skip=("NQ", "ES", "MNQ", "MES")):
    c = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    try:
        rows = c.execute("SELECT %s FROM csv_files WHERE is_master=1 ORDER BY instrument, filename"
                         % ",".join(COLS)).fetchall()
    finally:
        c.close()
    out, missing = [], []
    for r in rows:
        d = dict(zip(COLS, r))
        if str(d["instrument"] or "").upper() in skip:
            continue
        p = os.path.join(uploads, d["filename"])
        if not os.path.exists(p):
            missing.append(d["filename"])
            continue
        d["sha256"], d["bytes"] = sha256(p), os.path.getsize(p)
        out.append(d)
    return {"what": "master registry rows to add on another box", "skip": list(skip),
            "rows": out, "not_on_disk_here": missing}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--uploads", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip", default="NQ,ES,MNQ,MES")
    a = ap.parse_args(argv)
    doc = export(a.db, a.uploads, tuple(x.strip().upper() for x in a.skip.split(",") if x.strip()))
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1)
    print("exported %d rows (%.0f MB of files), %d registered but not on disk here"
          % (len(doc["rows"]), sum(r["bytes"] for r in doc["rows"]) / 1e6, len(doc["not_on_disk_here"])))


if __name__ == "__main__":
    main()
