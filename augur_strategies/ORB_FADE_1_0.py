"""
ORB FAILED-BREAK FADE — trade the false wick in reverse (item R, ORB.md §6).

The reconcile tool counted 306 false-wick breaks that cost the touch-entry ORB −$149,562:
price pierces the opening-range edge intrabar, then CLOSES back inside — the breakout trap.
This strategy trades that failure as the signal: on the FIRST bar that pierces an edge, if it
closes back inside the range, FADE it (short a failed up-break / long a failed down-break).
If the first pierce closes BEYOND the edge instead (a real break), the session is done — the
breakout won and there is nothing to fade.

Mechanics: entry at the failure bar's close; stop just beyond the wick extreme (+0.15×range
pad); target = the OPPOSITE range edge (target_R=0) or an R-multiple; EOD flat; one trade per
session; gap-through realism on the stop. `vol_gate` mirrors ORB's volume filter: 1.25 = fade
only the pokes the deploy ORB would actually have entered (its real losses); 0 = fade every
false wick. PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'ORB FADE 1.0 · failed-break reversal'
DESCRIPTION   = ("Fades the opening-range false wick: first pierce of an OR edge that closes "
                 "back inside triggers a trade AGAINST the break, stop beyond the wick, target "
                 "the far edge or an R-multiple. Companion/counter to the ORB family — turns "
                 "its documented worst pattern (306 wicks, −$149k) into the signal.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_0.py"

DEFAULT_PARAMS = {
    "or_bars":   {"default": 1, "min": 1, "max": 12, "step": 1, "type": "int", "label": "Opening range (bars)"},
    "trade_mode":{"default": "Both", "type": "str", "options": ["Both", "Long Only", "Short Only"], "label": "Fade direction"},
    "vol_gate":  {"default": 0.0, "min": 0.0, "max": 3.0, "step": 0.25, "type": "float",
                  "label": "Volume gate (× session avg, 0=fade all)",
                  "tooltip": "1.25 = fade only pokes with breakout-grade volume (the ones the deploy "
                             "ORB would have entered and lost); 0 = fade every false wick."},
    "stop_pad":  {"default": 0.15, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
                  "label": "Stop pad beyond the wick (× range)"},
    "target_R":  {"default": 0.0, "min": 0.0, "max": 4.0, "step": 0.5, "type": "float",
                  "label": "Target (× risk, 0 = opposite range edge)"},
}

PARAM_GRID_PRESETS = {
    "Fade feasibility": {
        "or_bars": [1], "trade_mode": ["Both"], "vol_gate": [0.0, 1.25],
        "stop_pad": [0.15], "target_R": [0.0, 1.0, 1.5, 2.0],
    },
}


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    or_bars: int = 1, trade_mode: str = "Both",
    vol_gate: float = 0.0, stop_pad: float = 0.15, target_R: float = 0.0,
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

    fade_short_ok = trade_mode in ("Both", "Short Only")   # short a failed UP-break
    fade_long_ok  = trade_mode in ("Both", "Long Only")    # long a failed DOWN-break

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
        if m > or_bars + 1 and or_bars >= 1:
            so, sh, sl, sc = o[i:j], h[i:j], l[i:j], c[i:j]
            sv = v[i:j] if v is not None else None
            or_hi = sh[:or_bars].max()
            or_lo = sl[:or_bars].min()
            rng   = or_hi - or_lo
            if rng > 0:
                pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; ek = -1
                for k in range(or_bars, m):
                    if pos == 0:
                        up = sh[k] >= or_hi + 1e-12 and sh[k] > or_hi   # pierced above
                        dn = sl[k] < or_lo                              # pierced below
                        if not (up or dn):
                            continue
                        # volume gate (mirror of ORB's filter on the poke bar)
                        if vol_gate > 0 and sv is not None and k > 0:
                            mv = sv[:k].mean()
                            if mv > 0 and sv[k] < vol_gate * mv:
                                break                      # ORB wouldn't have entered; no fade either
                        if up and sc[k] < or_hi and fade_short_ok:      # failed up-break -> SHORT
                            entry = sc[k]
                            stop  = sh[k] + stop_pad * rng
                            risk  = stop - entry
                            tgt   = or_lo if target_R <= 0 else entry - target_R * risk
                            pos = -1; ek = k; continue
                        elif dn and sc[k] > or_lo and fade_long_ok:     # failed down-break -> LONG
                            entry = sc[k]
                            stop  = sl[k] - stop_pad * rng
                            risk  = entry - stop
                            tgt   = or_hi if target_R <= 0 else entry + target_R * risk
                            pos = 1; ek = k; continue
                        else:
                            break                          # clean break (or wrong side) — no fade today
                    else:
                        if pos > 0:
                            if sl[k] <= stop:
                                ex = so[k] if so[k] < stop else stop
                                pnl_list.append(ex - entry)
                                if return_trades: trade_log.append((i + ek, i + k, ex - entry, 1, entry))
                                pos = 0; break
                            if sh[k] >= tgt:
                                pnl_list.append(tgt - entry)
                                if return_trades: trade_log.append((i + ek, i + k, tgt - entry, 1, entry))
                                pos = 0; break
                        else:
                            if sh[k] >= stop:
                                ex = so[k] if so[k] > stop else stop
                                pnl_list.append(entry - ex)
                                if return_trades: trade_log.append((i + ek, i + k, entry - ex, -1, entry))
                                pos = 0; break
                            if sl[k] <= tgt:
                                pnl_list.append(entry - tgt)
                                if return_trades: trade_log.append((i + ek, i + k, entry - tgt, -1, entry))
                                pos = 0; break
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
