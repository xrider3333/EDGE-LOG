"""
ORB 3.6 - BE08 REGION: run #239's neighbourhood, searched instead of pinned. (2026-09-30)

WHY THIS FILE EXISTS. Run #239 is the ORB control (#234) with one change: the breakeven trigger moves from
1.0 to 0.8 of the risk. Round 63 (ORB_ROUND63_BOOK463_LEG.md) found it is the only ORB leg that clears the
pre-registered bar inside the adopted BOOK #463 - walk-forward ROC at a $30k daily-valued drawdown 101.9 vs
94.0 %/yr, lockbox 158.7 vs 155.5, Sortino better in both - and the Frontier lane reproduced that to the
cent (run #478). The owner's call (2026-09-30) is SHADOW FIRST: #239 goes on paper as ORB_239.

But #239's only validate is a PINNED card (one configuration evaluated), so its walk-forward figure is an
in-sample replay, not a test, and its report has no landscape. The owner asked (2026-09-30) that anything
promising go through the house Auto-Validate. This file fences narrow OPEN ranges around #239 so one
validate re-fits the region inside every walk-forward fold - the hard test only #314 and #421 have faced -
and restores section 2 (parameter landscape, neighbours, plateau, PBO/DSR) for a paper-traded leg.

WHAT TO EXPECT, stated first. Run #421 did the same for #257's region: the region held up, but the cell it
crowned (an edge-of-range early breakeven) won the tuning years and lost $33k in the lockbox against the
frozen card. Re-tuning ORB has no forward skill (meta walk-forward: $166k vs $377k for the defaults). So
this run is read for the REGION - folds held, re-fitted walk-forward ROC at $30k against #314's 21.7 and
#421's 22.4, plateau width, PBO - and a crowned cell that differs from #239 is NOT a candidate. ORB_239 on
paper stays the frozen #239 cell whatever this run crowns.

Six knobs carry narrow ranges straddling #239 on both sides (3 x 3 x 3 x 3 x 3 x 3 = 729 cells, inside the
900-trial budget); everything else is the control's value, pinned. Defaults reproduce #239 exactly:
2,607 trades, $394,864.38; lockbox 178 trades, $94,267.52, PF 1.4949.

LIVE-LEGAL BY CONSTRUCTION, inherited from ORB 3.6 unchanged: entry at a finished bar's close; breakeven
armed on a finished bar's close and acting from the next bar; stop-first and gap-through fills; every gate
reads only prior bars. Run it on the certified window 2010-06-07 to 2026-08-13 with a 12-month lockbox.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_be08r", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 - BE08 region: run #239 neighbourhood, narrow open ranges'
DESCRIPTION   = ("Run #239 (the control with breakeven at 0.8R) mapped over its own neighbourhood instead of "
                 "one pinned point, so its walk-forward is re-fitted in every fold. Read for the region, not "
                 "for a new crown; the paper leg stays the frozen #239 cell.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

# Six knobs carry NARROW ranges straddling run #239; everything else is the control's value, pinned.
#   Bools need an explicit single-entry "options" list - a plain bool default is ignored by the
#   validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.0,  "min": 1.75, "max": 2.25, "step": 0.25, "type": "float", "label": "Stop (x range width) - NARROW RANGE 1.75-2.25"},
    "breakout_buf":   {"default": 0.25, "min": 0.20, "max": 0.30, "step": 0.05, "type": "float", "label": "Breakout buffer - NARROW RANGE 0.20-0.30"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close - PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF"},
    "be_after_R":     {"default": 0.8,  "min": 0.6,  "max": 1.0,  "step": 0.2,  "type": "float", "label": "Breakeven after (x risk) - NARROW RANGE 0.6-1.0"},
    "target_R":       {"default": 5.5,  "min": 5.0,  "max": 6.0,  "step": 0.5,  "type": "float", "label": "Target (x risk) - NARROW RANGE 5.0-6.0"},
    "atr_filter":     {"default": 0.7,  "min": 0.65, "max": 0.75, "step": 0.05, "type": "float", "label": "Vol-regime filter (trailing) - NARROW RANGE 0.65-0.75"},
    "vpace_filter":   {"default": 0.7,  "min": 0.65, "max": 0.75, "step": 0.05, "type": "float", "label": "Volume-pace gate (pre-fill bars only) - NARROW RANGE 0.65-0.75"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays - PINNED on"},
}

# arm math is ORB_3_6's, unchanged - this file only narrows the search space to #239's region.
run_backtest = _base.run_backtest
