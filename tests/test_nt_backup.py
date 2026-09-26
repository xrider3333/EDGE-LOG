"""Unit tests for api.nt_backup -- the nightly NinjaTrader snapshot.

WHY (2026-09-26): _copytree_lenient() passed onerror= to shutil.copytree(), which this
stdlib does not accept -- every night since 2026-08-14 (bar the very first) raised
TypeError, which aborted run_nightly() before Config.xml/UI.xml/the .cs sources were
copied and before _prune_old_folders() ran (runner.log: "[nt-backup] <date> FAILED:
TypeError: copytree() got an unexpected keyword argument 'onerror'", every date from
2026-08-15 through 2026-09-25). These tests pin: a locked/unreadable file is skipped,
not fatal; one failed step does not stop the later steps or the prune; and the prune
only ever touches folders named exactly YYYY-MM-DD, never a hand-made backup file/dir
that happens to live alongside them in C:\\EdgeLog\\_ntbackup.

Never touches C:\\EdgeLog -- every test points NT_DIR/DEST at tmp_path via monkeypatch,
which is also enforced by the live-system guard in tests/conftest.py.
"""
import datetime
import os
import sqlite3

from api import nt_backup as B


# ── _copy2_lenient / _copytree_lenient: a bad file is skipped, not fatal ──────────────

def test_copy2_lenient_skips_oserror_instead_of_raising(tmp_path, capsys):
    src = tmp_path / "src.txt"
    src.write_text("hi")
    # dst directory doesn't exist -> shutil.copy2 raises FileNotFoundError (an OSError)
    dst = tmp_path / "nowhere" / "dst.txt"
    B._copy2_lenient(str(src), str(dst))   # must not raise
    assert not dst.exists()
    assert "skipped locked/unreadable file" in capsys.readouterr().out


def test_copytree_lenient_copies_readable_files_and_skips_locked_one(tmp_path, capsys, monkeypatch):
    src = tmp_path / "workspaces"
    src.mkdir()
    (src / "good.xml").write_text("<a/>")
    (src / "locked.xml").write_text("<b/>")

    real_copy2 = B.shutil.copy2

    def _flaky_copy2(s, d):
        if os.path.basename(s) == "locked.xml":
            raise PermissionError(13, "in use by another process")
        return real_copy2(s, d)

    monkeypatch.setattr(B.shutil, "copy2", _flaky_copy2)
    dst = tmp_path / "out" / "workspaces"
    B._copytree_lenient(str(src), str(dst))

    assert (dst / "good.xml").exists()
    assert not (dst / "locked.xml").exists()
    assert "skipped locked/unreadable file" in capsys.readouterr().out


def test_copytree_lenient_missing_source_is_a_noop(tmp_path):
    dst = tmp_path / "out"
    B._copytree_lenient(str(tmp_path / "does_not_exist"), str(dst))
    assert not dst.exists()


# ── _prune_old_folders: only exact YYYY-MM-DD dirs, keeps newest N ────────────────────

def _mk_dated(dest, *names):
    for n in names:
        (dest / n).mkdir()


def test_prune_keeps_newest_n_dated_folders_only(tmp_path, monkeypatch):
    dest = tmp_path / "_ntbackup"
    dest.mkdir()
    dated = [f"2026-08-{d:02d}" for d in range(14, 32)]      # 18 dated folders
    _mk_dated(dest, *dated)
    monkeypatch.setattr(B, "DEST", str(dest))
    monkeypatch.setattr(B, "KEEP_DATED_FOLDERS", 14)

    B._prune_old_folders()

    remaining = sorted(p.name for p in dest.iterdir())
    assert remaining == dated[-14:]


def test_prune_never_touches_non_dated_names(tmp_path, monkeypatch):
    """C:\\EdgeLog\\_ntbackup also holds hand-made backups (nt_recover.ps1.bak-*,
    retired_strategies/, rollover-20260915-141002/, *.bak files). Pruning must ignore
    all of them by exact name pattern, even when there are more than KEEP_DATED_FOLDERS
    dated folders to prune."""
    dest = tmp_path / "_ntbackup"
    dest.mkdir()
    dated = [f"2026-08-{d:02d}" for d in range(1, 20)]        # 19 dated folders
    _mk_dated(dest, *dated)
    (dest / "retired_strategies").mkdir()
    (dest / "rollover-20260915-141002").mkdir()
    (dest / "nt_recover.ps1.bak-20260910-120741").write_text("x")
    (dest / "NinjaTrader.Custom.dll.v2.1.bak").write_text("x")
    (dest / "master_b3bf23b6.csv.pre-rebuild-20260909-143941").write_text("x")
    monkeypatch.setattr(B, "DEST", str(dest))
    monkeypatch.setattr(B, "KEEP_DATED_FOLDERS", 14)

    B._prune_old_folders()

    names = {p.name for p in dest.iterdir()}
    assert "retired_strategies" in names
    assert "rollover-20260915-141002" in names
    assert "nt_recover.ps1.bak-20260910-120741" in names
    assert "NinjaTrader.Custom.dll.v2.1.bak" in names
    assert "master_b3bf23b6.csv.pre-rebuild-20260909-143941" in names
    # only the 14 newest dated folders survive
    dated_remaining = sorted(n for n in names if n.startswith("2026-08-"))
    assert dated_remaining == dated[-14:]


def test_prune_below_the_keep_count_deletes_nothing(tmp_path, monkeypatch):
    dest = tmp_path / "_ntbackup"
    dest.mkdir()
    _mk_dated(dest, "2026-09-24", "2026-09-25")
    monkeypatch.setattr(B, "DEST", str(dest))
    monkeypatch.setattr(B, "KEEP_DATED_FOLDERS", 14)
    B._prune_old_folders()
    assert {p.name for p in dest.iterdir()} == {"2026-09-24", "2026-09-25"}


# ── run_nightly(): one failed step must not stop the rest, and prune must always run ──

def _mk_nt_dir(root):
    """A minimal fake NinjaTrader 8 folder: sqlite DB + workspaces + Config/UI.xml +
    one AddOn .cs + one EdgeLog*.cs strategy."""
    (root / "db").mkdir(parents=True)
    con = sqlite3.connect(str(root / "db" / "NinjaTrader.sqlite"))
    con.execute("CREATE TABLE Strategies (Id INTEGER, Classname TEXT, Name TEXT, Userdata BLOB)")
    con.execute("INSERT INTO Strategies VALUES (1, 'EdgeLogNOISE', 'EdgeLogNOISE', NULL)")
    con.commit()
    con.close()
    (root / "workspaces").mkdir()
    (root / "workspaces" / "Untitled 2.xml").write_text("<w/>")
    (root / "Config.xml").write_text("<c/>")
    (root / "UI.xml").write_text("<u/>")
    (root / "bin" / "Custom" / "AddOns").mkdir(parents=True)
    (root / "bin" / "Custom" / "AddOns" / "EdgeLogExport.cs").write_text("// addon")
    (root / "bin" / "Custom" / "Strategies").mkdir(parents=True)
    (root / "bin" / "Custom" / "Strategies" / "EdgeLogNOISE.cs").write_text("// strat")


def test_run_nightly_full_snapshot(tmp_path, monkeypatch):
    nt_dir = tmp_path / "NinjaTrader 8"
    _mk_nt_dir(nt_dir)
    dest = tmp_path / "_ntbackup"
    monkeypatch.setattr(B, "NT_DIR", str(nt_dir))
    monkeypatch.setattr(B, "DEST", str(dest))

    msg = B.run_nightly()

    assert "snapshot complete" in msg
    today = datetime.date.today().isoformat()
    out = dest / today
    assert (out / "NinjaTrader.sqlite").exists()
    assert (out / "edgelog_strategy_rows.json").exists()
    assert (out / "workspaces" / "Untitled 2.xml").exists()
    assert (out / "Config.xml").exists()
    assert (out / "UI.xml").exists()
    assert (out / "src" / "AddOns" / "EdgeLogExport.cs").exists()
    assert (out / "src" / "Strategies" / "EdgeLogNOISE.cs").exists()

    # calling again the same day is a no-op ("already done")
    msg2 = B.run_nightly()
    assert "already done" in msg2


def test_run_nightly_survives_a_locked_workspace_file_and_still_copies_the_rest(tmp_path, monkeypatch, capsys):
    nt_dir = tmp_path / "NinjaTrader 8"
    _mk_nt_dir(nt_dir)
    (nt_dir / "workspaces" / "locked.xml").write_text("<locked/>")
    dest = tmp_path / "_ntbackup"
    monkeypatch.setattr(B, "NT_DIR", str(nt_dir))
    monkeypatch.setattr(B, "DEST", str(dest))

    real_copy2 = B.shutil.copy2

    def _flaky_copy2(s, d):
        if os.path.basename(s) == "locked.xml":
            raise PermissionError(13, "in use by another process")
        return real_copy2(s, d)

    monkeypatch.setattr(B.shutil, "copy2", _flaky_copy2)

    msg = B.run_nightly()

    assert "FAILED" not in msg   # a locked file is not a fatal failure
    today = datetime.date.today().isoformat()
    out = dest / today
    # the good workspace file made it through despite the locked one
    assert (out / "workspaces" / "Untitled 2.xml").exists()
    assert not (out / "workspaces" / "locked.xml").exists()
    # AND the later steps (config, src) still ran
    assert (out / "Config.xml").exists()
    assert (out / "src" / "AddOns" / "EdgeLogExport.cs").exists()


def test_run_nightly_one_failed_step_does_not_block_later_steps_or_prune(tmp_path, monkeypatch):
    """Simulate the exact historical bug: the workspaces copytree step raises. Later
    steps (Config.xml/UI.xml/src) must still run, and pruning must still run."""
    nt_dir = tmp_path / "NinjaTrader 8"
    _mk_nt_dir(nt_dir)
    dest = tmp_path / "_ntbackup"
    dest.mkdir()
    # pre-existing excess of dated folders to prove prune still runs this call
    old_dated = [f"2026-08-{d:02d}" for d in range(1, 20)]
    _mk_dated(dest, *old_dated)
    monkeypatch.setattr(B, "NT_DIR", str(nt_dir))
    monkeypatch.setattr(B, "DEST", str(dest))
    monkeypatch.setattr(B, "KEEP_DATED_FOLDERS", 14)

    def _boom(src, dst):
        raise TypeError("copytree() got an unexpected keyword argument 'onerror'")

    monkeypatch.setattr(B, "_copytree_lenient", _boom)

    msg = B.run_nightly()

    assert "PARTIAL" in msg
    assert "workspaces" in msg
    today = datetime.date.today().isoformat()
    out = dest / today
    assert (out / "Config.xml").exists()
    assert (out / "UI.xml").exists()
    assert (out / "src" / "AddOns" / "EdgeLogExport.cs").exists()
    assert (out / "NinjaTrader.sqlite").exists()
    # prune ran: today's new folder plus the 19 old ones is 20 dated folders total,
    # so only the newest 14 (today + the 13 newest old ones) survive.
    remaining = {p.name for p in dest.iterdir()}
    assert today in remaining
    assert len(remaining) == 14


def test_run_nightly_no_sqlite_db_still_copies_everything_else(tmp_path, monkeypatch):
    nt_dir = tmp_path / "NinjaTrader 8"
    _mk_nt_dir(nt_dir)
    os.remove(nt_dir / "db" / "NinjaTrader.sqlite")
    dest = tmp_path / "_ntbackup"
    monkeypatch.setattr(B, "NT_DIR", str(nt_dir))
    monkeypatch.setattr(B, "DEST", str(dest))

    msg = B.run_nightly()

    today = datetime.date.today().isoformat()
    out = dest / today
    assert not (out / "NinjaTrader.sqlite").exists()
    assert (out / "Config.xml").exists()
    assert (out / "src" / "AddOns" / "EdgeLogExport.cs").exists()
