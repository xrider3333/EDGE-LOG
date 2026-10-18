"""TTM ARM B for QL_LATEMOM_NQ (20261017-1408-own): the prereg's 'Mechanism' text implemented from the text ONLY.
Written BEFORE the plugin's code was read. trend_k and counter_k are not given as numbers in the prereg ("params = the file's
DEFAULT_PARAMS defaults"), so they are arguments here and are filled from the plugin's DEFAULT_PARAMS values only (extracted by
AST, nothing else of the plugin is read for ARM B). lookback = 20 is in the Mechanism text itself.

Data facts used (checked on the pinned master 2010-06-07..2016-06-30 before this file was written): 1550 sessions, every session
starts at 09:30 ET, no in-session holes (positional index == clock index), 1510 sessions have 78 bars, 40 short sessions have
24/42/45/46 bars (none reaches bar 54).

Readings (most literal; each choice listed in READING below):
 R1 bar numbers are the 0-based in-session index (prereg convention: bar k opens at 09:30 + 5k min); session = run of equal day_id.
    The text's clock labels '14:30-15:00' for bars 54-65 and '09:30-14:30' for bars 0-53 do not match the indices (bar 54 opens
    14:00; bars 54-65 = 14:00-15:00, 12 bars = 60 min; bars 0-53 = 09:30-14:00). The INDICES are followed (they are internally
    consistent: 12 bars, signal at bar 65's close = 15:00, entry bar 66 = 15:00 open, exit bar 77 = 15:55 bar, 11-bar hold).
 R2 block move = close[65] - open[54] (SIGNED, literal); morning range = max(high[0..53]) - min(low[0..53]).
 R3 med_block = median of the SIGNED block move over the trailing sessions (literal 'median of (close[65]-open[54])', no abs);
    med_morn = median of the morning range over the same trailing sessions.
 R4 trailing set = the last `lookback` (20) prior sessions that HAVE bars 0..77 (full sessions); short sessions (no bar 54/65) are
    skipped for both medians; today excluded; no trade until 20 such prior sessions exist inside the loaded window.
 R5 LONG if move >= trend_k*med_block AND morning range <= counter_k*med_morn; else SHORT if -move >= trend_k*med_block AND
    morning range <= counter_k*med_morn (LONG is tested first; with a signed median <= 0 both can hold -> LONG). The morning test
    is the same plain range for both sides (the text uses the range, not a direction-specific counter move). Ties (==) pass.
 R6 entry at the OPEN of bar 66; exit at the CLOSE of the session's last bar (bar 77 on every full session); no stop, no target;
    one trade per session; sessions without bar 66 / 77 do not trade.
 R7 gross pts = side * (exit_px - entry_px); no cost here.
"""
import numpy as np

READING = [
    "R1 bar k = 0-based in-session index, opening at 09:30+5k ET (all 1550 pre-WF sessions start 09:30, no holes); the text's clock labels for bars 54-65 ('14:30-15:00') and 0-53 ('09:30-14:30') contradict the indices (bar 54 opens 14:00) - the INDICES are followed: block = 14:00-15:00 (12 bars), morning = 09:30-14:00",
    "R2 block move = close[65]-open[54], SIGNED; morning range = max(high[0..53]) - min(low[0..53])",
    "R3 med_block = median of the SIGNED block move (literal, no abs); med_morn = median morning range; same trailing sessions for both",
    "R4 trailing = last 20 prior FULL sessions (bars 0..77 present); the 40 short sessions (24-46 bars) are skipped; today excluded; no trade until 20 such prior sessions exist in the loaded window (from 2010-06-07)",
    "R5 LONG if move >= trend_k*med_block AND morn <= counter_k*med_morn; elif SHORT if -move >= trend_k*med_block AND morn <= counter_k*med_morn; LONG tested first; same plain morning range for both sides; equality passes",
    "R6 entry = OPEN of bar 66 (15:00); exit = CLOSE of the session's last bar (bar 77, 16:00); no stop/target; one trade per session",
    "R7 gross pts = side*(exit-entry); trend_k / counter_k from the plugin's DEFAULT_PARAMS (not in the prereg text); lookback 20 from the text",
]


def own_rule(o, h, l, c, day_id, trend_k, counter_k, lookback=20, block_stat="signed", skip_short_sessions=True):
    """Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)] in global bar indices.
    block_stat / skip_short_sessions exist only for the diagnostic variants; the ARM B reading is the defaults.
      block_stat: 'signed' (ARM B) | 'abs' (median of |close[65]-open[54]|) | 'range' (median of max(high[54..65])-min(low[54..65]))
      skip_short_sessions False: trailing = last `lookback` prior sessions of any length; block stats from the full ones among
      them, morning range from all of them (truncated slice on short sessions)."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    hist = []          # per prior session: (is_full, block_stat_value, morning_range)
    out = []
    for s, e in zip(starts, ends):
        L = e - s
        full = L >= 78
        morn = float(np.max(h[s:s + min(54, L)]) - np.min(l[s:s + min(54, L)]))
        if L >= 66:
            mv = float(c[s + 65] - o[s + 54])
            if block_stat == "signed":
                bv = mv
            elif block_stat == "abs":
                bv = abs(mv)
            else:
                bv = float(np.max(h[s + 54:s + 66]) - np.min(l[s + 54:s + 66]))
        else:
            mv, bv = None, None
        # trailing stats from PRIOR sessions only
        if skip_short_sessions:
            prior = [x for x in hist if x[0]][-lookback:]
            ok = len(prior) == lookback
            if ok:
                med_block = float(np.median([x[1] for x in prior]))
                med_morn = float(np.median([x[2] for x in prior]))
        else:
            prior = hist[-lookback:]
            blk = [x[1] for x in prior if x[1] is not None]
            ok = len(prior) == lookback and len(blk) > 0
            if ok:
                med_block = float(np.median(blk))
                med_morn = float(np.median([x[2] for x in prior]))
        if ok and full:
            room = morn <= counter_k * med_morn
            side = 0
            if mv >= trend_k * med_block and room:
                side = 1
            elif -mv >= trend_k * med_block and room:
                side = -1
            if side != 0:
                ent, xb = s + 66, e - 1
                ep, xp = float(o[ent]), float(c[xb])
                out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep))))
        hist.append((full, bv, morn))
    return out
