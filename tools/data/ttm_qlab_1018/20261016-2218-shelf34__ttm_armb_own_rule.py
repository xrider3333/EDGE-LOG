"""TTM ARM B for QL_TOMRUSH_NQ (20261016-2218-shelf34): the prereg's 'Mechanism' text implemented by TTM, written and frozen
BEFORE plugin_v2.py.txt was opened. Pure function over the registry master's arrays; no engine, no plugin code.

Prereg Mechanism (Qwen's words) read literally:
  R1 calendar: augur_engine.session_calendar.is_last_n_sessions_of_month(index, last_n=3, day_id) - True on the last 3
     trading sessions of the calendar month (published CME calendar; a data-hole session still counts, has no bars).
  R2 entry: LONG at the session's bar 0 OPEN (the session's first bar in the data = 09:30 open). One trade per qualifying
     session. No short leg.
  R3 ATR: ATR(atr_bars=14) = simple mean of TRUE RANGE over the 14 bars immediately before the session's bar 0 (global bars
     s-14..s-1, i.e. the prior session's last 14 bars); TR_i = max(h_i - l_i, |h_i - c_{i-1}|, |l_i - c_{i-1}|), c_{i-1} the
     previous bar in the data. Needs 15 prior bars (14 TR + 1 prev close); a session without them is skipped.
  R4 stop: stop = entry - stop_frac * ATR, live from the entry bar (bar 0) on, checked intrabar on each bar's low; on a bar
     AFTER the entry bar whose OPEN is at/below the stop, the fill is that open (gap-through); otherwise low <= stop fills at
     the stop. stop_frac is NOT stated in the prereg text - it is a parameter here (None = no stop).
  R5 default exit: the session's last bar's CLOSE (15:55 bar on a full day; the last bar in the data on a short day).
     A stop on the last bar books the stop.
Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)] with global bar indices.
"""
import numpy as np

from augur_engine.session_calendar import is_last_n_sessions_of_month


def own_rule(o, h, l, c, day_id, index, stop_frac=None, last_n=3, atr_bars=14):
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    day_id = np.asarray(day_id)
    n = len(c)
    flag = np.asarray(is_last_n_sessions_of_month(index, int(last_n), day_id), bool)
    prev_c = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    out = []
    for s, e in zip(starts, ends):
        if not flag[s]:
            continue
        ep = o[s]
        stop = None
        if stop_frac is not None:
            if s - atr_bars < 1:                      # TR needs the bar before each of the 14 ATR bars
                continue
            atr = float(tr[s - atr_bars:s].mean())
            stop = ep - float(stop_frac) * atr
        xb, xp = e - 1, c[e - 1]
        if stop is not None:
            for j in range(s, e):
                if j > s and o[j] <= stop:            # gap-through: a later bar opening past the stop books its open
                    xb, xp = j, o[j]
                    break
                if l[j] <= stop:
                    xb, xp = j, stop
                    break
        out.append((int(s), int(xb), 1, float(ep), float(xp), float(xp - ep)))
    return out
