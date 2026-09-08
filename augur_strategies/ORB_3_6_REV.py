"""
ORB 3.6 REV — the FAILED-BREAKOUT REVERSAL ("the trap trade") (2026-09-08, round 10).

ORB_3_6 (and every ancestor) trades ONE breakout per session and the day ends the
moment that trade exits. This fork asks a structural question: when that breakout is
STOPPED OUT, is the failure itself information? A breakout that reverses hard enough to
close back through the OPPOSITE opening-range level looks like a trapped-longs (or
trapped-shorts) event — the crowd that bought/sold the break is now underwater and has
to get out, which is exactly the kind of one-directional forced flow a reversal trade
wants to ride.

Adds FOUR knobs, all default OFF/0 so this file is BIT-IDENTICAL to ORB_3_6 with
everything at its default (smoke test at the bottom asserts it):

  * reverse_after_stop (bool) — after the first trade is STOPPED OUT (its INITIAL stop,
    not a breakeven-moved stop, unless reverse_after_be is set), allow ONE trade in the
    OPPOSITE direction, triggered the moment a later bar in the SAME session CLOSES
    beyond the opposite opening-range level (failed long -> close <= dn_lvl; failed
    short -> close >= up_lvl). Scanning starts at the exit bar itself (its close is
    already known once it closes, live-legal) through the session's last bar.
  * reverse_after_be (bool) — also allow the reversal when the first trade's exit was a
    STOP that had already been moved to breakeven by be_after_R (a scratch/small-loss
    exit rather than a clean initial-stop loss). OFF means only a true initial-stop-out
    triggers the trap trade.
  * rev_stop_frac / rev_target_R (float, 0 = reuse stop_frac / target_R) — the
    reversal's OWN risk geometry, measured from the reversal's own entry price with
    risk = rev_stop_frac * rng (rng = the same opening-range width). The reversal uses
    the SAME be_after_R breakeven rule as the parent (armed on a finished bar's close,
    takes effect next bar) — no separate breakeven knob, by design (keeps the geometry
    change isolated to stop/target only, per spec).
  * rev_direct — accepted for interface completeness but NOT IMPLEMENTED this round.
    See the note below __main__: the described scenario (first trade never taken
    because trade_mode forbade the direction, then price closes through the allowed
    side) turns out to already be exactly what the base entry loop does on its own —
    the allowed-direction close-cross is checked every bar regardless of what an
    earlier forbidden-direction breakout did, so a "direct" add-on has no daylight to
    stand in without inventing a rule the spec doesn't state. Kept simple per the
    spec's own "skip if it makes the code messy" clause.

The reversal trade is a SINGLE-LOT stop/target/EOD-flat trade only — no partial exit,
no N-bar trail (the spec only asked for "the reversal's own geometry" = stop/target).

LIVE-LEGAL BY CONSTRUCTION: the reversal's entry signal is a bar CLOSE (same style as
close_confirm entries elsewhere in this family) and its stop/target management reads
only that bar and earlier ones — nothing on an unfinished bar is ever used. The one
same-bar subtlety: the reversal signal is allowed to fire on the very bar the first
trade's stop was hit (that bar's OWN close, known once the bar closes, even though the
stop-fill used that bar's intrabar low) — this mirrors how close_confirm entries already
use a bar's close after other things happened earlier in the same bar.

Knobs = 3.6's fourteen + reverse_after_stop + reverse_after_be + rev_stop_frac +
rev_target_R + rev_direct (no-op).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.6 REV'
DESCRIPTION   = ("ORB_3_6 plus a failed-breakout reversal ('trap trade'): after the "
                 "first trade is stopped out, allow ONE opposite-direction trade once "
                 "price closes back through the opposite opening-range level, with its "
                 "own stop/target geometry. Everything OFF by default reproduces "
                 "ORB_3_6 exactly.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars": {
        "default": 2, "min": 1, "max": 12, "step": 1, "type": "int",
        "label": "Opening range (bars)",
        "tooltip": "Opening-range length in BARS. On 5-min data: 1=5min, 2=10min, 3=15min.",
    },
    "trade_mode": {
        "default": "First-candle dir", "type": "str",
        "options": ["Both", "First-candle dir", "Long Only", "Short Only"],
        "label": "Direction",
        "tooltip": "Both = trade either break. First-candle dir = only the way the "
                   "opening-range candle closed (the grail hunt's sole aggregate survivor).",
    },
    "stop_frac": {
        "default": 2.0, "min": 0.5, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Stop (× range width)",
        "tooltip": "Stop distance from entry as a multiple of the opening-range width. "
                   "FLOOR is 0.5 on purpose: below that the exact-stop-fill assumption "
                   "inflates PF.",
    },
    "vpace_filter": {
        "default": 0.7, "min": 0.0, "max": 1.4, "step": 0.1, "type": "float",
        "label": "Volume-pace gate (× trailing norm)",
        "tooltip": "Require the session's volume SO FAR (bars before this one) to be at "
                   "least this multiple of the same-length prefix averaged over the prior "
                   "20 sessions. LIVE-LEGAL: the fill bar's own volume is never read. 0=off.",
    },
    "breakout_buf": {
        "default": 0.25, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout buffer (× range)",
        "tooltip": "Require price to clear the range edge by this fraction of the range "
                   "width before entering. 0 = trade the touch.",
    },
    "close_confirm": {
        "default": True, "type": "bool",
        "label": "Close-confirmed entry (skip false wicks)",
        "tooltip": "ON (default) = only enter when a bar CLOSES beyond the edge, filling at "
                   "that close - the live-legal entry the grail hunt certified. OFF = touch "
                   "entry (models a resting stop; legal fill, but pairs with intrabar "
                   "quantities in ways the audit flagged - keep ON unless researching).",
    },
    "partial_exit_R": {
        "default": 3.0, "min": 0.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Partial exit / lot-1 TP (× risk, 0=off)",
        "tooltip": "Exit HALF at this R-multiple of initial risk. Remaining half trails / "
                   "rides. 0 = single lot.",
    },
    "trail_bars": {
        "default": 3, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop / lot-2 (bars, 0=off)",
        "tooltip": "Trail the stop to the rolling N-bar low/high (prior bars only). If a "
                   "partial is set, activates after it fires. 0 = fixed stop.",
    },
    "be_after_R": {
        "default": 0.0, "min": 0.0, "max": 4.0, "step": 0.1, "type": "float",
        "label": "Breakeven after (× risk, 0=off)",
        "tooltip": "Once a bar CLOSES at/beyond entry + this multiple of initial risk, "
                   "move the stop to ENTRY from the next bar on. Applies to BOTH the "
                   "first trade and (if taken) the reversal trade. 0 = off.",
    },
    "atr_filter": {
        "default": 0.7, "min": 0.0, "max": 1.5, "step": 0.1, "type": "float",
        "label": "Vol-regime filter (× trailing median, 0=off)",
        "tooltip": "Skip a session when its recent 5-session avg range is BELOW this "
                   "multiple of the trailing 60-session median session range. Trailing-only.",
    },
    "target_R": {
        "default": 5.5, "min": 0.0, "max": 8.0, "step": 0.5, "type": "float",
        "label": "Runner target (× risk, 0=EOD/trail only)",
        "tooltip": "Optional hard take-profit for the runner at this multiple of initial "
                   "risk. 0 = ride to trail-out / close.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Always exit at each session's last bar (no overnight). Keep ON.",
    },
    "skip_holidays": {
        "default": True, "type": "bool",
        "label": "Skip holiday half-days",
        "tooltip": "Skip early-close sessions, detected by session LENGTH. Calendar-known.",
    },
    # ── THE new levers ────────────────────────────────────────────────────────
    "reverse_after_stop": {
        "default": False, "type": "bool",
        "label": "Reverse after stop-out (trap trade)",
        "tooltip": "After the first trade is STOPPED OUT on its INITIAL stop, allow ONE "
                   "opposite-direction trade once a later bar in the same session "
                   "CLOSES beyond the opposite opening-range level. OFF = ORB_3_6 exactly.",
    },
    "reverse_after_be": {
        "default": False, "type": "bool",
        "label": "...also after a breakeven stop-out",
        "tooltip": "Extends reverse_after_stop to also trigger when the stop that got "
                   "hit had already been moved to breakeven by be_after_R (a scratch, "
                   "not a full loss). OFF = only a true initial-stop loss can trigger it.",
    },
    "rev_stop_frac": {
        "default": 0.0, "min": 0.0, "max": 3.0, "step": 0.25, "type": "float",
        "label": "Reversal stop (× range width, 0=reuse stop_frac)",
        "tooltip": "The trap trade's own stop distance as a multiple of the opening-"
                   "range width, measured from the reversal's own entry. 0 = reuse "
                   "stop_frac.",
    },
    "rev_target_R": {
        "default": 0.0, "min": 0.0, "max": 8.0, "step": 0.5, "type": "float",
        "label": "Reversal target (× reversal risk, 0=reuse target_R)",
        "tooltip": "The trap trade's own hard take-profit as a multiple of ITS OWN risk "
                   "(rev_stop_frac x range). 0 = reuse target_R.",
    },
    "rev_direct": {
        "default": False, "type": "bool",
        "label": "Direct reversal on forbidden-side breakout (NOT IMPLEMENTED)",
        "tooltip": "Placeholder only this round - has no effect. See the file docstring: "
                   "the scenario collapses into behaviour the base entry loop already "
                   "provides, so it was left un-coded rather than invent an ungrounded "
                   "rule. Kept as a knob for interface completeness / future round.",
    },
}

PARAM_GRID_PRESETS = {
    # Open ranges on the new knobs, crown fixed elsewhere - for an auto-validate later.
    "Trap trade (crown base, open reversal knobs)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.5],
        "vpace_filter": [0.8], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [0.0], "trail_bars": [0], "target_R": [5.0],
        "atr_filter": [0.75], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.5],
        "reverse_after_stop": [True], "reverse_after_be": [False, True],
        "rev_stop_frac": [0.0, 1.5, 2.0], "rev_target_R": [0.0, 3.0],
        "rev_direct": [False],
    },
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
    reverse_after_stop: bool = False, reverse_after_be: bool = False,
    rev_stop_frac: float = 0.0, rev_target_R: float = 0.0, rev_direct: bool = False,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
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
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
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
    rev_trade_log = []
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
        if m > or_bars + 1 and or_bars >= 1:
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

                # ── round-10 bookkeeping: what happened to the FIRST trade ────
                first_exit_kind = None   # 'stop_init' | 'stop_be' | 'target' | 'eod' | None
                first_exit_k = None
                first_dir = 0

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
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; continue
                        elif short_ok and dn:
                            entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False; continue
                    else:
                        # ── BREAKEVEN (3.6 lever): armed on a PRIOR bar's close,
                        #    applied here — i.e. from the bar AFTER the arming close.
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
                                raw   = ex_px - entry
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                first_exit_kind = 'stop_be' if be_armed else 'stop_init'
                                first_exit_k = k; first_dir = 1
                                pos = 0; break
                            if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                p_pnl = ptgt - entry; p_done = True; continue
                            if target_R > 0 and sh[k] >= tgt:
                                raw = tgt - entry
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                first_exit_kind = 'target'; first_exit_k = k; first_dir = 1
                                pos = 0; break
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                raw   = entry - ex_px
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                first_exit_kind = 'stop_be' if be_armed else 'stop_init'
                                first_exit_k = k; first_dir = -1
                                pos = 0; break
                            if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                                be_armed = True
                            if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                p_pnl = entry - ptgt; p_done = True; continue
                            if target_R > 0 and sl[k] <= tgt:
                                raw = entry - tgt
                                pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
                                first_exit_kind = 'target'; first_exit_k = k; first_dir = -1
                                pos = 0; break
                if pos != 0:                                        # EOD flat
                    raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry))
                    first_exit_kind = 'eod'; first_exit_k = m - 1
                    first_dir = 1 if pos > 0 else -1

                # ── round-10: the trap trade ───────────────────────────────
                do_rev = False
                if reverse_after_stop and first_exit_kind == 'stop_init':
                    do_rev = True
                elif reverse_after_stop and reverse_after_be and first_exit_kind == 'stop_be':
                    do_rev = True

                if do_rev and first_exit_k is not None and first_exit_k < m - 1:
                    rev_dir = -first_dir
                    for rk in range(first_exit_k, m):
                        trig = (sc[rk] >= up_lvl) if rev_dir > 0 else (sc[rk] <= dn_lvl)
                        if not trig:
                            continue
                        r_entry = sc[rk]
                        r_risk  = (rev_stop_frac if rev_stop_frac > 0 else stop_frac) * rng
                        r_tR    = rev_target_R if rev_target_R > 0 else target_R
                        if rev_dir > 0:
                            r_stop = r_entry - r_risk
                            r_tgt  = r_entry + r_tR * r_risk if r_tR > 0 else np.inf
                            r_belv = r_entry + be_after_R * r_risk if be_after_R > 0 else np.nan
                        else:
                            r_stop = r_entry + r_risk
                            r_tgt  = r_entry - r_tR * r_risk if r_tR > 0 else -np.inf
                            r_belv = r_entry - be_after_R * r_risk if be_after_R > 0 else np.nan
                        r_be_armed = False
                        r_pnl = None
                        r_exit_rel = m - 1
                        for rk2 in range(rk + 1, m):
                            if r_be_armed:
                                r_stop = max(r_stop, r_entry) if rev_dir > 0 else min(r_stop, r_entry)
                            if rev_dir > 0:
                                if sl[rk2] <= r_stop:
                                    ex_px = so[rk2] if so[rk2] < r_stop else r_stop
                                    r_pnl = ex_px - r_entry; r_exit_rel = rk2; break
                                if be_after_R > 0 and not r_be_armed and sc[rk2] >= r_belv:
                                    r_be_armed = True
                                if r_tR > 0 and sh[rk2] >= r_tgt:
                                    r_pnl = r_tgt - r_entry; r_exit_rel = rk2; break
                            else:
                                if sh[rk2] >= r_stop:
                                    ex_px = so[rk2] if so[rk2] > r_stop else r_stop
                                    r_pnl = r_entry - ex_px; r_exit_rel = rk2; break
                                if be_after_R > 0 and not r_be_armed and sc[rk2] <= r_belv:
                                    r_be_armed = True
                                if r_tR > 0 and sl[rk2] <= r_tgt:
                                    r_pnl = r_entry - r_tgt; r_exit_rel = rk2; break
                        if r_pnl is None:                          # EOD flat
                            r_pnl = (sc[-1] - r_entry) if rev_dir > 0 else (r_entry - sc[-1])
                            r_exit_rel = m - 1
                        pnl_list.append(r_pnl)
                        if return_trades:
                            trade_log.append((i + rk, i + r_exit_rel, r_pnl, rev_dir, r_entry))
                            rev_trade_log.append((i + rk, i + r_exit_rel, r_pnl, rev_dir, r_entry))
                        break   # ONE reversal trade only
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
        out["trades_rev"] = rev_trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test: (1) everything-OFF must be BIT-IDENTICAL to ORB_3_6.py on the #314
# crown params; (2) reverse_after_stop=True must actually change results and emit
# reversal trades.
# Run:  python augur_strategies/ORB_3_6_REV.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import importlib.util as ilu
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER  = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df  = pd.read_csv(MASTER)
    dt  = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)

    spec = ilu.spec_from_file_location("_orb36", os.path.join(ROOT, "augur_strategies", "ORB_3_6.py"))
    base = ilu.module_from_spec(spec); spec.loader.exec_module(base)

    CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
                 partial_exit_R=0.0, trail_bars=0, target_R=5.0,
                 atr_filter=0.75, vpace_filter=0.8, breakout_buf=0.25,
                 stop_frac=2.5, be_after_R=0.5, flat_eod=True, skip_holidays=True)
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    kw = dict(volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)

    r0 = base.run_backtest(*args, **kw, **CROWN)
    r1 = run_backtest(*args, **kw, **CROWN)   # all new knobs at default
    same = (r0["num_trades"] == r1["num_trades"]
            and abs(r0["total_pnl"] - r1["total_pnl"]) < 1e-9)
    print("all-OFF parity vs ORB_3_6: %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if same else "FAIL", r0["num_trades"], r1["num_trades"],
        r0["total_pnl"], r1["total_pnl"]))

    r2 = run_backtest(*args, **kw, **CROWN, reverse_after_stop=True)
    n_rev = len(r2.get("trades_rev") or [])
    print("reverse_after_stop=True changes results: %s  (pnl %.1f -> %.1f, n %d -> %d, rev trades %d)" % (
        "PASS" if abs(r2["total_pnl"] - r1["total_pnl"]) > 1e-9 else "FAIL",
        r1["total_pnl"], r2["total_pnl"], r1["num_trades"], r2["num_trades"], n_rev))
    sys.exit(0 if same else 1)
