"""
OPENING RANGE BREAKOUT — 2-LOT ENSEMBLE + LUNCH-HOUR TRAIL TIGHTENING (X13).

Byte-for-byte the ORB_3_0_ENS.py 2-lot book (lot A ride+BE / lot B N-bar trail,
booked as the 50/50 blend) with ONE addition: `lunch_trail` (int, default 0 = off).
When lunch_trail > 0, lot B's trail lookback becomes lunch_trail bars (instead of
trail_bars) for bars whose ET wall-clock time is 12:00-13:59 — the trail TIGHTENS
over the lunch chop, then loosens back to trail_bars after 14:00. The hypothesis:
lunch-hour retracements are mean-reversion noise, so giving back less of the move
there should cut drawdown without capping the afternoon trend leg.

Needs bar timestamps: the signature declares `index=None`, so engine.run_backtest
hands over arrays['index']. That index may be epoch SECONDS or a tz-aware
US/Eastern DatetimeIndex depending on the loader path — both are normalized to ET
hour robustly below. lunch_trail=0 (or index missing) = EXACT ORB_3_0_ENS
behavior (anchor: target_R 4.5 / trail_bars 5 full = $465,109 / DD $17,439 /
3951 trades). PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.0 · 2-lot ensemble + lunch trail tighten'
DESCRIPTION   = ("The ORB_3_0_ENS 2-lot book (ride+BE / trail, 50/50 blend) with one extra "
                 "knob: lunch_trail — lot B's trail lookback drops to this many bars during "
                 "12:00-13:59 ET, then reverts to trail_bars. 0 = off (= exact ENS).")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_0_ENS.py"

DEFAULT_PARAMS = {
    "or_bars":      {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":   {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction"},
    "stop_frac":    {"default": 1.75, "min": 1.75, "max": 1.75, "step": 0.25, "type": "float", "label": "Stop (× range width)"},
    "vol_filter":   {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter"},
    "atr_filter":   {"default": 0.1,  "min": 0.1,  "max": 0.1,  "step": 0.1,  "type": "float", "label": "Vol-regime filter"},
    "breakout_buf": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer"},
    "be_after_R":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Lot A breakeven (× risk) — PINNED"},
    "target_R": {
        "default": 4.5, "min": 3.0, "max": 6.0, "step": 0.5, "type": "float",
        "label": "Lot A target (× risk)",
        "tooltip": "Take-profit for the RIDE lot at this multiple of initial risk. 4.5R validated (#137).",
    },
    "trail_bars": {
        "default": 5, "min": 2, "max": 12, "step": 1, "type": "int",
        "label": "Lot B trail (bars)",
        "tooltip": "Trail the SECOND lot on the rolling N-bar low (long) / high (short) from entry. "
                   "5 validated (#125 / §4.16); 3-8 all in the plateau.",
    },
    "lunch_trail": {
        "default": 0, "min": 0, "max": 5, "step": 1, "type": "int",
        "label": "Lunch trail (bars, 0=off)",
        "tooltip": "When > 0, lot B's trail lookback becomes THIS many bars for bars stamped "
                   "12:00-13:59 ET (tighter over lunch), reverting to trail_bars after. "
                   "0 = off (= exact ORB_3_0_ENS behavior).",
    },
}

PARAM_GRID_PRESETS = {
    "Lunch-trail sweep (ENS 4.5/5 locked)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "be_after_R": [1.0],
        "target_R": [4.5], "trail_bars": [5], "lunch_trail": [0, 2, 3, 4],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 1.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0, target_R: float = 4.5,
    atr_filter: float = 0.1,
    be_after_R: float = 1.0, trail_bars: int = 5,
    lunch_trail: int = 0,
    flat_eod: bool = True, skip_holidays: bool = True,
    day_id=None, index=None,
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

    # ── Lunch mask (X13): per-bar True when the bar's ET time is 12:00-13:59.
    #    arrays['index'] may be epoch SECONDS or a tz-aware (US/Eastern) DatetimeIndex
    #    depending on the loader path — normalize robustly, never trust one shape.
    #    Naive datetimes are assumed already ET wall-clock. Any failure -> mask None
    #    -> feature inert (lunch_trail behaves as 0 = exact ENS).
    _lunch = None
    if lunch_trail and int(lunch_trail) > 0 and index is not None:
        try:
            import pandas as pd
            if str(getattr(index, "dtype", "")).startswith("datetime") or hasattr(index, "tz"):
                _di = pd.DatetimeIndex(index)
            else:
                _nv = np.asarray(index)
                if np.issubdtype(_nv.dtype, np.number):
                    _di = pd.to_datetime(_nv.astype(np.int64), unit="s", utc=True)
                else:
                    _di = pd.DatetimeIndex(pd.to_datetime(_nv))
            if _di.tz is not None:
                _di = _di.tz_convert("US/Eastern")
            _hh = np.asarray(_di.hour)
            if len(_hh) == n:
                _lunch = (_hh >= 12) & (_hh <= 13)
        except Exception:
            _lunch = None

    allow_long  = trade_mode in ("Both", "First-candle dir", "Long Only")
    allow_short = trade_mode in ("Both", "First-candle dir", "Short Only")

    _sess_bounds = []
    _a = 0
    while _a < n:
        _b = _a
        while _b < n and did[_b] == did[_a]:
            _b += 1
        _sess_bounds.append((_a, _b)); _a = _b
    _holiday_start = set()
    if skip_holidays and len(_sess_bounds) > 4:
        _lens = np.array([b - a for a, b in _sess_bounds], float)
        _half = 0.70 * np.median(_lens)
        for (a, b) in _sess_bounds:
            if (b - a) < _half:
                _holiday_start.add(a)
    _allow_start = {}
    if atr_filter > 0 and len(_sess_bounds) > 6:
        _srng = np.array([h[a:b].max() - l[a:b].min() for a, b in _sess_bounds], float)
        for _si, (a, b) in enumerate(_sess_bounds):
            if _si < 6:
                continue
            _recent = _srng[max(0, _si - 5):_si].mean()
            _ref    = np.median(_srng[max(0, _si - 60):_si])
            if _ref > 0 and _recent < atr_filter * _ref:
                _allow_start[a] = False

    pnl_list, trade_log = [], []
    i = 0
    while i < n:
        if _stop_event is not None and _stop_event.is_set():
            break
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        m = j - i
        if i in _holiday_start:
            i = j; continue
        if _allow_start.get(i, True) is False:
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

                pos = 0; entry = 0.0; ek = -1; risk = 0.0
                # per-lot state: stops, alive flags, banked PnLs, exit bars
                ast = bst = 0.0; a_on = b_on = False
                a_pnl = b_pnl = 0.0; a_ex = b_ex = -1
                tgt = 0.0; _mfe = 0.0; _be = False
                for k in range(or_bars, m):
                    if pos == 0:
                        up = sh[k] >= up_lvl
                        dn = sl[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        if long_ok and up:
                            entry = max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl
                            pos = 1
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            pos = -1
                        else:
                            continue
                        ek = k; risk = stop_frac * rng
                        ast = entry - risk if pos > 0 else entry + risk
                        bst = ast
                        tgt = (entry + target_R * risk) if pos > 0 else (entry - target_R * risk)
                        if target_R <= 0:
                            tgt = np.inf if pos > 0 else -np.inf
                        a_on = b_on = True; a_pnl = b_pnl = 0.0; a_ex = b_ex = -1
                        _mfe = 0.0; _be = False
                        continue
                    # ── manage both lots (identical bar semantics to the single-lot files) ──
                    if pos > 0:
                        # Lot B: update trail from PRIOR bars (no look-ahead), then stop check.
                        # X13: lookback = lunch_trail during 12:00-13:59 ET, else trail_bars.
                        if b_on and trail_bars > 0:
                            _tb = lunch_trail if (_lunch is not None and _lunch[i + k]) else trail_bars
                            ts = max(ek, k - _tb)
                            trail_low = sl[ts:k].min() if k > ts else sl[ek]
                            bst = max(bst, trail_low)
                        if a_on and sl[k] <= ast:
                            ex = so[k] if so[k] < ast else ast
                            a_pnl = ex - entry; a_on = False; a_ex = k
                        if b_on and sl[k] <= bst:
                            ex = so[k] if so[k] < bst else bst
                            b_pnl = ex - entry; b_on = False; b_ex = k
                        if a_on and target_R > 0 and sh[k] >= tgt:
                            a_pnl = tgt - entry; a_on = False; a_ex = k
                        if a_on and be_after_R > 0 and not _be:
                            _mfe = max(_mfe, sh[k] - entry)
                            if _mfe >= be_after_R * risk:
                                _be = True; ast = entry
                    else:
                        if b_on and trail_bars > 0:
                            _tb = lunch_trail if (_lunch is not None and _lunch[i + k]) else trail_bars
                            ts = max(ek, k - _tb)
                            trail_high = sh[ts:k].max() if k > ts else sh[ek]
                            bst = min(bst, trail_high)
                        if a_on and sh[k] >= ast:
                            ex = so[k] if so[k] > ast else ast
                            a_pnl = entry - ex; a_on = False; a_ex = k
                        if b_on and sh[k] >= bst:
                            ex = so[k] if so[k] > bst else bst
                            b_pnl = entry - ex; b_on = False; b_ex = k
                        if a_on and target_R > 0 and sl[k] <= tgt:
                            a_pnl = entry - tgt; a_on = False; a_ex = k
                        if a_on and be_after_R > 0 and not _be:
                            _mfe = max(_mfe, entry - sl[k])
                            if _mfe >= be_after_R * risk:
                                _be = True; ast = entry
                    if not a_on and not b_on:
                        break
                if pos != 0:
                    eod = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
                    if a_on: a_pnl = eod; a_ex = j - 1 - i
                    if b_on: b_pnl = eod; b_ex = j - 1 - i
                    pnl = 0.5 * (a_pnl + b_pnl)
                    pnl_list.append(pnl)
                    if return_trades:
                        trade_log.append((i + ek, i + max(a_ex, b_ex), pnl, 1 if pos > 0 else -1, entry))
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
