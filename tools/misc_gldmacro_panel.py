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
12-month lockbox has its closes and clock.
DATA QA (split / re-adjustment steps, ratio_qa): on every panel session, the ratio of two closes of the SAME session
from two sources - raw / split (the two alpaca daily files: must be 1 on every row), raw / the yahoo_adj close, raw /
the close of the 5m master's last bar of the session. A split or a re-adjustment in one source is a level STEP in that
ratio (the medians of the 21 sessions before and after a date differ by more than 0.5 pct); GLD never split, so any
step is flagged and nothing is written. One-day differences (a bad print in one source) are listed, not flagged.
THIS SCRIPT COMPUTES NO RETURN, PNL OR STATISTIC: it stores arrays and prints shapes, the calendar checks, the
same-session ratio checks, the short sessions and the sha256 to pin in the plugin.

    python tools/misc_gldmacro_panel.py     (writes C:/EdgeLog/alpaca_cache/gldmacro_panel/gldmacro_panel_v1.npz)
Memory: the 5m master (~205k rows) once, 184 MB peak (2026-11-14 build, 3 s); the panel is 85 KB. Never run it while
the PC is in QUIET. A rebuild writes a new zip (new sha256): the plugin then refuses it until PANEL_SHA256 is re-pinned.
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
QA_WIN, QA_STEP, QA_DAY = 21, 0.005, 0.005                # 21-session medians; a 0.5 pct level move = a step


def ratio_qa(label, num, den, dates, exact=False):
    """DATA QA - no return: q = num / den, two closes of the SAME session from two sources, on every session. A level
    STEP (a split or a re-adjustment in one source) = the medians of q over the QA_WIN sessions before and after a date
    differ by more than QA_STEP; one step is reported per run of flagged dates (the date where the medians differ
    most), with q's level on each side. Sessions where q is off its overall median by more than QA_DAY are listed
    (one-day differences, not flags). exact: the two sources must hold the same numbers. Returns the flag count."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    q = num / den
    n = len(q)
    hits = []
    for t in range(QA_WIN, n - QA_WIN + 1):
        before, after = np.median(q[t - QA_WIN:t]), np.median(q[t:t + QA_WIN])
        if abs(after / before - 1.0) > QA_STEP:
            hits.append((t, abs(after / before - 1.0)))
    steps, run = [], []
    for h in hits + [None]:
        if run and (h is None or h[0] != run[-1][0] + 1):
            t = max(run, key=lambda z: z[1])[0]
            steps.append((t, float(np.median(q[t - QA_WIN:t])), float(np.median(q[t:t + QA_WIN]))))
            run = []
        if h is not None:
            run.append(h)
    med = float(np.median(q))
    off = np.flatnonzero(np.abs(q / med - 1.0) > QA_DAY)
    differ = int((num != den).sum())
    flags = len(steps) + (differ if exact else 0)
    print("QA %s: %d sessions %s .. %s | ratio %.6f .. %.6f (median %.6f)%s | sessions off the median by more than "
          "%.1f pct: %d %s | level steps %d -> %s" % (
              label, n, dates[0].date(), dates[-1].date(), float(q.min()), float(q.max()), med,
              (" | rows where the two differ %d" % differ) if exact else "", 100 * QA_DAY, len(off),
              [str(dates[k].date()) for k in off[:12]], len(steps), "FLAG" if flags else "OK"))
    for t, b, a in steps:
        print("  QA FLAG %s: level step at %s - ratio level %.6f before, %.6f after" % (label, dates[t].date(), b, a))
    return flags


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
    # ---- the 5m clock: each session's first and last bar minute; the last bar's close only for the data QA
    idx = a["index"].tz_convert("US/Eastern")
    assert idx.is_monotonic_increasing, "5m master bars out of time order"
    keep = np.asarray(idx < pd.Timestamp(CUT, tz="US/Eastern") + pd.Timedelta(days=1))
    idx = idx[keep]
    df = pd.DataFrame({"d": idx.tz_localize(None).normalize(), "m": np.asarray(idx.hour * 60 + idx.minute),
                       "c": np.asarray(a["close"], float)[keep]})
    del a
    assert ((df.m >= OPEN_MIN) & (df.m <= LAST_SLOT)).all(), "5m master has bars outside 09:30 .. 15:55"
    assert not df.duplicated(["d", "m"]).any(), "duplicate 5m bars"
    g = df.groupby("d")
    first, last, last_close = g.m.min(), g.m.max(), g.c.last()
    print("GLD 5m master: %d bars, %d sessions %s .. %s" % (len(df), len(last), last.index[0].date(),
                                                            last.index[-1].date()))
    del df, g
    # ---- alpaca raw / split daily closes (the same numbers row for row: checked by the data QA below)
    raw = read_daily(RAW)
    spl = read_daily(SPLIT)
    if not raw.index.equals(spl.index):
        sys.exit("GLD_1Day_split.csv and GLD_1Day_raw.csv have different dates - a bad file; refusing to write")
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
    print("calendar: %d sessions %s .. %s; the yahoo 1d master, the 5m master, GLD_1Day_raw.csv and GLD_1Day_split.csv "
          "agree on every date; every 5m session opens with a 09:30 bar" % (len(cal), cal[0].date(), cal[-1].date()))
    flags = (ratio_qa("raw / split (the two alpaca daily files)", raw.values, spl.values, cal, exact=True)
             + ratio_qa("raw / yahoo_adj close", raw.values, close.values, cal)
             + ratio_qa("raw / close of the 5m master's last bar", raw.values, last_close.values, cal))
    if flags:
        sys.exit("DATA QA: %d flag(s) above - a split or a re-adjustment step in a GLD source; refusing to write"
                 % flags)
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
