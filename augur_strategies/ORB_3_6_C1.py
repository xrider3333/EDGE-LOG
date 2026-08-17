"""
ORB 3.6 — HUNT CANDIDATE 1, PINNED: the run #230 champion + breakeven at 1.0R.

2026-08-17 hunt result. The #230 grail (ORB_3_4_C221) was never offered the breakeven
lever because its base file lacks the knob; ORB_3_6.py adds it (armed on a finished
bar's CLOSE, acts from the NEXT bar — live-legal, same argument as the entry).

Measured on the harness (tools/orb_hunt.py, NQ 5m RTH no-adj, 0.533 pts/RT all-in,
1 contract), against the #230 champion on identical trades (n=2607 both):

                       net        PF     maxDD     MAR
    #230 champion   $348,129    1.263   $35,474    9.81
    + be 1.0R       $363,867    1.286   $28,501   12.77   (+$15.7k, DD -20%, MAR +30%)

Why 1.0R and not the sweep's LB-best 0.8: picking 0.8 for its lockbox reading IS
lockbox-peeking. 1.0 is the center of the plateau (0.8-1.2 all improve MAR to ~12.2-
12.8), it is the value the old (voided-base) study pre-registered and validated, and
it posts the best FULL DD/MAR anyway. Evidence of a real lever, not a fit:
  * plateau, not spike: be 0.8 / 1.0 / 1.2 within 4% of each other on FULL MAR;
  * helps 7 of 8 config NEIGHBORS (stop 1.5/1.75, trail 5, partial 2.5, target 5.0,
    buf 0.20; or_bars 3 neutral) — a curve-fit lever helps only its own point;
  * year-by-year: improvement is spread (2016 -$9.7k->-$7.8k, 2020 -$9.5k->-$9.6k~,
    2024 -$4.0k->+$4.3k, 2026 +$47.8k->+$57.3k), not one lucky year;
  * same 2607 trades — pure exit modification, no selection change.

REGIME CAVEAT unchanged from #230: 2010-2017 is flat; the money is post-2018.

Every knob pinned single-point so an Auto-Validate crowns THIS config by construction.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_c1", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 · hunt candidate 1 (be 1.0R), pinned'
DESCRIPTION   = ("The run #230 grail config plus breakeven-at-1.0R (armed on bar close, "
                 "acts next bar - live-legal). Same 2,607 trades, net +$15.7k, drawdown "
                 "-20%, MAR +30% vs #230. Every knob pinned; validating this file IS "
                 "validating that one config.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

# PINNED: min == max on every numeric knob, one option on every categorical. Bools need
#   an explicit single-entry "options" list — a plain bool default is ignored by the
#   validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction — PINNED"},
    "stop_frac":      {"default": 2.0,  "min": 2.0,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 3.0,  "min": 3.0,  "max": 3.0,  "step": 0.5,  "type": "float", "label": "Partial exit (× risk) — PINNED"},
    "trail_bars":     {"default": 3,    "min": 3,    "max": 3,    "step": 1,    "type": "int",   "label": "Trailing stop (bars) — PINNED"},
    "be_after_R":     {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk) — PINNED at the plateau center"},
    "target_R":       {"default": 5.5,  "min": 5.5,  "max": 5.5,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED"},
    "atr_filter":     {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) — PINNED"},
    "vpace_filter":   {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) — PINNED"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays — PINNED on"},
}

# arm math is ORB_3_6's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
