"""REPAIR A BAD STRETCH OF A FUTURES MASTER FROM THE NINJATRADER 10s CAPTURE.

WHY (2026-11-26). Every NQ master (NOADJ / ADJ / FADJ, RTH and ETH, 1m to 60m, plus the
legacy yahoo masters) carried a bad 2026-10-30 print: Yahoo's 1m NQ=F feed dropped
14:54-15:02 ET and then served a 15:03 bar with open 29562 (real ~28288) and the whole
hole's volume (25,641). The 14:53 bar was also partial (227 of 1,866 contracts). The 5m
bar at 15:00 inherited the 29562 open, which is the print NOISE trained on.

Re-pull, never hand-patch: the replacement bars are aggregated from the NT 10s capture
(C:\\EdgeLog\\ohlc\\NQ_10s.csv) with the same `aggregate()` the 1m backfill uses. Highs and
lows of the rebuilt minutes match the master to the tick on every clean neighbour.

For each file the bars touching the window are rebuilt at the file's own timeframe and
bucket anchor, and shifted by the file's own price offset (0 for NOADJ, the roll
adjustment for ADJ / FADJ). Before writing, the same rebuild is checked against the
file's CLEAN bars that day; a file that does not match there is refused.

Run:  python tools/repair_master_window.py --inst NQ --day 2026-10-30 \\
          --start 14:53 --end 15:03 [--write]        (dry run by default)
"""
import argparse
import glob
import os
import shutil
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from backfill_1m_from_10s import aggregate  # noqa: E402
from augur_engine.master_write import write_master_csv  # noqa: E402

TZ = "America/New_York"
TF_SEC = {"1m": 60, "2m": 120, "5m": 300, "15m": 900, "30m": 1800, "60m": 3600}


def et_epoch(day, hhmm):
    return int(pd.Timestamp("%s %s" % (day, hhmm), tz=TZ).timestamp())


def resample(m1, sec, anchor):
    d = m1.copy()
    d["b"] = anchor + ((d["time"] - anchor) // sec) * sec
    out = d.groupby("b").agg(open=("open", "first"), high=("high", "max"),
                             low=("low", "min"), close=("close", "last"),
                             volume=("volume", "sum")).reset_index()
    return out.rename(columns={"b": "time"})


def repair_file(path, tf, m1_day, w0, w1, write, bak_tag):
    sec = TF_SEC[tf]
    df = pd.read_csv(path, low_memory=False)
    d0, d1 = int(m1_day["time"].min()), int(m1_day["time"].max())
    day = df[(df["time"] >= d0) & (df["time"] <= d1)]
    if day.empty:
        return "no rows that day"
    anchor = int(day["time"].iloc[0])
    built = resample(m1_day, sec, anchor)
    hit = built[(built["time"] + sec > w0) & (built["time"] <= w1)]
    clean = built[~built["time"].isin(hit["time"])]
    j = day.merge(clean, on="time", suffixes=("", "_b"))
    if len(j) < 5:
        return "REFUSED: only %d clean bars to check" % len(j)
    off = (j["close"] - j["close_b"]).median()
    ok = ((j["high"] - j["high_b"] - off).abs() < 0.01) & ((j["low"] - j["low_b"] - off).abs() < 0.01)
    if ok.mean() < 0.9:
        return "REFUSED: rebuild matches only %.0f%% of clean bars (offset %.2f)" % (100 * ok.mean(), off)
    new = hit.copy()
    for c in ("open", "high", "low", "close"):
        new[c] = new[c] + off
    old = df[df["time"].isin(new["time"])]
    for c in [c for c in df.columns if c not in new.columns]:
        fill = day[c].dropna()
        new[c] = fill.iloc[0] if len(fill) else None
    new = new[df.columns]
    out = pd.concat([df[~df["time"].isin(new["time"])], new]).sort_values("time")
    out = out.reset_index(drop=True)
    msg = "offset %+.2f, clean match %d/%d, bars replaced %d, added %d, rows %d -> %d" % (
        off, ok.sum(), len(j), len(old), len(new) - len(old), len(df), len(out))
    if write:
        shutil.copy2(path, path + bak_tag)
        write_master_csv(out, path)
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="NQ")
    ap.add_argument("--day", required=True)
    ap.add_argument("--start", required=True, help="first bad 1m bar, ET HH:MM")
    ap.add_argument("--end", required=True, help="last bad 1m bar, ET HH:MM")
    ap.add_argument("--ten-sec", default=r"C:\EdgeLog\ohlc\NQ_10s.csv")
    ap.add_argument("--root", default=ROOT, help="checkout that holds augur_uploads + registry")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    up = os.path.join(a.root, "augur_uploads")
    w0, w1 = et_epoch(a.day, a.start), et_epoch(a.day, a.end)
    d10 = pd.read_csv(a.ten_sec)
    # 10s rows are stamped at bar END; keep the whole ET day for the clean-bar check
    lo, hi = et_epoch(a.day, "00:00"), et_epoch(a.day, "23:59") + 60
    m1 = aggregate(d10[(d10["time"] > lo) & (d10["time"] <= hi)])
    thin = m1[(m1["time"] >= w0) & (m1["time"] <= w1) & (m1["_n"] < 6)]
    if len(thin):
        sys.exit("10s capture is thin inside the window (%d partial minutes) - refusing" % len(thin))
    win = m1[(m1["time"] >= w0) & (m1["time"] <= w1)].drop(columns=["_n"])

    def patched_day(fname):
        # the master's own 1m day with ONLY the bad minutes swapped for the 10s rebuild, so a
        # higher timeframe rebuilt from it matches the master's resampler bar for bar
        d = pd.read_csv(os.path.join(up, fname), usecols=["time", "open", "high", "low",
                                                           "close", "volume"])
        d = d[(d["time"] >= lo) & (d["time"] < hi) & ~d["time"].isin(win["time"])]
        d = d[(d["time"] < w0) | (d["time"] > w1)]
        return pd.concat([d, win[d.columns]]).sort_values("time").reset_index(drop=True)

    bases = {"eth": patched_day("NOADJ_%s_1m_ETH.csv" % a.inst),
             "rth": patched_day("NOADJ_%s_1m_RTH.csv" % a.inst)}

    conn = sqlite3.connect(os.path.join(a.root, "optimizer_history.db"))
    reg = pd.read_sql("SELECT id, filename, name, timeframe, source, rows FROM csv_files "
                      "WHERE is_master=1 AND instrument=?", conn, params=(a.inst,))
    tag = ".bak-repair-%s" % a.day.replace("-", "")
    for _, r in reg.iterrows():
        tf = r["timeframe"]
        if tf not in TF_SEC:
            continue
        path = None
        for cand in (r["filename"], r["name"]):
            if cand and os.path.exists(os.path.join(up, cand)):
                path = os.path.join(up, cand)
                break
        if not path:
            continue
        # the day's 1m base must cover the file's session; RTH files take only RTH minutes
        base = bases["rth" if str(r["source"]).endswith("rth") else "eth"]
        msg = repair_file(path, tf, base, w0, w1, a.write, tag)
        print("%-24s %-4s %s" % (os.path.basename(path), tf, msg))
        if a.write and msg.startswith("offset"):
            n = int(msg.rsplit("-> ", 1)[1])
            conn.execute("UPDATE csv_files SET rows=? WHERE id=?", (n, int(r["id"])))
    conn.commit()
    conn.close()
    if not a.write:
        print("\ndry run: nothing written (add --write)")


if __name__ == "__main__":
    main()
