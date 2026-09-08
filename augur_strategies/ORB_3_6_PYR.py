"""
ORB 3.6 PYR — pyramiding (add a unit into a working trade), round 10 structural fork.

ORB_3_6 (the #314 crown's file) opens exactly one unit per breakout and rides it to the
runner target / trail / EOD. This fork adds ONE mechanism: once the trade is already
working, add a SECOND (and optionally third) unit at the SAME direction, sized off the
SAME opening-range risk, so a trade that is proving itself gets more size instead of the
strategy waiting for a fresh signal.

New knobs (all default OFF / no-op so pyr_add_R=0 reproduces ORB_3_6 byte-for-byte):

  pyr_add_R   (float, default 0=off) — once a bar CLOSES at or beyond entry + pyr_add_R
              x initial risk (longs; mirrored for shorts) and fewer than pyr_max adds
              have happened yet, add ONE more unit AT THAT CLOSE (same live-legal fill
              rule as the parent's own entry — only a finished bar's close is read).
  pyr_stop    ("shared" default, or "own") — "shared": the added unit's stop tracks the
              ORIGINAL unit's current stop variable every bar (so if breakeven/trailing
              has already moved it, the add inherits that for free — and because it is
              always the identical stop LEVEL, a shared add always exits on the exact
              same bar as unit 1, just at its own entry price). "own": the added unit
              gets an independent, fixed stop set at add_price -/+ pyr_stop_frac*rng and
              is NOT managed by breakeven/trailing afterwards (documented simplification
              — the parent has no mechanism for tracking N independently-managed stops
              and the crown's own sweep runs with trail/partial both off).
  pyr_stop_frac (float, default 0 = fall back to stop_frac) — only used when
              pyr_stop=="own".
  pyr_max     (int, default 1) — max adds per trade. The 2nd add (only reachable if
              pyr_max>=2) triggers at entry + 2*pyr_add_R*risk.

The TARGET is the same original target R-level for every unit — no unit gets a richer
target than the trade it joined. Every unit is checked stop-first (pessimistic) with the
same gap-through fill rule as the parent, and only finished bars are read for any
decision (live-legal by construction, reads no more of the future than the parent).

BOOK-KEEPING: pnl_list carries the TRADE's TOTAL points (sum across every unit that
fired) so downstream $ math (COST is charged PER UNIT PER ROUND TRIP by the driver, not
here — this file returns POINTS same as the parent). return_trades tuples are extended
with two extra fields so a driver can also see the per-unit picture without re-deriving
it:  (entry_i, exit_i, total_pnl, dir, entry_px, n_units, avg_pnl_per_unit, add_pnls)
where add_pnls is a tuple of the ADDED units' own pnl in points (unit 1 / the original
entry is excluded from add_pnls — its pnl is total_pnl minus sum(add_pnls)).

pyr_add_R=0 → the pyramiding branch never runs at all; the original ORB_3_6 loop body
runs UNCHANGED (verbatim), asserted bit-identical in the __main__ smoke test.
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.6 PYR · legal base + pyramiding'
DESCRIPTION   = ("The ORB_3_6 legal base (breakeven-after-R lever, v-pace/ATR-regime "
                 "gates, partial+trail scale-out) plus ONE new lever: once the trade is "
                 "working, add a second/third unit at the same direction and original "
                 "risk once price CLOSES pyr_add_R x risk past entry. Target is shared "
                 "across units; stop is shared (inherits BE/trail) or independent. "
                 "pyr_add_R=0 reproduces ORB_3_6 exactly.")

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
                   "rides. 0 = single lot. Applies to unit 1 only.",
    },
    "trail_bars": {
        "default": 3, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Trailing stop / lot-2 (bars, 0=off)",
        "tooltip": "Trail the stop to the rolling N-bar low/high (prior bars only). If a "
                   "partial is set, activates after it fires. 0 = fixed stop. Applies to "
                   "unit 1's stop, which shared-mode adds inherit.",
    },
    "be_after_R": {
        "default": 0.0, "min": 0.0, "max": 4.0, "step": 0.1, "type": "float",
        "label": "Breakeven after (× risk, 0=off)",
        "tooltip": "Once a bar CLOSES at/beyond entry + this multiple of initial risk, "
                   "move the stop to ENTRY from the next bar on. 0 = off.",
    },
    # ── THE new lever ─────────────────────────────────────────────────────────
    "pyr_add_R": {
        "default": 0.0, "min": 0.0, "max": 3.0, "step": 0.1, "type": "float",
        "label": "Pyramid add trigger (× risk, 0=off)",
        "tooltip": "Once a bar CLOSES at/beyond entry + this multiple of initial risk, add "
                   "ONE more unit at that close, same direction, same original risk. 0 = off "
                   "(= ORB_3_6 exactly). The 2nd add (pyr_max=2) fires at 2x this.",
    },
    "pyr_stop": {
        "default": "shared", "type": "str", "options": ["shared", "own"],
        "label": "Add's stop",
        "tooltip": "shared = the added unit uses unit 1's CURRENT stop (inherits breakeven/"
                   "trailing for free; always exits the same bar as unit 1). own = the added "
                   "unit gets its own fixed stop at add_price -/+ pyr_stop_frac x range, not "
                   "managed afterwards.",
    },
    "pyr_stop_frac": {
        "default": 0.0, "min": 0.0, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Add's own stop (× range width, 0=use stop_frac)",
        "tooltip": "Only used when pyr_stop='own'. 0 = fall back to stop_frac's value.",
    },
    "pyr_max": {
        "default": 1, "min": 1, "max": 2, "step": 1, "type": "int",
        "label": "Max adds per trade",
        "tooltip": "1 = at most one add (2 units total). 2 = a second add at "
                   "entry + 2 x pyr_add_R x risk (3 units total).",
    },
    # ── Inherited knobs ────────────────────────────────────────────────────────
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
                   "risk. 0 = ride to trail-out / close. SHARED across every unit.",
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
}

PARAM_GRID_PRESETS = {
    # Hold the #314 crown FIXED, sweep ONLY the new pyramiding lever. Open ranges on
    # the new knobs so this can be auto-validated later.
    "Short  (pyramid scan on the #314 crown)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.5],
        "vpace_filter": [0.8], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [0.0], "trail_bars": [0], "target_R": [5.0],
        "atr_filter": [0.75], "flat_eod": [True], "skip_holidays": [True],
        "be_after_R": [0.5],
        "pyr_add_R": [0.0, 0.5, 1.0, 1.5, 2.0, 3.0],
        "pyr_stop": ["shared", "own"], "pyr_stop_frac": [0.0, 2.5], "pyr_max": [1, 2],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 2, trade_mode: str = "First-candle dir",
    stop_frac: float = 2.0, vol_filter: float = 0.0, vpace_filter: float = 0.7,
    breakout_buf: float = 0.25, close_confirm: bool = True,
    partial_exit_R: float = 3.0, trail_bars: int = 3, be_after_R: float = 0.0,
    pyr_add_R: float = 0.0, pyr_stop: str = "shared", pyr_stop_frac: float = 0.0,
    pyr_max: int = 1,
    atr_filter: float = 0.7, target_R: float = 5.5,
    flat_eod: bool = True, skip_holidays: bool = True,
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

    _pyr_on = pyr_add_R > 0 and pyr_max >= 1

    pnl_list, trade_log = [], []
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

                # ══════════════════════════════════════════════════════════════
                # BRANCH A — pyr_add_R<=0: ORIGINAL ORB_3_6 loop body, VERBATIM.
                # ══════════════════════════════════════════════════════════════
                if not _pyr_on:
                    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                    ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                    be_armed = False; be_lvl = np.nan
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
                            if vpace_filter > 0 and _pace_ref is not None and sv is not None and k > 0:
                                _si2 = _pace_ord.get(i)
                                if _si2 is not None and k < _pace_ref.shape[1]:
                                    _rf = _pace_ref[_si2, k]
                                    if _rf == _rf and _rf > 0 and sv[:k].mean() < vpace_filter * _rf:
                                        continue
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
                            if be_armed:
                                stop = max(stop, entry) if pos > 0 else min(stop, entry)
                            if trail_bars > 0 and (partial_exit_R == 0 or p_done):
                                ts = max(ek, k - trail_bars)
                                if pos > 0:
                                    trail_low = sl[ts:k].min() if k > ts else sl[ek]
                                    stop = max(stop, trail_low)
                                else:
                                    trail_high = sh[ts:k].max() if k > ts else sh[ek]
                                    stop = min(stop, trail_high)

                            if pos > 0:
                                if sl[k] <= stop:
                                    ex_px = so[k] if so[k] < stop else stop
                                    raw   = ex_px - entry
                                    pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                    pnl_list.append(pnl)
                                    if return_trades:
                                        trade_log.append((i + ek, i + k, pnl, 1, entry, 1, pnl, ()))
                                    pos = 0; break
                                if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                                    be_armed = True
                                if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                    p_pnl = ptgt - entry; p_done = True; continue
                                if target_R > 0 and sh[k] >= tgt:
                                    raw = tgt - entry
                                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                    pnl_list.append(pnl)
                                    if return_trades:
                                        trade_log.append((i + ek, i + k, pnl, 1, entry, 1, pnl, ()))
                                    pos = 0; break
                            else:
                                if sh[k] >= stop:
                                    ex_px = so[k] if so[k] > stop else stop
                                    raw   = entry - ex_px
                                    pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                    pnl_list.append(pnl)
                                    if return_trades:
                                        trade_log.append((i + ek, i + k, pnl, -1, entry, 1, pnl, ()))
                                    pos = 0; break
                                if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                                    be_armed = True
                                if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                    p_pnl = entry - ptgt; p_done = True; continue
                                if target_R > 0 and sl[k] <= tgt:
                                    raw = entry - tgt
                                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                    pnl_list.append(pnl)
                                    if return_trades:
                                        trade_log.append((i + ek, i + k, pnl, -1, entry, 1, pnl, ()))
                                    pos = 0; break
                    if pos != 0:                                        # EOD flat
                        raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                        pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                        pnl_list.append(pnl)
                        if return_trades:
                            trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry, 1, pnl, ()))

                # ══════════════════════════════════════════════════════════════
                # BRANCH B — pyramiding ON. Unit 1 behaves exactly as branch A;
                # 1..pyr_max extra units are added into the working trade.
                # ══════════════════════════════════════════════════════════════
                else:
                    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                    ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                    be_armed = False; be_lvl = np.nan
                    entered = False; dirn = 0
                    u0_closed = False; u0_pnl = None; u0_exit_k = -1
                    adds_done = 0; extra = []   # [{entry,stop,own,closed,pnl,exit_k}]

                    for k in range(or_bars, m):
                        if not entered:
                            if close_confirm:
                                up = sc[k] >= up_lvl
                                dn = sc[k] <= dn_lvl
                            else:
                                up = sh[k] >= up_lvl
                                dn = sl[k] <= dn_lvl
                            if not (up or dn):
                                continue
                            if vpace_filter > 0 and _pace_ref is not None and sv is not None and k > 0:
                                _si2 = _pace_ord.get(i)
                                if _si2 is not None and k < _pace_ref.shape[1]:
                                    _rf = _pace_ref[_si2, k]
                                    if _rf == _rf and _rf > 0 and sv[:k].mean() < vpace_filter * _rf:
                                        continue
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
                                pos = 1; dirn = 1; ek = k; entered = True
                                p_done = False; p_pnl = 0.0; be_armed = False; continue
                            elif short_ok and dn:
                                entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                                risk  = stop_frac * rng
                                stop  = entry + risk
                                tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                                ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                                be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                                pos = -1; dirn = -1; ek = k; entered = True
                                p_done = False; p_pnl = 0.0; be_armed = False; continue
                            continue

                        # ── unit 1 management (identical mechanics to branch A) ──
                        if pos != 0:
                            if be_armed:
                                stop = max(stop, entry) if pos > 0 else min(stop, entry)
                            if trail_bars > 0 and (partial_exit_R == 0 or p_done):
                                ts = max(ek, k - trail_bars)
                                if pos > 0:
                                    trail_low = sl[ts:k].min() if k > ts else sl[ek]
                                    stop = max(stop, trail_low)
                                else:
                                    trail_high = sh[ts:k].max() if k > ts else sh[ek]
                                    stop = min(stop, trail_high)

                            if pos > 0:
                                if sl[k] <= stop:
                                    ex_px = so[k] if so[k] < stop else stop
                                    raw   = ex_px - entry
                                    u0_pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                    u0_exit_k = k; pos = 0; u0_closed = True
                                else:
                                    if be_after_R > 0 and not be_armed and sc[k] >= be_lvl:
                                        be_armed = True
                                    if not p_done and partial_exit_R > 0 and sh[k] >= ptgt:
                                        p_pnl = ptgt - entry; p_done = True
                                    elif target_R > 0 and sh[k] >= tgt:
                                        raw = tgt - entry
                                        u0_pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                        u0_exit_k = k; pos = 0; u0_closed = True
                            else:
                                if sh[k] >= stop:
                                    ex_px = so[k] if so[k] > stop else stop
                                    raw   = entry - ex_px
                                    u0_pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                    u0_exit_k = k; pos = 0; u0_closed = True
                                else:
                                    if be_after_R > 0 and not be_armed and sc[k] <= be_lvl:
                                        be_armed = True
                                    if not p_done and partial_exit_R > 0 and sl[k] <= ptgt:
                                        p_pnl = entry - ptgt; p_done = True
                                    elif target_R > 0 and sl[k] <= tgt:
                                        raw = entry - tgt
                                        u0_pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                        u0_exit_k = k; pos = 0; u0_closed = True

                        # ── pyramid add check — trade still working (pos!=0) ────
                        if pos != 0 and adds_done < pyr_max:
                            for add_idx in range(adds_done + 1, pyr_max + 1):
                                if add_idx != adds_done + 1:
                                    break
                                if dirn > 0:
                                    lvl = entry + add_idx * pyr_add_R * risk
                                    trig = sc[k] >= lvl
                                else:
                                    lvl = entry - add_idx * pyr_add_R * risk
                                    trig = sc[k] <= lvl
                                if trig:
                                    add_px = sc[k]
                                    eff_frac = pyr_stop_frac if pyr_stop_frac > 0 else stop_frac
                                    if pyr_stop == "shared":
                                        a_stop = stop
                                    else:
                                        a_stop = (add_px - eff_frac * rng) if dirn > 0 else (add_px + eff_frac * rng)
                                    extra.append({"entry": add_px, "stop": a_stop,
                                                  "own": pyr_stop == "own",
                                                  "closed": False, "pnl": None, "exit_k": None})
                                    adds_done += 1

                        # ── manage all open extra units ─────────────────────────
                        for u in extra:
                            if u["closed"]:
                                continue
                            u_stop = u["stop"] if u["own"] else stop
                            if dirn > 0:
                                if sl[k] <= u_stop:
                                    ex_px = so[k] if so[k] < u_stop else u_stop
                                    u["pnl"] = ex_px - u["entry"]; u["closed"] = True; u["exit_k"] = k
                                    continue
                                if target_R > 0 and sh[k] >= tgt:
                                    u["pnl"] = tgt - u["entry"]; u["closed"] = True; u["exit_k"] = k
                            else:
                                if sh[k] >= u_stop:
                                    ex_px = so[k] if so[k] > u_stop else u_stop
                                    u["pnl"] = u["entry"] - ex_px; u["closed"] = True; u["exit_k"] = k
                                    continue
                                if target_R > 0 and sl[k] <= tgt:
                                    u["pnl"] = u["entry"] - tgt; u["closed"] = True; u["exit_k"] = k

                        if u0_closed and all(u["closed"] for u in extra):
                            break

                    if entered and not (u0_closed and all(u["closed"] for u in extra)):
                        # ran out of bars this session → EOD flat everything still open
                        if not u0_closed:
                            raw = (sc[-1] - entry) if dirn > 0 else (entry - sc[-1])
                            u0_pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                            u0_exit_k = m - 1; u0_closed = True
                        for u in extra:
                            if not u["closed"]:
                                u["pnl"] = (sc[-1] - u["entry"]) if dirn > 0 else (u["entry"] - sc[-1])
                                u["closed"] = True; u["exit_k"] = m - 1

                    if entered:
                        add_pnls = tuple(u["pnl"] for u in extra)
                        total_pnl = u0_pnl + sum(add_pnls)
                        n_units = 1 + len(extra)
                        exit_k = max([u0_exit_k] + [u["exit_k"] for u in extra]) if extra else u0_exit_k
                        pnl_list.append(total_pnl)
                        if return_trades:
                            trade_log.append((i + ek, i + exit_k, total_pnl, dirn, entry,
                                              n_units, total_pnl / n_units, add_pnls))
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
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test: (1) pyr_add_R=0 must be BIT-IDENTICAL to ORB_3_6.py on the #314
# crown params; (2) pyr_add_R>0 must actually change results and add units.
# Run:  python augur_strategies/ORB_3_6_PYR.py
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
                 partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
                 breakout_buf=0.25, stop_frac=2.5, target_R=5.0, be_after_R=0.5,
                 atr_filter=0.75, vpace_filter=0.8)
    args = (df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    kw = dict(volumes=df["volume"].values, day_id=df["day_id"].values, return_trades=True)

    r0 = base.run_backtest(*args, **kw, **CROWN)
    r1 = run_backtest(*args, **kw, **CROWN, pyr_add_R=0.0)
    same = (r0["num_trades"] == r1["num_trades"]
            and abs(r0["total_pnl"] - r1["total_pnl"]) < 1e-9)
    print("pyr=0 parity vs ORB_3_6: %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if same else "FAIL", r0["num_trades"], r1["num_trades"],
        r0["total_pnl"], r1["total_pnl"]))

    r2 = run_backtest(*args, **kw, **CROWN, pyr_add_R=1.0, pyr_stop="shared", pyr_max=1)
    n_adds = sum(len(t[7]) for t in r2["trades"])
    print("pyr=1.0 shared changes results: %s  (pnl %.1f -> %.1f, n_trades %d -> %d, adds fired %d)" % (
        "PASS" if abs(r2["total_pnl"] - r1["total_pnl"]) > 1e-9 else "FAIL",
        r1["total_pnl"], r2["total_pnl"], r1["num_trades"], r2["num_trades"], n_adds))

    r3 = run_backtest(*args, **kw, **CROWN, pyr_add_R=1.0, pyr_stop="own",
                       pyr_stop_frac=2.5, pyr_max=2)
    n_adds3 = sum(len(t[7]) for t in r3["trades"])
    print("pyr=1.0 own/max2 runs: n_trades %d, total adds fired %d, pnl %.1f" % (
        r3["num_trades"], n_adds3, r3["total_pnl"]))

    sys.exit(0 if same else 1)
