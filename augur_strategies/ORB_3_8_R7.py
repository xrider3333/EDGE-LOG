"""
ORB 3.8 — ROUND-7 CANDIDATE R7: the run #314 crown plus the PRIOR-DAY LONG FILTER,
searched over its own NARROW neighbourhood (not pinned).

Round 7 (tools/orb_hunt7.py, 2026-09-05) went hunting for something to beat the freshly
crowned #314. The winner is not a new idea — it is a lead this project WROTE DOWN on
2026-08-18 and then left on the shelf. ORB.md, in its own words:

    "ORB's actually-bad population is a different one — long entries after a 0.6-0.8
     prior-day close lose $103 each over 252 trades, profit factor 0.79 — and that is a
     new, unexploited, not-yet-pre-registered lead."

It was tested once, on the #234 exit, and did not clear. Asked again on the exit that
actually got crowned, it clears everything:

    pinned window 2010-06-07..2026-08-13, NQ 5m RTH, 0.533 pts/RT, one contract
                                  5y MAR   full MAR   full DD    lockbox   worst 12mo
    crown #314                      2.79      0.85    $28,857    $87,132    -$13,608
    + skip long 0.60-0.85           2.86      1.08    $23,169   $101,684     -$9,805
    + that AND stop 3.0x            3.13      1.18    $22,442    $99,844     -$7,917

Full-window annualised MAR improves by 39 percent and the full-window drawdown falls by
22 percent, with a better worst year and a better lockbox at the same time.

WHY IT IS BELIEVABLE, and this is the part that matters. The filter is DIRECTIONAL and the
evidence respects the direction. Skipping the LONGS in that band clears the gate at every
band tested (eight of eight improve full MAR to 0.89-1.09 and the lockbox to $95k-$106k).
Skipping BOTH sides in the same band is a disaster at every band tested — full MAR 0.50 to
0.60. If this were merely "trade less", both would help. Only the side the 2026-08-18
diagnosis named is bad, which is what a real effect looks like and what a curve-fit does
not.

It is also live-legal by construction: the previous session's close position is fixed
before this session opens. Nothing here reads a bar that has not finished.

HONEST MARKS AGAINST IT. This stacks TWO levers found in the same sweep (the filter and a
wider stop), and stacking is where overfitting gets in - so the ranges below leave both
open and let the walk-forward choose, including the option of NOT widening the stop
(2.5 is in range) and of no partial. It also trades less again: about 2,010-2,038 trades
against the crown's 2,299, on top of the crown's own reduction from #234's 2,607.

DO NOT read the EV R column as the case for this. Round 6's lesson stands: the breakeven
sets the average loss, EV R's denominator. The case here is annualised MAR and drawdown,
measured on the full window AND the last five years, which is the gate this round
pre-registered before running.

WHY THE RANGES ARE OPEN (HARD RULE since v73.350): a fully pinned file records ONE config
and the report loses its parameter landscape. Five knobs carry narrow ranges centred on the
finding; everything else is the #314 crown's value, pinned.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_8.py")
_spec = _ilu.spec_from_file_location("_orb38_r7", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.8 - candidate R7: crown #314 + the prior-day long filter'
DESCRIPTION   = ("The #314 crown plus the filter ORB.md flagged unexploited on 2026-08-18: skip "
                 "LONG entries after a prior-day close inside a middling band. Full-window "
                 "annualised MAR 0.85 -> 1.08-1.18 with a 22 percent smaller drawdown and a "
                 "bigger lockbox. Directional: skipping both sides instead is a disaster, which "
                 "is why this reads as a real population and not a trade-count effect.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_8.py"

DEFAULT_PARAMS = {
    "or_bars":         {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED (a spike, round 5)"},
    "trade_mode":      {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],          "label": "Direction - PINNED"},
    "stop_frac":       {"default": 3.0,  "min": 2.5,  "max": 3.0,  "step": 0.25, "type": "float", "label": "Stop (x range width) - NARROW RANGE 2.5-3.0 (2.5 = the crown)"},
    "breakout_buf":    {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED (re-checked round 7, unmoved)"},
    "close_confirm":   {"default": True,  "type": "bool", "options": [True],                                    "label": "Confirm at bar close - PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R":  {"default": 0.0,  "min": 0.0,  "max": 4.0,  "step": 2.0,  "type": "float", "label": "Partial exit - NARROW RANGE, 0 = the crown"},
    "trail_bars":      {"default": 0,    "min": 0,    "max": 3,    "step": 3,    "type": "int",   "label": "Trailing stop - NARROW RANGE, 0 = the crown"},
    "be_after_R":      {"default": 0.5,  "min": 0.5,  "max": 0.5,  "step": 0.25, "type": "float", "label": "Breakeven after (x risk) - PINNED at the crown (do NOT search: it sets EV R's denominator)"},
    "target_R":        {"default": 5.0,  "min": 5.0,  "max": 5.0,  "step": 0.5,  "type": "float", "label": "Target (x risk) - PINNED (flat shoulder in round 6)"},
    "atr_filter":      {"default": 0.75, "min": 0.75, "max": 0.75, "step": 0.05, "type": "float", "label": "Vol-regime filter - PINNED at the crown"},
    "vpace_filter":    {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.05, "type": "float", "label": "Volume-pace gate - PINNED at the crown"},
    "daytype_mode":    {"default": "skip_band_long", "type": "str", "options": ["skip_band_long"],              "label": "Prior-day filter - PINNED to the LONG side (both-sides is a disaster, and that asymmetry is the evidence)"},
    "daytype_band_lo": {"default": 0.6,  "min": 0.55, "max": 0.65, "step": 0.05, "type": "float", "label": "Band low edge - NARROW RANGE 0.55-0.65"},
    "daytype_band_hi": {"default": 0.85, "min": 0.80, "max": 0.90, "step": 0.05, "type": "float", "label": "Band high edge - NARROW RANGE 0.80-0.90"},
    "flat_eod":        {"default": True,  "type": "bool", "options": [True],                                    "label": "Flat at the close - PINNED on"},
    "skip_holidays":   {"default": True,  "type": "bool", "options": [True],                                    "label": "Skip holidays - PINNED on"},
}

# the mechanism is ORB_3_8's, untouched - this file only narrows the search space.
run_backtest = _base.run_backtest
