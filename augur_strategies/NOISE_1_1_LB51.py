"""
NOISE 1.1 — ROUND-6 CANDIDATE LB51: the run #243 crown with a 51-bar lookback,
searched over its own NARROW neighbourhood (not pinned).

Round-6 sweep (tools/noise_hunt6.py, 2026-09-04) scored the crown's neighbourhood on
the owner's two cross-strategy reads — EV R (expectancy per average losing trade) and
R / YR (EV R x trades per year). One cell beat the crown on BOTH and kept the lockbox
and the worst rolling year, all four pre-registered legs at once:

    lookback 44 -> 51, nothing else touched (pinned window, NQ 5m RTH, 0.533 pts/RT):
        crown #243   EV R 0.2455   R/YR 67.2   net $380,745   DD $22,096   LB $42,746   worst-12mo -$3,256
        lookback 51  EV R 0.254    R/YR 68.4   net $391,312   DD $20,802   LB $52,823   worst-12mo -$2,911

A small gain on every leg. It is the highest R / YR of any single strategy on the board
as of this sweep, which is why it earns a validation slot and nothing more.

WHY THE RANGES ARE OPEN (HARD RULE since v73.350): an Auto-Validate on a fully pinned
file records ONE config and the report loses its whole parameter landscape. So the four
knobs nearest the candidate carry real, narrow ranges centred on it — the walk-forward
searches the plateau and may crown a neighbour, which is exactly the robustness read we
want. Everything else is the crown's own value, pinned.

Judge on WF folds vs #243's 7/8, on the lockbox, and on the ES transfer leg.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "NOISE_1_0.py")
_spec = _ilu.spec_from_file_location("_noise10_lb51", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'NOISE 1.1 - candidate LB51: crown #243 with lookback 51, narrow open ranges'
DESCRIPTION   = ("The #243 crown with lookback 51 - beats the crown on EV R, R / YR, lockbox and "
                 "worst rolling year in the round-6 sweep. Ranges are narrow and centred on the "
                 "candidate so the validate maps its plateau instead of recording one point.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

DEFAULT_PARAMS = {
    "lookback":        {"default": 51,   "min": 37,   "max": 65,   "step": 7,    "type": "int",   "label": "Lookback (bars) - NARROW RANGE around 51"},
    "band_mult_long":  {"default": 0.75, "min": 0.75, "max": 0.75, "step": 0.25, "type": "float", "label": "Long band multiple - PINNED (crown)"},
    "band_mult_short": {"default": 1.5,  "min": 1.25, "max": 1.75, "step": 0.25, "type": "float", "label": "Short band multiple - NARROW RANGE around 1.5"},
    "exit_mode":       {"default": "vwap", "type": "str", "options": ["vwap"],                                    "label": "Exit - PINNED (crown)"},
    "side":            {"default": "Both", "type": "str", "options": ["Both"],                                    "label": "Side - PINNED (crown)"},
    "window":          {"default": "all_day", "type": "str", "options": ["all_day"],                              "label": "Window - PINNED (crown)"},
    "flat_eod":        {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at close - PINNED on"},
    "skip_holidays":   {"default": False, "type": "bool", "options": [False],                                     "label": "Skip holidays - PINNED off (crown)"},
    "stop_mode":       {"default": "bandwidth", "type": "str", "options": ["bandwidth"],                          "label": "Stop mode - PINNED (crown)"},
    "confirm_bars":    {"default": 1,    "min": 1,    "max": 2,    "step": 1,    "type": "int",   "label": "Confirm bars - NARROW RANGE 1-2"},
    "daytype_mode":    {"default": "skip_bot_short", "type": "str", "options": ["skip_bot_short"],                "label": "Day-type filter - PINNED (crown)"},
    "daytype_lo":      {"default": 0.2,  "min": 0.2,  "max": 0.2,  "step": 0.05, "type": "float", "label": "Day-type low - PINNED (crown)"},
    "daytype_hi":      {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.05, "type": "float", "label": "Day-type high - PINNED (crown)"},
    "vol_skip_pct":    {"default": 90.0, "min": 90.0, "max": 90.0, "step": 1.0,  "type": "float", "label": "Vol-skip percentile - PINNED (crown)"},
    "stop_k":          {"default": 1.75, "min": 1.5,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Stop k - NARROW RANGE around 1.75"},
}

# the mechanism is NOISE_1_0's, untouched - this file only narrows the search space.
run_backtest = _base.run_backtest
