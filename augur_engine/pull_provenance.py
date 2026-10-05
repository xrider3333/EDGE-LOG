r"""WHICH PHOTOGRAPH OF THE VENDOR WAS THIS COMPUTED ON?

WHY THIS EXISTS (2026-10-05, MANAGER #53 item 3, from the 10-04 finding). Alpaca computes
`adjustment=split` AT QUERY TIME, and it corrects its own history. Measured: GE's daily bar for
2021-07-30 came back as **12.95 at about 15:45 and 103.60 at about 17:20 the same afternoon** -
the vendor fixed a missed 1-for-8 reverse split between two pulls an hour apart. Both pulls were
faithful to what we were told; they disagree because the thing we were told changed.

So a cache is a PHOTOGRAPH OF THE VENDOR ON THE DAY IT WAS PULLED, not a fact about the market,
and a result computed on one cannot be reproduced without knowing which photograph it used. This
module records that: for every pull, when it happened and a hash of exactly what came back. A
result can then cite its photograph, and a cache that disagrees with a fresh pull can be
recognised as a vendor correction rather than hunted as a loader bug - which is the wrong turn
this finding was about.

WHERE IT HOOKS IN, AND WHY THERE. In `fetch_bars`, the single call every lane goes through. TTM,
TBIS and the ROC-frontier harnesses pull straight into their own research caches and never touch
`upsert_master`, so anything recorded only on the library path would miss exactly the pulls that
matter - that is the limitation the split guard shipped with, and repeating it here would be
careless rather than unlucky.

WHAT IT IS NOT. It does not prevent anything, re-pull anything or judge anything. It is a
notebook. Every write failure is swallowed: a pull that worked must never fail because its
receipt could not be filed.
"""
import hashlib
import json
import os
import time

MANIFEST_NAME = "alpaca_pulls.jsonl"

# How many of a symbol's past pulls to keep when the manifest is trimmed. A pull record is ~250
# bytes, so this is cheap; the cap exists so a nightly refresh cannot grow the file for ever.
KEEP_PER_SERIES = 40


def _home():
    return os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def manifest_path():
    return os.path.join(_home(), "state", MANIFEST_NAME)


def content_hash(df):
    """A sha256 over exactly the bars that came back, and nothing else.

    Canonicalised so the same data always hashes the same: sorted by time, fixed decimal places,
    volume as an integer. It must NOT depend on pandas' dtype choices - pandas 3 changed the
    datetime resolution, and a hash that moved when the library was upgraded would report every
    cache as changed and teach everyone to ignore it.
    """
    if df is None or len(df) == 0:
        return "sha256:empty"
    h = hashlib.sha256()
    try:
        cols = ("time", "open", "high", "low", "close", "volume")
        sub = df[list(cols)].sort_values("time")
        for t, o, hi, lo, c, v in zip(sub["time"], sub["open"], sub["high"],
                                      sub["low"], sub["close"], sub["volume"]):
            h.update(("%d|%.6f|%.6f|%.6f|%.6f|%d\n"
                      % (int(t), float(o), float(hi), float(lo), float(c), int(v)))
                     .encode("ascii"))
    except Exception as e:
        return "sha256:unhashable(%s)" % type(e).__name__
    return "sha256:" + h.hexdigest()


def series_key(symbol, timeframe, adjustment="split", feed="sip"):
    """What counts as "the same series" for comparison purposes.

    `adjustment` is part of it on purpose: a split-adjusted pull and a raw one SHOULD differ, and
    treating them as one series would report that as a vendor change every time.
    """
    return "%s|%s|%s|%s" % (str(symbol).upper(), timeframe, adjustment, feed)


def _row(symbol, timeframe, start, end, adjustment, feed, df, wrote_to=None):
    first = last = None
    try:
        if df is not None and len(df):
            first = int(df["time"].min())
            last = int(df["time"].max())
    except Exception:
        pass
    return {
        "series": series_key(symbol, timeframe, adjustment, feed),
        "symbol": str(symbol).upper(),
        "timeframe": str(timeframe),
        "adjustment": str(adjustment),
        "feed": str(feed),
        "requested_start": str(start),
        "requested_end": str(end),
        "pulled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # SUB-SECOND ON PURPOSE. With whole seconds, two pulls in the same second tie and
        # "the newest pull" becomes whichever one a sort happened to put first - which is
        # exactly what compare_to_fresh asks for. Found by test_history_is_newest_first.
        "pulled_at_epoch": round(time.time(), 6),
        "rows": int(len(df)) if df is not None else 0,
        "first_bar": first,
        "last_bar": last,
        "content_hash": content_hash(df),
        "wrote_to": wrote_to,
    }


def _append(row):
    """Append one record under an OS lock, so five lanes pulling at once cannot interleave.

    Reuses alpaca_rate's lock rather than growing a second locking primitive - and an OS lock
    rather than a flag file, because the kernel releases it when a process dies and there is no
    staleness threshold to misjudge ([[edgelog-cross-process-lock]]).
    """
    path = manifest_path()
    line = json.dumps(row, sort_keys=True) + "\n"
    try:
        from . import alpaca_rate
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with alpaca_rate._lock(path + ".lock") as got:
            # Fail OPEN but do not write unlocked: a torn line would corrupt the record for
            # everybody, and a missing line only costs this one receipt.
            if not got:
                return False
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
        return True
    except Exception:
        return False


def record(symbol, timeframe, start, end, df, adjustment="split", feed="sip", wrote_to=None):
    """File the receipt for one pull. Returns the record, or None if nothing could be filed."""
    try:
        row = _row(symbol, timeframe, start, end, adjustment, feed, df, wrote_to)
    except Exception:
        return None
    _append(row)
    return row


def read_all(path=None):
    """Every record, oldest first. A damaged line is skipped, never raised: this file is a
    notebook, and one smudged entry must not make the rest unreadable."""
    path = path or manifest_path()
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        return []
    return out


def history(symbol, timeframe, adjustment="split", feed="sip", path=None):
    """This series' pulls, NEWEST FIRST.

    Ties on the timestamp fall back to POSITION IN THE FILE, which is the true order: the
    manifest is append-only, so a later line was written later whatever the clock said. Without
    that tie-break two pulls in the same second order arbitrarily and "the latest pull" is a
    coin flip.
    """
    key = series_key(symbol, timeframe, adjustment, feed)
    rows = [(i, r) for i, r in enumerate(read_all(path)) if r.get("series") == key]
    rows.sort(key=lambda p: (p[1].get("pulled_at_epoch") or 0, p[0]), reverse=True)
    return [r for _i, r in rows]


def latest(symbol, timeframe, adjustment="split", feed="sip", path=None):
    rows = history(symbol, timeframe, adjustment, feed, path)
    return rows[0] if rows else None


def changed_between_pulls(symbol, timeframe, adjustment="split", feed="sip", path=None):
    """Did the vendor's answer for this series ever change between two pulls?

    Compares consecutive records with the SAME requested window - a different window naturally
    gives a different hash, and reporting that as a vendor change would be noise that buries the
    real thing. Returns [(older, newer)] pairs, newest first.
    """
    rows = history(symbol, timeframe, adjustment, feed, path)
    out = []
    by_window = {}
    for r in rows:
        by_window.setdefault((r.get("requested_start"), r.get("requested_end")), []).append(r)
    for _w, group in by_window.items():
        for newer, older in zip(group, group[1:]):
            if newer.get("content_hash") != older.get("content_hash"):
                out.append((older, newer))
    out.sort(key=lambda p: p[1].get("pulled_at_epoch") or 0, reverse=True)
    return out


def describe(row):
    """One line a person can read, for a report footer or a log."""
    if not row:
        return "no recorded pull"
    return ("%s %s %s: %s rows pulled %s, content %s"
            % (row.get("symbol"), row.get("timeframe"), row.get("adjustment"),
               "{:,}".format(row.get("rows") or 0), row.get("pulled_at"),
               (row.get("content_hash") or "?")[:19]))


def compare_to_fresh(df_fresh, symbol, timeframe, adjustment="split", feed="sip", path=None):
    """Does the newest RECORDED pull of this series match what the vendor says now?

    Returns (verdict, message) with verdict one of "same", "differs", "unknown".

    "differs" is NOT a bug report. The vendor recomputes `adjustment=split` at query time and
    corrects its own history, so the honest reading is that the photograph has changed and any
    result built on the old one should be RE-PULLED rather than patched.
    """
    prev = latest(symbol, timeframe, adjustment, feed, path)
    if not prev:
        return "unknown", ("no recorded pull for %s %s, so there is nothing to compare this "
                           "against" % (symbol, timeframe))
    now_hash = content_hash(df_fresh)
    if now_hash == prev.get("content_hash"):
        return "same", ("%s %s is unchanged since the pull of %s (%s rows)"
                        % (symbol, timeframe, prev.get("pulled_at"),
                           "{:,}".format(prev.get("rows") or 0)))
    return "differs", (
        "cache differs from a fresh pull: %s %s was pulled %s with %s rows (%s) and the vendor "
        "now returns %s rows (%s). Alpaca computes adjustment=%s at QUERY TIME and corrects its "
        "own history, so RE-PULL rather than patch the cache, and treat any result computed on "
        "the older pull as suspect."
        % (symbol, timeframe, prev.get("pulled_at"), "{:,}".format(prev.get("rows") or 0),
           (prev.get("content_hash") or "?")[:19], "{:,}".format(len(df_fresh) if df_fresh is not None else 0),
           now_hash[:19], adjustment))


def trim(path=None, keep=KEEP_PER_SERIES):
    """Keep the newest `keep` records per series. Safe to skip; nothing depends on it."""
    path = path or manifest_path()
    rows = read_all(path)
    if not rows:
        return 0
    groups = {}
    for r in rows:                          # rows are in file order == chronological order
        groups.setdefault(r.get("series"), []).append(r)
    kept = []
    for _k, group in groups.items():
        kept.extend(group[-keep:])          # already in file order, which is chronological
    if len(kept) == len(rows):
        return 0
    try:
        from . import alpaca_rate
        with alpaca_rate._lock(path + ".lock") as got:
            if not got:
                return 0
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                for r in kept:
                    fh.write(json.dumps(r, sort_keys=True) + "\n")
            os.replace(tmp, path)
    except Exception:
        return 0
    return len(rows) - len(kept)
