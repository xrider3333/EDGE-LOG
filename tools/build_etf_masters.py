"""Build engine-format DAILY master CSVs for the ROUND-25 weak-edge book's ETF legs.

WHY: r25 (tools/r25_weak_edge_book.py) is a standalone script that downloads its own
Yahoo bars. The recorded next step is "ETF masters -> plugin files -> BOOK validate", so
the ETF tape has to live where the engine looks for data (augur_uploads/ + the csv_files
master registry) before Auto-Validate / a BOOK job can judge those legs.

── What the engine accepts for daily bars ────────────────────────────────────────────
Nothing special: `augur_engine.data.find_master(instrument, timeframe, session, source)`
is a plain filter over the csv_files registry, and `load_master_arrays` only needs the
columns time,open,high,low,close[,volume] with `time` in EPOCH SECONDS (UTC), which it
converts to US/Eastern and factorizes into day_id. So a daily master is simply one row
per trading day. The house already has one and this builder copies its convention
exactly (registry id 51, "QQQ 1d (Yahoo total-return)", master_ab0d7781.csv):
    timeframe = "1d"      session = "rth"      source = "yahoo_adj"
    each bar stamped 09:30 ET (the session open) of its own calendar day
That stamping matters: it is what makes day_id one-bar-per-day and keeps the bar inside
the ET calendar day it belongs to after the UTC round-trip.

── Split / dividend policy (r25 is the reference) ────────────────────────────────────
r25 downloads with auto_adjust=True: split- AND dividend-adjusted "total-return" prices.
r19b pre-registered that choice ("fair for multi-day holds, holders receive
distributions"). We must keep it or the plugin legs cannot reproduce r25.

This builder therefore downloads BOTH ways (auto_adjust=False is the only way to get RAW
OHLC *and* Volume *and* Adj Close in one frame) and writes:
    open/high/low/close = the auto_adjust=True frame, verbatim  <- the r25 tape
    volume              = raw (unadjusted) volume from the auto_adjust=False frame
It also prints max|auto_adjust=True - raw x (AdjClose/Close)| as a relative number, i.e.
how far yfinance's own adjusted print is from the textbook reconstruction. That gap is
small but NOT zero (yfinance rounds its adjusted prints; on QQQ it reaches ~5e-5 of the
price level, ~4c on a $700 bar), which is exactly why the OHLC written here is the
adjusted frame verbatim rather than the reconstruction: a 4c price difference is a few
dollars of PnL per trade, and the parity check demands the dollar.

CAVEAT worth knowing: a total-return series is re-scaled every time a new dividend is
paid, so the WHOLE history's price level drifts between downloads. Two masters built
months apart are not bit-identical, and neither are two r25 runs. Parity is therefore
only meaningful between a master and an r25 run from the same day.

Usage:  python tools/build_etf_masters.py            # build + register + cache-copy
        python tools/build_etf_masters.py --dry-run  # download + report, write nothing
"""
import argparse
import datetime as dt
import hashlib
import os
import shutil
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.paths import UPLOADS, DB_PATH  # noqa: E402

# GLD/TLT/IWM/QQQ are the r25 book's ETF legs; SPY is a control (never in the book).
TICKERS = ["GLD", "TLT", "IWM", "QQQ", "SPY"]
START = "2006-01-01"
TIMEFRAME = "1d"
SESSION = "rth"
SOURCE = "yahoo_adj"
CACHE_DIR = r"C:\EdgeLog\_anatomy_cache\etf_masters"


def _download(tk, end):
    import yfinance as yf
    raw = yf.download(tk, start=START, end=end, interval="1d",
                      auto_adjust=False, progress=False, actions=False)
    adj = yf.download(tk, start=START, end=end, interval="1d",
                      auto_adjust=True, progress=False, actions=False)
    for df in (raw, adj):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    return raw, adj


def build(tk, end, dry_run=False):
    raw, adj = _download(tk, end)
    need = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    missing = [c for c in need if c not in raw.columns]
    if missing:
        raise RuntimeError(f"{tk}: yfinance frame missing {missing}")
    raw = raw[need].dropna(subset=["Open", "High", "Low", "Close", "Adj Close"])

    a = adj.reindex(raw.index)[["Open", "High", "Low", "Close"]]
    keep = ~a.isna().any(axis=1).values
    raw = raw[keep]
    a = a[keep]
    o, h, l, c = (a[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    v = raw["Volume"].fillna(0).values.astype(float)

    # how far yfinance's adjusted print is from raw x (AdjClose/Close) — documentation
    # of the policy, not a gate; the OHLC written is the adjusted frame verbatim.
    ratio = (raw["Adj Close"] / raw["Close"]).values.astype(float)
    recon = np.column_stack([raw[k].values.astype(float) * ratio
                             for k in ("Open", "High", "Low", "Close")])
    reldiff = float(np.abs(recon - a.values.astype(float)).max()
                    / max(1e-9, float(np.abs(a.values).max())))

    # each bar stamped 09:30 ET of its own calendar day, then -> epoch seconds UTC
    days = pd.DatetimeIndex([pd.Timestamp(x).normalize() for x in a.index])
    stamps = (days + pd.Timedelta(hours=9, minutes=30)).tz_localize("US/Eastern")
    out = pd.DataFrame({
        "time": ((stamps.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)),  # POSIX seconds independent of datetime resolution (pandas 3 = microseconds; astype//1e9 breaks)
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    })
    out = out.sort_values("time").drop_duplicates("time").reset_index(drop=True)

    fname = "master_%s.csv" % hashlib.sha1(
        f"{tk}|{TIMEFRAME}|{SESSION}|{SOURCE}".encode()).hexdigest()[:8]
    d0 = str(days[0].date())
    d1 = str(days[-1].date())
    print(f"{tk:5} {fname}  rows={len(out):>6}  {d0} -> {d1}  "
          f"max|adj-recon| rel={reldiff:.2e}")
    if dry_run:
        return None

    path = os.path.join(UPLOADS, fname)
    os.makedirs(UPLOADS, exist_ok=True)
    out.to_csv(path, index=False)
    os.makedirs(CACHE_DIR, exist_ok=True)
    shutil.copy2(path, os.path.join(CACHE_DIR, fname))
    return dict(name=f"{tk} 1d (Yahoo total-return)", filename=fname, instrument=tk,
                rows=len(out), date_from=d0, date_to=d1,
                created_at=dt.datetime.now().isoformat(timespec="seconds"),
                timeframe=TIMEFRAME, is_master=1, source=SOURCE, session=SESSION,
                provenance=('{"source":"yahoo_adj","note":"daily, OHLC = yfinance'
                            ' auto_adjust=True (split+dividend total-return) verbatim,'
                            ' volume = raw unadjusted; bars stamped 09:30 ET",'
                            '"built_by":"tools/build_etf_masters.py"}'))


def register(rows):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        for r in rows:
            cur.execute("DELETE FROM csv_files WHERE instrument=? AND timeframe=? AND source=?",
                        (r["instrument"], r["timeframe"], r["source"]))
            cols = ",".join(r.keys())
            cur.execute(f"INSERT INTO csv_files ({cols}) VALUES ({','.join('?' * len(r))})",
                        tuple(r.values()))
        conn.commit()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--end", default=None, help="yfinance end date (exclusive); default tomorrow")
    a = ap.parse_args()
    end = a.end or str((dt.date.today() + dt.timedelta(days=1)))
    print(f"registry: {DB_PATH}\nuploads : {UPLOADS}\nwindow  : {START} -> {end} (exclusive)\n")
    rows = [r for r in (build(tk, end, a.dry_run) for tk in TICKERS) if r]
    if rows:
        register(rows)
        print(f"\nregistered {len(rows)} masters as timeframe={TIMEFRAME} session={SESSION} "
              f"source={SOURCE}; copies in {CACHE_DIR}")


if __name__ == "__main__":
    main()
