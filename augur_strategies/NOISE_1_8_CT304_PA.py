"""
NOISE 1.8 CT304 + PEAK-AGE EXIT (M6) -- board t82, M6 peak-age validate (owner 11-01, MANAGER #159).
Prereg: docs/PREREG_noise_m6_peakage_2026-11-01.md (locked before any number).

WHAT THIS IS
  Run #382 (NOISE_1_8_CT304.py) with ONE exit-only overlay: test 244's M6 "stalled runner" - once the
  trade's best open profit reaches pa_arm_r x its own risk, exit when pa_n closed 5m bars pass with no
  new best. pa_mode time_exit is the CONTROL MANAGER asked for: a plain exit after pa_n bars, unarmed,
  so M6 has to beat a time exit of the same length, not just hold. pa_weight is the fraction of the
  position that takes the variant exit; the rest holds to #382's own exit (test 245: lot count is a
  weight, nothing more).

KNOBS (exit-only; entries, sizes and the core are #382's, untouched; fold / crown params pass through)
  pa_mode    off / peak_age / time_exit.  off = #382 exactly (parity control IN the space).
  pa_n       bars: peak age for peak_age, bars held for time_exit.
  pa_arm_r   peak_age only: best open profit must reach this many R before the stall clock can fire.
  pa_weight  fraction of size on the variant exit (0..1).

NO LOOK-AHEAD (lock2.py m6_peakage, copied rule for rule)
  The running best uses bar j's high (long) / low (short); the rule is read at bar j's CLOSE and FILLS
  AT THE OPEN OF BAR j+1. It only acts on bars before the leg's own exit: when the leg exits at bar x's
  open the last bar it may act on is x-1, else x; if j+1 is past that the leg's exit stands.

KNOWN LIMIT (same convention as tests 74/75/239/240)
  The overlay rewrites each #382 trade's exit; it never lets NOISE re-enter later the same day.
"""
import importlib.util as _ilu
import os as _os

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sp = _ilu.spec_from_file_location("_noise_ct304_for_pa", _os.path.join(_HERE, "NOISE_1_8_CT304.py"))
_base = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_base)

STRATEGY_NAME = "NOISE 1.8 CT304 (#382) + peak-age exit (M6)"
DESCRIPTION = ("Run #382's NOISE leg with an exit-only stalled-runner rule (exit when N bars pass with no new best "
               "after the best reaches A x R) or a plain N-bar time exit; pa_mode off = #382 exactly.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304.py"
REQUIRED_LOOKBACK_SESSIONS = getattr(_base, "REQUIRED_LOOKBACK_SESSIONS", None)
_COST_PTS = _base._COST_PTS
_CROWN = {"gate_tf_min": 30, "gate_len": 16, "gate_ratio": 1.15, "tilt_mult": 2.0}   # run #382 champion (defaults only)

DEFAULT_PARAMS = {
    "pa_mode": {"default": "off", "type": "str", "options": ["off", "peak_age", "time_exit"],
                "label": "Exit overlay", "tooltip": "off = run #382 exactly; peak_age = M6 stalled runner; "
                                                    "time_exit = plain exit after N bars (the control)."},
    "pa_n": {"default": 10, "min": 3, "max": 20, "step": 1, "type": "int",
             "label": "N bars", "tooltip": "Peak age (bars with no new best) or bars held for the time exit."},
    "pa_arm_r": {"default": 0.5, "min": 0.25, "max": 2.0, "step": 0.25, "type": "float",
                 "label": "Arm at, R", "tooltip": "peak_age only: best open profit must reach this many R first."},
    "pa_weight": {"default": 1.0, "min": 0.25, "max": 1.0, "step": 0.25, "type": "float",
                  "label": "Weight on the variant exit", "tooltip": "Fraction of size that takes the overlay exit."},
}

PARAM_GRID_PRESETS = {
    "Short  (t82 prereg cells)": {"pa_mode": ["off", "peak_age", "time_exit"], "pa_n": [10], "pa_arm_r": [0.5],
                                  "pa_weight": [0.5, 1.0]},
}


def peak_age_exit(O, H, L, e, x, sd, ep, raw, risk, n, arm):
    """(new_raw, new_exit_bar): lock2.py m6_peakage for one trade."""
    at_open = abs((ep + sd * raw) - O[x]) < 1e-9
    last, run, jpk = (x - 1 if at_open else x), 0.0, e
    for j in range(e, last):
        v = sd * ((H[j] if sd > 0 else L[j]) - ep)
        if v > run:
            run, jpk = v, j
        if risk > 0 and run >= arm * risk and (j - jpk) >= n:
            return sd * (O[j + 1] - ep), j + 1
    return raw, x


def time_exit(O, e, x, sd, ep, raw, n):
    """(new_raw, new_exit_bar): exit at the open of bar e+n (n full bars held), read the same way as M6."""
    at_open = abs((ep + sd * raw) - O[x]) < 1e-9
    last = x - 1 if at_open else x
    j = e + int(n) - 1                                   # decided at bar j's close, filled at j+1's open
    if j < last:
        return sd * (O[j + 1] - ep), j + 1
    return raw, x


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 pa_mode="off", pa_n=10, pa_arm_r=0.5, pa_weight=1.0,
                 return_trades=False, return_levels=False, **kw):
    want_levels = return_levels or pa_mode != "off"
    r = _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                           return_trades=True, return_levels=want_levels, **dict(_CROWN, **kw))
    if not r or pa_mode == "off":
        if r and not return_levels:
            r.pop("levels", None)
        if r and not return_trades:
            for k in ("trades", "trade_sizes", "size_cost_pts", "decisions", "levels"):
                r.pop(k, None)
        return r
    O, H, L = (_np.asarray(v, float) for v in (opens, highs, lows))
    w = float(pa_weight)
    trades, pnls = [], []
    for t, s, lv in zip(r["trades"], r["trade_sizes"], r["levels"]):
        e, x, sd, ep = int(t[0]), int(t[1]), int(t[3]), float(t[4])
        raw = (float(t[2]) + (s - 1.0) * _COST_PTS) / s           # undo the tilt's cost fold (as in _TD)
        if pa_mode == "peak_age":
            nraw, nx = peak_age_exit(O, H, L, e, x, sd, ep, raw, float(lv.get("risk") or 0.0), int(pa_n), float(pa_arm_r))
        else:
            nraw, nx = time_exit(O, e, x, sd, ep, raw, int(pa_n))
        mraw = (1.0 - w) * raw + w * nraw                          # w of the size on the variant, the rest holds
        pts = s * mraw - (s - 1.0) * _COST_PTS
        tt = list(t)
        tt[1], tt[2] = (nx if w >= 1.0 else x), pts
        trades.append(tuple(tt))
        pnls.append(pts)
    p = _np.asarray(pnls, float)
    if not len(p):
        return r
    wn, lo = p[p > 0], p[p < 0]
    gw, gl = float(wn.sum()), float(-lo.sum())
    cum = _np.cumsum(p)
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)), "win_rate": float(100.0 * len(wn) / len(p)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - _np.maximum.accumulate(cum)).min()), "avg_pnl": float(p.mean()),
           "wins": int(len(wn)), "losses": int(len(lo))}
    if return_trades:
        out["trades"] = trades
        out["trade_sizes"] = r["trade_sizes"]
        out["size_cost_pts"] = _COST_PTS
        if "decisions" in r:
            out["decisions"] = r["decisions"]
        if return_levels:
            out["levels"] = r["levels"]
    return out
