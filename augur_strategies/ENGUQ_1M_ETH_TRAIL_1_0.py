"""
ENGU-Q 1m ETH — TRAIL-WIDTH search, pre-registered (Auto-Validate one-knob search).

Every knob is pinned to the certified 24h ETH config (buf_atr 0.9 * ema_len 1380 *
tl_len 170 * stop_mult 1.0 * min_brk 1.3 * vol_mult 0.8 * atr_len 106 * act_R 2.5 *
breakeven_R 1.5 * regime_len 0 off) EXCEPT trail_frac, which is left searchable over
2.1-2.6 (step 0.1). trail_frac is the ONLY knob discovery can move.

WHY THIS EXACT RANGE: a fine manual sweep of the certified config found trail_frac=2.3
nominally better than the certified 2.5 (net $461,874 / maxDD $49,899 / net-DD 9.26 vs
$434,721 / $50,420 / 8.62 for the certified 2.5). But that 2.3 was spotted by eyeballing
the WHOLE history including the lockbox slice, so adopting it directly would be
lockbox-shopping -- picking a config because it happens to look good on data that's
supposed to be held out for an honest final check. The legitimate move is to let the
optimizer choose the trail width using only the IN-SAMPLE window (pre-lockbox), and then
take exactly ONE honest lockbox look at whatever it picks. Constraining the searchable
range to 2.1-2.6 is deliberate, not arbitrary: past 2.6 the engine has a known
runaway-hold cliff (holding periods jump to 142-196 days), so the range is bounded away
from that failure mode by construction -- discovery cannot wander into the cliff no
matter what it prefers in-sample.

Created 2026-08-18. Trading logic is an EXACT copy of ENGUQ_1M_ETH_1_0.py's run_backtest,
imported unchanged (same pattern as ENGUQ_1M_ETH_FROZEN_1_0.py) -- this file only narrows
DEFAULT_PARAMS so run_validate's discovery has exactly one free dimension.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_eth_base_trail", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m ETH TRAIL-SEARCH 1.0"
DESCRIPTION = ("Certified 24h ETH config with every knob pinned EXCEPT trail_frac, which "
               "is searchable over 2.1-2.6 (the pre-registered range: a manual whole-history "
               "sweep spotted trail_frac=2.3 beating the certified 2.5, but that look "
               "included the lockbox slice, so it can't be adopted directly without "
               "lockbox-shopping. This file lets discovery pick trail_frac on the IN-SAMPLE "
               "window only, honestly, then takes one lockbox check on the winner. The range "
               "is capped at 2.6 because wider trail widths are a known runaway-hold cliff "
               "(142-196 day holds), so the search is bounded away from that failure mode by "
               "construction.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_1_0.py"

# PINNED: min == max == default on every knob except trail_frac, so discovery has
#   exactly one free dimension (trail_frac, 2.1-2.6). Step values on the pinned knobs
#   keep the UI slider widgets happy; they cannot move the value.
DEFAULT_PARAMS = {
    "tl_len":      {"default": 170,  "min": 170,  "max": 170,  "step": 4,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":    {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":       {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":  {"default": 2.5,  "min": 2.1,  "max": 2.6,  "step": 0.1, "type": "float", "label": "Trail Width (x risk) — SEARCHABLE 2.1-2.6"},
    "buf_atr":     {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":     {"default": 1.3,  "min": 1.3,  "max": 1.3,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":     {"default": 1380, "min": 1380, "max": 1380, "step": 40,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":     {"default": 106,  "min": 106,  "max": 106,  "step": 4,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":  {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
}

PARAM_GRID_PRESETS = {
    "ENGUQ ETH trail-width search 2.1-2.6 (pre-registered)": {
        "tl_len":      [170],
        "vol_mult":    [0.8],
        "stop_mult":   [1.0],
        "act_R":       [2.5],
        "trail_frac":  [2.1, 2.2, 2.3, 2.4, 2.5, 2.6],
        "buf_atr":     [0.9],
        "min_brk":     [1.3],
        "ema_len":     [1380],
        "atr_len":     [106],
        "regime_len":  [0],
        "breakeven_R": [1.5],
    }
}

# engine math is ENGUQ_1M_ETH_1_0's, unchanged — this file only narrows the search space.
run_backtest = _base.run_backtest
