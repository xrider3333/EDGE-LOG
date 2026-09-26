"""Shared helpers for the 2026-09-25 roll-detector audit (read-only research; nothing here is shipped).

Ground truth: tools/data/contract_switches_<ROOT>.csv, rebuilt by tools/rollaudit/ground_truth.py from databento_raw with the masters' own
stitch rule (tools/stitch_databento._active_by_day: max-volume contract per UTC day, forward-only).
64 raw switches per root 2010-06..2026-03 (+2 inferred after the raw files end 2026-06-05; the
2026-09 one reads -384.5 NQ points and is NOT trusted - post-raw data comes from another feed).

    import sys; sys.path.insert(0, r"C:\\EdgeLog\\_anatomy_cache\\rollaudit"); import rollaudit_lib as RL
    sw  = RL.load_switches("NQ")                         # DataFrame, raw switches only by default
    adj = RL.adjusted_arrays(arrays, "NQ")               # Panama back-adjusted copy of a load_master_arrays dict
    det = RL.true_detector("NQ")                         # drop-in for detect_roll_seams(day_open, day_close, day_ts)
    st  = RL.stitch_points(trades, arrays["index"], "NQ")  # per-trade roll offset booked as P&L (points, signed)
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
# committed exact switch tables (tools/data/contract_switches_<ROOT>.csv); override with ROLLAUDIT_DIR
TABLES = os.environ.get("ROLLAUDIT_DIR") or os.path.join(os.path.dirname(HERE), "data")


def load_switches(root, include_inferred=False):
    sw = pd.read_csv(os.path.join(TABLES, "contract_switches_%s.csv" % root))
    if not include_inferred:
        sw = sw[sw.source == "databento_raw"]
    sw = sw.copy()
    sw["ts"] = pd.to_datetime(sw.switch_sec, unit="s", utc=True)
    return sw.sort_values("switch_sec").reset_index(drop=True)


def _sec(index):
    ix = pd.DatetimeIndex(index)
    if ix.tz is None:
        ix = ix.tz_localize("US/Eastern")
    return (ix.tz_convert("UTC").asi8 // 10**9).astype(np.int64)


def adjusted_arrays(arrays, root, include_inferred=False):
    """Copy of a load_master_arrays dict with open/high/low/close Panama back-adjusted: every bar
    BEFORE a switch gets that switch's contract offset added (cumulative over later switches), so the
    series is price-continuous and the latest prices are real. Volume/index/day_id untouched."""
    sw = load_switches(root, include_inferred)
    sec = _sec(arrays["index"])
    add = np.zeros(len(sec))
    for s, off in zip(sw.switch_sec.to_numpy(), sw.contract_offset.to_numpy()):
        if not np.isfinite(off):
            continue
        add[sec < s] += off
    out = dict(arrays)
    for k in ("open", "high", "low", "close"):
        out[k] = np.asarray(arrays[k], float) + add
    out["_adjusted_for"] = root
    return out


def true_detector(root, include_inferred=False):
    """Drop-in replacement for the house detect_roll_seams(day_open, day_close, day_ts, ...): returns the
    day indices s whose day holds the first new-contract bar. When the switch falls BETWEEN two days
    (RTH masters: always), s = the first day after it, exactly the house meaning 'close[s-1] -> open[s]
    is a roll seam'. When the switch falls INSIDE a day (24h masters: 19:00/20:00 ET), s = the day that
    contains it - that day's own bars straddle two contracts; callers must treat it accordingly."""
    sw = load_switches(root, include_inferred)
    ssec = sw.switch_sec.to_numpy(np.int64)

    def detect(day_open, day_close, day_ts, *a, **k):
        dsec = _sec(pd.DatetimeIndex(list(day_ts)))
        out = set()
        for s in ssec:
            d = int(np.searchsorted(dsec, s, side="right")) - 1   # last day starting at/before the switch
            if d < 0 or d >= len(dsec):
                continue
            if dsec[d] == s:                                     # switch IS this day's first bar
                out.add(d)
            elif d + 1 < len(dsec) and d >= 0:
                # inside day d, or in the gap after day d's last bar (RTH): decide by the next day's start
                out.add(d + 1 if _between_days(d, s, dsec, day_ts) else d)
        return sorted(x for x in out if x > 0)
    return detect


def _between_days(d, s, dsec, day_ts=None):
    """True when the switch falls in the gap AFTER day d (RTH feeds: day d is a 09:30 day and the switch
    at 18:00-20:00 ET comes after its 16:00 close). False when day d is a midnight (00:00 ET) or 18:00
    session day - on 24h data every 19:00/20:00 switch is INSIDE the day that started before it.
    Fixed 2026-09-25: the old rule (next day within 24h and >= 6.5h after day start) also fired for a
    Thursday 20:00 switch on midnight days and returned the Friday."""
    first = pd.Timestamp(list(day_ts)[d]) if day_ts is not None else None
    if first is not None:
        if first.tzinfo is None:
            first = first.tz_localize("US/Eastern")
        first = first.tz_convert("US/Eastern")
        rth_day = (first.hour, first.minute) >= (9, 0) and first.hour < 17
        return bool(rth_day)
    return (dsec[d + 1] - s) <= 24 * 3600 and (s - dsec[d]) >= 6.5 * 3600


def stitch_points(trades, index, root, include_inferred=False):
    """Per trade (entry_idx, exit_idx, pnl, side, entry_px): the roll offset the trade books because it
    is open across a switch, in POINTS, signed (side x offset). Uses the true contract offset (not the
    1-minute jump). A trade is 'across' a switch when its entry bar is before the switch time and its
    exit bar is at/after it."""
    sw = load_switches(root, include_inferred)
    sec = _sec(index)
    ss = sw.switch_sec.to_numpy(np.int64); off = sw.contract_offset.to_numpy(float)
    out = []
    for t in trades:
        e, x = int(t[0]), int(t[1])
        side = int(t[3]) if len(t) > 3 else 1
        m = (ss > sec[e]) & (ss <= sec[x])
        out.append(float(side * np.nansum(off[m])))
    return np.array(out)
