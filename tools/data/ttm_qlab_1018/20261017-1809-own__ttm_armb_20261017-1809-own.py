"""TTM ARM B for QL_REVERSAL_NQ (20261017-1809-own): the prereg's 'Mechanism' text implemented from the text ALONE,
written and frozen (sha256 recorded in ttm_verify.json) BEFORE the plugin code was read.

Reading of the text (each ambiguity resolved to the most literal reading):
 R1  bar k = 0-based in-session POSITION (every session in the window starts 09:30 and has contiguous bars, so position = clock).
 R2  signal bars: in-session k >= warmup_bars (12 = 10:30 open); decision at bar k's CLOSE; entry at bar k+1's OPEN; k+1 must be
     in the same session (a signal on the session's last bar has no entry).
 R3  burst_hi = max(high[k-12..k-1]), burst_lo = min(low[k-12..k-1]) - 12 in-session bars, bar k itself excluded.
 R4  ATR = mean(high-low) over the last atr_bars=20 bars ending at k-1 = GLOBAL bars k-20..k-1 (crosses into the prior session
     when k < 20; 'the last 20 bars' is not restricted to the session). Skipped only when fewer than 20 bars exist before k.
 R5  trailing 20-session stats (med_range = median of prior sessions' high-low range, med_atr): the text says 'store' them, and
     the two signal formulas do not use them -> computed as nothing; NOT a filter, NOT a warmup requirement (variant
     `need_trail=True` skips sessions with < 20 prior sessions in the window, as a diagnostic only).
 R6  LONG  if close[k] < burst_lo - stretch_k*ATR  AND close[k] < open[0]   (open[0] = this session's 09:30 bar open);
     SHORT if close[k] > burst_hi + stretch_k*ATR  AND close[k] > open[0]. Strict inequalities. stretch_k has NO default in the
     text -> taken as an argument (the prereg says params = the file's DEFAULT_PARAMS; only that number is read from the file).
 R7  one trade per session = the FIRST qualifying signal bar; no re-entry after the exit.
 R8  stop = entry - stop_frac*ATR (long) / entry + stop_frac*ATR (short), stop_frac 1.5, ATR = the signal bar's ATR (R4);
     fixed level, never moved. Live from the fill: checked on the entry bar's low/high too; on a later bar an open already
     through the stop fills at that open (gap), else a touch fills at the stop price. No target, no time stop.
 R9  not stopped -> exit at the session's last bar's CLOSE (stop checked before that close on the last bar).
Returns (entry_bar, exit_bar, side, entry_px, exit_px, gross_pts) with GLOBAL bar indices into the arrays.
"""
import numpy as np


def own_rule(o, h, l, c, day_id, stretch_k, warmup_bars=12, atr_bars=20, stop_frac=1.5, trail_sessions=20,
             need_trail=False):
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    day_id = np.asarray(day_id)
    n = len(c)
    rng = h - l
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    out = []
    for si, (s, e) in enumerate(zip(starts, ends)):
        if need_trail and si < trail_sessions:
            continue
        o0 = o[s]
        for k in range(s + warmup_bars, e - 1):          # k+1 <= e-1 : the entry bar stays in the session
            if k - atr_bars < 0:
                continue
            atr = rng[k - atr_bars:k].mean()
            b_hi = h[k - warmup_bars:k].max()
            b_lo = l[k - warmup_bars:k].min()
            if c[k] < b_lo - stretch_k * atr and c[k] < o0:
                side = 1
            elif c[k] > b_hi + stretch_k * atr and c[k] > o0:
                side = -1
            else:
                continue
            ent = k + 1
            ep = o[ent]
            stop = ep - side * stop_frac * atr
            xb, xp = e - 1, c[e - 1]
            for j in range(ent, e):
                if j > ent and side * (o[j] - stop) <= 0:   # opened through the stop
                    xb, xp = j, o[j]
                    break
                if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                    xb, xp = j, stop
                    break
            out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
            break                                        # one trade per session
    return out
