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


def load_master_arrays(master, date_from=None, date_to=None):
    """Load a master row's CSV -> dict(open,high,low,close,volume,day_id,index,meta).
    day_id is the ET calendar-day factorization the day_id-aware strategies need.

    date_from / date_to (YYYY-MM-DD strings or None) slice the master to that ET-date
    window *before* day_id is factorized, so day_id stays 0-based and contiguous."""
    path = os.path.join(UPLOADS, master["filename"])
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
    return {
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
