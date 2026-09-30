"""Daily CAPTURE HEALTH for the NinjaTrader 10-second export (NQ_10s.csv / ES_10s.csv).

WHY: the order-flow shadows (10-second delta) and the 10s tail that feeds every paper leg both
depend on the export actually being written all day with its buy/sell split filled in. Measured
on 2026-09-30, about a third of days had capture gaps and on some days only 38 to 61 percent of
the session's bars carried a classified delta - and nothing said so until a study tripped on it.
This turns that into one small block in the nightly paper report.

The files are large (30 MB and growing), so the day is found by a binary search on byte offsets
and only the day's rows are read. Columns: time,open,high,low,close,volume,delta,buy_vol,sell_vol,
tick_count,rt. `time` = the bar's END, unix seconds (see api/paper.py, _resample). The export
writes a row for every ten seconds of the session, so the expected RTH count is exact.

capture_health(day) -> {"NQ": {...}, "ES": {...}, "warning": str | None}. Fail-soft: an
instrument whose file is missing or unreadable reports {"error": ...} and never raises.
"""
import datetime as dt
import io
import os
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
COLS = ["time", "open", "high", "low", "close", "volume", "delta", "buy_vol", "sell_vol",
        "tick_count", "rt"]
BAR_S = 10
WARN_DELTA_PCT = 80.0      # RTH delta coverage under this raises the warning
WARN_BARS_PCT = 90.0       # RTH bars under this share of expected raise the warning
ETH_EXPECTED = 23 * 3600 // BAR_S   # 18:00 to 17:00 ET = 23 hours = 8,280 bars


def _et_ts(day, hhmm, add_days=0):
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    d = day + dt.timedelta(days=add_days)
    return int(dt.datetime(d.year, d.month, d.day, h, m, tzinfo=ET).timestamp())


def _first_time(line):
    try:
        return int(float(line.split(b",", 1)[0]))
    except (ValueError, IndexError):
        return None


def _read_window(path, start_ts, end_ts):
    """Rows with start_ts < time <= end_ts, read without loading the whole file."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        lo, hi = 0, size
        # Find a byte offset (line-aligned) at or just before the first row with time > start_ts.
        while hi - lo > 65536:
            mid = (lo + hi) // 2
            f.seek(mid)
            f.readline()                      # drop the partial line
            pos = f.tell()
            t = _first_time(f.readline())
            if t is None:                     # EOF or junk: look earlier
                hi = mid
            elif t <= start_ts:
                lo = pos
            else:
                hi = mid
        f.seek(max(0, lo - 65536))            # back off a little: tolerates a slightly unsorted tail
        if f.tell() > 0:
            f.readline()
        data = f.read()
    # keep only what is needed from the read (it runs to the end of the file)
    lines = data.splitlines()
    keep = []
    for ln in lines:
        t = _first_time(ln)
        if t is None:
            continue
        if t > end_ts:
            if t > end_ts + 86400:            # well past the window: stop
                break
            continue
        if t > start_ts:
            keep.append(ln)
    if not keep:
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(io.BytesIO(b"\n".join(keep)), header=None, names=COLS)
    df["time"] = df["time"].astype("int64")
    df = df.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)
    return df


def _delta_pct(df):
    if df.empty:
        return 0.0
    classified = (pd.to_numeric(df["buy_vol"], errors="coerce").fillna(0)
                  + pd.to_numeric(df["sell_vol"], errors="coerce").fillna(0)) > 0
    return round(100.0 * float(classified.mean()), 1)


def _unclassified(df):
    """Bars that traded (volume > 0) but carry no buy/sell split. A bar with no volume is not
    counted: nothing could be classified there. Returns (count, longest run in minutes, ET start
    'HH:MM' of that run or None). A run continues across rows no more than a minute apart."""
    if df.empty:
        return 0, 0.0, None
    vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0) > 0
    cls = (pd.to_numeric(df["buy_vol"], errors="coerce").fillna(0)
           + pd.to_numeric(df["sell_vol"], errors="coerce").fillna(0)) > 0
    bad = (vol & ~cls).tolist()
    times = df["time"].tolist()
    best, best_start, run, run_start, prev_t = 0, None, 0, None, None
    for t, b in zip(times, bad):
        if b:
            if run and prev_t is not None and t - prev_t <= 60:
                run += t - prev_t
            else:
                run, run_start = BAR_S, t - BAR_S
            if run > best:
                best, best_start = run, run_start
            prev_t = t
        else:
            run, prev_t = 0, None
    st = dt.datetime.fromtimestamp(best_start, ET).strftime("%H:%M") if best_start is not None else None
    return int(sum(bad)), round(best / 60.0, 1), st


def _first_classified(df):
    """ET 'HH:MM' of the first bar in df that carries a buy/sell split, or None if none does."""
    if df.empty:
        return None
    cls = (pd.to_numeric(df["buy_vol"], errors="coerce").fillna(0)
           + pd.to_numeric(df["sell_vol"], errors="coerce").fillna(0)) > 0
    hit = df.loc[cls.values, "time"]
    if hit.empty:
        return None
    return dt.datetime.fromtimestamp(int(hit.iloc[0]) - BAR_S, ET).strftime("%H:%M")


def _longest_gap(times, start_ts, end_ts):
    """(minutes missing, ET start 'HH:MM:SS') of the longest hole between bars, edges included.
    Bars are stamped at their END, so a bar at t covers (t-10, t]; consecutive bars are 10 s apart."""
    prev = start_ts
    best, best_start = 0, start_ts
    for t in list(times) + [end_ts + BAR_S]:
        missing = t - prev - BAR_S
        if missing > best:
            best, best_start = missing, prev
        prev = t
    if best <= 0:
        return 0.0, None
    st = dt.datetime.fromtimestamp(best_start, ET)
    return round(best / 60.0, 1), st.strftime("%H:%M")


def one_instrument(path, day):
    """Health of one 10s file for trading day `day` (a datetime.date)."""
    from . import market_calendar as MC
    close = MC.session_close_et(day) if MC.is_session(day) else "16:00"
    rth_start, rth_end = _et_ts(day, "09:30"), _et_ts(day, close)
    eth_start, eth_end = _et_ts(day, "18:00", -1), _et_ts(day, "17:00")
    if not os.path.exists(path):
        return {"error": "10s file not found: " + path}
    df = _read_window(path, eth_start, eth_end)
    rth = df[(df["time"] > rth_start) & (df["time"] <= rth_end)]
    expected = (rth_end - rth_start) // BAR_S
    gap_min, gap_at = _longest_gap(rth["time"].tolist(), rth_start, rth_end)
    return {
        "rth": {"bars": int(len(rth)), "expected": int(expected),
                "bars_pct": round(100.0 * len(rth) / expected, 1) if expected else 0.0,
                "delta_pct": _delta_pct(rth),
                "unclassified_bars": _unclassified(rth)[0],
                "rt_bars": int((pd.to_numeric(rth["rt"], errors="coerce").fillna(0) == 1).sum()),
                "longest_gap_min": gap_min, "gap_start_et": gap_at},
        "eth": {"bars": int(len(df)), "expected": ETH_EXPECTED,
                "delta_pct": _delta_pct(df),
                # traded bars with no buy/sell split, and the longest unbroken stretch of them
                # (10-01: the 00:00-08:20 ET overnight bars had volume but zero classification)
                "unclassified_bars": _unclassified(df)[0],
                "unclassified_run_min": _unclassified(df)[1],
                "unclassified_run_start_et": _unclassified(df)[2],
                # first bar of the day that carries a buy/sell split (when the live capture started)
                "delta_from_et": _first_classified(df)},
        "file": path,
    }


def default_path(instrument):
    """The fresher of the addon / watch-folder copies, the same rule the paper legs read with."""
    from . import paper
    return paper._ticks_path(instrument)


def capture_health(day, instruments=("NQ", "ES"), path_for=None):
    """The report block. `path_for(instrument)` overrides the file choice (tests)."""
    if isinstance(day, str):
        day = dt.date.fromisoformat(day)
    path_for = path_for or default_path
    out = {}
    problems = []
    for inst in instruments:
        try:
            r = one_instrument(path_for(inst), day)
        except Exception as e:                      # fail-soft: a health line never costs the report
            r = {"error": "%s: %s" % (type(e).__name__, e)}
        out[inst] = r
        rth = r.get("rth")
        if rth is None:
            problems.append("%s capture unreadable (%s)" % (inst, r.get("error")))
            continue
        bits = []
        if rth["bars_pct"] < WARN_BARS_PCT:
            bits.append("only %s of %s session bars were captured (%d%%)"
                        % (format(rth["bars"], ","), format(rth["expected"], ","), round(rth["bars_pct"])))
        if rth["delta_pct"] < WARN_DELTA_PCT:
            bits.append("buy/sell delta is filled in on only %d%% of session bars"
                        % round(rth["delta_pct"]))
        if bits:
            problems.append("%s: %s" % (inst, " and ".join(bits)))
    out["warning"] = (("10-second capture problem on " + day.isoformat() + " - " + "; ".join(problems)
                       + ". Order-flow shadow rules that read delta are unreliable for this day.")
                      if problems else None)
    return out


def line(inst, rec):
    """One plain-English line for facts.md / logs, e.g. '10s capture NQ: 2,331/2,340 bars, delta on 98%'."""
    rth = (rec or {}).get("rth")
    if not rth:
        return "10s capture %s: unavailable (%s)" % (inst, (rec or {}).get("error"))
    s = "10s capture %s: %s/%s bars, delta on %d%%" % (
        inst, format(rth["bars"], ","), format(rth["expected"], ","), round(rth["delta_pct"]))
    if rth.get("longest_gap_min", 0) >= 1:
        s += ", longest gap %s min from %s ET" % (rth["longest_gap_min"], rth["gap_start_et"])
    eth = (rec or {}).get("eth") or {}
    if eth:
        s += "; full day delta on %d%%" % round(eth.get("delta_pct", 0))
        if eth.get("delta_pct", 100) < 80:
            s += (" (split starts %s ET)" % eth["delta_from_et"]) if eth.get("delta_from_et")                 else " (no split all day)"
    return s
