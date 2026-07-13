"""
OPENING RANGE BREAKOUT — 137-lock + ENTRY-CONFIRMATION research (item J, ORB.md §6).

The contradiction to resolve: `tools/reconcile.py` says TV's close-based model skipped 306
false-wick breaks (-$149,562 of engine losses) and netted +$30k MORE than the engine over 15y;
but ORB_3_0's `close_confirm=True` on #137's config was **-$392k** ($567k -> $175k) because it
fills at the confirming bar's CLOSE — a worse price on every REAL break. Is the false-wick skip
worth having if you don't pay the close-fill penalty? This file separates the CONFIRMATION from
the FILL with one `entry_mode` selector on the frozen #137+BE base:

    "touch"       enter the instant price TOUCHES the range edge; fill at the level
                  (resting stop order — the deploy baseline; gap-aware).
    "close"       enter when a bar CLOSES beyond the edge; fill at that close
                  (== ORB_3_0 close_confirm=True; the -$392k anchor at be=0).
    "close_open"  confirm on the close, enter at the NEXT bar's OPEN
                  (market order on confirmation — realistic, no level assumption).
    "close_level" confirm on the close, then rest a LIMIT back at the range edge;
                  fill only if price retraces to the level (TV-style level fill,
                  wick-skip kept; cost = missed runaway breaks that never retrace).

All modes share the identical exit stack (1.75xOR stop, 4.5R target, breakeven 1.0R, EOD,
gap-through realism) and the entry-bar convention (fill on bar k, manage from k+1) so deltas
are attributable to the entry mechanics alone. PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB 3.0 · 137-lock + entry-confirmation research (entry_mode)'
DESCRIPTION   = ("Run #137's champion + 1.0R breakeven with a selectable ENTRY: touch-the-level "
                 "(deploy), close-confirmed at the close (the -$392k trap), close-confirmed at "
                 "the next open, or close-confirmed with a limit back at the level (TV-style). "
                 "Research for item J — separates the wick-skip from the fill penalty.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_0_BE.py"

DEFAULT_PARAMS = {
    "or_bars":      {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars)"},
    "trade_mode":   {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction"},
    "stop_frac":    {"default": 1.75, "min": 1.75, "max": 1.75, "step": 0.25, "type": "float", "label": "Stop (× range width)"},
    "vol_filter":   {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter"},
    "atr_filter":   {"default": 0.1,  "min": 0.1,  "max": 0.1,  "step": 0.1,  "type": "float", "label": "Vol-regime filter"},
    "breakout_buf": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer"},
    "target_R":     {"default": 4.5,  "min": 4.5,  "max": 4.5,  "step": 0.5,  "type": "float", "label": "Target (× risk)"},
    "be_after_R":   {"default": 1.0,  "min": 0.0,  "max": 4.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk, 0=off)"},
    "entry_mode": {
        "default": "touch", "type": "str",
        "options": ["touch", "close", "close_open", "close_level"],
        "label": "Entry confirmation / fill",
        "tooltip": "touch = fill at the level on the first touch (deploy). close = fill at the "
                   "confirming close (worse fill). close_open = confirm on close, fill next open. "
                   "close_level = confirm on close, limit back at the level (misses runaways).",
    },
}

PARAM_GRID_PRESETS = {
    "Entry-mode bake-off (137+BE lock)": {
        "or_bars": [1], "trade_mode": ["Both"], "stop_frac": [1.75], "vol_filter": [1.25],
        "atr_filter": [0.1], "breakout_buf": [0.0], "target_R": [4.5], "be_after_R": [1.0],
        "entry_mode": ["touch", "close", "close_open", "close_level"],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    stop_frac: float = 1.75, vol_filter: float = 1.25,
    breakout_buf: float = 0.0, target_R: float = 4.5,
    atr_filter: float = 0.1,
    be_after_R: float = 1.0, entry_mode: str = "touch",
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
                pend = 0           # close_open / close_level: +1/-1 confirmed, awaiting fill
                pend_lvl = 0.0     # close_level: the resting limit price
                for k in range(or_bars, m):
                    if pos == 0:
                        # ── pending fills (confirmation already happened on an earlier close) ──
                        if pend != 0 and entry_mode == "close_open":
                            entry = so[k]
                            pos = pend; pend = 0
                        elif pend != 0 and entry_mode == "close_level":
                            if pend > 0 and sl[k] <= pend_lvl:
                                entry = so[k] if so[k] < pend_lvl else pend_lvl   # limit or better
                                pos = 1; pend = 0
                            elif pend < 0 and sh[k] >= pend_lvl:
                                entry = so[k] if so[k] > pend_lvl else pend_lvl
                                pos = -1; pend = 0
                            else:
                                continue                                          # still waiting
                        if pos != 0:                                              # a pending fill landed
                            _risk = stop_frac * rng
                            stop = entry - _risk if pos > 0 else entry + _risk
                            tgt = (entry + target_R * _risk) if pos > 0 else (entry - target_R * _risk)
                            if target_R <= 0:
                                tgt = np.inf if pos > 0 else -np.inf
                            ek = k; _mfe = 0.0; _be = False; continue

                        # ── fresh trigger ──
                        if entry_mode == "touch":
                            up = sh[k] >= up_lvl
                            dn = sl[k] <= dn_lvl
                        else:                       # all close-confirmed modes trigger on the CLOSE
                            up = sc[k] >= up_lvl
                            dn = sc[k] <= dn_lvl
                        if not (up or dn):
                            continue
                        if vol_filter > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_filter * mv:
                                continue
                        side = 1 if (long_ok and up) else (-1 if (short_ok and dn) else 0)
                        if side == 0:
                            continue
                        if entry_mode in ("close_open", "close_level"):
                            pend = side
                            pend_lvl = up_lvl if side > 0 else dn_lvl
                            continue
                        if side > 0:
                            entry = sc[k] if entry_mode == "close" else (max(up_lvl, so[k]) if so[k] > up_lvl else up_lvl)
                        else:
                            entry = sc[k] if entry_mode == "close" else (min(dn_lvl, so[k]) if so[k] < dn_lvl else dn_lvl)
                        pos = side; ek = k
                        _risk = stop_frac * rng
                        stop = entry - _risk if pos > 0 else entry + _risk
                        tgt = (entry + target_R * _risk) if pos > 0 else (entry - target_R * _risk)
                        if target_R <= 0:
                            tgt = np.inf if pos > 0 else -np.inf
                        _mfe = 0.0; _be = False; continue
                    else:
                        if pos > 0:
                            if sl[k] <= stop:
                                ex_px = so[k] if so[k] < stop else stop           # gap-through
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
