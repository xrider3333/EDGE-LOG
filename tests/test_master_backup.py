r"""Backup cover for the masters: the daily manifest, and the weekly external copy.

WHY THIS EXISTS (owner GO 2026-09-30). The nightly backup zips ~11 MB of untracked working
files and deliberately excludes the 3.08 GB of masters. So when NOADJ_NQ_5m_ETH silently lost
517,539 rows on 2026-09-29, nothing had a copy - it was recoverable only because an ADJ_ twin
had been rebuilt the day before. The manifest is the cheap half of the fix: a few KB a night
that turns a silent shrink into a line of text. The write guard stops a shrink at the source;
this notices if one ever gets through anyway.

THE RULE THIS FILE PROTECTS ABOVE ALL: **a backup must never be able to fail the backup job.**
It runs inside the existing nightly task, so an unreadable master, a missing file, a full disk
or a locked registry has to produce a REPORTED line and exit 0.
"""
import json
import os
import sqlite3
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import master_backup as mb  # noqa: E402


@pytest.fixture()
def lib(tmp_path):
    """A tiny master library: a registry plus two master CSVs on disk."""
    up = tmp_path / "uploads"
    up.mkdir()
    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
        instrument TEXT, timeframe TEXT, rows INT, date_from TEXT, date_to TEXT,
        created_at TEXT, is_master INT, source TEXT, provenance TEXT, session TEXT)""")
    for fn, inst in (("A.csv", "NQ"), ("B.csv", "ES")):
        conn.execute("INSERT INTO csv_files (filename,instrument,timeframe,is_master,source,session) "
                     "VALUES (?,?,'5m',1,'db_noadj_rth','rth')", (fn, inst))
        _write(up / fn, 100)
    conn.commit()
    conn.close()
    return dict(up=str(up), db=db, dest=str(tmp_path / "dest"))


def _write(path, n, start=1_700_000_000):
    pd.DataFrame({"time": [start + i * 300 for i in range(n)],
                  "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                  "volume": 7}).to_csv(path, index=False)


# ------------------------------------------------------------------- the manifest itself

def test_the_manifest_records_what_a_loss_would_change(lib):
    man = mb.build_manifest(lib["up"], lib["db"])
    assert set(man["masters"]) == {"A.csv", "B.csv"}
    e = man["masters"]["A.csv"]
    for field in ("rows", "first", "last", "bytes", "instrument", "timeframe", "source"):
        assert field in e, field
    assert e["rows"] == 100


def test_it_is_small_enough_to_keep_every_night(lib):
    """The whole argument for a daily manifest is that it costs nothing."""
    p = mb.write_manifest(mb.build_manifest(lib["up"], lib["db"]), lib["dest"])
    assert os.path.getsize(p) < 64 * 1024


def test_a_shrink_is_reported_in_plain_english(lib):
    old = mb.build_manifest(lib["up"], lib["db"])
    _write(os.path.join(lib["up"], "A.csv"), 40)              # lost 60 rows
    new = mb.build_manifest(lib["up"], lib["db"])
    lines = mb.compare(old, new)
    # Truncating the tail loses rows AND moves the last bar back, so both are reported - that
    # is right, not noise: either one alone would also be worth a look.
    assert any("LOST 60 rows" in x and "100 -> 40" in x for x in lines), lines
    assert all("A.csv" in x for x in lines)


def test_the_real_incident_shape_is_caught(lib):
    """NOADJ_NQ_5m_ETH kept its first and last bar and lost the middle, so a date-range check
    saw nothing wrong - that is exactly why the manifest counts ROWS, not just dates."""
    old = mb.build_manifest(lib["up"], lib["db"])
    p = os.path.join(lib["up"], "A.csv")
    d = pd.read_csv(p)
    holed = pd.concat([d.iloc[:20], d.iloc[-2:]], ignore_index=True)   # same span, fewer rows
    holed.to_csv(p, index=False)
    new = mb.build_manifest(lib["up"], lib["db"])
    assert new["masters"]["A.csv"]["first"] == old["masters"]["A.csv"]["first"]
    assert new["masters"]["A.csv"]["last"] == old["masters"]["A.csv"]["last"]
    lines = mb.compare(old, new)
    assert lines and "LOST" in lines[0], "a hole with unchanged endpoints must still be caught"


def test_history_starting_later_is_reported(lib):
    old = mb.build_manifest(lib["up"], lib["db"])
    _write(os.path.join(lib["up"], "A.csv"), 100, start=1_800_000_000)
    lines = mb.compare(old, mb.build_manifest(lib["up"], lib["db"]))
    assert any("starts LATER" in x for x in lines)


def test_a_master_that_became_unreadable_is_reported(lib):
    old = mb.build_manifest(lib["up"], lib["db"])
    open(os.path.join(lib["up"], "A.csv"), "wb").write(b"\x00\x01 rubbish")
    lines = mb.compare(old, mb.build_manifest(lib["up"], lib["db"]))
    assert any("A.csv" in x and "cannot be read" in x for x in lines)


def test_a_missing_file_is_reported_not_skipped(lib):
    old = mb.build_manifest(lib["up"], lib["db"])
    os.remove(os.path.join(lib["up"], "A.csv"))
    new = mb.build_manifest(lib["up"], lib["db"])
    assert new["masters"]["A.csv"]["error"] == "file missing"
    assert mb.compare(old, new)


def test_growth_is_not_reported(lib):
    """A diff that fires every night is a diff nobody reads."""
    old = mb.build_manifest(lib["up"], lib["db"])
    _write(os.path.join(lib["up"], "A.csv"), 140)
    assert mb.compare(old, mb.build_manifest(lib["up"], lib["db"])) == []


def test_a_brand_new_master_is_not_a_problem(lib):
    old = mb.build_manifest(lib["up"], lib["db"])
    conn = sqlite3.connect(lib["db"])
    conn.execute("INSERT INTO csv_files (filename,instrument,timeframe,is_master,source,session) "
                 "VALUES ('C.csv','GC','5m',1,'db_noadj_rth','rth')")
    conn.commit(); conn.close()
    _write(os.path.join(lib["up"], "C.csv"), 30)
    assert mb.compare(old, mb.build_manifest(lib["up"], lib["db"])) == []


def test_old_manifests_are_pruned_to_the_keep_limit(lib, monkeypatch):
    monkeypatch.setattr(mb, "KEEP_MANIFESTS", 3)
    man = mb.build_manifest(lib["up"], lib["db"])
    os.makedirs(lib["dest"], exist_ok=True)
    # Distinct stamps by hand: six real writes inside one second would collide on the
    # timestamp and overwrite each other, which would test nothing.
    for day in range(1, 7):
        with open(os.path.join(lib["dest"], "master_manifest-2026090%d-000000.json" % day),
                  "w", encoding="utf-8") as fh:
            json.dump(man, fh)
    mb.write_manifest(man, lib["dest"])            # the write that triggers the prune
    kept = [f for f in os.listdir(lib["dest"]) if f.startswith("master_manifest-")]
    assert len(kept) == 3, kept


# ----------------------------------------------------------------- the weekly copy

def test_no_external_drive_is_normal_and_not_an_error(lib, monkeypatch):
    monkeypatch.setattr(mb, "find_external_drive", lambda: None)
    msg = mb.weekly_copy(lib["up"], lib["db"])
    assert "no external drive" in msg and "normal case" in msg


def test_the_copy_keeps_only_the_last_two(lib, tmp_path, monkeypatch):
    drive = tmp_path / "ext"
    (drive / "EdgeLogMasters").mkdir(parents=True)
    for old in ("masters-20260901-000000", "masters-20260908-000000", "masters-20260915-000000"):
        (drive / "EdgeLogMasters" / old).mkdir()
    msg = mb.weekly_copy(lib["up"], lib["db"], drive=str(drive), force=True)
    left = sorted(os.listdir(drive / "EdgeLogMasters"))
    assert len(left) == mb.KEEP_COPIES, msg
    assert "pruned" in msg


def test_older_copies_are_pruned_only_after_the_new_one_lands(lib, tmp_path):
    """Pruning first would leave a window with zero copies, which is the moment a failure
    hurts most."""
    src = open(os.path.join(ROOT, "tools", "master_backup.py"), encoding="utf-8").read()
    body = src[src.index("def weekly_copy"):src.index("# ------", src.index("def weekly_copy"))]
    assert body.index("shutil.copy2") < body.index("shutil.rmtree")


def test_every_registered_master_is_copied(lib, tmp_path):
    drive = tmp_path / "ext"
    drive.mkdir()
    mb.weekly_copy(lib["up"], lib["db"], drive=str(drive), force=True)
    got = sorted(os.listdir(next((drive / "EdgeLogMasters").iterdir())))
    assert got == ["A.csv", "B.csv"]


def test_the_seven_day_gate_holds_between_copies(lib, tmp_path):
    drive = tmp_path / "ext"
    root = drive / "EdgeLogMasters"
    root.mkdir(parents=True)
    fresh = root / "masters-20260930-000000"
    fresh.mkdir()
    assert not mb.copy_due(str(root))
    msg = mb.weekly_copy(lib["up"], lib["db"], drive=str(drive), force=False)
    assert "less than" in msg and "none was made" in msg
    os.utime(fresh, (1_600_000_000, 1_600_000_000))
    assert mb.copy_due(str(root))


def test_a_full_drive_is_reported_rather_than_half_copied(lib, tmp_path, monkeypatch):
    drive = tmp_path / "ext"
    drive.mkdir()
    import shutil as sh
    monkeypatch.setattr(mb.shutil, "disk_usage", lambda p: sh._ntuple_diskusage(10, 9, 1))
    msg = mb.weekly_copy(lib["up"], lib["db"], drive=str(drive), force=True)
    assert "not enough" in msg
    assert not os.path.exists(drive / "EdgeLogMasters"), "nothing should have been started"


# ------------------------------------------------- it can never fail the nightly job

def test_an_unreadable_registry_does_not_fail_the_run(tmp_path, capsys):
    rc = mb.main(["--nightly", "--db", str(tmp_path / "nope.db"),
                  "--uploads", str(tmp_path), "--dest", str(tmp_path / "d")])
    assert rc == 0
    assert "FAILED" in capsys.readouterr().out


def test_a_shrink_still_exits_zero_by_default(lib, capsys):
    mb.write_manifest(mb.build_manifest(lib["up"], lib["db"]), lib["dest"])
    _write(os.path.join(lib["up"], "A.csv"), 5)
    rc = mb.main(["--manifest", "--db", lib["db"], "--uploads", lib["up"], "--dest", lib["dest"]])
    out = capsys.readouterr().out
    assert "LOST" in out, "the loss must be reported"
    assert rc == 0, "but it must not fail the nightly backup job"


def test_strict_is_available_for_a_human_run(lib):
    mb.write_manifest(mb.build_manifest(lib["up"], lib["db"]), lib["dest"])
    _write(os.path.join(lib["up"], "A.csv"), 5)
    rc = mb.main(["--manifest", "--strict", "--db", lib["db"],
                  "--uploads", lib["up"], "--dest", lib["dest"]])
    assert rc == 1


def test_a_dry_run_writes_nothing(lib):
    mb.main(["--nightly", "--dry-run", "--db", lib["db"], "--uploads", lib["up"],
             "--dest", lib["dest"]])
    assert not os.path.exists(lib["dest"])


def test_the_manifest_is_written_atomically(lib):
    """It lands in the same OneDrive folder as the other backups, where a torn write would be
    a corrupt record of what the masters looked like."""
    src = open(os.path.join(ROOT, "tools", "master_backup.py"), encoding="utf-8").read()
    body = src[src.index("def write_manifest"):src.index("def find_external_drive")]
    assert "os.replace" in body
