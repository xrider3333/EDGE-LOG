"""
OPENING RANGE BREAKOUT 3.1 — low-DOF base + a TWO-LOT scale-out.

This is ORB 3.0's clean, low-degrees-of-freedom base with EXACTLY TWO levers added
back from v2 — the only two needed to run a 2-contract "book one, ride one" plan:

    • partial_exit_R  → exit the FIRST lot (half) at this R-multiple of initial risk.
                        Books a win frequently → lifts realized win rate, smooths equity.
                        (the "take-profit early" contract — 119's DNA.)
    • trail_bars      → after the partial fires, TRAIL the runner (second lot) on the
                        rolling N-bar low (long) / high (short); stop only moves in the
                        favorable direction, ride to trail-out / target_R / EOD flat.
                        (the "trailing TP on the additional contract" — 121's DNA, but
                        de-artifacted: no sub-0.5 stop, no overnight gap risk.)

DELIBERATELY NOT re-added from v2: the ATR-normalized stop (use_atr_stop / stop_atr_mult
/ atr_period). Keeping only the range-frac stop holds this at 8 knobs — barely above 3.0
— so a walk-forward + lockbox can test the scale-out HYPOTHESIS in isolation instead of
wandering an over-parameterized surface. The whole point of forking 3.0 (not just
re-opening 2.0) is to sweep ONLY the two runner levers against a fixed, validated base.

Accounting mirrors v2 exactly: a scaled-out session books ONE trade whose PnL is the
average of the two half-legs (partial_pnl*0.5 + runner_pnl*0.5), so win_rate / num_trades
stay comparable to the single-lot 3.0 runs and the existing 2.0 history.

Knobs (7 active + optional target): or_bars · trade_mode · stop_frac · vol_filter ·
breakout_buf · partial_exit_R · trail_bars (+ optional target_R, atr_filter, flat_eod,
skip_holidays). PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.5 · low-DOF legal (6 knobs)'
DESCRIPTION   = ("ORB 3.0's clean low-DOF base with the two runner levers added back: "
                 "book the first lot at partial_exit_R, trail the second lot on an N-bar "
                 "low/high. Built to walk-forward the scale-out in isolation against a "
                 "fixed base (no ATR stop, no sub-0.5 stop). NQ 5m default; transfers to ES.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Lineage: forked from the locked-down deployable 3.0, which itself forked v2. The
# validation roadmap inherits 3.0's ticked steps (flagged "inherited — re-confirm").
_AUGUR_PARENT = "ORB_3_5.py"

DEFAULT_PARAMS = {
    "or_bars":       {"default": 1,    "min": 1,   "max": 3,   "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":    {"default": "Both", "type": "str", "options": ["Both", "First-candle dir", "Short Only"], "label": "Direction"},
    "stop_frac":     {"default": 0.75, "min": 0.5, "max": 1.25,"step": 0.25, "type": "float", "label": "Stop (x range width)"},
    "breakout_buf":  {"default": 0.0,  "min": 0.0, "max": 0.0, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED"},
    "close_confirm": {"default": False, "type": "bool", "options": [False], "label": "Confirm at bar close - PINNED off (touch is the edge)"},
    "partial_exit_R":{"default": 0.0,  "min": 0.0, "max": 0.0, "step": 0.5,  "type": "float", "label": "Partial exit - PINNED off"},
    "trail_bars":    {"default": 5,    "min": 0,   "max": 8,   "step": 1,    "type": "int",   "label": "Trailing stop (bars)"},
    "target_R":      {"default": 0.0,  "min": 0.0, "max": 0.0, "step": 0.5,  "type": "float", "label": "Target - PINNED off (ride to close)"},
    "atr_filter":    {"default": 0.0,  "min": 0.0, "max": 0.0, "step": 0.1,  "type": "float", "label": "Vol-regime filter - PINNED off"},
    "vpace_filter":  {"default": 0.0,  "min": 0.0, "max": 1.2, "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only)"},
    "gap_min":       {"default": 0.0,  "min": 0.0, "max": 0.0, "step": 0.05, "type": "float", "label": "Gap gate - PINNED off"},
    "orw_min":       {"default": 0.0,  "min": 0.0, "max": 0.0, "step": 0.1,  "type": "float", "label": "OR-width gate - PINNED off"},
    "entry_cutoff":  {"default": 0,    "min": 0,   "max": 12,  "step": 2,    "type": "int",   "label": "Entry window (bars after OR, 0 = all day)"},
    "flat_eod":      {"default": True,  "type": "bool", "options": [True],  "label": "Flat at the close - PINNED on"},
    "skip_holidays": {"default": False, "type": "bool", "options": [False], "label": "Skip holidays - PINNED off"},
}

# ─────────────────────────────────────────────────────────────────────────────
# v-SALVAGE FIX 2 (2026-08-11): the presets below carried "vol_filter" pinned at
#   1.25 (and swept 1.0/1.25/1.5 in Long) even though the SAME commit removed it
#   from DEFAULT_PARAMS. Removing a knob from DEFAULT_PARAMS only hides it from
#   the Builder UI — expand_grid() builds the parameter combos straight from the
#   preset dict below, so every grid run of this file was still executing the
#   look-ahead filter this file exists to REPLACE, and never once tested the
#   legal vpace_filter (which was absent from all four presets). That is how run
#   209 came back crowning "vol_filter 1.0 / vpace 0.0". Fixed: vol_filter is out
#   of every preset, vpace_filter is in. vol_filter survives ONLY as a function
#   argument (default 0.0) so ORB_3_1 parity can still be reproduced by hand.
# ─────────────────────────────────────────────────────────────────────────────
PARAM_GRID_PRESETS = {
    # ── THE hypothesis test: fix a clean validated base (119-flavour, stop 0.75,
    #    legal volume-pace gate, ride-to-close) and sweep ONLY the two runner
    #    levers. 6×4 = 24 combos. This is the lockbox-friendly, minimal-DOF
    #    walk-forward. The partial=0 / trail=0 corner IS the single-lot control.
    "Short  (scale-out core — 2 knobs only)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75],
        "vpace_filter": [0.8], "breakout_buf": [0.0], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True],
        "partial_exit_R": [0.0, 1.0, 1.5, 2.0, 2.5, 3.0],
        "trail_bars":     [0, 3, 5, 8],
    },
    # ── Adds a little base breadth (OR length, stop, v-pace) around the scale-out
    #    sweep for an XL / auto search. 2×2×2 base × 4×4 exits = 128 combos.
    "Medium (base + scale-out)": {
        "or_bars": [1, 3], "trade_mode": ["Both"], "stop_frac": [0.5, 0.75],
        "vpace_filter": [0.8, 1.0], "breakout_buf": [0.0], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True], "close_confirm": [False, True],
        "partial_exit_R": [0.0, 1.5, 2.0, 3.0],
        "trail_bars":     [0, 3, 5, 8],
    },
    # ── Full sweep incl. a runner cap (target_R) and vol-regime filter. For XXL /
    #    auto only — this is broad enough to overfit, so trust it ONLY through a
    #    walk-forward + lockbox, never a single in-sample best. vpace 0.0 is left
    #    in here on purpose as the gate-OFF control arm.
    "Long   (full — cap + regime)": {
        "or_bars": [1, 3, 6], "trade_mode": ["Both", "First-candle dir"],
        "stop_frac": [0.5, 0.75, 1.0], "vpace_filter": [0.0, 0.8, 1.1],
        "breakout_buf": [0.0], "atr_filter": [0.0, 0.8],
        "target_R": [0.0, 3.0, 4.5], "flat_eod": [True], "close_confirm": [False, True],
        "partial_exit_R": [0.0, 1.5, 2.0, 3.0],
        "trail_bars":     [0, 3, 5, 8],
    },
    # ── Holds the best-guess scale-out base fixed and sweeps ONLY partial_exit_R
    #    so you can read the lot-1 take-profit level in isolation (trail fixed at 5).
    "Partial (lot-1 TP scan)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [0.75],
        "vpace_filter": [0.8], "breakout_buf": [0.0], "atr_filter": [0.0],
        "target_R": [0.0], "flat_eod": [True], "trail_bars": [5],
        "partial_exit_R": [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 0.75, vol_filter: float = 0.0, vpace_filter: float = 0.0,
    gap_min: float = 0.0, orw_min: float = 0.0, entry_cutoff: int = 0,
    breakout_buf: float = 0.0, close_confirm: bool = False,
    partial_exit_R: float = 0.0, trail_bars: int = 0,
    atr_filter: float = 0.0, target_R: float = 0.0,
    flat_eod: bool = True, skip_holidays: bool = False,
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

    # ── V-PACE filter (vpace_filter > 0): the LEGAL replacement for vol_filter. ───────
    #   The illegal filter read the FILL BAR's finished volume. This reads only the bars
    #   that closed BEFORE it: the session's volume pace so far, against the same-length
    #   prefix averaged over the prior 20 sessions. Every input exists at the moment a
    #   resting stop could fill, so the rule is implementable exactly as backtested.
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

    # -- GAP gate (gap_min > 0): |overnight gap| in trailing-ATR units. The session open
    #    and every prior close are known at 09:30, before any bar of today prints. -----
    _gap_ok = {}
    if gap_min > 0 and len(_sess_bounds) > 21:
        _scl2 = np.array([c[b - 1] for a, b in _sess_bounds], float)
        _srg2 = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 21:
                continue
            _atr2 = _srg2[_si - 20:_si].mean()
            _gp = abs(o[a] - _scl2[_si - 1]) / _atr2 if _atr2 > 0 else 0.0
            if _gp < gap_min:
                _gap_ok[a] = False

    # -- OR-WIDTH gate (orw_min > 0): today's opening-range width as a percentile of the
    #    prior 20 sessions' OR widths (same or_bars). Known the moment the OR completes;
    #    entries only start on the bar AFTER the OR, so nothing reads the fill bar. -----
    _orw_ok = {}
    if orw_min > 0 and len(_sess_bounds) > 21 and or_bars >= 1:
        _orw = np.array([h[a:min(a + or_bars, b)].max() - l[a:min(a + or_bars, b)].min()
                         for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 21:
                continue
            _pct = float((_orw[_si - 20:_si] < _orw[_si]).mean())
            if _pct < orw_min:
                _orw_ok[a] = False

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
        if _gap_ok.get(i, True) is False:        # overnight gap too small (gap_min)
            i = j; continue
        if _orw_ok.get(i, True) is False:        # opening range too narrow today (orw_min)
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
                for k in range(or_bars, m):
                    if pos == 0:
                        # entry window (entry_cutoff > 0): no NEW entries after this many
                        #   bars past the OR - classic ORB practice, pure clock, legal.
                        if entry_cutoff > 0 and k > or_bars - 1 + entry_cutoff:
                            continue
                        # Entry trigger: TOUCH (high/low pierces the edge → fill at the edge,
                        # models a resting stop) or CLOSE-CONFIRMED (bar CLOSES beyond the edge
                        # → fill at that close, skipping false wicks that pierce then close back
                        # inside). Mirrors ORB 3.0's close_confirm semantics exactly.
                        if close_confirm:
                            up = sc[k] >= up_lvl
                            dn = sc[k] <= dn_lvl
                        else:
                            up = sh[k] >= up_lvl
                            dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        # LEGAL v-pace gate — is the session trading heavy so far? Every
                        #   input closed BEFORE this bar; the fill bar is never read.
                        if vpace_filter > 0 and _pace_ref is not None and sv is not None and k > 0:
                            _si2 = _pace_ord.get(i)
                            if _si2 is not None and k < _pace_ref.shape[1]:
                                _rf = _pace_ref[_si2, k]
                                if _rf == _rf and _rf > 0 and sv[:k].mean() < vpace_filter * _rf:
                                    continue
                        # legacy look-ahead filter — OFF by default and pinned off in the
                        #   search space. Kept only so ORB_3_1 parity can be reproduced.
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
                            pos = 1; ek = k; p_done = False; p_pnl = 0.0; continue
                        elif short_ok and dn:
                            entry = sc[k] if close_confirm else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                            risk  = stop_frac * rng
                            stop  = entry + risk
                            tgt   = entry - target_R * risk if target_R > 0 else -np.inf
                            ptgt  = entry - partial_exit_R * risk if partial_exit_R > 0 else -np.inf
                            pos = -1; ek = k; p_done = False; p_pnl = 0.0; continue
                    else:
                        # ── Trailing stop: active if trail_bars>0 AND (no partial
                        #    planned OR the partial has already fired). Uses PRIOR
                        #    bars' extremes (sl/sh[ts:k], excluding k) → no look-ahead.
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
                                # Gap-through realism: if the bar OPENED below the stop,
                                # a stop order fills at the open, not the stop price.
                                ex_px = so[k] if so[k] < stop else stop
                                raw   = ex_px - entry
                                pnl   = (p_pnl * 0.5 + raw * 0.5) if p_done else raw
                                pnl_list.append(pnl)
                                if return_trades: trade_log.append((i + ek, i + k, pnl, 1, entry))
                                pos = 0; break
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
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — proves the two runner levers actually change results, using the
# clean NQ 5m RTH master.   Run:  python augur_strategies/ORB_3_1.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    import pandas as pd

    ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOADS = os.path.join(ROOT, "augur_uploads")
    MASTER  = os.path.join(UPLOADS, "NOADJ_NQ_5m_RTH.csv")   # already RTH-filtered
    MULT    = 20                                             # NQ $/point

    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df  = pd.read_csv(MASTER)
    dt  = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df["day_id"] = pd.factorize(dt.dt.date)[0]
    df = df.sort_values("time").reset_index(drop=True)
    print("NQ 5m RTH master: %d bars, %d sessions" % (len(df), df["day_id"].nunique()))

    # Base = 119-flavour clean base (stop 0.75, vol 1.25, ride-to-close). We vary
    # ONLY partial_exit_R / trail_bars so the deltas are attributable to the scale-out.
    base = dict(or_bars=1, trade_mode="Both", stop_frac=0.75,
                vol_filter=1.25, breakout_buf=0.0, target_R=0.0, flat_eod=True)
    configs = [
        ("single-lot control (partial=0, trail=0)  [= 3.0]", {}),
        ("trail only            (trail=5)",                   {"trail_bars": 5}),
        ("book 1.5R + trail     (partial=1.5, trail=5)",      {"partial_exit_R": 1.5, "trail_bars": 5}),
        ("book 2.0R + trail     (partial=2.0, trail=5)",      {"partial_exit_R": 2.0, "trail_bars": 5}),
        ("book 2.0R + tight tr  (partial=2.0, trail=3)",      {"partial_exit_R": 2.0, "trail_bars": 3}),
        ("book 2.0R, hold EOD   (partial=2.0, trail=0)",      {"partial_exit_R": 2.0, "trail_bars": 0}),
    ]

    print()
    print("%-52s %7s %5s %5s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD $"))
    print("-" * 100)
    for label, kw in configs:
        r = run_backtest(
            df["open"].values, df["high"].values, df["low"].values, df["close"].values,
            volumes=df["volume"].values if "volume" in df.columns else None,
            day_id=df["day_id"].values, **{**base, **kw},
        )
        if r is None:
            print("%-52s  NO TRADES" % label); continue
        print("%-52s %7d %4.0f%% %5.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(r["total_pnl"] * MULT),
            "${:,.0f}".format(r["max_drawdown"] * MULT)))
    print()
    print("Gross of fees (PNL=SHARES*(EXIT-ENTRY)); the app nets ~$5.66+0.25pt/trade.")
    print("Read: does 'book + trail' lift WR / cut DD vs the single-lot control,")
    print("      and at what cost to net $? Trust it only through WF + lockbox.")
