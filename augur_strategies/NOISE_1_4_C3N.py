"""
NOISE 1.4 C3N -- the cost-robust corner (C3): band exit, ATR stop, three confirming closes, afternoon only.

ROUND 57 (2026-09-13, NOISE.md). Owner: "some of these configs are in an auto validate, and some aren't -
start auto validating them." Round 56's scorecard ranked every NOISE configuration on one continuous tape.
This configuration was measured there but has never been the CHAMPION of an Auto-Validate:
  it came out of the 2-minute search as rank 8 and was measured by hand in rounds 38 to 43, but no
  Auto-Validate has ever crowned it.

WHAT THIS FILE IS
  A fenced neighbourhood: every setting that defines the configuration is frozen, and 6 knobs are open
  one step either side of the configuration's own value, which is each knob's default. 729 cells.
  An Auto-Validate needs open ranges to have a landscape (a pinned file has no overfit test, no plateau,
  no neighbours), and the fence keeps the search inside this configuration's neighbourhood: an out-of-set
  cell is REFUSED, never clamped. The validate judges whichever cell its search crowns; whether that is
  the configuration itself is read off the run.

  Scorecard reading at the centre cell (continuous 2010-06-07 to 2026-07-16, house cost 0.533):
  2,112 trades, profit factor 1.457, 2024 onward 1.343, sealed year 1.065.

READ THE LOCKBOX CONTINUOUSLY. The validate grades its lockbox on a cold-restart reload that for NOISE drops
a large share of the sealed year (run #382: 239 reloaded vs 314 continuous). Judge the sealed year on a
continuous replay sliced by entry time.
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


_base = _load("NOISE_1_0.py", "_n10_for_noise_1_4_c3n")

STRATEGY_NAME = "NOISE 1.4 cost-robust corner neighbourhood"
DESCRIPTION = ("The C3 cost-robust NOISE geometry with its six numeric knobs open one step either side and every other setting frozen.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

_FROZEN = {'exit_mode': 'band', 'side': 'Both', 'window': 'afternoon_block', 'flat_eod': False, 'skip_holidays': False, 'stop_mode': 'atr', 'daytype_mode': 'skip_bot_short', 'daytype_lo': 0.1, 'daytype_hi': 0.95}

_CENTER = {'lookback': 74, 'band_mult_long': 1.0, 'band_mult_short': 1.75, 'stop_k': 0.75, 'vol_skip_pct': 93.0, 'confirm_bars': 3}

_ADMISSIBLE = {'lookback': [66, 74, 82], 'band_mult_long': [0.75, 1.0, 1.25], 'band_mult_short': [1.5, 1.75, 2.0], 'stop_k': [0.5, 0.75, 1.0], 'vol_skip_pct': [90.0, 93.0, 96.0], 'confirm_bars': [2, 3, 4]}

DEFAULT_PARAMS = {
    "lookback": {"default": 74, "min": 66, "max": 82, "step": 8, "type": "int", "label": "Noise lookback (sessions)"},
    "band_mult_long": {"default": 1.0, "min": 0.75, "max": 1.25, "step": 0.25, "type": "float", "label": "Upper band width (x noise)"},
    "band_mult_short": {"default": 1.75, "min": 1.5, "max": 2.0, "step": 0.25, "type": "float", "label": "Lower band width (x noise)"},
    "stop_k": {"default": 0.75, "min": 0.5, "max": 1.0, "step": 0.25, "type": "float", "label": "Protective stop size"},
    "vol_skip_pct": {"default": 93.0, "min": 90.0, "max": 96.0, "step": 3.0, "type": "float", "label": "Skip entries above prior-day volatility percentile"},
    "confirm_bars": {"default": 3, "min": 2, "max": 4, "step": 1, "type": "int", "label": "Closes outside the band before entry"},
}

PARAM_GRID_PRESETS = {"Short  (the fenced 729-cell neighbourhood)": dict(_ADMISSIBLE)}


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
    for k in ("lookback", "confirm_bars"):
        if k in p:
            p[k] = int(round(float(p[k])))
    call = dict(_FROZEN)
    call.update(p)
    return _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                              return_trades=return_trades, _stop_event=_stop_event,
                              _pause_event=_pause_event, **call)
