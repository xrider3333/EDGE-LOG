"""What the runner's Yahoo refresh (optimizer.auto_refresh_masters) may and may not change in a master.

WHY (MANAGER #67/#68, 2026-10-14). That refresh pulls 7 days of Yahoo 1m/2m/5m and merged it with Yahoo
WINNING every overlap, so each 4-hourly pass rewrote the last week of every auto-refreshed master. On
the NQ no-adjust masters that put Yahoo's NQ=F opens/closes - which differ from NinjaTrader's on ~70% of
5m bars since 10-05 (prints on the other side of the bar boundary, up to 2.25 points) - over bars that
had been NT-spliced. It also relabelled every row's `source` and replaced the registry provenance, which
deleted the NT splice/repair records of 10-12 and 10-14 from the NQ/ES 1m and 5m masters.

Three rules, each a pure function so it can be tested without the 9,700-line backend:
  1. A no-adjust master (source db_noadj* or nt_noadj*) only takes Yahoo bars PAST its last stored bar,
     and never a bar that is still forming (MANAGER #74, 10-15: a pull taken mid-bar returns the bar so far;
     appended, it would never be corrected, because the next pass only looks past it). Correcting a recent
     bar is tools/refresh_noadj_yahoo.py's job (a 3-day window that never touches an NT bar).
  2. A stored row keeps its own `source` tag unless the refresh actually replaced the bar.
  3. The splice / repair history in a master's provenance survives a refresh.
"""
import json
import os
import time

import pandas as pd

APPEND_ONLY_PREFIXES = ("db_noadj", "nt_noadj")
FORMING_SETTLE_S = 900          # a bar is final 15 min after its end (Yahoo restates the last bars for a while)
CARRIED_PROVENANCE_KEYS = ("splices", "repairs")


def append_only(source):
    """True for a master whose existing bars a Yahoo refresh must never overwrite."""
    return str(source or "").startswith(APPEND_ONLY_PREFIXES)


def _utc(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def bar_seconds(tf):
    """'5m' -> 300, '1h' -> 3600; None for any other label (no forming-bar cut is made then)."""
    s = str(tf or "").strip().lower()
    unit = {"m": 60, "h": 3600}.get(s[-1:])
    if not unit or not s[:-1].isdigit():
        return None
    return int(s[:-1]) * unit


def past_last_bar(ydf, existing_df, bar_s=None, now=None, settle_s=FORMING_SETTLE_S):
    """The rows of a datetime-indexed pull strictly after the existing master's last bar - and, given the
    bar length `bar_s`, without the bars that end less than `settle_s` before `now` (still forming).

    A naive stamp on either side is read as UTC, which is how the masters are written (the roll guard
    in auto_refresh_masters makes the same call)."""
    if ydf is None or ydf.empty:
        return ydf
    idx = pd.DatetimeIndex(ydf.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    keep = pd.Series(True, index=range(len(ydf))).to_numpy()
    if existing_df is not None and len(existing_df):
        keep &= (idx > _utc(existing_df.index[-1]))
    if bar_s:
        now = time.time() if now is None else now
        ends = idx.tz_localize(None).astype("datetime64[ns]").astype("int64") // 1_000_000_000 + int(bar_s)
        keep &= (ends + settle_s <= now)
    return ydf if keep.all() else ydf[keep]


def stored_source_tags(path):
    """{unix seconds: source tag} from a stored master's `source` column; {} when it has none."""
    if not path or not os.path.exists(path):
        return {}
    try:
        head = pd.read_csv(path, nrows=0)
        if "source" not in head.columns or "time" not in head.columns:
            return {}
        s = pd.read_csv(path, usecols=["time", "source"])
    except Exception:
        return {}
    s = s.dropna(subset=["source"])
    return dict(zip(s["time"].astype("int64").tolist(), s["source"].astype(str).tolist()))


def keep_source_tags(merged, tags):
    """`merged` (combine_ohlcv_frames output, '__src' column) with every row that the EXISTING frame
    supplied given back its stored tag. A row a pull replaced keeps the pull's label."""
    if merged is None or not tags or "__src" not in merged.columns:
        return merged
    idx = pd.DatetimeIndex(merged.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    unix = (idx.tz_localize(None).astype("datetime64[ns]").astype("int64") // 1_000_000_000)
    stored = pd.Series(unix, index=merged.index).map(tags)
    take = (merged["__src"] == "existing") & stored.notna()
    if take.any():
        merged = merged.copy()
        merged.loc[take, "__src"] = stored[take].values
    return merged


def carry_provenance(new_json, old_json):
    """The new provenance JSON with the old one's splice / repair history carried over."""
    try:
        new = json.loads(new_json or "{}")
        old = json.loads(old_json or "{}")
    except (TypeError, ValueError):
        return new_json
    if not isinstance(new, dict) or not isinstance(old, dict):
        return new_json
    for k in CARRIED_PROVENANCE_KEYS:
        if old.get(k) and not new.get(k):
            new[k] = old[k]
    return json.dumps(new)
