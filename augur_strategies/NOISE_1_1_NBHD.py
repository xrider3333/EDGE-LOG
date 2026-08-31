"""
NOISE 1.1 NBHD -- the SBS+V90 champion core with a TIGHT NEIGHBOURHOOD open.

WHAT THIS FILE IS FOR (owner 2026-08-30: "do the restricted re-search"):
run #243 crowned NOISE_1_1_SBS_V90.py, a PINNED single-config file. A pinned
validate searches one configuration, so it saves a one-point landscape: no
config-params parallel coordinates, no PDP curves, no 2E-2G surfaces, no knob
importance, no neighbour/plateau read and -- because CSCV needs a population --
no PBO at all. That is why run #243 shows "PBO n/a".

The opposite extreme is a plain validate on the parent NOISE_1_0.py, whose 15
knobs are wide open. That was run #237 (and its 2026-08-30 replication, run
#302): the sampler wandered off the champion core entirely -- lookback 64 with a
fixed stop -- and came back WEAK with PBO 0.599/0.60. Run #231, a narrower
300-config search, read PBO 0.37. Both are above the <=0.30 healthy band, and the
number climbs with the size of the pool the optimiser gets to pick from.

THIS FILE IS THE MIDDLE. The champion CORE is pinned exactly as SBS_V90 has it --
VWAP exit, both sides, all day, flat at the close, holidays traded, bandwidth
stop, the weak-close short filter (skip_bot_short) with its calibrated 0.2
threshold, one-bar confirmation -- and only the five knobs that set the champion's
GEOMETRY are left open, one grid step either side of the crowned value:

    lookback         40 / 44 / 48          (champion 44)
    band_mult_long   0.50 / 0.75 / 1.00    (champion 0.75)
    band_mult_short  1.25 / 1.50 / 1.75    (champion 1.50)
    stop_k           1.50 / 1.75 / 2.00    (champion 1.75)
    vol_skip_pct     85 / 90 / 95          (champion 90)

3^5 = 243 cells. The crowned config is IN the space (it is the centre of every
axis), so the search can only confirm it or find a neighbour that beats it, and
the resulting report finally carries the landscape run #243 could never have:
points, PDP, parallel coordinates, surfaces, knob importance, neighbours and a
real PBO measured over a pool the champion actually belongs to.

READING THE PBO THIS PRODUCES -- HONESTLY. PBO is not comparable across pools of
different size or spread. A tight neighbourhood of near-identical configs SHOULD
read lower than a wide-open search, because the in-sample best is far less likely
to be a lucky outlier when every candidate is a small perturbation of the same
strategy. That is a genuine statement about THIS selection (did the crowned
geometry hold up among its own neighbours?) and NOT a licence to quote it against
run #237's 0.60, which answered a different and much harder question (does the
champion survive when the whole NOISE_1_0 space competes?). Report both.

LOCKBOX HONESTY, CARRIED FORWARD from NOISE_1_1_SBS_V90.py: the NOISE family
lockbox is SPENT -- it has been read many times (runs 202/203, the 2026-08-11
gate test, runs #225/#231/#243, run #302). Every lockbox figure this run prints is
CONFIRMATORY ONLY and can never promote NOISE. The walk-forward folds and forward
paper data are the real judges.

Entry/exit math is NOISE_1_0.py's, unchanged. This file only shapes the search
space -- it adds no rule and changes no calculation.
"""
import importlib.util as _ilu
import inspect as _inspect
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "NOISE_1_0.py")
_spec = _ilu.spec_from_file_location("_noise10_base_nbhd", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'NOISE 1.1 NBHD - champion core, geometry neighbourhood open'

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

# The crowned SBS_V90 configuration. Every knob below either equals one of these
#   values (pinned) or is centred on it (open).
_CHAMP = {
    "lookback": 44, "band_mult_long": 0.75, "band_mult_short": 1.5,
    "exit_mode": "vwap", "side": "Both", "window": "all_day",
    "flat_eod": True, "skip_holidays": False,
    "stop_mode": "bandwidth", "stop_k": 1.75, "confirm_bars": 1,
    "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
    "vol_skip_pct": 90.0,
}

# OPEN: five geometry knobs, one grid step either side of the champion (3 values each).
# PINNED: the champion core. Bools and strings need an explicit single-entry
#   "options" list -- a plain default is ignored by the validate path (that is
#   what voided runs 206-208).
DEFAULT_PARAMS = {
    "lookback":        {"default": 44,   "min": 40,   "max": 48,   "step": 4,    "type": "int",   "label": "Noise lookback (sessions) - OPEN 40/44/48"},
    "band_mult_long":  {"default": 0.75, "min": 0.5,  "max": 1.0,  "step": 0.25, "type": "float", "label": "Upper band width (x noise) - OPEN 0.50/0.75/1.00"},
    "band_mult_short": {"default": 1.5,  "min": 1.25, "max": 1.75, "step": 0.25, "type": "float", "label": "Lower band width (x noise) - OPEN 1.25/1.50/1.75"},
    "exit_mode":       {"default": "vwap", "type": "str", "options": ["vwap"],                    "label": "Exit rule - PINNED to the VWAP cross"},
    "side":            {"default": "Both", "type": "str", "options": ["Both"],                    "label": "Direction - PINNED"},
    "window":          {"default": "all_day", "type": "str", "options": ["all_day"],              "label": "Entry window - PINNED"},
    "flat_eod":        {"default": True,  "type": "bool", "options": [True],                      "label": "Flat by session close - PINNED on"},
    "skip_holidays":   {"default": False, "type": "bool", "options": [False],                     "label": "Skip holiday half-days - PINNED off"},
    "stop_mode":       {"default": "bandwidth", "type": "str", "options": ["bandwidth"],          "label": "Protective stop - PINNED to bandwidth"},
    "stop_k":          {"default": 1.75, "min": 1.5,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Stop size (x band excursion) - OPEN 1.50/1.75/2.00"},
    "confirm_bars":    {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Entry confirmation - PINNED off"},
    "daytype_mode":    {"default": "skip_bot_short", "type": "str", "options": ["skip_bot_short"], "label": "Prior-day close-position filter - PINNED to the weak-close short skip"},
    "daytype_lo":      {"default": 0.2,  "min": 0.2,  "max": 0.2,  "step": 0.05, "type": "float", "label": "Bottom close-position threshold - PINNED (calibrated)"},
    "daytype_hi":      {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.05, "type": "float", "label": "Top close-position threshold - PINNED (unused in this mode)"},
    "vol_skip_pct":    {"default": 90.0, "min": 85.0, "max": 95.0, "step": 5.0,  "type": "float", "label": "Skip entries above prior-day vol percentile - OPEN 85/90/95"},
}

_OPEN_VALS = {
    "lookback": [40, 44, 48],
    "band_mult_long": [0.5, 0.75, 1.0],
    "band_mult_short": [1.25, 1.5, 1.75],
    "stop_k": [1.5, 1.75, 2.0],
    "vol_skip_pct": [85.0, 90.0, 95.0],
}

# The whole neighbourhood as one grid cell-set (243 configs), so a grid job on this
#   file sweeps exactly what the validate samples.
PARAM_GRID_PRESETS = {
    "Short  (champion neighbourhood, 243 cells)": dict(
        {k: [v] for k, v in _CHAMP.items() if k not in _OPEN_VALS}, **_OPEN_VALS
    ),
}

_BASE_ARGS = set(_inspect.signature(_base.run_backtest).parameters)


def run_backtest(opens, highs, lows, closes, **kw):
    """Entry/exit math is NOISE_1_0's, unchanged -- this file only shapes the
    search space. The champion core is applied here too, so calling this file
    with NO params reproduces the crowned SBS_V90 configuration exactly (the
    plain `run_backtest = _base.run_backtest` alias would silently fall back to
    NOISE_1_0's own signature defaults, which are a different config)."""
    p = dict(_CHAMP)
    p.update({k: v for k, v in kw.items() if k in _BASE_ARGS})
    return _base.run_backtest(opens, highs, lows, closes, **p)
