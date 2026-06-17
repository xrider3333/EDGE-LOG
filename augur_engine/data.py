"""Master-CSV data access (streamlit-free).

Reads the same master registry (optimizer_history.db -> csv_files, is_master=1) and
the same CSV files (augur_uploads/) the Streamlit app uses, and returns OHLCV arrays
+ a day_id (ET calendar-day index, as the strategies expect) ready for run_backtest.
"""
import os
import sqlite3

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


def load_master_arrays(master):
    """Load a master row's CSV -> dict(open,high,low,close,volume,day_id,index,meta).
    day_id is the ET calendar-day factorization the day_id-aware strategies need."""
    path = os.path.join(UPLOADS, master["filename"])
    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
    return {
        "open":  df["open"].values.astype(float),
        "high":  df["high"].values.astype(float),
        "low":   df["low"].values.astype(float),
        "close": df["close"].values.astype(float),
        "volume": df["volume"].values.astype(float) if "volume" in df.columns else None,
        "day_id": day_id,
        "index": df.index,
        "meta": master,
    }
