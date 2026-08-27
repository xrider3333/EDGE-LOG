"""
ENGU-Q 1m ETH — frozen #149 config with the RE-ENTRY COOLDOWN as the only free knob.

Everything is pinned to the deployed frozen clock-scaled #149 transfer config
(buf_atr 0.9 · ema_len 1380 · tl_len 170 · stop_mult 1.0 · trail_frac 2.5 · min_brk 1.3 ·
vol_mult 0.8 · atr_len 106 · act_R 2.5 · breakeven_R 1.5 · regime_len 0 off) EXCEPT
`cooldown_bars`, which sweeps 3..8. The search space is therefore one-dimensional and six
points wide: Auto-Validate crowns a cooldown length and nothing else can drift underneath
it.

WHY THIS FILE EXISTS (2026-08-26). Owner item 896: "no strategy should be messing up by
taking 5 trades in a row like that." Battery V (tools/enguq_cooldown_test.py) measured a
cooldown on the standalone harness and it cleared 5 of 5 pre-registered gates — the first
ENGU-Q filter of any kind to do so. Two robustness checks
(tools/enguq_cooldown_robust.py) said it is not a fluke:

  * PLATEAU, not a spike — every value from 3 to 8 bars lands together: net +$16.7k..
    +$21.9k, PF 1.350-1.355, lockbox PF 1.604-1.612. 1-2 are too short to bind, 9-12 fall
    back to control.
  * NOT MONSTER-DEPENDENT — the improvement is exactly +$18,263 whether you drop the best
    1 or the best 3 trades from BOTH sides, i.e. the top trades are identical in the two
    runs. That matters because ENGUQ.md §1.1 shows the top 10 winners are 83% of all net,
    so "kept one more monster" is the obvious way a result like this would be fake. The
    entire gain comes from deleting ~31 clustered net-negative trades.

Owner 2026-08-26, on being shown that: "yes run the validate job on 3-8". Hence 3..8 here
rather than the wider battery-V grid — the plateau is the hypothesis under test, and the
cells outside it (15/30/60/120/240) already scored 3/5, 3/5, 4/5, 4/5 and 1/5.

THE STANDALONE HARNESS IS NOT A VALIDATE. tools/enguq_cooldown_test.py computes PF, a
lockbox slice and a drawdown on one pass. It does NOT do walk-forward folds, the PBO gate,
the consistency-slice count, or an independent warm-start lockbox reload. That is exactly
the difference that caught run #167 (sharpest in-sample config, lockbox collapse) and the
ETH discovery artifact that made ENGUQ_1M_ETH_FROZEN_1_0.py necessary. Nothing gets
crowned off the standalone number.

Trading logic is an EXACT copy of ENGUQ_1M_ETH_1_0.py's run_backtest — imported unchanged.
This file only narrows the search space. Note `freeze_overnight` is absent and defaults
False, so this strategy needs no bar timestamps and is unaffected by the grid path's
missing `index` (memory: edgelog-grid-path-no-index).
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_eth_base_cooldown", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m ETH COOLDOWN 1.0"
DESCRIPTION = ("Frozen clock-scaled #149 ETH config with ONE free knob: cooldown_bars, the "
               "re-entry cooldown from owner item 896, swept 3-8 (the measured plateau). "
               "After a trade closes the strategy ignores entry signals for that many 1m "
               "bars. Everything else is pinned to the deployed config, so an Auto-Validate "
               "on this file grades the cooldown and nothing else. Battery V scored the "
               "5-bar cell 5/5 with the lockbox rising $98,488 -> $112,591 and PF "
               "1.332 -> 1.352; this run is what decides whether that survives walk-forward "
               "folds and an independent lockbox.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_1_0.py"

# Every knob min == max == default EXCEPT cooldown_bars. Step values keep the UI slider
# widgets happy; on the pinned rows they cannot move the value.
DEFAULT_PARAMS = {
    "tl_len":       {"default": 170,  "min": 170,  "max": 170,  "step": 4,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":     {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":    {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":        {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":   {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Width (x risk) — PINNED"},
    "buf_atr":      {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":      {"default": 1.3,  "min": 1.3,  "max": 1.3,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":      {"default": 1380, "min": 1380, "max": 1380, "step": 40,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":      {"default": 106,  "min": 106,  "max": 106,  "step": 4,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":   {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R":  {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
    # THE ONE FREE KNOB. Range is the measured plateau, not a guess.
    "cooldown_bars": {"default": 5,   "min": 3,    "max": 8,    "step": 1,   "type": "int",   "label": "Re-entry cooldown (bars) — THE VARIABLE, 3-8"},
}

PARAM_GRID_PRESETS = {
    "COOLDOWN SWEEP 3-8 (battery V plateau)": {
        "tl_len":       [170],
        "vol_mult":     [0.8],
        "stop_mult":    [1.0],
        "act_R":        [2.5],
        "trail_frac":   [2.5],
        "buf_atr":      [0.9],
        "min_brk":      [1.3],
        "ema_len":      [1380],
        "atr_len":      [106],
        "regime_len":   [0],
        "breakeven_R":  [1.5],
        "cooldown_bars": [3, 4, 5, 6, 7, 8],
    },
    # The control belongs in the same file so a single run can show the cooldown against
    # cooldown-off on identical data, rather than being compared to a number in a doc.
    "CONTROL - cooldown OFF (deployed)": {
        "tl_len":       [170],
        "vol_mult":     [0.8],
        "stop_mult":    [1.0],
        "act_R":        [2.5],
        "trail_frac":   [2.5],
        "buf_atr":      [0.9],
        "min_brk":      [1.3],
        "ema_len":      [1380],
        "atr_len":      [106],
        "regime_len":   [0],
        "breakeven_R":  [1.5],
        "cooldown_bars": [0],
    },
}

# engine math is ENGUQ_1M_ETH_1_0's, unchanged — this file only narrows the search space.
run_backtest = _base.run_backtest
