"""TTM (house verifier) ARM B for QL_LATEBREAK_NQ (20261017-1353-scalper): the prereg's 'Mechanism' text, written from the
prereg ALONE before plugin_v1.py.txt's code was opened. Pure function over the registry master's arrays; no look-ahead:
the morning range uses session bars 0..11 (all closed before bar 12), the quiet filter uses the 20 PRIOR sessions' morning
ranges (all finished sessions), the signal at bar k uses bars <= k, the fill is bar k+1's OPEN, and the stop is evaluated
from the fill bar onward. The knob VALUES (quiet_k, stop_frac) are not in the prereg text; they are arguments here and the
harness passes the plugin file's DEFAULT_PARAMS values (the prereg: 'params = the file's DEFAULT_PARAMS defaults').

Readings (most literal) where the text is ambiguous:
 R1 session = one day_id of the master; in-session bar index = position within the day_id (checked equal to the open-clock
    index (open - 09:30)/5min on every bar of the window - 0 mismatches), so 'bar 0..11' = 09:30..10:25 opens.
 R2 morning range MR = max(high[0:12]) - min(low[0:12]) of the session; morning high/low = those max/min. A session with
    fewer than 12 bars has no MR (none in this window: the shortest sessions have 24 bars).
 R3 trailing 20 sessions = the 20 sessions immediately BEFORE this one (this one excluded), every session counted
    (holiday / half days included - their MR is computed the same way); numpy median (mean of the 10th and 11th values);
    fewer than 20 prior sessions in the loaded data -> no trade (the first 20 sessions of the load are warm-up).
 R4 quiet filter: MR <= quiet_k x median (inclusive, as written '<=').
 R5 signal: the FIRST bar k with in-session index >= 30 (12:00 open) whose CLOSE is strictly above the morning high (LONG)
    or strictly below the morning low (SHORT); only that first bar counts (no later re-try). If that first k is the
    session's last bar there is no k+1 in the session -> no trade that session.
 R6 entry = bar k+1's OPEN (same session).
 R7 stop = entry - stop_frac x MR (LONG) / entry + stop_frac x MR (SHORT), fixed at entry. Checked from the entry bar on:
    on a bar after the entry bar, an OPEN at or past the stop books that open; otherwise a low <= stop (LONG) / high >=
    stop (SHORT) books the stop price. The entry bar opens AT the entry, so only the intrabar touch applies to it.
 R8 no target, no time stop: if the stop never hits, exit at the session's LAST bar's CLOSE (the last bar of that day_id
    in the data - 13:00 / 13:15 / 11:30 closes on short days). A stop hit on the last bar books the stop (stop first).
 R9 one trade per session; a trade never crosses a session.
Returns (entry_bar, exit_bar, side, entry_px, exit_px, gross_pts) with global bar indices."""
import numpy as np


def own_rule(o, h, l, c, day_id, quiet_k, stop_frac, lookback=20, morning_bars=12, first_signal_idx=30):
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    day_id = np.asarray(day_id)
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    mr = np.full(len(starts), np.nan)
    mhi = np.full(len(starts), np.nan)
    mlo = np.full(len(starts), np.nan)
    for i, (s, e) in enumerate(zip(starts, ends)):
        if e - s >= morning_bars:
            mhi[i] = h[s:s + morning_bars].max()
            mlo[i] = l[s:s + morning_bars].min()
            mr[i] = mhi[i] - mlo[i]
    out = []
    for i, (s, e) in enumerate(zip(starts, ends)):
        if i < lookback or not np.isfinite(mr[i]):
            continue
        prior = mr[i - lookback:i]
        if not np.all(np.isfinite(prior)):
            continue
        if not mr[i] <= quiet_k * float(np.median(prior)):
            continue
        k = None
        side = 0
        for j in range(s + first_signal_idx, e):
            if c[j] > mhi[i]:
                k, side = j, 1
                break
            if c[j] < mlo[i]:
                k, side = j, -1
                break
        if k is None or k + 1 >= e:
            continue
        ent = k + 1
        ep = o[ent]
        stop = ep - side * stop_frac * mr[i]
        xb, xp = e - 1, c[e - 1]
        for j in range(ent, e):
            if j > ent and side * (o[j] - stop) <= 0:
                xb, xp = j, o[j]
                break
            if (l[j] <= stop) if side > 0 else (h[j] >= stop):
                xb, xp = j, stop
                break
        out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
    return out
