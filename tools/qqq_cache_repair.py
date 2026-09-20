#!/usr/bin/env python3
"""Drop torn-write rows from the QQQ bar cache api/cloud_signal.py reads.

WHY THIS EXISTS (2026-09-20). The cache under EDGELOG_HOME/ohlc is appended by more than
one writer (api/cloud_signal.py writes atomically; tools/qqq_paper.py and hand edits do
not), and on 2026-09-18 a torn write left rows whose `time` is not an epoch second at all
and whose OHLC columns are shifted or NaN:

    QQQ_1m.csv  time=812, 9990234375, 99877929688   (low=194722, high=60669, close NaN)
    QQQ_5m.csv  time=200960, 799926800000           (high=373221, rest NaN)

`load_cached_bars` is a bare read_csv with no validation, so those rows reach the signal
engine; and `tests/test_cloud_signal.py` blew up on them with OutOfBoundsDatetime, which
turned a local data defect into a red push gate for every change on the machine.

A row is KEPT only when `time` parses as an epoch second inside [1e9, 2e9] (2001-09-09 ..
2033-05-18) and open/high/low/close are all present. Kept rows are sorted by time and
de-duplicated on time keeping the LAST, matching how the cache is meant to be appended.

Dry run by default -- nothing is written without --apply, and --apply backs the file up to
<name>.corrupt-<YYYYMMDD-HHMMSS> first and writes through a temp file + os.replace, so an
interrupted repair cannot itself tear the cache.

    python tools/qqq_cache_repair.py                 # report only
    python tools/qqq_cache_repair.py --apply         # back up, then rewrite
    python tools/qqq_cache_repair.py --home D:\tmp   # point at another EDGELOG_HOME
"""
import argparse
import datetime
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

# 2001-09-09 .. 2033-05-18. Wide enough that no real bar is ever rejected, narrow enough
# that a millisecond epoch, a truncated value or a shifted column cannot slip through.
EPOCH_MIN = 1_000_000_000
EPOCH_MAX = 2_000_000_000
OHLC = ["open", "high", "low", "close"]
CACHE_FILES = ("QQQ_1m.csv", "QQQ_5m.csv")


def classify(df):
    """(keep_mask, reasons) for one cache frame. Never raises on junk -- that is the point."""
    t = pd.to_numeric(df.get("time"), errors="coerce")
    in_range = t.between(EPOCH_MIN, EPOCH_MAX)
    have_ohlc = df.reindex(columns=OHLC).notna().all(axis=1)
    reasons = pd.Series("", index=df.index, dtype=object)
    reasons[~in_range] = "time is not an epoch second"
    reasons[in_range & ~have_ohlc] = "missing open/high/low/close"
    return in_range & have_ohlc, reasons


def repair_frame(df):
    """The cleaned frame: sane rows only, sorted by time, one row per timestamp."""
    keep, _ = classify(df)
    out = df[keep].copy()
    out["time"] = pd.to_numeric(out["time"]).astype("int64")
    return out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def _home():
    h = os.environ.get("EDGELOG_HOME")
    if h:
        return h
    return r"C:\EdgeLog" if os.name == "nt" else os.path.expanduser("~/edgelog")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=None, help="EDGELOG_HOME to repair under (default: the usual one)")
    ap.add_argument("--apply", action="store_true", help="actually rewrite (default: report only)")
    a = ap.parse_args(argv)

    ohlc_dir = os.path.join(a.home or _home(), "ohlc")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bad_total = 0
    for name in CACHE_FILES:
        path = os.path.join(ohlc_dir, name)
        if not os.path.exists(path):
            print(f"{name}: not present at {ohlc_dir} -- skipped")
            continue
        df = pd.read_csv(path)
        keep, reasons = classify(df)
        bad = df[~keep]
        bad_total += len(bad)
        print(f"{name}: {len(df)} rows, {len(bad)} malformed")
        for i, row in bad.iterrows():
            print(f"    row {i}: time={row.get('time')!r} -- {reasons[i]}")
        if not len(bad):
            continue
        clean = repair_frame(df)
        dropped_dupes = len(df) - len(bad) - len(clean)
        if dropped_dupes:
            print(f"    (plus {dropped_dupes} duplicate timestamp(s) collapsed)")
        if not a.apply:
            print(f"    would keep {len(clean)} rows -- re-run with --apply to write")
            continue
        backup = f"{path}.corrupt-{stamp}"
        shutil.copy2(path, backup)
        tmp = f"{path}.repair-{stamp}.tmp"
        clean.to_csv(tmp, index=False)
        os.replace(tmp, path)
        print(f"    repaired: {len(clean)} rows kept, backup {os.path.basename(backup)}")
    if not bad_total:
        print("nothing to repair")
    elif not a.apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
