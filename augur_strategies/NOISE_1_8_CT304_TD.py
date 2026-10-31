"""
NOISE 1.8 CT304 + TIME-DECAY TRAIL -- test 240 (owner GO 10-31, MANAGER #150).
Prereg: docs/PREREG_noise_t240_timedecay_2026-10-31.md (locked before the job was queued).

WHAT THIS IS
  Run #382 (NOISE_1_8_CT304.py at its crowned tilt: tilt_mult 2.0, gate 30 min / 16 / 1.15) with
  ONE exit overlay opened for Auto-Validate: an ATR trail from the trade's best close whose width
  k shrinks toward the close. Test 239 ran one fixed setting of it (start 3 x ATR14, linear to a
  floor of 1 x ATR at 16:00) and it came 4th of 5 out of sample; this file lets the search choose
  the shape instead of a guess.

KNOBS (all exit-only; entries, sizes and the core are #382's, untouched)
  td_shape    off / linear / convex.  off = #382 exactly (the parity control is IN the space).
  td_k_start  trail width in ATRs before the decay starts.
  td_k_end    trail width in ATRs at 16:00 (the decay runs from td_k_start to td_k_end).
  td_atr      ATR length in 5m bars (simple mean of true range; no trail until it exists).
  td_start    minutes after 09:30 when the decay begins (0 = from the open).
  convex = frac**2 (stays wide most of the day, tightens late); linear = frac.

NO LOOK-AHEAD
  The trail is set from bar j's CLOSE and acts from bar j+1: open through the stop fills at the
  open, a touch fills at the stop. On the trade's own exit bar the trail only acts when the leg's
  exit is NOT at that bar's open, and then the worse of the two fills is kept.

KNOWN LIMIT (stated in the prereg)
  The overlay rewrites each #382 trade's exit; it does not let NOISE re-enter later the same day
  after an earlier trail exit. So a trail can only take money from or give money to the trades
  #382 actually took - the same convention as tests 74, 75 and 239.
"""
import importlib.util as _ilu
import os as _os

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sp = _ilu.spec_from_file_location("_noise_ct304_for_td", _os.path.join(_HERE, "NOISE_1_8_CT304.py"))
_base = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_base)

STRATEGY_NAME = "NOISE 1.8 CT304 (#382) + time-decay ATR trail"
DESCRIPTION = ("Run #382's crowned NOISE leg with an exit-only ATR trail from the best close whose "
               "width decays toward the close; td_shape off = #382 exactly.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304.py"
REQUIRED_LOOKBACK_SESSIONS = getattr(_base, "REQUIRED_LOOKBACK_SESSIONS", None)
_COST_PTS = _base._COST_PTS
_CROWN = {"gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15, "tilt_mult": 2.0}   # run #382 champion

DEFAULT_PARAMS = {
    "td_shape": {"default": "off", "type": "str", "options": ["off", "linear", "convex"],
                 "label": "Time-decay trail shape",
                 "tooltip": "off = run #382 exactly; linear / convex = how the trail width shrinks toward 16:00."},
    "td_k_start": {"default": 3.0, "min": 2.0, "max": 5.0, "step": 0.5, "type": "float",
                   "label": "Trail width before the decay, ATRs", "tooltip": "Test 239 used 3.0."},
    "td_k_end": {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.25, "type": "float",
                 "label": "Trail width at 16:00, ATRs", "tooltip": "Test 239 used a floor of 1.0."},
    "td_atr": {"default": 14, "min": 7, "max": 28, "step": 7, "type": "int",
               "label": "ATR length, 5m bars", "tooltip": "Test 239 used 14."},
    "td_start": {"default": 0, "min": 0, "max": 300, "step": 30, "type": "int",
                 "label": "Decay starts, minutes after 09:30", "tooltip": "0 = from the open (test 239)."},
}

PARAM_GRID_PRESETS = {
    "Short  (test 239's fixed trail + off)": {"td_shape": ["off", "linear"], "td_k_start": [3.0], "td_k_end": [1.0],
                                              "td_atr": [14], "td_start": [0]},
}


def _atr(H, L, C, n):
    pc = _np.r_[C[0], C[:-1]]
    tr = _np.maximum(H - L, _np.maximum(_np.abs(H - pc), _np.abs(L - pc)))
    out = _np.full(len(C), _np.nan)
    if len(C) >= n:
        cs = _np.cumsum(tr)
        out[n - 1:] = (cs[n - 1:] - _np.r_[0.0, cs[:-n]]) / n
    return out


def _mins_since_open(index):
    import pandas as _pd
    idx = _pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    m = (idx - idx.normalize()).total_seconds().to_numpy() / 60.0 - 570.0 + 5.0    # bar END, minutes after 09:30
    return _np.clip(m, 0.0, 390.0)


def _k_path(m, shape, k0, k1, start):
    frac = _np.clip((m - start) / max(390.0 - start, 1.0), 0.0, 1.0)
    if shape == "convex":
        frac = frac ** 2
    return k0 + (k1 - k0) * frac


def trail_exit(O, H, L, C, a, k, e, x, sd, ep, raw):
    """(new_raw, new_exit_bar) for one trade; raw / x unchanged when the trail never fires."""
    at_open = abs((ep + sd * raw) - O[x]) < 1e-9
    last = x - 1 if at_open else x
    stop, best = None, ep
    for j in range(e, last + 1):
        if j > e and stop is not None:
            hit = None
            if sd * (O[j] - stop) <= 0:
                hit = sd * (O[j] - ep)
            elif sd * ((L[j] if sd > 0 else H[j]) - stop) <= 0:
                hit = sd * (stop - ep)
            if hit is not None:
                return (min(hit, raw) if j == x else hit), j
        if j >= x:
            break
        best = max(best, C[j]) if sd > 0 else min(best, C[j])
        if _np.isfinite(a[j]):
            s = best - sd * k[j] * a[j]
            stop = s if stop is None else (max(stop, s) if sd > 0 else min(stop, s))
    return raw, x


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 td_shape="off", td_k_start=3.0, td_k_end=1.0, td_atr=14, td_start=0,
                 return_trades=False, return_levels=False, **kw):
    r = _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                           return_trades=True, return_levels=return_levels, **dict(kw, **_CROWN))
    if not r or td_shape == "off" or index is None:
        if r and not return_trades:
            for k in ("trades", "trade_sizes", "size_cost_pts", "decisions", "levels"):
                r.pop(k, None)
        return r
    O, H, L, C = (_np.asarray(v, float) for v in (opens, highs, lows, closes))
    a = _atr(H, L, C, int(td_atr))
    k = _k_path(_mins_since_open(index), td_shape, float(td_k_start), float(td_k_end), float(td_start))
    trades, pnls = [], []
    for t, s in zip(r["trades"], r["trade_sizes"]):
        e, x, sd, ep = int(t[0]), int(t[1]), int(t[3]), float(t[4])
        raw = (float(t[2]) + (s - 1.0) * _COST_PTS) / s           # undo the tilt's cost fold
        nraw, nx = trail_exit(O, H, L, C, a, k, e, x, sd, ep, raw)
        pts = s * nraw - (s - 1.0) * _COST_PTS
        tt = list(t)
        tt[1], tt[2] = nx, pts
        trades.append(tuple(tt))
        pnls.append(pts)
    p = _np.asarray(pnls, float)
    w, lo = p[p > 0], p[p < 0]
    gw, gl = float(w.sum()), float(-lo.sum())
    cum = _np.cumsum(p)
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)), "win_rate": float(100.0 * len(w) / len(p)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - _np.maximum.accumulate(cum)).min()), "avg_pnl": float(p.mean()),
           "wins": int(len(w)), "losses": int(len(lo))}
    if return_trades:
        out["trades"] = trades
        out["trade_sizes"] = r["trade_sizes"]
        out["size_cost_pts"] = _COST_PTS
        for key in ("decisions", "levels"):
            if key in r:
                out[key] = r[key]
    return out
