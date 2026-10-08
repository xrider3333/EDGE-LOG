"""
NOISE 1.1 FUNDGRID -- NOISE_1_0 with the habitat rounds' frozen 54-cell grid as its search space.

WHAT THIS FILE IS FOR (NOISE lane, 2026-10-08): the NOISE habitat rounds (IWM r1, sector funds r1;
docs/PREREG_noise_sectors_r1_2026-10-08.md) crown a fund's own NOISE settings from a frozen grid,

    lookback         20 / 40 / 60
    band_mult_long   0.50 / 0.75 / 1.00
    band_mult_short  0.75 / 1.00 / 1.50
    stop_k           1.25 / 1.75

with the two NQ filters INHERITED and pinned (skip shorts after a weak prior close at 0.2; skip the
day after a top-5% prior range, vol_skip_pct 95) and NOISE_1_0's VWAP exit, bandwidth stop, flat at
the close, both sides, all day, one-bar confirmation. A Stage A PASS opens "a pinned 900-trial
Auto-Validate the same day ... the grid's axes as the search space"; this file is that space.

ONE DISCLOSED DIFFERENCE: an open range is min / max / step, so the short-band axis 0.75 / 1.00 / 1.50
cannot be written exactly - it is opened as 0.75 / 1.00 / 1.25 / 1.50 (step 0.25). The space is
3 x 3 x 4 x 2 = 72 cells; the 54 grid cells are all inside it.

The default is sector funds r1's XLK crown (40 / 1.00 / 1.00 / 1.75), so calling this file with no
params reproduces it. Entry/exit math is NOISE_1_0.py's, unchanged -- this file adds no rule and
changes no calculation.
"""
import importlib.util as _ilu
import inspect as _inspect
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "NOISE_1_0.py")
_spec = _ilu.spec_from_file_location("_noise10_base_fundgrid", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'NOISE 1.1 FUNDGRID - habitat-round grid open, NQ filters inherited'

_AUGUR_MARKET = {"instrument": "XLK", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

REQUIRED_LOOKBACK_SESSIONS = getattr(_base, "REQUIRED_LOOKBACK_SESSIONS", None)

# The XLK crown of sector funds r1 (Stage A 2026-10-08) on the pinned core.
_CROWN = {
    "lookback": 40, "band_mult_long": 1.0, "band_mult_short": 1.0,
    "exit_mode": "vwap", "side": "Both", "window": "all_day",
    "flat_eod": True, "skip_holidays": False,
    "stop_mode": "bandwidth", "stop_k": 1.75, "confirm_bars": 1,
    "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
    "vol_skip_pct": 95.0,
}

# OPEN: the grid's four axes. PINNED: the inherited core. Bools and strings need an explicit
#   single-entry "options" list -- a plain default is ignored by the validate path.
DEFAULT_PARAMS = {
    "lookback":        {"default": 40,   "min": 20,   "max": 60,   "step": 20,   "type": "int",   "label": "Noise lookback (sessions) - OPEN 20/40/60"},
    "band_mult_long":  {"default": 1.0,  "min": 0.5,  "max": 1.0,  "step": 0.25, "type": "float", "label": "Upper band width (x noise) - OPEN 0.50/0.75/1.00"},
    "band_mult_short": {"default": 1.0,  "min": 0.75, "max": 1.5,  "step": 0.25, "type": "float", "label": "Lower band width (x noise) - OPEN 0.75/1.00/1.25/1.50 (grid: 0.75/1.00/1.50)"},
    "exit_mode":       {"default": "vwap", "type": "str", "options": ["vwap"],                    "label": "Exit rule - PINNED to the VWAP cross"},
    "side":            {"default": "Both", "type": "str", "options": ["Both"],                    "label": "Direction - PINNED"},
    "window":          {"default": "all_day", "type": "str", "options": ["all_day"],              "label": "Entry window - PINNED"},
    "flat_eod":        {"default": True,  "type": "bool", "options": [True],                      "label": "Flat by session close - PINNED on"},
    "skip_holidays":   {"default": False, "type": "bool", "options": [False],                     "label": "Skip holiday half-days - PINNED off"},
    "stop_mode":       {"default": "bandwidth", "type": "str", "options": ["bandwidth"],          "label": "Protective stop - PINNED to bandwidth"},
    "stop_k":          {"default": 1.75, "min": 1.25, "max": 1.75, "step": 0.5,  "type": "float", "label": "Stop size (x band excursion) - OPEN 1.25/1.75"},
    "confirm_bars":    {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Entry confirmation - PINNED off"},
    "daytype_mode":    {"default": "skip_bot_short", "type": "str", "options": ["skip_bot_short"], "label": "Prior-day close-position filter - PINNED (inherited from NQ)"},
    "daytype_lo":      {"default": 0.2,  "min": 0.2,  "max": 0.2,  "step": 0.05, "type": "float", "label": "Bottom close-position threshold - PINNED (inherited)"},
    "daytype_hi":      {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.05, "type": "float", "label": "Top close-position threshold - PINNED (unused in this mode)"},
    "vol_skip_pct":    {"default": 95.0, "min": 95.0, "max": 95.0, "step": 5.0,  "type": "float", "label": "Skip the day after a top-5% prior range - PINNED (inherited)"},
}

_OPEN_VALS = {
    "lookback": [20, 40, 60],
    "band_mult_long": [0.5, 0.75, 1.0],
    "band_mult_short": [0.75, 1.0, 1.5],
    "stop_k": [1.25, 1.75],
}

# The habitat rounds' 54 cells as one grid cell-set, so a grid job on this file sweeps the frozen grid.
PARAM_GRID_PRESETS = {
    "Habitat grid (the frozen 54 cells)": dict(
        {k: [v] for k, v in _CROWN.items() if k not in _OPEN_VALS}, **_OPEN_VALS
    ),
}

_BASE_ARGS = set(_inspect.signature(_base.run_backtest).parameters)


def run_backtest(opens, highs, lows, closes, **kw):
    """Entry/exit math is NOISE_1_0's, unchanged -- this file only shapes the search space. The
    pinned core is applied here too, so calling this file with NO params reproduces the XLK crown."""
    p = dict(_CROWN)
    p.update({k: v for k, v in kw.items() if k in _BASE_ARGS})
    return _base.run_backtest(opens, highs, lows, closes, **p)
