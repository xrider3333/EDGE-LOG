"""
ORB 3.6 R6 + TIME-DECAY TRAIL (test 240, ORB half; owner GO 10-31, MANAGER #132). Prereg:
docs/PREREG_orb_t240_timedecay_2026-10-31.md (locked with tools/prereg_lock.py before the validate was queued).

The entry, stop, breakeven, target and flat-at-close are ORB #314's, every knob PINNED at #314's champion. On top sits ONE
overlay, the time-decay ATR trail (test 239 Phase B's E4, there with fixed knobs), now with real ranges so a 900-trial
Auto-Validate maps it:

    stop = best close since entry - k(t) x ATR(td_atr_len)          (a short mirrors it)
    k(t) = td_k_start until td_start_min minutes after the open, then decays to td_k_end at the 16:00 close:
           p = (minutes since the open - td_start_min) / (390 - td_start_min), clipped to 0..1
           k = td_k_start - (td_k_start - td_k_end) x shape(p), shape = p (linear) | sqrt(p) | p^2

Execution (no look-ahead, test 239's rules): the level is computed on a bar's CLOSE and acts from the NEXT bar; never on the
entry bar; open through the level = fill at the open, else a touch = fill at the level. The leg's own exit always applies;
on the leg's exit bar the overlay acts only when that exit is not at the bar's open, and then the worse fill is taken.
Minutes come from the bar's place in its session on the 5m RTH master (bar k closes at 9:30 + 5 x (k + 1)).
"""
import importlib.util as _ilu
import os as _os

import numpy as np

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6_R6.py")
_spec = _ilu.spec_from_file_location("_orb36_r6_td", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ORB 3.6 R6 + time-decay trail (test 240)"
DESCRIPTION = ("ORB #314's champion with every entry/exit knob pinned, plus a time-decay ATR trail with open ranges "
               "(start k, end k, ATR length, decay shape, decay start time) for the 900-trial validate of test 240.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6_R6.py"

_CHAMP = {"or_bars": 2, "trade_mode": "First-candle dir", "stop_frac": 2.5, "breakout_buf": 0.25, "close_confirm": True,
          "partial_exit_R": 0.0, "trail_bars": 0, "be_after_R": 0.5, "target_R": 5.0, "atr_filter": 0.75,
          "vpace_filter": 0.8, "flat_eod": True, "skip_holidays": True}

DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED at #314"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"], "label": "Direction - PINNED at #314"},
    "stop_frac":      {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.25, "type": "float", "label": "Stop (x range width) - PINNED at #314"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED at #314"},
    "close_confirm":  {"default": True, "type": "bool", "options": [True], "label": "Confirm at bar close - PINNED at #314"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED off"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Bar trail - PINNED off"},
    "be_after_R":     {"default": 0.5,  "min": 0.5,  "max": 0.5,  "step": 0.25, "type": "float", "label": "Breakeven after (x risk) - PINNED at #314"},
    "target_R":       {"default": 5.0,  "min": 5.0,  "max": 5.0,  "step": 0.5,  "type": "float", "label": "Target (x risk) - PINNED at #314"},
    "atr_filter":     {"default": 0.75, "min": 0.75, "max": 0.75, "step": 0.05, "type": "float", "label": "Vol-regime filter - PINNED at #314"},
    "vpace_filter":   {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.05, "type": "float", "label": "Volume-pace gate - PINNED at #314"},
    "flat_eod":       {"default": True, "type": "bool", "options": [True], "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True, "type": "bool", "options": [True], "label": "Skip holidays - PINNED on"},
    "td_k_start":     {"default": 3.0,  "min": 2.0,  "max": 5.0,  "step": 0.5,  "type": "float", "label": "Trail width at the start (x ATR)"},
    "td_k_end":       {"default": 1.0,  "min": 0.5,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Trail width at the close (x ATR)"},
    "td_atr_len":     {"default": 14,   "min": 8,    "max": 30,   "step": 2,    "type": "int",   "label": "ATR length (bars)"},
    "td_shape":       {"default": "linear", "type": "str", "options": ["linear", "sqrt", "square"], "label": "Decay shape"},
    "td_start_min":   {"default": 0,    "min": 0,    "max": 300,  "step": 30,   "type": "int",   "label": "Decay starts (minutes after the open)"},
}

PARAM_GRID_PRESETS = {
    "Short - E4 point (3.0 -> 1.0, ATR 14, linear, from the open)": {
        "td_k_start": [3.0], "td_k_end": [1.0], "td_atr_len": [14], "td_shape": ["linear"], "td_start_min": [0]},
    "Medium - width x shape": {
        "td_k_start": [2.0, 3.0, 4.0], "td_k_end": [0.5, 1.0, 1.5], "td_atr_len": [14], "td_shape": ["linear", "sqrt", "square"],
        "td_start_min": [0, 120]},
}


def _atr(h, l, c, n):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.empty_like(tr)
    cs = np.cumsum(tr)
    for i in range(len(tr)):
        a = max(0, i - n + 1)
        out[i] = (cs[i] - (cs[a - 1] if a > 0 else 0.0)) / (i - a + 1)
    return out


def _k_at(minute, ks, ke, shape, start):
    span = max(1.0, 390.0 - start)
    p = min(1.0, max(0.0, (minute - start) / span))
    f = p if shape == "linear" else (p ** 0.5 if shape == "sqrt" else p * p)
    return ks - (ks - ke) * f


def overlay(trades, o, h, l, c, did, ks, ke, n_atr, shape, start):
    """[(entry_bar, exit_bar, raw_pts, side, entry_px)] -> same list with the trail's exits (raw, before cost)."""
    a = _atr(h, l, c, int(n_atr))
    pos = np.zeros(len(c), dtype=int)                      # bar's place in its session
    for i in range(1, len(c)):
        pos[i] = pos[i - 1] + 1 if did[i] == did[i - 1] else 0
    out = []
    for t in trades:
        e, x, raw, sd, ep = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        at_open = abs((ep + sd * raw) - o[x]) < 1e-9
        last = x - 1 if at_open else x
        stop, best, res, xb = None, ep, raw, x
        for j in range(e, last + 1):
            if j > e and stop is not None:
                hit = None
                if sd * (o[j] - stop) <= 0:
                    hit = sd * (o[j] - ep)
                elif sd * ((l[j] if sd > 0 else h[j]) - stop) <= 0:
                    hit = sd * (stop - ep)
                if hit is not None:
                    res, xb = (min(hit, raw) if j == x else hit), j
                    break
            if j >= x:
                break
            best = max(best, c[j]) if sd > 0 else min(best, c[j])
            k = _k_at(5.0 * (pos[j] + 1), ks, ke, shape, start)
            stop = best - sd * k * a[j]
        out.append((e, xb, res, sd, ep) + tuple(t[5:]))
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, return_trades=False,
                 td_k_start=3.0, td_k_end=1.0, td_atr_len=14, td_shape="linear", td_start_min=0, **kw):
    p = dict(_CHAMP)
    p.update({k: v for k, v in kw.items() if k in _CHAMP})
    r = _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, return_trades=True, **p)
    if r is None:
        return None
    o, h, l, c = (np.asarray(x, float) for x in (opens, highs, lows, closes))
    T = overlay(r.get("trades") or [], o, h, l, c, np.asarray(day_id), float(td_k_start), float(td_k_end),
                int(td_atr_len), str(td_shape), float(td_start_min))
    pn = np.asarray([float(t[2]) for t in T], float)
    wins, losses = pn[pn > 0], pn[pn < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = np.cumsum(pn) if len(pn) else np.zeros(1)
    out = {"total_pnl": float(pn.sum()), "num_trades": int(len(pn)),
           "win_rate": float(100.0 * len(wins) / len(pn)) if len(pn) else 0.0,
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()) if len(pn) else 0.0,
           "avg_pnl": float(pn.mean()) if len(pn) else 0.0, "wins": int(len(wins)), "losses": int(len(losses))}
    if return_trades:
        out["trades"] = T
    return out
