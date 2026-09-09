"""
ORB 3.6 BUF - adaptive breakout buffer / multi-bar confirmation (round 11, 2026-09-09).

The #314 crown requires price to CLOSE beyond the opening-range edge by a buffer of
breakout_buf x range width (0.25). That buffer is the ENTRY threshold, and it is tied to
the SAME one number - the opening-range width - that also sets the stop and the target.
Two things have never been tested:

  (a) BUFFER YARDSTICK. Should the entry buffer be a multiple of the range width, or of
      a volatility yardstick that moves independently session to session (a session-level
      "ATR" proxy)? ORB_3_6 has no true per-bar ATR series; the closest thing it already
      computes is the trailing-60-session MEDIAN session range used by atr_filter's vol-
      regime gate. This fork reuses that exact quantity (computed identically - strictly
      from sessions BEFORE the current one, warm-up >= 6 sessions) as the ATR yardstick.

  (b) CONFIRMATION DEPTH. Instead of (or in addition to) a bigger buffer, require MORE
      THAN ONE consecutive bar to close beyond the level before entering. Entry still
      fills at the close of the LAST confirming bar - no new look-ahead.

Four new knobs, all default OFF/neutral so this file is asserted BIT-IDENTICAL to
ORB_3_6 on the crown params (smoke test at the bottom):

  buf_mode             "range" (default, = breakout_buf x range width, the crown exactly)
                        | "atr" (buf_atr_mult x the trailing session-range ATR proxy)
                        | "hybrid" (the LARGER of the two).
  buf_atr_mult          float, default 0.0. Only used in "atr"/"hybrid" modes.
  confirm_bars          int, default 1 (= the crown - one close is already "confirmed").
                        N consecutive closes beyond the level required before entry.
                        INERT when close_confirm=False (touch entry has no "close" to
                        require consecutively; the knob is simply never read in that path).
  confirm_close_beyond  bool, default False. When True and confirm_bars > 1, each
                        confirming close must ALSO clear the PREVIOUS confirming close
                        (a monotone push through the zone, not just N closes sitting past
                        the level). INERT when close_confirm=False, same reason as above.

LIVE-LEGAL BY CONSTRUCTION: the ATR proxy for a session is fixed BEFORE that session
starts (uses only prior sessions' finished ranges); the confirmation streak only reads
bars strictly before bar k when deciding bar k, and the fill is still the close of the
bar that completes the streak - exactly the parent's existing fill rule, just possibly
a few bars later.

Everything else (stop/target/be/partial/trail/vpace/atr-regime/holiday/EOD) is ORB_3_6
byte-for-byte.
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.6 BUF · adaptive buffer + multi-bar confirm'
DESCRIPTION   = ("The #314 crown's breakout buffer, generalised two ways: (1) tie the "
                 "buffer to a session-level ATR proxy instead of - or blended with - the "
                 "opening-range width, and (2) require N consecutive confirming closes "
                 "(optionally a monotone push) instead of just a bigger buffer. All knobs "
                 "default OFF; buf_mode=range, buf_atr_mult=0, confirm_bars=1 reproduces "
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
                   "width before entering. Used directly in buf_mode=range; in "
                   "buf_mode=hybrid it is compared against the ATR-based buffer and the "
                   "larger wins. 0 = trade the touch (subject to confirm_bars).",
    },
    "close_confirm": {
        "default": True, "type": "bool",
        "label": "Close-confirmed entry (skip false wicks)",
        "tooltip": "ON (default) = only enter when a bar CLOSES beyond the edge, filling at "
                   "that close - the live-legal entry the grail hunt certified. OFF = touch "
                   "entry (models a resting stop). confirm_bars / confirm_close_beyond only "
                   "apply when this is ON; they are inert (ignored) when OFF.",
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
                   "move the stop to ENTRY from the next bar on. 0 = off.",
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
    "buf_mode": {
        "default": "range", "type": "str", "options": ["range", "atr", "hybrid"],
        "label": "Breakout buffer yardstick",
        "tooltip": "range (default) = breakout_buf x opening-range width, the crown "
                   "exactly. atr = buf_atr_mult x a trailing session-range ATR proxy "
                   "(same trailing-60-session median atr_filter already computes). "
                   "hybrid = the LARGER of the two buffers.",
    },
    "buf_atr_mult": {
        "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.1, "type": "float",
        "label": "ATR buffer multiple (buf_mode atr/hybrid only)",
        "tooltip": "Buffer = this x the trailing session-range ATR proxy. Ignored in "
                   "buf_mode=range. 0 = no ATR buffer contribution.",
    },
    "confirm_bars": {
        "default": 1, "min": 1, "max": 3, "step": 1, "type": "int",
        "label": "Confirming closes required (close_confirm only)",
        "tooltip": "Require this many CONSECUTIVE bar closes beyond the level before "
                   "entering. 1 = the crown (one close is already confirmation). Fill is "
                   "still the close of the LAST confirming bar. Inert when close_confirm "
                   "is OFF.",
    },
    "confirm_close_beyond": {
        "default": False, "type": "bool",
        "label": "Require monotone push (confirm_bars > 1 only)",
        "tooltip": "When ON and confirm_bars > 1, each confirming close must ALSO clear "
                   "the previous confirming close (a monotone push, not just N closes "
                   "sitting past the level). Inert when close_confirm is OFF or "
                   "confirm_bars is 1.",
    },
}

PARAM_GRID_PRESETS = {
    # Round-11 BUF sweep: buffer yardstick x ATR multiple x confirmation depth x monotone.
    "BUF11 (adaptive buffer / confirm sweep)": {
        "or_bars": [2], "trade_mode": ["First-candle dir"], "stop_frac": [2.5],
        "vpace_filter": [0.8], "breakout_buf": [0.25], "close_confirm": [True],
        "partial_exit_R": [0.0], "trail_bars": [0], "be_after_R": [0.5],
        "atr_filter": [0.75], "target_R": [5.0], "flat_eod": [True], "skip_holidays": [True],
        "buf_mode": ["range", "atr", "hybrid"], "buf_atr_mult": [0.0, 0.1, 0.2, 0.3, 0.5],
        "confirm_bars": [1, 2, 3], "confirm_close_beyond": [False, True],
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
    buf_mode: str = "range", buf_atr_mult: float = 0.0,
    confirm_bars: int = 1, confirm_close_beyond: bool = False,
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

    # ── Session-range series (always computed - feeds atr_filter AND buf_mode) ──
    _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float) \
        if len(_sess_bounds) else np.array([])

    # ── Vol-regime filter (atr_filter > 0): trailing-only, no look-ahead ──────
    _allow_start = {}
    if atr_filter > 0 and len(_sess_bounds) > 6:
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 6:
                continue                          # warm-up → allow
            _recent = _srng[max(0, _si - 5):_si].mean()
            _ref    = np.median(_srng[max(0, _si - 60):_si])
            if _ref > 0 and _recent < atr_filter * _ref:
                _allow_start[a] = False

    # ── ATR proxy: SAME trailing-60-session median session range atr_filter   ──
    # ── uses, computed independently of atr_filter's own on/off state so both ──
    # ── buf_mode=atr/hybrid AND the confirm-distance diagnostic can use it     ──
    # ── even when buf_mode="range" (diagnostic only, never affects the buf).   ──
    _atr_ref_by_start = {}
    if len(_sess_bounds) > 6:
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 6:
                continue
            _ref = np.median(_srng[max(0, _si - 60):_si])
            if _ref > 0:
                _atr_ref_by_start[a] = _ref

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
    # diagnostic: (confirm-close distance beyond level, in ATR units, or nan) per trade,
    # parallel to trade_log / pnl_list, exposed via out["confirm_dist_atr"].
    confirm_dist_atr = []
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
                _atr_val = _atr_ref_by_start.get(i, np.nan)
                _buf_range = breakout_buf * rng
                _buf_atr = buf_atr_mult * _atr_val if _atr_val == _atr_val else np.nan
                if buf_mode == "range":
                    buf = _buf_range
                elif buf_mode == "atr":
                    buf = _buf_atr if _buf_atr == _buf_atr else _buf_range  # fallback: warm-up
                else:  # "hybrid"
                    buf = max(_buf_range, _buf_atr) if _buf_atr == _buf_atr else _buf_range
                up_lvl = or_hi + buf
                dn_lvl = or_lo - buf
                long_ok  = allow_long  and (trade_mode != "First-candle dir" or or_dir > 0)
                short_ok = allow_short and (trade_mode != "First-candle dir" or or_dir < 0)

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk = 0.0
                ptgt = 0.0; p_done = False; p_pnl = 0.0; ek = -1
                be_armed = False; be_lvl = np.nan
                up_streak = 0; dn_streak = 0
                up_last_close = np.nan; dn_last_close = np.nan
                for k in range(or_bars, m):
                    if pos == 0:
                        if close_confirm:
                            up_close = sc[k] >= up_lvl
                            dn_close = sc[k] <= dn_lvl
                            if confirm_bars > 1:
                                # up-direction streak (monotone = each confirming close
                                # clears the PREVIOUS confirming close).
                                if up_close and (not confirm_close_beyond or up_streak == 0
                                                  or sc[k] > up_last_close):
                                    up_streak += 1
                                else:
                                    up_streak = 1 if up_close else 0
                                up_last_close = sc[k] if up_close else up_last_close
                                # down-direction streak (monotone = each confirming close
                                # is BELOW the previous confirming close).
                                if dn_close and (not confirm_close_beyond or dn_streak == 0
                                                  or sc[k] < dn_last_close):
                                    dn_streak += 1
                                else:
                                    dn_streak = 1 if dn_close else 0
                                dn_last_close = sc[k] if dn_close else dn_last_close
                                up = up_streak >= confirm_bars
                                dn = dn_streak >= confirm_bars
                            else:
                                up = up_close
                                dn = dn_close
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
                        _cdist = np.nan
                        if long_ok and up:
                            entry = sc[k] if close_confirm else (max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl)
                            risk  = stop_frac * rng
                            stop  = entry - risk
                            tgt   = entry + target_R * risk if target_R > 0 else np.inf
                            ptgt  = entry + partial_exit_R * risk if partial_exit_R > 0 else np.inf
                            be_lvl = entry + be_after_R * risk if be_after_R > 0 else np.nan
                            if close_confirm and _atr_val == _atr_val and _atr_val > 0:
                                _cdist = (sc[k] - up_lvl) / _atr_val
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False
                            confirm_dist_atr.append(_cdist); continue
                        elif short_ok and dn:
                            entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            be_lvl = entry - be_after_R * risk if be_after_R > 0 else np.nan
                            if close_confirm and _atr_val == _atr_val and _atr_val > 0:
                                _cdist = (dn_lvl - sc[k]) / _atr_val
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; be_armed = False
                            confirm_dist_atr.append(_cdist); continue
                    else:
                        # ── BREAKEVEN: armed on a PRIOR bar's close, applied here.
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
                                pos = 0; break
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop   # gap-through
                                raw   = entry - ex_px
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, -1, entry))
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
                                pos = 0; break
                if pos != 0:                                        # EOD flat
                    raw = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    pnl = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((i + ek, j - 1, pnl, 1 if pos > 0 else -1, entry))
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
        out["confirm_dist_atr"] = confirm_dist_atr
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test: (1) all-knobs-OFF must be BIT-IDENTICAL to ORB_3_6.py on the #314
# crown params; (2) a non-default config must actually change results.
# Run:  python augur_strategies/ORB_3_6_BUF.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import importlib.util as ilu
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _UP     = os.path.join(ROOT, "augur_uploads")
    if not os.path.isdir(_UP):
        _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
    MASTER  = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")
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
    r1 = run_backtest(*args, **kw, **CROWN, buf_mode="range", buf_atr_mult=0.0,
                       confirm_bars=1, confirm_close_beyond=False)
    same = (r0["num_trades"] == r1["num_trades"]
            and abs(r0["total_pnl"] - r1["total_pnl"]) < 1e-9)
    print("knobs-off parity vs ORB_3_6: %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if same else "FAIL", r0["num_trades"], r1["num_trades"],
        r0["total_pnl"], r1["total_pnl"]))

    r2 = run_backtest(*args, **kw, **CROWN, buf_mode="atr", buf_atr_mult=0.3,
                       confirm_bars=1, confirm_close_beyond=False)
    r3 = run_backtest(*args, **kw, **CROWN, buf_mode="range", buf_atr_mult=0.0,
                       confirm_bars=2, confirm_close_beyond=True)
    print("buf_mode=atr changes results: %s  (pnl %.1f -> %.1f, n %d -> %d)" % (
        "PASS" if abs(r2["total_pnl"] - r1["total_pnl"]) > 1e-9 else "FAIL",
        r1["total_pnl"], r2["total_pnl"], r1["num_trades"], r2["num_trades"]))
    print("confirm_bars=2 changes results: %s  (pnl %.1f -> %.1f, n %d -> %d)" % (
        "PASS" if abs(r3["total_pnl"] - r1["total_pnl"]) > 1e-9 else "FAIL",
        r1["total_pnl"], r3["total_pnl"], r1["num_trades"], r3["num_trades"]))
    # close_confirm=False must make confirm_bars/confirm_close_beyond INERT.
    r4 = run_backtest(*args, **kw, **dict(CROWN, close_confirm=False),
                       confirm_bars=1, confirm_close_beyond=False)
    r5 = run_backtest(*args, **kw, **dict(CROWN, close_confirm=False),
                       confirm_bars=3, confirm_close_beyond=True)
    inert = (r4["num_trades"] == r5["num_trades"]
             and abs(r4["total_pnl"] - r5["total_pnl"]) < 1e-9)
    print("confirm knobs inert when close_confirm=False: %s  (n %d vs %d, pnl %.4f vs %.4f)" % (
        "PASS" if inert else "FAIL", r4["num_trades"], r5["num_trades"],
        r4["total_pnl"], r5["total_pnl"]))

    ok = same and inert
    sys.exit(0 if ok else 1)
