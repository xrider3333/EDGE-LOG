"""Master-CSV data access (streamlit-free).

Reads the same master registry (optimizer_history.db -> csv_files, is_master=1) and
the same CSV files (augur_uploads/) the Streamlit app uses, and returns OHLCV arrays
+ a day_id (ET calendar-day index, as the strategies expect) ready for run_backtest.
"""
import os
import sqlite3
import hashlib

import numpy as np
import pandas as pd

from .paths import UPLOADS, DB_PATH
from . import trial_cache as _TC


def list_masters():
    """All registered master CSVs as a list of dicts.

    Returns [] when this checkout has no master registry at all. optimizer_history.db
    is an untracked local file, so every git WORKTREE starts without one and
    sqlite3.connect() then silently CREATES an empty database whose first query raises
    "no such table: csv_files". Callers already treat an empty registry as "not
    registered in this checkout" (find_master -> None -> the affected tests skip
    themselves, which is exactly what tests/test_etf_book_shadow.py's own skip guard
    was written to do). Letting the bare DatabaseError escape turned that intended
    skip into 6 hard FAILURES in every worktree, which fails the pre-push engine gate
    and blocks `tools/wt.py ship` for every session. Any other database error raises.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(
            "SELECT * FROM csv_files WHERE is_master=1 "
            "ORDER BY instrument,timeframe,source", conn)
    except pd.errors.DatabaseError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise
    finally:
        conn.close()
    return df.to_dict("records")


# Roll-corrected masters are OPT-IN ONLY. A caller that does not name a source must never be
# handed one (2026-09-26): registering the first of them silently changed what every UNPINNED
# lookup returned, because this function took the first row of a list ordered by source name
# and "db_adj_eth" sorts before "db_noadj_eth". The live NinjaTrader ML gate
# (api/gate_live.py), the paper leg loader (api/paper.py) and the reconcile tool
# (augur_engine/reconcile.py) all resolve without a source, so all three would have switched
# to back-adjusted prices, against the explicit instruction that no live or paper leg's data
# changes. An adjusted master is a research artefact whose absolute price levels differ from
# the tradeable front contract by thousands of points; handing one to a live service by
# accident is the worst failure this registry can produce.
# Sources an UNPINNED lookup must never return. Two different conventions live here:
#   db_adj / db_fadj - roll-corrected futures, whose LEVELS differ from the tradeable price;
#   alpaca_          - SPLIT-adjusted stock bars, the opposite convention to the
#                      deliberately non-adjusted futures masters.
# alpaca_ was added 2026-10-01 (MANAGER review finding 10): "alpaca_split_rth" sorts BEFORE
# "nt_noadj_rth" and "tv", so once a stock master existed for a ticker the library already
# held - QQQ 1m/5m being the live case - every unpinned find_master for it would have
# returned split-adjusted stock data instead, including api/bars.py's fallback. Same shape
# as the September regression that re-pointed the live gate at back-adjusted prices.
ADJUSTED_SOURCE_PREFIXES = ("db_adj", "db_fadj", "alpaca_")

# The ONE exception, by ticker (MANAGER #156, 2026-10-12): an unpinned lookup for a ticker listed here may fall
# back to its split-adjusted Alpaca master, and only when no non-adjusted master of that timeframe exists. QQQ
# last split in 2000-03, so over the Alpaca masters' 2016+ window split-adjusted bars ARE the traded prices.
# Its non-adjusted 'NT' 1m/5m masters (49/50) were the QQQ live bar cache mis-imported a whole bar early and
# were retired; without this, unpinned QQQ 1m/5m lookups (api/bars.py and friends) found nothing. Never add a
# ticker that split inside its master's window, and never a futures root (roll-corrected levels stay opt-in).
UNPINNED_SPLIT_ADJUSTED_OK = {"QQQ"}


def is_adjusted_source(source):
    """True for a source an unpinned lookup must not substitute: roll-corrected futures
    (db_adj/db_fadj) or split-adjusted stock bars (alpaca_). Name the source to get one."""
    return str(source or "").startswith(ADJUSTED_SOURCE_PREFIXES)


def find_master(instrument, timeframe, session=None, source=None):
    """Best-matching master row for instrument+timeframe (+ optional session/source).

    For non-adjusted data pass source='db_noadj_rth'/'db_noadj_eth'.

    A ROLL-CORRECTED master ('db_adj_*' / 'db_fadj_*') is returned ONLY when `source` names
    one. Leave `source` blank and you get the unadjusted data you got before those masters
    existed - and if the only thing that would match is an adjusted master, this returns None
    rather than quietly substituting one. Failing to find data is recoverable; a live service
    silently re-pointed at a different price scale is not. See docs/ROLL_ADJUSTED_MASTERS.md.
    """
    cand = [m for m in list_masters()
            if str(m.get("instrument")) == str(instrument)
            and str(m.get("timeframe")) == str(timeframe)]
    if session:
        cand = [m for m in cand if str(m.get("session", "")).lower() == session.lower()]
    if source:
        cand = [m for m in cand if str(m.get("source", "")) == source]
    else:
        plain = [m for m in cand if not is_adjusted_source(m.get("source"))]
        if not plain and str(instrument) in UNPINNED_SPLIT_ADJUSTED_OK:
            plain = [m for m in cand if str(m.get("source", "")).startswith("alpaca_split")]
        cand = plain
    return cand[0] if cand else None


# ── PR3: in-process data-prep memoization (docs/INCREMENTAL_BACKTEST_REUSE.md
#    §2(b)) — repeated jobs over the same master+window skip the CSV read +
#    day_id factorization. Gated behind trial_cache.is_enabled() (the one switch
#    for the whole caching subsystem, default OFF): when OFF, load_master_arrays
#    behaves EXACTLY as before this feature existed — no memo lookup, no memo
#    write, byte-identical.
#
#    Key = (instrument, timeframe, source, filename, date_from, date_to,
#    file mtime, file size). The mtime+size pair mirrors data_quality.
#    check_master_cached's own freshness idiom, so a CSV that changed on disk
#    (an auto-sync landed new bars, a re-ingest replaced the file) is ALWAYS a
#    miss -> fresh read, never a stale array — the same "silent window slide"
#    hazard class CLAUDE.md's comparison-rerun hard rule warns about, just one
#    layer earlier (before a window even gets sliced). Bounded to a handful of
#    entries (LRU) since each entry holds several multi-MB numpy arrays.
_MEMO_MAX_ENTRIES = 4
_MEMO = []   # [(key, value_dict), ...] — index 0 = least-recently-used


def _memo_key(master, date_from, date_to, st_mtime, st_size):
    return (master.get("instrument"), master.get("timeframe"), master.get("source"),
            master.get("filename"), date_from, date_to, st_mtime, st_size, window_cut_rule(master))


# ETH SESSION CUT (MANAGER #98, TBIS 2026-10-16). A CME ETH session dated D runs from 18:00 ET on D-1 to
# 17:00 ET on D (17:15 before 2015-09; the 2010-15 masters carry real bars to 17:29). Cutting an ETH window
# at MIDNIGHT after date_to therefore kept 18:00-23:59 of date_to, the first hours of the NEXT session:
# 302 1m / 72 5m bars past a date_to=2016-06-30 pre-WF cut, and in every validate the first lockbox
# evening inside the optimize window (ENGU-Q #335: +$2,660 of lockbox-session movement in its optimize
# total). An ETH window now ends at 18:00 ET of date_to - the CME trade-date roll. date_from keeps its calendar
# meaning (live/paper loads pass date_from with no date_to and must not move), so the evening between an
# optimize window's end and a lockbox that starts at lb_from midnight sits in NEITHER: nothing leaks, and every
# stored lockbox label and replay keeps its midnight boundary. A caller that wants two windows to meet with no
# gap starts the second one at session_start_str(). RTH, stock (alpaca_*) and unlabelled masters keep the
# calendar cut, byte for byte; validate records the rule in windows.cut_rule.
# AUGUR_ETH_CALENDAR_CUT=1 restores the old cut, for to-the-cent repro gates of runs made before this.
ETH_SESSION_ROLL = "18:00"


def _is_eth(master):
    """A CME futures ETH master (18:00 ET roll). Stock data the registry also labels 'eth' (alpaca_*_eth
    extended hours run to 20:00 ET) is not one."""
    m = master or {}
    if str(m.get("source") or "").strip().lower().startswith("alpaca"):
        return False
    s = str(m.get("session") or "").strip().lower()
    if s:
        return s == "eth"
    return str(m.get("source") or "").strip().lower().endswith("_eth")


def _calendar_cut_forced():
    return os.environ.get("AUGUR_ETH_CALENDAR_CUT", "").strip() not in ("", "0")


_HATCH_SAID = []


def window_cut_rule(master):
    """'eth_session_18et' when an ETH window is cut at the session roll; 'calendar_forced' when the
    AUGUR_ETH_CALENDAR_CUT hatch put an ETH master back on the old cut (said once per process, and run docs
    record it); otherwise 'calendar'."""
    if not _is_eth(master):
        return "calendar"
    if _calendar_cut_forced():
        if not _HATCH_SAID:
            _HATCH_SAID.append(1)
            print("[data] AUGUR_ETH_CALENDAR_CUT is set: ETH windows use the OLD calendar cut, which keeps "
                  "the next session's evening (repro gates only)", flush=True)
        return "calendar_forced"
    return "eth_session_18et"


def window_end_ts(master, date_to):
    """Exclusive end of a window that runs through `date_to`: 18:00 ET of date_to on an ETH master (built
    from the wall clock, so DST days are right), otherwise the next midnight ET."""
    d = str(date_to)[:10]
    if window_cut_rule(master) == "eth_session_18et":
        return pd.Timestamp(f"{d} {ETH_SESSION_ROLL}", tz="US/Eastern")
    return pd.Timestamp(d, tz="US/Eastern") + pd.Timedelta(days=1)


def session_start_str(master, date):
    """The date_from string for the first instant of the session dated `date`: on an ETH master the
    evening before at 18:00 ET ('YYYY-MM-DD 18:00'), otherwise `date` itself, unchanged. For a caller whose
    second window must start exactly where a date_to window ended (pre-WF then WF, IS then OOS)."""
    if window_cut_rule(master) != "eth_session_18et":
        return date
    prev = (pd.Timestamp(str(date)[:10]) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{prev} {ETH_SESSION_ROLL}"


def _memo_get(key):
    for i, (k, v) in enumerate(_MEMO):
        if k == key:
            _MEMO.append(_MEMO.pop(i))          # bump to most-recently-used
            return v
    return None


def _memo_put(key, value):
    _MEMO.append((key, value))
    del _MEMO[:-_MEMO_MAX_ENTRIES]               # drop oldest beyond the cap


def _memo_clear():
    """Test-only escape hatch — production code never calls this; a changed
    file is already correctly handled by the mtime+size key above."""
    _MEMO.clear()


def load_master_arrays(master, date_from=None, date_to=None):
    """Load a master row's CSV -> dict(open,high,low,close,volume,day_id,index,meta).
    day_id is the ET calendar-day factorization the day_id-aware strategies need.

    date_from / date_to (YYYY-MM-DD strings or None) slice the master to that ET-date
    window *before* day_id is factorized, so day_id stays 0-based and contiguous.

    In-process memoized (PR3 above) when trial_cache.is_enabled() — a cache HIT
    returns a value equal to a fresh load (see that section's docstring for the
    key + invalidation contract). A HIT's outer dict is always a fresh shallow
    copy (callers may freely rebind its keys, e.g. `arrays["meta"] = ...`,
    without mutating the shared memo entry). Whenever memoization is active,
    the underlying numpy arrays are marked read-only from the moment an entry
    is created — including the very first (populating) call, not just later
    hits — so an accidental in-place mutation by ANY caller raises immediately
    instead of silently corrupting every future reader of that memo entry."""
    path = os.path.join(UPLOADS, master["filename"])

    memo_key = None
    if _TC.is_enabled():
        try:
            st = os.stat(path)
            memo_key = _memo_key(master, date_from, date_to, st.st_mtime, st.st_size)
            hit = _memo_get(memo_key)
            if hit is not None:
                return dict(hit)
        except OSError:
            memo_key = None   # can't stat -- fall through; pd.read_csv below will
                              # raise the SAME real error a memo-off caller would see

    df = pd.read_csv(path)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    if date_from:
        df = df[df.index >= pd.Timestamp(date_from, tz="US/Eastern")]
    if date_to:
        # inclusive of the whole `date_to` calendar day - or, on an ETH master, of the session dated
        # date_to, which ends before the 18:00 ET roll (window_end_ts; MANAGER #98)
        df = df[df.index < window_end_ts(master, date_to)]
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")
    # Data fingerprint (docs/INCREMENTAL_BACKTEST_REUSE.md): a sha1 of the SLICED
    # window's first/last bar timestamp + bar count. This is what makes a "silent
    # window slide" (master auto-synced new bars under a blank date_to -- the exact
    # #162-vs-#164 bug CLAUDE.md's hard rule warns about) a cache MISS rather than a
    # false hit: same date_from/date_to string can still resolve to a different set
    # of actual bars once new data lands, and this fingerprint changes when that
    # happens even though date_from/date_to themselves didn't. Non-breaking: purely
    # an ADDED top-level key, every existing key is untouched.
    n_bars = len(df.index)
    _first_ts = str(df.index[0]) if n_bars else ""
    _last_ts = str(df.index[-1]) if n_bars else ""
    fingerprint = hashlib.sha1(f"{_first_ts}|{_last_ts}|{n_bars}".encode()).hexdigest()
    result = {
        "open":  df["open"].values.astype(float),
        "high":  df["high"].values.astype(float),
        "low":   df["low"].values.astype(float),
        "close": df["close"].values.astype(float),
        "volume": df["volume"].values.astype(float) if "volume" in df.columns else None,
        "day_id": day_id,
        "index": df.index,
        "meta": master,
        "fingerprint": fingerprint,
        "window_cut": window_cut_rule(master),
    }
    if memo_key is not None:
        for _k in ("open", "high", "low", "close", "volume", "day_id"):
            _v = result.get(_k)
            if isinstance(_v, np.ndarray):
                _v.setflags(write=False)
        _memo_put(memo_key, result)
    return result
