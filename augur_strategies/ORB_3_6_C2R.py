# AUGUR-SOURCE: claude-review
"""
ORB 3.6 - C2 REGION: run #234's card (ride + breakeven), searched over its own neighbourhood.

WHY THIS FILE EXISTS. Run #234 (ORB_3_6_C2.py) is the book's ORB slot, but it is a PINNED
card: its validate evaluated one configuration, so its walk-forward simply replays one config
over history it was chosen on. The book has been using the family ratio 0.837 as a stand-in
haircut for that. This file gives #234 a real tuned walk-forward: the optimizer re-fits inside
every fold, the same way run #421 (ORB_3_6_E1R.py) did for #257's card.

SEARCH SPACE = ORB_3_6_E1R.py's, recentred on #234. Same six open knobs, same widths, same
steps (one step either side of the card), everything else pinned at the card's values. That
makes the #234 and #257 haircuts measured on identically shaped spaces (3x3x3x3x3x3 = 729 cells).

    knob             card #234    range
    stop_frac          2.00       1.75-2.25 step 0.25
    breakout_buf       0.25       0.20-0.30 step 0.05
    be_after_R         1.0        0.8-1.2   step 0.2
    target_R           5.5        5.0-6.0   step 0.5
    atr_filter         0.7        0.6-0.8   step 0.1
    vpace_filter       0.7        0.6-0.8   step 0.1

EXIT LOGIC unchanged: ORB_3_6's run_backtest, ride to target with breakeven, no partial, no
trail, flat at the close. At the defaults this file IS ORB_3_6_C2.py.

LIVE-LEGAL BY CONSTRUCTION, inherited from ORB 3.6: entry at a finished bar's close; breakeven
armed on a finished bar's close and acting from the next bar; stop-first and gap-through fills;
every gate reads only prior bars.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_c2r", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 - C2 region: run #234 card, narrow open ranges (tuned WF)'
DESCRIPTION   = ("Run #234's card (ride to 5.5R, breakeven 1.0R, filters 0.7/0.7) mapped over its "
                 "own neighbourhood with E1R's search shape, so the walk-forward re-fits inside "
                 "every fold. Purpose: the real tuned-WF haircut for the book's ORB slot.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.0,  "min": 1.75, "max": 2.25, "step": 0.25, "type": "float", "label": "Stop (x range width) - NARROW RANGE 1.75-2.25"},
    "breakout_buf":   {"default": 0.25, "min": 0.20, "max": 0.30, "step": 0.05, "type": "float", "label": "Breakout buffer - NARROW RANGE 0.20-0.30"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close - PINNED ON (live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF"},
    "be_after_R":     {"hard_min": 0.8, "default": 1.0,  "min": 0.8,  "max": 1.2,  "step": 0.2,  "type": "float", "label": "Breakeven after (x risk) - NARROW RANGE 0.8-1.2"},
    "target_R":       {"default": 5.5,  "min": 5.0,  "max": 6.0,  "step": 0.5,  "type": "float", "label": "Target (x risk) - NARROW RANGE 5.0-6.0"},
    "atr_filter":     {"default": 0.7,  "min": 0.6,  "max": 0.8,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) - NARROW RANGE 0.6-0.8"},
    "vpace_filter":   {"default": 0.7,  "min": 0.6,  "max": 0.8,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) - NARROW RANGE 0.6-0.8"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays - PINNED on"},
}

# arm math is ORB_3_6's, unchanged - this file only opens #234's neighbourhood.
run_backtest = _base.run_backtest
