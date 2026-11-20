"""
ORB OR15 1.0 - the ORB #314 mechanism (ORB_3_6.py core, run #314's file ORB_3_6_R6.py) with a 15-MINUTE opening range
(or_bars 3 on NQ 5m) instead of #314's 10 minutes (or_bars 2). Family ORB.

ORIGIN (w132 alpha hunt, lane ORB, 2026-11-20): W132_ALPHA.md leg RR_Q156_OR_15_min___314_exits ($39,988/yr, book +1
$180,321/yr, corr 0.55, one-episode warning). Harness: C:/EdgeLog/_anatomy_cache/t242_orb/w132r2/q156_r2.py, line 2
cell "OR 15 min, #314 exits" = run_backtest(ORB_3_6_R6.py, params = #314's validate champion with or_bars=3), NQ 5m RTH
no-adj, 2010-06-07..2025-06-30, cost 0.783 pts/RT. Leg CSV:
C:/EdgeLog/manager/reports/w132_orb_legs/RR_Q156_OR_15_min___314_exits.csv.
Prereg C:/EdgeLog/manager/prereg/PREREG_orb_or15_validate_2026-11-20.md.

WHAT THIS IS
  ORB_3_6.py's core loop UNCHANGED. Harness point = #314's champion knobs with or_bars 3:
      or_bars 3, stop_frac 2.5, breakout_buf 0.25, be_after_R 0.5, target_R 5.0, atr_filter 0.75, vpace_filter 0.8,
      close_confirm on, first-candle direction, no partial, no trail, flat at the close, skip holidays.
  DEFAULT_PARAMS defaults = that point. Ranges = ORB_3_6_R6.py's five open knobs (same ranges) PLUS or_bars ranged 2-4,
  so the 900-trial search tunes the opening-range length too (2 = #314's own 10-minute range).

NO LOOK-AHEAD: inherited from ORB_3_6 (entry on a finished bar's close; v-pace reads bars before the break bar and prior
sessions only; vol-regime and holiday gates use prior sessions / session length; BE arms on a close and acts next bar).
No ADJ levels are used, so no ROLL_SIGNAL is declared - same as ORB_3_6_R6.py.
"""
# AUGUR-SOURCE: claude-review
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_or15", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ORB OR15 1.0 - #314 mechanism, 15-minute opening range"
DESCRIPTION = ("ORB #314's close-confirm breakout (first-candle direction, breakeven after R, hard target, v-pace + "
               "vol-regime gates) with a 3-bar (15-minute) opening range on NQ 5m. Defaults = the w132 Q156 harness "
               "leg; R6's five knobs plus or_bars 2-4 ranged for the validate.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars":        {"default": 3,    "min": 2,    "max": 4,    "step": 1,    "type": "int",   "label": "Opening range (5m bars) - RANGE 2-4 (10-20 min)"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.5,  "min": 2.0,  "max": 2.5,  "step": 0.25, "type": "float", "label": "Stop (x range width) - NARROW RANGE 2.0-2.5"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close - PINNED ON (live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF"},
    "be_after_R":     {"default": 0.5,  "min": 0.5,  "max": 1.0,  "step": 0.25, "type": "float", "label": "Breakeven after (x risk) - NARROW RANGE 0.5-1.0"},
    "target_R":       {"default": 5.0,  "min": 5.0,  "max": 6.5,  "step": 0.5,  "type": "float", "label": "Target (x risk) - NARROW RANGE 5.0-6.5"},
    "atr_filter":     {"default": 0.75, "min": 0.75, "max": 0.85, "step": 0.05, "type": "float", "label": "Vol-regime filter - NARROW RANGE 0.75-0.85"},
    "vpace_filter":   {"default": 0.8,  "min": 0.75, "max": 0.85, "step": 0.05, "type": "float", "label": "Volume-pace gate - NARROW RANGE 0.75-0.85"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays - PINNED on"},
}

# the mechanism is ORB_3_6's, untouched - this file only sets the opening-range default and the search space.
run_backtest = _base.run_backtest
