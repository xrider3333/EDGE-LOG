"""
stitch_databento.py  —  Build back-adjusted continuous ES/NQ series from a
Databento GLBX.MDP3 ohlcv-1m batch download (split-by-instrument CSVs).

What it does
------------
1. Reads every per-contract CSV in databento_raw/, keeping only OUTRIGHT
   contracts (drops calendar-spread files like 'ESH0-ESM0', which trade the
   price *difference*, not the index).
2. Builds a continuous front-month series via VOLUME DOMINANCE: each day the
   active contract is the highest-volume one, with a monotonic forward-only
   roll (never rolls back to an expiring month). Contract order is derived from
   actual bar timestamps, so the single-digit year code (ESH0 = Mar-2020,
   trading in 2019) is never decoded by hand — no decade ambiguity.
3. Back-adjusts each roll (Panama-canal method): shifts all prior history by the
   new-minus-old close gap measured on the last overlapping bar, so the series
   is price-continuous. The most recent segment keeps real (un-shifted) prices.
4. Resamples the continuous 1m to 5m (O=first,H=max,L=min,C=last,V=sum).
5. Writes TradingView-style CSVs (time = Unix seconds + OHLCV):
       augur_uploads/ES_continuous_1m.csv   (full 1m, in case you want it)
       augur_watch/ES_continuous_5m.csv      (5m — auto-ingested by AUGUR)
   ...and the same for NQ.

Run:  python tools/stitch_databento.py
"""
import os
import glob
import sys
import numpy as np
import pandas as pd

HERE     = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(HERE)                       # AUGUR/
RAW_DIR  = os.path.join(ROOT, "databento_raw")
UPLOADS  = os.path.join(ROOT, "augur_uploads")
WATCH    = os.path.join(ROOT, "augur_watch")

NS = 1_000_000_000  # ns per second
ROOTS = ["ES", "NQ"]


def _outright_files(root):
    """All per-contract CSVs for `root`, excluding spreads (symbol has a '-')."""
    out = []
    for p in glob.glob(os.path.join(RAW_DIR, f"*.ohlcv-1m.{root}*.csv")):
        token = os.path.basename(p).split(".ohlcv-1m.")[-1][:-4]  # strip '.csv'
        if "-" in token:
            continue                       # calendar spread -> skip
        if not token.startswith(root):
            continue
        # outright = root + 1 month-letter + 1 year-digit  (e.g. ESH0, len 4)
        tail = token[len(root):]
        if len(tail) == 2 and tail[0].isalpha() and tail[1].isdigit():
            out.append(p)
    return sorted(out)


def _load_root(root):
    """Concatenate all outright contracts for `root` into one tidy frame."""
    files = _outright_files(root)
    if not files:
        return None
    print(f"  [{root}] {len(files)} outright contract files")
    frames = []
    # NOTE: key on instrument_id, NOT symbol — Databento's single-digit year code
    # collides across decades (ESH5 = both Mar-2015 and Mar-2025, same symbol
    # string, different instrument_id). instrument_id is the true contract id.
    usecols = ["ts_event", "instrument_id", "open", "high", "low",
               "close", "volume", "symbol"]
    for p in files:
        df = pd.read_csv(p, usecols=usecols)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["sec"] = (df["ts_event"].astype("int64") // NS).astype("int64")
    df["day"] = (df["sec"] // 86400).astype("int64")
    df["cid"] = df["instrument_id"].astype("int64")   # true contract key
    # numeric prices/volume
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("ts_event").reset_index(drop=True)
    print(f"  [{root}] {len(df):,} raw 1m bars across "
          f"{df['cid'].nunique()} real contracts "
          f"({df['symbol'].nunique()} distinct symbol codes)")
    return df


def _active_by_day(df):
    """Map day -> active contract id (volume dominance, monotonic roll)."""
    # daily volume per (day, cid)
    vol = (df.groupby(["day", "cid"])["volume"].sum()
             .reset_index())
    # contract expiry order proxy = last bar timestamp per cid
    order = (df.groupby("cid")["sec"].max()
               .sort_values().reset_index())
    rank = {c: i for i, c in enumerate(order["cid"])}
    # dominant (max-volume) cid per day
    idx = vol.groupby("day")["volume"].idxmax()
    dom = vol.loc[idx, ["day", "cid"]].set_index("day")["cid"].to_dict()
    # monotonic forward-only roll
    active = {}
    cur_cid, cur_rank = None, -1
    for d in sorted(dom):
        cand = dom[d]
        if rank.get(cand, -1) >= cur_rank:
            cur_cid, cur_rank = cand, rank[cand]
        active[d] = cur_cid
    return active


def _back_adjust(df):
    """df = continuous bars (one symbol per row, time-sorted). Returns the same
    frame with O/H/L/C shifted so rolls are price-continuous (latest = real)."""
    # ordered unique segments in time (by contract id)
    seg_ids = list(dict.fromkeys(df["cid"].tolist()))
    if len(seg_ids) < 2:
        return df
    # per-contract close (full raw series) for overlap lookup at rolls
    offsets = []  # offset applied at each roll boundary (new - old)
    for k in range(len(seg_ids) - 1):
        c_old = RAW_CLOSE[seg_ids[k]]
        c_new = RAW_CLOSE[seg_ids[k + 1]]
        common = c_old.index.intersection(c_new.index)
        if len(common):
            t = common.max()                      # last overlapping minute
            off = float(c_new.loc[t]) - float(c_old.loc[t])
        else:                                     # no overlap -> use the gap
            off = float(c_new.iloc[0]) - float(c_old.iloc[-1])
        offsets.append(off)
    # cumulative offset for segment k = sum of offsets at rolls >= k
    # (latest segment offset 0; everything earlier shifted by future gaps)
    cum = np.zeros(len(seg_ids))
    run = 0.0
    for k in range(len(seg_ids) - 2, -1, -1):
        run += offsets[k]
        cum[k] = run
    shift_by = {c: cum[i] for i, c in enumerate(seg_ids)}
    adj = df["cid"].map(shift_by).astype(float)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c] + adj
    print(f"      rolls={len(offsets)}  "
          f"total back-adjust shift={cum[0]:+.2f} pts (oldest bars)")
    return df


def _to_tv(df):
    """Continuous bars -> TradingView-style frame: time(unix s)+OHLCV."""
    out = pd.DataFrame({
        "time":   df["sec"].astype("int64"),
        "open":   df["open"].round(4),
        "high":   df["high"].round(4),
        "low":    df["low"].round(4),
        "close":  df["close"].round(4),
        "volume": df["volume"].astype("int64"),
    })
    return out.drop_duplicates(subset="time").sort_values("time")


def _resample_5m(tv1m, rth=False):
    """TV 1m frame -> TV 5m frame. If rth, keep only the 09:30-16:00 ET regular
    cash session BEFORE resampling (matches TradingView RTH index-futures hours
    and the prior VWAP RTH masters)."""
    d = tv1m.copy()
    d.index = pd.to_datetime(d["time"], unit="s", utc=True)
    if rth:
        et = d.index.tz_convert("US/Eastern")
        mins = et.hour * 60 + et.minute
        keep = (mins >= 9 * 60 + 30) & (mins < 16 * 60) & (et.dayofweek < 5)
        d = d[keep]
    agg = d.resample("5min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["open"])
    agg = agg.reset_index()
    agg["time"] = agg["time"].astype("int64") // NS
    return agg[["time", "open", "high", "low", "close", "volume"]]


# populated per-root inside main (used by _back_adjust)
RAW_CLOSE = {}


def process(root):
    global RAW_CLOSE
    print(f"\n=== {root} ===")
    df = _load_root(root)
    if df is None:
        print(f"  [{root}] no files found — skipping")
        return
    # full per-contract close series (for roll-overlap offset lookup); collapse
    # any duplicate minutes within a contract so the index is unique
    RAW_CLOSE = {c: g.groupby("sec")["close"].last().sort_index()
                 for c, g in df.groupby("cid")}
    active = _active_by_day(df)
    df["active"] = df["day"].map(active)
    cont = df[df["cid"] == df["active"]].copy()
    cont = cont.sort_values("ts_event").reset_index(drop=True)
    print(f"  [{root}] continuous: {len(cont):,} bars  "
          f"{pd.to_datetime(cont['sec'].iloc[0], unit='s').date()} -> "
          f"{pd.to_datetime(cont['sec'].iloc[-1], unit='s').date()}")
    cont = _back_adjust(cont)

    tv1     = _to_tv(cont)
    tv5_eth = _resample_5m(tv1, rth=False)
    tv5_rth = _resample_5m(tv1, rth=True)

    os.makedirs(UPLOADS, exist_ok=True)
    os.makedirs(WATCH, exist_ok=True)
    p1   = os.path.join(UPLOADS, f"{root}_continuous_1m.csv")
    p5e  = os.path.join(WATCH,   f"{root}_continuous_5m_ETH.csv")
    p5r  = os.path.join(WATCH,   f"{root}_continuous_5m_RTH.csv")
    tv1.to_csv(p1, index=False)
    tv5_eth.to_csv(p5e, index=False)
    tv5_rth.to_csv(p5r, index=False)
    print(f"  [{root}] wrote 1m      -> {p1}  ({len(tv1):,} bars)")
    print(f"  [{root}] wrote 5m ETH  -> {p5e}  ({len(tv5_eth):,} bars)")
    print(f"  [{root}] wrote 5m RTH  -> {p5r}  ({len(tv5_rth):,} bars)")


def main():
    if not os.path.isdir(RAW_DIR):
        print(f"!! {RAW_DIR} not found"); sys.exit(1)
    for r in ROOTS:
        process(r)
    print("\nDone. 5m files are in augur_watch/ — launch AUGUR to auto-ingest "
          "them as masters (or upload via the Library CSV tab).")


if __name__ == "__main__":
    main()
