# splice_nt_sessions.py - fill whole-session holes in the ES/NQ no-adjust masters from NinjaTrader 1-minute history.
#
# WHY (TBIS data QA, MANAGER #44/#49, 2026-10-10). The Databento source stops early on two real sessions,
# 2020-02-28 (last bar 10:58 ET) and 2020-06-30 (10:10 ET), in every ES and NQ master - 1m to 60m, RTH and ETH,
# no-adjust, TradingView and roll-corrected alike - which leaves four daily returns undefined. Nothing in the
# house can rebuild them; PAPER-NT8's EdgeLogHistFetch add-on pulls the missing minutes from NinjaTrader.
#
# WHAT IT DOES, per hole date and root (ES / NQ):
#   1. Reads the NT file: 1-minute bars stamped at bar END (unix UTC). Converts to bar START, the house convention.
#   2. For every registered no-adjust and TradingView master of that root (1m..60m, RTH or ETH) it re-derives bars
#      at the master's timeframe from the NT minutes, with the house rule (tools/refresh_resampled_masters.py):
#      GRID buckets anchored at the session open (09:30 ET RTH, 18:00 ET ETH), labelled by the earliest actual
#      minute; ROW-COUNT pairs for 2m.
#   3. ACCEPTANCE before touching anything, per master: (a) the same rule applied to the house 1m no-adjust master
#      on a full reference session must reproduce that master's own bars exactly (prices; volume too unless the
#      master is a TradingView export) - otherwise the rule is not this master's rule and the master is refused;
#      (b) on the hole day, every bar the master already has that lies wholly before the truncation must agree
#      with the NT-derived bar to within one tick after a CONSTANT level offset (0 for no-adjust; the
#      back-adjustment for a TradingView master). Any refusal names the master and the reason.
#   4. Splice: keep the master's own bars before the truncated bucket, add the NT-derived bars from there to the
#      session end (shifted by that offset), write through the master-write guard (atomic, refuses to lose rows),
#      update the registry row count, and record the splice (NT file sha256, rows added) in the provenance JSON.
# The roll-corrected ADJ/FADJ twins are NOT touched here: rebuild them afterwards with
# tools/build_adjusted_masters.py, then re-run the TTM #459 parity (355 trades, $72,716 on ADJ ES 30m).
#
# Run (dry run is the default; nothing is written without --commit):
#   python tools/splice_nt_sessions.py --root ES --date 2020-02-28 --nt C:\EdgeLog\nt_hist\out\ES_0320_1m_20200228.csv
#   python tools/splice_nt_sessions.py ... --commit
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.master_write import write_master_csv  # noqa: E402

ET = "US/Eastern"
TICK = 0.25
SPLICE_SOURCES = ("db_noadj_rth", "db_noadj_eth", "tv")
TF_MIN = {"1m": 1, "2m": 2, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


# ----------------------------------------------------------------------------- time helpers
def to_et(sec):
    return pd.to_datetime(pd.Series(sec), unit="s", utc=True).dt.tz_convert(ET)


def session_window(date, session):
    """[start, end) of the session that trades on `date` (ET). ETH opens 18:00 ET the evening before."""
    d = pd.Timestamp(date, tz=ET)
    if session == "rth":
        return d + pd.Timedelta(hours=9, minutes=30), d + pd.Timedelta(hours=16)
    return d - pd.Timedelta(hours=6), d + pd.Timedelta(hours=17)


def _epoch(ts):
    return int(pd.Timestamp(ts).tz_convert("UTC").timestamp())


# ----------------------------------------------------------------------------- the NT file
def load_nt(path, period_s=60):
    """NinjaTrader HistFetch output -> start-stamped 1m frame (time, open, high, low, close, volume)."""
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    need = ("time", "open", "high", "low", "close", "volume")
    missing = [c for c in need if c not in cols]
    if missing:
        raise ValueError(f"{os.path.basename(path)}: missing columns {missing}")
    out = pd.DataFrame({c: df[cols[c]] for c in need})
    out["time"] = out["time"].astype("int64") - period_s          # bar END -> bar START
    return out.sort_values("time").drop_duplicates("time").reset_index(drop=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- the house resample rule
def derive(m1, tf, session, date):
    """Bars at `tf` minutes for one session, from start-stamped 1m bars `m1` (house rule)."""
    s0, s1 = session_window(date, session)
    et = to_et(m1["time"].values)
    keep = ((et >= s0) & (et < s1)).values
    x = m1[keep].copy()
    if x.empty:
        return x
    if tf == 1:
        return x.reset_index(drop=True)
    et = to_et(x["time"].values)
    if tf == 2:                                                   # ROW-COUNT: consecutive pairs from session start
        key = np.arange(len(x)) // 2
    else:                                                         # GRID anchored at the session open
        key = ((et - s0).dt.total_seconds() // (tf * 60)).astype(int).values
    g = x.groupby(key, sort=True)
    return pd.DataFrame({"time": g["time"].first().values, "open": g["open"].first().values,
                         "high": g["high"].max().values, "low": g["low"].min().values,
                         "close": g["close"].last().values, "volume": g["volume"].sum().values})


def _rows_in(df, date, session):
    s0, s1 = session_window(date, session)
    et = to_et(df["time"].values)
    return df[((et >= s0) & (et < s1)).values]


# ----------------------------------------------------------------------------- acceptance + splice
class Refused(Exception):
    pass


def acceptance_reference(master, parent_1m, tf, session, ref_date, check_volume):
    """The rule must reproduce the master's own bars on a full reference session (from the house 1m parent)."""
    want = _rows_in(master, ref_date, session).reset_index(drop=True)
    got = derive(parent_1m, tf, session, ref_date).reset_index(drop=True)
    if len(want) == 0 or len(want) != len(got) or not (want["time"].values == got["time"].values).all():
        raise Refused(f"reference {ref_date}: {len(want)} master bars vs {len(got)} derived - the rule does not "
                      f"reproduce this master's bar times")
    off = (want["close"] - got["close"]).round(6)
    if off.nunique() != 1:
        raise Refused(f"reference {ref_date}: level offset is not constant ({off.min()}..{off.max()})")
    o = float(off.iloc[0])
    for c in ("open", "high", "low"):
        if not np.allclose(want[c] - got[c], o, atol=1e-6):
            raise Refused(f"reference {ref_date}: {c} does not match the rule")
    if check_volume and not (want["volume"].values == got["volume"].values).all():
        raise Refused(f"reference {ref_date}: volume does not match the rule")
    return o


def splice_plan(master, nt_1m, tf, session, date, ref_offset):
    """New master frame with the hole day completed, plus a report. Raises Refused on any disagreement."""
    have = _rows_in(master, date, session)
    if have.empty:
        raise Refused(f"{date}: the master has no bar at all that session - not a truncation, will not guess")
    derived = derive(nt_1m, tf, session, date)
    if derived.empty:
        raise Refused(f"{date}: the NT file has no minutes in this session")
    last_have = int(have["time"].max())
    # The master's last bar on the day was built from a truncated source, so it may be partial: every bucket from
    # the one holding the master's last bar onward is replaced; everything before it must agree with NT.
    cut = last_have
    before = derived[derived["time"] < cut].merge(have[have["time"] < cut], on="time", suffixes=("_nt", "_m"))
    if len(before) < 1:
        raise Refused(f"{date}: no overlapping bar before the truncation to check the NT level against")
    off = before["close_m"] - before["close_nt"]
    level = float(off.median())
    if abs(level - ref_offset) > TICK + 1e-9:
        raise Refused(f"{date}: NT level offset {level:+.2f} differs from the master's own {ref_offset:+.2f}")
    agree = (off - level).abs() <= TICK + 1e-9
    if agree.mean() < 0.9:
        raise Refused(f"{date}: only {agree.mean():.0%} of {len(before)} overlapping bars agree within one tick")
    add = derived[derived["time"] >= cut].copy()
    if "source" in master.columns:                                # the masters' row-provenance column
        add["source"] = "nt_hist_splice"
    for c in ("open", "high", "low", "close"):
        add[c] = add[c] + level
    s1 = _epoch(session_window(date, session)[1])
    replace = ((master["time"] >= cut) & (master["time"] < s1)).values
    stray = master[replace & ~master["time"].isin(add["time"]).values]
    if len(stray):
        raise Refused(f"{date}: {len(stray)} master bar(s) after the truncation are not in the NT data")
    new = pd.concat([master[~replace], add[list(master.columns)]], ignore_index=True)
    new = new.sort_values("time").reset_index(drop=True)
    if new["time"].duplicated().any():
        raise Refused(f"{date}: splice would duplicate a timestamp")
    rep = dict(overlap_bars=len(before), overlap_agree=float(agree.mean()), max_overlap_diff=float((off - level).abs().max()),
               level_offset=level, replaced_from=str(to_et([cut]).iloc[0])[:16], bars_added=len(new) - len(master),
               bars_written_for_day=len(add))
    return new, rep


# ----------------------------------------------------------------------------- registry + run
def targets(db, root, date):
    con = sqlite3.connect(db)
    rows = con.execute("select id, name, filename, timeframe, source, rows, provenance from csv_files "
                       "where is_master=1 and instrument=? and date_from<=? and date_to>=?", (root, date, date)).fetchall()
    con.close()
    return [r for r in rows if r[4] in SPLICE_SOURCES and r[3] in TF_MIN]


def parent_1m(db, root, session):
    con = sqlite3.connect(db)
    r = con.execute("select filename from csv_files where is_master=1 and instrument=? and timeframe='1m' and source=?",
                    (root, f"db_noadj_{session}")).fetchone()
    con.close()
    if not r:
        raise SystemExit(f"no {root} 1m db_noadj_{session} master registered")
    return r[0]


def reference_date(parent, date, session):
    """The last full session before `date` in the 1m parent."""
    et = to_et(parent["time"].values)
    d = et.dt.strftime("%Y-%m-%d")
    days = sorted(set(d[(et < pd.Timestamp(date, tz=ET)).values]))
    for day in reversed(days[-10:]):
        n = len(_rows_in(parent, day, session))
        if (session == "rth" and n == 390) or (session == "eth" and n >= 1300):
            return day
    raise SystemExit("no full reference session in the 10 days before the hole")


def record_splice(con, mid, provenance, entry, rows):
    try:
        p = json.loads(provenance or "{}")
        if not isinstance(p, dict):
            raise ValueError
    except ValueError:
        p = None
    if p is not None:
        p.setdefault("splices", []).append(entry)
        con.execute("update csv_files set rows=?, provenance=? where id=?", (rows, json.dumps(p), mid))
    else:
        con.execute("update csv_files set rows=? where id=?", (rows, mid))


def run(root, date, nt_path, commit=False, db=None, uploads=None, log=print):
    db = db or os.path.join(ROOT, "optimizer_history.db")
    uploads = uploads or os.path.join(ROOT, "augur_uploads")
    nt = load_nt(nt_path)
    nt_sha = sha256(nt_path)
    parents = {}
    results = []
    for mid, name, fn, tf_s, src, nrows, prov in targets(db, root, date):
        session = "eth" if src.endswith("_eth") or "ETH" in name else "rth"
        tf = TF_MIN[tf_s]
        if session not in parents:
            pf = parent_1m(db, root, session)
            parents[session] = pd.read_csv(os.path.join(uploads, pf))
        par = parents[session]
        path = os.path.join(uploads, fn)
        m = pd.read_csv(path)
        try:
            ref = reference_date(par, date, session)
            off = acceptance_reference(m, par, tf, session, ref, check_volume=(src != "tv"))
            new, rep = splice_plan(m, nt, tf, session, date, off)
        except Refused as e:
            log(f"REFUSED  #{mid} {name}: {e}")
            results.append((mid, name, "refused", str(e)))
            continue
        log(f"{'SPLICE ' if commit else 'DRY-RUN'}  #{mid} {name}: +{rep['bars_added']} bars (day rebuilt from "
            f"{rep['replaced_from']}), overlap {rep['overlap_bars']} bars, {rep['overlap_agree']:.0%} within a tick, "
            f"max diff {rep['max_overlap_diff']:.2f}, level {rep['level_offset']:+.2f} (ref {ref})")
        if commit and rep["bars_added"] > 0:
            write_master_csv(new, path, known_rows=nrows)
            con = sqlite3.connect(db)
            record_splice(con, mid, prov, dict(date=date, nt_file=os.path.basename(nt_path), nt_sha256=nt_sha,
                                                rows_added=rep["bars_added"], at=datetime.now(timezone.utc).isoformat()[:19],
                                                by="tools/splice_nt_sessions.py"), len(new))
            con.commit(); con.close()
        results.append((mid, name, "spliced" if commit else "planned", rep))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fill truncated ES/NQ sessions from NinjaTrader 1-minute history.")
    ap.add_argument("--root", required=True, choices=("ES", "NQ"))
    ap.add_argument("--date", required=True, help="the truncated session's trade date, YYYY-MM-DD")
    ap.add_argument("--nt", required=True, help="EdgeLogHistFetch output (1m, END-stamped unix UTC)")
    ap.add_argument("--commit", action="store_true", help="write; the default is a dry run")
    a = ap.parse_args(argv)
    res = run(a.root, a.date, a.nt, a.commit)
    bad = [r for r in res if r[2] == "refused"]
    print(f"{len(res) - len(bad)} master(s) {'spliced' if a.commit else 'ready'}, {len(bad)} refused."
          + ("" if a.commit else " Dry run - nothing written. Re-run with --commit, then tools/build_adjusted_masters.py."))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
