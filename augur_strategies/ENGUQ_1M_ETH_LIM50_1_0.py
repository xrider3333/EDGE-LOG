"""
ENGU-Q 1m ETH · SHALLOW LIMIT 0.50 ATR — FROZEN (validate card)
-----------------------------------------------------------------
Pinned single-point fork of ENGUQ_1M_ETH_LIM_1_0.py (the shallow-limit engine) with
limit_atr fixed at 0.50 and every other knob pinned to the certified #226 ETH config.
Zero optimization: the search space is ONE point, so Auto-Validate emits exactly one
report card for this configuration and the walk-forward / lockbox grades describe the
configuration itself rather than a discovery process.

Local battery-O finding this exists to validate (research numbers, engine-path costs
0.533 pts x $20, window 2010-06-07 .. 2026-06-30, NQ 1m ETH 24h):
  limit_atr 0.00 (parity / certified #226): net $434,721 · maxDD $50,420 · PF 1.332 · LB PF 1.493
  limit_atr 0.20:                           net $466,354 · maxDD $54,011 · PF 1.358 · LB PF 1.539
  limit_atr 0.50:                           net $513,008 · maxDD $61,666 · PF 1.401 · LB PF 1.674
Profit factor rises monotonically with limit depth, which is scale-invariant and therefore
cannot be produced by simply taking more risk; drawdown also scales because entering lower
against the same swing-low stop widens per-trade risk.

Engine math is ENGUQ_1M_ETH_LIM_1_0's, untouched. This file only narrows DEFAULT_PARAMS.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_LIM_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_eth_lim_base_50", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m ETH LIMIT 0.50 FROZEN 1.0"
DESCRIPTION = ("Certified #226 ETH config with a resting limit entry 0.50 x ATR below the "
               "signal bar's close (10-bar gap-honest fill window, no fill = no trade). "
               "All knobs PINNED — one configuration, zero optimization.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_LIM_1_0.py"

# PINNED: min == max == default on every knob, so the search space is a single point.
DEFAULT_PARAMS = {
    "limit_atr":   {"default": 0.50, "min": 0.50, "max": 0.50, "step": 0.05,"type": "float", "label": "Shallow Limit Depth (x ATR) — PINNED"},
    "tl_len":      {"default": 170,  "min": 170,  "max": 170,  "step": 4,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":    {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":       {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":  {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Width (x risk) — PINNED"},
    "buf_atr":     {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":     {"default": 1.3,  "min": 1.3,  "max": 1.3,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":     {"default": 1380, "min": 1380, "max": 1380, "step": 40,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":     {"default": 106,  "min": 106,  "max": 106,  "step": 4,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":  {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
}

PARAM_GRID_PRESETS = {
    "PINNED - 226 config + limit 0.50 ATR": {
        "limit_atr":   [0.50],
        "tl_len":      [170],
        "vol_mult":    [0.8],
        "stop_mult":   [1.0],
        "act_R":       [2.5],
        "trail_frac":  [2.5],
        "buf_atr":     [0.9],
        "min_brk":     [1.3],
        "ema_len":     [1380],
        "atr_len":     [106],
        "regime_len":  [0],
        "breakeven_R": [1.5],
    }
}

run_backtest = _base.run_backtest
