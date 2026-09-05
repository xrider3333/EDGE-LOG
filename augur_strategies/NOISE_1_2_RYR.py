"""
NOISE 1.2 RYR — R / YR NEIGHBOURHOOD (fenced search around the R / YR 102 plateau).

WHY THIS FILE EXISTS. The owner ranks on EV R = (1 - win%) x (PF - 1) and R / YR =
EV R x trades per year (app v73.460). Auto-Validate crowns on the house MAR rule, so
the R / YR leaders sit UNCROWNED inside passed runs - `tools/mine_ryr_frontier.py`
measured that across the whole Past Runs population. An R / YR-objective random search
over NOISE_1_0's own declared ranges (`tools/ryr_search.py`, 600 configs, NQ 5m RTH,
2010-06-07..2025-06-29, cost 0.533) found this region, which no NOISE run has crowned:

    n = 5,548 · PF 1.325 · win 14.3% · net $146,392 · DD $16,345 · MAR 8.96
    EV R 0.279 · 368 trades/yr · R / YR 102.6 · 7 of 8 chronological slices positive

That is the highest R / YR of any single NOISE configuration measured (the crowned
SBS_V90 geometry scores 74-77). It gets there by trading FAR more often - 368 a year
against the crown's 232 - at a lower profit factor, which is exactly the trade the
R / YR metric is designed to price.

IT IS A PLATEAU, NOT A SPIKE (`tools/ryr_neighbourhood.py`, one grid step either side of
every ranged knob, 30 neighbours): median neighbour R / YR 100.9 against the leader's
102.6, 29 of 30 keep PF >= 1.25, 28 of 30 keep 6+ of 8 slices positive. Only the
short-only side collapses (30.0), which is why `side` stays pinned to Both.

THE ENTRY WINDOW IS LEFT OPEN ON PURPOSE. It is the knob that moves this the most and
the two directions disagree about which is better: `all_day` measured R / YR 154.5 but
only 5 of 8 slices, `afternoon_block` 142.5 at 6 of 8, the centre `morning` 102.6 at 7
of 8. More trades, less consistency. That is a judgement the walk-forward folds should
make, not the sweep - so all three are in the space and the validate picks.

WHAT IS OPEN: entry window (3), noise lookback (3), the two band widths (3 each), and
the stop size (3) = 3^5 = 243 cells. Everything else is PINNED at the plateau centre.
The report therefore still carries a real landscape (points, PDP, parallel coordinates,
surfaces, knob importance, PBO over a pool this configuration belongs to).

READ THE PBO HONESTLY: a tight neighbourhood should read a LOWER overfit probability
than a wide-open search, because the in-sample best is far less likely to be a lucky
outlier among near-identical siblings. That is a statement about THIS selection, not a
number to quote against run #237's free-discovery 0.60. Report both.

LOCKBOX HONESTY, CARRIED FORWARD from NOISE_1_1_NBHD.py: the NOISE family lockbox is
SPENT - read on runs 202/203, the 2026-08-11 gate test, #225/#231/#243, #302, #305.
Every lockbox figure this run prints is CONFIRMATORY ONLY and can never promote NOISE.
The walk-forward folds and forward paper data are the real judges.

Entry/exit math is NOISE_1_0.py's, unchanged. This file only shapes the search space -
it adds no rule and changes no calculation.
"""
import importlib.util as _ilu
import inspect as _inspect
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "NOISE_1_0.py")
_spec = _ilu.spec_from_file_location("_noise10_base_ryr", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'NOISE 1.2 RYR - R / YR neighbourhood (368 trades a year plateau)'
DESCRIPTION = ("The R-per-year frontier region of NOISE on NQ 5m: many more trades at a "
               "lower profit factor than the crowned geometry. Entry window, lookback, both "
               "band widths and the stop are open across the measured plateau.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

# The R / YR search leader (plateau centre).
_CENTRE = {
    "lookback": 24, "band_mult_long": 0.75, "band_mult_short": 1.5,
    "exit_mode": "boundary", "side": "Both", "window": "morning",
    "flat_eod": True, "skip_holidays": True,
    "stop_mode": "bandwidth", "stop_k": 1.0, "confirm_bars": 1,
    "daytype_mode": "off", "daytype_lo": 0.25, "daytype_hi": 0.7,
    "vol_skip_pct": 82.0,
}

_OPEN_VALS = {
    "window": ["all_day", "morning", "afternoon_block"],   # 154.5 / 102.6 / 142.5 - folds disagree
    "lookback": [20, 24, 28],
    "band_mult_long": [0.5, 0.75, 1.0],
    "band_mult_short": [1.25, 1.5, 1.75],
    "stop_k": [0.75, 1.0, 1.25],
}

DEFAULT_PARAMS = {
    "lookback":        {"default": 24,   "min": 20,   "max": 28,   "step": 4,    "type": "int",   "label": "Noise lookback (sessions) - OPEN 20/24/28"},
    "band_mult_long":  {"default": 0.75, "min": 0.5,  "max": 1.0,  "step": 0.25, "type": "float", "label": "Upper band width (x noise) - OPEN 0.50/0.75/1.00"},
    "band_mult_short": {"default": 1.5,  "min": 1.25, "max": 1.75, "step": 0.25, "type": "float", "label": "Lower band width (x noise) - OPEN 1.25/1.50/1.75"},
    "exit_mode":       {"default": "boundary", "type": "str", "options": ["boundary"],            "label": "Exit rule - PINNED to the band boundary (vwap scored 44, band 64)"},
    "side":            {"default": "Both", "type": "str", "options": ["Both"],                    "label": "Direction - PINNED (short-only collapses to 30)"},
    "window":          {"default": "morning", "type": "str", "options": ["all_day", "morning", "afternoon_block"], "label": "Entry window - OPEN, the folds decide"},
    "flat_eod":        {"default": True,  "type": "bool", "options": [True],                      "label": "Flat by session close - PINNED on"},
    "skip_holidays":   {"default": True,  "type": "bool", "options": [True],                      "label": "Skip holiday half-days - PINNED on (plateau centre)"},
    "stop_mode":       {"default": "bandwidth", "type": "str", "options": ["bandwidth"],          "label": "Protective stop - PINNED to bandwidth"},
    "stop_k":          {"default": 1.0,  "min": 0.75, "max": 1.25, "step": 0.25, "type": "float", "label": "Stop size (x band excursion) - OPEN 0.75/1.00/1.25"},
    "confirm_bars":    {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Entry confirmation - PINNED off"},
    "daytype_mode":    {"default": "off", "type": "str", "options": ["off"],                      "label": "Prior-day close-position filter - PINNED off (every filter scored lower here)"},
    "daytype_lo":      {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Bottom close-position threshold - PINNED (unused when the filter is off)"},
    "daytype_hi":      {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.05, "type": "float", "label": "Top close-position threshold - PINNED (unused when the filter is off)"},
    "vol_skip_pct":    {"default": 82.0, "min": 82.0, "max": 82.0, "step": 1.0,  "type": "float", "label": "Skip entries above prior-day vol percentile - PINNED (plateau centre)"},
}

PARAM_GRID_PRESETS = {
    "Short  (R / YR neighbourhood, 243 cells)": dict(
        {k: [v] for k, v in _CENTRE.items() if k not in _OPEN_VALS}, **_OPEN_VALS
    ),
}

_BASE_ARGS = set(_inspect.signature(_base.run_backtest).parameters)


def run_backtest(opens, highs, lows, closes, **kw):
    """Entry/exit math is NOISE_1_0's, unchanged - this file only shapes the search
    space. The plateau centre is applied here too, so calling this file with NO params
    reproduces the R / YR search leader exactly rather than falling back to NOISE_1_0's
    own signature defaults, which are a different configuration."""
    p = dict(_CENTRE)
    p.update({k: v for k, v in kw.items() if k in _BASE_ARGS})
    return _base.run_backtest(opens, highs, lows, closes, **p)
