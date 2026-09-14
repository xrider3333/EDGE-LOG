"""
NOISE 1.1 N304C2 -- the live crown's settings, waiting for 2 closes outside the band before entering.

ROUND 57 (2026-09-13, NOISE.md). Owner: "some of these configs are in an auto validate, and some aren't -
start auto validating them." Round 56's scorecard ranked every NOISE configuration on one continuous tape.
This configuration was measured there but has never been the CHAMPION of an Auto-Validate:
  round 45 measured it by hand; run #316 validated a different configuration with the same confirmation
  (lookback 37, stop 2.0, volatility skip 90), so this one was never judged.

WHAT THIS FILE IS
  A fenced neighbourhood: every setting that defines the configuration is frozen, and 5 knobs are open
  one step either side of the configuration's own value, which is each knob's default. 243 cells.
  An Auto-Validate needs open ranges to have a landscape (a pinned file has no overfit test, no plateau,
  no neighbours), and the fence keeps the search inside this configuration's neighbourhood: an out-of-set
  cell is REFUSED, never clamped. The validate judges whichever cell its search crowns; whether that is
  the configuration itself is read off the run.

  Scorecard reading at the centre cell (continuous 2010-06-07 to 2026-07-16, house cost 0.533):
  4,075 trades, profit factor 1.403, 2024 onward 1.299, sealed year 1.262.

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


_base = _load("NOISE_1_0.py", "_n10_for_noise_1_1_n304c2")

STRATEGY_NAME = "NOISE 1.1 live crown neighbourhood, 2 confirming closes"
DESCRIPTION = ("The live NOISE crown (run 304) requiring two closes outside the band, its five numeric knobs open one step either side and every other setting frozen.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

_FROZEN = {'exit_mode': 'vwap', 'side': 'Both', 'window': 'all_day', 'flat_eod': True, 'skip_holidays': False, 'stop_mode': 'bandwidth', 'confirm_bars': 2, 'daytype_mode': 'skip_bot_short', 'daytype_lo': 0.2, 'daytype_hi': 0.8}

_CENTER = {'lookback': 40, 'band_mult_long': 0.75, 'band_mult_short': 1.5, 'stop_k': 1.75, 'vol_skip_pct': 95.0}

_ADMISSIBLE = {'lookback': [36, 40, 44], 'band_mult_long': [0.5, 0.75, 1.0], 'band_mult_short': [1.25, 1.5, 1.75], 'stop_k': [1.5, 1.75, 2.0], 'vol_skip_pct': [92.5, 95.0, 97.5]}

DEFAULT_PARAMS = {
    "lookback": {"default": 40, "min": 36, "max": 44, "step": 4, "type": "int", "label": "Noise lookback (sessions)"},
    "band_mult_long": {"default": 0.75, "min": 0.5, "max": 1.0, "step": 0.25, "type": "float", "label": "Upper band width (x noise)"},
    "band_mult_short": {"default": 1.5, "min": 1.25, "max": 1.75, "step": 0.25, "type": "float", "label": "Lower band width (x noise)"},
    "stop_k": {"default": 1.75, "min": 1.5, "max": 2.0, "step": 0.25, "type": "float", "label": "Protective stop size"},
    "vol_skip_pct": {"default": 95.0, "min": 92.5, "max": 97.5, "step": 2.5, "type": "float", "label": "Skip entries above prior-day volatility percentile"},
}

PARAM_GRID_PRESETS = {"Short  (the fenced 243-cell neighbourhood)": dict(_ADMISSIBLE)}


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
