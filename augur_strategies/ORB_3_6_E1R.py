"""
ORB 3.6 - E1 REGION: the money direction of run #257, searched over its own neighbourhood.

WHY THIS FILE EXISTS. Run #257 is the configuration with the most walk-forward money in the
whole opening-range family ($339,110 against the control's $310,678) and the most money by
calendar year (+$25,338 over the control, +$17,138 across the four biggest years), and it is
one of the owner's starred runs. But #257 exists only as a PINNED card: its validate evaluated
one configuration, so it has no parameter landscape, no neighbours, no plateau, no PBO/DSR -
the report-completeness gap. Worse, its walk-forward number is not comparable to the crown's:
a pinned run has nothing to re-fit inside a fold, so it simply replays one configuration over
history it was chosen on, while run #314 re-fitted inside every fold and earned its $252,549
the hard way. This file puts #257's direction through the SAME hard test.

WHAT #257 CHANGES vs the control (#234). Three knobs, all in one direction - hold the trade
open wider and gate it less:

    knob                  control #234     run #257
    stop (x range width)      2.00           2.50
    breakout buffer           0.25           0.30
    vol-regime filter         0.70           0.50

Everything else is the control: opening range 2 bars, first-candle direction, confirm at the
bar close, target 5.5R, breakeven at 1.0R, volume-pace gate 0.70, flat at the close.

WHAT THE FAMILY EVIDENCE SAYS ABOUT THE DIRECTION. Walk-forward money falls in lockstep as the
filters tighten - #257/#266 at $334-339k, the control cluster at $310k, #294 $290k, #297 $276k,
#298 $262k - and the calendar years agree, including in the big years. So looser gating earns
more and tighter gating is a drawdown dial. But the direction does NOT run forever: #266, which
removes the vol-regime filter entirely, earns $6,470 LESS than #257, which merely loosens it.
That says there is an interior best somewhere between "loose" and "off", and a single pinned
point cannot show where, or how wide the plateau around it is. Six knobs carry narrow ranges
straddling #257 on both sides so the walk-forward picks the cell and the report gets its surfaces.

WHY THE RANGES ARE OPEN (HARD RULE since v73.350). A fully pinned file records one config and
loses the parameter landscape - the config-params parallel coordinates, the PDP finder, the 3-D
surfaces, knob importance, neighbours and PBO all need a population. Ranges here are deliberately
narrow and centred on #257, not a re-open of the whole space: this session's meta walk-forward
showed that re-picking opening-range parameters across the FULL space has no forward skill
(re-picking earned $166k over eleven forward years against $377k for leaving the parent defaults
alone). This is a neighbourhood map, not a hunt for a new crown.

HOW TO JUDGE IT. Walk-forward folds held against the control's 7 of 8 and the crown's 7 of 8;
walk-forward efficiency against the crown's 3.15, which is the only other number measured the
same re-fitted way; the lockbox against $88,943; and whether the plateau around #257 is broad or
whether #257 sits on a spike. A neighbour beating #257 by a few thousand dollars is NOT a reason
to move - the family's differences inside the top cluster are smaller than what selection can
manufacture.

LIVE-LEGAL BY CONSTRUCTION, inherited from ORB 3.6 unchanged: entry at a finished bar's close;
breakeven armed on a finished bar's close and acting from the next bar; stop-first and
gap-through fills; every gate reads only prior bars.

REGIME CAVEAT: 2010-2017 is flat for this family and the money is post-2018. WINDOW CAVEAT: run
this on the certified window 2010-06-07 to 2026-08-13 with a 12-month lockbox, the same window
every configuration in the ranking table was measured on, or the figures are not comparable.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_e1r", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 - E1 region: the money direction of run #257, narrow open ranges'
DESCRIPTION   = ("Run #257's direction - wider stop, bigger buffer, looser vol-regime filter - "
                 "mapped over its own neighbourhood instead of one pinned point. #257 has the most "
                 "walk-forward money and the most calendar-year money in the family but no landscape. "
                 "Judge on WF folds vs the control's 7/8 and on whether the plateau is broad.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

# Six knobs carry NARROW ranges straddling run #257; everything else is the control's value,
#   pinned. Bools need an explicit single-entry "options" list - a plain bool default is
#   ignored by the validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.50, "min": 2.25, "max": 2.75, "step": 0.25, "type": "float", "label": "Stop (x range width) - NARROW RANGE 2.25-2.75"},
    "breakout_buf":   {"default": 0.30, "min": 0.25, "max": 0.35, "step": 0.05, "type": "float", "label": "Breakout buffer - NARROW RANGE 0.25-0.35"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close - PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF (the simplification)"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF (the simplification)"},
    "be_after_R":     {"default": 1.0,  "min": 0.8,  "max": 1.2,  "step": 0.2,  "type": "float", "label": "Breakeven after (x risk) - NARROW RANGE 0.8-1.2"},
    "target_R":       {"default": 5.5,  "min": 5.0,  "max": 6.0,  "step": 0.5,  "type": "float", "label": "Target (x risk) - NARROW RANGE 5.0-6.0"},
    "atr_filter":     {"default": 0.5,  "min": 0.4,  "max": 0.6,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) - NARROW RANGE 0.4-0.6"},
    "vpace_filter":   {"default": 0.7,  "min": 0.6,  "max": 0.8,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) - NARROW RANGE 0.6-0.8"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays - PINNED on"},
}

# arm math is ORB_3_6's, unchanged - this file only narrows the search space to #257's region.
run_backtest = _base.run_backtest
