"""Master-CSV data access (streamlit-free).

Reads the same master registry (optimizer_history.db -> csv_files, is_master=1) and
the same CSV files (augur_uploads/) the Streamlit app uses, and returns OHLCV arrays
+ a day_id (ET calendar-day index, as the strategies expect) ready for run_backtest.
"""
import os
import sqlite3
import hashlib

import numpy as np
import pandas as pd

from .paths import UPLOADS, DB_PATH
from . import trial_cache as _TC


def list_masters():
    """All registered master CSVs as a list of dicts."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(
            "SELECT * FROM csv_files WHERE is_master=1 "
            "ORDER BY instrument,timeframe,source", conn)
    finally:
        conn.close()
    return df.to_dict("records")


def find_master(instrument, timeframe, session=None, source=None):
    """Best-matching master row for instrument+timeframe (+ optional session/source).
    For non-adjusted data pass source='db_noadj_rth'/'db_noadj_eth'."""
    cand = [m for m in list_masters()
            if str(m.get("instrument")) == str(instrument)
            and str(m.get("timeframe")) == str(timeframe)]
    if session:
        cand = [m for m in cand if str(m.get("session", "")).lower() == session.lower()]
    if source:
        cand = [m for m in cand if str(m.get("source", "")) == source]
    return cand[0] if cand else None


# ── PR3: in-process data-prep memoization (docs/INCREMENTAL_BACKTEST_REUSE.md
#    §2(b)) — repeated jobs over the same master+window skip the CSV read +
#    day_id factorization. Gated behind trial_cache.is_enabled() (the one switch
#    for the whole caching subsystem, default OFF): when OFF, load_master_arrays
#    behaves EXACTLY as before this feature existed — no memo lookup, no memo
#    write, byte-identical.
#
#    Key = (instrument, timeframe, source, filename, date_from, date_to,
#    file mtime, file size). The mtime+size pair mirrors data_quality.
#    check_master_cached's own freshness idiom, so a CSV that changed on disk
#    (an auto-sync landed new bars, a re-ingest replaced the file) is ALWAYS a
#    miss -> fresh read, never a stale array — the same "silent window slide"
#    hazard class CLAUDE.md's comparison-rerun hard rule warns about, just one
#    layer earlier (before a window even gets sliced). Bounded to a handful of
#    entries (LRU) since each entry holds several multi-MB numpy arrays.
_MEMO_MAX_ENTRIES = 4
_MEMO = []   # [(key, value_dict), ...] — index 0 = least-recently-used


def _memo_key(master, date_from, date_to, st_mtime, st_size):
    return (master.get("instrument"), master.get("timeframe"), master.get("source"),
            master.get("filename"), date_from, date_to, st_mtime, st_size)


def _memo_get(key):
    for i, (k, v) in enumerate(_MEMO):
        if k == key:
            _MEMO.append(_MEMO.pop(i))          # bump to most-recently-used
            return v
    return None


def _memo_put(key, value):
    _MEMO.append((key, value))
    del _MEMO[:-_MEMO_MAX_ENTRIES]               # drop oldest beyond the cap


def _memo_clear():
    """Test-only escape hatch — production code never calls this; a changed
    file is already correctly handled by the mtime+size key above."""
    _MEMO.clear()


def load_master_arrays(master, date_from=None, date_to=None):
    """Load a master row's CSV -> dict(open,high,low,close,volume,day_id,index,meta).
    day_id is the ET calendar-day factorization the day_id-aware strategies need.

    date_from / date_to (YYYY-MM-DD strings or None) slice the master to that ET-date
    window *before* day_id is factorized, so day_id stays 0-based and contiguous.

    In-process memoized (PR3 above) when trial_cache.is_enabled() — a cache HIT
    returns a value equal to a fresh load (see that section's docstring for the
    key + invalidation contract). A HIT's outer dict is always a fresh shallow
    copy (callers may freely rebind its keys, e.g. `arrays["meta"] = ...`,
    without mutating the shared memo entry). Whenever memoization is active,
    the underlying numpy arrays are marked read-only from the moment an entry
    is created — including the very first (populating) call, not just later
    hits — so an accidental in-place mutation by ANY caller raises immediately
    instead of silently corrupting every future reader of that memo entry."""
    path = os.path.join(UPLOADS, master["filename"])

    memo_key = None
    if _TC.is_enabled():
        try:
            st = os.stat(path)
            memo_key = _memo_key(master, date_from, date_to, st.st_mtime, st.st_size)
            hit = _memo_get(memo_key)
            if hit is not None:
                return dict(hit)
        except OSError:
            memo_key = None   # can't stat -- fall through; pd.read_csv below will
                              # raise the SAME real error a memo-off caller would see

    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    if date_from:
        df = df[df.index >= pd.Timestamp(date_from, tz="US/Eastern")]
    if date_to:
        # inclusive of the whole `date_to` calendar day
        df = df[df.index < pd.Timestamp(date_to, tz="US/Eastern") + pd.Timedelta(days=1)]
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
    # Data fingerprint (docs/INCREMENTAL_BACKTEST_REUSE.md): a sha1 of the SLICED
    # window's first/last bar timestamp + bar count. This is what makes a "silent
    # window slide" (master auto-synced new bars under a blank date_to -- the exact
    # #162-vs-#164 bug CLAUDE.md's hard rule warns about) a cache MISS rather than a
    # false hit: same date_from/date_to string can still resolve to a different set
    # of actual bars once new data lands, and this fingerprint changes when that
    # happens even though date_from/date_to themselves didn't. Non-breaking: purely
    # an ADDED top-level key, every existing key is untouched.
    n_bars = len(df.index)
    _first_ts = str(df.index[0]) if n_bars else ""
    _last_ts = str(df.index[-1]) if n_bars else ""
    fingerprint = hashlib.sha1(f"{_first_ts}|{_last_ts}|{n_bars}".encode()).hexdigest()
    result = {
        "open":  df["open"].values.astype(float),
        "high":  df["high"].values.astype(float),
        "low":   df["low"].values.astype(float),
        "close": df["close"].values.astype(float),
        "volume": df["volume"].values.astype(float) if "volume" in df.columns else None,
        "day_id": day_id,
        "index": df.index,
        "meta": master,
        "fingerprint": fingerprint,
    }
    if memo_key is not None:
        for _k in ("open", "high", "low", "close", "volume", "day_id"):
            _v = result.get(_k)
            if isinstance(_v, np.ndarray):
                _v.setflags(write=False)
        _memo_put(memo_key, result)
    return result
