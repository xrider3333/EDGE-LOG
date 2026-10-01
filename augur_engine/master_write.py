"""THE ONE WAY A MASTER CSV GETS WRITTEN.

WHY THIS EXISTS (2026-09-30). NOADJ_NQ_5m_ETH lost 517,539 rows - everything between
2019-05-21 and 2026-09-22 - and the loss survived for a day with the registry agreeing it was
correct. It took two defects, and this module closes both:

  1. A NON-ATOMIC WRITE. `tools/refresh_noadj_yahoo.py` wrote each master with a bare
     `df.to_csv(path)`, straight over the live file. That is a ~34 MB write on a OneDrive-
     synced folder; interrupted partway it leaves a VALID CSV that simply stops early, here
     at 625,491 of 1,144,508 rows. `optimizer.save_master_csv` had already been made atomic
     for exactly this reason - the fix just never reached the standalone tools.
  2. NOTHING NOTICED A MASTER SHRINKING. The next refresh read the 625,491-row stump, saw
     Yahoo's 7-day window as new rows, appended them, and wrote the registry row to match.
     A truncation became a blessed master, and the only reason nothing was corrupted
     downstream is that no job happened to run that night.

So: every write goes to a sibling temp file, is flushed and fsynced, is READ BACK and counted,
and only then renamed over the target. A rename is atomic, so a reader and a kill -9 both see
either the whole old file or the whole new one - never half. And a write that would leave
FEWER rows than the file already on disk - or than the registry's count for that master, when
the caller passes `known_rows` - is refused unless the caller says, in words, why shrinking is
right. The registry comparison matters because the stump was already ON DISK when the next
refresh appended to it, so a disk-only check reads that as growth.

A refused write is not a failure to recover from: the old master stays exactly as it was.
"""
import os
import time
import uuid

import pandas as pd


class MasterShrank(Exception):
    """A write would have dropped rows from a master. The old file is untouched."""


def read_row_count(path):
    """Rows currently on disk, or None when that cannot be established.

    None means UNKNOWN, and a caller must not read it as zero. Zero would make every write
    look like growth, disabling the guard precisely when the file on disk is already damaged -
    and pandas happily parses binary rubbish as a header with no data rows, so "0" is a real
    possible answer here. A master always has rows, so 0 is reported as unknown too.
    """
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return None
        n = len(pd.read_csv(path, usecols=[0]))
        return n or None
    except Exception:
        return None          # unreadable -> unknown, never zero


def write_master_csv(df, path, allow_shrink=False, shrink_reason="", retries=10,
                     known_rows=None):
    """Write `df` to `path` atomically, refusing to lose rows.

    `allow_shrink` must be paired with a `shrink_reason` - a deliberate rebuild says so out
    loud, so that a silent truncation can never borrow the same code path.

    Returns the number of rows written. Raises MasterShrank when the write is refused.
    """
    if df is None:
        raise ValueError("refusing to write an empty master (df is None): %s" % path)
    n_new = len(df)
    if n_new == 0:
        raise MasterShrank("refusing to write ZERO rows over %s" % os.path.basename(path))

    # Compare against the LARGER of what is on disk and the last count we trusted.
    # Comparing only against the file was the hole in the first version (MANAGER review
    # 2026-09-30, finding 6): once a short file is on disk - because another process read
    # it mid-rewrite, or OneDrive restored a stale copy - appending to the stump looks like
    # growth and passes. `known_rows` is the registry's count for this master, which is the
    # last size a complete write recorded, so a truncation cannot launder itself through
    # one bad read.
    n_disk = read_row_count(path)
    n_old = n_disk
    if known_rows:
        n_old = int(known_rows) if n_disk is None else max(n_disk, int(known_rows))
    if n_old is not None and n_new < n_old and not allow_shrink:
        where = "on disk" if (n_disk is not None and n_old == n_disk) else "in the registry"
        raise MasterShrank(
            "refusing to write %s: it would go from %d rows (%s) to %d, losing %d. A master "
            "only ever grows unless a caller states why it should not. If this shrink is "
            "correct, pass allow_shrink=True with a reason."
            % (os.path.basename(path), n_old, where, n_new, n_old - n_new))
    if allow_shrink and n_old is not None and n_new < n_old and not shrink_reason:
        raise ValueError("allow_shrink needs a shrink_reason (writing %s)" % path)

    tmp = "%s.tmp-%s" % (path, uuid.uuid4().hex[:8])
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            df.to_csv(fh, index=False)
            fh.flush()
            os.fsync(fh.fileno())
        # Read the temp file back before it becomes the master. A short write that still
        # parses is the exact failure this module exists for, so counting rows on the file
        # we are about to install is the only check that would have caught it.
        n_disk = read_row_count(tmp)
        if n_disk != n_new:
            raise IOError("wrote %s but it reads back as %s rows, not %s - not installing it"
                          % (os.path.basename(tmp), n_disk, n_new))
        # Windows refuses a rename while another process holds the target open, and five
        # runner processes read these files continuously. Retry briefly; if it never frees,
        # the OLD master stays in place and the caller sees the error.
        for attempt in range(retries):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == retries - 1:
                    raise
                time.sleep(0.4)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return n_new
