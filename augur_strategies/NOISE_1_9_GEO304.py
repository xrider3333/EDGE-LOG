"""
NOISE 1.9 GEO304 -- the crown GEOMETRY searched again, but only on compressed hours.

ROUND 60 (2026-09-24, NOISE.md). Every NOISE validate to date searched the geometry on ALL trades and
then asked whether an hourly-squeeze FILTER improves the winner. Run #398 (NOISE-48) settled the filter
itself: hourly frame, length 20, threshold 1.15, PASS, overfit 0.198. Nobody has asked the other half of
the question -- whether the best ENTRY GEOMETRY for a book that only trades compressed hours is the same
geometry that wins on the whole tape. The compressed hour is a quieter, tighter regime, so the bands and
the stop that suit it need not be the crown's.

WHAT IS OPEN: the five knobs the crown neighbourhood file already fences, one step either side of run
#304's champion -- lookback 36/40/44, long band 0.5/0.75/1.0, short band 1.25/1.5/1.75, stop 1.5/1.75/2.0,
volatility skip 92.5/95/97.5 (243 cells). Everything else is run #304's champion, written out literally.
WHAT IS FROZEN: the filter, at run #398's crowned setting (60-minute frame, length 20, threshold 1.15).
The filter was chosen on these same years, so this file cannot re-choose it; the search here is over the
geometry only, and its walk-forward folds and overfit test judge that.

FENCED: an out-of-set configuration is REFUSED, never clamped.
PRE-REGISTERED BAR (written before the job was queued): the centre cell is the incumbent. A different
champion is adopted only if it PASSES, its overfit reading is no worse than #398's 0.198, and it beats
the centre continuously on profit factor in BOTH eras (before 2024, 2024 on) at cost 0.533 -- more
in-sample dollars alone is not enough, that is what crowned the 30-minute gate three times.
READ THE LOCKBOX CONTINUOUSLY - the saved strip is a cold-restart reload for NOISE.
"""
import importlib.util as _ilu
import os as _os

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _load(fn, alias):
    sp = _ilu.spec_from_file_location(alias, _os.path.join(_HERE, fn))
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


_base = _load("NOISE_1_0.py", "_n10_for_noise_1_9_hsq304")
_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_sq_for_hsq")   # run #321 compression function, by import

STRATEGY_NAME = "NOISE 1.9 crown geometry searched on compressed hours only"
DESCRIPTION = ("Only trades whose decision bar sat inside an hourly squeeze (60 min, length 20, threshold 1.15 - run 398 crowned) are kept; the five entry-geometry knobs are searched one step either side of run 304.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

_FROZEN = {'exit_mode': 'vwap', 'side': 'Both', 'window': 'all_day', 'flat_eod': True, 'skip_holidays': False, 'stop_mode': 'bandwidth', 'confirm_bars': 1, 'daytype_mode': 'skip_bot_short', 'daytype_lo': 0.2, 'daytype_hi': 0.8}

_CENTER = {'lookback': 40, 'band_mult_long': 0.75, 'band_mult_short': 1.5, 'stop_k': 1.75, 'vol_skip_pct': 95.0}

_ADMISSIBLE = {'lookback': [36, 40, 44], 'band_mult_long': [0.5, 0.75, 1.0],
               'band_mult_short': [1.25, 1.5, 1.75], 'stop_k': [1.5, 1.75, 2.0],
               'vol_skip_pct': [92.5, 95.0, 97.5]}
_GATE = {'tf_min': 60, 'len': 20, 'ratio': 1.15}     # run #398's crowned filter, frozen

DEFAULT_PARAMS = {
    "lookback": {"default": 40, "min": 36, "max": 44, "step": 4, "type": "int", "label": "Bands lookback (bars)"},
    "band_mult_long": {"default": 0.75, "min": 0.5, "max": 1.0, "step": 0.25, "type": "float", "label": "Long band width"},
    "band_mult_short": {"default": 1.5, "min": 1.25, "max": 1.75, "step": 0.25, "type": "float", "label": "Short band width"},
    "stop_k": {"default": 1.75, "min": 1.5, "max": 2.0, "step": 0.25, "type": "float", "label": "Stop width (bandwidths)"},
    "vol_skip_pct": {"default": 95.0, "min": 92.5, "max": 97.5, "step": 2.5, "type": "float", "label": "Skip days above this volatility percentile"},
}

PARAM_GRID_PRESETS = {"Short  (the fenced 243-cell geometry neighbourhood)": dict(_ADMISSIBLE)}


def _in_set(p):
    for k, allowed in _ADMISSIBLE.items():
        if not any(abs(float(p[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, _stop_event=None, _pause_event=None, **kw):
    p = {k: kw.get(k, v) for k, v in _CENTER.items()}
    if not _in_set(p):
        return None          # outside the pre-registered set - refused, never clamped
    if day_id is None or index is None:
        return None
    call = dict(_FROZEN)
    call.update({k: (int(round(float(v))) if k == "lookback" else float(v)) for k, v in p.items()})
    r = _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                           return_trades=True, _stop_event=_stop_event, _pause_event=_pause_event,
                           **call)
    if not r or not r.get("trades"):
        return None
    comp = _sq._compression(_np.asarray(highs, float), _np.asarray(lows, float),
                            _np.asarray(closes, float), day_id, index,
                            _GATE["tf_min"], _GATE["len"], _GATE["ratio"])
    n = len(closes)
    kept = [t for t in r["trades"] if 0 <= int(t[0]) - 1 < n and comp[int(t[0]) - 1]]
    if not kept:
        return None
    pnls = _np.array([float(t[2]) for t in kept], float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = _np.cumsum(pnls)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - _np.maximum.accumulate(cum)).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = kept
    return out
