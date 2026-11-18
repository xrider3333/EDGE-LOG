"""Register the Databento ZN / RTY / YM no-adjust ETH masters in the master registry (owner 11-18,
via MANAGER: "put the data there so we have it for the future").

The six CSVs (NOADJ_{ZN,RTY,YM}_{1m,5m}_ETH.csv) and their roll tables (ROLLS_*.csv) already sit in
augur_uploads/ (git-ignored). This adds one csv_files row per master (is_master=1, source db_noadj_eth,
session eth) so augur_engine.data.find_master resolves them, and records the known hole days in each
row's provenance and in data/cme_masters_manifest.json.

No RTH cut is built: find_master('RTY','5m',session='eth') is all a caller needs, and ZN's RTH day
(08:20-15:00 ET) is not the equity 09:30-16:00 cut, so an RTH file is a research decision, not a default.

Idempotent: a row whose filename is already registered is updated in place, never duplicated.
NQ / ES rows are never read or written.

usage: python tools/register_cme_masters.py [--db PATH] [--uploads DIR] [--dry-run]
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTS = ("ZN", "RTY", "YM")
TFS = ("1m", "5m")
# CME-wide data holes in the Databento pull (MANAGER 11-18); the NQ/ES masters had these spliced from NT.
HOLE_DAYS = ["2014-10-03", "2020-02-27", "2020-02-28", "2020-06-30"]
STARTS = {"RTY": "2017-07-10"}   # E-mini Russell 2000 moved to CME on 2017-07-10


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def describe(path):
    df = pd.read_csv(path, usecols=["time"])
    t = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("America/New_York")
    days = set(t.dt.strftime("%Y-%m-%d"))
    return {"rows": int(len(df)), "first": t.iloc[0].strftime("%Y-%m-%d %H:%M"),
            "last": t.iloc[-1].strftime("%Y-%m-%d %H:%M"),
            "hole_days_present": {d: (d in days) for d in HOLE_DAYS}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(ROOT, "optimizer_history.db"))
    ap.add_argument("--uploads", default=os.path.join(ROOT, "augur_uploads"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    entries = []
    for r in ROOTS:
        rolls = os.path.join(a.uploads, "ROLLS_%s.csv" % r)
        for tf in TFS:
            fn = "NOADJ_%s_%s_ETH.csv" % (r, tf)
            p = os.path.join(a.uploads, fn)
            if not os.path.exists(p):
                sys.exit("missing %s" % p)
            d = describe(p)
            prov = {"source": "db_noadj_eth", "vendor": "Databento GLBX.MDP3 ohlcv, front month, no back-adjust",
                    "built_from": "C:/EdgeLog/databento/masters/" + fn, "registered_by": "tools/register_cme_masters.py",
                    "registered_at": dt.datetime.now().strftime("%Y-%m-%dT%H:%M"),
                    "columns": "time,open,high,low,close,volume (no source column)", "session_cut": "none (full ETH)",
                    "date_from": d["first"], "date_to": d["last"], "total_rows": d["rows"],
                    "sha256": sha256(p), "bytes": os.path.getsize(p),
                    "rolls_file": os.path.basename(rolls) if os.path.exists(rolls) else None,
                    "known_hole_days": HOLE_DAYS, "hole_days_present": d["hole_days_present"],
                    "series_start": STARTS.get(r)}
            entries.append({"name": "%s %s ETH - no-adj" % (r, tf), "filename": fn, "instrument": r,
                            "rows": d["rows"], "date_from": d["first"][:10], "date_to": d["last"][:10],
                            "timeframe": tf, "source": "db_noadj_eth", "session": "eth", "provenance": prov})
            print("%-24s rows %10d  %s .. %s  %6.1f MB  holes present %s" % (
                fn, d["rows"], d["first"], d["last"], prov["bytes"] / 1e6, d["hole_days_present"]))

    man = {"what": "Databento no-adjust ETH masters for ZN / RTY / YM", "known_hole_days": HOLE_DAYS,
           "series_start": STARTS, "files": [{k: e["provenance"][k] for k in ("sha256", "bytes", "date_from", "date_to",
                                                                             "total_rows")} | {"filename": e["filename"]}
                                            for e in entries]}
    if a.dry_run:
        print(json.dumps(man, indent=1))
        return
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "cme_masters_manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, indent=1)
        f.write("\n")

    conn = sqlite3.connect(a.db)
    try:
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for e in entries:
            pj = json.dumps(e["provenance"])
            row = conn.execute("SELECT id FROM csv_files WHERE filename=?", (e["filename"],)).fetchone()
            if row:
                conn.execute("UPDATE csv_files SET name=?,instrument=?,rows=?,date_from=?,date_to=?,timeframe=?,"
                             "is_master=1,source=?,provenance=?,session=? WHERE id=?",
                             (e["name"], e["instrument"], e["rows"], e["date_from"], e["date_to"], e["timeframe"],
                              e["source"], pj, e["session"], row[0]))
                print("updated", e["filename"], "id", row[0])
            else:
                cur = conn.execute("INSERT INTO csv_files (name,filename,instrument,rows,date_from,date_to,created_at,"
                                   "timeframe,is_master,source,provenance,session) VALUES (?,?,?,?,?,?,?,?,1,?,?,?)",
                                   (e["name"], e["filename"], e["instrument"], e["rows"], e["date_from"], e["date_to"],
                                    now, e["timeframe"], e["source"], pj, e["session"]))
                print("registered", e["filename"], "id", cur.lastrowid)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
