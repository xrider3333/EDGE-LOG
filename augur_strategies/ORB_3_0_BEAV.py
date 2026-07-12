"""
OPENING RANGE BREAKOUT — #137 SEARCH SPACE + BREAKEVEN 1.0R (master-candidate).

Same low-DOF ORB engine as ORB_3_0 / ORB_3_0_BE, but built to be Auto-Validated as the NEW
MASTER: the #137 base search space is OPEN (or_bars, trade_mode, stop_frac, vol_filter,
atr_filter, breakout_buf, target_R) so the discovery populates the full config space (2A/2B/2C
tiles), while `be_after_R` is PINNED at 1.0 so the validated 1.0R breakeven is baked into every
config. The winner = the best base config WITH the breakeven = the deployable master, and the
config-space tiles line up with #137's report for a direct compare.

run_backtest is COPIED VERBATIM from ORB_3_0_BE.py (arm math identical), so with the winning
config it reproduces the #137+BE numbers ($574,177 full / DD -$26,763). PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.0 · 137-space search + BE 1.0R (master)'
DESCRIPTION   = ("#137's low-DOF base search space (OR / direction / stop / vol / target) with "
                 "the validated breakeven pinned at 1.0R. Auto-Validate this to discover the best "
                 "base config WITH breakeven — the master report, config space comparable to #137.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_0_BE.py"

# Base params OPEN (== ORB_3_0 low-DOF space); be_after_R PINNED 1.0 (min==max). skip_holidays/
# flat_eod stay at the run_backtest defaults (True/True) = #137's values. close_confirm is NOT a
# param of this engine, so it is intentionally absent from the search.
DEFAULT_PARAMS = {
    "or_bars":      {"default": 1,    "min": 1,    "max": 12,   "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":   {"default": "Both", "type": "str", "options": ["Both", "First-candle dir", "Long Only", "Short Only"], "label": "Direction"},
    "stop_frac":    {"default": 1.75, "min": 0.5,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Stop (× range width)"},
    "vol_filter":   {"default": 1.25, "min": 0.0,  "max": 3.0,  "step": 0.25, "type": "float", "label": "Volume filter (× session avg, 0=off)"},
    "atr_filter":   {"default": 0.1,  "min": 0.0,  "max": 1.5,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (× trailing median, 0=off)"},
    "breakout_buf": {"default": 0.0,  "min": 0.0,  "max": 0.5,  "step": 0.05, "type": "float", "label": "Breakout buffer (× range)"},
    "target_R":     {"default": 4.5,  "min": 0.0,  "max": 6.0,  "step": 0.5,  "type": "float", "label": "Target (× risk, 0=EOD only)"},
    "be_after_R": {
        "default": 1.0, "min": 1.0, "max": 1.0, "step": 0.1, "type": "float",
        "label": "Breakeven after (× risk) — PINNED",
        "tooltip": "Move the stop to ENTRY once unrealized profit reaches 1.0 × initial risk. "
                   "PINNED (validated in ORB.md §4.13-4.15 as the risk-adjusted champion). Baked "
                   "into every config so the search compares base configs on equal, BE-on footing.",
    },
}

PARAM_GRID_PRESETS = {
    "Master search (base + BE 1.0R)": {
        "or_bars": [1, 3, 6], "trade_mode": ["Both", "First-candle dir"],
        "stop_frac": [0.75, 1.0, 1.5, 1.75], "vol_filter": [1.0, 1.25, 1.5],
        "atr_filter": [0.0, 0.1], "breakout_buf": [0.0],
        "target_R": [0.0, 3.0, 4.5], "be_after_R": [1.0],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 1.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0, target_R: float = 4.5,
    atr_filter: float = 0.1,
    be_after_R: float = 1.0,
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

                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; ek = -1
                _risk = 0.0; _mfe = 0.0; _be = False
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
                            stop  = entry - stop_frac * rng
                            tgt   = entry + target_R * (entry - stop) if target_R > 0 else np.inf
                            pos = 1; ek = k; _risk = entry - stop; _mfe = 0.0; _be = False; continue
                        elif short_ok and dn:
                            entry = min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl
                            stop  = entry + stop_frac * rng
                            tgt   = entry - target_R * (stop - entry) if target_R > 0 else -np.inf
                            pos = -1; ek = k; _risk = stop - entry; _mfe = 0.0; _be = False; continue
                    else:
                        if pos > 0:
                            if sl[k] <= stop:
                                ex_px = so[k] if so[k] < stop else stop
                                pnl_list.append(ex_px - entry)
                                if return_trades: trade_log.append((i + ek, i + k, ex_px - entry, 1, entry))
                                pos = 0; break
                            if target_R > 0 and sh[k] >= tgt:
                                pnl_list.append(tgt - entry)
                                if return_trades: trade_log.append((i + ek, i + k, tgt - entry, 1, entry))
                                pos = 0; break
                            if be_after_R > 0 and not _be:
                                _mfe = max(_mfe, sh[k] - entry)
                                if _mfe >= be_after_R * _risk:
                                    _be = True; stop = entry
                        else:
                            if sh[k] >= stop:
                                ex_px = so[k] if so[k] > stop else stop
                                pnl_list.append(entry - ex_px)
                                if return_trades: trade_log.append((i + ek, i + k, entry - ex_px, -1, entry))
                                pos = 0; break
                            if target_R > 0 and sl[k] <= tgt:
                                pnl_list.append(entry - tgt)
                                if return_trades: trade_log.append((i + ek, i + k, entry - tgt, -1, entry))
                                pos = 0; break
                            if be_after_R > 0 and not _be:
                                _mfe = max(_mfe, entry - sl[k])
                                if _mfe >= be_after_R * _risk:
                                    _be = True; stop = entry
                if pos != 0:
                    pnl = (sc[-1] - entry) if pos > 0 else (entry - sc[-1])
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
