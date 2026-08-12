"""
ENGU-Q 1m ETH — FROZEN clock-scaled #149 transfer config, PINNED (Auto-Validate one-point).

Every knob is nailed to the frozen, zero-optimization clock-scaled #149 transfer config
(buf_atr 0.9 · ema_len 1380 · tl_len 170 · stop_mult 1.0 · trail_frac 2.5 · min_brk 1.3 ·
vol_mult 0.8 · atr_len 106 · act_R 2.5 · breakeven_R 1.5 · regime_len 0 off), so an
Auto-Validate on this file explores a SINGLE point and the champion it crowns IS that exact
config — no search, no drift. Mirrors the house pattern in ORB_3_1_125.py: run_validate has
no "use these params" argument, so pinning the file is the only way to get the full validate
report (walk-forward folds, lockbox, blotter, OHLC) for one exact configuration.

Created 2026-08-12. This file exists because a normal Auto-Validate on the 24h ETH tape
(run #198) let discovery roam and it crowned a config that gets STUCK in one 449-day
position — it takes ZERO lockbox trades in continuous operation and only looked like a PASS
because the engine grades the lockbox on an independent warm-start reload. Freezing the
already-known-good clock-scaled #149 config (the one ENGUQ_1M_ETH_1_0.py ships as its
default, cleared triage on NQ 1m ETH db_noadj_eth <=2026-06-30: n=2843, net=$434,721.12,
PF=1.33 — see that file's docstring and tools/paper_forward.py's ENGUQ_1M leg) sidesteps
that discovery artifact entirely and gets a real report card for the config the owner
actually wants graded.

Trading logic is an EXACT copy of ENGUQ_1M_ETH_1_0.py's run_backtest — imported unchanged,
nothing in the engine itself touched. This file only narrows DEFAULT_PARAMS to a single point.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_eth_base_frozen", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m ETH FROZEN 1.0"
DESCRIPTION = ("Pinned to the clock-scaled #149 transfer config (frozen, zero optimization) "
               "so Auto-Validate emits ONE report card for exactly this configuration. Same "
               "descending-trendline-break engine as ENGUQ_1M_ETH_1_0.py, unchanged. Exists "
               "because discovery on the 24h ETH tape (run #198) produced a stuck-position "
               "artifact (one 449-day trade, zero lockbox trades in continuous operation) "
               "that only passed because the lockbox grade came from an independent "
               "warm-start reload.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_1_0.py"

# PINNED: min == max == default on every numeric knob, so the search space is a single
#   point and the crowned config is the frozen clock-scaled #149 transfer config by
#   construction. Step values keep the UI slider widgets happy; they cannot move the value.
DEFAULT_PARAMS = {
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
    "PINNED - frozen clock-scaled 149": {
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

# engine math is ENGUQ_1M_ETH_1_0's, unchanged — this file only narrows the search space.
run_backtest = _base.run_backtest
