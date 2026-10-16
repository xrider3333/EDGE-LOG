"""TTM ARM B for QL_TRENDN (20261016-1342-own): the prereg's 'Mechanism' text implemented from the text ONLY.
Written BEFORE the plugin's code was read. The three fractions (threshold_frac, stop_frac, trail_frac) are not given as numbers in
the prereg ("params = the file's DEFAULT_PARAMS defaults"), so they are arguments here and are filled from the plugin's
DEFAULT_PARAMS values only (extracted by AST, nothing else of the plugin is read for ARM B).

Readings (most literal; each choice listed in READING below):
 R1 bar numbering is 0-based within the session (the text says "bars 0-11"); session = run of equal day_id; bar 0 = 09:30 ET.
 R2 first-hour range = max(high[0..11]) - min(low[0..11]); displacement = close[11] - open[0].
 R3 entry at the open of session bar 13 (literal "bar 13's open", 10:35 ET); bar 12 is skipped.
 R4 the |displacement| >= threshold_frac x range test applies to BOTH sides (the |.| makes it symmetric); displacement == 0 -> no trade.
 R5 initial stop = entry_px -/+ stop_frac x range (range = the first-hour range, fixed for the trade).
 R6 trailing: from the bar after entry, stop = max(stop, highest close since entry (entry bar's close included once it has closed)
    - trail_frac x range) for a long (mirror for a short); ratchet only tightens; uses closes of bars < j only (no look-ahead).
 R7 exit: on bar j > entry, an open at/through the stop fills at the open; else low <= stop (long) / high >= stop (short) fills at
    the stop price (touch counts as through, no tick rounding); on the entry bar only the intrabar test applies.
 R8 no stop hit -> flat at the close of the session's last bar. One trade per session. Sessions with < 14 bars do not trade.
"""
import numpy as np

READING = [
    "R1 bars 0-based within session (day_id run); bar 0 = 09:30 ET (all 1550 pre-WF sessions start 09:30, none has a gap in bars 0-13)",
    "R2 range = max(high[0..11]) - min(low[0..11]); displacement = close[11] - open[0]",
    "R3 entry = open of session bar 13 (10:35 ET), literal 'bar 13's open'; signal bar 12 itself is not traded on",
    "R4 threshold |disp| >= threshold_frac*range applies to longs AND shorts (the abs value read as symmetric); disp == 0 -> no trade",
    "R5 initial stop = entry_px - side*stop_frac*range, range = first-hour range held fixed for the trade",
    "R6 trail: from bar entry+1 on, stop = max(stop, max close since entry (closes of bars entry..j-1) - trail_frac*range) for long, mirror short; ratchet never loosens; no look-ahead",
    "R7 exit: bar j > entry opening at/through the stop -> fill at open; else low<=stop (long) / high>=stop (short) -> fill at the stop (touch = through, no tick rounding); entry bar: intrabar test only",
    "R8 no stop -> flat at the session's last bar close; one trade per session; sessions with < 14 bars skipped",
]


def own_rule(o, h, l, c, day_id, threshold_frac, stop_frac, trail_frac, entry_pos=13, short_needs_threshold=True):
    """Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)] in global bar indices.
    entry_pos / short_needs_threshold exist only for the diagnostic variants; the ARM B reading is the defaults."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    out = []
    for s, e in zip(starts, ends):
        if e - s < entry_pos + 1 or e - s < 12:
            continue
        rng = float(np.max(h[s:s + 12]) - np.min(l[s:s + 12]))
        disp = float(c[s + 11] - o[s])
        big = abs(disp) >= threshold_frac * rng
        if disp > 0 and big:
            side = 1
        elif disp < 0 and (big or not short_needs_threshold):
            side = -1
        else:
            continue
        ent = s + entry_pos
        ep = float(o[ent])
        stop = ep - side * stop_frac * rng
        best = None
        xb, xp = e - 1, float(c[e - 1])
        for j in range(ent, e):
            if j > ent:
                cj = float(c[j - 1])
                best = cj if best is None else (max(best, cj) if side > 0 else min(best, cj))
                cand = best - side * trail_frac * rng
                stop = max(stop, cand) if side > 0 else min(stop, cand)
                if side * (o[j] - stop) <= 0:
                    xb, xp = j, float(o[j])
                    break
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                xb, xp = j, float(stop)
                break
        out.append((int(ent), int(xb), int(side), ep, xp, float(side * (xp - ep))))
    return out
