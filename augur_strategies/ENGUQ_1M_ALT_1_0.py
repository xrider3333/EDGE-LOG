"""
ENGU-Q 1m ALT 1.0 — fast-trend second stream (ema90), PINNED (Auto-Validate one-point).

Second-stream candidate config: shares only ~7.1% of entries with the certified #149
champion (daily corr 0.085 vs #149) — a genuine second trade stream IF its edge is real.
Faster trend filter than #149 (ema_len 90 vs 390) and a wider trendline lookback
(tl_len 72 vs 48), looser volume gate (vol_mult 0.7), wider stop (stop_mult 1.9), and a
much wider trailing stop (trail_frac 4.0 vs 2.5).

Every knob is nailed to: tl_len 72 · vol_mult 0.7 · stop_mult 1.9 · act_R 2.5 ·
trail_frac 4.0 · buf_atr 0.4 · min_brk 1.6 · ema_len 90 · atr_len 18 · regime_len 0 off ·
breakeven_R 2.5. Mirrors the house pattern in ENGUQ_1M_149F_1_0.py: run_validate has no
"use these params" argument, so pinning the file is the only way to get the full validate
report (walk-forward folds, lockbox, blotter, OHLC) for one exact configuration.

Created 2026-08-13 for one report card. Evidence so far is thin (lockbox n=8) — the card
exists so Auto-Validate's walk-forward/lockbox machinery can put a real number on it
instead of only chat/scratchpad numbers.

CAUTION — trail_frac=4.0 is the STUCK-POSITION signature: two prior discovery champions
with trail 4.0 froze in one 449-day trade. A 2026-08-17 pre-check run of this exact config
on the NQ 1m RTH master (db_noadj_rth, ends 2026-07-16) found a 353.98-day held trade
(entry 2025-04-07, exit 2026-03-27) — well past a 120-day stuck-risk threshold, even
though the most recent entry (2026-06-25) is only 21 days before the master's end. Treat
this card's WF/lockbox numbers with that caveat: the config may not be live-deployable as
pinned even if the report card passes.

Trading logic is an EXACT copy of ENGUQ_1M_1_0.py's run_backtest (the RTH champion
engine) — imported unchanged, nothing in the engine itself touched. This file only
narrows DEFAULT_PARAMS to a single point.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_1m_base_alt", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m ALT 1.0"
DESCRIPTION = ("Pins the ALT fast-trend second-stream config (ema_len 90, tl_len 72, "
               "trail_frac 4.0) so Auto-Validate emits ONE report card. Same "
               "descending-trendline-break engine as ENGUQ_1M_1_0.py, unchanged. "
               "Created 2026-08-13 — 7.1% entry overlap with #149, thin LB evidence "
               "(n=8), so this card is the formal read on whether it's real. "
               "CAUTION: trail_frac=4.0 is the stuck-position signature — a 2026-08-17 "
               "pre-check found a 353.98-day held trade on this exact config.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_1_0.py"

# PINNED: min == max == default on every numeric knob, so the search space is a single
#   point and the crowned config is the ALT fast-trend config by construction.
#   Step values keep the UI slider widgets happy; they cannot move the value.
DEFAULT_PARAMS = {
    "tl_len":      {"default": 72,   "min": 72,   "max": 72,   "step": 1,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":    {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":   {"default": 1.9,  "min": 1.9,  "max": 1.9,  "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":       {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":  {"default": 4.0,  "min": 4.0,  "max": 4.0,  "step": 0.5, "type": "float", "label": "Trail Width (x risk) — PINNED"},
    "buf_atr":     {"default": 0.4,  "min": 0.4,  "max": 0.4,  "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":     {"default": 1.6,  "min": 1.6,  "max": 1.6,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":     {"default": 90,   "min": 90,   "max": 90,   "step": 10,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":     {"default": 18,   "min": 18,   "max": 18,   "step": 1,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":  {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R": {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
}

PARAM_GRID_PRESETS = {
    "PINNED - ALT fast-trend second-stream config": {
        "tl_len":      [72],
        "vol_mult":    [0.7],
        "stop_mult":   [1.9],
        "act_R":       [2.5],
        "trail_frac":  [4.0],
        "buf_atr":     [0.4],
        "min_brk":     [1.6],
        "ema_len":     [90],
        "atr_len":     [18],
        "regime_len":  [0],
        "breakeven_R": [2.5],
    }
}

# engine math is ENGUQ_1M_1_0's, unchanged — this file only narrows the search space.
run_backtest = _base.run_backtest
