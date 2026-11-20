"""
ORB BREAK2 1.0 - the ORB #314 mechanism (ORB_3_6.py core) PLUS a second break: when the first-candle-direction trade
exits on its STOP (initial or breakeven), take the OPPOSITE side's close-confirmed break later the same session.
Family ORB.

ORIGIN (w132 alpha hunt, lane ORB, 2026-11-20): W132_ALPHA.md leg RR_SCREEN1106_SECOND_break_opposite_side_after_stop_market
("SCREEN1106 second break"), one of the 5 legs FRONTIER's 2016-19 prefilter kept, as a SWAP for ORB #314.
Harness: C:/EdgeLog/_anatomy_cache/t242_orb/w132r2/screen_r2.py, cell "SECOND break, opposite side after stop (market)"
(dict(flip=True)); pre-WF original C:/EdgeLog/_anatomy_cache/t242_orb/screen1106/screen.py. Leg CSV:
C:/EdgeLog/manager/reports/w132_orb_legs/RR_SCREEN1106_SECOND_break_opposite_side_after_stop_market.csv.
Prereg C:/EdgeLog/manager/prereg/PREREG_orb_break2_validate_2026-11-20.md.

WHAT THIS IS
  ORB_3_6.py's run_backtest copied UNCHANGED (sessions, holiday / vol-regime / v-pace gates, close-confirm entry,
  stop-first gap-through fills, BE on a close acting next bar, target, EOD flat, return_levels), with ONE addition
  (marked BREAK2): if the first trade exited on its stop at bar x, scan bars x+1.. for the first bar that CLOSES beyond
  the OPPOSITE edge (or_lo - buf x range for a stopped long, or_hi + buf x range for a stopped short), enter at that
  close, risk = stop_frac x range, same BE / target / EOD exits. Harness rules kept exactly: no v-pace gate on the
  second entry, one second trade max, a BE stop counts as a stop, a target / EOD exit gets no second trade.
  The second leg's exit is single-lot (no partial, no trail) - both pinned off here, as in ORB_3_6_R6.py.
  Harness point = #314's champion knobs: or_bars 2, stop_frac 2.5, breakout_buf 0.25, be_after_R 0.5, target_R 5.0,
  atr_filter 0.75, vpace_filter 0.8, first-candle direction, close_confirm on.
  DEFAULT_PARAMS defaults = that point; ranges = ORB_3_6_R6.py's five open knobs. second_break pinned ON
  (second_break False = ORB_3_6 bit-for-bit).

NO LOOK-AHEAD: core inherited from ORB_3_6. The second entry reads only the stop bar's outcome (known at that bar) and
closes of LATER finished bars; it fills at the break bar's close and its exits start the bar after. The OR levels are
fixed at bar or_bars-1. No ADJ levels are used, so no ROLL_SIGNAL is declared - same as ORB_3_6_R6.py.
"""
# AUGUR-SOURCE: claude-review
import numpy as np

STRATEGY_NAME = "ORB BREAK2 1.0 - #314 mechanism + opposite-side second break after a stop"
DESCRIPTION = ("ORB #314's close-confirm breakout (first-candle direction, breakeven after R, hard target, v-pace + "
               "vol-regime gates); when that trade stops out, take the opposite edge's close-confirmed break the same "
               "session. Defaults = the w132 harness leg SCREEN1106 second break; R6's five knobs ranged.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.5,  "min": 2.0,  "max": 2.5,  "step": 0.25, "type": "float", "label": "Stop (x range width) - NARROW RANGE 2.0-2.5"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close - PINNED ON (live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF"},
    "be_after_R":     {"default": 0.5,  "min": 0.5,  "max": 1.0,  "step": 0.25, "type": "float", "label": "Breakeven after (x risk) - NARROW RANGE 0.5-1.0"},
    "target_R":       {"default": 5.0,  "min": 5.0,  "max": 6.5,  "step": 0.5,  "type": "float", "label": "Target (x risk) - NARROW RANGE 5.0-6.5"},
    "atr_filter":     {"default": 0.75, "min": 0.75, "max": 0.85, "step": 0.05, "type": "float", "label": "Vol-regime filter - NARROW RANGE 0.75-0.85"},
    "vpace_filter":   {"default": 0.8,  "min": 0.75, "max": 0.85, "step": 0.05, "type": "float", "label": "Volume-pace gate - NARROW RANGE 0.75-0.85"},
    "second_break":   {"default": True,  "type": "bool", "options": [True],                                      "label": "Second break after a stop - PINNED ON (the idea)"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays - PINNED on"},
}

PARAM_GRID_PRESETS = {
    "Short  (harness point, second break on/off)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.5], "breakout_buf": [0.25],
        "close_confirm": [True], "partial_exit_R": [0.0], "trail_bars": [0], "be_after_R": [0.5], "target_R": [5.0],
        "atr_filter": [0.75], "vpace_filter": [0.8], "second_break": [True, False], "flat_eod": [True], "skip_holidays": [True],
    },
}


def _break2_leg(so, sh, sl, sc, m, k0, side, entry, risk, be_after_R, target_R):
    """The second-break trade's exit walk = ORB_3_6's single-lot exit (no partial, no trail):
    stop checked first with gap-through fill, BE armed on a bar CLOSE and applied from the
    next bar, hard target, else flat at the session's last close. Entry bar k0 is not
    re-read (entry at its close). Returns (pnl pts, exit bar, BE-arm bar or -1)."""
    stop = entry - side * risk
    tgt = entry + side * target_R * risk if target_R > 0 else side * np.inf
    be = entry + side * be_after_R * risk if be_after_R > 0 else np.nan
    armed = False; bk = -1
    for k in range(k0 + 1, m):
        if armed:
            stop = max(stop, entry) if side > 0 else min(stop, entry)
        if side > 0:
            if sl[k] <= stop:
                return (so[k] if so[k] < stop else stop) - entry, k, bk
            if be_after_R > 0 and not armed and sc[k] >= be:
                armed = True; bk = k
            if target_R > 0 and sh[k] >= tgt:
                return tgt - entry, k, bk
        else:
            if sh[k] >= stop:
                return entry - (so[k] if so[k] > stop else stop), k, bk
            if be_after_R > 0 and not armed and sc[k] <= be:
                armed = True; bk = k
            if target_R > 0 and sl[k] <= tgt:
                return entry - tgt, k, bk
    return side * (sc[m - 1] - entry), m - 1, bk


def _levels_row(i, ek, pos, entry, risk, tgt, be_lvl, be_k, trail_bars, partial_exit_R):
    """One out["levels"] entry (return_levels -- see the docstring). Bar numbers are
    absolute indices into the arrays this call was handed. The initial stop is rebuilt
    with the very expression the entry used (entry -/+ risk), so it is the same float.
    be_bar is the bar at whose CLOSE breakeven armed (the stop is `be_stop` from the NEXT
    bar), or None. `trail`/`partial` say the stop can also move in ways not listed here
    (off on the live ORB #314 leg); a consumer must not rest orders from such a row."""
    def _fin(x):
        x = float(x)
        return x if np.isfinite(x) else None
    be_trigger = _fin(be_lvl)
    return {
        "entry_bar": int(i + ek), "side": int(pos), "entry": float(entry), "risk": float(risk),
        "stop": float(entry - risk) if pos > 0 else float(entry + risk),
        "target": _fin(tgt), "be_trigger": be_trigger,
        "be_stop": float(entry) if be_trigger is not None else None,
        "be_bar": int(i + be_k) if be_k >= 0 else None,
        "trail": bool(trail_bars > 0), "partial": bool(partial_exit_R > 0),
    }


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 2, trade_mode: str = "First-candle dir",
    stop_frac: float = 2.0, vol_filter: float = 0.0, vpace_filter: float = 0.7,
    breakout_buf: float = 0.25, close_confirm: bool = True,
    partial_exit_R: float = 3.0, trail_bars: int = 3, be_after_R: float = 0.0,
    atr_filter: float = 0.7, target_R: float = 5.5,
    flat_eod: bool = True, skip_holidays: bool = True,
    session_in_progress: bool = False,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    return_levels: bool = False,
    second_break: bool = True,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float) if volumes is not None else None
    n = len(c)
    if n < 10:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        return None

    allow_long  = trade_mode in ("Both", "First-candle dir", "Long Only")
    allow_short = trade_mode in ("Both", "First-candle dir", "Short Only")

    # ── Session boundaries ────────────────────────────────────────────────────
    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b

    # ── Half-day / holiday skip (skip_holidays) ───────────────────────────────
    # LIVE opt-in (session_in_progress, default False): a live engine hands this
    # function today's session while it is still being built bar by bar, so the LAST
    # session in `_sess_bounds` is short of the median for a reason that has nothing to
    # do with a holiday. session_in_progress=False (every existing backtest, every
    # sweep/validate call) reproduces the exact behaviour above, unconditionally. The
    # caller (api/cloud_signal.py) sets it True only when the last session is today's
    # AND the market calendar does not list today as a recognised early close -- on a
    # real half day this stays False and the length test still fires exactly as before.
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        _last_sess_idx = len(_sess_bounds) - 1
        for _si, (a, b) in enumerate(_sess_bounds):
            if (b - a) < _half:
                if session_in_progress and _si == _last_sess_idx:
                    continue          # exempt: this is the in-progress final session
                _holiday_start.add(a)

    # ── Vol-regime filter (atr_filter > 0): trailing-only, no look-ahead ──────
    _allow_start = {}
    if atr_filter > 0 and len(_sess_bounds) > 6:
        _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 6:
                continue                          # warm-up → allow
            _recent = _srng[max(0, _si - 5):_si].mean()
            _ref    = np.median(_srng[max(0, _si - 60):_si])
            if _ref > 0 and _recent < atr_filter * _ref:
                _allow_start[a] = False

    # ── V-PACE filter (legal): prior bars vs prior-20-session prefix norm ─────
    _pace_ord, _pace_ref = {}, None
    if vpace_filter > 0 and v is not None and len(_sess_bounds) > 21:
        _pace_ord = {a: si for si, (a, b) in enumerate(_sess_bounds)}
        _K = max(b - a for a, b in _sess_bounds)
        _pref = np.full((len(_sess_bounds), _K + 1), np.nan)
        for _si, (a, b) in enumerate(_sess_bounds):
            _cs = np.cumsum(np.asarray(v[a:b], dtype=float))
            _pref[_si, 1:(b - a) + 1] = _cs / np.arange(1, (b - a) + 1)
        _pace_ref = np.full_like(_pref, np.nan)
        for _si in range(20, len(_sess_bounds)):
            _pace_ref[_si, :] = np.nanmean(_pref[_si - 20:_si, :], axis=0)

    pnl_list, trade_log = [], []
    levels_log = []                      # return_levels only -- parallel to pnl_list
    i = 0
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        m = j - i
        if i in _holiday_start:                  # half-day / holiday skip
            i = j; continue
        if _allow_start.get(i, True) is False:   # vol-regime filter skipped this session
            i = j; continue
        if m > or_bars and or_bars >= 1:
            so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
            sv = v[i:j] if v is not None else None
            or_hi = sh[:or_bars].max()
            or_lo = sl[:or_bars].min()
            rng   = or_hi - or_lo
            if rng > 0:
                or_dir = 1 if sc[or_bars - 1] >= so[0] else -1
                buf    = breakout_buf * rng
                up_lvl = or_hi + buf
                dn_lvl = or_lo - buf
                long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
                short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                be_armed = False; be_lvl = np.nan
                be_k = -1                        # bar whose close armed breakeven (return_levels)
                _xk = -1; _s1 = 0                # BREAK2: bar + side of a first trade that exited on its STOP
                for k in range(or_bars, m):
                    if pos == 0:
                        if close_confirm:
                            up = sc[k] >= up_lvl
                            dn = sc[k] <= dn_lvl
                        else:
                            up = sh[k] >= up_lvl
                            dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        # LEGAL v-pace gate — inputs closed BEFORE this bar.
                        if vpace_filter > 0 and _pace_ref is not None and sv is not None and k > 0:
                            _si2 = _pace_ord.get(i)
                            if _si2 is not None and k < _pace_ref.shape[1]:
                                _rf = _pace_ref[_si2, k]
                                if _rf == _rf and _rf > 0 and sv[:k].mean() < vpace_filter * _rf:
                                    continue
                        # legacy look-ahead filter — OFF, kept only for 3.1 parity by hand.
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = sc[k] if close_confirm else (max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl)
                            risk  = stop_frac * rng
                            stop  = entry - risk
                            tgt   = entry + target_R * risk if target_R > 0 else np.inf
                            ptgt  = entry + partial_exit_R * risk if partial_exit_R > 0 else np.inf
                            be_lvl = entry + be_after_R * risk if be_after_R > 0 else np.nan
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; be_k = -1; continue
                        elif short_ok and dn:
                            entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; be_k = -1; continue
                    else:
                        # ── BREAKEVEN (the 3.6 lever): armed on a PRIOR bar's close,
                        #    applied here — i.e. from the bar AFTER the arming close.
                        #    Legal: only finished bars are read.
                        if be_armed:
                            stop = max(stop, entry) if pos > 0 else min(stop, entry)
                        # ── Trailing stop: prior bars' extremes only (excludes k).
                        if trail_bars > 0 and (partial_exit_R == 0 or p_done):
                            ts = max(ek, k - trail_bars)
                            if pos > 0:
                                trail_low = sl[ts:k].min() if k > ts else sl[ek]
                                stop = max(stop, trail_low)   # only move up
                            else:
                                trail_high = sh[ts:k].max() if k > ts else sh[ek]
                                stop = min(stop, trail_high)  # only move down

                        if pos > 0:
                            if sl[k] <= stop:                       # stop first (pessimistic)
                                ex_px = so[k] if so[k] < stop else stop   # gap-through
                                _xk = k; _s1 = 1
                                raw   = ex_px - entry
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                if return_levels: levels_log.append(_levels_row(i, ek, pos, entry, risk, tgt, be_lvl, be_k, trail_bars, partial_exit_R))
                                pos = 0; break
                            # arm BE off this bar's CLOSE — takes effect next bar.
                            # (checked before the partial's `continue` so a partial-fire
                            #  bar can still arm; ordering is state-neutral this bar.)
                            if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                                be_armed = True; be_k = k
                            if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                p_pnl = ptgt - entry; p_done = True; continue
                            if target_R > 0 and sh[k] >= tgt:
                                raw = tgt - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                if return_levels: levels_log.append(_levels_row(i, ek, pos, entry, risk, tgt, be_lvl, be_k, trail_bars, partial_exit_R))
                                pos = 0; break
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                _xk = k; _s1 = -1
                                raw   = entry - ex_px
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                if return_levels: levels_log.append(_levels_row(i, ek, pos, entry, risk, tgt, be_lvl, be_k, trail_bars, partial_exit_R))
                                pos = 0; break
                            if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                                be_armed = True; be_k = k
                            if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                p_pnl = entry - ptgt; p_done = True; continue
                            if target_R > 0 and sl[k] <= tgt:
                                raw = entry - tgt
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                if return_levels: levels_log.append(_levels_row(i, ek, pos, entry, risk, tgt, be_lvl, be_k, trail_bars, partial_exit_R))
                                pos = 0; break
                if pos != 0:                                        # EOD flat
                    raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry))
                    if return_levels: levels_log.append(_levels_row(i, ek, pos, entry, risk, tgt, be_lvl, be_k, trail_bars, partial_exit_R))
                # ── BREAK2 (the one addition): the first trade STOPPED (initial or breakeven stop),
                #    so take the OPPOSITE side's break: the first later bar (after the stop bar)
                #    that CLOSES beyond the other OR edge +/- buf, filled at that close. Same
                #    risk (stop_frac x range), same BE / target / EOD exits; no v-pace gate on
                #    the second entry (harness rule). Reads only finished bars - live-legal.
                if second_break and _xk >= 0 and close_confirm:
                    s2 = -_s1; lv2 = dn_lvl if _s1 > 0 else up_lvl
                    for k2 in range(_xk + 1, m):
                        if (s2 > 0 and sc[k2] >= lv2) or (s2 < 0 and sc[k2] <= lv2):
                            e2 = sc[k2]; r2 = stop_frac * rng
                            p2, x2, bk2 = _break2_leg(so, sh, sl, sc, m, k2, s2, e2, r2, be_after_R, target_R)
                            pnl_list.append(p2)
                            if return_trades: trade_log.append((i + k2, i + x2, p2, s2, e2))
                            if return_levels:
                                t2 = e2 + s2 * target_R * r2 if target_R > 0 else s2 * np.inf
                                b2 = e2 + s2 * be_after_R * r2 if be_after_R > 0 else np.nan
                                levels_log.append(_levels_row(i, k2, s2, e2, r2, t2, b2, bk2, 0, 0.0))
                            break
        i = j

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    if return_levels:
        out["levels"] = levels_log
    return out


