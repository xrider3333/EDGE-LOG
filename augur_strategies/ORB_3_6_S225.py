"""
ORB 3.6 — PLATEAU NEIGHBOUR OF RUN #234: stop 2.25x.

Run #234 (ORB_3_6_C2.py) crowned ride+BE at be 1.0R / target 5.5R / stop 2.0. Its
neighbours were only ever measured OFFLINE, where walk-forward does not exist. Owner
2026-08-17: "auto validate these ... WF is our judge". So each neighbour gets its own
pinned file and its own full validate, and the plateau gets mapped on WF folds rather
than on a net-dollar column.

This file = run #234's config with ONE knob moved: stop 2.25x.

Offline reading (NQ 5m RTH no-adj, 0.533 pts/RT, 1 contract, run #230's window):
    full-history net $378,708  ·  lockbox $82,171  ·  net/DD 11.11
    (#234 itself: $389,874  ·  $88,943  ·  13.38)

Those are OFFLINE numbers with NO walk-forward. Do not rank on them — that is exactly
the mistake this run exists to avoid. The verdict is the WF fold count + wfe this run
produces, read against #234's 7/8 and wfe 4.649.

CAVEAT on every row: the 2025-08-13..2026-08-13 lockbox has been read many times across
this program, so its dollars are encouraging, not confirmatory. REGIME CAVEAT unchanged:
2010-2017 flat, all the money is post-2018.

LIVE-LEGAL BY CONSTRUCTION: entry at a finished bar's close; BE armed on a finished
bar's close and acting from the next bar; stop-first + gap-through fills; every gate
reads only prior bars. Nothing on any fill bar is read before it exists.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_s225", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 · #234 neighbour — stop 2.25x, pinned'
DESCRIPTION   = ("Run #234's ride+BE config with ONE knob moved: stop 2.25x. Pinned to a "
                 "single point so the validate maps the plateau on WALK-FORWARD rather "
                 "than on an offline net-dollar column. Judge on WF folds vs #234's 7/8.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

# PINNED: min == max on every numeric knob, one option on every categorical. Bools need
#   an explicit single-entry "options" list — a plain bool default is ignored by the
#   validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction — PINNED"},
    "stop_frac":      {"default": 2.25,  "min": 2.25,  "max": 2.25,  "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit — PINNED OFF (the simplification)"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop — PINNED OFF (the simplification)"},
    "be_after_R":     {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk) — PINNED at the plateau center"},
    "target_R":       {"default": 5.5,  "min": 5.5,  "max": 5.5,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED"},
    "atr_filter":     {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) — PINNED"},
    "vpace_filter":   {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) — PINNED"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays — PINNED on"},
}

# arm math is ORB_3_6's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
