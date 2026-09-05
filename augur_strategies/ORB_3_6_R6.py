"""
ORB 3.6 — ROUND-6 CANDIDATE R6: the tighter-filter crown with re-tuned exits, searched
over its own NARROW neighbourhood (not pinned).

Round 5 found the crown's two filters (0.70 / 0.70) were never questioned and that
tightening them clears every pre-registered leg; runs #294 / #297 / #298 then PASSED
their validates (7/8 folds each, lockbox up to $105,977) — but those jobs never ran the
ES transfer leg the crown passed. Round 6 (tools/orb_hunt6.py, 2026-09-04) re-tuned the
exits UNDER the tighter filters and scored everything on the owner's two cross-strategy
reads — EV R (expectancy per average losing trade) and R / YR (EV R x trades per year):

    pinned window, NQ 5m RTH, 0.533 pts/RT, one contract
                                                EV R   R/YR    net       DD       LB       worst-12mo
    crown #234 (0.70/0.70, stop 2.0, be 1.0)   0.161  25.9  $389,874  $29,142  $88,943   -$22,051
    0.80/0.80, stop 2.5, tgt 5.5, be 0.50      0.205  27.5  $383,373  $32,529  $94,990   -$14,118
    0.75/0.80, stop 2.0, tgt 5.5, be 0.75      0.185  26.4  $382,893  $27,295  $100,739  -$14,436

Thirteen cells cleared all four legs (beat the crown on EV R and R/YR, lockbox >= crown,
worst year no worse). They all sit on one ridge: tighter filters, an earlier breakeven,
and a stop that is either the crown's or wider. This file's ranges cover that ridge so
ONE validate maps it instead of a pinned point — the walk-forward picks the cell.

WHY THE RANGES ARE OPEN (HARD RULE since v73.350): a fully pinned file records one
config and loses the parameter landscape. Five knobs carry narrow ranges centred on the
ridge; everything else is the crown's value, pinned. Judge on WF folds vs #234's 7/8, the
lockbox, and the ES transfer leg (set on the job) — the leg where round 4's two
gate-clearers died.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_r6", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 - candidate R6: tighter filters + re-tuned exits, narrow open ranges'
DESCRIPTION   = ("The #234 crown with both filters tightened (0.75-0.85) and the exits re-tuned "
                 "(stop 2.0-2.5, breakeven 0.5-1.0, target 5.0-6.5). Round-6 sweep: +27% EV R and "
                 "a better lockbox and worst year on the ridge. Narrow ranges so the validate maps "
                 "the plateau; the walk-forward and the ES transfer leg decide.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED (a spike, round 5)"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.5,  "min": 2.0,  "max": 2.5,  "step": 0.25, "type": "float", "label": "Stop (x range width) - NARROW RANGE 2.0-2.5"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close - PINNED ON (live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF"},
    "be_after_R":     {"default": 0.5,  "min": 0.5,  "max": 1.0,  "step": 0.25, "type": "float", "label": "Breakeven after (x risk) - NARROW RANGE 0.5-1.0"},
    "target_R":       {"default": 5.5,  "min": 5.0,  "max": 6.5,  "step": 0.5,  "type": "float", "label": "Target (x risk) - NARROW RANGE 5.0-6.5"},
    "atr_filter":     {"default": 0.8,  "min": 0.75, "max": 0.85, "step": 0.05, "type": "float", "label": "Vol-regime filter - NARROW RANGE 0.75-0.85"},
    "vpace_filter":   {"default": 0.8,  "min": 0.75, "max": 0.85, "step": 0.05, "type": "float", "label": "Volume-pace gate - NARROW RANGE 0.75-0.85"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays - PINNED on"},
}

# the mechanism is ORB_3_6's, untouched - this file only narrows the search space.
run_backtest = _base.run_backtest
