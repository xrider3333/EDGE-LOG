"""BUILD ROLL-CORRECTED NQ AND ES MASTERS, BESIDE THE NO-ADJUST ONES.

WHY (owner GO on ROLL_AUDIT.md decision 13, 2026-09-26). Every NQ/ES master we own is
NON-ADJUSTED: each quarterly contract change leaves a step in the price that is not a price
move. ROLL_AUDIT measured what that costs - a strategy holding across one books the step as
profit, its stops fire on it, and any indicator reading over it sees a range that never
traded. These new masters remove the steps using the committed roll table, so a re-validation
can be run on corrected data and compared against the run it is replacing.

NOTHING EXISTING IS TOUCHED. Every output is a NEW file with a NEW registry row. No master a
live or paper leg reads is modified, renamed or re-registered, and the no-adjust series stay
exactly as they are - they are still the right data for anything that wants the real tradeable
price of the front contract.

WHAT GETS BUILT, AND WHY TWO FAMILIES.
  ADJ_*  (source db_adj_<session>)  - back-adjusted. The newest segment keeps its real
         prices and history is shifted to match, so a price difference between any two bars
         is a real difference. This is the set for anything that HOLDS across a roll:
         ENGU-Q, TTM, ORB, and the books built from them.
  FADJ_* (source db_fadj_<session>) - forward-adjusted. The OLDEST segment keeps its real
         prices instead. Identical bar-to-bar differences, different absolute levels. This is
         for rules and model features keyed to a level learned from history, because
         back-adjusting moves sixteen years of history under them (ROLL_AUDIT 6.5). Built only
         for the four masters the level-based consumers actually read, listed in FADJ_ONLY
         below - building it for everything would double the Library for no reader.

MIXED BARS ARE MARKED IN THE FILE ITSELF. Twice in 2026 a switch happened INSIDE a bar, so
that bar's open is one contract and its close is another, and its high and low are a blend
that cannot be recovered. Those bars are rebuilt as a body with no wick (high and low equal
the max and min of the adjusted open and close) and carry `synthetic=1` plus
`source=roll_synthetic`, so a reader can find and exclude them without consulting a document.
`augur_engine/rolls.py` `guard_masks` exposes the same information as a no-fill mask.

THE FOUR 2026 OFFSETS ARE ESTIMATES. They were measured against the other root and against
the NinjaTrader capture, not against the raw feed, which stops 2026-06-07. This was raised as
a blocker before the work started and the owner said go, so the uncertainty is carried in the
data: the roll table marks them `status=estimated` with a range, the provenance JSON on every
master built here records how many estimated switches it contains, and this script prints it.
Replacing them with measured values needs a Databento re-pull for 2026-06..09
(docs/DATA_TAIL_2026.md). Do not quote a result spanning one of them as if it were measured.

WHAT THIS DOES NOT DO. It does not fill the 2026 summer holes in the 1-minute masters - that
is a separate decision with its own tradeoff (a different feed that disagrees with ours on 2
to 8 percent of prices; docs/DATA_TAIL_2026.md), and it is not mixed into this build so that
an ADJ master is exactly its no-adjust twin plus the table offsets and nothing else. That
property is what makes a before-and-after comparison meaningful.

    python tools/build_adjusted_masters.py                 # dry run: what would be built
    python tools/build_adjusted_masters.py --apply
    python tools/build_adjusted_masters.py --apply --only NOADJ_NQ_1m_ETH.csv
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import rolls  # noqa: E402

DEFAULT_UP = os.path.join(ROOT, "augur_uploads")
DEFAULT_DB = os.path.join(ROOT, "optimizer_history.db")

TF_SECONDS = {"1m": 60, "2m": 120, "5m": 300, "15m": 900, "30m": 1800, "60m": 3600}

# The masters a level-based consumer reads, so they also get a forward-adjusted twin:
# KEEL and the NinjaTrader gate read NQ 5m, and the ENGU-Q ER gate reads the 1m 24h series.
FADJ_ONLY = {"NOADJ_NQ_5m_RTH.csv", "NOADJ_NQ_5m_ETH.csv",
             "NOADJ_NQ_1m_ETH.csv", "NOADJ_ES_1m_ETH.csv"}


def noadj_masters(conn):
    """Every registered no-adjust NQ/ES master, as registry rows."""
    q = ("SELECT id,name,filename,instrument,timeframe,session,source,rows "
         "FROM csv_files WHERE is_master=1 AND source LIKE 'db_noadj%' "
         "AND instrument IN ('NQ','ES') ORDER BY filename")
    return [dict(zip(("id", "name", "filename", "instrument", "timeframe",
                      "session", "source", "rows"), r)) for r in conn.execute(q)]


def out_name(src_filename, method):
    """ADJ_NQ_1m_ETH.csv / FADJ_NQ_1m_ETH.csv from NOADJ_NQ_1m_ETH.csv.

    Deliberately a readable name rather than a random master_<hex>.csv: these are reference
    data a person will look for on disk, and the no-adjust masters they mirror are named the
    same way.
    """
    stem = src_filename[len("NOADJ_"):] if src_filename.startswith("NOADJ_") else src_filename
    return ("ADJ_" if method == "back" else "FADJ_") + stem


def build_one(src_path, root, timeframe, method):
    """Read a no-adjust master, apply the roll table, return (frame, stats)."""
    d = pd.read_csv(src_path)
    t = d["time"].values.astype("int64")
    tf = TF_SECONDS[timeframe]
    o, h, l, c = (d[k].values.astype("float64") for k in ("open", "high", "low", "close"))
    fn = rolls.back_adjust if method == "back" else rolls.forward_adjust
    ao, ah, al, ac, info = fn(t, o, h, l, c, root, tf)

    out = pd.DataFrame({"time": t, "open": ao, "high": ah, "low": al, "close": ac,
                        "volume": d["volume"].values})
    syn = info["synthetic"].astype(bool)
    # keep the original row provenance, but say plainly where a bar was rebuilt
    src_col = d["source"].astype(str).values if "source" in d.columns else np.array(["existing"] * len(d))
    src_col = src_col.copy()
    src_col[syn] = "roll_synthetic"
    out["source"] = src_col
    out["synthetic"] = syn.astype(int)

    # Two different questions, both worth recording. `estimated_in_series` is how many
    # estimated switches fall inside this master's own bars. `levels_rest_on_estimate` is
    # whether the SHIFT applied to it contains an estimate at all - true for every
    # back-adjusted master, because back-adjusting leans on every later switch, including the
    # 2026 ones. A reader who only sees the first number would wrongly think a pre-2026 window
    # is fully measured.
    n_est = sum(1 for r in info["switch_rows"] if r["status"] != "exact")
    stats = dict(rows=len(out), switches=info["n_switches_total"], synthetic=int(syn.sum()),
                 estimated=n_est, in_series_switches=info["n_switches"],
                 levels_rest_on_estimate=bool(info["levels_rest_on_estimate"]),
                 method=info["method"],
                 shift_oldest=float(info["shift_close"][0]) if len(out) else 0.0,
                 shift_newest=float(info["shift_close"][-1]) if len(out) else 0.0,
                 first_et=_et(t[0]) if len(t) else "", last_et=_et(t[-1]) if len(t) else "")
    return out, stats


def _et(sec):
    return str(pd.to_datetime(int(sec), unit="s", utc=True)
               .tz_convert("US/Eastern").strftime("%Y-%m-%d %H:%M"))


def register(conn, filename, src, frame, stats, method):
    """Insert or update this adjusted master's registry row. Never touches the source row."""
    sess = str(src["session"] or "").lower()
    source = ("db_adj_" if method == "back" else "db_fadj_") + (sess or "eth")
    label = "back-adjusted" if method == "back" else "forward-adjusted"
    name = "%s %s %s - %s" % (src["instrument"], src["timeframe"], sess.upper(), label)
    d_from = str(pd.to_datetime(int(frame["time"].min()), unit="s", utc=True)
                 .tz_convert("US/Eastern").date())
    d_to = str(pd.to_datetime(int(frame["time"].max()), unit="s", utc=True)
               .tz_convert("US/Eastern").date())
    prov = json.dumps(dict(
        source=source, built_at=dt.datetime.now().strftime("%Y-%m-%dT%H:%M"),
        built_by="tools/build_adjusted_masters.py",
        derived_from=src["filename"], method=method,
        roll_table="tools/data/rolls_%s.csv" % src["instrument"],
        switches_applied=stats["switches"], estimated_switches=stats["estimated"],
        switches_inside_this_span=stats["in_series_switches"],
        levels_rest_on_estimate=stats["levels_rest_on_estimate"],
        synthetic_bars=stats["synthetic"], total_rows=stats["rows"],
        shift_at_oldest_bar=stats["shift_oldest"], shift_at_newest_bar=stats["shift_newest"],
        caveat=("%d of the switches applied carry an ESTIMATED offset (the 2026 tail; the raw "
                "feed stops 2026-06-07)%s. See docs/ROLL_ADJUSTED_MASTERS.md and "
                "docs/DATA_TAIL_2026.md."
                % (stats["estimated"],
                   ", and because back-adjusting leans on every later switch, the price LEVELS "
                   "of this master's WHOLE history rest on them - not just its 2026 bars"
                   if stats["levels_rest_on_estimate"] and method == "back" else ""))
               if stats["estimated"] else "",
        source_csv_ids=[]))
    row = conn.execute("SELECT id FROM csv_files WHERE filename=?", (filename,)).fetchone()
    if row:
        conn.execute("UPDATE csv_files SET name=?,instrument=?,rows=?,date_from=?,date_to=?,"
                     "timeframe=?,is_master=1,source=?,provenance=?,session=? WHERE id=?",
                     (name, src["instrument"], stats["rows"], d_from, d_to,
                      src["timeframe"], source, prov, sess, row[0]))
        return "updated", row[0]
    cur = conn.execute(
        "INSERT INTO csv_files (name,filename,instrument,rows,date_from,date_to,created_at,"
        "timeframe,is_master,source,provenance,session) VALUES (?,?,?,?,?,?,?,?,1,?,?,?)",
        (name, filename, src["instrument"], stats["rows"], d_from, d_to,
         dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), src["timeframe"], source, prov, sess))
    return "inserted", cur.lastrowid


def write_atomic(path, frame):
    """Write beside the target and rename over it.

    Five runner processes read these files continuously and the refresh runs on its own
    thread, so an in-place write can be read half-finished - a backtest on a truncated master
    does not crash, it quietly answers on less data. Same reasoning as save_master_csv.
    """
    tmp = "%s.tmp-%d" % (path, os.getpid())
    frame.to_csv(tmp, index=False)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the files and register them")
    ap.add_argument("--reregister-only", action="store_true",
                    help="refresh the registry rows from the files already on disk, without "
                         "rewriting 1.7 GB of CSV - for a provenance-only change")
    ap.add_argument("--only", default="", help="comma list of source filenames to do")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--uploads", default=DEFAULT_UP)
    a = ap.parse_args()

    # The five runner processes poll this same sqlite file continuously, so a plain connect
    # loses the write lock and the build dies partway through with "database is locked" - which
    # is exactly what happened on the first re-registration attempt. A busy timeout waits for
    # the runner's short reads instead of giving up.
    conn = sqlite3.connect(a.db, timeout=120)
    conn.execute("PRAGMA busy_timeout = 120000")
    want = {x.strip() for x in a.only.split(",") if x.strip()}
    srcs = [m for m in noadj_masters(conn) if not want or m["filename"] in want]
    if not srcs:
        print("no no-adjust NQ/ES masters found (registry %s)" % a.db)
        return 1

    total_est = 0
    for src in srcs:
        tf = src["timeframe"]
        if tf not in TF_SECONDS:
            print("%-24s SKIP - no bar length known for timeframe %r" % (src["filename"], tf))
            continue
        spath = os.path.join(a.uploads, src["filename"])
        if not os.path.exists(spath):
            print("%-24s SKIP - file missing" % src["filename"])
            continue
        methods = ["back"] + (["forward"] if src["filename"] in FADJ_ONLY else [])
        for method in methods:
            fn = out_name(src["filename"], method)
            frame, st = build_one(spath, src["instrument"], tf, method)
            total_est = max(total_est, st["estimated"])
            print("%-24s -> %-24s %s rows, %d switches (%d ESTIMATED), %d synthetic bar(s)"
                  % (src["filename"], fn, format(st["rows"], ","), st["switches"],
                     st["estimated"], st["synthetic"]))
            print("     %s adjust: oldest bar shifted %+.2f, newest %+.2f, span %s .. %s"
                  % (st["method"], st["shift_oldest"], st["shift_newest"],
                     st["first_et"], st["last_et"]))
            if not (a.apply or a.reregister_only):
                continue
            if a.reregister_only:
                if not os.path.exists(os.path.join(a.uploads, fn)):
                    print("     SKIP - %s is not on disk, nothing to re-register" % fn)
                    continue
            else:
                write_atomic(os.path.join(a.uploads, fn), frame)
            what, rid = register(conn, fn, src, frame, st, method)
            conn.commit()
            print("     %s, %s in the registry as id %s"
                  % ("re-registered" if a.reregister_only else "written", what, rid))
    conn.close()
    if total_est:
        print("\nNOTE: %d of the switches applied carry an ESTIMATED offset (the 2026 tail - "
              "the raw feed stops 2026-06-07). A result that spans one is not measured data; "
              "see docs/ROLL_ADJUSTED_MASTERS.md." % total_est)
    if not (a.apply or a.reregister_only):
        print("\nDry run - nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
