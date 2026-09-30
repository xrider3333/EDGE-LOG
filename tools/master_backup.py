r"""BACKUP COVER FOR THE MASTERS: a daily manifest, and a weekly copy to the external drive.

WHY THIS EXISTS (owner GO 2026-09-30 evening). The nightly backup zips ~11 MB of untracked
working files and deliberately leaves the 3.08 GB of master CSVs out. That was a reasoned
choice - masters are derived data - but it meant that when NOADJ_NQ_5m_ETH silently lost
517,539 rows on 2026-09-29 there was no copy to restore from. It was only recoverable because
an ADJ_ twin happened to have been rebuilt the day before. Two cheap things close that:

  1. A DAILY MANIFEST (a few KB). Row count, first and last bar, size and mtime for every
     registered master, written next to the other backups and diffed against the previous
     one. A silent shrink becomes a line of text the next morning. This is the part that
     actually catches the failure - the write guard in augur_engine/master_write.py stops a
     shrink at the source, and this notices if one ever gets through anyway.

  2. A WEEKLY FULL COPY to the external drive, when one is attached, keeping the LAST TWO
     copies. ~6.2 GB for two. No drive attached is the normal case and is not an error.

DESIGN NOTE: this runs INSIDE the existing nightly job (no new scheduled task). It must never
be able to fail that job, so every step is wrapped and the exit code is 0 unless --strict is
passed. A backup that breaks the backup is worse than no backup.

    python tools/master_backup.py --nightly          # what the nightly job calls
    python tools/master_backup.py --manifest         # manifest + diff only
    python tools/master_backup.py --weekly-copy      # force the copy, ignoring the 7-day gate
    python tools/master_backup.py --nightly --dry-run
"""
import argparse
import datetime as dt
import glob
import json
import os
import shutil
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_UP = os.path.join(ROOT, "augur_uploads")
DEFAULT_DB = os.path.join(ROOT, "optimizer_history.db")
DEFAULT_DEST = r"C:\Users\xride\OneDrive\Backups\edgelog"
KEEP_MANIFESTS = 30
KEEP_COPIES = 2
COPY_EVERY_DAYS = 7


# ----------------------------------------------------------------------- the manifest

def master_rows(db):
    """(filename, instrument, timeframe, session, source) for every registered master."""
    conn = sqlite3.connect(db, timeout=120)
    try:
        conn.execute("PRAGMA busy_timeout=120000")
        return conn.execute(
            "SELECT filename, instrument, timeframe, session, source FROM csv_files "
            "WHERE is_master=1 ORDER BY filename").fetchall()
    finally:
        conn.close()


def describe_master(path):
    """Rows, first and last bar, bytes - or an error string. Reads one column, not the file."""
    try:
        t = pd.read_csv(path, usecols=["time"])["time"]
        if not len(t):
            return dict(error="no rows")
        first = pd.to_datetime(int(t.min()), unit="s", utc=True).tz_convert("US/Eastern")
        last = pd.to_datetime(int(t.max()), unit="s", utc=True).tz_convert("US/Eastern")
        return dict(rows=len(t), first=str(first)[:16], last=str(last)[:16],
                    bytes=os.path.getsize(path))
    except Exception as e:
        return dict(error="%s: %s" % (type(e).__name__, e))


def build_manifest(uploads=DEFAULT_UP, db=DEFAULT_DB):
    out = {"written": dt.datetime.now().isoformat(timespec="seconds"), "masters": {}}
    for fn, inst, tf, sess, src in master_rows(db):
        p = os.path.join(uploads, fn)
        entry = dict(instrument=inst, timeframe=tf, session=sess, source=src)
        entry.update(describe_master(p) if os.path.exists(p) else dict(error="file missing"))
        out["masters"][fn] = entry
    return out


def previous_manifest(dest=DEFAULT_DEST):
    """The most recent manifest already on disk, or None."""
    files = sorted(glob.glob(os.path.join(dest, "master_manifest-*.json")))
    for p in reversed(files):
        try:
            with open(p, encoding="utf-8") as fh:
                return os.path.basename(p), json.load(fh)
        except Exception:
            continue
    return None


def compare(old, new):
    """Plain-English lines for anything that got worse. Empty list means nothing did.

    A master GROWING is the normal case and is not reported - the point is to make a loss
    impossible to miss, not to produce a diff nobody reads.
    """
    lines = []
    o, n = old.get("masters", {}), new.get("masters", {})
    for fn in sorted(set(o) | set(n)):
        a, b = o.get(fn), n.get(fn)
        if a and not b:
            lines.append("%s: was in the last manifest and is no longer registered" % fn)
            continue
        if b and not a:
            continue                                  # new master, nothing to compare
        if b.get("error"):
            lines.append("%s: cannot be read now (%s) - it was %s rows"
                         % (fn, b["error"], a.get("rows", "?")))
            continue
        if a.get("error"):
            continue                                  # was broken, now readable: good news
        if b["rows"] < a["rows"]:
            lines.append("%s: LOST %d rows (%d -> %d)"
                         % (fn, a["rows"] - b["rows"], a["rows"], b["rows"]))
        if b["first"] > a["first"]:
            lines.append("%s: history now starts LATER (%s -> %s)" % (fn, a["first"], b["first"]))
        if b["last"] < a["last"]:
            lines.append("%s: last bar went BACKWARDS (%s -> %s)" % (fn, a["last"], b["last"]))
    return lines


def write_manifest(man, dest=DEFAULT_DEST, dry=False):
    if not dry:
        os.makedirs(dest, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(dest, "master_manifest-%s.json" % stamp)
    if dry:
        return path
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)
    old = sorted(glob.glob(os.path.join(dest, "master_manifest-*.json")))[:-KEEP_MANIFESTS]
    for p in old:
        try:
            os.remove(p)
        except OSError:
            pass
    return path


# ------------------------------------------------------------------ the weekly copy

def find_external_drive():
    """A non-C: fixed or removable drive with room, or None. Mirrors the convention in
    C:\\EdgeLog\\backup_to_external.ps1 - removable preferred, then fixed."""
    try:
        import ctypes
        best = None
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            root = "%s:\\" % letter
            if not os.path.exists(root):
                continue
            kind = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
            if kind not in (2, 3):                     # 2 removable, 3 fixed
                continue
            free = shutil.disk_usage(root).free
            if free < 8 * 1024 ** 3:                   # two copies plus headroom
                continue
            rank = 0 if kind == 2 else 1
            if best is None or rank < best[0]:
                best = (rank, root, free)
        return None if best is None else best[1]
    except Exception:
        return None


def existing_copies(dest_root):
    return sorted(glob.glob(os.path.join(dest_root, "masters-*")))


def copy_due(dest_root, every_days=COPY_EVERY_DAYS):
    """True when the newest copy on the drive is older than `every_days`, or there is none."""
    copies = existing_copies(dest_root)
    if not copies:
        return True
    try:
        newest = max(os.path.getmtime(p) for p in copies)
    except OSError:
        return True
    return (dt.datetime.now().timestamp() - newest) > every_days * 86400


def weekly_copy(uploads=DEFAULT_UP, db=DEFAULT_DB, drive=None, force=False, dry=False):
    """Copy every registered master to <drive>\\EdgeLogMasters\\masters-<stamp>\\.

    Returns a one-line plain-English result. Keeps the last KEEP_COPIES and prunes older ones
    only AFTER the new copy is complete, so a failure never leaves zero copies.
    """
    drive = drive or find_external_drive()
    if not drive:
        return "no external drive attached - nothing copied (this is the normal case)"
    dest_root = os.path.join(drive, "EdgeLogMasters")
    if not force and not copy_due(dest_root):
        newest = max(existing_copies(dest_root), key=os.path.getmtime)
        return ("a copy from %s is less than %d days old, so none was made (%s)"
                % (dt.datetime.fromtimestamp(os.path.getmtime(newest)).strftime("%Y-%m-%d"),
                   COPY_EVERY_DAYS, os.path.basename(newest)))

    files = [fn for (fn, _i, _t, _s, _src) in master_rows(db)
             if os.path.exists(os.path.join(uploads, fn))]
    total = sum(os.path.getsize(os.path.join(uploads, fn)) for fn in files)
    free = shutil.disk_usage(drive).free
    if free < total * 1.1:
        return ("external drive %s has %.1f GB free, which is not enough for %.1f GB of "
                "masters - nothing copied" % (drive, free / 1e9, total / 1e9))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = os.path.join(dest_root, "masters-%s" % stamp)
    if dry:
        return ("WOULD copy %d masters (%.2f GB) to %s, then keep the newest %d of %d"
                % (len(files), total / 1e9, target, KEEP_COPIES,
                   len(existing_copies(dest_root)) + 1))
    os.makedirs(target, exist_ok=True)
    copied = 0
    for fn in files:
        shutil.copy2(os.path.join(uploads, fn), os.path.join(target, fn))
        copied += 1
    # only now is it safe to drop an older copy
    pruned = 0
    for p in existing_copies(dest_root)[:-KEEP_COPIES]:
        try:
            shutil.rmtree(p)
            pruned += 1
        except OSError:
            pass
    return ("copied %d masters (%.2f GB) to %s; %d older copy(ies) pruned, keeping %d"
            % (copied, total / 1e9, target, pruned, KEEP_COPIES))


# ------------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--nightly", action="store_true",
                    help="manifest + diff, then the weekly copy if it is due (what the "
                         "nightly backup job calls)")
    ap.add_argument("--manifest", action="store_true", help="manifest + diff only")
    ap.add_argument("--weekly-copy", action="store_true",
                    help="copy now, ignoring the 7-day gate")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when a master shrank (default is 0, so the nightly backup "
                         "job is never failed by this)")
    ap.add_argument("--uploads", default=DEFAULT_UP)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--drive", default=None)
    a = ap.parse_args(argv)
    if not (a.nightly or a.manifest or a.weekly_copy):
        a.nightly = True

    losses = []
    if a.nightly or a.manifest:
        try:
            man = build_manifest(a.uploads, a.db)
            n = len(man["masters"])
            size = sum(m.get("bytes", 0) for m in man["masters"].values())
            prev = previous_manifest(a.dest)
            path = write_manifest(man, a.dest, a.dry_run)
            print("masters: manifest of %d masters (%.2f GB) -> %s"
                  % (n, size / 1e9, os.path.basename(path)))
            if prev is None:
                print("masters: no earlier manifest to compare against (this is the first)")
            else:
                losses = compare(prev[1], man)
                if losses:
                    print("masters: %d PROBLEM(S) against %s:" % (len(losses), prev[0]))
                    for line in losses:
                        print("masters:   " + line)
                else:
                    print("masters: nothing lost since %s" % prev[0])
        except Exception as e:
            print("masters: manifest FAILED - %s: %s" % (type(e).__name__, e))

    if a.nightly or a.weekly_copy:
        try:
            print("masters: " + weekly_copy(a.uploads, a.db, a.drive,
                                            force=a.weekly_copy, dry=a.dry_run))
        except Exception as e:
            print("masters: external copy FAILED - %s: %s" % (type(e).__name__, e))

    return 1 if (losses and a.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
