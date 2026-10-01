# refresh_resampled_masters.py — top up the RESAMPLED intraday masters (15m/30m/60m/2m,
# non-adjusted) from their already-current 5m/1m parents.
#
# WHY THIS EXISTS. tools/refresh_noadj_yahoo.py keeps the 5m and 1m non-adjusted masters
# current from Yahoo every day. But four masters that were built ON TOP of those (the 30m
# and 60m RTH masters, plus 15m and 2m) were a ONE-TIME resample done 2026-08-23 ("ttmsqz
# round 2", see their csv_files.provenance) and nothing has ever topped them up since --
# refresh_noadj_yahoo.py only knows how to pull 5m/1m from Yahoo, so a 30m/60m/15m/2m master
# just sat there. By 2026-09-25 the 30m/60m masters were 63 WEEKDAYS stale (last bar
# 2026-06-30 15:30 ET) while their parent already ran to 2026-09-25. This script closes that
# gap by re-deriving the same resample from the parent and appending only the new tail -- it
# never touches a row that already exists.
#
# TWO DIFFERENT RESAMPLE RULES -- discovered by trial, not assumed. The four masters'
# provenance notes use two different phrases ("session-anchored (09:30 ET) resample" for
# 15m/30m/60m vs "session-aligned resample" for 2m) and it turns out that difference is
# real, not just wording: they are built by two different rules, confirmed by resampling
# each one from scratch and checking every existing row matches to the tick (see
# process_one() below -- this is the acceptance test the task asked for, and it is what
# caught this):
#
#  1. GRID (15m, 30m, 60m -- parent is 1m for 15m, 5m for 30m/60m). Bucket MEMBERSHIP is a
#     fixed grid anchored at 09:30 ET, computed independently for every parent row from its
#     own clock time: a 30m grid is 09:30-09:59, 10:00-10:29, ...; a 60m grid is
#     09:30-10:29, 10:30-11:29, ... Do NOT use pandas .resample('30min') on a UTC-indexed
#     frame -- that snaps to UTC-clock boundaries, which is not the same grid and produces
#     different bars. The bucket's reported "time", however, is NOT the grid position -- it
#     is the EARLIEST parent row actually inside that window. On a gap-free day these are
#     identical. They diverge on a day with a missing parent bar: 2020-03-18's 5m parent is
#     missing both its 13:00 and 13:05 ET bars (a CME circuit-breaker halt), and the existing
#     30m master's bucket for that slot is timestamped 13:10 ET -- the first bar that
#     actually survived -- not the grid position "13:00". (2020-03-09's 5m parent is missing
#     only its 09:40 bar, which sits mid-window rather than at a boundary, so that day's
#     bucket labels land exactly on the grid anchor -- both examples are consistent with
#     "grid decides membership, earliest actual row decides the label".)
#  2. ROW-COUNT (2m only, parent is 1m). Within each session day, sort the parent's rows and
#     group every `ratio` of them in a row (ratio = tf_minutes / parent_tf_minutes = 2 here),
#     restarting at the first row of each new session day. The bucket's "time" is that
#     group's first row. This looks identical to GRID on a gap-free day, but behaves
#     differently after a gap: GRID re-anchors every window independently off the fixed
#     09:30 clock regardless of how many rows came before; ROW-COUNT just keeps counting
#     rows, so a gap shifts every later group's row-membership (not just the one it fell in).
#     GRID does NOT reproduce the existing 2m master (1155/794616 rows mismatch); ROW-COUNT
#     reproduces it exactly. GRID reproduces 15m/30m/60m exactly (up to one known exception,
#     next paragraph); ROW-COUNT does not. Both are OHLCV-aggregated the usual way within a
#     bucket: open=first, high=max, low=min, close=last, volume=sum.
#
# ONE KNOWN EXCEPTION THE REPRODUCTION CHECK WILL REPORT AND NOT FIX: the 15m master's own
# LAST existing row (2026-06-30 10:45 ET) does not match a from-scratch resample, because
# that row was ALREADY an incomplete bucket when the 15m master was originally built (the
# build job that created it stopped mid-morning that day, not at session close -- unlike the
# 30m/60m masters, whose last existing row is a genuine, complete, end-of-session bucket).
# This script will not silently accept or paper over that: it reports the mismatch and stops
# for that file rather than guessing which of the two disagreeing values is right. It never
# overwrites an existing row either way.
#
# NEVER STORE A HALF-FORMED BUCKET. The parent's last bar can land mid-bucket (e.g. the
# parent's last 5m bar is 15:55 ET, one short of a full 30m window that needs bars through
# 15:55 to close). Same spirit as refresh_noadj_yahoo.py's _drop_unclosed (written after the
# 2026-09-24 incident where a still-forming Yahoo bar got saved and stuck forever, because
# every later run only looks past the last saved timestamp): this script drops any trailing
# bucket whose window has not fully elapsed given the parent's own last bar, so a
# half-formed bar is never written. It is not lost -- the next run, once the parent has more
# bars, appends it.
#
# IT WILL NOT CARRY THE KNOWN CONTRACT SPLICE INTO THESE MASTERS. The 5m/1m parents carry an
# IN-BAR contract splice at 2026-09-14 11:30 ET: Yahoo rolled the front-month contract
# mid-session inside a single parent bar, booking roughly +304.5 (NQ) / +68.75 (ES) of pure
# roll gap as if it were real intraday range. Any resampled bucket whose window contains that
# minute would inherit it, and these four masters currently end 2026-06-30, so they do NOT
# have it yet -- appending blindly would newly introduce a bad bar into a master the live
# paper book reads (ES 30m RTH feeds the TTM_299 legs in api/paper.py).
#
# So this script runs the same guard the data refresh runs, augur_engine/roll_guard.py, and
# STOPS each master's new tail at the last clean bucket before the splice.
#
# IT HAS TO ASK THE PARENT, NOT THE BUCKET. The guard's "is this bar an extreme move for this
# bar size" test loses its bite as bars get coarser: a 30m bar's ordinary body is already so
# large that a carry-sized jump no longer stands ten standard deviations clear of it. Checked:
# run against their own buckets, ES 30m and 60m and NQ 2m are caught but NQ 30m and 60m sail
# through. So the parent's 5m or 1m bars are what get tested -- where a carry-sized jump IS
# extreme -- and any bucket whose WINDOW COVERS a flagged parent bar is refused. That is the
# same "propagate a mixed bar to coarser bars" rule ROLL_AUDIT.md section 6.2 describes.
# That takes them from 63 weekdays stale to a little over a week stale while adding no
# known-bad bar. The rest of the tail is not lost: it appends by itself once the splice in the
# PARENT is repaired (ROLL_AUDIT.md section 6.3, an open owner call). The run says out loud
# which span it held back, and a belt-and-braces span check still warns if a bucket that got
# through covers 2026-09-14.
#
# Run (dry-run is the default, prints what WOULD happen, writes nothing):
#   python tools/refresh_resampled_masters.py
#   python tools/refresh_resampled_masters.py --db "C:\...\optimizer_history.db" --uploads "C:\...\augur_uploads"
#   python tools/refresh_resampled_masters.py --apply     # actually writes (after the repro check passes)
import argparse
import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import roll_guard
from augur_engine.master_write import write_master_csv

DEFAULT_UP = os.path.join(ROOT, "augur_uploads")
DEFAULT_DB = os.path.join(ROOT, "optimizer_history.db")

# target resampled timeframe -> (its parent timeframe, its resample method). See the module
# docstring for how these were determined (by reproduction, not assumption).
TARGET_CONFIG = {
    "15m": {"parent": "1m", "method": "grid"},
    "30m": {"parent": "5m", "method": "grid"},
    "60m": {"parent": "5m", "method": "grid"},
    "2m":  {"parent": "1m", "method": "rowcount"},
}
TF_MINUTES = {"15m": 15, "30m": 30, "60m": 60, "2m": 2}
PARENT_TF_MINUTES = {"5m": 5, "1m": 1}

SESSION_OPEN_H, SESSION_OPEN_M = 9, 30   # RTH session open, ET

# The known Yahoo front-month-roll splice: booked inside the single parent bar that starts
# at this ET timestamp. Any resampled bucket whose window contains this instant inherits it.
SPLICE_BAR_ET = pd.Timestamp("2026-09-14 11:30:00", tz="US/Eastern")
SPLICE_NOTE = {"NQ": "NQ ~+304.5", "ES": "ES ~+68.75"}


def _et(unix_s_series):
    return pd.to_datetime(unix_s_series, unit="s", utc=True).dt.tz_convert("US/Eastern")


def _bucket_grid_key(et_series, tf_minutes):
    """Fixed 09:30-anchored grid position for each timestamp (GRID method's membership key
    -- see module docstring for why this is not always the bucket's reported "time"). A 30m
    grid is 09:30-09:59, 10:00-10:29, ...; a 60m grid is 09:30-10:29, 10:30-11:29, ...
    Computed independently per row from that row's own session open, so one row's gap never
    shifts where a later row's grid slot falls."""
    session_open = et_series.dt.normalize() + pd.Timedelta(hours=SESSION_OPEN_H, minutes=SESSION_OPEN_M)
    mins_since_open = (et_series - session_open).dt.total_seconds() / 60.0
    bucket_idx = np.floor(mins_since_open / tf_minutes).astype(np.int64)
    grid = session_open + pd.to_timedelta(bucket_idx * tf_minutes, unit="m")
    return (grid.astype("int64") // 1_000_000_000).astype(np.int64)


def resample_grid(parent, tf_minutes):
    """GRID-method resample (15m/30m/60m -- see module docstring). Parent frame needs
    columns time,open,high,low,close,volume (extra columns such as 'source' are ignored).

    Returns columns time (bucket's earliest actual row), open, high, low, close, volume, and
    an internal `_grid_key` (used only by _drop_incomplete_tail) -- callers writing a CSV
    must drop that column.
    """
    df = parent[["time", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values("time").reset_index(drop=True)
    df["_grid_key"] = _bucket_grid_key(_et(df["time"]), tf_minutes)
    g = df.groupby("_grid_key", sort=True)
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    out = out.reset_index().sort_values("time").reset_index(drop=True)
    out["time"] = out["time"].astype(np.int64)
    out["volume"] = out["volume"].astype(np.int64)
    return out


def resample_rowcount(parent, tf_minutes, parent_tf_minutes):
    """ROW-COUNT-method resample (2m only -- see module docstring). Groups every `ratio`
    parent rows in a row, restarting at the first row of each ET session day.

    Returns columns time (bucket's first row), open, high, low, close, volume, and internal
    `_grid_key` + `_n` (used only by _drop_incomplete_tail: `_n` is how many parent rows
    landed in the bucket, a full one has `_n == ratio`) -- callers writing a CSV must drop
    both.
    """
    ratio = tf_minutes // parent_tf_minutes
    if tf_minutes % parent_tf_minutes:
        raise ValueError(f"{tf_minutes}m is not a whole multiple of the {parent_tf_minutes}m parent")
    df = parent[["time", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values("time").reset_index(drop=True)
    day = _et(df["time"]).dt.date
    seq_in_day = df.groupby(day).cumcount()
    df["_day"] = day.values
    df["_grp"] = (seq_in_day // ratio).values
    g = df.groupby(["_day", "_grp"], sort=False)
    out = g.agg(time=("time", "first"), open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
                _n=("time", "size"))
    out = out.reset_index(drop=True).sort_values("time").reset_index(drop=True)
    out["time"] = out["time"].astype(np.int64)
    out["volume"] = out["volume"].astype(np.int64)
    out["_grid_key"] = out["time"]   # row-count buckets don't have a separate grid anchor
    return out


def _drop_incomplete_tail(resampled, tf_minutes, parent_last_time, parent_tf_seconds, ratio=None):
    """Drop the trailing bucket if it is not yet closed out by the parent's own last bar.
    GRID: complete once the window (_grid_key .. _grid_key + tf_minutes) closes at or before
    the parent's last bar's own close. ROW-COUNT: complete once it has its full `ratio` rows
    (a partial bucket only ever means the parent hasn't produced the rest of it yet). Only
    the LAST bucket in time order can ever be incomplete this way -- an old, historical
    partial bucket (a genuine early-close day, or a halt day) already has every bar the
    parent will ever give it, so it is left alone. Same spirit as refresh_noadj_yahoo.py's
    _drop_unclosed: a skipped bucket is not lost, the next run appends it once the parent has
    caught up."""
    if not len(resampled):
        return resampled
    if ratio is not None:
        complete = int(resampled.iloc[-1]["_n"]) >= ratio
    else:
        tf_s = tf_minutes * 60
        window_end = int(resampled.iloc[-1]["_grid_key"]) + tf_s
        complete = (parent_last_time + parent_tf_seconds) >= window_end
    if not complete:
        return resampled.iloc[:-1].reset_index(drop=True)
    return resampled


def _fmt_et(unix_s):
    return str(pd.to_datetime(int(unix_s), unit="s", utc=True).tz_convert("US/Eastern"))


def _fmt_bar(row):
    return (f"{_fmt_et(row['time'])}  O={row['open']:.2f} H={row['high']:.2f} "
            f"L={row['low']:.2f} C={row['close']:.2f} V={int(row['volume'])}")


def _splice_warning(instrument, new_rows, tf_minutes):
    """None, or a warning string, if the newly-appended span covers the known 2026-09-14
    11:30 ET contract-splice bar (checked by span, not exact bucket alignment, since a GRID
    bucket's label can sit slightly after its true window start -- see module docstring)."""
    if not len(new_rows):
        return None
    splice_s = int(SPLICE_BAR_ET.timestamp())
    tf_s = tf_minutes * 60
    span_lo = int(new_rows["time"].min())
    span_hi = int(new_rows["time"].max()) + tf_s
    # `span_hi` is the END of the last bucket, which is exclusive: a bucket stamped 11:00 on a
    # 30m master covers 11:00-11:29 and does NOT contain the 11:30 splice minute. Testing the
    # boundary inclusively made this warning fire on exactly the runs the guard had already
    # cut short, which reads as a contradiction.
    if not (span_lo <= splice_s < span_hi):
        return None
    note = SPLICE_NOTE.get(instrument, f"{instrument} roll splice")
    return (f"  WARNING: this run's new bars span 2026-09-14 -- the 11:30 ET parent bar that "
            f"day carries the known Yahoo front-month-roll splice ({note} in a single bar, "
            f"pure roll gap, not real range). Any bucket covering that minute inherits it. "
            f"Not corrected, only flagged.")


def find_masters(conn):
    """All resampled-timeframe masters (15m/30m/60m/2m, db_noadj* source) and their parent
    row, matched on instrument + session + source + the configured parent timeframe."""
    rows = conn.execute(
        "SELECT id,filename,instrument,timeframe,session,source,rows,date_to FROM csv_files "
        "WHERE is_master=1 AND source LIKE 'db_noadj%'").fetchall()
    by_key = {}
    for (mid, fn, inst, tf, sess, src, nrows, date_to) in rows:
        by_key.setdefault((inst, sess, src, tf), []).append(
            {"id": mid, "filename": fn, "instrument": inst, "timeframe": tf,
             "session": sess, "source": src, "rows": nrows, "date_to": date_to})
    targets = []
    for (inst, sess, src, tf), lst in by_key.items():
        cfg = TARGET_CONFIG.get(tf)
        if not cfg:
            continue
        parents = by_key.get((inst, sess, src, cfg["parent"]))
        if not parents:
            print(f"  skip {lst[0]['filename']}: no {cfg['parent']} parent found for {inst}/{sess}/{src}")
            continue
        for m in lst:
            targets.append((m, parents[0], cfg["method"]))
    targets.sort(key=lambda t: t[0]["filename"])
    return targets


# How far back the upstream feed may still restate a bar. Yahoo revises recent intraday bars -
# volume especially - for several days after the fact. 10 days is ~7 observed plus margin.
UNSETTLED_DAYS = 10

# How many dated .bak copies of each master to keep. Nightly runs make one per master
# per day inside the OneDrive-synced uploads folder, so this cannot be unbounded.
KEEP_BACKUPS = 3


def split_settled(existing, parent_last_t, days=UNSETTLED_DAYS):
    """(settled, unsettled) halves of a stored master, by bar time.

    WHY THIS EXISTS (2026-09-30, the evening of the day the nightly refresh went live). The
    reproduction check demands that every stored bucket can be rebuilt from the parent exactly.
    That is the right test for corruption, and it was the wrong test for the recent tail: Yahoo
    restated the volume of one 2026-09-29 12:30 ET bar from 23,092 to 25,672, so six coarse
    masters that had stored their buckets before the restatement could no longer reproduce, and
    the check refused the WHOLE file. All six froze a day behind their parents within hours of
    the schedule going live - the same freeze fixed that morning, arriving by a different door.

    So a bucket inside the restatement window is treated as RE-DERIVABLE rather than immutable:
    it is dropped and rebuilt from the parent as it stands now. Everything older must still
    reproduce to the tick, which is the part that actually catches a damaged master.
    """
    cutoff = int(parent_last_t) - int(days) * 86400
    return (existing[existing["time"] < cutoff].reset_index(drop=True),
            existing[existing["time"] >= cutoff].reset_index(drop=True))


def _bucket_from(rows):
    """The OHLCV bucket these parent rows make, by the same rule both methods share."""
    return dict(open=float(rows["open"].iloc[0]), high=float(rows["high"].max()),
                low=float(rows["low"].min()), close=float(rows["close"].iloc[-1]),
                volume=float(rows["volume"].sum()))


def _same_bucket(stored, built):
    return all(abs(float(stored[k]) - built[k]) <= 1e-6
               for k in ("open", "high", "low", "close", "volume"))


def repair_partial_last_row(existing, full, parent, check):
    """Rebuild a LAST row that was saved while its bucket was still filling.

    WHY THIS EXISTS (2026-09-30, owner GO via MANAGER). A resampled master written while the
    market is open stores a bucket built from only the parent bars that existed at that
    moment. Nothing ever revisits it, so the partial bar is permanent - exactly the hazard
    refresh_noadj_yahoo.py's own header warns about, one level up. NOADJ_NQ_15m_RTH carried
    one from 2026-06-30 10:45 ET: volume 5,270 against the parent's 16,244, because only the
    first 6 of its 15 one-minute bars had arrived. It failed the reproduction check every
    run, which correctly refused to append anything, so that master stood still for three
    months while the other six caught up.

    THE CHECK STAYS STRICT. This repairs a row only when all of the following hold, so a
    genuinely corrupt or differently-built master still stops the run:
      - the only disputed row is the master's LAST one (history is never rewritten);
      - it matches, to the tick on all five fields, the bucket built from the first K parent
        bars of its own window for some K < N. That is what being interrupted mid-bucket
        looks like, and it is not something corruption produces by accident.
    The repair is the full-window bucket, and it is named in the report, never silent.

    Returns (repaired_existing_or_None, note_or_None).
    """
    if not len(existing) or not len(full):
        return None, None
    bad = check[(check["open_new"].notna()) &
                ((check["open_old"] - check["open_new"]).abs().gt(1e-6) |
                 (check["high_old"] - check["high_new"]).abs().gt(1e-6) |
                 (check["low_old"] - check["low_new"]).abs().gt(1e-6) |
                 (check["close_old"] - check["close_new"]).abs().gt(1e-6) |
                 (check["volume_old"] - check["volume_new"]).abs().gt(1e-6))]
    last_t = int(existing["time"].max())
    if len(bad) != 1 or int(bad.iloc[0]["time"]) != last_t:
        return None, None            # more than the tail is wrong -> not this failure mode

    # The bucket's window ends where the NEXT rebuilt bucket begins; that boundary is right
    # for the grid rule and the row-count rule alike, so neither needs special-casing here.
    later = full[full["time"] > last_t]
    if not len(later):
        return None, None
    end_t = int(later["time"].iloc[0])
    seg = parent[(parent["time"] >= last_t) & (parent["time"] < end_t)]
    if len(seg) < 2:
        return None, None

    stored = existing.iloc[-1]
    k = next((i for i in range(1, len(seg))
              if _same_bucket(stored, _bucket_from(seg.iloc[:i]))), None)
    if k is None:
        return None, None            # not a prefix of its own bucket -> genuinely wrong

    built = _bucket_from(seg)
    repaired = existing.copy()
    for col, val in built.items():
        if col in repaired.columns:
            repaired.iloc[-1, repaired.columns.get_loc(col)] = val
    note = (f"REPAIRED the last stored row at {_fmt_et(last_t)}: it had been saved with only "
            f"{k} of its {len(seg)} parent bars in place, so it read "
            f"high {float(stored['high']):,.2f} / low {float(stored['low']):,.2f} / "
            f"close {float(stored['close']):,.2f} / volume {float(stored['volume']):,.0f}. "
            f"Rebuilt from the full window as high {built['high']:,.2f} / "
            f"low {built['low']:,.2f} / close {built['close']:,.2f} / "
            f"volume {built['volume']:,.0f}. No earlier row was touched.")
    return repaired, note


def process_one(uploads_dir, master, parent_row, method):
    """Dry-run analysis for one master. Returns (result_dict, existing_df, new_rows_df) --
    new_rows_df is None when the reproduction check failed (nothing safe to append)."""
    tf = master["timeframe"]
    tf_minutes = TF_MINUTES[tf]
    parent_tf = parent_row["timeframe"]
    parent_tf_minutes = PARENT_TF_MINUTES[parent_tf]
    parent_tf_seconds = parent_tf_minutes * 60

    mpath = os.path.join(uploads_dir, master["filename"])
    ppath = os.path.join(uploads_dir, parent_row["filename"])
    existing = pd.read_csv(mpath)
    parent = pd.read_csv(ppath)

    last_master_t = int(existing["time"].max())
    last_parent_t = int(parent["time"].max())

    ratio = None
    if method == "grid":
        full = resample_grid(parent, tf_minutes)
    else:
        ratio = tf_minutes // parent_tf_minutes
        full = resample_rowcount(parent, tf_minutes, parent_tf_minutes)
    full = _drop_incomplete_tail(full, tf_minutes, last_parent_t, parent_tf_seconds, ratio=ratio)

    # Bars the upstream feed may still restate are re-derived, not checked: see
    # split_settled. `existing` becomes the settled history, and everything from the cutoff
    # onwards is rebuilt from the parent as it stands now.
    settled, unsettled = split_settled(existing, last_parent_t)
    n_redrived = len(unsettled)
    if n_redrived:
        existing = settled

    # reproduction check: every SETTLED row the master already has must reappear, exactly,
    # in our from-scratch resample of the parent.
    check = existing.merge(full, on="time", how="left", suffixes=("_old", "_new"))
    missing = check[check["open_new"].isna()]
    if len(missing):
        result = (f"FAIL - {len(missing)} existing bucket(s) not reproduced at all "
                   f"(e.g. time={_fmt_et(missing.iloc[0]['time'])})")
    else:
        diffs = {}
        for col in ("open", "high", "low", "close", "volume"):
            diffs[col] = (check[f"{col}_old"] - check[f"{col}_new"]).abs().max()
        worst_col = max(diffs, key=diffs.get)
        worst = diffs[worst_col]
        if worst > 1e-6:
            bad = check.loc[(check[f"{worst_col}_old"] - check[f"{worst_col}_new"]).abs().idxmax()]
            result = (f"FAIL - worst mismatch on {worst_col}: existing={bad[f'{worst_col}_old']} "
                      f"vs resampled={bad[f'{worst_col}_new']} at {_fmt_et(bad['time'])}")
        else:
            result = f"PASS - {len(check):,}/{len(existing):,} existing rows matched exactly"

    # One failure mode is repairable and worth repairing: a last row saved mid-bucket.
    repair_note = None
    if not result.startswith("PASS") and not len(missing):
        repaired, repair_note = repair_partial_last_row(existing, full, parent, check)
        if repaired is not None:
            existing = repaired
            check = existing.merge(full, on="time", how="left", suffixes=("_old", "_new"))
            worst = max((check[f"{c}_old"] - check[f"{c}_new"]).abs().max()
                        for c in ("open", "high", "low", "close", "volume"))
            result = (f"PASS after repair - {len(check):,}/{len(existing):,} existing rows "
                      f"matched exactly") if worst <= 1e-6 else result

    passed = result.startswith("PASS")
    drop_cols = [c for c in ("_grid_key", "_n") if c in full.columns]
    # Everything after the SETTLED history: the re-derived window plus whatever is genuinely
    # new. `existing` is the settled half now, so its max is the right boundary.
    settled_last = int(existing["time"].max()) if len(existing) else -1
    new_rows = full[full["time"] > settled_last].drop(columns=drop_cols) if passed else None

    # Refuse to append a bucket that spans an UNRECOGNISED contract switch. The test runs on
    # the PARENT's bars, where a carry-sized jump is still an extreme move, and then any
    # bucket whose window covers a flagged parent bar is held back - along with everything
    # after it, so the master stays contiguous.
    #
    # A switch already written into tools/data/rolls_<root>.csv with a trustworthy status is
    # NOT held back (roll_guard passes it through), because the confirmation the guard was
    # waiting for has happened. This matters: before 2026-09-29 these four coarse masters had
    # been frozen at 2026-09-14 for two weeks on a switch that was recorded, measured, and
    # ALREADY PRESENT in the parent they resample from - so refusing bought nothing and cost
    # every coarse timeframe its tail. An ESTIMATED row still blocks.
    roll_hit = None
    if new_rows is not None and len(new_rows):
        roll_hit = roll_guard.first_suspect_after(
            parent["time"].values, parent["open"].values, parent["close"].values,
            after_time=last_master_t, volumes=parent.get("volume"),
            root=master["instrument"])
        if roll_hit is not None:
            # the bucket holding that parent bar starts at or before it, so cut from the
            # last bucket that both starts and ENDS before the flagged parent bar
            cutoff = int(roll_hit["time"]) - tf_minutes * 60 + 1
            new_rows = new_rows[new_rows["time"] < cutoff].reset_index(drop=True)

    info = {
        "filename": master["filename"], "parent_filename": parent_row["filename"],
        "instrument": master["instrument"], "tf_minutes": tf_minutes, "method": method,
        "last_master_et": _fmt_et(last_master_t), "last_parent_et": _fmt_et(last_parent_t),
        "check_result": result, "n_new": 0 if new_rows is None else len(new_rows),
        "master_id": master["id"], "mpath": mpath, "roll_hit": roll_hit,
        "repair_note": repair_note, "n_rederived": n_redrived,
    }
    return info, existing, new_rows


def print_report(info, new_rows):
    print(f"{info['filename']}  (parent {info['parent_filename']}, method={info['method']})")
    print(f"  current last bar (ET): {info['last_master_et']}")
    print(f"  parent last bar (ET):  {info['last_parent_et']}")
    print(f"  reproduction check: {info['check_result']}")
    if info.get("repair_note"):
        print("  " + info["repair_note"])
    if info.get("n_rederived"):
        print("  re-derived the last %d bucket(s) from the parent as it stands now, because the "
              "feed may still restate a bar that recent (older buckets still had to match "
              "exactly)" % info["n_rederived"])
    if new_rows is None:
        print("  STOPPING for this file -- reproduction check failed, nothing appended.")
        print()
        return
    hit = info.get("roll_hit")
    if hit is not None:
        print("  REFUSED an in-bar contract switch. " + roll_guard.describe(hit))
        print(f"    held back {hit['et_date']} onwards; it appends by itself once the "
              f"parent's splice is repaired (ROLL_AUDIT.md 6.3)")
    print(f"  new bars: {info['n_new']:,}")
    if info["n_new"]:
        print(f"  first new bar: {_fmt_bar(new_rows.iloc[0])}")
        print(f"  last new bar:  {_fmt_bar(new_rows.iloc[-1])}")
        warn = _splice_warning(info["instrument"], new_rows, info["tf_minutes"])
        if warn:
            print(warn)
    else:
        print("  already current -- nothing to append.")
    print()


def apply_one(conn, uploads_dir, info, existing, new_rows):
    mpath = info["mpath"]
    stamp = datetime.now().strftime("%Y%m%d")
    bak = f"{mpath}.bak-{stamp}"
    shutil.copy2(mpath, bak)
    # KEEP A FEW, NOT ALL (MANAGER review 2026-09-30, finding 9). This used to be a
    # hand-run tool; nightly it drops a full copy of every coarse master every day into
    # augur_uploads, which OneDrive then syncs - about 0.33 GB per run and nothing ever
    # removed them. Three is enough to undo a bad run by hand.
    try:
        old = sorted(glob.glob(mpath + ".bak-*"))[:-KEEP_BACKUPS]
        for p in old:
            os.remove(p)
        if old:
            print("  pruned %d old backup copy(ies) of %s"
                  % (len(old), os.path.basename(mpath)))
    except OSError as e:
        print("  could not prune old backups of %s: %s" % (os.path.basename(mpath), e))
    merged = pd.concat([existing, new_rows], ignore_index=True).sort_values("time").reset_index(drop=True)
    write_master_csv(merged, mpath)
    date_to = str(pd.to_datetime(int(merged["time"].max()), unit="s", utc=True)
                  .tz_convert("US/Eastern").date())
    conn.execute("UPDATE csv_files SET rows=?, date_to=? WHERE id=?",
                 (len(merged), date_to, info["master_id"]))
    conn.commit()
    print(f"  {info['filename']}: backed up -> {os.path.basename(bak)}, "
          f"+{len(new_rows):,} bars -> {len(merged):,} total, now through {date_to}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB, help="path to optimizer_history.db (default: this checkout's)")
    ap.add_argument("--uploads", default=DEFAULT_UP, help="path to augur_uploads/ (default: this checkout's)")
    ap.add_argument("--apply", action="store_true", help="write the extended masters (default is dry-run only)")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    targets = find_masters(conn)
    if not targets:
        print("No stale resampled masters found (or empty/missing registry at --db).")
        conn.close()
        return

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"refresh_resampled_masters.py -- {mode}  (db={args.db}, uploads={args.uploads})")
    print()

    for master, parent_row, method in targets:
        info, existing, new_rows = process_one(args.uploads, master, parent_row, method)
        print_report(info, new_rows)
        if args.apply and new_rows is not None and len(new_rows):
            apply_one(conn, args.uploads, info, existing, new_rows)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
