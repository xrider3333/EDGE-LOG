"""
ENGU-Q 1m ETH - EFFICIENCY GATE 0.25 FROZEN (validate card)
------------------------------------------------------------
Pinned single-point fork of ENGUQ_1M_ETH_ER_1_0.py: every knob fixed to the certified
#226 ETH config, er_len 60, er_th 0.25, raw entry (limit_atr 0). One configuration,
zero optimization, so the walk-forward / lockbox grades describe the configuration.

Battery V/W finding this validates (2010-06-07..2026-06-30, 0.533 pts x $20):
  control: n=2843  $434,721  PF 1.332  LB  $98,488 / PF 1.493
  gated  : n=1336  $486,413  PF 1.597  LB $146,231 / PF 2.645  (top-10 share 0.78->0.70)
  PF gain holds in all 4 eras; wins 96.4% of 5,000 paired block bootstraps.
Caveats: only 67 lockbox trades; the 0.30 threshold collapses (one-sided plateau);
the pairing with the limit-0.50 entry is weaker (84.5%) so this card is the RAW entry.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_ER_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_eth_er_base", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m ETH EFFICIENCY 0.25 FROZEN 1.0"
DESCRIPTION = ("Certified #226 ETH config gated by a Kaufman efficiency-ratio floor of "
               "0.25 over the last 60 minutes, raw signal-close entry. All knobs PINNED - "
               "one configuration, zero optimization.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_ER_1_0.py"

DEFAULT_PARAMS = {
    "er_len":      {"default": 60,   "min": 60,   "max": 60,   "step": 10,  "type": "int",   "label": "Efficiency Lookback - PINNED"},
    "er_th":       {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05,"type": "float", "label": "Efficiency Floor - PINNED"},
    "limit_atr":   {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05,"type": "float", "label": "Limit Depth - PINNED off (raw entry)"},
    "tl_len":      {"default": 170,  "min": 170,  "max": 170,  "step": 4,   "type": "int",   "label": "Trendline Length - PINNED"},
    "vol_mult":    {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1, "type": "float", "label": "Volume Spike - PINNED"},
    "stop_mult":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1, "type": "float", "label": "Stop - PINNED"},
    "act_R":       {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation - PINNED"},
    "trail_frac":  {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Width - PINNED"},
    "buf_atr":     {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.05,"type": "float", "label": "Breakout Buffer - PINNED"},
    "min_brk":     {"default": 1.3,  "min": 1.3,  "max": 1.3,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness - PINNED"},
    "ema_len":     {"default": 1380, "min": 1380, "max": 1380, "step": 40,  "type": "int",   "label": "Trend EMA - PINNED"},
    "atr_len":     {"default": 106,  "min": 106,  "max": 106,  "step": 4,   "type": "int",   "label": "ATR Length - PINNED"},
    "regime_len":  {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA - PINNED off"},
    "breakeven_R": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5, "type": "float", "label": "Breakeven - PINNED"},
}

PARAM_GRID_PRESETS = {
    "PINNED - 226 config + efficiency 0.25": {k: [v["default"]] for k, v in DEFAULT_PARAMS.items()}
}

run_backtest = _base.run_backtest
