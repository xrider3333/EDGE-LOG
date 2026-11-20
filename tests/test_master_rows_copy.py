import json, sqlite3
from tools import master_rows_export as E, master_rows_import as I

SCHEMA = ("CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name, filename, instrument, rows, date_from, "
          "date_to, created_at, timeframe, is_master, source, provenance, session)")


def _db(p, rows):
    c = sqlite3.connect(p); c.execute(SCHEMA)
    for r in rows:
        c.execute("INSERT INTO csv_files (name,filename,instrument,is_master,source,session,timeframe) "
                  "VALUES (?,?,?,?,?,?,?)", r)
    c.commit(); c.close()


def test_export_then_add_only_import(tmp_path):
    src, up = tmp_path / "src.db", tmp_path / "up"
    up.mkdir()
    (up / "q.csv").write_text("time\n1\n"); (up / "nq.csv").write_text("x")
    _db(src, [("QQQ", "q.csv", "QQQ", 1, "alpaca_split_rth", "rth", "5m"),
              ("NQ", "nq.csv", "NQ", 1, "db", "eth", "5m"),
              ("GLD", "gone.csv", "GLD", 1, "alpaca_split_rth", "rth", "5m")])
    doc = E.export(str(src), str(up))
    assert [r["filename"] for r in doc["rows"]] == ["q.csv"] and doc["not_on_disk_here"] == ["gone.csv"]
    dst = tmp_path / "dst.db"; _db(dst, [])
    add, skip, ref = I.plan(doc, str(dst), str(up))
    assert len(add) == 1 and not skip and not ref
    I.apply(add, str(dst))
    add2, skip2, _ = I.plan(doc, str(dst), str(up))      # second run: nothing new, nothing updated
    assert not add2 and skip2 == ["q.csv"]


def test_sha_mismatch_is_refused(tmp_path):
    up = tmp_path / "up"; up.mkdir(); (up / "q.csv").write_text("changed")
    dst = tmp_path / "dst.db"; _db(dst, [])
    doc = {"rows": [{"filename": "q.csv", "sha256": "0" * 64}]}
    add, _, ref = I.plan(doc, str(dst), str(up))
    assert not add and "sha256" in ref[0]
