"""Nightly NinjaTrader backup — makes the 2026-08-14 wipe a non-event.

WHY THIS EXISTS (2026-08-14). NinjaTrader 8's own auto-update silently deleted
every NinjaScript strategy instance (the rows in the sqlite `Strategies` table)
with no warning, and re-adding them by hand — reattaching each strategy to its
account, re-entering every parameter — cost an entire evening. There was no
backup to restore from; only a hand-made snapshot (C:\\EdgeLog\\_ntbackup\\2026-08-14\\,
taken with the sqlite3 `backup()` API so the open, WAL-mode NinjaTrader.sqlite
doesn't tear) made recovery possible at all.

This module makes that snapshot automatic and nightly, so a future wipe is a
five-minute restore instead of a lost evening:
  1. Copy the DB back: db\\NinjaTrader.sqlite -> NinjaTrader 8\\db\\NinjaTrader.sqlite
     (with NT closed), or at minimum re-add the strategy rows shown in
     edgelog_strategy_rows.json (Classname/Name/Userdata are the parameters).
  2. Restore workspaces\\ and Config.xml/UI.xml if the workspace layout is also gone.
  3. Restart NinjaTrader.

Snapshot contents per dated folder (C:\\EdgeLog\\_ntbackup\\YYYY-MM-DD\\):
  - NinjaTrader.sqlite         (sqlite3 backup() API — safe against the live lock)
  - workspaces\\                (full tree copy)
  - Config.xml, UI.xml
  - bin\\Custom\\AddOns\\*.cs and bin\\Custom\\Strategies\\EdgeLog*.cs (source we wrote)
  - edgelog_strategy_rows.json (Id/Classname/Name/Userdata for every EdgeLog* strategy,
    extracted straight from the Strategies table — the fastest path to manual re-add)

Idempotent: if today's dated folder already exists, run_nightly() does nothing and
reports "already done" — safe to call every loop tick without re-copying gigabytes.
Retention: keeps the newest 14 dated folders, deletes older ones.

Everything here is exception-proof: a backup job must never take down the watch loop.
"""
import base64
import datetime
import glob
import os
import shutil
import sqlite3

NT_DIR = r"C:\Users\xride\Documents\NinjaTrader 8"
DEST = r"C:\EdgeLog\_ntbackup"

KEEP_DATED_FOLDERS = 14


def _backup_sqlite(src_path, dst_path):
    """Copy a live (possibly WAL-locked) sqlite DB using the backup() API, which
    NinjaTrader itself can keep writing through — a plain file copy can tear."""
    src = sqlite3.connect(src_path)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _extract_strategy_rows(sqlite_path, out_json_path):
    """Pull every EdgeLog* strategy row out of the Strategies table into a plain
    JSON file — same shape as the reference backup at
    C:\\EdgeLog\\_ntbackup\\2026-08-14\\edgelog_strategy_rows.json, so a human (or a
    future script) can read off Classname/Name/Userdata without opening NinjaTrader
    or a sqlite browser at all."""
    con = sqlite3.connect(sqlite_path)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT Id, Classname, Name, Userdata FROM Strategies "
            "WHERE Name LIKE 'EdgeLog%' OR Classname LIKE '%EdgeLog%'")
        rows = []
        for _id, classname, name, userdata in cur.fetchall():
            blob = bytes(userdata) if userdata is not None else b""
            b64 = base64.b64encode(blob).decode("ascii")
            try:
                utf16_text = blob.decode("utf-16")[:400]
            except Exception:
                utf16_text = ""
            rows.append({
                "Id": _id,
                "Classname": classname,
                "Name": name,
                "Userdata_b64": b64,
                "Userdata_utf16": utf16_text,
            })
    finally:
        con.close()
    import json
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    return len(rows)


def _copy2_lenient(src, dst):
    """copy_function for shutil.copytree(): behaves like shutil.copy2, but a locked
    or unreadable file (NT can hold files open while running) is logged and skipped
    instead of raising. This is the version-stable way to make copytree() tolerate a
    bad file -- copytree()'s own `onerror` hook fires for errors in the DIRECTORY
    WALK (os.scandir/os.makedirs), not for a failed per-file copy, and this stdlib's
    shutil.copytree() does not accept an `onerror` keyword argument at all. Passing
    one (the previous approach here) raised TypeError on every single run, which
    aborted run_nightly() before Config.xml/UI.xml/the .cs sources were ever copied
    and before _prune_old_folders() ran -- every night since 2026-08-14 except the
    very first (see runner.log)."""
    try:
        shutil.copy2(src, dst)
    except OSError as e:
        print(f"[nt-backup] skipped locked/unreadable file: {src}: {type(e).__name__}: {e}")


def _copytree_lenient(src, dst):
    """shutil.copytree using _copy2_lenient so a locked/in-use file is skipped rather
    than aborting the whole snapshot. Also swallows shutil.Error/OSError raised by the
    directory walk itself (e.g. a folder vanishing mid-copy), so this one step can
    never take down the rest of run_nightly()."""
    if not os.path.isdir(src):
        return
    try:
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore_dangling_symlinks=True,
                         copy_function=_copy2_lenient)
    except (shutil.Error, OSError) as e:
        print(f"[nt-backup] copytree {src} -> {dst} failed: {type(e).__name__}: {e}")


def _copy_file_lenient(src, dst):
    try:
        if os.path.exists(src):
            shutil.copy2(src, dst)
    except Exception as e:
        print(f"[nt-backup] skipped {src}: {type(e).__name__}: {e}")


def _prune_old_folders():
    """Keep only the newest KEEP_DATED_FOLDERS dated snapshot folders."""
    if not os.path.isdir(DEST):
        return
    dated = []
    for name in os.listdir(DEST):
        full = os.path.join(DEST, name)
        if os.path.isdir(full):
            try:
                datetime.date.fromisoformat(name)
                dated.append(name)
            except ValueError:
                continue
    dated.sort()
    excess = dated[:-KEEP_DATED_FOLDERS] if len(dated) > KEEP_DATED_FOLDERS else []
    for name in excess:
        full = os.path.join(DEST, name)
        try:
            shutil.rmtree(full, ignore_errors=True)
            print(f"[nt-backup] pruned old snapshot {name}")
        except Exception as e:
            print(f"[nt-backup] prune failed for {name}: {type(e).__name__}: {e}")


def run_nightly():
    """Take tonight's snapshot if it doesn't already exist. Idempotent, never raises.
    Returns a one-line summary string."""
    today = datetime.date.today().isoformat()
    out_dir = os.path.join(DEST, today)
    if os.path.isdir(out_dir):
        msg = f"[nt-backup] {today} already done -- skipping"
        print(msg)
        return msg
    n_rows = 0
    n_src = 0
    failed_steps = []

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        # Can't even create tonight's folder -- nothing below can run, but leave
        # out_dir absent so the idempotency check at the top retries next loop tick.
        msg = f"[nt-backup] {today} FAILED: {type(e).__name__}: {e}"
        print(msg)
        return msg

    # Each step below is independent -- one failing (a locked file, a missing NT
    # folder, a bad sqlite read) must never stop the LATER steps from running, and
    # must never stop _prune_old_folders() from running at the end. This is the fix
    # for the 2026-08-15..2026-09-25 outage: the old code had one big try/except
    # around the whole body, so the workspaces copytree()'s TypeError skipped
    # Config.xml/UI.xml/the .cs sources AND the prune, every single night.

    db_src = os.path.join(NT_DIR, "db", "NinjaTrader.sqlite")
    db_dst = os.path.join(out_dir, "NinjaTrader.sqlite")
    if os.path.exists(db_src):
        try:
            _backup_sqlite(db_src, db_dst)
            n_rows = _extract_strategy_rows(
                db_dst, os.path.join(out_dir, "edgelog_strategy_rows.json"))
        except Exception as e:
            failed_steps.append("sqlite")
            print(f"[nt-backup] sqlite snapshot failed: {type(e).__name__}: {e}")
    else:
        print(f"[nt-backup] no sqlite DB found at {db_src}")

    try:
        _copytree_lenient(os.path.join(NT_DIR, "workspaces"),
                           os.path.join(out_dir, "workspaces"))
    except Exception as e:
        failed_steps.append("workspaces")
        print(f"[nt-backup] workspaces copy failed: {type(e).__name__}: {e}")

    try:
        _copy_file_lenient(os.path.join(NT_DIR, "Config.xml"),
                            os.path.join(out_dir, "Config.xml"))
        _copy_file_lenient(os.path.join(NT_DIR, "UI.xml"),
                            os.path.join(out_dir, "UI.xml"))
    except Exception as e:
        failed_steps.append("config")
        print(f"[nt-backup] Config.xml/UI.xml copy failed: {type(e).__name__}: {e}")

    try:
        addons_dir = os.path.join(NT_DIR, "bin", "Custom", "AddOns")
        strategies_dir = os.path.join(NT_DIR, "bin", "Custom", "Strategies")
        src_out = os.path.join(out_dir, "src")
        os.makedirs(src_out, exist_ok=True)
        for pattern, subdir in ((os.path.join(addons_dir, "*.cs"), "AddOns"),
                                 (os.path.join(strategies_dir, "EdgeLog*.cs"), "Strategies")):
            for path in glob.glob(pattern):
                dest_subdir = os.path.join(src_out, subdir)
                os.makedirs(dest_subdir, exist_ok=True)
                _copy_file_lenient(path, os.path.join(dest_subdir, os.path.basename(path)))
                n_src += 1
    except Exception as e:
        failed_steps.append("src")
        print(f"[nt-backup] .cs source copy failed: {type(e).__name__}: {e}")

    # Pruning runs no matter what happened above -- it is the step that reclaims
    # disk, and it must not be starved by an earlier failure the way it was here.
    try:
        _prune_old_folders()
    except Exception as e:
        failed_steps.append("prune")
        print(f"[nt-backup] prune step failed: {type(e).__name__}: {e}")

    if failed_steps:
        msg = (f"[nt-backup] {today} snapshot PARTIAL -- "
               f"{n_rows} EdgeLog strategy row(s), {n_src} .cs source file(s) -- "
               f"failed step(s): {', '.join(failed_steps)}")
    else:
        msg = (f"[nt-backup] {today} snapshot complete -- "
               f"{n_rows} EdgeLog strategy row(s), {n_src} .cs source file(s)")
    print(msg)
    return msg


if __name__ == "__main__":
    print(run_nightly())
