"""Build the pinned side panel for augur_strategies/MISC_GLDMACRO_1_0.py (opus hunt strategy 97, GLD-MACRODAY).

The plugin runs on the GLD 5m RTH master (alpaca_split_rth, engine master id 79): the master is the bar clock (entry
and exit bars) and the price source of the release-day-open entry (cell 97b). This panel holds what the master does
not carry, from the hunt harness's own inputs (C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S97/s97_lib.py,
gld_daily):
  * close    GLD daily closes of the yahoo_adj GLD 1d master (engine master id 52), loaded with
             augur_engine.data.load_master_arrays exactly as s97_lib.gld_daily (np.asarray(close, float)): the official
             16:00 / half-day closes, the return prices of cell 97a. GLD pays no dividend and never split, so the
             adjusted close is the traded close;
  * raw      C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv closes, parsed as s97_lib.gld_daily (csv.DictReader,
             float()): the share-count and cost price of cell 97a (the hunt's raw price for every D-1 in 2016+);
  * last_min minute of day (ET) of each session's last 5m bar in the GLD 5m master (955 = 15:55; 775 = 12:55 on a half
             day; 2019-08-12 stops at 15:25): the plugin's test that a session is complete inside the job's bars.
The session calendar = the yahoo master's dates 2016-01-04 .. 2026-06-30. This script checks that it equals the 5m
master's sessions and GLD_1Day_raw.csv's dates, that GLD_1Day_split.csv equals the raw file (no split), that every 5m
session opens with a 09:30 bar, and refuses to write on any difference. Everything runs to 2026-06-30 so the engine's
12-month lockbox has its closes and clock. THIS SCRIPT COMPUTES NO RETURN, PNL OR STATISTIC: it stores arrays and
prints shapes, the calendar checks, the short sessions and the sha256 to pin in the plugin.

    python tools/misc_gldmacro_panel.py     (writes C:/EdgeLog/alpaca_cache/gldmacro_panel/gldmacro_panel_v1.npz)
Memory: the 5m master (~205k rows) once, ~150 MB peak; the panel is ~80 KB. Never run it while the PC is in QUIET.
"""
import csv
import hashlib
import os
import sys

import numpy as np
import pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"      # the master registry lives in the shared checkout
RAW = "C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv"
SPLIT = "C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_split.csv"
OUT = "C:/EdgeLog/alpaca_cache/gldmacro_panel/gldmacro_panel_v1.npz"
FROM, CUT = "2016-01-01", "2026-06-30"
OPEN_MIN, LAST_SLOT = 570, 955                            # 09:30 and 15:55 ET, minute of day


def read_daily(path):
    """s97_lib.gld_daily's alpaca parse (csv.DictReader + float()) with the cut moved from the seal to CUT."""
    dts, cl = [], []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["date"][:10] > CUT:
                break
            dts.append(r["date"][:10])
            cl.append(float(r["close"]))
    s = pd.Series(cl, index=pd.to_datetime(dts))
    assert s.index.is_monotonic_increasing and not s.index.duplicated().any(), path
    assert s.index.max() <= pd.Timestamp(CUT), path
    return s[s.index >= pd.Timestamp(FROM)]


def main():
    cwd = os.getcwd()
    os.chdir(SHARED)
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    try:
        m1 = D.find_master("GLD", "1d", "rth", "yahoo_adj")
        m5 = D.find_master("GLD", "5m", "rth", "alpaca_split_rth")
        assert m1 is not None and m5 is not None, "GLD masters not registered"
        y = D.load_master_arrays(m1, date_from=FROM, date_to=CUT)
        a = D.load_master_arrays(m5, date_from=FROM, date_to=CUT)
    finally:
        os.chdir(cwd)
    print("yahoo_adj GLD 1d master id %s (%s) | GLD 5m master id %s (%s)" % (m1["id"], m1["filename"], m5["id"],
                                                                           m5["filename"]))
    # ---- yahoo daily closes, exactly s97_lib.gld_daily's series (dates normalised, duplicates dropped)
    yi = y["index"].tz_localize(None).normalize()
    close = pd.Series(np.asarray(y["close"], float), index=yi)
    close = close[~close.index.duplicated()]
    assert close.index.is_monotonic_increasing and close.index.max() <= pd.Timestamp(CUT)
    del y
    # ---- the 5m clock: each session's first and last bar minute (no prices kept)
    idx = a["index"].tz_convert("US/Eastern")
    keep = idx < pd.Timestamp(CUT, tz="US/Eastern") + pd.Timedelta(days=1)
    idx = idx[keep]
    df = pd.DataFrame({"d": idx.tz_localize(None).normalize(), "m": np.asarray(idx.hour * 60 + idx.minute)})
    del a
    assert ((df.m >= OPEN_MIN) & (df.m <= LAST_SLOT)).all(), "5m master has bars outside 09:30 .. 15:55"
    assert not df.duplicated(["d", "m"]).any(), "duplicate 5m bars"
    g = df.groupby("d").m
    first, last = g.min(), g.max()
    print("GLD 5m master: %d bars, %d sessions %s .. %s" % (len(df), len(last), last.index[0].date(),
                                                            last.index[-1].date()))
    # ---- alpaca raw / split daily closes
    raw = read_daily(RAW)
    spl = read_daily(SPLIT)
    if not (raw.index.equals(spl.index) and bool((raw.values == spl.values).all())):
        sys.exit("GLD_1Day_split.csv differs from GLD_1Day_raw.csv - a split or a bad file; refusing to write")
    cal = close.index
    for nm, other in (("GLD 5m master sessions", pd.DatetimeIndex(last.index)), ("GLD_1Day_raw.csv", raw.index)):
        if not cal.equals(other):
            sys.exit("calendar mismatch: yahoo_adj 1d vs %s: only yahoo %s, only other %s" % (
                nm, [str(x.date()) for x in cal.difference(other)][:10],
                [str(x.date()) for x in other.difference(cal)][:10]))
    bad_open = first[first != OPEN_MIN]
    if len(bad_open):
        sys.exit("5m sessions whose first bar is not 09:30: %s" % {str(k.date()): int(v) for k, v in
                                                                    bad_open.items()})
    for nm, v in (("close", close.values), ("raw", raw.values)):
        if not (np.isfinite(v).all() and (v > 0).all()):
            sys.exit("non-finite or non-positive %s close in the panel window" % nm)
    print("calendar: %d sessions %s .. %s; the yahoo 1d master, the 5m master and GLD_1Day_raw.csv agree on every "
          "date; raw == split on every row; every 5m session opens with a 09:30 bar" % (
              len(cal), cal[0].date(), cal[-1].date()))
    print("5m sessions whose last bar is not 15:55 (half days 12:55, holes):",
          {str(k.date()): "%02d:%02d" % divmod(int(v), 60) for k, v in last[last != LAST_SLOT].items()})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, dates=np.array([int(d.strftime("%Y%m%d")) for d in cal], dtype="int64"),
             close=close.to_numpy(np.float64), raw=raw.to_numpy(np.float64),
             last_min=last.to_numpy().astype("int64"))
    with open(OUT, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    print("%s  sessions %d  sha256 %s" % (OUT, len(cal), sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
