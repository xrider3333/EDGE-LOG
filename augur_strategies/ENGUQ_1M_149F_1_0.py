"""
ENGU-Q 1m 149 FROZEN — CERTIFIED #149 DEPLOY CONFIG, PINNED (Auto-Validate one-point).

Every knob is nailed to the certified #149 deploy config (buf_atr 0.9 · ema_len 390 ·
tl_len 48 · stop_mult 1.0 · trail_frac 2.5 · min_brk 1.3 · vol_mult 0.8 · atr_len 30 ·
act_R 2.5 · breakeven_R 1.5 · regime_len 0 off), so an Auto-Validate on this file
explores a SINGLE point and the champion it crowns IS #149 by construction — no
search, no drift. Mirrors the house pattern in ORB_3_1_125.py and
ENGUQ_1M_ETH_FROZEN_1_0.py: run_validate has no "use these params" argument, so
pinning the file is the only way to get the full validate report (walk-forward
folds, lockbox, blotter, OHLC) for one exact configuration.

Created 2026-08-12. This file exists so the honest #149 baseline — re-scored on the
fresher master (now ending 2026-07-16) — has a real, visible run card in
RESULTS ▸ Past-Runs instead of only existing in chat/scratchpad numbers.

Trading logic is an EXACT copy of ENGUQ_1M_1_0.py's run_backtest (the RTH champion
engine) — imported unchanged, nothing in the engine itself touched. This file only
narrows DEFAULT_PARAMS to a single point (the same numeric values already documented
as NQ_DEPLOY_PARAMS_149 in ENGUQ_1M_1_0.py).
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_1m_base_149f", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m 149 FROZEN 1.0"
DESCRIPTION = ("Pins the certified #149 deploy config (frozen, zero optimization) so "
               "Auto-Validate emits ONE report card — the visible baseline. Same "
               "descending-trendline-break engine as ENGUQ_1M_1_0.py, unchanged. "
               "Created 2026-08-12 so the honest re-scored #149 baseline exists as a "
               "real run card in Past-Runs instead of only chat/scratchpad numbers.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_1_0.py"

# PINNED: min == max == default on every numeric knob, so the search space is a single
#   point and the crowned config is the certified #149 deploy config by construction.
#   Step values keep the UI slider widgets happy; they cannot move the value.
DEFAULT_PARAMS = {
    "tl_len":      {"default": 48,   "min": 48,   "max": 48,   "step": 1,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":    {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":       {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":  {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Width (x risk) — PINNED"},
    "buf_atr":     {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":     {"default": 1.3,  "min": 1.3,  "max": 1.3,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":     {"default": 390,  "min": 390,  "max": 390,  "step": 10,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":     {"default": 30,   "min": 30,   "max": 30,   "step": 1,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":  {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
}

PARAM_GRID_PRESETS = {
    "PINNED - certified #149 deploy config": {
        "tl_len":      [48],
        "vol_mult":    [0.8],
        "stop_mult":   [1.0],
        "act_R":       [2.5],
        "trail_frac":  [2.5],
        "buf_atr":     [0.9],
        "min_brk":     [1.3],
        "ema_len":     [390],
        "atr_len":     [30],
        "regime_len":  [0],
        "breakeven_R": [1.5],
    }
}

# engine math is ENGUQ_1M_1_0's, unchanged — this file only narrows the search space.
run_backtest = _base.run_backtest
