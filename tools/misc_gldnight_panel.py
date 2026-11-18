"""Build the pinned side panel for augur_strategies/MISC_GLDNIGHT_1_0.py (opus hunt 158 / 160, GLD-NIGHT).

The plugin runs on the GLD 5m RTH master (alpaca_split_rth, engine master id 79): the master is the bar clock only
(entry bar = D-1's last 5m bar, exit bar = D's 09:30 bar). This panel holds the prices the master does not carry, from
the hunt harness's own input (C:/EdgeLog/_anatomy_cache/opus_hunt1109/db_masters/r20_run.py, daily('GLD'), cell 160a):
  * open      C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv opens: the official opening print, the exit of 160a;
  * close     the same file's closes: the official closing print, the entry of 160a;
  * raw       the same closes again (GLD never split, so raw = traded): the share-count and cost price. Kept as its
              own array so the plugin sizes from `raw` and prices from `close`, as the sibling MISC_GLDMACRO_1_0 does;
  * first_min minute of day (ET) of each session's first 5m bar in the GLD 5m master (570 = 09:30 on every session);
  * last_min  minute of day of each session's last 5m bar (955 = 15:55; 775 = 12:55 on a half day; 2019-08-12 stops
              at 15:25): the plugin's test that D-1 is complete inside the job's bars;
  * gap       calendar days from the previous session to this one (1 = a weeknight, 3 = a plain weekend, 2 = a
              mid-week holiday, 4+ = a holiday weekend; 0 on the first row, which never trades).
The session calendar = GLD_1Day_raw.csv's dates 2016-01-04 .. 2026-06-30. This script checks that it equals the 5m
master's sessions and the sibling panel's dates (gldmacro_panel_v1.npz), that GLD_1Day_split.csv equals the raw file
(no split), that every 5m session opens with a 09:30 bar, and refuses to write on any difference. Everything runs to
2026-06-30 so the engine's 12-month lockbox has its prints and clock.
DATA QA (misc_gldmacro_panel.ratio_qa: two prices of the SAME session from two sources, never a return): raw / split
closes and opens (must be 1 on every row), raw close / the sibling panel's yahoo close and its raw (the cross-check:
how many differ and by how much), raw close / the close of the 5m master's last bar, raw open / the open of the 5m
master's 09:30 bar. A level step in any ratio = a split or re-adjustment in one source: flagged, nothing written.
THIS SCRIPT COMPUTES NO RETURN, PNL OR STATISTIC: it stores arrays and prints shapes, the calendar checks, the
same-session ratio checks, the gap counts, the short sessions and the sha256 to pin in the plugin.

    python tools/misc_gldnight_panel.py     (writes C:/EdgeLog/alpaca_cache/gldnight_panel/gldnight_panel_v1.npz)
Memory: the 5m master (~205k rows) once, under 200 MB; the panel is about 130 KB. Never run it while the PC is in
QUIET. A rebuild writes a new zip (new sha256): the plugin then refuses it until PANEL_SHA256 is re-pinned.
"""
import csv
import hashlib
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from misc_gldmacro_panel import ratio_qa  # noqa: E402

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"      # the master registry lives in the shared checkout
RAW = "C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_raw.csv"
SPLIT = "C:/EdgeLog/alpaca_cache/etf_daily/GLD_1Day_split.csv"
SIBLING = "C:/EdgeLog/alpaca_cache/gldmacro_panel/gldmacro_panel_v1.npz"
OUT = "C:/EdgeLog/alpaca_cache/gldnight_panel/gldnight_panel_v1.npz"
FROM, CUT = "2016-01-01", "2026-06-30"
OPEN_MIN, LAST_SLOT = 570, 955                            # 09:30 and 15:55 ET, minute of day


def read_daily(path):
    """The harness's daily file (date, open, .., close) as a frame on FROM .. CUT (csv.DictReader + float())."""
    dts, op, cl = [], [], []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["date"][:10] > CUT:
                break
            dts.append(r["date"][:10])
            op.append(float(r["open"]))
            cl.append(float(r["close"]))
    s = pd.DataFrame({"open": op, "close": cl}, index=pd.to_datetime(dts))
    assert s.index.is_monotonic_increasing and not s.index.duplicated().any(), path
    assert s.index.max() <= pd.Timestamp(CUT), path
    return s[s.index >= pd.Timestamp(FROM)]


def differ_report(label, a, b):
    """DATA QA - no return: how many same-session prices differ between two sources, and by how much (bp)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = np.abs(a / b - 1.0) * 1e4
    n = int((a != b).sum())
    print("CROSS-CHECK %s: %d sessions | differ on %d | abs diff bp: median %.4f, p99 %.3f, max %.2f | differ by more "
          "than 1 bp: %d, more than 10 bp: %d" % (label, len(a), n, float(np.median(d)), float(np.percentile(d, 99)),
                                                  float(d.max()), int((d > 1).sum()), int((d > 10).sum())))


def main():
    cwd = os.getcwd()
    os.chdir(SHARED)
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    try:
        m5 = D.find_master("GLD", "5m", "rth", "alpaca_split_rth")
        assert m5 is not None, "GLD 5m master not registered"
        a = D.load_master_arrays(m5, date_from=FROM, date_to=CUT)
    finally:
        os.chdir(cwd)
    print("GLD 5m master id %s (%s)" % (m5["id"], m5["filename"]))
    # ---- the 5m clock: each session's first and last bar minute; first open / last close only for the data QA
    idx = a["index"].tz_convert("US/Eastern")
    assert idx.is_monotonic_increasing, "5m master bars out of time order"
    keep = np.asarray(idx < pd.Timestamp(CUT, tz="US/Eastern") + pd.Timedelta(days=1))
    idx = idx[keep]
    df = pd.DataFrame({"d": idx.tz_localize(None).normalize(), "m": np.asarray(idx.hour * 60 + idx.minute),
                       "o": np.asarray(a["open"], float)[keep], "c": np.asarray(a["close"], float)[keep]})
    del a
    assert ((df.m >= OPEN_MIN) & (df.m <= LAST_SLOT)).all(), "5m master has bars outside 09:30 .. 15:55"
    assert not df.duplicated(["d", "m"]).any(), "duplicate 5m bars"
    g = df.groupby("d")
    first, last, first_open, last_close = g.m.min(), g.m.max(), g.o.first(), g.c.last()
    print("GLD 5m master: %d bars, %d sessions %s .. %s" % (len(df), len(last), last.index[0].date(),
                                                            last.index[-1].date()))
    del df, g
    raw = read_daily(RAW)
    spl = read_daily(SPLIT)
    if not raw.index.equals(spl.index):
        sys.exit("GLD_1Day_split.csv and GLD_1Day_raw.csv have different dates - a bad file; refusing to write")
    cal = raw.index
    if not os.path.exists(SIBLING):
        sys.exit("the sibling panel %s is not on this machine - the close cross-check cannot run" % SIBLING)
    z = np.load(SIBLING, allow_pickle=False)
    sib_dates = pd.to_datetime(pd.Series(np.asarray(z["dates"]).astype(str)), format="%Y%m%d")
    for nm, other in (("GLD 5m master sessions", pd.DatetimeIndex(last.index)),
                      ("gldmacro_panel_v1.npz", pd.DatetimeIndex(sib_dates))):
        if not cal.equals(other):
            sys.exit("calendar mismatch: GLD_1Day_raw.csv vs %s: only raw %s, only other %s" % (
                nm, [str(x.date()) for x in cal.difference(other)][:10],
                [str(x.date()) for x in other.difference(cal)][:10]))
    bad_open = first[first != OPEN_MIN]
    if len(bad_open):
        sys.exit("5m sessions whose first bar is not 09:30: %s" % {str(k.date()): int(v) for k, v in
                                                                    bad_open.items()})
    for nm, v in (("open", raw.open.values), ("close", raw.close.values)):
        if not (np.isfinite(v).all() and (v > 0).all()):
            sys.exit("non-finite or non-positive %s in the panel window" % nm)
    print("calendar: %d sessions %s .. %s; GLD_1Day_raw.csv, GLD_1Day_split.csv, the 5m master and the sibling panel "
          "agree on every date; every 5m session opens with a 09:30 bar" % (len(cal), cal[0].date(), cal[-1].date()))
    differ_report("raw close vs the sibling panel's `close` (yahoo_adj 1d master)", raw.close.values, z["close"])
    differ_report("raw close vs the sibling panel's `raw` (the same file)", raw.close.values, z["raw"])
    differ_report("raw open vs the open of the 5m master's 09:30 bar", raw.open.values, first_open.values)
    flags = (ratio_qa("raw / split close (the two alpaca daily files)", raw.close.values, spl.close.values, cal,
                      exact=True)
             + ratio_qa("raw / split open", raw.open.values, spl.open.values, cal, exact=True)
             + ratio_qa("raw close / the sibling panel's yahoo close", raw.close.values, z["close"], cal)
             + ratio_qa("raw close / the sibling panel's raw", raw.close.values, z["raw"], cal, exact=True)
             + ratio_qa("raw close / close of the 5m master's last bar", raw.close.values, last_close.values, cal)
             + ratio_qa("raw open / open of the 5m master's 09:30 bar", raw.open.values, first_open.values, cal))
    if flags:
        sys.exit("DATA QA: %d flag(s) above - a split, a re-adjustment step or a changed file in a GLD source; "
                 "refusing to write" % flags)
    gap = np.concatenate([[0], np.diff(cal.values).astype("timedelta64[D]").astype("int64")])
    u, c = np.unique(gap[1:], return_counts=True)
    print("calendar gap to the previous session (days: sessions):", dict(zip(u.tolist(), c.tolist())))
    print("5m sessions whose last bar is not 15:55 (half days 12:55, holes):",
          {str(k.date()): "%02d:%02d" % divmod(int(v), 60) for k, v in last[last != LAST_SLOT].items()})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, dates=np.array([int(d.strftime("%Y%m%d")) for d in cal], dtype="int64"),
             open=raw.open.to_numpy(np.float64), close=raw.close.to_numpy(np.float64),
             raw=raw.close.to_numpy(np.float64), first_min=first.to_numpy().astype("int64"),
             last_min=last.to_numpy().astype("int64"), gap=gap.astype("int64"))
    with open(OUT, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    print("%s  sessions %d  sha256 %s" % (OUT, len(cal), sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
