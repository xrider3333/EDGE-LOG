"""Build the pinned side panel for augur_strategies/MISC_EVENTCRUSH_1_0.py (opus hunt strategy 94, EVENTCRUSH).

The plugin runs on the VIXY 5m RTH master (alpaca_split_rth, engine master id 141): VIXY's own prices come from the
job's bars. This panel holds only what the master does not carry, from the same inputs the hunt harness read
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S94/s94_lib.py, s94_run.py):
  * the session calendar = the dates of C:/EdgeLog/alpaca_cache/etf_daily/VIXY_1Day_raw.csv (the hunt used the VIXY
    5m master's dates and asserted they equal this file's, SPY 5m's and SPY daily's; this script re-checks all four
    through 2026-06-30 and refuses to write on any difference);
  * daily closes from etf_daily/{VIXY,SPY}_1Day_{raw,split}.csv, parsed exactly as s94_lib.read_daily (raw = share
    counts and per-share cost, raw / split = the reverse-split share ratio, split = the hedge's beta);
  * SPY 5m RTH closes by bar slot (09:30 .. 15:55, NaN where the master has no bar) from the SPY master
    (alpaca_split_rth, id 112), loaded with augur_engine.data.load_master_arrays like s94_lib.sess5 (the hedge leg).
Everything runs to 2026-06-30 (bars starting before 2026-06-30 16:00 ET, daily rows <= 2026-06-30) so the engine's
12-month lockbox has a calendar and SPY prices. THIS SCRIPT COMPUTES NO RETURN, PNL OR STATISTIC - it stores arrays
and prints shapes, the calendar checks, the reverse-split dates (corporate actions) and the sha256 to pin in the plugin.

    python tools/misc_eventcrush_panel.py     (writes C:/EdgeLog/alpaca_cache/eventcrush_panel/eventcrush_panel_v1.npz)
Memory: two 5m masters of ~205k rows each, one at a time; the panel itself is ~2 MB.
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"      # the master registry lives in the shared checkout
ETF = "C:/EdgeLog/alpaca_cache/etf_daily/"
OUT = "C:/EdgeLog/alpaca_cache/eventcrush_panel/eventcrush_panel_v1.npz"
CUT = "2026-06-30"
SLOTS = 78                                                # 5m bars starting 09:30 .. 15:55 ET


def read_daily(path):
    """s94_lib.read_daily with the cut moved from the seal to CUT (same parsing: str -> float via numpy)."""
    rows = []
    with open(path) as f:
        h = f.readline().strip().split(",")
        for ln in f:
            if ln[:10] > CUT:
                break
            rows.append(ln.strip().split(","))
    d = pd.DataFrame(rows, columns=h)
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date").replace("", np.nan).astype(float)
    assert d.index.is_monotonic_increasing and d.index.max() <= pd.Timestamp(CUT)
    return d


def bars5(D, sym):
    """(dates, slot, close) of the RTH 5m bars at or before 15:55, like s94_lib.sess5 (no prices are changed)."""
    m = D.find_master(sym, "5m", "rth", "alpaca_split_rth")
    assert m is not None and m["source"] == "alpaca_split_rth", sym
    a = D.load_master_arrays(m, date_from="2016-01-01", date_to=CUT)
    idx = a["index"].tz_convert("US/Eastern")
    keep = idx < pd.Timestamp(CUT + " 16:00", tz="US/Eastern")
    idx = idx[keep]
    c = np.asarray(a["close"], float)[keep]
    d = idx.tz_localize(None).normalize()
    mins = idx.hour * 60 + idx.minute
    df = pd.DataFrame({"d": d, "m": np.asarray(mins), "c": c})
    df = df[(df.m >= 570) & (df.m <= 955)]
    assert not df.duplicated(["d", "m"]).any(), sym
    print("%s 5m master id %s (%s): %d bars, %s .. %s" % (sym, m["id"], m["filename"], len(df), df.d.min().date(),
                                                          df.d.max().date()))
    return df


def main():
    cwd = os.getcwd()
    os.chdir(SHARED)
    sys.path.insert(0, SHARED)
    from augur_engine import data as D
    try:
        v5 = bars5(D, "VIXY")
        vdays = pd.DatetimeIndex(sorted(v5.d.unique()))
        last_v = v5.groupby("d").m.max()
        del v5                                            # VIXY prices come from the job's master, not the panel
        s5 = bars5(D, "SPY")
    finally:
        os.chdir(cwd)
    vr = read_daily(ETF + "VIXY_1Day_raw.csv")
    vs = read_daily(ETF + "VIXY_1Day_split.csv")
    sr = read_daily(ETF + "SPY_1Day_raw.csv")
    ss = read_daily(ETF + "SPY_1Day_split.csv")
    cal = vr.index
    sdays = pd.DatetimeIndex(sorted(s5.d.unique()))
    for nm, other in (("VIXY daily split", vs.index), ("SPY daily raw", sr.index), ("SPY daily split", ss.index),
                      ("VIXY 5m master", vdays), ("SPY 5m master", sdays)):
        if not cal.equals(other):
            sys.exit("calendar mismatch: VIXY daily raw vs %s: only daily %s, only other %s" % (
                nm, [str(x.date()) for x in cal.difference(other)][:10],
                [str(x.date()) for x in other.difference(cal)][:10]))
    print("calendar: %d sessions %s .. %s; VIXY 5m, SPY 5m and the four daily files agree on every date" % (
        len(cal), cal[0].date(), cal[-1].date()))
    print("VIXY 5m sessions whose last bar is not 15:55 (early closes 12:55, holes):",
          {str(k.date()): "%02d:%02d" % divmod(int(v), 60) for k, v in last_v[last_v != 955].items()})
    for nm, r, s in (("VIXY", vr, vs), ("SPY", sr, ss)):
        q = (r.close / s.close).to_numpy()
        ch = np.flatnonzero(np.abs(q[1:] / q[:-1] - 1) > 1e-6) + 1
        print("%s raw/split ratio steps (reverse splits on the ex-date; corporate actions, not returns): %s; "
              "ratio first %.6g last %.6g" % (nm, [(str(cal[i].date()), "1:%g" % round(q[i] / q[i - 1], 4)) for i in ch],
                                             q[0], q[-1]))
    spy5 = np.full((len(cal), SLOTS), np.nan, np.float64)
    row = cal.get_indexer(pd.DatetimeIndex(s5.d))
    assert (row >= 0).all()
    spy5[row, (s5.m.to_numpy() - 570) // 5] = s5.c.to_numpy()
    last_s = s5.groupby("d").m.max()
    print("SPY 5m sessions whose last bar is not 15:55:",
          {str(k.date()): "%02d:%02d" % divmod(int(v), 60) for k, v in last_s[last_s != 955].items()})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez(OUT, dates=np.array([int(d.strftime("%Y%m%d")) for d in cal], dtype="int64"),
             vixy_raw=vr.close.to_numpy(np.float64), vixy_split=vs.close.to_numpy(np.float64),
             spy_raw=sr.close.to_numpy(np.float64), spy_split=ss.close.to_numpy(np.float64), spy5=spy5)
    with open(OUT, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    print("%s  dates %d  spy5 %s (%d bars)  sha256 %s" % (OUT, len(cal), spy5.shape, int(np.isfinite(spy5).sum()), sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
