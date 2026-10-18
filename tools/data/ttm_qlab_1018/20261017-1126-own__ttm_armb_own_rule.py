"""TTM arm B for QL_GAPFILL_NQ (20261017-1126-own): the prereg's Mechanism text, implemented by TTM from the text ONLY,
BEFORE the plugin code was read. Pure function over the registry master's arrays (open/high/low/close/day_id).
The three knob VALUES (gap_min_pts, stop_frac, atr_bars) are passed in by the harness: the prereg names the knobs but not
their defaults, so the harness takes only the plugin's DEFAULT_PARAMS literal (AST-extracted, nothing else read)."""
import numpy as np

READING = [
    "session = one ET calendar day of the master (day_id); bar 0 = the session's first bar in the data (every session in the "
    "window starts 09:30, checked in the harness)",
    "prior_close = close of the LAST bar of the PREVIOUS session present in the loaded data (no calendar-gap check); the first "
    "session of the loaded window has no prior close -> skipped",
    "gap = open[bar 0] - prior_close; LONG if gap > +gap_min_pts, SHORT if gap < -gap_min_pts (strict inequalities), else no trade",
    "entry fills at bar 0's OPEN; one trade per session; 1 contract",
    "ATR = simple mean of TRUE RANGE over the prior session's last atr_bars bars; TR = max(h-l, |h-prev_c|, |l-prev_c|) with "
    "prev_c the previous bar's close when that bar is in the same prior session, else h-l; a prior session with fewer than "
    "atr_bars bars -> no ATR -> session skipped (never happens in this window); no Wilder smoothing",
    "stop = entry - stop_frac*ATR (long) / entry + stop_frac*ATR (short), FIXED at entry ('trailing' read as the ATR window, "
    "not a trailing stop)",
    "stop live from the entry bar (bar 0) on: on bars after the entry bar, a bar whose OPEN is at/past the stop exits at that "
    "open; otherwise a bar whose low (long) / high (short) touches the stop exits AT the stop price",
    "no target, no time stop: else exit at the CLOSE of the session's last bar in the data (half-days / short sessions = their "
    "own last bar)",
    "gross pts = side * (exit_px - entry_px); trades recorded at the FILL bars (global indices)",
]


def _sessions(day_id):
    day_id = np.asarray(day_id)
    n = len(day_id)
    starts = np.r_[0, np.flatnonzero(np.diff(day_id)) + 1]
    ends = np.r_[starts[1:], n]
    return starts, ends


def _atr_prior(h, l, c, ps, pe, atr_bars, atr_mode="tr"):
    """ATR over the prior session [ps, pe): its last atr_bars bars. atr_mode 'tr' = true range (arm B); 'hl' = high-low
    (diagnostic variant only)."""
    if pe - ps < atr_bars:
        return None
    a = pe - atr_bars
    rng = h[a:pe] - l[a:pe]
    if atr_mode == "hl":
        return float(rng.mean())
    tr = rng.copy()
    for i, j in enumerate(range(a, pe)):
        if j - 1 >= ps:
            pc = c[j - 1]
            tr[i] = max(h[j] - l[j], abs(h[j] - pc), abs(l[j] - pc))
    return float(tr.mean())


def own_rule(o, h, l, c, day_id, gap_min_pts, stop_frac, atr_bars, atr_mode="tr", gap_through_on_entry_bar=False):
    """Returns [(entry_bar, exit_bar, side, entry_px, exit_px, gross_pts)]."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    atr_bars = int(atr_bars)
    starts, ends = _sessions(day_id)
    out = []
    for si in range(1, len(starts)):
        s, e = starts[si], ends[si]
        ps, pe = starts[si - 1], ends[si - 1]
        prior_close = c[pe - 1]
        gap = o[s] - prior_close
        if gap > gap_min_pts:
            side = 1
        elif gap < -gap_min_pts:
            side = -1
        else:
            continue
        atr = _atr_prior(h, l, c, ps, pe, atr_bars, atr_mode)
        if atr is None:
            continue
        ent = s
        ep = o[ent]
        stop = ep - side * stop_frac * atr
        xb, xp = e - 1, c[e - 1]
        for j in range(ent, e):
            if j > ent or gap_through_on_entry_bar:
                if side * (o[j] - stop) <= 0:
                    xb, xp = j, o[j]
                    break
            hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
            if hit:
                xb, xp = j, stop
                break
        out.append((int(ent), int(xb), int(side), float(ep), float(xp), float(side * (xp - ep))))
    return out
